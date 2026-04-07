#!/usr/bin/env python3
"""EXP-501/502/509: Exercise Signature, Meal Size Estimation, Absorption Window.

EXP-501: Exercise signature detection — exercise increases insulin sensitivity
         for 24-48h, producing characteristic supply-demand patterns (reduced
         demand relative to insulin, more frequent lows).

EXP-502: Meal size estimation — does the demand integral correlate with
         carb intake? Can we estimate meal size from flux alone?

EXP-509: Optimal absorption window — does the carb absorption window (default
         3h) need to be adjusted per patient or meal size?

References:
  - exp_metabolic_441.py: compute_supply_demand()
  - exp_refined_483.py: detect_meals_demand_weighted()
  - continuous_pk.py: PK_NORMALIZATION, carb absorption model
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-501: Exercise Signature ─────────────────────────────────────────

def run_exp501(patients, detail=False):
    """Detect exercise-like events from metabolic flux patterns.

    Exercise signature: period of elevated demand (muscle glucose uptake)
    followed by 12-24h of reduced demand (increased insulin sensitivity).
    In flux terms: a sharp demand spike without carb absorption, followed
    by a sustained period where supply > demand (BG drops or stays low
    despite normal insulin).

    We detect this as: high demand episodes (P90) with NO carb absorption,
    followed by BG trending lower-than-usual for the next 12h.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        demand = sd['demand']
        supply = sd['supply']
        net_flux = supply - demand

        # Carb rate from PK
        carb_rate = pk[:, 3] if pk is not None and pk.shape[1] > 3 else np.zeros(N)

        # Patient-specific demand threshold (P90)
        pos_demand = demand[demand > 0.01]
        if len(pos_demand) < 100:
            results[p['name']] = {'error': 'insufficient demand data'}
            continue
        high_demand_thresh = float(np.percentile(pos_demand, 90))

        # Overall BG statistics for comparison
        overall_bg_mean = float(np.nanmean(bg[valid]))

        # Find exercise-like events
        events = []
        i = 0
        while i < N - 144:  # need 12h post-event
            if demand[i] > high_demand_thresh and carb_rate[i] < 0.05:
                # Found high demand without carbs — potential exercise
                # Check sustained (>30 min of elevated demand)
                sustained = 0
                for j in range(i, min(i + 12, N)):
                    if demand[j] > high_demand_thresh * 0.5:
                        sustained += 1
                if sustained < 4:  # need ≥20 min sustained
                    i += 6
                    continue

                # Measure post-event effects (next 12h)
                post_start = i + 12  # skip 1h immediate recovery
                post_end = min(i + 144, N)
                post_bg = bg[post_start:post_end]
                post_valid = ~np.isnan(post_bg)

                if post_valid.sum() < 72:  # need ≥50% of 12h
                    i += 24
                    continue

                post_mean = float(np.nanmean(post_bg[post_valid]))
                post_low_pct = float(np.mean(post_bg[post_valid] < 70) * 100)

                # BG drop from event start to 6h later
                bg_at_event = bg[i] if valid[i] else np.nan
                bg_6h = bg[min(i + 72, N - 1)] if valid[min(i + 72, N - 1)] else np.nan

                # Net flux in post-event window (positive = BG rising)
                post_flux = net_flux[post_start:post_end]
                mean_post_flux = float(np.mean(post_flux))

                events.append({
                    'idx': int(i),
                    'hour': int(df.index[i].hour) if hasattr(df.index, 'hour') else 0,
                    'bg_at_event': float(bg_at_event) if not np.isnan(bg_at_event) else None,
                    'post_bg_mean': post_mean,
                    'bg_delta_from_overall': round(post_mean - overall_bg_mean, 1),
                    'post_low_pct': round(post_low_pct, 1),
                    'post_flux_mean': round(mean_post_flux, 3),
                })
                i += 144  # skip 12h
            else:
                i += 1

        if not events:
            results[p['name']] = {'n_events': 0, 'error': 'no exercise-like events detected'}
            if detail:
                print(f"  {p['name']}: no exercise-like events")
            continue

        # Analyze distribution
        bg_deltas = [e['bg_delta_from_overall'] for e in events if e['bg_delta_from_overall'] is not None]
        low_pcts = [e['post_low_pct'] for e in events]
        hours = [e['hour'] for e in events]

        # Hour distribution (exercise typically afternoon/evening)
        hour_counts = {}
        for h in hours:
            bucket = f"{(h // 6) * 6:02d}-{((h // 6) + 1) * 6:02d}"
            hour_counts[bucket] = hour_counts.get(bucket, 0) + 1

        # Is post-event BG systematically lower?
        if bg_deltas:
            t_stat, t_pval = stats.ttest_1samp(bg_deltas, 0)
        else:
            t_stat, t_pval = 0, 1

        results[p['name']] = {
            'n_events': len(events),
            'events_per_week': round(len(events) / (N / (288 * 7)), 1),
            'mean_bg_delta': round(float(np.mean(bg_deltas)), 1) if bg_deltas else 0,
            'mean_post_low_pct': round(float(np.mean(low_pcts)), 1),
            'bg_delta_pvalue': round(float(t_pval), 4),
            'hour_distribution': hour_counts,
            'sensitivity_confirmed': bool(bg_deltas and np.mean(bg_deltas) < -5 and t_pval < 0.1),
        }

        if detail:
            r = results[p['name']]
            conf = '✓' if r['sensitivity_confirmed'] else '✗'
            print(f"  {p['name']}: {r['n_events']} events ({r['events_per_week']:.1f}/wk) "
                  f"post-BG delta={r['mean_bg_delta']:+.0f} (p={r['bg_delta_pvalue']:.3f}) "
                  f"lows={r['mean_post_low_pct']:.0f}% sensitivity={conf}")

    return results


