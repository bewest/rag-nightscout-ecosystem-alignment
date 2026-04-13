#!/usr/bin/env python3
"""EXP-2628: Autosens vs ISF Calibration Validation

The loop computes a sensitivity_ratio (autosens) that adjusts ISF
dynamically. Our calibration pipeline computes an effective ISF ratio
from correction windows. If both measure the same thing, they should
correlate. If they don't, they capture different aspects of insulin
sensitivity.

Hypotheses:
  H1: Per-patient mean sensitivity_ratio correlates with our ISF ratio
      (Spearman r > 0.3 across patients).
  H2: Within-patient, sensitivity_ratio temporal variation predicts
      per-window ISF variation (r > 0.2 for ≥ 5/9 patients).
  H3: sensitivity_ratio has lower CV than our per-window ISF
      (autosens smooths more aggressively).

Requires: FULL telemetry patients with sensitivity_ratio data.
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

sys.path.insert(0, str(PROJ / 'tools'))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def calibrate_isf_ratio(pdf, n_sample=200):
    """Calibrate ISF ratio from correction windows (simplified EXP-2582)."""
    pdf = pdf.sort_values('timestamp').reset_index(drop=True)
    glucose = pdf['sgv'].values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    isf_sched = pdf['scheduled_isf'].values.astype(float)
    cr_sched = pdf['scheduled_cr'].values.astype(float)
    basal_sched = pdf['scheduled_basal_rate'].values.astype(float)

    # Find correction windows: bolus > 0.5U, carbs < 1g, BG > 150
    corr_mask = (bolus > 0.5) & (carbs <= 1) & (glucose > 150) & ~np.isnan(glucose)
    corr_indices = np.where(corr_mask)[0]

    if len(corr_indices) < 10:
        return None, []

    # Sample corrections
    if len(corr_indices) > n_sample:
        rng = np.random.RandomState(42)
        corr_indices = rng.choice(corr_indices, n_sample, replace=False)

    isf_ratios = []
    window_data = []  # (timestamp, isf_ratio, sensitivity_ratio)

    for idx in corr_indices:
        end_idx = min(idx + 24, len(glucose) - 1)
        if np.isnan(glucose[end_idx]):
            continue

        start_bg = float(glucose[idx])
        actual_drop = start_bg - float(glucose[end_idx])
        bolus_u = float(bolus[idx])
        isf_val = float(isf_sched[idx])
        basal_val = float(basal_sched[idx])

        if pd.isna(isf_val) or isf_val <= 0 or bolus_u <= 0:
            continue

        # Simulate with profile ISF
        settings = TherapySettings(
            isf=isf_val,
            cr=float(cr_sched[idx]) if not pd.isna(cr_sched[idx]) else 10.0,
            basal_rate=basal_val if not pd.isna(basal_val) else 0.8,
            dia_hours=5.0,
        )
        events = [InsulinEvent(time_minutes=0, units=bolus_u)]
        try:
            result = forward_simulate(
                initial_glucose=start_bg,
                settings=settings,
                duration_hours=2.0,
                bolus_events=events,
            )
            predicted_drop = start_bg - result.glucose[-1]
        except Exception:
            continue

        if abs(predicted_drop) < 5:
            continue

        ratio = actual_drop / predicted_drop
        if 0.1 <= ratio <= 5.0:
            isf_ratios.append(ratio)
            # Get sensitivity_ratio at this time
            sens_r = pdf.iloc[idx].get('sensitivity_ratio', np.nan)
            ts = pdf.iloc[idx]['timestamp']
            window_data.append({
                'timestamp': ts,
                'isf_ratio': ratio,
                'sensitivity_ratio': float(sens_r) if not pd.isna(sens_r) else np.nan,
                'hour': ts.hour,
            })

    if not isf_ratios:
        return None, []

    return float(np.median(isf_ratios)), window_data


def main():
    print("=" * 70)
    print("EXP-2628: Autosens vs ISF Calibration Validation")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    # Check sensitivity_ratio availability
    print("\n--- Sensitivity ratio coverage ---")
    per_patient_stats = {}
    for pid in FULL_PATIENTS:
        pdf = df[df['patient_id'] == pid]
        sr = pdf['sensitivity_ratio']
        n_valid = sr.notna().sum()
        pct = n_valid / len(pdf) * 100
        mean_sr = float(sr.mean()) if n_valid > 0 else np.nan
        cv_sr = float(sr.std() / sr.mean() * 100) if n_valid > 10 and sr.mean() > 0 else np.nan
        print(f"  {pid}: {n_valid}/{len(pdf)} ({pct:.1f}%), mean={mean_sr:.3f}, CV={cv_sr:.1f}%")
        per_patient_stats[pid] = {
            'n_valid': int(n_valid),
            'pct': pct,
            'mean_sr': mean_sr,
            'cv_sr': cv_sr,
        }

    # Calibrate ISF ratio per patient
    print("\n--- ISF calibration ---")
    patient_isf_ratios = {}
    patient_window_data = {}
    for pid in FULL_PATIENTS:
        pdf = df[df['patient_id'] == pid]
        median_ratio, window_data = calibrate_isf_ratio(pdf)
        if median_ratio is None:
            print(f"  {pid}: insufficient corrections")
            continue
        patient_isf_ratios[pid] = median_ratio
        patient_window_data[pid] = window_data
        n_with_sr = sum(1 for w in window_data if not np.isnan(w['sensitivity_ratio']))
        print(f"  {pid}: ISF ratio={median_ratio:.3f}, "
              f"{len(window_data)} windows, {n_with_sr} with sens_ratio")

    # H1: Cross-patient correlation
    print("\n--- H1: Cross-patient sensitivity_ratio vs ISF ratio ---")
    pids_with_both = [p for p in patient_isf_ratios
                      if not np.isnan(per_patient_stats[p]['mean_sr'])]
    if len(pids_with_both) >= 5:
        sr_vals = [per_patient_stats[p]['mean_sr'] for p in pids_with_both]
        isf_vals = [patient_isf_ratios[p] for p in pids_with_both]
        r, p = spearmanr(sr_vals, isf_vals)
        h1 = r > 0.3 and p < 0.1
        print(f"  Patients: {pids_with_both}")
        print(f"  Spearman r = {r:.3f}, p = {p:.3f}")
        for pid in pids_with_both:
            print(f"    {pid}: sens_ratio={per_patient_stats[pid]['mean_sr']:.3f}, "
                  f"ISF_ratio={patient_isf_ratios[pid]:.3f}")
    else:
        h1 = False
        r = np.nan
        print(f"  Only {len(pids_with_both)} patients with both — insufficient")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'}")

    # H2: Within-patient temporal correlation
    print("\n--- H2: Within-patient sens_ratio vs ISF ratio ---")
    n_correlated = 0
    within_patient_r = {}
    for pid in pids_with_both:
        wd = patient_window_data[pid]
        pairs = [(w['sensitivity_ratio'], w['isf_ratio'])
                 for w in wd if not np.isnan(w['sensitivity_ratio'])]
        if len(pairs) < 20:
            print(f"  {pid}: only {len(pairs)} paired windows — skip")
            continue
        sr_arr = np.array([p[0] for p in pairs])
        isf_arr = np.array([p[1] for p in pairs])
        rr, pp = spearmanr(sr_arr, isf_arr)
        within_patient_r[pid] = rr
        correlated = rr > 0.2
        if correlated:
            n_correlated += 1
        print(f"  {pid}: r={rr:.3f}, p={pp:.3f}, n={len(pairs)} "
              f"{'✓' if correlated else '✗'}")

    h2 = n_correlated >= 5
    print(f"  Correlated patients: {n_correlated}/{len(within_patient_r)}")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'}")

    # H3: Autosens CV < ISF ratio CV
    print("\n--- H3: Autosens CV < ISF ratio CV ---")
    n_lower_cv = 0
    for pid in pids_with_both:
        wd = patient_window_data[pid]
        isf_ratios = [w['isf_ratio'] for w in wd]
        sr_ratios = [w['sensitivity_ratio'] for w in wd if not np.isnan(w['sensitivity_ratio'])]
        if len(sr_ratios) < 10 or len(isf_ratios) < 10:
            continue
        cv_isf = np.std(isf_ratios) / np.mean(isf_ratios) * 100
        cv_sr = np.std(sr_ratios) / np.mean(sr_ratios) * 100
        lower = cv_sr < cv_isf
        if lower:
            n_lower_cv += 1
        print(f"  {pid}: CV_autosens={cv_sr:.1f}%, CV_isf_ratio={cv_isf:.1f}% "
              f"{'✓' if lower else '✗'}")

    h3 = n_lower_cv >= len(pids_with_both) * 0.6
    print(f"  Autosens smoother in {n_lower_cv}/{len(pids_with_both)}")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2628")
    print("=" * 70)
    confirmations = {
        'H1_cross_patient_correlation': h1,
        'H2_within_patient_correlation': h2,
        'H3_autosens_smoother': h3,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    output = {
        'experiment': 'EXP-2628',
        'title': 'Autosens vs ISF Calibration',
        'hypotheses': confirmations,
        'per_patient': per_patient_stats,
        'isf_ratios': {k: round(v, 3) for k, v in patient_isf_ratios.items()},
        'within_patient_r': {k: round(v, 3) for k, v in within_patient_r.items()},
    }
    outfile = OUTDIR / 'exp-2628_autosens_validation.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
