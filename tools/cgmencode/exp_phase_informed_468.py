#!/usr/bin/env python3
"""EXP-468–475: Phase-Informed Experiments.

Building on EXP-464–467 phase analysis findings, these experiments address:
- EXP-468: Hybrid hepatic model (physiology + basal schedule as EGP proxy)
- EXP-469: Flat schedule penalty (rich vs flat schedule quality)
- EXP-470: Circadian ISF inference from observed glucose dynamics
- EXP-471: Phase lag as UAM feature (announced vs unannounced meal classification)
- EXP-472: Product vs sum of harmonics for forecasting
- EXP-473: TDD-relative PK channels for cross-patient transfer
- EXP-474: Basal-relative (AC/DC) insulin decomposition
- EXP-475: Conservation score as training data quality gate

Key insight from EXP-467: hepatic model covers only 48% of basal demand and
peaks at the wrong time. The patient's basal schedule IS the clinical proxy
for expected glucose production.

References:
  - exp_phase_464.py: EXP-464–467 phase relationship experiments
  - exp_metabolic_441.py: compute_supply_demand() (time-varying CR fixed)
  - continuous_pk.py: expand_schedule(), compute_hepatic_production()
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.continuous_pk import (
    expand_schedule,
    compute_hepatic_production,
    PK_NORMALIZATION,
    PK_CHANNEL_NAMES,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-468: Hybrid Hepatic Model ────────────────────────────────────────

def compute_hybrid_hepatic(df, pk_array, alpha=0.4, beta=0.6, weight_kg=70.0):
    """Hybrid hepatic = α×physio_model + β×basal_schedule×ISF.

    The patient's basal rate is the clinician's best estimate of the insulin
    needed to counteract endogenous glucose production at each hour. Thus:
        EGP_clinical(t) ≈ basal_rate(t) × ISF(t) × (5/60)
    gives the mg/dL equivalent of hepatic production implied by the profile.

    The physio model (Hill + circadian) captures insulin-modulated suppression.
    The hybrid combines both signals.
    """
    N = len(df)

    # Physiological model
    iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
    if hasattr(df.index, 'hour'):
        hours = df.index.hour + df.index.minute / 60.0
    else:
        hours = np.zeros(N)
    physio = compute_hepatic_production(iob, hours, weight_kg=weight_kg)

    # Clinical model from basal schedule
    basal_sched = df.attrs.get('basal_schedule', [])
    isf_sched = df.attrs.get('isf_schedule', [])
    basal_curve = expand_schedule(df.index, basal_sched, default=0.5)[:N]
    isf_curve = expand_schedule(df.index, isf_sched, default=40.0)[:N]
    if np.median(isf_curve) < 15:
        isf_curve = isf_curve * 18.0182
    clinical_egp = basal_curve * (5.0 / 60.0) * isf_curve  # mg/dL per 5min

    hybrid = alpha * physio + beta * clinical_egp
    return {
        'hybrid': hybrid,
        'physio': physio,
        'clinical': clinical_egp,
        'alpha': alpha,
        'beta': beta,
    }


def run_exp468(patients, detail=False):
    """Test hybrid hepatic model vs physio-only.

    Success metric: does the hybrid model reduce the conservation residual
    (difference between predicted and actual glucose change)?
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        N = len(df)

        # Original supply-demand with physio hepatic
        sd_orig = compute_supply_demand(df, pk)

        # Hybrid hepatic
        hep = compute_hybrid_hepatic(df, pk)

        # Recompute supply with hybrid hepatic
        supply_hybrid = hep['hybrid'] + (sd_orig['supply'] - sd_orig['hepatic'])

        # Conservation: ΔBG ≈ supply - demand
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        dbg_actual = np.diff(bg)

        # Predicted ΔBG with original hepatic
        net_orig = sd_orig['supply'][1:] - sd_orig['demand'][1:]
        residual_orig = dbg_actual - net_orig

        # Predicted ΔBG with hybrid hepatic
        net_hybrid = supply_hybrid[1:] - sd_orig['demand'][1:]
        residual_hybrid = dbg_actual - net_hybrid

        # Filter NaN
        valid = ~(np.isnan(residual_orig) | np.isnan(residual_hybrid))
        r_orig = residual_orig[valid]
        r_hybrid = residual_hybrid[valid]

        results[p['name']] = {
            'residual_orig_mean': round(float(np.mean(np.abs(r_orig))), 2),
            'residual_hybrid_mean': round(float(np.mean(np.abs(r_hybrid))), 2),
            'improvement_pct': round(100 * (1 - np.mean(np.abs(r_hybrid)) / max(np.mean(np.abs(r_orig)), 0.01)), 1),
            'residual_orig_std': round(float(np.std(r_orig)), 2),
            'residual_hybrid_std': round(float(np.std(r_hybrid)), 2),
            'hepatic_physio_mean': round(float(np.mean(hep['physio'])), 3),
            'hepatic_clinical_mean': round(float(np.mean(hep['clinical'])), 3),
            'hepatic_hybrid_mean': round(float(np.mean(hep['hybrid'])), 3),
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']}: |resid| orig={r['residual_orig_mean']:.2f} → "
                  f"hybrid={r['residual_hybrid_mean']:.2f} "
                  f"({r['improvement_pct']:+.1f}%)")
            print(f"  Hepatic: physio={r['hepatic_physio_mean']:.3f}, "
                  f"clinical={r['hepatic_clinical_mean']:.3f}, "
                  f"hybrid={r['hepatic_hybrid_mean']:.3f}")

    return results


