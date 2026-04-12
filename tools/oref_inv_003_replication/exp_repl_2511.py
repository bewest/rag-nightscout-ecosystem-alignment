#!/usr/bin/env python3
"""
EXP-2511–2518: Algorithm-Neutral PK Feature Replacement

Tests whether replacing the 5 approximated OREF features (iob_basaliob,
iob_bolusiob, iob_activity, reason_Dev, reason_BGI) with physics-derived
PK equivalents from continuous_pk.py improves model performance and
cross-algorithm generalizability.

The 5 approximated features use heuristic mappings (e.g., proportional IOB
split, glucose_roc × 5 for reason_Dev) that don't accurately capture the
underlying physiology for Loop patients. The PK replacements compute the
same signals from first-principles insulin pharmacokinetics.

Experiments:
  2511 - Baseline: OREF-32 with approximated features
  2512 - PK-replaced: OREF-32 with 5 PK replacements
  2513 - PK-augmented: OREF-32 (original) + 8 PK augmentation features (40 total)
  2514 - PK-only: Algorithm-neutral features only (~18 features)
  2515 - Cross-algorithm transfer: Loop→AAPS and AAPS→Loop
  2516 - SHAP analysis: rank correlation with colleague under each feature set
  2517 - Per-patient improvement analysis
  2518 - Synthesis and report generation

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2511 --figures
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2511 --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from oref_inv_003_replication.data_bridge import (
    load_patients_with_features,
    OREF_FEATURES,
)
from oref_inv_003_replication.pk_bridge import (
    add_pk_features_to_grid,
    get_oref32_with_pk_replacements,
    get_pk_only_features,
    get_augmented_features,
    PK_REPLACEMENT_FEATURES,
    PK_AUGMENTATION_FEATURES,
    ALL_PK_FEATURES,
)
from oref_inv_003_replication.report_engine import (
    ComparisonReport,
    save_figure,
    COLORS,
    NumpyEncoder,
)

LGB_PARAMS = {
    "n_estimators": 500, "learning_rate": 0.05, "max_depth": 6,
    "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.8,
    "verbose": -1, "random_state": 42,
}

# Colleague's SHAP ranking (top features for hypo, from OREF-INV-003 Table 3)
COLLEAGUE_HYPO_RANKING = {
    'cgm_mgdl': 1, 'sug_eventualBG': 2, 'iob_basaliob': 3, 'reason_minGuardBG': 4,
    'sug_ISF': 5, 'reason_BGI': 6, 'iob_iob': 7, 'iob_activity': 8,
    'reason_Dev': 9, 'sug_current_target': 10, 'sug_threshold': 11,
    'hour': 12, 'minute': 13, 'iob_bolusiob': 14, 'reason_COB': 15,
    'sug_insulinReq': 16, 'sug_sensitivityRatio': 17, 'sug_CR': 18,
    'reason_minPredBG': 19, 'sug_IOBreq': 20,
}

COLLEAGUE_HYPER_RANKING = {
    'cgm_mgdl': 1, 'sug_eventualBG': 2, 'iob_basaliob': 3, 'reason_minGuardBG': 4,
    'reason_BGI': 5, 'sug_ISF': 6, 'iob_iob': 7, 'iob_activity': 8,
    'reason_Dev': 9, 'sug_current_target': 10, 'sug_threshold': 11,
    'iob_bolusiob': 12, 'hour': 13, 'minute': 14, 'sug_sensitivityRatio': 15,
    'reason_COB': 16, 'sug_CR': 17, 'sug_insulinReq': 18,
    'reason_minPredBG': 19, 'sug_IOBreq': 20,
}


def _prepare_Xy(df, features, target):
    """Return X, y after dropping rows missing target or cgm_mgdl."""
    sub = df.dropna(subset=["cgm_mgdl"])
    sub = sub.dropna(subset=[target])
    available = [f for f in features if f in sub.columns]
    X = sub[available].fillna(0).copy()
    y = sub[target].values.astype(int)
    return X, y


def _evaluate_cv(X, y, n_folds=5, label=""):
    """5-fold CV AUC with stratification."""
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    aucs = []
    for tr_idx, te_idx in skf.split(X, y):
        model = lgb.LGBMClassifier(**LGB_PARAMS)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X.iloc[tr_idx], y.iloc[tr_idx] if hasattr(y, 'iloc') else y[tr_idx])
        pred = model.predict_proba(X.iloc[te_idx])[:, 1]
        try:
            aucs.append(roc_auc_score(
                y.iloc[te_idx] if hasattr(y, 'iloc') else y[te_idx], pred))
        except ValueError:
            pass
    return np.mean(aucs) if aucs else np.nan, np.std(aucs) if aucs else np.nan


def _get_shap_ranking(X, y, n_features=20):
    """Train model and return SHAP-based feature ranking."""
    try:
        import shap
    except ImportError:
        # Fallback to gain importance
        model = lgb.LGBMClassifier(**LGB_PARAMS)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X, y)
        imp = model.feature_importances_
        ranked = sorted(zip(X.columns, imp), key=lambda x: -x[1])
        return {name: i+1 for i, (name, _) in enumerate(ranked[:n_features])}

    model = lgb.LGBMClassifier(**LGB_PARAMS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(X, y)

    # Use sample for SHAP (cap at 50K for speed)
    sample_size = min(len(X), 50000)
    X_sample = X.sample(sample_size, random_state=42)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    if isinstance(shap_values, list):
        shap_values = shap_values[1]  # class 1 (event) SHAP values

    mean_abs = np.mean(np.abs(shap_values), axis=0)
    ranked = sorted(zip(X.columns, mean_abs), key=lambda x: -x[1])
    return {name: i+1 for i, (name, _) in enumerate(ranked[:n_features])}


def _compute_rho_vs_colleague(our_ranking, colleague_ranking):
    """Spearman ρ between our SHAP ranking and colleague's."""
    common = set(our_ranking.keys()) & set(colleague_ranking.keys())
    if len(common) < 5:
        return np.nan, np.nan
    our_ranks = [our_ranking[f] for f in common]
    their_ranks = [colleague_ranking[f] for f in common]
    rho, p = spearmanr(our_ranks, their_ranks)
    return rho, p


