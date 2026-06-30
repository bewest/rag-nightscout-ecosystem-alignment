"""clinical_decision_report.py — Clinical-grade decision support report.

Transforms raw advisory output (``SettingsRecommendation`` list plus a
glycemic summary) into a structured, clinically documentable report that
is comparable across AID systems and multiple-daily-injection (MDI)
therapy, and suitable for engagement / reimbursement justification.

The report mirrors the basal/bolus mental model so it degrades gracefully
even for MDI:

  0. Overall insulin sufficiency — hypo/hyper risk, main risks, what's
     working.
  1. Basal sufficiency — change / no-change with optional time block;
     practical recommendation in-body, theoretical optimum in addenda.
  2. ISF adequacy — same treatment.
  3. Carb ratio (CR) adequacy — same treatment, with sequencing deferral.
  4. Overall justification — theoretical vs practical, what changed/held.
  5. Addenda — factors, risks, mitigations, and theoretical optima.

Every recommendation (including a documented no-change) carries a 2-week
expected-outcome projection plus explicit success and stop/escalate
criteria, enabling an automatic feedback loop on the next review.

All clinical judgement lives in :mod:`clinical_decision_policy`; this
module is the declarative assembler.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .types import SettingsParameter, SettingsRecommendation
from .clinical_decision_policy import ClinicalDecisionPolicy, DEFAULT_POLICY


# ── Enums ─────────────────────────────────────────────────────────────

class DecisionMode(str, Enum):
    CHANGE = "change"
    NO_CHANGE = "no_change"


class HoldReason(str, Enum):
    NONE = "none"
    DEFERRED_SEQUENCING = "deferred_pending_basal_isf"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CLINICIAN_CONTEXT = "clinician_context"
    NO_DEVIATION = "no_meaningful_deviation"


# ── Leaf dataclasses ──────────────────────────────────────────────────

@dataclass
class ExpectedOutcome:
    """A single 2-week projected metric for the feedback loop."""
    metric: str               # "TIR", "TBR<70", "TAR>180", ...
    baseline: float
    expected_2wk: float
    unit: str                 # "%", "mg/dL"
    direction: str            # "increase" / "decrease" / "stable"


@dataclass
class FollowUpCriteria:
    """Explicit success and stop/escalate gates for the next review."""
    success: List[str]
    stop_escalate: List[str]
    revisit_days: int = 14


@dataclass
class DomainRecommendation:
    """A per-parameter recommendation (basal / ISF / CR)."""
    domain: str
    mode: DecisionMode
    summary: str
    confidence: float
    evidence: str
    justification: str
    follow_up: FollowUpCriteria
    hold_reason: HoldReason = HoldReason.NONE
    current_value: Optional[float] = None
    practical_value: Optional[float] = None
    practical_change_pct: Optional[float] = None
    theoretical_value: Optional[float] = None
    theoretical_change_pct: Optional[float] = None
    affected_time_block: Optional[Tuple[float, float]] = None
    expected_outcomes: List[ExpectedOutcome] = field(default_factory=list)


@dataclass
class InsulinSufficiencyAssessment:
    """Overall insulin sufficiency overview (facet 0)."""
    summary: str
    overall_mode: DecisionMode
    main_risks: List[str]
    whats_working: List[str]
    hypo_burden_frac: float
    hyper_burden_frac: float


@dataclass
class ReimbursementEvidence:
    """Structured line-item evidence for reimbursement justification."""
    data_sufficiency: str
    risks_reviewed: List[str]
    mitigations: List[str]
    alternatives_discussed: List[str]
    patient_barriers: List[str]
    agreed_plan: str
    expected_trajectory: str
    follow_up_date: str


@dataclass
class RebootRecommendation:
    """Onboarding reinitialization ("settings reboot") recommendation."""
    recommended: bool
    rationale: str


@dataclass
class ReportFigure:
    """A data visualization attached to the report.

    Figures carry a self-contained base64 PNG payload (for portable HTML)
    and an optional relative path (for markdown that references a written
    PNG file). ``section`` ties the figure to the part of the report it
    supports so readers can follow along: ``insulin_sufficiency``,
    ``basal``, ``isf``, ``cr``, or ``overview``.
    """
    section: str
    title: str
    caption: str
    filename: str
    png_base64: Optional[str] = None
    rel_path: Optional[str] = None
    alt: str = ""


@dataclass
class ClinicalDecisionReport:
    """Top-level clinical-grade decision support report."""
    patient_id: str
    generated_at_utc: str
    glycemic_summary: Dict[str, float]
    insulin_sufficiency: InsulinSufficiencyAssessment
    basal: DomainRecommendation
    isf: DomainRecommendation
    cr: DomainRecommendation
    overall_justification: str
    addenda: List[str]
    reboot: RebootRecommendation
    policy: Dict
    reimbursement: Optional[ReimbursementEvidence] = None
    figures: List[ReportFigure] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = _to_jsonable(self)
        # Keep report.json lean: drop the heavy base64 image payloads,
        # preserving figure metadata (section/title/caption/filename/path).
        for fig in d.get("figures", []):
            fig["png_base64"] = None
        return d


# ── Serialization helper ──────────────────────────────────────────────

def _to_jsonable(obj):
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(getattr(obj, k))
                for k in obj.__dataclass_fields__}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


# ── Glycemic normalization ────────────────────────────────────────────

def _g(glycemic: Dict[str, float], *keys, default=0.0) -> float:
    for k in keys:
        if k in glycemic and glycemic[k] is not None:
            return float(glycemic[k])
    return default


_DOMAIN_PARAM = {
    "basal": SettingsParameter.BASAL_RATE,
    "isf": SettingsParameter.ISF,
    "cr": SettingsParameter.CR,
}
_DOMAIN_LABEL = {"basal": "Basal", "isf": "ISF", "cr": "Carb ratio"}


# ── Domain recommendation assembly ────────────────────────────────────

def _pick_domain_rec(
    domain: str,
    recs: List[SettingsRecommendation],
) -> Optional[SettingsRecommendation]:
    """Choose the most impactful actionable rec for a domain.

    Prefers the highest |predicted_tir_delta| among directional (non-
    informational) recs; falls back to the first informational rec so the
    builder can still surface evidence in a no-change.
    """
    param = _DOMAIN_PARAM[domain]
    domain_recs = [r for r in recs if r.parameter == param]
    if not domain_recs:
        return None
    actionable = [r for r in domain_recs
                  if r.direction in ("increase", "decrease")]
    if actionable:
        return max(actionable, key=lambda r: abs(r.predicted_tir_delta))
    return domain_recs[0]


def _build_domain(
    domain: str,
    rec: Optional[SettingsRecommendation],
    glycemic: Dict[str, float],
    policy: ClinicalDecisionPolicy,
) -> DomainRecommendation:
    label = _DOMAIN_LABEL[domain]
    tir_pp = _g(glycemic, "tir") * 100.0

    # ── No candidate recommendation at all ───────────────────────────
    if rec is None:
        return DomainRecommendation(
            domain=domain,
            mode=DecisionMode.NO_CHANGE,
            summary=f"{label}: no change recommended.",
            confidence=0.0,
            evidence=(f"No actionable {label} signal in the analysis "
                      f"window; current setting is consistent with "
                      f"observed glucose behavior."),
            justification=(
                f"{label} reviewed: the data do not support a change this "
                f"cycle. Maintaining the current setting and re-evaluating "
                f"at the next review."),
            hold_reason=HoldReason.NO_DEVIATION,
            expected_outcomes=_stable_outcomes(glycemic),
            follow_up=_no_change_followup(label, policy),
        )

    current = rec.current_value
    theoretical = rec.suggested_value
    confidence = rec.confidence
    delta = rec.predicted_tir_delta
    is_informational = rec.direction not in ("increase", "decrease")

    theoretical_pct = (
        (theoretical / current - 1.0) * 100.0
        if current else None)

    # ── Gating: confidence + effect size ─────────────────────────────
    if is_informational or not policy.passes_change_gate(confidence, delta):
        hold = (HoldReason.NO_DEVIATION if is_informational
                else HoldReason.INSUFFICIENT_EVIDENCE)
        if hold == HoldReason.INSUFFICIENT_EVIDENCE:
            failed = []
            if confidence < policy.min_confidence_for_change:
                failed.append(
                    f"confidence {confidence:.2f} below "
                    f"{policy.min_confidence_for_change:.2f}")
            if abs(delta) < policy.min_effect_size_pp:
                failed.append(
                    f"effect size {delta:+.1f}pp below "
                    f"{policy.min_effect_size_pp:.1f}pp")
            reason = "insufficient evidence (" + "; ".join(failed) + ")"
        else:
            reason = "no clinically meaningful deviation"
        return DomainRecommendation(
            domain=domain,
            mode=DecisionMode.NO_CHANGE,
            summary=f"{label}: no change recommended ({reason}).",
            confidence=confidence,
            evidence=rec.evidence,
            justification=(
                f"{label} reviewed: a directional signal exists "
                f"(theoretical target {theoretical:g}) but is held due to "
                f"{reason}. Re-evaluate at the next review."),
            hold_reason=hold,
            current_value=current,
            theoretical_value=theoretical,
            theoretical_change_pct=theoretical_pct,
            expected_outcomes=_stable_outcomes(glycemic),
            follow_up=_no_change_followup(label, policy),
        )

    # ── Actionable change: clamp theoretical -> practical ────────────
    practical = policy.clamp_practical_change(current, theoretical)
    practical_pct = (
        (practical / current - 1.0) * 100.0 if current else None)
    expected_tir = max(0.0, min(100.0, tir_pp + delta))

    return DomainRecommendation(
        domain=domain,
        mode=DecisionMode.CHANGE,
        summary=(f"{label}: {rec.direction} from {current:g} to "
                 f"{practical:g} ({practical_pct:+.0f}%)."),
        confidence=confidence,
        evidence=rec.evidence,
        justification=(
            f"{label} {rec.direction}: implement the practical step "
            f"{current:g} -> {practical:g} ({practical_pct:+.0f}%) now. "
            f"Theoretical optimum is {theoretical:g} "
            f"({theoretical_pct:+.0f}%); the practical step honors a safe "
            f"titration cap of {policy.max_change_pct_per_cycle:.0f}% per "
            f"cycle. {rec.rationale}"),
        current_value=current,
        practical_value=practical,
        practical_change_pct=practical_pct,
        theoretical_value=theoretical,
        theoretical_change_pct=theoretical_pct,
        affected_time_block=tuple(rec.affected_hours)
        if rec.affected_hours else None,
        expected_outcomes=_change_outcomes(glycemic, expected_tir),
        follow_up=_change_followup(label, glycemic, expected_tir, policy),
    )


# ── Expected outcomes + follow-up criteria ────────────────────────────

def _stable_outcomes(glycemic: Dict[str, float]) -> List[ExpectedOutcome]:
    tir = _g(glycemic, "tir") * 100.0
    tbr = _g(glycemic, "tbr_lt70", "tbr") * 100.0
    tar = _g(glycemic, "tar_gt180", "tar") * 100.0
    return [
        ExpectedOutcome("TIR", round(tir, 1), round(tir, 1), "%", "stable"),
        ExpectedOutcome("TBR<70", round(tbr, 2), round(tbr, 2), "%", "stable"),
        ExpectedOutcome("TAR>180", round(tar, 1), round(tar, 1), "%", "stable"),
    ]


def _change_outcomes(glycemic: Dict[str, float],
                     expected_tir: float) -> List[ExpectedOutcome]:
    tir = _g(glycemic, "tir") * 100.0
    tbr = _g(glycemic, "tbr_lt70", "tbr") * 100.0
    tar = _g(glycemic, "tar_gt180", "tar") * 100.0
    direction = "increase" if expected_tir > tir else (
        "decrease" if expected_tir < tir else "stable")
    return [
        ExpectedOutcome("TIR", round(tir, 1), round(expected_tir, 1),
                        "%", direction),
        ExpectedOutcome("TBR<70", round(tbr, 2), round(tbr, 2),
                        "%", "stable"),
        ExpectedOutcome("TAR>180", round(tar, 1),
                        round(max(0.0, tar - (expected_tir - tir)), 1),
                        "%", "decrease" if expected_tir > tir else "stable"),
    ]


def _no_change_followup(label: str,
                        policy: ClinicalDecisionPolicy) -> FollowUpCriteria:
    tbr_target = policy.target_tbr_frac * 100.0
    return FollowUpCriteria(
        success=[
            f"{label} held: glycemic metrics remain within tolerance of "
            f"baseline over the 2-week window.",
            f"No new hypoglycemia signal (TBR<70 stays below "
            f"{tbr_target:.0f}%).",
        ],
        stop_escalate=[
            f"TBR<70 rises by more than "
            f"{policy.tbr_worsening_guardrail_pp:.0f} pp -> escalate review.",
            f"TIR declines materially -> re-open {label} for change.",
        ],
        revisit_days=14,
    )


def _change_followup(label: str, glycemic: Dict[str, float],
                     expected_tir: float,
                     policy: ClinicalDecisionPolicy) -> FollowUpCriteria:
    tir = _g(glycemic, "tir") * 100.0
    gain = expected_tir - tir
    needed = gain * policy.success_capture_frac
    return FollowUpCriteria(
        success=[
            f"TIR improves by at least {needed:+.1f} pp toward the "
            f"projected {expected_tir:.0f}% within 2 weeks.",
            f"TBR<70 does not worsen by more than "
            f"{policy.tbr_worsening_guardrail_pp:.0f} pp.",
        ],
        stop_escalate=[
            f"TBR<70 increases by more than "
            f"{policy.tbr_worsening_guardrail_pp:.0f} pp after the {label} "
            f"change -> revert and escalate.",
            "Severe hypoglycemia (TBR<54) emerges -> revert immediately.",
            "No measurable TIR improvement at 2 weeks -> reassess direction.",
        ],
        revisit_days=14,
    )


# ── Insulin sufficiency overview ──────────────────────────────────────

def _build_insulin_sufficiency(
    glycemic: Dict[str, float],
    domains: List[DomainRecommendation],
    policy: ClinicalDecisionPolicy,
) -> InsulinSufficiencyAssessment:
    tir = _g(glycemic, "tir")
    tbr = _g(glycemic, "tbr_lt70", "tbr")
    tbr54 = _g(glycemic, "tbr_lt54")
    tar = _g(glycemic, "tar_gt180", "tar")
    cv = _g(glycemic, "cv_pct", default=0.0)

    risks: List[str] = []
    working: List[str] = []

    if tbr > policy.target_tbr_frac:
        risks.append(
            f"Hypoglycemia burden elevated (TBR<70 {tbr*100:.1f}% vs target "
            f"{policy.target_tbr_frac*100:.0f}%).")
    if tbr54 > 0.01:
        risks.append(
            f"Clinically significant lows present (TBR<54 {tbr54*100:.2f}%).")
    if tar > policy.target_tar_frac:
        risks.append(
            f"Hyperglycemia burden elevated (TAR>180 {tar*100:.1f}% vs "
            f"target {policy.target_tar_frac*100:.0f}%).")
    if cv and cv > 36.0:
        risks.append(
            f"Glycemic variability high (CV {cv:.0f}% vs target 36%).")

    if tir >= policy.target_tir_frac:
        working.append(f"Time-in-range at goal (TIR {tir*100:.0f}%).")
    if tbr <= policy.target_tbr_frac:
        working.append(
            f"Hypoglycemia within target (TBR<70 {tbr*100:.1f}%).")
    if cv and cv <= 36.0:
        working.append(f"Glucose variability controlled (CV {cv:.0f}%).")
    if not working:
        working.append(
            "Settings are internally consistent; no single parameter is "
            "grossly miscalibrated.")

    n_change = sum(1 for d in domains if d.mode == DecisionMode.CHANGE)
    overall_mode = (DecisionMode.CHANGE
                    if (n_change > 0 or risks) else DecisionMode.NO_CHANGE)

    if not risks:
        summary = (
            f"Overall insulin delivery is sufficient (TIR {tir*100:.0f}%, "
            f"TBR<70 {tbr*100:.1f}%, TAR>180 {tar*100:.0f}%). No major "
            f"safety concern identified.")
    else:
        summary = (
            f"Overall insulin delivery shows opportunity for improvement "
            f"(TIR {tir*100:.0f}%, TBR<70 {tbr*100:.1f}%, TAR>180 "
            f"{tar*100:.0f}%). {len(risks)} risk(s) identified; "
            f"{n_change} parameter change(s) proposed this cycle.")

    return InsulinSufficiencyAssessment(
        summary=summary,
        overall_mode=overall_mode,
        main_risks=risks,
        whats_working=working,
        hypo_burden_frac=tbr,
        hyper_burden_frac=tar,
    )


# ── CR sequencing / deferral ──────────────────────────────────────────

def _apply_cr_sequencing(
    basal: DomainRecommendation,
    isf: DomainRecommendation,
    cr: DomainRecommendation,
    glycemic: Dict[str, float],
    cr_score: Optional[float],
    policy: ClinicalDecisionPolicy,
) -> DomainRecommendation:
    """Defer a CR change when basal + ISF move in lock-step.

    Overnight and meal-response dynamics need to settle independently
    after a basal/ISF adjustment, so a same-cycle CR change is deferred
    unless severe persistent post-meal hyperglycemia justifies acting now.
    """
    if cr.mode != DecisionMode.CHANGE:
        return cr
    if not policy.defer_cr_when_basal_isf_lockstep:
        return cr
    lockstep = (basal.mode == DecisionMode.CHANGE
                and isf.mode == DecisionMode.CHANGE)
    if not lockstep:
        return cr

    tar = _g(glycemic, "tar_gt180", "tar")
    score = cr_score if cr_score is not None else 100.0
    if policy.is_severe_hyper(tar, score):
        # Exception: keep the CR change, annotate the override.
        cr.justification = (
            "Carb ratio change retained despite concurrent basal+ISF "
            "adjustment because severe persistent post-meal hyperglycemia "
            f"(TAR>180 {tar*100:.0f}%, CR effectiveness {score:.0f}/100) "
            "warrants acting now. " + cr.justification)
        return cr

    # Defer: convert to a documented no-change.
    return DomainRecommendation(
        domain="cr",
        mode=DecisionMode.NO_CHANGE,
        summary="Carb ratio: change deferred to next cycle.",
        confidence=cr.confidence,
        evidence=cr.evidence,
        justification=(
            "Carb ratio reviewed: a change is supported by the data, but "
            "basal and ISF are being adjusted in lock-step this cycle. "
            "Overnight and meal-response dynamics must settle independently "
            "before re-evaluating CR, so the CR change is deferred to the "
            "next review to avoid confounded titration."),
        hold_reason=HoldReason.DEFERRED_SEQUENCING,
        current_value=cr.current_value,
        theoretical_value=cr.theoretical_value,
        theoretical_change_pct=cr.theoretical_change_pct,
        expected_outcomes=_stable_outcomes(glycemic),
        follow_up=_no_change_followup("Carb ratio", policy),
    )


# ── Reboot composite ──────────────────────────────────────────────────

def _build_reboot(
    glycemic: Dict[str, float],
    recs: List[SettingsRecommendation],
    policy: ClinicalDecisionPolicy,
) -> RebootRecommendation:
    tbr = _g(glycemic, "tbr_lt70", "tbr")
    tar = _g(glycemic, "tar_gt180", "tar")

    mismatches = []
    confidences = []
    for r in recs:
        if r.current_value and r.current_value > 0 and r.suggested_value:
            mismatches.append(abs(r.suggested_value / r.current_value - 1.0))
        confidences.append(r.confidence)
    max_mismatch = max(mismatches) if mismatches else 0.0
    consistency = (sum(confidences) / len(confidences)
                   if confidences else 1.0)

    recommended = policy.should_reboot_onboarding(
        tbr_frac=tbr, tar_frac=tar,
        max_mismatch_ratio=max_mismatch,
        recommendation_consistency=consistency)

    if recommended:
        rationale = (
            "Severe-mismatch composite met: extreme glycemic burden "
            f"(TBR<70 {tbr*100:.1f}%, TAR>180 {tar*100:.0f}%), large "
            f"parameter mismatch (max {max_mismatch*100:.0f}% from current), "
            f"and low recommendation consistency (mean confidence "
            f"{consistency:.2f}). Recommend a structured settings "
            "reinitialization (onboarding reboot) to re-anchor basal, ISF, "
            "and CR to the patient's true physiology rather than titrating "
            "from miscalibrated starting values.")
    else:
        rationale = (
            "Settings reboot not indicated: the severe-mismatch composite "
            "(burden + large mismatch + low consistency) is not met. "
            "Incremental titration is appropriate.")

    return RebootRecommendation(recommended=recommended, rationale=rationale)


# ── Overall justification + addenda ───────────────────────────────────

def _build_overall_justification(
    domains: List[DomainRecommendation],
    reboot: RebootRecommendation,
) -> str:
    changes = [d for d in domains if d.mode == DecisionMode.CHANGE]
    holds = [d for d in domains if d.mode == DecisionMode.NO_CHANGE]
    parts = []
    if changes:
        change_str = "; ".join(
            f"{_DOMAIN_LABEL[d.domain]} {d.current_value:g}->"
            f"{d.practical_value:g}" for d in changes)
        parts.append(
            f"Practical changes this cycle: {change_str}. Each practical "
            f"step is the safe-titration projection of a larger theoretical "
            f"optimum (documented in the addenda).")
    else:
        parts.append(
            "No parameter changes are recommended this cycle; all domains "
            "were reviewed and held with documented rationale.")
    if holds:
        hold_str = ", ".join(
            f"{_DOMAIN_LABEL[d.domain]} ({d.hold_reason.value})"
            for d in holds)
        parts.append(f"Held/deferred: {hold_str}.")
    if reboot.recommended:
        parts.append(
            "A settings reinitialization is additionally recommended (see "
            "reboot rationale).")
    return " ".join(parts)


def _build_addenda(
    domains: List[DomainRecommendation],
    insulin: InsulinSufficiencyAssessment,
    policy: ClinicalDecisionPolicy,
) -> List[str]:
    addenda: List[str] = []
    addenda.append(
        "Factors considered: time-in-range distribution, hypo/hyper burden, "
        "glycemic variability, per-parameter advisory evidence, and "
        "cross-parameter sequencing.")
    for d in domains:
        if d.theoretical_value is not None:
            addenda.append(
                f"{_DOMAIN_LABEL[d.domain]} theoretical optimum: "
                f"{d.theoretical_value:g}"
                + (f" ({d.theoretical_change_pct:+.0f}% vs current "
                   f"{d.current_value:g})"
                   if d.theoretical_change_pct is not None else "")
                + (f"; practical step capped at "
                   f"{policy.max_change_pct_per_cycle:.0f}%/cycle -> "
                   f"{d.practical_value:g}."
                   if d.mode == DecisionMode.CHANGE
                   else "; held this cycle."))
    if insulin.main_risks:
        addenda.append(
            "Risks reviewed and mitigated: " + " ".join(insulin.main_risks))
    addenda.append(
        "Mitigations: changes are bounded by a per-cycle titration cap; "
        "carb ratio is sequenced after basal/ISF to avoid confounded "
        "adjustment; explicit stop/escalate criteria accompany every "
        "recommendation for the 2-week feedback loop.")
    return addenda


# ── Reimbursement evidence ────────────────────────────────────────────

def _build_reimbursement(
    glycemic: Dict[str, float],
    domains: List[DomainRecommendation],
    insulin: InsulinSufficiencyAssessment,
    days_of_data: Optional[float],
    patient_barriers: Optional[List[str]],
    generated_at: datetime,
    policy: ClinicalDecisionPolicy,
) -> ReimbursementEvidence:
    n_readings = int(_g(glycemic, "n_readings", default=0))
    days_str = (f"{days_of_data:.0f} days" if days_of_data
                else "the available window")
    data_sufficiency = (
        f"Analysis based on {days_str} of CGM data"
        + (f" ({n_readings:,} readings)" if n_readings else "")
        + ". Sufficient for time-in-range and titration assessment.")

    risks = list(insulin.main_risks) or [
        "No major glycemic risk identified; routine surveillance documented."]
    mitigations = [
        "Recommendations bounded by a safe per-cycle titration cap.",
        "Carb ratio sequenced after basal/ISF to prevent confounded change.",
        "Explicit stop/escalate criteria defined for each recommendation.",
    ]
    alternatives = [
        "Considered no-change vs incremental titration vs settings reboot.",
        "Theoretical optima documented but deferred in favor of safe steps.",
    ]
    barriers = list(patient_barriers or []) or [
        "No patient-reported adherence, supply, or prescription barriers "
        "noted at this review."]

    changes = [d for d in domains if d.mode == DecisionMode.CHANGE]
    if changes:
        plan = "Agreed plan: " + "; ".join(
            f"{_DOMAIN_LABEL[d.domain]} -> {d.practical_value:g}"
            for d in changes) + ". Re-evaluate in 2 weeks."
    else:
        plan = ("Agreed plan: maintain current settings with documented "
                "rationale; re-evaluate in 2 weeks.")

    tir = _g(glycemic, "tir") * 100.0
    expected_tir = tir
    for d in changes:
        for o in d.expected_outcomes:
            if o.metric == "TIR":
                expected_tir = max(expected_tir, o.expected_2wk)
    trajectory = (
        f"Projected time-in-range at next review: ~{expected_tir:.0f}% "
        f"(baseline {tir:.0f}%). Outcome will be scored against the "
        f"per-recommendation success and stop/escalate criteria.")

    follow_up_date = (generated_at + timedelta(days=14)).date().isoformat()

    return ReimbursementEvidence(
        data_sufficiency=data_sufficiency,
        risks_reviewed=risks,
        mitigations=mitigations,
        alternatives_discussed=alternatives,
        patient_barriers=barriers,
        agreed_plan=plan,
        expected_trajectory=trajectory,
        follow_up_date=follow_up_date,
    )


# ── Public builder ────────────────────────────────────────────────────

def build_clinical_decision_report(
    patient_id: str,
    glycemic: Dict[str, float],
    settings_recs: Optional[List[SettingsRecommendation]],
    policy: ClinicalDecisionPolicy = DEFAULT_POLICY,
    cr_score: Optional[float] = None,
    days_of_data: Optional[float] = None,
    generated_at_utc: Optional[str] = None,
    patient_barriers: Optional[List[str]] = None,
    figures: Optional[List[ReportFigure]] = None,
) -> ClinicalDecisionReport:
    """Assemble a clinical-grade decision support report.

    Args:
        patient_id: patient identifier.
        glycemic: glycemic summary dict. Range metrics are fractions
            (0-1): ``tir``, ``tbr_lt70`` (or ``tbr``), ``tbr_lt54``,
            ``tar_gt180`` (or ``tar``), ``tar_gt250``. Scalars:
            ``mean_mgdl``, ``cv_pct``, ``ea1c_gmi_pct``, ``n_readings``.
        settings_recs: advisory output (already consolidated by the
            pipeline). May be empty/None for a pure no-change report.
        policy: clinical decision policy (gating, titration, sequencing).
        cr_score: CR effectiveness score (0-100) for the severe-hyper
            exception. When omitted the exception cannot fire.
        days_of_data: data coverage for reimbursement documentation.
        generated_at_utc: ISO timestamp override (defaults to now).
        patient_barriers: clinician-supplied adherence/supply/prescription
            barriers for the reimbursement evidence block.
        figures: optional data visualizations to embed, each tagged with
            the report section it supports.

    Returns:
        ClinicalDecisionReport.
    """
    recs = list(settings_recs or [])
    now = datetime.now(timezone.utc)
    generated = generated_at_utc or now.isoformat()

    # Per-domain assembly.
    basal = _build_domain(
        "basal", _pick_domain_rec("basal", recs), glycemic, policy)
    isf = _build_domain(
        "isf", _pick_domain_rec("isf", recs), glycemic, policy)
    cr = _build_domain(
        "cr", _pick_domain_rec("cr", recs), glycemic, policy)

    # Sequencing: defer CR behind basal+ISF lock-step.
    cr = _apply_cr_sequencing(basal, isf, cr, glycemic, cr_score, policy)

    domains = [basal, isf, cr]
    insulin = _build_insulin_sufficiency(glycemic, domains, policy)
    reboot = _build_reboot(glycemic, recs, policy)
    overall = _build_overall_justification(domains, reboot)
    addenda = _build_addenda(domains, insulin, policy)

    reimbursement = None
    if policy.reimbursement_mode:
        reimbursement = _build_reimbursement(
            glycemic, domains, insulin, days_of_data, patient_barriers,
            now, policy)

    return ClinicalDecisionReport(
        patient_id=patient_id,
        generated_at_utc=generated,
        glycemic_summary=dict(glycemic),
        insulin_sufficiency=insulin,
        basal=basal,
        isf=isf,
        cr=cr,
        overall_justification=overall,
        addenda=addenda,
        reboot=reboot,
        policy=policy.to_dict(),
        reimbursement=reimbursement,
        figures=list(figures or []),
    )
