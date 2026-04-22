"""audition_matrix.py — 4-factor audition recommendation engine.

Research basis: EXP-2843/2844/2845/2845b/2845c/2846/2847 + audition-matrix
synthesis doc (docs/60-research/audition-matrix-2026-04-22.md).

Charter: Stream B operational. Recommendations are profile-vs-actual
gaps; observed effective ISF is NOT biological ISF. The audition signal
is the DIRECTION + MAGNITUDE of the gap relative to scheduled.

Audition factors:
    1. Controller       (Loop / Trio / OpenAPS / AAPS)
    2. SMB capability   (per-patient configuration, crosses controllers)
    3. Phenotype        (down_shift / flat / up_shift)
    4. Time-of-day      (dawn 0-6 / midday 6-12 / afternoon 12-18 / night 18-24)

Decision rules (compiled from audition matrix):
  - flat + low recovery (median_recovery_fraction < 0.4):
      triple-flag triage candidate. Audit ISF + site-rotation history.
  - down_shifters: hardest cut at dawn (-15%). Suggest tighter dawn basal.
  - up_shifters: heaviest raise midday/evening (+11%). Suggest looser
    midday/evening basal.
  - Controller-route effect (Loop +basal, Trio -basal+SMB) means SAME
    envelope demand → different schedule edits per route.
  - Patient `b` archetype: Loop, flat, SMB-enabled, recovery=0,
    isf_gap_pct=-14%, post_high=30.9, wear_isf_drop=-31.5%.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .types import (
    ControllerType,
    PatientProfile,
    SettingsParameter,
    SettingsRecommendation,
    ConfidenceGrade,
)


PHENOTYPE_DOWN = "down_shift"
PHENOTYPE_FLAT = "flat"
PHENOTYPE_UP = "up_shift"

TOD_DAWN = (0.0, 6.0)
TOD_MIDDAY = (6.0, 12.0)
TOD_AFTERNOON = (12.0, 18.0)
TOD_NIGHT = (18.0, 24.0)


@dataclass
class AuditionInputs:
    """Per-patient inputs required by the audition matrix.

    All fields are observed metrics computed by upstream Stream B
    experiments (EXP-2812 recovery, EXP-2844 phenotype,
    EXP-2845c TOD shift, EXP-2846 SMB capability, EXP-2847 ISF gap).
    """

    controller: ControllerType
    smb_capable: bool
    phenotype: str                              # "down_shift" / "flat" / "up_shift"
    median_recovery_fraction: Optional[float]   # EXP-2812
    isf_gap_pct: Optional[float] = None         # EXP-2847; +ve = over-correct
    post_high_mg_dl: Optional[float] = None     # EXP-2843 envelope
    wear_isf_drop_pct: Optional[float] = None   # EXP-2812 site age
    simpson_paradox: Optional[bool] = None      # EXP-2853: sign(β_fast) ≠ sign(β_slow)
    simpson_stability_frac: Optional[float] = None  # EXP-2856: rolling-window agreement
    p_simpson: Optional[float] = None           # EXP-2859: bootstrap P(simpson)


@dataclass
class AuditionFlag:
    """A triage flag emitted by the audition matrix."""

    name: str
    severity: str          # "high" | "medium" | "low"
    rationale: str


def classify_triage_flags(inputs: AuditionInputs) -> List[AuditionFlag]:
    """Compute audition triage flags using the 4-factor matrix.

    Patient `b` (the archetype) hits all three high-severity flags:
    flat-low-recovery, ISF under-correction, site-degradation.
    """
    flags: List[AuditionFlag] = []

    if (
        inputs.phenotype == PHENOTYPE_FLAT
        and inputs.median_recovery_fraction is not None
        and inputs.median_recovery_fraction < 0.4
    ):
        flags.append(AuditionFlag(
            name="flat_low_recovery",
            severity="high",
            rationale=(
                "Flat phenotype with median recovery < 0.4 indicates "
                "envelope is being held by sustained controller intervention "
                "rather than schedule. Audition ISF + site rotation."
            ),
        ))

    if inputs.isf_gap_pct is not None and inputs.isf_gap_pct < -10:
        flags.append(AuditionFlag(
            name="isf_under_correction",
            severity="high",
            rationale=(
                f"Observed correction ISF {inputs.isf_gap_pct:+.0f}% vs "
                "scheduled — corrections under-deliver the predicted drop. "
                "Consider tightening scheduled ISF (smaller mg/dL/U)."
            ),
        ))
    elif inputs.isf_gap_pct is not None and inputs.isf_gap_pct > 30:
        flags.append(AuditionFlag(
            name="isf_over_correction",
            severity="medium",
            rationale=(
                f"Observed correction ISF {inputs.isf_gap_pct:+.0f}% vs "
                "scheduled — corrections over-deliver. Consider loosening "
                "scheduled ISF (larger mg/dL/U)."
            ),
        ))

    if (
        inputs.wear_isf_drop_pct is not None
        and inputs.wear_isf_drop_pct < -20
    ):
        flags.append(AuditionFlag(
            name="site_degradation",
            severity="high",
            rationale=(
                f"Effective ISF drops {inputs.wear_isf_drop_pct:.0f}% with "
                "cannula age. Investigate site-rotation discipline."
            ),
        ))

    if (
        inputs.post_high_mg_dl is not None
        and inputs.post_high_mg_dl > 25
    ):
        flags.append(AuditionFlag(
            name="post_high_envelope",
            severity="medium",
            rationale=(
                f"Post-high envelope {inputs.post_high_mg_dl:.0f} mg/dL above "
                "target — controller is sustaining high-end without recovery."
            ),
        ))

    # EXP-2854: prefer the direct EXP-2853 Simpson-paradox flag if available
    # (catches 9/29 patients across all phenotypes; phenotype proxy only
    # catches 2/9 of them). Fall back to phenotype proxy when not provided.
    # EXP-2856: severity depends on rolling-window stability — Simpson-positive
    # patients have only 25% median agreement across rolling 30d windows
    # (vs 87.5% for Simpson-negative), so a single-window Simpson=True without
    # stability evidence is LOW confidence.
    # EXP-2859: bootstrap P(simpson) takes precedence when available — gives
    # explicit confidence (only 2/26 patients are P>=0.9, 12/26 are P<=0.1
    # confidently clean, 12/26 are uncertain boundary).
    if inputs.p_simpson is not None:
        if inputs.p_simpson >= 0.9:
            flags.append(AuditionFlag(
                name="window_dependence_warning",
                severity="medium",
                rationale=(
                    f"EXP-2859 bootstrap P(simpson)={inputs.p_simpson:.0%} — "
                    "high-confidence Simpson regime. β_fast (5-min reactive) "
                    "and β_slow (48h structural) sign-mismatch is robust to "
                    "data resampling; conflicting timescale recommendations "
                    "are expected."
                ),
            ))
        elif inputs.p_simpson > 0.1:
            flags.append(AuditionFlag(
                name="window_dependence_warning",
                severity="low",
                rationale=(
                    f"EXP-2859 bootstrap P(simpson)={inputs.p_simpson:.0%} — "
                    "boundary case. Patient sits near the β_fast=0 / β_slow=0 "
                    "regime boundary; Simpson classification is uncertain. "
                    "Recommendations from one timescale MAY conflict with the "
                    "other — sanity-check before applying."
                ),
            ))
        # P<=0.1: confidently non-Simpson, suppress flag
    elif inputs.simpson_paradox is True:
        if (
            inputs.simpson_stability_frac is not None
            and inputs.simpson_stability_frac >= 0.75
        ):
            sev = "medium"
            stab_note = (
                f" Confirmed stable across rolling 30d windows "
                f"({inputs.simpson_stability_frac:.0%} agreement)."
            )
        else:
            sev = "low"
            stab_note = (
                " EXP-2856 flagged Simpson-positive patients have only ~25% "
                "rolling-window agreement; single-window flag is provisional."
            )
        flags.append(AuditionFlag(
            name="window_dependence_warning",
            severity=sev,
            rationale=(
                "EXP-2853 Simpson decomposition: β_fast (5-min reactive) and "
                "β_slow (48h structural) have opposite signs. Audition "
                "recommendations from one timescale will conflict with the "
                "other; use both views before changing settings."
                + stab_note
            ),
        ))
    elif inputs.simpson_paradox is None and inputs.phenotype == PHENOTYPE_UP:
        # Fallback: up_shift phenotype as a coarse proxy when Simpson flag
        # is not yet computed for this patient.
        flags.append(AuditionFlag(
            name="window_dependence_warning",
            severity="low",
            rationale=(
                "Up-shift phenotype proxy — multi-scale envelope coupling "
                "(EXP-2849) shows sign flip between fast (6-12h) and slow "
                "(24-48h) windows for ~50% of these patients. Recommendations "
                "from 48h structural-demand signal may conflict with reactive-"
                "loop behavior visible at 6h. Compute EXP-2853 Simpson flag "
                "for direct detection."
            ),
        ))

    return flags


def _basal_window_for_phenotype(phenotype: str) -> Tuple[float, float]:
    """Return (start_hour, end_hour) for the schedule window most likely
    to drive the phenotype shift (EXP-2845c)."""
    if phenotype == PHENOTYPE_DOWN:
        return TOD_DAWN              # down_shifters cut hardest at dawn
    if phenotype == PHENOTYPE_UP:
        return TOD_AFTERNOON         # up_shifters raise hardest midday/evening
    return (0.0, 24.0)               # flat: whole-day audit


def _route_aware_parameter(
    controller: ControllerType,
    smb_capable: bool,
) -> SettingsParameter:
    """Map controller + SMB capability to the schedule parameter most
    responsive to controller compensation (EXP-2845)."""
    # Loop/AAPS without SMB drive compensation through basal; SMB-capable
    # controllers (Trio uniformly, OpenAPS some, Loop some) route through
    # SMB and tolerate looser basal but tighter ISF/CR.
    if smb_capable:
        return SettingsParameter.ISF
    return SettingsParameter.BASAL_RATE


def generate_audition_recommendations(
    inputs: AuditionInputs,
    profile: Optional[PatientProfile] = None,
) -> List[SettingsRecommendation]:
    """Emit audition-matrix-driven SettingsRecommendation list.

    Returns recommendations consumable by the existing recommender.
    Confidence is moderate (0.55–0.7) — this is an audition signal, not
    a closed-form optimization. Magnitudes are bounded conservatively.
    """
    recs: List[SettingsRecommendation] = []
    flags = classify_triage_flags(inputs)
    flag_names = {f.name for f in flags}

    affected = _basal_window_for_phenotype(inputs.phenotype)

    if "isf_under_correction" in flag_names and inputs.isf_gap_pct is not None:
        magnitude = min(abs(inputs.isf_gap_pct), 20.0)
        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="decrease",          # tighter ISF (smaller mg/dL/U)
            magnitude_pct=magnitude,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=2.0,
            affected_hours=affected,
            confidence=0.65,
            evidence=(
                f"EXP-2847 correction-ISF audit: observed gap "
                f"{inputs.isf_gap_pct:+.0f}% (under-correction)."
            ),
            rationale=(
                "Corrections systematically under-deliver predicted drop. "
                "Tighten scheduled ISF (smaller mg/dL/U) to align with "
                "observed effective response. Stream B audition only."
            ),
            confidence_grade=ConfidenceGrade.B,
            ci_width_pct=46.0,
        ))

    if "isf_over_correction" in flag_names and inputs.isf_gap_pct is not None:
        magnitude = min(inputs.isf_gap_pct, 25.0)
        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase",
            magnitude_pct=magnitude,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=1.5,
            affected_hours=affected,
            confidence=0.6,
            evidence=(
                f"EXP-2847 correction-ISF audit: observed gap "
                f"{inputs.isf_gap_pct:+.0f}% (over-correction)."
            ),
            rationale=(
                "Corrections systematically over-deliver predicted drop. "
                "Loosen scheduled ISF (larger mg/dL/U)."
            ),
            confidence_grade=ConfidenceGrade.B,
            ci_width_pct=46.0,
        ))

    if inputs.phenotype == PHENOTYPE_DOWN:
        # down_shifters: profile basal too aggressive; recommend BASAL DECREASE
        # in dawn window unless route is SMB (then ISF instead).
        param = _route_aware_parameter(inputs.controller, inputs.smb_capable)
        recs.append(SettingsRecommendation(
            parameter=param,
            direction="decrease" if param == SettingsParameter.BASAL_RATE
                       else "increase",
            magnitude_pct=10.0,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=1.5,
            affected_hours=TOD_DAWN,
            confidence=0.6,
            evidence=(
                "EXP-2845c TOD analysis: down-shifters cut hardest at dawn "
                "(-15%). EXP-2845 controller-route: same envelope demand, "
                "different routes."
            ),
            rationale=(
                f"Controller {inputs.controller.value} consistently reduces "
                "delivery during dawn vs profile. Adjust schedule "
                f"({param.value}) to match observed demand pattern."
            ),
            confidence_grade=ConfidenceGrade.B,
            ci_width_pct=46.0,
        ))
    elif inputs.phenotype == PHENOTYPE_UP:
        param = _route_aware_parameter(inputs.controller, inputs.smb_capable)
        recs.append(SettingsRecommendation(
            parameter=param,
            direction="increase" if param == SettingsParameter.BASAL_RATE
                       else "decrease",
            magnitude_pct=10.0,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=1.5,
            affected_hours=TOD_AFTERNOON,
            confidence=0.6,
            evidence=(
                "EXP-2845c TOD analysis: up-shifters raise hardest midday/"
                "evening (+11%)."
            ),
            rationale=(
                f"Controller {inputs.controller.value} consistently increases "
                "delivery during midday/afternoon vs profile. Adjust schedule "
                f"({param.value}) to match observed demand pattern."
            ),
            confidence_grade=ConfidenceGrade.B,
            ci_width_pct=46.0,
        ))

    if "site_degradation" in flag_names:
        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="decrease",
            magnitude_pct=15.0,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=2.5,
            affected_hours=(0.0, 24.0),
            confidence=0.55,
            evidence=(
                f"EXP-2812 cannula-age audit: ISF drops "
                f"{inputs.wear_isf_drop_pct:.0f}% with site age."
            ),
            rationale=(
                "Effective insulin response degrades over cannula life. "
                "First-line action: tighten site-rotation discipline. "
                "Settings change is a fallback if rotation is already strict."
            ),
            confidence_grade=ConfidenceGrade.C,
            ci_width_pct=60.0,
        ))

    # Apply profile values + suggested_value if profile provided
    if profile is not None:
        recs = [_attach_profile_values(r, profile) for r in recs]

    return recs


def _attach_profile_values(
    rec: SettingsRecommendation,
    profile: PatientProfile,
) -> SettingsRecommendation:
    """Pull current values from the profile schedule and compute the
    suggested target value for the relevant time-of-day window."""
    schedule = {
        SettingsParameter.ISF: profile.isf_schedule,
        SettingsParameter.CR: profile.cr_schedule,
        SettingsParameter.BASAL_RATE: profile.basal_schedule,
    }.get(rec.parameter)
    if not schedule:
        return rec
    # Take the median value across schedule entries within the affected window
    start_h, end_h = rec.affected_hours
    relevant = []
    for entry in schedule:
        try:
            time_str = entry.get("time", "00:00")
            h = float(time_str.split(":")[0])
        except (ValueError, AttributeError):
            continue
        if start_h <= h < end_h:
            relevant.append(float(entry.get("value", 0.0)))
    if not relevant:
        relevant = [float(entry.get("value", 0.0)) for entry in schedule]
    if not relevant:
        return rec
    current = sum(relevant) / len(relevant)
    delta = rec.magnitude_pct / 100.0
    if rec.direction == "increase":
        suggested = current * (1 + delta)
    else:
        suggested = current * (1 - delta)
    rec.current_value = current
    rec.suggested_value = suggested
    return rec


__all__ = [
    "AuditionInputs",
    "AuditionFlag",
    "classify_triage_flags",
    "generate_audition_recommendations",
]
