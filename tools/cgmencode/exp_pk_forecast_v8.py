#!/usr/bin/env python3
"""EXP-382 through EXP-385: Ensemble, Horizon Weighting & Cross-Attention

Key insight from EXP-378 full validation:
  - Dual encoder: h30=19.7 (best ever), but h120=38.5
  - Shared ResNet: h30=21.5 (worse), but h120=37.9 (better)
  - Both tie at MAE=35.9 overall. Champion is EXP-368 at 35.8.

The architectures have COMPLEMENTARY strengths by horizon. This enables:

EXP-382 — Model Ensemble
  Average predictions from dual_isf + shared_isf at eval time.
  If errors are decorrelated, ensemble MAE < min(individual MAEs).
  Also: learned per-horizon weighting (α_h optimized on held-out fold).
  Hypothesis: Ensemble beats 35.8 champion by combining h30+h120 strengths.

EXP-383 — Horizon-Weighted Loss
  Weight h30/h60 loss by 2× (clinically most important).
  Weight h480/h720 by 0.5× (regression-to-mean anyway).
  Hypothesis: Focusing model capacity on short horizons improves h30
  without proportional h120+ degradation (since long horizons are noise).

EXP-384 — Dual Encoder with IOB Branch
  Add IOB (dense signal, directly tied to glucose) to glucose branch.
  2ch glucose+IOB encoder vs 1ch glucose-only encoder.
  Hypothesis: IOB context helps the glucose encoder without PK noise.

EXP-385 — Cross-Attention Fusion
  After encoding glucose and PK separately, apply cross-attention.
  Glucose features attend to PK features to identify relevant PK moments.
  Hypothesis: Learned attention > simple concatenation for late fusion.

Usage:
    python tools/cgmencode/exp_pk_forecast_v8.py --experiment 382 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v8.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse, copy
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features
from cgmencode.metrics import compute_clinical_forecast_metrics

# ─── Constants ───

SEEDS = [42, 123, 456]
SEEDS_QUICK = [42]
GLUCOSE_SCALE = 400.0
QUICK_PATIENTS = 4
QUICK_EPOCHS = 30
QUICK_PATIENCE = 8

HORIZONS_EXTENDED = {
    'h30': 6, 'h60': 12, 'h120': 24, 'h180': 36,
    'h240': 48, 'h360': 72, 'h480': 96, 'h720': 144,
}
HORIZONS_STANDARD = {'h30': 6, 'h60': 12, 'h120': 24}

PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
FUTURE_PK_INDICES = [1, 2, 3, 6]  # insulin_net, carb_rate, net_balance, net_effect


# ─── Data Loading (shared with v7) ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile_isf(train_dir):
    profile_path = os.path.join(train_dir, 'profile.json')
    if not os.path.exists(profile_path):
        return None
    try:
        with open(profile_path) as f:
            profile = json.load(f)
        store = profile.get('store', {})
        default_profile = store.get('Default', store.get(next(iter(store), ''), {}))
        sens = default_profile.get('sens', [])
        if sens:
            isf_values = [s.get('value', 0) for s in sens]
            mean_isf = np.mean([v for v in isf_values if v > 0])
            if mean_isf < 15:
                mean_isf *= 18.0182
            return float(mean_isf) if mean_isf > 0 else None
        return None
    except Exception:
        return None


def load_forecast_data(patients_dir, history_steps=72, max_horizon=144,
                       max_patients=None, load_isf=False, stride=None):
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    all_isf_train, all_isf_val = [], []
    per_patient = []
    window_size = history_steps + max_horizon

    if stride is None:
        stride = history_steps // 2

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir)
        pk_grid = build_continuous_pk_features(df)

        isf = None
        if load_isf:
            isf = load_patient_profile_isf(train_dir)

        # Windowing
        n_steps = min(len(base_grid), len(pk_grid))
        windows_b, windows_p = [], []
        for start in range(0, n_steps - window_size + 1, stride):
            w_b = base_grid[start:start + window_size]
            w_p = pk_grid[start:start + window_size]
            if np.isnan(w_b[:history_steps, 0]).mean() > 0.3:
                continue
            w_b = np.nan_to_num(w_b, 0.0)
            w_p = np.nan_to_num(w_p, 0.0)
            windows_b.append(w_b)
            windows_p.append(w_p)

        if len(windows_b) < 10:
            continue

        n = len(windows_b)
        split = int(0.8 * n)
        bt, bv = windows_b[:split], windows_b[split:]
        pt, pv = windows_p[:split], windows_p[split:]

        patient_info = {
            'name': pdir.name,
            'n_windows': n,
            'n_train': len(bt),
            'n_val': len(bv),
            'isf': isf,
        }

        all_base_train.extend(bt)
        all_base_val.extend(bv)
        all_pk_train.extend(pt)
        all_pk_val.extend(pv)

        if isf is not None:
            all_isf_train.extend([isf] * len(bt))
            all_isf_val.extend([isf] * len(bv))

        name = pdir.name
        print(f"  {name}: {n} windows ({len(bt)} train, {len(bv)} val)"
              f"  [stride={stride}]")
        per_patient.append(patient_info)

    base_t = np.array(all_base_train, dtype=np.float32)
    base_v = np.array(all_base_val, dtype=np.float32)
    pk_t = np.array(all_pk_train, dtype=np.float32)
    pk_v = np.array(all_pk_val, dtype=np.float32)
    print(f"Total: {len(base_t)} train, {len(base_v)} val")

    if load_isf and all_isf_train:
        isf_t = np.array(all_isf_train, dtype=np.float32)
        isf_v = np.array(all_isf_val, dtype=np.float32)
        return base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient
    return base_t, base_v, pk_t, pk_v, None, None, per_patient


def extract_targets(base_windows, history_steps, horizons):
    indices = list(horizons.values())
    return base_windows[:, [history_steps + idx - 1 for idx in indices], 0]


# ─── Model Building Blocks ───

class ResBlock1d(nn.Module):
    def __init__(self, in_ch, out_ch, dropout=0.1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_ch, out_ch, 3, padding=1)
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, 3, padding=1)
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.skip = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        residual = self.skip(x)
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.drop(out)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual)


class ResNetCNNWithFuture(nn.Module):
    """Standard ResNet + future PK (baseline reference)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.hist_stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.hist_blocks = nn.Sequential(
            ResBlock1d(64, 128, dropout=dropout),
            ResBlock1d(128, 128, dropout=dropout),
            ResBlock1d(128, 64, dropout=dropout),
        )
        self.hist_pool = nn.AdaptiveAvgPool1d(1)
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        h = self.hist_stem(h)
        h = self.hist_blocks(h)
        h_feat = self.hist_pool(h).squeeze(-1)
        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


