#!/usr/bin/env python3
"""EXP-497/498/496: Device Age Effects and CR Fidelity.

EXP-497: Sensor age effect on residual magnitude and noise
EXP-498: Cannula/site age effect on insulin delivery fidelity
EXP-496: CR fidelity — post-meal glucose excursion vs configured CR

These experiments test whether device degradation (sensor drift, cannula
occlusion) is visible in the metabolic flux residuals, and whether carb
ratio settings match observed meal responses.

References:
  - exp_settings_489.py: Basal adequacy, fidelity score
  - exp_metabolic_441.py: compute_supply_demand()
  - continuous_pk.py: expand_schedule(), PK_NORMALIZATION
"""

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.continuous_pk import expand_schedule
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


def _dedup_timestamps(timestamps, min_gap_hours=6):
    """Deduplicate timestamps that are within min_gap_hours of each other."""
    if not timestamps:
        return []
    sorted_ts = sorted(timestamps)
    unique = [sorted_ts[0]]
    for ts in sorted_ts[1:]:
        if (ts - unique[-1]).total_seconds() > min_gap_hours * 3600:
            unique.append(ts)
    return unique


def _compute_sensor_age_hours(index, sensor_starts):
    """For each timestep, compute hours since last sensor insertion."""
    age = np.full(len(index), np.nan)
    starts = _dedup_timestamps(sensor_starts, min_gap_hours=6)
    if not starts:
        return age

    for i, ts in enumerate(index):
        # Find most recent sensor start before this timestamp
        best = None
        for s in starts:
            if s <= ts:
                best = s
            else:
                break
        if best is not None:
            age[i] = (ts - best).total_seconds() / 3600
    return age


def _compute_site_age_hours(index, site_changes):
    """For each timestep, compute hours since last site/cannula change."""
    age = np.full(len(index), np.nan)
    changes = _dedup_timestamps(site_changes, min_gap_hours=6)
    if not changes:
        return age

    for i, ts in enumerate(index):
        best = None
        for s in changes:
            if s <= ts:
                best = s
            else:
                break
        if best is not None:
            age[i] = (ts - best).total_seconds() / 3600
    return age


# ── EXP-497: Sensor Age Effect ──────────────────────────────────────────

