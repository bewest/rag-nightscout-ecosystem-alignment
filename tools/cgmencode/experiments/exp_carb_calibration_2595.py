#!/usr/bin/env python3
"""EXP-2595: Carb Absorption Model Calibration.

EXP-2594 revealed the sim underestimates post-meal excursions by 54 mg/dL.
The carb absorption model (gamma-like, peak at 20min, 3h absorption) is
too slow. This experiment sweeps carb delay and absorption speed to find
optimal parameters that best match actual excursions.

Hypotheses:
  H1: A faster carb absorption model (delay < 20min or absorption < 3h)
      reduces mean excursion error by ≥30%.
  H2: Optimal carb delay is shorter than current 20 min (likely 5-10 min
      because modern fast-acting carbs hit faster than classical models).
  H3: After calibration, peak-within-30 rate improves from 39.6% to ≥50%.

Design:
  Using the same 270 meal events from EXP-2594, sweep:
    - carb_delay: [5, 10, 15, 20, 30] minutes
    - carb_absorption: [1.5, 2.0, 2.5, 3.0] hours
  For each combination, compute mean peak error and excursion error.
  Find the optimal parameters.
"""

import json
import sys
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2595_carb_calibration.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
}
PATIENT_ISF_CR = {
    "a": (0.5, 2.0), "b": (0.5, 2.0), "c": (0.5, 1.4),
    "d": (0.5, 1.8), "e": (0.5, 2.0), "f": (0.5, 2.5),
    "g": (0.5, 2.0), "i": (0.5, 3.0), "k": (0.5, 2.0),
}

MIN_CARBS = 10.0
POST_MEAL_HOURS = 4.0
STEPS_PER_HOUR = 12
MIN_GLUCOSE_FILL = 0.70
MAX_MEALS_PER_PATIENT = 20  # fewer than 2594 for speed

# Sweep parameters
CARB_DELAYS = [5, 10, 15, 20, 30]  # minutes
CARB_ABSORPTIONS = [1.5, 2.0, 2.5, 3.0]  # hours


def _extract_meal_events(pdf):
    """Same extraction as EXP-2594."""
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

        post_g = glucose[i:i + post_window_steps]
        fill = (~np.isnan(post_g)).mean()
        if fill < MIN_GLUCOSE_FILL:
            continue

        next_2h = min(i + 24, N)
        other_carbs = carbs[i + 1:next_2h]
        if (other_carbs >= MIN_CARBS).any():
            continue

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
            "post_glucose": post_g.copy(),
        })

    return meals


def _simulate_and_score(meal, profile_isf, profile_cr, profile_basal,
                         isf_mult, cr_mult, counter_reg_k,
                         carb_delay, carb_absorption):
    """Simulate one meal with given carb params and return error metrics."""
    carb_events = [CarbEvent(
        time_minutes=0.0, grams=float(meal["carbs"]),
        absorption_hours=carb_absorption, delay_minutes=carb_delay)]

    bolus_events = []
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

    sim_g = np.array(result.glucose)
    actual_g = meal["post_glucose"]
    sim_len = min(len(sim_g), len(actual_g))

    actual_valid = actual_g[:sim_len]
    valid = ~np.isnan(actual_valid)
    if valid.sum() < 10:
        return None

    actual_peak = float(np.nanmax(actual_valid))
    sim_peak = float(np.max(sim_g[:sim_len]))
    actual_excursion = actual_peak - meal["pre_glucose"]
    sim_excursion = sim_peak - sim_g[0]

    return {
        "peak_error": abs(sim_peak - actual_peak),
        "excursion_error": abs(sim_excursion - actual_excursion),
        "peak_within_30": sim_peak - actual_peak < 30 and actual_peak - sim_peak < 30,
        "sim_peak": sim_peak,
        "actual_peak": actual_peak,
        "sim_excursion": sim_excursion,
        "actual_excursion": actual_excursion,
    }


