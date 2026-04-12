#!/usr/bin/env python3
"""
EXP-2571: Phenotype-Specific Settings Optimization

HYPOTHESIS: Well-Controlled (WC) and Hypo-Prone (HP) patient phenotypes
(EXP-2541) have systematically different optimal ISF/CR multipliers.
If true, phenotype classification can predict the DIRECTION of settings
adjustments, enabling faster cold-start recommendations.

DESIGN:
  - Classify NS patients (a-k) into phenotypes using existing criteria:
    WC: TIR>70%, hypo<5%, CV<36%
    HP: TIR<70% OR hypo>5% OR CV>40%
  - Run joint ISF×CR optimization per patient (reuse EXP-2568 approach)
  - Compare optimal settings between phenotype groups
  - Test: Mann-Whitney U for ISF and CR optima between groups

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
ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
CR_GRID = [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]


def classify_phenotype(glucose):
    """Simple phenotype classification from glucose array."""
    valid = glucose[np.isfinite(glucose)]
    tir = float(np.mean((valid >= 70) & (valid <= 180)))
    hypo = float(np.mean(valid < 70))
    cv = float(np.std(valid) / np.mean(valid))
    if tir >= 0.70 and hypo < 0.05 and cv < 0.36:
        return 'WC', tir, hypo, cv
    return 'HP', tir, hypo, cv


def extract_meal_windows(df, patient_id, max_windows=50):
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


def joint_optimize(windows):
    """Find optimal ISF×CR via grid search."""
    best_tir, best_isf, best_cr = -1.0, 1.0, 1.0
    for isf_m in ISF_GRID:
        for cr_m in CR_GRID:
            tirs = []
            for w in windows:
                try:
                    s = TherapySettings(
                        isf=w['isf'] * isf_m, cr=w['cr'] * cr_m,
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
                except Exception:
                    pass
            if tirs:
                mean_tir = float(np.mean(tirs))
                if mean_tir > best_tir:
                    best_tir = mean_tir
                    best_isf = isf_m
                    best_cr = cr_m
    return best_isf, best_cr, best_tir


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2571: Phenotype-Specific Settings Optimization')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    patients = {}
    for pid in NS_PATIENTS:
        pdf = df[df['patient_id'] == pid]
        glucose = pdf['glucose'].dropna().values
        pheno, tir, hypo, cv = classify_phenotype(glucose)

        windows = extract_meal_windows(df, pid)
        if len(windows) < 5:
            print(f'  {pid}: {len(windows)} windows (skip)')
            continue

        opt_isf, opt_cr, opt_tir = joint_optimize(windows)

        print(f'  {pid}: {pheno} (TIR={tir:.3f}, hypo={hypo:.3f}, CV={cv:.2f}) '
              f'→ opt ISF×{opt_isf}, CR×{opt_cr}, TIR={opt_tir:.3f}')

        patients[pid] = {
            'phenotype': pheno,
            'actual_tir': tir,
            'actual_hypo': hypo,
            'cv': cv,
            'optimal_isf': opt_isf,
            'optimal_cr': opt_cr,
            'optimal_tir': opt_tir,
            'n_windows': len(windows),
        }

    # Group by phenotype
    wc = {k: v for k, v in patients.items() if v['phenotype'] == 'WC'}
    hp = {k: v for k, v in patients.items() if v['phenotype'] == 'HP'}

    print(f'\n  Phenotype Split: WC={len(wc)}, HP={len(hp)}')

    if len(wc) >= 2 and len(hp) >= 2:
        wc_isf = [v['optimal_isf'] for v in wc.values()]
        hp_isf = [v['optimal_isf'] for v in hp.values()]
        wc_cr = [v['optimal_cr'] for v in wc.values()]
        hp_cr = [v['optimal_cr'] for v in hp.values()]

        u_isf, p_isf = stats.mannwhitneyu(wc_isf, hp_isf, alternative='two-sided')
        u_cr, p_cr = stats.mannwhitneyu(wc_cr, hp_cr, alternative='two-sided')

        print(f'\n  ISF: WC mean={np.mean(wc_isf):.2f} vs HP mean={np.mean(hp_isf):.2f} '
              f'(U={u_isf:.0f}, p={p_isf:.3f})')
        print(f'  CR:  WC mean={np.mean(wc_cr):.2f} vs HP mean={np.mean(hp_cr):.2f} '
              f'(U={u_cr:.0f}, p={p_cr:.3f})')

        # Also check actual TIR vs phenotype
        wc_tir = [v['actual_tir'] for v in wc.values()]
        hp_tir = [v['actual_tir'] for v in hp.values()]
        u_tir, p_tir = stats.mannwhitneyu(wc_tir, hp_tir, alternative='two-sided')
        print(f'  TIR: WC mean={np.mean(wc_tir):.3f} vs HP mean={np.mean(hp_tir):.3f} '
              f'(U={u_tir:.0f}, p={p_tir:.3f})')

        # Check if phenotype predicts optimization direction
        print(f'\n  Per-Phenotype Optimization Patterns:')
        print(f'  WC patients: {", ".join(f"{k}(ISF={v["optimal_isf"]},CR={v["optimal_cr"]})" for k,v in wc.items())}')
        print(f'  HP patients: {", ".join(f"{k}(ISF={v["optimal_isf"]},CR={v["optimal_cr"]})" for k,v in hp.items())}')

        isf_diff = p_isf < 0.1
        cr_diff = p_cr < 0.1
        passed = sum([isf_diff, cr_diff])
        verdict = 'SUPPORTED' if passed >= 1 else 'NOT SUPPORTED'
    else:
        verdict = 'INCONCLUSIVE'
        p_isf, p_cr = 1.0, 1.0
        print('  Not enough patients in both groups for statistical test')

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2571_phenotype_optimization.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2571',
            'hypothesis': 'Phenotype predicts optimal ISF/CR direction',
            'verdict': verdict,
            'patients': patients,
            'tests': {
                'isf_mannwhitney_p': float(p_isf),
                'cr_mannwhitney_p': float(p_cr),
            },
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
