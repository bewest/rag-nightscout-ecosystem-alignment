#!/usr/bin/env python3
"""EXP-1621 through EXP-1626: Demand Diagnosis and Rescue Carb Inference.

Follows up on EXP-1611–1616 which revealed the demand model over-predicts
insulin effectiveness by ~5× (β=0.191). This batch:

1. Diagnoses the demand computation chain to find where the 5× comes from
2. Tests steady-state balance at known physiological states
3. Infers rescue carb quantities from hypo recovery residuals
4. Validates β-corrected model across all natural experiment contexts
5. Computes an information content analysis per experiment type

Supply-demand computation chain:
  insulin_total = pk[0] × 0.05          (U/min)
  isf_curve     = pk[7] × 200.0         (mg/dL per U)
  demand        = |insulin_total × 5.0 × isf_curve|  (mg/dL per 5-min step)

Key finding from EXP-1611–1616:
  β = 0.191 → model demand is ~5.2× the observed glucose-lowering effect
  α = 1.332 → hepatic production slightly under-predicted

Diagnostic from initial audit:
  Patient a (ISF=48.6, basal=0.4): demand=4.36 vs supply=1.30 during fasting
  Patient b (ISF=89.7, basal=1.2): demand=2.04 vs supply=1.69 during fasting
  → Both predict falling glucose during fasting, but actual dBG ≈ 0

Hypotheses for the 5× over-prediction:
  H1: insulin_total includes IOB from prior boluses, not just basal
  H2: ISF represents TOTAL effect over DIA, but demand treats it as instantaneous
  H3: AID loop withdraws basal during corrections, reducing net insulin
  H4: Counter-regulatory response reduces insulin effectiveness at low glucose

References:
  - exp_natural_deconfound_1611.py: EXP-1611–1616 deconfounding results
  - exp_hypo_supply_demand_1601.py: EXP-1601–1606 hypo decomposition
  - continuous_pk.py: PK channel computation
"""

import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = 60  # 5 hours = 60 steps

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Utility: find clean fasting windows with IOB ≈ 0 ──────────────────

def find_clean_fasting(glucose, bolus, carbs, iob, hours, min_steps=36):
    """Find fasting windows where IOB is also near zero (truly quiescent)."""
    N = len(glucose)
    mask = np.ones(N, dtype=bool)
    for i in range(N):
        if np.isnan(glucose[i]):
            mask[i] = False
        elif carbs[i] > 1.0 or bolus[i] > 0.1:
            mask[max(0, i - min_steps):min(N, i + min_steps)] = False
        elif abs(iob[i]) > 0.5:  # IOB near zero
            mask[i] = False

    windows = []
    in_run = False
    start = 0
    for i in range(N):
        if mask[i] and not in_run:
            in_run = True
            start = i
        elif not mask[i] and in_run:
            in_run = False
            if i - start >= min_steps:
                windows.append((start, i))
    if in_run and N - start >= min_steps:
        windows.append((start, N))
    return windows


def find_hypo_recovery_episodes(glucose, carbs, min_depth=60, threshold=70):
    """Find hypo episodes and their recovery phases.
    Returns list of dicts with nadir info and recovery window."""
    N = len(glucose)
    episodes = []
    i = 0
    while i < N - 24:  # need 2h post-nadir
        if np.isnan(glucose[i]) or glucose[i] >= threshold:
            i += 1
            continue
        # Find nadir
        nadir_idx = i
        nadir_bg = glucose[i]
        j = i + 1
        while j < N and not np.isnan(glucose[j]) and glucose[j] < threshold + 20:
            if glucose[j] < nadir_bg:
                nadir_bg = glucose[j]
                nadir_idx = j
            j += 1

        # Recovery window: nadir to +2h
        rec_end = min(nadir_idx + 24, N)
        if rec_end - nadir_idx < 6:
            i = j
            continue

        # Check for entered carbs in recovery window
        recovery_carbs = np.nansum(carbs[nadir_idx:rec_end])
        has_announced_carbs = recovery_carbs > 1.0

        # Recovery magnitude
        rec_bg = glucose[nadir_idx:rec_end]
        valid = ~np.isnan(rec_bg)
        if valid.sum() < 6:
            i = j
            continue

        peak_recovery = float(np.nanmax(rec_bg))
        rebound = peak_recovery - nadir_bg

        episodes.append({
            'nadir_idx': nadir_idx,
            'nadir_bg': float(nadir_bg),
            'recovery_end': rec_end,
            'rebound_mg': float(rebound),
            'announced_carbs': float(recovery_carbs),
            'has_announced': has_announced_carbs,
            'peak_recovery_bg': peak_recovery,
        })
        i = rec_end  # skip past this episode
    return episodes


# ── EXP-1621: Demand Chain Diagnosis ──────────────────────────────────

def exp_1621_demand_diagnosis(patients):
    """Trace the demand computation chain and identify the 5× source.

    For each patient, extract PK components at clean fasting (IOB≈0)
    where we know the system should be at steady state:
      dBG/dt ≈ 0 → supply ≈ demand → hepatic ≈ basal_demand
    """
    print("\n=== EXP-1621: Demand Chain Diagnosis ===")

    per_patient = {}
    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64)
                              if 'bolus' in df.columns else np.zeros(len(df)), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64)
                              if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        if hasattr(df.index, 'hour'):
            hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = np.zeros(len(df))

        sd = compute_supply_demand(df, pk)

        # Clean fasting (IOB ≈ 0)
        windows = find_clean_fasting(glucose, bolus, carbs, iob, hours)
        if not windows:
            print(f"  {name}: no clean fasting windows")
            continue

        all_idx = np.concatenate([np.arange(s, e) for s, e in windows])

        # PK channels
        norms = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
        ch_names = ['insulin_total', 'insulin_net', 'basal_ratio', 'carb_rate',
                    'carb_accel', 'hepatic_production', 'net_balance', 'isf_curve']

        pk_fasting = pk[all_idx]
        denorm = {ch: pk_fasting[:, i] * norms[i] for i, ch in enumerate(ch_names)}

        # Demand chain components
        insulin_rate = denorm['insulin_total']  # U/min
        isf = denorm['isf_curve']               # mg/dL/U
        demand_computed = np.abs(insulin_rate * 5.0 * isf)
        supply_computed = sd['supply'][all_idx]
        hepatic_computed = sd['hepatic'][all_idx]
        net_pk = denorm['net_balance']           # PK's own net balance

        # Actual dBG
        actual_dbg_full = np.full(len(glucose), np.nan)
        for i in range(1, len(glucose)):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i-1]):
                actual_dbg_full[i] = glucose[i] - glucose[i-1]
        actual_dbg = actual_dbg_full[all_idx]

        valid = ~np.isnan(actual_dbg)
        n_valid = valid.sum()
        if n_valid < 20:
            continue

        # Basal schedule
        basal_sched = df.attrs.get('basal_schedule', [])
        if basal_sched:
            basal_rates = [e.get('value', 0.8) for e in basal_sched]
            mean_basal = float(np.mean(basal_rates))
        else:
            mean_basal = 0.8

        isf_sched = df.attrs.get('isf_schedule', [])
        if isf_sched:
            isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in isf_sched]
            mean_isf = float(np.mean(isf_vals))
            # Check if ISF is in mmol/L (< 10) vs mg/dL (> 10)
            if mean_isf < 10:
                mean_isf_mgdl = mean_isf * 18.0
            else:
                mean_isf_mgdl = mean_isf
        else:
            mean_isf_mgdl = 50.0

        # Expected steady-state demand from first principles
        # At basal_rate (U/h), steady-state insulin_activity = basal_rate / 60 (U/min)
        # But this assumes exponential decay where integral = total_dose
        # Demand_expected = basal_rate_per_min * 5min * ISF
        expected_basal_demand = (mean_basal / 60.0) * 5.0 * mean_isf_mgdl
        observed_demand = float(np.mean(demand_computed[valid]))
        demand_ratio = observed_demand / max(expected_basal_demand, 0.01)

        # Steady-state check: at IOB≈0, demand should ≈ supply
        mean_supply = float(np.mean(supply_computed[valid]))
        mean_demand = float(np.mean(demand_computed[valid]))
        mean_actual = float(np.nanmean(actual_dbg[valid]))
        balance_error = mean_supply - mean_demand  # should be ≈ 0 at steady state

        # Effective β for this patient at steady state
        # actual_dBG ≈ supply - demand*β → β = (supply - actual_dBG) / demand
        eff_beta = (mean_supply - mean_actual) / max(mean_demand, 0.01)

        result = {
            'n_clean_fasting_steps': n_valid,
            'mean_iob': float(np.nanmean(iob[all_idx])),
            'basal_rate_u_h': mean_basal,
            'isf_mgdl': mean_isf_mgdl,
            'expected_basal_demand': float(expected_basal_demand),
            'observed_demand': float(observed_demand),
            'demand_ratio': float(demand_ratio),
            'mean_supply': float(mean_supply),
            'mean_hepatic': float(np.mean(hepatic_computed[valid])),
            'balance_error': float(balance_error),
            'actual_dbg': float(mean_actual),
            'effective_beta': float(eff_beta),
            'pk_net_balance': float(np.mean(net_pk[valid])),
            'insulin_rate_u_min': float(np.mean(insulin_rate[valid])),
            'isf_pk': float(np.mean(isf[valid])),
        }
        per_patient[name] = result

        print(f"  {name}: basal={mean_basal:.2f}U/h  ISF={mean_isf_mgdl:.0f}mg/dL/U  "
              f"demand={mean_demand:.2f} vs expected={expected_basal_demand:.2f}  "
              f"ratio={demand_ratio:.2f}×  eff_β={eff_beta:.3f}  "
              f"n={n_valid}")

    # Population summary
    if per_patient:
        ratios = [v['demand_ratio'] for v in per_patient.values() if v['demand_ratio'] < 100]
        betas = [v['effective_beta'] for v in per_patient.values() if 0 < v['effective_beta'] < 5]
        print(f"\n  Demand/Expected ratio: {np.mean(ratios):.2f}× ± {np.std(ratios):.2f}")
        print(f"  Effective β at steady state: {np.mean(betas):.3f} ± {np.std(betas):.3f}")

    return {
        'experiment': 'EXP-1621',
        'title': 'Demand Chain Diagnosis at Clean Fasting',
        'per_patient': per_patient,
    }


