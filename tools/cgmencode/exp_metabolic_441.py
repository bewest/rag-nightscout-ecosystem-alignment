#!/usr/bin/env python3
"""EXP-441 through EXP-445: Product Flux, TDD Normalization, and Metabolic Throughput.

Building on EXP-435–440 (metabolic flux = |insulin| + |carb|), these experiments
test the user's insight that glucose dynamics are better captured as the PRODUCT
of supply and demand harmonics, with hepatic production as the always-on baseline.

Key insight: The liver never stops producing glucose. The true decomposition is:
  SUPPLY(t) = hepatic_production(t) + carb_absorption(t)   (always > 0)
  DEMAND(t) = insulin_action(t)                             (always > 0 with basal)
  dBG/dt ≈ SUPPLY - DEMAND

The PRODUCT (supply × demand) captures metabolic THROUGHPUT — how hard the
system is working to maintain homeostasis.  The RATIO (supply / demand) captures
the balance direction.

EXP-441: Product flux with hepatic (supply × demand) vs current sum flux
EXP-442: TDD-normalized channels — rolling TDD, insulin as fraction of daily dose
EXP-443: Throughput + balance as dual channels (product AND ratio)
EXP-444: Log-power spectrum of metabolic throughput across time scales
EXP-445: Cross-patient equivariance with TDD normalization

References:
  - cgmsim-lib liver.ts: Hill equation for insulin suppression of EGP
  - cgmsim-lib sinus.ts: Circadian ±20% modulation
  - AndroidAPS TddCalculatorImpl.kt: TDD = Σ(bolus) + Σ(basal × 5/60)
  - GluPredKit loop_v2.py: ISF = 1800/TDD, CR = 500/TDD (population rules)
  - continuous_pk.py: compute_hepatic_production(), compute_net_metabolic_balance()
  - exp_metabolic_flux.py: EXP-435–440 sum-based flux (predecessor)
"""

import sys, os, json, argparse, warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings('ignore', category=RuntimeWarning)

# ── Imports from existing infrastructure ──────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import (
    build_continuous_pk_features,
    compute_hepatic_production,
    compute_net_metabolic_balance,
    expand_schedule,
    PK_NORMALIZATION,
    PK_CHANNEL_NAMES,
)

# Reuse patient loading from metabolic flux experiments
from cgmencode.exp_metabolic_flux import (
    load_patients,
    _extract_isf_scalar,
    _extract_cr_scalar,
    classify_windows_by_event,
)

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── Core: Supply-Demand Decomposition ─────────────────────────────────

def compute_supply_demand(df, pk_array=None):
    """Decompose glucose dynamics into supply and demand harmonics.

    Supply = hepatic_production + carb_absorption (glucose appearance, always > 0)
    Demand = insulin_action (glucose disposal, always > 0 with basal)

    Both are in mg/dL per 5-min step (same units as net_balance).

    Args:
        df: Patient DataFrame with iob, cob, bolus, carbs, temp_rate columns
            and attrs containing isf_schedule, cr_schedule, basal_schedule
        pk_array: Optional (N, 8) PK array. If provided, extracts channels
                  directly (faster). Otherwise recomputes from df.

    Returns:
        dict with keys:
            supply: (N,) hepatic + carb absorption (mg/dL per 5min)
            demand: (N,) insulin action (mg/dL per 5min)
            hepatic: (N,) hepatic production alone (mg/dL per 5min)
            carb_supply: (N,) carb absorption alone (mg/dL per 5min)
            product: (N,) supply × demand (throughput)
            ratio: (N,) supply / demand (balance, >1 rising, <1 falling)
            sum_flux: (N,) |supply - demand| + hepatic (original-style for comparison)
            net: (N,) supply - demand (signed, same as net_balance)
    """
    N = len(df)

    if pk_array is not None and pk_array.shape[1] >= 8:
        # Extract from pre-computed PK channels (denormalize)
        # Channel indices: 0=insulin_total, 5=hepatic_production, 6=net_balance, 7=isf_curve
        insulin_total = pk_array[:, 0] * PK_NORMALIZATION['insulin_total']   # U/min
        hepatic_raw = pk_array[:, 5] * PK_NORMALIZATION['hepatic_production']  # mg/dL per 5min
        net_balance = pk_array[:, 6] * PK_NORMALIZATION['net_balance']         # mg/dL per 5min
        isf_curve = pk_array[:, 7] * PK_NORMALIZATION['isf_curve']             # mg/dL/U
        carb_rate = pk_array[:, 3] * PK_NORMALIZATION['carb_rate']             # g/min

        # Reconstruct supply and demand from PK channels
        # demand = insulin_activity × 5min × ISF (mg/dL per step)
        demand = np.abs(insulin_total * 5.0 * isf_curve)

        # carb_supply = carb_rate × 5min × (ISF / CR)
        cr_sched = df.attrs.get('cr_schedule', [])
        if cr_sched:
            cr_vals = [e.get('value', e.get('carbratio', 10)) for e in cr_sched]
            cr_scalar = float(np.median(cr_vals))
        else:
            cr_scalar = 10.0
        carb_supply = np.abs(carb_rate * 5.0 * (isf_curve / max(cr_scalar, 1.0)))

        hepatic = np.maximum(hepatic_raw, 0)
        supply = hepatic + carb_supply
    else:
        # Recompute from scratch
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)

        # Get IOB for hepatic computation
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        # Get hour-of-day array
        if hasattr(df.index, 'hour'):
            hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = np.zeros(N)

        # Hepatic production (Hill equation + circadian)
        hepatic = compute_hepatic_production(iob, hours, weight_kg=70.0)

        # Carb absorption from COB deltas
        cob = np.nan_to_num(df['cob'].values.astype(np.float64), nan=0.0)
        delta_cob = np.zeros_like(cob)
        delta_cob[1:] = cob[:-1] - cob[1:]  # positive = carbs being absorbed
        carb_supply = np.abs(delta_cob * (isf / max(cr, 1.0)))

        supply = hepatic + carb_supply

        # Insulin action from IOB deltas
        delta_iob = np.zeros_like(iob)
        delta_iob[1:] = iob[:-1] - iob[1:]  # positive = insulin being absorbed
        demand = np.abs(delta_iob * isf)

    # Ensure non-negative
    supply = np.maximum(supply, 0)
    demand = np.maximum(demand, 0)

    eps = 1e-8

    # Product = metabolic throughput
    product = supply * demand

    # Ratio = balance direction (>1 = glucose rising)
    ratio = supply / (demand + eps)

    # Net = signed flux (same as net_balance concept)
    net = supply - demand

    # Original-style sum flux for comparison
    sum_flux = np.abs(supply - hepatic) + demand  # carb_supply + demand (no hepatic)

    return {
        'supply': supply,
        'demand': demand,
        'hepatic': hepatic,
        'carb_supply': carb_supply if 'carb_supply' in dir() else supply - hepatic,
        'product': product,
        'ratio': ratio,
        'sum_flux': sum_flux,
        'net': net,
    }


