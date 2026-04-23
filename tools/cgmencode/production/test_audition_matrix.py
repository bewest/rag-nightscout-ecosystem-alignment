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


def test_p_simpson_high_emits_medium():
    """EXP-2859: P(simpson) >= 0.9 → MEDIUM severity, takes precedence."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        simpson_paradox=False,  # would suppress under EXP-2854 logic
        p_simpson=0.95,         # but bootstrap says high-confidence Simpson
    )
    flags = classify_triage_flags(inputs)
    warn = [f for f in flags if f.name == "window_dependence_warning"]
    assert warn and warn[0].severity == "medium"
    assert "P(simpson)=95%" in warn[0].rationale


def test_p_simpson_boundary_emits_low():
    """EXP-2859: 0.1 < P(simpson) < 0.9 → LOW severity, boundary case."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_simpson=0.5,
    )
    flags = classify_triage_flags(inputs)
    warn = [f for f in flags if f.name == "window_dependence_warning"]
    assert warn and warn[0].severity == "low"
    assert "boundary" in warn[0].rationale.lower()


def test_p_simpson_low_suppresses():
    """EXP-2859: P(simpson) <= 0.1 → confidently non-Simpson, suppress."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",   # would normally trigger phenotype proxy
        median_recovery_fraction=0.6,
        p_simpson=0.05,         # but bootstrap says definitely not
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "window_dependence_warning" not in names


def test_p_isf_under_high_emits_high_severity():
    """EXP-2861: P(under)>=0.9 → HIGH severity, bootstrap-confident."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",
        median_recovery_fraction=0.6,
        p_isf_under_correction=0.95,
        p_isf_over_correction=0.0,
    )
    flags = classify_triage_flags(inputs)
    under = [f for f in flags if f.name == "isf_under_correction"]
    assert under and under[0].severity == "high"
    assert "EXP-2861" in under[0].rationale


def test_p_isf_over_high_emits_medium():
    """EXP-2861: P(over)>=0.9 → MEDIUM severity."""
    inputs = AuditionInputs(
        controller=ControllerType.TRIO,
        smb_capable=True,
        phenotype="down_shift",
        median_recovery_fraction=0.5,
        p_isf_over_correction=0.92,
        p_isf_under_correction=0.0,
    )
    flags = classify_triage_flags(inputs)
    over = [f for f in flags if f.name == "isf_over_correction"]
    assert over and over[0].severity == "medium"
    assert "EXP-2861" in over[0].rationale


def test_p_isf_boundary_emits_low():
    """EXP-2861: 0.1<=P<0.9 → LOW severity, boundary."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_isf_under_correction=0.4,
        p_isf_over_correction=0.05,
    )
    flags = classify_triage_flags(inputs)
    under = [f for f in flags if f.name == "isf_under_correction"]
    assert under and under[0].severity == "low"
    assert "boundary" in under[0].rationale.lower()


def test_p_isf_within_band_suppresses():
    """EXP-2861: both P<0.1 → confidently neutral, suppress; ignore point isf_gap_pct."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        isf_gap_pct=-25,                  # would normally trigger naive flag
        p_isf_under_correction=0.05,      # but bootstrap says no
        p_isf_over_correction=0.0,
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "isf_under_correction" not in names
    assert "isf_over_correction" not in names


def test_p_isf_takes_precedence_over_point_estimate():
    """EXP-2861: bootstrap fields override naive isf_gap_pct branch."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        isf_gap_pct=+50,                 # naive would emit over-correction
        p_isf_under_correction=0.95,     # bootstrap says under!
        p_isf_over_correction=0.0,
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "isf_under_correction" in names
    assert "isf_over_correction" not in names


def test_p_low_recovery_high_emits_high_severity():
    """EXP-2862: flat + P(low recovery)>=0.9 → HIGH severity, bootstrap-confident."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.0,
        p_low_recovery=1.0,
    )
    flags = classify_triage_flags(inputs)
    rec = [f for f in flags if f.name == "flat_low_recovery"]
    assert rec and rec[0].severity == "high"
    assert "EXP-2862" in rec[0].rationale


def test_p_low_recovery_boundary_emits_low():
    """EXP-2862: flat + 0.1 <= P < 0.9 → LOW severity, boundary."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.3,
        p_low_recovery=0.5,
    )
    flags = classify_triage_flags(inputs)
    rec = [f for f in flags if f.name == "flat_low_recovery"]
    assert rec and rec[0].severity == "low"
    assert "boundary" in rec[0].rationale.lower()


def test_p_low_recovery_below_threshold_suppresses():
    """EXP-2862: flat + P(low) < 0.1 → confidently fine, suppress; ignore naive."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.3,    # would normally trigger naive flag
        p_low_recovery=0.05,             # but bootstrap says no
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "flat_low_recovery" not in names


def test_p_low_recovery_takes_precedence_over_point_estimate():
    """EXP-2862: bootstrap field overrides naive median_recovery_fraction branch."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,    # naive would NOT emit
        p_low_recovery=0.95,             # bootstrap says low
    )
    flags = classify_triage_flags(inputs)
    rec = [f for f in flags if f.name == "flat_low_recovery"]
    assert rec and rec[0].severity == "high"


def test_p_site_degradation_high_emits_high_severity():
    """EXP-2863: P(site-degradation)>=0.9 → HIGH severity."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",
        median_recovery_fraction=0.6,
        p_site_degradation=0.95,
    )
    flags = classify_triage_flags(inputs)
    site = [f for f in flags if f.name == "site_degradation"]
    assert site and site[0].severity == "high"
    assert "EXP-2863" in site[0].rationale


