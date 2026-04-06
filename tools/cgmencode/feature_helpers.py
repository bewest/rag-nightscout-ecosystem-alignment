"""Shared feature engineering helpers for glucose ML experiments.

Reusable utilities for normalization, conditioning, and feature extraction
that can be imported by any experiment runner (forecasting or classification).

Functions:
  - multi_rate_ema(): Compress arbitrarily long history into fixed-width channels
  - isf_normalize_glucose(): Patient-specific ISF normalization
  - glucodensity_head_features(): Fixed-size distributional summary for head injection
  - functional_depth_features(): Atypicality scoring for head injection
  - patient_zscore_normalize(): Per-patient z-score normalization

Design principle: These produce features for HEAD INJECTION (after conv pooling),
not as input channels. Scalar/global features tiled into CNN input channels give
zero temporal gradient (EXP-359, EXP-338 lesson). Head injection avoids this.

References:
  - evidence-synthesis-normalization-long-horizon-2026-04-06.md §1.6
  - forecaster-progress-report-2026-04-06.md §5
  - fda-experiment-proposals-2026-04-05.md §2 (Feature-Problem-Encoding Matrix)
"""

import numpy as np

try:
    from .fda_features import glucodensity as _fda_glucodensity
    from .fda_features import functional_depth as _fda_depth
except ImportError:
    try:
        from fda_features import glucodensity as _fda_glucodensity
        from fda_features import functional_depth as _fda_depth
    except ImportError:
        _fda_glucodensity = None
        _fda_depth = None

GLUCOSE_SCALE = 400.0


# ---------------------------------------------------------------------------
# Multi-Rate Exponential Moving Average
# ---------------------------------------------------------------------------

def compute_ema(series, alpha):
    """Single-rate EMA. Handles NaN by carrying forward."""
    ema = np.empty_like(series, dtype=np.float32)
    ema[0] = series[0] if not np.isnan(series[0]) else 0.0
    for i in range(1, len(series)):
        if np.isnan(series[i]):
            ema[i] = ema[i - 1]
        else:
            ema[i] = alpha * series[i] + (1 - alpha) * ema[i - 1]
    return ema


def multi_rate_ema(glucose, alphas=(0.7, 0.3, 0.1, 0.03)):
    """Compress glucose history into multi-rate EMA channels.

    Each alpha produces one channel of the same length as input.
    Fast alphas (0.7) track recent changes; slow alphas (0.03) capture
    long-term trends. Together they provide scale-adaptive smoothing
    that represents arbitrarily long history in fixed-width format.

    Args:
        glucose: (T,) array of glucose values (raw mg/dL or normalized)
        alphas: Tuple of smoothing factors. Default:
            0.7  → τ ≈ 2 readings  (10 min half-life)
            0.3  → τ ≈ 6 readings  (30 min half-life)
            0.1  → τ ≈ 19 readings (95 min half-life)
            0.03 → τ ≈ 66 readings (5.5 hr half-life)

    Returns:
        (T, len(alphas)) array of EMA channels
    """
    T = len(glucose)
    out = np.zeros((T, len(alphas)), dtype=np.float32)
    for i, alpha in enumerate(alphas):
        out[:, i] = compute_ema(glucose, alpha)
    return out


def multi_rate_ema_batch(windows, glucose_channel=0,
                         alphas=(0.7, 0.3, 0.1, 0.03)):
    """Apply multi-rate EMA to a batch of windows.

    Args:
        windows: (N, T, C) array of windowed data
        glucose_channel: Which channel is glucose
        alphas: EMA smoothing factors

    Returns:
        (N, T, len(alphas)) array of EMA channels
    """
    N, T, C = windows.shape
    out = np.zeros((N, T, len(alphas)), dtype=np.float32)
    for n in range(N):
        out[n] = multi_rate_ema(windows[n, :, glucose_channel], alphas)
    return out


# ---------------------------------------------------------------------------
# ISF-Normalized Glucose
# ---------------------------------------------------------------------------

def isf_normalize_glucose(glucose_mgdl, isf_mgdl_per_u, target_bg=100.0):
    """Normalize glucose relative to patient's insulin sensitivity.

    Converts glucose from mg/dL to "insulin-equivalent units":
        normalized = (glucose - target) / ISF

    A value of +1.0 means glucose is 1 ISF unit above target (i.e., one unit
    of insulin would bring it to target). This makes cross-patient comparison
    meaningful: a reading of +2.0 has the same clinical significance regardless
    of whether the patient's ISF is 30 or 80 mg/dL/U.

    Proven in forecasting: EXP-361 ISF normalization = −0.4 MAE for free.

    Args:
        glucose_mgdl: Glucose in mg/dL (scalar or array)
        isf_mgdl_per_u: ISF in mg/dL per unit insulin (scalar or array)
            For mmol/L profiles, multiply by 18.0182 first.
        target_bg: Target glucose in mg/dL (default 100)

    Returns:
        ISF-normalized glucose (same shape as input)
    """
    isf = np.maximum(np.asarray(isf_mgdl_per_u, dtype=np.float32), 1.0)
    return (np.asarray(glucose_mgdl, dtype=np.float32) - target_bg) / isf