def compute_rolling_tdd(df, window_hours=24):
    """Compute rolling Total Daily Dose from bolus + basal columns.

    Following AndroidAPS pattern: TDD = Σ(bolus) + Σ(actual_basal × 5/60).

    Args:
        df: Patient DataFrame with bolus, temp_rate (or net_basal) columns
        window_hours: Rolling window size in hours (default 24)

    Returns:
        (N,) array of rolling TDD in U/day
    """
    N = len(df)
    steps_per_window = int(window_hours * 12)  # 12 steps per hour at 5-min
    tdd = np.full(N, np.nan)

    # Bolus insulin
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)

    # Actual basal rate: temp_rate if available, else scheduled + net_basal
    if 'temp_rate' in df.columns:
        basal_uhr = np.nan_to_num(df['temp_rate'].values.astype(np.float64), nan=0.0)
    else:
        # Reconstruct from scheduled + net deviation
        basal_sched = df.attrs.get('basal_schedule', [])
        if basal_sched:
            sched_vals = [e.get('value', e.get('rate', 0.8)) for e in basal_sched]
            sched_rate = float(np.median(sched_vals))
        else:
            sched_rate = 0.8
        net = np.nan_to_num(df['net_basal'].values.astype(np.float64), nan=0.0)
        basal_uhr = sched_rate + net

    basal_uhr = np.maximum(basal_uhr, 0)

    # Insulin per 5-min step: basal_rate(U/hr) × (5/60) hr + bolus(U)
    insulin_per_step = basal_uhr * (5.0 / 60.0) + bolus

    # Rolling sum (24h window)
    cumsum = np.cumsum(insulin_per_step)
    for i in range(steps_per_window, N):
        tdd[i] = cumsum[i] - cumsum[i - steps_per_window]

    # Fill first window with first valid value
    first_valid = tdd[steps_per_window] if steps_per_window < N else np.nan
    tdd[:steps_per_window] = first_valid

    # Scale to daily rate if window != 24h
    tdd = tdd * (24.0 / window_hours)

    return tdd


def compute_tdd_normalized_channels(df, pk_array, tdd):
    """Express insulin channels as fraction of TDD.

    Following GluPredKit pattern: ISF ≈ 1800/TDD.
    Normalizing insulin by TDD is equivalent to multiplying by ISF/1800.

    Args:
        df: Patient DataFrame
        pk_array: (N, 8) PK features
        tdd: (N,) rolling TDD array

    Returns:
        dict with TDD-normalized channels
    """
    eps = 1e-8
    tdd_safe = np.maximum(tdd, eps)

    # insulin_total as fraction of daily rate
    insulin_total_raw = pk_array[:, 0] * PK_NORMALIZATION['insulin_total']  # U/min
    daily_rate = tdd_safe / (24 * 60)  # U/min average
    insulin_frac = insulin_total_raw / (daily_rate + eps)

    # Bolus as fraction of TDD
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
    bolus_frac = bolus / (tdd_safe + eps)

    # Implied ISF from 1800 rule
    isf_1800 = 1800.0 / (tdd_safe + eps)

    # ISF-implied glucose effect of insulin
    insulin_effect_tdd = insulin_total_raw * 5.0 * isf_1800  # mg/dL per step

    return {
        'insulin_frac': insulin_frac,        # dimensionless, 1.0 = average rate
        'bolus_frac': bolus_frac,            # dimensionless, fraction of daily dose
        'isf_1800': isf_1800,                # mg/dL/U, population-estimated ISF
        'insulin_effect_tdd': insulin_effect_tdd,  # mg/dL per step (TDD-normalized)
        'tdd': tdd,                          # U/day
    }


# ── Window utilities ──────────────────────────────────────────────────

def window_stats(arr, window_size, step=None):
    """Compute windowed statistics for an array."""
    if step is None:
        step = window_size // 2
    N = len(arr)
    windows = []
    for start in range(0, N - window_size + 1, step):
        w = arr[start:start + window_size]
        if np.all(np.isnan(w)):
            continue
        w_clean = w[~np.isnan(w)]
        if len(w_clean) < window_size // 4:
            continue
        windows.append({
            'start': start,
            'mean': float(np.mean(w_clean)),
            'std': float(np.std(w_clean)),
            'max': float(np.max(w_clean)),
            'p95': float(np.percentile(w_clean, 95)),
            'sum': float(np.sum(w_clean)),
            'nonzero_frac': float(np.mean(w_clean > 1e-6)),
        })
    return windows


# ── EXP-441: Product Flux with Hepatic ───────────────────────────────

def run_exp441(patients, quick=False):
    """EXP-441: Compare supply×demand (product) vs |insulin|+|carb| (sum).

    Tests whether the product of supply and demand harmonics provides
    better event discrimination than the additive sum.

    The key hypothesis: product captures metabolic THROUGHPUT, which is
    high when the system is working hard (meal + correction simultaneously)
    and low during stable periods — even for UAM/non-bolusing patients
    because hepatic production provides a nonzero baseline.
    """
    results = {'experiment_id': 'EXP-441',
               'title': 'Product flux with hepatic vs sum flux',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {}}

    scales = {'2h': 24, '6h': 72, '12h': 144}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        sd = compute_supply_demand(df, pk)

        pat_result = {
            'supply_stats': {
                'mean': float(np.mean(sd['supply'])),
                'std': float(np.std(sd['supply'])),
                'p95': float(np.percentile(sd['supply'], 95)),
                'nonzero_frac': float(np.mean(sd['supply'] > 0.01)),
            },
            'demand_stats': {
                'mean': float(np.mean(sd['demand'])),
                'std': float(np.std(sd['demand'])),
                'p95': float(np.percentile(sd['demand'], 95)),
                'nonzero_frac': float(np.mean(sd['demand'] > 0.01)),
            },
            'hepatic_stats': {
                'mean': float(np.mean(sd['hepatic'])),
                'std': float(np.std(sd['hepatic'])),
                'min': float(np.min(sd['hepatic'])),
                'max': float(np.max(sd['hepatic'])),
            },
            'product_stats': {
                'mean': float(np.mean(sd['product'])),
                'std': float(np.std(sd['product'])),
                'p95': float(np.percentile(sd['product'], 95)),
                'nonzero_frac': float(np.mean(sd['product'] > 0.01)),
            },
            'scales': {},
        }

        # Per-scale event discrimination comparison
        for scale_name, wsize in scales.items():
            events = classify_windows_by_event(df, wsize)
            if events is None or len(events) < 10:
                pat_result['scales'][scale_name] = {'status': 'insufficient_events'}
                continue

            # Compute windowed statistics for product and sum
            prod_windows = window_stats(sd['product'], wsize)
            sum_windows = window_stats(sd['sum_flux'], wsize)

            n_windows = min(len(prod_windows), len(sum_windows), len(events))
            if n_windows < 10:
                pat_result['scales'][scale_name] = {'status': 'insufficient_windows'}
                continue

            prod_means = np.array([w['mean'] for w in prod_windows[:n_windows]])
            sum_means = np.array([w['mean'] for w in sum_windows[:n_windows]])
            labels = events[:n_windows]

            meal_mask = np.array([l == 'meal' for l in labels])
            stable_mask = np.array([l == 'stable' for l in labels])

            scale_result = {
                'n_windows': int(n_windows),
                'n_meal': int(np.sum(meal_mask)),
                'n_stable': int(np.sum(stable_mask)),
            }

            if np.sum(meal_mask) >= 3 and np.sum(stable_mask) >= 3:
                # Cohen's d for product
                prod_meal = prod_means[meal_mask]
                prod_stable = prod_means[stable_mask]
                pooled_std = np.sqrt((np.var(prod_meal) + np.var(prod_stable)) / 2)
                if pooled_std > 1e-10:
                    d_product = float((np.mean(prod_meal) - np.mean(prod_stable)) / pooled_std)
                else:
                    d_product = 0.0

                # Cohen's d for sum
                sum_meal = sum_means[meal_mask]
                sum_stable = sum_means[stable_mask]
                pooled_std_s = np.sqrt((np.var(sum_meal) + np.var(sum_stable)) / 2)
                if pooled_std_s > 1e-10:
                    d_sum = float((np.mean(sum_meal) - np.mean(sum_stable)) / pooled_std_s)
                else:
                    d_sum = 0.0

                # AUC (binary: meal vs stable)
                from sklearn.metrics import roc_auc_score
                binary_labels = np.concatenate([np.ones(np.sum(meal_mask)),
                                                np.zeros(np.sum(stable_mask))])
                prod_scores = np.concatenate([prod_meal, prod_stable])
                sum_scores = np.concatenate([sum_meal, sum_stable])

                try:
                    auc_product = float(roc_auc_score(binary_labels, prod_scores))
                except:
                    auc_product = 0.5
                try:
                    auc_sum = float(roc_auc_score(binary_labels, sum_scores))
                except:
                    auc_sum = 0.5

                scale_result.update({
                    'cohens_d_product': d_product,
                    'cohens_d_sum': d_sum,
                    'd_advantage': float(d_product - d_sum),
                    'auc_product': auc_product,
                    'auc_sum': auc_sum,
                    'auc_advantage': float(auc_product - auc_sum),
                    'product_wins': d_product > d_sum,
                })

            pat_result['scales'][scale_name] = scale_result

        results['per_patient'][name] = pat_result

    # Aggregate
    agg = {'product_wins_count': 0, 'sum_wins_count': 0, 'total_compared': 0}
    for scale_name in scales:
        d_prod_all, d_sum_all, auc_prod_all, auc_sum_all = [], [], [], []
        for pname, pr in results['per_patient'].items():
            sr = pr['scales'].get(scale_name, {})
            if 'cohens_d_product' in sr:
                d_prod_all.append(sr['cohens_d_product'])
                d_sum_all.append(sr['cohens_d_sum'])
                auc_prod_all.append(sr['auc_product'])
                auc_sum_all.append(sr['auc_sum'])
                if sr.get('product_wins'):
                    agg['product_wins_count'] += 1
                else:
                    agg['sum_wins_count'] += 1
                agg['total_compared'] += 1

        if d_prod_all:
            agg[scale_name] = {
                'mean_d_product': float(np.mean(d_prod_all)),
                'mean_d_sum': float(np.mean(d_sum_all)),
                'mean_auc_product': float(np.mean(auc_prod_all)),
                'mean_auc_sum': float(np.mean(auc_sum_all)),
                'product_better_pct': float(np.mean(np.array(d_prod_all) > np.array(d_sum_all)) * 100),
            }

    results['aggregate'] = agg

    # Check if hepatic rescues zero-flux patients
    hepatic_rescue = {}
    for pname, pr in results['per_patient'].items():
        supply_nonzero = pr['supply_stats']['nonzero_frac']
        demand_nonzero = pr['demand_stats']['nonzero_frac']
        product_nonzero = pr['product_stats']['nonzero_frac']
        hepatic_mean = pr['hepatic_stats']['mean']
        hepatic_rescue[pname] = {
            'supply_nonzero_pct': float(supply_nonzero * 100),
            'demand_nonzero_pct': float(demand_nonzero * 100),
            'product_nonzero_pct': float(product_nonzero * 100),
            'hepatic_mean': hepatic_mean,
            'rescued': supply_nonzero > 0.5 and demand_nonzero > 0.1,
        }
    results['hepatic_rescue'] = hepatic_rescue

    return results


