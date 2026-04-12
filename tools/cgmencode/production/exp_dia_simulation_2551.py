#!/usr/bin/env python3
"""
EXP-2551: Two-Component DIA Simulation Accuracy

Hypothesis: Using two-component DIA (fast τ=0.8h + persistent tail) and
power-law ISF in simulate_tir_with_settings() produces more accurate
retrospective TIR predictions than the current perturbation model.

Design:
  - 3 simulation models compared:
    (A) Current perturbation model (2h half-life exponential decay)
    (B) Two-component DIA (fast + persistent, from EXP-2525/2534)
    (C) Two-component DIA + power-law ISF (from EXP-2511)
  - Validation: 80/20 temporal holdout per patient
    - Train: first 80% of days → compute optimal settings
    - Test: last 20% → simulate TIR with those settings, compare to actual
  - Primary metric: TIR prediction MAE (pp) across patients
  - Secondary: correlation of predicted vs actual TIR delta

Research basis:
  - EXP-2525: Two-component DIA model (R²=0.827)
  - EXP-2534: Persistent = residual IOB, not HGP (mechanism correction)
  - EXP-2511: Power-law ISF β=0.9 (17/17 patients)
  - EXP-1717: Combined optimization predicts +2.8% TIR

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_dia_simulation_2551.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_dia_simulation_2551.py --figures
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from cgmencode.production.types import (
    MetabolicState, PatientData, PatientProfile,
)
from cgmencode.production.metabolic_engine import (
    compute_metabolic_state, decompose_two_component_dia,
    _FAST_TAU_HOURS, _PERSISTENT_FRACTION,
)
from cgmencode.production.settings_advisor import simulate_tir_with_settings
from cgmencode.production.natural_experiment_detector import (
    detect_natural_experiments,
)
from cgmencode.production.settings_optimizer import optimize_settings

# ── Constants ────────────────────────────────────────────────────────

HOLDOUT_FRACTION = 0.20
POWER_LAW_BETA = 0.9  # from EXP-2511
TIR_LOW = 70.0
TIR_HIGH = 180.0

# Two-component DIA simulation parameters (from EXP-2525)
FAST_TAU_STEPS = int(_FAST_TAU_HOURS * 12)  # 0.8h × 12 steps/h ≈ 10 steps
PERSISTENT_DECAY_STEPS = int(12.0 * 12)     # 12h lookback
FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION  # 0.63


# ── Simulation Models ────────────────────────────────────────────────

def simulate_tir_current(glucose: np.ndarray,
                         metabolic: MetabolicState,
                         hours: np.ndarray,
                         isf_mult: float = 1.0,
                         cr_mult: float = 1.0,
                         basal_mult: float = 1.0,
                         ) -> Tuple[float, float]:
    """Model A: Current perturbation model (baseline)."""
    return simulate_tir_with_settings(
        glucose, metabolic, hours,
        isf_multiplier=isf_mult,
        cr_multiplier=cr_mult,
        basal_multiplier=basal_mult,
    )


def simulate_tir_two_component(glucose: np.ndarray,
                                metabolic: MetabolicState,
                                hours: np.ndarray,
                                isf_mult: float = 1.0,
                                cr_mult: float = 1.0,
                                basal_mult: float = 1.0,
                                ) -> Tuple[float, float]:
    """Model B: Two-component DIA simulation.

    Instead of a single 2h half-life decay, uses:
    - Fast component: exponential decay with τ=0.8h (10 steps)
    - Persistent component: slow decay with τ=12h (144 steps)

    The fast component carries 63% of the perturbation, the persistent
    carries 37%. This matches the validated two-component model from
    EXP-2525 (R²=0.827).
    """
    N = len(glucose)
    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    supply = metabolic.supply
    demand = metabolic.demand

    # Two decay factors
    fast_decay = np.exp(-1.0 / max(FAST_TAU_STEPS, 1))      # τ=0.8h
    persistent_decay = np.exp(-1.0 / PERSISTENT_DECAY_STEPS) # τ=12h

    delta_fast = np.zeros(N)
    delta_persistent = np.zeros(N)

    for t in range(1, N):
        delta_fast[t] = delta_fast[t - 1] * fast_decay
        delta_persistent[t] = delta_persistent[t - 1] * persistent_decay

        s = float(supply[t - 1]) if np.isfinite(supply[t - 1]) else 0.0
        d = float(demand[t - 1]) if np.isfinite(demand[t - 1]) else 0.0

        # ISF perturbation: split into fast and persistent
        demand_delta = d * (isf_mult * basal_mult - 1.0)
        supply_delta = s * (1.0 / max(cr_mult, 0.1) - 1.0)
        step_pert = supply_delta - demand_delta

        delta_fast[t] += step_pert * FAST_FRACTION
        delta_persistent[t] += step_pert * _PERSISTENT_FRACTION

    delta = delta_fast + delta_persistent
    sim_bg = np.clip(bg + delta, 40.0, 400.0)

    valid_orig = bg[np.isfinite(bg)]
    valid_sim = sim_bg[np.isfinite(sim_bg)]
    tir_current = float(np.mean((valid_orig >= TIR_LOW) & (valid_orig <= TIR_HIGH)))
    tir_sim = float(np.mean((valid_sim >= TIR_LOW) & (valid_sim <= TIR_HIGH)))
    return tir_current, tir_sim


def simulate_tir_two_component_powerlaw(glucose: np.ndarray,
                                         metabolic: MetabolicState,
                                         hours: np.ndarray,
                                         isf_mult: float = 1.0,
                                         cr_mult: float = 1.0,
                                         basal_mult: float = 1.0,
                                         ) -> Tuple[float, float]:
    """Model C: Two-component DIA + power-law ISF.

    Adds the ISF power-law correction from EXP-2511:
    effective_isf_mult = isf_mult^(1 - β) where β=0.9

    For β=0.9, a 2× ISF change only produces 2^0.1 ≈ 1.07× the effect.
    This prevents the simulation from overestimating the impact of large
    ISF corrections — matching the empirical finding that ISF has
    diminishing returns with dose.
    """
    N = len(glucose)
    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    supply = metabolic.supply
    demand = metabolic.demand

    fast_decay = np.exp(-1.0 / max(FAST_TAU_STEPS, 1))
    persistent_decay = np.exp(-1.0 / PERSISTENT_DECAY_STEPS)

    delta_fast = np.zeros(N)
    delta_persistent = np.zeros(N)

    # Power-law correction: effective multiplier is dampened
    if isf_mult > 0:
        effective_isf_mult = isf_mult ** (1.0 - POWER_LAW_BETA)
    else:
        effective_isf_mult = 1.0

    for t in range(1, N):
        delta_fast[t] = delta_fast[t - 1] * fast_decay
        delta_persistent[t] = delta_persistent[t - 1] * persistent_decay

        s = float(supply[t - 1]) if np.isfinite(supply[t - 1]) else 0.0
        d = float(demand[t - 1]) if np.isfinite(demand[t - 1]) else 0.0

        # Power-law dampened ISF effect
        demand_delta = d * (effective_isf_mult * basal_mult - 1.0)
        supply_delta = s * (1.0 / max(cr_mult, 0.1) - 1.0)
        step_pert = supply_delta - demand_delta

        delta_fast[t] += step_pert * FAST_FRACTION
        delta_persistent[t] += step_pert * _PERSISTENT_FRACTION

    delta = delta_fast + delta_persistent
    sim_bg = np.clip(bg + delta, 40.0, 400.0)

    valid_orig = bg[np.isfinite(bg)]
    valid_sim = sim_bg[np.isfinite(sim_bg)]
    tir_current = float(np.mean((valid_orig >= TIR_LOW) & (valid_orig <= TIR_HIGH)))
    tir_sim = float(np.mean((valid_sim >= TIR_LOW) & (valid_sim <= TIR_HIGH)))
    return tir_current, tir_sim


# ── Temporal Split ───────────────────────────────────────────────────

def temporal_split(patient: PatientData,
                   holdout_frac: float = HOLDOUT_FRACTION,
                   ) -> Tuple[PatientData, PatientData]:
    """Split patient data into train (first 80%) and test (last 20%)."""
    N = patient.n_samples
    split_idx = int(N * (1.0 - holdout_frac))

    def _slice(arr, start, end):
        if arr is None:
            return None
        return arr[start:end].copy()

    train = PatientData(
        glucose=patient.glucose[:split_idx].copy(),
        timestamps=patient.timestamps[:split_idx].copy(),
        profile=patient.profile,
        iob=_slice(patient.iob, 0, split_idx),
        cob=_slice(patient.cob, 0, split_idx),
        bolus=_slice(patient.bolus, 0, split_idx),
        carbs=_slice(patient.carbs, 0, split_idx),
        basal_rate=_slice(patient.basal_rate, 0, split_idx),
    )
    test = PatientData(
        glucose=patient.glucose[split_idx:].copy(),
        timestamps=patient.timestamps[split_idx:].copy(),
        profile=patient.profile,
        iob=_slice(patient.iob, split_idx, N),
        cob=_slice(patient.cob, split_idx, N),
        bolus=_slice(patient.bolus, split_idx, N),
        carbs=_slice(patient.carbs, split_idx, N),
        basal_rate=_slice(patient.basal_rate, split_idx, N),
    )
    return train, test


# ── Per-Patient Experiment ───────────────────────────────────────────

@dataclass
class PatientResult:
    patient_id: str
    n_train: int
    n_test: int
    actual_tir_train: float
    actual_tir_test: float
    # Settings recommendations from train period
    isf_mult: float
    cr_mult: float
    basal_mult: float
    # Model A: current perturbation
    predicted_tir_A: float
    tir_delta_pred_A: float
    tir_delta_actual: float
    tir_mae_A: float
    # Model B: two-component DIA
    predicted_tir_B: float
    tir_delta_pred_B: float
    tir_mae_B: float
    # Model C: two-component + power-law
    predicted_tir_C: float
    tir_delta_pred_C: float
    tir_mae_C: float


def run_patient(patient: PatientData, patient_id: str) -> Optional[PatientResult]:
    """Run all 3 simulation models on one patient with temporal holdout."""
    if patient.n_samples < 576:  # minimum 2 days
        print(f"  {patient_id}: skip (n={patient.n_samples} < 576)")
        return None

    # Temporal split
    train, test = temporal_split(patient)
    print(f"  {patient_id}: train={train.n_samples}, test={test.n_samples}")

    # Compute metabolic state for both periods
    meta_train = compute_metabolic_state(train)
    meta_test = compute_metabolic_state(test)

    from cgmencode.production.metabolic_engine import _extract_hours
    hours_train = _extract_hours(train.timestamps)
    hours_test = _extract_hours(test.timestamps)

    # Actual TIR
    def tir(g):
        g_valid = g[np.isfinite(g)]
        if len(g_valid) == 0:
            return 0.5
        return float(np.mean((g_valid >= TIR_LOW) & (g_valid <= TIR_HIGH)))

    tir_train = tir(train.glucose)
    tir_test = tir(test.glucose)

    # Generate settings recommendations from train period
    # Use the settings optimizer on natural experiments
    try:
        ne_census = detect_natural_experiments(
            train.glucose, meta_train, hours_train, train.profile,
            bolus=train.bolus, carbs=train.carbs, basal_rate=train.basal_rate,
        )
        opt_result = optimize_settings(ne_census, train.profile)
        isf_mult = opt_result.isf_ratio if opt_result.isf_ratio else 1.0
        cr_mult = opt_result.cr_ratio if opt_result.cr_ratio else 1.0
        basal_mult = opt_result.basal_ratio if opt_result.basal_ratio else 1.0
    except Exception as e:
        print(f"    settings optimizer failed: {e}, using default perturbation")
        isf_mult, cr_mult, basal_mult = 1.3, 1.0, 1.0  # fallback: 30% ISF increase

    # Run all 3 models on test period
    _, pred_A = simulate_tir_current(
        test.glucose, meta_test, hours_test,
        isf_mult=isf_mult, cr_mult=cr_mult, basal_mult=basal_mult)

    _, pred_B = simulate_tir_two_component(
        test.glucose, meta_test, hours_test,
        isf_mult=isf_mult, cr_mult=cr_mult, basal_mult=basal_mult)

    _, pred_C = simulate_tir_two_component_powerlaw(
        test.glucose, meta_test, hours_test,
        isf_mult=isf_mult, cr_mult=cr_mult, basal_mult=basal_mult)

    tir_delta_actual = tir_test - tir_train

    return PatientResult(
        patient_id=patient_id,
        n_train=train.n_samples,
        n_test=test.n_samples,
        actual_tir_train=tir_train,
        actual_tir_test=tir_test,
        isf_mult=isf_mult,
        cr_mult=cr_mult,
        basal_mult=basal_mult,
        predicted_tir_A=pred_A,
        tir_delta_pred_A=pred_A - tir_train,
        tir_delta_actual=tir_delta_actual,
        tir_mae_A=abs(pred_A - tir_test),
        predicted_tir_B=pred_B,
        tir_delta_pred_B=pred_B - tir_train,
        tir_mae_B=abs(pred_B - tir_test),
        predicted_tir_C=pred_C,
        tir_delta_pred_C=pred_C - tir_train,
        tir_mae_C=abs(pred_C - tir_test),
    )


# ── Aggregate Analysis ───────────────────────────────────────────────

@dataclass
class ExperimentResults:
    exp_id: str = "EXP-2551"
    title: str = "Two-Component DIA Simulation Accuracy"
    timestamp: str = ""
    n_patients: int = 0
    patients: List[dict] = field(default_factory=list)
    # Aggregate metrics
    mae_A: float = 0.0  # current perturbation
    mae_B: float = 0.0  # two-component DIA
    mae_C: float = 0.0  # two-component + power-law
    corr_A: float = 0.0
    corr_B: float = 0.0
    corr_C: float = 0.0
    winner: str = ""
    improvement_pp: float = 0.0


def aggregate(results: List[PatientResult]) -> ExperimentResults:
    """Compute aggregate metrics across patients."""
    exp = ExperimentResults(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_patients=len(results),
        patients=[asdict(r) for r in results],
    )

    mae_a = [r.tir_mae_A for r in results]
    mae_b = [r.tir_mae_B for r in results]
    mae_c = [r.tir_mae_C for r in results]

    exp.mae_A = float(np.mean(mae_a))
    exp.mae_B = float(np.mean(mae_b))
    exp.mae_C = float(np.mean(mae_c))

    # Correlation of predicted vs actual TIR delta
    actual_deltas = [r.tir_delta_actual for r in results]
    pred_a = [r.tir_delta_pred_A for r in results]
    pred_b = [r.tir_delta_pred_B for r in results]
    pred_c = [r.tir_delta_pred_C for r in results]

    if len(results) >= 3:
        exp.corr_A = float(np.corrcoef(actual_deltas, pred_a)[0, 1])
        exp.corr_B = float(np.corrcoef(actual_deltas, pred_b)[0, 1])
        exp.corr_C = float(np.corrcoef(actual_deltas, pred_c)[0, 1])
    else:
        exp.corr_A = exp.corr_B = exp.corr_C = float('nan')

    # Determine winner
    maes = {'A_perturbation': exp.mae_A, 'B_two_component': exp.mae_B,
            'C_two_comp_powerlaw': exp.mae_C}
    exp.winner = min(maes, key=maes.get)
    exp.improvement_pp = exp.mae_A - min(exp.mae_B, exp.mae_C)

    return exp


# ── Figures ──────────────────────────────────────────────────────────

def generate_figures(exp: ExperimentResults, out_dir: Path):
    """Generate visualization figures."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping figures")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    patients = exp.patients

    # Figure 1: TIR prediction MAE comparison (bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = [p['patient_id'] for p in patients]
    x = np.arange(len(labels))
    w = 0.25
    ax.bar(x - w, [p['tir_mae_A'] * 100 for p in patients], w,
           label=f'A: Perturbation (MAE={exp.mae_A*100:.1f}pp)', alpha=0.8)
    ax.bar(x, [p['tir_mae_B'] * 100 for p in patients], w,
           label=f'B: Two-Comp DIA (MAE={exp.mae_B*100:.1f}pp)', alpha=0.8)
    ax.bar(x + w, [p['tir_mae_C'] * 100 for p in patients], w,
           label=f'C: +Power-Law ISF (MAE={exp.mae_C*100:.1f}pp)', alpha=0.8)
    ax.set_xlabel('Patient')
    ax.set_ylabel('TIR Prediction Error (pp)')
    ax.set_title('EXP-2551: Simulation Model Comparison — TIR Prediction MAE')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / 'fig_2551_tir_mae_comparison.png', dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_dir / 'fig_2551_tir_mae_comparison.png'}")

    # Figure 2: Predicted vs Actual TIR delta scatter
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, key, label, corr in [
        (axes[0], 'tir_delta_pred_A', 'A: Perturbation', exp.corr_A),
        (axes[1], 'tir_delta_pred_B', 'B: Two-Comp DIA', exp.corr_B),
        (axes[2], 'tir_delta_pred_C', 'C: +Power-Law ISF', exp.corr_C),
    ]:
        actual = [p['tir_delta_actual'] * 100 for p in patients]
        predicted = [p[key] * 100 for p in patients]
        ax.scatter(actual, predicted, s=60, alpha=0.7)
        for i, pid in enumerate(labels):
            ax.annotate(pid, (actual[i], predicted[i]), fontsize=7,
                       textcoords='offset points', xytext=(3, 3))
        lims = [min(min(actual), min(predicted)) - 2,
                max(max(actual), max(predicted)) + 2]
        ax.plot(lims, lims, 'k--', alpha=0.3, label='Perfect')
        ax.set_xlabel('Actual TIR Δ (pp)')
        ax.set_ylabel('Predicted TIR Δ (pp)')
        ax.set_title(f'{label}\nr={corr:.3f}')
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.suptitle('EXP-2551: Predicted vs Actual TIR Change', fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / 'fig_2551_tir_delta_scatter.png', dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_dir / 'fig_2551_tir_delta_scatter.png'}")

    # Figure 3: Settings multipliers applied
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w, [p['isf_mult'] for p in patients], w, label='ISF mult')
    ax.bar(x, [p['cr_mult'] for p in patients], w, label='CR mult')
    ax.bar(x + w, [p['basal_mult'] for p in patients], w, label='Basal mult')
    ax.axhline(y=1.0, color='k', linestyle='--', alpha=0.3)
    ax.set_xlabel('Patient')
    ax.set_ylabel('Settings Multiplier')
    ax.set_title('EXP-2551: Optimized Settings Multipliers (from Train Period)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / 'fig_2551_settings_multipliers.png', dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_dir / 'fig_2551_settings_multipliers.png'}")


# ── Data Loading ─────────────────────────────────────────────────────

def load_patients() -> Dict[str, PatientData]:
    """Load patient data from parquet files."""
    parquet_dir = PROJECT_ROOT / "externals" / "data" / "parquet"
    if not parquet_dir.exists():
        # Try alternative location
        parquet_dir = PROJECT_ROOT / "externals" / "parquet"
    if not parquet_dir.exists():
        print(f"Parquet directory not found, generating synthetic data")
        return generate_synthetic_patients()

    patients = {}
    try:
        from cgmencode.production.test_production import make_glucose, make_profile
        # Try loading from parquet
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from ns2parquet import read_patient_parquet
        for pq_file in sorted(parquet_dir.glob("*.parquet")):
            pid = pq_file.stem
            try:
                patient = read_patient_parquet(pq_file)
                patients[pid] = patient
            except Exception as e:
                print(f"  skip {pid}: {e}")
    except ImportError:
        print("Parquet loader not available, using synthetic data")
        return generate_synthetic_patients()

    if not patients:
        return generate_synthetic_patients()
    return patients


def generate_synthetic_patients(n_patients: int = 11) -> Dict[str, PatientData]:
    """Generate synthetic patients for testing the simulation framework.

    Creates realistic glucose + insulin traces with known properties:
    - Different ISF and CR profiles (some miscalibrated)
    - Circadian variation
    - Meal boluses with insulin stacking
    - Known ground truth for validation
    """
    rng = np.random.RandomState(42)
    patient_ids = [chr(ord('a') + i) for i in range(n_patients)]
    patients = {}

    for i, pid in enumerate(patient_ids):
        n_days = 30 + rng.randint(0, 60)  # 30-90 days
        N = n_days * 288  # 5-min intervals

        # Patient-specific parameters
        true_isf = 30.0 + rng.uniform(-15, 30)     # mg/dL per U
        true_cr = 8.0 + rng.uniform(-3, 7)          # g per U
        true_basal = 0.5 + rng.uniform(0.0, 1.5)    # U/h

        # Scheduled (potentially miscalibrated) settings
        isf_error = 1.0 + rng.uniform(-0.4, 0.8)    # 0.6-1.8× of true
        cr_error = 1.0 + rng.uniform(-0.3, 0.5)
        sched_isf = true_isf * isf_error
        sched_cr = true_cr * cr_error

        # Generate glucose trace with circadian pattern
        t = np.arange(N, dtype=np.float64)
        hours = (t * 5.0 / 60.0) % 24.0
        ts_ms = (1700000000000 + t * 300000).astype(np.float64)

        # Base glucose with circadian
        base = 140.0 + 30.0 * np.sin(2 * np.pi * (hours - 5.0) / 24.0)
        noise = rng.normal(0, 8, N)
        glucose = base + noise

        # Add meals (3/day) with realistic excursions
        for day in range(n_days):
            for meal_hour, carbs_g in [(7.5, 40), (12.5, 50), (19.0, 60)]:
                idx = day * 288 + int(meal_hour * 12)
                if idx + 72 < N:
                    carb_var = carbs_g * rng.uniform(0.5, 1.5)
                    rise = carb_var * (true_isf / true_cr) * rng.uniform(0.6, 1.0)
                    profile_shape = np.exp(-np.arange(72) / 18.0) * (1 - np.exp(-np.arange(72) / 4.0))
                    profile_shape /= max(profile_shape.max(), 1e-6)
                    glucose[idx:idx + 72] += rise * profile_shape

        glucose = np.clip(glucose, 40, 400)

        # Generate IOB (insulin on board)
        iob = np.full(N, true_basal * 2.5)  # baseline IOB from basal
        for day in range(n_days):
            for meal_hour in [7.5, 12.5, 19.0]:
                idx = day * 288 + int(meal_hour * 12)
                if idx + 60 < N:
                    bolus = rng.uniform(1.0, 5.0)
                    decay = np.exp(-np.arange(60) / (true_isf * 0.1))
                    iob[idx:idx + 60] += bolus * decay

        # Generate bolus and carbs arrays
        bolus = np.zeros(N)
        carbs_arr = np.zeros(N)
        for day in range(n_days):
            for meal_hour, carbs_g in [(7.5, 40), (12.5, 50), (19.0, 60)]:
                idx = day * 288 + int(meal_hour * 12)
                if idx < N:
                    bolus[idx] = carbs_g / sched_cr
                    carbs_arr[idx] = carbs_g * rng.uniform(0.8, 1.2)

        # COB from carbs
        cob = np.zeros(N)
        for j in range(N):
            if carbs_arr[j] > 0:
                remaining = int(min(72, N - j))
                decay = np.exp(-np.arange(remaining) / 24.0)
                cob[j:j + remaining] += carbs_arr[j] * decay

        basal_rate = np.full(N, true_basal)

        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": sched_isf}],
            cr_schedule=[{"time": "00:00", "value": sched_cr}],
            basal_schedule=[{"time": "00:00", "value": true_basal}],
            dia_hours=5.0,
        )

        patients[pid] = PatientData(
            glucose=glucose,
            timestamps=ts_ms,
            profile=profile,
            iob=iob,
            cob=cob,
            bolus=bolus,
            carbs=carbs_arr,
            basal_rate=basal_rate,
        )

    return patients


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-2551: DIA Simulation Accuracy")
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--output', type=str, default=None,
                       help='Output JSON path')
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2551: Two-Component DIA Simulation Accuracy")
    print("=" * 70)

    # Load data
    print("\nLoading patient data...")
    patients = load_patients()
    print(f"  Loaded {len(patients)} patients")

    # Run per-patient experiments
    print("\nRunning simulation models (A/B/C) per patient...")
    results: List[PatientResult] = []
    for pid in sorted(patients.keys()):
        try:
            result = run_patient(patients[pid], pid)
            if result is not None:
                results.append(result)
                print(f"    MAE: A={result.tir_mae_A*100:.1f}pp  "
                      f"B={result.tir_mae_B*100:.1f}pp  "
                      f"C={result.tir_mae_C*100:.1f}pp")
        except Exception as e:
            print(f"    {pid} FAILED: {e}")

    if not results:
        print("ERROR: No patient results. Exiting.")
        sys.exit(1)

    # Aggregate
    exp = aggregate(results)

    # Print summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"\nPatients analyzed: {exp.n_patients}")
    print(f"\nTIR Prediction MAE (pp):")
    print(f"  A (current perturbation):     {exp.mae_A * 100:.2f} pp")
    print(f"  B (two-component DIA):        {exp.mae_B * 100:.2f} pp")
    print(f"  C (two-comp + power-law ISF): {exp.mae_C * 100:.2f} pp")
    print(f"\nPredicted vs Actual TIR-delta correlation:")
    print(f"  A: r = {exp.corr_A:.3f}")
    print(f"  B: r = {exp.corr_B:.3f}")
    print(f"  C: r = {exp.corr_C:.3f}")
    print(f"\nWinner: {exp.winner}")
    print(f"Improvement over baseline: {exp.improvement_pp * 100:.2f} pp")

    # Save results JSON
    out_path = args.output or str(
        PROJECT_ROOT / "externals" / "experiments" / "exp-2551_dia_simulation.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(asdict(exp), f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

    # Generate figures
    if args.figures:
        print("\nGenerating figures...")
        fig_dir = PROJECT_ROOT / "docs" / "60-research" / "figures"
        generate_figures(exp, fig_dir)

    return exp


if __name__ == '__main__':
    main()
