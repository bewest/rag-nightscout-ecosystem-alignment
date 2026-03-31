"""
physics_model.py — Simple physiological glucose model using IOB/COB dynamics.

Implements a first-order forward integration from Loop-reported IOB/COB:

    BG_pred(t+1) = BG_pred(t) - ΔIOB(t)*ISF + ΔCOB(t)*(ISF/CR)

where ΔIOB = IOB(t) - IOB(t+1) is insulin absorbed per step, and
      ΔCOB = COB(t) - COB(t+1) is carbs absorbed per step.

This is the "L1 Physics" layer in the ML composition architecture.
The residual (actual - physics_predicted) captures what physics can't explain:
sensor noise, exercise, stress, compression artifacts, model mismatch.
Training the AE on residuals (L3) should be easier than raw glucose.

Usage:
    from tools.cgmencode.physics_model import compute_residual_windows

    residual_windows, physics_windows = compute_residual_windows(
        windows_norm, isf=40.0, cr=10.0)
"""

import numpy as np
from .schema import (
    IDX_GLUCOSE, IDX_IOB, IDX_COB,
    NORMALIZATION_SCALES, SCALE_ARRAY,
)

# Residual normalization: residuals are typically in [-100, +100] mg/dL
# Using 200 keeps normalized values in roughly [-0.5, 0.5]
RESIDUAL_SCALE = 200.0


def physics_predict_window(window_raw_glucose, window_raw_iob, window_raw_cob,
                           isf=40.0, cr=10.0):
    """Forward-integrate glucose prediction for a single window.

    Args:
        window_raw_glucose: (T,) actual glucose in mg/dL
        window_raw_iob: (T,) IOB in units
        window_raw_cob: (T,) COB in grams
        isf: Insulin Sensitivity Factor (mg/dL per unit)
        cr: Carb Ratio (grams per unit)

    Returns:
        physics_pred: (T,) predicted glucose in mg/dL
    """
    T = len(window_raw_glucose)
    pred = np.zeros(T)
    pred[0] = window_raw_glucose[0]  # start from actual

    for t in range(1, T):
        # Insulin absorbed this 5-min step (positive = glucose drop)
        delta_iob = window_raw_iob[t - 1] - window_raw_iob[t]
        # Carbs absorbed this 5-min step (positive = glucose rise)
        delta_cob = window_raw_cob[t - 1] - window_raw_cob[t]

        insulin_effect = -delta_iob * isf       # lowers BG
        carb_effect = delta_cob * (isf / cr)    # raises BG

        pred[t] = pred[t - 1] + insulin_effect + carb_effect

    return pred


def compute_residual_windows(windows_norm, isf=40.0, cr=10.0):
    """Compute physics prediction and residual for each window.

    Takes normalized windows (from CGMDataset), denormalizes to compute
    physics prediction, then creates residual windows where glucose channel
    is replaced with (actual - physics_predicted) / RESIDUAL_SCALE.

    Args:
        windows_norm: (N, T, 8) array of normalized feature windows
        isf: Insulin Sensitivity Factor (mg/dL per unit)
        cr: Carb Ratio (grams per unit)

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
        # Denormalize to raw values
        glucose_raw = windows_norm[i, :, IDX_GLUCOSE] * glucose_scale
        iob_raw = windows_norm[i, :, IDX_IOB] * iob_scale
        cob_raw = windows_norm[i, :, IDX_COB] * cob_scale

        # Forward-integrate physics model
        pred = physics_predict_window(glucose_raw, iob_raw, cob_raw, isf, cr)
        physics_pred_raw[i] = pred

        # Residual in mg/dL
        residual = glucose_raw - pred
        all_residuals.append(residual)

        # Replace glucose channel with normalized residual
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
    }

    return residual_windows, physics_pred_raw, stats


def residual_to_glucose(residual_norm, physics_pred_raw):
    """Convert reconstructed residual back to glucose in mg/dL.

    Args:
        residual_norm: (T,) or (N, T) normalized residual from AE output
        physics_pred_raw: (T,) or (N, T) physics prediction in mg/dL

    Returns:
        glucose_mgdl: reconstructed glucose in mg/dL
    """
    return physics_pred_raw + residual_norm * RESIDUAL_SCALE
