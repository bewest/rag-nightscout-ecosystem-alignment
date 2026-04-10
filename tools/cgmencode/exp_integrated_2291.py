#!/usr/bin/env python3
"""
EXP-2291 through EXP-2298: Integrated Therapy Optimization

Synthesizes all prior findings into per-patient actionable therapy
recommendations with projected outcomes and safety guardrails.

Experiments:
  2291: Per-patient settings recommendation (ISF, CR, basal, target)
  2292: Circadian-aware 2-zone profile design
  2293: Hypo-safe corridor definition
  2294: Projected outcomes under optimized settings
  2295: Monitoring cadence recommendation
  2296: Algorithm-specific mapping (Loop/AAPS/Trio parameters)
  2297: Safety guardrails and limits
  2298: Population-level summary dashboard

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_integrated_2291.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_integrated_2291.py --figures --tiny  # fast dev mode
"""

import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    """Load patients from parquet — 40× faster than JSON."""
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        # Extract profile settings from grid columns
        profile = {
            'isf': float(pdf['scheduled_isf'].median()),
            'cr': float(pdf['scheduled_cr'].median()),
            'basal': float(pdf['scheduled_basal_rate'].median()),
            'target': float(110 - pdf['glucose_vs_target'].median() + pdf['glucose'].median())
                      if pdf['glucose'].notna().any() and pdf['glucose_vs_target'].notna().any()
                      else 110,
        }
        patients.append({'name': pid, 'df': pdf, 'profile': profile})
        print(f"  Loaded {pid}: {len(pdf)} steps (ISF={profile['isf']:.1f}, CR={profile['cr']:.1f}, basal={profile['basal']:.2f})")
    return patients


def hour_of_day(df):
    idx = pd.to_datetime(df.index) if not isinstance(df.index, pd.DatetimeIndex) else df.index
    return idx.hour

def compute_tir(bg, low=70, high=180):
    v = bg[~np.isnan(bg)]
    return float(np.mean((v >= low) & (v <= high)) * 100) if len(v) else np.nan

def compute_tbr(bg, thresh=70):
    v = bg[~np.isnan(bg)]
    return float(np.mean(v < thresh) * 100) if len(v) else np.nan

def compute_tar(bg, thresh=180):
    v = bg[~np.isnan(bg)]
    return float(np.mean(v > thresh) * 100) if len(v) else np.nan

def compute_mean_bg(bg):
    v = bg[~np.isnan(bg)]
    return float(np.mean(v)) if len(v) else np.nan

def compute_gmi(bg):
    """Glucose Management Indicator (estimated A1C)."""
    mean = compute_mean_bg(bg)
    if np.isnan(mean): return np.nan
    return float(3.31 + 0.02392 * mean)

def compute_cv(bg):
    v = bg[~np.isnan(bg)]
    if len(v) == 0 or np.mean(v) == 0: return np.nan
    return float(np.std(v) / np.mean(v) * 100)

# ── Load prior results ───────────────────────────────────────────────────

