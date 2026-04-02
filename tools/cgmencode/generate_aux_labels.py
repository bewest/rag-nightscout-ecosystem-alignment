"""
generate_aux_labels.py — Generate auxiliary training labels for multi-task learning.

Produces per-window labels for all 4 objectives:
  1. Forecast: glucose reconstruction (implicit — the window itself is the target)
  2. Event: meal/exercise/sleep/sick classification from Nightscout treatments
  3. Drift: ISF/CR % deviation from nominal via Kalman filter pseudo-labels
  4. State: metabolic state classification via PatternStateMachine pseudo-labels

Usage:
    from tools.cgmencode.generate_aux_labels import build_multitask_dataset
    dataset = build_multitask_dataset('externals/ns-data/patients', window_size=12)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import TensorDataset

from .label_events import (
    EXTENDED_LABEL_MAP,
    extract_override_events,
    build_pre_event_windows,
    extract_extended_tabular,
)
from .real_data_adapter import build_nightscout_grid, build_extended_features
from .state_tracker import ISFCRTracker, DriftDetector
from .experiment_lib import load_patient_profile


# State label mapping (matches DriftDetector.classify() output)
STATE_LABEL_MAP = {
    'stable': 0,
    'resistance': 1,
    'sensitivity': 2,
    'carb_change': 3,
}

# Event classes for the auxiliary head
N_EVENT_CLASSES = len(EXTENDED_LABEL_MAP)  # 9 (none + 8 event types)
N_STATE_CLASSES = len(STATE_LABEL_MAP)     # 4


def _generate_drift_labels(feat_array, isf_nominal, cr_nominal):
    """Run Kalman filter over feature windows, return per-window drift labels.

    Args:
        feat_array: (N_windows, window_size*2, n_features) numpy array
        isf_nominal: patient's nominal ISF from profile
        cr_nominal: patient's nominal CR from profile

    Returns:
        drift_labels: (N_windows, 2) array of [ISF_pct_dev, CR_pct_dev]
    """
    from .schema import NORMALIZATION_SCALES
    scale_g = NORMALIZATION_SCALES['glucose']
    scale_iob = NORMALIZATION_SCALES.get('iob', 25.0)
    scale_cob = NORMALIZATION_SCALES.get('cob', 200.0)

    n_windows = feat_array.shape[0]
    drift_labels = np.full((n_windows, 2), np.nan, dtype=np.float32)

    tracker = ISFCRTracker(nominal_isf=isf_nominal, nominal_cr=cr_nominal)

    for i in range(n_windows):
        window = feat_array[i]  # (window_size*2, n_features)
        # Use the midpoint of the window for the Kalman observation
        half = window.shape[0] // 2
        # Compute glucose residual: actual change - physics predicted change
        g_start = float(window[0, 0] * scale_g)
        g_mid = float(window[half, 0] * scale_g)
        iob_delta = float((window[half, 1] - window[0, 1]) * scale_iob)
        cob_delta = float((window[half, 2] - window[0, 2]) * scale_cob)

        glucose_residual = (g_mid - g_start) - (
            -iob_delta * isf_nominal + cob_delta * (isf_nominal / cr_nominal)
        )

        state = tracker.update(glucose_residual, iob_delta, cob_delta)
        drift_labels[i, 0] = state['isf_drift_pct']
        drift_labels[i, 1] = state['cr_drift_pct']

    return drift_labels


def _generate_state_labels(drift_labels, isf_nominal, cr_nominal):
    """Classify drift labels into metabolic state categories.

    Uses a local DriftDetector-compatible classification without requiring
    the full Kalman history — operates on the per-window drift outputs.

    Args:
        drift_labels: (N_windows, 2) from _generate_drift_labels
        isf_nominal: patient nominal ISF
        cr_nominal: patient nominal CR

    Returns:
        state_labels: (N_windows,) LongTensor with STATE_LABEL_MAP values
    """
    n = drift_labels.shape[0]
    state_labels = np.zeros(n, dtype=np.int64)
    threshold = 5.0  # matches recalibrated DriftDetector default

    for i in range(n):
        isf_dev = drift_labels[i, 0]
        cr_dev = drift_labels[i, 1]
        if np.isnan(isf_dev) or np.isnan(cr_dev):
            state_labels[i] = -1  # invalid — will be masked in loss
            continue

        if abs(isf_dev) < threshold and abs(cr_dev) < threshold:
            state_labels[i] = STATE_LABEL_MAP['stable']
        elif isf_dev < -threshold:
            state_labels[i] = STATE_LABEL_MAP['resistance']
        elif isf_dev > threshold:
            state_labels[i] = STATE_LABEL_MAP['sensitivity']
        else:
            state_labels[i] = STATE_LABEL_MAP['carb_change']

    return state_labels


def _generate_event_labels(patient_path, n_windows, window_size, stride):
    """Extract event labels for each window center from Nightscout data.

    Args:
        patient_path: path to patient training dir
        n_windows: number of windows
        window_size: half-window size in 5-min steps
        stride: stride between windows in 5-min steps

    Returns:
        event_labels: (n_windows,) array with EXTENDED_LABEL_MAP values
    """
    event_labels = np.zeros(n_windows, dtype=np.int64)  # default: 'none' = 0

    tx_path = os.path.join(patient_path, 'treatments.json')
    ds_path = os.path.join(patient_path, 'devicestatus.json')

    if not os.path.exists(tx_path):
        return event_labels

    events, _ = extract_override_events(
        tx_path, ds_path if os.path.exists(ds_path) else None
    )
    if not events:
        return event_labels

    # Build a map: 5-min step index → event type
    event_steps = {}
    for ev in events:
        step_idx = ev.get('step_index')
        if step_idx is not None:
            label = EXTENDED_LABEL_MAP.get(ev['event_type'], 0)
            if label > event_steps.get(step_idx, 0):
                event_steps[step_idx] = label

    # Map events to window centers
    ws = window_size * 2
    for i in range(n_windows):
        center = i * stride + window_size
        # Check if any event falls within ±window_size of center
        for offset in range(-window_size, window_size):
            step = center + offset
            if step in event_steps:
                event_labels[i] = max(event_labels[i], event_steps[step])

    return event_labels


def build_multitask_windows(patient_paths, window_size=12,
                            split='training', verbose=True):
    """Build multi-task training windows from patient data.

    For each patient:
    1. Load Nightscout grid → 8 or 16 feature windows
    2. Generate event labels from treatments.json
    3. Generate drift labels via Kalman filter
    4. Generate state labels from drift classification

    Args:
        patient_paths: list of paths to patient dirs (parent of training/)
        window_size: half-window in 5-min steps (full window = 2*window_size)
        split: 'training' or 'verification'
        verbose: print progress

    Returns:
        dict with:
            'features': (N, 2*window_size, n_features) numpy array
            'event_labels': (N,) int64 array
            'drift_targets': (N, 2) float32 array
            'state_labels': (N,) int64 array
            'patient_ids': (N,) list of patient name strings
    """
    all_features = []
    all_events = []
    all_drift = []
    all_states = []
    all_pids = []

    ws = window_size * 2
    stride = window_size

    for pdir in patient_paths:
        pdir = Path(pdir)
        patient_name = pdir.name
        data_path = pdir / split
        if not data_path.is_dir():
            continue

        # Build feature grid
        try:
            grid_df, feat8 = build_nightscout_grid(str(data_path), verbose=False)
            if feat8 is None:
                continue
            feat16 = build_extended_features(grid_df, feat8, verbose=False)
        except Exception as e:
            if verbose:
                print(f'  Skip {patient_name}: {e}')
            continue

        # Extract windows
        windows = []
        for start in range(0, feat16.shape[0] - ws, stride):
            w = feat16[start:start + ws]
            if not np.isnan(w[:, 0]).any():
                windows.append(w)

        if not windows:
            continue

        feat_array = np.stack(windows).astype(np.float32)
        n_win = feat_array.shape[0]

        # Load patient profile for Kalman
        isf, cr = load_patient_profile(str(data_path))

        # Generate labels for each objective
        event_labels = _generate_event_labels(str(data_path), n_win, window_size, stride)
        drift_labels = _generate_drift_labels(feat_array, isf, cr)
        state_labels = _generate_state_labels(drift_labels, isf, cr)

        all_features.append(feat_array)
        all_events.append(event_labels)
        all_drift.append(drift_labels)
        all_states.append(state_labels)
        all_pids.extend([patient_name] * n_win)

        if verbose:
            n_events = int((event_labels > 0).sum())
            n_drift = int((~np.isnan(drift_labels[:, 0])).sum() & (np.abs(drift_labels[:, 0]) > 5).sum())
            print(f'  {patient_name}: {n_win} windows, {n_events} events, {n_drift} drifts')

    if not all_features:
        return {
            'features': np.empty((0, ws, 16), dtype=np.float32),
            'event_labels': np.empty(0, dtype=np.int64),
            'drift_targets': np.empty((0, 2), dtype=np.float32),
            'state_labels': np.empty(0, dtype=np.int64),
            'patient_ids': [],
        }

    return {
        'features': np.concatenate(all_features),
        'event_labels': np.concatenate(all_events),
        'drift_targets': np.concatenate(all_drift),
        'state_labels': np.concatenate(all_states),
        'patient_ids': all_pids,
    }


class MultitaskDataset(torch.utils.data.Dataset):
    """Dataset that yields (features, targets_dict) for train_multitask()."""

    def __init__(self, features, event_labels=None, drift_targets=None,
                 state_labels=None):
        """
        Args:
            features: (N, T, F) tensor
            event_labels: (N,) LongTensor or None
            drift_targets: (N, 2) FloatTensor or None
            state_labels: (N,) LongTensor or None
        """
        self.features = features
        self.event_labels = event_labels
        self.drift_targets = drift_targets
        self.state_labels = state_labels

    def __len__(self):
        return self.features.shape[0]

    def __getitem__(self, idx):
        x = self.features[idx]
        targets = {'x': x}
        if self.event_labels is not None:
            targets['event_label'] = self.event_labels[idx]
        if self.drift_targets is not None:
            targets['drift_target'] = self.drift_targets[idx]
        if self.state_labels is not None:
            targets['state_label'] = self.state_labels[idx]
        return x, targets


def build_multitask_dataset(patients_dir, window_size=12, split='training',
                            val_fraction=0.2, seed=42, verbose=True):
    """End-to-end: patients dir → train/val MultitaskDatasets.

    Args:
        patients_dir: path to patients dir with {patient}/{split}/ subdirs
        window_size: half-window in 5-min steps
        split: 'training' or 'verification'
        val_fraction: fraction held out for validation
        seed: random seed for reproducibility
        verbose: print progress

    Returns:
        (train_ds, val_ds, metadata) where metadata has label distributions
    """
    patients_dir = Path(patients_dir)
    patient_paths = sorted(
        d for d in patients_dir.iterdir()
        if d.is_dir() and (d / split).is_dir()
    )

    if verbose:
        print(f'Building multi-task dataset from {len(patient_paths)} patients ({split})')

    data = build_multitask_windows(patient_paths, window_size, split, verbose)
    n = data['features'].shape[0]
    if n == 0:
        raise ValueError(f'No windows extracted from {patients_dir}/{split}')

    # Shuffle
    rng = np.random.RandomState(seed)
    perm = rng.permutation(n)
    features = torch.from_numpy(data['features'][perm])
    events = torch.from_numpy(data['event_labels'][perm])
    drift = torch.from_numpy(data['drift_targets'][perm])
    states = torch.from_numpy(data['state_labels'][perm])

    # Split
    split_idx = int((1 - val_fraction) * n)
    train_ds = MultitaskDataset(
        features[:split_idx], events[:split_idx],
        drift[:split_idx], states[:split_idx],
    )
    val_ds = MultitaskDataset(
        features[split_idx:], events[split_idx:],
        drift[split_idx:], states[split_idx:],
    )

    # Metadata
    event_dist = {k: int((data['event_labels'] == v).sum())
                  for k, v in EXTENDED_LABEL_MAP.items()}
    state_dist = {k: int((data['state_labels'] == v).sum())
                  for k, v in STATE_LABEL_MAP.items()}
    drift_valid = ~np.isnan(data['drift_targets'][:, 0])
    meta = {
        'n_total': n,
        'n_train': split_idx,
        'n_val': n - split_idx,
        'n_patients': len(patient_paths),
        'event_distribution': event_dist,
        'state_distribution': state_dist,
        'drift_valid_pct': round(float(drift_valid.mean() * 100), 1),
        'n_event_classes': N_EVENT_CLASSES,
        'n_state_classes': N_STATE_CLASSES,
    }

    if verbose:
        print(f'  Total: {n} windows ({split_idx} train, {n-split_idx} val)')
        print(f'  Events: {sum(v for k, v in event_dist.items() if k != "none")} labeled')
        print(f'  Drift: {drift_valid.sum()} valid observations')
        print(f'  States: {state_dist}')

    return train_ds, val_ds, meta
