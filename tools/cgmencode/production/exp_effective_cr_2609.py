#!/usr/bin/env python3
"""EXP-2609: Effective Carb Ratio from Meal Response.

Hypothesis: The actual glucose response to meals reveals an "effective CR"
that differs from the scheduled CR, similar to how correction-based ISF
differs from profile ISF. This effective CR can improve meal-bolus
recommendations.

H1: Effective CR (carbs / insulin_needed_to_offset_meal_rise) differs from
    profile CR by ≥15% for ≥6/9 FULL patients.
H2: Effective CR has circadian variation: morning CR is tighter (lower)
    than evening CR for ≥5/9 patients (dawn phenomenon).
H3: Meals where bolus matches effective CR have better 3h post-meal TIR
    than meals where bolus matches profile CR (≥5pp difference).

Design:
- Extract meal events (carbs ≥ 10g with bolus ≥ 0.5U)
- Compute 3h post-meal glucose trajectory
- Effective CR = carbs / (bolus + correction_insulin_needed)
  where correction_insulin_needed = post_meal_rise / effective_ISF
- Compare effective CR to profile CR per patient and time block
- Classify meals by bolus adequacy (under/over/correct) and compare TIR

If confirmed: Productionize effective CR estimation and advise_effective_cr()
into settings_advisor.py.
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
OUTFILE = Path("externals/experiments/exp-2609_effective_cr.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Time blocks for circadian analysis
TIME_BLOCKS = {
    "dawn": (4, 10),
    "day": (10, 16),
    "evening": (16, 22),
    "overnight": (22, 4),
}

MEAL_MIN_CARBS = 10   # grams
MEAL_MIN_BOLUS = 0.5  # units
POST_MEAL_WINDOW = 36  # 3 hours at 5-min intervals


def _extract_meal_windows(pdf, max_meals=80):
    """Extract meal events with post-meal glucose trajectories."""
    meals = []

    # Find meal events
    carb_mask = (pdf["carbs"] >= MEAL_MIN_CARBS) & (pdf["bolus"] >= MEAL_MIN_BOLUS)
    meal_indices = pdf.index[carb_mask].tolist()

    for idx in meal_indices:
        if len(meals) >= max_meals:
            break

        pos = pdf.index.get_loc(idx)
        if pos + POST_MEAL_WINDOW >= len(pdf):
            continue

        # Pre-meal and post-meal window
        pre_glucose = pdf.iloc[pos]["glucose"]
        if np.isnan(pre_glucose):
            continue

        post_window = pdf.iloc[pos:pos + POST_MEAL_WINDOW]
        post_glucose = post_window["glucose"].values

        # Skip if too many NaN in post-meal window
        valid = ~np.isnan(post_glucose)
        if np.sum(valid) < POST_MEAL_WINDOW * 0.5:
            continue

        # Check for additional meals in window (contamination)
        extra_carbs = post_window["carbs"].iloc[1:].sum()
        if extra_carbs > 5:
            continue  # Skip contaminated windows

        carbs = float(pdf.iloc[pos]["carbs"])
        bolus = float(pdf.iloc[pos]["bolus"])
        hour = int(pdf.iloc[pos]["time"].hour)
        isf = float(pdf.iloc[pos]["scheduled_isf"]) if not np.isnan(pdf.iloc[pos]["scheduled_isf"]) else None
        cr = float(pdf.iloc[pos]["scheduled_cr"]) if not np.isnan(pdf.iloc[pos]["scheduled_cr"]) else None
        iob = float(pdf.iloc[pos]["iob"]) if "iob" in pdf and not np.isnan(pdf.iloc[pos]["iob"]) else 0

        if isf is None or cr is None or isf <= 0 or cr <= 0:
            continue

        # Compute meal metrics
        post_valid = post_glucose[valid]
        peak_rise = float(np.nanmax(post_glucose) - pre_glucose)
        end_glucose = float(np.nanmean(post_glucose[-6:]))  # last 30 min avg
        total_rise = end_glucose - pre_glucose

        # Time in range during post-meal window
        post_tir = float(np.mean((post_valid >= 70) & (post_valid <= 180)) * 100)

        # Effective CR calculation:
        # If the meal caused a rise, we need MORE insulin than was given
        # effective_insulin_needed = carbs / effective_CR
        # actual_insulin_effect = bolus * ISF (in mg/dL)
        # glucose_from_carbs = peak_rise + bolus * ISF (if no insulin, rise would be bigger)
        # effective_CR = carbs / (glucose_from_carbs / ISF)
        glucose_from_carbs = peak_rise + bolus * isf
        if glucose_from_carbs > 0 and isf > 0:
            effective_insulin = glucose_from_carbs / isf
            effective_cr = carbs / effective_insulin if effective_insulin > 0 else None
        else:
            effective_cr = None

        meals.append({
            "carbs": carbs,
            "bolus": bolus,
            "hour": hour,
            "pre_glucose": pre_glucose,
            "peak_rise": peak_rise,
            "end_glucose": end_glucose,
            "total_rise": total_rise,
            "post_tir": post_tir,
            "profile_isf": isf,
            "profile_cr": cr,
            "effective_cr": effective_cr,
            "iob_at_meal": iob,
            "cr_ratio": effective_cr / cr if effective_cr and cr > 0 else None,
        })

    return meals


def _classify_time_block(hour):
    """Classify hour into time block."""
    for name, (start, end) in TIME_BLOCKS.items():
        if start < end:
            if start <= hour < end:
                return name
        else:  # overnight wraps
            if hour >= start or hour < end:
                return name
    return "day"


def main():
    print("=" * 70)
    print("EXP-2609: Effective Carb Ratio from Meal Response")
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

        meals = _extract_meal_windows(pdf)
        if len(meals) < 10:
            print(f"  Only {len(meals)} clean meals, skipping")
            continue

        # Filter to valid effective CR
        valid_meals = [m for m in meals if m["effective_cr"] is not None
                       and 0.5 < m["effective_cr"] < 100]

        if len(valid_meals) < 10:
            print(f"  Only {len(valid_meals)} valid CR meals, skipping")
            continue

        profile_cr = np.median([m["profile_cr"] for m in valid_meals])
        effective_crs = [m["effective_cr"] for m in valid_meals]
        cr_ratios = [m["cr_ratio"] for m in valid_meals if m["cr_ratio"] is not None]
        median_effective_cr = np.median(effective_crs)
        median_ratio = np.median(cr_ratios)

        print(f"  {len(valid_meals)} clean meals analyzed")
        print(f"  Profile CR: {profile_cr:.1f}")
        print(f"  Effective CR: {median_effective_cr:.1f} (median)")
        print(f"  Ratio (effective/profile): {median_ratio:.2f}")

        # Circadian analysis
        block_crs = {}
        for m in valid_meals:
            block = _classify_time_block(m["hour"])
            if block not in block_crs:
                block_crs[block] = []
            block_crs[block].append(m["effective_cr"])

        circadian = {}
        for block, crs in sorted(block_crs.items()):
            if len(crs) >= 3:
                circadian[block] = {
                    "n": len(crs),
                    "median_cr": round(float(np.median(crs)), 1),
                    "mean_cr": round(float(np.mean(crs)), 1),
                    "std_cr": round(float(np.std(crs)), 1),
                }
                print(f"  {block}: CR={np.median(crs):.1f} (n={len(crs)})")

        # Bolus adequacy analysis
        under_bolused = [m for m in valid_meals if m["cr_ratio"] and m["cr_ratio"] < 0.85]
        over_bolused = [m for m in valid_meals if m["cr_ratio"] and m["cr_ratio"] > 1.15]
        correct_bolused = [m for m in valid_meals if m["cr_ratio"]
                          and 0.85 <= m["cr_ratio"] <= 1.15]

        under_tir = np.mean([m["post_tir"] for m in under_bolused]) if under_bolused else 0
        over_tir = np.mean([m["post_tir"] for m in over_bolused]) if over_bolused else 0
        correct_tir = np.mean([m["post_tir"] for m in correct_bolused]) if correct_bolused else 0

        print(f"  Under-bolused ({len(under_bolused)}): post-TIR={under_tir:.1f}%")
        print(f"  Correct ({len(correct_bolused)}): post-TIR={correct_tir:.1f}%")
        print(f"  Over-bolused ({len(over_bolused)}): post-TIR={over_tir:.1f}%")

        # Dawn phenomenon check
        dawn_cr = circadian.get("dawn", {}).get("median_cr", None)
        evening_cr = circadian.get("evening", {}).get("median_cr", None)
        dawn_tighter = dawn_cr is not None and evening_cr is not None and dawn_cr < evening_cr

        results[pid] = {
            "n_meals": len(valid_meals),
            "profile_cr": round(profile_cr, 1),
            "effective_cr_median": round(median_effective_cr, 1),
            "effective_cr_mean": round(float(np.mean(effective_crs)), 1),
            "cr_ratio": round(median_ratio, 2),
            "cr_ratio_std": round(float(np.std(cr_ratios)), 2),
            "circadian": circadian,
            "dawn_tighter": dawn_tighter,
            "bolus_adequacy": {
                "under_n": len(under_bolused),
                "correct_n": len(correct_bolused),
                "over_n": len(over_bolused),
                "under_tir": round(under_tir, 1),
                "correct_tir": round(correct_tir, 1),
                "over_tir": round(over_tir, 1),
            },
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    # H1: Effective CR differs from profile
    h1_count = 0
    print(f"\n{'Pt':>5s}  {'Prof CR':>7s}  {'Eff CR':>7s}  {'Ratio':>6s}  {'Diff%':>6s}")
    print("-" * 40)
    for pid, r in sorted(results.items()):
        diff_pct = abs(r["cr_ratio"] - 1.0) * 100
        marker = "***" if diff_pct >= 15 else ""
        if diff_pct >= 15:
            h1_count += 1
        print(f"{pid:>5s}  {r['profile_cr']:>7.1f}  {r['effective_cr_median']:>7.1f}  "
              f"{r['cr_ratio']:>6.2f}  {diff_pct:>5.1f}% {marker}")

    h1_confirmed = h1_count >= 6
    print(f"\nH1 - Effective CR differs ≥15% from profile: {h1_count}/{len(results)} patients")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥6/{len(results)})")

    # H2: Dawn CR tighter than evening
    h2_count = sum(1 for r in results.values() if r["dawn_tighter"])
    h2_confirmed = h2_count >= 5
    print(f"\nH2 - Dawn CR tighter than evening: {h2_count}/{len(results)} patients")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: ≥5/{len(results)})")

    # H3: Correct-bolused meals have better TIR
    all_under_tir = []
    all_correct_tir = []
    for r in results.values():
        ba = r["bolus_adequacy"]
        if ba["under_n"] >= 3:
            all_under_tir.append(ba["under_tir"])
        if ba["correct_n"] >= 3:
            all_correct_tir.append(ba["correct_tir"])

    if all_correct_tir and all_under_tir:
        h3_diff = np.mean(all_correct_tir) - np.mean(all_under_tir)
        h3_confirmed = h3_diff >= 5
        print(f"\nH3 - Correct-bolused TIR ({np.mean(all_correct_tir):.1f}%) vs "
              f"Under-bolused TIR ({np.mean(all_under_tir):.1f}%)")
        print(f"  Difference: {h3_diff:+.1f}pp")
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: ≥5pp)")
    else:
        h3_confirmed = False
        h3_diff = 0
        print(f"\nH3 - Insufficient data for bolus adequacy comparison")
        print(f"  H3 NOT CONFIRMED")

    # Save results
    output = {
        "experiment": "EXP-2609",
        "title": "Effective Carb Ratio from Meal Response",
        "patients": results,
        "hypotheses": {
            "H1": {
                "description": "Effective CR differs ≥15% from profile",
                "count": h1_count,
                "total": len(results),
                "confirmed": h1_confirmed,
            },
            "H2": {
                "description": "Dawn CR tighter than evening",
                "count": h2_count,
                "total": len(results),
                "confirmed": h2_confirmed,
            },
            "H3": {
                "description": "Correct-bolused meals have better 3h TIR",
                "diff_pp": round(h3_diff, 1),
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
