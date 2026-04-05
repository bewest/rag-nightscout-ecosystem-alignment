#!/usr/bin/env python3
"""
test_fda_features_gpu.py — Tests for GPU-accelerated FDA features.

Verifies numerical agreement between fda_features.py (scikit-fda/CPU)
and fda_features_gpu.py (PyTorch/GPU) implementations.

Usage:
    python -m pytest tools/cgmencode/test_fda_features_gpu.py -v
    python tools/cgmencode/test_fda_features_gpu.py           # standalone
"""

import sys
import time
import numpy as np
import torch
import pytest
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cgmencode.fda_features as cpu_fda
import cgmencode.fda_features_gpu as gpu_fda


# ── Test Fixtures ─────────────────────────────────────────────────────

def _make_test_data(n_samples=200, n_points=24, seed=42):
    """Generate realistic CGM-like test data (normalized 0-1)."""
    rng = np.random.RandomState(seed)
    t = np.linspace(0, 2 * np.pi, n_points)
    data = np.zeros((n_samples, n_points), dtype=np.float64)
    for i in range(n_samples):
        base = 0.3 + 0.15 * rng.randn()
        amp = 0.1 + 0.05 * rng.randn()
        phase = rng.uniform(0, 2 * np.pi)
        noise = rng.randn(n_points) * 0.02
        data[i] = base + amp * np.sin(t + phase) + noise
    data = np.clip(data, 0.05, 0.95)
    return data


def _make_multichannel_data(n_samples=200, n_points=24, n_channels=3,
                            seed=42):
    """Generate multichannel test data."""
    rng = np.random.RandomState(seed)
    data = np.zeros((n_samples, n_points, n_channels), dtype=np.float64)
    data[:, :, 0] = _make_test_data(n_samples, n_points, seed)
    for ch in range(1, n_channels):
        data[:, :, ch] = rng.randn(n_samples, n_points) * 0.1 + 0.5
    return data


@pytest.fixture
def test_data():
    return _make_test_data()


@pytest.fixture
def test_data_large():
    return _make_test_data(n_samples=1000, n_points=48)


@pytest.fixture
def multichannel_data():
    return _make_multichannel_data()


DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ── B-spline Smoothing Tests ─────────────────────────────────────────

class TestBsplineSmooth:
    def test_coefficients_shape(self, test_data):
        """GPU bspline returns correct coefficient shape."""
        n_basis = 10
        result = gpu_fda.bspline_smooth(test_data, n_basis=n_basis,
                                        device=DEVICE)
        assert result['coefficients'].shape == (200, n_basis)
        assert result['coefficients'].dtype == np.float32

    def test_roundtrip_low_error(self, test_data):
        """B-spline round-trip error should be small for near-interpolation."""
        n_basis = test_data.shape[1] - 2  # near-interpolation
        rt = gpu_fda.bspline_roundtrip_error(test_data, n_basis=n_basis,
                                             device=DEVICE)
        assert rt['mae'] < 0.01, f"Round-trip MAE too high: {rt['mae']}"

    def test_agrees_with_cpu(self, test_data):
        """GPU coefficients should be close to CPU (scikit-fda) coefficients."""
        n_basis = 12
        cpu_coeffs = cpu_fda.bspline_coefficients(test_data, n_basis=n_basis)
        gpu_coeffs = gpu_fda.bspline_coefficients(test_data, n_basis=n_basis,
                                                  device=DEVICE)
        # Both solve same least-squares problem; tolerance for float precision
        # The basis construction may differ slightly, so we compare
        # reconstruction error instead of raw coefficients
        cpu_rt = cpu_fda.bspline_roundtrip_error(test_data, n_basis=n_basis)
        gpu_rt = gpu_fda.bspline_roundtrip_error(test_data, n_basis=n_basis,
                                                 device=DEVICE)
        assert abs(cpu_rt['mae'] - gpu_rt['mae']) < 0.005, \
            f"Round-trip MAE differs: CPU={cpu_rt['mae']:.6f} GPU={gpu_rt['mae']:.6f}"

    def test_default_n_basis(self, test_data):
        """Default n_basis should be n_points - 2."""
        result = gpu_fda.bspline_smooth(test_data, device=DEVICE)
        expected_n_basis = max(5, test_data.shape[1] - 2)
        assert result['n_basis'] == expected_n_basis


# ── Functional Derivatives Tests ──────────────────────────────────────

