#!/usr/bin/env python3
"""
EXP-2568: Joint ISF × CR Optimization via Forward Simulation

HYPOTHESIS: ISF and CR interact nonlinearly during post-meal corrections.
Optimizing them JOINTLY should yield higher TIR than optimizing each
independently (EXP-2563 + EXP-2567).

DESIGN:
  - Joint grid: ISF × [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
                 CR  × [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
  - 49 combinations per patient
  - 50 meal windows per patient (carbs>10g, bolus>0.1U)
  - 4-hour forward simulation, TIR (70-180) outcome
  - NS patients only (a-k)
  - Compare joint optimal TIR vs single-axis optima

RESULT: (pending)
"""

import json
import time
import numpy as np
from pathlib import Path
from itertools import product

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
CR_GRID = [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
MAX_WINDOWS = 50


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
        })
        if len(windows) >= max_windows:
            break
    return windows


def evaluate_settings(windows, isf_mult, cr_mult):
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


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2568: Joint ISF × CR Optimization')
    print('=' * 70)
    print(f'  Grid: {len(ISF_GRID)} ISF × {len(CR_GRID)} CR = '
          f'{len(ISF_GRID) * len(CR_GRID)} combos per patient')

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    results = {}
    for pid in NS_PATIENTS:
        windows = extract_meal_windows(df, pid)
        if len(windows) < 5:
            print(f'  {pid}: {len(windows)} windows (skip)')
            continue

        grid_results = {}
        for isf_m, cr_m in product(ISF_GRID, CR_GRID):
            key = f'isf{isf_m:.1f}_cr{cr_m:.1f}'
            result = evaluate_settings(windows, isf_m, cr_m)
            if result:
                grid_results[key] = result

        # Find joint optimum
        best_key = max(grid_results, key=lambda k: grid_results[k]['tir'])
        best = grid_results[best_key]

        # Find single-axis optima for comparison
        baseline = grid_results.get('isf1.0_cr1.0', {'tir': 0, 'hypo_pct': 0})

        # Best ISF at CR=1.0
        isf_only = {k: v for k, v in grid_results.items() if '_cr1.0' in k}
        best_isf_key = max(isf_only, key=lambda k: isf_only[k]['tir']) if isf_only else 'isf1.0_cr1.0'

        # Best CR at ISF=1.0
        cr_only = {k: v for k, v in grid_results.items() if 'isf1.0_' in k}
        best_cr_key = max(cr_only, key=lambda k: cr_only[k]['tir']) if cr_only else 'isf1.0_cr1.0'

        isf_val = float(best_isf_key.split('_')[0].replace('isf', ''))
        cr_val = float(best_cr_key.split('_')[1].replace('cr', ''))
        joint_isf = float(best_key.split('_')[0].replace('isf', ''))
        joint_cr = float(best_key.split('_')[1].replace('cr', ''))

        synergy = best['tir'] - max(
            grid_results.get(best_isf_key, {'tir': 0})['tir'],
            grid_results.get(best_cr_key, {'tir': 0})['tir']
        )

        print(f'  {pid}: {len(windows)}w | baseline TIR={baseline["tir"]:.3f} | '
              f'ISF-only: x{isf_val} TIR={grid_results.get(best_isf_key, {}).get("tir", 0):.3f} | '
              f'CR-only: x{cr_val} TIR={grid_results.get(best_cr_key, {}).get("tir", 0):.3f} | '
              f'JOINT: ISF×{joint_isf} CR×{joint_cr} TIR={best["tir"]:.3f} '
              f'synergy={synergy:+.3f}')

        results[pid] = {
            'n_windows': len(windows),
            'baseline_tir': baseline['tir'],
            'baseline_hypo': baseline['hypo_pct'],
            'best_isf_only': {'mult': isf_val, 'tir': grid_results.get(best_isf_key, {}).get('tir', 0)},
            'best_cr_only': {'mult': cr_val, 'tir': grid_results.get(best_cr_key, {}).get('tir', 0)},
            'joint_optimal': {
                'isf_mult': joint_isf, 'cr_mult': joint_cr,
                'tir': best['tir'], 'hypo_pct': best['hypo_pct'],
            },
            'synergy': synergy,
            'grid_size': len(grid_results),
        }

    # Summary
    synergies = [v['synergy'] for v in results.values()]
    joint_tirs = [v['joint_optimal']['tir'] for v in results.values()]
    baseline_tirs = [v['baseline_tir'] for v in results.values()]
    isf_mults = [v['joint_optimal']['isf_mult'] for v in results.values()]
    cr_mults = [v['joint_optimal']['cr_mult'] for v in results.values()]

    print(f'\nSummary ({len(results)} patients):')
    print(f'  Baseline TIR: mean={np.mean(baseline_tirs):.3f}')
    print(f'  Joint TIR:    mean={np.mean(joint_tirs):.3f} '
          f'(+{np.mean(joint_tirs) - np.mean(baseline_tirs):.3f})')
    print(f'  Synergy:      mean={np.mean(synergies):+.3f} '
          f'(positive={sum(1 for s in synergies if s > 0.01)}/{len(synergies)})')
    print(f'  Joint ISF:    mean={np.mean(isf_mults):.2f} '
          f'range=[{min(isf_mults):.1f}, {max(isf_mults):.1f}]')
    print(f'  Joint CR:     mean={np.mean(cr_mults):.2f} '
          f'range=[{min(cr_mults):.1f}, {max(cr_mults):.1f}]')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    verdict = 'SUPPORTED' if np.mean(synergies) > 0.01 else 'NOT SUPPORTED'
    print(f'\n  VERDICT: {verdict}')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2568_joint_optimization.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2568',
            'hypothesis': 'Joint ISF×CR optimization yields higher TIR than independent optimization',
            'verdict': verdict,
            'results': results,
            'summary': {
                'mean_baseline_tir': float(np.mean(baseline_tirs)),
                'mean_joint_tir': float(np.mean(joint_tirs)),
                'mean_synergy': float(np.mean(synergies)),
                'n_positive_synergy': sum(1 for s in synergies if s > 0.01),
                'n_patients': len(results),
            },
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
