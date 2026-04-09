#!/usr/bin/env python3
"""EXP-1591–1598: Meal-Response Clustering

Batch 7: Group meals by absorption profile, score CR per cluster,
separate bolus-timing effects from CR effectiveness.

Depends on:
  - exp_metabolic_441.compute_supply_demand()
  - production/meal_detector.detect_meal_events(), classify_meal_response()
  - production/types.MetabolicState, PatientProfile, DetectedMeal
  - exp_clinical_1531._fidelity_grade() for context
"""

import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

# Imports
from cgmencode import exp_metabolic_441
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.production.types import (
    PatientData, MetabolicState, PatientProfile,
)
from cgmencode.production.meal_detector import (
    detect_meal_events, classify_meal_response, build_meal_history,
)


def _load_patients():
    """Load patient cohort."""
    patients = load_patients(patients_dir=str(PATIENTS_DIR), max_patients=None)
    return patients


def _build_metabolic(sd, glucose):
    """Build MetabolicState from supply-demand dict."""
    n = len(glucose)
    net_flux = np.asarray(sd.get('net_flux', sd.get('net', np.zeros(n))), dtype=float)
    demand = np.asarray(sd.get('insulin_demand', sd.get('demand', np.zeros(n))), dtype=float)
    carb_s = np.asarray(sd.get('carb_supply', np.zeros(n)), dtype=float)
    hepatic = np.asarray(sd.get('hepatic_supply', sd.get('hepatic', np.zeros(n))), dtype=float)
    supply = hepatic + carb_s
    residual = np.zeros(n, dtype=float)
    if n > 1:
        dBG = np.diff(glucose)
        residual[:n-1] = dBG - net_flux[:n-1]
    return MetabolicState(
        supply=supply[:n], demand=demand[:n], hepatic=hepatic[:n],
        carb_supply=carb_s[:n], net_flux=net_flux[:n], residual=residual[:n],
    )


def _extract_meal_features(glucose, metabolic, hours, meal, profile_isf=50.0,
                           profile_cr=10.0):
    """Extract per-meal feature vector for clustering."""
    idx = meal.index
    n = len(glucose)
    post_window = min(n, idx + 3 * STEPS_PER_HOUR)  # 3h post-meal
    pre_start = max(0, idx - 6)  # 30 min pre-meal

    # Glucose features
    bg_start = float(np.nanmean(glucose[pre_start:idx+1])) if idx > 0 else float(glucose[idx])
    post_g = glucose[idx:post_window]
    if len(post_g) < 6:
        return None

    bg_peak = float(np.nanmax(post_g))
    excursion = bg_peak - bg_start
    peak_offset = int(np.nanargmax(post_g))
    peak_time_min = peak_offset * 5.0

    # Return-to-baseline time
    returned = np.where(post_g[peak_offset:] <= bg_start + 10)[0]
    rtb_min = float(returned[0] * 5.0 + peak_time_min) if len(returned) > 0 else float(len(post_g) * 5.0)

    # Pre-meal glucose features
    pre_g = glucose[pre_start:idx+1]
    pre_trend = float(pre_g[-1] - pre_g[0]) / max(1, len(pre_g)) if len(pre_g) > 1 else 0.0
    pre_cv = float(np.nanstd(pre_g) / max(1, np.nanmean(pre_g))) if len(pre_g) > 1 else 0.0

    # Metabolic features (demand/supply in post-meal window)
    early_end = min(n, idx + 2 * STEPS_PER_HOUR)
    late_start = idx + 2 * STEPS_PER_HOUR
    late_end = min(n, idx + 5 * STEPS_PER_HOUR)

    early_demand = float(np.nansum(np.abs(metabolic.demand[idx:early_end])))
    late_demand = float(np.nansum(np.abs(metabolic.demand[late_start:late_end]))) if late_start < n else 0.0
    tail_ratio = late_demand / max(early_demand, 0.01)

    early_supply = float(np.nansum(metabolic.carb_supply[idx:early_end]))
    total_supply = float(np.nansum(metabolic.carb_supply[idx:post_window]))

    # Residual integral (burst magnitude)
    resid_integral = float(np.nansum(metabolic.residual[idx:post_window]))

    # IOB at meal time (from demand as proxy)
    iob_at_meal = float(np.nanmean(np.abs(metabolic.demand[pre_start:idx+1]))) if idx > 0 else 0.0

    # Net flux dynamics
    net_flux_early = float(np.nanmean(metabolic.net_flux[idx:early_end]))
    net_flux_post = float(np.nanmean(metabolic.net_flux[idx:post_window]))

    # Area under glucose curve above baseline
    auc_above = float(np.nansum(np.clip(post_g - bg_start, 0, None))) * 5.0  # mg·min/dL

    # Bolus timing proxy: how fast does demand ramp after meal?
    demand_ramp_window = min(6, post_window - idx)
    if demand_ramp_window > 1:
        demand_ramp = float(np.nanmean(np.diff(np.abs(metabolic.demand[idx:idx+demand_ramp_window]))))
    else:
        demand_ramp = 0.0

    return {
        'patient': None,  # filled by caller
        'meal_index': idx,
        'hour_of_day': float(hours[idx]) if idx < len(hours) else meal.hour_of_day,
        'meal_window': meal.window if hasattr(meal, 'window') else 'unknown',
        'announced': meal.announced,
        'estimated_carbs_g': meal.estimated_carbs_g,
        'confidence': meal.confidence,
        # Glucose response features (primary for clustering)
        'bg_start': bg_start,
        'excursion': excursion,
        'peak_time_min': peak_time_min,
        'rtb_min': rtb_min,
        'auc_above': auc_above,
        'pre_trend': pre_trend,
        'pre_cv': pre_cv,
        # Metabolic features
        'early_demand': early_demand,
        'tail_ratio': tail_ratio,
        'early_supply': early_supply,
        'total_supply': total_supply,
        'resid_integral': resid_integral,
        'iob_at_meal': iob_at_meal,
        'net_flux_early': net_flux_early,
        'net_flux_post': net_flux_post,
        'demand_ramp': demand_ramp,
    }


