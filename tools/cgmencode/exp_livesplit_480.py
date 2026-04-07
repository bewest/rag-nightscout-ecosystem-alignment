#!/usr/bin/env python3
"""EXP-480–482: Live-split validation of non-bolusing meal detection.

Tests metabolic flux meal detection on live-split data — a near-100% UAM
patient (only 7 correction boluses and 3 carb corrections in 58 days).
The user reports this patient eats ~2 meals/day (lunch + dinner) plus
occasional dessert.

This is the acid test: can our physics-based decomposition detect meals
from AID temp-basal reactions alone, with essentially zero carb/bolus data?

EXP-480: Load live-split data into our pipeline and characterize
EXP-481: Apply all 4 meal detection methods and compare
EXP-482: Unified detector combining residual + demand + glucose_deriv

Data format: Raw Nightscout JSON (entries.json, treatments.json,
devicestatus.json, profile.json) — requires adapter to DataFrame.

References:
  - exp_nonbolus_476.py: EXP-476–479 non-bolusing detection methods
  - exp_metabolic_441.py: compute_supply_demand()
  - continuous_pk.py: build_continuous_pk_features()
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from cgmencode.continuous_pk import (
    build_continuous_pk_features,
    expand_schedule,
    compute_hepatic_production,
    PK_NORMALIZATION,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand

LIVE_SPLIT_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'live-split'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── Data Adapter ──────────────────────────────────────────────────────────

def load_live_split(split_dir, subset='training'):
    """Load live-split Nightscout data into DataFrame + PK array.

    Adapts raw Nightscout JSON format to the DataFrame structure expected
    by our experiment pipeline.
    """
    base = Path(split_dir) / subset

    # Load entries (CGM readings)
    with open(base / 'entries.json') as f:
        entries = json.load(f)

    # Load treatments (temp basals, boluses, carbs)
    with open(base / 'treatments.json') as f:
        treatments = json.load(f)

    # Load profile
    profile_path = base / 'profile.json'
    with open(profile_path) as f:
        profile_data = json.load(f)

    if isinstance(profile_data, list):
        profile_data = profile_data[0] if profile_data else {}

    store = profile_data.get('store', {})
    default_profile = next(iter(store.values())) if store else {}

    basal_sched = default_profile.get('basal', [])
    isf_sched = default_profile.get('sens', default_profile.get('sensitivity', []))
    cr_sched = default_profile.get('carbratio', [])
    dia = default_profile.get('dia', 6.0)
    units = default_profile.get('units', 'mg/dL')

    # Build entries DataFrame
    entry_records = []
    for e in entries:
        if e.get('type') != 'sgv':
            continue
        ts = e.get('dateString', e.get('sysTime'))
        if not ts:
            continue
        sgv = e.get('sgv', 0)
        if sgv <= 0:
            continue
        entry_records.append({
            'timestamp': pd.Timestamp(ts),
            'glucose': float(sgv),
            'direction': e.get('direction', 'NONE'),
        })

    if not entry_records:
        raise ValueError("No SGV entries found")

    df_entries = pd.DataFrame(entry_records)
    df_entries = df_entries.sort_values('timestamp').drop_duplicates('timestamp')
    df_entries = df_entries.set_index('timestamp')

    # Resample to 5-min grid
    start = df_entries.index.min().floor('5min')
    end = df_entries.index.max().ceil('5min')
    grid = pd.date_range(start, end, freq='5min')
    df = pd.DataFrame(index=grid)
    df['glucose'] = df_entries['glucose'].reindex(grid, method='nearest', tolerance='5min')
    df['direction'] = df_entries['direction'].reindex(grid, method='nearest', tolerance='5min')
    df['glucose'] = df['glucose'].ffill(limit=3)

    # Process treatments
    bolus_series = pd.Series(0.0, index=grid)
    carbs_series = pd.Series(0.0, index=grid)
    temp_rate_series = pd.Series(0.0, index=grid)
    iob_series = pd.Series(0.0, index=grid)
    cob_series = pd.Series(0.0, index=grid)

    for t in treatments:
        ts_str = t.get('created_at', t.get('timestamp'))
        if not ts_str:
            continue
        try:
            ts = pd.Timestamp(ts_str)
        except Exception:
            continue

        nearest_idx = grid.searchsorted(ts)
        if nearest_idx >= len(grid):
            nearest_idx = len(grid) - 1

        event_type = t.get('eventType', '')

        if 'Bolus' in event_type or 'bolus' in event_type:
            amt = t.get('insulin', t.get('amount', 0))
            if amt and float(amt) > 0:
                bolus_series.iloc[nearest_idx] += float(amt)

        if 'Carb' in event_type or (t.get('carbs') or 0) > 0:
            carbs_val = t.get('carbs') or 0
            if carbs_val and float(carbs_val) > 0:
                carbs_series.iloc[nearest_idx] += float(carbs_val)

        if event_type == 'Temp Basal':
            rate = t.get('rate', 0)
            duration_min = t.get('duration', 30)
            if rate is not None:
                # Fill temp rate for duration
                n_steps = int(float(duration_min) / 5)
                for s in range(n_steps):
                    idx = nearest_idx + s
                    if idx < len(grid):
                        temp_rate_series.iloc[idx] = float(rate)

    df['bolus'] = bolus_series
    df['carbs'] = carbs_series
    df['temp_rate'] = temp_rate_series
    df['iob'] = iob_series
    df['cob'] = cob_series

    # Compute simple IOB from boluses + temp basals
    # Approximate: IOB decays with DIA curve (simplified exponential)
    dia_steps = int(dia * 60 / 5)
    insulin_events = df['bolus'].values + df['temp_rate'].values * (5.0 / 60.0)
    iob_computed = np.zeros(len(df))
    for i in range(len(df)):
        if insulin_events[i] > 0:
            # Distribute over DIA with peak at 75 min
            for j in range(min(dia_steps, len(df) - i)):
                t_min = j * 5
                # Simplified Fiasp-like curve
                fraction = max(0, 1.0 - t_min / (dia * 60))
                iob_computed[i + j] += insulin_events[i] * fraction

    df['iob'] = iob_computed

    # Store profile info as attrs
    df.attrs['basal_schedule'] = basal_sched
    df.attrs['isf_schedule'] = isf_sched
    df.attrs['cr_schedule'] = cr_sched
    df.attrs['dia'] = dia
    df.attrs['units'] = units
    df.attrs['profile_units'] = units

    # Build PK features
    pk = build_continuous_pk_features(df)

    return df, pk


# ── EXP-480: Characterize Live-Split Data ─────────────────────────────────

def run_exp480(df, pk, detail=False):
    """Characterize the live-split patient's data and bolusing style."""
    N = len(df)
    total_days = N / 288

    bolus = df['bolus'].values
    carbs = df['carbs'].values
    temp_rate = df['temp_rate'].values

    n_bolus = np.sum(bolus > 0.1)
    n_carbs = np.sum(carbs > 0)
    n_temp = np.sum(np.diff(temp_rate) != 0)  # temp rate changes

    # Glucose stats
    bg = df['glucose'].values
    valid_bg = bg[~np.isnan(bg)]

    results = {
        'total_days': round(total_days, 1),
        'total_steps': N,
        'glucose_coverage': round(len(valid_bg) / N, 3),
        'glucose_mean': round(float(np.nanmean(bg)), 1),
        'glucose_std': round(float(np.nanstd(bg)), 1),
        'tir_70_180': round(float(np.mean((valid_bg >= 70) & (valid_bg <= 180))), 3),
        'boluses_total': int(n_bolus),
        'boluses_per_day': round(n_bolus / total_days, 2),
        'carb_entries_total': int(n_carbs),
        'carb_entries_per_day': round(n_carbs / total_days, 2),
        'temp_rate_changes_per_day': round(n_temp / total_days, 1),
        'mean_temp_rate': round(float(np.mean(temp_rate[temp_rate > 0])), 2) if np.sum(temp_rate > 0) > 0 else 0,
        'basal_schedule': df.attrs.get('basal_schedule', []),
        'isf': df.attrs.get('isf_schedule', []),
        'cr': df.attrs.get('cr_schedule', []),
    }

    if detail:
        print(f"  Days: {results['total_days']:.1f}, Coverage: {results['glucose_coverage']:.0%}")
        print(f"  Glucose: {results['glucose_mean']:.0f} ± {results['glucose_std']:.0f} mg/dL, "
              f"TIR: {results['tir_70_180']:.0%}")
        print(f"  Boluses: {results['boluses_total']} ({results['boluses_per_day']:.2f}/day)")
        print(f"  Carb entries: {results['carb_entries_total']} ({results['carb_entries_per_day']:.2f}/day)")
        print(f"  Temp rate changes: {results['temp_rate_changes_per_day']:.0f}/day")

    return results