def load_prior_results():
    """Load results from prior experiment batches."""
    prior = {}
    paths = {
        'variability': 'externals/experiments/exp-2261-2268_variability.json',
        'circadian': 'externals/experiments/exp-2271-2278_circadian.json',
        'hypo': 'externals/experiments/exp-2281-2288_hypo_safety.json',
    }
    for key, path in paths.items():
        if os.path.exists(path):
            with open(path) as f:
                prior[key] = json.load(f)
            print(f"  Loaded {key}: {path}")
        else:
            print(f"  Missing {key}: {path}")
    return prior


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2291_settings(patients, prior):
    """Per-patient settings recommendation combining all findings."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        profile = pat['profile']
        bg = df['glucose'].values

        # Current settings from profile
        current_isf = profile['isf']
        current_cr = profile['cr']
        current_basal = profile['basal']
        current_target = profile['target']

        # Current metrics
        current_tir = compute_tir(bg)
        current_tbr = compute_tbr(bg)
        current_tar = compute_tar(bg)
        current_mean = compute_mean_bg(bg)
        current_gmi = compute_gmi(bg)
        current_cv_val = compute_cv(bg)

        # Determine hypo phenotype from prior results
        hypo_data = prior.get('hypo', {}).get('exp_2283', {}).get(name, {})
        median_start = hypo_data.get('median_start_bg', 130)
        is_overcorrection = median_start > 120
        is_chronic_low = median_start < 100

        # Determine variability source
        var_data = prior.get('variability', {}).get('exp_2268', {}).get(name, {})
        primary_var = var_data.get('primary_source', 'circadian')

        # Settings recommendations
        # ISF: +19% base correction (EXP-1941), further adjusted by phenotype
        isf_correction = 1.19  # base
        if is_overcorrection:
            isf_correction *= 1.05  # extra 5% for over-correctors
        recommended_isf = current_isf * isf_correction

        # CR: -28% base correction, adjusted
        cr_correction = 0.72
        if is_overcorrection:
            cr_correction *= 0.95  # less aggressive CR for over-correctors
        recommended_cr = current_cr * cr_correction

        # Basal: depends on phenotype
        if is_chronic_low:
            basal_correction = 0.90  # 10% reduction for chronic-low
        elif current_tbr > 4:
            basal_correction = 0.95  # 5% reduction if TBR > 4%
        else:
            basal_correction = 1.08  # +8% from EXP-1941
        recommended_basal = current_basal * basal_correction

        # Target: raise for chronic-low patients
        if is_chronic_low:
            recommended_target = max(current_target, 120)
        elif current_tbr > 4:
            recommended_target = max(current_target, 110)
        else:
            recommended_target = current_target

        results[name] = {
            'current': {
                'isf': float(current_isf), 'cr': float(current_cr),
                'basal': float(current_basal), 'target': float(current_target),
            },
            'recommended': {
                'isf': round(float(recommended_isf), 1),
                'cr': round(float(recommended_cr), 1),
                'basal': round(float(recommended_basal), 2),
                'target': int(recommended_target),
            },
            'corrections': {
                'isf_pct': round((isf_correction - 1) * 100, 1),
                'cr_pct': round((cr_correction - 1) * 100, 1),
                'basal_pct': round((basal_correction - 1) * 100, 1),
                'target_change': int(recommended_target - current_target),
            },
            'phenotype': 'over-correction' if is_overcorrection else ('chronic-low' if is_chronic_low else 'mixed'),
            'primary_variability': primary_var,
            'current_metrics': {
                'tir': round(current_tir, 1), 'tbr': round(current_tbr, 1),
                'tar': round(current_tar, 1), 'mean_bg': round(current_mean, 1),
                'gmi': round(current_gmi, 1), 'cv': round(current_cv_val, 1),
            }
        }
        print(f"  {name}: {results[name]['phenotype']} | ISF {current_isf:.0f}→{recommended_isf:.0f} (+{(isf_correction-1)*100:.0f}%), CR {current_cr:.0f}→{recommended_cr:.0f}, basal {current_basal:.2f}→{recommended_basal:.2f}")
    return results


def exp_2292_profiles(patients, prior):
    """Circadian-aware 2-zone profile design."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values
        hours = hour_of_day(df)

        # Compute day and night mean glucose
        day_mask = (hours >= 7) & (hours < 22) & ~np.isnan(bg)
        night_mask = ((hours < 7) | (hours >= 22)) & ~np.isnan(bg)

        day_mean = float(np.mean(bg[day_mask])) if day_mask.sum() > 0 else np.nan
        night_mean = float(np.mean(bg[night_mask])) if night_mask.sum() > 0 else np.nan
        day_tir = compute_tir(bg[day_mask])
        night_tir = compute_tir(bg[night_mask])
        day_tbr = compute_tbr(bg[day_mask])
        night_tbr = compute_tbr(bg[night_mask])

        # Dawn data from prior experiments
        dawn_data = prior.get('circadian', {}).get('exp_2274', {}).get(name, {})
        dawn_rise = dawn_data.get('dawn_rise', 0)

        # Stability from prior
        stability_data = prior.get('circadian', {}).get('exp_2275', {}).get(name, {})
        stability = stability_data.get('stability_score', 0.5)

        # Zone boundaries
        day_start = 7
        day_end = 22

        # Day zone adjustments
        day_offset = day_mean - 120
        night_offset = night_mean - 120

        # Basal adjustment per zone
        isf = pat['profile']['isf']

        day_basal_adj = day_offset / isf * 0.5  # 50% correction
        night_basal_adj = night_offset / isf * 0.5

        # Dawn preemption: if dawn > 15 mg/dL, increase 5-8am basal
        dawn_preempt = dawn_rise / isf * 0.3 if dawn_rise > 15 else 0

        results[name] = {
            'day_zone': {'start': day_start, 'end': day_end},
            'night_zone': {'start': day_end, 'end': day_start},
            'day_mean_bg': round(day_mean, 1),
            'night_mean_bg': round(night_mean, 1),
            'day_tir': round(day_tir, 1),
            'night_tir': round(night_tir, 1),
            'day_tbr': round(day_tbr, 1),
            'night_tbr': round(night_tbr, 1),
            'day_basal_adj': round(float(day_basal_adj), 3),
            'night_basal_adj': round(float(night_basal_adj), 3),
            'dawn_preempt': round(float(dawn_preempt), 3),
            'dawn_rise': round(float(dawn_rise), 1) if dawn_rise else 0,
            'profile_stability': round(float(stability), 3),
            'profile_recommended': stability > 0.5,
        }
        print(f"  {name}: day={day_mean:.0f} night={night_mean:.0f} mg/dL, dawn={dawn_rise:.0f}, stable={'Y' if stability > 0.5 else 'N'}")
    return results