# ── EXP-442: TDD-Normalized Channels ────────────────────────────────

def run_exp442(patients, quick=False):
    """EXP-442: TDD normalization of insulin channels.

    Tests whether expressing insulin as a fraction of Total Daily Dose
    provides better cross-patient normalization than fixed-scalar normalization.

    The 1800 rule (ISF ≈ 1800/TDD) implies TDD normalization ≈ ISF normalization.
    """
    results = {'experiment_id': 'EXP-442',
               'title': 'TDD-normalized insulin channels',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {}}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        # Compute rolling TDD
        tdd = compute_rolling_tdd(df, window_hours=24)

        # TDD-normalized channels
        tdd_channels = compute_tdd_normalized_channels(df, pk, tdd)

        # Profile ISF for comparison
        isf_profile = _extract_isf_scalar(df)

        # ISF from 1800 rule
        median_tdd = float(np.nanmedian(tdd))
        isf_1800_median = 1800.0 / max(median_tdd, 1.0)

        pat_result = {
            'tdd_stats': {
                'median': median_tdd,
                'std': float(np.nanstd(tdd)),
                'min': float(np.nanmin(tdd)) if not np.all(np.isnan(tdd)) else 0,
                'max': float(np.nanmax(tdd)) if not np.all(np.isnan(tdd)) else 0,
                'cv': float(np.nanstd(tdd) / max(median_tdd, 0.01)),
            },
            'isf_comparison': {
                'isf_profile': isf_profile,
                'isf_1800_rule': isf_1800_median,
                'ratio': float(isf_profile / max(isf_1800_median, 1.0)),
                'agreement_pct': float(min(isf_profile, isf_1800_median) /
                                       max(isf_profile, isf_1800_median) * 100),
            },
            'insulin_frac_stats': {
                'mean': float(np.nanmean(tdd_channels['insulin_frac'])),
                'std': float(np.nanstd(tdd_channels['insulin_frac'])),
                'p95': float(np.nanpercentile(tdd_channels['insulin_frac'], 95)),
            },
            'bolus_frac_stats': {
                'mean': float(np.nanmean(tdd_channels['bolus_frac'])),
                'max': float(np.nanmax(tdd_channels['bolus_frac'])),
                'daily_bolus_pct': 0.0,
            },
        }

        # Estimate bolus fraction of TDD
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        total_bolus = float(np.sum(bolus))
        n_days = len(df) / 288.0
        if n_days > 0 and median_tdd > 0:
            daily_bolus = total_bolus / n_days
            pat_result['bolus_frac_stats']['daily_bolus_pct'] = float(
                daily_bolus / median_tdd * 100)

        # Cross-patient equivariance test prep: compute glucose response × ISF
        # If ISF_profile ≈ ISF_1800, normalization is consistent
        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        glucose_norm_profile = (glucose - 110.0) / max(isf_profile, 1.0)
        glucose_norm_tdd = (glucose - 110.0) / max(isf_1800_median, 1.0)

        pat_result['glucose_norm_stats'] = {
            'raw_std': float(np.std(glucose)),
            'profile_norm_std': float(np.std(glucose_norm_profile)),
            'tdd_norm_std': float(np.std(glucose_norm_tdd)),
        }

        results['per_patient'][name] = pat_result

    # Aggregate: cross-patient coefficient of variation
    agg = {}
    raw_stds, prof_stds, tdd_stds = [], [], []
    isf_profiles, isf_1800s, tdds = [], [], []
    bolus_pcts = []

    for pname, pr in results['per_patient'].items():
        raw_stds.append(pr['glucose_norm_stats']['raw_std'])
        prof_stds.append(pr['glucose_norm_stats']['profile_norm_std'])
        tdd_stds.append(pr['glucose_norm_stats']['tdd_norm_std'])
        isf_profiles.append(pr['isf_comparison']['isf_profile'])
        isf_1800s.append(pr['isf_comparison']['isf_1800_rule'])
        tdds.append(pr['tdd_stats']['median'])
        bolus_pcts.append(pr['bolus_frac_stats']['daily_bolus_pct'])

    agg['cross_patient_cv'] = {
        'raw_glucose_cv': float(np.std(raw_stds) / max(np.mean(raw_stds), 1)),
        'profile_norm_cv': float(np.std(prof_stds) / max(np.mean(prof_stds), 0.01)),
        'tdd_norm_cv': float(np.std(tdd_stds) / max(np.mean(tdd_stds), 0.01)),
    }
    agg['isf_agreement'] = {
        'mean_profile': float(np.mean(isf_profiles)),
        'mean_1800_rule': float(np.mean(isf_1800s)),
        'correlation': float(np.corrcoef(isf_profiles, isf_1800s)[0, 1])
            if len(isf_profiles) > 2 else 0.0,
    }
    agg['tdd_population'] = {
        'mean': float(np.mean(tdds)),
        'std': float(np.std(tdds)),
        'range': [float(np.min(tdds)), float(np.max(tdds))],
    }
    agg['bolus_fraction'] = {
        'mean_pct': float(np.mean(bolus_pcts)),
        'std_pct': float(np.std(bolus_pcts)),
        'range_pct': [float(np.min(bolus_pcts)), float(np.max(bolus_pcts))],
    }

    results['aggregate'] = agg
    return results


# ── EXP-443: Throughput + Balance as Dual Channels ───────────────────