# ── Sub-experiments ──────────────────────────────────────────────────────

def exp_2511_baseline(df, features, n_folds, gen_figures):
    """EXP-2511: Baseline with original OREF-32 features."""
    print("\n=== EXP-2511: Baseline (OREF-32 original) ===")

    X, y_hypo = _prepare_Xy(df, features, "hypo_4h")
    _, y_hyper = _prepare_Xy(df, features, "hyper_4h")

    hypo_auc, hypo_std = _evaluate_cv(X, y_hypo, n_folds)
    hyper_auc, hyper_std = _evaluate_cv(X, y_hyper, n_folds)

    # SHAP ranking
    ranking_hypo = _get_shap_ranking(X, y_hypo)
    rho_hypo, p_hypo = _compute_rho_vs_colleague(ranking_hypo, COLLEAGUE_HYPO_RANKING)

    ranking_hyper = _get_shap_ranking(X, y_hyper)
    rho_hyper, p_hyper = _compute_rho_vs_colleague(ranking_hyper, COLLEAGUE_HYPER_RANKING)

    print(f"  Hypo  AUC: {hypo_auc:.4f} ± {hypo_std:.4f}")
    print(f"  Hyper AUC: {hyper_auc:.4f} ± {hyper_std:.4f}")
    print(f"  SHAP ρ vs colleague: hypo={rho_hypo:.3f} hyper={rho_hyper:.3f}")
    print(f"  Top-5 hypo: {[f for f,r in sorted(ranking_hypo.items(), key=lambda x: x[1])[:5]]}")

    return {
        "hypo_auc": hypo_auc, "hypo_std": hypo_std,
        "hyper_auc": hyper_auc, "hyper_std": hyper_std,
        "rho_hypo": rho_hypo, "p_hypo": p_hypo,
        "rho_hyper": rho_hyper, "p_hyper": p_hyper,
        "ranking_hypo": ranking_hypo,
        "ranking_hyper": ranking_hyper,
        "n_features": len(features),
        "n_rows": len(X),
    }


