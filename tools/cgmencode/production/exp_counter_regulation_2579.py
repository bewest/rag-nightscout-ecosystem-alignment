#!/usr/bin/env python3
"""
EXP-2579: Derivative-Dependent Counter-Regulation Model

HYPOTHESIS: Adding a glucose-rate-dependent opposing force to the forward sim
(mimicking glucagon release when glucose drops fast, and insulin secretion when
glucose rises fast) will reduce the 2.5× overestimation of correction effects.

RATIONALE (from EXP-2572–2578):
  - Sim overestimates correction bolus effect by 2.5× at 2h (EXP-2575)
  - The overestimation is STRUCTURAL, not parametric:
    - Tuning persistent fraction: no effect (EXP-2576)
    - Incorporating loop basal reduction: no effect (EXP-2577)
    - Increasing target-seeking decay: WORSENS it (EXP-2578)
  - Root cause: real counter-regulation opposes glucose CHANGES (derivative),
    not deviations from a target. When glucose drops fast, glucagon +
    hepatic glucose production ramp up. The sim has no such mechanism.

DESIGN:
  Counter-regulation model: when dBG/dt is negative (glucose dropping),
  add an opposing upward force proportional to the rate of change:

    counter_reg = -k × min(dBG_raw, 0)        [positive when glucose drops]

  This means:
    - No effect when glucose is rising (dBG > 0)
    - Small effect for slow drops
    - Large effect for fast drops (strong glucagon response)

  We sweep:
    k ∈ [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    symmetric ∈ [False, True]  (True = also dampen rises)

  Evaluation: compare sim-predicted vs actual glucose change at 30min, 1h, 2h
  for 376 pure correction events across 11 NS patients.

  Success criterion: actual/sim ratio within 0.7-1.3 at 2h (currently 0.39)
"""

import json
import time
import numpy as np
from pathlib import Path

import pandas as pd

import cgmencode.production.forward_simulator as fs
import cgmencode.production.metabolic_engine as me
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
    _STEP_MINUTES, _STEPS_PER_HOUR
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

K_GRID = [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0]
SYMMETRIC_OPTIONS = [False, True]
HORIZONS = [6, 12, 24]  # steps: 30min, 1h, 2h


def extract_corrections(df, max_per_patient=50):
    """Extract pure correction boluses with outcome trajectories."""
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
            glucose_after = pdf.iloc[pos:pos + 25]['glucose'].values
            if np.isnan(glucose_after[:13]).sum() > 3:
                continue

            row = pdf.iloc[pos]
            isf = row.get('scheduled_isf', 50)
            cr = row.get('scheduled_cr', 10)
            basal = row.get('scheduled_basal_rate', 1.0)

            corrections.append({
                'patient_id': pid,
                'bolus': float(row['bolus']),
                'glucose_start': float(row['glucose']),
                'iob_start': float(row.get('iob', 0)),
                'isf': float(isf) if not pd.isna(isf) else 50.0,
                'cr': float(cr) if not pd.isna(cr) else 10.0,
                'basal': float(basal) if not pd.isna(basal) else 1.0,
                'glucose_trajectory': [float(x) if not pd.isna(x) else np.nan
                                       for x in glucose_after],
                'hour': float(row.get('hour', 12)),
            })
            count += 1
    return corrections