def run_exp497(patients, detail=False):
    """Analyze how sensor age affects residual noise and BG variability.

    Theory: CGM sensors degrade over their 10-day life. Early readings may
    be noisy (warmup), middle readings most accurate, late readings may drift.
    This should appear as increased residual magnitude at sensor edges.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        sensor_starts = df.attrs.get('sensor_start_times', [])
        if not sensor_starts:
            results[p['name']] = {'error': 'no sensor start data'}
            continue

        sd = compute_supply_demand(df, pk)
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)

        net_flux = sd['supply'] - sd['demand']
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        residual = dbg - net_flux

        # Compute sensor age at each timestep
        sensor_age_h = _compute_sensor_age_hours(df.index, sensor_starts)
        has_age = ~np.isnan(sensor_age_h) & valid

        if has_age.sum() < 1000:
            results[p['name']] = {'error': 'insufficient sensor age data'}
            continue

        # Bin by sensor age: day 0-1, 1-2, 2-3, ..., 9-10
        age_bins = {}
        for day in range(10):
            lo, hi = day * 24, (day + 1) * 24
            mask = has_age & (sensor_age_h >= lo) & (sensor_age_h < hi)
            n = mask.sum()
            if n < 100:
                continue
            resid_abs = np.abs(residual[mask])
            bg_std = np.nanstd(bg[mask])
            age_bins[f'day_{day}'] = {
                'n_points': int(n),
                'residual_mae': round(float(np.mean(resid_abs)), 3),
                'residual_std': round(float(np.std(resid_abs)), 3),
                'bg_std': round(float(bg_std), 1),
                'bg_mean': round(float(np.nanmean(bg[mask])), 1),
            }

        if len(age_bins) < 5:
            results[p['name']] = {'error': 'insufficient age bin coverage', 'bins': len(age_bins)}
            continue

        # Trend: does residual MAE increase with sensor age?
        days = []
        maes = []
        for k, v in sorted(age_bins.items()):
            day_num = int(k.split('_')[1])
            days.append(day_num)
            maes.append(v['residual_mae'])

        if len(days) >= 4:
            slope, intercept, r, pval, se = stats.linregress(days, maes)
            trend = 'degrading' if slope > 0.01 and pval < 0.1 else \
                    ('improving' if slope < -0.01 and pval < 0.1 else 'flat')
        else:
            slope = pval = 0
            trend = 'insufficient'

        # Warmup effect: day 0 vs day 1-3
        warmup_bins = [v['residual_mae'] for k, v in age_bins.items() if k == 'day_0']
        mid_bins = [v['residual_mae'] for k, v in age_bins.items() if k in ('day_1', 'day_2', 'day_3')]
        warmup_excess = (warmup_bins[0] - np.mean(mid_bins)) if warmup_bins and mid_bins else 0

        # Late degradation: day 7-9 vs day 3-6
        late_bins = [v['residual_mae'] for k, v in age_bins.items()
                     if k in ('day_7', 'day_8', 'day_9')]
        stable_bins = [v['residual_mae'] for k, v in age_bins.items()
                       if k in ('day_3', 'day_4', 'day_5', 'day_6')]
        late_excess = (np.mean(late_bins) - np.mean(stable_bins)) if late_bins and stable_bins else 0

        n_sensors = len(_dedup_timestamps(sensor_starts, min_gap_hours=6))
        results[p['name']] = {
            'n_sensors': n_sensors,
            'n_points': int(has_age.sum()),
            'age_bins': age_bins,
            'trend_slope': round(float(slope), 4),
            'trend_pvalue': round(float(pval), 4),
            'trend': trend,
            'warmup_excess': round(float(warmup_excess), 3),
            'late_excess': round(float(late_excess), 3),
        }

        if detail:
            r = results[p['name']]
            print(f"  {p['name']}: {r['n_sensors']} sensors, trend={r['trend']} "
                  f"(slope={r['trend_slope']:+.4f}, p={r['trend_pvalue']:.3f}) "
                  f"warmup={r['warmup_excess']:+.3f} late={r['late_excess']:+.3f}")

    return results


# ── EXP-498: Cannula/Site Age Effect ────────────────────────────────────

def run_exp498(patients, detail=False):
    """Analyze how infusion site age affects insulin delivery fidelity.

    Theory: Cannula sites degrade over 2-3 days. Lipohypertrophy, tissue
    inflammation, or partial occlusion reduces insulin absorption. This
    should appear as increased supply-demand imbalance in later site days.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        site_changes = df.attrs.get('site_change_times', [])
        if not site_changes:
            results[p['name']] = {'error': 'no site change data'}
            continue

        sd = compute_supply_demand(df, pk)
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)

        net_flux = sd['supply'] - sd['demand']
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        residual = dbg - net_flux

        site_age_h = _compute_site_age_hours(df.index, site_changes)
        has_age = ~np.isnan(site_age_h) & valid

        if has_age.sum() < 1000:
            results[p['name']] = {'error': 'insufficient site age data'}
            continue

        # Bin by site age: 0-12h, 12-24h, 24-36h, 36-48h, 48-60h, 60-72h, 72h+
        bin_edges = [0, 12, 24, 36, 48, 60, 72, 9999]
        bin_labels = ['0-12h', '12-24h', '24-36h', '36-48h', '48-60h', '60-72h', '72h+']
        age_bins = {}

        for j in range(len(bin_labels)):
            lo, hi = bin_edges[j], bin_edges[j + 1]
            mask = has_age & (site_age_h >= lo) & (site_age_h < hi)
            n = mask.sum()
            if n < 50:
                continue

            # Supply-demand balance (positive = glucose rising = insulin insufficient)
            mean_flux = float(np.mean(net_flux[mask]))
            # BG stats
            bg_mean = float(np.nanmean(bg[mask]))
            bg_std = float(np.nanstd(bg[mask]))
            # TIR
            bg_valid = bg[mask & valid]
            tir = float(np.mean((bg_valid >= 70) & (bg_valid <= 180))) if len(bg_valid) > 0 else 0
            # Residual
            resid_mae = float(np.mean(np.abs(residual[mask])))

            age_bins[bin_labels[j]] = {
                'n_points': int(n),
                'mean_flux': round(mean_flux, 3),
                'bg_mean': round(bg_mean, 1),
                'bg_std': round(bg_std, 1),
                'tir': round(tir * 100, 1),
                'residual_mae': round(resid_mae, 3),
            }

        if len(age_bins) < 3:
            results[p['name']] = {'error': 'insufficient age bin coverage'}
            continue

        # Trend: does BG rise with site age? (insulin absorption degrades)
        mid_points = []
        bg_means = []
        for label, v in age_bins.items():
            h = (bin_edges[bin_labels.index(label)] + bin_edges[bin_labels.index(label) + 1]) / 2
            if h > 100:
                h = 78  # cap the 72h+ bin
            mid_points.append(h)
            bg_means.append(v['bg_mean'])

        if len(mid_points) >= 3:
            slope, intercept, r, pval, se = stats.linregress(mid_points, bg_means)
            trend = 'degrading' if slope > 0.05 and pval < 0.1 else \
                    ('improving' if slope < -0.05 and pval < 0.1 else 'flat')
        else:
            slope = pval = 0
            trend = 'insufficient'

        n_sites = len(_dedup_timestamps(site_changes, min_gap_hours=6))
        avg_duration = (df.index[-1] - df.index[0]).total_seconds() / 3600 / max(1, n_sites)

        results[p['name']] = {
            'n_site_changes': n_sites,
            'avg_site_hours': round(avg_duration, 1),
            'age_bins': age_bins,
            'bg_trend_slope': round(float(slope), 3),
            'bg_trend_pvalue': round(float(pval), 4),
            'trend': trend,
        }

        if detail:
            r = results[p['name']]
            print(f"  {p['name']}: {r['n_site_changes']} sites (avg {r['avg_site_hours']:.0f}h), "
                  f"trend={r['trend']} (slope={r['bg_trend_slope']:+.3f} mg/dL/h, p={r['bg_trend_pvalue']:.3f})")

    return results


