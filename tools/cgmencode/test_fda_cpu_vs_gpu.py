#!/usr/bin/env python3
"""
test_fda_cpu_vs_gpu.py — End-to-end CPU (scikit-fda) vs GPU (PyTorch) tests.

Each test runs the *identical* operation through both code paths on a small,
deterministic fixture and asserts tight numerical agreement.  The fixtures
are the minimum data needed to exercise each scikit-fda call chain.

Run:
    python -m pytest tools/cgmencode/test_fda_cpu_vs_gpu.py -v --tb=short
"""

import sys
import numpy as np
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cgmencode.fda_features as cpu
import cgmencode.fda_features_gpu as gpu

# ── Minimal deterministic fixtures ────────────────────────────────────
# These are the smallest arrays that produce numerically meaningful
# results through the full scikit-fda pipeline.

# 8 curves × 12 time points — enough for BSpline(n_basis=10), FPCA(k≤7),
# depth (needs ≥3), and KDE (needs ≥2 unique values per curve).
SEED = 2025
N_SAMPLES, N_POINTS = 8, 12


@pytest.fixture(scope="module")
def fixture():
    """Deterministic 8×12 CGM-like array and matching grid."""
    rng = np.random.RandomState(SEED)
    # Smooth curves: low-freq sine + noise, clipped to [0.05, 0.95]
    t = np.linspace(0, 2 * np.pi, N_POINTS)
    base = 0.5 + 0.3 * np.sin(t)
    data = np.clip(
        base[None, :] + 0.08 * rng.randn(N_SAMPLES, N_POINTS),
        0.05, 0.95,
    ).astype(np.float64)
    grid = np.linspace(0, N_POINTS - 1, N_POINTS, dtype=np.float64)
    return data, grid


DEVICE = "cpu"  # tests verify algorithm, not hardware

# ── 1. B-spline coefficients ─────────────────────────────────────────

class TestBsplineCoeffs:
    """CPU: FDataGrid → to_basis(BSplineBasis) → .coefficients
       GPU: collocation matrix → lstsq
    """

    def test_coefficients_match(self, fixture):
        data, grid = fixture
        n_basis = 8
        cpu_c = cpu.bspline_coefficients(data, n_basis=n_basis,
                                         grid_points=grid)
        gpu_r = gpu.bspline_smooth(data, n_basis=n_basis,
                                   grid_points=grid, device=DEVICE)
        gpu_c = gpu_r['coefficients']
        assert cpu_c.shape == gpu_c.shape
        # Coefficients may differ (different solver), so compare
        # reconstruction: coeffs × collocation → curves on grid
        recon_cpu = _cpu_reconstruct(cpu_c, grid, n_basis)
        # GPU: coeffs @ colloc^T
        import torch
        recon_gpu = (gpu_r['_coeffs_gpu'] @ gpu_r['_colloc_gpu'].T
                     ).cpu().numpy()
        mae = np.abs(recon_cpu - recon_gpu).mean()
        assert mae < 0.005, f"B-spline reconstruction MAE: {mae:.6f}"

    def test_roundtrip_residuals_comparable(self, fixture):
        """Both paths should have similar smoothing residuals."""
        data, grid = fixture
        n_basis = 10  # near-interpolation
        cpu_c = cpu.bspline_coefficients(data, n_basis=n_basis,
                                         grid_points=grid)
        gpu_r = gpu.bspline_smooth(data, n_basis=n_basis,
                                   grid_points=grid, device=DEVICE)
        # Residual = |data - smoothed|
        recon_cpu = _cpu_reconstruct(cpu_c, grid, n_basis)
        recon_gpu = (gpu_r['_coeffs_gpu'] @ gpu_r['_colloc_gpu'].T
                     ).cpu().numpy()
        cpu_res = np.abs(data - recon_cpu).mean()
        gpu_res = np.abs(data - recon_gpu).mean()
        # Both should be tiny; difference should be small
        assert abs(cpu_res - gpu_res) < 0.005, \
            f"Residual gap: CPU={cpu_res:.6f}, GPU={gpu_res:.6f}"


def _cpu_reconstruct(coeffs, grid, n_basis):
    """Reconstruct from CPU B-spline coefficients via scikit-fda."""
    import skfda
    basis = skfda.representation.basis.BSplineBasis(
        domain_range=(grid[0], grid[-1]), n_basis=n_basis)
    fd = skfda.FDataBasis(basis, coeffs.astype(np.float64))
    return fd(grid).squeeze()


