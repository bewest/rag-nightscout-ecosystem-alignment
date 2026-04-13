#!/usr/bin/env python3
"""EXP-2607: Cross-Controller Advisory Validation (ODC Patients).

Hypothesis: The advisory system generalizes across AID controllers.
We test on ODC (OpenAPS Data Commons) patients who use a different
controller than our NS patients, to validate cross-controller robustness.

H1: SQS vs TIR correlation holds for ODC patients (r ≥ 0.5).
H2: Advisory direction consistency: ODC patients receive similar
    distribution of increase/decrease recommendations.
H3: Combined NS+ODC SQS vs TIR correlation ≥ 0.6.

Design:
- Run full advisory on ODC patients with adequate telemetry
- Compare SQS, recommendations, and outcomes with NS patients
- Test whether advisory generalizes or is controller-specific
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
OUTFILE = Path("externals/experiments/exp-2607_odc_validation.json")

# ODC patients with adequate telemetry (glucose >70%, >100 boluses)
ODC_PATIENTS = [
    "odc-74077367",
    "odc-86025410",
    "odc-96254963",
    "odc-39819048",
    "odc-49141524",
]
NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _build_profile(pdf):
    isf = float(pdf["scheduled_isf"].dropna().median()) if pdf["scheduled_isf"].notna().any() else 50.0
    cr = float(pdf["scheduled_cr"].dropna().median()) if pdf["scheduled_cr"].notna().any() else 10.0
    basal = float(pdf["scheduled_basal_rate"].dropna().median()) if pdf["scheduled_basal_rate"].notna().any() else 0.8
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _extract_correction_events(pdf, max_events=50):
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
        if len(events) >= max_events:
            break
    return events


def _extract_meal_events(pdf, max_events=50):
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
        if len(events) >= max_events:
            break
    return events


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

    try:
        clinical = generate_clinical_report(
            glucose=glucose, metabolic=None, profile=profile,
            carbs=carbs, bolus=bolus, hours=hours,
        )
    except Exception as e:
        return {'patient': pid, 'error': f'clinical_report: {e}'}

    correction_events = _extract_correction_events(pdf)
    meal_events = _extract_meal_events(pdf)

    try:
        recs = generate_settings_advice(
            glucose=glucose, metabolic=None, hours=hours,
            clinical=clinical, profile=profile,
            days_of_data=days, bolus=bolus, carbs=carbs,
            iob=iob, cob=cob, actual_basal=actual_basal,
            correction_events=correction_events,
            meal_events=meal_events,
        )
    except Exception as e:
        return {'patient': pid, 'error': f'settings_advice: {e}'}

    sqs = compute_settings_quality_score(recs)

    valid_g = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) * 100
    tbr = float(np.mean(valid_g < 70)) * 100
    tar = float(np.mean(valid_g > 180)) * 100

    return {
        'patient': pid,
        'controller': 'ODC' if pid.startswith('odc') else 'NS',
        'sqs': round(sqs, 1),
        'tir': round(tir, 1),
        'tbr': round(tbr, 1),
        'tar': round(tar, 1),
        'n_recs': len(recs),
        'days': round(days, 1),
        'n_corrections': len(correction_events),
        'n_meals': len(meal_events),
        'top_rec': {
            'param': recs[0].parameter.value if hasattr(recs[0].parameter, 'value') else str(recs[0].parameter),
            'dir': recs[0].direction,
            'mag': recs[0].magnitude_pct,
        } if recs else None,
        'recs_summary': [{
            'param': r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter),
            'dir': r.direction,
            'mag': r.magnitude_pct,
        } for r in recs],
    }


def main():
    print("=" * 70)
    print("EXP-2607: Cross-Controller Advisory Validation (ODC Patients)")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows\n")

    all_patients = NS_PATIENTS + ODC_PATIENTS
    results = []

    for pid in all_patients:
        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        if len(pdf) < 100:
            print(f"  SKIP: {len(pdf)} rows")
            results.append({'patient': pid, 'error': f'too few rows ({len(pdf)})'})
            continue

        r = run_patient(pid, pdf)
        results.append(r)

        if 'error' in r:
            print(f"  ERROR: {r['error']}")
            continue

        top = r['top_rec']
        top_str = f"{top['param']} {top['dir']} {top['mag']:.0f}%" if top else "none"
        print(f"  [{r['controller']}] SQS={r['sqs']:.1f}, TIR={r['tir']:.1f}%, "
              f"TBR={r['tbr']:.1f}%, {r['n_recs']} recs, top={top_str}")
        print(f"  Data: {r['days']:.0f}d, {r['n_corrections']} corrections, "
              f"{r['n_meals']} meals")

    # Split by controller
    valid = [r for r in results if 'error' not in r]
    ns = [r for r in valid if r['controller'] == 'NS']
    odc = [r for r in valid if r['controller'] == 'ODC']

    print(f"\n{'='*70}")
    print(f"CROSS-PATIENT SUMMARY")
    print(f"{'='*70}")

    print(f"\n{'Ctrl':>4}  {'Pt':>18}  {'SQS':>5}  {'TIR':>5}  {'TBR':>5}  "
          f"{'Recs':>4}  {'Top':>20}")
    print(f"{'-'*4}  {'-'*18}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*4}  {'-'*20}")
    for r in valid:
        top = r['top_rec']
        top_str = f"{top['param']} {top['dir']}" if top else "-"
        print(f"{r['controller']:>4}  {r['patient']:>18}  {r['sqs']:>5.1f}  "
              f"{r['tir']:>5.1f}  {r['tbr']:>5.1f}  {r['n_recs']:>4}  {top_str:>20}")

    # H1: ODC SQS vs TIR
    if len(odc) >= 3:
        odc_sqs = [r['sqs'] for r in odc]
        odc_tir = [r['tir'] for r in odc]
        h1_r, h1_p = stats.pearsonr(odc_sqs, odc_tir)
    else:
        h1_r, h1_p = 0, 1
    h1 = h1_r >= 0.5
    print(f"\nH1 - ODC SQS vs TIR: r={h1_r:.3f} (p={h1_p:.4f}), n={len(odc)}")
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'} (threshold: r ≥ 0.5)")

    # H2: Direction distribution similarity
    ns_increase = sum(1 for r in ns if r['top_rec'] and r['top_rec']['dir'] == 'increase')
    odc_increase = sum(1 for r in odc if r['top_rec'] and r['top_rec']['dir'] == 'increase')
    ns_pct = ns_increase / len(ns) * 100 if ns else 0
    odc_pct = odc_increase / len(odc) * 100 if odc else 0
    h2 = abs(ns_pct - odc_pct) < 40  # within 40pp
    print(f"\nH2 - Direction distribution: NS={ns_pct:.0f}% increase, ODC={odc_pct:.0f}% increase")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'} (threshold: within 40pp)")

    # H3: Combined SQS vs TIR
    all_sqs = [r['sqs'] for r in valid]
    all_tir = [r['tir'] for r in valid]
    if len(all_sqs) >= 4:
        h3_r, h3_p = stats.pearsonr(all_sqs, all_tir)
    else:
        h3_r, h3_p = 0, 1
    h3 = h3_r >= 0.6
    print(f"\nH3 - Combined SQS vs TIR: r={h3_r:.3f} (p={h3_p:.4f}), n={len(valid)}")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'} (threshold: r ≥ 0.6)")

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
            'experiment': 'EXP-2607',
            'title': 'Cross-Controller Advisory Validation',
            'hypotheses': {
                'H1': {'confirmed': h1, 'r': float(h1_r), 'p': float(h1_p)},
                'H2': {'confirmed': h2, 'ns_increase_pct': ns_pct, 'odc_increase_pct': odc_pct},
                'H3': {'confirmed': h3, 'r': float(h3_r), 'p': float(h3_p)},
            },
            'patients': results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == '__main__':
    main()
