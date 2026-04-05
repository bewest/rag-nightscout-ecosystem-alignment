#!/usr/bin/env python3
"""
fda_features.py — Functional Data Analysis feature extraction for CGM data.

Provides B-spline smoothing, FPCA decomposition, glucodensity profiles,
functional derivatives, depth measures, and distance metrics as a drop-in
preprocessing layer compatible with the existing multiscale data pipeline.

Part of EXP-328 (FDA Toolchain Bootstrap).

Usage:
    from tools.cgmencode.fda_features import (
        bspline_smooth, fpca_scores, glucodensity,
        functional_derivatives, functional_depth, l2_distance_to_mean,
        fda_encode,
    )

    # Single-channel smoothing
    fd = bspline_smooth(glucose_grid, n_knots=12)

    # Full pipeline encoding
    features = fda_encode(windows_np, method='fpca', n_components=5)
"""

import numpy as np
from scipy import stats as scipy_stats
import skfda
from skfda.representation.basis import BSplineBasis, FourierBasis
from skfda.representation.grid import FDataGrid
from skfda.preprocessing.dim_reduction import FPCA
from skfda.exploratory.depth import ModifiedBandDepth
from skfda.misc.metrics import l2_distance


# ── Core FDA Functions ─────────────────────────────────────────────────

def grid_to_fdatagrid(data, grid_points=None):
    """Convert numpy array to scikit-fda FDataGrid.

    Args:
        data: array of shape (n_samples, n_points) or (n_samples, n_points, n_channels)
        grid_points: optional 1-d array of time points; defaults to [0..n_points-1]

    Returns:
        FDataGrid object
    """
    if data.ndim == 2:
        # (n_samples, n_points) → single-channel
        pass
    elif data.ndim == 3:
        # (n_samples, n_points, n_channels) — scikit-fda expects (n_samples, n_points, n_dim)
        pass
    else:
        raise ValueError(f"Expected 2D or 3D array, got shape {data.shape}")

    if grid_points is None:
        grid_points = np.arange(data.shape[1], dtype=np.float64)

    return FDataGrid(data_matrix=data.astype(np.float64),
                     grid_points=grid_points)


def bspline_smooth(data, n_knots=None, order=4, grid_points=None,
                   smoothing_parameter=None, n_basis=None):
    """Fit B-spline basis to gridded data and return the smoothed FDataBasis.

    Uses least-squares projection (to_basis) for reliable fitting.

    Args:
        data: array (n_samples, n_points) — single channel
        n_knots: number of interior knots (auto-calculated if None)
        order: B-spline order (4 = cubic, default)
        grid_points: optional time grid
        smoothing_parameter: not used (kept for API compat)
        n_basis: total basis functions; overrides n_knots if provided.
                 Default: n_points - 2 (near-interpolation)

    Returns:
        FDataBasis on BSplineBasis
    """
    fd_grid = grid_to_fdatagrid(data, grid_points)
    n_points = data.shape[1]

    if n_basis is not None:
        pass
    elif n_knots is not None:
        n_basis = n_knots + order
    else:
        # Default: near-interpolation (n_points - 2 basis functions)
        n_basis = max(order + 1, n_points - 2)

    basis = BSplineBasis(
        domain_range=fd_grid.domain_range[0],
        n_basis=n_basis,
        order=order,
    )
    return fd_grid.to_basis(basis)


def bspline_coefficients(data, n_knots=None, order=4, grid_points=None,
                         n_basis=None):
    """Extract B-spline coefficient vectors from gridded data.

    Args:
        data: array (n_samples, n_points) — single channel
        n_knots, order, grid_points, n_basis: see bspline_smooth

    Returns:
        np.ndarray of shape (n_samples, n_basis)
    """
    fd_basis = bspline_smooth(data, n_knots, order, grid_points,
                              n_basis=n_basis)
    return fd_basis.coefficients.astype(np.float32)


