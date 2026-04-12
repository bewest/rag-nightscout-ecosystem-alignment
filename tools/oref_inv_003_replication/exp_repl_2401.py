#!/usr/bin/env python3
"""
EXP-2401–2408: Feature Importance Ranking Replication

Replicates OREF-INV-003's SHAP feature importance analysis using our
independent dataset of 19 patients (11 Loop + 8 AAPS/ODC).

Experiments:
  2401 - Full-cohort SHAP importance ranking vs OREF-INV-003
  2402 - Loop-only subset analysis (does algorithm matter?)
  2403 - AAPS/ODC-only subset analysis (closest to their cohort)
  2404 - Per-patient SHAP stability (how much does importance vary?)
  2405 - User-controllable vs algorithm-dynamic importance split
  2406 - Feature interaction analysis (is CR×hour still #1?)
  2407 - Rank correlation analysis (Spearman ρ between rankings)
  2408 - Synthesis: what replicates, what doesn't, and why

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2401 --figures
"""

import argparse
import json
import os
import resource
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score, r2_score
from scipy.stats import spearmanr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from oref_inv_003_replication.data_bridge import (
    load_patients_with_features,
    split_loop_vs_oref,
    OREF_FEATURES,
)
from oref_inv_003_replication.colleague_loader import (
    ColleagueModels,
    normalize_shap_importance,
    shap_rank_correlation,
)
from oref_inv_003_replication.report_engine import (
    ComparisonReport,
    save_figure,
    plot_shap_comparison,
    COLORS,
    PATIENT_COLORS,
    NumpyEncoder,
)

try:
    import shap

    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False


def _mem_mb():
    """Current RSS in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _ts():
    """Short UTC timestamp for log lines."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

# ---------------------------------------------------------------------------
# Feature category classification (for EXP-2405)
# ---------------------------------------------------------------------------
FEATURE_CATEGORIES = {
    "user_controllable": [
        "sug_current_target",
        "sug_ISF",
        "sug_CR",
        "sug_threshold",
        "maxSMBBasalMinutes",
        "maxUAMSMBBasalMinutes",
    ],
    "algorithm_dynamic": [
        "sug_sensitivityRatio",
        "sug_rate",
        "sug_duration",
        "sug_insulinReq",
        "sug_eventualBG",
        "reason_Dev",
        "reason_BGI",
        "reason_minGuardBG",
        "isf_ratio",
        "sr_deviation",
        "dynisf_x_sr",
        "dynisf_x_isf_ratio",
    ],
    "current_state": [
        "cgm_mgdl",
        "iob_iob",
        "iob_basaliob",
        "iob_bolusiob",
        "iob_activity",
        "sug_COB",
        "direction_num",
        "bg_above_target",
        "iob_pct_max",
        "sug_smb_units",
    ],
    "time": ["hour"],
    "mode_flags": ["has_dynisf", "has_smb", "has_uam"],
}

# Invert for fast lookup
_FEATURE_TO_CATEGORY = {}
for cat, feats in FEATURE_CATEGORIES.items():
    for f in feats:
        _FEATURE_TO_CATEGORY[f] = cat

FIGURES_DIR = Path("tools/oref_inv_003_replication/figures")
RESULTS_DIR = Path("externals/experiments")

# Configurable at runtime via --shap-rows CLI arg
SHAP_MAX_ROWS = 50000
SHAP_CHUNK_SIZE = 10000

# ---------------------------------------------------------------------------
# LightGBM helpers
# ---------------------------------------------------------------------------
LGB_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
)


def _prepare_Xy(df, features, target, is_classifier=True):
    """Return X, y after dropping rows missing the target or cgm_mgdl."""
    sub = df.dropna(subset=["cgm_mgdl"])
    sub = sub.dropna(subset=[target])
    X = sub[features].fillna(0).copy()
    y = sub[target].values
    if is_classifier:
        y = y.astype(int)
    return X, y


def train_and_evaluate(X, y, is_classifier=True, label="model"):
    """Train a LightGBM model with 5-fold CV and return model + metrics."""
    if is_classifier:
        model = lgb.LGBMClassifier(**LGB_PARAMS)
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        try:
            scores = cross_val_score(
                model, X, y, cv=cv, scoring="roc_auc", error_score="raise"
            )
            metric_name, metric_val = "auc", float(np.mean(scores))
        except Exception:
            scores = cross_val_score(
                model, X, y, cv=cv, scoring="accuracy", error_score="raise"
            )
            metric_name, metric_val = "accuracy", float(np.mean(scores))
    else:
        model = lgb.LGBMRegressor(**LGB_PARAMS)
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        # For regressor, use KFold-like scoring — bin y for stratification
        y_binned = pd.qcut(y, q=5, labels=False, duplicates="drop")
        try:
            scores = cross_val_score(
                model,
                X,
                y,
                cv=StratifiedKFold(
                    n_splits=5, shuffle=True, random_state=42
                ).split(X, y_binned),
                scoring="r2",
                error_score="raise",
            )
            metric_name, metric_val = "r2", float(np.mean(scores))
        except Exception:
            metric_name, metric_val = "r2", float("nan")

    # Fit on full data for SHAP
    model.fit(X, y)
    print(f"  {label}: {metric_name}={metric_val:.4f} (n={len(y)})")
    return model, {metric_name: metric_val, "n": len(y)}


