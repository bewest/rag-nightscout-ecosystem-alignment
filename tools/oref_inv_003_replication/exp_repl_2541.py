#!/usr/bin/env python3
"""
EXP-2541–2544: Per-Patient DIA Fitting for PK Feature Optimization

Profile DIA defaults (5-6h) far exceed measured IOB decay (2.8-3.8h, EXP-2353).
This experiment grid-searches DIA per patient to maximize CV AUC, then evaluates
whether personalized DIA improves SHAP ρ vs colleague beyond the fixed-DIA result
(ρ=0.609 from EXP-2531).

Experiments:
  2541 - Grid search DIA per patient (2.0-8.0h, 0.5h steps)
  2542 - Compare profile DIA vs EXP-2353 DIA vs optimal DIA
  2543 - Final model with optimized DIA: AUC + SHAP ρ vs colleague
  2544 - Sensitivity analysis: how much does DIA precision matter?

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2541
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2541 --quick
"""

import argparse
import json
import resource
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.model_selection import StratifiedKFold, cross_val_score

from oref_inv_003_replication.data_bridge import (
    OREF_FEATURES,
    load_grid,
    build_oref_features,
    compute_4h_outcomes,
    _load_patient_dia,
)
from oref_inv_003_replication.pk_bridge import compute_pk_for_patient
from oref_inv_003_replication.report_engine import (
    ComparisonReport,
    NumpyEncoder,
)

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

RESULTS_DIR = Path("externals/experiments")
FIGURES_DIR = Path("tools/oref_inv_003_replication/figures")

# Colleague's SHAP rankings (from OREF-INV-003 Table 3)
COLLEAGUE_HYPO = {
    'cgm_mgdl': 1, 'iob_basaliob': 2, 'sug_ISF': 3, 'sug_CR': 4,
    'sug_current_target': 5, 'hour': 6, 'iob_activity': 7,
    'sug_sensitivityRatio': 8, 'iob_bolusiob': 9, 'reason_Dev': 10,
    'reason_BGI': 11, 'sug_eventualBG': 12, 'sug_insulinReq': 13,
    'iob_iob': 14,
}
COLLEAGUE_HYPER = {
    'cgm_mgdl': 1, 'hour': 2, 'sug_current_target': 3, 'sug_ISF': 4,
    'bg_above_target': 5, 'sug_CR': 6, 'iob_basaliob': 7,
    'sug_sensitivityRatio': 8, 'iob_iob': 9, 'sug_insulinReq': 10,
    'reason_BGI': 11, 'iob_activity': 12, 'sug_eventualBG': 13,
    'reason_Dev': 14,
}

# EXP-2353 measured IOB decay DIA values
EXP2353_DIA = {
    'a': 3.8, 'b': 3.2, 'c': 3.0, 'd': 3.6, 'e': 3.2,
    'f': 3.6, 'g': 3.4, 'h': 2.8, 'i': 2.9, 'k': 3.3,
    # j: skipped (no Loop devicestatus for IOB decay)
}

LGB_PARAMS = dict(
    n_estimators=500, learning_rate=0.05, max_depth=6,
    min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
    random_state=42, verbose=-1,
)

# Min DIA = 2*peak_min/60 = 2.5h for peak=75min (exponential kernel constraint)
DIA_GRID = np.arange(2.5, 8.5, 0.5)  # 2.5, 3.0, ..., 8.0
DIA_GRID_QUICK = np.array([2.5, 3.0, 3.5, 4.0, 5.0, 6.0])


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _mem_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _rebuild_pk_with_dia(grid_df, patient_id, dia_hours, peak_min=75.0):
    """Rebuild PK features for one patient with a specific DIA."""
    pt = grid_df[grid_df['patient_id'] == patient_id].copy()
    if len(pt) == 0:
        return None
    try:
        pk = compute_pk_for_patient(pt, dia_hours=dia_hours, peak_min=peak_min, verbose=False)
        return pk
    except Exception:
        return None


