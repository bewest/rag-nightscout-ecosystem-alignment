#!/usr/bin/env python3
"""EXP-399 through EXP-402: Champion-Based Improvements

Phase 5 (v10/v11) regressed because training tricks were applied to the BASE
model, not the EXP-387 champion. This file corrects that by building EVERY
experiment on the champion architecture (dual encoder + shared ResNet ensemble
with ISF normalization and per-patient weights).

Progress report findings driving these experiments:
  - EXP-387 champion = 24.4 MAE (quick), 34.4 MAE (full at 8 horizons)
  - Per-patient fine-tuning is the #1 recommended next step (expected -3 to -5)
  - Single-horizon specialist avoids multi-horizon dilution (ERA 2 was single-h)
  - Training improvements (longer + SWA) should be applied to champion arch
  - ISF-normalized glucose is highest-priority normalization from evidence synthesis

EXP-399: Per-patient fine-tuning of champion models
  - Train globally, then fine-tune last layers per patient
  - Freeze encoder, unfreeze head, 10-20 epochs per patient
  - Expected: -3 to -5 MAE (single biggest expected improvement)

EXP-400: Single-horizon specialist at h60
  - Train dedicated model for h60 only (no multi-horizon dilution)
  - ERA 2's advantage was partly single-horizon focus
  - Expected: h60 from 23.7 → ~19-21 mg/dL

EXP-401: Training improvements ON champion architecture
  - Apply 100ep + SWA + cosine to the dual+shared ensemble
  - Phase 5 tested these on base model = wrong; now on champion = right
  - Expected: -1 to -2 MAE

EXP-402: Per-patient z-score normalization
  - Evidence synthesis ★★★★ priority: dual-channel (BG/400 + z-scored)
  - Equalizes cross-patient variance while preserving absolute thresholds
  - Expected: improved cross-patient generalization

── NEXT STEPS: After finishing v12, pick up v13 ─────────────────────────

  exp_pk_forecast_v13.py has EXP-403 and EXP-404 ready to run:

  EXP-403: Multi-rate EMA channels — replaces single glucose channel with
    fast/medium/slow EMA (α=0.7/0.3/0.1) plus raw + derivative = 5ch
    glucose branch. Complements your architecture improvements by giving the
    model multi-scale glucose dynamics. Uses feature_helpers.py.

  EXP-404: Glucodensity + functional depth as head features — proven FDA
    features (glucodensity Δ=+0.54 Silhouette, depth 112× hypo enrichment)
    injected at classifier head. Architecture-agnostic — works with your
    champion model. Uses feature_helpers.py.

  These are feature engineering experiments that DON'T conflict with your
  architecture/training improvements in v12. They complement them.

  Both experiments include clinical metrics (MARD, Clarke zones, ISO 15197,
  trend accuracy) automatically — evaluate_model() now scores every variant.

  Run: python tools/cgmencode/exp_pk_forecast_v13.py --experiment 403
       python tools/cgmencode/exp_pk_forecast_v13.py --experiment 404

Usage:
    python tools/cgmencode/exp_pk_forecast_v12.py --experiment 399 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v12.py --experiment all --device cuda
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

try:
    from cgmencode.metrics import compute_clinical_forecast_metrics
except ImportError:
    compute_clinical_forecast_metrics = None

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


# ─── Data Loading (from v9 — includes per-patient idx tracking) ───

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
        stride = 36

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir)
        pk_grid = build_continuous_pk_features(df)

        isf = None
        if load_isf:
            isf = load_patient_profile_isf(train_dir)

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
            'train_idx': (len(all_base_train), len(all_base_train) + len(bt)),
            'val_idx': (len(all_base_val), len(all_base_val) + len(bv)),
        }

        all_base_train.extend(bt)
        all_base_val.extend(bv)
        all_pk_train.extend(pt)
        all_pk_val.extend(pv)

        if isf is not None:
            all_isf_train.extend([isf] * len(bt))
            all_isf_val.extend([isf] * len(bv))

        name = pdir.name
        print(f"  {name}: {n} windows ({len(bt)} train, {len(bv)} val)")
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


# ─── Model Architectures (from v8 champion) ───

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

    def extract_features(self, x_hist, x_future):
        """Extract pre-head features for fine-tuning."""
        h = x_hist.permute(0, 2, 1)
        h = self.hist_stem(h)
        h = self.hist_blocks(h)
        h_feat = self.hist_pool(h).squeeze(-1)
        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)
        return torch.cat([h_feat, f_feat], dim=1)


class DualEncoderWithFuture(nn.Module):
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

    def extract_features(self, x_glucose, x_pk_hist, x_future):
        """Extract pre-head features for fine-tuning."""
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
        return torch.cat([g_feat, p_feat, f_feat], dim=1)


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, use_swa=False, swa_start_frac=0.75):
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    swa_model = None
    swa_scheduler = None
    swa_start = int(epochs * swa_start_frac) if use_swa else epochs + 1
    if use_swa:
        swa_model = torch.optim.swa_utils.AveragedModel(model)
        swa_scheduler = torch.optim.swa_utils.SWALR(
            optimizer, swa_lr=1e-4, anneal_epochs=5)

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
            loss = F.mse_loss(preds, targets)
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                targets = batch[-1].to(device)
                preds = model(*inputs)
                val_losses.append(F.mse_loss(preds, targets).item())

        val_loss = np.mean(val_losses)

        if epoch >= swa_start and swa_model is not None:
            swa_model.update_parameters(model)
            swa_scheduler.step()
        else:
            scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())
            wait = 0
        else:
            wait += 1
            if wait >= patience and epoch < swa_start:
                break

    if best_state is not None and swa_model is None:
        model.load_state_dict(best_state)

    if swa_model is not None:
        # Custom BN update for multi-input models
        _update_bn_multi_input(swa_model, train_loader, device)
        return swa_model.module

    return model


def _update_bn_multi_input(swa_model, loader, device):
    """Update BN stats for SWA model with multi-input forward pass."""
    for module in swa_model.modules():
        if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d)):
            module.reset_running_stats()
            module.momentum = None

    swa_model.train()
    with torch.no_grad():
        for batch in loader:
            inputs = [b.to(device) for b in batch[:-1]]
            swa_model(*inputs)
    swa_model.eval()


def fine_tune_model(model, train_loader, val_loader, device, epochs=15,
                    lr=1e-4, freeze_encoder=True):
    """Fine-tune a pre-trained model, optionally freezing encoder layers."""
    model.to(device)

    if freeze_encoder:
        # Freeze everything except the head
        for name, param in model.named_parameters():
            if 'head' not in name:
                param.requires_grad = False

    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.Adam(trainable, lr=lr)

    best_val_loss = float('inf')
    best_state = None

    for epoch in range(epochs):
        model.train()
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            optimizer.zero_grad()
            preds = model(*inputs)
            loss = F.mse_loss(preds, targets)
            loss.backward()
            optimizer.step()

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                targets = batch[-1].to(device)
                preds = model(*inputs)
                val_losses.append(F.mse_loss(preds, targets).item())

        val_loss = np.mean(val_losses)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())

    if best_state is not None:
        model.load_state_dict(best_state)

    # Unfreeze all parameters after fine-tuning
    for param in model.parameters():
        param.requires_grad = True

    return model


# ─── Evaluation ───

def evaluate_model(model, val_loader, device, horizons, scale=GLUCOSE_SCALE):
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1]
            preds = model(*inputs).cpu().numpy()
            all_preds.append(preds)
            all_targets.append(targets.numpy())

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

    # Clinical metrics: MARD, Clarke Error Grid, ISO 15197, trend accuracy
    if compute_clinical_forecast_metrics is not None:
        try:
            clinical = compute_clinical_forecast_metrics(
                targets, preds, glucose_scale=scale)
            result['clinical'] = clinical
        except Exception:
            pass

    return result, preds, targets


def optimize_ensemble_weights_2(preds_list, targets, horizons, scale=GLUCOSE_SCALE):
    """Optimize per-horizon α for 2-model ensemble."""
    assert len(preds_list) == 2
    p_a, p_b = preds_list

    optimal = {}
    for i, name in enumerate(horizons.keys()):
        best_alpha, best_mae = 0.5, float('inf')
        for alpha in np.arange(0.0, 1.01, 0.05):
            blend = alpha * p_a[:, i] + (1 - alpha) * p_b[:, i]
            mae = float(np.mean(np.abs(blend - targets[:, i])) * scale)
            if mae < best_mae:
                best_mae = mae
                best_alpha = alpha
        optimal[name] = float(best_alpha)
    return optimal


# ─── Feature Preparation (from v8 champion) ───

def prepare_dual_encoder_features(base_train, base_val, pk_train, pk_val,
                                  history_steps, horizons,
                                  isf_train=None, isf_val=None):
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    glucose_t = base_train[:, :history_steps, 0:1].copy().astype(np.float32)
    glucose_v = base_val[:, :history_steps, 0:1].copy().astype(np.float32)

    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        glucose_t[:, :, 0:1] *= isf_factor_t
        glucose_v[:, :, 0:1] *= isf_factor_v
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
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    hist_t = base_train[:, :history_steps].copy()
    hist_v = base_val[:, :history_steps].copy()

    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        hist_t[:, :, 0:1] *= isf_factor_t
        hist_v[:, :, 0:1] *= isf_factor_v
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


def prepare_dual_features_zscore(base_train, base_val, pk_train, pk_val,
                                 history_steps, horizons, per_patient,
                                 isf_train=None, isf_val=None):
    """Dual-channel glucose: BG/400 (raw) + z-scored (per-patient normalized).

    The raw channel preserves absolute thresholds (hypo < 70 mg/dL).
    The z-scored channel equalizes cross-patient variance for pattern matching.
    """
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    raw_t = base_train[:, :history_steps, 0:1].copy().astype(np.float32)
    raw_v = base_val[:, :history_steps, 0:1].copy().astype(np.float32)

    # Compute per-patient z-scores
    zscore_t = np.zeros_like(raw_t)
    zscore_v = np.zeros_like(raw_v)
    for pinfo in per_patient:
        t_start, t_end = pinfo['train_idx']
        v_start, v_end = pinfo['val_idx']
        # Compute stats from training portion of this patient
        patient_glucose = raw_t[t_start:t_end, :, 0]
        mu = patient_glucose.mean()
        sigma = max(patient_glucose.std(), 1e-6)
        zscore_t[t_start:t_end, :, 0] = (raw_t[t_start:t_end, :, 0] - mu) / sigma
        zscore_v[v_start:v_end, :, 0] = (raw_v[v_start:v_end, :, 0] - mu) / sigma

    # Stack: 2-channel glucose (raw + z-scored)
    glucose_t = np.concatenate([raw_t, zscore_t], axis=2)
    glucose_v = np.concatenate([raw_v, zscore_v], axis=2)

    # ISF normalization on raw channel only
    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        glucose_t[:, :, 0:1] *= isf_factor_t
        glucose_v[:, :, 0:1] *= isf_factor_v
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


# ─── DataLoader Helpers ───

def _make_dual_loaders(g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v,
                       batch_size=128):
    train_ds = TensorDataset(
        torch.from_numpy(g_t), torch.from_numpy(pk_h_t),
        torch.from_numpy(f_t), torch.from_numpy(t_t))
    val_ds = TensorDataset(
        torch.from_numpy(g_v), torch.from_numpy(pk_h_v),
        torch.from_numpy(f_v), torch.from_numpy(t_v))
    return (DataLoader(train_ds, batch_size=batch_size, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _make_shared_loaders(h_t, h_v, f_t, f_v, t_t, t_v, batch_size=128):
    train_ds = TensorDataset(
        torch.from_numpy(h_t), torch.from_numpy(f_t),
        torch.from_numpy(t_t.astype(np.float32)))
    val_ds = TensorDataset(
        torch.from_numpy(h_v), torch.from_numpy(f_v),
        torch.from_numpy(t_v.astype(np.float32)))
    return (DataLoader(train_ds, batch_size=batch_size, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _make_patient_loaders(g_all, pinfo, is_dual=True):
    """Create per-patient train/val loaders from full arrays."""
    t_start, t_end = pinfo['train_idx']
    v_start, v_end = pinfo['val_idx']

    if is_dual:
        train_ds = TensorDataset(
            torch.from_numpy(g_all[0][t_start:t_end]),
            torch.from_numpy(g_all[1][t_start:t_end]),
            torch.from_numpy(g_all[2][t_start:t_end]),
            torch.from_numpy(g_all[3][t_start:t_end]))
        val_ds = TensorDataset(
            torch.from_numpy(g_all[0][v_start:v_end]),
            torch.from_numpy(g_all[1][v_start:v_end]),
            torch.from_numpy(g_all[2][v_start:v_end]),
            torch.from_numpy(g_all[3][v_start:v_end]))
    else:
        train_ds = TensorDataset(
            torch.from_numpy(g_all[0][t_start:t_end]),
            torch.from_numpy(g_all[1][t_start:t_end]),
            torch.from_numpy(g_all[2][t_start:t_end]))
        val_ds = TensorDataset(
            torch.from_numpy(g_all[0][v_start:v_end]),
            torch.from_numpy(g_all[1][v_start:v_end]),
            torch.from_numpy(g_all[2][v_start:v_end]))

    bs = min(64, max(8, (t_end - t_start) // 4))
    return (DataLoader(train_ds, batch_size=bs, shuffle=True),
            DataLoader(val_ds, batch_size=256))


# ─── Result Helpers ───

def _run_variant(name, model, train_loader, val_loader, device, horizons,
                 train_kw, scale=GLUCOSE_SCALE):
    t0 = time.time()
    n_params = sum(p.numel() for p in model.parameters())
    model = train_model(model, train_loader, val_loader, device, **train_kw)
    res, preds, targets = evaluate_model(model, val_loader, device, horizons,
                                         scale=scale)
    elapsed = time.time() - t0
    res['n_params'] = n_params
    res['time_s'] = round(elapsed)
    h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
    print(f"    {name}... MAE={res['mae_overall']:.1f} [{h_str}]  ({res['time_s']}s)")
    return res, model, preds, targets


def _save_results(exp_name, description, results, horizons, filename):
    summary = defaultdict(lambda: defaultdict(list))
    for key, val in results.items():
        base = key.rsplit('_s', 1)[0]
        for metric, value in val.items():
            if isinstance(value, (int, float)):
                summary[base][metric].append(value)
            elif isinstance(value, dict) and metric == 'mae_per_horizon':
                for h, v in value.items():
                    summary[base][f'mae_{h}'].append(v)

    agg = {}
    for variant, metrics in summary.items():
        agg[variant] = {}
        for metric, values in metrics.items():
            agg[variant][metric] = {
                'mean': round(np.mean(values), 1),
                'std': round(np.std(values), 1),
            }

    output = {
        'experiment': exp_name,
        'description': description,
        'horizons': horizons,
        'raw_results': results,
        'summary': agg,
    }

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Saved: {filename}")

    print("─── Summary ───")
    for variant in sorted(agg.keys()):
        m = agg[variant]
        if 'mae_overall' in m:
            s = f"  {variant}: MAE={m['mae_overall']['mean']:.1f}±{m['mae_overall']['std']:.1f}"
            h_parts = []
            for h in horizons.keys():
                k = f'mae_{h}'
                if k in m:
                    h_parts.append(f"{h}={m[k]['mean']:.1f}±{m[k]['std']:.1f}")
            if h_parts:
                s += f" [{', '.join(h_parts)}]"
            print(s)


# ═══════════════════════════════════════════════════════════
# EXP-399: Per-Patient Fine-Tuning of Champion
# ═══════════════════════════════════════════════════════════

def run_exp399(args):
    """Per-patient fine-tuning: train globally, then fine-tune head per patient.

    The EXP-387 champion trains a global dual+shared ensemble. Per-patient
    fine-tuning should capture patient-specific insulin:glucose dynamics
    that the global model misses. This is the #1 recommended experiment
    from the progress report.

    Variants:
      1. baseline_ensemble: Global dual+shared ensemble (EXP-387 reproduction)
      2. finetune_head: Fine-tune head only (freeze encoder)
      3. finetune_full: Fine-tune all layers with low LR
      4. finetune_ensemble: Fine-tune both models, then ensemble
    """
    print("=" * 60)
    print("exp399_per_patient_finetune")
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
    base_epochs = QUICK_EPOCHS if quick else 60
    base_patience = QUICK_PATIENCE if quick else 15
    ft_epochs = 10 if quick else 20

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Prepare features
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        (sh_t, sh_v, sf_t, sf_v,
         stgt_t, stgt_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)
        shared_tl, shared_vl = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, stgt_t, stgt_v)

        # 1) Train global models (baseline reproduction)
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_global', dual_model, dual_tl, dual_vl,
            device, horizons, {'epochs': base_epochs, 'patience': base_patience})
        results[f"dual_global_s{seed}"] = res_dual

        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, _ = _run_variant(
            'shared_global', shared_model, shared_tl, shared_vl,
            device, horizons, {'epochs': base_epochs, 'patience': base_patience})
        results[f"shared_global_s{seed}"] = res_shared

        # Global ensemble baseline (per-patient weights from EXP-387)
        global_opt = optimize_ensemble_weights_2(
            [preds_dual, preds_shared], targets, horizons)

        ens_pp_preds = np.zeros_like(preds_dual)
        for pi, pinfo in enumerate(per_patient):
            v_start, v_end = pinfo['val_idx']
            if v_end - v_start < 5:
                for i, name in enumerate(horizons.keys()):
                    w = global_opt[name]
                    ens_pp_preds[v_start:v_end, i] = (
                        w * preds_dual[v_start:v_end, i] +
                        (1 - w) * preds_shared[v_start:v_end, i])
                continue
            pp_opt = optimize_ensemble_weights_2(
                [preds_dual[v_start:v_end], preds_shared[v_start:v_end]],
                targets[v_start:v_end], horizons)
            for i, name in enumerate(horizons.keys()):
                w = pp_opt[name]
                ens_pp_preds[v_start:v_end, i] = (
                    w * preds_dual[v_start:v_end, i] +
                    (1 - w) * preds_shared[v_start:v_end, i])

        ens_baseline = {}
        for i, name in enumerate(horizons.keys()):
            ens_baseline[name] = float(
                np.mean(np.abs(ens_pp_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        bl_res = {
            'mae_overall': float(np.mean(list(ens_baseline.values()))),
            'mae_per_horizon': ens_baseline,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_baseline.items())
        print(f"    baseline_ensemble... MAE={bl_res['mae_overall']:.1f} [{h_str}]")
        results[f"baseline_ensemble_s{seed}"] = bl_res

        # 2) Per-patient fine-tuning (head only)
        t0 = time.time()
        ft_head_dual_preds = preds_dual.copy()
        ft_head_shared_preds = preds_shared.copy()

        for pi, pinfo in enumerate(per_patient):
            t_start, t_end = pinfo['train_idx']
            v_start, v_end = pinfo['val_idx']
            if t_end - t_start < 20:
                continue

            # Fine-tune dual model head for this patient
            ft_dual = copy.deepcopy(dual_model)
            p_dual_tl, p_dual_vl = _make_patient_loaders(
                (g_t, pk_h_t, f_t, tgt_t), pinfo, is_dual=True)
            ft_dual = fine_tune_model(
                ft_dual, p_dual_tl, p_dual_vl, device,
                epochs=ft_epochs, lr=1e-4, freeze_encoder=True)

            # Get fine-tuned predictions for this patient's val set
            ft_dual.eval()
            with torch.no_grad():
                all_p = []
                for batch in p_dual_vl:
                    inputs = [b.to(device) for b in batch[:-1]]
                    all_p.append(ft_dual(*inputs).cpu().numpy())
            ft_head_dual_preds[v_start:v_end] = np.concatenate(all_p)

            # Fine-tune shared model head
            ft_shared = copy.deepcopy(shared_model)
            p_shared_tl, p_shared_vl = _make_patient_loaders(
                (sh_t, sf_t, stgt_t), pinfo, is_dual=False)
            ft_shared = fine_tune_model(
                ft_shared, p_shared_tl, p_shared_vl, device,
                epochs=ft_epochs, lr=1e-4, freeze_encoder=True)

            ft_shared.eval()
            with torch.no_grad():
                all_p = []
                for batch in p_shared_vl:
                    inputs = [b.to(device) for b in batch[:-1]]
                    all_p.append(ft_shared(*inputs).cpu().numpy())
            ft_head_shared_preds[v_start:v_end] = np.concatenate(all_p)

        # Evaluate fine-tuned dual
        ft_dual_ph = {}
        for i, name in enumerate(horizons.keys()):
            ft_dual_ph[name] = float(
                np.mean(np.abs(ft_head_dual_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ft_dual_res = {
            'mae_overall': float(np.mean(list(ft_dual_ph.values()))),
            'mae_per_horizon': ft_dual_ph,
            'time_s': round(time.time() - t0),
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_dual_ph.items())
        print(f"    finetune_head_dual... MAE={ft_dual_res['mae_overall']:.1f} [{h_str}]  ({ft_dual_res['time_s']}s)")
        results[f"finetune_head_dual_s{seed}"] = ft_dual_res

        # Evaluate fine-tuned shared
        ft_shared_ph = {}
        for i, name in enumerate(horizons.keys()):
            ft_shared_ph[name] = float(
                np.mean(np.abs(ft_head_shared_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ft_shared_res = {
            'mae_overall': float(np.mean(list(ft_shared_ph.values()))),
            'mae_per_horizon': ft_shared_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_shared_ph.items())
        print(f"    finetune_head_shared... MAE={ft_shared_res['mae_overall']:.1f} [{h_str}]")
        results[f"finetune_head_shared_s{seed}"] = ft_shared_res

        # 3) Per-patient fine-tuning (all layers, low LR)
        t0 = time.time()
        ft_full_dual_preds = preds_dual.copy()

        for pi, pinfo in enumerate(per_patient):
            t_start, t_end = pinfo['train_idx']
            v_start, v_end = pinfo['val_idx']
            if t_end - t_start < 20:
                continue

            ft_dual = copy.deepcopy(dual_model)
            p_dual_tl, p_dual_vl = _make_patient_loaders(
                (g_t, pk_h_t, f_t, tgt_t), pinfo, is_dual=True)
            ft_dual = fine_tune_model(
                ft_dual, p_dual_tl, p_dual_vl, device,
                epochs=ft_epochs, lr=5e-5, freeze_encoder=False)

            ft_dual.eval()
            with torch.no_grad():
                all_p = []
                for batch in p_dual_vl:
                    inputs = [b.to(device) for b in batch[:-1]]
                    all_p.append(ft_dual(*inputs).cpu().numpy())
            ft_full_dual_preds[v_start:v_end] = np.concatenate(all_p)

        ft_full_ph = {}
        for i, name in enumerate(horizons.keys()):
            ft_full_ph[name] = float(
                np.mean(np.abs(ft_full_dual_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ft_full_res = {
            'mae_overall': float(np.mean(list(ft_full_ph.values()))),
            'mae_per_horizon': ft_full_ph,
            'time_s': round(time.time() - t0),
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_full_ph.items())
        print(f"    finetune_full_dual... MAE={ft_full_res['mae_overall']:.1f} [{h_str}]  ({ft_full_res['time_s']}s)")
        results[f"finetune_full_dual_s{seed}"] = ft_full_res

        # 4) Fine-tuned ensemble (head-finetuned dual + head-finetuned shared)
        ft_ens_preds = np.zeros_like(preds_dual)
        for pi, pinfo in enumerate(per_patient):
            v_start, v_end = pinfo['val_idx']
            p_d = ft_head_dual_preds[v_start:v_end]
            p_s = ft_head_shared_preds[v_start:v_end]
            p_t = targets[v_start:v_end]

            if v_end - v_start < 5:
                ft_ens_preds[v_start:v_end] = 0.5 * p_d + 0.5 * p_s
                continue

            pp_opt = optimize_ensemble_weights_2([p_d, p_s], p_t, horizons)
            for i, name in enumerate(horizons.keys()):
                w = pp_opt[name]
                ft_ens_preds[v_start:v_end, i] = w * p_d[:, i] + (1 - w) * p_s[:, i]

        ft_ens_ph = {}
        for i, name in enumerate(horizons.keys()):
            ft_ens_ph[name] = float(
                np.mean(np.abs(ft_ens_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ft_ens_res = {
            'mae_overall': float(np.mean(list(ft_ens_ph.values()))),
            'mae_per_horizon': ft_ens_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_ens_ph.items())
        print(f"    finetune_ensemble... MAE={ft_ens_res['mae_overall']:.1f} [{h_str}]")
        results[f"finetune_ensemble_s{seed}"] = ft_ens_res

    _save_results('exp399_per_patient_finetune',
                  'Per-patient fine-tuning of champion dual+shared ensemble',
                  results, horizons,
                  'externals/experiments/exp399_per_patient_finetune.json')


# ═══════════════════════════════════════════════════════════
# EXP-400: Single-Horizon Specialist at h60
# ═══════════════════════════════════════════════════════════

def run_exp400(args):
    """Single-horizon specialist: train dedicated models for each horizon.

    ERA 2's advantage was single-horizon focus. Multi-horizon training
    dilutes optimization across horizons. Test whether a dedicated h60
    model (n_horizons=1) significantly beats the multi-horizon model at h60.

    Variants:
      1. multi_horizon: Standard multi-h model (reference at h60)
      2. h60_specialist: Dedicated h60-only model
      3. h30_specialist: Dedicated h30-only model
      4. specialist_ensemble: Per-horizon specialists combined
    """
    print("=" * 60)
    print("exp400_single_horizon_specialist")
    print("=" * 60)

    device = torch.device(args.device)
    quick = args.quick
    history_steps = 72
    multi_horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_multi = len(multi_horizons)
    max_horizon = max(multi_horizons.values())

    # Individual horizon configs
    specialist_horizons = {
        'h30': {'h30': 6},
        'h60': {'h60': 12},
        'h120': {'h120': 24},
    }

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

        # Multi-horizon reference (dual encoder)
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, multi_horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)

        torch.manual_seed(seed)
        multi_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_multi)
        res_multi, _, preds_multi, targets_multi = _run_variant(
            'multi_horizon', multi_model, dual_tl, dual_vl,
            device, multi_horizons, train_kw)
        results[f"multi_horizon_s{seed}"] = res_multi

        # Single-horizon specialists
        specialist_preds = {}
        for h_name, h_dict in specialist_horizons.items():
            (sg_t, sg_v, spk_h_t, spk_h_v, sf_t, sf_v,
             stgt_t, stgt_v) = prepare_dual_encoder_features(
                base_t, base_v, pk_t, pk_v, history_steps, h_dict,
                isf_train=isf_t, isf_val=isf_v)

            s_tl, s_vl = _make_dual_loaders(
                sg_t, sg_v, spk_h_t, spk_h_v, sf_t, sf_v, stgt_t, stgt_v)

            torch.manual_seed(seed)
            spec_model = DualEncoderWithFuture(
                pk_hist_channels=4, pk_future_channels=4, n_horizons=1)
            res_spec, _, preds_spec, targets_spec = _run_variant(
                f'{h_name}_specialist', spec_model, s_tl, s_vl,
                device, h_dict, train_kw)
            results[f"{h_name}_specialist_s{seed}"] = res_spec
            specialist_preds[h_name] = (preds_spec, targets_spec)

        # Combined specialist ensemble: use each specialist for its horizon
        # Report MAE at matching horizons
        combined_ph = {}
        for h_name in specialist_horizons:
            sp, st = specialist_preds[h_name]
            mae = float(np.mean(np.abs(sp[:, 0] - st[:, 0])) * GLUCOSE_SCALE)
            combined_ph[h_name] = mae

        combined_res = {
            'mae_overall': float(np.mean(list(combined_ph.values()))),
            'mae_per_horizon': combined_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in combined_ph.items())
        print(f"    specialist_ensemble... MAE={combined_res['mae_overall']:.1f} [{h_str}]")
        results[f"specialist_ensemble_s{seed}"] = combined_res

    _save_results('exp400_single_horizon_specialist',
                  'Single-horizon specialist vs multi-horizon',
                  results, {**HORIZONS_STANDARD},
                  'externals/experiments/exp400_specialist.json')


# ═══════════════════════════════════════════════════════════
# EXP-401: Training Improvements ON Champion Architecture
# ═══════════════════════════════════════════════════════════

def run_exp401(args):
    """Apply training improvements to champion architecture.

    Phase 5 (v10/v11) applied SWA, longer training, cosine annealing to the
    BASE model. The progress report identified this as a regression because
    the champion is EXP-387 (dual+shared ensemble with ISF + per-patient
    weights). Now we apply these same tricks to the RIGHT architecture.

    Variants:
      1. baseline_60ep: Champion architecture, 60 epochs (reference)
      2. long_100ep: 100 epochs, patience 20
      3. swa_60ep: 60ep with SWA (last 25%)
      4. swa_100ep: 100ep with SWA
      5. long_100ep_ensemble: 100ep dual + 100ep shared + per-patient weights
    """
    print("=" * 60)
    print("exp401_champion_training_improvements")
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

    configs = [
        ('baseline_60ep',  {'epochs': 30 if quick else 60,  'patience': 8 if quick else 15, 'use_swa': False}),
        ('long_100ep',     {'epochs': 50 if quick else 100, 'patience': 12 if quick else 20, 'use_swa': False}),
        ('swa_60ep',       {'epochs': 30 if quick else 60,  'patience': 8 if quick else 15, 'use_swa': True}),
        ('swa_100ep',      {'epochs': 50 if quick else 100, 'patience': 12 if quick else 20, 'use_swa': True}),
    ]

    results = {}

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Prepare features (same for all configs)
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        (sh_t, sh_v, sf_t, sf_v,
         stgt_t, stgt_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)
        shared_tl, shared_vl = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, stgt_t, stgt_v)

        for config_name, train_kw in configs:
            torch.manual_seed(seed)
            dual_model = DualEncoderWithFuture(
                pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
            res_dual, _, preds_dual, targets = _run_variant(
                f'dual_{config_name}', dual_model, dual_tl, dual_vl,
                device, horizons, train_kw)
            results[f"dual_{config_name}_s{seed}"] = res_dual

            torch.manual_seed(seed)
            shared_model = ResNetCNNWithFuture(
                hist_channels=8, pk_channels=4, n_horizons=n_horizons)
            res_shared, _, preds_shared, _ = _run_variant(
                f'shared_{config_name}', shared_model, shared_tl, shared_vl,
                device, horizons, train_kw)
            results[f"shared_{config_name}_s{seed}"] = res_shared

            # Per-patient ensemble for this config
            ens_preds = np.zeros_like(preds_dual)
            global_opt = optimize_ensemble_weights_2(
                [preds_dual, preds_shared], targets, horizons)
            for pi, pinfo in enumerate(per_patient):
                v_start, v_end = pinfo['val_idx']
                if v_end - v_start < 5:
                    for i, name in enumerate(horizons.keys()):
                        w = global_opt[name]
                        ens_preds[v_start:v_end, i] = (
                            w * preds_dual[v_start:v_end, i] +
                            (1 - w) * preds_shared[v_start:v_end, i])
                    continue
                pp_opt = optimize_ensemble_weights_2(
                    [preds_dual[v_start:v_end], preds_shared[v_start:v_end]],
                    targets[v_start:v_end], horizons)
                for i, name in enumerate(horizons.keys()):
                    w = pp_opt[name]
                    ens_preds[v_start:v_end, i] = (
                        w * preds_dual[v_start:v_end, i] +
                        (1 - w) * preds_shared[v_start:v_end, i])

            ens_ph = {}
            for i, name in enumerate(horizons.keys()):
                ens_ph[name] = float(
                    np.mean(np.abs(ens_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
            ens_res = {
                'mae_overall': float(np.mean(list(ens_ph.values()))),
                'mae_per_horizon': ens_ph,
            }
            h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_ph.items())
            print(f"    ensemble_{config_name}... MAE={ens_res['mae_overall']:.1f} [{h_str}]")
            results[f"ensemble_{config_name}_s{seed}"] = ens_res

    _save_results('exp401_champion_training_improvements',
                  'Training improvements (SWA, longer epochs) on champion architecture',
                  results, horizons,
                  'externals/experiments/exp401_champion_training.json')


# ═══════════════════════════════════════════════════════════
# EXP-402: Per-Patient Z-Score Normalization
# ═══════════════════════════════════════════════════════════

def run_exp402(args):
    """Per-patient z-score + raw dual-channel glucose normalization.

    Evidence synthesis ★★★★ priority. Currently glucose is normalized by
    BG/400 (fixed scale). Per-patient z-scoring equalizes variance across
    patients. Providing BOTH channels (raw + z-scored) lets the model use
    z-scored for pattern shape and raw for absolute threshold detection.

    Variants:
      1. baseline_1ch: Standard BG/400 single channel (reference)
      2. zscore_2ch: BG/400 + z-scored dual channel
      3. zscore_only_1ch: Z-scored only (no raw — test if abs thresholds matter)
    """
    print("=" * 60)
    print("exp402_zscore_normalization")
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

        # 1) Baseline 1ch (standard ISF-normalized)
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)

        torch.manual_seed(seed)
        model_1ch = DualEncoderWithFuture(
            glucose_channels=1, pk_hist_channels=4,
            pk_future_channels=4, n_horizons=n_horizons)
        res_1ch, _, _, _ = _run_variant(
            'baseline_1ch', model_1ch, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"baseline_1ch_s{seed}"] = res_1ch

        # 2) Z-score 2ch (raw + z-scored)
        (gz_t, gz_v, pkz_h_t, pkz_h_v, fz_t, fz_v,
         ztgt_t, ztgt_v) = prepare_dual_features_zscore(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            per_patient, isf_train=isf_t, isf_val=isf_v)

        z2_tl, z2_vl = _make_dual_loaders(
            gz_t, gz_v, pkz_h_t, pkz_h_v, fz_t, fz_v, ztgt_t, ztgt_v)

        torch.manual_seed(seed)
        model_2ch = DualEncoderWithFuture(
            glucose_channels=2, pk_hist_channels=4,
            pk_future_channels=4, n_horizons=n_horizons)
        res_2ch, _, _, _ = _run_variant(
            'zscore_2ch', model_2ch, z2_tl, z2_vl,
            device, horizons, train_kw)
        results[f"zscore_2ch_s{seed}"] = res_2ch

        # 3) Z-score only (drop raw channel)
        gz_only_t = gz_t[:, :, 1:2].copy()  # just the z-scored channel
        gz_only_v = gz_v[:, :, 1:2].copy()

        z1_tl, z1_vl = _make_dual_loaders(
            gz_only_t, gz_only_v, pkz_h_t, pkz_h_v, fz_t, fz_v, ztgt_t, ztgt_v)

        torch.manual_seed(seed)
        model_z1 = DualEncoderWithFuture(
            glucose_channels=1, pk_hist_channels=4,
            pk_future_channels=4, n_horizons=n_horizons)
        res_z1, _, _, _ = _run_variant(
            'zscore_only_1ch', model_z1, z1_tl, z1_vl,
            device, horizons, train_kw)
        results[f"zscore_only_1ch_s{seed}"] = res_z1

    _save_results('exp402_zscore_normalization',
                  'Per-patient z-score glucose normalization',
                  results, horizons,
                  'externals/experiments/exp402_zscore.json')


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='EXP-399–402: Champion improvements')
    parser.add_argument('--experiment', type=str, default='all',
                        help='399, 400, 401, 402, or "all"')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, fewer epochs')
    args = parser.parse_args()

    experiments = {
        '399': run_exp399,
        '400': run_exp400,
        '401': run_exp401,
        '402': run_exp402,
    }

    if args.experiment == 'all':
        for name, fn in experiments.items():
            fn(args)
    elif args.experiment in experiments:
        experiments[args.experiment](args)
    else:
        print(f"Unknown experiment: {args.experiment}")
        print(f"Available: {', '.join(experiments.keys())}, all")
        sys.exit(1)


if __name__ == '__main__':
    main()
