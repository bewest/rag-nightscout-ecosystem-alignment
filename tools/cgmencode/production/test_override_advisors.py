"""Tests for the meal-override schedule recommender (GAP-OVRD-001).

Covers the dinner-window pattern detection that produces a Loop /
Trio / AAPS override recommendation given the patient's actual evening
descent or overshoot signature.
"""
from __future__ import annotations

import numpy as np
import pytest


def _mk_profile(target=110.0, isf=50.0, basal=0.8):
    """Minimal profile-shape stub mirroring PatientProfile accessors."""
    class _P:
        target_schedule = [{'value': target}]
        isf_schedule = [{'value': isf}]
        basal_schedule = [{'value': basal}]
    return _P()


def _make_dinner_descent(days=14, baseline=140.0, nadir=85.0):
    """Synthesize glucose+hours showing late-evening drop-into-overnight.

    Pattern: high in dinner window (140), descends to nadir (85) overnight.
    This is the alcohol/hepatic-suppression signature.
    """
    n = days * 24 * 12
    hours = np.tile(np.linspace(0, 24, 24 * 12, endpoint=False), days)
    glucose = np.full(n, 110.0)
    # Dinner window 18-22: elevated baseline
    dinner = (hours >= 18) & (hours < 22)
    glucose[dinner] = baseline
    # Overnight 22-6: descend to nadir (alcohol pattern)
    overnight = (hours >= 22) | (hours < 6)
    glucose[overnight] = nadir
    return glucose, hours


def _make_dinner_overshoot(days=14, baseline=140.0, peak=220.0):
    n = days * 24 * 12
    hours = np.tile(np.linspace(0, 24, 24 * 12, endpoint=False), days)
    glucose = np.full(n, 110.0)
    dinner = (hours >= 18) & (hours < 22)
    glucose[dinner] = baseline
    overnight = (hours >= 22) | (hours < 6)
    glucose[overnight] = peak
    return glucose, hours


# ──────────────────────────────────────────────────────────────────────
# Pattern detection
# ──────────────────────────────────────────────────────────────────────


def test_descent_pattern_emits_alcohol_override_recommendation():
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    g, h = _make_dinner_descent(baseline=160.0, nadir=85.0)
    recs = recommend_meal_override_schedule(
        g, h, _mk_profile(),
        days_of_data=14.0, has_alcohol_context=True,
    )
    assert len(recs) == 1
    rec = recs[0]
    assert rec.action_type == "loop_override_recommendation"
    assert rec.priority == 3
    assert "alcohol-induced" in rec.description.lower()
    assert "dinner / alcohol" in rec.description.lower()
    # softer settings: target up, ISF up (less aggressive), basal down
    assert "1.30" in rec.description  # ISF ratio
    assert "0.80" in rec.description  # basal multiplier


def test_descent_pattern_uses_neutral_phrasing_without_alcohol_hint():
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    g, h = _make_dinner_descent(baseline=160.0, nadir=85.0)
    recs = recommend_meal_override_schedule(
        g, h, _mk_profile(),
        days_of_data=14.0, has_alcohol_context=None,
    )
    assert len(recs) == 1
    desc = recs[0].description.lower()
    assert "alcohol-induced hepatic glucose suppression" not in desc
    assert "post-dinner hepatic suppression" in desc


def test_overshoot_pattern_emits_aggressive_override():
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    g, h = _make_dinner_overshoot(baseline=140.0, peak=220.0)
    recs = recommend_meal_override_schedule(
        g, h, _mk_profile(target=110.0),
        days_of_data=14.0,
    )
    assert len(recs) == 1
    rec = recs[0]
    assert "dinner aggressive" in rec.description.lower()
    assert "0.85" in rec.description  # tighter ISF ratio


def test_no_recommendation_when_pattern_is_flat():
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    n = 14 * 24 * 12
    hours = np.tile(np.linspace(0, 24, 24 * 12, endpoint=False), 14)
    g = np.full(n, 130.0)  # perfectly flat
    recs = recommend_meal_override_schedule(
        g, hours, _mk_profile(), days_of_data=14.0,
    )
    assert recs == []


def test_no_recommendation_below_min_days():
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    g, h = _make_dinner_descent(days=5)
    recs = recommend_meal_override_schedule(
        g, h, _mk_profile(), days_of_data=5.0,
    )
    assert recs == []


def test_recommendation_predicted_tir_within_dataclass_cap():
    """Smoke test: the override recs ship a predicted_tir_delta that
    survives the GAP-ADVR-003 dataclass clamp without triggering it."""
    from tools.cgmencode.production.advisor._override_advisors import (
        recommend_meal_override_schedule,
    )
    g, h = _make_dinner_descent()
    recs = recommend_meal_override_schedule(
        g, h, _mk_profile(), days_of_data=14.0,
    )
    assert len(recs) == 1
    assert -15.0 <= recs[0].predicted_tir_delta <= 15.0
    assert not hasattr(recs[0], "_raw_predicted_tir_delta")