def _apply_pk_to_oref(oref_df, pk_df, patient_mask):
    """Replace 5 approximated features with PK values for one patient."""
    mapping = {
        'pk_basal_iob': 'iob_basaliob',
        'pk_bolus_iob': 'iob_bolusiob',
        'pk_activity': 'iob_activity',
        'pk_dev': 'reason_Dev',
        'pk_bgi': 'reason_BGI',
    }
    result = oref_df.copy()
    for pk_col, oref_col in mapping.items():
        if pk_col in pk_df.columns:
            result.loc[patient_mask, oref_col] = pk_df[pk_col].values
    return result


def _per_patient_cv_auc(X, y, n_splits=3):
    """Quick 3-fold CV AUC for a single patient's data."""
    if y.sum() < n_splits or (len(y) - y.sum()) < n_splits:
        return float('nan')
    try:
        model = lgb.LGBMClassifier(**{**LGB_PARAMS, 'n_estimators': 200})
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        scores = cross_val_score(model, X, y, cv=cv, scoring='roc_auc', error_score='raise')
        return float(np.mean(scores))
    except Exception:
        return float('nan')


def _cohort_cv_auc(X, y, n_splits=5):
    """5-fold CV AUC on full cohort."""
    model = lgb.LGBMClassifier(**LGB_PARAMS)
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    try:
        scores = cross_val_score(model, X, y, cv=cv, scoring='roc_auc', error_score='raise')
        return float(np.mean(scores)), float(np.std(scores))
    except Exception:
        return float('nan'), float('nan')


def _compute_shap_ranks(X, y, features, max_rows=50000, chunk_size=10000):
    """Compute SHAP importance rankings."""
    if not HAS_SHAP:
        return {}
    model = lgb.LGBMClassifier(**LGB_PARAMS)
    model.fit(X, y)

    n = min(max_rows, len(X))
    X_sample = X.sample(n=n, random_state=42) if len(X) > n else X

    chunks = [X_sample.iloc[i:i+chunk_size] for i in range(0, len(X_sample), chunk_size)]
    shap_vals_list = []
    explainer = shap.TreeExplainer(model)
    for chunk in chunks:
        sv = explainer.shap_values(chunk)
        if isinstance(sv, list):
            sv = sv[1]  # positive class
        shap_vals_list.append(np.abs(sv))

    shap_abs = np.concatenate(shap_vals_list, axis=0)
    importance = shap_abs.mean(axis=0)
    rank_order = np.argsort(-importance)
    ranks = {features[i]: int(rank + 1) for rank, i in enumerate(rank_order)}
    return ranks


