#!/usr/bin/env python3
"""EXP-464–467: Phase Relationship Visualization & Schedule Decomposition.

Answers the fundamental question: Do the PK dynamics show insulin and glucose
activities moving in and out of phase correctly over the 24h cycle?

The user's insight connects therapy settings to physiology:
  - CR schedule  ↔ EGP variation: Higher CR = more carbs/U = body needs more
    glucose energy → basal increases in same time segments (IN PHASE)
  - ISF schedule ↔ Resistance: Lower ISF = more resistance → dawn cortisol etc.
    ISF and sensitivity are anti-phase with resistance.
  - Basal schedule ↔ Hepatic production: Higher basal needed when EGP is higher

EXP-464: 24h Phase Portrait — Average supply vs demand by hour-of-day
EXP-465: Schedule Concordance — Do basal, CR, ISF schedules move together?
EXP-466: Phase lag measurement — Cross-correlation of supply/demand at meals
EXP-467: UVA/Padova compartment comparison — Do our channels match expected
          multi-compartment behavior?

References:
  - continuous_pk.py: expand_schedule(), build_continuous_pk_features()
  - exp_metabolic_441.py: compute_supply_demand() (NOW with time-varying CR)
  - cgmsim-lib liver.ts: Hill equation EGP model
  - UVA/Padova: Dalla Man et al. 2007 — Multi-compartment glucose model
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.continuous_pk import (
    expand_schedule,
    PK_NORMALIZATION,
    PK_CHANNEL_NAMES,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-464: 24h Phase Portrait ──────────────────────────────────────────

def run_exp464(patients, detail=False):
    """Average supply vs demand by hour of day — shows the phase dance.

    If schedules are correct, we should see:
    - Supply peaks at meal times (carb absorption + hepatic)
    - Demand peaks ~30-60min AFTER meals (insulin action lag)
    - Overnight: both low, demand slightly > supply (BG falling or stable)
    - Dawn (4-7 AM): supply rises (hepatic up), demand lags → BG rising
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        if not hasattr(df.index, 'hour'):
            continue

        hours = df.index.hour + df.index.minute / 60.0

        # Bin into 24 hourly bins
        hourly = {}
        for h in range(24):
            mask = (hours >= h) & (hours < h + 1)
            if mask.sum() < 10:
                continue
            hourly[h] = {
                'supply_mean': float(np.mean(sd['supply'][mask])),
                'demand_mean': float(np.mean(sd['demand'][mask])),
                'hepatic_mean': float(np.mean(sd['hepatic'][mask])),
                'carb_supply_mean': float(np.mean(sd['carb_supply'][mask])),
                'product_mean': float(np.mean(sd['product'][mask])),
                'ratio_mean': float(np.mean(sd['ratio'][mask])),
                'net_mean': float(np.mean(sd['net'][mask])),
                'n': int(mask.sum()),
            }

        # Find phase characteristics
        supply_by_hr = [hourly.get(h, {}).get('supply_mean', 0) for h in range(24)]
        demand_by_hr = [hourly.get(h, {}).get('demand_mean', 0) for h in range(24)]

        # Cross-correlation to find lag
        supply_arr = np.array(supply_by_hr) - np.mean(supply_by_hr)
        demand_arr = np.array(demand_by_hr) - np.mean(demand_by_hr)
        xcorr = np.correlate(supply_arr, demand_arr, mode='full')
        lags = np.arange(-23, 24)
        peak_lag_idx = np.argmax(xcorr)
        peak_lag_hr = int(lags[peak_lag_idx])

        # Peak hours
        supply_peak_hr = int(np.argmax(supply_by_hr))
        demand_peak_hr = int(np.argmax(demand_by_hr))

        # Dawn window (4-7 AM) — supply should exceed demand here
        dawn_hours = [4, 5, 6]
        dawn_supply = np.mean([hourly.get(h, {}).get('supply_mean', 0) for h in dawn_hours])
        dawn_demand = np.mean([hourly.get(h, {}).get('demand_mean', 0) for h in dawn_hours])

        # Overnight window (0-4 AM) — demand should exceed supply (BG stable/falling)
        night_hours = [0, 1, 2, 3]
        night_supply = np.mean([hourly.get(h, {}).get('supply_mean', 0) for h in night_hours])
        night_demand = np.mean([hourly.get(h, {}).get('demand_mean', 0) for h in night_hours])

        results[p['name']] = {
            'hourly_profile': hourly,
            'supply_peak_hour': supply_peak_hr,
            'demand_peak_hour': demand_peak_hr,
            'supply_demand_lag_hours': peak_lag_hr,
            'dawn_supply': round(dawn_supply, 2),
            'dawn_demand': round(dawn_demand, 2),
            'dawn_ratio': round(dawn_supply / max(dawn_demand, 0.01), 3),
            'night_supply': round(night_supply, 2),
            'night_demand': round(night_demand, 2),
            'night_ratio': round(night_supply / max(night_demand, 0.01), 3),
        }

        if detail:
            print(f"\n{p['name']}: Supply peak={supply_peak_hr}:00, "
                  f"Demand peak={demand_peak_hr}:00, Lag={peak_lag_hr}h")
            print(f"  Dawn (4-7): supply={dawn_supply:.2f}, demand={dawn_demand:.2f}, "
                  f"ratio={dawn_supply/max(dawn_demand,0.01):.2f}")
            print(f"  Night (0-4): supply={night_supply:.2f}, demand={night_demand:.2f}, "
                  f"ratio={night_supply/max(night_demand,0.01):.2f}")

    return results