def run_sim_with_counter_reg(corr, k_value, symmetric=False):
    """Run forward sim with monkey-patched counter-regulation.

    We patch the integration loop by intercepting the glucose update.
    The approach: run the sim normally, then apply counter-regulation
    as a post-hoc correction to the trajectory.

    Actually, for proper integration we need to modify the dBG calculation.
    Since forward_simulate doesn't support counter-regulation natively,
    we'll implement a mini-sim that matches the production code but adds
    the counter-reg term.
    """
    settings = TherapySettings(
        isf=corr['isf'],
        cr=corr['cr'],
        basal_rate=corr['basal'],
        dia_hours=5.0,
    )

    # Duration: 2.5h (enough for 2h horizon + buffer)
    duration_h = 2.5
    n_steps = int(duration_h * _STEPS_PER_HOUR)

    bolus_events = [InsulinEvent(time_minutes=0.0, units=corr['bolus'])]

    if k_value == 0.0:
        # No counter-regulation: use standard sim
        result = forward_simulate(
            initial_glucose=corr['glucose_start'],
            settings=settings,
            duration_hours=duration_h,
            start_hour=corr['hour'],
            bolus_events=bolus_events,
            initial_iob=corr['iob_start'],
        )
        return result.glucose[:n_steps]

    # With counter-regulation: run standard sim, then apply post-hoc
    # correction iteratively. This is an approximation — the counter-reg
    # would ideally be inside the integration loop, but monkey-patching
    # the loop is fragile. Instead we use a simple iterative approach:
    #
    # Step 1: Run baseline sim (k=0)
    # Step 2: At each step, compute dBG from sim
    # Step 3: Apply counter-regulation: if dBG < 0, add k×|dBG|
    # Step 4: Build corrected trajectory

    result = forward_simulate(
        initial_glucose=corr['glucose_start'],
        settings=settings,
        duration_hours=duration_h,
        start_hour=corr['hour'],
        bolus_events=bolus_events,
        initial_iob=corr['iob_start'],
    )

    raw_glucose = result.glucose[:n_steps].copy()
    corrected = np.zeros(n_steps)
    corrected[0] = raw_glucose[0]

    for t in range(1, n_steps):
        # Raw dBG from sim
        raw_dBG = raw_glucose[t] - raw_glucose[t - 1]

        # Scale dBG relative to corrected trajectory position
        # (corrected trajectory diverges from raw, so we scale proportionally)
        if t >= 2:
            corrected_dBG = corrected[t - 1] - corrected[t - 2]
        else:
            corrected_dBG = raw_dBG

        # Apply counter-regulation
        if symmetric:
            # Oppose both drops and rises
            counter_reg = -k_value * corrected_dBG
        else:
            # Only oppose drops (glucagon-like)
            if corrected_dBG < 0:
                counter_reg = -k_value * corrected_dBG  # positive
            else:
                counter_reg = 0.0

        # Use the raw sim's dBG (physics-driven) plus counter-reg correction
        effective_dBG = raw_dBG + counter_reg

        corrected[t] = np.clip(corrected[t - 1] + effective_dBG, 40, 400)

    return corrected


