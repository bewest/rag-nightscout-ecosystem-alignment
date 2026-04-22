"""Integration test: audition matrix wiring through recommender."""
from __future__ import annotations

from cgmencode.production.recommender import generate_recommendations
from cgmencode.production.audition_matrix import AuditionInputs
from cgmencode.production.types import (
    BasalAssessment, ClinicalReport, ControllerType, GlycemicGrade,
    PatientProfile,
)


def _clinical() -> ClinicalReport:
    return ClinicalReport(
        grade=GlycemicGrade.B, risk_score=40.0, tir=65.0, tbr=3.0,
        tar=32.0, mean_glucose=160.0, gmi=6.8, cv=33.0,
        basal_assessment=BasalAssessment.APPROPRIATE, cr_score=70.0,
        recommendations=["Acceptable control."],
    )


def _profile() -> PatientProfile:
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 90}],
        cr_schedule=[{"time": "00:00", "value": 10}],
        basal_schedule=[{"time": "00:00", "value": 0.8}],
    )


def test_recommender_no_audition_inputs_backward_compat():
    recs = generate_recommendations(
        clinical=_clinical(), hypo_alert=None,
        meal_prediction=None, settings_recs=None,
    )
    # Backward compat: zero audition entries when not provided
    assert not any(r.action_type.startswith("audition_") for r in recs)


def test_recommender_patient_b_archetype_emits_audition_actions():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.0,
        isf_gap_pct=-14.0,
        post_high_mg_dl=30.9,
        wear_isf_drop_pct=-31.5,
    )
    recs = generate_recommendations(
        clinical=_clinical(), hypo_alert=None,
        meal_prediction=None, settings_recs=None,
        audition_inputs=inputs, profile=_profile(),
    )
    flag_actions = [r for r in recs if r.action_type.startswith("audition_flag_")]
    setting_actions = [r for r in recs
                       if r.action_type.startswith("audition_")
                       and not r.action_type.startswith("audition_flag_")]
    # All three high-severity flags surface
    flag_names = {r.action_type for r in flag_actions}
    assert "audition_flag_flat_low_recovery" in flag_names
    assert "audition_flag_isf_under_correction" in flag_names
    assert "audition_flag_site_degradation" in flag_names
    # Settings recs surface (ISF tighten + site-degradation)
    assert setting_actions
    assert any(
        r.settings_rec is not None
        and r.settings_rec.parameter.value == "isf"
        for r in setting_actions
    )
    # All audition entries are priority 2
    assert all(r.priority == 2 for r in flag_actions + setting_actions)
