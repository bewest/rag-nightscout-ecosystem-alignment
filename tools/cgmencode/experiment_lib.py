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
from .model import CGMTransformerAE, CGMGroupedEncoder, AttentionPooling, train_one_epoch, eval_loss
from .real_data_adapter import (
    load_nightscout_to_dataset, load_multipatient_nightscout,
    build_nightscout_grid, build_extended_features,
    downsample_grid, build_multihorizon_windows,
)
from .schema import FUTURE_UNKNOWN_CHANNELS
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

def create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2,
                 semantic_groups=False, aux_config=None, dropout=0.1):
    """Create a model by name."""
    if arch == 'grouped':
        return CGMGroupedEncoder(
            input_dim=input_dim, d_model=d_model, nhead=nhead, num_layers=num_layers,
            dropout=dropout, semantic_groups=semantic_groups, aux_config=aux_config)
    elif arch == 'ae':
        return CGMTransformerAE(
            input_dim=input_dim, d_model=d_model, nhead=nhead, num_layers=num_layers)
    else:
        raise ValueError(f'Unknown architecture: {arch}')


def mask_future_channels(x_in, half):
    """Zero out future-unknown channels in positions half: onward.

    Uses FUTURE_UNKNOWN_CHANNELS from schema.py — channels whose values
    are unknown at real-time inference (future glucose, IOB, COB, actions,
    glucose derivatives, and treatment-timing features).
    """
    for ch in FUTURE_UNKNOWN_CHANNELS:
        if ch < x_in.shape[2]:
            x_in[:, half:, ch] = 0.0
    return x_in


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

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)
    return best, ep + 1


def train_forecast(model, train_ds, val_ds, save_path, label,
                   lr=1e-3, epochs=50, batch=32, patience=15,
                   weight_decay=1e-5, lr_patience=5):
    """Forecast-aware training: masks future glucose so the model learns to
    predict it from history + other features.

    Input windows are (x, x) autoencoder pairs where x = [history | future].
    During training, future glucose (channel 0, positions half:) is zeroed in
    the model input. The loss is MSE on future glucose only.
    Returns (best_val_loss, epochs_run).
    """
    device = get_device()
    model.to(device)
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    def _forecast_step(batch_data, backward=False):
        x = batch_to_device(batch_data[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])  # future glucose only
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _forecast_step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _forecast_step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
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

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)
    return best, ep + 1


# ── Evaluation ───────────────────────────────────────────────────────────

def forecast_mse(model, val_ds, batch_size=64, mask_future=True):
    """Causal future-only forecast MSE on glucose channel.

    This is THE standard metric for comparing forecast models.
    Input windows are [history | future], each half = window_size steps.
    Model predicts with causal mask; we score only future glucose (channel 0).

    When mask_future=True (default), future glucose values in the input are
    zeroed out so the model cannot simply copy them.  This makes the metric
    a TRUE forecast evaluation rather than a reconstruction test.
    """
    device = get_device()
    model.eval()
    crit = nn.MSELoss()
    losses = []
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        if mask_future:
            x_input = x.clone()
            mask_future_channels(x_input, half)
        else:
            x_input = x
        with torch.no_grad():
            pred = model(x_input, causal=True)
        # Handle multi-task models that return a dict
        if isinstance(pred, dict):
            pred = pred['forecast']
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


MMOL_TO_MGDL = 18.0182


def load_patient_profile(data_path):
    """Load ISF/CR from profile.json → (isf_mgdl, cr).

    ISF is always returned in mg/dL per unit. If the Nightscout profile
    uses mmol/L display units (``store.Default.units == "mmol/L"``), the
    stored ISF value is converted by multiplying by 18.0182.

    CR (grams of carbs per unit insulin) is unit-agnostic and returned
    as-is regardless of display units.
    """
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

                # Convert ISF to mg/dL if profile uses mmol/L display units.
                # Nightscout SGV values are always stored in mg/dL, so ISF
                # must match for physics model calculations to be correct.
                units = default.get('units', 'mg/dL')
                if units and 'mmol' in units.lower():
                    isf = isf * MMOL_TO_MGDL

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


# ── Multi-Task Training ──────────────────────────────────────────────────

DEFAULT_TASK_WEIGHTS = {
    'forecast': 1.0,
    'event': 0.3,
    'drift': 0.2,
    'state': 0.1,
}