# ── EXP-465: Schedule Concordance ─────────────────────────────────────────

def run_exp465(patients, detail=False):
    """Measure whether basal, CR, and ISF schedules move concordantly.

    The user's hypothesis:
    - Basal ↑ when EGP ↑ → should correlate with CR schedule changes
    - ISF ↓ when resistance ↑ → ISF dips should coincide with basal peaks
    - All three encode aspects of the same circadian physiology

    We measure:
    1. Pearson correlation between expanded schedule curves
    2. Whether schedules are flat (no circadian modeling) vs multi-segment
    3. Concordance index: do all schedules change at similar times of day?
    """
    results = {}

    for p in patients:
        df = p['df']
        N = len(df)
        if not hasattr(df.index, 'hour'):
            continue

        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])
        cr_sched = df.attrs.get('cr_schedule', [])

        # Expand all three schedules
        basal_curve = expand_schedule(df.index, basal_sched, default=0.5)[:N]
        isf_curve = expand_schedule(df.index, isf_sched, default=40.0)[:N]
        cr_curve = expand_schedule(df.index, cr_sched, default=10.0)[:N]

        # Handle mmol/L ISF
        if np.median(isf_curve) < 15:
            isf_curve = isf_curve * 18.0182

        # Count schedule segments
        n_basal_segs = len(basal_sched)
        n_isf_segs = len(isf_sched)
        n_cr_segs = len(cr_sched)

        # Compute correlations (hourly averages to remove noise)
        hours = df.index.hour
        basal_hourly = [np.mean(basal_curve[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)]
        isf_hourly = [np.mean(isf_curve[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)]
        cr_hourly = [np.mean(cr_curve[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)]

        basal_h = np.array(basal_hourly)
        isf_h = np.array(isf_hourly)
        cr_h = np.array(cr_hourly)

        # Expected: basal ↑ when ISF ↓ (anti-correlated) — more resistance = more basal
        # Expected: basal ↑ when CR ↑ (correlated) — more EGP = more insulin needed
        # Expected: ISF ↓ when CR ↑ (anti-correlated) — resistance = less sensitive + more carbs needed

        def safe_corr(a, b):
            if np.std(a) < 1e-10 or np.std(b) < 1e-10:
                return 0.0
            return float(np.corrcoef(a, b)[0, 1])

        r_basal_isf = safe_corr(basal_h, isf_h)
        r_basal_cr = safe_corr(basal_h, cr_h)
        r_isf_cr = safe_corr(isf_h, cr_h)

        # Compute schedule ranges (circadian amplitude)
        basal_range = float(np.max(basal_curve) - np.min(basal_curve))
        isf_range = float(np.max(isf_curve) - np.min(isf_curve))
        cr_range = float(np.max(cr_curve) - np.min(cr_curve))

        # Relative variation (coefficient of variation)
        basal_cv = float(np.std(basal_curve) / max(np.mean(basal_curve), 0.01))
        isf_cv = float(np.std(isf_curve) / max(np.mean(isf_curve), 0.01))
        cr_cv = float(np.std(cr_curve) / max(np.mean(cr_curve), 0.01))

        results[p['name']] = {
            'schedule_segments': {
                'basal': n_basal_segs,
                'isf': n_isf_segs,
                'cr': n_cr_segs,
            },
            'correlations': {
                'basal_vs_isf': round(r_basal_isf, 3),
                'basal_vs_cr': round(r_basal_cr, 3),
                'isf_vs_cr': round(r_isf_cr, 3),
            },
            'expected_signs': {
                'basal_vs_isf_expected_negative': r_basal_isf < 0,
                'basal_vs_cr_expected_positive': r_basal_cr > 0,
                'isf_vs_cr_expected_negative': r_isf_cr < 0,
            },
            'circadian_amplitude': {
                'basal_range_U_hr': round(basal_range, 3),
                'isf_range_mgdL_U': round(isf_range, 1),
                'cr_range_g_U': round(cr_range, 1),
            },
            'coefficient_of_variation': {
                'basal_cv': round(basal_cv, 3),
                'isf_cv': round(isf_cv, 3),
                'cr_cv': round(cr_cv, 3),
            },
        }

        if detail:
            print(f"\n{p['name']}: segs=[basal:{n_basal_segs}, ISF:{n_isf_segs}, CR:{n_cr_segs}]")
            print(f"  r(basal,ISF)={r_basal_isf:+.3f} (expect −)")
            print(f"  r(basal,CR)={r_basal_cr:+.3f} (expect +)")
            print(f"  r(ISF,CR)={r_isf_cr:+.3f} (expect −)")
            print(f"  CV: basal={basal_cv:.3f}, ISF={isf_cv:.3f}, CR={cr_cv:.3f}")

    return results


# ── EXP-466: Meal Phase Lag ───────────────────────────────────────────────

def run_exp466(patients, detail=False):
    """Measure the supply→demand phase lag around meals.

    At a meal, carb absorption starts immediately → supply rises.
    Insulin bolus → demand rises ~15-30 min later (insulin onset).
    For UAM meals (no bolus), demand rises ~60-90 min later (AID reaction).

    This phase lag is a fundamental signature of the insulin-carb interaction.
    """
    from scipy.signal import find_peaks

    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        if not hasattr(df.index, 'hour'):
            continue

        # Find supply peaks (potential meals)
        carb_supply = sd['carb_supply']
        supply_smooth = pd.Series(carb_supply).rolling(6, center=True, min_periods=1).mean().values
        threshold = np.percentile(supply_smooth[supply_smooth > 0], 75)

        peaks, props = find_peaks(supply_smooth, height=threshold,
                                  distance=12, prominence=threshold * 0.5)

        if len(peaks) < 3:
            results[p['name']] = {'n_meals': len(peaks), 'lag_minutes': None}
            continue

        # For each supply peak, find the nearest demand peak within ±2 hours
        demand_smooth = pd.Series(sd['demand']).rolling(6, center=True, min_periods=1).mean().values
        demand_thresh = np.percentile(demand_smooth[demand_smooth > 0], 50)
        demand_peaks, _ = find_peaks(demand_smooth, height=demand_thresh,
                                     distance=6, prominence=demand_thresh * 0.3)

        lags = []
        for sp in peaks:
            # Find closest demand peak AFTER supply peak
            after = demand_peaks[demand_peaks > sp]
            if len(after) > 0:
                nearest = after[0]
                lag_steps = nearest - sp
                if lag_steps <= 24:  # within 2 hours
                    lags.append(int(lag_steps) * 5)  # convert to minutes

        if lags:
            lag_arr = np.array(lags)
            results[p['name']] = {
                'n_meals_detected': len(peaks),
                'n_with_demand_response': len(lags),
                'lag_minutes_mean': round(float(np.mean(lag_arr)), 1),
                'lag_minutes_median': round(float(np.median(lag_arr)), 1),
                'lag_minutes_std': round(float(np.std(lag_arr)), 1),
                'lag_minutes_p25': round(float(np.percentile(lag_arr, 25)), 1),
                'lag_minutes_p75': round(float(np.percentile(lag_arr, 75)), 1),
            }
        else:
            results[p['name']] = {
                'n_meals_detected': len(peaks),
                'n_with_demand_response': 0,
                'lag_minutes': None,
            }

        if detail and lags:
            r = results[p['name']]
            print(f"\n{p['name']}: {r['n_meals_detected']} meals, "
                  f"{r['n_with_demand_response']} with response, "
                  f"lag={r['lag_minutes_median']:.0f}min (IQR {r['lag_minutes_p25']:.0f}-{r['lag_minutes_p75']:.0f})")

    return results


# ── EXP-467: Schedule-Hepatic Alignment ───────────────────────────────────

def run_exp467(patients, detail=False):
    """Test if patient's basal schedule correlates with our hepatic model.

    The user's key insight: basal rate IS the clinical proxy for EGP.
    When a clinician sets higher basal at 4-7 AM, they're compensating for
    the dawn phenomenon = increased hepatic glucose production.

    If our hepatic model (Hill equation + circadian) is correct, it should
    correlate with the patient's basal schedule — they're modeling the same
    underlying phenomenon from different angles.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        if not hasattr(df.index, 'hour'):
            continue

        basal_sched = df.attrs.get('basal_schedule', [])
        N = len(df)
        basal_curve = expand_schedule(df.index, basal_sched, default=0.5)[:N]
        hepatic = sd['hepatic']

        hours = df.index.hour

        # Hourly averages
        basal_hourly = np.array([np.mean(basal_curve[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)])
        hepatic_hourly = np.array([np.mean(hepatic[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)])

        # Correlation
        if np.std(basal_hourly) < 1e-10 or np.std(hepatic_hourly) < 1e-10:
            corr = 0.0
        else:
            corr = float(np.corrcoef(basal_hourly, hepatic_hourly)[0, 1])

        # Scale comparison: basal U/hr → demand mg/dL/step vs hepatic mg/dL/step
        isf_sched = df.attrs.get('isf_schedule', [])
        isf_curve = expand_schedule(df.index, isf_sched, default=40.0)[:N]
        if np.median(isf_curve) < 15:
            isf_curve = isf_curve * 18.0182
        basal_as_demand = basal_curve * (5.0 / 60.0) * isf_curve  # U/hr → U/5min → mg/dL/5min

        basal_demand_hourly = np.array([np.mean(basal_as_demand[hours == h]) if (hours == h).sum() > 0 else 0 for h in range(24)])

        # Ratio: how much of basal demand is explained by hepatic production?
        hepatic_basal_ratio = np.mean(hepatic) / max(np.mean(basal_as_demand), 0.01)

        results[p['name']] = {
            'basal_hepatic_corr': round(corr, 3),
            'hepatic_mean_mgdl_5min': round(float(np.mean(hepatic)), 3),
            'basal_demand_mean_mgdl_5min': round(float(np.mean(basal_as_demand)), 3),
            'hepatic_to_basal_ratio': round(hepatic_basal_ratio, 3),
            'basal_schedule_segments': len(basal_sched),
            'basal_peak_hour': int(np.argmax(basal_hourly)),
            'hepatic_peak_hour': int(np.argmax(hepatic_hourly)),
        }

        if detail:
            r = results[p['name']]
            print(f"\n{p['name']}: r(basal,hepatic)={corr:+.3f}, "
                  f"hepatic/basal_demand={hepatic_basal_ratio:.2f}")
            print(f"  Basal peak={r['basal_peak_hour']}:00, "
                  f"Hepatic peak={r['hepatic_peak_hour']}:00")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-464–467: Phase relationship experiments')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--quick', action='store_true', help='Only load 3 patients')
    parser.add_argument('--detail', action='store_true', help='Verbose per-patient output')
    parser.add_argument('--save', action='store_true', help='Save results JSON')
    parser.add_argument('--exp', type=str, default='all',
                        help='Run specific experiment (464,465,466,467) or all')
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    max_patients = 3 if args.quick else None
    patients = load_patients(str(patients_dir), max_patients=max_patients)
    print(f"Loaded {len(patients)} patients")

    all_results = {}
    exps = args.exp.split(',') if args.exp != 'all' else ['464', '465', '466', '467']

    if '464' in exps:
        print("\n═══ EXP-464: 24h Phase Portrait ═══")
        r464 = run_exp464(patients, detail=args.detail)
        all_results['exp464_phase_portrait'] = r464

        # Summary
        lags = [v['supply_demand_lag_hours'] for v in r464.values()]
        dawn_ratios = [v['dawn_ratio'] for v in r464.values()]
        print(f"\nSupply→demand lag: median {np.median(lags):.0f}h "
              f"(range {min(lags)}-{max(lags)})")
        print(f"Dawn ratio (supply/demand): mean {np.mean(dawn_ratios):.2f} "
              f"(>1 = BG rising at dawn)")

    if '465' in exps:
        print("\n═══ EXP-465: Schedule Concordance ═══")
        r465 = run_exp465(patients, detail=args.detail)
        all_results['exp465_schedule_concordance'] = r465

        # Summary: How many patients have expected correlation signs?
        n_correct_basal_isf = sum(1 for v in r465.values()
                                  if v['expected_signs']['basal_vs_isf_expected_negative'])
        n_correct_basal_cr = sum(1 for v in r465.values()
                                 if v['expected_signs']['basal_vs_cr_expected_positive'])
        n_correct_isf_cr = sum(1 for v in r465.values()
                               if v['expected_signs']['isf_vs_cr_expected_negative'])
        n = len(r465)
        print(f"\nExpected correlation signs:")
        print(f"  r(basal,ISF) < 0: {n_correct_basal_isf}/{n}")
        print(f"  r(basal,CR) > 0:  {n_correct_basal_cr}/{n}")
        print(f"  r(ISF,CR) < 0:    {n_correct_isf_cr}/{n}")

    if '466' in exps:
        print("\n═══ EXP-466: Meal Phase Lag ═══")
        r466 = run_exp466(patients, detail=args.detail)
        all_results['exp466_meal_phase_lag'] = r466

        # Summary
        median_lags = [v['lag_minutes_median'] for v in r466.values()
                       if v.get('lag_minutes_median') is not None]
        if median_lags:
            print(f"\nMedian meal phase lag: {np.median(median_lags):.0f} min "
                  f"(range {min(median_lags):.0f}-{max(median_lags):.0f})")

    if '467' in exps:
        print("\n═══ EXP-467: Schedule-Hepatic Alignment ═══")
        r467 = run_exp467(patients, detail=args.detail)
        all_results['exp467_schedule_hepatic'] = r467

        # Summary
        corrs = [v['basal_hepatic_corr'] for v in r467.values()]
        ratios = [v['hepatic_to_basal_ratio'] for v in r467.values()]
        print(f"\nBasal↔hepatic correlation: mean {np.mean(corrs):+.3f} "
              f"(range {min(corrs):+.3f} to {max(corrs):+.3f})")
        print(f"Hepatic/basal demand ratio: mean {np.mean(ratios):.2f} "
              f"(1.0 = hepatic model matches basal profile)")

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
