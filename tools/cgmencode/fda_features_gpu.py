#!/usr/bin/env python3
"""
fda_features_gpu.py — GPU-accelerated FDA feature extraction using PyTorch.

Drop-in replacement for the per-sample-loop functions in fda_features.py.
Falls back to CPU PyTorch when CUDA is unavailable (still faster than
scikit-fda loops due to vectorized tensor ops).

Key speedups over fda_features.py:
  - glucodensity: batched KDE via torch (eliminates per-sample Python loop)
  - l2_distance_to_mean: vectorized subtraction (eliminates per-sample loop)
  - bspline_smooth: torch.linalg.lstsq on GPU
  - fpca_scores: torch.linalg.svd on GPU
  - functional_derivatives: analytic from B-spline coefficients on GPU

Usage:
    from tools.cgmencode.fda_features_gpu import (
        glucodensity, l2_distance_to_mean, bspline_smooth,
        fpca_scores, functional_derivatives, fda_encode,
    )
"""

import numpy as np
import torch
import scipy.integrate
from scipy.interpolate import BSpline as ScipyBSpline


def _resolve_device(device=None):
    """Resolve device argument to torch.device."""
    if device is None:
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if isinstance(device, torch.device):
        return device
    return torch.device(device)


def _simpson_weights(grid_points):
    """Compute Simpson's quadrature weights matching scikit-fda.

    scikit-fda's FPCA and L² distance use Simpson's composite rule weights
    for numerical integration. This replicates that exactly:
        identity = np.eye(n_points)
        weights = scipy.integrate.simpson(y=identity, x=grid_points)
    giving a (n_points,) weight vector where ∫f(t)dt ≈ Σ w_i f(t_i).
    """
    n = len(grid_points)
    identity = np.eye(n)
    return scipy.integrate.simpson(y=identity, x=grid_points)


# ── B-spline Basis Matrix Construction ────────────────────────────────

def _bspline_collocation_matrix(n_points, n_basis, order=4,
                                grid_points=None):
    """Build B-spline collocation matrix using scipy.

    Returns numpy array of shape (n_points, n_basis).
    This is done on CPU (one-time cost), then transferred to GPU for solving.
    """
    if grid_points is None:
        grid_points = np.arange(n_points, dtype=np.float64)

    domain = (float(grid_points[0]), float(grid_points[-1]))
    n_internal_knots = n_basis - order
    internal_knots = np.linspace(domain[0], domain[1],
                                 n_internal_knots + 2)[1:-1]
    knots = np.concatenate([
        np.full(order, domain[0]),
        internal_knots,
        np.full(order, domain[1]),
    ])

    colloc = np.zeros((n_points, n_basis), dtype=np.float64)
    for j in range(n_basis):
        c = np.zeros(n_basis)
        c[j] = 1.0
        spl = ScipyBSpline(knots, c, order - 1, extrapolate=True)
        colloc[:, j] = spl(grid_points)

    return colloc


def _bspline_deriv_collocation(n_points, n_basis, order=4,
                               grid_points=None, deriv_order=1):
    """Build derivative collocation matrix.

    Evaluates the deriv_order-th derivative of each B-spline basis function
    at the grid points.
    """
    if grid_points is None:
        grid_points = np.arange(n_points, dtype=np.float64)

    domain = (float(grid_points[0]), float(grid_points[-1]))
    n_internal_knots = n_basis - order
    internal_knots = np.linspace(domain[0], domain[1],
                                 n_internal_knots + 2)[1:-1]
    knots = np.concatenate([
        np.full(order, domain[0]),
        internal_knots,
        np.full(order, domain[1]),
    ])

    colloc = np.zeros((n_points, n_basis), dtype=np.float64)
    for j in range(n_basis):
        c = np.zeros(n_basis)
        c[j] = 1.0
        spl = ScipyBSpline(knots, c, order - 1, extrapolate=True)
        dspl = spl.derivative(deriv_order)
        colloc[:, j] = dspl(grid_points)

    return colloc


# Cache for collocation matrices (keyed by shape params)
_colloc_cache = {}


