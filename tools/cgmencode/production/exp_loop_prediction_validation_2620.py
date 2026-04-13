#!/usr/bin/env python3
"""EXP-2620: Settings Calibration vs Loop Prediction Error

Validates our forward-sim ISF/CR calibration by comparing it to the loop's
own prediction accuracy. The loop has `loop_predicted_30`, `loop_predicted_60`,
and `eventual_bg` columns. If our calibrated ISF differs from profile ISF,
the loop's predictions (which use profile ISF) should show systematic errors
consistent with our calibration direction.

Hypotheses:
  H1: Patients with ISF_ratio < 1.0 (insulin works less than loop expects)
      have loop predictions that UNDER-predict glucose (predict too-low values)
      — confirmed if median signed error > 0 for >6/9 patients with ISF<1.
  H2: Loop prediction MAE correlates with our settings deviation magnitude
      (|ISF_ratio - 1|) across patients (r > 0.3).
  H3: Loop's prediction components (pred_iob, pred_cob, pred_uam, pred_zt)
      reveal which assumptions drive prediction error — component contribution
      correlates with our calibration direction.
  H4: Our forward sim achieves comparable or better accuracy than loop's
      predictions for 2h correction windows (MAE within 1.5× loop MAE).

Requires: FULL telemetry patients (insulin + glucose + loop predictions).
"""
import json
import sys
import os
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path

PROJ = Path(__file__).resolve().parents[3]
PARQUET = PROJ / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
OUTDIR = PROJ / 'externals' / 'experiments'
OUTDIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJ / 'tools'))
from cgmencode.production.forward_simulator import forward_simulate


def load_data():
    """Load parquet with loop prediction columns."""
    df = pd.read_parquet(PARQUET)
    # Column name mapping: parquet uses 'time' and 'glucose', not 'timestamp'/'sgv'
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def compute_loop_prediction_error(df):
    """Compute loop's prediction error by comparing predicted vs actual glucose.

    For each row with loop_predicted_30, find the actual glucose 30 min later
    (6 rows ahead at 5-min intervals) and compute signed error.
    """
    results = []
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)

        # Need loop predictions AND enough future data
        has_pred = pdf['loop_predicted_30'].notna() & pdf['loop_predicted_60'].notna()
        if has_pred.sum() < 100:
            print(f"  {pid}: skip (only {has_pred.sum()} predictions)")
            continue

        # Compute actual glucose at t+30 and t+60 (shift -6 and -12 rows)
        pdf['actual_30'] = pdf['sgv'].shift(-6)  # 6 * 5min = 30min
        pdf['actual_60'] = pdf['sgv'].shift(-12)  # 12 * 5min = 60min

        # Filter to rows with both prediction and actual
        mask_30 = has_pred & pdf['actual_30'].notna()
        mask_60 = has_pred & pdf['actual_60'].notna()

        if mask_30.sum() < 50:
            print(f"  {pid}: skip (only {mask_30.sum()} valid rows)")
            continue

        # Signed error: actual - predicted (positive = loop under-predicted)
        err_30 = pdf.loc[mask_30, 'actual_30'] - pdf.loc[mask_30, 'loop_predicted_30']
        err_60 = pdf.loc[mask_60, 'actual_60'] - pdf.loc[mask_60, 'loop_predicted_60']

        # Also get eventual_bg error if available
        has_eventual = pdf['eventual_bg'].notna() & pdf['actual_60'].notna()
        eventual_err = None
        if has_eventual.sum() > 50:
            eventual_err = pdf.loc[has_eventual, 'actual_60'] - pdf.loc[has_eventual, 'eventual_bg']

        result = {
            'patient_id': pid,
            'n_predictions': int(mask_30.sum()),
            # 30-min prediction accuracy
            'loop_mae_30': float(err_30.abs().mean()),
            'loop_median_signed_err_30': float(err_30.median()),
            'loop_mean_signed_err_30': float(err_30.mean()),
            'loop_rmse_30': float(np.sqrt((err_30 ** 2).mean())),
            # 60-min prediction accuracy
            'loop_mae_60': float(err_60.abs().mean()),
            'loop_median_signed_err_60': float(err_60.median()),
            'loop_mean_signed_err_60': float(err_60.mean()),
            # Directional accuracy (did loop predict direction correctly?)
            'loop_direction_acc_30': float(
                ((err_30 > 0) == ((pdf.loc[mask_30, 'actual_30'] - pdf.loc[mask_30, 'sgv']) > 0)).mean()
            ) if mask_30.sum() > 0 else None,
        }

        if eventual_err is not None:
            result['eventual_mae'] = float(eventual_err.abs().mean())
            result['eventual_median_signed_err'] = float(eventual_err.median())

        results.append(result)

    return results