# ── EXP-502: Meal Size Estimation ───────────────────────────────────────

def run_exp502(patients, detail=False):
    """Test if demand integral correlates with actual carb intake.

    For patients who announce meals, we can compare:
    - demand_integral (from flux decomposition, works for all patients)
    - carb_integral (from PK carb absorption channel, only if carbs entered)

    If they correlate well, demand_integral can estimate meal size
    even for UAM patients who don't enter carbs.
    """
    CARB_NORM = 5.0  # PK_NORMALIZATION['carb_rate']

    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        demand = sd['demand']
        carb_rate_raw = pk[:, 3] * CARB_NORM if pk is not None and pk.shape[1] > 3 else np.zeros(N)
        carb_rate_norm = pk[:, 3] if pk is not None and pk.shape[1] > 3 else np.zeros(N)

        # Find meal events from demand peaks
        demand_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values
        pos_demand = demand_smooth[demand_smooth > 0.01]
        if len(pos_demand) < 100:
            results[p['name']] = {'error': 'insufficient demand data'}
            continue

        meal_thresh = float(np.percentile(pos_demand, 75))

        meals = []
        i = 0
        while i < N - 36:  # need 3h window
            if demand_smooth[i] > meal_thresh and valid[i]:
                # Demand integral over 3h
                demand_integral = float(np.sum(demand[i:i + 36]))
                # Carb integral over 3h (raw units)
                carb_integral = float(np.sum(carb_rate_raw[i:i + 36]))
                # BG excursion
                bg_3h = bg[i:i + 36]
                excursion = float(np.nanmax(bg_3h) - bg[i]) if not np.isnan(bg[i]) else 0

                has_carbs = carb_integral > 0.5  # at least ~0.5g carbs entered

                meals.append({
                    'idx': int(i),
                    'demand_integral': demand_integral,
                    'carb_integral': carb_integral,
                    'has_carbs': has_carbs,
                    'excursion': excursion,
                })
                i += 36
            else:
                i += 1

        if len(meals) < 10:
            results[p['name']] = {'n_meals': len(meals), 'error': 'insufficient meals'}
            continue

        # Split by carb availability
        announced = [m for m in meals if m['has_carbs']]
        unannounced = [m for m in meals if not m['has_carbs']]

        # For announced meals: correlate demand_integral with carb_integral
        if len(announced) >= 10:
            d_ints = [m['demand_integral'] for m in announced]
            c_ints = [m['carb_integral'] for m in announced]
            corr, pval = stats.pearsonr(d_ints, c_ints)
        else:
            corr, pval = None, None

        # Size bins for demand-based meal size estimation
        all_d = [m['demand_integral'] for m in meals]
        d_p25, d_p50, d_p75 = np.percentile(all_d, [25, 50, 75])

        size_bins = {
            'small': sum(1 for d in all_d if d < d_p25),
            'medium': sum(1 for d in all_d if d_p25 <= d < d_p75),
            'large': sum(1 for d in all_d if d >= d_p75),
        }

        # Excursion by size: do larger demand meals cause larger excursions?
        small_exc = [m['excursion'] for m in meals if m['demand_integral'] < d_p25]
        large_exc = [m['excursion'] for m in meals if m['demand_integral'] >= d_p75]
        exc_difference = (float(np.median(large_exc)) - float(np.median(small_exc))) \
            if small_exc and large_exc else 0

        results[p['name']] = {
            'n_meals': len(meals),
            'n_announced': len(announced),
            'n_unannounced': len(unannounced),
            'announced_pct': round(len(announced) / len(meals) * 100, 1),
            'demand_carb_correlation': round(float(corr), 3) if corr is not None else None,
            'demand_carb_pvalue': round(float(pval), 4) if pval is not None else None,
            'demand_percentiles': {
                'p25': round(d_p25, 2),
                'p50': round(d_p50, 2),
                'p75': round(d_p75, 2),
            },
            'size_bins': size_bins,
            'large_vs_small_excursion': round(exc_difference, 1),
        }

        if detail:
            r = results[p['name']]
            corr_str = f"r={r['demand_carb_correlation']:.3f}" if r['demand_carb_correlation'] else "N/A"
            print(f"  {p['name']}: {r['n_meals']} meals ({r['announced_pct']:.0f}% announced) "
                  f"demand-carb corr={corr_str} "
                  f"large-small exc={r['large_vs_small_excursion']:+.0f} mg/dL")

    return results