def _rho_vs_colleague(our_ranks, their_ranks):
    """Spearman ρ between our SHAP ranks and colleague's."""
    common = set(our_ranks.keys()) & set(their_ranks.keys())
    if len(common) < 5:
        return float('nan'), float('nan')
    ours = [our_ranks[f] for f in common]
    theirs = [their_ranks[f] for f in common]
    rho, pval = spearmanr(ours, theirs)
    return float(rho), float(pval)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  EXP-2541: Per-Patient DIA Grid Search                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def exp_2541_dia_grid_search(grid_df, oref_base, outcomes_df, features, quick=False):
    """Grid search DIA per patient to maximize per-patient hypo CV AUC."""
    print(f"\n{'='*60}")
    print(f"[{_ts()}] EXP-2541: Per-Patient DIA Grid Search")
    print(f"{'='*60}")

    dia_values = DIA_GRID_QUICK if quick else DIA_GRID
    patients = sorted(grid_df['patient_id'].unique())
    profile_dia = _load_patient_dia()

    results = {}
    for pid in patients:
        t0 = time.time()
        pt_mask = outcomes_df['patient_id'] == pid
        pt_outcomes = outcomes_df[pt_mask]
        n_rows = int(pt_mask.sum())
        n_hypo = int(pt_outcomes['hypo_4h'].sum()) if 'hypo_4h' in pt_outcomes.columns else 0

        if n_rows < 200 or n_hypo < 10:
            print(f"  [{_ts()}] {pid}: SKIP (n={n_rows}, hypo={n_hypo})")
            results[pid] = {'skipped': True, 'reason': f'insufficient data (n={n_rows}, hypo={n_hypo})'}
            continue

        prof_dia = profile_dia.get(pid, 6.0)
        exp2353_dia = EXP2353_DIA.get(pid, None)

        dia_scores = {}
        for dia_val in dia_values:
            pk = _rebuild_pk_with_dia(grid_df, pid, dia_val)
            if pk is None:
                continue

            oref_trial = _apply_pk_to_oref(outcomes_df, pk, pt_mask)
            pt_sub = oref_trial.loc[pt_mask].dropna(subset=['hypo_4h'])
            X = pt_sub[features].fillna(0)
            y = pt_sub['hypo_4h'].astype(int).values

            auc = _per_patient_cv_auc(X, y, n_splits=3)
            dia_scores[float(dia_val)] = auc

        if not dia_scores or all(np.isnan(v) for v in dia_scores.values()):
            print(f"  [{_ts()}] {pid}: SKIP (all DIA scores NaN)")
            results[pid] = {'skipped': True, 'reason': 'all DIA scores NaN'}
            continue

        valid = {k: v for k, v in dia_scores.items() if not np.isnan(v)}
        best_dia = max(valid, key=valid.get) if valid else prof_dia
        best_auc = valid.get(best_dia, float('nan'))
        prof_auc = dia_scores.get(prof_dia, dia_scores.get(float(round(prof_dia * 2) / 2), float('nan')))
        exp_auc = dia_scores.get(exp2353_dia, float('nan')) if exp2353_dia else float('nan')

        elapsed = time.time() - t0
        print(f"  [{_ts()}] {pid}: best DIA={best_dia}h (AUC={best_auc:.4f}), "
              f"profile={prof_dia}h ({prof_auc:.4f}), "
              f"EXP-2353={exp2353_dia}h ({exp_auc:.4f}) [{elapsed:.0f}s]")

        results[pid] = {
            'profile_dia': prof_dia,
            'exp2353_dia': exp2353_dia,
            'optimal_dia': best_dia,
            'optimal_auc': best_auc,
            'profile_auc': float(prof_auc) if not np.isnan(prof_auc) else None,
            'exp2353_auc': float(exp_auc) if not np.isnan(exp_auc) else None,
            'dia_curve': {str(k): float(v) if not np.isnan(v) else None for k, v in dia_scores.items()},
            'n_rows': n_rows,
            'n_hypo': n_hypo,
            'elapsed_s': round(elapsed, 1),
        }

    # Summary statistics
    fitted = {k: v for k, v in results.items() if not v.get('skipped')}
    if fitted:
        opt_dias = [v['optimal_dia'] for v in fitted.values()]
        prof_dias = [v['profile_dia'] for v in fitted.values()]
        opt_aucs = [v['optimal_auc'] for v in fitted.values() if v['optimal_auc'] is not None]
        prof_aucs = [v['profile_auc'] for v in fitted.values() if v.get('profile_auc') is not None]

        print(f"\n  Summary ({len(fitted)} patients):")
        print(f"    Optimal DIA: mean={np.mean(opt_dias):.1f}h, range=[{min(opt_dias):.1f}, {max(opt_dias):.1f}]")
        print(f"    Profile DIA: mean={np.mean(prof_dias):.1f}h")
        if opt_aucs and prof_aucs:
            print(f"    AUC gain: {np.mean(opt_aucs) - np.mean(prof_aucs):+.4f} "
                  f"(optimal vs profile)")

    return {'exp_id': 'EXP-2541', 'per_patient': results,
            'dia_grid': dia_values.tolist(), 'quick': quick}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  EXP-2542: DIA Source Comparison                               ║
# ╚══════════════════════════════════════════════════════════════════╝

