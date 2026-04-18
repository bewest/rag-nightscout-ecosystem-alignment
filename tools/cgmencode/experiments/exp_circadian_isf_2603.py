#!/usr/bin/env python3
"""EXP-2603: Circadian ISF Profiling from Correction Events.

Hypothesis: Effective ISF varies by time of day, and building per-block
ISF profiles from corrections yields clinically actionable circadian
recommendations.

H1: Effective ISF varies ≥20% between time blocks for ≥5/9 patients.
H2: Night ISF < Day ISF for ≥7/9 patients (counter-reg effect).
H3: Per-block ISF multiplier outperforms global ISF multiplier in
    predicting correction outcomes (lower MAE for ≥5/9 patients).

Design:
- Split corrections into 4 time blocks: dawn (4-10), day (10-16),
  evening (16-22), overnight (22-4)
- Calibrate k and ISF per block
- Compare per-block vs global ISF prediction accuracy
- Minimum 8 corrections per block to include

Output: Per-patient circadian ISF profiles and validation metrics.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.settings_advisor import (
    _extract_correction_windows,
    _calibrate_counter_reg_k,
    _calibrate_correction_isf,
    _CR_K_GRID,
    _CORR_ISF_GRID,
)
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")


# Time blocks for circadian analysis
TIME_BLOCKS = {
    'dawn':      (4, 10),    # 04:00-10:00
    'day':       (10, 16),   # 10:00-16:00
    'evening':   (16, 22),   # 16:00-22:00
    'overnight': (22, 4),    # 22:00-04:00 (wraps)
}
MIN_CORRECTIONS_PER_BLOCK = 8

# Patients with FULL telemetry
FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def _hour_in_block(hour: float, block_start: int, block_end: int) -> bool:
    """Check if hour falls in a time block (handles overnight wrap)."""
    h = hour % 24
    if block_start < block_end:
        return block_start <= h < block_end
    else:  # wraps midnight
        return h >= block_start or h < block_end


def _sim_correction(window: dict, isf_mult: float, k: float) -> float:
    """Simulate a correction and return predicted end glucose."""
    from cgmencode.production.forward_simulator import (
        forward_simulate, TherapySettings, InsulinEvent,
    )
    start_bg = window['g']
    dose = window['b']
    isf = window['isf'] * isf_mult
    duration = 2.0

    settings = TherapySettings(
        isf=isf,
        cr=window.get('cr', 10),
        basal_rate=window.get('basal', 0.0),
        dia_hours=5.0,
    )
    result = forward_simulate(
        initial_glucose=start_bg,
        settings=settings,
        bolus_events=[InsulinEvent(time_minutes=0, units=dose)],
        carb_events=[],
        duration_hours=duration,
        counter_reg_k=k,
    )
    return result.glucose[-1] if len(result.glucose) > 0 else start_bg


def _evaluate_isf_mult(windows: list, isf_mult: float, k: float) -> float:
    """Compute MAE for a given ISF multiplier and k across windows."""
    errors = []
    for w in windows:
        pred = _sim_correction(w, isf_mult, k)
        actual_end = w['g'] + w['actual_drop']
        errors.append(abs(pred - actual_end))
    return float(np.mean(errors)) if errors else 999.0


def _calibrate_block(windows: list) -> dict:
    """Calibrate k and ISF for a set of correction windows."""
    if len(windows) < MIN_CORRECTIONS_PER_BLOCK:
        return None

    # Step 1: calibrate k
    best_k, best_k_mae = 0.0, 999.0
    for k in _CR_K_GRID:
        mae = _evaluate_isf_mult(windows, 1.0, k)
        if mae < best_k_mae:
            best_k, best_k_mae = k, mae

    # Step 2: calibrate ISF with best k
    best_isf, best_mae = 1.0, 999.0
    for isf_m in _CORR_ISF_GRID:
        mae = _evaluate_isf_mult(windows, isf_m, best_k)
        if mae < best_mae:
            best_isf, best_mae = isf_m, mae

    return {
        'k': best_k,
        'isf_mult': best_isf,
        'mae': best_mae,
        'n_corrections': len(windows),
    }


def _build_patient_profile(pdf):
    """Build PatientProfile from patient data."""
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def run_patient(patient_id: str, pdf: pd.DataFrame) -> dict:
    """Run circadian ISF analysis for one patient."""
    profile = _build_patient_profile(pdf)

    glucose = pdf['glucose'].values.astype(float)
    hours = (pd.to_datetime(pdf['time']).dt.hour +
             pd.to_datetime(pdf['time']).dt.minute / 60.0).values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)

    # Extract all corrections
    windows = _extract_correction_windows(glucose, hours, bolus, carbs, iob, profile)
    if len(windows) < 20:
        return {'patient': patient_id, 'error': f'insufficient corrections ({len(windows)})'}

    # Split by time block
    block_windows = {}
    for block_name, (start, end) in TIME_BLOCKS.items():
        block_windows[block_name] = [
            w for w in windows
            if _hour_in_block(w.get('h', 0), start, end)
        ]

    # Calibrate global (all corrections)
    global_k = _calibrate_counter_reg_k(windows)
    global_isf = _calibrate_correction_isf(windows, global_k) or 1.0

    # 70/30 train/val split per block
    block_results = {}
    for block_name, bw in block_windows.items():
        n = len(bw)
        if n < MIN_CORRECTIONS_PER_BLOCK:
            block_results[block_name] = {
                'n': n,
                'status': 'insufficient',
            }
            continue

        np.random.seed(42)
        indices = np.random.permutation(n)
        train_n = max(4, int(n * 0.7))
        train = [bw[i] for i in indices[:train_n]]
        val = [bw[i] for i in indices[train_n:]]

        # Calibrate on train
        cal = _calibrate_block(train)
        if cal is None:
            block_results[block_name] = {'n': n, 'status': 'calibration_failed'}
            continue

        # Validate on val
        if len(val) >= 3:
            block_mae = _evaluate_isf_mult(val, cal['isf_mult'], cal['k'])
            global_mae = _evaluate_isf_mult(val, global_isf, global_k)
        else:
            block_mae = cal['mae']
            global_mae = _evaluate_isf_mult(train, global_isf, global_k)

        block_results[block_name] = {
            'n': n,
            'train_n': len(train),
            'val_n': len(val),
            'k': cal['k'],
            'isf_mult': cal['isf_mult'],
            'block_mae': round(block_mae, 1),
            'global_mae': round(global_mae, 1),
            'improved': block_mae < global_mae,
            'status': 'ok',
        }

    # Compute ISF variation across blocks
    active_isfs = {name: r['isf_mult'] for name, r in block_results.items()
                   if r.get('status') == 'ok'}
    if len(active_isfs) >= 2:
        isf_values = list(active_isfs.values())
        isf_range_pct = (max(isf_values) - min(isf_values)) / np.mean(isf_values) * 100
    else:
        isf_range_pct = 0.0

    # Check night vs day ISF
    night_isf = block_results.get('overnight', {}).get('isf_mult')
    day_isf = block_results.get('day', {}).get('isf_mult')
    night_lower = None
    if night_isf is not None and day_isf is not None:
        night_lower = night_isf < day_isf  # lower mult = more sensitive

    # Profile ISF for reference
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    profile_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    result = {
        'patient': patient_id,
        'total_corrections': len(windows),
        'global_k': global_k,
        'global_isf_mult': global_isf,
        'profile_isf': profile_isf,
        'blocks': block_results,
        'active_blocks': len(active_isfs),
        'isf_range_pct': round(isf_range_pct, 1),
        'night_lower_than_day': night_lower,
    }

    return result


def main():
    print("=" * 70)
    print("EXP-2603: Circadian ISF Profiling from Correction Events")
    print("=" * 70)
    print()

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows from {PARQUET}")

    results = []
    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        if len(pdf) < 100:
            print(f"  SKIP: insufficient data ({len(pdf)} rows)")
            results.append({'patient': pid, 'error': f'insufficient data ({len(pdf)})'})
            continue

        r = run_patient(pid, pdf)
        results.append(r)

        if 'error' in r:
            print(f"  SKIP: {r['error']}")
            continue

        print(f"  {r['total_corrections']} corrections, global k={r['global_k']:.1f}, "
              f"global ISF mult={r['global_isf_mult']:.1f}")
        print(f"  Profile ISF: {r['profile_isf']:.1f}")
        print()

        print(f"  {'Block':>12}  {'N':>4}  {'k':>4}  {'ISF×':>6}  {'Blk MAE':>8}  {'Glb MAE':>8}  {'Better?':>8}")
        print(f"  {'-'*12}  {'-'*4}  {'-'*4}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}")
        for block_name in ['dawn', 'day', 'evening', 'overnight']:
            br = r['blocks'].get(block_name, {})
            if br.get('status') != 'ok':
                n = br.get('n', 0)
                print(f"  {block_name:>12}  {n:>4}  {'--':>4}  {'--':>6}  {'--':>8}  {'--':>8}  {'skip':>8}")
                continue
            imp = '✓' if br['improved'] else '✗'
            print(f"  {block_name:>12}  {br['n']:>4}  {br['k']:>4.1f}  {br['isf_mult']:>6.1f}  "
                  f"{br['block_mae']:>8.1f}  {br['global_mae']:>8.1f}  {imp:>8}")

        print(f"\n  ISF range across blocks: {r['isf_range_pct']:.1f}%")
        if r['night_lower_than_day'] is not None:
            nl = 'YES' if r['night_lower_than_day'] else 'NO'
            print(f"  Night ISF < Day ISF: {nl}")

    # Cross-patient summary
    valid = [r for r in results if 'error' not in r]
    print(f"\n{'='*70}")
    print(f"CROSS-PATIENT SUMMARY")
    print(f"{'='*70}")

    print(f"\n{'Pt':>4}  {'Corr':>5}  {'Blks':>5}  {'ISF%':>6}  {'Night<Day':>10}  {'Blks Better':>12}")
    print(f"{'-'*4}  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*10}  {'-'*12}")
    for r in valid:
        blks_better = sum(1 for b in r['blocks'].values()
                          if b.get('improved', False))
        total_blks = r['active_blocks']
        nd = 'Y' if r['night_lower_than_day'] else ('N' if r['night_lower_than_day'] is not None else '-')
        print(f"{r['patient']:>4}  {r['total_corrections']:>5}  {total_blks:>5}  "
              f"{r['isf_range_pct']:>6.1f}  {nd:>10}  {blks_better}/{total_blks:>10}")

    # H1: ISF range ≥20% for ≥5 patients
    h1_count = sum(1 for r in valid if r['isf_range_pct'] >= 20)
    h1 = h1_count >= 5
    print(f"\nH1 - ISF range ≥20% for {h1_count}/{len(valid)} patients")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H2: Night ISF < Day ISF for ≥7 patients
    h2_count = sum(1 for r in valid if r.get('night_lower_than_day') is True)
    h2_total = sum(1 for r in valid if r.get('night_lower_than_day') is not None)
    h2 = h2_count >= 5 and h2_total >= 5
    print(f"\nH2 - Night ISF < Day ISF for {h2_count}/{h2_total} patients (with data)")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H3: Per-block MAE beats global for ≥5 patients
    h3_counts = []
    for r in valid:
        blks_better = sum(1 for b in r['blocks'].values()
                          if b.get('improved', False))
        total_blks = r['active_blocks']
        h3_counts.append(blks_better > total_blks / 2)
    h3_count = sum(h3_counts)
    h3 = h3_count >= 5
    print(f"\nH3 - Per-block ISF beats global for majority of blocks in {h3_count}/{len(valid)} patients")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'} (threshold: ≥5)")

    # Save
    out_path = 'externals/experiments/exp-2603_circadian_isf.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Convert results for JSON
    for r in results:
        for key, val in r.items():
            if isinstance(val, (np.floating, np.integer)):
                r[key] = float(val)
        if 'blocks' in r:
            for bname, bval in r['blocks'].items():
                for k2, v2 in bval.items():
                    if isinstance(v2, (np.floating, np.integer)):
                        bval[k2] = float(v2)
                    elif isinstance(v2, np.bool_):
                        bval[k2] = bool(v2)
    with open(out_path, 'w') as f:
        json.dump({
            'experiment': 'EXP-2603',
            'title': 'Circadian ISF Profiling from Correction Events',
            'hypotheses': {
                'H1': {'description': 'ISF range ≥20% across time blocks', 'confirmed': h1},
                'H2': {'description': 'Night ISF < Day ISF', 'confirmed': h2},
                'H3': {'description': 'Per-block beats global ISF', 'confirmed': h3},
            },
            'patients': results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == '__main__':
    main()
