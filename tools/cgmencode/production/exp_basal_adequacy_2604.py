#!/usr/bin/env python3
"""EXP-2604: Overnight Basal Adequacy Assessment.

Hypothesis: During overnight fasting (22:00-06:00), glucose drift direction
and magnitude indicate basal rate adequacy. Rising glucose = basal too low,
falling = too high. By comparing actual vs expected drift using the forward
sim (basal-only, no bolus/carbs), we can derive a basal adequacy metric.

H1: ≥5/9 patients have a clear directional drift pattern overnight
    (median drift magnitude ≥5 mg/dL/hr).
H2: Sim-predicted drift (basal-only with counter-reg k) correlates with
    actual drift (r ≥ 0.5) across patients.
H3: Basal adequacy metric (actual_drift - predicted_drift) correlates
    with TBR (r ≥ 0.4, sign: excess basal → more lows).

Design:
- Extract overnight fasting windows: 22:00-06:00, carbs=0, minimal bolus
- Compute actual glucose drift per window (mg/dL/hr)
- Simulate basal-only drift using forward_simulate with patient's k
- Derive basal_adequacy = actual_drift - sim_drift
  - Positive: glucose rises more than expected → basal too low
  - Negative: glucose falls more than expected → basal too high

Output: Per-patient basal adequacy and validation.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)
from cgmencode.production.settings_advisor import (
    _extract_correction_windows,
    _calibrate_counter_reg_k,
)
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2604_basal_adequacy.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Fasting window criteria
OVERNIGHT_START = 22  # 22:00
OVERNIGHT_END = 6     # 06:00
MIN_WINDOW_HOURS = 3  # minimum 3h continuous fasting
MAX_IOB = 0.5         # max IOB to consider "fasting"
MAX_CARBS_WINDOW = 1  # max carbs in window
MIN_WINDOWS = 3       # minimum windows per patient
STEP_MINUTES = 5      # parquet sampling interval


def _build_profile(pdf):
    """Build PatientProfile from patient data."""
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _extract_overnight_windows(pdf):
    """Extract overnight fasting windows from patient data.

    Returns list of dicts with:
      start_bg, end_bg, duration_hours, actual_drift_per_hr,
      start_iob, mean_iob, date
    """
    times = pd.to_datetime(pdf['time'])
    glucose = pdf['glucose'].values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    hours = (times.dt.hour + times.dt.minute / 60.0).values.astype(float)
    dates = times.dt.date

    # Identify overnight periods: 22:00 - 06:00
    N = len(pdf)
    windows = []
    i = 0

    while i < N - 36:  # need at least 3h = 36 steps
        h = hours[i]
        # Is this in the overnight window?
        if not (h >= OVERNIGHT_START or h < OVERNIGHT_END):
            i += 1
            continue

        # Start of potential window
        start_idx = i
        j = i + 1

        # Extend window while conditions hold
        while j < N:
            hj = hours[j]
            # Stop if we leave overnight window
            if OVERNIGHT_END <= hj < OVERNIGHT_START:
                break
            # Stop if bolus or carbs
            if bolus[j] > 0.3 or carbs[j] > MAX_CARBS_WINDOW:
                break
            # Stop if high IOB
            if iob[j] > MAX_IOB and not np.isnan(iob[j]):
                break
            # Stop if glucose gap
            if np.isnan(glucose[j]):
                # Skip small gaps
                gap_end = j + 1
                while gap_end < N and np.isnan(glucose[gap_end]) and gap_end - j < 4:
                    gap_end += 1
                if gap_end - j >= 4:
                    break
                j = gap_end
                continue
            j += 1

        # Check window length
        window_steps = j - start_idx
        window_hours = window_steps * STEP_MINUTES / 60.0

        if window_hours >= MIN_WINDOW_HOURS:
            wg = glucose[start_idx:j]
            valid_mask = ~np.isnan(wg)
            if np.sum(valid_mask) >= 20:  # at least 20 valid readings
                start_bg = float(np.nanmean(wg[:3]))
                end_bg = float(np.nanmean(wg[-3:]))
                if not np.isnan(start_bg) and not np.isnan(end_bg):
                    drift = end_bg - start_bg
                    drift_per_hr = drift / window_hours

                    windows.append({
                        'start_bg': start_bg,
                        'end_bg': end_bg,
                        'duration_hours': round(window_hours, 1),
                        'actual_drift_per_hr': round(drift_per_hr, 1),
                        'actual_drift_total': round(drift, 1),
                        'start_iob': float(iob[start_idx]) if not np.isnan(iob[start_idx]) else 0.0,
                        'mean_iob': round(float(np.nanmean(iob[start_idx:j])), 2),
                        'start_hour': round(float(hours[start_idx]), 1),
                        'date': str(dates.iloc[start_idx]),
                    })

        i = j + 1

    return windows


def _simulate_basal_drift(start_bg: float, duration_hours: float,
                          basal_rate: float, isf: float, k: float) -> float:
    """Simulate basal-only glucose drift."""
    settings = TherapySettings(
        isf=isf, cr=10, basal_rate=basal_rate, dia_hours=5.0,
    )
    result = forward_simulate(
        initial_glucose=start_bg,
        settings=settings,
        bolus_events=[],
        carb_events=[],
        duration_hours=duration_hours,
        counter_reg_k=k,
    )
    if len(result.glucose) < 2:
        return 0.0
    sim_end = result.glucose[-1]
    return (sim_end - start_bg) / duration_hours


def run_patient(pid: str, pdf: pd.DataFrame) -> dict:
    """Analyze basal adequacy for one patient."""
    profile = _build_profile(pdf)

    # Get patient's counter-reg k
    glucose = pdf['glucose'].values.astype(float)
    hours_arr = (pd.to_datetime(pdf['time']).dt.hour +
                 pd.to_datetime(pdf['time']).dt.minute / 60.0).values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs_arr = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)

    corrections = _extract_correction_windows(
        glucose, hours_arr, bolus, carbs_arr, iob, profile
    )
    k = _calibrate_counter_reg_k(corrections) if len(corrections) >= 10 else 2.0

    # Extract overnight windows
    windows = _extract_overnight_windows(pdf)
    if len(windows) < MIN_WINDOWS:
        return {'patient': pid, 'error': f'insufficient windows ({len(windows)})'}

    # Get basal rate and ISF
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    basal_rate = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8
    isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    # Simulate each window
    for w in windows:
        sim_drift = _simulate_basal_drift(
            w['start_bg'], w['duration_hours'], basal_rate, isf, k
        )
        w['sim_drift_per_hr'] = round(sim_drift, 1)
        w['basal_adequacy'] = round(w['actual_drift_per_hr'] - sim_drift, 1)

    # Aggregate metrics
    drifts = [w['actual_drift_per_hr'] for w in windows]
    sim_drifts = [w['sim_drift_per_hr'] for w in windows]
    adequacies = [w['basal_adequacy'] for w in windows]

    median_drift = float(np.median(drifts))
    median_sim_drift = float(np.median(sim_drifts))
    median_adequacy = float(np.median(adequacies))

    # Direction: is glucose predominantly rising or falling overnight?
    rising_pct = sum(1 for d in drifts if d > 2) / len(drifts)
    falling_pct = sum(1 for d in drifts if d < -2) / len(drifts)
    flat_pct = 1.0 - rising_pct - falling_pct

    # Actual vs sim drift correlation
    if len(drifts) >= 5:
        drift_corr, drift_p = stats.pearsonr(drifts, sim_drifts)
    else:
        drift_corr, drift_p = 0.0, 1.0

    # TIR and TBR for this patient
    valid_g = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) * 100
    tbr = float(np.mean(valid_g < 70)) * 100

    # Basal recommendation
    if median_adequacy > 5:
        basal_direction = "increase"
        basal_note = "glucose rises more than expected → basal likely too low"
    elif median_adequacy < -5:
        basal_direction = "decrease"
        basal_note = "glucose falls more than expected → basal likely too high"
    else:
        basal_direction = "adequate"
        basal_note = "overnight drift is within expected range"

    return {
        'patient': pid,
        'n_windows': len(windows),
        'k': k,
        'basal_rate': basal_rate,
        'isf': isf,
        'median_drift_per_hr': round(median_drift, 1),
        'median_sim_drift': round(median_sim_drift, 1),
        'median_adequacy': round(median_adequacy, 1),
        'rising_pct': round(rising_pct * 100, 0),
        'falling_pct': round(falling_pct * 100, 0),
        'flat_pct': round(flat_pct * 100, 0),
        'drift_corr': round(drift_corr, 3),
        'drift_p': round(drift_p, 4),
        'tir': round(tir, 1),
        'tbr': round(tbr, 1),
        'basal_direction': basal_direction,
        'basal_note': basal_note,
        'windows': windows[:10],  # save first 10 for inspection
    }


def main():
    print("=" * 70)
    print("EXP-2604: Overnight Basal Adequacy Assessment")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows from {PARQUET}\n")

    results = []
    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        r = run_patient(pid, pdf)
        results.append(r)

        if 'error' in r:
            print(f"  SKIP: {r['error']}")
            continue

        print(f"  {r['n_windows']} overnight windows, k={r['k']:.1f}")
        print(f"  Basal: {r['basal_rate']:.2f} U/hr, ISF: {r['isf']:.1f}")
        print(f"  Median drift: {r['median_drift_per_hr']:+.1f} mg/dL/hr "
              f"(sim: {r['median_sim_drift']:+.1f})")
        print(f"  Adequacy: {r['median_adequacy']:+.1f} mg/dL/hr → {r['basal_direction']}")
        print(f"  Pattern: {r['rising_pct']:.0f}% rising, "
              f"{r['falling_pct']:.0f}% falling, {r['flat_pct']:.0f}% flat")
        print(f"  Drift corr: r={r['drift_corr']:.3f} (p={r['drift_p']:.4f})")
        print(f"  TIR: {r['tir']:.1f}%, TBR: {r['tbr']:.1f}%")

    # Cross-patient summary
    valid = [r for r in results if 'error' not in r]
    print(f"\n{'='*70}")
    print(f"CROSS-PATIENT SUMMARY")
    print(f"{'='*70}")

    print(f"\n{'Pt':>4}  {'Win':>4}  {'Drift':>7}  {'Sim':>6}  {'Adeq':>6}  "
          f"{'Dir':>10}  {'TIR':>5}  {'TBR':>5}")
    print(f"{'-'*4}  {'-'*4}  {'-'*7}  {'-'*6}  {'-'*6}  {'-'*10}  {'-'*5}  {'-'*5}")
    for r in valid:
        print(f"{r['patient']:>4}  {r['n_windows']:>4}  "
              f"{r['median_drift_per_hr']:>+7.1f}  {r['median_sim_drift']:>+6.1f}  "
              f"{r['median_adequacy']:>+6.1f}  {r['basal_direction']:>10}  "
              f"{r['tir']:>5.1f}  {r['tbr']:>5.1f}")

    # H1: Clear drift pattern for ≥5 patients
    h1_count = sum(1 for r in valid if abs(r['median_drift_per_hr']) >= 5)
    h1 = h1_count >= 5
    print(f"\nH1 - Drift ≥5 mg/dL/hr for {h1_count}/{len(valid)} patients")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H2: Sim-actual drift correlation
    all_actual = [r['median_drift_per_hr'] for r in valid]
    all_sim = [r['median_sim_drift'] for r in valid]
    if len(all_actual) >= 4:
        h2_r, h2_p = stats.pearsonr(all_actual, all_sim)
    else:
        h2_r, h2_p = 0, 1
    h2 = h2_r >= 0.5
    print(f"\nH2 - Sim vs actual drift correlation: r={h2_r:.3f} (p={h2_p:.4f})")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'} (threshold: r ≥ 0.5)")

    # H3: Basal adequacy vs TBR correlation
    all_adeq = [r['median_adequacy'] for r in valid]
    all_tbr = [r['tbr'] for r in valid]
    if len(all_adeq) >= 4:
        h3_r, h3_p = stats.pearsonr(all_adeq, all_tbr)
    else:
        h3_r, h3_p = 0, 1
    h3 = abs(h3_r) >= 0.4
    print(f"\nH3 - Adequacy vs TBR: r={h3_r:.3f} (p={h3_p:.4f})")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'} "
          f"(threshold: |r| ≥ 0.4, expect negative)")

    # Save results
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    for r in results:
        for k, v in r.items():
            if isinstance(v, (np.floating, np.integer)):
                r[k] = float(v)
            elif isinstance(v, np.bool_):
                r[k] = bool(v)
        if 'windows' in r:
            for w in r['windows']:
                for k2, v2 in w.items():
                    if isinstance(v2, (np.floating, np.integer)):
                        w[k2] = float(v2)

    with open(OUTFILE, 'w') as f:
        json.dump({
            'experiment': 'EXP-2604',
            'title': 'Overnight Basal Adequacy Assessment',
            'hypotheses': {
                'H1': {'description': 'Clear drift ≥5 mg/dL/hr', 'confirmed': h1,
                       'count': h1_count},
                'H2': {'description': 'Sim-actual drift correlation',
                       'confirmed': h2, 'r': h2_r, 'p': h2_p},
                'H3': {'description': 'Adequacy vs TBR correlation',
                       'confirmed': h3, 'r': h3_r, 'p': h3_p},
            },
            'patients': results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == '__main__':
    main()
