#!/usr/bin/env python3
"""EXP-2605: Advisory Temporal Stability.

Hypothesis: Settings recommendations remain consistent when computed on
different time windows of the same patient's data. Stability is essential
for user trust — recommendations that flip-flop are useless.

H1: For ≥7/9 patients, the top recommendation direction is the same
    in both halves of their data (first half vs second half).
H2: SQS scores are stable: first-half vs second-half correlation
    r ≥ 0.8 across patients.
H3: Recommendation magnitudes are stable: coefficient of variation
    across windows < 30% for majority of patients.

Design:
- Split each patient's data into first-half and second-half
- Run generate_settings_advice() on each half
- Compare top recommendation, SQS score, and magnitudes
- Also test 3-way split (tertiles) for finer granularity
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.settings_advisor import (
    generate_settings_advice,
    compute_settings_quality_score,
)
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2605_temporal_stability.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


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


def _extract_correction_events(pdf):
    """Extract correction events for advisories."""
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        pre_window = glucose[max(0, i-12):i]
        post_window = glucose[i:post_idx]
        pre_tir = float(np.nanmean((pre_window >= 70) & (pre_window <= 180))) if len(pre_window) > 0 else 0.5
        post_tir = float(np.nanmean((post_window >= 70) & (post_window <= 180))) if len(post_window) > 0 else 0.5
        events.append({
            "start_bg": float(glucose[i]),
            "tir_change": post_tir - pre_tir,
            "rebound": bool(np.any(post_window < 70)),
            "rebound_magnitude": float(glucose[i] - np.nanmin(post_window)) if not np.all(np.isnan(post_window)) else 0.0,
            "went_below_70": bool(np.any(post_window < 70)),
            "bolus": float(bolus[i]),
            "hour": float(hours[i]),
        })
    return events[:50]


def _extract_meal_events(pdf):
    """Extract meal events for CR adequacy."""
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 48):
        if carbs[i] < 10 or np.isnan(glucose[i]):
            continue
        post_idx = i + 48
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        events.append({
            "carbs": float(carbs[i]),
            "bolus": float(bolus[i]),
            "start_bg": float(glucose[i]),
            "peak_bg": float(np.nanmax(glucose[i:post_idx])),
            "end_bg": float(glucose[post_idx]),
            "hour": float(hours[i]),
        })
    return events[:50]


def _run_advisory(pdf):
    """Run full advisory on a patient dataframe slice."""
    profile = _build_profile(pdf)
    glucose = pdf['glucose'].values.astype(float)
    hours = (pd.to_datetime(pdf['time']).dt.hour +
             pd.to_datetime(pdf['time']).dt.minute / 60.0).values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)
    cob = pdf['cob'].fillna(0).values.astype(float) if 'cob' in pdf else None
    actual_basal = pdf['actual_basal_rate'].fillna(0).values.astype(float) if 'actual_basal_rate' in pdf else None

    days = len(pdf) * 5 / 60 / 24

    # Generate proper ClinicalReport object
    clinical = generate_clinical_report(
        glucose=glucose, metabolic=None, profile=profile,
        carbs=carbs, bolus=bolus, hours=hours,
    )

    correction_events = _extract_correction_events(pdf)
    meal_events = _extract_meal_events(pdf)

    recs = generate_settings_advice(
        glucose=glucose,
        metabolic=None,
        hours=hours,
        clinical=clinical,
        profile=profile,
        days_of_data=days,
        bolus=bolus,
        carbs=carbs,
        iob=iob,
        cob=cob,
        actual_basal=actual_basal,
        correction_events=correction_events,
        meal_events=meal_events,
    )

    sqs = compute_settings_quality_score(recs)

    valid_g = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) if len(valid_g) > 0 else 0.5

    return {
        'n_recs': len(recs),
        'sqs': round(sqs, 1),
        'recs': [{
            'parameter': r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter),
            'direction': r.direction,
            'magnitude_pct': r.magnitude_pct,
            'confidence': r.confidence,
            'predicted_tir_delta': r.predicted_tir_delta,
        } for r in recs],
        'top_rec': {
            'parameter': recs[0].parameter.value if hasattr(recs[0].parameter, 'value') else str(recs[0].parameter),
            'direction': recs[0].direction,
            'magnitude_pct': recs[0].magnitude_pct,
        } if recs else None,
        'days': round(days, 1),
        'tir': round(tir * 100, 1),
    }


def run_patient(pid: str, pdf: pd.DataFrame) -> dict:
    """Compare advisories across time windows for one patient."""
    N = len(pdf)
    mid = N // 2

    # Split into halves
    first_half = pdf.iloc[:mid].reset_index(drop=True)
    second_half = pdf.iloc[mid:].reset_index(drop=True)

    # Run advisory on each
    try:
        full = _run_advisory(pdf)
        h1 = _run_advisory(first_half)
        h2 = _run_advisory(second_half)
    except Exception as e:
        return {'patient': pid, 'error': str(e)}

    # Compare directions
    if full['top_rec'] and h1['top_rec'] and h2['top_rec']:
        dir_match_h1_h2 = (h1['top_rec']['direction'] == h2['top_rec']['direction'] and
                           h1['top_rec']['parameter'] == h2['top_rec']['parameter'])
        dir_match_full_h1 = (full['top_rec']['direction'] == h1['top_rec']['direction'] and
                             full['top_rec']['parameter'] == h1['top_rec']['parameter'])
        dir_match_full_h2 = (full['top_rec']['direction'] == h2['top_rec']['direction'] and
                             full['top_rec']['parameter'] == h2['top_rec']['parameter'])
    else:
        dir_match_h1_h2 = None
        dir_match_full_h1 = None
        dir_match_full_h2 = None

    # Magnitude CV across windows for top recommendation
    magnitudes = []
    for r in [full, h1, h2]:
        if r['top_rec']:
            magnitudes.append(r['top_rec']['magnitude_pct'])
    mag_cv = float(np.std(magnitudes) / np.mean(magnitudes) * 100) if len(magnitudes) >= 2 and np.mean(magnitudes) > 0 else 0.0

    # Tertile analysis (3 windows)
    t1_end = N // 3
    t2_end = 2 * N // 3
    tertiles = []
    for start, end in [(0, t1_end), (t1_end, t2_end), (t2_end, N)]:
        try:
            t = _run_advisory(pdf.iloc[start:end].reset_index(drop=True))
            tertiles.append(t)
        except:
            tertiles.append({'sqs': None, 'top_rec': None})

    tertile_sqs = [t['sqs'] for t in tertiles if t.get('sqs') is not None]
    tertile_sqs_cv = float(np.std(tertile_sqs) / np.mean(tertile_sqs) * 100) if len(tertile_sqs) >= 2 and np.mean(tertile_sqs) > 0 else 0.0

    return {
        'patient': pid,
        'full': full,
        'first_half': h1,
        'second_half': h2,
        'dir_match_h1_h2': dir_match_h1_h2,
        'dir_match_full_h1': dir_match_full_h1,
        'dir_match_full_h2': dir_match_full_h2,
        'sqs_full': full['sqs'],
        'sqs_h1': h1['sqs'],
        'sqs_h2': h2['sqs'],
        'magnitude_cv': round(mag_cv, 1),
        'tertile_sqs': tertile_sqs,
        'tertile_sqs_cv': round(tertile_sqs_cv, 1),
    }


def main():
    print("=" * 70)
    print("EXP-2605: Advisory Temporal Stability")
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
            print(f"  ERROR: {r['error']}")
            continue

        # Top recommendations
        for label, key in [('Full', 'full'), ('Half 1', 'first_half'), ('Half 2', 'second_half')]:
            adv = r[key]
            if adv['top_rec']:
                print(f"  {label:>6}: SQS={adv['sqs']:>5.1f}, "
                      f"top={adv['top_rec']['parameter']} {adv['top_rec']['direction']} "
                      f"{adv['top_rec']['magnitude_pct']:.0f}%  "
                      f"({adv['n_recs']} recs, {adv['days']:.0f}d)")
            else:
                print(f"  {label:>6}: SQS={adv['sqs']:>5.1f}, no recommendations")

        match_sym = '✓' if r['dir_match_h1_h2'] else ('✗' if r['dir_match_h1_h2'] is not None else '-')
        print(f"  Direction match H1↔H2: {match_sym}")
        print(f"  Magnitude CV: {r['magnitude_cv']:.1f}%")

    # Cross-patient summary
    valid = [r for r in results if 'error' not in r]

    print(f"\n{'='*70}")
    print(f"CROSS-PATIENT SUMMARY")
    print(f"{'='*70}")

    print(f"\n{'Pt':>4}  {'SQS_F':>6}  {'SQS_1':>6}  {'SQS_2':>6}  "
          f"{'Dir?':>5}  {'Mag CV':>7}  {'TSQS CV':>8}")
    print(f"{'-'*4}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*8}")
    for r in valid:
        match = '✓' if r['dir_match_h1_h2'] else ('✗' if r['dir_match_h1_h2'] is not None else '-')
        print(f"{r['patient']:>4}  {r['sqs_full']:>6.1f}  {r['sqs_h1']:>6.1f}  "
              f"{r['sqs_h2']:>6.1f}  {match:>5}  {r['magnitude_cv']:>7.1f}  "
              f"{r['tertile_sqs_cv']:>8.1f}")

    # H1: Direction consistency for ≥7/9
    h1_count = sum(1 for r in valid if r.get('dir_match_h1_h2') is True)
    h1_total = sum(1 for r in valid if r.get('dir_match_h1_h2') is not None)
    h1 = h1_count >= 7
    print(f"\nH1 - Direction match H1↔H2 for {h1_count}/{h1_total} patients")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'} (threshold: ≥7)")

    # H2: SQS stability (half correlation)
    sqs_h1 = [r['sqs_h1'] for r in valid]
    sqs_h2 = [r['sqs_h2'] for r in valid]
    if len(sqs_h1) >= 4:
        h2_r, h2_p = stats.pearsonr(sqs_h1, sqs_h2)
    else:
        h2_r, h2_p = 0, 1
    h2 = h2_r >= 0.8
    print(f"\nH2 - SQS H1↔H2 correlation: r={h2_r:.3f} (p={h2_p:.4f})")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'} (threshold: r ≥ 0.8)")

    # H3: Magnitude CV < 30% for majority
    h3_count = sum(1 for r in valid if r.get('magnitude_cv', 100) < 30)
    h3 = h3_count >= 5
    print(f"\nH3 - Magnitude CV < 30% for {h3_count}/{len(valid)} patients")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'} (threshold: ≥5)")

    # Save
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    # Clean for JSON
    def clean(obj):
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    save_results = []
    for r in results:
        sr = {}
        for k, v in r.items():
            if isinstance(v, dict):
                sr[k] = {k2: clean(v2) for k2, v2 in v.items()}
            elif isinstance(v, list):
                sr[k] = [clean(x) if not isinstance(x, dict)
                         else {k2: clean(v2) for k2, v2 in x.items()}
                         for x in v]
            else:
                sr[k] = clean(v)
        save_results.append(sr)

    with open(OUTFILE, 'w') as f:
        json.dump({
            'experiment': 'EXP-2605',
            'title': 'Advisory Temporal Stability',
            'hypotheses': {
                'H1': {'confirmed': h1, 'count': h1_count, 'total': h1_total},
                'H2': {'confirmed': h2, 'r': float(h2_r), 'p': float(h2_p)},
                'H3': {'confirmed': h3, 'count': h3_count},
            },
            'patients': save_results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == '__main__':
    main()
