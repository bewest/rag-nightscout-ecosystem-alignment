#!/usr/bin/env python3
"""Verification Validation Report

Runs the full advisory pipeline on the verification (held-out) data
and compares with training results. Generates:
1. Train vs Verify advisory agreement table
2. Correction vignettes with forward sim overlays
3. Meal response vignettes
4. Per-patient TIR and settings quality summary

Outputs:
- visualizations/reports/verification_summary.png
- visualizations/reports/vignette_corrections.png
- visualizations/reports/vignette_meals.png
- visualizations/reports/train_vs_verify.png
- Markdown report to stdout
"""
import json
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import timedelta

PROJ = Path(__file__).resolve().parents[3]
TRAIN_PARQUET = PROJ / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
VERIFY_PARQUET = PROJ / 'externals' / 'ns-parquet' / 'verification' / 'grid.parquet'
OUTDIR = PROJ / 'visualizations' / 'reports'
OUTDIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJ / 'tools'))
from cgmencode.production.settings_advisor import (
    generate_settings_advice,
    compute_settings_quality_score,
)
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)
from cgmencode.production.types import (
    BasalAssessment,
    ClinicalReport, GlycemicGrade, PatientProfile,
)

FULL_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k']


def load_grid(path):
    df = pd.read_parquet(path)
    df = df.rename(columns={'time': 'timestamp', 'glucose': 'sgv'})
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def build_advisory_inputs(pdf):
    """Build inputs for generate_settings_advice from patient data."""
    pdf = pdf.sort_values('timestamp').reset_index(drop=True)
    glucose = pdf['sgv'].values.astype(float)
    hours = (pdf['timestamp'].dt.hour + pdf['timestamp'].dt.minute / 60.0).values.astype(float)

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
        return None, {}

    tir = float(np.mean((valid_glucose >= 70) & (valid_glucose <= 180))) * 100
    tbr = float(np.mean(valid_glucose < 70)) * 100
    tar = float(np.mean(valid_glucose > 180)) * 100
    mean_g = float(np.nanmean(glucose))

    clinical = ClinicalReport(
        grade=GlycemicGrade.A if tir >= 70 else (GlycemicGrade.B if tir >= 60 else GlycemicGrade.C),
        risk_score=max(0, 100 - tir),
        tir=tir, tbr=tbr, tar=tar,
        mean_glucose=mean_g,
        gmi=round(3.31 + 0.02392 * mean_g, 1),
        cv=float(np.nanstd(glucose) / mean_g * 100) if mean_g > 0 else 30.0,
        basal_assessment=BasalAssessment.APPROPRIATE,
        cr_score=50.0,
        effective_isf=isf_val,
    )

    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)
    iob = pdf['iob'].fillna(0).values.astype(float)
    cob = pdf['cob'].fillna(0).values.astype(float)
    actual_basal = pdf.get('actual_basal_rate', pd.Series(dtype=float)).fillna(basal_val).values.astype(float)
    override = pdf.get('override_active', pd.Series(dtype=float)).fillna(0).values.astype(float)
    days_of_data = max(1, (pdf['timestamp'].max() - pdf['timestamp'].min()).days)

    correction_events = []
    corr_mask = (bolus > 0.5) & (carbs <= 1) & (glucose > 150) & ~np.isnan(glucose)
    for idx in np.where(corr_mask)[0]:
        post_2h = min(idx + 24, len(glucose) - 1)
        post_4h = min(idx + 48, len(glucose) - 1)
        pre = float(glucose[idx])
        post2 = float(glucose[post_2h]) if not np.isnan(glucose[post_2h]) else pre
        post4 = float(glucose[post_4h]) if not np.isnan(glucose[post_4h]) else pre
        correction_events.append({
            'start_bg': pre, 'tir_change': (1.0 if 70 <= post2 <= 180 else 0.0) - (1.0 if 70 <= pre <= 180 else 0.0),
            'drop_4h': pre - post4, 'rebound': post4 > pre * 0.95 and post2 < pre * 0.8,
            'rebound_magnitude': max(0, post4 - post2), 'went_below_70': post2 < 70 or post4 < 70,
        })

    meal_events = []
    meal_mask = (bolus > 0.5) & (carbs > 5) & ~np.isnan(glucose)
    for idx in np.where(meal_mask)[0]:
        post_idx = min(idx + 48, len(glucose) - 1)
        post_bg = float(glucose[post_idx]) if not np.isnan(glucose[post_idx]) else float(glucose[idx])
        meal_events.append({
            'carbs': float(carbs[idx]), 'bolus': float(bolus[idx]),
            'pre_meal_bg': float(glucose[idx]), 'post_meal_bg_4h': post_bg,
            'hour': float(hours[idx]),
        })

    inputs = {
        'glucose': glucose, 'metabolic': None, 'hours': hours,
        'clinical': clinical, 'profile': profile, 'days_of_data': float(days_of_data),
        'carbs': carbs, 'bolus': bolus, 'iob': iob, 'cob': cob,
        'actual_basal': actual_basal,
        'correction_events': correction_events[:200],
        'meal_events': meal_events[:200],
        'override_active': override,
    }

    stats = {'tir': tir, 'tbr': tbr, 'tar': tar, 'mean_glucose': mean_g,
             'cv': clinical.cv, 'days': days_of_data, 'n_corrections': len(correction_events),
             'n_meals': len(meal_events), 'isf': isf_val, 'cr': cr_val, 'basal': basal_val}
    return inputs, stats


