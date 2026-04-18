#!/usr/bin/env python3
"""
validate_horizons.py — Full 11-patient validation of h30-h180 forecasts.

Validates production forecast models (PKGroupedEncoder from EXP-619) against
parquet grid data by constructing inputs that match the original training
pipeline exactly:

  1. build_nightscout_grid → base_grid (8ch normalized)
  2. build_continuous_pk_features → pk_grid (8ch PK-normalized)
  3. prepare_pk_future → replace ch4,5,7 with PK channels / PK_NORMS
  4. _apply_isf_norm → ISF-normalize glucose channel

The previous version used prepare_input_window from glucose_forecast.py which
approximated these steps but did not match the training pipeline, causing
MAE of 60-130 mg/dL instead of the expected 11-18 mg/dL.

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/validate_horizons.py
    PYTHONPATH=tools python tools/cgmencode/production/validate_horizons.py --tiny
    PYTHONPATH=tools python tools/cgmencode/production/validate_horizons.py --device cuda
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from cgmencode.continuous_pk import (
    compute_insulin_activity,
    compute_carb_absorption_rate,
    compute_hepatic_production,
    compute_net_metabolic_balance,
    PK_NORMALIZATION,
)
from cgmencode.production.glucose_forecast import (
    HORIZON_ROUTING, ROUTED_MAE, WINDOW_CONFIG,
    _build_model, _torch_available,
)

# Constants matching exp_pk_forecast_v14.py training pipeline
GLUCOSE_SCALE = 400.0
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]

# Base grid normalization scales (from schema.py NORMALIZATION_SCALES)
BASE_SCALES = {'glucose': 400.0, 'iob': 20.0, 'cob': 100.0, 'net_basal': 5.0}

# Horizon step index in the future portion (0-indexed, each step = 5 min)
HORIZON_STEPS = {
    'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
    'h150': 29, 'h180': 35,
}

WINDOW_LABELS = {
    'w48': 'w48_short', 'w72': 'w72_mid',
    'w96': 'w96_extended', 'w144': 'w144_strategic',
}


def _col(g: pd.DataFrame, name: str, default: float = 0.0) -> np.ndarray:
    """Extract column from DataFrame, filling NaN with *default*."""
    if name in g.columns:
        return np.nan_to_num(g[name].values.astype(np.float64), nan=default)
    return np.full(len(g), default, dtype=np.float64)


def load_parquet_patients(tiny: bool = False) -> dict:
    """Load per-patient DataFrames from parquet grid.

    Returns dict mapping patient_id → DataFrame (sorted by time).
    """
    if tiny:
        grid_path = PROJECT_ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        grid_path = PROJECT_ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"

    if not grid_path.exists():
        print(f"ERROR: {grid_path} not found")
        return {}

    print(f"Loading grid from {grid_path}...")
    t0 = time.time()
    df = pd.read_parquet(grid_path)
    print(f"  Loaded {len(df)} rows in {time.time()-t0:.2f}s")

    patients = {}
    for pid, group in df.groupby('patient_id'):
        g = group.sort_values('time').reset_index(drop=True)
        if len(g) < 288:  # at least 1 day of 5-min data
            continue
        patients[str(pid)] = g

    print(f"  {len(patients)} patients loaded")
    return patients


def build_features_from_parquet(g: pd.DataFrame):
    """Build 8-channel model input matching the EXP-619 training pipeline.

    Reproduces the exact feature construction used during training:
      base_grid channels 0-3,6 from raw parquet values (normalized by schema
      NORMALIZATION_SCALES), plus PK-replaced channels 4,5,7 computed via
      continuous_pk functions and double-normalized (first by PK_NORMALIZATION
      inside build_continuous_pk_features, then by PK_NORMS inside
      prepare_pk_future).

    Returns:
        (features, isf) — (N, 8) float32 array (glucose channel keeps NaN for
        windowing quality check) and scalar patient ISF in mg/dL/U.
    """
    N = len(g)

    # --- Raw values from parquet ---
    glucose_raw = g['glucose'].values.astype(np.float64)  # keep NaN
    iob = _col(g, 'iob')
    cob = _col(g, 'cob')
    net_basal = _col(g, 'net_basal')
    bolus = _col(g, 'bolus')
    carbs = _col(g, 'carbs')
    time_sin = _col(g, 'time_sin')
    actual_basal = _col(g, 'actual_basal_rate')
    sched_basal = _col(g, 'scheduled_basal_rate')
    sched_isf = _col(g, 'scheduled_isf', default=50.0)
    sched_cr = _col(g, 'scheduled_cr', default=10.0)

    # Patient ISF = mean of unique schedule values (matches load_patient_profile_isf
    # which computes np.mean of the profile sens entries)
    positive_isf = sched_isf[sched_isf > 0]
    unique_isf = np.unique(positive_isf)
    isf = float(np.mean(unique_isf)) if len(unique_isf) > 0 else 50.0
    if isf < 15:  # mmol/L → mg/dL
        isf *= 18.0182

    # Hours of day for hepatic production model
    times = pd.to_datetime(g['time'])
    hours = (times.dt.hour + times.dt.minute / 60.0).values.astype(np.float64)

    # --- Compute PK features (raw, same as build_continuous_pk_features) ---

    insulin = compute_insulin_activity(
        pd.Series(bolus), pd.Series(actual_basal), sched_basal)
    insulin_net_raw = insulin['net']  # U/min

    carb_rate_raw = compute_carb_absorption_rate(pd.Series(carbs))  # g/min

    hepatic_raw = compute_hepatic_production(iob, hours)  # mg/dL per 5min

    net_balance_raw = compute_net_metabolic_balance(
        insulin_net_raw, carb_rate_raw, hepatic_raw, sched_isf, sched_cr)

    # --- Assemble 8-channel features (matching prepare_pk_future) ---

    features = np.zeros((N, 8), dtype=np.float32)

    # Base grid channels (normalized by schema NORMALIZATION_SCALES)
    features[:, 0] = glucose_raw / BASE_SCALES['glucose']   # glucose/400, NaN propagates
    features[:, 1] = iob / BASE_SCALES['iob']               # IOB/20
    features[:, 2] = cob / BASE_SCALES['cob']               # COB/100
    features[:, 3] = net_basal / BASE_SCALES['net_basal']    # net_basal/5
    features[:, 6] = time_sin                                # sin(2π·hour/24)

    # PK-replaced channels (double-normalized: /PK_NORMALIZATION then /PK_NORMS,
    # exactly as prepare_pk_future applies to build_continuous_pk_features output)
    features[:, 4] = (insulin_net_raw / PK_NORMALIZATION['insulin_net']) / PK_NORMS[1]
    features[:, 5] = (carb_rate_raw / PK_NORMALIZATION['carb_rate']) / PK_NORMS[3]
    features[:, 7] = (net_balance_raw / PK_NORMALIZATION['net_balance']) / PK_NORMS[6]

    # ISF normalization on glucose channel (matching _apply_isf_norm)
    features[:, 0] *= (GLUCOSE_SCALE / isf)
    np.clip(features[:, 0], 0, 10, out=features[:, 0])

    return features, isf


def create_sliding_windows(features: np.ndarray, window_size: int,
                           stride: int = None) -> list:
    """Create sliding windows, skipping those with >30% NaN glucose in history.

    Matches the windowing logic in load_bridge_data (exp_pk_forecast_v14.py):
    stride defaults to max(window_size // 3, 12), NaN → 0 after quality check.
    """
    if stride is None:
        stride = max(window_size // 3, 12)
    half = window_size // 2
    N = len(features)
    windows = []
    for start in range(0, N - window_size + 1, stride):
        w = features[start:start + window_size].copy()
        if np.isnan(w[:half, 0]).mean() > 0.3:
            continue
        np.nan_to_num(w, copy=False, nan=0.0)
        windows.append(w)
    return windows


def load_production_model(patient_id: str, window: str,
                          models_dir: str, device: str = 'cpu'):
    """Load a single production model for a patient/window.

    Production models are named: {window_label}_ft_{patient_id}.pth
    """
    import torch

    label = WINDOW_LABELS.get(window, window)
    path = Path(models_dir) / f"{label}_ft_{patient_id}.pth"
    if not path.exists():
        return None

    ckpt = torch.load(str(path), map_location=device, weights_only=False)
    model = _build_model(
        input_dim=ckpt.get('input_dim', 8),
        d_model=ckpt.get('d_model', 64),
        nhead=ckpt.get('nhead', 4),
        num_layers=ckpt.get('num_layers', 4),
    )
    model.load_state_dict(ckpt['model_state'])
    return model.to(torch.device(device)).eval()


def validate_horizons(patients: dict,
                      models_dir: str,
                      device: str = 'cpu',
                      max_windows: int = 50,
                      ) -> dict:
    """Validate forecast accuracy at multiple horizons.

    For each patient, builds 8-channel features from the parquet grid using the
    exact same pipeline as training (PK features + ISF normalization), creates
    sliding windows, runs inference with causal masking, and compares predicted
    vs actual glucose at each horizon.

    Args:
        patients: dict of patient_id → DataFrame.
        models_dir: path to production model .pth files.
        device: 'cpu' or 'cuda'.
        max_windows: max windows to evaluate per patient per horizon.

    Returns:
        Dict with per-patient, per-horizon MAE results.
    """
    if not _torch_available:
        print("ERROR: PyTorch not available")
        return {}

    import torch

    horizons_to_validate = ['h30', 'h60', 'h90', 'h120', 'h150', 'h180']
    results = {}
    overall_errors = {h: [] for h in horizons_to_validate}

    for pid, g in sorted(patients.items()):
        n_samples = len(g)
        days = n_samples * 5 / 1440
        print(f"\n  Patient {pid} ({n_samples} samples, {days:.1f} days)")

        # Build features matching training pipeline
        t0 = time.time()
        features, isf = build_features_from_parquet(g)
        print(f"    ISF={isf:.0f} mg/dL/U, features built in {time.time()-t0:.1f}s")

        patient_errors = {h: [] for h in horizons_to_validate}
        model_cache = {}

        for horizon in horizons_to_validate:
            win_key = HORIZON_ROUTING.get(horizon)
            if win_key is None:
                continue

            cfg = WINDOW_CONFIG.get(win_key)
            if cfg is None:
                continue

            total_len = cfg['total']
            hist_len = cfg['history']
            h_step = HORIZON_STEPS[horizon]

            if h_step >= cfg['future']:
                continue

            # Load model (cache per window key)
            if win_key not in model_cache:
                model_cache[win_key] = load_production_model(
                    pid, win_key, models_dir, device)
            model = model_cache[win_key]
            if model is None:
                print(f"    {horizon}: no model for {pid}/{win_key}")
                continue

            # Create sliding windows
            windows = create_sliding_windows(features, total_len)
            if not windows:
                print(f"    {horizon}: no valid windows")
                continue

            # Subsample if too many
            if len(windows) > max_windows:
                step = len(windows) // max_windows
                windows = windows[::step][:max_windows]

            # Batch inference
            batch = torch.tensor(
                np.array(windows, dtype=np.float32),
                device=torch.device(device))

            horizon_errors = []
            batch_size = 64

            for bi in range(0, len(batch), batch_size):
                xb = batch[bi:bi + batch_size]
                x_in = xb.clone()
                # PK-mode masking: only mask future glucose (ch0),
                # PK channels stay (deterministic from past events)
                x_in[:, hist_len:, 0] = 0.0

                with torch.no_grad():
                    pred = model(x_in, causal=True)

                pred_norm = pred[:, hist_len:, 0].cpu().numpy()
                actual_norm = xb[:, hist_len:, 0].cpu().numpy()

                # Denormalize: pred * ISF (reverses glucose/ISF normalization)
                pred_mg = np.clip(pred_norm * isf, 30.0, 400.0)
                actual_mg = np.clip(actual_norm * isf, 30.0, 400.0)

                if h_step < pred_mg.shape[1]:
                    p_h = pred_mg[:, h_step]
                    a_h = actual_mg[:, h_step]
                    # Filter windows where target was NaN (filled to 0 → <35 after denorm)
                    valid = a_h > 35.0
                    errs = np.abs(p_h[valid] - a_h[valid])
                    horizon_errors.extend(errs.tolist())

            if horizon_errors:
                mae = float(np.mean(horizon_errors))
                patient_errors[horizon] = horizon_errors
                overall_errors[horizon].extend(horizon_errors)
                expected = ROUTED_MAE.get(horizon, 0)
                status = "✓" if mae <= expected * 1.3 else "✗"
                print(f"    {horizon}: MAE={mae:.1f} mg/dL "
                      f"(expected {expected:.1f}, n={len(horizon_errors)}) {status}")

        results[pid] = patient_errors

    # Summary
    print("\n" + "=" * 60)
    print("OVERALL VALIDATION SUMMARY")
    print("=" * 60)

    summary = {}
    all_pass = True
    for horizon in horizons_to_validate:
        errors = overall_errors[horizon]
        if errors:
            mae = float(np.mean(errors))
            expected = ROUTED_MAE.get(horizon, 0)
            within = mae <= expected * 1.3  # 30% tolerance
            status = "PASS" if within else "FAIL"
            if not within:
                all_pass = False
            summary[horizon] = {
                'mae': round(mae, 2),
                'expected': expected,
                'n_windows': len(errors),
                'status': status,
            }
            print(f"  {horizon}: MAE={mae:.1f} mg/dL "
                  f"(expected ≤{expected*1.3:.1f}, n={len(errors)}) [{status}]")
        else:
            print(f"  {horizon}: no data")

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return {'patients': results, 'summary': summary, 'all_pass': all_pass}


def main():
    parser = argparse.ArgumentParser(description="Validate extended forecast horizons")
    parser.add_argument('--tiny', action='store_true', help="Use tiny dataset")
    parser.add_argument('--device', default='cpu', help="Device: cpu or cuda")
    parser.add_argument('--max-windows', type=int, default=50,
                        help="Max eval windows per patient per horizon")
    parser.add_argument('--output', help="Save results to JSON file")
    args = parser.parse_args()

    models_dir = str(PROJECT_ROOT / "externals" / "models" / "production")

    if not Path(models_dir).exists():
        print(f"ERROR: Models directory not found: {models_dir}")
        sys.exit(1)

    patients = load_parquet_patients(tiny=args.tiny)
    if not patients:
        print("ERROR: No patients loaded")
        sys.exit(1)

    print(f"\nValidating {len(patients)} patients at h30-h180...")
    print(f"  Models: {models_dir}")
    print(f"  Device: {args.device}")
    print(f"  Max windows: {args.max_windows}")

    results = validate_horizons(patients, models_dir, args.device, args.max_windows)

    if args.output:
        serializable = {
            'summary': results.get('summary', {}),
            'all_pass': results.get('all_pass', False),
        }
        with open(args.output, 'w') as f:
            json.dump(serializable, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
