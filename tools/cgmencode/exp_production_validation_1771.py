#!/usr/bin/env python3
"""EXP-1771 to EXP-1775: Production Validation & Autoproductionization.

Validates research findings against the production pipeline's Hill-equation
metabolic engine before applying fixes. Tests:

  EXP-1771: Hepatic base rate comparison (prod=1.0 vs research=1.5)
  EXP-1772: Demand calibration in Hill model (fasting drift test)
  EXP-1773: UAM threshold consistency (1.0 vs 3.0 mg/dL/5min)
  EXP-1774: 4-harmonic vs 1st-harmonic temporal encoding
  EXP-1775: Rescue carb detection with Hill-model S×D

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_production_validation_1771.py --figures
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings('ignore', category=RuntimeWarning)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path('externals/ns-data/patients')
RESULTS_DIR = Path('externals/experiments')
FIGURES_DIR = Path('docs/60-research/figures')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
LOW = 70.0
HIGH = 180.0


def _get_isf(pat):
    sched = pat['df'].attrs.get('isf_schedule', [])
    if not sched:
        return 50.0
    vals = [s['value'] for s in sched]
    mean_isf = np.mean(vals)
    if mean_isf < 15:
        mean_isf *= 18.0182
    return mean_isf


def _get_basal(pat):
    sched = pat['df'].attrs.get('basal_schedule', [])
    if not sched:
        return 1.0
    return np.mean([s['value'] for s in sched])


def _get_cr(pat):
    sched = pat['df'].attrs.get('cr_schedule', [])
    if not sched:
        return 10.0
    return np.mean([s['value'] for s in sched])


def _extract_hours(timestamps):
    """Extract fractional hours from Unix timestamps (ms)."""
    ts = np.asarray(timestamps, dtype=np.float64)
    seconds = ts / 1000.0 if ts.max() > 1e12 else ts
    return (seconds % 86400) / 3600.0


def _hill_hepatic(iob, hours, base_egp, hill_n=1.5, hill_k=2.0, circ_amp=0.15):
    """Hill-equation hepatic production (production model)."""
    iob_safe = np.maximum(np.nan_to_num(iob, nan=0.0), 0.0)
    suppression = iob_safe ** hill_n / (iob_safe ** hill_n + hill_k ** hill_n)
    egp_insulin = base_egp * (1.0 - suppression)
    circadian = 1.0 + circ_amp * np.sin(2.0 * np.pi * (hours - 5.0) / 24.0)
    return np.maximum(egp_insulin * circadian, 0.0)


def _production_supply_demand(pat, base_egp=1.0, calibrate=False):
    """Replicate production metabolic_engine logic with configurable params."""
    df = pat['df']
    glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=120.0)
    iob = np.nan_to_num(df['iob'].values.astype(float), nan=0.0)
    carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)
    N = len(glucose)

    timestamps = df['date'].values if 'date' in df.columns else np.arange(N) * 300000
    ts_float = timestamps.astype(np.int64) if hasattr(timestamps, 'astype') else np.array(timestamps, dtype=np.int64)
    hours = (ts_float / 1000 % 86400) / 3600.0

    isf = _get_isf(pat)
    cr = _get_cr(pat)
    basal = _get_basal(pat)

    # Hepatic production (Hill equation)
    hepatic = _hill_hepatic(iob, hours, base_egp)

    # Carb supply from entered carbs (simplified COB model)
    cob_vals = df['cob'].values.astype(float) if 'cob' in df.columns else np.zeros(N)
    cob_vals = np.nan_to_num(cob_vals, nan=0.0)
    delta_cob = np.zeros(N)
    delta_cob[1:] = cob_vals[:-1] - cob_vals[1:]
    carb_supply = np.abs(delta_cob * (isf / max(cr, 1.0)))

    supply = hepatic + carb_supply

    # Demand from IOB deltas
    delta_iob = np.zeros(N)
    delta_iob[1:] = iob[:-1] - iob[1:]
    demand = np.abs(delta_iob * isf)

    # Optional demand calibration (research method ported to Hill model)
    if calibrate:
        demand_at_basal = basal * isf / 12.0  # mg/dL per step at scheduled basal
        # Mean hepatic at typical IOB (~basal IOB ≈ basal × DIA/2)
        typical_iob = basal * 2.5  # ~half of 5h DIA accumulation
        mean_hepatic = float(np.mean(_hill_hepatic(
            np.full(288, typical_iob), np.linspace(0, 24, 288), base_egp)))
        if demand_at_basal > 0.01:
            cal_factor = mean_hepatic / demand_at_basal
            demand = demand * cal_factor

    supply = np.maximum(supply, 0.0)
    demand = np.maximum(demand, 0.0)
    net = supply - demand

    # Actual dBG/dt
    actual_dbg = np.zeros(N)
    actual_dbg[1:] = np.diff(glucose)

    return {
        'supply': supply, 'demand': demand, 'net': net,
        'hepatic': hepatic, 'carb_supply': carb_supply,
        'glucose': glucose, 'actual_dbg': actual_dbg,
        'hours': hours, 'iob': iob,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1771: Hepatic Base Rate Comparison
# ═══════════════════════════════════════════════════════════════════════

def exp_1771_hepatic_base_rate(patients, make_figures=False):
    """Compare production (1.0) vs research (1.5) hepatic base rate.

    Tests which base rate produces better residuals during fasting windows
    (when supply ≈ hepatic only, no carbs, low IOB).
    """
    print("\n" + "="*70)
    print("EXP-1771: Hepatic Base Rate Comparison (1.0 vs 1.5)")
    print("="*70)

    results_by_patient = {}
    all_fasting_residuals = {1.0: [], 1.5: []}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0.0)

        # Find fasting windows: no carbs for 3h, low bolus activity
        fasting_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(STEPS_PER_HOUR * 3, len(glucose)):
            window_carbs = np.nansum(carbs[i - STEPS_PER_HOUR * 3:i])
            if window_carbs < 1.0 and not np.isnan(glucose[i]):
                fasting_mask[i] = True

        if fasting_mask.sum() < 100:
            print(f"  Patient {pid}: insufficient fasting windows ({fasting_mask.sum()} steps)")
            continue

        patient_results = {}
        for base_rate in [1.0, 1.5]:
            sd = _production_supply_demand(pat, base_egp=base_rate)
            # Residual during fasting: actual_dBG - predicted_net
            residual = sd['actual_dbg'] - sd['net']
            fasting_res = residual[fasting_mask]
            valid = np.isfinite(fasting_res)
            if valid.sum() < 50:
                continue

            fasting_res = fasting_res[valid]
            mean_res = float(np.mean(fasting_res))
            std_res = float(np.std(fasting_res))
            rmse = float(np.sqrt(np.mean(fasting_res**2)))
            # Bias: mean residual (positive = model under-predicts supply)
            patient_results[base_rate] = {
                'mean_residual': mean_res,
                'std_residual': std_res,
                'rmse': rmse,
                'n_fasting_steps': int(valid.sum()),
            }
            all_fasting_residuals[base_rate].extend(fasting_res.tolist())

        if len(patient_results) == 2:
            better = 1.0 if patient_results[1.0]['rmse'] < patient_results[1.5]['rmse'] else 1.5
            print(f"  Patient {pid}: base=1.0 RMSE={patient_results[1.0]['rmse']:.3f}, "
                  f"base=1.5 RMSE={patient_results[1.5]['rmse']:.3f} → better={better}")
            results_by_patient[pid] = patient_results

    # Population summary
    pop = {}
    for base_rate in [1.0, 1.5]:
        arr = np.array(all_fasting_residuals[base_rate])
        if len(arr) > 0:
            pop[str(base_rate)] = {
                'mean_residual': float(np.mean(arr)),
                'std_residual': float(np.std(arr)),
                'rmse': float(np.sqrt(np.mean(arr**2))),
                'mean_bias_abs': float(np.mean(np.abs(arr))),
                'n_total': len(arr),
            }
            print(f"\n  Population base={base_rate}: RMSE={pop[str(base_rate)]['rmse']:.3f}, "
                  f"bias={pop[str(base_rate)]['mean_residual']:.3f}")

    # Count which is better per patient
    better_counts = {1.0: 0, 1.5: 0}
    for pid, pr in results_by_patient.items():
        better = 1.0 if pr[1.0]['rmse'] < pr[1.5]['rmse'] else 1.5
        better_counts[better] += 1
    print(f"\n  Patient vote: base=1.0 wins {better_counts[1.0]}, base=1.5 wins {better_counts[1.5]}")

    result = {
        'experiment_id': 'EXP-1771',
        'title': 'Hepatic Base Rate Comparison in Hill Model',
        'population': pop,
        'per_patient': {pid: {str(k): v for k, v in pr.items()}
                        for pid, pr in results_by_patient.items()},
        'better_count_1_0': better_counts[1.0],
        'better_count_1_5': better_counts[1.5],
        'results': {
            'rmse_1_0': pop.get('1.0', {}).get('rmse', 0),
            'rmse_1_5': pop.get('1.5', {}).get('rmse', 0),
            'bias_1_0': pop.get('1.0', {}).get('mean_residual', 0),
            'bias_1_5': pop.get('1.5', {}).get('mean_residual', 0),
            'winner': '1.0' if pop.get('1.0', {}).get('rmse', 99) < pop.get('1.5', {}).get('rmse', 99) else '1.5',
        },
    }

    if make_figures:
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        # Panel A: RMSE comparison per patient
        pids = sorted(results_by_patient.keys())
        rmse_1 = [results_by_patient[p][1.0]['rmse'] for p in pids]
        rmse_15 = [results_by_patient[p][1.5]['rmse'] for p in pids]
        x = np.arange(len(pids))
        axes[0].bar(x - 0.15, rmse_1, 0.3, label='base=1.0 (production)', color='#e74c3c', alpha=0.8)
        axes[0].bar(x + 0.15, rmse_15, 0.3, label='base=1.5 (research)', color='#2ecc71', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(pids)
        axes[0].set_ylabel('Fasting RMSE (mg/dL/step)')
        axes[0].set_title('A: Hepatic Base Rate → Fasting RMSE')
        axes[0].legend()

        # Panel B: Bias comparison
        bias_1 = [results_by_patient[p][1.0]['mean_residual'] for p in pids]
        bias_15 = [results_by_patient[p][1.5]['mean_residual'] for p in pids]
        axes[1].bar(x - 0.15, bias_1, 0.3, label='base=1.0', color='#e74c3c', alpha=0.8)
        axes[1].bar(x + 0.15, bias_15, 0.3, label='base=1.5', color='#2ecc71', alpha=0.8)
        axes[1].axhline(0, color='black', linestyle='--', alpha=0.3)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(pids)
        axes[1].set_ylabel('Mean Fasting Bias (mg/dL/step)')
        axes[1].set_title('B: Fasting Bias (0 = perfect)')
        axes[1].legend()

        # Panel C: Residual distributions
        for base_rate, color, label in [(1.0, '#e74c3c', 'base=1.0'), (1.5, '#2ecc71', 'base=1.5')]:
            arr = np.array(all_fasting_residuals[base_rate])
            if len(arr) > 0:
                axes[2].hist(arr, bins=100, alpha=0.5, color=color, label=label, density=True)
        axes[2].axvline(0, color='black', linestyle='--', alpha=0.3)
        axes[2].set_xlabel('Fasting Residual (mg/dL/step)')
        axes[2].set_ylabel('Density')
        axes[2].set_title('C: Residual Distributions')
        axes[2].set_xlim(-10, 10)
        axes[2].legend()

        plt.tight_layout()
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGURES_DIR / 'prod-fig1-hepatic-base-rate.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: prod-fig1-hepatic-base-rate.png")

    return result


# ═══════════════════════════════════════════════════════════════════════
# EXP-1772: Demand Calibration in Hill Model
# ═══════════════════════════════════════════════════════════════════════

def exp_1772_demand_calibration(patients, make_figures=False):
    """Test whether demand calibration improves Hill-model fasting predictions.

    At scheduled basal rate, demand should equal hepatic production (steady state).
    Without calibration, demand = |ΔIOB| × ISF which may not balance hepatic.
    """
    print("\n" + "="*70)
    print("EXP-1772: Demand Calibration in Hill Model")
    print("="*70)

    results_by_patient = {}
    all_fasting_drift = {'uncalibrated': [], 'calibrated': []}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        # Find fasting windows
        fasting_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(STEPS_PER_HOUR * 3, len(glucose)):
            window_carbs = np.nansum(carbs[i - STEPS_PER_HOUR * 3:i])
            if window_carbs < 1.0 and not np.isnan(glucose[i]):
                fasting_mask[i] = True

        if fasting_mask.sum() < 100:
            continue

        patient_results = {}
        for label, cal in [('uncalibrated', False), ('calibrated', True)]:
            # Use best base rate from EXP-1771 (we'll use 1.5 as reference)
            sd = _production_supply_demand(pat, base_egp=1.5, calibrate=cal)
            residual = sd['actual_dbg'] - sd['net']
            fasting_res = residual[fasting_mask]
            valid = np.isfinite(fasting_res)
            if valid.sum() < 50:
                continue

            fasting_res = fasting_res[valid]

            # Fasting drift: mean predicted net flux during fasting
            # Should be ~0 if model is well-calibrated
            fasting_net = sd['net'][fasting_mask]
            valid_net = np.isfinite(fasting_net)
            mean_predicted_drift = float(np.mean(fasting_net[valid_net])) if valid_net.sum() > 0 else 0

            patient_results[label] = {
                'rmse': float(np.sqrt(np.mean(fasting_res**2))),
                'mean_residual': float(np.mean(fasting_res)),
                'predicted_drift': mean_predicted_drift,
                'supply_mean': float(np.mean(sd['supply'][fasting_mask])),
                'demand_mean': float(np.mean(sd['demand'][fasting_mask])),
            }
            all_fasting_drift[label].extend(fasting_res.tolist())

        if len(patient_results) == 2:
            better = 'calibrated' if patient_results['calibrated']['rmse'] < patient_results['uncalibrated']['rmse'] else 'uncalibrated'
            print(f"  Patient {pid}: uncal RMSE={patient_results['uncalibrated']['rmse']:.3f} "
                  f"drift={patient_results['uncalibrated']['predicted_drift']:.3f}, "
                  f"cal RMSE={patient_results['calibrated']['rmse']:.3f} "
                  f"drift={patient_results['calibrated']['predicted_drift']:.3f} → {better}")
            results_by_patient[pid] = patient_results

    # Also compare with research model
    research_residuals = []
    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        fasting_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(STEPS_PER_HOUR * 3, len(glucose)):
            window_carbs = np.nansum(carbs[i - STEPS_PER_HOUR * 3:i])
            if window_carbs < 1.0 and not np.isnan(glucose[i]):
                fasting_mask[i] = True

        if fasting_mask.sum() < 100:
            continue

        try:
            sd_research = compute_supply_demand(df, calibrate=True)
            residual = np.zeros(len(glucose))
            actual_dbg = np.zeros(len(glucose))
            actual_dbg[1:] = np.diff(glucose)
            residual = actual_dbg - sd_research['net']
            fasting_res = residual[fasting_mask]
            valid = np.isfinite(fasting_res)
            if valid.sum() > 50:
                research_residuals.extend(fasting_res[valid].tolist())
                rmse = float(np.sqrt(np.mean(fasting_res[valid]**2)))
                if pid in results_by_patient:
                    results_by_patient[pid]['research'] = {
                        'rmse': rmse,
                        'mean_residual': float(np.mean(fasting_res[valid])),
                    }
        except Exception as e:
            print(f"  Patient {pid} research model failed: {e}")

    # Population summary
    pop = {}
    for label in ['uncalibrated', 'calibrated']:
        arr = np.array(all_fasting_drift[label])
        if len(arr) > 0:
            pop[label] = {
                'rmse': float(np.sqrt(np.mean(arr**2))),
                'mean_bias': float(np.mean(arr)),
                'n_total': len(arr),
            }
    if research_residuals:
        rarr = np.array(research_residuals)
        pop['research'] = {
            'rmse': float(np.sqrt(np.mean(rarr**2))),
            'mean_bias': float(np.mean(rarr)),
            'n_total': len(rarr),
        }

    for label, p in pop.items():
        print(f"\n  Population {label}: RMSE={p['rmse']:.3f}, bias={p['mean_bias']:.3f}")

    cal_wins = sum(1 for p in results_by_patient.values()
                   if p.get('calibrated', {}).get('rmse', 99) < p.get('uncalibrated', {}).get('rmse', 99))

    result = {
        'experiment_id': 'EXP-1772',
        'title': 'Demand Calibration in Hill Model',
        'population': pop,
        'per_patient': results_by_patient,
        'results': {
            'calibrated_wins': cal_wins,
            'total_patients': len(results_by_patient),
            'rmse_uncalibrated': pop.get('uncalibrated', {}).get('rmse', 0),
            'rmse_calibrated': pop.get('calibrated', {}).get('rmse', 0),
            'rmse_research': pop.get('research', {}).get('rmse', 0),
        },
    }

    if make_figures:
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        pids = sorted(results_by_patient.keys())

        # Panel A: RMSE three-way comparison
        rmse_uncal = [results_by_patient[p].get('uncalibrated', {}).get('rmse', 0) for p in pids]
        rmse_cal = [results_by_patient[p].get('calibrated', {}).get('rmse', 0) for p in pids]
        rmse_res = [results_by_patient[p].get('research', {}).get('rmse', 0) for p in pids]
        x = np.arange(len(pids))
        w = 0.25
        axes[0].bar(x - w, rmse_uncal, w, label='Hill uncal', color='#e74c3c', alpha=0.8)
        axes[0].bar(x, rmse_cal, w, label='Hill calibrated', color='#2ecc71', alpha=0.8)
        axes[0].bar(x + w, rmse_res, w, label='Research model', color='#3498db', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(pids)
        axes[0].set_ylabel('Fasting RMSE (mg/dL/step)')
        axes[0].set_title('A: Demand Calibration → Fasting RMSE')
        axes[0].legend(fontsize=8)

        # Panel B: Supply vs demand balance during fasting
        supply_uncal = [results_by_patient[p].get('uncalibrated', {}).get('supply_mean', 0) for p in pids]
        demand_uncal = [results_by_patient[p].get('uncalibrated', {}).get('demand_mean', 0) for p in pids]
        supply_cal = [results_by_patient[p].get('calibrated', {}).get('supply_mean', 0) for p in pids]
        demand_cal = [results_by_patient[p].get('calibrated', {}).get('demand_mean', 0) for p in pids]
        axes[1].scatter(supply_uncal, demand_uncal, c='#e74c3c', s=60, label='Uncalibrated', zorder=3)
        axes[1].scatter(supply_cal, demand_cal, c='#2ecc71', s=60, label='Calibrated', zorder=3)
        max_val = max(max(supply_uncal + supply_cal), max(demand_uncal + demand_cal)) * 1.1
        axes[1].plot([0, max_val], [0, max_val], 'k--', alpha=0.3, label='Supply=Demand')
        axes[1].set_xlabel('Mean Fasting Supply (mg/dL/step)')
        axes[1].set_ylabel('Mean Fasting Demand (mg/dL/step)')
        axes[1].set_title('B: Supply-Demand Balance (fasting)')
        axes[1].legend(fontsize=8)

        # Panel C: Predicted drift during fasting
        drift_uncal = [results_by_patient[p].get('uncalibrated', {}).get('predicted_drift', 0) for p in pids]
        drift_cal = [results_by_patient[p].get('calibrated', {}).get('predicted_drift', 0) for p in pids]
        axes[2].bar(x - 0.15, drift_uncal, 0.3, label='Uncalibrated', color='#e74c3c', alpha=0.8)
        axes[2].bar(x + 0.15, drift_cal, 0.3, label='Calibrated', color='#2ecc71', alpha=0.8)
        axes[2].axhline(0, color='black', linestyle='--', alpha=0.3)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(pids)
        axes[2].set_ylabel('Predicted Fasting Drift (mg/dL/step)')
        axes[2].set_title('C: Drift (0 = steady state)')
        axes[2].legend()

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'prod-fig2-demand-calibration.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: prod-fig2-demand-calibration.png")

    return result


# ═══════════════════════════════════════════════════════════════════════
# EXP-1773: UAM Threshold Consistency
# ═══════════════════════════════════════════════════════════════════════

def exp_1773_uam_threshold(patients, make_figures=False):
    """Compare UAM detection at threshold 1.0 vs 3.0 mg/dL/5min.

    Tests precision, recall, F1 against known meal events as ground truth.
    """
    print("\n" + "="*70)
    print("EXP-1773: UAM Threshold Consistency (1.0 vs 3.0)")
    print("="*70)

    thresholds = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    results_by_threshold = {t: {'tp': 0, 'fp': 0, 'fn': 0, 'total_uam_steps': 0,
                                'total_steps': 0} for t in thresholds}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        try:
            sd = compute_supply_demand(df, calibrate=True)
        except Exception as e:
            print(f"  Patient {pid}: S×D failed: {e}")
            continue

        N = len(glucose)
        actual_dbg = np.zeros(N)
        actual_dbg[1:] = np.diff(glucose)
        residual = actual_dbg - sd['net']

        # Ground truth: carb-free rises (UAM) vs carb-associated rises
        # A rise with carbs within ±30min is "announced meal"
        # A rise without carbs is "unannounced" (UAM)
        carb_proximity = np.zeros(N, dtype=bool)
        for i in range(N):
            window = carbs[max(0, i-6):min(N, i+7)]
            if np.nansum(window) > 1.0:
                carb_proximity[i] = True

        # Actual rises
        rising = actual_dbg > 0.5
        uam_ground_truth = rising & ~carb_proximity  # rising without nearby carbs
        meal_ground_truth = rising & carb_proximity   # rising with nearby carbs

        for thresh in thresholds:
            uam_detected = residual > thresh
            # True positive: detected UAM where there's actual carb-free rise
            tp = int(np.sum(uam_detected & uam_ground_truth))
            # False positive: detected UAM where there's a carb-associated rise or no rise
            fp = int(np.sum(uam_detected & ~uam_ground_truth))
            # False negative: missed UAM (carb-free rise not detected)
            fn = int(np.sum(~uam_detected & uam_ground_truth))

            results_by_threshold[thresh]['tp'] += tp
            results_by_threshold[thresh]['fp'] += fp
            results_by_threshold[thresh]['fn'] += fn
            results_by_threshold[thresh]['total_uam_steps'] += int(uam_detected.sum())
            results_by_threshold[thresh]['total_steps'] += N

    # Compute metrics
    threshold_metrics = {}
    for thresh in thresholds:
        r = results_by_threshold[thresh]
        precision = r['tp'] / max(r['tp'] + r['fp'], 1)
        recall = r['tp'] / max(r['tp'] + r['fn'], 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        uam_rate = r['total_uam_steps'] / max(r['total_steps'], 1)
        threshold_metrics[thresh] = {
            'precision': float(precision),
            'recall': float(recall),
            'f1': float(f1),
            'uam_rate': float(uam_rate),
        }
        print(f"  Threshold {thresh:.1f}: P={precision:.3f} R={recall:.3f} "
              f"F1={f1:.3f} UAM_rate={uam_rate:.3f}")

    # Find optimal threshold
    best_thresh = max(thresholds, key=lambda t: threshold_metrics[t]['f1'])
    print(f"\n  Best F1 threshold: {best_thresh} (F1={threshold_metrics[best_thresh]['f1']:.3f})")
    print(f"  Production (1.0): F1={threshold_metrics[1.0]['f1']:.3f}")
    print(f"  Research (3.0):   F1={threshold_metrics[3.0]['f1']:.3f}")

    result = {
        'experiment_id': 'EXP-1773',
        'title': 'UAM Threshold Consistency',
        'threshold_metrics': {str(k): v for k, v in threshold_metrics.items()},
        'results': {
            'best_threshold': best_thresh,
            'best_f1': threshold_metrics[best_thresh]['f1'],
            'f1_at_1_0': threshold_metrics[1.0]['f1'],
            'f1_at_3_0': threshold_metrics[3.0]['f1'],
            'precision_at_1_0': threshold_metrics[1.0]['precision'],
            'recall_at_1_0': threshold_metrics[1.0]['recall'],
            'precision_at_3_0': threshold_metrics[3.0]['precision'],
            'recall_at_3_0': threshold_metrics[3.0]['recall'],
        },
    }

    if make_figures:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Panel A: P-R-F1 curves
        t_vals = sorted(threshold_metrics.keys())
        p_vals = [threshold_metrics[t]['precision'] for t in t_vals]
        r_vals = [threshold_metrics[t]['recall'] for t in t_vals]
        f1_vals = [threshold_metrics[t]['f1'] for t in t_vals]

        axes[0].plot(t_vals, p_vals, 'o-', label='Precision', color='#e74c3c')
        axes[0].plot(t_vals, r_vals, 's-', label='Recall', color='#2ecc71')
        axes[0].plot(t_vals, f1_vals, 'D-', label='F1', color='#3498db', linewidth=2)
        axes[0].axvline(1.0, color='orange', linestyle='--', alpha=0.5, label='Production (1.0)')
        axes[0].axvline(3.0, color='purple', linestyle='--', alpha=0.5, label='Research (3.0)')
        axes[0].axvline(best_thresh, color='gold', linestyle='-', alpha=0.7, label=f'Best ({best_thresh})')
        axes[0].set_xlabel('UAM Threshold (mg/dL/5min)')
        axes[0].set_ylabel('Score')
        axes[0].set_title('A: UAM Detection P/R/F1 vs Threshold')
        axes[0].legend(fontsize=8)

        # Panel B: UAM rate vs threshold
        uam_rates = [threshold_metrics[t]['uam_rate'] for t in t_vals]
        axes[1].plot(t_vals, uam_rates, 'o-', color='#9b59b6')
        axes[1].axvline(1.0, color='orange', linestyle='--', alpha=0.5)
        axes[1].axvline(3.0, color='purple', linestyle='--', alpha=0.5)
        axes[1].set_xlabel('UAM Threshold (mg/dL/5min)')
        axes[1].set_ylabel('Fraction of Steps Flagged as UAM')
        axes[1].set_title('B: UAM Detection Rate')

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'prod-fig3-uam-threshold.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: prod-fig3-uam-threshold.png")

    return result


# ═══════════════════════════════════════════════════════════════════════
# EXP-1774: 4-Harmonic Temporal Encoding
# ═══════════════════════════════════════════════════════════════════════

def exp_1774_harmonic_encoding(patients, make_figures=False):
    """Compare 1-harmonic (sin/cos 24h) vs 4-harmonic (24+12+8+6h) temporal
    encoding for predicting glucose dynamics.

    Tests: How much circadian variance is captured by each encoding?
    Does 4-harmonic improve residual prediction?
    """
    print("\n" + "="*70)
    print("EXP-1774: 4-Harmonic vs 1-Harmonic Temporal Encoding")
    print("="*70)

    periods = [24.0, 12.0, 8.0, 6.0]
    results_by_patient = {}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        N = len(glucose)

        timestamps = df['date'].values if 'date' in df.columns else np.arange(N) * 300000
        ts_float = timestamps.astype(np.int64) if hasattr(timestamps, 'astype') else np.array(timestamps, dtype=np.int64)
        hours = (ts_float / 1000 % 86400) / 3600.0

        valid = np.isfinite(glucose)
        if valid.sum() < 1000:
            continue

        g = glucose[valid]
        h = hours[valid]

        # 1-harmonic: sin(2πh/24) + cos(2πh/24) + offset
        angle_24 = 2.0 * np.pi * h / 24.0
        A1 = np.column_stack([np.sin(angle_24), np.cos(angle_24), np.ones(len(h))])
        try:
            c1, _, _, _ = np.linalg.lstsq(A1, g, rcond=None)
            pred1 = A1 @ c1
            ss_res1 = np.sum((g - pred1)**2)
            ss_tot = np.sum((g - np.mean(g))**2)
            r2_1h = float(1.0 - ss_res1 / max(ss_tot, 1e-12))
        except:
            r2_1h = 0.0

        # 4-harmonic: sin/cos for each period
        columns = []
        for p in periods:
            angle = 2.0 * np.pi * h / p
            columns.append(np.sin(angle))
            columns.append(np.cos(angle))
        columns.append(np.ones(len(h)))
        A4 = np.column_stack(columns)
        try:
            c4, _, _, _ = np.linalg.lstsq(A4, g, rcond=None)
            pred4 = A4 @ c4
            ss_res4 = np.sum((g - pred4)**2)
            r2_4h = float(1.0 - ss_res4 / max(ss_tot, 1e-12))
        except:
            r2_4h = 0.0

        # Incremental R² from each harmonic
        r2_incremental = {}
        for k, p in enumerate(periods):
            # Fit with first k harmonics only
            cols_k = []
            for j in range(k + 1):
                angle = 2.0 * np.pi * h / periods[j]
                cols_k.append(np.sin(angle))
                cols_k.append(np.cos(angle))
            cols_k.append(np.ones(len(h)))
            Ak = np.column_stack(cols_k)
            try:
                ck, _, _, _ = np.linalg.lstsq(Ak, g, rcond=None)
                predk = Ak @ ck
                ss_resk = np.sum((g - predk)**2)
                r2_k = float(1.0 - ss_resk / max(ss_tot, 1e-12))
            except:
                r2_k = 0.0
            r2_incremental[f'{int(p)}h'] = r2_k

        # Amplitude of each harmonic
        amplitudes = {}
        for k, p in enumerate(periods):
            a_k = c4[2 * k]
            b_k = c4[2 * k + 1]
            amp = float(np.sqrt(a_k**2 + b_k**2))
            amplitudes[f'{int(p)}h'] = amp

        results_by_patient[pid] = {
            'r2_1harmonic': r2_1h,
            'r2_4harmonic': r2_4h,
            'r2_improvement': r2_4h - r2_1h,
            'r2_incremental': r2_incremental,
            'amplitudes': amplitudes,
        }
        print(f"  Patient {pid}: 1H R²={r2_1h:.4f}, 4H R²={r2_4h:.4f}, "
              f"Δ={r2_4h - r2_1h:.4f}")

    # Population summary
    r2_1h_all = [r['r2_1harmonic'] for r in results_by_patient.values()]
    r2_4h_all = [r['r2_4harmonic'] for r in results_by_patient.values()]
    delta_all = [r['r2_improvement'] for r in results_by_patient.values()]

    print(f"\n  Population: 1H R²={np.mean(r2_1h_all):.4f} ± {np.std(r2_1h_all):.4f}")
    print(f"  Population: 4H R²={np.mean(r2_4h_all):.4f} ± {np.std(r2_4h_all):.4f}")
    print(f"  Improvement: {np.mean(delta_all):.4f} ± {np.std(delta_all):.4f}")
    print(f"  All patients improve: {all(d > 0 for d in delta_all)}")

    result = {
        'experiment_id': 'EXP-1774',
        'title': '4-Harmonic vs 1-Harmonic Temporal Encoding',
        'per_patient': results_by_patient,
        'results': {
            'mean_r2_1h': float(np.mean(r2_1h_all)),
            'mean_r2_4h': float(np.mean(r2_4h_all)),
            'mean_improvement': float(np.mean(delta_all)),
            'all_improve': all(d > 0 for d in delta_all),
            'n_patients': len(results_by_patient),
            'max_improvement_patient': max(results_by_patient.keys(),
                                           key=lambda p: results_by_patient[p]['r2_improvement']),
        },
    }

    if make_figures:
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        pids = sorted(results_by_patient.keys())

        # Panel A: R² comparison
        x = np.arange(len(pids))
        r2_1 = [results_by_patient[p]['r2_1harmonic'] for p in pids]
        r2_4 = [results_by_patient[p]['r2_4harmonic'] for p in pids]
        axes[0].bar(x - 0.15, r2_1, 0.3, label='1 harmonic (24h)', color='#e74c3c', alpha=0.8)
        axes[0].bar(x + 0.15, r2_4, 0.3, label='4 harmonics (24+12+8+6h)', color='#2ecc71', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(pids)
        axes[0].set_ylabel('Circadian R²')
        axes[0].set_title('A: Circadian Variance Captured')
        axes[0].legend(fontsize=8)

        # Panel B: Incremental R² by harmonic (population mean)
        periods_label = ['24h', '24+12h', '24+12+8h', '24+12+8+6h']
        incr_means = []
        for k, p in enumerate(periods):
            key = f'{int(p)}h'
            vals = [results_by_patient[pid]['r2_incremental'][key] for pid in pids]
            incr_means.append(np.mean(vals))
        axes[1].bar(range(len(periods_label)), incr_means, color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c'], alpha=0.8)
        axes[1].set_xticks(range(len(periods_label)))
        axes[1].set_xticklabels(periods_label)
        axes[1].set_ylabel('Cumulative R²')
        axes[1].set_title('B: Incremental R² by Harmonic')

        # Panel C: Amplitude spectrum (population mean)
        amp_labels = [f'{int(p)}h' for p in periods]
        amp_means = []
        for p in periods:
            key = f'{int(p)}h'
            vals = [results_by_patient[pid]['amplitudes'][key] for pid in pids]
            amp_means.append(np.mean(vals))
        axes[2].bar(range(len(amp_labels)), amp_means,
                    color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c'], alpha=0.8)
        axes[2].set_xticks(range(len(amp_labels)))
        axes[2].set_xticklabels(amp_labels)
        axes[2].set_ylabel('Amplitude (mg/dL)')
        axes[2].set_title('C: Harmonic Amplitudes')

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'prod-fig4-harmonic-encoding.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: prod-fig4-harmonic-encoding.png")

    return result


# ═══════════════════════════════════════════════════════════════════════
# EXP-1775: Rescue Carb Detection with Hill Model
# ═══════════════════════════════════════════════════════════════════════

def exp_1775_rescue_detection_hill(patients, make_figures=False):
    """Validate rescue carb binary detection using production Hill-model S×D.

    EXP-1648 showed F1=0.91 using research S×D. Does Hill model maintain this?
    """
    print("\n" + "="*70)
    print("EXP-1775: Rescue Carb Detection with Hill Model S×D")
    print("="*70)

    # Detection logic from EXP-1648: residual flip after nadir
    COUNTER_REG_FLOOR = 1.68  # mg/dL/step from EXP-1644

    results_by_model = {'research': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0},
                        'hill_uncal': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0},
                        'hill_cal': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}}

    episode_counts = {'total': 0, 'with_rescue': 0}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = np.nan_to_num(df['glucose'].values.astype(float), nan=np.nan)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0.0)
        N = len(glucose)

        # Get all three S×D models
        try:
            sd_research = compute_supply_demand(df, calibrate=True)
        except:
            sd_research = None

        sd_hill_uncal = _production_supply_demand(pat, base_egp=1.5, calibrate=False)
        sd_hill_cal = _production_supply_demand(pat, base_egp=1.5, calibrate=True)

        # Find hypo episodes
        i = 0
        while i < N - 36:
            if np.isnan(glucose[i]) or glucose[i] >= LOW:
                i += 1
                continue

            # Find nadir
            nadir_idx = i
            nadir_bg = glucose[i]
            j = i + 1
            while j < min(i + 36, N):
                if not np.isnan(glucose[j]) and glucose[j] < nadir_bg:
                    nadir_bg = glucose[j]
                    nadir_idx = j
                if not np.isnan(glucose[j]) and glucose[j] > LOW + 30:
                    break
                j += 1

            post_end = min(N, nadir_idx + 24)  # 2h post-nadir
            if post_end - nadir_idx < 6:
                i = j + 12
                continue

            # Ground truth: were rescue carbs consumed in post-nadir window?
            post_carbs = carbs[nadir_idx:post_end]
            has_rescue = float(np.nansum(post_carbs)) > 1.0

            # Detection: residual exceeds counter-regulatory floor in first 20min
            detect_window = min(4, post_end - nadir_idx)  # 4 steps = 20min

            episode_counts['total'] += 1
            if has_rescue:
                episode_counts['with_rescue'] += 1

            for model_name, sd in [('research', sd_research),
                                    ('hill_uncal', sd_hill_uncal),
                                    ('hill_cal', sd_hill_cal)]:
                if sd is None:
                    continue

                # Compute residual in post-nadir window
                actual_dbg = np.zeros(N)
                actual_dbg[1:] = np.diff(glucose)
                residual = actual_dbg - sd['net']

                post_res = residual[nadir_idx:nadir_idx + detect_window]
                valid = np.isfinite(post_res)
                if valid.sum() == 0:
                    continue

                # Detect: max residual > counter-regulatory floor
                max_res = float(np.nanmax(post_res))
                detected = max_res > COUNTER_REG_FLOOR

                if detected and has_rescue:
                    results_by_model[model_name]['tp'] += 1
                elif detected and not has_rescue:
                    results_by_model[model_name]['fp'] += 1
                elif not detected and has_rescue:
                    results_by_model[model_name]['fn'] += 1
                else:
                    results_by_model[model_name]['tn'] += 1

            i = j + 12

    # Compute metrics
    model_metrics = {}
    for model_name, counts in results_by_model.items():
        tp, fp, fn, tn = counts['tp'], counts['fp'], counts['fn'], counts['tn']
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        model_metrics[model_name] = {
            'precision': float(precision),
            'recall': float(recall),
            'f1': float(f1),
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        }
        print(f"  {model_name}: P={precision:.3f} R={recall:.3f} F1={f1:.3f} "
              f"(TP={tp} FP={fp} FN={fn} TN={tn})")

    print(f"\n  Total hypo episodes: {episode_counts['total']}")
    print(f"  With rescue carbs: {episode_counts['with_rescue']} "
          f"({100*episode_counts['with_rescue']/max(episode_counts['total'],1):.0f}%)")

    result = {
        'experiment_id': 'EXP-1775',
        'title': 'Rescue Carb Detection with Hill Model',
        'model_metrics': model_metrics,
        'episode_counts': episode_counts,
        'results': {
            'f1_research': model_metrics.get('research', {}).get('f1', 0),
            'f1_hill_uncal': model_metrics.get('hill_uncal', {}).get('f1', 0),
            'f1_hill_cal': model_metrics.get('hill_cal', {}).get('f1', 0),
            'total_episodes': episode_counts['total'],
            'rescue_rate': episode_counts['with_rescue'] / max(episode_counts['total'], 1),
        },
    }

    if make_figures:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Panel A: F1 comparison
        models = ['research', 'hill_uncal', 'hill_cal']
        labels = ['Research\n(calibrated)', 'Hill\n(uncalibrated)', 'Hill\n(calibrated)']
        colors = ['#3498db', '#e74c3c', '#2ecc71']
        f1s = [model_metrics[m]['f1'] for m in models]
        precs = [model_metrics[m]['precision'] for m in models]
        recs = [model_metrics[m]['recall'] for m in models]

        x = np.arange(len(models))
        w = 0.25
        axes[0].bar(x - w, precs, w, label='Precision', color='#e74c3c', alpha=0.8)
        axes[0].bar(x, recs, w, label='Recall', color='#2ecc71', alpha=0.8)
        axes[0].bar(x + w, f1s, w, label='F1', color='#3498db', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(labels)
        axes[0].set_ylabel('Score')
        axes[0].set_title('A: Rescue Detection by S×D Model')
        axes[0].legend()
        axes[0].set_ylim(0, 1)

        # Panel B: Confusion breakdown
        for idx, (m, label, color) in enumerate(zip(models, labels, colors)):
            tp = model_metrics[m]['tp']
            fp = model_metrics[m]['fp']
            fn = model_metrics[m]['fn']
            tn = model_metrics[m]['tn']
            total = tp + fp + fn + tn
            if total > 0:
                axes[1].barh(idx * 4, tp, color='#2ecc71', height=0.8, label='TP' if idx == 0 else '')
                axes[1].barh(idx * 4 + 1, fp, color='#e74c3c', height=0.8, label='FP' if idx == 0 else '')
                axes[1].barh(idx * 4 + 2, fn, color='#f39c12', height=0.8, label='FN' if idx == 0 else '')
                axes[1].barh(idx * 4 + 3, tn, color='#95a5a6', height=0.8, label='TN' if idx == 0 else '')

        axes[1].set_yticks([0.5, 4.5, 8.5])
        axes[1].set_yticklabels(labels)
        axes[1].set_xlabel('Count')
        axes[1].set_title('B: Confusion Matrix Breakdown')
        axes[1].legend(loc='lower right', fontsize=8)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'prod-fig5-rescue-detection-hill.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: prod-fig5-rescue-detection-hill.png")

    return result


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--exp', type=int, default=0, help='Run specific experiment (0=all)')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(str(PATIENTS_DIR))
    print(f"Loaded {len(patients)} patients")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    experiments = {
        1771: ('exp_1771_hepatic_base_rate', exp_1771_hepatic_base_rate),
        1772: ('exp_1772_demand_calibration', exp_1772_demand_calibration),
        1773: ('exp_1773_uam_threshold', exp_1773_uam_threshold),
        1774: ('exp_1774_harmonic_encoding', exp_1774_harmonic_encoding),
        1775: ('exp_1775_rescue_detection_hill', exp_1775_rescue_detection_hill),
    }

    to_run = experiments if args.exp == 0 else {args.exp: experiments[args.exp]}

    for eid, (name, func) in sorted(to_run.items()):
        try:
            result = func(patients, make_figures=args.figures)
            out_file = RESULTS_DIR / f'exp-{eid}_production_validation.json'
            with open(out_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved: {out_file.name}")
        except Exception as e:
            import traceback
            print(f"  EXP-{eid} FAILED: {e}")
            traceback.print_exc()

    print("\n" + "="*70)
    print("All experiments complete.")
    print("="*70)


if __name__ == '__main__':
    main()
