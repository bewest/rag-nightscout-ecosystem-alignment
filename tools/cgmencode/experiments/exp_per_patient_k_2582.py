#!/usr/bin/env python3
"""
EXP-2582: Per-Patient Counter-Regulation Calibration

HYPOTHESIS: Per-patient counter_reg_k calibration will significantly improve
the 4/11 in-range rate (EXP-2581). Patients with anomalous corrections
(e.g., patient c where glucose RISES after corrections) may need very
different k values or have distinct physiological characteristics.

DESIGN:
  For each patient with ≥15 corrections:
    1. Find optimal k that minimizes |ratio@2h - 1.0|
    2. Find optimal k that minimizes MAE@2h
    3. Characterize: what patient features predict optimal k?
       - Mean glucose, TIR, hypo%, bolus size, ISF, correction frequency

  Then test: does per-patient k improve population metrics?
  Compare: population k=1.5 vs per-patient optimal k

PATIENT ANOMALIES TO INVESTIGATE:
  - Patient c: ratio is NEGATIVE (glucose rises after corrections)
  - Patient h: ratio 1.9 (counter-reg too strong with population k)
  - Patients j,k: too few events (n=8), high noise
"""

import json
import time
import numpy as np
from pathlib import Path

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

K_FINE_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 20.0]


def extract_corrections(df, patient_id, max_n=80):
    """Extract pure correction boluses for a single patient."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (
        (pdf['bolus'] > 0.5) &
        (pdf['glucose'] > 150) &
        (pdf['carbs'].fillna(0) < 1)
    )
    carb_near = pdf['carbs'].fillna(0).rolling(13, center=True, min_periods=1).sum()
    mask = mask & (carb_near < 5)

    corrections = []
    for idx in pdf.index[mask]:
        if len(corrections) >= max_n:
            break
        pos = pdf.index.get_loc(idx)
        if pos + 25 >= len(pdf):
            continue
        glucose_after = pdf.iloc[pos:pos + 25]['glucose'].values
        if np.isnan(glucose_after[:13]).sum() > 3:
            continue

        row = pdf.iloc[pos]
        isf = row.get('scheduled_isf', 50)
        corrections.append({
            'bolus': float(row['bolus']),
            'glucose_start': float(row['glucose']),
            'iob_start': float(row.get('iob', 0)),
            'isf': float(isf) if not pd.isna(isf) else 50.0,
            'cr': float(row.get('scheduled_cr', 10)) if not pd.isna(row.get('scheduled_cr', 10)) else 10.0,
            'basal': float(row.get('scheduled_basal_rate', 1.0)) if not pd.isna(row.get('scheduled_basal_rate', 1.0)) else 1.0,
            'glucose_trajectory': [float(x) if not pd.isna(x) else np.nan for x in glucose_after],
            'hour': float(row.get('hour', 12)),
            # Extra features for profiling
            'actual_delta_2h': float(glucose_after[24] - row['glucose']) if len(glucose_after) > 24 and not np.isnan(glucose_after[24]) else np.nan,
        })
    return corrections


def evaluate_k_for_patient(corrections, k_value):
    """Run sim with k for a patient's corrections, return metrics."""
    ratios_2h = []
    maes_2h = []
    sim_deltas = []
    actual_deltas = []

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
        # 2h horizon (step 24)
        if len(corr['glucose_trajectory']) > 24:
            actual_val = corr['glucose_trajectory'][24]
            if not np.isnan(actual_val):
                actual_d = actual_val - corr['glucose_start']
                sim_d = result.glucose[24] - corr['glucose_start']
                actual_deltas.append(actual_d)
                sim_deltas.append(sim_d)
                if abs(sim_d) > 1:
                    ratios_2h.append(actual_d / sim_d)
                maes_2h.append(abs(actual_d - sim_d))

    if not ratios_2h:
        return None

    return {
        'ratio_mean': float(np.mean(ratios_2h)),
        'ratio_median': float(np.median(ratios_2h)),
        'mae': float(np.mean(maes_2h)),
        'n': len(ratios_2h),
        'mean_actual_delta': float(np.mean(actual_deltas)),
        'mean_sim_delta': float(np.mean(sim_deltas)),
    }