def run_exp443(patients, quick=False):
    """EXP-443: Metabolic throughput (product) + balance (ratio) as dual channels.

    Tests whether the combination of throughput (how hard the system works)
    and balance (which direction it's trending) provides better multi-class
    event discrimination than either alone.

    Throughput = supply × demand  (high during active management)
    Balance = supply / demand     (>1 rising, <1 falling, =1 stable)
    """
    results = {'experiment_id': 'EXP-443',
               'title': 'Throughput + balance dual-channel discrimination',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {}}

    scales = {'2h': 24, '6h': 72, '12h': 144}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        sd = compute_supply_demand(df, pk)

        pat_result = {'scales': {}}

        for scale_name, wsize in scales.items():
            events = classify_windows_by_event(df, wsize)
            if events is None or len(events) < 10:
                pat_result['scales'][scale_name] = {'status': 'insufficient_events'}
                continue

            # Windowed throughput and balance
            prod_w = window_stats(sd['product'], wsize)
            ratio_w = window_stats(sd['ratio'], wsize)
            glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
            glu_w = window_stats(glucose, wsize)

            n_w = min(len(prod_w), len(ratio_w), len(glu_w), len(events))
            if n_w < 10:
                pat_result['scales'][scale_name] = {'status': 'insufficient_windows'}
                continue

            prod_means = np.array([w['mean'] for w in prod_w[:n_w]])
            ratio_means = np.array([w['mean'] for w in ratio_w[:n_w]])
            glu_stds = np.array([w['std'] for w in glu_w[:n_w]])
            labels = events[:n_w]

            # Multi-class: meal, correction, stable
            meal_mask = np.array([l == 'meal' for l in labels])
            corr_mask = np.array([l == 'correction' for l in labels])
            stable_mask = np.array([l == 'stable' for l in labels])

            scale_result = {
                'n_windows': int(n_w),
                'n_meal': int(np.sum(meal_mask)),
                'n_correction': int(np.sum(corr_mask)),
                'n_stable': int(np.sum(stable_mask)),
            }

            # Silhouette-like metric: 2D separation using (throughput, balance)
            if np.sum(meal_mask) >= 3 and np.sum(stable_mask) >= 3:
                # 1D AUCs for each channel
                binary = np.concatenate([np.ones(np.sum(meal_mask)),
                                         np.zeros(np.sum(stable_mask))])
                try:
                    from sklearn.metrics import roc_auc_score, silhouette_score
                    auc_prod = float(roc_auc_score(binary,
                        np.concatenate([prod_means[meal_mask], prod_means[stable_mask]])))
                    auc_ratio = float(roc_auc_score(binary,
                        np.concatenate([ratio_means[meal_mask], ratio_means[stable_mask]])))
                    auc_glucose = float(roc_auc_score(binary,
                        np.concatenate([glu_stds[meal_mask], glu_stds[stable_mask]])))
                except:
                    auc_prod = auc_ratio = auc_glucose = 0.5

                scale_result['auc_throughput'] = auc_prod
                scale_result['auc_balance'] = auc_ratio
                scale_result['auc_glucose_std'] = auc_glucose

                # 2D silhouette: throughput × balance space
                try:
                    # Combine meal + stable for 2D test
                    combined_mask = meal_mask | stable_mask
                    features_2d = np.column_stack([
                        prod_means[combined_mask],
                        ratio_means[combined_mask],
                    ])
                    labels_2d = np.array([1 if l == 'meal' else 0
                                          for l, m in zip(labels, combined_mask) if m])

                    # Normalize features to [0, 1] for fair silhouette
                    for col in range(features_2d.shape[1]):
                        r = features_2d[:, col].max() - features_2d[:, col].min()
                        if r > 1e-10:
                            features_2d[:, col] = (features_2d[:, col] -
                                                    features_2d[:, col].min()) / r

                    if len(np.unique(labels_2d)) > 1 and len(labels_2d) >= 4:
                        sil_2d = float(silhouette_score(features_2d, labels_2d))
                    else:
                        sil_2d = 0.0

                    # 1D silhouette with just glucose for comparison
                    glu_1d = glu_stds[combined_mask].reshape(-1, 1)
                    if glu_1d.max() - glu_1d.min() > 1e-10:
                        glu_1d = (glu_1d - glu_1d.min()) / (glu_1d.max() - glu_1d.min())
                    if len(np.unique(labels_2d)) > 1:
                        sil_glucose = float(silhouette_score(glu_1d, labels_2d))
                    else:
                        sil_glucose = 0.0

                    scale_result['silhouette_2d_throughput_balance'] = sil_2d
                    scale_result['silhouette_1d_glucose'] = sil_glucose
                    scale_result['silhouette_advantage'] = float(sil_2d - sil_glucose)
                except Exception as e:
                    scale_result['silhouette_error'] = str(e)

                # 3-class characterization: what does each event type look like?
                if np.sum(corr_mask) >= 2:
                    scale_result['class_profiles'] = {
                        'meal': {
                            'throughput_mean': float(np.mean(prod_means[meal_mask])),
                            'balance_mean': float(np.mean(ratio_means[meal_mask])),
                        },
                        'correction': {
                            'throughput_mean': float(np.mean(prod_means[corr_mask])),
                            'balance_mean': float(np.mean(ratio_means[corr_mask])),
                        },
                        'stable': {
                            'throughput_mean': float(np.mean(prod_means[stable_mask])),
                            'balance_mean': float(np.mean(ratio_means[stable_mask])),
                        },
                    }

            pat_result['scales'][scale_name] = scale_result

        results['per_patient'][name] = pat_result

    # Aggregate per scale
    agg = {}
    for scale_name in scales:
        aucs_prod, aucs_ratio, aucs_glu = [], [], []
        sils_2d, sils_glu = [], []
        for pname, pr in results['per_patient'].items():
            sr = pr['scales'].get(scale_name, {})
            if 'auc_throughput' in sr:
                aucs_prod.append(sr['auc_throughput'])
                aucs_ratio.append(sr['auc_balance'])
                aucs_glu.append(sr['auc_glucose_std'])
            if 'silhouette_2d_throughput_balance' in sr:
                sils_2d.append(sr['silhouette_2d_throughput_balance'])
                sils_glu.append(sr['silhouette_1d_glucose'])

        if aucs_prod:
            agg[scale_name] = {
                'mean_auc_throughput': float(np.mean(aucs_prod)),
                'mean_auc_balance': float(np.mean(aucs_ratio)),
                'mean_auc_glucose': float(np.mean(aucs_glu)),
                'mean_sil_2d': float(np.mean(sils_2d)) if sils_2d else None,
                'mean_sil_glucose': float(np.mean(sils_glu)) if sils_glu else None,
            }
    results['aggregate'] = agg
    return results


# ── EXP-444: Log-Power Spectrum of Metabolic Throughput ──────────────