def exp_2542_dia_comparison(exp_2541_results, grid_df, oref_base, outcomes_df, features):
    """Compare cohort-level AUC across DIA sources: profile, EXP-2353, optimal."""
    print(f"\n{'='*60}")
    print(f"[{_ts()}] EXP-2542: DIA Source Comparison (Cohort-Level)")
    print(f"{'='*60}")

    per_pt = exp_2541_results['per_patient']
    fitted_patients = [pid for pid, v in per_pt.items() if not v.get('skipped')]

    if not fitted_patients:
        print("  No patients with valid DIA fits — skipping")
        return {'exp_id': 'EXP-2542', 'skipped': True}

    dia_sources = {
        'profile': {pid: per_pt[pid]['profile_dia'] for pid in fitted_patients},
        'exp2353': {pid: per_pt[pid].get('exp2353_dia', per_pt[pid]['profile_dia'])
                    for pid in fitted_patients},
        'optimal': {pid: per_pt[pid]['optimal_dia'] for pid in fitted_patients},
        'fixed_3.3': {pid: 3.3 for pid in fitted_patients},  # EXP-2353 median
        'fixed_5.0': {pid: 5.0 for pid in fitted_patients},  # pk_bridge default
    }
    # Fill EXP-2353 missing values with profile defaults
    for pid in fitted_patients:
        if dia_sources['exp2353'][pid] is None:
            dia_sources['exp2353'][pid] = dia_sources['profile'][pid]

    cohort_results = {}
    for source_name, dia_dict in dia_sources.items():
        t0 = time.time()
        print(f"\n  [{_ts()}] Building PK with DIA source: {source_name}")

        oref_trial = outcomes_df.copy()
        for pid in fitted_patients:
            dia = dia_dict[pid]
            pt_mask = oref_trial['patient_id'] == pid
            pk = _rebuild_pk_with_dia(grid_df, pid, dia)
            if pk is not None:
                oref_trial = _apply_pk_to_oref(oref_trial, pk, pt_mask)

        valid = oref_trial.dropna(subset=['hypo_4h', 'hyper_4h'])
        X = valid[features].fillna(0)
        y_hypo = valid['hypo_4h'].astype(int).values
        y_hyper = valid['hyper_4h'].astype(int).values

        hypo_auc, hypo_std = _cohort_cv_auc(X, y_hypo)
        hyper_auc, hyper_std = _cohort_cv_auc(X, y_hyper)

        elapsed = time.time() - t0
        print(f"    hypo AUC={hypo_auc:.4f}±{hypo_std:.4f}, "
              f"hyper AUC={hyper_auc:.4f}±{hyper_std:.4f} [{elapsed:.0f}s]")

        dias_used = [dia_dict[pid] for pid in fitted_patients]
        cohort_results[source_name] = {
            'hypo_auc': hypo_auc, 'hypo_std': hypo_std,
            'hyper_auc': hyper_auc, 'hyper_std': hyper_std,
            'mean_dia': float(np.mean(dias_used)),
            'dia_range': [float(min(dias_used)), float(max(dias_used))],
            'elapsed_s': round(elapsed, 1),
        }

    # Rank sources by hypo AUC
    ranked = sorted(cohort_results.items(), key=lambda x: x[1]['hypo_auc'], reverse=True)
    print(f"\n  DIA Source Ranking (by hypo AUC):")
    for rank, (name, r) in enumerate(ranked, 1):
        delta = r['hypo_auc'] - cohort_results['profile']['hypo_auc']
        print(f"    #{rank}: {name:12s} AUC={r['hypo_auc']:.4f} "
              f"(Δ={delta:+.4f} vs profile, mean DIA={r['mean_dia']:.1f}h)")

    return {'exp_id': 'EXP-2542', 'cohort_results': cohort_results,
            'ranking': [name for name, _ in ranked]}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  EXP-2543: Optimized-DIA SHAP Analysis                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def exp_2543_optimized_shap(exp_2541_results, grid_df, oref_base, outcomes_df, features):
    """Train final model with optimized DIA, compute SHAP ρ vs colleague."""
    print(f"\n{'='*60}")
    print(f"[{_ts()}] EXP-2543: Optimized-DIA SHAP ρ vs Colleague")
    print(f"{'='*60}")

    if not HAS_SHAP:
        print("  SHAP not available — skipping")
        return {'exp_id': 'EXP-2543', 'skipped': True, 'reason': 'no shap'}

    per_pt = exp_2541_results['per_patient']
    fitted_patients = [pid for pid, v in per_pt.items() if not v.get('skipped')]

    if not fitted_patients:
        return {'exp_id': 'EXP-2543', 'skipped': True, 'reason': 'no fitted patients'}

    # Build DIA dicts for optimal and EXP-2353
    dia_optimal = {pid: per_pt[pid]['optimal_dia'] for pid in fitted_patients}
    dia_exp2353 = {}
    for pid in fitted_patients:
        d = per_pt[pid].get('exp2353_dia')
        dia_exp2353[pid] = d if d is not None else per_pt[pid]['profile_dia']

    results = {}
    for label, dia_dict in [('optimal', dia_optimal), ('exp2353', dia_exp2353)]:
        t0 = time.time()
        print(f"\n  [{_ts()}] Computing SHAP with DIA source: {label}")

        oref_trial = outcomes_df.copy()
        for pid in fitted_patients:
            pt_mask = oref_trial['patient_id'] == pid
            pk = _rebuild_pk_with_dia(grid_df, pid, dia_dict[pid])
            if pk is not None:
                oref_trial = _apply_pk_to_oref(oref_trial, pk, pt_mask)

        valid = oref_trial.dropna(subset=['hypo_4h', 'hyper_4h'])
        X = valid[features].fillna(0)
        y_hypo = valid['hypo_4h'].astype(int).values
        y_hyper = valid['hyper_4h'].astype(int).values

        hypo_ranks = _compute_shap_ranks(X, y_hypo, features)
        hyper_ranks = _compute_shap_ranks(X, y_hyper, features)

        rho_hypo, p_hypo = _rho_vs_colleague(hypo_ranks, COLLEAGUE_HYPO)
        rho_hyper, p_hyper = _rho_vs_colleague(hyper_ranks, COLLEAGUE_HYPER)

        elapsed = time.time() - t0
        print(f"    SHAP ρ hypo={rho_hypo:.3f} (p={p_hypo:.3f}), "
              f"hyper={rho_hyper:.3f} (p={p_hyper:.3f}) [{elapsed:.0f}s]")

        # Show top-10 for hypo
        if hypo_ranks:
            sorted_feats = sorted(hypo_ranks.items(), key=lambda x: x[1])[:10]
            print(f"    Top-10 hypo: {', '.join(f'{f}(#{r})' for f, r in sorted_feats)}")

        results[label] = {
            'hypo_rho': rho_hypo, 'hypo_p': p_hypo,
            'hyper_rho': rho_hyper, 'hyper_p': p_hyper,
            'hypo_ranks': hypo_ranks, 'hyper_ranks': hyper_ranks,
            'iob_basaliob_rank_hypo': hypo_ranks.get('iob_basaliob'),
            'elapsed_s': round(elapsed, 1),
        }

    # Compare with EXP-2531 baseline (ρ=0.609)
    opt_rho = results['optimal']['hypo_rho']
    baseline_rho = 0.609
    print(f"\n  Δρ vs EXP-2531 (profile DIA, PK): {opt_rho - baseline_rho:+.3f}")
    print(f"  iob_basaliob rank: #{results['optimal'].get('iob_basaliob_rank_hypo', '?')} "
          f"(colleague: #2)")

    return {'exp_id': 'EXP-2543', 'shap_results': results,
            'baseline_rho': baseline_rho}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  EXP-2544: DIA Sensitivity Analysis                            ║
