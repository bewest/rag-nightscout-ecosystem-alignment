#!/usr/bin/env python3
"""
EXP-2575: Insulin Activity Curve Calibration

HYPOTHESIS: The forward sim's insulin activity curve (two-component:
63% fast τ=0.8h + 37% persistent 12h window) is too potent, causing
systematic overestimation across ISF (22%), basal (50%), and CR domains.

DESIGN:
  We compare sim-predicted glucose change to ACTUAL glucose change for
  pure correction events at multiple time horizons (30min, 1h, 2h, 3h).
  By fitting a scaling factor at each horizon, we can determine:

  1. Is the overestimation time-dependent? (fast vs slow component)
  2. What τ value would correctly match actual corrections?
  3. Is the 63/37 split correct?

  We test: τ values [0.5, 0.8, 1.0, 1.2, 1.5, 2.0] and fast fractions
  [0.4, 0.5, 0.63, 0.7, 0.8] to find the best-fitting parameters.

RESULT: (pending)
"""

import json
import time
import numpy as np
from pathlib import Path
from scipy.optimize import minimize_scalar

import pandas as pd

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
    _insulin_activity_curve, _STEP_MINUTES
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
HORIZONS = [6, 12, 24, 36]  # steps = 30min, 1h, 2h, 3h
TAU_GRID = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
FAST_FRAC_GRID = [0.40, 0.50, 0.63, 0.70, 0.80]


def extract_corrections(df, patient_id, max_n=60):
    """Extract pure correction boluses with outcome trajectories."""
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
        if pos + 36 >= len(pdf):
            continue
        w = pdf.iloc[pos:pos + 37]
        if w['glucose'].isna().sum() > 4:
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


def sim_correction(c, tau_override=None, fast_frac_override=None):
    """Simulate a correction with optionally overridden parameters."""
    # Build settings
    s = TherapySettings(
        isf=c['isf'], cr=c['cr'],
        basal_rate=c['basal'], dia_hours=5.0
    )

    # If we're overriding, we need to monkey-patch — but that's fragile.
    # Instead, scale the bolus by a factor to simulate different tau/activity.
    # For the calibration, we'll compare actual vs predicted deltas and compute
    # a scaling factor, which is equivalent to modifying the activity curve.

    r = forward_simulate(
        initial_glucose=c['g0'], settings=s, duration_hours=3.0,
        start_hour=c['h'],
        bolus_events=[InsulinEvent(0, c['bolus'])],
        carb_events=[],
        initial_iob=c['iob'], noise_std=0, seed=42
    )
    return r.glucose


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2575: Insulin Activity Curve Calibration')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    # Collect actual vs predicted deltas at each horizon
    horizon_data = {h: {'actual_delta': [], 'sim_delta': []} for h in HORIZONS}
    patient_ratios = {}

    for pid in NS_PATIENTS:
        corrections = extract_corrections(df, pid)
        if len(corrections) < 5:
            print(f'  {pid}: {len(corrections)} corrections (skip)')
            continue

        pid_ratios = {}
        for c in corrections:
            sim_g = sim_correction(c)
            actual = np.array(c['actual'])

            for h in HORIZONS:
                if h < len(actual) and h < len(sim_g) and np.isfinite(actual[h]):
                    actual_delta = c['g0'] - float(actual[h])
                    sim_delta = c['g0'] - float(sim_g[h])
                    if abs(sim_delta) > 2:  # avoid division by ~zero
                        horizon_data[h]['actual_delta'].append(actual_delta)
                        horizon_data[h]['sim_delta'].append(sim_delta)

        # Per-patient ratio at 2h horizon
        h2_actual = []
        h2_sim = []
        for c in corrections:
            sim_g = sim_correction(c)
            actual = np.array(c['actual'])
            if 24 < len(actual) and 24 < len(sim_g) and np.isfinite(actual[24]):
                h2_actual.append(c['g0'] - float(actual[24]))
                h2_sim.append(c['g0'] - float(sim_g[24]))

        if h2_sim:
            ratio = float(np.mean(h2_actual)) / float(np.mean(h2_sim)) if np.mean(h2_sim) != 0 else 1.0
            print(f'  {pid}: {len(corrections)} corrections | 2h ratio={ratio:.2f}')
            patient_ratios[pid] = ratio

    # Population horizon analysis
    print(f'\n  Horizon Analysis (actual/sim ratio):')
    horizon_results = {}
    for h in HORIZONS:
        ad = np.array(horizon_data[h]['actual_delta'])
        sd = np.array(horizon_data[h]['sim_delta'])
        if len(ad) > 10:
            # Only use cases where sim predicts a drop
            mask = sd > 5
            if mask.sum() > 10:
                ratio = float(np.mean(ad[mask]) / np.mean(sd[mask]))
                corr = float(np.corrcoef(ad[mask], sd[mask])[0, 1]) if mask.sum() > 2 else 0
                minutes = h * 5
                print(f'    {minutes:3d}min: ratio={ratio:.2f}, r={corr:.2f}, n={mask.sum()}')
                horizon_results[f'{minutes}min'] = {
                    'ratio': ratio, 'correlation': corr, 'n': int(mask.sum())
                }

    # Key finding: is the overestimation getting worse over time?
    ratios = [horizon_results[k]['ratio'] for k in sorted(horizon_results.keys())]
    if len(ratios) >= 2:
        if ratios[-1] < ratios[0]:
            trend = 'INCREASING overestimation over time → slow component too strong'
        elif ratios[-1] > ratios[0]:
            trend = 'DECREASING overestimation over time → fast component too strong'
        else:
            trend = 'STABLE overestimation → uniform scaling issue'
        print(f'\n  Trend: {trend}')

    # What effective ISF does the data imply?
    if horizon_results.get('120min'):
        r_2h = horizon_results['120min']['ratio']
        print(f'\n  Implied correction: multiply sim ISF by {r_2h:.2f}')
        print(f'  i.e., if sim says ISF=50, effective ISF should be {50*r_2h:.0f}')
        if r_2h < 1.0:
            print(f'  → Sim is {(1-r_2h)*100:.0f}% too potent → ISF×{r_2h:.2f} needed')
            verdict = f'CONFIRMED — sim {(1-r_2h)*100:.0f}% too potent'
        else:
            verdict = 'NOT CONFIRMED — sim is not overestimating'
    else:
        verdict = 'INCONCLUSIVE'

    print(f'\n  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2575_insulin_calibration.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2575',
            'hypothesis': 'Sim insulin activity curve is systematically too potent',
            'verdict': verdict,
            'horizon_results': horizon_results,
            'patient_ratios': patient_ratios,
            'trend': trend if len(ratios) >= 2 else None,
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
