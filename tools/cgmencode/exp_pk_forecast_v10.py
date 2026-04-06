#!/usr/bin/env python3
"""EXP-391 through EXP-395: Training Improvements & Feature Refinement

Champion: EXP-382 ensemble (34.4±0.1) — dual encoder + shared ResNet.
V9 showed: 3-model ensemble doesn't beat 2-model. Distillation and boosting
work but don't surpass ensemble. Architecture complexity always hurts at scale.

V10 strategy: Improve the INDIVIDUAL models within the champion ensemble.
Feature and training changes translate reliably from quick→full mode.
Better individuals → better ensemble without adding model count.

EXP-391 — Stochastic Weight Averaging (SWA)
  After standard training, continue with cyclical LR for 20 epochs
  and average weights. SWA typically gives 0.5-1.5% improvement for free.
  This is a training technique, not architecture change → should translate.

EXP-392 — Data Augmentation
  Time series augmentation: Gaussian noise, magnitude scaling, temporal
  jitter. Addresses limited data (1400 windows/patient). Should help
  most for patients with less data (h: 1434 windows vs i: 1435).
  Variants: noise_only, scale_only, combined, aggressive.

EXP-393 — Cosine Annealing with Warm Restarts
  Replace ReduceLROnPlateau with CosineAnnealingWarmRestarts.
  Multiple warm restarts explore broader loss landscape.
  Combined with longer training (100 epochs instead of 60).

EXP-394 — Horizon-Weighted Ensemble Training
  Train dual encoder emphasizing h30-h120 (short-term specialization).
  Train shared ResNet emphasizing h240-h720 (long-term specialization).
  Then ensemble. Each model focuses where it's already strongest.

EXP-395 — Multi-Resolution Ensemble
  Train same architecture at 6h and 12h history windows, then ensemble.
  6h model: better at h30-h120 (less noise, more data per window).
  12h model: better at h360-h720 (sees full DIA context, meal patterns).
  Different from adding 3rd model type — same arch, different data view.

Usage:
    python tools/cgmencode/exp_pk_forecast_v10.py --experiment 391 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v10.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from torch.optim.swa_utils import AveragedModel, SWALR
import json, os, sys, time, argparse, copy
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

SEEDS_FULL = [42, 123, 456]
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


# ─── Data Loading (shared with v7/v8) ───

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
    """Standard ResNet + future PK (the shared model in champion ensemble)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.hist_stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=7, padding=3),
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
    """The dual encoder in champion ensemble (v6 architecture)."""
    def __init__(self, pk_hist_channels, pk_future_channels,
                 n_horizons=8, dropout=0.1):
        super().__init__()
        self.glucose_stem = nn.Sequential(
            nn.Conv1d(1, 48, kernel_size=7, padding=3),
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


# ─── Training Functions ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, horizon_weights=None):
    """Standard training with early stopping."""
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
                per_sample = (preds - targets) ** 2
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


def train_model_swa(model, train_loader, val_loader, device, epochs=60,
                    patience=15, lr=1e-3, swa_start_frac=0.75,
                    swa_lr=5e-4, swa_epochs=20):
    """Train with standard training then SWA phase.
    
    Phase 1: Standard training with early stopping (standard epochs)
    Phase 2: SWA with cyclical LR from best model state
    """
    model = train_model(model, train_loader, val_loader, device,
                        epochs=epochs, patience=patience, lr=lr)

    # Phase 2: SWA from best model state
    swa_model = AveragedModel(model)
    optimizer = torch.optim.SGD(model.parameters(), lr=swa_lr)
    swa_scheduler = SWALR(optimizer, swa_lr=swa_lr, anneal_epochs=5)

    model.to(device)
    for epoch in range(swa_epochs):
        model.train()
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            optimizer.zero_grad()
            preds = model(*inputs)
            loss = F.mse_loss(preds, targets)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        swa_model.update_parameters(model)
        swa_scheduler.step()

    # Custom BN update for multi-input models
    # (torch.optim.swa_utils.update_bn only handles single-input)
    _update_bn_multi_input(train_loader, swa_model, device)
    return swa_model


def _update_bn_multi_input(loader, model, device):
    """Update BatchNorm stats for models with multiple inputs."""
    # Reset BN running stats
    for module in model.modules():
        if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d)):
            module.reset_running_stats()
            module.momentum = None  # use cumulative moving average

    model.train()
    with torch.no_grad():
        for batch in loader:
            inputs = [b.to(device) for b in batch[:-1]]
            model(*inputs)


