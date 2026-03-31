"""
sim_adapter.py — Bridge between conformance vectors and cgmencode training pipeline.

Converts SIM-* (in-silico) and TV-* (real AAPS replay) conformance vectors into
the same (Samples, TimeSteps, 8) tensor format that FixtureEncoder produces.

This is the GAP-ML-001 fix: the format bridge between aid-autoresearch physics
simulation output and cgmencode's ML training pipeline.

Approach:
  - Each conformance vector contains an algorithm decision snapshot with
    predicted BG trajectories (predBGs.IOB, COB, UAM, ZT).
  - We reconstruct 8-feature time windows by combining the predicted glucose
    trajectory with decayed IOB/COB curves and the profile's basal/action context.
  - Output is numpy arrays compatible with CGMDataset / ConditionedDataset.
"""

import json
import numpy as np
import torch
from pathlib import Path
from typing import List, Tuple, Optional

# Reuse the Dataset classes from encoder.py
from .encoder import CGMDataset, ConditionedDataset


def _exponential_decay(initial: float, half_life_steps: int, n_steps: int) -> np.ndarray:
    """Simple exponential decay curve."""
    if half_life_steps <= 0 or initial == 0:
        return np.zeros(n_steps)
    k = np.log(2) / half_life_steps
    t = np.arange(n_steps)
    return initial * np.exp(-k * t)


def vector_to_features(vec: dict, curve_key: str = 'IOB') -> Optional[np.ndarray]:
    """
    Convert a single SIM-*/TV-* conformance vector into an (N, 8) feature array.

    Feature channels (matching FixtureEncoder schema):
      0: glucose     - from predBGs trajectory
      1: iob         - exponential decay from initial IOB
      2: cob         - exponential decay from initial COB
      3: net_basal   - currentTemp.rate - profile.basalRate
      4: bolus       - zero (post-decision trajectory)
      5: carbs       - zero (post-decision trajectory)
      6: time_sin    - synthetic circadian (if timestamp available)
      7: time_cos    - synthetic circadian (if timestamp available)
    """
    inp = vec.get('input', {})
    out = vec.get('originalOutput', {})

    # Extract prediction trajectory
    pred_bgs = out.get('predBGs', {})
    glucose_curve = pred_bgs.get(curve_key)
    if not glucose_curve or len(glucose_curve) < 6:
        return None

    n_steps = len(glucose_curve)
    features = np.zeros((n_steps, 8), dtype=np.float64)

    # Channel 0: Glucose from prediction trajectory
    features[:, 0] = np.array(glucose_curve, dtype=np.float64)

    # Channel 1: IOB — exponential decay (DIA ~5h = 60 steps at 5min)
    initial_iob = inp.get('iob', {}).get('iob', 0) or 0
    features[:, 1] = _exponential_decay(abs(initial_iob), half_life_steps=30, n_steps=n_steps)
    if initial_iob < 0:
        features[:, 1] *= -1

    # Channel 2: COB — exponential decay (absorption ~3h = 36 steps)
    initial_cob = inp.get('mealData', {}).get('cob', 0) or 0
    features[:, 2] = _exponential_decay(initial_cob, half_life_steps=18, n_steps=n_steps)

    # Channel 3: net_basal
    profile = inp.get('profile', {})
    current_temp = inp.get('currentTemp', {})
    scheduled_basal = profile.get('basalRate', profile.get('current_basal', 0)) or 0
    temp_rate = current_temp.get('rate', scheduled_basal) or scheduled_basal
    features[:, 3] = temp_rate - scheduled_basal

    # Channels 4-5: bolus and carbs are zero (these are post-decision projections)

    # Channels 6-7: circadian time
    gs = inp.get('glucoseStatus', {})
    timestamp = gs.get('timestamp') or gs.get('date')
    if timestamp:
        try:
            from datetime import datetime
            if isinstance(timestamp, str):
                # Try ISO format
                for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    dt = None
            elif isinstance(timestamp, (int, float)):
                dt = datetime.utcfromtimestamp(timestamp / 1000)
            else:
                dt = None

            if dt:
                hour_frac = dt.hour + dt.minute / 60.0
                base_sin = np.sin(2 * np.pi * hour_frac / 24.0)
                base_cos = np.cos(2 * np.pi * hour_frac / 24.0)
                # Advance circadian by 5min per step
                for i in range(n_steps):
                    h = hour_frac + (i * 5 / 60.0)
                    features[i, 6] = np.sin(2 * np.pi * h / 24.0)
                    features[i, 7] = np.cos(2 * np.pi * h / 24.0)
        except Exception:
            pass  # Leave as zeros if timestamp parsing fails

    return features


