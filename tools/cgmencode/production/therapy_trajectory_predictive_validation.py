"""therapy_trajectory_predictive_validation.py — the "AUC-proof" step.

Direct analog of Candidly's step 2: before doing anything else with the
turn-level emission features (regime-conditioned gates, unsupervised
discovery, etc.), prove they actually carry forward-looking signal about
the next turn's outcome. Candidly trained a classifier on their per-turn
features and got 0.90 AUC separating resolved vs abandoned conversations
*before* fitting the heavier IO-HMM. This module runs the same kind of
check on the therapy-trajectory turns.

Methodology, and why it's set up this way:

  * Binary framing (resolved-like vs not) rather than the full 5-value
    rule-based label, matching Candidly's own binary resolved/abandoned
    proof step. ``improving``/``stable_good`` -> 1 (resolved-like),
    ``worsening``/``stable_poor`` -> 0; ``unknown`` turns are dropped
    (no reliable follow-up to validate against).
  * Leave-*patient*-out cross-validation (``sklearn`` ``LeaveOneGroupOut``
    grouped by ``patient_id``), not a random split — a random split would
    let turns from the same patient leak across train/test and overstate
    accuracy, exactly the risk flagged in
    ``docs/60-research/state-aware-harness-parallels-2026-07-01.md`` §6.4
    as a precondition for trusting any state model built from this data.
  * Two feature sets are compared, not one: a "baseline" set (only the
    current turn's own glycemic state: TIR/TBR/TAR/CV) versus a "full"
    set that adds the researched physiology features (activity, flux/EGP,
    saturation, glycogen proxy, site wear). Current TIR is expected to
    have *some* predictive power just from continuity/regression-to-the-
    mean; the scientifically interesting question is whether the
    physiology features add predictive value *beyond* that, not whether
    the combined model beats chance.
  * Out-of-fold predicted probabilities are pooled across all
    leave-one-patient-out folds before computing a single AUC, rather
    than averaging per-fold AUCs — several patients have too few turns
    or too little class variation for a per-fold AUC to be meaningful on
    its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .controller_dynamics_facts_loader import ControllerDynamicsFactsLoader

BASELINE_FEATURES = ["tir", "tbr_l1", "tbr_l2", "tar_l1", "cv"]

PHYSIOLOGY_FEATURES = [
    "weekend_day_fraction",
    "meal_count",
    "bolus_active_row_count",
    "smb_active_row_count",
    "override_active_fraction",
    "exercise_active_fraction",
    "suspension_active_fraction",
    "mean_hepatic_production",
    "mean_carb_supply",
    "mean_insulin_demand",
    "mean_net_flux",
    "saturation_wall_pct",
    "carbs_48h_g",
    "mean_cage_hours",
    "mean_sage_hours",
]

FULL_FEATURES = BASELINE_FEATURES + PHYSIOLOGY_FEATURES

RESOLVED_STATES = {"improving", "stable_good"}
UNRESOLVED_STATES = {"worsening", "stable_poor"}
MIN_COMPLETENESS = 0.5


@dataclass
class EvaluationResult:
    feature_set_name: str
    features: list[str]
    n_samples: int
    n_groups: int
    n_groups_scored: int          # groups with both classes present (AUC-eligible)
    auc_pooled: float | None
    feature_importance: dict[str, float] = field(default_factory=dict)


def prepare_binary_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to reliable, resolved/unresolved turns and attach a binary label.

    Drops ``unknown`` turns (no reliable follow-up) and any turn whose own
    data completeness is below ``MIN_COMPLETENESS`` (matches the harness's
    own reliability gate).
    """
    reliable = df[df["data_completeness"] >= MIN_COMPLETENESS].copy()
    reliable = reliable[reliable["state"].isin(RESOLVED_STATES | UNRESOLVED_STATES)]
    reliable["resolved_like"] = reliable["state"].isin(RESOLVED_STATES).astype(int)
    return reliable


