#!/usr/bin/env python3
"""
EXP-2573: Meal-Size-Dependent CR Optimization

HYPOTHESIS: Small meals (≤20g) and large meals (≥50g) have different
optimal CR multipliers. EXP-2535 showed BG rise/gram decreases with
meal size (5.50→0.59 mg/dL/g), and CR nonlinearity (γ=0.119). The
forward sim should show different optimal CR at each meal tier.

DESIGN:
  - Split meal windows into tiers: Small (≤20g), Medium (20-50g), Large (≥50g)
  - Run CR grid search [0.8-3.0] within each tier
  - Compare optimal CR multiplier across tiers
  - If optimal differs by >20%, meal-size CR is warranted

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
CR_GRID = [0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0]
TIERS = {'small': (0, 20), 'medium': (20, 50), 'large': (50, 500)}


def extract_tiered_meal_windows(df, patient_id, max_per_tier=30):
    """Extract meal windows split by carb size tier."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (pdf['carbs'].fillna(0) >= 10) & (pdf['bolus'] > 0.1) & (pdf['glucose'] > 60)
    idxs = pdf.index[mask]

    tier_windows = {t: [] for t in TIERS}
    for idx in idxs:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        w = pdf.iloc[pos:pos + 48]
        if w['glucose'].isna().sum() > 5:
            continue
        carbs = float(w['carbs'].iloc[0])
        for tier_name, (lo, hi) in TIERS.items():
            if lo < carbs <= hi and len(tier_windows[tier_name]) < max_per_tier:
                tier_windows[tier_name].append({
                    'g': float(w['glucose'].iloc[0]),
                    'b': float(w['bolus'].iloc[0]),
                    'c': carbs,
                    'iob': float(w['iob'].iloc[0]),
                    'h': float(w['time'].iloc[0].hour),
                    'isf': float(w['scheduled_isf'].iloc[0]),
                    'cr': float(w['scheduled_cr'].iloc[0]),
                    'basal': float(w['scheduled_basal_rate'].iloc[0]),
                })
                break
    return tier_windows


def evaluate_cr_at_tier(windows, cr_mult):
    """Compute mean TIR for a set of windows at given CR multiplier."""
    tirs = []
    for w in windows:
        try:
            s = TherapySettings(
                isf=w['isf'], cr=w['cr'] * cr_mult,
                basal_rate=w['basal'], dia_hours=5.0
            )
            r = forward_simulate(
                initial_glucose=w['g'], settings=s, duration_hours=4.0,
                start_hour=w['h'],
                bolus_events=[InsulinEvent(0, w['b'])],
                carb_events=[CarbEvent(0, w['c'])],
                initial_iob=w['iob'], noise_std=0, seed=42
            )
            tirs.append(r.tir)
        except Exception:
            continue
    return float(np.mean(tirs)) if tirs else None


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2573: Meal-Size-Dependent CR Optimization')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    all_tier_optima = {t: [] for t in TIERS}
    patient_results = {}

    for pid in NS_PATIENTS:
        tier_windows = extract_tiered_meal_windows(df, pid)
        counts = {t: len(ws) for t, ws in tier_windows.items()}
        print(f'\n  {pid}: small={counts["small"]}, med={counts["medium"]}, '
              f'large={counts["large"]}')

        pid_results = {}
        for tier_name, windows in tier_windows.items():
            if len(windows) < 5:
                print(f'    {tier_name}: skip ({len(windows)} windows)')
                continue

            best_tir = -1
            best_cr = 1.0
            for cr_m in CR_GRID:
                tir = evaluate_cr_at_tier(windows, cr_m)
                if tir is not None and tir > best_tir:
                    best_tir = tir
                    best_cr = cr_m

            baseline_tir = evaluate_cr_at_tier(windows, 1.0)
            delta = (best_tir - (baseline_tir or 0)) * 100

            print(f'    {tier_name}: optimal CR×{best_cr:.1f} '
                  f'(TIR {baseline_tir:.3f}→{best_tir:.3f}, +{delta:.1f}pp)')
            pid_results[tier_name] = {
                'n': len(windows),
                'optimal_cr': best_cr,
                'baseline_tir': baseline_tir,
                'best_tir': best_tir,
            }
            all_tier_optima[tier_name].append(best_cr)

        patient_results[pid] = pid_results

    # Population summary
    print('\n' + '=' * 70)
    print('Population Summary')
    print('=' * 70)
    for tier_name in TIERS:
        vals = all_tier_optima[tier_name]
        if vals:
            print(f'  {tier_name:8s}: n={len(vals):2d}, mean CR×{np.mean(vals):.2f}, '
                  f'median CR×{np.median(vals):.2f}, range [{min(vals):.1f}-{max(vals):.1f}]')

    # Statistical test: do tiers differ?
    from scipy.stats import kruskal
    tier_lists = [all_tier_optima[t] for t in TIERS if len(all_tier_optima[t]) >= 3]
    if len(tier_lists) >= 2:
        stat, p = kruskal(*tier_lists)
        print(f'\n  Kruskal-Wallis: H={stat:.2f}, p={p:.4f}')
        if p < 0.05:
            print(f'  → SIGNIFICANT: meal-size CR is warranted')
            verdict = 'SUPPORTED'
        else:
            print(f'  → NOT significant: same CR works for all sizes')
            verdict = 'NOT SUPPORTED'
    else:
        verdict = 'INCONCLUSIVE'
        print(f'  Too few tiers for statistical test')

    # Check if large meals genuinely need different CR
    sm = all_tier_optima.get('small', [])
    lg = all_tier_optima.get('large', [])
    if sm and lg:
        diff = abs(np.mean(sm) - np.mean(lg))
        print(f'\n  Small vs Large CR difference: {diff:.2f}')
        if diff > 0.2:
            print(f'  → Practical difference ≥0.2: meal-size CR has clinical value')
        else:
            print(f'  → Practical difference <0.2: not clinically meaningful')

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2573_meal_size_cr.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2573',
            'hypothesis': 'Small and large meals need different CR multipliers',
            'verdict': verdict,
            'tier_optima': {t: vals for t, vals in all_tier_optima.items()},
            'patient_results': patient_results,
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