def fpca_scores(data, n_components=5, grid_points=None, n_knots=None,
                order=4, smooth_first=True, n_basis=None):
    """Compute Functional PCA scores.

    Args:
        data: array (n_samples, n_points) — single channel
        n_components: number of principal components
        grid_points: optional time grid
        n_knots, order, n_basis: B-spline params if smooth_first=True
        smooth_first: whether to B-spline smooth before FPCA

    Returns:
        tuple of (scores, fpca_object):
          scores: np.ndarray (n_samples, n_components) — PC projections
          fpca: fitted FPCA object (contains components_, explained_variance_,
                explained_variance_ratio_, singular_values_)
    """
    if smooth_first:
        fd = bspline_smooth(data, n_knots, order, grid_points, n_basis=n_basis)
        # FPCA n_components must be < n_basis of the representation
        max_k = fd.n_basis - 1
    else:
        fd = grid_to_fdatagrid(data, grid_points)
        max_k = min(data.shape) - 1

    n_components = min(n_components, max_k, data.shape[0] - 1)
    if n_components < 1:
        n_components = 1

    fpca = FPCA(n_components=n_components)
    scores = fpca.fit_transform(fd)
    return scores.astype(np.float32), fpca


def fpca_variance_explained(data, max_components=20, grid_points=None,
                            n_knots=None, order=4, smooth_first=True,
                            n_basis=None):
    """Compute cumulative variance explained by FPCA components.

    Args:
        data: array (n_samples, n_points) — single channel
        max_components: maximum K to compute
        grid_points, n_knots, order, smooth_first, n_basis: see fpca_scores

    Returns:
        dict with 'explained_variance', 'variance_ratios',
        'cumulative_variance', 'n_for_90', 'n_for_95', 'n_for_99'
    """
    K = min(max_components, data.shape[0] - 1, data.shape[1] - 1)
    _, fpca = fpca_scores(data, n_components=K, grid_points=grid_points,
                          n_knots=n_knots, order=order,
                          smooth_first=smooth_first, n_basis=n_basis)

    explained_var = fpca.explained_variance_
    ratios = fpca.explained_variance_ratio_
    cumulative = np.cumsum(ratios)

    def n_for_threshold(thresh):
        idx = np.searchsorted(cumulative, thresh)
        return int(idx + 1) if idx < len(cumulative) else len(cumulative)

    return {
        'explained_variance': explained_var.tolist(),
        'variance_ratios': ratios.tolist(),
        'cumulative_variance': cumulative.tolist(),
        'n_for_90': n_for_threshold(0.90),
        'n_for_95': n_for_threshold(0.95),
        'n_for_99': n_for_threshold(0.99),
        'n_computed': int(len(ratios)),
    }


def glucodensity(data, n_bins=50, glucose_range=(0.0, 1.0)):
    """Compute glucodensity (KDE-based distributional profile) per window.

    Implements Matabuena et al. (2021) glucodensity concept: the probability
    density of glucose values within a time window.

    Args:
        data: array (n_samples, n_points) — glucose channel (normalized)
        n_bins: number of evaluation points for the density
        glucose_range: (min, max) of evaluation range

    Returns:
        np.ndarray (n_samples, n_bins) — density evaluated at grid points
    """
    eval_points = np.linspace(glucose_range[0], glucose_range[1], n_bins)
    densities = np.zeros((data.shape[0], n_bins), dtype=np.float32)

    for i in range(data.shape[0]):
        values = data[i]
        values = values[~np.isnan(values)]
        if len(values) < 3:
            continue
        # Clamp to range to avoid KDE edge issues
        values = np.clip(values, glucose_range[0] + 1e-6,
                         glucose_range[1] - 1e-6)
        try:
            kde = scipy_stats.gaussian_kde(values, bw_method='scott')
            densities[i] = kde(eval_points).astype(np.float32)
        except (np.linalg.LinAlgError, ValueError):
            # Degenerate case (all values identical)
            nearest = np.argmin(np.abs(eval_points - values.mean()))
            densities[i, nearest] = 1.0

    return densities