# ── EXP-1622: Steady-State Balance Analysis ──────────────────────────

def exp_1622_steady_state_balance(patients):
    """Test whether hepatic ≈ demand at true steady state (IOB→0, dBG→0).

    At physiological steady state:
      EGP (hepatic) ≈ insulin-mediated glucose disposal + non-insulin disposal
      
    The model ignores non-insulin glucose disposal (brain: ~120g/day ≈ 0.42 mg/dL/step).
    This missing demand term would shift the balance.
    """
    print("\n=== EXP-1622: Steady-State Balance Analysis ===")

    # Brain glucose uptake: ~120g/day for 70kg person
    # Distribution volume: ~17 L
    # 120g / 1440 min * 5 min = 0.417g per 5-min
    # In concentration: 417mg / 170dL = 2.45 mg/dL per step... that seems high
    # Actually: glucose distribution volume for a 70kg person is about 200 dL (20L)
    # 417 mg / 200 dL = 2.09 mg/dL/step — still very significant
    # Let's use a more conservative estimate: brain uses ~5 mg/kg/min → ~25 mg/min → 125 mg/5min
    # 125 mg / 200 dL = 0.625 mg/dL/step
    BRAIN_GLUCOSE_UPTAKE = 0.625  # mg/dL per 5-min step (conservative)

    per_patient = {}
    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64)
                              if 'bolus' in df.columns else np.zeros(len(df)), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64)
                              if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        if hasattr(df.index, 'hour'):
            hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = np.zeros(len(df))

        sd = compute_supply_demand(df, pk)

        # Clean fasting (IOB ≈ 0)
        windows = find_clean_fasting(glucose, bolus, carbs, iob, hours)
        if not windows:
            continue

        all_idx = np.concatenate([np.arange(s, e) for s, e in windows])
        supply = sd['supply'][all_idx]
        demand = sd['demand'][all_idx]
        hepatic = sd['hepatic'][all_idx]

        actual_dbg_full = np.full(len(glucose), np.nan)
        for i in range(1, len(glucose)):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i-1]):
                actual_dbg_full[i] = glucose[i] - glucose[i-1]
        actual = actual_dbg_full[all_idx]
        valid = ~np.isnan(actual)
        if valid.sum() < 20:
            continue

        # Model 0: original (no correction)
        pred_0 = (supply - demand)[valid]
        r2_0 = 1 - np.sum((actual[valid] - pred_0)**2) / max(np.sum((actual[valid] - np.mean(actual[valid]))**2), 1e-8)

        # Model 1: add brain glucose uptake to demand
        pred_1 = (supply - demand - BRAIN_GLUCOSE_UPTAKE)[valid]
        r2_1 = 1 - np.sum((actual[valid] - pred_1)**2) / max(np.sum((actual[valid] - np.mean(actual[valid]))**2), 1e-8)

        # Model 2: β-corrected demand (use effective β from EXP-1621)
        mean_supply = float(np.mean(supply[valid]))
        mean_demand = float(np.mean(demand[valid]))
        mean_actual = float(np.mean(actual[valid]))
        eff_beta = (mean_supply - mean_actual) / max(mean_demand, 0.01)
        pred_2 = (supply - demand * eff_beta)[valid]
        r2_2 = 1 - np.sum((actual[valid] - pred_2)**2) / max(np.sum((actual[valid] - np.mean(actual[valid]))**2), 1e-8)

        # Model 3: β + brain
        pred_3 = (supply - demand * eff_beta - BRAIN_GLUCOSE_UPTAKE)[valid]
        r2_3 = 1 - np.sum((actual[valid] - pred_3)**2) / max(np.sum((actual[valid] - np.mean(actual[valid]))**2), 1e-8)

        result = {
            'n_steps': int(valid.sum()),
            'mean_supply': float(mean_supply),
            'mean_demand': float(mean_demand),
            'mean_actual_dbg': float(mean_actual),
            'effective_beta': float(eff_beta),
            'brain_uptake_added': float(BRAIN_GLUCOSE_UPTAKE),
            'r2_model0_original': float(r2_0),
            'r2_model1_plus_brain': float(r2_1),
            'r2_model2_beta_corrected': float(r2_2),
            'r2_model3_beta_plus_brain': float(r2_3),
            'mae_model0': float(np.mean(np.abs(actual[valid] - pred_0))),
            'mae_model2': float(np.mean(np.abs(actual[valid] - pred_2))),
        }
        per_patient[name] = result
        print(f"  {name}: R² original={r2_0:.4f}  +brain={r2_1:.4f}  "
              f"β-corrected={r2_2:.4f}  β+brain={r2_3:.4f}  "
              f"eff_β={eff_beta:.3f}")

    return {
        'experiment': 'EXP-1622',
        'title': 'Steady-State Balance Analysis',
        'brain_glucose_uptake_mgdl_step': BRAIN_GLUCOSE_UPTAKE,
        'per_patient': per_patient,
    }


# ── EXP-1623: Rescue Carb Inference ──────────────────────────────────

