#!/usr/bin/env python3
"""Autonomous experiment runner for cgmencode Gen-3 optimization.

Runs a sweep of hyperparameter configurations, evaluates each, and
selects the best. Designed to be left running unattended on GPU.

Usage:
    # Quick sweep (3 configs, 1 seed each)
    python -m tools.cgmencode.run_experiments --sweep quick --name exp160

    # Full sweep (all configs, 3 seeds each)
    python -m tools.cgmencode.run_experiments --sweep full --name exp160

    # Custom single experiment
    python -m tools.cgmencode.run_experiments --d-model 128 --num-layers 4 \
        --dropout 0.2 --weight-decay 1e-4 --name exp_custom
"""
import argparse
import itertools
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import torch

from tools.cgmencode.device import resolve_device
from tools.cgmencode.experiment_lib import (
    create_model,
    forecast_mse,
    mask_future_channels,
    persistence_mse,
    set_device,
    set_seed,
    train_forecast,
)
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout


# ── Experiment Configuration Space ──────────────────────────────────────

QUICK_SWEEP = [
    # Baseline Gen-3 (already run as exp159, re-run for consistency)
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'baseline'},
    # Higher regularization (address 21f overfitting)
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.2,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'high_reg'},
    # Smaller model (fewer params, less overfitting)
    {'d_model': 64, 'nhead': 4, 'num_layers': 3, 'dropout': 0.15,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'small_reg'},
]

FULL_SWEEP = [
    # ── Model Size ──
    {'d_model': 64,  'nhead': 4, 'num_layers': 2, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'tiny'},
    {'d_model': 64,  'nhead': 4, 'num_layers': 3, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'small'},
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'medium'},
    {'d_model': 128, 'nhead': 8, 'num_layers': 4, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'large'},
    {'d_model': 256, 'nhead': 8, 'num_layers': 3, 'dropout': 0.1,
     'weight_decay': 1e-5, 'lr': 1e-3, 'label': 'xlarge'},

    # ── Regularization ──
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.2,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'med_highreg'},
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.3,
     'weight_decay': 1e-3, 'lr': 1e-3, 'label': 'med_maxreg'},
    {'d_model': 64,  'nhead': 4, 'num_layers': 3, 'dropout': 0.2,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'small_highreg'},

    # ── Learning Rate ──
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.15,
     'weight_decay': 1e-4, 'lr': 5e-4, 'label': 'med_slowlr'},
    {'d_model': 128, 'nhead': 8, 'num_layers': 3, 'dropout': 0.15,
     'weight_decay': 1e-4, 'lr': 2e-3, 'label': 'med_fastlr'},

    # ── Depth vs Width ──
    {'d_model': 64,  'nhead': 4, 'num_layers': 6, 'dropout': 0.15,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'deep_narrow'},
    {'d_model': 256, 'nhead': 8, 'num_layers': 2, 'dropout': 0.15,
     'weight_decay': 1e-4, 'lr': 1e-3, 'label': 'shallow_wide'},
]


def discover_patients(patients_dir):
    """Find all patient training directories."""
    return sorted([
        os.path.join(patients_dir, d, 'training')
        for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d, 'training'))
        and os.path.exists(os.path.join(patients_dir, d, 'training', 'entries.json'))
    ])


def run_single_config(config, feature_mode, patient_paths, data_cache, args):
    """Train one configuration and return results."""
    label = config['label']
    t0 = time.time()

    # Use cached data
    cache_key = f'{feature_mode}f'
    if cache_key not in data_cache:
        if feature_mode == 8:
            data_cache[cache_key] = load_multipatient_nightscout(
                patient_paths, task='forecast', window_size=args.window)
        else:
            data_cache[cache_key] = load_multipatient_nightscout(
                patient_paths, task='forecast', window_size=args.window,
                extended_features=True)

    train_ds, val_ds = data_cache[cache_key]
    if train_ds is None:
        return None

    input_dim = train_ds[0][0].shape[-1] if feature_mode != 8 else 8

    # Persistence baseline (cached)
    persist_key = f'persist_{cache_key}'
    if persist_key not in data_cache:
        data_cache[persist_key] = persistence_mse(val_ds)
    persist = data_cache[persist_key]

    use_semantic = (feature_mode != 8)
    seed_results = {}

    for seed in args.seeds:
        set_seed(seed)
        model = create_model(
            'grouped', input_dim=input_dim,
            d_model=config['d_model'], nhead=config['nhead'],
            num_layers=config['num_layers'],
            semantic_groups=use_semantic,
        )
        # Override dropout if specified
        if 'dropout' in config:
            for module in model.modules():
                if isinstance(module, torch.nn.Dropout):
                    module.p = config['dropout']

        n_params = sum(p.numel() for p in model.parameters())

        ckpt_path = os.path.join(
            args.output_dir,
            f'{args.name}_{cache_key}_{label}_s{seed}.pth')

        best_val, epochs_run = train_forecast(
            model, train_ds, val_ds, ckpt_path,
            label=f'{cache_key}-{label}-s{seed}',
            lr=config.get('lr', 1e-3),
            epochs=args.epochs,
            batch=args.batch,
            patience=args.patience,
            weight_decay=config.get('weight_decay', 1e-5),
        )

        val_mse = forecast_mse(model, val_ds, mask_future=True)
        val_mae = np.sqrt(val_mse) * 400.0

        seed_results[str(seed)] = {
            'best_val_loss': float(best_val),
            'epochs_run': epochs_run,
            'forecast_mse': float(val_mse),
            'mae_mgdl': round(float(val_mae), 2),
        }
        print(f'    {label} s{seed}: MAE={val_mae:.1f} mg/dL ({epochs_run} epochs)')

    mses = [s['forecast_mse'] for s in seed_results.values()]
    maes = [s['mae_mgdl'] for s in seed_results.values()]

    return {
        'config': config,
        'feature_mode': feature_mode,
        'input_dim': input_dim,
        'n_params': n_params,
        'n_train': len(train_ds),
        'n_val': len(val_ds),
        'persistence_mse': float(persist),
        'seeds': seed_results,
        'aggregate': {
            'mean_mse': round(float(np.mean(mses)), 6),
            'std_mse': round(float(np.std(mses)), 6),
            'mean_mae': round(float(np.mean(maes)), 1),
            'std_mae': round(float(np.std(maes)), 1),
            'vs_persistence': round(float(1.0 - np.mean(mses) / persist) * 100, 1),
        },
        'elapsed_seconds': round(time.time() - t0, 1),
    }


