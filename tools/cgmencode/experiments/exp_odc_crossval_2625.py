#!/usr/bin/env python3
"""EXP-2625: ODC Patient Cross-Validation

All advisories were developed and calibrated on NS patients (a-g, i, k).
The 7 ODC patients are an independent validation set. If the advisory
pipeline generalizes, it validates that our findings are not overfit.

Hypotheses:
  H1: Advisory count for ODC patients is within 1 SD of NS patients
      (i.e., between 3 and 11 using NS mean=7.2, SD≈2).
  H2: SQS vs TIR correlation is positive (r > 0) for ODC patients.
  H3: CR and ISF advisories dominate top-3 for ≥ 4/7 ODC patients
      (same pattern as NS patients).
  H4: No contradictions in ODC patients (same-parameter opposite-direction).

Requires: FULL telemetry ODC patients.
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
from cgmencode.production.settings_advisor import (
    generate_settings_advice,
    compute_settings_quality_score,
)
from cgmencode.production.types import (
    BasalAssessment,
    ClinicalReport, GlycemicGrade, PatientProfile,
    SettingsParameter,
)

ODC_PATIENTS = [
    'odc-39819048', 'odc-49141524', 'odc-58680324',
    'odc-61403732', 'odc-74077367', 'odc-86025410', 'odc-96254963'
]
# Also include NS patients for comparison
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def build_patient_inputs(pdf):
    """Build inputs for generate_settings_advice from patient parquet data."""
    pdf = pdf.sort_values('timestamp').reset_index(drop=True)

    glucose = pdf['sgv'].values.astype(float)
    hours_raw = pdf['timestamp'].dt.hour + pdf['timestamp'].dt.minute / 60.0
    hours = hours_raw.values.astype(float)

    # Profile from scheduled values
    isf_val = float(pdf['scheduled_isf'].median())
    cr_val = float(pdf['scheduled_cr'].median())
    basal_val = float(pdf['scheduled_basal_rate'].median())
    if pd.isna(isf_val) or isf_val <= 0: isf_val = 50.0
    if pd.isna(cr_val) or cr_val <= 0: cr_val = 10.0
    if pd.isna(basal_val) or basal_val <= 0: basal_val = 0.8

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": isf_val}],
        cr_schedule=[{"time": "00:00", "value": cr_val}],
        basal_schedule=[{"time": "00:00", "value": basal_val}],
        dia_hours=5.0,
    )

    valid_glucose = glucose[~np.isnan(glucose)]
    if len(valid_glucose) < 100:
        return None, None

    tir = float(np.mean((valid_glucose >= 70) & (valid_glucose <= 180))) * 100
    tbr = float(np.mean(valid_glucose < 70)) * 100
    tar = float(np.mean(valid_glucose > 180)) * 100
    mean_g = float(np.nanmean(glucose))

    clinical = ClinicalReport(
        grade=GlycemicGrade.B if tir >= 60 else GlycemicGrade.C,
        risk_score=max(0, 100 - tir),
        tir=tir,
        tbr=tbr,
        tar=tar,
        mean_glucose=mean_g,
        gmi=round(3.31 + 0.02392 * mean_g, 1),
        cv=float(np.nanstd(glucose) / mean_g * 100) if mean_g > 0 else 30.0,
        basal_assessment=BasalAssessment.APPROPRIATE,
        cr_score=50.0,
        effective_isf=isf_val,
    )

    metabolic = None

    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)
    cob = pdf['cob'].fillna(0).values.astype(float)
    actual_basal = pdf['actual_basal_rate'].fillna(basal_val).values.astype(float)
    override = pdf['override_active'].fillna(0).values.astype(float)

    days_of_data = max(1, (pdf['timestamp'].max() - pdf['timestamp'].min()).days)

    # Correction events
    correction_events = []
    corr_mask = (bolus > 0.5) & (carbs <= 1) & (glucose > 150) & ~np.isnan(glucose)
    for idx in np.where(corr_mask)[0]:
        post_2h = min(idx + 24, len(glucose) - 1)
        post_4h = min(idx + 48, len(glucose) - 1)
        pre = float(glucose[idx])
        post2 = float(glucose[post_2h]) if not np.isnan(glucose[post_2h]) else pre
        post4 = float(glucose[post_4h]) if not np.isnan(glucose[post_4h]) else pre
        was_in_range = 1.0 if 70 <= post2 <= 180 else 0.0
        went_below = post2 < 70 or post4 < 70
        correction_events.append({
            'start_bg': pre,
            'tir_change': was_in_range - (1.0 if 70 <= pre <= 180 else 0.0),
            'drop_4h': pre - post4,
            'rebound': post4 > pre * 0.95 and post2 < pre * 0.8,
            'rebound_magnitude': max(0, post4 - post2),
            'went_below_70': went_below,
            'bolus': float(bolus[idx]),
            'hour': float(hours[idx]),
        })

    # Meal events
    meal_events = []
    meal_mask = (bolus > 0.5) & (carbs > 5) & ~np.isnan(glucose)
    for idx in np.where(meal_mask)[0]:
        post_idx = min(idx + 48, len(glucose) - 1)
        post_bg = float(glucose[post_idx]) if not np.isnan(glucose[post_idx]) else float(glucose[idx])
        meal_events.append({
            'carbs': float(carbs[idx]),
            'bolus': float(bolus[idx]),
            'pre_meal_bg': float(glucose[idx]),
            'post_meal_bg_4h': post_bg,
            'hour': float(hours[idx]),
        })

    return {
        'glucose': glucose,
        'metabolic': metabolic,
        'hours': hours,
        'clinical': clinical,
        'profile': profile,
        'days_of_data': float(days_of_data),
        'carbs': carbs,
        'bolus': bolus,
        'iob': iob,
        'cob': cob,
        'actual_basal': actual_basal,
        'correction_events': correction_events[:200],
        'meal_events': meal_events[:200],
        'override_active': override,
    }, tir


def run_audit(df, patient_list, label):
    """Run advisory audit on a set of patients."""
    results = {}
    for pid in sorted(patient_list):
        pdf = df[df['patient_id'] == pid]
        if len(pdf) < 100:
            print(f"    {pid}: {len(pdf)} rows (skipping)")
            continue

        inputs, actual_tir = build_patient_inputs(pdf)
        if inputs is None:
            print(f"    {pid}: insufficient glucose data")
            continue

        try:
            recs = generate_settings_advice(**inputs)
        except Exception as e:
            print(f"    {pid}: ERROR — {e}")
            continue

        sqs = compute_settings_quality_score(recs)

        # Check contradictions
        by_param = {}
        for rec in recs:
            p = rec.parameter.value
            by_param.setdefault(p, []).append(rec.direction)
        contradictions = [p for p, dirs in by_param.items()
                         if 'increase' in dirs and 'decrease' in dirs]

        # Top-3 parameters
        top3 = [r.parameter.value for r in recs[:3]]

        print(f"    {pid}: TIR={actual_tir:.1f}%, SQS={sqs:.1f}, "
              f"advisories={len(recs)}, contradictions={len(contradictions)}")
        for rec in recs[:3]:
            print(f"      {rec.parameter.value}: {rec.direction} {rec.magnitude_pct:.0f}% "
                  f"(ΔTIR={rec.predicted_tir_delta:+.1f}pp)")

        results[pid] = {
            'tir': actual_tir,
            'sqs': sqs,
            'n_advisories': len(recs),
            'contradictions': contradictions,
            'top3_params': top3,
        }

    return results


def main():
    print("=" * 70)
    print("EXP-2625: ODC Patient Cross-Validation")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    # Run on NS patients first (reference)
    print("\n--- NS patients (reference) ---")
    ns_results = run_audit(df, NS_PATIENTS, "NS")

    # Run on ODC patients (test set)
    print("\n--- ODC patients (test set) ---")
    odc_results = run_audit(df, ODC_PATIENTS, "ODC")

    if not odc_results:
        print("\nNo ODC results — cannot evaluate hypotheses.")
        return

    # Stats
    ns_counts = [r['n_advisories'] for r in ns_results.values()]
    odc_counts = [r['n_advisories'] for r in odc_results.values()]
    ns_mean = np.mean(ns_counts) if ns_counts else 7.0
    ns_std = np.std(ns_counts) if ns_counts else 2.0
    odc_mean = np.mean(odc_counts) if odc_counts else 0
    odc_tirs = [r['tir'] for r in odc_results.values()]
    odc_sqss = [r['sqs'] for r in odc_results.values()]

    # H1: Advisory count within 1 SD
    print(f"\n--- H1: ODC advisory count within 1 SD of NS ---")
    print(f"  NS: mean={ns_mean:.1f}, SD={ns_std:.1f} → range [{ns_mean-ns_std:.1f}, {ns_mean+ns_std:.1f}]")
    print(f"  ODC: mean={odc_mean:.1f}, counts={odc_counts}")
    h1 = abs(odc_mean - ns_mean) <= ns_std
    print(f"  H1 {'CONFIRMED' if h1 else 'NOT CONFIRMED'}")

    # H2: SQS vs TIR positive correlation
    print(f"\n--- H2: SQS vs TIR positive correlation for ODC ---")
    if len(odc_tirs) >= 4:
        r, p = spearmanr(odc_sqss, odc_tirs)
        h2 = r > 0
        print(f"  Spearman r = {r:.3f}, p = {p:.3f}")
    else:
        h2 = False
        print(f"  Only {len(odc_tirs)} ODC patients — insufficient")
    print(f"  H2 {'CONFIRMED' if h2 else 'NOT CONFIRMED'}")

    # H3: CR and ISF dominate top-3
    print(f"\n--- H3: CR/ISF dominate top-3 for ≥ 4/7 ODC ---")
    n_cr_isf_dominant = 0
    for pid, r in odc_results.items():
        cr_isf = sum(1 for p in r['top3_params'] if p in ('cr', 'isf'))
        if cr_isf >= 2:
            n_cr_isf_dominant += 1
        print(f"    {pid}: top-3 = {r['top3_params']}, CR/ISF count = {cr_isf}")
    h3 = n_cr_isf_dominant >= 4
    print(f"  CR/ISF dominant in {n_cr_isf_dominant}/{len(odc_results)}")
    print(f"  H3 {'CONFIRMED' if h3 else 'NOT CONFIRMED'}")

    # H4: No contradictions
    print(f"\n--- H4: No contradictions in ODC ---")
    n_contradictions = sum(1 for r in odc_results.values() if r['contradictions'])
    h4 = n_contradictions == 0
    for pid, r in odc_results.items():
        if r['contradictions']:
            print(f"    {pid}: contradictions in {r['contradictions']}")
    print(f"  Patients with contradictions: {n_contradictions}/{len(odc_results)}")
    print(f"  H4 {'CONFIRMED' if h4 else 'NOT CONFIRMED'}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2625")
    print("=" * 70)
    confirmations = {
        'H1_advisory_count_similar': h1,
        'H2_sqs_tir_positive': h2,
        'H3_cr_isf_dominant': h3,
        'H4_no_contradictions': h4,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    output = {
        'experiment': 'EXP-2625',
        'title': 'ODC Patient Cross-Validation',
        'hypotheses': confirmations,
        'ns_results': ns_results,
        'odc_results': odc_results,
        'ns_mean_count': float(ns_mean),
        'ns_std_count': float(ns_std),
        'odc_mean_count': float(odc_mean),
    }
    outfile = OUTDIR / 'exp-2625_odc_crossval.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