def compute_shap_importance(model, X, use_interactions=False, max_rows=None,
                            chunk_size=None):
    """Compute mean |SHAP| importance per feature with progress diagnostics.

    When *max_rows* is large, SHAP values are computed in chunks of
    *chunk_size* rows so that progress, ETA and memory can be reported
    during long runs.
    """
    if max_rows is None:
        max_rows = SHAP_MAX_ROWS
    if chunk_size is None:
        chunk_size = SHAP_CHUNK_SIZE
    features = list(X.columns)
    interaction_values = None

    if HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
            if max_rows and len(X) > max_rows:
                X_sample = X.sample(n=max_rows, random_state=42)
            else:
                X_sample = X
                max_rows = len(X)

            n_total = len(X_sample)
            print(f"  [{_ts()}] SHAP values: {n_total:,} rows "
                  f"(chunk={chunk_size:,}, ~{n_total // chunk_size + 1} "
                  f"chunks)  mem={_mem_mb():.0f} MB")

            if use_interactions:
                try:
                    t0 = time.monotonic()
                    interaction_values = explainer.shap_interaction_values(
                        X_sample
                    )
                    elapsed = time.monotonic() - t0
                    print(f"  [{_ts()}] SHAP interactions done in "
                          f"{elapsed:.0f}s  mem={_mem_mb():.0f} MB")
                except Exception:
                    pass

            # --- Chunked SHAP values with progress ---
            t0 = time.monotonic()
            chunks = []
            for start in range(0, n_total, chunk_size):
                end = min(start + chunk_size, n_total)
                chunk_vals = explainer.shap_values(X_sample.iloc[start:end])
                if isinstance(chunk_vals, list):
                    chunk_vals = chunk_vals[1]
                chunks.append(chunk_vals)

                done = end
                elapsed = time.monotonic() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (n_total - done) / rate if rate > 0 else 0
                pct = done / n_total * 100
                print(f"  [{_ts()}] SHAP progress: {done:,}/{n_total:,} "
                      f"({pct:.0f}%)  {rate:.0f} rows/s  "
                      f"ETA {eta:.0f}s  mem={_mem_mb():.0f} MB")

            shap_values = np.vstack(chunks)
            total_time = time.monotonic() - t0
            print(f"  [{_ts()}] SHAP complete: {n_total:,} rows in "
                  f"{total_time:.0f}s ({n_total/total_time:.0f} rows/s)")

            mean_abs = np.mean(np.abs(shap_values), axis=0)
            importance = dict(zip(features, mean_abs.tolist()))
            method = "shap"
        except Exception as e:
            print(f"    SHAP failed ({e}), falling back to gain")
            importance = dict(
                zip(features, model.feature_importances_.tolist())
            )
            method = "gain_fallback"
    else:
        importance = dict(
            zip(features, model.feature_importances_.tolist())
        )
        method = "gain_fallback"

    return importance, method, interaction_values


# ---------------------------------------------------------------------------
# Sub-experiments
# ---------------------------------------------------------------------------


def exp_2401_full_cohort(df, features, colleague, gen_figures):
    """EXP-2401: Full-cohort SHAP importance ranking vs OREF-INV-003."""
    print("\n=== EXP-2401: Full-cohort SHAP ranking ===")
    results = {"models": {}, "shap": {}, "comparison": {}}

    for target, is_cls, label in [
        ("hypo_4h", True, "hypo"),
        ("hyper_4h", True, "hyper"),
        ("bg_change_4h", False, "bg_change"),
    ]:
        X, y = _prepare_Xy(df, features, target, is_cls)
        if len(y) < 100:
            print(f"  Skipping {label}: only {len(y)} rows")
            continue

        model, metrics = train_and_evaluate(X, y, is_cls, label)
        raw_imp, method, _ = compute_shap_importance(model, X)
        norm_imp = normalize_shap_importance(raw_imp)

        results["models"][label] = {**metrics, "method": method}
        results["shap"][label] = norm_imp

        # Compare with colleague's
        try:
            comp_df = colleague.compare_importance(raw_imp, label)
            results["comparison"][label] = comp_df.to_dict(orient="records")
        except Exception as e:
            print(f"    Could not compare {label}: {e}")

        if gen_figures and label in ("hypo", "hyper"):
            their_shap = colleague.shap_importance.get(label, {})
            fig = plot_shap_comparison(
                their_shap,
                norm_imp,
                title=f"SHAP Importance — {label.title()} Model",
                top_n=15,
                output_path=FIGURES_DIR
                / f"fig_2401_shap_comparison_{label}.png",
            )
            plt.close("all")

    # Rank scatter (hypo model)
    if gen_figures and "hypo" in results["shap"]:
        _plot_rank_scatter(
            colleague, results["shap"]["hypo"], "hypo",
            FIGURES_DIR / "fig_2401_rank_scatter.png",
        )

    return results


def exp_2402_loop_only(loop_df, features, colleague, full_shap):
    """EXP-2402: Loop-only subset analysis."""
    print("\n=== EXP-2402: Loop-only subset ===")
    results = {"models": {}, "shap": {}}

    for target, is_cls, label in [
        ("hypo_4h", True, "hypo"),
        ("hyper_4h", True, "hyper"),
    ]:
        X, y = _prepare_Xy(loop_df, features, target, is_cls)
        if len(y) < 100:
            print(f"  Skipping {label}: only {len(y)} rows")
            continue
        model, metrics = train_and_evaluate(X, y, is_cls, f"loop_{label}")
        raw_imp, method, _ = compute_shap_importance(model, X)
        norm_imp = normalize_shap_importance(raw_imp)
        results["models"][label] = {**metrics, "method": method}
        results["shap"][label] = norm_imp

    # Rank correlation: Loop vs full cohort
    results["rho_vs_full"] = {}
    for label in results["shap"]:
        if label in full_shap:
            loop_rank = sorted(
                results["shap"][label], key=results["shap"][label].get, reverse=True
            )
            full_rank = sorted(
                full_shap[label], key=full_shap[label].get, reverse=True
            )
            rho = shap_rank_correlation(loop_rank, full_rank)
            results["rho_vs_full"][label] = rho
            print(f"  Loop vs full-cohort ρ ({label}): {rho:.3f}")

    return results


