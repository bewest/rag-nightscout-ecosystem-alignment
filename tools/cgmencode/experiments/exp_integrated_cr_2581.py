#!/usr/bin/env python3
"""
EXP-2581: Integrated Counter-Regulation Calibration

HYPOTHESIS: The counter_reg_k parameter now integrated into forward_simulate()
can be calibrated to bring the 2h correction ratio from 0.39 to ~1.0 using
the multiplicative dampening model: dBG *= 1/(1+k) when dBG < 0.

This differs from EXP-2579 (post-hoc additive correction) because:
  - Dampening is applied INSIDE the integration loop at each step
  - The glucose trajectory self-consistently reflects the counter-regulation
  - The persistent component, IOB, and decay all interact with the dampened drops
  - Cannot overshoot (1/(1+k) is always in (0,1) for k>0)

DESIGN:
  - Sweep k over [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
  - For each k, run forward_simulate with counter_reg_k on 458 corrections
  - Measure actual/sim ratio at 30min, 1h, 2h
  - Find k that gives ratio closest to 1.0 at 2h
  - Compare MAE improvement

SUCCESS: Find k where ratio@2h ∈ [0.8, 1.2] with MAE < 65 mg/dL
"""

import json
import time
import numpy as np
from pathlib import Path

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, _STEP_MINUTES
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0]
HORIZONS = [6, 12, 24]  # steps: 30min, 1h, 2h


def extract_corrections(df, max_per_patient=50):
    """Extract pure correction boluses with outcome trajectories."""
    corrections = []
    for pid in NS_PATIENTS:
        pdf = df[df['patient_id'] == pid]
        mask = (
            (pdf['bolus'] > 0.5) &
            (pdf['glucose'] > 150) &
            (pdf['carbs'].fillna(0) < 1)
        )
        carb_near = pdf['carbs'].fillna(0).rolling(13, center=True, min_periods=1).sum()
        mask = mask & (carb_near < 5)

        idxs = pdf.index[mask]
        count = 0
        for idx in idxs:
            if count >= max_per_patient:
                break
            pos = pdf.index.get_loc(idx)
            if pos + 25 >= len(pdf):
                continue
            glucose_after = pdf.iloc[pos:pos + 25]['glucose'].values
            if np.isnan(glucose_after[:13]).sum() > 3:
                continue

            row = pdf.iloc[pos]
            isf = row.get('scheduled_isf', 50)
            cr = row.get('scheduled_cr', 10)
            basal = row.get('scheduled_basal_rate', 1.0)

            corrections.append({
                'patient_id': pid,
                'bolus': float(row['bolus']),
                'glucose_start': float(row['glucose']),
                'iob_start': float(row.get('iob', 0)),
                'isf': float(isf) if not pd.isna(isf) else 50.0,
                'cr': float(cr) if not pd.isna(cr) else 10.0,
                'basal': float(basal) if not pd.isna(basal) else 1.0,
                'glucose_trajectory': [float(x) if not pd.isna(x) else np.nan
                                       for x in glucose_after],
                'hour': float(row.get('hour', 12)),
            })
            count += 1
    return corrections


