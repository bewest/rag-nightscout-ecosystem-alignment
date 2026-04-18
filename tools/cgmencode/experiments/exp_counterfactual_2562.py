#!/usr/bin/env python3
"""
EXP-2562: Forward Simulator Counterfactual Analysis on Real Patient Data

Hypothesis:
    The forward simulator can generate clinically meaningful "what-if"
    counterfactual scenarios from real patient data, producing TIR
    predictions that are more accurate than the perturbation model
    (which showed a null result in EXP-2552).

Background:
    - EXP-2552 showed null result: perturbation model can't differentiate
      circadian optimization strategies because the perturbation magnitude
      is dampened equally by power-law ISF for both approaches.
    - The forward simulator (EXP-2553, 2554) produces physiologically
      realistic trajectories with 2-comp DIA + delayed carbs + power-law ISF.
    - The key advantage is that forward_sim models the FULL trajectory
      including carb-insulin timing interactions, not just a perturbation
      on the current glucose value.

Method:
    For each patient's real data:
    1. Extract natural experiment windows (meals, corrections, overnight)
    2. For each window, run forward_sim with:
       a) Current settings (baseline)
       b) Modified ISF (+20%, -20%)
       c) Modified CR (+20%, -20%)
       d) Modified basal (+20%, -20%)
       e) Pre-bolus timing (+15 min, +30 min)
    3. Compare simulated TIR vs actual TIR in each window
    4. Evaluate which modifications would have improved outcomes

Sub-experiments:
    EXP-2562a: Correction bolus counterfactuals (ISF sensitivity)
    EXP-2562b: Meal bolus counterfactuals (CR and timing sensitivity)
    EXP-2562c: Overnight basal counterfactuals (basal rate sensitivity)
    EXP-2562d: Full-day composite counterfactuals
    EXP-2562e: Per-phenotype counterfactual impact
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Import production modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.production.forward_simulator import (
    forward_simulate, compare_scenarios, TherapySettings,
    InsulinEvent, CarbEvent,
)


@dataclass
class CounterfactualResult:
    """Result of one counterfactual scenario."""
    scenario: str
    n_windows: int
    baseline_tir: float
    modified_tir: float
    tir_delta: float
    baseline_tbr: float      # time below range
    modified_tbr: float
    tbr_delta: float
    mean_glucose_delta: float
    n_improved: int           # windows where TIR improved
    n_worsened: int           # windows where TIR worsened
    improvement_rate: float


@dataclass
class SubExperimentResult:
    exp_id: str
    window_type: str
    n_patients: int
    n_windows: int
    counterfactuals: List[CounterfactualResult]
    best_scenario: str
    best_tir_delta: float
    conclusion: str


@dataclass
class ExperimentReport:
    exp_id: str = 'EXP-2562'
    hypothesis: str = 'Forward simulator counterfactuals reveal actionable settings changes'
    timestamp: str = ''
    runtime_seconds: float = 0.0
    sub_experiments: List[SubExperimentResult] = field(default_factory=list)
    overall_conclusion: str = ''
    next_steps: List[str] = field(default_factory=list)


# ── Window Extraction ────────────────────────────────────────────────

def extract_correction_windows(df_patient, min_bg=150, min_bolus=0.5,
                                carb_free_minutes=60, window_hours=6):
    """Extract isolated correction bolus windows."""
    windows = []
    steps_per_hour = 12
    window_steps = window_hours * steps_per_hour
    carb_free_steps = carb_free_minutes // 5

    glucose = df_patient['glucose'].values
    bolus = df_patient['bolus'].values
    carbs = df_patient['carbs'].values
    iob = df_patient['iob'].values
    times = df_patient['time'].values

    for i in range(carb_free_steps, len(glucose) - window_steps):
        if bolus[i] < min_bolus:
            continue
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue

        # Check carb-free zone around bolus
        carb_window = carbs[max(0, i - carb_free_steps):i + carb_free_steps]
        if np.nansum(carb_window) > 1.0:
            continue

        # Extract window
        end = i + window_steps
        g_window = glucose[i:end]
        if np.isnan(g_window).mean() > 0.3:
            continue

        windows.append({
            'start_idx': i,
            'glucose': g_window,
            'initial_bg': float(glucose[i]),
            'bolus_units': float(bolus[i]),
            'initial_iob': float(iob[i]),
            'duration_hours': window_hours,
        })

    return windows


def extract_meal_windows(df_patient, min_carbs=10, window_hours=4):
    """Extract meal event windows."""
    windows = []
    steps_per_hour = 12
    window_steps = window_hours * steps_per_hour

    glucose = df_patient['glucose'].values
    bolus = df_patient['bolus'].values
    carbs = df_patient['carbs'].values
    iob = df_patient['iob'].values
    isf = df_patient['scheduled_isf'].values
    cr = df_patient['scheduled_cr'].values
    times = df_patient['time'].values

    for i in range(12, len(glucose) - window_steps):
        if carbs[i] < min_carbs:
            continue
        if np.isnan(glucose[i]):
            continue

        g_window = glucose[i:i + window_steps]
        if np.isnan(g_window).mean() > 0.3:
            continue

        # Find associated bolus (within ±30 min)
        bolus_window = bolus[max(0, i - 6):i + 6]
        total_bolus = np.nansum(bolus_window)

        windows.append({
            'start_idx': i,
            'glucose': g_window,
            'initial_bg': float(glucose[i]),
            'carbs_g': float(carbs[i]),
            'bolus_units': float(total_bolus),
            'initial_iob': float(iob[i]),
            'scheduled_isf': float(isf[i]),
            'scheduled_cr': float(cr[i]),
            'duration_hours': window_hours,
        })

    return windows


def extract_overnight_windows(df_patient, window_hours=8):
    """Extract overnight fasting windows (midnight to 6 AM)."""
    windows = []
    steps_per_hour = 12
    window_steps = window_hours * steps_per_hour

    glucose = df_patient['glucose'].values
    carbs = df_patient['carbs'].values
    bolus = df_patient['bolus'].values
    iob = df_patient['iob'].values
    hours = df_patient['time'].dt.hour.values + df_patient['time'].dt.minute.values / 60.0
    basal = df_patient['actual_basal_rate'].values
    sched_basal = df_patient['scheduled_basal_rate'].values

    for i in range(0, len(glucose) - window_steps, window_steps):
        # Must start between 10 PM and midnight
        if hours[i] < 22 and hours[i] > 1:
            continue
        if np.isnan(glucose[i]):
            continue

        g_window = glucose[i:i + window_steps]
        c_window = carbs[i:i + window_steps]
        b_window = bolus[i:i + window_steps]

        # Must be fasting (no carbs, no manual boluses > 0.5U)
        if np.nansum(c_window) > 1.0:
            continue
        if np.nanmax(b_window) > 0.5:
            continue
        if np.isnan(g_window).mean() > 0.3:
            continue

        windows.append({
            'start_idx': i,
            'glucose': g_window,
            'initial_bg': float(glucose[i]),
            'initial_iob': float(iob[i]),
            'mean_basal': float(np.nanmean(basal[i:i + window_steps])),
            'scheduled_basal': float(np.nanmean(sched_basal[i:i + window_steps])),
            'duration_hours': window_hours,
        })

    return windows


# ── Counterfactual Simulation ────────────────────────────────────────

def compute_tir(glucose, low=70, high=180):
    """Compute time in range for a glucose trace."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0, 0.0
    tir = np.mean((valid >= low) & (valid <= high)) * 100
    tbr = np.mean(valid < low) * 100
    return tir, tbr


