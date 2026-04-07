#!/usr/bin/env python3
"""EXP-505/506/508: Dawn Quantification, Fat/Protein Tail, AID Mode Fingerprint.

EXP-505: Quantify dawn phenomenon per patient — magnitude, onset time,
         and correlation with overnight basal settings.

EXP-506: Detect fat/protein absorption tails — extended BG rise 4-8h
         after meals suggests fat/protein delayed absorption.

EXP-508: AID mode fingerprint — do different AID operational modes
         (aggressive temp basal vs SMB vs manual) produce distinct
         metabolic flux signatures?

References:
  - exp_metabolic_441.py: compute_supply_demand()
  - continuous_pk.py: expand_schedule(), PK channels
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


# ── EXP-505: Dawn Phenomenon Quantification ─────────────────────────────

def run_exp505(patients, detail=False):
    """Quantify dawn phenomenon: BG rise between 3-7 AM driven by cortisol.

    Measures: magnitude (BG nadir→7AM peak), onset time, duration,
    and whether basal settings compensate adequately.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        if not hasattr(df.index, 'hour') or not hasattr(df.index, 'date'):
            continue

        hours = df.index.hour
        dates = df.index.date
        unique_dates = sorted(set(dates))

        # Analyze each night: 0-8 AM window
        nights = []
        for d in unique_dates:
            mask = (dates == d) & (hours >= 0) & (hours < 8)
            idx = np.where(mask)[0]
            if len(idx) < 80:  # need ≥80% of 96 possible points
                continue

            bg_night = bg[idx]
            v = ~np.isnan(bg_night)
            if v.sum() < 60:
                continue

            hours_night = hours[idx]

            # Check no carbs (no eating overnight)
            carb_rate = pk[idx, 3] if pk is not None and pk.shape[1] > 3 else np.zeros(len(idx))
            if np.max(carb_rate) > 0.1:
                continue  # skip nights with carb activity

            # Find nadir (lowest BG) and its hour
            bg_valid = np.where(v, bg_night, 999)
            nadir_idx = np.argmin(bg_valid)
            nadir_bg = float(bg_night[nadir_idx])
            nadir_hour = float(hours_night[nadir_idx])

            # Find BG at 7 AM (or closest)
            am7_mask = hours_night == 7
            if am7_mask.sum() > 0:
                am7_bg = float(np.nanmean(bg_night[am7_mask]))
            else:
                am7_bg = nadir_bg  # fallback

            # Dawn rise = 7AM - nadir (positive = dawn phenomenon present)
            dawn_rise = am7_bg - nadir_bg

            # Pre-dawn BG (0-3 AM average)
            pre_dawn = (hours_night >= 0) & (hours_night < 3) & v
            pre_dawn_mean = float(np.nanmean(bg_night[pre_dawn])) if pre_dawn.sum() > 10 else np.nan

            nights.append({
                'date': str(d),
                'nadir_bg': nadir_bg,
                'nadir_hour': nadir_hour,
                'am7_bg': am7_bg,
                'dawn_rise': dawn_rise,
                'pre_dawn_mean': pre_dawn_mean,
            })

        if len(nights) < 20:
            results[p['name']] = {'n_nights': len(nights), 'error': 'insufficient clean nights'}
            if detail:
                print(f"  {p['name']}: {len(nights)} clean nights — insufficient")
            continue

        rises = [n['dawn_rise'] for n in nights]
        nadirs = [n['nadir_hour'] for n in nights]

        # Dawn phenomenon present if median rise > 10 mg/dL
        median_rise = float(np.median(rises))
        mean_nadir_hour = float(np.mean(nadirs))
        pct_with_dawn = float(np.mean([1 for r in rises if r > 10]) / len(rises) * 100)

        # Seasonal trend: does dawn phenomenon change over 6 months?
        if len(nights) >= 30:
            x = np.arange(len(rises))
            slope, _, _, pval, _ = stats.linregress(x, rises)
            seasonal_trend = 'increasing' if slope > 0.05 and pval < 0.1 else \
                             ('decreasing' if slope < -0.05 and pval < 0.1 else 'stable')
        else:
            slope = pval = 0
            seasonal_trend = 'insufficient'

        results[p['name']] = {
            'n_nights': len(nights),
            'median_dawn_rise': round(median_rise, 1),
            'mean_nadir_hour': round(mean_nadir_hour, 1),
            'pct_with_dawn': round(pct_with_dawn, 1),
            'dawn_iqr': [round(float(np.percentile(rises, 25)), 1),
                         round(float(np.percentile(rises, 75)), 1)],
            'seasonal_trend': seasonal_trend,
            'seasonal_slope': round(float(slope), 3),
        }

        if detail:
            r = results[p['name']]
            sym = '☀' if r['median_dawn_rise'] > 10 else '🌙'
            print(f"  {p['name']}: dawn={r['median_dawn_rise']:+.0f} mg/dL "
                  f"({r['pct_with_dawn']:.0f}% of nights) "
                  f"nadir={r['mean_nadir_hour']:.1f}h "
                  f"trend={r['seasonal_trend']} {sym}")

    return results