def functional_derivatives(data, order=1, n_knots=None, bspline_order=4,
                           grid_points=None, n_basis=None):
    """Compute functional derivatives from B-spline representation.

    Unlike finite differences, these are analytic derivatives of the smooth
    fitted curve, providing noise-robust rate-of-change estimates.

    Args:
        data: array (n_samples, n_points) — single channel
        order: derivative order (1 = velocity, 2 = acceleration)
        n_knots, bspline_order, n_basis: B-spline fit parameters
        grid_points: optional time grid

    Returns:
        np.ndarray (n_samples, n_points) — derivative evaluated on original grid
    """
    fd_basis = bspline_smooth(data, n_knots, bspline_order, grid_points,
                              n_basis=n_basis)
    fd_deriv = fd_basis.derivative(order=order)

    # Evaluate on original grid
    if grid_points is None:
        grid_points = np.arange(data.shape[1], dtype=np.float64)

    deriv_values = fd_deriv(grid_points)
    # Shape: (n_samples, n_points, 1) → (n_samples, n_points)
    if deriv_values.ndim == 3:
        deriv_values = deriv_values[:, :, 0]

    return deriv_values.astype(np.float32)


def functional_depth(data, method='modified_band', grid_points=None):
    """Compute functional depth — how "central/typical" each curve is.

    Low depth indicates outlier/atypical curves. Useful for novelty detection
    (e.g., pre-hypoglycemic patterns).

    Args:
        data: array (n_samples, n_points)
        method: 'modified_band' (default)
        grid_points: optional time grid

    Returns:
        np.ndarray (n_samples,) — depth scores in [0, 1]
    """
    fd_grid = grid_to_fdatagrid(data, grid_points)
    depth_fn = ModifiedBandDepth()
    return depth_fn(fd_grid).astype(np.float32)


def l2_distance_to_mean(data, grid_points=None):
    """Compute L² distance of each curve to the sample mean function.

    Args:
        data: array (n_samples, n_points)
        grid_points: optional time grid

    Returns:
        np.ndarray (n_samples,) — L² distance to mean
    """
    fd_grid = grid_to_fdatagrid(data, grid_points)
    mean_fd = fd_grid.mean()

    distances = np.zeros(data.shape[0], dtype=np.float32)
    for i in range(data.shape[0]):
        sample_fd = fd_grid[i]
        d = l2_distance(sample_fd, mean_fd)
        distances[i] = float(d.ravel()[0]) if hasattr(d, 'ravel') else float(d)

    return distances


def bspline_roundtrip_error(data, n_knots=None, order=4, grid_points=None,
                            n_basis=None):
    """Measure B-spline reconstruction accuracy (round-trip error).

    Fits B-spline to data, evaluates on original grid, computes MAE.

    Args:
        data: array (n_samples, n_points)
        n_knots, order, n_basis: B-spline parameters (see bspline_smooth)
        grid_points: optional time grid

    Returns:
        dict with 'mae', 'max_error', 'per_sample_mae'
    """
    if grid_points is None:
        grid_points = np.arange(data.shape[1], dtype=np.float64)

    fd_basis = bspline_smooth(data, n_knots, order, grid_points,
                              n_basis=n_basis)
    reconstructed = fd_basis(grid_points)
    if reconstructed.ndim == 3:
        reconstructed = reconstructed[:, :, 0]

    errors = np.abs(data.astype(np.float64) - reconstructed)
    per_sample = errors.mean(axis=1)

    return {
        'mae': float(per_sample.mean()),
        'max_error': float(errors.max()),
        'per_sample_mae': per_sample.astype(np.float32),
    }


# ── Multi-Channel FDA Encoding ─────────────────────────────────────────