def exp_1623_rescue_carb_inference(patients):
    """Estimate rescue carb quantities from hypo recovery residuals.

    During hypo recovery with zero entered carbs:
      actual_dBG = supply - demand + RESCUE_EFFECT + counter_reg + noise
      RESCUE_EFFECT ≈ actual_dBG - (supply - demand)
    
    Convert to grams:
      rescue_carbs_g = RESCUE_EFFECT / (ISF / CR) per step
    
    ISF/CR converts mg/dL_per_step to g_carbs_per_step.
    """
    print("\n=== EXP-1623: Rescue Carb Inference from Hypo Recovery ===")

    all_unannounced = []
    all_announced = []
    per_patient = {}

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df, pk)

        # Get ISF and CR for carb estimation
        isf_sched = df.attrs.get('isf_schedule', [])
        cr_sched = df.attrs.get('cr_schedule', [])
        if isf_sched:
            isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in isf_sched]
            mean_isf = float(np.mean(isf_vals))
            if mean_isf < 10:
                mean_isf *= 18.0
        else:
            mean_isf = 50.0
        if cr_sched:
            cr_vals = [e.get('value', e.get('carbratio', 10)) for e in cr_sched]
            mean_cr = float(np.mean(cr_vals))
        else:
            mean_cr = 10.0

        # mg/dL per gram of carbs = ISF / CR
        mgdl_per_gram = mean_isf / max(mean_cr, 1.0)

        # Find hypo episodes
        episodes = find_hypo_recovery_episodes(glucose, carbs_arr)
        if not episodes:
            continue

        p_unannounced = []
        p_announced = []
        for ep in episodes:
            nadir = ep['nadir_idx']
            rec_end = ep['recovery_end']
            bg = glucose[nadir:rec_end]
            sup = sd['supply'][nadir:rec_end]
            dem = sd['demand'][nadir:rec_end]

            # Actual dBG in recovery
            valid_dbg = []
            for i in range(1, len(bg)):
                if not np.isnan(bg[i]) and not np.isnan(bg[i-1]):
                    valid_dbg.append(bg[i] - bg[i-1])
            if len(valid_dbg) < 3:
                continue

            actual_dbg = np.array(valid_dbg)
            net_model = (sup[1:len(valid_dbg)+1] - dem[1:len(valid_dbg)+1])

            # Residual = unmodeled glucose-raising force
            residual = actual_dbg - net_model
            total_residual = float(np.sum(np.maximum(residual, 0)))

            # Convert to grams of carbs
            estimated_carbs_g = total_residual / max(mgdl_per_gram, 0.1)

            entry = {
                'nadir_bg': ep['nadir_bg'],
                'rebound_mg': ep['rebound_mg'],
                'estimated_rescue_g': float(estimated_carbs_g),
                'announced_carbs_g': ep['announced_carbs'],
                'total_positive_residual': float(total_residual),
                'recovery_steps': len(valid_dbg),
                'iob_at_nadir': float(iob[nadir]) if nadir < len(iob) else 0,
            }

            if ep['has_announced']:
                p_announced.append(entry)
                all_announced.append(entry)
            else:
                p_unannounced.append(entry)
                all_unannounced.append(entry)

        if p_unannounced or p_announced:
            unanc_carbs = [e['estimated_rescue_g'] for e in p_unannounced]
            anc_carbs = [e['estimated_rescue_g'] for e in p_announced]
            per_patient[name] = {
                'n_unannounced': len(p_unannounced),
                'n_announced': len(p_announced),
                'isf_mgdl': mean_isf,
                'cr_g_per_u': mean_cr,
                'mgdl_per_gram': mgdl_per_gram,
                'unannounced_rescue_g_mean': float(np.mean(unanc_carbs)) if unanc_carbs else None,
                'unannounced_rescue_g_median': float(np.median(unanc_carbs)) if unanc_carbs else None,
                'unannounced_rescue_g_p75': float(np.percentile(unanc_carbs, 75)) if unanc_carbs else None,
                'announced_rescue_g_mean': float(np.mean(anc_carbs)) if anc_carbs else None,
            }
            n_u = len(unanc_carbs)
            med_u = np.median(unanc_carbs) if unanc_carbs else 0
            print(f"  {name}: {n_u} unannounced (median {med_u:.0f}g), "
                  f"{len(anc_carbs)} announced  ISF/CR={mgdl_per_gram:.1f}")

    # Population summary
    if all_unannounced:
        u_carbs = [e['estimated_rescue_g'] for e in all_unannounced]
        a_carbs = [e['estimated_rescue_g'] for e in all_announced]
        print(f"\n  Unannounced rescue carbs (n={len(u_carbs)}):")
        print(f"    Median: {np.median(u_carbs):.0f}g  Mean: {np.mean(u_carbs):.0f}g  "
              f"P75: {np.percentile(u_carbs, 75):.0f}g  P95: {np.percentile(u_carbs, 95):.0f}g")
        if a_carbs:
            print(f"  Announced rescue carbs (n={len(a_carbs)}):")
            print(f"    Median: {np.median(a_carbs):.0f}g  Mean: {np.mean(a_carbs):.0f}g")

        # Compare to clinical expectations
        pct_over_15 = np.mean(np.array(u_carbs) > 15) * 100
        pct_over_30 = np.mean(np.array(u_carbs) > 30) * 100
        pct_meal_sized = np.mean(np.array(u_carbs) > 40) * 100
        print(f"\n  Clinical comparison:")
        print(f"    > 15g (standard rescue): {pct_over_15:.0f}%")
        print(f"    > 30g (double rescue): {pct_over_30:.0f}%")
        print(f"    > 40g (meal-sized): {pct_meal_sized:.0f}%")

    # Distribution by severity
    severity_bins = [(0, 54, 'severe (<54)'), (54, 65, 'moderate (54-65)'),
                     (65, 70, 'mild (65-70)')]
    print(f"\n  Rescue carbs by severity:")
    for lo, hi, label in severity_bins:
        subset = [e for e in all_unannounced if lo <= e['nadir_bg'] < hi]
        if subset:
            carbs_s = [e['estimated_rescue_g'] for e in subset]
            print(f"    {label}: median={np.median(carbs_s):.0f}g  "
                  f"mean={np.mean(carbs_s):.0f}g  n={len(subset)}")

    return {
        'experiment': 'EXP-1623',
        'title': 'Rescue Carb Inference from Hypo Recovery',
        'population': {
            'n_unannounced': len(all_unannounced),
            'n_announced': len(all_announced),
            'unannounced_median_g': float(np.median(u_carbs)) if all_unannounced else None,
            'unannounced_mean_g': float(np.mean(u_carbs)) if all_unannounced else None,
            'unannounced_p75_g': float(np.percentile(u_carbs, 75)) if all_unannounced else None,
            'unannounced_p95_g': float(np.percentile(u_carbs, 95)) if all_unannounced else None,
            'pct_over_15g': float(pct_over_15) if all_unannounced else None,
            'pct_over_30g': float(pct_over_30) if all_unannounced else None,
            'pct_meal_sized_40g': float(pct_meal_sized) if all_unannounced else None,
        },
        'per_patient': per_patient,
        '_all_unannounced': [
            {k: v for k, v in e.items() if not k.startswith('_')}
            for e in all_unannounced
        ],
    }


# ── EXP-1624: β-Corrected Model Validation ──────────────────────────

