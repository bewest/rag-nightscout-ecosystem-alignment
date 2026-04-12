#!/usr/bin/env python3
"""
EXP-2576: Persistent Component Calibration

HYPOTHESIS: The forward sim's persistent insulin component
(_PERSISTENT_FRACTION=0.37) is the root cause of 61% overestimation.
The persistent component accumulates total delivered excess insulin
(not remaining IOB) over 12h, creating an ever-growing
glucose-lowering force that doesn't decay.

DESIGN:
  - Extract pure corrections from all NS patients
  - Run sim with persistent_fraction = [0, 0.05, 0.10, 0.15, 0.20, 0.37]
  - Measure actual/sim ratio at 30min, 1h, 2h horizons for each fraction
  - Find fraction that produces ratio closest to 1.0 at all horizons
  - Also test fast_tau = [0.5, 0.8, 1.0, 1.5, 2.0] at best fraction

  Note: We monkey-patch the forward_simulator module constants since
  TherapySettings doesn't expose these parameters.

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

# Save original values
ORIG_PERSISTENT_FRAC = me._PERSISTENT_FRACTION
ORIG_FAST_TAU = me._FAST_TAU_HOURS

PERSISTENT_GRID = [0.0, 0.05, 0.10, 0.15, 0.20, 0.37]
TAU_GRID = [0.5, 0.8, 1.0, 1.5, 2.0]
HORIZONS = {6: '30min', 12: '60min', 24: '120min'}


def set_persistent_fraction(frac):
    """Monkey-patch the persistent fraction in both modules."""
    me._PERSISTENT_FRACTION = frac
    fs._PERSISTENT_FRACTION = frac
    fs._FAST_FRACTION = 1.0 - frac


def set_fast_tau(tau):
    """Monkey-patch the fast tau."""
    me._FAST_TAU_HOURS = tau
    fs._FAST_TAU_HOURS = tau


def restore_defaults():
    """Restore original values."""
    set_persistent_fraction(ORIG_PERSISTENT_FRAC)
    set_fast_tau(ORIG_FAST_TAU)


def extract_corrections(df, patient_id, max_n=40):
    """Extract pure correction windows."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (
        (pdf['bolus'] > 0.5) &
        (pdf['glucose'] > 150) &
        (pdf['carbs'].fillna(0) < 1)
    )
    carb_near = pdf['carbs'].fillna(0).rolling(13, center=True, min_periods=1).sum()
    mask = mask & (carb_near < 5)

    idxs = pdf.index[mask]
    corrections = []
    for idx in idxs[:max_n * 2]:
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
        })
        if len(corrections) >= max_n:
            break
    return corrections


