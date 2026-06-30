"""Tests for the demand-phase ISF recommendation synthesizer.

Reproducibly surfaces the validated demand-phase ISF (the true 0-2h
insulin effect, EXP-2651) as a deconfounded ISF candidate so the decision
layer can recommend a safety-bounded change when warranted, or hold with
informative context when the estimate is too sparse.
"""
from __future__ import annotations

from cgmencode.production.types import SettingsParameter
from cgmencode.production.clinical_decision_report import (
    synthesize_demand_isf_rec,
    build_clinical_decision_report,
    DecisionMode,
)


def _glycemic(tir=0.58, tar=0.40, tbr=0.02):
    return {
        "tir": tir, "tbr_lt70": tbr, "tbr_lt54": 0.004,
        "tar_gt180": tar, "tar_gt250": 0.10,
        "mean_mgdl": 170.0, "cv_pct": 37.0, "ea1c_gmi_pct": 7.4,
    }


class TestSynthesizer:
    def test_decrease_when_demand_below_profile(self):
        rec = synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=30, apparent_isf=88.5,
            inflation_ratio=2.95, n_corrections=40, confidence_label="high",
            ci_low=26, ci_high=34)
        assert rec is not None
        assert rec.parameter == SettingsParameter.ISF
        assert rec.direction == "decrease"
        assert rec.current_value == 40
        assert rec.suggested_value == 30

    def test_increase_when_demand_above_profile(self):
        rec = synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=52, apparent_isf=90,
            inflation_ratio=1.7, n_corrections=40, confidence_label="high",
            ci_low=46, ci_high=58)
        assert rec.direction == "increase"

    def test_evidence_is_deconfounded_no_controller_marker(self):
        rec = synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=30, apparent_isf=88.5,
            inflation_ratio=2.95, n_corrections=40, confidence_label="high",
            ci_low=26, ci_high=34)
        assert "EXP-2651" in rec.evidence
        assert "[Controller:" not in rec.evidence  # not pipeline-dampened
        # Mentions apparent inflation so it is not confused with the target.
        assert "88" in rec.evidence or "2.9" in rec.evidence

    def test_confidence_maps_from_label(self):
        hi = synthesize_demand_isf_rec(40, 30, 88, 2.9, 40, "high", 26, 34)
        med = synthesize_demand_isf_rec(40, 30, 88, 2.9, 25, "medium", 24, 36)
        lo = synthesize_demand_isf_rec(40, 30, 88, 2.9, 5, "low", 21, 39)
        assert hi.confidence > med.confidence > lo.confidence

    def test_none_when_gap_small(self):
        rec = synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=39, apparent_isf=80,
            inflation_ratio=2.0, n_corrections=40, confidence_label="high",
            ci_low=36, ci_high=42)
        assert rec is None

    def test_none_when_too_few_corrections(self):
        rec = synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=30, apparent_isf=88,
            inflation_ratio=2.9, n_corrections=2, confidence_label="low",
            ci_low=21, ci_high=39)
        assert rec is None

    def test_none_when_demand_missing(self):
        assert synthesize_demand_isf_rec(
            profile_isf=40, demand_isf=None, apparent_isf=88,
            inflation_ratio=2.9, n_corrections=40, confidence_label="high",
            ci_low=None, ci_high=None) is None


class TestSynthesizerInReport:
    def test_high_confidence_demand_drives_change(self):
        rec = synthesize_demand_isf_rec(
            40, 30, 88.5, 2.95, 40, "high", 26, 34)
        rep = build_clinical_decision_report(
            patient_id="x", glycemic=_glycemic(), settings_recs=[rec],
            controller_trust={"isf": 0.3})
        assert rep.isf.mode == DecisionMode.CHANGE
        assert rep.isf.theoretical_value == 30
        # Clamp keeps the practical step safe (>= 32 for a 40 baseline, 20%).
        assert rep.isf.practical_value >= 32

    def test_low_confidence_demand_holds_with_context(self):
        rec = synthesize_demand_isf_rec(
            40, 30, 88.5, 2.95, 5, "low", 21, 39)
        rep = build_clinical_decision_report(
            patient_id="x", glycemic=_glycemic(), settings_recs=[rec],
            controller_trust={"isf": 0.3})
        assert rep.isf.mode == DecisionMode.NO_CHANGE
        # The demand-phase signal and its theoretical target are surfaced.
        assert rep.isf.theoretical_value == 30
        assert "EXP-2651" in (rep.isf.evidence or "")