class TestFunctionalDerivatives:
    def test_output_shape(self, test_data):
        """Derivatives should have same shape as input."""
        d1 = gpu_fda.functional_derivatives(test_data, order=1, device=DEVICE)
        assert d1.shape == test_data.shape
        assert d1.dtype == np.float32

    def test_second_derivative(self, test_data):
        """Second derivative should also work."""
        d2 = gpu_fda.functional_derivatives(test_data, order=2, device=DEVICE)
        assert d2.shape == test_data.shape
        assert np.all(np.isfinite(d2))

    def test_agrees_with_cpu(self, test_data):
        """GPU derivatives should be close to CPU (scikit-fda) derivatives."""
        n_basis = 12
        cpu_d1 = cpu_fda.functional_derivatives(test_data, order=1,
                                                n_basis=n_basis)
        gpu_d1 = gpu_fda.functional_derivatives(test_data, order=1,
                                                n_basis=n_basis, device=DEVICE)
        # Allow tolerance for different basis construction approaches
        corr = np.corrcoef(cpu_d1.ravel(), gpu_d1.ravel())[0, 1]
        assert corr > 0.95, f"Derivative correlation too low: {corr:.4f}"

    def test_sine_derivative(self):
        """Known derivative: d/dt sin(t) = cos(t)."""
        n_pts = 48
        t = np.linspace(0, 2 * np.pi, n_pts)
        data = np.sin(t).reshape(1, -1)
        d1 = gpu_fda.functional_derivatives(data, order=1,
                                            grid_points=t, device=DEVICE)
        expected = np.cos(t)
        # Exclude endpoints (B-spline edge effects)
        inner = slice(3, -3)
        mae = np.abs(d1[0, inner] - expected[inner]).mean()
        assert mae < 0.15, f"Sine derivative MAE too high: {mae:.4f}"


# ── FPCA Tests ────────────────────────────────────────────────────────

class TestFPCA:
    def test_scores_shape(self, test_data):
        """FPCA scores should have (n_samples, n_components) shape."""
        scores, info = gpu_fda.fpca_scores(test_data, n_components=5,
                                           device=DEVICE)
        assert scores.shape == (200, 5)
        assert scores.dtype == np.float32

    def test_variance_explained_sums(self, test_data):
        """Variance ratios should sum to ≤ 1."""
        _, info = gpu_fda.fpca_scores(test_data, n_components=10,
                                      device=DEVICE)
        total = info['explained_variance_ratio_'].sum()
        assert total <= 1.0 + 1e-5, f"Variance ratios sum to {total}"

    def test_agrees_with_cpu_variance(self, test_data):
        """GPU and CPU FPCA should explain similar variance."""
        cpu_var = cpu_fda.fpca_variance_explained(test_data, max_components=5)
        gpu_var = gpu_fda.fpca_variance_explained(test_data, max_components=5,
                                                  device=DEVICE)
        cpu_90 = cpu_var['n_for_90']
        gpu_90 = gpu_var['n_for_90']
        # Same number of components for 90% variance (±1)
        assert abs(cpu_90 - gpu_90) <= 1, \
            f"90% variance components differ: CPU={cpu_90} GPU={gpu_90}"

    def test_reconstruction_quality(self, test_data):
        """FPCA reconstruction from scores should be close to original."""
        n_comp = 10
        scores, info = gpu_fda.fpca_scores(test_data, n_components=n_comp,
                                           device=DEVICE)
        # Reconstruct: X_hat = scores @ components + mean
        recon = scores @ info['components_'] + info['mean_']
        mae = np.abs(test_data.astype(np.float32) - recon).mean()
        assert mae < 0.1, f"FPCA reconstruction MAE too high: {mae:.4f}"

    def test_smooth_first_flag(self, test_data):
        """smooth_first=False should also work."""
        scores, info = gpu_fda.fpca_scores(test_data, n_components=3,
                                           smooth_first=False, device=DEVICE)
        assert scores.shape == (200, 3)


# ── Glucodensity Tests ────────────────────────────────────────────────