# ── EXP-471: Phase Lag as UAM Feature ─────────────────────────────────────

def run_exp471(patients, detail=False):
    """Classify meals as announced vs UAM based on supply→demand phase lag.

    Hypothesis: Pre-bolused meals have supply→demand lag < 20 min.
    UAM meals (AID-only response) have lag > 40 min.

    We use known carb events as ground truth and measure the lag at each.
    """
    from scipy.signal import find_peaks

    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)
        N = len(df)

        if not hasattr(df.index, 'hour'):
            continue

        # Get announced meals
        carbs = df.get('carbs', pd.Series(np.zeros(N), index=df.index))
        carbs_arr = np.nan_to_num(carbs.values.astype(np.float64), nan=0.0)

        # Supply and demand smoothed
        supply_sm = pd.Series(sd['carb_supply']).rolling(6, center=True, min_periods=1).mean().values
        demand_sm = pd.Series(sd['demand']).rolling(6, center=True, min_periods=1).mean().values

        # For each announced meal, find supply peak and nearest demand peak
        meal_indices = np.where(carbs_arr > 5)[0]  # meals > 5g
        if len(meal_indices) < 3:
            results[p['name']] = {'n_meals': len(meal_indices), 'insufficient_data': True}
            continue

        # Deduplicate: keep first in each 2-hour window
        deduped = [meal_indices[0]]
        for idx in meal_indices[1:]:
            if idx - deduped[-1] > 24:  # 2 hours
                deduped.append(idx)
        meal_indices = np.array(deduped)

        lags = []
        announced_lags = []
        bolus_col = df.get('bolus', pd.Series(np.zeros(N), index=df.index))
        bolus_arr = np.nan_to_num(bolus_col.values.astype(np.float64), nan=0.0)

        for mi in meal_indices:
            # Window around meal
            start = max(0, mi - 6)  # 30 min before
            end = min(N, mi + 24)   # 2 hours after

            if end - start < 12:
                continue

            # Find supply peak in window
            window_supply = supply_sm[start:end]
            if np.max(window_supply) < np.percentile(supply_sm[supply_sm > 0], 25):
                continue
            supply_peak = start + np.argmax(window_supply)

            # Find demand peak AFTER supply peak
            demand_window_start = supply_peak
            demand_window_end = min(N, supply_peak + 24)  # 2 hours
            if demand_window_end <= demand_window_start:
                continue
            window_demand = demand_sm[demand_window_start:demand_window_end]
            if len(window_demand) == 0:
                continue
            demand_peak = demand_window_start + np.argmax(window_demand)

            lag_min = (demand_peak - supply_peak) * 5
            if lag_min < 0:
                lag_min = 0

            # Check if bolus was given near this meal (±30 min)
            bolus_window = bolus_arr[max(0, mi-6):min(N, mi+6)]
            has_bolus = np.sum(bolus_window) > 0.5

            lags.append({
                'lag_min': int(lag_min),
                'carbs_g': float(carbs_arr[mi]),
                'has_bolus': bool(has_bolus),
            })
            if has_bolus:
                announced_lags.append(lag_min)

        if not lags:
            results[p['name']] = {'n_meals': len(meal_indices), 'n_analyzed': 0}
            continue

        all_lag = [l['lag_min'] for l in lags]
        bolused = [l for l in lags if l['has_bolus']]
        unbolused = [l for l in lags if not l['has_bolus']]

        results[p['name']] = {
            'n_meals': len(meal_indices),
            'n_analyzed': len(lags),
            'n_with_bolus': len(bolused),
            'n_without_bolus': len(unbolused),
            'lag_all_median': round(float(np.median(all_lag)), 1),
            'lag_bolused_median': round(float(np.median([l['lag_min'] for l in bolused])), 1) if bolused else None,
            'lag_unbolused_median': round(float(np.median([l['lag_min'] for l in unbolused])), 1) if unbolused else None,
            'lag_bolused_mean': round(float(np.mean([l['lag_min'] for l in bolused])), 1) if bolused else None,
            'lag_unbolused_mean': round(float(np.mean([l['lag_min'] for l in unbolused])), 1) if unbolused else None,
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']}: {r['n_analyzed']} meals analyzed, "
                  f"{r['n_with_bolus']} bolused, {r['n_without_bolus']} unbolused")
            if r['lag_bolused_median'] is not None:
                print(f"  Bolused lag: median={r['lag_bolused_median']:.0f}min, "
                      f"mean={r['lag_bolused_mean']:.0f}min")
            if r['lag_unbolused_median'] is not None:
                print(f"  Unbolused lag: median={r['lag_unbolused_median']:.0f}min, "
                      f"mean={r['lag_unbolused_mean']:.0f}min")

    return results