def _save_result(exp_id, data, elapsed):
    """Save experiment result."""
    out = RESULTS_DIR / f'exp-{exp_id}_meal_clustering.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ Saved → {out}  ({elapsed:.1f}s)")


# ============================================================
# EXP-1591: Meal Feature Extraction
# ============================================================
def exp_1591(patients):
    """Extract per-meal feature vectors across all patients."""
    print("\n" + "─" * 60)
    print("EXP-1591: Meal Feature Extraction")
    print("─" * 60)
    t0 = time.time()

    all_meals = []
    patient_summaries = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)
            hours = np.arange(n) % STEPS_PER_DAY / STEPS_PER_HOUR
            timestamps = np.arange(n) * 5 * 60 * 1000

            sd = exp_metabolic_441.compute_supply_demand(df, p['pk'])
            metabolic = _build_metabolic(sd, glucose)

            profile = PatientProfile(
                isf_schedule=[{'time': '00:00', 'value': 50.0}],
                cr_schedule=[{'time': '00:00', 'value': 10.0}],
                basal_schedule=[{'time': '00:00', 'value': 1.0}],
                dia_hours=5.0, target_low=70, target_high=180,
            )

            meals = detect_meal_events(glucose, metabolic, hours, timestamps, profile)

            n_meals = len(meals)
            n_announced = sum(1 for m in meals if m.announced)

            patient_meals = []
            for m in meals:
                feat = _extract_meal_features(glucose, metabolic, hours, m)
                if feat is not None:
                    feat['patient'] = p['name']
                    patient_meals.append(feat)

            all_meals.extend(patient_meals)

            patient_summaries[p['name']] = {
                'n_detected': n_meals,
                'n_announced': n_announced,
                'n_features_extracted': len(patient_meals),
                'unannounced_frac': 1 - n_announced / max(n_meals, 1),
                'mean_excursion': float(np.nanmean([m['excursion'] for m in patient_meals])) if patient_meals else 0,
                'mean_peak_time': float(np.nanmean([m['peak_time_min'] for m in patient_meals])) if patient_meals else 0,
            }

            ann_str = f"{n_announced}/{n_meals} announced"
            exc = patient_summaries[p['name']]['mean_excursion']
            pk = patient_summaries[p['name']]['mean_peak_time']
            print(f"  {p['name']}: {n_meals} meals ({ann_str})  "
                  f"Mean excursion={exc:.0f}mg  Peak={pk:.0f}min  "
                  f"Features={len(patient_meals)}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            patient_summaries[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1591',
        'title': 'Meal Feature Extraction',
        'total_meals': len(all_meals),
        'patients': patient_summaries,
        'feature_names': list(all_meals[0].keys()) if all_meals else [],
    }
    _save_result(1591, result, time.time() - t0)
    return all_meals


