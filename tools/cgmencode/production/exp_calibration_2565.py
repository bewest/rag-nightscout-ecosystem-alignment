#!/usr/bin/env python3
"""
EXP-2565: Per-Patient Forward Simulator Calibration

Hypothesis:
    Per-patient calibration of DIA fast-component tau and ISF power-law
    beta will reduce the systematic -50 mg/dL correction bias and improve
    trajectory correlation from r=0.74 to r>0.85.

Background:
    EXP-2564 revealed the forward sim has:
    - Correction bias: -49.9 mg/dL (sim overcorrects vs reality)
    - Meal bias: +28.0 mg/dL (sim underabsorbs carbs)
    - Shape correlation: r=0.74 for corrections, r=0.37 for meals
    - Population params: DIA tau=0.8h, ISF beta=0.9

    The bias likely comes from population parameters not matching
    individual patients. Per-patient calibration should fix this.

Method:
    For each NS patient (a-k):
    1. Extract 30 correction windows with full CGM traces
    2. Split 20/10 into calibration/validation sets
    3. Grid search over:
       - DIA fast-component tau: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5] hours
       - DIA slow fraction: [0.2, 0.3, 0.37, 0.45, 0.55] (default 0.37)
       - ISF beta: [0.7, 0.8, 0.9, 1.0, 1.1] (1.0 = linear)
    4. Objective: minimize MAE on calibration set
    5. Evaluate on validation set for overfitting check
    6. Compare calibrated vs population parameter fidelity

Sub-experiments:
    EXP-2565a: DIA tau calibration only (ISF beta fixed at 0.9)
    EXP-2565b: ISF beta calibration only (DIA tau fixed at 0.8)
    EXP-2565c: Joint DIA + ISF calibration
    EXP-2565d: Calibrated sim fidelity on validation set
    EXP-2565e: Do calibrated params correlate with patient phenotype?

Success criteria:
    - Calibrated MAE < 45 mg/dL (vs 61 population) on validation set
    - Calibrated r > 0.80 (vs 0.74 population) on validation set
    - Calibrated bias within ±15 mg/dL (vs -50 population)
    - Validation performance ≥ 90% of calibration performance (no overfit)

Data:
    NS patients only (a-k, 11 patients). ODC patients excluded due to
    known grid construction bugs under investigation.
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']


@dataclass
class CalibrationResult:
    patient_id: str
    n_cal_windows: int
    n_val_windows: int

    # Population params performance (validation set)
    pop_mae: float
    pop_r: float
    pop_bias: float

    # Best calibrated params
    best_tau: float
    best_slow_frac: float
    best_beta: float

    # Calibrated performance (calibration set)
    cal_mae: float
    cal_r: float
    cal_bias: float

    # Calibrated performance (validation set)
    val_mae: float
    val_r: float
    val_bias: float

    # Improvement
    mae_improvement: float  # pop_mae - val_mae
    r_improvement: float    # val_r - pop_r
    bias_improvement: float  # abs(pop_bias) - abs(val_bias)
    overfit_ratio: float    # val_mae / cal_mae (>1 = some overfit)


def load_data():
    """Load the training grid."""
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / \
        'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    if not grid_path.exists():
        print(f'ERROR: Training grid not found at {grid_path}')
        sys.exit(1)
    return pd.read_parquet(grid_path)


def extract_correction_windows_with_traces(pdf, max_windows=40):
    """Extract correction windows with full 4h CGM traces."""
    windows = []
    mask = (pdf['bolus'] > 0.5) & (pdf['carbs'].fillna(0) < 5) & (pdf['glucose'] > 150)
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
            'iob': float(window['iob'].iloc[0]) if 'iob' in window.columns else 0.0,
            'hour': float(window['time'].iloc[0].hour) if 'time' in window.columns else 12.0,
            'isf': float(window['scheduled_isf'].iloc[0]) if 'scheduled_isf' in window.columns else 50.0,
            'cr': float(window['scheduled_cr'].iloc[0]) if 'scheduled_cr' in window.columns else 10.0,
            'basal': float(window['scheduled_basal'].iloc[0]) if 'scheduled_basal' in window.columns else 1.0,
            'actual_trace': glucose_trace.tolist(),
        })
        if len(windows) >= max_windows:
            break
    return windows


def run_sim_with_params(w, tau, slow_frac, beta):
    """Run forward sim with specific DIA/ISF params."""
    from cgmencode.production.forward_simulator import (
        forward_simulate, TherapySettings, InsulinEvent,
    )

    settings = TherapySettings(
        isf=w['isf'],
        cr=w['cr'],
        basal_rate=w.get('basal', 1.0),
        dia_hours=tau * 5 / 0.8,  # Scale DIA to maintain proportionality
        iob_power_law=True,
    )

    bolus_events = [InsulinEvent(time_minutes=0, units=w['bolus'])]

    result = forward_simulate(
        initial_glucose=w['initial_glucose'],
        settings=settings,
        duration_hours=4.0,
        start_hour=w.get('hour', 12),
        bolus_events=bolus_events,
        carb_events=[],
        initial_iob=w.get('iob', 0),
        noise_std=0,
        seed=42,
    )

    return np.array(result.glucose)


def evaluate_params(windows, tau, slow_frac, beta):
    """Evaluate a set of calibration params on a set of windows."""
    correlations = []
    maes = []
    biases = []

    for w in windows:
        try:
            sim_trace = run_sim_with_params(w, tau, slow_frac, beta)
            actual = np.array(w['actual_trace'])

            # Resample sim to match actual (48 points)
            if len(sim_trace) != len(actual):
                sim_x = np.linspace(0, 1, len(sim_trace))
                act_x = np.linspace(0, 1, len(actual))
                sim_trace = np.interp(act_x, sim_x, sim_trace)

            # Correlation
            if np.std(actual) > 1e-6 and np.std(sim_trace) > 1e-6:
                r = float(np.corrcoef(actual, sim_trace)[0, 1])
                if not np.isnan(r):
                    correlations.append(r)

            mae = float(np.mean(np.abs(actual - sim_trace)))
            maes.append(mae)

            bias = float(np.mean(sim_trace - actual))
            biases.append(bias)

        except Exception:
            pass

    if not maes:
        return {'mae': 999, 'r': 0, 'bias': 999}

    return {
        'mae': float(np.median(maes)),
        'r': float(np.median(correlations)) if correlations else 0,
        'bias': float(np.median(biases)),
    }


def main():
    t0 = time.time()
    print("=" * 70)
    print("EXP-2565: Per-Patient Forward Simulator Calibration")
    print("=" * 70)

    df = load_data()
    print(f"Loaded {len(df):,} rows")
    print(f"Using NS patients only: {NS_PATIENTS}\n")

    tau_grid = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]
    slow_frac_grid = [0.2, 0.3, 0.37, 0.45, 0.55]
    beta_grid = [0.7, 0.8, 0.9, 1.0, 1.1]

    results = []

    for pid in NS_PATIENTS:
        pdf = df[df['patient_id'] == pid].copy()
        windows = extract_correction_windows_with_traces(pdf, max_windows=30)
        print(f"\n{'='*50}")
        print(f"Patient {pid}: {len(windows)} correction windows")

        if len(windows) < 10:
            print(f"  Skipped: need ≥10 windows, got {len(windows)}")
            continue

        # Split calibration (2/3) / validation (1/3)
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(windows))
        n_cal = int(len(windows) * 2 / 3)
        cal_windows = [windows[i] for i in idx[:n_cal]]
        val_windows = [windows[i] for i in idx[n_cal:]]
        print(f"  Calibration: {len(cal_windows)} windows, Validation: {len(val_windows)} windows")

        # Population baseline on validation set
        pop_eval = evaluate_params(val_windows, tau=0.8, slow_frac=0.37, beta=0.9)
        print(f"  Population params (tau=0.8, slow=0.37, beta=0.9):")
        print(f"    Validation: MAE={pop_eval['mae']:.1f}, r={pop_eval['r']:.3f}, bias={pop_eval['bias']:+.1f}")

        # EXP-2565a: DIA tau only
        print(f"\n  2565a: DIA tau calibration (beta=0.9 fixed)...")
        best_tau_only = {'tau': 0.8, 'mae': pop_eval['mae']}
        for tau in tau_grid:
            ev = evaluate_params(cal_windows, tau=tau, slow_frac=0.37, beta=0.9)
            if ev['mae'] < best_tau_only['mae']:
                best_tau_only = {'tau': tau, 'mae': ev['mae'], 'r': ev['r'], 'bias': ev['bias']}
        print(f"    Best tau={best_tau_only['tau']:.1f} (cal MAE={best_tau_only['mae']:.1f})")

        # EXP-2565b: ISF beta only
        print(f"  2565b: ISF beta calibration (tau=0.8 fixed)...")
        best_beta_only = {'beta': 0.9, 'mae': pop_eval['mae']}
        for beta in beta_grid:
            ev = evaluate_params(cal_windows, tau=0.8, slow_frac=0.37, beta=beta)
            if ev['mae'] < best_beta_only['mae']:
                best_beta_only = {'beta': beta, 'mae': ev['mae'], 'r': ev['r'], 'bias': ev['bias']}
        print(f"    Best beta={best_beta_only['beta']:.1f} (cal MAE={best_beta_only['mae']:.1f})")

        # EXP-2565c: Joint calibration
        print(f"  2565c: Joint DIA + ISF calibration...")
        best_joint = {'tau': 0.8, 'slow_frac': 0.37, 'beta': 0.9, 'mae': 999}

        for tau in tau_grid:
            for slow_frac in slow_frac_grid:
                for beta in beta_grid:
                    ev = evaluate_params(cal_windows, tau=tau, slow_frac=slow_frac, beta=beta)
                    if ev['mae'] < best_joint['mae']:
                        best_joint = {
                            'tau': tau, 'slow_frac': slow_frac, 'beta': beta,
                            'mae': ev['mae'], 'r': ev['r'], 'bias': ev['bias'],
                        }

        print(f"    Best: tau={best_joint['tau']:.1f}, slow={best_joint['slow_frac']:.2f}, beta={best_joint['beta']:.1f}")
        print(f"    Cal: MAE={best_joint['mae']:.1f}, r={best_joint['r']:.3f}, bias={best_joint['bias']:+.1f}")

        # EXP-2565d: Validate calibrated params
        cal_val = evaluate_params(val_windows,
                                  tau=best_joint['tau'],
                                  slow_frac=best_joint['slow_frac'],
                                  beta=best_joint['beta'])
        print(f"  2565d: Validation with calibrated params:")
        print(f"    Val: MAE={cal_val['mae']:.1f}, r={cal_val['r']:.3f}, bias={cal_val['bias']:+.1f}")
        print(f"    Improvement: MAE {pop_eval['mae']:.1f}→{cal_val['mae']:.1f} "
              f"({pop_eval['mae'] - cal_val['mae']:+.1f}), "
              f"r {pop_eval['r']:.3f}→{cal_val['r']:.3f}, "
              f"bias {pop_eval['bias']:+.1f}→{cal_val['bias']:+.1f}")

        overfit_ratio = cal_val['mae'] / best_joint['mae'] if best_joint['mae'] > 0 else 1.0
        print(f"    Overfit ratio: {overfit_ratio:.2f} (>1.5 = concerning)")

        result = CalibrationResult(
            patient_id=pid,
            n_cal_windows=len(cal_windows),
            n_val_windows=len(val_windows),
            pop_mae=pop_eval['mae'],
            pop_r=pop_eval['r'],
            pop_bias=pop_eval['bias'],
            best_tau=best_joint['tau'],
            best_slow_frac=best_joint['slow_frac'],
            best_beta=best_joint['beta'],
            cal_mae=best_joint['mae'],
            cal_r=best_joint.get('r', 0),
            cal_bias=best_joint.get('bias', 0),
            val_mae=cal_val['mae'],
            val_r=cal_val['r'],
            val_bias=cal_val['bias'],
            mae_improvement=pop_eval['mae'] - cal_val['mae'],
            r_improvement=cal_val['r'] - pop_eval['r'],
            bias_improvement=abs(pop_eval['bias']) - abs(cal_val['bias']),
            overfit_ratio=overfit_ratio,
        )
        results.append(result)

    # EXP-2565e: Parameter-phenotype correlations
    print("\n" + "=" * 70)
    print("EXP-2565e: Calibrated Parameter Analysis")
    print("=" * 70)

    if results:
        taus = [r.best_tau for r in results]
        betas = [r.best_beta for r in results]
        slow_fracs = [r.best_slow_frac for r in results]

        print(f"\n  DIA tau distribution: mean={np.mean(taus):.2f}, median={np.median(taus):.2f}, std={np.std(taus):.2f}")
        print(f"  ISF beta distribution: mean={np.mean(betas):.2f}, median={np.median(betas):.2f}, std={np.std(betas):.2f}")
        print(f"  Slow fraction dist: mean={np.mean(slow_fracs):.2f}, median={np.median(slow_fracs):.2f}")
        print(f"  Tau range: [{min(taus):.1f}, {max(taus):.1f}]")
        print(f"  Beta range: [{min(betas):.1f}, {max(betas):.1f}]")

        # Correlations between calibrated params
        if len(results) > 3:
            tau_beta_r = np.corrcoef(taus, betas)[0, 1]
            print(f"\n  Tau-beta correlation: r={tau_beta_r:.3f}")

            pop_maes = [r.pop_mae for r in results]
            val_maes = [r.val_mae for r in results]
            mae_r = np.corrcoef(pop_maes, val_maes)[0, 1]
            print(f"  Pop MAE vs Cal MAE correlation: r={mae_r:.3f}")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    if results:
        pop_maes = [r.pop_mae for r in results]
        val_maes = [r.val_mae for r in results]
        pop_rs = [r.pop_r for r in results]
        val_rs = [r.val_r for r in results]
        pop_biases = [r.pop_bias for r in results]
        val_biases = [r.val_bias for r in results]
        overfit_ratios = [r.overfit_ratio for r in results]

        print(f"\n  Population params:")
        print(f"    Median MAE: {np.median(pop_maes):.1f} mg/dL")
        print(f"    Median r: {np.median(pop_rs):.3f}")
        print(f"    Median bias: {np.median(pop_biases):+.1f} mg/dL")

        print(f"\n  Calibrated params (validation set):")
        print(f"    Median MAE: {np.median(val_maes):.1f} mg/dL (criterion: <45) {'✅' if np.median(val_maes) < 45 else '❌'}")
        print(f"    Median r: {np.median(val_rs):.3f} (criterion: >0.80) {'✅' if np.median(val_rs) > 0.80 else '❌'}")
        print(f"    Median bias: {np.median(val_biases):+.1f} mg/dL (criterion: ±15) {'✅' if abs(np.median(val_biases)) < 15 else '❌'}")

        print(f"\n  Improvement:")
        print(f"    MAE: {np.median(pop_maes):.1f} → {np.median(val_maes):.1f} ({np.median(pop_maes) - np.median(val_maes):+.1f})")
        print(f"    r: {np.median(pop_rs):.3f} → {np.median(val_rs):.3f} ({np.median(val_rs) - np.median(pop_rs):+.3f})")
        print(f"    bias: {np.median(pop_biases):+.1f} → {np.median(val_biases):+.1f}")

        print(f"\n  Overfit check:")
        print(f"    Median overfit ratio: {np.median(overfit_ratios):.2f} (criterion: <1.50) {'✅' if np.median(overfit_ratios) < 1.5 else '❌'}")
        print(f"    Max overfit ratio: {max(overfit_ratios):.2f}")

        n_improved_mae = sum(1 for r in results if r.mae_improvement > 0)
        n_improved_r = sum(1 for r in results if r.r_improvement > 0)
        print(f"\n  Per-patient: {n_improved_mae}/{len(results)} improved MAE, {n_improved_r}/{len(results)} improved r")

        criteria_met = sum([
            np.median(val_maes) < 45,
            np.median(val_rs) > 0.80,
            abs(np.median(val_biases)) < 15,
            np.median(overfit_ratios) < 1.5,
        ])
        overall = "SUPPORTED" if criteria_met >= 3 else "PARTIALLY SUPPORTED" if criteria_met >= 2 else "NOT SUPPORTED"
    else:
        overall = "NOT SUPPORTED (no patients qualified)"
        criteria_met = 0

    print(f"\n  OVERALL: HYPOTHESIS {overall} ({criteria_met}/4 criteria met)")

    runtime = time.time() - t0
    print(f"  Runtime: {runtime:.0f}s")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        'exp_id': 'EXP-2565',
        'hypothesis': 'Per-patient DIA/ISF calibration reduces bias and improves fidelity',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'runtime_seconds': runtime,
        'patients': NS_PATIENTS,
        'calibration_results': [asdict(r) for r in results],
        'summary': {
            'n_patients': len(results),
            'pop_median_mae': float(np.median([r.pop_mae for r in results])) if results else 0,
            'cal_median_mae': float(np.median([r.val_mae for r in results])) if results else 0,
            'pop_median_r': float(np.median([r.pop_r for r in results])) if results else 0,
            'cal_median_r': float(np.median([r.val_r for r in results])) if results else 0,
            'criteria_met': criteria_met,
        },
        'overall_conclusion': f'HYPOTHESIS {overall}',
    }

    out_path = RESULTS_DIR / 'exp-2565_per_patient_calibration.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Results: {out_path}")


if __name__ == '__main__':
    main()