def evaluate_feature_set(
    df: pd.DataFrame,
    features: list[str],
    feature_set_name: str,
) -> EvaluationResult:
    """Leave-patient-out cross-validated AUC for one feature set.

    Returns ``auc_pooled=None`` if there isn't enough class variation
    across held-out folds to compute a meaningful AUC (e.g. too few
    patients or a degenerate label distribution).
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    available = [f for f in features if f in df.columns]
    X = df[available].to_numpy(dtype=float)
    y = df["resolved_like"].to_numpy()
    groups = df["patient_id"].to_numpy()
    n_groups = len(np.unique(groups))

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])

    auc_pooled = None
    n_groups_scored = 0
    if n_groups >= 2 and len(np.unique(y)) == 2:
        cv = LeaveOneGroupOut()
        try:
            oof_proba = cross_val_predict(
                pipeline, X, y, groups=groups, cv=cv, method="predict_proba",
            )[:, 1]
            auc_pooled = float(roc_auc_score(y, oof_proba))
        except ValueError:
            auc_pooled = None
        # Count how many held-out groups actually had both classes present
        # (informational only -- the pooled AUC above is the primary metric).
        for g in np.unique(groups):
            mask = groups == g
            if len(np.unique(y[mask])) == 2 or len(np.unique(y[~mask])) == 2:
                n_groups_scored += 1

    # Feature importance from a model refit on all data (qualitative only;
    # not itself cross-validated). Coefficient magnitude is meaningful
    # because features are standardized by the same pipeline.
    importance: dict[str, float] = {}
    try:
        pipeline.fit(X, y)
        coefs = pipeline.named_steps["clf"].coef_[0]
        importance = {f: float(c) for f, c in zip(available, coefs)}
    except ValueError:
        pass

    return EvaluationResult(
        feature_set_name=feature_set_name,
        features=available,
        n_samples=len(df),
        n_groups=n_groups,
        n_groups_scored=n_groups_scored,
        auc_pooled=auc_pooled,
        feature_importance=importance,
    )


def compare_feature_sets(df: pd.DataFrame) -> dict:
    """Run the baseline-vs-full comparison and return a plain-dict summary."""
    dataset = prepare_binary_dataset(df)
    baseline = evaluate_feature_set(dataset, BASELINE_FEATURES, "baseline_glycemic_only")
    full = evaluate_feature_set(dataset, FULL_FEATURES, "full_with_physiology")

    delta_auc = (
        full.auc_pooled - baseline.auc_pooled
        if baseline.auc_pooled is not None and full.auc_pooled is not None
        else None
    )
    top_physiology = sorted(
        (
            (feat, val) for feat, val in full.feature_importance.items()
            if feat in PHYSIOLOGY_FEATURES
        ),
        key=lambda kv: abs(kv[1]), reverse=True,
    )[:5]

    return {
        "n_samples": len(dataset),
        "n_groups": int(dataset["patient_id"].nunique()) if not dataset.empty else 0,
        "resolved_like_fraction": (
            float(dataset["resolved_like"].mean()) if not dataset.empty else None
        ),
        "baseline": {
            "features": baseline.features,
            "auc_pooled": baseline.auc_pooled,
        },
        "full": {
            "features": full.features,
            "auc_pooled": full.auc_pooled,
        },
        "delta_auc_from_physiology_features": delta_auc,
        "top_physiology_features_by_importance": top_physiology,
    }


def add_controller_lineage(
    df: pd.DataFrame,
    loader: ControllerDynamicsFactsLoader | None = None,
) -> pd.DataFrame:
    """Attach EXP-2753 ``controller_type`` ("loop"/"trio_openaps"/None) per row.

    Controller lineage is only known for a subset of patients (the
    EXP-2753 audition cohort); rows for other patients get ``None`` and
    are dropped by ``controller_stratified_summary`` rather than guessed.
    """
    loader = loader or ControllerDynamicsFactsLoader()
    out = df.copy()
    out["controller_type"] = out["patient_id"].map(
        lambda pid: loader.lookup(pid).controller_type
    )
    return out


def controller_stratified_summary(
    df: pd.DataFrame,
    loader: ControllerDynamicsFactsLoader | None = None,
) -> dict:
    """Check whether trajectory findings differ by controller lineage.

    Reports both a population-level (between-patient) view -- mean TIR
    and state mix per controller, where large differences are expected
    given known population differences between cohorts -- and a
    leave-patient-out AUC check for whether controller identity itself
    adds *within-patient* turn-level predictive value on top of the
    baseline/full feature sets. These answer different questions: the
    population view can show a large controller effect on average
    control quality while the AUC check correctly shows near-zero
    within-patient predictive value, because a patient-level-constant
    covariate cannot discriminate between that same patient's own turns
    under leave-one-patient-out validation. Both readings are reported
    to avoid overclaiming either "controller doesn't matter" or
    "controller silently drives the earlier predictive-signal result."
    """
    tagged = add_controller_lineage(df, loader=loader)
    known = tagged[tagged["controller_type"].notna()]
    if known.empty:
        return {"n_patients_with_known_controller": 0}

    dataset = prepare_binary_dataset(known)
    result: dict = {
        "n_patients_with_known_controller": int(known["patient_id"].nunique()),
        "mean_tir_by_controller": known.groupby("controller_type")["tir"].mean().round(1).to_dict(),
        "state_distribution_by_controller": {
            ctrl: g["state"].value_counts(normalize=True).round(3).to_dict()
            for ctrl, g in known.groupby("controller_type")
        },
    }
    if dataset.empty:
        return result

    dataset = dataset.assign(is_loop=(dataset["controller_type"] == "loop").astype(float))
    controller_only = evaluate_feature_set(dataset, ["is_loop"], "controller_identity_only")
    baseline_plus = evaluate_feature_set(
        dataset, BASELINE_FEATURES + ["is_loop"], "baseline_plus_controller",
    )
    baseline_alone = evaluate_feature_set(dataset, BASELINE_FEATURES, "baseline_known_controller_subset")

    result.update({
        "auc_controller_identity_only": controller_only.auc_pooled,
        "auc_baseline_known_controller_subset": baseline_alone.auc_pooled,
        "auc_baseline_plus_controller_identity": baseline_plus.auc_pooled,
        "controller_identity_within_patient_lift": (
            baseline_plus.auc_pooled - baseline_alone.auc_pooled
            if baseline_plus.auc_pooled is not None and baseline_alone.auc_pooled is not None
            else None
        ),
    })
    return result
