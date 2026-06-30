"""Unit tests for the clinical decision policy layer.

Red->green TDD for clinical_decision_policy.ClinicalDecisionPolicy — the
configurable gating/sequencing/titration layer that turns raw advisory
output into clinically documentable, reimbursement-ready decisions.

Design intent (from requirements lock 2026-06-30):
  - Quantitative gating: confidence + effect-size thresholds.
  - Titration cadence: ~10% per ~3 days, up to a per-cycle ceiling that
    grows while data continues to support change.
  - Sequencing: when basal + ISF change in lock-step, defer CR unless a
    severe-hyperglycemia exception fires.
  - Onboarding reboot: severe mismatch composite (hypo/hyper burden +
    large parameter mismatch + low recommendation consistency).
"""
from __future__ import annotations

import pytest

from cgmencode.production.clinical_decision_policy import (
    ClinicalDecisionPolicy,
    DEFAULT_POLICY,
    OutputMode,
)


class TestPolicyDefaults:
    def test_default_policy_is_instance(self):
        assert isinstance(DEFAULT_POLICY, ClinicalDecisionPolicy)

    def test_default_output_is_consolidated(self):
        assert DEFAULT_POLICY.output_mode == OutputMode.CONSOLIDATED

    def test_reimbursement_off_by_default(self):
        assert DEFAULT_POLICY.reimbursement_mode is False

    def test_defer_cr_enabled_by_default(self):
        assert DEFAULT_POLICY.defer_cr_when_basal_isf_lockstep is True

    def test_titration_moderate_default(self):
        # Moderate default: 20% per ~2-week cycle, ~10% per 3 days cadence.
        assert DEFAULT_POLICY.max_change_pct_per_cycle == pytest.approx(20.0)
        assert DEFAULT_POLICY.titration_step_pct == pytest.approx(10.0)
        assert DEFAULT_POLICY.titration_cadence_days == pytest.approx(3.0)


class TestChangeGating:
    def test_change_blocked_below_confidence(self):
        p = ClinicalDecisionPolicy(min_confidence_for_change=0.5)
        assert p.passes_change_gate(confidence=0.4, effect_size_pp=5.0) is False

    def test_change_blocked_below_effect_size(self):
        p = ClinicalDecisionPolicy(min_effect_size_pp=1.0)
        assert p.passes_change_gate(confidence=0.9, effect_size_pp=0.2) is False

    def test_change_allowed_when_both_pass(self):
        p = ClinicalDecisionPolicy(
            min_confidence_for_change=0.5, min_effect_size_pp=1.0)
        assert p.passes_change_gate(confidence=0.7, effect_size_pp=3.0) is True

    def test_effect_size_uses_absolute_value(self):
        p = ClinicalDecisionPolicy(min_effect_size_pp=1.0)
        assert p.passes_change_gate(confidence=0.9, effect_size_pp=-3.0) is True


class TestTitrationClamp:
    def test_clamp_caps_large_change(self):
        p = ClinicalDecisionPolicy(max_change_pct_per_cycle=20.0)
        # A theoretical 50% reduction is capped to 20% for the practical step.
        practical = p.clamp_practical_change(
            current=100.0, theoretical=50.0)
        assert practical == pytest.approx(80.0)

    def test_clamp_caps_large_increase(self):
        p = ClinicalDecisionPolicy(max_change_pct_per_cycle=20.0)
        practical = p.clamp_practical_change(
            current=100.0, theoretical=200.0)
        assert practical == pytest.approx(120.0)

    def test_clamp_passes_small_change(self):
        p = ClinicalDecisionPolicy(max_change_pct_per_cycle=20.0)
        practical = p.clamp_practical_change(
            current=100.0, theoretical=95.0)
        assert practical == pytest.approx(95.0)

    def test_clamp_zero_current_returns_theoretical(self):
        p = ClinicalDecisionPolicy(max_change_pct_per_cycle=20.0)
        assert p.clamp_practical_change(current=0.0, theoretical=5.0) == 5.0


class TestSevereHyperException:
    def test_severe_hyper_true_when_tar_and_cr_score_bad(self):
        p = ClinicalDecisionPolicy(
            severe_hyper_tar_frac=0.50, severe_hyper_cr_score_max=25.0)
        assert p.is_severe_hyper(tar_frac=0.55, cr_score=10.0) is True

    def test_severe_hyper_false_when_tar_ok(self):
        p = ClinicalDecisionPolicy(
            severe_hyper_tar_frac=0.50, severe_hyper_cr_score_max=25.0)
        assert p.is_severe_hyper(tar_frac=0.30, cr_score=10.0) is False

    def test_severe_hyper_false_when_cr_score_ok(self):
        p = ClinicalDecisionPolicy(
            severe_hyper_tar_frac=0.50, severe_hyper_cr_score_max=25.0)
        assert p.is_severe_hyper(tar_frac=0.55, cr_score=60.0) is False


