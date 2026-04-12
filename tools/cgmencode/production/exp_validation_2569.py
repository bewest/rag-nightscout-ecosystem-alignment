#!/usr/bin/env python3
"""
EXP-2569: Settings Gap Validation — Does Forward Sim Identify Real Problems?

HYPOTHESIS: Patients with larger forward-sim-predicted TIR improvement from
joint ISF×CR optimization should have worse ACTUAL TIR in their real data.
If the sim correctly identifies who needs help most, there should be a
negative correlation between actual TIR and predicted improvement.

DESIGN:
  - Load actual TIR per patient from grid data (real CGM readings)
  - Load predicted TIR improvement from EXP-2568 joint optimization
  - Compute Spearman correlation between actual TIR and sim improvement
  - Also check: actual hypo% vs sim-predicted ISF optimal
  - NS patients only (a-k)

RESULT: (pending)
"""

import json
import time
import numpy as np
from pathlib import Path
from scipy import stats

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']


def compute_actual_metrics(df, patient_id):
    """Compute actual TIR, hypo%, and hyperglycemia from real CGM data."""
    pdf = df[df['patient_id'] == patient_id]
    glucose = pdf['glucose'].dropna()
    if len(glucose) < 100:
        return None
    return {
        'actual_tir': float(np.mean((glucose >= 70) & (glucose <= 180))),
        'actual_hypo': float(np.mean(glucose < 70)),
        'actual_hyper': float(np.mean(glucose > 180)),
        'mean_glucose': float(glucose.mean()),
        'cv': float(glucose.std() / glucose.mean()),
        'n_readings': len(glucose),
    }


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2569: Settings Gap Validation')
    print('=' * 70)

    # Load EXP-2568 results
    exp2568_path = RESULTS_DIR / 'exp-2568_joint_optimization.json'
    if not exp2568_path.exists():
        print('ERROR: EXP-2568 results not found. Run exp_joint_opt_2568.py first.')
        return
    with open(exp2568_path) as f:
        exp2568 = json.load(f)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    # Compute actual metrics and pair with sim predictions
    paired = []
    for pid in NS_PATIENTS:
        if pid not in exp2568['results']:
            continue
        actual = compute_actual_metrics(df, pid)
        if not actual:
            continue
        sim = exp2568['results'][pid]
        paired.append({
            'patient': pid,
            'actual_tir': actual['actual_tir'],
            'actual_hypo': actual['actual_hypo'],
            'actual_hyper': actual['actual_hyper'],
            'mean_glucose': actual['mean_glucose'],
            'cv': actual['cv'],
            'sim_baseline_tir': sim['baseline_tir'],
            'sim_joint_tir': sim['joint_optimal']['tir'],
            'sim_improvement': sim['joint_optimal']['tir'] - sim['baseline_tir'],
            'optimal_isf': sim['joint_optimal']['isf_mult'],
            'optimal_cr': sim['joint_optimal']['cr_mult'],
            'synergy': sim['synergy'],
        })

    if len(paired) < 4:
        print(f'Not enough patients ({len(paired)}), need at least 4')
        return

    actual_tirs = [p['actual_tir'] for p in paired]
    sim_improvements = [p['sim_improvement'] for p in paired]
    actual_hypos = [p['actual_hypo'] for p in paired]
    optimal_isfs = [p['optimal_isf'] for p in paired]
    sim_tirs = [p['sim_baseline_tir'] for p in paired]

    # Test 1: Actual TIR vs Sim improvement (should be negative — worse TIR → more room)
    r1, p1 = stats.spearmanr(actual_tirs, sim_improvements)
    print(f'\n  Test 1: Actual TIR vs Sim Improvement')
    print(f'    Spearman r={r1:.3f}, p={p1:.3f}')
    print(f'    Interpretation: {"Validated" if r1 < -0.3 else "Weak/No"} — '
          f'{"worse actual TIR → larger sim improvement" if r1 < 0 else "opposite direction"}')

    # Test 2: Actual TIR vs Sim baseline TIR (should be positive — sim captures real ranking)
    r2, p2 = stats.spearmanr(actual_tirs, sim_tirs)
    print(f'\n  Test 2: Actual TIR vs Sim Baseline TIR')
    print(f'    Spearman r={r2:.3f}, p={p2:.3f}')
    print(f'    Interpretation: {"Validated" if r2 > 0.3 else "Weak/No"} — '
          f'{"sim ranks patients correctly" if r2 > 0 else "sim ranking wrong"}')

    # Test 3: Actual hypo% vs optimal ISF (should be positive — more hypos → ISF needs reduction)
    r3, p3 = stats.spearmanr(actual_hypos, optimal_isfs)
    print(f'\n  Test 3: Actual Hypo% vs Optimal ISF')
    print(f'    Spearman r={r3:.3f}, p={p3:.3f}')
    print(f'    Interpretation: {"Validated" if r3 > 0.3 else "Weak/No"} — '
          f'{"more hypos → higher optimal ISF (less aggressive)" if r3 > 0 else "ISF not tracking hypo risk"}')

    # Test 4: Sim baseline vs actual — are they even measuring the same thing?
    r4, p4 = stats.pearsonr(actual_tirs, sim_tirs)
    print(f'\n  Test 4: Actual vs Sim TIR correlation (Pearson)')
    print(f'    r={r4:.3f}, p={p4:.3f}')
    print(f'    MAE between actual and sim: {np.mean(np.abs(np.array(actual_tirs)-np.array(sim_tirs))):.3f}')

    # Per-patient detail
    print(f'\n  Per-Patient Detail:')
    print(f'  {"Pat":>3s}  {"ActTIR":>6s}  {"SimTIR":>6s}  {"SimOpt":>6s}  {"Δ":>6s}  ISF×  CR×')
    for p in sorted(paired, key=lambda x: x['actual_tir']):
        print(f'  {p["patient"]:>3s}  {p["actual_tir"]:.3f}  {p["sim_baseline_tir"]:.3f}  '
              f'{p["sim_joint_tir"]:.3f}  {p["sim_improvement"]:+.3f}  '
              f'{p["optimal_isf"]:.1f}   {p["optimal_cr"]:.1f}')

    # Verdict
    validated_tests = sum([r1 < -0.3, r2 > 0.3, r3 > 0.3])
    if validated_tests >= 2:
        verdict = 'SUPPORTED'
    elif validated_tests >= 1:
        verdict = 'PARTIALLY SUPPORTED'
    else:
        verdict = 'NOT SUPPORTED'
    print(f'\n  VERDICT: {verdict} ({validated_tests}/3 validation tests passed)')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2569_settings_gap_validation.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2569',
            'hypothesis': 'Forward sim identifies patients who need most help',
            'verdict': verdict,
            'tests': {
                'actual_tir_vs_sim_improvement': {'r': r1, 'p': p1},
                'actual_tir_vs_sim_baseline': {'r': r2, 'p': p2},
                'actual_hypo_vs_optimal_isf': {'r': r3, 'p': p3},
                'actual_vs_sim_pearson': {'r': r4, 'p': p4},
            },
            'paired_data': paired,
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