def patient_zscore_normalize(glucose, patient_mean, patient_std):
    """Per-patient z-score normalization with fallback.

    Args:
        glucose: Glucose values (raw or normalized)
        patient_mean: Patient's historical mean glucose
        patient_std: Patient's historical std glucose

    Returns:
        Z-scored glucose. Falls back to glucose/400 if std < 1.
    """
    if patient_std is None or patient_std < 1.0:
        return np.asarray(glucose, dtype=np.float32) / GLUCOSE_SCALE
    return (np.asarray(glucose, dtype=np.float32) - patient_mean) / patient_std


# ---------------------------------------------------------------------------
# Glucodensity Head Features
# ---------------------------------------------------------------------------

def glucodensity_head_features(windows, glucose_channel=0, n_bins=8,
                               glucose_range=(0.0, 1.0)):
    """Compute glucodensity histogram features for classifier head injection.

    Produces a fixed-size (N, n_bins) distributional summary of each window's
    glucose values. Unlike TIR (5-bin), glucodensity captures the full shape
    of the glucose distribution via KDE.

    EXP-330: Glucodensity Silhouette = 0.965 vs TIR = 0.422 (+0.543).
    EXP-338: Head injection Override F1 = 0.880 (+0.006), ECE −16%.

    MUST be injected at classifier head, NOT as conv input channel.

    Args:
        windows: (N, T, C) windowed data (normalized 0-1)
        glucose_channel: Which channel is glucose
        n_bins: Number of histogram bins (8 = proven, 50 = full resolution)
        glucose_range: (min, max) for bin edges

    Returns:
        (N, n_bins) array of density features, L1-normalized per sample
    """
    if _fda_glucodensity is not None:
        glucose = windows[:, :, glucose_channel]
        densities = _fda_glucodensity(glucose, n_bins=n_bins,
                                       glucose_range=glucose_range)
        # L1-normalize so each row sums to ~1
        row_sums = densities.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-8)
        return (densities / row_sums).astype(np.float32)

    # Fallback: simple histogram if scikit-fda not available
    N = windows.shape[0]
    bins = np.linspace(glucose_range[0], glucose_range[1], n_bins + 1)
    out = np.zeros((N, n_bins), dtype=np.float32)
    for i in range(N):
        vals = windows[i, :, glucose_channel]
        vals = vals[~np.isnan(vals)]
        if len(vals) > 0:
            hist, _ = np.histogram(vals, bins=bins)
            out[i] = hist / max(len(vals), 1)
    return out


# ---------------------------------------------------------------------------
# Functional Depth Head Features
# ---------------------------------------------------------------------------

def functional_depth_features(windows, glucose_channel=0):
    """Compute functional depth (atypicality) for classifier head injection.

    Modified Band Depth scores each window on [0, 1]:
    - High depth (→1): typical/central glucose trajectory
    - Low depth (→0): atypical/outlier trajectory (hypo precursor!)

    EXP-335: Q1 depth = 33.7% hypo rate vs Q4 = 0.3% (112× enrichment).

    MUST be injected at classifier head, NOT as conv input channel.

    Args:
        windows: (N, T, C) windowed data
        glucose_channel: Which channel is glucose

    Returns:
        (N, 1) array of depth scores for head concatenation
    """
    glucose = windows[:, :, glucose_channel]

    if _fda_depth is not None:
        depths = _fda_depth(glucose)
        return depths.reshape(-1, 1).astype(np.float32)

    # Fallback: use L2 distance to mean as proxy (anti-correlated with depth)
    mean_curve = np.nanmean(glucose, axis=0)
    l2_dist = np.sqrt(np.nanmean((glucose - mean_curve) ** 2, axis=1))
    # Invert and normalize to [0, 1] range
    max_dist = np.maximum(l2_dist.max(), 1e-8)
    proxy_depth = 1.0 - (l2_dist / max_dist)
    return proxy_depth.reshape(-1, 1).astype(np.float32)


# ---------------------------------------------------------------------------
# Combined Head Features
# ---------------------------------------------------------------------------

def compute_head_features(windows, glucose_channel=0, n_gd_bins=8,
                          include_glucodensity=True, include_depth=True):
    """Compute all head-injection features in one call.

    Returns:
        (N, D) array where D depends on which features are enabled:
          glucodensity: +n_gd_bins (default 8)
          depth: +1
        Also returns list of feature names.
    """
    features = []
    names = []

    if include_glucodensity:
        gd = glucodensity_head_features(windows, glucose_channel, n_gd_bins)
        features.append(gd)
        names.extend([f'gd_bin_{i}' for i in range(n_gd_bins)])

    if include_depth:
        depth = functional_depth_features(windows, glucose_channel)
        features.append(depth)
        names.append('func_depth')

    if not features:
        N = windows.shape[0]
        return np.zeros((N, 0), dtype=np.float32), names

    return np.concatenate(features, axis=1).astype(np.float32), names