def run_exp444(patients, quick=False):
    """EXP-444: Power spectrum analysis of metabolic throughput.

    Tests whether throughput has characteristic spectral signatures at
    different frequencies corresponding to:
    - Meal frequency (~3-5h periods → 0.2-0.33 cycles/hour)
    - Circadian (~24h period → 0.042 cycles/hour)
    - Basal rhythm (~12h period → 0.083 cycles/hour)

    Also compares log-power representation vs linear for dynamic range.
    """
    results = {'experiment_id': 'EXP-444',
               'title': 'Log-power spectrum of metabolic throughput',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {}}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        sd = compute_supply_demand(df, pk)

        throughput = sd['product']
        supply = sd['supply']
        demand = sd['demand']
        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)

        N = len(throughput)
        if N < 288:  # Need at least 1 day
            results['per_patient'][name] = {'status': 'insufficient_data'}
            continue

        # FFT of throughput
        # Sampling: 12 samples/hour (5-min intervals)
        fs = 12.0  # samples per hour
        freq = np.fft.rfftfreq(N, d=1.0/fs)  # cycles per hour

        fft_throughput = np.fft.rfft(throughput - np.mean(throughput))
        psd_throughput = np.abs(fft_throughput) ** 2 / N

        fft_glucose = np.fft.rfft(glucose - np.mean(glucose))
        psd_glucose = np.abs(fft_glucose) ** 2 / N

        fft_supply = np.fft.rfft(supply - np.mean(supply))
        psd_supply = np.abs(fft_supply) ** 2 / N

        fft_demand = np.fft.rfft(demand - np.mean(demand))
        psd_demand = np.abs(fft_demand) ** 2 / N

        # Find peaks at physiological frequencies
        # Meal: 3-5h period → 0.2-0.33 cyc/h
        # Circadian: 24h → 0.0417 cyc/h
        # Basal: 12h → 0.0833 cyc/h

        freq_bands = {
            'circadian_24h': (0.035, 0.050),   # ~24h period
            'basal_12h':     (0.070, 0.100),   # ~12h period
            'meal_5h':       (0.17, 0.23),     # ~4-6h period
            'meal_3h':       (0.28, 0.40),     # ~2.5-3.5h period
            'noise_1h':      (0.80, 1.20),     # ~1h period (high freq noise)
        }

        pat_result = {'spectral_power': {}}

        for band_name, (f_lo, f_hi) in freq_bands.items():
            mask = (freq >= f_lo) & (freq < f_hi)
            if np.sum(mask) == 0:
                continue

            pat_result['spectral_power'][band_name] = {
                'throughput_power': float(np.sum(psd_throughput[mask])),
                'glucose_power': float(np.sum(psd_glucose[mask])),
                'supply_power': float(np.sum(psd_supply[mask])),
                'demand_power': float(np.sum(psd_demand[mask])),
                'throughput_vs_glucose_ratio': float(
                    np.sum(psd_throughput[mask]) / max(np.sum(psd_glucose[mask]), 1e-10)),
            }

        # Log-power dynamic range comparison
        log_throughput = np.log1p(throughput)
        log_glucose_var = np.log1p(np.abs(np.diff(glucose, prepend=glucose[0])))

        pat_result['dynamic_range'] = {
            'throughput_linear_range': float(np.percentile(throughput, 99) -
                                              np.percentile(throughput, 1)),
            'throughput_log_range': float(np.percentile(log_throughput, 99) -
                                           np.percentile(log_throughput, 1)),
            'glucose_var_linear_range': float(np.percentile(np.abs(np.diff(glucose)), 99)),
            'glucose_var_log_range': float(np.percentile(log_glucose_var, 99) -
                                            np.percentile(log_glucose_var, 1)),
            'log_compression_ratio': float(
                (np.percentile(throughput, 99) - np.percentile(throughput, 1)) /
                max(np.percentile(log_throughput, 99) - np.percentile(log_throughput, 1), 0.01)),
        }

        # Cross-spectrum: supply × demand coherence
        # High coherence at meal freq = coordinated response
        min_len = min(len(psd_supply), len(psd_demand))
        cross_spectrum = np.sqrt(psd_supply[:min_len] * psd_demand[:min_len])
        auto_spectrum = np.sqrt(psd_supply[:min_len] ** 2 + psd_demand[:min_len] ** 2) / 2

        coherence = np.zeros(min_len)
        for i in range(min_len):
            if auto_spectrum[i] > 1e-20:
                coherence[i] = cross_spectrum[i] / auto_spectrum[i]

        pat_result['supply_demand_coherence'] = {}
        for band_name, (f_lo, f_hi) in freq_bands.items():
            mask = (freq[:min_len] >= f_lo) & (freq[:min_len] < f_hi)
            if np.sum(mask) > 0:
                pat_result['supply_demand_coherence'][band_name] = float(
                    np.mean(coherence[mask]))

        results['per_patient'][name] = pat_result

    # Aggregate spectral signatures
    agg = {'mean_spectral_power': {}, 'mean_coherence': {}}
    for band_name in freq_bands:
        throughput_powers, glucose_powers, coherences = [], [], []
        for pname, pr in results['per_patient'].items():
            if 'spectral_power' not in pr:
                continue
            sp = pr['spectral_power'].get(band_name, {})
            if 'throughput_power' in sp:
                throughput_powers.append(sp['throughput_power'])
                glucose_powers.append(sp['glucose_power'])
            coh = pr.get('supply_demand_coherence', {}).get(band_name)
            if coh is not None:
                coherences.append(coh)

        if throughput_powers:
            agg['mean_spectral_power'][band_name] = {
                'throughput': float(np.mean(throughput_powers)),
                'glucose': float(np.mean(glucose_powers)),
                'ratio': float(np.mean(throughput_powers) / max(np.mean(glucose_powers), 1e-10)),
            }
        if coherences:
            agg['mean_coherence'][band_name] = float(np.mean(coherences))

    results['aggregate'] = agg
    return results


# ── EXP-445: Cross-Patient Equivariance with TDD Normalization ───────

def run_exp445(patients, quick=False):
    """EXP-445: Cross-patient equivariance test with TDD normalization.

    Extends EXP-422 (ISF equivariance) by testing whether TDD normalization
    produces more consistent cross-patient representations than profile ISF
    or raw encoding.

    For each patient pair, compare cosine similarity of:
    1. Raw glucose responses to similar events
    2. Profile-ISF-normalized responses
    3. TDD-normalized responses

    If TDD normalization works, cross-patient similarity should increase.
    """
    results = {'experiment_id': 'EXP-445',
               'title': 'Cross-patient equivariance with TDD normalization',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {},
               'patient_pairs': []}

    # First pass: compute per-patient event signatures
    patient_sigs = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        tdd = compute_rolling_tdd(df, window_hours=24)
        median_tdd = float(np.nanmedian(tdd))

        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        sd = compute_supply_demand(df, pk)

        # Find meal events and extract response windows
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        meal_indices = np.where(carbs > 10)[0]

        # Extract 2h (24-step) windows after each meal
        responses_raw = []
        responses_isf = []
        responses_tdd = []
        throughputs = []

        for idx in meal_indices:
            end = idx + 24
            if end > len(glucose):
                continue
            # Skip if another meal within window
            if np.any(carbs[idx+1:end] > 5):
                continue

            raw = glucose[idx:end] - glucose[idx]  # Delta from baseline
            responses_raw.append(raw)
            responses_isf.append(raw / max(isf, 1.0))

            local_tdd = tdd[idx] if not np.isnan(tdd[idx]) else median_tdd
            isf_tdd = 1800.0 / max(local_tdd, 1.0)
            responses_tdd.append(raw / max(isf_tdd, 1.0))

            throughputs.append(sd['product'][idx:end])

        if len(responses_raw) < 3:
            results['per_patient'][name] = {'status': 'insufficient_isolated_meals',
                                             'n_meals': len(responses_raw)}
            continue

        # Average meal signature for this patient
        n_resp = len(responses_raw)
        avg_raw = np.mean(responses_raw, axis=0)
        avg_isf = np.mean(responses_isf, axis=0)
        avg_tdd = np.mean(responses_tdd, axis=0)
        avg_throughput = np.mean(throughputs, axis=0) if throughputs else np.zeros(24)

        patient_sigs[name] = {
            'avg_raw': avg_raw,
            'avg_isf': avg_isf,
            'avg_tdd': avg_tdd,
            'avg_throughput': avg_throughput,
            'isf': isf,
            'tdd': median_tdd,
            'n_meals': n_resp,
        }

        results['per_patient'][name] = {
            'n_meals': n_resp,
            'isf': isf,
            'tdd': median_tdd,
            'peak_raw': float(np.max(avg_raw)),
            'peak_isf_norm': float(np.max(avg_isf)),
            'peak_tdd_norm': float(np.max(avg_tdd)),
            'internal_consistency': {
                'raw_std': float(np.std([np.max(r) for r in responses_raw])),
                'isf_std': float(np.std([np.max(r) for r in responses_isf])),
                'tdd_std': float(np.std([np.max(r) for r in responses_tdd])),
            },
        }

    # Second pass: cross-patient similarity
    sig_names = sorted(patient_sigs.keys())
    raw_sims, isf_sims, tdd_sims, throughput_sims = [], [], [], []

    for i in range(len(sig_names)):
        for j in range(i + 1, len(sig_names)):
            p1, p2 = sig_names[i], sig_names[j]
            s1, s2 = patient_sigs[p1], patient_sigs[p2]

            def cosine_sim(a, b):
                norm = np.linalg.norm(a) * np.linalg.norm(b)
                if norm < 1e-10:
                    return 0.0
                return float(np.dot(a, b) / norm)

            raw_sim = cosine_sim(s1['avg_raw'], s2['avg_raw'])
            isf_sim = cosine_sim(s1['avg_isf'], s2['avg_isf'])
            tdd_sim = cosine_sim(s1['avg_tdd'], s2['avg_tdd'])
            thr_sim = cosine_sim(s1['avg_throughput'], s2['avg_throughput'])

            pair = {
                'patient_1': p1,
                'patient_2': p2,
                'isf_1': s1['isf'],
                'isf_2': s2['isf'],
                'tdd_1': s1['tdd'],
                'tdd_2': s2['tdd'],
                'raw_similarity': raw_sim,
                'isf_norm_similarity': isf_sim,
                'tdd_norm_similarity': tdd_sim,
                'throughput_similarity': thr_sim,
                'isf_norm_delta': float(isf_sim - raw_sim),
                'tdd_norm_delta': float(tdd_sim - raw_sim),
            }
            results['patient_pairs'].append(pair)
            raw_sims.append(raw_sim)
            isf_sims.append(isf_sim)
            tdd_sims.append(tdd_sim)
            throughput_sims.append(thr_sim)

    # Aggregate
    if raw_sims:
        results['aggregate'] = {
            'n_pairs': len(raw_sims),
            'mean_raw_similarity': float(np.mean(raw_sims)),
            'mean_isf_similarity': float(np.mean(isf_sims)),
            'mean_tdd_similarity': float(np.mean(tdd_sims)),
            'mean_throughput_similarity': float(np.mean(throughput_sims)),
            'isf_norm_improvement': float(np.mean(isf_sims) - np.mean(raw_sims)),
            'tdd_norm_improvement': float(np.mean(tdd_sims) - np.mean(raw_sims)),
            'throughput_similarity_mean': float(np.mean(throughput_sims)),
            'tdd_wins_over_isf': int(sum(1 for ts, is_ in zip(tdd_sims, isf_sims)
                                          if ts > is_)),
            'tdd_wins_over_raw': int(sum(1 for ts, rs in zip(tdd_sims, raw_sims)
                                          if ts > rs)),
            'total_pairs': len(raw_sims),
        }

        # Statistical test: paired t-test TDD vs raw
        if len(raw_sims) >= 3:
            t_stat, p_val = stats.ttest_rel(tdd_sims, raw_sims)
            results['aggregate']['tdd_vs_raw_ttest'] = {
                't_statistic': float(t_stat),
                'p_value': float(p_val),
                'significant': p_val < 0.05,
            }
    else:
        results['aggregate'] = {'status': 'insufficient_patients_with_meals'}

    return results


