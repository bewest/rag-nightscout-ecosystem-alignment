#!/usr/bin/env python3
"""
EXP-2321 through EXP-2328: Unified Patient Phenotyping Engine

Combines all prior analysis into a comprehensive per-patient profile that
maps to specific algorithm recommendations.

Experiments:
  2321: Multi-dimensional phenotype clustering
  2322: Therapy priority ranking (what to fix first)
  2323: Risk stratification (composite safety score)
  2324: Algorithm suitability (which AID features help which patients)
  2325: Data quality assessment (reliability of each patient's data)
  2326: Intervention impact estimation (expected benefit per change)
  2327: Cross-patient similarity network
  2328: Comprehensive patient passport (unified report)

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_phenotype_2321.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_phenotype_2321.py --figures --tiny
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        profile = {
            'isf': float(pdf['scheduled_isf'].median()),
            'cr': float(pdf['scheduled_cr'].median()),
            'basal': float(pdf['scheduled_basal_rate'].median()),
        }
        patients.append({'name': pid, 'df': pdf, 'profile': profile})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def load_prior_results():
    """Load all prior experiment results."""
    prior = {}
    paths = {
        'variability': 'externals/experiments/exp-2261-2268_variability.json',
        'circadian': 'externals/experiments/exp-2271-2278_circadian.json',
        'hypo': 'externals/experiments/exp-2281-2288_hypo_safety.json',
        'integrated': 'externals/experiments/exp-2291-2298_integrated.json',
        'meal': 'externals/experiments/exp-2301-2308_meal_response.json',
        'loop': 'externals/experiments/exp-2311-2318_loop_decisions.json',
    }
    for key, path in paths.items():
        if os.path.exists(path):
            with open(path) as f:
                prior[key] = json.load(f)
            print(f"  Loaded {key}")
        else:
            print(f"  Missing {key}")
    return prior


def compute_metrics(df):
    """Compute basic glucose metrics."""
    bg = df['glucose'].values
    valid = bg[~np.isnan(bg)]
    if len(valid) == 0:
        return {}
    return {
        'tir': float(np.mean((valid >= 70) & (valid <= 180)) * 100),
        'tbr': float(np.mean(valid < 70) * 100),
        'tar': float(np.mean(valid > 180) * 100),
        'mean_bg': float(np.mean(valid)),
        'cv': float(np.std(valid) / np.mean(valid) * 100),
        'gmi': float(3.31 + 0.02392 * np.mean(valid)),
        'cgm_coverage': float(np.mean(~np.isnan(bg)) * 100),
        'n_days': len(df) / (STEPS_PER_HOUR * 24),
    }


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2321_clustering(patients, prior):
    """Multi-dimensional phenotype clustering."""
    names = [p['name'] for p in patients]
    
    # Build feature matrix from all prior results
    features = []
    feature_names = []
    
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        # Glucose metrics
        row = [
            metrics.get('tir', 50),
            metrics.get('tbr', 5),
            metrics.get('tar', 30),
            metrics.get('cv', 30),
        ]
        
        # Hypo phenotype
        hypo = prior.get('hypo', {}).get('exp_2283', {}).get(name, {})
        row.append(hypo.get('median_start_bg', 120))
        
        # Meal response
        meal = prior.get('meal', {}).get('exp_2301', {}).get(name, {})
        row.extend([
            meal.get('meals_per_day', 2),
            meal.get('mean_rise', 60),
        ])
        
        # Loop behavior
        loop = prior.get('loop', {}).get('exp_2311', {}).get(name, {})
        row.extend([
            loop.get('zero_delivery_pct', 50),
            loop.get('above_scheduled_pct', 10),
        ])
        
        # Variability
        var = prior.get('variability', {}).get('exp_2268', {}).get(name, {})
        primary = var.get('primary_source', 'circadian')
        row.append(1.0 if primary == 'sensitivity' else 0.0)
        
        features.append(row)
    
    feature_names = ['TIR', 'TBR', 'TAR', 'CV', 'hypo_start_bg',
                     'meals_per_day', 'meal_rise',
                     'zero_delivery_pct', 'above_scheduled_pct',
                     'sensitivity_dominant']
    
    X = np.array(features)
    
    # Normalize
    X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    
    # Hierarchical clustering
    dist = pdist(X_norm, metric='euclidean')
    Z = linkage(dist, method='ward')
    clusters = fcluster(Z, t=3, criterion='maxclust')
    
    # Name clusters by dominant characteristics
    cluster_profiles = {}
    for c in np.unique(clusters):
        mask = clusters == c
        c_names = [names[i] for i in range(len(names)) if mask[i]]
        c_features = X[mask]
        cluster_profiles[int(c)] = {
            'patients': c_names,
            'mean_tir': round(float(c_features[:, 0].mean()), 1),
            'mean_tbr': round(float(c_features[:, 1].mean()), 1),
            'mean_cv': round(float(c_features[:, 3].mean()), 1),
            'mean_zero_delivery': round(float(c_features[:, 7].mean()), 1),
        }
    
    results = {
        'clusters': {names[i]: int(clusters[i]) for i in range(len(names))},
        'cluster_profiles': cluster_profiles,
        'feature_names': feature_names,
        'n_clusters': len(np.unique(clusters)),
    }
    
    for c, prof in cluster_profiles.items():
        print(f"  Cluster {c}: {prof['patients']} — TIR={prof['mean_tir']:.0f}%, TBR={prof['mean_tbr']:.1f}%, CV={prof['mean_cv']:.0f}%")
    return results


def exp_2322_priority(patients, prior):
    """Therapy priority ranking — what to fix first."""
    results = {}
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        priorities = []
        
        # Check TBR (safety first)
        tbr = metrics.get('tbr', 0)
        if tbr > 4:
            priorities.append(('reduce_hypo', 'CRITICAL', f'TBR {tbr:.1f}% > 4% target'))
        elif tbr > 1:
            priorities.append(('reduce_hypo', 'HIGH', f'TBR {tbr:.1f}% > 1% ideal'))
        
        # Check TIR
        tir = metrics.get('tir', 50)
        if tir < 50:
            priorities.append(('improve_tir', 'CRITICAL', f'TIR {tir:.0f}% < 50% minimum'))
        elif tir < 70:
            priorities.append(('improve_tir', 'HIGH', f'TIR {tir:.0f}% < 70% target'))
        
        # Check CV
        cv = metrics.get('cv', 30)
        if cv > 36:
            priorities.append(('reduce_variability', 'HIGH', f'CV {cv:.0f}% > 36% target'))
        
        # Check meal response
        meal = prior.get('meal', {}).get('exp_2308', {}).get(name, {})
        if meal and not meal.get('skipped'):
            grade = meal.get('grade', 'C')
            if grade == 'D':
                priorities.append(('improve_meals', 'HIGH', f'Meal grade D'))
            elif grade == 'C':
                priorities.append(('improve_meals', 'MODERATE', f'Meal grade C'))
        
        # Check settings
        settings = prior.get('integrated', {}).get('exp_2291', {}).get(name, {})
        if settings:
            isf_pct = settings.get('corrections', {}).get('isf_pct', 0)
            cr_pct = settings.get('corrections', {}).get('cr_pct', 0)
            if abs(isf_pct) > 15:
                priorities.append(('correct_isf', 'HIGH', f'ISF needs {isf_pct:+.0f}% correction'))
            if abs(cr_pct) > 20:
                priorities.append(('correct_cr', 'HIGH', f'CR needs {cr_pct:+.0f}% correction'))
        
        # Sort by severity
        severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MODERATE': 2, 'LOW': 3}
        priorities.sort(key=lambda x: severity_order.get(x[1], 4))
        
        results[name] = {
            'priorities': [{'action': p[0], 'severity': p[1], 'reason': p[2]} for p in priorities],
            'n_critical': sum(1 for p in priorities if p[1] == 'CRITICAL'),
            'n_high': sum(1 for p in priorities if p[1] == 'HIGH'),
            'top_priority': priorities[0][0] if priorities else 'none',
        }
        top = priorities[0] if priorities else ('none', 'LOW', '')
        print(f"  {name}: #{1} {top[0]} ({top[1]}), {len(priorities)} total priorities")
    return results


def exp_2323_risk(patients, prior):
    """Risk stratification — composite safety score."""
    results = {}
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        risk_score = 0
        risk_factors = []
        
        # TBR contribution (0-40 points)
        tbr = metrics.get('tbr', 0)
        tbr_risk = min(40, tbr * 8)
        risk_score += tbr_risk
        if tbr > 4:
            risk_factors.append(f'High TBR ({tbr:.1f}%)')
        
        # CV contribution (0-20 points)
        cv = metrics.get('cv', 30)
        cv_risk = max(0, min(20, (cv - 30) * 2))
        risk_score += cv_risk
        if cv > 36:
            risk_factors.append(f'High CV ({cv:.0f}%)')
        
        # Hypo frequency (from prior)
        hypo = prior.get('hypo', {}).get('exp_2281', {}).get(name, {})
        hypo_per_day = hypo.get('hypos_per_day', 0)
        hypo_risk = min(20, hypo_per_day * 10)
        risk_score += hypo_risk
        if hypo_per_day > 1:
            risk_factors.append(f'Frequent hypos ({hypo_per_day:.1f}/day)')
        
        # Loop effectiveness (from prior)
        loop = prior.get('loop', {}).get('exp_2318', {}).get(name, {})
        loop_grade = loop.get('overall', 50) if loop else 50
        loop_risk = max(0, (100 - loop_grade) * 0.2)
        risk_score += loop_risk
        
        risk_score = min(100, risk_score)
        
        if risk_score >= 60:
            category = 'HIGH'
        elif risk_score >= 30:
            category = 'MODERATE'
        else:
            category = 'LOW'
        
        results[name] = {
            'risk_score': round(risk_score, 1),
            'category': category,
            'components': {
                'tbr_risk': round(tbr_risk, 1),
                'cv_risk': round(cv_risk, 1),
                'hypo_risk': round(hypo_risk, 1),
                'loop_risk': round(loop_risk, 1),
            },
            'risk_factors': risk_factors,
        }
        print(f"  {name}: {category} ({risk_score:.0f}/100) — {risk_factors if risk_factors else 'no major factors'}")
    return results


def exp_2324_algorithm(patients, prior):
    """Algorithm suitability — which AID features help which patients."""
    results = {}
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        # Analyze which algorithmic features would help
        features = {}
        
        # SMB (Super Micro Bolus): helps with post-meal spikes
        meal = prior.get('meal', {}).get('exp_2301', {}).get(name, {})
        mean_rise = meal.get('mean_rise', 60)
        features['smb'] = {
            'benefit': 'HIGH' if mean_rise > 80 else 'MODERATE' if mean_rise > 50 else 'LOW',
            'reason': f'Mean meal rise {mean_rise:.0f} mg/dL',
        }
        
        # Dynamic ISF: helps sensitivity-dominant patients
        var = prior.get('variability', {}).get('exp_2268', {}).get(name, {})
        primary = var.get('primary_source', 'circadian')
        features['dynamic_isf'] = {
            'benefit': 'HIGH' if primary == 'sensitivity' else 'MODERATE',
            'reason': f'Primary variability: {primary}',
        }
        
        # UAM (Unannounced Meal): helps patients with low meal logging
        meals_per_day = meal.get('meals_per_day', 2)
        uam_per_day = meal.get('uam_per_day', 20)
        features['uam'] = {
            'benefit': 'HIGH' if uam_per_day > meals_per_day * 5 else 'MODERATE' if uam_per_day > meals_per_day * 2 else 'LOW',
            'reason': f'{meals_per_day:.1f} meals vs {uam_per_day:.0f} UAM/day',
        }
        
        # Autosens: helps patients with variable ISF
        circ = prior.get('circadian', {}).get('exp_2275', {}).get(name, {})
        stability = circ.get('stability_score', 0.5)
        features['autosens'] = {
            'benefit': 'HIGH' if stability < 0.4 else 'MODERATE' if stability < 0.7 else 'LOW',
            'reason': f'Profile stability {stability:.2f}',
        }
        
        # Suspend before low: helps high TBR patients
        tbr = metrics.get('tbr', 0)
        features['suspend_before_low'] = {
            'benefit': 'HIGH' if tbr > 4 else 'MODERATE' if tbr > 2 else 'LOW',
            'reason': f'TBR {tbr:.1f}%',
        }
        
        # Count high-benefit features
        high_count = sum(1 for f in features.values() if f['benefit'] == 'HIGH')
        
        results[name] = {
            'features': features,
            'high_benefit_count': high_count,
            'recommended_algorithm': 'oref1/AAPS' if high_count >= 3 else 'Loop' if high_count <= 1 else 'Trio',
        }
        print(f"  {name}: {high_count} high-benefit features → {results[name]['recommended_algorithm']}")
    return results


def exp_2325_data_quality(patients):
    """Data quality assessment."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        n_days = len(df) / (STEPS_PER_HOUR * 24)
        
        # CGM coverage
        cgm_coverage = float(df['glucose'].notna().mean() * 100)
        
        # Loop data coverage
        loop_coverage = float(df['loop_enacted_rate'].notna().mean() * 100) if 'loop_enacted_rate' in df.columns else 0
        
        # Bolus data
        bolus_days = float((df['bolus'] > 0).sum() / (STEPS_PER_HOUR * 24))
        
        # Carb data
        carb_days = float((df['carbs'] > 0).sum() / (STEPS_PER_HOUR * 24))
        
        # Sensor phase data
        sensor_coverage = float(df['sensor_phase'].notna().mean() * 100) if 'sensor_phase' in df.columns else 0
        
        # Overall quality score
        quality = 0
        if cgm_coverage > 80: quality += 30
        elif cgm_coverage > 50: quality += 15
        if loop_coverage > 70: quality += 25
        elif loop_coverage > 40: quality += 12
        if n_days > 90: quality += 20
        elif n_days > 30: quality += 10
        if carb_days > 1: quality += 15
        elif carb_days > 0.5: quality += 8
        quality += min(10, sensor_coverage / 10)
        
        grade = 'A' if quality >= 80 else 'B' if quality >= 60 else 'C' if quality >= 40 else 'D'
        
        results[name] = {
            'cgm_coverage': round(cgm_coverage, 1),
            'loop_coverage': round(loop_coverage, 1),
            'bolus_events_per_day': round(bolus_days, 1),
            'carb_events_per_day': round(carb_days, 1),
            'n_days': round(n_days, 0),
            'quality_score': round(quality, 1),
            'grade': grade,
        }
        print(f"  {name}: {grade} ({quality:.0f}), CGM={cgm_coverage:.0f}%, loop={loop_coverage:.0f}%, {n_days:.0f}d")
    return results