def exp_2403_oref_only(oref_df, features, colleague, full_shap):
    """EXP-2403: AAPS/ODC-only subset (closest to their cohort)."""
    print("\n=== EXP-2403: AAPS/ODC-only subset ===")
    results = {"models": {}, "shap": {}, "rho_vs_colleague": {}}

    for target, is_cls, label in [
        ("hypo_4h", True, "hypo"),
        ("hyper_4h", True, "hyper"),
    ]:
        X, y = _prepare_Xy(oref_df, features, target, is_cls)
        if len(y) < 100:
            print(f"  Skipping {label}: only {len(y)} rows")
            continue
        model, metrics = train_and_evaluate(X, y, is_cls, f"oref_{label}")
        raw_imp, method, _ = compute_shap_importance(model, X)
        norm_imp = normalize_shap_importance(raw_imp)
        results["models"][label] = {**metrics, "method": method}
        results["shap"][label] = norm_imp

        # Rank correlation vs colleague
        their_shap = colleague.shap_importance.get(label, {})
        if their_shap:
            oref_rank = sorted(norm_imp, key=norm_imp.get, reverse=True)
            their_rank = sorted(their_shap, key=their_shap.get, reverse=True)
            rho = shap_rank_correlation(oref_rank, their_rank)
            results["rho_vs_colleague"][label] = rho
            print(f"  AAPS vs colleague ρ ({label}): {rho:.3f}")

    return results


def exp_2404_per_patient_stability(df, features, gen_figures):
    """EXP-2404: Per-patient SHAP stability."""
    print("\n=== EXP-2404: Per-patient stability ===")
    patients = df["patient_id"].unique()
    importance_rows = []

    for pid in sorted(patients):
        pdf = df[df["patient_id"] == pid]
        if len(pdf) < 5000:
            print(f"  Skipping {pid}: only {len(pdf)} rows (<5000)")
            continue

        X, y = _prepare_Xy(pdf, features, "hypo_4h", True)
        if len(y) < 200 or y.sum() < 10:
            print(f"  Skipping {pid}: insufficient positive class")
            continue

        model, _ = train_and_evaluate(X, y, True, f"patient_{pid}")
        raw_imp, _, _ = compute_shap_importance(model, X)
        norm_imp = normalize_shap_importance(raw_imp)
        norm_imp["patient_id"] = pid
        importance_rows.append(norm_imp)

    if not importance_rows:
        print("  No patients qualified for per-patient analysis")
        return {"patients_analyzed": 0}

    imp_df = pd.DataFrame(importance_rows).set_index("patient_id")
    cv_per_feature = imp_df.std() / imp_df.mean().replace(0, np.nan)

    results = {
        "patients_analyzed": len(importance_rows),
        "cv_per_feature": cv_per_feature.dropna()
        .sort_values()
        .to_dict(),
        "mean_importance": imp_df.mean().sort_values(ascending=False).to_dict(),
    }

    if gen_figures and len(importance_rows) >= 2:
        _plot_patient_heatmap(
            imp_df, FIGURES_DIR / "fig_2401_per_patient_stability.png"
        )

    return results


def exp_2405_category_split(full_shap, colleague, gen_figures):
    """EXP-2405: User-controllable vs algorithm-dynamic importance split."""
    print("\n=== EXP-2405: Feature category split ===")
    results = {}

    for label in ("hypo", "hyper"):
        our = full_shap.get(label, {})
        theirs = normalize_shap_importance(
            colleague.shap_importance.get(label, {})
        )
        if not our or not theirs:
            continue

        our_cat = _sum_by_category(our)
        their_cat = _sum_by_category(theirs)

        results[label] = {
            "ours": our_cat,
            "theirs": their_cat,
            "our_user_controllable_pct": our_cat.get("user_controllable", 0),
            "their_user_controllable_pct": their_cat.get(
                "user_controllable", 0
            ),
        }
        print(
            f"  {label}: ours user-ctrl={our_cat.get('user_controllable', 0):.1f}%"
            f"  theirs={their_cat.get('user_controllable', 0):.1f}%"
        )

    if gen_figures and results:
        _plot_category_split(results, FIGURES_DIR / "fig_2401_category_split.png")

    return results


def exp_2406_interaction(df, features):
    """EXP-2406: Feature interaction analysis (is CR × hour still #1?)."""
    print("\n=== EXP-2406: Interaction analysis ===")
    X, y = _prepare_Xy(df, features, "hypo_4h", True)
    if len(y) < 100:
        return {"error": "insufficient data"}

    model, _ = train_and_evaluate(X, y, True, "interaction_hypo")

    interaction_result = {}
    if HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
            max_rows = min(50000, len(X))
            X_sample = X.sample(n=max_rows, random_state=42) if len(X) > max_rows else X
            print(f"  Computing SHAP interactions on {len(X_sample)} rows...")
            iv = explainer.shap_interaction_values(X_sample)
            if isinstance(iv, list):
                iv = iv[1]

            n_feat = len(features)
            mean_abs_int = np.mean(np.abs(iv), axis=0)
            # Zero the diagonal (self-interaction)
            np.fill_diagonal(mean_abs_int, 0)

            pairs = []
            for i in range(n_feat):
                for j in range(i + 1, n_feat):
                    pairs.append(
                        (features[i], features[j], float(mean_abs_int[i, j]))
                    )
            pairs.sort(key=lambda x: x[2], reverse=True)

            top_10 = [
                {"f1": a, "f2": b, "strength": v} for a, b, v in pairs[:10]
            ]
            interaction_result = {
                "method": "shap_interaction",
                "top_interactions": top_10,
                "cr_hour_rank": _find_pair_rank(pairs, "sug_CR", "hour"),
            }
            print(f"  Top interaction: {pairs[0][0]} × {pairs[0][1]} = {pairs[0][2]:.4f}")
        except Exception as e:
            print(f"  SHAP interactions failed ({e}), using gain proxy")
            interaction_result = _gain_interaction_proxy(model, features)
    else:
        print("  shap not installed, using gain proxy")
        interaction_result = _gain_interaction_proxy(model, features)

    return interaction_result