# ============================================================
# EXP-1592: Meal-Response Clustering
# ============================================================
def exp_1592(all_meals):
    """Cluster meals by absorption profile using KMeans."""
    print("\n" + "─" * 60)
    print("EXP-1592: Meal-Response Clustering")
    print("─" * 60)
    t0 = time.time()

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score

    # Build feature matrix for clustering
    cluster_features = [
        'excursion', 'peak_time_min', 'rtb_min', 'auc_above',
        'tail_ratio', 'demand_ramp', 'estimated_carbs_g',
    ]

    rows = []
    valid_meals = []
    for m in all_meals:
        feat = [m.get(f, 0) for f in cluster_features]
        if all(np.isfinite(v) for v in feat):
            rows.append(feat)
            valid_meals.append(m)

    if len(rows) < 20:
        print("  INSUFFICIENT DATA for clustering")
        _save_result(1592, {'error': 'insufficient_data', 'n_valid': len(rows)}, time.time() - t0)
        return all_meals, None

    X = np.array(rows)
    scaler = StandardScaler()
    X_norm = scaler.fit_transform(X)

    # Test k=2..6 with silhouette score
    sil_scores = {}
    best_k = 3
    best_sil = -1

    for k in range(2, 7):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_norm)
        sil = silhouette_score(X_norm, labels)
        sil_scores[k] = float(sil)
        if sil > best_sil:
            best_sil = sil
            best_k = k
        print(f"  k={k}: silhouette={sil:.3f}")

    # Fit best model
    km_best = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km_best.fit_predict(X_norm)
    print(f"  Best k={best_k} (silhouette={best_sil:.3f})")

    # Characterize clusters
    cluster_profiles = {}
    for c in range(best_k):
        mask = labels == c
        cluster_meals = [valid_meals[i] for i in range(len(valid_meals)) if mask[i]]
        n_c = int(mask.sum())

        profile = {}
        for feat in cluster_features:
            vals = [m[feat] for m in cluster_meals if np.isfinite(m.get(feat, float('nan')))]
            profile[feat] = {
                'mean': float(np.mean(vals)) if vals else 0,
                'std': float(np.std(vals)) if vals else 0,
                'median': float(np.median(vals)) if vals else 0,
            }

        # Determine cluster label based on characteristics
        exc = profile['excursion']['mean']
        pk_time = profile['peak_time_min']['mean']
        tail = profile['tail_ratio']['mean']
        rtb = profile['rtb_min']['mean']

        # Label based on primary distinguishing feature (excursion magnitude)
        if exc < 30:
            label = 'flat_response'
        elif exc < 60:
            label = 'controlled_rise'
        elif pk_time < 45:
            label = 'fast_spike'
        elif exc > 90:
            label = 'high_excursion'
        elif pk_time > 80:
            label = 'delayed_peak'
        else:
            label = 'moderate'

        # Announced fraction
        ann_frac = sum(1 for m in cluster_meals if m['announced']) / max(n_c, 1)

        # Patient distribution
        patient_dist = {}
        for m in cluster_meals:
            patient_dist[m['patient']] = patient_dist.get(m['patient'], 0) + 1

        cluster_profiles[c] = {
            'label': label,
            'n_meals': n_c,
            'fraction': n_c / len(valid_meals),
            'announced_frac': ann_frac,
            'features': profile,
            'patient_distribution': patient_dist,
        }

        print(f"  Cluster {c} ({label}): n={n_c} ({n_c/len(valid_meals)*100:.0f}%)  "
              f"excursion={exc:.0f}mg  peak={pk_time:.0f}min  "
              f"tail={tail:.2f}  ann={ann_frac:.0%}")

    # Assign cluster labels back to meals
    for i, m in enumerate(valid_meals):
        m['cluster'] = int(labels[i])
        m['cluster_label'] = cluster_profiles[labels[i]]['label']

    result = {
        'experiment': 'EXP-1592',
        'title': 'Meal-Response Clustering',
        'n_valid_meals': len(valid_meals),
        'best_k': best_k,
        'silhouette_scores': sil_scores,
        'best_silhouette': best_sil,
        'cluster_profiles': cluster_profiles,
        'feature_names': cluster_features,
    }
    _save_result(1592, result, time.time() - t0)
    return valid_meals, cluster_profiles


