#!/usr/bin/env python3
"""EXP-2631: Phase-Resolved Correction Dynamics

Uses EXP-2624's pooled correction events. Segments each correction trajectory
into 3 phases:
  Phase 1 (Demand):      0 → insulin peak (~1.25h) — rapid glucose drop from insulin
  Phase 2 (Suppression): peak → nadir (~1.25-3.5h) — EGP suppression lag
  Phase 3 (Recovery):    nadir → end (~3.5h+) — EGP + counter-reg dominate

Hypotheses:
  H1: Phase 3 slope ≈ base EGP rate (16-20 mg/dL/hr) across patients (CV < 30%)
  H2: Phase 2 duration inversely correlates with correction IOB (r < -0.2)
  H3: Per-patient phase calibration reduces trajectory RMSE >25% vs fixed Hill
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
EXP2624 = ROOT / "externals" / "experiments" / "exp-2624_correction_egp_recovery.json"
OUT = ROOT / "externals" / "experiments" / "exp-2631_phase_resolved.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Phase boundaries (in 5-min steps from correction bolus)
INSULIN_PEAK_STEP = 15   # 75 min = 1.25h
STEPS_PER_HOUR = 12
MAX_STEPS = 72           # 6h window

# Hill parameters (matching metabolic_engine.py)
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP_PER_5MIN = 1.5  # mg/dL per 5-min step
BASE_EGP_PER_HR = BASE_EGP_PER_5MIN * 12  # 18 mg/dL/hr


def _load_correction_events_with_grid():
    """Detect correction events directly from grid (same criteria as EXP-2624)."""
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    events = []
    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy()
        if len(dp) == 0:
            continue
        dp = dp.reset_index(drop=True)

        # Correction criteria: bolus > 0.5U, BG >= 130, no carbs within ±30min (6 steps)
        for i in range(6, len(dp) - MAX_STEPS):
            row = dp.iloc[i]
            if pd.isna(row.get("bolus")) or row["bolus"] <= 0.5:
                continue
            if pd.isna(row.get("glucose")) or row["glucose"] < 130:
                continue
            # No carbs within ±30 min
            window = dp.iloc[max(0, i - 6):min(len(dp), i + 7)]
            carb_sum = window["carbs"].fillna(0).sum() if "carbs" in window.columns else 0
            if carb_sum > 0:
                continue

            events.append({
                "patient_id": pid,
                "timestamp": str(row["time"]),
                "grid_index": i,
                "bolus_u": float(row["bolus"]),
                "pre_bg": float(row["glucose"]),
                "iob_at_bolus": float(row["iob"]) if not pd.isna(row.get("iob")) else np.nan,
            })

    print(f"Detected {len(events)} correction events from grid")
    for p in sorted(set(e["patient_id"] for e in events)):
        n = sum(1 for e in events if e["patient_id"] == p)
        print(f"  Patient {p}: {n} events")
    return events, df


def _extract_trajectory(df_patient, event_time, n_steps=MAX_STEPS):
    """Extract glucose + IOB trajectory starting at correction time."""
    t0 = pd.Timestamp(event_time)
    mask = (df_patient["time"] >= t0) & (
        df_patient["time"] < t0 + pd.Timedelta(minutes=5 * n_steps)
    )
    seg = df_patient.loc[mask].copy()
    if len(seg) < 20:
        return None
    seg["step"] = ((seg["time"] - t0).dt.total_seconds() / 300).round().astype(int)
    seg = seg.drop_duplicates("step").set_index("step").sort_index()

    # Require reasonable coverage
    expected = set(range(n_steps))
    coverage = len(expected & set(seg.index)) / n_steps
    if coverage < 0.7:
        return None
    return seg


def _find_nadir(glucose_series, min_step=6, max_step=60):
    """Find the glucose nadir between min_step and max_step."""
    valid = glucose_series.loc[
        (glucose_series.index >= min_step) & (glucose_series.index <= max_step)
    ].dropna()
    if len(valid) < 3:
        return None, None
    nadir_step = valid.idxmin()
    nadir_val = valid.loc[nadir_step]
    return int(nadir_step), float(nadir_val)


def _fit_phase_slopes(seg, nadir_step):
    """Fit linear slopes for each of the 3 phases."""
    glucose = seg["glucose"].dropna()

    # Phase 1: 0 → insulin peak (demand phase)
    p1_end = min(INSULIN_PEAK_STEP, nadir_step - 1)
    p1 = glucose.loc[(glucose.index >= 0) & (glucose.index <= p1_end)]

    # Phase 2: insulin peak → nadir (EGP suppression lag)
    p2 = glucose.loc[(glucose.index > p1_end) & (glucose.index <= nadir_step)]

    # Phase 3: nadir → end (recovery)
    p3 = glucose.loc[glucose.index > nadir_step]

    results = {}
    for name, phase_data in [("p1_demand", p1), ("p2_suppression", p2), ("p3_recovery", p3)]:
        if len(phase_data) < 3:
            results[name] = {"slope_per_hr": np.nan, "r2": np.nan, "n_points": len(phase_data)}
            continue
        x = phase_data.index.values.astype(float)
        y = phase_data.values
        slope, intercept, r, p_val, se = stats.linregress(x, y)
        slope_per_hr = slope * STEPS_PER_HOUR  # convert from per-step to per-hour
        results[name] = {
            "slope_per_hr": float(slope_per_hr),
            "r2": float(r**2),
            "n_points": len(phase_data),
            "p_value": float(p_val),
            "se_per_hr": float(se * STEPS_PER_HOUR),
        }
    return results


def _hill_egp(iob):
    """Hill equation EGP at given IOB."""
    if iob <= 0:
        return BASE_EGP_PER_HR
    suppression = iob**HILL_N / (iob**HILL_N + HILL_K**HILL_N)
    return BASE_EGP_PER_HR * (1.0 - suppression)


def _compute_trajectory_rmse(seg, nadir_step, phase_slopes):
    """Compute RMSE for fixed Hill vs phase-calibrated model."""
    glucose = seg["glucose"].dropna()
    iob_series = seg["iob"].dropna() if "iob" in seg.columns else None
    if len(glucose) < 10:
        return None, None

    g0 = glucose.iloc[0]
    steps = glucose.index.values.astype(float)

    # Fixed Hill model: predict glucose = g0 + cumulative(EGP - insulin_effect)
    hill_pred = np.full(len(steps), g0)
    phase_pred = np.full(len(steps), g0)

    for i, s in enumerate(steps):
        if i == 0:
            continue
        ds = s - steps[0]  # steps from start

        # Hill model: simple EGP accumulation (net of insulin)
        iob_at_step = float(iob_series.loc[s]) if (iob_series is not None and s in iob_series.index) else 2.0
        egp_rate = _hill_egp(iob_at_step)  # mg/dL/hr
        # Simple model: glucose change = EGP - insulin_demand
        # Use the initial slope as proxy for insulin demand rate
        hill_pred[i] = g0 + (egp_rate - abs(phase_slopes.get("p1_demand", {}).get("slope_per_hr", 30))) * ds / STEPS_PER_HOUR

        # Phase-calibrated model: use measured slopes
        if ds <= INSULIN_PEAK_STEP:
            rate = phase_slopes.get("p1_demand", {}).get("slope_per_hr", -30)
        elif ds <= nadir_step:
            rate = phase_slopes.get("p2_suppression", {}).get("slope_per_hr", -10)
        else:
            rate = phase_slopes.get("p3_recovery", {}).get("slope_per_hr", 15)
        phase_pred[i] = phase_pred[i - 1] + rate / STEPS_PER_HOUR * (steps[i] - steps[i - 1]) / STEPS_PER_HOUR
        # Simpler: just accumulate
        phase_pred[i] = g0 + rate * ds / STEPS_PER_HOUR

    actual = glucose.values
    hill_rmse = np.sqrt(np.nanmean((actual - hill_pred) ** 2))
    phase_rmse = np.sqrt(np.nanmean((actual - phase_pred) ** 2))

    return float(hill_rmse), float(phase_rmse)


def run():
    events, df = _load_correction_events_with_grid()

    all_results = []
    per_patient = {}

    for pid in FULL_PATIENTS:
        df_p = df[df["patient_id"] == pid]
        if len(df_p) == 0:
            continue

        patient_events = [e for e in events if e.get("patient_id") == pid]
        if not patient_events:
            print(f"  Patient {pid}: 0 correction events, skipping")
            continue

        patient_phase_slopes = {"p1": [], "p2": [], "p3": []}
        patient_nadirs = []
        patient_iob_at_correction = []
        patient_phase2_duration = []
        patient_rmse_hill = []
        patient_rmse_phase = []

        for ev in patient_events:
            t0 = ev.get("time") or ev.get("timestamp") or ev.get("correction_time")
            if t0 is None:
                continue

            seg = _extract_trajectory(df_p, t0)
            if seg is None:
                continue

            nadir_step, nadir_val = _find_nadir(seg["glucose"])
            if nadir_step is None or nadir_step <= INSULIN_PEAK_STEP:
                continue

            slopes = _fit_phase_slopes(seg, nadir_step)

            # IOB at correction time
            iob0 = float(seg["iob"].iloc[0]) if "iob" in seg.columns and not seg["iob"].isna().iloc[0] else np.nan

            # Phase 2 duration in hours
            p2_duration_hr = (nadir_step - INSULIN_PEAK_STEP) * 5 / 60

            # RMSE comparison
            hill_rmse, phase_rmse = _compute_trajectory_rmse(seg, nadir_step, slopes)

            event_result = {
                "patient_id": pid,
                "correction_time": str(t0),
                "nadir_step": nadir_step,
                "nadir_hours": nadir_step * 5 / 60,
                "nadir_glucose": nadir_val,
                "glucose_at_correction": float(seg["glucose"].iloc[0]) if not seg["glucose"].isna().iloc[0] else np.nan,
                "iob_at_correction": iob0,
                "phase2_duration_hr": p2_duration_hr,
                "phases": slopes,
                "hill_rmse": hill_rmse,
                "phase_rmse": phase_rmse,
            }
            all_results.append(event_result)

            if not np.isnan(slopes.get("p1_demand", {}).get("slope_per_hr", np.nan)):
                patient_phase_slopes["p1"].append(slopes["p1_demand"]["slope_per_hr"])
            if not np.isnan(slopes.get("p2_suppression", {}).get("slope_per_hr", np.nan)):
                patient_phase_slopes["p2"].append(slopes["p2_suppression"]["slope_per_hr"])
            if not np.isnan(slopes.get("p3_recovery", {}).get("slope_per_hr", np.nan)):
                patient_phase_slopes["p3"].append(slopes["p3_recovery"]["slope_per_hr"])
            patient_nadirs.append(nadir_step * 5 / 60)
            if not np.isnan(iob0):
                patient_iob_at_correction.append(iob0)
                patient_phase2_duration.append(p2_duration_hr)
            if hill_rmse is not None:
                patient_rmse_hill.append(hill_rmse)
                patient_rmse_phase.append(phase_rmse)

        per_patient[pid] = {
            "n_events": len([r for r in all_results if r["patient_id"] == pid]),
            "p3_recovery_slopes": patient_phase_slopes["p3"],
            "p3_mean": float(np.mean(patient_phase_slopes["p3"])) if patient_phase_slopes["p3"] else np.nan,
            "p3_std": float(np.std(patient_phase_slopes["p3"])) if patient_phase_slopes["p3"] else np.nan,
            "p1_mean": float(np.mean(patient_phase_slopes["p1"])) if patient_phase_slopes["p1"] else np.nan,
            "nadir_mean_hr": float(np.mean(patient_nadirs)) if patient_nadirs else np.nan,
            "hill_rmse_mean": float(np.mean(patient_rmse_hill)) if patient_rmse_hill else np.nan,
            "phase_rmse_mean": float(np.mean(patient_rmse_phase)) if patient_rmse_phase else np.nan,
        }
        n = per_patient[pid]["n_events"]
        p3m = per_patient[pid]["p3_mean"]
        print(f"  Patient {pid}: {n} events, P3 recovery slope = {p3m:.1f} mg/dL/hr")

    # === Hypothesis Tests ===
    print("\n=== HYPOTHESIS TESTS ===\n")

    # H1: Phase 3 slope ≈ base EGP (16-20 mg/dL/hr), CV < 30%
    all_p3 = [r["phases"]["p3_recovery"]["slope_per_hr"]
              for r in all_results
              if not np.isnan(r["phases"].get("p3_recovery", {}).get("slope_per_hr", np.nan))]
    p3_mean = np.mean(all_p3)
    p3_std = np.std(all_p3)
    p3_cv = p3_std / abs(p3_mean) if p3_mean != 0 else np.inf
    p3_in_range = 16 <= p3_mean <= 20
    h1_pass = p3_cv < 0.30 and p3_in_range

    # Per-patient means for inter-patient CV
    per_patient_p3_means = [v["p3_mean"] for v in per_patient.values() if not np.isnan(v.get("p3_mean", np.nan))]
    inter_cv = np.std(per_patient_p3_means) / abs(np.mean(per_patient_p3_means)) if per_patient_p3_means else np.nan

    print(f"H1: Phase 3 recovery slope")
    print(f"    Mean = {p3_mean:.1f} mg/dL/hr (expected 16-20)")
    print(f"    Intra-event CV = {p3_cv:.3f}")
    print(f"    Inter-patient CV = {inter_cv:.3f}")
    print(f"    In range: {p3_in_range}, CV<0.30: {p3_cv < 0.30}")
    print(f"    → {'PASS' if h1_pass else 'FAIL'}")

    # H2: Phase 2 duration inversely correlated with IOB (r < -0.2)
    iob_vals = [r["iob_at_correction"] for r in all_results if not np.isnan(r["iob_at_correction"])]
    p2_vals = [r["phase2_duration_hr"] for r in all_results if not np.isnan(r["iob_at_correction"])]
    if len(iob_vals) > 10:
        r_iob_p2, p_iob_p2 = stats.pearsonr(iob_vals, p2_vals)
        h2_pass = r_iob_p2 < -0.2
        print(f"\nH2: Phase 2 duration vs IOB correlation")
        print(f"    r = {r_iob_p2:.3f}, p = {p_iob_p2:.4f}")
        print(f"    → {'PASS' if h2_pass else 'FAIL'}")
    else:
        r_iob_p2, p_iob_p2 = np.nan, np.nan
        h2_pass = False
        print(f"\nH2: Insufficient data (n={len(iob_vals)})")

    # H3: Phase-calibrated RMSE < Hill RMSE by >25%
    hill_rmses = [r["hill_rmse"] for r in all_results if r["hill_rmse"] is not None]
    phase_rmses = [r["phase_rmse"] for r in all_results if r["phase_rmse"] is not None]
    if hill_rmses and phase_rmses:
        hill_mean_rmse = np.mean(hill_rmses)
        phase_mean_rmse = np.mean(phase_rmses)
        improvement = (hill_mean_rmse - phase_mean_rmse) / hill_mean_rmse
        h3_pass = improvement > 0.25
        print(f"\nH3: RMSE improvement with phase calibration")
        print(f"    Hill RMSE = {hill_mean_rmse:.1f}, Phase RMSE = {phase_mean_rmse:.1f}")
        print(f"    Improvement = {improvement:.1%}")
        print(f"    → {'PASS' if h3_pass else 'FAIL'}")
    else:
        improvement = np.nan
        h3_pass = False
        print(f"\nH3: Insufficient RMSE data")

    # === Summary ===
    summary = {
        "experiment": "EXP-2631",
        "title": "Phase-Resolved Correction Dynamics",
        "n_events": len(all_results),
        "n_patients": len(per_patient),
        "hypotheses": {
            "H1": {
                "statement": "Phase 3 slope ≈ 16-20 mg/dL/hr, CV < 30%",
                "result": "PASS" if h1_pass else "FAIL",
                "p3_mean": float(p3_mean),
                "p3_std": float(p3_std),
                "intra_cv": float(p3_cv),
                "inter_patient_cv": float(inter_cv),
                "base_egp_reference": BASE_EGP_PER_HR,
            },
            "H2": {
                "statement": "Phase 2 duration inversely correlates with IOB (r < -0.2)",
                "result": "PASS" if h2_pass else "FAIL",
                "r": float(r_iob_p2) if not np.isnan(r_iob_p2) else None,
                "p_value": float(p_iob_p2) if not np.isnan(p_iob_p2) else None,
            },
            "H3": {
                "statement": "Phase calibration reduces RMSE >25% vs fixed Hill",
                "result": "PASS" if h3_pass else "FAIL",
                "hill_rmse": float(hill_mean_rmse) if hill_rmses else None,
                "phase_rmse": float(phase_mean_rmse) if phase_rmses else None,
                "improvement_pct": float(improvement * 100) if not np.isnan(improvement) else None,
            },
        },
        "phase_summary": {
            "p1_demand": {
                "mean_slope": float(np.mean([r["phases"]["p1_demand"]["slope_per_hr"]
                    for r in all_results
                    if not np.isnan(r["phases"].get("p1_demand", {}).get("slope_per_hr", np.nan))])),
                "description": "Rapid glucose drop from insulin action",
            },
            "p2_suppression": {
                "mean_slope": float(np.mean([r["phases"]["p2_suppression"]["slope_per_hr"]
                    for r in all_results
                    if not np.isnan(r["phases"].get("p2_suppression", {}).get("slope_per_hr", np.nan))])),
                "mean_duration_hr": float(np.mean([r["phase2_duration_hr"] for r in all_results])),
                "description": "EGP suppression lag — glucose still falling but slower",
            },
            "p3_recovery": {
                "mean_slope": float(p3_mean),
                "cv": float(p3_cv),
                "description": "EGP + counter-regulation recovery phase",
            },
        },
        "per_patient": per_patient,
        "all_events": all_results,
    }

    print(f"\n=== SUMMARY ===")
    print(f"Events analyzed: {len(all_results)}")
    print(f"Phase 1 (demand): {summary['phase_summary']['p1_demand']['mean_slope']:.1f} mg/dL/hr")
    print(f"Phase 2 (suppression): {summary['phase_summary']['p2_suppression']['mean_slope']:.1f} mg/dL/hr")
    print(f"Phase 3 (recovery): {p3_mean:.1f} mg/dL/hr (base EGP = {BASE_EGP_PER_HR})")

    os.makedirs(OUT.parent, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    run()
