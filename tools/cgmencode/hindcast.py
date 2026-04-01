#!/usr/bin/env python3
"""
hindcast.py — Retrospective inference tool for cgmencode models.

Point at cached Nightscout data, pick a historical time, and test model
inference through multiple frames — not just forecasting.

Inference Frames:
    forecast       Predict future glucose from history (tests extrapolation)
    reconstruct    Reconstruct full window (tests representation quality)
    anomaly        Rank windows by reconstruction error (high = unusual)
    counterfactual Zero out treatment actions, compare with/without
    impute         Mask glucose values, predict from IOB/actions alone
    similarity     Find past windows with similar model residual patterns

Usage:
    # Forecast: predict future from history context
    python3 -m tools.cgmencode.hindcast \\
        --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \\
        --checkpoint externals/experiments/ae_best.pth \\
        --model ae \\
        --at "2026-02-08T14:00:00Z"

    # Anomaly: find unusual metabolic patterns
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint checkpoints/ae_best.pth \\
        --mode anomaly --top 10

    # Counterfactual: what if no treatment?
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint checkpoints/ae_best.pth \\
        --mode counterfactual --pick interesting

    # Imputation: can model infer glucose from IOB/actions alone?
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint checkpoints/ae_best.pth \\
        --mode impute --mask-fraction 0.5

    # Similarity: find metabolically similar past events
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint checkpoints/ae_best.pth \\
        --mode similarity --at "2026-01-15T12:00:00Z"

    # Scan multiple interesting windows (forecast/reconstruct modes)
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint checkpoints/ae_best.pth \\
        --scan 10

    # Compare two models side-by-side
    python3 -m tools.cgmencode.hindcast \\
        --data /path/to/ns-data \\
        --checkpoint externals/experiments/ae_best.pth \\
        --checkpoint2 externals/experiments/ae_010b_grouped_w12.pth \\
        --model ae --model2 grouped \\
        --at "2026-02-01T12:00:00Z"
"""

import argparse
import json
import re
import sys
import os
import numpy as np
import pandas as pd
import torch
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from .schema import (
    NORMALIZATION_SCALES, NUM_FEATURES, FEATURE_NAMES,
    IDX_GLUCOSE, ALL_VALS_IDX, IDX_TIME_SIN, IDX_TIME_COS,
    STATE_IDX, ACTION_IDX, TIME_IDX,
)
from .model import CGMTransformerAE, CGMGroupedEncoder
from .real_data_adapter import build_nightscout_grid

SCALE = NORMALIZATION_SCALES

# Models we can load for hindcast
HINDCAST_MODELS = {
    'ae': {
        'class': CGMTransformerAE,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
    },
    'grouped': {
        'class': CGMGroupedEncoder,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
    },
}


def load_model(checkpoint_path: str, model_type: str = 'ae') -> torch.nn.Module:
    """Load a trained model from checkpoint."""
    ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=True)

    # Handle both raw state_dict and wrapped checkpoint formats
    if isinstance(ckpt, dict) and 'model_state' in ckpt:
        state_dict = ckpt['model_state']
        config = ckpt.get('config', {})
    else:
        state_dict = ckpt
        config = {}

    reg = HINDCAST_MODELS[model_type]
    kwargs = config if config else reg['kwargs']
    model = reg['class'](**kwargs)
    model.load_state_dict(state_dict)
    model.eval()

    param_count = sum(p.numel() for p in model.parameters())
    return model, param_count, ckpt if isinstance(ckpt, dict) else {}


def parse_time(time_str: str, reference_time: pd.Timestamp) -> pd.Timestamp:
    """Parse human-friendly time strings.

    Supports:
        - ISO 8601: "2026-02-08T14:00:00Z"
        - Relative:  "8 hours ago", "30 minutes ago", "2 days ago"
        - Named:     "yesterday 14:00", "yesterday"
    """
    time_str = time_str.strip()

    # Relative: "N hours/minutes/days ago"
    m = re.match(r'^(\d+)\s*(hours?|minutes?|mins?|days?)\s*ago$', time_str, re.IGNORECASE)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith('hour'):
            return reference_time - pd.Timedelta(hours=n)
        elif unit.startswith('min'):
            return reference_time - pd.Timedelta(minutes=n)
        elif unit.startswith('day'):
            return reference_time - pd.Timedelta(days=n)

    # "yesterday" or "yesterday HH:MM"
    if time_str.lower().startswith('yesterday'):
        rest = time_str[9:].strip()
        yesterday = reference_time - pd.Timedelta(days=1)
        if rest:
            parts = rest.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            yesterday = yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return yesterday

    # ISO 8601 or any pandas-parseable format
    try:
        ts = pd.Timestamp(time_str)
        if ts.tz is None:
            ts = ts.tz_localize('UTC')
        return ts
    except Exception:
        raise ValueError(f"Cannot parse time: '{time_str}'")


def find_loop_prediction(data_path: str, target_time: pd.Timestamp
                          ) -> Optional[Dict]:
    """Find Loop's glucose prediction closest to target_time from devicestatus."""
    ds_path = Path(data_path) / 'devicestatus.json'
    if not ds_path.exists():
        return None

    with open(ds_path) as f:
        ds_list = json.load(f)

    best = None
    best_delta = float('inf')

    for ds in ds_list:
        loop = ds.get('loop', {})
        predicted = loop.get('predicted', {})
        if not predicted or 'values' not in predicted:
            continue

        ts_str = ds.get('created_at')
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str)
        if ts.tz is None:
            ts = ts.tz_localize('UTC')

        delta = abs((ts - target_time).total_seconds())
        if delta < best_delta:
            best_delta = delta
            best = {
                'timestamp': ts,
                'start': pd.Timestamp(predicted['startDate']),
                'values': predicted['values'],
                'iob': loop.get('iob', {}).get('iob'),
                'cob': loop.get('cob', {}).get('cob'),
                'delta_seconds': delta,
            }

    # Only accept if within 10 minutes
    if best and best['delta_seconds'] <= 600:
        return best
    return None