def test_p_site_degradation_boundary_emits_low():
    """EXP-2863: 0.1<=P<0.9 → LOW (boundary). Critical given typical CI width >100pp."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_site_degradation=0.5,
    )
    flags = classify_triage_flags(inputs)
    site = [f for f in flags if f.name == "site_degradation"]
    assert site and site[0].severity == "low"
    assert "boundary" in site[0].rationale.lower()


def test_p_site_degradation_low_suppresses():
    """EXP-2863: P<0.1 → suppress; ignore naive wear_isf_drop_pct."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        wear_isf_drop_pct=-30,         # naive would emit HIGH
        p_site_degradation=0.05,       # bootstrap says no
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "site_degradation" not in names


def test_p_site_degradation_takes_precedence_over_naive():
    """EXP-2863: bootstrap branch precedes naive wear_isf_drop_pct branch."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        wear_isf_drop_pct=-5,            # naive would NOT emit
        p_site_degradation=0.95,         # bootstrap says yes
    )
    flags = classify_triage_flags(inputs)
    site = [f for f in flags if f.name == "site_degradation"]
    assert site and site[0].severity == "high"


def test_p_post_high_high_emits_medium_severity():
    """EXP-2864: P(envelope>25)>=0.9 → MEDIUM severity."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="up_shift",
        median_recovery_fraction=0.6,
        p_post_high_envelope=0.95,
    )
    flags = classify_triage_flags(inputs)
    flag = [f for f in flags if f.name == "post_high_envelope"]
    assert flag and flag[0].severity == "medium"
    assert "EXP-2864" in flag[0].rationale


def test_p_post_high_boundary_emits_low():
    """EXP-2864: 0.1<=P<0.9 → LOW (boundary)."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_post_high_envelope=0.4,
    )
    flags = classify_triage_flags(inputs)
    flag = [f for f in flags if f.name == "post_high_envelope"]
    assert flag and flag[0].severity == "low"
    assert "boundary" in flag[0].rationale.lower()


def test_p_post_high_below_threshold_suppresses():
    """EXP-2864: P<0.1 → suppress; ignore naive post_high_mg_dl."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        post_high_mg_dl=40,             # naive would emit
        p_post_high_envelope=0.05,      # bootstrap says no
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "post_high_envelope" not in names


def test_p_post_high_takes_precedence_over_naive():
    """EXP-2864: bootstrap branch precedes naive post_high_mg_dl."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        post_high_mg_dl=10,             # naive would NOT emit
        p_post_high_envelope=0.95,      # bootstrap says yes
    )
    flags = classify_triage_flags(inputs)
    flag = [f for f in flags if f.name == "post_high_envelope"]
    assert flag and flag[0].severity == "medium"


def test_p_basal_mismatch_high_emits_high_severity_with_safety_caveat():
    """EXP-2865: P>=0.9 → HIGH severity; rationale must contain safety caveat."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_basal_mismatch=0.95,
        basal_recommended_mult=0.07,
    )
    flags = classify_triage_flags(inputs)
    flag = [f for f in flags if f.name == "basal_mismatch"]
    assert flag and flag[0].severity == "high"
    assert "EXP-2865" in flag[0].rationale
    assert "TRIAGE" in flag[0].rationale
    assert "do NOT lower basal" in flag[0].rationale


def test_p_basal_mismatch_boundary_emits_low():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_basal_mismatch=0.4,
    )
    flags = classify_triage_flags(inputs)
    flag = [f for f in flags if f.name == "basal_mismatch"]
    assert flag and flag[0].severity == "low"


def test_p_basal_mismatch_below_threshold_suppresses():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        p_basal_mismatch=0.05,
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "basal_mismatch" not in names


def test_p_basal_mismatch_none_emits_no_flag():
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
    )
    flags = classify_triage_flags(inputs)
    names = {f.name for f in flags}
    assert "basal_mismatch" not in names


def test_basal_mismatch_loop_includes_hypo_prevention_hint():
    """EXP-2871/2872/2873: Loop basal_mismatch rationale should reference
    hypo-prevention bias and recommend softening schedule first."""
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.5,
        p_basal_mismatch=0.95,
        basal_recommended_mult=0.40,
    )
    flags = classify_triage_flags(inputs)
    bm = [f for f in flags if f.name == "basal_mismatch"]
    assert bm, "expected basal_mismatch flag"
    assert "Loop" in bm[0].rationale
    assert "hypo-prevention" in bm[0].rationale.lower()
    assert "schedule" in bm[0].rationale.lower()


def test_basal_mismatch_trio_includes_smb_substitution_hint():
    """EXP-2871/2872/2873: Trio basal_mismatch rationale should reference
    SMB substitution and recommend ISF audit before lowering basal."""
    inputs = AuditionInputs(
        controller=ControllerType.TRIO,
        smb_capable=True,
        phenotype="flat",
        median_recovery_fraction=0.5,
        p_basal_mismatch=0.95,
        basal_recommended_mult=0.40,
    )
    flags = classify_triage_flags(inputs)
    bm = [f for f in flags if f.name == "basal_mismatch"]
    assert bm, "expected basal_mismatch flag"
    assert "Trio" in bm[0].rationale
    assert "SMB" in bm[0].rationale or "smb" in bm[0].rationale.lower()
    assert "ISF" in bm[0].rationale
