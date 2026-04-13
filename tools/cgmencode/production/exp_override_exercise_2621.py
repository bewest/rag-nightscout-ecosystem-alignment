#!/usr/bin/env python3
"""EXP-2621: Override & Exercise Impact on ISF Calibration

The parquet has `override_active` (100% fill) and `exercise_active` (100% fill).
These represent user-initiated settings adjustments (temporary target changes,
exercise mode, etc.) that modify insulin delivery behavior.

Hypotheses:
  H1: Override-active periods show different ISF than non-override periods
      (median ISF differs by ≥ 0.15) for ≥ 6/12 FULL patients.
  H2: Exercise-active periods show different ISF than non-exercise periods
      (median ISF differs by ≥ 0.15) for ≥ 4/12 patients with exercise events.
  H3: Filtering OUT override/exercise periods from calibration reduces ISF
      variance (CV decreases ≥ 5%) for ≥ 6/12 patients.
  H4: Override frequency (% of time in override) correlates with settings
      deviation |ISF_ratio - 1| (r > 0.3) — more overrides = worse settings.

Requires: FULL telemetry patients only.
"""
import json
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path

PROJ = Path(__file__).resolve().parents[3]
PARQUET = PROJ / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
OUTDIR = PROJ / 'externals' / 'experiments'
OUTDIR.mkdir(parents=True, exist_ok=True)

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k',
                 'odc-39819048', 'odc-49141524', 'odc-58680324',
                 'odc-61403732', 'odc-74077367', 'odc-86025410', 'odc-96254963']


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df[df['patient_id'].isin(FULL_PATIENTS)]


def compute_isf_by_context(df, context_col):
    """Compute ISF ratio for correction events split by a boolean context column."""
    results = []
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)

        # Find correction boluses
        corrections = pdf[
            (pdf['bolus'] > 0.5) &
            ((pdf['carbs'].isna()) | (pdf['carbs'] <= 1)) &
            (pdf['sgv'] > 150) &
            (pdf['scheduled_isf'].notna()) & (pdf['scheduled_isf'] > 0)
        ]

        if len(corrections) < 10:
            continue

        profile_isf = pdf['scheduled_isf'].median()

        # Split corrections by context
        context_on = corrections[corrections[context_col] > 0]
        context_off = corrections[corrections[context_col] == 0]

        def compute_isf_ratios(subset):
            ratios = []
            for idx in subset.index:
                pos = pdf.index.get_loc(idx)
                if pos + 23 >= len(pdf):
                    continue
                window = pdf.iloc[pos:pos+24]
                if window['sgv'].isna().sum() > 5:
                    continue
                actual_drop = window['sgv'].iloc[0] - window['sgv'].iloc[-1]
                bolus = window['bolus'].iloc[0]
                expected_drop = bolus * profile_isf
                if expected_drop > 0:
                    ratio = actual_drop / expected_drop
                    if 0.1 < ratio < 5.0:
                        ratios.append(ratio)
            return ratios

        ratios_on = compute_isf_ratios(context_on)
        ratios_off = compute_isf_ratios(context_off)

        pct_active = float((pdf[context_col] > 0).mean())

        result = {
            'patient_id': pid,
            'context': context_col,
            'pct_active': pct_active,
            'n_on': len(ratios_on),
            'n_off': len(ratios_off),
        }

        if len(ratios_on) >= 3:
            result['isf_on_median'] = float(np.median(ratios_on))
            result['isf_on_mean'] = float(np.mean(ratios_on))
            result['isf_on_cv'] = float(np.std(ratios_on) / np.mean(ratios_on))
        if len(ratios_off) >= 3:
            result['isf_off_median'] = float(np.median(ratios_off))
            result['isf_off_mean'] = float(np.mean(ratios_off))
            result['isf_off_cv'] = float(np.std(ratios_off) / np.mean(ratios_off))

        # Combined (all corrections)
        all_ratios = ratios_on + ratios_off
        if len(all_ratios) >= 3:
            result['isf_all_median'] = float(np.median(all_ratios))
            result['isf_all_cv'] = float(np.std(all_ratios) / np.mean(all_ratios))

        # Filtered (exclude context_on) CV improvement
        if len(ratios_off) >= 3 and len(all_ratios) >= 3:
            cv_all = np.std(all_ratios) / np.mean(all_ratios)
            cv_filtered = np.std(ratios_off) / np.mean(ratios_off)
            result['cv_reduction_pct'] = float((cv_all - cv_filtered) / cv_all * 100)

        # ISF difference
        if 'isf_on_median' in result and 'isf_off_median' in result:
            result['isf_diff'] = float(abs(result['isf_on_median'] - result['isf_off_median']))

        results.append(result)

    return results


def analyze_override_types(df):
    """Analyze what override types exist and their frequency."""
    results = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid]
        override_types = pdf['override_type'].value_counts()
        result = {
            'patient_id': pid,
            'override_types': {str(k): int(v) for k, v in override_types.items()},
            'pct_override_active': float((pdf['override_active'] > 0).mean()),
            'pct_exercise_active': float((pdf['exercise_active'] > 0).mean()),
            'total_rows': len(pdf),
        }
        results.append(result)
    return results


