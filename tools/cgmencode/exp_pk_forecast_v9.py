#!/usr/bin/env python3
"""EXP-386 through EXP-390: Advanced Ensemble & Distillation

Building on EXP-382's breakthrough (ensemble MAE=34.4 vs 35.8 champion):

EXP-386 — 3-Model Ensemble
  Add a glucose-only model as extreme diversity member.
  Dual encoder sees glucose+PK separately, shared ResNet sees all 8ch together,
  glucose-only sees pure glucose signal. Maximum error decorrelation.
  Hypothesis: 3-model ensemble beats 2-model by 0.3-0.5 mg/dL.

EXP-387 — Per-Patient Ensemble Weights
  Instead of global α, optimize weights per patient on their validation data.
  Different patients have different insulin dynamics (j=no Loop, h=sparse CGM).
  Hypothesis: Per-patient α improves overall by 0.2-0.5, especially on outliers.

EXP-388 — Knowledge Distillation
  Train single model to match ensemble soft targets (mean of dual+shared preds).
  If successful: simpler deployment (1 model instead of 2).
  Hypothesis: Distilled model recovers 70-80% of ensemble improvement.

EXP-389 — Residual Boosting
  Train second model on residuals (errors) of dual encoder.
  Then: final_pred = dual_pred + residual_model_pred.
  Hypothesis: Residual model learns systematic biases, -0.3-0.5 improvement.

EXP-390 — State-Conditional Ensemble Weights
  α depends on current glucose state (IOB level, glucose volatility, trend).
  When IOB is high → weight shared model more (insulin dynamics active).
  When glucose is flat → weight dual more (pure trend continuation).
  Hypothesis: Adaptive α beats fixed α by 0.2-0.4.

Usage:
    python tools/cgmencode/exp_pk_forecast_v9.py --experiment 386 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v9.py --experiment all --device cuda
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


# ─── Data Loading (shared with v8) ───

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
    """Load multi-patient data. Returns per-patient splits for per-patient experiments."""
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
    """Standard ResNet + future PK (shared baseline)."""
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
    """Separate glucose vs PK encoders."""
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
            ResBlock1d(32, 32, dropout=dropout),
            ResBlock1d(32, 32, dropout=dropout),
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


class GlucoseOnlyCNN(nn.Module):
    """Pure glucose-only model: just glucose + future PK.
    
    Maximally different from both dual encoder (which has PK history)
    and shared ResNet (which has all 8 channels). This model sees ONLY
    glucose history + future PK projections.
    """
    def __init__(self, pk_future_channels=4, n_horizons=8, dropout=0.1):
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

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(48 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_glucose, x_future):
        g = x_glucose.permute(0, 2, 1)
        g = self.glucose_stem(g)
        g = self.glucose_blocks(g)
        g_feat = self.glucose_pool(g).squeeze(-1)
        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)
        return self.head(torch.cat([g_feat, f_feat], dim=1))


class DistilledModel(nn.Module):
    """Single model trained on ensemble soft targets.
    
    Architecture: shared ResNet (same as 240K model) but trained to match
    the average prediction of dual + shared models.
    """
    def __init__(self, hist_channels=8, pk_channels=4, n_horizons=8, dropout=0.1):
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


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3):
    """Standard MSE training."""
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

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
                val_losses.append(F.mse_loss(preds, targets).item())

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


def train_distillation(student, teacher_preds_train, teacher_preds_val,
                       train_loader, val_loader, device, epochs=60,
                       patience=15, lr=1e-3, alpha=0.7):
    """Train student to match teacher (soft targets) + real targets.
    
    Loss = α * MSE(student, teacher) + (1-α) * MSE(student, real)
    
    Creates a NEW DataLoader that includes soft targets as an extra tensor,
    avoiding shuffle-order misalignment.
    """
    student.to(device)
    optimizer = torch.optim.Adam(student.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    # Build new datasets that include soft targets
    train_ds = train_loader.dataset
    train_tensors = list(train_ds.tensors)
    soft_train = torch.from_numpy(teacher_preds_train).float()
    # Append soft targets: inputs... + real_targets + soft_targets
    distill_train_ds = TensorDataset(*train_tensors, soft_train)
    distill_train_loader = DataLoader(distill_train_ds, batch_size=128,
                                      shuffle=True)

    best_val_loss = float('inf')
    best_state = None
    wait = 0

    for epoch in range(epochs):
        student.train()
        train_losses = []
        for batch in distill_train_loader:
            # batch = [input1, input2, ..., real_targets, soft_targets]
            inputs = [b.to(device) for b in batch[:-2]]
            real_targets = batch[-2].to(device)
            soft_targets = batch[-1].to(device)

            optimizer.zero_grad()
            preds = student(*inputs)
            loss_soft = F.mse_loss(preds, soft_targets)
            loss_hard = F.mse_loss(preds, real_targets)
            loss = alpha * loss_soft + (1 - alpha) * loss_hard
            loss.backward()
            nn.utils.clip_grad_norm_(student.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())

        student.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                real_targets = batch[-1].to(device)
                preds = student(*inputs)
                val_losses.append(F.mse_loss(preds, real_targets).item())

        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone()
                          for k, v in student.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        student.load_state_dict(best_state)
    return student


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
    return result, preds, targets


def get_train_predictions(model, train_dataset_or_loader, device):
    """Get model predictions on training data IN ORIGINAL ORDER.
    
    IMPORTANT: If given a DataLoader with shuffle=True, creates a new
    non-shuffled loader to ensure predictions align with original data order.
    Accepts either a DataLoader or a TensorDataset.
    """
    model.eval()
    if isinstance(train_dataset_or_loader, DataLoader):
        # Create non-shuffled loader to preserve order
        loader = DataLoader(train_dataset_or_loader.dataset,
                            batch_size=256, shuffle=False)
    else:
        loader = DataLoader(train_dataset_or_loader, batch_size=256,
                            shuffle=False)
    all_preds = []
    with torch.no_grad():
        for batch in loader:
            inputs = [b.to(device) for b in batch[:-1]]
            preds = model(*inputs)
            all_preds.append(preds.cpu().numpy())
    return np.concatenate(all_preds)


def evaluate_ensemble(preds_list, targets, horizons, scale=GLUCOSE_SCALE,
                      weights=None):
    """Evaluate ensemble of predictions."""
    if weights is None:
        weights = np.ones(len(preds_list)) / len(preds_list)
    else:
        weights = np.array(weights) / np.sum(weights)
    ensemble_preds = sum(w * p for w, p in zip(weights, preds_list))

    per_horizon = {}
    for i, name in enumerate(horizons.keys()):
        mae = float(np.mean(np.abs(ensemble_preds[:, i] - targets[:, i])) * scale)
        per_horizon[name] = mae

    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }


def optimize_ensemble_weights_3(preds_list, targets, horizons, scale=GLUCOSE_SCALE):
    """Find per-horizon optimal weights for 3-model ensemble via grid search.
    
    For each horizon, find (α, β, γ) that minimizes MAE where
    pred = α*pred_A + β*pred_B + γ*pred_C, α+β+γ=1.
    """
    assert len(preds_list) == 3, "Requires 3-model ensemble"
    p_a, p_b, p_c = preds_list

    optimal_weights = {}
    for i, name in enumerate(horizons.keys()):
        best_weights, best_mae = (1/3, 1/3, 1/3), float('inf')
        # Grid search with step 0.05, constrained α+β+γ=1
        for a in np.arange(0.0, 1.01, 0.05):
            for b in np.arange(0.0, 1.01 - a, 0.05):
                c = 1.0 - a - b
                if c < -0.01:
                    continue
                c = max(0, c)
                blend = a * p_a[:, i] + b * p_b[:, i] + c * p_c[:, i]
                mae = float(np.mean(np.abs(blend - targets[:, i])) * scale)
                if mae < best_mae:
                    best_mae = mae
                    best_weights = (float(a), float(b), float(c))
        optimal_weights[name] = best_weights

    return optimal_weights


def optimize_ensemble_weights_2(preds_list, targets, horizons, scale=GLUCOSE_SCALE):
    """Find per-horizon optimal α for 2-model ensemble."""
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


# ─── Feature Preparation ───

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
        glucose_t = glucose_t * isf_factor_t
        glucose_v = glucose_v * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(glucose_t, 0, 10, out=glucose_t)
        np.clip(glucose_v, 0, 10, out=glucose_v)

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


def prepare_glucose_only_features(base_train, base_val, pk_train, pk_val,
                                  history_steps, horizons,
                                  isf_train=None, isf_val=None):
    """Prepare glucose-only features: just glucose history + future PK."""
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    glucose_t = base_train[:, :history_steps, 0:1].copy().astype(np.float32)
    glucose_v = base_val[:, :history_steps, 0:1].copy().astype(np.float32)

    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        glucose_t = glucose_t * isf_factor_t
        glucose_v = glucose_v * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(glucose_t, 0, 10, out=glucose_t)
        np.clip(glucose_v, 0, 10, out=glucose_v)

    future_t = np.stack([
        pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    future_v = np.stack([
        pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    return (glucose_t, glucose_v, future_t, future_v,
            targets_train, targets_val)


# ─── Data Loaders ───

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


def _make_glucose_only_loaders(g_t, g_v, f_t, f_v, t_t, t_v):
    train_ds = TensorDataset(
        torch.from_numpy(g_t), torch.from_numpy(f_t),
        torch.from_numpy(t_t.astype(np.float32)))
    val_ds = TensorDataset(
        torch.from_numpy(g_v), torch.from_numpy(f_v),
        torch.from_numpy(t_v.astype(np.float32)))
    return (DataLoader(train_ds, batch_size=128, shuffle=True),
            DataLoader(val_ds, batch_size=256))


# ─── Helpers ───

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
            horizon_means[h] = {'mean': float(np.mean(vals)),
                                'std': float(np.std(vals))}
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
# EXP-386: 3-Model Ensemble (Dual + Shared + Glucose-Only)
# ═══════════════════════════════════════════════════════════

def run_exp_386(args):
    """3-model ensemble: maximize prediction diversity."""
    print("=" * 60)
    print("exp386_3model_ensemble")
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

        # Prepare features for all 3 architectures
        (g_t, g_v, pk_h_t, pk_h_v, f_t, f_v,
         tgt_t, tgt_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        (sh_t, sh_v, sf_t, sf_v,
         stgt_t, stgt_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        (go_t, go_v, gof_t, gof_v,
         gotgt_t, gotgt_v) = prepare_glucose_only_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, tgt_t, tgt_v)
        shared_tl, shared_vl = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, stgt_t, stgt_v)
        go_tl, go_vl = _make_glucose_only_loaders(
            go_t, go_v, gof_t, gof_v, gotgt_t, gotgt_v)

        # Train 3 models
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_isf', dual_model, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"dual_isf_s{seed}"] = res_dual

        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, targets_shared = _run_variant(
            'shared_isf', shared_model, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"shared_isf_s{seed}"] = res_shared

        torch.manual_seed(seed)
        go_model = GlucoseOnlyCNN(
            pk_future_channels=4, n_horizons=n_horizons)
        res_go, go_model, preds_go, targets_go = _run_variant(
            'glucose_only', go_model, go_tl, go_vl,
            device, horizons, train_kw)
        n_go_params = sum(p.numel() for p in go_model.parameters())
        results[f"glucose_only_s{seed}"] = res_go

        # 2-model ensemble (reference: same as EXP-382)
        ens_2 = evaluate_ensemble([preds_dual, preds_shared], targets, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_2['mae_per_horizon'].items())
        print(f"    ensemble_2model... MAE={ens_2['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_2model_s{seed}"] = ens_2

        # 3-model ensemble: equal weights
        ens_3_equal = evaluate_ensemble(
            [preds_dual, preds_shared, preds_go], targets, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_3_equal['mae_per_horizon'].items())
        print(f"    ensemble_3model_equal... MAE={ens_3_equal['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_3model_equal_s{seed}"] = ens_3_equal

        # 3-model ensemble: optimal weights
        opt3 = optimize_ensemble_weights_3(
            [preds_dual, preds_shared, preds_go], targets, horizons)
        # Apply optimal weights
        ens_3_opt_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            a, b, c = opt3[name]
            ens_3_opt_preds[:, i] = (a * preds_dual[:, i] +
                                     b * preds_shared[:, i] +
                                     c * preds_go[:, i])
        ens_3_opt_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_3_opt_ph[name] = float(
                np.mean(np.abs(ens_3_opt_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_3_opt = {
            'mae_overall': float(np.mean(list(ens_3_opt_ph.values()))),
            'mae_per_horizon': ens_3_opt_ph,
            'optimal_weights': opt3,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_3_opt_ph.items())
        print(f"    ensemble_3model_optimal... MAE={ens_3_opt['mae_overall']:.1f} [{h_str}]")
        wt_strs = []
        for h, (a, b, c) in opt3.items():
            wt_strs.append(f"{h}=({a:.2f},{b:.2f},{c:.2f})")
        print(f"      weights(dual,shared,gluc)=[{', '.join(wt_strs)}]")
        results[f"ensemble_3model_optimal_s{seed}"] = ens_3_opt

    _save_results('exp386_3model_ensemble',
                  '3-model ensemble: dual + shared + glucose-only',
                  results, horizons,
                  'externals/experiments/exp386_3model_ensemble.json')


# ═══════════════════════════════════════════════════════════
# EXP-387: Per-Patient Ensemble Weights
# ═══════════════════════════════════════════════════════════

def run_exp_387(args):
    """Per-patient optimized ensemble weights vs global weights."""
    print("=" * 60)
    print("exp387_per_patient_weights")
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

        # Train models
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_isf', dual_model, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"dual_isf_s{seed}"] = res_dual

        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, _ = _run_variant(
            'shared_isf', shared_model, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"shared_isf_s{seed}"] = res_shared

        # Global ensemble (reference)
        global_opt = optimize_ensemble_weights_2(
            [preds_dual, preds_shared], targets, horizons)
        ens_global_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            w = global_opt[name]
            ens_global_preds[:, i] = w * preds_dual[:, i] + (1 - w) * preds_shared[:, i]
        ens_global_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_global_ph[name] = float(
                np.mean(np.abs(ens_global_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_global = {
            'mae_overall': float(np.mean(list(ens_global_ph.values()))),
            'mae_per_horizon': ens_global_ph,
            'global_weights': global_opt,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_global_ph.items())
        print(f"    ensemble_global... MAE={ens_global['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_global_s{seed}"] = ens_global

        # Per-patient ensemble
        ens_pp_preds = np.zeros_like(preds_dual)
        patient_weights = {}
        for pi, pinfo in enumerate(per_patient):
            v_start, v_end = pinfo['val_idx']
            p_dual = preds_dual[v_start:v_end]
            p_shared = preds_shared[v_start:v_end]
            p_targets = targets[v_start:v_end]

            if len(p_dual) < 5:
                # Too few samples, use global weights
                for i, name in enumerate(horizons.keys()):
                    w = global_opt[name]
                    ens_pp_preds[v_start:v_end, i] = (
                        w * p_dual[:, i] + (1 - w) * p_shared[:, i])
                patient_weights[pinfo['name']] = global_opt
                continue

            # Optimize per-patient weights
            pp_opt = optimize_ensemble_weights_2(
                [p_dual, p_shared], p_targets, horizons)
            patient_weights[pinfo['name']] = pp_opt

            for i, name in enumerate(horizons.keys()):
                w = pp_opt[name]
                ens_pp_preds[v_start:v_end, i] = (
                    w * p_dual[:, i] + (1 - w) * p_shared[:, i])

        ens_pp_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_pp_ph[name] = float(
                np.mean(np.abs(ens_pp_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_pp = {
            'mae_overall': float(np.mean(list(ens_pp_ph.values()))),
            'mae_per_horizon': ens_pp_ph,
            'patient_weights': patient_weights,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_pp_ph.items())
        print(f"    ensemble_per_patient... MAE={ens_pp['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_per_patient_s{seed}"] = ens_pp

        # Print per-patient weight comparison
        print("      Per-patient α_dual at h120:")
        for pname, pw in patient_weights.items():
            gw = global_opt.get('h120', 0.5)
            ppw = pw.get('h120', 0.5)
            delta = ppw - gw
            print(f"        {pname}: {ppw:.2f} (global={gw:.2f}, Δ={delta:+.2f})")

    _save_results('exp387_per_patient_weights',
                  'Per-patient vs global ensemble weights',
                  results, horizons,
                  'externals/experiments/exp387_per_patient.json')


# ═══════════════════════════════════════════════════════════
# EXP-388: Knowledge Distillation
# ═══════════════════════════════════════════════════════════

def run_exp_388(args):
    """Train single model to match ensemble predictions."""
    print("=" * 60)
    print("exp388_distillation")
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

        # Prepare features for teachers
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

        # Train teacher models
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_isf', dual_model, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"dual_isf_s{seed}"] = res_dual

        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, _ = _run_variant(
            'shared_isf', shared_model, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"shared_isf_s{seed}"] = res_shared

        # Ensemble reference
        ens_ref = evaluate_ensemble([preds_dual, preds_shared], targets, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_ref['mae_per_horizon'].items())
        print(f"    ensemble_ref... MAE={ens_ref['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_ref_s{seed}"] = ens_ref

        # Generate teacher predictions on TRAINING set
        dual_train_preds = get_train_predictions(dual_model, dual_tl, device)
        shared_train_preds = get_train_predictions(shared_model, shared_tl, device)
        teacher_train = (dual_train_preds + shared_train_preds) / 2
        teacher_val = (preds_dual + preds_shared) / 2

        # Student: shared ResNet trained with distillation
        for alpha in [0.5, 0.7, 0.9]:
            torch.manual_seed(seed)
            student = DistilledModel(
                hist_channels=8, pk_channels=4, n_horizons=n_horizons)
            t0 = time.time()
            n_params = sum(p.numel() for p in student.parameters())
            student = train_distillation(
                student, teacher_train, teacher_val,
                shared_tl, shared_vl, device,
                alpha=alpha, **train_kw)
            res_student, _, _ = evaluate_model(
                student, shared_vl, device, horizons)
            elapsed = time.time() - t0
            h_str = ', '.join(f"{k}={v:.1f}"
                              for k, v in res_student['mae_per_horizon'].items())
            print(f"    distill_a{alpha}... MAE={res_student['mae_overall']:.1f} "
                  f"[{h_str}]  ({n_params:,} params, {elapsed:.0f}s)")
            res_student['n_params'] = n_params
            res_student['alpha'] = alpha
            results[f"distill_a{alpha}_s{seed}"] = res_student

        # Baseline: same architecture, standard MSE training (no distillation)
        torch.manual_seed(seed)
        baseline = DistilledModel(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_base, _, _, _ = _run_variant(
            'baseline_shared', baseline, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"baseline_shared_s{seed}"] = res_base

    _save_results('exp388_distillation',
                  'Knowledge distillation: ensemble → single model',
                  results, horizons,
                  'externals/experiments/exp388_distillation.json')


# ═══════════════════════════════════════════════════════════
# EXP-389: Residual Boosting
# ═══════════════════════════════════════════════════════════

def run_exp_389(args):
    """Train residual model on errors of primary model."""
    print("=" * 60)
    print("exp389_residual_boosting")
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

        # Prepare features
        (sh_t, sh_v, sf_t, sf_v,
         stgt_t, stgt_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, history_steps, horizons,
            isf_train=isf_t, isf_val=isf_v)

        shared_tl, shared_vl = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, stgt_t, stgt_v)

        # Train primary model (shared ResNet)
        torch.manual_seed(seed)
        primary = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_primary, primary, preds_primary, targets = _run_variant(
            'primary_shared', primary, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"primary_shared_s{seed}"] = res_primary

        # Compute residuals on training and validation sets
        primary_train_preds = get_train_predictions(primary, shared_tl, device)
        # Residuals = actual - predicted (what the model missed)
        residuals_train = stgt_t - primary_train_preds
        residuals_val = stgt_v - preds_primary

        # Build residual loaders (same inputs, residual targets)
        res_tl_ds = TensorDataset(
            torch.from_numpy(sh_t), torch.from_numpy(sf_t),
            torch.from_numpy(residuals_train.astype(np.float32)))
        res_vl_ds = TensorDataset(
            torch.from_numpy(sh_v), torch.from_numpy(sf_v),
            torch.from_numpy(residuals_val.astype(np.float32)))
        res_tl = DataLoader(res_tl_ds, batch_size=128, shuffle=True)
        res_vl = DataLoader(res_vl_ds, batch_size=256)

        # Train residual model (smaller — residuals should be easier)
        for scale_factor in [0.5, 1.0]:
            variant_name = f"boost_{scale_factor}"
            torch.manual_seed(seed + 1)
            if scale_factor < 1.0:
                # Smaller residual model
                residual_model = ResNetCNNWithFuture(
                    hist_channels=8, pk_channels=4, n_horizons=n_horizons,
                    dropout=0.2)
            else:
                residual_model = ResNetCNNWithFuture(
                    hist_channels=8, pk_channels=4, n_horizons=n_horizons)

            t0 = time.time()
            n_params = sum(p.numel() for p in residual_model.parameters())
            residual_model = train_model(
                residual_model, res_tl, res_vl, device, **train_kw)

            # Boosted prediction = primary + scale * residual
            residual_model.eval()
            all_res_preds = []
            with torch.no_grad():
                for batch in res_vl:
                    inputs = [b.to(device) for b in batch[:-1]]
                    rpreds = residual_model(*inputs)
                    all_res_preds.append(rpreds.cpu().numpy())
            res_preds = np.concatenate(all_res_preds)

            boosted_preds = preds_primary + scale_factor * res_preds

            per_horizon = {}
            for i, name in enumerate(horizons.keys()):
                mae = float(np.mean(np.abs(
                    boosted_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
                per_horizon[name] = mae
            boosted_res = {
                'mae_overall': float(np.mean(list(per_horizon.values()))),
                'mae_per_horizon': per_horizon,
                'n_params': n_params,
                'scale_factor': scale_factor,
            }
            elapsed = time.time() - t0
            h_str = ', '.join(f"{k}={v:.1f}" for k, v in per_horizon.items())
            print(f"    {variant_name}... MAE={boosted_res['mae_overall']:.1f} "
                  f"[{h_str}]  ({n_params:,} params, {elapsed:.0f}s)")
            results[f"{variant_name}_s{seed}"] = boosted_res

    _save_results('exp389_residual_boosting',
                  'Residual boosting: primary + residual correction',
                  results, horizons,
                  'externals/experiments/exp389_boosting.json')


# ═══════════════════════════════════════════════════════════
# EXP-390: State-Conditional Ensemble Weights
# ═══════════════════════════════════════════════════════════

def run_exp_390(args):
    """Ensemble weights conditioned on glucose state features."""
    print("=" * 60)
    print("exp390_conditional_ensemble")
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

        # Train models
        torch.manual_seed(seed)
        dual_model = DualEncoderWithFuture(
            pk_hist_channels=4, pk_future_channels=4, n_horizons=n_horizons)
        res_dual, dual_model, preds_dual, targets = _run_variant(
            'dual_isf', dual_model, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"dual_isf_s{seed}"] = res_dual

        torch.manual_seed(seed)
        shared_model = ResNetCNNWithFuture(
            hist_channels=8, pk_channels=4, n_horizons=n_horizons)
        res_shared, shared_model, preds_shared, _ = _run_variant(
            'shared_isf', shared_model, shared_tl, shared_vl,
            device, horizons, train_kw)
        results[f"shared_isf_s{seed}"] = res_shared

        # Optimal global ensemble (reference)
        global_opt = optimize_ensemble_weights_2(
            [preds_dual, preds_shared], targets, horizons)
        ens_global = evaluate_ensemble(
            [preds_dual, preds_shared], targets, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_global['mae_per_horizon'].items())
        print(f"    ensemble_equal... MAE={ens_global['mae_overall']:.1f} [{h_str}]")
        results[f"ensemble_equal_s{seed}"] = ens_global

        # Extract state features from validation data
        # IOB: channel 1 of base grid, last value in history
        iob_val = base_v[:, history_steps - 1, 1]  # IOB at prediction time
        # Glucose trend: difference over last 6 steps (30 min)
        gluc_trend = (base_v[:, history_steps - 1, 0] -
                      base_v[:, history_steps - 7, 0]) * GLUCOSE_SCALE
        # Glucose volatility: std of last 12 steps (1h)
        gluc_vol = np.std(base_v[:, history_steps - 12:history_steps, 0],
                          axis=1) * GLUCOSE_SCALE
        # Current glucose level
        gluc_level = base_v[:, history_steps - 1, 0] * GLUCOSE_SCALE

        # Strategy 1: IOB-conditioned (high IOB → more shared weight)
        iob_median = np.median(iob_val)
        high_iob = iob_val > iob_median
        ens_iob_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            g_w = global_opt[name]
            # High IOB: shift 0.15 toward shared (less dual weight)
            w_high = max(0, g_w - 0.15)
            w_low = min(1, g_w + 0.15)
            ens_iob_preds[high_iob, i] = (
                w_high * preds_dual[high_iob, i] +
                (1 - w_high) * preds_shared[high_iob, i])
            ens_iob_preds[~high_iob, i] = (
                w_low * preds_dual[~high_iob, i] +
                (1 - w_low) * preds_shared[~high_iob, i])
        ens_iob_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_iob_ph[name] = float(
                np.mean(np.abs(ens_iob_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_iob = {
            'mae_overall': float(np.mean(list(ens_iob_ph.values()))),
            'mae_per_horizon': ens_iob_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_iob_ph.items())
        print(f"    cond_iob... MAE={ens_iob['mae_overall']:.1f} [{h_str}]")
        results[f"cond_iob_s{seed}"] = ens_iob

        # Strategy 2: Trend-conditioned (steep trend → more dual weight)
        steep_trend = np.abs(gluc_trend) > np.median(np.abs(gluc_trend))
        ens_trend_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            g_w = global_opt[name]
            w_steep = min(1, g_w + 0.15)  # More dual for steep trends
            w_flat = max(0, g_w - 0.15)   # More shared for flat
            ens_trend_preds[steep_trend, i] = (
                w_steep * preds_dual[steep_trend, i] +
                (1 - w_steep) * preds_shared[steep_trend, i])
            ens_trend_preds[~steep_trend, i] = (
                w_flat * preds_dual[~steep_trend, i] +
                (1 - w_flat) * preds_shared[~steep_trend, i])
        ens_trend_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_trend_ph[name] = float(
                np.mean(np.abs(ens_trend_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_trend = {
            'mae_overall': float(np.mean(list(ens_trend_ph.values()))),
            'mae_per_horizon': ens_trend_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_trend_ph.items())
        print(f"    cond_trend... MAE={ens_trend['mae_overall']:.1f} [{h_str}]")
        results[f"cond_trend_s{seed}"] = ens_trend

        # Strategy 3: Volatility-conditioned (high vol → more shared)
        high_vol = gluc_vol > np.median(gluc_vol)
        ens_vol_preds = np.zeros_like(preds_dual)
        for i, name in enumerate(horizons.keys()):
            g_w = global_opt[name]
            w_high = max(0, g_w - 0.15)  # More shared for volatile
            w_low = min(1, g_w + 0.15)   # More dual for stable
            ens_vol_preds[high_vol, i] = (
                w_high * preds_dual[high_vol, i] +
                (1 - w_high) * preds_shared[high_vol, i])
            ens_vol_preds[~high_vol, i] = (
                w_low * preds_dual[~high_vol, i] +
                (1 - w_low) * preds_shared[~high_vol, i])
        ens_vol_ph = {}
        for i, name in enumerate(horizons.keys()):
            ens_vol_ph[name] = float(
                np.mean(np.abs(ens_vol_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        ens_vol = {
            'mae_overall': float(np.mean(list(ens_vol_ph.values()))),
            'mae_per_horizon': ens_vol_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ens_vol_ph.items())
        print(f"    cond_volatility... MAE={ens_vol['mae_overall']:.1f} [{h_str}]")
        results[f"cond_volatility_s{seed}"] = ens_vol

        # Strategy 4: Oracle conditional (use whichever model has lower error)
        # This gives an UPPER BOUND on what any conditional strategy can achieve
        dual_errors = np.abs(preds_dual - targets) * GLUCOSE_SCALE
        shared_errors = np.abs(preds_shared - targets) * GLUCOSE_SCALE
        oracle_preds = np.where(dual_errors < shared_errors,
                                preds_dual, preds_shared)
        oracle_ph = {}
        for i, name in enumerate(horizons.keys()):
            oracle_ph[name] = float(
                np.mean(np.abs(oracle_preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        oracle_res = {
            'mae_overall': float(np.mean(list(oracle_ph.values()))),
            'mae_per_horizon': oracle_ph,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in oracle_ph.items())
        print(f"    oracle_conditional... MAE={oracle_res['mae_overall']:.1f} [{h_str}]"
              "  (upper bound)")
        results[f"oracle_conditional_s{seed}"] = oracle_res

    _save_results('exp390_conditional_ensemble',
                  'State-conditional ensemble weights',
                  results, horizons,
                  'externals/experiments/exp390_conditional.json')


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

EXPERIMENTS = {
    386: run_exp_386,
    387: run_exp_387,
    388: run_exp_388,
    389: run_exp_389,
    390: run_exp_390,
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-386-390: Advanced Ensemble & Distillation')
    parser.add_argument('--experiment', type=str, default='all',
                        help='Experiment number or "all"')
    parser.add_argument('--device', type=str, default='cuda',
                        help='Device (cuda or cpu)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients',
                        help='Path to patient data directory')
    args = parser.parse_args()

    if args.experiment == 'all':
        for exp_num, fn in sorted(EXPERIMENTS.items()):
            fn(args)
    else:
        exp_num = int(args.experiment)
        if exp_num in EXPERIMENTS:
            EXPERIMENTS[exp_num](args)
        else:
            print(f"Unknown experiment: {exp_num}")
            print(f"Available: {sorted(EXPERIMENTS.keys())}")
            sys.exit(1)


if __name__ == '__main__':
    main()
