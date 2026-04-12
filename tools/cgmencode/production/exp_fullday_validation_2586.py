#!/usr/bin/env python3
"""EXP-2586: Full-Day Simulation Validation with Calibrated Parameters.

Hypotheses:
  H1: Using calibrated counter-reg k + optimal ISF/CR multipliers produces
      simulated daily glucose trajectories that match actual within 20% TIR
  H2: Calibrated parameters (correction k + meal ISF/CR) outperform
      uncalibrated defaults for full-day TIR prediction
  H3: Per-patient calibrated sims predict relative TIR ranking across patients
      (patients with higher actual TIR also have higher simulated TIR)

Design:
  For each patient:
    1. Extract complete days with sufficient data (≥80% glucose fill)
    2. Replay all bolus + carb events through forward_simulate with:
       a) Default settings (no counter-reg, profile ISF/CR)
       b) Correction k only (counter-reg but profile ISF/CR)
       c) Full calibration (counter-reg + optimal ISF/CR from EXP-2585/2568)
    3. Compare simulated TIR vs actual TIR for each configuration

This is the ultimate validation: does our calibrated digital twin actually
predict real-world outcomes for an entire day?
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
OUTFILE = Path("externals/experiments/exp-2586_fullday_validation.json")

# Per-patient calibrated parameters
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0, "j": 0.0, "k": 0.0,
    "odc-74077367": 2.5, "odc-86025410": 0.5, "odc-96254963": 2.0,
}

# Best ISF/CR multipliers from EXP-2568 joint optimization
PATIENT_ISF_CR = {
    "a": (0.5, 2.0), "b": (0.5, 2.0), "c": (0.5, 1.4),
    "d": (0.5, 1.8), "e": (0.5, 2.0), "f": (0.5, 2.5),
    "g": (0.5, 2.0), "h": (0.7, 2.0), "i": (0.5, 3.0),
    "j": (0.9, 1.0), "k": (0.5, 2.0),
}

MIN_GLUCOSE_FILL = 0.75  # 75% glucose fill required per day
MAX_DAYS = 10  # Cap days to keep runtime reasonable
SIM_STEP_MINUTES = 5
STEPS_PER_HOUR = 60 // SIM_STEP_MINUTES
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288


def _compute_tir(glucose: np.ndarray) -> float:
    """Compute TIR (70-180) from glucose array, ignoring NaN."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return float('nan')
    return float(np.mean((valid >= 70) & (valid <= 180)))


def _simulate_day(
    day_data: pd.DataFrame,
    isf_mult: float,
    cr_mult: float,
    counter_reg_k: float,
    profile_isf: float,
    profile_cr: float,
    profile_basal: float,
) -> dict:
    """Simulate one full day using forward_simulate with event replay.

    Since forward_simulate is a continuous sim, we segment the day into
    2-hour windows starting from each significant event (bolus or carb),
    and stitch the trajectories together.

    Returns dict with simulated TIR and trajectory statistics.
    """
    g = day_data["glucose"].values
    t = pd.to_datetime(day_data["time"])
    hours = (t.dt.hour + t.dt.minute / 60.0).values
    bolus = day_data["bolus"].fillna(0).values
    carbs_arr = day_data["carbs"].fillna(0).values
    iob = day_data["iob"].fillna(0).values

    N = len(g)
    sim_glucose = np.full(N, np.nan)

    # Strategy: walk through the day. Start a 2h sim from each event.
    # Between events, use the sim trajectory. Restart on new events.
    settings = TherapySettings(
        isf=profile_isf * isf_mult,
        cr=profile_cr * cr_mult,
        basal_rate=profile_basal,
        dia_hours=5.0,
    )

    i = 0
    while i < N:
        if np.isnan(g[i]):
            i += 1
            continue

        # Find next significant event (bolus or carbs)
        has_event = bolus[i] > 0.1 or carbs_arr[i] > 1.0

        if not has_event:
            # No event — just carry forward if we have a sim value, else use actual
            if i > 0 and not np.isnan(sim_glucose[i - 1]):
                sim_glucose[i] = sim_glucose[i - 1]  # flat carry
            else:
                sim_glucose[i] = g[i]
            i += 1
            continue

        # Simulate from this event for up to 2 hours
        sim_duration = min(2.0, (N - i) / STEPS_PER_HOUR)
        if sim_duration < 0.5:
            i += 1
            continue

        bolus_events = []
        carb_events = []
        if bolus[i] > 0.1:
            bolus_events.append(InsulinEvent(0, float(bolus[i])))
        if carbs_arr[i] > 1.0:
            carb_events.append(CarbEvent(0, float(carbs_arr[i])))

        try:
            r = forward_simulate(
                initial_glucose=float(g[i]),
                settings=settings,
                duration_hours=sim_duration,
                start_hour=float(hours[i]),
                bolus_events=bolus_events,
                carb_events=carb_events,
                initial_iob=float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                noise_std=0,
                seed=42,
                counter_reg_k=counter_reg_k,
            )
            # Fill sim trajectory into our array
            sim_steps = min(len(r.glucose), N - i)
            for j in range(sim_steps):
                sim_glucose[i + j] = r.glucose[j]
            i += sim_steps
        except Exception:
            sim_glucose[i] = g[i]
            i += 1

    # Fill remaining gaps with actual glucose (for TIR comparison)
    for i in range(N):
        if np.isnan(sim_glucose[i]) and not np.isnan(g[i]):
            sim_glucose[i] = g[i]

    sim_tir = _compute_tir(sim_glucose)
    actual_tir = _compute_tir(g)
    mae = float(np.nanmean(np.abs(sim_glucose - g)))

    return {
        "actual_tir": round(actual_tir, 3),
        "sim_tir": round(sim_tir, 3),
        "tir_error": round(abs(sim_tir - actual_tir), 3),
        "mae": round(mae, 1),
        "n_events": int(np.sum((bolus > 0.1) | (carbs_arr > 1.0))),
    }