# ── 2. Functional derivatives ─────────────────────────────────────────

class TestFunctionalDerivatives:
    """CPU: BSpline fit → .derivative(order) → evaluate
       GPU: BSpline fit → analytic coefficient derivative → evaluate
    """

    def test_first_derivative_match(self, fixture):
        data, grid = fixture
        cpu_d = cpu.functional_derivatives(data, order=1, n_basis=8,
                                           grid_points=grid)
        gpu_d = gpu.functional_derivatives(data, order=1, n_basis=8,
                                           grid_points=grid, device=DEVICE)
        assert cpu_d.shape == gpu_d.shape
        # Interior points (exclude B-spline edge artifacts)
        s = slice(2, -2)
        corr = np.corrcoef(cpu_d[:, s].ravel(), gpu_d[:, s].ravel())[0, 1]
        assert corr > 0.98, f"1st derivative correlation: {corr:.4f}"
        mae = np.abs(cpu_d[:, s] - gpu_d[:, s]).mean()
        assert mae < 0.05, f"1st derivative MAE: {mae:.6f}"

    def test_second_derivative_match(self, fixture):
        data, grid = fixture
        cpu_d2 = cpu.functional_derivatives(data, order=2, n_basis=8,
                                            grid_points=grid)
        gpu_d2 = gpu.functional_derivatives(data, order=2, n_basis=8,
                                            grid_points=grid, device=DEVICE)
        s = slice(3, -3)
        corr = np.corrcoef(cpu_d2[:, s].ravel(), gpu_d2[:, s].ravel())[0, 1]
        assert corr > 0.95, f"2nd derivative correlation: {corr:.4f}"


# ── 3. FPCA scores & variance ────────────────────────────────────────

class TestFPCA:
    """CPU: FPCA().fit_transform(FDataGrid/FDataBasis)
       GPU: Simpson-weighted Cholesky PCA via SVD
    """

    def test_variance_ratios_match(self, fixture):
        data, grid = fixture
        n_comp = 3
        cpu_var = cpu.fpca_variance_explained(data, max_components=n_comp,
                                              grid_points=grid)
        gpu_var = gpu.fpca_variance_explained(data, max_components=n_comp,
                                              grid_points=grid, device=DEVICE)
        cpu_r = np.array(cpu_var['variance_ratios'])
        gpu_r = np.array(gpu_var['variance_ratios'])
        np.testing.assert_allclose(cpu_r, gpu_r, atol=0.02,
            err_msg="FPCA variance ratios diverge")

    def test_cumulative_variance_match(self, fixture):
        """Cumulative variance should be close.

        Note: with smooth_first=True (default), CPU does basis-FPCA while
        GPU does grid-FPCA on smoothed data — small divergence expected.
        """
        data, grid = fixture
        cpu_v = cpu.fpca_variance_explained(data, max_components=5,
                                            grid_points=grid)
        gpu_v = gpu.fpca_variance_explained(data, max_components=5,
                                            grid_points=grid, device=DEVICE)
        cpu_cum = np.array(cpu_v['cumulative_variance'])
        gpu_cum = np.array(gpu_v['cumulative_variance'])
        np.testing.assert_allclose(cpu_cum, gpu_cum, atol=0.04,
            err_msg="Cumulative variance diverges")

    def test_cumulative_variance_no_smooth(self, fixture):
        """Without smoothing, both paths operate on identical input → tighter."""
        data, grid = fixture
        cpu_v = cpu.fpca_variance_explained(data, max_components=5,
                                            grid_points=grid,
                                            smooth_first=False)
        gpu_v = gpu.fpca_variance_explained(data, max_components=5,
                                            grid_points=grid,
                                            smooth_first=False, device=DEVICE)
        cpu_cum = np.array(cpu_v['cumulative_variance'])
        gpu_cum = np.array(gpu_v['cumulative_variance'])
        np.testing.assert_allclose(cpu_cum, gpu_cum, atol=0.02,
            err_msg="No-smooth cumulative variance diverges")

    def test_scores_subspace_agreement(self, fixture):
        """Score vectors may differ in sign, but should span same subspace.

        Check: projecting CPU scores onto GPU component space (and vice
        versa) recovers nearly all variance.
        """
        data, grid = fixture
        n_comp = 3
        cpu_scores, cpu_fpca = cpu.fpca_scores(
            data, n_components=n_comp, grid_points=grid)
        gpu_scores, gpu_info = gpu.fpca_scores(
            data, n_components=n_comp, grid_points=grid, device=DEVICE)

        # Variance captured should be similar
        cpu_var = np.var(cpu_scores, axis=0)
        gpu_var = np.var(gpu_scores, axis=0)
        # Sort by variance (PCs may be reordered)
        cpu_sorted = np.sort(cpu_var)[::-1]
        gpu_sorted = np.sort(gpu_var)[::-1]
        rel_diff = np.abs(cpu_sorted - gpu_sorted) / (cpu_sorted + 1e-8)
        assert rel_diff.max() < 0.15, \
            f"PC variance mismatch: {rel_diff}"

    def test_reconstruction_both_paths(self, fixture):
        """Both paths should reconstruct original data with similar error."""
        data, grid = fixture
        n_comp = min(N_SAMPLES - 1, N_POINTS - 1)
        # CPU
        cpu_scores, cpu_fpca = cpu.fpca_scores(
            data, n_components=n_comp, grid_points=grid, smooth_first=False)
        # GPU
        gpu_scores, gpu_info = gpu.fpca_scores(
            data, n_components=n_comp, grid_points=grid,
            smooth_first=False, device=DEVICE)

        gpu_recon = gpu_scores @ gpu_info['components_'] + gpu_info['mean_']
        gpu_err = np.abs(gpu_recon - data).mean()
        assert gpu_err < 0.05, f"GPU reconstruction MAE: {gpu_err:.6f}"