def exp_2512_pk_replaced(df, pk_replaced_features, n_folds, gen_figures):
    """EXP-2512: OREF-32 with 5 PK replacements."""
    print("\n=== EXP-2512: PK-Replaced (5 approximated → 5 PK) ===")

    X, y_hypo = _prepare_Xy(df, pk_replaced_features, "hypo_4h")
    _, y_hyper = _prepare_Xy(df, pk_replaced_features, "hyper_4h")

    hypo_auc, hypo_std = _evaluate_cv(X, y_hypo, n_folds)
    hyper_auc, hyper_std = _evaluate_cv(X, y_hyper, n_folds)

    ranking_hypo = _get_shap_ranking(X, y_hypo)
    ranking_hyper = _get_shap_ranking(X, y_hyper)

    # For PK-replaced, we can't directly compare ranking with colleague
    # because feature names differ. Map back.
    pk_to_oref = {
        'pk_basal_iob': 'iob_basaliob',
        'pk_bolus_iob': 'iob_bolusiob',
        'pk_activity': 'iob_activity',
        'pk_dev': 'reason_Dev',
        'pk_bgi': 'reason_BGI',
    }
    mapped_ranking = {}
    for f, rank in ranking_hypo.items():
        mapped_ranking[pk_to_oref.get(f, f)] = rank

    rho_hypo, p_hypo = _compute_rho_vs_colleague(mapped_ranking, COLLEAGUE_HYPO_RANKING)

    mapped_hyper = {}
    for f, rank in ranking_hyper.items():
        mapped_hyper[pk_to_oref.get(f, f)] = rank

    rho_hyper, p_hyper = _compute_rho_vs_colleague(mapped_hyper, COLLEAGUE_HYPER_RANKING)

    print(f"  Hypo  AUC: {hypo_auc:.4f} ± {hypo_std:.4f}")
    print(f"  Hyper AUC: {hyper_auc:.4f} ± {hyper_std:.4f}")
    print(f"  SHAP ρ vs colleague (mapped): hypo={rho_hypo:.3f} hyper={rho_hyper:.3f}")

    # Check PK replacement feature ranks specifically
    pk_ranks = {f: ranking_hypo.get(f, 99) for f in PK_REPLACEMENT_FEATURES if f in ranking_hypo}
    print(f"  PK replacement ranks (hypo): {pk_ranks}")

    return {
        "hypo_auc": hypo_auc, "hypo_std": hypo_std,
        "hyper_auc": hyper_auc, "hyper_std": hyper_std,
        "rho_hypo": rho_hypo, "p_hypo": p_hypo,
        "rho_hyper": rho_hyper, "p_hyper": p_hyper,
        "ranking_hypo": ranking_hypo,
        "ranking_hyper": ranking_hyper,
        "pk_ranks_hypo": pk_ranks,
        "n_features": len(pk_replaced_features),
    }


def exp_2513_pk_augmented(df, augmented_features, n_folds, gen_figures):
    """EXP-2513: OREF-32 (original) + 8 PK augmentation features."""
    print("\n=== EXP-2513: PK-Augmented (32 + 8 PK = 40 features) ===")

    X, y_hypo = _prepare_Xy(df, augmented_features, "hypo_4h")
    _, y_hyper = _prepare_Xy(df, augmented_features, "hyper_4h")

    hypo_auc, hypo_std = _evaluate_cv(X, y_hypo, n_folds)
    hyper_auc, hyper_std = _evaluate_cv(X, y_hyper, n_folds)

    ranking_hypo = _get_shap_ranking(X, y_hypo)

    # Identify which PK features entered top-20
    pk_in_top20 = {f: ranking_hypo[f] for f in PK_AUGMENTATION_FEATURES
                   if f in ranking_hypo}

    print(f"  Hypo  AUC: {hypo_auc:.4f} ± {hypo_std:.4f}")
    print(f"  Hyper AUC: {hyper_auc:.4f} ± {hyper_std:.4f}")
    print(f"  PK augmentation features in top-20: {pk_in_top20}")

    return {
        "hypo_auc": hypo_auc, "hypo_std": hypo_std,
        "hyper_auc": hyper_auc, "hyper_std": hyper_std,
        "ranking_hypo": ranking_hypo,
        "pk_in_top20": pk_in_top20,
        "n_features": len(augmented_features),
    }


def exp_2514_pk_only(df, pk_features, n_folds, gen_figures):
    """EXP-2514: Algorithm-neutral PK-only features."""
    print("\n=== EXP-2514: PK-Only (algorithm-neutral) ===")

    X, y_hypo = _prepare_Xy(df, pk_features, "hypo_4h")
    _, y_hyper = _prepare_Xy(df, pk_features, "hyper_4h")

    hypo_auc, hypo_std = _evaluate_cv(X, y_hypo, n_folds)
    hyper_auc, hyper_std = _evaluate_cv(X, y_hyper, n_folds)

    ranking_hypo = _get_shap_ranking(X, y_hypo)

    print(f"  Hypo  AUC: {hypo_auc:.4f} ± {hypo_std:.4f}")
    print(f"  Hyper AUC: {hyper_auc:.4f} ± {hyper_std:.4f}")
    print(f"  Top-5 hypo: {[f for f,r in sorted(ranking_hypo.items(), key=lambda x: x[1])[:5]]}")
    print(f"  Feature count: {len(pk_features)} (vs 32 OREF)")

    return {
        "hypo_auc": hypo_auc, "hypo_std": hypo_std,
        "hyper_auc": hyper_auc, "hyper_std": hyper_std,
        "ranking_hypo": ranking_hypo,
        "n_features": len(pk_features),
    }


