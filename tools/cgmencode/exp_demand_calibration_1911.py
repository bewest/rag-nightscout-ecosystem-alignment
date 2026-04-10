#!/usr/bin/env python3
"""EXP-1911–1918: Demand Calibration & Model Improvement.

The S/D model's demand scale varies from 0.1 to 3.0× across patients.
This batch investigates WHY and builds a patient-adaptive demand model.

Key question: What drives the massive demand scale variation?
Hypotheses:
  H1: AID system type (oref1 vs Loop vs MDI)
  H2: Total daily dose (higher TDD → different demand dynamics)
  H3: Data quality (missing insulin → demand under-counted)
  H4: Insulin sensitivity varies more than ISF profile captures
  H5: Hepatic glucose production varies by patient
  H6: Event-level calibration differs from global calibration
"""

import argparse
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

warnings.filterwarnings('ignore')

FIGURES_DIR = Path('docs/60-research/figures')
RESULTS_PATH = Path('externals/experiments/exp-1911_demand_calibration.json')

# --- Helpers ---

def get_isf(patient):
    isf_sched = patient['df'].attrs.get('isf_schedule', None)
    if isf_sched and isinstance(isf_sched, list) and len(isf_sched) > 0:
        val = isf_sched[0].get('value', isf_sched[0].get('sensitivity', 50))
        if val < 15:
            val *= 18.0182
        return val
    return 50

def get_cr(patient):
    cr_sched = patient['df'].attrs.get('cr_schedule', None)
    if cr_sched and isinstance(cr_sched, list) and len(cr_sched) > 0:
        return cr_sched[0].get('value', cr_sched[0].get('ratio', 10))
    return 10

def get_basal(patient):
    basal_sched = patient['df'].attrs.get('basal_schedule', None)
    if basal_sched and isinstance(basal_sched, list) and len(basal_sched) > 0:
        return basal_sched[0].get('value', basal_sched[0].get('rate', 1.0))
    return 1.0

def optimal_demand_scale(sd, glucose, scale_range=(0.01, 5.01), step=0.05):
    """Find optimal demand scale via grid search."""
    supply = sd.get('supply', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])
    best_scale = 1.0
    best_loss = np.inf
    for scale in np.arange(scale_range[0], scale_range[1], step):
        net = supply - demand * scale
        residual = dg - net
        valid = np.isfinite(residual)
        if valid.sum() < 10:
            continue
        loss = float(np.mean(residual[valid] ** 2))
        if loss < best_loss:
            best_loss = loss
            best_scale = scale
    return best_scale, best_loss

def patient_characteristics(patient):
    """Extract summary characteristics for correlation analysis."""
    df = patient['df']
    glucose = df['glucose'].values
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))

    valid_g = glucose[np.isfinite(glucose)]
    steps_per_day = 288

    # TDD (total daily dose) proxy
    daily_bolus = np.nansum(bolus) / (len(df) / steps_per_day)
    daily_basal = np.nansum(temp_rate / 12) / (len(df) / steps_per_day)  # U/h → U/5min × 12
    tdd = daily_bolus + daily_basal

    # Mean IOB
    mean_iob = float(np.nanmean(iob)) if np.any(np.isfinite(iob)) else 0

    # CGM coverage
    cgm_coverage = np.sum(np.isfinite(glucose)) / len(glucose)

    # Mean glucose
    mean_g = float(np.mean(valid_g)) if len(valid_g) > 0 else np.nan

    # CV
    cv = float(np.std(valid_g) / np.mean(valid_g)) if len(valid_g) > 100 and np.mean(valid_g) > 0 else np.nan

    # TIR
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) if len(valid_g) > 0 else 0

    # Daily carbs
    daily_carbs = np.nansum(carbs) / (len(df) / steps_per_day)

    # Zero delivery fraction (AID system proxy)
    zero_frac = float(np.mean(temp_rate == 0))

    # SMB ratio
    small = np.sum((bolus > 0) & (bolus < 0.5))
    large = np.sum(bolus >= 0.5)
    smb_ratio = small / max(large, 1)

    # Insulin data coverage
    insulin_coverage = np.sum(np.isfinite(iob) & (iob > 0)) / max(len(iob), 1)

    return {
        'tdd': round(float(tdd), 1),
        'daily_bolus': round(float(daily_bolus), 1),
        'daily_basal': round(float(daily_basal), 1),
        'mean_iob': round(float(mean_iob), 2),
        'mean_glucose': round(float(mean_g), 1),
        'cv': round(float(cv), 3) if np.isfinite(cv) else None,
        'tir': round(float(tir), 3),
        'daily_carbs': round(float(daily_carbs), 1),
        'cgm_coverage': round(float(cgm_coverage), 3),
        'insulin_coverage': round(float(insulin_coverage), 3),
        'zero_frac': round(float(zero_frac), 3),
        'smb_ratio': round(float(smb_ratio), 2),
    }

def classify_aid(smb_ratio, zero_frac, rate_change_freq=0):
    if smb_ratio > 2:
        return 'oref1/AAPS'
    elif zero_frac > 0.8:
        return 'MDI/Open'
    else:
        return 'Loop-like'


# ======================================================================
# EXP-1911: Demand Scale vs Patient Characteristics
# ======================================================================

