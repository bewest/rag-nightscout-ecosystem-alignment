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

from .model import CGMTransformerAE
from .toolbox import CGMTransformerVAE, ConditionedTransformer, CGMDenoisingDiffusion
from .sim_adapter import load_conformance_to_dataset
from .train import MODEL_REGISTRY, DEFAULT_DATA_DIRS


# Denormalization constants (must match encoder.py scaling)
SCALE = {
    'glucose': 400.0,
    'iob': 20.0,
    'cob': 100.0,
    'net_basal': 5.0,
    'bolus': 10.0,
    'carbs': 100.0,
}


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
    all_mae = []
    all_rmse = []

    with torch.no_grad():
        for batch in val_loader:
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
                t = torch.zeros(x.size(0), dtype=torch.long)
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


def main():
    parser = argparse.ArgumentParser(description='Evaluate cgmencode models')
    parser.add_argument('--model', choices=list(MODEL_REGISTRY.keys()),
                        help='Architecture to evaluate')
    parser.add_argument('--checkpoint', help='Path to model checkpoint')
    parser.add_argument('--data', nargs='+', help='Data directories')
    parser.add_argument('--window', type=int, default=12)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--baseline', action='store_true', help='Only compute persistence baseline')
    args = parser.parse_args()

    data_dirs = args.data if args.data else DEFAULT_DATA_DIRS

    print("=== cgmencode Evaluation ===")
    print(f"Data: {data_dirs}")

    results = {}

    # Always compute persistence baseline
    print("\n--- Persistence Baseline (glucose stays flat) ---")
    base_train, base_val = load_conformance_to_dataset(
        data_dirs, task='forecast', window_size=args.window)
    if base_val:
        base_mae, base_rmse = persistence_baseline(base_val, args.window)
        results['persistence'] = {'mae_mgdl': round(base_mae, 2), 'rmse_mgdl': round(base_rmse, 2)}
        print(f"  MAE:  {base_mae:.2f} mg/dL")
        print(f"  RMSE: {base_rmse:.2f} mg/dL")
    else:
        print("  No validation data found.")

    if args.baseline:
        return

    # Evaluate trained model
    if not args.model or not args.checkpoint:
        print("\nSpecify --model and --checkpoint to evaluate a trained model.")
        return

    reg = MODEL_REGISTRY[args.model]
    _, val_ds = load_conformance_to_dataset(
        data_dirs, task=reg['task'], window_size=args.window, conditioned=reg['conditioned'])

    if not val_ds:
        print("ERROR: No validation data.")
        sys.exit(1)

    val_loader = DataLoader(val_ds, batch_size=args.batch)

    # Load model
    model = reg['class'](**reg['kwargs'])
    checkpoint = torch.load(args.checkpoint, map_location='cpu')
    model.load_state_dict(checkpoint['model_state'])
    print(f"\n--- {args.model.upper()} (epoch {checkpoint.get('epoch', '?')}) ---")

    metrics = evaluate_model(model, val_loader, args.model, args.window)
    results[args.model] = metrics
    print(f"  MAE:  {metrics['mae_mgdl']:.2f} mg/dL")
    print(f"  RMSE: {metrics['rmse_mgdl']:.2f} mg/dL")

    # Comparison
    if 'persistence' in results:
        improvement = results['persistence']['mae_mgdl'] - metrics['mae_mgdl']
        print(f"\n  vs baseline: {'↓' if improvement > 0 else '↑'} {abs(improvement):.2f} mg/dL MAE")

    print(f"\n{json.dumps(results, indent=2)}")


if __name__ == '__main__':
    main()
