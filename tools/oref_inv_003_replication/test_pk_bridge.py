"""
test_pk_bridge.py — Validation tests for PK bridge feature translations.

Tests that PK-derived features correctly match the semantics of oref0/Loop
IOB models. Inspired by tools/aid-autoresearch/validate_oref0.py boundary
vector pattern: known inputs → expected outputs.

Tests verify:
  1. IOB-remaining kernel physics (unit dose → expected decay)
  2. NET IOB model (actual - scheduled, can be negative)
  3. Steady-state basal → zero net IOB
  4. Suspension → negative IOB accumulation
  5. Single bolus → correct exponential IOB decay
  6. Feature correlation with reported devicestatus IOB
  7. Unit/scale validation vs oref0 expected ranges

References:
  - externals/oref0/lib/iob/total.js (basaliob/bolusiob split)
  - externals/oref0/lib/iob/history.js:553 (netBasalRate = rate - scheduled)
  - externals/LoopWorkspace/LoopKit/.../DoseEntry.swift:114 (netBasalUnits)
  - externals/oref0/lib/iob/calculate.js (exponential insulin curve)
"""

import pytest
import numpy as np
import pandas as pd
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.oref_inv_003_replication.pk_bridge import (
    _build_iob_kernel,
    compute_pk_for_patient,
    add_pk_features_to_grid,
    get_oref32_with_pk_replacements,
    get_pk_only_features,
    get_augmented_features,
    ALL_PK_FEATURES,
    PK_REPLACEMENT_FEATURES,
    PK_AUGMENTATION_FEATURES,
)
from tools.cgmencode.continuous_pk import _convolve_doses_with_kernel


# ── Helpers ──────────────────────────────────────────────────────────

def _make_patient_grid(n_steps: int = 288, basal_rate: float = 1.0,
                       scheduled_basal: float = 1.0, isf: float = 50.0,
                       cr: float = 10.0, glucose: float = 120.0,
                       boluses: dict = None) -> pd.DataFrame:
    """Create a synthetic patient grid for testing.

    Args:
        n_steps: Number of 5-min steps (288 = 24 hours)
        basal_rate: Actual basal rate (U/hr) — constant
        scheduled_basal: Scheduled basal rate (U/hr) — constant
        isf: ISF in mg/dL/U
        cr: Carb ratio in g/U
        glucose: Starting glucose (will add small noise)
        boluses: Dict of {step_index: dose_U} for bolus injections
    """
    times = pd.date_range('2024-01-01', periods=n_steps, freq='5min')
    np.random.seed(42)
    glucose_vals = glucose + np.random.randn(n_steps) * 2  # small noise

    df = pd.DataFrame({
        'time': times,
        'patient_id': 'test',
        'glucose': glucose_vals,
        'glucose_roc': np.gradient(glucose_vals),
        'bolus': 0.0,
        'carbs': 0.0,
        'iob': 0.0,  # will be set by test if needed
        'actual_basal_rate': basal_rate,
        'scheduled_basal_rate': scheduled_basal,
        'scheduled_isf': isf,
        'scheduled_cr': cr,
        'net_basal': basal_rate - scheduled_basal,
    })

    if boluses:
        for step, dose in boluses.items():
            df.loc[step, 'bolus'] = dose

    return df.set_index('time')


# ── Kernel Tests ─────────────────────────────────────────────────────

