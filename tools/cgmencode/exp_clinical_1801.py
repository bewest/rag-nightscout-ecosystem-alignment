#!/usr/bin/env python3
"""
EXP-1801: Production Settings Optimizer Validation

Validates that the production settings_optimizer module produces results
concordant with the research recommend_settings() from EXP-1701.

Runs both pipelines on all patients and compares:
  - ISF mismatch ratios
  - Basal change directions
  - CR change directions
  - Confidence grades
  - TIR predictions

Also generates comparison visualizations.

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1801.py
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1801.py --max-patients 3
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# ── Ensure project root on path ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.production.pipeline import run_pipeline
from cgmencode.production.types import PatientData, PatientProfile
from cgmencode.production.settings_optimizer import optimize_settings
from cgmencode.production.natural_experiment_detector import detect_natural_experiments

# ── Patient Loading ──────────────────────────────────────────────────

def load_patients():
    """Load patients using the same method as exp_clinical_1701."""
    try:
        from cgmencode.exp_clinical_1701 import load_patients as _load
        return _load()
    except ImportError:
        from cgmencode.exp_clinical_1551 import load_patients as _load
        return _load()


def _patient_to_production(pat: dict) -> PatientData:
    """Convert research patient dict to production PatientData."""
    df = pat['df']
    name = pat['name']

    glucose = df['glucose'].values.astype(float) if 'glucose' in df.columns else df.iloc[:, 0].values.astype(float)
    n = len(glucose)

    # Timestamps
    if hasattr(df.index, 'astype'):
        try:
            ts = df.index.astype(np.int64) // 10**6  # ns → ms
        except Exception:
            ts = np.arange(n, dtype=np.int64) * 300_000 + 1735689600000
    else:
        ts = np.arange(n, dtype=np.int64) * 300_000 + 1735689600000

    # Profile
    isf_sched = df.attrs.get('isf_schedule', [{'time': '00:00', 'value': 50}])
    cr_sched = df.attrs.get('cr_schedule', [{'time': '00:00', 'value': 10}])
    basal_sched = df.attrs.get('basal_schedule', [{'time': '00:00', 'value': 0.8}])

    profile = PatientProfile(
        isf_schedule=isf_sched,
        cr_schedule=cr_sched,
        basal_schedule=basal_sched,
    )

    kwargs = dict(
        glucose=glucose,
        timestamps=ts,
        profile=profile,
        patient_id=name,
    )

    # Optional insulin data
    if 'iob' in df.columns:
        kwargs['iob'] = df['iob'].values.astype(float)
    if 'bolus' in df.columns:
        kwargs['bolus'] = df['bolus'].values.astype(float)
    if 'carbs' in df.columns:
        kwargs['carbs'] = df['carbs'].values.astype(float)
    if 'basal_rate' in df.columns:
        kwargs['basal_rate'] = df['basal_rate'].values.astype(float)

    return PatientData(**kwargs)


# ── Research Pipeline ────────────────────────────────────────────────

def _run_research(pat: dict) -> dict:
    """Run research recommend_settings on a patient."""
    try:
        from cgmencode.exp_clinical_1701 import recommend_settings
        return recommend_settings(pat)
    except Exception as e:
        return {'error': str(e)}


# ── Comparison Logic ─────────────────────────────────────────────────

def _compare_one(name: str, research: dict, production) -> dict:
    """Compare research vs production results for one patient."""
    if 'error' in research:
        return {'name': name, 'status': 'research_error', 'error': research['error']}
    if production is None:
        return {'name': name, 'status': 'production_none'}

    opt = production.optimal
    result = {'name': name, 'status': 'ok'}

    # ISF comparison
    research_isf = {}
    for period, vals in research.get('isf_schedule', {}).items():
        research_isf[period] = vals.get('isf', 0)

    prod_isf = {e.period: e.recommended_value for e in opt.isf_schedule}

    isf_concordance = []
    for period in research_isf:
        r_val = research_isf[period]
        p_val = prod_isf.get(period, 0)
        if r_val > 0 and p_val > 0:
            ratio = p_val / r_val
            isf_concordance.append(ratio)

    result['isf_concordance_mean'] = float(np.mean(isf_concordance)) if isf_concordance else None
    result['isf_concordance_std'] = float(np.std(isf_concordance)) if isf_concordance else None

    # Basal direction agreement
    research_basal = research.get('basal_schedule', {})
    prod_basal = {e.period: e for e in opt.basal_schedule}
    basal_agree = 0
    basal_total = 0
    for period in research_basal:
        r_rate = research_basal[period].get('rate', 0)
        p_entry = prod_basal.get(period)
        if p_entry is None:
            continue
        basal_total += 1
        # Check if both agree on direction vs profile
        r_current = 0.8  # default
        r_change = r_rate - r_current
        p_change = p_entry.recommended_value - p_entry.current_value
        if (r_change >= 0 and p_change >= 0) or (r_change < 0 and p_change < 0):
            basal_agree += 1

    result['basal_direction_agreement'] = basal_agree / max(basal_total, 1)

    # CR direction agreement
    research_cr = research.get('cr_schedule', {})
    prod_cr = {e.period: e for e in opt.cr_schedule}
    cr_agree = 0
    cr_total = 0
    for period in research_cr:
        r_cr = research_cr[period].get('cr', 0)
        p_entry = prod_cr.get(period)
        if p_entry is None:
            continue
        cr_total += 1
        r_change = r_cr - 10.0  # default profile CR
        p_change = p_entry.recommended_value - p_entry.current_value
        if (r_change >= 0 and p_change >= 0) or (r_change < 0 and p_change < 0):
            cr_agree += 1

    result['cr_direction_agreement'] = cr_agree / max(cr_total, 1)

    # Confidence comparison
    result['research_confidence'] = research.get('confidence', 'unknown')
    result['production_grade'] = opt.confidence_grade.value
    result['production_tir_delta'] = opt.predicted_tir_delta
    result['production_dominant'] = opt.dominant_lever
    result['total_evidence'] = opt.total_evidence
    result['n_recommendations'] = production.n_recommendations

    return result


# ── Visualizations ───────────────────────────────────────────────────

VIZ_DIR = PROJECT_ROOT / "visualizations" / "natural-experiments"


def viz_concordance(comparisons: list, output_path: Path):
    """Fig 64: ISF concordance scatter — research vs production."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # ISF concordance
    ax = axes[0]
    names = [c['name'] for c in comparisons if c.get('isf_concordance_mean')]
    vals = [c['isf_concordance_mean'] for c in comparisons if c.get('isf_concordance_mean')]
    if vals:
        colors = ['#2ecc71' if 0.8 <= v <= 1.2 else '#e74c3c' for v in vals]
        ax.barh(names, vals, color=colors, edgecolor='white')
        ax.axvline(1.0, color='black', linestyle='--', alpha=0.5)
        ax.axvspan(0.8, 1.2, alpha=0.1, color='green')
        ax.set_xlabel('Production / Research ISF Ratio')
        ax.set_title('ISF Concordance')
    else:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)

    # Direction agreement
    ax = axes[1]
    names_all = [c['name'] for c in comparisons if c.get('status') == 'ok']
    basal_ag = [c.get('basal_direction_agreement', 0) * 100 for c in comparisons if c.get('status') == 'ok']
    cr_ag = [c.get('cr_direction_agreement', 0) * 100 for c in comparisons if c.get('status') == 'ok']
    if names_all:
        x = np.arange(len(names_all))
        w = 0.35
        ax.bar(x - w/2, basal_ag, w, label='Basal', color='#3498db')
        ax.bar(x + w/2, cr_ag, w, label='CR', color='#e67e22')
        ax.set_xticks(x)
        ax.set_xticklabels(names_all, rotation=45, ha='right')
        ax.set_ylabel('Direction Agreement (%)')
        ax.set_title('Direction Concordance')
        ax.legend()
        ax.set_ylim(0, 110)
    else:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)

    # TIR prediction & evidence
    ax = axes[2]
    tir = [c.get('production_tir_delta', 0) for c in comparisons if c.get('status') == 'ok']
    evidence = [c.get('total_evidence', 0) for c in comparisons if c.get('status') == 'ok']
    if tir and evidence:
        scatter = ax.scatter(evidence, tir, c=tir, cmap='RdYlGn', s=100, edgecolors='black')
        for i, n in enumerate(names_all):
            ax.annotate(n, (evidence[i], tir[i]), fontsize=8, ha='left', va='bottom')
        ax.set_xlabel('Total Evidence Windows')
        ax.set_ylabel('Predicted TIR Δ (pp)')
        ax.set_title('Evidence vs TIR Prediction')
        plt.colorbar(scatter, ax=ax, label='TIR Δ')
    else:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)

    fig.suptitle('EXP-1801: Production vs Research Concordance', fontsize=14, fontweight='bold')
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {output_path}")