# ── EXP-506: Fat/Protein Absorption Tail ────────────────────────────────

def run_exp506(patients, detail=False):
    """Detect extended absorption tails from fat/protein-rich meals.

    Fat and protein cause delayed glucose rise 3-8h after eating.
    We detect this as: demand integral CONTINUES growing after the
    initial 3h absorption window, OR BG rises again 4-6h post-meal.

    Metric: ratio of late demand (3-6h) to early demand (0-3h) after meals.
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

        meals = []
        i = 0
        while i < N - 72:  # need 6h post-meal
            if demand_smooth[i] > meal_thresh and valid[i]:
                # Early demand (0-3h)
                early = float(np.sum(demand[i:i + 36]))
                # Late demand (3-6h)
                late = float(np.sum(demand[i + 36:i + 72]))

                if early < 0.01:
                    i += 12
                    continue

                tail_ratio = late / (early + 1e-6)

                # BG trajectory: does it rise again after 3h?
                bg_3h = bg[min(i + 36, N - 1)] if valid[min(i + 36, N - 1)] else np.nan
                bg_5h = bg[min(i + 60, N - 1)] if valid[min(i + 60, N - 1)] else np.nan
                bg_start = bg[i]

                secondary_rise = (bg_5h - bg_3h) if not (np.isnan(bg_3h) or np.isnan(bg_5h)) else 0

                meals.append({
                    'idx': int(i),
                    'early_demand': early,
                    'late_demand': late,
                    'tail_ratio': tail_ratio,
                    'secondary_rise': float(secondary_rise),
                    'has_tail': tail_ratio > 0.3 and secondary_rise > 5,
                })
                i += 72
            else:
                i += 1

        if len(meals) < 20:
            results[p['name']] = {'n_meals': len(meals), 'error': 'insufficient meals'}
            continue

        tail_ratios = [m['tail_ratio'] for m in meals]
        secondary_rises = [m['secondary_rise'] for m in meals]
        pct_with_tail = float(np.mean([m['has_tail'] for m in meals]) * 100)

        results[p['name']] = {
            'n_meals': len(meals),
            'median_tail_ratio': round(float(np.median(tail_ratios)), 3),
            'pct_with_tail': round(pct_with_tail, 1),
            'median_secondary_rise': round(float(np.median(secondary_rises)), 1),
            'tail_ratio_iqr': [round(float(np.percentile(tail_ratios, 25)), 3),
                               round(float(np.percentile(tail_ratios, 75)), 3)],
        }

        if detail:
            r = results[p['name']]
            sym = '🍕' if r['pct_with_tail'] > 20 else '🥗'
            print(f"  {p['name']}: tail_ratio={r['median_tail_ratio']:.3f} "
                  f"({r['pct_with_tail']:.0f}% with tail) "
                  f"secondary_rise={r['median_secondary_rise']:+.0f} "
                  f"[{r['n_meals']} meals] {sym}")

    return results


# ── EXP-508: AID Mode Fingerprint ──────────────────────────────────────

def run_exp508(patients, detail=False):
    """Identify AID operational mode fingerprints from PK patterns.

    Different AID strategies produce distinct signatures:
    - SMB-dominant: frequent small insulin_net spikes, high basal_ratio variance
    - Temp basal: smooth insulin_net with fewer spikes, basal_ratio oscillates
    - Manual bolus: sharp insulin_net spikes, basal_ratio near 1.0

    We characterize each patient's insulin delivery fingerprint.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        if pk is None or pk.shape[1] < 5:
            results[p['name']] = {'error': 'no PK data'}
            continue

        N = len(df)
        INS_NORM = 0.05

        # PK channels
        insulin_total = pk[:, 0] * INS_NORM  # total insulin activity
        insulin_net = pk[:, 1] * INS_NORM    # net (above basal) activity
        basal_ratio = pk[:, 2] * 2.0         # actual/scheduled basal
        carb_rate = pk[:, 3]                  # carb absorption

        # 1. Insulin delivery pattern
        # Spike frequency: how often does insulin_net exceed P90?
        pos_net = insulin_net[insulin_net > 1e-6]
        if len(pos_net) < 100:
            results[p['name']] = {'error': 'insufficient insulin data'}
            continue

        spike_thresh = float(np.percentile(pos_net, 90))
        spikes = insulin_net > spike_thresh
        spike_transitions = np.diff(spikes.astype(int))
        n_spikes = int(np.sum(spike_transitions == 1))
        spikes_per_day = n_spikes / (N / 288)

        # 2. Spike characteristics
        # Mean spike duration (consecutive above-threshold steps)
        spike_durations = []
        in_spike = False
        dur = 0
        for s in spikes:
            if s:
                dur += 1
                in_spike = True
            else:
                if in_spike:
                    spike_durations.append(dur)
                dur = 0
                in_spike = False
        mean_spike_dur = float(np.mean(spike_durations)) * 5 if spike_durations else 0  # minutes

        # 3. Basal ratio variability
        br_std = float(np.std(basal_ratio))
        br_mean = float(np.mean(basal_ratio))
        time_suspended = float(np.mean(basal_ratio < 0.1) * 100)  # % time at zero
        time_high_temp = float(np.mean(basal_ratio > 1.5) * 100)  # % time at >150%

        # 4. Net vs total ratio: what fraction of insulin is corrections?
        total_sum = float(np.sum(insulin_total))
        net_sum = float(np.sum(np.abs(insulin_net)))
        correction_fraction = net_sum / (total_sum + 1e-6)

        # 5. Classify AID mode
        if spikes_per_day > 15 and mean_spike_dur < 20:
            mode = 'SMB_dominant'
        elif time_suspended > 10 and time_high_temp > 10:
            mode = 'aggressive_temp'
        elif spikes_per_day < 5 and br_std < 0.3:
            mode = 'conservative'
        else:
            mode = 'hybrid'

        results[p['name']] = {
            'mode': mode,
            'spikes_per_day': round(spikes_per_day, 1),
            'mean_spike_duration_min': round(mean_spike_dur, 1),
            'basal_ratio_mean': round(br_mean, 2),
            'basal_ratio_std': round(br_std, 3),
            'time_suspended_pct': round(time_suspended, 1),
            'time_high_temp_pct': round(time_high_temp, 1),
            'correction_fraction': round(correction_fraction, 3),
        }

        if detail:
            r = results[p['name']]
            mode_sym = {'SMB_dominant': '⚡', 'aggressive_temp': '🔄',
                        'conservative': '📊', 'hybrid': '🔀'}[r['mode']]
            print(f"  {p['name']}: {r['mode']} {mode_sym} "
                  f"spikes={r['spikes_per_day']:.0f}/day "
                  f"dur={r['mean_spike_duration_min']:.0f}min "
                  f"suspended={r['time_suspended_pct']:.0f}% "
                  f"high_temp={r['time_high_temp_pct']:.0f}% "
                  f"correction={r['correction_fraction']:.1%}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-505/506/508: Dawn, fat/protein tail, AID mode')
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

    print("\n═══ EXP-505: Dawn Phenomenon Quantification ═══")
    r505 = run_exp505(patients, detail=args.detail)
    all_results['exp505_dawn'] = r505
    dawn_pct = [v['pct_with_dawn'] for v in r505.values() if 'pct_with_dawn' in v]
    if dawn_pct:
        print(f"\n  Mean dawn frequency: {np.mean(dawn_pct):.0f}% of nights across patients")

    print("\n═══ EXP-506: Fat/Protein Absorption Tail ═══")
    r506 = run_exp506(patients, detail=args.detail)
    all_results['exp506_fat_protein'] = r506
    tail_pcts = [v['pct_with_tail'] for v in r506.values() if 'pct_with_tail' in v]
    if tail_pcts:
        print(f"\n  Mean meals with tail: {np.mean(tail_pcts):.0f}%")

    print("\n═══ EXP-508: AID Mode Fingerprint ═══")
    r508 = run_exp508(patients, detail=args.detail)
    all_results['exp508_aid_mode'] = r508
    mode_counts = {}
    for v in r508.values():
        m = v.get('mode', '')
        if m:
            mode_counts[m] = mode_counts.get(m, 0) + 1
    if mode_counts:
        print(f"\n  Mode distribution: {dict(sorted(mode_counts.items()))}")

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
