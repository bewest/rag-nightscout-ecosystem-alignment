#!/usr/bin/env python3
"""
EXP-2580: Joint ISF×CR Optimization with Counter-Regulation

HYPOTHESIS: Adding derivative-dependent counter-regulation (k=1.1, per EXP-2579)
to the forward sim will change the optimal ISF multiplier from ×0.5 (artifact)
to a more clinically reasonable value (×0.8–1.2), because the sim will no longer
overestimate insulin's effect by 2.5×.

DESIGN:
  - Same grid as EXP-2568: ISF × [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
                            CR  × [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
  - BUT: apply post-hoc counter-regulation correction (k=1.1, glucagon-only)
    to each sim trajectory before computing TIR
  - Compare optimal ISF/CR with vs without counter-regulation
  - If optimal ISF moves from 0.5 → 0.9+, the artifact is resolved

RATIONALE:
  EXP-2579 showed counter-reg at k=1.2 brings correction ratio from 0.39→1.09.
  The ISF×0.5 artifact (EXP-2568, 2572) exists because the sim overestimates
  insulin effect, so "lower ISF" = "less insulin effect" = "more realistic."
  With counter-regulation, the sim should be calibrated enough that ISF×1.0
  is already realistic.

SUCCESS CRITERION: Optimal ISF multiplier ≥ 0.8 for majority of patients.
"""