def viz_settings_dashboard(comparisons: list, output_path: Path):
    """Fig 65: Per-patient settings optimization dashboard."""
    ok = [c for c in comparisons if c.get('status') == 'ok']
    if not ok:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Top-left: Recommendations per patient
    ax = axes[0, 0]
    names = [c['name'] for c in ok]
    n_recs = [c.get('n_recommendations', 0) for c in ok]
    ax.barh(names, n_recs, color='#3498db', edgecolor='white')
    ax.set_xlabel('Actionable Recommendations')
    ax.set_title('Recommendations per Patient')
    ax.axvline(np.mean(n_recs), color='red', linestyle='--', label=f'Mean={np.mean(n_recs):.1f}')
    ax.legend()

    # Top-right: Confidence grades
    ax = axes[0, 1]
    grades = [c.get('production_grade', 'D') for c in ok]
    grade_counts = {}
    for g in grades:
        grade_counts[g] = grade_counts.get(g, 0) + 1
    grade_labels = sorted(grade_counts.keys())
    grade_vals = [grade_counts[g] for g in grade_labels]
    colors = {'A': '#27ae60', 'B': '#2ecc71', 'C': '#f39c12', 'D': '#e74c3c'}
    ax.bar(grade_labels, grade_vals, color=[colors.get(g, '#95a5a6') for g in grade_labels])
    ax.set_ylabel('Patient Count')
    ax.set_title('Confidence Grade Distribution')

    # Bottom-left: Dominant lever distribution
    ax = axes[1, 0]
    levers = [c.get('production_dominant', 'isf') for c in ok]
    lever_counts = {}
    for l in levers:
        lever_counts[l] = lever_counts.get(l, 0) + 1
    lever_labels = sorted(lever_counts.keys())
    lever_vals = [lever_counts[l] for l in lever_labels]
    ax.pie(lever_vals, labels=lever_labels, autopct='%1.0f%%',
           colors=['#3498db', '#e67e22', '#2ecc71'])
    ax.set_title('Dominant Improvement Lever')

    # Bottom-right: TIR delta distribution
    ax = axes[1, 1]
    tir = [c.get('production_tir_delta', 0) for c in ok]
    ax.hist(tir, bins=max(3, len(tir)//2), color='#2ecc71', edgecolor='black', alpha=0.8)
    ax.axvline(np.mean(tir), color='red', linestyle='--', label=f'Mean={np.mean(tir):.2f}pp')
    ax.set_xlabel('Predicted TIR Δ (pp)')
    ax.set_ylabel('Patient Count')
    ax.set_title('TIR Improvement Distribution')
    ax.legend()

    fig.suptitle('EXP-1801: Production Settings Optimizer Dashboard', fontsize=14, fontweight='bold')
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {output_path}")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-1801: Production Validation")
    parser.add_argument('--max-patients', type=int, default=None)
    args = parser.parse_args()

    print("=" * 60)
    print("EXP-1801: Production Settings Optimizer Validation")
    print("=" * 60)

    patients = load_patients()
    if args.max_patients:
        patients = patients[:args.max_patients]
    print(f"\nLoaded {len(patients)} patients")

    comparisons = []
    for i, pat in enumerate(patients):
        name = pat['name']
        print(f"\n[{i+1}/{len(patients)}] Patient {name}")

        # Run research pipeline
        print(f"  Running research recommend_settings()...")
        research = _run_research(pat)
        if 'error' in research:
            print(f"  ⚠ Research error: {research['error']}")

        # Run production pipeline
        print(f"  Converting to production format...")
        try:
            prod_patient = _patient_to_production(pat)
        except Exception as e:
            print(f"  ⚠ Conversion error: {e}")
            comparisons.append({'name': name, 'status': 'conversion_error', 'error': str(e)})
            continue

        print(f"  Running production pipeline...")
        try:
            prod_result = run_pipeline(prod_patient)
            prod_opt = prod_result.optimal_settings
            if prod_opt:
                print(f"  ✓ Production: grade={prod_opt.optimal.confidence_grade.value}, "
                      f"evidence={prod_opt.optimal.total_evidence}, "
                      f"TIR_Δ={prod_opt.optimal.predicted_tir_delta:.2f}pp, "
                      f"recs={prod_opt.n_recommendations}")
            else:
                print(f"  ⚠ Production returned None optimal_settings")
                if prod_result.warnings:
                    for w in prod_result.warnings:
                        if 'optim' in w.lower() or 'setting' in w.lower():
                            print(f"    Warning: {w}")
        except Exception as e:
            print(f"  ⚠ Production error: {e}")
            prod_opt = None

        # Compare
        comparison = _compare_one(name, research, prod_opt)
        comparisons.append(comparison)
        if comparison['status'] == 'ok':
            isf_c = comparison.get('isf_concordance_mean')
            print(f"  ISF concordance: {isf_c:.3f}" if isf_c else "  ISF concordance: N/A")
            print(f"  Basal direction: {comparison['basal_direction_agreement']:.0%}")
            print(f"  CR direction: {comparison['cr_direction_agreement']:.0%}")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    ok = [c for c in comparisons if c.get('status') == 'ok']
    print(f"  Successful: {len(ok)}/{len(comparisons)}")

    if ok:
        isf_conc = [c['isf_concordance_mean'] for c in ok if c.get('isf_concordance_mean')]
        basal_ag = [c['basal_direction_agreement'] for c in ok]
        cr_ag = [c['cr_direction_agreement'] for c in ok]
        tir = [c.get('production_tir_delta', 0) for c in ok]
        recs = [c.get('n_recommendations', 0) for c in ok]

        if isf_conc:
            print(f"  ISF concordance: {np.mean(isf_conc):.3f} ± {np.std(isf_conc):.3f}")
        print(f"  Basal direction agreement: {np.mean(basal_ag):.0%}")
        print(f"  CR direction agreement: {np.mean(cr_ag):.0%}")
        print(f"  Mean predicted TIR Δ: {np.mean(tir):.2f}pp")
        print(f"  Mean recommendations: {np.mean(recs):.1f}")

    # ── Save results ─────────────────────────────────────────────────
    results_path = PROJECT_ROOT / "externals" / "experiments" / "exp-1801_production_validation.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, 'w') as f:
        json.dump({
            'experiment': 'EXP-1801',
            'title': 'Production Settings Optimizer Validation',
            'n_patients': len(patients),
            'n_successful': len(ok),
            'comparisons': comparisons,
            'summary': {
                'isf_concordance_mean': float(np.mean(isf_conc)) if isf_conc else None,
                'basal_direction_agreement': float(np.mean(basal_ag)) if ok else None,
                'cr_direction_agreement': float(np.mean(cr_ag)) if ok else None,
                'mean_tir_delta': float(np.mean(tir)) if ok else None,
                'mean_recommendations': float(np.mean(recs)) if ok else None,
            },
        }, f, indent=2, default=str)
    print(f"\n  Results saved: {results_path}")

    # ── Visualizations ───────────────────────────────────────────────
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    if ok:
        viz_concordance(comparisons, VIZ_DIR / "fig64_production_concordance.png")
        viz_settings_dashboard(comparisons, VIZ_DIR / "fig65_production_dashboard.png")

    print("\n✓ EXP-1801 complete")
    return comparisons


if __name__ == "__main__":
    main()
