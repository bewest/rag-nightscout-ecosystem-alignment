#!/usr/bin/env python3
"""EXP-2622: Advisory Convergence — Minimum Data Requirements

For production deployment, we need to know: how many days of data does
each advisory need before it stabilizes? We'll compute ISF, CR, and basal
advisories on increasing subsets of data (7, 14, 21, 30, 45, 60, 90 days)
and measure when the advisory stabilizes (< 10% change from final value).

Hypotheses:
  H1: ISF calibration stabilizes within 14 days for ≥ 8/12 patients
      (change < 10% from 90-day value by day 14).
  H2: CR calibration stabilizes within 21 days for ≥ 6/12 patients.
  H3: Advisory direction (increase/decrease/adequate) stabilizes before
      magnitude — direction correct by 7 days for ≥ 8/12 patients.
  H4: Patients with more correction events stabilize faster
      (Spearman r < -0.3 between n_corrections and days_to_stable).

Requires: FULL telemetry patients with ≥ 30 days of data.
"""
import json
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

PROJ = Path(__file__).resolve().parents[3]
PARQUET = PROJ / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
OUTDIR = PROJ / 'externals' / 'experiments'
OUTDIR.mkdir(parents=True, exist_ok=True)

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k',
                 'odc-39819048', 'odc-49141524', 'odc-58680324',
                 'odc-61403732', 'odc-74077367', 'odc-86025410', 'odc-96254963']

DATA_WINDOWS = [7, 14, 21, 30, 45, 60, 90]


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df[df['patient_id'].isin(FULL_PATIENTS)]


def compute_isf_for_window(pdf, n_days):
    """Compute ISF ratio from the first n_days of data."""
    start = pdf['timestamp'].min()
    end = start + pd.Timedelta(days=n_days)
    window = pdf[(pdf['timestamp'] >= start) & (pdf['timestamp'] < end)]

    if len(window) < 100:
        return None, 0

    # Find correction boluses
    corrections = window[
        (window['bolus'] > 0.5) &
        ((window['carbs'].isna()) | (window['carbs'] <= 1)) &
        (window['sgv'] > 150) &
        (window['scheduled_isf'].notna()) & (window['scheduled_isf'] > 0)
    ]

    if len(corrections) < 3:
        return None, 0

    profile_isf = window['scheduled_isf'].median()
    ratios = []

    for idx in corrections.index:
        pos = window.index.get_loc(idx)
        if pos + 23 >= len(window):
            continue
        w = window.iloc[pos:pos+24]
        if w['sgv'].isna().sum() > 5:
            continue
        actual_drop = w['sgv'].iloc[0] - w['sgv'].iloc[-1]
        bolus = w['bolus'].iloc[0]
        expected_drop = bolus * profile_isf
        if expected_drop > 0:
            ratio = actual_drop / expected_drop
            if 0.1 < ratio < 5.0:
                ratios.append(ratio)

    if len(ratios) >= 3:
        return float(np.median(ratios)), len(ratios)
    return None, 0


def compute_cr_for_window(pdf, n_days):
    """Compute effective CR from the first n_days of data."""
    start = pdf['timestamp'].min()
    end = start + pd.Timedelta(days=n_days)
    window = pdf[(pdf['timestamp'] >= start) & (pdf['timestamp'] < end)]

    if len(window) < 100:
        return None, 0

    # Find meal boluses
    meals = window[
        (window['bolus'] > 0.5) &
        (window['carbs'] > 5) &
        (window['sgv'].notna()) &
        (window['scheduled_cr'].notna()) & (window['scheduled_cr'] > 0)
    ]

    if len(meals) < 3:
        return None, 0

    profile_cr = window['scheduled_cr'].median()
    cr_ratios = []

    for idx in meals.index:
        pos = window.index.get_loc(idx)
        if pos + 23 >= len(window):
            continue
        w = window.iloc[pos:pos+24]
        if w['sgv'].isna().sum() > 5:
            continue

        carbs = w['carbs'].iloc[0]
        bolus = w['bolus'].iloc[0]
        bg_rise = w['sgv'].iloc[12] - w['sgv'].iloc[0]  # 1h post-meal

        # Effective CR: how much did BG rise per carb?
        # If profile_cr is correct, carbs/profile_cr units of insulin should
        # cover the carbs. The actual bolus covers bolus*profile_cr grams.
        # If bg_rise > 0, we under-dosed. effective_cr > profile_cr.
        if bolus > 0 and carbs > 0:
            covered_carbs = bolus * profile_cr
            cr_ratio = carbs / covered_carbs  # >1 = under-bolused
            if 0.2 < cr_ratio < 5.0:
                cr_ratios.append(cr_ratio)

    if len(cr_ratios) >= 3:
        return float(np.median(cr_ratios)), len(cr_ratios)
    return None, 0