# ============================================================
# EXP-1593: Cluster-Specific CR Effectiveness
# ============================================================
def exp_1593(meals_with_clusters, cluster_profiles):
    """Compute CR effectiveness per cluster."""
    print("\n" + "─" * 60)
    print("EXP-1593: Cluster-Specific CR Effectiveness")
    print("─" * 60)
    t0 = time.time()

    if not cluster_profiles:
        print("  SKIPPED — no cluster profiles available")
        _save_result(1593, {'error': 'no_clusters'}, time.time() - t0)
        return

    # For each cluster, compute how well the "standard" CR works
    # CR effectiveness = how close excursion is to target (0 = perfect)
    # Target excursion after perfect bolus: ~30-50 mg/dL (physiological minimum)
    TARGET_EXCURSION = 40.0  # mg/dL ideal post-meal excursion

    cluster_cr = {}
    for c_id, c_prof in cluster_profiles.items():
        c_meals = [m for m in meals_with_clusters if m.get('cluster') == c_id]
        if not c_meals:
            continue

        # Separate announced (bolused) vs unannounced
        announced = [m for m in c_meals if m['announced']]
        unannounced = [m for m in c_meals if not m['announced']]

        # For announced meals: CR effectiveness = how close excursion to target
        ann_excursions = [m['excursion'] for m in announced if np.isfinite(m['excursion'])]
        unann_excursions = [m['excursion'] for m in unannounced if np.isfinite(m['excursion'])]

        # CR effectiveness ratio: actual_excursion / expected_from_carbs
        cr_ratios = []
        for m in announced:
            if m['estimated_carbs_g'] > 5 and np.isfinite(m['excursion']):
                # Expected excursion = carbs * (ISF/CR) for unboosted
                expected = m['estimated_carbs_g'] * (50.0 / 10.0)  # ISF/CR default
                ratio = m['excursion'] / max(expected, 1)
                cr_ratios.append(ratio)

        # AUC-based CR score: lower AUC = better bolus coverage
        ann_aucs = [m['auc_above'] for m in announced if np.isfinite(m.get('auc_above', float('nan')))]
        unann_aucs = [m['auc_above'] for m in unannounced if np.isfinite(m.get('auc_above', float('nan')))]

        cluster_cr[c_id] = {
            'label': c_prof['label'],
            'n_announced': len(announced),
            'n_unannounced': len(unannounced),
            'announced_mean_excursion': float(np.mean(ann_excursions)) if ann_excursions else None,
            'unannounced_mean_excursion': float(np.mean(unann_excursions)) if unann_excursions else None,
            'excursion_delta': (float(np.mean(unann_excursions)) - float(np.mean(ann_excursions)))
                             if ann_excursions and unann_excursions else None,
            'cr_ratio_mean': float(np.mean(cr_ratios)) if cr_ratios else None,
            'cr_ratio_std': float(np.std(cr_ratios)) if cr_ratios else None,
            'announced_auc_mean': float(np.mean(ann_aucs)) if ann_aucs else None,
            'unannounced_auc_mean': float(np.mean(unann_aucs)) if unann_aucs else None,
            'bolus_benefit_pct': (1 - float(np.mean(ann_excursions)) / max(float(np.mean(unann_excursions)), 1)) * 100
                                if ann_excursions and unann_excursions and np.mean(unann_excursions) > 0 else None,
        }

        label = c_prof['label']
        ann_exc = cluster_cr[c_id]['announced_mean_excursion']
        unann_exc = cluster_cr[c_id]['unannounced_mean_excursion']
        benefit = cluster_cr[c_id]['bolus_benefit_pct']
        cr_r = cluster_cr[c_id]['cr_ratio_mean']
        print(f"  Cluster {c_id} ({label}): "
              f"Ann excursion={ann_exc:.0f}mg  "
              f"Unann={unann_exc:.0f}mg  "
              f"Bolus benefit={benefit:+.0f}%  "
              f"CR ratio={cr_r:.2f}" if ann_exc and unann_exc and benefit is not None and cr_r else
              f"  Cluster {c_id} ({label}): insufficient announced meals")

    result = {
        'experiment': 'EXP-1593',
        'title': 'Cluster-Specific CR Effectiveness',
        'cluster_cr': cluster_cr,
    }
    _save_result(1593, result, time.time() - t0)
    return cluster_cr