def normalize_features(data: np.ndarray) -> np.ndarray:
    """Apply the same scaling as FixtureEncoder.generate_training_vectors."""
    scaled = data.copy()
    scaled[:, 0] /= 400.0   # Glucose 0-400 → 0-1
    scaled[:, 1] /= 20.0    # IOB 0-20 → 0-1
    scaled[:, 2] /= 100.0   # COB 0-100 → 0-1
    scaled[:, 3] /= 5.0     # Net basal -5..5 → -1..1
    scaled[:, 4] /= 10.0    # Bolus 0-10 → 0-1
    scaled[:, 5] /= 100.0   # Carbs 0-100 → 0-1
    # time_sin/cos already -1..1
    return scaled


def load_conformance_vectors(
    dirs: List[str],
    curve_keys: List[str] = None,
    min_steps: int = 12,
) -> List[np.ndarray]:
    """
    Load SIM-*/TV-* conformance vectors and convert to normalized feature arrays.

    Args:
        dirs: Directories containing .json conformance vectors
        curve_keys: Which predBGs curves to use (default: all available)
        min_steps: Minimum trajectory length to include

    Returns:
        List of (N, 8) normalized numpy arrays, one per trajectory
    """
    if curve_keys is None:
        curve_keys = ['IOB', 'COB', 'UAM', 'ZT']

    results = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for json_file in sorted(p.glob('*.json')):
            try:
                with open(json_file) as f:
                    vec = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            pred_bgs = vec.get('originalOutput', {}).get('predBGs', {})
            for key in curve_keys:
                if key in pred_bgs and len(pred_bgs[key]) >= min_steps:
                    features = vector_to_features(vec, curve_key=key)
                    if features is not None and len(features) >= min_steps:
                        results.append(normalize_features(features))

    return results


def load_conformance_to_dataset(
    dirs: List[str],
    task: str = 'reconstruct',
    window_size: int = 12,
    val_split: float = 0.2,
    conditioned: bool = False,
    curve_keys: List[str] = None,
) -> Tuple[Optional[torch.utils.data.Dataset], Optional[torch.utils.data.Dataset]]:
    """
    Load conformance vectors and return (train_ds, val_ds) compatible with
    the existing cgmencode training pipeline.

    This is the primary entry point — the bridge between aid-autoresearch
    physics output and cgmencode ML training.
    """
    trajectories = load_conformance_vectors(dirs, curve_keys=curve_keys)
    if not trajectories:
        return None, None

    # Pad or truncate to uniform length for batching
    # Use the trajectories directly as training windows
    all_vectors = []
    for traj in trajectories:
        # For short trajectories, use them as-is (single window)
        if len(traj) >= window_size + 6:
            # Sliding window to get more samples
            total_len = window_size + 6  # window + small lead/result
            for i in range(len(traj) - total_len + 1):
                all_vectors.append(traj[i:i + total_len])
        elif len(traj) >= window_size:
            all_vectors.append(traj[:window_size + min(6, len(traj) - window_size)])

    if not all_vectors:
        return None, None

    # Pad to same length for stacking
    max_len = max(v.shape[0] for v in all_vectors)
    padded = np.zeros((len(all_vectors), max_len, 8), dtype=np.float64)
    for i, v in enumerate(all_vectors):
        padded[i, :v.shape[0], :] = v

    np.random.shuffle(padded)
    split_idx = int(len(padded) * (1 - val_split))
    train_v, val_v = padded[:split_idx], padded[split_idx:]

    if conditioned:
        return (ConditionedDataset(train_v, window_size=window_size),
                ConditionedDataset(val_v, window_size=window_size))

    return (CGMDataset(train_v, task=task, window_size=window_size),
            CGMDataset(val_v, task=task, window_size=window_size))


if __name__ == '__main__':
    import sys

    # Default: load from this repo's conformance directories
    default_dirs = [
        'conformance/in-silico/vectors',
        'conformance/t1pal/vectors/oref0-endtoend',
    ]

    dirs = sys.argv[1:] if len(sys.argv) > 1 else default_dirs

    print("=== Conformance Vector → cgmencode Bridge ===")
    print(f"Scanning: {dirs}")

    trajectories = load_conformance_vectors(dirs)
    print(f"Loaded {len(trajectories)} trajectories")
    if trajectories:
        lengths = [len(t) for t in trajectories]
        print(f"  Trajectory lengths: min={min(lengths)}, max={max(lengths)}, median={sorted(lengths)[len(lengths)//2]}")
        print(f"  Feature shape: ({trajectories[0].shape[1]},) per timestep")

    print()
    print("--- Training Dataset ---")
    train_ds, val_ds = load_conformance_to_dataset(dirs, task='forecast', window_size=12)
    if train_ds:
        print(f"  Train samples: {len(train_ds)}")
        print(f"  Val samples: {len(val_ds)}")
        x, y = train_ds[0]
        print(f"  Sample shape: {x.shape}")
    else:
        print("  No usable data found.")