def exp_2293_corridor(patients, prior):
    """Hypo-safe corridor definition per patient."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values
        hours = hour_of_day(df)

        # Compute percentile corridors
        hourly_percentiles = {}
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            vals = bg[mask]
            if len(vals) >= 50:
                hourly_percentiles[str(h)] = {
                    'p10': float(np.percentile(vals, 10)),
                    'p25': float(np.percentile(vals, 25)),
                    'p50': float(np.percentile(vals, 50)),
                    'p75': float(np.percentile(vals, 75)),
                    'p90': float(np.percentile(vals, 90)),
                }

        # Define safe corridor: p10 should be >70, p90 should be <180
        hypo_risk_hours = []
        hyper_risk_hours = []
        for h_str, p in hourly_percentiles.items():
            if p['p10'] < 70:
                hypo_risk_hours.append(int(h_str))
            if p['p90'] > 250:
                hyper_risk_hours.append(int(h_str))

        # "Safe target" for each hour: the glucose where p10 stays >70
        safe_targets = {}
        for h_str, p in hourly_percentiles.items():
            # If p10 is X and we want p10 ≥ 70, we need to shift up by (70 - X)
            margin = 70 - p['p10']
            if margin > 0:
                safe_targets[h_str] = round(p['p50'] + margin, 0)
            else:
                safe_targets[h_str] = round(p['p50'], 0)

        results[name] = {
            'hourly_percentiles': hourly_percentiles,
            'hypo_risk_hours': hypo_risk_hours,
            'hyper_risk_hours': hyper_risk_hours,
            'n_hypo_risk_hours': len(hypo_risk_hours),
            'n_hyper_risk_hours': len(hyper_risk_hours),
            'safe_targets': safe_targets,
        }
        print(f"  {name}: {len(hypo_risk_hours)} hypo-risk hours, {len(hyper_risk_hours)} hyper-risk hours")
    return results


def exp_2294_projection(patients, r2291):
    """Project outcomes under optimized settings."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values

        settings = r2291.get(name, {})
        if not settings:
            results[name] = {'skipped': True}
            continue

        current = settings['current_metrics']
        corrections = settings['corrections']

        # Project new glucose trace (simplified linear model)
        # Correction effects:
        # ISF ↑ → fewer aggressive corrections → less post-correction hypo, slightly higher mean
        # CR ↓ → smaller meal boluses → higher post-meal peaks but fewer hypos
        # Basal change → shifts mean glucose
        isf_effect = corrections['isf_pct'] / 100 * 5  # mg/dL shift
        cr_effect = corrections['cr_pct'] / 100 * 3    # mg/dL shift  
        basal_effect = corrections['basal_pct'] / 100 * 10  # mg/dL shift

        total_shift = isf_effect + cr_effect + basal_effect
        # Apply shift
        projected_bg = bg + total_shift

        # Compute projected metrics
        proj_tir = compute_tir(projected_bg)
        proj_tbr = compute_tbr(projected_bg)
        proj_tar = compute_tar(projected_bg)
        proj_mean = compute_mean_bg(projected_bg)
        proj_gmi = compute_gmi(projected_bg)
        proj_cv = compute_cv(projected_bg)

        # Hypo event count (approximate)
        valid = projected_bg[~np.isnan(projected_bg)]
        proj_hypo_pct = float(np.mean(valid < 70) * 100)
        current_hypo_pct = current['tbr']
        hypo_reduction = current_hypo_pct - proj_hypo_pct

        results[name] = {
            'glucose_shift': round(total_shift, 1),
            'projected': {
                'tir': round(proj_tir, 1), 'tbr': round(proj_tbr, 1),
                'tar': round(proj_tar, 1), 'mean_bg': round(proj_mean, 1),
                'gmi': round(proj_gmi, 1), 'cv': round(proj_cv, 1),
            },
            'current': current,
            'changes': {
                'tir': round(proj_tir - current['tir'], 1),
                'tbr': round(proj_tbr - current['tbr'], 1),
                'tar': round(proj_tar - current['tar'], 1),
                'mean_bg': round(proj_mean - current['mean_bg'], 1),
                'hypo_reduction_pct': round(hypo_reduction, 1),
            },
            'meets_targets': {
                'tir_70': proj_tir >= 70,
                'tbr_4': proj_tbr <= 4,
                'tar_25': proj_tar <= 25,
                'cv_36': proj_cv <= 36,
            }
        }
        print(f"  {name}: TIR {current['tir']:.1f}→{proj_tir:.1f} ({proj_tir-current['tir']:+.1f}), TBR {current['tbr']:.1f}→{proj_tbr:.1f}, shift={total_shift:+.1f}")
    return results