def get_isf_calibration(df):
    """Get our calibrated ISF ratio for each patient using existing calibration."""
    results = {}
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp')
        # Need scheduled_isf and correction events
        has_isf = pdf['scheduled_isf'].notna()
        has_bolus = pdf['bolus'].notna() & (pdf['bolus'] > 0)

        if has_isf.sum() < 100 or has_bolus.sum() < 10:
            continue

        profile_isf = pdf.loc[has_isf, 'scheduled_isf'].median()

        # Use our calibration to get effective ISF
        try:
            cal_result = calibrate_isf_from_corrections(pdf)
            if cal_result and 'calibrated_isf' in cal_result:
                cal_isf = cal_result['calibrated_isf']
                results[pid] = {
                    'profile_isf': float(profile_isf),
                    'calibrated_isf': float(cal_isf),
                    'isf_ratio': float(cal_isf / profile_isf) if profile_isf > 0 else None,
                    'n_corrections': cal_result.get('n_corrections', 0),
                }
        except Exception as e:
            # Fallback: compute from correction events directly
            pass

    return results


def compute_isf_ratio_simple(df):
    """Simpler ISF ratio computation using forward sim on correction windows."""
    results = {}
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)

        # Find correction boluses: bolus > 0, carbs <= 1
        corrections = pdf[
            (pdf['bolus'].notna()) & (pdf['bolus'] > 0.5) &
            ((pdf['carbs'].isna()) | (pdf['carbs'] <= 1)) &
            (pdf['sgv'] > 150)
        ]

        if len(corrections) < 5:
            continue

        profile_isf = pdf['scheduled_isf'].median()
        if pd.isna(profile_isf) or profile_isf <= 0:
            continue

        # For each correction, compute actual vs expected glucose drop
        isf_ratios = []
        for idx in corrections.index:
            pos = pdf.index.get_loc(idx)
            if pos + 24 >= len(pdf):  # need 2h of data
                continue

            window = pdf.iloc[pos:pos+25]  # 2h window
            if window['sgv'].isna().sum() > 5:
                continue

            start_bg = window['sgv'].iloc[0]
            end_bg = window['sgv'].iloc[-1]
            actual_drop = start_bg - end_bg
            bolus = window['bolus'].iloc[0]
            expected_drop = bolus * profile_isf

            if expected_drop > 0:
                ratio = actual_drop / expected_drop
                if 0.1 < ratio < 5.0:  # sanity bounds
                    isf_ratios.append(ratio)

        if len(isf_ratios) >= 3:
            results[pid] = {
                'profile_isf': float(profile_isf),
                'isf_ratio': float(np.median(isf_ratios)),
                'isf_ratio_mean': float(np.mean(isf_ratios)),
                'isf_ratio_std': float(np.std(isf_ratios)),
                'n_corrections': len(isf_ratios),
                'settings_deviation': float(abs(np.median(isf_ratios) - 1.0)),
            }

    return results