def evaluate_k(corrections, k_value):
    """Evaluate a k value using the integrated counter-regulation."""
    ratios = {h: [] for h in HORIZONS}
    maes = {h: [] for h in HORIZONS}

    for corr in corrections:
        settings = TherapySettings(
            isf=corr['isf'], cr=corr['cr'],
            basal_rate=corr['basal'], dia_hours=5.0
        )
        result = forward_simulate(
            initial_glucose=corr['glucose_start'],
            settings=settings,
            duration_hours=2.5,
            start_hour=corr['hour'],
            bolus_events=[InsulinEvent(0.0, corr['bolus'])],
            initial_iob=corr['iob_start'],
            counter_reg_k=k_value,
        )
        sim_glucose = result.glucose

        for h in HORIZONS:
            if h >= len(corr['glucose_trajectory']):
                continue
            actual_val = corr['glucose_trajectory'][h]
            if np.isnan(actual_val):
                continue

            actual_delta = actual_val - corr['glucose_start']
            sim_delta = sim_glucose[h] - corr['glucose_start']

            if abs(sim_delta) > 1:
                ratios[h].append(actual_delta / sim_delta)
            maes[h].append(abs(actual_delta - sim_delta))

    results = {}
    for h in HORIZONS:
        h_min = h * 5
        if ratios[h]:
            results[f'{h_min}min_ratio_mean'] = float(np.mean(ratios[h]))
            results[f'{h_min}min_ratio_median'] = float(np.median(ratios[h]))
            results[f'{h_min}min_mae'] = float(np.mean(maes[h]))
            results[f'{h_min}min_n'] = len(ratios[h])
    return results


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2581: Integrated Counter-Regulation Calibration")
    print("=" * 70)
    print("Model: dBG *= 1/(1+k) when dBG < 0 (inside integration loop)")

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')
    print(f"\nData: {df.shape}")

    corrections = extract_corrections(df)
    print(f"Corrections: {len(corrections)} across {len(NS_PATIENTS)} patients")

    by_patient = {}
    for c in corrections:
        by_patient.setdefault(c['patient_id'], []).append(c)

    # Sweep k
    print("\n" + "-" * 70)
    print(f"{'k':>6} | {'ratio@30m':>10} {'ratio@1h':>10} {'ratio@2h':>10} | "
          f"{'MAE@30m':>8} {'MAE@1h':>8} {'MAE@2h':>8}")
    print("-" * 70)

    all_results = []
    for k in K_GRID:
        result = evaluate_k(corrections, k)
        result['k'] = k
        all_results.append(result)

        r30 = result.get('30min_ratio_mean', -99)
        r60 = result.get('60min_ratio_mean', -99)
        r120 = result.get('120min_ratio_mean', -99)
        m30 = result.get('30min_mae', -99)
        m60 = result.get('60min_mae', -99)
        m120 = result.get('120min_mae', -99)
        print(f"{k:6.1f} | {r30:10.3f} {r60:10.3f} {r120:10.3f} | "
              f"{m30:8.1f} {m60:8.1f} {m120:8.1f}")

    # Find best k
    valid = [r for r in all_results if '120min_ratio_mean' in r]
    best_ratio = min(valid, key=lambda r: abs(r['120min_ratio_mean'] - 1.0))
    best_mae = min(valid, key=lambda r: r.get('120min_mae', 999))
    baseline = [r for r in all_results if r['k'] == 0.0][0]

    print("\n" + "=" * 70)
    print("BEST k VALUES")
    print("=" * 70)
    print(f"Best by ratio@2h: k={best_ratio['k']:.1f} "
          f"(ratio={best_ratio['120min_ratio_mean']:.3f})")
    print(f"Best by MAE@2h:   k={best_mae['k']:.1f} "
          f"(MAE={best_mae['120min_mae']:.1f})")

    # Per-patient analysis with best k
    print("\n" + "-" * 70)
    print(f"Per-patient analysis (k={best_ratio['k']:.1f})")
    print("-" * 70)

    per_patient = {}
    for pid in sorted(by_patient):
        patient_corrs = by_patient[pid]
        result = evaluate_k(patient_corrs, best_ratio['k'])
        per_patient[pid] = result
        r2h = result.get('120min_ratio_mean', -1)
        mae2h = result.get('120min_mae', -1)
        n = result.get('120min_n', 0)
        in_range = '✓' if 0.7 <= r2h <= 1.3 else '✗'
        print(f"  {pid}: ratio@2h={r2h:.3f}, MAE@2h={mae2h:.1f}, n={n} {in_range}")

    # Verdict
    br = best_ratio['120min_ratio_mean']
    bm = best_ratio['120min_mae']
    bl_r = baseline['120min_ratio_mean']
    bl_m = baseline['120min_mae']

    improvement_ratio = (1 - abs(br - 1.0) / abs(bl_r - 1.0)) * 100
    improvement_mae = (1 - bm / bl_m) * 100

    print(f"\n{'=' * 70}")
    print(f"CONCLUSION")
    print(f"{'=' * 70}")
    print(f"Baseline (k=0): ratio@2h={bl_r:.3f}, MAE@2h={bl_m:.1f}")
    print(f"Best (k={best_ratio['k']:.1f}):  ratio@2h={br:.3f}, MAE@2h={bm:.1f}")
    print(f"Ratio improvement: {improvement_ratio:.1f}%")
    print(f"MAE improvement:   {improvement_mae:.1f}%")

    n_good = sum(1 for r in per_patient.values()
                 if 0.7 <= r.get('120min_ratio_mean', -1) <= 1.3)
    print(f"Patients in [0.7, 1.3]: {n_good}/{len(per_patient)}")

    if 0.8 <= br <= 1.2 and bm < 65:
        verdict = "CONFIRMED"
        print(f"\n✓ CONFIRMED: Integrated counter-reg achieves target calibration")
    elif improvement_ratio > 50:
        verdict = "PARTIAL"
        print(f"\n~ PARTIAL: Significant improvement but outside target range")
    else:
        verdict = "NOT CONFIRMED"
        print(f"\n✗ NOT CONFIRMED")

    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.0f}s")

    output = {
        'experiment': 'EXP-2581',
        'title': 'Integrated counter-regulation calibration',
        'model': 'dBG *= 1/(1+k) when dBG < 0, inside integration loop',
        'verdict': verdict,
        'n_corrections': len(corrections),
        'k_grid': K_GRID,
        'all_results': all_results,
        'best_by_ratio': best_ratio,
        'best_by_mae': best_mae,
        'baseline': baseline,
        'improvement_ratio_pct': improvement_ratio,
        'improvement_mae_pct': improvement_mae,
        'per_patient': per_patient,
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2581_integrated_counter_reg.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