def main():
    parser = argparse.ArgumentParser(
        description='Autonomous experiment runner for Gen-3 optimization')
    parser.add_argument('--sweep', choices=['quick', 'full', 'none'],
                        default='none', help='Predefined sweep to run')
    parser.add_argument('--features', type=int, nargs='+', default=[21],
                        help='Feature modes to test (default: 21)')
    parser.add_argument('--name', type=str, default='exp_sweep',
                        help='Experiment name prefix')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    parser.add_argument('--output-dir', type=str,
                        default='externals/experiments')
    parser.add_argument('--window', type=int, default=24)
    parser.add_argument('--epochs', type=int, default=150)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--patience', type=int, default=25)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42])
    parser.add_argument('--device', type=str, default='auto')

    # Single-config overrides
    parser.add_argument('--d-model', type=int, default=128)
    parser.add_argument('--nhead', type=int, default=8)
    parser.add_argument('--num-layers', type=int, default=3)
    parser.add_argument('--dropout', type=float, default=0.1)
    parser.add_argument('--weight-decay', type=float, default=1e-5)
    parser.add_argument('--lr', type=float, default=1e-3)

    args = parser.parse_args()

    device = resolve_device(args.device)
    set_device(device)
    print(f'Device: {device}')
    print(f'Started: {datetime.now().isoformat()}')

    patient_paths = discover_patients(args.patients_dir)
    print(f'Patients: {len(patient_paths)}')

    os.makedirs(args.output_dir, exist_ok=True)

    # Build config list
    if args.sweep == 'quick':
        configs = QUICK_SWEEP
    elif args.sweep == 'full':
        configs = FULL_SWEEP
    else:
        configs = [{
            'd_model': args.d_model, 'nhead': args.nhead,
            'num_layers': args.num_layers, 'dropout': args.dropout,
            'weight_decay': args.weight_decay, 'lr': args.lr,
            'label': 'custom',
        }]

    data_cache = {}
    all_results = {}
    total_t0 = time.time()

    for feat_mode in args.features:
        print(f'\n{"="*60}')
        print(f'  {feat_mode}-Feature Sweep ({len(configs)} configs × {len(args.seeds)} seeds)')
        print(f'{"="*60}')

        for i, config in enumerate(configs):
            print(f'\n  [{i+1}/{len(configs)}] {config["label"]} '
                  f'(d={config["d_model"]}, L={config["num_layers"]}, '
                  f'drop={config.get("dropout", 0.1)}, wd={config.get("weight_decay", 1e-5)})')
            result = run_single_config(
                config, feat_mode, patient_paths, data_cache, args)
            if result:
                key = f'{feat_mode}f_{config["label"]}'
                all_results[key] = result

    # Save all results
    output_path = os.path.join(args.output_dir, f'{args.name}_results.json')
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f'\nResults saved: {output_path}')

    # Rank by MAE
    print(f'\n{"="*60}')
    print(f'  RANKING (by MAE)')
    print(f'{"="*60}')

    ranked = sorted(all_results.items(), key=lambda x: x[1]['aggregate']['mean_mae'])
    for rank, (key, res) in enumerate(ranked, 1):
        agg = res['aggregate']
        cfg = res['config']
        print(f'  #{rank}: {key}  MAE={agg["mean_mae"]:.1f}±{agg["std_mae"]:.1f} mg/dL  '
              f'({agg["vs_persistence"]:.1f}% vs persist)  '
              f'{res["n_params"]:,} params')

    best_key = ranked[0][0]
    best = ranked[0][1]
    print(f'\n  BEST: {best_key}')
    print(f'  MAE={best["aggregate"]["mean_mae"]:.1f} mg/dL '
          f'({best["aggregate"]["vs_persistence"]:.1f}% vs persistence)')
    print(f'  Config: d_model={best["config"]["d_model"]}, '
          f'layers={best["config"]["num_layers"]}, '
          f'dropout={best["config"].get("dropout", 0.1)}, '
          f'wd={best["config"].get("weight_decay", 1e-5)}')

    total_time = time.time() - total_t0
    print(f'\n  Total time: {total_time/60:.1f} minutes')
    print(f'  Finished: {datetime.now().isoformat()}')


if __name__ == '__main__':
    main()