def _get_collocation(n_points, n_basis, order, grid_points_key, grid_points):
    """Get or build cached collocation matrix."""
    key = ('colloc', n_points, n_basis, order, grid_points_key)
    if key not in _colloc_cache:
        _colloc_cache[key] = _bspline_collocation_matrix(
            n_points, n_basis, order, grid_points)
    return _colloc_cache[key]


def _get_deriv_collocation(n_points, n_basis, order, grid_points_key,
                           grid_points, deriv_order):
    """Get or build cached derivative collocation matrix."""
    key = ('deriv', n_points, n_basis, order, grid_points_key, deriv_order)
    if key not in _colloc_cache:
        _colloc_cache[key] = _bspline_deriv_collocation(
            n_points, n_basis, order, grid_points, deriv_order)
    return _colloc_cache[key]


def clear_cache():
    """Clear the collocation matrix cache."""
    _colloc_cache.clear()


# ── GPU B-spline Smoothing ────────────────────────────────────────────

def bspline_smooth(data, n_knots=None, order=4, grid_points=None,
                   n_basis=None, device=None):
    """Fit B-spline basis to gridded data via least-squares on GPU.

    Args:
        data: array (n_samples, n_points)
        n_knots: number of interior knots (auto if None)
        order: B-spline order (4 = cubic)
        grid_points: optional 1-d time grid
        n_basis: total basis functions; overrides n_knots.
                 Default: n_points - 2
        device: torch device (None = auto)

    Returns:
        dict with 'coefficients' (n_samples, n_basis) as numpy,
        'colloc_matrix', 'n_basis', 'order', 'grid_points'
    """
    device = _resolve_device(device)
    n_samples, n_points = data.shape

    if n_basis is not None:
        pass
    elif n_knots is not None:
        n_basis = n_knots + order
    else:
        n_basis = max(order + 1, n_points - 2)

    if grid_points is None:
        gp_np = np.arange(n_points, dtype=np.float64)
        gp_key = ('default', n_points)
    else:
        gp_np = np.asarray(grid_points, dtype=np.float64)
        gp_key = ('custom', tuple(gp_np.tolist()))

    # Build collocation matrix (cached, CPU)
    B_np = _get_collocation(n_points, n_basis, order, gp_key, gp_np)

    # Solve on GPU: B @ coeffs = data^T → coeffs = lstsq(B, data^T)
    B_t = torch.tensor(B_np, dtype=torch.float64, device=device)
    Y_t = torch.tensor(data.astype(np.float64), dtype=torch.float64,
                       device=device).T  # (n_points, n_samples)

    result = torch.linalg.lstsq(B_t, Y_t)
    coeffs = result.solution.T  # (n_samples, n_basis)

    return {
        'coefficients': coeffs.float().cpu().numpy(),
        'colloc_np': B_np,
        'n_basis': n_basis,
        'order': order,
        'grid_points': gp_np,
        '_coeffs_gpu': coeffs,
        '_colloc_gpu': B_t,
        '_device': device,
    }


def bspline_coefficients(data, n_knots=None, order=4, grid_points=None,
                         n_basis=None, device=None):
    """Extract B-spline coefficient vectors.

    Returns:
        np.ndarray (n_samples, n_basis)
    """
    result = bspline_smooth(data, n_knots, order, grid_points,
                            n_basis=n_basis, device=device)
    return result['coefficients']


def bspline_roundtrip_error(data, n_knots=None, order=4, grid_points=None,
                            n_basis=None, device=None):
    """Measure B-spline reconstruction accuracy.

    Returns:
        dict with 'mae', 'max_error', 'per_sample_mae'
    """
    device = _resolve_device(device)
    result = bspline_smooth(data, n_knots, order, grid_points,
                            n_basis=n_basis, device=device)

    coeffs_t = result['_coeffs_gpu']   # (n_samples, n_basis)
    B_t = result['_colloc_gpu']         # (n_points, n_basis)

    # Reconstruct: data_hat = coeffs @ B^T → (n_samples, n_points)
    recon_t = coeffs_t @ B_t.T
    data_t = torch.tensor(data.astype(np.float64), dtype=torch.float64,
                          device=device)
    errors_t = (data_t - recon_t).abs()
    per_sample = errors_t.mean(dim=1).float().cpu().numpy()

    return {
        'mae': float(per_sample.mean()),
        'max_error': float(errors_t.max().item()),
        'per_sample_mae': per_sample,
    }