# ╚══════════════════════════════════════════════════════════════════╝

def exp_2544_sensitivity(exp_2541_results):
    """Analyze how sensitive AUC is to DIA precision."""
    print(f"\n{'='*60}")
    print(f"[{_ts()}] EXP-2544: DIA Sensitivity Analysis")
    print(f"{'='*60}")

    per_pt = exp_2541_results['per_patient']
    fitted_patients = [pid for pid, v in per_pt.items() if not v.get('skipped')]

    sensitivity_results = {}
    for pid in fitted_patients:
        curve = per_pt[pid].get('dia_curve', {})
        if not curve:
            continue
        dias = sorted(float(k) for k in curve.keys())
        aucs = [curve[str(d)] if curve.get(str(d)) is not None else float('nan') for d in dias]
        valid = [(d, a) for d, a in zip(dias, aucs) if not np.isnan(a)]
        if len(valid) < 3:
            continue

        opt_dia = per_pt[pid]['optimal_dia']
        opt_auc = per_pt[pid]['optimal_auc']

        # Compute AUC loss at ±0.5h, ±1.0h, ±2.0h from optimal
        losses = {}
        for offset in [0.5, 1.0, 2.0]:
            for sign_label, sign in [('minus', -1), ('plus', 1)]:
                test_dia = opt_dia + sign * offset
                key = f"{sign_label}_{offset:.1f}h"
                test_auc = curve.get(str(test_dia))
                if test_auc is not None and not np.isnan(test_auc):
                    losses[key] = opt_auc - test_auc
                else:
                    losses[key] = None

        # AUC range across all DIA values
        valid_aucs = [a for _, a in valid]
        auc_range = max(valid_aucs) - min(valid_aucs)

        sensitivity_results[pid] = {
            'optimal_dia': opt_dia,
            'auc_range': round(auc_range, 4),
            'losses': losses,
            'n_valid_dias': len(valid),
        }

        # Classify sensitivity
        if auc_range < 0.005:
            sensitivity = 'insensitive'
        elif auc_range < 0.015:
            sensitivity = 'moderate'
        else:
            sensitivity = 'sensitive'

        sensitivity_results[pid]['sensitivity'] = sensitivity
        print(f"  {pid}: {sensitivity} (range={auc_range:.4f}, optimal={opt_dia}h)")

    # Population summary
    sensitivities = [v['sensitivity'] for v in sensitivity_results.values()]
    print(f"\n  Population: {sensitivities.count('insensitive')} insensitive, "
          f"{sensitivities.count('moderate')} moderate, "
          f"{sensitivities.count('sensitive')} sensitive")

    auc_ranges = [v['auc_range'] for v in sensitivity_results.values()]
    if auc_ranges:
        print(f"  AUC range across DIA: mean={np.mean(auc_ranges):.4f}, "
              f"max={max(auc_ranges):.4f}")

    return {'exp_id': 'EXP-2544', 'per_patient': sensitivity_results}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Visualization                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

