"""
experiment_lib.py — Rigid shared infrastructure for ML experiments.

This module provides reusable building blocks so that experiment files
stay small (~100 lines each) and focused on *what* to test, not *how*
to train/evaluate/save.

Coding agents should NOT edit this file.  Edit experiments_agentic.py instead.
"""

import json
import os
import time
import numpy as np
import torch
import torch.nn as nn
from contextlib import contextmanager
from pathlib import Path
from torch.utils.data import DataLoader

from .device import resolve_device, batch_to_device
from .model import CGMTransformerAE, CGMGroupedEncoder, train_one_epoch, eval_loss
from .real_data_adapter import (
    load_nightscout_to_dataset, load_multipatient_nightscout,
    build_nightscout_grid, build_extended_features,
    downsample_grid, build_multihorizon_windows,
)
from .evaluate import (
    evaluate_model, persistence_baseline,
    time_in_range, glycemia_risk_index, clinical_summary, override_accuracy,
)
from .schema import (
    NUM_FEATURES, NUM_FEATURES_EXTENDED,
    NORMALIZATION_SCALES, EXTENDED_FEATURE_NAMES,
)

# Module-level device, shared with run_experiment.py
_device = torch.device('cpu')


def set_device(dev):
    global _device
    _device = dev


def get_device():
    return _device


# ── Reproducibility ──────────────────────────────────────────────────────

import random

