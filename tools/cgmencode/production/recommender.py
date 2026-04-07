"""
recommender.py — Action recommendation engine.

Orchestrates meal prediction + settings advice into a prioritized
list of ActionRecommendations.

Priority system:
  1. SAFETY — hypo alerts, urgent dosing concerns
  2. TIR — settings changes, eating_soon recommendations
  3. CONVENIENCE — informational pattern insights

Each recommendation includes a predicted TIR improvement and
confidence score, enabling the clinical team to evaluate
cost/benefit before acting.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .types import (
    ActionRecommendation, ClinicalReport, HypoAlert,
    MealHistory, MealPrediction, MetabolicState,
    PatientProfile, PipelineResult, SettingsRecommendation,
)


def generate_recommendations(
    clinical: ClinicalReport,
    hypo_alert: Optional[HypoAlert],
    meal_prediction: Optional[MealPrediction],
    settings_recs: Optional[List[SettingsRecommendation]],
    meal_history: Optional[MealHistory] = None,
) -> List[ActionRecommendation]:
    """Generate prioritized action recommendations.

    Combines all inference outputs into a ranked recommendation list.

    Priority:
      1 = Safety (hypo risk, urgent)
      2 = TIR improvement (settings, meal timing)
      3 = Informational (patterns, insights)

    Args:
        clinical: ClinicalReport from clinical_rules.
        hypo_alert: HypoAlert from hypo_predictor.
        meal_prediction: MealPrediction from meal_predictor.
        settings_recs: list of SettingsRecommendation from settings_advisor.
        meal_history: MealHistory for unannounced meal warnings.

    Returns:
        List of ActionRecommendation sorted by priority then confidence.
    """
    recs = []

    # ── Priority 1: Safety ────────────────────────────────────────
    if hypo_alert and hypo_alert.should_alert:
        lead = hypo_alert.lead_time_estimate
        recs.append(ActionRecommendation(
            action_type="hypo_alert",
            priority=1,
            description=(
                f"Hypoglycemia risk: {hypo_alert.probability*100:.0f}% probability "
                f"within {hypo_alert.horizon_minutes} minutes"
                + (f" (est. {lead:.0f} min)" if lead else "")
                + ". Consider reducing insulin or taking carbs."
            ),
            predicted_tir_delta=2.0,  # Avoiding a hypo improves TIR
            confidence=hypo_alert.confidence or 0.5,
            time_sensitive=True,
            deadline_minutes=lead,
        ))

    # ── Priority 2: Meal timing (eating_soon) ─────────────────────
    if meal_prediction and meal_prediction.recommend_eating_soon:
        recs.append(ActionRecommendation(
            action_type="eating_soon",
            priority=2,
            description=(
                f"Predicted {meal_prediction.predicted_window.value} in "
                f"~{meal_prediction.minutes_until:.0f} min "
                f"(~{meal_prediction.estimated_carbs_g:.0f}g). "
                f"Consider pre-bolus now for better post-meal control."
            ),
            predicted_tir_delta=3.0,  # Pre-bolus typically +3-5pp TIR
            confidence=meal_prediction.confidence,
            time_sensitive=True,
            deadline_minutes=meal_prediction.minutes_until,
            meal_prediction=meal_prediction,
        ))

    # ── Priority 2: Settings changes ──────────────────────────────
    if settings_recs:
        for sr in settings_recs:
            recs.append(ActionRecommendation(
                action_type=f"adjust_{sr.parameter.value}",
                priority=2,
                description=sr.rationale,
                predicted_tir_delta=sr.predicted_tir_delta,
                confidence=sr.confidence,
                time_sensitive=False,
                settings_rec=sr,
            ))

    # ── Priority 3: Unannounced meal warning ──────────────────────
    if meal_history and meal_history.unannounced_fraction > 0.30:
        recs.append(ActionRecommendation(
            action_type="unannounced_meal_warning",
            priority=3,
            description=(
                f"{meal_history.unannounced_fraction*100:.0f}% of detected meals "
                f"have no carb entry. Logging meals improves prediction accuracy "
                f"and enables better pre-bolus timing."
            ),
            predicted_tir_delta=2.0,
            confidence=0.8,
            time_sensitive=False,
        ))

    # ── Priority 3: Grade-based general advice ────────────────────
    if clinical.recommendations:
        # Only add the most actionable recommendation
        for rec_text in clinical.recommendations[:1]:
            if "Excellent" not in rec_text and "acceptable" not in rec_text:
                recs.append(ActionRecommendation(
                    action_type="clinical_insight",
                    priority=3,
                    description=rec_text,
                    predicted_tir_delta=1.0,
                    confidence=0.6,
                    time_sensitive=False,
                ))

    # Sort: priority first, then by predicted impact
    recs.sort(key=lambda r: (r.priority, -abs(r.predicted_tir_delta)))

    return recs