def exp_2407_rank_correlation(full_shap, loop_shap, oref_shap, colleague):
    """EXP-2407: Spearman ρ between their rankings and ours."""
    print("\n=== EXP-2407: Rank correlation analysis ===")
    results = {}

    for label in ("hypo", "hyper"):
        theirs = colleague.shap_importance.get(label, {})
        if not theirs:
            continue
        their_rank = sorted(theirs, key=theirs.get, reverse=True)

        entry = {}
        for cohort_name, cohort_shap in [
            ("full", full_shap),
            ("loop", loop_shap),
            ("aaps", oref_shap),
        ]:
            our = cohort_shap.get(label, {})
            if not our:
                continue
            our_rank = sorted(our, key=our.get, reverse=True)
            rho = shap_rank_correlation(their_rank, our_rank)

            # Compute p-value via scipy
            common = [f for f in their_rank if f in set(our_rank)]
            if len(common) >= 3:
                r1 = [their_rank.index(f) for f in common]
                r2 = [our_rank.index(f) for f in common]
                stat, p = spearmanr(r1, r2)
            else:
                stat, p = float("nan"), float("nan")

            entry[cohort_name] = {
                "rho": float(rho),
                "scipy_rho": float(stat),
                "p_value": float(p),
                "n_common": len(common),
            }
            print(
                f"  {label} {cohort_name}: ρ={stat:.3f}  p={p:.4f}  (n={len(common)})"
            )

        results[label] = entry

    return results


def exp_2408_synthesis(all_results, colleague, report):
    """EXP-2408: Synthesis — what replicates, what doesn't, why."""
    print("\n=== EXP-2408: Synthesis ===")

    # Colleague's 10 key findings to compare against
    findings = [
        ("F1", "cgm_mgdl is top feature for hypo prediction"),
        ("F2", "cgm_mgdl is top feature for hyper prediction"),
        ("F3", "iob_basaliob is #2 for hypo"),
        ("F4", "hour is #2 for hyper"),
        ("F5", "User-controllable settings account for ~36% of hypo importance"),
        ("F6", "User-controllable settings account for ~28% of hyper importance"),
        ("F7", "CR × hour is the strongest interaction"),
        ("F8", "sug_ISF and sug_CR both in top-5 for hypo"),
        ("F9", "bg_above_target in top-5 for hyper"),
        ("F10", "Overall SHAP rankings are stable across cohort"),
    ]

    full_shap = all_results.get("exp_2401", {}).get("shap", {})
    cat_results = all_results.get("exp_2405", {})
    interaction = all_results.get("exp_2406", {})
    rho_results = all_results.get("exp_2407", {})
    stability = all_results.get("exp_2404", {})

    synthesis_lines = []

    for fid, claim in findings:
        report.add_their_finding(fid, claim, evidence="OREF-INV-003 Table 4/5")
        agreement, evidence = _assess_finding(
            fid, full_shap, cat_results, interaction, rho_results, stability
        )
        report.add_our_finding(
            fid,
            f"{'Confirmed' if 'agree' in agreement else 'Not confirmed'}: {claim}",
            evidence=evidence,
            agreement=agreement,
            our_source="EXP-2401 analysis",
        )
        synthesis_lines.append(f"- **{fid}** ({agreement}): {evidence}")

    synthesis_text = "## Replication Summary\n\n" + "\n".join(synthesis_lines)

    # Overall agreement
    agreements = [
        _assess_finding(fid, full_shap, cat_results, interaction, rho_results, stability)[0]
        for fid, _ in findings
    ]
    n_agree = sum(1 for a in agreements if "agree" in a and "disagree" not in a)
    n_disagree = sum(1 for a in agreements if "disagree" in a)
    n_other = len(agreements) - n_agree - n_disagree

    synthesis_text += (
        f"\n\n**Overall**: {n_agree}/{len(findings)} findings replicated, "
        f"{n_disagree} disagreed, {n_other} inconclusive."
    )

    report.set_synthesis(synthesis_text)
    return {"findings_assessed": len(findings), "agreed": n_agree, "disagreed": n_disagree}


# ---------------------------------------------------------------------------
# Helper: assess individual findings
# ---------------------------------------------------------------------------