def evaluate_k(corrections, k_value, symmetric=False):
    """Evaluate a k value across all corrections at all horizons."""
    ratios = {h: [] for h in HORIZONS}
    maes = {h: [] for h in HORIZONS}

    for corr in corrections:
        sim_glucose = run_sim_with_counter_reg(corr, k_value, symmetric)
        actual_traj = corr['glucose_trajectory']

        for h in HORIZONS:
            if h >= len(actual_traj) or np.isnan(actual_traj[h]):
                continue

            actual_delta = actual_traj[h] - corr['glucose_start']
            sim_delta = sim_glucose[h] - corr['glucose_start']

            if abs(sim_delta) > 1:
                ratios[h].append(actual_delta / sim_delta)

            maes[h].append(abs(actual_delta - (sim_glucose[h] - corr['glucose_start'])))

    results = {}
    for h in HORIZONS:
        h_min = h * 5
        if ratios[h]:
            results[f'{h_min}min_ratio_mean'] = float(np.mean(ratios[h]))
            results[f'{h_min}min_ratio_median'] = float(np.median(ratios[h]))
            results[f'{h_min}min_mae'] = float(np.mean(maes[h]))
            results[f'{h_min}min_n'] = len(ratios[h])
    return results


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2579: Derivative-Dependent Counter-Regulation Model")
    print("=" * 70)

    # Load data
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    print(f"\nLoading {grid_path}...")
    df = pd.read_parquet(grid_path)
    print(f"  Shape: {df.shape}")

    # Extract corrections
    print("\nExtracting pure correction events...")
    corrections = extract_corrections(df)
    print(f"  Found {len(corrections)} corrections across {len(NS_PATIENTS)} NS patients")

    # Patient breakdown
    by_patient = {}
    for c in corrections:
        by_patient.setdefault(c['patient_id'], []).append(c)
    for pid in sorted(by_patient):
        print(f"    {pid}: {len(by_patient[pid])} corrections")

    # Evaluate all k × symmetric combinations
    all_results = []
    print("\n" + "-" * 70)
    print("Sweeping k and symmetric options...")
    print("-" * 70)

    for symmetric in SYMMETRIC_OPTIONS:
        sym_label = "symmetric" if symmetric else "glucagon-only"
        for k in K_GRID:
            print(f"\n  k={k:.1f} ({sym_label})...", end=" ", flush=True)
            result = evaluate_k(corrections, k, symmetric)
            result['k'] = k
            result['symmetric'] = symmetric
            all_results.append(result)

            # Print summary
            r2h = result.get('120min_ratio_mean', -1)
            mae2h = result.get('120min_mae', -1)
            print(f"ratio@2h={r2h:.3f}, MAE@2h={mae2h:.1f}")

    # Find best configuration
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    # Best by ratio closest to 1.0 at 2h
    valid_results = [r for r in all_results if '120min_ratio_mean' in r]
    best_ratio = min(valid_results, key=lambda r: abs(r['120min_ratio_mean'] - 1.0))
    best_mae = min(valid_results, key=lambda r: r.get('120min_mae', 999))

    print(f"\nBest by ratio@2h (closest to 1.0):")
    print(f"  k={best_ratio['k']:.1f}, symmetric={best_ratio['symmetric']}")
    for h in HORIZONS:
        h_min = h * 5
        key = f'{h_min}min_ratio_mean'
        if key in best_ratio:
            print(f"    {h_min}min: ratio={best_ratio[key]:.3f}, "
                  f"MAE={best_ratio[f'{h_min}min_mae']:.1f}, "
                  f"n={best_ratio[f'{h_min}min_n']}")

    print(f"\nBest by MAE@2h:")
    print(f"  k={best_mae['k']:.1f}, symmetric={best_mae['symmetric']}")
    for h in HORIZONS:
        h_min = h * 5
        key = f'{h_min}min_ratio_mean'
        if key in best_mae:
            print(f"    {h_min}min: ratio={best_mae[key]:.3f}, "
                  f"MAE={best_mae[f'{h_min}min_mae']:.1f}, "
                  f"n={best_mae[f'{h_min}min_n']}")

    # Baseline (k=0) for comparison
    baseline = [r for r in all_results if r['k'] == 0.0 and not r['symmetric']][0]
    print(f"\nBaseline (k=0, no counter-reg):")
    for h in HORIZONS:
        h_min = h * 5
        key = f'{h_min}min_ratio_mean'
        if key in baseline:
            print(f"    {h_min}min: ratio={baseline[key]:.3f}, "
                  f"MAE={baseline[f'{h_min}min_mae']:.1f}")

    # Per-patient analysis with best k
    print("\n" + "-" * 70)
    print(f"Per-patient analysis with best k={best_ratio['k']:.1f}, "
          f"symmetric={best_ratio['symmetric']}")
    print("-" * 70)

    per_patient = {}
    for pid in sorted(by_patient):
        patient_corrs = by_patient[pid]
        result = evaluate_k(patient_corrs, best_ratio['k'], best_ratio['symmetric'])
        per_patient[pid] = result
        r2h = result.get('120min_ratio_mean', -1)
        mae2h = result.get('120min_mae', -1)
        n = result.get('120min_n', 0)
        print(f"  {pid}: ratio@2h={r2h:.3f}, MAE@2h={mae2h:.1f}, n={n}")

    # Improvement calculation
    baseline_ratio = baseline.get('120min_ratio_mean', 0)
    best_ratio_val = best_ratio.get('120min_ratio_mean', 0)
    improvement = abs(best_ratio_val - 1.0) - abs(baseline_ratio - 1.0)
    pct_improvement = (1 - abs(best_ratio_val - 1.0) / abs(baseline_ratio - 1.0)) * 100

    print(f"\n{'=' * 70}")
    print(f"CONCLUSION")
    print(f"{'=' * 70}")
    print(f"Baseline ratio@2h: {baseline_ratio:.3f} (deviation from 1.0: {abs(baseline_ratio-1.0):.3f})")
    print(f"Best ratio@2h:     {best_ratio_val:.3f} (deviation from 1.0: {abs(best_ratio_val-1.0):.3f})")
    print(f"Improvement:       {pct_improvement:.1f}%")

    if abs(best_ratio_val - 1.0) < 0.3:
        verdict = "CONFIRMED"
        print(f"\n✓ HYPOTHESIS CONFIRMED: Counter-regulation brings ratio within 0.7-1.3")
    elif pct_improvement > 30:
        verdict = "PARTIAL"
        print(f"\n~ PARTIAL: Substantial improvement but ratio still outside 0.7-1.3")
    else:
        verdict = "NOT CONFIRMED"
        print(f"\n✗ NOT CONFIRMED: Counter-regulation insufficient to fix overestimation")

    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.0f}s")

    # Save results
    output = {
        'experiment': 'EXP-2579',
        'title': 'Derivative-dependent counter-regulation model',
        'hypothesis': 'Adding glucose-rate-dependent opposing force reduces 2.5x overestimation',
        'verdict': verdict,
        'n_corrections': len(corrections),
        'patients': list(by_patient.keys()),
        'k_grid': K_GRID,
        'symmetric_options': SYMMETRIC_OPTIONS,
        'horizons_steps': HORIZONS,
        'all_results': all_results,
        'best_by_ratio': best_ratio,
        'best_by_mae': best_mae,
        'baseline': baseline,
        'improvement_pct': pct_improvement,
        'per_patient_best_k': per_patient,
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2579_counter_regulation.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
