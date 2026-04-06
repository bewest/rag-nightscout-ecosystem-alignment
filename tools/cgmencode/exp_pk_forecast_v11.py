#!/usr/bin/env python3
"""EXP-396 through EXP-398: Combined Best Techniques

V10 findings to combine:
  - EXP-393: plateau_100ep -1.6 on shared ResNet (longer training)
  - EXP-391: SWA -0.5 on dual encoder
  - EXP-394: short-weighting helps dual -0.8
  - EXP-382: 2-model ensemble still champion (34.4±0.1)

EXP-396 — Combined Training Improvements
  Train both models with 100 epochs + patience 20 (not 60+15).
  Apply SWA to dual encoder (not shared — hurt in v10).
  Ensemble the improved models. This stacks two orthogonal improvements.
  Hypothesis: -1.0 to -2.0 vs current champion.

EXP-397 — SWA + Longer Training + Short-Weight Dual
  Same as 396 but also apply short-horizon weighting to dual encoder.
  Dual already excels at h30-h120; focusing its loss there should help.
  Hypothesis: dual_short + shared_long_training → best ensemble yet.

EXP-398 — Sweep Training Duration
  How much does additional training help? Test 60/80/100/120/150 epochs
  on shared ResNet to find the sweet spot before diminishing returns.

Usage:
    python tools/cgmencode/exp_pk_forecast_v11.py --experiment 396 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v11.py --experiment all --device cuda
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
FUTURE_PK_INDICES = [1, 2, 3, 6]


# ─── Data Loading (shared) ───

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
            'name': pdir.name, 'n_windows': n,
            'n_train': len(bt), 'n_val': len(bv), 'isf': isf,
        }

        all_base_train.extend(bt)
        all_base_val.extend(bv)
        all_pk_train.extend(pt)
        all_pk_val.extend(pv)

        if isf is not None:
            all_isf_train.extend([isf] * len(bt))
            all_isf_val.extend([isf] * len(bv))

        print(f"  {pdir.name}: {n} windows ({len(bt)} train, {len(bv)} val)"
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


# ─── Models ───

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
            nn.Conv1d(hist_channels, 64, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(64))
        self.hist_blocks = nn.Sequential(
            ResBlock1d(64, 128, dropout=dropout),
            ResBlock1d(128, 128, dropout=dropout),
            ResBlock1d(128, 64, dropout=dropout))
        self.hist_pool = nn.AdaptiveAvgPool1d(1)
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1))
        self.head = nn.Sequential(
            nn.Linear(64 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons))

    def forward(self, x_hist, x_future):
        h = self.hist_stem(x_hist.permute(0, 2, 1))
        h = self.hist_pool(self.hist_blocks(h)).squeeze(-1)
        f = self.future_conv(x_future.permute(0, 2, 1)).squeeze(-1)
        return self.head(torch.cat([h, f], dim=1))


class DualEncoderWithFuture(nn.Module):
    def __init__(self, pk_hist_channels, pk_future_channels,
                 n_horizons=8, dropout=0.1):
        super().__init__()
        self.glucose_stem = nn.Sequential(
            nn.Conv1d(1, 48, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(48))
        self.glucose_blocks = nn.Sequential(
            ResBlock1d(48, 96, dropout=dropout),
            ResBlock1d(96, 96, dropout=dropout),
            ResBlock1d(96, 48, dropout=dropout))
        self.glucose_pool = nn.AdaptiveAvgPool1d(1)
        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32))
        self.pk_blocks = nn.Sequential(
            ResBlock1d(32, 64, dropout=dropout),
            ResBlock1d(64, 32, dropout=dropout))
        self.pk_pool = nn.AdaptiveAvgPool1d(1)
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1))
        self.head = nn.Sequential(
            nn.Linear(48 + 32 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons))

    def forward(self, x_glucose, x_pk_hist, x_future):
        g = self.glucose_pool(self.glucose_blocks(
            self.glucose_stem(x_glucose.permute(0, 2, 1)))).squeeze(-1)
        p = self.pk_pool(self.pk_blocks(
            self.pk_stem(x_pk_hist.permute(0, 2, 1)))).squeeze(-1)
        f = self.future_conv(x_future.permute(0, 2, 1)).squeeze(-1)
        return self.head(torch.cat([g, p, f], dim=1))


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, horizon_weights=None):
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
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            optimizer.zero_grad()
            preds = model(*inputs)
            if hw is not None:
                loss = torch.mean((preds - targets) ** 2 * hw.unsqueeze(0))
            else:
                loss = F.mse_loss(preds, targets)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

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
                    patience=15, lr=1e-3, swa_lr=5e-4, swa_epochs=20,
                    horizon_weights=None):
    """Standard training then SWA phase."""
    model = train_model(model, train_loader, val_loader, device,
                        epochs=epochs, patience=patience, lr=lr,
                        horizon_weights=horizon_weights)

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
    for module in swa_model.modules():
        if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d)):
            module.reset_running_stats()
            module.momentum = None
    swa_model.train()
    with torch.no_grad():
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            swa_model(*inputs)

    return swa_model


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
    per_h = {}
    for i, name in enumerate(horizons.keys()):
        per_h[name] = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * scale)
    per_h['overall'] = float(np.mean(list(per_h.values())))
    return per_h, preds, targets


def evaluate_ensemble(preds_list, targets, horizons, scale=GLUCOSE_SCALE,
                      weights=None):
    if weights is None:
        weights = [1.0 / len(preds_list)] * len(preds_list)

    if isinstance(weights[0], (list, np.ndarray)):
        combined = np.zeros_like(preds_list[0])
        for h_idx in range(len(list(horizons.keys()))):
            for m_idx, p in enumerate(preds_list):
                combined[:, h_idx] += weights[m_idx][h_idx] * p[:, h_idx]
    else:
        combined = sum(w * p for w, p in zip(weights, preds_list))

    per_h = {}
    for i, name in enumerate(horizons.keys()):
        per_h[name] = float(np.mean(np.abs(combined[:, i] - targets[:, i])) * scale)
    per_h['overall'] = float(np.mean(list(per_h.values())))
    return per_h


def optimize_ensemble_weights(preds_list, targets, horizons, steps=21):
    assert len(preds_list) == 2
    names = list(horizons.keys())
    best_weights = [[], []]
    for h_idx in range(len(names)):
        best_mae, best_a = float('inf'), 0.5
        for a_int in range(0, steps):
            a = a_int / (steps - 1)
            combined = a * preds_list[0][:, h_idx] + (1 - a) * preds_list[1][:, h_idx]
            mae = np.mean(np.abs(combined - targets[:, h_idx]))
            if mae < best_mae:
                best_mae, best_a = mae, a
        best_weights[0].append(best_a)
        best_weights[1].append(1 - best_a)
    return best_weights


# ─── Data Preparation ───

def prepare_inputs(base_t, base_v, pk_t, pk_v, history_steps, horizons,
                   isf_t=None, isf_v=None, max_horizon=144):
    tgt_t = extract_targets(base_t, history_steps, horizons)
    tgt_v = extract_targets(base_v, history_steps, horizons)

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

    hist_t = base_t[:, :history_steps, :].copy()
    hist_v = base_v[:, :history_steps, :].copy()
    if isf_t is not None:
        hist_t[:, :, 0:1] *= (GLUCOSE_SCALE / isf_t).reshape(-1, 1, 1)
        hist_v[:, :, 0:1] *= (GLUCOSE_SCALE / isf_v).reshape(-1, 1, 1)
        np.clip(hist_t[:, :, 0:1], 0, 10, out=hist_t[:, :, 0:1])
        np.clip(hist_v[:, :, 0:1], 0, 10, out=hist_v[:, :, 0:1])

    pk_hist_t = np.stack([pk_t[:, :history_steps, idx] / PK_NORMS[idx]
                          for idx in FUTURE_PK_INDICES], axis=-1)
    pk_hist_v = np.stack([pk_v[:, :history_steps, idx] / PK_NORMS[idx]
                          for idx in FUTURE_PK_INDICES], axis=-1)

    fpk_t = np.stack([pk_t[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
                      for idx in FUTURE_PK_INDICES], axis=-1)
    fpk_v = np.stack([pk_v[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
                      for idx in FUTURE_PK_INDICES], axis=-1)

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
    return train_loader, val_loader


# ─── EXP-396: Combined Training Improvements ───

def run_exp_396(patients_dir, device, quick=False):
    """Combine longer training + SWA for the champion ensemble."""
    print("\nexp396_combined_training")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL

    # Training configurations
    if quick:
        baseline_kw = {'epochs': 30, 'patience': 8}
        improved_kw = {'epochs': 50, 'patience': 12}
        swa_epochs = 10
    else:
        baseline_kw = {'epochs': 60, 'patience': 15}
        improved_kw = {'epochs': 100, 'patience': 20}
        swa_epochs = 20

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

        # --- BASELINE: current champion setup (60ep, patience 15) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld = make_loaders(inputs, 'dual')
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device, **baseline_kw)
        r, p_dual_base, tgt = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_baseline... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_baseline'].append(r)

        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ls, val_ls = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ls, val_ls, device, **baseline_kw)
        r, p_sh_base, _ = evaluate_model(model, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_baseline... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_baseline'].append(r)

        r_ens_base = evaluate_ensemble([p_dual_base, p_sh_base], tgt, horizons)
        print(f"    ensemble_baseline... MAE={r_ens_base['overall']:.1f}")
        all_results['ensemble_baseline'].append(r_ens_base)

        # --- IMPROVED: longer training for both ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld = make_loaders(inputs, 'dual')
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ld, val_ld, device, **improved_kw)
        r, p_dual_long, _ = evaluate_model(model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_long'].append(r)

        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ls, val_ls = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ls, val_ls, device, **improved_kw)
        r, p_sh_long, _ = evaluate_model(model, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_long'].append(r)

        r_ens_long = evaluate_ensemble([p_dual_long, p_sh_long], tgt, horizons)
        print(f"    ensemble_long... MAE={r_ens_long['overall']:.1f}")
        all_results['ensemble_long'].append(r_ens_long)

        # --- SWA DUAL + LONG SHARED ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld = make_loaders(inputs, 'dual')
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        swa_model = train_model_swa(model, train_ld, val_ld, device,
                                     epochs=improved_kw['epochs'],
                                     patience=improved_kw['patience'],
                                     swa_epochs=swa_epochs)
        r, p_dual_swa, _ = evaluate_model(swa_model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_swa_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_swa_long'].append(r)

        # Reuse shared_long prediction
        r_ens_swa = evaluate_ensemble([p_dual_swa, p_sh_long], tgt, horizons)
        print(f"    ensemble_swa_long... MAE={r_ens_swa['overall']:.1f}")
        all_results['ensemble_swa_long'].append(r_ens_swa)

        # Optimal weights
        w = optimize_ensemble_weights([p_dual_swa, p_sh_long], tgt, horizons)
        r_opt = evaluate_ensemble([p_dual_swa, p_sh_long], tgt, horizons,
                                   weights=w)
        w_str = ', '.join(f'{k}=({w[0][i]:.2f},{w[1][i]:.2f})'
                         for i, k in enumerate(horizons.keys()))
        print(f"    ensemble_swa_long_optimal... MAE={r_opt['overall']:.1f}")
        print(f"      weights=[{w_str}]")
        all_results['ensemble_swa_long_optimal'].append(r_opt)

        # --- BEST COMBO: SWA dual + SWA shared (both long) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ls, val_ls = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        swa_sh = train_model_swa(model, train_ls, val_ls, device,
                                  epochs=improved_kw['epochs'],
                                  patience=improved_kw['patience'],
                                  swa_epochs=swa_epochs)
        r, p_sh_swa, _ = evaluate_model(swa_sh, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_swa_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_swa_long'].append(r)

        r_both_swa = evaluate_ensemble([p_dual_swa, p_sh_swa], tgt, horizons)
        print(f"    ensemble_both_swa... MAE={r_both_swa['overall']:.1f}")
        all_results['ensemble_both_swa'].append(r_both_swa)

    return _save_results('exp396_combined_training', all_results, horizons)


# ─── EXP-397: Short-Weight Dual + Long Training ───

def run_exp_397(patients_dir, device, quick=False):
    """Short-horizon weighted dual + longer training shared."""
    print("\nexp397_short_dual_long_shared")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL

    if quick:
        improved_kw = {'epochs': 50, 'patience': 12}
        short_weights = [2.0, 1.0, 0.5]
        swa_epochs = 10
    else:
        improved_kw = {'epochs': 100, 'patience': 20}
        short_weights = [3.0, 2.0, 1.5, 1.0, 0.5, 0.3, 0.2, 0.1]
        swa_epochs = 20

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

        # Dual with short weights + SWA + long training
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ld, val_ld = make_loaders(inputs, 'dual')
        model = DualEncoderWithFuture(4, 4, n_horizons)
        t0 = time.time()
        swa_model = train_model_swa(model, train_ld, val_ld, device,
                                     epochs=improved_kw['epochs'],
                                     patience=improved_kw['patience'],
                                     swa_epochs=swa_epochs,
                                     horizon_weights=short_weights)
        r, p_dual_short, tgt = evaluate_model(swa_model, val_ld, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    dual_short_swa... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['dual_short_swa'].append(r)

        # Shared with long training (no SWA — hurt in v10)
        torch.manual_seed(seed)
        np.random.seed(seed)
        train_ls, val_ls = make_loaders(inputs, 'shared')
        model = ResNetCNNWithFuture(12, 4, n_horizons)
        t0 = time.time()
        model = train_model(model, train_ls, val_ls, device, **improved_kw)
        r, p_sh_long, _ = evaluate_model(model, val_ls, device, horizons)
        dt = time.time() - t0
        h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
        print(f"    shared_long... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
        all_results['shared_long'].append(r)

        # Ensemble
        r_ens = evaluate_ensemble([p_dual_short, p_sh_long], tgt, horizons)
        print(f"    ensemble_short_dual... MAE={r_ens['overall']:.1f}")
        all_results['ensemble_short_dual'].append(r_ens)

        # Optimal
        w = optimize_ensemble_weights([p_dual_short, p_sh_long], tgt, horizons)
        r_opt = evaluate_ensemble([p_dual_short, p_sh_long], tgt, horizons,
                                   weights=w)
        w_str = ', '.join(f'{k}=({w[0][i]:.2f},{w[1][i]:.2f})'
                         for i, k in enumerate(horizons.keys()))
        print(f"    ensemble_optimal... MAE={r_opt['overall']:.1f}")
        print(f"      weights=[{w_str}]")
        all_results['ensemble_optimal'].append(r_opt)

    return _save_results('exp397_short_dual', all_results, horizons)


# ─── EXP-398: Training Duration Sweep ───

def run_exp_398(patients_dir, device, quick=False):
    """Sweep training epochs to find optimal duration."""
    print("\nexp398_epoch_sweep")
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    seeds = SEEDS_QUICK if quick else SEEDS_FULL

    if quick:
        epoch_configs = [
            ('ep20', 20, 6),
            ('ep30', 30, 8),
            ('ep50', 50, 12),
            ('ep80', 80, 18),
        ]
    else:
        epoch_configs = [
            ('ep60', 60, 15),
            ('ep80', 80, 18),
            ('ep100', 100, 20),
            ('ep120', 120, 25),
            ('ep150', 150, 30),
        ]

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
        for name, epochs, patience in epoch_configs:
            torch.manual_seed(seed)
            np.random.seed(seed)
            train_ld, val_ld = make_loaders(inputs, 'shared')
            model = ResNetCNNWithFuture(12, 4, n_horizons)
            t0 = time.time()
            model = train_model(model, train_ld, val_ld, device,
                                epochs=epochs, patience=patience)
            r, _, _ = evaluate_model(model, val_ld, device, horizons)
            dt = time.time() - t0
            h_str = ', '.join(f'{k}={v:.1f}' for k, v in r.items() if k != 'overall')
            print(f"    {name}... MAE={r['overall']:.1f} [{h_str}]  ({dt:.0f}s)")
            all_results[name].append(r)

    return _save_results('exp398_epoch_sweep', all_results, horizons)


# ─── Utilities ───

def _save_results(name, all_results, horizons):
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


EXPERIMENTS = {
    '396': run_exp_396,
    '397': run_exp_397,
    '398': run_exp_398,
}


def main():
    parser = argparse.ArgumentParser(
        description='PK Forecast v11: Combined Best Techniques')
    parser.add_argument('--experiment', default='all')
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
        sys.exit(1)


if __name__ == '__main__':
    main()