def exp_2515_cross_algorithm(df, oref_features, pk_features, n_folds, gen_figures):
    """EXP-2515: Cross-algorithm transfer (Loop↔AAPS)."""
    print("\n=== EXP-2515: Cross-Algorithm Transfer ===")

    loop_patients = [p for p in df['patient_id'].unique() if not p.startswith('odc-')]
    oref_patients = [p for p in df['patient_id'].unique() if p.startswith('odc-')]

    loop_df = df[df['patient_id'].isin(loop_patients)]
    oref_df = df[df['patient_id'].isin(oref_patients)]

    results = {}

    for fset_name, fset in [("oref32", oref_features), ("pk_only", pk_features)]:
        # Loop → AAPS transfer
        X_train, y_train = _prepare_Xy(loop_df, fset, "hypo_4h")
        X_test, y_test = _prepare_Xy(oref_df, fset, "hypo_4h")

        if len(X_train) > 0 and len(X_test) > 0 and y_test.sum() > 5:
            model = lgb.LGBMClassifier(**LGB_PARAMS)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(X_train, y_train)
            pred = model.predict_proba(X_test)[:, 1]
            try:
                loop_to_oref = roc_auc_score(y_test, pred)
            except ValueError:
                loop_to_oref = np.nan
        else:
            loop_to_oref = np.nan

        # AAPS → Loop transfer
        X_train2, y_train2 = _prepare_Xy(oref_df, fset, "hypo_4h")
        X_test2, y_test2 = _prepare_Xy(loop_df, fset, "hypo_4h")

        if len(X_train2) > 0 and len(X_test2) > 0 and y_test2.sum() > 5:
            model2 = lgb.LGBMClassifier(**LGB_PARAMS)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model2.fit(X_train2, y_train2)
            pred2 = model2.predict_proba(X_test2)[:, 1]
            try:
                oref_to_loop = roc_auc_score(y_test2, pred2)
            except ValueError:
                oref_to_loop = np.nan
        else:
            oref_to_loop = np.nan

        results[fset_name] = {
            "loop_to_oref": loop_to_oref,
            "oref_to_loop": oref_to_loop,
            "mean_transfer": np.nanmean([loop_to_oref, oref_to_loop]),
        }

        print(f"  {fset_name}: Loop→AAPS={loop_to_oref:.4f}, AAPS→Loop={oref_to_loop:.4f}")

    # Transfer improvement
    oref_transfer = results["oref32"]["mean_transfer"]
    pk_transfer = results["pk_only"]["mean_transfer"]
    delta = pk_transfer - oref_transfer
    print(f"  Transfer improvement (PK vs OREF): {delta:+.4f}")
    results["transfer_delta"] = delta
    results["n_loop_patients"] = len(loop_patients)
    results["n_oref_patients"] = len(oref_patients)

    return results


def exp_2516_shap_comparison(df, oref_features, pk_replaced, pk_only, gen_figures):
    """EXP-2516: SHAP ranking correlation comparison across feature sets."""
    print("\n=== EXP-2516: SHAP Ranking Comparison ===")

    results = {}
    feature_sets = {
        "oref32": oref_features,
        "pk_replaced": pk_replaced,
        "pk_only": pk_only,
    }

    pk_to_oref = {
        'pk_basal_iob': 'iob_basaliob',
        'pk_bolus_iob': 'iob_bolusiob',
        'pk_activity': 'iob_activity',
        'pk_dev': 'reason_Dev',
        'pk_bgi': 'reason_BGI',
    }

    for name, fset in feature_sets.items():
        X, y = _prepare_Xy(df, fset, "hypo_4h")
        ranking = _get_shap_ranking(X, y)

        # Map PK feature names back to OREF names for comparison
        mapped = {}
        for f, rank in ranking.items():
            mapped[pk_to_oref.get(f, f)] = rank

        rho, p = _compute_rho_vs_colleague(mapped, COLLEAGUE_HYPO_RANKING)

        results[name] = {
            "rho": rho, "p": p,
            "top5": [f for f, r in sorted(ranking.items(), key=lambda x: x[1])[:5]],
        }
        print(f"  {name}: ρ={rho:.3f} (p={p:.4f}), top-5={results[name]['top5']}")

    return results