def main():
    print("=" * 70)
    print("EXP-2621: Override & Exercise Impact on ISF")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()
    print(f"Loaded {len(df)} rows for {df['patient_id'].nunique()} FULL patients")

    # Step 0: Override/exercise prevalence
    print("\n--- Step 0: Override/Exercise Prevalence ---")
    prevalence = analyze_override_types(df)
    for p in prevalence:
        print(f"  {p['patient_id']}: override={p['pct_override_active']:.1%}, "
              f"exercise={p['pct_exercise_active']:.1%}, "
              f"types={p['override_types']}")

    # Step 1: H1 — Override impact on ISF
    print("\n--- Step 1: H1 — Override Impact on ISF ---")
    override_results = compute_isf_by_context(df, 'override_active')
    h1_count = 0
    h1_total = 0
    for r in override_results:
        if 'isf_diff' in r:
            h1_total += 1
            if r['isf_diff'] >= 0.15:
                h1_count += 1
            print(f"  {r['patient_id']}: ISF_on={r.get('isf_on_median', 'N/A'):.2f}, "
                  f"ISF_off={r.get('isf_off_median', 'N/A'):.2f}, "
                  f"diff={r['isf_diff']:.2f}, n_on={r['n_on']}, n_off={r['n_off']}, "
                  f"{'✓' if r['isf_diff'] >= 0.15 else '✗'}")
        elif r['n_on'] == 0:
            print(f"  {r['patient_id']}: no override corrections (override pct={r['pct_active']:.1%})")
        else:
            print(f"  {r['patient_id']}: n_on={r['n_on']}, n_off={r['n_off']} (insufficient)")

    h1_confirmed = h1_count >= 6 and h1_total >= 10
    print(f"\nH1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}: "
          f"{h1_count}/{h1_total} patients show ISF diff ≥ 0.15 during overrides")

    # Step 2: H2 — Exercise impact on ISF
    print("\n--- Step 2: H2 — Exercise Impact on ISF ---")
    exercise_results = compute_isf_by_context(df, 'exercise_active')
    h2_count = 0
    h2_total = 0
    for r in exercise_results:
        if 'isf_diff' in r:
            h2_total += 1
            if r['isf_diff'] >= 0.15:
                h2_count += 1
            print(f"  {r['patient_id']}: ISF_on={r.get('isf_on_median', 'N/A'):.2f}, "
                  f"ISF_off={r.get('isf_off_median', 'N/A'):.2f}, "
                  f"diff={r['isf_diff']:.2f}, n_on={r['n_on']}, n_off={r['n_off']}, "
                  f"{'✓' if r['isf_diff'] >= 0.15 else '✗'}")
        elif r['n_on'] == 0:
            print(f"  {r['patient_id']}: no exercise corrections (exercise pct={r['pct_active']:.1%})")
        else:
            print(f"  {r['patient_id']}: n_on={r['n_on']}, n_off={r['n_off']} (insufficient)")

    h2_threshold = max(4, h2_total // 3)
    h2_confirmed = h2_count >= h2_threshold and h2_total >= 4
    print(f"\nH2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}: "
          f"{h2_count}/{h2_total} patients show ISF diff ≥ 0.15 during exercise")

    # Step 3: H3 — Filtering out overrides reduces ISF variance
    print("\n--- Step 3: H3 — CV Reduction from Filtering ---")
    h3_count = 0
    h3_total = 0
    for r in override_results:
        if 'cv_reduction_pct' in r:
            h3_total += 1
            if r['cv_reduction_pct'] >= 5.0:
                h3_count += 1
            print(f"  {r['patient_id']}: CV_all={r.get('isf_all_cv', 0):.2f}, "
                  f"CV_filtered={r.get('isf_off_cv', 0):.2f}, "
                  f"reduction={r['cv_reduction_pct']:+.1f}%, "
                  f"{'✓' if r['cv_reduction_pct'] >= 5.0 else '✗'}")

    h3_confirmed = h3_count >= 6 and h3_total >= 10
    print(f"\nH3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}: "
          f"{h3_count}/{h3_total} patients show ≥5% CV reduction from filtering")

    # Step 4: H4 — Override frequency correlates with settings deviation
    print("\n--- Step 4: H4 — Override % vs Settings Deviation ---")
    paired = []
    for r in override_results:
        if 'isf_all_median' in r and r['n_off'] >= 3:
            paired.append({
                'patient_id': r['patient_id'],
                'pct_override': r['pct_active'],
                'settings_deviation': abs(r['isf_all_median'] - 1.0),
            })

    if len(paired) >= 5:
        from scipy.stats import spearmanr
        overrides = [p['pct_override'] for p in paired]
        deviations = [p['settings_deviation'] for p in paired]
        r, p = spearmanr(overrides, deviations)
        h4_confirmed = abs(r) > 0.3 and p < 0.1
        print(f"\nSpearman r = {r:.3f}, p = {p:.3f}")
        for pp in paired:
            print(f"  {pp['patient_id']}: override={pp['pct_override']:.1%}, "
                  f"deviation={pp['settings_deviation']:.2f}")
        print(f"\nH4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}: "
              f"|r|={'>' if abs(r) > 0.3 else '<='} 0.3")
    else:
        h4_confirmed = False
        print("H4: Insufficient data")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2621")
    print("=" * 70)
    confirmations = {
        'H1_override_isf_split': h1_confirmed,
        'H2_exercise_isf_split': h2_confirmed,
        'H3_cv_reduction_filtering': h3_confirmed,
        'H4_override_freq_vs_deviation': h4_confirmed,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    # Save results
    output = {
        'experiment': 'EXP-2621',
        'title': 'Override & Exercise Impact on ISF',
        'hypotheses': confirmations,
        'override_prevalence': prevalence,
        'override_isf_results': override_results,
        'exercise_isf_results': exercise_results,
    }
    outfile = OUTDIR / 'exp-2621_override_exercise_isf.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