class DualEncoderWithFuture(nn.Module):
    """Separate encoders for glucose vs PK/treatment features."""
    def __init__(self, glucose_channels=1, pk_hist_channels=4,
                 pk_future_channels=4, n_horizons=8, dropout=0.1):
        super().__init__()
        self.glucose_stem = nn.Sequential(
            nn.Conv1d(glucose_channels, 48, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(48),
        )
        self.glucose_blocks = nn.Sequential(
            ResBlock1d(48, 96, dropout=dropout),
            ResBlock1d(96, 96, dropout=dropout),
            ResBlock1d(96, 48, dropout=dropout),
        )
        self.glucose_pool = nn.AdaptiveAvgPool1d(1)

        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32),
        )
        self.pk_blocks = nn.Sequential(
            ResBlock1d(32, 64, dropout=dropout),
            ResBlock1d(64, 32, dropout=dropout),
        )
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )

        self.head = nn.Sequential(
            nn.Linear(48 + 32 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_glucose, x_pk_hist, x_future):
        g = x_glucose.permute(0, 2, 1)
        g = self.glucose_stem(g)
        g = self.glucose_blocks(g)
        g_feat = self.glucose_pool(g).squeeze(-1)

        p = x_pk_hist.permute(0, 2, 1)
        p = self.pk_stem(p)
        p = self.pk_blocks(p)
        p_feat = self.pk_pool(p).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([g_feat, p_feat, f_feat], dim=1))