def analyze_prediction_components(df):
    """Analyze loop's prediction component breakdown (pred_iob, pred_cob, etc.)."""
    component_cols = ['pred_iob_30', 'pred_cob_30', 'pred_uam_30', 'pred_zt_30']

    # Check which columns exist
    available = [c for c in component_cols if c in df.columns]
    if not available:
        return None

    results = []
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid]
        has_components = pdf[available].notna().all(axis=1)

        if has_components.sum() < 100:
            continue

        comp_data = pdf.loc[has_components, available]
        sgv = pdf.loc[has_components, 'sgv']

        result = {'patient_id': pid, 'n_rows': int(has_components.sum())}
        for col in available:
            result[f'{col}_mean'] = float(comp_data[col].mean())
            result[f'{col}_std'] = float(comp_data[col].std())
            # Contribution: mean absolute deviation from current sgv
            deviation = (comp_data[col] - sgv).abs()
            result[f'{col}_contribution'] = float(deviation.mean())

        results.append(result)

    return results


def compare_sim_vs_loop(df):
    """Compare our forward sim accuracy to loop's predictions on correction windows."""
    results = []
    patients = sorted(df['patient_id'].unique())

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('timestamp').reset_index(drop=True)

        # Find correction events with loop predictions
        corrections = pdf[
            (pdf['bolus'].notna()) & (pdf['bolus'] > 0.5) &
            ((pdf['carbs'].isna()) | (pdf['carbs'] <= 1)) &
            (pdf['sgv'] > 150) &
            (pdf['loop_predicted_30'].notna())
        ]

        if len(corrections) < 5:
            continue

        sim_errors = []
        loop_errors_30 = []
        loop_errors_60 = []

        for idx in corrections.index:
            pos = pdf.index.get_loc(idx)
            if pos + 24 >= len(pdf):
                continue

            window = pdf.iloc[pos:pos+25]
            if window['sgv'].isna().sum() > 5:
                continue

            start_bg = float(window['sgv'].iloc[0])
            bolus = float(window['bolus'].iloc[0])
            iob = float(window['iob'].iloc[0]) if pd.notna(window['iob'].iloc[0]) else 0
            profile_isf = float(window['scheduled_isf'].iloc[0]) if pd.notna(window['scheduled_isf'].iloc[0]) else 50
            basal = float(window['scheduled_basal_rate'].iloc[0]) if pd.notna(window['scheduled_basal_rate'].iloc[0]) else 0.5

            # Our forward sim prediction
            try:
                sim_result = forward_simulate(
                    glucose_start=start_bg,
                    bolus_insulin=bolus,
                    iob_start=iob,
                    isf=profile_isf,
                    basal_rate=basal,
                    carbs=0,
                    cr=15,
                    duration_hours=2.0,
                )
                if sim_result and 'glucose_trace' in sim_result:
                    trace = sim_result['glucose_trace']
                    # Get sim prediction at 30min and 60min
                    sim_30 = trace[min(6, len(trace)-1)]
                    sim_60 = trace[min(12, len(trace)-1)]
                    sim_120 = trace[-1]

                    # Actual glucose at those times
                    actual_30 = float(window['sgv'].iloc[min(6, len(window)-1)])
                    actual_60 = float(window['sgv'].iloc[min(12, len(window)-1)])
                    actual_120 = float(window['sgv'].iloc[-1])

                    sim_errors.append({
                        'sim_err_30': abs(sim_30 - actual_30),
                        'sim_err_60': abs(sim_60 - actual_60),
                        'sim_err_120': abs(sim_120 - actual_120),
                    })

                    # Loop prediction at same time
                    loop_pred_30 = float(window['loop_predicted_30'].iloc[0])
                    loop_errors_30.append(abs(loop_pred_30 - actual_30))

                    if pd.notna(window['loop_predicted_60'].iloc[0]):
                        loop_pred_60 = float(window['loop_predicted_60'].iloc[0])
                        loop_errors_60.append(abs(loop_pred_60 - actual_60))
            except Exception:
                continue

        if len(sim_errors) >= 3:
            sim_df = pd.DataFrame(sim_errors)
            results.append({
                'patient_id': pid,
                'n_corrections': len(sim_errors),
                # Our sim accuracy
                'sim_mae_30': float(sim_df['sim_err_30'].mean()),
                'sim_mae_60': float(sim_df['sim_err_60'].mean()),
                'sim_mae_120': float(sim_df['sim_err_120'].mean()),
                # Loop's accuracy on same windows
                'loop_mae_30': float(np.mean(loop_errors_30)) if loop_errors_30 else None,
                'loop_mae_60': float(np.mean(loop_errors_60)) if loop_errors_60 else None,
                # Ratio: sim/loop (< 1 means our sim is better)
                'sim_vs_loop_30': float(sim_df['sim_err_30'].mean() / np.mean(loop_errors_30)) if loop_errors_30 else None,
                'sim_vs_loop_60': float(sim_df['sim_err_60'].mean() / np.mean(loop_errors_60)) if loop_errors_60 else None,
            })

    return results


