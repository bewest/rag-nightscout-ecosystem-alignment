#!/usr/bin/env python3
"""EXP-2594: Post-Meal Response Simulation Accuracy.

The full-day sim is at ceiling (r=0.883 rank correlation). Post-meal
windows (0-4h after carbs) are where the forward sim should add the
most value since that's where CR/ISF directly determine outcomes.

Hypotheses:
  H1: The forward sim predicts post-meal glucose PEAK within 30 mg/dL
      for ≥60% of meals (using calibrated ISF/CR/k from EXP-2568/2582).
  H2: Predicted time-to-peak matches actual within 30 minutes for ≥50%
      of meals.
  H3: Sim-predicted post-meal TIR (time 70-180 in 0-4h window) correlates
      with actual post-meal TIR (r > 0.5 across patients).
  H4: Meal size categories (small/medium/large) have different sim accuracy
      — the sim works better for small meals than large meals.

Design:
  For each FULL patient:
    1. Identify meal events (carbs ≥ 10g, with sufficient glucose before/after)
    2. Extract 4-hour post-meal glucose window
    3. Simulate the same window with calibrated parameters
    4. Compare: peak, time-to-peak, 4h endpoint, post-meal TIR
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2594_meal_response.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Per-patient calibrated k (EXP-2582)
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
}

# Best ISF/CR multipliers from EXP-2568 joint optimization
PATIENT_ISF_CR = {
    "a": (0.5, 2.0), "b": (0.5, 2.0), "c": (0.5, 1.4),
    "d": (0.5, 1.8), "e": (0.5, 2.0), "f": (0.5, 2.5),
    "g": (0.5, 2.0), "i": (0.5, 3.0), "k": (0.5, 2.0),
}

MIN_CARBS = 10.0  # minimum carbs to count as a meal
POST_MEAL_HOURS = 4.0
STEPS_PER_HOUR = 12  # 5-minute intervals
MIN_GLUCOSE_FILL = 0.70  # 70% of post-meal window must have glucose
MAX_MEALS_PER_PATIENT = 30  # cap for runtime


def _categorize_meal(carbs):
    if carbs < 20:
        return "small"
    elif carbs < 50:
        return "medium"
    else:
        return "large"


def _extract_meal_events(pdf):
    """Extract meal events with sufficient surrounding glucose data."""
    meals = []
    carbs = pdf["carbs"].fillna(0).values
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    times = pd.to_datetime(pdf["time"])
    hours = (times.dt.hour + times.dt.minute / 60.0).values
    iob = pdf["iob"].fillna(0).values

    N = len(pdf)
    post_window_steps = int(POST_MEAL_HOURS * STEPS_PER_HOUR)

    for i in range(N - post_window_steps):
        if carbs[i] < MIN_CARBS:
            continue
        if np.isnan(glucose[i]):
            continue

        # Check post-meal glucose fill
        post_g = glucose[i:i + post_window_steps]
        fill = (~np.isnan(post_g)).mean()
        if fill < MIN_GLUCOSE_FILL:
            continue

        # Skip if another large meal within 2h (confounding)
        next_2h = min(i + 24, N)  # 2h = 24 steps
        other_carbs = carbs[i + 1:next_2h]
        if (other_carbs >= MIN_CARBS).any():
            continue

        # Collect bolus at meal time (may be split across ±1 step)
        meal_bolus = bolus[i]
        if i + 1 < N:
            meal_bolus += bolus[i + 1]
        if i > 0:
            meal_bolus += bolus[i - 1]

        meals.append({
            "index": i,
            "carbs": float(carbs[i]),
            "bolus": float(meal_bolus),
            "pre_glucose": float(glucose[i]),
            "hour": float(hours[i]),
            "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            "category": _categorize_meal(carbs[i]),
            "post_glucose": post_g.copy(),
        })

    return meals


def _simulate_meal(meal, profile_isf, profile_cr, profile_basal,
                   isf_mult, cr_mult, counter_reg_k):
    """Simulate a single meal event and return predicted trajectory."""
    bolus_events = []
    carb_events = [CarbEvent(time_minutes=0.0, grams=float(meal["carbs"]))]

    if meal["bolus"] > 0.1:
        bolus_events.append(InsulinEvent(
            time_minutes=0.0, units=float(meal["bolus"])))

    settings = TherapySettings(
        isf=profile_isf * isf_mult,
        cr=profile_cr * cr_mult,
        basal_rate=profile_basal,
        dia_hours=5.0,
    )

    result = forward_simulate(
        initial_glucose=meal["pre_glucose"],
        settings=settings,
        duration_hours=POST_MEAL_HOURS,
        start_hour=meal["hour"],
        bolus_events=bolus_events,
        carb_events=carb_events,
        initial_iob=meal["iob"],
        noise_std=0.0,
        metabolic_basal_rate=profile_basal,
        counter_reg_k=counter_reg_k,
    )

    return result.glucose


def _analyze_trajectory(glucose, sim_glucose):
    """Compare actual vs simulated post-meal trajectories."""
    valid = ~np.isnan(glucose)
    if valid.sum() < 10:
        return None

    # Actual metrics
    valid_g = glucose.copy()
    valid_g[np.isnan(valid_g)] = np.interp(
        np.flatnonzero(np.isnan(valid_g)),
        np.flatnonzero(~np.isnan(valid_g)),
        valid_g[~np.isnan(valid_g)]
    ) if valid.sum() > 1 else valid_g

    actual_peak = float(np.nanmax(valid_g))
    actual_peak_idx = int(np.nanargmax(valid_g))
    actual_peak_hours = actual_peak_idx / STEPS_PER_HOUR
    actual_endpoint = float(valid_g[-1]) if not np.isnan(valid_g[-1]) else float("nan")
    actual_tir = float(np.mean((valid_g[valid] >= 70) & (valid_g[valid] <= 180)))
    actual_excursion = actual_peak - glucose[0] if not np.isnan(glucose[0]) else float("nan")

    # Sim metrics
    sim_len = min(len(sim_glucose), len(glucose))
    sim_g = np.array(sim_glucose[:sim_len])
    sim_peak = float(np.max(sim_g))
    sim_peak_idx = int(np.argmax(sim_g))
    sim_peak_hours = sim_peak_idx / STEPS_PER_HOUR
    sim_endpoint = float(sim_g[-1])
    sim_tir = float(np.mean((sim_g >= 70) & (sim_g <= 180)))
    sim_excursion = sim_peak - sim_g[0]

    return {
        "actual_peak": actual_peak,
        "sim_peak": sim_peak,
        "peak_error": abs(sim_peak - actual_peak),
        "actual_peak_hours": actual_peak_hours,
        "sim_peak_hours": sim_peak_hours,
        "peak_time_error_min": abs(sim_peak_hours - actual_peak_hours) * 60,
        "actual_endpoint": actual_endpoint,
        "sim_endpoint": sim_endpoint,
        "endpoint_error": abs(sim_endpoint - actual_endpoint) if not np.isnan(actual_endpoint) else float("nan"),
        "actual_tir": actual_tir,
        "sim_tir": sim_tir,
        "tir_error": abs(sim_tir - actual_tir),
        "actual_excursion": actual_excursion,
        "sim_excursion": sim_excursion,
        "excursion_error": abs(sim_excursion - actual_excursion) if not np.isnan(actual_excursion) else float("nan"),
    }


def main():
    print("=" * 70)
    print("EXP-2594: Post-Meal Response Simulation Accuracy")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}
    all_meals = []

    for pid in FULL_PATIENTS:
        print(f"\n--- Patient {pid} ---")
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        k = PATIENT_K.get(pid, 1.5)
        isf_mult, cr_mult = PATIENT_ISF_CR.get(pid, (0.5, 2.0))
        profile_isf = float(pdf["scheduled_isf"].dropna().median())
        profile_cr = float(pdf["scheduled_cr"].dropna().median())
        profile_basal = float(pdf["scheduled_basal_rate"].dropna().median())

        meals = _extract_meal_events(pdf)
        if not meals:
            print(f"  No valid meals found")
            continue

        meals = meals[:MAX_MEALS_PER_PATIENT]
        print(f"  Found {len(meals)} meals")

        meal_results = []
        for m in meals:
            sim_g = _simulate_meal(
                m, profile_isf, profile_cr, profile_basal,
                isf_mult, cr_mult, k)
            analysis = _analyze_trajectory(m["post_glucose"], sim_g)
            if analysis is None:
                continue

            analysis["carbs"] = m["carbs"]
            analysis["bolus"] = m["bolus"]
            analysis["pre_glucose"] = m["pre_glucose"]
            analysis["hour"] = m["hour"]
            analysis["category"] = m["category"]
            analysis["patient_id"] = pid
            meal_results.append(analysis)

        if not meal_results:
            print(f"  No analyzable meals")
            continue

        mdf = pd.DataFrame(meal_results)
        all_meals.extend(meal_results)

        # Per-patient summary
        peak_within_30 = float((mdf["peak_error"] < 30).mean())
        time_within_30 = float((mdf["peak_time_error_min"] < 30).mean())
        mean_peak_err = float(mdf["peak_error"].mean())
        mean_tir_err = float(mdf["tir_error"].mean())

        summary = {
            "patient_id": pid,
            "n_meals": len(mdf),
            "peak_within_30_pct": peak_within_30,
            "time_within_30_pct": time_within_30,
            "mean_peak_error": mean_peak_err,
            "mean_tir_error": mean_tir_err,
            "mean_actual_tir": float(mdf["actual_tir"].mean()),
            "mean_sim_tir": float(mdf["sim_tir"].mean()),
            "by_category": {},
        }
        for cat in ["small", "medium", "large"]:
            cat_df = mdf[mdf["category"] == cat]
            if len(cat_df) > 0:
                summary["by_category"][cat] = {
                    "n": len(cat_df),
                    "mean_peak_error": float(cat_df["peak_error"].mean()),
                    "peak_within_30_pct": float((cat_df["peak_error"] < 30).mean()),
                }

        all_results[pid] = summary
        print(f"  Peak within 30: {peak_within_30:.0%}, Time within 30min: {time_within_30:.0%}")
        print(f"  Mean peak error: {mean_peak_err:.1f} mg/dL, TIR error: {mean_tir_err:.3f}")

    if not all_meals:
        print("No meal results")
        return

    # Cross-patient analysis
    adf = pd.DataFrame(all_meals)
    sdf = pd.DataFrame(list(all_results.values()))
    from scipy import stats

    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    print(f"\nTotal meals analyzed: {len(adf)}")
    print(f"\n{'Patient':<6} {'Meals':>5} {'PkErr':>6} {'Pk<30':>6} {'Tm<30':>6} "
          f"{'TIR_err':>7} {'ActTIR':>6} {'SimTIR':>6}")
    print("-" * 55)
    for _, r in sdf.iterrows():
        print(f"{r['patient_id']:<6} {r['n_meals']:>5} {r['mean_peak_error']:>6.1f} "
              f"{r['peak_within_30_pct']:>6.0%} {r['time_within_30_pct']:>6.0%} "
              f"{r['mean_tir_error']:>7.3f} {r['mean_actual_tir']:>6.1%} "
              f"{r['mean_sim_tir']:>6.1%}")

    # H1: Peak within 30 mg/dL for ≥60% of meals
    peak_within_30 = float((adf["peak_error"] < 30).mean())
    print(f"\nH1 - Peak within 30 mg/dL: {peak_within_30:.1%} (need ≥60%)")
    h1_confirmed = peak_within_30 >= 0.60
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")
    print(f"  Mean peak error: {adf['peak_error'].mean():.1f} mg/dL")
    print(f"  Median peak error: {adf['peak_error'].median():.1f} mg/dL")

    # H2: Time-to-peak within 30 min for ≥50%
    time_within_30 = float((adf["peak_time_error_min"] < 30).mean())
    print(f"\nH2 - Time-to-peak within 30 min: {time_within_30:.1%} (need ≥50%)")
    h2_confirmed = time_within_30 >= 0.50
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")
    print(f"  Mean time error: {adf['peak_time_error_min'].mean():.1f} min")

    # H3: Sim TIR vs actual TIR correlation across patients
    if len(sdf) >= 4:
        r_tir, p_tir = stats.spearmanr(sdf["mean_actual_tir"], sdf["mean_sim_tir"])
        print(f"\nH3 - Sim TIR vs actual TIR across patients: r={r_tir:.3f}, p={p_tir:.3f}")
        h3_confirmed = r_tir > 0.5
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.5)")
    else:
        h3_confirmed = False

    # H4: Accuracy by meal size
    print(f"\nH4 - Accuracy by meal size:")
    for cat in ["small", "medium", "large"]:
        cat_df = adf[adf["category"] == cat]
        if len(cat_df) > 0:
            pk30 = (cat_df["peak_error"] < 30).mean()
            mean_err = cat_df["peak_error"].mean()
            print(f"  {cat:>8}: n={len(cat_df)}, peak_err={mean_err:.1f}, within_30={pk30:.0%}")

    # Check if small > medium > large accuracy
    cat_errs = {}
    for cat in ["small", "medium", "large"]:
        cat_df = adf[adf["category"] == cat]
        if len(cat_df) > 0:
            cat_errs[cat] = cat_df["peak_error"].mean()

    h4_confirmed = (len(cat_errs) >= 2 and
                    cat_errs.get("small", 999) < cat_errs.get("large", 0))
    print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'} "
          f"(small meals more accurate than large)")

    # Additional: excursion analysis
    print(f"\nExcursion Analysis:")
    print(f"  Mean actual excursion: {adf['actual_excursion'].mean():.1f} mg/dL")
    print(f"  Mean sim excursion: {adf['sim_excursion'].mean():.1f} mg/dL")
    excursion_err = adf["excursion_error"].dropna()
    print(f"  Mean excursion error: {excursion_err.mean():.1f} mg/dL")
    r_exc, p_exc = stats.spearmanr(
        adf["actual_excursion"].dropna(), adf["sim_excursion"].iloc[:len(adf["actual_excursion"].dropna())])
    print(f"  Excursion correlation: r={r_exc:.3f}, p={p_exc:.3f}")

    # Sim bias analysis
    peak_bias = adf["sim_peak"].mean() - adf["actual_peak"].mean()
    tir_bias = adf["sim_tir"].mean() - adf["actual_tir"].mean()
    print(f"\nSim Bias:")
    print(f"  Peak bias: {peak_bias:+.1f} mg/dL (positive = sim predicts higher)")
    print(f"  TIR bias: {tir_bias:+.3f} (positive = sim predicts better TIR)")

    output = {
        "experiment": "EXP-2594",
        "title": "Post-Meal Response Simulation Accuracy",
        "total_meals": len(adf),
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "h4_confirmed": h4_confirmed,
        "peak_within_30_pct": peak_within_30,
        "mean_peak_error": float(adf["peak_error"].mean()),
        "patient_summary": sdf.to_dict(orient="records"),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
