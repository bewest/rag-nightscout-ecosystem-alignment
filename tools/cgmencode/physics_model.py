"""
physics_model.py — Physiological glucose models for residual learning.

Three physics levels:
  1. Simple: ΔIOB×ISF - ΔCOB×ISF/CR (current, 13.89 MAE)
  2. Enhanced: + liver glucose production + circadian rhythm + insulin suppression
  3. UVA/Padova: full 14-state ODE via Node.js replay (uva_replay.js)

The residual (actual - physics_predicted) captures what physics can't explain.
Training the AE on residuals (L3) is dramatically easier than raw glucose.

Usage:
    from tools.cgmencode.physics_model import compute_residual_windows

    # Simple physics
    residual_windows, physics_pred, stats = compute_residual_windows(
        windows_norm, isf=40.0, cr=10.0, level='simple')

    # Enhanced with liver + circadian
    residual_windows, physics_pred, stats = compute_residual_windows(
        windows_norm, isf=40.0, cr=10.0, weight=70.0, level='enhanced')

    # UVA/Padova (from pre-computed predictions)
    residual_windows, physics_pred, stats = compute_residual_windows_uva(
        windows_norm, uva_grid, window_indices)
"""

import json
import numpy as np
from .schema import (
    IDX_GLUCOSE, IDX_IOB, IDX_COB, IDX_NET_BASAL, IDX_TIME_SIN, IDX_TIME_COS,
    NORMALIZATION_SCALES,
)

# Residual normalization: residuals are typically in [-100, +100] mg/dL
# Using 200 keeps normalized values in roughly [-0.5, 0.5]
RESIDUAL_SCALE = 200.0

# ── Liver glucose production constants (from cgmsim-lib src/liver.ts) ──
LIVER_BASE_RATE = 1.5       # mg/dL per 5-min step at zero insulin
LIVER_HILL_K = 1.0          # half-max IOB for suppression (units)
LIVER_HILL_N = 2.0          # Hill coefficient (steepness)
CIRCADIAN_AMPLITUDE = 0.15  # ±15% dawn/dusk variation
CIRCADIAN_PEAK_HOUR = 5.0   # peak liver output at 5 AM (dawn phenomenon)


def _hour_from_time_encoding(time_sin, time_cos):
    """Extract hour of day from sin/cos time encoding."""
    radians = np.arctan2(time_sin, time_cos)
    hours = radians * 24.0 / (2.0 * np.pi)
    return hours % 24.0


def _liver_production(iob, hour):
    """Hepatic glucose production: base rate × insulin suppression × circadian.

    Based on cgmsim-lib Hill equation (src/liver.ts):
      suppression = IOB^n / (IOB^n + k^n)
      liver_output = base * (1 - suppression) * circadian
    """
    suppression = (iob ** LIVER_HILL_N) / (iob ** LIVER_HILL_N + LIVER_HILL_K ** LIVER_HILL_N + 1e-8)
    phase = 2.0 * np.pi * (hour - CIRCADIAN_PEAK_HOUR) / 24.0
    circadian = 1.0 + CIRCADIAN_AMPLITUDE * np.cos(phase)
    return LIVER_BASE_RATE * (1.0 - suppression) * circadian


def physics_predict_window(window_raw_glucose, window_raw_iob, window_raw_cob,
                           isf=40.0, cr=10.0):
    """Level 1 (Simple): ΔIOB×ISF - ΔCOB×ISF/CR forward integration."""
    T = len(window_raw_glucose)
    pred = np.zeros(T)
    pred[0] = window_raw_glucose[0]

    for t in range(1, T):
        delta_iob = window_raw_iob[t - 1] - window_raw_iob[t]
        delta_cob = window_raw_cob[t - 1] - window_raw_cob[t]
        insulin_effect = -delta_iob * isf
        carb_effect = delta_cob * (isf / cr)
        pred[t] = pred[t - 1] + insulin_effect + carb_effect

    return pred


