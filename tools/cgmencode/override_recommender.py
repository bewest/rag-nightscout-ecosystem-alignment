"""
override_recommender.py — Override recommendation pipeline for AID systems.

Completes the override pipeline: we already know WHEN to recommend an override
(EXP-227: TIR-impact F1=0.993), but not WHAT override to recommend.
This module answers WHICH type and HOW strong.

Build on:
  - EXP-077: Action magnitude (bolus MAE=2.3U via GradientBoosting)
  - EXP-097: Action-value estimation (ISF estimate limited)
  - EXP-227: Override WHEN detection (TIR-impact utility F1=0.993)

Approach: Counterfactual forecasting — run the forecast model with different
override scenarios injected, score each by predicted TIR, and recommend the
best one. Also provides a trained value model for fast inference.
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from .schema import (
    NORMALIZATION_SCALES, FUTURE_UNKNOWN_CHANNELS,
    IDX_OVERRIDE_ACTIVE, IDX_OVERRIDE_TYPE, OVERRIDE_TYPES,
    NUM_FEATURES, NUM_FEATURES_EXTENDED,
)
from .experiment_lib import (
    create_model, mask_future_channels, get_device, batch_to_device,
    set_seed,
)


GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']  # 400.0

# Standard override types and strength multipliers
OVERRIDE_TYPE_LIST = ['eating_soon', 'exercise', 'sleep', 'sick', 'custom']
OVERRIDE_STRENGTHS = [0.5, 0.75, 1.0, 1.25, 1.5]  # temp basal multiplier

# TIR bounds (mg/dL normalized)
TIR_LOW = 70.0 / GLUCOSE_SCALE   # 0.175
TIR_HIGH = 180.0 / GLUCOSE_SCALE  # 0.45


def _compute_tir(glucose_trajectory):
    """Compute Time-in-Range for a glucose trajectory tensor.

    Args:
        glucose_trajectory: (B, T) normalized glucose values

    Returns:
        (B,) TIR fraction per sample
    """
    in_range = (glucose_trajectory >= TIR_LOW) & (glucose_trajectory <= TIR_HIGH)
    return in_range.float().mean(dim=1)


def counterfactual_forecast(model, x, override_type, strength, horizon_steps=None):
    """Predict glucose trajectory under a hypothetical override.

    Injects override_active=1.0 and override_type encoding into channels 10,11
    of the input, then runs the forecast model.

    Args:
        model: CGMGroupedEncoder instance (must accept ≥ 12 input channels)
        x: (B, T, C) input window — must have C ≥ 12 for override channels
        override_type: str from OVERRIDE_TYPE_LIST (e.g., 'eating_soon')
        strength: float — currently encodes as override_type * strength
        horizon_steps: If set, return only this many future steps

    Returns:
        (B, T_future, 1) predicted glucose trajectory under this override
    """
    device = x.device
    half = x.shape[1] // 2
    n_channels = x.shape[2]

    x_cf = x.clone()

    # Inject override into channels 10, 11 (if available)
    if n_channels > IDX_OVERRIDE_TYPE:
        type_val = OVERRIDE_TYPES.get(override_type, 0.0)
        x_cf[:, :, IDX_OVERRIDE_ACTIVE] = 1.0
        x_cf[:, :, IDX_OVERRIDE_TYPE] = type_val * strength

    mask_future_channels(x_cf, half)

    model.eval()
    with torch.no_grad():
        pred = model(x_cf, causal=True)
        if isinstance(pred, dict):
            pred = pred['forecast']

    future_pred = pred[:, half:, :1]
    if horizon_steps is not None:
        future_pred = future_pred[:, :horizon_steps, :]
    return future_pred


def evaluate_overrides(model, x, override_types=None, strengths=None,
                       horizon_steps=12):
    """Score each (type, strength) pair by predicted TIR.

    Args:
        model: Forecast model
        x: (B, T, C) input batch
        override_types: List of override type strings (default: OVERRIDE_TYPE_LIST)
        strengths: List of strength multipliers (default: OVERRIDE_STRENGTHS)
        horizon_steps: Steps in future to evaluate (12 = 60 min)

    Returns:
        List of dicts sorted by predicted_tir descending:
        [{'type': str, 'strength': float, 'predicted_tir': float, 'predicted_mean_glucose': float}]
    """
    if override_types is None:
        override_types = OVERRIDE_TYPE_LIST
    if strengths is None:
        strengths = OVERRIDE_STRENGTHS

    results = []
    for otype in override_types:
        for strength in strengths:
            pred_g = counterfactual_forecast(
                model, x, otype, strength, horizon_steps=horizon_steps)
            # pred_g: (B, hz, 1) — squeeze to (B, hz)
            pred_flat = pred_g.squeeze(-1)
            tir = _compute_tir(pred_flat).mean().item()
            mean_g = pred_flat.mean().item() * GLUCOSE_SCALE
            results.append({
                'type': otype,
                'strength': strength,
                'predicted_tir': round(tir, 4),
                'predicted_mean_glucose': round(mean_g, 1),
            })

    results.sort(key=lambda r: r['predicted_tir'], reverse=True)
    return results


def recommend_override(model, x, override_types=None, strengths=None,
                       horizon_steps=12):
    """Recommend the best override for the current glucose state.

    Args:
        model: Forecast model (must accept ≥ 12 input channels)
        x: (B, T, C) input batch
        override_types, strengths, horizon_steps: Passed to evaluate_overrides

    Returns:
        dict with:
            override_type: str — recommended type
            strength: float — recommended strength
            confidence: float — TIR improvement over no-override
            predicted_tir: float — expected TIR with recommendation
            predicted_tir_no_override: float — expected TIR without override
            all_evaluations: list — full ranked results
    """
    # Get no-override baseline
    half = x.shape[1] // 2
    x_baseline = x.clone()
    mask_future_channels(x_baseline, half)
    model.eval()
    with torch.no_grad():
        baseline_pred = model(x_baseline, causal=True)
        if isinstance(baseline_pred, dict):
            baseline_pred = baseline_pred['forecast']
    baseline_tir = _compute_tir(
        baseline_pred[:, half:half + horizon_steps, 0]).mean().item()

    ranked = evaluate_overrides(model, x, override_types, strengths, horizon_steps)
    best = ranked[0]

    return {
        'override_type': best['type'],
        'strength': best['strength'],
        'confidence': round(best['predicted_tir'] - baseline_tir, 4),
        'predicted_tir': best['predicted_tir'],
        'predicted_tir_no_override': round(baseline_tir, 4),
        'all_evaluations': ranked,
    }


class OverrideValueModel(nn.Module):
    """Learned mapping: (glucose_state, override_type, strength) → TIR_delta.

    Faster than counterfactual at inference (no N forward passes needed).
    Train on historical override outcomes.
    """

    def __init__(self, state_dim=8, hidden_dim=64, n_override_types=5):
        super().__init__()
        # Input: state features + one-hot override type + strength scalar
        input_dim = state_dim + n_override_types + 1
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),  # predicted TIR delta
        )
        self.n_override_types = n_override_types

    def forward(self, state, override_type_idx, strength):
        """
        Args:
            state: (B, state_dim) glucose state summary
            override_type_idx: (B,) long tensor — index into override types
            strength: (B, 1) strength multiplier

        Returns:
            (B, 1) predicted TIR delta
        """
        onehot = torch.zeros(state.size(0), self.n_override_types,
                             device=state.device)
        onehot.scatter_(1, override_type_idx.unsqueeze(1), 1.0)
        x = torch.cat([state, onehot, strength], dim=1)
        return self.net(x)


def train_override_value_model(train_ds, val_ds, save_path,
                               state_dim=8, hidden_dim=64,
                               label='override-value', lr=1e-3,
                               epochs=50, patience=15, batch_size=32):
    """Train the value model on historical override outcomes.

    Datasets should yield (state, override_type_idx, strength, tir_delta) tuples.

    Args:
        train_ds, val_ds: TensorDatasets with 4 tensors each
        save_path: Checkpoint path
        state_dim, hidden_dim: Architecture params
        label, lr, epochs, patience, batch_size: Training params

    Returns:
        (best_val_loss, epochs_run, model)
    """
    device = get_device()
    model = OverrideValueModel(state_dim=state_dim, hidden_dim=hidden_dim)
    model.to(device)

    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    crit = nn.MSELoss()
    best_val, stale = float('inf'), 0

    for ep in range(epochs):
        model.train()
        for batch in DataLoader(train_ds, batch_size=batch_size, shuffle=True):
            state = batch[0].to(device)
            otype = batch[1].to(device)
            strength = batch[2].to(device)
            tir_delta = batch[3].to(device)

            pred = model(state, otype, strength)
            loss = crit(pred, tir_delta.unsqueeze(1))
            opt.zero_grad()
            loss.backward()
            opt.step()

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for batch in DataLoader(val_ds, batch_size=64):
                state = batch[0].to(device)
                otype = batch[1].to(device)
                strength = batch[2].to(device)
                tir_delta = batch[3].to(device)
                pred = model(state, otype, strength)
                vtl += crit(pred, tir_delta.unsqueeze(1)).item() * state.size(0)
                vn += state.size(0)
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best_val:
            best_val, stale = vl, 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'epoch': ep,
                         'val_loss': vl, 'label': label}, save_path)
        else:
            stale += 1
        if patience > 0 and stale >= patience:
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])

    return best_val, ep + 1, model