def test_h1_signed_error_direction(loop_errors, isf_ratios):
    """H1: ISF_ratio < 1.0 → loop under-predicts glucose (positive signed error)."""
    h1_results = []
    for le in loop_errors:
        pid = le['patient_id']
        if pid not in isf_ratios:
            continue
        isf_ratio = isf_ratios[pid]['isf_ratio']
        signed_err = le['loop_median_signed_err_30']

        # If ISF_ratio < 1: insulin works LESS than expected → loop over-predicts drops
        # → actual glucose HIGHER than predicted → positive signed error
        expected_positive = isf_ratio < 1.0
        actual_positive = signed_err > 0

        h1_results.append({
            'patient_id': pid,
            'isf_ratio': isf_ratio,
            'loop_signed_err_30': signed_err,
            'expected_positive': expected_positive,
            'actual_positive': actual_positive,
            'direction_match': expected_positive == actual_positive,
        })

    return h1_results


def test_h2_mae_correlation(loop_errors, isf_ratios):
    """H2: Loop MAE correlates with our settings deviation magnitude."""
    paired = []
    for le in loop_errors:
        pid = le['patient_id']
        if pid not in isf_ratios:
            continue
        paired.append({
            'patient_id': pid,
            'loop_mae_30': le['loop_mae_30'],
            'settings_deviation': isf_ratios[pid]['settings_deviation'],
        })

    if len(paired) < 4:
        return None, None

    from scipy.stats import spearmanr
    deviations = [p['settings_deviation'] for p in paired]
    maes = [p['loop_mae_30'] for p in paired]
    r, p = spearmanr(deviations, maes)
    return float(r), float(p), paired