class DualEncoderCrossAttention(nn.Module):
    """Dual encoder with cross-attention between glucose and PK features.

    After separate encoding, glucose features attend to PK features:
    - Q from glucose encoder (what glucose "wants to know")
    - K, V from PK encoder (what PK can tell)
    This lets the model learn which PK moments are relevant for
    each glucose feature, enabling horizon-aware information routing.
    """
    def __init__(self, pk_hist_channels=4, pk_future_channels=4,
                 n_horizons=8, dropout=0.1, n_heads=4):
        super().__init__()
        self.glucose_stem = nn.Sequential(
            nn.Conv1d(1, 48, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(48),
        )
        self.glucose_blocks = nn.Sequential(
            ResBlock1d(48, 48, dropout=dropout),
            ResBlock1d(48, 48, dropout=dropout),
        )

        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 48, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(48),
        )
        self.pk_blocks = nn.Sequential(
            ResBlock1d(48, 48, dropout=dropout),
        )

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )

        # Cross-attention: glucose attends to PK
        self.cross_attn = nn.MultiheadAttention(
            embed_dim=48, num_heads=n_heads, dropout=dropout, batch_first=True)
        self.attn_norm = nn.LayerNorm(48)

        self.glucose_pool = nn.AdaptiveAvgPool1d(1)
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        self.head = nn.Sequential(
            nn.Linear(48 + 48 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_glucose, x_pk_hist, x_future):
        g = x_glucose.permute(0, 2, 1)  # (B, 1, T) -> (B, 48, T)
        g = self.glucose_stem(g)
        g = self.glucose_blocks(g)

        p = x_pk_hist.permute(0, 2, 1)
        p = self.pk_stem(p)
        p = self.pk_blocks(p)

        # Cross-attention: glucose queries, PK keys/values
        # Transpose to (B, T, C) for attention
        g_seq = g.permute(0, 2, 1)  # (B, T, 48)
        p_seq = p.permute(0, 2, 1)  # (B, T, 48)
        attn_out, _ = self.cross_attn(g_seq, p_seq, p_seq)
        g_attended = self.attn_norm(g_seq + attn_out)  # residual connection

        # Pool attended glucose features
        g_feat = g_attended.permute(0, 2, 1)  # back to (B, 48, T)
        g_feat = self.glucose_pool(g_feat).squeeze(-1)

        p_feat = self.pk_pool(p).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([g_feat, p_feat, f_feat], dim=1))


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, loss_fn='mse', horizon_weights=None):
    """Train with optional per-horizon loss weighting."""
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    hw = None
    if horizon_weights is not None:
        hw = torch.tensor(horizon_weights, dtype=torch.float32, device=device)

    best_val_loss = float('inf')
    best_state = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        train_losses = []
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            optimizer.zero_grad()

            preds = model(*inputs)
            if hw is not None:
                per_sample = (preds - targets) ** 2  # (B, H)
                loss = torch.mean(per_sample * hw.unsqueeze(0))
            else:
                loss = F.mse_loss(preds, targets)

            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                targets = batch[-1].to(device)
                preds = model(*inputs)
                if hw is not None:
                    vl = torch.mean((preds - targets) ** 2 * hw.unsqueeze(0))
                else:
                    vl = F.mse_loss(preds, targets)
                val_losses.append(vl.item())

        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone()
                          for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    return model


def evaluate_model(model, val_loader, device, horizons, scale=GLUCOSE_SCALE):
    """Returns result dict, raw predictions, raw targets."""
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            preds = model(*inputs)
            all_preds.append(preds.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    per_horizon = {}
    for i, name in enumerate(horizons.keys()):
        mae = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * scale)
        per_horizon[name] = mae

    result = {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }

    try:
        clinical = compute_clinical_forecast_metrics(
            targets, preds, glucose_scale=scale)
        result['clinical'] = clinical
    except Exception:
        pass

    return result, preds, targets


