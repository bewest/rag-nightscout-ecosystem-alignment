"""clinical_decision_policy.py — Configurable policy layer for clinical-grade
decision support.

This module isolates *all* tunable clinical judgement from the report
builder so the behaviour can be changed without rewiring core logic. It
encodes the requirements locked on 2026-06-30:

  * Quantitative gating (confidence + effect size) for change vs no-change.
  * Practical titration clamp (theoretical optimum is preserved separately
    in the report addenda; the in-body recommendation is the safe step).
  * Sequencing/dependency rules: defer carb ratio (CR) when basal + ISF are
    being changed in lock-step, unless a severe-hyperglycemia exception
    fires.
  * Onboarding reinitialization ("settings reboot") via a severe-mismatch
    composite: hypo/hyper burden + large parameter mismatch + low
    recommendation consistency.

Titration default rationale: clinicians commonly titrate ~10% every ~3
days, which permits roughly 20% over a two-week review cycle while data
continues to support the direction. The defaults below encode that
"moderate" stance; tighten or loosen via constructor overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class OutputMode(str, Enum):
    """How deliverables are packaged for different audiences."""
    CONSOLIDATED = "consolidated"   # single combined report (default)
    SPLIT = "split"                 # separate audience-specific outputs


@dataclass
class ClinicalDecisionPolicy:
    """Tunable policy for clinical-grade decision support.

    All clinical thresholds live here so the report builder stays
    declarative. Construct with overrides to change behaviour; nothing in
    the builder hard-codes these values.
    """

    # ── Output / mode toggles ────────────────────────────────────────
    output_mode: OutputMode = OutputMode.CONSOLIDATED
    reimbursement_mode: bool = False

    # ── Change vs no-change gating ───────────────────────────────────
    min_confidence_for_change: float = 0.5   # 0-1 recommendation confidence
    min_effect_size_pp: float = 1.0          # predicted TIR delta (pp)

    # ── Practical titration ──────────────────────────────────────────
    max_change_pct_per_cycle: float = 20.0   # ceiling per ~2-week cycle
    titration_step_pct: float = 10.0         # typical step magnitude
    titration_cadence_days: float = 3.0      # typical interval between steps

    # ── Sequencing / dependency rules ────────────────────────────────
    defer_cr_when_basal_isf_lockstep: bool = True
    severe_hyper_tar_frac: float = 0.50      # TAR>180 fraction for exception
    severe_hyper_cr_score_max: float = 25.0  # CR effectiveness score (0-100)

    # ── Onboarding reboot composite ──────────────────────────────────
    reboot_tbr_frac: float = 0.06            # extreme hypo burden leg
    reboot_tar_frac: float = 0.55            # extreme hyper burden leg
    reboot_mismatch_ratio: float = 0.40      # |suggested/current - 1| leg
    reboot_consistency_max: float = 0.45     # low recommendation consistency

    # ── Target outcomes (ADA/ATTD consensus defaults) ────────────────
    target_tir_frac: float = 0.70
    target_tbr_frac: float = 0.04
    target_tar_frac: float = 0.25

    # ── Two-week feedback guardrails ─────────────────────────────────
    # A change is judged a success if it captures at least this fraction
    # of the predicted TIR gain without worsening TBR beyond the guardrail.
    success_capture_frac: float = 0.50
    tbr_worsening_guardrail_pp: float = 1.0  # absolute pp increase in TBR

    # ── Deconfounding (accuracy / less-conservative) ─────────────────
    # Deconfounded advisories explicitly remove the controller-masking
    # confound (e.g. demand-phase ISF EXP-2651, correction-denominator /
    # bilateral EXP-2741, deconfounded basal block audit EXP-3447). The
    # pipeline's controller-masking penalty therefore double-counts the
    # confound for these, making recommendations overly conservative.
    prefer_deconfounded: bool = True   # prefer deconfounded gate-passers
    trust_deconfounded: bool = True    # credit back the masking penalty
    deconfounding_markers: tuple = (
        "EXP-3447", "EXP-2651", "EXP-2741", "deconfound", "deconfounded",
        "demand-phase", "correction-denominator", "bilateral",
    )
    # Dose-shaping advisories (e.g. ISF non-linearity EXP-2511) describe a
    # dose-conditional effective ISF — guidance to split large corrections,
    # NOT a change to the baseline ISF schedule. They are demoted out of
    # the headline recommendation and surfaced as labeled addenda guidance
    # so a large-dose effective ISF (e.g. 16) is never presented as the
    # baseline ISF "optimum".
    dose_shaping_markers: tuple = (
        "non-linearity", "nonlinearity", "EXP-2511", "diminishing returns",
        "splitting", "split-dose", "split into", "dose-shaping",
    )
    # Safety caps on credited confidence. ISF is capped tighter because
    # removing the controller's residual safety margin raises TBR
    # (EXP-2738: +6.2pp); deconfounding improves accuracy but must not
    # license an unbounded ISF change.
    deconfounded_isf_confidence_cap: float = 0.80
    deconfounded_cr_confidence_cap: float = 0.90

    # ── Gating helpers ───────────────────────────────────────────────

    def passes_change_gate(self, confidence: float,
                           effect_size_pp: float) -> bool:
        """True when a change is well-supported enough to recommend.

        Both legs must pass: confidence at/above threshold and an effect
        size (|predicted TIR delta|) at/above threshold.
        """
        if confidence is None or effect_size_pp is None:
            return False
        return (confidence >= self.min_confidence_for_change
                and abs(effect_size_pp) >= self.min_effect_size_pp)

    def clamp_practical_change(self, current: float,
                               theoretical: float) -> float:
        """Clamp a theoretical target value to the per-cycle titration cap.

        The theoretical optimum is preserved separately (report addenda);
        this returns the *practical* value to implement now. A zero/invalid
        current value cannot be expressed as a percentage change, so the
        theoretical value is returned unchanged.
        """
        if not current or current <= 0:
            return theoretical
        cap = self.max_change_pct_per_cycle / 100.0
        lo = current * (1.0 - cap)
        hi = current * (1.0 + cap)
        return float(min(max(theoretical, lo), hi))

    def is_severe_hyper(self, tar_frac: float, cr_score: float) -> bool:
        """Severe persistent post-meal hyperglycemia exception.

        Used to permit a same-cycle CR change even when CR would normally
        be deferred behind a basal+ISF lock-step adjustment.
        """
        return (tar_frac >= self.severe_hyper_tar_frac
                and cr_score <= self.severe_hyper_cr_score_max)

    def should_reboot_onboarding(self, tbr_frac: float, tar_frac: float,
                                 max_mismatch_ratio: float,
                                 recommendation_consistency: float) -> bool:
        """Severe-mismatch composite that recommends a settings reboot.

        All three legs must hold:
          1. Extreme glycemic burden (hypo OR hyper).
          2. Large parameter mismatch (max |suggested/current - 1|).
          3. Low recommendation consistency (mean confidence proxy).
        """
        burden = (tbr_frac >= self.reboot_tbr_frac
                  or tar_frac >= self.reboot_tar_frac)
        mismatch = max_mismatch_ratio >= self.reboot_mismatch_ratio
        inconsistent = recommendation_consistency <= self.reboot_consistency_max
        return bool(burden and mismatch and inconsistent)

    def is_deconfounded(self, text: str) -> bool:
        """True when advisory evidence indicates a validated deconfounding
        method (controller-masking confound already removed)."""
        if not text:
            return False
        low = text.lower()
        return any(m.lower() in low for m in self.deconfounding_markers)

    def is_dose_shaping(self, text: str) -> bool:
        """True when an advisory is dose-conditional guidance (split large
        corrections) rather than a baseline schedule change."""
        if not text:
            return False
        low = text.lower()
        return any(m.lower() in low for m in self.dose_shaping_markers)

    def credited_confidence(self, domain: str, confidence: float,
                            observed_trust: Optional[float]) -> float:
        """Recover the controller-masking penalty for a deconfounded
        ISF/CR advisory, bounded by a safety cap.

        The pipeline uniformly multiplies observed ISF/CR confidence by a
        controller "trust" factor (<1 for masking controllers like Loop).
        That penalty does not apply to deconfounded estimates, so we divide
        it back out — capped to preserve documented safety margins
        (EXP-2738). Basal is excluded (already un-dampened upstream via
        EXP-3447). A no-op when disabled or trust is unknown/≥1.
        """
        if not self.trust_deconfounded:
            return confidence
        if domain not in ("isf", "cr"):
            return confidence
        if not observed_trust or observed_trust <= 0 or observed_trust >= 1:
            return confidence
        cap = (self.deconfounded_isf_confidence_cap if domain == "isf"
               else self.deconfounded_cr_confidence_cap)
        return float(min(confidence / observed_trust, cap))

    def to_dict(self) -> dict:
        """JSON-serializable snapshot for report provenance."""
        d = asdict(self)
        d["output_mode"] = self.output_mode.value
        return d


# Module-level default used when callers don't supply a policy.
DEFAULT_POLICY = ClinicalDecisionPolicy()