def find_interesting_windows(df: pd.DataFrame, features: np.ndarray,
                              n: int = 5, history: int = 12, horizon: int = 12
                              ) -> List[int]:
    """Find time indices where interesting things happen (meals, corrections, swings)."""
    glucose = df['glucose'].values
    total_len = history + horizon
    candidates = []

    for i in range(history, len(glucose) - horizon):
        window = glucose[i - history:i + horizon]
        if np.any(np.isnan(window)):
            continue

        # Score by: glucose variability + bolus/carb activity
        glucose_range = np.nanmax(window) - np.nanmin(window)
        bolus_sum = df['bolus'].values[i - history:i + horizon].sum()
        carbs_sum = df['carbs'].values[i - history:i + horizon].sum()
        activity = bolus_sum * 10 + carbs_sum

        # Prefer windows with both activity AND glucose movement
        score = glucose_range * (1 + activity)
        candidates.append((score, i))

    candidates.sort(reverse=True)
    # Space them out: don't pick windows too close together
    selected = []
    for score, idx in candidates:
        if all(abs(idx - s) > total_len for s in selected):
            selected.append(idx)
            if len(selected) >= n:
                break

    return selected


def run_hindcast(model: torch.nn.Module, features: np.ndarray,
                  center_idx: int, history: int = 12, horizon: int = 12,
                  mode: str = 'forecast'
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """Run model inference on a hindcast window.

    Modes:
        'forecast':     History has real data, future state/action zeroed.
                        Tests: can the model predict what happens next?
        'reconstruct':  Full window has real data. Model reconstructs it.
                        Tests: how well does the model represent this pattern?

    Returns (pred_glucose, recon_history) in mg/dL.
        pred_glucose: horizon-length array of predicted future glucose
        recon_history: history-length array of reconstructed history glucose
    """
    start = center_idx - history
    end = center_idx + horizon
    window = features[start:end].copy()

    if mode == 'forecast':
        # Zero out future state/action, keep time features
        window[history:, :6] = 0.0
    # else: reconstruct mode — full window has real data

    x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)

    with torch.no_grad():
        output = model(x)

    out = output[0].numpy()
    pred_glucose = out[history:, IDX_GLUCOSE] * SCALE['glucose']
    recon_history = out[:history, IDX_GLUCOSE] * SCALE['glucose']
    return pred_glucose, recon_history


def extract_embeddings(model: torch.nn.Module, x: torch.Tensor) -> np.ndarray:
    """Extract transformer encoder embeddings from model.

    Works for both CGMTransformerAE and CGMGroupedEncoder by replaying the
    forward pass up to (but not including) the output projection.

    Returns (SeqLen, d_model) numpy array.
    """
    with torch.no_grad():
        if isinstance(model, CGMGroupedEncoder):
            state = model.state_proj(x[..., :3])
            action = model.action_proj(x[..., 3:6])
            time = model.time_proj(x[..., 6:8])
            z = torch.cat([state, action, time], dim=-1)
        else:
            z = model.input_projection(x)
        z = model.pos_encoder(z)
        encoded = model.transformer_encoder(z)
    return encoded[0].numpy()  # drop batch dim


def run_anomaly_scan(model: torch.nn.Module, features: np.ndarray,
                     df: pd.DataFrame, history: int = 12, horizon: int = 12,
                     top_n: int = 10, stride: int = 6
                     ) -> List[Dict]:
    """Scan all windows, rank by reconstruction error (anomaly score).

    High reconstruction error = the model can't represent this pattern well,
    meaning it's unusual/anomalous relative to training data.
    """
    total_len = history + horizon
    results = []

    for start in range(0, len(features) - total_len, stride):
        window = features[start:start + total_len]
        actual_g = df['glucose'].values[start:start + total_len]

        if np.any(np.isnan(actual_g)):
            continue

        x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            output = model(x)
        recon = output[0].numpy()

        # Per-channel reconstruction error
        recon_glucose = recon[:, IDX_GLUCOSE] * SCALE['glucose']
        mae = np.mean(np.abs(recon_glucose - actual_g))

        # Also compute per-channel errors for context
        recon_iob = recon[:, 1] * SCALE['iob']
        actual_iob = df['iob'].values[start:start + total_len]
        iob_mae = np.mean(np.abs(recon_iob - actual_iob))

        center_idx = start + history
        results.append({
            'center_idx': center_idx,
            'time': str(df.index[center_idx]),
            'glucose_mae': float(mae),
            'iob_mae': float(iob_mae),
            'bg_range': float(np.max(actual_g) - np.min(actual_g)),
            'bg_mean': float(np.mean(actual_g)),
            'bg_at_center': float(actual_g[history]),
        })

    results.sort(key=lambda r: r['glucose_mae'], reverse=True)
    return results[:top_n]


