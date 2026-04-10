#!/usr/bin/env python3
"""
EXP-1991–1998: Patient Phenotyping & Personalized Algorithm Selection

Building on all prior research (EXP-1851–1988), these experiments synthesize
patient-level profiles to determine which algorithm strategies benefit which
patients. The goal is to move from population-level findings to personalized
recommendations.

Key hypotheses:
- Patients cluster into distinct metabolic phenotypes
- Each phenotype has a different optimal algorithm strategy
- Cross-patient transfer of settings corrections fails because phenotypes differ
- A small number of features can predict phenotype membership
- Phenotype-aware algorithms outperform one-size-fits-all approaches

Depends on: exp_metabolic_441.py, all prior experiment findings.

Usage: PYTHONPATH=tools python3 tools/cgmencode/exp_patient_phenotyping_1991.py --figures
"""

import sys
import os
import json
import argparse
import numpy as np
import warnings
warnings.filterwarnings('ignore')

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
FIGURES_DIR = 'docs/60-research/figures'
RESULTS_FILE = 'externals/experiments/exp-1991_patient_phenotyping.json'


def get_isf(df):
    isf_sched = df.attrs.get('isf_schedule', [{'value': 50}])
    isf = float(isf_sched[0]['value'])
    if isf < 15:
        isf *= 18.0182
    return isf

def get_cr(df):
    cr_sched = df.attrs.get('cr_schedule', [{'value': 10}])
    return float(cr_sched[0]['value'])

def get_basal(df):
    basal_sched = df.attrs.get('basal_schedule', [{'value': 1.0}])
    return float(basal_sched[0]['value'])