def find_vignette_events(pdf, event_type='correction', n=3):
    """Find representative events for vignettes."""
    pdf = pdf.sort_values('timestamp').reset_index(drop=True)
    glucose = pdf['sgv'].values.astype(float)
    bolus = pdf['bolus'].fillna(0).values.astype(float)
    carbs = pdf['carbs'].fillna(0).values.astype(float)

    if event_type == 'correction':
        mask = (bolus > 0.5) & (carbs <= 1) & (glucose > 150) & ~np.isnan(glucose)
    else:  # meal
        mask = (bolus > 0.5) & (carbs > 10) & ~np.isnan(glucose)

    indices = np.where(mask)[0]
    if len(indices) == 0:
        return []

    events = []
    rng = np.random.RandomState(42)
    sample = rng.choice(indices, min(n * 3, len(indices)), replace=False)

    for idx in sample:
        # Need 2h window after event
        end_idx = min(idx + 24, len(glucose) - 1)
        window = glucose[idx:end_idx + 1]
        if np.isnan(window).sum() > len(window) * 0.3:
            continue

        timestamps = pdf['timestamp'].iloc[idx:end_idx + 1].values
        events.append({
            'idx': idx,
            'timestamp': pdf['timestamp'].iloc[idx],
            'start_bg': float(glucose[idx]),
            'end_bg': float(glucose[end_idx]) if not np.isnan(glucose[end_idx]) else None,
            'bolus': float(bolus[idx]),
            'carbs': float(carbs[idx]),
            'actual_glucose': window.copy(),
            'actual_timestamps': timestamps,
            'isf': float(pdf['scheduled_isf'].iloc[idx]) if 'scheduled_isf' in pdf else 50.0,
            'cr': float(pdf['scheduled_cr'].iloc[idx]) if 'scheduled_cr' in pdf else 10.0,
            'basal': float(pdf['scheduled_basal_rate'].iloc[idx]) if 'scheduled_basal_rate' in pdf else 0.8,
        })
        if len(events) >= n:
            break

    return events


def simulate_event(event, counter_reg_k=3.0):
    """Run forward sim for an event and return predicted glucose."""
    settings = TherapySettings(
        isf=event['isf'] if not pd.isna(event['isf']) else 50.0,
        cr=event['cr'] if not pd.isna(event['cr']) else 10.0,
        basal_rate=event['basal'] if not pd.isna(event['basal']) else 0.8,
        dia_hours=5.0,
    )
    bolus_events = [InsulinEvent(time_minutes=0, units=event['bolus'])]
    carb_events = []
    if event['carbs'] > 0:
        carb_events = [CarbEvent(time_minutes=0, grams=event['carbs'])]

    result = forward_simulate(
        initial_glucose=event['start_bg'],
        settings=settings,
        duration_hours=2.0,
        bolus_events=bolus_events,
        carb_events=carb_events,
        counter_reg_k=counter_reg_k,
    )
    return result.glucose