def multitask_loss(outputs, targets, weights=None, class_weights=None):
    """Compute composite loss from multi-task model outputs.

    Args:
        outputs: dict from CGMGroupedEncoder with aux_config
            - 'forecast': (B, T, input_dim) — reconstruction
            - 'event_logits': (B, n_classes) — optional event classification
            - 'drift_pred': (B, 2) — optional ISF/CR deviation prediction
            - 'state_logits': (B, n_states) — optional metabolic state
        targets: dict with matching keys
            - 'x': (B, T, input_dim) — full window for forecast target
            - 'event_label': (B,) LongTensor — optional event class index
            - 'drift_target': (B, 2) — optional ISF/CR % deviation
            - 'state_label': (B,) LongTensor — optional metabolic state index
        weights: dict of task name → weight (default: DEFAULT_TASK_WEIGHTS)
        class_weights: optional dict with per-class weights for CE losses
            - 'event': (n_event_classes,) tensor of per-class weights
            - 'state': (n_state_classes,) tensor of per-class weights
            These address class imbalance (e.g., correction_bolus at 48%).
            Computed by generate_aux_labels.compute_class_weights().

    Returns:
        (total_loss, loss_dict) where loss_dict has per-head losses for logging
    """
    w = weights or DEFAULT_TASK_WEIGHTS
    cw = class_weights or {}
    mse = nn.MSELoss()

    loss_dict = {}
    total = torch.tensor(0.0, device=targets['x'].device)

    # If model returned a plain tensor (no aux heads), wrap it
    if isinstance(outputs, torch.Tensor):
        outputs = {'forecast': outputs}

    # Forecast head: MSE on future glucose only
    x = targets['x']
    pred = outputs['forecast']
    half = x.shape[1] // 2
    forecast_loss = mse(pred[:, half:, :1], x[:, half:, :1])
    loss_dict['forecast'] = forecast_loss.item()
    total = total + w.get('forecast', 1.0) * forecast_loss

    # Event head: CrossEntropy on event classification (with optional class weights)
    if 'event_logits' in outputs and 'event_label' in targets:
        labels = targets['event_label']
        valid = labels >= 0
        if valid.any():
            event_cw = cw.get('event')
            if event_cw is not None:
                event_cw = event_cw.to(targets['x'].device)
            ce_event = nn.CrossEntropyLoss(weight=event_cw)
            event_loss = ce_event(outputs['event_logits'][valid], labels[valid])
            loss_dict['event'] = event_loss.item()
            total = total + w.get('event', 0.3) * event_loss

    # Drift head: MSE on ISF/CR % deviation
    if 'drift_pred' in outputs and 'drift_target' in targets:
        drift_tgt = targets['drift_target']
        valid = ~torch.isnan(drift_tgt[:, 0])
        if valid.any():
            drift_loss = mse(outputs['drift_pred'][valid], drift_tgt[valid])
            loss_dict['drift'] = drift_loss.item()
            total = total + w.get('drift', 0.2) * drift_loss

    # State head: CrossEntropy on metabolic state (with optional class weights)
    if 'state_logits' in outputs and 'state_label' in targets:
        labels = targets['state_label']
        valid = labels >= 0
        if valid.any():
            state_cw = cw.get('state')
            if state_cw is not None:
                state_cw = state_cw.to(targets['x'].device)
            ce_state = nn.CrossEntropyLoss(weight=state_cw)
            state_loss = ce_state(outputs['state_logits'][valid], labels[valid])
            loss_dict['state'] = state_loss.item()
            total = total + w.get('state', 0.1) * state_loss

    return total, loss_dict


def train_multitask(model, train_ds, val_ds, save_path, label,
                    lr=1e-3, epochs=50, batch=32, patience=15,
                    weight_decay=1e-5, lr_patience=5, task_weights=None,
                    class_weights=None):
    """Multi-objective training loop with composite loss.

    Handles both plain autoencoders (backward compatible — just MSE)
    and multi-task models with auxiliary heads.

    Datasets should yield tuples of (features, targets_dict) where
    targets_dict is a dict with 'x' and optional 'event_label',
    'drift_target', 'state_label'. For backward compatibility,
    also accepts (x, x) pairs from standard AE datasets.

    Args:
        class_weights: optional dict with per-class weight tensors:
            {'event': (n_event_classes,) tensor, 'state': (n_state_classes,) tensor}
            From generate_aux_labels.compute_class_weights(). Addresses class
            imbalance in event detection (correction_bolus dominance) and
            state classification.

    Returns (best_val_loss, epochs_run, loss_history).
    """
    device = get_device()
    model.to(device)
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    best = float('inf')
    stale = 0
    history = []

    def _make_targets(batch_data):
        """Convert batch to targets dict, handling both AE and multitask formats."""
        features = batch_to_device(batch_data[0], device)
        if len(batch_data) > 1 and isinstance(batch_data[1], dict):
            targets = {k: batch_to_device(v, device) if isinstance(v, torch.Tensor) else v
                       for k, v in batch_data[1].items()}
            targets['x'] = features
        else:
            targets = {'x': features}
        return features, targets

    def _step(batch_data, backward=False):
        features, targets = _make_targets(batch_data)
        half = features.shape[1] // 2
        x_in = features.clone()
        mask_future_channels(x_in, half)

        outputs = model(x_in, causal=True)
        total_loss, loss_dict = multitask_loss(outputs, targets, task_weights,
                                               class_weights=class_weights)

        if backward:
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return total_loss.item() * features.size(0), features.size(0), loss_dict

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        epoch_losses = {}
        for b in train_dl:
            opt.zero_grad()
            l, n, ld = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
            for k, v in ld.items():
                epoch_losses.setdefault(k, []).append(v)
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n, _ = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        avg_losses = {k: float(np.mean(v)) for k, v in epoch_losses.items()}
        history.append({'epoch': ep, 'train_loss': tl, 'val_loss': vl, **avg_losses})

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
                'task_weights': task_weights or DEFAULT_TASK_WEIGHTS,
                'aux_config': getattr(model, 'aux_config', {}),
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            head_str = ' '.join(f'{k}={v:.4f}' for k, v in avg_losses.items())
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e} [{head_str}]{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)
    return best, ep + 1, history
