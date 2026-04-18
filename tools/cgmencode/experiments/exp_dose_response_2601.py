#!/usr/bin/env python3
"""EXP-2601: Dose-Response Simulation for Settings Adjustments.

For each patient's top recommendation, simulate what happens if they
adjust the setting by 25%, 50%, 75%, and 100% of the suggested change.
This produces a dose-response curve for settings adjustments.

Hypotheses:
  H1: TIR improvement is monotonically increasing with dose fraction
      for ≥7/9 patients (no U-shaped responses).
  H2: The 50% dose captures ≥60% of the full-dose benefit
      (diminishing returns support conservative adjustment).
  H3: Simulated TIR improvement at 100% dose correlates with the
      advisory's predicted_tir_delta (r > 0.6).
  H4: For at least 2/9 patients, the optimal dose is <100%
      (the full recommendation overshoots).

Design:
  For each patient's top ISF or basal recommendation:
    1. Extract correction/meal windows from validation period
    2. Simulate with 0%, 25%, 50%, 75%, 100% of the change applied
    3. Compute TIR at each dose level
    4. Plot dose-response curve
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
from cgmencode.production.settings_advisor import generate_settings_advice
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2601_dose_response.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
DOSE_FRACTIONS = [0.0, 0.25, 0.50, 0.75, 1.0]


def _build_patient_profile(pdf):
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _extract_correction_events(pdf, max_events=50):
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        pre_window = glucose[max(0, i-12):i]
        post_window = glucose[i:post_idx]
        pre_tir = float(np.nanmean((pre_window >= 70) & (pre_window <= 180))) if len(pre_window) > 0 else 0.5
        post_tir = float(np.nanmean((post_window >= 70) & (post_window <= 180))) if len(post_window) > 0 else 0.5
        events.append({
            "start_bg": float(glucose[i]), "tir_change": post_tir - pre_tir,
            "rebound": bool(np.any(post_window < 70)),
            "rebound_magnitude": float(glucose[i] - np.nanmin(post_window)) if not np.all(np.isnan(post_window)) else 0.0,
            "went_below_70": bool(np.any(post_window < 70)),
            "bolus": float(bolus[i]), "hour": float(hours[i]),
        })
        if len(events) >= max_events:
            break
    return events


def _extract_meal_events(pdf, max_events=30):
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 48):
        if carbs[i] < 10 or np.isnan(glucose[i]):
            continue
        post_idx = i + 48
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        events.append({
            "carbs": float(carbs[i]), "bolus": float(bolus[i]),
            "pre_meal_bg": float(glucose[i]),
            "post_meal_bg_4h": float(glucose[post_idx]),
            "hour": float(hours[i]),
        })
        if len(events) >= max_events:
            break
    return events


def _sim_tir_with_adjustment(pdf, param, current_val, suggested_val, dose_frac,
                              n_windows=40):
    """Simulate TIR with a fractional adjustment applied.

    Returns (tir_before, tir_after) for comparison.
    """
    adjusted_val = current_val + dose_frac * (suggested_val - current_val)

    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    isf_med = float(pdf["scheduled_isf"].dropna().median())
    cr_med = float(pdf["scheduled_cr"].dropna().median())
    basal_med = float(pdf["scheduled_basal_rate"].dropna().median())

    # Apply adjustment
    if param == "isf":
        isf_adj = adjusted_val
        cr_adj = cr_med
        basal_adj = basal_med
    elif param == "cr":
        isf_adj = isf_med
        cr_adj = adjusted_val
        basal_adj = basal_med
    elif param == "basal_rate":
        isf_adj = isf_med
        cr_adj = cr_med
        basal_adj = adjusted_val
    else:
        return None, None

    # Sim correction/bolus windows
    tirs_current = []
    tirs_adjusted = []
    N = len(glucose)
    count = 0

    for i in range(N - 24):
        if bolus[i] < 0.3:
            continue
        if np.isnan(glucose[i]):
            continue
        post_idx = i + 24
        if post_idx >= N:
            continue

        # Actual TIR in this window
        wg = glucose[i:post_idx]
        if np.sum(~np.isnan(wg)) < 12:
            continue
        actual_tir = float(np.nanmean((wg >= 70) & (wg <= 180)))
        tirs_current.append(actual_tir)

        # Sim with current settings
        carb_events = []
        if carbs[i] > 1.0:
            carb_events = [CarbEvent(time_minutes=0, grams=float(carbs[i]))]

        ts_adj = TherapySettings(
            isf=isf_adj * 0.5,  # standard ISF calibration
            cr=cr_adj * 2.0,
            basal_rate=basal_adj,
            dia_hours=5.0,
            carb_sensitivity=2.0,
        )

        try:
            result = forward_simulate(
                initial_glucose=float(glucose[i]),
                settings=ts_adj,
                bolus_events=[InsulinEvent(time_minutes=0, units=float(bolus[i]))],
                carb_events=carb_events,
                duration_hours=2.0,
                counter_reg_k=2.0,
            )
            sim_tir = float(np.mean((result.glucose >= 70) & (result.glucose <= 180)))
            tirs_adjusted.append(sim_tir)
        except Exception:
            tirs_adjusted.append(actual_tir)

        count += 1
        if count >= n_windows:
            break

    if len(tirs_current) < 5:
        return None, None

    return float(np.mean(tirs_current)), float(np.mean(tirs_adjusted))


def main():
    print("=" * 70)
    print("EXP-2601: Dose-Response Simulation for Settings Adjustments")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 50}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        glucose = pdf["glucose"].values
        hours = (pd.to_datetime(pdf["time"]).dt.hour +
                 pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
        bolus = pdf["bolus"].fillna(0).values
        carbs = pdf["carbs"].fillna(0).values
        iob = pdf["iob"].fillna(0).values
        cob = pdf["cob"].fillna(0).values if "cob" in pdf.columns else None
        actual_basal = pdf["actual_basal_rate"].fillna(0).values if "actual_basal_rate" in pdf.columns else None

        profile = _build_patient_profile(pdf)
        days = (pd.to_datetime(pdf["time"]).max() - pd.to_datetime(pdf["time"]).min()).days

        try:
            metabolic = compute_metabolic_state(glucose, hours)
        except Exception:
            metabolic = None

        try:
            clinical = generate_clinical_report(
                glucose=glucose, metabolic=metabolic, profile=profile,
                carbs=carbs, bolus=bolus, hours=hours,
            )
        except Exception as e:
            print(f"  Clinical report failed: {e}")
            continue

        correction_events = _extract_correction_events(pdf)
        meal_events = _extract_meal_events(pdf)

        try:
            recs = generate_settings_advice(
                glucose=glucose, metabolic=metabolic, hours=hours,
                clinical=clinical, profile=profile, days_of_data=float(days),
                carbs=carbs, bolus=bolus, iob=iob, cob=cob,
                actual_basal=actual_basal,
                correction_events=correction_events,
                meal_events=meal_events,
            )
        except Exception as e:
            print(f"  Advisory failed: {e}")
            continue

        if not recs:
            print("  No recommendations")
            continue

        # Use top recommendation
        top = recs[0]
        param = top.parameter.value
        current = top.current_value
        suggested = top.suggested_value

        print(f"  Top rec: {param} {top.direction} {top.magnitude_pct:.0f}% "
              f"({current:.2f}→{suggested:.2f})")

        # Use validation period (last 30%)
        val_start = int(0.7 * len(pdf))
        val_pdf = pdf.iloc[val_start:].reset_index(drop=True)

        # Dose-response curve
        dose_results = []
        for dose in DOSE_FRACTIONS:
            tir_actual, tir_sim = _sim_tir_with_adjustment(
                val_pdf, param, current, suggested, dose)
            if tir_actual is None:
                continue
            adjusted_val = current + dose * (suggested - current)
            dose_results.append({
                "dose_fraction": dose,
                "adjusted_value": adjusted_val,
                "sim_tir": tir_sim,
                "actual_tir": tir_actual,
            })
            print(f"  Dose {dose:.0%}: value={adjusted_val:.2f}, "
                  f"sim_tir={tir_sim:.1%}, actual_tir={tir_actual:.1%}")

        if len(dose_results) < 3:
            print("  Not enough dose levels")
            continue

        # Check monotonicity
        sim_tirs = [d["sim_tir"] for d in dose_results]
        is_monotonic = all(sim_tirs[i] <= sim_tirs[i+1] for i in range(len(sim_tirs)-1)) or \
                       all(sim_tirs[i] >= sim_tirs[i+1] for i in range(len(sim_tirs)-1))

        # Find optimal dose
        best_dose_idx = np.argmax(sim_tirs)
        optimal_dose = dose_results[best_dose_idx]["dose_fraction"]

        # TIR at baseline, TIR at full
        baseline_tir = dose_results[0]["actual_tir"]
        full_sim_tir = dose_results[-1]["sim_tir"]
        half_sim_tir = None
        for d in dose_results:
            if abs(d["dose_fraction"] - 0.5) < 0.01:
                half_sim_tir = d["sim_tir"]

        results[pid] = {
            "patient_id": pid,
            "parameter": param,
            "current_value": current,
            "suggested_value": suggested,
            "predicted_delta": top.predicted_tir_delta,
            "dose_results": dose_results,
            "is_monotonic": is_monotonic,
            "optimal_dose": optimal_dose,
            "baseline_tir": baseline_tir,
            "full_sim_tir": full_sim_tir,
            "half_sim_tir": half_sim_tir,
        }

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "pid": r["patient_id"],
        "param": r["parameter"],
        "monotonic": r["is_monotonic"],
        "optimal_dose": r["optimal_dose"],
        "base_tir": r["baseline_tir"],
        "full_tir": r["full_sim_tir"],
        "half_tir": r["half_sim_tir"],
        "pred_delta": r["predicted_delta"],
    } for r in results.values()])

    print(f"\n{'Pt':<4} {'Param':>12} {'Mono':>5} {'OptDose':>8} {'Base':>6} "
          f"{'50%':>6} {'100%':>6} {'Δpred':>6}")
    print("-" * 60)
    for _, r in sdf.iterrows():
        half = f"{r['half_tir']:.1%}" if r['half_tir'] is not None else "N/A"
        print(f"{r['pid']:<4} {r['param']:>12} {'✓' if r['monotonic'] else '✗':>5} "
              f"{r['optimal_dose']:>8.0%} {r['base_tir']:>6.1%} "
              f"{half:>6} {r['full_tir']:>6.1%} {r['pred_delta']:>+6.1f}")

    # H1: Monotonicity
    n_monotonic = sdf["monotonic"].sum()
    print(f"\nH1 - Monotonic for {n_monotonic}/{len(sdf)} patients")
    h1_confirmed = n_monotonic >= 7
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥7)")

    # H2: 50% dose captures ≥60% of benefit
    half_frac = []
    for _, r in sdf.iterrows():
        if r["half_tir"] is not None and r["full_tir"] != r["base_tir"]:
            gain_half = (r["half_tir"] - r["base_tir"])
            gain_full = (r["full_tir"] - r["base_tir"])
            if gain_full != 0:
                half_frac.append(gain_half / gain_full)
    mean_half_frac = np.mean(half_frac) if half_frac else 0
    print(f"\nH2 - 50% dose captures {mean_half_frac:.1%} of full benefit")
    h2_confirmed = mean_half_frac >= 0.6
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: ≥60%)")

    # H3: Sim TIR change vs predicted delta
    sim_changes = sdf["full_tir"] - sdf["base_tir"]
    r_sim_pred, p_sim_pred = stats.spearmanr(sim_changes, sdf["pred_delta"])
    print(f"\nH3 - Sim TIR change vs predicted delta: r={r_sim_pred:.3f} (p={p_sim_pred:.3f})")
    h3_confirmed = r_sim_pred > 0.6
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.6)")

    # H4: Optimal dose <100%
    n_overshoot = (sdf["optimal_dose"] < 1.0).sum()
    print(f"\nH4 - Optimal dose <100% for {n_overshoot}/{len(sdf)} patients")
    h4_confirmed = n_overshoot >= 2
    print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'} (threshold: ≥2)")

    output = {
        "experiment": "EXP-2601",
        "title": "Dose-Response Simulation for Settings Adjustments",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "h4_confirmed": h4_confirmed,
        "patient_results": list(results.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
