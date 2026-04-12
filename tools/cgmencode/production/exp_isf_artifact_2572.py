#!/usr/bin/env python3
"""
EXP-2572: ISF Artifact Check — Is ISF×0.5 Real or Sim Artifact?

HYPOTHESIS: The universal ISF×0.5 finding in EXP-2568/2571 may be a
forward sim artifact. If the sim overestimates insulin effectiveness
(corrections drop glucose too much in the sim), then ISF×0.5 is just
compensating for a modeling bias, not a real clinical signal.

DESIGN:
  - Extract correction windows: bolus>0.5U, no carbs ±30min, glucose>150
  - Compare actual 2h glucose drop to sim-predicted drop at ISF×1.0
  - If sim overshoots (larger predicted drop), ISF×0.5 is compensatory
  - If sim undershoots, ISF×0.5 is genuinely needed
  - Compute ratio: actual_drop / sim_predicted_drop per patient
  - If ratio < 0.7 → sim overshoots → ISF×0.5 is artifact
  - If ratio > 1.3 → sim undershoots → ISF×0.5 is real

RESULT: (pending)
"""

import json
import time
import numpy as np
from pathlib import Path
from scipy import stats

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']


def extract_correction_windows(df, patient_id, max_windows=50):
    """Extract pure correction windows (no meals)."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (
        (pdf['bolus'] > 0.5) &
        (pdf['glucose'] > 150) &
        (pdf['carbs'].fillna(0) < 1)
    )
    # Also exclude windows where carbs appear within ±6 steps (30 min)
    carb_near = pdf['carbs'].fillna(0).rolling(13, center=True, min_periods=1).sum()
    mask = mask & (carb_near < 5)

    idxs = pdf.index[mask]
    windows = []
    for idx in idxs[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 24 >= len(pdf):  # 2 hour window
            continue
        w = pdf.iloc[pos:pos + 24]
        if w['glucose'].isna().sum() > 3:
            continue
        windows.append({
            'g': float(w['glucose'].iloc[0]),
            'b': float(w['bolus'].iloc[0]),
            'iob': float(w['iob'].iloc[0]),
            'h': float(w['time'].iloc[0].hour),
            'isf': float(w['scheduled_isf'].iloc[0]),
            'cr': float(w['scheduled_cr'].iloc[0]),
            'basal': float(w['scheduled_basal_rate'].iloc[0]),
            'actual_glucose': w['glucose'].values.tolist(),
        })
        if len(windows) >= max_windows:
            break
    return windows


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2572: ISF Artifact Check')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    results = {}
    all_ratios = []

    for pid in NS_PATIENTS:
        windows = extract_correction_windows(df, pid)
        if len(windows) < 3:
            print(f'  {pid}: {len(windows)} correction windows (skip)')
            continue

        ratios = []
        actual_drops = []
        sim_drops = []

        for w in windows:
            actual = np.array(w['actual_glucose'])
            actual_valid = actual[np.isfinite(actual)]
            if len(actual_valid) < 10:
                continue

            actual_drop = w['g'] - float(np.min(actual_valid[6:]))  # min after 30 min

            # Simulate at ISF×1.0
            try:
                s = TherapySettings(
                    isf=w['isf'], cr=w['cr'],
                    basal_rate=w['basal'], dia_hours=5.0
                )
                r = forward_simulate(
                    initial_glucose=w['g'], settings=s, duration_hours=2.0,
                    start_hour=w['h'],
                    bolus_events=[InsulinEvent(0, w['b'])],
                    carb_events=[],
                    initial_iob=w['iob'], noise_std=0, seed=42
                )
                sim_drop = w['g'] - float(np.min(r.glucose[6:]))
            except Exception:
                continue

            if sim_drop > 5 and actual_drop > 5:
                ratio = actual_drop / sim_drop
                ratios.append(ratio)
                actual_drops.append(actual_drop)
                sim_drops.append(sim_drop)

        if not ratios:
            print(f'  {pid}: no valid correction comparisons')
            continue

        mean_ratio = float(np.mean(ratios))
        mean_actual = float(np.mean(actual_drops))
        mean_sim = float(np.mean(sim_drops))
        all_ratios.extend(ratios)

        verdict = 'ARTIFACT' if mean_ratio < 0.7 else ('REAL' if mean_ratio > 1.3 else 'NEUTRAL')
        print(f'  {pid}: {len(ratios)} corrections | actual drop={mean_actual:.0f} '
              f'sim drop={mean_sim:.0f} | ratio={mean_ratio:.2f} ({verdict})')

        results[pid] = {
            'n_corrections': len(ratios),
            'mean_actual_drop': mean_actual,
            'mean_sim_drop': mean_sim,
            'mean_ratio': mean_ratio,
            'interpretation': verdict,
        }

    # Summary
    if all_ratios:
        pop_ratio = float(np.mean(all_ratios))
        print(f'\n  Population: {len(all_ratios)} total corrections')
        print(f'  Mean ratio (actual/sim drop): {pop_ratio:.2f}')
        print(f'  Median ratio: {float(np.median(all_ratios)):.2f}')

        if pop_ratio < 0.7:
            verdict = 'ARTIFACT CONFIRMED'
            print(f'  → Sim OVERSHOOTS by {(1-pop_ratio)*100:.0f}%: ISF×0.5 compensates for model bias')
        elif pop_ratio > 1.3:
            verdict = 'REAL SIGNAL'
            print(f'  → Sim UNDERSHOOTS by {(pop_ratio-1)*100:.0f}%: ISF×0.5 reflects genuine need')
        else:
            verdict = 'MIXED — sim is reasonably calibrated'
            print(f'  → Sim is approximately correct: ISF×0.5 not fully explained by bias')

        n_artifact = sum(1 for v in results.values() if v['interpretation'] == 'ARTIFACT')
        n_real = sum(1 for v in results.values() if v['interpretation'] == 'REAL')
        n_neutral = sum(1 for v in results.values() if v['interpretation'] == 'NEUTRAL')
        print(f'  Per-patient: {n_artifact} ARTIFACT, {n_real} REAL, {n_neutral} NEUTRAL')
    else:
        verdict = 'INCONCLUSIVE'

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2572_isf_artifact_check.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2572',
            'hypothesis': 'ISF×0.5 is a sim artifact from ISF overestimation',
            'verdict': verdict,
            'results': results,
            'population_ratio': float(np.mean(all_ratios)) if all_ratios else None,
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