class TestGlucodensity:
    def test_output_shape(self, test_data):
        """Glucodensity should return (n_samples, n_bins)."""
        gd = gpu_fda.glucodensity(test_data, n_bins=50, device=DEVICE)
        assert gd.shape == (200, 50)

    def test_non_negative(self, test_data):
        """Densities should be non-negative."""
        gd = gpu_fda.glucodensity(test_data, device=DEVICE)
        assert np.all(gd >= -1e-6), "Negative densities found"

    def test_finite(self, test_data):
        """All outputs should be finite."""
        gd = gpu_fda.glucodensity(test_data, device=DEVICE)
        assert np.all(np.isfinite(gd)), "Non-finite densities found"

    def test_handles_nan(self):
        """Should handle NaN values gracefully."""
        data = _make_test_data(n_samples=50, n_points=24)
        data[0, 5:10] = np.nan  # some NaNs
        data[1, :] = np.nan     # all NaN (degenerate)
        gd = gpu_fda.glucodensity(data, device=DEVICE)
        assert gd.shape == (50, 50)
        assert np.all(np.isfinite(gd))

    def test_agrees_with_cpu(self, test_data):
        """GPU and CPU glucodensity should be similar.

        Note: exact agreement is not expected because Scott's bandwidth
        estimation may differ slightly between scipy and our implementation.
        We check correlation and peak location agreement.
        """
        cpu_gd = cpu_fda.glucodensity(test_data, n_bins=50)
        gpu_gd = gpu_fda.glucodensity(test_data, n_bins=50, device=DEVICE)

        # Shape must match
        assert cpu_gd.shape == gpu_gd.shape

        # Peak locations should agree for most samples
        cpu_peaks = cpu_gd.argmax(axis=1)
        gpu_peaks = gpu_gd.argmax(axis=1)
        peak_agreement = (np.abs(cpu_peaks - gpu_peaks) <= 3).mean()
        assert peak_agreement > 0.8, \
            f"Peak agreement only {peak_agreement:.1%}"

        # Correlation of density profiles
        valid = (cpu_gd.sum(axis=1) > 0) & (gpu_gd.sum(axis=1) > 0)
        if valid.sum() > 10:
            corr = np.corrcoef(cpu_gd[valid].ravel(),
                               gpu_gd[valid].ravel())[0, 1]
            assert corr > 0.85, f"Density correlation too low: {corr:.4f}"

    def test_custom_range(self, test_data):
        """Custom glucose range should work."""
        gd = gpu_fda.glucodensity(test_data, n_bins=30,
                                  glucose_range=(0.1, 0.9), device=DEVICE)
        assert gd.shape == (200, 30)


# ── L² Distance Tests ────────────────────────────────────────────────

class TestL2Distance:
    def test_output_shape(self, test_data):
        """L2 distance should return (n_samples,) array."""
        dists = gpu_fda.l2_distance_to_mean(test_data, device=DEVICE)
        assert dists.shape == (200,)
        assert dists.dtype == np.float32

    def test_non_negative(self, test_data):
        """Distances should be non-negative."""
        dists = gpu_fda.l2_distance_to_mean(test_data, device=DEVICE)
        assert np.all(dists >= 0), "Negative distances found"

    def test_mean_has_zero_distance(self):
        """The mean itself should have near-zero distance."""
        data = _make_test_data(n_samples=100, n_points=24)
        mean_curve = data.mean(axis=0, keepdims=True)
        # Add mean as a sample
        data_with_mean = np.concatenate([data, mean_curve], axis=0)
        dists = gpu_fda.l2_distance_to_mean(data_with_mean, device=DEVICE)
        # Last sample (the mean) should be very close to 0
        # Not exactly 0 because recomputed mean includes itself
        assert dists[-1] < dists.mean() * 0.1, \
            f"Mean distance {dists[-1]:.6f} not near zero"

    def test_agrees_with_cpu(self, test_data):
        """GPU and CPU L2 distances should be correlated.

        Note: absolute values may differ due to different L2 integration
        approaches (scikit-fda vs torch), but ranking should agree.
        """
        cpu_dists = cpu_fda.l2_distance_to_mean(test_data)
        gpu_dists = gpu_fda.l2_distance_to_mean(test_data, device=DEVICE)

        # Rank correlation (Spearman)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(cpu_dists, gpu_dists)
        assert corr > 0.95, f"Rank correlation too low: {corr:.4f}"

    def test_with_custom_grid(self, test_data):
        """Non-uniform grid spacing should work."""
        grid = np.sort(np.random.RandomState(42).uniform(
            0, 10, test_data.shape[1]))
        dists = gpu_fda.l2_distance_to_mean(test_data, grid_points=grid,
                                            device=DEVICE)
        assert dists.shape == (200,)
        assert np.all(np.isfinite(dists))


# ── Functional Depth Tests ────────────────────────────────────────────

