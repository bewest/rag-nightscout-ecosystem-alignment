#!/usr/bin/env python3
"""
EXP-2583: Counter-Regulated Sim Meal Trajectory Validation

HYPOTHESIS: The counter-regulated forward sim (calibrated k per patient
from EXP-2582) produces realistic post-meal glucose trajectories, not
just corrections. Since counter-reg only opposes drops (glucagon-only),
it should:
  - Not affect the initial post-meal rise (dBG > 0)
  - Reduce the predicted post-peak drop (dBG < 0)
  - Produce a shallower, more realistic return toward baseline

DESIGN:
  For each patient:
    1. Extract 50 meal events (carbs>10g, bolus>0.1U)
    2. Run sim with: (a) k=0 (baseline), (b) k=1.5 (population),
       (c) per-patient optimal k from EXP-2582
    3. Compare 4h trajectories: peak glucose, time-to-peak, nadir,
       time-in-range, final glucose
    4. Compute MAE at 1h, 2h, 3h, 4h for each k variant

SUCCESS: Per-patient k reduces MAE by ≥10% vs k=0 for meals
"""

import json
import time
import numpy as np
from pathlib import Path

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

# Per-patient optimal k from EXP-2582
PATIENT_K = {
    'a': 2.0, 'b': 3.0, 'c': 7.0, 'd': 1.5, 'e': 1.5,
    'f': 1.0, 'g': 1.0, 'h': 0.0, 'i': 3.0, 'j': 0.0, 'k': 0.0,
}
POPULATION_K = 1.5
HORIZONS = [12, 24, 36, 48]  # steps: 1h, 2h, 3h, 4h