def plot_verification_summary(train_results, verify_results):
    """Plot train vs verify comparison."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Advisory Pipeline: Training vs Verification Validation', fontsize=14, fontweight='bold')

    patients = sorted(set(train_results.keys()) & set(verify_results.keys()))

    # 1. TIR comparison
    ax = axes[0, 0]
    train_tir = [train_results[p]['stats']['tir'] for p in patients]
    verify_tir = [verify_results[p]['stats']['tir'] for p in patients]
    x = np.arange(len(patients))
    ax.bar(x - 0.15, train_tir, 0.3, label='Training', color='#2196F3', alpha=0.8)
    ax.bar(x + 0.15, verify_tir, 0.3, label='Verification', color='#FF9800', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('TIR (%)')
    ax.set_title('Time in Range: Train vs Verify')
    ax.legend()
    ax.axhline(y=70, color='green', linestyle='--', alpha=0.5, label='Target 70%')
    ax.set_ylim(40, 100)

    # 2. SQS comparison
    ax = axes[0, 1]
    train_sqs = [train_results[p]['sqs'] for p in patients]
    verify_sqs = [verify_results[p]['sqs'] for p in patients]
    ax.bar(x - 0.15, train_sqs, 0.3, label='Training', color='#2196F3', alpha=0.8)
    ax.bar(x + 0.15, verify_sqs, 0.3, label='Verification', color='#FF9800', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('SQS')
    ax.set_title('Settings Quality Score: Train vs Verify')
    ax.legend()
    ax.set_ylim(30, 100)

    # 3. Advisory count comparison
    ax = axes[1, 0]
    train_n = [train_results[p]['n_advisories'] for p in patients]
    verify_n = [verify_results[p]['n_advisories'] for p in patients]
    ax.bar(x - 0.15, train_n, 0.3, label='Training', color='#2196F3', alpha=0.8)
    ax.bar(x + 0.15, verify_n, 0.3, label='Verification', color='#FF9800', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('Count')
    ax.set_title('Advisory Count: Train vs Verify')
    ax.legend()

    # 4. Advisory direction agreement
    ax = axes[1, 1]
    agreement = []
    for p in patients:
        t_recs = {(r.parameter.value, r.direction) for r in train_results[p]['recs']}
        v_recs = {(r.parameter.value, r.direction) for r in verify_results[p]['recs']}
        if t_recs or v_recs:
            overlap = len(t_recs & v_recs)
            total = len(t_recs | v_recs)
            agreement.append(overlap / total * 100 if total > 0 else 0)
        else:
            agreement.append(100)
    bars = ax.bar(x, agreement, 0.5, color=['#4CAF50' if a >= 60 else '#FF5722' for a in agreement], alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('Agreement (%)')
    ax.set_title('Advisory Direction Agreement (Train↔Verify)')
    ax.axhline(y=60, color='orange', linestyle='--', alpha=0.5)
    ax.set_ylim(0, 105)
    for i, v in enumerate(agreement):
        ax.text(i, v + 2, f'{v:.0f}%', ha='center', fontsize=9)

    plt.tight_layout()
    outpath = OUTDIR / 'train_vs_verify.png'
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def plot_vignettes(events, sim_traces, title, filename):
    """Plot vignette events with sim overlay."""
    n = len(events)
    if n == 0:
        return None

    fig, axes = plt.subplots(1, min(n, 3), figsize=(5 * min(n, 3), 4), squeeze=False)
    fig.suptitle(title, fontsize=13, fontweight='bold')

    for i, (event, sim_glucose) in enumerate(zip(events[:3], sim_traces[:3])):
        ax = axes[0, i]
        actual = event['actual_glucose']
        n_pts = min(len(actual), len(sim_glucose))
        minutes = np.arange(n_pts) * 5

        ax.plot(minutes, actual[:n_pts], 'b-o', markersize=3, label='Actual', linewidth=1.5)
        ax.plot(minutes, sim_glucose[:n_pts], 'r--', label='Predicted (sim)', linewidth=1.5, alpha=0.8)

        # TIR band
        ax.axhspan(70, 180, alpha=0.1, color='green')
        ax.axhline(70, color='red', alpha=0.3, linewidth=0.5)
        ax.axhline(180, color='orange', alpha=0.3, linewidth=0.5)

        ts = event['timestamp']
        ts_str = pd.Timestamp(ts).strftime('%m/%d %H:%M') if hasattr(ts, 'strftime') else str(ts)[:16]
        desc = f"Bolus: {event['bolus']:.1f}U"
        if event['carbs'] > 0:
            desc += f", Carbs: {event['carbs']:.0f}g"

        ax.set_title(f"{ts_str}\n{desc}", fontsize=9)
        ax.set_xlabel('Minutes')
        if i == 0:
            ax.set_ylabel('Glucose (mg/dL)')
        ax.legend(fontsize=7)
        ax.set_ylim(40, 350)

        # Compute MAE
        valid = ~np.isnan(actual[:n_pts])
        if valid.sum() > 0:
            mae = np.mean(np.abs(actual[:n_pts][valid] - sim_glucose[:n_pts][valid]))
            ax.text(0.95, 0.05, f'MAE={mae:.0f}', transform=ax.transAxes,
                    ha='right', fontsize=8, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    outpath = OUTDIR / filename
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def plot_patient_overview(verify_results):
    """Plot per-patient glycemic overview from verification data."""
    patients = sorted(verify_results.keys())
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle('Verification Set: Patient Glycemic Overview', fontsize=14, fontweight='bold')

    # 1. Stacked TIR/TBR/TAR
    ax = axes[0]
    tir = [verify_results[p]['stats']['tir'] for p in patients]
    tbr = [verify_results[p]['stats']['tbr'] for p in patients]
    tar = [verify_results[p]['stats']['tar'] for p in patients]
    x = np.arange(len(patients))
    ax.bar(x, tbr, 0.6, label='Below Range (<70)', color='#f44336', alpha=0.8)
    ax.bar(x, tir, 0.6, bottom=tbr, label='In Range (70-180)', color='#4CAF50', alpha=0.8)
    ax.bar(x, tar, 0.6, bottom=[t+i for t, i in zip(tbr, tir)], label='Above Range (>180)', color='#FF9800', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('Percentage')
    ax.set_title('Time in Range Distribution')
    ax.legend(loc='upper right')
    ax.axhline(y=4, color='red', linestyle=':', alpha=0.5)  # TBR target
    for i, (t, b) in enumerate(zip(tir, tbr)):
        ax.text(i, b + t/2, f'{t:.0f}%', ha='center', va='center', fontsize=9, fontweight='bold', color='white')

    # 2. Mean glucose + CV
    ax2 = axes[1]
    mean_g = [verify_results[p]['stats']['mean_glucose'] for p in patients]
    cv = [verify_results[p]['stats']['cv'] for p in patients]
    ax2.bar(x - 0.15, mean_g, 0.3, label='Mean Glucose (mg/dL)', color='#2196F3', alpha=0.8)
    ax2_twin = ax2.twinx()
    ax2_twin.bar(x + 0.15, cv, 0.3, label='CV (%)', color='#9C27B0', alpha=0.6)
    ax2.set_xticks(x)
    ax2.set_xticklabels(patients)
    ax2.set_ylabel('Mean Glucose (mg/dL)')
    ax2_twin.set_ylabel('CV (%)')
    ax2.set_title('Mean Glucose and Variability')
    ax2.axhline(y=154, color='green', linestyle='--', alpha=0.3, label='A1c 7% ≈ 154')
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    plt.tight_layout()
    outpath = OUTDIR / 'verification_summary.png'
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def main():
    print("=" * 70)
    print("VERIFICATION VALIDATION REPORT")
    print("=" * 70)

    # Load both datasets
    print("\nLoading training data...", end=' ', flush=True)
    train_df = load_grid(TRAIN_PARQUET)
    print(f"{len(train_df)} rows")

    print("Loading verification data...", end=' ', flush=True)
    verify_df = load_grid(VERIFY_PARQUET)
    print(f"{len(verify_df)} rows")

    # Run advisory pipeline on both
    train_results = {}
    verify_results = {}

    for dataset_name, df, results in [('Training', train_df, train_results),
                                       ('Verification', verify_df, verify_results)]:
        print(f"\n--- {dataset_name} Set Advisories ---")
        for pid in FULL_PATIENTS:
            pdf = df[df['patient_id'] == pid]
            if len(pdf) < 100:
                continue

            inputs, stats = build_advisory_inputs(pdf)
            if inputs is None:
                continue

            try:
                recs = generate_settings_advice(**inputs)
                sqs = compute_settings_quality_score(recs)
            except Exception as e:
                print(f"  {pid}: ERROR — {e}")
                continue

            results[pid] = {
                'stats': stats,
                'recs': recs,
                'sqs': sqs,
                'n_advisories': len(recs),
            }
            top = recs[0] if recs else None
            top_str = f"{top.parameter.value} {top.direction} {top.magnitude_pct:.0f}%" if top else "none"
            print(f"  {pid}: TIR={stats['tir']:.1f}%, SQS={sqs:.1f}, "
                  f"n={len(recs)}, top={top_str}")

    # Generate comparison visualization
    print("\n--- Generating Visualizations ---")
    plot_verification_summary(train_results, verify_results)
    print(f"  ✓ Train vs Verify comparison: {OUTDIR}/train_vs_verify.png")

    plot_patient_overview(verify_results)
    print(f"  ✓ Patient overview: {OUTDIR}/verification_summary.png")

    # Generate vignettes for 3 representative patients
    vignette_patients = ['c', 'e', 'g']  # low, mid, high TIR
    for pid in vignette_patients:
        vpdf = verify_df[verify_df['patient_id'] == pid]
        if len(vpdf) < 100:
            continue

        # Correction vignettes
        corr_events = find_vignette_events(vpdf, 'correction', n=3)
        if corr_events:
            sim_traces = [simulate_event(e) for e in corr_events]
            outpath = plot_vignettes(corr_events, sim_traces,
                                     f'Patient {pid}: Correction Vignettes (Verification)',
                                     f'vignette_corrections_{pid}.png')
            if outpath:
                print(f"  ✓ Correction vignettes ({pid}): {outpath}")

        # Meal vignettes
        meal_events = find_vignette_events(vpdf, 'meal', n=3)
        if meal_events:
            sim_traces = [simulate_event(e) for e in meal_events]
            outpath = plot_vignettes(meal_events, sim_traces,
                                     f'Patient {pid}: Meal Response Vignettes (Verification)',
                                     f'vignette_meals_{pid}.png')
            if outpath:
                print(f"  ✓ Meal vignettes ({pid}): {outpath}")

    # Print markdown report
    print("\n" + "=" * 70)
    print("SUMMARY REPORT")
    print("=" * 70)

    # Agreement analysis
    common_patients = sorted(set(train_results.keys()) & set(verify_results.keys()))
    print(f"\nPatients in both sets: {common_patients}")
    print(f"\n### Advisory Agreement (Train → Verify)")
    print(f"| Patient | Train TIR | Verify TIR | Train SQS | Verify SQS | Train N | Verify N | Agreement |")
    print(f"|---------|-----------|------------|-----------|------------|---------|----------|-----------|")

    agreements = []
    for p in common_patients:
        t = train_results[p]
        v = verify_results[p]
        t_recs = {(r.parameter.value, r.direction) for r in t['recs']}
        v_recs = {(r.parameter.value, r.direction) for r in v['recs']}
        overlap = len(t_recs & v_recs)
        total = len(t_recs | v_recs)
        agree = overlap / total * 100 if total > 0 else 100
        agreements.append(agree)
        print(f"| {p} | {t['stats']['tir']:.1f}% | {v['stats']['tir']:.1f}% | "
              f"{t['sqs']:.1f} | {v['sqs']:.1f} | {t['n_advisories']} | {v['n_advisories']} | {agree:.0f}% |")

    mean_agree = np.mean(agreements) if agreements else 0
    print(f"\nMean advisory agreement: {mean_agree:.1f}%")
    print(f"Patients with >60% agreement: {sum(1 for a in agreements if a >= 60)}/{len(agreements)}")

    # Top advisory by patient
    print(f"\n### Top Advisory per Patient (Verification)")
    print(f"| Patient | Parameter | Direction | Magnitude | ΔTIR | Confidence |")
    print(f"|---------|-----------|-----------|-----------|------|------------|")
    for p in common_patients:
        recs = verify_results[p]['recs']
        if recs:
            r = recs[0]
            print(f"| {p} | {r.parameter.value} | {r.direction} | {r.magnitude_pct:.0f}% | "
                  f"+{r.predicted_tir_delta:.1f}pp | {r.confidence:.2f} |")

    print(f"\nVisualization files saved to: {OUTDIR}/")
    print(f"  - train_vs_verify.png")
    print(f"  - verification_summary.png")
    for pid in vignette_patients:
        print(f"  - vignette_corrections_{pid}.png")
        print(f"  - vignette_meals_{pid}.png")


if __name__ == '__main__':
    main()