def get_patient_profile(df, pid):
    """Extract patient characteristics for profiling."""
    pdf = df[df['patient_id'] == pid]
    glucose = pdf['glucose'].dropna()
    return {
        'mean_glucose': float(glucose.mean()),
        'std_glucose': float(glucose.std()),
        'tir': float(((glucose >= 70) & (glucose <= 180)).mean()),
        'hypo_pct': float((glucose < 70).mean()),
        'hyper_pct': float((glucose > 180).mean()),
        'mean_isf': float(pdf['scheduled_isf'].median()),
        'mean_cr': float(pdf['scheduled_cr'].median()),
        'mean_basal': float(pdf['scheduled_basal_rate'].median()),
        'total_rows': len(pdf),
        'mean_bolus': float(pdf['bolus'][pdf['bolus'] > 0.1].mean()) if (pdf['bolus'] > 0.1).any() else 0,
        'mean_iob': float(pdf['iob'].mean()),
    }


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2582: Per-Patient Counter-Regulation Calibration")
    print("=" * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    results = {}
    for pid in NS_PATIENTS:
        corrections = extract_corrections(df, pid)
        if len(corrections) < 8:
            print(f"\n  {pid}: {len(corrections)} corrections (too few, skip calibration)")
            continue

        profile = get_patient_profile(df, pid)

        # Sweep k
        k_results = {}
        for k in K_FINE_GRID:
            res = evaluate_k_for_patient(corrections, k)
            if res:
                k_results[k] = res

        # Find optimal k by ratio
        best_k_ratio = min(k_results, key=lambda k: abs(k_results[k]['ratio_mean'] - 1.0))
        best_k_mae = min(k_results, key=lambda k: k_results[k]['mae'])

        # Population k=1.5 result
        pop_result = k_results.get(1.5, k_results.get(1.0))

        results[pid] = {
            'n_corrections': len(corrections),
            'profile': profile,
            'k_sweep': {str(k): v for k, v in k_results.items()},
            'best_k_ratio': best_k_ratio,
            'best_k_mae': best_k_mae,
            'best_result': k_results[best_k_ratio],
            'pop_k_result': pop_result,
        }

        br = k_results[best_k_ratio]
        pr = pop_result or {'ratio_mean': -1, 'mae': -1}
        print(f"\n  {pid}: n={len(corrections)}, "
              f"pop_k=1.5 ratio={pr['ratio_mean']:.3f} MAE={pr['mae']:.1f}, "
              f"best_k={best_k_ratio:.1f} ratio={br['ratio_mean']:.3f} MAE={br['mae']:.1f}")

        # Anomaly analysis
        actual_delta = br['mean_actual_delta']
        print(f"       mean actual Δ2h={actual_delta:.1f} mg/dL, "
              f"ISF={profile['mean_isf']:.0f}, TIR={profile['tir']:.1%}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: Population vs Per-Patient k")
    print("=" * 70)
    print(f"{'Patient':>8} | {'Pop k=1.5':>12} {'Per-patient':>12} | "
          f"{'Best k':>7} {'Δ Ratio':>8} {'Δ MAE':>8}")
    print("-" * 70)

    pop_ratios = []
    per_ratios = []
    pop_maes = []
    per_maes = []
    k_values = []

    for pid in sorted(results):
        r = results[pid]
        pop_r = r['pop_k_result']['ratio_mean'] if r['pop_k_result'] else -1
        per_r = r['best_result']['ratio_mean']
        pop_m = r['pop_k_result']['mae'] if r['pop_k_result'] else -1
        per_m = r['best_result']['mae']
        best_k = r['best_k_ratio']

        pop_ratios.append(pop_r)
        per_ratios.append(per_r)
        pop_maes.append(pop_m)
        per_maes.append(per_m)
        k_values.append(best_k)

        print(f"{pid:>8} | ratio={pop_r:.3f} | ratio={per_r:.3f} | "
              f"k={best_k:5.1f} {per_r - pop_r:+8.3f} {per_m - pop_m:+8.1f}")

    print("-" * 70)
    print(f"{'Mean':>8} | ratio={np.mean(pop_ratios):.3f} | ratio={np.mean(per_ratios):.3f} | "
          f"k={np.mean(k_values):5.1f} "
          f"{np.mean(per_ratios) - np.mean(pop_ratios):+8.3f} "
          f"{np.mean(per_maes) - np.mean(pop_maes):+8.1f}")

    # Profile correlation with optimal k
    print("\n" + "-" * 70)
    print("Correlation: Patient features vs optimal k")
    print("-" * 70)

    features = ['mean_glucose', 'std_glucose', 'tir', 'hypo_pct',
                'mean_isf', 'mean_basal', 'mean_bolus', 'mean_iob']
    k_arr = np.array(k_values)
    for feat in features:
        vals = [results[pid]['profile'][feat] for pid in sorted(results)]
        if len(set(vals)) > 1:
            corr = np.corrcoef(vals, k_arr)[0, 1]
            print(f"  {feat:>15}: r = {corr:+.3f}")

    # Verdict
    pop_in_range = sum(1 for r in pop_ratios if 0.7 <= r <= 1.3)
    per_in_range = sum(1 for r in per_ratios if 0.7 <= r <= 1.3)
    n = len(pop_ratios)

    print(f"\n{'=' * 70}")
    print(f"CONCLUSION")
    print(f"{'=' * 70}")
    print(f"Pop k=1.5 in-range: {pop_in_range}/{n}")
    print(f"Per-patient k in-range: {per_in_range}/{n}")
    print(f"k range: {min(k_values):.1f} to {max(k_values):.1f}")
    print(f"Mean per-patient k: {np.mean(k_values):.1f}")

    if per_in_range > pop_in_range + 2:
        verdict = "CONFIRMED"
        print(f"\n✓ CONFIRMED: Per-patient calibration substantially improves fit")
    elif per_in_range > pop_in_range:
        verdict = "MARGINAL"
        print(f"\n~ MARGINAL: Small improvement from per-patient calibration")
    else:
        verdict = "NOT CONFIRMED"
        print(f"\n✗ NOT CONFIRMED: Per-patient calibration doesn't help")

    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.0f}s")

    output = {
        'experiment': 'EXP-2582',
        'title': 'Per-patient counter-regulation calibration',
        'verdict': verdict,
        'results': results,
        'pop_in_range': pop_in_range,
        'per_in_range': per_in_range,
        'k_values': {pid: results[pid]['best_k_ratio'] for pid in results},
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2582_per_patient_k.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