def exp_2295_cadence(patients, prior):
    """Monitoring cadence recommendation."""
    results = {}
    for pat in patients:
        name = pat['name']

        # Profile stability from EXP-2275
        stability = prior.get('circadian', {}).get('exp_2275', {}).get(name, {})
        stability_score = stability.get('stability_score', 0.5)
        drift_rmse = stability.get('mean_drift_rmse', 20)

        # Convergence from cross-validation (if available)
        # Use stability as proxy for convergence speed
        
        # Variability attribution
        var = prior.get('variability', {}).get('exp_2268', {}).get(name, {})
        primary = var.get('primary_source', 'circadian')

        # Recommendation logic
        if stability_score > 0.7:
            recalibration_days = 90
            confidence = 'high'
        elif stability_score > 0.5:
            recalibration_days = 60
            confidence = 'moderate'
        else:
            recalibration_days = 30
            confidence = 'low'

        # Override for sensitivity-dominant patients
        if primary == 'sensitivity':
            recalibration_days = min(recalibration_days, 30)
            confidence = 'low'

        # Minimum data for reliable estimation
        # From EXP-2254: need 30-60 days for stable estimates
        min_data_days = 30 if stability_score > 0.5 else 60

        results[name] = {
            'recalibration_days': recalibration_days,
            'confidence': confidence,
            'stability_score': round(stability_score, 3),
            'drift_rmse': round(drift_rmse, 1) if drift_rmse else None,
            'primary_variability': primary,
            'min_data_days': min_data_days,
            'monitoring_frequency': 'weekly' if recalibration_days <= 30 else ('biweekly' if recalibration_days <= 60 else 'monthly'),
        }
        print(f"  {name}: recalibrate every {recalibration_days}d, confidence={confidence}, monitor {results[name]['monitoring_frequency']}")
    return results


