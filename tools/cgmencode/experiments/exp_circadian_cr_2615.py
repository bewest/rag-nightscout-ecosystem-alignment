#!/usr/bin/env python3
"""EXP-2615: Circadian CR Advisory Productionization.

From EXP-2609: dawn CR is tighter (lower) than evening CR for 6/9 patients.
This experiment validates whether a time-block-specific CR recommendation
improves post-meal outcomes over the global CR recommendation.

H1: Per-block effective CR explains ≥5pp more post-meal TIR variance than
    global effective CR (R² improvement) for ≥5/9 patients.
H2: Dawn block (4-10h) has a significantly lower effective CR than evening
    (16-22h) with p < 0.1 by paired t-test across patients.
H3: Meals during dawn block have worse post-meal TIR than evening block
    (≥3pp difference), consistent with dawn phenomenon requiring more insulin.

Design:
- Extract meals per time block (dawn 4-10, day 10-16, evening 16-22, overnight 22-4)
- Compute per-block effective CR
- Compare post-meal TIR across blocks
- Validate statistical significance of circadian pattern
- If confirmed: add circadian_cr recommendation to settings_advisor

Also tests whether adding ODC patients shows same pattern.
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
OUTFILE = Path("externals/experiments/exp-2615_circadian_cr.json")
ALL_PATIENTS = [
    "a", "b", "c", "d", "e", "f", "g", "i", "k",
    "odc-74077367", "odc-86025410", "odc-96254963",
]

TIME_BLOCKS = {
    "dawn": (4, 10),
    "day": (10, 16),
    "evening": (16, 22),
    "overnight": (22, 4),
}

MEAL_MIN_CARBS = 10
MEAL_MIN_BOLUS = 0.5
POST_MEAL_WINDOW = 36


def _classify_block(hour):
    for name, (start, end) in TIME_BLOCKS.items():
        if start < end:
            if start <= hour < end:
                return name
        else:
            if hour >= start or hour < end:
                return name
    return "day"


def _extract_block_meals(pdf, max_per_block=50):
    """Extract meals classified by time block."""
    block_meals = {b: [] for b in TIME_BLOCKS}

    carb_mask = (pdf["carbs"] >= MEAL_MIN_CARBS) & (pdf["bolus"] >= MEAL_MIN_BOLUS)
    meal_indices = pdf.index[carb_mask].tolist()

    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())

    for idx in meal_indices:
        pos = pdf.index.get_loc(idx)
        if pos + POST_MEAL_WINDOW >= len(pdf):
            continue

        row = pdf.iloc[pos]
        pre_g = row["glucose"]
        if np.isnan(pre_g):
            continue

        block = _classify_block(int(row["time"].hour))
        if len(block_meals[block]) >= max_per_block:
            continue

        post = pdf.iloc[pos:pos + POST_MEAL_WINDOW]["glucose"].values
        valid = ~np.isnan(post)
        if np.sum(valid) < POST_MEAL_WINDOW * 0.4:
            continue

        # Skip contaminated
        extra = pdf.iloc[pos + 1:pos + POST_MEAL_WINDOW]["carbs"].sum()
        if extra > 5:
            continue

        carbs_val = float(row["carbs"])
        bolus_val = float(row["bolus"])
        peak_rise = float(np.nanmax(post) - pre_g)
        post_valid = post[valid]
        post_tir = float(np.mean((post_valid >= 70) & (post_valid <= 180)) * 100)

        # Effective CR
        glucose_from_carbs = peak_rise + bolus_val * isf
        if glucose_from_carbs > 0 and isf > 0:
            eff_insulin = glucose_from_carbs / isf
            eff_cr = carbs_val / eff_insulin if eff_insulin > 0 else None
        else:
            eff_cr = None

        if eff_cr is not None and 0.5 < eff_cr < 100:
            block_meals[block].append({
                "carbs": carbs_val,
                "bolus": bolus_val,
                "pre_g": float(pre_g),
                "peak_rise": peak_rise,
                "post_tir": post_tir,
                "effective_cr": eff_cr,
                "profile_cr": cr,
            })

    return block_meals


def main():
    print("=" * 70)
    print("EXP-2615: Circadian CR Advisory Productionization")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}
    dawn_crs_all = []
    evening_crs_all = []
    dawn_tirs_all = []
    evening_tirs_all = []

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        ctrl = "ODC" if pid.startswith("odc") else "NS"
        print(f"\n{'='*50}")
        print(f"PATIENT {pid} ({ctrl})")
        print(f"{'='*50}")

        block_meals = _extract_block_meals(pdf)

        block_stats = {}
        global_cr = []
        for block, meals in block_meals.items():
            if len(meals) < 3:
                continue
            crs = [m["effective_cr"] for m in meals]
            tirs = [m["post_tir"] for m in meals]
            global_cr.extend(crs)
            block_stats[block] = {
                "n": len(meals),
                "median_cr": round(float(np.median(crs)), 1),
                "mean_tir": round(float(np.mean(tirs)), 1),
                "cr_std": round(float(np.std(crs)), 1),
            }
            print(f"  {block:>10s}: CR={np.median(crs):.1f}, TIR={np.mean(tirs):.1f}%, n={len(meals)}")

        if not global_cr or len(block_stats) < 2:
            print(f"  Insufficient data")
            continue

        global_median_cr = float(np.median(global_cr))

        # Per-block vs global TIR prediction
        # For each meal, predict adequacy using global CR vs block CR
        block_r2_improvement = []
        for block, meals in block_meals.items():
            if len(meals) < 5:
                continue
            tirs = [m["post_tir"] for m in meals]
            global_dists = [abs(m["effective_cr"] - global_median_cr) for m in meals]
            block_cr = np.median([m["effective_cr"] for m in meals])
            block_dists = [abs(m["effective_cr"] - block_cr) for m in meals]

            if len(set(global_dists)) > 1 and len(set(block_dists)) > 1:
                r_global = stats.pearsonr(global_dists, tirs)[0] ** 2
                r_block = stats.pearsonr(block_dists, tirs)[0] ** 2
                block_r2_improvement.append(r_block - r_global)

        # Dawn vs evening comparison
        dawn_cr = block_stats.get("dawn", {}).get("median_cr")
        evening_cr = block_stats.get("evening", {}).get("median_cr")
        dawn_tir = block_stats.get("dawn", {}).get("mean_tir")
        evening_tir = block_stats.get("evening", {}).get("mean_tir")

        if dawn_cr is not None:
            dawn_crs_all.append(dawn_cr)
        if evening_cr is not None:
            evening_crs_all.append(evening_cr)
        if dawn_tir is not None:
            dawn_tirs_all.append(dawn_tir)
        if evening_tir is not None:
            evening_tirs_all.append(evening_tir)

        results[pid] = {
            "ctrl": ctrl,
            "global_cr": round(global_median_cr, 1),
            "block_stats": block_stats,
            "dawn_tighter": dawn_cr is not None and evening_cr is not None and dawn_cr < evening_cr,
            "r2_improvement_mean": round(float(np.mean(block_r2_improvement)), 3) if block_r2_improvement else None,
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT ANALYSIS")
    print("=" * 70)

    # H1: Per-block improves R² for ≥5 patients
    h1_count = sum(1 for r in results.values()
                   if r["r2_improvement_mean"] is not None and r["r2_improvement_mean"] > 0.05)
    h1_confirmed = h1_count >= 5
    print(f"\nH1 - Per-block R² improvement > 5%: {h1_count}/{len(results)}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H2: Dawn CR lower than evening (paired test)
    paired = [(r["block_stats"].get("dawn", {}).get("median_cr"),
               r["block_stats"].get("evening", {}).get("median_cr"))
              for r in results.values()
              if "dawn" in r["block_stats"] and "evening" in r["block_stats"]]
    if len(paired) >= 5:
        dawn_vals = [p[0] for p in paired]
        evening_vals = [p[1] for p in paired]
        t_stat, t_p = stats.ttest_rel(dawn_vals, evening_vals)
        dawn_lower = sum(1 for d, e in paired if d < e)
        h2_confirmed = t_p < 0.1 and np.mean(dawn_vals) < np.mean(evening_vals)
    else:
        t_stat, t_p = 0, 1
        dawn_lower = 0
        h2_confirmed = False

    print(f"\nH2 - Dawn CR < Evening CR:")
    print(f"  Dawn mean={np.mean(dawn_crs_all):.1f}, Evening mean={np.mean(evening_crs_all):.1f}")
    print(f"  {dawn_lower}/{len(paired)} patients have dawn < evening")
    print(f"  Paired t-test: t={t_stat:.3f}, p={t_p:.4f}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: p < 0.1)")

    # H3: Dawn TIR worse than evening
    if dawn_tirs_all and evening_tirs_all:
        dawn_tir_mean = np.mean(dawn_tirs_all)
        evening_tir_mean = np.mean(evening_tirs_all)
        tir_diff = evening_tir_mean - dawn_tir_mean
        h3_confirmed = tir_diff >= 3
        print(f"\nH3 - Dawn TIR={dawn_tir_mean:.1f}%, Evening TIR={evening_tir_mean:.1f}%")
        print(f"  Difference: {tir_diff:+.1f}pp")
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: ≥3pp)")
    else:
        h3_confirmed = False
        tir_diff = 0
        print(f"\nH3 - Insufficient data")

    # Summary
    print(f"\n{'Pt':>18s}  {'Ctrl':>4s}  {'Dawn':>6s}  {'Day':>6s}  {'Eve':>6s}  {'Night':>6s}  {'Dawn<Eve':>8s}")
    print("-" * 60)
    for pid, r in sorted(results.items()):
        bs = r["block_stats"]
        print(f"{pid:>18s}  {r['ctrl']:>4s}  "
              f"{bs.get('dawn', {}).get('median_cr', '-'):>6}  "
              f"{bs.get('day', {}).get('median_cr', '-'):>6}  "
              f"{bs.get('evening', {}).get('median_cr', '-'):>6}  "
              f"{bs.get('overnight', {}).get('median_cr', '-'):>6}  "
              f"{'YES' if r['dawn_tighter'] else 'NO':>8s}")

    output = {
        "experiment": "EXP-2615",
        "title": "Circadian CR Advisory Productionization",
        "patients": results,
        "hypotheses": {
            "H1": {"count": h1_count, "confirmed": h1_confirmed},
            "H2": {"t_stat": round(t_stat, 3), "p": round(t_p, 4),
                    "dawn_lower_count": dawn_lower, "confirmed": h2_confirmed},
            "H3": {"tir_diff": round(tir_diff, 1), "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