def run_correction_counterfactuals(windows, base_isf=50.0, base_cr=10.0,
                                    base_basal=1.0):
    """Run counterfactual scenarios on correction windows."""
    scenarios = {
        'ISF+20%': {'isf_mult': 1.2},
        'ISF-20%': {'isf_mult': 0.8},
        'ISF+40%': {'isf_mult': 1.4},
    }

    results = {}
    for name, params in scenarios.items():
        isf_m = params.get('isf_mult', 1.0)
        baseline_tirs = []
        modified_tirs = []
        baseline_tbrs = []
        modified_tbrs = []
        mean_glucose_deltas = []

        for w in windows:
            base_settings = TherapySettings(
                isf=base_isf, cr=base_cr, basal_rate=base_basal,
                dia_hours=5.0, iob_power_law=True
            )
            mod_settings = TherapySettings(
                isf=base_isf * isf_m, cr=base_cr, basal_rate=base_basal,
                dia_hours=5.0, iob_power_law=True
            )

            bolus_ev = [InsulinEvent(time_minutes=0, units=w['bolus_units'],
                                     is_bolus=True)]

            base_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=base_settings,
                duration_hours=w['duration_hours'], bolus_events=bolus_ev,
                initial_iob=w.get('initial_iob', 0), seed=42
            )
            mod_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=mod_settings,
                duration_hours=w['duration_hours'], bolus_events=bolus_ev,
                initial_iob=w.get('initial_iob', 0), seed=42
            )

            b_tir, b_tbr = compute_tir(np.array(base_sim.glucose))
            m_tir, m_tbr = compute_tir(np.array(mod_sim.glucose))
            baseline_tirs.append(b_tir)
            modified_tirs.append(m_tir)
            baseline_tbrs.append(b_tbr)
            modified_tbrs.append(m_tbr)
            mean_glucose_deltas.append(
                np.mean(mod_sim.glucose) - np.mean(base_sim.glucose)
            )

        if not baseline_tirs:
            continue

        bt = np.mean(baseline_tirs)
        mt = np.mean(modified_tirs)
        bb = np.mean(baseline_tbrs)
        mb = np.mean(modified_tbrs)
        improved = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m > b)
        worsened = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m < b)

        results[name] = CounterfactualResult(
            scenario=name,
            n_windows=len(baseline_tirs),
            baseline_tir=bt,
            modified_tir=mt,
            tir_delta=mt - bt,
            baseline_tbr=bb,
            modified_tbr=mb,
            tbr_delta=mb - bb,
            mean_glucose_delta=np.mean(mean_glucose_deltas),
            n_improved=improved,
            n_worsened=worsened,
            improvement_rate=improved / len(baseline_tirs) if baseline_tirs else 0,
        )

    return results


