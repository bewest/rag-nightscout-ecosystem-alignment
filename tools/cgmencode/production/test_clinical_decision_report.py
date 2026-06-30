"""Tests for the clinical-grade decision report builder.

Red->green TDD for clinical_decision_report.build_clinical_decision_report.

Covers the requirements locked 2026-06-30:
  0. Overall insulin sufficiency (hypo/hyper risk, what's working).
  1. Basal change/no-change with time block + practical vs theoretical.
  2. ISF change/no-change with time block + practical vs theoretical.
  3. CR change/no-change, deferred when basal+ISF move in lock-step.
  4. Overall justification (theoretical vs practical).
  5. Addenda documenting factors/risks/mitigations.
  + 2-week expected outcomes with success + stop/escalate criteria.
  + Reimbursement evidence block (toggle).
  + Onboarding reboot composite.
"""
from __future__ import annotations

import pytest

from cgmencode.production.types import (
    SettingsParameter, SettingsRecommendation,
)
from cgmencode.production.clinical_decision_policy import (
    ClinicalDecisionPolicy, OutputMode,
)
from cgmencode.production.clinical_decision_report import (
    build_clinical_decision_report,
    ClinicalDecisionReport,
    DomainRecommendation,
    DecisionMode,
    HoldReason,
)


# ── Fixtures / helpers ───────────────────────────────────────────────

def _glycemic(tir=0.62, tbr=0.047, tbr54=0.016, tar=0.337,
              tar250=0.12, mean=162.0, cv=43.4, gmi=7.19):
    return {
        "tir": tir, "tbr_lt70": tbr, "tbr_lt54": tbr54,
        "tar_gt180": tar, "tar_gt250": tar250,
        "mean_mgdl": mean, "cv_pct": cv, "ea1c_gmi_pct": gmi,
    }


def _rec(param, direction, current, suggested, delta, conf,
         affected=(0.0, 24.0), evidence=None):
    return SettingsRecommendation(
        parameter=param, direction=direction, magnitude_pct=abs(
            (suggested / current - 1.0) * 100) if current else 0.0,
        current_value=current, suggested_value=suggested,
        predicted_tir_delta=delta, affected_hours=affected,
        confidence=conf, evidence=evidence or f"evidence for {param.value}",
        rationale=f"rationale for {param.value}",
    )


# ── Top-level contract ───────────────────────────────────────────────

class TestReportShape:
    def test_returns_report(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert isinstance(rep, ClinicalDecisionReport)

    def test_has_all_domains(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert isinstance(rep.basal, DomainRecommendation)
        assert isinstance(rep.isf, DomainRecommendation)
        assert isinstance(rep.cr, DomainRecommendation)

    def test_serializes_to_dict(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        d = rep.to_dict()
        assert d["patient_id"] == "c"
        assert "insulin_sufficiency" in d
        assert "basal" in d and "isf" in d and "cr" in d
        assert d["basal"]["mode"] in ("change", "no_change")

    def test_policy_snapshot_embedded(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.policy["output_mode"] == "consolidated"


# ── No-change documentation (facet 0/4/5) ────────────────────────────

class TestNoChange:
    def test_empty_recs_yields_no_change(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.basal.mode == DecisionMode.NO_CHANGE
        assert rep.isf.mode == DecisionMode.NO_CHANGE
        assert rep.cr.mode == DecisionMode.NO_CHANGE

    def test_no_change_has_justification(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.basal.justification  # non-empty rationale even for hold

    def test_no_change_has_expected_outcomes(self):
        # A documented no-change must still predict a 2-week trajectory.
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert len(rep.cr.expected_outcomes) >= 1

    def test_no_change_has_followup_criteria(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.cr.follow_up.success
        assert rep.cr.follow_up.stop_escalate

    def test_low_confidence_change_is_held(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 60, 3.0, 0.2)]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.isf.mode == DecisionMode.NO_CHANGE
        assert rep.isf.hold_reason == HoldReason.INSUFFICIENT_EVIDENCE

    def test_passable_narrow_rec_beats_low_confidence_larger_delta(self):
        recs = [
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.0, 1.4, 3.0, 0.2,
                 affected=(0.0, 24.0)),
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.0, 1.1, 1.2, 0.65,
                 affected=(6.0, 12.0)),
        ]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.basal.mode == DecisionMode.CHANGE
        assert rep.basal.affected_time_block == (6.0, 12.0)


# ── Practical vs theoretical (facet 1/2) ─────────────────────────────

class TestPracticalVsTheoretical:
    def test_change_uses_clamped_practical(self):
        # Theoretical halving (50->25, -50%) clamped to -20% => 40.
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 25, 5.0, 0.8)]
        policy = ClinicalDecisionPolicy(max_change_pct_per_cycle=20.0)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs,
            policy=policy)
        assert rep.isf.mode == DecisionMode.CHANGE
        assert rep.isf.practical_value == pytest.approx(40.0)
        assert rep.isf.theoretical_value == pytest.approx(25.0)

    def test_time_block_present_on_change(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 60, 5.0, 0.8,
                     affected=(0.0, 6.0))]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.isf.affected_time_block == (0.0, 6.0)

    def test_time_block_absent_on_no_change(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.isf.affected_time_block is None

    def test_theoretical_recorded_in_addenda(self):
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 25, 5.0, 0.8)]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        joined = " ".join(rep.addenda).lower()
        assert "theoretical" in joined