def exp_2296_algorithm_mapping(patients, r2291, prior):
    """Map recommendations to Loop/AAPS/Trio algorithm parameters."""
    results = {}
    for pat in patients:
        name = pat['name']
        settings = r2291.get(name, {})
        if not settings:
            results[name] = {'skipped': True}
            continue

        rec = settings['recommended']

        # Loop parameters
        loop_params = {
            'correction_range_min': rec['target'] - 10,
            'correction_range_max': rec['target'] + 10,
            'suspend_threshold': max(55, rec['target'] - 55),
            'basal_rate': rec['basal'],
            'isf': rec['isf'],
            'cr': rec['cr'],
            'max_basal': round(rec['basal'] * 4, 2),
            'max_bolus': round(rec['cr'] * 2, 1),  # ~2× meal bolus
        }

        # AAPS/oref1 parameters
        aaps_params = {
            'profile_isf': rec['isf'],
            'profile_ic': rec['cr'],
            'profile_basal': rec['basal'],
            'min_bg': rec['target'] - 10,
            'max_bg': rec['target'] + 10,
            'max_iob': round(rec['basal'] * 6, 1),  # 6× hourly basal
            'max_smb': round(rec['basal'] * 2, 1),
            'enable_smb': True,
            'enable_uam': True,
            'autosens_max': 1.2,
            'autosens_min': 0.8,
        }

        # Trio parameters (similar to AAPS but Swift-based)
        trio_params = {
            'isf': rec['isf'],
            'cr': rec['cr'],
            'basal': rec['basal'],
            'target_glucose': rec['target'],
            'max_iob': round(rec['basal'] * 6, 1),
            'max_smb': round(rec['basal'] * 2, 1),
            'enable_smb': True,
            'enable_dynamic_isf': True,
            'adjustment_factor': 0.8,  # conservative start
        }

        results[name] = {
            'loop': loop_params,
            'aaps': aaps_params,
            'trio': trio_params,
            'notes': []
        }

        # Add phenotype-specific notes
        phenotype = settings.get('phenotype', '')
        if phenotype == 'over-correction':
            results[name]['notes'].append('Consider reducing max_bolus to prevent over-correction hypos')
        elif phenotype == 'chronic-low':
            results[name]['notes'].append('Consider raising suspend_threshold to prevent chronic low glucose')
            results[name]['notes'].append('Consider reducing max_basal_rate')

        print(f"  {name}: Loop/AAPS/Trio params generated")
    return results


def exp_2297_guardrails(patients, r2291, r2294):
    """Safety guardrails and limits."""
    results = {}
    for pat in patients:
        name = pat['name']
        settings = r2291.get(name, {})
        projection = r2294.get(name, {})

        if not settings or not projection or projection.get('skipped'):
            results[name] = {'skipped': True}
            continue

        rec = settings['recommended']
        curr = settings['current']
        proj = projection.get('projected', {})

        # Guardrail checks
        guardrails = []
        passed = 0
        total = 0

        # 1. ISF change limit: max 50% change
        total += 1
        isf_change = abs(rec['isf'] - curr['isf']) / curr['isf']
        if isf_change <= 0.5:
            passed += 1
        else:
            guardrails.append(f"ISF change {isf_change*100:.0f}% exceeds 50% limit")

        # 2. CR change limit: max 50% change
        total += 1
        cr_change = abs(rec['cr'] - curr['cr']) / curr['cr']
        if cr_change <= 0.5:
            passed += 1
        else:
            guardrails.append(f"CR change {cr_change*100:.0f}% exceeds 50% limit")

        # 3. Basal change limit: max 30% change
        total += 1
        basal_change = abs(rec['basal'] - curr['basal']) / curr['basal'] if curr['basal'] > 0 else 0
        if basal_change <= 0.3:
            passed += 1
        else:
            guardrails.append(f"Basal change {basal_change*100:.0f}% exceeds 30% limit")

        # 4. Projected TBR must be < 4%
        total += 1
        if proj.get('tbr', 10) <= 4:
            passed += 1
        else:
            guardrails.append(f"Projected TBR {proj['tbr']:.1f}% exceeds 4% limit")

        # 5. Projected TIR must improve or stay stable
        total += 1
        tir_change = projection.get('changes', {}).get('tir', 0)
        if tir_change >= -2:
            passed += 1
        else:
            guardrails.append(f"Projected TIR decrease of {tir_change:.1f}pp")

        # 6. No ISF below absolute minimum (10 for mg/dL users)
        total += 1
        if rec['isf'] >= 10:
            passed += 1
        else:
            guardrails.append(f"ISF {rec['isf']} below minimum 10")

        # 7. No basal below 0.1 U/hr
        total += 1
        if rec['basal'] >= 0.1:
            passed += 1
        else:
            guardrails.append(f"Basal {rec['basal']} below minimum 0.1 U/hr")

        results[name] = {
            'guardrails_passed': passed,
            'guardrails_total': total,
            'all_passed': passed == total,
            'violations': guardrails,
            'safe_to_implement': len(guardrails) == 0,
            'isf_change_pct': round(isf_change * 100, 1),
            'cr_change_pct': round(cr_change * 100, 1),
            'basal_change_pct': round(basal_change * 100, 1),
        }
        status = "✓ SAFE" if not guardrails else f"⚠ {len(guardrails)} violations"
        print(f"  {name}: {passed}/{total} guardrails passed — {status}")
    return results