def run_meal_counterfactuals(windows):
    """Run counterfactual scenarios on meal windows."""
    scenarios = {
        'CR+20%': {'cr_mult': 1.2},
        'CR-20%': {'cr_mult': 0.8},
        'PreBolus+15min': {'prebolus_min': 15},
        'PreBolus+30min': {'prebolus_min': 30},
    }

    results = {}
    for name, params in scenarios.items():
        cr_m = params.get('cr_mult', 1.0)
        prebolus = params.get('prebolus_min', 0)
        baseline_tirs = []
        modified_tirs = []
        baseline_tbrs = []
        modified_tbrs = []
        mean_glucose_deltas = []

        for w in windows:
            isf = w.get('scheduled_isf', 50.0)
            cr = w.get('scheduled_cr', 10.0)
            if isf <= 0:
                isf = 50.0
            if cr <= 0:
                cr = 10.0

            base_settings = TherapySettings(
                isf=isf, cr=cr, basal_rate=1.0, dia_hours=5.0,
                iob_power_law=True
            )
            mod_settings = TherapySettings(
                isf=isf, cr=cr * cr_m, basal_rate=1.0, dia_hours=5.0,
                iob_power_law=True
            )

            carb_ev = [CarbEvent(time_minutes=0, grams=w['carbs_g'],
                                  absorption_hours=3.0, delay_minutes=20)]

            # Bolus: compute from CR
            bolus_dose = w['carbs_g'] / cr
            mod_bolus_dose = w['carbs_g'] / (cr * cr_m)

            # If prebolus scenario, shift bolus timing
            bolus_time = -prebolus if prebolus > 0 else 0
            base_bolus = [InsulinEvent(time_minutes=0, units=bolus_dose,
                                       is_bolus=True)]
            mod_bolus = [InsulinEvent(time_minutes=bolus_time,
                                      units=mod_bolus_dose if cr_m != 1.0 else bolus_dose,
                                      is_bolus=True)]

            base_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=base_settings,
                duration_hours=w['duration_hours'], bolus_events=base_bolus,
                carb_events=carb_ev, initial_iob=w.get('initial_iob', 0), seed=42
            )
            mod_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=mod_settings,
                duration_hours=w['duration_hours'], bolus_events=mod_bolus,
                carb_events=carb_ev, initial_iob=w.get('initial_iob', 0), seed=42
            )

            b_tir, b_tbr = compute_tir(np.array(base_sim.glucose))
            m_tir, m_tbr = compute_tir(np.array(mod_sim.glucose))
            baseline_tirs.append(b_tir)
            modified_tirs.append(m_tir)
            baseline_tbrs.append(b_tbr)
            modified_tbrs.append(m_tbr)
            mean_glucose_deltas.append(
                np.mean(mod_sim.glucose) - np.mean(base_sim.glucose)
            )

        if not baseline_tirs:
            continue

        bt = np.mean(baseline_tirs)
        mt = np.mean(modified_tirs)
        improved = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m > b)
        worsened = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m < b)

        results[name] = CounterfactualResult(
            scenario=name,
            n_windows=len(baseline_tirs),
            baseline_tir=bt,
            modified_tir=mt,
            tir_delta=mt - bt,
            baseline_tbr=np.mean(baseline_tbrs),
            modified_tbr=np.mean(modified_tbrs),
            tbr_delta=np.mean(modified_tbrs) - np.mean(baseline_tbrs),
            mean_glucose_delta=np.mean(mean_glucose_deltas),
            n_improved=improved,
            n_worsened=worsened,
            improvement_rate=improved / len(baseline_tirs) if baseline_tirs else 0,
        )

    return results