# ── CR deferral sequencing (facet 3) ─────────────────────────────────

class TestCRDeferral:
    def _lockstep_recs(self):
        return [
            _rec(SettingsParameter.BASAL_RATE, "decrease", 1.4, 1.2, 3.0, 0.8),
            _rec(SettingsParameter.ISF, "increase", 50, 60, 3.0, 0.8),
            _rec(SettingsParameter.CR, "decrease", 10, 8, 3.0, 0.8),
        ]

    def test_cr_deferred_when_basal_isf_lockstep(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tar=0.20), settings_recs=self._lockstep_recs())
        assert rep.basal.mode == DecisionMode.CHANGE
        assert rep.isf.mode == DecisionMode.CHANGE
        assert rep.cr.mode == DecisionMode.NO_CHANGE
        assert rep.cr.hold_reason == HoldReason.DEFERRED_SEQUENCING

    def test_cr_not_deferred_when_severe_hyper(self):
        # Severe persistent hyper => CR exception fires, change allowed.
        rep = build_clinical_decision_report(
            patient_id="c",
            glycemic=_glycemic(tar=0.60), settings_recs=self._lockstep_recs(),
            cr_score=10.0)
        assert rep.cr.mode == DecisionMode.CHANGE

    def test_cr_change_allowed_when_no_lockstep(self):
        # Only CR changes; basal/isf hold => no deferral.
        recs = [_rec(SettingsParameter.CR, "decrease", 10, 8, 3.0, 0.8)]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.cr.mode == DecisionMode.CHANGE

    def test_defer_disabled_by_policy(self):
        policy = ClinicalDecisionPolicy(
            defer_cr_when_basal_isf_lockstep=False)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tar=0.20),
            settings_recs=self._lockstep_recs(), policy=policy)
        assert rep.cr.mode == DecisionMode.CHANGE


# ── Insulin sufficiency (facet 0) ────────────────────────────────────

class TestInsulinSufficiency:
    def test_flags_hypo_risk(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tbr=0.08), settings_recs=[])
        risks = " ".join(rep.insulin_sufficiency.main_risks).lower()
        assert "hypo" in risks

    def test_flags_hyper_risk(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tar=0.45), settings_recs=[])
        risks = " ".join(rep.insulin_sufficiency.main_risks).lower()
        assert "hyper" in risks or "high" in risks

    def test_reports_whats_working(self):
        rep = build_clinical_decision_report(
            patient_id="c",
            glycemic=_glycemic(tir=0.80, tbr=0.02, tar=0.18, cv=30.0),
            settings_recs=[])
        assert rep.insulin_sufficiency.whats_working


# ── Two-week outcomes ────────────────────────────────────────────────

class TestExpectedOutcomes:
    def test_tir_outcome_reflects_predicted_delta(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 55, 4.0, 0.8)]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tir=0.62), settings_recs=recs)
        tir_outcomes = [o for o in rep.isf.expected_outcomes
                        if o.metric == "TIR"]
        assert tir_outcomes
        o = tir_outcomes[0]
        assert o.baseline == pytest.approx(62.0, abs=0.1)
        assert o.expected_2wk == pytest.approx(66.0, abs=0.1)

    def test_change_has_success_and_stop_criteria(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 55, 4.0, 0.8)]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.isf.follow_up.success
        assert rep.isf.follow_up.stop_escalate
        assert rep.isf.follow_up.revisit_days == 14


# ── Reimbursement evidence ───────────────────────────────────────────