def exp_1624_corrected_model(patients):
    """Apply per-patient β correction and test across ALL contexts.
    
    Unlike EXP-1614 which used population β, this uses per-patient β
    derived from clean fasting steady-state balance (EXP-1621).
    """
    print("\n=== EXP-1624: β-Corrected Model Validation ===")

    per_patient = {}
    context_r2 = defaultdict(lambda: {'before': [], 'after': []})

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64)
                              if 'bolus' in df.columns else np.zeros(len(df)), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        if hasattr(df.index, 'hour'):
            hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = np.zeros(len(df))

        sd = compute_supply_demand(df, pk)

        # Compute per-patient β from clean fasting
        windows = find_clean_fasting(glucose, bolus, carbs_arr, iob, hours)
        if not windows:
            continue

        fasting_idx = np.concatenate([np.arange(s, e) for s, e in windows])
        actual_full = np.full(len(glucose), np.nan)
        for i in range(1, len(glucose)):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i-1]):
                actual_full[i] = glucose[i] - glucose[i-1]

        f_actual = actual_full[fasting_idx]
        f_supply = sd['supply'][fasting_idx]
        f_demand = sd['demand'][fasting_idx]
        valid = ~np.isnan(f_actual)
        if valid.sum() < 20:
            continue

        eff_beta = float((np.mean(f_supply[valid]) - np.mean(f_actual[valid])) /
                         max(np.mean(f_demand[valid]), 0.01))
        eff_beta = max(0.01, min(eff_beta, 5.0))  # clamp

        # Now test on FULL trace with context labeling
        N = len(glucose)
        supply = sd['supply']
        demand = sd['demand']
        actual = actual_full

        # Label contexts
        context_mask = np.full(N, 'other', dtype=object)
        # Fasting
        for s, e in windows:
            context_mask[s:e] = 'fasting'
        # Overnight (0-6 AM)
        if hasattr(df.index, 'hour'):
            overnight = (df.index.hour >= 0) & (df.index.hour < 6)
            context_mask[overnight & (context_mask == 'other')] = 'overnight'
        # Correction (bolus > 0.5, no carbs nearby)
        for i in range(6, N - 24):
            if bolus[i] >= 0.5 and np.sum(carbs_arr[max(0,i-6):i+7]) < 1:
                context_mask[i:min(i+24, N)] = 'correction'
        # Meal (carbs > 5)
        for i in range(N - 36):
            if carbs_arr[i] >= 5:
                context_mask[i:min(i+36, N)] = 'meal'

        # R² by context
        p_results = {'effective_beta': eff_beta}
        for ctx in ['fasting', 'overnight', 'correction', 'meal', 'other']:
            mask = (context_mask == ctx) & ~np.isnan(actual)
            n = mask.sum()
            if n < 20:
                continue
            a = actual[mask]
            pred_0 = supply[mask] - demand[mask]
            pred_1 = supply[mask] - demand[mask] * eff_beta
            var = np.sum((a - np.mean(a))**2)
            if var < 1e-8:
                continue
            r2_0 = 1 - np.sum((a - pred_0)**2) / var
            r2_1 = 1 - np.sum((a - pred_1)**2) / var
            p_results[f'{ctx}_r2_before'] = float(r2_0)
            p_results[f'{ctx}_r2_after'] = float(r2_1)
            p_results[f'{ctx}_n'] = int(n)
            context_r2[ctx]['before'].append(r2_0)
            context_r2[ctx]['after'].append(r2_1)

        per_patient[name] = p_results
        print(f"  {name}: β={eff_beta:.3f}  "
              f"fast={p_results.get('fasting_r2_after', 'N/A'):.4f}  "
              f"corr={p_results.get('correction_r2_after', 'N/A'):.4f}  "
              f"meal={p_results.get('meal_r2_after', 'N/A'):.4f}")

    # Population summary by context
    print(f"\n  Population R² by context (mean across patients):")
    for ctx in ['fasting', 'overnight', 'correction', 'meal', 'other']:
        b = context_r2[ctx]['before']
        a = context_r2[ctx]['after']
        if b and a:
            print(f"    {ctx:12s}: {np.mean(b):.4f} → {np.mean(a):.4f}  "
                  f"(n={len(b)} patients)")

    return {
        'experiment': 'EXP-1624',
        'title': 'β-Corrected Model Validation Across Contexts',
        'per_patient': per_patient,
        'context_summary': {
            ctx: {
                'r2_before_mean': float(np.mean(v['before'])) if v['before'] else None,
                'r2_after_mean': float(np.mean(v['after'])) if v['after'] else None,
                'n_patients': len(v['before']),
            }
            for ctx, v in context_r2.items()
        },
    }


# ── EXP-1625: Rescue Carb Profile Analysis ──────────────────────────

def exp_1625_rescue_profile(patients):
    """Characterize the temporal profile of inferred rescue carbs.
    
    Analyze minute-by-minute rescue carb absorption during hypo recovery.
    Compare to known meal absorption profiles.
    """
    print("\n=== EXP-1625: Rescue Carb Temporal Profile ===")

    # Collect residual profiles aligned to nadir
    max_steps_post = 36  # 3 hours post-nadir
    all_profiles_unannounced = []
    all_profiles_announced = []

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)

        sd = compute_supply_demand(df, pk)
        episodes = find_hypo_recovery_episodes(glucose, carbs_arr)

        for ep in episodes:
            nadir = ep['nadir_idx']
            end = min(nadir + max_steps_post, len(glucose))
            bg = glucose[nadir:end]
            sup = sd['supply'][nadir:end]
            dem = sd['demand'][nadir:end]

            profile = np.full(max_steps_post, np.nan)
            for i in range(1, min(len(bg), max_steps_post)):
                if not np.isnan(bg[i]) and not np.isnan(bg[i-1]):
                    actual = bg[i] - bg[i-1]
                    modeled = sup[i] - dem[i]
                    profile[i] = actual - modeled  # residual = rescue effect

            if np.sum(~np.isnan(profile)) < 6:
                continue

            if ep['has_announced']:
                all_profiles_announced.append(profile)
            else:
                all_profiles_unannounced.append(profile)

    # Compute mean profiles
    result = {}
    minutes = np.arange(max_steps_post) * 5  # convert to minutes

    if all_profiles_unannounced:
        profiles = np.array(all_profiles_unannounced)
        mean_profile = np.nanmean(profiles, axis=0)
        std_profile = np.nanstd(profiles, axis=0)
        peak_idx = np.nanargmax(mean_profile)
        peak_min = int(peak_idx * 5)
        result['unannounced'] = {
            'n_episodes': len(all_profiles_unannounced),
            'mean_profile': [float(x) if not np.isnan(x) else None for x in mean_profile],
            'peak_residual_mgdl_step': float(np.nanmax(mean_profile)),
            'peak_time_min': peak_min,
            'total_30min': float(np.nansum(mean_profile[:6])),
            'total_60min': float(np.nansum(mean_profile[:12])),
            'total_120min': float(np.nansum(mean_profile[:24])),
        }
        print(f"  Unannounced (n={len(all_profiles_unannounced)}): "
              f"peak={np.nanmax(mean_profile):.2f} mg/dL/step at {peak_min}min  "
              f"total_1h={np.nansum(mean_profile[:12]):.1f} mg/dL")

    if all_profiles_announced:
        profiles = np.array(all_profiles_announced)
        mean_profile = np.nanmean(profiles, axis=0)
        peak_idx = np.nanargmax(mean_profile)
        result['announced'] = {
            'n_episodes': len(all_profiles_announced),
            'mean_profile': [float(x) if not np.isnan(x) else None for x in mean_profile],
            'peak_residual_mgdl_step': float(np.nanmax(mean_profile)),
            'peak_time_min': int(peak_idx * 5),
            'total_60min': float(np.nansum(mean_profile[:12])),
        }
        print(f"  Announced (n={len(all_profiles_announced)}): "
              f"peak={np.nanmax(mean_profile):.2f} mg/dL/step at {peak_idx*5}min")

    return {
        'experiment': 'EXP-1625',
        'title': 'Rescue Carb Temporal Profile',
        **result,
    }


# ── EXP-1626: Glycogen Pool Proxy ─────────────────────────────────────