class TestFunctionalDepth:
    def test_output_shape(self, test_data):
        """Depth should return (n_samples,) array."""
        depths = gpu_fda.functional_depth(test_data, device=DEVICE)
        assert depths.shape == (200,)

    def test_bounded_01(self, test_data):
        """Depth values should be in [0, 1]."""
        depths = gpu_fda.functional_depth(test_data, device=DEVICE)
        assert np.all(depths >= -0.01) and np.all(depths <= 1.01), \
            f"Depths out of range: [{depths.min():.4f}, {depths.max():.4f}]"

    def test_outlier_has_low_depth(self):
        """An obvious outlier should have lower depth than typical curves."""
        data = _make_test_data(n_samples=100, n_points=24)
        # Add an extreme outlier
        outlier = np.ones((1, 24)) * 0.95  # far from typical ~0.3
        data_with_outlier = np.concatenate([data, outlier], axis=0)
        depths = gpu_fda.functional_depth(data_with_outlier, device=DEVICE)
        median_depth = np.median(depths[:-1])
        outlier_depth = depths[-1]
        assert outlier_depth < median_depth, \
            f"Outlier depth {outlier_depth:.4f} >= median {median_depth:.4f}"

    def test_agrees_with_cpu_ranking(self, test_data):
        """GPU depth ranking should agree with CPU (scikit-fda) ranking."""
        # Use smaller sample for CPU speed
        small = test_data[:50]
        cpu_depths = cpu_fda.functional_depth(small)
        gpu_depths = gpu_fda.functional_depth(small, device=DEVICE)

        from scipy.stats import spearmanr
        corr, _ = spearmanr(cpu_depths, gpu_depths)
        assert corr > 0.85, f"Depth rank correlation too low: {corr:.4f}"

    def test_high_fidelity_vs_cpu(self):
        """GPU depth should closely match scikit-fda values (same algorithm)."""
        data = _make_test_data(n_samples=80, n_points=24)
        cpu_depths = cpu_fda.functional_depth(data)
        gpu_depths = gpu_fda.functional_depth(data, device=DEVICE)
        mae = np.abs(cpu_depths - gpu_depths).mean()
        assert mae < 0.05, f"Depth MAE vs scikit-fda: {mae:.4f} (>0.05)"


# ── High-fidelity agreement tests ────────────────────────────────────

class TestHighFidelity:
    """Verify numerical closeness to scikit-fda, not just correlation."""

    def test_l2_distance_close(self):
        """GPU L2 values should be within 10% of scikit-fda values."""
        data = _make_test_data(n_samples=100, n_points=24)
        cpu_dists = cpu_fda.l2_distance_to_mean(data)
        gpu_dists = gpu_fda.l2_distance_to_mean(data, device=DEVICE)
        # Relative error
        rel_err = np.abs(cpu_dists - gpu_dists) / (cpu_dists + 1e-8)
        mean_rel = rel_err.mean()
        assert mean_rel < 0.10, \
            f"L2 mean relative error: {mean_rel:.4f} (>10%)"

    def test_fpca_variance_close(self):
        """GPU FPCA should explain nearly identical variance ratios."""
        data = _make_test_data(n_samples=200, n_points=24)
        cpu_var = cpu_fda.fpca_variance_explained(data, max_components=5)
        gpu_var = gpu_fda.fpca_variance_explained(data, max_components=5,
                                                  device=DEVICE)
        cpu_cum = np.array(cpu_var['cumulative_variance'])
        gpu_cum = np.array(gpu_var['cumulative_variance'])
        mae = np.abs(cpu_cum - gpu_cum).mean()
        assert mae < 0.05, \
            f"Cumulative variance MAE: {mae:.4f} (>0.05)"

    def test_depth_values_close(self):
        """GPU depth values should be close to scikit-fda values."""
        data = _make_test_data(n_samples=80, n_points=24)
        cpu_depths = cpu_fda.functional_depth(data)
        gpu_depths = gpu_fda.functional_depth(data, device=DEVICE)
        mae = np.abs(cpu_depths - gpu_depths).mean()
        assert mae < 0.05, f"Depth MAE: {mae:.4f} (>0.05)"


# ── fda_encode Integration Tests ──────────────────────────────────────