# ── EXP-446: Meal Counting Sanity Check ──────────────────────────────

def run_exp446(patients, quick=False):
    """EXP-446: Can we count meals per day from metabolic flux peaks?

    Common-sense validation: if the throughput signal is physiologically
    meaningful, peak detection should yield ~2-5 meal-like events per day.

    For each patient-day, we:
    1. Detect throughput peaks (scipy.signal.find_peaks with min prominence)
    2. Count peaks per calendar day
    3. Cross-validate against announced meals (carbs > 5g in treatments)
    4. Flag unannounced peaks (flux peak with no nearby carb entry) = UAM candidates

    This also characterizes each patient's "metabolic style":
    - Regular eaters (~3 meals/day, low variance)
    - Grazers (5+ smaller events/day)
    - Irregular (high day-to-day variance)
    """
    from scipy.signal import find_peaks

    results = {'experiment_id': 'EXP-446',
               'title': 'Meal counting from metabolic throughput peaks',
               'timestamp': datetime.utcnow().isoformat() + 'Z',
               'per_patient': {}}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']

        sd = compute_supply_demand(df, pk)
        throughput = sd['product']
        supply = sd['supply']

        N = len(df)
        n_days = N / 288.0
        if n_days < 1:
            results['per_patient'][name] = {'status': 'insufficient_data'}
            continue

        # Ground truth: announced meals from carbs column
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        announced_meal_idx = np.where(carbs > 5.0)[0]

        # Peak detection on throughput
        # Minimum distance between peaks: 1.5 hours (18 steps)
        # Try multiple prominence thresholds to find the "right" sensitivity
        throughput_smooth = np.convolve(throughput, np.ones(6) / 6, mode='same')

        # Adaptive threshold: use patient's own statistics
        # Key: product has a nonzero baseline (hepatic × basal), so use
        # relative prominence above the running median, not absolute height
        p25 = np.percentile(throughput_smooth, 25)
        p50 = np.percentile(throughput_smooth, 50)
        p75 = np.percentile(throughput_smooth, 75)
        p90 = np.percentile(throughput_smooth, 90)
        iqr = p75 - p25

        thresholds = {
            'very_sensitive': {'height': p25, 'prominence': max(iqr * 0.5, 0.1), 'distance': 12},
            'sensitive':      {'height': p50, 'prominence': max(iqr * 0.75, 0.1), 'distance': 18},
            'moderate':       {'height': p50, 'prominence': max(iqr * 1.0, 0.1), 'distance': 24},
            'strict':         {'height': p75, 'prominence': max(iqr * 1.5, 0.1), 'distance': 36},
        }

        # Also detect on supply alone (hepatic + carbs, no demand required)
        supply_smooth = np.convolve(supply, np.ones(6) / 6, mode='same')
        supply_p50 = np.percentile(supply_smooth, 50)
        supply_p75 = np.percentile(supply_smooth, 75)
        supply_p90 = np.percentile(supply_smooth, 90)
        supply_iqr = supply_p75 - np.percentile(supply_smooth, 25)

        pat_result = {
            'n_days': float(n_days),
            'announced_meals_total': int(len(announced_meal_idx)),
            'announced_meals_per_day': float(len(announced_meal_idx) / n_days),
            'thresholds': {},
        }

        for thresh_name, params in thresholds.items():
            peaks, properties = find_peaks(
                throughput_smooth,
                height=params['height'],
                prominence=params['prominence'],
                distance=params['distance'],
            )

            peaks_per_day = float(len(peaks) / n_days)

            # Cross-validate: how many flux peaks are near an announced meal?
            # "Near" = within ±1 hour (12 steps) — product peak lags carb entry
            matched = 0
            unmatched_peaks = []
            for pk_idx in peaks:
                near_carb = np.any(np.abs(announced_meal_idx - pk_idx) <= 12)
                if near_carb:
                    matched += 1
                else:
                    unmatched_peaks.append(int(pk_idx))

            # How many announced meals have a nearby flux peak?
            meals_with_peak = 0
            for meal_idx in announced_meal_idx:
                if len(peaks) > 0 and np.min(np.abs(peaks - meal_idx)) <= 12:
                    meals_with_peak += 1

            n_peaks = len(peaks)
            precision = matched / max(n_peaks, 1)  # of detected peaks, how many are real meals
            recall = meals_with_peak / max(len(announced_meal_idx), 1)  # of real meals, how many detected

            pat_result['thresholds'][thresh_name] = {
                'n_peaks': n_peaks,
                'peaks_per_day': peaks_per_day,
                'matched_to_announced': matched,
                'unmatched_peaks': len(unmatched_peaks),
                'unmatched_per_day': float(len(unmatched_peaks) / n_days),
                'announced_with_peak': meals_with_peak,
                'precision': float(precision),
                'recall': float(recall),
                'f1': float(2 * precision * recall / max(precision + recall, 1e-10)),
            }

        # Supply-based peak detection (carb absorption directly)
        supply_thresholds = {
            'supply_sensitive': {'height': supply_p50, 'prominence': max(supply_iqr * 0.75, 0.01), 'distance': 18},
            'supply_moderate':  {'height': supply_p75, 'prominence': max(supply_iqr * 1.0, 0.01), 'distance': 24},
        }

        for thresh_name, params in supply_thresholds.items():
            try:
                peaks_s, _ = find_peaks(supply_smooth, **params)
            except Exception:
                peaks_s = np.array([])
            peaks_s_per_day = float(len(peaks_s) / n_days)
            matched_s = 0
            for pk_idx in peaks_s:
                if len(announced_meal_idx) > 0 and np.any(np.abs(announced_meal_idx - pk_idx) <= 12):
                    matched_s += 1
            meals_with_s = 0
            for meal_idx in announced_meal_idx:
                if len(peaks_s) > 0 and np.min(np.abs(peaks_s - meal_idx)) <= 12:
                    meals_with_s += 1
            n_s = len(peaks_s)
            prec_s = matched_s / max(n_s, 1)
            rec_s = meals_with_s / max(len(announced_meal_idx), 1)
            pat_result['thresholds'][thresh_name] = {
                'n_peaks': int(n_s),
                'peaks_per_day': peaks_s_per_day,
                'matched_to_announced': matched_s,
                'unmatched_peaks': int(n_s - matched_s),
                'unmatched_per_day': float((n_s - matched_s) / n_days),
                'announced_with_peak': meals_with_s,
                'precision': float(prec_s),
                'recall': float(rec_s),
                'f1': float(2 * prec_s * rec_s / max(prec_s + rec_s, 1e-10)),
            }

        # Per-day breakdown (moderate threshold)
        mod_peaks, _ = find_peaks(
            throughput_smooth,
            height=thresholds['moderate']['height'],
            prominence=thresholds['moderate']['prominence'],
            distance=thresholds['moderate']['distance'],
        )

        # Assign peaks and meals to calendar days
        if hasattr(df.index, 'date'):
            dates = df.index.date
            unique_dates = sorted(set(dates))

            daily_stats = []
            for d in unique_dates:
                day_mask = np.array([dt == d for dt in dates])
                day_indices = np.where(day_mask)[0]
                if len(day_indices) < 144:  # skip partial days (< 12h)
                    continue

                lo, hi = day_indices[0], day_indices[-1]
                day_peaks = [p for p in mod_peaks if lo <= p <= hi]
                day_meals = [m for m in announced_meal_idx if lo <= m <= hi]

                daily_stats.append({
                    'date': str(d),
                    'flux_peaks': len(day_peaks),
                    'announced_meals': len(day_meals),
                    'uam_candidates': max(0, len(day_peaks) - len(day_meals)),
                })

            if daily_stats:
                flux_per_day = [d['flux_peaks'] for d in daily_stats]
                meals_per_day = [d['announced_meals'] for d in daily_stats]
                uam_per_day = [d['uam_candidates'] for d in daily_stats]

                pat_result['daily_analysis'] = {
                    'n_complete_days': len(daily_stats),
                    'flux_peaks_per_day': {
                        'mean': float(np.mean(flux_per_day)),
                        'std': float(np.std(flux_per_day)),
                        'min': int(np.min(flux_per_day)),
                        'max': int(np.max(flux_per_day)),
                        'median': float(np.median(flux_per_day)),
                    },
                    'announced_meals_per_day': {
                        'mean': float(np.mean(meals_per_day)),
                        'std': float(np.std(meals_per_day)),
                        'median': float(np.median(meals_per_day)),
                    },
                    'uam_candidates_per_day': {
                        'mean': float(np.mean(uam_per_day)),
                        'std': float(np.std(uam_per_day)),
                    },
                    'correlation_flux_vs_meals': float(
                        np.corrcoef(flux_per_day, meals_per_day)[0, 1])
                        if len(set(flux_per_day)) > 1 and len(set(meals_per_day)) > 1
                        else 0.0,
                }

                # Classify eating style
                mean_fpd = np.mean(flux_per_day)
                std_fpd = np.std(flux_per_day)
                cv = std_fpd / max(mean_fpd, 0.1)

                if mean_fpd < 2:
                    style = 'minimal_detection'
                elif mean_fpd <= 4 and cv < 0.5:
                    style = 'regular_eater'
                elif mean_fpd > 5:
                    style = 'grazer'
                elif cv > 0.7:
                    style = 'irregular'
                else:
                    style = 'moderate'

                pat_result['eating_style'] = style

        results['per_patient'][name] = pat_result

    # Aggregate
    agg = {
        'population_announced_meals_per_day': [],
        'population_flux_peaks_per_day': {},
        'eating_styles': {},
    }

    announced_rates, flux_rates = [], []
    precisions, recalls, f1s = [], [], []
    styles_count = {}

    for pname, pr in results['per_patient'].items():
        if 'status' in pr:
            continue
        announced_rates.append(pr['announced_meals_per_day'])

        mod = pr['thresholds'].get('moderate', {})
        if 'peaks_per_day' in mod:
            flux_rates.append(mod['peaks_per_day'])
            precisions.append(mod['precision'])
            recalls.append(mod['recall'])
            f1s.append(mod['f1'])

        style = pr.get('eating_style', 'unknown')
        styles_count[style] = styles_count.get(style, 0) + 1

    if announced_rates:
        agg['population_announced_meals_per_day'] = {
            'mean': float(np.mean(announced_rates)),
            'std': float(np.std(announced_rates)),
            'range': [float(np.min(announced_rates)), float(np.max(announced_rates))],
        }
    if flux_rates:
        agg['population_flux_peaks_per_day'] = {
            'mean': float(np.mean(flux_rates)),
            'std': float(np.std(flux_rates)),
            'range': [float(np.min(flux_rates)), float(np.max(flux_rates))],
        }
        agg['moderate_threshold_performance'] = {
            'mean_precision': float(np.mean(precisions)),
            'mean_recall': float(np.mean(recalls)),
            'mean_f1': float(np.mean(f1s)),
        }
    agg['eating_styles'] = styles_count

    # Sanity verdict
    mean_flux = np.mean(flux_rates) if flux_rates else 0
    if 2.0 <= mean_flux <= 6.0:
        agg['sanity_verdict'] = 'PASS: plausible meal count range'
    elif mean_flux < 2.0:
        agg['sanity_verdict'] = 'WARN: too few peaks detected (threshold too strict or weak signal)'
    else:
        agg['sanity_verdict'] = 'WARN: too many peaks (threshold too sensitive or grazing pattern)'

    results['aggregate'] = agg
    return results


