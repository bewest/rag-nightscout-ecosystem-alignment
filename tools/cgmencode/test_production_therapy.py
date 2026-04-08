"""Comprehensive test suite for production_therapy.py (v10 pipeline).

Run with:
    PYTHONPATH=tools pytest tools/cgmencode/test_production_therapy.py -v
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from cgmencode.production_therapy import (
    TargetProfile, ADA_CLINICAL, AID_AWARE, PREGNANCY, PEDIATRIC,
    TARGET_PROFILES, DEFAULT_PROFILE,
    Grade, SafetyTier, HypoCause,
    TimeInRanges, TherapyFlags, HypoEpisode, Preconditions, Recommendation,
    TherapyAssessment, TherapyPipeline, PatientReport, CohortReport,
    compute_time_in_ranges, compute_safety_score, compute_v10_score,
    generate_recommendations,
    STEPS_PER_DAY, STEPS_PER_HOUR,
    ADA_TIR_TARGET, ADA_TBR_L1_TARGET, ADA_TBR_L2_TARGET,
    ADA_TAR_L1_TARGET, ADA_TAR_L2_TARGET, ADA_CV_TARGET,
    V10_WEIGHTS, GRADE_BOUNDARIES,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def make_glucose(value=120.0, n=STEPS_PER_DAY * 14):
    """Create constant glucose array."""
    return np.full(n, value, dtype=np.float64)


def make_zeros(n=STEPS_PER_DAY * 14):
    return np.zeros(n, dtype=np.float64)


# ---------------------------------------------------------------------------
# 1. TestTargetProfiles
# ---------------------------------------------------------------------------

class TestTargetProfiles:

    def test_ada_defaults(self):
        p = ADA_CLINICAL
        assert p.tir_target == 70.0
        assert p.tbr_l1_target == 4.0
        assert p.tbr_l2_target == 1.0
        assert p.tar_l1_target == 25.0
        assert p.tar_l2_target == 5.0
        assert p.cv_target == 36.0
        assert p.safety_override is True
        assert p.tbr_sustained_only is False

    def test_aid_aware_defaults(self):
        p = AID_AWARE
        assert p.cv_target == 40.0
        assert p.tbr_sustained_only is True
        assert p.sustained_min_minutes == 15
        assert p.safety_critical == 10.0
        assert p.safety_high == 6.0
        assert p.safety_moderate == 3.0

    def test_pregnancy_tighter(self):
        p = PREGNANCY
        assert p.tbr_l1_target == 3.0
        assert p.tbr_l2_target == 0.5
        assert p.cv_target == 33.0

    def test_profile_registry(self):
        assert set(TARGET_PROFILES.keys()) == {'ada', 'aid', 'pregnancy', 'pediatric'}

    def test_default_profile_is_ada(self):
        assert DEFAULT_PROFILE is ADA_CLINICAL

    def test_safety_tier_from_profile(self):
        # AID_AWARE has safety_moderate=3.0 and safety_high=6.0
        # 5.0 >= 3.0 (moderate) but < 6.0 (high) → MODERATE
        tier = AID_AWARE.safety_tier_from_tbr(5.0)
        assert tier == SafetyTier.MODERATE


# ---------------------------------------------------------------------------
# 2. TestGrade
# ---------------------------------------------------------------------------

class TestGrade:

    def test_grade_boundaries(self):
        assert Grade.from_score(80) == Grade.A
        assert Grade.from_score(79.9) == Grade.B
        assert Grade.from_score(65) == Grade.B
        assert Grade.from_score(64.9) == Grade.C
        assert Grade.from_score(50) == Grade.C
        assert Grade.from_score(49.9) == Grade.D
        assert Grade.from_score(0) == Grade.D
        assert Grade.from_score(100) == Grade.A

    def test_grade_enum_values(self):
        assert Grade.A.value == 'A'
        assert Grade.B.value == 'B'
        assert Grade.C.value == 'C'
        assert Grade.D.value == 'D'


# ---------------------------------------------------------------------------
# 3. TestSafetyTier
# ---------------------------------------------------------------------------

class TestSafetyTier:

    def test_ada_tiers(self):
        assert SafetyTier.from_tbr(8.0) == SafetyTier.CRITICAL
        assert SafetyTier.from_tbr(4.0) == SafetyTier.HIGH
        assert SafetyTier.from_tbr(2.0) == SafetyTier.MODERATE
        assert SafetyTier.from_tbr(1.9) == SafetyTier.LOW

    def test_aid_tiers(self):
        # AID_AWARE: moderate=3.0, high=6.0 → 5.0 is MODERATE (not HIGH)
        assert SafetyTier.from_tbr(5.0, profile=AID_AWARE) == SafetyTier.MODERATE

    def test_backward_compatible(self):
        # No profile → uses default ADA boundaries: 4.0 → HIGH
        assert SafetyTier.from_tbr(4.0) == SafetyTier.HIGH


# ---------------------------------------------------------------------------
# 4. TestTimeInRanges
# ---------------------------------------------------------------------------

class TestTimeInRanges:

    @pytest.fixture()
    def tir_good(self):
        """Good TIR: meets all ADA defaults."""
        return TimeInRanges(
            tir=80.0, tbr_l1=2.0, tbr_l2=0.5, tar_l1=15.0, tar_l2=2.5,
            cv=30.0, mean_glucose=140.0, overnight_tir=85.0,
        )

    @pytest.fixture()
    def tir_bad(self):
        """Bad TIR: fails all ADA defaults."""
        return TimeInRanges(
            tir=40.0, tbr_l1=8.0, tbr_l2=3.0, tar_l1=30.0, tar_l2=10.0,
            cv=45.0, mean_glucose=200.0, overnight_tir=35.0,
        )

    def test_total_tbr(self, tir_good):
        assert tir_good.total_tbr == pytest.approx(2.5)

    def test_total_tar(self, tir_good):
        assert tir_good.total_tar == pytest.approx(17.5)

    def test_estimated_a1c(self, tir_good):
        expected = (140.0 + 46.7) / 28.7
        assert tir_good.estimated_a1c == pytest.approx(expected)

    def test_meets_ada_defaults(self, tir_good):
        assert tir_good.meets_ada_tir is True   # 80 >= 70
        assert tir_good.meets_ada_tbr is True   # 2 < 4 and 0.5 < 1
        assert tir_good.meets_ada_tar is True   # 15 < 25 and 2.5 < 5
        assert tir_good.meets_ada_cv is True    # 30 < 36

    def test_meets_targets_with_profile(self, tir_good):
        # With PREGNANCY (cv_target=33): cv 30 < 33 → still True
        result = tir_good.meets_targets(PREGNANCY)
        assert result['cv'] is True

        # Fabricate a borderline case: cv=34 → fails PREGNANCY but passes ADA
        borderline = TimeInRanges(
            tir=80.0, tbr_l1=2.0, tbr_l2=0.4, tar_l1=15.0, tar_l2=2.5,
            cv=34.0, mean_glucose=140.0, overnight_tir=85.0,
        )
        assert borderline.meets_targets(ADA_CLINICAL)['cv'] is True   # 34 < 36
        assert borderline.meets_targets(PREGNANCY)['cv'] is False     # 34 >= 33

    def test_target_status_all_met(self, tir_good):
        assert tir_good.target_status() == 'meets_all_targets'

    def test_target_status_none_met(self, tir_bad):
        assert tir_bad.target_status() == 'significantly_below'


# ---------------------------------------------------------------------------
# 5. TestComputeTimeInRanges
# ---------------------------------------------------------------------------

class TestComputeTimeInRanges:

    def test_all_in_range(self):
        g = make_glucose(120.0)
        r = compute_time_in_ranges(g)
        assert r.tir == pytest.approx(100.0)
        assert r.tbr_l1 == pytest.approx(0.0)
        assert r.tbr_l2 == pytest.approx(0.0)
        assert r.tar_l1 == pytest.approx(0.0)
        assert r.tar_l2 == pytest.approx(0.0)

    def test_all_low(self):
        g = make_glucose(60.0)
        r = compute_time_in_ranges(g)
        # 60 is in [54, 69] → TBR L1
        assert r.tbr_l1 == pytest.approx(100.0)
        assert r.tir == pytest.approx(0.0)

    def test_all_high(self):
        g = make_glucose(200.0)
        r = compute_time_in_ranges(g)
        # 200 is in [181, 250] → TAR L1
        assert r.tar_l1 == pytest.approx(100.0)
        assert r.tir == pytest.approx(0.0)

    def test_mixed_values(self):
        # 50% in-range, 25% low, 25% high
        n = 400
        g = np.empty(n, dtype=np.float64)
        g[:200] = 120.0   # in range
        g[200:300] = 60.0  # TBR L1
        g[300:400] = 200.0 # TAR L1
        r = compute_time_in_ranges(g)
        assert r.tir == pytest.approx(50.0)
        assert r.tbr_l1 == pytest.approx(25.0)
        assert r.tar_l1 == pytest.approx(25.0)

    def test_nan_handling(self):
        n = 400
        g = np.full(n, 120.0, dtype=np.float64)
        g[200:] = np.nan
        r = compute_time_in_ranges(g)
        # Only 200 valid values, all 120 → TIR=100%
        assert r.tir == pytest.approx(100.0)

    def test_cv_calculation(self):
        g = np.array([100.0, 200.0], dtype=np.float64)
        r = compute_time_in_ranges(g)
        mean_g = 150.0
        std_g = np.std(g)  # population std
        expected_cv = std_g / mean_g * 100
        assert r.cv == pytest.approx(expected_cv, rel=1e-5)


# ---------------------------------------------------------------------------
# 6. TestComputeSafetyScore
# ---------------------------------------------------------------------------

class TestComputeSafetyScore:

    def test_perfect_safety(self):
        assert compute_safety_score(0, 0, 0) == pytest.approx(100.0)

    def test_moderate_tbr(self):
        # penalty = 3*10 + 0*50 + 0 = 30 → 100-30 = 70
        assert compute_safety_score(3, 0, 0) == pytest.approx(70.0)

    def test_severe_tbr(self):
        # penalty = 0*10 + 2*50 + 0 = 100 → 100-100 = 0
        assert compute_safety_score(0, 2, 0) == pytest.approx(0.0)

    def test_clamped_to_zero(self):
        # penalty = 10*10 + 5*50 + 50 = 100+250+50 = 400 → max(0, -300) = 0
        assert compute_safety_score(10, 5, 50) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 7. TestComputeV10Score
# ---------------------------------------------------------------------------

class TestComputeV10Score:

    def test_perfect_score(self):
        # tir=100*0.5 + max(0,100-0*2)*0.2 + 100*0.1 + 100*0.2
        # = 50 + 20 + 10 + 20 = 100
        score = compute_v10_score(tir=100, cv=0, overnight_tir=100, safety_score=100)
        assert score == pytest.approx(100.0)

    def test_weight_sum(self):
        total = sum(V10_WEIGHTS.values())
        assert total == pytest.approx(1.0)
        assert V10_WEIGHTS == {'tir': 0.5, 'cv': 0.2, 'overnight': 0.1, 'safety': 0.2}

    def test_grade_d_score(self):
        # tir=10*0.5=5, cv component=max(0,100-90*2)=max(0,-80)=0, ov=10*0.1=1, safety=10*0.2=2
        # total = 5+0+1+2=8
        score = compute_v10_score(tir=10, cv=90, overnight_tir=10, safety_score=10)
        assert score < 50
        assert Grade.from_score(score) == Grade.D


# ---------------------------------------------------------------------------
# 8. TestGenerateRecommendations
# ---------------------------------------------------------------------------

class TestGenerateRecommendations:

    def _default_flags(self, **overrides):
        kw = dict(basal_flag=False, cr_flag=False, isf_flag=False,
                  cv_flag=False, tbr_flag=False)
        kw.update(overrides)
        return TherapyFlags(**kw)

    def test_safety_override_fires(self):
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=5.0, safety_tier=SafetyTier.HIGH,
            profile=ADA_CLINICAL,
        )
        assert recs[0].parameter == 'aggressiveness'
        assert recs[0].direction == 'decrease'

    def test_safety_override_magnitude(self):
        flags = self._default_flags()
        # tbr_excess = 5.0 - 4.0 = 1.0 → magnitude = min(20, 1.0*5) = 5
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=5.0, safety_tier=SafetyTier.HIGH,
            profile=ADA_CLINICAL,
        )
        assert recs[0].magnitude_pct == pytest.approx(5.0)

        # Large excess: 20.0 - 4.0 = 16 → min(20, 80) = 20 (capped)
        recs2 = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=20.0, safety_tier=SafetyTier.CRITICAL,
            profile=ADA_CLINICAL,
        )
        assert recs2[0].magnitude_pct == pytest.approx(20.0)

    def test_no_safety_override_below_threshold(self):
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=3.9, safety_tier=SafetyTier.MODERATE,
            profile=ADA_CLINICAL,
        )
        # No aggressiveness rec → should be 'maintain'
        assert all(r.parameter != 'aggressiveness' for r in recs)

    def test_fix_order_basal_cr_isf(self):
        flags = self._default_flags(basal_flag=True, cr_flag=True, cv_flag=True)
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=3.0, max_excursion=80,
            cv=40, total_tbr=3.0, safety_tier=SafetyTier.MODERATE,
            profile=ADA_CLINICAL,
        )
        params = [r.parameter for r in recs]
        assert params == ['basal', 'cr', 'isf']

    def test_no_flags_maintain(self):
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.A, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=2.0, safety_tier=SafetyTier.MODERATE,
            profile=ADA_CLINICAL,
        )
        assert len(recs) == 1
        assert recs[0].direction == 'maintain'

    def test_aid_profile_sustained_tbr(self):
        """AID_AWARE with total_tbr=5.0 but sustained_tbr=2.0 → no safety override."""
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=5.0, safety_tier=SafetyTier.MODERATE,
            profile=AID_AWARE, sustained_tbr=2.0,
        )
        # sustained_tbr=2.0 < tbr_l1_target=4.0 → no override
        assert all(r.parameter != 'aggressiveness' for r in recs)

    def test_aid_profile_sustained_above_threshold(self):
        """AID_AWARE with sustained_tbr=5.0 → safety override fires."""
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=6.0, safety_tier=SafetyTier.MODERATE,
            profile=AID_AWARE, sustained_tbr=5.0,
        )
        assert recs[0].parameter == 'aggressiveness'
        assert recs[0].direction == 'decrease'

    def test_cr_adjust_grade_d(self):
        flags = self._default_flags(cr_flag=True)
        recs_d = generate_recommendations(
            flags, Grade.D, overnight_drift=0, max_excursion=80,
            cv=30, total_tbr=2.0, safety_tier=SafetyTier.MODERATE,
            profile=ADA_CLINICAL,
        )
        cr_rec_d = [r for r in recs_d if r.parameter == 'cr'][0]
        assert cr_rec_d.magnitude_pct == 50  # CR_ADJUST_GRADE_D

        recs_b = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=80,
            cv=30, total_tbr=2.0, safety_tier=SafetyTier.MODERATE,
            profile=ADA_CLINICAL,
        )
        cr_rec_b = [r for r in recs_b if r.parameter == 'cr'][0]
        assert cr_rec_b.magnitude_pct == 30  # CR_ADJUST_STANDARD

    def test_profile_name_in_rationale(self):
        flags = self._default_flags()
        recs = generate_recommendations(
            flags, Grade.B, overnight_drift=0, max_excursion=0,
            cv=30, total_tbr=5.0, safety_tier=SafetyTier.HIGH,
            profile=ADA_CLINICAL,
        )
        assert ADA_CLINICAL.name in recs[0].rationale


# ---------------------------------------------------------------------------
# 9. TestTherapyFlags
# ---------------------------------------------------------------------------

class TestTherapyFlags:

    def test_n_flags(self):
        f = TherapyFlags(basal_flag=True, cr_flag=True, isf_flag=False,
                         cv_flag=False, tbr_flag=True)
        assert f.n_flags == 3

    def test_has_safety_issue(self):
        assert TherapyFlags(tbr_flag=True).has_safety_issue is True
        assert TherapyFlags(basal_flag=True).has_safety_issue is False
        assert TherapyFlags().has_safety_issue is False


# ---------------------------------------------------------------------------
# 10. TestHypoEpisode
# ---------------------------------------------------------------------------

class TestHypoEpisode:

    def test_duration_minutes(self):
        ep = HypoEpisode(start_idx=0, end_idx=6, duration_steps=6,
                         nadir_mg_dl=55.0)
        assert ep.duration_minutes == pytest.approx(30.0)

    def test_is_severe(self):
        severe = HypoEpisode(start_idx=0, end_idx=3, duration_steps=3,
                              nadir_mg_dl=50.0)
        assert severe.is_severe is True

        not_severe = HypoEpisode(start_idx=0, end_idx=3, duration_steps=3,
                                  nadir_mg_dl=55.0)
        assert not_severe.is_severe is False

        boundary = HypoEpisode(start_idx=0, end_idx=3, duration_steps=3,
                                nadir_mg_dl=54.0)
        # nadir < 54 is severe; 54 itself is NOT severe
        assert boundary.is_severe is False


# ---------------------------------------------------------------------------
# 11. TestPreconditions
# ---------------------------------------------------------------------------

class TestPreconditions:

    def test_sufficient_data(self):
        p = Preconditions(
            cgm_coverage=0.85, insulin_coverage=0.80,
            n_days=90, n_meals=100, n_corrections=50,
        ).check()
        assert p.sufficient_for_triage is True
        assert p.sufficient_for_full is True

    def test_insufficient_data(self):
        p = Preconditions(
            cgm_coverage=0.85, insulin_coverage=0.80,
            n_days=10, n_meals=5, n_corrections=2,
        ).check()
        assert p.sufficient_for_triage is False
        assert p.sufficient_for_full is False

    def test_analysis_level(self):
        """Derived analysis level from sufficient_for_* fields."""
        def level(pc):
            if pc.sufficient_for_full:
                return 'full'
            if pc.sufficient_for_triage:
                return 'triage'
            return 'insufficient'

        # < 14 days → insufficient
        p1 = Preconditions(
            cgm_coverage=0.9, insulin_coverage=0.9,
            n_days=10, n_meals=5, n_corrections=2,
        ).check()
        assert level(p1) == 'insufficient'

        # 14-89 days → triage (enough for triage but not full)
        p2 = Preconditions(
            cgm_coverage=0.9, insulin_coverage=0.9,
            n_days=30, n_meals=50, n_corrections=20,
        ).check()
        assert level(p2) == 'triage'

        # >= 90 days → full
        p3 = Preconditions(
            cgm_coverage=0.9, insulin_coverage=0.9,
            n_days=100, n_meals=200, n_corrections=80,
        ).check()
        assert level(p3) == 'full'


# ---------------------------------------------------------------------------
# 12. TestTherapyPipeline (integration)
# ---------------------------------------------------------------------------

class TestTherapyPipeline:

    def test_pipeline_init_default_profile(self):
        pipe = TherapyPipeline()
        assert pipe.profile is ADA_CLINICAL

    def test_pipeline_init_custom_profile(self):
        pipe = TherapyPipeline(profile=AID_AWARE)
        assert pipe.profile is AID_AWARE

    def test_load_arrays_and_assess(self):
        pipe = TherapyPipeline()
        g = make_glucose(120.0)
        pipe.load_arrays('test_patient', g, make_zeros(), make_zeros())
        result = pipe.assess('test_patient')
        assert isinstance(result, TherapyAssessment)
        assert result.patient_id == 'test_patient'

    def test_assess_all_in_range_patient(self):
        pipe = TherapyPipeline()
        g = make_glucose(120.0)
        pipe.load_arrays('good', g, make_zeros(), make_zeros())
        a = pipe.assess('good')
        # All 120 → TIR=100, TBR=0 → high score, no safety issues
        assert a.grade in (Grade.A, Grade.B)
        assert a.flags.has_safety_issue is False

    def test_assess_all_low_patient(self):
        pipe = TherapyPipeline()
        g = make_glucose(60.0)
        pipe.load_arrays('low', g, make_zeros(), make_zeros())
        a = pipe.assess('low')
        # All 60 → TBR_L1=100%, safety alert
        assert a.flags.tbr_flag is True
        assert a.safety_tier in (SafetyTier.HIGH, SafetyTier.CRITICAL)

    def test_profile_affects_assessment(self):
        """CV between 36 and 40 → flagged by ADA (cv_target=36) but not AID (cv_target=40)."""
        # Build glucose with CV ≈ 38%
        rng = np.random.RandomState(42)
        n = STEPS_PER_DAY * 14
        mean_g = 120.0
        target_cv = 38.0
        target_std = mean_g * target_cv / 100.0
        g = rng.normal(mean_g, target_std, n).clip(50, 400)

        pipe_ada = TherapyPipeline(profile=ADA_CLINICAL)
        pipe_ada.load_arrays('p1', g.copy(), make_zeros(n), make_zeros(n))
        a_ada = pipe_ada.assess('p1')

        pipe_aid = TherapyPipeline(profile=AID_AWARE)
        pipe_aid.load_arrays('p1', g.copy(), make_zeros(n), make_zeros(n))
        a_aid = pipe_aid.assess('p1')

        # ADA flags cv (cv_target=36), AID does not (cv_target=40)
        actual_cv = a_ada.time_in_ranges.cv
        if 36 <= actual_cv < 40:
            assert a_ada.flags.cv_flag is True
            assert a_aid.flags.cv_flag is False


# ---------------------------------------------------------------------------
# 13. TestPatientReport
# ---------------------------------------------------------------------------

class TestPatientReport:

    @pytest.fixture()
    def report(self):
        pipe = TherapyPipeline(profile=ADA_CLINICAL)
        g = make_glucose(120.0)
        pipe.load_arrays('patient_42', g, make_zeros(), make_zeros())
        return pipe.patient_report('patient_42')

    def test_report_contains_profile_name(self, report):
        text = report.text_summary()
        assert ADA_CLINICAL.name in text

    def test_report_contains_patient_id(self, report):
        text = report.text_summary()
        assert 'patient_42' in text

    def test_report_json_parseable(self, report):
        j = report.to_json()
        data = json.loads(j)
        assert isinstance(data, dict)
        assert 'grade' in data

    def test_report_has_grade(self, report):
        text = report.text_summary()
        assert report.a.grade.value in text


# ---------------------------------------------------------------------------
# 14. TestCohortReport
# ---------------------------------------------------------------------------

class TestCohortReport:

    def test_empty_cohort(self):
        cr = CohortReport([], profile=ADA_CLINICAL)
        assert cr.text_summary() == "No patients assessed."

    def test_cohort_contains_profile_name(self):
        pipe = TherapyPipeline(profile=ADA_CLINICAL)
        for pid in ('a', 'b'):
            pipe.load_arrays(pid, make_glucose(120.0), make_zeros(), make_zeros())
        pipe.assess_all()
        cr = pipe.cohort_report()
        text = cr.text_summary()
        assert ADA_CLINICAL.name in text

    def test_cohort_sorted_by_score(self):
        pipe = TherapyPipeline()
        # Two patients: one good (120), one bad (60) → different scores
        pipe.load_arrays('good', make_glucose(120.0), make_zeros(), make_zeros())
        pipe.load_arrays('bad', make_glucose(60.0), make_zeros(), make_zeros())
        pipe.assess_all()
        cr = pipe.cohort_report()
        scores = [a.v10_score for a in cr.assessments]
        assert scores == sorted(scores)