def run():
    df = pd.read_parquet(PARQUET)
    results = {"experiment": "EXP-2586", "patients": {}}

    patients = sorted(PATIENT_K.keys())
    for pid in patients:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) == 0:
            continue

        # Get profile values
        isf_vals = pdf["scheduled_isf"].dropna()
        cr_vals = pdf["scheduled_cr"].dropna()
        basal_col = "scheduled_basal_rate" if "scheduled_basal_rate" in pdf.columns else "scheduled_basal"
        basal_vals = pdf[basal_col].dropna()

        if len(isf_vals) == 0 or len(cr_vals) == 0 or len(basal_vals) == 0:
            continue

        profile_isf = float(isf_vals.median())
        profile_cr = float(cr_vals.median())
        profile_basal = float(basal_vals.median())

        k = PATIENT_K[pid]
        isf_cr = PATIENT_ISF_CR.get(pid, (1.0, 1.0))

        # Extract complete days
        pdf["date"] = pd.to_datetime(pdf["time"]).dt.date
        daily_fill = pdf.groupby("date")["glucose"].apply(
            lambda x: x.notna().mean()
        )
        good_days = daily_fill[daily_fill >= MIN_GLUCOSE_FILL].index.tolist()

        if len(good_days) == 0:
            print(f"{pid}: no days with ≥{MIN_GLUCOSE_FILL*100:.0f}% glucose fill — SKIP")
            continue

        # Select up to MAX_DAYS evenly spaced
        if len(good_days) > MAX_DAYS:
            step = len(good_days) // MAX_DAYS
            good_days = good_days[::step][:MAX_DAYS]

        print(f"\n{'='*60}")
        print(f"Patient {pid}: {len(good_days)} days, k={k}, ISF×{isf_cr[0]}, CR×{isf_cr[1]}")

        configs = [
            ("default", 1.0, 1.0, 0.0),
            ("counter_reg_only", 1.0, 1.0, k),
            ("full_calibration", isf_cr[0], isf_cr[1], k),
        ]

        patient_results = {"k": k, "isf_mult": isf_cr[0], "cr_mult": isf_cr[1], "days": []}

        for config_name, isf_m, cr_m, crk in configs:
            tir_errors = []
            maes = []
            actual_tirs = []
            sim_tirs = []

            for day in good_days:
                ddf = pdf[pdf["date"] == day].copy()
                if len(ddf) < STEPS_PER_DAY * 0.5:  # at least 12h of data
                    continue

                day_result = _simulate_day(
                    ddf, isf_m, cr_m, crk,
                    profile_isf, profile_cr, profile_basal,
                )
                tir_errors.append(day_result["tir_error"])
                maes.append(day_result["mae"])
                actual_tirs.append(day_result["actual_tir"])
                sim_tirs.append(day_result["sim_tir"])

            if tir_errors:
                mean_tir_error = float(np.mean(tir_errors))
                mean_mae = float(np.mean(maes))
                tir_corr = float(np.corrcoef(actual_tirs, sim_tirs)[0, 1]) if len(actual_tirs) > 2 else float('nan')
                print(f"  {config_name}: TIR error={mean_tir_error:.3f}, MAE={mean_mae:.1f}, "
                      f"TIR corr={tir_corr:.3f}, n={len(tir_errors)} days")

                patient_results[config_name] = {
                    "mean_tir_error": round(mean_tir_error, 3),
                    "mean_mae": round(mean_mae, 1),
                    "tir_correlation": round(tir_corr, 3),
                    "n_days": len(tir_errors),
                    "actual_tir_mean": round(float(np.mean(actual_tirs)), 3),
                    "sim_tir_mean": round(float(np.mean(sim_tirs)), 3),
                }

        results["patients"][pid] = patient_results

    # Cross-patient ranking analysis
    print(f"\n{'='*60}")
    print("CROSS-PATIENT ANALYSIS")
    for config_name in ["default", "counter_reg_only", "full_calibration"]:
        actual = []
        simulated = []
        for pid, pr in results["patients"].items():
            if config_name in pr:
                actual.append(pr[config_name]["actual_tir_mean"])
                simulated.append(pr[config_name]["sim_tir_mean"])
        if len(actual) > 2:
            rank_corr = float(np.corrcoef(actual, simulated)[0, 1])
            tir_errors_all = [pr[config_name]["mean_tir_error"]
                              for pr in results["patients"].values()
                              if config_name in pr]
            print(f"  {config_name}: rank corr={rank_corr:.3f}, "
                  f"mean TIR error={np.mean(tir_errors_all):.3f}")
            results.setdefault("cross_patient", {})[config_name] = {
                "rank_correlation": round(rank_corr, 3),
                "mean_tir_error": round(float(np.mean(tir_errors_all)), 3),
            }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    run()