# ============================================================
# EXP-1594: Bolus Timing vs CR Disentanglement
# ============================================================
def exp_1594(meals_with_clusters, patients):
    """Separate bolus-timing effects from CR dose effects."""
    print("\n" + "─" * 60)
    print("EXP-1594: Bolus Timing vs CR Disentanglement")
    print("─" * 60)
    t0 = time.time()

    # Strategy: For announced meals, compare early-bolus vs late-bolus effects
    # Early bolus = high demand_ramp (insulin hits fast)
    # Late bolus = low demand_ramp (insulin lags)

    announced = [m for m in meals_with_clusters if m.get('announced', False)]

    if len(announced) < 20:
        print("  INSUFFICIENT announced meals for timing analysis")
        _save_result(1594, {'error': 'insufficient_data', 'n_announced': len(announced)}, time.time() - t0)
        return

    # Split by demand ramp (proxy for bolus timing)
    ramps = [m['demand_ramp'] for m in announced if np.isfinite(m['demand_ramp'])]
    median_ramp = float(np.median(ramps))

    early_bolus = [m for m in announced if m['demand_ramp'] >= median_ramp]
    late_bolus = [m for m in announced if m['demand_ramp'] < median_ramp]

    # Compare excursions
    early_exc = [m['excursion'] for m in early_bolus if np.isfinite(m['excursion'])]
    late_exc = [m['excursion'] for m in late_bolus if np.isfinite(m['excursion'])]
    early_pk = [m['peak_time_min'] for m in early_bolus if np.isfinite(m['peak_time_min'])]
    late_pk = [m['peak_time_min'] for m in late_bolus if np.isfinite(m['peak_time_min'])]
    early_auc = [m['auc_above'] for m in early_bolus if np.isfinite(m.get('auc_above', float('nan')))]
    late_auc = [m['auc_above'] for m in late_bolus if np.isfinite(m.get('auc_above', float('nan')))]

    # Also analyze by cluster
    per_cluster = {}
    for m in announced:
        cl = m.get('cluster_label', 'unknown')
        if cl not in per_cluster:
            per_cluster[cl] = {'early': [], 'late': []}
        if m['demand_ramp'] >= median_ramp:
            per_cluster[cl]['early'].append(m['excursion'])
        else:
            per_cluster[cl]['late'].append(m['excursion'])

    timing_by_cluster = {}
    for cl, data in per_cluster.items():
        e_mean = float(np.mean(data['early'])) if data['early'] else None
        l_mean = float(np.mean(data['late'])) if data['late'] else None
        timing_by_cluster[cl] = {
            'early_bolus_excursion': e_mean,
            'late_bolus_excursion': l_mean,
            'timing_effect': (l_mean - e_mean) if e_mean and l_mean else None,
            'n_early': len(data['early']),
            'n_late': len(data['late']),
        }

    # Variance decomposition: how much of excursion variance is timing vs dose?
    from sklearn.linear_model import LinearRegression

    feat_timing = np.array([[m['demand_ramp']] for m in announced
                            if np.isfinite(m['demand_ramp']) and np.isfinite(m['excursion'])])
    feat_dose = np.array([[m['estimated_carbs_g']] for m in announced
                          if np.isfinite(m['demand_ramp']) and np.isfinite(m['excursion'])])
    feat_both = np.column_stack([feat_timing, feat_dose]) if len(feat_timing) > 0 else np.array([])
    y = np.array([m['excursion'] for m in announced
                  if np.isfinite(m['demand_ramp']) and np.isfinite(m['excursion'])])

    r2_timing = 0.0
    r2_dose = 0.0
    r2_both = 0.0
    if len(y) > 10:
        lr_t = LinearRegression().fit(feat_timing, y)
        r2_timing = float(lr_t.score(feat_timing, y))
        lr_d = LinearRegression().fit(feat_dose, y)
        r2_dose = float(lr_d.score(feat_dose, y))
        lr_b = LinearRegression().fit(feat_both, y)
        r2_both = float(lr_b.score(feat_both, y))

    print(f"  Announced meals: {len(announced)}")
    print(f"  Median demand ramp: {median_ramp:.4f}")
    print(f"  Early bolus: n={len(early_bolus)}  excursion={np.mean(early_exc):.0f}±{np.std(early_exc):.0f}mg  "
          f"peak={np.mean(early_pk):.0f}min")
    print(f"  Late bolus:  n={len(late_bolus)}  excursion={np.mean(late_exc):.0f}±{np.std(late_exc):.0f}mg  "
          f"peak={np.mean(late_pk):.0f}min")
    print(f"  Timing effect: {np.mean(late_exc) - np.mean(early_exc):+.0f}mg excursion")
    print(f"  Variance explained: timing R²={r2_timing:.3f}  dose R²={r2_dose:.3f}  both R²={r2_both:.3f}")

    for cl, td in timing_by_cluster.items():
        te = td.get('timing_effect')
        print(f"  {cl}: timing effect={te:+.0f}mg" if te is not None else f"  {cl}: insufficient data")

    result = {
        'experiment': 'EXP-1594',
        'title': 'Bolus Timing vs CR Disentanglement',
        'n_announced': len(announced),
        'median_demand_ramp': median_ramp,
        'early_bolus': {
            'n': len(early_bolus),
            'mean_excursion': float(np.mean(early_exc)),
            'std_excursion': float(np.std(early_exc)),
            'mean_peak_time': float(np.mean(early_pk)),
            'mean_auc': float(np.mean(early_auc)) if early_auc else None,
        },
        'late_bolus': {
            'n': len(late_bolus),
            'mean_excursion': float(np.mean(late_exc)),
            'std_excursion': float(np.std(late_exc)),
            'mean_peak_time': float(np.mean(late_pk)),
            'mean_auc': float(np.mean(late_auc)) if late_auc else None,
        },
        'timing_effect_mg': float(np.mean(late_exc) - np.mean(early_exc)),
        'variance_decomposition': {
            'r2_timing_only': r2_timing,
            'r2_dose_only': r2_dose,
            'r2_both': r2_both,
        },
        'timing_by_cluster': timing_by_cluster,
    }
    _save_result(1594, result, time.time() - t0)
    return result