# ── EXP-473: TDD-Relative PK Channels ────────────────────────────────────

def run_exp473(patients, detail=False):
    """Express insulin as fraction of TDD and carbs as fraction of total daily carbs.

    This normalizes the "power" of metabolic activity relative to the patient's
    baseline. A 2U bolus means very different things for someone with TDD=20 vs TDD=80.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        N = len(df)

        if not hasattr(df.index, 'date'):
            continue

        # Compute daily totals
        bolus = np.nan_to_num(df.get('bolus', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df.get('carbs', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64), nan=0.0)
        temp_rate = np.nan_to_num(df.get('temp_rate', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64), nan=0.0)

        # TDD = sum(bolus) + sum(temp_rate * 5/60) per day
        dates = df.index.date
        unique_dates = sorted(set(dates))

        daily_tdd = {}
        daily_carbs = {}
        for d in unique_dates:
            mask = dates == d
            tdd = np.sum(bolus[mask]) + np.sum(temp_rate[mask]) * 5.0 / 60.0
            tc = np.sum(carbs[mask])
            daily_tdd[d] = max(tdd, 1.0)  # avoid division by zero
            daily_carbs[d] = max(tc, 1.0)

        # Normalize each timestep's insulin and carbs by daily total
        insulin_frac = np.zeros(N)
        carbs_frac = np.zeros(N)
        for i in range(N):
            d = dates[i]
            # Insulin: bolus contribution as fraction of TDD
            insulin_frac[i] = bolus[i] / daily_tdd[d]
            carbs_frac[i] = carbs[i] / daily_carbs[d]

        # Compute supply-demand with normalized channels
        sd = compute_supply_demand(df, pk)

        # TDD-normalized throughput
        tdd_arr = np.array([daily_tdd[d] for d in dates])
        product_tdd_norm = sd['product'] / (tdd_arr ** 2)  # normalize by TDD²
        sum_tdd_norm = sd['sum_flux'] / tdd_arr

        # Cross-patient: compute coefficient of variation of normalized signals
        results[p['name']] = {
            'tdd_mean': round(float(np.mean(list(daily_tdd.values()))), 1),
            'tdd_std': round(float(np.std(list(daily_tdd.values()))), 1),
            'total_daily_carbs_mean': round(float(np.mean(list(daily_carbs.values()))), 1),
            'product_raw_mean': round(float(np.mean(sd['product'])), 2),
            'product_tdd_norm_mean': round(float(np.mean(product_tdd_norm)), 4),
            'product_tdd_norm_cv': round(float(np.std(product_tdd_norm) / max(np.mean(product_tdd_norm), 1e-8)), 3),
            'sum_raw_mean': round(float(np.mean(sd['sum_flux'])), 2),
            'sum_tdd_norm_mean': round(float(np.mean(sum_tdd_norm)), 4),
            'sum_tdd_norm_cv': round(float(np.std(sum_tdd_norm) / max(np.mean(sum_tdd_norm), 1e-8)), 3),
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']}: TDD={r['tdd_mean']:.1f}±{r['tdd_std']:.1f}, "
                  f"daily carbs={r['total_daily_carbs_mean']:.0f}g")
            print(f"  product: raw={r['product_raw_mean']:.1f}, "
                  f"TDD-norm={r['product_tdd_norm_mean']:.4f} (CV={r['product_tdd_norm_cv']:.3f})")

    # Cross-patient comparison: does TDD normalization reduce inter-patient variance?
    if len(results) >= 3:
        raw_means = [v['product_raw_mean'] for v in results.values()]
        norm_means = [v['product_tdd_norm_mean'] for v in results.values()]
        raw_cv = np.std(raw_means) / max(np.mean(raw_means), 1e-8)
        norm_cv = np.std(norm_means) / max(np.mean(norm_means), 1e-8)

        cross = {
            'cross_patient_product_raw_cv': round(float(raw_cv), 3),
            'cross_patient_product_tdd_norm_cv': round(float(norm_cv), 3),
            'normalization_reduces_variance': norm_cv < raw_cv,
        }
        for v in results.values():
            v['cross_patient'] = cross
        if detail:
            print(f"\nCross-patient: raw CV={raw_cv:.3f}, TDD-norm CV={norm_cv:.3f}, "
                  f"reduces variance: {norm_cv < raw_cv}")

    return results


# ── EXP-474: Basal-Relative (AC/DC) Insulin Decomposition ────────────────

def run_exp474(patients, detail=False):
    """Decompose insulin into DC (basal) and AC (bolus) components.

    The basal rate is the DC offset — steady-state insulin delivery.
    Boluses and temp adjustments are the AC signal — event-driven changes.

    The AC component should be much more discriminative for event classification
    since it represents intentional metabolic interventions.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        N = len(df)

        if not hasattr(df.index, 'hour'):
            continue

        # DC: basal schedule expanded
        basal_sched = df.attrs.get('basal_schedule', [])
        basal_dc = expand_schedule(df.index, basal_sched, default=0.5)[:N]

        # Total insulin activity from PK channel 0
        insulin_total = pk[:, 0] * PK_NORMALIZATION['insulin_total']  # U/min

        # Convert basal to U/min for same units
        basal_dc_per_min = basal_dc / 60.0  # U/hr → U/min

        # AC = total - DC (can be negative if AID reduces below profile)
        insulin_ac = insulin_total - basal_dc_per_min

        # ISF for conversion to mg/dL
        isf_sched = df.attrs.get('isf_schedule', [])
        isf_curve = expand_schedule(df.index, isf_sched, default=40.0)[:N]
        if np.median(isf_curve) < 15:
            isf_curve = isf_curve * 18.0182

        # Convert to mg/dL per 5min
        demand_total = np.abs(insulin_total * 5.0 * isf_curve)
        demand_dc = np.abs(basal_dc_per_min * 5.0 * isf_curve)
        demand_ac = insulin_ac * 5.0 * isf_curve  # signed: positive = above basal

        # Supply from original decomposition
        sd = compute_supply_demand(df, pk)

        # How much of total demand is DC (basal) vs AC (corrections/meals)?
        dc_fraction = np.mean(demand_dc) / max(np.mean(demand_total), 0.01)

        # AC power: RMS of AC component (like electrical AC power)
        ac_rms = np.sqrt(np.mean(demand_ac ** 2))

        # Event windows: AC signal during meal times vs fasting
        carbs = np.nan_to_num(df.get('carbs', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64), nan=0.0)
        meal_mask = np.zeros(N, dtype=bool)
        meal_indices = np.where(carbs > 5)[0]
        for mi in meal_indices:
            meal_mask[max(0, mi):min(N, mi + 24)] = True  # 2h after meal

        ac_meal = np.mean(demand_ac[meal_mask]) if meal_mask.sum() > 0 else 0
        ac_fasting = np.mean(demand_ac[~meal_mask]) if (~meal_mask).sum() > 0 else 0

        results[p['name']] = {
            'dc_fraction_of_demand': round(float(dc_fraction), 3),
            'ac_rms_mgdl_5min': round(float(ac_rms), 2),
            'ac_mean_at_meals': round(float(ac_meal), 2),
            'ac_mean_fasting': round(float(ac_fasting), 2),
            'ac_meal_vs_fasting_ratio': round(float(ac_meal / max(abs(ac_fasting), 0.01)), 2),
            'demand_total_mean': round(float(np.mean(demand_total)), 2),
            'demand_dc_mean': round(float(np.mean(demand_dc)), 2),
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']}: DC={r['dc_fraction_of_demand']:.1%} of demand, "
                  f"AC RMS={r['ac_rms_mgdl_5min']:.2f}")
            print(f"  AC at meals={r['ac_mean_at_meals']:+.2f}, "
                  f"AC fasting={r['ac_mean_fasting']:+.2f}, "
                  f"ratio={r['ac_meal_vs_fasting_ratio']:.1f}×")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-468–475: Phase-informed experiments')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--quick', action='store_true', help='Only load 3 patients')
    parser.add_argument('--detail', action='store_true', help='Verbose per-patient output')
    parser.add_argument('--save', action='store_true', help='Save results JSON')
    parser.add_argument('--exp', type=str, default='all',
                        help='Run specific experiments (468,471,473,474) or all')
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    max_patients = 3 if args.quick else None
    patients = load_patients(str(patients_dir), max_patients=max_patients)
    print(f"Loaded {len(patients)} patients")

    all_results = {}
    exps = args.exp.split(',') if args.exp != 'all' else ['468', '471', '473', '474']

    if '468' in exps:
        print("\n═══ EXP-468: Hybrid Hepatic Model ═══")
        r468 = run_exp468(patients, detail=args.detail)
        all_results['exp468_hybrid_hepatic'] = r468

        improvements = [v['improvement_pct'] for v in r468.values()]
        print(f"\nResidual improvement: mean {np.mean(improvements):+.1f}% "
              f"(range {min(improvements):+.1f}% to {max(improvements):+.1f}%)")

    if '471' in exps:
        print("\n═══ EXP-471: Phase Lag as UAM Feature ═══")
        r471 = run_exp471(patients, detail=args.detail)
        all_results['exp471_phase_lag_uam'] = r471

        bolused_lags = [v['lag_bolused_median'] for v in r471.values()
                        if v.get('lag_bolused_median') is not None]
        unbolused_lags = [v['lag_unbolused_median'] for v in r471.values()
                          if v.get('lag_unbolused_median') is not None]
        if bolused_lags and unbolused_lags:
            print(f"\nBolused median lag: {np.median(bolused_lags):.0f} min")
            print(f"Unbolused median lag: {np.median(unbolused_lags):.0f} min")
            print(f"Separation: {np.median(unbolused_lags) - np.median(bolused_lags):.0f} min")

    if '473' in exps:
        print("\n═══ EXP-473: TDD-Relative PK Channels ═══")
        r473 = run_exp473(patients, detail=args.detail)
        all_results['exp473_tdd_relative'] = r473

    if '474' in exps:
        print("\n═══ EXP-474: Basal-Relative (AC/DC) Decomposition ═══")
        r474 = run_exp474(patients, detail=args.detail)
        all_results['exp474_ac_dc_decomposition'] = r474

        dc_fracs = [v['dc_fraction_of_demand'] for v in r474.values()]
        ac_ratios = [v['ac_meal_vs_fasting_ratio'] for v in r474.values()]
        print(f"\nDC fraction: mean {np.mean(dc_fracs):.1%} (range {min(dc_fracs):.1%}–{max(dc_fracs):.1%})")
        print(f"AC meal/fasting ratio: mean {np.mean(ac_ratios):.1f}× (range {min(ac_ratios):.1f}–{max(ac_ratios):.1f})")

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, val in all_results.items():
            path = RESULTS_DIR / f"{key}.json"
            with open(path, 'w') as f:
                json.dump(val, f, indent=2, default=str)
            print(f"Saved: {path}")

    return all_results


if __name__ == '__main__':
    main()
