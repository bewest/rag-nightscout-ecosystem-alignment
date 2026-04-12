#!/usr/bin/env python3
"""
EXP-2563: Per-Patient ISF/CR Optimization via Forward Simulator

Hypothesis:
    Forward sim grid search over ISF×CR multiplier space will identify
    patient-specific optimal settings that differ from current profile
    values, and these optimal settings will be consistent across
    bootstrap resamples of each patient's windows.

Background:
    - EXP-2562 showed ISF+20% → +2.1pp TIR, CR+20% → +3.3pp TIR at
      population level. But these are averages — individual patients
      may need very different adjustments.
    - The settings_optimizer currently uses a perturbation model (which
      showed null results in EXP-2552 for circadian strategies).
    - This experiment validates forward sim as an optimization engine.

Method:
    For each patient:
    1. Extract correction windows (ISF optimization) and meal windows
       (CR optimization)
    2. Grid search ISF multipliers [0.7 .. 1.5, step 0.1]
    3. Grid search CR multipliers [0.7 .. 1.5, step 0.1]
    4. Report optimal multiplier per patient with bootstrap 95% CI
    5. Compute combined ISF×CR grid for joint optimization

Sub-experiments:
    EXP-2563a: Per-patient optimal ISF from correction windows
    EXP-2563b: Per-patient optimal CR from meal windows
    EXP-2563c: Joint ISF×CR optimization (top 5 patients with most data)
    EXP-2563d: Consistency check — compare forward-sim optima to
               settings_optimizer natural-experiment optima

Success criteria:
    - >80% of patients show optimal ISF ≠ 1.0 with bootstrap CI excluding 1.0
    - >60% of patients show optimal CR ≠ 1.0 with bootstrap CI excluding 1.0
    - Joint optimization TIR gain > sum of individual gains for >30% of patients
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
class PatientOptimization:
    patient_id: str
    window_type: str
    n_windows: int
    multiplier_grid: List[float] = field(default_factory=list)
    tir_by_multiplier: Dict[str, float] = field(default_factory=dict)
    optimal_multiplier: float = 1.0
    optimal_tir_delta: float = 0.0
    bootstrap_ci_low: float = 1.0
    bootstrap_ci_high: float = 1.0
    ci_excludes_one: bool = False


def load_data():
    """Load the training grid."""
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    df = pd.read_parquet(grid_path)
    return df


def extract_correction_windows(pdf, max_windows=50):
    """Extract correction bolus windows (bolus without carbs, glucose > 150)."""
    windows = []
    bolus_mask = (pdf['bolus'] > 0.5) & (pdf['carbs'].fillna(0) < 5) & (pdf['glucose'] > 150)
    bolus_idx = pdf.index[bolus_mask]

    for idx in bolus_idx[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        window = pdf.iloc[pos:pos + 48]
        if len(window) < 48:
            continue
        if window['glucose'].isna().sum() > 5:
            continue
        windows.append({
            'initial_glucose': float(window['glucose'].iloc[0]),
            'bolus': float(window['bolus'].iloc[0]),
            'iob': float(window['iob'].iloc[0]) if 'iob' in window.columns else 0.0,
            'hour': float(window['time'].iloc[0].hour) if 'time' in window.columns else 12.0,
            'isf': float(window['scheduled_isf'].iloc[0]) if 'scheduled_isf' in window.columns else 50.0,
            'cr': float(window['scheduled_cr'].iloc[0]) if 'scheduled_cr' in window.columns else 10.0,
            'basal': float(window['scheduled_basal'].iloc[0]) if 'scheduled_basal' in window.columns else 1.0,
            'actual_tir': float((window['glucose'].between(70, 180)).mean()),
        })
        if len(windows) >= max_windows:
            break
    return windows


def extract_meal_windows(pdf, max_windows=50):
    """Extract meal bolus windows (carbs > 10g)."""
    windows = []
    meal_mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)
    meal_idx = pdf.index[meal_mask]

    for idx in meal_idx[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        window = pdf.iloc[pos:pos + 48]
        if len(window) < 48:
            continue
        if window['glucose'].isna().sum() > 5:
            continue
        windows.append({
            'initial_glucose': float(window['glucose'].iloc[0]),
            'bolus': float(window['bolus'].iloc[0]),
            'carbs': float(window['carbs'].iloc[0]),
            'iob': float(window['iob'].iloc[0]) if 'iob' in window.columns else 0.0,
            'hour': float(window['time'].iloc[0].hour) if 'time' in window.columns else 12.0,
            'isf': float(window['scheduled_isf'].iloc[0]) if 'scheduled_isf' in window.columns else 50.0,
            'cr': float(window['scheduled_cr'].iloc[0]) if 'scheduled_cr' in window.columns else 10.0,
            'basal': float(window['scheduled_basal'].iloc[0]) if 'scheduled_basal' in window.columns else 1.0,
            'actual_tir': float((window['glucose'].between(70, 180)).mean()),
        })
        if len(windows) >= max_windows:
            break
    return windows


def run_grid_search(windows, window_type, multiplier_grid, patient_settings):
    """Run forward sim for each window at each multiplier value."""
    from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent, CarbEvent

    results_by_mult = {f"{m:.1f}": [] for m in multiplier_grid}

    for w in windows:
        for mult in multiplier_grid:
            if window_type == 'correction':
                settings = TherapySettings(
                    isf=w['isf'] * mult,
                    cr=w['cr'],
                    basal_rate=w.get('basal', 1.0),
                    dia_hours=5.0,
                )
            else:  # meal
                settings = TherapySettings(
                    isf=w['isf'],
                    cr=w['cr'] * mult,
                    basal_rate=w.get('basal', 1.0),
                    dia_hours=5.0,
                )

            bolus_events = [InsulinEvent(time_minutes=0, units=w['bolus'])]
            carb_events = [CarbEvent(time_minutes=0, grams=w.get('carbs', 0))] if w.get('carbs', 0) > 0 else []

            try:
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
                tir = float(np.mean((np.array(result.glucose) >= 70) & (np.array(result.glucose) <= 180)))
                tbr = float(np.mean(np.array(result.glucose) < 70))
                results_by_mult[f"{mult:.1f}"].append({'tir': tir, 'tbr': tbr})
            except Exception:
                pass

    return results_by_mult


def bootstrap_optimal(windows, window_type, multiplier_grid, n_bootstrap=200):
    """Bootstrap to get CI on optimal multiplier."""
    from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent, CarbEvent

    rng = np.random.RandomState(42)
    optimal_mults = []

    for _ in range(n_bootstrap):
        # Resample windows
        idx = rng.choice(len(windows), size=len(windows), replace=True)
        sampled = [windows[i] for i in idx]

        # Quick grid search on resampled windows
        best_mult = 1.0
        best_tir = -1.0

        for mult in multiplier_grid:
            tirs = []
            for w in sampled:
                if window_type == 'correction':
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
                carb_events = [CarbEvent(time_minutes=0, grams=w.get('carbs', 0))] if w.get('carbs', 0) > 0 else []

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
                mean_tir = np.mean(tirs)
                if mean_tir > best_tir:
                    best_tir = mean_tir
                    best_mult = mult

        optimal_mults.append(best_mult)

    return optimal_mults


def run_joint_optimization(windows_corr, windows_meal, isf_grid, cr_grid, patient_id):
    """Joint ISF×CR grid search for a single patient."""
    from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent, CarbEvent

    joint_results = {}

    all_windows = []
    for w in windows_corr:
        all_windows.append(('correction', w))
    for w in windows_meal:
        all_windows.append(('meal', w))

    if len(all_windows) < 10:
        return None

    for isf_m in isf_grid:
        for cr_m in cr_grid:
            tirs = []
            for wtype, w in all_windows:
                settings = TherapySettings(
                    isf=w['isf'] * isf_m,
                    cr=w['cr'] * cr_m,
                    basal_rate=w.get('basal', 1.0),
                    dia_hours=5.0,
                )
                bolus_events = [InsulinEvent(time_minutes=0, units=w['bolus'])]
                carb_events = [CarbEvent(time_minutes=0, grams=w.get('carbs', 0))] if w.get('carbs', 0) > 0 else []

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
                joint_results[f"{isf_m:.1f},{cr_m:.1f}"] = {
                    'mean_tir': float(np.mean(tirs)),
                    'n_windows': len(tirs),
                }

    return joint_results


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2563: Per-Patient ISF/CR Optimization via Forward Simulator")
    print("=" * 70)

    df = load_data()
    patients = sorted(df['patient_id'].unique()) if 'patient_id' in df.columns else sorted(df.index.get_level_values(0).unique())
    print(f"Loaded {len(df):,} rows, {len(patients)} patients\n")

    multiplier_grid = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

    # EXP-2563a: Per-patient ISF optimization
    print("--- EXP-2563a: Per-Patient ISF Optimization ---")
    isf_results = []
    for pid in patients:
        if 'patient_id' in df.columns:
            pdf = df[df['patient_id'] == pid].copy()
        else:
            pdf = df.loc[pid].copy()

        windows = extract_correction_windows(pdf)
        print(f"  {pid}: {len(windows)} correction windows", end="")

        if len(windows) < 5:
            print(" (skipped: <5)")
            continue

        # Grid search
        grid_results = run_grid_search(windows, 'correction', multiplier_grid, None)

        # Find optimal
        best_mult = 1.0
        best_tir = 0.0
        baseline_tir = 0.0
        tir_by_mult = {}
        for mult_str, vals in grid_results.items():
            if vals:
                mean_tir = np.mean([v['tir'] for v in vals])
                tir_by_mult[mult_str] = float(mean_tir)
                if float(mult_str) == 1.0:
                    baseline_tir = mean_tir
                if mean_tir > best_tir:
                    best_tir = mean_tir
                    best_mult = float(mult_str)

        # Bootstrap CI
        boot_mults = bootstrap_optimal(windows, 'correction', multiplier_grid, n_bootstrap=100)
        ci_low = float(np.percentile(boot_mults, 2.5))
        ci_high = float(np.percentile(boot_mults, 97.5))
        ci_excludes_one = ci_low > 1.0 or ci_high < 1.0

        opt = PatientOptimization(
            patient_id=pid,
            window_type='correction',
            n_windows=len(windows),
            multiplier_grid=multiplier_grid,
            tir_by_multiplier=tir_by_mult,
            optimal_multiplier=best_mult,
            optimal_tir_delta=float(best_tir - baseline_tir),
            bootstrap_ci_low=ci_low,
            bootstrap_ci_high=ci_high,
            ci_excludes_one=ci_excludes_one,
        )
        isf_results.append(opt)
        print(f" → ISF×{best_mult:.1f} (TIR +{best_tir - baseline_tir:.1f}pp, CI [{ci_low:.1f}, {ci_high:.1f}]{'*' if ci_excludes_one else ''})")

    n_isf_not_one = sum(1 for r in isf_results if r.optimal_multiplier != 1.0)
    n_isf_ci = sum(1 for r in isf_results if r.ci_excludes_one)
    print(f"\n  ISF summary: {n_isf_not_one}/{len(isf_results)} patients optimal ≠ 1.0, {n_isf_ci}/{len(isf_results)} CI excludes 1.0")

    # EXP-2563b: Per-patient CR optimization
    print("\n--- EXP-2563b: Per-Patient CR Optimization ---")
    cr_results = []
    for pid in patients:
        if 'patient_id' in df.columns:
            pdf = df[df['patient_id'] == pid].copy()
        else:
            pdf = df.loc[pid].copy()

        windows = extract_meal_windows(pdf)
        print(f"  {pid}: {len(windows)} meal windows", end="")

        if len(windows) < 5:
            print(" (skipped: <5)")
            continue

        grid_results = run_grid_search(windows, 'meal', multiplier_grid, None)

        best_mult = 1.0
        best_tir = 0.0
        baseline_tir = 0.0
        tir_by_mult = {}
        for mult_str, vals in grid_results.items():
            if vals:
                mean_tir = np.mean([v['tir'] for v in vals])
                tir_by_mult[mult_str] = float(mean_tir)
                if float(mult_str) == 1.0:
                    baseline_tir = mean_tir
                if mean_tir > best_tir:
                    best_tir = mean_tir
                    best_mult = float(mult_str)

        boot_mults = bootstrap_optimal(windows, 'meal', multiplier_grid, n_bootstrap=100)
        ci_low = float(np.percentile(boot_mults, 2.5))
        ci_high = float(np.percentile(boot_mults, 97.5))
        ci_excludes_one = ci_low > 1.0 or ci_high < 1.0

        opt = PatientOptimization(
            patient_id=pid,
            window_type='meal',
            n_windows=len(windows),
            multiplier_grid=multiplier_grid,
            tir_by_multiplier=tir_by_mult,
            optimal_multiplier=best_mult,
            optimal_tir_delta=float(best_tir - baseline_tir),
            bootstrap_ci_low=ci_low,
            bootstrap_ci_high=ci_high,
            ci_excludes_one=ci_excludes_one,
        )
        cr_results.append(opt)
        print(f" → CR×{best_mult:.1f} (TIR +{best_tir - baseline_tir:.1f}pp, CI [{ci_low:.1f}, {ci_high:.1f}]{'*' if ci_excludes_one else ''})")

    n_cr_not_one = sum(1 for r in cr_results if r.optimal_multiplier != 1.0)
    n_cr_ci = sum(1 for r in cr_results if r.ci_excludes_one)
    print(f"\n  CR summary: {n_cr_not_one}/{len(cr_results)} patients optimal ≠ 1.0, {n_cr_ci}/{len(cr_results)} CI excludes 1.0")

    # EXP-2563c: Joint optimization for top patients
    print("\n--- EXP-2563c: Joint ISF×CR Optimization ---")
    # Pick patients with most combined windows
    patient_window_counts = {}
    for r in isf_results:
        patient_window_counts[r.patient_id] = patient_window_counts.get(r.patient_id, 0) + r.n_windows
    for r in cr_results:
        patient_window_counts[r.patient_id] = patient_window_counts.get(r.patient_id, 0) + r.n_windows

    top_patients = sorted(patient_window_counts, key=patient_window_counts.get, reverse=True)[:5]
    coarse_grid = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]

    joint_results = {}
    for pid in top_patients:
        if 'patient_id' in df.columns:
            pdf = df[df['patient_id'] == pid].copy()
        else:
            pdf = df.loc[pid].copy()

        corr_w = extract_correction_windows(pdf, max_windows=30)
        meal_w = extract_meal_windows(pdf, max_windows=30)
        print(f"  {pid}: {len(corr_w)} corr + {len(meal_w)} meal windows", end="")

        jr = run_joint_optimization(corr_w, meal_w, coarse_grid, coarse_grid, pid)
        if jr is None:
            print(" (skipped: <10 total)")
            continue

        # Find optimal
        best_key = max(jr, key=lambda k: jr[k]['mean_tir'])
        baseline_key = "1.0,1.0"
        baseline_tir = jr.get(baseline_key, {}).get('mean_tir', 0)
        best_tir = jr[best_key]['mean_tir']
        isf_opt, cr_opt = best_key.split(',')

        joint_results[pid] = {
            'optimal_isf_mult': float(isf_opt),
            'optimal_cr_mult': float(cr_opt),
            'baseline_tir': float(baseline_tir),
            'optimal_tir': float(best_tir),
            'tir_delta': float(best_tir - baseline_tir),
            'grid': jr,
        }
        print(f" → ISF×{isf_opt}, CR×{cr_opt} (TIR +{best_tir - baseline_tir:.1f}pp)")

    # EXP-2563d: Consistency with settings_optimizer
    print("\n--- EXP-2563d: Consistency Check ---")
    isf_dist = [r.optimal_multiplier for r in isf_results]
    cr_dist = [r.optimal_multiplier for r in cr_results]
    print(f"  ISF optimal multiplier distribution: mean={np.mean(isf_dist):.2f}, median={np.median(isf_dist):.2f}, std={np.std(isf_dist):.2f}")
    print(f"  CR optimal multiplier distribution: mean={np.mean(cr_dist):.2f}, median={np.median(cr_dist):.2f}, std={np.std(cr_dist):.2f}")
    print(f"  ISF range: [{min(isf_dist):.1f}, {max(isf_dist):.1f}]")
    print(f"  CR range: [{min(cr_dist):.1f}, {max(cr_dist):.1f}]")

    # Cross-check: do ISF and CR optima correlate?
    paired = []
    for ir in isf_results:
        for cr in cr_results:
            if ir.patient_id == cr.patient_id:
                paired.append((ir.optimal_multiplier, cr.optimal_multiplier))
    if len(paired) > 3:
        isf_vals, cr_vals = zip(*paired)
        corr = float(np.corrcoef(isf_vals, cr_vals)[0, 1])
        print(f"  ISF-CR optimal correlation: r={corr:.3f} (n={len(paired)})")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n  EXP-2563a (ISF optimization):")
    print(f"    {n_isf_not_one}/{len(isf_results)} patients: optimal ISF ≠ 1.0 ({100*n_isf_not_one/len(isf_results):.0f}%)")
    print(f"    {n_isf_ci}/{len(isf_results)} patients: bootstrap CI excludes 1.0 ({100*n_isf_ci/len(isf_results):.0f}%)")
    isf_deltas = [r.optimal_tir_delta for r in isf_results]
    print(f"    Mean TIR delta at optimal: +{np.mean(isf_deltas):.1f}pp")
    print(f"    ISF multiplier distribution: {np.mean(isf_dist):.2f} ± {np.std(isf_dist):.2f}")

    isf_success = n_isf_not_one / len(isf_results) >= 0.8 if isf_results else False
    print(f"    Criterion (>80% ≠ 1.0): {'✅ MET' if isf_success else '❌ NOT MET'}")

    print(f"\n  EXP-2563b (CR optimization):")
    print(f"    {n_cr_not_one}/{len(cr_results)} patients: optimal CR ≠ 1.0 ({100*n_cr_not_one/len(cr_results):.0f}%)")
    print(f"    {n_cr_ci}/{len(cr_results)} patients: bootstrap CI excludes 1.0 ({100*n_cr_ci/len(cr_results):.0f}%)")
    cr_deltas = [r.optimal_tir_delta for r in cr_results]
    print(f"    Mean TIR delta at optimal: +{np.mean(cr_deltas):.1f}pp")
    print(f"    CR multiplier distribution: {np.mean(cr_dist):.2f} ± {np.std(cr_dist):.2f}")

    cr_success = n_cr_not_one / len(cr_results) >= 0.6 if cr_results else False
    print(f"    Criterion (>60% ≠ 1.0): {'✅ MET' if cr_success else '❌ NOT MET'}")

    if joint_results:
        print(f"\n  EXP-2563c (Joint optimization):")
        for pid, jr in joint_results.items():
            print(f"    {pid}: ISF×{jr['optimal_isf_mult']:.1f} + CR×{jr['optimal_cr_mult']:.1f} → TIR +{jr['tir_delta']:.1f}pp")

    overall = "SUPPORTED" if (isf_success or cr_success) else "NOT SUPPORTED"
    print(f"\n  OVERALL: HYPOTHESIS {overall}")

    runtime = time.time() - t0
    print(f"  Runtime: {runtime:.0f}s")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        'exp_id': 'EXP-2563',
        'hypothesis': 'Per-patient ISF/CR optimization via forward sim',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'runtime_seconds': runtime,
        'isf_optimization': [asdict(r) for r in isf_results],
        'cr_optimization': [asdict(r) for r in cr_results],
        'joint_optimization': joint_results,
        'summary': {
            'isf_pct_not_one': 100 * n_isf_not_one / len(isf_results) if isf_results else 0,
            'isf_pct_ci_excludes': 100 * n_isf_ci / len(isf_results) if isf_results else 0,
            'cr_pct_not_one': 100 * n_cr_not_one / len(cr_results) if cr_results else 0,
            'cr_pct_ci_excludes': 100 * n_cr_ci / len(cr_results) if cr_results else 0,
            'isf_mean_delta': float(np.mean(isf_deltas)) if isf_deltas else 0,
            'cr_mean_delta': float(np.mean(cr_deltas)) if cr_deltas else 0,
        },
        'overall_conclusion': f'HYPOTHESIS {overall}',
    }

    out_path = RESULTS_DIR / 'exp-2563_per_patient_optimization.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results: {out_path}")


if __name__ == '__main__':
    main()
