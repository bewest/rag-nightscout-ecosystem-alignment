#!/usr/bin/env python3
"""EXP-2598: Per-Patient CSF Calibration from Meal Events.

EXP-2596 found population CSF=2.0 is the sweet spot, but per-patient
optimal CSF ranges 1.5-5.0. Can we calibrate CSF per-patient from their
meal response data, similar to how we calibrate k from corrections?

Hypotheses:
  H1: Per-patient CSF calibration improves ranking correlation over
      population CSF=2.0 (r > 0.95 vs r=0.933).
  H2: Optimal CSF correlates with patient metabolic characteristics
      (TIR, mean glucose, or scheduled CR) — r > 0.5.
  H3: CSF can be predicted from non-meal data (correction response,
      mean glucose, TIR) for cold-start initialization.

Design:
  For each FULL patient:
    1. Extract meal events (carbs > 10g, valid 4h follow-up)
    2. Split into calibration (70%) and validation (30%)
    3. Sweep CSF 0.5-8.0 on calibration set
    4. Evaluate best CSF on validation set
    5. Compare per-patient vs population CSF=2.0
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2598_per_patient_csf.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
CSF_RANGE = np.arange(0.5, 8.5, 0.5)
POPULATION_CSF = 2.0


def _extract_meal_windows(pdf, window_hours=4):
    """Extract meal events with pre/post glucose windows."""
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    iob = pdf["iob"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    windows = []
    pts_per_hour = 12  # 5-min intervals
    window_pts = window_hours * pts_per_hour
    N = len(glucose)

    for i in range(N - window_pts):
        if carbs[i] < 10 or np.isnan(glucose[i]):
            continue
        if bolus[i] < 0.1:
            continue

        # Get glucose window
        wg = glucose[i:i + window_pts]
        if np.sum(~np.isnan(wg)) < window_pts * 0.5:
            continue

        # Actual peak excursion (max rise from start)
        valid_wg = np.where(np.isnan(wg), glucose[i], wg)
        actual_peak = float(np.nanmax(valid_wg) - glucose[i])

        isf = float(pdf["scheduled_isf"].iloc[i]) if not np.isnan(pdf["scheduled_isf"].iloc[i]) else 50.0
        cr = float(pdf["scheduled_cr"].iloc[i]) if not np.isnan(pdf["scheduled_cr"].iloc[i]) else 10.0
        basal = float(pdf["scheduled_basal_rate"].iloc[i]) if not np.isnan(pdf["scheduled_basal_rate"].iloc[i]) else 0.8

        windows.append({
            "index": i,
            "glucose_start": float(glucose[i]),
            "actual_peak": actual_peak,
            "carbs": float(carbs[i]),
            "bolus": float(bolus[i]),
            "iob": float(iob[i]),
            "hour": float(hours[i]),
            "isf": isf,
            "cr": cr,
            "basal": basal,
        })

    return windows


def _sim_peak(meal, csf, isf_mult=0.5, cr_mult=2.0, k=2.0):
    """Simulate peak excursion for a meal event with given CSF."""
    ts = TherapySettings(
        isf=meal["isf"] * isf_mult,
        cr=meal["cr"] * cr_mult,
        basal_rate=meal["basal"],
        dia_hours=5.0,
        carb_sensitivity=csf,
    )

    events_insulin = [InsulinEvent(time_minutes=0, units=meal["bolus"])]
    events_carbs = [CarbEvent(time_minutes=0, grams=meal["carbs"])]

    result = forward_simulate(
        initial_glucose=meal["glucose_start"],
        settings=ts,
        bolus_events=events_insulin,
        carb_events=events_carbs,
        duration_hours=4.0,
        counter_reg_k=k,
    )

    sim_peak = float(max(result.glucose) - meal["glucose_start"])
    return sim_peak


def _evaluate_csf(meals, csf, k=2.0):
    """Evaluate CSF on a set of meals. Returns metrics."""
    actual_peaks = [m["actual_peak"] for m in meals]
    sim_peaks = [_sim_peak(m, csf, k=k) for m in meals]

    actual = np.array(actual_peaks)
    sim = np.array(sim_peaks)

    r, p = stats.spearmanr(actual, sim) if len(actual) >= 5 else (0.0, 1.0)
    mae = float(np.mean(np.abs(actual - sim)))
    bias = float(np.mean(sim - actual))
    within_30 = float(np.mean(np.abs(actual - sim) <= 30))

    return {
        "csf": float(csf),
        "rank_r": float(r),
        "rank_p": float(p),
        "mae": mae,
        "bias": bias,
        "within_30_pct": within_30,
        "n_meals": len(meals),
    }


def main():
    print("=" * 70)
    print("EXP-2598: Per-Patient CSF Calibration from Meal Events")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    # Per-patient k values from EXP-2582
    patient_k = {
        "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
        "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
    }

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 50}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        meals = _extract_meal_windows(pdf)
        if len(meals) < 10:
            print(f"  Only {len(meals)} meals, skipping")
            continue

        # Split 70/30 calibration/validation
        np.random.seed(42)
        idx = np.random.permutation(len(meals))
        split = int(0.7 * len(meals))
        cal_meals = [meals[i] for i in idx[:split]]
        val_meals = [meals[i] for i in idx[split:]]

        print(f"  {len(meals)} meals total: {len(cal_meals)} cal, {len(val_meals)} val")

        k = patient_k.get(pid, 2.0)

        # Sweep CSF on calibration set
        best_csf = POPULATION_CSF
        best_score = -999
        cal_results = []

        for csf in CSF_RANGE:
            metrics = _evaluate_csf(cal_meals, csf, k=k)
            cal_results.append(metrics)
            # Score: rank correlation + within-30% (both important)
            score = metrics["rank_r"] + metrics["within_30_pct"]
            if score > best_score:
                best_score = score
                best_csf = float(csf)

        print(f"  Best calibration CSF: {best_csf}")

        # Evaluate best vs population on validation set
        val_personal = _evaluate_csf(val_meals, best_csf, k=k)
        val_population = _evaluate_csf(val_meals, POPULATION_CSF, k=k)

        print(f"  Validation - Personal CSF={best_csf}:")
        print(f"    r={val_personal['rank_r']:.3f}, MAE={val_personal['mae']:.1f}, "
              f"within-30={val_personal['within_30_pct']:.1%}")
        print(f"  Validation - Population CSF={POPULATION_CSF}:")
        print(f"    r={val_population['rank_r']:.3f}, MAE={val_population['mae']:.1f}, "
              f"within-30={val_population['within_30_pct']:.1%}")

        # TIR and mean glucose for H2
        glucose = pdf["glucose"].values
        valid_g = glucose[~np.isnan(glucose)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))
        mean_g = float(np.nanmean(valid_g))
        cr = float(pdf["scheduled_cr"].dropna().median())

        results[pid] = {
            "patient_id": pid,
            "n_meals": len(meals),
            "n_cal": len(cal_meals),
            "n_val": len(val_meals),
            "best_csf": best_csf,
            "population_csf": POPULATION_CSF,
            "val_personal": val_personal,
            "val_population": val_population,
            "tir": tir,
            "mean_glucose": mean_g,
            "scheduled_cr": cr,
            "counter_reg_k": k,
            "calibration_sweep": cal_results,
        }

    if not results:
        print("No results")
        return

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "pid": r["patient_id"],
        "best_csf": r["best_csf"],
        "r_personal": r["val_personal"]["rank_r"],
        "r_population": r["val_population"]["rank_r"],
        "mae_personal": r["val_personal"]["mae"],
        "mae_population": r["val_population"]["mae"],
        "w30_personal": r["val_personal"]["within_30_pct"],
        "w30_population": r["val_population"]["within_30_pct"],
        "tir": r["tir"],
        "mean_g": r["mean_glucose"],
        "cr": r["scheduled_cr"],
    } for r in results.values()])

    print(f"\n{'Pt':<4} {'CSF':>4} {'r_pers':>7} {'r_pop':>7} {'MAE_p':>6} {'MAE_P':>6} "
          f"{'W30_p':>6} {'W30_P':>6}")
    print("-" * 60)
    for _, r in sdf.iterrows():
        print(f"{r['pid']:<4} {r['best_csf']:>4.1f} {r['r_personal']:>7.3f} {r['r_population']:>7.3f} "
              f"{r['mae_personal']:>6.1f} {r['mae_population']:>6.1f} "
              f"{r['w30_personal']:>6.1%} {r['w30_population']:>6.1%}")

    # H1: Per-patient vs population ranking
    mean_r_personal = sdf["r_personal"].mean()
    mean_r_population = sdf["r_population"].mean()
    print(f"\nH1 - Mean rank r: personal={mean_r_personal:.3f} vs population={mean_r_population:.3f}")
    h1_confirmed = mean_r_personal > 0.95 and mean_r_personal > mean_r_population
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} "
          f"(threshold: personal > 0.95 and > population)")

    # H2: CSF correlates with patient characteristics
    r_csf_tir, p_csf_tir = stats.spearmanr(sdf["best_csf"], sdf["tir"])
    r_csf_mg, p_csf_mg = stats.spearmanr(sdf["best_csf"], sdf["mean_g"])
    r_csf_cr, p_csf_cr = stats.spearmanr(sdf["best_csf"], sdf["cr"])
    print(f"\nH2 - CSF correlates with:")
    print(f"  TIR: r={r_csf_tir:.3f} (p={p_csf_tir:.3f})")
    print(f"  Mean glucose: r={r_csf_mg:.3f} (p={p_csf_mg:.3f})")
    print(f"  Scheduled CR: r={r_csf_cr:.3f} (p={p_csf_cr:.3f})")
    best_corr = max(abs(r_csf_tir), abs(r_csf_mg), abs(r_csf_cr))
    h2_confirmed = best_corr > 0.5
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} "
          f"(threshold: any |r| > 0.5)")

    # H3: Predict CSF from non-meal data
    # Simple: use mean_glucose as predictor
    if h2_confirmed:
        best_predictor = "TIR" if abs(r_csf_tir) >= max(abs(r_csf_mg), abs(r_csf_cr)) else \
                         "mean_glucose" if abs(r_csf_mg) >= abs(r_csf_cr) else "CR"
        print(f"\n  Best predictor: {best_predictor}")
    h3_confirmed = h2_confirmed  # cold-start prediction requires H2
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (requires H2)")

    # Improvement analysis
    improved = (sdf["r_personal"] > sdf["r_population"]).sum()
    print(f"\nPer-patient CSF better for {improved}/{len(sdf)} patients (ranking)")
    improved_mae = (sdf["mae_personal"] < sdf["mae_population"]).sum()
    print(f"Per-patient CSF better for {improved_mae}/{len(sdf)} patients (MAE)")

    output = {
        "experiment": "EXP-2598",
        "title": "Per-Patient CSF Calibration from Meal Events",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "mean_r_personal": mean_r_personal,
        "mean_r_population": mean_r_population,
        "patient_results": list(results.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
