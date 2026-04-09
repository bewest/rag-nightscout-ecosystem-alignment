#!/usr/bin/env python3
"""Generate private clinical report for live-recent data.

Reads from: externals/ns-data/live-recent/
Outputs to: externals/ns-data/live-recent/reports/  (git-ignored)

Usage:
    PYTHONPATH=tools python tools/cgmencode/run_private_report.py
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

LIVE_DIR = ROOT / 'externals' / 'ns-data' / 'live-recent'
REPORT_DIR = LIVE_DIR / 'reports'

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib required"); sys.exit(1)

plt.rcParams.update({'figure.figsize': (12, 6), 'font.size': 10})


# ── Data Loading ─────────────────────────────────────────────────────

def load_live_data():
    """Load live-recent Nightscout JSON into pipeline format."""
    from cgmencode.production.types import PatientData, PatientProfile

    manifest = json.load(open(LIVE_DIR / 'manifest.json'))
    print(f"  Source: {manifest.get('source', 'unknown')}")
    print(f"  Date range: {manifest.get('dateRange', {}).get('start')} → "
          f"{manifest.get('dateRange', {}).get('end')}")
    print(f"  Entries: {manifest['counts']['entries']}, "
          f"Treatments: {manifest['counts']['treatments']}")

    # Load entries (SGV data)
    entries = json.load(open(LIVE_DIR / 'entries.json'))
    if not entries:
        print("  ERROR: No entries data")
        return None, manifest

    # Sort by date
    entries.sort(key=lambda e: e.get('date', e.get('dateString', 0)))

    # Build DataFrame
    records = []
    for e in entries:
        if e.get('type') != 'sgv':
            continue
        ts = e.get('date')
        if isinstance(ts, str):
            ts = pd.Timestamp(ts).timestamp() * 1000
        sgv = e.get('sgv')
        if sgv is None or ts is None:
            continue
        records.append({'date': float(ts), 'sgv': float(sgv),
                        'direction': e.get('direction', 'NONE')})

    if not records:
        print("  ERROR: No SGV records")
        return None, manifest

    df = pd.DataFrame(records).sort_values('date').reset_index(drop=True)
    print(f"  SGV records: {len(df)}")

    # Load treatments
    treatments = json.load(open(LIVE_DIR / 'treatments.json'))
    bolus_map = {}
    carb_map = {}
    temp_basal_map = {}
    for t in treatments:
        ts = t.get('created_at') or t.get('timestamp')
        if not ts:
            continue
        if isinstance(ts, str):
            try:
                ts = pd.Timestamp(ts).timestamp() * 1000
            except:
                continue
        evt = t.get('eventType', '')
        if 'Bolus' in evt or t.get('insulin'):
            ins = t.get('insulin', 0)
            if ins and ins > 0:
                bolus_map[float(ts)] = float(ins)
        if t.get('carbs'):
            carb_map[float(ts)] = float(t['carbs'])
        if 'Temp Basal' in evt:
            temp_basal_map[float(ts)] = float(t.get('rate', 0))

    # Load profile
    profiles = json.load(open(LIVE_DIR / 'profile.json'))
    if profiles:
        prof = profiles[0] if isinstance(profiles, list) else profiles
        store = prof.get('store', {})
        active_name = prof.get('defaultProfile', list(store.keys())[0] if store else '')
        active = store.get(active_name, {})

        sens = active.get('sens', active.get('sensitivity', []))
        isf_schedule = []
        if isinstance(sens, list):
            for s in sens:
                isf_schedule.append({
                    'time': s.get('time', s.get('timeAsSeconds', '00:00')),
                    'value': s.get('value', s.get('sensitivity', 50))
                })
        cr_list = active.get('carbratio', [])
        cr_schedule = []
        if isinstance(cr_list, list):
            for c in cr_list:
                cr_schedule.append({
                    'time': c.get('time', '00:00'),
                    'value': c.get('value', c.get('carbratio', 10))
                })
        basal_list = active.get('basal', [])
        basal_schedule = []
        if isinstance(basal_list, list):
            for b in basal_list:
                basal_schedule.append({
                    'time': b.get('time', '00:00'),
                    'value': b.get('value', b.get('rate', 0.8))
                })

        units = active.get('units', prof.get('units', 'mg/dL'))
        dia = active.get('dia', prof.get('dia', 5.0))
    else:
        isf_schedule = [{'time': '00:00', 'value': 50}]
        cr_schedule = [{'time': '00:00', 'value': 10}]
        basal_schedule = [{'time': '00:00', 'value': 0.8}]
        units = 'mg/dL'
        dia = 5.0

    profile = PatientProfile(
        isf_schedule=isf_schedule,
        cr_schedule=cr_schedule,
        basal_schedule=basal_schedule,
        dia_hours=float(dia),
        units=units,
    )
    print(f"  Profile: ISF={isf_schedule}, units={units}")

    # Build 5-min grid
    ts_min = df['date'].min()
    ts_max = df['date'].max()
    grid_ts = np.arange(ts_min, ts_max + 300_000, 300_000)
    n = len(grid_ts)

    glucose = np.full(n, np.nan)
    for _, row in df.iterrows():
        idx = int((row['date'] - ts_min) / 300_000)
        if 0 <= idx < n:
            glucose[idx] = row['sgv']

    # Interpolate short gaps
    valid = ~np.isnan(glucose)
    if valid.sum() > 10:
        glucose = pd.Series(glucose).interpolate(method='linear', limit=6).values

    # Map treatments to grid
    bolus = np.zeros(n)
    carbs = np.zeros(n)
    for ts, val in bolus_map.items():
        idx = int((ts - ts_min) / 300_000)
        if 0 <= idx < n:
            bolus[idx] += val
    for ts, val in carb_map.items():
        idx = int((ts - ts_min) / 300_000)
        if 0 <= idx < n:
            carbs[idx] += val

    patient = PatientData(
        glucose=glucose,
        timestamps=grid_ts,
        profile=profile,
        patient_id='live-recent',
        bolus=bolus,
        carbs=carbs,
    )
    print(f"  Grid: {n} steps ({patient.days_of_data:.1f} days), "
          f"{valid.sum()} valid glucose readings")

    return patient, manifest


# ── Visualization ────────────────────────────────────────────────────

def fig_glucose_overview(patient, result, manifest):
    """Multi-day glucose trace with meal markers and hypo zones."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)

    ts_hours = (patient.timestamps - patient.timestamps[0]) / 3600_000
    glucose = patient.glucose

    # Panel 1: Full glucose trace
    ax = axes[0]
    ax.plot(ts_hours, glucose, 'b-', linewidth=0.5, alpha=0.7)
    ax.axhspan(70, 180, color='green', alpha=0.1, label='Target range')
    ax.axhline(70, color='red', linestyle='--', alpha=0.3)
    ax.axhline(180, color='orange', linestyle='--', alpha=0.3)
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_title(f'Glucose Overview — {patient.days_of_data:.0f} days')
    ax.legend(fontsize=8)
    ax.set_ylim(40, 350)

    # Panel 2: Daily overlay (last 14 days)
    ax = axes[1]
    hours_of_day = (patient.timestamps % 86400_000) / 3600_000
    days = (patient.timestamps - patient.timestamps[0]) / 86400_000
    n_days = int(days[-1])
    cmap = plt.cm.viridis(np.linspace(0.2, 0.8, min(n_days, 14)))
    for d in range(max(0, n_days - 14), n_days):
        mask = (days >= d) & (days < d + 1)
        if mask.sum() > 0:
            ax.plot(hours_of_day[mask], glucose[mask], '-',
                    color=cmap[d - max(0, n_days - 14)], alpha=0.4, linewidth=0.8)
    ax.axhspan(70, 180, color='green', alpha=0.1)
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_title('Daily Overlay (last 14 days)')
    ax.set_xlim(0, 24)
    ax.set_ylim(40, 350)

    # Panel 3: Treatments
    ax = axes[2]
    if patient.bolus is not None:
        bolus_idx = patient.bolus > 0
        if bolus_idx.any():
            ax.stem(ts_hours[bolus_idx], patient.bolus[bolus_idx],
                    linefmt='b-', markerfmt='bo', basefmt='', label='Bolus (U)')
    if patient.carbs is not None:
        carb_idx = patient.carbs > 0
        if carb_idx.any():
            ax.stem(ts_hours[carb_idx], patient.carbs[carb_idx],
                    linefmt='orange', markerfmt='o', basefmt='', label='Carbs (g)')
    ax.set_xlabel('Hours from start')
    ax.set_ylabel('Amount')
    ax.set_title('Treatments')
    ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(REPORT_DIR / 'fig1_glucose_overview.png', dpi=150)
    plt.close()
    print("  fig1_glucose_overview.png")


