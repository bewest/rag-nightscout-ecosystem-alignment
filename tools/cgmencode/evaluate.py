#!/usr/bin/env python3
"""
evaluate.py — Evaluation metrics for cgmencode models.

Usage:
    python3 -m tools.cgmencode.evaluate --model ae --checkpoint checkpoints/ae_best.pth
    python3 -m tools.cgmencode.evaluate --baseline  # persistence baseline only
"""

import argparse
import json
import sys
import os
import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader

from .schema import NORMALIZATION_SCALES
from .model import CGMTransformerAE, CGMGroupedEncoder
from .toolbox import CGMTransformerVAE, ConditionedTransformer, CGMDenoisingDiffusion
from .sim_adapter import load_conformance_to_dataset
from .train import MODEL_REGISTRY, DEFAULT_DATA_DIRS
from .device import resolve_device, add_device_arg, batch_to_device


# Denormalization uses canonical scales from schema.py
SCALE = NORMALIZATION_SCALES


def denormalize_glucose(tensor_or_array):
    """Convert normalized [0-1] glucose back to mg/dL."""
    return tensor_or_array * SCALE['glucose']


def mae_mgdl(pred, target):
    """Mean Absolute Error in mg/dL (glucose channel only)."""
    pred_g = denormalize_glucose(pred[..., 0])
    tgt_g = denormalize_glucose(target[..., 0])
    return torch.mean(torch.abs(pred_g - tgt_g)).item()


def rmse_mgdl(pred, target):
    """Root Mean Square Error in mg/dL (glucose channel only)."""
    pred_g = denormalize_glucose(pred[..., 0])
    tgt_g = denormalize_glucose(target[..., 0])
    return torch.sqrt(torch.mean((pred_g - tgt_g) ** 2)).item()


def persistence_baseline(dataset, window_size=12):
    """
    Persistence forecast: predict that glucose stays at last observed value.
    Returns MAE and RMSE in mg/dL.
    """
    all_abs_errors = []
    for i in range(len(dataset)):
        x, y = dataset[i]
        # Last glucose in history window
        last_glucose = x[window_size - 1, 0]
        # Future glucose values (second half of the window)
        future_glucose = y[window_size:, 0]
        if len(future_glucose) == 0 or torch.isnan(last_glucose):
            continue
        abs_err = denormalize_glucose(torch.abs(future_glucose - last_glucose))
        valid = ~torch.isnan(abs_err)
        if valid.any():
            all_abs_errors.extend(abs_err[valid].tolist())

    if not all_abs_errors:
        return float('inf'), float('inf')
    arr = np.array(all_abs_errors)
    return float(np.mean(arr)), float(np.sqrt(np.mean(arr ** 2)))


def evaluate_model(model, val_loader, model_name, window_size=12):
    """Evaluate a trained model, returning metrics dict."""
    model.eval()
    device = next(model.parameters()).device
    all_mae = []
    all_rmse = []

    with torch.no_grad():
        for batch in val_loader:
            batch = batch_to_device(batch, device)
            if model_name == 'conditioned':
                (hist, actions), target = batch
                pred = model(hist, actions)
                # pred is (B, future_steps) glucose only
                pred_g = denormalize_glucose(pred)
                tgt_g = denormalize_glucose(target)
                all_mae.append(torch.mean(torch.abs(pred_g - tgt_g)).item())
                all_rmse.append(torch.sqrt(torch.mean((pred_g - tgt_g) ** 2)).item())
            elif model_name == 'vae':
                x, y = batch
                recon, mu, logvar = model(x)
                all_mae.append(mae_mgdl(recon, y))
                all_rmse.append(rmse_mgdl(recon, y))
            elif model_name == 'diffusion':
                x, y = batch
                t = torch.zeros(x.size(0), dtype=torch.long, device=device)
                output = model(x, t)
                all_mae.append(mae_mgdl(output, y))
                all_rmse.append(rmse_mgdl(output, y))
            else:  # ae
                x, y = batch
                output = model(x)
                all_mae.append(mae_mgdl(output, y))
                all_rmse.append(rmse_mgdl(output, y))

    return {
        'mae_mgdl': round(np.mean(all_mae), 2),
        'rmse_mgdl': round(np.mean(all_rmse), 2),
    }


def per_horizon_mae(model, val_loader, model_name, window_size=12, interval_min=5):
    """
    Compute MAE at each future timestep (per-horizon analysis).

    Returns dict mapping horizon label (e.g., '15min') to MAE in mg/dL.
    Essential for clinical validation — accuracy degrades with forecast horizon.
    """
    model.eval()
    device = next(model.parameters()).device
    # Collect per-timestep errors: {timestep_idx: [abs_errors]}
    horizon_errors = {}

    with torch.no_grad():
        for batch in val_loader:
            batch = batch_to_device(batch, device)
            if model_name == 'conditioned':
                (hist, actions), target = batch
                pred = model(hist, actions)
                pred_g = denormalize_glucose(pred)
                tgt_g = denormalize_glucose(target)
                # pred_g: (B, future_steps)
                for t in range(pred_g.size(-1)):
                    errs = torch.abs(pred_g[:, t] - tgt_g[:, t])
                    horizon_errors.setdefault(t, []).extend(errs.cpu().tolist())
            else:
                x, y = batch
                if model_name == 'vae':
                    output, _, _ = model(x)
                elif model_name == 'diffusion':
                    t_idx = torch.zeros(x.size(0), dtype=torch.long, device=device)
                    output = model(x, t_idx)
                else:
                    output = model(x)

                # Only measure future timesteps (after window_size)
                pred_g = denormalize_glucose(output[:, window_size:, 0])
                tgt_g = denormalize_glucose(y[:, window_size:, 0])
                for t in range(pred_g.size(-1)):
                    errs = torch.abs(pred_g[:, t] - tgt_g[:, t])
                    valid = ~torch.isnan(errs)
                    if valid.any():
                        horizon_errors.setdefault(t, []).extend(errs[valid].cpu().tolist())

    results = {}
    for t_idx in sorted(horizon_errors.keys()):
        minutes = (t_idx + 1) * interval_min
        label = f"{minutes}min"
        mae = float(np.mean(horizon_errors[t_idx]))
        results[label] = round(mae, 2)

    return results