class TestRebootComposite:
    def test_reboot_triggers_on_full_composite(self):
        p = ClinicalDecisionPolicy(
            reboot_tbr_frac=0.06, reboot_tar_frac=0.50,
            reboot_mismatch_ratio=0.40, reboot_consistency_max=0.45)
        # Extreme hyper burden + large mismatch + low consistency.
        assert p.should_reboot_onboarding(
            tbr_frac=0.02, tar_frac=0.60,
            max_mismatch_ratio=0.55, recommendation_consistency=0.30) is True

    def test_reboot_blocked_when_burden_ok(self):
        p = ClinicalDecisionPolicy(
            reboot_tbr_frac=0.06, reboot_tar_frac=0.50,
            reboot_mismatch_ratio=0.40, reboot_consistency_max=0.45)
        assert p.should_reboot_onboarding(
            tbr_frac=0.01, tar_frac=0.20,
            max_mismatch_ratio=0.55, recommendation_consistency=0.30) is False

    def test_reboot_blocked_when_mismatch_small(self):
        p = ClinicalDecisionPolicy(
            reboot_tbr_frac=0.06, reboot_tar_frac=0.50,
            reboot_mismatch_ratio=0.40, reboot_consistency_max=0.45)
        assert p.should_reboot_onboarding(
            tbr_frac=0.02, tar_frac=0.60,
            max_mismatch_ratio=0.10, recommendation_consistency=0.30) is False

    def test_reboot_blocked_when_consistency_high(self):
        p = ClinicalDecisionPolicy(
            reboot_tbr_frac=0.06, reboot_tar_frac=0.50,
            reboot_mismatch_ratio=0.40, reboot_consistency_max=0.45)
        assert p.should_reboot_onboarding(
            tbr_frac=0.02, tar_frac=0.60,
            max_mismatch_ratio=0.55, recommendation_consistency=0.80) is False

    def test_reboot_triggers_on_hypo_burden(self):
        p = ClinicalDecisionPolicy(
            reboot_tbr_frac=0.06, reboot_tar_frac=0.50,
            reboot_mismatch_ratio=0.40, reboot_consistency_max=0.45)
        # High TBR alone satisfies the burden leg.
        assert p.should_reboot_onboarding(
            tbr_frac=0.10, tar_frac=0.20,
            max_mismatch_ratio=0.55, recommendation_consistency=0.30) is True


class TestPolicyOverrides:
    def test_split_output_mode(self):
        p = ClinicalDecisionPolicy(output_mode=OutputMode.SPLIT)
        assert p.output_mode == OutputMode.SPLIT

    def test_reimbursement_mode_toggle(self):
        p = ClinicalDecisionPolicy(reimbursement_mode=True)
        assert p.reimbursement_mode is True

    def test_policy_is_serializable(self):
        p = ClinicalDecisionPolicy()
        d = p.to_dict()
        assert d["output_mode"] == "consolidated"
        assert d["reimbursement_mode"] is False
        assert "max_change_pct_per_cycle" in d


class TestDeconfounding:
    def test_defaults_enabled(self):
        p = ClinicalDecisionPolicy()
        assert p.prefer_deconfounded is True
        assert p.trust_deconfounded is True

    def test_is_deconfounded_detects_markers(self):
        p = ClinicalDecisionPolicy()
        assert p.is_deconfounded("Deconfounded basal block audit (EXP-3447)")
        assert p.is_deconfounded("Demand-phase ISF (EXP-2651) target")
        assert p.is_deconfounded("Multi-factor deconfounding (EXP-2741)")
        assert not p.is_deconfounded("ISF non-linearity (EXP-2511)")


class TestDoseShaping:
    def test_detects_dose_shaping(self):
        p = ClinicalDecisionPolicy()
        assert p.is_dose_shaping("ISF non-linearity (EXP-2511): ...")
        assert p.is_dose_shaping("Splitting into 2x1.4U would be more")
        assert p.is_dose_shaping("diminishing returns at high dose")

    def test_not_dose_shaping_for_baseline(self):
        p = ClinicalDecisionPolicy()
        assert not p.is_dose_shaping("Demand-phase ISF (EXP-2651) target")
        assert not p.is_dose_shaping("Overnight quadrant analysis (EXP-2589)")
        p = ClinicalDecisionPolicy()
        assert p.is_deconfounded("Deconfounded basal block audit (EXP-3447)")
        assert p.is_deconfounded("Demand-phase ISF (EXP-2651) target")
        assert p.is_deconfounded("Multi-factor deconfounding (EXP-2741)")
        assert not p.is_deconfounded("ISF non-linearity (EXP-2511)")

    def test_credit_recovers_dampened_confidence(self):
        # Loop isf_trust=0.3 dampened 0.6 -> 0.18; credit recovers toward 0.6.
        p = ClinicalDecisionPolicy()
        credited = p.credited_confidence("isf", 0.18, observed_trust=0.3)
        assert credited == pytest.approx(0.6, abs=1e-6)

    def test_credit_capped_for_isf_safety(self):
        # EXP-2738: ISF must stay bounded even when deconfounded.
        p = ClinicalDecisionPolicy(deconfounded_isf_confidence_cap=0.80)
        credited = p.credited_confidence("isf", 0.5, observed_trust=0.3)
        assert credited == pytest.approx(0.80)

    def test_credit_noop_when_trust_unknown(self):
        p = ClinicalDecisionPolicy()
        assert p.credited_confidence("isf", 0.18, observed_trust=None) == 0.18

    def test_credit_noop_when_disabled(self):
        p = ClinicalDecisionPolicy(trust_deconfounded=False)
        assert p.credited_confidence("isf", 0.18, observed_trust=0.3) == 0.18

    def test_credit_only_isf_cr(self):
        # Basal deconfounded recs are not re-credited (already un-dampened
        # upstream via EXP-3447), so basal credit is a no-op.
        p = ClinicalDecisionPolicy()
        assert p.credited_confidence("basal", 0.5, observed_trust=0.3) == 0.5

    def test_reimbursement_mode_toggle(self):
        p = ClinicalDecisionPolicy(reimbursement_mode=True)
        assert p.reimbursement_mode is True

    def test_policy_is_serializable(self):
        p = ClinicalDecisionPolicy()
        d = p.to_dict()
        assert d["output_mode"] == "consolidated"
        assert d["reimbursement_mode"] is False
        assert "max_change_pct_per_cycle" in d
