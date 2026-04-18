#!/usr/bin/env python3
"""EXP-2616: Actual-Delivery Forward Sim — Deconfounding Loop Compensation.

DISCOVERY: The forward sim uses scheduled_basal_rate, but loops actually
deliver 65-88% LESS basal (via suspension) and compensate with SMBs.
counter_reg_k has been absorbing this insulin accounting error.

This experiment tests whether feeding ACTUAL delivered insulin into the sim
dramatically improves prediction accuracy and reduces counter_reg_k reliance.

We compute three sim variants per correction window:
  A) sim_scheduled: current approach (scheduled basal + manual bolus)
  B) sim_actual: actual_basal_rate + manual bolus + SMBs
  C) sim_actual_nok: same as B but with k=0 (no counter-reg)

H1: sim_actual has ≥20% lower MAE than sim_scheduled for SMB patients
    (b,c,d,e,g,i,k where basal adjustment > 50%).
H2: sim_actual with k=0 achieves similar MAE to sim_scheduled with
    calibrated k (within 15%), proving k was compensating for insulin error.
H3: ISF calibrated from sim_actual is closer to 1.0× (less distorted)
    than ISF from sim_scheduled (currently 0.5×).

If confirmed: Productionize actual-delivery sim as default, recalibrate ISF/CR.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2616_actual_delivery.json")

# Full telemetry patients with insulin data
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k",
                 "odc-74077367", "odc-86025410", "odc-96254963"]

# Per-patient k values from EXP-2614/calibration
PATIENT_K = {
    "a": 3.0, "b": 7.0, "c": 0.0, "d": 3.0, "e": 2.0,
    "f": 1.0, "g": 4.0, "i": 5.0, "k": 1.5,
    "odc-74077367": 2.0, "odc-86025410": 1.0, "odc-96254963": 2.0,
}

CORRECTION_WINDOW_STEPS = 24  # 2h at 5-min
ISF_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 2.5, 3.0]


def _extract_correction_windows(pdf, max_windows=40):
    """Extract correction bolus windows with actual delivery data."""
    windows = []
    bolus_mask = (pdf["bolus"] >= 0.5)
    # No carbs within window
    for idx in pdf.index[bolus_mask]:
        pos = pdf.index.get_loc(idx)
        if pos + CORRECTION_WINDOW_STEPS >= len(pdf):
            continue

        row = pdf.iloc[pos]
        pre_g = row["glucose"]
        if np.isnan(pre_g) or pre_g < 120:
            continue

        window = pdf.iloc[pos:pos + CORRECTION_WINDOW_STEPS]

        # Skip meals
        if window["carbs"].sum() > 2:
            continue

        # Check glucose coverage
        g_vals = window["glucose"].values
        valid = ~np.isnan(g_vals)
        if np.sum(valid) < CORRECTION_WINDOW_STEPS * 0.5:
            continue

        end_g = g_vals[valid][-1]
        actual_drop = end_g - pre_g

        # Collect actual delivery data in window
        actual_basal_rates = window["actual_basal_rate"].values
        scheduled_basal = float(row["scheduled_basal_rate"])
        smb_boluses = window["bolus_smb"].values
        manual_bolus = float(row["bolus"])

        # Total insulin: scheduled vs actual
        dt_h = 5.0 / 60.0  # 5 min in hours
        sched_total = scheduled_basal * CORRECTION_WINDOW_STEPS * dt_h
        actual_total = np.nansum(actual_basal_rates) * dt_h + np.nansum(smb_boluses)

        windows.append({
            "pre_g": float(pre_g),
            "end_g": float(end_g),
            "actual_drop": float(actual_drop),
            "manual_bolus": manual_bolus,
            "scheduled_basal": scheduled_basal,
            "actual_basal_rates": actual_basal_rates.tolist(),
            "smb_boluses": smb_boluses.tolist(),
            "sched_insulin_total": float(sched_total + manual_bolus),
            "actual_insulin_total": float(actual_total + manual_bolus),
            "isf": float(row["scheduled_isf"]),
            "cr": float(row["scheduled_cr"]),
            "hour": int(row["time"].hour),
        })

        if len(windows) >= max_windows:
            break

    return windows


def _sim_correction(window, isf_mult, k, use_actual_delivery=False):
    """Simulate a correction window with scheduled or actual delivery."""
    settings = TherapySettings(
        basal_rate=window["scheduled_basal"],
        isf=window["isf"] * isf_mult,
        cr=window["cr"],
    )

    bolus_events = [InsulinEvent(time_minutes=0, units=window["manual_bolus"])]

    if use_actual_delivery:
        # Add SMBs as additional bolus events
        for i, smb in enumerate(window["smb_boluses"]):
            if smb > 0 and not np.isnan(smb):
                bolus_events.append(InsulinEvent(
                    time_minutes=i * 5,
                    units=float(smb),
                    is_bolus=True,
                ))
        # Override basal with actual delivery rate (mean)
        actual_mean = np.nanmean(window["actual_basal_rates"])
        if not np.isnan(actual_mean):
            settings = TherapySettings(
                basal_rate=actual_mean,
                isf=window["isf"] * isf_mult,
                cr=window["cr"],
            )

    result = forward_simulate(
        initial_glucose=window["pre_g"],
        settings=settings,
        bolus_events=bolus_events,
        carb_events=[],
        duration_hours=2.0,
        counter_reg_k=k,
    )

    # End glucose from sim
    sim_end = result.glucose[-1] if len(result.glucose) > 0 else window["pre_g"]
    sim_drop = sim_end - window["pre_g"]
    return sim_drop, sim_end


def _calibrate_isf(windows, k, use_actual_delivery=False):
    """Find best ISF multiplier for given windows and delivery mode."""
    best_isf = 1.0
    best_mae = float("inf")

    for isf_mult in ISF_GRID:
        errors = []
        for w in windows:
            sim_drop, _ = _sim_correction(w, isf_mult, k, use_actual_delivery)
            errors.append(abs(sim_drop - w["actual_drop"]))
        mae = np.mean(errors)
        if mae < best_mae:
            best_mae = mae
            best_isf = isf_mult

    return best_isf, best_mae


def main():
    print("=" * 70)
    print("EXP-2616: Actual-Delivery Forward Sim — Loop Deconfounding")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}
    smb_patients = []
    non_smb_patients = []

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        # Classify controller type
        smb_total = pdf["bolus_smb"].sum()
        basal_adj = (pdf["actual_basal_rate"].mean() - pdf["scheduled_basal_rate"].mean()) / max(pdf["scheduled_basal_rate"].mean(), 0.01)
        is_smb = abs(basal_adj) > 0.3 and smb_total > 100
        ctrl = "ODC" if pid.startswith("odc") else "NS"

        print(f"\n{'='*50}")
        print(f"PATIENT {pid} ({ctrl}, {'SMB' if is_smb else 'TempBasal'})")
        print(f"  Basal adj: {basal_adj:+.0%}, SMB total: {smb_total:.0f}U")
        print(f"{'='*50}")

        windows = _extract_correction_windows(pdf)
        if len(windows) < 5:
            print(f"  Only {len(windows)} correction windows, skipping")
            continue

        print(f"  {len(windows)} correction windows")

        # Mean insulin accounting
        sched_ins = np.mean([w["sched_insulin_total"] for w in windows])
        actual_ins = np.mean([w["actual_insulin_total"] for w in windows])
        print(f"  Mean insulin/window: scheduled={sched_ins:.2f}U, actual={actual_ins:.2f}U")

        k = PATIENT_K.get(pid, 1.5)

        # A) sim_scheduled (current approach)
        isf_sched, mae_sched = _calibrate_isf(windows, k, use_actual_delivery=False)
        print(f"  A) Scheduled: ISF×{isf_sched}, MAE={mae_sched:.1f} mg/dL (k={k})")

        # B) sim_actual (actual delivery)
        isf_actual, mae_actual = _calibrate_isf(windows, k, use_actual_delivery=True)
        print(f"  B) Actual:    ISF×{isf_actual}, MAE={mae_actual:.1f} mg/dL (k={k})")

        # C) sim_actual with k=0 (no counter-reg)
        isf_actual_nok, mae_actual_nok = _calibrate_isf(windows, k=0, use_actual_delivery=True)
        print(f"  C) Actual k=0: ISF×{isf_actual_nok}, MAE={mae_actual_nok:.1f} mg/dL")

        # D) sim_scheduled with k=0 (baseline)
        isf_sched_nok, mae_sched_nok = _calibrate_isf(windows, k=0, use_actual_delivery=False)
        print(f"  D) Sched k=0: ISF×{isf_sched_nok}, MAE={mae_sched_nok:.1f} mg/dL")

        mae_improvement = (mae_sched - mae_actual) / mae_sched * 100 if mae_sched > 0 else 0
        k_equiv = abs(mae_actual_nok - mae_sched) / max(mae_sched, 1) * 100

        print(f"  MAE improvement (A→B): {mae_improvement:+.1f}%")
        print(f"  ISF shift: {isf_sched}→{isf_actual} (actual delivery)")

        patient_result = {
            "ctrl": ctrl,
            "is_smb": is_smb,
            "basal_adj_pct": round(basal_adj * 100, 0),
            "smb_total": round(float(smb_total), 0),
            "n_windows": len(windows),
            "mean_sched_insulin": round(sched_ins, 2),
            "mean_actual_insulin": round(actual_ins, 2),
            "scheduled": {"isf_mult": isf_sched, "mae": round(mae_sched, 1)},
            "actual_with_k": {"isf_mult": isf_actual, "mae": round(mae_actual, 1)},
            "actual_no_k": {"isf_mult": isf_actual_nok, "mae": round(mae_actual_nok, 1)},
            "scheduled_no_k": {"isf_mult": isf_sched_nok, "mae": round(mae_sched_nok, 1)},
            "mae_improvement_pct": round(mae_improvement, 1),
            "k": k,
        }
        results[pid] = patient_result

        if is_smb:
            smb_patients.append(pid)
        else:
            non_smb_patients.append(pid)

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT ANALYSIS")
    print("=" * 70)

    # H1: ≥20% MAE improvement for SMB patients
    smb_improvements = [results[p]["mae_improvement_pct"] for p in smb_patients if p in results]
    h1_count = sum(1 for x in smb_improvements if x >= 20)
    h1_confirmed = h1_count >= len(smb_improvements) * 0.5 if smb_improvements else False
    print(f"\nH1 - MAE improvement ≥20% for SMB patients:")
    print(f"  Improvements: {[round(x,1) for x in smb_improvements]}")
    print(f"  {h1_count}/{len(smb_improvements)} meet threshold")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: sim_actual(k=0) ≈ sim_scheduled(k=calibrated) within 15%
    h2_pairs = []
    for pid in results:
        mae_actual_nok = results[pid]["actual_no_k"]["mae"]
        mae_sched_k = results[pid]["scheduled"]["mae"]
        if mae_sched_k > 0:
            ratio = abs(mae_actual_nok - mae_sched_k) / mae_sched_k * 100
            h2_pairs.append((pid, ratio))
    h2_within = sum(1 for _, r in h2_pairs if r <= 15)
    h2_confirmed = h2_within >= len(h2_pairs) * 0.5 if h2_pairs else False
    print(f"\nH2 - Actual(k=0) ≈ Scheduled(k=cal) within 15%:")
    for pid, r in h2_pairs:
        tag = "✓" if r <= 15 else "✗"
        print(f"  {pid:>18s}: {r:.1f}% diff {tag}")
    print(f"  {h2_within}/{len(h2_pairs)} within 15%")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: ISF from actual delivery closer to 1.0
    isf_sched_all = [results[p]["scheduled"]["isf_mult"] for p in results]
    isf_actual_all = [results[p]["actual_with_k"]["isf_mult"] for p in results]
    dist_sched = np.mean([abs(x - 1.0) for x in isf_sched_all])
    dist_actual = np.mean([abs(x - 1.0) for x in isf_actual_all])
    h3_confirmed = dist_actual < dist_sched
    print(f"\nH3 - ISF closer to 1.0× with actual delivery:")
    print(f"  Scheduled ISFs: {isf_sched_all}")
    print(f"  Actual ISFs:    {isf_actual_all}")
    print(f"  Mean dist from 1.0: scheduled={dist_sched:.2f}, actual={dist_actual:.2f}")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # Summary table
    print(f"\n{'Pt':>18s}  {'Type':>8s}  {'SchedISF':>8s}  {'ActISF':>7s}  {'MAE_S':>6s}  {'MAE_A':>6s}  {'Δ%':>6s}")
    print("-" * 72)
    for pid in sorted(results.keys()):
        r = results[pid]
        typ = "SMB" if r["is_smb"] else "TmpBas"
        print(f"{pid:>18s}  {typ:>8s}  {r['scheduled']['isf_mult']:>8.1f}  "
              f"{r['actual_with_k']['isf_mult']:>7.1f}  "
              f"{r['scheduled']['mae']:>6.1f}  {r['actual_with_k']['mae']:>6.1f}  "
              f"{r['mae_improvement_pct']:>+5.1f}%")

    output = {
        "experiment": "EXP-2616",
        "title": "Actual-Delivery Forward Sim — Loop Deconfounding",
        "patients": results,
        "smb_patients": smb_patients,
        "non_smb_patients": non_smb_patients,
        "hypotheses": {
            "H1": {"improvements": smb_improvements, "confirmed": h1_confirmed},
            "H2": {"pairs": {p: r for p, r in h2_pairs}, "confirmed": h2_confirmed},
            "H3": {"dist_sched": round(dist_sched, 3), "dist_actual": round(dist_actual, 3),
                    "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
