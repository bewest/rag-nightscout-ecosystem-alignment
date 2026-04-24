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
    ActionRecommendation, ClinicalReport, HypoAlert, HypoPhenotype,
    MealHistory, MealPrediction, MetabolicState,
    PatientProfile, PipelineResult, SettingsRecommendation,
    ControllerType, ControllerBehavior,
)
from .audition_matrix import (
    AuditionInputs, classify_triage_flags,
    generate_audition_recommendations,
)


def generate_recommendations(
    clinical: ClinicalReport,
    hypo_alert: Optional[HypoAlert],
    meal_prediction: Optional[MealPrediction],
    settings_recs: Optional[List[SettingsRecommendation]],
    meal_history: Optional[MealHistory] = None,
    prediction_bias_mgdl: Optional[float] = None,
    audition_inputs: Optional[AuditionInputs] = None,
    profile: Optional[PatientProfile] = None,
    overnight_assessment: Optional[object] = None,
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
        prediction_bias_mgdl: systematic prediction bias (EXP-2331).
        audition_inputs: optional 4-factor audition matrix inputs
            (EXP-2843..2847). When provided, the audition module is
            consulted and its recommendations + triage flags are merged.
        profile: optional PatientProfile used to attach current/suggested
            values to audition recommendations.

    Returns:
        List of ActionRecommendation sorted by priority then confidence.
    """
    recs = []

    # ── Priority 1: Safety ────────────────────────────────────────
    if hypo_alert and hypo_alert.should_alert:
        lead = hypo_alert.lead_time_estimate
        phenotype = hypo_alert.hypo_phenotype

        # Phenotype-specific guidance (EXP-2281)
        if phenotype == HypoPhenotype.OVER_CORRECTION:
            phenotype_advice = " Over-correction pattern detected — consider reducing correction dose or extending pre-bolus timing."
        elif phenotype == HypoPhenotype.CHRONIC_LOW:
            phenotype_advice = " Chronic-low pattern detected — consider reducing basal rate or raising target."
        else:
            phenotype_advice = ""

        recs.append(ActionRecommendation(
            action_type="hypo_alert",
            priority=1,
            description=(
                f"Hypoglycemia risk: {hypo_alert.probability*100:.0f}% probability "
                f"within {hypo_alert.horizon_minutes} minutes"
                + (f" (est. {lead:.0f} min)" if lead else "")
                + ". Consider reducing insulin or taking carbs."
                + phenotype_advice
            ),
            predicted_tir_delta=2.0,
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
        settings_recs = _apply_conflict_resolution(
            settings_recs, overnight_assessment)
        for sr in settings_recs:
            # Demote conflicting basal recommendations to priority 3
            # so they still surface but do not dominate. The advisor
            # may have flagged it via a `_conflict_warning` attribute.
            conflict_note = getattr(sr, "_conflict_warning", "")
            prio = 3 if conflict_note else 2
            desc = sr.rationale + (f"  ⚠️ {conflict_note}" if conflict_note else "")
            recs.append(ActionRecommendation(
                action_type=f"adjust_{sr.parameter.value}",
                priority=prio,
                description=desc,
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

    # ── Priority 3: Prediction bias awareness (EXP-2331) ─────────
    # WARN about systematic prediction bias but do NOT correct it.
    # Naive bias correction is DANGEROUS for 8/10 patients: removing
    # the negative bias removes the loop's defensive suspension,
    # which prevents real hypos. Report the bias as informational only.
    if prediction_bias_mgdl is not None and abs(prediction_bias_mgdl) > 1.0:
        direction = "under-predicting" if prediction_bias_mgdl < 0 else "over-predicting"
        recs.append(ActionRecommendation(
            action_type="prediction_bias_info",
            priority=3,
            description=(
                f"Systematic prediction bias detected: {direction} by "
                f"{abs(prediction_bias_mgdl):.1f} mg/dL at 30 min. "
                f"This drives defensive loop behavior. "
                f"⚠ Do NOT correct — bias removal increases hypo risk "
                f"for most patients (EXP-2331)."
            ),
            predicted_tir_delta=0.0,  # Explicitly zero — do not correct
            confidence=0.9,
            time_sensitive=False,
        ))

    # ── Priority 2: Audition matrix (EXP-2843..2847) ──────────────
    # Stream B operational layer. Profile-vs-actual gap recommendations
    # derived from 4-factor classification (controller × SMB cap ×
    # phenotype × time-of-day). Triage flags surface as priority 2
    # informational entries when severity is "high".
    if audition_inputs is not None:
        flags = classify_triage_flags(audition_inputs)
        for flag in flags:
            if flag.severity != "high":
                continue
            recs.append(ActionRecommendation(
                action_type=f"audition_flag_{flag.name}",
                priority=2,
                description=f"Audition triage [{flag.severity}]: {flag.rationale}",
                predicted_tir_delta=1.0,
                confidence=0.6,
                time_sensitive=False,
            ))
        for sr in generate_audition_recommendations(audition_inputs, profile):
            recs.append(ActionRecommendation(
                action_type=f"audition_{sr.parameter.value}",
                priority=2,
                description=sr.rationale,
                predicted_tir_delta=sr.predicted_tir_delta,
                confidence=sr.confidence,
                time_sensitive=False,
                settings_rec=sr,
            ))

    # Sort: priority first, then by predicted impact
    recs.sort(key=lambda r: (r.priority, -abs(r.predicted_tir_delta)))

    return recs


# ── Conflict resolution & sample-size guards ─────────────────────────

def _apply_conflict_resolution(
    settings_recs: List[SettingsRecommendation],
    overnight_assessment: Optional[object],
) -> List[SettingsRecommendation]:
    """Annotate settings recommendations that conflict with other
    pipeline outputs so the recommender can demote them.

    Currently flags overnight basal recommendations whose direction
    disagrees with the overnight-assessment model
    (`suggested_basal_change_pct`). The overnight assessment is
    alcohol-/EGP-suppression aware (it reads the deep-fasting drift
    and Loop-suspension fraction); when it points in the opposite
    direction, the basal advisor is almost certainly chasing a
    symptom rather than a true basal deficit (GAP-RECO-001).

    Sets `_conflict_warning` (str) attribute on each affected rec.
    Mutates the SettingsRecommendation list in-place but also returns
    it for chaining.
    """
    if not settings_recs or overnight_assessment is None:
        return settings_recs

    overnight_pct = getattr(
        overnight_assessment, "suggested_basal_change_pct", None)
    overnight_conf = getattr(
        overnight_assessment, "confidence", 0.0) or 0.0

    if overnight_pct is None:
        return settings_recs

    for sr in settings_recs:
        param = getattr(sr.parameter, "value", str(sr.parameter))
        if param not in ("basal_rate", "basal"):
            continue
        # Determine if affected hours overlap the overnight window.
        affected = getattr(sr, "affected_hours", None)
        is_overnight = (
            affected is not None
            and len(affected) >= 2
            and float(affected[0]) < 6.0
        )
        if not is_overnight:
            continue
        # Sign disagreement: rec increases while overnight model says
        # decrease (or vice versa).
        rec_signed_pct = (
            getattr(sr, "magnitude_pct", 0.0) or 0.0
        ) * (1.0 if sr.direction == "increase" else -1.0)
        if rec_signed_pct == 0.0 or overnight_pct == 0.0:
            continue
        if (rec_signed_pct > 0) != (overnight_pct > 0):
            sr._conflict_warning = (
                f"Conflicts with overnight assessment "
                f"(suggested {overnight_pct:+.1f}% basal change, "
                f"confidence {overnight_conf:.2f}). Possible "
                f"alcohol- or EGP-suppression overnight pattern; "
                f"do not act on this without clinician review."
            )
    return settings_recs


# ── Controller-Specific Behavior (EXP-2081) ──────────────────────────

# EXP-2081: 19 patients, 4 controllers. Each controller has a distinct
# compensation style that affects how much we can trust observed metrics.
#
# Loop/Trio: aggressive suspension (38-96% zero delivery), COMPENSATING/PASSIVE
#   → Observed ISF and metabolic data heavily influenced by loop suspension
#   → Settings errors are MASKED — patient may be fine even with wrong ISF
#   → Recommendation confidence should be LOWER
#
# AAPS: moderate suspension, BALANCED
#   → Better settings visibility, reasonable trust in observed data
#
# OpenAPS: SMB + high temp basal, AGGRESSIVE/most settings-transparent
#   → Best settings visibility, highest recommendation confidence

_CONTROLLER_PROFILES = {
    ControllerType.LOOP: ControllerBehavior(
        controller=ControllerType.LOOP,
        compensation_style="compensating",
        suspension_pct=0.55,          # 38-76% zero delivery (median ~55%)
        settings_visibility=0.3,
        isf_trust=0.3,
        cr_trust=0.4,
        recommendation_notes=(
            "Loop uses aggressive temp basal suspension to prevent lows. "
            "This masks ISF errors: observed effective ISF may be 1.5-2.2× "
            "higher than profile due to loop compensation. Settings changes "
            "may show <1% TIR impact because Loop re-compensates. "
            "Focus recommendations on CR and pre-bolus timing."
        ),
    ),
    ControllerType.TRIO: ControllerBehavior(
        controller=ControllerType.TRIO,
        compensation_style="passive",
        suspension_pct=0.45,
        settings_visibility=0.35,
        isf_trust=0.35,
        cr_trust=0.45,
        recommendation_notes=(
            "Trio (oref1 on iOS) also compensates via temp basal but uses "
            "SMB for upward corrections. Settings visibility is slightly "
            "better than Loop. ISF changes may have more visible effect "
            "due to SMB dosing, but basal changes remain largely masked."
        ),
    ),
    ControllerType.AAPS: ControllerBehavior(
        controller=ControllerType.AAPS,
        compensation_style="balanced",
        suspension_pct=0.30,
        settings_visibility=0.6,
        isf_trust=0.6,
        cr_trust=0.6,
        recommendation_notes=(
            "AAPS provides balanced automation with moderate temp basal "
            "and optional SMB. Settings are more visible than Loop/Trio. "
            "ISF and CR recommendations have moderate confidence. "
            "DynISF feature may already be auto-adjusting ISF."
        ),
    ),
    ControllerType.OPENAPS: ControllerBehavior(
        controller=ControllerType.OPENAPS,
        compensation_style="aggressive",
        suspension_pct=0.20,
        settings_visibility=0.7,
        isf_trust=0.7,
        cr_trust=0.65,
        recommendation_notes=(
            "OpenAPS (oref0/oref1 on rigs) is the most settings-transparent "
            "controller. Autosens provides real-time ISF scaling. "
            "Observed metrics closely reflect actual settings accuracy. "
            "Recommendations have highest confidence of all controllers."
        ),
    ),
    ControllerType.UNKNOWN: ControllerBehavior(
        controller=ControllerType.UNKNOWN,
        compensation_style="unknown",
        suspension_pct=0.0,
        settings_visibility=0.5,
        isf_trust=0.5,
        cr_trust=0.5,
        recommendation_notes=(
            "Controller not identified. Using conservative defaults. "
            "Settings recommendations have moderate confidence."
        ),
    ),
}


def detect_controller_type(patient: 'PatientData') -> ControllerType:
    """Detect AID controller from patient metadata or data patterns.

    Detection heuristics (in priority order):
    1. Explicit metadata field (patient.metadata['controller'])
    2. DeviceStatus structure patterns
    3. Basal delivery patterns (suspension fraction)

    Args:
        patient: PatientData with optional metadata.

    Returns:
        ControllerType enum.
    """
    # Check explicit metadata
    meta = getattr(patient, 'metadata', {}) or {}
    controller_str = meta.get('controller', meta.get('pump', '')).lower()

    if 'loop' in controller_str and 'open' not in controller_str:
        return ControllerType.LOOP
    if 'trio' in controller_str:
        return ControllerType.TRIO
    if 'aaps' in controller_str or 'androidaps' in controller_str:
        return ControllerType.AAPS
    if 'openaps' in controller_str or 'oref' in controller_str:
        return ControllerType.OPENAPS

    # Heuristic: suspension fraction + SMB cadence
    # AAPS/oref1 emit small (<0.3 U) automated SMBs at high cadence.
    # Loop autobolus-OFF has user-driven boluses only — sparser, larger.
    # This separates the two even when both show ~25-50% basal suspension.
    has_smb_cadence = False
    if patient.bolus is not None:
        bolus = patient.bolus
        valid_bolus = bolus[np.isfinite(bolus) & (bolus > 0)]
        if len(valid_bolus) >= 50:
            small_frac = float(np.mean(valid_bolus < 0.3))
            # AAPS/oref1 small-bolus fraction is typically >0.5;
            # Loop user-bolus fraction is typically <0.2.
            has_smb_cadence = small_frac > 0.4

    if patient.basal_rate is not None:
        basal = patient.basal_rate
        valid = basal[np.isfinite(basal)]
        if len(valid) > 288:
            suspension_frac = float(np.mean(valid == 0))
            if suspension_frac > 0.60:
                return ControllerType.LOOP  # Very high suspension → Loop
            elif suspension_frac > 0.40:
                # Could be Loop autobolus-OFF (high suspension, no SMB
                # cadence) or Trio (high suspension WITH SMB cadence).
                return ControllerType.TRIO if has_smb_cadence else ControllerType.LOOP
            elif suspension_frac > 0.15:
                # Could be AAPS (moderate suspension WITH SMB cadence)
                # or a low-activity Loop autobolus-OFF deployment.
                return ControllerType.AAPS if has_smb_cadence else ControllerType.LOOP

    return ControllerType.UNKNOWN


def get_controller_behavior(controller: ControllerType) -> ControllerBehavior:
    """Get the behavior profile for a controller type."""
    return _CONTROLLER_PROFILES.get(controller, _CONTROLLER_PROFILES[ControllerType.UNKNOWN])


def adjust_confidence_for_controller(
    recs: list[SettingsRecommendation],
    controller: ControllerType,
) -> list[SettingsRecommendation]:
    """Adjust recommendation confidence based on controller behavior.

    Research (EXP-2081): Loop masks ISF errors so effectively that
    changing ISF produces <1% TIR impact. AAPS/OpenAPS are more
    settings-transparent.

    This does NOT modify the recommendations — it adjusts confidence
    scores to reflect how much we trust the observed data.

    Args:
        recs: list of SettingsRecommendation.
        controller: detected controller type.

    Returns:
        Same list with adjusted confidence scores.
    """
    behavior = get_controller_behavior(controller)

    for rec in recs:
        if rec.parameter.value in ('isf', 'ISF'):
            rec.confidence *= behavior.isf_trust
        elif rec.parameter.value in ('cr', 'CR'):
            rec.confidence *= behavior.cr_trust
        else:
            rec.confidence *= behavior.settings_visibility

        # Add controller note to evidence
        if behavior.recommendation_notes and controller != ControllerType.UNKNOWN:
            rec.evidence += f" [Controller: {controller.value}]"

    return recs