def exp_2517_per_patient(df, oref_features, pk_replaced, n_folds, gen_figures):
    """EXP-2517: Per-patient AUC comparison (OREF-32 vs PK-replaced)."""
    print("\n=== EXP-2517: Per-Patient Improvement ===")

    patients = sorted(df['patient_id'].unique())
    results = {}

    for pid in patients:
        pdata = df[df['patient_id'] == pid]

        X_oref, y_oref = _prepare_Xy(pdata, oref_features, "hypo_4h")
        X_pk, y_pk = _prepare_Xy(pdata, pk_replaced, "hypo_4h")

        if len(X_oref) < 200 or y_oref.sum() < 10:
            continue

        auc_oref, _ = _evaluate_cv(X_oref, y_oref, min(n_folds, 3))
        auc_pk, _ = _evaluate_cv(X_pk, y_pk, min(n_folds, 3))

        delta = auc_pk - auc_oref
        results[pid] = {
            "auc_oref": auc_oref, "auc_pk": auc_pk,
            "delta": delta, "n_rows": len(X_oref),
            "hypo_rate": y_oref.mean(),
            "is_loop": not pid.startswith('odc-'),
        }
        tag = "Loop" if results[pid]["is_loop"] else "AAPS"
        direction = "↑" if delta > 0 else "↓"
        print(f"  {pid:15s} ({tag:4s}): OREF={auc_oref:.4f} → PK={auc_pk:.4f} ({direction}{abs(delta):.4f})")

    n_improved = sum(1 for v in results.values() if v['delta'] > 0)
    n_total = len(results)
    n_loop_improved = sum(1 for v in results.values() if v['is_loop'] and v['delta'] > 0)
    n_loop_total = sum(1 for v in results.values() if v['is_loop'])

    print(f"  Overall: {n_improved}/{n_total} improved")
    print(f"  Loop patients: {n_loop_improved}/{n_loop_total} improved")

    return {
        "per_patient": results,
        "n_improved": n_improved,
        "n_total": n_total,
        "n_loop_improved": n_loop_improved,
        "n_loop_total": n_loop_total,
    }


def exp_2518_synthesis(all_results, gen_figures):
    """EXP-2518: Synthesis report."""
    print("\n=== EXP-2518: Synthesis ===")

    base = all_results.get("2511", {})
    pk_rep = all_results.get("2512", {})
    pk_aug = all_results.get("2513", {})
    pk_only = all_results.get("2514", {})
    transfer = all_results.get("2515", {})
    per_patient = all_results.get("2517", {})

    summary = {
        "auc_comparison": {
            "baseline_hypo": base.get("hypo_auc"),
            "pk_replaced_hypo": pk_rep.get("hypo_auc"),
            "pk_augmented_hypo": pk_aug.get("hypo_auc"),
            "pk_only_hypo": pk_only.get("hypo_auc"),
            "baseline_hyper": base.get("hyper_auc"),
            "pk_replaced_hyper": pk_rep.get("hyper_auc"),
            "pk_augmented_hyper": pk_aug.get("hyper_auc"),
            "pk_only_hyper": pk_only.get("hyper_auc"),
        },
        "shap_rho_comparison": {
            "baseline_rho_hypo": base.get("rho_hypo"),
            "pk_replaced_rho_hypo": pk_rep.get("rho_hypo"),
        },
        "transfer_delta": transfer.get("transfer_delta"),
        "per_patient_improved": per_patient.get("n_improved"),
        "per_patient_total": per_patient.get("n_total"),
    }

    # Key findings
    delta_hypo = (pk_rep.get("hypo_auc", 0) or 0) - (base.get("hypo_auc", 0) or 0)
    delta_rho = (pk_rep.get("rho_hypo", 0) or 0) - (base.get("rho_hypo", 0) or 0)
    pk_only_pct = (pk_only.get("hypo_auc", 0) or 0) / max(base.get("hypo_auc", 0.001) or 0.001, 0.001) * 100

    print(f"  PK replacement AUC delta: {delta_hypo:+.4f}")
    print(f"  PK replacement ρ delta: {delta_rho:+.3f}")
    print(f"  PK-only achieves {pk_only_pct:.1f}% of baseline AUC with fewer features")
    print(f"  Cross-algorithm transfer delta: {transfer.get('transfer_delta', 'N/A')}")

    summary["key_findings"] = {
        "pk_replacement_helps": delta_hypo > 0,
        "pk_replacement_auc_delta": delta_hypo,
        "pk_improves_rho": delta_rho > 0,
        "pk_rho_delta": delta_rho,
        "pk_only_pct_of_baseline": pk_only_pct,
        "pk_transfers_better": (transfer.get("transfer_delta", 0) or 0) > 0,
    }

    return summary