class TestFdaEncode:
    def test_all_methods(self, multichannel_data):
        """All encoding methods should produce valid output."""
        methods_shapes = {
            'bspline_coeffs': (200,),  # (200, n_basis)
            'fpca': (200, 5),
            'glucodensity': (200, 50),
            'derivatives': (200, 24),
            'depth': (200,),
            'l2_dist': (200,),
        }
        for method in methods_shapes:
            result = gpu_fda.fda_encode(multichannel_data, method=method,
                                        device=DEVICE)
            assert np.all(np.isfinite(result)), \
                f"Non-finite values in {method}"

    def test_multichannel(self, multichannel_data):
        """Multichannel encoding should concatenate correctly."""
        result = gpu_fda.fda_encode_multichannel(
            multichannel_data, method='fpca', channels=[0, 1],
            n_components=3, device=DEVICE)
        assert result.shape == (200, 6)  # 3 components × 2 channels

    def test_2d_input(self, test_data):
        """2D input (no channel dim) should work."""
        result = gpu_fda.fda_encode(test_data, method='glucodensity',
                                    device=DEVICE)
        assert result.shape == (200, 50)

    def test_invalid_method(self, test_data):
        """Invalid method should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown FDA method"):
            gpu_fda.fda_encode(test_data, method='invalid', device=DEVICE)


# ── Performance Benchmark ─────────────────────────────────────────────

class TestPerformance:
    """Performance comparison (not strict assertions — just reporting)."""

    @pytest.mark.slow
    def test_glucodensity_speedup(self):
        """GPU glucodensity should be faster than CPU for large data."""
        data = _make_test_data(n_samples=2000, n_points=24)

        t0 = time.time()
        cpu_gd = cpu_fda.glucodensity(data, n_bins=50)
        cpu_time = time.time() - t0

        t0 = time.time()
        gpu_gd = gpu_fda.glucodensity(data, n_bins=50, device=DEVICE)
        gpu_time = time.time() - t0

        speedup = cpu_time / max(gpu_time, 1e-6)
        print(f"\n  Glucodensity (2000 samples): "
              f"CPU={cpu_time:.2f}s, GPU={gpu_time:.2f}s, "
              f"speedup={speedup:.1f}×")
        # Just verify it completed and produced valid output
        assert np.all(np.isfinite(gpu_gd))

    @pytest.mark.slow
    def test_l2_distance_speedup(self):
        """GPU L2 distance should be faster than CPU for large data."""
        data = _make_test_data(n_samples=2000, n_points=24)

        t0 = time.time()
        cpu_dists = cpu_fda.l2_distance_to_mean(data)
        cpu_time = time.time() - t0

        t0 = time.time()
        gpu_dists = gpu_fda.l2_distance_to_mean(data, device=DEVICE)
        gpu_time = time.time() - t0

        speedup = cpu_time / max(gpu_time, 1e-6)
        print(f"\n  L2 Distance (2000 samples): "
              f"CPU={cpu_time:.2f}s, GPU={gpu_time:.2f}s, "
              f"speedup={speedup:.1f}×")
        assert np.all(np.isfinite(gpu_dists))

    @pytest.mark.slow
    def test_full_pipeline_speedup(self):
        """Full FDA pipeline comparison."""
        data = _make_test_data(n_samples=1000, n_points=24)

        # CPU pipeline
        t0 = time.time()
        cpu_fda.bspline_coefficients(data, n_basis=12)
        cpu_fda.functional_derivatives(data, order=1, n_basis=12)
        cpu_fda.glucodensity(data, n_bins=50)
        cpu_fda.l2_distance_to_mean(data)
        cpu_time = time.time() - t0

        # GPU pipeline
        t0 = time.time()
        gpu_fda.bspline_coefficients(data, n_basis=12, device=DEVICE)
        gpu_fda.functional_derivatives(data, order=1, n_basis=12,
                                       device=DEVICE)
        gpu_fda.glucodensity(data, n_bins=50, device=DEVICE)
        gpu_fda.l2_distance_to_mean(data, device=DEVICE)
        gpu_time = time.time() - t0

        speedup = cpu_time / max(gpu_time, 1e-6)
        print(f"\n  Full pipeline (1000 samples): "
              f"CPU={cpu_time:.2f}s, GPU={gpu_time:.2f}s, "
              f"speedup={speedup:.1f}×")


# ── Standalone runner ─────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"Device: {DEVICE}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name()}")
    print()

    # Run pytest with verbose output
    sys.exit(pytest.main([__file__, '-v', '--tb=short',
                          '-x',  # stop on first failure
                          '-k', 'not slow']))