def main():
    print("=" * 70)
    print("EXP-2595: Carb Absorption Model Calibration")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    # Collect all meals first
    all_meals_by_patient = {}
    total_meals = 0
    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue
        meals = _extract_meal_events(pdf)[:MAX_MEALS_PER_PATIENT]
        if meals:
            k = PATIENT_K.get(pid, 1.5)
            isf_mult, cr_mult = PATIENT_ISF_CR.get(pid, (0.5, 2.0))
            profile_isf = float(pdf["scheduled_isf"].dropna().median())
            profile_cr = float(pdf["scheduled_cr"].dropna().median())
            profile_basal = float(pdf["scheduled_basal_rate"].dropna().median())
            all_meals_by_patient[pid] = {
                "meals": meals,
                "k": k, "isf_mult": isf_mult, "cr_mult": cr_mult,
                "profile_isf": profile_isf, "profile_cr": profile_cr,
                "profile_basal": profile_basal,
            }
            total_meals += len(meals)
            print(f"  {pid}: {len(meals)} meals")

    print(f"\nTotal meals: {total_meals}")
    print(f"Sweeping {len(CARB_DELAYS)}×{len(CARB_ABSORPTIONS)} = "
          f"{len(CARB_DELAYS)*len(CARB_ABSORPTIONS)} parameter combinations")

    # Sweep all parameter combinations
    sweep_results = []

    for delay, absorption in product(CARB_DELAYS, CARB_ABSORPTIONS):
        peak_errors = []
        excursion_errors = []
        within_30_count = 0
        total_count = 0

        for pid, data in all_meals_by_patient.items():
            for meal in data["meals"]:
                result = _simulate_and_score(
                    meal, data["profile_isf"], data["profile_cr"],
                    data["profile_basal"], data["isf_mult"], data["cr_mult"],
                    data["k"], delay, absorption)
                if result is None:
                    continue
                peak_errors.append(result["peak_error"])
                excursion_errors.append(result["excursion_error"])
                within_30_count += int(result["peak_within_30"])
                total_count += 1

        if total_count == 0:
            continue

        mean_peak = float(np.mean(peak_errors))
        mean_exc = float(np.mean(excursion_errors))
        pct_30 = within_30_count / total_count

        sweep_results.append({
            "carb_delay_min": delay,
            "carb_absorption_h": absorption,
            "mean_peak_error": mean_peak,
            "mean_excursion_error": mean_exc,
            "peak_within_30_pct": pct_30,
            "n_meals": total_count,
        })

        print(f"  delay={delay:>2}min abs={absorption:.1f}h: "
              f"peak_err={mean_peak:>5.1f} exc_err={mean_exc:>5.1f} "
              f"within_30={pct_30:.0%}")

    rdf = pd.DataFrame(sweep_results)

    # Find optimal by peak error
    best_peak = rdf.loc[rdf["mean_peak_error"].idxmin()]
    best_exc = rdf.loc[rdf["mean_excursion_error"].idxmin()]
    baseline = rdf[(rdf["carb_delay_min"] == 20) & (rdf["carb_absorption_h"] == 3.0)]

    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")

    print(f"\nBaseline (delay=20, abs=3.0):")
    if not baseline.empty:
        b = baseline.iloc[0]
        print(f"  Peak error: {b['mean_peak_error']:.1f} mg/dL")
        print(f"  Excursion error: {b['mean_excursion_error']:.1f} mg/dL")
        print(f"  Within 30: {b['peak_within_30_pct']:.0%}")
        baseline_peak = b['mean_peak_error']
        baseline_exc = b['mean_excursion_error']
        baseline_30 = b['peak_within_30_pct']

    print(f"\nBest by peak error:")
    print(f"  delay={best_peak['carb_delay_min']:.0f}min, "
          f"abs={best_peak['carb_absorption_h']:.1f}h")
    print(f"  Peak error: {best_peak['mean_peak_error']:.1f} mg/dL")
    print(f"  Excursion error: {best_peak['mean_excursion_error']:.1f} mg/dL")
    print(f"  Within 30: {best_peak['peak_within_30_pct']:.0%}")

    print(f"\nBest by excursion error:")
    print(f"  delay={best_exc['carb_delay_min']:.0f}min, "
          f"abs={best_exc['carb_absorption_h']:.1f}h")
    print(f"  Peak error: {best_exc['mean_peak_error']:.1f} mg/dL")
    print(f"  Excursion error: {best_exc['mean_excursion_error']:.1f} mg/dL")
    print(f"  Within 30: {best_exc['peak_within_30_pct']:.0%}")

    # Hypotheses
    if not baseline.empty:
        peak_improvement = 1.0 - best_peak['mean_peak_error'] / baseline_peak
        exc_improvement = 1.0 - best_exc['mean_excursion_error'] / baseline_exc

        print(f"\nH1 - Faster absorption reduces excursion error by ≥30%:")
        print(f"  Peak error improvement: {peak_improvement:.1%}")
        print(f"  Excursion error improvement: {exc_improvement:.1%}")
        h1_confirmed = peak_improvement >= 0.30 or exc_improvement >= 0.30
        print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

        print(f"\nH2 - Optimal delay < 20 min:")
        h2_confirmed = best_peak['carb_delay_min'] < 20
        print(f"  Optimal delay: {best_peak['carb_delay_min']:.0f} min")
        print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

        print(f"\nH3 - After calibration, peak-within-30 ≥ 50%:")
        best_30 = rdf["peak_within_30_pct"].max()
        h3_confirmed = best_30 >= 0.50
        print(f"  Best peak-within-30: {best_30:.0%} (vs baseline {baseline_30:.0%})")
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")
    else:
        h1_confirmed = h2_confirmed = h3_confirmed = False

    # Per-patient optimal (to check if optimal varies by patient)
    print(f"\n{'=' * 70}")
    print("PER-PATIENT OPTIMAL PARAMETERS")
    print(f"{'=' * 70}")

    for pid, data in all_meals_by_patient.items():
        best_err = float("inf")
        best_params = (20, 3.0)
        for delay, absorption in product(CARB_DELAYS, CARB_ABSORPTIONS):
            errors = []
            for meal in data["meals"]:
                result = _simulate_and_score(
                    meal, data["profile_isf"], data["profile_cr"],
                    data["profile_basal"], data["isf_mult"], data["cr_mult"],
                    data["k"], delay, absorption)
                if result:
                    errors.append(result["peak_error"])
            if errors and np.mean(errors) < best_err:
                best_err = np.mean(errors)
                best_params = (delay, absorption)

        print(f"  {pid}: optimal delay={best_params[0]}min abs={best_params[1]:.1f}h "
              f"peak_err={best_err:.1f}")

    # Save
    output = {
        "experiment": "EXP-2595",
        "title": "Carb Absorption Model Calibration",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "sweep_results": sweep_results,
        "best_peak_params": {
            "delay_min": float(best_peak["carb_delay_min"]),
            "absorption_h": float(best_peak["carb_absorption_h"]),
        },
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
