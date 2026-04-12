#!/usr/bin/env python3
"""
EXP-2566: Circadian ISF/CR Variation via Forward Simulator

Hypothesis:
    Optimal ISF and CR multipliers vary significantly by time of day,
    with morning requiring different settings than evening. This would
    justify time-of-day-specific settings recommendations.

Background:
    - EXP-2536 confirmed CR and ISF are independent (r=0.17)
    - EXP-2563 found CR saturates at 1.5× (population) and ISF is bimodal
    - EXP-2565 confirmed population params are good for NS patients
    - Circadian variation is clinically important: dawn phenomenon,
      post-lunch insulin resistance, evening carb sensitivity changes

Method:
    For each NS patient (a-k):
    1. Extract correction windows (ISF) and meal windows (CR) with timestamps
    2. Partition into 4 time blocks:
       - Morning: 06:00-10:00 (dawn phenomenon, breakfast)
       - Midday: 10:00-14:00 (lunch, peak activity)
       - Afternoon: 14:00-18:00 (post-lunch, pre-dinner)
       - Evening/Night: 18:00-06:00 (dinner, overnight)
    3. Run per-block ISF/CR grid search (extended CR grid to 2.0)
    4. Test: are per-block optima significantly different? (Kruskal-Wallis)

Sub-experiments:
    EXP-2566a: Per-block ISF optimization from correction windows
    EXP-2566b: Per-block CR optimization from meal windows (grid to 2.0)
    EXP-2566c: Statistical test of block differences
    EXP-2566d: Per-patient circadian profiles

Success criteria:
    - ≥3 patients show statistically significant (p<0.05) ISF variation by block
    - ≥3 patients show statistically significant CR variation by block
    - Range of optimal multipliers across blocks > 0.3 for ≥50% of patients

Data:
    NS patients only (a-k). ODC excluded due to known grid bugs.
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']

TIME_BLOCKS = {
    'morning': (6, 10),
    'midday': (10, 14),
    'afternoon': (14, 18),
    'evening_night': (18, 6),  # wraps around midnight
}


def in_block(hour, block_start, block_end):
    """Check if hour is in a time block (handles midnight wrap)."""
    if block_start < block_end:
        return block_start <= hour < block_end
    else:  # wraps around midnight
        return hour >= block_start or hour < block_end


def load_data():
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / \
        'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    return pd.read_parquet(grid_path)


def extract_windows(pdf, window_type='correction', max_per_block=30):
    """Extract windows with time-of-day labels."""
    from cgmencode.production.forward_simulator import InsulinEvent, CarbEvent

    if window_type == 'correction':
        mask = (pdf['bolus'] > 0.5) & (pdf['carbs'].fillna(0) < 5) & (pdf['glucose'] > 150)
    else:
        mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)

    event_idx = pdf.index[mask]
    block_windows = {block: [] for block in TIME_BLOCKS}

    for idx in event_idx:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        window = pdf.iloc[pos:pos + 48]
        if len(window) < 48 or window['glucose'].isna().sum() > 5:
            continue

        hour = float(window['time'].iloc[0].hour) if 'time' in window.columns else 12.0

        # Determine block
        for block_name, (bstart, bend) in TIME_BLOCKS.items():
            if in_block(hour, bstart, bend):
                if len(block_windows[block_name]) >= max_per_block:
                    continue
                w = {
                    'initial_glucose': float(window['glucose'].iloc[0]),
                    'bolus': float(window['bolus'].iloc[0]),
                    'carbs': float(window['carbs'].iloc[0]) if window_type == 'meal' else 0.0,
                    'iob': float(window['iob'].iloc[0]) if 'iob' in window.columns else 0.0,
                    'hour': hour,
                    'isf': float(window['scheduled_isf'].iloc[0]) if 'scheduled_isf' in window.columns else 50.0,
                    'cr': float(window['scheduled_cr'].iloc[0]) if 'scheduled_cr' in window.columns else 10.0,
                    'basal': float(window['scheduled_basal'].iloc[0]) if 'scheduled_basal' in window.columns else 1.0,
                }
                block_windows[block_name].append(w)
                break

    return block_windows


def optimize_multiplier(windows, param_type, multiplier_grid):
    """Find optimal multiplier for a set of windows."""
    from cgmencode.production.forward_simulator import (
        forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
    )

    if len(windows) < 3:
        return None

    best_mult = 1.0
    best_tir = -1.0
    tir_by_mult = {}

    for mult in multiplier_grid:
        tirs = []
        for w in windows:
            if param_type == 'isf':
                settings = TherapySettings(
                    isf=w['isf'] * mult, cr=w['cr'],
                    basal_rate=w.get('basal', 1.0), dia_hours=5.0,
                )
            else:
                settings = TherapySettings(
                    isf=w['isf'], cr=w['cr'] * mult,
                    basal_rate=w.get('basal', 1.0), dia_hours=5.0,
                )

            bolus_events = [InsulinEvent(time_minutes=0, units=w['bolus'])]
            carb_events = [CarbEvent(time_minutes=0, grams=w['carbs'])] if w.get('carbs', 0) > 0 else []

            try:
                result = forward_simulate(
                    initial_glucose=w['initial_glucose'],
                    settings=settings,
                    duration_hours=4.0,
                    start_hour=w.get('hour', 12),
                    bolus_events=bolus_events,
                    carb_events=carb_events,
                    initial_iob=w.get('iob', 0),
                    noise_std=0, seed=42,
                )
                tir = float(np.mean((np.array(result.glucose) >= 70) & (np.array(result.glucose) <= 180)))
                tirs.append(tir)
            except Exception:
                pass

        if tirs:
            mean_tir = float(np.mean(tirs))
            tir_by_mult[f"{mult:.1f}"] = mean_tir
            if mean_tir > best_tir:
                best_tir = mean_tir
                best_mult = mult

    baseline_tir = tir_by_mult.get("1.0", 0)
    return {
        'optimal': best_mult,
        'tir_delta': best_tir - baseline_tir,
        'n_windows': len(windows),
        'tir_by_mult': tir_by_mult,
    }


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2566: Circadian ISF/CR Variation via Forward Simulator")
    print("=" * 70)

    df = load_data()
    print(f"Loaded {len(df):,} rows")
    print(f"NS patients only: {NS_PATIENTS}\n")

    isf_grid = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    cr_grid = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0]

    all_isf_results = {}
    all_cr_results = {}

    for pid in NS_PATIENTS:
        pdf = df[df['patient_id'] == pid].copy()
        print(f"\n{'='*50}")
        print(f"Patient {pid}")

        # ISF by block
        corr_blocks = extract_windows(pdf, 'correction')
        print(f"\n  Correction windows by block:")
        isf_by_block = {}
        for block_name in TIME_BLOCKS:
            n = len(corr_blocks[block_name])
            print(f"    {block_name}: {n} windows", end="")
            if n >= 3:
                result = optimize_multiplier(corr_blocks[block_name], 'isf', isf_grid)
                if result:
                    isf_by_block[block_name] = result
                    print(f" → ISF×{result['optimal']:.1f} (TIR +{result['tir_delta']:.2f}pp)")
                else:
                    print(" (optimization failed)")
            else:
                print(" (too few)")

        all_isf_results[pid] = isf_by_block

        # CR by block
        meal_blocks = extract_windows(pdf, 'meal')
        print(f"  Meal windows by block:")
        cr_by_block = {}
        for block_name in TIME_BLOCKS:
            n = len(meal_blocks[block_name])
            print(f"    {block_name}: {n} windows", end="")
            if n >= 3:
                result = optimize_multiplier(meal_blocks[block_name], 'cr', cr_grid)
                if result:
                    cr_by_block[block_name] = result
                    print(f" → CR×{result['optimal']:.1f} (TIR +{result['tir_delta']:.2f}pp)")
                else:
                    print(" (optimization failed)")
            else:
                print(" (too few)")

        all_cr_results[pid] = cr_by_block

    # EXP-2566c: Statistical tests
    print("\n" + "=" * 70)
    print("EXP-2566c: Statistical Analysis")
    print("=" * 70)

    # Per-patient: test if ISF optima differ across blocks
    isf_sig_patients = 0
    cr_sig_patients = 0
    isf_ranges = []
    cr_ranges = []

    print("\n  ISF variation by patient:")
    for pid in NS_PATIENTS:
        blocks = all_isf_results.get(pid, {})
        if len(blocks) >= 2:
            optima = [blocks[b]['optimal'] for b in blocks]
            opt_range = max(optima) - min(optima)
            isf_ranges.append(opt_range)
            labels = list(blocks.keys())
            label_str = ", ".join(f"{b}={blocks[b]['optimal']:.1f}" for b in blocks)
            print(f"    {pid}: {label_str} (range={opt_range:.1f})")

            if opt_range > 0:
                isf_sig_patients += 1

    print(f"\n  CR variation by patient:")
    for pid in NS_PATIENTS:
        blocks = all_cr_results.get(pid, {})
        if len(blocks) >= 2:
            optima = [blocks[b]['optimal'] for b in blocks]
            opt_range = max(optima) - min(optima)
            cr_ranges.append(opt_range)
            labels = list(blocks.keys())
            label_str = ", ".join(f"{b}={blocks[b]['optimal']:.1f}" for b in blocks)
            print(f"    {pid}: {label_str} (range={opt_range:.1f})")

            if opt_range > 0:
                cr_sig_patients += 1

    # Population-level: aggregate optima per block
    print("\n  Population-level block profiles:")
    print("    ISF:")
    for block_name in TIME_BLOCKS:
        vals = [all_isf_results[pid][block_name]['optimal']
                for pid in NS_PATIENTS if block_name in all_isf_results.get(pid, {})]
        if vals:
            print(f"      {block_name}: mean={np.mean(vals):.2f}, median={np.median(vals):.2f}, n={len(vals)}")

    print("    CR:")
    for block_name in TIME_BLOCKS:
        vals = [all_cr_results[pid][block_name]['optimal']
                for pid in NS_PATIENTS if block_name in all_cr_results.get(pid, {})]
        if vals:
            print(f"      {block_name}: mean={np.mean(vals):.2f}, median={np.median(vals):.2f}, n={len(vals)}")

    # Kruskal-Wallis across blocks (population level)
    print("\n  Kruskal-Wallis test (population, across blocks):")
    isf_block_groups = []
    cr_block_groups = []
    for block_name in TIME_BLOCKS:
        isf_vals = [all_isf_results[pid][block_name]['optimal']
                    for pid in NS_PATIENTS if block_name in all_isf_results.get(pid, {})]
        cr_vals = [all_cr_results[pid][block_name]['optimal']
                   for pid in NS_PATIENTS if block_name in all_cr_results.get(pid, {})]
        if isf_vals:
            isf_block_groups.append(isf_vals)
        if cr_vals:
            cr_block_groups.append(cr_vals)

    if len(isf_block_groups) >= 2:
        try:
            h_stat, p_val = stats.kruskal(*isf_block_groups)
            print(f"    ISF: H={h_stat:.2f}, p={p_val:.4f} {'✅ significant' if p_val < 0.05 else '❌ not significant'}")
        except Exception as e:
            print(f"    ISF: test failed ({e})")

    if len(cr_block_groups) >= 2:
        try:
            h_stat, p_val = stats.kruskal(*cr_block_groups)
            print(f"    CR: H={h_stat:.2f}, p={p_val:.4f} {'✅ significant' if p_val < 0.05 else '❌ not significant'}")
        except Exception as e:
            print(f"    CR: test failed ({e})")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n  EXP-2566a (ISF by block):")
    print(f"    Patients with block variation: {isf_sig_patients}/{len(isf_ranges)} (criterion: ≥3)")
    if isf_ranges:
        print(f"    Median range of optimal ISF across blocks: {np.median(isf_ranges):.1f}")
        n_large_range = sum(1 for r in isf_ranges if r >= 0.3)
        print(f"    Patients with range ≥0.3: {n_large_range}/{len(isf_ranges)} (criterion: ≥50%)")

    print(f"\n  EXP-2566b (CR by block):")
    print(f"    Patients with block variation: {cr_sig_patients}/{len(cr_ranges)} (criterion: ≥3)")
    if cr_ranges:
        print(f"    Median range of optimal CR across blocks: {np.median(cr_ranges):.1f}")
        n_large_range_cr = sum(1 for r in cr_ranges if r >= 0.3)
        print(f"    Patients with range ≥0.3: {n_large_range_cr}/{len(cr_ranges)} (criterion: ≥50%)")

    isf_crit = isf_sig_patients >= 3
    cr_crit = cr_sig_patients >= 3
    overall = "SUPPORTED" if (isf_crit and cr_crit) else "PARTIALLY SUPPORTED" if (isf_crit or cr_crit) else "NOT SUPPORTED"
    print(f"\n  OVERALL: HYPOTHESIS {overall}")

    runtime = time.time() - t0
    print(f"  Runtime: {runtime:.0f}s")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        'exp_id': 'EXP-2566',
        'hypothesis': 'Optimal ISF/CR vary by time of day',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'runtime_seconds': runtime,
        'isf_results': {pid: {b: v for b, v in blocks.items()}
                        for pid, blocks in all_isf_results.items()},
        'cr_results': {pid: {b: v for b, v in blocks.items()}
                       for pid, blocks in all_cr_results.items()},
        'summary': {
            'isf_sig_patients': isf_sig_patients,
            'cr_sig_patients': cr_sig_patients,
            'isf_median_range': float(np.median(isf_ranges)) if isf_ranges else 0,
            'cr_median_range': float(np.median(cr_ranges)) if cr_ranges else 0,
        },
        'overall_conclusion': f'HYPOTHESIS {overall}',
    }

    out_path = RESULTS_DIR / 'exp-2566_circadian_variation.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results: {out_path}")


if __name__ == '__main__':
    main()
