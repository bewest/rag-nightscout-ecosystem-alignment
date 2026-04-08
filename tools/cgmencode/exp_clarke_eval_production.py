#!/usr/bin/env python3
"""
EXP-1401: Clarke Error Grid Evaluation of PKGroupedEncoder Production Model

Evaluates the EXP-619 champion model on held-out verification data with
proper Clarke Error Grid analysis at all forecast horizons (h30–h360).

This replaces the EXP-929 Clarke evaluation (which used Ridge regression)
with a direct evaluation of the production PKGroupedEncoder transformer.

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_clarke_eval_production.py

Data: externals/ns-data/patients/{a-k}/verification/
Models: externals/experiments/exp619_w{48,96,144}_ft_{a-k}_s{seed}.pth
Output: externals/experiments/exp1401_clarke_production.json
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features
from cgmencode.metrics import clarke_zone
from cgmencode.exp_pk_forecast_v14 import (
    PKGroupedEncoder, mask_future_pk, PK_NORMS, GLUCOSE_SCALE,
    PRODUCTION_SEEDS,
)

PATIENTS = list('abcdefghijk')
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
MODELS_DIR = ROOT / 'externals' / 'experiments'
DATA_DIR = ROOT / 'externals' / 'ns-data' / 'patients'

# EXP-619 routing: which window is best per horizon
ROUTING = {
    'h30': 'w48', 'h60': 'w48', 'h90': 'w48', 'h120': 'w48',
    'h150': 'w96', 'h180': 'w96', 'h240': 'w96',
    'h300': 'w144', 'h360': 'w144',
}

# Horizon name → future step index (0-based, 5min intervals)
HORIZON_STEPS = {
    'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
    'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71,
}

WINDOW_CONFIGS = {
    'w48': {'total': 48, 'history': 24, 'future': 24, 'future_steps': None},
    'w96': {'total': 96, 'history': 48, 'future': 48, 'future_steps': None},
    'w144': {'total': 144, 'history': 72, 'future': 72, 'future_steps': None},
}


def load_model(patient_id, window, seed, device='cpu'):
    """Load a single fine-tuned PKGroupedEncoder checkpoint."""
    fname = f"exp619_{window}_ft_{patient_id}_s{seed}.pth"
    path = MODELS_DIR / fname
    if not path.exists():
        return None
    ckpt = torch.load(path, map_location=device, weights_only=True)
    model = PKGroupedEncoder(input_dim=8, d_model=64, nhead=4,
                             num_layers=4, dim_feedforward=128,
                             dropout=0.0)
    model.load_state_dict(ckpt['model_state'])
    model.to(device)
    model.eval()
    return model


def load_ensemble(patient_id, window, device='cpu'):
    """Load 5-seed ensemble for a patient+window."""
    models = []
    for seed in PRODUCTION_SEEDS:
        m = load_model(patient_id, window, seed, device)
        if m is not None:
            models.append(m)
    return models


def build_verification_windows(patient_id, window_size, stride=12):
    """Build sliding windows from held-out verification data.

    Returns: (windows_8ch: ndarray [N, window_size, 8],
              isf_values: ndarray [N] or None)
    """
    data_path = DATA_DIR / patient_id / 'verification'
    if not data_path.exists():
        print(f"  ⚠ No verification data for patient {patient_id}")
        return None, None, None

    df, feats_8ch = build_nightscout_grid(str(data_path), verbose=False)
    pk = build_continuous_pk_features(df, dia_hours=5.0)

    # Build the 8-channel PK-replaced features matching EXP-619 training
    # Channel layout: [glucose/400, IOB/20, COB/100, net_basal/5,
    #                  insulin_net/PK[1], carb_rate/PK[3], sin_time, net_balance/PK[6]]
    base = feats_8ch.copy()  # Already has glucose/400, IOB/20, COB/100, net_basal/5, ...
    # Replace ch4 (bolus) with PK insulin_net
    base[:, 4] = pk[:, 1] / PK_NORMS[1]
    # Replace ch5 (carbs) with PK carb_rate
    base[:, 5] = pk[:, 3] / PK_NORMS[3]
    # ch6 is sin_time (already in base from build_nightscout_grid)
    # Replace ch7 (cos_time) with net_balance
    base[:, 7] = pk[:, 6] / PK_NORMS[6]

    # Get ISF for ISF normalization (EXP-619 used ISF)
    profile_path = data_path / 'profile.json'
    isf = None
    if profile_path.exists():
        try:
            with open(profile_path) as f:
                profiles = json.load(f)
            if profiles and isinstance(profiles, list):
                store = profiles[0].get('store', {})
                for pname, pdata in store.items():
                    sens = pdata.get('sens', [])
                    if sens:
                        isf = float(sens[0].get('value', 50))
                        break
            if isf is None:
                isf = 50.0
        except Exception:
            isf = 50.0
    else:
        isf = 50.0

    # Apply ISF normalization to glucose channel
    isf_factor = GLUCOSE_SCALE / isf
    base[:, 0] = base[:, 0] * isf_factor
    np.clip(base[:, 0], 0, 10, out=base[:, 0])

    # Extract raw glucose for computing reference values
    glucose_raw = df['glucose'].values.copy()

    # Slide windows
    n_steps = len(base)
    windows = []
    glucose_windows = []
    for start in range(0, n_steps - window_size + 1, stride):
        w = base[start:start + window_size]
        g = glucose_raw[start:start + window_size]
        # Skip windows with too many NaN glucose values in history or future
        half = window_size // 2
        hist_valid = np.sum(np.isfinite(g[:half]) & (g[:half] > 0))
        future_valid = np.sum(np.isfinite(g[half:]) & (g[half:] > 0))
        if hist_valid < half * 0.5 or future_valid < 2:
            continue
        # NaN-fill for non-glucose channels
        w_clean = np.nan_to_num(w, nan=0.0)
        windows.append(w_clean)
        glucose_windows.append(g)

    if not windows:
        print(f"  ⚠ No valid windows for patient {patient_id}")
        return None, None, None

    windows = np.array(windows, dtype=np.float32)
    glucose_windows = np.array(glucose_windows, dtype=np.float64)
    print(f"  Patient {patient_id}: {len(windows)} windows, ISF={isf}")
    return windows, glucose_windows, isf


def evaluate_ensemble_clarke(models, windows_8ch, glucose_raw, isf,
                             window_name, device='cpu'):
    """Run ensemble predictions and compute Clarke zones at each horizon.

    Returns dict with per-horizon Clarke zone analysis.
    """
    cfg = WINDOW_CONFIGS[window_name]
    half = cfg['total'] // 2
    future_steps = cfg['future']

    # Determine which horizons this window can evaluate
    valid_horizons = {h: s for h, s in HORIZON_STEPS.items()
                     if s < future_steps}

    # Run ensemble predictions
    x_tensor = torch.tensor(windows_8ch, dtype=torch.float32)
    dl = DataLoader(TensorDataset(x_tensor), batch_size=64, shuffle=False)

    all_model_preds = []
    for model in models:
        preds = []
        with torch.no_grad():
            for (batch,) in dl:
                batch = batch.to(device)
                x_in = batch.clone()
                mask_future_pk(x_in, half, pk_mode=True)
                out = model(x_in, causal=True)
                # Denormalize: undo ISF then scale
                p = out[:, half:, 0].cpu().numpy()
                p = p * (isf / GLUCOSE_SCALE) * GLUCOSE_SCALE  # = p * isf
                preds.append(p)
        all_model_preds.append(np.concatenate(preds, axis=0))

    # Ensemble mean
    ensemble_preds = np.mean(all_model_preds, axis=0)  # [N, future_steps]
    ensemble_std = np.std(all_model_preds, axis=0)

    # Reference glucose (raw, already in mg/dL)
    ref_glucose = glucose_raw[:, half:]  # [N, future_steps]

    # Compute Clarke zones per horizon
    results = {}
    for h_name, step_idx in valid_horizons.items():
        pred_h = ensemble_preds[:, step_idx]
        ref_h = ref_glucose[:, step_idx]

        # Filter valid pairs (both finite and > 0)
        valid = (np.isfinite(ref_h) & np.isfinite(pred_h) &
                 (ref_h > 10) & (pred_h > 10))
        if np.sum(valid) < 20:
            continue

        ref_v = ref_h[valid]
        pred_v = pred_h[valid]

        # Clarke zones
        zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
        for r, p in zip(ref_v, pred_v):
            z = clarke_zone(float(r), float(p))
            zones[z] += 1
        total = sum(zones.values())
        zone_pct = {k: round(v / total * 100, 2) for k, v in zones.items()}

        # Error metrics
        errors = np.abs(pred_v - ref_v)
        mae = float(np.mean(errors))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        rel_errors = errors / np.maximum(ref_v, 1.0)
        mard = float(np.mean(rel_errors) * 100)

        # Ensemble uncertainty at this horizon
        std_h = ensemble_std[:, step_idx][valid]
        mean_std = float(np.mean(std_h))

        results[h_name] = {
            'clarke_zones': zone_pct,
            'clarke_A_pct': zone_pct['A'],
            'clarke_AB_pct': round(zone_pct['A'] + zone_pct['B'], 2),
            'clarke_DE_pct': round(zone_pct['D'] + zone_pct['E'], 2),
            'mae_mgdl': round(mae, 2),
            'rmse_mgdl': round(rmse, 2),
            'mard_pct': round(mard, 2),
            'ensemble_std_mean': round(mean_std, 2),
            'n_predictions': total,
        }

    return results


def run_evaluation():
    """Main evaluation loop: all patients × all windows × all horizons."""
    print(f"EXP-1401: Clarke Error Grid — PKGroupedEncoder Production Evaluation")
    print(f"Device: {DEVICE}")
    print(f"Models: {MODELS_DIR}")
    print(f"Data: {DATA_DIR}")
    print()

    t0 = time.time()

    # Windows needed (unique from routing)
    windows_needed = sorted(set(ROUTING.values()))
    print(f"Windows to evaluate: {windows_needed}")
    print(f"Patients: {PATIENTS}")
    print()

    # Per-patient, per-window results
    all_results = {}

    for patient_id in PATIENTS:
        print(f"\n{'='*60}")
        print(f"Patient {patient_id}")
        print(f"{'='*60}")
        patient_results = {}

        for window in windows_needed:
            print(f"\n  Window {window}:")
            # Load models
            models = load_ensemble(patient_id, window, DEVICE)
            if not models:
                print(f"    ⚠ No models found for {patient_id}/{window}")
                continue
            print(f"    Loaded {len(models)}-seed ensemble")

            # Build windows from verification data
            cfg = WINDOW_CONFIGS[window]
            windows_8ch, glucose_raw, isf = build_verification_windows(
                patient_id, cfg['total'], stride=12)
            if windows_8ch is None:
                continue

            # Evaluate
            horizon_results = evaluate_ensemble_clarke(
                models, windows_8ch, glucose_raw, isf, window, DEVICE)

            for h_name, h_result in horizon_results.items():
                print(f"    {h_name}: MAE={h_result['mae_mgdl']:.1f} "
                      f"A={h_result['clarke_A_pct']:.1f}% "
                      f"A+B={h_result['clarke_AB_pct']:.1f}% "
                      f"D+E={h_result['clarke_DE_pct']:.1f}%")

            patient_results[window] = horizon_results

            # Free GPU memory
            del models
            torch.cuda.empty_cache() if DEVICE == 'cuda' else None

        all_results[patient_id] = patient_results

    # Aggregate: use routing to pick best window per horizon
    print(f"\n{'='*60}")
    print("ROUTED AGGREGATE RESULTS")
    print(f"{'='*60}")

    routed_aggregate = {}
    for h_name, best_window in ROUTING.items():
        per_patient_metrics = []
        for patient_id in PATIENTS:
            pw = all_results.get(patient_id, {}).get(best_window, {})
            if h_name in pw:
                per_patient_metrics.append({
                    'patient': patient_id,
                    **pw[h_name],
                })

        if not per_patient_metrics:
            print(f"  {h_name}: NO DATA")
            continue

        n = len(per_patient_metrics)
        mean_A = np.mean([m['clarke_A_pct'] for m in per_patient_metrics])
        mean_AB = np.mean([m['clarke_AB_pct'] for m in per_patient_metrics])
        mean_DE = np.mean([m['clarke_DE_pct'] for m in per_patient_metrics])
        mean_mae = np.mean([m['mae_mgdl'] for m in per_patient_metrics])
        mean_rmse = np.mean([m['rmse_mgdl'] for m in per_patient_metrics])
        mean_mard = np.mean([m['mard_pct'] for m in per_patient_metrics])

        # Per-zone aggregate
        zone_means = {}
        for z in 'ABCDE':
            zone_means[z] = round(float(np.mean(
                [m['clarke_zones'][z] for m in per_patient_metrics])), 2)

        routed = {
            'best_window': best_window,
            'n_patients': n,
            'mean_clarke_A_pct': round(float(mean_A), 2),
            'mean_clarke_AB_pct': round(float(mean_AB), 2),
            'mean_clarke_DE_pct': round(float(mean_DE), 2),
            'mean_zone_pcts': zone_means,
            'mean_mae_mgdl': round(float(mean_mae), 2),
            'mean_rmse_mgdl': round(float(mean_rmse), 2),
            'mean_mard_pct': round(float(mean_mard), 2),
            'per_patient': per_patient_metrics,
        }
        routed_aggregate[h_name] = routed

        print(f"  {h_name} ({best_window}): MAE={mean_mae:.1f}  "
              f"A={mean_A:.1f}%  A+B={mean_AB:.1f}%  "
              f"D+E={mean_DE:.1f}%  ({n} patients)")

    elapsed = time.time() - t0

    # Save results
    output = {
        'experiment': 'EXP-1401',
        'name': 'Clarke Error Grid — PKGroupedEncoder Production',
        'model': 'PKGroupedEncoder (EXP-619)',
        'data_split': 'verification (held-out)',
        'device': DEVICE,
        'elapsed_seconds': round(elapsed, 1),
        'routing': ROUTING,
        'routed_aggregate': routed_aggregate,
        'per_patient_per_window': all_results,
    }

    out_path = ROOT / 'externals' / 'experiments' / 'exp1401_clarke_production.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n✓ Results saved to {out_path}")
    print(f"  Elapsed: {elapsed:.1f}s")

    return output


if __name__ == '__main__':
    run_evaluation()