def exp_2326_impact(patients, prior):
    """Intervention impact estimation."""
    results = {}
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        interventions = {}
        
        # 1. ISF correction impact
        tbr = metrics.get('tbr', 0)
        interventions['isf_correction'] = {
            'expected_tbr_reduction': round(tbr * 0.15, 1),  # 15% of current TBR
            'expected_tar_increase': round(metrics.get('tar', 0) * 0.03, 1),  # slight increase
            'confidence': 'HIGH',
        }
        
        # 2. CR correction impact
        meal = prior.get('meal', {}).get('exp_2307', {}).get(name, {})
        stacking = meal.get('stacking_rate', 50) if meal and not meal.get('skipped') else 50
        interventions['cr_correction'] = {
            'expected_stacking_reduction': round(stacking * 0.3, 1),  # 30% less stacking
            'expected_tar_reduction': round(metrics.get('tar', 0) * 0.1, 1),
            'confidence': 'MODERATE',
        }
        
        # 3. Basal optimization
        loop = prior.get('loop', {}).get('exp_2313', {}).get(name, {})
        suspension = loop.get('suspension_pct', 50)
        interventions['basal_optimization'] = {
            'expected_suspension_reduction': round(suspension * 0.1, 1),
            'expected_tir_improvement': round(max(0, (suspension - 50) * 0.1), 1),
            'confidence': 'MODERATE',
        }
        
        # 4. 2-zone profiling
        circ = prior.get('circadian', {}).get('exp_2275', {}).get(name, {})
        stability = circ.get('stability_score', 0.5)
        interventions['two_zone_profile'] = {
            'expected_tir_improvement': round(max(0, (0.8 - stability) * 5), 1) if stability < 0.8 else 0,
            'confidence': 'HIGH' if stability > 0.5 else 'LOW',
        }
        
        # Rank by expected impact
        total_impact = (
            interventions['isf_correction']['expected_tbr_reduction'] * 3 +
            interventions['cr_correction']['expected_tar_reduction'] * 2 +
            interventions['basal_optimization']['expected_tir_improvement'] * 2 +
            interventions['two_zone_profile']['expected_tir_improvement']
        )
        
        results[name] = {
            'interventions': interventions,
            'total_impact_score': round(total_impact, 1),
        }
        print(f"  {name}: impact score={total_impact:.1f}")
    return results