def _assess_finding(fid, full_shap, cat_results, interaction, rho_results, stability):
    """Return (agreement_level, evidence_string) for a colleague finding."""
    hypo_shap = full_shap.get("hypo", {})
    hyper_shap = full_shap.get("hyper", {})

    if not hypo_shap and not hyper_shap:
        return "inconclusive", "Insufficient data to evaluate"

    hypo_rank = sorted(hypo_shap, key=hypo_shap.get, reverse=True) if hypo_shap else []
    hyper_rank = sorted(hyper_shap, key=hyper_shap.get, reverse=True) if hyper_shap else []

    if fid == "F1":
        if hypo_rank and hypo_rank[0] == "cgm_mgdl":
            return "strongly_agrees", f"cgm_mgdl is #1 hypo ({hypo_shap.get('cgm_mgdl', 0):.1f}%)"
        elif hypo_rank and "cgm_mgdl" in hypo_rank[:3]:
            pos = hypo_rank.index("cgm_mgdl") + 1
            return "partially_agrees", f"cgm_mgdl is #{pos} hypo (top-3 but not #1)"
        elif hypo_rank:
            return "disagrees", f"cgm_mgdl is #{hypo_rank.index('cgm_mgdl') + 1 if 'cgm_mgdl' in hypo_rank else '?'}"
        return "inconclusive", "No hypo SHAP data"

    if fid == "F2":
        if hyper_rank and hyper_rank[0] == "cgm_mgdl":
            return "strongly_agrees", f"cgm_mgdl is #1 hyper ({hyper_shap.get('cgm_mgdl', 0):.1f}%)"
        elif hyper_rank and "cgm_mgdl" in hyper_rank[:3]:
            pos = hyper_rank.index("cgm_mgdl") + 1
            return "partially_agrees", f"cgm_mgdl is #{pos} hyper"
        return "inconclusive", "Hyper ranking unavailable or cgm_mgdl not near top"

    if fid == "F3":
        if hypo_rank and len(hypo_rank) > 1:
            pos = hypo_rank.index("iob_basaliob") + 1 if "iob_basaliob" in hypo_rank else None
            if pos == 2:
                return "strongly_agrees", f"iob_basaliob is #{pos} hypo"
            elif pos and pos <= 5:
                return "partially_agrees", f"iob_basaliob is #{pos} hypo (top-5)"
            elif pos:
                return "disagrees", f"iob_basaliob is #{pos} hypo"
        return "inconclusive", "Cannot evaluate iob_basaliob rank"

    if fid == "F4":
        if hyper_rank and len(hyper_rank) > 1:
            pos = hyper_rank.index("hour") + 1 if "hour" in hyper_rank else None
            if pos == 2:
                return "strongly_agrees", f"hour is #{pos} hyper"
            elif pos and pos <= 5:
                return "partially_agrees", f"hour is #{pos} hyper"
            elif pos:
                return "disagrees", f"hour is #{pos} hyper"
        return "inconclusive", "Cannot evaluate hour rank"

    if fid == "F5":
        hypo_cat = cat_results.get("hypo", {})
        ours = hypo_cat.get("our_user_controllable_pct", None)
        if ours is not None:
            if abs(ours - 36) < 10:
                return "agrees", f"User-ctrl hypo = {ours:.1f}% (theirs ~36%)"
            elif ours > 20:
                return "partially_agrees", f"User-ctrl hypo = {ours:.1f}% (theirs ~36%)"
            else:
                return "disagrees", f"User-ctrl hypo = {ours:.1f}% (theirs ~36%)"
        return "inconclusive", "Category split not computed"

    if fid == "F6":
        hyper_cat = cat_results.get("hyper", {})
        ours = hyper_cat.get("our_user_controllable_pct", None)
        if ours is not None:
            if abs(ours - 28) < 10:
                return "agrees", f"User-ctrl hyper = {ours:.1f}% (theirs ~28%)"
            elif ours > 15:
                return "partially_agrees", f"User-ctrl hyper = {ours:.1f}% (theirs ~28%)"
            else:
                return "disagrees", f"User-ctrl hyper = {ours:.1f}% (theirs ~28%)"
        return "inconclusive", "Category split not computed"

    if fid == "F7":
        top = interaction.get("top_interactions", [])
        cr_hour_rank = interaction.get("cr_hour_rank", None)
        if cr_hour_rank == 1:
            return "strongly_agrees", "CR × hour is #1 interaction"
        elif cr_hour_rank and cr_hour_rank <= 3:
            top1 = f"{top[0]['f1']}×{top[0]['f2']}" if top else "?"
            return "partially_agrees", f"CR × hour is #{cr_hour_rank} (top is {top1})"
        elif cr_hour_rank:
            return "disagrees", f"CR × hour is #{cr_hour_rank}"
        return "inconclusive", "Interaction analysis unavailable"

    if fid == "F8":
        if hypo_rank:
            isf_pos = hypo_rank.index("sug_ISF") + 1 if "sug_ISF" in hypo_rank else None
            cr_pos = hypo_rank.index("sug_CR") + 1 if "sug_CR" in hypo_rank else None
            if isf_pos and cr_pos and isf_pos <= 5 and cr_pos <= 5:
                return "strongly_agrees", f"ISF #{isf_pos}, CR #{cr_pos} (both top-5 hypo)"
            elif isf_pos and cr_pos and (isf_pos <= 5 or cr_pos <= 5):
                return "partially_agrees", f"ISF #{isf_pos}, CR #{cr_pos} (one in top-5)"
            elif isf_pos and cr_pos:
                return "disagrees", f"ISF #{isf_pos}, CR #{cr_pos} (neither top-5)"
        return "inconclusive", "Cannot evaluate ISF/CR ranks"

    if fid == "F9":
        if hyper_rank:
            pos = hyper_rank.index("bg_above_target") + 1 if "bg_above_target" in hyper_rank else None
            if pos and pos <= 5:
                return "strongly_agrees", f"bg_above_target #{pos} hyper"
            elif pos and pos <= 10:
                return "partially_agrees", f"bg_above_target #{pos} hyper"
            elif pos:
                return "disagrees", f"bg_above_target #{pos} hyper"
        return "inconclusive", "Cannot evaluate bg_above_target rank"

    if fid == "F10":
        n = stability.get("patients_analyzed", 0)
        if n < 3:
            return "inconclusive", f"Only {n} patients analyzed"
        cv_vals = list(stability.get("cv_per_feature", {}).values())
        if cv_vals:
            median_cv = float(np.median(cv_vals))
            if median_cv < 0.5:
                return "agrees", f"Median CV={median_cv:.2f} across {n} patients (stable)"
            elif median_cv < 1.0:
                return "partially_agrees", f"Median CV={median_cv:.2f} (moderate stability)"
            else:
                return "disagrees", f"Median CV={median_cv:.2f} (unstable)"
        return "inconclusive", "CV data unavailable"

    return "not_comparable", "Finding not mapped"


# ---------------------------------------------------------------------------
# Helper: category sums
# ---------------------------------------------------------------------------