def train_model_cosine(model, train_loader, val_loader, device, epochs=100,
                       lr=1e-3, T_0=20, T_mult=2):
    """Train with CosineAnnealingWarmRestarts scheduler.
    
    No early stopping — relies on LR schedule to prevent overfitting.
    Restarts at epoch T_0, T_0*T_mult, T_0*T_mult^2, ...
    With T_0=20, T_mult=2: restarts at 20, 60, (would be 140 but capped at 100)
    """
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=T_0, T_mult=T_mult)

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
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        scheduler.step()

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
            best_state = {k: v.cpu().clone()
                          for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    return model


class AugmentedDataset(torch.utils.data.Dataset):
    """Wraps a TensorDataset with online time-series augmentation."""

    def __init__(self, base_dataset, noise_std=0.0, scale_range=0.0,
                 jitter_steps=0):
        self.base = base_dataset
        self.noise_std = noise_std
        self.scale_range = scale_range
        self.jitter_steps = jitter_steps

    def __len__(self):
        return len(self.base)

    def __getitem__(self, idx):
        tensors = list(self.base[idx])
        # Augment only input tensors (not the last one = targets)
        for i in range(len(tensors) - 1):
            t = tensors[i].clone()
            if self.noise_std > 0:
                t = t + torch.randn_like(t) * self.noise_std
            if self.scale_range > 0:
                scale = 1.0 + (torch.rand(1).item() * 2 - 1) * self.scale_range
                t = t * scale
            if self.jitter_steps > 0 and t.dim() >= 1 and t.shape[0] > 2:
                shift = torch.randint(-self.jitter_steps, self.jitter_steps + 1,
                                      (1,)).item()
                if shift != 0:
                    t = torch.roll(t, shifts=shift, dims=0)
            tensors[i] = t
        return tuple(tensors)


# ─── Evaluation ───

def evaluate_model(model, val_loader, device, horizons, scale=GLUCOSE_SCALE):
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1]
            preds = model(*inputs).cpu()
            all_preds.append(preds)
            all_targets.append(targets)
    preds = torch.cat(all_preds).numpy()
    targets = torch.cat(all_targets).numpy()
    names = list(horizons.keys())
    per_h = {}
    for i, name in enumerate(names):
        per_h[name] = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * scale)
    per_h['overall'] = float(np.mean(list(per_h.values())))
    return per_h, preds, targets


def evaluate_ensemble(preds_list, targets, horizons, scale=GLUCOSE_SCALE,
                      weights=None):
    """Evaluate ensemble of prediction arrays (in normalized space)."""
    if weights is None:
        weights = [1.0 / len(preds_list)] * len(preds_list)
    n_h = len(list(horizons.keys()))
    names = list(horizons.keys())

    if isinstance(weights[0], (list, np.ndarray)):
        combined = np.zeros_like(preds_list[0])
        for h_idx in range(n_h):
            for m_idx, p in enumerate(preds_list):
                combined[:, h_idx] += weights[m_idx][h_idx] * p[:, h_idx]
    else:
        combined = sum(w * p for w, p in zip(weights, preds_list))

    per_h = {}
    for i, name in enumerate(names):
        per_h[name] = float(np.mean(np.abs(combined[:, i] - targets[:, i])) * scale)
    per_h['overall'] = float(np.mean(list(per_h.values())))
    return per_h


