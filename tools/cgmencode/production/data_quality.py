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
from typing import Optional

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


def detect_compression_lows(
    glucose: np.ndarray,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    *,
    drop_threshold: float = 30.0,
    drop_window_steps: int = 3,        # 15 min @ 5-min cadence
    low_threshold: float = 60.0,
    recovery_threshold: float = 25.0,
    recovery_window_steps: int = 6,    # 30 min
    insulin_window_steps: int = 24,    # ±2 h
    insulin_dose_threshold: float = 0.3,
    carb_window_steps: int = 6,
) -> np.ndarray:
    """Flag suspected compression-low (pressure-on-sensor) artifacts.

    Signature, conservative:
      * BG drops by ``drop_threshold`` mg/dL in ``drop_window_steps``,
      * reaches ``< low_threshold`` mg/dL,
      * recovers by ``recovery_threshold`` mg/dL within
        ``recovery_window_steps``,
      * NO bolus > ``insulin_dose_threshold`` U in
        [-insulin_window_steps, 0],
      * NO real carbs (>5 g) in [-carb_window_steps, recovery window].

    These criteria are deliberately conservative — only flag drops that
    have no plausible insulin/carb explanation.

    Args:
        glucose: (N,) glucose (mg/dL); NaNs tolerated.
        bolus, carbs: optional (N,) arrays for cause attribution.

    Returns:
        Indices of glucose samples flagged as artifact-low nadirs.
    """
    N = len(glucose)
    if N < drop_window_steps + recovery_window_steps + 1:
        return np.array([], dtype=int)

    flagged: list[int] = []
    g = np.asarray(glucose, dtype=float)

    for i in range(drop_window_steps, N - recovery_window_steps):
        gi = g[i]
        if not np.isfinite(gi) or gi >= low_threshold:
            continue

        pre = g[i - drop_window_steps:i + 1]
        pre_valid = pre[np.isfinite(pre)]
        if pre_valid.size < 2:
            continue
        peak_pre = float(np.max(pre_valid))
        if (peak_pre - gi) < drop_threshold:
            continue

        post = g[i:i + recovery_window_steps + 1]
        post_valid = post[np.isfinite(post)]
        if post_valid.size < 2:
            continue
        peak_post = float(np.max(post_valid))
        if (peak_post - gi) < recovery_threshold:
            continue

        if bolus is not None:
            b_lo = max(0, i - insulin_window_steps)
            b_window = bolus[b_lo:i + 1]
            b_valid = b_window[np.isfinite(b_window)]
            if b_valid.size and float(np.max(b_valid)) > insulin_dose_threshold:
                continue

        if carbs is not None:
            c_lo = max(0, i - carb_window_steps)
            c_hi = min(N, i + recovery_window_steps + 1)
            c_window = carbs[c_lo:c_hi]
            c_valid = c_window[np.isfinite(c_window)]
            if c_valid.size and float(np.nansum(c_valid)) > 5.0:
                continue

        flagged.append(i)

    return np.array(flagged, dtype=int)


def clean_glucose(glucose: np.ndarray,
                  sigma_mult: float = DEFAULT_SIGMA,
                  *,
                  bolus: Optional[np.ndarray] = None,
                  carbs: Optional[np.ndarray] = None,
                  detect_artifacts: bool = True) -> CleanedData:
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

    if detect_artifacts:
        compression_lows = detect_compression_lows(
            cleaned, bolus=bolus, carbs=carbs)
    else:
        compression_lows = np.array([], dtype=int)

    return CleanedData(
        glucose=cleaned,
        original_glucose=glucose.copy(),
        spike_indices=spikes,
        n_spikes=len(spikes),
        sigma_threshold=sigma_mult,
        compression_low_indices=compression_lows,
        n_compression_lows=int(len(compression_lows)),
    )
