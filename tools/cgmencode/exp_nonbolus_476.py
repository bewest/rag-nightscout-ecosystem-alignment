#!/usr/bin/env python3
"""EXP-476–479: Non-Bolusing & Idealized Model Robustness.

Tests whether metabolic flux features work for patients who DON'T bolus
(100% UAM / SMB-only), where the "close enough" idealized model must
substitute for missing carb entries.

Patient behavior spectrum (from cohort analysis):
  - k: 0.4 carb entries/day, 42.8 SMBs/day (0.4U) → near 100% UAM
  - i: 0.6 carb entries/day, 56.3 SMBs/day (0.7U) → near 100% UAM
  - e: 2.0 carb entries/day, 52.1 SMBs/day (1.1U) → heavy SMB
  - f: 2.0 carb entries/day, 3.0 boluses/day (8.3U) → traditional boluser
  - a: 3.8 carb entries/day, 4.9 boluses/day (3.9U) → traditional boluser

Key insight: For non-bolusers, carb_supply ≈ 0 (no COB data). But the AID
still reacts to glucose rises via SMBs → demand signal captures the response.
The "unmodeled supply" appears as the conservation residual.

Three alternative supply proxies for non-bolusing patients:
  1. Demand-only: AID reaction (SMB clusters) marks meal events
  2. Glucose derivative: dBG/dt as proxy for net supply
  3. Conservation residual: actual ΔBG − predicted ΔBG = unmodeled supply

EXP-476: Classify patients by bolusing style (traditional vs SMB vs hybrid)
EXP-477: Compare meal detection across bolusing styles
EXP-478: Residual-as-supply — use conservation residual as UAM supply proxy
EXP-479: AC/DC + phase features robustness across bolusing styles

References:
  - exp_phase_informed_468.py: EXP-471 phase lag, EXP-474 AC/DC
  - exp_metabolic_441.py: compute_supply_demand()
  - exp_meal_tally.py: EXP-447 meal tally
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from cgmencode.continuous_pk import (
    expand_schedule,
    PK_NORMALIZATION,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-476: Classify Bolusing Style ─────────────────────────────────────

def classify_bolusing_style(df):
    """Classify patient's insulin delivery pattern.

    Returns dict with style classification and metrics:
      - 'traditional': Few large boluses (< 10/day, mean > 2U)
      - 'smb_dominant': Many tiny boluses (> 20/day, mean < 1U), few carb entries
      - 'hybrid': Mix of SMBs and manual boluses
      - 'uam_fraction': Estimated fraction of meals that are unannounced
    """
    N = len(df)
    total_days = max(N / 288, 1)

    bolus = np.nan_to_num(
        df.get('bolus', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64),
        nan=0.0)
    carbs = np.nan_to_num(
        df.get('carbs', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64),
        nan=0.0)

    n_bolus = np.sum(bolus > 0.1)
    n_carbs = np.sum(carbs > 0)
    bolus_per_day = n_bolus / total_days
    carb_entries_per_day = n_carbs / total_days

    mean_bolus_size = float(np.mean(bolus[bolus > 0.1])) if n_bolus > 0 else 0.0
    total_bolus_per_day = float(np.sum(bolus) / total_days)

    # Classification
    if bolus_per_day > 20 and mean_bolus_size < 1.5:
        style = 'smb_dominant'
    elif bolus_per_day < 10 and mean_bolus_size > 2.0:
        style = 'traditional'
    else:
        style = 'hybrid'

    # Estimate UAM fraction: what fraction of glucose rises lack a carb entry?
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = np.nan_to_num(df[bg_col].values.astype(np.float64), nan=0.0)
    dbg = np.diff(bg)

    # Rising windows (> 2 mg/dL per 5 min for 15+ min)
    rising = np.zeros(len(dbg), dtype=bool)
    for i in range(2, len(dbg)):
        if dbg[i-2] > 1 and dbg[i-1] > 1 and dbg[i] > 1:
            rising[i] = True

    n_rises = 0
    n_announced = 0
    i = 0
    while i < len(rising):
        if rising[i]:
            start = i
            while i < len(rising) and rising[i]:
                i += 1
            n_rises += 1
            # Check if carb entry within ±30 min of rise start
            window_start = max(0, start - 6)
            window_end = min(N, start + 6)
            if np.sum(carbs[window_start:window_end]) > 0:
                n_announced += 1
        else:
            i += 1

    uam_fraction = 1.0 - (n_announced / max(n_rises, 1))

    return {
        'style': style,
        'bolus_per_day': round(bolus_per_day, 1),
        'carb_entries_per_day': round(carb_entries_per_day, 1),
        'mean_bolus_size_U': round(mean_bolus_size, 2),
        'total_bolus_per_day_U': round(total_bolus_per_day, 1),
        'n_glucose_rises': n_rises,
        'n_announced_rises': n_announced,
        'uam_fraction': round(uam_fraction, 3),
    }


def run_exp476(patients, detail=False):
    """Classify all patients by bolusing style."""
    results = {}
    for p in patients:
        style = classify_bolusing_style(p['df'])
        results[p['name']] = style
        if detail:
            print(f"\n{p['name']}: {style['style']} — "
                  f"{style['bolus_per_day']} bolus/day "
                  f"({style['mean_bolus_size_U']}U avg), "
                  f"{style['carb_entries_per_day']} carbs/day, "
                  f"UAM={style['uam_fraction']:.0%}")
    return results


# ── EXP-477: Meal Detection Across Bolusing Styles ───────────────────────

def detect_meals_demand_only(sd, min_distance=12):
    """Detect meals from demand signal alone (AID reaction to glucose rises).

    For SMB-dominant patients, clusters of increasing demand mark meal responses.
    The AID ramps up SMBs → demand rises → signals a meal even without carb data.
    """
    demand = sd['demand']
    demand_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values
    threshold = np.percentile(demand_smooth[demand_smooth > 0], 60)

    peaks, props = find_peaks(demand_smooth, height=threshold,
                              distance=min_distance, prominence=threshold * 0.3)
    return peaks, demand_smooth


def detect_meals_residual(df, sd):
    """Detect meals from conservation residual (unmodeled supply proxy).

    residual = actual ΔBG − predicted ΔBG
    Positive residual = more glucose appearing than modeled → likely UAM meal.
    """
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)
    dbg = np.zeros_like(bg)
    dbg[1:] = bg[1:] - bg[:-1]

    predicted_dbg = sd['supply'] - sd['demand']
    residual = dbg - predicted_dbg

    # Smooth and find positive peaks (unmodeled supply)
    resid_smooth = pd.Series(residual).rolling(6, center=True, min_periods=1).mean().values
    pos_resid = np.maximum(resid_smooth, 0)
    threshold = np.percentile(pos_resid[pos_resid > 0], 70) if np.sum(pos_resid > 0) > 100 else 1.0

    peaks, _ = find_peaks(pos_resid, height=threshold,
                          distance=12, prominence=threshold * 0.3)
    return peaks, resid_smooth


def detect_meals_glucose_derivative(df, min_distance=12):
    """Detect meals from glucose rate of change (simplest approach).

    dBG/dt > threshold for sustained period → likely meal.
    Works regardless of bolusing style.
    """
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)
    dbg = np.zeros_like(bg)
    dbg[1:] = bg[1:] - bg[:-1]

    dbg_smooth = pd.Series(dbg).rolling(6, center=True, min_periods=1).mean().values
    pos_dbg = np.maximum(dbg_smooth, 0)
    threshold = np.percentile(pos_dbg[pos_dbg > 0], 70) if np.sum(pos_dbg > 0) > 100 else 1.0

    peaks, _ = find_peaks(pos_dbg, height=threshold,
                          distance=min_distance, prominence=threshold * 0.3)
    return peaks, dbg_smooth


def run_exp477(patients, styles, detail=False):
    """Compare meal detection methods across bolusing styles.

    For each patient, compare 4 detection methods:
    1. supply_demand: Original sum_flux peaks (needs carb data)
    2. demand_only: AID reaction peaks (works without carb data)
    3. residual: Conservation residual peaks (unmodeled supply)
    4. glucose_deriv: Simple dBG/dt peaks (baseline)

    Ground truth: known carb entries (where available) + glucose rises.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)
        N = len(df)
        total_days = max(N / 288, 1)
        style = styles.get(p['name'], {}).get('style', 'unknown')

        # Method 1: Sum flux (original)
        sum_flux = sd['sum_flux']
        sf_smooth = pd.Series(sum_flux).rolling(6, center=True, min_periods=1).mean().values
        sf_thresh = np.percentile(sf_smooth[sf_smooth > 0], 50) if np.sum(sf_smooth > 0) > 100 else 1.0
        sf_peaks, _ = find_peaks(sf_smooth, height=sf_thresh, distance=12,
                                 prominence=sf_thresh * 0.3)

        # Method 2: Demand only
        demand_peaks, _ = detect_meals_demand_only(sd)

        # Method 3: Residual
        resid_peaks, _ = detect_meals_residual(df, sd)

        # Method 4: Glucose derivative
        gd_peaks, _ = detect_meals_glucose_derivative(df)

        # Ground truth: carb entries
        carbs = np.nan_to_num(
            df.get('carbs', pd.Series(np.zeros(N), index=df.index)).values.astype(np.float64),
            nan=0.0)
        carb_events = np.where(carbs > 5)[0]
        # Deduplicate
        if len(carb_events) > 0:
            deduped = [carb_events[0]]
            for idx in carb_events[1:]:
                if idx - deduped[-1] > 24:
                    deduped.append(idx)
            carb_events = np.array(deduped)

        def count_hits(detected_peaks, truth, tolerance=12):
            """Count how many truth events have a detected peak within tolerance."""
            if len(truth) == 0 or len(detected_peaks) == 0:
                return 0, 0
            hits = 0
            for t in truth:
                dists = np.abs(detected_peaks - t)
                if np.min(dists) <= tolerance:
                    hits += 1
            return hits, len(truth)

        sf_hits, sf_total = count_hits(sf_peaks, carb_events)
        dem_hits, dem_total = count_hits(demand_peaks, carb_events)
        res_hits, res_total = count_hits(resid_peaks, carb_events)
        gd_hits, gd_total = count_hits(gd_peaks, carb_events)

        results[p['name']] = {
            'style': style,
            'carb_events': len(carb_events),
            'methods': {
                'sum_flux': {
                    'events_per_day': round(len(sf_peaks) / total_days, 1),
                    'recall': round(sf_hits / max(sf_total, 1), 3),
                },
                'demand_only': {
                    'events_per_day': round(len(demand_peaks) / total_days, 1),
                    'recall': round(dem_hits / max(dem_total, 1), 3),
                },
                'residual': {
                    'events_per_day': round(len(resid_peaks) / total_days, 1),
                    'recall': round(res_hits / max(res_total, 1), 3),
                },
                'glucose_deriv': {
                    'events_per_day': round(len(gd_peaks) / total_days, 1),
                    'recall': round(gd_hits / max(gd_total, 1), 3),
                },
            },
        }

        if detail:
            r = results[p['name']]
            m = r['methods']
            print(f"\n{p['name']} ({style}, {r['carb_events']} carb events):")
            for mname, mv in m.items():
                print(f"  {mname:15s}: {mv['events_per_day']:.1f}/day, "
                      f"recall={mv['recall']:.0%}")

    return results