# ── Experiment Registry ──────────────────────────────────────────────

EXPERIMENTS = {
    '441': run_exp441,
    '442': run_exp442,
    '443': run_exp443,
    '444': run_exp444,
    '445': run_exp445,
    '446': run_exp446,
}


# ── Scorecard ────────────────────────────────────────────────────────

def product_scorecard(all_results):
    """Print summary scorecard for EXP-441 through EXP-445."""
    print("\n" + "=" * 72)
    print("  PRODUCT FLUX & TDD NORMALIZATION SCORECARD (EXP-441–446)")
    print("=" * 72)

    for exp_id, res in sorted(all_results.items()):
        print(f"\n{'─' * 60}")
        title = res.get('title', exp_id)
        print(f"  EXP-{exp_id}: {title}")
        print(f"{'─' * 60}")

        agg = res.get('aggregate', {})

        if exp_id == '441':
            rescue = res.get('hepatic_rescue', {})
            rescued = sum(1 for v in rescue.values() if v.get('rescued'))
            total = len(rescue)
            print(f"  Hepatic rescue: {rescued}/{total} patients have nonzero supply")
            for scale in ['2h', '6h', '12h']:
                sa = agg.get(scale, {})
                if 'mean_d_product' in sa:
                    print(f"  {scale}: product d={sa['mean_d_product']:.2f} "
                          f"vs sum d={sa['mean_d_sum']:.2f} "
                          f"| product better {sa['product_better_pct']:.0f}% of patients")
            pw = agg.get('product_wins_count', 0)
            sw = agg.get('sum_wins_count', 0)
            print(f"  Overall: product wins {pw}, sum wins {sw}")

        elif exp_id == '442':
            cp = agg.get('cross_patient_cv', {})
            print(f"  Cross-patient CV: raw={cp.get('raw_glucose_cv', 0):.3f} "
                  f"profile={cp.get('profile_norm_cv', 0):.3f} "
                  f"tdd={cp.get('tdd_norm_cv', 0):.3f}")
            ia = agg.get('isf_agreement', {})
            print(f"  ISF agreement: profile mean={ia.get('mean_profile', 0):.1f} "
                  f"1800-rule mean={ia.get('mean_1800_rule', 0):.1f} "
                  f"r={ia.get('correlation', 0):.3f}")
            tp = agg.get('tdd_population', {})
            print(f"  TDD population: mean={tp.get('mean', 0):.1f} U/day "
                  f"std={tp.get('std', 0):.1f} "
                  f"range=[{tp.get('range', [0, 0])[0]:.1f}, {tp.get('range', [0, 0])[1]:.1f}]")
            bf = agg.get('bolus_fraction', {})
            print(f"  Bolus fraction: mean={bf.get('mean_pct', 0):.1f}% "
                  f"range=[{bf.get('range_pct', [0, 0])[0]:.1f}%, {bf.get('range_pct', [0, 0])[1]:.1f}%]")

        elif exp_id == '443':
            for scale in ['2h', '6h', '12h']:
                sa = agg.get(scale, {})
                if sa:
                    print(f"  {scale}: AUC throughput={sa.get('mean_auc_throughput', 0):.3f} "
                          f"balance={sa.get('mean_auc_balance', 0):.3f} "
                          f"glucose={sa.get('mean_auc_glucose', 0):.3f}")
                    if sa.get('mean_sil_2d') is not None:
                        print(f"       sil 2D={sa['mean_sil_2d']:.3f} "
                              f"vs glucose 1D={sa.get('mean_sil_glucose', 0):.3f} "
                              f"Δ={sa['mean_sil_2d'] - sa.get('mean_sil_glucose', 0):.3f}")

        elif exp_id == '444':
            sp = agg.get('mean_spectral_power', {})
            coh = agg.get('mean_coherence', {})
            for band in ['circadian_24h', 'basal_12h', 'meal_5h', 'meal_3h']:
                bp = sp.get(band, {})
                c = coh.get(band, 0)
                if bp:
                    print(f"  {band}: throughput/glucose ratio={bp.get('ratio', 0):.2f} "
                          f"| coherence={c:.3f}")

        elif exp_id == '445':
            if 'mean_raw_similarity' in agg:
                print(f"  Cross-patient similarity ({agg.get('n_pairs', 0)} pairs):")
                print(f"    Raw:         {agg['mean_raw_similarity']:.4f}")
                print(f"    ISF-normed:  {agg['mean_isf_similarity']:.4f} "
                      f"(Δ={agg['isf_norm_improvement']:+.4f})")
                print(f"    TDD-normed:  {agg['mean_tdd_similarity']:.4f} "
                      f"(Δ={agg['tdd_norm_improvement']:+.4f})")
                print(f"    Throughput:  {agg['mean_throughput_similarity']:.4f}")
                t = agg.get('tdd_vs_raw_ttest', {})
                if t:
                    sig = "✓" if t.get('significant') else "✗"
                    print(f"  TDD vs raw t-test: p={t['p_value']:.4f} {sig}")
                print(f"  TDD wins over ISF: {agg.get('tdd_wins_over_isf', 0)}/{agg['total_pairs']}")
                print(f"  TDD wins over raw: {agg.get('tdd_wins_over_raw', 0)}/{agg['total_pairs']}")

        elif exp_id == '446':
            pa = agg.get('population_announced_meals_per_day', {})
            pf = agg.get('population_flux_peaks_per_day', {})
            print(f"  Announced meals/day: {pa.get('mean', 0):.1f} ± {pa.get('std', 0):.1f}")
            print(f"  Flux peaks/day:      {pf.get('mean', 0):.1f} ± {pf.get('std', 0):.1f}")
            mt = agg.get('moderate_threshold_performance', {})
            if mt:
                print(f"  Moderate threshold:  P={mt['mean_precision']:.2f} "
                      f"R={mt['mean_recall']:.2f} F1={mt['mean_f1']:.2f}")
            styles = agg.get('eating_styles', {})
            if styles:
                style_str = ', '.join(f"{k}: {v}" for k, v in sorted(styles.items()))
                print(f"  Eating styles:       {style_str}")
            verdict = agg.get('sanity_verdict', '')
            if verdict:
                print(f"  Verdict: {verdict}")

    print("\n" + "=" * 72)