def compute_glycogen_proxy(glucose, carbs, iob, window_hours=6):
    """Estimate a relative glycogen pool state from observable signals.

    The glycogen pool is never measured directly. We construct a proxy from:
    1. Recent glucose integral (higher glucose → more glycogen loading)
    2. Recent carb intake (carbs → glycogen synthesis)
    3. Recent time below range (depletion signal)
    4. IOB trajectory (high insulin → glycogen synthesis inhibited)

    Output is normalized to [0, 1]: 0 = depleted, 1 = saturated/overflowing.
    """
    N = len(glucose)
    window = window_hours * STEPS_PER_HOUR
    proxy = np.full(N, np.nan)

    for i in range(window, N):
        bg_window = glucose[i - window:i]
        carb_window = carbs[i - window:i]
        iob_window = iob[i - window:i]

        valid = ~np.isnan(bg_window)
        if valid.sum() < window // 2:
            continue

        # Component 1: Glucose integral (mean glucose maps to glycogen loading)
        # Normalize: 70 mg/dL → 0, 180 mg/dL → 1
        mean_bg = float(np.nanmean(bg_window))
        bg_score = np.clip((mean_bg - 70) / 110, 0, 1.5)

        # Component 2: Recent carb load
        total_carbs = float(np.nansum(carb_window))
        # 0g → 0, 100g → 1 (typical 6h carb intake)
        carb_score = np.clip(total_carbs / 100, 0, 2.0)

        # Component 3: Time below range (depletion)
        time_below = float(np.nansum(bg_window[valid] < 70)) / max(valid.sum(), 1)
        depletion = time_below * 3  # amplify: even 10% time below = significant

        # Component 4: IOB effect (high insulin → inhibits glycogen synthesis)
        mean_iob = float(np.nanmean(np.abs(iob_window)))
        # High IOB → less glycogen built up
        iob_penalty = np.clip(mean_iob / 5.0, 0, 0.5)

        # Composite: weighted sum
        raw = 0.4 * bg_score + 0.3 * carb_score - 0.2 * depletion - 0.1 * iob_penalty
        proxy[i] = np.clip(raw, 0, 1)

    return proxy


def exp_1626_glycogen_proxy(patients):
    """Construct glycogen pool proxy and test if it explains metabolic variability.

    Hypotheses:
    H1: Glycogen proxy correlates with hepatic residual (depleted → less counter-reg)
    H2: Glycogen proxy modulates insulin sensitivity (full → resistant)
    H3: Glycogen state predicts hypo recovery magnitude
    H4: Glycogen transitions (rapid depletion/loading) create distinct metabolic signatures
    """
    print("\n=== EXP-1626: Glycogen Pool Proxy Construction ===")

    per_patient = {}
    all_records = []

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df, pk)

        proxy = compute_glycogen_proxy(glucose, carbs_arr, iob, window_hours=6)
        valid_proxy = ~np.isnan(proxy)

        # Compute actual dBG
        actual_dbg = np.full(len(glucose), np.nan)
        for i in range(1, len(glucose)):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i-1]):
                actual_dbg[i] = glucose[i] - glucose[i-1]

        # Residual = actual - modeled
        residual = actual_dbg - (sd['supply'] - sd['demand'])

        # Bin by glycogen state
        bins = [(0, 0.2, 'depleted'), (0.2, 0.4, 'low'), (0.4, 0.6, 'moderate'),
                (0.6, 0.8, 'full'), (0.8, 1.01, 'overflowing')]

        bin_stats = {}
        for lo, hi, label in bins:
            mask = valid_proxy & ~np.isnan(actual_dbg) & (proxy >= lo) & (proxy < hi)
            n = mask.sum()
            if n < 50:
                continue
            bin_stats[label] = {
                'n': int(n),
                'mean_residual': float(np.nanmean(residual[mask])),
                'mean_supply': float(np.mean(sd['supply'][mask])),
                'mean_demand': float(np.mean(sd['demand'][mask])),
                'mean_actual_dbg': float(np.nanmean(actual_dbg[mask])),
                'mean_glucose': float(np.nanmean(glucose[mask])),
                'std_residual': float(np.nanstd(residual[mask])),
            }

        # Correlation: proxy vs residual, proxy vs glucose variability
        both_valid = valid_proxy & ~np.isnan(residual)
        if both_valid.sum() > 100:
            r_residual, p_residual = stats.pearsonr(proxy[both_valid], residual[both_valid])
            # Effective β by glycogen state (does sensitivity change?)
            low_glyc = both_valid & (proxy < 0.3)
            high_glyc = both_valid & (proxy > 0.7)
            beta_low = None
            beta_high = None
            if low_glyc.sum() > 50 and np.mean(sd['demand'][low_glyc]) > 0.01:
                beta_low = float((np.mean(sd['supply'][low_glyc]) - np.nanmean(actual_dbg[low_glyc])) /
                                 max(np.mean(sd['demand'][low_glyc]), 0.01))
            if high_glyc.sum() > 50 and np.mean(sd['demand'][high_glyc]) > 0.01:
                beta_high = float((np.mean(sd['supply'][high_glyc]) - np.nanmean(actual_dbg[high_glyc])) /
                                  max(np.mean(sd['demand'][high_glyc]), 0.01))
        else:
            r_residual, p_residual = 0, 1
            beta_low, beta_high = None, None

        per_patient[name] = {
            'proxy_mean': float(np.nanmean(proxy[valid_proxy])),
            'proxy_std': float(np.nanstd(proxy[valid_proxy])),
            'n_valid': int(valid_proxy.sum()),
            'r_proxy_vs_residual': float(r_residual),
            'p_proxy_vs_residual': float(p_residual),
            'beta_low_glycogen': beta_low,
            'beta_high_glycogen': beta_high,
            'bins': bin_stats,
        }

        beta_str = ""
        if beta_low is not None and beta_high is not None:
            beta_str = f"  β_low={beta_low:.3f} β_high={beta_high:.3f}"
        print(f"  {name}: proxy_mean={np.nanmean(proxy[valid_proxy]):.3f}  "
              f"r(proxy,residual)={r_residual:.3f}{beta_str}")

        # Collect for population analysis
        for i in range(len(glucose)):
            if valid_proxy[i] and not np.isnan(actual_dbg[i]):
                all_records.append({
                    'patient': name,
                    'glycogen': proxy[i],
                    'residual': residual[i],
                    'actual_dbg': actual_dbg[i],
                    'supply': sd['supply'][i],
                    'demand': sd['demand'][i],
                    'glucose': glucose[i],
                })

    # Population analysis
    if all_records:
        glyc = np.array([r['glycogen'] for r in all_records])
        resid = np.array([r['residual'] for r in all_records])
        valid = ~np.isnan(resid)

        r_pop, p_pop = stats.pearsonr(glyc[valid], resid[valid])
        print(f"\n  Population r(glycogen, residual) = {r_pop:.4f}  (p={p_pop:.2e})")

        # ANOVA: does glycogen state explain residual variance?
        groups = []
        for lo, hi in [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]:
            mask = valid & (glyc >= lo) & (glyc < hi)
            if mask.sum() > 50:
                groups.append(resid[mask])
        if len(groups) >= 3:
            f_stat, p_anova = stats.f_oneway(*groups)
            print(f"  ANOVA F={f_stat:.2f}  p={p_anova:.2e}")
        else:
            f_stat, p_anova = 0, 1

    return {
        'experiment': 'EXP-1626',
        'title': 'Glycogen Pool Proxy: Hidden State Variable',
        'per_patient': per_patient,
        'population': {
            'r_proxy_vs_residual': float(r_pop) if all_records else None,
            'p_proxy_vs_residual': float(p_pop) if all_records else None,
            'anova_f': float(f_stat) if all_records else None,
            'anova_p': float(p_anova) if all_records else None,
            'n_records': len(all_records),
        },
    }


# ── EXP-1627: Glycogen Modulates Sensitivity ─────────────────────────

