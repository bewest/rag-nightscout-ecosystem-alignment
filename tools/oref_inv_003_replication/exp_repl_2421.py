#!/usr/bin/env python3
"""
EXP-2421–2428: CR × Hour Interaction Replication

Replicates OREF-INV-003's Finding F2: "CR × hour is the strongest interaction".
The colleague found that carb ratio interacts with time of day more than any
other feature pair, with breakfast CR being the most impactful time block.

We test this on our independent data (11 Loop + 8 AAPS/ODC), augment with
pre-meal BG confound analysis (our EXP-2341 finding), and compare effective
CR vs scheduled CR by hour.

Experiments:
  2421 - Full-cohort CR × hour interaction ranking
  2422 - Per-patient CR × hour stability
  2423 - Effective CR by hour (vs scheduled CR)
  2424 - Pre-meal BG confound analysis
  2425 - Loop vs AAPS CR × hour comparison
  2426 - Circadian interaction map (all features × hour)
  2427 - Meal-centric analysis (spike regression)
  2428 - Synthesis

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2421 --figures
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2421 --figures --tiny
"""

import argparse
import json
import resource
import time
import warnings
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, r2_score
from scipy.stats import spearmanr, pearsonr

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
)
from oref_inv_003_replication.report_engine import (
    ComparisonReport,
    save_figure,
    NumpyEncoder,
    COLORS,
    PATIENT_COLORS,
)

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")


def _mem_mb():
    """Current RSS in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _ts():
    """Short UTC timestamp for log lines."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


RESULTS_PATH = Path("externals/experiments/exp_2421_cr_hour.json")
FIGURES_DIR = Path("tools/oref_inv_003_replication/figures")
RESULTS_DIR = Path("externals/experiments")

# Configurable at runtime via CLI
SHAP_INTERACTION_ROWS = 30000

# Time blocks for circadian analysis
TIME_BLOCKS = {
    "night":     (0, 6),
    "morning":   (6, 12),
    "afternoon": (12, 18),
    "evening":   (18, 24),
}