# ── EXP-496: CR Fidelity ────────────────────────────────────────────────

def run_exp496(patients, detail=False):
    """Evaluate carb ratio fidelity from post-meal glucose excursions.

    Methodology: Detect meals via demand peaks starting from euglycemic BG
    (70-160 mg/dL). Measure peak excursion over 2h. Correct CR produces
    moderate excursion (~40-60 mg/dL); too-high CR → large excursion,
    too-low CR → over-correction with possible lows.

    NOTE: In AID systems, CR fidelity is confounded by automated corrections.
    We assess the EXCURSION magnitude, not the return-to-baseline.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        cr_sched = df.attrs.get('cr_schedule', [])

        if cr_sched:
            cr_values = [entry['value'] for entry in cr_sched
                         if isinstance(entry, dict) and 'value' in entry]
            configured_cr = float(np.median(cr_values)) if cr_values else None
        else:
            configured_cr = None

        sd = compute_supply_demand(df, pk)
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        # Find meal events via demand peaks, filtered for euglycemic start
        demand = sd['demand']
        demand_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values
        pos_demand = demand_smooth[demand_smooth > 0.01]
        if len(pos_demand) < 100:
            results[p['name']] = {'error': 'insufficient demand data'}
            continue

        meal_thresh = float(np.percentile(pos_demand, 80))
        meals = []
        i = 0
        while i < N - 24:  # need 2h post-meal
            if demand_smooth[i] > meal_thresh and valid[i]:
                bg_pre = bg[i]
                if np.isnan(bg_pre) or bg_pre < 70 or bg_pre > 160:
                    i += 6
                    continue

                # Measure peak excursion over 2h
                bg_2h = bg[i:i + 24]
                valid_2h = ~np.isnan(bg_2h)
                if valid_2h.sum() < 16:
                    i += 12
                    continue

                bg_peak = float(np.nanmax(bg_2h))
                excursion = bg_peak - bg_pre

                # Demand integral (proxy for meal size)
                demand_integral = float(np.sum(demand[i:i + 24]))

                # Check for post-meal low (< 70) in 4h
                bg_4h = bg[i:min(N, i + 48)]
                has_low = bool(np.nanmin(bg_4h) < 70) if len(bg_4h) > 0 else False

                meals.append({
                    'idx': int(i),
                    'bg_pre': float(bg_pre),
                    'bg_peak': bg_peak,
                    'excursion': float(excursion),
                    'demand_integral': demand_integral,
                    'post_meal_low': has_low,
                })
                i += 24  # skip 2h
            else:
                i += 1

        if len(meals) < 10:
            results[p['name']] = {
                'n_meals': len(meals),
                'configured_cr': configured_cr,
                'error': 'insufficient euglycemic meal events'
            }
            continue

        excursions = [m['excursion'] for m in meals]
        demand_integrals = [m['demand_integral'] for m in meals]
        low_rate = float(np.mean([m['post_meal_low'] for m in meals]) * 100)

        median_excursion = float(np.median(excursions))

        # Excursion per unit demand (normalized meal response)
        valid_meals = [(e, d) for e, d in zip(excursions, demand_integrals) if d > 0.01]
        if valid_meals:
            norm_excursions = [e / d for e, d in valid_meals]
            median_norm = float(np.median(norm_excursions))
        else:
            median_norm = 0

        # Temporal trend: early vs late meals
        mid = len(meals) // 2
        if mid >= 5:
            early_exc = float(np.median(excursions[:mid]))
            late_exc = float(np.median(excursions[mid:]))
            exc_drift = late_exc - early_exc
        else:
            early_exc = late_exc = median_excursion
            exc_drift = 0

        # Assessment: AID-aware thresholds
        # In AID, post-meal lows at 4h are normal (system correction).
        # Focus on excursion magnitude and severe low rate.
        if median_excursion > 70:
            cr_assessment = 'too_high'       # large excursions → insufficient insulin per carb
        elif median_excursion < 10 and low_rate > 50:
            cr_assessment = 'too_aggressive'  # tiny excursion + frequent lows → over-correcting
        elif low_rate > 50:
            cr_assessment = 'borderline_low'  # moderate excursion but frequent lows
        else:
            cr_assessment = 'adequate'

        results[p['name']] = {
            'n_meals': len(meals),
            'configured_cr': round(configured_cr, 1) if configured_cr else None,
            'median_excursion': round(median_excursion, 1),
            'excursion_iqr': [round(float(np.percentile(excursions, 25)), 1),
                              round(float(np.percentile(excursions, 75)), 1)],
            'post_meal_low_pct': round(low_rate, 1),
            'median_norm_excursion': round(median_norm, 2),
            'early_excursion': round(early_exc, 1),
            'late_excursion': round(late_exc, 1),
            'excursion_drift': round(exc_drift, 1),
            'cr_assessment': cr_assessment,
        }

        if detail:
            r = results[p['name']]
            sym = {'adequate': '✓', 'too_high': '↑', 'too_aggressive': '⚡', 'borderline_low': '⚠'}[r['cr_assessment']]
            print(f"  {p['name']}: CR={r['configured_cr']} exc={r['median_excursion']:+.0f} "
                  f"IQR=[{r['excursion_iqr'][0]:+.0f},{r['excursion_iqr'][1]:+.0f}] "
                  f"lows={r['post_meal_low_pct']:.0f}% "
                  f"[{r['n_meals']} meals] {sym}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-496/497/498: Device age effects and CR fidelity')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    print("Loading patients...")
    patients = load_patients(str(patients_dir), max_patients=args.max_patients)
    print(f"  Loaded {len(patients)} patients")

    all_results = {}

    print("\n═══ EXP-497: Sensor Age Effect on Residual ═══")
    r497 = run_exp497(patients, detail=args.detail)
    all_results['exp497_sensor_age'] = r497
    degrading = sum(1 for v in r497.values() if v.get('trend') == 'degrading')
    total = sum(1 for v in r497.values() if v.get('trend') and v['trend'] != 'insufficient')
    print(f"\n  Summary: {degrading}/{total} show sensor degradation trend")

    print("\n═══ EXP-498: Cannula/Site Age Effect ═══")
    r498 = run_exp498(patients, detail=args.detail)
    all_results['exp498_site_age'] = r498
    degrading = sum(1 for v in r498.values() if v.get('trend') == 'degrading')
    total = sum(1 for v in r498.values() if v.get('trend') and v['trend'] != 'insufficient')
    print(f"\n  Summary: {degrading}/{total} show site degradation trend")

    print("\n═══ EXP-496: CR Fidelity (Post-Meal Excursion) ═══")
    r496 = run_exp496(patients, detail=args.detail)
    all_results['exp496_cr_fidelity'] = r496
    for assess in ['adequate', 'too_high', 'too_low']:
        n = sum(1 for v in r496.values() if v.get('cr_assessment') == assess)
        if n:
            print(f"  {assess}: {n} patients")

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