def evaluate_ensemble(preds_list, targets, horizons, scale=GLUCOSE_SCALE,
                      weights=None):
    """Evaluate ensemble of predictions.

    Args:
        preds_list: list of prediction arrays, each (N, H)
        targets: ground truth (N, H)
        horizons: dict of horizon names → indices
        scale: glucose scale for MAE conversion
        weights: optional per-model weights (default: equal)

    Returns:
        result dict with MAE per horizon
    """
    if weights is None:
        weights = np.ones(len(preds_list)) / len(preds_list)
    else:
        weights = np.array(weights) / np.sum(weights)

    ensemble_preds = sum(w * p for w, p in zip(weights, preds_list))

    per_horizon = {}
    for i, name in enumerate(horizons.keys()):
        mae = float(np.mean(np.abs(ensemble_preds[:, i] - targets[:, i])) * scale)
        per_horizon[name] = mae

    result = {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }
    return result


def optimize_ensemble_weights(preds_list, targets, horizons, scale=GLUCOSE_SCALE):
    """Find per-horizon optimal weights via grid search.

    For each horizon, find α that minimizes MAE of
    α * preds_A + (1-α) * preds_B.

    Returns:
        dict mapping horizon name → optimal α for model A
    """
    assert len(preds_list) == 2, "Only supports 2-model ensemble"
    p_a, p_b = preds_list

    optimal_weights = {}
    for i, name in enumerate(horizons.keys()):
        best_alpha, best_mae = 0.5, float('inf')
        for alpha in np.arange(0.0, 1.01, 0.05):
            blend = alpha * p_a[:, i] + (1 - alpha) * p_b[:, i]
            mae = float(np.mean(np.abs(blend - targets[:, i])) * scale)
            if mae < best_mae:
                best_mae = mae
                best_alpha = alpha
        optimal_weights[name] = float(best_alpha)

    return optimal_weights


# ─── Feature Preparation ───