def fda_encode(windows, method='fpca', channel=0, **kwargs):
    """Apply FDA encoding to windowed data.

    Drop-in encoding step: takes (N, T, C) windows, returns features.

    Args:
        windows: np.ndarray (n_samples, n_timesteps, n_channels)
        method: one of 'bspline_coeffs', 'fpca', 'glucodensity',
                'derivatives', 'depth', 'l2_dist'
        channel: which channel to operate on (default 0 = glucose)
        **kwargs: passed to the underlying FDA function

    Returns:
        np.ndarray — shape depends on method:
          bspline_coeffs: (N, n_basis)
          fpca:           (N, n_components)
          glucodensity:   (N, n_bins)
          derivatives:    (N, T)
          depth:          (N,)
          l2_dist:        (N,)
    """
    if windows.ndim == 2:
        channel_data = windows
    elif windows.ndim == 3:
        channel_data = windows[:, :, channel]
    else:
        raise ValueError(f"Expected 2D or 3D, got shape {windows.shape}")

    if method == 'bspline_coeffs':
        return bspline_coefficients(channel_data, **kwargs)
    elif method == 'fpca':
        scores, _ = fpca_scores(channel_data, **kwargs)
        return scores
    elif method == 'glucodensity':
        return glucodensity(channel_data, **kwargs)
    elif method == 'derivatives':
        return functional_derivatives(channel_data, **kwargs)
    elif method == 'depth':
        return functional_depth(channel_data, **kwargs)
    elif method == 'l2_dist':
        return l2_distance_to_mean(channel_data, **kwargs)
    else:
        raise ValueError(f"Unknown FDA method: {method}. "
                         f"Choose from: bspline_coeffs, fpca, glucodensity, "
                         f"derivatives, depth, l2_dist")


def fda_encode_multichannel(windows, method='fpca', channels=None, **kwargs):
    """Apply FDA encoding to multiple channels and concatenate.

    Args:
        windows: np.ndarray (n_samples, n_timesteps, n_channels)
        method: FDA method to apply per channel
        channels: list of channel indices (default: [0] = glucose only)
        **kwargs: passed to fda_encode

    Returns:
        np.ndarray — concatenated features across channels
    """
    if channels is None:
        channels = [0]

    features = []
    for ch in channels:
        feat = fda_encode(windows, method=method, channel=ch, **kwargs)
        if feat.ndim == 1:
            feat = feat[:, np.newaxis]
        features.append(feat)

    return np.concatenate(features, axis=1)


# ── Validation / Bootstrap (EXP-328) ──────────────────────────────────

