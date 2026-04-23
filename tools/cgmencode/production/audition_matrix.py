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
    p_isf_under_correction: Optional[float] = None  # EXP-2861: bootstrap P(gap<-10%)
    p_isf_over_correction: Optional[float] = None   # EXP-2861: bootstrap P(gap>+30%)
    p_low_recovery: Optional[float] = None      # EXP-2862: bootstrap P(median recovery<0.4)
    p_site_degradation: Optional[float] = None  # EXP-2863: bootstrap P(aged-fresh ISF delta<-20%)
    p_post_high_envelope: Optional[float] = None  # EXP-2864: bootstrap P(envelope>25 mg/dL)
    p_basal_mismatch: Optional[float] = None      # EXP-2865: max bootstrap P(scheduled basal mult>0.5) across TOD
    basal_recommended_mult: Optional[float] = None  # EXP-2865: median recommended actual/scheduled multiplier (triage only, NOT a setting change)
    counter_reg_intercept: Optional[float] = None   # EXP-2875: residual mg/dL/min unexplained by IOB+basal in rescue-free hypo recovery; <0.5 = impaired, >=2.0 = strongly preserved
    # --- EXP-2882/2884/2885/2886/2889 phenotype axes ---
    # Kept as THREE orthogonal axes per EXP-2888: composite scores lose
    # information. See docs/60-research/deconfounding-toolkit-2026-04-22.md.
    stack_score: Optional[float] = None             # EXP-2882: fraction of evenings with bolus-stacking (IOB+bolus4h > 75th pct)
    braking_ratio: Optional[float] = None           # EXP-2885: mean actual_basal / sched_basal during pre-nadir descents; low = strong brake
    counterfactual_severe: Optional[float] = None   # EXP-2889: per-patient fraction of descents that would reach <54 mg/dL without AID suspension (ISF=50)
    aid_protection_severe: Optional[float] = None   # EXP-2889: counterfactual_severe - observed_severe (how much the AID buffers this patient)
    algorithm_lineage: Optional[str] = None         # "Loop (iOS)" | "oref1 (modern)" | "oref0 (legacy)" — controller family, not brand
    phenotype_archetype: Optional[str] = None       # EXP-2886: one of {well_defended, algorithm_dependent, exposed_stacker, hidden_leverage, lax_braking, stacker_balanced, stacker_weak_defense}
    night_severe_excess: Optional[float] = None     # EXP-2895: nighttime severe-rate - daytime severe-rate (per-patient or per-cell)
    protection_z_within_lineage: Optional[float] = None  # EXP-2900: z-score of aid_protection_severe vs lineage (or cell) median
    regime_label: Optional[str] = None  # EXP-2902: {mechanism_gap, load_saturation, moderate, defended, over_performer_at_load}


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

    if inputs.phenotype == PHENOTYPE_FLAT and inputs.p_low_recovery is not None:
        if inputs.p_low_recovery >= 0.9:
            flags.append(AuditionFlag(
                name="flat_low_recovery",
                severity="high",
                rationale=(
                    f"Flat phenotype + bootstrap P(recovery<0.4)="
                    f"{inputs.p_low_recovery:.2f} (EXP-2862). Envelope is "
                    "held by sustained controller intervention rather than "
                    "schedule. Audition ISF + site rotation."
                ),
            ))
        elif inputs.p_low_recovery >= 0.1:
            flags.append(AuditionFlag(
                name="flat_low_recovery",
                severity="low",
                rationale=(
                    f"Flat phenotype + bootstrap P(recovery<0.4)="
                    f"{inputs.p_low_recovery:.2f} (EXP-2862) — boundary; "
                    "transition count or noise leaves classification "
                    "uncertain. Provisional flag."
                ),
            ))
        # else: confidently above 0.4 → suppress
    elif (
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

    if inputs.p_isf_under_correction is not None or inputs.p_isf_over_correction is not None:
        p_under = inputs.p_isf_under_correction or 0.0
        p_over = inputs.p_isf_over_correction or 0.0
        if p_under >= 0.9:
            flags.append(AuditionFlag(
                name="isf_under_correction",
                severity="high",
                rationale=(
                    f"Bootstrap P(under-correction)={p_under:.2f} (EXP-2861). "
                    "Corrections under-deliver predicted drop with high confidence. "
                    "Consider tightening scheduled ISF (smaller mg/dL/U)."
                ),
            ))
        elif p_over >= 0.9:
            flags.append(AuditionFlag(
                name="isf_over_correction",
                severity="medium",
                rationale=(
                    f"Bootstrap P(over-correction)={p_over:.2f} (EXP-2861). "
                    "Corrections over-deliver with high confidence. "
                    "Consider loosening scheduled ISF (larger mg/dL/U)."
                ),
            ))
        elif max(p_under, p_over) >= 0.1:
            direction = "under" if p_under > p_over else "over"
            p = max(p_under, p_over)
            flags.append(AuditionFlag(
                name=f"isf_{direction}_correction",
                severity="low",
                rationale=(
                    f"Bootstrap P({direction}-correction)={p:.2f} (EXP-2861) — "
                    "boundary; per-event noise leaves classification uncertain. "
                    "Provisional flag pending more correction events."
                ),
            ))
        # else: confidently within band (suppress)
    elif inputs.isf_gap_pct is not None and inputs.isf_gap_pct < -10:
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

    if inputs.p_site_degradation is not None:
        if inputs.p_site_degradation >= 0.9:
            flags.append(AuditionFlag(
                name="site_degradation",
                severity="high",
                rationale=(
                    f"Bootstrap P(site-degradation)={inputs.p_site_degradation:.2f} "
                    "(EXP-2863). Effective ISF drops with cannula age with high "
                    "confidence. Investigate site-rotation discipline."
                ),
            ))
        elif inputs.p_site_degradation >= 0.1:
            flags.append(AuditionFlag(
                name="site_degradation",
                severity="low",
                rationale=(
                    f"Bootstrap P(site-degradation)={inputs.p_site_degradation:.2f} "
                    "(EXP-2863) — boundary. Per-event ISF noise leaves the wear "
                    "signal indistinguishable from sampling variance "
                    "(typical CI width >100pp). Provisional flag."
                ),
            ))
        # else: confidently no degradation → suppress
    elif (
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

    if inputs.p_post_high_envelope is not None:
        if inputs.p_post_high_envelope >= 0.9:
            flags.append(AuditionFlag(
                name="post_high_envelope",
                severity="medium",
                rationale=(
                    f"Bootstrap P(envelope>25 mg/dL)={inputs.p_post_high_envelope:.2f} "
                    "(EXP-2864). Controller sustains high-end without recovery "
                    "with high confidence."
                ),
            ))
        elif inputs.p_post_high_envelope >= 0.1:
            flags.append(AuditionFlag(
                name="post_high_envelope",
                severity="low",
                rationale=(
                    f"Bootstrap P(envelope>25 mg/dL)={inputs.p_post_high_envelope:.2f} "
                    "(EXP-2864) — boundary; provisional flag."
                ),
            ))
        # else: confidently in target → suppress
    elif (
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

    if inputs.p_basal_mismatch is not None:
        mult_str = (
            f"; median observed/scheduled mult={inputs.basal_recommended_mult:.2f}"
            if inputs.basal_recommended_mult is not None
            else ""
        )
        # EXP-2871/2872/2873: Loop and Trio differ on suspension polarity.
        # Loop suspends in normal/low envelopes (hypo-prevention bias);
        # Trio suspends in elevated envelopes (SMB substitution). The same
        # basal_mismatch signal therefore means different things per
        # controller. Do NOT vary thresholds (no validated cohort yet);
        # vary the rationale guidance.
        ctl = getattr(inputs.controller, "value", inputs.controller)
        if ctl == ControllerType.LOOP.value:
            ctl_hint = (
                " Controller=Loop: suspension is hypo-prevention biased "
                "(EXP-2871); the gap most likely reflects the schedule "
                "being too aggressive for fasting equilibrium. Soften "
                "schedule first; ISF often follows."
            )
        elif ctl in (ControllerType.TRIO.value, ControllerType.AAPS.value,
                     ControllerType.OPENAPS.value):
            ctl_hint = (
                f" Controller={ctl}: SMB-driven controllers substitute "
                "basal with corrections (EXP-2871); the gap may reflect "
                "ISF stacking driving basal suspension rather than a true "
                "schedule excess. Audit ISF and SMB cap before lowering "
                "basal."
            )
        else:
            ctl_hint = ""

        if inputs.p_basal_mismatch >= 0.9:
            flags.append(AuditionFlag(
                name="basal_mismatch",
                severity="high",
                rationale=(
                    f"Bootstrap P(scheduled basal >> actual)={inputs.p_basal_mismatch:.2f} "
                    f"in fasting equilibrium (EXP-2865){mult_str}. "
                    "TRIAGE ONLY — the gap IS the EGP safety margin "
                    "(per EXP-2738); do NOT lower basal by the multiplier. "
                    f"Audit basal schedule + EGP exposure.{ctl_hint}"
                ),
            ))
        elif inputs.p_basal_mismatch >= 0.1:
            flags.append(AuditionFlag(
                name="basal_mismatch",
                severity="low",
                rationale=(
                    f"Bootstrap P(scheduled basal >> actual)={inputs.p_basal_mismatch:.2f} "
                    f"(EXP-2865){mult_str} — boundary; provisional flag.{ctl_hint}"
                ),
            ))
        # else: confidently aligned → suppress

    # EXP-2875: counter-regulation residual. Patients with intercept
    # <0.5 mg/dL/min in rescue-free hypo recovery have impaired glucagon
    # response — aggressive hypo prevention (early basal suspension,
    # rescue-carb prompts) is warranted because they cannot self-rescue.
    # Patients with intercept >=2.0 have strongly preserved counter-reg;
    # routine hypo handling is safer and over-suspending may cause
    # rebound hyperglycemia.
    if inputs.counter_reg_intercept is not None:
        cr = inputs.counter_reg_intercept
        if cr < 0.5:
            flags.append(AuditionFlag(
                name="impaired_counter_regulation",
                severity="high",
                rationale=(
                    f"Counter-reg residual intercept = {cr:.2f} mg/dL/min "
                    "in rescue-free hypo recovery (EXP-2875). Below the "
                    "+0.5 impaired-response threshold. Patient has "
                    "limited self-rescue capacity; emphasize early hypo "
                    "prevention, rescue-carb protocols, and avoid "
                    "aggressive ISF settings."
                ),
            ))
        elif cr >= 2.0:
            flags.append(AuditionFlag(
                name="preserved_counter_regulation",
                severity="low",
                rationale=(
                    f"Counter-reg residual intercept = {cr:.2f} mg/dL/min "
                    "(EXP-2875) — strongly preserved glucagon response. "
                    "Hypo events self-resolve faster than IOB decay alone "
                    "predicts; monitor for rebound hyperglycemia after "
                    "hypo. Aggressive basal suspension may not be needed."
                ),
            ))
        # else: 0.5 ≤ cr < 2.0 = typical preserved range, no flag

        # EXP-2898/2901: rebound_overshoot_algorithm_gap
        # High intercept (>=3.0) + low protection (<0.30) is the lagging-
        # indicator pattern: rapid recovery exists ONLY because the patient
        # is reaching severe hypo often. The fast bounce-back is a symptom
        # of upstream AID failure, not resilience.
        if (
            cr >= 3.0
            and inputs.aid_protection_severe is not None
            and inputs.aid_protection_severe < 0.30
        ):
            flags.append(AuditionFlag(
                name="rebound_overshoot_algorithm_gap",
                severity="high",
                rationale=(
                    f"EXP-2898: counter-reg intercept = {cr:.2f} mg/dL/min "
                    "is unusually high AND aid_protection_severe = "
                    f"{inputs.aid_protection_severe:.2f} is below 0.30. "
                    "Rapid recovery is a LAGGING indicator here — the "
                    "patient reaches severe hypo often enough that fast "
                    "rebound is observable. The algorithm is failing to "
                    "PREVENT the events, not the body's failure to "
                    "recover. Treat as algorithm/settings gap, not as "
                    "preserved counter-regulation."
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
    # ------------------------------------------------------------------
    # EXP-2889 AID-safety-dependence flags
    # ------------------------------------------------------------------
    # Patients whose counterfactual (AID-off) severe-hypo rate is high
    # and whose braking_ratio is low are relying on the controller for
    # safety. This is distinct from the other flags because it describes
    # COUNTERFACTUAL risk, not observed outcomes (which the AID has
    # already protected). See EXP-2889 for the construct validation
    # (rho=-0.71, p=0.001 vs counterfactual_severe).
    if (
        inputs.braking_ratio is not None
        and inputs.counterfactual_severe is not None
    ):
        if (
            inputs.braking_ratio <= 0.10
            and inputs.counterfactual_severe >= 0.95
        ):
            flags.append(AuditionFlag(
                name="aid_safety_dependence_high",
                severity="high",
                rationale=(
                    "EXP-2889 counterfactual replay: "
                    f"braking_ratio={inputs.braking_ratio:.2f} (strong "
                    "AID suspension) and "
                    f"counterfactual_severe={inputs.counterfactual_severe:.0%} "
                    "(≈all descents would reach <54 mg/dL without AID "
                    "intervention). Settings-under-AID do not constitute "
                    "safe settings-without-AID. Review standalone-pump "
                    "fallback plan, sensor-dropout behaviour, and whether "
                    "basal/ISF/CR are genuinely tuned or are compensating "
                    "for controller aggressiveness."
                ),
            ))
        elif (
            inputs.braking_ratio is not None
            and inputs.braking_ratio >= 0.40
            and inputs.aid_protection_severe is not None
            and inputs.aid_protection_severe <= 0.15
        ):
            flags.append(AuditionFlag(
                name="lax_braking_controller_efficacy",
                severity="medium",
                rationale=(
                    "EXP-2889: the AID is delivering "
                    f"{inputs.braking_ratio:.0%} of scheduled basal during "
                    "descents (weak braking) AND protection magnitude is "
                    f"only {inputs.aid_protection_severe:.0%}. Either "
                    "settings are so conservative the AID has nothing to "
                    "do, or controller tuning/thresholds are insufficiently "
                    "aggressive. Compare TDD vs profile basal to distinguish."
                ),
            ))

    # Stacker flag — EXP-2882
    if inputs.stack_score is not None and inputs.stack_score >= 0.75:
        flags.append(AuditionFlag(
            name="evening_stacker",
            severity="medium",
            rationale=(
                f"EXP-2882 stack_score={inputs.stack_score:.0%} — "
                "dinner-to-bed window repeatedly shows elevated IOB+recent "
                "bolus, suggesting bolus-stacking. Audit dinner bolus "
                "timing, carb accounting, and whether evening ISF/CR are "
                "calibrated for larger / later meals."
            ),
        ))

    # SMB-absent algorithm-gap flag — EXP-2893/2894
    # Distinct from lax_braking: this fires when basal-cut is OK but
    # the SMB/auto-bolus channel is missing entirely. Hyper-correction
    # is then user-driven only, eroding TIR even if hypo protection is
    # adequate.
    if (
        inputs.smb_capable is False
        and inputs.aid_protection_severe is not None
        and inputs.aid_protection_severe >= 0.40
    ):
        # Adequate hypo protection (>=40 pp) confirms basal-cut is
        # working; SMB-absence is then the limiting factor for hyper.
        flags.append(AuditionFlag(
            name="smb_absent_algorithm_gap",
            severity="medium",
            rationale=(
                "EXP-2893/2894: SMB / automatic-bolus channel is absent "
                f"(smb_capable=False) while hypo protection is "
                f"{inputs.aid_protection_severe:.0%}. The algorithm "
                "cannot auto-correct hyper events; users must bolus "
                "manually. For Loop users this may indicate the "
                "automatic-bolus toggle is off (opt-in feature). For "
                "oref0 legacy users this is an absent code path — "
                "migration to oref1-family or Loop ≥3.x with auto-bolus "
                "enabled would close the gap."
            ),
        ))

    # Night-protection-degraded flag — EXP-2895
    # Lineage-conditional thresholds: oref0 patients are doubly exposed
    # (settings AND TOD), oref1 mildly. Loop is TOD-invariant — no flag.
    if inputs.night_severe_excess is not None:
        lin = inputs.algorithm_lineage
        threshold = None
        severity = None
        if lin == "oref0 (legacy)" and inputs.night_severe_excess >= 0.15:
            threshold, severity = 0.15, "high"
        elif lin == "oref1 (modern)" and inputs.night_severe_excess >= 0.10:
            threshold, severity = 0.10, "medium"
        # Loop intentionally excluded — EXP-2895 shows TOD-invariance
        if threshold is not None:
            flags.append(AuditionFlag(
                name="night_protection_degraded",
                severity=severity,
                rationale=(
                    f"EXP-2895: nighttime severe-hypo rate exceeds "
                    f"daytime by {inputs.night_severe_excess:.0%} "
                    f"(threshold {threshold:.0%} for {lin}). The "
                    "controller's overnight protection is materially "
                    "weaker than daytime. Audit overnight basal "
                    "scheduling, sensor reliability during sleep, and "
                    "whether the dawn-phenomenon adjustment is "
                    "active. For oref0 patients consider migration to "
                    "an oref1-family controller (TOD degradation is "
                    "smaller in oref1)."
                ),
            ))

    # Per-patient protection deviation — EXP-2900
    # Identifies individuals whose protection is materially below or above
    # their lineage/cell median. Under-performers get tuning headroom
    # signal; over-performers are tagged for replicable-pattern audit.
    if inputs.protection_z_within_lineage is not None:
        z = inputs.protection_z_within_lineage
        if z <= -1.0:
            flags.append(AuditionFlag(
                name="under_performer_for_lineage",
                severity="medium",
                rationale=(
                    f"EXP-2900: aid_protection_severe is {-z:.1f} SD "
                    "below the lineage/cell comparator median. "
                    "Material individual headroom beyond what the "
                    "lineage-tercile baseline suggests. Ordered "
                    "remediation: (1) counter-regulation channel "
                    "(EXP-2898 intercept), (2) site-degradation "
                    "(EXP-2842 recovery=0 + ISF drop), (3) within-"
                    "tercile setting re-tune, (4) mechanism upgrade "
                    "(basal-cut / SMB enablement)."
                ),
            ))
        elif z >= 1.0:
            flags.append(AuditionFlag(
                name="over_performer_for_lineage",
                severity="low",
                rationale=(
                    f"EXP-2900: aid_protection_severe is {z:.1f} SD "
                    "above the lineage/cell comparator median. "
                    "Capture the patient's settings fingerprint as a "
                    "candidate template for same-cell peers; useful "
                    "as a replicable best-practice reference."
                ),
            ))

    # EXP-2902 regime label (cohort stratification in protection x cf space)
    if inputs.regime_label is not None:
        if inputs.regime_label == "load_saturation":
            flags.append(AuditionFlag(
                name="regime_load_saturation",
                severity="medium",
                rationale=(
                    "EXP-2902: cf_severe >= 0.95 — every descent reaches "
                    "the hypo precipice without AID intervention. "
                    "Settings/behaviour drive cf to ceiling; mechanism "
                    "channels may all pass yet observed severe-rate stays "
                    "high. Settings de-aggression (CR or basal pullback "
                    "~10%) has higher leverage than algorithm migration "
                    "or mechanism upgrade."
                ),
            ))
        elif inputs.regime_label == "mechanism_gap":
            flags.append(AuditionFlag(
                name="regime_mechanism_gap",
                severity="high",
                rationale=(
                    "EXP-2902: aid_protection_severe < 0.35 with "
                    "non-saturated cf — algorithm/mechanism deficit. "
                    "Audit basal-cut utilization (EXP-2892), SMB "
                    "presence (EXP-2893), and consider algorithm "
                    "migration. Settings tuning alone is unlikely to "
                    "close the gap."
                ),
            ))

    if inputs.simpson_paradox is None and inputs.phenotype == PHENOTYPE_UP:
        # Fallback: up_shift phenotype as a coarse proxy when Simpson flag
        # is not yet computed for this patient. Suppressed if EXP-2859
        # bootstrap has already classified the patient (p_simpson set).
        if inputs.p_simpson is not None:
            pass
        else:
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