def generate_report(all_results, gen_figures):
    """Generate comparison report."""
    report = ComparisonReport(
        exp_id="2511",
        title="Algorithm-Neutral PK Feature Replacement",
        description=(
            "Systematic comparison of algorithm-specific OREF-32 features "
            "versus physics-derived PK features for hypo/hyper prediction. "
            "Tests whether first-principles insulin pharmacokinetics can "
            "replace heuristic feature approximations and improve "
            "cross-algorithm generalizability."
        ),
    )

    base = all_results.get("2511", {})
    pk_rep = all_results.get("2512", {})
    pk_aug = all_results.get("2513", {})
    pk_only = all_results.get("2514", {})
    transfer = all_results.get("2515", {})
    shap_cmp = all_results.get("2516", {})
    per_patient = all_results.get("2517", {})
    synthesis = all_results.get("2518", {})

    # Their findings
    report.add_their_finding(
        "F1: iob_basaliob is #3 most important feature (SHAP)",
        f"In our data with original OREF-32, iob_basaliob ranks "
        f"#{base.get('ranking_hypo', {}).get('iob_basaliob', '?')} for hypo. "
        f"With PK replacement (pk_basal_iob), it ranks "
        f"#{pk_rep.get('pk_ranks_hypo', {}).get('pk_basal_iob', '?')}."
    )
    report.add_their_finding(
        "F5: Algorithm predictions are bad (eventualBG R²=0.002)",
        "PK-derived net_balance provides physics-based prediction that doesn't "
        "depend on algorithm-specific eventualBG computation."
    )

    # Our findings
    delta_hypo = (pk_rep.get("hypo_auc", 0) or 0) - (base.get("hypo_auc", 0) or 0)
    report.add_our_finding(
        f"PK replacement {'improves' if delta_hypo > 0 else 'changes'} hypo AUC by {delta_hypo:+.4f}",
        f"OREF-32 original: {base.get('hypo_auc', '?'):.4f} → "
        f"PK-replaced: {pk_rep.get('hypo_auc', '?'):.4f}"
    )

    pk_transfer = transfer.get("transfer_delta", 0) or 0
    report.add_our_finding(
        f"Cross-algorithm transfer {'improves' if pk_transfer > 0 else 'changes'} by {pk_transfer:+.4f} with PK features",
        f"PK features provide algorithm-neutral signals that transfer "
        f"{'better' if pk_transfer > 0 else 'differently'} between Loop and AAPS patients."
    )

    n_improved = per_patient.get("n_improved", 0)
    n_total = per_patient.get("n_total", 0)
    report.add_our_finding(
        f"Per-patient: {n_improved}/{n_total} patients improve with PK replacement",
        f"Loop patients: {per_patient.get('n_loop_improved', 0)}/{per_patient.get('n_loop_total', 0)} improved"
    )

    # Methodology
    report.set_methodology(
        "**PK Bridge**: continuous_pk.py computes 8 physiological channels "
        "(insulin activity decomposition, carb absorption rate, hepatic "
        "production, net metabolic balance) from first-principles insulin "
        "pharmacokinetics using oref0/cgmsim-lib exponential activity curves.\n\n"
        "**Feature Sets**:\n"
        "1. OREF-32 original (baseline with 5 approximated features)\n"
        "2. OREF-32 PK-replaced (5 approximated → 5 PK-derived)\n"
        "3. OREF-32 PK-augmented (32 original + 8 PK = 40 features)\n"
        "4. PK-only (~18 algorithm-neutral features)\n\n"
        "**Models**: LightGBM classifiers (500 trees, depth 6, subsample 0.8), "
        "5-fold stratified CV, SHAP TreeExplainer for feature importance.\n\n"
        "**Data**: 803K rows, 19 patients (11 Loop, 8 AAPS). "
        "4h binary hypo (<70 mg/dL) and hyper (>180 mg/dL) outcomes."
    )

    # Limitations
    report.set_limitations(
        "1. **Population imbalance**: 11 Loop vs 8 AAPS patients with very different "
        "data volumes (Loop: ~50K rows each, some AAPS: ~3K rows).\n\n"
        "2. **PK parameter assumptions**: Fixed DIA=5h and peak=55min for all patients. "
        "Individual PK profiling (EXP-2351) showed DIA ranges 2.8-3.8h.\n\n"
        "3. **Schedule accuracy**: PK features depend on therapy schedule correctness. "
        "If scheduled_basal_rate is wrong, basal_ratio is wrong.\n\n"
        "4. **Feature name mapping**: When comparing PK rankings to colleague's, we map "
        "PK names back to OREF names (pk_basal_iob→iob_basaliob). This assumes "
        "semantic equivalence that is approximate.\n\n"
        "5. **SHAP sample**: 50K rows for SHAP (computational constraint). "
        "Full-data SHAP may shift rankings."
    )

    report.set_raw_results(all_results)
    report.save()

    return report