def main():
    parser = argparse.ArgumentParser(description='Evaluate cgmencode models')
    parser.add_argument('--model', choices=list(MODEL_REGISTRY.keys()),
                        help='Architecture to evaluate')
    parser.add_argument('--checkpoint', help='Path to model checkpoint')
    parser.add_argument('--data', nargs='+', help='Conformance data directories')
    parser.add_argument('--source', choices=['conformance', 'nightscout', 'csv'],
                        default='conformance', help='Data source type')
    parser.add_argument('--data-path', help='Path to data directory (nightscout/csv)')
    parser.add_argument('--window', type=int, default=12)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--baseline', action='store_true', help='Only compute persistence baseline')
    parser.add_argument('--save', help='Save results JSON to this path')
    add_device_arg(parser)
    args = parser.parse_args()

    device = resolve_device(args.device)
    print("=== cgmencode Evaluation ===")
    print(f"Source: {args.source}")
    print(f"Device: {device}")

    def _load_val(task='forecast', conditioned=False, force_window=None):
        """Load validation data. force_window overrides the actual window size used."""
        ws = force_window if force_window else args.window
        if args.source == 'nightscout':
            from .real_data_adapter import load_nightscout_to_dataset
            if not args.data_path:
                print("ERROR: --data-path required for Nightscout source")
                sys.exit(1)
            _, val_ds = load_nightscout_to_dataset(
                args.data_path, task=task, window_size=ws, conditioned=conditioned)
            return val_ds
        else:
            data_dirs = args.data if args.data else DEFAULT_DATA_DIRS
            _, val_ds = load_conformance_to_dataset(
                data_dirs, task=task, window_size=ws, conditioned=conditioned)
            return val_ds

    results = {}

    # Persistence baseline needs windows of 2*window_size (history + future)
    print("\n--- Persistence Baseline (glucose stays flat) ---")
    base_val = _load_val(task='forecast', conditioned=False, force_window=args.window * 2)
    if base_val:
        base_mae, base_rmse = persistence_baseline(base_val, args.window)
        results['persistence'] = {'mae_mgdl': round(base_mae, 2), 'rmse_mgdl': round(base_rmse, 2)}
        print(f"  MAE:  {base_mae:.2f} mg/dL")
        print(f"  RMSE: {base_rmse:.2f} mg/dL")
    else:
        print("  No validation data found.")

    if args.baseline:
        if args.save:
            _save_results(results, args.save)
        return

    # Evaluate trained model
    if not args.model or not args.checkpoint:
        print("\nSpecify --model and --checkpoint to evaluate a trained model.")
        return

    reg = MODEL_REGISTRY[args.model]
    val_ds = _load_val(task=reg['task'], conditioned=reg['conditioned'])

    if not val_ds:
        print("ERROR: No validation data.")
        sys.exit(1)

    use_pin = device.type == 'cuda'
    val_loader = DataLoader(val_ds, batch_size=args.batch, pin_memory=use_pin)

    # Load model
    model = reg['class'](**reg['kwargs'])
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    if 'model_state' in checkpoint:
        model.load_state_dict(checkpoint['model_state'])
        print(f"\n--- {args.model.upper()} (epoch {checkpoint.get('epoch', '?')}) ---")
    else:
        model.load_state_dict(checkpoint)
        print(f"\n--- {args.model.upper()} ---")
    model.to(device)

    metrics = evaluate_model(model, val_loader, args.model, args.window)
    results[args.model] = metrics
    print(f"  MAE:  {metrics['mae_mgdl']:.2f} mg/dL")
    print(f"  RMSE: {metrics['rmse_mgdl']:.2f} mg/dL")

    # Per-horizon breakdown
    horizon = per_horizon_mae(model, val_loader, args.model, args.window)
    if horizon:
        results[f'{args.model}_per_horizon'] = horizon
        print(f"\n  Per-horizon MAE (mg/dL):")
        for label, mae in horizon.items():
            print(f"    {label:>6s}: {mae:.2f}")

    # Comparison
    if 'persistence' in results:
        improvement = results['persistence']['mae_mgdl'] - metrics['mae_mgdl']
        pct = (improvement / results['persistence']['mae_mgdl']) * 100 if results['persistence']['mae_mgdl'] > 0 else 0
        print(f"\n  vs baseline: {'↓' if improvement > 0 else '↑'} {abs(improvement):.2f} mg/dL MAE ({abs(pct):.1f}%)")

    print(f"\n{json.dumps(results, indent=2)}")

    if args.save:
        _save_results(results, args.save)


def _save_results(results, path):
    """Save results dict to JSON file."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {path}")


if __name__ == '__main__':
    main()
