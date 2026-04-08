"""
glucose_forecast.py — PKGroupedEncoder ensemble inference for production.

Loads trained transformer models from EXP-619 and produces 4-hour glucose
forecasts with 5-seed ensemble averaging and per-horizon confidence.

Research basis:
  EXP-619: Full-scale validation (11 patients, 5 seeds, 4 windows)
  Champion: PKGroupedEncoder (134K params), 8ch PK features
  Routed MAE: h30=11.1, h90=16.1, h180=18.5, h360=21.9 mg/dL

Architecture:
  PKGroupedEncoder: 3-group projection (state/action/extra) → transformer
  8 channels: glucose, IOB, COB, net_basal, insulin_net, carb_rate, sin_time, net_balance
  PK mode: future glucose masked, PK channels kept (deterministic from past)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .types import ForecastResult, MetabolicState, PatientData, PatientProfile

# ── Constants (from exp_pk_forecast_v14.py) ───────────────────────────

GLUCOSE_SCALE = 400.0
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
PRODUCTION_SEEDS = [42, 123, 456, 789, 1024]

# Horizon routing: best window per horizon (from EXP-619)
HORIZON_ROUTING = {
    'h30': 'w48', 'h60': 'w48', 'h90': 'w48', 'h120': 'w48',
    'h150': 'w96', 'h180': 'w96', 'h240': 'w96',
    'h300': 'w144', 'h360': 'w144',
}

# Window config: total steps (history + future)
WINDOW_CONFIG = {
    'w48': {'total': 48, 'history': 24, 'future': 24},
    'w72': {'total': 72, 'history': 36, 'future': 36},
    'w96': {'total': 96, 'history': 48, 'future': 48},
    'w144': {'total': 144, 'history': 72, 'future': 72},
}

# Validated MAE per horizon (EXP-619, routed)
ROUTED_MAE = {
    'h30': 11.13, 'h60': 14.21, 'h90': 16.06, 'h120': 17.37,
    'h150': 17.95, 'h180': 18.51, 'h240': 20.00,
    'h300': 20.18, 'h360': 21.92,
}


# ── Model Architecture (mirrored from exp_pk_forecast_v14.py) ─────────

_torch_available = False
try:
    import torch
    import torch.nn as nn
    _torch_available = True
except ImportError:
    pass


def _build_model(input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 4, dim_feedforward: int = 128,
                 dropout: float = 0.1):
    """Construct PKGroupedEncoder model.

    Mirrors the architecture in exp_pk_forecast_v14.py:275-336
    to avoid importing the 18K-line experiment script.
    """
    if not _torch_available:
        raise ImportError("PyTorch required for glucose forecasting")

    class PositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int = 5000):
            super().__init__()
            pe = torch.zeros(max_len, d_model)
            position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div_term = torch.exp(
                torch.arange(0, d_model, 2).float()
                * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(position * div_term)
            pe[:, 1::2] = torch.cos(position * div_term)
            pe = pe.unsqueeze(0)
            self.register_buffer('pe', pe)

        def forward(self, x):
            return x + self.pe[:, :x.size(1)]

    class PKGroupedEncoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.input_dim = input_dim
            self.d_model = d_model
            d_state = d_model // 2
            d_action = d_model // 4
            self.state_proj = nn.Linear(3, d_state)
            self.action_proj = nn.Linear(3, d_action)
            if input_dim >= 7:
                d_extra = d_model - d_state - d_action
                n_extra = input_dim - 6
                self.extra_proj = nn.Linear(n_extra, d_extra)
            else:
                self.extra_proj = None
                self.action_proj = nn.Linear(3, d_model - d_state)
            self.pos_encoder = PositionalEncoding(d_model)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout, batch_first=True, norm_first=True)
            self.transformer_encoder = nn.TransformerEncoder(
                encoder_layer, num_layers=num_layers)
            self.output_projection = nn.Linear(d_model, input_dim)

        def _causal_mask(self, sz, device):
            return torch.triu(
                torch.ones(sz, sz, device=device) * float('-inf'),
                diagonal=1)

        def encode(self, x, causal=False):
            state = self.state_proj(x[..., :3])
            action = self.action_proj(x[..., 3:6])
            if self.extra_proj is not None and x.size(-1) > 6:
                extra = self.extra_proj(x[..., 6:])
                z = torch.cat([state, action, extra], dim=-1)
            else:
                z = torch.cat([state, action], dim=-1)
            z = self.pos_encoder(z)
            mask = (self._causal_mask(x.size(1), x.device)
                    if causal else None)
            return self.transformer_encoder(z, mask=mask)

        def forward(self, x, causal=False):
            return self.output_projection(self.encode(x, causal=causal))

    return PKGroupedEncoder()


# ── Model Loading ─────────────────────────────────────────────────────

_model_cache: Dict[str, list] = {}


def load_ensemble(patient_id: str, window: str = 'w48',
                  models_dir: Optional[str] = None,
                  device: str = 'cpu',
                  input_dim: int = 8) -> list:
    """Load 5-seed ensemble for a patient from EXP-619 checkpoints.

    Args:
        patient_id: patient letter (a-k).
        window: window size label (w48, w72, w96, w144).
        models_dir: directory containing .pth files.
        device: torch device string.
        input_dim: model input channels (8 for champion).

    Returns:
        List of (model, seed) tuples, all in eval mode.
    """
    if not _torch_available:
        raise ImportError("PyTorch required for glucose forecasting")

    cache_key = f"{patient_id}_{window}_{device}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    if models_dir is None:
        models_dir = str(
            Path(__file__).resolve().parent.parent.parent.parent
            / 'externals' / 'experiments')

    dev = torch.device(device)
    models = []

    for seed in PRODUCTION_SEEDS:
        path = Path(models_dir) / f"exp619_{window}_ft_{patient_id}_s{seed}.pth"
        if not path.exists():
            continue
        ckpt = torch.load(str(path), map_location=dev, weights_only=False)
        model = _build_model(input_dim=input_dim)
        model.load_state_dict(ckpt['model_state'])
        model = model.to(dev).eval()
        models.append((model, seed))

    if models:
        _model_cache[cache_key] = models
    return models


def clear_model_cache():
    """Free cached models from memory."""
    _model_cache.clear()


# ── Input Preparation ─────────────────────────────────────────────────

def prepare_input_window(
    glucose: np.ndarray,
    metabolic: MetabolicState,
    patient: PatientData,
    hours: np.ndarray,
    window: str = 'w48',
    isf: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """Build 8-channel input tensor from current patient state.

    Takes the last `history` timesteps and pads `future` steps with
    zeros (to be masked during inference).

    Channel layout:
      [0] glucose / GLUCOSE_SCALE (optionally ISF-normalized)
      [1] IOB / 20
      [2] COB / 100
      [3] net_basal / 5
      [4] insulin_net (PK) / PK_NORMS[1]=0.05
      [5] carb_rate (PK) / PK_NORMS[3]=0.5
      [6] sin(2π·hour/24)
      [7] net_balance (supply-demand) / PK_NORMS[6]=20

    Args:
        glucose: (N,) cleaned glucose array.
        metabolic: MetabolicState with supply, demand, net_flux.
        patient: PatientData for IOB, COB, basal_rate.
        hours: (N,) fractional hours of day.
        window: window size label.
        isf: patient ISF for normalization. None = skip ISF norm.

    Returns:
        (input_array, history_len): input shape (total_steps, 8),
        and the history/future split point.
    """
    cfg = WINDOW_CONFIG[window]
    hist_len = cfg['history']
    total = cfg['total']
    N = len(glucose)

    # Gather history window
    start = max(0, N - hist_len)
    end = N
    actual_hist = end - start

    # Build 8-channel history
    hist = np.zeros((hist_len, 8))
    offset = hist_len - actual_hist

    g = np.nan_to_num(glucose[start:end], nan=120.0)
    hist[offset:, 0] = g / GLUCOSE_SCALE

    if patient.iob is not None:
        iob = np.nan_to_num(patient.iob[start:end], nan=0.0)
        hist[offset:, 1] = iob / 20.0

    if patient.cob is not None:
        cob = np.nan_to_num(patient.cob[start:end], nan=0.0)
        hist[offset:, 2] = cob / 100.0
    elif metabolic is not None:
        hist[offset:, 2] = np.nan_to_num(
            metabolic.carb_supply[start:end], nan=0.0) / 100.0

    if patient.basal_rate is not None:
        basal = np.nan_to_num(patient.basal_rate[start:end], nan=0.8)
        # net_basal = basal - profile median
        med_basal = patient.profile.basal_schedule[0].get('value', 0.8)
        hist[offset:, 3] = (basal - med_basal) / 5.0

    # PK channels: approximate from metabolic state
    if metabolic is not None:
        # insulin_net ≈ demand signal (insulin action)
        hist[offset:, 4] = np.nan_to_num(
            metabolic.demand[start:end], nan=0.0) / PK_NORMS[1]
        # carb_rate ≈ carb_supply signal
        hist[offset:, 5] = np.nan_to_num(
            metabolic.carb_supply[start:end], nan=0.0) / PK_NORMS[3]

    # Time features
    h = hours[start:end]
    hist[offset:, 6] = np.sin(2 * np.pi * h / 24.0)

    # Net balance (supply - demand)
    if metabolic is not None:
        hist[offset:, 7] = np.nan_to_num(
            metabolic.net_flux[start:end], nan=0.0) / PK_NORMS[6]

    # ISF normalization
    if isf is not None and isf > 0:
        hist[:, 0] *= (GLUCOSE_SCALE / isf)
        hist[:, 0] = np.clip(hist[:, 0], 0.0, 10.0)

    # Build future (zeros — will be masked except PK channels)
    future_len = total - hist_len
    future = np.zeros((future_len, 8))

    # Extend deterministic PK channels into future (constant extrapolation)
    if hist_len > 0:
        for ch in [1, 2, 3, 4, 5, 6, 7]:
            future[:, ch] = hist[-1, ch]
        # Advance sin_time properly
        last_hour = float(hours[-1]) if len(hours) > 0 else 12.0
        future_hours = last_hour + np.arange(1, future_len + 1) * 5.0 / 60.0
        future[:, 6] = np.sin(2 * np.pi * future_hours / 24.0)

    input_arr = np.concatenate([hist, future], axis=0)  # (total, 8)
    return input_arr, hist_len


# ── Inference ─────────────────────────────────────────────────────────

def predict_trajectory(
    patient: PatientData,
    metabolic: MetabolicState,
    hours: np.ndarray,
    glucose: np.ndarray,
    patient_id: str,
    window: str = 'w48',
    models_dir: Optional[str] = None,
    device: str = 'cpu',
    isf: Optional[float] = None,
) -> Optional[ForecastResult]:
    """Run ensemble glucose forecast for a patient.

    Args:
        patient: PatientData with glucose, IOB, etc.
        metabolic: MetabolicState from physics engine.
        hours: (N,) fractional hours.
        glucose: (N,) cleaned glucose array.
        patient_id: patient letter (a-k) for model lookup.
        window: window size (w48, w72, w96, w144).
        models_dir: directory containing .pth files.
        device: 'cpu' or 'cuda'.
        isf: patient ISF for normalization.

    Returns:
        ForecastResult or None if models unavailable.
    """
    if not _torch_available:
        return None

    # Load ensemble
    ensemble = load_ensemble(patient_id, window, models_dir, device)
    if not ensemble:
        return None

    # Prepare input
    input_arr, hist_len = prepare_input_window(
        glucose, metabolic, patient, hours, window, isf)

    x = torch.tensor(input_arr, dtype=torch.float32).unsqueeze(0)  # (1, T, 8)
    x = x.to(torch.device(device))

    # Run ensemble predictions
    all_preds = []
    for model, seed in ensemble:
        with torch.no_grad():
            x_in = x.clone()
            # Mask future glucose (channel 0) — PK channels stay
            x_in[:, hist_len:, 0] = 0.0
            pred = model(x_in, causal=True)  # (1, T, 8)
            future_gluc = pred[0, hist_len:, 0].cpu().numpy()
            all_preds.append(future_gluc)

    preds = np.array(all_preds)  # (n_seeds, future_len)
    mean_pred = np.mean(preds, axis=0)
    std_pred = np.std(preds, axis=0)

    # Denormalize
    if isf is not None and isf > 0:
        mean_pred_mg = mean_pred * (isf / GLUCOSE_SCALE) * GLUCOSE_SCALE
        std_pred_mg = std_pred * (isf / GLUCOSE_SCALE) * GLUCOSE_SCALE
    else:
        mean_pred_mg = mean_pred * GLUCOSE_SCALE
        std_pred_mg = std_pred * GLUCOSE_SCALE

    # Clip to physiological range
    mean_pred_mg = np.clip(mean_pred_mg, 30.0, 400.0)

    future_len = len(mean_pred_mg)
    horizons_minutes = np.arange(1, future_len + 1) * 5

    # Confidence: inverse of ensemble std relative to MAE
    mean_std = float(np.mean(std_pred_mg))
    expected_mae = ROUTED_MAE.get(f'h{horizons_minutes[-1]}',
                                  ROUTED_MAE.get('h120', 17.0))
    confidence = max(0.0, min(1.0, 1.0 - mean_std / (expected_mae * 2)))

    # Build per-horizon MAE from routing table
    mae_metrics = {}
    for h_label, mae_val in ROUTED_MAE.items():
        h_min = int(h_label[1:])
        cfg = WINDOW_CONFIG[window]
        max_future_min = cfg['future'] * 5
        if h_min <= max_future_min:
            mae_metrics[h_label] = mae_val

    # Timestamps
    last_ts = int(patient.timestamps[-1]) if len(patient.timestamps) > 0 else 0
    forecast_ts = [last_ts + int(m * 60_000) for m in horizons_minutes]

    return ForecastResult(
        predicted_glucose=mean_pred_mg,
        ensemble_std=std_pred_mg,
        horizons_minutes=horizons_minutes,
        timestamps_ms=forecast_ts,
        ensemble_size=len(ensemble),
        mae_expected=mae_metrics,
        confidence=confidence,
        model_window=window,
        uses_isf_norm=isf is not None,
    )
