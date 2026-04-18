#!/usr/bin/env python3
"""
EXP-2564: Forward Simulator Fidelity Validation

Hypothesis:
    Forward sim glucose traces correlate with actual CGM traces (r > 0.7)
    for 4-hour correction and meal windows, validating the digital twin
    as a basis for counterfactual reasoning.

Background:
    - EXP-2562 showed forward sim counterfactuals produce directionally
      consistent results (ISF+20% → +2.1pp TIR, CR+20% → +3.3pp TIR).
    - But we haven't validated that the sim TRAJECTORY matches reality.
    - If the sim is well-calibrated, its counterfactual predictions are
      trustworthy. If not, we know where to improve it.
    - The forward sim uses 2-component DIA (τ=0.8h/persistent), delayed
      carb absorption (gamma-like, peak at 20min), and power-law ISF.

Method:
    For each patient:
    1. Extract correction and meal windows with complete 4h CGM traces
    2. Run forward sim from same initial conditions (glucose, IOB, bolus,
       carbs, settings)
    3. Compare simulated vs actual glucose traces:
       a) Pearson correlation (shape agreement)
       b) MAE (absolute accuracy)
       c) TIR agreement (clinical relevance)
       d) Nadir/peak timing agreement (dynamics)
    4. Identify systematic biases (does sim over/under-predict?)

Sub-experiments:
    EXP-2564a: Correction window fidelity (ISF-dominated dynamics)
    EXP-2564b: Meal window fidelity (CR/carb absorption dynamics)
    EXP-2564c: Bias analysis (systematic over/under-prediction by zone)
    EXP-2564d: Per-patient calibration quality

Success criteria:
    - Median correlation r > 0.5 for correction windows
    - Median correlation r > 0.4 for meal windows (harder due to carb variability)
    - TIR agreement > 60% (same TIR classification in >60% of windows)
    - Nadir timing within ±30 minutes for >50% of correction windows
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'


@dataclass
class WindowFidelity:
    window_id: int
    window_type: str
    correlation: float
    mae: float
    actual_tir: float
    sim_tir: float
    tir_agrees: bool
    actual_nadir: float
    sim_nadir: float
    nadir_time_actual: int
    nadir_time_sim: int
    nadir_timing_error_min: int
    actual_peak: float
    sim_peak: float
    mean_bias: float  # sim - actual (positive = sim overestimates)
    initial_glucose: float


def load_data():
    """Load the training grid."""
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    df = pd.read_parquet(grid_path)
    return df


def extract_windows_with_traces(pdf, window_type='correction', max_windows=40):
    """Extract windows with full 4h glucose traces for comparison."""
    windows = []

    if window_type == 'correction':
        mask = (pdf['bolus'] > 0.5) & (pdf['carbs'].fillna(0) < 5) & (pdf['glucose'] > 150)
    else:  # meal
        mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)

    event_idx = pdf.index[mask]

    for idx in event_idx[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        window = pdf.iloc[pos:pos + 48]
        if len(window) < 48:
            continue

        glucose_trace = window['glucose'].values.astype(float)
        if np.isnan(glucose_trace).sum() > 5:
            continue

        # Interpolate small gaps
        if np.isnan(glucose_trace).any():
            valid = ~np.isnan(glucose_trace)
            if valid.sum() < 40:
                continue
            glucose_trace = np.interp(
                np.arange(len(glucose_trace)),
                np.where(valid)[0],
                glucose_trace[valid],
            )

        windows.append({
            'initial_glucose': float(glucose_trace[0]),
            'bolus': float(window['bolus'].iloc[0]),
            'carbs': float(window['carbs'].iloc[0]) if window_type == 'meal' else 0.0,
            'iob': float(window['iob'].iloc[0]) if 'iob' in window.columns else 0.0,
            'hour': float(window['time'].iloc[0].hour) if 'time' in window.columns else 12.0,
            'isf': float(window['scheduled_isf'].iloc[0]) if 'scheduled_isf' in window.columns else 50.0,
            'cr': float(window['scheduled_cr'].iloc[0]) if 'scheduled_cr' in window.columns else 10.0,
            'basal': float(window['scheduled_basal'].iloc[0]) if 'scheduled_basal' in window.columns else 1.0,
            'actual_glucose_trace': glucose_trace.tolist(),
        })
        if len(windows) >= max_windows:
            break

    return windows


def compare_traces(actual, simulated):
    """Compare actual vs simulated glucose traces."""
    actual = np.array(actual)
    simulated = np.array(simulated)

    # Resample simulated to match actual length (48 points = 4h at 5min)
    if len(simulated) != len(actual):
        sim_x = np.linspace(0, 1, len(simulated))
        act_x = np.linspace(0, 1, len(actual))
        simulated = np.interp(act_x, sim_x, simulated)

    # Correlation
    if np.std(actual) < 1e-6 or np.std(simulated) < 1e-6:
        corr = 0.0
    else:
        corr = float(np.corrcoef(actual, simulated)[0, 1])
        if np.isnan(corr):
            corr = 0.0

    # MAE
    mae = float(np.mean(np.abs(actual - simulated)))

    # TIR
    actual_tir = float(np.mean((actual >= 70) & (actual <= 180)))
    sim_tir = float(np.mean((simulated >= 70) & (simulated <= 180)))
    tir_agrees = abs(actual_tir - sim_tir) < 0.15  # within 15pp

    # Nadir (minimum)
    actual_nadir = float(np.min(actual))
    sim_nadir = float(np.min(simulated))
    nadir_time_actual = int(np.argmin(actual)) * 5  # minutes
    nadir_time_sim = int(np.argmin(simulated)) * 5
    nadir_timing_error = abs(nadir_time_actual - nadir_time_sim)

    # Peak (maximum)
    actual_peak = float(np.max(actual))
    sim_peak = float(np.max(simulated))

    # Bias
    mean_bias = float(np.mean(simulated - actual))

    return WindowFidelity(
        window_id=0,
        window_type='',
        correlation=corr,
        mae=mae,
        actual_tir=actual_tir,
        sim_tir=sim_tir,
        tir_agrees=tir_agrees,
        actual_nadir=actual_nadir,
        sim_nadir=sim_nadir,
        nadir_time_actual=nadir_time_actual,
        nadir_time_sim=nadir_time_sim,
        nadir_timing_error_min=nadir_timing_error,
        actual_peak=actual_peak,
        sim_peak=sim_peak,
        mean_bias=mean_bias,
        initial_glucose=float(actual[0]),
    )


def run_sim_for_window(w, window_type):
    """Run forward sim for a single window."""
    from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent, CarbEvent

    settings = TherapySettings(
        isf=w['isf'],
        cr=w['cr'],
        basal_rate=w.get('basal', 1.0),
        dia_hours=5.0,
    )

    bolus_events = [InsulinEvent(time_minutes=0, units=w['bolus'])] if w['bolus'] > 0 else []
    carb_events = [CarbEvent(time_minutes=0, grams=w['carbs'])] if w.get('carbs', 0) > 0 else []

    result = forward_simulate(
        initial_glucose=w['initial_glucose'],
        settings=settings,
        duration_hours=4.0,
        start_hour=w.get('hour', 12),
        bolus_events=bolus_events,
        carb_events=carb_events,
        initial_iob=w.get('iob', 0),
        noise_std=0,
        seed=42,
    )

    return result.glucose


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2564: Forward Simulator Fidelity Validation")
    print("=" * 70)

    df = load_data()
    patients = sorted(df['patient_id'].unique()) if 'patient_id' in df.columns else sorted(df.index.get_level_values(0).unique())
    print(f"Loaded {len(df):,} rows, {len(patients)} patients\n")

    # EXP-2564a: Correction fidelity
    print("--- EXP-2564a: Correction Window Fidelity ---")
    corr_fidelity = []
    per_patient_corr = {}

    for pid in patients:
        if 'patient_id' in df.columns:
            pdf = df[df['patient_id'] == pid].copy()
        else:
            pdf = df.loc[pid].copy()

        windows = extract_windows_with_traces(pdf, 'correction', max_windows=30)
        if len(windows) < 3:
            print(f"  {pid}: {len(windows)} windows (skipped)")
            continue

        patient_results = []
        for i, w in enumerate(windows):
            try:
                sim_trace = run_sim_for_window(w, 'correction')
                fid = compare_traces(w['actual_glucose_trace'], sim_trace)
                fid.window_id = i
                fid.window_type = 'correction'
                patient_results.append(fid)
            except Exception as e:
                pass

        if patient_results:
            median_r = np.median([f.correlation for f in patient_results])
            median_mae = np.median([f.mae for f in patient_results])
            tir_agree_pct = np.mean([f.tir_agrees for f in patient_results]) * 100
            median_bias = np.median([f.mean_bias for f in patient_results])
            corr_fidelity.extend(patient_results)
            per_patient_corr[pid] = {
                'n_windows': len(patient_results),
                'median_r': float(median_r),
                'median_mae': float(median_mae),
                'tir_agreement_pct': float(tir_agree_pct),
                'median_bias': float(median_bias),
            }
            print(f"  {pid}: {len(patient_results)} windows, r={median_r:.3f}, MAE={median_mae:.1f}, TIR agree={tir_agree_pct:.0f}%, bias={median_bias:+.1f}")

    if corr_fidelity:
        print(f"\n  Correction summary (n={len(corr_fidelity)}):")
        print(f"    Median r: {np.median([f.correlation for f in corr_fidelity]):.3f}")
        print(f"    Median MAE: {np.median([f.mae for f in corr_fidelity]):.1f} mg/dL")
        print(f"    TIR agreement: {np.mean([f.tir_agrees for f in corr_fidelity])*100:.0f}%")
        print(f"    Median bias: {np.median([f.mean_bias for f in corr_fidelity]):+.1f} mg/dL")
        nadir_30 = np.mean([f.nadir_timing_error_min <= 30 for f in corr_fidelity]) * 100
        print(f"    Nadir timing ≤30min: {nadir_30:.0f}%")

    # EXP-2564b: Meal fidelity
    print("\n--- EXP-2564b: Meal Window Fidelity ---")
    meal_fidelity = []
    per_patient_meal = {}

    for pid in patients:
        if 'patient_id' in df.columns:
            pdf = df[df['patient_id'] == pid].copy()
        else:
            pdf = df.loc[pid].copy()

        windows = extract_windows_with_traces(pdf, 'meal', max_windows=30)
        if len(windows) < 3:
            print(f"  {pid}: {len(windows)} windows (skipped)")
            continue

        patient_results = []
        for i, w in enumerate(windows):
            try:
                sim_trace = run_sim_for_window(w, 'meal')
                fid = compare_traces(w['actual_glucose_trace'], sim_trace)
                fid.window_id = i
                fid.window_type = 'meal'
                patient_results.append(fid)
            except Exception as e:
                pass

        if patient_results:
            median_r = np.median([f.correlation for f in patient_results])
            median_mae = np.median([f.mae for f in patient_results])
            tir_agree_pct = np.mean([f.tir_agrees for f in patient_results]) * 100
            median_bias = np.median([f.mean_bias for f in patient_results])
            meal_fidelity.extend(patient_results)
            per_patient_meal[pid] = {
                'n_windows': len(patient_results),
                'median_r': float(median_r),
                'median_mae': float(median_mae),
                'tir_agreement_pct': float(tir_agree_pct),
                'median_bias': float(median_bias),
            }
            print(f"  {pid}: {len(patient_results)} windows, r={median_r:.3f}, MAE={median_mae:.1f}, TIR agree={tir_agree_pct:.0f}%, bias={median_bias:+.1f}")

    if meal_fidelity:
        print(f"\n  Meal summary (n={len(meal_fidelity)}):")
        print(f"    Median r: {np.median([f.correlation for f in meal_fidelity]):.3f}")
        print(f"    Median MAE: {np.median([f.mae for f in meal_fidelity]):.1f} mg/dL")
        print(f"    TIR agreement: {np.mean([f.tir_agrees for f in meal_fidelity])*100:.0f}%")
        print(f"    Median bias: {np.median([f.mean_bias for f in meal_fidelity]):+.1f} mg/dL")

    # EXP-2564c: Bias analysis by glucose zone
    print("\n--- EXP-2564c: Bias Analysis by Glucose Zone ---")
    all_fidelity = corr_fidelity + meal_fidelity
    if all_fidelity:
        zones = {
            'hypo (<70)': [f for f in all_fidelity if f.initial_glucose < 70],
            'low-normal (70-100)': [f for f in all_fidelity if 70 <= f.initial_glucose < 100],
            'normal (100-150)': [f for f in all_fidelity if 100 <= f.initial_glucose < 150],
            'high (150-200)': [f for f in all_fidelity if 150 <= f.initial_glucose < 200],
            'very high (>200)': [f for f in all_fidelity if f.initial_glucose >= 200],
        }
        for zone_name, zone_data in zones.items():
            if zone_data:
                bias = np.median([f.mean_bias for f in zone_data])
                r = np.median([f.correlation for f in zone_data])
                mae = np.median([f.mae for f in zone_data])
                print(f"  {zone_name}: n={len(zone_data)}, bias={bias:+.1f}, r={r:.3f}, MAE={mae:.1f}")

    # EXP-2564d: Per-patient calibration quality
    print("\n--- EXP-2564d: Per-Patient Calibration Quality ---")
    all_patient_stats = {}
    for pid in sorted(set(list(per_patient_corr.keys()) + list(per_patient_meal.keys()))):
        corr_stats = per_patient_corr.get(pid, {})
        meal_stats = per_patient_meal.get(pid, {})
        combined_r = []
        combined_mae = []
        if corr_stats:
            combined_r.append(corr_stats['median_r'])
            combined_mae.append(corr_stats['median_mae'])
        if meal_stats:
            combined_r.append(meal_stats['median_r'])
            combined_mae.append(meal_stats['median_mae'])
        if combined_r:
            avg_r = np.mean(combined_r)
            avg_mae = np.mean(combined_mae)
            quality = "GOOD" if avg_r > 0.5 else "FAIR" if avg_r > 0.3 else "POOR"
            all_patient_stats[pid] = {'avg_r': float(avg_r), 'avg_mae': float(avg_mae), 'quality': quality}
            print(f"  {pid}: avg_r={avg_r:.3f}, avg_MAE={avg_mae:.1f} → {quality}")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    if corr_fidelity:
        corr_r = np.median([f.correlation for f in corr_fidelity])
        corr_tir = np.mean([f.tir_agrees for f in corr_fidelity]) * 100
        nadir_30 = np.mean([f.nadir_timing_error_min <= 30 for f in corr_fidelity]) * 100
        corr_met = corr_r > 0.5
        print(f"\n  EXP-2564a (Correction fidelity):")
        print(f"    Median r: {corr_r:.3f} (criterion: >0.5) {'✅' if corr_met else '❌'}")
        print(f"    TIR agreement: {corr_tir:.0f}% (criterion: >60%) {'✅' if corr_tir > 60 else '❌'}")
        print(f"    Nadir timing ≤30min: {nadir_30:.0f}% (criterion: >50%) {'✅' if nadir_30 > 50 else '❌'}")

    if meal_fidelity:
        meal_r = np.median([f.correlation for f in meal_fidelity])
        meal_tir = np.mean([f.tir_agrees for f in meal_fidelity]) * 100
        meal_met = meal_r > 0.4
        print(f"\n  EXP-2564b (Meal fidelity):")
        print(f"    Median r: {meal_r:.3f} (criterion: >0.4) {'✅' if meal_met else '❌'}")
        print(f"    TIR agreement: {meal_tir:.0f}% (criterion: >60%) {'✅' if meal_tir > 60 else '❌'}")

    n_good = sum(1 for s in all_patient_stats.values() if s['quality'] == 'GOOD')
    n_fair = sum(1 for s in all_patient_stats.values() if s['quality'] == 'FAIR')
    n_poor = sum(1 for s in all_patient_stats.values() if s['quality'] == 'POOR')
    print(f"\n  EXP-2564d (Per-patient quality):")
    print(f"    GOOD: {n_good}, FAIR: {n_fair}, POOR: {n_poor}")

    criteria_met = sum([
        corr_r > 0.5 if corr_fidelity else False,
        meal_r > 0.4 if meal_fidelity else False,
        corr_tir > 60 if corr_fidelity else False,
    ])
    overall = "SUPPORTED" if criteria_met >= 2 else "PARTIALLY SUPPORTED" if criteria_met >= 1 else "NOT SUPPORTED"
    print(f"\n  OVERALL: HYPOTHESIS {overall} ({criteria_met}/3 criteria met)")

    runtime = time.time() - t0
    print(f"  Runtime: {runtime:.0f}s")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        'exp_id': 'EXP-2564',
        'hypothesis': 'Forward sim traces correlate with actual CGM traces',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'runtime_seconds': runtime,
        'correction_fidelity': {
            'n_windows': len(corr_fidelity),
            'median_r': float(np.median([f.correlation for f in corr_fidelity])) if corr_fidelity else 0,
            'median_mae': float(np.median([f.mae for f in corr_fidelity])) if corr_fidelity else 0,
            'tir_agreement_pct': float(np.mean([f.tir_agrees for f in corr_fidelity]) * 100) if corr_fidelity else 0,
            'median_bias': float(np.median([f.mean_bias for f in corr_fidelity])) if corr_fidelity else 0,
        },
        'meal_fidelity': {
            'n_windows': len(meal_fidelity),
            'median_r': float(np.median([f.correlation for f in meal_fidelity])) if meal_fidelity else 0,
            'median_mae': float(np.median([f.mae for f in meal_fidelity])) if meal_fidelity else 0,
            'tir_agreement_pct': float(np.mean([f.tir_agrees for f in meal_fidelity]) * 100) if meal_fidelity else 0,
            'median_bias': float(np.median([f.mean_bias for f in meal_fidelity])) if meal_fidelity else 0,
        },
        'per_patient_correction': per_patient_corr,
        'per_patient_meal': per_patient_meal,
        'per_patient_quality': all_patient_stats,
        'overall_conclusion': f'HYPOTHESIS {overall}',
    }

    out_path = RESULTS_DIR / 'exp-2564_forward_sim_fidelity.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results: {out_path}")


if __name__ == '__main__':
    main()
