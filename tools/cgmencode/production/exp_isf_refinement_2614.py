#!/usr/bin/env python3
"""EXP-2614: ISF Magnitude Refinement via Finer Grid.

Problem: The current correction ISF advisory gives 25% for 7/9 NS patients
because the ISF multiplier grid (_CORR_ISF_GRID) has only 11 points from
0.5 to 2.0, and most patients land near the 1.0-1.5 range where the grid
spacing is 0.1 (10%). The 25% cap means SQS can't distinguish between
patients who need 15% ISF increase vs 35%.

H1: A finer ISF grid (0.05 step from 0.8 to 1.5) produces different
    optimal multipliers for ≥5/9 patients (vs current 1.25 for all).
H2: The finer multiplier produces smaller prediction errors (MAE) for
    at least 5/9 patients compared to the coarse grid.
H3: Finer ISF magnitudes improve SQS vs TIR correlation (r > 0.603).

Design:
- For each patient, run correction ISF calibration with both coarse and fine grids
- Compare optimal ISF multipliers and MAEs
- Compute SQS with finer magnitudes and correlate with TIR
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.settings_advisor import (
    _extract_correction_windows,
    _calibrate_counter_reg_k,
    _CORR_ISF_GRID,
)
from cgmencode.production.forward_simulator import (
    forward_simulate,
    TherapySettings,
    InsulinEvent,
)
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2614_isf_refinement.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Finer grid: 0.05 step from 0.7 to 2.0
FINE_ISF_GRID = [round(x * 0.05 + 0.7, 2) for x in range(27)]  # 0.70 to 2.00
COARSE_ISF_GRID = list(_CORR_ISF_GRID)


def _calibrate_isf_with_grid(windows, k, grid):
    """Run ISF calibration with a specific grid."""
    if not windows:
        return None, None

    best_mult = 1.0
    best_mae = float("inf")

    for isf_mult in grid:
        errors = []
        for w in windows[:50]:
            settings = TherapySettings(
                isf=w["isf"] * isf_mult,
                cr=w["cr"],
                basal_rate=w["basal"],
            )
            result = forward_simulate(
                initial_glucose=w["g"],
                settings=settings,
                bolus_events=[InsulinEvent(time_minutes=0, units=w["b"])],
                carb_events=[],
                duration_hours=2.0,
                counter_reg_k=k,
            )
            predicted_end = result.glucose[-1]
            actual_end = w["g"] + w["actual_drop"]
            errors.append(abs(predicted_end - actual_end))

        mae = np.mean(errors)
        if mae < best_mae:
            best_mae = mae
            best_mult = isf_mult

    return best_mult, best_mae


def main():
    print("=" * 70)
    print("EXP-2614: ISF Magnitude Refinement via Finer Grid")
    print("=" * 70)
    print(f"Coarse grid: {COARSE_ISF_GRID}")
    print(f"Fine grid: {FINE_ISF_GRID[:5]}...{FINE_ISF_GRID[-5:]}")

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) < 1000:
            continue

        g_mask = pdf["glucose"].notna()
        glucose = pdf.loc[g_mask, "glucose"].values
        hours = pdf.loc[g_mask, "time"].dt.hour.values
        bolus = pdf.loc[g_mask, "bolus"].values
        carbs = pdf.loc[g_mask, "carbs"].values
        iob = pdf.loc[g_mask, "iob"].values

        isf = float(pdf["scheduled_isf"].dropna().median())
        cr = float(pdf["scheduled_cr"].dropna().median())
        basal = float(pdf["scheduled_basal_rate"].dropna().median())
        profile = PatientProfile(
            isf_schedule=[{"start": "00:00:00", "value": isf}],
            cr_schedule=[{"start": "00:00:00", "value": cr}],
            basal_schedule=[{"start": "00:00:00", "value": basal}],
            target_low=70, target_high=180, dia_hours=6.0,
        )

        windows = _extract_correction_windows(
            glucose, hours, bolus, carbs, iob, profile, max_windows=100,
        )
        if len(windows) < 10:
            print(f"  {pid}: only {len(windows)} corrections, skipping")
            continue

        k = _calibrate_counter_reg_k(windows)

        # Run both grids
        coarse_mult, coarse_mae = _calibrate_isf_with_grid(windows, k, COARSE_ISF_GRID)
        fine_mult, fine_mae = _calibrate_isf_with_grid(windows, k, FINE_ISF_GRID)

        tir = float(np.mean((glucose >= 70) & (glucose <= 180)) * 100)

        # Magnitude from each
        coarse_mag = abs(coarse_mult - 1.0) * 100
        fine_mag = abs(fine_mult - 1.0) * 100

        print(f"  {pid}: coarse ISF×{coarse_mult:.1f} (MAE={coarse_mae:.1f}), "
              f"fine ISF×{fine_mult:.2f} (MAE={fine_mae:.1f}), "
              f"k={k:.1f}, TIR={tir:.1f}%")

        results[pid] = {
            "coarse_mult": round(coarse_mult, 2),
            "fine_mult": round(fine_mult, 2),
            "coarse_mae": round(coarse_mae, 1),
            "fine_mae": round(fine_mae, 1),
            "coarse_magnitude": round(coarse_mag, 0),
            "fine_magnitude": round(fine_mag, 0),
            "k": round(k, 1),
            "tir": round(tir, 1),
            "n_windows": len(windows),
            "profile_isf": isf,
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT COMPARISON")
    print("=" * 70)

    pids = list(results.keys())

    # H1: Different optimal multipliers
    h1_count = 0
    for pid in pids:
        r = results[pid]
        if abs(r["coarse_mult"] - r["fine_mult"]) >= 0.05:
            h1_count += 1
    h1_confirmed = h1_count >= 5
    print(f"\nH1 - Different multipliers (coarse vs fine): {h1_count}/{len(pids)}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H2: Fine grid lower MAE
    h2_count = sum(1 for pid in pids if results[pid]["fine_mae"] < results[pid]["coarse_mae"])
    h2_confirmed = h2_count >= 5
    print(f"\nH2 - Fine grid lower MAE: {h2_count}/{len(pids)}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H3: Finer SQS vs TIR (using magnitude as proxy)
    tirs = [results[pid]["tir"] for pid in pids]
    coarse_mags = [results[pid]["coarse_magnitude"] for pid in pids]
    fine_mags = [results[pid]["fine_magnitude"] for pid in pids]

    # SQS approximation: 100 - magnitude * 2 * 0.15 (ISF weight = 2)
    coarse_sqs = [100 - m * 2 * 0.15 for m in coarse_mags]
    fine_sqs = [100 - m * 2 * 0.15 for m in fine_mags]

    r_coarse, _ = stats.pearsonr(coarse_sqs, tirs) if len(set(coarse_sqs)) > 1 else (0, 1)
    r_fine, p_fine = stats.pearsonr(fine_sqs, tirs) if len(set(fine_sqs)) > 1 else (0, 1)

    h3_confirmed = r_fine > 0.603
    print(f"\nH3 - ISF-only SQS vs TIR:")
    print(f"  Coarse: r={r_coarse:.3f}")
    print(f"  Fine:   r={r_fine:.3f} (p={p_fine:.4f})")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.603)")

    # Summary table
    print(f"\n{'Pt':>5s}  {'Coarse':>7s}  {'Fine':>7s}  {'C_MAE':>6s}  {'F_MAE':>6s}  {'C_Mag':>6s}  {'F_Mag':>6s}  {'TIR':>5s}")
    print("-" * 60)
    for pid in sorted(pids):
        r = results[pid]
        print(f"{pid:>5s}  {r['coarse_mult']:>7.2f}  {r['fine_mult']:>7.2f}  "
              f"{r['coarse_mae']:>6.1f}  {r['fine_mae']:>6.1f}  "
              f"{r['coarse_magnitude']:>5.0f}%  {r['fine_magnitude']:>5.0f}%  "
              f"{r['tir']:>5.1f}")

    output = {
        "experiment": "EXP-2614",
        "title": "ISF Magnitude Refinement via Finer Grid",
        "coarse_grid": COARSE_ISF_GRID,
        "fine_grid": FINE_ISF_GRID,
        "patients": results,
        "hypotheses": {
            "H1": {"count": h1_count, "confirmed": h1_confirmed},
            "H2": {"count": h2_count, "confirmed": h2_confirmed},
            "H3": {"r_coarse": round(r_coarse, 3), "r_fine": round(r_fine, 3), "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