def exp_2327_similarity(patients, prior):
    """Cross-patient similarity network."""
    names = [p['name'] for p in patients]
    n = len(names)
    
    # Build feature vectors
    features = []
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        row = [
            metrics.get('tir', 50), metrics.get('tbr', 5),
            metrics.get('cv', 30), metrics.get('mean_bg', 150),
        ]
        # Add meal and loop features
        meal = prior.get('meal', {}).get('exp_2301', {}).get(name, {})
        loop = prior.get('loop', {}).get('exp_2311', {}).get(name, {})
        row.extend([
            meal.get('meals_per_day', 2),
            meal.get('mean_rise', 60),
            loop.get('zero_delivery_pct', 50),
        ])
        features.append(row)
    
    X = np.array(features)
    X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    
    # Compute pairwise distances
    dist_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dist_matrix[i, j] = np.sqrt(np.sum((X_norm[i] - X_norm[j])**2))
    
    # Find most similar pairs
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((names[i], names[j], round(float(dist_matrix[i, j]), 2)))
    pairs.sort(key=lambda x: x[2])
    
    results = {
        'distance_matrix': {names[i]: {names[j]: round(float(dist_matrix[i, j]), 2) for j in range(n)} for i in range(n)},
        'most_similar': [{'pair': [p[0], p[1]], 'distance': p[2]} for p in pairs[:5]],
        'most_different': [{'pair': [p[0], p[1]], 'distance': p[2]} for p in pairs[-5:]],
    }
    
    print(f"  Most similar: {pairs[0][0]}-{pairs[0][1]} (d={pairs[0][2]:.2f})")
    print(f"  Most different: {pairs[-1][0]}-{pairs[-1][1]} (d={pairs[-1][2]:.2f})")
    return results