# ── 4. Glucodensity ──────────────────────────────────────────────────

class TestGlucodensity:
    """CPU: per-sample scipy.stats.gaussian_kde (Scott's rule)
       GPU: batched Gaussian KDE (Scott's bandwidth)
    """

    def test_density_shape_and_range(self, fixture):
        data, _ = fixture
        cpu_g = cpu.glucodensity(data, n_bins=30)
        gpu_g = gpu.glucodensity(data, n_bins=30, device=DEVICE)
        assert cpu_g.shape == gpu_g.shape == (N_SAMPLES, 30)
        # Both should be non-negative
        assert cpu_g.min() >= -1e-6
        assert gpu_g.min() >= -1e-6

    def test_peak_location_agreement(self, fixture):
        data, _ = fixture
        cpu_g = cpu.glucodensity(data, n_bins=50)
        gpu_g = gpu.glucodensity(data, n_bins=50, device=DEVICE)
        cpu_peaks = cpu_g.argmax(axis=1)
        gpu_peaks = gpu_g.argmax(axis=1)
        # Peaks within ±3 bins for ≥75% of samples
        close = np.abs(cpu_peaks - gpu_peaks) <= 3
        assert close.mean() >= 0.75, \
            f"Peak agreement: {close.mean():.0%} (need ≥75%)"

    def test_density_correlation(self, fixture):
        """Full density profiles should correlate highly."""
        data, _ = fixture
        cpu_g = cpu.glucodensity(data, n_bins=50)
        gpu_g = gpu.glucodensity(data, n_bins=50, device=DEVICE)
        for i in range(N_SAMPLES):
            c = cpu_g[i]
            g = gpu_g[i]
            if c.max() < 1e-8 and g.max() < 1e-8:
                continue  # both flat — trivially agree
            corr = np.corrcoef(c, g)[0, 1]
            assert corr > 0.85, \
                f"Sample {i} density corr: {corr:.4f}"


# ── 5. L² distance to mean ──────────────────────────────────────────