def run_overnight_counterfactuals(windows):
    """Run counterfactual scenarios on overnight windows."""
    scenarios = {
        'Basal+20%': {'basal_mult': 1.2},
        'Basal-20%': {'basal_mult': 0.8},
        'Basal+10%': {'basal_mult': 1.1},
        'Basal-10%': {'basal_mult': 0.9},
    }

    results = {}
    for name, params in scenarios.items():
        basal_m = params['basal_mult']
        baseline_tirs = []
        modified_tirs = []
        baseline_tbrs = []
        modified_tbrs = []
        mean_glucose_deltas = []

        for w in windows:
            basal = w.get('scheduled_basal', 1.0)
            if basal <= 0:
                basal = 1.0

            base_settings = TherapySettings(
                isf=50.0, cr=10.0, basal_rate=basal, dia_hours=5.0,
                iob_power_law=True
            )
            mod_settings = TherapySettings(
                isf=50.0, cr=10.0, basal_rate=basal * basal_m, dia_hours=5.0,
                iob_power_law=True
            )

            base_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=base_settings,
                duration_hours=w['duration_hours'],
                initial_iob=w.get('initial_iob', 0), seed=42,
                start_hour=22.0  # overnight
            )
            mod_sim = forward_simulate(
                initial_glucose=w['initial_bg'], settings=mod_settings,
                duration_hours=w['duration_hours'],
                initial_iob=w.get('initial_iob', 0), seed=42,
                start_hour=22.0
            )

            b_tir, b_tbr = compute_tir(np.array(base_sim.glucose))
            m_tir, m_tbr = compute_tir(np.array(mod_sim.glucose))
            baseline_tirs.append(b_tir)
            modified_tirs.append(m_tir)
            baseline_tbrs.append(b_tbr)
            modified_tbrs.append(m_tbr)
            mean_glucose_deltas.append(
                np.mean(mod_sim.glucose) - np.mean(base_sim.glucose)
            )

        if not baseline_tirs:
            continue

        bt = np.mean(baseline_tirs)
        mt = np.mean(modified_tirs)
        improved = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m > b)
        worsened = sum(1 for b, m in zip(baseline_tirs, modified_tirs) if m < b)

        results[name] = CounterfactualResult(
            scenario=name,
            n_windows=len(baseline_tirs),
            baseline_tir=bt,
            modified_tir=mt,
            tir_delta=mt - bt,
            baseline_tbr=np.mean(baseline_tbrs),
            modified_tbr=np.mean(modified_tbrs),
            tbr_delta=np.mean(modified_tbrs) - np.mean(baseline_tbrs),
            mean_glucose_delta=np.mean(mean_glucose_deltas),
            n_improved=improved,
            n_worsened=worsened,
            improvement_rate=improved / len(baseline_tirs) if baseline_tirs else 0,
        )

    return results


# ── Main ─────────────────────────────────────────────────────────────