def exp_1911(patients, figures_dir):
    """Correlate optimal demand scale with patient characteristics (TDD, TIR, CV, etc.).
    Identify which features predict demand scale."""
    print("\n" + "=" * 70)
    print("EXP-1911: Demand Scale vs Patient Characteristics")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)

        scale, loss = optimal_demand_scale(sd, glucose)
        chars = patient_characteristics(p)
        chars['patient'] = name
        chars['optimal_scale'] = round(scale, 2)
        chars['optimal_loss'] = round(loss, 2)
        chars['isf_profile'] = get_isf(p)
        chars['cr_profile'] = get_cr(p)
        chars['basal_profile'] = get_basal(p)
        results.append(chars)
        print(f"  {name}: scale={scale:.2f} TDD={chars['tdd']:.0f} TIR={chars['tir']:.1%}"
              f" CV={chars['cv']} zero={chars['zero_frac']:.1%} smb={chars['smb_ratio']:.1f}")

    # Correlation analysis
    scales = np.array([r['optimal_scale'] for r in results])
    features = ['tdd', 'daily_bolus', 'daily_basal', 'mean_iob', 'mean_glucose',
                'tir', 'daily_carbs', 'cgm_coverage', 'insulin_coverage',
                'zero_frac', 'smb_ratio', 'isf_profile', 'cr_profile', 'basal_profile']

    correlations = {}
    for feat in features:
        vals = np.array([r.get(feat, np.nan) or np.nan for r in results], dtype=float)
        valid = np.isfinite(vals) & np.isfinite(scales)
        if valid.sum() >= 5:
            r = np.corrcoef(scales[valid], vals[valid])[0, 1]
            correlations[feat] = round(float(r), 3)

    print(f"\n  Correlations with demand scale:")
    for feat, r in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    {feat}: r={r:+.3f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        names = [r['patient'] for r in results]

        top_feats = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)[:6]
        for idx, (feat, corr) in enumerate(top_feats):
            ax = axes[idx // 3, idx % 3]
            vals = [r.get(feat, 0) or 0 for r in results]
            ax.scatter(vals, scales, c='steelblue', s=80, alpha=0.7)
            for i, name in enumerate(names):
                ax.annotate(name, (vals[i], scales[i]), fontsize=8, ha='center', va='bottom')
            ax.set_xlabel(feat)
            ax.set_ylabel('Optimal Demand Scale')
            ax.set_title(f'{feat} vs scale (r={corr:+.3f})')

        plt.suptitle('EXP-1911: Demand Scale vs Patient Characteristics', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig01-scale-correlations.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    best_corr = max(correlations.items(), key=lambda x: abs(x[1]))
    verdict = f"BEST_CORRELATE:{best_corr[0]}(r={best_corr[1]:+.3f})"
    print(f"\n  ✓ EXP-1911 verdict: {verdict}")
    return {
        'experiment': 'EXP-1911', 'title': 'Demand Scale vs Characteristics',
        'verdict': verdict,
        'correlations': correlations,
        'per_patient': results,
    }


# ======================================================================
# EXP-1912: System-Type Effect on Demand Scale
# ======================================================================

def exp_1912(patients, figures_dir):
    """Compare demand scale distributions between oref1/AAPS, Loop-like, and MDI patients."""
    print("\n" + "=" * 70)
    print("EXP-1912: System-Type Effect on Demand Scale")
    print("=" * 70)

    groups = {'oref1/AAPS': [], 'Loop-like': [], 'MDI/Open': []}
    patient_info = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        scale, loss = optimal_demand_scale(sd, glucose)

        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        small = np.sum((bolus > 0) & (bolus < 0.5))
        large = np.sum(bolus >= 0.5)
        smb_ratio = small / max(large, 1)
        zero_frac = float(np.mean(temp_rate == 0))
        system = classify_aid(smb_ratio, zero_frac)

        groups[system].append({'patient': name, 'scale': scale, 'loss': loss})
        patient_info.append({'patient': name, 'system': system, 'scale': round(scale, 2), 'loss': round(loss, 2)})
        print(f"  {name}: system={system} scale={scale:.2f}")

    # Group statistics
    group_stats = {}
    for system, members in groups.items():
        if members:
            scales = [m['scale'] for m in members]
            group_stats[system] = {
                'n': len(members),
                'mean_scale': round(float(np.mean(scales)), 2),
                'std_scale': round(float(np.std(scales)), 2),
                'patients': [m['patient'] for m in members],
            }
            print(f"\n  {system} (n={len(members)}): mean_scale={np.mean(scales):.2f}±{np.std(scales):.2f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Box plot by system type
        system_data = {}
        for info in patient_info:
            sys = info['system']
            if sys not in system_data:
                system_data[sys] = []
            system_data[sys].append(info['scale'])

        labels = sorted(system_data.keys())
        data = [system_data[l] for l in labels]
        bp = axes[0].boxplot(data, labels=labels, patch_artist=True)
        colors = {'Loop-like': 'steelblue', 'oref1/AAPS': 'green', 'MDI/Open': 'gray'}
        for patch, label in zip(bp['boxes'], labels):
            patch.set_facecolor(colors.get(label, 'gray'))
            patch.set_alpha(0.6)
        axes[0].set_ylabel('Optimal Demand Scale')
        axes[0].set_title('Demand Scale by AID System Type')

        # Per-patient with system coloring
        names = [info['patient'] for info in patient_info]
        scales = [info['scale'] for info in patient_info]
        c = [colors.get(info['system'], 'gray') for info in patient_info]
        axes[1].bar(range(len(names)), scales, color=c, alpha=0.7)
        axes[1].set_xticks(range(len(names)))
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Optimal Demand Scale')
        axes[1].set_title('Per-Patient Demand Scale (colored by system)')

        plt.suptitle('EXP-1912: System-Type Effect on Demand Scale', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig02-system-type.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    # Test if system type matters
    oref_scales = [m['scale'] for m in groups.get('oref1/AAPS', [])]
    loop_scales = [m['scale'] for m in groups.get('Loop-like', [])]
    if oref_scales and loop_scales:
        diff = abs(np.mean(oref_scales) - np.mean(loop_scales))
        significant = diff > 0.5
    else:
        significant = False

    verdict = f"SYSTEM_{'MATTERS' if significant else 'MINOR'}"
    print(f"\n  ✓ EXP-1912 verdict: {verdict}")
    return {
        'experiment': 'EXP-1912', 'title': 'System-Type Effect',
        'verdict': verdict,
        'group_stats': group_stats,
        'per_patient': patient_info,
    }


# ======================================================================
# EXP-1913: Data Quality vs Demand Scale
# ======================================================================

def exp_1913(patients, figures_dir):
    """Test if demand scale variation is driven by data quality issues
    (missing insulin, CGM gaps, etc.)."""
    print("\n" + "=" * 70)
    print("EXP-1913: Data Quality vs Demand Scale")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        scale, loss = optimal_demand_scale(sd, glucose)

        # Data quality metrics
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))

        cgm_gaps = np.sum(~np.isfinite(glucose)) / len(glucose)
        iob_zero_frac = np.sum(iob == 0) / len(iob) if len(iob) > 0 else 1
        iob_nan_frac = np.sum(~np.isfinite(iob)) / len(iob) if len(iob) > 0 else 1
        bolus_frequency = np.sum(bolus > 0) / (len(df) / 288)  # boluses per day
        insulin_activity = np.sum(iob > 0) / max(np.sum(np.isfinite(iob)), 1)

        # Demand component statistics
        demand = sd.get('demand', np.zeros_like(glucose))
        demand_nonzero = np.sum(demand > 0.01) / len(demand)
        demand_mean = float(np.nanmean(demand))
        demand_max = float(np.nanmax(demand))

        result = {
            'patient': name,
            'optimal_scale': round(scale, 2),
            'cgm_gaps': round(float(cgm_gaps), 3),
            'iob_zero_frac': round(float(iob_zero_frac), 3),
            'iob_nan_frac': round(float(iob_nan_frac), 3),
            'bolus_per_day': round(float(bolus_frequency), 1),
            'insulin_activity': round(float(insulin_activity), 3),
            'demand_nonzero': round(float(demand_nonzero), 3),
            'demand_mean': round(float(demand_mean), 3),
            'demand_max': round(float(demand_max), 1),
        }
        results.append(result)
        print(f"  {name}: scale={scale:.2f} cgm_gaps={cgm_gaps:.1%} iob_zero={iob_zero_frac:.1%}"
              f" demand_nonzero={demand_nonzero:.1%} demand_mean={demand_mean:.2f}")

    # Correlation with scale
    scales = np.array([r['optimal_scale'] for r in results])
    quality_feats = ['cgm_gaps', 'iob_zero_frac', 'iob_nan_frac', 'bolus_per_day',
                     'insulin_activity', 'demand_nonzero', 'demand_mean', 'demand_max']
    correlations = {}
    for feat in quality_feats:
        vals = np.array([r[feat] for r in results], dtype=float)
        valid = np.isfinite(vals) & np.isfinite(scales)
        if valid.sum() >= 5:
            r = np.corrcoef(scales[valid], vals[valid])[0, 1]
            correlations[feat] = round(float(r), 3)

    print(f"\n  Data quality correlations with demand scale:")
    for feat, r in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    {feat}: r={r:+.3f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        names = [r['patient'] for r in results]

        # Demand activity vs scale
        axes[0, 0].scatter([r['demand_nonzero'] for r in results], scales, c='steelblue', s=80)
        for i, n in enumerate(names):
            axes[0, 0].annotate(n, ([r['demand_nonzero'] for r in results][i], scales[i]), fontsize=8)
        axes[0, 0].set_xlabel('Demand Nonzero Fraction')
        axes[0, 0].set_ylabel('Optimal Scale')
        axes[0, 0].set_title(f'Demand Activity (r={correlations.get("demand_nonzero", 0):+.3f})')

        # IOB zeros vs scale
        axes[0, 1].scatter([r['iob_zero_frac'] for r in results], scales, c='salmon', s=80)
        for i, n in enumerate(names):
            axes[0, 1].annotate(n, ([r['iob_zero_frac'] for r in results][i], scales[i]), fontsize=8)
        axes[0, 1].set_xlabel('IOB Zero Fraction')
        axes[0, 1].set_ylabel('Optimal Scale')
        axes[0, 1].set_title(f'IOB Availability (r={correlations.get("iob_zero_frac", 0):+.3f})')

        # Demand mean vs scale
        axes[1, 0].scatter([r['demand_mean'] for r in results], scales, c='green', s=80)
        for i, n in enumerate(names):
            axes[1, 0].annotate(n, ([r['demand_mean'] for r in results][i], scales[i]), fontsize=8)
        axes[1, 0].set_xlabel('Mean Demand')
        axes[1, 0].set_ylabel('Optimal Scale')
        axes[1, 0].set_title(f'Demand Magnitude (r={correlations.get("demand_mean", 0):+.3f})')

        # Bolus frequency vs scale
        axes[1, 1].scatter([r['bolus_per_day'] for r in results], scales, c='orange', s=80)
        for i, n in enumerate(names):
            axes[1, 1].annotate(n, ([r['bolus_per_day'] for r in results][i], scales[i]), fontsize=8)
        axes[1, 1].set_xlabel('Boluses per Day')
        axes[1, 1].set_ylabel('Optimal Scale')
        axes[1, 1].set_title(f'Bolus Frequency (r={correlations.get("bolus_per_day", 0):+.3f})')

        plt.suptitle('EXP-1913: Data Quality vs Demand Scale', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig03-data-quality.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    best = max(correlations.items(), key=lambda x: abs(x[1])) if correlations else ('none', 0)
    verdict = f"BEST_QUALITY_CORRELATE:{best[0]}(r={best[1]:+.3f})"
    print(f"\n  ✓ EXP-1913 verdict: {verdict}")
    return {
        'experiment': 'EXP-1913', 'title': 'Data Quality vs Demand Scale',
        'verdict': verdict,
        'correlations': correlations,
        'per_patient': results,
    }


# ======================================================================
# EXP-1914: Event-Level vs Global Demand Calibration
# ======================================================================

def exp_1914(patients, figures_dir):
    """Compare global demand scale to event-level (per-correction, per-meal) calibration.
    Does the demand model need one number or context-specific calibration?"""
    print("\n" + "=" * 70)
    print("EXP-1914: Event-Level vs Global Demand Calibration")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        n = len(glucose)
        sd = compute_supply_demand(df)

        # Global scale
        global_scale, global_loss = optimal_demand_scale(sd, glucose)

        # Meal-window scale (±3h around meals)
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
        meal_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            if carbs[i] >= 5:
                start = max(0, i - 6)
                end = min(n, i + 36)
                meal_mask[start:end] = True

        non_meal_mask = ~meal_mask
        meal_frac = meal_mask.sum() / n

        # Meal-window scale
        supply = sd.get('supply', np.zeros(n))
        demand = sd.get('demand', np.zeros(n))
        dg = np.diff(glucose, prepend=glucose[0])

        best_meal_scale = global_scale
        best_meal_loss = np.inf
        for scale in np.arange(0.01, 5.01, 0.1):
            net = supply - demand * scale
            residual = dg - net
            r_meal = residual[meal_mask]
            valid = np.isfinite(r_meal)
            if valid.sum() < 10:
                continue
            loss = float(np.mean(r_meal[valid] ** 2))
            if loss < best_meal_loss:
                best_meal_loss = loss
                best_meal_scale = scale

        # Non-meal scale
        best_nonmeal_scale = global_scale
        best_nonmeal_loss = np.inf
        for scale in np.arange(0.01, 5.01, 0.1):
            net = supply - demand * scale
            residual = dg - net
            r_nm = residual[non_meal_mask]
            valid = np.isfinite(r_nm)
            if valid.sum() < 10:
                continue
            loss = float(np.mean(r_nm[valid] ** 2))
            if loss < best_nonmeal_loss:
                best_nonmeal_loss = loss
                best_nonmeal_scale = scale

        result = {
            'patient': name,
            'global_scale': round(global_scale, 2),
            'meal_scale': round(best_meal_scale, 2),
            'nonmeal_scale': round(best_nonmeal_scale, 2),
            'scale_diff': round(abs(best_meal_scale - best_nonmeal_scale), 2),
            'meal_fraction': round(float(meal_frac), 3),
        }
        results.append(result)
        print(f"  {name}: global={global_scale:.2f} meal={best_meal_scale:.2f}"
              f" non-meal={best_nonmeal_scale:.2f} diff={abs(best_meal_scale - best_nonmeal_scale):.2f}"
              f" meal_frac={meal_frac:.1%}")

    # Population
    diffs = [r['scale_diff'] for r in results]
    context_matters = sum(1 for d in diffs if d > 0.3)
    print(f"\n  Population event-level calibration:")
    print(f"    Mean scale difference (meal vs non-meal): {np.mean(diffs):.2f}")
    print(f"    Context matters (diff>0.3): {context_matters}/{len(results)}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        axes[0].bar(x - 0.2, [r['global_scale'] for r in results], 0.2, label='Global', alpha=0.7)
        axes[0].bar(x, [r['meal_scale'] for r in results], 0.2, label='Meal', alpha=0.7, color='orange')
        axes[0].bar(x + 0.2, [r['nonmeal_scale'] for r in results], 0.2, label='Non-Meal', alpha=0.7, color='green')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Optimal Demand Scale')
        axes[0].set_title('Global vs Context-Specific Demand Scale')
        axes[0].legend()

        axes[1].bar(x, diffs, color=['red' if d > 0.3 else 'gray' for d in diffs], alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('|Meal Scale - Non-Meal Scale|')
        axes[1].set_title('Context Sensitivity of Demand Scale')
        axes[1].axhline(0.3, color='red', linestyle='--', label='Significance threshold')
        axes[1].legend()

        plt.suptitle('EXP-1914: Event-Level vs Global Demand Calibration', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig04-event-level.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"CONTEXT_{'MATTERS' if context_matters > len(results) / 2 else 'MINOR'}_{context_matters}/{len(results)}"
    print(f"\n  ✓ EXP-1914 verdict: {verdict}")
    return {
        'experiment': 'EXP-1914', 'title': 'Event-Level vs Global Calibration',
        'verdict': verdict,
        'mean_diff': round(float(np.mean(diffs)), 2),
        'context_matters_count': context_matters,
        'per_patient': results,
    }


# ======================================================================
# EXP-1915: Overnight-Only Demand Calibration
# ======================================================================

def exp_1915(patients, figures_dir):
    """Calibrate demand scale using overnight data only (midnight-6am).
    Minimal confounders: no meals, minimal boluses. Purest ISF signal."""
    print("\n" + "=" * 70)
    print("EXP-1915: Overnight-Only Demand Calibration")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        n = len(glucose)
        sd = compute_supply_demand(df)

        # Global scale
        global_scale, global_loss = optimal_demand_scale(sd, glucose)

        # Overnight mask (midnight-6am = steps 0-72 of each day)
        steps_per_day = 288
        overnight_mask = np.zeros(n, dtype=bool)
        for day_start in range(0, n, steps_per_day):
            end_overnight = min(day_start + 72, n)
            overnight_mask[day_start:end_overnight] = True

        supply = sd.get('supply', np.zeros(n))
        demand = sd.get('demand', np.zeros(n))
        dg = np.diff(glucose, prepend=glucose[0])

        # Overnight scale
        best_overnight_scale = global_scale
        best_overnight_loss = np.inf
        for scale in np.arange(0.01, 5.01, 0.05):
            net = supply - demand * scale
            residual = dg - net
            r_on = residual[overnight_mask]
            valid = np.isfinite(r_on)
            if valid.sum() < 50:
                continue
            loss = float(np.mean(r_on[valid] ** 2))
            if loss < best_overnight_loss:
                best_overnight_loss = loss
                best_overnight_scale = scale

        # Daytime scale (complement)
        daytime_mask = ~overnight_mask
        best_daytime_scale = global_scale
        best_daytime_loss = np.inf
        for scale in np.arange(0.01, 5.01, 0.05):
            net = supply - demand * scale
            residual = dg - net
            r_day = residual[daytime_mask]
            valid = np.isfinite(r_day)
            if valid.sum() < 50:
                continue
            loss = float(np.mean(r_day[valid] ** 2))
            if loss < best_daytime_loss:
                best_daytime_loss = loss
                best_daytime_scale = scale

        result = {
            'patient': name,
            'global_scale': round(global_scale, 2),
            'overnight_scale': round(best_overnight_scale, 2),
            'daytime_scale': round(best_daytime_scale, 2),
            'overnight_vs_day': round(best_overnight_scale - best_daytime_scale, 2),
            'overnight_steps': int(overnight_mask.sum()),
        }
        results.append(result)
        print(f"  {name}: global={global_scale:.2f} overnight={best_overnight_scale:.2f}"
              f" daytime={best_daytime_scale:.2f} diff={best_overnight_scale - best_daytime_scale:+.2f}")

    diffs = [r['overnight_vs_day'] for r in results]
    circadian = sum(1 for d in diffs if abs(d) > 0.3)
    print(f"\n  Population overnight calibration:")
    print(f"    Mean overnight-daytime diff: {np.mean(diffs):+.2f}")
    print(f"    Circadian effect (diff>0.3): {circadian}/{len(results)}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        axes[0].bar(x - 0.2, [r['global_scale'] for r in results], 0.2, label='Global', alpha=0.7)
        axes[0].bar(x, [r['overnight_scale'] for r in results], 0.2, label='Overnight', alpha=0.7, color='navy')
        axes[0].bar(x + 0.2, [r['daytime_scale'] for r in results], 0.2, label='Daytime', alpha=0.7, color='gold')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Optimal Demand Scale')
        axes[0].set_title('Demand Scale: Overnight vs Daytime')
        axes[0].legend()

        axes[1].bar(x, diffs, color=['purple' if abs(d) > 0.3 else 'gray' for d in diffs], alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Overnight - Daytime Scale')
        axes[1].set_title('Circadian Demand Scale Difference')
        axes[1].axhline(0, color='black', linewidth=0.5)

        plt.suptitle('EXP-1915: Overnight-Only Demand Calibration', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig05-overnight-calibration.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"CIRCADIAN_{'SIGNIFICANT' if circadian > len(results) / 2 else 'MINOR'}_{circadian}/{len(results)}"
    print(f"\n  ✓ EXP-1915 verdict: {verdict}")
    return {
        'experiment': 'EXP-1915', 'title': 'Overnight-Only Demand Calibration',
        'verdict': verdict,
        'mean_diff': round(float(np.mean(diffs)), 2),
        'circadian_count': circadian,
        'per_patient': results,
    }


# ======================================================================
# EXP-1916: Supply Component Analysis
# ======================================================================

def exp_1916(patients, figures_dir):
    """Analyze the supply side: is hepatic glucose production correctly calibrated?
    Compare supply magnitude to known physiological ranges."""
    print("\n" + "=" * 70)
    print("EXP-1916: Supply Component Analysis")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)

        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        hepatic = sd.get('hepatic', np.zeros_like(glucose))
        carb_supply = sd.get('carb_supply', np.zeros_like(glucose))
        net = sd.get('net', np.zeros_like(glucose))

        valid_s = supply[np.isfinite(supply)]
        valid_d = demand[np.isfinite(demand)]
        valid_h = hepatic[np.isfinite(hepatic)]
        valid_c = carb_supply[np.isfinite(carb_supply)]

        # Supply/demand ratio
        total_supply = np.nansum(supply)
        total_demand = np.nansum(demand)
        sd_ratio = total_supply / total_demand if total_demand > 0 else np.inf

        # Hepatic fraction of supply
        hepatic_frac = np.nansum(hepatic) / total_supply if total_supply > 0 else 0

        # Supply/demand balance at different glucose levels
        high_mask = glucose > 180
        low_mask = glucose < 70
        normal_mask = (glucose >= 70) & (glucose <= 180)

        supply_high = float(np.nanmean(supply[high_mask])) if high_mask.sum() > 10 else np.nan
        supply_low = float(np.nanmean(supply[low_mask])) if low_mask.sum() > 10 else np.nan
        supply_normal = float(np.nanmean(supply[normal_mask])) if normal_mask.sum() > 10 else np.nan
        demand_high = float(np.nanmean(demand[high_mask])) if high_mask.sum() > 10 else np.nan
        demand_low = float(np.nanmean(demand[low_mask])) if low_mask.sum() > 10 else np.nan
        demand_normal = float(np.nanmean(demand[normal_mask])) if normal_mask.sum() > 10 else np.nan

        result = {
            'patient': name,
            'supply_mean': round(float(np.nanmean(valid_s)), 2),
            'demand_mean': round(float(np.nanmean(valid_d)), 2),
            'hepatic_mean': round(float(np.nanmean(valid_h)), 3),
            'carb_supply_mean': round(float(np.nanmean(valid_c)), 2),
            'sd_ratio': round(float(sd_ratio), 3),
            'hepatic_frac': round(float(hepatic_frac), 3),
            'supply_high': round(supply_high, 2) if np.isfinite(supply_high) else None,
            'supply_low': round(supply_low, 2) if np.isfinite(supply_low) else None,
            'demand_high': round(demand_high, 2) if np.isfinite(demand_high) else None,
            'demand_low': round(demand_low, 2) if np.isfinite(demand_low) else None,
        }
        results.append(result)
        print(f"  {name}: supply={np.nanmean(valid_s):.2f} demand={np.nanmean(valid_d):.2f}"
              f" hepatic={np.nanmean(valid_h):.3f} S/D={sd_ratio:.3f} hep_frac={hepatic_frac:.1%}")

    # Population
    sd_ratios = [r['sd_ratio'] for r in results if np.isfinite(r['sd_ratio'])]
    print(f"\n  Population supply analysis:")
    print(f"    Mean S/D ratio: {np.mean(sd_ratios):.3f}")
    print(f"    If S/D < 1: demand dominates → scale needs to be < 1")
    print(f"    If S/D > 1: supply dominates → scale needs to be > 1")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # Supply vs Demand
        axes[0].bar(x - 0.15, [r['supply_mean'] for r in results], 0.3, label='Supply', alpha=0.7, color='green')
        axes[0].bar(x + 0.15, [r['demand_mean'] for r in results], 0.3, label='Demand', alpha=0.7, color='red')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Mean Magnitude')
        axes[0].set_title('Supply vs Demand Components')
        axes[0].legend()

        # S/D ratio
        ratios = [r['sd_ratio'] for r in results]
        axes[1].bar(x, ratios, color=['green' if r > 1 else 'red' for r in ratios], alpha=0.7)
        axes[1].axhline(1.0, color='black', linestyle='--', label='Balance')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Supply / Demand Ratio')
        axes[1].set_title('Supply-Demand Balance')
        axes[1].legend()

        # Hepatic vs carb supply
        axes[2].bar(x - 0.15, [r['hepatic_mean'] for r in results], 0.3, label='Hepatic', alpha=0.7)
        axes[2].bar(x + 0.15, [r['carb_supply_mean'] for r in results], 0.3, label='Carb', alpha=0.7)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(names)
        axes[2].set_ylabel('Mean Magnitude')
        axes[2].set_title('Supply Decomposition: Hepatic vs Carbs')
        axes[2].legend()

        plt.suptitle('EXP-1916: Supply Component Analysis', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig06-supply-analysis.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    supply_dominant = sum(1 for r in sd_ratios if r > 1)
    verdict = f"SUPPLY_DOMINANT_{supply_dominant}_OF_{len(sd_ratios)}_RATIO={np.mean(sd_ratios):.2f}"
    print(f"\n  ✓ EXP-1916 verdict: {verdict}")
    return {
        'experiment': 'EXP-1916', 'title': 'Supply Component Analysis',
        'verdict': verdict,
        'mean_sd_ratio': round(float(np.mean(sd_ratios)), 3),
        'per_patient': results,
    }


# ======================================================================
# EXP-1917: Patient-Adaptive Demand Model
# ======================================================================

def exp_1917(patients, figures_dir):
    """Build a patient-adaptive demand model that uses patient characteristics
    to predict the optimal demand scale WITHOUT running optimization."""
    print("\n" + "=" * 70)
    print("EXP-1917: Patient-Adaptive Demand Model")
    print("=" * 70)

    # Gather training data
    all_data = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        scale, loss = optimal_demand_scale(sd, glucose)
        chars = patient_characteristics(p)

        sd_ratio = np.nansum(sd.get('supply', np.zeros(1))) / max(np.nansum(sd.get('demand', np.zeros(1))), 1)

        all_data.append({
            'patient': name,
            'optimal_scale': scale,
            'sd_ratio': sd_ratio,
            **chars,
        })

    # Simple predictive model: try SD ratio as predictor
    scales = np.array([d['optimal_scale'] for d in all_data])
    sd_ratios = np.array([d['sd_ratio'] for d in all_data])

    # Linear regression: scale = a * sd_ratio + b
    valid = np.isfinite(sd_ratios) & np.isfinite(scales)
    if valid.sum() >= 5:
        A = np.vstack([sd_ratios[valid], np.ones(valid.sum())]).T
        try:
            coeffs = np.linalg.lstsq(A, scales[valid], rcond=None)[0]
            predicted = sd_ratios * coeffs[0] + coeffs[1]
            residuals = scales - predicted
            r2 = 1 - np.sum(residuals[valid] ** 2) / np.sum((scales[valid] - np.mean(scales[valid])) ** 2)
        except:
            coeffs = [0, np.mean(scales)]
            predicted = np.full_like(scales, np.mean(scales))
            r2 = 0
    else:
        coeffs = [0, np.mean(scales)]
        predicted = np.full_like(scales, np.mean(scales))
        r2 = 0

    # LOO cross-validation
    loo_errors = []
    for i in range(len(all_data)):
        train_scales = np.delete(scales, i)
        train_ratios = np.delete(sd_ratios, i)
        v = np.isfinite(train_ratios) & np.isfinite(train_scales)
        if v.sum() >= 3:
            A_t = np.vstack([train_ratios[v], np.ones(v.sum())]).T
            try:
                c_t = np.linalg.lstsq(A_t, train_scales[v], rcond=None)[0]
                pred_i = sd_ratios[i] * c_t[0] + c_t[1]
                loo_errors.append(abs(pred_i - scales[i]))
            except:
                pass

    loo_mae = float(np.mean(loo_errors)) if loo_errors else np.nan

    for d in all_data:
        pred = d['sd_ratio'] * coeffs[0] + coeffs[1]
        d['predicted_scale'] = round(float(pred), 2)
        d['prediction_error'] = round(float(abs(pred - d['optimal_scale'])), 2)
        print(f"  {d['patient']}: actual={d['optimal_scale']:.2f} predicted={pred:.2f}"
              f" error={abs(pred - d['optimal_scale']):.2f} sd_ratio={d['sd_ratio']:.3f}")

    print(f"\n  Linear model: scale = {coeffs[0]:.3f} × SD_ratio + {coeffs[1]:.3f}")
    print(f"  R² = {r2:.3f}")
    print(f"  LOO MAE = {loo_mae:.3f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Actual vs predicted
        axes[0].scatter(scales, [d['predicted_scale'] for d in all_data], c='steelblue', s=80)
        for d in all_data:
            axes[0].annotate(d['patient'], (d['optimal_scale'], d['predicted_scale']), fontsize=8)
        min_v = min(min(scales), min(d['predicted_scale'] for d in all_data))
        max_v = max(max(scales), max(d['predicted_scale'] for d in all_data))
        axes[0].plot([min_v, max_v], [min_v, max_v], 'r--', label='Perfect')
        axes[0].set_xlabel('Actual Optimal Scale')
        axes[0].set_ylabel('Predicted Scale')
        axes[0].set_title(f'Actual vs Predicted (R²={r2:.3f})')
        axes[0].legend()

        # SD ratio vs scale
        axes[1].scatter(sd_ratios, scales, c='steelblue', s=80)
        for d in all_data:
            axes[1].annotate(d['patient'], (d['sd_ratio'], d['optimal_scale']), fontsize=8)
        x_line = np.linspace(min(sd_ratios), max(sd_ratios), 100)
        axes[1].plot(x_line, x_line * coeffs[0] + coeffs[1], 'r-', label=f'Linear fit')
        axes[1].set_xlabel('Supply/Demand Ratio')
        axes[1].set_ylabel('Optimal Demand Scale')
        axes[1].set_title('SD Ratio as Demand Scale Predictor')
        axes[1].legend()

        plt.suptitle('EXP-1917: Patient-Adaptive Demand Model', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig07-adaptive-model.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"R2={r2:.3f}_LOO_MAE={loo_mae:.3f}"
    print(f"\n  ✓ EXP-1917 verdict: {verdict}")
    return {
        'experiment': 'EXP-1917', 'title': 'Patient-Adaptive Demand Model',
        'verdict': verdict,
        'r2': round(float(r2), 3),
        'loo_mae': round(float(loo_mae), 3),
        'coefficients': [round(float(c), 4) for c in coeffs],
        'per_patient': all_data,
    }


# ======================================================================
# EXP-1918: Validated Improved Model
# ======================================================================

def exp_1918(patients, figures_dir):
    """Final validation: compare original model, patient-optimized, and
    adaptive-predicted demand scales using temporal cross-validation."""
    print("\n" + "=" * 70)
    print("EXP-1918: Validated Improved Model")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        n = len(glucose)
        mid = n // 2

        # Half splits
        df_h1 = df.iloc[:mid].copy()
        df_h2 = df.iloc[mid:].copy()
        g_h1 = glucose[:mid]
        g_h2 = glucose[mid:]

        # Half 1: compute supply-demand
        sd_h1 = compute_supply_demand(df_h1)
        sd_h2 = compute_supply_demand(df_h2)

        # Approach 1: Profile (scale=1.0)
        loss_profile = _compute_loss(sd_h2, g_h2, 1.0)

        # Approach 2: Optimized on H1
        h1_scale, _ = optimal_demand_scale(sd_h1, g_h1)
        loss_optimized = _compute_loss(sd_h2, g_h2, h1_scale)

        # Approach 3: Population mean scale from H1
        # (would need all patients' H1 — use simple heuristic)
        pop_scale = 1.5  # approximate population mean from EXP-1893
        loss_population = _compute_loss(sd_h2, g_h2, pop_scale)

        # Approach 4: SD ratio predictor from H1
        sd_ratio_h1 = np.nansum(sd_h1.get('supply', np.zeros(mid))) / max(np.nansum(sd_h1.get('demand', np.zeros(mid))), 1)
        # Simple heuristic: if S/D ratio > 1, scale up demand
        adaptive_scale = max(0.1, min(5.0, sd_ratio_h1))
        loss_adaptive = _compute_loss(sd_h2, g_h2, adaptive_scale)

        # Rankings
        losses = {
            'profile': loss_profile,
            'optimized': loss_optimized,
            'population': loss_population,
            'adaptive': loss_adaptive,
        }
        best = min(losses, key=lambda k: losses[k] if np.isfinite(losses[k]) else np.inf)

        result = {
            'patient': name,
            'h1_scale': round(h1_scale, 2),
            'adaptive_scale': round(adaptive_scale, 2),
            'loss_profile': round(float(loss_profile), 2) if np.isfinite(loss_profile) else None,
            'loss_optimized': round(float(loss_optimized), 2) if np.isfinite(loss_optimized) else None,
            'loss_population': round(float(loss_population), 2) if np.isfinite(loss_population) else None,
            'loss_adaptive': round(float(loss_adaptive), 2) if np.isfinite(loss_adaptive) else None,
            'best_approach': best,
        }
        results.append(result)
        print(f"  {name}: profile={loss_profile:.0f} opt={loss_optimized:.0f}"
              f" pop={loss_population:.0f} adapt={loss_adaptive:.0f} → best={best}")

    # Count wins
    wins = {}
    for r in results:
        b = r['best_approach']
        wins[b] = wins.get(b, 0) + 1

    print(f"\n  Approach wins:")
    for approach, count in sorted(wins.items(), key=lambda x: x[1], reverse=True):
        print(f"    {approach}: {count}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))
        w = 0.2

        axes[0].bar(x - 1.5*w, [r['loss_profile'] or 0 for r in results], w, label='Profile', alpha=0.7)
        axes[0].bar(x - 0.5*w, [r['loss_optimized'] or 0 for r in results], w, label='Optimized', alpha=0.7)
        axes[0].bar(x + 0.5*w, [r['loss_population'] or 0 for r in results], w, label='Population', alpha=0.7)
        axes[0].bar(x + 1.5*w, [r['loss_adaptive'] or 0 for r in results], w, label='Adaptive', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Half-2 Loss')
        axes[0].set_title('Model Comparison (Temporal Validation)')
        axes[0].legend(fontsize=8)

        # Improvement over profile
        for approach, color in [('optimized', 'green'), ('adaptive', 'orange')]:
            imps = []
            for r in results:
                lp = r['loss_profile'] or 1
                la = r[f'loss_{approach}'] or lp
                imps.append((lp - la) / lp * 100 if lp > 0 else 0)
            axes[1].bar(x + (0 if approach == 'optimized' else 0.3) - 0.15, imps,
                       0.3, label=f'{approach} vs profile', alpha=0.7, color=color)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Improvement over Profile (%)')
        axes[1].set_title('Improvement by Approach')
        axes[1].axhline(0, color='black', linewidth=0.5)
        axes[1].legend()

        plt.suptitle('EXP-1918: Validated Model Comparison', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'demand-fig08-validated-model.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    best_approach = max(wins, key=wins.get)
    verdict = f"BEST:{best_approach}({wins[best_approach]}/{len(results)})"
    print(f"\n  ✓ EXP-1918 verdict: {verdict}")
    return {
        'experiment': 'EXP-1918', 'title': 'Validated Improved Model',
        'verdict': verdict,
        'wins': wins,
        'per_patient': results,
    }


def _compute_loss(sd, glucose, scale):
    """Helper to compute loss with a given demand scale."""
    supply = sd.get('supply', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])
    net = supply - demand * scale
    residual = dg - net
    valid = np.isfinite(residual)
    if valid.sum() < 10:
        return np.nan
    return float(np.mean(residual[valid] ** 2))


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1911–1918: Demand Calibration')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--experiment', type=int, help='Run single experiment (1911–1918)')
    args = parser.parse_args()

    figures_dir = FIGURES_DIR if args.figures else None
    if figures_dir:
        figures_dir.mkdir(parents=True, exist_ok=True)

    patients = load_patients('externals/ns-data/patients/')
    print(f"Loaded {len(patients)} patients")

    experiments = {
        1911: exp_1911,
        1912: exp_1912,
        1913: exp_1913,
        1914: exp_1914,
        1915: exp_1915,
        1916: exp_1916,
        1917: exp_1917,
        1918: exp_1918,
    }

    if args.experiment:
        to_run = {args.experiment: experiments[args.experiment]}
    else:
        to_run = experiments

    all_results = {}
    print(f"\n{'=' * 70}")
    print(f"EXP-1911–1918: Demand Calibration & Model Improvement")
    print(f"{'=' * 70}")

    for exp_id, exp_fn in sorted(to_run.items()):
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{exp_id}: {exp_fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'#' * 70}")
        result = exp_fn(patients, figures_dir)
        all_results[f'EXP-{exp_id}'] = result

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {RESULTS_PATH}")

    print(f"\n{'=' * 70}")
    print(f"SYNTHESIS: Demand Calibration & Model Improvement")
    print(f"{'=' * 70}")
    for k in sorted(all_results.keys()):
        v = all_results[k]
        print(f"  {k}: {v.get('verdict', '?')}")
    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