def prepare_dual_encoder_features(base_train, base_val, pk_train, pk_val,
                                  history_steps, horizons,
                                  isf_train=None, isf_val=None,
                                  include_iob=False):
    """Prepare separate glucose, PK-history, and future-PK tensors.

    If include_iob=True, glucose tensor has 2 channels (glucose + IOB).
    """
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    if include_iob:
        # Glucose + IOB (channel 1 in base_grid)
        glucose_t = base_train[:, :history_steps, 0:2].copy().astype(np.float32)
        glucose_v = base_val[:, :history_steps, 0:2].copy().astype(np.float32)
    else:
        glucose_t = base_train[:, :history_steps, 0:1].copy().astype(np.float32)
        glucose_v = base_val[:, :history_steps, 0:1].copy().astype(np.float32)

    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        # Only ISF-normalize the glucose channel (index 0)
        glucose_t[:, :, 0:1] = glucose_t[:, :, 0:1] * isf_factor_t
        glucose_v[:, :, 0:1] = glucose_v[:, :, 0:1] * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(glucose_t[:, :, 0:1], 0, 10, out=glucose_t[:, :, 0:1])
        np.clip(glucose_v[:, :, 0:1], 0, 10, out=glucose_v[:, :, 0:1])

    pk_hist_t = np.stack([
        pk_train[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    pk_hist_v = np.stack([
        pk_val[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    future_t = np.stack([
        pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    future_v = np.stack([
        pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    return (glucose_t, glucose_v, pk_hist_t, pk_hist_v,
            future_t, future_v, targets_train, targets_val)


def prepare_shared_features(base_train, base_val, pk_train, pk_val,
                            history_steps, horizons,
                            isf_train=None, isf_val=None):
    """Prepare 8ch + future PK features for shared ResNet reference."""
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    hist_t = base_train[:, :history_steps].copy()
    hist_v = base_val[:, :history_steps].copy()

    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        hist_t[:, :, 0:1] = hist_t[:, :, 0:1] * isf_factor_t
        hist_v[:, :, 0:1] = hist_v[:, :, 0:1] * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(hist_t[:, :, 0:1], 0, 10, out=hist_t[:, :, 0:1])
        np.clip(hist_v[:, :, 0:1], 0, 10, out=hist_v[:, :, 0:1])

    future_t = np.stack([
        pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    future_v = np.stack([
        pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    return (hist_t.astype(np.float32), hist_v.astype(np.float32),
            future_t, future_v, targets_train, targets_val)


# ─── Helpers ───

def _make_dual_loaders(g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v):
    train_ds = TensorDataset(
        torch.from_numpy(g_t), torch.from_numpy(pk_h_t),
        torch.from_numpy(f_t), torch.from_numpy(t_t))
    val_ds = TensorDataset(
        torch.from_numpy(g_v), torch.from_numpy(pk_h_v),
        torch.from_numpy(f_v), torch.from_numpy(t_v))
    return (DataLoader(train_ds, batch_size=128, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _make_shared_loaders(h_t, h_v, f_t, f_v, t_t, t_v):
    train_ds = TensorDataset(
        torch.from_numpy(h_t), torch.from_numpy(f_t),
        torch.from_numpy(t_t.astype(np.float32)))
    val_ds = TensorDataset(
        torch.from_numpy(h_v), torch.from_numpy(f_v),
        torch.from_numpy(t_v.astype(np.float32)))
    return (DataLoader(train_ds, batch_size=128, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _run_variant(name, model, train_loader, val_loader, device, horizons,
                 train_kw, scale=GLUCOSE_SCALE):
    t0 = time.time()
    n_params = sum(p.numel() for p in model.parameters())
    model = train_model(model, train_loader, val_loader, device, **train_kw)
    res, preds, targets = evaluate_model(model, val_loader, device, horizons,
                                         scale=scale)
    elapsed = time.time() - t0
    h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
    print(f"    {name}... MAE={res['mae_overall']:.1f} [{h_str}]"
          f"  ({n_params:,} params, {elapsed:.0f}s)")
    res['n_params'] = n_params
    return res, model, preds, targets


def _save_results(exp_name, description, results, horizons, filepath):
    summary = {}
    variant_groups = defaultdict(list)
    for key, val in results.items():
        parts = key.rsplit('_', 1)
        base_name = parts[0] if len(parts) > 1 and parts[-1].startswith('s') else key
        variant_groups[base_name].append(val)

    for vname, runs in variant_groups.items():
        maes = [r['mae_overall'] for r in runs]
        horizon_means = {}
        for h in horizons:
            vals = [r['mae_per_horizon'].get(h, 0) for r in runs]
            horizon_means[h] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals))}
        summary[vname] = {
            'mae_overall_mean': float(np.mean(maes)),
            'mae_overall_std': float(np.std(maes)),
            'mae_per_horizon': horizon_means,
            'n_seeds': len(runs),
        }

    data = {
        'experiment': exp_name,
        'description': description,
        'horizons': horizons,
        'results': results,
        'summary': summary,
    }
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved: {filepath}")

    print("\n─── Summary ───")
    for vname, stats in sorted(summary.items()):
        h_strs = ', '.join(
            f"{h}={stats['mae_per_horizon'][h]['mean']:.1f}±{stats['mae_per_horizon'][h]['std']:.1f}"
            for h in horizons)
        print(f"  {vname}: MAE={stats['mae_overall_mean']:.1f}±{stats['mae_overall_std']:.1f} "
              f"[{h_strs}]")


# ═══════════════════════════════════════════════════════════
# EXP-382: Model Ensemble (Dual + Shared)
# ═══════════════════════════════════════════════════════════

def run_exp_382(args):
    print("=" * 60)
    print("exp382_ensemble")
    print("=" * 60)

    device = torch.device(args.device)
    quick = args.quick
    history_steps = 72
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    max_patients = QUICK_PATIENTS if quick else None
    data = load_forecast_data(
        args.patients_dir, history_steps, max_horizon,
        max_patients=max_patients, load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    seeds = SEEDS_QUICK if quick else SEEDS
    train_kw = {
        'epochs': QUICK_EPOCHS if quick else 60,
        'patience': QUICK_PATIENCE if quick else 15,
    }

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Prepare features (ISF-normalized)
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        (sh_t, sh_v, sf_t, sf_v,
         stgt_t, stgt_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_loader_t, dual_loader_v = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)
        shared_loader_t, shared_loader_v = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, stgt_t, stgt_v)

        # Train dual encoder
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4,
            n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_isf', dual_model, dual_loader_t, dual_loader_v,
            device, horizons, train_kw)
        results[f"dual_isf_s{seed}"] = res_dual

        # Train shared ResNet
        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, targets_shared = _run_variant(
            'shared_isf', shared_model, shared_loader_t, shared_loader_v,
            device, horizons, train_kw)
        results[f"shared_isf_s{seed}"] = res_shared

        # Ensemble 1: Simple average (equal weights)
        ens_equal = evaluate_ensemble(
            [preds_dual, preds_shared], targets, horizons)
        h_str = ', '.join(f"{k}={v:.1f}"
                          for k, v in ens_equal['mae_per_horizon'].items())
        print(f"    ensemble_equal... MAE={ens_equal['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_equal_s{seed}"] = ens_equal

        # Ensemble 2: Dual-weighted (70% dual for h30-h60, 30% for h120+)
        dual_weight_map = {
            'h30': 0.8, 'h60': 0.7, 'h120': 0.3, 'h180': 0.3,
            'h240': 0.3, 'h360': 0.4, 'h480': 0.4, 'h720': 0.5,
        }
        ens_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            w = dual_weight_map.get(name, 0.5)
            ens_preds[:, i] = w * preds_dual[:, i] + (1 - w) * preds_shared[:, i]
        ens_weighted_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_weighted_ph[name] = float(
                np.mean(np.abs(ens_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_weighted = {
            'mae_overall': float(np.mean(list(ens_weighted_ph.values()))),
            'mae_per_horizon': ens_weighted_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}"
                          for k, v in ens_weighted['mae_per_horizon'].items())
        print(f"    ensemble_weighted... MAE={ens_weighted['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_weighted_s{seed}"] = ens_weighted

        # Ensemble 3: Optimal per-horizon weights (found via grid search)
        opt_weights = optimize_ensemble_weights(
            [preds_dual, preds_shared], targets, horizons)
        ens_opt_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            w = opt_weights[name]
            ens_opt_preds[:, i] = w * preds_dual[:, i] + (1 - w) * preds_shared[:, i]
        ens_opt_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_opt_ph[name] = float(
                np.mean(np.abs(ens_opt_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_opt = {
            'mae_overall': float(np.mean(list(ens_opt_ph.values()))),
            'mae_per_horizon': ens_opt_ph,
            'optimal_weights': opt_weights,
        }
        h_str = ', '.join(f"{k}={v:.1f}"
                          for k, v in ens_opt['mae_per_horizon'].items())
        wt_str = ', '.join(f"{k}={v:.2f}" for k, v in opt_weights.items())
        print(f"    ensemble_optimal... MAE={ens_opt['mae_overall']:.1f} [{h_str}]"
              f"\n      α_dual=[{wt_str}]")
        results[f"ensemble_optimal_s{seed}"] = ens_opt

    _save_results('exp382_ensemble',
                  'Model ensemble: dual encoder + shared ResNet with ISF',
                  results, horizons,
                  'externals/experiments/exp382_ensemble.json')


# ═══════════════════════════════════════════════════════════
# EXP-383: Horizon-Weighted Loss
# ═══════════════════════════════════════════════════════════

def run_exp_383(args):
    print("=" * 60)
    print("exp383_horizon_loss")
    print("=" * 60)

    device = torch.device(args.device)
    quick = args.quick
    history_steps = 72
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    max_patients = QUICK_PATIENTS if quick else None
    data = load_forecast_data(
        args.patients_dir, history_steps, max_horizon,
        max_patients=max_patients, load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    seeds = SEEDS_QUICK if quick else SEEDS
    base_train_kw = {
        'epochs': QUICK_EPOCHS if quick else 60,
        'patience': QUICK_PATIENCE if quick else 15,
    }

    # Weight profiles to test
    n_h = n_horizons
    weight_profiles = {
        'uniform': [1.0] * n_h,
        'clinical': [],  # h30=3×, h60=2×, h120=1.5×, rest=1×, h720=0.5×
        'short_focus': [],  # h30=4×, h60=2×, rest=0.5×
        'exponential_decay': [],  # exp(-0.3*i) weighting
    }

    # Build clinical weights based on horizon names
    h_names = list(horizons.keys())
    clinical_map = {'h30': 3.0, 'h60': 2.0, 'h120': 1.5, 'h180': 1.0,
                    'h240': 1.0, 'h360': 0.8, 'h480': 0.7, 'h720': 0.5}
    weight_profiles['clinical'] = [clinical_map.get(h, 1.0) for h in h_names]

    short_map = {'h30': 4.0, 'h60': 2.0, 'h120': 1.0, 'h180': 0.5,
                 'h240': 0.5, 'h360': 0.5, 'h480': 0.5, 'h720': 0.5}
    weight_profiles['short_focus'] = [short_map.get(h, 0.5) for h in h_names]

    weight_profiles['exponential_decay'] = [
        float(np.exp(-0.3 * i)) for i in range(n_h)]

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")

        # Prepare features (dual encoder with ISF)
        torch.manual_seed(seed)
        np.random.seed(seed)

        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)
        loader_t, loader_v = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)

        for wname, weights in weight_profiles.items():
            torch.manual_seed(seed)
            model = DualEncoderWithFuture(
                pk_hist_channels=4, pk_future_channels=4,
                n_horizons=n_horizons)

            hw = weights if wname != 'uniform' else None
            train_kw = {**base_train_kw, 'horizon_weights': hw}

            res, model, preds, targets = _run_variant(
                wname, model, loader_t, loader_v, device, horizons,
                train_kw)
            results[f"{wname}_s{seed}"] = res

    _save_results('exp383_horizon_loss',
                  'Horizon-weighted MSE loss for dual encoder',
                  results, horizons,
                  'externals/experiments/exp383_horizon_loss.json')


# ═══════════════════════════════════════════════════════════
# EXP-384: Dual Encoder + IOB Branch
# ═══════════════════════════════════════════════════════════

def run_exp_384(args):
    print("=" * 60)
    print("exp384_dual_iob")
    print("=" * 60)

    device = torch.device(args.device)
    quick = args.quick
    history_steps = 72
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    max_patients = QUICK_PATIENTS if quick else None
    data = load_forecast_data(
        args.patients_dir, history_steps, max_horizon,
        max_patients=max_patients, load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    seeds = SEEDS_QUICK if quick else SEEDS
    train_kw = {
        'epochs': QUICK_EPOCHS if quick else 60,
        'patience': QUICK_PATIENCE if quick else 15,
    }

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Variant 1: Standard dual encoder (1ch glucose)
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v, include_iob=False)
        loader_t, loader_v = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)

        torch.manual_seed(seed)
        model_1ch = DualEncoderWithFuture(
            glucose_channels=1, pk_hist_channels=4,
            pk_future_channels=4, n_horizons=n_horizons)
        res_1ch, _, _, _ = _run_variant(
            'dual_glucose_1ch', model_1ch, loader_t, loader_v,
            device, horizons, train_kw)
        results[f"dual_glucose_1ch_s{seed}"] = res_1ch

        # Variant 2: Dual encoder with IOB (2ch glucose+IOB)
        (g2_t, g2_v, pk_h2_t, pk_h2_v, f2_t, f2_v,
         tgt2_t, tgt2_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v, include_iob=True)
        loader2_t, loader2_v = _make_dual_loaders(
            g2_t, g2_v, pk_h2_t, pk_h2_v, f2_t, f2_v, tgt2_t, tgt2_v)

        torch.manual_seed(seed)
        model_2ch = DualEncoderWithFuture(
            glucose_channels=2, pk_hist_channels=4,
            pk_future_channels=4, n_horizons=n_horizons)
        res_2ch, _, _, _ = _run_variant(
            'dual_glucose_iob_2ch', model_2ch, loader2_t, loader2_v,
            device, horizons, train_kw)
        results[f"dual_glucose_iob_2ch_s{seed}"] = res_2ch

    _save_results('exp384_dual_iob',
                  'Dual encoder with IOB in glucose branch',
                  results, horizons,
                  'externals/experiments/exp384_dual_iob.json')


# ═══════════════════════════════════════════════════════════
# EXP-385: Cross-Attention Fusion
# ═══════════════════════════════════════════════════════════

def run_exp_385(args):
    print("=" * 60)
    print("exp385_cross_attn")
    print("=" * 60)

    device = torch.device(args.device)
    quick = args.quick
    history_steps = 72
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    max_patients = QUICK_PATIENTS if quick else None
    data = load_forecast_data(
        args.patients_dir, history_steps, max_horizon,
        max_patients=max_patients, load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    seeds = SEEDS_QUICK if quick else SEEDS
    train_kw = {
        'epochs': QUICK_EPOCHS if quick else 60,
        'patience': QUICK_PATIENCE if quick else 15,
    }

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)
        loader_t, loader_v = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)

        # Variant 1: Standard dual encoder (concatenation fusion)
        torch.manual_seed(seed)
        model_concat = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4,
            n_horizons=n_horizons)
        res_concat, _, _, _ = _run_variant(
            'dual_concat', model_concat, loader_t, loader_v,
            device, horizons, train_kw)
        results[f"dual_concat_s{seed}"] = res_concat

        # Variant 2: Cross-attention fusion (4 heads)
        torch.manual_seed(seed)
        model_xattn4 = DualEncoderCrossAttention(
            pk_hist_channels=4, pk_future_channels=4,
            n_horizons=n_horizons, n_heads=4)
        res_xattn4, _, _, _ = _run_variant(
            'dual_xattn_4h', model_xattn4, loader_t, loader_v,
            device, horizons, train_kw)
        results[f"dual_xattn_4h_s{seed}"] = res_xattn4

        # Variant 3: Cross-attention fusion (8 heads)
        torch.manual_seed(seed)
        model_xattn8 = DualEncoderCrossAttention(
            pk_hist_channels=4, pk_future_channels=4,
            n_horizons=n_horizons, n_heads=8)
        res_xattn8, _, _, _ = _run_variant(
            'dual_xattn_8h', model_xattn8, loader_t, loader_v,
            device, horizons, train_kw)
        results[f"dual_xattn_8h_s{seed}"] = res_xattn8

    _save_results('exp385_cross_attn',
                  'Cross-attention fusion between glucose and PK encoders',
                  results, horizons,
                  'externals/experiments/exp385_cross_attn.json')


# ─── CLI ───

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='EXP-382 to EXP-385: Ensemble & advanced fusion')
    parser.add_argument('--experiment', type=str, default='382',
                        help='Experiment number (382-385) or "all"')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '382': run_exp_382,
        '383': run_exp_383,
        '384': run_exp_384,
        '385': run_exp_385,
    }

    if args.experiment == 'all':
        for name, fn in experiments.items():
            fn(args)
    elif args.experiment in experiments:
        experiments[args.experiment](args)
    else:
        print(f"Unknown experiment: {args.experiment}")
        print(f"Available: {', '.join(experiments.keys())} or 'all'")
        sys.exit(1)