def exp_1627_glycogen_sensitivity(patients):
    """Test whether glycogen state modulates effective insulin sensitivity.

    Clinical knowledge:
    - Full glycogen + high glucose → insulin resistance (β decreases)
    - Depleted glycogen + low glucose → increased sensitivity (β increases)
    - DKA / extended hyperglycemia → profound resistance
    - Post-exercise with depleted glycogen → hypersensitivity

    We test: does the effective β (insulin effectiveness) vary systematically
    with the glycogen proxy? If so, glycogen is an actionable hidden variable.
    """
    print("\n=== EXP-1627: Glycogen Modulates Insulin Sensitivity ===")

    per_patient = {}
    all_beta_by_quintile = defaultdict(list)

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df, pk)
        proxy = compute_glycogen_proxy(glucose, carbs_arr, iob, window_hours=6)

        actual_dbg = np.full(len(glucose), np.nan)
        for i in range(1, len(glucose)):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i-1]):
                actual_dbg[i] = glucose[i] - glucose[i-1]

        valid = ~np.isnan(proxy) & ~np.isnan(actual_dbg)

        # Compute β by glycogen quintile
        proxy_valid = proxy[valid]
        try:
            quintiles = np.percentile(proxy_valid, [20, 40, 60, 80])
        except Exception:
            continue

        q_labels = ['Q1_depleted', 'Q2_low', 'Q3_moderate', 'Q4_full', 'Q5_overflowing']
        q_edges = [0] + list(quintiles) + [1.01]

        p_result = {}
        for qi in range(5):
            lo, hi = q_edges[qi], q_edges[qi + 1]
            mask = valid & (proxy >= lo) & (proxy < hi) & (sd['demand'] > 0.1)
            n = mask.sum()
            if n < 30:
                continue
            a = actual_dbg[mask]
            s = sd['supply'][mask]
            d = sd['demand'][mask]

            # β = (supply - actual_dBG) / demand
            eff_beta = float((np.mean(s) - np.nanmean(a)) / max(np.mean(d), 0.01))
            eff_beta = max(-2, min(eff_beta, 10))

            # Also: residual magnitude as proxy for unmodeled effects
            residual_std = float(np.nanstd(a - (s - d)))

            p_result[q_labels[qi]] = {
                'n': int(n),
                'effective_beta': eff_beta,
                'mean_demand': float(np.mean(d)),
                'mean_supply': float(np.mean(s)),
                'mean_glucose': float(np.nanmean(glucose[mask])),
                'residual_std': residual_std,
            }
            all_beta_by_quintile[q_labels[qi]].append(eff_beta)

        per_patient[name] = p_result

        # Print trend
        betas = [p_result[q]['effective_beta'] for q in q_labels if q in p_result]
        if len(betas) >= 3:
            trend = "↑" if betas[-1] > betas[0] else "↓"
            print(f"  {name}: β across glycogen quintiles: "
                  f"{' → '.join(f'{b:.2f}' for b in betas)}  {trend}")

    # Population: is there a monotonic trend?
    print(f"\n  Population β by glycogen quintile:")
    pop_betas = []
    for q in ['Q1_depleted', 'Q2_low', 'Q3_moderate', 'Q4_full', 'Q5_overflowing']:
        if q in all_beta_by_quintile:
            vals = all_beta_by_quintile[q]
            mean_b = float(np.mean(vals))
            pop_betas.append(mean_b)
            print(f"    {q:20s}: β = {mean_b:.3f} ± {np.std(vals):.3f}  (n={len(vals)} patients)")

    if len(pop_betas) >= 3:
        trend_r, trend_p = stats.spearmanr(range(len(pop_betas)), pop_betas)
        print(f"  Monotonic trend: Spearman r = {trend_r:.3f}  (p={trend_p:.4f})")
        if trend_r < -0.5:
            print(f"  → CONFIRMED: Sensitivity DECREASES as glycogen fills (resistance)")
        elif trend_r > 0.5:
            print(f"  → Sensitivity INCREASES with glycogen (unexpected)")
        else:
            print(f"  → No clear monotonic trend")

    return {
        'experiment': 'EXP-1627',
        'title': 'Glycogen Pool Modulates Insulin Sensitivity',
        'per_patient': per_patient,
        'population_beta_by_quintile': {
            q: {
                'mean_beta': float(np.mean(v)),
                'std_beta': float(np.std(v)),
                'n_patients': len(v),
            }
            for q, v in all_beta_by_quintile.items()
        },
        'trend_spearman_r': float(trend_r) if len(pop_betas) >= 3 else None,
        'trend_p': float(trend_p) if len(pop_betas) >= 3 else None,
    }


# ── EXP-1628: Glycogen Predicts Hypo Recovery ────────────────────────

def exp_1628_glycogen_hypo_recovery(patients):
    """Test whether pre-hypo glycogen state predicts recovery dynamics.

    If glycogen is depleted before a hypo:
    - Counter-regulatory response is WEAKER (less hepatic glucose available)
    - Patient needs MORE rescue carbs
    - Recovery is slower or shallower without rescue eating
    
    If glycogen is full before a hypo:
    - Counter-regulatory response is STRONGER
    - Less rescue carbs needed
    - Recovery may be faster / more bounce-back
    """
    print("\n=== EXP-1628: Glycogen State Predicts Hypo Recovery ===")

    all_episodes = []
    per_patient = {}

    for p in patients:
        name, df, pk = p['name'], p['df'], p['pk']
        glucose = df['glucose'].values.astype(np.float64)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                   if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df, pk)
        proxy = compute_glycogen_proxy(glucose, carbs_arr, iob, window_hours=6)

        episodes = find_hypo_recovery_episodes(glucose, carbs_arr)

        p_episodes = []
        for ep in episodes:
            nadir = ep['nadir_idx']
            rec_end = ep['recovery_end']

            if np.isnan(proxy[nadir]):
                continue

            # Pre-hypo glycogen (at nadir)
            glyc_at_nadir = float(proxy[nadir])

            # Recovery slope (first 30 min post-nadir)
            end_30 = min(nadir + 6, len(glucose))
            bg_30 = glucose[nadir:end_30]
            valid_30 = ~np.isnan(bg_30)
            if valid_30.sum() < 3:
                continue
            recovery_slope = float((np.nanmean(bg_30[-3:]) - bg_30[0]) / max(valid_30.sum(), 1))

            # Residual sum in recovery (proxy for rescue carb amount)
            bg = glucose[nadir:rec_end]
            sup = sd['supply'][nadir:rec_end]
            dem = sd['demand'][nadir:rec_end]
            residual_sum = 0
            for i in range(1, min(len(bg), 24)):
                if not np.isnan(bg[i]) and not np.isnan(bg[i-1]):
                    actual = bg[i] - bg[i-1]
                    modeled = sup[i] - dem[i]
                    residual_sum += max(actual - modeled, 0)

            entry = {
                'patient': name,
                'nadir_bg': ep['nadir_bg'],
                'glycogen_at_nadir': glyc_at_nadir,
                'rebound_mg': ep['rebound_mg'],
                'recovery_slope_30min': recovery_slope,
                'rescue_residual': float(residual_sum),
                'has_announced': ep['has_announced'],
            }
            p_episodes.append(entry)
            all_episodes.append(entry)

        if p_episodes:
            glyc_vals = [e['glycogen_at_nadir'] for e in p_episodes]
            rebound_vals = [e['rebound_mg'] for e in p_episodes]
            if len(glyc_vals) > 10:
                r, p_val = stats.pearsonr(glyc_vals, rebound_vals)
            else:
                r, p_val = 0, 1
            per_patient[name] = {
                'n_episodes': len(p_episodes),
                'r_glycogen_vs_rebound': float(r),
                'p_value': float(p_val),
                'mean_glycogen_at_hypo': float(np.mean(glyc_vals)),
            }
            print(f"  {name}: n={len(p_episodes)}  r(glycogen, rebound)={r:.3f}  "
                  f"mean_glyc={np.mean(glyc_vals):.3f}")

    # Population analysis: glycogen terciles
    if all_episodes:
        glyc = np.array([e['glycogen_at_nadir'] for e in all_episodes])
        rebound = np.array([e['rebound_mg'] for e in all_episodes])
        rescue = np.array([e['rescue_residual'] for e in all_episodes])
        slope = np.array([e['recovery_slope_30min'] for e in all_episodes])

        try:
            terciles = np.percentile(glyc, [33, 67])
        except Exception:
            terciles = [0.3, 0.6]

        print(f"\n  By glycogen tercile (n={len(all_episodes)} episodes):")
        for label, lo, hi in [('Depleted', 0, terciles[0]),
                               ('Moderate', terciles[0], terciles[1]),
                               ('Full', terciles[1], 1.01)]:
            mask = (glyc >= lo) & (glyc < hi)
            n = mask.sum()
            if n < 10:
                continue
            print(f"    {label:10s} (n={n:4d}): "
                  f"rebound={np.mean(rebound[mask]):.0f}mg  "
                  f"rescue_residual={np.mean(rescue[mask]):.0f}  "
                  f"recovery_slope={np.mean(slope[mask]):.2f}")

        r_pop, p_pop = stats.pearsonr(glyc, rebound)
        r_rescue, p_rescue = stats.pearsonr(glyc, rescue)
        print(f"\n  Population: r(glycogen, rebound)={r_pop:.3f} (p={p_pop:.2e})")
        print(f"  Population: r(glycogen, rescue)={r_rescue:.3f} (p={p_rescue:.2e})")

    return {
        'experiment': 'EXP-1628',
        'title': 'Glycogen State Predicts Hypo Recovery Dynamics',
        'per_patient': per_patient,
        'population': {
            'n_episodes': len(all_episodes),
            'r_glycogen_vs_rebound': float(r_pop) if all_episodes else None,
            'p_glycogen_vs_rebound': float(p_pop) if all_episodes else None,
            'r_glycogen_vs_rescue': float(r_rescue) if all_episodes else None,
            'p_glycogen_vs_rescue': float(p_rescue) if all_episodes else None,
        } if all_episodes else {},
        '_all_episodes': all_episodes[:500],  # sample for viz
    }