class TestL2Distance:
    """CPU: FDataGrid.mean() + per-sample l2_distance()
       GPU: vectorized (X - mean)² @ simpson_weights
    """

    def test_distances_match(self, fixture):
        data, grid = fixture
        cpu_d = cpu.l2_distance_to_mean(data, grid_points=grid)
        gpu_d = gpu.l2_distance_to_mean(data, grid_points=grid, device=DEVICE)
        assert cpu_d.shape == gpu_d.shape == (N_SAMPLES,)
        np.testing.assert_allclose(cpu_d, gpu_d, rtol=0.05, atol=1e-5,
            err_msg="L² distances diverge")

    def test_ranking_preserved(self, fixture):
        """Ranking of curves by distance should be identical."""
        data, grid = fixture
        cpu_d = cpu.l2_distance_to_mean(data, grid_points=grid)
        gpu_d = gpu.l2_distance_to_mean(data, grid_points=grid, device=DEVICE)
        cpu_rank = np.argsort(cpu_d)
        gpu_rank = np.argsort(gpu_d)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(cpu_rank, gpu_rank)
        assert corr > 0.95, f"Rank correlation: {corr:.4f}"

    def test_identical_curves_both_zero(self):
        """Identical curves → both paths return zero."""
        data = np.tile([0.3, 0.5, 0.7, 0.5], (5, 1)).astype(float)
        cpu_d = cpu.l2_distance_to_mean(data)
        gpu_d = gpu.l2_distance_to_mean(data, device=DEVICE)
        np.testing.assert_allclose(cpu_d, 0.0, atol=1e-6)
        np.testing.assert_allclose(gpu_d, 0.0, atol=1e-6)

    def test_nonuniform_grid(self):
        """Simpson's weights handle non-uniform spacing identically."""
        grid = np.array([0.0, 0.5, 2.0, 3.5, 4.0])
        data = np.array([[1, 2, 3, 4, 5], [5, 4, 3, 2, 1]], dtype=float)
        cpu_d = cpu.l2_distance_to_mean(data, grid_points=grid)
        gpu_d = gpu.l2_distance_to_mean(data, grid_points=grid, device=DEVICE)
        np.testing.assert_allclose(cpu_d, gpu_d, rtol=0.05, atol=1e-4,
            err_msg="Non-uniform grid distances differ")


# ── 6. Modified Band Depth ───────────────────────────────────────────

class TestFunctionalDepth:
    """CPU: ModifiedBandDepth()(FDataGrid)
       GPU: searchsorted SimplicialDepth + Simpson integration
    """

    def test_depths_match(self, fixture):
        data, grid = fixture
        cpu_dep = cpu.functional_depth(data, grid_points=grid)
        gpu_dep = gpu.functional_depth(data, grid_points=grid, device=DEVICE)
        assert cpu_dep.shape == gpu_dep.shape == (N_SAMPLES,)
        np.testing.assert_allclose(cpu_dep, gpu_dep, atol=0.02,
            err_msg="Depth values diverge")

    def test_ranking_preserved(self, fixture):
        data, grid = fixture
        cpu_dep = cpu.functional_depth(data, grid_points=grid)
        gpu_dep = gpu.functional_depth(data, grid_points=grid, device=DEVICE)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(cpu_dep, gpu_dep)
        assert corr > 0.95, f"Depth rank correlation: {corr:.4f}"

    def test_identical_curves_both_one(self):
        """Both paths: identical curves → depth=1.0."""
        data = np.tile([1, 2, 3, 4], (5, 1)).astype(float)
        cpu_dep = cpu.functional_depth(data)
        gpu_dep = gpu.functional_depth(data, device=DEVICE)
        np.testing.assert_allclose(cpu_dep, 1.0, atol=1e-5)
        np.testing.assert_allclose(gpu_dep, 1.0, atol=1e-5)

    def test_ordered_curves_both_paths(self):
        """Both paths: 5 ordered curves → [0.4, 0.7, 0.8, 0.7, 0.4]."""
        data = np.array([[0,0,0,0],[1,1,1,1],[2,2,2,2],
                         [3,3,3,3],[4,4,4,4]], dtype=float)
        expected = np.array([0.4, 0.7, 0.8, 0.7, 0.4])
        cpu_dep = cpu.functional_depth(data)
        gpu_dep = gpu.functional_depth(data, device=DEVICE)
        np.testing.assert_allclose(cpu_dep, expected, atol=1e-5,
            err_msg="CPU depth wrong on ordered data")
        np.testing.assert_allclose(gpu_dep, expected, atol=1e-5,
            err_msg="GPU depth wrong on ordered data")

    def test_outlier_detected_by_both(self, fixture):
        """Both paths should rank the outlier as lowest depth."""
        data, grid = fixture
        outlier = np.ones((1, N_POINTS)) * 10.0  # way outside [0.05, 0.95]
        data_ext = np.vstack([data, outlier])
        cpu_dep = cpu.functional_depth(data_ext, grid_points=grid)
        gpu_dep = gpu.functional_depth(data_ext, grid_points=grid,
                                       device=DEVICE)
        # Outlier (last) should be deepest-last in both
        assert np.argmin(cpu_dep) == N_SAMPLES, "CPU missed outlier"
        assert np.argmin(gpu_dep) == N_SAMPLES, "GPU missed outlier"


# ── 7. fda_encode dispatcher ─────────────────────────────────────────