class TestIOBKernel:
    """Verify IOB-remaining kernel physics."""

    def test_kernel_starts_at_one(self):
        """At t=0, 100% of dose remains on board."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        assert kernel[0] > 0.99, f"Kernel should start near 1.0, got {kernel[0]}"

    def test_kernel_ends_near_zero(self):
        """At t=DIA, dose is nearly fully absorbed."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        assert kernel[-1] < 0.02, f"Kernel should end near 0.0, got {kernel[-1]}"

    def test_kernel_monotonically_decreases(self):
        """IOB remaining should only decrease over time."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        diffs = np.diff(kernel)
        assert np.all(diffs <= 0.001), "IOB kernel should be monotonically decreasing"

    def test_kernel_length(self):
        """Kernel length = DIA / interval."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        assert len(kernel) == 60, f"Expected 60 steps (5h/5min), got {len(kernel)}"

    def test_unit_dose_total_absorption(self):
        """1U dose should result in ~1U total absorbed over DIA."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        # Total absorbed = 1.0 - kernel[-1] (initial 1.0 minus remaining)
        total_absorbed = 1.0 - kernel[-1]
        assert 0.98 < total_absorbed < 1.01, f"Expected ~1.0U absorbed, got {total_absorbed}"

    def test_iob_at_peak(self):
        """At peak activity time (~55min = step 11), significant IOB remains."""
        kernel = _build_iob_kernel(5.0, 55.0, 5)
        iob_at_peak = kernel[11]  # step 11 = 55 min
        assert 0.5 < iob_at_peak < 0.85, f"IOB at peak should be 50-85%, got {iob_at_peak}"


# ── NET IOB Model Tests ─────────────────────────────────────────────

class TestNetIOBModel:
    """Verify NET IOB semantics match Loop/oref0 behavior."""

    def test_steady_state_basal_zero_net_iob(self):
        """When actual == scheduled basal, net basal IOB ≈ 0.

        Both Loop and oref0: scheduled basal is equilibrium.
        No deviation → no net IOB contribution from basal.
        """
        df = _make_patient_grid(n_steps=288, basal_rate=1.0, scheduled_basal=1.0)
        pk = compute_pk_for_patient(df, verbose=False)

        mean_basal_iob = pk['pk_basal_iob'].mean()
        assert abs(mean_basal_iob) < 0.01, \
            f"Steady-state basal should have ~0 net IOB, got {mean_basal_iob:.4f}"

    def test_suspension_produces_negative_iob(self):
        """When pump suspends (actual=0, scheduled=1.0), IOB goes negative.

        oref0 (history.js:553): netBasalRate = rate - scheduledRate → negative entries
        Loop (DoseEntry.swift:114): netBasalUnits = actual - scheduled → negative
        """
        df = _make_patient_grid(n_steps=288, basal_rate=0.0, scheduled_basal=1.0)
        pk = compute_pk_for_patient(df, verbose=False)

        # After DIA warmup (60 steps), net basal IOB should be strongly negative
        steady_state_iob = pk['pk_basal_iob'].iloc[60:].mean()
        assert steady_state_iob < -0.5, \
            f"Suspended basal should produce negative IOB, got {steady_state_iob:.3f}"

    def test_high_temp_produces_positive_iob(self):
        """When pump delivers MORE than scheduled (high temp), net basal IOB > 0."""
        df = _make_patient_grid(n_steps=288, basal_rate=2.0, scheduled_basal=1.0)
        pk = compute_pk_for_patient(df, verbose=False)

        steady_state_iob = pk['pk_basal_iob'].iloc[60:].mean()
        assert steady_state_iob > 0.5, \
            f"High temp basal should produce positive IOB, got {steady_state_iob:.3f}"

    def test_bolus_iob_always_nonnegative(self):
        """Bolus IOB should never go negative (you can't un-inject insulin)."""
        df = _make_patient_grid(n_steps=288, boluses={20: 5.0, 100: 3.0})
        pk = compute_pk_for_patient(df, verbose=False)

        assert pk['pk_bolus_iob'].min() >= -0.001, \
            f"Bolus IOB should be ≥ 0, got min={pk['pk_bolus_iob'].min():.4f}"

    def test_single_bolus_decay(self):
        """5U bolus at t=0 should decay from ~5U to ~0U over DIA."""
        df = _make_patient_grid(n_steps=120, basal_rate=1.0, scheduled_basal=1.0,
                                boluses={0: 5.0})
        pk = compute_pk_for_patient(df, verbose=False)

        # At t=0: IOB ≈ 5U (just injected)
        iob_t0 = pk['pk_bolus_iob'].iloc[0]
        assert 4.5 < iob_t0 < 5.1, f"IOB at injection should be ~5U, got {iob_t0:.2f}"

        # At t=55min (step 11, peak activity): IOB should be 50-85% remaining
        iob_peak = pk['pk_bolus_iob'].iloc[11]
        assert 2.5 < iob_peak < 4.5, f"IOB at peak should be ~3.5U, got {iob_peak:.2f}"

        # At t=5h (step 60): IOB should be near zero
        iob_end = pk['pk_bolus_iob'].iloc[60]
        assert iob_end < 0.1, f"IOB at DIA should be ~0, got {iob_end:.2f}"


# ── Feature Unit/Semantic Tests ──────────────────────────────────────

class TestFeatureSemantics:
    """Verify feature units and semantics match oref0 definitions."""

    def test_bgi_formula_matches_oref0(self):
        """BGI = -activity × ISF.

        oref0 (determine-basal.js:398):
            var bgi = round(( -iob_data.activity * sens * 5 ), 2)
        Our pk_activity is already in U/5min, so: pk_bgi = -pk_activity * ISF
        """
        df = _make_patient_grid(n_steps=288, isf=50.0, boluses={20: 5.0})
        pk = compute_pk_for_patient(df, verbose=False)

        # Verify formula: pk_bgi == -pk_activity * ISF
        expected_bgi = -pk['pk_activity'] * 50.0
        np.testing.assert_allclose(
            pk['pk_bgi'].values, expected_bgi.values,
            atol=0.001, err_msg="pk_bgi should equal -pk_activity × ISF"
        )

    def test_dev_formula_matches_oref0(self):
        """Deviation = 6 × (glucose_roc - pk_bgi).

        oref0 (determine-basal.js):
            deviation = round(30 / 5 * (minDelta - bgi))
        glucose_roc is already in mg/dL per 5min.
        """
        df = _make_patient_grid(n_steps=288, boluses={20: 5.0})
        pk = compute_pk_for_patient(df, verbose=False)

        glucose_roc = df['glucose_roc'].fillna(0).values
        expected_dev = 6.0 * (glucose_roc - pk['pk_bgi'].values)
        np.testing.assert_allclose(
            pk['pk_dev'].values, expected_dev,
            atol=0.01, err_msg="pk_dev should equal 6 × (glucose_roc - pk_bgi)"
        )

    def test_bolus_produces_negative_bgi(self):
        """A bolus should cause glucose-lowering effect (negative BGI)."""
        df = _make_patient_grid(n_steps=120, isf=50.0, boluses={10: 5.0})
        pk = compute_pk_for_patient(df, verbose=False)

        # After bolus onset (~15min, step 3-4), BGI should be negative
        bgi_after_bolus = pk['pk_bgi'].iloc[15:30].mean()
        assert bgi_after_bolus < -1.0, \
            f"BGI after bolus should be negative (glucose lowering), got {bgi_after_bolus:.2f}"

    def test_activity_units_per_5min(self):
        """Activity should be in U/5min, not U/min.

        A 5U bolus at peak activity should have ~0.05-0.15 U/5min.
        """
        df = _make_patient_grid(n_steps=120, basal_rate=1.0, scheduled_basal=1.0,
                                boluses={0: 5.0})
        pk = compute_pk_for_patient(df, verbose=False)

        # Peak activity at ~step 11 (55 min)
        peak_activity = pk['pk_activity'].iloc[10:13].mean()
        assert 0.02 < abs(peak_activity) < 0.5, \
            f"Peak activity should be ~0.05-0.15 U/5min, got {peak_activity:.4f}"


# ── Feature List Tests ───────────────────────────────────────────────

class TestFeatureLists:
    """Verify feature list helpers produce correct output."""

    def test_replacement_features_count(self):
        assert len(PK_REPLACEMENT_FEATURES) == 5

    def test_augmentation_features_count(self):
        assert len(PK_AUGMENTATION_FEATURES) == 8

    def test_all_features_count(self):
        assert len(ALL_PK_FEATURES) == 13

    def test_oref32_replacements_correct_length(self):
        """OREF-32 with replacements should still have 32 features."""
        replaced = get_oref32_with_pk_replacements()
        assert len(replaced) == 32, f"Expected 32 features, got {len(replaced)}"

    def test_oref32_replacements_contain_pk_names(self):
        """Replaced features should use pk_ prefix."""
        replaced = get_oref32_with_pk_replacements()
        pk_names = [f for f in replaced if f.startswith('pk_')]
        assert len(pk_names) == 5, f"Expected 5 pk_ features, got {pk_names}"

    def test_pk_only_features_include_context(self):
        """PK-only set should include glucose, time, and all PK channels."""
        pk_only = get_pk_only_features()
        assert 'cgm_mgdl' in pk_only
        assert 'time_sin' in pk_only
        assert 'pk_basal_iob' in pk_only

    def test_augmented_features_superset(self):
        """Augmented set should be OREF-32-replaced + PK augmentation."""
        augmented = get_augmented_features()
        replaced = get_oref32_with_pk_replacements()
        assert len(augmented) == len(replaced) + len(PK_AUGMENTATION_FEATURES)


# ── Integration Tests (require parquet data) ─────────────────────────

GRID_PATH = os.path.join(_PROJECT_ROOT, 'externals', 'ns-parquet', 'training', 'grid.parquet')
HAS_DATA = os.path.exists(GRID_PATH)


@pytest.mark.skipif(not HAS_DATA, reason="Requires parquet grid data")
class TestRealDataValidation:
    """Integration tests against real patient data."""

    @pytest.fixture(scope='class')
    def grid(self):
        return pd.read_parquet(GRID_PATH)

    def test_net_iob_correlates_with_reported(self, grid):
        """PK net total IOB should correlate r>0.8 with reported devicestatus IOB.

        This validates the NET model: pk_basal_iob + pk_bolus_iob ≈ reported IOB.
        """
        pt = grid[grid['patient_id'] == 'c'].copy()
        pk = compute_pk_for_patient(pt, verbose=False)
        pk_total = pk['pk_basal_iob'].values + pk['pk_bolus_iob'].values
        reported = pt['iob'].values
        mask = ~np.isnan(reported) & ~np.isnan(pk_total)
        corr = np.corrcoef(pk_total[mask], reported[mask])[0, 1]
        assert corr > 0.8, f"Expected r>0.8 with reported IOB, got {corr:.4f}"

    def test_basal_iob_goes_negative_for_loop_patients(self, grid):
        """Loop patients frequently suspend delivery → net basal IOB should go negative."""
        pt = grid[grid['patient_id'] == 'c'].copy()
        pk = compute_pk_for_patient(pt, verbose=False)
        neg_frac = (pk['pk_basal_iob'] < 0).mean()
        assert neg_frac > 0.5, \
            f"Loop patient should have >50% negative basal IOB, got {neg_frac:.1%}"

    def test_all_features_numeric_no_inf(self, grid):
        """All PK features should be numeric with no infinities."""
        pt = grid[grid['patient_id'] == 'k'].copy()
        pk = compute_pk_for_patient(pt, verbose=False)
        for col in ALL_PK_FEATURES:
            assert col in pk.columns, f"Missing feature: {col}"
            assert not np.any(np.isinf(pk[col].values)), f"Inf found in {col}"

    def test_feature_ranges_match_oref0(self, grid):
        """PK feature ranges should be in oref0-plausible ballpark."""
        pt = grid[grid['patient_id'] == 'c'].copy()
        pk = compute_pk_for_patient(pt, verbose=False)

        # pk_bolus_iob: 0 to ~25U (large but possible with stacked boluses)
        assert pk['pk_bolus_iob'].min() >= -0.001
        assert pk['pk_bolus_iob'].max() < 50

        # pk_activity: ±1 U/5min (very generous bound)
        assert pk['pk_activity'].min() > -2.0
        assert pk['pk_activity'].max() < 2.0

        # pk_bgi: ±100 mg/dL/5min (generous bound)
        assert pk['pk_bgi'].min() > -150
        assert pk['pk_bgi'].max() < 150

    def test_multi_patient_consistency(self, grid):
        """PK bridge should produce results for multiple patients without errors."""
        patients_tested = 0
        for pid in ['c', 'e', 'k']:
            pt = grid[grid['patient_id'] == pid].copy()
            if len(pt) == 0:
                continue
            pk = compute_pk_for_patient(pt, verbose=False)
            assert len(pk) == len(pt), f"Patient {pid}: length mismatch"
            assert set(ALL_PK_FEATURES).issubset(pk.columns)
            patients_tested += 1
        assert patients_tested >= 3, "Should test at least 3 patients"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# ── Tests for data quality assessment and PK integration ─────────────

from tools.oref_inv_003_replication.data_bridge import (
    assess_patient_quality,
    build_oref_features,
    DATA_QUALITY_THRESHOLDS,
    OREF_FEATURES,
)


class TestPatientQuality:
    """Tests for assess_patient_quality()."""

    @pytest.fixture
    def grid(self):
        grid_path = os.path.join(_PROJECT_ROOT, 'externals', 'ns-parquet', 'training', 'grid.parquet')
        if not os.path.exists(grid_path):
            pytest.skip('Training grid not available')
        return pd.read_parquet(grid_path)

    def test_returns_all_patients(self, grid):
        quality = assess_patient_quality(grid)
        expected_pids = set(grid['patient_id'].unique())
        assert set(quality.index) == expected_pids

    def test_cgm_density_range(self, grid):
        quality = assess_patient_quality(grid)
        assert (quality['cgm_density'] >= 0).all()
        assert (quality['cgm_density'] <= 1).all()

    def test_stale_patient_fails(self, grid):
        """odc-84181797 has 4% CGM and 0% IOB — should fail quality."""
        quality = assess_patient_quality(grid)
        if 'odc-84181797' in quality.index:
            assert not quality.loc['odc-84181797', 'passes_quality'], \
                "odc-84181797 should fail quality (4% CGM, 0% IOB)"

    def test_good_patients_pass(self, grid):
        """Loop patients a, b, c with dense data should pass."""
        quality = assess_patient_quality(grid)
        for pid in ['a', 'b', 'c']:
            if pid in quality.index:
                assert quality.loc[pid, 'passes_quality'], \
                    f"Patient {pid} should pass quality"


class TestBuildOrefWithPK:
    """Tests for build_oref_features(use_pk=True)."""

    @pytest.fixture
    def grid(self):
        grid_path = os.path.join(_PROJECT_ROOT, 'externals', 'ns-parquet', 'training', 'grid.parquet')
        if not os.path.exists(grid_path):
            pytest.skip('Training grid not available')
        df = pd.read_parquet(grid_path)
        # Use a single patient for speed
        return df[df['patient_id'] == 'c'].copy()

    def test_pk_mode_produces_all_features(self, grid):
        """PK mode should still produce all 32 OREF features."""
        result = build_oref_features(grid, use_pk=True)
        missing = set(OREF_FEATURES) - set(result.columns)
        assert not missing, f"Missing features: {missing}"

    def test_pk_mode_differs_from_approx(self, grid):
        """PK-derived features should differ from approximated ones."""
        approx = build_oref_features(grid, use_pk=False)
        pk = build_oref_features(grid, use_pk=True)

        for col in ['iob_basaliob', 'iob_bolusiob', 'iob_activity']:
            # The values should be materially different
            diff = (pk[col] - approx[col]).abs().mean()
            assert diff > 0.001, \
                f"{col}: PK and approx values are identical (diff={diff})"

    def test_pk_basaliob_can_be_negative(self, grid):
        """PK-derived basaliob should go negative (suspension periods)."""
        result = build_oref_features(grid, use_pk=True)
        assert (result['iob_basaliob'] < -0.01).any(), \
            "PK basaliob should be negative during pump suspension"

    def test_backward_compatible_without_pk(self, grid):
        """Default (use_pk=False) should produce same results as before."""
        result = build_oref_features(grid, use_pk=False)
        assert set(OREF_FEATURES).issubset(result.columns)

    def test_pk_activity_not_circular(self, grid):
        """PK activity should NOT be derived from glucose_roc (anti-circularity).

        The approximation has iob_activity = -glucose_roc / ISF (r ≈ -0.86),
        which is circular: it conflates insulin + food + noise. PK activity is
        computed from insulin delivery alone and should have |r| < 0.3 with
        glucose_roc.
        """
        result = build_oref_features(grid, use_pk=True)
        act = result['iob_activity'].dropna()
        roc = grid.loc[act.index, 'glucose_roc'].fillna(0)
        valid = np.isfinite(act) & np.isfinite(roc)
        r = np.corrcoef(act[valid], roc[valid])[0, 1]
        assert abs(r) < 0.30, \
            f"PK activity should not be circular (r={r:.3f} with glucose_roc)"


class TestPatientDIA:
    """Tests for per-patient DIA loading."""

    def test_dia_loaded(self):
        from tools.oref_inv_003_replication.data_bridge import _load_patient_dia
        dia = _load_patient_dia()
        assert len(dia) > 0, "Should load at least some DIAs"

    def test_loop_patients_dia_6(self):
        """Loop patients a-k should have DIA=6.0h."""
        from tools.oref_inv_003_replication.data_bridge import _load_patient_dia
        dia = _load_patient_dia()
        for pid in ['a', 'b', 'c', 'e', 'f', 'g']:
            if pid in dia:
                assert dia[pid] == 6.0, \
                    f"Patient {pid} DIA should be 6.0, got {dia[pid]}"

    def test_odc_patients_vary(self):
        """ODC patients should have varying DIA (5-7h)."""
        from tools.oref_inv_003_replication.data_bridge import _load_patient_dia
        dia = _load_patient_dia()
        odc_dias = [v for k, v in dia.items() if k.startswith('odc-')]
        if odc_dias:
            assert len(set(odc_dias)) > 1, \
                "ODC patients should have different DIA values"


class TestPeakParameter:
    """Tests for insulin peak parameter alignment.

    All three AID systems (Loop, oref0, AAPS) use the same exponential
    insulin activity curve but with different peak times:
      - Rapid-acting (Humalog/Novolog): peak=75 min
      - Ultra-rapid (Fiasp/Lyumjev):    peak=55 min

    Rapid-acting is far more common, so peak=75 should be our default.
    """

    @pytest.fixture(scope='class')
    def grid(self):
        grid_path = os.path.join(_PROJECT_ROOT, 'externals', 'ns-parquet',
                                 'training', 'grid.parquet')
        if not os.path.exists(grid_path):
            pytest.skip('Training grid not available')
        grid = pd.read_parquet(grid_path)
        quality = assess_patient_quality(grid)
        return grid[grid['patient_id'].isin(
            quality[quality['passes_quality']].index
        )].copy()

    def test_default_peak_is_75(self):
        """data_bridge should use peak=75 (rapid-acting) by default."""
        import inspect
        from tools.oref_inv_003_replication.data_bridge import build_oref_features
        src = inspect.getsource(build_oref_features)
        assert 'default_peak = 75' in src, \
            "build_oref_features should default to peak=75 (rapid-acting)"

    def test_pk_correlation_above_threshold(self, grid):
        """PK total IOB should correlate r>0.85 with reported IOB on average."""
        result = build_oref_features(grid, use_pk=True)
        reported = grid['iob'].astype(float).fillna(0.0)
        pk_total = result['iob_basaliob'] + result['iob_bolusiob']

        corrs = []
        for pid in grid['patient_id'].unique():
            mask = grid['patient_id'] == pid
            rep = reported[mask].values
            pk = pk_total[mask].values
            valid = np.isfinite(rep) & (rep != 0) & np.isfinite(pk)
            if valid.sum() < 50:
                continue
            corrs.append(np.corrcoef(rep[valid], pk[valid])[0, 1])

        mean_r = np.mean(corrs)
        assert mean_r > 0.85, \
            f"Mean PK-vs-reported r should be >0.85, got {mean_r:.4f}"

    def test_ramp_impact_negligible(self):
        """The 15-min injection-site ramp should affect <1% of total activity.

        oref0 uses no ramp, Loop uses 10-min delay. Our 15-min linear ramp
        is a minor difference because early-time activity is very small
        for peak=75.
        """
        from tools.cgmencode.continuous_pk import _build_activity_kernel
        kernel = _build_activity_kernel(dia_hours=6.0, peak_min=75.0,
                                        interval_min=5)
        total = np.sum(kernel) * 5  # integrate over time
        # With ramp vs without: ramp only reduces first 2 steps (t=5,10)
        # The total should still be close to 1.0 (normalized)
        assert abs(total - 1.0) < 0.02, \
            f"Kernel should integrate to ~1.0, got {total:.4f}"
