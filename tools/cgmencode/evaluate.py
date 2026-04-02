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


# =============================================================================
# Clinical Outcome Metrics (agentic delivery scoring)
# =============================================================================

def time_in_range(glucose_mgdl, low=70.0, high=180.0):
    """Compute Time-in-Range (TIR) percentage.

    Standard ranges per international consensus:
    - Very low: <54 mg/dL
    - Low: 54-69 mg/dL
    - Target: 70-180 mg/dL
    - High: 181-250 mg/dL
    - Very high: >250 mg/dL

    Args:
        glucose_mgdl: array-like of glucose values in mg/dL
        low: lower bound of target range (default 70)
        high: upper bound of target range (default 180)

    Returns:
        dict with TIR breakdown percentages
    """
    g = np.asarray(glucose_mgdl, dtype=float)
    g = g[~np.isnan(g)]
    if len(g) == 0:
        return {'tir': 0.0, 'below_54': 0.0, 'below_70': 0.0,
                'above_180': 0.0, 'above_250': 0.0, 'n_readings': 0}

    n = len(g)
    return {
        'tir': float(np.mean((g >= low) & (g <= high)) * 100),
        'below_54': float(np.mean(g < 54) * 100),
        'below_70': float(np.mean(g < 70) * 100),
        'above_180': float(np.mean(g > 180) * 100),
        'above_250': float(np.mean(g > 250) * 100),
        'n_readings': n,
    }


def glucose_variability(glucose_mgdl):
    """Compute glucose variability metrics.

    Returns:
        dict with CV (coefficient of variation), SD, and mean
    """
    g = np.asarray(glucose_mgdl, dtype=float)
    g = g[~np.isnan(g)]
    if len(g) < 2:
        return {'cv': 0.0, 'sd': 0.0, 'mean': 0.0}

    mean_g = float(np.mean(g))
    sd_g = float(np.std(g, ddof=1))
    cv = (sd_g / mean_g * 100) if mean_g > 0 else 0.0
    return {'cv': round(cv, 2), 'sd': round(sd_g, 2), 'mean': round(mean_g, 2)}


def glycemia_risk_index(glucose_mgdl):
    """Compute the Glycemia Risk Index (GRI).

    GRI = (3.0 × %below54) + (2.4 × %below70-54) + (1.6 × %above250) + (0.8 × %above180-250)
    Range: 0 (perfect) to 100 (worst).
    Reference: Klonoff et al., J Diabetes Sci Technol, 2023.

    Args:
        glucose_mgdl: array-like of glucose values in mg/dL

    Returns:
        dict with GRI score and components
    """
    g = np.asarray(glucose_mgdl, dtype=float)
    g = g[~np.isnan(g)]
    if len(g) == 0:
        return {'gri': 0.0, 'vlow_component': 0.0, 'low_component': 0.0,
                'high_component': 0.0, 'vhigh_component': 0.0}

    pct_below54 = np.mean(g < 54) * 100
    pct_54_70 = np.mean((g >= 54) & (g < 70)) * 100
    pct_180_250 = np.mean((g > 180) & (g <= 250)) * 100
    pct_above250 = np.mean(g > 250) * 100

    vlow = 3.0 * pct_below54
    low = 2.4 * pct_54_70
    high = 0.8 * pct_180_250
    vhigh = 1.6 * pct_above250

    gri = min(100.0, vlow + low + high + vhigh)

    return {
        'gri': round(float(gri), 2),
        'vlow_component': round(float(vlow), 2),
        'low_component': round(float(low), 2),
        'high_component': round(float(high), 2),
        'vhigh_component': round(float(vhigh), 2),
    }


def hypo_events(glucose_mgdl, threshold=70.0, min_duration_steps=3):
    """Count hypoglycemic events (consecutive readings below threshold).

    Args:
        glucose_mgdl: array-like of glucose readings in mg/dL
        threshold: hypo threshold (default 70 mg/dL)
        min_duration_steps: minimum consecutive steps to count as event (default 3 = 15 min)

    Returns:
        dict with event count and total time below threshold
    """
    g = np.asarray(glucose_mgdl, dtype=float)
    below = g < threshold
    events = 0
    streak = 0
    total_steps_below = 0

    for b in below:
        if b:
            streak += 1
            total_steps_below += 1
        else:
            if streak >= min_duration_steps:
                events += 1
            streak = 0
    if streak >= min_duration_steps:
        events += 1

    return {
        'hypo_events': events,
        'total_steps_below': int(total_steps_below),
        'pct_below': float(np.mean(below) * 100) if len(g) > 0 else 0.0,
    }


def clinical_summary(glucose_mgdl):
    """Compute all clinical metrics in one call.

    Args:
        glucose_mgdl: array-like of glucose values in mg/dL

    Returns:
        dict with TIR, variability, GRI, and hypo event data
    """
    return {
        **time_in_range(glucose_mgdl),
        **glucose_variability(glucose_mgdl),
        **glycemia_risk_index(glucose_mgdl),
        **hypo_events(glucose_mgdl),
    }


# =============================================================================
# Decision Quality Metrics (override suggestion scoring)
# =============================================================================

def override_accuracy(suggested, actual, lead_window_steps=6):
    """Score override suggestion quality.

    Args:
        suggested: list of dicts {'timestamp_idx': int, 'event_type': str}
        actual: list of dicts {'timestamp_idx': int, 'event_type': str}
        lead_window_steps: how many steps before actual event counts as "correct"

    Returns:
        dict with precision, recall, F1, and mean lead time
    """
    if not suggested:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
                'mean_lead_time': 0.0, 'n_suggested': 0, 'n_actual': len(actual)}

    tp = 0
    lead_times = []

    for s in suggested:
        for a in actual:
            if s['event_type'] == a['event_type']:
                delta = a['timestamp_idx'] - s['timestamp_idx']
                if 0 <= delta <= lead_window_steps:
                    tp += 1
                    lead_times.append(delta)
                    break

    precision = tp / len(suggested) if suggested else 0.0
    recall = tp / len(actual) if actual else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'mean_lead_time': round(float(np.mean(lead_times)), 2) if lead_times else 0.0,
        'n_suggested': len(suggested),
        'n_actual': len(actual),
        'true_positives': tp,
    }


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
