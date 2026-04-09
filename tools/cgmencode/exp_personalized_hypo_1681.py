#!/usr/bin/env python3
"""EXP-1681 through EXP-1688: Personalized Hypo-Recovery and Therapy Diagnostics.

Following the rescue carb inference results (EXP-1641–1648), which showed that:
  - Binary rescue detection works (F1=0.91) but magnitude fails (r≈0)
  - Cross-patient transfer fails (LOPO R²=-1.02)
  - 43% of episodes cause post-hypo hyperglycemia

This series investigates:
  1. Within-patient rescue phenotypes (clustering)
  2. Post-hypo hyperglycemia prediction (which episodes overshoot?)
  3. The "demand vacuum" — IOB/demand at nadir vs rebound
  4. Temporal patterns — when do hypos happen? Pre-meal?
  5. Hypo as therapy diagnostic — frequency correlates with ISF/basal settings?
  6. Supply-demand equilibrium restoration time
  7. Hypo cascading — do hypos cluster in time?
  8. Personalized risk profile (integrates all features)

References:
  EXP-1641–1648: Rescue carb inference (detection/estimation disconnect)
  EXP-1631–1636: Corrected supply-demand model
  EXP-1621–1628: Demand diagnosis, glycogen proxy
  EXP-1611–1616: Natural experiment deconfounding
"""

import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats, optimize
from scipy.signal import savgol_filter

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients, _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Hypo episode detection (reuse from EXP-1641 with enrichments) ──────

def find_hypo_episodes_enriched(glucose, carbs, iob, sd_dict, pk_channels,
                                 threshold=70, pre_window=36, post_window=72):
    """Find hypo episodes with extended context for therapy analysis.

    Enhanced from EXP-1641 with:
      - Longer post window (6h instead of 3h) for equilibrium analysis
      - Pre-hypo supply-demand trajectory
      - Glycogen proxy computation
      - Time-of-day encoding
    """
    N = len(glucose)
    supply = sd_dict['supply']
    demand = sd_dict['demand']
    net = sd_dict['net']

    episodes = []
    i = 0
    min_gap = 12  # 1h between episodes

    while i < N - post_window:
        if np.isnan(glucose[i]) or glucose[i] >= threshold:
            i += 1
            continue

        # Find nadir
        nadir_idx = i
        nadir_bg = glucose[i]
        j = i + 1
        while j < min(i + post_window, N):
            if np.isnan(glucose[j]):
                j += 1
                continue
            if glucose[j] < nadir_bg:
                nadir_bg = glucose[j]
                nadir_idx = j
            if glucose[j] > threshold + 30:
                break
            j += 1

        pre_start = max(0, nadir_idx - pre_window)
        post_end = min(N, nadir_idx + post_window)

        if post_end - nadir_idx < 12:  # need at least 1h post
            i = j + min_gap
            continue

        post_bg = glucose[nadir_idx:post_end]
        valid_post = ~np.isnan(post_bg)
        if valid_post.sum() < 12:
            i = j + min_gap
            continue

        # Recovery metrics
        peak_recovery = float(np.nanmax(post_bg))
        rebound = peak_recovery - nadir_bg

        # Time to return above threshold
        recovery_steps = len(post_bg)
        for k in range(1, len(post_bg)):
            if not np.isnan(post_bg[k]) and post_bg[k] >= threshold:
                recovery_steps = k
                break

        # Time to peak
        peak_idx = 0
        for k in range(len(post_bg)):
            if not np.isnan(post_bg[k]) and post_bg[k] == peak_recovery:
                peak_idx = k
                break

        # Announced carbs
        post_carbs = carbs[nadir_idx:post_end]
        announced = float(np.nansum(post_carbs))

        # Pre-hypo context
        pre_iob = float(np.nanmean(iob[pre_start:nadir_idx + 1]))
        iob_at_nadir = float(iob[nadir_idx]) if not np.isnan(iob[nadir_idx]) else pre_iob

        # Supply-demand at nadir and in context
        supply_at_nadir = float(supply[nadir_idx])
        demand_at_nadir = float(demand[nadir_idx])
        net_at_nadir = float(net[nadir_idx])

        # Pre-hypo trend (dBG/dt for 30 min before nadir)
        pre_bg = glucose[max(0, nadir_idx - 6):nadir_idx + 1]
        valid_pre = ~np.isnan(pre_bg)
        if valid_pre.sum() >= 3:
            t = np.arange(len(pre_bg))[valid_pre]
            bg = pre_bg[valid_pre]
            pre_slope = float(np.polyfit(t, bg, 1)[0])
        else:
            pre_slope = float('nan')

        # Post-nadir rates at multiple horizons
        rates = {}
        for mins, steps in [(10, 2), (20, 4), (30, 6), (60, 12), (120, 24)]:
            end = min(steps + 1, len(post_bg))
            seg = post_bg[:end]
            v = ~np.isnan(seg)
            if v.sum() >= 2:
                tt = np.arange(len(seg))[v]
                rates[f'rate_{mins}min'] = float(np.polyfit(tt, seg[v], 1)[0])
            else:
                rates[f'rate_{mins}min'] = float('nan')

        # Glycogen proxy (cumulative net flux over preceding 6h)
        gly_start = max(0, nadir_idx - 72)
        glycogen_proxy = float(np.nansum(net[gly_start:nadir_idx]))

        # Time of day (step within the day)
        tod_step = nadir_idx % STEPS_PER_DAY
        tod_hour = tod_step / STEPS_PER_HOUR

        # Post-nadir supply-demand trajectories
        post_supply = supply[nadir_idx:post_end].copy()
        post_demand = demand[nadir_idx:post_end].copy()
        post_net = net[nadir_idx:post_end].copy()

        # Equilibrium: when does |net| stay < 0.5 for 30 min?
        eq_time = len(post_net)
        for k in range(6, len(post_net)):
            window = post_net[max(0, k-6):k]
            if len(window) >= 6 and np.all(np.abs(window) < 0.5):
                eq_time = k
                break

        # Severity classification
        if nadir_bg < 54:
            severity = 'severe'
        elif nadir_bg < 60:
            severity = 'moderate'
        else:
            severity = 'mild'

        # Post-hypo hyperglycemia
        causes_hyper = peak_recovery > 180
        rebound_above_110 = rebound > 110

        episodes.append({
            'nadir_idx': nadir_idx,
            'nadir_bg': float(nadir_bg),
            'severity': severity,
            'rebound_mg': float(rebound),
            'peak_recovery_bg': peak_recovery,
            'peak_idx': peak_idx,
            'recovery_steps': recovery_steps,
            'announced_carbs': announced,
            'has_announced': announced > 1.0,
            'iob_at_nadir': iob_at_nadir,
            'pre_iob': pre_iob,
            'supply_at_nadir': supply_at_nadir,
            'demand_at_nadir': demand_at_nadir,
            'net_at_nadir': net_at_nadir,
            'pre_slope': pre_slope,
            'glycogen_proxy': glycogen_proxy,
            'tod_hour': tod_hour,
            'eq_time_steps': eq_time,
            'causes_hyper': causes_hyper,
            'rebound_above_110': rebound_above_110,
            'post_bg': post_bg.copy(),
            'post_supply': post_supply.copy(),
            'post_demand': post_demand.copy(),
            'post_net': post_net.copy(),
            **rates,
        })

        i = max(j, nadir_idx + 6) + min_gap

    return episodes


