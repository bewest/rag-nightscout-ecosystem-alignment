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
import sys
import time
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader

from .model import CGMTransformerAE, train_one_epoch, eval_loss
from .toolbox import ConditionedTransformer
from .sim_adapter import load_conformance_to_dataset
from .real_data_adapter import load_nightscout_to_dataset, load_nightscout_grid_timestamps
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


def save_results(results, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'  Results → {path}')


def train_loop(model, train_ld, val_ld, lr, epochs, save_path, label,
               weight_decay=1e-5, patience=15, lr_patience=5):
    """Standard training loop with LR scheduling and early stopping.
    Returns (best_val_loss, epochs_run)."""
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


def load_best(model, path):
    """Load best checkpoint into model."""
    ckpt = torch.load(path, map_location='cpu', weights_only=True)
    model.load_state_dict(ckpt['model_state'])
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
    real_tl = DataLoader(real_t, batch_size=args.batch, shuffle=True)
    real_vl = DataLoader(real_v, batch_size=args.batch)

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
        ckpt = torch.load(save_path, map_location='cpu', weights_only=True)
        model.load_state_dict(ckpt['model_state'])
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
                       save_path, label, batch=32, weight_decay=1e-5):
    """Train a ConditionedTransformer with standard loop. Returns (best_val, epochs_run)."""
    train_ld = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_ld = DataLoader(val_ds, batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    for ep in range(epochs):
        model.train()
        total = 0; n = 0
        for batch_data in train_ld:
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
    all_pred_glucose = []
    all_actual_glucose = []

    ds = torch.utils.data.TensorDataset(
        torch.FloatTensor(val_windows_residual),
        torch.FloatTensor(val_windows_residual))
    loader = DataLoader(ds, batch_size=64)

    idx = 0
    with torch.no_grad():
        for batch_in, _ in loader:
            recon = model(batch_in)  # (B, T, 8)
            B = recon.shape[0]

            # Extract reconstructed residual (channel 0)
            residual_recon = recon[:, :, 0].numpy()  # (B, T) normalized

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


def main():
    parser = argparse.ArgumentParser(
        description='Run cgmencode experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('experiment',
                        choices=['transfer', 'conditioned', 'cond-transfer',
                                 'residual', 'physics-compare',
                                 'residual-transfer', 'longer-horizons', 'all'],
                        help='Which experiment to run')
    parser.add_argument('--real-data', required=True,
                        help='Path to Nightscout JSON directory')
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
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if args.experiment in ('transfer', 'all'):
        run_transfer(args)
    if args.experiment in ('conditioned', 'all'):
        run_conditioned(args)
    if args.experiment in ('cond-transfer', 'all'):
        run_conditioned_transfer(args)
    if args.experiment in ('residual', 'all'):
        run_residual(args)
    if args.experiment in ('physics-compare', 'all'):
        run_physics_comparison(args)
    if args.experiment in ('residual-transfer', 'all'):
        run_residual_transfer(args)
    if args.experiment in ('longer-horizons', 'all'):
        run_longer_horizons(args)


if __name__ == '__main__':
    main()
