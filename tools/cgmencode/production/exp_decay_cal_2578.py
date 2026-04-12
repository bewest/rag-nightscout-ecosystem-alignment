#!/usr/bin/env python3
"""
EXP-2578: Counter-Regulatory Decay Calibration

HYPOTHESIS: The forward sim's mean-reversion/decay rate (0.005/step)
is far too weak. Real counter-regulatory physiology (hepatic glucose
production, glucagon) provides much stronger homeostatic buffering.
Increasing the decay_rate should reduce the 61% overestimation.

DESIGN:
  - Sweep decay_rate over [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
  - Also sweep decay_target (equilibrium glucose) over [100, 110, 120, 130]
  - For each combo, run sim on 376 pure corrections
  - Measure actual/sim ratio at 30min, 1h, 2h
  - Find (decay_rate, decay_target) that minimizes MAE at 2h

  If the optimal decay_rate is much higher than 0.005, this confirms
  the missing counter-regulation is the root cause AND provides an
  empirical fix for the forward sim.

RESULT: (pending)
"""

import json
import time
import numpy as np
from pathlib import Path

import pandas as pd

import cgmencode.production.forward_simulator as fs
import cgmencode.production.metabolic_engine as me
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

# Save originals
ORIG_DECAY_RATE = me._DECAY_RATE
ORIG_DECAY_TARGET = me._DECAY_TARGET

DECAY_RATE_GRID = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15]
DECAY_TARGET_GRID = [100, 110, 120, 130, 140]


def set_decay_params(rate, target):
    """Monkey-patch decay parameters."""
    me._DECAY_RATE = rate
    me._DECAY_TARGET = target
    fs._DECAY_RATE = rate
    fs._DECAY_TARGET = target


def restore_defaults():
    set_decay_params(ORIG_DECAY_RATE, ORIG_DECAY_TARGET)


def extract_corrections(df, max_per_patient=40):
    """Extract all corrections from NS patients."""
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
            w = pdf.iloc[pos:pos + 25]
            if w['glucose'].isna().sum() > 3:
                continue
            corrections.append({
                'g0': float(w['glucose'].iloc[0]),
                'bolus': float(w['bolus'].iloc[0]),
                'iob': float(w['iob'].iloc[0]),
                'h': float(w['time'].iloc[0].hour),
                'isf': float(w['scheduled_isf'].iloc[0]),
                'cr': float(w['scheduled_cr'].iloc[0]),
                'basal': float(w['scheduled_basal_rate'].iloc[0]),
                'actual': [float(x) for x in w['glucose'].values],
                'pid': pid,
            })
            count += 1
    return corrections