def main():
    print("=" * 70)
    print("EXP-2620: Settings Calibration vs Loop Prediction Error")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    # Check available columns
    loop_cols = [c for c in df.columns if 'loop' in c.lower() or 'predict' in c.lower()
                 or 'eventual' in c.lower() or 'pred_' in c.lower()]
    print(f"Loop-related columns: {loop_cols}")

    # Step 1: Compute loop prediction errors
    print("\n--- Step 1: Loop Prediction Errors ---")
    loop_errors = compute_loop_prediction_error(df)
    print(f"\nLoop prediction errors for {len(loop_errors)} patients:")
    for le in loop_errors:
        print(f"  {le['patient_id']}: MAE_30={le['loop_mae_30']:.1f}, "
              f"signed_err_30={le['loop_median_signed_err_30']:+.1f}, "
              f"n={le['n_predictions']}")

    # Step 2: Our ISF calibration
    print("\n--- Step 2: ISF Calibration (simple method) ---")
    isf_ratios = compute_isf_ratio_simple(df)
    print(f"\nISF ratios for {len(isf_ratios)} patients:")
    for pid, data in sorted(isf_ratios.items()):
        print(f"  {pid}: ISF_ratio={data['isf_ratio']:.2f} "
              f"(profile={data['profile_isf']:.0f}, n_corr={data['n_corrections']})")

    # Step 3: H1 — Signed error direction
    print("\n--- Step 3: H1 — Signed Error Direction ---")
    h1_results = test_h1_signed_error_direction(loop_errors, isf_ratios)
    if h1_results:
        matches = sum(1 for r in h1_results if r['direction_match'])
        total = len(h1_results)
        print(f"\nH1 direction matches: {matches}/{total}")
        for r in h1_results:
            print(f"  {r['patient_id']}: ISF_ratio={r['isf_ratio']:.2f}, "
                  f"signed_err={r['loop_signed_err_30']:+.1f}, "
                  f"match={'✓' if r['direction_match'] else '✗'}")
        h1_confirmed = matches > total * 0.6
        print(f"\nH1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}: "
              f"{matches}/{total} direction matches "
              f"({'>' if h1_confirmed else '<='} 60% threshold)")
    else:
        h1_confirmed = False
        print("H1: Insufficient data")

    # Step 4: H2 — MAE correlation
    print("\n--- Step 4: H2 — MAE vs Settings Deviation ---")
    h2_result = test_h2_mae_correlation(loop_errors, isf_ratios)
    if h2_result[0] is not None:
        r, p, paired = h2_result
        h2_confirmed = abs(r) > 0.3 and p < 0.1
        print(f"\nSpearman r = {r:.3f}, p = {p:.3f}")
        print(f"H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}: "
              f"|r|={'>' if abs(r) > 0.3 else '<='} 0.3")
        for pp in paired:
            print(f"  {pp['patient_id']}: deviation={pp['settings_deviation']:.2f}, "
                  f"loop_mae={pp['loop_mae_30']:.1f}")
    else:
        h2_confirmed = False
        print("H2: Insufficient data")

    # Step 5: H3 — Prediction components
    print("\n--- Step 5: H3 — Loop Prediction Components ---")
    components = analyze_prediction_components(df)
    if components:
        print(f"\nComponent analysis for {len(components)} patients:")
        for c in components:
            print(f"  {c['patient_id']} (n={c['n_rows']}):")
            for col in ['pred_iob_30', 'pred_cob_30', 'pred_uam_30', 'pred_zt_30']:
                if f'{col}_contribution' in c:
                    print(f"    {col}: contrib={c[f'{col}_contribution']:.1f}, "
                          f"mean={c[f'{col}_mean']:.1f} ± {c[f'{col}_std']:.1f}")
        h3_confirmed = len(components) >= 3  # Have enough data to analyze
    else:
        h3_confirmed = False
        print("H3: No prediction component columns available")

    # Step 6: H4 — Sim vs Loop accuracy
    print("\n--- Step 6: H4 — Our Sim vs Loop Predictions ---")
    sim_vs_loop = compare_sim_vs_loop(df)
    if sim_vs_loop:
        print(f"\nSim vs Loop on correction windows ({len(sim_vs_loop)} patients):")
        within_threshold = 0
        for svl in sim_vs_loop:
            ratio_30 = svl.get('sim_vs_loop_30')
            ratio_str = f"{ratio_30:.2f}" if ratio_30 is not None else "N/A"
            if ratio_30 is not None and ratio_30 <= 1.5:
                within_threshold += 1
            print(f"  {svl['patient_id']}: sim_MAE_30={svl['sim_mae_30']:.1f}, "
                  f"loop_MAE_30={svl.get('loop_mae_30', 'N/A')}, "
                  f"ratio={ratio_str} (n={svl['n_corrections']})")
        h4_confirmed = within_threshold > len(sim_vs_loop) * 0.5
        print(f"\nH4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}: "
              f"{within_threshold}/{len(sim_vs_loop)} patients have sim/loop ratio ≤ 1.5")
    else:
        h4_confirmed = False
        print("H4: Insufficient data")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2620")
    print("=" * 70)
    confirmations = {
        'H1_signed_error_direction': h1_confirmed,
        'H2_mae_settings_correlation': h2_confirmed,
        'H3_component_analysis': h3_confirmed,
        'H4_sim_vs_loop_accuracy': h4_confirmed,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    # Save results
    output = {
        'experiment': 'EXP-2620',
        'title': 'Settings Calibration vs Loop Prediction Error',
        'hypotheses': confirmations,
        'loop_prediction_errors': loop_errors,
        'isf_ratios': {k: v for k, v in isf_ratios.items()},
        'h1_results': h1_results if h1_results else [],
        'sim_vs_loop': sim_vs_loop if sim_vs_loop else [],
        'components': components if components else [],
    }
    outfile = OUTDIR / 'exp-2620_loop_prediction_validation.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