# ── EXP-478: Residual-as-Supply ───────────────────────────────────────────

def run_exp478(patients, styles, detail=False):
    """Use conservation residual as UAM supply proxy.

    For non-bolusing patients, the conservation equation is:
      ΔBG = supply - demand + residual

    Where residual captures unmodeled supply (UAM meals, exercise, etc.).
    We reconstruct an "augmented supply" = hepatic + carb_supply + max(residual, 0)
    and test if this improves the phase relationship quality.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)
        N = len(df)
        style = styles.get(p['name'], {}).get('style', 'unknown')

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        dbg = np.zeros_like(bg)
        dbg[1:] = bg[1:] - bg[:-1]

        predicted_dbg = sd['supply'] - sd['demand']
        residual = dbg - predicted_dbg

        # Positive residual = unmodeled supply (UAM meals)
        uam_supply = np.maximum(residual, 0)
        # Negative residual = unmodeled demand (exercise, overcorrection)
        unmodeled_demand = np.maximum(-residual, 0)

        # Augmented supply and demand
        aug_supply = sd['supply'] + uam_supply
        aug_demand = sd['demand'] + unmodeled_demand

        # Augmented product (throughput)
        aug_product = aug_supply * aug_demand

        # Compare: does augmented decomposition detect more meals?
        # Use augmented sum_flux
        aug_sum_flux = (aug_supply - sd['hepatic']) + aug_demand
        asf_smooth = pd.Series(aug_sum_flux).rolling(6, center=True, min_periods=1).mean().values
        asf_thresh = np.percentile(asf_smooth[asf_smooth > 0], 50) if np.sum(asf_smooth > 0) > 100 else 1.0
        asf_peaks, _ = find_peaks(asf_smooth, height=asf_thresh, distance=12,
                                  prominence=asf_thresh * 0.3)

        # Original sum_flux for comparison
        sf_smooth = pd.Series(sd['sum_flux']).rolling(6, center=True, min_periods=1).mean().values
        sf_thresh = np.percentile(sf_smooth[sf_smooth > 0], 50) if np.sum(sf_smooth > 0) > 100 else 1.0
        sf_peaks, _ = find_peaks(sf_smooth, height=sf_thresh, distance=12,
                                 prominence=sf_thresh * 0.3)

        total_days = max(N / 288, 1)

        # Conservation quality: how much residual is captured?
        orig_resid_rms = float(np.sqrt(np.mean(residual ** 2)))
        # After augmentation, residual should be near zero
        aug_resid = dbg - (aug_supply - aug_demand)
        aug_resid_rms = float(np.sqrt(np.mean(aug_resid ** 2)))

        # Fraction of time residual is "supply-like" vs "demand-like"
        supply_residual_frac = float(np.mean(residual > 0.5))
        demand_residual_frac = float(np.mean(residual < -0.5))

        results[p['name']] = {
            'style': style,
            'uam_supply_mean': round(float(np.mean(uam_supply)), 3),
            'unmodeled_demand_mean': round(float(np.mean(unmodeled_demand)), 3),
            'orig_events_per_day': round(len(sf_peaks) / total_days, 1),
            'augmented_events_per_day': round(len(asf_peaks) / total_days, 1),
            'events_gained': round((len(asf_peaks) - len(sf_peaks)) / total_days, 1),
            'orig_resid_rms': round(orig_resid_rms, 2),
            'aug_resid_rms': round(aug_resid_rms, 2),
            'supply_residual_fraction': round(supply_residual_frac, 3),
            'demand_residual_fraction': round(demand_residual_frac, 3),
            'aug_product_mean': round(float(np.mean(aug_product)), 1),
            'orig_product_mean': round(float(np.mean(sd['product'])), 1),
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']} ({style}):")
            print(f"  Events/day: orig={r['orig_events_per_day']:.1f} → "
                  f"augmented={r['augmented_events_per_day']:.1f} "
                  f"(+{r['events_gained']:.1f})")
            print(f"  Residual RMS: {r['orig_resid_rms']:.2f} → {r['aug_resid_rms']:.2f}")
            print(f"  Residual budget: supply-like={r['supply_residual_fraction']:.0%}, "
                  f"demand-like={r['demand_residual_fraction']:.0%}")

    return results


# ── EXP-479: Feature Robustness Across Bolusing Styles ────────────────────

def run_exp479(patients, styles, detail=False):
    """Test AC/DC and phase features across bolusing styles.

    The idealized model should work if:
    1. AC signal still separates meal from fasting (even with SMBs)
    2. Demand peaks still cluster at meal times
    3. The phase portrait (24h supply/demand) still shows circadian pattern

    For SMB patients: AC = sum of SMBs above baseline. Many tiny boluses
    should aggregate into demand peaks that track meals.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)
        N = len(df)
        style = styles.get(p['name'], {}).get('style', 'unknown')

        if not hasattr(df.index, 'hour'):
            continue

        # AC/DC decomposition
        basal_sched = df.attrs.get('basal_schedule', [])
        basal_dc = expand_schedule(df.index, basal_sched, default=0.5)[:N]
        insulin_total = pk[:, 0] * PK_NORMALIZATION['insulin_total']
        basal_dc_per_min = basal_dc / 60.0
        insulin_ac = insulin_total - basal_dc_per_min

        isf_sched = df.attrs.get('isf_schedule', [])
        isf_curve = expand_schedule(df.index, isf_sched, default=40.0)[:N]
        if np.median(isf_curve) < 15:
            isf_curve = isf_curve * 18.0182

        demand_ac = insulin_ac * 5.0 * isf_curve

        # Detect glucose rises (proxy for "true meals" regardless of announcement)
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        dbg = np.zeros_like(bg)
        dbg[1:] = bg[1:] - bg[:-1]
        dbg_smooth = pd.Series(dbg).rolling(6, center=True, min_periods=1).mean().values

        # Glucose rise windows (sustained >1 mg/dL/5min for 15+ min)
        rise_mask = np.zeros(N, dtype=bool)
        for i in range(3, N):
            if dbg_smooth[i-2] > 0.5 and dbg_smooth[i-1] > 0.5 and dbg_smooth[i] > 0.5:
                rise_mask[i] = True

        # Steady/falling windows
        steady_mask = ~rise_mask

        # AC signal during glucose rises vs steady
        ac_at_rise = float(np.mean(demand_ac[rise_mask])) if rise_mask.sum() > 100 else 0
        ac_at_steady = float(np.mean(demand_ac[steady_mask])) if steady_mask.sum() > 100 else 0

        # Demand signal during rises vs steady
        demand_at_rise = float(np.mean(sd['demand'][rise_mask])) if rise_mask.sum() > 100 else 0
        demand_at_steady = float(np.mean(sd['demand'][steady_mask])) if steady_mask.sum() > 100 else 0

        # Phase: how quickly does demand respond to glucose rise?
        # Find glucose rise onsets
        rise_starts = []
        in_rise = False
        for i in range(N):
            if rise_mask[i] and not in_rise:
                rise_starts.append(i)
                in_rise = True
            elif not rise_mask[i]:
                in_rise = False

        # For each rise onset, measure time to demand peak
        demand_smooth = pd.Series(sd['demand']).rolling(6, center=True, min_periods=1).mean().values
        response_lags = []
        for rs in rise_starts:
            window_end = min(N, rs + 36)  # 3 hours
            if window_end - rs < 12:
                continue
            window = demand_smooth[rs:window_end]
            peak_idx = np.argmax(window)
            if peak_idx > 0:
                response_lags.append(peak_idx * 5)  # minutes

        results[p['name']] = {
            'style': style,
            'glucose_rise_fraction': round(float(rise_mask.sum() / N), 3),
            'ac_at_rise': round(ac_at_rise, 2),
            'ac_at_steady': round(ac_at_steady, 2),
            'ac_rise_vs_steady': round(ac_at_rise / max(abs(ac_at_steady), 0.01), 1),
            'demand_at_rise': round(demand_at_rise, 2),
            'demand_at_steady': round(demand_at_steady, 2),
            'demand_rise_ratio': round(demand_at_rise / max(demand_at_steady, 0.01), 2),
            'n_rise_events': len(rise_starts),
            'response_lag_median_min': round(float(np.median(response_lags)), 0) if response_lags else None,
            'response_lag_mean_min': round(float(np.mean(response_lags)), 0) if response_lags else None,
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']} ({style}):")
            print(f"  AC: rise={r['ac_at_rise']:+.2f}, steady={r['ac_at_steady']:+.2f}, "
                  f"ratio={r['ac_rise_vs_steady']:.1f}×")
            print(f"  Demand: rise={r['demand_at_rise']:.2f}, steady={r['demand_at_steady']:.2f}, "
                  f"ratio={r['demand_rise_ratio']:.2f}")
            if r['response_lag_median_min'] is not None:
                print(f"  Glucose→demand response: median={r['response_lag_median_min']:.0f}min, "
                      f"mean={r['response_lag_mean_min']:.0f}min")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-476–479: Non-bolusing & idealized model robustness')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--quick', action='store_true', help='Only load 3 patients')
    parser.add_argument('--detail', action='store_true', help='Verbose per-patient output')
    parser.add_argument('--save', action='store_true', help='Save results JSON')
    parser.add_argument('--exp', type=str, default='all',
                        help='Run specific experiments (476,477,478,479) or all')
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    max_patients = 3 if args.quick else None
    patients = load_patients(str(patients_dir), max_patients=max_patients)
    print(f"Loaded {len(patients)} patients")

    all_results = {}
    exps = args.exp.split(',') if args.exp != 'all' else ['476', '477', '478', '479']

    # EXP-476 is needed by later experiments
    print("\n═══ EXP-476: Bolusing Style Classification ═══")
    r476 = run_exp476(patients, detail=args.detail)
    all_results['exp476_bolusing_styles'] = r476

    # Summary
    style_counts = {}
    for v in r476.values():
        s = v['style']
        style_counts[s] = style_counts.get(s, 0) + 1
    print(f"\nStyles: {style_counts}")
    uam_fracs = [v['uam_fraction'] for v in r476.values()]
    print(f"UAM fraction: mean {np.mean(uam_fracs):.0%} "
          f"(range {min(uam_fracs):.0%}–{max(uam_fracs):.0%})")

    if '477' in exps:
        print("\n═══ EXP-477: Meal Detection Across Styles ═══")
        r477 = run_exp477(patients, r476, detail=args.detail)
        all_results['exp477_meal_detection_styles'] = r477

        # Compare methods by style
        for style in ['traditional', 'smb_dominant', 'hybrid']:
            style_patients = {k: v for k, v in r477.items() if v['style'] == style}
            if not style_patients:
                continue
            print(f"\n  {style.upper()} ({len(style_patients)} patients):")
            for method in ['sum_flux', 'demand_only', 'residual', 'glucose_deriv']:
                recalls = [v['methods'][method]['recall']
                           for v in style_patients.values()
                           if v['carb_events'] > 0]
                events = [v['methods'][method]['events_per_day']
                          for v in style_patients.values()]
                if recalls:
                    print(f"    {method:15s}: recall={np.mean(recalls):.0%}, "
                          f"events/day={np.mean(events):.1f}")

    if '478' in exps:
        print("\n═══ EXP-478: Residual-as-Supply ═══")
        r478 = run_exp478(patients, r476, detail=args.detail)
        all_results['exp478_residual_supply'] = r478

        # Summary by style
        for style in ['traditional', 'smb_dominant', 'hybrid']:
            sp = {k: v for k, v in r478.items() if v['style'] == style}
            if not sp:
                continue
            gained = [v['events_gained'] for v in sp.values()]
            print(f"\n  {style}: events gained/day = {np.mean(gained):+.1f}")

    if '479' in exps:
        print("\n═══ EXP-479: Feature Robustness Across Styles ═══")
        r479 = run_exp479(patients, r476, detail=args.detail)
        all_results['exp479_feature_robustness'] = r479

        # Key question: does AC signal work for SMB patients?
        for style in ['traditional', 'smb_dominant', 'hybrid']:
            sp = {k: v for k, v in r479.items() if v['style'] == style}
            if not sp:
                continue
            ac_ratios = [v['ac_rise_vs_steady'] for v in sp.values()]
            dem_ratios = [v['demand_rise_ratio'] for v in sp.values()]
            lags = [v['response_lag_median_min'] for v in sp.values()
                    if v['response_lag_median_min'] is not None]
            print(f"\n  {style} ({len(sp)} patients):")
            print(f"    AC rise/steady ratio: {np.mean(ac_ratios):.1f}×")
            print(f"    Demand rise/steady ratio: {np.mean(dem_ratios):.2f}")
            if lags:
                print(f"    Glucose→demand lag: {np.median(lags):.0f}min")

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, val in all_results.items():
            path = RESULTS_DIR / f"{key}.json"
            with open(path, 'w') as f:
                json.dump(val, f, indent=2, default=str)
            print(f"\nSaved: {path}")

    return all_results


if __name__ == '__main__':
    main()
