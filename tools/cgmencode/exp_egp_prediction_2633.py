#!/usr/bin/env python3
"""EXP-2633: EGP-Aware Prediction Comparison

Uses per-patient calibrated recovery rates from EXP-2631 to test whether
EGP-awareness improves post-correction trajectory prediction.

Two models compared:
  Standard: glucose drops by bolus effect, then stays flat (no EGP model)
  EGP-Aware: glucose drops by bolus effect, then rises at calibrated recovery rate

Hypotheses:
  H1: EGP-aware prediction reduces MAE by ≥15% in the 3-6h window
  H2: EGP-aware model predicts nadir timing within ±30min (median error)
  H3: Benefit is largest for patients with highest phase 3 recovery rates
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
EXP2631 = ROOT / "externals" / "experiments" / "exp-2631_phase_resolved.json"
OUT = ROOT / "externals" / "experiments" / "exp-2633_egp_prediction.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
STEPS_PER_HOUR = 12
MAX_STEPS = 72  # 6h

# Hill parameters
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP_PER_5MIN = 1.5
BASE_EGP_PER_HR = BASE_EGP_PER_5MIN * 12  # 18


def _hill_egp(iob):
    """Hill EGP at given IOB (mg/dL/hr)."""
    if iob <= 0 or np.isnan(iob):
        return BASE_EGP_PER_HR
    suppression = iob**HILL_N / (iob**HILL_N + HILL_K**HILL_N)
    return BASE_EGP_PER_HR * (1.0 - suppression)


def _insulin_activity(t_min, dia_min=360, peak_min=75):
    """Exponential insulin model activity at time t (fraction of peak)."""
    if t_min <= 0:
        return 0.0
    tau = peak_min * (1 - peak_min / dia_min) / (1 - 2 * peak_min / dia_min)
    a = 2 * tau / dia_min
    S = 1 / (1 - a + (1 + a) * np.exp(-dia_min / tau))
    activity = (S / tau**2) * t_min * (1 - t_min / dia_min) * np.exp(-t_min / tau)
    return max(0, activity)


def _predict_standard(g0, bolus_u, isf, n_steps=MAX_STEPS):
    """Standard prediction: bolus drops glucose by ISF * dose, then flat."""
    pred = np.full(n_steps, g0)
    cumulative_effect = 0
    for s in range(1, n_steps):
        t_min = s * 5
        activity = _insulin_activity(t_min)
        cumulative_effect += activity * 5  # integrate over 5-min step
        pred[s] = g0 - bolus_u * isf * cumulative_effect
    return pred


def _predict_egp_aware(g0, bolus_u, isf, iob_series, recovery_rate, n_steps=MAX_STEPS):
    """EGP-aware: insulin drops glucose, then EGP raises it.
    
    Uses per-patient calibrated recovery_rate from EXP-2631 phase 3.
    Applies Hill suppression based on current IOB.
    """
    pred = np.full(n_steps, g0)
    cumulative_insulin = 0
    for s in range(1, n_steps):
        t_min = s * 5
        activity = _insulin_activity(t_min)
        cumulative_insulin += activity * 5

        # Insulin effect (glucose lowering)
        insulin_drop = bolus_u * isf * cumulative_insulin

        # EGP effect: use Hill suppression based on IOB
        iob_at_step = iob_series[s] if s < len(iob_series) else iob_series[-1]
        egp_rate = _hill_egp(iob_at_step)  # mg/dL/hr
        # Scale by patient's calibrated recovery vs base EGP
        if BASE_EGP_PER_HR > 0:
            patient_scale = recovery_rate / BASE_EGP_PER_HR
        else:
            patient_scale = 1.0
        adjusted_egp = egp_rate * patient_scale
        egp_cumulative = adjusted_egp * (s * 5 / 60)  # cumulative over hours

        pred[s] = g0 - insulin_drop + egp_cumulative

    return pred


def _predict_phase_model(g0, p1_slope, p2_slope, p3_slope, nadir_step, n_steps=MAX_STEPS):
    """Three-phase linear model."""
    pred = np.full(n_steps, g0)
    INSULIN_PEAK_STEP = 15
    for s in range(1, n_steps):
        hours = s * 5 / 60
        if s <= INSULIN_PEAK_STEP:
            rate = p1_slope
        elif s <= nadir_step:
            rate = p2_slope
        else:
            rate = p3_slope
        pred[s] = pred[s - 1] + rate / STEPS_PER_HOUR  # per 5-min step
    return pred


def run():
    # Load EXP-2631 results for per-patient calibration
    with open(EXP2631) as f:
        r31 = json.load(f)

    per_patient_phase = r31.get("per_patient", {})
    print("Per-patient phase 3 recovery rates from EXP-2631:")
    for pid in FULL_PATIENTS:
        p3 = per_patient_phase.get(pid, {}).get("p3_mean", np.nan)
        print(f"  {pid}: {p3:.1f} mg/dL/hr")

    # Load grid
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # Detect correction events
    events_by_patient = {}
    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        events = []
        for i in range(6, len(dp) - MAX_STEPS):
            row = dp.iloc[i]
            if pd.isna(row.get("bolus")) or row["bolus"] <= 0.5:
                continue
            if pd.isna(row.get("glucose")) or row["glucose"] < 130:
                continue
            window = dp.iloc[max(0, i - 6):min(len(dp), i + 7)]
            carb_sum = window["carbs"].fillna(0).sum() if "carbs" in window.columns else 0
            if carb_sum > 0:
                continue
            events.append(i)
        events_by_patient[pid] = events

    total = sum(len(v) for v in events_by_patient.values())
    print(f"\nTotal correction events: {total}")

    # Compare predictions
    all_results = []
    patient_results = {}

    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        events = events_by_patient.get(pid, [])
        if not events:
            continue

        p_data = per_patient_phase.get(pid, {})
        recovery_rate = p_data.get("p3_mean", 13.3)  # fallback to population mean
        p1_slope = p_data.get("p1_mean", -15.7)
        nadir_hr = p_data.get("nadir_mean_hr", 2.5)
        nadir_step = int(nadir_hr * STEPS_PER_HOUR)

        # Use patient's scheduled ISF
        isf_col = "scheduled_isf"
        if isf_col in dp.columns:
            isf = dp[isf_col].dropna().median()
            if np.isnan(isf) or isf <= 0:
                isf = 50  # fallback
        else:
            isf = 50

        p_standard_mae = {w: [] for w in ["1-2h", "2-3h", "3-4h", "4-5h", "5-6h", "3-6h"]}
        p_egp_mae = {w: [] for w in p_standard_mae}
        p_phase_mae = {w: [] for w in p_standard_mae}
        p_nadir_errors = []
        n_valid = 0

        for idx in events:
            seg = dp.iloc[idx:idx + MAX_STEPS]
            if len(seg) < MAX_STEPS * 0.7:
                continue

            glucose = seg["glucose"].values
            iob = seg["iob"].values if "iob" in seg.columns else np.full(MAX_STEPS, 2.0)
            bolus = seg.iloc[0]["bolus"] if not pd.isna(seg.iloc[0].get("bolus")) else 0
            g0 = glucose[0] if not np.isnan(glucose[0]) else 150

            # Skip if too many NaN
            valid_mask = ~np.isnan(glucose[:MAX_STEPS])
            if valid_mask.sum() < 20:
                continue

            n_valid += 1

            # Generate predictions
            std_pred = _predict_standard(g0, bolus, isf, len(glucose))
            egp_pred = _predict_egp_aware(g0, bolus, isf, iob, recovery_rate, len(glucose))
            phase_pred = _predict_phase_model(
                g0, p1_slope, (p1_slope + recovery_rate) / 2, recovery_rate,
                nadir_step, len(glucose)
            )

            # Compute MAE per window
            windows = {
                "1-2h": (12, 24),
                "2-3h": (24, 36),
                "3-4h": (36, 48),
                "4-5h": (48, 60),
                "5-6h": (60, 72),
                "3-6h": (36, 72),
            }
            for wname, (s_start, s_end) in windows.items():
                s_end = min(s_end, len(glucose))
                actual_w = glucose[s_start:s_end]
                std_w = std_pred[s_start:s_end]
                egp_w = egp_pred[s_start:s_end]
                phase_w = phase_pred[s_start:s_end]

                valid = ~np.isnan(actual_w)
                if valid.sum() < 3:
                    continue

                p_standard_mae[wname].append(float(np.mean(np.abs(actual_w[valid] - std_w[valid]))))
                p_egp_mae[wname].append(float(np.mean(np.abs(actual_w[valid] - egp_w[valid]))))
                p_phase_mae[wname].append(float(np.mean(np.abs(actual_w[valid] - phase_w[valid]))))

            # Nadir timing
            actual_nadir_idx = np.nanargmin(glucose[6:min(60, len(glucose))]) + 6
            actual_nadir_hr = actual_nadir_idx * 5 / 60
            pred_nadir_hr = nadir_hr
            p_nadir_errors.append(abs(actual_nadir_hr - pred_nadir_hr) * 60)  # in minutes

        # Per-patient summary
        p_summary = {"n_events": n_valid, "recovery_rate": recovery_rate, "isf": isf}
        for wname in p_standard_mae:
            if p_standard_mae[wname]:
                std_m = np.mean(p_standard_mae[wname])
                egp_m = np.mean(p_egp_mae[wname])
                phase_m = np.mean(p_phase_mae[wname])
                improvement = (std_m - egp_m) / std_m if std_m > 0 else 0
                p_summary[f"mae_standard_{wname}"] = float(std_m)
                p_summary[f"mae_egp_{wname}"] = float(egp_m)
                p_summary[f"mae_phase_{wname}"] = float(phase_m)
                p_summary[f"improvement_{wname}"] = float(improvement)

        if p_nadir_errors:
            p_summary["nadir_error_median_min"] = float(np.median(p_nadir_errors))
            p_summary["nadir_error_mean_min"] = float(np.mean(p_nadir_errors))

        patient_results[pid] = p_summary
        imp_36 = p_summary.get("improvement_3-6h", 0)
        print(f"  Patient {pid}: {n_valid} events, 3-6h improvement = {imp_36:.1%}")

        # Store per-event results for first patient for visualization
        if pid == FULL_PATIENTS[0]:
            for idx in events[:5]:
                seg = dp.iloc[idx:idx + MAX_STEPS]
                glucose = seg["glucose"].values[:MAX_STEPS]
                iob = seg["iob"].values[:MAX_STEPS] if "iob" in seg.columns else np.full(MAX_STEPS, 2.0)
                bolus = seg.iloc[0]["bolus"]
                g0 = glucose[0]
                if np.isnan(g0):
                    continue
                all_results.append({
                    "patient_id": pid,
                    "time": str(seg.iloc[0]["time"]),
                    "actual": [float(g) if not np.isnan(g) else None for g in glucose],
                    "standard_pred": [float(g) for g in _predict_standard(g0, bolus, isf, len(glucose))],
                    "egp_pred": [float(g) for g in _predict_egp_aware(g0, bolus, isf, iob, recovery_rate, len(glucose))],
                })

    # === Hypothesis Tests ===
    print("\n=== HYPOTHESIS TESTS ===\n")

    # H1: EGP-aware reduces MAE ≥15% in 3-6h window
    all_std = []
    all_egp = []
    for pid, ps in patient_results.items():
        if f"mae_standard_3-6h" in ps:
            all_std.append(ps["mae_standard_3-6h"])
            all_egp.append(ps["mae_egp_3-6h"])
    if all_std:
        std_mean = np.mean(all_std)
        egp_mean = np.mean(all_egp)
        h1_improvement = (std_mean - egp_mean) / std_mean if std_mean > 0 else 0
        h1_pass = h1_improvement >= 0.15
        print(f"H1: MAE improvement in 3-6h window")
        print(f"    Standard MAE = {std_mean:.1f}, EGP MAE = {egp_mean:.1f}")
        print(f"    Improvement = {h1_improvement:.1%}")
        print(f"    → {'PASS' if h1_pass else 'FAIL'}")
    else:
        h1_improvement = np.nan
        h1_pass = False
        print("H1: No data")

    # H2: Nadir timing ±30 min (median)
    all_nadir_errors = [ps.get("nadir_error_median_min", np.nan)
                        for ps in patient_results.values()
                        if not np.isnan(ps.get("nadir_error_median_min", np.nan))]
    if all_nadir_errors:
        median_nadir_err = np.median(all_nadir_errors)
        h2_pass = median_nadir_err <= 30
        print(f"\nH2: Nadir timing prediction")
        print(f"    Median error = {median_nadir_err:.0f} min (threshold ≤30)")
        print(f"    Per-patient: {[f'{e:.0f}' for e in all_nadir_errors]}")
        print(f"    → {'PASS' if h2_pass else 'FAIL'}")
    else:
        median_nadir_err = np.nan
        h2_pass = False
        print("\nH2: No nadir data")

    # H3: Benefit correlates with recovery rate
    recovery_rates = []
    improvements = []
    for pid, ps in patient_results.items():
        if "improvement_3-6h" in ps and "recovery_rate" in ps:
            recovery_rates.append(ps["recovery_rate"])
            improvements.append(ps["improvement_3-6h"])
    if len(recovery_rates) > 3:
        r_corr, p_corr = stats.pearsonr(recovery_rates, improvements)
        h3_pass = r_corr > 0.3
        print(f"\nH3: Recovery rate vs improvement correlation")
        print(f"    r = {r_corr:.3f}, p = {p_corr:.4f}")
        print(f"    → {'PASS' if h3_pass else 'FAIL'}")
    else:
        r_corr, p_corr = np.nan, np.nan
        h3_pass = False
        print(f"\nH3: Insufficient data (n={len(recovery_rates)})")

    # === Window-by-window breakdown ===
    print("\n=== MAE BY WINDOW ===")
    window_summary = {}
    for w in ["1-2h", "2-3h", "3-4h", "4-5h", "5-6h", "3-6h"]:
        stds = [ps[f"mae_standard_{w}"] for ps in patient_results.values() if f"mae_standard_{w}" in ps]
        egps = [ps[f"mae_egp_{w}"] for ps in patient_results.values() if f"mae_egp_{w}" in ps]
        if stds and egps:
            sm, em = np.mean(stds), np.mean(egps)
            imp = (sm - em) / sm if sm > 0 else 0
            window_summary[w] = {"standard": float(sm), "egp": float(em), "improvement": float(imp)}
            print(f"  {w}: Standard={sm:.1f}, EGP={em:.1f}, Δ={imp:.1%}")

    summary = {
        "experiment": "EXP-2633",
        "title": "EGP-Aware Prediction Comparison",
        "n_patients": len(patient_results),
        "total_events": sum(ps["n_events"] for ps in patient_results.values()),
        "hypotheses": {
            "H1": {
                "statement": "EGP-aware reduces 3-6h MAE by ≥15%",
                "result": "PASS" if h1_pass else "FAIL",
                "improvement_pct": float(h1_improvement * 100) if not np.isnan(h1_improvement) else None,
                "standard_mae": float(std_mean) if all_std else None,
                "egp_mae": float(egp_mean) if all_egp else None,
            },
            "H2": {
                "statement": "Nadir timing within ±30min",
                "result": "PASS" if h2_pass else "FAIL",
                "median_error_min": float(median_nadir_err) if not np.isnan(median_nadir_err) else None,
            },
            "H3": {
                "statement": "Benefit correlates with recovery rate (r>0.3)",
                "result": "PASS" if h3_pass else "FAIL",
                "r": float(r_corr) if not np.isnan(r_corr) else None,
                "p_value": float(p_corr) if not np.isnan(p_corr) else None,
            },
        },
        "window_summary": window_summary,
        "per_patient": patient_results,
        "sample_trajectories": all_results,
    }

    os.makedirs(OUT.parent, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    run()
