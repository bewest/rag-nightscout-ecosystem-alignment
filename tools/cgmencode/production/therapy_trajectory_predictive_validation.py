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

# Recency/momentum/episode-level features added after the first-cut "full"
# feature set tested null (§6.4 of the design doc): a flat 72h mean may
# dilute exactly the timing signal that matters, so these instead capture
# "what happened most recently" and "is the turn itself trending", plus
# saturation episode-level detail beyond the aggregate wall_pct.
RECENCY_MOMENTUM_FEATURES = [
    "last24h_tir",
    "last24h_tbr_l1",
    "last24h_tbr_l2",
    "last24h_net_flux_mean",
    "tir_within_turn_trend",
    "net_flux_std",
    "n_wall_episodes",
    "n_high_glucose_episodes",
    "excess_insulin_u",
    "delayed_hypo_risk",
]

FULL_FEATURES = BASELINE_FEATURES + PHYSIOLOGY_FEATURES
REFINED_FEATURES = FULL_FEATURES + RECENCY_MOMENTUM_FEATURES

RESOLVED_STATES = {"improving", "stable_good"}
UNRESOLVED_STATES = {"worsening", "stable_poor"}
MIN_COMPLETENESS = 0.5
DEFAULT_MODEL = "logistic"


@dataclass
class EvaluationResult:
    feature_set_name: str
    features: list[str]
    n_samples: int
    n_groups: int
    n_groups_scored: int          # groups with both classes present (AUC-eligible)
    auc_pooled: float | None
    model: str = DEFAULT_MODEL
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


def _build_pipeline(model: str):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if model == "logistic":
        clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    elif model == "gbm":
        from sklearn.ensemble import HistGradientBoostingClassifier
        clf = HistGradientBoostingClassifier(class_weight="balanced", random_state=0)
    else:
        raise ValueError(f"Unknown model type: {model!r} (expected 'logistic' or 'gbm')")

    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", clf),
    ])


def evaluate_feature_set(
    df: pd.DataFrame,
    features: list[str],
    feature_set_name: str,
    model: str = DEFAULT_MODEL,
) -> EvaluationResult:
    """Leave-patient-out cross-validated AUC for one feature set.

    ``model`` is ``"logistic"`` (default; interpretable, gives feature
    coefficients) or ``"gbm"`` (``HistGradientBoostingClassifier``; can
    capture nonlinearities/interactions the linear model misses, at the
    cost of not returning a simple per-feature coefficient).

    Returns ``auc_pooled=None`` if there isn't enough class variation
    across held-out folds to compute a meaningful AUC (e.g. too few
    patients or a degenerate label distribution).
    """
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict

    available = [f for f in features if f in df.columns]
    X = df[available].to_numpy(dtype=float)
    y = df["resolved_like"].to_numpy()
    groups = df["patient_id"].to_numpy()
    n_groups = len(np.unique(groups))

    pipeline = _build_pipeline(model)

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
    # because features are standardized by the same pipeline. Only
    # extracted for the logistic model -- GBM importance would need
    # permutation importance, which is a separate, heavier computation
    # not included here.
    importance: dict[str, float] = {}
    if model == "logistic":
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
        model=model,
        feature_importance=importance,
    )


def compare_feature_sets(df: pd.DataFrame, model: str = DEFAULT_MODEL) -> dict:
    """Run the baseline-vs-full-vs-refined comparison and return a summary.

    ``model`` applies to every feature set compared, so the comparison is
    apples-to-apples (see ``evaluate_feature_set`` for model choices).
    """
    dataset = prepare_binary_dataset(df)
    baseline = evaluate_feature_set(dataset, BASELINE_FEATURES, "baseline_glycemic_only", model=model)
    full = evaluate_feature_set(dataset, FULL_FEATURES, "full_with_physiology", model=model)
    refined = evaluate_feature_set(
        dataset, REFINED_FEATURES, "refined_with_recency_momentum", model=model,
    )

    def _delta(a: EvaluationResult, b: EvaluationResult) -> float | None:
        if a.auc_pooled is None or b.auc_pooled is None:
            return None
        return b.auc_pooled - a.auc_pooled

    def _top_features(result: EvaluationResult, pool: list[str], n: int = 5) -> list[tuple[str, float]]:
        return sorted(
            ((feat, val) for feat, val in result.feature_importance.items() if feat in pool),
            key=lambda kv: abs(kv[1]), reverse=True,
        )[:n]

    return {
        "model": model,
        "n_samples": len(dataset),
        "n_groups": int(dataset["patient_id"].nunique()) if not dataset.empty else 0,
        "resolved_like_fraction": (
            float(dataset["resolved_like"].mean()) if not dataset.empty else None
        ),
        "baseline": {"features": baseline.features, "auc_pooled": baseline.auc_pooled},
        "full": {"features": full.features, "auc_pooled": full.auc_pooled},
        "refined": {"features": refined.features, "auc_pooled": refined.auc_pooled},
        "delta_auc_from_physiology_features": _delta(baseline, full),
        "delta_auc_from_recency_momentum_features": _delta(full, refined),
        "delta_auc_refined_vs_baseline": _delta(baseline, refined),
        "top_physiology_features_by_importance": _top_features(full, PHYSIOLOGY_FEATURES),
        "top_recency_momentum_features_by_importance": _top_features(
            refined, RECENCY_MOMENTUM_FEATURES,
        ),
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