def _plot_dia_curves(exp_2541_results):
    """Plot DIA vs AUC curves per patient."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available — skipping plots")
        return

    per_pt = exp_2541_results['per_patient']
    fitted = {k: v for k, v in per_pt.items() if not v.get('skipped') and v.get('dia_curve')}

    if not fitted:
        return

    n = len(fitted)
    cols = min(4, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3 * rows), squeeze=False)

    for idx, (pid, data) in enumerate(sorted(fitted.items())):
        ax = axes[idx // cols][idx % cols]
        curve = data['dia_curve']
        dias = sorted(float(k) for k in curve.keys())
        aucs = [curve[str(d)] for d in dias]

        valid_dias = [d for d, a in zip(dias, aucs) if a is not None and not np.isnan(a)]
        valid_aucs = [a for a in aucs if a is not None and not np.isnan(a)]

        ax.plot(valid_dias, valid_aucs, 'b.-', linewidth=1.5)
        ax.axvline(data['optimal_dia'], color='green', linestyle='--', alpha=0.7, label=f"opt={data['optimal_dia']}h")
        ax.axvline(data['profile_dia'], color='red', linestyle=':', alpha=0.7, label=f"prof={data['profile_dia']}h")
        if data.get('exp2353_dia'):
            ax.axvline(data['exp2353_dia'], color='orange', linestyle='-.', alpha=0.7, label=f"2353={data['exp2353_dia']}h")
        ax.set_title(pid, fontsize=10)
        ax.set_xlabel('DIA (h)')
        ax.set_ylabel('AUC')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # Hide unused axes
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    plt.suptitle('EXP-2541: Per-Patient DIA vs Hypo AUC', fontsize=12, fontweight='bold')
    plt.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / 'fig_2541_dia_curves.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {FIGURES_DIR / 'fig_2541_dia_curves.png'}")


def _plot_dia_comparison(exp_2542_results):
    """Bar chart comparing DIA sources."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return

    cr = exp_2542_results.get('cohort_results', {})
    if not cr:
        return

    sources = list(cr.keys())
    hypo_aucs = [cr[s]['hypo_auc'] for s in sources]
    hyper_aucs = [cr[s]['hyper_auc'] for s in sources]

    x = np.arange(len(sources))
    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, hypo_aucs, width, label='Hypo AUC', color='steelblue')
    ax.bar(x + width/2, hyper_aucs, width, label='Hyper AUC', color='coral')
    ax.set_xticks(x)
    ax.set_xticklabels(sources, rotation=15)
    ax.set_ylabel('AUC')
    ax.set_title('EXP-2542: Cohort AUC by DIA Source')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Add mean DIA annotations
    for i, s in enumerate(sources):
        ax.annotate(f"DIA={cr[s]['mean_dia']:.1f}h", (i, min(hypo_aucs[i], hyper_aucs[i]) - 0.005),
                    ha='center', fontsize=8, color='gray')

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig_2542_dia_comparison.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {FIGURES_DIR / 'fig_2542_dia_comparison.png'}")


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Report Generation                                              ║
# ╚══════════════════════════════════════════════════════════════════╝

