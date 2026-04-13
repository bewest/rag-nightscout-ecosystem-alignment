#!/usr/bin/env python3
"""EXP-2624: Advisory Consolidation Audit

With 17 advisories in generate_settings_advice(), we need to verify:
1. How many fire per patient?
2. Do any contradict each other?
3. Which have the highest predicted TIR delta?
4. What's the overall settings quality score distribution?

This is a quality audit for production readiness. We run the full
advisory pipeline on synthetic data mimicking each patient's profile
and measure advisory coherence.

Hypotheses:
  H1: Average advisory count per patient ≤ 8 (not overwhelming).
  H2: Contradictory advisories (same parameter, opposite direction)
      occur in ≤ 2/12 patients after consolidation.
  H3: The top-3 advisories by TIR delta are consistent across ≥ 6/9
      patients (same parameter types dominate).
  H4: Settings Quality Score (SQS) correlates with actual TIR
      (Spearman r > 0.3 across patients).

Requires: FULL telemetry patients.
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

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df[df['patient_id'].isin(FULL_PATIENTS)]


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
    if pd.isna(isf_val): isf_val = 50.0
    if pd.isna(cr_val): cr_val = 10.0
    if pd.isna(basal_val): basal_val = 0.8

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": isf_val}],
        cr_schedule=[{"time": "00:00", "value": cr_val}],
        basal_schedule=[{"time": "00:00", "value": basal_val}],
        dia_hours=5.0,
    )

    # Clinical report (simplified)
    valid_glucose = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_glucose >= 70) & (valid_glucose <= 180))) * 100
    tbr = float(np.mean(valid_glucose < 70)) * 100
    tar = float(np.mean(valid_glucose > 180)) * 100

    clinical = ClinicalReport(
        grade=GlycemicGrade.B if tir >= 60 else GlycemicGrade.C,
        risk_score=max(0, 100 - tir),
        tir=tir,
        tbr=tbr,
        tar=tar,
        mean_glucose=float(np.nanmean(glucose)),
        gmi=round(3.31 + 0.02392 * float(np.nanmean(glucose)), 1),
        cv=float(np.nanstd(glucose) / np.nanmean(glucose) * 100),
        basal_assessment=BasalAssessment.APPROPRIATE,
        cr_score=50.0,
        effective_isf=isf_val,
    )

    # Metabolic state — pass None (requires physics engine run, not applicable here)
    metabolic = None

    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)
    cob = pdf['cob'].fillna(0).values.astype(float)
    actual_basal = pdf['actual_basal_rate'].fillna(basal_val).values.astype(float)
    override = pdf['override_active'].fillna(0).values.astype(float)

    days_of_data = (pdf['timestamp'].max() - pdf['timestamp'].min()).days

    # Build correction events (format: start_bg, tir_change, drop_4h)
    correction_events = []
    corr_mask = (bolus > 0.5) & (carbs <= 1) & (glucose > 150) & ~np.isnan(glucose)
    corr_indices = np.where(corr_mask)[0]
    for idx in corr_indices:
        post_2h = min(idx + 24, len(glucose) - 1)
        post_4h = min(idx + 48, len(glucose) - 1)
        pre = float(glucose[idx])
        post2 = float(glucose[post_2h]) if not np.isnan(glucose[post_2h]) else pre
        post4 = float(glucose[post_4h]) if not np.isnan(glucose[post_4h]) else pre
        # tir_change: was in range after? positive = good
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

    # Build meal events
    meal_events = []
    meal_mask = (bolus > 0.5) & (carbs > 5) & ~np.isnan(glucose)
    for idx in np.where(meal_mask)[0]:
        post_idx = min(idx + 48, len(glucose) - 1)  # 4h later
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
        'correction_events': correction_events[:200],  # limit for perf
        'meal_events': meal_events[:200],
        'override_active': override,
    }, tir


def main():
    print("=" * 70)
    print("EXP-2624: Advisory Consolidation Audit")
    print("=" * 70)

    print("\n--- Loading data ---")
    df = load_data()

    audit_results = {}
    all_advisory_counts = []
    all_sqs = []
    all_tir = []
    param_tir_deltas = {}

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid]
        print(f"\n  {pid}: {len(pdf)} rows...")

        try:
            inputs, actual_tir = build_patient_inputs(pdf)
            recs = generate_settings_advice(**inputs)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        sqs = compute_settings_quality_score(recs)

        print(f"    TIR={actual_tir:.1f}%, SQS={sqs:.1f}, advisories={len(recs)}")

        # Analyze each advisory
        by_param = {}
        for rec in recs:
            param = rec.parameter.value
            if param not in by_param:
                by_param[param] = []
            by_param[param].append({
                'direction': rec.direction,
                'magnitude_pct': rec.magnitude_pct,
                'predicted_tir_delta': rec.predicted_tir_delta,
                'confidence': rec.confidence,
                'evidence': rec.evidence[:80] + '...' if len(rec.evidence) > 80 else rec.evidence,
            })
            print(f"    {param}: {rec.direction} {rec.magnitude_pct:.0f}% "
                  f"(Δ TIR={rec.predicted_tir_delta:+.1f}pp, conf={rec.confidence:.2f})")

        # Check for contradictions within same parameter
        contradictions = []
        for param, advices in by_param.items():
            directions = set(a['direction'] for a in advices)
            if len(directions) > 1 and 'increase' in directions and 'decrease' in directions:
                contradictions.append(param)

        if contradictions:
            print(f"    ⚠ CONTRADICTIONS in: {contradictions}")

        audit_results[pid] = {
            'actual_tir': actual_tir,
            'sqs': sqs,
            'n_advisories': len(recs),
            'by_parameter': by_param,
            'contradictions': contradictions,
            'top_3': [{'param': r.parameter.value,
                       'direction': r.direction,
                       'delta': r.predicted_tir_delta}
                      for r in recs[:3]],
        }

        all_advisory_counts.append(len(recs))
        all_sqs.append(sqs)
        all_tir.append(actual_tir)

        # Track which params have highest delta
        for rec in recs[:3]:
            p = rec.parameter.value
            param_tir_deltas.setdefault(p, []).append(rec.predicted_tir_delta)

    # H1: Average advisory count ≤ 8
    print("\n--- H1: Average advisory count ≤ 8 ---")
    mean_count = np.mean(all_advisory_counts) if all_advisory_counts else 0
    h1_confirmed = mean_count <= 8
    print(f"  Mean advisories: {mean_count:.1f}")
    print(f"  Range: {min(all_advisory_counts)}-{max(all_advisory_counts)}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: Contradictions in ≤ 2/9
    print("\n--- H2: Contradictions in ≤ 2/9 ---")
    n_with_contradictions = sum(1 for r in audit_results.values() if r['contradictions'])
    h2_confirmed = n_with_contradictions <= 2
    print(f"  Patients with contradictions: {n_with_contradictions}/{len(audit_results)}")
    for pid, r in audit_results.items():
        if r['contradictions']:
            print(f"    {pid}: {r['contradictions']}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Top-3 parameter types consistent
    print("\n--- H3: Top-3 parameter consistency ---")
    top3_params_per_patient = {}
    for pid, r in audit_results.items():
        params = [t['param'] for t in r['top_3']]
        for p in params:
            top3_params_per_patient.setdefault(p, 0)
            top3_params_per_patient[p] += 1
    print("  Parameter frequency in top-3:")
    for p, c in sorted(top3_params_per_patient.items(), key=lambda x: -x[1]):
        print(f"    {p}: {c}/{len(audit_results)}")
    most_common = max(top3_params_per_patient.values()) if top3_params_per_patient else 0
    h3_confirmed = most_common >= 6
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # H4: SQS correlates with TIR
    print("\n--- H4: SQS vs TIR correlation ---")
    if len(all_sqs) >= 5:
        r, p = spearmanr(all_sqs, all_tir)
        h4_confirmed = r > 0.3 and p < 0.1
        print(f"  Spearman r = {r:.3f}, p = {p:.3f}")
        for pid, res in audit_results.items():
            print(f"    {pid}: TIR={res['actual_tir']:.1f}%, SQS={res['sqs']:.1f}")
        print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}")
    else:
        h4_confirmed = False
        print("  H4: Insufficient data")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — EXP-2624")
    print("=" * 70)
    confirmations = {
        'H1_advisory_count_manageable': h1_confirmed,
        'H2_few_contradictions': h2_confirmed,
        'H3_consistent_top_params': h3_confirmed,
        'H4_sqs_vs_tir': h4_confirmed,
    }
    for h, c in confirmations.items():
        print(f"  {h}: {'CONFIRMED' if c else 'NOT CONFIRMED'}")

    output = {
        'experiment': 'EXP-2624',
        'title': 'Advisory Consolidation Audit',
        'hypotheses': confirmations,
        'per_patient': audit_results,
        'mean_advisory_count': mean_count,
        'param_frequency_in_top3': top3_params_per_patient,
    }
    outfile = OUTDIR / 'exp-2624_advisory_audit.json'
    with open(outfile, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == '__main__':
    main()