LGB_PARAMS = dict(
    n_estimators=500, learning_rate=0.05, max_depth=6,
    min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
    random_state=42, verbose=-1,
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def prepare_data(df: pd.DataFrame) -> tuple:
    """Prepare features and labels for modeling."""
    valid = df.dropna(subset=["cgm_mgdl", "hypo_4h", "hyper_4h"]).copy()
    X = valid[OREF_FEATURES].fillna(0)
    y_hypo = valid["hypo_4h"].astype(int)
    y_hyper = valid["hyper_4h"].astype(int)
    return X, y_hypo, y_hyper


def train_hypo_model(X: pd.DataFrame, y: pd.Series,
                     n_estimators: int = 500) -> lgb.LGBMClassifier:
    """Train a hypo LightGBM classifier and return it."""
    params = {**LGB_PARAMS, "n_estimators": n_estimators}
    model = lgb.LGBMClassifier(**params)
    model.fit(X, y)
    return model


def compute_interaction_strengths(model, X: pd.DataFrame,
                                  features: list, max_rows: int = None):
    """Compute pairwise interaction strengths.

    Uses SHAP interaction values if available; falls back to gain-based
    product proxy.

    Returns
    -------
    pairs : list[dict]
        Sorted list of {f1, f2, strength} dicts, highest first.
    method : str
        'shap_interaction' or 'gain_product_proxy'.
    matrix : np.ndarray or None
        Full interaction matrix (n_features × n_features) if SHAP, else None.
    """
    if max_rows is None:
        max_rows = SHAP_INTERACTION_ROWS
    if HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
            n_sample = min(max_rows, len(X))
            X_sample = X.sample(n=n_sample, random_state=42)
            n_feat = len(features)
            print(f"    [{_ts()}] SHAP interactions: {n_sample:,} rows × "
                  f"{n_feat} features  mem={_mem_mb():.0f} MB")
            t0 = time.monotonic()
            iv = explainer.shap_interaction_values(X_sample)
            elapsed = time.monotonic() - t0
            if isinstance(iv, list):
                iv = iv[1]
            print(f"    [{_ts()}] SHAP interactions done: {elapsed:.0f}s  "
                  f"({n_sample/elapsed:.0f} rows/s)  mem={_mem_mb():.0f} MB")

            n_feat = len(features)
            mean_abs = np.mean(np.abs(iv), axis=0)
            np.fill_diagonal(mean_abs, 0)

            pairs = []
            for i in range(n_feat):
                for j in range(i + 1, n_feat):
                    pairs.append({
                        "f1": features[i], "f2": features[j],
                        "strength": float(mean_abs[i, j]),
                    })
            pairs.sort(key=lambda x: x["strength"], reverse=True)
            return pairs, "shap_interaction", mean_abs
        except Exception as e:
            print(f"    SHAP interactions failed ({e}), using gain proxy")

    # Gain-based product proxy
    imp = dict(zip(features, model.feature_importances_.tolist()))
    top = sorted(imp, key=imp.get, reverse=True)[:20]
    pairs = []
    for i, f1 in enumerate(top):
        for f2 in top[i + 1:]:
            pairs.append({
                "f1": f1, "f2": f2,
                "strength": imp[f1] * imp[f2],
            })
    pairs.sort(key=lambda x: x["strength"], reverse=True)
    return pairs, "gain_product_proxy", None


def find_pair_rank(pairs: list, f1: str, f2: str):
    """Find 1-indexed rank of a feature pair in sorted interaction list."""
    for i, p in enumerate(pairs):
        if ({p["f1"], p["f2"]} == {f1, f2}):
            return i + 1
    return None


def hour_to_block(hour: float) -> str:
    """Map hour (0-23) to time block name."""
    for name, (lo, hi) in TIME_BLOCKS.items():
        if lo <= hour < hi:
            return name
    return "night"


def identify_meal_events(df: pd.DataFrame) -> pd.DataFrame:
    """Identify meal events as COB transitions from 0 → >0.

    Returns rows where the current COB is >0 and the previous row
    (within the same patient) had COB==0.
    """
    result = df.copy()
    result["prev_cob"] = result.groupby("patient_id")["sug_COB"].shift(1)
    meals = result[(result["sug_COB"] > 0) & (result["prev_cob"] == 0)].copy()
    meals = meals.drop(columns=["prev_cob"])
    return meals


# ---------------------------------------------------------------------------
# Sub-experiments
# ---------------------------------------------------------------------------


def run_2421(X, y_hypo, features, do_figures=False):
    """EXP-2421: Full-cohort CR × hour interaction ranking."""
    print("\n=== EXP-2421: CR × Hour Interaction (full cohort) ===")
    print("  Training hypo model...")
    model = train_hypo_model(X, y_hypo)

    pairs, method, matrix = compute_interaction_strengths(model, X, features)
    cr_hour_rank = find_pair_rank(pairs, "sug_CR", "hour")
    top_10 = pairs[:10]

    print(f"  Method: {method}")
    print(f"  CR × hour rank: #{cr_hour_rank}")
    for i, p in enumerate(top_10, 1):
        tag = " ← CR×hour" if {p["f1"], p["f2"]} == {"sug_CR", "hour"} else ""
        print(f"    {i:2d}. {p['f1']} × {p['f2']} = {p['strength']:.4f}{tag}")

    # Partial dependence for CR across time blocks
    pd_by_block = {}
    cr_values = np.linspace(X["sug_CR"].quantile(0.05),
                            X["sug_CR"].quantile(0.95), 20)
    for block_name, (lo, hi) in TIME_BLOCKS.items():
        mask = (X["hour"] >= lo) & (X["hour"] < hi)
        X_block = X[mask]
        if len(X_block) < 100:
            continue
        preds = []
        for cr_val in cr_values:
            X_mod = X_block.copy()
            X_mod["sug_CR"] = cr_val
            pred = model.predict_proba(X_mod)[:, 1].mean()
            preds.append(float(pred))
        pd_by_block[block_name] = {
            "cr_values": cr_values.tolist(),
            "hypo_prob": preds,
            "n_rows": int(mask.sum()),
        }

    if do_figures:
        _plot_interaction_heatmap(pairs, features, matrix,
                                 "fig_2421_interaction_heatmap.png")
        _plot_cr_partial_dependence(pd_by_block,
                                   "fig_2421_cr_by_timeblock.png")

    return {
        "method": method,
        "cr_hour_rank": cr_hour_rank,
        "top_10_interactions": top_10,
        "pd_by_block": pd_by_block,
        "hypo_model_importance": dict(zip(features,
            model.feature_importances_.tolist())),
    }


def run_2422(df, features, do_figures=False):
    """EXP-2422: Per-patient CR × hour interaction."""
    print("\n=== EXP-2422: Per-Patient CR × Hour ===")
    patient_results = {}

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        X_p, y_hypo_p, _ = prepare_data(pdf)
        if len(X_p) < 2000 or y_hypo_p.sum() < 20:
            print(f"  {pid}: skipped (too few rows or events)")
            continue

        model = train_hypo_model(X_p, y_hypo_p, n_estimators=200)
        pairs, method, _ = compute_interaction_strengths(
            model, X_p, features, max_rows=10000)
        cr_hour_rank = find_pair_rank(pairs, "sug_CR", "hour")
        top_1 = pairs[0] if pairs else {}

        patient_results[pid] = {
            "cr_hour_rank": cr_hour_rank,
            "top_interaction": top_1,
            "method": method,
            "n_rows": len(X_p),
        }
        top_str = f"{top_1.get('f1', '?')} × {top_1.get('f2', '?')}"
        print(f"  {pid}: CR×hour rank=#{cr_hour_rank}, top={top_str}")

    # Stability summary
    ranks = [r["cr_hour_rank"] for r in patient_results.values()
             if r["cr_hour_rank"] is not None]
    rank_is_1 = sum(1 for r in ranks if r == 1)
    rank_top3 = sum(1 for r in ranks if r <= 3)

    summary = {
        "patients_analyzed": len(patient_results),
        "cr_hour_rank_1_count": rank_is_1,
        "cr_hour_top3_count": rank_top3,
        "median_rank": float(np.median(ranks)) if ranks else None,
        "mean_rank": float(np.mean(ranks)) if ranks else None,
    }
    print(f"  Summary: {rank_is_1}/{len(ranks)} patients have CR×hour as #1")
    print(f"  Median CR×hour rank: {summary['median_rank']}")

    if do_figures and patient_results:
        _plot_per_patient_cr_hour(patient_results,
                                 "fig_2422_per_patient_cr_hour.png")

    return {"patients": patient_results, "summary": summary}


def run_2423(df, do_figures=False):
    """EXP-2423: Effective CR by hour of day.

    Computes effective_CR = actual_glucose_rise / carbs for meal events
    and compares with scheduled CR by hour.
    """
    print("\n=== EXP-2423: Effective CR by Hour ===")
    meals = identify_meal_events(df)
    if len(meals) < 20:
        print("  Too few meal events for analysis")
        return {"error": "insufficient_meals", "n_meals": len(meals)}

    # Compute effective CR for each meal event
    meals = meals.copy()
    meals["time_block"] = meals["hour"].apply(hour_to_block)

    # For effective CR we need glucose rise and carb amount
    # Use bg_change_4h as the glucose rise, sug_COB as carb proxy
    valid = meals.dropna(subset=["bg_change_4h"]).copy()
    valid = valid[valid["sug_COB"] > 0]

    if len(valid) < 20:
        print(f"  Only {len(valid)} valid meal events with outcomes")
        return {"error": "insufficient_valid_meals", "n_valid": len(valid)}

    # effective_CR: mg/dL rise per gram of carbs
    valid["effective_cr"] = valid["bg_change_4h"] / valid["sug_COB"]
    valid["scheduled_cr"] = valid["sug_CR"]

    block_stats = {}
    for block in TIME_BLOCKS:
        bm = valid[valid["time_block"] == block]
        if len(bm) < 5:
            continue
        block_stats[block] = {
            "n_meals": len(bm),
            "effective_cr_mean": float(bm["effective_cr"].mean()),
            "effective_cr_median": float(bm["effective_cr"].median()),
            "effective_cr_std": float(bm["effective_cr"].std()),
            "scheduled_cr_mean": float(bm["scheduled_cr"].mean()),
            "scheduled_cr_median": float(bm["scheduled_cr"].median()),
            "carbs_variance_explained": _r2_carbs_vs_rise(bm),
        }
        print(f"  {block:10s}: n={len(bm):3d}  eff_CR={bm['effective_cr'].median():.1f}  "
              f"sched_CR={bm['scheduled_cr'].median():.1f}  "
              f"carb_R²={block_stats[block]['carbs_variance_explained']:.3f}")

    # Overall correlation
    overall_r2 = _r2_carbs_vs_rise(valid)
    print(f"  Overall carbs→rise R²: {overall_r2:.3f}")

    # Is morning CR most different from scheduled?
    morning_gap = None
    if "morning" in block_stats:
        ms = block_stats["morning"]
        morning_gap = abs(ms["effective_cr_mean"] - ms["scheduled_cr_mean"])

    if do_figures and block_stats:
        _plot_effective_cr_by_hour(valid, block_stats,
                                  "fig_2423_effective_cr.png")

    return {
        "n_meal_events": len(valid),
        "block_stats": block_stats,
        "overall_carbs_r2": overall_r2,
        "morning_gap": morning_gap,
    }


def run_2424(df, features, do_figures=False):
    """EXP-2424: Pre-meal BG confound analysis.

    Our EXP-2341 found pre-meal BG explains 11-48% of rise variance vs
    carbs only 0-17%. When controlling for pre-meal BG, does CR × hour
    interaction weaken or strengthen?
    """
    print("\n=== EXP-2424: Pre-Meal BG Confound ===")
    X_full, y_hypo, _ = prepare_data(df)
    if len(X_full) < 500:
        return {"error": "insufficient_data"}

    # Model A: standard (all features)
    print("  Model A: all features...")
    model_a = train_hypo_model(X_full, y_hypo)
    pairs_a, method_a, _ = compute_interaction_strengths(
        model_a, X_full, features, max_rows=20000)
    rank_a = find_pair_rank(pairs_a, "sug_CR", "hour")

    # Model B: remove cgm_mgdl and bg_above_target (pre-meal BG proxies)
    confound_feats = ["cgm_mgdl", "bg_above_target"]
    features_b = [f for f in features if f not in confound_feats]
    X_b = X_full[features_b]
    print("  Model B: without pre-BG features...")
    model_b = train_hypo_model(X_b, y_hypo, n_estimators=500)
    pairs_b, method_b, _ = compute_interaction_strengths(
        model_b, X_b, features_b, max_rows=20000)
    rank_b = find_pair_rank(pairs_b, "sug_CR", "hour")

    # Model C: add explicit pre-BG × CR and pre-BG × hour interactions
    X_c = X_full.copy()
    X_c["bg_x_cr"] = X_c["cgm_mgdl"] * X_c["sug_CR"]
    X_c["bg_x_hour"] = X_c["cgm_mgdl"] * X_c["hour"]
    features_c = features + ["bg_x_cr", "bg_x_hour"]
    print("  Model C: with explicit BG interaction terms...")
    model_c = train_hypo_model(X_c, y_hypo, n_estimators=500)
    pairs_c, method_c, _ = compute_interaction_strengths(
        model_c, X_c, features_c, max_rows=20000)
    rank_c = find_pair_rank(pairs_c, "sug_CR", "hour")

    print(f"  CR×hour rank: A={rank_a}, B(no BG)={rank_b}, C(+BG terms)={rank_c}")

    # Pre-BG correlation with rise
    meals = identify_meal_events(df)
    meals_valid = meals.dropna(subset=["bg_change_4h", "cgm_mgdl"])
    if len(meals_valid) > 10:
        r_bg, p_bg = pearsonr(meals_valid["cgm_mgdl"], meals_valid["bg_change_4h"])
    else:
        r_bg, p_bg = float("nan"), float("nan")
    print(f"  Pre-BG vs rise: r={r_bg:.3f}, p={p_bg:.4f}")

    result = {
        "model_a_rank": rank_a,
        "model_a_top5": pairs_a[:5],
        "model_b_rank_no_bg": rank_b,
        "model_b_top5": pairs_b[:5],
        "model_c_rank_bg_interactions": rank_c,
        "model_c_top5": pairs_c[:5],
        "pre_bg_rise_r": float(r_bg),
        "pre_bg_rise_p": float(p_bg),
        "confound_features_removed": confound_feats,
    }

    if rank_a and rank_b:
        if rank_b < rank_a:
            result["confound_effect"] = "strengthens"
            print("  → Removing BG STRENGTHENS CR×hour (was confounded)")
        elif rank_b > rank_a:
            result["confound_effect"] = "weakens"
            print("  → Removing BG WEAKENS CR×hour")
        else:
            result["confound_effect"] = "no_change"
            print("  → No change in CR×hour rank")

    return result


def run_2425(df, features, do_figures=False):
    """EXP-2425: Loop vs AAPS CR × hour comparison."""
    print("\n=== EXP-2425: Loop vs AAPS CR × Hour ===")
    loop_df, oref_df = split_loop_vs_oref(df)
    results = {}

    for label, subset in [("Loop", loop_df), ("AAPS", oref_df)]:
        X_s, y_hypo_s, _ = prepare_data(subset)
        if len(X_s) < 1000 or y_hypo_s.sum() < 20:
            print(f"  {label}: skipped (too few rows)")
            continue

        model = train_hypo_model(X_s, y_hypo_s)
        pairs, method, _ = compute_interaction_strengths(
            model, X_s, features, max_rows=20000)
        cr_hour_rank = find_pair_rank(pairs, "sug_CR", "hour")

        results[label] = {
            "cr_hour_rank": cr_hour_rank,
            "top_5": pairs[:5],
            "method": method,
            "n_rows": len(X_s),
        }
        print(f"  {label}: CR×hour rank=#{cr_hour_rank}, n={len(X_s)}")

    if do_figures and len(results) == 2:
        _plot_loop_vs_aaps_interaction(results,
                                      "fig_2425_loop_vs_aaps_cr_hour.png")

    return results


def run_2426(X, y_hypo, features, do_figures=False):
    """EXP-2426: Full circadian interaction map (all features × hour)."""
    print("\n=== EXP-2426: Circadian Interaction Map ===")
    model = train_hypo_model(X, y_hypo)
    pairs, method, matrix = compute_interaction_strengths(
        model, X, features, max_rows=20000)

    # Extract all hour interactions
    hour_interactions = {}
    hour_idx = features.index("hour") if "hour" in features else None
    for p in pairs:
        if p["f1"] == "hour":
            hour_interactions[p["f2"]] = p["strength"]
        elif p["f2"] == "hour":
            hour_interactions[p["f1"]] = p["strength"]

    hour_sorted = sorted(hour_interactions.items(), key=lambda x: x[1], reverse=True)
    print(f"  Circadian interactions (method: {method}):")
    key_features = ["sug_CR", "sug_ISF", "iob_iob", "sug_COB",
                    "sug_current_target", "cgm_mgdl"]
    for feat, strength in hour_sorted[:10]:
        tag = " ←" if feat in key_features else ""
        print(f"    hour × {feat:25s} = {strength:.4f}{tag}")

    # ISF × hour rank (related to our EXP-2271 circadian ISF finding)
    isf_hour_rank = find_pair_rank(pairs, "sug_ISF", "hour")
    iob_hour_rank = find_pair_rank(pairs, "iob_iob", "hour")
    cob_hour_rank = find_pair_rank(pairs, "sug_COB", "hour")
    target_hour_rank = find_pair_rank(pairs, "sug_current_target", "hour")

    result = {
        "method": method,
        "hour_interactions": dict(hour_sorted),
        "key_ranks": {
            "cr_x_hour": find_pair_rank(pairs, "sug_CR", "hour"),
            "isf_x_hour": isf_hour_rank,
            "iob_x_hour": iob_hour_rank,
            "cob_x_hour": cob_hour_rank,
            "target_x_hour": target_hour_rank,
        },
    }
    print(f"  ISF×hour rank: #{isf_hour_rank} (ref: our EXP-2271 ISF varies 2-4×)")

    if do_figures:
        _plot_circadian_map(hour_sorted, "fig_2426_circadian_map.png")

    return result


def run_2427(df, features, do_figures=False):
    """EXP-2427: Meal-centric analysis — spike regression."""
    print("\n=== EXP-2427: Meal-Centric Analysis ===")
    meals = identify_meal_events(df)
    meals = meals.dropna(subset=["bg_change_4h", "cgm_mgdl",
                                  "sug_CR", "iob_iob"]).copy()
    if len(meals) < 30:
        print(f"  Only {len(meals)} meal events, skipping")
        return {"error": "insufficient_meals", "n_meals": len(meals)}

    meals["time_block"] = meals["hour"].apply(hour_to_block)
    print(f"  Meal events: {len(meals)}")
    for block in TIME_BLOCKS:
        n = (meals["time_block"] == block).sum()
        print(f"    {block:10s}: {n}")

    # Base regression: spike ~ CR + hour + pre_BG + IOB
    from sklearn.linear_model import LinearRegression

    y = meals["bg_change_4h"].values
    base_features = ["sug_CR", "hour", "cgm_mgdl", "iob_iob"]
    X_base = meals[base_features].fillna(0).values

    reg_base = LinearRegression().fit(X_base, y)
    r2_base = reg_base.score(X_base, y)
    print(f"  Base model R² (CR+hour+BG+IOB): {r2_base:.4f}")

    # With CR×hour interaction
    X_inter = np.column_stack([X_base, meals["sug_CR"] * meals["hour"]])
    reg_inter = LinearRegression().fit(X_inter, y)
    r2_inter = reg_inter.score(X_inter, y)
    delta_r2 = r2_inter - r2_base
    print(f"  +CR×hour R²: {r2_inter:.4f} (Δ={delta_r2:+.4f})")

    # Full model with all interactions
    bolus_timing = meals.get("sug_smb_units", pd.Series(0, index=meals.index))
    X_full = np.column_stack([
        X_base,
        meals["sug_CR"] * meals["hour"],
        meals["cgm_mgdl"] * meals["hour"],
        bolus_timing.fillna(0).values,
    ])
    reg_full = LinearRegression().fit(X_full, y)
    r2_full = reg_full.score(X_full, y)
    print(f"  Full model R²: {r2_full:.4f}")

    # Per-block R² for CR alone
    block_r2 = {}
    for block in TIME_BLOCKS:
        bm = meals[meals["time_block"] == block]
        if len(bm) < 10:
            continue
        yb = bm["bg_change_4h"].values
        xb = bm["sug_CR"].values.reshape(-1, 1)
        r2b = LinearRegression().fit(xb, yb).score(xb, yb)
        block_r2[block] = float(r2b)
        print(f"    {block}: CR-only R² = {r2b:.4f}")

    result = {
        "n_meals": len(meals),
        "r2_base": float(r2_base),
        "r2_with_cr_hour": float(r2_inter),
        "r2_delta_cr_hour": float(delta_r2),
        "r2_full": float(r2_full),
        "base_coefficients": dict(zip(
            base_features + ["CR×hour"],
            reg_inter.coef_.tolist(),
        )),
        "block_cr_r2": block_r2,
    }

    if do_figures:
        _plot_meal_regression(meals, block_r2, r2_base, r2_inter,
                             "fig_2427_meal_regression.png")

    return result


def run_2428(all_results, do_figures=False):
    """EXP-2428: Synthesis — generate comparison report."""
    print("\n=== EXP-2428: Synthesis ===")

    report = ComparisonReport(
        exp_id="EXP-2421",
        title="CR × Hour Interaction Replication",
        phase="replication",
        script="tools/oref_inv_003_replication/exp_repl_2421.py",
    )

    # Their finding
    report.add_their_finding(
        "F2", "CR × hour is the strongest interaction",
        evidence="LightGBM SHAP interaction analysis on 28 oref users. "
                 "Breakfast CR is the most impactful time block.",
        source="OREF-INV-003 Findings Overview",
    )

    # Our finding from EXP-2421
    r2421 = all_results.get("exp_2421", {})
    cr_rank = r2421.get("cr_hour_rank")
    if cr_rank == 1:
        agreement = "strongly_agrees"
        claim = "CR × hour is #1 interaction in our data"
    elif cr_rank and cr_rank <= 3:
        agreement = "agrees"
        claim = f"CR × hour is #{cr_rank} interaction (top-3)"
    elif cr_rank and cr_rank <= 5:
        agreement = "partially_agrees"
        claim = f"CR × hour is #{cr_rank} interaction (top-5)"
    elif cr_rank:
        agreement = "partially_disagrees"
        claim = f"CR × hour is #{cr_rank} interaction"
    else:
        agreement = "inconclusive"
        claim = "CR × hour rank could not be determined"

    report.add_our_finding(
        "F2", claim,
        evidence=f"Method: {r2421.get('method', '?')}, rank #{cr_rank}",
        agreement=agreement,
        our_source="EXP-2341 context CR, EXP-2221 meal pharma",
    )

    # Augmentation: pre-meal BG confound
    r2424 = all_results.get("exp_2424", {})
    confound_effect = r2424.get("confound_effect", "unknown")
    report.add_their_finding(
        "F2-aug", "CR × hour interaction (pre-BG not controlled)",
        evidence="Their LightGBM analysis did not explicitly control for "
                 "starting BG level.",
        source="OREF-INV-003 methodology",
    )
    report.add_our_finding(
        "F2-aug",
        f"Pre-meal BG confound {confound_effect} CR×hour interaction",
        evidence=f"Pre-BG→rise r={r2424.get('pre_bg_rise_r', '?'):.3f}. "
                 f"Model A rank={r2424.get('model_a_rank')}, "
                 f"B(no BG)={r2424.get('model_b_rank_no_bg')}, "
                 f"C(+BG terms)={r2424.get('model_c_rank_bg_interactions')}",
        agreement="not_comparable",
        our_source="EXP-2341: pre-BG explains 11-48% of rise variance",
    )

    # Effective CR finding
    r2423 = all_results.get("exp_2423", {})
    if "block_stats" in r2423:
        morning_stats = r2423["block_stats"].get("morning", {})
        overall_r2 = r2423.get("overall_carbs_r2", 0)
        report.add_our_finding(
            "F2-eff",
            f"Effective CR varies by time block (carbs R²={overall_r2:.3f})",
            evidence=f"Morning eff_CR={morning_stats.get('effective_cr_mean', '?'):.1f}, "
                     f"scheduled CR={morning_stats.get('scheduled_cr_mean', '?'):.1f}",
            agreement="agrees" if morning_stats else "inconclusive",
            our_source="EXP-2341: carb counting explains 1-15% of spike variance",
        )

    # Per-patient stability
    r2422 = all_results.get("exp_2422", {})
    summary_2422 = r2422.get("summary", {})
    if summary_2422.get("patients_analyzed", 0) > 0:
        pct_top1 = (summary_2422.get("cr_hour_rank_1_count", 0) /
                    max(1, summary_2422.get("patients_analyzed", 1))) * 100
        report.add_our_finding(
            "F2-stab",
            f"CR×hour is #1 in {pct_top1:.0f}% of patients "
            f"(median rank: {summary_2422.get('median_rank')})",
            evidence=f"{summary_2422.get('patients_analyzed')} patients analyzed",
            agreement="agrees" if pct_top1 > 40 else "partially_disagrees",
            our_source="Per-patient analysis",
        )

    # Loop vs AAPS
    r2425 = all_results.get("exp_2425", {})
    loop_rank = r2425.get("Loop", {}).get("cr_hour_rank")
    aaps_rank = r2425.get("AAPS", {}).get("cr_hour_rank")
    if loop_rank is not None and aaps_rank is not None:
        report.add_our_finding(
            "F2-alg",
            f"CR×hour: Loop=#{loop_rank}, AAPS=#{aaps_rank}",
            evidence="Different algorithms show "
                     f"{'similar' if abs(loop_rank - aaps_rank) <= 2 else 'different'} "
                     "CR×hour interaction strength",
            agreement="agrees" if abs(loop_rank - aaps_rank) <= 2 else "partially_disagrees",
            our_source="Algorithm comparison",
        )

    # Meal-centric
    r2427 = all_results.get("exp_2427", {})
    if "r2_delta_cr_hour" in r2427:
        delta = r2427["r2_delta_cr_hour"]
        report.add_our_finding(
            "F2-meal",
            f"Adding CR×hour improves meal spike R² by {delta:+.4f}",
            evidence=f"Base R²={r2427['r2_base']:.3f}, "
                     f"+CR×hour R²={r2427['r2_with_cr_hour']:.3f}",
            agreement="agrees" if delta > 0.01 else "partially_disagrees",
            our_source="EXP-2221 meal pharmacodynamics",
        )

    # Circadian map
    r2426 = all_results.get("exp_2426", {})
    key_ranks = r2426.get("key_ranks", {})
    if key_ranks:
        report.add_our_finding(
            "F2-circ",
            f"Circadian map: ISF×hour=#{key_ranks.get('isf_x_hour')}, "
            f"IOB×hour=#{key_ranks.get('iob_x_hour')}",
            evidence=f"CR×hour=#{key_ranks.get('cr_x_hour')}, "
                     f"target×hour=#{key_ranks.get('target_x_hour')}",
            agreement="not_comparable",
            our_source="EXP-2271: ISF varies 2-4× circadianly",
        )

    # Methodology
    report.set_methodology(
        "Trained LightGBM hypo classifiers (500 trees, lr=0.05, depth=6) on "
        "19 patients (11 Loop + 8 AAPS/ODC). Computed pairwise interaction "
        f"strengths via {'SHAP interaction values' if HAS_SHAP else 'gain product proxy'}. "
        "Augmented with pre-meal BG confound analysis, effective CR calculation, "
        "and meal-centric regression models."
    )

    # Synthesis narrative
    synth_lines = [
        f"CR × hour interaction rank in our data: #{cr_rank} "
        f"({'replicates' if cr_rank and cr_rank <= 3 else 'does not replicate'} "
        f"their #1 finding).",
    ]
    if confound_effect == "strengthens":
        synth_lines.append(
            "CRITICAL: Removing pre-meal BG strengthens CR×hour, suggesting "
            "their finding may be partially confounded by starting glucose."
        )
    elif confound_effect == "weakens":
        synth_lines.append(
            "Removing pre-meal BG weakens CR×hour, suggesting the interaction "
            "is genuine and not a BG confound."
        )
    if r2427.get("r2_delta_cr_hour", 0) > 0.01:
        synth_lines.append(
            f"Meal-centric regression confirms: CR×hour term adds "
            f"ΔR²={r2427['r2_delta_cr_hour']:+.4f} to spike prediction."
        )
    else:
        synth_lines.append(
            f"However, meal regression shows small CR×hour contribution "
            f"(ΔR²={r2427.get('r2_delta_cr_hour', 0):+.4f}), consistent with "
            f"our EXP-2341 finding that carb counting explains only 1-15% of variance."
        )
    report.set_synthesis("\n".join(synth_lines))

    report.set_limitations(
        "Our cohort is smaller (19 vs 28 users) and mixed-algorithm (Loop + AAPS) "
        "vs their pure oref cohort. Effective CR uses COB as a carb proxy, which "
        "may underestimate actual carb intake. SHAP interaction values are "
        "computationally expensive and may use a gain-based proxy instead."
    )

    if do_figures:
        # Collect generated figures
        for fig_path in FIGURES_DIR.glob("fig_242*.png"):
            report.add_figure(fig_path.name, fig_path.stem.replace("_", " "))

    report.set_raw_results(all_results)
    report.save()

    return {
        "cr_hour_rank": cr_rank,
        "agreement": agreement,
        "confound_effect": confound_effect,
    }


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _plot_interaction_heatmap(pairs, features, matrix, output_name):
    """Heatmap of top interaction strengths."""
    fig, ax = plt.subplots(figsize=(10, 8))

    if matrix is not None:
        # Use actual SHAP interaction matrix (top 15 features)
        imp = np.diag(matrix) if matrix.shape[0] > 0 else np.zeros(len(features))
        top_idx = np.argsort(imp)[-15:][::-1]
        sub_matrix = matrix[np.ix_(top_idx, top_idx)]
        np.fill_diagonal(sub_matrix, 0)
        top_names = [features[i] for i in top_idx]

        im = ax.imshow(sub_matrix, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(len(top_names)))
        ax.set_xticklabels(top_names, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(len(top_names)))
        ax.set_yticklabels(top_names, fontsize=7)
        fig.colorbar(im, ax=ax, label="Mean |SHAP interaction|")
    else:
        # Build matrix from pairs list (gain proxy)
        top_feats = set()
        for p in pairs[:30]:
            top_feats.add(p["f1"])
            top_feats.add(p["f2"])
        top_feats = sorted(top_feats)[:15]
        n = len(top_feats)
        mat = np.zeros((n, n))
        feat_idx = {f: i for i, f in enumerate(top_feats)}
        for p in pairs:
            if p["f1"] in feat_idx and p["f2"] in feat_idx:
                i, j = feat_idx[p["f1"]], feat_idx[p["f2"]]
                mat[i, j] = mat[j, i] = p["strength"]

        im = ax.imshow(mat, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(n))
        ax.set_xticklabels(top_feats, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(n))
        ax.set_yticklabels(top_feats, fontsize=7)
        fig.colorbar(im, ax=ax, label="Interaction strength (gain proxy)")

    ax.set_title("Feature Interaction Heatmap — Hypo Model", fontweight="bold")
    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_cr_partial_dependence(pd_by_block, output_name):
    """Partial dependence of CR across time blocks."""
    fig, ax = plt.subplots(figsize=(10, 6))
    block_colors = {
        "night": "#6366f1", "morning": "#f59e0b",
        "afternoon": "#10b981", "evening": "#ef4444",
    }
    for block, data in pd_by_block.items():
        color = block_colors.get(block, "#6b7280")
        ax.plot(data["cr_values"], data["hypo_prob"],
                "-o", color=color, markersize=3, linewidth=2,
                label=f"{block} (n={data['n_rows']:,})", alpha=0.9)
    ax.set_xlabel("Carb Ratio (g/U)", fontsize=11)
    ax.set_ylabel("Predicted Hypo Probability", fontsize=11)
    ax.set_title("CR Partial Dependence by Time Block", fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_facecolor(COLORS["bg_light"])
    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_per_patient_cr_hour(patient_results, output_name):
    """Bar chart of CR×hour rank per patient."""
    pids = sorted(patient_results.keys())
    ranks = [patient_results[p]["cr_hour_rank"] or 0 for p in pids]
    colors = [PATIENT_COLORS.get(p, "#6b7280") for p in pids]

    fig, ax = plt.subplots(figsize=(12, 5))
    bars = ax.bar(range(len(pids)), ranks, color=colors, edgecolor="white")
    ax.axhline(y=1, color="#059669", linestyle="--", alpha=0.7, label="Rank #1")
    ax.axhline(y=3, color="#f59e0b", linestyle="--", alpha=0.5, label="Top-3")
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=8)
    ax.set_xlabel("Patient ID")
    ax.set_ylabel("CR × Hour Interaction Rank")
    ax.set_title("Per-Patient CR × Hour Rank", fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_effective_cr_by_hour(meals_df, block_stats, output_name):
    """Box plot of effective CR by time block vs scheduled CR."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    blocks_order = ["night", "morning", "afternoon", "evening"]
    present_blocks = [b for b in blocks_order if b in block_stats]
    block_colors = {
        "night": "#6366f1", "morning": "#f59e0b",
        "afternoon": "#10b981", "evening": "#ef4444",
    }

    # Box plot of effective CR
    data_boxes = []
    labels = []
    colors = []
    for b in present_blocks:
        bm = meals_df[meals_df["time_block"] == b]
        data_boxes.append(bm["effective_cr"].dropna().values)
        labels.append(f"{b}\n(n={len(bm)})")
        colors.append(block_colors.get(b, "#6b7280"))

    if data_boxes:
        bp = ax1.boxplot(data_boxes, labels=labels, patch_artist=True)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
    ax1.set_ylabel("Effective CR (mg/dL per g carbs)")
    ax1.set_title("Effective CR by Time Block", fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)

    # Scheduled vs effective CR comparison
    x = range(len(present_blocks))
    eff_means = [block_stats[b]["effective_cr_mean"] for b in present_blocks]
    sched_means = [block_stats[b]["scheduled_cr_mean"] for b in present_blocks]
    width = 0.35
    ax2.bar([i - width / 2 for i in x], sched_means, width,
            label="Scheduled CR", color=COLORS["theirs"], alpha=0.7)
    ax2.bar([i + width / 2 for i in x], eff_means, width,
            label="Effective CR", color=COLORS["ours"], alpha=0.7)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(present_blocks)
    ax2.set_ylabel("CR value")
    ax2.set_title("Scheduled vs Effective CR", fontweight="bold")
    ax2.legend()
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_loop_vs_aaps_interaction(results, output_name):
    """Side-by-side top interactions for Loop vs AAPS."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    for ax, label in [(ax1, "Loop"), (ax2, "AAPS")]:
        r = results.get(label, {})
        top5 = r.get("top_5", [])
        if not top5:
            ax.text(0.5, 0.5, f"No data for {label}", ha="center", va="center",
                    transform=ax.transAxes)
            continue
        names = [f"{p['f1']}\n×{p['f2']}" for p in top5]
        vals = [p["strength"] for p in top5]
        cr_hour_mask = [{p["f1"], p["f2"]} == {"sug_CR", "hour"} for p in top5]
        bar_colors = ["#f59e0b" if m else COLORS["ours"] for m in cr_hour_mask]
        ax.barh(range(len(names)), vals, color=bar_colors, edgecolor="white")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel("Interaction Strength")
        ax.set_title(f"{label} Top-5 Interactions\n(CR×hour rank: "
                     f"#{r.get('cr_hour_rank', '?')})",
                     fontweight="bold")
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_circadian_map(hour_sorted, output_name):
    """Bar chart of all feature × hour interaction strengths."""
    top_n = min(15, len(hour_sorted))
    feats = [f for f, _ in hour_sorted[:top_n]]
    vals = [v for _, v in hour_sorted[:top_n]]
    key_feats = {"sug_CR", "sug_ISF", "iob_iob", "sug_COB", "sug_current_target"}
    bar_colors = ["#f59e0b" if f in key_feats else COLORS["ours"] for f in feats]

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(range(len(feats)), vals, color=bar_colors, edgecolor="white")
    ax.set_yticks(range(len(feats)))
    ax.set_yticklabels(feats, fontsize=8)
    ax.set_xlabel("Interaction Strength with Hour")
    ax.set_title("Circadian Interaction Map: Feature × Hour", fontweight="bold")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)
    ax.set_facecolor(COLORS["bg_light"])
    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _plot_meal_regression(meals_df, block_r2, r2_base, r2_inter, output_name):
    """Meal regression summary figure."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Left: scatter of CR vs spike by time block
    block_colors = {
        "night": "#6366f1", "morning": "#f59e0b",
        "afternoon": "#10b981", "evening": "#ef4444",
    }
    for block, color in block_colors.items():
        bm = meals_df[meals_df["time_block"] == block]
        if len(bm) == 0:
            continue
        ax1.scatter(bm["sug_CR"], bm["bg_change_4h"],
                    c=color, alpha=0.4, s=15, label=block)
    ax1.set_xlabel("Carb Ratio (g/U)")
    ax1.set_ylabel("4h BG Change (mg/dL)")
    ax1.set_title("CR vs Spike by Time Block", fontweight="bold")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color="gray", linestyle=":", alpha=0.5)

    # Right: R² comparison bar chart
    models = ["CR only\n(overall)"]
    r2_vals = [block_r2.get("morning", 0)]
    models.append("Base\n(CR+hour+BG+IOB)")
    r2_vals.append(r2_base)
    models.append("+CR×hour")
    r2_vals.append(r2_inter)

    for block in ["night", "morning", "afternoon", "evening"]:
        if block in block_r2:
            models.append(f"CR only\n({block})")
            r2_vals.append(block_r2[block])

    bar_colors_list = [COLORS["ours"]] * len(models)
    ax2.bar(range(len(models)), r2_vals, color=bar_colors_list,
            edgecolor="white", alpha=0.8)
    ax2.set_xticks(range(len(models)))
    ax2.set_xticklabels(models, fontsize=7, rotation=30, ha="right")
    ax2.set_ylabel("R²")
    ax2.set_title("Spike Prediction R² Comparison", fontweight="bold")
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_name)
    plt.close(fig)


def _r2_carbs_vs_rise(df: pd.DataFrame) -> float:
    """R² of carbs (COB) predicting glucose rise."""
    valid = df.dropna(subset=["sug_COB", "bg_change_4h"])
    valid = valid[valid["sug_COB"] > 0]
    if len(valid) < 10:
        return float("nan")
    from sklearn.linear_model import LinearRegression
    X = valid["sug_COB"].values.reshape(-1, 1)
    y = valid["bg_change_4h"].values
    return float(LinearRegression().fit(X, y).score(X, y))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="EXP-2421: CR × Hour Interaction Replication"
    )
    parser.add_argument("--figures", action="store_true",
                        help="Generate comparison figures")
    parser.add_argument("--tiny", action="store_true",
                        help="Use only 2 patients for quick testing")
    parser.add_argument(
        "--data-path", type=str, default="externals/ns-parquet/training",
        help="Path to parquet data directory (default: training set)",
    )
    parser.add_argument(
        "--shap-rows", type=int, default=30000,
        help="Max rows for SHAP interaction sampling (default: 30000)",
    )
    parser.add_argument(
        "--label", type=str, default="",
        help="Label suffix for output files (e.g. 'verification')",
    )
    args = parser.parse_args()

    # Set module-level config
    global SHAP_INTERACTION_ROWS
    SHAP_INTERACTION_ROWS = args.shap_rows

    run_start = time.monotonic()
    print("=" * 70)
    print("EXP-2421–2428: CR × Hour Interaction Replication")
    print("=" * 70)
    print(f"[{_ts()}] data={args.data_path}  shap_rows={SHAP_INTERACTION_ROWS}  "
          f"label={args.label or '(default)'}")

    if args.figures:
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"[{_ts()}] Loading patient data from {args.data_path}...")
    df = load_patients_with_features(parquet_path=args.data_path)
    print(f"  Loaded {len(df):,} rows, {df['patient_id'].nunique()} patients  "
          f"mem={_mem_mb():.0f} MB")

    if args.tiny:
        keep = sorted(df["patient_id"].unique())[:2]
        df = df[df["patient_id"].isin(keep)]
        print(f"  --tiny: reduced to {len(df):,} rows ({keep})")

    X, y_hypo, y_hyper = prepare_data(df)
    features = [f for f in OREF_FEATURES if f in X.columns]
    missing = set(OREF_FEATURES) - set(X.columns)
    if missing:
        print(f"  Warning: missing features: {missing}")

    print(f"  Data: {len(X):,} rows, {X.shape[1]} features")
    print(f"  Hypo rate: {y_hypo.mean() * 100:.1f}%, "
          f"Hyper rate: {y_hyper.mean() * 100:.1f}%")

    # Run sub-experiments
    all_results = {}

    for name, func, func_args in [
        ("exp_2421", run_2421, (X, y_hypo, features, args.figures)),
        ("exp_2422", run_2422, (df, features, args.figures)),
        ("exp_2423", run_2423, (df, args.figures)),
        ("exp_2424", run_2424, (df, features, args.figures)),
        ("exp_2425", run_2425, (df, features, args.figures)),
        ("exp_2426", run_2426, (X, y_hypo, features, args.figures)),
        ("exp_2427", run_2427, (df, features, args.figures)),
    ]:
        sub_start = time.monotonic()
        all_results[name] = func(*func_args)
        sub_elapsed = time.monotonic() - sub_start
        wall_so_far = time.monotonic() - run_start
        print(f"  [{_ts()}] {name} done in {sub_elapsed:.0f}s  "
              f"(total {wall_so_far:.0f}s)  mem={_mem_mb():.0f} MB")

    all_results["exp_2428"] = run_2428(all_results, args.figures)

    # Save JSON results
    suffix = f"_{args.label}" if args.label else ""
    results_path = RESULTS_DIR / f"exp_2421_cr_hour{suffix}.json"
    all_results["_meta"] = {
        "data_path": args.data_path,
        "shap_interaction_rows": SHAP_INTERACTION_ROWS,
        "label": args.label,
        "total_rows": len(df),
        "n_patients": int(df["patient_id"].nunique()),
        "wall_time_s": round(time.monotonic() - run_start, 1),
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)
    print(f"\n[{_ts()}] Results saved to {results_path}")

    # Summary
    wall = time.monotonic() - run_start
    h, m = int(wall // 3600), int((wall % 3600) // 60)
    print(f"\n{'=' * 60}")
    print(f"EXP-2421 COMPLETE  [{_ts()}]  wall={h}h{m:02d}m  "
          f"mem={_mem_mb():.0f} MB")
    print(f"{'=' * 60}")
    r = all_results.get("exp_2421", {})
    print(f"  CR × hour rank: #{r.get('cr_hour_rank', '?')}")
    print(f"  Method: {r.get('method', '?')}")
    s = all_results.get("exp_2428", {})
    print(f"  Agreement: {s.get('agreement', '?')}")
    print(f"  Confound effect: {s.get('confound_effect', '?')}")
    print(f"  Data: {args.data_path} ({len(df):,} rows)")
    print(f"  SHAP: {'TreeExplainer' if HAS_SHAP else 'gain fallback'} "
          f"(interaction_rows={SHAP_INTERACTION_ROWS})")
    print()


if __name__ == "__main__":
    main()