def enhanced_predict_window(window_raw_glucose, window_raw_iob, window_raw_cob,
                            window_time_sin, window_time_cos,
                            isf=40.0, cr=10.0):
    """Level 2 (Enhanced): Simple + liver production + circadian rhythm.

    Adds hepatic glucose production modulated by:
    - Insulin suppression (Hill equation on IOB)
    - Circadian rhythm (dawn phenomenon peaks ~5 AM)
    """
    T = len(window_raw_glucose)
    pred = np.zeros(T)
    pred[0] = window_raw_glucose[0]

    for t in range(1, T):
        delta_iob = window_raw_iob[t - 1] - window_raw_iob[t]
        delta_cob = window_raw_cob[t - 1] - window_raw_cob[t]
        insulin_effect = -delta_iob * isf
        carb_effect = delta_cob * (isf / cr)

        hour = _hour_from_time_encoding(window_time_sin[t], window_time_cos[t])
        liver = _liver_production(window_raw_iob[t], hour)

        pred[t] = pred[t - 1] + insulin_effect + carb_effect + liver

    return pred


# ── UVA/Padova prediction loading ──

def load_uva_predictions(json_path):
    """Load pre-computed UVA/Padova predictions from uva_replay.js output.

    Returns:
        uva_bg: dict mapping epoch_ms → predicted_bg (mg/dL)
        metadata: dict with model/patient info
    """
    with open(json_path) as f:
        data = json.load(f)
    uva_bg = {}
    for p in data['predictions']:
        uva_bg[p['time']] = p['predicted_bg']
    return uva_bg, data.get('metadata', {})


def compute_residual_windows(windows_norm, isf=40.0, cr=10.0, level='simple'):
    """Compute physics prediction and residual for each window.

    Args:
        windows_norm: (N, T, 8) array of normalized feature windows
        isf: Insulin Sensitivity Factor (mg/dL per unit)
        cr: Carb Ratio (grams per unit)
        level: 'simple' (ΔIOB/ΔCOB only) or 'enhanced' (+ liver + circadian)

    Returns:
        residual_windows: (N, T, 8) — glucose replaced with normalized residual
        physics_pred_raw: (N, T) — physics predictions in mg/dL (for eval)
        stats: dict with residual statistics
    """
    N, T, F = windows_norm.shape
    glucose_scale = NORMALIZATION_SCALES['glucose']  # 400
    iob_scale = NORMALIZATION_SCALES['iob']          # 20
    cob_scale = NORMALIZATION_SCALES['cob']          # 100

    residual_windows = windows_norm.copy()
    physics_pred_raw = np.zeros((N, T))
    all_residuals = []

    for i in range(N):
        glucose_raw = windows_norm[i, :, IDX_GLUCOSE] * glucose_scale
        iob_raw = windows_norm[i, :, IDX_IOB] * iob_scale
        cob_raw = windows_norm[i, :, IDX_COB] * cob_scale

        if level == 'enhanced':
            time_sin = windows_norm[i, :, IDX_TIME_SIN]
            time_cos = windows_norm[i, :, IDX_TIME_COS]
            pred = enhanced_predict_window(
                glucose_raw, iob_raw, cob_raw, time_sin, time_cos, isf, cr)
        else:
            pred = physics_predict_window(glucose_raw, iob_raw, cob_raw, isf, cr)

        physics_pred_raw[i] = pred
        residual = glucose_raw - pred
        all_residuals.append(residual)
        residual_windows[i, :, IDX_GLUCOSE] = residual / RESIDUAL_SCALE

    all_residuals = np.concatenate(all_residuals)
    stats = {
        'mean': float(np.mean(all_residuals)),
        'std': float(np.std(all_residuals)),
        'min': float(np.min(all_residuals)),
        'max': float(np.max(all_residuals)),
        'p5': float(np.percentile(all_residuals, 5)),
        'p95': float(np.percentile(all_residuals, 95)),
        'scale': RESIDUAL_SCALE,
        'level': level,
    }

    return residual_windows, physics_pred_raw, stats