def generate_report(all_results):
    """Generate comparison report for EXP-2541-2544."""
    report = ComparisonReport(
        exp_id="EXP-2541",
        title="Per-Patient DIA Fitting for PK Feature Optimization",
        phase="augmentation",
    )

    report.add_their_finding(
        "F_DIA",
        "PK models use fixed DIA (5-6h from profiles) for all patients",
        "Profile settings across cohort; OREF-INV-003 uses whatever the user set",
    )

    # Extract key results
    r2541 = all_results.get('exp_2541', {})
    r2542 = all_results.get('exp_2542', {})
    r2543 = all_results.get('exp_2543', {})
    r2544 = all_results.get('exp_2544', {})

    # Per-patient DIA results
    fitted = {k: v for k, v in r2541.get('per_patient', {}).items() if not v.get('skipped', True)}
    if fitted:
        opt_dias = [v['optimal_dia'] for v in fitted.values()]
        evidence = (f"Grid search across {len(fitted)} patients: "
                    f"optimal DIA mean={np.mean(opt_dias):.1f}h "
                    f"(range {min(opt_dias):.1f}-{max(opt_dias):.1f}h). "
                    f"EXP-2353 measured IOB decay: 2.8-3.8h. "
                    f"Profile defaults: 5-6h.")
        report.add_our_finding(
            "F_DIA_OPT",
            f"Optimal DIA ({np.mean(opt_dias):.1f}h mean) is shorter than profile defaults (5-6h)",
            evidence,
            agreement="agrees",
        )

    # Cohort comparison
    cr = r2542.get('cohort_results', {})
    if cr:
        best_source = r2542.get('ranking', ['?'])[0]
        best_auc = cr.get(best_source, {}).get('hypo_auc', '?')
        prof_auc = cr.get('profile', {}).get('hypo_auc', '?')
        report.add_our_finding(
            "F_DIA_COHORT",
            f"Best DIA source: {best_source} (AUC={best_auc:.4f} vs profile={prof_auc:.4f})",
            f"Compared 5 DIA sources at cohort level: {r2542.get('ranking', [])}",
            agreement="not_comparable",
        )

    # SHAP ρ
    shap_r = r2543.get('shap_results', {})
    if 'optimal' in shap_r:
        opt_rho = shap_r['optimal']['hypo_rho']
        baseline = r2543.get('baseline_rho', 0.609)
        report.add_our_finding(
            "F_DIA_SHAP",
            f"Optimized-DIA SHAP ρ={opt_rho:.3f} (Δ={opt_rho - baseline:+.3f} vs profile-DIA PK)",
            f"iob_basaliob rank: #{shap_r['optimal'].get('iob_basaliob_rank_hypo', '?')} "
            f"(colleague: #2). Baseline ρ=0.609 from EXP-2531.",
            agreement="partially_agrees" if opt_rho > baseline else "inconclusive",
        )

    report_path = report.save()
    print(f"\n  Report: {report_path}")
    return report_path


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Main                                                           ║
# ╚══════════════════════════════════════════════════════════════════╝

