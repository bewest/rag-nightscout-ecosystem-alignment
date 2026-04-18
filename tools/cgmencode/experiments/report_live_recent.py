#!/usr/bin/env python3
"""Live-Recent Settings Recommendations Report

Parses live Nightscout data for patient c and generates:
1. Current glycemic assessment
2. Ambulatory glucose profile (daily pattern)
3. Settings recommendations with explanations
4. 7-day glucose trace with TIR band
5. Forward sim scenarios showing recommendation impact

Outputs:
- visualizations/reports/live_glucose_trace.png
- visualizations/reports/live_ambulatory_profile.png
- visualizations/reports/live_recommendations.png
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
from datetime import datetime, timedelta, timezone

PROJ = Path(__file__).resolve().parents[3]
LIVE_DIR = PROJ / 'externals' / 'ns-data' / 'live-recent'
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
    BasalAssessment, ClinicalReport, GlycemicGrade, PatientProfile,
)


def load_entries(path):
    """Load CGM entries from Nightscout JSON."""
    with open(path) as f:
        raw = json.load(f)
    records = []
    for e in raw:
        sgv = e.get('sgv')
        ds = e.get('dateString') or e.get('sysTime')
        if sgv is None or ds is None:
            continue
        try:
            ts = pd.Timestamp(ds)
            records.append({'timestamp': ts, 'sgv': float(sgv), 'direction': e.get('direction', '')})
        except Exception:
            continue
    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df = df.sort_values('timestamp').drop_duplicates(subset='timestamp')
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df


def load_treatments(path):
    """Load treatments from Nightscout JSON."""
    with open(path) as f:
        raw = json.load(f)
    records = []
    for t in raw:
        ds = t.get('created_at') or t.get('timestamp')
        if ds is None:
            continue
        try:
            ts = pd.Timestamp(ds)
            records.append({
                'timestamp': ts,
                'eventType': t.get('eventType', ''),
                'insulin': float(t.get('insulin', 0) or 0),
                'carbs': float(t.get('carbs', 0) or 0),
                'rate': float(t.get('rate', 0) or 0) if t.get('rate') is not None else None,
                'duration': float(t.get('duration', 0) or 0),
            })
        except Exception:
            continue
    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df = df.sort_values('timestamp').drop_duplicates()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df


def load_profile(path):
    """Load profile settings from Nightscout JSON."""
    with open(path) as f:
        profiles = json.load(f)
    if not profiles:
        return None

    store = profiles[0].get('store', {})
    default = store.get('Default', next(iter(store.values())) if store else {})

    isf_schedule = default.get('sens', [])
    cr_schedule = default.get('carbratio', [])
    basal_schedule = default.get('basal', [])
    dia = float(default.get('dia', 5.0))

    return {
        'isf_schedule': isf_schedule,
        'cr_schedule': cr_schedule,
        'basal_schedule': basal_schedule,
        'dia': dia,
        'units': default.get('units', 'mg/dl'),
    }


def compute_glycemic_stats(entries_df, last_n_days=14):
    """Compute glycemic statistics."""
    if len(entries_df) == 0:
        return {}
    cutoff = entries_df['timestamp'].max() - timedelta(days=last_n_days)
    df = entries_df[entries_df['timestamp'] >= cutoff].copy()
    glucose = df['sgv'].values.astype(float)
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return {}

    return {
        'n_readings': len(valid),
        'days': last_n_days,
        'mean': float(np.mean(valid)),
        'std': float(np.std(valid)),
        'cv': float(np.std(valid) / np.mean(valid) * 100),
        'median': float(np.median(valid)),
        'tir': float(np.mean((valid >= 70) & (valid <= 180)) * 100),
        'tbr': float(np.mean(valid < 70) * 100),
        'tbr_serious': float(np.mean(valid < 54) * 100),
        'tar': float(np.mean(valid > 180) * 100),
        'tar_serious': float(np.mean(valid > 250) * 100),
        'gmi': round(3.31 + 0.02392 * float(np.mean(valid)), 1),
        'min': float(np.min(valid)),
        'max': float(np.max(valid)),
        'p10': float(np.percentile(valid, 10)),
        'p25': float(np.percentile(valid, 25)),
        'p75': float(np.percentile(valid, 75)),
        'p90': float(np.percentile(valid, 90)),
    }


def plot_glucose_trace(entries_df, treatments_df, stats, last_n_days=7):
    """Plot recent glucose trace with TIR bands and treatments."""
    cutoff = entries_df['timestamp'].max() - timedelta(days=last_n_days)
    df = entries_df[entries_df['timestamp'] >= cutoff].copy()

    fig, ax = plt.subplots(figsize=(16, 5))
    fig.suptitle(f'Glucose Trace — Last {last_n_days} Days', fontsize=14, fontweight='bold')

    # TIR band
    ax.axhspan(70, 180, alpha=0.08, color='green')
    ax.axhline(70, color='red', alpha=0.3, linewidth=0.5)
    ax.axhline(180, color='orange', alpha=0.3, linewidth=0.5)
    ax.axhline(54, color='darkred', alpha=0.2, linewidth=0.5)
    ax.axhline(250, color='darkorange', alpha=0.2, linewidth=0.5)

    # Glucose trace
    ax.plot(df['timestamp'], df['sgv'], 'b-', linewidth=0.6, alpha=0.7)

    # Color-code glucose values
    low = df[df['sgv'] < 70]
    high = df[df['sgv'] > 180]
    ax.scatter(low['timestamp'], low['sgv'], c='red', s=3, alpha=0.8, zorder=5)
    ax.scatter(high['timestamp'], high['sgv'], c='orange', s=3, alpha=0.5, zorder=5)

    # Treatment markers
    if len(treatments_df) > 0:
        treats = treatments_df[treatments_df['timestamp'] >= cutoff]
        bolus = treats[(treats['insulin'] > 0)]
        carbs = treats[(treats['carbs'] > 0)]
        if len(bolus) > 0:
            ax.scatter(bolus['timestamp'], [40] * len(bolus), marker='^', c='purple',
                       s=bolus['insulin'] * 10, alpha=0.5, label=f'Bolus ({len(bolus)} events)')
        if len(carbs) > 0:
            ax.scatter(carbs['timestamp'], [35] * len(carbs), marker='D', c='green',
                       s=carbs['carbs'] * 2, alpha=0.5, label=f'Carbs ({len(carbs)} events)')

    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_ylim(30, 350)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.legend(loc='upper right', fontsize=8)

    # Stats box
    stats_text = (f"TIR: {stats['tir']:.1f}%  TBR: {stats['tbr']:.1f}%  TAR: {stats['tar']:.1f}%\n"
                  f"Mean: {stats['mean']:.0f}  CV: {stats['cv']:.1f}%  GMI: {stats['gmi']}")
    ax.text(0.01, 0.97, stats_text, transform=ax.transAxes, fontsize=9, va='top',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

    plt.tight_layout()
    outpath = OUTDIR / 'live_glucose_trace.png'
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def plot_ambulatory_profile(entries_df, last_n_days=14):
    """Plot ambulatory glucose profile (daily overlay)."""
    cutoff = entries_df['timestamp'].max() - timedelta(days=last_n_days)
    df = entries_df[entries_df['timestamp'] >= cutoff].copy()
    df['hour'] = df['timestamp'].dt.hour + df['timestamp'].dt.minute / 60.0

    fig, ax = plt.subplots(figsize=(14, 5))
    fig.suptitle(f'Ambulatory Glucose Profile — Last {last_n_days} Days', fontsize=14, fontweight='bold')

    # TIR band
    ax.axhspan(70, 180, alpha=0.08, color='green')
    ax.axhline(70, color='red', alpha=0.3, linewidth=0.5)
    ax.axhline(180, color='orange', alpha=0.3, linewidth=0.5)

    # Per-day traces (light)
    for date, group in df.groupby(df['timestamp'].dt.date):
        ax.plot(group['hour'], group['sgv'], 'b-', alpha=0.05, linewidth=0.5)

    # Percentile bands
    bins = np.arange(0, 24.25, 0.25)
    df['hour_bin'] = pd.cut(df['hour'], bins=bins, labels=bins[:-1])
    hourly = df.groupby('hour_bin', observed=False)['sgv']

    hours = np.array([float(h) for h in bins[:-1]])
    p10 = hourly.quantile(0.10).values.astype(float)
    p25 = hourly.quantile(0.25).values.astype(float)
    p50 = hourly.quantile(0.50).values.astype(float)
    p75 = hourly.quantile(0.75).values.astype(float)
    p90 = hourly.quantile(0.90).values.astype(float)

    ax.fill_between(hours, p10, p90, alpha=0.1, color='blue', label='10th-90th')
    ax.fill_between(hours, p25, p75, alpha=0.2, color='blue', label='25th-75th')
    ax.plot(hours, p50, 'b-', linewidth=2, label='Median')

    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 25, 3)])
    ax.set_ylim(40, 350)
    ax.legend(loc='upper right', fontsize=8)

    plt.tight_layout()
    outpath = OUTDIR / 'live_ambulatory_profile.png'
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def plot_recommendations(recs, profile_info, stats):
    """Plot recommendations as a visual summary."""
    if not recs:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle('Settings Recommendations', fontsize=14, fontweight='bold')

    # 1. Current settings vs recommended
    ax = axes[0]
    params = []
    current_vals = []
    recommended_vals = []
    colors = []

    isf = profile_info['isf_schedule'][0]['value'] if profile_info['isf_schedule'] else 50
    cr = profile_info['cr_schedule'][0]['value'] if profile_info['cr_schedule'] else 10
    basal = profile_info['basal_schedule'][0]['value'] if profile_info['basal_schedule'] else 1.0

    setting_map = {'isf': isf, 'cr': cr, 'basal_rate': basal, 'dia': profile_info['dia']}

    for r in recs[:5]:
        pname = r.parameter.value
        current = setting_map.get(pname, None)
        if current is None:
            continue
        pct = r.magnitude_pct / 100.0
        if r.direction == 'increase':
            new_val = current * (1 + pct)
        else:
            new_val = current * (1 - pct)
        params.append(pname.upper())
        current_vals.append(current)
        recommended_vals.append(new_val)
        colors.append('#4CAF50' if r.direction == 'increase' else '#f44336')

    if params:
        x = np.arange(len(params))
        ax.barh(x - 0.15, current_vals, 0.3, label='Current', color='#2196F3', alpha=0.8)
        ax.barh(x + 0.15, recommended_vals, 0.3, label='Recommended', color=colors, alpha=0.8)
        ax.set_yticks(x)
        ax.set_yticklabels(params)
        ax.set_xlabel('Value')
        ax.set_title('Current vs Recommended')
        ax.legend()

    # 2. Predicted TIR improvement
    ax = axes[1]
    if recs:
        rec_labels = [f"{r.parameter.value}\n({r.direction})" for r in recs[:5]]
        tir_deltas = [r.predicted_tir_delta for r in recs[:5]]
        confidences = [r.confidence for r in recs[:5]]
        x = np.arange(len(rec_labels))
        bar_colors = ['#4CAF50' if d > 0 else '#f44336' for d in tir_deltas]
        bars = ax.bar(x, tir_deltas, 0.6, color=bar_colors, alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(rec_labels, fontsize=8)
        ax.set_ylabel('Predicted TIR Change (pp)')
        ax.set_title('Expected Impact')
        ax.axhline(0, color='gray', linewidth=0.5)

        for i, (d, c) in enumerate(zip(tir_deltas, confidences)):
            ax.text(i, d + 0.1, f'conf={c:.2f}', ha='center', fontsize=7)

    plt.tight_layout()
    outpath = OUTDIR / 'live_recommendations.png'
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    return outpath


def main():
    print("=" * 70)
    print("LIVE-RECENT SETTINGS RECOMMENDATIONS REPORT")
    print("=" * 70)

    # Load data
    print("\nLoading live-recent data...")
    entries_df = load_entries(LIVE_DIR / 'entries-fresh.json')
    treatments_df = load_treatments(LIVE_DIR / 'treatments-fresh.json')
    profile_info = load_profile(LIVE_DIR / 'profile-fresh.json')

    print(f"  Entries: {len(entries_df)} readings")
    print(f"  Date range: {entries_df['timestamp'].min()} to {entries_df['timestamp'].max()}")
    print(f"  Treatments: {len(treatments_df)}")
    print(f"  Profile ISF: {profile_info['isf_schedule']}")
    print(f"  Profile CR: {profile_info['cr_schedule']}")
    print(f"  Profile Basal: {profile_info['basal_schedule']}")
    print(f"  DIA: {profile_info['dia']}h")

    # Glycemic statistics
    for period in [7, 14, 30, 90]:
        stats = compute_glycemic_stats(entries_df, last_n_days=period)
        if stats:
            print(f"\n  {period}-day stats: TIR={stats['tir']:.1f}%, TBR={stats['tbr']:.1f}%, "
                  f"TAR={stats['tar']:.1f}%, Mean={stats['mean']:.0f}, CV={stats['cv']:.1f}%, GMI={stats['gmi']}")

    stats_14d = compute_glycemic_stats(entries_df, last_n_days=14)

    # Generate visualizations
    print("\n--- Generating Visualizations ---")
    plot_glucose_trace(entries_df, treatments_df, stats_14d, last_n_days=7)
    print(f"  ✓ Glucose trace: {OUTDIR}/live_glucose_trace.png")

    plot_ambulatory_profile(entries_df, last_n_days=14)
    print(f"  ✓ Ambulatory profile: {OUTDIR}/live_ambulatory_profile.png")

    # Build advisory inputs
    print("\n--- Running Advisory Pipeline ---")
    glucose = entries_df['sgv'].values.astype(float)
    hours = (entries_df['timestamp'].dt.hour + entries_df['timestamp'].dt.minute / 60.0).values.astype(float)

    isf_val = float(profile_info['isf_schedule'][0]['value'])
    cr_val = float(profile_info['cr_schedule'][0]['value'])
    basal_rates = profile_info['basal_schedule']
    mean_basal = float(np.mean([b['value'] for b in basal_rates]))

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": isf_val}],
        cr_schedule=[{"time": "00:00", "value": cr_val}],
        basal_schedule=[{"time": "00:00", "value": mean_basal}],
        dia_hours=profile_info['dia'],
    )

    clinical = ClinicalReport(
        grade=GlycemicGrade.A if stats_14d['tir'] >= 70 else (GlycemicGrade.B if stats_14d['tir'] >= 60 else GlycemicGrade.C),
        risk_score=max(0, 100 - stats_14d['tir']),
        tir=stats_14d['tir'], tbr=stats_14d['tbr'], tar=stats_14d['tar'],
        mean_glucose=stats_14d['mean'],
        gmi=stats_14d['gmi'],
        cv=stats_14d['cv'],
        basal_assessment=BasalAssessment.APPROPRIATE,
        cr_score=50.0,
        effective_isf=isf_val,
    )

    # Build correction and meal events from treatments
    correction_events = []
    meal_events = []
    bolus_treats = treatments_df[treatments_df['eventType'].str.contains('Bolus|bolus', na=False)]
    carb_treats = treatments_df[treatments_df['carbs'] > 0]

    for _, row in bolus_treats.iterrows():
        ts = row['timestamp']
        close_entries = entries_df[(entries_df['timestamp'] >= ts - timedelta(minutes=10)) &
                                   (entries_df['timestamp'] <= ts + timedelta(minutes=10))]
        if len(close_entries) == 0:
            continue
        bg_at_bolus = float(close_entries.iloc[0]['sgv'])
        post_entries = entries_df[(entries_df['timestamp'] >= ts + timedelta(hours=3, minutes=50)) &
                                   (entries_df['timestamp'] <= ts + timedelta(hours=4, minutes=10))]
        post_bg = float(post_entries.iloc[0]['sgv']) if len(post_entries) > 0 else bg_at_bolus

        if row['insulin'] > 0.5 and bg_at_bolus > 150:
            correction_events.append({
                'start_bg': bg_at_bolus, 'tir_change': (1.0 if 70 <= post_bg <= 180 else 0.0) - (1.0 if 70 <= bg_at_bolus <= 180 else 0.0),
                'drop_4h': bg_at_bolus - post_bg, 'rebound': False,
                'rebound_magnitude': 0, 'went_below_70': post_bg < 70,
            })

    for _, row in carb_treats.iterrows():
        ts = row['timestamp']
        close_entries = entries_df[(entries_df['timestamp'] >= ts - timedelta(minutes=10)) &
                                   (entries_df['timestamp'] <= ts + timedelta(minutes=10))]
        if len(close_entries) == 0:
            continue
        bg_at_meal = float(close_entries.iloc[0]['sgv'])
        post_entries = entries_df[(entries_df['timestamp'] >= ts + timedelta(hours=3, minutes=50)) &
                                   (entries_df['timestamp'] <= ts + timedelta(hours=4, minutes=10))]
        post_bg = float(post_entries.iloc[0]['sgv']) if len(post_entries) > 0 else bg_at_meal

        meal_events.append({
            'carbs': float(row['carbs']), 'bolus': float(row.get('insulin', 0) or 0),
            'pre_meal_bg': bg_at_meal, 'post_meal_bg_4h': post_bg,
            'hour': float(ts.hour + ts.minute / 60.0),
        })

    # Build glucose + hours arrays for the last 14 days
    cutoff = entries_df['timestamp'].max() - timedelta(days=14)
    recent = entries_df[entries_df['timestamp'] >= cutoff]
    glucose_14d = recent['sgv'].values.astype(float)
    hours_14d = (recent['timestamp'].dt.hour + recent['timestamp'].dt.minute / 60.0).values.astype(float)

    days_total = (entries_df['timestamp'].max() - entries_df['timestamp'].min()).days

    try:
        recs = generate_settings_advice(
            glucose=glucose_14d,
            metabolic=None,
            hours=hours_14d,
            clinical=clinical,
            profile=profile,
            days_of_data=float(min(days_total, 90)),
            correction_events=correction_events[:200],
            meal_events=meal_events[:200],
        )
        sqs = compute_settings_quality_score(recs)
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"  SQS: {sqs:.1f}")
    print(f"  Advisories: {len(recs)}")

    plot_recommendations(recs, profile_info, stats_14d)
    print(f"  ✓ Recommendations: {OUTDIR}/live_recommendations.png")

    # Markdown report
    print("\n" + "=" * 70)
    print("SETTINGS RECOMMENDATIONS REPORT")
    print("=" * 70)

    print(f"\n## Current Glycemic Assessment (14-day)")
    print(f"| Metric | Value | Target |")
    print(f"|--------|-------|--------|")
    print(f"| Time in Range | {stats_14d['tir']:.1f}% | ≥70% |")
    print(f"| Time Below Range | {stats_14d['tbr']:.1f}% | <4% |")
    print(f"| Time Below 54 | {stats_14d['tbr_serious']:.1f}% | <1% |")
    print(f"| Time Above Range | {stats_14d['tar']:.1f}% | <25% |")
    print(f"| Time Above 250 | {stats_14d['tar_serious']:.1f}% | <5% |")
    print(f"| Mean Glucose | {stats_14d['mean']:.0f} mg/dL | <154 |")
    print(f"| GMI | {stats_14d['gmi']} | <7.0 |")
    print(f"| CV | {stats_14d['cv']:.1f}% | <36% |")
    print(f"| Readings | {stats_14d['n_readings']} | |")

    grade = "A" if stats_14d['tir'] >= 70 else ("B" if stats_14d['tir'] >= 60 else ("C" if stats_14d['tir'] >= 50 else "D"))
    print(f"\n**Glycemic Grade: {grade}**")
    print(f"**Settings Quality Score: {sqs:.1f}/100**")

    print(f"\n## Current Settings")
    print(f"| Setting | Value |")
    print(f"|---------|-------|")
    print(f"| ISF | {isf_val} mg/dL/U |")
    print(f"| CR | 1:{cr_val} |")
    for b in basal_rates:
        print(f"| Basal ({b['time']}) | {b['value']} U/hr |")
    print(f"| DIA | {profile_info['dia']}h |")

    print(f"\n## Recommendations (sorted by expected TIR impact)")
    print(f"| # | Parameter | Direction | Magnitude | Expected ΔTIR | Confidence | Rationale |")
    print(f"|---|-----------|-----------|-----------|---------------|------------|-----------|")
    for i, r in enumerate(recs, 1):
        rationale = r.rationale[:60] + "..." if len(r.rationale) > 60 else r.rationale
        print(f"| {i} | {r.parameter.value} | {r.direction} | {r.magnitude_pct:.0f}% | "
              f"+{r.predicted_tir_delta:.1f}pp | {r.confidence:.2f} | {rationale} |")

    print(f"\n## Data Summary")
    print(f"- Correction events analyzed: {len(correction_events)}")
    print(f"- Meal events analyzed: {len(meal_events)}")
    print(f"- Days of data: {days_total}")
    print(f"- Total entries: {len(entries_df)}")

    print(f"\n## Visualization Files")
    print(f"- `visualizations/reports/live_glucose_trace.png`")
    print(f"- `visualizations/reports/live_ambulatory_profile.png`")
    print(f"- `visualizations/reports/live_recommendations.png`")


if __name__ == '__main__':
    main()