def compute_residual_windows_uva(windows_norm, uva_bg_grid, window_stride=None):
    """Compute differential residuals using UVA/Padova predictions.

    Uses the differential approach: for each window starting at index j,
      physics_pred(t) = actual_glucose(0) + [UVA(j+t) - UVA(j)]
      residual(t) = actual_glucose(t) - physics_pred(t)

    This captures UVA/Padova's prediction of glucose CHANGE from the window
    start, anchored to the actual glucose at t=0. Avoids absolute drift.

    Args:
        windows_norm: (N, T, 8) normalized feature windows
        uva_bg_grid: (G,) array of UVA predicted BG on the 5-min grid,
                     aligned with the feature grid
        window_stride: stride between windows (default: T // 2 for 50% overlap)

    Returns:
        residual_windows: (N, T, 8) with glucose → normalized residual
        physics_pred_raw: (N, T) UVA-derived predictions in mg/dL
        stats: dict with residual statistics
    """
    N, T, F = windows_norm.shape
    glucose_scale = NORMALIZATION_SCALES['glucose']
    if window_stride is None:
        window_stride = T // 2

    residual_windows = windows_norm.copy()
    physics_pred_raw = np.zeros((N, T))
    all_residuals = []
    skipped = 0

    for i in range(N):
        j = i * window_stride  # grid index of window start
        glucose_raw = windows_norm[i, :, IDX_GLUCOSE] * glucose_scale

        if j + T > len(uva_bg_grid):
            # Window extends past UVA predictions — use simple fallback
            physics_pred_raw[i] = glucose_raw
            residual_windows[i, :, IDX_GLUCOSE] = 0.0
            skipped += 1
            continue

        uva_window = uva_bg_grid[j:j + T]
        uva_delta = uva_window - uva_window[0]  # change from window start
        pred = glucose_raw[0] + uva_delta         # anchor to actual start BG
        pred = np.clip(pred, 40.0, 400.0)

        physics_pred_raw[i] = pred
        residual = glucose_raw - pred
        all_residuals.append(residual)
        residual_windows[i, :, IDX_GLUCOSE] = residual / RESIDUAL_SCALE

    if all_residuals:
        all_residuals = np.concatenate(all_residuals)
    else:
        all_residuals = np.zeros(1)

    stats = {
        'mean': float(np.mean(all_residuals)),
        'std': float(np.std(all_residuals)),
        'min': float(np.min(all_residuals)),
        'max': float(np.max(all_residuals)),
        'p5': float(np.percentile(all_residuals, 5)),
        'p95': float(np.percentile(all_residuals, 95)),
        'scale': RESIDUAL_SCALE,
        'level': 'uva',
        'skipped_windows': skipped,
    }

    return residual_windows, physics_pred_raw, stats


def align_uva_to_grid(uva_bg_dict, grid_timestamps_ms, fill_value=None):
    """Align UVA/Padova predictions to the feature grid by timestamp.

    Args:
        uva_bg_dict: dict mapping epoch_ms → predicted_bg
        grid_timestamps_ms: (G,) array of grid timestamps in epoch_ms
        fill_value: value for missing UVA predictions (default: forward fill)

    Returns:
        uva_grid: (G,) array of UVA predicted BG aligned to feature grid
    """
    G = len(grid_timestamps_ms)
    uva_grid = np.full(G, np.nan)

    for i, ts in enumerate(grid_timestamps_ms):
        if ts in uva_bg_dict:
            uva_grid[i] = uva_bg_dict[ts]

    # Forward-fill NaN gaps (UVA predictions are on same 5-min grid)
    valid = np.where(~np.isnan(uva_grid))[0]
    if len(valid) > 0:
        for i in range(G):
            if np.isnan(uva_grid[i]):
                # Find nearest previous valid
                prev = valid[valid <= i]
                if len(prev) > 0:
                    uva_grid[i] = uva_grid[prev[-1]]
                else:
                    # Before first UVA prediction — use first valid
                    uva_grid[i] = uva_grid[valid[0]]

    return uva_grid


def residual_to_glucose(residual_norm, physics_pred_raw):
    """Convert reconstructed residual back to glucose in mg/dL.

    Args:
        residual_norm: (T,) or (N, T) normalized residual from AE output
        physics_pred_raw: (T,) or (N, T) physics prediction in mg/dL

    Returns:
        glucose_mgdl: reconstructed glucose in mg/dL
    """
    return physics_pred_raw + residual_norm * RESIDUAL_SCALE