def generate_figures(all_results):
    """Generate all comparison figures."""
    base = all_results.get("2511", {})
    pk_rep = all_results.get("2512", {})
    pk_aug = all_results.get("2513", {})
    pk_only = all_results.get("2514", {})

    # Figure 1: AUC comparison across feature sets
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    models = ["OREF-32\n(baseline)", "PK-Replaced\n(5 swapped)", "PK-Augmented\n(32+8=40)", "PK-Only\n(~18)"]
    hypo_aucs = [
        base.get("hypo_auc", 0) or 0,
        pk_rep.get("hypo_auc", 0) or 0,
        pk_aug.get("hypo_auc", 0) or 0,
        pk_only.get("hypo_auc", 0) or 0,
    ]
    hyper_aucs = [
        base.get("hyper_auc", 0) or 0,
        pk_rep.get("hyper_auc", 0) or 0,
        pk_aug.get("hyper_auc", 0) or 0,
        pk_only.get("hyper_auc", 0) or 0,
    ]

    colors = [COLORS["neutral"], COLORS["ours"], COLORS["ours"], COLORS["ours"]]

    axes[0].bar(models, hypo_aucs, color=colors)
    axes[0].axhline(0.83, color=COLORS["theirs"], ls="--", label="Colleague (0.83)")
    axes[0].set_ylabel("AUC")
    axes[0].set_title("Hypo Prediction (<70 mg/dL, 4h)")
    axes[0].set_ylim(0.5, 1.0)
    axes[0].legend()

    axes[1].bar(models, hyper_aucs, color=colors)
    axes[1].axhline(0.88, color=COLORS["theirs"], ls="--", label="Colleague (0.88)")
    axes[1].set_ylabel("AUC")
    axes[1].set_title("Hyper Prediction (>180 mg/dL, 4h)")
    axes[1].set_ylim(0.5, 1.0)
    axes[1].legend()

    plt.suptitle("EXP-2511: Feature Set Comparison — Hypo/Hyper Prediction AUC", fontsize=14)
    plt.tight_layout()
    save_figure(fig, "fig_2511_feature_set_comparison.png")

    # Figure 2: Per-patient improvement scatter
    per_patient = all_results.get("2517", {}).get("per_patient", {})
    if per_patient:
        fig, ax = plt.subplots(figsize=(10, 6))
        for pid, vals in per_patient.items():
            color = COLORS["ours"] if vals["is_loop"] else COLORS["theirs"]
            marker = 'o' if vals["is_loop"] else 's'
            ax.scatter(vals["auc_oref"], vals["auc_pk"], c=color, marker=marker,
                       s=100, alpha=0.7, edgecolors='black', linewidth=0.5)
            ax.annotate(pid, (vals["auc_oref"], vals["auc_pk"]),
                        fontsize=7, ha='left', va='bottom')

        lims = [0.4, 1.0]
        ax.plot(lims, lims, 'k--', alpha=0.3, label='No change')
        ax.set_xlabel("AUC with OREF-32 (original)")
        ax.set_ylabel("AUC with PK-Replaced")
        ax.set_title("EXP-2517: Per-Patient AUC Change (OREF → PK)")
        ax.legend(["No change", "Loop patient", "AAPS patient"])
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        plt.tight_layout()
        save_figure(fig, "fig_2517_per_patient_pk.png")

    # Figure 3: Cross-algorithm transfer
    transfer = all_results.get("2515", {})
    if "oref32" in transfer and "pk_only" in transfer:
        fig, ax = plt.subplots(figsize=(8, 5))
        x = ["Loop→AAPS", "AAPS→Loop"]
        oref_vals = [transfer["oref32"]["loop_to_oref"], transfer["oref32"]["oref_to_loop"]]
        pk_vals = [transfer["pk_only"]["loop_to_oref"], transfer["pk_only"]["oref_to_loop"]]

        width = 0.35
        ax.bar([0-width/2, 1-width/2], oref_vals, width, label="OREF-32", color=COLORS["neutral"])
        ax.bar([0+width/2, 1+width/2], pk_vals, width, label="PK-Only", color=COLORS["ours"])
        ax.set_xticks([0, 1])
        ax.set_xticklabels(x)
        ax.set_ylabel("Transfer AUC")
        ax.set_title("EXP-2515: Cross-Algorithm Transfer (OREF vs PK Features)")
        ax.legend()
        ax.set_ylim(0.4, 1.0)
        plt.tight_layout()
        save_figure(fig, "fig_2515_cross_transfer.png")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EXP-2511–2518: Algorithm-Neutral PK Feature Replacement"
    )
    parser.add_argument("--figures", action="store_true")
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2511–2518: Algorithm-Neutral PK Feature Replacement")
    print("=" * 70)

    # Load data
    print("\n[1/3] Loading parquet grid data...")
    df = load_patients_with_features()
    oref_features = [f for f in OREF_FEATURES if f in df.columns]

    if args.tiny:
        tiny_patients = ["a", "b", "odc-86025410"]
        print(f"[TINY MODE] Using patients: {tiny_patients}")
        df = df[df["patient_id"].isin(tiny_patients)].copy()

    print(f"  Loaded: {len(df):,} rows, {df['patient_id'].nunique()} patients")

    # Add PK features
    print("\n[2/3] Computing PK features...")
    import time
    t0 = time.time()

    # Load raw parquet to compute PK (need actual grid columns, not OREF-mapped)
    import pandas as pd
    grid = pd.read_parquet('externals/ns-parquet/training/grid.parquet')
    if args.tiny:
        grid = grid[grid['patient_id'].isin(tiny_patients)]

    enriched_grid = add_pk_features_to_grid(grid, verbose=True)

    # Merge PK columns back into the OREF-mapped DataFrame
    # Align by index (both have same row order from parquet)
    for col in ALL_PK_FEATURES:
        df[col] = enriched_grid[col].values

    elapsed = time.time() - t0
    print(f"  PK features computed in {elapsed:.1f}s")

    # Prepare feature sets
    pk_replaced = get_oref32_with_pk_replacements(oref_features)
    pk_augmented = get_augmented_features(oref_features)
    pk_only = get_pk_only_features()

    # Add glucose_roc and glucose_accel from grid (needed by pk_only)
    for col in ['glucose_roc', 'glucose_accel']:
        if col in enriched_grid.columns and col not in df.columns:
            df[col] = enriched_grid[col].values

    n_folds = 2 if args.tiny else 5

    print(f"\n[3/3] Running experiments...")
    print(f"  Feature sets: OREF-32={len(oref_features)}, "
          f"PK-replaced={len(pk_replaced)}, "
          f"PK-augmented={len(pk_augmented)}, "
          f"PK-only={len(pk_only)}")

    all_results = {}
    all_results["2511"] = exp_2511_baseline(df, oref_features, n_folds, args.figures)
    all_results["2512"] = exp_2512_pk_replaced(df, pk_replaced, n_folds, args.figures)
    all_results["2513"] = exp_2513_pk_augmented(df, pk_augmented, n_folds, args.figures)
    all_results["2514"] = exp_2514_pk_only(df, pk_only, n_folds, args.figures)
    all_results["2515"] = exp_2515_cross_algorithm(df, oref_features, pk_only, n_folds, args.figures)
    all_results["2516"] = exp_2516_shap_comparison(df, oref_features, pk_replaced, pk_only, args.figures)
    all_results["2517"] = exp_2517_per_patient(df, oref_features, pk_replaced, n_folds, args.figures)
    all_results["2518"] = exp_2518_synthesis(all_results, args.figures)

    # Generate report
    generate_report(all_results, args.figures)

    # Generate figures
    if args.figures:
        generate_figures(all_results)

    # Save raw results
    out_path = Path("externals/experiments/exp_2511_pk_neutral.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder))
    print(f"\nResults saved to {out_path}")

    print("\n" + "=" * 70)
    print("EXP-2511–2518 complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