def main():
    parser = argparse.ArgumentParser(description="EXP-2541: Per-Patient DIA Fitting")
    parser.add_argument("--data-path", default="externals/ns-parquet/training")
    parser.add_argument("--quick", action="store_true", help="Use coarse DIA grid (6 vs 13 values)")
    parser.add_argument("--skip-shap", action="store_true", help="Skip SHAP computation (faster)")
    parser.add_argument("--only", type=str, help="Run only specific sub-experiment (2541,2542,2543,2544)")
    args = parser.parse_args()

    print(f"[{_ts()}] EXP-2541-2544: Per-Patient DIA Fitting")
    print(f"  Data: {args.data_path}")
    print(f"  Quick: {args.quick}")
    print(f"  Memory: {_mem_mb():.0f} MB")

    t_start = time.time()

    # Load data
    print(f"\n[{_ts()}] Loading grid data...")
    grid = load_grid(args.data_path)
    print(f"  Grid: {len(grid)} rows, {grid['patient_id'].nunique()} patients")

    # Build base OREF features (no PK — we'll add PK per-DIA)
    print(f"[{_ts()}] Building base OREF features (no PK)...")
    oref_base = build_oref_features(grid, use_pk=False)

    # Compute outcomes
    print(f"[{_ts()}] Computing 4h outcomes...")
    outcomes = compute_4h_outcomes(oref_base)
    features = [f for f in OREF_FEATURES if f in outcomes.columns]
    print(f"  Outcomes: {len(outcomes)} rows, {int(outcomes['hypo_4h'].sum())} hypo events")

    all_results = {'metadata': {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data_path': args.data_path,
        'n_rows': len(outcomes),
        'n_patients': int(outcomes['patient_id'].nunique()),
        'quick': args.quick,
    }}

    # EXP-2541: Grid search
    if not args.only or '2541' in args.only:
        r2541 = exp_2541_dia_grid_search(grid, oref_base, outcomes, features, quick=args.quick)
        all_results['exp_2541'] = r2541
    else:
        r2541 = None

    # EXP-2542: DIA source comparison
    if r2541 and (not args.only or '2542' in args.only):
        r2542 = exp_2542_dia_comparison(r2541, grid, oref_base, outcomes, features)
        all_results['exp_2542'] = r2542
    else:
        r2542 = None

    # EXP-2543: SHAP with optimized DIA
    if r2541 and not args.skip_shap and (not args.only or '2543' in args.only):
        r2543 = exp_2543_optimized_shap(r2541, grid, oref_base, outcomes, features)
        all_results['exp_2543'] = r2543
    else:
        r2543 = None

    # EXP-2544: Sensitivity analysis
    if r2541 and (not args.only or '2544' in args.only):
        r2544 = exp_2544_sensitivity(r2541)
        all_results['exp_2544'] = r2544
    else:
        r2544 = None

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp_2541_dia_fitting.json"
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)
    print(f"\n[{_ts()}] Results saved: {out_path}")

    # Plots
    if r2541:
        _plot_dia_curves(r2541)
    if r2542:
        _plot_dia_comparison(r2542)

    # Report
    generate_report(all_results)

    elapsed = time.time() - t_start
    print(f"\n[{_ts()}] Total elapsed: {elapsed / 60:.1f} min ({_mem_mb():.0f} MB)")


if __name__ == "__main__":
    main()
