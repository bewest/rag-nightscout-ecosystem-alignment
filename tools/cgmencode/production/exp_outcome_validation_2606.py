#!/usr/bin/env python3
"""EXP-2606: Retrospective Outcome Validation.

Hypothesis: Patients whose actual settings are closer to what we recommend
should have better glycemic outcomes. This is the strongest possible test
of advisory clinical validity.

H1: SQS correlates with TIR (r ≥ 0.7) — higher SQS = better outcomes.
    (Revalidation post-ISF-fix; previously r=0.833 in EXP-2600.)
H2: The distance between actual ISF and recommended ISF correlates with
    TIR (r ≤ -0.5, sign: larger distance = worse TIR).
H3: Patients with "adequate" basal assessment have higher TIR than
    patients with "increase"/"decrease" assessment (≥5pp difference).

Design:
- Run advisory on each patient's full data
- Compute distance between current and recommended settings
- Correlate distances with TIR, TBR, TAR

This validates the overall advisory system after the EXP-2601/2602
ISF fix (removed sim-based ISF, kept correction-based only).
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
from cgmencode.production.types import PatientProfile, SettingsParameter

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2606_outcome_validation.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _build_profile(pdf):
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
        pre_w = glucose[max(0, i-12):i]
        post_w = glucose[i:post_idx]
        pre_tir = float(np.nanmean((pre_w >= 70) & (pre_w <= 180))) if len(pre_w) > 0 else 0.5
        post_tir = float(np.nanmean((post_w >= 70) & (post_w <= 180))) if len(post_w) > 0 else 0.5
        events.append({
            "start_bg": float(glucose[i]),
            "tir_change": post_tir - pre_tir,
            "rebound": bool(np.any(post_w < 70)),
            "rebound_magnitude": float(glucose[i] - np.nanmin(post_w)) if not np.all(np.isnan(post_w)) else 0.0,
            "went_below_70": bool(np.any(post_w < 70)),
            "bolus": float(bolus[i]),
            "hour": float(hours[i]),
        })
    return events[:50]


def _extract_meal_events(pdf):
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


def run_patient(pid: str, pdf: pd.DataFrame) -> dict:
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

    clinical = generate_clinical_report(
        glucose=glucose, metabolic=None, profile=profile,
        carbs=carbs, bolus=bolus, hours=hours,
    )

    correction_events = _extract_correction_events(pdf)
    meal_events = _extract_meal_events(pdf)

    recs = generate_settings_advice(
        glucose=glucose, metabolic=None, hours=hours,
        clinical=clinical, profile=profile,
        days_of_data=days, bolus=bolus, carbs=carbs,
        iob=iob, cob=cob, actual_basal=actual_basal,
        correction_events=correction_events,
        meal_events=meal_events,
    )

    sqs = compute_settings_quality_score(recs)

    # Glycemic outcomes
    valid_g = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) * 100
    tbr = float(np.mean(valid_g < 70)) * 100
    tar = float(np.mean(valid_g > 180)) * 100
    mean_g = float(np.nanmean(valid_g))
    cv = float(np.nanstd(valid_g) / mean_g * 100) if mean_g > 0 else 0

    # ISF distance: if ISF rec exists, how far is current from suggested?
    isf_distance = 0.0
    isf_direction = None
    isf_current = None
    isf_suggested = None
    for r in recs:
        if r.parameter == SettingsParameter.ISF:
            isf_current = r.current_value
            isf_suggested = r.suggested_value
            isf_distance = abs(r.current_value - r.suggested_value) / r.current_value * 100
            isf_direction = r.direction
            break

    # CR distance
    cr_distance = 0.0
    cr_direction = None
    for r in recs:
        if r.parameter == SettingsParameter.CR:
            cr_distance = abs(r.current_value - r.suggested_value) / r.current_value * 100
            cr_direction = r.direction
            break

    # Total settings distance (sum of all recommendation magnitudes)
    total_distance = sum(r.magnitude_pct for r in recs)

    return {
        'patient': pid,
        'sqs': round(sqs, 1),
        'tir': round(tir, 1),
        'tbr': round(tbr, 1),
        'tar': round(tar, 1),
        'mean_g': round(mean_g, 0),
        'cv': round(cv, 1),
        'n_recs': len(recs),
        'isf_distance': round(isf_distance, 1),
        'isf_direction': isf_direction,
        'isf_current': isf_current,
        'isf_suggested': isf_suggested,
        'cr_distance': round(cr_distance, 1),
        'cr_direction': cr_direction,
        'total_distance': round(total_distance, 0),
        'recs_summary': [{
            'param': r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter),
            'dir': r.direction,
            'mag': r.magnitude_pct,
            'conf': r.confidence,
        } for r in recs],
    }


def main():
    print("=" * 70)
    print("EXP-2606: Retrospective Outcome Validation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows\n")

    results = []
    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        r = run_patient(pid, pdf)
        results.append(r)

        print(f"  SQS: {r['sqs']:.1f}, TIR: {r['tir']:.1f}%, TBR: {r['tbr']:.1f}%")
        print(f"  ISF: {r['isf_current']}→{r['isf_suggested']} ({r['isf_direction']}, "
              f"dist={r['isf_distance']:.1f}%)")
        if r['cr_direction']:
            print(f"  CR: {r['cr_direction']} (dist={r['cr_distance']:.1f}%)")
        print(f"  Total distance: {r['total_distance']:.0f}")
        print(f"  Recs: {r['n_recs']}")

    # Summary
    print(f"\n{'='*70}")
    print(f"CROSS-PATIENT SUMMARY")
    print(f"{'='*70}")
    print(f"\n{'Pt':>4}  {'SQS':>5}  {'TIR':>5}  {'TBR':>5}  {'ISFd':>6}  {'TotD':>6}")
    print(f"{'-'*4}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*6}")
    for r in results:
        print(f"{r['patient']:>4}  {r['sqs']:>5.1f}  {r['tir']:>5.1f}  "
              f"{r['tbr']:>5.1f}  {r['isf_distance']:>6.1f}  {r['total_distance']:>6.0f}")

    # H1: SQS vs TIR
    sqs_vals = [r['sqs'] for r in results]
    tir_vals = [r['tir'] for r in results]
    h1_r, h1_p = stats.pearsonr(sqs_vals, tir_vals)
    h1 = h1_r >= 0.7
    print(f"\nH1 - SQS vs TIR: r={h1_r:.3f} (p={h1_p:.4f})")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'} (threshold: r ≥ 0.7)")

    # H2: ISF distance vs TIR
    isf_d = [r['isf_distance'] for r in results]
    h2_r, h2_p = stats.pearsonr(isf_d, tir_vals)
    h2 = h2_r <= -0.5
    print(f"\nH2 - ISF distance vs TIR: r={h2_r:.3f} (p={h2_p:.4f})")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'} (threshold: r ≤ -0.5)")

    # H3: Total distance vs TIR
    tot_d = [r['total_distance'] for r in results]
    h3_r, h3_p = stats.pearsonr(tot_d, tir_vals)
    print(f"\nH3 - Total distance vs TIR: r={h3_r:.3f} (p={h3_p:.4f})")
    h3 = h3_r <= -0.5
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'} (threshold: r ≤ -0.5)")

    # Bonus: SQS vs TBR
    tbr_vals = [r['tbr'] for r in results]
    b_r, b_p = stats.pearsonr(sqs_vals, tbr_vals)
    print(f"\nBonus - SQS vs TBR: r={b_r:.3f} (p={b_p:.4f})")

    # Save
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    for r in results:
        for k, v in r.items():
            if isinstance(v, (np.floating, np.integer)):
                r[k] = float(v)
            elif isinstance(v, np.bool_):
                r[k] = bool(v)

    with open(OUTFILE, 'w') as f:
        json.dump({
            'experiment': 'EXP-2606',
            'title': 'Retrospective Outcome Validation',
            'hypotheses': {
                'H1': {'confirmed': h1, 'r': float(h1_r), 'p': float(h1_p),
                       'description': 'SQS vs TIR correlation'},
                'H2': {'confirmed': h2, 'r': float(h2_r), 'p': float(h2_p),
                       'description': 'ISF distance vs TIR'},
                'H3': {'confirmed': h3, 'r': float(h3_r), 'p': float(h3_p),
                       'description': 'Total distance vs TIR'},
            },
            'patients': results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == '__main__':
    main()