def glucose_metrics(glucose):
    valid = glucose[~np.isnan(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'cv': np.nan, 'mean': np.nan}
    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
    tbr = np.mean(valid < 70) * 100
    tar = np.mean(valid > 180) * 100
    cv = np.std(valid) / np.mean(valid) * 100
    return {'tir': tir, 'tbr': tbr, 'tar': tar, 'cv': cv, 'mean': np.mean(valid)}

def hour_of_day(idx):
    return (idx % STEPS_PER_DAY) / STEPS_PER_HOUR


# ============================================================================
# EXP-1991: Comprehensive Patient Feature Extraction
# ============================================================================

def exp_1991_feature_extraction(patients, make_figures=False):
    """Extract comprehensive feature vectors for each patient."""
    print("\n" + "=" * 70)
    print("EXP-1991: Comprehensive Patient Feature Extraction")
    print("=" * 70)

    results = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values
        iob = df['iob'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        isf = get_isf(df)
        cr = get_cr(df)
        sched_basal = get_basal(df)
        metrics = glucose_metrics(glucose)

        # Glucose dynamics
        valid_g = glucose[~np.isnan(glucose)]
        glucose_mean = np.mean(valid_g) if len(valid_g) > 0 else np.nan
        glucose_std = np.std(valid_g) if len(valid_g) > 0 else np.nan

        # Trend rate distribution
        trends = np.diff(glucose)
        valid_trends = trends[~np.isnan(trends)]
        trend_mean = np.mean(valid_trends) if len(valid_trends) > 0 else 0
        trend_std = np.std(valid_trends) if len(valid_trends) > 0 else 0

        # Time-of-day patterns
        morning_tir = []
        evening_tir = []
        overnight_tir = []
        for i in range(n):
            h = hour_of_day(i)
            if np.isnan(glucose[i]):
                continue
            in_range = 70 <= glucose[i] <= 180
            if 6 <= h < 10:
                morning_tir.append(in_range)
            elif 17 <= h < 21:
                evening_tir.append(in_range)
            elif h < 6 or h >= 22:
                overnight_tir.append(in_range)

        morning_tir_val = np.mean(morning_tir) * 100 if morning_tir else np.nan
        evening_tir_val = np.mean(evening_tir) * 100 if evening_tir else np.nan
        overnight_tir_val = np.mean(overnight_tir) * 100 if overnight_tir else np.nan

        # Dawn phenomenon
        g_3am = [glucose[i] for i in range(n) if 2.5 <= hour_of_day(i) < 3.5 and not np.isnan(glucose[i])]
        g_8am = [glucose[i] for i in range(n) if 7.5 <= hour_of_day(i) < 8.5 and not np.isnan(glucose[i])]
        dawn_rise = np.mean(g_8am) - np.mean(g_3am) if g_3am and g_8am else 0

        # Meal patterns
        meal_count = np.sum(carbs >= 5)
        meals_per_day = meal_count / (n / STEPS_PER_DAY) if n > 0 else 0
        mean_carbs = np.mean(carbs[carbs >= 5]) if np.sum(carbs >= 5) > 0 else 0
        total_daily_carbs = np.sum(carbs) / (n / STEPS_PER_DAY)

        # Bolus patterns
        bolus_count = np.sum(bolus >= 0.1)
        boluses_per_day = bolus_count / (n / STEPS_PER_DAY)
        mean_bolus = np.mean(bolus[bolus >= 0.1]) if np.sum(bolus >= 0.1) > 0 else 0
        total_daily_bolus = np.sum(bolus) / (n / STEPS_PER_DAY)

        # Loop behavior
        valid_nb = net_basal[~np.isnan(net_basal)]
        if len(valid_nb) > 100 and sched_basal > 0:
            compensation = np.mean(np.abs(valid_nb)) / sched_basal
            suspension_frac = np.mean(valid_nb <= 0.05)
            pct_increasing = np.mean(valid_nb > sched_basal * 0.1)
        else:
            compensation = 0
            suspension_frac = 1.0
            pct_increasing = 0

        # IOB patterns
        valid_iob = iob[~np.isnan(iob)]
        mean_iob = np.mean(valid_iob) if len(valid_iob) > 0 else 0
        max_iob = np.percentile(valid_iob, 95) if len(valid_iob) > 0 else 0

        # Hypo events
        in_hypo = False
        hypo_count = 0
        for i in range(1, n):
            if not np.isnan(glucose[i]) and glucose[i] < 70 and not in_hypo:
                hypo_count += 1
                in_hypo = True
            elif not np.isnan(glucose[i]) and glucose[i] >= 80:
                in_hypo = False
        hypo_per_week = hypo_count / (n / STEPS_PER_DAY) * 7

        # Insulin sensitivity indicators
        total_daily_insulin = total_daily_bolus + sched_basal * 24
        carb_insulin_ratio = total_daily_carbs / total_daily_insulin if total_daily_insulin > 0 else 0

        features = {
            'patient': pid,
            'isf': float(isf),
            'cr': float(cr),
            'basal': float(sched_basal),
            'tir': float(metrics['tir']),
            'tbr': float(metrics['tbr']),
            'tar': float(metrics['tar']),
            'cv': float(metrics['cv']),
            'glucose_mean': float(glucose_mean),
            'glucose_std': float(glucose_std),
            'trend_std': float(trend_std),
            'morning_tir': float(morning_tir_val),
            'evening_tir': float(evening_tir_val),
            'overnight_tir': float(overnight_tir_val),
            'dawn_rise': float(dawn_rise),
            'meals_per_day': float(meals_per_day),
            'mean_carbs': float(mean_carbs),
            'total_daily_carbs': float(total_daily_carbs),
            'boluses_per_day': float(boluses_per_day),
            'mean_bolus': float(mean_bolus),
            'total_daily_bolus': float(total_daily_bolus),
            'total_daily_insulin': float(total_daily_insulin),
            'compensation': float(compensation),
            'suspension_frac': float(suspension_frac),
            'pct_increasing': float(pct_increasing),
            'mean_iob': float(mean_iob),
            'max_iob_p95': float(max_iob),
            'hypo_per_week': float(hypo_per_week),
            'carb_insulin_ratio': float(carb_insulin_ratio),
        }

        print(f"  {pid}: TIR={metrics['tir']:.0f}% TBR={metrics['tbr']:.1f}% "
              f"dawn={dawn_rise:+.0f} meals/d={meals_per_day:.1f} "
              f"comp={compensation:.2f} hypo/wk={hypo_per_week:.1f}")

        results.append(features)

    if make_figures and HAS_MPL:
        # Feature correlation heatmap
        feature_names = [k for k in results[0].keys() if k != 'patient' and isinstance(results[0][k], (int, float))]
        data = np.array([[r[f] for f in feature_names] for r in results])

        # Normalize
        data_norm = (data - np.nanmean(data, axis=0)) / (np.nanstd(data, axis=0) + 1e-10)

        fig, ax = plt.subplots(figsize=(12, 10))
        # Simple correlation matrix
        corr = np.corrcoef(data_norm.T)
        corr = np.nan_to_num(corr)
        im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
        ax.set_xticks(range(len(feature_names)))
        ax.set_yticks(range(len(feature_names)))
        ax.set_xticklabels(feature_names, rotation=90, fontsize=6)
        ax.set_yticklabels(feature_names, fontsize=6)
        plt.colorbar(im)
        ax.set_title('Patient Feature Correlation Matrix')
        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig01-features.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"{len(results[0])-1}_FEATURES_{len(results)}_PATIENTS"
    print(f"\n  ✓ EXP-1991 verdict: {verdict}")

    return {
        'experiment': 'EXP-1991',
        'verdict': verdict,
        'per_patient': results,
        'feature_names': [k for k in results[0].keys() if k != 'patient']
    }


# ============================================================================
# EXP-1992: K-means Phenotype Clustering (Manual)
# ============================================================================

def exp_1992_phenotype_clustering(patients, features_result, make_figures=False):
    """Cluster patients into phenotypes using simple distance metrics."""
    print("\n" + "=" * 70)
    print("EXP-1992: Phenotype Clustering")
    print("=" * 70)

    per_patient = features_result['per_patient']

    # Select key features for clustering
    cluster_features = ['tir', 'tbr', 'cv', 'compensation', 'dawn_rise',
                        'meals_per_day', 'total_daily_insulin', 'hypo_per_week']

    data = np.array([[p[f] for f in cluster_features] for p in per_patient])
    pids = [p['patient'] for p in per_patient]

    # Normalize
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0) + 1e-10
    data_norm = (data - mean) / std

    # Simple k-means (k=3, manual implementation)
    np.random.seed(42)
    k = 3
    # Initialize centroids using k-means++ style
    centroids = [data_norm[np.random.randint(len(data_norm))]]
    for _ in range(k - 1):
        dists = np.array([min(np.sum((x - c) ** 2) for c in centroids) for x in data_norm])
        probs = dists / dists.sum()
        centroids.append(data_norm[np.random.choice(len(data_norm), p=probs)])
    centroids = np.array(centroids)

    for _ in range(50):  # iterations
        # Assign
        labels = np.array([np.argmin([np.sum((x - c) ** 2) for c in centroids]) for x in data_norm])
        # Update
        new_centroids = np.array([data_norm[labels == i].mean(axis=0) if (labels == i).sum() > 0 else centroids[i]
                                  for i in range(k)])
        if np.allclose(new_centroids, centroids):
            break
        centroids = new_centroids

    # Characterize clusters
    cluster_profiles = {}
    for i in range(k):
        members = [pids[j] for j in range(len(pids)) if labels[j] == i]
        cluster_data = data[labels == i]
        if len(cluster_data) == 0:
            continue

        profile = {f: float(np.mean(cluster_data[:, j])) for j, f in enumerate(cluster_features)}
        profile['members'] = members
        profile['n'] = len(members)

        # Name the cluster based on dominant characteristics
        if profile['tir'] > 80:
            name = 'WELL_CONTROLLED'
        elif profile['compensation'] > 1.0 or profile['cv'] > 40:
            name = 'STRUGGLING'
        else:
            name = 'MODERATE'

        cluster_profiles[name] = profile
        print(f"  Cluster {name} (n={len(members)}): {members}")
        print(f"    TIR={profile['tir']:.0f}% TBR={profile['tbr']:.1f}% "
              f"CV={profile['cv']:.0f}% comp={profile['compensation']:.2f}")

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: TIR vs CV colored by cluster
        colors = ['#2ecc71', '#f39c12', '#e74c3c']
        for i in range(k):
            mask = labels == i
            cluster_name = list(cluster_profiles.keys())[min(i, len(cluster_profiles) - 1)]
            axes[0].scatter(data[mask, 0], data[mask, 3],  # TIR vs CV
                          s=100, color=colors[i % 3], edgecolor='black',
                          label=cluster_name)
            for j in np.where(mask)[0]:
                axes[0].annotate(pids[j], (data[j, 0], data[j, 3]),
                               fontsize=8, ha='center', va='bottom')
        axes[0].set_xlabel('TIR (%)')
        axes[0].set_ylabel('Compensation')
        axes[0].set_title('Patient Phenotypes: TIR vs Loop Compensation')
        axes[0].legend()

        # Plot 2: Radar chart (simplified as parallel coordinates)
        for i in range(k):
            mask = labels == i
            cluster_name = list(cluster_profiles.keys())[min(i, len(cluster_profiles) - 1)]
            profile = np.mean(data_norm[mask], axis=0)
            axes[1].plot(range(len(cluster_features)), profile, 'o-',
                        color=colors[i % 3], label=cluster_name, linewidth=2)
        axes[1].set_xticks(range(len(cluster_features)))
        axes[1].set_xticklabels([f.replace('_', '\n') for f in cluster_features], fontsize=7)
        axes[1].set_ylabel('Normalized Value')
        axes[1].set_title('Cluster Profiles')
        axes[1].legend()
        axes[1].axhline(0, color='black', linewidth=0.5)

        # Plot 3: TIR vs TBR with cluster colors
        for i in range(k):
            mask = labels == i
            cluster_name = list(cluster_profiles.keys())[min(i, len(cluster_profiles) - 1)]
            axes[2].scatter(data[mask, 0], data[mask, 1],  # TIR vs TBR
                          s=100, color=colors[i % 3], edgecolor='black',
                          label=cluster_name)
            for j in np.where(mask)[0]:
                axes[2].annotate(pids[j], (data[j, 0], data[j, 1]),
                               fontsize=8, ha='center', va='bottom')
        axes[2].set_xlabel('TIR (%)')
        axes[2].set_ylabel('TBR (%)')
        axes[2].set_title('TIR vs Hypo Risk by Phenotype')
        axes[2].legend()

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig02-clusters.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"{len(cluster_profiles)}_PHENOTYPES_{k}_CLUSTERS"
    print(f"\n  ✓ EXP-1992 verdict: {verdict}")

    return {
        'experiment': 'EXP-1992',
        'verdict': verdict,
        'cluster_profiles': {k: {kk: vv for kk, vv in v.items()} for k, v in cluster_profiles.items()},
        'patient_labels': {pids[i]: int(labels[i]) for i in range(len(pids))},
        'cluster_features': cluster_features
    }


# ============================================================================
# EXP-1993: Phenotype-Specific Algorithm Strategy
# ============================================================================

def exp_1993_phenotype_strategy(patients, cluster_result, make_figures=False):
    """Map each phenotype to its optimal algorithm strategy."""
    print("\n" + "=" * 70)
    print("EXP-1993: Phenotype-Specific Algorithm Strategy")
    print("=" * 70)

    clusters = cluster_result['cluster_profiles']
    patient_labels = cluster_result['patient_labels']

    strategies = {}
    for cluster_name, profile in clusters.items():
        members = profile['members']

        # Determine optimal strategy based on profile
        strategy = {
            'cluster': cluster_name,
            'members': members,
            'n': len(members),
        }

        tir = profile['tir']
        tbr = profile['tbr']
        comp = profile['compensation']
        cv = profile['cv']
        dawn = profile.get('dawn_rise', 0)
        hypo = profile.get('hypo_per_week', 0)

        priorities = []

        # Safety first
        if tbr > 4:
            priorities.append({
                'priority': 1,
                'action': 'Reduce TBR',
                'method': 'Reduce basal, widen target range low end',
                'expected_impact': 'TBR reduction'
            })

        # Then compensation reduction
        if comp > 1.0:
            priorities.append({
                'priority': 2,
                'action': 'Reduce loop compensation',
                'method': 'Adjust basal profile to match delivery pattern',
                'expected_impact': 'Compensation <1.0 U/h'
            })

        # Then TIR improvement
        if tir < 70:
            if dawn > 15:
                priorities.append({
                    'priority': 3,
                    'action': 'Address dawn phenomenon',
                    'method': 'Proactive dawn basal ramp 3-6AM',
                    'expected_impact': '+2-5pp morning TIR'
                })
            if cv > 35:
                priorities.append({
                    'priority': 4,
                    'action': 'Reduce variability',
                    'method': 'Meal announcement, pre-bolus timing guidance',
                    'expected_impact': 'CV reduction'
                })
        elif tir >= 70:
            if tbr > 3:
                priorities.append({
                    'priority': 3,
                    'action': 'Reduce hypo while maintaining TIR',
                    'method': 'Conservative basal reduction, wider low target',
                    'expected_impact': 'TBR <3% without TIR loss'
                })

        # Meal optimization for everyone
        priorities.append({
            'priority': len(priorities) + 1,
            'action': 'Meal-size adaptive dosing',
            'method': 'Scale insulin delivery to estimated meal size',
            'expected_impact': 'Reduced spikes for large meals, reduced overshoot for small'
        })

        strategy['priorities'] = priorities

        print(f"  {cluster_name}: {members}")
        for pr in priorities:
            print(f"    #{pr['priority']}: {pr['action']} → {pr['expected_impact']}")

        strategies[cluster_name] = strategy

    if make_figures and HAS_MPL:
        fig, ax = plt.subplots(figsize=(14, 8))

        y_pos = 0
        colors = {'WELL_CONTROLLED': '#2ecc71', 'MODERATE': '#f39c12', 'STRUGGLING': '#e74c3c'}

        for cluster_name, strategy in strategies.items():
            color = colors.get(cluster_name, '#3498db')
            ax.barh(y_pos, len(strategy['priorities']), color=color, height=0.8, alpha=0.7)
            ax.text(-0.5, y_pos, f"{cluster_name}\n({', '.join(strategy['members'])})",
                   ha='right', va='center', fontsize=8, fontweight='bold')

            for i, pr in enumerate(strategy['priorities']):
                ax.text(i + 0.5, y_pos, f"#{pr['priority']}: {pr['action'][:20]}",
                       ha='center', va='center', fontsize=7, color='white', fontweight='bold')
            y_pos += 1

        ax.set_xlabel('Number of Priorities')
        ax.set_title('Phenotype-Specific Algorithm Strategies')
        ax.set_yticks([])
        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig03-strategies.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"{len(strategies)}_STRATEGIES"
    print(f"\n  ✓ EXP-1993 verdict: {verdict}")

    return {
        'experiment': 'EXP-1993',
        'verdict': verdict,
        'strategies': strategies
    }


# ============================================================================
# EXP-1994: Glycemic Variability Decomposition
# ============================================================================

def exp_1994_variability_decomposition(patients, make_figures=False):
    """Decompose glucose variability into meal-related, overnight, and residual."""
    print("\n" + "=" * 70)
    print("EXP-1994: Glycemic Variability Decomposition")
    print("=" * 70)

    results = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values
        n = len(glucose)

        valid_g = glucose[~np.isnan(glucose)]
        total_var = np.var(valid_g) if len(valid_g) > 100 else np.nan

        # Meal-related variance (within 3h of carb entry ≥ 5g)
        meal_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            if carbs[i] >= 5:
                meal_mask[max(0, i):min(n, i + 36)] = True

        meal_glucose = glucose[meal_mask & ~np.isnan(glucose)]
        non_meal_glucose = glucose[~meal_mask & ~np.isnan(glucose)]

        meal_var = np.var(meal_glucose) if len(meal_glucose) > 100 else 0
        non_meal_var = np.var(non_meal_glucose) if len(non_meal_glucose) > 100 else 0

        # Overnight variance (22:00-06:00)
        overnight_mask = np.array([hour_of_day(i) >= 22 or hour_of_day(i) < 6 for i in range(n)])
        daytime_mask = ~overnight_mask

        overnight_glucose = glucose[overnight_mask & ~np.isnan(glucose)]
        daytime_glucose = glucose[daytime_mask & ~np.isnan(glucose)]

        overnight_var = np.var(overnight_glucose) if len(overnight_glucose) > 100 else 0
        daytime_var = np.var(daytime_glucose) if len(daytime_glucose) > 100 else 0

        # Compute fractions
        meal_frac = len(meal_glucose) / (len(meal_glucose) + len(non_meal_glucose)) if len(meal_glucose) + len(non_meal_glucose) > 0 else 0
        pct_meal_time = meal_frac * 100

        # Weighted variance contributions
        if total_var and total_var > 0:
            meal_contribution = (meal_var * meal_frac) / total_var * 100
            non_meal_contribution = (non_meal_var * (1 - meal_frac)) / total_var * 100
            overnight_frac = len(overnight_glucose) / len(valid_g) if len(valid_g) > 0 else 0
            overnight_contribution = (overnight_var * overnight_frac) / total_var * 100
        else:
            meal_contribution = non_meal_contribution = overnight_contribution = 0

        print(f"  {pid}: total_var={total_var:.0f} meal={meal_contribution:.0f}% "
              f"non-meal={non_meal_contribution:.0f}% overnight={overnight_contribution:.0f}% "
              f"meal_time={pct_meal_time:.0f}%")

        results.append({
            'patient': pid,
            'total_variance': float(total_var) if not np.isnan(total_var) else 0,
            'meal_variance': float(meal_var),
            'non_meal_variance': float(non_meal_var),
            'overnight_variance': float(overnight_var),
            'daytime_variance': float(daytime_var),
            'meal_contribution_pct': float(meal_contribution),
            'non_meal_contribution_pct': float(non_meal_contribution),
            'overnight_contribution_pct': float(overnight_contribution),
            'pct_meal_time': float(pct_meal_time)
        })

    # Population averages
    pop_meal = np.mean([r['meal_contribution_pct'] for r in results])
    pop_nonmeal = np.mean([r['non_meal_contribution_pct'] for r in results])
    pop_overnight = np.mean([r['overnight_contribution_pct'] for r in results])

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Stacked bar of variance decomposition
        pids = [r['patient'] for r in results]
        meal_vals = [r['meal_contribution_pct'] for r in results]
        nonmeal_vals = [r['non_meal_contribution_pct'] for r in results]
        x = range(len(results))

        axes[0].bar(x, meal_vals, label='Meal-related', color='#e74c3c')
        axes[0].bar(x, nonmeal_vals, bottom=meal_vals, label='Non-meal', color='#3498db')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(pids)
        axes[0].set_ylabel('Variance Contribution (%)')
        axes[0].set_title('Glucose Variance Decomposition')
        axes[0].legend()

        # Plot 2: Overnight vs daytime variance
        overnight_vars = [r['overnight_variance'] for r in results]
        daytime_vars = [r['daytime_variance'] for r in results]
        axes[1].scatter(daytime_vars, overnight_vars, s=80, c='steelblue', edgecolor='black')
        for r in results:
            axes[1].annotate(r['patient'], (r['daytime_variance'], r['overnight_variance']),
                           fontsize=8, ha='center', va='bottom')
        max_val = max(max(daytime_vars), max(overnight_vars)) * 1.1
        axes[1].plot([0, max_val], [0, max_val], 'k--', alpha=0.3, label='Equal')
        axes[1].set_xlabel('Daytime Variance')
        axes[1].set_ylabel('Overnight Variance')
        axes[1].set_title('Daytime vs Overnight Variability')
        axes[1].legend()

        # Plot 3: Meal time fraction vs meal variance contribution
        axes[2].scatter([r['pct_meal_time'] for r in results],
                       [r['meal_contribution_pct'] for r in results],
                       s=80, c='#e74c3c', edgecolor='black')
        for r in results:
            axes[2].annotate(r['patient'], (r['pct_meal_time'], r['meal_contribution_pct']),
                           fontsize=8, ha='center', va='bottom')
        axes[2].set_xlabel('Time in Meal Window (%)')
        axes[2].set_ylabel('Meal Variance Contribution (%)')
        axes[2].set_title('Meal Time vs Meal Variance')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig04-variability.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"MEAL_{pop_meal:.0f}%_NONMEAL_{pop_nonmeal:.0f}%_OVERNIGHT_{pop_overnight:.0f}%"
    print(f"\n  ✓ EXP-1994 verdict: {verdict}")

    return {
        'experiment': 'EXP-1994',
        'verdict': verdict,
        'per_patient': results,
        'population_meal_contribution': float(pop_meal),
        'population_nonmeal_contribution': float(pop_nonmeal),
        'population_overnight_contribution': float(pop_overnight)
    }


# ============================================================================
# EXP-1995: Insulin Sensitivity Circadian Profile
# ============================================================================

def exp_1995_circadian_isf(patients, make_figures=False):
    """Measure effective insulin sensitivity by time of day."""
    print("\n" + "=" * 70)
    print("EXP-1995: Insulin Sensitivity Circadian Profile")
    print("=" * 70)

    results = []
    all_hourly_isf = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values
        isf_profile = get_isf(df)
        n = len(glucose)

        # Estimate effective ISF by hour:
        # After a bolus event, measure glucose drop over 2 hours
        hourly_isf = np.full(24, np.nan)
        hourly_samples = {h: [] for h in range(24)}

        bolus_idx = np.where(bolus >= 0.5)[0]  # significant boluses

        for bi in bolus_idx:
            h = int(hour_of_day(bi))
            if h >= 24:
                h = 23
            if bi + 24 >= n or bi < 6:
                continue

            # Glucose at bolus time and 2h later
            g_pre = glucose[bi]
            g_post = glucose[bi + 24]  # 2 hours later
            if np.isnan(g_pre) or np.isnan(g_post):
                continue

            # Only look at corrections (pre-meal glucose > 120, no carbs within 1h)
            carbs_col = df['carbs'].values
            carbs_nearby = np.nansum(carbs_col[max(0, bi - 6):min(n, bi + 6)])
            if carbs_nearby > 5:
                continue  # meal bolus, skip
            if g_pre < 120:
                continue  # not a clear correction

            drop = g_pre - g_post
            dose = bolus[bi]
            effective_isf = drop / dose if dose > 0 else np.nan
            if not np.isnan(effective_isf) and 10 < effective_isf < 300:
                hourly_samples[h].append(effective_isf)

        for h in range(24):
            if hourly_samples[h]:
                hourly_isf[h] = np.median(hourly_samples[h])

        # Fill gaps with interpolation
        valid = ~np.isnan(hourly_isf)
        if valid.sum() >= 3:
            valid_hours = np.where(valid)[0]
            valid_vals = hourly_isf[valid]
            hourly_isf_interp = np.interp(np.arange(24), valid_hours, valid_vals)
        else:
            hourly_isf_interp = np.full(24, isf_profile)

        # Circadian ratio
        morning_isf = np.mean(hourly_isf_interp[6:10])
        afternoon_isf = np.mean(hourly_isf_interp[12:16])
        evening_isf = np.mean(hourly_isf_interp[18:22])
        overnight_isf = np.mean(hourly_isf_interp[0:6])

        total_samples = sum(len(v) for v in hourly_samples.values())
        ratio = morning_isf / evening_isf if evening_isf > 0 else np.nan

        print(f"  {pid}: profile_isf={isf_profile:.0f} morning={morning_isf:.0f} "
              f"evening={evening_isf:.0f} ratio={ratio:.2f} n={total_samples}")

        results.append({
            'patient': pid,
            'profile_isf': float(isf_profile),
            'hourly_isf': hourly_isf_interp.tolist(),
            'morning_isf': float(morning_isf),
            'afternoon_isf': float(afternoon_isf),
            'evening_isf': float(evening_isf),
            'overnight_isf': float(overnight_isf),
            'morning_evening_ratio': float(ratio) if not np.isnan(ratio) else None,
            'n_samples': total_samples
        })
        all_hourly_isf.append(hourly_isf_interp)

    # Population
    pop_ratio = np.nanmean([r['morning_evening_ratio'] for r in results if r['morning_evening_ratio'] is not None])
    pop_hourly = np.nanmean(all_hourly_isf, axis=0)

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        hours = np.arange(24)
        for i, r in enumerate(results):
            axes[0].plot(hours, r['hourly_isf'], alpha=0.4, linewidth=1)
        axes[0].plot(hours, pop_hourly, 'k-', linewidth=2, label='Population mean')
        axes[0].set_xlabel('Hour of Day')
        axes[0].set_ylabel('Effective ISF (mg/dL per unit)')
        axes[0].set_title('Circadian Insulin Sensitivity')
        axes[0].legend()
        axes[0].set_xticks(range(0, 24, 3))

        # Morning/evening ratio
        ratios = [r['morning_evening_ratio'] for r in results if r['morning_evening_ratio'] is not None]
        pids = [r['patient'] for r in results if r['morning_evening_ratio'] is not None]
        axes[1].bar(range(len(ratios)), ratios, color=['#e74c3c' if r < 0.8 else '#2ecc71' if r > 1.2 else '#f39c12' for r in ratios])
        axes[1].set_xticks(range(len(pids)))
        axes[1].set_xticklabels(pids)
        axes[1].set_ylabel('Morning/Evening ISF Ratio')
        axes[1].set_title('Circadian ISF Ratio by Patient')
        axes[1].axhline(1.0, color='black', linestyle='--', alpha=0.5)

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig05-circadian-isf.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"MORNING_EVENING_RATIO_{pop_ratio:.2f}"
    print(f"\n  ✓ EXP-1995 verdict: {verdict}")

    return {
        'experiment': 'EXP-1995',
        'verdict': verdict,
        'per_patient': results,
        'population_ratio': float(pop_ratio),
        'population_hourly_isf': pop_hourly.tolist()
    }


# ============================================================================
# EXP-1996: Carb Absorption Speed Profiling
# ============================================================================

def exp_1996_carb_absorption_speed(patients, make_figures=False):
    """Profile carb absorption speed per patient from post-meal glucose rise."""
    print("\n" + "=" * 70)
    print("EXP-1996: Carb Absorption Speed Profiling")
    print("=" * 70)

    results = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values
        n = len(glucose)

        # Find meal events with bolus (to get clean absorption curves)
        meals = np.where(carbs >= 15)[0]  # substantial meals only
        peak_times = []
        rise_rates = []

        for meal_idx in meals:
            if meal_idx + 36 >= n:
                continue
            pre = glucose[meal_idx]
            if np.isnan(pre):
                continue

            # Find peak within 3 hours
            post = glucose[meal_idx:meal_idx + 36]
            valid_mask = ~np.isnan(post)
            if valid_mask.sum() < 10:
                continue

            peak_idx = np.nanargmax(post)
            peak_time_min = peak_idx * 5
            peak_val = post[peak_idx]
            spike = peak_val - pre

            if spike < 10:
                continue

            peak_times.append(peak_time_min)

            # Rise rate: spike / time to peak
            if peak_time_min > 0:
                rise_rate = spike / peak_time_min  # mg/dL per minute
                rise_rates.append(rise_rate)

        if peak_times:
            median_peak_time = np.median(peak_times)
            mean_rise_rate = np.mean(rise_rates) if rise_rates else 0
            pct_fast = np.mean(np.array(peak_times) < 45) * 100  # peak < 45min
            pct_slow = np.mean(np.array(peak_times) > 75) * 100  # peak > 75min
        else:
            median_peak_time = mean_rise_rate = pct_fast = pct_slow = 0

        # Classify absorption speed
        if median_peak_time < 45:
            speed = 'FAST'
        elif median_peak_time > 75:
            speed = 'SLOW'
        else:
            speed = 'MODERATE'

        print(f"  {pid}: n={len(peak_times)} peak={median_peak_time:.0f}min "
              f"rise={mean_rise_rate:.2f}mg/dL/min fast={pct_fast:.0f}% "
              f"slow={pct_slow:.0f}% → {speed}")

        results.append({
            'patient': pid,
            'n_meals': len(peak_times),
            'median_peak_time_min': float(median_peak_time),
            'mean_rise_rate': float(mean_rise_rate),
            'pct_fast_absorption': float(pct_fast),
            'pct_slow_absorption': float(pct_slow),
            'absorption_speed': speed
        })

    # Population
    pop_peak = np.mean([r['median_peak_time_min'] for r in results])
    speed_counts = {}
    for r in results:
        s = r['absorption_speed']
        speed_counts[s] = speed_counts.get(s, 0) + 1

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Plot 1: Peak time distribution
        pids = [r['patient'] for r in results]
        peaks = [r['median_peak_time_min'] for r in results]
        colors = ['#e74c3c' if r['absorption_speed'] == 'FAST'
                  else '#2ecc71' if r['absorption_speed'] == 'SLOW'
                  else '#f39c12' for r in results]
        axes[0].bar(range(len(results)), peaks, color=colors)
        axes[0].set_xticks(range(len(results)))
        axes[0].set_xticklabels(pids)
        axes[0].set_ylabel('Median Time to Peak (min)')
        axes[0].set_title('Carb Absorption Speed by Patient')
        axes[0].axhline(45, color='red', linestyle='--', alpha=0.5, label='Fast threshold')
        axes[0].axhline(75, color='green', linestyle='--', alpha=0.5, label='Slow threshold')
        axes[0].legend()

        # Plot 2: Fast vs slow % per patient
        fast = [r['pct_fast_absorption'] for r in results]
        slow = [r['pct_slow_absorption'] for r in results]
        x = np.arange(len(results))
        axes[1].bar(x - 0.15, fast, 0.3, label='Fast (<45min)', color='#e74c3c')
        axes[1].bar(x + 0.15, slow, 0.3, label='Slow (>75min)', color='#2ecc71')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(pids)
        axes[1].set_ylabel('% of Meals')
        axes[1].set_title('Fast vs Slow Absorption Fraction')
        axes[1].legend()

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig06-absorption-speed.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"POP_PEAK_{pop_peak:.0f}min_FAST={speed_counts.get('FAST',0)}_MODERATE={speed_counts.get('MODERATE',0)}_SLOW={speed_counts.get('SLOW',0)}"
    print(f"\n  ✓ EXP-1996 verdict: {verdict}")

    return {
        'experiment': 'EXP-1996',
        'verdict': verdict,
        'per_patient': results,
        'population_peak_time': float(pop_peak),
        'speed_distribution': speed_counts
    }


# ============================================================================
# EXP-1997: Cross-Patient Transfer Analysis
# ============================================================================

def exp_1997_cross_patient_transfer(patients, features_result, make_figures=False):
    """Test whether corrections derived from one patient work for another."""
    print("\n" + "=" * 70)
    print("EXP-1997: Cross-Patient Transfer Analysis")
    print("=" * 70)

    per_patient = features_result['per_patient']
    pids = [p['patient'] for p in per_patient]

    # Feature vectors for similarity
    feat_keys = ['tir', 'cv', 'compensation', 'dawn_rise', 'meals_per_day',
                 'total_daily_insulin', 'hypo_per_week']
    data = np.array([[p[f] for f in feat_keys] for p in per_patient])
    data_norm = (data - np.mean(data, axis=0)) / (np.std(data, axis=0) + 1e-10)

    # Compute pairwise similarity
    n_patients = len(pids)
    similarity = np.zeros((n_patients, n_patients))
    for i in range(n_patients):
        for j in range(n_patients):
            similarity[i, j] = 1 / (1 + np.sqrt(np.sum((data_norm[i] - data_norm[j]) ** 2)))

    # For each patient, find most similar and most different
    results = []
    for i in range(n_patients):
        sims = similarity[i].copy()
        sims[i] = -1  # exclude self
        most_similar_idx = np.argmax(sims)
        sims[i] = 2
        most_different_idx = np.argmin(sims)

        # TIR comparison
        tir_i = per_patient[i]['tir']
        tir_similar = per_patient[most_similar_idx]['tir']
        tir_different = per_patient[most_different_idx]['tir']

        print(f"  {pids[i]}: most_similar={pids[most_similar_idx]} "
              f"(sim={similarity[i, most_similar_idx]:.2f}, TIR {tir_similar:.0f}%) "
              f"most_different={pids[most_different_idx]} "
              f"(sim={similarity[i, most_different_idx]:.2f}, TIR {tir_different:.0f}%)")

        results.append({
            'patient': pids[i],
            'most_similar': pids[most_similar_idx],
            'similarity': float(similarity[i, most_similar_idx]),
            'similar_tir': float(tir_similar),
            'most_different': pids[most_different_idx],
            'difference': float(similarity[i, most_different_idx]),
            'different_tir': float(tir_different)
        })

    # Overall transferability: correlation between similarity and TIR difference
    sim_vals = []
    tir_diffs = []
    for i in range(n_patients):
        for j in range(i + 1, n_patients):
            sim_vals.append(similarity[i, j])
            tir_diffs.append(abs(per_patient[i]['tir'] - per_patient[j]['tir']))

    transfer_corr = np.corrcoef(sim_vals, tir_diffs)[0, 1]

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Plot 1: Similarity heatmap
        im = axes[0].imshow(similarity, cmap='YlOrRd', vmin=0, vmax=1)
        axes[0].set_xticks(range(n_patients))
        axes[0].set_yticks(range(n_patients))
        axes[0].set_xticklabels(pids)
        axes[0].set_yticklabels(pids)
        plt.colorbar(im, ax=axes[0])
        axes[0].set_title('Patient Similarity Matrix')

        # Plot 2: Similarity vs TIR difference
        axes[1].scatter(sim_vals, tir_diffs, alpha=0.5, s=40, c='steelblue')
        axes[1].set_xlabel('Patient Similarity')
        axes[1].set_ylabel('|TIR Difference| (pp)')
        axes[1].set_title(f'Similarity vs TIR Gap (r={transfer_corr:.2f})')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig07-transfer.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"TRANSFER_r={transfer_corr:.2f}"
    print(f"\n  ✓ EXP-1997 verdict: {verdict}")

    return {
        'experiment': 'EXP-1997',
        'verdict': verdict,
        'per_patient': results,
        'transfer_correlation': float(transfer_corr),
        'similarity_matrix': similarity.tolist()
    }


# ============================================================================
# EXP-1998: Comprehensive Patient Report Cards
# ============================================================================

def exp_1998_report_cards(patients, all_results, make_figures=False):
    """Generate comprehensive per-patient report cards."""
    print("\n" + "=" * 70)
    print("EXP-1998: Comprehensive Patient Report Cards")
    print("=" * 70)

    features = all_results.get('EXP-1991', {}).get('per_patient', [])
    clusters = all_results.get('EXP-1992', {}).get('patient_labels', {})
    cluster_profiles = all_results.get('EXP-1992', {}).get('cluster_profiles', {})
    variability = {r['patient']: r for r in all_results.get('EXP-1994', {}).get('per_patient', [])}
    circadian = {r['patient']: r for r in all_results.get('EXP-1995', {}).get('per_patient', [])}
    absorption = {r['patient']: r for r in all_results.get('EXP-1996', {}).get('per_patient', [])}
    transfer = {r['patient']: r for r in all_results.get('EXP-1997', {}).get('per_patient', [])}

    report_cards = []

    for feat in features:
        pid = feat['patient']
        card = {
            'patient': pid,
            'phenotype': None,
            'glucose_control': {
                'tir': feat['tir'],
                'tbr': feat['tbr'],
                'tar': feat['tar'],
                'cv': feat['cv'],
                'ea1c': (feat['glucose_mean'] + 46.7) / 28.7 if feat['glucose_mean'] else None
            },
            'settings': {
                'isf': feat['isf'],
                'cr': feat['cr'],
                'basal': feat['basal']
            },
            'behavior': {
                'meals_per_day': feat['meals_per_day'],
                'mean_carbs': feat['mean_carbs'],
                'total_daily_carbs': feat['total_daily_carbs'],
                'boluses_per_day': feat['boluses_per_day']
            },
            'loop_performance': {
                'compensation': feat['compensation'],
                'suspension_frac': feat['suspension_frac'],
                'pct_increasing': feat['pct_increasing']
            },
            'safety': {
                'hypo_per_week': feat['hypo_per_week'],
                'tbr': feat['tbr']
            }
        }

        # Add cluster assignment
        cluster_idx = clusters.get(pid)
        if cluster_idx is not None:
            for name, profile in cluster_profiles.items():
                if pid in profile.get('members', []):
                    card['phenotype'] = name
                    break

        # Add variability decomposition
        if pid in variability:
            v = variability[pid]
            card['variability'] = {
                'meal_pct': v['meal_contribution_pct'],
                'non_meal_pct': v['non_meal_contribution_pct'],
                'overnight_pct': v['overnight_contribution_pct']
            }

        # Add circadian ISF
        if pid in circadian:
            c = circadian[pid]
            card['circadian_isf'] = {
                'morning': c['morning_isf'],
                'evening': c['evening_isf'],
                'ratio': c['morning_evening_ratio']
            }

        # Add absorption speed
        if pid in absorption:
            a = absorption[pid]
            card['absorption'] = {
                'speed': a['absorption_speed'],
                'peak_time_min': a['median_peak_time_min'],
                'pct_fast': a['pct_fast_absorption'],
                'pct_slow': a['pct_slow_absorption']
            }

        # Add transfer info
        if pid in transfer:
            t = transfer[pid]
            card['most_similar'] = t['most_similar']

        # Generate top-3 recommendations
        recommendations = []
        if feat['tbr'] > 5:
            recommendations.append('URGENT: Reduce TBR (currently {:.1f}%)'.format(feat['tbr']))
        if feat['compensation'] > 1.0:
            recommendations.append('Review settings: loop compensation {:.2f}x'.format(feat['compensation']))
        if feat.get('dawn_rise', 0) > 20:
            recommendations.append('Consider dawn basal ramp (rise {:.0f} mg/dL)'.format(feat['dawn_rise']))
        if feat['tir'] < 60:
            recommendations.append('TIR critically low ({:.0f}%): comprehensive settings review'.format(feat['tir']))
        if feat['meals_per_day'] > 5:
            recommendations.append('High meal frequency ({:.1f}/day): meal consolidation may help'.format(feat['meals_per_day']))

        card['recommendations'] = recommendations[:3]

        # Overall grade
        if feat['tir'] >= 80 and feat['tbr'] < 4:
            grade = 'A'
        elif feat['tir'] >= 70 and feat['tbr'] < 5:
            grade = 'B'
        elif feat['tir'] >= 60:
            grade = 'C'
        else:
            grade = 'D'
        card['grade'] = grade

        print(f"  {pid}: Grade={grade} phenotype={card['phenotype']} "
              f"TIR={feat['tir']:.0f}% TBR={feat['tbr']:.1f}% "
              f"recs={len(recommendations)}")

        report_cards.append(card)

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        # Plot 1: Grade distribution
        grades = [c['grade'] for c in report_cards]
        grade_counts = {g: grades.count(g) for g in ['A', 'B', 'C', 'D']}
        colors = {'A': '#2ecc71', 'B': '#3498db', 'C': '#f39c12', 'D': '#e74c3c'}
        axes[0, 0].bar(grade_counts.keys(), grade_counts.values(),
                       color=[colors[g] for g in grade_counts.keys()])
        axes[0, 0].set_ylabel('Count')
        axes[0, 0].set_title('Patient Grade Distribution')

        # Plot 2: TIR vs TBR with grades
        for card in report_cards:
            color = colors[card['grade']]
            axes[0, 1].scatter(card['glucose_control']['tir'],
                             card['glucose_control']['tbr'],
                             s=100, c=color, edgecolor='black')
            axes[0, 1].annotate(card['patient'],
                              (card['glucose_control']['tir'],
                               card['glucose_control']['tbr']),
                              fontsize=8, ha='center', va='bottom')
        axes[0, 1].set_xlabel('TIR (%)')
        axes[0, 1].set_ylabel('TBR (%)')
        axes[0, 1].set_title('TIR vs TBR by Grade')
        axes[0, 1].axhline(5, color='red', linestyle='--', alpha=0.5)
        axes[0, 1].axvline(70, color='green', linestyle='--', alpha=0.5)

        # Plot 3: Compensation vs TIR colored by phenotype
        phenotype_colors = {'WELL_CONTROLLED': '#2ecc71', 'MODERATE': '#f39c12', 'STRUGGLING': '#e74c3c'}
        for card in report_cards:
            color = phenotype_colors.get(card['phenotype'], '#999999')
            axes[1, 0].scatter(card['loop_performance']['compensation'],
                             card['glucose_control']['tir'],
                             s=100, c=color, edgecolor='black')
            axes[1, 0].annotate(card['patient'],
                              (card['loop_performance']['compensation'],
                               card['glucose_control']['tir']),
                              fontsize=8)
        axes[1, 0].set_xlabel('Loop Compensation')
        axes[1, 0].set_ylabel('TIR (%)')
        axes[1, 0].set_title('Compensation vs TIR by Phenotype')

        # Plot 4: Recommendation count by patient
        pids = [c['patient'] for c in report_cards]
        rec_counts = [len(c['recommendations']) for c in report_cards]
        rec_colors = [colors[c['grade']] for c in report_cards]
        axes[1, 1].bar(range(len(report_cards)), rec_counts, color=rec_colors)
        axes[1, 1].set_xticks(range(len(report_cards)))
        axes[1, 1].set_xticklabels(pids)
        axes[1, 1].set_ylabel('# Recommendations')
        axes[1, 1].set_title('Action Items per Patient')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'pheno-fig08-report-cards.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    # Summary
    grade_dist = {g: sum(1 for c in report_cards if c['grade'] == g) for g in ['A', 'B', 'C', 'D']}
    verdict = f"A={grade_dist['A']}_B={grade_dist['B']}_C={grade_dist['C']}_D={grade_dist['D']}"
    print(f"\n  ✓ EXP-1998 verdict: {verdict}")

    return {
        'experiment': 'EXP-1998',
        'verdict': verdict,
        'report_cards': report_cards,
        'grade_distribution': grade_dist
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1991–1998: Patient Phenotyping')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    os.makedirs(FIGURES_DIR, exist_ok=True)

    all_results = {}

    # EXP-1991: Feature extraction (foundation for all others)
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1991")
    print(f"{'#' * 70}")
    features = exp_1991_feature_extraction(patients, make_figures=args.figures)
    all_results['EXP-1991'] = features

    # EXP-1992: Clustering
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1992")
    print(f"{'#' * 70}")
    clusters = exp_1992_phenotype_clustering(patients, features, make_figures=args.figures)
    all_results['EXP-1992'] = clusters

    # EXP-1993: Strategies
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1993")
    print(f"{'#' * 70}")
    all_results['EXP-1993'] = exp_1993_phenotype_strategy(patients, clusters, make_figures=args.figures)

    # EXP-1994: Variability decomposition
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1994")
    print(f"{'#' * 70}")
    all_results['EXP-1994'] = exp_1994_variability_decomposition(patients, make_figures=args.figures)

    # EXP-1995: Circadian ISF
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1995")
    print(f"{'#' * 70}")
    all_results['EXP-1995'] = exp_1995_circadian_isf(patients, make_figures=args.figures)

    # EXP-1996: Absorption speed
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1996")
    print(f"{'#' * 70}")
    all_results['EXP-1996'] = exp_1996_carb_absorption_speed(patients, make_figures=args.figures)

    # EXP-1997: Transfer analysis
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1997")
    print(f"{'#' * 70}")
    all_results['EXP-1997'] = exp_1997_cross_patient_transfer(patients, features, make_figures=args.figures)

    # EXP-1998: Report cards
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1998")
    print(f"{'#' * 70}")
    all_results['EXP-1998'] = exp_1998_report_cards(patients, all_results, make_figures=args.figures)

    # Summary
    print("\n" + "=" * 70)
    print("SYNTHESIS: Patient Phenotyping")
    print("=" * 70)
    for exp_id in sorted(all_results.keys()):
        print(f"  {exp_id}: {all_results[exp_id]['verdict']}")

    with open(RESULTS_FILE, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)


if __name__ == '__main__':
    main()