import json
import time
import numpy as np
from pathlib import Path
from itertools import product

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
    _STEP_MINUTES
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
CR_GRID = [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
MAX_WINDOWS = 50

# Counter-regulation parameters (from EXP-2579)
COUNTER_REG_K = 1.1  # Midpoint of optimal range (1.0-1.2)


def apply_counter_regulation(glucose_trace, k=COUNTER_REG_K):
    """Apply derivative-dependent counter-regulation to a sim trajectory.

    When glucose is dropping (dBG < 0), add an opposing upward force
    proportional to the rate of change. Mimics glucagon response.
    """
    corrected = np.zeros(len(glucose_trace))
    corrected[0] = glucose_trace[0]

    for t in range(1, len(glucose_trace)):
        raw_dBG = glucose_trace[t] - glucose_trace[t - 1]

        if t >= 2:
            corrected_dBG = corrected[t - 1] - corrected[t - 2]
        else:
            corrected_dBG = raw_dBG

        # Glucagon-only: oppose drops
        if corrected_dBG < 0:
            counter_reg = -k * corrected_dBG
        else:
            counter_reg = 0.0

        effective_dBG = raw_dBG + counter_reg
        corrected[t] = np.clip(corrected[t - 1] + effective_dBG, 40, 400)

    return corrected


def extract_meal_windows(df, patient_id, max_windows=MAX_WINDOWS):
    """Extract meal windows with carbs>10g and bolus>0.1U."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)
    idxs = pdf.index[mask]

    windows = []
    for idx in idxs[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        w = pdf.iloc[pos:pos + 48]
        if w['glucose'].isna().sum() > 5:
            continue
        windows.append({
            'g': float(w['glucose'].iloc[0]),
            'b': float(w['bolus'].iloc[0]),
            'c': float(w['carbs'].iloc[0]),
            'iob': float(w['iob'].iloc[0]),
            'h': float(w['time'].iloc[0].hour),
            'isf': float(w['scheduled_isf'].iloc[0]),
            'cr': float(w['scheduled_cr'].iloc[0]),
            'basal': float(w['scheduled_basal_rate'].iloc[0]),
            'actual_tir': float(np.mean(
                (w['glucose'].dropna() >= 70) & (w['glucose'].dropna() <= 180)
            )),
        })
        if len(windows) >= max_windows:
            break
    return windows


def evaluate_settings(windows, isf_mult, cr_mult, use_counter_reg=False):
    """Evaluate ISF×CR multiplier pair, return mean TIR and hypo%."""
    tirs, hypos = [], []
    for w in windows:
        try:
            s = TherapySettings(
                isf=w['isf'] * isf_mult, cr=w['cr'] * cr_mult,
                basal_rate=w['basal'], dia_hours=5.0
            )
            r = forward_simulate(
                initial_glucose=w['g'], settings=s, duration_hours=4.0,
                start_hour=w['h'],
                bolus_events=[InsulinEvent(0, w['b'])],
                carb_events=[CarbEvent(0, w['c'])],
                initial_iob=w['iob'], noise_std=0, seed=42
            )
            gluc = np.array(r.glucose)

            if use_counter_reg:
                gluc = apply_counter_regulation(gluc)

            tirs.append(float(np.mean((gluc >= 70) & (gluc <= 180))))
            hypos.append(float(np.mean(gluc < 70)))
        except Exception:
            pass
    if not tirs:
        return None
    return {
        'tir': float(np.mean(tirs)),
        'hypo_pct': float(np.mean(hypos)),
        'n': len(tirs),
    }


def run_grid(df, patient_id, use_counter_reg=False):
    """Run full ISF×CR grid for a patient."""
    windows = extract_meal_windows(df, patient_id)
    if len(windows) < 5:
        return None, windows

    grid_results = {}
    for isf_m, cr_m in product(ISF_GRID, CR_GRID):
        key = f'isf{isf_m:.1f}_cr{cr_m:.1f}'
        result = evaluate_settings(windows, isf_m, cr_m, use_counter_reg)
        if result:
            grid_results[key] = result

    return grid_results, windows


def find_optimum(grid_results):
    """Find optimal settings from grid results."""
    if not grid_results:
        return None

    best_key = max(grid_results, key=lambda k: grid_results[k]['tir'])
    best = grid_results[best_key]

    isf_val = float(best_key.split('_')[0].replace('isf', ''))
    cr_val = float(best_key.split('_')[1].replace('cr', ''))

    baseline = grid_results.get('isf1.0_cr1.0', {'tir': 0, 'hypo_pct': 0})

    return {
        'best_isf': isf_val,
        'best_cr': cr_val,
        'best_tir': best['tir'],
        'best_hypo': best['hypo_pct'],
        'baseline_tir': baseline['tir'],
        'baseline_hypo': baseline['hypo_pct'],
        'tir_gain': best['tir'] - baseline['tir'],
    }


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2580: Joint ISF×CR Optimization WITH Counter-Regulation')
    print('=' * 70)
    print(f'Counter-regulation k={COUNTER_REG_K}')
    print(f'Grid: {len(ISF_GRID)} ISF × {len(CR_GRID)} CR = '
          f'{len(ISF_GRID) * len(CR_GRID)} combos per patient')

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    results_without = {}
    results_with = {}

    for pid in NS_PATIENTS:
        print(f'\n  {pid}:', end=' ', flush=True)

        # Without counter-regulation (baseline)
        grid_no_cr, windows = run_grid(df, pid, use_counter_reg=False)
        if grid_no_cr is None:
            print(f'skip ({len(windows)} windows)')
            continue
        opt_no_cr = find_optimum(grid_no_cr)

        # With counter-regulation
        grid_with_cr, _ = run_grid(df, pid, use_counter_reg=True)
        opt_with_cr = find_optimum(grid_with_cr)

        results_without[pid] = opt_no_cr
        results_with[pid] = opt_with_cr

        print(f'windows={len(windows)}, '
              f'without_CR: ISF×{opt_no_cr["best_isf"]:.1f} CR×{opt_no_cr["best_cr"]:.1f} '
              f'(TIR={opt_no_cr["best_tir"]:.1%}), '
              f'with_CR: ISF×{opt_with_cr["best_isf"]:.1f} CR×{opt_with_cr["best_cr"]:.1f} '
              f'(TIR={opt_with_cr["best_tir"]:.1%})')

    # Summary
    print('\n' + '=' * 70)
    print('COMPARISON: Without vs With Counter-Regulation')
    print('=' * 70)
    print(f'{"Patient":>8} | {"Without CR":>20} | {"With CR":>20} | ISF shift')
    print('-' * 75)

    isf_without_list = []
    isf_with_list = []
    for pid in sorted(results_without):
        w = results_without[pid]
        c = results_with[pid]
        shift = c['best_isf'] - w['best_isf']
        print(f'{pid:>8} | ISF×{w["best_isf"]:.1f} CR×{w["best_cr"]:.1f} '
              f'TIR={w["best_tir"]:.1%} | ISF×{c["best_isf"]:.1f} CR×{c["best_cr"]:.1f} '
              f'TIR={c["best_tir"]:.1%} | {shift:+.1f}')
        isf_without_list.append(w['best_isf'])
        isf_with_list.append(c['best_isf'])

    mean_isf_without = np.mean(isf_without_list)
    mean_isf_with = np.mean(isf_with_list)

    print('-' * 75)
    print(f'{"Mean":>8} | ISF×{mean_isf_without:.2f} '
          f'                | ISF×{mean_isf_with:.2f} '
          f'                | {mean_isf_with - mean_isf_without:+.2f}')

    # Verdict
    n_good = sum(1 for v in isf_with_list if v >= 0.8)
    n_total = len(isf_with_list)

    print(f'\n{"=" * 70}')
    print(f'CONCLUSION')
    print(f'{"=" * 70}')
    print(f'Mean ISF without CR: ×{mean_isf_without:.2f}')
    print(f'Mean ISF with CR:    ×{mean_isf_with:.2f}')
    print(f'Patients with ISF ≥ 0.8: {n_good}/{n_total}')

    if n_good >= n_total * 0.6:
        verdict = 'CONFIRMED'
        print(f'\n✓ HYPOTHESIS CONFIRMED: Counter-regulation resolves ISF artifact')
    elif mean_isf_with > mean_isf_without + 0.15:
        verdict = 'PARTIAL'
        print(f'\n~ PARTIAL: ISF improved but not fully resolved')
    else:
        verdict = 'NOT CONFIRMED'
        print(f'\n✗ NOT CONFIRMED: Counter-regulation does not fix ISF artifact')

    elapsed = time.time() - t0
    print(f'\nElapsed: {elapsed:.0f}s')

    # Save
    output = {
        'experiment': 'EXP-2580',
        'title': 'Joint ISF×CR optimization with counter-regulation',
        'hypothesis': 'Counter-regulation (k=1.1) resolves ISF×0.5 artifact',
        'counter_reg_k': COUNTER_REG_K,
        'verdict': verdict,
        'isf_grid': ISF_GRID,
        'cr_grid': CR_GRID,
        'results_without_cr': results_without,
        'results_with_cr': results_with,
        'mean_isf_without': mean_isf_without,
        'mean_isf_with': mean_isf_with,
        'n_isf_ge_0_8': n_good,
        'n_patients': n_total,
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2580_joint_opt_counter_reg.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()