# ── Figures ────────────────────────────────────────────────────────────

def generate_figures(results):
    """Generate visualization figures."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Demand chain diagnosis — observed vs expected demand
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1621 = results['EXP-1621']
    pp = r1621['per_patient']
    patients_sorted = sorted(pp.keys())
    expected = [pp[p]['expected_basal_demand'] for p in patients_sorted]
    observed = [pp[p]['observed_demand'] for p in patients_sorted]
    eff_betas = [pp[p]['effective_beta'] for p in patients_sorted]

    x = np.arange(len(patients_sorted))
    width = 0.35
    axes[0].bar(x - width/2, expected, width, label='Expected (basal×ISF)', color='#4CAF50', alpha=0.7)
    axes[0].bar(x + width/2, observed, width, label='Observed (PK chain)', color='#F44336', alpha=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(patients_sorted)
    axes[0].set_ylabel('Demand (mg/dL per 5-min)')
    axes[0].set_title('Demand: Expected vs PK-Computed')
    axes[0].legend()

    axes[1].bar(x, eff_betas, color='#2196F3', alpha=0.8)
    axes[1].axhline(y=1.0, color='k', linestyle='--', alpha=0.5, label='Perfect model')
    axes[1].axhline(y=np.mean(eff_betas), color='r', linestyle='-', alpha=0.7,
                    label=f'Mean β={np.mean(eff_betas):.3f}')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(patients_sorted)
    axes[1].set_ylabel('Effective β (steady-state)')
    axes[1].set_title('Steady-State β by Patient')
    axes[1].legend()

    fig.suptitle('EXP-1621: Why Is Demand 5× Too High?', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'demand-fig1-chain-diagnosis.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Steady-state balance R² comparison
    fig, ax = plt.subplots(figsize=(12, 6))
    r1622 = results['EXP-1622']
    pp = r1622['per_patient']
    patients_sorted = sorted(pp.keys())
    models = ['r2_model0_original', 'r2_model2_beta_corrected']
    labels = ['Original', 'β-Corrected']
    colors = ['#F44336', '#4CAF50']

    x = np.arange(len(patients_sorted))
    width = 0.35
    for j, (model, label, color) in enumerate(zip(models, labels, colors)):
        vals = [pp[p].get(model, 0) for p in patients_sorted]
        ax.bar(x + j*width - width/2, vals, width, label=label, color=color, alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels(patients_sorted)
    ax.set_ylabel('R²')
    ax.set_title('Clean Fasting R²: Original vs β-Corrected')
    ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
    ax.legend()
    fig.suptitle('EXP-1622: Does β-Correction Fix Steady-State?', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'demand-fig2-steady-state.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Rescue carb distribution
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    r1623 = results['EXP-1623']
    if '_all_unannounced' in r1623 and r1623['_all_unannounced']:
        u_carbs = [e['estimated_rescue_g'] for e in r1623['_all_unannounced']]
        u_carbs_clipped = np.clip(u_carbs, 0, 150)
        axes[0].hist(u_carbs_clipped, bins=30, color='#F44336', alpha=0.7, edgecolor='black')
        axes[0].axvline(x=15, color='green', linestyle='--', linewidth=2, label='Standard rescue (15g)')
        axes[0].axvline(x=30, color='orange', linestyle='--', linewidth=2, label='Double rescue (30g)')
        axes[0].axvline(x=float(np.median(u_carbs)), color='blue', linestyle='-', linewidth=2,
                        label=f'Median ({np.median(u_carbs):.0f}g)')
        axes[0].set_xlabel('Estimated Rescue Carbs (g)')
        axes[0].set_ylabel('Count')
        axes[0].set_title('Inferred Rescue Carb Distribution')
        axes[0].legend()

        # By nadir depth
        nadirs = [e['nadir_bg'] for e in r1623['_all_unannounced']]
        axes[1].scatter(nadirs, u_carbs_clipped, alpha=0.3, s=20, color='#F44336')
        axes[1].set_xlabel('Nadir BG (mg/dL)')
        axes[1].set_ylabel('Estimated Rescue Carbs (g)')
        axes[1].set_title('Rescue Carbs vs Hypo Severity')
        axes[1].axhline(y=15, color='green', linestyle='--', alpha=0.5)
        axes[1].axvline(x=54, color='red', linestyle='--', alpha=0.5, label='Severe (<54)')
        axes[1].legend()

    fig.suptitle('EXP-1623: How Much Do Patients Actually Eat During Hypos?',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'demand-fig3-rescue-carbs.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: β-corrected R² by context
    fig, ax = plt.subplots(figsize=(10, 6))
    r1624 = results['EXP-1624']
    ctx_sum = r1624.get('context_summary', {})
    contexts = ['fasting', 'overnight', 'correction', 'meal', 'other']
    ctx_present = [c for c in contexts if c in ctx_sum and ctx_sum[c]['r2_before_mean'] is not None]
    before = [ctx_sum[c]['r2_before_mean'] for c in ctx_present]
    after = [ctx_sum[c]['r2_after_mean'] for c in ctx_present]

    x = np.arange(len(ctx_present))
    width = 0.35
    ax.bar(x - width/2, before, width, label='Original', color='#F44336', alpha=0.7)
    ax.bar(x + width/2, after, width, label='β-Corrected', color='#4CAF50', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(ctx_present)
    ax.set_ylabel('Mean R² (across patients)')
    ax.set_title('Model R² by Context: Before vs After β-Correction')
    ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
    ax.legend()
    fig.suptitle('EXP-1624: Does Per-Patient β Fix the Model?', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'demand-fig4-corrected-contexts.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: Rescue carb temporal profile
    fig, ax = plt.subplots(figsize=(10, 6))
    r1625 = results['EXP-1625']
    minutes = np.arange(36) * 5
    if 'unannounced' in r1625:
        profile = r1625['unannounced']['mean_profile']
        profile_arr = np.array([x if x is not None else np.nan for x in profile])
        ax.plot(minutes, profile_arr, 'r-', linewidth=2, label='Unannounced rescue')
        ax.fill_between(minutes, 0, np.maximum(profile_arr, 0), alpha=0.2, color='red')
    if 'announced' in r1625:
        profile = r1625['announced']['mean_profile']
        profile_arr = np.array([x if x is not None else np.nan for x in profile])
        ax.plot(minutes, profile_arr, 'b-', linewidth=2, label='Announced rescue')
    ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
    ax.set_xlabel('Minutes After Nadir')
    ax.set_ylabel('Residual (mg/dL per 5-min step)')
    ax.set_title('Rescue Carb Absorption Profile (Aligned to Hypo Nadir)')
    ax.legend()
    fig.suptitle('EXP-1625: What Does Rescue Eating Look Like?', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'demand-fig5-rescue-profile.png', dpi=150)
    plt.close()
    print("  Saved fig5")

    # Fig 6: Glycogen proxy — residual by glycogen bin
    if 'EXP-1626' in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        r1626 = results['EXP-1626']
        pp = r1626['per_patient']
        bin_labels = ['depleted', 'low', 'moderate', 'full', 'overflowing']
        colors_bins = ['#D32F2F', '#FF9800', '#4CAF50', '#2196F3', '#9C27B0']

        # Aggregate bins across patients
        agg_resid = defaultdict(list)
        agg_supply = defaultdict(list)
        for pname, pdata in pp.items():
            for b in bin_labels:
                if b in pdata.get('bins', {}):
                    agg_resid[b].append(pdata['bins'][b]['mean_residual'])
                    agg_supply[b].append(pdata['bins'][b]['mean_supply'])

        present = [b for b in bin_labels if b in agg_resid and len(agg_resid[b]) >= 3]
        x = np.arange(len(present))
        resid_means = [np.mean(agg_resid[b]) for b in present]
        resid_stds = [np.std(agg_resid[b]) for b in present]
        bar_colors = [colors_bins[bin_labels.index(b)] for b in present]

        axes[0].bar(x, resid_means, yerr=resid_stds, color=bar_colors, alpha=0.8,
                    edgecolor='black', capsize=4)
        axes[0].axhline(y=0, color='k', linestyle='--', alpha=0.3)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(present, rotation=15)
        axes[0].set_ylabel('Mean Residual (mg/dL/step)')
        axes[0].set_title('Model Residual by Glycogen State')

        # Fig 6b: β by glycogen quintile
        if 'EXP-1627' in results:
            r1627 = results['EXP-1627']
            q_data = r1627.get('population_beta_by_quintile', {})
            q_labels = ['Q1_depleted', 'Q2_low', 'Q3_moderate', 'Q4_full', 'Q5_overflowing']
            q_short = ['Depleted', 'Low', 'Moderate', 'Full', 'Overflow']
            q_present = [q for q in q_labels if q in q_data]
            if q_present:
                x2 = np.arange(len(q_present))
                betas = [q_data[q]['mean_beta'] for q in q_present]
                beta_stds = [q_data[q]['std_beta'] for q in q_present]
                q_colors = [colors_bins[q_labels.index(q)] for q in q_present]
                axes[1].bar(x2, betas, yerr=beta_stds, color=q_colors, alpha=0.8,
                            edgecolor='black', capsize=4)
                axes[1].axhline(y=1.0, color='k', linestyle='--', alpha=0.5, label='β=1 (perfect)')
                axes[1].set_xticks(x2)
                axes[1].set_xticklabels([q_short[q_labels.index(q)] for q in q_present], rotation=15)
                axes[1].set_ylabel('Effective β (insulin effectiveness)')
                axes[1].set_title('Does Glycogen State Modulate Sensitivity?')
                axes[1].legend()

        fig.suptitle('EXP-1626/1627: The Hidden Glycogen Variable', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(FIGURES_DIR / 'demand-fig6-glycogen-proxy.png', dpi=150)
        plt.close()
        print("  Saved fig6")

    # Fig 7: Glycogen predicts hypo recovery
    if 'EXP-1628' in results:
        r1628 = results['EXP-1628']
        episodes = r1628.get('_all_episodes', [])
        if episodes:
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
            glyc = [e['glycogen_at_nadir'] for e in episodes]
            rebound = [e['rebound_mg'] for e in episodes]
            rescue = [e['rescue_residual'] for e in episodes]

            axes[0].scatter(glyc, rebound, alpha=0.2, s=15, color='#F44336')
            # Trend line
            z = np.polyfit(glyc, rebound, 1)
            x_line = np.linspace(0, 1, 50)
            axes[0].plot(x_line, np.polyval(z, x_line), 'k-', linewidth=2,
                        label=f'slope={z[0]:.1f}')
            axes[0].set_xlabel('Glycogen Proxy at Nadir')
            axes[0].set_ylabel('Rebound Magnitude (mg/dL)')
            axes[0].set_title('Higher Glycogen → More Rebound?')
            axes[0].legend()

            axes[1].scatter(glyc, rescue, alpha=0.2, s=15, color='#2196F3')
            z2 = np.polyfit(glyc, rescue, 1)
            axes[1].plot(x_line, np.polyval(z2, x_line), 'k-', linewidth=2,
                        label=f'slope={z2[0]:.1f}')
            axes[1].set_xlabel('Glycogen Proxy at Nadir')
            axes[1].set_ylabel('Rescue Residual (mg/dL total)')
            axes[1].set_title('Higher Glycogen → Less Rescue Needed?')
            axes[1].legend()

            fig.suptitle('EXP-1628: Does Glycogen State Predict Hypo Recovery?',
                        fontsize=14, fontweight='bold')
            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'demand-fig7-glycogen-hypo.png', dpi=150)
            plt.close()
            print("  Saved fig7")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Demand Diagnosis & Rescue Carb Inference')
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(
        patients_dir=str(PATIENTS_DIR),
        max_patients=args.max_patients,
    )
    print(f"Loaded {len(patients)} patients")

    results = {}

    r1621 = exp_1621_demand_diagnosis(patients)
    results['EXP-1621'] = r1621

    r1622 = exp_1622_steady_state_balance(patients)
    results['EXP-1622'] = r1622

    r1623 = exp_1623_rescue_carb_inference(patients)
    results['EXP-1623'] = r1623

    r1624 = exp_1624_corrected_model(patients)
    results['EXP-1624'] = r1624

    r1625 = exp_1625_rescue_profile(patients)
    results['EXP-1625'] = r1625

    r1626 = exp_1626_glycogen_proxy(patients)
    results['EXP-1626'] = r1626

    r1627 = exp_1627_glycogen_sensitivity(patients)
    results['EXP-1627'] = r1627

    r1628 = exp_1628_glycogen_hypo_recovery(patients)
    results['EXP-1628'] = r1628

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, data in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_demand_rescue.json"
        clean = {}
        for k, v in data.items():
            if k.startswith('_'):
                continue
            clean[k] = v
        with open(RESULTS_DIR / fname, 'w') as f:
            json.dump(clean, f, indent=2, default=str)
    print(f"\nSaved {len(results)} experiment JSONs")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if r1623.get('population', {}).get('unannounced_median_g'):
        pop = r1623['population']
        print(f"  Rescue carbs (unannounced): median={pop['unannounced_median_g']:.0f}g  "
              f"mean={pop['unannounced_mean_g']:.0f}g  P75={pop['unannounced_p75_g']:.0f}g")
        print(f"  > 15g: {pop['pct_over_15g']:.0f}%  > 30g: {pop['pct_over_30g']:.0f}%  "
              f"> 40g (meal-sized): {pop['pct_meal_sized_40g']:.0f}%")

    if 'EXP-1626' in results:
        pop26 = results['EXP-1626'].get('population', {})
        if pop26.get('r_proxy_vs_residual') is not None:
            print(f"\n  Glycogen proxy:")
            print(f"    r(glycogen, residual) = {pop26['r_proxy_vs_residual']:.4f}  "
                  f"(p={pop26['p_proxy_vs_residual']:.2e})")
            print(f"    ANOVA F = {pop26.get('anova_f', 0):.2f}  "
                  f"(p={pop26.get('anova_p', 1):.2e})")
    if 'EXP-1627' in results:
        trend_r = results['EXP-1627'].get('trend_spearman_r')
        if trend_r is not None:
            print(f"    Sensitivity trend (Spearman): r = {trend_r:.3f}")
    if 'EXP-1628' in results:
        pop28 = results['EXP-1628'].get('population', {})
        if pop28.get('r_glycogen_vs_rebound') is not None:
            print(f"    Glycogen→rebound: r = {pop28['r_glycogen_vs_rebound']:.3f}")
            print(f"    Glycogen→rescue:  r = {pop28['r_glycogen_vs_rescue']:.3f}")


if __name__ == '__main__':
    main()