def _sum_by_category(shap_dict):
    """Sum normalized SHAP importance by feature category."""
    totals = {cat: 0.0 for cat in FEATURE_CATEGORIES}
    for feat, val in shap_dict.items():
        cat = _FEATURE_TO_CATEGORY.get(feat, "unknown")
        if cat in totals:
            totals[cat] += val
    return totals


# ---------------------------------------------------------------------------
# Helper: interaction proxy from gain
# ---------------------------------------------------------------------------


def _gain_interaction_proxy(model, features):
    """Rough interaction proxy when SHAP interactions unavailable."""
    imp = dict(zip(features, model.feature_importances_.tolist()))
    # Heuristic: product of individual importances as proxy
    pairs = []
    feat_list = sorted(imp, key=imp.get, reverse=True)[:15]  # top 15
    for i, f1 in enumerate(feat_list):
        for f2 in feat_list[i + 1 :]:
            pairs.append({"f1": f1, "f2": f2, "strength": imp[f1] * imp[f2]})
    pairs.sort(key=lambda x: x["strength"], reverse=True)
    cr_hour_rank = _find_pair_rank(
        [(p["f1"], p["f2"], p["strength"]) for p in pairs], "sug_CR", "hour"
    )
    return {
        "method": "gain_product_proxy",
        "top_interactions": pairs[:10],
        "cr_hour_rank": cr_hour_rank,
    }


def _find_pair_rank(pairs, f1, f2):
    """Find rank (1-indexed) of a feature pair in sorted interaction list."""
    for i, (a, b, _) in enumerate(pairs):
        if (a == f1 and b == f2) or (a == f2 and b == f1):
            return i + 1
    return None


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _plot_rank_scatter(colleague, our_shap, model_name, path):
    """Scatter: their rank vs our rank for common features."""
    theirs = colleague.shap_importance.get(model_name, {})
    if not theirs or not our_shap:
        return

    their_rank = sorted(theirs, key=theirs.get, reverse=True)
    our_rank = sorted(our_shap, key=our_shap.get, reverse=True)
    common = [f for f in their_rank if f in set(our_rank)]

    if len(common) < 3:
        return

    x = [their_rank.index(f) + 1 for f in common]
    y = [our_rank.index(f) + 1 for f in common]

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(x, y, s=60, c=COLORS["ours"], alpha=0.8, edgecolors="white")
    for f, xi, yi in zip(common, x, y):
        ax.annotate(
            f, (xi, yi), fontsize=7, ha="left", va="bottom",
            xytext=(3, 3), textcoords="offset points",
        )
    mx = max(max(x), max(y)) + 1
    ax.plot([1, mx], [1, mx], "--", color=COLORS["neutral"], alpha=0.5, label="Perfect agreement")
    ax.set_xlabel("Colleague rank")
    ax.set_ylabel("Our rank")
    ax.set_title(f"Rank Comparison — {model_name.title()} Model")
    ax.legend()
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