def validate_fda_toolchain(windows, scale_name='fast', verbose=True):
    """Run EXP-328 validation suite on a set of windows.

    Tests B-spline round-trip, FPCA variance, glucodensity computation,
    derivative SNR, depth computation, and L² distances.

    Args:
        windows: np.ndarray (n_samples, n_timesteps, n_channels)
        scale_name: label for reporting
        verbose: print progress

    Returns:
        dict with validation results for all FDA methods
    """
    glucose = windows[:, :, 0]  # channel 0 = glucose
    n_samples, n_points = glucose.shape

    results = {
        'scale': scale_name,
        'n_samples': n_samples,
        'n_points': n_points,
    }

    if verbose:
        print(f"\n  FDA Bootstrap Validation ({scale_name}): "
              f"{n_samples} samples × {n_points} points")

    # 1. B-spline round-trip (near-interpolation with n_basis = n_points-2)
    if verbose:
        print("    [1/6] B-spline round-trip...")
    # Near-interpolation: high n_basis for fidelity test
    n_basis_interp = max(5, n_points - 2)
    rt = bspline_roundtrip_error(glucose, n_basis=n_basis_interp)
    rt_mgdl = rt['mae'] * 400.0
    # Also test smoothing regime (fewer basis functions)
    n_basis_smooth = max(5, n_points // 2)
    rt_smooth = bspline_roundtrip_error(glucose, n_basis=n_basis_smooth)
    rt_smooth_mgdl = rt_smooth['mae'] * 400.0
    # Pass: interpolation < 2 mg/dL (noise floor) AND smoothing < 10 mg/dL
    interp_pass = rt_mgdl < 2.0
    smooth_pass = rt_smooth_mgdl < 10.0
    results['bspline'] = {
        'n_basis_interp': n_basis_interp,
        'mae_interp_mgdl': float(rt_mgdl),
        'max_error_interp_mgdl': float(rt['max_error'] * 400.0),
        'n_basis_smooth': n_basis_smooth,
        'mae_smooth_mgdl': float(rt_smooth_mgdl),
        'max_error_smooth_mgdl': float(rt_smooth['max_error'] * 400.0),
        'pass': interp_pass and smooth_pass,
    }
    if verbose:
        s1 = "✓" if interp_pass else "✗"
        s2 = "✓" if smooth_pass else "✗"
        print(f"      Interp (n_basis={n_basis_interp}): "
              f"MAE={rt_mgdl:.3f} mg/dL (< 2.0) {s1}")
        print(f"      Smooth (n_basis={n_basis_smooth}): "
              f"MAE={rt_smooth_mgdl:.3f} mg/dL (< 10.0) {s2}")

    # 2. FPCA variance explained
    if verbose:
        print("    [2/6] FPCA variance structure...")
    var_info = fpca_variance_explained(glucose, max_components=20,
                                       n_basis=n_basis_interp)
    results['fpca'] = var_info
    results['fpca']['pass'] = var_info['n_for_90'] <= 8
    if verbose:
        print(f"      90% var with K={var_info['n_for_90']}, "
              f"95% with K={var_info['n_for_95']} "
              f"(target: 90% with K≤8) "
              f"{'✓ PASS' if var_info['n_for_90'] <= 8 else '✗ FAIL'}")

    # 3. Glucodensity
    if verbose:
        print("    [3/6] Glucodensity profiles...")
    gd = glucodensity(glucose, n_bins=50)
    gd_valid = np.all(np.isfinite(gd)) and gd.shape == (n_samples, 50)
    results['glucodensity'] = {
        'shape': list(gd.shape),
        'mean_density_sum': float(gd.sum(axis=1).mean()),
        'pass': bool(gd_valid),
    }
    if verbose:
        print(f"      Shape: {gd.shape}, valid: {gd_valid} "
              f"{'✓ PASS' if gd_valid else '✗ FAIL'}")

    # 4. Functional derivatives
    if verbose:
        print("    [4/6] Functional derivatives...")
    d1 = functional_derivatives(glucose, order=1, n_basis=n_basis_interp)
    d2 = functional_derivatives(glucose, order=2, n_basis=n_basis_interp)
    d1_valid = d1.shape == glucose.shape and np.all(np.isfinite(d1))
    results['derivatives'] = {
        'd1_shape': list(d1.shape),
        'd1_mean_abs': float(np.abs(d1).mean()),
        'd1_std': float(d1.std()),
        'd2_mean_abs': float(np.abs(d2).mean()),
        'pass': bool(d1_valid),
    }
    if verbose:
        print(f"      1st: mean|d/dt|={np.abs(d1).mean():.4f}, "
              f"2nd: mean|d²/dt²|={np.abs(d2).mean():.4f} "
              f"{'✓ PASS' if d1_valid else '✗ FAIL'}")

    # 5. Functional depth
    if verbose:
        print("    [5/6] Functional depth (Modified Band Depth)...")
    depths = functional_depth(glucose)
    depth_valid = (depths.shape == (n_samples,) and
                   np.all(np.isfinite(depths)) and
                   depths.min() >= 0)
    results['depth'] = {
        'mean': float(depths.mean()),
        'std': float(depths.std()),
        'min': float(depths.min()),
        'max': float(depths.max()),
        'pass': bool(depth_valid),
    }
    if verbose:
        print(f"      Mean={depths.mean():.3f}, range=[{depths.min():.3f}, "
              f"{depths.max():.3f}] "
              f"{'✓ PASS' if depth_valid else '✗ FAIL'}")

    # 6. L² distance to mean
    if verbose:
        print("    [6/6] L² distance to mean...")
    l2_dists = l2_distance_to_mean(glucose)
    l2_valid = (l2_dists.shape == (n_samples,) and
                np.all(np.isfinite(l2_dists)))
    results['l2_distance'] = {
        'mean': float(l2_dists.mean()),
        'std': float(l2_dists.std()),
        'pass': bool(l2_valid),
    }
    if verbose:
        print(f"      Mean L²={l2_dists.mean():.4f}, "
              f"std={l2_dists.std():.4f} "
              f"{'✓ PASS' if l2_valid else '✗ FAIL'}")

    # Overall
    all_pass = all(results[k].get('pass', False) for k in
                   ['bspline', 'fpca', 'glucodensity', 'derivatives',
                    'depth', 'l2_distance'])
    results['all_pass'] = all_pass
    if verbose:
        print(f"\n    Overall: {'✓ ALL PASS' if all_pass else '✗ SOME FAILED'}")

    return results