def set_seed(seed=42):
    """Set all random seeds for reproducible training."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ── Experiment Context ───────────────────────────────────────────────────

class ExperimentContext:
    """Manages timing, results dict, and save for an experiment run.

    Usage:
        ctx = ExperimentContext('EXP-026', output_dir)
        ctx.log('Step 1 done')
        ctx.result['my_metric'] = 0.42
        ctx.save('exp026_results.json')
    """

    def __init__(self, exp_id, output_dir, **extra):
        self.exp_id = exp_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.result = {
            'experiment': exp_id,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            **extra,
        }
        print('=' * 60)
        print(f'{exp_id}')
        print('=' * 60)

    def log(self, msg):
        print(f'  [{self.exp_id}] {msg}')

    def section(self, title):
        print(f'\n--- {title} ---')

    def save(self, filename):
        self.result['elapsed_seconds'] = round(time.time() - self.t0, 1)
        path = self.output_dir / filename
        with open(path, 'w') as f:
            json.dump(self.result, f, indent=2, default=str)
        print(f'\n  Results → {path}  ({self.result["elapsed_seconds"]}s)')
        return self.result


# ── Model Factory ────────────────────────────────────────────────────────

def create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2):
    """Create a model by name."""
    if arch == 'grouped':
        return CGMGroupedEncoder(
            input_dim=input_dim, d_model=d_model, nhead=nhead, num_layers=num_layers)
    elif arch == 'ae':
        return CGMTransformerAE(
            input_dim=input_dim, d_model=d_model, nhead=nhead, num_layers=num_layers)
    else:
        raise ValueError(f'Unknown architecture: {arch}')


def load_checkpoint(model, path):
    """Load best checkpoint into model, return checkpoint dict."""
    ckpt = torch.load(path, map_location=get_device(), weights_only=True)
    model.load_state_dict(ckpt['model_state'])
    model.to(get_device())
    return ckpt


def find_checkpoint(output_dir, *candidates):
    """Find first existing checkpoint from candidate list."""
    out = Path(output_dir)
    for c in candidates:
        p = out / c
        if p.exists():
            return str(p)
    # Fallback: any grouped checkpoint
    for f in sorted(out.glob('*grouped*.pth')):
        return str(f)
    return None


def transfer_weights(model_src, model_dst):
    """Copy compatible weights from src to dst. Returns count transferred."""
    src_sd = model_src.state_dict()
    dst_sd = model_dst.state_dict()
    n = 0
    for k, v in src_sd.items():
        if k in dst_sd and dst_sd[k].shape == v.shape:
            dst_sd[k] = v
            n += 1
    model_dst.load_state_dict(dst_sd)
    return n


# ── Training ─────────────────────────────────────────────────────────────

def train(model, train_ds, val_ds, save_path, label,
          lr=1e-3, epochs=50, batch=32, patience=15,
          weight_decay=1e-5, lr_patience=5):
    """Standard training loop. Returns (best_val_loss, epochs_run)."""
    device = get_device()
    model.to(device)
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    for ep in range(epochs):
        tl = train_one_epoch(model, train_dl, opt, crit)
        vl = eval_loss(model, val_dl, crit)
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    load_checkpoint(model, save_path)
    return best, ep + 1


# ── Evaluation ───────────────────────────────────────────────────────────

def forecast_mse(model, val_ds, batch_size=64):
    """Causal future-only forecast MSE on glucose channel.

    This is THE standard metric for comparing forecast models.
    Input windows are [history | future], each half = window_size steps.
    Model predicts with causal mask; we score only future glucose (channel 0).
    """
    device = get_device()
    model.eval()
    crit = nn.MSELoss()
    losses = []
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        with torch.no_grad():
            pred = model(x, causal=True)
        losses.append(crit(pred[:, half:, :1], x[:, half:, :1]).item())
    return float(np.mean(losses))


def persistence_mse(val_ds, batch_size=64):
    """Persistence baseline: last known glucose repeated forward."""
    crit = nn.MSELoss()
    losses = []
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch[0]
        half = x.shape[1] // 2
        persist = x[:, half - 1:half, :1].expand(-1, half, -1)
        losses.append(crit(persist, x[:, half:, :1]).item())
    return float(np.mean(losses))


def improvement_pct(model_mse, baseline_mse):
    """Percentage improvement over baseline."""
    if baseline_mse <= 0:
        return 0.0
    return float((baseline_mse - model_mse) / baseline_mse * 100)


# ── Data Loading ─────────────────────────────────────────────────────────

def resolve_patient_paths(patients_dir=None, real_data=None):
    """Resolve patient training directories."""
    if patients_dir and os.path.isdir(patients_dir):
        paths = sorted([
            os.path.join(patients_dir, p, 'training')
            for p in os.listdir(patients_dir)
            if os.path.isdir(os.path.join(patients_dir, p, 'training'))
        ])
        if paths:
            return paths
    if real_data:
        return [real_data]
    return []


def load_patient_profile(data_path):
    """Load ISF/CR from profile.json → (isf, cr)."""
    for candidate in [data_path, os.path.dirname(data_path.rstrip('/'))]:
        profile_path = os.path.join(candidate, 'profile.json')
        if os.path.exists(profile_path):
            with open(profile_path) as f:
                profiles = json.load(f)
            if profiles:
                store = profiles[0].get('store', {})
                default = store.get('Default', {})
                sens = default.get('sens', [{}])
                cr_list = default.get('carbratio', [{}])
                isf = float(sens[0].get('value', 40.0)) if sens else 40.0
                cr = float(cr_list[0].get('value', 10.0)) if cr_list else 10.0
                if isf != 40.0 or cr != 10.0:
                    return isf, cr
    return 40.0, 10.0


def build_16f_windows(patient_paths, window_size):
    """Build 16-feature extended windows from patient data."""
    windows = []
    ws = window_size * 2
    stride = window_size
    for ppath in patient_paths:
        try:
            grid_df, feat8 = build_nightscout_grid(ppath, verbose=False)
            if feat8 is None:
                continue
            feat16 = build_extended_features(grid_df, feat8, verbose=False)
            for start in range(0, feat16.shape[0] - ws, stride):
                w = feat16[start:start + ws]
                if not np.isnan(w[:, 0]).any():
                    windows.append(w)
        except Exception:
            continue
    return windows


def windows_to_datasets(windows, val_fraction=0.2, seed=42):
    """Convert list of numpy windows to train/val TensorDatasets.

    Each dataset yields (x, x) pairs for autoencoder-style training
    (matching what train_one_epoch expects).
    """
    arr = np.stack(windows).astype(np.float32)
    rng = np.random.RandomState(seed)
    rng.shuffle(arr)
    split = int((1 - val_fraction) * len(arr))
    t_train = torch.from_numpy(arr[:split])
    t_val = torch.from_numpy(arr[split:])
    train_ds = torch.utils.data.TensorDataset(t_train, t_train)
    val_ds = torch.utils.data.TensorDataset(t_val, t_val)
    return train_ds, val_ds


# ── Promotion (fold experiment → main model) ─────────────────────────────

def promote_checkpoint(src_path, dest_name, output_dir='checkpoints'):
    """Copy an experiment checkpoint to the production checkpoints dir.

    After experiments determine a winner, call this to make it the
    default model for inference/deployment.
    """
    import shutil
    dest = os.path.join(output_dir, dest_name)
    os.makedirs(output_dir, exist_ok=True)
    shutil.copy2(src_path, dest)
    print(f'  Promoted: {src_path} → {dest}')
    return dest