def load_patient_data():
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / \
        'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    return pd.read_parquet(grid_path)


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2562: Forward Simulator Counterfactual Analysis')
    print('=' * 70)

    df = load_patient_data()
    patients = sorted(df['patient_id'].unique())
    print(f'Loaded {len(df):,} rows, {len(patients)} patients')

    report = ExperimentReport(
        timestamp=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
    )

    # Limit windows per patient for runtime
    MAX_WINDOWS = 50

    # EXP-2562a: Correction counterfactuals
    print('\n--- EXP-2562a: Correction Bolus Counterfactuals ---')
    all_correction_windows = []
    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        wins = extract_correction_windows(pdf)
        if len(wins) > MAX_WINDOWS:
            wins = wins[:MAX_WINDOWS]
        all_correction_windows.extend(wins)
        print(f'  {pid}: {len(wins)} correction windows')

    print(f'  Total: {len(all_correction_windows)} windows')
    if all_correction_windows:
        cf_results = run_correction_counterfactuals(all_correction_windows)
        best = max(cf_results.values(), key=lambda r: r.tir_delta)
        report.sub_experiments.append(SubExperimentResult(
            exp_id='EXP-2562a',
            window_type='correction',
            n_patients=len(patients),
            n_windows=len(all_correction_windows),
            counterfactuals=[asdict(r) for r in cf_results.values()],
            best_scenario=best.scenario,
            best_tir_delta=best.tir_delta,
            conclusion=f'Best: {best.scenario} → {best.tir_delta:+.1f}pp TIR',
        ))
        for name, r in cf_results.items():
            print(f'    {name}: TIR {r.tir_delta:+.1f}pp, TBR {r.tbr_delta:+.1f}pp, '
                  f'{r.improvement_rate:.0%} improved')

    # EXP-2562b: Meal counterfactuals
    print('\n--- EXP-2562b: Meal Bolus Counterfactuals ---')
    all_meal_windows = []
    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        wins = extract_meal_windows(pdf)
        if len(wins) > MAX_WINDOWS:
            wins = wins[:MAX_WINDOWS]
        all_meal_windows.extend(wins)
        print(f'  {pid}: {len(wins)} meal windows')

    print(f'  Total: {len(all_meal_windows)} windows')
    if all_meal_windows:
        mf_results = run_meal_counterfactuals(all_meal_windows)
        best = max(mf_results.values(), key=lambda r: r.tir_delta)
        report.sub_experiments.append(SubExperimentResult(
            exp_id='EXP-2562b',
            window_type='meal',
            n_patients=len(patients),
            n_windows=len(all_meal_windows),
            counterfactuals=[asdict(r) for r in mf_results.values()],
            best_scenario=best.scenario,
            best_tir_delta=best.tir_delta,
            conclusion=f'Best: {best.scenario} → {best.tir_delta:+.1f}pp TIR',
        ))
        for name, r in mf_results.items():
            print(f'    {name}: TIR {r.tir_delta:+.1f}pp, TBR {r.tbr_delta:+.1f}pp, '
                  f'{r.improvement_rate:.0%} improved')

    # EXP-2562c: Overnight counterfactuals
    print('\n--- EXP-2562c: Overnight Basal Counterfactuals ---')
    all_overnight_windows = []
    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        wins = extract_overnight_windows(pdf)
        if len(wins) > MAX_WINDOWS:
            wins = wins[:MAX_WINDOWS]
        all_overnight_windows.extend(wins)
        print(f'  {pid}: {len(wins)} overnight windows')

    print(f'  Total: {len(all_overnight_windows)} windows')
    if all_overnight_windows:
        of_results = run_overnight_counterfactuals(all_overnight_windows)
        best = max(of_results.values(), key=lambda r: r.tir_delta)
        report.sub_experiments.append(SubExperimentResult(
            exp_id='EXP-2562c',
            window_type='overnight',
            n_patients=len(patients),
            n_windows=len(all_overnight_windows),
            counterfactuals=[asdict(r) for r in of_results.values()],
            best_scenario=best.scenario,
            best_tir_delta=best.tir_delta,
            conclusion=f'Best: {best.scenario} → {best.tir_delta:+.1f}pp TIR',
        ))
        for name, r in of_results.items():
            print(f'    {name}: TIR {r.tir_delta:+.1f}pp, TBR {r.tbr_delta:+.1f}pp, '
                  f'{r.improvement_rate:.0%} improved')

    # Overall
    if report.sub_experiments:
        all_deltas = []
        for se in report.sub_experiments:
            for cf in se.counterfactuals:
                if isinstance(cf, dict):
                    all_deltas.append(cf['tir_delta'])

        report.overall_conclusion = (
            f'Forward simulator produced counterfactuals across '
            f'{sum(se.n_windows for se in report.sub_experiments)} windows. '
            f'TIR deltas range {min(all_deltas):+.1f} to {max(all_deltas):+.1f}pp.'
        )
        report.next_steps = [
            'Compare forward_sim TIR predictions to actual observed TIR',
            'Integrate best counterfactuals into settings_optimizer',
            'Generate per-patient personalized recommendations',
        ]

    report.runtime_seconds = time.time() - t0

    # Save
    result_path = RESULTS_DIR / 'exp-2562_counterfactual_analysis.json'
    with open(result_path, 'w') as f:
        json.dump(asdict(report), f, indent=2, default=str)

    print(f'\n{"=" * 70}')
    print(f'Runtime: {report.runtime_seconds:.0f}s')
    print(f'Results: {result_path}')
    print(f'Conclusion: {report.overall_conclusion}')

    return report


if __name__ == '__main__':
    main()