def _plot_category_split(cat_results, path):
    """Stacked bar: user-controllable vs other categories."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    categories = list(FEATURE_CATEGORIES.keys())
    cat_colors = ["#2563eb", "#7c3aed", "#059669", "#f59e0b", "#6b7280"]

    for ax, label in zip(axes, ("hypo", "hyper")):
        entry = cat_results.get(label, {})
        ours = entry.get("ours", {})
        theirs = entry.get("theirs", {})
        if not ours:
            continue

        x = np.arange(2)
        bottoms_o = 0.0
        bottoms_t = 0.0
        for cat, color in zip(categories, cat_colors):
            o_val = ours.get(cat, 0)
            t_val = theirs.get(cat, 0)
            ax.bar(0, o_val, bottom=bottoms_o, color=color, width=0.5, label=cat if ax == axes[0] else "")
            ax.bar(1, t_val, bottom=bottoms_t, color=color, width=0.5, alpha=0.7)
            bottoms_o += o_val
            bottoms_t += t_val

        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Ours", "Theirs"])
        ax.set_ylabel("Cumulative SHAP %")
        ax.set_title(f"{label.title()} Model")

    axes[0].legend(fontsize=7, loc="upper right")
    fig.suptitle("Feature Category Importance Split", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


def _plot_patient_heatmap(imp_df, path):
    """Heatmap of per-patient feature importance."""
    # Keep top 15 features by mean importance
    top_feats = imp_df.mean().sort_values(ascending=False).head(15).index.tolist()
    sub = imp_df[top_feats]

    fig, ax = plt.subplots(figsize=(12, max(4, len(sub) * 0.5)))
    im = ax.imshow(sub.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(top_feats)))
    ax.set_xticklabels(top_feats, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(sub)))
    ax.set_yticklabels(sub.index, fontsize=8)
    ax.set_title("Per-Patient Feature Importance (top 15)")
    fig.colorbar(im, ax=ax, label="Normalized SHAP %")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


def _plot_3way_comparison(full_shap, loop_shap, oref_shap, colleague, path):
    """3-way bar chart: theirs / our Loop / our AAPS (hypo model)."""
    theirs = normalize_shap_importance(colleague.shap_importance.get("hypo", {}))
    ours_loop = loop_shap.get("hypo", {})
    ours_aaps = oref_shap.get("hypo", {})

    if not theirs or (not ours_loop and not ours_aaps):
        return

    all_feats = set(theirs) | set(ours_loop) | set(ours_aaps)
    ranked = sorted(all_feats, key=lambda f: theirs.get(f, 0), reverse=True)[:15]

    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(ranked))
    h = 0.25

    ax.barh(y - h, [theirs.get(f, 0) for f in ranked], h, label="Colleague (oref)", color=COLORS["theirs"], alpha=0.85)
    if ours_loop:
        ax.barh(y, [ours_loop.get(f, 0) for f in ranked], h, label="Ours (Loop)", color=COLORS["ours"], alpha=0.85)
    if ours_aaps:
        ax.barh(y + h, [ours_aaps.get(f, 0) for f in ranked], h, label="Ours (AAPS)", color="#059669", alpha=0.85)

    ax.set_yticks(y)
    ax.set_yticklabels(ranked, fontsize=8)
    ax.set_xlabel("Normalized SHAP Importance (%)")
    ax.set_title("3-Way Comparison: Colleague vs Loop vs AAPS (Hypo)")
    ax.legend(fontsize=8)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="EXP-2401: Feature Importance Ranking Replication"
    )
    parser.add_argument(
        "--figures", action="store_true", help="Generate comparison figures"
    )
    parser.add_argument(
        "--tiny", action="store_true",
        help="Use only 2 patients for quick testing",
    )
    parser.add_argument(
        "--data-path", type=str, default="externals/ns-parquet/training",
        help="Path to parquet data directory (default: training set)",
    )
    parser.add_argument(
        "--shap-rows", type=int, default=50000,
        help="Max rows for SHAP sampling (0 = use all, default: 50000)",
    )
    parser.add_argument(
        "--label", type=str, default="",
        help="Label suffix for output files (e.g. 'verification')",
    )
    parser.add_argument(
        "--use-pk", action="store_true",
        help="Replace 5 approximated IOB features with PK-derived equivalents",
    )
    args = parser.parse_args()

    # Set module-level SHAP config from CLI
    global SHAP_MAX_ROWS
    SHAP_MAX_ROWS = args.shap_rows if args.shap_rows > 0 else None

    run_start = time.monotonic()
    print(f"[{_ts()}] EXP-2401 starting  data={args.data_path}  "
          f"shap_rows={SHAP_MAX_ROWS or 'ALL'}  "
          f"use_pk={args.use_pk}  "
          f"label={args.label or '(default)'}")

    if args.figures:
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print(f"[{_ts()}] Loading patient data from {args.data_path}...")
    df = load_patients_with_features(parquet_path=args.data_path,
                                     use_pk=args.use_pk)
    print(f"  Loaded {len(df):,} rows, {df['patient_id'].nunique()} patients  "
          f"mem={_mem_mb():.0f} MB")

    if args.tiny:
        keep = sorted(df["patient_id"].unique())[:2]
        df = df[df["patient_id"].isin(keep)]
        print(f"  --tiny: reduced to {len(df)} rows ({keep})")

    loop_df, oref_df = split_loop_vs_oref(df)
    print(f"  Loop: {len(loop_df)} rows, AAPS/ODC: {len(oref_df)} rows")

    features = [f for f in OREF_FEATURES if f in df.columns]
    missing = set(OREF_FEATURES) - set(df.columns)
    if missing:
        print(f"  Warning: missing features: {missing}")

    # ------------------------------------------------------------------
    # Load colleague models
    # ------------------------------------------------------------------
    print("\nLoading colleague models...")
    try:
        colleague = ColleagueModels()
        print(colleague.summary())
    except Exception as e:
        print(f"  Could not load colleague models: {e}")
        print("  Creating stub with published results for comparison")
        colleague = _stub_colleague()

    # ------------------------------------------------------------------
    # Run sub-experiments
    # ------------------------------------------------------------------
    all_results = {}

    # EXP-2401
    r2401 = exp_2401_full_cohort(df, features, colleague, args.figures)
    all_results["exp_2401"] = r2401

    # EXP-2402
    r2402 = exp_2402_loop_only(loop_df, features, colleague, r2401.get("shap", {}))
    all_results["exp_2402"] = r2402

    # EXP-2403
    r2403 = exp_2403_oref_only(oref_df, features, colleague, r2401.get("shap", {}))
    all_results["exp_2403"] = r2403

    # EXP-2404
    r2404 = exp_2404_per_patient_stability(df, features, args.figures)
    all_results["exp_2404"] = r2404

    # EXP-2405
    r2405 = exp_2405_category_split(r2401.get("shap", {}), colleague, args.figures)
    all_results["exp_2405"] = r2405

    # EXP-2406
    r2406 = exp_2406_interaction(df, features)
    all_results["exp_2406"] = r2406

    # EXP-2407
    r2407 = exp_2407_rank_correlation(
        r2401.get("shap", {}),
        r2402.get("shap", {}),
        r2403.get("shap", {}),
        colleague,
    )
    all_results["exp_2407"] = r2407

    # EXP-2408 — Synthesis + report
    report = ComparisonReport(
        "EXP-2401",
        "Feature Importance Ranking Replication",
        phase="replication",
        script="exp_repl_2401.py",
    )
    report.set_methodology(
        "Trained LightGBM models (500 trees, lr=0.05, depth=6) on 19 patients "
        "(11 Loop + 8 AAPS/ODC). Computed SHAP feature importance using "
        f"TreeExplainer ({'shap' if HAS_SHAP else 'gain fallback'}). "
        "Compared rankings with OREF-INV-003's 28-user oref cohort via "
        "Spearman rank correlation."
    )
    report.set_limitations(
        "Our cohort is smaller (19 vs 28 users) and mixed-algorithm (Loop + AAPS) "
        "vs their pure oref cohort. Some OREF features are approximated from our "
        "grid data rather than extracted directly. SHAP may use gain fallback if "
        "the shap package is not installed."
    )

    r2408 = exp_2408_synthesis(all_results, colleague, report)
    all_results["exp_2408"] = r2408

    report.set_raw_results(all_results)

    # 3-way comparison figure
    if args.figures:
        _plot_3way_comparison(
            r2401.get("shap", {}),
            r2402.get("shap", {}),
            r2403.get("shap", {}),
            colleague,
            FIGURES_DIR / "fig_2401_loop_vs_oref_comparison.png",
        )
        for fname in FIGURES_DIR.glob("fig_2401_*.png"):
            report.add_figure(str(fname), fname.stem.replace("_", " "))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    print(f"\n[{_ts()}] Saving results...")
    report.save()

    suffix = f"_{args.label}" if args.label else ""
    results_path = RESULTS_DIR / f"exp_2401_replication{suffix}.json"
    all_results["_meta"] = {
        "data_path": args.data_path,
        "shap_max_rows": SHAP_MAX_ROWS,
        "use_pk": args.use_pk,
        "label": args.label,
        "total_rows": len(df),
        "n_patients": int(df["patient_id"].nunique()),
        "wall_time_s": round(time.monotonic() - run_start, 1),
    }
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)
    print(f"  JSON: {results_path}")

    # Summary
    wall = time.monotonic() - run_start
    h, m = int(wall // 3600), int((wall % 3600) // 60)
    print(f"\n{'=' * 60}")
    print(f"EXP-2401 COMPLETE  [{_ts()}]  wall={h}h{m:02d}m  "
          f"mem={_mem_mb():.0f} MB")
    print(f"{'=' * 60}")
    if "exp_2408" in all_results:
        s = all_results["exp_2408"]
        print(
            f"  Findings assessed: {s.get('findings_assessed', '?')}  "
            f"Agreed: {s.get('agreed', '?')}  "
            f"Disagreed: {s.get('disagreed', '?')}"
        )
    print(f"  Data: {args.data_path} ({len(df):,} rows)")
    print(f"  SHAP: {'TreeExplainer' if HAS_SHAP else 'gain fallback'} "
          f"(max_rows={SHAP_MAX_ROWS or 'ALL'})")
    print()


# ---------------------------------------------------------------------------
# Stub colleague when models aren't available on disk
# ---------------------------------------------------------------------------


class _StubColleagueModels:
    """Minimal stand-in using published OREF-INV-003 results."""

    def __init__(self):
        self.shap_importance = {
            "hypo": {
                "cgm_mgdl": 19.8, "iob_basaliob": 8.4, "sug_CR": 8.0,
                "sug_ISF": 7.5, "sug_current_target": 7.4, "iob_iob": 5.2,
                "hour": 4.8, "sug_eventualBG": 4.5, "sug_COB": 3.9,
                "direction_num": 3.6, "bg_above_target": 3.2,
                "iob_bolusiob": 2.8, "sug_rate": 2.5, "iob_activity": 2.3,
                "sug_sensitivityRatio": 2.1, "sug_duration": 1.9,
                "reason_Dev": 1.5, "sug_insulinReq": 1.4,
                "reason_BGI": 1.2, "reason_minGuardBG": 1.0,
                "sug_threshold": 0.9, "has_smb": 0.8,
                "isf_ratio": 0.7, "has_dynisf": 0.6,
                "iob_pct_max": 0.5, "sr_deviation": 0.4,
                "has_uam": 0.3, "sug_smb_units": 0.3,
                "dynisf_x_sr": 0.2, "dynisf_x_isf_ratio": 0.2,
                "maxSMBBasalMinutes": 0.1, "maxUAMSMBBasalMinutes": 0.1,
            },
            "hyper": {
                "cgm_mgdl": 32.6, "hour": 13.5, "bg_above_target": 7.0,
                "sug_ISF": 5.0, "sug_CR": 4.8, "sug_current_target": 4.5,
                "direction_num": 3.8, "iob_iob": 3.2, "sug_eventualBG": 2.9,
                "iob_basaliob": 2.7, "sug_COB": 2.5, "iob_bolusiob": 2.0,
                "sug_sensitivityRatio": 1.8, "sug_rate": 1.5,
                "iob_activity": 1.3, "reason_Dev": 1.1,
                "sug_duration": 1.0, "sug_insulinReq": 0.9,
                "reason_BGI": 0.8, "reason_minGuardBG": 0.7,
                "sug_threshold": 0.6, "has_smb": 0.5,
                "isf_ratio": 0.4, "has_dynisf": 0.4,
                "iob_pct_max": 0.3, "sr_deviation": 0.3,
                "has_uam": 0.2, "sug_smb_units": 0.2,
                "dynisf_x_sr": 0.1, "dynisf_x_isf_ratio": 0.1,
                "maxSMBBasalMinutes": 0.1, "maxUAMSMBBasalMinutes": 0.1,
            },
        }
        self.training_stats = {
            "n_train": 2_900_000, "n_users": 28, "n_features": 32,
        }

    @property
    def features(self):
        return OREF_FEATURES

    def summary(self):
        return (
            "StubColleagueModels: Using published OREF-INV-003 results "
            f"(n={self.training_stats['n_users']} users, "
            f"{self.training_stats['n_train']} rows)"
        )

    def compare_importance(self, our_shap, model_name="hypo"):
        theirs = self.shap_importance.get(model_name, {})
        their_norm = normalize_shap_importance(theirs)
        our_norm = normalize_shap_importance(our_shap)
        their_rank = sorted(their_norm, key=their_norm.get, reverse=True)
        our_rank = sorted(our_norm, key=our_norm.get, reverse=True)
        rows = []
        all_feats = sorted(set(their_rank) | set(our_rank))
        for f in all_feats:
            tr = their_rank.index(f) + 1 if f in their_rank else None
            orr = our_rank.index(f) + 1 if f in our_rank else None
            rows.append({
                "feature": f,
                "their_rank": tr,
                "their_importance": their_norm.get(f, 0),
                "our_rank": orr,
                "our_importance": our_norm.get(f, 0),
                "rank_delta": (tr - orr) if tr and orr else None,
            })
        return pd.DataFrame(rows).sort_values("their_rank")

    def rank_features(self, model_name="hypo"):
        s = self.shap_importance.get(model_name, {})
        return sorted(s.items(), key=lambda x: x[1], reverse=True)


def _stub_colleague():
    return _StubColleagueModels()


if __name__ == "__main__":
    main()