# ============================================================
# EXP-1595: Cross-Patient Cluster Transferability
# ============================================================
def exp_1595(meals_with_clusters, cluster_profiles):
    """Test whether meal clusters generalize across patients."""
    print("\n" + "─" * 60)
    print("EXP-1595: Cross-Patient Cluster Transferability")
    print("─" * 60)
    t0 = time.time()

    if not cluster_profiles:
        print("  SKIPPED — no cluster profiles")
        _save_result(1595, {'error': 'no_clusters'}, time.time() - t0)
        return

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score, adjusted_rand_score

    cluster_features = [
        'excursion', 'peak_time_min', 'rtb_min', 'auc_above',
        'tail_ratio', 'demand_ramp', 'estimated_carbs_g',
    ]

    # Group meals by patient
    by_patient = {}
    for m in meals_with_clusters:
        p = m['patient']
        if p not in by_patient:
            by_patient[p] = []
        by_patient[p].append(m)

    # Leave-one-patient-out: train on N-1 patients, predict on held-out
    patient_names = sorted(by_patient.keys())
    transfer_results = {}

    for holdout in patient_names:
        train_meals = [m for p, meals in by_patient.items() for m in meals if p != holdout]
        test_meals = by_patient.get(holdout, [])

        if len(test_meals) < 5 or len(train_meals) < 20:
            transfer_results[holdout] = {'error': 'insufficient_data'}
            continue

        # Build feature matrices
        def make_X(meal_list):
            rows = []
            valid = []
            for m in meal_list:
                feat = [m.get(f, 0) for f in cluster_features]
                if all(np.isfinite(v) for v in feat):
                    rows.append(feat)
                    valid.append(m)
            return np.array(rows) if rows else np.array([]).reshape(0, len(cluster_features)), valid

        X_train, train_valid = make_X(train_meals)
        X_test, test_valid = make_X(test_meals)

        if len(X_train) < 20 or len(X_test) < 3:
            transfer_results[holdout] = {'error': 'insufficient_valid_features'}
            continue

        scaler = StandardScaler().fit(X_train)
        X_train_n = scaler.transform(X_train)
        X_test_n = scaler.transform(X_test)

        n_clusters = len(cluster_profiles)
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        train_labels = km.fit_predict(X_train_n)
        test_labels = km.predict(X_test_n)

        # Compare test labels to global labels
        global_test_labels = np.array([m.get('cluster', -1) for m in test_valid])

        # Silhouette on test set
        if len(set(test_labels)) > 1:
            test_sil = float(silhouette_score(X_test_n, test_labels))
        else:
            test_sil = 0.0

        # Adjusted Rand Index
        if len(set(global_test_labels)) > 1 and len(set(test_labels)) > 1:
            ari = float(adjusted_rand_score(global_test_labels, test_labels))
        else:
            ari = 0.0

        # Cluster distribution comparison
        train_dist = {int(c): int((train_labels == c).sum()) for c in range(n_clusters)}
        test_dist = {int(c): int((test_labels == c).sum()) for c in range(n_clusters)}

        transfer_results[holdout] = {
            'n_test': len(X_test),
            'test_silhouette': test_sil,
            'adjusted_rand_index': ari,
            'train_cluster_dist': train_dist,
            'test_cluster_dist': test_dist,
        }

        print(f"  {holdout}: n={len(X_test)}  sil={test_sil:.3f}  ARI={ari:.3f}")

    # Summary
    valid_results = {k: v for k, v in transfer_results.items() if 'error' not in v}
    if valid_results:
        mean_sil = float(np.mean([v['test_silhouette'] for v in valid_results.values()]))
        mean_ari = float(np.mean([v['adjusted_rand_index'] for v in valid_results.values()]))
        print(f"  Mean transfer silhouette: {mean_sil:.3f}")
        print(f"  Mean ARI: {mean_ari:.3f}")
    else:
        mean_sil = 0.0
        mean_ari = 0.0

    result = {
        'experiment': 'EXP-1595',
        'title': 'Cross-Patient Cluster Transferability',
        'per_patient': transfer_results,
        'mean_silhouette': mean_sil,
        'mean_ari': mean_ari,
        'transferable': mean_sil > 0.15,
    }
    _save_result(1595, result, time.time() - t0)
    return result


# ============================================================
# EXP-1596: Cluster-Aware Recommendations
# ============================================================
def exp_1596(meals_with_clusters, cluster_profiles):
    """Use clusters to improve therapy settings recommendations."""
    print("\n" + "─" * 60)
    print("EXP-1596: Cluster-Aware Recommendations")
    print("─" * 60)
    t0 = time.time()

    if not cluster_profiles:
        print("  SKIPPED — no cluster profiles")
        _save_result(1596, {'error': 'no_clusters'}, time.time() - t0)
        return

    # For each patient, generate cluster-specific recommendations
    by_patient = {}
    for m in meals_with_clusters:
        p = m['patient']
        if p not in by_patient:
            by_patient[p] = []
        by_patient[p].append(m)

    patient_recs = {}
    for pname, meals in sorted(by_patient.items()):
        # Count meals per cluster
        cluster_counts = {}
        cluster_excursions = {}
        cluster_aucs = {}
        for m in meals:
            cl = m.get('cluster_label', 'unknown')
            cluster_counts[cl] = cluster_counts.get(cl, 0) + 1
            if cl not in cluster_excursions:
                cluster_excursions[cl] = []
                cluster_aucs[cl] = []
            if np.isfinite(m['excursion']):
                cluster_excursions[cl].append(m['excursion'])
            if np.isfinite(m.get('auc_above', float('nan'))):
                cluster_aucs[cl].append(m['auc_above'])

        # Generate recommendations per cluster
        recs = []
        for cl, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
            exc_list = cluster_excursions.get(cl, [])
            mean_exc = float(np.mean(exc_list)) if exc_list else 0
            auc_list = cluster_aucs.get(cl, [])
            mean_auc = float(np.mean(auc_list)) if auc_list else 0

            rec = {'cluster': cl, 'n_meals': count, 'mean_excursion': mean_exc, 'mean_auc': mean_auc}

            if mean_exc > 80:
                rec['recommendation'] = 'decrease_cr'
                rec['rationale'] = f'High excursion ({mean_exc:.0f}mg) suggests insufficient bolus coverage'
                rec['priority'] = 'high'
            elif mean_exc > 50:
                rec['recommendation'] = 'consider_prebolus'
                rec['rationale'] = f'Moderate excursion ({mean_exc:.0f}mg) may benefit from earlier bolus timing'
                rec['priority'] = 'medium'
            elif mean_exc < 10:
                rec['recommendation'] = 'increase_cr_or_reduce'
                rec['rationale'] = f'Flat response ({mean_exc:.0f}mg) suggests possible over-bolusing'
                rec['priority'] = 'low'
            else:
                rec['recommendation'] = 'maintain'
                rec['rationale'] = f'Adequate response ({mean_exc:.0f}mg)'
                rec['priority'] = 'none'

            recs.append(rec)

        # Dominant cluster
        dominant = max(cluster_counts, key=cluster_counts.get)
        actionable = [r for r in recs if r['priority'] in ('high', 'medium')]

        patient_recs[pname] = {
            'dominant_cluster': dominant,
            'cluster_distribution': cluster_counts,
            'recommendations': recs,
            'n_actionable': len(actionable),
        }

        act_str = ', '.join(f"{r['cluster']}→{r['recommendation']}" for r in actionable[:3])
        print(f"  {pname}: dominant={dominant}  actionable={len(actionable)}  {act_str}")

    result = {
        'experiment': 'EXP-1596',
        'title': 'Cluster-Aware Recommendations',
        'per_patient': patient_recs,
        'total_actionable': sum(v['n_actionable'] for v in patient_recs.values()),
    }
    _save_result(1596, result, time.time() - t0)
    return result