# ── GPU Functional Derivatives ────────────────────────────────────────

def functional_derivatives(data, order=1, n_knots=None, bspline_order=4,
                           grid_points=None, n_basis=None, device=None):
    """Compute functional derivatives on GPU.

    Fits B-spline, then evaluates derivative collocation matrix × coefficients.

    Returns:
        np.ndarray (n_samples, n_points)
    """
    device = _resolve_device(device)
    n_samples, n_points = data.shape

    if n_basis is None:
        if n_knots is not None:
            n_basis = n_knots + bspline_order
        else:
            n_basis = max(bspline_order + 1, n_points - 2)

    if grid_points is None:
        gp_np = np.arange(n_points, dtype=np.float64)
        gp_key = ('default', n_points)
    else:
        gp_np = np.asarray(grid_points, dtype=np.float64)
        gp_key = ('custom', tuple(gp_np.tolist()))

    # Get B-spline coefficients
    result = bspline_smooth(data, n_knots=n_knots, order=bspline_order,
                            grid_points=gp_np, n_basis=n_basis, device=device)
    coeffs_t = result['_coeffs_gpu']  # (n_samples, n_basis)

    # Build derivative collocation matrix
    D_np = _get_deriv_collocation(n_points, n_basis, bspline_order,
                                  gp_key, gp_np, order)
    D_t = torch.tensor(D_np, dtype=torch.float64, device=device)

    # Derivative values: coeffs @ D^T → (n_samples, n_points)
    deriv_t = coeffs_t @ D_t.T

    return deriv_t.float().cpu().numpy()


# ── GPU FPCA ──────────────────────────────────────────────────────────

def fpca_scores(data, n_components=5, grid_points=None, n_knots=None,
                order=4, smooth_first=True, n_basis=None, device=None):
    """Compute Functional PCA scores on GPU — matches scikit-fda algorithm.

    Implements the same weighted PCA as scikit-fda's FPCA._fit_grid():
      1. Compute Simpson's quadrature weights W = diag(w)
      2. L = cholesky(W)^T
      3. Transform: X_new = (X_centered @ W) @ L^{-T}
      4. PCA on X_new (standard SVD)
      5. Recover components: C = L^{-1} @ pca_components^T

    Returns:
        tuple (scores, info_dict):
          scores: np.ndarray (n_samples, n_components)
          info: dict with explained_variance_, explained_variance_ratio_,
                singular_values_, components_, mean_ (as numpy arrays)
    """
    device = _resolve_device(device)
    n_samples, n_points = data.shape

    if smooth_first:
        result = bspline_smooth(data, n_knots, order, grid_points,
                                n_basis=n_basis, device=device)
        coeffs_t = result['_coeffs_gpu']
        B_t = result['_colloc_gpu']
        X_np = (coeffs_t @ B_t.T).cpu().numpy().astype(np.float64)
    else:
        X_np = data.astype(np.float64)

    # Grid for Simpson's weights
    if grid_points is None:
        gp = np.arange(n_points, dtype=np.float64)
    else:
        gp = np.asarray(grid_points, dtype=np.float64)

    # Center
    mean = X_np.mean(axis=0, keepdims=True)
    Xc = X_np - mean

    # Simpson's quadrature weights (matching scikit-fda)
    w = _simpson_weights(gp)
    W = np.diag(w).astype(np.float64)

    # Cholesky: W = L L^T (factorization_matrix)
    Lt = np.linalg.cholesky(W).T  # upper triangular

    # Weighted transform: X_new = Xc @ W @ L^{-T}
    XW = Xc @ W
    X_new = np.linalg.solve(Lt.T, XW.T).T  # (n_samples, n_points)

    # Clamp n_components
    max_k = min(n_samples - 1, n_points)
    n_components = min(n_components, max_k)
    if n_components < 1:
        n_components = 1

    # PCA via SVD on GPU
    X_new_t = torch.tensor(X_new, dtype=torch.float64, device=device)
    # Center X_new (already centered via Xc, but PCA expects centered input)
    X_new_mean = X_new_t.mean(dim=0, keepdim=True)
    X_new_c = X_new_t - X_new_mean

    U, S, Vh = torch.linalg.svd(X_new_c, full_matrices=False)

    # Scores in the weighted space
    scores_weighted = (U[:, :n_components] * S[:n_components].unsqueeze(0))

    # Recover original-space components: solve Lt @ C^T = Vh^T
    pca_components = Vh[:n_components].cpu().numpy()
    original_components = np.linalg.solve(Lt, pca_components.T).T

    # Scores = Xc @ W @ original_components^T (project centered data)
    scores = (Xc @ W @ original_components.T).astype(np.float32)

    # Variance explained (from SVD singular values)
    sv = S.cpu().numpy()
    total_var = (sv ** 2).sum() / max(n_samples - 1, 1)
    explained = (sv[:n_components] ** 2) / max(n_samples - 1, 1)
    ratios = explained / max(total_var, 1e-12)

    info = {
        'explained_variance_': explained.astype(np.float32),
        'explained_variance_ratio_': ratios.astype(np.float32),
        'singular_values_': sv[:n_components].astype(np.float32),
        'components_': original_components.astype(np.float32),
        'mean_': mean.squeeze(0).astype(np.float32),
    }

    return scores, info


