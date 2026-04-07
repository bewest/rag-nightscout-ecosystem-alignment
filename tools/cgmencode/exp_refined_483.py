#!/usr/bin/env python3
"""EXP-483–488: Refined Detection & Residual Analysis.

Building on EXP-480–482 live-split validation, these experiments refine
the unified detector and decompose the conservation residual.

EXP-483: Demand-weighted unified detector (filter overnight noise)
EXP-484: Meal size estimation from demand amplitude
EXP-486: Dessert detection (post-dinner secondary peaks)
EXP-488: Residual decomposition (meal vs dawn vs noise)

References:
  - exp_livesplit_480.py: Live-split data adapter and EXP-480–482
  - exp_nonbolus_476.py: EXP-476–479 non-bolusing methods
  - exp_metabolic_441.py: compute_supply_demand()
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from cgmencode.continuous_pk import PK_NORMALIZATION, expand_schedule
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_livesplit_480 import load_live_split

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
LIVE_SPLIT_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'live-split'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'

# Precondition thresholds for metabolic flux analysis
MIN_CGM_COVERAGE = 0.70   # ≥70% CGM readings present in a day
MIN_INS_COVERAGE = 0.10   # ≥10% of day has non-zero insulin activity


def assess_day_readiness(bg_day, demand_day, n_expected=288):
    """Check if a day meets preconditions for metabolic flux analysis.

    Preconditions:
    1. CGM coverage: ≥70% non-NaN glucose readings (sensor must be active)
    2. Insulin telemetry: ≥10% of timesteps with non-zero demand (pump data present)

    These encode the physical requirements:
    - CGM sensor must be transmitting (no sensor warmup, dropout, or expiry)
    - Pump must be delivering insulin (cannula functional, site not occluded)
    - Together they ensure the supply-demand framework has inputs to work with

    Returns dict with 'ready' bool, 'cgm_pct', 'ins_pct', 'reason'.
    """
    N = len(bg_day)
    cgm_pct = float(np.sum(~np.isnan(bg_day))) / max(N, 1)
    ins_pct = float(np.sum(demand_day > 0.01)) / max(N, 1)

    if cgm_pct < MIN_CGM_COVERAGE and ins_pct < MIN_INS_COVERAGE:
        return {'ready': False, 'cgm_pct': cgm_pct, 'ins_pct': ins_pct,
                'reason': 'both_gap'}
    elif cgm_pct < MIN_CGM_COVERAGE:
        return {'ready': False, 'cgm_pct': cgm_pct, 'ins_pct': ins_pct,
                'reason': 'cgm_gap'}
    elif ins_pct < MIN_INS_COVERAGE:
        return {'ready': False, 'cgm_pct': cgm_pct, 'ins_pct': ins_pct,
                'reason': 'ins_gap'}
    return {'ready': True, 'cgm_pct': cgm_pct, 'ins_pct': ins_pct,
            'reason': 'ready'}


# ── EXP-483: Demand-Weighted Unified Detector ─────────────────────────────

def detect_meals_demand_weighted(df, pk, detail=False):
    """Demand-primary meal detector with adaptive day-local thresholds.

    Strategy:
    1. Primary signal: demand peaks using DAY-LOCAL adaptive threshold
       (fixes global threshold masking variable-demand days)
    2. Glucose-derivative fallback for zero-insulin days/segments
    3. Confirmation: glucose rise OR positive residual within ±30min
    4. Filter: suppress 0–5 AM unless demand > 2× daily baseline
    5. Merge: deduplicate within 90-minute windows
    """
    sd = compute_supply_demand(df, pk)
    N = len(df)

    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)
    dbg = np.zeros_like(bg)
    valid = ~np.isnan(bg)
    dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)

    # Demand signal
    demand = sd['demand']
    dem_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values

    # Glucose derivative (fallback + confirmation)
    dbg_smooth = pd.Series(dbg).rolling(6, center=True, min_periods=1).mean().values

    # Residual for confirmation
    predicted_dbg = sd['supply'] - sd['demand']
    residual = dbg - predicted_dbg
    resid_smooth = pd.Series(residual).rolling(6, center=True, min_periods=1).mean().values

    # Day-local adaptive detection
    confirmed_peaks = []

    if hasattr(df.index, 'date'):
        dates = df.index.date
        unique_dates = sorted(set(dates))
    else:
        # Fallback: split into 288-step "days"
        unique_dates = list(range(N // 288 + 1))
        dates = np.array([i // 288 for i in range(N)])

    for d in unique_dates:
        if hasattr(d, 'isoformat'):
            mask = dates == d
        else:
            mask = np.array(dates) == d
        idx = np.where(mask)[0]
        if len(idx) < 24:  # <2h of data
            continue

        dem_day = dem_smooth[idx]
        dbg_day = dbg_smooth[idx]
        bg_day = bg[idx]

        day_peaks = []

        # Check if this day has insulin data
        has_insulin = np.sum(dem_day > 0.01) > 12  # >1h of insulin

        if has_insulin:
            # Day-local threshold: use this day's 50th percentile of positive demand
            pos_dem = dem_day[dem_day > 0.01]
            if len(pos_dem) > 10:
                day_thresh = np.percentile(pos_dem, 50)
                day_prom = np.percentile(pos_dem, 30) * 0.3
            else:
                day_thresh = 0.5
                day_prom = 0.1

            # Find demand peaks for this day
            peaks_in_day, _ = find_peaks(dem_day, height=day_thresh,
                                         distance=18, prominence=day_prom)
            for p in peaks_in_day:
                day_peaks.append(('demand', idx[p]))
        else:
            # FALLBACK: glucose derivative only (no insulin data)
            bg_valid = ~np.isnan(bg_day)
            if np.sum(bg_valid) > 24:
                # Rising glucose > 2 mg/dL per 5min sustained
                rise_thresh = 1.5
                peaks_bg, _ = find_peaks(dbg_day, height=rise_thresh,
                                        distance=18, prominence=0.5)
                for p in peaks_bg:
                    day_peaks.append(('glucose_fallback', idx[p]))

        # Confirm and filter each candidate
        for source, p in day_peaks:
            if source == 'demand':
                # Confirm: glucose rise or positive residual nearby
                window = slice(max(0, p - 6), min(N, p + 6))
                has_rise = np.any(dbg_smooth[window] > 0.5)
                has_pos_resid = np.any(resid_smooth[window] > 0.5)
                if not (has_rise or has_pos_resid):
                    continue

            # Overnight filter: suppress 0-5 AM unless strong signal
            if hasattr(df.index, 'hour') and p < len(df.index):
                hour = df.index[p].hour
                if 0 <= hour < 5:
                    if source == 'demand':
                        day_baseline = np.median(dem_day[dem_day > 0.01]) if np.sum(dem_day > 0.01) > 10 else 1.0
                        if dem_smooth[p] < 2 * day_baseline:
                            continue
                    else:
                        continue  # suppress all glucose-only overnight

            confirmed_peaks.append(p)

    # Global sort + deduplicate: merge peaks within 90 min
    confirmed_peaks.sort()
    if confirmed_peaks:
        merged = [confirmed_peaks[0]]
        for p in confirmed_peaks[1:]:
            if (p - merged[-1]) > 18:  # 90 min
                merged.append(p)
            elif dem_smooth[p] > dem_smooth[merged[-1]]:
                merged[-1] = p  # keep the stronger peak
        confirmed_peaks = merged

    return np.array(confirmed_peaks), dem_smooth


def run_exp483(df, pk, detail=False):
    """Test demand-weighted unified detector with precondition gating."""
    sd = compute_supply_demand(df, pk)
    peaks, dem_smooth = detect_meals_demand_weighted(df, pk, detail=detail)
    N = len(df)
    total_days = max(N / 288, 1)

    if not hasattr(df.index, 'date'):
        return {'events_per_day': round(len(peaks) / total_days, 1)}

    dates = df.index.date
    unique_dates = sorted(set(dates))

    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)

    daily = []
    daily_detail = []
    ready_daily = []
    gap_daily = []
    readiness_summary = {'ready': 0, 'cgm_gap': 0, 'ins_gap': 0, 'both_gap': 0}

    for d in unique_dates:
        mask = dates == d
        idx = np.where(mask)[0]
        day_start = idx[0]
        day_end = idx[-1] + 1
        day_peaks = [p for p in peaks if day_start <= p < day_end]
        n_meals = len(day_peaks)
        daily.append(n_meals)

        times = []
        for p in day_peaks:
            if p < len(df.index):
                h = df.index[p].hour + df.index[p].minute / 60.0
                times.append(round(h, 1))

        # Assess preconditions for this day
        readiness = assess_day_readiness(bg[idx], sd['demand'][idx])
        readiness_summary[readiness['reason']] += 1

        entry = {'date': str(d), 'n_meals': n_meals, 'times': times,
                 'ready': readiness['ready'], 'reason': readiness['reason'],
                 'cgm_pct': round(readiness['cgm_pct'], 2),
                 'ins_pct': round(readiness['ins_pct'], 2)}
        daily_detail.append(entry)

        if readiness['ready']:
            ready_daily.append(n_meals)
        else:
            gap_daily.append(n_meals)

    # Timing breakdown
    all_times = []
    for d in daily_detail:
        all_times.extend(d['times'])
    times_arr = np.array(all_times) if all_times else np.array([])

    results = {
        'all_days': {
            'n_days': len(daily),
            'events_per_day_mean': round(float(np.mean(daily)), 2),
            'events_per_day_median': round(float(np.median(daily)), 1),
            'events_per_day_std': round(float(np.std(daily)), 2),
            'days_with_0': int(sum(1 for c in daily if c == 0)),
            'days_with_1': int(sum(1 for c in daily if c == 1)),
            'days_with_2': int(sum(1 for c in daily if c == 2)),
            'days_with_3': int(sum(1 for c in daily if c == 3)),
            'days_with_4plus': int(sum(1 for c in daily if c >= 4)),
        },
        'preconditions': readiness_summary,
    }

    # Precondition-gated results (the real metric)
    if ready_daily:
        results['ready_days'] = {
            'n_days': len(ready_daily),
            'events_per_day_mean': round(float(np.mean(ready_daily)), 2),
            'events_per_day_median': round(float(np.median(ready_daily)), 1),
            'events_per_day_std': round(float(np.std(ready_daily)), 2),
            'detection_rate': round(sum(1 for c in ready_daily if c > 0) / len(ready_daily), 3),
            'days_with_0': int(sum(1 for c in ready_daily if c == 0)),
            'days_with_2_or_3': int(sum(1 for c in ready_daily if c in (2, 3))),
        }

    if len(times_arr) > 0:
        n_ready = max(len(ready_daily), 1)
        results['timing_per_day'] = {
            'breakfast_6_11': round(float(np.sum((times_arr >= 6) & (times_arr < 11))) / n_ready, 2),
            'lunch_11_15': round(float(np.sum((times_arr >= 11) & (times_arr < 15))) / n_ready, 2),
            'afternoon_15_17': round(float(np.sum((times_arr >= 15) & (times_arr < 17))) / n_ready, 2),
            'dinner_17_21': round(float(np.sum((times_arr >= 17) & (times_arr < 21))) / n_ready, 2),
            'dessert_21_24': round(float(np.sum((times_arr >= 21) & (times_arr < 24))) / n_ready, 2),
            'overnight_0_6': round(float(np.sum((times_arr >= 0) & (times_arr < 6))) / n_ready, 2),
        }

    if detail:
        r_all = results['all_days']
        print(f"  ALL days ({r_all['n_days']}): {r_all['events_per_day_mean']:.1f} ± "
              f"{r_all['events_per_day_std']:.1f}/day (median {r_all['events_per_day_median']:.0f})")
        rs = readiness_summary
        print(f"  Preconditions: {rs['ready']} ready, {rs['cgm_gap']} CGM-gap, "
              f"{rs['ins_gap']} INS-gap, {rs['both_gap']} both-gap")
        if 'ready_days' in results:
            r_rdy = results['ready_days']
            print(f"  READY days ({r_rdy['n_days']}): {r_rdy['events_per_day_mean']:.1f} ± "
                  f"{r_rdy['events_per_day_std']:.1f}/day (median {r_rdy['events_per_day_median']:.0f})")
            print(f"  Detection rate: {r_rdy['detection_rate']:.0%} "
                  f"({r_rdy['n_days'] - r_rdy['days_with_0']}/{r_rdy['n_days']} days)")
            print(f"  2-3 meals/day: {r_rdy['days_with_2_or_3']}/{r_rdy['n_days']} "
                  f"= {r_rdy['days_with_2_or_3']/r_rdy['n_days']:.0%}")
        if 'timing_per_day' in results:
            t = results['timing_per_day']
            print(f"  Timing: bkf={t['breakfast_6_11']:.1f}, lunch={t['lunch_11_15']:.1f}, "
                  f"dinner={t['dinner_17_21']:.1f}, dessert={t['dessert_21_24']:.1f}, "
                  f"overnight={t['overnight_0_6']:.1f}")

        # Sample week
        print(f"\n  Sample week:")
        for d in daily_detail[:7]:
            status = '✓' if d['ready'] else f'✗ {d["reason"]}'
            times_str = ', '.join(f"{t:.0f}:00" for t in d['times'])
            print(f"    {d['date']}: {d['n_meals']} meals [{times_str}] {status}")

    results['daily_detail'] = daily_detail
    return results


# ── EXP-486: Dessert Detection ────────────────────────────────────────────

def run_exp486(df, pk, meal_peaks, detail=False):
    """Detect post-dinner secondary peaks (dessert).

    Look for demand peaks within 1–3 hours after a dinner-time (17-21h) peak.
    """
    sd = compute_supply_demand(df, pk)
    N = len(df)
    demand = sd['demand']
    dem_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values

    if not hasattr(df.index, 'hour'):
        return {}

    dates = df.index.date
    unique_dates = sorted(set(dates))

    dinner_peaks = []
    dessert_peaks = []

    for p in meal_peaks:
        if p < len(df.index):
            hour = df.index[p].hour + df.index[p].minute / 60.0
            if 17 <= hour < 21:
                dinner_peaks.append(p)

    # For each dinner, look for secondary peak 1-3h later
    dem_thresh = np.percentile(dem_smooth[dem_smooth > 0], 40) if np.sum(dem_smooth > 0) > 100 else 0.5

    for dp in dinner_peaks:
        window_start = dp + 12  # 1 hour after
        window_end = min(N, dp + 36)  # 3 hours after
        if window_end <= window_start:
            continue

        window = dem_smooth[window_start:window_end]
        local_peaks, _ = find_peaks(window, height=dem_thresh, distance=6)

        if len(local_peaks) > 0:
            best = local_peaks[np.argmax(window[local_peaks])]
            dessert_idx = window_start + best
            dessert_hour = df.index[dessert_idx].hour + df.index[dessert_idx].minute / 60.0
            dessert_peaks.append({
                'dinner_time': round(df.index[dp].hour + df.index[dp].minute / 60.0, 1),
                'dessert_time': round(dessert_hour, 1),
                'gap_minutes': round((dessert_idx - dp) * 5, 0),
                'dinner_demand': round(float(dem_smooth[dp]), 2),
                'dessert_demand': round(float(dem_smooth[dessert_idx]), 2),
                'date': str(df.index[dp].date()),
            })

    total_days = len(unique_dates)
    results = {
        'n_dinners': len(dinner_peaks),
        'dinners_per_day': round(len(dinner_peaks) / max(total_days, 1), 2),
        'n_desserts': len(dessert_peaks),
        'desserts_per_day': round(len(dessert_peaks) / max(total_days, 1), 2),
        'dessert_fraction': round(len(dessert_peaks) / max(len(dinner_peaks), 1), 3),
        'dessert_gap_mean_min': round(float(np.mean([d['gap_minutes'] for d in dessert_peaks])), 0) if dessert_peaks else None,
    }

    if detail:
        print(f"  Dinners: {results['n_dinners']} ({results['dinners_per_day']:.1f}/day)")
        print(f"  Desserts: {results['n_desserts']} ({results['desserts_per_day']:.1f}/day)")
        print(f"  Dessert fraction: {results['dessert_fraction']:.0%}")
        if results['dessert_gap_mean_min']:
            print(f"  Dessert gap: {results['dessert_gap_mean_min']:.0f} min after dinner")

    results['events'] = dessert_peaks[:20]
    return results


# ── EXP-488: Residual Decomposition ──────────────────────────────────────

def run_exp488(df, pk, meal_peaks, detail=False):
    """Decompose conservation residual into meal, dawn, and noise components.

    residual = actual ΔBG - predicted ΔBG (supply - demand)

    Components:
    - Meal-correlated: positive residual within ±1h of demand peaks
    - Dawn-correlated: positive residual during 4–8 AM
    - Activity-correlated: negative residual during typical exercise hours
    - Noise: everything else
    """
    sd = compute_supply_demand(df, pk)
    N = len(df)

    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)
    dbg = np.zeros_like(bg)
    valid = ~np.isnan(bg)
    dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)

    predicted_dbg = sd['supply'] - sd['demand']
    residual = dbg - predicted_dbg

    if not hasattr(df.index, 'hour'):
        return {}

    hours = df.index.hour

    # Classify each timestep
    meal_mask = np.zeros(N, dtype=bool)
    for p in meal_peaks:
        start = max(0, p - 12)  # 1h before
        end = min(N, p + 12)    # 1h after
        meal_mask[start:end] = True

    dawn_mask = (hours >= 4) & (hours < 8) & ~meal_mask
    exercise_mask = (hours >= 15) & (hours < 19) & ~meal_mask  # typical exercise window
    noise_mask = ~meal_mask & ~dawn_mask & ~exercise_mask

    # Residual energy in each component
    total_var = float(np.nanvar(residual))
    if total_var < 1e-10:
        return {'error': 'zero variance in residual'}

    def component_stats(mask, name):
        r = residual[mask & ~np.isnan(residual)]
        if len(r) == 0:
            return {'fraction_of_time': 0, 'mean': 0, 'variance_share': 0}
        return {
            'fraction_of_time': round(float(mask.sum() / N), 3),
            'mean': round(float(np.mean(r)), 3),
            'std': round(float(np.std(r)), 3),
            'variance_share': round(float(np.var(r) * mask.sum()) / (total_var * N), 3),
            'positive_fraction': round(float(np.mean(r > 0.5)), 3),
            'negative_fraction': round(float(np.mean(r < -0.5)), 3),
        }

    results = {
        'total_residual_mean': round(float(np.nanmean(residual)), 3),
        'total_residual_std': round(float(np.nanstd(residual)), 3),
        'meal_component': component_stats(meal_mask, 'meal'),
        'dawn_component': component_stats(dawn_mask, 'dawn'),
        'exercise_component': component_stats(exercise_mask, 'exercise'),
        'noise_component': component_stats(noise_mask, 'noise'),
    }

    if detail:
        print(f"  Total residual: {results['total_residual_mean']:+.3f} ± "
              f"{results['total_residual_std']:.3f}")
        for comp_name in ['meal_component', 'dawn_component', 'exercise_component', 'noise_component']:
            c = results[comp_name]
            label = comp_name.replace('_component', '')
            print(f"  {label:10s}: {c['fraction_of_time']:.0%} of time, "
                  f"mean={c['mean']:+.3f}, var_share={c['variance_share']:.0%}, "
                  f"pos={c.get('positive_fraction', 0):.0%}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-483–488: Refined detection & residual analysis')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--live-split-dir', type=str, default=None)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--exp', type=str, default='all',
                        help='Run specific experiments (483,486,488) or all')
    args = parser.parse_args()

    live_dir = Path(args.live_split_dir) if args.live_split_dir else LIVE_SPLIT_DIR

    print(f"Loading live-split data...")
    df, pk = load_live_split(live_dir, subset='training')
    print(f"  Loaded: {len(df)} steps ({len(df)/288:.1f} days)")

    all_results = {}
    exps = args.exp.split(',') if args.exp != 'all' else ['483', '486', '488']

    # Run primary detector first (needed by 486, 488)
    print("\n═══ EXP-483: Demand-Weighted Unified Detector ═══")
    r483 = run_exp483(df, pk, detail=args.detail)
    all_results['exp483_demand_weighted'] = r483
    meal_peaks, _ = detect_meals_demand_weighted(df, pk)

    if '486' in exps:
        print("\n═══ EXP-486: Dessert Detection ═══")
        r486 = run_exp486(df, pk, meal_peaks, detail=args.detail)
        all_results['exp486_dessert_detection'] = r486

    if '488' in exps:
        print("\n═══ EXP-488: Residual Decomposition ═══")
        r488 = run_exp488(df, pk, meal_peaks, detail=args.detail)
        all_results['exp488_residual_decomposition'] = r488

    # Also run on 11-patient cohort for comparison
    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    if patients_dir.exists():
        print(f"\n═══ Cohort Comparison ═══")
        patients = load_patients(str(patients_dir), max_patients=3)
        for p in patients:
            peaks_p, _ = detect_meals_demand_weighted(p['df'], p['pk'])
            n_days = len(p['df']) / 288
            if hasattr(p['df'].index, 'date'):
                dates = p['df'].index.date
                unique_dates = sorted(set(dates))
                daily = []
                for d in unique_dates:
                    day_start = np.searchsorted(dates, d)
                    day_end = np.searchsorted(dates, d, side='right')
                    day_peaks = [pp for pp in peaks_p if day_start <= pp < day_end]
                    daily.append(len(day_peaks))
                print(f"  {p['name']}: {np.mean(daily):.1f} ± {np.std(daily):.1f}/day "
                      f"(median {np.median(daily):.0f})")

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