def exp_2298_dashboard(patients, all_results):
    """Population-level summary dashboard."""
    r2291 = all_results.get('exp_2291', {})
    r2294 = all_results.get('exp_2294', {})
    r2297 = all_results.get('exp_2297', {})

    # Population aggregates
    names = sorted([p['name'] for p in patients])
    
    phenotype_counts = {'over-correction': 0, 'chronic-low': 0, 'mixed': 0}
    tir_improvements = []
    tbr_improvements = []
    safe_count = 0
    meeting_70 = 0

    for name in names:
        s = r2291.get(name, {})
        p = r2294.get(name, {})
        g = r2297.get(name, {})

        if s:
            phenotype = s.get('phenotype', 'mixed')
            phenotype_counts[phenotype] = phenotype_counts.get(phenotype, 0) + 1

        if p and not p.get('skipped'):
            changes = p.get('changes', {})
            tir_improvements.append(changes.get('tir', 0))
            tbr_improvements.append(changes.get('tbr', 0))
            if p.get('projected', {}).get('tir', 0) >= 70:
                meeting_70 += 1

        if g and not g.get('skipped'):
            if g.get('safe_to_implement'):
                safe_count += 1

    results = {
        'n_patients': len(names),
        'phenotype_distribution': phenotype_counts,
        'mean_tir_improvement': round(float(np.mean(tir_improvements)), 1) if tir_improvements else 0,
        'median_tir_improvement': round(float(np.median(tir_improvements)), 1) if tir_improvements else 0,
        'mean_tbr_improvement': round(float(np.mean(tbr_improvements)), 1) if tbr_improvements else 0,
        'patients_meeting_70_tir': meeting_70,
        'patients_safe_to_implement': safe_count,
        'per_patient_summary': {}
    }

    for name in names:
        s = r2291.get(name, {})
        p = r2294.get(name, {})
        g = r2297.get(name, {})
        results['per_patient_summary'][name] = {
            'phenotype': s.get('phenotype', '?'),
            'current_tir': s.get('current_metrics', {}).get('tir', 0),
            'projected_tir': p.get('projected', {}).get('tir', 0) if p and not p.get('skipped') else None,
            'tir_change': p.get('changes', {}).get('tir', 0) if p and not p.get('skipped') else None,
            'safe': g.get('safe_to_implement', False) if g and not g.get('skipped') else None,
        }

    print(f"  Population: {len(names)} patients")
    print(f"  Phenotypes: {phenotype_counts}")
    print(f"  Mean TIR improvement: {results['mean_tir_improvement']:+.1f}pp")
    print(f"  Patients meeting 70% TIR: {meeting_70}/{len(names)}")
    print(f"  Safe to implement: {safe_count}/{len(names)}")

    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)

    # Fig 1: Settings changes
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    r = results['exp_2291']
    names = sorted(r.keys())
    x = np.arange(len(names))

    for idx, (param, label) in enumerate([('isf_pct', 'ISF Change %'), ('cr_pct', 'CR Change %'), ('basal_pct', 'Basal Change %')]):
        ax = axes[idx]
        vals = [r[n]['corrections'][param] for n in names]
        colors = ['green' if v > 0 else 'red' for v in vals]
        ax.bar(x, vals, color=colors, alpha=0.7)
        ax.set_xticks(x); ax.set_xticklabels(names)
        ax.set_ylabel(label); ax.axhline(0, color='black', lw=0.5)
        ax.set_title(label)
    fig.suptitle('EXP-2291: Per-Patient Settings Corrections', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig01-settings.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 1: settings")

    # Fig 2: 2-zone profiles
    fig, ax = plt.subplots(figsize=(12, 6))
    r2292 = results['exp_2292']
    x = np.arange(len(names))
    day_means = [r2292[n]['day_mean_bg'] for n in names]
    night_means = [r2292[n]['night_mean_bg'] for n in names]
    w = 0.35
    ax.bar(x - w/2, day_means, w, label='Day (7-22h)', color='gold', alpha=0.7)
    ax.bar(x + w/2, night_means, w, label='Night (22-7h)', color='midnightblue', alpha=0.7)
    ax.axhspan(70, 180, alpha=0.1, color='green')
    ax.axhline(120, color='orange', ls='--', label='Target 120')
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Mean BG (mg/dL)'); ax.legend()
    ax.set_title('EXP-2292: Day vs Night Mean Glucose')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig02-profiles.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 2: profiles")

    # Fig 3: Safety corridor
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2293 = results['exp_2293']
    for idx, name in enumerate(sorted(r2293.keys())):
        if idx >= 11: break
        ax = axes[idx]
        data = r2293[name]
        hrs = sorted([int(h) for h in data['hourly_percentiles'].keys()])
        p10 = [data['hourly_percentiles'][str(h)]['p10'] for h in hrs]
        p50 = [data['hourly_percentiles'][str(h)]['p50'] for h in hrs]
        p90 = [data['hourly_percentiles'][str(h)]['p90'] for h in hrs]
        ax.fill_between(hrs, p10, p90, alpha=0.2, color='blue')
        ax.plot(hrs, p50, 'b-', lw=2)
        ax.axhspan(70, 180, alpha=0.1, color='green')
        ax.axhline(70, color='red', ls='--', alpha=0.5)
        ax.axhline(180, color='orange', ls='--', alpha=0.5)
        ax.set_title(f"{name}: {data['n_hypo_risk_hours']}h hypo risk")
        ax.set_xlim(-0.5, 23.5)
        ax.set_ylim(30, 350)
    axes[-1].axis('off')
    fig.suptitle('EXP-2293: Glucose Corridors (p10-p90) by Hour\nRed/Orange lines = hypo/hyper thresholds', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig03-corridor.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 3: corridor")

    # Fig 4: TIR projection
    fig, ax = plt.subplots(figsize=(12, 6))
    r2294 = results['exp_2294']
    valid = [n for n in names if not r2294.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    current = [r2294[n]['current']['tir'] for n in valid]
    projected = [r2294[n]['projected']['tir'] for n in valid]
    w = 0.35
    ax.bar(x - w/2, current, w, label='Current', color='gray', alpha=0.7)
    ax.bar(x + w/2, projected, w, label='Projected', color='steelblue', alpha=0.7)
    ax.axhline(70, color='green', ls='--', label='70% Target')
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('TIR %'); ax.legend()
    ax.set_title('EXP-2294: Current vs Projected TIR Under Optimized Settings')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig04-projection.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 4: projection")

    # Fig 5: Monitoring cadence
    fig, ax = plt.subplots(figsize=(12, 5))
    r2295 = results['exp_2295']
    x = np.arange(len(names))
    days = [r2295[n]['recalibration_days'] for n in names]
    conf_colors = {'high': 'green', 'moderate': 'orange', 'low': 'red'}
    colors = [conf_colors.get(r2295[n]['confidence'], 'gray') for n in names]
    ax.bar(x, days, color=colors, alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Days Between Recalibration')
    ax.set_title('EXP-2295: Recommended Monitoring Cadence\n(Green=high confidence, orange=moderate, red=low)')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig05-cadence.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 5: cadence")

    # Fig 6: Algorithm mapping summary
    fig, ax = plt.subplots(figsize=(12, 6))
    r2296 = results['exp_2296']
    # Show key params comparison: Loop ISF, AAPS max_iob, Trio adjustment
    valid = [n for n in names if not r2296.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    loop_isf = [r2296[n]['loop']['isf'] for n in valid]
    aaps_max_iob = [r2296[n]['aaps']['max_iob'] for n in valid]
    trio_target = [r2296[n]['trio']['target_glucose'] for n in valid]
    ax2 = ax.twinx()
    ax.bar(x - 0.2, loop_isf, 0.4, label='ISF (mg/dL/U)', color='steelblue', alpha=0.7)
    ax2.bar(x + 0.2, aaps_max_iob, 0.4, label='Max IOB (U)', color='orange', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('ISF (mg/dL/U)', color='steelblue')
    ax2.set_ylabel('Max IOB (U)', color='orange')
    ax.set_title('EXP-2296: Algorithm Parameters (Loop ISF & AAPS Max IOB)')
    ax.legend(loc='upper left'); ax2.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig06-algorithm.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 6: algorithm")

    # Fig 7: Guardrails
    fig, ax = plt.subplots(figsize=(12, 5))
    r2297 = results['exp_2297']
    valid = [n for n in names if not r2297.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    passed = [r2297[n]['guardrails_passed'] for n in valid]
    total = [r2297[n]['guardrails_total'] for n in valid]
    colors = ['green' if r2297[n]['safe_to_implement'] else 'red' for n in valid]
    ax.bar(x, passed, color=colors, alpha=0.7)
    ax.bar(x, [t - p for t, p in zip(total, passed)], bottom=passed, color='gray', alpha=0.3)
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('Guardrails')
    ax.set_title('EXP-2297: Safety Guardrails (green=all passed, red=violations)')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig07-guardrails.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 7: guardrails")

    # Fig 8: Population dashboard
    fig = plt.figure(figsize=(16, 8))
    gs = GridSpec(2, 2)

    # TIR current vs projected
    ax1 = fig.add_subplot(gs[0, 0])
    r2294_d = results['exp_2294']
    valid = [n for n in names if not r2294_d.get(n, {}).get('skipped')]
    curr = [r2294_d[n]['current']['tir'] for n in valid]
    proj = [r2294_d[n]['projected']['tir'] for n in valid]
    ax1.scatter(curr, proj, s=100, c='steelblue', alpha=0.7, zorder=5)
    for i, n in enumerate(valid):
        ax1.annotate(n, (curr[i], proj[i]), fontsize=8, ha='center', va='bottom')
    ax1.plot([40, 100], [40, 100], 'k--', alpha=0.3)
    ax1.axhline(70, color='green', ls=':', alpha=0.5)
    ax1.axvline(70, color='green', ls=':', alpha=0.5)
    ax1.set_xlabel('Current TIR %'); ax1.set_ylabel('Projected TIR %')
    ax1.set_title('TIR: Current vs Projected')

    # Phenotype pie
    ax2 = fig.add_subplot(gs[0, 1])
    r2298 = results['exp_2298']
    pheno = r2298['phenotype_distribution']
    labels = [f'{k}\n({v})' for k, v in pheno.items() if v > 0]
    vals = [v for v in pheno.values() if v > 0]
    ax2.pie(vals, labels=labels, autopct='%1.0f%%', colors=['#e74c3c', '#3498db', '#95a5a6'])
    ax2.set_title('Hypo Phenotype Distribution')

    # Summary metrics
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis('off')
    summary_text = (
        f"Population Summary (n={r2298['n_patients']})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Mean TIR improvement:     {r2298['mean_tir_improvement']:+.1f} pp\n"
        f"Median TIR improvement:   {r2298['median_tir_improvement']:+.1f} pp\n"
        f"Mean TBR improvement:     {r2298['mean_tbr_improvement']:+.1f} pp\n"
        f"Patients meeting 70% TIR: {r2298['patients_meeting_70_tir']}/{r2298['n_patients']}\n"
        f"Safe to implement:        {r2298['patients_safe_to_implement']}/{r2298['n_patients']}\n"
    )
    ax3.text(0.05, 0.95, summary_text, transform=ax3.transAxes, fontsize=14,
             fontfamily='monospace', va='top')

    fig.suptitle('EXP-2298: Integrated Therapy Optimization Dashboard', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/int-fig08-dashboard.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 8: dashboard")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true', help='Use tiny parquet for fast dev')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    print("Loading prior results...")
    prior = load_prior_results()
    print()

    results = {}

    print("Running exp_2291: Settings Recommendation...")
    results['exp_2291'] = exp_2291_settings(patients, prior)
    print("  ✓ completed")

    print("Running exp_2292: 2-Zone Profiles...")
    results['exp_2292'] = exp_2292_profiles(patients, prior)
    print("  ✓ completed")

    print("Running exp_2293: Safety Corridors...")
    results['exp_2293'] = exp_2293_corridor(patients, prior)
    print("  ✓ completed")

    print("Running exp_2294: Outcome Projection...")
    results['exp_2294'] = exp_2294_projection(patients, results['exp_2291'])
    print("  ✓ completed")

    print("Running exp_2295: Monitoring Cadence...")
    results['exp_2295'] = exp_2295_cadence(patients, prior)
    print("  ✓ completed")

    print("Running exp_2296: Algorithm Mapping...")
    results['exp_2296'] = exp_2296_algorithm_mapping(patients, results['exp_2291'], prior)
    print("  ✓ completed")

    print("Running exp_2297: Safety Guardrails...")
    results['exp_2297'] = exp_2297_guardrails(patients, results['exp_2291'], results['exp_2294'])
    print("  ✓ completed")

    print("Running exp_2298: Population Dashboard...")
    results['exp_2298'] = exp_2298_dashboard(patients, results)
    print("  ✓ completed")

    out_path = 'externals/experiments/exp-2291-2298_integrated.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out_path}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