# ── EXP-1681: Within-Patient Rescue Phenotype Clustering ───────────────

def exp_1681_rescue_clustering(patients):
    """Cluster each patient's hypo episodes into rescue phenotypes.

    Hypothesis: each patient has 2-4 typical rescue behaviors:
      - Fast rescue (glucose tabs): rapid rise, moderate peak
      - Slow rescue (food): delayed rise, higher peak
      - No rescue (counter-reg only): slow rise, low peak
      - Over-rescue (panic): very fast rise, hyperglycemia
    """
    print("\n=== EXP-1681: Within-Patient Rescue Phenotype Clustering ===")

    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    results = {}
    all_phenotype_counts = defaultdict(int)

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        isf = _extract_isf_scalar(df)

        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        if len(episodes) < 10:
            print(f"  {name}: {len(episodes)} episodes (too few)")
            continue

        # Feature matrix for clustering
        features = []
        for ep in episodes:
            f = [
                ep.get('rate_10min', 0) or 0,
                ep.get('rate_30min', 0) or 0,
                ep.get('rate_60min', 0) or 0,
                ep['rebound_mg'],
                ep['peak_idx'] / STEPS_PER_HOUR,  # hours to peak
                ep['recovery_steps'] / STEPS_PER_HOUR,
                ep['nadir_bg'],
            ]
            features.append(f)
        X = np.array(features)

        # Handle NaN
        X = np.nan_to_num(X, nan=0.0)

        # Scale
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Find optimal k (2-5 clusters)
        best_k, best_sil = 2, -1
        for k in range(2, min(6, len(episodes) // 5 + 1)):
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(X_scaled)
            sil = silhouette_score(X_scaled, labels)
            if sil > best_sil:
                best_sil = sil
                best_k = k

        # Final clustering
        km = KMeans(n_clusters=best_k, n_init=10, random_state=42)
        labels = km.fit_predict(X_scaled)

        # Characterize clusters
        clusters = []
        for c in range(best_k):
            mask = labels == c
            c_eps = [ep for ep, m in zip(episodes, mask) if m]
            rate_30 = np.nanmean([ep.get('rate_30min', 0) or 0 for ep in c_eps])
            rebound = np.nanmean([ep['rebound_mg'] for ep in c_eps])
            peak_time = np.nanmean([ep['peak_idx'] / STEPS_PER_HOUR for ep in c_eps])
            nadir = np.nanmean([ep['nadir_bg'] for ep in c_eps])
            hyper_rate = np.mean([ep['causes_hyper'] for ep in c_eps])

            # Classify phenotype
            if rate_30 > 5 and rebound > 100:
                phenotype = 'over-rescue'
            elif rate_30 > 3:
                phenotype = 'fast-rescue'
            elif rate_30 > 1:
                phenotype = 'slow-rescue'
            else:
                phenotype = 'minimal-rescue'

            clusters.append({
                'cluster': c,
                'n': int(mask.sum()),
                'phenotype': phenotype,
                'mean_rate_30': round(rate_30, 2),
                'mean_rebound': round(rebound, 1),
                'mean_peak_time_h': round(peak_time, 2),
                'mean_nadir': round(nadir, 1),
                'hyper_rate': round(hyper_rate, 3),
            })
            all_phenotype_counts[phenotype] += int(mask.sum())

        results[name] = {
            'n_episodes': len(episodes),
            'optimal_k': best_k,
            'silhouette': round(best_sil, 3),
            'clusters': clusters,
        }

        pheno_str = ', '.join(f"{c['phenotype']}({c['n']})" for c in clusters)
        print(f"  {name}: {len(episodes)} eps, k={best_k} sil={best_sil:.3f} -> {pheno_str}")

    # Population summary
    total = sum(all_phenotype_counts.values())
    print(f"\n  Population phenotype distribution (n={total}):")
    for pheno, count in sorted(all_phenotype_counts.items(), key=lambda x: -x[1]):
        print(f"    {pheno}: {count} ({100*count/total:.1f}%)")

    return {
        'experiment': 'EXP-1681',
        'title': 'Within-Patient Rescue Phenotype Clustering',
        'per_patient': results,
        'population_phenotypes': dict(all_phenotype_counts),
        'total_episodes': total,
    }


# ── EXP-1682: Post-Hypo Hyperglycemia Prediction ──────────────────────

def exp_1682_hypo_hyper_prediction(patients):
    """Predict which hypo episodes will cause post-hypo hyperglycemia.

    Target: rebound > 110 mg/dL from nadir (post-hypo hyperglycemia)
    Features available at nadir time: severity, IOB, demand state, glycogen,
    time of day, pre-hypo slope.
    """
    print("\n=== EXP-1682: Post-Hypo Hyperglycemia Prediction ===")

    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_predict
    from sklearn.metrics import roc_auc_score, classification_report
    from sklearn.preprocessing import StandardScaler

    # Collect all episodes with features available at nadir
    all_features = []
    all_labels = []
    patient_ids = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        for ep in episodes:
            feat = [
                ep['nadir_bg'],
                ep['iob_at_nadir'],
                ep['demand_at_nadir'],
                ep['supply_at_nadir'],
                ep['net_at_nadir'],
                ep['glycogen_proxy'],
                ep['pre_slope'] if not np.isnan(ep['pre_slope']) else 0,
                np.sin(2 * np.pi * ep['tod_hour'] / 24),  # circadian sin
                np.cos(2 * np.pi * ep['tod_hour'] / 24),  # circadian cos
            ]
            if any(np.isnan(feat)):
                continue
            all_features.append(feat)
            all_labels.append(int(ep['rebound_above_110']))
            patient_ids.append(name)

    X = np.array(all_features)
    y = np.array(all_labels)
    pids = np.array(patient_ids)

    print(f"  Total episodes: {len(y)}")
    print(f"  Positive (rebound >110): {y.sum()} ({100*y.mean():.1f}%)")

    # Model 1: Logistic regression (interpretable)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr_pred = cross_val_predict(lr, X_scaled, y, cv=5, method='predict_proba')[:, 1]
    lr_auc = roc_auc_score(y, lr_pred)

    # Feature importance from LR
    lr.fit(X_scaled, y)
    feature_names = ['nadir_bg', 'iob_at_nadir', 'demand', 'supply', 'net',
                     'glycogen', 'pre_slope', 'tod_sin', 'tod_cos']
    coefs = dict(zip(feature_names, [round(c, 3) for c in lr.coef_[0]]))

    print(f"\n  Logistic Regression AUC: {lr_auc:.3f}")
    print(f"  Coefficients:")
    for feat, coef in sorted(coefs.items(), key=lambda x: -abs(x[1])):
        print(f"    {feat}: {coef:+.3f}")

    # Model 2: Gradient Boosting (performance ceiling)
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
    gb_pred = cross_val_predict(gb, X_scaled, y, cv=5, method='predict_proba')[:, 1]
    gb_auc = roc_auc_score(y, gb_pred)

    print(f"\n  Gradient Boosting AUC: {gb_auc:.3f}")

    # LOPO evaluation
    lopo_aucs = {}
    for pat_name in np.unique(pids):
        test_mask = pids == pat_name
        train_mask = ~test_mask
        if y[test_mask].sum() < 5 or y[test_mask].sum() == len(y[test_mask]):
            continue
        lr_lopo = LogisticRegression(random_state=42, max_iter=1000)
        lr_lopo.fit(X_scaled[train_mask], y[train_mask])
        pred = lr_lopo.predict_proba(X_scaled[test_mask])[:, 1]
        try:
            auc = roc_auc_score(y[test_mask], pred)
            lopo_aucs[pat_name] = round(auc, 3)
        except ValueError:
            pass

    print(f"\n  LOPO AUC by patient:")
    for name, auc in sorted(lopo_aucs.items()):
        print(f"    {name}: {auc:.3f}")
    mean_lopo = np.mean(list(lopo_aucs.values())) if lopo_aucs else 0
    print(f"  Mean LOPO AUC: {mean_lopo:.3f}")

    return {
        'experiment': 'EXP-1682',
        'title': 'Post-Hypo Hyperglycemia Prediction',
        'n_episodes': len(y),
        'positive_rate': round(float(y.mean()), 3),
        'lr_auc_cv5': round(lr_auc, 3),
        'gb_auc_cv5': round(gb_auc, 3),
        'lr_coefficients': coefs,
        'lopo_auc': lopo_aucs,
        'mean_lopo_auc': round(mean_lopo, 3),
    }


# ── EXP-1683: Demand Vacuum Effect ────────────────────────────────────

def exp_1683_demand_vacuum(patients):
    """Characterize the 'demand vacuum' — how IOB depletion at nadir
    amplifies the rebound from rescue carbs.

    Hypothesis: AID systems suspend insulin during hypo, creating near-zero
    IOB. When rescue carbs arrive, there's no insulin to buffer the rise,
    causing massive glucose spikes. The 'demand vacuum' is the key amplifier.
    """
    print("\n=== EXP-1683: Demand Vacuum Characterization ===")

    all_data = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        # Compute rolling mean IOB for normalization
        mean_iob = float(np.nanmean(iob[iob > 0])) if np.any(iob > 0) else 1.0

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        for ep in episodes:
            iob_ratio = ep['iob_at_nadir'] / mean_iob if mean_iob > 0 else 0
            demand_ratio = ep['demand_at_nadir'] / float(np.nanmean(sd['demand'])) if np.nanmean(sd['demand']) > 0 else 0

            all_data.append({
                'patient': name,
                'iob_at_nadir': ep['iob_at_nadir'],
                'iob_ratio': iob_ratio,
                'demand_at_nadir': ep['demand_at_nadir'],
                'demand_ratio': demand_ratio,
                'rebound_mg': ep['rebound_mg'],
                'causes_hyper': ep['causes_hyper'],
                'recovery_rate_10': ep.get('rate_10min', 0) or 0,
                'nadir_bg': ep['nadir_bg'],
                'glycogen_proxy': ep['glycogen_proxy'],
            })

    # Analysis
    iob_ratios = np.array([d['iob_ratio'] for d in all_data])
    rebounds = np.array([d['rebound_mg'] for d in all_data])
    hyper_flags = np.array([d['causes_hyper'] for d in all_data])

    # Tertile analysis: low/mid/high IOB at nadir
    iob_vals = np.array([d['iob_at_nadir'] for d in all_data])
    t1 = np.percentile(iob_vals, 33.3)
    t2 = np.percentile(iob_vals, 66.6)

    tertiles = {
        'low_iob': iob_vals <= t1,
        'mid_iob': (iob_vals > t1) & (iob_vals <= t2),
        'high_iob': iob_vals > t2,
    }

    print(f"  Total episodes: {len(all_data)}")
    print(f"  IOB tertile thresholds: {t1:.2f} / {t2:.2f} U")
    print()

    tertile_results = {}
    for tname, mask in tertiles.items():
        reb = rebounds[mask]
        hyp = hyper_flags[mask]
        rate = np.array([d['recovery_rate_10'] for d, m in zip(all_data, mask) if m])
        tertile_results[tname] = {
            'n': int(mask.sum()),
            'mean_rebound': round(float(np.nanmean(reb)), 1),
            'median_rebound': round(float(np.nanmedian(reb)), 1),
            'hyper_rate': round(float(np.mean(hyp)), 3),
            'mean_recovery_rate': round(float(np.nanmean(rate)), 2),
        }
        print(f"  {tname} (n={mask.sum()}): rebound={np.nanmean(reb):.1f}±{np.nanstd(reb):.1f} "
              f"hyper={100*np.mean(hyp):.1f}% rate={np.nanmean(rate):.2f}")

    # Correlation: IOB ratio vs rebound
    valid = ~(np.isnan(iob_ratios) | np.isnan(rebounds))
    r_iob_rebound = stats.spearmanr(iob_ratios[valid], rebounds[valid])
    print(f"\n  IOB ratio vs rebound: r={r_iob_rebound.statistic:.3f} (p={r_iob_rebound.pvalue:.2e})")

    # Correlation: demand at nadir vs rebound
    demands = np.array([d['demand_at_nadir'] for d in all_data])
    valid2 = ~(np.isnan(demands) | np.isnan(rebounds))
    r_demand_rebound = stats.spearmanr(demands[valid2], rebounds[valid2])
    print(f"  Demand at nadir vs rebound: r={r_demand_rebound.statistic:.3f} (p={r_demand_rebound.pvalue:.2e})")

    # Key metric: does low IOB + low demand create bigger rebounds?
    vacuum_mask = (iob_ratios < 0.5) & (np.array([d['demand_ratio'] for d in all_data]) < 0.5)
    non_vacuum = ~vacuum_mask
    print(f"\n  Demand vacuum (<50% IOB AND <50% demand): {vacuum_mask.sum()} episodes")
    if vacuum_mask.sum() > 10:
        print(f"    Vacuum rebound: {np.nanmean(rebounds[vacuum_mask]):.1f} "
              f"vs non-vacuum: {np.nanmean(rebounds[non_vacuum]):.1f}")
        print(f"    Vacuum hyper rate: {100*np.mean(hyper_flags[vacuum_mask]):.1f}% "
              f"vs non-vacuum: {100*np.mean(hyper_flags[non_vacuum]):.1f}%")

    return {
        'experiment': 'EXP-1683',
        'title': 'Demand Vacuum Characterization',
        'n_episodes': len(all_data),
        'iob_tertile_thresholds': [round(t1, 3), round(t2, 3)],
        'tertile_results': tertile_results,
        'r_iob_rebound': round(r_iob_rebound.statistic, 3),
        'r_demand_rebound': round(r_demand_rebound.statistic, 3),
        'vacuum_n': int(vacuum_mask.sum()),
        'vacuum_rebound': round(float(np.nanmean(rebounds[vacuum_mask])), 1) if vacuum_mask.sum() > 0 else None,
        'nonvacuum_rebound': round(float(np.nanmean(rebounds[non_vacuum])), 1) if non_vacuum.sum() > 0 else None,
    }


# ── EXP-1684: Temporal Hypo Patterns ──────────────────────────────────

def exp_1684_temporal_patterns(patients):
    """Analyze when hypos occur and how timing affects recovery.

    Questions:
      - Are hypos concentrated before meals, overnight, or after exercise?
      - Does time-of-day affect rebound severity?
      - Is there a circadian pattern to rescue behavior?
    """
    print("\n=== EXP-1684: Temporal Hypo Patterns ===")

    all_episodes = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        for ep in episodes:
            ep['patient'] = name
            all_episodes.append(ep)

    print(f"  Total episodes: {len(all_episodes)}")

    # Bin by time of day (4-hour blocks)
    tod_bins = {
        'overnight (0-4)': (0, 4),
        'early_morning (4-8)': (4, 8),
        'morning (8-12)': (8, 12),
        'afternoon (12-16)': (12, 16),
        'evening (16-20)': (16, 20),
        'night (20-24)': (20, 24),
    }

    tod_results = {}
    for bin_name, (start, end) in tod_bins.items():
        eps = [ep for ep in all_episodes if start <= ep['tod_hour'] < end]
        if len(eps) < 5:
            continue
        rebounds = [ep['rebound_mg'] for ep in eps]
        hyper_rate = np.mean([ep['causes_hyper'] for ep in eps])
        mean_nadir = np.mean([ep['nadir_bg'] for ep in eps])
        mean_iob = np.mean([ep['iob_at_nadir'] for ep in eps])

        tod_results[bin_name] = {
            'n': len(eps),
            'mean_rebound': round(float(np.mean(rebounds)), 1),
            'hyper_rate': round(float(hyper_rate), 3),
            'mean_nadir': round(mean_nadir, 1),
            'mean_iob': round(mean_iob, 3),
        }
        print(f"  {bin_name}: n={len(eps)} rebound={np.mean(rebounds):.1f} "
              f"hyper={100*hyper_rate:.1f}% nadir={mean_nadir:.1f} iob={mean_iob:.3f}")

    # Pre-meal detection: is there a carb entry within 30-90 min AFTER nadir?
    # (suggesting the hypo occurred before a planned meal)
    pre_meal_count = 0
    for pat in patients:
        df = pat['df']
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)

        for ep in [e for e in all_episodes if e['patient'] == pat['name']]:
            nidx = ep['nadir_idx']
            # Look for meal-sized carbs (>10g) 30-90 min after nadir
            meal_window = carbs[nidx + 6:min(nidx + 18, len(carbs))]
            if np.nansum(meal_window) > 10:
                pre_meal_count += 1

    pre_meal_rate = pre_meal_count / len(all_episodes) if all_episodes else 0
    print(f"\n  Pre-meal hypos (meal >10g within 30-90 min): {pre_meal_count}/{len(all_episodes)} ({100*pre_meal_rate:.1f}%)")

    # Severity by time of day
    print("\n  Severity by time of day:")
    for bin_name, (start, end) in tod_bins.items():
        eps = [ep for ep in all_episodes if start <= ep['tod_hour'] < end]
        if len(eps) < 5:
            continue
        sev_counts = defaultdict(int)
        for ep in eps:
            sev_counts[ep['severity']] += 1
        severe_pct = sev_counts.get('severe', 0) / len(eps) * 100
        print(f"    {bin_name}: {severe_pct:.1f}% severe (n={len(eps)})")

    return {
        'experiment': 'EXP-1684',
        'title': 'Temporal Hypo Patterns',
        'n_episodes': len(all_episodes),
        'tod_results': tod_results,
        'pre_meal_rate': round(pre_meal_rate, 3),
        'pre_meal_count': pre_meal_count,
    }


# ── EXP-1685: Hypo as Therapy Diagnostic ──────────────────────────────

def exp_1685_therapy_diagnostic(patients):
    """Can hypo frequency and patterns diagnose therapy misconfiguration?

    Hypothesis: patients with more frequent/severe hypos have ISF or basal
    settings that are too aggressive. The hypo pattern itself is a signal
    of therapy adequacy.
    """
    print("\n=== EXP-1685: Hypo as Therapy Diagnostic ===")

    patient_profiles = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        isf = _extract_isf_scalar(df)
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        if len(episodes) < 5:
            continue

        # Patient therapy settings
        basal_rates = df.attrs.get('basal_schedule', [])
        mean_basal = np.mean([b['value'] for b in basal_rates]) if basal_rates else float('nan')

        # Hypo metrics
        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY
        hypo_rate = len(episodes) / valid_days  # episodes per day
        severe_rate = len([e for e in episodes if e['severity'] == 'severe']) / valid_days
        mean_nadir = np.mean([e['nadir_bg'] for e in episodes])
        mean_rebound = np.mean([e['rebound_mg'] for e in episodes])
        hyper_rate = np.mean([e['causes_hyper'] for e in episodes])

        # Time below range
        tbr = np.nanmean(glucose < 70)
        tir = np.nanmean((glucose >= 70) & (glucose <= 180))
        tar = np.nanmean(glucose > 180)

        # Mean demand/supply ratio
        mean_demand = float(np.nanmean(sd['demand']))
        mean_supply = float(np.nanmean(sd['supply']))
        ds_ratio = mean_demand / mean_supply if mean_supply > 0 else float('nan')

        profile = {
            'patient': name,
            'isf': isf,
            'mean_basal': round(mean_basal, 3) if not np.isnan(mean_basal) else None,
            'valid_days': round(valid_days, 1),
            'hypo_rate': round(hypo_rate, 2),
            'severe_rate': round(severe_rate, 3),
            'mean_nadir': round(mean_nadir, 1),
            'mean_rebound': round(mean_rebound, 1),
            'hyper_rate': round(hyper_rate, 3),
            'tbr': round(float(tbr), 4),
            'tir': round(float(tir), 4),
            'tar': round(float(tar), 4),
            'ds_ratio': round(ds_ratio, 3),
            'demand_calibration': round(sd.get('demand_calibration', 1.0), 3),
        }
        patient_profiles.append(profile)

    # Correlations: therapy settings vs hypo patterns
    profiles = patient_profiles
    isfs = np.array([p['isf'] for p in profiles])
    hypo_rates = np.array([p['hypo_rate'] for p in profiles])
    severe_rates = np.array([p['severe_rate'] for p in profiles])
    basals = np.array([p['mean_basal'] if p['mean_basal'] else np.nan for p in profiles])
    tirs = np.array([p['tir'] for p in profiles])

    print(f"  Patient profiles:")
    for p in profiles:
        print(f"    {p['patient']}: ISF={p['isf']:.0f} basal={p['mean_basal']} "
              f"hypo/day={p['hypo_rate']:.2f} severe/day={p['severe_rate']:.3f} "
              f"TBR={100*p['tbr']:.1f}% TIR={100*p['tir']:.1f}%")

    # ISF vs hypo rate
    valid_isf = ~np.isnan(isfs)
    r_isf_hypo = stats.spearmanr(isfs[valid_isf], hypo_rates[valid_isf])
    print(f"\n  ISF vs hypo rate: r={r_isf_hypo.statistic:.3f} (p={r_isf_hypo.pvalue:.3f})")

    # Basal vs hypo rate
    valid_basal = ~np.isnan(basals)
    if valid_basal.sum() >= 3:
        r_basal_hypo = stats.spearmanr(basals[valid_basal], hypo_rates[valid_basal])
        print(f"  Basal vs hypo rate: r={r_basal_hypo.statistic:.3f} (p={r_basal_hypo.pvalue:.3f})")
    else:
        r_basal_hypo = type('obj', (object,), {'statistic': float('nan'), 'pvalue': float('nan')})()

    # DS ratio vs TIR
    ds_ratios = np.array([p['ds_ratio'] for p in profiles])
    valid_ds = ~np.isnan(ds_ratios)
    r_ds_tir = stats.spearmanr(ds_ratios[valid_ds], tirs[valid_ds])
    print(f"  D/S ratio vs TIR: r={r_ds_tir.statistic:.3f} (p={r_ds_tir.pvalue:.3f})")

    # Demand calibration vs hypo rate
    calibs = np.array([p['demand_calibration'] for p in profiles])
    r_calib_hypo = stats.spearmanr(calibs, hypo_rates)
    print(f"  Demand calibration vs hypo rate: r={r_calib_hypo.statistic:.3f} (p={r_calib_hypo.pvalue:.3f})")

    return {
        'experiment': 'EXP-1685',
        'title': 'Hypo as Therapy Diagnostic',
        'patient_profiles': profiles,
        'r_isf_hypo': round(r_isf_hypo.statistic, 3),
        'r_basal_hypo': round(r_basal_hypo.statistic, 3),
        'r_ds_tir': round(r_ds_tir.statistic, 3),
        'r_calib_hypo': round(r_calib_hypo.statistic, 3),
    }


# ── EXP-1686: Supply-Demand Equilibrium Restoration ───────────────────

def exp_1686_equilibrium_restoration(patients):
    """How long does it take supply-demand to re-equilibrate after hypo?

    Measures: time for |net flux| to return to normal post-hypo,
    and characterizes the oscillation pattern (overshoot → correction → stable).
    """
    print("\n=== EXP-1686: Supply-Demand Equilibrium Restoration ===")

    all_eq_times = []
    all_oscillations = []
    per_patient = {}

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        # Compute population-level net flux stats for this patient
        net = sd['net']
        net_std = float(np.nanstd(net))
        net_mean = float(np.nanmean(net))

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        eq_times = []
        oscillation_counts = []

        for ep in episodes:
            pnet = ep['post_net']

            # Equilibrium: first time |net - mean| < 0.5*std for 6 consecutive steps
            eq_step = len(pnet)
            for k in range(6, len(pnet)):
                window = pnet[max(0, k-6):k]
                if len(window) >= 6 and np.all(np.abs(window - net_mean) < 0.5 * net_std):
                    eq_step = k
                    break

            eq_times.append(eq_step)
            all_eq_times.append(eq_step)

            # Count sign changes in net flux (oscillations)
            sign_changes = 0
            for k in range(1, min(36, len(pnet))):
                if pnet[k] * pnet[k-1] < 0:
                    sign_changes += 1
            oscillation_counts.append(sign_changes)
            all_oscillations.append(sign_changes)

        if episodes:
            mean_eq = np.mean(eq_times) / STEPS_PER_HOUR
            mean_osc = np.mean(oscillation_counts)
            per_patient[name] = {
                'n': len(episodes),
                'mean_eq_hours': round(mean_eq, 1),
                'median_eq_hours': round(float(np.median(eq_times)) / STEPS_PER_HOUR, 1),
                'mean_oscillations': round(mean_osc, 1),
            }
            print(f"  {name}: eq={mean_eq:.1f}h oscillations={mean_osc:.1f} (n={len(episodes)})")

    # Population statistics
    pop_eq = np.array(all_eq_times) / STEPS_PER_HOUR
    pop_osc = np.array(all_oscillations)
    print(f"\n  Population equilibrium time: {np.mean(pop_eq):.1f} ± {np.std(pop_eq):.1f}h")
    print(f"  Population oscillations: {np.mean(pop_osc):.1f} ± {np.std(pop_osc):.1f}")
    print(f"  Episodes reaching equilibrium <2h: {(pop_eq < 2).sum()}/{len(pop_eq)} ({100*(pop_eq < 2).mean():.1f}%)")
    print(f"  Episodes NEVER reaching equilibrium: {(pop_eq >= 6).sum()}/{len(pop_eq)} ({100*(pop_eq >= 6).mean():.1f}%)")

    return {
        'experiment': 'EXP-1686',
        'title': 'Supply-Demand Equilibrium Restoration',
        'n_episodes': len(all_eq_times),
        'population_mean_eq_hours': round(float(np.mean(pop_eq)), 2),
        'population_median_eq_hours': round(float(np.median(pop_eq)), 2),
        'population_mean_oscillations': round(float(np.mean(pop_osc)), 1),
        'pct_under_2h': round(float((pop_eq < 2).mean()), 3),
        'pct_never_eq': round(float((pop_eq >= 6).mean()), 3),
        'per_patient': per_patient,
    }


# ── EXP-1687: Hypo Cascading ─────────────────────────────────────────

def exp_1687_hypo_cascading(patients):
    """Do hypos cluster in time? Does one hypo increase risk of another?

    Tests whether hypo episodes are Poisson-distributed (random) or
    exhibit clustering (contagion). A hypo that causes hyperglycemia may
    trigger aggressive AID correction → another hypo.
    """
    print("\n=== EXP-1687: Hypo Cascading ===")

    per_patient = {}
    all_gaps = []
    all_cascade_rates = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        if len(episodes) < 10:
            continue

        # Inter-episode gaps (in hours)
        nadirs = [ep['nadir_idx'] for ep in episodes]
        gaps = [(nadirs[i+1] - nadirs[i]) / STEPS_PER_HOUR for i in range(len(nadirs)-1)]
        all_gaps.extend(gaps)

        # Cascade: hypo within 6h of previous
        cascade_count = sum(1 for g in gaps if g < 6)
        cascade_rate = cascade_count / len(gaps) if gaps else 0

        # Test: Poisson vs clustered
        # Under Poisson, inter-arrival times are exponential
        # Dispersion index: var/mean > 1 indicates clustering
        gap_array = np.array(gaps)
        dispersion = np.var(gap_array) / np.mean(gap_array) if np.mean(gap_array) > 0 else 1

        # Does previous hypo's rebound predict next hypo?
        post_hyper_then_hypo = 0
        post_normal_then_hypo = 0
        for i in range(len(episodes) - 1):
            gap_h = (episodes[i+1]['nadir_idx'] - episodes[i]['nadir_idx']) / STEPS_PER_HOUR
            if gap_h > 12:
                continue
            if episodes[i]['causes_hyper']:
                post_hyper_then_hypo += 1
            else:
                post_normal_then_hypo += 1

        per_patient[name] = {
            'n_episodes': len(episodes),
            'mean_gap_hours': round(float(np.mean(gaps)), 1),
            'median_gap_hours': round(float(np.median(gaps)), 1),
            'cascade_rate_6h': round(cascade_rate, 3),
            'dispersion_index': round(dispersion, 2),
            'post_hyper_cascade': post_hyper_then_hypo,
            'post_normal_cascade': post_normal_then_hypo,
        }
        all_cascade_rates.append(cascade_rate)

        clustered = "CLUSTERED" if dispersion > 1.5 else "random-like"
        print(f"  {name}: gap={np.mean(gaps):.1f}h cascade={100*cascade_rate:.1f}% "
              f"dispersion={dispersion:.2f} ({clustered})")

    # Population analysis
    all_gaps_arr = np.array(all_gaps)
    pop_dispersion = np.var(all_gaps_arr) / np.mean(all_gaps_arr) if np.mean(all_gaps_arr) > 0 else 1
    mean_cascade = np.mean(all_cascade_rates)

    print(f"\n  Population: median gap={np.median(all_gaps_arr):.1f}h "
          f"cascade={100*mean_cascade:.1f}% dispersion={pop_dispersion:.2f}")

    # Test: does post-hypo hyperglycemia increase cascade risk?
    total_hyper_cascade = sum(p['post_hyper_cascade'] for p in per_patient.values())
    total_normal_cascade = sum(p['post_normal_cascade'] for p in per_patient.values())
    total_cascade = total_hyper_cascade + total_normal_cascade
    if total_cascade > 0:
        hyper_cascade_pct = total_hyper_cascade / total_cascade
        print(f"  Cascades after hyper-rebound: {total_hyper_cascade}/{total_cascade} "
              f"({100*hyper_cascade_pct:.1f}%)")

    return {
        'experiment': 'EXP-1687',
        'title': 'Hypo Cascading',
        'n_patients': len(per_patient),
        'population_median_gap_hours': round(float(np.median(all_gaps_arr)), 1),
        'population_dispersion': round(pop_dispersion, 2),
        'mean_cascade_rate': round(mean_cascade, 3),
        'per_patient': per_patient,
    }


# ── EXP-1688: Personalized Hypo Risk Profile ─────────────────────────

def exp_1688_risk_profile(patients):
    """Build a per-patient hypo risk profile integrating all features.

    Generates a comprehensive "hypo fingerprint" for each patient:
    frequency, severity, timing, rescue behavior, therapy settings.
    Then tests if the profile predicts outcomes (TIR, TBR).
    """
    print("\n=== EXP-1688: Personalized Hypo Risk Profile ===")

    profiles = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        isf = _extract_isf_scalar(df)
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        episodes = find_hypo_episodes_enriched(glucose, carbs, iob, sd, pk)

        if len(episodes) < 5:
            continue

        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY

        # Frequency metrics
        hypo_per_day = len(episodes) / valid_days
        severe_per_day = len([e for e in episodes if e['severity'] == 'severe']) / valid_days

        # Severity metrics
        mean_nadir = np.mean([e['nadir_bg'] for e in episodes])
        nadir_p10 = np.percentile([e['nadir_bg'] for e in episodes], 10)

        # Recovery metrics
        mean_rebound = np.mean([e['rebound_mg'] for e in episodes])
        hyper_rate = np.mean([e['causes_hyper'] for e in episodes])
        mean_eq_time = np.mean([e['eq_time_steps'] for e in episodes]) / STEPS_PER_HOUR

        # Timing
        tod_hours = [e['tod_hour'] for e in episodes]
        overnight_pct = len([h for h in tod_hours if h < 6 or h >= 22]) / len(tod_hours)
        pre_meal_pct = len([h for h in tod_hours if 6 <= h < 9 or 11 <= h < 13 or 17 <= h < 19]) / len(tod_hours)

        # Demand vacuum severity
        mean_iob_ratio = np.mean([e['iob_at_nadir'] for e in episodes]) / max(float(np.nanmean(iob)), 0.01)

        # Glycogen patterns
        mean_glycogen = np.mean([e['glycogen_proxy'] for e in episodes])

        # Clustering
        nadirs = sorted([e['nadir_idx'] for e in episodes])
        if len(nadirs) > 1:
            gaps = [(nadirs[i+1] - nadirs[i]) / STEPS_PER_HOUR for i in range(len(nadirs)-1)]
            cascade_rate = np.mean([g < 6 for g in gaps])
            gap_dispersion = np.var(gaps) / np.mean(gaps) if np.mean(gaps) > 0 else 1
        else:
            cascade_rate = 0
            gap_dispersion = 1

        # Outcomes
        tbr = float(np.nanmean(glucose < 70))
        tir = float(np.nanmean((glucose >= 70) & (glucose <= 180)))
        tar = float(np.nanmean(glucose > 180))
        cv = float(np.nanstd(glucose) / np.nanmean(glucose))

        profile = {
            'patient': name,
            'isf': isf,
            'hypo_per_day': round(hypo_per_day, 2),
            'severe_per_day': round(severe_per_day, 3),
            'mean_nadir': round(mean_nadir, 1),
            'nadir_p10': round(nadir_p10, 1),
            'mean_rebound': round(mean_rebound, 1),
            'hyper_rate': round(hyper_rate, 3),
            'mean_eq_hours': round(mean_eq_time, 1),
            'overnight_pct': round(overnight_pct, 3),
            'pre_meal_pct': round(pre_meal_pct, 3),
            'mean_iob_ratio': round(mean_iob_ratio, 3),
            'mean_glycogen': round(mean_glycogen, 1),
            'cascade_rate': round(cascade_rate, 3),
            'gap_dispersion': round(gap_dispersion, 2),
            'tbr': round(tbr, 4),
            'tir': round(tir, 4),
            'tar': round(tar, 4),
            'cv': round(cv, 4),
            'n_episodes': len(episodes),
        }
        profiles.append(profile)

    # Print risk profiles
    print(f"\n  {'Pat':>4} {'Hypo/d':>7} {'Sev/d':>7} {'Nadir':>6} {'Reb':>5} "
          f"{'Hyper%':>7} {'Eq(h)':>6} {'Nite%':>6} {'Casc%':>6} {'TBR%':>6} {'TIR%':>6}")
    for p in sorted(profiles, key=lambda x: -x['hypo_per_day']):
        print(f"  {p['patient']:>4} {p['hypo_per_day']:>7.2f} {p['severe_per_day']:>7.3f} "
              f"{p['mean_nadir']:>6.1f} {p['mean_rebound']:>5.0f} "
              f"{100*p['hyper_rate']:>6.1f}% {p['mean_eq_hours']:>5.1f}h "
              f"{100*p['overnight_pct']:>5.1f}% {100*p['cascade_rate']:>5.1f}% "
              f"{100*p['tbr']:>5.1f}% {100*p['tir']:>5.1f}%")

    # Correlations between hypo profile and outcomes
    if len(profiles) >= 5:
        hp = np.array([p['hypo_per_day'] for p in profiles])
        hr = np.array([p['hyper_rate'] for p in profiles])
        tirs = np.array([p['tir'] for p in profiles])
        tars = np.array([p['tar'] for p in profiles])
        cvs = np.array([p['cv'] for p in profiles])

        r_hp_tir = stats.spearmanr(hp, tirs)
        r_hr_tar = stats.spearmanr(hr, tars)
        r_hp_cv = stats.spearmanr(hp, cvs)

        print(f"\n  Hypo rate vs TIR: r={r_hp_tir.statistic:.3f} (p={r_hp_tir.pvalue:.3f})")
        print(f"  Hyper-rebound rate vs TAR: r={r_hr_tar.statistic:.3f} (p={r_hr_tar.pvalue:.3f})")
        print(f"  Hypo rate vs CV: r={r_hp_cv.statistic:.3f} (p={r_hp_cv.pvalue:.3f})")
    else:
        r_hp_tir = r_hr_tar = r_hp_cv = type('obj', (object,), {'statistic': float('nan')})()

    return {
        'experiment': 'EXP-1688',
        'title': 'Personalized Hypo Risk Profile',
        'profiles': profiles,
        'r_hypo_rate_tir': round(r_hp_tir.statistic, 3),
        'r_hyper_rebound_tar': round(r_hr_tar.statistic, 3),
        'r_hypo_rate_cv': round(r_hp_cv.statistic, 3),
    }


# ── Figure generation ─────────────────────────────────────────────────

def generate_figures(results, patients):
    """Generate 6 figures for the personalized hypo analysis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Rescue phenotype distribution
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 1a: Population phenotype pie chart
    r1651 = results.get('EXP-1681', {})
    phenos = r1651.get('population_phenotypes', {})
    if phenos:
        labels = list(phenos.keys())
        sizes = list(phenos.values())
        colors = {'over-rescue': '#e74c3c', 'fast-rescue': '#f39c12',
                  'slow-rescue': '#3498db', 'minimal-rescue': '#2ecc71'}
        ax_colors = [colors.get(l, '#95a5a6') for l in labels]
        axes[0].pie(sizes, labels=labels, colors=ax_colors, autopct='%1.1f%%',
                    startangle=90)
        axes[0].set_title('Population Rescue Phenotypes')

    # 1b: Per-patient cluster counts
    per_pat = r1651.get('per_patient', {})
    if per_pat:
        pat_names = sorted(per_pat.keys())
        ks = [per_pat[n]['optimal_k'] for n in pat_names]
        sils = [per_pat[n]['silhouette'] for n in pat_names]
        x = np.arange(len(pat_names))
        bars = axes[1].bar(x, ks, color='steelblue', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(pat_names)
        axes[1].set_ylabel('Optimal clusters (k)')
        axes[1].set_title('Rescue Behavior Complexity per Patient')
        ax2 = axes[1].twinx()
        ax2.plot(x, sils, 'ro-', label='Silhouette')
        ax2.set_ylabel('Silhouette Score')
        ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig1-phenotypes.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Hyperglycemia prediction ROC-like summary
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1652 = results.get('EXP-1682', {})
    lopo = r1652.get('lopo_auc', {})
    if lopo:
        names = sorted(lopo.keys())
        aucs = [lopo[n] for n in names]
        colors = ['green' if a > 0.6 else 'orange' if a > 0.5 else 'red' for a in aucs]
        axes[0].barh(names, aucs, color=colors, alpha=0.8)
        axes[0].axvline(0.5, color='gray', linestyle='--', label='Random')
        axes[0].set_xlabel('LOPO AUC')
        axes[0].set_title('Post-Hypo Hyperglycemia Prediction (LOPO)')
        axes[0].legend()

    # 2b: Feature importance
    coefs = r1652.get('lr_coefficients', {})
    if coefs:
        sorted_coefs = sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)
        feat_names, feat_vals = zip(*sorted_coefs)
        colors = ['red' if v > 0 else 'blue' for v in feat_vals]
        axes[1].barh(feat_names, feat_vals, color=colors, alpha=0.8)
        axes[1].set_xlabel('Logistic Regression Coefficient')
        axes[1].set_title('Feature Importance for Hyper-Rebound Prediction')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig2-hyperglycemia-prediction.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Demand vacuum
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1653 = results.get('EXP-1683', {})
    tertiles = r1653.get('tertile_results', {})
    if tertiles:
        tnames = list(tertiles.keys())
        rebounds = [tertiles[t]['mean_rebound'] for t in tnames]
        hyper_pcts = [100 * tertiles[t]['hyper_rate'] for t in tnames]

        x = np.arange(len(tnames))
        axes[0].bar(x, rebounds, color=['#2ecc71', '#f39c12', '#e74c3c'], alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels([t.split('_')[0] for t in tnames])
        axes[0].set_ylabel('Mean Rebound (mg/dL)')
        axes[0].set_title('IOB at Nadir → Rebound Severity')

        axes[1].bar(x, hyper_pcts, color=['#2ecc71', '#f39c12', '#e74c3c'], alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels([t.split('_')[0] for t in tnames])
        axes[1].set_ylabel('Hyperglycemia Rate (%)')
        axes[1].set_title('IOB at Nadir → Post-Hypo Hyperglycemia Rate')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig3-demand-vacuum.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: Temporal patterns
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1654 = results.get('EXP-1684', {})
    tod = r1654.get('tod_results', {})
    if tod:
        bin_names = list(tod.keys())
        counts = [tod[b]['n'] for b in bin_names]
        hyper_rates = [100 * tod[b]['hyper_rate'] for b in bin_names]
        short_names = [b.split('(')[1].rstrip(')') if '(' in b else b for b in bin_names]

        x = np.arange(len(bin_names))
        axes[0].bar(x, counts, color='steelblue', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(short_names, rotation=45, ha='right')
        axes[0].set_ylabel('Episode Count')
        axes[0].set_title('Hypo Frequency by Time of Day')

        axes[1].bar(x, hyper_rates, color='coral', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(short_names, rotation=45, ha='right')
        axes[1].set_ylabel('Post-Hypo Hyperglycemia Rate (%)')
        axes[1].set_title('Rebound Severity by Time of Day')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig4-temporal.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: Equilibrium restoration
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1656 = results.get('EXP-1686', {})
    per_pat = r1656.get('per_patient', {})
    if per_pat:
        names = sorted(per_pat.keys())
        eq_times = [per_pat[n]['mean_eq_hours'] for n in names]
        oscs = [per_pat[n]['mean_oscillations'] for n in names]

        x = np.arange(len(names))
        axes[0].bar(x, eq_times, color='steelblue', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Hours to Equilibrium')
        axes[0].set_title('Mean Time to S×D Equilibrium Post-Hypo')
        axes[0].axhline(2, color='green', linestyle='--', label='Target (2h)')
        axes[0].legend()

        axes[1].bar(x, oscs, color='coral', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Net Flux Sign Changes')
        axes[1].set_title('S×D Oscillations in 3h Post-Hypo')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig5-equilibrium.png', dpi=150)
    plt.close()
    print("  Saved fig5")

    # Fig 6: Personalized risk profile heatmap
    fig, ax = plt.subplots(figsize=(14, 8))

    r1658 = results.get('EXP-1688', {})
    risk_profiles = r1658.get('profiles', [])
    if risk_profiles:
        # Select key metrics for heatmap
        metrics = ['hypo_per_day', 'severe_per_day', 'hyper_rate', 'overnight_pct',
                    'cascade_rate', 'mean_rebound', 'cv', 'tbr', 'tar']
        pat_names = [p['patient'] for p in risk_profiles]

        data = np.array([[p[m] for m in metrics] for p in risk_profiles])

        # Normalize each column to [0, 1]
        data_norm = data.copy()
        for col in range(data.shape[1]):
            cmin, cmax = data[:, col].min(), data[:, col].max()
            if cmax > cmin:
                data_norm[:, col] = (data[:, col] - cmin) / (cmax - cmin)
            else:
                data_norm[:, col] = 0.5

        im = ax.imshow(data_norm, aspect='auto', cmap='RdYlGn_r')
        ax.set_xticks(np.arange(len(metrics)))
        ax.set_xticklabels(metrics, rotation=45, ha='right')
        ax.set_yticks(np.arange(len(pat_names)))
        ax.set_yticklabels(pat_names)
        ax.set_title('Personalized Hypo Risk Profile (normalized, red=higher risk)')

        # Annotate with actual values
        for i in range(len(pat_names)):
            for j in range(len(metrics)):
                val = data[i, j]
                fmt = '.2f' if val < 1 else '.1f' if val < 10 else '.0f'
                ax.text(j, i, f'{val:{fmt}}', ha='center', va='center',
                        fontsize=7, color='black')

        plt.colorbar(im, label='Risk (normalized)')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'hypo2-fig6-risk-profile.png', dpi=150)
    plt.close()
    print("  Saved fig6")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1681–1688: Personalized Hypo Analysis')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1681'] = exp_1681_rescue_clustering(patients)
    results['EXP-1682'] = exp_1682_hypo_hyper_prediction(patients)
    results['EXP-1683'] = exp_1683_demand_vacuum(patients)
    results['EXP-1684'] = exp_1684_temporal_patterns(patients)
    results['EXP-1685'] = exp_1685_therapy_diagnostic(patients)
    results['EXP-1686'] = exp_1686_equilibrium_restoration(patients)
    results['EXP-1687'] = exp_1687_hypo_cascading(patients)
    results['EXP-1688'] = exp_1688_risk_profile(patients)

    # Save experiment JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_personalized_hypo.json"
        out = {}
        for k, v in result.items():
            if isinstance(v, (dict, list, str, int, float, bool, type(None))):
                out[k] = v
        with open(RESULTS_DIR / fname, 'w') as f:
            json.dump(out, f, indent=2, default=str)
    print(f"\nSaved {len(results)} experiment JSONs")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    r1651 = results.get('EXP-1681', {})
    r1652 = results.get('EXP-1682', {})
    r1653 = results.get('EXP-1683', {})
    r1654 = results.get('EXP-1684', {})
    r1655 = results.get('EXP-1685', {})
    r1656 = results.get('EXP-1686', {})
    r1657 = results.get('EXP-1687', {})
    r1658 = results.get('EXP-1688', {})

    print(f"  Rescue phenotypes: {r1651.get('population_phenotypes', {})}")
    print(f"  Hyper prediction: LR AUC={r1652.get('lr_auc_cv5', '?')} "
          f"GB AUC={r1652.get('gb_auc_cv5', '?')} "
          f"LOPO={r1652.get('mean_lopo_auc', '?')}")
    print(f"  Demand vacuum: IOB→rebound r={r1653.get('r_iob_rebound', '?')}")
    print(f"  Pre-meal hypos: {100*r1654.get('pre_meal_rate', 0):.1f}%")
    print(f"  Therapy diag: ISF→hypo r={r1655.get('r_isf_hypo', '?')}")
    print(f"  Equilibrium: mean={r1656.get('population_mean_eq_hours', '?')}h "
          f"never={100*r1656.get('pct_never_eq', 0):.0f}%")
    print(f"  Cascading: rate={100*r1657.get('mean_cascade_rate', 0):.0f}% "
          f"dispersion={r1657.get('population_dispersion', '?')}")
    print(f"  Risk profile: hypo→TIR r={r1658.get('r_hypo_rate_tir', '?')} "
          f"hyper→TAR r={r1658.get('r_hyper_rebound_tar', '?')}")


if __name__ == '__main__':
    main()
