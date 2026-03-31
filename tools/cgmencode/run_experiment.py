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
from .real_data_adapter import load_nightscout_to_dataset
from .evaluate import evaluate_model, persistence_baseline
from .physics_model import compute_residual_windows, residual_to_glucose, RESIDUAL_SCALE

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


def main():
    parser = argparse.ArgumentParser(
        description='Run cgmencode experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('experiment',
                        choices=['transfer', 'conditioned', 'cond-transfer', 'residual', 'all'],
                        help='Which experiment to run')
    parser.add_argument('--real-data', required=True,
                        help='Path to Nightscout JSON directory')
    parser.add_argument('--synth-dirs', nargs='+', default=DEFAULT_SYNTH_DIRS,
                        help='Synthetic data directories')
    parser.add_argument('--output-dir', default='externals/experiments',
                        help='Directory for checkpoints and results')
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


if __name__ == '__main__':
    main()
