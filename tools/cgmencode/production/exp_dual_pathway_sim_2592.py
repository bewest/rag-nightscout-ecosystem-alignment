#!/usr/bin/env python3
"""EXP-2592: Dual-Pathway ISF + Circadian k Full-Day Simulation.

Builds on EXP-2586 (full-day validation) by adding:
  1. Dual-pathway ISF: correction boluses use correction-optimal ISF,
     meal boluses use meal-optimal ISF.
  2. Circadian counter-regulation k: day k vs night k.
  3. Both combined.

Hypotheses:
  H1: Dual-pathway ISF improves full-day TIR prediction over single-ISF
      (reduce mean TIR error by ≥3 percentage points).
  H2: Circadian k improves full-day prediction over constant k
      (reduce mean TIR error by ≥2 percentage points).
  H3: Combined (dual-ISF + circadian k) produces the best full-day
      prediction (rank correlation r > 0.65 vs EXP-2586's 0.623).

Design:
  Replay complete days through forward_simulate with 4 configurations:
    A) EXP-2586 baseline: single ISF + constant k
    B) Dual-pathway ISF + constant k
    C) Single ISF + circadian k
    D) Dual-pathway ISF + circadian k (full model)
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
OUTFILE = Path("externals/experiments/exp-2592_dual_pathway_sim.json")

# FULL telemetry patients only
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Per-patient counter-reg k (EXP-2582)
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
}

# Circadian k (EXP-2588): day vs night
PATIENT_DAY_K = {
    "a": 1.0, "b": 7.0, "c": 4.0, "d": 1.0, "e": 7.0,
    "f": 0.5, "g": 5.0, "i": 7.0, "k": 0.0,
}
PATIENT_NIGHT_K = {
    "a": 7.0, "b": 10.0, "c": 5.0, "d": 7.0, "e": 7.0,
    "f": 1.0, "g": 2.0, "i": 10.0, "k": 0.0,
}

# Meal-optimal ISF/CR (EXP-2568)
PATIENT_MEAL_ISF_CR = {
    "a": (0.5, 2.0), "b": (0.5, 2.0), "c": (0.5, 1.4),
    "d": (0.5, 1.8), "e": (0.5, 2.0), "f": (0.5, 2.5),
    "g": (0.5, 2.0), "i": (0.5, 3.0), "k": (0.5, 2.0),
}

# Correction-optimal ISF (EXP-2585) — used with per-patient k
PATIENT_CORR_ISF = {
    "a": 0.5, "b": 0.5, "c": 2.0, "d": 0.5, "e": 0.5,
    "f": 0.5, "g": 0.5, "i": 0.5, "k": 0.5,
}

MIN_GLUCOSE_FILL = 0.75
MAX_DAYS = 10
STEPS_PER_HOUR = 12
SIM_WINDOW_HOURS = 2.0


def _compute_tir(glucose):
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return float("nan")
    return float(np.mean((valid >= 70) & (valid <= 180)))


def _is_correction_bolus(glucose_at_event, carbs_at_event):
    """Classify bolus as correction (high BG, no carbs) or meal."""
    return glucose_at_event > 150 and carbs_at_event < 1.0


def _simulate_day(day_data, isf_mult, cr_mult, counter_reg_k,
                   profile_isf, profile_cr, profile_basal,
                   dual_pathway=False, corr_isf_mult=None,
                   circadian_k=False, day_k=None, night_k=None):
    """Simulate one day with optional dual-pathway ISF and circadian k."""
    g = day_data["glucose"].values
    t = pd.to_datetime(day_data["time"])
    hours = (t.dt.hour + t.dt.minute / 60.0).values
    bolus = day_data["bolus"].fillna(0).values
    carbs_arr = day_data["carbs"].fillna(0).values

    N = len(g)
    sim_glucose = np.full(N, np.nan)

    i = 0
    while i < N:
        if np.isnan(g[i]):
            i += 1
            continue

        has_event = bolus[i] > 0.1 or carbs_arr[i] > 1.0
        if not has_event:
            if i > 0 and not np.isnan(sim_glucose[i - 1]):
                sim_glucose[i] = sim_glucose[i - 1]
            else:
                sim_glucose[i] = g[i]
            i += 1
            continue

        sim_duration = min(SIM_WINDOW_HOURS, (N - i) / STEPS_PER_HOUR)
        if sim_duration < 0.5:
            i += 1
            continue

        # Determine ISF multiplier based on event type
        event_isf_mult = isf_mult  # default
        if dual_pathway and bolus[i] > 0.1:
            if _is_correction_bolus(g[i], carbs_arr[i]):
                event_isf_mult = corr_isf_mult if corr_isf_mult else isf_mult
            # else: meal → use meal isf_mult (default)

        # Determine k based on time of day
        event_k = counter_reg_k
        if circadian_k and day_k is not None and night_k is not None:
            hour = hours[i]
            event_k = day_k if 6.0 <= hour < 22.0 else night_k

        bolus_events = []
        carb_events = []
        if bolus[i] > 0.1:
            bolus_events.append(InsulinEvent(time_minutes=0.0 * 60.0, units=float(bolus[i])))
        if carbs_arr[i] > 1.0:
            carb_events.append(CarbEvent(time_minutes=0.0 * 60.0, grams=float(carbs_arr[i])))

        # Look for nearby events within the sim window
        sim_steps = int(sim_duration * STEPS_PER_HOUR)
        for j in range(i + 1, min(i + sim_steps, N)):
            dt_h = (j - i) / STEPS_PER_HOUR
            if bolus[j] > 0.1:
                bolus_events.append(InsulinEvent(time_minutes=dt_h * 60.0, units=float(bolus[j])))
            if carbs_arr[j] > 1.0:
                carb_events.append(CarbEvent(time_minutes=dt_h * 60.0, grams=float(carbs_arr[j])))

        settings = TherapySettings(
            isf=profile_isf * event_isf_mult,
            cr=profile_cr * cr_mult,
            basal_rate=profile_basal,
            dia_hours=5.0,
        )

        result = forward_simulate(
            initial_glucose=g[i],
            settings=settings,
            duration_hours=sim_duration,
            start_hour=hours[i],
            bolus_events=bolus_events,
            carb_events=carb_events,
            initial_iob=0.0,
            noise_std=0.0,
            metabolic_basal_rate=profile_basal,
            counter_reg_k=event_k,
        )

        # Write sim results
        sim_len = min(len(result.glucose), sim_steps)
        for j in range(sim_len):
            if i + j < N:
                sim_glucose[i + j] = result.glucose[j]

        i += sim_len

    sim_tir = _compute_tir(sim_glucose)
    actual_tir = _compute_tir(g)
    valid_sim = ~np.isnan(sim_glucose) & ~np.isnan(g)
    mae = float(np.mean(np.abs(sim_glucose[valid_sim] - g[valid_sim]))) if valid_sim.sum() > 10 else float("nan")

    return {
        "sim_tir": sim_tir,
        "actual_tir": actual_tir,
        "tir_error": abs(sim_tir - actual_tir),
        "mae": mae,
        "n_sim_points": int(valid_sim.sum()),
    }


def main():
    print("=" * 70)
    print("EXP-2592: Dual-Pathway ISF + Circadian k Full-Day Simulation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}
    configs = ["baseline", "dual_isf", "circadian_k", "combined"]

    for pid in FULL_PATIENTS:
        print(f"\n--- Patient {pid} ---")
        pdf = df[df["patient_id"] == pid].copy()
        if pdf.empty:
            continue

        pdf["date"] = pd.to_datetime(pdf["time"]).dt.date
        dates = sorted(pdf["date"].unique())

        # Get patient parameters
        k = PATIENT_K.get(pid, 1.5)
        day_k = PATIENT_DAY_K.get(pid, 2.2)
        night_k = PATIENT_NIGHT_K.get(pid, 3.8)
        meal_isf, meal_cr = PATIENT_MEAL_ISF_CR.get(pid, (0.5, 2.0))
        corr_isf = PATIENT_CORR_ISF.get(pid, 0.5)

        profile_isf = float(pdf["scheduled_isf"].dropna().median())
        profile_cr = float(pdf["scheduled_cr"].dropna().median())
        profile_basal = float(pdf["scheduled_basal_rate"].dropna().median())

        patient_days = {c: [] for c in configs}
        n_days = 0

        for d in dates[:MAX_DAYS]:
            ddf = pdf[pdf["date"] == d].sort_values("time")
            if len(ddf) < 200:
                continue
            g = ddf["glucose"].values
            if (~np.isnan(g)).mean() < MIN_GLUCOSE_FILL:
                continue

            n_days += 1

            # A) Baseline: single ISF + constant k (EXP-2586 equivalent)
            r_base = _simulate_day(
                ddf, meal_isf, meal_cr, k,
                profile_isf, profile_cr, profile_basal)
            patient_days["baseline"].append(r_base)

            # B) Dual-pathway ISF + constant k
            r_dual = _simulate_day(
                ddf, meal_isf, meal_cr, k,
                profile_isf, profile_cr, profile_basal,
                dual_pathway=True, corr_isf_mult=corr_isf)
            patient_days["dual_isf"].append(r_dual)

            # C) Single ISF + circadian k
            r_circ = _simulate_day(
                ddf, meal_isf, meal_cr, k,
                profile_isf, profile_cr, profile_basal,
                circadian_k=True, day_k=day_k, night_k=night_k)
            patient_days["circadian_k"].append(r_circ)

            # D) Combined: dual ISF + circadian k
            r_comb = _simulate_day(
                ddf, meal_isf, meal_cr, k,
                profile_isf, profile_cr, profile_basal,
                dual_pathway=True, corr_isf_mult=corr_isf,
                circadian_k=True, day_k=day_k, night_k=night_k)
            patient_days["combined"].append(r_comb)

        if n_days == 0:
            print(f"  No valid days")
            continue

        print(f"  Simulated {n_days} days")

        patient_summary = {"patient_id": pid, "n_days": n_days}
        for c in configs:
            days = patient_days[c]
            if not days:
                continue
            mean_tir_err = float(np.mean([d["tir_error"] for d in days]))
            mean_mae = float(np.nanmean([d["mae"] for d in days]))
            mean_sim_tir = float(np.mean([d["sim_tir"] for d in days]))
            mean_actual_tir = float(np.mean([d["actual_tir"] for d in days]))
            patient_summary[f"{c}_tir_error"] = mean_tir_err
            patient_summary[f"{c}_mae"] = mean_mae
            patient_summary[f"{c}_sim_tir"] = mean_sim_tir
            patient_summary[f"{c}_actual_tir"] = mean_actual_tir

        all_results[pid] = patient_summary
        print(f"  Baseline TIR err: {patient_summary.get('baseline_tir_error', 'N/A'):.3f}")
        print(f"  Dual ISF err:     {patient_summary.get('dual_isf_tir_error', 'N/A'):.3f}")
        print(f"  Circadian k err:  {patient_summary.get('circadian_k_tir_error', 'N/A'):.3f}")
        print(f"  Combined err:     {patient_summary.get('combined_tir_error', 'N/A'):.3f}")

    # Cross-patient analysis
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    sdf = pd.DataFrame(list(all_results.values()))
    if sdf.empty:
        print("No results")
        return

    print(f"\n{'Patient':<4} {'Days':>4} ", end="")
    for c in configs:
        print(f"{'TIRErr_'+c[:4]:>10} ", end="")
    print()
    print("-" * 60)
    for _, r in sdf.iterrows():
        print(f"{r['patient_id']:<4} {r['n_days']:>4} ", end="")
        for c in configs:
            val = r.get(f"{c}_tir_error", float("nan"))
            print(f"{val:>10.3f} ", end="")
        print()

    # Mean errors across patients
    print(f"\n{'Config':<15} {'Mean TIR Error':>15} {'Mean MAE':>10}")
    print("-" * 45)
    for c in configs:
        col = f"{c}_tir_error"
        mae_col = f"{c}_mae"
        if col in sdf.columns:
            mean_err = sdf[col].mean()
            mean_mae = sdf[mae_col].mean() if mae_col in sdf.columns else float("nan")
            print(f"{c:<15} {mean_err:>15.3f} {mean_mae:>10.1f}")

    # H1: Dual ISF improves by ≥3pp
    base_err = sdf["baseline_tir_error"].mean()
    dual_err = sdf["dual_isf_tir_error"].mean()
    improvement_dual = base_err - dual_err
    print(f"\nH1 - Dual ISF improvement: {improvement_dual:+.3f} (need ≥0.030)")
    h1_confirmed = improvement_dual >= 0.030
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: Circadian k improves by ≥2pp
    circ_err = sdf["circadian_k_tir_error"].mean()
    improvement_circ = base_err - circ_err
    print(f"\nH2 - Circadian k improvement: {improvement_circ:+.3f} (need ≥0.020)")
    h2_confirmed = improvement_circ >= 0.020
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Combined rank correlation > 0.65
    from scipy import stats
    valid_h3 = sdf.dropna(subset=["combined_sim_tir", "combined_actual_tir"])
    if len(valid_h3) >= 4:
        r_rank, p_rank = stats.spearmanr(valid_h3["combined_sim_tir"],
                                          valid_h3["combined_actual_tir"])
        print(f"\nH3 - Combined rank correlation: r={r_rank:.3f}, p={p_rank:.3f}")
        h3_confirmed = r_rank > 0.65
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: 0.65)")

        # Compare with baseline rank correlation
        r_base_rank, _ = stats.spearmanr(valid_h3["baseline_sim_tir"],
                                          valid_h3["baseline_actual_tir"])
        print(f"  Baseline rank correlation: r={r_base_rank:.3f}")
        print(f"  Improvement: {r_rank - r_base_rank:+.3f}")
    else:
        h3_confirmed = False

    # Per-patient improvement table
    print(f"\nPer-Patient Improvement (Combined vs Baseline):")
    improved = 0
    for _, r in sdf.iterrows():
        base = r.get("baseline_tir_error", float("nan"))
        comb = r.get("combined_tir_error", float("nan"))
        delta = base - comb
        better = "✓" if delta > 0 else "✗"
        improved += 1 if delta > 0 else 0
        print(f"  {r['patient_id']}: baseline={base:.3f} combined={comb:.3f} Δ={delta:+.3f} {better}")
    print(f"  Improved: {improved}/{len(sdf)}")

    output = {
        "experiment": "EXP-2592",
        "title": "Dual-Pathway ISF + Circadian k Full-Day Simulation",
        "summary": sdf.to_dict(orient="records"),
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "mean_errors": {c: float(sdf[f"{c}_tir_error"].mean()) for c in configs},
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