# ── Results I/O ──────────────────────────────────────────────────────

def save_results(exp_id, results):
    """Save experiment results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"exp{exp_id}_{'product_flux hepatic tdd_normalization throughput_balance spectral_throughput tdd_equivariance'.split()[int(exp_id) - 441]}.json"
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved: {path}")
    return path


def save_results_named(exp_id, results):
    """Save with descriptive filename."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    names = {
        '441': 'product_flux_hepatic',
        '442': 'tdd_normalization',
        '443': 'throughput_balance',
        '444': 'spectral_throughput',
        '445': 'tdd_equivariance',
        '446': 'meal_counting',
    }
    fname = f"exp{exp_id}_{names.get(exp_id, 'unknown')}.json"
    path = RESULTS_DIR / fname
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved: {path}")
    return path


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-441–446: Product Flux, TDD Normalization, Metabolic Throughput')
    parser.add_argument('--experiment', '-e', type=str, default=None,
                        help='Run specific experiment (441-446). Default: all')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick mode: first 4 patients only')
    parser.add_argument('--patient', '-p', type=str, default=None,
                        help='Run for specific patient only')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Print scorecard from existing results (no recomputation)')
    args = parser.parse_args()

    if args.summary:
        all_results = {}
        for eid in EXPERIMENTS:
            names = {
                '441': 'product_flux_hepatic',
                '442': 'tdd_normalization',
                '443': 'throughput_balance',
                '444': 'spectral_throughput',
                '445': 'tdd_equivariance',
                '446': 'meal_counting',
            }
            fname = f"exp{eid}_{names[eid]}.json"
            path = RESULTS_DIR / fname
            if path.exists():
                with open(path) as f:
                    all_results[eid] = json.load(f)
        if all_results:
            product_scorecard(all_results)
        else:
            print("No results found. Run experiments first.")
        return

    # Load patients
    print(f"Loading patients from {PATIENTS_DIR}...")
    max_p = 4 if args.quick else None
    patients = load_patients(str(PATIENTS_DIR), max_patients=max_p,
                             patient_filter=args.patient, verbose=True)
    print(f"Loaded {len(patients)} patients")

    if len(patients) == 0:
        print("ERROR: No patients loaded")
        sys.exit(1)

    # Run experiments
    exp_ids = [args.experiment] if args.experiment else sorted(EXPERIMENTS.keys())

    all_results = {}
    import time
    t0 = time.time()

    for eid in exp_ids:
        if eid not in EXPERIMENTS:
            print(f"Unknown experiment: {eid}")
            continue

        print(f"\n{'━' * 50}")
        print(f"  Running EXP-{eid}...")
        print(f"{'━' * 50}")

        t1 = time.time()
        try:
            result = EXPERIMENTS[eid](patients, quick=args.quick)
            elapsed = time.time() - t1
            print(f"  Completed in {elapsed:.1f}s")
            save_results_named(eid, result)
            all_results[eid] = result
        except Exception as e:
            import traceback
            print(f"  ERROR in EXP-{eid}: {e}")
            traceback.print_exc()

    elapsed_total = time.time() - t0
    print(f"\n{'━' * 50}")
    print(f"  Total time: {elapsed_total:.1f}s")

    if all_results:
        product_scorecard(all_results)


if __name__ == '__main__':
    main()