def fig_clinical_summary(result):
    """Clinical metrics dashboard."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    cr = result.clinical_report

    # TIR pie
    ax = axes[0, 0]
    sizes = [cr.tir, cr.tbr, cr.tar]
    labels = [f'TIR\n{cr.tir*100:.0f}%', f'TBR\n{cr.tbr*100:.0f}%', f'TAR\n{cr.tar*100:.0f}%']
    colors = ['#2ecc71', '#e74c3c', '#f1c40f']
    ax.pie(sizes, labels=labels, colors=colors, autopct='', startangle=90,
           textprops={'fontweight': 'bold'})
    ax.set_title(f'Glycemic Distribution — ADA Grade: {cr.grade.value}')

    # Fidelity
    ax = axes[0, 1]
    fid = getattr(cr, 'fidelity', None)
    if fid:
        metrics = {'RMSE': fid.rmse, 'Corr.\nEnergy': fid.correction_energy / 100,
                   'R²': max(0, (fid.r2 or 0)) * 10}
        bars = ax.bar(list(metrics.keys()), list(metrics.values()),
                      color=['#3498db', '#e67e22', '#9b59b6'], alpha=0.8)
        ax.set_title(f'Fidelity: {fid.fidelity_grade.value} '
                     f'(RMSE={fid.rmse:.1f}, CE={fid.correction_energy:.0f})')
    else:
        ax.text(0.5, 0.5, 'Fidelity not computed\n(insufficient data)',
                ha='center', va='center', transform=ax.transAxes, fontsize=12)
        ax.set_title('Fidelity Assessment')

    # Circadian
    ax = axes[1, 0]
    if result.patterns and result.patterns.harmonic:
        h = result.patterns.harmonic
        hours = np.linspace(0, 24, 200)
        pred = h.predict(hours)
        ax.plot(hours, pred, 'g-', linewidth=2, label=f'4-Harmonic (R²={h.r2:.3f})')
        if result.patterns.circadian:
            c = result.patterns.circadian
            sin_fit = c.a + c.amplitude * np.sin(2 * np.pi * (hours - c.phase_hours) / 24)
            ax.plot(hours, sin_fit, 'r--', alpha=0.5,
                    label=f'Sinusoidal (R²={c.r2_improvement or 0:.3f})')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Glucose (mg/dL)')
        ax.legend(fontsize=9)
        ax.set_xlim(0, 24)
    ax.set_title('Circadian Pattern')

    # ISF assessment
    ax = axes[1, 1]
    info_lines = []
    if cr.effective_isf:
        info_lines.append(f"Effective ISF: {cr.effective_isf:.1f} mg/dL")
    if cr.profile_isf:
        info_lines.append(f"Profile ISF: {cr.profile_isf:.1f} mg/dL")
    if cr.isf_discrepancy:
        info_lines.append(f"Discrepancy: {cr.isf_discrepancy:.2f}×")
    if cr.basal_assessment:
        info_lines.append(f"Basal: {cr.basal_assessment.value}")
    if cr.cr_score is not None:
        info_lines.append(f"CR Score: {cr.cr_score:.2f}")

    ax.text(0.1, 0.5, '\n'.join(info_lines) if info_lines else 'No ISF data',
            transform=ax.transAxes, fontsize=13, va='center',
            family='monospace')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title('Settings Assessment')

    plt.suptitle('Clinical Summary — Live Data', fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(REPORT_DIR / 'fig2_clinical_summary.png', dpi=150)
    plt.close()
    print("  fig2_clinical_summary.png")


def fig_meal_analysis(result):
    """Meal detection and archetype analysis."""
    mh = result.meal_history
    if not mh or not mh.meals:
        print("  SKIP fig3: no meals")
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    meals = mh.meals

    # Meal timing distribution
    ax = axes[0]
    meal_hours = []
    for m in meals:
        if hasattr(m, 'timestamp_ms') and m.timestamp_ms:
            h = (m.timestamp_ms % 86400_000) / 3600_000
            meal_hours.append(h)
    if meal_hours:
        ax.hist(meal_hours, bins=24, range=(0, 24), color='#e67e22', alpha=0.8)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Count')
    ax.set_title(f'Meal Timing Distribution (n={len(meals)})')

    # Announced vs Unannounced
    ax = axes[1]
    n_ann = sum(1 for m in meals if m.is_announced)
    n_uam = len(meals) - n_ann
    ax.bar(['Announced', 'Unannounced'], [n_ann, n_uam],
           color=['#3498db', '#e74c3c'], alpha=0.8)
    ax.set_ylabel('Count')
    ax.set_title(f'Meal Announcement ({n_ann/(n_ann+n_uam)*100:.0f}% announced)')

    # Archetype distribution
    ax = axes[2]
    ctrl = sum(1 for m in meals if getattr(m, 'archetype', None) and 'CONTROLLED' in str(m.archetype))
    high = sum(1 for m in meals if getattr(m, 'archetype', None) and 'HIGH' in str(m.archetype))
    other = len(meals) - ctrl - high
    if ctrl or high:
        ax.bar(['Controlled\nRise', 'High\nExcursion', 'Unclassified'],
               [ctrl, high, other],
               color=['#2ecc71', '#e74c3c', '#95a5a6'], alpha=0.8)
    else:
        ax.bar(['All Meals'], [len(meals)], color='#95a5a6')
    ax.set_ylabel('Count')
    ax.set_title('Meal Archetypes')

    plt.tight_layout()
    plt.savefig(REPORT_DIR / 'fig3_meal_analysis.png', dpi=150)
    plt.close()
    print("  fig3_meal_analysis.png")


# ── Report Generation ────────────────────────────────────────────────

def generate_private_report(patient, result, manifest):
    """Generate markdown report for live-recent data."""
    cr = result.clinical_report
    fid = getattr(cr, 'fidelity', None)
    mh = result.meal_history

    lines = [
        "# Private Clinical Inference Report — Live Data",
        "",
        f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Source**: {manifest.get('source', 'unknown')}",
        f"**Date Range**: {manifest.get('dateRange', {}).get('start', 'N/A')} → "
        f"{manifest.get('dateRange', {}).get('end', 'N/A')}",
        f"**Duration**: {patient.days_of_data:.1f} days ({patient.n_samples} samples)",
        f"**Pipeline**: Production (72 tests, commit 7246a46)",
        "",
        "---",
        "",
        "## Glucose Overview",
        "",
        "![Glucose Overview](fig1_glucose_overview.png)",
        "",
        "## Clinical Summary",
        "",
        "![Clinical Summary](fig2_clinical_summary.png)",
        "",
        "### Glycemic Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Time in Range (70-180) | {cr.tir*100:.1f}% |",
        f"| Time Below Range (<70) | {cr.tbr*100:.1f}% |",
        f"| Time Above Range (>180) | {cr.tar*100:.1f}% |",
        f"| ADA Grade | {cr.grade.value} |",
        f"| Mean Glucose | {cr.mean_glucose:.0f} mg/dL |" if hasattr(cr, 'mean_glucose') and cr.mean_glucose else "| Mean Glucose | N/A |",
        f"| GMI (est. A1c) | {cr.gmi:.1f}% |" if hasattr(cr, 'gmi') and cr.gmi else "| GMI | N/A |",
    ]

    if fid:
        lines.extend([
            "",
            "### Fidelity Assessment",
            "",
            f"**Grade**: {fid.fidelity_grade.value}",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| RMSE | {fid.rmse:.2f} mg/dL/5min |",
            f"| Correction Energy | {fid.correction_energy:.0f} |",
            f"| R² | {fid.r2:.3f} |" if fid.r2 is not None else "| R² | N/A |",
            f"| Conservation Integral | {fid.conservation_integral:.0f} |" if hasattr(fid, 'conservation_integral') and fid.conservation_integral else "",
        ])

    # Settings analysis
    lines.extend([
        "",
        "### Settings Assessment",
        "",
        f"**Profile Units**: {patient.profile.units}",
        "",
    ])

    isf_raw = [e.get('value', e.get('sensitivity')) for e in patient.profile.isf_schedule]
    isf_mgdl = [e.get('value', e.get('sensitivity')) for e in patient.profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio')) for e in patient.profile.cr_schedule]
    lines.append(f"**Profile ISF**: {isf_raw} {patient.profile.units}"
                 + (f" → {[f'{v:.1f}' for v in isf_mgdl]} mg/dL"
                    if patient.profile.is_mmol or all(v < 15 for v in isf_raw if v) else ""))
    lines.append(f"**Profile CR**: {cr_vals}")
    lines.append(f"**DIA**: {patient.profile.dia_hours}h")
    lines.append("")

    if cr.effective_isf:
        lines.append(f"**Effective ISF**: {cr.effective_isf:.1f} mg/dL")
    if cr.profile_isf:
        lines.append(f"**Profile ISF (mg/dL)**: {cr.profile_isf:.1f}")
    if cr.isf_discrepancy:
        lines.append(f"**ISF Discrepancy**: {cr.isf_discrepancy:.2f}× profile")
        if abs(cr.isf_discrepancy) > 1.5:
            lines.append(f"  ⚠️  Significant ISF mismatch — effective ISF differs "
                         f"substantially from profile settings.")
    lines.append("")

    # Circadian
    if result.patterns:
        lines.extend(["### Circadian Pattern", ""])
        if result.patterns.harmonic:
            h = result.patterns.harmonic
            lines.append(f"**4-Harmonic Model**: R² = {h.r2:.3f}")
            lines.append(f"**Dominant Period**: {h.dominant_period:.0f}h "
                         f"(amplitude: {h.dominant_amplitude:.1f} mg/dL)")
        if result.patterns.circadian:
            c = result.patterns.circadian
            lines.append(f"**Legacy Sinusoidal**: R² = {c.r2_improvement or 0:.3f}, "
                         f"amplitude = {c.amplitude:.1f} mg/dL, "
                         f"peak at {c.phase_hours:.1f}h")
        lines.append("")

    # Meals
    if mh and mh.meals:
        lines.extend([
            "## Meal Analysis",
            "",
            "![Meal Analysis](fig3_meal_analysis.png)",
            "",
            f"**Total meals detected**: {len(mh.meals)}",
        ])
        n_ann = sum(1 for m in mh.meals if m.is_announced)
        n_uam = len(mh.meals) - n_ann
        lines.append(f"**Announced**: {n_ann} ({n_ann/len(mh.meals)*100:.0f}%)")
        lines.append(f"**Unannounced (UAM)**: {n_uam} ({n_uam/len(mh.meals)*100:.0f}%)")

        ctrl = sum(1 for m in mh.meals if getattr(m, 'archetype', None) and 'CONTROLLED' in str(m.archetype))
        high = sum(1 for m in mh.meals if getattr(m, 'archetype', None) and 'HIGH' in str(m.archetype))
        if ctrl or high:
            lines.append(f"**Controlled Rise**: {ctrl}")
            lines.append(f"**High Excursion**: {high}")

        if hasattr(mh, 'cr_score') and mh.cr_score:
            lines.append(f"**CR Score**: {mh.cr_score:.2f}")
        lines.append("")

    # Recommendations
    if result.settings_recs:
        lines.extend(["## Settings Recommendations", ""])
        for rec in result.settings_recs:
            cg = getattr(rec, 'confidence_grade', None)
            cg_str = f" (Confidence: {cg.value})" if cg else ""
            lines.append(f"- **{rec.parameter.value}**: {rec.suggestion}{cg_str}")
        lines.append("")

    if result.recommendations:
        lines.extend(["## Action Recommendations", ""])
        for rec in result.recommendations:
            lines.append(f"- [P{rec.priority}] {rec.description}")
        lines.append("")

    # Warnings
    if result.warnings:
        lines.extend(["## Pipeline Warnings", ""])
        for w in result.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*This report is generated by the production inference pipeline and is for "
        "informational purposes only. It is not medical advice. Always consult with "
        "your healthcare provider before making changes to diabetes management.*",
    ])

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Loading live-recent data ===")
    patient, manifest = load_live_data()
    if patient is None:
        print("Failed to load data")
        sys.exit(1)

    print(f"\n=== Running pipeline ===")
    from cgmencode.production.pipeline import run_pipeline
    t0 = time.time()
    result = run_pipeline(patient)
    elapsed = (time.time() - t0) * 1000
    print(f"  Pipeline completed in {elapsed:.0f}ms")

    print(f"\n=== Generating visualizations ===")
    fig_glucose_overview(patient, result, manifest)
    fig_clinical_summary(result)
    fig_meal_analysis(result)

    print(f"\n=== Generating report ===")
    report = generate_private_report(patient, result, manifest)
    report_path = REPORT_DIR / 'clinical-report.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"  Report: {report_path}")

    # Summary JSON
    cr = result.clinical_report
    fid = getattr(cr, 'fidelity', None)
    summary = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'source': manifest.get('source'),
        'days': patient.days_of_data,
        'n_samples': patient.n_samples,
        'tir': cr.tir,
        'tbr': cr.tbr,
        'tar': cr.tar,
        'ada_grade': cr.grade.value,
        'fidelity_grade': fid.fidelity_grade.value if fid else None,
        'fidelity_rmse': fid.rmse if fid else None,
        'effective_isf': cr.effective_isf,
        'profile_isf': cr.profile_isf,
        'isf_discrepancy': cr.isf_discrepancy,
        'n_meals': len(result.meal_history.meals) if result.meal_history else 0,
        'pipeline_ms': elapsed,
    }
    with open(REPORT_DIR / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Summary: {REPORT_DIR / 'summary.json'}")

    print("\nDone!")
