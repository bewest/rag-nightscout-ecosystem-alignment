#!/usr/bin/env python3
"""
EXP-2171–2178: Patient Phenotyping & Comprehensive Therapy Profiles

Synthesize all prior findings into actionable per-patient profiles combining
metabolic phenotype, therapy adequacy, risk stratification, and recommendations.

EXP-2171: Metabolic phenotype clustering — group patients by glycemic behavior
EXP-2172: Therapy adequacy scorecard — multi-dimensional ISF/CR/basal/overnight
EXP-2173: Risk stratification — composite safety score per patient
EXP-2174: Temporal stability analysis — how consistent are phenotypes over time?
EXP-2175: Intervention priority matrix — rank interventions by patient × impact
EXP-2176: Cross-metric correlations — which metrics predict which outcomes?
EXP-2177: Patient similarity network — who responds similarly to therapy?
EXP-2178: Comprehensive profile cards — actionable per-patient summary

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

patients = load_patients(PATIENT_DIR)


def get_profile_value(schedule, hour):
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    result = sorted_sched[0].get('value', None)
    target_seconds = hour * 3600
    for entry in sorted_sched:
        if entry.get('timeAsSeconds', 0) <= target_seconds:
            result = entry.get('value', result)
    return result


def compute_patient_metrics(p):
    """Compute comprehensive metrics for a single patient."""
    df = p['df']
    g = df['glucose'].values
    n_days = len(g) // STEPS_PER_DAY
    valid = ~np.isnan(g)
    g_valid = g[valid]

    if len(g_valid) < 100:
        return None

    metrics = {}

    # Basic glucose stats
    metrics['mean_glucose'] = float(np.mean(g_valid))
    metrics['median_glucose'] = float(np.median(g_valid))
    metrics['std_glucose'] = float(np.std(g_valid))
    metrics['cv_glucose'] = float(np.std(g_valid) / np.mean(g_valid) * 100)

    # Time in range
    metrics['tir'] = float(np.mean((g_valid >= 70) & (g_valid <= 180)) * 100)
    metrics['tbr'] = float(np.mean(g_valid < 70) * 100)
    metrics['tbr_severe'] = float(np.mean(g_valid < 54) * 100)
    metrics['tar'] = float(np.mean(g_valid > 180) * 100)
    metrics['tar_severe'] = float(np.mean(g_valid > 250) * 100)

    # GMI (Glucose Management Indicator)
    metrics['gmi'] = 3.31 + 0.02392 * metrics['mean_glucose']

    # CGM coverage
    metrics['cgm_coverage'] = float(valid.sum() / len(g) * 100)

    # Hypo events (crossing below 70)
    hypo_count = 0
    severe_hypo = 0
    for i in range(1, len(g)):
        if not np.isnan(g[i]) and not np.isnan(g[i-1]):
            if g[i] < 70 and g[i-1] >= 70:
                hypo_count += 1
            if g[i] < 54 and g[i-1] >= 54:
                severe_hypo += 1
    metrics['hypo_events'] = hypo_count
    metrics['hypo_per_week'] = hypo_count / (n_days / 7)
    metrics['severe_hypo_events'] = severe_hypo
    metrics['severe_hypo_per_week'] = severe_hypo / (n_days / 7)

    # Glycemic variability
    diffs = np.diff(g_valid)
    metrics['mage'] = float(np.mean(np.abs(diffs[np.abs(diffs) > np.std(diffs)])))
    metrics['gri'] = float(np.std(diffs))  # Glucose rate of change variability

    # Overnight metrics
    overnight_g = []
    for d in range(n_days):
        start = d * STEPS_PER_DAY
        end = start + 6 * STEPS_PER_HOUR
        if end >= len(g):
            continue
        night = g[start:end]
        v = night[~np.isnan(night)]
        if len(v) > 10:
            overnight_g.extend(v.tolist())

    if overnight_g:
        og = np.array(overnight_g)
        metrics['overnight_mean'] = float(np.mean(og))
        metrics['overnight_cv'] = float(np.std(og) / np.mean(og) * 100)
        metrics['overnight_tir'] = float(np.mean((og >= 70) & (og <= 180)) * 100)
        metrics['overnight_tbr'] = float(np.mean(og < 70) * 100)

    # Daytime metrics (8am-10pm)
    daytime_g = []
    for d in range(n_days):
        start = d * STEPS_PER_DAY + 8 * STEPS_PER_HOUR
        end = d * STEPS_PER_DAY + 22 * STEPS_PER_HOUR
        if end >= len(g):
            continue
        day = g[start:end]
        v = day[~np.isnan(day)]
        if len(v) > 10:
            daytime_g.extend(v.tolist())

    if daytime_g:
        dg = np.array(daytime_g)
        metrics['daytime_mean'] = float(np.mean(dg))
        metrics['daytime_cv'] = float(np.std(dg) / np.mean(dg) * 100)

    # Meal response (post-bolus excursion)
    if 'bolus' in df.columns:
        bolus = df['bolus'].values
        meal_peaks = []
        for i in range(len(bolus)):
            if not np.isnan(bolus[i]) and bolus[i] > 0.5:
                # Look at 2h post-bolus peak
                window = g[i:min(i + 24, len(g))]  # 2 hours
                v = window[~np.isnan(window)]
                if len(v) > 5:
                    pre = g[i] if not np.isnan(g[i]) else np.nan
                    if not np.isnan(pre):
                        peak = float(np.max(v))
                        excursion = peak - pre
                        if excursion > 0:
                            meal_peaks.append(excursion)

        if meal_peaks:
            metrics['mean_meal_excursion'] = float(np.mean(meal_peaks))
            metrics['median_meal_excursion'] = float(np.median(meal_peaks))

    # AID delivery metrics
    has_rate = 'enacted_rate' in df.columns or 'temp_rate' in df.columns
    if has_rate:
        rate_col = 'enacted_rate' if 'enacted_rate' in df.columns else 'temp_rate'
        rates = df[rate_col].values
        valid_r = rates[~np.isnan(rates)]
        if len(valid_r) > 0:
            metrics['mean_delivery'] = float(np.mean(valid_r))
            metrics['zero_delivery_pct'] = float(np.mean(valid_r < 0.01) * 100)

    # ISF check
    isf_schedule = df.attrs.get('isf_schedule', [])
    if isf_schedule:
        isf_val = isf_schedule[0].get('value', None)
        if isf_val is not None:
            if isf_val < 15:  # mmol/L
                isf_val *= 18.0182
            metrics['profile_isf'] = float(isf_val)

    # CR check
    cr_schedule = df.attrs.get('cr_schedule', [])
    if cr_schedule:
        cr_val = cr_schedule[0].get('value', None)
        if cr_val is not None:
            metrics['profile_cr'] = float(cr_val)

    return metrics


# ── EXP-2171: Metabolic Phenotype Clustering ────────────────────────
def exp_2171_phenotype_clustering():
    """Group patients by glycemic behavior patterns."""
    print("\n═══ EXP-2171: Metabolic Phenotype Clustering ═══")

    all_metrics = {}
    for p in patients:
        m = compute_patient_metrics(p)
        if m:
            all_metrics[p['name']] = m

    # Define phenotype axes
    phenotypes = {}
    for name, m in all_metrics.items():
        # Axis 1: Glycemic control (TIR-based)
        if m['tir'] >= 80:
            control = 'excellent'
        elif m['tir'] >= 70:
            control = 'good'
        elif m['tir'] >= 55:
            control = 'moderate'
        else:
            control = 'poor'

        # Axis 2: Variability (CV-based)
        if m['cv_glucose'] < 25:
            variability = 'low'
        elif m['cv_glucose'] < 36:
            variability = 'moderate'
        else:
            variability = 'high'

        # Axis 3: Hypo risk
        if m['hypo_per_week'] < 1:
            hypo_risk = 'low'
        elif m['hypo_per_week'] < 3:
            hypo_risk = 'moderate'
        else:
            hypo_risk = 'high'

        # Axis 4: Overnight quality
        overnight_cv = m.get('overnight_cv', 30)
        if overnight_cv < 15:
            overnight = 'stable'
        elif overnight_cv < 25:
            overnight = 'moderate'
        else:
            overnight = 'volatile'

        phenotype = f"{control}_{variability}_{hypo_risk}_{overnight}"
        phenotypes[name] = {
            'control': control,
            'variability': variability,
            'hypo_risk': hypo_risk,
            'overnight': overnight,
            'phenotype': phenotype,
            'metrics': {k: v for k, v in m.items()
                        if isinstance(v, (int, float))}
        }

        print(f"  {name}: {control} control, {variability} variability, "
              f"{hypo_risk} hypo risk, {overnight} overnight "
              f"(TIR={m['tir']:.0f}%, CV={m['cv_glucose']:.0f}%, "
              f"hypo={m['hypo_per_week']:.1f}/wk)")

    with open(f'{EXP_DIR}/exp-2171_phenotypes.json', 'w') as f:
        json.dump(phenotypes, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and phenotypes:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        patient_names = sorted(phenotypes.keys())

        # Panel 1: TIR vs CV scatter with labels
        for pn in patient_names:
            m = phenotypes[pn]['metrics']
            color = {'excellent': 'green', 'good': 'limegreen',
                     'moderate': 'orange', 'poor': 'red'}[phenotypes[pn]['control']]
            axes[0, 0].scatter(m['cv_glucose'], m['tir'], s=100, c=color,
                               edgecolors='black', linewidth=0.5, zorder=3)
            axes[0, 0].annotate(pn, (m['cv_glucose'], m['tir']),
                                textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[0, 0].axhline(y=70, color='green', linestyle='--', alpha=0.3)
        axes[0, 0].axvline(x=36, color='red', linestyle='--', alpha=0.3)
        axes[0, 0].set_xlabel('Glucose CV (%)')
        axes[0, 0].set_ylabel('Time in Range (%)')
        axes[0, 0].set_title('Glycemic Control vs Variability')
        axes[0, 0].grid(True, alpha=0.3)

        # Panel 2: Hypo risk vs TBR
        for pn in patient_names:
            m = phenotypes[pn]['metrics']
            color = {'low': 'green', 'moderate': 'orange',
                     'high': 'red'}[phenotypes[pn]['hypo_risk']]
            axes[0, 1].scatter(m['tbr'], m['hypo_per_week'], s=100, c=color,
                               edgecolors='black', linewidth=0.5, zorder=3)
            axes[0, 1].annotate(pn, (m['tbr'], m['hypo_per_week']),
                                textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[0, 1].set_xlabel('Time Below Range (%)')
        axes[0, 1].set_ylabel('Hypos per Week')
        axes[0, 1].set_title('Hypo Frequency vs Time Below Range')
        axes[0, 1].grid(True, alpha=0.3)

        # Panel 3: Phenotype distribution
        controls = [phenotypes[pn]['control'] for pn in patient_names]
        from collections import Counter
        ctrl_counts = Counter(controls)
        axes[1, 0].pie(ctrl_counts.values(), labels=ctrl_counts.keys(),
                       colors=['green' if 'exc' in k else 'limegreen' if 'good' in k
                               else 'orange' if 'mod' in k else 'red'
                               for k in ctrl_counts.keys()],
                       autopct='%1.0f%%', startangle=90)
        axes[1, 0].set_title('Control Level Distribution')

        # Panel 4: Radar-like bar chart of key metrics
        metric_names = ['tir', 'tbr', 'tar', 'cv_glucose', 'hypo_per_week']
        metric_labels = ['TIR%', 'TBR%', 'TAR%', 'CV%', 'Hypo/wk']
        x = np.arange(len(metric_names))
        width = 0.08
        for pi, pn in enumerate(patient_names):
            vals = [phenotypes[pn]['metrics'].get(mn, 0) for mn in metric_names]
            axes[1, 1].bar(x + pi * width - len(patient_names) * width / 2,
                          vals, width, label=pn, alpha=0.8)
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels(metric_labels, fontsize=9)
        axes[1, 1].set_ylabel('Value')
        axes[1, 1].set_title('Key Metrics by Patient')
        axes[1, 1].legend(fontsize=6, ncol=3, loc='upper right')
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig01-clustering.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig01-clustering.png")

    return phenotypes


# ── EXP-2172: Therapy Adequacy Scorecard ────────────────────────────
def exp_2172_therapy_scorecard():
    """Multi-dimensional therapy adequacy assessment."""
    print("\n═══ EXP-2172: Therapy Adequacy Scorecard ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        m = compute_patient_metrics(p)
        if not m:
            continue

        # Score each dimension (0-100)
        scores = {}

        # TIR score: 70% → 100 points, <50% → 0
        scores['tir_score'] = min(100, max(0, (m['tir'] - 50) / (70 - 50) * 100))

        # TBR score: <1% → 100, >5% → 0
        scores['tbr_score'] = min(100, max(0, (5 - m['tbr']) / (5 - 1) * 100))

        # TAR score: <25% → 100, >50% → 0
        scores['tar_score'] = min(100, max(0, (50 - m['tar']) / (50 - 25) * 100))

        # CV score: <25% → 100, >40% → 0
        scores['cv_score'] = min(100, max(0, (40 - m['cv_glucose']) / (40 - 25) * 100))

        # Hypo score: <1/wk → 100, >5/wk → 0
        scores['hypo_score'] = min(100, max(0, (5 - m['hypo_per_week']) / (5 - 1) * 100))

        # Overnight score
        overnight_cv = m.get('overnight_cv', 30)
        scores['overnight_score'] = min(100, max(0, (30 - overnight_cv) / (30 - 10) * 100))

        # GMI score: <7% → 100, >8% → 0
        scores['gmi_score'] = min(100, max(0, (8 - m['gmi']) / (8 - 7) * 100))

        # Overall composite
        weights = {
            'tir_score': 0.25, 'tbr_score': 0.20, 'tar_score': 0.15,
            'cv_score': 0.10, 'hypo_score': 0.15, 'overnight_score': 0.10,
            'gmi_score': 0.05
        }
        composite = sum(scores[k] * weights[k] for k in weights)

        # Grade
        if composite >= 80:
            grade = 'A'
        elif composite >= 65:
            grade = 'B'
        elif composite >= 50:
            grade = 'C'
        elif composite >= 35:
            grade = 'D'
        else:
            grade = 'F'

        all_results[name] = {
            'scores': scores,
            'composite': float(composite),
            'grade': grade,
            'weakest': min(scores, key=scores.get),
            'strongest': max(scores, key=scores.get),
            'metrics': {k: v for k, v in m.items() if isinstance(v, (int, float))}
        }

        weakest_name = min(scores, key=scores.get).replace('_score', '')
        print(f"  {name}: Grade={grade} ({composite:.0f}/100), "
              f"weakest={weakest_name} ({min(scores.values()):.0f}), "
              f"TIR={m['tir']:.0f}% TBR={m['tbr']:.1f}% CV={m['cv_glucose']:.0f}%")

    with open(f'{EXP_DIR}/exp-2172_scorecard.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Composite scores with grades
        composites = [all_results[pn]['composite'] for pn in patient_names]
        grades = [all_results[pn]['grade'] for pn in patient_names]
        colors_g = {'A': 'green', 'B': 'limegreen', 'C': 'orange', 'D': 'red', 'F': 'darkred'}
        bar_colors = [colors_g[g] for g in grades]
        bars = axes[0].bar(patient_names, composites, color=bar_colors, alpha=0.8)
        for bi, bar in enumerate(bars):
            axes[0].text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1,
                         grades[bi], ha='center', va='bottom', fontsize=10, fontweight='bold')
        axes[0].set_ylabel('Composite Score')
        axes[0].set_title('Therapy Adequacy Score')
        axes[0].set_ylim(0, 110)
        axes[0].axhline(y=80, color='green', linestyle='--', alpha=0.3, label='A threshold')
        axes[0].axhline(y=50, color='orange', linestyle='--', alpha=0.3, label='C threshold')
        axes[0].legend(fontsize=7)
        axes[0].tick_params(axis='x', labelsize=8)

        # Panel 2: Heatmap of dimension scores
        dim_names = ['tir_score', 'tbr_score', 'tar_score', 'cv_score',
                     'hypo_score', 'overnight_score', 'gmi_score']
        dim_labels = ['TIR', 'TBR', 'TAR', 'CV', 'Hypo', 'Overnight', 'GMI']
        data = np.array([[all_results[pn]['scores'][d] for d in dim_names]
                         for pn in patient_names])
        im = axes[1].imshow(data.T, aspect='auto', cmap='RdYlGn', vmin=0, vmax=100)
        axes[1].set_xticks(range(len(patient_names)))
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_yticks(range(len(dim_labels)))
        axes[1].set_yticklabels(dim_labels, fontsize=8)
        axes[1].set_title('Score Heatmap')
        plt.colorbar(im, ax=axes[1], shrink=0.8)

        # Panel 3: Weakest dimension distribution
        from collections import Counter
        weakest = [all_results[pn]['weakest'].replace('_score', '') for pn in patient_names]
        weak_counts = Counter(weakest)
        axes[2].barh(list(weak_counts.keys()), list(weak_counts.values()),
                     color='coral', alpha=0.7)
        axes[2].set_xlabel('Number of Patients')
        axes[2].set_title('Most Common Weakest Dimension')
        axes[2].grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig02-scorecard.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig02-scorecard.png")

    return all_results


# ── EXP-2173: Risk Stratification ──────────────────────────────────
def exp_2173_risk_stratification():
    """Composite safety score per patient."""
    print("\n═══ EXP-2173: Risk Stratification ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        m = compute_patient_metrics(p)
        if not m:
            continue

        # Risk factors (higher = more risk)
        risks = {}

        # Hypo risk
        risks['hypo_frequency'] = min(10, m['hypo_per_week'])
        risks['severe_hypo'] = min(10, m['severe_hypo_per_week'] * 5)
        risks['tbr'] = min(10, m['tbr'] * 2)

        # Hyperglycemia risk
        risks['tar'] = min(10, m['tar'] / 5)
        risks['tar_severe'] = min(10, m['tar_severe'] / 2)

        # Variability risk
        risks['cv'] = min(10, max(0, (m['cv_glucose'] - 20) / 2))

        # Overnight risk
        overnight_tbr = m.get('overnight_tbr', 0)
        risks['overnight_hypo'] = min(10, overnight_tbr * 3)

        # Composite
        hypo_composite = (risks['hypo_frequency'] * 0.3 +
                          risks['severe_hypo'] * 0.4 +
                          risks['tbr'] * 0.3)
        hyper_composite = (risks['tar'] * 0.6 + risks['tar_severe'] * 0.4)
        variability_composite = risks['cv']
        overnight_composite = risks['overnight_hypo']

        overall = (hypo_composite * 0.4 + hyper_composite * 0.25 +
                   variability_composite * 0.15 + overnight_composite * 0.2)

        # Risk tier
        if overall >= 6:
            tier = 'CRITICAL'
        elif overall >= 4:
            tier = 'HIGH'
        elif overall >= 2:
            tier = 'MODERATE'
        else:
            tier = 'LOW'

        all_results[name] = {
            'risk_factors': risks,
            'hypo_composite': float(hypo_composite),
            'hyper_composite': float(hyper_composite),
            'variability_composite': float(variability_composite),
            'overnight_composite': float(overnight_composite),
            'overall_risk': float(overall),
            'tier': tier
        }

        print(f"  {name}: [{tier}] overall={overall:.1f}, "
              f"hypo={hypo_composite:.1f} hyper={hyper_composite:.1f} "
              f"var={variability_composite:.1f} overnight={overnight_composite:.1f}")

    with open(f'{EXP_DIR}/exp-2173_risk.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Overall risk with tiers
        risks = [all_results[pn]['overall_risk'] for pn in patient_names]
        tiers = [all_results[pn]['tier'] for pn in patient_names]
        tier_colors = {'CRITICAL': 'darkred', 'HIGH': 'red',
                       'MODERATE': 'orange', 'LOW': 'green'}
        bar_colors = [tier_colors[t] for t in tiers]
        bars = axes[0].bar(patient_names, risks, color=bar_colors, alpha=0.8)
        for bi, bar in enumerate(bars):
            axes[0].text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.1,
                         tiers[bi][:4], ha='center', va='bottom', fontsize=7, fontweight='bold')
        axes[0].set_ylabel('Overall Risk Score')
        axes[0].set_title('Risk Stratification')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Risk decomposition
        hypo_r = [all_results[pn]['hypo_composite'] for pn in patient_names]
        hyper_r = [all_results[pn]['hyper_composite'] for pn in patient_names]
        var_r = [all_results[pn]['variability_composite'] for pn in patient_names]
        night_r = [all_results[pn]['overnight_composite'] for pn in patient_names]
        x = np.arange(len(patient_names))
        w = 0.2
        axes[1].bar(x - 1.5*w, hypo_r, w, label='Hypo', color='red', alpha=0.7)
        axes[1].bar(x - 0.5*w, hyper_r, w, label='Hyper', color='orange', alpha=0.7)
        axes[1].bar(x + 0.5*w, var_r, w, label='Variability', color='purple', alpha=0.7)
        axes[1].bar(x + 1.5*w, night_r, w, label='Overnight', color='blue', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Risk Component')
        axes[1].set_title('Risk Decomposition')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Tier distribution
        from collections import Counter
        tier_counts = Counter(tiers)
        axes[2].pie(tier_counts.values(), labels=tier_counts.keys(),
                    colors=[tier_colors[t] for t in tier_counts.keys()],
                    autopct='%1.0f%%', startangle=90)
        axes[2].set_title('Risk Tier Distribution')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig03-risk.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig03-risk.png")

    return all_results


# ── EXP-2174: Temporal Stability Analysis ───────────────────────────
def exp_2174_temporal_stability():
    """How consistent are phenotypes over time?"""
    print("\n═══ EXP-2174: Temporal Stability Analysis ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        if n_days < 28:
            continue

        # Split into 2-week blocks
        block_size = 14  # days
        n_blocks = n_days // block_size
        block_metrics = []

        for b in range(n_blocks):
            start = b * block_size * STEPS_PER_DAY
            end = (b + 1) * block_size * STEPS_PER_DAY
            block_g = g[start:end]
            valid = block_g[~np.isnan(block_g)]

            if len(valid) < 100:
                continue

            tir = float(np.mean((valid >= 70) & (valid <= 180)) * 100)
            tbr = float(np.mean(valid < 70) * 100)
            cv = float(np.std(valid) / np.mean(valid) * 100)
            mean_g = float(np.mean(valid))

            block_metrics.append({
                'block': b,
                'tir': tir,
                'tbr': tbr,
                'cv': cv,
                'mean_glucose': mean_g
            })

        if len(block_metrics) < 3:
            continue

        # Compute stability (CV of metrics across blocks)
        tirs = [bm['tir'] for bm in block_metrics]
        tbrs = [bm['tbr'] for bm in block_metrics]
        cvs = [bm['cv'] for bm in block_metrics]
        means = [bm['mean_glucose'] for bm in block_metrics]

        tir_stability = float(np.std(tirs))
        tbr_stability = float(np.std(tbrs))
        cv_stability = float(np.std(cvs))
        mean_stability = float(np.std(means))

        # Trend detection (linear fit)
        blocks_x = np.arange(len(tirs))
        tir_slope = float(np.polyfit(blocks_x, tirs, 1)[0]) if len(tirs) >= 3 else 0
        mean_slope = float(np.polyfit(blocks_x, means, 1)[0]) if len(means) >= 3 else 0

        # Is patient improving or deteriorating?
        if tir_slope > 1:
            trend = 'improving'
        elif tir_slope < -1:
            trend = 'deteriorating'
        else:
            trend = 'stable'

        all_results[name] = {
            'n_blocks': len(block_metrics),
            'tir_std': tir_stability,
            'tbr_std': tbr_stability,
            'cv_std': cv_stability,
            'mean_glucose_std': mean_stability,
            'tir_slope_per_2wk': tir_slope,
            'mean_glucose_slope': mean_slope,
            'trend': trend,
            'block_metrics': block_metrics
        }

        print(f"  {name}: {trend}, TIR σ={tir_stability:.1f}pp, "
              f"slope={tir_slope:+.2f}pp/2wk, "
              f"glucose σ={mean_stability:.1f} mg/dL ({len(block_metrics)} blocks)")

    with open(f'{EXP_DIR}/exp-2174_stability.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: TIR over time for all patients
        for pn in patient_names:
            blocks = all_results[pn]['block_metrics']
            tirs = [bm['tir'] for bm in blocks]
            axes[0].plot(range(len(tirs)), tirs, '-o', label=pn, markersize=3, alpha=0.7)
        axes[0].axhline(y=70, color='green', linestyle='--', alpha=0.3)
        axes[0].set_xlabel('2-Week Block')
        axes[0].set_ylabel('TIR (%)')
        axes[0].set_title('TIR Stability Over Time')
        axes[0].legend(fontsize=7, ncol=2)
        axes[0].grid(True, alpha=0.3)

        # Panel 2: TIR variability
        tir_stds = [all_results[pn]['tir_std'] for pn in patient_names]
        colors_s = ['green' if s < 5 else 'orange' if s < 10 else 'red' for s in tir_stds]
        axes[1].bar(patient_names, tir_stds, color=colors_s, alpha=0.7)
        axes[1].set_ylabel('TIR Standard Deviation (pp)')
        axes[1].set_title('TIR Variability Across 2-Week Blocks')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Trend
        slopes = [all_results[pn]['tir_slope_per_2wk'] for pn in patient_names]
        colors_t = ['green' if s > 0.5 else 'red' if s < -0.5 else 'gray' for s in slopes]
        axes[2].bar(patient_names, slopes, color=colors_t, alpha=0.7)
        axes[2].axhline(y=0, color='black', linewidth=0.5)
        axes[2].set_ylabel('TIR Slope (pp per 2 weeks)')
        axes[2].set_title('Trend: Improving or Deteriorating?')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig04-stability.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig04-stability.png")

    return all_results


# ── EXP-2175: Intervention Priority Matrix ─────────────────────────
def exp_2175_intervention_matrix():
    """Rank interventions by patient × expected impact."""
    print("\n═══ EXP-2175: Intervention Priority Matrix ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        m = compute_patient_metrics(p)
        if not m:
            continue

        interventions = {}

        # 1. Reduce basal (if over-basaled → reduce hypos)
        if m['tbr'] > 2 or m['hypo_per_week'] > 2:
            interventions['reduce_basal'] = {
                'priority': 'HIGH' if m['tbr'] > 4 else 'MEDIUM',
                'expected_benefit': 'Reduce TBR and hypo frequency',
                'evidence': f"TBR={m['tbr']:.1f}%, hypo={m['hypo_per_week']:.1f}/wk"
            }

        # 2. Increase ISF (if ISF too aggressive → less correction hypo)
        if m['tbr'] > 1 and m.get('profile_isf', 100) < 80:
            interventions['increase_isf'] = {
                'priority': 'HIGH',
                'expected_benefit': 'Reduce correction overshoot',
                'evidence': f"ISF={m.get('profile_isf', 'N/A')}, TBR={m['tbr']:.1f}%"
            }

        # 3. Adjust CR (if high TAR → more aggressive CR)
        if m['tar'] > 30:
            interventions['adjust_cr'] = {
                'priority': 'MEDIUM',
                'expected_benefit': 'Reduce post-meal spikes',
                'evidence': f"TAR={m['tar']:.0f}%"
            }

        # 4. Pre-bolus timing (if high meal excursion)
        excursion = m.get('mean_meal_excursion', 0)
        if excursion > 50:
            interventions['pre_bolus'] = {
                'priority': 'MEDIUM',
                'expected_benefit': f'Reduce meal spikes by ~{excursion * 0.3:.0f} mg/dL',
                'evidence': f"Mean excursion={excursion:.0f} mg/dL"
            }

        # 5. Circadian basal (if high overnight TAR + dawn)
        overnight_mean = m.get('overnight_mean', 150)
        if overnight_mean > 160 and m.get('overnight_tir', 100) < 70:
            interventions['circadian_basal'] = {
                'priority': 'MEDIUM',
                'expected_benefit': 'Address dawn phenomenon',
                'evidence': f"Overnight mean={overnight_mean:.0f}, "
                            f"TIR={m.get('overnight_tir', 0):.0f}%"
            }

        # 6. Late dinner management (if high overnight hypos)
        if m.get('overnight_tbr', 0) > 3:
            interventions['dinner_management'] = {
                'priority': 'HIGH',
                'expected_benefit': 'Reduce nocturnal hypos',
                'evidence': f"Overnight TBR={m.get('overnight_tbr', 0):.1f}%"
            }

        # Overall recommendation
        if not interventions:
            priority = 'MAINTAIN'
        elif any(v['priority'] == 'HIGH' for v in interventions.values()):
            priority = 'ACT_NOW'
        else:
            priority = 'OPTIMIZE'

        all_results[name] = {
            'interventions': interventions,
            'n_interventions': len(interventions),
            'overall_priority': priority,
            'key_metrics': {
                'tir': m['tir'], 'tbr': m['tbr'], 'tar': m['tar'],
                'hypo_per_week': m['hypo_per_week'],
                'cv': m['cv_glucose']
            }
        }

        n_high = sum(1 for v in interventions.values() if v['priority'] == 'HIGH')
        print(f"  {name}: [{priority}] {len(interventions)} interventions "
              f"({n_high} HIGH priority)")

    with open(f'{EXP_DIR}/exp-2175_interventions.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Intervention count per patient
        counts = [all_results[pn]['n_interventions'] for pn in patient_names]
        priorities = [all_results[pn]['overall_priority'] for pn in patient_names]
        p_colors = {'ACT_NOW': 'red', 'OPTIMIZE': 'orange', 'MAINTAIN': 'green'}
        bar_colors = [p_colors.get(pr, 'gray') for pr in priorities]
        axes[0].bar(patient_names, counts, color=bar_colors, alpha=0.7)
        axes[0].set_ylabel('Number of Interventions')
        axes[0].set_title('Intervention Count by Patient')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Most common interventions
        from collections import Counter
        all_interventions = []
        for pn in patient_names:
            all_interventions.extend(all_results[pn]['interventions'].keys())
        int_counts = Counter(all_interventions)
        if int_counts:
            names_i = list(int_counts.keys())
            vals_i = list(int_counts.values())
            axes[1].barh(names_i, vals_i, color='steelblue', alpha=0.7)
            axes[1].set_xlabel('Number of Patients')
            axes[1].set_title('Intervention Frequency')
            axes[1].grid(True, alpha=0.3, axis='x')

        # Panel 3: Impact matrix heatmap
        int_types = sorted(set(all_interventions))
        matrix = np.zeros((len(patient_names), len(int_types)))
        for pi, pn in enumerate(patient_names):
            for ii, it in enumerate(int_types):
                if it in all_results[pn]['interventions']:
                    priority = all_results[pn]['interventions'][it]['priority']
                    matrix[pi, ii] = 2 if priority == 'HIGH' else 1

        if int_types:
            im = axes[2].imshow(matrix.T, aspect='auto', cmap='YlOrRd',
                                vmin=0, vmax=2)
            axes[2].set_xticks(range(len(patient_names)))
            axes[2].set_xticklabels(patient_names, fontsize=8)
            axes[2].set_yticks(range(len(int_types)))
            axes[2].set_yticklabels([it.replace('_', ' ') for it in int_types], fontsize=8)
            axes[2].set_title('Intervention Priority Matrix')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig05-interventions.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig05-interventions.png")

    return all_results


# ── EXP-2176: Cross-Metric Correlations ─────────────────────────────
def exp_2176_correlations():
    """Which metrics predict which outcomes?"""
    print("\n═══ EXP-2176: Cross-Metric Correlations ═══")

    all_metrics = {}
    for p in patients:
        m = compute_patient_metrics(p)
        if m:
            all_metrics[p['name']] = m

    metric_names = ['tir', 'tbr', 'tar', 'cv_glucose', 'hypo_per_week',
                    'mean_glucose', 'gmi']
    optional_metrics = ['overnight_cv', 'overnight_tir', 'daytime_cv']

    # Build correlation matrix
    n_patients = len(all_metrics)
    all_metric_names = metric_names + [m for m in optional_metrics
                                       if all(m in all_metrics[pn] for pn in all_metrics)]

    data_matrix = []
    patient_names = sorted(all_metrics.keys())
    for pn in patient_names:
        row = [all_metrics[pn].get(mn, np.nan) for mn in all_metric_names]
        data_matrix.append(row)

    data = np.array(data_matrix)

    # Compute correlations
    n_metrics = len(all_metric_names)
    corr_matrix = np.zeros((n_metrics, n_metrics))
    for i in range(n_metrics):
        for j in range(n_metrics):
            x = data[:, i]
            y = data[:, j]
            valid = ~np.isnan(x) & ~np.isnan(y)
            if valid.sum() >= 3:
                corr_matrix[i, j] = float(np.corrcoef(x[valid], y[valid])[0, 1])

    # Find strongest correlations
    strong = []
    for i in range(n_metrics):
        for j in range(i + 1, n_metrics):
            r = corr_matrix[i, j]
            if abs(r) > 0.5:
                strong.append({
                    'metric1': all_metric_names[i],
                    'metric2': all_metric_names[j],
                    'r': float(r)
                })

    strong.sort(key=lambda x: abs(x['r']), reverse=True)

    results = {
        'correlation_matrix': corr_matrix.tolist(),
        'metric_names': all_metric_names,
        'strong_correlations': strong,
        'n_patients': n_patients
    }

    for s in strong[:8]:
        print(f"  {s['metric1']} ↔ {s['metric2']}: r={s['r']:.3f}")

    with open(f'{EXP_DIR}/exp-2176_correlations.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        # Panel 1: Full correlation heatmap
        short_names = [mn.replace('_glucose', '').replace('_per_week', '/wk')
                       .replace('overnight_', 'O.') for mn in all_metric_names]
        im = axes[0].imshow(corr_matrix, cmap='RdBu_r', vmin=-1, vmax=1)
        axes[0].set_xticks(range(n_metrics))
        axes[0].set_xticklabels(short_names, fontsize=7, rotation=45, ha='right')
        axes[0].set_yticks(range(n_metrics))
        axes[0].set_yticklabels(short_names, fontsize=7)
        axes[0].set_title('Metric Correlations')
        plt.colorbar(im, ax=axes[0], shrink=0.8)

        # Panel 2: Top correlations
        if strong:
            top = strong[:10]
            labels = [f"{s['metric1'][:8]}↔{s['metric2'][:8]}" for s in top]
            values = [s['r'] for s in top]
            colors = ['blue' if v > 0 else 'red' for v in values]
            axes[1].barh(labels, values, color=colors, alpha=0.7)
            axes[1].set_xlabel('Correlation (r)')
            axes[1].set_title('Strongest Correlations')
            axes[1].grid(True, alpha=0.3, axis='x')

        # Panel 3: TIR vs hypo scatter
        tirs = [all_metrics[pn]['tir'] for pn in patient_names]
        hypos = [all_metrics[pn]['hypo_per_week'] for pn in patient_names]
        axes[2].scatter(tirs, hypos, s=100, c='steelblue', edgecolors='black',
                        linewidth=0.5, zorder=3)
        for pi, pn in enumerate(patient_names):
            axes[2].annotate(pn, (tirs[pi], hypos[pi]),
                             textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[2].set_xlabel('TIR (%)')
        axes[2].set_ylabel('Hypos per Week')
        axes[2].set_title('TIR vs Hypo Frequency')
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig06-correlations.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig06-correlations.png")

    return results


# ── EXP-2177: Patient Similarity Network ───────────────────────────
def exp_2177_similarity():
    """Which patients respond similarly?"""
    print("\n═══ EXP-2177: Patient Similarity Network ═══")

    all_metrics = {}
    for p in patients:
        m = compute_patient_metrics(p)
        if m:
            all_metrics[p['name']] = m

    patient_names = sorted(all_metrics.keys())
    feature_names = ['tir', 'tbr', 'tar', 'cv_glucose', 'hypo_per_week',
                     'mean_glucose']

    # Build feature matrix
    feature_matrix = []
    for pn in patient_names:
        row = [all_metrics[pn].get(fn, 0) for fn in feature_names]
        feature_matrix.append(row)

    X = np.array(feature_matrix)

    # Normalize
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0)
    stds[stds == 0] = 1
    X_norm = (X - means) / stds

    # Compute pairwise distances
    n = len(patient_names)
    dist_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dist_matrix[i, j] = float(np.sqrt(np.sum((X_norm[i] - X_norm[j]) ** 2)))

    # Find most similar pairs
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({
                'patient1': patient_names[i],
                'patient2': patient_names[j],
                'distance': float(dist_matrix[i, j])
            })

    pairs.sort(key=lambda x: x['distance'])

    # Identify clusters (simple: closest pairs)
    clusters = []
    used = set()
    for pair in pairs:
        if pair['distance'] < 2.0:  # Within 2 std devs
            p1, p2 = pair['patient1'], pair['patient2']
            added = False
            for cluster in clusters:
                if p1 in cluster or p2 in cluster:
                    cluster.add(p1)
                    cluster.add(p2)
                    added = True
                    break
            if not added:
                clusters.append({p1, p2})

    cluster_list = [sorted(list(c)) for c in clusters]
    # Singletons
    all_clustered = set()
    for c in clusters:
        all_clustered.update(c)
    singletons = [pn for pn in patient_names if pn not in all_clustered]

    results = {
        'distance_matrix': dist_matrix.tolist(),
        'patient_names': patient_names,
        'most_similar': pairs[:5],
        'most_different': pairs[-5:],
        'clusters': cluster_list,
        'singletons': singletons
    }

    print(f"  Clusters: {cluster_list}")
    print(f"  Singletons: {singletons}")
    for pair in pairs[:5]:
        print(f"  Similar: {pair['patient1']}↔{pair['patient2']} "
              f"(dist={pair['distance']:.2f})")

    with open(f'{EXP_DIR}/exp-2177_similarity.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        # Panel 1: Distance heatmap
        im = axes[0].imshow(dist_matrix, cmap='viridis_r')
        axes[0].set_xticks(range(n))
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_yticks(range(n))
        axes[0].set_yticklabels(patient_names, fontsize=8)
        axes[0].set_title('Patient Similarity (Distance)')
        plt.colorbar(im, ax=axes[0], shrink=0.8)

        # Panel 2: 2D projection (PCA-like: first 2 features)
        pc1 = X_norm[:, 0]  # TIR-based
        pc2 = X_norm[:, 3]  # CV-based
        axes[1].scatter(pc1, pc2, s=100, c='steelblue', edgecolors='black',
                        linewidth=0.5, zorder=3)
        for pi, pn in enumerate(patient_names):
            axes[1].annotate(pn, (pc1[pi], pc2[pi]),
                             textcoords="offset points", xytext=(5, 5), fontsize=9)
        axes[1].set_xlabel('TIR (normalized)')
        axes[1].set_ylabel('CV (normalized)')
        axes[1].set_title('Patient Similarity Map')
        axes[1].grid(True, alpha=0.3)

        # Panel 3: Top similar and dissimilar pairs
        labels_sim = [f"{p['patient1']}-{p['patient2']}" for p in pairs[:5]]
        dists_sim = [p['distance'] for p in pairs[:5]]
        labels_diff = [f"{p['patient1']}-{p['patient2']}" for p in pairs[-5:]]
        dists_diff = [p['distance'] for p in pairs[-5:]]

        all_labels = labels_sim + ['---'] + labels_diff
        all_dists = dists_sim + [0] + dists_diff
        all_colors = ['green'] * 5 + ['white'] + ['red'] * 5

        axes[2].barh(all_labels, all_dists, color=all_colors, alpha=0.7)
        axes[2].set_xlabel('Distance (lower = more similar)')
        axes[2].set_title('Most Similar vs Most Different')
        axes[2].grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig07-similarity.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig07-similarity.png")

    return results


# ── EXP-2178: Comprehensive Profile Cards ──────────────────────────
def exp_2178_profile_cards():
    """Actionable per-patient summary combining all findings."""
    print("\n═══ EXP-2178: Comprehensive Profile Cards ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        m = compute_patient_metrics(p)
        if not m:
            continue

        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        # Determine overall assessment
        strengths = []
        weaknesses = []
        recommendations = []

        if m['tir'] >= 70:
            strengths.append(f"Good TIR ({m['tir']:.0f}%)")
        else:
            weaknesses.append(f"Low TIR ({m['tir']:.0f}%)")

        if m['tbr'] < 4:
            if m['tbr'] < 1:
                strengths.append(f"Excellent TBR ({m['tbr']:.1f}%)")
        else:
            weaknesses.append(f"High TBR ({m['tbr']:.1f}%)")
            recommendations.append("SAFETY: Reduce insulin aggressiveness")

        if m['tar'] < 25:
            strengths.append(f"Low TAR ({m['tar']:.0f}%)")
        elif m['tar'] > 35:
            weaknesses.append(f"High TAR ({m['tar']:.0f}%)")
            recommendations.append("Consider more aggressive CR or pre-bolusing")

        if m['cv_glucose'] < 33:
            strengths.append(f"Moderate variability (CV={m['cv_glucose']:.0f}%)")
        else:
            weaknesses.append(f"High variability (CV={m['cv_glucose']:.0f}%)")

        if m['hypo_per_week'] < 2:
            strengths.append(f"Low hypo rate ({m['hypo_per_week']:.1f}/wk)")
        else:
            weaknesses.append(f"Frequent hypos ({m['hypo_per_week']:.1f}/wk)")
            recommendations.append("Review ISF and basal for hypo reduction")

        overnight_cv = m.get('overnight_cv', 30)
        if overnight_cv < 15:
            strengths.append(f"Stable overnight (CV={overnight_cv:.0f}%)")
        elif overnight_cv > 25:
            weaknesses.append(f"Volatile overnight (CV={overnight_cv:.0f}%)")
            recommendations.append("Consider overnight basal adjustment")

        # Overall grade
        score = (min(m['tir'] / 70, 1) * 30 +
                 min(max(0, 5 - m['tbr']) / 5, 1) * 25 +
                 min(max(0, 40 - m['tar']) / 40, 1) * 20 +
                 min(max(0, 5 - m['hypo_per_week']) / 5, 1) * 15 +
                 min(max(0, 30 - overnight_cv) / 30, 1) * 10)

        if score >= 80:
            grade = 'A'
        elif score >= 65:
            grade = 'B'
        elif score >= 50:
            grade = 'C'
        elif score >= 35:
            grade = 'D'
        else:
            grade = 'F'

        all_results[name] = {
            'grade': grade,
            'score': float(score),
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommendations': recommendations,
            'key_metrics': {
                'tir': m['tir'],
                'tbr': m['tbr'],
                'tar': m['tar'],
                'cv': m['cv_glucose'],
                'hypo_per_week': m['hypo_per_week'],
                'mean_glucose': m['mean_glucose'],
                'gmi': m['gmi'],
                'cgm_coverage': m['cgm_coverage'],
                'profile_isf': m.get('profile_isf', None),
                'profile_cr': m.get('profile_cr', None),
                'overnight_cv': overnight_cv,
                'overnight_tir': m.get('overnight_tir', None),
                'n_days': n_days
            }
        }

        print(f"  {name}: Grade={grade} ({score:.0f}/100), "
              f"{len(strengths)} strengths, {len(weaknesses)} weaknesses, "
              f"{len(recommendations)} recommendations")

    with open(f'{EXP_DIR}/exp-2178_profiles.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        patient_names = sorted(all_results.keys())

        # Panel 1: Profile scores with grades
        scores = [all_results[pn]['score'] for pn in patient_names]
        grades = [all_results[pn]['grade'] for pn in patient_names]
        colors_g = {'A': 'green', 'B': 'limegreen', 'C': 'orange', 'D': 'red', 'F': 'darkred'}
        bar_colors = [colors_g[g] for g in grades]
        bars = axes[0, 0].bar(patient_names, scores, color=bar_colors, alpha=0.8)
        for bi, bar in enumerate(bars):
            axes[0, 0].text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1,
                            grades[bi], ha='center', va='bottom', fontsize=10, fontweight='bold')
        axes[0, 0].set_ylabel('Profile Score')
        axes[0, 0].set_title('Comprehensive Patient Scores')
        axes[0, 0].set_ylim(0, 110)
        axes[0, 0].tick_params(axis='x', labelsize=8)
        axes[0, 0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Strengths vs weaknesses count
        n_strengths = [len(all_results[pn]['strengths']) for pn in patient_names]
        n_weaknesses = [len(all_results[pn]['weaknesses']) for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[0, 1].bar(x - 0.15, n_strengths, 0.3, label='Strengths', color='green', alpha=0.7)
        axes[0, 1].bar(x + 0.15, n_weaknesses, 0.3, label='Weaknesses', color='red', alpha=0.7)
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(patient_names, fontsize=8)
        axes[0, 1].set_ylabel('Count')
        axes[0, 1].set_title('Strengths vs Weaknesses')
        axes[0, 1].legend(fontsize=8)
        axes[0, 1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Key metrics summary
        tirs = [all_results[pn]['key_metrics']['tir'] for pn in patient_names]
        tbrs = [all_results[pn]['key_metrics']['tbr'] for pn in patient_names]
        tars = [all_results[pn]['key_metrics']['tar'] for pn in patient_names]
        w = 0.25
        axes[1, 0].bar(x - w, tirs, w, label='TIR', color='green', alpha=0.7)
        axes[1, 0].bar(x, tbrs, w, label='TBR', color='red', alpha=0.7)
        axes[1, 0].bar(x + w, tars, w, label='TAR', color='orange', alpha=0.7)
        axes[1, 0].set_xticks(x)
        axes[1, 0].set_xticklabels(patient_names, fontsize=8)
        axes[1, 0].set_ylabel('Percentage')
        axes[1, 0].set_title('Glucose Distribution')
        axes[1, 0].legend(fontsize=8)
        axes[1, 0].axhline(y=70, color='green', linestyle='--', alpha=0.3)
        axes[1, 0].axhline(y=4, color='red', linestyle='--', alpha=0.3)
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        # Panel 4: Recommendation counts
        n_recs = [len(all_results[pn]['recommendations']) for pn in patient_names]
        rec_colors = ['green' if r == 0 else 'orange' if r <= 2 else 'red' for r in n_recs]
        axes[1, 1].bar(patient_names, n_recs, color=rec_colors, alpha=0.7)
        axes[1, 1].set_ylabel('Number of Recommendations')
        axes[1, 1].set_title('Actionable Recommendations')
        axes[1, 1].tick_params(axis='x', labelsize=8)
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pheno-fig08-profiles.png', dpi=150)
        plt.close()
        print("  → Saved pheno-fig08-profiles.png")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2171–2178: Patient Phenotyping & Therapy Profiles")
    print("=" * 60)

    r1 = exp_2171_phenotype_clustering()
    r2 = exp_2172_therapy_scorecard()
    r3 = exp_2173_risk_stratification()
    r4 = exp_2174_temporal_stability()
    r5 = exp_2175_intervention_matrix()
    r6 = exp_2176_correlations()
    r7 = exp_2177_similarity()
    r8 = exp_2178_profile_cards()

    print("\n" + "=" * 60)
    n_complete = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r)
    print(f"Results: {n_complete}/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/pheno-fig01–08")
    print("=" * 60)