def optimize_ensemble_weights(preds_list, targets, horizons, steps=21):
    """Grid search for optimal per-horizon 2-model weights."""
    assert len(preds_list) == 2
    names = list(horizons.keys())
    best_weights = [[], []]
    for h_idx in range(len(names)):
        best_mae = float('inf')
        best_a = 0.5
        for a_int in range(0, steps):
            a = a_int / (steps - 1)
            combined = a * preds_list[0][:, h_idx] + (1 - a) * preds_list[1][:, h_idx]
            mae = np.mean(np.abs(combined - targets[:, h_idx]))
            if mae < best_mae:
                best_mae = mae
                best_a = a
        best_weights[0].append(best_a)
        best_weights[1].append(1 - best_a)
    return best_weights


# ─── Input Preparation ───

def prepare_inputs(base_t, base_v, pk_t, pk_v, history_steps, horizons,
                   isf_t=None, isf_v=None, max_horizon=144):
    """Prepare model inputs for dual encoder + shared ResNet with ISF normalization.

    base_t/base_v columns are ALREADY normalized by build_nightscout_grid
    (glucose/400, IOB, COB, etc). DO NOT divide by GLUCOSE_SCALE again.
    ISF normalization: multiply glucose by (GLUCOSE_SCALE / ISF) to convert
    from glucose/400 → glucose/ISF space. Apply to BOTH inputs and targets.
    """
    tgt_t = extract_targets(base_t, history_steps, horizons)
    tgt_v = extract_targets(base_v, history_steps, horizons)

    # Glucose channel for dual encoder
    gluc_t = base_t[:, :history_steps, 0:1].copy()
    gluc_v = base_v[:, :history_steps, 0:1].copy()
    if isf_t is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_t).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_v).reshape(-1, 1, 1)
        gluc_t *= isf_factor_t
        gluc_v *= isf_factor_v
        tgt_t = tgt_t * (GLUCOSE_SCALE / isf_t).reshape(-1, 1)
        tgt_v = tgt_v * (GLUCOSE_SCALE / isf_v).reshape(-1, 1)
        np.clip(gluc_t, 0, 10, out=gluc_t)
        np.clip(gluc_v, 0, 10, out=gluc_v)

    # Shared history (8ch) — ISF-normalize only glucose column
    hist_t = base_t[:, :history_steps, :].copy()
    hist_v = base_v[:, :history_steps, :].copy()
    if isf_t is not None:
        hist_t[:, :, 0:1] *= (GLUCOSE_SCALE / isf_t).reshape(-1, 1, 1)
        hist_v[:, :, 0:1] *= (GLUCOSE_SCALE / isf_v).reshape(-1, 1, 1)
        np.clip(hist_t[:, :, 0:1], 0, 10, out=hist_t[:, :, 0:1])
        np.clip(hist_v[:, :, 0:1], 0, 10, out=hist_v[:, :, 0:1])

    # PK history
    pk_hist_t = np.stack([
        pk_t[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES], axis=-1)
    pk_hist_v = np.stack([
        pk_v[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES], axis=-1)

    # Future PK
    fpk_t = np.stack([
        pk_t[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES], axis=-1)
    fpk_v = np.stack([
        pk_v[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES], axis=-1)

    # Shared model: hist + PK history
    combined_hist_t = np.concatenate([hist_t, pk_hist_t], axis=-1)
    combined_hist_v = np.concatenate([hist_v, pk_hist_v], axis=-1)

    return {
        'glucose': (gluc_t, gluc_v),
        'pk_hist': (pk_hist_t, pk_hist_v),
        'future_pk': (fpk_t, fpk_v),
        'combined_hist': (combined_hist_t, combined_hist_v),
        'targets': (tgt_t, tgt_v),
    }


def make_loaders(inputs_dict, model_type='dual', batch_size=128):
    """Create DataLoaders for the specified model type."""
    tgt_t, tgt_v = inputs_dict['targets']

    if model_type == 'dual':
        gluc_t, gluc_v = inputs_dict['glucose']
        pk_t, pk_v = inputs_dict['pk_hist']
        fpk_t, fpk_v = inputs_dict['future_pk']
        train_ds = TensorDataset(
            torch.from_numpy(gluc_t), torch.from_numpy(pk_t),
            torch.from_numpy(fpk_t), torch.from_numpy(tgt_t))
        val_ds = TensorDataset(
            torch.from_numpy(gluc_v), torch.from_numpy(pk_v),
            torch.from_numpy(fpk_v), torch.from_numpy(tgt_v))
    elif model_type == 'shared':
        ch_t, ch_v = inputs_dict['combined_hist']
        fpk_t, fpk_v = inputs_dict['future_pk']
        train_ds = TensorDataset(
            torch.from_numpy(ch_t), torch.from_numpy(fpk_t),
            torch.from_numpy(tgt_t))
        val_ds = TensorDataset(
            torch.from_numpy(ch_v), torch.from_numpy(fpk_v),
            torch.from_numpy(tgt_v))
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=256, shuffle=False)
    return train_loader, val_loader, train_ds, val_ds


# ─── EXP-391: Stochastic Weight Averaging ───

def run_exp_391(patients_dir, device, quick=False):
    """SWA applied to both champion models, then ensembled."""
    print("\nexp391_swa")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL
    epochs = QUICK_EPOCHS if quick else 60
    patience = QUICK_PATIENCE if quick else 15
    swa_epochs = 10 if quick else 20

    data = load_forecast_data(
        patients_dir, history_steps=72, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    inputs = prepare_inputs(base_t, base_v, pk_t, pk_v, 72, horizons,
                            isf_t, isf_v)
    all_results = defaultdict(list)

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # --- Dual encoder: standard ---
        train_ld, val_ld, _, _ = make_loaders(inputs, 'dual')
        model_dual = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model_dual = train_model(model_dual, train_ld, val_ld, device,
                                 epochs=epochs, patience=patience)
        r, p_dual, tgt = evaluate_model(model_dual, val_ld, device, horizons)
        dt = time.time() - t0
        n_params = sum(p.numel() for p in model_dual.parameters())
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_standard... MAE={r['overall']:.1f} [{h_str}]  "
              f"({n_params:,} params, {dt:.0f}s)")
        all_results['dual_standard'].append(r)

        # --- Dual encoder: SWA ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        model_dual_swa = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        swa_model = train_model_swa(model_dual_swa, train_ld, val_ld, device,
                                     epochs=epochs, patience=patience,
                                     swa_epochs=swa_epochs)
        r_swa, p_dual_swa, _ = evaluate_model(swa_model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_swa.items() if k != 'overall')
        print(f"    dual_swa... MAE={r_swa['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_swa'].append(r_swa)

        # --- Shared ResNet: standard ---
        train_ls, val_ls, _, _ = make_loaders(inputs, 'shared')
        model_shared = ResNetCNNWithFuture(12, 4, n_horizons)
        torch.manual_seed(seed)
        np.random.seed(seed)
        t0 = time.time()
        model_shared = train_model(model_shared, train_ls, val_ls, device,
                                    epochs=epochs, patience=patience)
        r_sh, p_shared, _ = evaluate_model(model_shared, val_ls, device, horizons)
        dt = time.time() - t0
        n_params = sum(p.numel() for p in model_shared.parameters())
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_sh.items() if k != 'overall')
        print(f"    shared_standard... MAE={r_sh['overall']:.1f} [{h_str}]  "
              f"({n_params:,} params, {dt:.0f}s)")
        all_results['shared_standard'].append(r_sh)

        # --- Shared ResNet: SWA ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        model_shared_swa = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        swa_sh = train_model_swa(model_shared_swa, train_ls, val_ls, device,
                                  epochs=epochs, patience=patience,
                                  swa_epochs=swa_epochs)
        r_sh_swa, p_shared_swa, _ = evaluate_model(swa_sh, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_sh_swa.items() if k != 'overall')
        print(f"    shared_swa... MAE={r_sh_swa['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_swa'].append(r_sh_swa)

        # --- Ensembles ---
        # Standard ensemble
        r_ens = evaluate_ensemble([p_dual, p_shared], tgt, horizons)
        print(f"    ensemble_standard... MAE={r_ens['overall']:.1f}")
        all_results['ensemble_standard'].append(r_ens)

        # SWA ensemble
        r_swa_ens = evaluate_ensemble([p_dual_swa, p_shared_swa],
                                       tgt, horizons)
        print(f"    ensemble_swa... MAE={r_swa_ens['overall']:.1f}")
        all_results['ensemble_swa'].append(r_swa_ens)

        # Optimal SWA ensemble
        w = optimize_ensemble_weights([p_dual_swa, p_shared_swa],
                                       tgt, horizons)
        r_opt = evaluate_ensemble([p_dual_swa, p_shared_swa],
                                   tgt, horizons, weights=w)
        w_str = ', '.join(f'{k}=({w[0][i]:.2f},{w[1][i]:.2f})'
                         for i, k in enumerate(horizons.keys()))
        print(f"    ensemble_swa_optimal... MAE={r_opt['overall']:.1f}")
        print(f"      weights(dual,shared)=[{w_str}]")
        all_results['ensemble_swa_optimal'].append(r_opt)

    return _save_results('exp391_swa', all_results, horizons)


# ─── EXP-392: Data Augmentation ───

def run_exp_392(patients_dir, device, quick=False):
    """Test augmentation strategies on the shared ResNet model."""
    print("\nexp392_augmentation")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL
    epochs = QUICK_EPOCHS if quick else 60
    patience = QUICK_PATIENCE if quick else 15

    data = load_forecast_data(
        patients_dir, history_steps=72, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    inputs = prepare_inputs(base_t, base_v, pk_t, pk_v, 72, horizons,
                            isf_t, isf_v)
    all_results = defaultdict(list)

    aug_configs = {
        'no_aug': {'noise_std': 0.0, 'scale_range': 0.0, 'jitter_steps': 0},
        'noise_light': {'noise_std': 0.01, 'scale_range': 0.0, 'jitter_steps': 0},
        'noise_medium': {'noise_std': 0.02, 'scale_range': 0.0, 'jitter_steps': 0},
        'scale_only': {'noise_std': 0.0, 'scale_range': 0.05, 'jitter_steps': 0},
        'combined_light': {'noise_std': 0.01, 'scale_range': 0.03, 'jitter_steps': 1},
        'combined_medium': {'noise_std': 0.02, 'scale_range': 0.05, 'jitter_steps': 2},
    }

    for seed in seeds:
        print(f"\n  seed={seed}:")
        for aug_name, aug_cfg in aug_configs.items():
            torch.manual_seed(seed)
            np.random.seed(seed)

            _, val_ld, train_ds, _ = make_loaders(inputs, 'shared')

            # Wrap train dataset with augmentation
            if aug_name == 'no_aug':
                train_ld = DataLoader(train_ds, batch_size=128, shuffle=True)
            else:
                aug_ds = AugmentedDataset(train_ds, **aug_cfg)
                train_ld = DataLoader(aug_ds, batch_size=128, shuffle=True)

            model = ResNetCNNWithFuture(12, 4, n_horizons)
            t0 = time.time()
            model = train_model(model, train_ld, val_ld, device,
                                epochs=epochs, patience=patience)
            r, _, _ = evaluate_model(model, val_ld, device, horizons)
            dt = time.time() - t0
            n_params = sum(p.numel() for p in model.parameters())
            h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
            print(f"    {aug_name}... MAE={r['overall']:.1f} [{h_str}]  "
                  f"({n_params:,} params, {dt:.0f}s)")
            all_results[aug_name].append(r)

    return _save_results('exp392_augmentation', all_results, horizons)


# ─── EXP-393: Cosine Annealing ───

def run_exp_393(patients_dir, device, quick=False):
    """Compare LR schedules: ReduceOnPlateau vs CosineAnnealing."""
    print("\nexp393_cosine")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL
    epochs = QUICK_EPOCHS if quick else 60
    patience = QUICK_PATIENCE if quick else 15
    cosine_epochs = 50 if quick else 100

    data = load_forecast_data(
        patients_dir, history_steps=72, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    inputs = prepare_inputs(base_t, base_v, pk_t, pk_v, 72, horizons,
                            isf_t, isf_v)
    all_results = defaultdict(list)

    for seed in seeds:
        print(f"\n  seed={seed}:")

        # Shared ResNet with ReduceOnPlateau (baseline)
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld, _, _ = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device,
                            epochs=epochs, patience=patience)
        r, _, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    plateau_60ep... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['plateau_60ep'].append(r)

        # Cosine with warm restarts (T_0=20, T_mult=2)
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model_cosine(model, train_ld, val_ld, device,
                                    epochs=cosine_epochs, T_0=20, T_mult=2)
        r, _, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    cosine_100ep... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['cosine_100ep'].append(r)

        # Cosine with short restarts (T_0=10)
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model_cosine(model, train_ld, val_ld, device,
                                    epochs=cosine_epochs, T_0=10, T_mult=2)
        r, _, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    cosine_T10... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['cosine_T10'].append(r)

        # ReduceOnPlateau with 100 epochs (more training budget)
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device,
                            epochs=cosine_epochs, patience=20)
        r, _, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    plateau_100ep... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['plateau_100ep'].append(r)

    return _save_results('exp393_cosine', all_results, horizons)


# ─── EXP-394: Horizon-Weighted Ensemble Training ───

def run_exp_394(patients_dir, device, quick=False):
    """Train specialized models: one for short horizons, one for long."""
    print("\nexp394_horizon_weighted")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL
    epochs = QUICK_EPOCHS if quick else 60
    patience = QUICK_PATIENCE if quick else 15

    data = load_forecast_data(
        patients_dir, history_steps=72, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    inputs = prepare_inputs(base_t, base_v, pk_t, pk_v, 72, horizons,
                            isf_t, isf_v)
    all_results = defaultdict(list)

    # Define horizon weights for specialization
    if quick:
        # h30, h60, h120
        short_weights = [2.0, 1.0, 0.5]
        long_weights = [0.5, 1.0, 2.0]
        uniform_weights = [1.0, 1.0, 1.0]
    else:
        # h30, h60, h120, h180, h240, h360, h480, h720
        short_weights = [3.0, 2.0, 1.5, 1.0, 0.5, 0.3, 0.2, 0.1]
        long_weights = [0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        uniform_weights = [1.0] * 8

    for seed in seeds:
        print(f"\n  seed={seed}:")

        # --- Dual encoder: uniform (baseline) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld, _, _ = make_loaders(inputs, 'dual')
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device,
                            epochs=epochs, patience=patience)
        r, p_dual_uni, tgt = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_uniform... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_uniform'].append(r)

        # --- Dual encoder: short-weighted ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device,
                            epochs=epochs, patience=patience,
                            horizon_weights=short_weights)
        r, p_dual_short, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_short... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_short'].append(r)

        # --- Shared ResNet: uniform (baseline) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ls, val_ls, _, _ = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ls, val_ls, device,
                            epochs=epochs, patience=patience)
        r, p_sh_uni, _ = evaluate_model(model, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_uniform... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_uniform'].append(r)

        # --- Shared ResNet: long-weighted ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ls, val_ls, device,
                            epochs=epochs, patience=patience,
                            horizon_weights=long_weights)
        r, p_sh_long, _ = evaluate_model(model, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_long'].append(r)

        # --- Standard ensemble (both uniform) ---
        r_ens = evaluate_ensemble([p_dual_uni, p_sh_uni], tgt,
                                  horizons)
        print(f"    ensemble_uniform... MAE={r_ens['overall']:.1f}")
        all_results['ensemble_uniform'].append(r_ens)

        # --- Specialized ensemble: short-dual + long-shared ---
        r_spec = evaluate_ensemble([p_dual_short, p_sh_long], tgt,
                                    horizons)
        print(f"    ensemble_specialized... MAE={r_spec['overall']:.1f}")
        all_results['ensemble_specialized'].append(r_spec)

        # --- Optimal weights: specialized ensemble ---
        w = optimize_ensemble_weights([p_dual_short, p_sh_long],
                                       tgt, horizons)
        r_opt = evaluate_ensemble([p_dual_short, p_sh_long],
                                   tgt, horizons, weights=w)
        w_str = ', '.join(f'{k}=({w[0][i]:.2f},{w[1][i]:.2f})'
                         for i, k in enumerate(horizons.keys()))
        print(f"    ensemble_spec_optimal... MAE={r_opt['overall']:.1f}")
        print(f"      weights(dual,shared)=[{w_str}]")
        all_results['ensemble_spec_optimal'].append(r_opt)

    return _save_results('exp394_horizon_weighted', all_results, horizons)


# ─── EXP-395: Multi-Resolution Ensemble ───

def run_exp_395(patients_dir, device, quick=False):
    """Ensemble models with different history lengths (6h + 12h)."""
    print("\nexp395_multi_resolution")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL
    epochs = QUICK_EPOCHS if quick else 60
    patience = QUICK_PATIENCE if quick else 15

    all_results = defaultdict(list)

    # Load data at two resolutions
    data_6h = load_forecast_data(
        patients_dir, history_steps=72, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t_6, base_v_6, pk_t_6, pk_v_6, isf_t_6, isf_v_6, pp_6 = data_6h

    data_12h = load_forecast_data(
        patients_dir, history_steps=144, max_horizon=144,
        max_patients=QUICK_PATIENTS if quick else None,
        load_isf=True, stride=36)
    base_t_12, base_v_12, pk_t_12, pk_v_12, isf_t_12, isf_v_12, pp_12 = data_12h

    inputs_6h = prepare_inputs(base_t_6, base_v_6, pk_t_6, pk_v_6,
                                72, horizons, isf_t_6, isf_v_6)
    inputs_12h = prepare_inputs(base_t_12, base_v_12, pk_t_12, pk_v_12,
                                 144, horizons, isf_t_12, isf_v_12)

    for seed in seeds:
        print(f"\n  seed={seed}:")

        # --- 6h shared ResNet (reference) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_6, val_6, _, _ = make_loaders(inputs_6h, 'shared')
        model_6 = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model_6 = train_model(model_6, train_6, val_6, device,
                               epochs=epochs, patience=patience)
        r_6, p_6, tgt_6 = evaluate_model(model_6, val_6, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_6.items() if k != 'overall')
        print(f"    shared_6h... MAE={r_6['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_6h'].append(r_6)

        # --- 12h shared ResNet ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_12, val_12, _, _ = make_loaders(inputs_12h, 'shared')
        model_12 = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model_12 = train_model(model_12, train_12, val_12, device,
                                epochs=epochs, patience=patience)
        r_12, p_12, tgt_12 = evaluate_model(model_12, val_12, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_12.items() if k != 'overall')
        print(f"    shared_12h... MAE={r_12['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_12h'].append(r_12)

        # --- 6h dual encoder (reference) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        dtrain_6, dval_6, _, _ = make_loaders(inputs_6h, 'dual')
        model_d6 = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model_d6 = train_model(model_d6, dtrain_6, dval_6, device,
                                epochs=epochs, patience=patience)
        r_d6, p_d6, _ = evaluate_model(model_d6, dval_6, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_d6.items() if k != 'overall')
        print(f"    dual_6h... MAE={r_d6['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_6h'].append(r_d6)

        # --- 12h dual encoder ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        dtrain_12, dval_12, _, _ = make_loaders(inputs_12h, 'dual')
        model_d12 = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model_d12 = train_model(model_d12, dtrain_12, dval_12, device,
                                 epochs=epochs, patience=patience)
        r_d12, p_d12, _ = evaluate_model(model_d12, dval_12, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r_d12.items() if k != 'overall')
        print(f"    dual_12h... MAE={r_d12['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_12h'].append(r_d12)

        # --- Champion reference: 6h dual+shared ensemble ---
        r_champ = evaluate_ensemble([p_d6, p_6], tgt_6, horizons)
        print(f"    ensemble_6h_ref... MAE={r_champ['overall']:.1f}")
        all_results['ensemble_6h_ref'].append(r_champ)

        # Multi-resolution ensembles need aligned val sets.
        # Different history lengths produce different val windows.
        # We can only ensemble if val sets match.
        n_val_6 = len(tgt_6)
        n_val_12 = len(tgt_12)

        if n_val_6 != n_val_12:
            # Use the smaller set — windows overlap at the end (both chronological)
            n_min = min(n_val_6, n_val_12)
            # Take the LAST n_min from each (both are from end of patient data)
            p_6_aligned = p_6[-n_min:]
            p_12_aligned = p_12[-n_min:]
            p_d6_aligned = p_d6[-n_min:]
            p_d12_aligned = p_d12[-n_min:]
            tgt_aligned = tgt_6[-n_min:]
            print(f"    [alignment: 6h={n_val_6}, 12h={n_val_12}, using last {n_min}]")
        else:
            p_6_aligned = p_6
            p_12_aligned = p_12
            p_d6_aligned = p_d6
            p_d12_aligned = p_d12
            tgt_aligned = tgt_6

        # --- Multi-res shared ensemble (6h + 12h) ---
        r_mr_sh = evaluate_ensemble([p_6_aligned, p_12_aligned],
                                     tgt_aligned, horizons)
        print(f"    multires_shared... MAE={r_mr_sh['overall']:.1f}")
        all_results['multires_shared'].append(r_mr_sh)

        # --- Multi-res dual ensemble (6h + 12h) ---
        r_mr_d = evaluate_ensemble([p_d6_aligned, p_d12_aligned],
                                    tgt_aligned, horizons)
        print(f"    multires_dual... MAE={r_mr_d['overall']:.1f}")
        all_results['multires_dual'].append(r_mr_d)

        # --- 4-model multi-res ensemble ---
        r_4m = evaluate_ensemble(
            [p_d6_aligned, p_6_aligned, p_d12_aligned, p_12_aligned],
            tgt_aligned, horizons)
        print(f"    multires_4model... MAE={r_4m['overall']:.1f}")
        all_results['multires_4model'].append(r_4m)

    return _save_results('exp395_multi_resolution', all_results, horizons)


# ─── Utilities ───

def _save_results(name, all_results, horizons):
    """Save and print summary."""
    summary = {}
    for variant, results_list in sorted(all_results.items()):
        h_names = list(horizons.keys()) + ['overall']
        mean_r = {}
        for h in h_names:
            vals = [r[h] for r in results_list if h in r]
            if vals:
                mean_r[h] = float(np.mean(vals))
                mean_r[f'{h}_std'] = float(np.std(vals))
        summary[variant] = mean_r

    output = {
        'experiment': name,
        'horizons': horizons,
        'n_seeds': len(next(iter(all_results.values()))),
        'per_seed': {v: rs for v, rs in all_results.items()},
        'summary': summary,
    }

    out_dir = Path('externals/experiments')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{name}.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=float)
    print(f"Saved: {out_path}")

    print("\n─── Summary ───")
    for variant in sorted(summary.keys()):
        s = summary[variant]
        overall = s.get('overall', 0)
        overall_std = s.get('overall_std', 0)
        h_parts = []
        for h in horizons.keys():
            if h in s:
                h_parts.append(f"{h}={s[h]:.1f}±{s.get(f'{h}_std', 0):.1f}")
        h_str = ', '.join(h_parts)
        print(f"  {variant}: MAE={overall:.1f}±{overall_std:.1f} [{h_str}]")

    return output


# ─── Main ───

EXPERIMENTS = {
    '391': run_exp_391,
    '392': run_exp_392,
    '393': run_exp_393,
    '394': run_exp_394,
    '395': run_exp_395,
}


def main():
    parser = argparse.ArgumentParser(
        description='PK Forecast v10: Training Improvements')
    parser.add_argument('--experiment', default='all',
                        help='Experiment number (391-395) or "all"')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--patients-dir',
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"Device: {device}")
    if 'cuda' in str(device):
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    if args.experiment == 'all':
        for exp_id, fn in sorted(EXPERIMENTS.items()):
            fn(args.patients_dir, device, args.quick)
    elif args.experiment in EXPERIMENTS:
        EXPERIMENTS[args.experiment](args.patients_dir, device, args.quick)
    else:
        print(f"Unknown experiment: {args.experiment}")
        print(f"Available: {list(EXPERIMENTS.keys())}")
        sys.exit(1)


if __name__ == '__main__':
    main()