# ============================================================
# EXP-1597: Temporal Clustering Patterns
# ============================================================
def exp_1597(meals_with_clusters, cluster_profiles):
    """Analyze time-of-day patterns in meal clusters."""
    print("\n" + "─" * 60)
    print("EXP-1597: Temporal Clustering Patterns")
    print("─" * 60)
    t0 = time.time()

    if not cluster_profiles:
        print("  SKIPPED — no cluster profiles")
        _save_result(1597, {'error': 'no_clusters'}, time.time() - t0)
        return

    # Analyze hour-of-day distribution per cluster
    from scipy import stats

    cluster_temporal = {}
    all_hours = [m['hour_of_day'] for m in meals_with_clusters if np.isfinite(m['hour_of_day'])]

    for c_id, c_prof in cluster_profiles.items():
        c_meals = [m for m in meals_with_clusters if m.get('cluster') == c_id]
        hours = [m['hour_of_day'] for m in c_meals if np.isfinite(m['hour_of_day'])]

        if len(hours) < 5:
            cluster_temporal[c_id] = {'error': 'insufficient_data'}
            continue

        # Hour distribution
        hour_hist, _ = np.histogram(hours, bins=24, range=(0, 24))
        peak_hour = int(np.argmax(hour_hist))

        # Circular statistics for meal timing
        radians = np.array(hours) * 2 * np.pi / 24
        mean_cos = float(np.mean(np.cos(radians)))
        mean_sin = float(np.mean(np.sin(radians)))
        mean_angle = float(np.arctan2(mean_sin, mean_cos))
        mean_hour = (mean_angle * 24 / (2 * np.pi)) % 24
        concentration = float(np.sqrt(mean_cos**2 + mean_sin**2))

        # KS test vs overall distribution
        if len(hours) > 10 and len(all_hours) > 10:
            ks_stat, ks_pval = stats.ks_2samp(hours, all_hours)
        else:
            ks_stat, ks_pval = 0.0, 1.0

        # Meal window distribution
        windows = {'breakfast': 0, 'lunch': 0, 'dinner': 0, 'snack': 0}
        for h in hours:
            if 5 <= h < 10:
                windows['breakfast'] += 1
            elif 10 <= h < 14:
                windows['lunch'] += 1
            elif 17 <= h < 21:
                windows['dinner'] += 1
            else:
                windows['snack'] += 1
        total = max(sum(windows.values()), 1)
        window_frac = {k: v / total for k, v in windows.items()}

        cluster_temporal[c_id] = {
            'label': c_prof['label'],
            'n_meals': len(hours),
            'mean_hour': mean_hour,
            'peak_hour': peak_hour,
            'concentration': concentration,
            'hour_histogram': [int(x) for x in hour_hist],
            'ks_stat': float(ks_stat),
            'ks_pval': float(ks_pval),
            'time_dependent': ks_pval < 0.05,
            'window_fractions': window_frac,
        }

        label = c_prof['label']
        time_dep = "YES" if ks_pval < 0.05 else "no"
        dom_window = max(window_frac, key=window_frac.get)
        print(f"  Cluster {c_id} ({label}): mean_hour={mean_hour:.1f}  "
              f"peak={peak_hour}:00  conc={concentration:.2f}  "
              f"time-dep={time_dep} (p={ks_pval:.3f})  dominant={dom_window}")

    # Summary: are clusters time-dependent?
    time_dependent_clusters = sum(1 for v in cluster_temporal.values()
                                  if isinstance(v, dict) and v.get('time_dependent', False))
    total_clusters = len([v for v in cluster_temporal.values() if isinstance(v, dict) and 'error' not in v])

    print(f"  Time-dependent clusters: {time_dependent_clusters}/{total_clusters}")

    result = {
        'experiment': 'EXP-1597',
        'title': 'Temporal Clustering Patterns',
        'cluster_temporal': cluster_temporal,
        'n_time_dependent': time_dependent_clusters,
        'n_total': total_clusters,
    }
    _save_result(1597, result, time.time() - t0)
    return result