def evaluate_decay(corrections, rate, target):
    """Evaluate sim at given decay params across all corrections."""
    set_decay_params(rate, target)

    actual_2h = []
    sim_2h = []

    for c in corrections:
        try:
            s = TherapySettings(
                isf=c['isf'], cr=c['cr'],
                basal_rate=c['basal'], dia_hours=5.0
            )
            r = forward_simulate(
                initial_glucose=c['g0'], settings=s, duration_hours=2.5,
                start_hour=c['h'],
                bolus_events=[InsulinEvent(0, c['bolus'])],
                carb_events=[], initial_iob=c['iob'],
                noise_std=0, seed=42
            )
            if 24 < len(r.glucose) and 24 < len(c['actual']):
                if np.isfinite(c['actual'][24]):
                    actual_2h.append(c['actual'][24])
                    sim_2h.append(float(r.glucose[24]))
        except Exception:
            continue

    restore_defaults()

    if not actual_2h:
        return None

    actual_arr = np.array(actual_2h)
    sim_arr = np.array(sim_2h)
    mae = float(np.mean(np.abs(actual_arr - sim_arr)))
    # Ratio of glucose CHANGES (not absolute)
    actual_delta = np.array([c['g0'] for c in corrections[:len(actual_arr)]]) - actual_arr
    sim_delta = np.array([c['g0'] for c in corrections[:len(sim_arr)]]) - sim_arr
    mask = np.abs(sim_delta) > 3
    ratio = float(np.mean(actual_delta[mask]) / np.mean(sim_delta[mask])) if mask.sum() > 0 else 0
    corr = float(np.corrcoef(actual_arr, sim_arr)[0, 1]) if len(actual_arr) > 2 else 0

    return {'mae': mae, 'ratio': ratio, 'correlation': corr, 'n': len(actual_arr)}


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2578: Counter-Regulatory Decay Calibration')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')
    corrections = extract_corrections(df)
    print(f'  Total corrections: {len(corrections)}')

    # Phase 1: Sweep decay rate at default target
    print(f'\n  Phase 1: Decay rate sweep (target={ORIG_DECAY_TARGET})')
    print(f'  {"Rate":>8s} | {"MAE":>7s} | {"Ratio":>7s} | {"r":>7s}')
    print(f'  {"-"*8} | {"-"*7} | {"-"*7} | {"-"*7}')

    best_rate = ORIG_DECAY_RATE
    best_mae = float('inf')
    rate_results = {}

    for rate in DECAY_RATE_GRID:
        result = evaluate_decay(corrections, rate, ORIG_DECAY_TARGET)
        if result:
            print(f'  {rate:8.3f} | {result["mae"]:7.1f} | {result["ratio"]:7.3f} | {result["correlation"]:7.3f}')
            rate_results[str(rate)] = result
            if result['mae'] < best_mae:
                best_mae = result['mae']
                best_rate = rate

    print(f'\n  Best rate: {best_rate} (MAE={best_mae:.1f})')

    # Phase 2: Sweep target at best rate
    print(f'\n  Phase 2: Decay target sweep (rate={best_rate})')
    print(f'  {"Target":>8s} | {"MAE":>7s} | {"Ratio":>7s} | {"r":>7s}')
    print(f'  {"-"*8} | {"-"*7} | {"-"*7} | {"-"*7}')

    best_target = ORIG_DECAY_TARGET
    best_overall_mae = float('inf')
    target_results = {}

    for target in DECAY_TARGET_GRID:
        result = evaluate_decay(corrections, best_rate, target)
        if result:
            print(f'  {target:8.0f} | {result["mae"]:7.1f} | {result["ratio"]:7.3f} | {result["correlation"]:7.3f}')
            target_results[str(target)] = result
            if result['mae'] < best_overall_mae:
                best_overall_mae = result['mae']
                best_target = target

    print(f'\n  Best target: {best_target} (MAE={best_overall_mae:.1f})')

    # Summary
    orig_result = evaluate_decay(corrections, ORIG_DECAY_RATE, ORIG_DECAY_TARGET)
    best_result = evaluate_decay(corrections, best_rate, best_target)

    print(f'\n  Original: rate={ORIG_DECAY_RATE}, target={ORIG_DECAY_TARGET}')
    if orig_result:
        print(f'    MAE={orig_result["mae"]:.1f}, ratio={orig_result["ratio"]:.3f}, r={orig_result["correlation"]:.3f}')
    print(f'  Optimized: rate={best_rate}, target={best_target}')
    if best_result:
        print(f'    MAE={best_result["mae"]:.1f}, ratio={best_result["ratio"]:.3f}, r={best_result["correlation"]:.3f}')

    improvement = (orig_result['mae'] - best_result['mae']) / orig_result['mae'] * 100 if orig_result and best_result else 0
    print(f'\n  MAE improvement: {improvement:.0f}%')

    if improvement > 20:
        verdict = f'CALIBRATED: rate={best_rate}, target={best_target} ({improvement:.0f}% MAE reduction)'
    elif improvement > 5:
        verdict = f'MARGINAL: rate={best_rate}, target={best_target} ({improvement:.0f}% MAE reduction)'
    else:
        verdict = f'NOT EFFECTIVE: decay tuning doesn\'t help'

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    restore_defaults()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2578_decay_calibration.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2578',
            'hypothesis': 'Higher counter-regulatory decay rate fixes overestimation',
            'verdict': verdict,
            'original': {'rate': ORIG_DECAY_RATE, 'target': ORIG_DECAY_TARGET},
            'calibrated': {'rate': best_rate, 'target': best_target},
            'rate_results': rate_results,
            'target_results': target_results,
            'improvement_pct': improvement,
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