def fpca_variance_explained(data, max_components=20, grid_points=None,
                            n_knots=None, order=4, smooth_first=True,
                            n_basis=None, device=None):
    """Compute cumulative variance explained by FPCA components on GPU.

    Returns:
        dict with 'explained_variance', 'variance_ratios',
        'cumulative_variance', 'n_for_90', 'n_for_95', 'n_for_99'
    """
    K = min(max_components, data.shape[0] - 1, data.shape[1] - 1)
    _, info = fpca_scores(data, n_components=K, grid_points=grid_points,
                          n_knots=n_knots, order=order,
                          smooth_first=smooth_first, n_basis=n_basis,
                          device=device)

    ratios = info['explained_variance_ratio_']
    cumulative = np.cumsum(ratios)

    def n_for_threshold(thresh):
        idx = np.searchsorted(cumulative, thresh)
        return int(idx + 1) if idx < len(cumulative) else len(cumulative)

    return {
        'explained_variance': info['explained_variance_'].tolist(),
        'variance_ratios': ratios.tolist(),
        'cumulative_variance': cumulative.tolist(),
        'n_for_90': n_for_threshold(0.90),
        'n_for_95': n_for_threshold(0.95),
        'n_for_99': n_for_threshold(0.99),
        'n_computed': int(len(ratios)),
    }


# ── GPU Glucodensity (Batched KDE) ───────────────────────────────────

