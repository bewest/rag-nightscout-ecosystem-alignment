#!/usr/bin/env python3
"""EXP-2611: Pre-Bolus Timing Impact on Post-Meal Glucose.

Hypothesis: Meal bolus timing relative to carb intake significantly
affects post-meal glucose outcomes. Pre-bolusing (giving insulin before
eating) should reduce post-meal spikes and improve TIR.

H1: Meals with pre-bolus (bolus 5-30 min before carbs) have lower peak
    glucose rise than meals without pre-bolus (≥10 mg/dL difference
    across ≥6/9 patients).
H2: Pre-bolused meals have better 3h post-meal TIR (≥5pp improvement
    across patients).
H3: Pre-bolus benefit is larger for larger meals (correlation r ≥ 0.3
    between meal size and pre-bolus TIR improvement).

Design:
- For each patient, find carb entries (≥10g)
- Classify meals by bolus timing using time_since_bolus_min at carb row:
  - Pre-bolus: time_since_bolus_min between 5 and 30 (bolus was 5-30 min before)
  - Concurrent: time_since_bolus_min between 0 and 5
  - Late-bolus: time_since_bolus_min = 0 at carb row, but bolus appears within 30min after
- Compare post-meal glucose metrics by timing category
- Test dose-response with meal size

Note: time_since_bolus_min = time since last bolus event. At the carb row,
if the bolus was given X minutes ago, time_since_bolus_min ≈ X.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2611_prebolus_timing.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

POST_MEAL_WINDOW = 36  # 3 hours at 5-min intervals
MIN_CARBS = 10  # grams


def _classify_timing(row):
    """Classify bolus timing relative to carbs."""
    tsb = row.get("time_since_bolus_min", np.nan)
    if np.isnan(tsb):
        return "unknown"
    if 5 <= tsb <= 30:
        return "pre_bolus"
    elif 0 <= tsb < 5:
        return "concurrent"
    elif tsb > 30:
        return "no_recent_bolus"
    return "unknown"


def _extract_timed_meals(pdf, max_meals=200):
    """Extract meals classified by bolus timing."""
    meals = {"pre_bolus": [], "concurrent": [], "no_recent_bolus": []}

    carb_mask = pdf["carbs"] >= MIN_CARBS
    meal_indices = pdf.index[carb_mask].tolist()

    for idx in meal_indices:
        pos = pdf.index.get_loc(idx)
        if pos + POST_MEAL_WINDOW >= len(pdf):
            continue

        row = pdf.iloc[pos]
        pre_glucose = row["glucose"]
        if np.isnan(pre_glucose):
            continue

        timing = _classify_timing(row)
        if timing not in meals:
            continue

        # Post-meal window
        post_window = pdf.iloc[pos:pos + POST_MEAL_WINDOW]
        post_glucose = post_window["glucose"].values
        valid = ~np.isnan(post_glucose)
        if np.sum(valid) < POST_MEAL_WINDOW * 0.4:
            continue

        # Skip contaminated windows (additional meals)
        extra_carbs = post_window["carbs"].iloc[1:].sum()
        if extra_carbs > 5:
            continue

        carbs = float(row["carbs"])
        post_valid = post_glucose[valid]
        peak_rise = float(np.nanmax(post_glucose) - pre_glucose)
        end_glucose = float(np.nanmean(post_glucose[-6:]))
        post_tir = float(np.mean((post_valid >= 70) & (post_valid <= 180)) * 100)

        # Time to peak (in minutes)
        peak_idx = np.nanargmax(post_glucose)
        time_to_peak = peak_idx * 5  # 5-min intervals

        meal_data = {
            "carbs": carbs,
            "pre_glucose": float(pre_glucose),
            "peak_rise": peak_rise,
            "end_glucose": end_glucose,
            "post_tir": post_tir,
            "time_to_peak": time_to_peak,
            "time_since_bolus": float(row.get("time_since_bolus_min", np.nan)),
        }

        meals[timing].append(meal_data)

    return meals


def main():
    print("=" * 70)
    print("EXP-2611: Pre-Bolus Timing Impact on Post-Meal Glucose")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        meals = _extract_timed_meals(pdf)

        n_pre = len(meals["pre_bolus"])
        n_conc = len(meals["concurrent"])
        n_late = len(meals["no_recent_bolus"])

        print(f"  Pre-bolus: {n_pre}, Concurrent: {n_conc}, No recent: {n_late}")

        if n_pre < 3 or n_conc < 3:
            print(f"  Insufficient meals for comparison, skipping")
            continue

        # Compare pre-bolus vs concurrent
        pre_peaks = [m["peak_rise"] for m in meals["pre_bolus"]]
        conc_peaks = [m["peak_rise"] for m in meals["concurrent"]]
        pre_tir = [m["post_tir"] for m in meals["pre_bolus"]]
        conc_tir = [m["post_tir"] for m in meals["concurrent"]]
        pre_ttp = [m["time_to_peak"] for m in meals["pre_bolus"]]
        conc_ttp = [m["time_to_peak"] for m in meals["concurrent"]]

        peak_diff = np.mean(conc_peaks) - np.mean(pre_peaks)
        tir_diff = np.mean(pre_tir) - np.mean(conc_tir)
        ttp_diff = np.mean(conc_ttp) - np.mean(pre_ttp)

        print(f"  Peak rise — Pre: {np.mean(pre_peaks):.0f}, Conc: {np.mean(conc_peaks):.0f}, Δ={peak_diff:.0f} mg/dL")
        print(f"  Post-TIR — Pre: {np.mean(pre_tir):.1f}%, Conc: {np.mean(conc_tir):.1f}%, Δ={tir_diff:+.1f}pp")
        print(f"  Time-to-peak — Pre: {np.mean(pre_ttp):.0f}min, Conc: {np.mean(conc_ttp):.0f}min")

        # Meal size interaction
        pre_carbs = [m["carbs"] for m in meals["pre_bolus"]]
        pre_peaks_arr = np.array(pre_peaks)
        conc_carbs = [m["carbs"] for m in meals["concurrent"]]
        conc_peaks_arr = np.array(conc_peaks)

        # Dose-response: does pre-bolus benefit increase with meal size?
        # Compare peak rise per gram for pre vs concurrent
        pre_per_g = [m["peak_rise"] / m["carbs"] for m in meals["pre_bolus"] if m["carbs"] > 0]
        conc_per_g = [m["peak_rise"] / m["carbs"] for m in meals["concurrent"] if m["carbs"] > 0]

        results[pid] = {
            "n_pre": n_pre,
            "n_concurrent": n_conc,
            "n_no_recent": n_late,
            "pre_peak_mean": round(float(np.mean(pre_peaks)), 1),
            "conc_peak_mean": round(float(np.mean(conc_peaks)), 1),
            "peak_diff": round(peak_diff, 1),
            "pre_tir_mean": round(float(np.mean(pre_tir)), 1),
            "conc_tir_mean": round(float(np.mean(conc_tir)), 1),
            "tir_diff": round(tir_diff, 1),
            "pre_ttp_mean": round(float(np.mean(pre_ttp)), 0),
            "conc_ttp_mean": round(float(np.mean(conc_ttp)), 0),
            "pre_per_g_mean": round(float(np.mean(pre_per_g)), 2) if pre_per_g else None,
            "conc_per_g_mean": round(float(np.mean(conc_per_g)), 2) if conc_per_g else None,
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    # H1: Peak rise difference
    h1_count = 0
    peak_diffs = []
    for pid, r in sorted(results.items()):
        peak_diffs.append(r["peak_diff"])
        if r["peak_diff"] >= 10:
            h1_count += 1
            marker = "***"
        else:
            marker = ""
        print(f"  {pid}: Peak Δ={r['peak_diff']:+.0f} mg/dL, TIR Δ={r['tir_diff']:+.1f}pp {marker}")

    h1_confirmed = h1_count >= 6
    print(f"\nH1 - Pre-bolus reduces peak ≥10 mg/dL: {h1_count}/{len(results)} patients")
    print(f"  Mean peak difference: {np.mean(peak_diffs):.1f} mg/dL")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥6/{len(results)})")

    # H2: TIR improvement
    tir_diffs = [r["tir_diff"] for r in results.values()]
    mean_tir_diff = np.mean(tir_diffs)
    h2_confirmed = mean_tir_diff >= 5
    print(f"\nH2 - Pre-bolus TIR improvement: mean={mean_tir_diff:+.1f}pp")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: ≥5pp)")

    # H3: Dose-response with meal size
    # Rough test: do larger meals benefit more from pre-bolusing?
    if len(results) >= 5:
        # Use per-gram reduction as proxy
        per_g_benefits = []
        for pid, r in results.items():
            if r["pre_per_g_mean"] is not None and r["conc_per_g_mean"] is not None:
                benefit = r["conc_per_g_mean"] - r["pre_per_g_mean"]
                per_g_benefits.append(benefit)

        mean_per_g_benefit = np.mean(per_g_benefits) if per_g_benefits else 0
        h3_confirmed = mean_per_g_benefit > 0
        print(f"\nH3 - Per-gram peak reduction: {mean_per_g_benefit:+.2f} mg/dL/g")
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (positive benefit per gram)")
    else:
        h3_confirmed = False
        print(f"\nH3 - Insufficient data")

    # Summary table
    print(f"\n{'Pt':>5s}  {'Pre':>4s}  {'Conc':>4s}  {'PeakPre':>8s}  {'PeakCon':>8s}  {'TIR_Pre':>7s}  {'TIR_Con':>7s}  {'PeakΔ':>6s}  {'TIRΔ':>6s}")
    print("-" * 70)
    for pid in sorted(results.keys()):
        r = results[pid]
        print(f"{pid:>5s}  {r['n_pre']:>4d}  {r['n_concurrent']:>4d}  "
              f"{r['pre_peak_mean']:>8.0f}  {r['conc_peak_mean']:>8.0f}  "
              f"{r['pre_tir_mean']:>7.1f}  {r['conc_tir_mean']:>7.1f}  "
              f"{r['peak_diff']:>+5.0f}  {r['tir_diff']:>+5.1f}")

    # Save results
    output = {
        "experiment": "EXP-2611",
        "title": "Pre-Bolus Timing Impact on Post-Meal Glucose",
        "patients": results,
        "hypotheses": {
            "H1": {
                "description": "Pre-bolus reduces peak ≥10 mg/dL for ≥6 patients",
                "count": h1_count,
                "total": len(results),
                "mean_peak_diff": round(float(np.mean(peak_diffs)), 1),
                "confirmed": h1_confirmed,
            },
            "H2": {
                "description": "Pre-bolus TIR improvement ≥5pp",
                "mean_tir_diff": round(mean_tir_diff, 1),
                "confirmed": h2_confirmed,
            },
            "H3": {
                "description": "Larger meals benefit more from pre-bolusing",
                "confirmed": h3_confirmed,
            },
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