def exp_2328_passport(patients, all_results, prior):
    """Comprehensive patient passport."""
    results = {}
    for pat in patients:
        name = pat['name']
        metrics = compute_metrics(pat['df'])
        
        # Gather from all experiments
        cluster = all_results.get('exp_2321', {}).get('clusters', {}).get(name, 0)
        priority = all_results.get('exp_2322', {}).get(name, {})
        risk = all_results.get('exp_2323', {}).get(name, {})
        algo = all_results.get('exp_2324', {}).get(name, {})
        quality = all_results.get('exp_2325', {}).get(name, {})
        impact = all_results.get('exp_2326', {}).get(name, {})
        
        # Hypo phenotype
        settings = prior.get('integrated', {}).get('exp_2291', {}).get(name, {})
        phenotype = settings.get('phenotype', 'unknown')
        
        # Cadence
        cadence = prior.get('integrated', {}).get('exp_2295', {}).get(name, {})
        
        passport = {
            'patient': name,
            'cluster': cluster,
            'phenotype': phenotype,
            'risk_category': risk.get('category', 'UNKNOWN'),
            'risk_score': risk.get('risk_score', 0),
            'data_quality': quality.get('grade', '?'),
            'top_priority': priority.get('top_priority', 'none'),
            'n_priorities': len(priority.get('priorities', [])),
            'recommended_algorithm': algo.get('recommended_algorithm', '?'),
            'recalibration_days': cadence.get('recalibration_days', 60),
            'metrics': metrics,
            'recommended_settings': settings.get('recommended', {}),
            'impact_score': impact.get('total_impact_score', 0),
        }
        
        results[name] = passport
        print(f"  {name}: {phenotype}, {risk.get('category', '?')} risk, #{1} {priority.get('top_priority', '?')}, algo={algo.get('recommended_algorithm', '?')}")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])

    # Fig 1: Clustering dendrogram-like visualization
    fig, ax = plt.subplots(figsize=(14, 6))
    r2321 = results['exp_2321']
    clusters = [r2321['clusters'].get(n, 0) for n in names]
    colors = {1: '#e74c3c', 2: '#3498db', 3: '#2ecc71'}
    cluster_colors = [colors.get(c, 'gray') for c in clusters]
    
    metrics = [compute_metrics(p['df']) for p in patients]
    tir = [m.get('tir', 50) for m in metrics]
    tbr = [m.get('tbr', 5) for m in metrics]
    
    scatter = ax.scatter(tir, tbr, c=cluster_colors, s=200, zorder=5, edgecolors='black')
    for i, n in enumerate(names):
        ax.annotate(n, (tir[i], tbr[i]), fontsize=12, ha='center', va='bottom', fontweight='bold')
    ax.set_xlabel('TIR %', fontsize=12); ax.set_ylabel('TBR %', fontsize=12)
    ax.axvline(70, color='green', ls='--', alpha=0.3, label='70% TIR target')
    ax.axhline(4, color='red', ls='--', alpha=0.3, label='4% TBR limit')
    ax.legend()
    ax.set_title('EXP-2321: Patient Clusters (TIR vs TBR)', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig01-clusters.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: clusters")

    # Fig 2: Priority ranking
    fig, ax = plt.subplots(figsize=(14, 6))
    r2322 = results['exp_2322']
    x = np.arange(len(names))
    crit = [r2322[n]['n_critical'] for n in names]
    high = [r2322[n]['n_high'] for n in names]
    ax.bar(x, crit, color='red', alpha=0.7, label='Critical')
    ax.bar(x, high, bottom=crit, color='orange', alpha=0.7, label='High')
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Number of Priorities'); ax.legend()
    for i, n in enumerate(names):
        top = r2322[n]['top_priority']
        ax.text(i, crit[i] + high[i] + 0.1, top.replace('_', '\n'), ha='center', va='bottom', fontsize=7)
    ax.set_title('EXP-2322: Therapy Priority Ranking', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig02-priorities.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: priorities")

    # Fig 3: Risk stratification
    fig, ax = plt.subplots(figsize=(12, 5))
    r2323 = results['exp_2323']
    scores = [r2323[n]['risk_score'] for n in names]
    cat_colors = {'HIGH': 'red', 'MODERATE': 'orange', 'LOW': 'green'}
    colors = [cat_colors.get(r2323[n]['category'], 'gray') for n in names]
    ax.bar(np.arange(len(names)), scores, color=colors, alpha=0.7)
    ax.axhline(60, color='red', ls='--', alpha=0.5, label='HIGH threshold')
    ax.axhline(30, color='orange', ls='--', alpha=0.5, label='MODERATE threshold')
    ax.set_xticks(np.arange(len(names))); ax.set_xticklabels(names)
    ax.set_ylabel('Risk Score (0-100)'); ax.legend()
    ax.set_title('EXP-2323: Composite Risk Stratification', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig03-risk.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: risk")

    # Fig 4: Algorithm suitability
    fig, ax = plt.subplots(figsize=(14, 6))
    r2324 = results['exp_2324']
    features_list = ['smb', 'dynamic_isf', 'uam', 'autosens', 'suspend_before_low']
    feature_labels = ['SMB', 'Dynamic\nISF', 'UAM', 'Autosens', 'Suspend\nBefore Low']
    benefit_vals = {'HIGH': 2, 'MODERATE': 1, 'LOW': 0}
    data = np.array([[benefit_vals.get(r2324[n]['features'][f]['benefit'], 0) for f in features_list] for n in names])
    im = ax.imshow(data.T, aspect='auto', cmap='RdYlGn', vmin=0, vmax=2)
    ax.set_xticks(range(len(names))); ax.set_xticklabels(names)
    ax.set_yticks(range(len(feature_labels))); ax.set_yticklabels(feature_labels)
    for i in range(len(names)):
        for j in range(len(features_list)):
            benefit = r2324[names[i]]['features'][features_list[j]]['benefit']
            ax.text(i, j, benefit[0], ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(i, -0.6, r2324[names[i]]['recommended_algorithm'], ha='center', fontsize=8, fontweight='bold')
    plt.colorbar(im, label='Benefit (0=Low, 2=High)')
    ax.set_title('EXP-2324: Algorithm Feature Suitability', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig04-algorithm.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: algorithm")

    # Fig 5: Data quality
    fig, ax = plt.subplots(figsize=(12, 5))
    r2325 = results['exp_2325']
    scores_q = [r2325[n]['quality_score'] for n in names]
    grade_colors = {'A': 'green', 'B': 'steelblue', 'C': 'orange', 'D': 'red'}
    colors_q = [grade_colors.get(r2325[n]['grade'], 'gray') for n in names]
    ax.bar(np.arange(len(names)), scores_q, color=colors_q, alpha=0.7)
    ax.set_xticks(np.arange(len(names))); ax.set_xticklabels(names)
    for i, n in enumerate(names):
        ax.text(i, scores_q[i] + 1, r2325[n]['grade'], ha='center', fontsize=12, fontweight='bold')
    ax.set_ylabel('Quality Score'); ax.set_title('EXP-2325: Data Quality Assessment', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig05-quality.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: quality")

    # Fig 6: Intervention impact
    fig, ax = plt.subplots(figsize=(12, 5))
    r2326 = results['exp_2326']
    impacts = [r2326[n]['total_impact_score'] for n in names]
    ax.bar(np.arange(len(names)), impacts, color='mediumpurple', alpha=0.7)
    ax.set_xticks(np.arange(len(names))); ax.set_xticklabels(names)
    ax.set_ylabel('Impact Score'); ax.set_title('EXP-2326: Expected Intervention Impact', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig06-impact.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: impact")

    # Fig 7: Similarity network
    fig, ax = plt.subplots(figsize=(10, 10))
    r2327 = results['exp_2327']
    # Plot as scatter with lines for most similar pairs
    np.random.seed(42)
    pos = {n: (np.random.randn(), np.random.randn()) for n in names}
    # Use MDS-like positioning from distance matrix
    from scipy.spatial.distance import squareform
    dist_flat = []
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            dist_flat.append(r2327['distance_matrix'][names[i]][names[j]])
    # Simple spring layout
    pos_arr = np.random.randn(len(names), 2) * 2
    for _ in range(100):
        forces = np.zeros_like(pos_arr)
        for i in range(len(names)):
            for j in range(i+1, len(names)):
                d = r2327['distance_matrix'][names[i]][names[j]]
                diff = pos_arr[j] - pos_arr[i]
                dist = np.sqrt(np.sum(diff**2)) + 1e-8
                force = (dist - d) * diff / dist * 0.01
                forces[i] += force
                forces[j] -= force
        pos_arr += forces
    
    for i, n in enumerate(names):
        ax.scatter(pos_arr[i, 0], pos_arr[i, 1], s=300, c=cluster_colors[i], zorder=5, edgecolors='black')
        ax.annotate(n, pos_arr[i], fontsize=14, ha='center', va='bottom', fontweight='bold')
    
    # Draw lines for top 5 most similar
    for pair in r2327['most_similar'][:5]:
        i = names.index(pair['pair'][0])
        j = names.index(pair['pair'][1])
        ax.plot([pos_arr[i, 0], pos_arr[j, 0]], [pos_arr[i, 1], pos_arr[j, 1]],
                'b-', alpha=0.3, lw=2)
    
    ax.set_title('EXP-2327: Patient Similarity Network\n(Lines = most similar pairs)', fontsize=14, fontweight='bold')
    ax.axis('off')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pheno-fig07-network.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: network")

    # Fig 8: Patient passport summary
    fig = plt.figure(figsize=(18, 10))
    r2328 = results['exp_2328']
    gs = GridSpec(3, 4, hspace=0.4, wspace=0.3)
    
    for idx, name in enumerate(names):
        if idx >= 11: break
        row, col = idx // 4, idx % 4
        ax = fig.add_subplot(gs[row, col])
        p = r2328[name]
        
        risk_colors = {'HIGH': '#e74c3c', 'MODERATE': '#f39c12', 'LOW': '#27ae60', 'UNKNOWN': 'gray'}
        bg_color = risk_colors.get(p['risk_category'], 'gray')
        
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.05",
                     facecolor=bg_color, alpha=0.15, transform=ax.transAxes))
        
        text = (
            f"Patient {name}\n"
            f"━━━━━━━━━━━━━━\n"
            f"Phenotype: {p['phenotype']}\n"
            f"Risk: {p['risk_category']} ({p['risk_score']:.0f})\n"
            f"Data: {p['data_quality']}\n"
            f"#1: {p['top_priority']}\n"
            f"Algo: {p['recommended_algorithm']}\n"
            f"Recal: {p['recalibration_days']}d\n"
            f"TIR: {p['metrics'].get('tir', 0):.0f}%"
        )
        ax.text(0.1, 0.9, text, transform=ax.transAxes, fontsize=8,
                fontfamily='monospace', va='top')
        ax.axis('off')
    
    if len(names) < 12:
        ax_last = fig.add_subplot(gs[2, 3])
        ax_last.axis('off')
    
    fig.suptitle('EXP-2328: Patient Passports', fontsize=16, fontweight='bold')
    plt.savefig(f'{fig_dir}/pheno-fig08-passports.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: passports")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    print("Loading prior results...")
    prior = load_prior_results()
    print()

    results = {}

    for exp_id, exp_name, exp_fn in [
        ('exp_2321', 'Clustering', lambda: exp_2321_clustering(patients, prior)),
        ('exp_2322', 'Priority Ranking', lambda: exp_2322_priority(patients, prior)),
        ('exp_2323', 'Risk Stratification', lambda: exp_2323_risk(patients, prior)),
        ('exp_2324', 'Algorithm Suitability', lambda: exp_2324_algorithm(patients, prior)),
        ('exp_2325', 'Data Quality', lambda: exp_2325_data_quality(patients)),
        ('exp_2326', 'Impact Estimation', lambda: exp_2326_impact(patients, prior)),
        ('exp_2327', 'Similarity Network', lambda: exp_2327_similarity(patients, prior)),
    ]:
        print(f"Running {exp_id}: {exp_name}...")
        results[exp_id] = exp_fn()
        print(f"  ✓ completed\n")

    print("Running exp_2328: Patient Passport...")
    results['exp_2328'] = exp_2328_passport(patients, results, prior)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2321-2328_phenotype.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"Results saved to {out_path}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