def glucodensity(data, n_bins=50, glucose_range=(0.0, 1.0), device=None):
    """Compute glucodensity via batched Gaussian KDE on GPU.

    Eliminates the per-sample Python loop in fda_features.py by computing
    all KDE evaluations as a single batched tensor operation.

    Args:
        data: array (n_samples, n_points) — glucose values (normalized)
        n_bins: number of density evaluation points
        glucose_range: (min, max) for evaluation grid
        device: torch device

    Returns:
        np.ndarray (n_samples, n_bins) — density profiles
    """
    device = _resolve_device(device)
    n_samples, n_points = data.shape

    # Evaluation grid: (n_bins,)
    eval_pts = torch.linspace(glucose_range[0], glucose_range[1], n_bins,
                              dtype=torch.float32, device=device)

    # Data tensor: (n_samples, n_points)
    X = torch.tensor(data.astype(np.float32), dtype=torch.float32,
                     device=device)

    # Handle NaN: replace with 0 and create validity mask
    nan_mask = torch.isnan(X)
    X = torch.where(nan_mask, torch.zeros_like(X), X)
    valid_count = (~nan_mask).sum(dim=1).float()  # (n_samples,)

    # Clamp to range
    eps = 1e-6
    X = X.clamp(glucose_range[0] + eps, glucose_range[1] - eps)

    # Scott's rule bandwidth per sample: h = n^(-1/5) * std
    # Use valid points only for std computation
    X_for_std = X.clone()
    X_for_std[nan_mask] = float('nan')
    stds = torch.nanmean((X_for_std - torch.nanmean(X_for_std, dim=1,
                          keepdim=True)) ** 2, dim=1).sqrt()
    bw = valid_count.pow(-0.2) * stds  # (n_samples,)
    bw = bw.clamp(min=1e-6)

    # Batched KDE: density(x) = (1/N) * Σ K((x - xi)/h) / h
    # X:        (n_samples, n_points, 1)
    # eval_pts: (1, 1, n_bins)
    # Result:   (n_samples, n_bins)
    X_3d = X.unsqueeze(2)            # (n_samples, n_points, 1)
    E_3d = eval_pts.view(1, 1, -1)   # (1, 1, n_bins)
    bw_3d = bw.view(-1, 1, 1)        # (n_samples, 1, 1)

    # Gaussian kernel: K(u) = exp(-0.5 * u²) / sqrt(2π)
    u = (E_3d - X_3d) / bw_3d       # (n_samples, n_points, n_bins)
    kernel = torch.exp(-0.5 * u * u) * 0.3989422804014327  # 1/sqrt(2π)

    # Zero out contributions from NaN positions
    kernel[nan_mask.unsqueeze(2).expand_as(kernel)] = 0.0

    # Sum and normalize
    densities = kernel.sum(dim=1) / (valid_count.unsqueeze(1) * bw.unsqueeze(1))

    # Handle degenerate cases (< 3 valid points or zero bandwidth)
    degenerate = valid_count < 3
    if degenerate.any():
        means = torch.nanmean(X_for_std, dim=1)
        for i in torch.where(degenerate)[0]:
            densities[i] = 0.0
            nearest = (eval_pts - means[i]).abs().argmin()
            densities[i, nearest] = 1.0

    return densities.cpu().numpy()


# ── GPU L² Distance to Mean ──────────────────────────────────────────

def l2_distance_to_mean(data, grid_points=None, device=None):
    """Compute L² distance of each curve to the sample mean — vectorized.

    Matches scikit-fda's L² distance which uses Simpson's rule integration:
        d(f, g) = sqrt(∫(f(t) - g(t))² dt)

    Args:
        data: array (n_samples, n_points)
        grid_points: optional 1-d time grid (for non-uniform spacing)
        device: torch device

    Returns:
        np.ndarray (n_samples,) — L² distances
    """
    device = _resolve_device(device)
    n_samples, n_points = data.shape

    if grid_points is None:
        gp = np.arange(n_points, dtype=np.float64)
    else:
        gp = np.asarray(grid_points, dtype=np.float64)

    # Simpson's quadrature weights (matching scikit-fda)
    w = _simpson_weights(gp)  # (n_points,)
    w_t = torch.tensor(w, dtype=torch.float64, device=device)

    X = torch.tensor(data.astype(np.float64), dtype=torch.float64,
                     device=device)

    mean = X.mean(dim=0, keepdim=True)  # (1, n_points)
    diff = X - mean  # (n_samples, n_points)

    # L² distance via Simpson's weights: sqrt(Σ w_i * (f_i - g_i)²)
    integrand = diff ** 2 * w_t.unsqueeze(0)  # (n_samples, n_points)
    distances = torch.sqrt(integrand.sum(dim=1).clamp(min=0))

    return distances.float().cpu().numpy()


# ── GPU Functional Depth ──────────────────────────────────────────────

