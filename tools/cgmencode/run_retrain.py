#!/usr/bin/env python3
"""Retrain cgmencode models with configurable feature sets.

Usage:
    # 8-feature baseline with timezone fix
    python -m tools.cgmencode.run_retrain --features 8 --name exp155

    # 21-feature extended (CAGE/SAGE + monthly phase)
    python -m tools.cgmencode.run_retrain --features 21 --name exp156b

    # Both experiments
    python -m tools.cgmencode.run_retrain --features 8 21 --name exp157

    # Custom training params
    python -m tools.cgmencode.run_retrain --features 21 --epochs 100 --patience 20 --num-layers 4
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch

from tools.cgmencode.device import resolve_device
from tools.cgmencode.experiment_lib import (
    build_16f_windows,
    create_model,
    forecast_mse,
    persistence_mse,
    set_device,
    set_seed,
    train_forecast,
    windows_to_datasets,
)
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout


def discover_patients(patients_dir):
    """Find all patient training directories."""
    patients = sorted([
        os.path.join(patients_dir, d, 'training')
        for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d, 'training'))
        and os.path.exists(os.path.join(patients_dir, d, 'training', 'entries.json'))
    ])
    return patients


def run_experiment(feature_mode, patient_paths, args):
    """Run a single experiment configuration across multiple seeds.

    Returns dict with experiment results.
    """
    label = f"{feature_mode}f"
    t0 = time.time()

    # Load data
    if feature_mode == 8:
        print(f"\n  Loading 8-feature data (window_size={args.window})...")
        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=args.window)
        input_dim = 8
    else:
        print(f"\n  Loading {feature_mode}-feature extended data (window_size={args.window})...")
        windows = build_16f_windows(patient_paths, window_size=args.window)
        if not windows:
            print("  ERROR: No valid windows produced")
            return None
        input_dim = windows[0].shape[1]
        label = f"{input_dim}f"
        train_ds, val_ds = windows_to_datasets(windows, val_fraction=0.2, seed=42)

    print(f"  Train: {len(train_ds)}, Val: {len(val_ds)}, input_dim: {input_dim}")

    # Persistence baseline
    persist = persistence_mse(val_ds)
    print(f"  Persistence baseline: MSE={persist:.6f}, ~MAE={np.sqrt(persist)*400:.1f} mg/dL")

    result = {
        'feature_mode': feature_mode,
        'actual_input_dim': input_dim,
        'window_size': args.window,
        'epochs': args.epochs,
        'patience': args.patience,
        'num_layers': args.num_layers,
        'd_model': args.d_model,
        'n_patients': len(patient_paths),
        'n_train': len(train_ds),
        'n_val': len(val_ds),
        'persistence_mse': float(persist),
        'seeds': {},
    }

    for seed in args.seeds:
        print(f"\n  --- Seed {seed} ---")
        set_seed(seed)
        model = create_model(
            'grouped', input_dim=input_dim,
            d_model=args.d_model, nhead=args.nhead, num_layers=args.num_layers,
        )
        n_params = sum(p.numel() for p in model.parameters())
        if seed == args.seeds[0]:
            print(f"  Model: {n_params:,} parameters")

        ckpt_path = os.path.join(args.output_dir, f'{args.name}_{label}_s{seed}.pth')
        best_val, epochs_run = train_forecast(
            model, train_ds, val_ds, ckpt_path,
            label=f'{label}-s{seed}',
            lr=args.lr, epochs=args.epochs, batch=args.batch, patience=args.patience,
        )

        val_mse = forecast_mse(model, val_ds, mask_future=True)
        val_mae = np.sqrt(val_mse) * 400.0

        result['seeds'][str(seed)] = {
            'best_val_loss': float(best_val),
            'epochs_run': epochs_run,
            'forecast_mse': float(val_mse),
            'mae_mgdl': round(float(val_mae), 2),
            'checkpoint': ckpt_path,
        }
        print(f"  Seed {seed}: MSE={val_mse:.6f}, ~MAE={val_mae:.1f} mg/dL")

    # Aggregate
    mses = [s['forecast_mse'] for s in result['seeds'].values()]
    maes = [s['mae_mgdl'] for s in result['seeds'].values()]
    result['aggregate'] = {
        'mean_mse': round(float(np.mean(mses)), 6),
        'std_mse': round(float(np.std(mses)), 6),
        'mean_mae': round(float(np.mean(maes)), 1),
        'std_mae': round(float(np.std(maes)), 1),
        'vs_persistence': round(float(1.0 - np.mean(mses) / persist) * 100, 1),
    }
    result['elapsed_seconds'] = round(time.time() - t0, 1)
    result['n_params'] = n_params

    print(f"\n  Result: MAE={result['aggregate']['mean_mae']:.1f} ± {result['aggregate']['std_mae']:.1f} mg/dL"
          f"  ({result['aggregate']['vs_persistence']:.1f}% vs persistence)")
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Retrain cgmencode models with configurable feature sets')
    parser.add_argument('--features', type=int, nargs='+', default=[8],
                        help='Feature modes to train: 8 (core) and/or 21 (extended)')
    parser.add_argument('--name', type=str, default='retrain',
                        help='Experiment name prefix for output files')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients',
                        help='Path to patients directory')
    parser.add_argument('--output-dir', type=str,
                        default='externals/experiments',
                        help='Output directory for checkpoints and results')
    parser.add_argument('--window', type=int, default=24,
                        help='Window size in 5-min steps (default: 24 = 2h)')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--patience', type=int, default=15)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--num-layers', type=int, default=3)
    parser.add_argument('--d-model', type=int, default=64)
    parser.add_argument('--nhead', type=int, default=4)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 456, 789])
    parser.add_argument('--device', type=str, default='auto',
                        help='Device: auto, cpu, cuda')

    args = parser.parse_args()

    # Setup device
    device = resolve_device(args.device)
    set_device(device)
    print(f"Device: {device}")

    # Discover patients
    patient_paths = discover_patients(args.patients_dir)
    print(f"Found {len(patient_paths)} patients in {args.patients_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    # Run experiments
    all_results = {}
    for feat in args.features:
        print(f"\n{'=' * 60}")
        print(f"  {feat}-Feature Forecast Experiment")
        print(f"{'=' * 60}")
        result = run_experiment(feat, patient_paths, args)
        if result:
            all_results[f'{feat}f'] = result

    # Save combined results
    output_path = os.path.join(args.output_dir, f'{args.name}_results.json')
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved: {output_path}")

    # Summary
    if len(all_results) > 1:
        print(f"\n{'=' * 60}")
        print(f"  COMPARISON SUMMARY")
        print(f"{'=' * 60}")
        for key, res in all_results.items():
            agg = res['aggregate']
            print(f"  {key}: MAE={agg['mean_mae']:.1f} ± {agg['std_mae']:.1f} mg/dL"
                  f"  ({agg['vs_persistence']:.1f}% vs persistence)")

    print("\nDone!")


if __name__ == '__main__':
    main()
