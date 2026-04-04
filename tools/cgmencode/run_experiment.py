#!/usr/bin/env python3
"""
run_experiment.py — Orchestrates multi-step ML experiments.

Each experiment is a reproducible sequence of train/evaluate steps using
the existing train.py and evaluate.py infrastructure.

Usage:
    # Transfer learning: synthetic pre-train → real fine-tune → compare vs scratch
    python3 -m tools.cgmencode.run_experiment transfer \
        --real-data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history

    # Conditioned Transformer with regularization sweep
    python3 -m tools.cgmencode.run_experiment conditioned \
        --real-data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history

    # Both experiments
    python3 -m tools.cgmencode.run_experiment all \
        --real-data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history
"""

import argparse
import json
import os
import random
import sys
import time
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader

from .device import resolve_device, add_device_arg, batch_to_device


def set_seed(seed):
    """Set all random seeds for reproducible training.

    Controls: Python random, NumPy, PyTorch CPU/CUDA.
    Does NOT affect data loading (real data is deterministic),
    only model initialization, batch shuffling, and synthetic splits.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

from .model import CGMTransformerAE, CGMGroupedEncoder, train_one_epoch, eval_loss
from .toolbox import ConditionedTransformer
from .sim_adapter import load_conformance_to_dataset
from .real_data_adapter import (
    load_nightscout_to_dataset, load_nightscout_grid_timestamps,
    load_multipatient_nightscout,
)
from .evaluate import evaluate_model, persistence_baseline
from .physics_model import (
    compute_residual_windows, compute_residual_windows_uva,
    residual_to_glucose, load_uva_predictions, align_uva_to_grid,
    RESIDUAL_SCALE,
)

DEFAULT_SYNTH_DIRS = [
    'conformance/in-silico/vectors',
    'conformance/t1pal/vectors/oref0-endtoend',
]

# Module-level default device, set by main() so all experiment functions
# use GPU automatically without changing every train_loop/load_best call.
_DEFAULT_DEVICE = torch.device('cpu')


def set_default_device(device: torch.device):
    """Set the module-level default compute device."""
    global _DEFAULT_DEVICE
    _DEFAULT_DEVICE = device


def save_results(results, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'  Results → {path}')


def train_loop(model, train_ld, val_ld, lr, epochs, save_path, label,
               weight_decay=1e-5, patience=15, lr_patience=5, device=None):
    """Standard training loop with LR scheduling and early stopping.
    Returns (best_val_loss, epochs_run)."""
    device = device if device is not None else _DEFAULT_DEVICE
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0
    epochs_run = 0

    for ep in range(epochs):
        epochs_run = ep + 1
        tl = train_one_epoch(model, train_ld, opt, crit)
        vl = eval_loss(model, val_ld, crit)
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
            print(f'  [{label}] Epoch {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    return best, epochs_run


def load_best(model, path, device=None):
    """Load best checkpoint into model."""
    device = device if device is not None else _DEFAULT_DEVICE
    ckpt = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt['model_state'])
    model.to(device)
    return ckpt


def run_transfer(args):
    """EXP-003: Sim-to-Real Transfer Learning."""
    print('=' * 60)
    print('EXP-003: Sim-to-Real Transfer Learning')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-003', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Step 1: Pre-train on synthetic
    print('\n--- Step 1: Pre-train on synthetic ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)

    if syn_t and len(syn_t) > 0:
        print(f'  Synthetic: {len(syn_t)} train, {len(syn_v)} val')
        model_syn = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        train_loop(model_syn,
                   DataLoader(syn_t, batch_size=args.batch, shuffle=True),
                   DataLoader(syn_v, batch_size=args.batch),
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=str(out / 'ae_synthetic.pth'), label='synthetic')
        results['has_synthetic'] = True
    else:
        print('  WARNING: No synthetic vectors found.')
        results['has_synthetic'] = False

    # Step 2: Load real data
    print('\n--- Step 2: Load real data ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    real_tl = DataLoader(real_t, batch_size=args.batch, shuffle=True)
    real_vl = DataLoader(real_v, batch_size=args.batch)
    results['real_samples'] = {'train': len(real_t), 'val': len(real_v)}

    # Step 3: Zero-shot evaluation
    if results.get('has_synthetic'):
        print('\n--- Step 3: Zero-shot (synthetic model → real data) ---')
        model_zs = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        load_best(model_zs, str(out / 'ae_synthetic.pth'))
        results['zero_shot'] = evaluate_model(model_zs, real_vl, 'ae', args.window)
        print(f'  Zero-shot: MAE={results["zero_shot"]["mae_mgdl"]:.2f} '
              f'RMSE={results["zero_shot"]["rmse_mgdl"]:.2f} mg/dL')

    # Step 4: Fine-tune (transfer)
    print('\n--- Step 4: Fine-tune on real data (transfer) ---')
    model_ft = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    if results.get('has_synthetic'):
        load_best(model_ft, str(out / 'ae_synthetic.pth'))
    train_loop(model_ft, real_tl, real_vl,
               lr=5e-4, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_transfer.pth'), label='transfer')

    # Step 5: From scratch (baseline)
    print('\n--- Step 5: Train from scratch (baseline) ---')
    model_sc = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    train_loop(model_sc, real_tl, real_vl,
               lr=1e-3, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_scratch.pth'), label='scratch')

    # Step 6: Final comparison
    print('\n--- Results ---')
    load_best(model_ft, str(out / 'ae_transfer.pth'))
    results['transfer'] = evaluate_model(model_ft, real_vl, 'ae', args.window)

    load_best(model_sc, str(out / 'ae_scratch.pth'))
    results['scratch'] = evaluate_model(model_sc, real_vl, 'ae', args.window)

    # Persistence baseline (needs 2x window)
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    print(f'\n  Persistence:   MAE={p_mae:.2f}  RMSE={p_rmse:.2f} mg/dL')
    if 'zero_shot' in results:
        zs = results['zero_shot']
        print(f'  Zero-shot:     MAE={zs["mae_mgdl"]:.2f}  RMSE={zs["rmse_mgdl"]:.2f} mg/dL')
    ft = results['transfer']
    sc = results['scratch']
    print(f'  Transfer:      MAE={ft["mae_mgdl"]:.2f}  RMSE={ft["rmse_mgdl"]:.2f} mg/dL')
    print(f'  From scratch:  MAE={sc["mae_mgdl"]:.2f}  RMSE={sc["rmse_mgdl"]:.2f} mg/dL')

    delta = sc['mae_mgdl'] - ft['mae_mgdl']
    if delta > 0:
        print(f'\n  Transfer wins by {delta:.2f} mg/dL MAE')
    else:
        print(f'\n  Scratch wins by {-delta:.2f} mg/dL MAE')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp003_transfer_results.json'))
    return results


def run_conditioned(args):
    """EXP-004: Conditioned Transformer with regularization."""
    print('=' * 60)
    print('EXP-004: Conditioned Transformer Regularization')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)

    # Load real data (conditioned format: 2x window, split at window_size)
    print('\n--- Load real data (conditioned) ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, window_size=args.window, conditioned=True)
    use_pin = _DEFAULT_DEVICE.type == 'cuda'
    real_tl = DataLoader(real_t, batch_size=args.batch, shuffle=True, pin_memory=use_pin)
    real_vl = DataLoader(real_v, batch_size=args.batch, pin_memory=use_pin)

    # Sweep: try different regularization configs
    configs = [
        {'label': 'baseline',   'dropout': 0.0, 'weight_decay': 0.0,  'lr': 5e-4},
        {'label': 'dropout',    'dropout': 0.1, 'weight_decay': 0.0,  'lr': 5e-4},
        {'label': 'wd',         'dropout': 0.0, 'weight_decay': 1e-4, 'lr': 5e-4},
        {'label': 'dropout+wd', 'dropout': 0.2, 'weight_decay': 1e-4, 'lr': 3e-4},
    ]

    results = {
        'experiment': 'EXP-004',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'real_samples': {'train': len(real_t), 'val': len(real_v)},
        'configs': {},
    }

    crit = nn.MSELoss()

    for cfg in configs:
        label = cfg['label']
        print(f'\n--- Config: {label} (dropout={cfg["dropout"]}, wd={cfg["weight_decay"]}) ---')

        # Build model with dropout via the encoder layer
        model = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)

        # Manually add dropout if requested (ConditionedTransformer doesn't expose it)
        if cfg['dropout'] > 0:
            # Add dropout after each linear projection
            model.history_proj = nn.Sequential(
                nn.Linear(8, 64), nn.Dropout(cfg['dropout']))
            model.action_proj = nn.Sequential(
                nn.Linear(3, 64), nn.Dropout(cfg['dropout']))

        model.to(_DEFAULT_DEVICE)

        opt = torch.optim.AdamW(model.parameters(), lr=cfg['lr'],
                                weight_decay=cfg['weight_decay'])
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

        best_val = float('inf')
        stale = 0
        save_path = str(out / f'conditioned_{label}.pth')

        for ep in range(args.epochs):
            # Train
            model.train()
            total = 0; n = 0
            for batch in real_tl:
                batch = batch_to_device(batch, _DEFAULT_DEVICE)
                (h, a), t = batch
                opt.zero_grad()
                pred = model(h, a)
                loss = crit(pred, t)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                total += loss.item() * h.size(0); n += h.size(0)
            tl = total / n

            # Validate
            model.eval()
            total_v = 0; nv = 0
            with torch.no_grad():
                for batch in real_vl:
                    batch = batch_to_device(batch, _DEFAULT_DEVICE)
                    (h, a), t = batch
                    pred = model(h, a)
                    total_v += crit(pred, t).item() * h.size(0); nv += h.size(0)
            vl = total_v / nv
            sched.step(vl)

            if vl < best_val:
                best_val = vl; stale = 0
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                torch.save({'epoch': ep, 'model_state': model.state_dict(),
                            'val_loss': vl, 'config': cfg}, save_path)
            else:
                stale += 1

            if (ep + 1) % 10 == 0 or ep == args.epochs - 1:
                lr_now = opt.param_groups[0]['lr']
                mark = ' *' if stale == 0 else ''
                print(f'  [{label}] Epoch {ep+1:3d}/{args.epochs} '
                      f'train={tl:.6f} val={vl:.6f} best={best_val:.6f} '
                      f'lr={lr_now:.1e}{mark}')

            if args.patience > 0 and stale >= args.patience:
                print(f'  [{label}] Early stop at epoch {ep+1}')
                break

        # Evaluate best
        ckpt = torch.load(save_path, map_location=_DEFAULT_DEVICE, weights_only=True)
        model.load_state_dict(ckpt['model_state'])
        model.to(_DEFAULT_DEVICE)
        metrics = evaluate_model(model, real_vl, 'conditioned', args.window)
        results['configs'][label] = {
            **cfg, **metrics,
            'best_val_loss': round(best_val, 8),
            'epochs_run': ep + 1,
        }
        print(f'  [{label}] MAE={metrics["mae_mgdl"]:.2f} RMSE={metrics["rmse_mgdl"]:.2f} mg/dL')

    # Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    print(f'\n--- Summary ---')
    print(f'  Persistence: MAE={p_mae:.2f} mg/dL')
    for label, m in results['configs'].items():
        print(f'  {label:12s}: MAE={m["mae_mgdl"]:.2f}  RMSE={m["rmse_mgdl"]:.2f} mg/dL')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp004_conditioned_results.json'))
    return results


def run_conditioned_transfer(args):
    """EXP-006: Conditioned Transformer with synthetic pre-training + real fine-tuning."""
    print('=' * 60)
    print('EXP-006: Conditioned Transformer — Synthetic Pre-train → Real Fine-tune')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-006', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Step 1: Pre-train on synthetic (conditioned mode — diverse actions from 50 patients)
    print('\n--- Step 1: Pre-train on synthetic (conditioned) ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, window_size=args.window, conditioned=True)

    if syn_t and len(syn_t) > 0:
        print(f'  Synthetic: {len(syn_t)} train, {len(syn_v)} val')
        model_syn = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
        _train_conditioned(model_syn, syn_t, syn_v, lr=1e-3, epochs=args.epochs,
                           patience=args.patience, save_path=str(out / 'cond_synthetic.pth'),
                           label='synthetic', batch=args.batch)
        results['has_synthetic'] = True
        results['synthetic_samples'] = {'train': len(syn_t), 'val': len(syn_v)}
    else:
        print('  WARNING: No synthetic vectors found.')
        results['has_synthetic'] = False

    # Step 2: Load real data (conditioned)
    print('\n--- Step 2: Load real data (conditioned) ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, window_size=args.window, conditioned=True)
    results['real_samples'] = {'train': len(real_t), 'val': len(real_v)}

    # Step 3: Zero-shot evaluation (synthetic model → real data)
    if results.get('has_synthetic'):
        print('\n--- Step 3: Zero-shot (synthetic → real) ---')
        model_zs = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
        load_best(model_zs, str(out / 'cond_synthetic.pth'))
        real_vl = DataLoader(real_v, batch_size=args.batch)
        results['zero_shot'] = evaluate_model(model_zs, real_vl, 'conditioned', args.window)
        print(f'  Zero-shot: MAE={results["zero_shot"]["mae_mgdl"]:.2f} '
              f'RMSE={results["zero_shot"]["rmse_mgdl"]:.2f} mg/dL')

    # Step 4: Fine-tune on real data (transfer)
    print('\n--- Step 4: Fine-tune on real data (transfer) ---')
    model_ft = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
    if results.get('has_synthetic'):
        load_best(model_ft, str(out / 'cond_synthetic.pth'))
    _train_conditioned(model_ft, real_t, real_v, lr=5e-4, epochs=args.epochs,
                       patience=args.patience, save_path=str(out / 'cond_transfer.pth'),
                       label='transfer', batch=args.batch, weight_decay=1e-4)

    # Step 5: From scratch with best regularization (wd=1e-4, from EXP-004)
    print('\n--- Step 5: From scratch with wd=1e-4 (EXP-004 best) ---')
    model_sc = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
    _train_conditioned(model_sc, real_t, real_v, lr=5e-4, epochs=args.epochs,
                       patience=args.patience, save_path=str(out / 'cond_scratch.pth'),
                       label='scratch', batch=args.batch, weight_decay=1e-4)

    # Step 6: Final comparison
    print('\n--- Results ---')
    real_vl = DataLoader(real_v, batch_size=args.batch)

    load_best(model_ft, str(out / 'cond_transfer.pth'))
    results['transfer'] = evaluate_model(model_ft, real_vl, 'conditioned', args.window)

    load_best(model_sc, str(out / 'cond_scratch.pth'))
    results['scratch'] = evaluate_model(model_sc, real_vl, 'conditioned', args.window)

    # Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    print(f'\n  Persistence:   MAE={p_mae:.2f}  RMSE={p_rmse:.2f} mg/dL')
    if 'zero_shot' in results:
        zs = results['zero_shot']
        print(f'  Zero-shot:     MAE={zs["mae_mgdl"]:.2f}  RMSE={zs["rmse_mgdl"]:.2f} mg/dL')
    ft = results['transfer']
    sc = results['scratch']
    print(f'  Transfer:      MAE={ft["mae_mgdl"]:.2f}  RMSE={ft["rmse_mgdl"]:.2f} mg/dL')
    print(f'  From scratch:  MAE={sc["mae_mgdl"]:.2f}  RMSE={sc["rmse_mgdl"]:.2f} mg/dL')

    delta = sc['mae_mgdl'] - ft['mae_mgdl']
    if delta > 0:
        print(f'\n  Transfer wins by {delta:.2f} mg/dL MAE')
    else:
        print(f'\n  Scratch wins by {-delta:.2f} mg/dL MAE')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp006_cond_transfer_results.json'))
    return results


def _train_conditioned(model, train_ds, val_ds, lr, epochs, patience,
                       save_path, label, batch=32, weight_decay=1e-5, device=None):
    """Train a ConditionedTransformer with standard loop. Returns (best_val, epochs_run)."""
    device = device if device is not None else _DEFAULT_DEVICE
    model.to(device)
    use_pin = device.type == 'cuda'
    train_ld = DataLoader(train_ds, batch_size=batch, shuffle=True, pin_memory=use_pin)
    val_ld = DataLoader(val_ds, batch_size=batch, pin_memory=use_pin)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    for ep in range(epochs):
        model.train()
        total = 0; n = 0
        for batch_data in train_ld:
            batch_data = batch_to_device(batch_data, device)
            (h, a), t = batch_data
            opt.zero_grad()
            pred = model(h, a)
            loss = crit(pred, t)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += loss.item() * h.size(0); n += h.size(0)
        tl = total / n

        model.eval()
        total_v = 0; nv = 0
        with torch.no_grad():
            for batch_data in val_ld:
                batch_data = batch_to_device(batch_data, device)
                (h, a), t = batch_data
                pred = model(h, a)
                total_v += crit(pred, t).item() * h.size(0); nv += h.size(0)
        vl = total_v / nv
        sched.step(vl)

        if vl < best:
            best = vl; stale = 0
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save({'epoch': ep, 'model_state': model.state_dict(),
                        'val_loss': vl, 'label': label}, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] Epoch {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    return best, ep + 1


def _evaluate_residual_model(model, val_windows_residual, physics_pred_val, val_windows_orig):
    """Evaluate AE on residual data and convert back to glucose MAE.

    The AE reconstructs residual windows. We add physics prediction back
    to get final glucose, then compare to actual glucose.
    """
    from .schema import IDX_GLUCOSE, NORMALIZATION_SCALES
    glucose_scale = NORMALIZATION_SCALES['glucose']

    model.eval()
    device = next(model.parameters()).device
    all_pred_glucose = []
    all_actual_glucose = []

    ds = torch.utils.data.TensorDataset(
        torch.FloatTensor(val_windows_residual),
        torch.FloatTensor(val_windows_residual))
    loader = DataLoader(ds, batch_size=64)

    idx = 0
    with torch.no_grad():
        for batch_in, _ in loader:
            batch_in = batch_in.to(device, non_blocking=True)
            recon = model(batch_in)  # (B, T, 8)
            B = recon.shape[0]

            # Extract reconstructed residual (channel 0)
            residual_recon = recon[:, :, 0].cpu().numpy()  # (B, T) normalized

            for b in range(B):
                i = idx + b
                if i >= len(physics_pred_val):
                    break
                # Convert: physics_pred (mg/dL) + residual * RESIDUAL_SCALE
                pred_glucose = residual_to_glucose(residual_recon[b], physics_pred_val[i])
                actual_glucose = val_windows_orig[i, :, IDX_GLUCOSE] * glucose_scale
                all_pred_glucose.append(pred_glucose)
                all_actual_glucose.append(actual_glucose)
            idx += B

    all_pred = np.concatenate(all_pred_glucose)
    all_actual = np.concatenate(all_actual_glucose)
    mae = float(np.mean(np.abs(all_pred - all_actual)))
    rmse = float(np.sqrt(np.mean((all_pred - all_actual) ** 2)))
    return {'mae_mgdl': round(mae, 2), 'rmse_mgdl': round(rmse, 2)}


def _evaluate_physics_only(physics_pred_raw, val_windows_orig):
    """Evaluate physics-only prediction (no ML) against actual glucose."""
    from .schema import IDX_GLUCOSE, NORMALIZATION_SCALES
    glucose_scale = NORMALIZATION_SCALES['glucose']

    all_pred = []
    all_actual = []
    for i in range(len(physics_pred_raw)):
        actual = val_windows_orig[i, :, IDX_GLUCOSE] * glucose_scale
        all_pred.append(physics_pred_raw[i])
        all_actual.append(actual)

    all_pred = np.concatenate(all_pred)
    all_actual = np.concatenate(all_actual)
    mae = float(np.mean(np.abs(all_pred - all_actual)))
    rmse = float(np.sqrt(np.mean((all_pred - all_actual) ** 2)))
    return {'mae_mgdl': round(mae, 2), 'rmse_mgdl': round(rmse, 2)}


def run_residual(args):
    """EXP-005: Physics-ML Residual Training.

    Train AE on residual = actual_glucose - physics_predicted.
    Compare: physics-only, raw AE, residual AE (physics + ML).
    """
    print('=' * 60)
    print('EXP-005: Physics-ML Residual Training')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-005', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load Nightscout profile for therapy settings
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0  # defaults
    if os.path.exists(profile_path):
        import json as jlib
        with open(profile_path) as f:
            profiles = jlib.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'\n  Patient params: ISF={isf} mg/dL/U, CR={cr} g/U')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Step 1: Load raw data and get normalized windows
    print('\n--- Step 1: Load real data ---')
    from .real_data_adapter import load_nightscout_to_dataset, split_into_windows
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)

    # Get the raw numpy windows for physics computation
    train_windows = real_t.vectors.numpy()  # (N_train, T, 8)
    val_windows = real_v.vectors.numpy()    # (N_val, T, 8)
    results['samples'] = {'train': len(train_windows), 'val': len(val_windows)}

    # Step 2: Compute physics predictions and residuals
    print('\n--- Step 2: Compute physics predictions ---')
    train_residual, train_physics, train_stats = compute_residual_windows(
        train_windows, isf=isf, cr=cr)
    val_residual, val_physics, val_stats = compute_residual_windows(
        val_windows, isf=isf, cr=cr)

    print(f'  Residual stats (train): mean={train_stats["mean"]:.1f}, '
          f'std={train_stats["std"]:.1f}, range=[{train_stats["min"]:.0f}, '
          f'{train_stats["max"]:.0f}] mg/dL')
    print(f'  Residual stats (val):   mean={val_stats["mean"]:.1f}, '
          f'std={val_stats["std"]:.1f}, range=[{val_stats["min"]:.0f}, '
          f'{val_stats["max"]:.0f}] mg/dL')
    results['residual_stats'] = {'train': train_stats, 'val': val_stats}

    # Step 3: Physics-only baseline
    print('\n--- Step 3: Physics-only baseline ---')
    physics_metrics = _evaluate_physics_only(val_physics, val_windows)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f} '
          f'RMSE={physics_metrics["rmse_mgdl"]:.2f} mg/dL')

    # Step 4: Train AE on residual data
    print('\n--- Step 4: Train AE on residuals ---')
    from .encoder import CGMDataset
    residual_train_ds = CGMDataset(train_residual, task='reconstruct',
                                    window_size=args.window)
    residual_val_ds = CGMDataset(val_residual, task='reconstruct',
                                  window_size=args.window)
    residual_train_ld = DataLoader(residual_train_ds, batch_size=args.batch, shuffle=True)
    residual_val_ld = DataLoader(residual_val_ds, batch_size=args.batch)

    model_residual = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    train_loop(model_residual, residual_train_ld, residual_val_ld,
               lr=1e-3, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_residual.pth'), label='residual')

    # Step 5: Train AE on raw data (baseline, same setup as EXP-003 scratch)
    print('\n--- Step 5: Train AE on raw data (baseline) ---')
    raw_train_ld = DataLoader(real_t, batch_size=args.batch, shuffle=True)
    raw_val_ld = DataLoader(real_v, batch_size=args.batch)

    model_raw = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    train_loop(model_raw, raw_train_ld, raw_val_ld,
               lr=1e-3, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_raw.pth'), label='raw')

    # Step 6: Evaluate all approaches
    print('\n--- Step 6: Final evaluation ---')

    # Load best checkpoints
    load_best(model_residual, str(out / 'ae_residual.pth'))
    load_best(model_raw, str(out / 'ae_raw.pth'))

    # Residual AE: reconstruct residuals → add physics → glucose
    residual_metrics = _evaluate_residual_model(
        model_residual, val_residual, val_physics, val_windows)
    results['residual_ae'] = residual_metrics

    # Raw AE: evaluate normally
    results['raw_ae'] = evaluate_model(model_raw, raw_val_ld, 'ae', args.window)

    # Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Print summary
    print(f'\n  Persistence:     MAE={p_mae:.2f}  RMSE={p_rmse:.2f} mg/dL')
    print(f'  Physics-only:    MAE={physics_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={physics_metrics["rmse_mgdl"]:.2f} mg/dL')
    print(f'  Raw AE:          MAE={results["raw_ae"]["mae_mgdl"]:.2f}  '
          f'RMSE={results["raw_ae"]["rmse_mgdl"]:.2f} mg/dL')
    print(f'  Residual AE:     MAE={residual_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={residual_metrics["rmse_mgdl"]:.2f} mg/dL')

    # Which is best?
    best_name = min(
        [('Physics-only', physics_metrics['mae_mgdl']),
         ('Raw AE', results['raw_ae']['mae_mgdl']),
         ('Residual AE', residual_metrics['mae_mgdl'])],
        key=lambda x: x[1])
    print(f'\n  Best: {best_name[0]} ({best_name[1]:.2f} mg/dL MAE)')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp005_residual_results.json'))
    return results


def run_physics_comparison(args):
    """EXP-007: Physics Level Comparison — simple vs enhanced vs UVA/Padova.

    Trains residual AE with three physics backends, same architecture.
    Tests whether more sophisticated physics → better residuals → better ML.
    """
    print('=' * 60)
    print('EXP-007: Physics Level Comparison')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-007', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load profile
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'\n  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Step 1: Load data
    print('\n--- Step 1: Load real data ---')
    from .real_data_adapter import load_nightscout_to_dataset as _load_ns
    real_t, real_v = _load_ns(args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}

    # Step 2: Compute residuals with each physics level
    levels = {}

    # 2a. Simple (ΔIOB×ISF only)
    print('\n--- Step 2a: Simple physics residuals ---')
    s_tr, s_tp, s_ts = compute_residual_windows(train_np, isf=isf, cr=cr, level='simple')
    s_vr, s_vp, s_vs = compute_residual_windows(val_np, isf=isf, cr=cr, level='simple')
    levels['simple'] = {'train_res': s_tr, 'train_phys': s_tp, 'val_res': s_vr, 'val_phys': s_vp}
    print(f'  Residual std: {s_ts["std"]:.1f} mg/dL')
    results['simple_stats'] = s_vs

    # 2b. Enhanced (+ liver + circadian)
    print('\n--- Step 2b: Enhanced physics residuals ---')
    e_tr, e_tp, e_ts = compute_residual_windows(train_np, isf=isf, cr=cr, level='enhanced')
    e_vr, e_vp, e_vs = compute_residual_windows(val_np, isf=isf, cr=cr, level='enhanced')
    levels['enhanced'] = {'train_res': e_tr, 'train_phys': e_tp, 'val_res': e_vr, 'val_phys': e_vp}
    print(f'  Residual std: {e_ts["std"]:.1f} mg/dL')
    results['enhanced_stats'] = e_vs

    # 2c. UVA/Padova (from pre-computed replay)
    uva_path = getattr(args, 'uva_predictions', None)
    if uva_path is None:
        uva_path = str(out / 'uva_predictions.json')
    has_uva = os.path.exists(uva_path)

    if has_uva:
        print(f'\n--- Step 2c: UVA/Padova residuals ({uva_path}) ---')
        uva_bg_dict, uva_meta = load_uva_predictions(uva_path)
        grid_ts = load_nightscout_grid_timestamps(args.real_data)
        uva_grid = align_uva_to_grid(uva_bg_dict, grid_ts)
        print(f'  UVA grid: {len(uva_grid)} points, '
              f'{np.sum(~np.isnan(uva_grid))}/{len(uva_grid)} matched')

        # Compute per-window differential residuals (train + val same grid)
        all_np = np.concatenate([train_np, val_np], axis=0)
        u_ar, u_ap, u_as = compute_residual_windows_uva(all_np, uva_grid)
        n_train = len(train_np)
        u_tr = u_ar[:n_train]
        u_tp = u_ap[:n_train]
        u_vr = u_ar[n_train:]
        u_vp = u_ap[n_train:]
        # Recompute val-only stats
        val_glucose = val_np[:, :, 0] * 400.0
        u_val_residuals = val_glucose - u_vp
        u_vs = {
            'mean': float(np.mean(u_val_residuals)),
            'std': float(np.std(u_val_residuals)),
            'level': 'uva',
        }
        levels['uva'] = {'train_res': u_tr, 'train_phys': u_tp, 'val_res': u_vr, 'val_phys': u_vp}
        print(f'  UVA differential residual std: {u_vs["std"]:.1f} mg/dL')
        results['uva_stats'] = u_vs
    else:
        print(f'\n  No UVA predictions at {uva_path} — skipping UVA level')

    # Step 3: Physics-only baselines
    print('\n--- Step 3: Physics-only baselines ---')
    for name, data in levels.items():
        metrics = _evaluate_physics_only(data['val_phys'], val_np)
        results[f'{name}_physics_only'] = metrics
        print(f'  {name:10s}: MAE={metrics["mae_mgdl"]:.2f}  RMSE={metrics["rmse_mgdl"]:.2f}')

    # Step 4: Train residual AE for each level
    from .encoder import CGMDataset
    for name, data in levels.items():
        print(f'\n--- Step 4: Train residual AE ({name}) ---')
        tr_ds = CGMDataset(data['train_res'], task='reconstruct', window_size=args.window)
        vr_ds = CGMDataset(data['val_res'], task='reconstruct', window_size=args.window)
        tr_ld = DataLoader(tr_ds, batch_size=args.batch, shuffle=True)
        vr_ld = DataLoader(vr_ds, batch_size=args.batch)

        model = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        ckpt = str(out / f'ae_residual_{name}.pth')
        train_loop(model, tr_ld, vr_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt, label=f'residual-{name}')

        # Evaluate
        load_best(model, ckpt)
        metrics = _evaluate_residual_model(model, data['val_res'], data['val_phys'], val_np)
        results[f'{name}_residual_ae'] = metrics
        print(f'  {name} Residual AE: MAE={metrics["mae_mgdl"]:.2f}  '
              f'RMSE={metrics["rmse_mgdl"]:.2f}')

    # Step 5: Persistence baseline
    print('\n--- Step 5: Persistence baseline ---')
    _, rv_2x = _load_ns(args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Physics Level Comparison')
    print('=' * 60)
    print(f'  {"Approach":<30s}  {"MAE mg/dL":>10s}  {"RMSE mg/dL":>10s}')
    print(f'  {"-"*30}  {"-"*10}  {"-"*10}')
    print(f'  {"Persistence":<30s}  {p_mae:>10.2f}  {p_rmse:>10.2f}')
    for name in levels:
        po = results[f'{name}_physics_only']
        ra = results[f'{name}_residual_ae']
        print(f'  {name + " physics-only":<30s}  {po["mae_mgdl"]:>10.2f}  {po["rmse_mgdl"]:>10.2f}')
        print(f'  {name + " residual AE":<30s}  {ra["mae_mgdl"]:>10.2f}  {ra["rmse_mgdl"]:>10.2f}')
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp007_physics_comparison.json'))
    return results


def run_residual_transfer(args):
    """EXP-009: Residual Transfer Learning — synth pretrain + real finetune on residuals.

    Combines the two best techniques: physics-ML residual (EXP-005/007) and
    sim-to-real transfer (EXP-003). Uses enhanced physics for both stages.
    """
    print('=' * 60)
    print('EXP-009: Residual Transfer Learning')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-009', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load patient profile for physics model
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Step 1: Load synthetic data and compute enhanced residuals
    print('\n--- Step 1: Synthetic → enhanced residuals ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)

    has_synthetic = syn_t is not None and len(syn_t) > 0
    results['has_synthetic'] = has_synthetic

    if has_synthetic:
        syn_train_np = syn_t.vectors.numpy()
        syn_val_np = syn_v.vectors.numpy()
        print(f'  Synthetic: {len(syn_train_np)} train, {len(syn_val_np)} val')

        # For synthetic vectors, use their profile ISF/CR if available
        # (different patients have different params — use mean or per-window)
        # Simple: use real patient's ISF/CR as approximation
        syn_tr_res, syn_tr_phys, syn_stats = compute_residual_windows(
            syn_train_np, isf=isf, cr=cr, level='enhanced')
        syn_vr_res, syn_vr_phys, _ = compute_residual_windows(
            syn_val_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Synthetic residual std: {syn_stats["std"]:.1f} mg/dL')
        results['synthetic_residual_stats'] = syn_stats

        # Pre-train AE on synthetic residuals
        print('\n--- Step 2: Pre-train on synthetic residuals ---')
        from .encoder import CGMDataset
        syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=args.window)
        syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=args.window)
        model_synth = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        train_loop(model_synth,
                   DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True),
                   DataLoader(syn_res_val_ds, batch_size=args.batch),
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=str(out / 'ae_residual_synth.pth'), label='synth-residual')
    else:
        print('  WARNING: No synthetic vectors found.')

    # Step 3: Load real data → enhanced residuals
    print('\n--- Step 3: Real data → enhanced residuals ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['real_samples'] = {'train': len(train_np), 'val': len(val_np)}

    real_tr_res, real_tr_phys, real_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    real_vr_res, real_vr_phys, _ = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Real residual std: {real_stats["std"]:.1f} mg/dL')
    results['real_residual_stats'] = real_stats

    from .encoder import CGMDataset
    real_res_train_ds = CGMDataset(real_tr_res, task='reconstruct', window_size=args.window)
    real_res_val_ds = CGMDataset(real_vr_res, task='reconstruct', window_size=args.window)
    real_res_train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
    real_res_val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

    # Step 4: Zero-shot (synthetic residual model → real residuals)
    if has_synthetic:
        print('\n--- Step 4: Zero-shot evaluation ---')
        model_zs = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        load_best(model_zs, str(out / 'ae_residual_synth.pth'))
        zs_metrics = _evaluate_residual_model(model_zs, real_vr_res, real_vr_phys, val_np)
        results['zero_shot'] = zs_metrics
        print(f'  Zero-shot: MAE={zs_metrics["mae_mgdl"]:.2f}  RMSE={zs_metrics["rmse_mgdl"]:.2f}')

    # Step 5: Fine-tune (synth pretrained → real residuals)
    print('\n--- Step 5: Fine-tune on real residuals ---')
    model_ft = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    if has_synthetic:
        load_best(model_ft, str(out / 'ae_residual_synth.pth'))
    train_loop(model_ft, real_res_train_ld, real_res_val_ld,
               lr=5e-4, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_residual_transfer.pth'), label='residual-transfer')

    # Step 6: From-scratch on real residuals (baseline = EXP-007 enhanced)
    print('\n--- Step 6: From-scratch on real residuals ---')
    model_sc = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    train_loop(model_sc, real_res_train_ld, real_res_val_ld,
               lr=1e-3, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_residual_scratch.pth'), label='residual-scratch')

    # Step 7: Evaluate all
    print('\n--- Step 7: Final evaluation ---')
    load_best(model_ft, str(out / 'ae_residual_transfer.pth'))
    load_best(model_sc, str(out / 'ae_residual_scratch.pth'))

    transfer_metrics = _evaluate_residual_model(model_ft, real_vr_res, real_vr_phys, val_np)
    scratch_metrics = _evaluate_residual_model(model_sc, real_vr_res, real_vr_phys, val_np)
    physics_metrics = _evaluate_physics_only(real_vr_phys, val_np)

    results['transfer'] = transfer_metrics
    results['scratch'] = scratch_metrics
    results['physics_only'] = physics_metrics

    # Persistence
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Residual Transfer Learning')
    print('=' * 60)
    print(f'  Persistence:           MAE={p_mae:.2f}  RMSE={p_rmse:.2f}')
    print(f'  Physics-only:          MAE={physics_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={physics_metrics["rmse_mgdl"]:.2f}')
    if has_synthetic:
        print(f'  Zero-shot (synth→real): MAE={zs_metrics["mae_mgdl"]:.2f}  '
              f'RMSE={zs_metrics["rmse_mgdl"]:.2f}')
    print(f'  Transfer (synth→real): MAE={transfer_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={transfer_metrics["rmse_mgdl"]:.2f}')
    print(f'  Scratch:               MAE={scratch_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={scratch_metrics["rmse_mgdl"]:.2f}')

    improvement = (scratch_metrics['mae_mgdl'] - transfer_metrics['mae_mgdl']) / scratch_metrics['mae_mgdl'] * 100
    print(f'\n  Transfer vs scratch: {"↓" if improvement > 0 else "↑"}{abs(improvement):.1f}%')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp009_residual_transfer.json'))
    return results


def run_longer_horizons(args):
    """EXP-010: Longer Forecast Horizons — 1hr, 2hr, 3hr windows.

    Tests whether enhanced residual AE degrades at longer forecast horizons.
    Physics model may drift more, but ML correction should compensate.
    """
    print('=' * 60)
    print('EXP-010: Longer Forecast Horizons')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-010', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load profile
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    horizons = [12, 24, 36]  # 1hr, 2hr, 3hr
    horizon_results = {}

    from .encoder import CGMDataset

    for window in horizons:
        label = f'{window * 5}min ({window} steps)'
        print(f'\n{"─" * 50}')
        print(f'  Horizon: {label}')
        print(f'{"─" * 50}')

        # Load data at this window size
        real_t, real_v = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window)
        if real_t is None or len(real_t) == 0:
            print(f'  No data for window={window}, skipping')
            continue

        train_np = real_t.vectors.numpy()
        val_np = real_v.vectors.numpy()
        print(f'  Windows: {len(train_np)} train, {len(val_np)} val')

        # Enhanced residuals
        tr_res, tr_phys, tr_stats = compute_residual_windows(
            train_np, isf=isf, cr=cr, level='enhanced')
        vr_res, vr_phys, vr_stats = compute_residual_windows(
            val_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Residual std: {vr_stats["std"]:.1f} mg/dL')

        # Physics-only baseline
        physics_metrics = _evaluate_physics_only(vr_phys, val_np)
        print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

        # Train residual AE (adapt d_model for longer sequences)
        res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
        res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=window)
        res_train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True)
        res_val_ld = DataLoader(res_val_ds, batch_size=args.batch)

        model = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        ckpt = str(out / f'ae_residual_w{window}.pth')
        train_loop(model, res_train_ld, res_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt, label=f'residual-w{window}')

        load_best(model, ckpt)
        ae_metrics = _evaluate_residual_model(model, vr_res, vr_phys, val_np)

        # Persistence
        _, rv_2x = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window * 2)
        p_mae, p_rmse = persistence_baseline(rv_2x, window)

        horizon_results[window] = {
            'window_steps': window,
            'window_minutes': window * 5,
            'samples': {'train': len(train_np), 'val': len(val_np)},
            'residual_stats': vr_stats,
            'physics_only': physics_metrics,
            'residual_ae': ae_metrics,
            'persistence': {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)},
        }
        print(f'  Residual AE: MAE={ae_metrics["mae_mgdl"]:.2f}  RMSE={ae_metrics["rmse_mgdl"]:.2f}')

    results['horizons'] = horizon_results
    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Longer Forecast Horizons')
    print('=' * 60)
    print(f'  {"Window":<15s}  {"Persist MAE":>12s}  {"Physics MAE":>12s}  {"Residual AE":>12s}')
    print(f'  {"-"*15}  {"-"*12}  {"-"*12}  {"-"*12}')
    for w, hr in sorted(horizon_results.items()):
        wlabel = f'{w*5}min ({w} steps)'
        print(f'  {wlabel:<15s}  {hr["persistence"]["mae_mgdl"]:>12.2f}  '
              f'{hr["physics_only"]["mae_mgdl"]:>12.2f}  '
              f'{hr["residual_ae"]["mae_mgdl"]:>12.2f}')
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp010_longer_horizons.json'))
    return results


def _build_feature_grid(data_path):
    """Build the full 5-min feature grid from Nightscout data, returning
    both the normalized features array and the grid DatetimeIndex.

    This duplicates the grid-building logic from load_nightscout_to_dataset
    but returns the raw grid (no windowing) for flexible splitting.
    """
    import pandas as pd
    from .schema import NORMALIZATION_SCALES
    SCALE = NORMALIZATION_SCALES
    data_dir = Path(data_path)

    # 1. CGM entries → 5-min grid
    with open(data_dir / 'entries.json') as f:
        entries = json.load(f)
    cgm_times, cgm_values = [], []
    for e in entries:
        if e.get('type') != 'sgv' or 'sgv' not in e:
            continue
        if 'date' in e:
            ts = pd.Timestamp(e['date'], unit='ms', tz='UTC')
        elif 'dateString' in e:
            ts = pd.Timestamp(e['dateString'])
        else:
            continue
        cgm_times.append(ts)
        cgm_values.append(float(e['sgv']))

    cgm_df = pd.DataFrame({'glucose': cgm_values}, index=pd.DatetimeIndex(cgm_times))
    cgm_df = cgm_df.sort_index()
    cgm_df = cgm_df[~cgm_df.index.duplicated(keep='first')]
    grid_start = cgm_df.index.min().floor('5min')
    grid_end = cgm_df.index.max().ceil('5min')
    grid = pd.date_range(grid_start, grid_end, freq='5min')
    df = pd.DataFrame(index=grid)
    cgm_df.index = cgm_df.index.round('5min')
    cgm_grouped = cgm_df.groupby(level=0).mean()
    df['glucose'] = cgm_grouped['glucose']
    df['glucose'] = df['glucose'].interpolate(limit=6)

    # 2. DeviceStatus → IOB/COB
    with open(data_dir / 'devicestatus.json') as f:
        devicestatus = json.load(f)
    ds_times, ds_iob, ds_cob = [], [], []
    for ds in devicestatus:
        loop = ds.get('loop', {})
        iob_data = loop.get('iob', {})
        if not iob_data or 'iob' not in iob_data:
            continue
        ts = pd.Timestamp(ds.get('created_at'))
        ds_times.append(ts)
        ds_iob.append(float(iob_data['iob']))
        ds_cob.append(float(loop.get('cob', {}).get('cob', 0)))
    ds_df = pd.DataFrame({'iob': ds_iob, 'cob': ds_cob},
                          index=pd.DatetimeIndex(ds_times))
    ds_df = ds_df.sort_index()
    ds_df = ds_df[~ds_df.index.duplicated(keep='first')]
    ds_df.index = ds_df.index.round('5min')
    ds_grouped = ds_df.groupby(level=0).mean()
    df['iob'] = ds_grouped['iob']
    df['cob'] = ds_grouped['cob']
    df['iob'] = df['iob'].interpolate(limit=6).fillna(0)
    df['cob'] = df['cob'].interpolate(limit=6).fillna(0)

    # 3. Treatments → bolus, carbs, temp basal
    with open(data_dir / 'treatments.json') as f:
        treatments = json.load(f)
    df['bolus'] = 0.0
    df['carbs'] = 0.0
    df['temp_rate'] = np.nan
    for t in treatments:
        if 'created_at' not in t:
            continue
        ts = pd.Timestamp(t['created_at']).round('5min')
        if ts not in df.index:
            continue
        etype = t.get('eventType', '')
        if etype == 'Bolus' or 'Bolus' in etype:
            df.at[ts, 'bolus'] += float(t.get('insulin', 0) or 0)
        if float(t.get('carbs', 0) or 0) > 0:
            df.at[ts, 'carbs'] += float(t['carbs'])
        if etype in ('Temp Basal', 'TempBasal'):
            df.at[ts, 'temp_rate'] = float(t.get('rate', 0) or 0)

    # 4. Profile → scheduled basal
    with open(data_dir / 'profile.json') as f:
        profiles = json.load(f)
    basal_schedule = []
    if profiles:
        store = profiles[0].get('store', {})
        default = store.get('Default', {})
        basal_schedule = default.get('basal', [])
    scheduled = np.zeros(len(df))
    for i, ts in enumerate(df.index):
        secs = ts.hour * 3600 + ts.minute * 60 + ts.second
        rate = basal_schedule[0]['value'] if basal_schedule else 0
        for seg in basal_schedule:
            if seg.get('timeAsSeconds', 0) <= secs:
                rate = seg['value']
        scheduled[i] = rate
    df['temp_rate'] = df['temp_rate'].ffill()
    df['temp_rate'] = df['temp_rate'].fillna(pd.Series(scheduled, index=df.index))
    df['net_basal'] = df['temp_rate'].values - scheduled

    # 5. Build feature array
    hours = df.index.hour + df.index.minute / 60.0
    time_sin = np.sin(2 * np.pi * hours / 24.0)
    time_cos = np.cos(2 * np.pi * hours / 24.0)
    features = np.column_stack([
        df['glucose'].values / SCALE['glucose'],
        df['iob'].values / SCALE['iob'],
        df['cob'].values / SCALE['cob'],
        df['net_basal'].values / SCALE['net_basal'],
        df['bolus'].values / SCALE['bolus'],
        df['carbs'].values / SCALE['carbs'],
        time_sin,
        time_cos,
    ]).astype(np.float32)

    return features, df.index


def run_walkforward(args):
    """EXP-011: Walk-Forward Temporal Validation.

    Strict temporal split with NO window overlap between train and test:
    - Train: days 1-60 (first ~70% of data)
    - Test: days 61-85 (last ~30%)
    - Gap: optionally skip 1 day between train/test to prevent leakage

    This gives an honest estimate of how well the model predicts on
    truly unseen future data, unlike the overlapping window split.
    """
    print('=' * 60)
    print('EXP-011: Walk-Forward Temporal Validation')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-011', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load profile
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'  Patient: ISF={isf}, CR={cr}')

    # Step 1: Build full feature grid
    print('\n--- Step 1: Build feature grid ---')
    features, grid_index = _build_feature_grid(args.real_data)
    total_days = (grid_index[-1] - grid_index[0]).days
    print(f'  Grid: {len(features)} points, {total_days} days '
          f'({grid_index[0].strftime("%Y-%m-%d")} to {grid_index[-1].strftime("%Y-%m-%d")})')

    from .real_data_adapter import split_into_windows
    from .encoder import CGMDataset
    window = args.window

    # Define temporal splits
    splits = [
        {'name': 'walkforward_70_30', 'train_frac': 0.70, 'gap_days': 0},
        {'name': 'walkforward_70_30_gap1d', 'train_frac': 0.70, 'gap_days': 1},
        {'name': 'walkforward_80_20', 'train_frac': 0.80, 'gap_days': 0},
    ]

    # Also run the original overlapping split for comparison
    print('\n--- Step 2: Original overlapping split (reference) ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=window)
    train_np_orig = real_t.vectors.numpy()
    val_np_orig = real_v.vectors.numpy()
    tr_res, tr_phys, _ = compute_residual_windows(train_np_orig, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, _ = compute_residual_windows(val_np_orig, isf=isf, cr=cr, level='enhanced')

    # Train on original split
    res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
    res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=window)
    model_orig = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
    train_loop(model_orig,
               DataLoader(res_train_ds, batch_size=args.batch, shuffle=True),
               DataLoader(res_val_ds, batch_size=args.batch),
               lr=1e-3, epochs=args.epochs, patience=args.patience,
               save_path=str(out / 'ae_wf_original.pth'), label='original-split')
    load_best(model_orig, str(out / 'ae_wf_original.pth'))
    orig_metrics = _evaluate_residual_model(model_orig, vr_res, vr_phys, val_np_orig)
    orig_physics = _evaluate_physics_only(vr_phys, val_np_orig)
    results['original_split'] = {
        'train_windows': len(train_np_orig),
        'val_windows': len(val_np_orig),
        'residual_ae': orig_metrics,
        'physics_only': orig_physics,
    }
    print(f'  Original: {len(train_np_orig)} train, {len(val_np_orig)} val → '
          f'AE MAE={orig_metrics["mae_mgdl"]:.2f}')

    # Step 3: Walk-forward splits
    for split_cfg in splits:
        name = split_cfg['name']
        train_frac = split_cfg['train_frac']
        gap_days = split_cfg['gap_days']

        print(f'\n--- Step 3: {name} (train={train_frac*100:.0f}%, gap={gap_days}d) ---')

        # Hard temporal split on the grid
        split_point = int(len(features) * train_frac)
        gap_points = gap_days * 288  # 288 = 24*60/5 points per day

        train_grid = features[:split_point]
        test_grid = features[split_point + gap_points:]

        split_date = grid_index[split_point].strftime('%Y-%m-%d')
        train_days = (grid_index[split_point] - grid_index[0]).days
        test_days = (grid_index[-1] - grid_index[min(split_point + gap_points, len(grid_index)-1)]).days
        print(f'  Split at {split_date}: {train_days}d train, {test_days}d test'
              f'{f", {gap_days}d gap" if gap_days else ""}')

        # Window each side independently
        train_wins = split_into_windows(train_grid, window_size=window)
        test_wins = split_into_windows(test_grid, window_size=window)

        if not train_wins or not test_wins:
            print(f'  Skipping {name}: insufficient windows')
            continue

        train_np = np.array(train_wins)
        test_np = np.array(test_wins)
        print(f'  Windows: {len(train_np)} train, {len(test_np)} test')

        # Compute enhanced residuals
        tr_res, tr_phys, tr_stats = compute_residual_windows(
            train_np, isf=isf, cr=cr, level='enhanced')
        te_res, te_phys, te_stats = compute_residual_windows(
            test_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Train residual std: {tr_stats["std"]:.1f}, Test: {te_stats["std"]:.1f} mg/dL')

        # Train AE on walk-forward train set
        tr_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
        te_ds = CGMDataset(te_res, task='reconstruct', window_size=window)
        tr_ld = DataLoader(tr_ds, batch_size=args.batch, shuffle=True)
        te_ld = DataLoader(te_ds, batch_size=args.batch)

        model = CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2)
        ckpt = str(out / f'ae_wf_{name}.pth')
        train_loop(model, tr_ld, te_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt, label=name)

        load_best(model, ckpt)
        ae_metrics = _evaluate_residual_model(model, te_res, te_phys, test_np)
        physics_metrics = _evaluate_physics_only(te_phys, test_np)

        # Persistence on test set (need 2x windows for persistence)
        test_wins_2x = split_into_windows(test_grid, window_size=window * 2)
        if test_wins_2x:
            test_tensor_2x = torch.tensor(np.array(test_wins_2x), dtype=torch.float32)
            from .evaluate import persistence_baseline as _pb
            te_ds_2x = CGMDataset(test_tensor_2x, task='forecast', window_size=window * 2)
            p_mae, p_rmse = _pb(te_ds_2x, window)
        else:
            p_mae, p_rmse = float('nan'), float('nan')

        results[name] = {
            'train_windows': len(train_np),
            'test_windows': len(test_np),
            'train_days': train_days,
            'test_days': test_days,
            'gap_days': gap_days,
            'residual_ae': ae_metrics,
            'physics_only': physics_metrics,
            'persistence': {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)},
            'residual_stats': {'train_std': tr_stats['std'], 'test_std': te_stats['std']},
        }
        print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')
        print(f'  Residual AE:  MAE={ae_metrics["mae_mgdl"]:.2f}  RMSE={ae_metrics["rmse_mgdl"]:.2f}')
        print(f'  Persistence:  MAE={p_mae:.2f}')

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Walk-Forward Temporal Validation')
    print('=' * 60)
    print(f'  {"Split":<30s}  {"Persist":>8s}  {"Physics":>8s}  {"Res AE":>8s}')
    print(f'  {"-"*30}  {"-"*8}  {"-"*8}  {"-"*8}')
    print(f'  {"original (overlapping)":<30s}  '
          f'{"—":>8s}  '
          f'{orig_physics["mae_mgdl"]:>8.2f}  '
          f'{orig_metrics["mae_mgdl"]:>8.2f}')
    for split_cfg in splits:
        name = split_cfg['name']
        if name in results:
            r = results[name]
            print(f'  {name:<30s}  '
                  f'{r["persistence"]["mae_mgdl"]:>8.2f}  '
                  f'{r["physics_only"]["mae_mgdl"]:>8.2f}  '
                  f'{r["residual_ae"]["mae_mgdl"]:>8.2f}')
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp011_walkforward.json'))
    return results


def _evaluate_residual_future_only(model, val_windows_residual, physics_pred_val,
                                   val_windows_orig, history_steps=None,
                                   interval_min=5):
    """Evaluate AE on residual data using **causal attention** (future-only forecast).

    Unlike _evaluate_residual_model which measures reconstruction MAE across
    all timesteps, this function:
    1. Runs the model with causal=True (each position can only attend to past)
    2. Measures MAE only on the *future* timesteps (after history_steps)

    This is the clinically relevant metric: given observed history, how well
    does the model predict upcoming glucose values?

    Returns:
        dict with 'mae_mgdl', 'rmse_mgdl', and 'per_horizon' breakdown
    """
    from .schema import IDX_GLUCOSE, NORMALIZATION_SCALES
    glucose_scale = NORMALIZATION_SCALES['glucose']

    T = val_windows_residual.shape[1]
    if history_steps is None:
        history_steps = T // 2  # default: first half is history

    model.eval()
    all_future_pred = []
    all_future_actual = []
    # Per-horizon collection: {step_offset: [abs_errors]}
    horizon_errors = {}

    ds = torch.utils.data.TensorDataset(
        torch.FloatTensor(val_windows_residual),
        torch.FloatTensor(val_windows_residual))
    loader = DataLoader(ds, batch_size=64)

    idx = 0
    with torch.no_grad():
        for batch_in, _ in loader:
            # Run with causal mask — position t can only attend to 0..t
            batch_in = batch_in.to(_DEFAULT_DEVICE, non_blocking=True)
            recon = model(batch_in, causal=True)  # (B, T, 8)
            B = recon.shape[0]

            residual_recon = recon[:, :, 0].cpu().numpy()  # (B, T) normalized

            for b in range(B):
                i = idx + b
                if i >= len(physics_pred_val):
                    break

                # Future-only: steps history_steps .. T-1
                pred_residual = residual_recon[b, history_steps:]
                pred_glucose = residual_to_glucose(pred_residual, physics_pred_val[i, history_steps:])
                actual_glucose = val_windows_orig[i, history_steps:, IDX_GLUCOSE] * glucose_scale

                all_future_pred.append(pred_glucose)
                all_future_actual.append(actual_glucose)

                # Per-horizon errors
                abs_errs = np.abs(pred_glucose - actual_glucose)
                for step in range(len(abs_errs)):
                    horizon_errors.setdefault(step, []).append(abs_errs[step])

            idx += B

    all_pred = np.concatenate(all_future_pred)
    all_actual = np.concatenate(all_future_actual)
    mae = float(np.mean(np.abs(all_pred - all_actual)))
    rmse = float(np.sqrt(np.mean((all_pred - all_actual) ** 2)))

    # Per-horizon breakdown
    per_horizon = {}
    for step in sorted(horizon_errors.keys()):
        minutes = (step + 1) * interval_min
        label = f'{minutes}min'
        per_horizon[label] = round(float(np.mean(horizon_errors[step])), 2)

    return {
        'mae_mgdl': round(mae, 2),
        'rmse_mgdl': round(rmse, 2),
        'history_steps': history_steps,
        'future_steps': T - history_steps,
        'per_horizon': per_horizon,
    }


def run_grouped_benchmark(args):
    """EXP-012a: GroupedEncoder Benchmark + Future-Only Forecast Metric.

    Compares CGMGroupedEncoder vs CGMTransformerAE on enhanced physics residuals.
    Both models have ~68K params and identical training setup. Reports:
    1. Reconstruction MAE (all timesteps — existing metric)
    2. Future-only MAE (causal attention, second-half only — clinically relevant)
    3. Per-horizon breakdown (5min, 10min, 15min, 20min, 25min, 30min)
    """
    print('=' * 60)
    print('EXP-012a: GroupedEncoder Benchmark + Future-Only Forecast')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-012a', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    # Load patient profile
    profile_path = os.path.join(args.real_data, 'profile.json')
    isf, cr = 40.0, 10.0
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            store = profiles[0].get('store', {})
            default = store.get('Default', {})
            sens = default.get('sens', [{}])
            carbratio = default.get('carbratio', [{}])
            if sens and 'value' in sens[0]:
                isf = float(sens[0]['value'])
            if carbratio and 'value' in carbratio[0]:
                cr = float(carbratio[0]['value'])
    print(f'\n  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Step 1: Load real data
    print('\n--- Step 1: Load real data ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Windows: {len(train_np)} train, {len(val_np)} val '
          f'({args.window} steps = {args.window * 5} min)')

    # Step 2: Compute enhanced physics residuals
    print('\n--- Step 2: Enhanced physics residuals ---')
    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, vr_stats = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Residual std: train={tr_stats["std"]:.1f}, val={vr_stats["std"]:.1f} mg/dL')
    results['residual_stats'] = {'train': tr_stats, 'val': vr_stats}

    # Step 3: Physics-only baseline
    print('\n--- Step 3: Physics-only baseline ---')
    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}  '
          f'RMSE={physics_metrics["rmse_mgdl"]:.2f} mg/dL')

    # Step 4: Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence:  MAE={p_mae:.2f}  RMSE={p_rmse:.2f} mg/dL')

    # Step 5: Train and evaluate both architectures
    from .encoder import CGMDataset
    res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)
    res_train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True)
    res_val_ld = DataLoader(res_val_ds, batch_size=args.batch)

    architectures = {
        'ae': {
            'class': CGMTransformerAE,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
        'grouped': {
            'class': CGMGroupedEncoder,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
    }

    for arch_name, arch_cfg in architectures.items():
        print(f'\n--- Step 5: Train {arch_name} on enhanced residuals ---')
        model = arch_cfg['class'](**arch_cfg['kwargs'])
        param_count = sum(p.numel() for p in model.parameters())
        print(f'  {arch_name}: {param_count:,} parameters')

        ckpt = str(out / f'ae_grouped_bench_{arch_name}.pth')
        train_loop(model, res_train_ld, res_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt, label=f'residual-{arch_name}')

        # Load best checkpoint
        load_best(model, ckpt)

        # 5a. Reconstruction MAE (existing metric — all timesteps)
        recon_metrics = _evaluate_residual_model(
            model, vr_res, vr_phys, val_np)
        print(f'  [{arch_name}] Reconstruction: MAE={recon_metrics["mae_mgdl"]:.2f}  '
              f'RMSE={recon_metrics["rmse_mgdl"]:.2f} mg/dL')

        # 5b. Future-only MAE (causal attention — clinically relevant)
        future_metrics = _evaluate_residual_future_only(
            model, vr_res, vr_phys, val_np,
            history_steps=args.window // 2)
        print(f'  [{arch_name}] Future-only (causal): MAE={future_metrics["mae_mgdl"]:.2f}  '
              f'RMSE={future_metrics["rmse_mgdl"]:.2f} mg/dL')
        if future_metrics.get('per_horizon'):
            print(f'  [{arch_name}] Per-horizon:')
            for label, mae in future_metrics['per_horizon'].items():
                print(f'    {label:>6s}: {mae:.2f} mg/dL')

        results[arch_name] = {
            'params': param_count,
            'reconstruction': recon_metrics,
            'future_only': future_metrics,
        }

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — GroupedEncoder Benchmark + Future-Only Forecast')
    print('=' * 60)
    print(f'  {"Metric":<32s}  {"AE":>10s}  {"Grouped":>10s}  {"Winner":>8s}')
    print(f'  {"-"*32}  {"-"*10}  {"-"*10}  {"-"*8}')

    ae_r = results['ae']
    gr_r = results['grouped']

    rows = [
        ('Params', f'{ae_r["params"]:,}', f'{gr_r["params"]:,}', '—'),
        ('Recon MAE (mg/dL)',
         f'{ae_r["reconstruction"]["mae_mgdl"]:.2f}',
         f'{gr_r["reconstruction"]["mae_mgdl"]:.2f}',
         'AE' if ae_r['reconstruction']['mae_mgdl'] <= gr_r['reconstruction']['mae_mgdl'] else 'Grouped'),
        ('Future-only MAE (mg/dL)',
         f'{ae_r["future_only"]["mae_mgdl"]:.2f}',
         f'{gr_r["future_only"]["mae_mgdl"]:.2f}',
         'AE' if ae_r['future_only']['mae_mgdl'] <= gr_r['future_only']['mae_mgdl'] else 'Grouped'),
    ]

    # Add per-horizon rows
    ae_horizon = ae_r.get('future_only', {}).get('per_horizon', {})
    gr_horizon = gr_r.get('future_only', {}).get('per_horizon', {})
    for label in ae_horizon:
        ae_val = ae_horizon.get(label, float('inf'))
        gr_val = gr_horizon.get(label, float('inf'))
        winner = 'AE' if ae_val <= gr_val else 'Grouped'
        rows.append((f'  Horizon {label}', f'{ae_val:.2f}', f'{gr_val:.2f}', winner))

    for name, ae_v, gr_v, winner in rows:
        print(f'  {name:<32s}  {ae_v:>10s}  {gr_v:>10s}  {winner:>8s}')

    print(f'\n  Persistence baseline:  MAE={p_mae:.2f} mg/dL')
    print(f'  Physics-only baseline: MAE={physics_metrics["mae_mgdl"]:.2f} mg/dL')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp012a_grouped_benchmark.json'))
    return results


def _load_patient_profile(data_path):
    """Load ISF/CR from Nightscout profile.json with unit conversion.

    Delegates to experiment_lib.load_patient_profile() which correctly
    handles mmol/L → mg/dL ISF conversion.
    """
    from .experiment_lib import load_patient_profile
    return load_patient_profile(data_path)


def run_grouped_transfer(args):
    """EXP-012b: GroupedEncoder + Residual Transfer Learning.

    Tests whether GroupedEncoder's forecast advantage (EXP-012a) survives
    transfer learning. Runs the EXP-009 pipeline for both AE and GroupedEncoder:
      1. Pre-train on synthetic enhanced residuals
      2. Fine-tune on real enhanced residuals
      3. From-scratch baseline on real
      4. Evaluate with reconstruction AND future-only forecast metrics

    Key question: does Grouped + transfer beat AE + transfer on forecast MAE?
    """
    print('=' * 60)
    print('EXP-012b: GroupedEncoder + Residual Transfer Learning')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-012b', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # --- Load synthetic data ---
    print('\n--- Step 1: Synthetic → enhanced residuals ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)
    has_synthetic = syn_t is not None and len(syn_t) > 0
    results['has_synthetic'] = has_synthetic

    syn_res_train_ds = syn_res_val_ds = None
    if has_synthetic:
        syn_train_np = syn_t.vectors.numpy()
        syn_val_np = syn_v.vectors.numpy()
        print(f'  Synthetic: {len(syn_train_np)} train, {len(syn_val_np)} val')

        syn_tr_res, syn_tr_phys, syn_stats = compute_residual_windows(
            syn_train_np, isf=isf, cr=cr, level='enhanced')
        syn_vr_res, syn_vr_phys, _ = compute_residual_windows(
            syn_val_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Synthetic residual std: {syn_stats["std"]:.1f} mg/dL')
        results['synthetic_residual_stats'] = syn_stats

        from .encoder import CGMDataset
        syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=args.window)
        syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=args.window)
    else:
        print('  WARNING: No synthetic vectors found — skipping pre-training stage.')

    # --- Load real data ---
    print('\n--- Step 2: Real data → enhanced residuals ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['real_samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Real: {len(train_np)} train, {len(val_np)} val')

    real_tr_res, real_tr_phys, real_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    real_vr_res, real_vr_phys, _ = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Real residual std: {real_stats["std"]:.1f} mg/dL')
    results['real_residual_stats'] = real_stats

    from .encoder import CGMDataset
    real_res_train_ds = CGMDataset(real_tr_res, task='reconstruct', window_size=args.window)
    real_res_val_ds = CGMDataset(real_vr_res, task='reconstruct', window_size=args.window)
    real_res_train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
    real_res_val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

    # Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    # Physics-only baseline
    physics_metrics = _evaluate_physics_only(real_vr_phys, val_np)
    results['physics_only'] = physics_metrics

    # --- Run for both architectures ---
    architectures = {
        'ae': {
            'class': CGMTransformerAE,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
        'grouped': {
            'class': CGMGroupedEncoder,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
    }

    for arch_name, arch_cfg in architectures.items():
        print(f'\n{"=" * 50}')
        print(f'  Architecture: {arch_name}')
        print(f'{"=" * 50}')
        arch_results = {}
        ModelClass = arch_cfg['class']
        model_kwargs = arch_cfg['kwargs']
        param_count = sum(p.numel() for p in ModelClass(**model_kwargs).parameters())
        arch_results['params'] = param_count

        # Step A: Pre-train on synthetic residuals
        synth_ckpt = str(out / f'ae_012b_{arch_name}_synth.pth')
        if has_synthetic:
            print(f'\n  --- Pre-train {arch_name} on synthetic residuals ---')
            model_synth = ModelClass(**model_kwargs)
            train_loop(model_synth,
                       DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True),
                       DataLoader(syn_res_val_ds, batch_size=args.batch),
                       lr=1e-3, epochs=args.epochs, patience=args.patience,
                       save_path=synth_ckpt, label=f'{arch_name}-synth')

        # Step B: Zero-shot evaluation (synthetic model → real data)
        if has_synthetic:
            print(f'\n  --- Zero-shot {arch_name} (synth→real) ---')
            model_zs = ModelClass(**model_kwargs)
            load_best(model_zs, synth_ckpt)
            zs_recon = _evaluate_residual_model(model_zs, real_vr_res, real_vr_phys, val_np)
            zs_forecast = _evaluate_residual_future_only(
                model_zs, real_vr_res, real_vr_phys, val_np,
                history_steps=args.window // 2)
            arch_results['zero_shot'] = {
                'reconstruction': zs_recon,
                'future_only': zs_forecast,
            }
            print(f'  [{arch_name}] Zero-shot: recon MAE={zs_recon["mae_mgdl"]:.2f}, '
                  f'forecast MAE={zs_forecast["mae_mgdl"]:.2f}')

        # Step C: Fine-tune (synthetic pretrained → real)
        print(f'\n  --- Fine-tune {arch_name} on real residuals ---')
        model_ft = ModelClass(**model_kwargs)
        if has_synthetic:
            load_best(model_ft, synth_ckpt)
        ft_ckpt = str(out / f'ae_012b_{arch_name}_transfer.pth')
        train_loop(model_ft, real_res_train_ld, real_res_val_ld,
                   lr=5e-4, epochs=args.epochs, patience=args.patience,
                   save_path=ft_ckpt, label=f'{arch_name}-transfer')

        # Step D: From-scratch baseline on real
        print(f'\n  --- Scratch {arch_name} on real residuals ---')
        model_sc = ModelClass(**model_kwargs)
        sc_ckpt = str(out / f'ae_012b_{arch_name}_scratch.pth')
        train_loop(model_sc, real_res_train_ld, real_res_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=sc_ckpt, label=f'{arch_name}-scratch')

        # Step E: Evaluate all variants
        print(f'\n  --- Evaluate {arch_name} ---')
        load_best(model_ft, ft_ckpt)
        load_best(model_sc, sc_ckpt)

        for variant_name, model_v in [('transfer', model_ft), ('scratch', model_sc)]:
            recon = _evaluate_residual_model(model_v, real_vr_res, real_vr_phys, val_np)
            forecast = _evaluate_residual_future_only(
                model_v, real_vr_res, real_vr_phys, val_np,
                history_steps=args.window // 2)
            arch_results[variant_name] = {
                'reconstruction': recon,
                'future_only': forecast,
            }
            print(f'  [{arch_name} {variant_name}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f} mg/dL')

        results[arch_name] = arch_results

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary table
    print('\n' + '=' * 60)
    print('SUMMARY — GroupedEncoder + Residual Transfer')
    print('=' * 60)
    header = f'  {"Variant":<28s}  {"Recon MAE":>10s}  {"Forecast MAE":>12s}'
    print(header)
    print(f'  {"-"*28}  {"-"*10}  {"-"*12}')
    print(f'  {"Persistence":<28s}  {"—":>10s}  {p_mae:>12.2f}')
    print(f'  {"Physics-only":<28s}  {physics_metrics["mae_mgdl"]:>10.2f}  {"—":>12s}')

    for arch in ['ae', 'grouped']:
        ar = results[arch]
        for variant in ['zero_shot', 'transfer', 'scratch']:
            if variant not in ar:
                continue
            label = f'{arch} {variant}'
            vr = ar[variant]
            print(f'  {label:<28s}  {vr["reconstruction"]["mae_mgdl"]:>10.2f}  '
                  f'{vr["future_only"]["mae_mgdl"]:>12.2f}')

    # Key comparison
    ae_tf = results['ae'].get('transfer', {}).get('future_only', {}).get('mae_mgdl', float('inf'))
    gr_tf = results['grouped'].get('transfer', {}).get('future_only', {}).get('mae_mgdl', float('inf'))
    if ae_tf != float('inf') and gr_tf != float('inf'):
        pct = (ae_tf - gr_tf) / ae_tf * 100
        winner = 'Grouped' if gr_tf < ae_tf else 'AE'
        print(f'\n  Key: {winner} transfer wins on forecast by {abs(pct):.1f}%')
        print(f'    AE transfer forecast:      {ae_tf:.2f} mg/dL')
        print(f'    Grouped transfer forecast:  {gr_tf:.2f} mg/dL')

    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp012b_grouped_transfer.json'))
    return results


def run_causal_longer_horizons(args):
    """EXP-010b: Causal Future-Only Metric on Longer Horizons.

    Extends EXP-010 by:
    1. Testing both AE and GroupedEncoder at each horizon (1hr, 2hr, 3hr)
    2. Evaluating with causal future-only metric (not just reconstruction)
    3. Per-horizon breakdown showing how forecast quality degrades with distance

    Key question: does GroupedEncoder's advantage grow or shrink at longer horizons?
    """
    print('=' * 60)
    print('EXP-010b: Causal Future-Only on Longer Horizons')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-010b', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    horizons = [12, 24, 36]  # 1hr, 2hr, 3hr
    horizon_results = {}

    from .encoder import CGMDataset

    architectures = {
        'ae': {
            'class': CGMTransformerAE,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
        'grouped': {
            'class': CGMGroupedEncoder,
            'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        },
    }

    for window in horizons:
        label = f'{window * 5}min ({window} steps)'
        print(f'\n{"─" * 60}')
        print(f'  Horizon: {label}')
        print(f'{"─" * 60}')

        real_t, real_v = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window)
        if real_t is None or len(real_t) == 0:
            print(f'  No data for window={window}, skipping')
            continue

        train_np = real_t.vectors.numpy()
        val_np = real_v.vectors.numpy()
        print(f'  Windows: {len(train_np)} train, {len(val_np)} val')

        tr_res, tr_phys, tr_stats = compute_residual_windows(
            train_np, isf=isf, cr=cr, level='enhanced')
        vr_res, vr_phys, vr_stats = compute_residual_windows(
            val_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Residual std: {vr_stats["std"]:.1f} mg/dL')

        physics_metrics = _evaluate_physics_only(vr_phys, val_np)
        print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

        # Persistence baseline
        _, rv_2x = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window * 2)
        p_mae, p_rmse = persistence_baseline(rv_2x, window)

        res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
        res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=window)
        res_train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True)
        res_val_ld = DataLoader(res_val_ds, batch_size=args.batch)

        horizon_entry = {
            'window_steps': window,
            'window_minutes': window * 5,
            'history_steps': window // 2,
            'forecast_steps': window - window // 2,
            'samples': {'train': len(train_np), 'val': len(val_np)},
            'residual_stats': vr_stats,
            'physics_only': physics_metrics,
            'persistence': {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)},
        }

        for arch_name, arch_cfg in architectures.items():
            print(f'\n  --- Train {arch_name} at {window * 5}min ---')
            model = arch_cfg['class'](**arch_cfg['kwargs'])
            ckpt = str(out / f'ae_010b_{arch_name}_w{window}.pth')
            train_loop(model, res_train_ld, res_val_ld,
                       lr=1e-3, epochs=args.epochs, patience=args.patience,
                       save_path=ckpt, label=f'{arch_name}-w{window}')

            load_best(model, ckpt)

            recon = _evaluate_residual_model(model, vr_res, vr_phys, val_np)
            forecast = _evaluate_residual_future_only(
                model, vr_res, vr_phys, val_np,
                history_steps=window // 2)

            horizon_entry[arch_name] = {
                'reconstruction': recon,
                'future_only': forecast,
            }
            print(f'  [{arch_name}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f} mg/dL')
            if forecast.get('per_horizon'):
                horizons_str = ', '.join(f'{k}={v}' for k, v in forecast['per_horizon'].items())
                print(f'  [{arch_name}] per-horizon: {horizons_str}')

        horizon_results[window] = horizon_entry

    results['horizons'] = horizon_results
    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary table
    print('\n' + '=' * 60)
    print('SUMMARY — Causal Future-Only on Longer Horizons')
    print('=' * 60)
    print(f'  {"Window":<10s}  {"Persist":>8s}  {"Physics":>8s}  '
          f'{"AE Recon":>9s}  {"AE Fcast":>9s}  '
          f'{"Grp Recon":>9s}  {"Grp Fcast":>9s}  {"Winner":>7s}')
    print(f'  {"-"*10}  {"-"*8}  {"-"*8}  '
          f'{"-"*9}  {"-"*9}  {"-"*9}  {"-"*9}  {"-"*7}')

    for w in sorted(horizon_results.keys()):
        hr = horizon_results[w]
        wlabel = f'{w*5}min'
        persist = hr['persistence']['mae_mgdl']
        physics = hr['physics_only']['mae_mgdl']
        ae_r = hr.get('ae', {})
        gr_r = hr.get('grouped', {})
        ae_recon = ae_r.get('reconstruction', {}).get('mae_mgdl', float('nan'))
        ae_fcast = ae_r.get('future_only', {}).get('mae_mgdl', float('nan'))
        gr_recon = gr_r.get('reconstruction', {}).get('mae_mgdl', float('nan'))
        gr_fcast = gr_r.get('future_only', {}).get('mae_mgdl', float('nan'))
        winner = 'Grouped' if gr_fcast < ae_fcast else 'AE'
        print(f'  {wlabel:<10s}  {persist:>8.2f}  {physics:>8.2f}  '
              f'{ae_recon:>9.2f}  {ae_fcast:>9.2f}  '
              f'{gr_recon:>9.2f}  {gr_fcast:>9.2f}  {winner:>7s}')

    # Grouped advantage at each horizon
    print(f'\n  GroupedEncoder forecast advantage by horizon:')
    for w in sorted(horizon_results.keys()):
        hr = horizon_results[w]
        ae_f = hr.get('ae', {}).get('future_only', {}).get('mae_mgdl', 0)
        gr_f = hr.get('grouped', {}).get('future_only', {}).get('mae_mgdl', 0)
        if ae_f > 0:
            pct = (ae_f - gr_f) / ae_f * 100
            print(f'    {w*5}min: {pct:+.1f}% (AE={ae_f:.2f}, Grouped={gr_f:.2f})')

    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp010b_causal_horizons.json'))
    return results


def run_multiseed_robustness(args):
    """EXP-013: Multi-Seed Robustness at 1hr.

    Resolves conflicting results between EXP-012a (Grouped wins at 1hr)
    and EXP-010b (AE wins at 1hr) by running both architectures across
    multiple seeds and reporting mean +/- std.

    Seeds control: model initialization, batch shuffling.
    Data and physics are deterministic — identical every run.
    """
    print('=' * 60)
    print('EXP-013: Multi-Seed Robustness (AE vs Grouped, 1hr)')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-013', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    seeds = [42, 123, 456, 789, 1024]
    results['seeds'] = seeds

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Load data ONCE (deterministic — same every seed)
    print('\n--- Loading data (shared across all seeds) ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Windows: {len(train_np)} train, {len(val_np)} val')

    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, vr_stats = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Residual std: {vr_stats["std"]:.1f} mg/dL')

    # Physics-only and persistence baselines (deterministic, compute once)
    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence: MAE={p_mae:.2f}')

    from .encoder import CGMDataset
    res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)

    architectures = {
        'ae': {'class': CGMTransformerAE,
               'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
        'grouped': {'class': CGMGroupedEncoder,
                    'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
    }

    # Collect per-seed results
    seed_results = {arch: [] for arch in architectures}

    for seed in seeds:
        print(f'\n{"─" * 60}')
        print(f'  Seed: {seed}')
        print(f'{"─" * 60}')

        for arch_name, arch_cfg in architectures.items():
            set_seed(seed)

            model = arch_cfg['class'](**arch_cfg['kwargs'])
            ckpt = str(out / f'ae_013_{arch_name}_s{seed}.pth')

            # Fresh DataLoaders each seed (shuffle order depends on seed)
            train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True)
            val_ld = DataLoader(res_val_ds, batch_size=args.batch)

            train_loop(model, train_ld, val_ld,
                       lr=1e-3, epochs=args.epochs, patience=args.patience,
                       save_path=ckpt, label=f'{arch_name}-s{seed}')

            load_best(model, ckpt)
            recon = _evaluate_residual_model(model, vr_res, vr_phys, val_np)
            forecast = _evaluate_residual_future_only(
                model, vr_res, vr_phys, val_np,
                history_steps=args.window // 2)

            seed_results[arch_name].append({
                'seed': seed,
                'reconstruction': recon,
                'future_only': forecast,
            })
            print(f'  [{arch_name} s{seed}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f}')

            # Clean up checkpoint to save disk
            if os.path.exists(ckpt):
                os.remove(ckpt)

    # Compute statistics
    for arch_name in architectures:
        recon_vals = [r['reconstruction']['mae_mgdl'] for r in seed_results[arch_name]]
        fcast_vals = [r['future_only']['mae_mgdl'] for r in seed_results[arch_name]]
        results[arch_name] = {
            'runs': seed_results[arch_name],
            'reconstruction': {
                'mean': round(float(np.mean(recon_vals)), 2),
                'std': round(float(np.std(recon_vals)), 2),
                'min': round(float(np.min(recon_vals)), 2),
                'max': round(float(np.max(recon_vals)), 2),
                'all': [round(v, 2) for v in recon_vals],
            },
            'future_only': {
                'mean': round(float(np.mean(fcast_vals)), 2),
                'std': round(float(np.std(fcast_vals)), 2),
                'min': round(float(np.min(fcast_vals)), 2),
                'max': round(float(np.max(fcast_vals)), 2),
                'all': [round(v, 2) for v in fcast_vals],
            },
        }

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Multi-Seed Robustness (5 seeds)')
    print('=' * 60)
    print(f'  {"Metric":<24s}  {"AE (mean\u00b1std)":>18s}  {"Grouped (mean\u00b1std)":>18s}  {"Winner":>8s}')
    print(f'  {"-"*24}  {"-"*18}  {"-"*18}  {"-"*8}')

    ae_s = results['ae']
    gr_s = results['grouped']

    for metric_key, metric_label in [('reconstruction', 'Recon MAE'),
                                     ('future_only', 'Forecast MAE (causal)')]:
        ae_m = ae_s[metric_key]
        gr_m = gr_s[metric_key]
        ae_str = f'{ae_m["mean"]:.2f}\u00b1{ae_m["std"]:.2f}'
        gr_str = f'{gr_m["mean"]:.2f}\u00b1{gr_m["std"]:.2f}'
        winner = 'AE' if ae_m['mean'] < gr_m['mean'] else 'Grouped'
        print(f'  {metric_label:<24s}  {ae_str:>18s}  {gr_str:>18s}  {winner:>8s}')

    # Individual runs
    print(f'\n  Individual forecast MAEs:')
    print(f'  {"Seed":>6s}  {"AE":>8s}  {"Grouped":>8s}  {"Winner":>8s}')
    for i, seed in enumerate(seeds):
        ae_v = ae_s['future_only']['all'][i]
        gr_v = gr_s['future_only']['all'][i]
        w = 'AE' if ae_v < gr_v else 'Grouped'
        print(f'  {seed:>6d}  {ae_v:>8.2f}  {gr_v:>8.2f}  {w:>8s}')

    ae_wins = sum(1 for i in range(len(seeds))
                  if ae_s['future_only']['all'][i] < gr_s['future_only']['all'][i])
    gr_wins = len(seeds) - ae_wins
    print(f'\n  Score: AE {ae_wins}/{len(seeds)}, Grouped {gr_wins}/{len(seeds)}')
    print(f'  Persistence baseline: {p_mae:.2f} mg/dL')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp013_multiseed.json'))
    return results


def run_walkforward_grouped_transfer(args):
    """EXP-014: Walk-Forward Temporal Validation with Grouped + Transfer.

    Verifies that the Grouped+transfer best result (0.43 MAE from EXP-012b)
    holds under strict temporal validation:
    - Hard chronological split (no overlapping windows between train/test)
    - Optional 1-day gap to prevent boundary leakage
    - Tests both AE and GroupedEncoder with transfer learning
    - Reports reconstruction AND causal future-only forecast metrics

    Key question: does 0.43 survive honest temporal evaluation?
    """
    print('=' * 60)
    print('EXP-014: Walk-Forward with Grouped + Transfer')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-014', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    set_seed(42)  # reproducible

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Load synthetic data for pre-training
    print('\n--- Step 1: Synthetic data for pre-training ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)
    has_synthetic = syn_t is not None and len(syn_t) > 0
    results['has_synthetic'] = has_synthetic

    syn_res_train_ds = syn_res_val_ds = None
    if has_synthetic:
        syn_train_np = syn_t.vectors.numpy()
        syn_val_np = syn_v.vectors.numpy()
        print(f'  Synthetic: {len(syn_train_np)} train, {len(syn_val_np)} val')

        syn_tr_res, _, syn_stats = compute_residual_windows(
            syn_train_np, isf=isf, cr=cr, level='enhanced')
        syn_vr_res, _, _ = compute_residual_windows(
            syn_val_np, isf=isf, cr=cr, level='enhanced')
        print(f'  Synthetic residual std: {syn_stats["std"]:.1f} mg/dL')
        results['synthetic_residual_stats'] = syn_stats

        from .encoder import CGMDataset
        syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=args.window)
        syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=args.window)
    else:
        print('  WARNING: No synthetic vectors — transfer will skip pre-training.')

    # Build full feature grid for walk-forward splitting
    print('\n--- Step 2: Build feature grid ---')
    features, grid_index = _build_feature_grid(args.real_data)
    total_days = (grid_index[-1] - grid_index[0]).days
    print(f'  Grid: {len(features)} points, {total_days} days')

    from .real_data_adapter import split_into_windows
    from .encoder import CGMDataset
    window = args.window

    architectures = {
        'ae': {'class': CGMTransformerAE,
               'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
        'grouped': {'class': CGMGroupedEncoder,
                    'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
    }

    # Walk-forward split: 70/30 with 1-day gap (strictest from EXP-011)
    split_cfg = {'name': 'wf_70_30_gap1d', 'train_frac': 0.70, 'gap_days': 1}
    train_frac = split_cfg['train_frac']
    gap_days = split_cfg['gap_days']

    split_point = int(len(features) * train_frac)
    gap_points = gap_days * 288

    train_grid = features[:split_point]
    test_grid = features[split_point + gap_points:]

    split_date = grid_index[split_point].strftime('%Y-%m-%d')
    train_days = (grid_index[split_point] - grid_index[0]).days
    test_days = (grid_index[-1] - grid_index[min(split_point + gap_points, len(grid_index)-1)]).days
    print(f'\n  Walk-forward split at {split_date}: {train_days}d train, '
          f'{test_days}d test, {gap_days}d gap')

    train_wins = split_into_windows(train_grid, window_size=window)
    test_wins = split_into_windows(test_grid, window_size=window)
    train_np = np.array(train_wins)
    test_np = np.array(test_wins)
    print(f'  Windows: {len(train_np)} train, {len(test_np)} test')
    results['walk_forward'] = {
        'split_date': split_date, 'train_days': train_days,
        'test_days': test_days, 'gap_days': gap_days,
        'train_windows': len(train_np), 'test_windows': len(test_np),
    }

    # Compute enhanced residuals for real train/test
    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    te_res, te_phys, te_stats = compute_residual_windows(
        test_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Residual std: train={tr_stats["std"]:.1f}, test={te_stats["std"]:.1f} mg/dL')

    real_tr_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
    real_te_ds = CGMDataset(te_res, task='reconstruct', window_size=window)
    real_tr_ld = DataLoader(real_tr_ds, batch_size=args.batch, shuffle=True)
    real_te_ld = DataLoader(real_te_ds, batch_size=args.batch)

    # Physics-only baseline on test set
    physics_metrics = _evaluate_physics_only(te_phys, test_np)
    results['physics_only'] = physics_metrics

    # Persistence on test set
    test_wins_2x = split_into_windows(test_grid, window_size=window * 2)
    if test_wins_2x:
        test_tensor_2x = torch.tensor(np.array(test_wins_2x), dtype=torch.float32)
        te_ds_2x = CGMDataset(test_tensor_2x, task='forecast', window_size=window * 2)
        p_mae, p_rmse = persistence_baseline(te_ds_2x, window)
    else:
        p_mae, p_rmse = float('nan'), float('nan')
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}

    # Run each architecture: scratch + transfer
    for arch_name, arch_cfg in architectures.items():
        print(f'\n{"=" * 50}')
        print(f'  Architecture: {arch_name}')
        print(f'{"=" * 50}')
        ModelClass = arch_cfg['class']
        model_kwargs = arch_cfg['kwargs']
        arch_results = {}

        # --- Pre-train on synthetic ---
        synth_ckpt = str(out / f'ae_014_{arch_name}_synth.pth')
        if has_synthetic:
            print(f'\n  --- Pre-train {arch_name} on synthetic ---')
            set_seed(42)
            model_synth = ModelClass(**model_kwargs)
            train_loop(model_synth,
                       DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True),
                       DataLoader(syn_res_val_ds, batch_size=args.batch),
                       lr=1e-3, epochs=args.epochs, patience=args.patience,
                       save_path=synth_ckpt, label=f'{arch_name}-synth')

        # --- Transfer: synth pretrain → real finetune ---
        print(f'\n  --- Transfer {arch_name} (synth→real walk-forward) ---')
        set_seed(42)
        model_ft = ModelClass(**model_kwargs)
        if has_synthetic:
            load_best(model_ft, synth_ckpt)
        ft_ckpt = str(out / f'ae_014_{arch_name}_transfer.pth')
        train_loop(model_ft, real_tr_ld, real_te_ld,
                   lr=5e-4, epochs=args.epochs, patience=args.patience,
                   save_path=ft_ckpt, label=f'{arch_name}-transfer')

        # --- Scratch baseline ---
        print(f'\n  --- Scratch {arch_name} on walk-forward ---')
        set_seed(42)
        model_sc = ModelClass(**model_kwargs)
        sc_ckpt = str(out / f'ae_014_{arch_name}_scratch.pth')
        train_loop(model_sc, real_tr_ld, real_te_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=sc_ckpt, label=f'{arch_name}-scratch')

        # --- Evaluate both ---
        print(f'\n  --- Evaluate {arch_name} ---')
        load_best(model_ft, ft_ckpt)
        load_best(model_sc, sc_ckpt)

        for variant_name, model_v in [('transfer', model_ft), ('scratch', model_sc)]:
            recon = _evaluate_residual_model(model_v, te_res, te_phys, test_np)
            forecast = _evaluate_residual_future_only(
                model_v, te_res, te_phys, test_np,
                history_steps=window // 2)
            arch_results[variant_name] = {
                'reconstruction': recon,
                'future_only': forecast,
            }
            print(f'  [{arch_name} {variant_name}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f} mg/dL')

        results[arch_name] = arch_results

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY — Walk-Forward with Grouped + Transfer')
    print(f'  (70/30 split, 1-day gap, {train_days}d train / {test_days}d test)')
    print('=' * 60)
    header = f'  {"Variant":<28s}  {"Recon MAE":>10s}  {"Forecast MAE":>12s}'
    print(header)
    print(f'  {"-"*28}  {"-"*10}  {"-"*12}')
    print(f'  {"Persistence":<28s}  {"\u2014":>10s}  {p_mae:>12.2f}')
    print(f'  {"Physics-only":<28s}  {physics_metrics["mae_mgdl"]:>10.2f}  {"\u2014":>12s}')

    for arch in ['ae', 'grouped']:
        ar = results[arch]
        for variant in ['transfer', 'scratch']:
            label = f'{arch} {variant}'
            vr = ar[variant]
            print(f'  {label:<28s}  {vr["reconstruction"]["mae_mgdl"]:>10.2f}  '
                  f'{vr["future_only"]["mae_mgdl"]:>12.2f}')

    # Compare to EXP-012b (random split) results
    ae_wf = results['ae']['transfer']['future_only']['mae_mgdl']
    gr_wf = results['grouped']['transfer']['future_only']['mae_mgdl']
    print(f'\n  Walk-forward vs random split (EXP-012b):')
    print(f'    AE transfer forecast:      {ae_wf:.2f} (wf) vs 0.80 (random)')
    print(f'    Grouped transfer forecast:  {gr_wf:.2f} (wf) vs 0.43 (random)')

    winner = 'Grouped' if gr_wf < ae_wf else 'AE'
    pct = abs(ae_wf - gr_wf) / max(ae_wf, gr_wf) * 100
    print(f'    Walk-forward winner: {winner} ({pct:.1f}% better)')

    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp014_walkforward_transfer.json'))
    return results


def run_multiseed_transfer(args):
    """EXP-015: Multi-Seed Robustness WITH Transfer Learning.

    EXP-013 showed AE is more reliable than Grouped from scratch (0.74±0.23
    vs 1.01±0.64). But EXP-014 showed transfer stabilizes Grouped. This
    experiment answers: does transfer actually reduce Grouped's seed variance?

    Protocol:
    1. Pre-train ONCE per architecture on synthetic data (seed=42, shared)
    2. Fine-tune from pre-trained weights 5× with different seeds
    3. Report mean ± std across fine-tuning seeds
    """
    print('=' * 60)
    print('EXP-015: Multi-Seed Robustness WITH Transfer')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-015', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    seeds = [42, 123, 456, 789, 1024]
    results['seeds'] = seeds

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # --- Step 1: Load synthetic data for pre-training ---
    print('\n--- Step 1: Synthetic pre-training data ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)
    has_synthetic = syn_t is not None and len(syn_t) > 0
    results['has_synthetic'] = has_synthetic

    if not has_synthetic:
        print('  ERROR: Need synthetic data for transfer learning')
        return results

    syn_train_np = syn_t.vectors.numpy()
    syn_val_np = syn_v.vectors.numpy()
    print(f'  Synthetic: {len(syn_train_np)} train, {len(syn_val_np)} val')

    syn_tr_res, _, syn_stats = compute_residual_windows(
        syn_train_np, isf=isf, cr=cr, level='enhanced')
    syn_vr_res, _, _ = compute_residual_windows(
        syn_val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Synthetic residual std: {syn_stats["std"]:.1f} mg/dL')

    from .encoder import CGMDataset
    syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=args.window)
    syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=args.window)

    # --- Step 2: Load real data ---
    print('\n--- Step 2: Real data ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Real: {len(train_np)} train, {len(val_np)} val')

    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, _ = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Real residual std: {tr_stats["std"]:.1f} mg/dL')

    real_res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    real_res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)

    # Baselines (deterministic)
    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence: MAE={p_mae:.2f}')

    architectures = {
        'ae': {'class': CGMTransformerAE,
               'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
        'grouped': {'class': CGMGroupedEncoder,
                    'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
    }

    # --- Step 3: Pre-train ONCE per architecture (deterministic seed=42) ---
    print('\n--- Step 3: Pre-train on synthetic (shared, seed=42) ---')
    pretrained_weights = {}
    for arch_name, arch_cfg in architectures.items():
        set_seed(42)
        model = arch_cfg['class'](**arch_cfg['kwargs'])
        syn_train_ld = DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True)
        syn_val_ld = DataLoader(syn_res_val_ds, batch_size=args.batch)
        ckpt_path = str(out / f'exp015_pretrain_{arch_name}.pth')

        train_loop(model, syn_train_ld, syn_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt_path, label=f'pretrain-{arch_name}')

        load_best(model, ckpt_path)
        pretrained_weights[arch_name] = model.state_dict()
        print(f'  [{arch_name}] Pre-trained checkpoint saved')

    # --- Step 4: Fine-tune 5× per architecture with different seeds ---
    print('\n--- Step 4: Multi-seed fine-tuning ---')
    seed_results = {arch: [] for arch in architectures}

    for seed in seeds:
        print(f'\n{"─" * 60}')
        print(f'  Seed: {seed}')
        print(f'{"─" * 60}')

        for arch_name, arch_cfg in architectures.items():
            set_seed(seed)

            # Start from pre-trained weights
            model = arch_cfg['class'](**arch_cfg['kwargs'])
            model.load_state_dict(pretrained_weights[arch_name])

            ckpt = str(out / f'exp015_ft_{arch_name}_s{seed}.pth')

            # Fresh loaders (shuffle order depends on seed)
            train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
            val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

            train_loop(model, train_ld, val_ld,
                       lr=3e-4, epochs=args.epochs, patience=args.patience,
                       save_path=ckpt, label=f'{arch_name}-s{seed}')

            load_best(model, ckpt)
            recon = _evaluate_residual_model(model, vr_res, vr_phys, val_np)
            forecast = _evaluate_residual_future_only(
                model, vr_res, vr_phys, val_np,
                history_steps=args.window // 2)

            seed_results[arch_name].append({
                'seed': seed,
                'reconstruction': recon,
                'future_only': forecast,
            })
            print(f'  [{arch_name} s{seed}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f}')

            # Cleanup
            if os.path.exists(ckpt):
                os.remove(ckpt)

    # Cleanup pre-trained checkpoints
    for arch_name in architectures:
        p = str(out / f'exp015_pretrain_{arch_name}.pth')
        if os.path.exists(p):
            os.remove(p)

    # --- Compute statistics ---
    for arch_name in architectures:
        recon_vals = [r['reconstruction']['mae_mgdl'] for r in seed_results[arch_name]]
        fcast_vals = [r['future_only']['mae_mgdl'] for r in seed_results[arch_name]]
        results[arch_name] = {
            'runs': seed_results[arch_name],
            'reconstruction': {
                'mean': round(float(np.mean(recon_vals)), 2),
                'std': round(float(np.std(recon_vals)), 2),
                'min': round(float(np.min(recon_vals)), 2),
                'max': round(float(np.max(recon_vals)), 2),
                'all': [round(v, 2) for v in recon_vals],
            },
            'future_only': {
                'mean': round(float(np.mean(fcast_vals)), 2),
                'std': round(float(np.std(fcast_vals)), 2),
                'min': round(float(np.min(fcast_vals)), 2),
                'max': round(float(np.max(fcast_vals)), 2),
                'all': [round(v, 2) for v in fcast_vals],
            },
        }

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # --- Compare with EXP-013 (from-scratch) ---
    print('\n' + '=' * 60)
    print('SUMMARY — Multi-Seed WITH Transfer (5 seeds)')
    print('=' * 60)
    print(f'  {"Metric":<24s}  {"AE (mean±std)":>18s}  {"Grouped (mean±std)":>18s}  {"Winner":>8s}')
    print(f'  {"-"*24}  {"-"*18}  {"-"*18}  {"-"*8}')

    ae_s = results['ae']
    gr_s = results['grouped']

    for metric_key, metric_label in [('reconstruction', 'Recon MAE'),
                                     ('future_only', 'Forecast MAE (causal)')]:
        ae_m = ae_s[metric_key]
        gr_m = gr_s[metric_key]
        ae_str = f'{ae_m["mean"]:.2f}±{ae_m["std"]:.2f}'
        gr_str = f'{gr_m["mean"]:.2f}±{gr_m["std"]:.2f}'
        winner = 'AE' if ae_m['mean'] < gr_m['mean'] else 'Grouped'
        print(f'  {metric_label:<24s}  {ae_str:>18s}  {gr_str:>18s}  {winner:>8s}')

    print(f'\n  Individual forecast MAEs:')
    print(f'  {"Seed":>6s}  {"AE":>8s}  {"Grouped":>8s}  {"Winner":>8s}')
    for i, seed in enumerate(seeds):
        ae_v = ae_s['future_only']['all'][i]
        gr_v = gr_s['future_only']['all'][i]
        w = 'AE' if ae_v < gr_v else 'Grouped'
        print(f'  {seed:>6d}  {ae_v:>8.2f}  {gr_v:>8.2f}  {w:>8s}')

    ae_wins = sum(1 for i in range(len(seeds))
                  if ae_s['future_only']['all'][i] < gr_s['future_only']['all'][i])
    gr_wins = len(seeds) - ae_wins
    print(f'\n  Score: AE {ae_wins}/{len(seeds)}, Grouped {gr_wins}/{len(seeds)}')

    # Compare variance with EXP-013
    print(f'\n  Variance comparison with EXP-013 (from-scratch):')
    print(f'    EXP-013 AE std:      0.23  →  EXP-015: {ae_s["future_only"]["std"]:.2f}')
    print(f'    EXP-013 Grouped std: 0.64  →  EXP-015: {gr_s["future_only"]["std"]:.2f}')

    variance_reduced = gr_s['future_only']['std'] < 0.64
    print(f'    Transfer reduces Grouped variance: {"YES ✓" if variance_reduced else "NO ✗"}')

    print(f'\n  Persistence baseline: {p_mae:.2f} mg/dL')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp015_multiseed_transfer.json'))
    return results


def _ddpm_sample(model, shape, num_steps=50):
    """Generate samples from trained diffusion model using DDPM reverse process.

    Uses a stride through the original 1000-step schedule for efficiency.
    Returns denoised sample in data space.
    """
    device = next(model.parameters()).device
    T_full = model.timesteps

    # Subsample timesteps for fast generation
    stride = max(1, T_full // num_steps)
    timesteps = list(range(T_full - 1, -1, -stride))

    # Precompute alpha schedule from registered buffers
    alphas_cumprod = model.sqrt_alphas_cumprod ** 2  # recover αbar from sqrt
    betas = 1.0 - alphas_cumprod / torch.cat([torch.ones(1, device=device), alphas_cumprod[:-1]])

    x_t = torch.randn(shape, device=device)

    with torch.no_grad():
        for i, t in enumerate(timesteps):
            t_batch = torch.full((shape[0],), t, device=device, dtype=torch.long)
            predicted_noise = model(x_t, t_batch)

            alpha_bar_t = alphas_cumprod[t]
            beta_t = betas[t]
            alpha_t = 1.0 - beta_t

            # DDPM reverse step: x_{t-1} = (1/sqrt(α_t)) * (x_t - β_t/sqrt(1-αbar_t) * ε_θ)
            coeff = beta_t / (torch.sqrt(1.0 - alpha_bar_t) + 1e-8)
            x_mean = (1.0 / torch.sqrt(alpha_t)) * (x_t - coeff * predicted_noise)

            if t > 0:
                noise = torch.randn_like(x_t)
                sigma = torch.sqrt(beta_t)
                x_t = x_mean + sigma * noise
            else:
                x_t = x_mean

    return x_t


def _train_diffusion_epoch(model, loader, optimizer):
    """One epoch of DDPM noise prediction training."""
    model.train()
    device = next(model.parameters()).device
    total_loss = 0
    n = 0
    for batch_in, _ in loader:
        batch_in = batch_in.to(device, non_blocking=True)
        optimizer.zero_grad()
        B = batch_in.size(0)
        t = torch.randint(0, model.timesteps, (B,), device=device)
        noise = torch.randn_like(batch_in)
        x_t = model.q_sample(batch_in, t, noise=noise)
        predicted_noise = model(x_t, t)
        loss = torch.nn.functional.mse_loss(predicted_noise, noise)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item() * B
        n += B
    return total_loss / n if n > 0 else float('inf')


def _eval_diffusion(model, loader):
    """Evaluate diffusion model noise prediction loss."""
    model.eval()
    device = next(model.parameters()).device
    total_loss = 0
    n = 0
    with torch.no_grad():
        for batch_in, _ in loader:
            batch_in = batch_in.to(device, non_blocking=True)
            B = batch_in.size(0)
            t = torch.randint(0, model.timesteps, (B,), device=device)
            noise = torch.randn_like(batch_in)
            x_t = model.q_sample(batch_in, t, noise=noise)
            predicted_noise = model(x_t, t)
            loss = torch.nn.functional.mse_loss(predicted_noise, noise)
            total_loss += loss.item() * B
            n += B
    return total_loss / n if n > 0 else float('inf')


def _evaluate_diffusion_forecast(model, val_windows_residual, physics_pred_val,
                                 val_windows_orig, history_steps=None,
                                 interval_min=5, n_samples=20):
    """Evaluate diffusion model on forecast task.

    Strategy: condition on observed history by:
    1. Starting from noise
    2. Running reverse diffusion
    3. Replacing history portion with actual observed values at each step
    4. The future portion gets denoised while staying coherent with history

    Average across n_samples stochastic runs for a mean prediction.
    """
    from .schema import IDX_GLUCOSE, NORMALIZATION_SCALES
    glucose_scale = NORMALIZATION_SCALES['glucose']

    T = val_windows_residual.shape[1]
    if history_steps is None:
        history_steps = T // 2

    model.eval()
    device = next(model.parameters()).device
    T_full = model.timesteps

    # Fast sampling schedule
    num_steps = 50
    stride = max(1, T_full // num_steps)
    timesteps = list(range(T_full - 1, -1, -stride))

    alphas_cumprod = model.sqrt_alphas_cumprod ** 2
    betas = 1.0 - alphas_cumprod / torch.cat([torch.ones(1, device=device), alphas_cumprod[:-1]])

    all_future_pred = []
    all_future_actual = []
    horizon_errors = {}

    # Process in mini-batches for memory efficiency
    batch_size = 64
    residual_tensor = torch.FloatTensor(val_windows_residual).to(device)

    for start in range(0, len(val_windows_residual), batch_size):
        end = min(start + batch_size, len(val_windows_residual))
        batch_obs = residual_tensor[start:end]  # (B, T, 8)
        B = batch_obs.shape[0]

        # Average n_samples stochastic predictions
        sample_preds = []
        for _ in range(n_samples):
            x_t = torch.randn_like(batch_obs)
            # Inpaint history at each reverse step
            with torch.no_grad():
                for step_t in timesteps:
                    t_batch = torch.full((B,), step_t, device=device, dtype=torch.long)
                    predicted_noise = model(x_t, t_batch)

                    alpha_bar_t = alphas_cumprod[step_t]
                    beta_t = betas[step_t]
                    alpha_t = 1.0 - beta_t

                    coeff = beta_t / (torch.sqrt(1.0 - alpha_bar_t) + 1e-8)
                    x_mean = (1.0 / torch.sqrt(alpha_t)) * (x_t - coeff * predicted_noise)

                    if step_t > 0:
                        noise = torch.randn_like(x_t)
                        sigma = torch.sqrt(beta_t)
                        x_t = x_mean + sigma * noise
                    else:
                        x_t = x_mean

                    # Inpaint: replace history portion with noised observation
                    if step_t > 0:
                        obs_noise = torch.randn_like(batch_obs)
                        sqrt_ab = model.sqrt_alphas_cumprod[step_t]
                        sqrt_1_ab = model.sqrt_one_minus_alphas_cumprod[step_t]
                        noised_obs = sqrt_ab * batch_obs + sqrt_1_ab * obs_noise
                        x_t[:, :history_steps, :] = noised_obs[:, :history_steps, :]
                    else:
                        x_t[:, :history_steps, :] = batch_obs[:, :history_steps, :]

            sample_preds.append(x_t[:, :, 0].cpu().numpy())  # glucose channel

        # Average across samples
        mean_pred = np.mean(sample_preds, axis=0)  # (B, T)

        for b in range(B):
            i = start + b
            if i >= len(physics_pred_val):
                break

            pred_residual = mean_pred[b, history_steps:]
            pred_glucose = residual_to_glucose(pred_residual, physics_pred_val[i, history_steps:])
            actual_glucose = val_windows_orig[i, history_steps:, IDX_GLUCOSE] * glucose_scale

            all_future_pred.append(pred_glucose)
            all_future_actual.append(actual_glucose)

            abs_errs = np.abs(pred_glucose - actual_glucose)
            for step in range(len(abs_errs)):
                horizon_errors.setdefault(step, []).append(abs_errs[step])

    all_pred = np.concatenate(all_future_pred)
    all_actual = np.concatenate(all_future_actual)
    mae = float(np.mean(np.abs(all_pred - all_actual)))
    rmse = float(np.sqrt(np.mean((all_pred - all_actual) ** 2)))

    per_horizon = {}
    for step in sorted(horizon_errors.keys()):
        minutes = (step + 1) * interval_min
        per_horizon[f'{minutes}min'] = round(float(np.mean(horizon_errors[step])), 2)

    # Compute spread across samples (uncertainty metric)
    return {
        'mae_mgdl': round(mae, 2),
        'rmse_mgdl': round(rmse, 2),
        'history_steps': history_steps,
        'future_steps': T - history_steps,
        'n_samples': n_samples,
        'per_horizon': per_horizon,
    }


def run_diffusion_benchmark(args):
    """EXP-016: Diffusion Model Benchmark.

    First test of CGMDenoisingDiffusion on the residual forecast task.
    Compares DDPM against AE and GroupedEncoder baselines.

    Key question: does stochastic generation beat deterministic reconstruction?
    Bonus: DDPM gives uncertainty quantification for free via sample spread.
    """
    print('=' * 60)
    print('EXP-016: Diffusion Model Benchmark')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-016', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    set_seed(42)

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # --- Load data ---
    print('\n--- Step 1: Load data + residuals ---')
    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Windows: {len(train_np)} train, {len(val_np)} val')

    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, _ = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')
    print(f'  Residual std: {tr_stats["std"]:.1f} mg/dL')

    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence: MAE={p_mae:.2f}')

    from .encoder import CGMDataset
    res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)
    use_pin = _DEFAULT_DEVICE.type == 'cuda'
    train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True, pin_memory=use_pin)
    val_ld = DataLoader(res_val_ds, batch_size=args.batch, pin_memory=use_pin)

    # --- Step 2: Train Diffusion model ---
    print('\n--- Step 2: Train DDPM ---')
    from .toolbox import CGMDenoisingDiffusion

    # Use fewer timesteps for training efficiency on small data
    diffusion_timesteps = 200
    model = CGMDenoisingDiffusion(
        input_dim=8, d_model=64, nhead=4, timesteps=diffusion_timesteps)
    model.to(_DEFAULT_DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'  DDPM params: {n_params:,} (timesteps={diffusion_timesteps})')
    results['ddpm_params'] = n_params
    results['diffusion_timesteps'] = diffusion_timesteps

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    best_val = float('inf')
    stale = 0
    ckpt_path = str(out / 'exp016_ddpm.pth')

    for ep in range(args.epochs):
        tl = _train_diffusion_epoch(model, train_ld, optimizer)
        vl = _eval_diffusion(model, val_ld)
        sched.step(vl)

        if vl < best_val:
            best_val = vl
            stale = 0
            os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
            torch.save({'epoch': ep, 'model_state': model.state_dict(),
                        'val_loss': vl}, ckpt_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == args.epochs - 1:
            lr_now = optimizer.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [DDPM] Epoch {ep+1:3d}/{args.epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best_val:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if args.patience > 0 and stale >= args.patience:
            print(f'  [DDPM] Early stop at epoch {ep+1}')
            break

    # Load best
    ckpt = torch.load(ckpt_path, map_location=_DEFAULT_DEVICE, weights_only=True)
    model.load_state_dict(ckpt['model_state'])
    model.to(_DEFAULT_DEVICE)
    results['ddpm_training'] = {
        'best_val_loss': round(best_val, 6),
        'best_epoch': ckpt['epoch'],
    }
    print(f'  Best DDPM val loss: {best_val:.6f} (epoch {ckpt["epoch"]})')

    # --- Step 3: Evaluate DDPM forecast ---
    print('\n--- Step 3: DDPM forecast evaluation (20 samples) ---')
    ddpm_forecast = _evaluate_diffusion_forecast(
        model, vr_res, vr_phys, val_np,
        history_steps=args.window // 2, n_samples=20)
    results['ddpm_forecast'] = ddpm_forecast
    print(f'  DDPM forecast MAE: {ddpm_forecast["mae_mgdl"]:.2f}')

    # --- Step 4: AE and Grouped baselines for comparison ---
    print('\n--- Step 4: AE + Grouped baselines ---')
    baselines = {
        'ae': CGMTransformerAE(input_dim=8, d_model=64, nhead=4, num_layers=2),
        'grouped': CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2),
    }

    for name, bmodel in baselines.items():
        set_seed(42)
        bmodel = baselines[name].__class__(input_dim=8, d_model=64, nhead=4, num_layers=2)
        b_train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True)
        b_val_ld = DataLoader(res_val_ds, batch_size=args.batch)
        b_ckpt = str(out / f'exp016_{name}.pth')

        train_loop(bmodel, b_train_ld, b_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=b_ckpt, label=name)

        load_best(bmodel, b_ckpt)
        recon = _evaluate_residual_model(bmodel, vr_res, vr_phys, val_np)
        forecast = _evaluate_residual_future_only(
            bmodel, vr_res, vr_phys, val_np,
            history_steps=args.window // 2)

        results[name] = {
            'reconstruction': recon,
            'future_only': forecast,
        }
        print(f'  [{name}] recon={recon["mae_mgdl"]:.2f}  forecast={forecast["mae_mgdl"]:.2f}')

        if os.path.exists(b_ckpt):
            os.remove(b_ckpt)

    # Cleanup DDPM checkpoint
    if os.path.exists(ckpt_path):
        os.remove(ckpt_path)

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # --- Summary ---
    print('\n' + '=' * 60)
    print('SUMMARY — Diffusion Benchmark')
    print('=' * 60)

    ae_f = results['ae']['future_only']['mae_mgdl']
    gr_f = results['grouped']['future_only']['mae_mgdl']
    dd_f = ddpm_forecast['mae_mgdl']

    print(f'  {"Model":<20s}  {"Forecast MAE":>12s}  {"vs Persistence":>14s}')
    print(f'  {"-"*20}  {"-"*12}  {"-"*14}')
    print(f'  {"Persistence":<20s}  {p_mae:>12.2f}  {"baseline":>14s}')
    print(f'  {"Physics-only":<20s}  {physics_metrics["mae_mgdl"]:>12.2f}  '
          f'{(1-physics_metrics["mae_mgdl"]/p_mae)*100:>13.1f}%')
    print(f'  {"AE (scratch)":<20s}  {ae_f:>12.2f}  {(1-ae_f/p_mae)*100:>13.1f}%')
    print(f'  {"Grouped (scratch)":<20s}  {gr_f:>12.2f}  {(1-gr_f/p_mae)*100:>13.1f}%')
    print(f'  {"DDPM (20 samples)":<20s}  {dd_f:>12.2f}  {(1-dd_f/p_mae)*100:>13.1f}%')

    # Per-horizon comparison
    if ddpm_forecast.get('per_horizon') and results['ae']['future_only'].get('per_horizon'):
        print(f'\n  Per-horizon forecast MAE:')
        ae_ph = results['ae']['future_only']['per_horizon']
        dd_ph = ddpm_forecast['per_horizon']
        print(f'  {"Horizon":<10s}  {"AE":>8s}  {"DDPM":>8s}  {"Winner":>8s}')
        for h in sorted(dd_ph.keys(), key=lambda x: int(x.replace('min', ''))):
            if h in ae_ph:
                w = 'AE' if ae_ph[h] < dd_ph[h] else 'DDPM'
                print(f'  {h:<10s}  {ae_ph[h]:>8.2f}  {dd_ph[h]:>8.2f}  {w:>8s}')

    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp016_diffusion_benchmark.json'))
    return results


def run_seed_ensemble(args):
    """EXP-017: Seed Ensemble for Grouped+Transfer.

    Trains 5 Grouped+transfer models with different seeds (same as EXP-015)
    and averages their predictions at inference time. Tests whether
    ensemble averaging beats the single best model.

    Also tests AE ensemble for fair comparison.
    """
    print('=' * 60)
    print('EXP-017: Seed Ensemble (5-model averaging)')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-017', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    seeds = [42, 123, 456, 789, 1024]
    results['seeds'] = seeds

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    # Load synthetic + real data (same as EXP-015)
    print('\n--- Step 1: Data loading ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, task='forecast', window_size=args.window)
    has_synthetic = syn_t is not None and len(syn_t) > 0
    if not has_synthetic:
        print('  ERROR: Need synthetic data for transfer')
        return results

    syn_train_np = syn_t.vectors.numpy()
    syn_val_np = syn_v.vectors.numpy()
    syn_tr_res, _, syn_stats = compute_residual_windows(
        syn_train_np, isf=isf, cr=cr, level='enhanced')
    syn_vr_res, _, _ = compute_residual_windows(
        syn_val_np, isf=isf, cr=cr, level='enhanced')

    from .encoder import CGMDataset
    syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=args.window)
    syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=args.window)

    real_t, real_v = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window)
    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Real: {len(train_np)} train, {len(val_np)} val')

    tr_res, tr_phys, _ = compute_residual_windows(
        train_np, isf=isf, cr=cr, level='enhanced')
    vr_res, vr_phys, _ = compute_residual_windows(
        val_np, isf=isf, cr=cr, level='enhanced')

    real_res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    real_res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)

    # Baselines
    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics

    _, rv_2x = load_nightscout_to_dataset(
        args.real_data, task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2)}

    architectures = {
        'ae': {'class': CGMTransformerAE,
               'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
        'grouped': {'class': CGMGroupedEncoder,
                    'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
    }

    # --- Step 2: Pre-train once per architecture ---
    print('\n--- Step 2: Pre-train on synthetic (seed=42) ---')
    pretrained_weights = {}
    for arch_name, arch_cfg in architectures.items():
        set_seed(42)
        model = arch_cfg['class'](**arch_cfg['kwargs'])
        syn_train_ld = DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True)
        syn_val_ld = DataLoader(syn_res_val_ds, batch_size=args.batch)
        ckpt_path = str(out / f'exp017_pretrain_{arch_name}.pth')
        train_loop(model, syn_train_ld, syn_val_ld,
                   lr=1e-3, epochs=args.epochs, patience=args.patience,
                   save_path=ckpt_path, label=f'pretrain-{arch_name}')
        load_best(model, ckpt_path)
        pretrained_weights[arch_name] = model.state_dict()
        print(f'  [{arch_name}] Pre-trained')

    # --- Step 3: Train 5 models per architecture, collect predictions ---
    print('\n--- Step 3: Train 5 models per architecture ---')
    from .schema import IDX_GLUCOSE, NORMALIZATION_SCALES
    glucose_scale = NORMALIZATION_SCALES['glucose']

    T = vr_res.shape[1]
    history_steps = T // 2

    for arch_name, arch_cfg in architectures.items():
        individual_forecasts = []  # per-seed forecast arrays
        individual_maes = []

        for seed in seeds:
            set_seed(seed)
            model = arch_cfg['class'](**arch_cfg['kwargs'])
            model.load_state_dict(pretrained_weights[arch_name])

            ckpt = str(out / f'exp017_{arch_name}_s{seed}.pth')
            train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
            val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

            train_loop(model, train_ld, val_ld,
                       lr=3e-4, epochs=args.epochs, patience=args.patience,
                       save_path=ckpt, label=f'{arch_name}-s{seed}')
            load_best(model, ckpt)

            # Get per-window glucose predictions for ensemble averaging
            model.eval()
            ds = torch.utils.data.TensorDataset(
                torch.FloatTensor(vr_res), torch.FloatTensor(vr_res))
            loader = DataLoader(ds, batch_size=64)

            all_pred_glucose = []
            idx = 0
            with torch.no_grad():
                for batch_in, _ in loader:
                    batch_in = batch_in.to(_DEFAULT_DEVICE, non_blocking=True)
                    recon = model(batch_in, causal=True)
                    B = recon.shape[0]
                    residual_recon = recon[:, :, 0].cpu().numpy()
                    for b in range(B):
                        i = idx + b
                        if i >= len(vr_phys):
                            break
                        pred_residual = residual_recon[b, history_steps:]
                        pred_glucose = residual_to_glucose(
                            pred_residual, vr_phys[i, history_steps:])
                        all_pred_glucose.append(pred_glucose)
                    idx += B

            pred_array = np.array(all_pred_glucose)  # (N, future_steps)
            individual_forecasts.append(pred_array)

            # Individual MAE
            actual_glucose = val_np[:len(pred_array), history_steps:, IDX_GLUCOSE] * glucose_scale
            mae = float(np.mean(np.abs(pred_array - actual_glucose)))
            individual_maes.append(round(mae, 2))
            print(f'  [{arch_name} s{seed}] forecast MAE={mae:.2f}')

            if os.path.exists(ckpt):
                os.remove(ckpt)

        # --- Ensemble: average predictions ---
        ensemble_pred = np.mean(individual_forecasts, axis=0)  # (N, future_steps)
        actual_glucose = val_np[:len(ensemble_pred), history_steps:, IDX_GLUCOSE] * glucose_scale
        ensemble_mae = float(np.mean(np.abs(ensemble_pred - actual_glucose)))
        ensemble_rmse = float(np.sqrt(np.mean((ensemble_pred - actual_glucose) ** 2)))

        # Per-horizon ensemble errors
        per_horizon = {}
        for step in range(ensemble_pred.shape[1]):
            minutes = (step + 1) * 5
            step_errors = np.abs(ensemble_pred[:, step] - actual_glucose[:, step])
            per_horizon[f'{minutes}min'] = round(float(np.mean(step_errors)), 2)

        # Prediction spread (uncertainty proxy)
        pred_std = np.std(individual_forecasts, axis=0)  # (N, future_steps)
        mean_spread = float(np.mean(pred_std)) * glucose_scale
        per_horizon_spread = {}
        for step in range(pred_std.shape[1]):
            minutes = (step + 1) * 5
            per_horizon_spread[f'{minutes}min'] = round(
                float(np.mean(pred_std[:, step])) * glucose_scale, 2)

        results[arch_name] = {
            'individual_maes': individual_maes,
            'individual_mean': round(float(np.mean(individual_maes)), 2),
            'individual_std': round(float(np.std(individual_maes)), 2),
            'ensemble_mae': round(ensemble_mae, 2),
            'ensemble_rmse': round(ensemble_rmse, 2),
            'ensemble_per_horizon': per_horizon,
            'mean_prediction_spread_mgdl': round(mean_spread, 2),
            'per_horizon_spread': per_horizon_spread,
        }

    # Cleanup pre-trained checkpoints
    for arch_name in architectures:
        p = str(out / f'exp017_pretrain_{arch_name}.pth')
        if os.path.exists(p):
            os.remove(p)

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # --- Summary ---
    print('\n' + '=' * 60)
    print('SUMMARY — Seed Ensemble (5 models)')
    print('=' * 60)

    for arch_name in ['ae', 'grouped']:
        ar = results[arch_name]
        print(f'\n  {arch_name.upper()}:')
        print(f'    Individual MAEs: {ar["individual_maes"]}')
        print(f'    Individual mean: {ar["individual_mean"]} ± {ar["individual_std"]}')
        print(f'    Ensemble MAE:    {ar["ensemble_mae"]}')
        improvement = (ar['individual_mean'] - ar['ensemble_mae']) / ar['individual_mean'] * 100
        print(f'    Ensemble vs mean: {improvement:+.1f}%')
        best_individual = min(ar['individual_maes'])
        vs_best = (best_individual - ar['ensemble_mae']) / best_individual * 100
        print(f'    Ensemble vs best single: {vs_best:+.1f}%')
        print(f'    Mean prediction spread: {ar["mean_prediction_spread_mgdl"]:.2f} mg/dL')

    ae_ens = results['ae']['ensemble_mae']
    gr_ens = results['grouped']['ensemble_mae']
    winner = 'Grouped' if gr_ens < ae_ens else 'AE'
    pct = abs(ae_ens - gr_ens) / max(ae_ens, gr_ens) * 100
    print(f'\n  Ensemble winner: {winner} ({pct:.1f}% better)')
    print(f'  Persistence: {p_mae:.2f}')
    print(f'  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp017_seed_ensemble.json'))
    return results


def run_transfer_longer_horizons(args):
    """EXP-018: Grouped+Transfer at Longer Horizons (2hr, 3hr).

    EXP-010b showed from scratch: AE wins at 1hr/2hr, Grouped wins at 3hr.
    EXP-015 showed transfer flips the 1hr result (Grouped wins with transfer).
    Does transfer help Grouped at all horizons?

    Tests both AE+transfer and Grouped+transfer at 1hr, 2hr, 3hr.
    """
    print('=' * 60)
    print('EXP-018: Transfer at Longer Horizons')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    results = {'experiment': 'EXP-018', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ')}

    set_seed(42)

    isf, cr = _load_patient_profile(args.real_data)
    print(f'  Patient: ISF={isf}, CR={cr}')
    results['patient'] = {'isf': isf, 'cr': cr}

    horizons = [12, 24, 36]  # 1hr, 2hr, 3hr
    results['horizons'] = [w * 5 for w in horizons]

    from .encoder import CGMDataset

    architectures = {
        'ae': {'class': CGMTransformerAE,
               'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
        'grouped': {'class': CGMGroupedEncoder,
                    'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2}},
    }

    horizon_results = {}

    for window in horizons:
        label = f'{window * 5}min'
        print(f'\n{"=" * 60}')
        print(f'  Horizon: {label} ({window} steps)')
        print(f'{"=" * 60}')

        # Load synthetic data at this horizon
        print(f'\n  --- Synthetic data at {label} ---')
        syn_t, syn_v = load_conformance_to_dataset(
            args.synth_dirs, task='forecast', window_size=window)
        has_synthetic = syn_t is not None and len(syn_t) > 0

        syn_res_train_ds = syn_res_val_ds = None
        if has_synthetic:
            syn_train_np = syn_t.vectors.numpy()
            syn_val_np = syn_v.vectors.numpy()
            syn_tr_res, _, _ = compute_residual_windows(
                syn_train_np, isf=isf, cr=cr, level='enhanced')
            syn_vr_res, _, _ = compute_residual_windows(
                syn_val_np, isf=isf, cr=cr, level='enhanced')
            syn_res_train_ds = CGMDataset(syn_tr_res, task='reconstruct', window_size=window)
            syn_res_val_ds = CGMDataset(syn_vr_res, task='reconstruct', window_size=window)
            print(f'  Synthetic: {len(syn_train_np)} train, {len(syn_val_np)} val')
        else:
            print(f'  WARNING: No synthetic data at {label}')

        # Load real data at this horizon
        print(f'\n  --- Real data at {label} ---')
        real_t, real_v = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window)
        if real_t is None or len(real_t) == 0:
            print(f'  No data for window={window}, skipping')
            continue

        train_np = real_t.vectors.numpy()
        val_np = real_v.vectors.numpy()
        print(f'  Real: {len(train_np)} train, {len(val_np)} val')

        tr_res, tr_phys, _ = compute_residual_windows(
            train_np, isf=isf, cr=cr, level='enhanced')
        vr_res, vr_phys, vr_stats = compute_residual_windows(
            val_np, isf=isf, cr=cr, level='enhanced')

        physics_metrics = _evaluate_physics_only(vr_phys, val_np)

        _, rv_2x = load_nightscout_to_dataset(
            args.real_data, task='forecast', window_size=window * 2)
        p_mae, p_rmse = persistence_baseline(rv_2x, window)

        real_res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=window)
        real_res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=window)

        horizon_entry = {
            'window_steps': window,
            'window_minutes': window * 5,
            'samples': {'train': len(train_np), 'val': len(val_np)},
            'physics_only': physics_metrics,
            'persistence': {'mae_mgdl': round(p_mae, 2)},
        }

        for arch_name, arch_cfg in architectures.items():
            arch_results = {}

            # --- Transfer: pre-train on synthetic, fine-tune on real ---
            if has_synthetic:
                set_seed(42)
                model = arch_cfg['class'](**arch_cfg['kwargs'])
                syn_train_ld = DataLoader(syn_res_train_ds, batch_size=args.batch, shuffle=True)
                syn_val_ld = DataLoader(syn_res_val_ds, batch_size=args.batch)
                pre_ckpt = str(out / f'exp018_pre_{arch_name}_{window}.pth')

                print(f'\n  --- Pre-train {arch_name} at {label} ---')
                train_loop(model, syn_train_ld, syn_val_ld,
                           lr=1e-3, epochs=args.epochs, patience=args.patience,
                           save_path=pre_ckpt, label=f'pre-{arch_name}-{label}')
                load_best(model, pre_ckpt)

                # Fine-tune
                print(f'  --- Fine-tune {arch_name} at {label} ---')
                ft_ckpt = str(out / f'exp018_ft_{arch_name}_{window}.pth')
                real_train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
                real_val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

                train_loop(model, real_train_ld, real_val_ld,
                           lr=3e-4, epochs=args.epochs, patience=args.patience,
                           save_path=ft_ckpt, label=f'ft-{arch_name}-{label}')
                load_best(model, ft_ckpt)

                recon = _evaluate_residual_model(model, vr_res, vr_phys, val_np)
                forecast = _evaluate_residual_future_only(
                    model, vr_res, vr_phys, val_np,
                    history_steps=window // 2)
                arch_results['transfer'] = {
                    'reconstruction': recon,
                    'future_only': forecast,
                }
                print(f'  [{arch_name} transfer {label}] recon={recon["mae_mgdl"]:.2f}  '
                      f'forecast={forecast["mae_mgdl"]:.2f}')

                # Cleanup
                for p in [pre_ckpt, ft_ckpt]:
                    if os.path.exists(p):
                        os.remove(p)

            # --- Scratch baseline ---
            set_seed(42)
            model = arch_cfg['class'](**arch_cfg['kwargs'])
            scratch_ckpt = str(out / f'exp018_scratch_{arch_name}_{window}.pth')
            real_train_ld = DataLoader(real_res_train_ds, batch_size=args.batch, shuffle=True)
            real_val_ld = DataLoader(real_res_val_ds, batch_size=args.batch)

            print(f'  --- Scratch {arch_name} at {label} ---')
            train_loop(model, real_train_ld, real_val_ld,
                       lr=1e-3, epochs=args.epochs, patience=args.patience,
                       save_path=scratch_ckpt, label=f'scratch-{arch_name}-{label}')
            load_best(model, scratch_ckpt)

            recon = _evaluate_residual_model(model, vr_res, vr_phys, val_np)
            forecast = _evaluate_residual_future_only(
                model, vr_res, vr_phys, val_np,
                history_steps=window // 2)
            arch_results['scratch'] = {
                'reconstruction': recon,
                'future_only': forecast,
            }
            print(f'  [{arch_name} scratch {label}] recon={recon["mae_mgdl"]:.2f}  '
                  f'forecast={forecast["mae_mgdl"]:.2f}')

            if os.path.exists(scratch_ckpt):
                os.remove(scratch_ckpt)

            horizon_entry[arch_name] = arch_results

        horizon_results[label] = horizon_entry

    results['horizons_detail'] = horizon_results

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)

    # --- Summary ---
    print('\n' + '=' * 60)
    print('SUMMARY — Transfer at Longer Horizons')
    print('=' * 60)

    print(f'\n  {"Horizon":<10s}  {"AE scratch":>12s}  {"AE transfer":>12s}  '
          f'{"Gr scratch":>12s}  {"Gr transfer":>12s}  {"Winner":>14s}')
    print(f'  {"-"*10}  {"-"*12}  {"-"*12}  {"-"*12}  {"-"*12}  {"-"*14}')

    for window in horizons:
        label = f'{window * 5}min'
        if label not in horizon_results:
            continue
        hr = horizon_results[label]
        ae_s = hr.get('ae', {}).get('scratch', {}).get('future_only', {}).get('mae_mgdl', 0)
        ae_t = hr.get('ae', {}).get('transfer', {}).get('future_only', {}).get('mae_mgdl', 0)
        gr_s = hr.get('grouped', {}).get('scratch', {}).get('future_only', {}).get('mae_mgdl', 0)
        gr_t = hr.get('grouped', {}).get('transfer', {}).get('future_only', {}).get('mae_mgdl', 0)

        vals = {'AE scratch': ae_s, 'AE transfer': ae_t,
                'Gr scratch': gr_s, 'Gr transfer': gr_t}
        winner = min(vals, key=vals.get) if any(v > 0 for v in vals.values()) else '?'
        print(f'  {label:<10s}  {ae_s:>12.2f}  {ae_t:>12.2f}  '
              f'{gr_s:>12.2f}  {gr_t:>12.2f}  {winner:>14s}')

    # Transfer improvement analysis
    print(f'\n  Transfer improvement (scratch → transfer):')
    for window in horizons:
        label = f'{window * 5}min'
        if label not in horizon_results:
            continue
        hr = horizon_results[label]
        for arch in ['ae', 'grouped']:
            s = hr.get(arch, {}).get('scratch', {}).get('future_only', {}).get('mae_mgdl', 0)
            t = hr.get(arch, {}).get('transfer', {}).get('future_only', {}).get('mae_mgdl', 0)
            if s > 0 and t > 0:
                pct = (s - t) / s * 100
                print(f'    {arch} {label}: {s:.2f} → {t:.2f} ({pct:+.1f}%)')

    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp018_transfer_horizons.json'))
    return results


# ─── EXP-019+: Multi-patient scale experiments ─────────────────────────


def _resolve_multipatient_paths(args):
    """Resolve patient training directories from --patients-dir or --real-data."""
    if hasattr(args, 'patients_dir') and args.patients_dir:
        base = args.patients_dir
        paths = sorted([
            os.path.join(base, p, 'training')
            for p in os.listdir(base)
            if os.path.isdir(os.path.join(base, p, 'training'))
        ])
        return paths
    return [args.real_data]


def _load_multipatient_profiles(patient_paths):
    """Load ISF/CR from each patient and return averages."""
    isfs, crs = [], []
    for p in patient_paths:
        parent = os.path.dirname(p)  # training/ → patient dir
        isf, cr = _load_patient_profile(parent)
        if isf == 40.0 and cr == 10.0:
            isf, cr = _load_patient_profile(p)
        isfs.append(isf)
        crs.append(cr)
    avg_isf = float(np.mean(isfs))
    avg_cr = float(np.mean(crs))
    return avg_isf, avg_cr, list(zip(isfs, crs))


def run_multipatient_cond_transfer(args):
    """EXP-019: Multi-Patient Conditioned Transfer — Revisiting EXP-006 at Scale.

    EXP-006 was a dead end: only 267 synthetic + 1,538 real conditioned windows.
    Now we have sweep-uva-250 (8K+ synthetic) and 10 patients (25K+ real).

    Steps:
      1. Pre-train Conditioned Transformer on sweep-uva-250 synthetic data
      2. Fine-tune on 10-patient real data (multi-patient conditioned windows)
      3. Train from scratch on same real data
      4. Compare transfer vs scratch vs persistence baselines
    """
    print('=' * 60)
    print('EXP-019: Multi-Patient Conditioned Transfer (Revisiting EXP-006 at Scale)')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    set_seed(42)

    results = {
        'experiment': 'EXP-019',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hypothesis': ('EXP-006 failed with 267 synth + 1538 real conditioned windows. '
                        'Now testing with sweep-uva-250 (8K+) + 10 patients (25K+). '
                        'Does 30x more synthetic + 17x more real fix conditioned transfer?'),
    }

    patient_paths = _resolve_multipatient_paths(args)
    n_patients = len(patient_paths)
    print(f'  Patients: {n_patients} training directories')
    results['n_patients'] = n_patients

    # --- Step 1: Pre-train on synthetic ---
    print('\n--- Step 1: Pre-train on synthetic (conditioned) ---')
    syn_t, syn_v = load_conformance_to_dataset(
        args.synth_dirs, window_size=args.window, conditioned=True)

    has_synth = syn_t is not None and len(syn_t) > 0
    results['has_synthetic'] = has_synth
    if has_synth:
        results['synthetic_samples'] = {'train': len(syn_t), 'val': len(syn_v)}
        print(f'  Synthetic: {len(syn_t)} train, {len(syn_v)} val')

        model_syn = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
        n_params = sum(p.numel() for p in model_syn.parameters())
        results['model_params'] = n_params
        print(f'  Model params: {n_params:,}')

        _train_conditioned(model_syn, syn_t, syn_v, lr=1e-3, epochs=args.epochs,
                           patience=args.patience,
                           save_path=str(out / 'exp019_cond_synth.pth'),
                           label='synthetic_pretrain', batch=args.batch)
    else:
        print('  WARNING: No synthetic conditioned vectors found.')

    # --- Step 2: Load multi-patient real data (conditioned) ---
    print('\n--- Step 2: Load multi-patient real data (conditioned) ---')
    if n_patients > 1:
        real_t, real_v = load_multipatient_nightscout(
            patient_paths, window_size=args.window, conditioned=True)
    else:
        real_t, real_v = load_nightscout_to_dataset(
            patient_paths[0], window_size=args.window, conditioned=True)
    results['real_samples'] = {'train': len(real_t), 'val': len(real_v)}
    print(f'  Real: {len(real_t)} train, {len(real_v)} val')

    # Persistence baseline (use first patient's data for consistency)
    _, rv_2x = load_nightscout_to_dataset(
        patient_paths[0], task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence baseline: MAE={p_mae:.2f}')

    real_vl = DataLoader(real_v, batch_size=args.batch)

    # --- Step 3: Zero-shot evaluation ---
    if has_synth:
        print('\n--- Step 3: Zero-shot (synthetic → real) ---')
        model_zs = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
        load_best(model_zs, str(out / 'exp019_cond_synth.pth'))
        results['zero_shot'] = evaluate_model(model_zs, real_vl, 'conditioned', args.window)
        print(f'  Zero-shot: MAE={results["zero_shot"]["mae_mgdl"]:.2f} mg/dL')

    # --- Step 4: Fine-tune (transfer) ---
    print('\n--- Step 4: Fine-tune on multi-patient real (transfer) ---')
    model_ft = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
    if has_synth:
        load_best(model_ft, str(out / 'exp019_cond_synth.pth'))
    _train_conditioned(model_ft, real_t, real_v, lr=5e-4, epochs=args.epochs,
                       patience=args.patience,
                       save_path=str(out / 'exp019_cond_transfer.pth'),
                       label='transfer', batch=args.batch, weight_decay=1e-4)

    # --- Step 5: From scratch with best regularization ---
    print('\n--- Step 5: From scratch with wd=1e-4 ---')
    model_sc = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
    _train_conditioned(model_sc, real_t, real_v, lr=5e-4, epochs=args.epochs,
                       patience=args.patience,
                       save_path=str(out / 'exp019_cond_scratch.pth'),
                       label='scratch', batch=args.batch, weight_decay=1e-4)

    # --- Step 6: Final comparison ---
    print('\n--- Results ---')
    load_best(model_ft, str(out / 'exp019_cond_transfer.pth'))
    results['transfer'] = evaluate_model(model_ft, real_vl, 'conditioned', args.window)

    load_best(model_sc, str(out / 'exp019_cond_scratch.pth'))
    results['scratch'] = evaluate_model(model_sc, real_vl, 'conditioned', args.window)

    # EXP-006 comparison context
    results['exp006_reference'] = {
        'note': 'EXP-006 had 267 synth + 1538 real → transfer 31.49, scratch 25.10, persist 19.01',
        'transfer_mae': 31.49,
        'scratch_mae': 25.10,
        'persistence_mae': 19.01,
    }

    # Print summary
    print(f'\n  {"Method":<20} {"MAE":>8} {"RMSE":>8}  vs Persistence')
    print(f'  {"-"*55}')
    persist_mae = results['persistence']['mae_mgdl']
    for label in ['transfer', 'scratch']:
        m = results[label]
        pct = (m['mae_mgdl'] - persist_mae) / persist_mae * 100
        mark = '✓' if pct < 0 else '✗'
        print(f'  {label:<20} {m["mae_mgdl"]:>8.2f} {m["rmse_mgdl"]:>8.2f}  '
              f'{pct:+.1f}% {mark}')
    if has_synth:
        m = results['zero_shot']
        pct = (m['mae_mgdl'] - persist_mae) / persist_mae * 100
        mark = '✓' if pct < 0 else '✗'
        print(f'  {"zero_shot":<20} {m["mae_mgdl"]:>8.2f} {m["rmse_mgdl"]:>8.2f}  '
              f'{pct:+.1f}% {mark}')
    print(f'  {"persistence":<20} {persist_mae:>8.2f}')

    # Comparison to EXP-006
    print(f'\n  --- vs EXP-006 (267 synth, 1538 real) ---')
    t_now = results['transfer']['mae_mgdl']
    s_now = results['scratch']['mae_mgdl']
    print(f'  Transfer: {31.49:.2f} → {t_now:.2f} '
          f'({"improved" if t_now < 31.49 else "worse"})')
    print(f'  Scratch:  {25.10:.2f} → {s_now:.2f} '
          f'({"improved" if s_now < 25.10 else "worse"})')
    if has_synth and t_now < s_now:
        print(f'  ✓ Transfer now HELPS (was harmful in EXP-006)')
    elif has_synth:
        print(f'  ✗ Transfer still hurts (but gap may have narrowed)')

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp019_multipatient_cond_transfer.json'))
    return results


def run_multipatient_diffusion(args):
    """EXP-020: Diffusion at Multi-Patient Scale — Revisiting EXP-016.

    EXP-016 was a dead end: 857K params vs 3K windows, toy forward process.
    Now we have 10 patients (32K+ windows) and GPU for faster iteration.
    Tests whether 10× more data and proper training fix DDPM.
    """
    print('=' * 60)
    print('EXP-020: Multi-Patient Diffusion Benchmark (Revisiting EXP-016 at Scale)')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)
    set_seed(42)

    results = {
        'experiment': 'EXP-020',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hypothesis': ('EXP-016 DDPM failed at 3K windows (28.66 MAE, worse than persistence). '
                        'Testing with 10-patient multi-patient data (32K+ windows). '
                        'Does 10x more data rescue diffusion?'),
    }

    patient_paths = _resolve_multipatient_paths(args)
    n_patients = len(patient_paths)
    print(f'  Patients: {n_patients} training directories')
    results['n_patients'] = n_patients

    # Load multi-patient data (forecast mode for residual computation)
    print('\n--- Step 1: Load multi-patient data + residuals ---')
    if n_patients > 1:
        real_t, real_v = load_multipatient_nightscout(
            patient_paths, window_size=args.window)
    else:
        real_t, real_v = load_nightscout_to_dataset(
            patient_paths[0], task='forecast', window_size=args.window)

    train_np = real_t.vectors.numpy()
    val_np = real_v.vectors.numpy()
    results['samples'] = {'train': len(train_np), 'val': len(val_np)}
    print(f'  Windows: {len(train_np)} train, {len(val_np)} val')

    # Use average profile for physics (multi-patient approximation)
    avg_isf, avg_cr, patient_profiles = _load_multipatient_profiles(patient_paths)
    results['avg_profile'] = {'isf': avg_isf, 'cr': avg_cr}
    print(f'  Avg profile: ISF={avg_isf:.1f}, CR={avg_cr:.1f}')

    tr_res, tr_phys, tr_stats = compute_residual_windows(
        train_np, isf=avg_isf, cr=avg_cr, level='enhanced')
    vr_res, vr_phys, _ = compute_residual_windows(
        val_np, isf=avg_isf, cr=avg_cr, level='enhanced')
    print(f'  Residual std: {tr_stats["std"]:.1f} mg/dL')

    physics_metrics = _evaluate_physics_only(vr_phys, val_np)
    results['physics_only'] = physics_metrics
    print(f'  Physics-only: MAE={physics_metrics["mae_mgdl"]:.2f}')

    # Persistence baseline
    _, rv_2x = load_nightscout_to_dataset(
        patient_paths[0], task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence: MAE={p_mae:.2f}')

    from .encoder import CGMDataset
    res_train_ds = CGMDataset(tr_res, task='reconstruct', window_size=args.window)
    res_val_ds = CGMDataset(vr_res, task='reconstruct', window_size=args.window)
    use_pin = _DEFAULT_DEVICE.type == 'cuda'
    train_ld = DataLoader(res_train_ds, batch_size=args.batch, shuffle=True, pin_memory=use_pin)
    val_ld = DataLoader(res_val_ds, batch_size=args.batch, pin_memory=use_pin)

    # --- Train DDPM ---
    print('\n--- Step 2: Train DDPM ---')
    from .toolbox import CGMDenoisingDiffusion

    diffusion_timesteps = 200
    model = CGMDenoisingDiffusion(
        input_dim=8, d_model=64, nhead=4, timesteps=diffusion_timesteps)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'  DDPM params: {n_params:,} (timesteps={diffusion_timesteps})')
    results['ddpm_params'] = n_params
    results['diffusion_timesteps'] = diffusion_timesteps

    device = _DEFAULT_DEVICE
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    best_val = float('inf')
    stale = 0
    ckpt_path = str(out / 'exp020_ddpm.pth')

    for ep in range(args.epochs):
        tl = _train_diffusion_epoch(model, train_ld, optimizer)
        vl = _eval_diffusion(model, val_ld)
        sched.step(vl)

        if vl < best_val:
            best_val = vl
            stale = 0
            os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
            torch.save({'epoch': ep, 'model_state': model.state_dict(),
                        'val_loss': vl}, ckpt_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == args.epochs - 1:
            lr_now = optimizer.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [DDPM] Epoch {ep+1:3d}/{args.epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best_val:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if args.patience > 0 and stale >= args.patience:
            print(f'  [DDPM] Early stop at epoch {ep+1}')
            break

    results['ddpm_training'] = {'best_val_loss': round(best_val, 6),
                                'best_epoch': ep}

    # --- Evaluate DDPM forecast ---
    print('\n--- Step 3: Evaluate DDPM forecast ---')
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt['model_state'])

    ddpm_forecast = _evaluate_diffusion_forecast(
        model, vr_res, vr_phys, val_np,
        history_steps=args.window // 2, n_samples=20)
    results['ddpm_forecast'] = ddpm_forecast
    ddpm_mae = ddpm_forecast['mae_mgdl']
    ddpm_rmse = ddpm_forecast.get('rmse_mgdl', 0)
    print(f'  DDPM: MAE={ddpm_mae:.2f}, RMSE={ddpm_rmse:.2f}')

    # --- Train baselines (AE + Grouped) for comparison ---
    print('\n--- Step 4: Train AE + Grouped baselines ---')
    for arch_name, arch_cls in [('ae', CGMTransformerAE), ('grouped', CGMGroupedEncoder)]:
        model_b = arch_cls(input_dim=8, d_model=64, nhead=4)
        _train_residual_model(
            model_b, res_train_ds, res_val_ds, arch_name, args,
            save_path=str(out / f'exp020_{arch_name}.pth'))
        load_best(model_b, str(out / f'exp020_{arch_name}.pth'))
        baseline_vl = DataLoader(res_val_ds, batch_size=args.batch)
        results[arch_name] = evaluate_model(model_b, baseline_vl, arch_name, args.window)
        print(f'  {arch_name}: MAE={results[arch_name]["mae_mgdl"]:.2f}')

    # --- Summary ---
    print(f'\n  === EXP-020 Summary (Multi-Patient Diffusion) ===')
    persist_mae = results['persistence']['mae_mgdl']
    print(f'  {"Method":<20} {"MAE":>8}  vs Persistence  vs EXP-016')
    print(f'  {"-"*60}')
    ddpm_016 = 28.66
    print(f'  {"DDPM (multi)":<20} {ddpm_mae:>8.2f}  '
          f'{(ddpm_mae - persist_mae)/persist_mae*100:+.1f}%         '
          f'{ddpm_mae - ddpm_016:+.2f}')
    print(f'  {"DDPM (EXP-016)":<20} {ddpm_016:>8.2f}  (reference)')
    print(f'  {"Persistence":<20} {persist_mae:>8.2f}')

    results['exp016_reference'] = {
        'ddpm_mae': 28.66,
        'persistence_mae': 19.01,
        'samples_train': 3085,
    }

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp020_multipatient_diffusion.json'))
    return results


def _train_residual_model(model, train_ds, val_ds, arch_name, args, save_path):
    """Train an AE/Grouped model on residual data (shared helper)."""
    device = _DEFAULT_DEVICE
    model.to(device)
    use_pin = device.type == 'cuda'
    train_ld = DataLoader(train_ds, batch_size=args.batch, shuffle=True, pin_memory=use_pin)
    val_ld = DataLoader(val_ds, batch_size=args.batch, pin_memory=use_pin)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    criterion = nn.MSELoss()
    best_val = float('inf')
    stale = 0

    for ep in range(args.epochs):
        tl = train_one_epoch(model, train_ld, optimizer, criterion)
        vl = eval_loss(model, val_ld, criterion)
        sched.step(vl)
        if vl < best_val:
            best_val = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save({'epoch': ep, 'model_state': model.state_dict(),
                        'val_loss': vl}, save_path)
        else:
            stale += 1
        if args.patience > 0 and stale >= args.patience:
            break


def run_multiseed_conditioned(args):
    """EXP-021: Multi-Seed Robustness of Conditioned Transformer.

    EXP-019 showed 14.8 MAE on seed=42. Verify this is stable across
    5 seeds to confirm the Conditioned Transformer is reliably useful.
    """
    print('=' * 60)
    print('EXP-021: Multi-Seed Robustness — Conditioned Transformer')
    print('=' * 60)
    t0 = time.time()
    out = Path(args.output_dir)

    seeds = [42, 123, 456, 789, 1024]
    results = {
        'experiment': 'EXP-021',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hypothesis': ('EXP-019 got 14.8 MAE on seed=42. Is this stable '
                       'across seeds or a lucky initialization?'),
        'seeds': seeds,
    }

    # --- Load data ONCE (deterministic) ---
    print('\n--- Loading multi-patient conditioned data (shared across seeds) ---')
    patient_paths = _resolve_multipatient_paths(args)
    n_patients = len(patient_paths)
    print(f'  Patients: {n_patients} training directories')
    results['n_patients'] = n_patients

    if n_patients > 1:
        real_t, real_v = load_multipatient_nightscout(
            patient_paths, window_size=args.window, conditioned=True)
    else:
        real_t, real_v = load_nightscout_to_dataset(
            patient_paths[0], window_size=args.window, conditioned=True)
    results['samples'] = {'train': len(real_t), 'val': len(real_v)}
    print(f'  Windows: {len(real_t)} train, {len(real_v)} val')

    # Persistence baseline (deterministic)
    _, rv_2x = load_nightscout_to_dataset(
        patient_paths[0], task='forecast', window_size=args.window * 2)
    p_mae, p_rmse = persistence_baseline(rv_2x, args.window)
    results['persistence'] = {'mae_mgdl': round(p_mae, 2), 'rmse_mgdl': round(p_rmse, 2)}
    print(f'  Persistence baseline: MAE={p_mae:.2f}')

    # --- Run per-seed ---
    seed_maes = []
    seed_rmses = []
    seed_details = {}

    for i, seed in enumerate(seeds):
        print(f'\n{"─" * 60}')
        print(f'  Seed {seed} ({i+1}/{len(seeds)})')
        print(f'{"─" * 60}')
        set_seed(seed)

        model = ConditionedTransformer(history_dim=8, action_dim=3, d_model=64)
        if i == 0:
            n_params = sum(p.numel() for p in model.parameters())
            results['model_params'] = n_params
            print(f'  Model params: {n_params:,}')

        ckpt_path = str(out / f'exp021_cond_s{seed}.pth')
        best_val, epochs_run = _train_conditioned(
            model, real_t, real_v, lr=5e-4, epochs=args.epochs,
            patience=args.patience, save_path=ckpt_path,
            label=f'seed-{seed}', batch=args.batch, weight_decay=1e-4)

        # Reload best and evaluate
        load_best(model, ckpt_path)
        val_ld = DataLoader(real_v, batch_size=args.batch)
        metrics = evaluate_model(model, val_ld, 'conditioned', args.window)

        seed_maes.append(metrics['mae_mgdl'])
        seed_rmses.append(metrics['rmse_mgdl'])
        seed_details[str(seed)] = {
            'mae_mgdl': metrics['mae_mgdl'],
            'rmse_mgdl': metrics['rmse_mgdl'],
            'best_val_loss': round(best_val, 6),
            'epochs_run': epochs_run,
        }
        print(f'  Seed {seed}: MAE={metrics["mae_mgdl"]:.2f}, '
              f'RMSE={metrics["rmse_mgdl"]:.2f}, val_loss={best_val:.6f}')

    # --- Summary ---
    import numpy as np
    mae_arr = np.array(seed_maes)
    rmse_arr = np.array(seed_rmses)

    results['seed_details'] = seed_details
    results['summary'] = {
        'mae_mean': round(float(mae_arr.mean()), 2),
        'mae_std': round(float(mae_arr.std()), 2),
        'mae_min': round(float(mae_arr.min()), 2),
        'mae_max': round(float(mae_arr.max()), 2),
        'rmse_mean': round(float(rmse_arr.mean()), 2),
        'rmse_std': round(float(rmse_arr.std()), 2),
    }
    results['exp019_reference'] = {
        'note': 'EXP-019 seed=42: scratch 14.76, transfer 14.81, persistence 26.92',
        'scratch_mae': 14.76,
        'transfer_mae': 14.81,
    }

    print(f'\n  === EXP-021 Summary ===')
    print(f'  Conditioned Transformer across {len(seeds)} seeds:')
    print(f'  MAE: {mae_arr.mean():.2f} ± {mae_arr.std():.2f} mg/dL '
          f'(range: {mae_arr.min():.2f} – {mae_arr.max():.2f})')
    print(f'  RMSE: {rmse_arr.mean():.2f} ± {rmse_arr.std():.2f} mg/dL')
    pct = (mae_arr.mean() - p_mae) / p_mae * 100
    print(f'  vs Persistence ({p_mae:.2f}): {pct:+.1f}%')
    if mae_arr.std() < 2.0:
        print(f'  ✓ STABLE — std={mae_arr.std():.2f} < 2.0 mg/dL')
    else:
        print(f'  ✗ UNSTABLE — std={mae_arr.std():.2f} ≥ 2.0 mg/dL')

    elapsed = time.time() - t0
    results['elapsed_seconds'] = round(elapsed, 1)
    print(f'\n  Total time: {elapsed:.0f}s')

    save_results(results, str(out / 'exp021_multiseed_conditioned.json'))
    return results



def _build_legacy_registry():
    """Map legacy experiment names to local functions."""
    return {
        'transfer': run_transfer,
        'conditioned': run_conditioned,
        'cond-transfer': run_conditioned_transfer,
        'residual': run_residual,
        'physics-compare': run_physics_comparison,
        'residual-transfer': run_residual_transfer,
        'longer-horizons': run_longer_horizons,
        'walkforward': run_walkforward,
        'grouped-benchmark': run_grouped_benchmark,
        'grouped-transfer': run_grouped_transfer,
        'causal-longer-horizons': run_causal_longer_horizons,
        'multiseed': run_multiseed_robustness,
        'walkforward-transfer': run_walkforward_grouped_transfer,
        'multiseed-transfer': run_multiseed_transfer,
        'diffusion-benchmark': run_diffusion_benchmark,
        'seed-ensemble': run_seed_ensemble,
        'transfer-horizons': run_transfer_longer_horizons,
        'multipatient-cond-transfer': run_multipatient_cond_transfer,
        'multipatient-diffusion': run_multipatient_diffusion,
        'multiseed-conditioned': run_multiseed_conditioned,
    }


def _build_full_registry():
    """Merge legacy + agentic + archived experiment registries."""
    registry = _build_legacy_registry()
    # Import active agentic experiments (experiments_agentic.py)
    try:
        from . import experiments_agentic as _agentic
        for key, func_name in _agentic.REGISTRY.items():
            registry[key] = getattr(_agentic, func_name)
    except ImportError:
        pass
    # Import archived experiments on demand
    for archive_module in [
        'experiments_archive_r1_r13',
        'experiments_archive_r14_r30',
    ]:
        try:
            mod = __import__(f'tools.cgmencode.{archive_module}', fromlist=['ARCHIVE_REGISTRY'])
            for key, func_name in getattr(mod, 'ARCHIVE_REGISTRY', {}).items():
                if key not in registry:  # active experiments take precedence
                    registry[key] = getattr(mod, func_name)
        except (ImportError, AttributeError):
            pass
    return registry


def main():
    registry = _build_full_registry()
    all_choices = sorted(registry.keys()) + ['all']

    parser = argparse.ArgumentParser(
        description='Run cgmencode experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Agentic experiments (EXP-026+) live in experiments_agentic.py\n'
               'Legacy experiments (EXP-001-025) live in this file.')
    parser.add_argument('experiment', choices=all_choices,
                        help='Which experiment to run')
    parser.add_argument('--real-data', required=True,
                        help='Path to Nightscout JSON directory')
    parser.add_argument('--patients-dir', default=None,
                        help='Auto-expand patient training dirs (e.g. externals/ns-data/patients)')
    parser.add_argument('--synth-dirs', nargs='+', default=DEFAULT_SYNTH_DIRS,
                        help='Synthetic data directories')
    parser.add_argument('--output-dir', default='externals/experiments',
                        help='Directory for checkpoints and results')
    parser.add_argument('--uva-predictions', default=None,
                        help='Path to UVA/Padova predictions JSON (from uva_replay.js)')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--window', type=int, default=12,
                        help='History window in 5-min steps (default: 12 = 1 hour)')
    parser.add_argument('--patience', type=int, default=15,
                        help='Early stopping patience (0=disabled)')
    add_device_arg(parser)
    args = parser.parse_args()

    # Resolve compute device — shared with experiment_lib
    args.resolved_device = resolve_device(args.device)
    set_default_device(args.resolved_device)
    from . import experiment_lib as _lib
    _lib.set_device(args.resolved_device)
    print(f'Device: {args.resolved_device}')

    os.makedirs(args.output_dir, exist_ok=True)

    exp = args.experiment
    if exp == 'all':
        # Run legacy experiments only (agentic have dependencies)
        for name, func in _build_legacy_registry().items():
            func(args)
    elif exp in registry:
        registry[exp](args)
    else:
        print(f'Unknown experiment: {exp}')
        sys.exit(1)


if __name__ == '__main__':
    main()