def main():
    print("=" * 70)
    print("EXP-2622: Advisory Convergence — Minimum Data Requirements")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    # Check data span per patient
    print("\n--- Data span per patient ---")
    patient_spans = {}
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid]
        span = (pdf['timestamp'].max() - pdf['timestamp'].min()).days
        patient_spans[pid] = span
        print(f"  {pid}: {span} days, {len(pdf)} rows")

    # Only include patients with ≥ 30 days
    eligible = [pid for pid, span in patient_spans.items() if span >= 30]
    print(f"\nEligible patients (≥30 days): {len(eligible)}")

    # Step 1: ISF convergence
    print("\n--- Step 1: ISF Convergence ---")
    isf_convergence = {}
    for pid in eligible:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)
        max_days = patient_spans[pid]
        results = []
        for n_days in DATA_WINDOWS:
            if n_days > max_days:
                break
            isf_ratio, n_corr = compute_isf_for_window(pdf, n_days)
            results.append({
                'days': n_days,
                'isf_ratio': isf_ratio,
                'n_corrections': n_corr,
            })

        # Also compute full-data ISF as reference
        isf_full, n_full = compute_isf_for_window(pdf, max_days)

        isf_convergence[pid] = {
            'windows': results,
            'full_isf': isf_full,
            'full_n': n_full,
            'max_days': max_days,
        }

        if isf_full is not None:
            print(f"  {pid} (full ISF={isf_full:.2f}, n={n_full}):")
            for r in results:
                if r['isf_ratio'] is not None:
                    pct_diff = abs(r['isf_ratio'] - isf_full) / isf_full * 100
                    print(f"    {r['days']:3d}d: ISF={r['isf_ratio']:.2f} "
                          f"(Δ={pct_diff:.1f}%, n={r['n_corrections']}) "
                          f"{'✓' if pct_diff < 10 else '✗'}")
                else:
                    print(f"    {r['days']:3d}d: insufficient data")

    # Step 2: CR convergence
    print("\n--- Step 2: CR Convergence ---")
    cr_convergence = {}
    for pid in eligible:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)
        max_days = patient_spans[pid]
        results = []
        for n_days in DATA_WINDOWS:
            if n_days > max_days:
                break
            cr_ratio, n_meals = compute_cr_for_window(pdf, n_days)
            results.append({
                'days': n_days,
                'cr_ratio': cr_ratio,
                'n_meals': n_meals,
            })

        cr_full, n_full = compute_cr_for_window(pdf, max_days)
        cr_convergence[pid] = {
            'windows': results,
            'full_cr': cr_full,
            'full_n': n_full,
            'max_days': max_days,
        }

        if cr_full is not None:
            print(f"  {pid} (full CR_ratio={cr_full:.2f}, n={n_full}):")
            for r in results:
                if r['cr_ratio'] is not None:
                    pct_diff = abs(r['cr_ratio'] - cr_full) / cr_full * 100
                    print(f"    {r['days']:3d}d: CR={r['cr_ratio']:.2f} "
                          f"(Δ={pct_diff:.1f}%, n={r['n_meals']}) "
                          f"{'✓' if pct_diff < 10 else '✗'}")
                else:
                    print(f"    {r['days']:3d}d: insufficient data")

    # Step 3: H1 — ISF stabilizes by 14 days
    print("\n--- Step 3: H1 — ISF Stable by 14 Days ---")
    h1_count = 0
    h1_total = 0
    for pid, data in isf_convergence.items():
        if data['full_isf'] is None:
            continue
        h1_total += 1
        # Check 14-day value
        day14 = [w for w in data['windows'] if w['days'] == 14]
        if day14 and day14[0]['isf_ratio'] is not None:
            pct_diff = abs(day14[0]['isf_ratio'] - data['full_isf']) / data['full_isf'] * 100
            if pct_diff < 10:
                h1_count += 1
                print(f"  {pid}: ✓ (14d ISF={day14[0]['isf_ratio']:.2f}, "
                      f"full={data['full_isf']:.2f}, Δ={pct_diff:.1f}%)")
            else:
                print(f"  {pid}: ✗ (14d ISF={day14[0]['isf_ratio']:.2f}, "
                      f"full={data['full_isf']:.2f}, Δ={pct_diff:.1f}%)")
        else:
            print(f"  {pid}: no 14d data")

    h1_confirmed = h1_count >= 8
    print(f"\nH1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}: "
          f"{h1_count}/{h1_total} stable by 14 days")

    # Step 4: H2 — CR stabilizes by 21 days
    print("\n--- Step 4: H2 — CR Stable by 21 Days ---")
    h2_count = 0
    h2_total = 0
    for pid, data in cr_convergence.items():
        if data['full_cr'] is None:
            continue
        h2_total += 1
        day21 = [w for w in data['windows'] if w['days'] == 21]
        if day21 and day21[0]['cr_ratio'] is not None:
            pct_diff = abs(day21[0]['cr_ratio'] - data['full_cr']) / data['full_cr'] * 100
            if pct_diff < 10:
                h2_count += 1
                print(f"  {pid}: ✓ (21d CR={day21[0]['cr_ratio']:.2f}, "
                      f"full={data['full_cr']:.2f}, Δ={pct_diff:.1f}%)")
            else:
                print(f"  {pid}: ✗ (21d CR={day21[0]['cr_ratio']:.2f}, "
                      f"full={data['full_cr']:.2f}, Δ={pct_diff:.1f}%)")
        else:
            print(f"  {pid}: no 21d data")

    h2_confirmed = h2_count >= 6
    print(f"\nH2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}: "
          f"{h2_count}/{h2_total} stable by 21 days")

    # Step 5: H3 — Direction stabilizes before magnitude
    print("\n--- Step 5: H3 — Direction Stable by 7 Days ---")
    h3_count = 0
    h3_total = 0
    for pid, data in isf_convergence.items():
        if data['full_isf'] is None:
            continue
        full_direction = 'increase' if data['full_isf'] > 1.1 else ('decrease' if data['full_isf'] < 0.9 else 'adequate')

        day7 = [w for w in data['windows'] if w['days'] == 7]
        if day7 and day7[0]['isf_ratio'] is not None:
            h3_total += 1
            d7_direction = 'increase' if day7[0]['isf_ratio'] > 1.1 else ('decrease' if day7[0]['isf_ratio'] < 0.9 else 'adequate')
            match = d7_direction == full_direction
            if match:
                h3_count += 1
            print(f"  {pid}: 7d={d7_direction} ({day7[0]['isf_ratio']:.2f}), "
                  f"full={full_direction} ({data['full_isf']:.2f}), "
                  f"{'✓' if match else '✗'}")

    h3_confirmed = h3_count >= 8
    print(f"\nH3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}: "
          f"{h3_count}/{h3_total} direction correct by 7 days")

    # Step 6: H4 — More corrections = faster stabilization
    print("\n--- Step 6: H4 — Corrections vs Convergence Speed ---")
    convergence_data = []
    for pid, data in isf_convergence.items():
        if data['full_isf'] is None or data['full_n'] < 5:
            continue
        # Find first window where ISF is within 10% of full
        days_to_stable = None
        for w in data['windows']:
            if w['isf_ratio'] is not None:
                pct_diff = abs(w['isf_ratio'] - data['full_isf']) / data['full_isf'] * 100
                if pct_diff < 10:
                    days_to_stable = w['days']
                    break

        if days_to_stable is not None:
            convergence_data.append({
                'patient_id': pid,
                'n_corrections': data['full_n'],
                'days_to_stable': days_to_stable,
            })

    if len(convergence_data) >= 5:
        n_corrs = [d['n_corrections'] for d in convergence_data]
        days = [d['days_to_stable'] for d in convergence_data]
        r, p = spearmanr(n_corrs, days)
        h4_confirmed = r < -0.3 and p < 0.1
        print(f"\nSpearman r = {r:.3f}, p = {p:.3f}")
        for d in sorted(convergence_data, key=lambda x: x['n_corrections']):
            print(f"  {d['patient_id']}: {d['n_corrections']} corrections, "
                  f"stable at {d['days_to_stable']} days")
        print(f"\nH4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}: "
              f"r={'<' if r < -0.3 else '>='} -0.3")
    else:
        h4_confirmed = False
        print("H4: Insufficient data")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2622")
    print("=" * 70)
    confirmations = {
        'H1_isf_stable_14d': h1_confirmed,
        'H2_cr_stable_21d': h2_confirmed,
        'H3_direction_stable_7d': h3_confirmed,
        'H4_more_corrections_faster': h4_confirmed,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    # Save results
    output = {
        'experiment': 'EXP-2622',
        'title': 'Advisory Convergence — Minimum Data Requirements',
        'hypotheses': confirmations,
        'isf_convergence': isf_convergence,
        'cr_convergence': cr_convergence,
        'convergence_speed': convergence_data if convergence_data else [],
    }
    outfile = OUTDIR / 'exp-2622_advisory_convergence.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