def evaluate_params(corrections, persistent_frac, fast_tau=None):
    """Run sim at given params and compute actual/sim ratio at each horizon."""
    set_persistent_fraction(persistent_frac)
    if fast_tau is not None:
        set_fast_tau(fast_tau)

    horizon_ratios = {}
    for h_step, h_name in HORIZONS.items():
        actual_deltas = []
        sim_deltas = []

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
                    carb_events=[],
                    initial_iob=c['iob'], noise_std=0, seed=42
                )
                if h_step < len(r.glucose) and h_step < len(c['actual']):
                    actual_d = c['g0'] - c['actual'][h_step]
                    sim_d = c['g0'] - float(r.glucose[h_step])
                    if abs(sim_d) > 3 and np.isfinite(c['actual'][h_step]):
                        actual_deltas.append(actual_d)
                        sim_deltas.append(sim_d)
            except Exception:
                continue

        if actual_deltas and sim_deltas:
            mean_actual = float(np.mean(actual_deltas))
            mean_sim = float(np.mean(sim_deltas))
            ratio = mean_actual / mean_sim if abs(mean_sim) > 1 else 1.0
            mae = float(np.mean(np.abs(np.array(actual_deltas) - np.array(sim_deltas))))
            horizon_ratios[h_name] = {
                'ratio': round(ratio, 3),
                'mae': round(mae, 1),
                'n': len(actual_deltas),
            }

    restore_defaults()
    return horizon_ratios


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2576: Persistent Component Calibration')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    # Collect all corrections
    all_corrections = []
    for pid in NS_PATIENTS:
        corrections = extract_corrections(df, pid)
        all_corrections.extend(corrections)
        print(f'  {pid}: {len(corrections)} corrections')
    print(f'  Total: {len(all_corrections)} corrections')

    # Phase 1: Sweep persistent fraction at default tau
    print(f'\n  Phase 1: Persistent fraction sweep (tau={ORIG_FAST_TAU}h)')
    print(f'  {"Frac":>6s} | {"30min":>8s} | {"60min":>8s} | {"120min":>8s} | {"MAE-2h":>7s}')
    print(f'  {"-"*6} | {"-"*8} | {"-"*8} | {"-"*8} | {"-"*7}')

    frac_results = {}
    best_frac = 0.37
    best_2h_error = float('inf')

    for frac in PERSISTENT_GRID:
        ratios = evaluate_params(all_corrections, frac)
        r30 = ratios.get('30min', {}).get('ratio', '-')
        r60 = ratios.get('60min', {}).get('ratio', '-')
        r120 = ratios.get('120min', {}).get('ratio', '-')
        mae = ratios.get('120min', {}).get('mae', float('inf'))

        print(f'  {frac:6.2f} | {str(r30):>8s} | {str(r60):>8s} | {str(r120):>8s} | {mae:>7.1f}')
        frac_results[str(frac)] = ratios

        # Best = ratio closest to 1.0 at 2h
        if isinstance(r120, float):
            error = abs(r120 - 1.0)
            if error < best_2h_error:
                best_2h_error = error
                best_frac = frac

    print(f'\n  Best persistent fraction: {best_frac:.2f}')

    # Phase 2: Sweep tau at best fraction
    print(f'\n  Phase 2: Tau sweep (persistent={best_frac})')
    print(f'  {"Tau":>6s} | {"30min":>8s} | {"60min":>8s} | {"120min":>8s} | {"MAE-2h":>7s}')
    print(f'  {"-"*6} | {"-"*8} | {"-"*8} | {"-"*8} | {"-"*7}')

    tau_results = {}
    best_tau = ORIG_FAST_TAU
    best_overall_error = float('inf')

    for tau in TAU_GRID:
        ratios = evaluate_params(all_corrections, best_frac, tau)
        r30 = ratios.get('30min', {}).get('ratio', '-')
        r60 = ratios.get('60min', {}).get('ratio', '-')
        r120 = ratios.get('120min', {}).get('ratio', '-')
        mae = ratios.get('120min', {}).get('mae', float('inf'))

        print(f'  {tau:6.1f} | {str(r30):>8s} | {str(r60):>8s} | {str(r120):>8s} | {mae:>7.1f}')
        tau_results[str(tau)] = ratios

        # Best = lowest MAE at 2h
        if mae < best_overall_error:
            best_overall_error = mae
            best_tau = tau

    print(f'\n  Best tau: {best_tau}h')
    print(f'  Recommended params: persistent={best_frac}, tau={best_tau}h')
    print(f'  Current params: persistent={ORIG_PERSISTENT_FRAC}, tau={ORIG_FAST_TAU}h')

    verdict = (f'CALIBRATED: persistent={best_frac}, tau={best_tau} '
               f'(was persistent={ORIG_PERSISTENT_FRAC}, tau={ORIG_FAST_TAU})')
    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    restore_defaults()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2576_persistent_calibration.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2576',
            'hypothesis': 'Persistent component causes overestimation',
            'verdict': verdict,
            'frac_results': frac_results,
            'tau_results': tau_results,
            'best_frac': best_frac,
            'best_tau': best_tau,
            'original': {'persistent': ORIG_PERSISTENT_FRAC, 'tau': ORIG_FAST_TAU},
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
