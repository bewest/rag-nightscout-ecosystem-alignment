"""Tests for audition_matrix production module (EXP-2843..2847 synthesis)."""
from __future__ import annotations

import pytest

from cgmencode.production.audition_matrix import (
    AuditionInputs,
    AuditionFlag,
    classify_triage_flags,
    generate_audition_recommendations,
)
from cgmencode.production.types import (
    ControllerType,
    PatientProfile,
    SettingsParameter,
)


def _profile() -> PatientProfile:
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 90}],
        cr_schedule=[{"time": "00:00", "value": 10}],
        basal_schedule=[{"time": "00:00", "value": 0.8}],
        dia_hours=5.0,
    )


def test_patient_b_archetype_emits_three_flags():
    """Patient `b` (the audition-matrix triple-flag) hits flat-low-recovery,
    isf_under_correction, and site_degradation simultaneously."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.0,
        isf_gap_pct=-14.0,
        post_high_mg_dl=30.9,
        wear_isf_drop_pct=-31.5,
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "flat_low_recovery" in names
    assert "isf_under_correction" in names
    assert "site_degradation" in names
    assert "post_high_envelope" in names
    assert all(isinstance(f, AuditionFlag) for f in flags)


def test_well_controlled_patient_emits_no_flags():
    inputs = AuditionInputs(
        controller=ControllerType.TRIO,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.85,
        isf_gap_pct=5.0,
        post_high_mg_dl=10.0,
        wear_isf_drop_pct=-5.0,
    )
    assert classify_triage_flags(inputs) == []


def test_down_shifter_recommends_dawn_window():
    """EXP-2845c: down_shifters cut hardest at dawn."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="down_shift",
        median_recovery_fraction=0.6,
    )
    recs = generate_audition_recommendations(inputs, _profile())
    assert len(recs) >= 1
    dawn = [r for r in recs if r.affected_hours == (0.0, 6.0)]
    assert dawn, "down_shifter should produce a dawn-window recommendation"
    # Loop without SMB → basal route
    assert dawn[0].parameter == SettingsParameter.BASAL_RATE
    assert dawn[0].direction == "decrease"


def test_up_shifter_smb_capable_routes_to_isf():
    """EXP-2845: SMB-capable controllers route through ISF, not basal."""
    inputs = AuditionInputs(
        controller=ControllerType.TRIO,
        smb_capable=True,
        phenotype="up_shift",
        median_recovery_fraction=0.5,
    )
    recs = generate_audition_recommendations(inputs, _profile())
    isf_recs = [r for r in recs if r.parameter == SettingsParameter.ISF]
    assert isf_recs, "SMB-capable up_shifter should route through ISF"
    # up_shifter + ISF route → ISF DECREASE (tighter) per matrix
    assert isf_recs[0].direction == "decrease"


def test_isf_gap_drives_under_correction_recommendation():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.2,
        isf_gap_pct=-14.0,
    )
    recs = generate_audition_recommendations(inputs, _profile())
    isf = [r for r in recs if "under-correction" in r.evidence
           or "under-correction" in r.rationale]
    assert isf, "negative ISF gap should emit under-correction rec"
    rec = isf[0]
    # Magnitude bounded and rounded to gap magnitude
    assert 0 < rec.magnitude_pct <= 20.0
    assert rec.current_value == 90.0
    # decrease in mg/dL/U from 90 by 14% ≈ 77.4
    assert 70 < rec.suggested_value < 85


def test_profile_attached_for_basal_recommendation():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="down_shift",
        median_recovery_fraction=0.6,
    )
    recs = generate_audition_recommendations(inputs, _profile())
    basal = [r for r in recs if r.parameter == SettingsParameter.BASAL_RATE]
    assert basal
    rec = basal[0]
    assert rec.current_value == 0.8
    # 10% decrease
    assert abs(rec.suggested_value - 0.72) < 0.01


def test_no_profile_leaves_zero_values():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.2,
        isf_gap_pct=-14.0,
    )
    recs = generate_audition_recommendations(inputs, profile=None)
    assert recs
    assert recs[0].current_value == 0.0
    assert recs[0].suggested_value == 0.0


def test_site_degradation_recommends_low_confidence_isf_decrease():
    inputs = AuditionInputs(
        controller=ControllerType.AAPS,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.3,
        wear_isf_drop_pct=-25.0,
    )
    recs = generate_audition_recommendations(inputs, _profile())
    site = [r for r in recs if "cannula-age" in r.evidence]
    assert site
    assert site[0].confidence < 0.6  # site rec is lower confidence
    assert site[0].affected_hours == (0.0, 24.0)


def test_up_shift_emits_window_dependence_warning():
    """EXP-2850: up_shift patients are window-sensitive (50% sign-consistent
    vs 80-100% for flat/down). Audition must surface a warning."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",
        median_recovery_fraction=0.6,
    )
    flags = classify_triage_flags(inputs)
    warn = [f for f in flags if f.name == "window_dependence_warning"]
    assert warn, "up_shift should emit window_dependence_warning"
    assert warn[0].severity == "low"


def test_flat_and_down_do_not_emit_window_dependence_warning():
    """EXP-2850: flat (100%) and down_shift (80%) are timescale-robust;
    no window-dependence warning required."""
    for ph in ("flat", "down_shift"):
        inputs = AuditionInputs(
            controller=ControllerType.LOOP,
            smb_capable=False,
            phenotype=ph,
            median_recovery_fraction=0.6,
        )
        flags = classify_triage_flags(inputs)
        names = {f.name for f in flags}
        assert "window_dependence_warning" not in names, (
            f"{ph} should NOT emit window_dependence_warning"
        )


def test_simpson_flag_overrides_phenotype_proxy():
    """EXP-2854/2856: when EXP-2853 Simpson flag is available, it takes
    precedence over the phenotype proxy. Severity is LOW without stability
    evidence (per EXP-2856 — flagged patients are only 25% stable)."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",  # would NOT trigger phenotype proxy
        median_recovery_fraction=0.6,
        simpson_paradox=True,
    )
    flags = classify_triage_flags(inputs)
    warn = [f for f in flags if f.name == "window_dependence_warning"]
    assert warn, "Simpson flag should emit window_dependence_warning"
    assert warn[0].severity == "low"  # provisional without stability
    assert "Simpson" in warn[0].rationale
    assert "provisional" in warn[0].rationale.lower() or "25%" in warn[0].rationale


def test_simpson_with_stability_promotes_severity():
    """EXP-2856: Simpson + rolling-window stability >=0.75 → MEDIUM severity."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        simpson_paradox=True,
        simpson_stability_frac=0.85,
    )
    flags = classify_triage_flags(inputs)
    warn = [f for f in flags if f.name == "window_dependence_warning"]
    assert warn
    assert warn[0].severity == "medium"
    assert "stable" in warn[0].rationale.lower()


def test_simpson_false_suppresses_phenotype_proxy():
    """EXP-2854: explicit Simpson=False overrides up_shift phenotype proxy."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",   # would normally trigger
        median_recovery_fraction=0.6,
        simpson_paradox=False,  # but direct measurement says no
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "window_dependence_warning" not in names, (
        "Explicit Simpson=False should suppress phenotype-proxy warning"
    )
