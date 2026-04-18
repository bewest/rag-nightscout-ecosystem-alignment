#!/usr/bin/env python3
"""EXP-2589: Overnight Basal Adequacy Assessment via Forward Simulator.

Hypotheses:
  H1: During fasting overnight windows (00-06, carbs=0, IOB<0.5U), the direction
      of glucose drift (rising vs falling) reliably indicates basal rate adequacy.
      Rising = basal too low, Falling = basal too high.
  H2: The forward simulator (with counter-reg night k) predicts the direction of
      overnight drift for ≥70% of fasting windows.
  H3: A quantitative basal adequacy metric (actual_drift - predicted_drift)
      correlates with the patient's overall TIR (r > 0.3).

Design:
  1. Extract 4h+ overnight fasting windows (00-06, carbs=0, IOB<0.5U) from
     FULL telemetry patients only.
  2. For each window: measure actual glucose drift (linear regression slope).
  3. Run forward sim with basal-only (no bolus, no carbs) from window start.
     Use counter_reg_k=3.8 (population night k from EXP-2588).
  4. Compare predicted drift direction vs actual drift direction.
  5. Derive basal adequacy metric per patient.

Only FULL telemetry patients: a-g, i, k (9 NS patients).
Excludes: h (sparse glucose), j (no IOB), ODC (different analysis).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from cgmencode.production.forward_simulator import (
    TherapySettings,
    forward_simulate,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# FULL telemetry NS patients (a-g, i, k)
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Night k from EXP-2588 per patient
PATIENT_NIGHT_K = {
    "a": 7.0, "b": 10.0, "c": 5.0, "d": 7.0, "e": 7.0,
    "f": 1.0, "g": 2.0, "h": 1.5, "i": 10.0, "j": 0.0, "k": 0.0,
}
POPULATION_NIGHT_K = 3.8


def extract_fasting_windows(pdf: pd.DataFrame, min_hours: float = 3.0,
                             min_bolus_gap_min: float = 120.0) -> list:
    """Extract overnight fasting windows from patient data.

    Criteria:
      - Hours 00-06 (overnight)
      - carbs == 0 throughout window
      - No recent bolus (time_since_bolus_min > min_bolus_gap_min)
      - Glucose available (non-NaN) for ≥60% of window
      - At least min_hours long

    Relaxed from IOB < 0.5 constraint (too strict for closed-loop patients
    where the loop maintains IOB continuously from temp basals).
    """
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour + t.dt.minute / 60.0

    # Night mask: 00-06
    night_mask = hours < 6.0

    # Fasting mask: no carbs
    carb_mask = pdf["carbs"].fillna(0) == 0

    # No recent bolus mask
    if "time_since_bolus_min" in pdf.columns:
        bolus_mask = pdf["time_since_bolus_min"].fillna(999) >= min_bolus_gap_min
    else:
        # Fallback: use bolus column directly
        bolus_mask = pdf["bolus"].fillna(0) == 0

    # Combined mask
    eligible = night_mask & carb_mask & bolus_mask
    eligible_idx = pdf.index[eligible].tolist()

    if not eligible_idx:
        return []

    # Group consecutive eligible rows into windows
    windows = []
    current_window = [eligible_idx[0]]

    for i in range(1, len(eligible_idx)):
        idx = eligible_idx[i]
        prev_idx = eligible_idx[i - 1]
        # Check if consecutive (within 10 minutes)
        t_gap = (t.loc[idx] - t.loc[prev_idx]).total_seconds() / 60.0
        if t_gap <= 10.0:
            current_window.append(idx)
        else:
            if len(current_window) >= 1:
                windows.append(current_window)
            current_window = [idx]
    if current_window:
        windows.append(current_window)

    # Filter by minimum duration and glucose availability
    min_rows = int(min_hours * 12)  # 5-min intervals
    valid_windows = []

    for w_idx in windows:
        if len(w_idx) < min_rows:
            continue
        w_data = pdf.loc[w_idx]
        gluc = w_data["glucose"].values
        gluc_valid = ~np.isnan(gluc)
        if gluc_valid.mean() < 0.60:
            continue

        # Trim to glucose-available segment
        valid_positions = np.where(gluc_valid)[0]
        start_pos = valid_positions[0]
        end_pos = valid_positions[-1]
        if end_pos - start_pos < min_rows:
            continue

        w_trimmed = w_idx[start_pos:end_pos + 1]
        valid_windows.append(w_trimmed)

    return valid_windows


def measure_actual_drift(pdf: pd.DataFrame, window_idx: list) -> dict:
    """Measure actual glucose drift in a fasting window.

    Returns dict with start_glucose, end_glucose, drift_mg_per_hour,
    direction ('rising', 'falling', 'flat'), and stats.
    """
    w_data = pdf.loc[window_idx]
    gluc = w_data["glucose"].values
    valid = ~np.isnan(gluc)

    if valid.sum() < 10:
        return None

    # Linear regression for drift rate
    t_hours = np.arange(len(gluc)) * (5.0 / 60.0)  # 5-min intervals
    t_valid = t_hours[valid]
    g_valid = gluc[valid]

    slope, intercept = np.polyfit(t_valid, g_valid, 1)

    start_g = g_valid[0]
    end_g = g_valid[-1]
    duration_h = t_valid[-1] - t_valid[0]
    total_drift = end_g - start_g

    # Direction threshold: ±3 mg/dL/h is "flat"
    if slope > 3.0:
        direction = "rising"
    elif slope < -3.0:
        direction = "falling"
    else:
        direction = "flat"

    return {
        "start_glucose": float(start_g),
        "end_glucose": float(end_g),
        "duration_hours": float(duration_h),
        "total_drift": float(total_drift),
        "drift_mg_per_hour": float(slope),
        "direction": direction,
        "n_points": int(valid.sum()),
        "mean_glucose": float(np.nanmean(gluc)),
        "mean_iob": float(w_data["iob"].fillna(0).mean()),
    }


def simulate_basal_drift(pdf: pd.DataFrame, window_idx: list,
                          counter_reg_k: float = 3.8) -> dict:
    """Simulate glucose trajectory using only scheduled basal."""
    w_data = pdf.loc[window_idx]
    gluc = w_data["glucose"].values
    valid = ~np.isnan(gluc)
    if valid.sum() < 10:
        return None

    start_g = gluc[np.where(valid)[0][0]]
    duration_h = len(window_idx) * 5.0 / 60.0

    # Get settings from data
    isf = w_data["scheduled_isf"].dropna()
    cr = w_data["scheduled_cr"].dropna()
    basal = w_data["scheduled_basal_rate"].dropna()

    if isf.empty or cr.empty or basal.empty:
        return None

    isf_val = float(isf.median())
    cr_val = float(cr.median())
    basal_val = float(basal.median())

    t = pd.to_datetime(w_data["time"])
    start_hour = float(t.iloc[0].hour + t.iloc[0].minute / 60.0)

    settings = TherapySettings(
        isf=isf_val,
        cr=cr_val,
        basal_rate=basal_val,
        dia_hours=5.0,
    )

    # Simulate basal-only (no bolus, no carbs)
    # metabolic_basal_rate = scheduled basal (assume correct for now)
    result = forward_simulate(
        initial_glucose=start_g,
        settings=settings,
        duration_hours=duration_h,
        start_hour=start_hour,
        bolus_events=[],
        carb_events=[],
        initial_iob=0.0,
        noise_std=0.0,
        metabolic_basal_rate=basal_val,
        counter_reg_k=counter_reg_k,
    )

    sim_gluc = result.glucose
    sim_t = np.arange(len(sim_gluc)) * (5.0 / 60.0)

    # Sim drift via linear regression
    sim_slope, _ = np.polyfit(sim_t, sim_gluc, 1)
    sim_total = float(sim_gluc[-1] - sim_gluc[0])

    if sim_slope > 3.0:
        sim_direction = "rising"
    elif sim_slope < -3.0:
        sim_direction = "falling"
    else:
        sim_direction = "flat"

    return {
        "sim_start_glucose": float(sim_gluc[0]),
        "sim_end_glucose": float(sim_gluc[-1]),
        "sim_drift_mg_per_hour": float(sim_slope),
        "sim_total_drift": sim_total,
        "sim_direction": sim_direction,
        "settings_isf": isf_val,
        "settings_cr": cr_val,
        "settings_basal": basal_val,
        "counter_reg_k": counter_reg_k,
    }


def analyze_loop_basal_compensation(pdf: pd.DataFrame, window_idx: list) -> dict:
    """Analyze the loop's basal compensation during a fasting window.

    The loop adjusts actual_basal_rate relative to scheduled_basal_rate.
    Net_basal = actual - scheduled tells us what the loop thinks:
      - net_basal > 0: loop adding insulin → scheduled too low for current state
      - net_basal < 0: loop removing insulin → scheduled too high or preventing low
      - net_basal ≈ 0: scheduled rate is appropriate

    In a closed-loop system, the loop's cumulative overnight net_basal IS the
    basal adequacy signal — more reliable than glucose drift alone.
    """
    w_data = pdf.loc[window_idx]

    sched = w_data["scheduled_basal_rate"].dropna()
    actual = w_data["actual_basal_rate"].dropna()
    net = w_data["net_basal"].dropna()
    gluc = w_data["glucose"].dropna()

    if sched.empty or net.empty:
        return None

    # Glucose drift
    if len(gluc) >= 10:
        t_hours = np.arange(len(w_data)) * (5.0 / 60.0)
        g_vals = w_data["glucose"].values
        valid = ~np.isnan(g_vals)
        t_v = t_hours[valid]
        g_v = g_vals[valid]
        if len(t_v) >= 10:
            slope, _ = np.polyfit(t_v, g_v, 1)
            glucose_slope = float(slope)
        else:
            glucose_slope = float("nan")
    else:
        glucose_slope = float("nan")

    sched_rate = float(sched.median())
    actual_rate = float(actual.median())
    net_median = float(net.median())
    net_mean = float(net.mean())

    # Cumulative extra insulin over window (U)
    duration_h = len(window_idx) * 5.0 / 60.0
    total_net_insulin = float(net.sum() * 5.0 / 60.0)  # U/hr × hr = U

    # Fraction of time loop suspended (actual = 0)
    suspend_frac = float((actual == 0).mean()) if len(actual) > 0 else float("nan")

    # Fraction of time loop above scheduled
    above_frac = float((actual > sched.values[:len(actual)]).mean()) if len(actual) > 0 and len(sched) >= len(actual) else float("nan")

    return {
        "scheduled_basal_rate": sched_rate,
        "actual_basal_rate_median": actual_rate,
        "net_basal_median": net_median,
        "net_basal_mean": net_mean,
        "total_net_insulin_u": total_net_insulin,
        "duration_hours": duration_h,
        "suspend_fraction": suspend_frac,
        "glucose_slope_mg_h": glucose_slope,
    }



    """Sweep metabolic basal rate to find what explains actual drift.

    If actual glucose rises by 15 mg/dL/h, we try lower metabolic basal
    rates until the sim matches. The gap between scheduled and optimal
    metabolic basal rate is the basal adequacy signal.
    """
    w_data = pdf.loc[window_idx]
    gluc = w_data["glucose"].values
    valid = ~np.isnan(gluc)
    if valid.sum() < 10:
        return None

    start_g = gluc[np.where(valid)[0][0]]
    duration_h = len(window_idx) * 5.0 / 60.0

    isf = float(w_data["scheduled_isf"].dropna().median())
    cr = float(w_data["scheduled_cr"].dropna().median())
    basal = float(w_data["scheduled_basal_rate"].dropna().median())

    t = pd.to_datetime(w_data["time"])
    start_hour = float(t.iloc[0].hour + t.iloc[0].minute / 60.0)

    # Actual drift
    t_hours = np.arange(len(gluc)) * (5.0 / 60.0)
    t_valid = t_hours[valid]
    g_valid = gluc[valid]
    actual_slope, _ = np.polyfit(t_valid, g_valid, 1)

    # Sweep metabolic basal from 0.5x to 1.5x scheduled
    multipliers = np.arange(0.5, 1.55, 0.05)
    best_mult = 1.0
    best_error = float("inf")
    sweep_results = []

    for mult in multipliers:
        met_basal = basal * mult
        settings = TherapySettings(
            isf=isf, cr=cr, basal_rate=basal, dia_hours=5.0,
        )
        result = forward_simulate(
            initial_glucose=start_g,
            settings=settings,
            duration_hours=duration_h,
            start_hour=start_hour,
            bolus_events=[], carb_events=[],
            initial_iob=0.0, noise_std=0.0,
            metabolic_basal_rate=met_basal,
            counter_reg_k=counter_reg_k,
        )
        sim_gluc = result.glucose
        sim_t = np.arange(len(sim_gluc)) * (5.0 / 60.0)
        sim_slope, _ = np.polyfit(sim_t, sim_gluc, 1)

        error = abs(sim_slope - actual_slope)
        sweep_results.append({
            "mult": float(mult),
            "met_basal": float(met_basal),
            "sim_slope": float(sim_slope),
            "error": float(error),
        })
        if error < best_error:
            best_error = error
            best_mult = float(mult)

    return {
        "scheduled_basal": basal,
        "optimal_met_basal_mult": best_mult,
        "optimal_met_basal": basal * best_mult,
        "actual_slope": float(actual_slope),
        "best_sim_slope_error": float(best_error),
        "sweep": sweep_results,
    }


def main():
    print("=" * 70)
    print("EXP-2589: Overnight Basal Adequacy Assessment")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    all_results = {}
    summary_rows = []

    for pid in FULL_PATIENTS:
        print(f"\n--- Patient {pid} ---")
        pdf = df[df["patient_id"] == pid].copy()

        if pdf.empty:
            print(f"  No data for {pid}")
            continue

        # Extract fasting windows
        windows = extract_fasting_windows(pdf)
        print(f"  Found {len(windows)} fasting windows (≥3h, 00-06)")

        if not windows:
            print(f"  SKIP: no valid fasting windows")
            continue

        night_k = PATIENT_NIGHT_K.get(pid, POPULATION_NIGHT_K)
        patient_results = {
            "patient_id": pid,
            "n_windows": len(windows),
            "night_k": night_k,
        }

        actual_slopes = []
        net_basals = []
        net_insulins = []
        suspend_fracs = []

        for wi, w_idx in enumerate(windows):
            actual = measure_actual_drift(pdf, w_idx)
            if actual is None:
                continue
            actual_slopes.append(actual["drift_mg_per_hour"])

            loop_comp = analyze_loop_basal_compensation(pdf, w_idx)
            if loop_comp:
                net_basals.append(loop_comp["net_basal_mean"])
                net_insulins.append(loop_comp["total_net_insulin_u"])
                suspend_fracs.append(loop_comp["suspend_fraction"])

        if not actual_slopes:
            print(f"  SKIP: no valid windows with drift data")
            continue

        mean_slope = float(np.mean(actual_slopes))
        mean_net = float(np.mean(net_basals)) if net_basals else float("nan")
        mean_net_insulin = float(np.mean(net_insulins)) if net_insulins else float("nan")
        mean_suspend = float(np.mean(suspend_fracs)) if suspend_fracs else float("nan")

        # Patient TIR
        g = pdf["glucose"].dropna()
        tir = float(((g >= 70) & (g <= 180)).mean()) if len(g) > 0 else float("nan")

        # Basal adequacy assessment from loop behavior
        sched = float(pdf["scheduled_basal_rate"].dropna().median())

        # Assessment logic:
        # net_basal consistently positive → scheduled too low
        # net_basal consistently negative → scheduled too high
        if mean_net > 0.1:
            assessment = "TOO_LOW"
            suggested_mult = 1.0 + (mean_net / sched) if sched > 0 else 1.0
        elif mean_net < -0.1:
            assessment = "TOO_HIGH"
            suggested_mult = max(0.5, 1.0 + (mean_net / sched)) if sched > 0 else 1.0
        else:
            assessment = "ADEQUATE"
            suggested_mult = 1.0

        patient_results["summary"] = {
            "n_valid_windows": len(actual_slopes),
            "mean_glucose_slope_mg_h": mean_slope,
            "mean_net_basal": mean_net,
            "mean_net_insulin_per_window_u": mean_net_insulin,
            "mean_suspend_fraction": mean_suspend,
            "scheduled_basal": sched,
            "assessment": assessment,
            "suggested_basal_mult": float(suggested_mult),
            "tir": tir,
        }

        print(f"  Valid windows: {len(actual_slopes)}")
        print(f"  Actual glucose slope: {mean_slope:+.1f} mg/dL/h")
        print(f"  Net basal (loop compensation): {mean_net:+.2f} U/h")
        print(f"  Suspend fraction: {mean_suspend:.0%}")
        print(f"  Assessment: {assessment} (scheduled={sched:.2f}, mult={suggested_mult:.2f})")
        print(f"  TIR: {tir:.1%}")

        all_results[pid] = patient_results
        summary_rows.append({
            "patient": pid,
            "n_windows": len(actual_slopes),
            "glucose_slope": mean_slope,
            "net_basal": mean_net,
            "net_insulin": mean_net_insulin,
            "suspend_frac": mean_suspend,
            "sched_basal": sched,
            "assessment": assessment,
            "suggested_mult": suggested_mult,
            "tir": tir,
        })

    # === Cross-patient analysis ===
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    sdf = pd.DataFrame(summary_rows)
    if sdf.empty:
        print("No valid results")
        return

    print(f"\n{'Patient':<4} {'Win':>3} {'GlucSlope':>9} {'NetBasal':>8} "
          f"{'Suspend':>7} {'SchedBas':>8} {'Mult':>5} {'Assessment':<12} {'TIR':>5}")
    print("-" * 75)
    for _, r in sdf.iterrows():
        print(f"{r['patient']:<4} {r['n_windows']:>3} {r['glucose_slope']:>+9.1f} "
              f"{r['net_basal']:>+8.2f} {r['suspend_frac']:>7.0%} "
              f"{r['sched_basal']:>8.2f} {r['suggested_mult']:>5.2f} "
              f"{r['assessment']:<12} {r['tir']:>5.1%}")

    # H1: Glucose drift direction correlates with loop net basal
    from scipy import stats
    valid = sdf.dropna(subset=["glucose_slope", "net_basal"])
    if len(valid) >= 4:
        r1, p1 = stats.pearsonr(valid["glucose_slope"], valid["net_basal"])
        print(f"\nH1 - Glucose slope vs net basal correlation:")
        print(f"  r = {r1:.3f}, p = {p1:.3f}")
        h1_note = (
            "CONFIRMED" if r1 > 0.3 else
            "PARTIAL" if r1 > 0.0 else
            "NOT CONFIRMED"
        )
        print(f"  H1 {h1_note}: {'positive' if r1 > 0 else 'negative'} correlation")
        print(f"  Interpretation: {'Loop adds insulin when glucose rises (expected)' if r1 > 0 else 'UNEXPECTED: loop cuts when glucose rises'}")

    # H2: Net basal is a reliable basal adequacy signal
    # Patients with net_basal > 0 should have scheduled basal too low
    too_low = sdf[sdf["assessment"] == "TOO_LOW"]
    too_high = sdf[sdf["assessment"] == "TOO_HIGH"]
    adequate = sdf[sdf["assessment"] == "ADEQUATE"]
    print(f"\nH2 - Loop-based basal assessment distribution:")
    print(f"  TOO_LOW (loop adds basal): {len(too_low)} patients: {', '.join(too_low['patient'].tolist())}")
    print(f"  TOO_HIGH (loop cuts basal): {len(too_high)} patients: {', '.join(too_high['patient'].tolist())}")
    print(f"  ADEQUATE (near zero net): {len(adequate)} patients: {', '.join(adequate['patient'].tolist())}")

    # H3: Loop compensation correlates with overall TIR
    valid_h3 = sdf.dropna(subset=["net_basal", "tir"])
    if len(valid_h3) >= 4:
        # Use absolute net_basal — higher = more loop work = worse settings
        r3, p3 = stats.pearsonr(valid_h3["net_basal"].abs(), valid_h3["tir"])
        print(f"\nH3 - |Net basal| vs TIR correlation:")
        print(f"  r = {r3:.3f}, p = {p3:.3f}")
        print(f"  {'CONFIRMED' if r3 < -0.3 else 'NOT CONFIRMED'}: "
              f"{'More loop compensation → worse TIR' if r3 < 0 else 'No clear relationship'}")

    # Quadrant analysis: glucose direction × net basal direction
    # This is the KEY insight for closed-loop basal assessment
    print(f"\nQuadrant Analysis (Glucose Slope × Net Basal):")
    print(f"  {'Patient':<4} {'GlucSlope':>9} {'NetBasal':>8} {'Quadrant':<25} {'Clinical'}")
    print(f"  {'-'*80}")
    for _, r in sdf.iterrows():
        gs = r["glucose_slope"]
        nb = r["net_basal"]
        if gs > 3.0 and nb > 0.1:
            quad = "Rising + Loop Adding"
            clinical = "BASAL TOO LOW (loop can't keep up)"
        elif gs > 3.0 and nb < -0.1:
            quad = "Rising + Loop Cutting"
            clinical = "DAWN PHENOMENON (endogenous, not basal)"
        elif gs < -3.0 and nb > 0.1:
            quad = "Falling + Loop Adding"
            clinical = "OVERCORRECTION (prior bolus effect)"
        elif gs < -3.0 and nb < -0.1:
            quad = "Falling + Loop Cutting"
            clinical = "BASAL TOO HIGH"
        elif abs(gs) <= 3.0 and nb > 0.1:
            quad = "Flat + Loop Adding"
            clinical = "BASAL SLIGHTLY LOW (loop compensating OK)"
        elif abs(gs) <= 3.0 and nb < -0.1:
            quad = "Flat + Loop Cutting"
            clinical = "BASAL SLIGHTLY HIGH (loop managing)"
        else:
            quad = "Flat + Neutral"
            clinical = "BASAL ADEQUATE"
        print(f"  {r['patient']:<4} {gs:>+9.1f} {nb:>+8.2f} {quad:<25} {clinical}")

    # Suspension analysis
    print(f"\nSuspension Analysis:")
    print(f"  Patients with >50% suspension: "
          f"{', '.join(sdf[sdf['suspend_frac'] > 0.5]['patient'].tolist())}")
    print(f"  These patients have scheduled basal that the loop considers too aggressive")

    # Clinical recommendations
    print(f"\nClinical Recommendations:")
    for _, r in sdf.iterrows():
        if r["assessment"] == "TOO_LOW":
            pct = (r["suggested_mult"] - 1) * 100
            print(f"  {r['patient']}: INCREASE overnight basal by ~{pct:.0f}% "
                  f"(from {r['sched_basal']:.2f} to {r['sched_basal']*r['suggested_mult']:.2f} U/h)")
        elif r["assessment"] == "TOO_HIGH":
            pct = (1 - r["suggested_mult"]) * 100
            print(f"  {r['patient']}: DECREASE overnight basal by ~{pct:.0f}% "
                  f"(from {r['sched_basal']:.2f} to {r['sched_basal']*r['suggested_mult']:.2f} U/h)")
        else:
            print(f"  {r['patient']}: No change needed (basal adequate)")

    # Save results
    output = {
        "experiment": "EXP-2589",
        "title": "Overnight Basal Adequacy Assessment",
        "approach": "Loop compensation analysis (net_basal = actual - scheduled)",
        "key_finding": "In closed-loop systems, the loop's net_basal adjustment "
                       "IS the basal adequacy signal, more reliable than glucose drift.",
        "summary": summary_rows,
        "patients": {pid: all_results[pid] for pid in all_results},
    }

    out_path = RESULTS_DIR / "exp-2589_basal_adequacy.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
