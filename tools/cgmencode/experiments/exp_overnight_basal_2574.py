#!/usr/bin/env python3
"""
EXP-2574: Overnight Basal Adequacy Analysis

HYPOTHESIS: The forward sim is most reliable for non-meal periods (correction
r=0.74 per EXP-2564). Overnight periods (00:00-06:00) with no carbs/boluses
should reveal whether basal rates are adequate. If overnight glucose drifts
significantly, the basal rate needs adjustment.

DESIGN:
  - Extract overnight windows (00:00-06:00) with no bolus/carbs
  - For each patient, simulate 6h at current basal (no events)
  - Compare sim trajectory to actual trajectory
  - Run basal grid search [0.5-2.0] to find rate that best matches flat glucose
  - If optimal differs from current by >20%, basal needs adjustment
  - Also detect dawn phenomenon (systematic rise after 04:00)

RESULT: (pending)
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
BASAL_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0]


def extract_overnight_windows(df, patient_id, max_windows=30):
    """Extract clean overnight windows (no bolus/carbs, 00:00-06:00)."""
    pdf = df[df['patient_id'] == patient_id].copy()
    pdf['hour'] = pdf['time'].dt.hour

    # Find midnight starts
    midnight_mask = (pdf['hour'] == 0)
    idxs = pdf.index[midnight_mask]

    windows = []
    for idx in idxs:
        pos = pdf.index.get_loc(idx)
        if pos + 72 >= len(pdf):  # 6h × 12 steps/h
            continue
        w = pdf.iloc[pos:pos + 72]

        # Skip if any bolus or carbs during window
        if w['bolus'].sum() > 0.1 or w['carbs'].fillna(0).sum() > 2:
            continue
        if w['glucose'].isna().sum() > 10:
            continue
        if w['glucose'].iloc[0] < 80 or w['glucose'].iloc[0] > 200:
            continue

        windows.append({
            'g': float(w['glucose'].iloc[0]),
            'iob': float(w['iob'].iloc[0]),
            'basal': float(w['scheduled_basal_rate'].iloc[0]),
            'isf': float(w['scheduled_isf'].iloc[0]),
            'cr': float(w['scheduled_cr'].iloc[0]),
            'actual_glucose': w['glucose'].values.tolist(),
            'hours': w['hour'].values.tolist(),
        })
        if len(windows) >= max_windows:
            break
    return windows


def evaluate_basal_mult(windows, basal_mult):
    """Evaluate how well a basal multiplier achieves flat glucose overnight."""
    total_flatness = 0
    count = 0
    for w in windows:
        try:
            s = TherapySettings(
                isf=w['isf'], cr=w['cr'],
                basal_rate=w['basal'] * basal_mult,
                dia_hours=5.0
            )
            r = forward_simulate(
                initial_glucose=w['g'], settings=s, duration_hours=6.0,
                start_hour=0,
                bolus_events=[], carb_events=[],
                initial_iob=w['iob'], noise_std=0, seed=42
            )
            # Flatness = inverse of glucose range (want smallest range)
            g_range = max(r.glucose) - min(r.glucose)
            total_flatness += g_range
            count += 1
        except Exception:
            continue
    return total_flatness / count if count > 0 else None


def detect_dawn_phenomenon(windows):
    """Detect systematic glucose rise after 04:00."""
    if len(windows) < 3:
        return None

    rises = []
    for w in windows:
        actual = np.array(w['actual_glucose'])
        valid = actual[np.isfinite(actual)]
        if len(valid) < 60:
            continue
        # Compare first 4h (0-48 steps) to last 2h (48-72 steps)
        early = valid[:48]
        late = valid[48:]
        if len(late) > 0:
            rise = float(np.mean(late) - np.mean(early))
            rises.append(rise)

    if not rises:
        return None
    mean_rise = float(np.mean(rises))
    return {
        'mean_rise_mg_dl': mean_rise,
        'n_nights': len(rises),
        'has_dawn': mean_rise > 10,
    }


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2574: Overnight Basal Adequacy Analysis')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    results = {}
    all_optima = []
    dawn_count = 0

    for pid in NS_PATIENTS:
        windows = extract_overnight_windows(df, pid)
        if len(windows) < 3:
            print(f'  {pid}: {len(windows)} overnight windows (skip)')
            continue

        # Find optimal basal multiplier (minimizes glucose range)
        best_range = float('inf')
        best_mult = 1.0
        for m in BASAL_GRID:
            g_range = evaluate_basal_mult(windows, m)
            if g_range is not None and g_range < best_range:
                best_range = g_range
                best_mult = m

        baseline_range = evaluate_basal_mult(windows, 1.0)
        dawn = detect_dawn_phenomenon(windows)

        # Actual overnight drift
        actual_drifts = []
        for w in windows:
            actual = np.array(w['actual_glucose'])
            valid = actual[np.isfinite(actual)]
            if len(valid) > 10:
                actual_drifts.append(float(valid[-1] - valid[0]))

        mean_drift = float(np.mean(actual_drifts)) if actual_drifts else 0

        adjustment = 'INCREASE' if best_mult > 1.1 else ('DECREASE' if best_mult < 0.9 else 'OK')
        dawn_flag = '(dawn)' if dawn and dawn['has_dawn'] else ''
        if dawn and dawn['has_dawn']:
            dawn_count += 1

        print(f'  {pid}: {len(windows)} nights | optimal basal×{best_mult:.1f} '
              f'({adjustment}) | drift={mean_drift:+.0f} | '
              f'range {baseline_range:.0f}→{best_range:.0f} {dawn_flag}')

        results[pid] = {
            'n_nights': len(windows),
            'optimal_basal_mult': best_mult,
            'baseline_glucose_range': baseline_range,
            'optimal_glucose_range': best_range,
            'actual_mean_drift': mean_drift,
            'adjustment': adjustment,
            'dawn_phenomenon': dawn,
        }
        all_optima.append(best_mult)

    # Summary
    print(f'\n  Population: {len(all_optima)} patients')
    if all_optima:
        print(f'  Mean optimal basal×{np.mean(all_optima):.2f}, '
              f'median×{np.median(all_optima):.2f}')
        n_adjust = sum(1 for m in all_optima if abs(m - 1.0) > 0.1)
        print(f'  Needing adjustment: {n_adjust}/{len(all_optima)}')
        print(f'  Dawn phenomenon: {dawn_count}/{len(all_optima)} patients')

        if n_adjust >= len(all_optima) * 0.5:
            verdict = 'SUPPORTED'
            print(f'  → ≥50% patients need basal adjustment')
        elif n_adjust >= 3:
            verdict = 'WEAKLY SUPPORTED'
            print(f'  → ≥3 patients need basal adjustment')
        else:
            verdict = 'NOT SUPPORTED'
            print(f'  → Most patients have adequate basals')
    else:
        verdict = 'INCONCLUSIVE'

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2574_overnight_basal.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2574',
            'hypothesis': 'Forward sim can identify basal inadequacy overnight',
            'verdict': verdict,
            'results': results,
            'population': {
                'mean_optimal_mult': float(np.mean(all_optima)) if all_optima else None,
                'n_needing_adjustment': sum(1 for m in all_optima if abs(m - 1.0) > 0.1),
                'n_dawn_phenomenon': dawn_count,
            },
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