# ── EXP-509: Absorption Window Optimization ─────────────────────────────

def run_exp509(patients, detail=False):
    """Test if different absorption windows capture meal events differently.

    Default carb absorption is 3h (180 min). For large/fatty meals,
    absorption can extend to 4-6h. For simple carbs, 1-2h.

    We test whether using different integration windows changes the
    demand-excursion correlation or meal detection quality.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        demand = sd['demand']
        demand_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values
        pos_demand = demand_smooth[demand_smooth > 0.01]
        if len(pos_demand) < 100:
            results[p['name']] = {'error': 'insufficient data'}
            continue

        meal_thresh = float(np.percentile(pos_demand, 80))

        # Test windows: 1h, 2h, 3h, 4h, 5h
        window_results = {}
        for window_h in [1, 2, 3, 4, 5]:
            steps = window_h * 12
            meals = []
            i = 0
            while i < N - steps:
                if demand_smooth[i] > meal_thresh and valid[i]:
                    bg_window = bg[i:i + steps]
                    valid_w = ~np.isnan(bg_window)
                    if valid_w.sum() < steps * 0.7:
                        i += 6
                        continue

                    demand_int = float(np.sum(demand[i:i + steps]))
                    excursion = float(np.nanmax(bg_window) - bg[i])

                    meals.append((demand_int, excursion))
                    i += steps
                else:
                    i += 1

            if len(meals) < 20:
                continue

            d_ints = [m[0] for m in meals]
            excursions = [m[1] for m in meals]

            corr, pval = stats.pearsonr(d_ints, excursions)
            window_results[f'{window_h}h'] = {
                'n_meals': len(meals),
                'demand_exc_corr': round(float(corr), 3),
                'demand_exc_pval': round(float(pval), 4),
                'median_excursion': round(float(np.median(excursions)), 1),
            }

        if not window_results:
            results[p['name']] = {'error': 'no valid windows'}
            continue

        # Find optimal window (highest correlation)
        best_window = max(window_results.items(),
                          key=lambda x: x[1]['demand_exc_corr'])

        results[p['name']] = {
            'windows': window_results,
            'best_window': best_window[0],
            'best_correlation': best_window[1]['demand_exc_corr'],
        }

        if detail:
            r = results[p['name']]
            windows_str = ' '.join(f"{k}:{v['demand_exc_corr']:+.3f}"
                                   for k, v in sorted(window_results.items()))
            print(f"  {p['name']}: best={r['best_window']} (r={r['best_correlation']:+.3f}) "
                  f"[{windows_str}]")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-501/502/509: Exercise, meal size, absorption window')
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

    print("\n═══ EXP-501: Exercise Signature Detection ═══")
    r501 = run_exp501(patients, detail=args.detail)
    all_results['exp501_exercise'] = r501
    confirmed = sum(1 for v in r501.values() if v.get('sensitivity_confirmed'))
    total = sum(1 for v in r501.values() if 'n_events' in v and v['n_events'] > 0)
    print(f"\n  Summary: {confirmed}/{total} show post-event insulin sensitivity increase")

    print("\n═══ EXP-502: Meal Size Estimation from Demand Integral ═══")
    r502 = run_exp502(patients, detail=args.detail)
    all_results['exp502_meal_size'] = r502

    print("\n═══ EXP-509: Absorption Window Optimization ═══")
    r509 = run_exp509(patients, detail=args.detail)
    all_results['exp509_absorption_window'] = r509

    # Count best windows
    window_counts = {}
    for v in r509.values():
        bw = v.get('best_window', '')
        if bw:
            window_counts[bw] = window_counts.get(bw, 0) + 1
    if window_counts:
        print(f"\n  Best window distribution: {dict(sorted(window_counts.items()))}")

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
