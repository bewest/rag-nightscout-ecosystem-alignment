"""
data_quality.py — Spike cleaning for CGM glucose data.

Research basis: EXP-681 (spike detection), EXP-691 (cleaned model v2)
Key finding: σ=2.0 universal threshold yields +52% R² (0.304→0.461)

Algorithm:
  1. Compute residual jumps |Δglucose[t] - Δglucose[t-1]|
  2. Flag where jump > μ + 2σ (not default 3σ — research-proven)
  3. Linear interpolation over flagged regions
"""

from __future__ import annotations

import numpy as np

from .types import CleanedData


# Research-validated: σ=2.0 is universally optimal (EXP-681, EXP-691)
DEFAULT_SIGMA = 2.0


def detect_spikes(glucose: np.ndarray,
                  sigma_mult: float = DEFAULT_SIGMA) -> np.ndarray:
    """Detect sensor spikes via sigma threshold on residual jumps.

    Adapted from exp_autoresearch_681.py:107-117 with σ default
    changed from 3.0 to research-validated 2.0.

    Args:
        glucose: (N,) raw glucose values (mg/dL). NaNs are tolerated.
        sigma_mult: multiplier for threshold = μ + sigma_mult × σ

    Returns:
        Array of indices flagged as spikes.
    """
    if len(glucose) < 100:
        return np.array([], dtype=int)

    jumps = np.abs(np.diff(glucose))
    valid = np.isfinite(jumps)
    if valid.sum() < 100:
        return np.array([], dtype=int)

    mu = np.nanmean(jumps[valid])
    sigma = np.nanstd(jumps[valid])
    threshold = mu + sigma_mult * sigma
    spike_idx = np.where(valid & (jumps > threshold))[0] + 1
    return spike_idx


def interpolate_spikes(glucose: np.ndarray,
                       spike_idx: np.ndarray) -> np.ndarray:
    """Linear interpolation over detected spike positions.

    For contiguous spike regions, finds nearest non-spike anchors
    on each side and interpolates. Edge spikes use nearest valid value.

    Adapted from exp_autoresearch_681.py:120-138.

    Args:
        glucose: (N,) glucose values to clean.
        spike_idx: indices to interpolate over.

    Returns:
        (N,) cleaned glucose array.
    """
    if len(spike_idx) == 0:
        return glucose.copy()

    cleaned = glucose.copy()
    spike_set = set(spike_idx.tolist())

    for idx in spike_idx:
        # Walk left to find non-spike anchor
        left = idx - 1
        while left >= 0 and left in spike_set:
            left -= 1
        # Walk right to find non-spike anchor
        right = idx + 1
        while right < len(cleaned) and right in spike_set:
            right += 1

        # Interpolate between anchors
        if (left >= 0 and right < len(cleaned)
                and np.isfinite(cleaned[left])
                and np.isfinite(cleaned[right])):
            frac = (idx - left) / max(right - left, 1)
            cleaned[idx] = cleaned[left] + frac * (cleaned[right] - cleaned[left])
        elif left >= 0 and np.isfinite(cleaned[left]):
            cleaned[idx] = cleaned[left]
        elif right < len(cleaned) and np.isfinite(cleaned[right]):
            cleaned[idx] = cleaned[right]

    return cleaned


def clean_glucose(glucose: np.ndarray,
                  sigma_mult: float = DEFAULT_SIGMA) -> CleanedData:
    """Full spike-cleaning pipeline: detect + interpolate.

    This is the primary public API for data quality processing.

    Args:
        glucose: (N,) raw CGM glucose values (mg/dL).
        sigma_mult: sigma threshold multiplier (default 2.0).

    Returns:
        CleanedData with cleaned glucose, spike indices, and metadata.
    """
    spikes = detect_spikes(glucose, sigma_mult)
    cleaned = interpolate_spikes(glucose, spikes)

    return CleanedData(
        glucose=cleaned,
        original_glucose=glucose.copy(),
        spike_indices=spikes,
        n_spikes=len(spikes),
        sigma_threshold=sigma_mult,
    )