class TestReimbursement:
    def test_absent_by_default(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.reimbursement is None

    def test_present_when_mode_on(self):
        policy = ClinicalDecisionPolicy(reimbursement_mode=True)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            policy=policy, days_of_data=180.0,
            patient_barriers=["insulin supply gap"])
        rb = rep.reimbursement
        assert rb is not None
        assert rb.data_sufficiency
        assert rb.risks_reviewed
        assert rb.agreed_plan
        assert "insulin supply gap" in rb.patient_barriers
        assert rb.follow_up_date


# ── Onboarding reboot ────────────────────────────────────────────────

class TestRebootTrigger:
    def test_reboot_recommended_on_severe_mismatch(self):
        # Extreme hyper, large mismatch (50->150 ISF), low confidence.
        recs = [
            _rec(SettingsParameter.ISF, "increase", 50, 150, 3.0, 0.3),
            _rec(SettingsParameter.BASAL_RATE, "decrease", 1.4, 0.7, 3.0, 0.3),
        ]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(tar=0.60), settings_recs=recs)
        assert rep.reboot.recommended is True
        assert rep.reboot.rationale

    def test_no_reboot_when_well_controlled(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 55, 3.0, 0.8)]
        rep = build_clinical_decision_report(
            patient_id="c",
            glycemic=_glycemic(tir=0.80, tbr=0.02, tar=0.18), settings_recs=recs)
        assert rep.reboot.recommended is False


# ── Overall justification (facet 4) ──────────────────────────────────

class TestOverallJustification:
    def test_overall_justification_nonempty(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.overall_justification


class TestDeconfounding:
    def test_gate_aware_surfaces_deconfounded(self):
        # Live scenario: flashier confounded rec fails the gate; the
        # deconfounded rec passes -> it is surfaced as the change.
        recs = [
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 2.5, 2.8, 0.22,
                 evidence="Overnight quadrant analysis (EXP-2589)"),
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 1.9, 1.3, 0.67,
                 affected=(6.0, 12.0),
                 evidence="Deconfounded basal block audit (EXP-3447)"),
        ]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.basal.mode == DecisionMode.CHANGE
        assert rep.basal.affected_time_block == (6.0, 12.0)  # the EXP-3447 one

    def test_prefers_deconfounded_among_gated(self):
        # Both pass the gate; preference picks the deconfounded estimate
        # even though it has a smaller predicted delta.
        recs = [
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 2.5, 2.8, 0.80,
                 evidence="Overnight quadrant analysis (EXP-2589)"),
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 1.9, 1.3, 0.80,
                 affected=(6.0, 12.0),
                 evidence="Deconfounded basal block audit (EXP-3447)"),
        ]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.basal.affected_time_block == (6.0, 12.0)

    def test_disable_prefer_keeps_max_delta(self):
        recs = [
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 2.5, 2.8, 0.80,
                 evidence="EXP-2589"),
            _rec(SettingsParameter.BASAL_RATE, "increase", 1.7, 1.9, 1.3, 0.80,
                 affected=(6.0, 12.0), evidence="EXP-3447 deconfounded"),
        ]
        policy = ClinicalDecisionPolicy(prefer_deconfounded=False)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs,
            policy=policy)
        # Highest-delta rec wins when preference is off (full-day block).
        assert rep.basal.affected_time_block == (0.0, 24.0)

    def test_credit_lets_deconfounded_isf_pass_gate(self):
        # Dampened demand-phase ISF (conf 0.18) credited via Loop trust 0.3.
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 40, 3.0, 0.18,
                     evidence="Demand-phase ISF (EXP-2651) target")]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs,
            controller_trust={"isf": 0.3, "cr": 0.4, "basal": 0.3})
        assert rep.isf.mode == DecisionMode.CHANGE

    def test_no_credit_without_trust_holds(self):
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 40, 3.0, 0.18,
                     evidence="Demand-phase ISF (EXP-2651) target")]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        assert rep.isf.mode == DecisionMode.NO_CHANGE

    def test_non_deconfounded_isf_not_credited(self):
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 40, 3.0, 0.18,
                     evidence="ISF non-linearity (EXP-2511)")]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs,
            controller_trust={"isf": 0.3})
        assert rep.isf.mode == DecisionMode.NO_CHANGE

    def test_deconfounding_documented(self):
        recs = [_rec(SettingsParameter.ISF, "decrease", 50, 40, 3.0, 0.18,
                     evidence="Demand-phase ISF (EXP-2651) target")]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs,
            controller_trust={"isf": 0.3})
        joined = (rep.isf.justification + " ".join(rep.addenda)).lower()
        assert "deconfound" in joined
