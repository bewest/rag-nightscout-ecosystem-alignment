#!/usr/bin/env python3
"""EXP-2623: Multi-Feature ISF Prediction

EXP-2619 showed individual metabolic features explain ≤23% of per-window
ISF variance, with different features best for different patients. Can a
multi-feature regression (combining glucose_std, cum_carbs, mean_glucose,
carb_insulin_ratio) explain more ISF variance?

Hypotheses:
  H1: Multi-feature regression R² > best single-feature R² for ≥ 6/9
      FULL patients (combination captures complementary signals).
  H2: Mean multi-patient R² ≥ 0.20 (explaining at least 20% of ISF
      variance across the cohort).
  H3: A consistent feature subset (≤ 3 features) works for ≥ 6/9
      patients (universal model possible).
  H4: Adding loop workload (actual/scheduled basal ratio) as a feature
      improves R² by ≥ 0.05 for ≥ 4/9 patients.

Requires: FULL telemetry patients with correction events.
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

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df[df['patient_id'].isin(FULL_PATIENTS)]


def extract_correction_windows(pdf, profile_isf):
    """Extract correction windows and compute ISF ratio + context features."""
    windows = []
    pdf = pdf.sort_values('timestamp').reset_index(drop=True)

    corrections = pdf[
        (pdf['bolus'] > 0.5) &
        ((pdf['carbs'].isna()) | (pdf['carbs'] <= 1)) &
        (pdf['sgv'] > 150) &
        (pdf['scheduled_isf'].notna())
    ]

    for idx in corrections.index:
        pos = pdf.index.get_loc(idx)
        if pos + 23 >= len(pdf) or pos < 24:
            continue

        window = pdf.iloc[pos:pos+24]
        if window['sgv'].isna().sum() > 5:
            continue

        actual_drop = window['sgv'].iloc[0] - window['sgv'].iloc[-1]
        bolus = window['bolus'].iloc[0]
        expected_drop = bolus * profile_isf
        if expected_drop <= 0:
            continue

        isf_ratio = actual_drop / expected_drop
        if not (0.1 < isf_ratio < 5.0):
            continue

        # Context features from preceding 24h
        lookback_start = max(0, pos - 288)  # 288 = 24h at 5min
        lookback = pdf.iloc[lookback_start:pos]

        # Glucose features
        lb_glucose = lookback['sgv'].dropna()
        glucose_std = float(lb_glucose.std()) if len(lb_glucose) > 10 else np.nan
        mean_glucose = float(lb_glucose.mean()) if len(lb_glucose) > 10 else np.nan
        glucose_cv = glucose_std / mean_glucose if mean_glucose > 0 else np.nan

        # Carb/insulin features
        cum_carbs = float(lookback['carbs'].sum())
        cum_bolus = float(lookback['bolus'].sum())
        cum_iob = float(lookback['iob'].mean()) if 'iob' in lookback.columns else np.nan
        carb_insulin_ratio = cum_carbs / cum_bolus if cum_bolus > 0 else np.nan

        # Loop workload (actual/scheduled basal ratio)
        if 'actual_basal_rate' in lookback.columns and 'scheduled_basal_rate' in lookback.columns:
            sched = lookback['scheduled_basal_rate']
            actual = lookback['actual_basal_rate']
            valid = sched.notna() & actual.notna() & (sched > 0)
            if valid.sum() > 10:
                workload_ratio = float((actual[valid] / sched[valid]).mean())
            else:
                workload_ratio = np.nan
        else:
            workload_ratio = np.nan

        # Time features
        hour = float(window['timestamp'].iloc[0].hour)
        current_bg = float(window['sgv'].iloc[0])

        windows.append({
            'isf_ratio': isf_ratio,
            'glucose_std': glucose_std,
            'mean_glucose': mean_glucose,
            'glucose_cv': glucose_cv,
            'cum_carbs': cum_carbs,
            'cum_bolus': cum_bolus,
            'mean_iob': cum_iob,
            'carb_insulin_ratio': carb_insulin_ratio,
            'workload_ratio': workload_ratio,
            'hour': hour,
            'current_bg': current_bg,
        })

    return pd.DataFrame(windows)


def regression_analysis(wdf, features, target='isf_ratio'):
    """Run OLS regression and return R², coefficients."""
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    valid = wdf[features + [target]].dropna()
    if len(valid) < 20:
        return None

    X = valid[features].values
    y = valid[target].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LinearRegression()
    model.fit(X_scaled, y)
    r2 = model.score(X_scaled, y)

    return {
        'r2': float(r2),
        'n': len(valid),
        'coefficients': {f: float(c) for f, c in zip(features, model.coef_)},
        'intercept': float(model.intercept_),
    }


def main():
    print("=" * 70)
    print("EXP-2623: Multi-Feature ISF Prediction")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    base_features = ['glucose_std', 'mean_glucose', 'cum_carbs',
                     'carb_insulin_ratio', 'hour', 'current_bg']
    all_features = base_features + ['workload_ratio']

    results = {}

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid]
        profile_isf = pdf['scheduled_isf'].median()
        if pd.isna(profile_isf) or profile_isf <= 0:
            continue

        wdf = extract_correction_windows(pdf, profile_isf)
        if len(wdf) < 20:
            print(f"  {pid}: skip ({len(wdf)} windows)")
            continue

        print(f"\n  {pid}: {len(wdf)} correction windows")

        # Single-feature R² (baseline from EXP-2619)
        single_best_r2 = 0
        single_best_feat = None
        for feat in base_features:
            sr = regression_analysis(wdf, [feat])
            if sr and sr['r2'] > single_best_r2:
                single_best_r2 = sr['r2']
                single_best_feat = feat

        print(f"    Best single: {single_best_feat} R²={single_best_r2:.3f}")

        # Multi-feature: all base features
        multi_base = regression_analysis(wdf, base_features)
        if multi_base:
            print(f"    Multi-base (6 feat): R²={multi_base['r2']:.3f}")
            # Show top 3 coefficients
            sorted_coefs = sorted(multi_base['coefficients'].items(),
                                  key=lambda x: abs(x[1]), reverse=True)
            for feat, coef in sorted_coefs[:3]:
                print(f"      {feat}: β={coef:+.3f}")

        # Multi-feature: with workload ratio
        multi_all = regression_analysis(wdf, all_features)
        if multi_all:
            print(f"    Multi+workload (7 feat): R²={multi_all['r2']:.3f}")
            workload_improvement = multi_all['r2'] - (multi_base['r2'] if multi_base else 0)
            print(f"      Workload adds: ΔR²={workload_improvement:+.3f}")

        # Best 3-feature subset (exhaustive search)
        from itertools import combinations
        best_3_r2 = 0
        best_3_feats = None
        for combo in combinations(base_features, 3):
            sr = regression_analysis(wdf, list(combo))
            if sr and sr['r2'] > best_3_r2:
                best_3_r2 = sr['r2']
                best_3_feats = combo

        if best_3_feats:
            print(f"    Best 3-feat: {best_3_feats} R²={best_3_r2:.3f}")

        results[pid] = {
            'n_windows': len(wdf),
            'single_best_feat': single_best_feat,
            'single_best_r2': single_best_r2,
            'multi_base_r2': multi_base['r2'] if multi_base else None,
            'multi_all_r2': multi_all['r2'] if multi_all else None,
            'best_3_feats': list(best_3_feats) if best_3_feats else None,
            'best_3_r2': best_3_r2,
            'multi_base': multi_base,
            'multi_all': multi_all,
        }

    # H1: Multi > single for ≥ 6/9
    print("\n--- H1: Multi-feature > single-feature ---")
    h1_count = 0
    h1_total = 0
    for pid, r in results.items():
        if r['multi_base_r2'] is not None:
            h1_total += 1
            improvement = r['multi_base_r2'] - r['single_best_r2']
            if improvement > 0:
                h1_count += 1
            print(f"  {pid}: single={r['single_best_r2']:.3f}, "
                  f"multi={r['multi_base_r2']:.3f}, "
                  f"Δ={improvement:+.3f} {'✓' if improvement > 0 else '✗'}")

    h1_confirmed = h1_count >= 6
    print(f"\nH1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}: "
          f"{h1_count}/{h1_total} show multi > single")

    # H2: Mean R² ≥ 0.20
    print("\n--- H2: Mean multi-patient R² ≥ 0.20 ---")
    r2_values = [r['multi_base_r2'] for r in results.values()
                 if r['multi_base_r2'] is not None]
    mean_r2 = np.mean(r2_values) if r2_values else 0
    h2_confirmed = mean_r2 >= 0.20
    print(f"  Mean R² = {mean_r2:.3f}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Consistent 3-feature subset
    print("\n--- H3: Consistent 3-feature subset ---")
    feat_counts = {}
    for pid, r in results.items():
        if r['best_3_feats']:
            for f in r['best_3_feats']:
                feat_counts[f] = feat_counts.get(f, 0) + 1

    print("  Feature frequency in best-3 subsets:")
    for f, c in sorted(feat_counts.items(), key=lambda x: -x[1]):
        print(f"    {f}: {c}/{len(results)}")

    # Check if any 3-feature combo is best for ≥ 6/9
    combo_counts = {}
    for pid, r in results.items():
        if r['best_3_feats']:
            key = tuple(sorted(r['best_3_feats']))
            combo_counts[key] = combo_counts.get(key, 0) + 1

    most_common_combo = max(combo_counts.items(), key=lambda x: x[1]) if combo_counts else (None, 0)
    h3_confirmed = most_common_combo[1] >= 6
    print(f"\n  Most common combo: {most_common_combo[0]} ({most_common_combo[1]} patients)")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # H4: Workload adds ≥ 0.05 R²
    print("\n--- H4: Workload ratio adds ≥ 0.05 R² ---")
    h4_count = 0
    h4_total = 0
    for pid, r in results.items():
        if r['multi_base_r2'] is not None and r['multi_all_r2'] is not None:
            h4_total += 1
            improvement = r['multi_all_r2'] - r['multi_base_r2']
            if improvement >= 0.05:
                h4_count += 1
            print(f"  {pid}: base={r['multi_base_r2']:.3f}, "
                  f"+workload={r['multi_all_r2']:.3f}, "
                  f"Δ={improvement:+.3f} {'✓' if improvement >= 0.05 else '✗'}")

    h4_confirmed = h4_count >= 4
    print(f"\nH4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}: "
          f"{h4_count}/{h4_total} show ≥0.05 R² from workload")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2623")
    print("=" * 70)
    confirmations = {
        'H1_multi_beats_single': h1_confirmed,
        'H2_mean_r2_above_20pct': h2_confirmed,
        'H3_consistent_3_features': h3_confirmed,
        'H4_workload_adds_signal': h4_confirmed,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    output = {
        'experiment': 'EXP-2623',
        'title': 'Multi-Feature ISF Prediction',
        'hypotheses': confirmations,
        'per_patient': results,
        'mean_multi_r2': mean_r2,
        'feature_frequency': feat_counts,
    }
    outfile = OUTDIR / 'exp-2623_multi_feature_isf.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