def run_counterfactual(model: torch.nn.Module, features: np.ndarray,
                       center_idx: int, history: int = 12, horizon: int = 12
                       ) -> Tuple[np.ndarray, np.ndarray]:
    """Run counterfactual: what would glucose look like WITHOUT treatment?

    Zeroes out action channels (basal, bolus, carbs) in the entire window,
    keeping state (glucose, IOB, COB) and time features intact.
    The model reconstructs what it thinks would happen without those actions.

    Returns (actual_recon, counterfactual_recon) in mg/dL.
    """
    start = center_idx - history
    end = center_idx + horizon

    # Normal reconstruction (with actions)
    window_real = features[start:end].copy()
    x_real = torch.tensor(window_real, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        out_real = model(x_real)
    recon_real = out_real[0].numpy()[:, IDX_GLUCOSE] * SCALE['glucose']

    # Counterfactual: zero out action channels
    window_cf = features[start:end].copy()
    window_cf[:, ACTION_IDX] = 0.0
    x_cf = torch.tensor(window_cf, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        out_cf = model(x_cf)
    recon_cf = out_cf[0].numpy()[:, IDX_GLUCOSE] * SCALE['glucose']

    return recon_real, recon_cf


def run_imputation(model: torch.nn.Module, features: np.ndarray,
                   center_idx: int, history: int = 12, horizon: int = 12,
                   mask_fraction: float = 0.5
                   ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Test model's ability to fill in missing glucose values.

    Masks a fraction of glucose values (sets to 0), keeps all other
    channels intact, and asks the model to reconstruct. Compares
    predicted glucose at masked positions vs ground truth.

    Returns (actual_glucose, predicted_glucose, mask_bool) all full-window length.
    """
    start = center_idx - history
    end = center_idx + horizon
    total_len = history + horizon

    actual_glucose = features[start:end, IDX_GLUCOSE].copy() * SCALE['glucose']

    # Create mask: randomly select positions to zero out
    rng = np.random.RandomState(center_idx)  # reproducible per window
    n_mask = max(1, int(total_len * mask_fraction))
    mask_positions = rng.choice(total_len, size=n_mask, replace=False)
    mask_bool = np.zeros(total_len, dtype=bool)
    mask_bool[mask_positions] = True

    # Zero out masked glucose positions
    window = features[start:end].copy()
    window[mask_bool, IDX_GLUCOSE] = 0.0

    x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        output = model(x)
    predicted = output[0].numpy()[:, IDX_GLUCOSE] * SCALE['glucose']

    return actual_glucose, predicted, mask_bool


def run_similarity(model: torch.nn.Module, features: np.ndarray,
                   df: pd.DataFrame, center_idx: int,
                   history: int = 12, horizon: int = 12,
                   top_n: int = 5, stride: int = 6
                   ) -> List[Dict]:
    """Find windows most similar to reference in model representation space.

    Uses reconstruction residual L2 distance: windows where the model makes
    similar errors share similar metabolic dynamics the model hasn't fully
    captured. Also includes raw feature L2 for comparison.
    """
    total_len = history + horizon
    start = center_idx - history
    end = center_idx + horizon

    ref_window = features[start:end]
    x_ref = torch.tensor(ref_window, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        out_ref = model(x_ref)
    ref_residual = (x_ref[0] - out_ref[0]).numpy().flatten()
    ref_features = ref_window.flatten()

    results = []
    for s in range(0, len(features) - total_len, stride):
        if abs(s - start) < total_len:
            continue

        w_glucose = df['glucose'].values[s:s + total_len]
        if np.any(np.isnan(w_glucose)):
            continue

        x = torch.tensor(features[s:s + total_len], dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            out = model(x)
        residual = (x[0] - out[0]).numpy().flatten()
        w_features = features[s:s + total_len].flatten()

        # L2 distance in residual space (model-aware similarity)
        resid_dist = float(np.linalg.norm(ref_residual - residual))
        # L2 distance in raw feature space (model-agnostic similarity)
        raw_dist = float(np.linalg.norm(ref_features - w_features))

        c_idx = s + history
        results.append({
            'center_idx': c_idx,
            'time': str(df.index[c_idx]),
            'resid_distance': resid_dist,
            'raw_distance': raw_dist,
            'bg_mean': float(np.mean(w_glucose)),
            'bg_range': float(np.max(w_glucose) - np.min(w_glucose)),
            'bg_at_center': float(w_glucose[history]) if history < len(w_glucose) else np.nan,
            'iob_at_center': float(df['iob'].values[c_idx]),
        })

    results.sort(key=lambda r: r['resid_distance'])
    return results[:top_n]


def format_glucose(val: float) -> str:
    """Format glucose value, handling NaN."""
    if np.isnan(val):
        return '  N/A'
    return f'{val:5.0f}'


def sparkline(values: List[float], width: int = 20) -> str:
    """ASCII sparkline for glucose trend."""
    blocks = ' ▁▂▃▄▅▆▇█'
    valid = [v for v in values if not np.isnan(v)]
    if not valid:
        return ' ' * width

    lo, hi = min(valid), max(valid)
    rng = hi - lo if hi > lo else 1.0

    result = []
    for v in values:
        if np.isnan(v):
            result.append(' ')
        else:
            idx = int((v - lo) / rng * (len(blocks) - 1))
            result.append(blocks[idx])

    # Truncate or pad to width
    line = ''.join(result)
    if len(line) > width:
        line = line[:width]
    return line


def display_hindcast(df: pd.DataFrame, features: np.ndarray,
                      center_idx: int, history: int, horizon: int,
                      model_pred: np.ndarray,
                      model_name: str, checkpoint_name: str,
                      mode: str = 'forecast',
                      recon_history: Optional[np.ndarray] = None,
                      loop_pred: Optional[Dict] = None,
                      model2_pred: Optional[np.ndarray] = None,
                      model2_name: Optional[str] = None,
                      recon2_history: Optional[np.ndarray] = None):
    """Display hindcast comparison as ASCII table."""
    start = center_idx - history
    end = center_idx + horizon
    timestamps = df.index[start:end]
    actual_glucose = df['glucose'].values[start:end]
    actual_iob = df['iob'].values[start:end]

    center_time = df.index[center_idx]

    # Header
    print(f'\n{"═" * 72}')
    print(f'  cgmencode Hindcast')
    print(f'{"═" * 72}')
    print(f'  Prediction time: {center_time.strftime("%Y-%m-%d %H:%M UTC")}')
    print(f'  Model:           {model_name} ({checkpoint_name})')
    print(f'  Mode:            {mode}')
    print(f'  History:         {history} steps ({history * 5} min)')
    print(f'  Horizon:         {horizon} steps ({horizon * 5} min)')

    # Context: what's happening at this time
    bg_at_t = actual_glucose[history - 1]
    iob_at_t = actual_iob[history - 1]
    recent_carbs = df['carbs'].values[start:center_idx].sum()
    recent_bolus = df['bolus'].values[start:center_idx].sum()
    print(f'  BG at T:         {bg_at_t:.0f} mg/dL')
    print(f'  IOB at T:        {iob_at_t:.2f} U')
    if recent_carbs > 0:
        print(f'  Recent carbs:    {recent_carbs:.0f}g (in history window)')
    if recent_bolus > 0:
        print(f'  Recent bolus:    {recent_bolus:.2f}U (in history window)')

    # Align Loop predictions to our grid if available
    loop_glucose = None
    if loop_pred:
        lp_start = loop_pred['start']
        if lp_start.tz is None:
            lp_start = lp_start.tz_localize('UTC')
        loop_vals = loop_pred['values']

        loop_glucose = np.full(horizon, np.nan)
        for h in range(horizon):
            target_time = timestamps[history + h]
            # Loop predictions are at 5-min intervals from start
            minutes_from_start = (target_time - lp_start).total_seconds() / 60
            loop_idx = int(round(minutes_from_start / 5))
            if 0 <= loop_idx < len(loop_vals):
                loop_glucose[h] = loop_vals[loop_idx]

        print(f'  Loop prediction: found ({loop_pred["delta_seconds"]:.0f}s offset)')
    else:
        print(f'  Loop prediction: not found near this time')

    # History section
    print(f'\n{"─" * 72}')
    print(f'  History ({timestamps[0].strftime("%H:%M")}–{timestamps[history-1].strftime("%H:%M")})')
    print(f'{"─" * 72}')

    hist_glucose = actual_glucose[:history]
    print(f'  BG trend: {sparkline(hist_glucose.tolist(), width=history)}')
    print(f'  Range:    {np.nanmin(hist_glucose):.0f}–{np.nanmax(hist_glucose):.0f} mg/dL')

    # Show reconstruction quality for history portion
    if recon_history is not None:
        recon_errors = []
        for i in range(history):
            if not np.isnan(hist_glucose[i]):
                recon_errors.append(abs(recon_history[i] - hist_glucose[i]))
        if recon_errors:
            r_mae = np.mean(recon_errors)
            print(f'  Recon MAE:{r_mae:5.1f} mg/dL (how well model represents history)')

            # Warn if model outputs look like residuals (near-zero)
            pred_range = np.max(model_pred) - np.min(model_pred)
            pred_mean = np.mean(np.abs(model_pred))
            glucose_mean = np.nanmean(actual_glucose)
            if pred_mean < 50 and glucose_mean > 80:
                print(f'  ⚠ WARNING: Model output range ({pred_mean:.0f} avg) << actual glucose '
                      f'({glucose_mean:.0f} avg)')
                print(f'             This checkpoint may be a residual model (trained on '
                      f'physics-corrected data)')
                print(f'             Try: --mode reconstruct, or use a non-residual checkpoint')

    # Prediction table
    print(f'\n{"─" * 72}')
    has_loop = loop_glucose is not None
    has_model2 = model2_pred is not None

    # Build header
    hdr = f'  {"Time":<8s} {"Actual":>7s} {"Model":>7s}'
    sep = f'  {"────────"} {"───────"} {"───────"}'
    if has_model2:
        hdr += f' {model2_name[:7]:>7s}'
        sep += f' {"───────"}'
    if has_loop:
        hdr += f' {"Loop":>7s}'
        sep += f' {"───────"}'
    hdr += f' {"ML Err":>7s}'
    sep += f' {"───────"}'
    if has_loop:
        hdr += f' {"LP Err":>7s}'
        sep += f' {"───────"}'

    print(f'  Predictions ({timestamps[history].strftime("%H:%M")}–{timestamps[-1].strftime("%H:%M")})')
    print(f'{"─" * 72}')
    print(hdr)
    print(sep)

    model_errors = []
    loop_errors = []
    model2_errors = []
    persist_errors = []
    persist_val = actual_glucose[history - 1]

    for h in range(horizon):
        idx = history + h
        ts_str = timestamps[idx].strftime('%H:%M')
        actual = actual_glucose[idx]
        pred = model_pred[h]
        ml_err = pred - actual if not np.isnan(actual) else np.nan

        row = f'  {ts_str:<8s} {format_glucose(actual)} {format_glucose(pred)}'

        if has_model2:
            p2 = model2_pred[h]
            row += f' {format_glucose(p2)}'
            if not np.isnan(actual):
                model2_errors.append(abs(p2 - actual))

        if has_loop:
            lp = loop_glucose[h]
            row += f' {format_glucose(lp)}'
            if not np.isnan(actual) and not np.isnan(lp):
                lp_err = lp - actual
                loop_errors.append(abs(lp_err))
                row += f' {ml_err:+6.0f} {lp_err:+6.0f}'
            else:
                row += f' {ml_err:+6.0f}     N/A'
        else:
            row += f' {ml_err:+6.0f}'

        if not np.isnan(actual):
            model_errors.append(abs(ml_err))
            persist_errors.append(abs(persist_val - actual))

        print(row)

    # Metrics summary
    print(f'\n{"─" * 72}')
    print(f'  Metrics (horizon = {horizon * 5} min)')
    print(f'{"─" * 72}')

    if model_errors:
        ml_mae = np.mean(model_errors)
        ml_rmse = np.sqrt(np.mean(np.array(model_errors) ** 2))
        print(f'  {model_name:<12s}  MAE={ml_mae:5.1f} mg/dL   RMSE={ml_rmse:5.1f} mg/dL')

    if model2_errors:
        m2_mae = np.mean(model2_errors)
        m2_rmse = np.sqrt(np.mean(np.array(model2_errors) ** 2))
        print(f'  {model2_name:<12s}  MAE={m2_mae:5.1f} mg/dL   RMSE={m2_rmse:5.1f} mg/dL')

    if loop_errors:
        lp_mae = np.mean(loop_errors)
        lp_rmse = np.sqrt(np.mean(np.array(loop_errors) ** 2))
        print(f'  {"Loop":<12s}  MAE={lp_mae:5.1f} mg/dL   RMSE={lp_rmse:5.1f} mg/dL')

    if persist_errors:
        p_mae = np.mean(persist_errors)
        p_rmse = np.sqrt(np.mean(np.array(persist_errors) ** 2))
        print(f'  {"Persistence":<12s}  MAE={p_mae:5.1f} mg/dL   RMSE={p_rmse:5.1f} mg/dL')

    print(f'{"═" * 72}')

    return {
        'time': str(center_time),
        'bg_at_t': float(bg_at_t) if not np.isnan(bg_at_t) else None,
        'model_mae': float(np.mean(model_errors)) if model_errors else None,
        'loop_mae': float(np.mean(loop_errors)) if loop_errors else None,
        'persist_mae': float(np.mean(persist_errors)) if persist_errors else None,
    }


def display_anomaly_scan(results: List[Dict], model_name: str, checkpoint_name: str):
    """Display top anomalous windows ranked by reconstruction error."""
    print(f'\n{"═" * 72}')
    print(f'  cgmencode Anomaly Scan')
    print(f'{"═" * 72}')
    print(f'  Model: {model_name} ({checkpoint_name})')
    print(f'  Frame: Reconstruction error as anomaly score')
    print(f'         High error = unusual pattern the model can\'t represent')
    print(f'\n  {"Rank":<5s} {"Time":<22s} {"Anom Score":>10s} {"BG Mean":>8s} '
          f'{"BG Range":>9s} {"IOB MAE":>8s}')
    print(f'  {"─" * 5} {"─" * 22} {"─" * 10} {"─" * 8} {"─" * 9} {"─" * 8}')

    for i, r in enumerate(results):
        ts = pd.Timestamp(r['time']).strftime('%Y-%m-%d %H:%M')
        print(f'  {i+1:<5d} {ts:<22s} {r["glucose_mae"]:>9.1f}  '
              f'{r["bg_mean"]:>7.0f}  {r["bg_range"]:>8.0f}  '
              f'{r["iob_mae"]:>7.2f}')

    if results:
        scores = [r['glucose_mae'] for r in results]
        print(f'\n  Score range: {min(scores):.1f} – {max(scores):.1f} mg/dL recon MAE')
        print(f'  Interpretation:')
        print(f'    Normal windows ≈ low score (model represents them well)')
        print(f'    Anomalous windows ≈ high score (exercise? sensor issue? unusual meal?)')
    print(f'{"═" * 72}')


def display_counterfactual(df: pd.DataFrame, center_idx: int,
                            history: int, horizon: int,
                            recon_real: np.ndarray, recon_cf: np.ndarray,
                            model_name: str, checkpoint_name: str):
    """Display counterfactual: with treatment vs without."""
    start = center_idx - history
    end = center_idx + horizon
    total_len = history + horizon
    timestamps = df.index[start:end]
    actual_glucose = df['glucose'].values[start:end]
    actual_bolus = df['bolus'].values[start:end]
    actual_carbs = df['carbs'].values[start:end]

    center_time = df.index[center_idx]

    print(f'\n{"═" * 72}')
    print(f'  cgmencode Counterfactual Analysis')
    print(f'{"═" * 72}')
    print(f'  Window:  {timestamps[0].strftime("%Y-%m-%d %H:%M")} – '
          f'{timestamps[-1].strftime("%H:%M")} UTC')
    print(f'  Model:   {model_name} ({checkpoint_name})')
    print(f'  Frame:   "What if no bolus/basal/carbs had been given?"')
    print(f'           Action channels zeroed → model predicts untreated trajectory')

    # Summarize actions in window
    total_bolus = np.sum(actual_bolus)
    total_carbs = np.sum(actual_carbs)
    print(f'\n  Actions in window:')
    print(f'    Total bolus: {total_bolus:.2f} U')
    print(f'    Total carbs: {total_carbs:.0f} g')

    print(f'\n  {"Time":<8s} {"Actual":>7s} {"w/Treat":>8s} {"No Treat":>9s} '
          f'{"Δ Effect":>9s} {"Bolus":>6s} {"Carbs":>6s}')
    print(f'  {"────────"} {"───────"} {"────────"} {"─────────"} '
          f'{"─────────"} {"──────"} {"──────"}')

    for i in range(total_len):
        ts_str = timestamps[i].strftime('%H:%M')
        actual = actual_glucose[i]
        real = recon_real[i]
        cf = recon_cf[i]
        effect = real - cf  # positive = treatment raised BG (carbs), negative = lowered (insulin)
        bolus = actual_bolus[i]
        carbs = actual_carbs[i]

        marker = ' '
        if i == history:
            marker = '►'

        bolus_str = f'{bolus:.1f}' if bolus > 0 else '  ·'
        carbs_str = f'{carbs:.0f}' if carbs > 0 else '  ·'

        print(f'{marker} {ts_str:<8s} {format_glucose(actual)} {format_glucose(real)} '
              f'{format_glucose(cf)}  {effect:+8.1f} {bolus_str:>6s} {carbs_str:>6s}')

    # Summary
    effect = recon_real - recon_cf
    print(f'\n  Treatment effect (model\'s view):')
    print(f'    Mean Δ:  {np.mean(effect):+.1f} mg/dL (positive = raised BG)')
    print(f'    Max Δ:   {np.max(effect):+.1f} mg/dL')
    print(f'    Min Δ:   {np.min(effect):+.1f} mg/dL')

    if total_bolus > 0.1 and np.mean(effect) > 5:
        print(f'  ⚠ Unexpected: treatment appears to RAISE BG — model may not have')
        print(f'    learned action→state causality (common with single-patient data)')
    print(f'{"═" * 72}')


def display_imputation(df: pd.DataFrame, center_idx: int,
                        history: int, horizon: int,
                        actual_glucose: np.ndarray,
                        predicted_glucose: np.ndarray,
                        mask_bool: np.ndarray,
                        model_name: str, checkpoint_name: str,
                        mask_fraction: float):
    """Display imputation results: model fills in missing glucose."""
    start = center_idx - history
    end = center_idx + horizon
    timestamps = df.index[start:end]

    print(f'\n{"═" * 72}')
    print(f'  cgmencode Imputation Test')
    print(f'{"═" * 72}')
    print(f'  Window:  {timestamps[0].strftime("%Y-%m-%d %H:%M")} – '
          f'{timestamps[-1].strftime("%H:%M")} UTC')
    print(f'  Model:   {model_name} ({checkpoint_name})')
    print(f'  Frame:   "Can the model infer glucose from IOB/COB/actions alone?"')
    print(f'           {mask_fraction:.0%} of glucose values masked (set to 0)')
    print(f'           Model sees: IOB, COB, basal, bolus, carbs, time')

    print(f'\n  {"Time":<8s} {"Actual":>7s} {"Pred":>7s} {"Err":>7s} {"Status":>8s}')
    print(f'  {"────────"} {"───────"} {"───────"} {"───────"} {"────────"}')

    masked_errors = []
    visible_errors = []

    for i in range(len(actual_glucose)):
        ts_str = timestamps[i].strftime('%H:%M')
        actual = actual_glucose[i]
        pred = predicted_glucose[i]
        err = pred - actual
        status = 'MASKED' if mask_bool[i] else 'visible'

        if mask_bool[i]:
            masked_errors.append(abs(err))
            print(f'  {ts_str:<8s} {format_glucose(actual)} {format_glucose(pred)} '
                  f'{err:+6.0f}  {"██ MASKED"}')
        else:
            visible_errors.append(abs(err))
            print(f'  {ts_str:<8s} {format_glucose(actual)} {format_glucose(pred)} '
                  f'{err:+6.0f}  {"·  visible"}')

    print(f'\n  Imputation accuracy:')
    if masked_errors:
        m_mae = np.mean(masked_errors)
        m_rmse = np.sqrt(np.mean(np.array(masked_errors) ** 2))
        print(f'    Masked positions:  MAE={m_mae:5.1f}  RMSE={m_rmse:5.1f} mg/dL '
              f'({len(masked_errors)} points)')
    if visible_errors:
        v_mae = np.mean(visible_errors)
        print(f'    Visible positions: MAE={v_mae:5.1f} mg/dL ({len(visible_errors)} points)')
    if masked_errors and visible_errors:
        ratio = np.mean(masked_errors) / max(np.mean(visible_errors), 0.01)
        print(f'    Masked/Visible ratio: {ratio:.2f}x  '
              f'(1.0 = model ignores glucose input; >2.0 = relies heavily on it)')
    print(f'{"═" * 72}')


def display_similarity(df: pd.DataFrame, features: np.ndarray,
                        center_idx: int, history: int, horizon: int,
                        similar_windows: List[Dict],
                        model_name: str, checkpoint_name: str):
    """Display windows most similar to reference in embedding space."""
    start = center_idx - history
    end = center_idx + horizon
    timestamps = df.index[start:end]
    ref_glucose = df['glucose'].values[start:end]

    print(f'\n{"═" * 72}')
    print(f'  cgmencode Similarity Search')
    print(f'{"═" * 72}')
    print(f'  Model:     {model_name} ({checkpoint_name})')
    print(f'  Frame:     "Find metabolically similar past events"')
    print(f'             Reconstruction residual L2 distance (lower = more similar)')

    print(f'\n  Reference window:')
    print(f'    Time:  {timestamps[0].strftime("%Y-%m-%d %H:%M")} – '
          f'{timestamps[-1].strftime("%H:%M")}')
    print(f'    BG:    {sparkline(ref_glucose.tolist(), width=history + horizon)}'
          f'  {np.nanmin(ref_glucose):.0f}–{np.nanmax(ref_glucose):.0f} mg/dL')
    print(f'    IOB:   {df["iob"].values[center_idx]:.2f} U')

    if not similar_windows:
        print(f'\n  No similar windows found')
        print(f'{"═" * 72}')
        return

    print(f'\n  {"Rank":<5s} {"Dist":>6s} {"Raw":>6s} {"Time":<22s} '
          f'{"BG":>4s} {"IOB":>5s} {"BG Trend"}')
    print(f'  {"─" * 5} {"─" * 6} {"─" * 6} {"─" * 22} '
          f'{"─" * 4} {"─" * 5} {"─" * 24}')

    for i, w in enumerate(similar_windows):
        ts = pd.Timestamp(w['time']).strftime('%Y-%m-%d %H:%M')
        w_start = w['center_idx'] - history
        w_end = w['center_idx'] + horizon
        w_glucose = df['glucose'].values[w_start:w_end]
        trend = sparkline(w_glucose.tolist(), width=history + horizon)

        print(f'  {i+1:<5d} {w["resid_distance"]:>5.3f} {w["raw_distance"]:>5.2f} '
              f'{ts:<22s} {w["bg_mean"]:>3.0f}  {w["iob_at_center"]:>4.1f} {trend}')

    dists = [w['resid_distance'] for w in similar_windows]
    print(f'\n  Distance range: {min(dists):.4f} – {max(dists):.4f}')
    print(f'  Columns: Dist = model residual L2, Raw = feature L2 (model-agnostic)')
    print(f'  Similar residual patterns → model "sees" these windows the same way')
    print(f'{"═" * 72}')


def main():
    parser = argparse.ArgumentParser(
        description='Retrospective model inference — compare predictions vs Nightscout actuals',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Forecast: predict future from history
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --at "2026-02-08T14:00:00Z"

  # Anomaly detection: find unusual metabolic patterns
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --mode anomaly --top 10

  # Counterfactual: "what if no treatment?"
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --mode counterfactual --pick interesting

  # Imputation: can model infer glucose from IOB/actions alone?
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --mode impute --mask-fraction 0.5

  # Similarity: find metabolically similar past events
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --mode similarity --at "2026-01-15T12:00:00Z"

  # Scan interesting windows (forecast/reconstruct modes)
  %(prog)s --data path/to/ns-data --checkpoint ae_best.pth --scan 10

Inference Frames:
  forecast       Predict future glucose from history context (tests extrapolation)
  reconstruct    Full window reconstruction (tests representation quality)
  anomaly        Rank all windows by reconstruction error (unusual = high error)
  counterfactual Zero out treatment actions, compare with/without (needs GroupedEncoder)
  impute         Mask glucose values, predict from IOB/actions alone (tests understanding)
  similarity     Find past windows with similar metabolic embeddings
        ''')

    parser.add_argument('--data', required=True,
                        help='Path to Nightscout fixture directory (with entries.json, etc.)')
    parser.add_argument('--checkpoint', required=True,
                        help='Path to trained model checkpoint (.pth)')
    parser.add_argument('--model', default='ae', choices=list(HINDCAST_MODELS.keys()),
                        help='Model architecture (default: ae)')
    parser.add_argument('--at', dest='at_time',
                        help='Time to hindcast at (ISO-8601, "8 hours ago", "yesterday 14:00")')
    parser.add_argument('--pick', choices=['interesting', 'random'],
                        help='Auto-pick a window: "interesting" (meals/swings) or "random"')
    parser.add_argument('--scan', type=int, metavar='N',
                        help='Scan N interesting windows and summarize')
    parser.add_argument('--history', type=int, default=12,
                        help='History window in 5-min steps (default: 12 = 60 min)')
    parser.add_argument('--horizon', type=int, default=12,
                        help='Prediction horizon in 5-min steps (default: 12 = 60 min)')
    parser.add_argument('--mode', default='forecast',
                        choices=['forecast', 'reconstruct', 'anomaly',
                                 'counterfactual', 'impute', 'similarity'],
                        help='Inference frame (default: forecast). See help for descriptions.')

    # Mode-specific options
    parser.add_argument('--top', type=int, default=10,
                        help='Number of results for anomaly/similarity modes (default: 10)')
    parser.add_argument('--mask-fraction', type=float, default=0.5,
                        help='Fraction of glucose to mask in impute mode (default: 0.5)')
    parser.add_argument('--stride', type=int, default=6,
                        help='Step stride for scanning modes (default: 6 = 30 min)')

    # Second model for comparison
    parser.add_argument('--checkpoint2', help='Second model checkpoint for side-by-side comparison')
    parser.add_argument('--model2', default='grouped', choices=list(HINDCAST_MODELS.keys()),
                        help='Second model architecture (default: grouped)')

    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--quiet', action='store_true', help='Suppress data loading output')

    args = parser.parse_args()

    # --- Load data ---
    df, features = build_nightscout_grid(args.data, verbose=not args.quiet)
    if df is None:
        print('ERROR: Failed to load Nightscout data')
        sys.exit(1)

    data_start = df.index[0]
    data_end = df.index[-1]
    if not args.quiet:
        print(f'  Data range: {data_start.strftime("%Y-%m-%d")} to {data_end.strftime("%Y-%m-%d")} '
              f'({len(df)} steps, {len(df) * 5 / 60 / 24:.0f} days)')

    # --- Load model ---
    model, param_count, ckpt_meta = load_model(args.checkpoint, args.model)
    ckpt_name = Path(args.checkpoint).name
    if not args.quiet:
        epoch = ckpt_meta.get('epoch', '?')
        val_loss = ckpt_meta.get('val_loss', '?')
        print(f'\n  Model: {args.model} ({param_count:,} params, epoch={epoch}, val_loss={val_loss})')

    # Optional second model
    model2 = None
    if args.checkpoint2:
        model2, p2_count, _ = load_model(args.checkpoint2, args.model2)
        if not args.quiet:
            print(f'  Model2: {args.model2} ({p2_count:,} params)')

    # --- Determine time point(s) ---
    total_needed = args.history + args.horizon

    # === ANOMALY MODE: scan all windows, rank by reconstruction error ===
    if args.mode == 'anomaly':
        results = run_anomaly_scan(model, features, df,
                                   history=args.history, horizon=args.horizon,
                                   top_n=args.top, stride=args.stride)
        display_anomaly_scan(results, args.model, ckpt_name)
        if args.json:
            json.dump(results, sys.stdout, indent=2, default=str)
        return

    # === Modes that need a center_idx: resolve time target ===
    center_idx = _resolve_center_idx(args, df, features)

    # === COUNTERFACTUAL MODE ===
    if args.mode == 'counterfactual':
        recon_real, recon_cf = run_counterfactual(
            model, features, center_idx, args.history, args.horizon)
        display_counterfactual(df, center_idx, args.history, args.horizon,
                               recon_real, recon_cf, args.model, ckpt_name)
        return

    # === IMPUTATION MODE ===
    if args.mode == 'impute':
        actual_g, pred_g, mask = run_imputation(
            model, features, center_idx, args.history, args.horizon,
            mask_fraction=args.mask_fraction)
        display_imputation(df, center_idx, args.history, args.horizon,
                            actual_g, pred_g, mask,
                            args.model, ckpt_name, args.mask_fraction)
        return

    # === SIMILARITY MODE ===
    if args.mode == 'similarity':
        similar = run_similarity(model, features, df, center_idx,
                                  args.history, args.horizon,
                                  top_n=args.top, stride=args.stride)
        display_similarity(df, features, center_idx, args.history, args.horizon,
                            similar, args.model, ckpt_name)
        return

    # === FORECAST / RECONSTRUCT MODES (original behavior) ===
    if args.scan:
        indices = find_interesting_windows(df, features, n=args.scan,
                                           history=args.history, horizon=args.horizon)
        if not indices:
            print('ERROR: No valid windows found in data')
            sys.exit(1)

        all_results = []
        for idx in indices:
            pred, recon = run_hindcast(model, features, idx, args.history, args.horizon, args.mode)
            loop = find_loop_prediction(args.data, df.index[idx])

            pred2, recon2 = None, None
            if model2:
                pred2, recon2 = run_hindcast(model2, features, idx, args.history, args.horizon, args.mode)

            result = display_hindcast(
                df, features, idx, args.history, args.horizon,
                pred, args.model, ckpt_name, mode=args.mode,
                recon_history=recon, loop_pred=loop,
                model2_pred=pred2, model2_name=args.model2 if model2 else None,
                recon2_history=recon2)
            all_results.append(result)

        # Summary across all scanned windows
        print(f'\n{"═" * 72}')
        print(f'  SCAN SUMMARY ({len(all_results)} windows)')
        print(f'{"═" * 72}')
        ml_maes = [r['model_mae'] for r in all_results if r['model_mae'] is not None]
        lp_maes = [r['loop_mae'] for r in all_results if r['loop_mae'] is not None]
        p_maes = [r['persist_mae'] for r in all_results if r['persist_mae'] is not None]
        if ml_maes:
            print(f'  Model avg MAE:       {np.mean(ml_maes):5.1f} mg/dL  (across {len(ml_maes)} windows)')
        if lp_maes:
            print(f'  Loop avg MAE:        {np.mean(lp_maes):5.1f} mg/dL  (across {len(lp_maes)} windows)')
        if p_maes:
            print(f'  Persistence avg MAE: {np.mean(p_maes):5.1f} mg/dL  (across {len(p_maes)} windows)')
        print(f'{"═" * 72}')

        if args.json:
            json.dump(all_results, sys.stdout, indent=2, default=str)

    else:
        # Single window forecast/reconstruct
        pred, recon = run_hindcast(model, features, center_idx, args.history, args.horizon, args.mode)
        loop = find_loop_prediction(args.data, df.index[center_idx])

        pred2, recon2 = None, None
        if model2:
            pred2, recon2 = run_hindcast(model2, features, center_idx, args.history, args.horizon, args.mode)

        result = display_hindcast(
            df, features, center_idx, args.history, args.horizon,
            pred, args.model, ckpt_name, mode=args.mode,
            recon_history=recon, loop_pred=loop,
            model2_pred=pred2, model2_name=args.model2 if model2 else None,
            recon2_history=recon2)

        if args.json:
            json.dump(result, sys.stdout, indent=2, default=str)


def _resolve_center_idx(args, df, features) -> int:
    """Resolve the center index from --at, --pick, or default."""
    data_end = df.index[-1]

    if args.at_time:
        target = parse_time(args.at_time, reference_time=data_end)
    elif args.pick == 'random':
        valid_range = range(args.history, len(df) - args.horizon)
        target_idx = np.random.choice(list(valid_range))
        target = df.index[target_idx]
    elif args.pick == 'interesting':
        indices = find_interesting_windows(df, features, n=1,
                                           history=args.history, horizon=args.horizon)
        if not indices:
            print('ERROR: No interesting windows found')
            sys.exit(1)
        target = df.index[indices[0]]
    else:
        # Default: pick the most interesting window
        indices = find_interesting_windows(df, features, n=1,
                                           history=args.history, horizon=args.horizon)
        if indices:
            target = df.index[indices[0]]
        else:
            target = data_end - pd.Timedelta(hours=2)

    if target.tz is None:
        target = target.tz_localize('UTC')

    # Find nearest grid index
    target_round = target.round('5min')
    if target_round in df.index:
        center_idx = df.index.get_loc(target_round)
    else:
        diffs = abs(df.index - target)
        center_idx = diffs.argmin()

    # Bounds check
    if center_idx < args.history:
        print(f'WARNING: Requested time too early, shifting forward')
        center_idx = args.history
    if center_idx + args.horizon > len(df):
        print(f'WARNING: Requested time too late, shifting backward')
        center_idx = len(df) - args.horizon

    # Check for NaN glucose in window
    total_needed = args.history + args.horizon
    window_glucose = df['glucose'].values[center_idx - args.history:center_idx + args.horizon]
    nan_count = np.sum(np.isnan(window_glucose))
    if nan_count > total_needed * 0.3:
        print(f'WARNING: {nan_count}/{total_needed} NaN glucose values in window')

    return center_idx


if __name__ == '__main__':
    main()