# ============================================================
# EXP-1598: Integration Summary
# ============================================================
def exp_1598(all_meals, cluster_profiles, cr_results, timing_results, transfer_results):
    """Summarize meal-clustering insights and production implications."""
    print("\n" + "─" * 60)
    print("EXP-1598: Meal-Response Clustering Summary")
    print("─" * 60)
    t0 = time.time()

    summary = {
        'total_meals_analyzed': len(all_meals),
        'n_patients': len(set(m['patient'] for m in all_meals)),
    }

    # Cluster summary
    if cluster_profiles:
        summary['n_clusters'] = len(cluster_profiles)
        summary['cluster_labels'] = [cp['label'] for cp in cluster_profiles.values()]
        summary['cluster_sizes'] = [cp['n_meals'] for cp in cluster_profiles.values()]

    # CR effectiveness summary
    if cr_results:
        bolus_benefits = [v.get('bolus_benefit_pct') for v in cr_results.values()
                         if v.get('bolus_benefit_pct') is not None]
        summary['mean_bolus_benefit_pct'] = float(np.mean(bolus_benefits)) if bolus_benefits else None

    # Timing summary
    if timing_results:
        summary['timing_r2'] = timing_results.get('variance_decomposition', {}).get('r2_timing_only', 0)
        summary['dose_r2'] = timing_results.get('variance_decomposition', {}).get('r2_dose_only', 0)
        summary['timing_effect_mg'] = timing_results.get('timing_effect_mg', 0)

    # Transfer summary
    if transfer_results:
        summary['transfer_silhouette'] = transfer_results.get('mean_silhouette', 0)
        summary['transfer_ari'] = transfer_results.get('mean_ari', 0)
        summary['clusters_transferable'] = transfer_results.get('transferable', False)

    # Production implications
    implications = []
    if cluster_profiles:
        n_clusters = len(cluster_profiles)
        if n_clusters >= 2:
            implications.append(f"Meal responses cluster into {n_clusters} distinct profiles")
        flat_clusters = [cp for cp in cluster_profiles.values() if cp['label'] == 'flat']
        if flat_clusters:
            flat_pct = sum(cp['n_meals'] for cp in flat_clusters) / max(len(all_meals), 1) * 100
            implications.append(f"Flat responses ({flat_pct:.0f}% of meals) indicate strong AID suppression")

    if timing_results:
        te = timing_results.get('timing_effect_mg', 0)
        if abs(te) > 10:
            implications.append(f"Bolus timing has {te:+.0f}mg excursion impact — pre-bolus advice warranted")

    if transfer_results and transfer_results.get('transferable'):
        implications.append("Clusters transfer across patients — can use population-level models")

    summary['production_implications'] = implications

    for imp in implications:
        print(f"  → {imp}")

    result = {
        'experiment': 'EXP-1598',
        'title': 'Meal-Response Clustering Summary',
        'summary': summary,
    }
    _save_result(1598, result, time.time() - t0)
    return summary


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 70)
    print("EXP-1591-1598: Meal-Response Clustering")
    print("=" * 70)

    patients = _load_patients()
    print(f"Loaded {len(patients)} patients\n")

    # EXP-1591: Extract features
    all_meals = exp_1591(patients)

    # EXP-1592: Cluster
    meals_clustered, cluster_profiles = exp_1592(all_meals)

    # EXP-1593: CR per cluster
    cr_results = exp_1593(meals_clustered, cluster_profiles)

    # EXP-1594: Timing vs dose
    timing_results = exp_1594(meals_clustered, patients)

    # EXP-1595: Cross-patient transfer
    transfer_results = exp_1595(meals_clustered, cluster_profiles)

    # EXP-1596: Cluster-aware recs
    exp_1596(meals_clustered, cluster_profiles)

    # EXP-1597: Temporal patterns
    exp_1597(meals_clustered, cluster_profiles)

    # EXP-1598: Summary
    exp_1598(all_meals, cluster_profiles, cr_results, timing_results, transfer_results)

    print("\n" + "=" * 70)
    print("COMPLETE: 8/8 experiments")
    print("=" * 70)
