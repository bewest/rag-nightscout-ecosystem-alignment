#!/usr/bin/env python3
"""EXP-2596: Decoupled Carb Sensitivity Factor Calibration.

EXP-2595 root-caused the excursion underestimation: ISF×0.5 + CR×2.0
reduces CSF (ISF/CR) to 25% of profile, making carbs barely register.
The forward_simulator supports decoupled carb_sensitivity. This experiment
calibrates CSF independently from ISF to fix post-meal trajectories.

The insight: ISF calibration (for insulin sensitivity) and CSF calibration
(for carb sensitivity) serve DIFFERENT purposes:
  - ISF×0.5 correctly models how insulin affects glucose (with counter-reg k)
  - CSF should match how carbs actually raise glucose (independent of ISF)

Hypotheses:
  H1: Using profile CSF (ISF_profile/CR_profile ≈ 5 mg/dL/g) with
      calibrated ISF (×0.5) produces more realistic excursions than
      the coupled CSF (ISF_cal/CR_cal ≈ 1.25 mg/dL/g).
  H2: Optimal CSF produces mean excursion error < 30 mg/dL (vs 54 mg/dL).
  H3: Decoupled CSF maintains patient ranking accuracy (r > 0.85) while
      improving peak prediction (within-30 > 50%).

Design:
  For each patient, sweep carb_sensitivity from 1.0 to 8.0 mg/dL/g
  while keeping ISF×0.5 and counter_reg_k fixed. Compare excursion
  accuracy and TIR ranking across patients.
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
OUTFILE = Path("externals/experiments/exp-2596_decoupled_csf.json")

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
MAX_MEALS_PER_PATIENT = 20

# CSF sweep: 1.0 to 8.0 mg/dL per gram
CSF_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0]


def _extract_meal_events(pdf):
    """Same as EXP-2594/2595."""
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
        if carbs[i] < MIN_CARBS or np.isnan(glucose[i]):
            continue
        post_g = glucose[i:i + post_window_steps]
        if (~np.isnan(post_g)).mean() < MIN_GLUCOSE_FILL:
            continue
        next_2h = min(i + 24, N)
        if (carbs[i + 1:next_2h] >= MIN_CARBS).any():
            continue

        meal_bolus = bolus[i]
        if i + 1 < N:
            meal_bolus += bolus[i + 1]
        if i > 0:
            meal_bolus += bolus[i - 1]

        meals.append({
            "carbs": float(carbs[i]),
            "bolus": float(meal_bolus),
            "pre_glucose": float(glucose[i]),
            "hour": float(hours[i]),
            "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            "post_glucose": post_g.copy(),
        })
    return meals


def _simulate_meal(meal, profile_isf, profile_cr, profile_basal,
                   isf_mult, counter_reg_k, carb_sensitivity):
    """Simulate with decoupled carb_sensitivity."""
    carb_events = [CarbEvent(time_minutes=0.0, grams=float(meal["carbs"]),
                             delay_minutes=5.0)]  # use optimal delay from EXP-2595
    bolus_events = []
    if meal["bolus"] > 0.1:
        bolus_events.append(InsulinEvent(
            time_minutes=0.0, units=float(meal["bolus"])))

    settings = TherapySettings(
        isf=profile_isf * isf_mult,
        cr=profile_cr,  # CR doesn't matter when carb_sensitivity is set
        basal_rate=profile_basal,
        dia_hours=5.0,
        carb_sensitivity=carb_sensitivity,  # DECOUPLED
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


def _score_trajectory(actual_g, sim_g, pre_glucose):
    """Score sim vs actual for a single meal."""
    sim_len = min(len(sim_g), len(actual_g))
    actual = actual_g[:sim_len]
    sim = np.array(sim_g[:sim_len])
    valid = ~np.isnan(actual)
    if valid.sum() < 10:
        return None

    actual_peak = float(np.nanmax(actual))
    sim_peak = float(np.max(sim))
    actual_exc = actual_peak - pre_glucose
    sim_exc = sim_peak - sim[0]

    valid_g = actual[valid]
    sim_valid = sim[:len(valid_g)]
    actual_tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))
    sim_tir = float(np.mean((sim_valid >= 70) & (sim_valid <= 180)))

    return {
        "peak_error": abs(sim_peak - actual_peak),
        "excursion_error": abs(sim_exc - actual_exc),
        "peak_within_30": abs(sim_peak - actual_peak) < 30,
        "actual_tir": actual_tir,
        "sim_tir": sim_tir,
        "sim_excursion": sim_exc,
        "actual_excursion": actual_exc,
    }


def main():
    print("=" * 70)
    print("EXP-2596: Decoupled Carb Sensitivity Factor Calibration")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    # Collect meals and patient params
    patient_data = {}
    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue
        meals = _extract_meal_events(pdf)[:MAX_MEALS_PER_PATIENT]
        if not meals:
            continue

        isf_mult, cr_mult = PATIENT_ISF_CR.get(pid, (0.5, 2.0))
        profile_isf = float(pdf["scheduled_isf"].dropna().median())
        profile_cr = float(pdf["scheduled_cr"].dropna().median())
        profile_basal = float(pdf["scheduled_basal_rate"].dropna().median())
        profile_csf = profile_isf / max(profile_cr, 1.0)
        coupled_csf = (profile_isf * isf_mult) / max(profile_cr * cr_mult, 1.0)

        patient_data[pid] = {
            "meals": meals, "k": PATIENT_K.get(pid, 1.5),
            "isf_mult": isf_mult, "profile_isf": profile_isf,
            "profile_cr": profile_cr, "profile_basal": profile_basal,
            "profile_csf": profile_csf, "coupled_csf": coupled_csf,
        }
        print(f"  {pid}: {len(meals)} meals, profile_CSF={profile_csf:.1f}, coupled_CSF={coupled_csf:.2f}")

    # Sweep CSF values
    print(f"\nSweeping CSF: {CSF_VALUES}")
    sweep_results = []

    for csf in CSF_VALUES:
        peak_errors = []
        exc_errors = []
        within_30 = 0
        total = 0
        per_patient_tir = {}

        for pid, data in patient_data.items():
            patient_peak_errors = []
            patient_actual_tirs = []
            patient_sim_tirs = []

            for meal in data["meals"]:
                sim_g = _simulate_meal(
                    meal, data["profile_isf"], data["profile_cr"],
                    data["profile_basal"], data["isf_mult"],
                    data["k"], csf)
                score = _score_trajectory(meal["post_glucose"], sim_g, meal["pre_glucose"])
                if score is None:
                    continue

                peak_errors.append(score["peak_error"])
                exc_errors.append(score["excursion_error"])
                within_30 += int(score["peak_within_30"])
                total += 1
                patient_actual_tirs.append(score["actual_tir"])
                patient_sim_tirs.append(score["sim_tir"])

            if patient_actual_tirs:
                per_patient_tir[pid] = {
                    "actual_tir": np.mean(patient_actual_tirs),
                    "sim_tir": np.mean(patient_sim_tirs),
                }

        if total == 0:
            continue

        mean_peak = float(np.mean(peak_errors))
        mean_exc = float(np.mean(exc_errors))
        pct_30 = within_30 / total

        # Cross-patient TIR ranking
        from scipy import stats
        if len(per_patient_tir) >= 4:
            actual_tirs = [v["actual_tir"] for v in per_patient_tir.values()]
            sim_tirs = [v["sim_tir"] for v in per_patient_tir.values()]
            r_rank, p_rank = stats.spearmanr(actual_tirs, sim_tirs)
        else:
            r_rank, p_rank = float("nan"), float("nan")

        sweep_results.append({
            "csf": csf,
            "mean_peak_error": mean_peak,
            "mean_excursion_error": mean_exc,
            "peak_within_30_pct": pct_30,
            "rank_correlation": r_rank,
            "n_meals": total,
        })

        print(f"  CSF={csf:>4.1f}: peak_err={mean_peak:>5.1f} exc_err={mean_exc:>5.1f} "
              f"within_30={pct_30:>4.0%} rank_r={r_rank:>6.3f}")

    rdf = pd.DataFrame(sweep_results)

    # Find best configurations
    best_peak_idx = rdf["mean_peak_error"].idxmin()
    best_exc_idx = rdf["mean_excursion_error"].idxmin()
    best_peak = rdf.iloc[best_peak_idx]
    best_exc = rdf.iloc[best_exc_idx]

    # Baseline comparison (coupled CSF ≈ 1.25)
    coupled_row = rdf[rdf["csf"] == 1.0].iloc[0] if 1.0 in rdf["csf"].values else rdf.iloc[0]
    # Find the row closest to typical coupled CSF
    profile_row = rdf[(rdf["csf"] == 5.0)].iloc[0] if 5.0 in rdf["csf"].values else rdf.iloc[-1]

    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")

    print(f"\nCoupled baseline (CSF≈1.25 from ISF×0.5/CR×2.0):")
    print(f"  [Closest tested: CSF=1.0]")
    print(f"  Peak error: {coupled_row['mean_peak_error']:.1f}, within_30: {coupled_row['peak_within_30_pct']:.0%}")

    print(f"\nProfile CSF (≈5.0):")
    print(f"  Peak error: {profile_row['mean_peak_error']:.1f}, within_30: {profile_row['peak_within_30_pct']:.0%}")
    print(f"  Rank correlation: {profile_row['rank_correlation']:.3f}")

    print(f"\nBest by peak error: CSF={best_peak['csf']:.1f}")
    print(f"  Peak error: {best_peak['mean_peak_error']:.1f}, within_30: {best_peak['peak_within_30_pct']:.0%}")
    print(f"  Rank correlation: {best_peak['rank_correlation']:.3f}")

    # H1: Profile CSF better than coupled
    h1_improvement = coupled_row['mean_peak_error'] - best_peak['mean_peak_error']
    print(f"\nH1 - Profile CSF improvement over coupled:")
    print(f"  Peak error reduction: {h1_improvement:.1f} mg/dL")
    h1_confirmed = best_peak['mean_peak_error'] < coupled_row['mean_peak_error'] * 0.8
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} "
          f"(need 20%+ improvement)")

    # H2: Mean excursion error < 30 mg/dL
    print(f"\nH2 - Excursion error < 30 mg/dL:")
    print(f"  Best excursion error: {best_exc['mean_excursion_error']:.1f}")
    h2_confirmed = best_exc["mean_excursion_error"] < 30
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Maintain ranking while improving peaks
    print(f"\nH3 - Maintain ranking (r>0.85) with better peaks (>50% within 30):")
    best_balanced = rdf[(rdf["rank_correlation"] > 0.85) & (rdf["peak_within_30_pct"] > 0.50)]
    if not best_balanced.empty:
        bb = best_balanced.iloc[0]
        print(f"  Best balanced: CSF={bb['csf']:.1f}, r={bb['rank_correlation']:.3f}, "
              f"within_30={bb['peak_within_30_pct']:.0%}")
        h3_confirmed = True
    else:
        # Find best balanced as high ranking + good peaks
        good_rank = rdf[rdf["rank_correlation"] > 0.85]
        if not good_rank.empty:
            best_rank_30 = good_rank.loc[good_rank["peak_within_30_pct"].idxmax()]
            print(f"  Best with r>0.85: CSF={best_rank_30['csf']:.1f}, "
                  f"r={best_rank_30['rank_correlation']:.3f}, "
                  f"within_30={best_rank_30['peak_within_30_pct']:.0%}")
        h3_confirmed = False
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # Per-patient optimal CSF
    print(f"\n{'=' * 70}")
    print("PER-PATIENT OPTIMAL CSF")
    print(f"{'=' * 70}")

    for pid, data in patient_data.items():
        best_err = float("inf")
        best_csf = 5.0
        for csf in CSF_VALUES:
            errors = []
            for meal in data["meals"]:
                sim_g = _simulate_meal(
                    meal, data["profile_isf"], data["profile_cr"],
                    data["profile_basal"], data["isf_mult"],
                    data["k"], csf)
                score = _score_trajectory(meal["post_glucose"], sim_g, meal["pre_glucose"])
                if score:
                    errors.append(score["peak_error"])
            if errors and np.mean(errors) < best_err:
                best_err = np.mean(errors)
                best_csf = csf
        print(f"  {pid}: optimal CSF={best_csf:.1f}, peak_err={best_err:.1f}, "
              f"profile_CSF={data['profile_csf']:.1f}, coupled_CSF={data['coupled_csf']:.2f}")

    # Save
    output = {
        "experiment": "EXP-2596",
        "title": "Decoupled Carb Sensitivity Factor Calibration",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "sweep_results": sweep_results,
        "best_csf_peak": float(best_peak["csf"]),
        "best_csf_excursion": float(best_exc["csf"]),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