def extract_meal_windows(df, patient_id, max_n=60):
    """Extract meal events with 4h actual glucose trajectory."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)
    idxs = pdf.index[mask]

    meals = []
    for idx in idxs:
        if len(meals) >= max_n:
            break
        pos = pdf.index.get_loc(idx)
        if pos + 49 >= len(pdf):
            continue
        window = pdf.iloc[pos:pos + 49]
        glucose_traj = window['glucose'].values
        if np.isnan(glucose_traj[:25]).sum() > 5:
            continue

        row = pdf.iloc[pos]
        isf = row.get('scheduled_isf', 50)
        meals.append({
            'glucose_start': float(row['glucose']),
            'bolus': float(row['bolus']),
            'carbs': float(row['carbs']),
            'iob_start': float(row.get('iob', 0)),
            'isf': float(isf) if not pd.isna(isf) else 50.0,
            'cr': float(row.get('scheduled_cr', 10)) if not pd.isna(row.get('scheduled_cr', 10)) else 10.0,
            'basal': float(row.get('scheduled_basal_rate', 1.0)) if not pd.isna(row.get('scheduled_basal_rate', 1.0)) else 1.0,
            'hour': float(row.get('hour', 12)),
            'actual_traj': [float(x) if not pd.isna(x) else np.nan for x in glucose_traj],
        })
    return meals


def evaluate_meals(meals, k_value):
    """Evaluate sim with given k across meal events."""
    horizon_maes = {h: [] for h in HORIZONS}
    peaks_actual = []
    peaks_sim = []
    tir_actual = []
    tir_sim = []

    for meal in meals:
        settings = TherapySettings(
            isf=meal['isf'], cr=meal['cr'],
            basal_rate=meal['basal'], dia_hours=5.0
        )
        result = forward_simulate(
            initial_glucose=meal['glucose_start'],
            settings=settings,
            duration_hours=4.0,
            start_hour=meal['hour'],
            bolus_events=[InsulinEvent(0.0, meal['bolus'])],
            carb_events=[CarbEvent(0.0, meal['carbs'])],
            initial_iob=meal['iob_start'],
            counter_reg_k=k_value,
        )

        sim_gluc = result.glucose
        actual_traj = np.array(meal['actual_traj'])

        # Horizons
        for h in HORIZONS:
            if h < len(actual_traj) and not np.isnan(actual_traj[h]):
                if h < len(sim_gluc):
                    horizon_maes[h].append(abs(actual_traj[h] - sim_gluc[h]))

        # Peak and TIR (over 4h window or available data)
        n = min(len(actual_traj), len(sim_gluc), 49)
        valid_mask = ~np.isnan(actual_traj[:n])
        if valid_mask.sum() > 10:
            actual_valid = actual_traj[:n][valid_mask]
            sim_valid = sim_gluc[:n][valid_mask]

            peaks_actual.append(float(np.max(actual_valid)))
            peaks_sim.append(float(np.max(sim_valid)))

            tir_actual.append(float(np.mean((actual_valid >= 70) & (actual_valid <= 180))))
            tir_sim.append(float(np.mean((sim_valid >= 70) & (sim_valid <= 180))))

    results = {
        'n_meals': len(meals),
    }
    for h in HORIZONS:
        h_min = h * 5
        if horizon_maes[h]:
            results[f'mae_{h_min}min'] = float(np.mean(horizon_maes[h]))
            results[f'n_{h_min}min'] = len(horizon_maes[h])

    if peaks_actual:
        results['peak_actual_mean'] = float(np.mean(peaks_actual))
        results['peak_sim_mean'] = float(np.mean(peaks_sim))
        results['peak_error'] = float(np.mean(np.abs(np.array(peaks_sim) - np.array(peaks_actual))))
        results['tir_actual_mean'] = float(np.mean(tir_actual))
        results['tir_sim_mean'] = float(np.mean(tir_sim))
        results['tir_error'] = float(np.mean(np.abs(np.array(tir_sim) - np.array(tir_actual))))

    return results


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2583: Counter-Regulated Sim Meal Trajectory Validation")
    print("=" * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    all_results = {}
    print(f"\n{'Patient':>8} | {'k':>4} | {'MAE@1h':>7} {'MAE@2h':>7} {'MAE@3h':>7} {'MAE@4h':>7} | "
          f"{'Peak err':>9} {'TIR err':>8}")
    print("-" * 80)

    for pid in NS_PATIENTS:
        meals = extract_meal_windows(df, pid)
        if len(meals) < 5:
            continue

        patient_k = PATIENT_K.get(pid, POPULATION_K)
        k_variants = {'k0': 0.0, 'kpop': POPULATION_K, 'kopt': patient_k}

        patient_results = {'n_meals': len(meals), 'patient_k': patient_k}

        for label, k in k_variants.items():
            res = evaluate_meals(meals, k)
            patient_results[label] = res

            if label in ('k0', 'kopt'):
                m1 = res.get('mae_60min', -1)
                m2 = res.get('mae_120min', -1)
                m3 = res.get('mae_180min', -1)
                m4 = res.get('mae_240min', -1)
                pe = res.get('peak_error', -1)
                te = res.get('tir_error', -1)
                print(f"{pid:>8} | {k:4.1f} | {m1:7.1f} {m2:7.1f} {m3:7.1f} {m4:7.1f} | "
                      f"{pe:9.1f} {te:8.3f}")

        all_results[pid] = patient_results

    # Population summary
    print("\n" + "=" * 70)
    print("POPULATION SUMMARY")
    print("=" * 70)

    for label, desc in [('k0', 'No counter-reg (k=0)'),
                        ('kpop', f'Population (k={POPULATION_K})'),
                        ('kopt', 'Per-patient optimal k')]:
        maes = {h: [] for h in HORIZONS}
        peak_errs = []
        tir_errs = []

        for pid in all_results:
            r = all_results[pid].get(label, {})
            for h in HORIZONS:
                v = r.get(f'mae_{h*5}min')
                if v is not None:
                    maes[h].append(v)
            if 'peak_error' in r:
                peak_errs.append(r['peak_error'])
            if 'tir_error' in r:
                tir_errs.append(r['tir_error'])

        print(f"\n  {desc}:")
        for h in HORIZONS:
            if maes[h]:
                print(f"    MAE@{h*5}min: {np.mean(maes[h]):.1f} mg/dL")
        if peak_errs:
            print(f"    Peak error: {np.mean(peak_errs):.1f} mg/dL")
        if tir_errs:
            print(f"    TIR error: {np.mean(tir_errs):.3f}")

    # Improvement calculation
    k0_maes_2h = [all_results[p]['k0']['mae_120min'] for p in all_results
                  if 'mae_120min' in all_results[p].get('k0', {})]
    kopt_maes_2h = [all_results[p]['kopt']['mae_120min'] for p in all_results
                    if 'mae_120min' in all_results[p].get('kopt', {})]

    if k0_maes_2h and kopt_maes_2h:
        improvement = (1 - np.mean(kopt_maes_2h) / np.mean(k0_maes_2h)) * 100

        print(f"\n{'=' * 70}")
        print(f"CONCLUSION")
        print(f"{'=' * 70}")
        print(f"Mean MAE@2h: k=0: {np.mean(k0_maes_2h):.1f}, "
              f"per-patient: {np.mean(kopt_maes_2h):.1f}")
        print(f"Improvement: {improvement:.1f}%")

        if improvement >= 10:
            verdict = "CONFIRMED"
            print(f"\n✓ CONFIRMED: Counter-reg improves meal prediction by ≥10%")
        elif improvement > 0:
            verdict = "MARGINAL"
            print(f"\n~ MARGINAL: Some improvement but <10%")
        else:
            verdict = "NOT CONFIRMED"
            print(f"\n✗ NOT CONFIRMED: Counter-reg doesn't improve meal predictions")
    else:
        verdict = "INSUFFICIENT DATA"

    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.0f}s")

    output = {
        'experiment': 'EXP-2583',
        'title': 'Counter-regulated sim meal trajectory validation',
        'verdict': verdict,
        'patient_k': PATIENT_K,
        'population_k': POPULATION_K,
        'results': all_results,
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2583_meal_validation.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
