#!/usr/bin/env python3
"""
EXP-2081–2088: Cross-Patient Phenotyping & Intervention Targeting

Synthesize all prior findings to cluster patients by AID behavior and
determine which therapy interventions yield the highest impact for each type.

EXP-2081: Glycemic fingerprint — multidimensional patient profile
EXP-2082: AID behavior clustering — suspension, correction, meal patterns
EXP-2083: Setting mismatch severity — composite miscalibration score
EXP-2084: Intervention impact ranking — which change helps most per patient
EXP-2085: Risk stratification — hypo risk vs hyper risk profile
EXP-2086: Temporal stability — do patients change phenotype over months?
EXP-2087: Supply-demand decomposition — separate loss sources for deconfounding
EXP-2088: Actionable summary — one-page therapy card per patient

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
    from matplotlib.patches import FancyBboxPatch
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESH = 70
TARGET_HIGH = 180
SUPPLY_SCALE = 0.3


patients = load_patients(PATIENT_DIR)


def get_profile_value(df, attr_name, hour, convert_mmol=False):
    """Get profile value for a given hour from list-of-dicts schedule."""
    schedule = df.attrs.get(attr_name, [])
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    applicable = None
    for entry in sorted_sched:
        time_str = entry.get('time', '00:00')
        val = entry.get('value')
        h, m = map(int, time_str.split(':'))
        sched_hour = h + m / 60
        if sched_hour <= hour:
            applicable = val
    if applicable is None:
        applicable = sorted_sched[0].get('value')
    if applicable is not None and convert_mmol and applicable < 15:
        applicable *= 18.0182
    return applicable


# ── EXP-2081: Glycemic Fingerprint ────────────────────────────────────
def exp_2081_glycemic_fingerprint():
    """Multidimensional glycemic profile for each patient."""
    print("\n═══ EXP-2081: Glycemic Fingerprint ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]

        if len(g_valid) < STEPS_PER_DAY:
            continue

        # Core metrics
        mean_g = float(np.mean(g_valid))
        std_g = float(np.std(g_valid))
        cv = std_g / mean_g * 100
        tir = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
        tbr = float(np.mean(g_valid < 70))
        tar = float(np.mean(g_valid > 180))
        eA1c = (mean_g + 46.7) / 28.7

        # Variability metrics
        # GRI = Glycemic Risk Index (composite)
        vlow = float(np.mean(g_valid < 54))  # very low
        low = tbr - vlow
        high = float(np.mean(g_valid > 250))  # very high
        gri_hypo = vlow * 8.81 + low * 2.82  # weighted hypo component
        gri_hyper = high * 4.16 + (tar - high) * 0.73  # weighted hyper component

        # Rate of change
        dg = np.diff(g_valid)
        roc_mean = float(np.mean(np.abs(dg)))
        roc_p95 = float(np.percentile(np.abs(dg), 95))

        # Time below range patterns
        hypo_mask = g_valid < HYPO_THRESH
        if np.any(hypo_mask):
            # Count distinct hypo events (groups of consecutive below-range)
            hypo_transitions = np.diff(hypo_mask.astype(int))
            n_hypo_events = int(np.sum(hypo_transitions == 1))
            # Average duration
            hypo_runs = []
            in_hypo = False
            run_len = 0
            for v in hypo_mask:
                if v:
                    in_hypo = True
                    run_len += 1
                elif in_hypo:
                    hypo_runs.append(run_len)
                    in_hypo = False
                    run_len = 0
            if in_hypo:
                hypo_runs.append(run_len)
            mean_hypo_dur = float(np.mean(hypo_runs)) * 5 if hypo_runs else 0  # minutes
        else:
            n_hypo_events = 0
            mean_hypo_dur = 0

        # Circadian pattern strength
        hours = np.arange(len(g_valid)) % STEPS_PER_DAY / STEPS_PER_HOUR
        hourly_means = []
        for h in range(24):
            mask = (hours >= h) & (hours < h + 1)
            if np.sum(mask) > 0:
                hourly_means.append(float(np.mean(g_valid[mask])))
        circadian_range = max(hourly_means) - min(hourly_means) if hourly_means else 0

        # IOB patterns
        iob = df['iob'].values
        iob_valid = iob[~np.isnan(iob)]
        mean_iob = float(np.mean(iob_valid)) if len(iob_valid) > 0 else 0

        # Insulin delivery
        bolus = df['bolus'].values
        bolus_valid = bolus[~np.isnan(bolus)]
        total_bolus_day = float(np.sum(bolus_valid)) / (len(g_valid) / STEPS_PER_DAY)

        n_days = len(g_valid) / STEPS_PER_DAY

        results[name] = {
            'mean_glucose': round(mean_g, 1),
            'std_glucose': round(std_g, 1),
            'cv': round(cv, 1),
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3),
            'eA1c': round(eA1c, 1),
            'gri_hypo': round(gri_hypo, 3),
            'gri_hyper': round(gri_hyper, 3),
            'roc_mean': round(roc_mean, 1),
            'roc_p95': round(roc_p95, 1),
            'n_hypo_events': n_hypo_events,
            'mean_hypo_dur_min': round(mean_hypo_dur, 1),
            'circadian_range': round(circadian_range, 1),
            'mean_iob': round(mean_iob, 2),
            'bolus_per_day': round(total_bolus_day, 1),
            'n_days': round(n_days, 1)
        }

        print(f"  {name}: TIR={tir:.0%} CV={cv:.0f}% eA1c={eA1c:.1f} "
              f"hypos={n_hypo_events} circ_range={circadian_range:.0f}mg/dL")

    if MAKE_FIGS:
        # Radar chart of key metrics for all patients
        fig, axes = plt.subplots(3, 4, figsize=(20, 15),
                                  subplot_kw=dict(polar=True))
        axes = axes.flatten()

        categories = ['TIR', 'CV\n(inv)', 'Hypo\nSafety', 'Circ.\nStab.',
                      'Rate\nStab.', 'eA1c\n(inv)']
        n_cats = len(categories)
        angles = np.linspace(0, 2 * np.pi, n_cats, endpoint=False).tolist()
        angles += angles[:1]

        for idx, (name, r) in enumerate(sorted(results.items())):
            if idx >= 11:
                break
            ax = axes[idx]

            # Normalize to 0-1 (higher = better)
            values = [
                r['tir'],  # TIR (already 0-1)
                max(0, 1 - r['cv'] / 50),  # CV inverted (lower better)
                max(0, 1 - r['tbr'] / 0.10),  # Hypo safety (lower TBR better)
                max(0, 1 - r['circadian_range'] / 60),  # Circ stability
                max(0, 1 - r['roc_mean'] / 5),  # Rate stability
                max(0, 1 - (r['eA1c'] - 5.5) / 3),  # eA1c inverted
            ]
            values += values[:1]

            ax.fill(angles, values, alpha=0.25, color='C0')
            ax.plot(angles, values, 'o-', color='C0', linewidth=2)
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(categories, size=7)
            ax.set_ylim(0, 1)
            ax.set_title(f"Patient {name}", fontweight='bold', size=12, pad=15)
            ax.set_yticklabels([])

        # Hide unused subplot
        for idx in range(len(results), len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle('EXP-2081: Glycemic Fingerprint — Radar Profiles',
                     fontsize=16, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pheno-fig01-fingerprint.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig01-fingerprint.png")

    output = {'experiment': 'EXP-2081', 'title': 'Glycemic Fingerprint',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2081_glycemic_fingerprint.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2082: AID Behavior Clustering ─────────────────────────────────
def exp_2082_aid_behavior_clustering():
    """Cluster patients by AID loop behavior patterns."""
    print("\n═══ EXP-2082: AID Behavior Clustering ═══")

    features = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        # Suspension behavior
        enacted = df['enacted_rate'].values
        enacted_valid = enacted[~np.isnan(enacted)]
        suspend_rate = float(np.mean(enacted_valid == 0)) if len(enacted_valid) > 0 else 0

        # Bolus patterns
        bolus = df['bolus'].values
        bolus_events = bolus[~np.isnan(bolus) & (bolus > 0)]
        n_bolus_per_day = len(bolus_events) / (len(g_valid) / STEPS_PER_DAY)
        mean_bolus = float(np.mean(bolus_events)) if len(bolus_events) > 0 else 0

        # Carb patterns
        carbs = df['carbs'].values
        carb_events = carbs[~np.isnan(carbs) & (carbs > 0)]
        n_carb_per_day = len(carb_events) / (len(g_valid) / STEPS_PER_DAY)
        mean_carb = float(np.mean(carb_events)) if len(carb_events) > 0 else 0

        # IOB behavior
        iob = df['iob'].values
        iob_valid = iob[~np.isnan(iob)]
        mean_iob = float(np.mean(iob_valid)) if len(iob_valid) > 0 else 0
        iob_cv = float(np.std(iob_valid) / np.mean(iob_valid) * 100) if len(iob_valid) > 0 and np.mean(iob_valid) > 0 else 0

        # Correction frequency
        n_corrections = 0
        for i in range(len(bolus)):
            if not np.isnan(bolus[i]) and bolus[i] > 0.5:
                if i < len(g) and not np.isnan(g[i]) and g[i] > 150:
                    n_corrections += 1
        corr_per_day = n_corrections / (len(g_valid) / STEPS_PER_DAY)

        # Net basal vs scheduled
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.full(len(df), np.nan)
        nb_valid = net_basal[~np.isnan(net_basal)]
        # Mean temp basal adjustment
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.full(len(df), np.nan)
        tr_valid = temp_rate[~np.isnan(temp_rate)]
        mean_temp = float(np.mean(tr_valid)) if len(tr_valid) > 0 else 0

        # TIR, TBR for clustering
        tir = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
        tbr = float(np.mean(g_valid < 70))
        tar = float(np.mean(g_valid > 180))

        features[name] = {
            'suspend_rate': round(suspend_rate, 3),
            'n_bolus_per_day': round(n_bolus_per_day, 1),
            'mean_bolus_u': round(mean_bolus, 2),
            'n_carb_per_day': round(n_carb_per_day, 1),
            'mean_carb_g': round(mean_carb, 1),
            'mean_iob': round(mean_iob, 2),
            'iob_cv': round(iob_cv, 1),
            'corr_per_day': round(corr_per_day, 1),
            'mean_temp_rate': round(mean_temp, 3),
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3)
        }

    # Simple k-means-style clustering using 2D: suspend_rate vs correction_frequency
    # (avoiding sklearn dependency — manual approach)
    names = sorted(features.keys())
    x = np.array([features[n]['suspend_rate'] for n in names])
    y = np.array([features[n]['corr_per_day'] for n in names])
    tir_arr = np.array([features[n]['tir'] for n in names])
    tbr_arr = np.array([features[n]['tbr'] for n in names])

    # Define phenotype by quadrant
    med_x = float(np.median(x))
    med_y = float(np.median(y))

    clusters = {}
    for i, n in enumerate(names):
        if x[i] > med_x and y[i] > med_y:
            phenotype = "COMPENSATING"  # high suspend + high correction
        elif x[i] > med_x and y[i] <= med_y:
            phenotype = "PASSIVE"  # high suspend + low correction (loop does everything)
        elif x[i] <= med_x and y[i] > med_y:
            phenotype = "AGGRESSIVE"  # low suspend + high correction
        else:
            phenotype = "BALANCED"  # low suspend + low correction

        clusters[n] = phenotype
        features[n]['phenotype'] = phenotype
        print(f"  {n}: {phenotype} (suspend={x[i]:.0%}, corr={y[i]:.1f}/day, "
              f"TIR={tir_arr[i]:.0%})")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(10, 8))
        colors = {'COMPENSATING': 'red', 'PASSIVE': 'orange',
                  'AGGRESSIVE': 'purple', 'BALANCED': 'green'}

        for i, n in enumerate(names):
            c = colors[clusters[n]]
            ax.scatter(x[i], y[i], c=c, s=200, zorder=5, edgecolors='black')
            ax.annotate(n, (x[i], y[i]), fontsize=14, fontweight='bold',
                       ha='center', va='bottom', xytext=(0, 8),
                       textcoords='offset points')

        # Quadrant lines
        ax.axvline(med_x, color='gray', linestyle='--', alpha=0.5)
        ax.axhline(med_y, color='gray', linestyle='--', alpha=0.5)

        # Quadrant labels
        ax.text(0.95, 0.95, 'COMPENSATING\n(high suspend + corrections)',
                transform=ax.transAxes, ha='right', va='top', color='red',
                fontsize=10, fontstyle='italic')
        ax.text(0.95, 0.05, 'PASSIVE\n(high suspend, few corrections)',
                transform=ax.transAxes, ha='right', va='bottom', color='orange',
                fontsize=10, fontstyle='italic')
        ax.text(0.05, 0.95, 'AGGRESSIVE\n(low suspend + corrections)',
                transform=ax.transAxes, ha='left', va='top', color='purple',
                fontsize=10, fontstyle='italic')
        ax.text(0.05, 0.05, 'BALANCED\n(low suspend, few corrections)',
                transform=ax.transAxes, ha='left', va='bottom', color='green',
                fontsize=10, fontstyle='italic')

        ax.set_xlabel('Suspension Rate (fraction of time at zero delivery)',
                     fontsize=12)
        ax.set_ylabel('Corrections per Day', fontsize=12)
        ax.set_title('EXP-2082: AID Behavior Phenotyping', fontsize=14,
                     fontweight='bold')
        ax.grid(True, alpha=0.3)

        fig.savefig(f'{FIG_DIR}/pheno-fig02-clustering.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig02-clustering.png")

    output = {'experiment': 'EXP-2082', 'title': 'AID Behavior Clustering',
              'medians': {'suspend_rate': round(med_x, 3),
                         'corr_per_day': round(med_y, 1)},
              'per_patient': features}
    with open(f'{EXP_DIR}/exp-2082_aid_clustering.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2083: Setting Mismatch Severity ───────────────────────────────
def exp_2083_setting_mismatch():
    """Composite score of how far off each patient's settings are."""
    print("\n═══ EXP-2083: Setting Mismatch Severity ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        sd = compute_supply_demand(df)
        net = sd['net']

        # ISF mismatch: compare correction outcomes to profile prediction
        bolus = df['bolus'].values
        isf_ratios = []
        for i in range(len(g) - 4 * STEPS_PER_HOUR):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            if np.isnan(g[i]) or g[i] < 150:
                continue
            # Look 2h ahead for glucose drop
            future = g[i:i + 2 * STEPS_PER_HOUR]
            future_valid = future[~np.isnan(future)]
            if len(future_valid) < STEPS_PER_HOUR:
                continue
            actual_drop = g[i] - np.min(future_valid)
            if actual_drop < 10:
                continue
            effective_isf = actual_drop / bolus[i]
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            profile_isf = get_profile_value(df, 'isf_schedule', hour, convert_mmol=True)
            if profile_isf and profile_isf > 0:
                isf_ratios.append(effective_isf / profile_isf)

        isf_mismatch = float(np.median(isf_ratios)) if isf_ratios else 1.0

        # CR mismatch: post-meal excursion vs expected
        carbs_col = df['carbs'].values
        cr_ratios = []
        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(carbs_col[i]) or carbs_col[i] < 5:
                continue
            if np.isnan(g[i]):
                continue
            # Look 2h ahead for peak
            future = g[i:i + 2 * STEPS_PER_HOUR]
            future_valid = future[~np.isnan(future)]
            if len(future_valid) < 6:
                continue
            spike = float(np.max(future_valid)) - g[i]
            if spike < 10:
                continue
            # Expected: carbs / CR * ISF should predict the spike
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            profile_cr = get_profile_value(df, 'cr_schedule', hour)
            profile_isf = get_profile_value(df, 'isf_schedule', hour, convert_mmol=True)
            if profile_cr and profile_isf and profile_cr > 0:
                expected_spike = (carbs_col[i] / profile_cr) * profile_isf
                if expected_spike > 0:
                    cr_ratios.append(spike / expected_spike)

        cr_mismatch = float(np.median(cr_ratios)) if cr_ratios else 1.0

        # Basal mismatch: fasting drift
        basal_drifts = []
        for i in range(STEPS_PER_HOUR, len(g) - STEPS_PER_HOUR):
            # Fasting: no carbs within ±3h
            window = 3 * STEPS_PER_HOUR
            start = max(0, i - window)
            end = min(len(carbs_col), i + window)
            carb_sum = np.nansum(carbs_col[start:end])
            if carb_sum > 0:
                continue
            # No bolus within ±2h
            bolus_window = 2 * STEPS_PER_HOUR
            bs = max(0, i - bolus_window)
            be = min(len(bolus), i + bolus_window)
            bolus_sum = np.nansum(bolus[bs:be])
            if bolus_sum > 0:
                continue
            if np.isnan(g[i]) or np.isnan(g[i - 1]):
                continue
            basal_drifts.append(g[i] - g[i - 1])

        basal_drift = float(np.mean(basal_drifts)) if basal_drifts else 0
        basal_mismatch = abs(basal_drift) / 2  # scale: 2 mg/dL/5min = severe

        # Composite score (0-10 scale)
        isf_score = min(10, abs(isf_mismatch - 1) * 5)
        cr_score = min(10, abs(cr_mismatch - 1) * 5)
        basal_score = min(10, basal_mismatch * 10)
        composite = (isf_score + cr_score + basal_score) / 3

        results[name] = {
            'isf_mismatch_ratio': round(isf_mismatch, 2),
            'cr_mismatch_ratio': round(cr_mismatch, 2),
            'basal_drift_mg_per_5min': round(basal_drift, 2),
            'isf_score': round(isf_score, 1),
            'cr_score': round(cr_score, 1),
            'basal_score': round(basal_score, 1),
            'composite_mismatch': round(composite, 1),
            'n_isf_events': len(isf_ratios),
            'n_cr_events': len(cr_ratios),
            'n_fasting_periods': len(basal_drifts)
        }

        severity = "LOW" if composite < 2 else "MODERATE" if composite < 5 else "HIGH"
        print(f"  {name}: {severity} (ISF={isf_mismatch:.2f}× CR={cr_mismatch:.2f}× "
              f"basal_drift={basal_drift:+.2f} composite={composite:.1f}/10)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))

        names = sorted(results.keys())
        x_pos = np.arange(len(names))

        # ISF mismatch
        ax = axes[0]
        vals = [results[n]['isf_mismatch_ratio'] for n in names]
        colors = ['green' if abs(v - 1) < 0.3 else 'orange' if abs(v - 1) < 0.7
                  else 'red' for v in vals]
        ax.bar(x_pos, vals, color=colors, edgecolor='black')
        ax.axhline(1.0, color='black', linestyle='--', linewidth=2, label='Perfect')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(names, fontsize=12, fontweight='bold')
        ax.set_ylabel('Effective/Profile ISF Ratio')
        ax.set_title('ISF Mismatch', fontweight='bold')
        ax.legend()

        # CR mismatch
        ax = axes[1]
        vals = [results[n]['cr_mismatch_ratio'] for n in names]
        colors = ['green' if abs(v - 1) < 0.3 else 'orange' if abs(v - 1) < 0.7
                  else 'red' for v in vals]
        ax.bar(x_pos, vals, color=colors, edgecolor='black')
        ax.axhline(1.0, color='black', linestyle='--', linewidth=2, label='Perfect')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(names, fontsize=12, fontweight='bold')
        ax.set_ylabel('Actual/Expected Spike Ratio')
        ax.set_title('CR Mismatch', fontweight='bold')
        ax.legend()

        # Composite
        ax = axes[2]
        vals = [results[n]['composite_mismatch'] for n in names]
        colors = ['green' if v < 2 else 'orange' if v < 5 else 'red' for v in vals]
        ax.barh(x_pos, vals, color=colors, edgecolor='black')
        ax.set_yticks(x_pos)
        ax.set_yticklabels(names, fontsize=12, fontweight='bold')
        ax.set_xlabel('Composite Mismatch Score (0=perfect, 10=severe)')
        ax.set_title('Overall Setting Mismatch', fontweight='bold')
        ax.axvline(2, color='green', linestyle=':', alpha=0.5, label='Low')
        ax.axvline(5, color='red', linestyle=':', alpha=0.5, label='High')
        ax.legend()

        fig.suptitle('EXP-2083: Setting Mismatch Severity', fontsize=14,
                     fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pheno-fig03-mismatch.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig03-mismatch.png")

    output = {'experiment': 'EXP-2083', 'title': 'Setting Mismatch Severity',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2083_mismatch.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2084: Intervention Impact Ranking ─────────────────────────────
def exp_2084_intervention_ranking():
    """Which single intervention helps each patient most?"""
    print("\n═══ EXP-2084: Intervention Impact Ranking ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        tir_base = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
        tbr_base = float(np.mean(g_valid < 70))
        tar_base = float(np.mean(g_valid > 180))

        interventions = {}

        # 1. Reduce basal by 12% (population mean)
        g_basal = g_valid + 5  # less insulin → higher glucose
        tir_basal = float(np.mean((g_basal >= 70) & (g_basal <= 180)))
        tbr_basal = float(np.mean(g_basal < 70))
        interventions['reduce_basal_12pct'] = {
            'delta_tir': round((tir_basal - tir_base) * 100, 1),
            'delta_tbr': round((tbr_basal - tbr_base) * 100, 1),
            'description': 'Reduce basal by 12%'
        }

        # 2. Increase ISF by 20%
        g_isf = g_valid.copy()
        # Less aggressive corrections → fewer hypos but more hypers
        hypo_mask = g_valid < 70
        g_isf[hypo_mask] = g_valid[hypo_mask] + 15  # would have been higher with less insulin
        tir_isf = float(np.mean((g_isf >= 70) & (g_isf <= 180)))
        tbr_isf = float(np.mean(g_isf < 70))
        interventions['increase_isf_20pct'] = {
            'delta_tir': round((tir_isf - tir_base) * 100, 1),
            'delta_tbr': round((tbr_isf - tbr_base) * 100, 1),
            'description': 'Increase ISF by 20%'
        }

        # 3. Circadian ISF (different AM/PM)
        hours = np.arange(len(g_valid)) % STEPS_PER_DAY / STEPS_PER_HOUR
        g_circ = g_valid.copy()
        # Morning: more aggressive (lower glucose)
        morning = (hours >= 6) & (hours < 12)
        g_circ[morning & (g_valid > 180)] -= 10  # better coverage AM
        # Evening: less aggressive (prevent hypos)
        evening = (hours >= 18) | (hours < 6)
        g_circ[evening & (g_valid < 80)] += 10
        tir_circ = float(np.mean((g_circ >= 70) & (g_circ <= 180)))
        tbr_circ = float(np.mean(g_circ < 70))
        interventions['circadian_isf'] = {
            'delta_tir': round((tir_circ - tir_base) * 100, 1),
            'delta_tbr': round((tbr_circ - tbr_base) * 100, 1),
            'description': 'Circadian ISF (AM aggressive, PM conservative)'
        }

        # 4. Dinner-specific CR (more aggressive)
        g_dinner = g_valid.copy()
        dinner = (hours >= 17) & (hours < 21)
        g_dinner[dinner & (g_valid > 180)] -= 20  # more insulin at dinner
        tir_dinner = float(np.mean((g_dinner >= 70) & (g_dinner <= 180)))
        tbr_dinner = float(np.mean(g_dinner < 70))
        interventions['dinner_cr'] = {
            'delta_tir': round((tir_dinner - tir_base) * 100, 1),
            'delta_tbr': round((tbr_dinner - tbr_base) * 100, 1),
            'description': 'Dinner-specific CR (more aggressive)'
        }

        # 5. Dawn basal ramp
        g_dawn = g_valid.copy()
        dawn = (hours >= 3) & (hours < 8)
        g_dawn[dawn & (g_valid > 140)] -= 15
        tir_dawn = float(np.mean((g_dawn >= 70) & (g_dawn <= 180)))
        tbr_dawn = float(np.mean(g_dawn < 70))
        interventions['dawn_basal_ramp'] = {
            'delta_tir': round((tir_dawn - tir_base) * 100, 1),
            'delta_tbr': round((tbr_dawn - tbr_base) * 100, 1),
            'description': 'Dawn basal ramp (3-8am)'
        }

        # Rank by TIR improvement
        ranked = sorted(interventions.items(),
                       key=lambda x: x[1]['delta_tir'], reverse=True)
        for rank, (intv, data) in enumerate(ranked, 1):
            data['rank'] = rank

        results[name] = {
            'baseline_tir': round(tir_base, 3),
            'baseline_tbr': round(tbr_base, 3),
            'interventions': interventions,
            'top_intervention': ranked[0][0],
            'top_delta_tir': ranked[0][1]['delta_tir']
        }

        print(f"  {name}: Top={ranked[0][0]} (+{ranked[0][1]['delta_tir']:.1f}pp TIR)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 8))

        names = sorted(results.keys())
        intv_names = ['reduce_basal_12pct', 'increase_isf_20pct', 'circadian_isf',
                     'dinner_cr', 'dawn_basal_ramp']
        intv_labels = ['Reduce Basal', 'Increase ISF', 'Circadian ISF',
                      'Dinner CR', 'Dawn Ramp']
        n_intv = len(intv_names)
        x = np.arange(len(names))
        width = 0.15

        for j, (intv, label) in enumerate(zip(intv_names, intv_labels)):
            vals = [results[n]['interventions'][intv]['delta_tir'] for n in names]
            ax.bar(x + j * width, vals, width, label=label,
                  edgecolor='black', alpha=0.8)

        ax.set_xticks(x + width * 2)
        ax.set_xticklabels(names, fontsize=12, fontweight='bold')
        ax.set_ylabel('TIR Improvement (percentage points)', fontsize=12)
        ax.set_title('EXP-2084: Intervention Impact by Patient', fontsize=14,
                     fontweight='bold')
        ax.legend(loc='upper right')
        ax.axhline(0, color='black', linewidth=0.5)
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/pheno-fig04-interventions.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig04-interventions.png")

    output = {'experiment': 'EXP-2084', 'title': 'Intervention Impact Ranking',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2084_interventions.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2085: Risk Stratification ─────────────────────────────────────
def exp_2085_risk_stratification():
    """Hypo risk vs hyper risk profile for clinical prioritization."""
    print("\n═══ EXP-2085: Risk Stratification ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        n_days = len(g_valid) / STEPS_PER_DAY

        # Hypo risk metrics
        tbr = float(np.mean(g_valid < 70))
        tbr_severe = float(np.mean(g_valid < 54))

        # LBGI (Low Blood Glucose Index)
        f_bg = 1.509 * (np.log(np.maximum(g_valid, 1)) ** 1.084 - 5.381)
        rl = np.where(f_bg < 0, 10 * f_bg ** 2, 0)
        lbgi = float(np.mean(rl))

        # Hypo event count
        hypo_mask = g_valid < 70
        hypo_transitions = np.diff(hypo_mask.astype(int))
        n_hypo = int(np.sum(hypo_transitions == 1))
        hypo_per_week = n_hypo / n_days * 7

        # Nocturnal hypo
        hours = np.arange(len(g_valid)) % STEPS_PER_DAY / STEPS_PER_HOUR
        nocturnal = (hours >= 22) | (hours < 6)
        nocturnal_hypo = float(np.mean(g_valid[nocturnal] < 70)) if np.sum(nocturnal) > 0 else 0

        # Hyper risk metrics
        tar = float(np.mean(g_valid > 180))
        tar_severe = float(np.mean(g_valid > 250))

        # HBGI (High Blood Glucose Index)
        rh = np.where(f_bg > 0, 10 * f_bg ** 2, 0)
        hbgi = float(np.mean(rh))

        # Time above 250 consecutive
        hyper_mask = g_valid > 250
        if np.any(hyper_mask):
            hyper_transitions = np.diff(hyper_mask.astype(int))
            n_hyper_events = int(np.sum(hyper_transitions == 1))
            # Longest streak above 250
            max_streak = 0
            current_streak = 0
            for v in hyper_mask:
                if v:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
            max_hyper_min = max_streak * 5
        else:
            n_hyper_events = 0
            max_hyper_min = 0

        # Risk classification
        if tbr_severe > 0.01 or lbgi > 5:
            hypo_class = "HIGH"
        elif tbr > 0.04 or lbgi > 2.5:
            hypo_class = "MODERATE"
        else:
            hypo_class = "LOW"

        if tar_severe > 0.05 or hbgi > 10:
            hyper_class = "HIGH"
        elif tar > 0.25 or hbgi > 5:
            hyper_class = "MODERATE"
        else:
            hyper_class = "LOW"

        results[name] = {
            'tbr': round(tbr, 3),
            'tbr_severe': round(tbr_severe, 3),
            'lbgi': round(lbgi, 2),
            'hypo_per_week': round(hypo_per_week, 1),
            'nocturnal_hypo': round(nocturnal_hypo, 3),
            'hypo_class': hypo_class,
            'tar': round(tar, 3),
            'tar_severe': round(tar_severe, 3),
            'hbgi': round(hbgi, 2),
            'n_hyper_events': n_hyper_events,
            'max_hyper_min': max_hyper_min,
            'hyper_class': hyper_class,
            'priority': 'HYPO' if hypo_class == "HIGH" else
                       'HYPER' if hyper_class == "HIGH" else
                       'BALANCED'
        }

        print(f"  {name}: Hypo={hypo_class} (LBGI={lbgi:.1f}) "
              f"Hyper={hyper_class} (HBGI={hbgi:.1f}) → {results[name]['priority']}")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(10, 8))

        names = sorted(results.keys())
        lbgi = [results[n]['lbgi'] for n in names]
        hbgi = [results[n]['hbgi'] for n in names]
        priority = [results[n]['priority'] for n in names]

        colors = {'HYPO': 'blue', 'HYPER': 'red', 'BALANCED': 'green'}
        for i, n in enumerate(names):
            c = colors[priority[i]]
            ax.scatter(hbgi[i], lbgi[i], c=c, s=250, edgecolors='black',
                      linewidth=2, zorder=5)
            ax.annotate(n, (hbgi[i], lbgi[i]), fontsize=13, fontweight='bold',
                       ha='center', va='bottom', xytext=(0, 10),
                       textcoords='offset points')

        # Risk zones
        ax.axhline(2.5, color='blue', linestyle=':', alpha=0.4,
                   label='Moderate hypo risk')
        ax.axhline(5.0, color='blue', linestyle='--', alpha=0.4,
                   label='High hypo risk')
        ax.axvline(5.0, color='red', linestyle=':', alpha=0.4,
                   label='Moderate hyper risk')
        ax.axvline(10.0, color='red', linestyle='--', alpha=0.4,
                   label='High hyper risk')

        ax.set_xlabel('HBGI (High Blood Glucose Index)', fontsize=12)
        ax.set_ylabel('LBGI (Low Blood Glucose Index)', fontsize=12)
        ax.set_title('EXP-2085: Risk Stratification (LBGI vs HBGI)',
                     fontsize=14, fontweight='bold')
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/pheno-fig05-risk.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig05-risk.png")

    output = {'experiment': 'EXP-2085', 'title': 'Risk Stratification',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2085_risk.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2086: Temporal Stability ──────────────────────────────────────
def exp_2086_temporal_stability():
    """Do patients change phenotype over the observation period?"""
    print("\n═══ EXP-2086: Temporal Stability ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < 2 * STEPS_PER_DAY * 30:  # need at least 2 months
            print(f"  {name}: insufficient data ({len(g_valid)/STEPS_PER_DAY:.0f} days)")
            results[name] = {'sufficient_data': False}
            continue

        n_days = len(g_valid) / STEPS_PER_DAY
        n_months = int(n_days / 30)
        if n_months < 2:
            results[name] = {'sufficient_data': False}
            continue

        monthly_tir = []
        monthly_tbr = []
        monthly_cv = []
        monthly_mean = []

        for m in range(n_months):
            start = m * 30 * STEPS_PER_DAY
            end = min(len(g_valid), (m + 1) * 30 * STEPS_PER_DAY)
            month_g = g_valid[start:end]
            if len(month_g) < 7 * STEPS_PER_DAY:  # need at least a week
                continue
            monthly_tir.append(float(np.mean((month_g >= 70) & (month_g <= 180))))
            monthly_tbr.append(float(np.mean(month_g < 70)))
            monthly_cv.append(float(np.std(month_g) / np.mean(month_g) * 100))
            monthly_mean.append(float(np.mean(month_g)))

        if len(monthly_tir) < 2:
            results[name] = {'sufficient_data': False}
            continue

        # Trend detection (simple linear regression)
        x = np.arange(len(monthly_tir))
        tir_slope = float(np.polyfit(x, monthly_tir, 1)[0])
        tbr_slope = float(np.polyfit(x, monthly_tbr, 1)[0])
        cv_slope = float(np.polyfit(x, monthly_cv, 1)[0])
        mean_slope = float(np.polyfit(x, monthly_mean, 1)[0])

        # Stability classification
        tir_range = max(monthly_tir) - min(monthly_tir)
        if tir_range < 0.05:
            stability = "STABLE"
        elif tir_range < 0.10:
            stability = "MODERATE"
        else:
            stability = "VARIABLE"

        # Direction
        if abs(tir_slope) < 0.005:
            direction = "FLAT"
        elif tir_slope > 0:
            direction = "IMPROVING"
        else:
            direction = "DECLINING"

        results[name] = {
            'sufficient_data': True,
            'n_months': len(monthly_tir),
            'monthly_tir': [round(v, 3) for v in monthly_tir],
            'monthly_tbr': [round(v, 3) for v in monthly_tbr],
            'monthly_cv': [round(v, 1) for v in monthly_cv],
            'monthly_mean': [round(v, 1) for v in monthly_mean],
            'tir_slope_per_month': round(tir_slope, 4),
            'tbr_slope_per_month': round(tbr_slope, 4),
            'tir_range': round(tir_range, 3),
            'stability': stability,
            'direction': direction
        }

        print(f"  {name}: {stability} {direction} "
              f"(TIR range={tir_range:.1%}, slope={tir_slope:+.3f}/mo, "
              f"{len(monthly_tir)} months)")

    if MAKE_FIGS:
        # Monthly TIR trajectories
        fig, ax = plt.subplots(figsize=(14, 7))

        for name, r in sorted(results.items()):
            if not r.get('sufficient_data', False):
                continue
            months = np.arange(1, len(r['monthly_tir']) + 1)
            tir_pct = [v * 100 for v in r['monthly_tir']]
            style = '-' if r['stability'] == 'STABLE' else '--' if r['stability'] == 'MODERATE' else ':'
            ax.plot(months, tir_pct, f'o{style}', label=f"{name} ({r['direction']})",
                   linewidth=2, markersize=8)

        ax.axhline(70, color='green', linestyle='--', alpha=0.5, label='TIR target (70%)')
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Time in Range (%)', fontsize=12)
        ax.set_title('EXP-2086: TIR Temporal Stability (Monthly)',
                     fontsize=14, fontweight='bold')
        ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(30, 100)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/pheno-fig06-stability.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig06-stability.png")

    output = {'experiment': 'EXP-2086', 'title': 'Temporal Stability',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2086_stability.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2087: Supply-Demand Loss Decomposition ───────────────────────
def exp_2087_supply_demand_decomposition():
    """Decompose prediction error into supply vs demand components.

    The hypothesis: supply errors (insulin/carb timing) and demand errors
    (glucose production/utilization) may operate on different timescales
    and be separable, even without direct measurement of each source.
    This could help deconfound ISF/CR/basal estimates.
    """
    print("\n═══ EXP-2087: Supply-Demand Loss Decomposition ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        sd = compute_supply_demand(df)
        net = sd['net']

        # Actual glucose changes
        dg = np.diff(g)

        # Trim to same length
        min_len = min(len(dg), len(net) - 1)
        dg_trim = dg[:min_len]
        net_trim = net[:min_len]

        # Valid mask
        valid = ~np.isnan(dg_trim) & ~np.isnan(net_trim)
        dg_v = dg_trim[valid]
        net_v = net_trim[valid]

        if len(dg_v) < STEPS_PER_DAY:
            continue

        # Residual = actual change - model prediction
        residual = dg_v - net_v

        # Decompose residual by context
        hours = np.arange(len(dg_trim))[valid] % STEPS_PER_DAY / STEPS_PER_HOUR

        # Supply-dominated windows (insulin acting: post-bolus)
        bolus = df['bolus'].values
        iob = df['iob'].values

        # Classify each timestep
        supply_mask = np.zeros(len(dg_v), dtype=bool)
        demand_mask = np.zeros(len(dg_v), dtype=bool)

        idx_map = np.where(valid)[0]
        for j, orig_idx in enumerate(idx_map):
            if orig_idx >= len(iob):
                continue
            iob_val = iob[orig_idx] if not np.isnan(iob[orig_idx]) else 0
            # High IOB → supply-dominated
            if iob_val > 1.0:
                supply_mask[j] = True
            # Low IOB + no recent carbs → demand-dominated (hepatic/exercise)
            elif iob_val < 0.3:
                demand_mask[j] = True

        supply_residual = residual[supply_mask]
        demand_residual = residual[demand_mask]

        # Loss metrics
        supply_rmse = float(np.sqrt(np.mean(supply_residual ** 2))) if len(supply_residual) > 100 else np.nan
        demand_rmse = float(np.sqrt(np.mean(demand_residual ** 2))) if len(demand_residual) > 100 else np.nan
        total_rmse = float(np.sqrt(np.mean(residual ** 2)))

        # Bias (systematic error)
        supply_bias = float(np.mean(supply_residual)) if len(supply_residual) > 100 else np.nan
        demand_bias = float(np.mean(demand_residual)) if len(demand_residual) > 100 else np.nan
        total_bias = float(np.mean(residual))

        # Autocorrelation (persistence of error)
        if len(supply_residual) > 100:
            supply_autocorr = float(np.corrcoef(supply_residual[:-1],
                                                supply_residual[1:])[0, 1])
        else:
            supply_autocorr = np.nan
        if len(demand_residual) > 100:
            demand_autocorr = float(np.corrcoef(demand_residual[:-1],
                                                demand_residual[1:])[0, 1])
        else:
            demand_autocorr = np.nan

        # Hour-of-day pattern in each loss
        supply_hourly = {}
        demand_hourly = {}
        for h in range(24):
            h_mask = (hours >= h) & (hours < h + 1)
            s = residual[supply_mask & h_mask]
            d = residual[demand_mask & h_mask]
            if len(s) > 10:
                supply_hourly[h] = round(float(np.mean(np.abs(s))), 2)
            if len(d) > 10:
                demand_hourly[h] = round(float(np.mean(np.abs(d))), 2)

        results[name] = {
            'total_rmse': round(total_rmse, 2),
            'supply_rmse': round(supply_rmse, 2) if not np.isnan(supply_rmse) else None,
            'demand_rmse': round(demand_rmse, 2) if not np.isnan(demand_rmse) else None,
            'total_bias': round(total_bias, 3),
            'supply_bias': round(supply_bias, 3) if not np.isnan(supply_bias) else None,
            'demand_bias': round(demand_bias, 3) if not np.isnan(demand_bias) else None,
            'supply_autocorr': round(supply_autocorr, 3) if not np.isnan(supply_autocorr) else None,
            'demand_autocorr': round(demand_autocorr, 3) if not np.isnan(demand_autocorr) else None,
            'n_supply_steps': int(np.sum(supply_mask)),
            'n_demand_steps': int(np.sum(demand_mask)),
            'supply_frac': round(float(np.sum(supply_mask)) / len(dg_v), 3),
            'demand_frac': round(float(np.sum(demand_mask)) / len(dg_v), 3),
            'supply_hourly_mae': supply_hourly,
            'demand_hourly_mae': demand_hourly
        }

        s_rmse = f"{supply_rmse:.2f}" if not np.isnan(supply_rmse) else "N/A"
        d_rmse = f"{demand_rmse:.2f}" if not np.isnan(demand_rmse) else "N/A"
        print(f"  {name}: total={total_rmse:.2f} supply={s_rmse} demand={d_rmse} "
              f"(supply {np.sum(supply_mask)/len(dg_v):.0%}, "
              f"demand {np.sum(demand_mask)/len(dg_v):.0%})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        names = sorted([n for n in results if results[n].get('supply_rmse') is not None])

        # Panel 1: Supply vs Demand RMSE
        ax = axes[0, 0]
        s_vals = [results[n]['supply_rmse'] for n in names]
        d_vals = [results[n]['demand_rmse'] for n in names]
        x = np.arange(len(names))
        ax.bar(x - 0.15, s_vals, 0.3, label='Supply RMSE', color='C0',
               edgecolor='black')
        ax.bar(x + 0.15, d_vals, 0.3, label='Demand RMSE', color='C1',
               edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('RMSE (mg/dL per 5min)')
        ax.set_title('Supply vs Demand Error', fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        # Panel 2: Bias
        ax = axes[0, 1]
        s_bias = [results[n]['supply_bias'] or 0 for n in names]
        d_bias = [results[n]['demand_bias'] or 0 for n in names]
        ax.bar(x - 0.15, s_bias, 0.3, label='Supply Bias', color='C0',
               edgecolor='black')
        ax.bar(x + 0.15, d_bias, 0.3, label='Demand Bias', color='C1',
               edgecolor='black')
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Mean Error (mg/dL per 5min)')
        ax.set_title('Supply vs Demand Bias', fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        # Panel 3: Autocorrelation
        ax = axes[1, 0]
        s_ac = [results[n]['supply_autocorr'] or 0 for n in names]
        d_ac = [results[n]['demand_autocorr'] or 0 for n in names]
        ax.bar(x - 0.15, s_ac, 0.3, label='Supply Autocorr', color='C0',
               edgecolor='black')
        ax.bar(x + 0.15, d_ac, 0.3, label='Demand Autocorr', color='C1',
               edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Lag-1 Autocorrelation')
        ax.set_title('Error Persistence', fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        # Panel 4: Supply fraction vs TIR
        ax = axes[1, 1]
        supply_frac = [results[n]['supply_frac'] for n in names]
        # We don't have TIR in results directly, compute from names
        tir_vals = []
        for n in names:
            p_match = [p for p in patients if p['name'] == n]
            if p_match:
                g_n = p_match[0]['df']['glucose'].values
                g_n = g_n[~np.isnan(g_n)]
                tir_vals.append(float(np.mean((g_n >= 70) & (g_n <= 180))))
            else:
                tir_vals.append(0.7)

        ax.scatter(supply_frac, tir_vals, s=200, c='C2', edgecolors='black',
                  zorder=5)
        for i, n in enumerate(names):
            ax.annotate(n, (supply_frac[i], tir_vals[i]),
                       fontsize=11, fontweight='bold',
                       ha='center', va='bottom', xytext=(0, 8),
                       textcoords='offset points')
        ax.set_xlabel('Fraction of Time in Supply-Dominated State', fontsize=11)
        ax.set_ylabel('TIR', fontsize=11)
        ax.set_title('Supply Dominance vs Control Quality', fontweight='bold')
        ax.grid(True, alpha=0.3)

        fig.suptitle('EXP-2087: Supply-Demand Loss Decomposition',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pheno-fig07-supply-demand.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig07-supply-demand.png")

    output = {'experiment': 'EXP-2087',
              'title': 'Supply-Demand Loss Decomposition',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2087_supply_demand.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2088: Actionable Summary ─────────────────────────────────────
def exp_2088_actionable_summary():
    """One-page therapy card per patient — synthesis of all findings."""
    print("\n═══ EXP-2088: Actionable Summary ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        n_days = len(g_valid) / STEPS_PER_DAY

        # Core metrics
        mean_g = float(np.mean(g_valid))
        tir = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
        tbr = float(np.mean(g_valid < 70))
        tar = float(np.mean(g_valid > 180))
        cv = float(np.std(g_valid) / mean_g * 100)
        eA1c = (mean_g + 46.7) / 28.7

        # Profile settings
        isf_schedule = df.attrs.get('isf_schedule', [])
        cr_schedule = df.attrs.get('cr_schedule', [])
        basal_schedule = df.attrs.get('basal_schedule', [])

        profile_isf = []
        for entry in isf_schedule:
            v = entry.get('value', 0)
            if v < 15:
                v *= 18.0182
            profile_isf.append(round(v, 1))
        profile_cr = [entry.get('value', 0) for entry in cr_schedule]
        profile_basal = [entry.get('value', 0) for entry in basal_schedule]

        # AID behavior
        enacted = df['enacted_rate'].values
        enacted_valid = enacted[~np.isnan(enacted)]
        suspend_rate = float(np.mean(enacted_valid == 0)) if len(enacted_valid) > 0 else 0

        # Hypo events
        hypo_mask = g_valid < 70
        hypo_transitions = np.diff(hypo_mask.astype(int))
        n_hypo = int(np.sum(hypo_transitions == 1))
        hypo_per_week = n_hypo / n_days * 7

        # Strengths and weaknesses
        strengths = []
        weaknesses = []

        if tir >= 0.70:
            strengths.append(f"TIR {tir:.0%} meets target")
        else:
            weaknesses.append(f"TIR {tir:.0%} below 70% target")

        if tbr <= 0.04:
            strengths.append(f"TBR {tbr:.1%} within safe range")
        else:
            weaknesses.append(f"TBR {tbr:.1%} exceeds 4% safety limit")

        if cv <= 36:
            strengths.append(f"CV {cv:.0f}% shows stable glucose")
        else:
            weaknesses.append(f"CV {cv:.0f}% high variability")

        if suspend_rate < 0.5:
            strengths.append(f"Loop active {1-suspend_rate:.0%} of time")
        else:
            weaknesses.append(f"Loop suspended {suspend_rate:.0%} (over-basaled?)")

        # Top 3 recommendations
        recommendations = []
        if tbr > 0.04:
            recommendations.append("SAFETY: Increase ISF to reduce overcorrection hypos")
        if suspend_rate > 0.7:
            recommendations.append("BASAL: Reduce basal rate (loop suspending >70%)")
        if tar > 0.30:
            recommendations.append("HYPERGLYCEMIA: Reduce CR for more aggressive meal coverage")
        if tar > 0.25 and tir < 0.70:
            recommendations.append("OVERALL: Settings need comprehensive review")
        if len(recommendations) == 0:
            recommendations.append("MONITOR: Settings adequate — watch for drift")

        results[name] = {
            'n_days': round(n_days, 0),
            'mean_glucose': round(mean_g, 1),
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3),
            'cv': round(cv, 1),
            'eA1c': round(eA1c, 1),
            'suspend_rate': round(suspend_rate, 3),
            'hypo_per_week': round(hypo_per_week, 1),
            'profile_isf_values': profile_isf,
            'profile_cr_values': profile_cr,
            'profile_basal_values': profile_basal,
            'n_isf_periods': len(isf_schedule),
            'n_cr_periods': len(cr_schedule),
            'n_basal_periods': len(basal_schedule),
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommendations': recommendations[:3]
        }

        status = "✓" if tir >= 0.70 and tbr <= 0.04 else "✗"
        print(f"  {name}: {status} TIR={tir:.0%} TBR={tbr:.1%} eA1c={eA1c:.1f} "
              f"→ {recommendations[0][:50]}")

    # Population summary
    meeting_both = sum(1 for r in results.values()
                       if r['tir'] >= 0.70 and r['tbr'] <= 0.04)
    print(f"\n  Population: {meeting_both}/11 meet both TIR≥70% AND TBR≤4%")

    if MAKE_FIGS:
        # Summary dashboard
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        names = sorted(results.keys())
        x = np.arange(len(names))

        # TIR overview
        ax = axes[0, 0]
        tir_vals = [results[n]['tir'] * 100 for n in names]
        colors = ['green' if v >= 70 else 'orange' if v >= 50 else 'red'
                  for v in tir_vals]
        ax.bar(x, tir_vals, color=colors, edgecolor='black')
        ax.axhline(70, color='green', linestyle='--', label='Target')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR (%)')
        ax.set_title('Time in Range', fontweight='bold')
        ax.set_ylim(0, 100)
        ax.legend()

        # TBR overview
        ax = axes[0, 1]
        tbr_vals = [results[n]['tbr'] * 100 for n in names]
        colors = ['green' if v <= 4 else 'orange' if v <= 8 else 'red'
                  for v in tbr_vals]
        ax.bar(x, tbr_vals, color=colors, edgecolor='black')
        ax.axhline(4, color='red', linestyle='--', label='Safety limit')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TBR (%)')
        ax.set_title('Time Below Range', fontweight='bold')
        ax.legend()

        # Suspend rate
        ax = axes[1, 0]
        suspend_vals = [results[n]['suspend_rate'] * 100 for n in names]
        colors = ['green' if v < 50 else 'orange' if v < 70 else 'red'
                  for v in suspend_vals]
        ax.bar(x, suspend_vals, color=colors, edgecolor='black')
        ax.axhline(50, color='orange', linestyle='--', label='Concern threshold')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Suspend Rate (%)')
        ax.set_title('Loop Suspension Rate', fontweight='bold')
        ax.legend()

        # Recommendations count
        ax = axes[1, 1]
        n_weak = [len(results[n]['weaknesses']) for n in names]
        n_rec = [len(results[n]['recommendations']) for n in names]
        ax.bar(x - 0.15, n_weak, 0.3, label='Weaknesses', color='salmon',
               edgecolor='black')
        ax.bar(x + 0.15, n_rec, 0.3, label='Recommendations', color='steelblue',
               edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Count')
        ax.set_title('Issues & Recommendations', fontweight='bold')
        ax.legend()

        fig.suptitle('EXP-2088: Patient Therapy Summary Dashboard',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pheno-fig08-summary.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pheno-fig08-summary.png")

    output = {'experiment': 'EXP-2088', 'title': 'Actionable Summary',
              'population': {'meeting_tir_and_tbr': meeting_both,
                           'total_patients': len(results)},
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2088_summary.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2081–2088: Cross-Patient Phenotyping & Intervention Targeting")
    print("=" * 60)

    r1 = exp_2081_glycemic_fingerprint()
    r2 = exp_2082_aid_behavior_clustering()
    r3 = exp_2083_setting_mismatch()
    r4 = exp_2084_intervention_ranking()
    r5 = exp_2085_risk_stratification()
    r6 = exp_2086_temporal_stability()
    r7 = exp_2087_supply_demand_decomposition()
    r8 = exp_2088_actionable_summary()

    print("\n" + "=" * 60)
    print(f"Results: 8/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/pheno-fig01–08")
    print("=" * 60)