# ── EXP-481: All 4 Meal Detection Methods ─────────────────────────────────

def run_exp481(df, pk, detail=False):
    """Apply all 4 detection methods to live-split data.

    Expected: ~2 meals/day (lunch + dinner), sometimes dessert.
    """
    sd = compute_supply_demand(df, pk)
    N = len(df)
    total_days = max(N / 288, 1)

    bg_col = 'glucose'
    bg = df[bg_col].values.astype(np.float64)
    dbg = np.zeros_like(bg)
    valid = ~np.isnan(bg)
    dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)

    methods = {}

    # Method 1: Sum flux
    sf = sd['sum_flux']
    sf_sm = pd.Series(sf).rolling(6, center=True, min_periods=1).mean().values
    sf_thresh = np.percentile(sf_sm[sf_sm > 0], 50) if np.sum(sf_sm > 0) > 100 else 1.0
    sf_peaks, _ = find_peaks(sf_sm, height=sf_thresh, distance=12, prominence=sf_thresh * 0.3)
    methods['sum_flux'] = {'peaks': sf_peaks, 'per_day': round(len(sf_peaks) / total_days, 1)}

    # Method 2: Demand only
    dem = sd['demand']
    dem_sm = pd.Series(dem).rolling(6, center=True, min_periods=1).mean().values
    dem_thresh = np.percentile(dem_sm[dem_sm > 0], 60) if np.sum(dem_sm > 0) > 100 else 1.0
    dem_peaks, _ = find_peaks(dem_sm, height=dem_thresh, distance=12, prominence=dem_thresh * 0.3)
    methods['demand_only'] = {'peaks': dem_peaks, 'per_day': round(len(dem_peaks) / total_days, 1)}

    # Method 3: Residual (unmodeled supply)
    predicted_dbg = sd['supply'] - sd['demand']
    residual = dbg - predicted_dbg
    resid_sm = pd.Series(np.maximum(residual, 0)).rolling(6, center=True, min_periods=1).mean().values
    res_thresh = np.percentile(resid_sm[resid_sm > 0], 70) if np.sum(resid_sm > 0) > 100 else 1.0
    res_peaks, _ = find_peaks(resid_sm, height=res_thresh, distance=12, prominence=res_thresh * 0.3)
    methods['residual'] = {'peaks': res_peaks, 'per_day': round(len(res_peaks) / total_days, 1)}

    # Method 4: Glucose derivative
    dbg_sm = pd.Series(np.maximum(dbg, 0)).rolling(6, center=True, min_periods=1).mean().values
    gd_thresh = np.percentile(dbg_sm[dbg_sm > 0], 70) if np.sum(dbg_sm > 0) > 100 else 1.0
    gd_peaks, _ = find_peaks(dbg_sm, height=gd_thresh, distance=12, prominence=gd_thresh * 0.3)
    methods['glucose_deriv'] = {'peaks': gd_peaks, 'per_day': round(len(gd_peaks) / total_days, 1)}

    # Method 5: Unified — vote across residual + demand + glucose_deriv
    # A "meal" is detected if ≥2 of 3 methods have a peak within ±1 hour
    all_candidate_peaks = set()
    for m in ['residual', 'demand_only', 'glucose_deriv']:
        for p in methods[m]['peaks']:
            all_candidate_peaks.add(p)

    unified_peaks = []
    for cp in sorted(all_candidate_peaks):
        votes = 0
        for m in ['residual', 'demand_only', 'glucose_deriv']:
            dists = np.abs(methods[m]['peaks'] - cp) if len(methods[m]['peaks']) > 0 else np.array([999])
            if np.min(dists) <= 12:  # within 1 hour
                votes += 1
        if votes >= 2:
            # Deduplicate: only keep if not too close to previous
            if not unified_peaks or (cp - unified_peaks[-1]) > 12:
                unified_peaks.append(cp)

    methods['unified_2of3'] = {'peaks': np.array(unified_peaks), 'per_day': round(len(unified_peaks) / total_days, 1)}

    # Daily breakdown
    if hasattr(df.index, 'date'):
        dates = df.index.date
        unique_dates = sorted(set(dates))
        daily_counts = {}
        for method_name, method_data in methods.items():
            daily = []
            for d in unique_dates:
                day_start = np.searchsorted(dates, d)
                day_end = np.searchsorted(dates, d, side='right')
                day_peaks = [p for p in method_data['peaks'] if day_start <= p < day_end]
                daily.append(len(day_peaks))
            daily_counts[method_name] = daily
            method_data['daily_mean'] = round(float(np.mean(daily)), 2)
            method_data['daily_std'] = round(float(np.std(daily)), 2)
            method_data['daily_median'] = round(float(np.median(daily)), 1)
            method_data['days_with_2_plus'] = int(sum(1 for d in daily if d >= 2))
            method_data['days_with_exactly_2'] = int(sum(1 for d in daily if d == 2))
            method_data['days_with_3_plus'] = int(sum(1 for d in daily if d >= 3))

        # Hour-of-day distribution for unified detector
        hours_detected = []
        for p in unified_peaks:
            if p < len(df.index) and hasattr(df.index[p], 'hour'):
                hours_detected.append(df.index[p].hour)

        if hours_detected:
            from collections import Counter
            hour_counts = Counter(hours_detected)
            methods['unified_2of3']['hour_distribution'] = dict(sorted(hour_counts.items()))

    results = {}
    for name, data in methods.items():
        r = {k: v for k, v in data.items() if k != 'peaks'}
        r['total_peaks'] = len(data['peaks'])
        results[name] = r

    if detail:
        n_days = len(unique_dates) if hasattr(df.index, 'date') else total_days
        for name, r in results.items():
            print(f"\n  {name}:")
            print(f"    Events/day: {r.get('daily_mean', r['per_day']):.1f} ± "
                  f"{r.get('daily_std', 0):.1f} (median {r.get('daily_median', 'N/A')})")
            if 'days_with_2_plus' in r:
                print(f"    Days with ≥2: {r['days_with_2_plus']}/{int(n_days)} "
                      f"({r['days_with_2_plus']/max(n_days,1):.0%})")
            if 'hour_distribution' in r:
                print(f"    Peak hours: {r['hour_distribution']}")

    return results, methods