def functional_depth(data, method='modified_band', grid_points=None,
                     device=None):
    """Compute Modified Band Depth on GPU — matches scikit-fda algorithm.

    Implements scikit-fda's IntegratedDepth(SimplicialDepth()):
      1. At each time point, compute pointwise SimplicialDepth via searchsorted
      2. Integrate pointwise depths via Simpson's rule (average_function_value)

    SimplicialDepth at each point t:
      - Sort all n values at time t
      - For each sample x_i(t), count how many pairs (j,k) form a band
        containing x_i(t): depth = (C(n,2) - C(below,2) - C(above,2)) / C(n,2)

    Args:
        data: array (n_samples, n_points)
        device: torch device

    Returns:
        np.ndarray (n_samples,) — depth scores in [0, 1]
    """
    device = _resolve_device(device)
    n, T = data.shape

    X = torch.tensor(data.astype(np.float64), dtype=torch.float64,
                     device=device)

    # Sort each time point column (fit step)
    sorted_vals, _ = X.sort(dim=0)  # (n, T)

    # Pointwise SimplicialDepth for each sample at each time point
    # searchsorted: find positions in sorted values
    # positions_left[i,t] = number of sorted values strictly < X[i,t]
    positions_left = torch.searchsorted(sorted_vals.T.contiguous(),
                                        X.T.contiguous(),
                                        side='left').T  # (n, T)
    positions_right = torch.searchsorted(sorted_vals.T.contiguous(),
                                         X.T.contiguous(),
                                         side='right').T  # (n, T)

    below = positions_left.double()         # strictly below
    above = (n - positions_right).double()  # strictly above
    total_pairs = n * (n - 1) / 2.0        # C(n, 2)

    # C(k, 2) = k*(k-1)/2
    def comb2(k):
        return k * (k - 1) / 2.0

    # Pointwise depth: (C(n,2) - C(below,2) - C(above,2)) / C(n,2)
    pointwise = (total_pairs - comb2(below) - comb2(above)) / total_pairs
    # (n, T)

    # Integrate via Simpson's rule (matching scikit-fda's average_function_value)
    if grid_points is None:
        gp = np.arange(T, dtype=np.float64)
    else:
        gp = np.asarray(grid_points, dtype=np.float64)

    w = _simpson_weights(gp)  # (T,)
    domain_len = gp[-1] - gp[0]
    w_t = torch.tensor(w, dtype=torch.float64, device=device)

    # average_function_value = ∫depth(t)dt / (b - a)
    depths = (pointwise * w_t.unsqueeze(0)).sum(dim=1) / domain_len

    return depths.float().cpu().numpy()


# ── Multi-Channel FDA Encoding ────────────────────────────────────────

def fda_encode(windows, method='fpca', channel=0, device=None, **kwargs):
    """Apply GPU-accelerated FDA encoding to windowed data.

    Same API as fda_features.fda_encode but runs on GPU.

    Args:
        windows: np.ndarray (n_samples, n_timesteps, n_channels)
        method: 'bspline_coeffs', 'fpca', 'glucodensity',
                'derivatives', 'depth', 'l2_dist'
        channel: which channel (default 0 = glucose)
        device: torch device
        **kwargs: passed to underlying function

    Returns:
        np.ndarray
    """
    if windows.ndim == 2:
        channel_data = windows
    elif windows.ndim == 3:
        channel_data = windows[:, :, channel]
    else:
        raise ValueError(f"Expected 2D or 3D, got shape {windows.shape}")

    if method == 'bspline_coeffs':
        return bspline_coefficients(channel_data, device=device, **kwargs)
    elif method == 'fpca':
        scores, _ = fpca_scores(channel_data, device=device, **kwargs)
        return scores
    elif method == 'glucodensity':
        return glucodensity(channel_data, device=device, **kwargs)
    elif method == 'derivatives':
        return functional_derivatives(channel_data, device=device, **kwargs)
    elif method == 'depth':
        return functional_depth(channel_data, device=device, **kwargs)
    elif method == 'l2_dist':
        return l2_distance_to_mean(channel_data, device=device, **kwargs)
    else:
        raise ValueError(f"Unknown FDA method: {method}. "
                         f"Choose from: bspline_coeffs, fpca, glucodensity, "
                         f"derivatives, depth, l2_dist")


def fda_encode_multichannel(windows, method='fpca', channels=None,
                            device=None, **kwargs):
    """Apply GPU FDA encoding to multiple channels and concatenate."""
    if channels is None:
        channels = [0]

    features = []
    for ch in channels:
        feat = fda_encode(windows, method=method, channel=ch,
                          device=device, **kwargs)
        if feat.ndim == 1:
            feat = feat[:, np.newaxis]
        features.append(feat)

    return np.concatenate(features, axis=1)