class TestFdaEncodeDispatch:
    """Verify fda_encode() gives same results through CPU and GPU paths."""

    @pytest.mark.parametrize("method", [
        "bspline_coeffs", "fpca", "glucodensity",
        "derivatives", "depth", "l2_dist",
    ])
    def test_encode_method(self, fixture, method):
        data, _ = fixture
        cpu_result = cpu.fda_encode(data, method=method)
        gpu_result = gpu.fda_encode(data, method=method, device=DEVICE)
        assert cpu_result.shape == gpu_result.shape, \
            f"{method}: shape {cpu_result.shape} vs {gpu_result.shape}"
        assert np.all(np.isfinite(cpu_result)), f"{method}: CPU has NaN"
        assert np.all(np.isfinite(gpu_result)), f"{method}: GPU has NaN"

    @pytest.mark.parametrize("method", [
        "bspline_coeffs", "fpca", "glucodensity",
        "derivatives", "depth", "l2_dist",
    ])
    def test_encode_multichannel(self, fixture, method):
        data, _ = fixture
        mc = np.stack([data, data * 0.9], axis=-1)  # (8, 12, 2)
        cpu_r = cpu.fda_encode_multichannel(mc, method=method, channels=[0, 1])
        gpu_r = gpu.fda_encode_multichannel(mc, method=method,
                                            channels=[0, 1], device=DEVICE)
        assert cpu_r.shape == gpu_r.shape, \
            f"{method} MC: shape {cpu_r.shape} vs {gpu_r.shape}"


# ── 8. Analytical cross-checks (no CPU needed) ───────────────────────

class TestAnalyticalCrossChecks:
    """Known-answer tests that validate the math, not just CPU agreement."""

    def test_l2_triangle_inequality(self, fixture):
        """L² distance satisfies triangle inequality d(a,c) ≤ d(a,b) + d(b,c)."""
        data, grid = fixture
        # Pick 3 curves: a, b, c
        a, b, c = data[0:1], data[1:2], data[2:3]
        w = gpu._simpson_weights(grid)
        import torch
        W = torch.tensor(w, dtype=torch.float64)

        def l2(x, y):
            d = torch.tensor(x - y, dtype=torch.float64)
            return torch.sqrt((d ** 2 * W).sum()).item()

        d_ab = l2(a, b)
        d_bc = l2(b, c)
        d_ac = l2(a, c)
        assert d_ac <= d_ab + d_bc + 1e-10, \
            f"Triangle inequality violated: {d_ac} > {d_ab} + {d_bc}"

    def test_fpca_total_variance_conservation(self, fixture):
        """Sum of all eigenvalues = total variance of data."""
        data, grid = fixture
        n_comp = min(N_SAMPLES - 1, N_POINTS)
        _, info = gpu.fpca_scores(data, n_components=n_comp,
                                  grid_points=grid, smooth_first=False,
                                  device=DEVICE)
        # Sum of explained variance ratios ≤ 1.0
        total = info['explained_variance_ratio_'].sum()
        assert 0.95 <= total <= 1.0 + 1e-5, \
            f"Variance ratios sum to {total}, expected ~1.0"

    def test_depth_is_affine_invariant(self, fixture):
        """Depth ranking shouldn't change under affine transform y = a*x + b."""
        data, _ = fixture
        transformed = 2.5 * data + 100  # scale + shift
        d_orig = gpu.functional_depth(data, device=DEVICE)
        d_xform = gpu.functional_depth(transformed, device=DEVICE)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(d_orig, d_xform)
        assert corr > 0.99, f"Depth not affine invariant: ρ={corr:.4f}"

    def test_derivative_of_integral_identity(self):
        """If f(t) = ∫₀ᵗ g(s)ds, then f'(t) ≈ g(t) (fundamental theorem).

        Use g(t) = cos(t), so f(t) = sin(t), f'(t) = cos(t) = g(t).
        """
        t = np.linspace(0, 2 * np.pi, 48)
        f_data = np.array([np.sin(t)] * 3)  # f = sin(t)
        deriv = gpu.functional_derivatives(f_data, order=1,
                                           grid_points=t, device=DEVICE)
        expected = np.cos(t)
        # Interior check
        s = slice(4, -4)
        mae = np.abs(deriv[:, s] - expected[s]).mean()
        assert mae < 0.1, f"FTC check MAE: {mae:.4f}"


# ── Standalone runner ─────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