# ── EXP-482: Unified Detector Deep Dive ───────────────────────────────────

def run_exp482(df, pk, methods, detail=False):
    """Analyze the unified detector's daily meal tally vs expected 2-3/day.

    Deep dive: per-day breakdown, timing patterns, and signal quality.
    """
    N = len(df)
    unified = methods['unified_2of3']
    peaks = unified['peaks']

    if not hasattr(df.index, 'date'):
        return {}

    dates = df.index.date
    unique_dates = sorted(set(dates))

    bg = df['glucose'].values.astype(np.float64)
    sd = compute_supply_demand(df, pk)

    daily_detail = []
    for d in unique_dates:
        day_start = np.searchsorted(dates, d)
        day_end = np.searchsorted(dates, d, side='right')
        day_peaks = [p for p in peaks if day_start <= p < day_end]

        day_info = {
            'date': str(d),
            'n_meals': len(day_peaks),
            'meal_times': [],
            'glucose_at_meal': [],
            'demand_at_meal': [],
        }

        for p in day_peaks:
            if p < len(df.index):
                hour = df.index[p].hour + df.index[p].minute / 60.0
                day_info['meal_times'].append(round(hour, 1))
                if not np.isnan(bg[p]):
                    day_info['glucose_at_meal'].append(round(float(bg[p]), 0))
                day_info['demand_at_meal'].append(round(float(sd['demand'][p]), 2))

        daily_detail.append(day_info)

    # Statistics
    meal_counts = [d['n_meals'] for d in daily_detail]
    all_times = []
    for d in daily_detail:
        all_times.extend(d['meal_times'])

    results = {
        'n_days': len(unique_dates),
        'meals_per_day_mean': round(float(np.mean(meal_counts)), 2),
        'meals_per_day_median': round(float(np.median(meal_counts)), 1),
        'meals_per_day_std': round(float(np.std(meal_counts)), 2),
        'days_with_0': int(sum(1 for c in meal_counts if c == 0)),
        'days_with_1': int(sum(1 for c in meal_counts if c == 1)),
        'days_with_2': int(sum(1 for c in meal_counts if c == 2)),
        'days_with_3': int(sum(1 for c in meal_counts if c == 3)),
        'days_with_4plus': int(sum(1 for c in meal_counts if c >= 4)),
    }

    if all_times:
        # Cluster meal times to find typical lunch/dinner/dessert
        times_arr = np.array(all_times)
        results['meal_time_mean'] = round(float(np.mean(times_arr)), 1)
        results['meal_time_std'] = round(float(np.std(times_arr)), 1)

        # Typical meal windows
        lunch_window = (11, 14)
        dinner_window = (17, 21)
        dessert_window = (21, 23.5)

        n_lunch = int(np.sum((times_arr >= lunch_window[0]) & (times_arr < lunch_window[1])))
        n_dinner = int(np.sum((times_arr >= dinner_window[0]) & (times_arr < dinner_window[1])))
        n_dessert = int(np.sum((times_arr >= dessert_window[0]) & (times_arr < dessert_window[1])))
        n_breakfast = int(np.sum((times_arr >= 6) & (times_arr < 11)))
        n_other = len(times_arr) - n_lunch - n_dinner - n_dessert - n_breakfast

        results['timing'] = {
            'breakfast_6_11': n_breakfast,
            'lunch_11_14': n_lunch,
            'dinner_17_21': n_dinner,
            'dessert_21_23': n_dessert,
            'other': n_other,
            'total': len(times_arr),
        }

        results['timing_per_day'] = {
            'breakfast': round(n_breakfast / len(unique_dates), 2),
            'lunch': round(n_lunch / len(unique_dates), 2),
            'dinner': round(n_dinner / len(unique_dates), 2),
            'dessert': round(n_dessert / len(unique_dates), 2),
        }

    if detail:
        print(f"\n  Meals/day: {results['meals_per_day_mean']:.1f} ± "
              f"{results['meals_per_day_std']:.1f} "
              f"(median {results['meals_per_day_median']:.0f})")
        print(f"  Distribution: 0={results['days_with_0']}, 1={results['days_with_1']}, "
              f"2={results['days_with_2']}, 3={results['days_with_3']}, "
              f"4+={results['days_with_4plus']}")
        if 'timing_per_day' in results:
            t = results['timing_per_day']
            print(f"  Per day: breakfast={t['breakfast']:.1f}, lunch={t['lunch']:.1f}, "
                  f"dinner={t['dinner']:.1f}, dessert={t['dessert']:.1f}")

        # Show a sample week
        print(f"\n  Sample week:")
        for d in daily_detail[:7]:
            times_str = ', '.join(f"{t:.0f}:00" for t in d['meal_times'])
            print(f"    {d['date']}: {d['n_meals']} meals — [{times_str}]")

    results['daily_detail'] = daily_detail
    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-480–482: Live-split non-bolusing validation')
    parser.add_argument('--split-dir', type=str, default=None)
    parser.add_argument('--subset', type=str, default='training',
                        choices=['training', 'verification'])
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()

    split_dir = Path(args.split_dir) if args.split_dir else LIVE_SPLIT_DIR
    print(f"Loading {args.subset} data from {split_dir}...")

    df, pk = load_live_split(split_dir, subset=args.subset)
    print(f"  Loaded: {len(df)} steps ({len(df)/288:.1f} days)")

    all_results = {}

    print("\n═══ EXP-480: Data Characterization ═══")
    r480 = run_exp480(df, pk, detail=args.detail)
    all_results['exp480_live_characterize'] = r480

    print("\n═══ EXP-481: Meal Detection Methods ═══")
    r481, methods = run_exp481(df, pk, detail=args.detail)
    all_results['exp481_live_meal_detection'] = r481

    print("\n═══ EXP-482: Unified Detector Deep Dive ═══")
    r482 = run_exp482(df, pk, methods, detail=args.detail)
    all_results['exp482_live_unified'] = r482

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
