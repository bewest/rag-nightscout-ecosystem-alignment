#!/usr/bin/env python3
"""
EXP-2577: AID Loop Basal Counteraction Quantification

HYPOTHESIS: The AID loop systematically reduces basal delivery after
correction boluses, counteracting ~60% of the bolus's glucose-lowering
effect. Using actual_basal_rate (what the loop delivered) instead of
scheduled_basal_rate in the forward sim should dramatically reduce
overestimation (from ratio=0.37 toward ratio=1.0).

DESIGN:
  Phase 1: Quantify loop basal response during corrections
  - Extract correction windows with actual_basal_rate data
  - Measure: actual_basal / scheduled_basal during 2h post-correction
  - Compute "basal deficit" = scheduled - actual (units reduced by loop)

  Phase 2: Test forward sim with actual basal
  - Run sim with metabolic_basal_rate = actual_basal_rate (time-varying)
  - Compare actual/sim ratio at 30min, 1h, 2h
  - If ratio improves toward 1.0, loop counteraction is confirmed as root cause

RESULT: (pending)
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
HORIZONS = {6: '30min', 12: '60min', 24: '120min'}


def extract_corrections_with_basal(df, patient_id, max_n=50):
    """Extract corrections with actual basal rate data."""
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
        if w['actual_basal_rate'].isna().sum() > 10:
            continue

        corrections.append({
            'g0': float(w['glucose'].iloc[0]),
            'bolus': float(w['bolus'].iloc[0]),
            'iob': float(w['iob'].iloc[0]),
            'h': float(w['time'].iloc[0].hour),
            'isf': float(w['scheduled_isf'].iloc[0]),
            'cr': float(w['scheduled_cr'].iloc[0]),
            'sched_basal': float(w['scheduled_basal_rate'].iloc[0]),
            'actual_basals': w['actual_basal_rate'].fillna(
                w['scheduled_basal_rate']).values.tolist(),
            'actual_glucose': [float(x) for x in w['glucose'].values],
        })
        if len(corrections) >= max_n:
            break
    return corrections


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2577: AID Loop Basal Counteraction')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    # Phase 1: Quantify basal reduction
    print('\n  Phase 1: Basal reduction during corrections')
    all_ratios = []
    all_deficits = []

    for pid in NS_PATIENTS:
        corrections = extract_corrections_with_basal(df, pid)
        if len(corrections) < 3:
            print(f'  {pid}: {len(corrections)} corrections (skip)')
            continue

        basal_ratios = []
        basal_deficits_u = []
        for c in corrections:
            actual = np.array(c['actual_basals'])
            sched = c['sched_basal']
            if sched > 0:
                ratio = float(np.mean(actual)) / sched
                deficit = (sched - float(np.mean(actual))) * 2.0  # 2h in units
                basal_ratios.append(ratio)
                basal_deficits_u.append(deficit)

        if basal_ratios:
            mean_ratio = float(np.mean(basal_ratios))
            mean_deficit = float(np.mean(basal_deficits_u))
            all_ratios.extend(basal_ratios)
            all_deficits.extend(basal_deficits_u)
            pct_reduced = (1 - mean_ratio) * 100
            print(f'  {pid}: {len(corrections)} corrections | '
                  f'actual/scheduled={mean_ratio:.2f} '
                  f'({pct_reduced:+.0f}% basal) | '
                  f'deficit={mean_deficit:.2f}U/2h')

    if all_ratios:
        pop_ratio = float(np.mean(all_ratios))
        pop_deficit = float(np.mean(all_deficits))
        print(f'\n  Population: actual/scheduled={pop_ratio:.2f} '
              f'({(1-pop_ratio)*100:+.0f}% basal reduction)')
        print(f'  Mean basal deficit: {pop_deficit:.2f}U over 2h post-correction')

    # Phase 2: Sim with actual basal vs scheduled basal
    print(f'\n  Phase 2: Sim comparison (scheduled vs actual basal)')

    scheduled_ratios = {h: [] for h in HORIZONS.values()}
    actual_ratios = {h: [] for h in HORIZONS.values()}

    for pid in NS_PATIENTS:
        corrections = extract_corrections_with_basal(df, pid)
        if len(corrections) < 3:
            continue

        for c in corrections:
            # Sim with SCHEDULED basal (current behavior)
            try:
                s_sched = TherapySettings(
                    isf=c['isf'], cr=c['cr'],
                    basal_rate=c['sched_basal'], dia_hours=5.0
                )
                r_sched = forward_simulate(
                    initial_glucose=c['g0'], settings=s_sched,
                    duration_hours=2.5, start_hour=c['h'],
                    bolus_events=[InsulinEvent(0, c['bolus'])],
                    carb_events=[], initial_iob=c['iob'],
                    noise_std=0, seed=42
                )
            except Exception:
                continue

            # Sim with ACTUAL basal (loop-adjusted)
            try:
                mean_actual_basal = float(np.mean(c['actual_basals'][:24]))
                s_actual = TherapySettings(
                    isf=c['isf'], cr=c['cr'],
                    basal_rate=mean_actual_basal, dia_hours=5.0
                )
                r_actual = forward_simulate(
                    initial_glucose=c['g0'], settings=s_actual,
                    duration_hours=2.5, start_hour=c['h'],
                    bolus_events=[InsulinEvent(0, c['bolus'])],
                    carb_events=[], initial_iob=c['iob'],
                    noise_std=0, seed=42
                )
            except Exception:
                continue

            for h_step, h_name in HORIZONS.items():
                if h_step < len(c['actual_glucose']) and np.isfinite(c['actual_glucose'][h_step]):
                    actual_delta = c['g0'] - c['actual_glucose'][h_step]

                    if h_step < len(r_sched.glucose):
                        sim_delta_sched = c['g0'] - float(r_sched.glucose[h_step])
                        if abs(sim_delta_sched) > 3:
                            scheduled_ratios[h_name].append(actual_delta / sim_delta_sched)

                    if h_step < len(r_actual.glucose):
                        sim_delta_actual = c['g0'] - float(r_actual.glucose[h_step])
                        if abs(sim_delta_actual) > 3:
                            actual_ratios[h_name].append(actual_delta / sim_delta_actual)

    print(f'\n  {"Horizon":>8s} | {"Sched ratio":>12s} | {"Actual ratio":>12s} | Improvement')
    print(f'  {"-"*8} | {"-"*12} | {"-"*12} | {"-"*11}')

    for h_name in ['30min', '60min', '120min']:
        sr = float(np.mean(scheduled_ratios[h_name])) if scheduled_ratios[h_name] else 0
        ar = float(np.mean(actual_ratios[h_name])) if actual_ratios[h_name] else 0
        improvement = abs(ar - 1.0) < abs(sr - 1.0)
        print(f'  {h_name:>8s} | {sr:>12.3f} | {ar:>12.3f} | '
              f'{"YES" if improvement else "no"} '
              f'(err {abs(sr-1)*100:.0f}%→{abs(ar-1)*100:.0f}%)')

    # Verdict
    sr_2h = float(np.mean(scheduled_ratios.get('120min', [0])))
    ar_2h = float(np.mean(actual_ratios.get('120min', [0])))
    improved = abs(ar_2h - 1.0) < abs(sr_2h - 1.0)

    if improved and abs(ar_2h - 1.0) < 0.3:
        verdict = f'CONFIRMED — actual basal reduces error from {abs(sr_2h-1)*100:.0f}% to {abs(ar_2h-1)*100:.0f}%'
    elif improved:
        verdict = f'PARTIALLY CONFIRMED — improves but still off ({abs(ar_2h-1)*100:.0f}% error)'
    else:
        verdict = 'NOT CONFIRMED — actual basal doesn\'t help'

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2577_loop_counteraction.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2577',
            'hypothesis': 'AID loop basal counteraction causes sim overestimation',
            'verdict': verdict,
            'basal_reduction_ratio': float(np.mean(all_ratios)) if all_ratios else None,
            'mean_basal_deficit_u': float(np.mean(all_deficits)) if all_deficits else None,
            'scheduled_ratios': {k: float(np.mean(v)) if v else None
                                 for k, v in scheduled_ratios.items()},
            'actual_ratios': {k: float(np.mean(v)) if v else None
                              for k, v in actual_ratios.items()},
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
