"""Tests for the cross-design migration hypothetical (GAP-XDES-001)."""
from __future__ import annotations

import pytest


def _mk_clinical(tir=0.66, tbr=0.038, tbr54=0.005, tar=0.30):
    """Stub a ClinicalReport with the percentage fields the advisor reads.
    `tbr54` arg is retained for backward-compatibility with this test
    file's old call sites but the advisor derives severe-hypo from
    `tbr` directly (ClinicalReport has no tbr_lt54 field today)."""
    class _C:
        pass
    c = _C()
    c.tir = tir
    c.tbr = tbr
    c.tar = tar
    return c


# ──────────────────────────────────────────────────────────────────────


def test_loop_to_oref1_emits_directional_estimate():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(tir=0.62, tbr=0.027, tbr54=0.0014, tar=0.34),
        ControllerType.LOOP, days_of_data=60.0,
    )
    assert len(recs) == 1
    rec = recs[0]
    assert rec.action_type == "design_migration_hypothetical"
    assert rec.priority == 3
    assert "Trio or AAPS (oref1)" in rec.description
    assert rec.predicted_tir_delta > 0


def test_oref1_already_above_ceiling_returns_no_recommendation():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    # Patient already on oref1, no Loop migration suggested
    recs = recommend_design_migration(
        _mk_clinical(tir=0.85, tbr=0.02, tbr54=0.0, tar=0.13),
        ControllerType.AAPS, days_of_data=60.0,
        target_design='oref1',
    )
    assert recs == []


def test_high_tbr_triggers_risk_warning():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(tir=0.55, tbr=0.06, tbr54=0.015, tar=0.39),
        ControllerType.LOOP, days_of_data=60.0,
    )
    assert len(recs) == 1
    assert "Caveat" in recs[0].description
    assert "hepatic suppression" in recs[0].description


def test_short_data_returns_no_recommendation():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(), ControllerType.LOOP, days_of_data=5.0,
    )
    assert recs == []


def test_unknown_controller_returns_no_recommendation():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(), ControllerType.UNKNOWN, days_of_data=60.0,
    )
    assert recs == []


def test_high_tir_patient_gets_scaled_benefit():
    """A patient close to the oref1 baseline should get a smaller dTIR
    than the cohort delta of +16.5pp."""
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(tir=0.78, tbr=0.025, tbr54=0.0, tar=0.20),
        ControllerType.LOOP, days_of_data=60.0,
    )
    assert len(recs) == 1
    # Headroom is ~83-78=5 → cap at 6 (headroom + 1)
    assert recs[0].predicted_tir_delta <= 6.0
    assert recs[0].predicted_tir_delta > 0


def test_predicted_tir_delta_within_dataclass_cap():
    from tools.cgmencode.production.advisor._design_comparison import (
        recommend_design_migration,
    )
    from tools.cgmencode.production.types import ControllerType
    recs = recommend_design_migration(
        _mk_clinical(tir=0.55, tbr=0.04, tbr54=0.005, tar=0.40),
        ControllerType.LOOP, days_of_data=60.0,
    )
    assert -15.0 <= recs[0].predicted_tir_delta <= 15.0
    assert not hasattr(recs[0], "_raw_predicted_tir_delta")
