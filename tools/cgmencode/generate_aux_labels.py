"""
generate_aux_labels.py — Generate auxiliary training labels for multi-task learning.

Produces per-window labels for all 4 objectives:
  1. Forecast: glucose reconstruction (implicit — the window itself is the target)
  2. Event: meal/exercise/sleep/sick classification from Nightscout treatments
  3. Drift: ISF/CR % deviation from nominal via Kalman filter pseudo-labels
  4. State: metabolic state classification via PatternStateMachine pseudo-labels

Drift and state labels are calibrated against clinical autosens algorithms:
  - oref0/oref1 autosens (OpenAPS Reference Design)
  - AAPS SensitivityOref1Plugin (8h + 24h dual-window)
  - Trio autosens (conservative lowest-ratio selection)

Key clinical alignments (EXP-154):
  - Meal exclusion: skip Kalman updates during COB absorption (autosens rule)
  - Low BG protection: suppress positive deviations when BG < 80 mg/dL
  - Bounded ratio: ISF ratio clamped to [autosens_min, autosens_max] = [0.7, 1.2]
  - State thresholds: use autosens ratio bounds, not fixed % threshold
  - CGM accuracy: 20/20 rule (±20% above 80, ±20 mg/dL below 80)

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

# ── Clinical calibration constants (from oref0/AAPS/Trio autosens) ──────
# Autosens ratio bounds: how far ISF can drift from nominal.
# oref0: autosens_min=0.7, autosens_max=1.2 (profile/index.js:18-19)
# AAPS:  AutosensMin=0.7 (0.1-1.0), AutosensMax=1.2 (0.5-3.0)
# Trio:  autosensMin=0.7, autosensMax=1.2
AUTOSENS_MIN = 0.7   # Max resistance: ISF at 70% of nominal
AUTOSENS_MAX = 1.2   # Max sensitivity: ISF at 120% of nominal

# Meal exclusion: skip drift updates when COB exceeds this threshold.
# oref0 excludes ALL windows where COB > 0 plus first 45min post-carb.
# We use a small threshold to tolerate rounding artifacts.
COB_EXCLUSION_THRESHOLD_G = 0.5  # grams (normalized COB * scale > this → skip)

# Low BG protection threshold (mg/dL).
# oref0: "set positive deviations to zero if BG is below 80" (autosens.js:196)
LOW_BG_THRESHOLD_MGDL = 80.0

# Autosens-style state classification thresholds (ratio space).
# ratio < RESISTANCE_RATIO → resistance (need more insulin)
# ratio > SENSITIVITY_RATIO → sensitivity (need less insulin)
# In between → stable
# These map to ±10% from nominal (ratio 0.9–1.1) which is tighter than
# the hard bounds (0.7–1.2) but wider than zero-crossing used by raw autosens.
RESISTANCE_RATIO = 0.90   # ISF at 90% of nominal = mild resistance
SENSITIVITY_RATIO = 1.10  # ISF at 110% of nominal = mild sensitivity

# CGM accuracy bounds: 20/20 rule (ISO 15197 / FDA guidance)
# CGM reading must be within ±20% of reference above 80 mg/dL,
# or within ±20 mg/dL below 80 mg/dL.
CGM_20_20_PCT = 0.20       # 20% relative error above 80
CGM_20_20_ABS = 20.0       # 20 mg/dL absolute error below 80
CGM_20_20_THRESHOLD = 80.0 # mg/dL boundary between relative and absolute


def cgm_accuracy_within_20_20(predicted_mgdl, actual_mgdl):
    """Check if predicted glucose is within 20/20 CGM accuracy bounds.

    The 20/20 rule: a CGM reading is considered accurate if:
      - Above 80 mg/dL: within ±20% of reference
      - Below 80 mg/dL: within ±20 mg/dL of reference

    Args:
        predicted_mgdl: predicted glucose value(s) in mg/dL
        actual_mgdl: actual/reference glucose value(s) in mg/dL

    Returns:
        Boolean array (or scalar) indicating accuracy compliance
    """
    predicted_mgdl = np.asarray(predicted_mgdl, dtype=np.float64)
    actual_mgdl = np.asarray(actual_mgdl, dtype=np.float64)

    is_above = actual_mgdl >= CGM_20_20_THRESHOLD
    abs_error = np.abs(predicted_mgdl - actual_mgdl)
    # Relative error for readings above threshold
    rel_error = np.where(actual_mgdl > 0,
                         abs_error / actual_mgdl,
                         np.inf)
    within = np.where(is_above,
                      rel_error <= CGM_20_20_PCT,
                      abs_error <= CGM_20_20_ABS)
    return within


def compute_class_weights(labels, n_classes, smoothing=0.1):
    """Compute inverse-frequency class weights for imbalanced classification.

    Uses smoothed inverse frequency: w_c = N / (n_classes * count_c + smoothing*N)
    This prevents infinite weights for absent classes and reduces the
    dominance of majority classes (e.g., correction_bolus at 54%).

    Args:
        labels: (N,) int array of class indices
        n_classes: total number of classes
        smoothing: Laplace smoothing factor (0.1 = 10% of uniform)

    Returns:
        weights: (n_classes,) float32 array of per-class weights
    """
    counts = np.bincount(labels[labels >= 0], minlength=n_classes).astype(np.float64)
    n_total = float(counts.sum())
    if n_total == 0:
        return np.ones(n_classes, dtype=np.float32)
    smoothed = counts + smoothing * n_total / n_classes
    weights = n_total / (n_classes * smoothed)
    return weights.astype(np.float32)


def _generate_drift_labels(feat_array, isf_nominal, cr_nominal):
    """Run Kalman filter over feature windows, return per-window drift labels.

    Aligned with oref0 autosens clinical algorithm (EXP-154):
      - Excludes meal absorption windows (COB > threshold) from Kalman updates
      - Suppresses positive deviations when BG < 80 mg/dL (low BG protection)
      - Expresses drift as autosens ratio [AUTOSENS_MIN, AUTOSENS_MAX]
        then converts to signed fractional deviation

    The autosens algorithm (oref0/lib/determine-basal/autosens.js) works by:
      1. Computing deviation = actual_delta - predicted_delta (BGI)
      2. Excluding all deviations during carb absorption (COB > 0)
      3. Zeroing positive deviations when BG < 80 (prevent false sensitivity)
      4. Taking median of remaining non-meal deviations
      5. Converting to ratio bounded by [0.7, 1.2]

    Our Kalman approach tracks the same underlying signal but with Bayesian
    updating instead of percentile statistics. We add autosens's exclusion
    rules to improve label quality.

    Args:
        feat_array: (N_windows, window_size*2, n_features) numpy array
        isf_nominal: patient's nominal ISF from profile
        cr_nominal: patient's nominal CR from profile

    Returns:
        drift_labels: (N_windows, 2) array of [ISF_ratio_dev, CR_ratio_dev]
            Values expressed as signed fractional deviation from ratio=1.0:
              -0.3 means ratio=0.7 (max resistance, autosens_min)
              +0.2 means ratio=1.2 (max sensitivity, autosens_max)
              0.0 means ratio=1.0 (nominal, no drift)
    """
    from .schema import NORMALIZATION_SCALES
    scale_g = NORMALIZATION_SCALES['glucose']
    scale_iob = NORMALIZATION_SCALES.get('iob', 20.0)
    scale_cob = NORMALIZATION_SCALES.get('cob', 100.0)

    n_windows = feat_array.shape[0]
    drift_labels = np.full((n_windows, 2), np.nan, dtype=np.float32)

    tracker = ISFCRTracker(nominal_isf=isf_nominal, nominal_cr=cr_nominal)

    # Track meal exclusion windows for logging
    n_meal_excluded = 0
    n_low_bg_suppressed = 0

    for i in range(n_windows):
        window = feat_array[i]  # (window_size*2, n_features)
        half = window.shape[0] // 2

        # ── Denormalize key values ──
        g_start = float(window[0, 0] * scale_g)
        g_mid = float(window[half, 0] * scale_g)
        iob_delta = float((window[half, 1] - window[0, 1]) * scale_iob)
        cob_delta = float((window[half, 2] - window[0, 2]) * scale_cob)

        # COB at midpoint (denormalized)
        cob_mid = float(window[half, 2] * scale_cob)
        # Mean COB over first half of window
        cob_mean_first_half = float(window[:half, 2].mean() * scale_cob)

        # ── Meal exclusion (autosens rule) ──
        # oref0 autosens excludes ALL deviations during carb absorption
        # (COB > 0, or first 45min post-carb, or high IOB + positive deviation).
        # We exclude windows where COB is significant in either half.
        if cob_mid > COB_EXCLUSION_THRESHOLD_G or cob_mean_first_half > COB_EXCLUSION_THRESHOLD_G:
            n_meal_excluded += 1
            # Still record the current ratio estimate but don't update Kalman
            isf_est, cr_est = tracker.state[0], tracker.state[1]
            isf_ratio = isf_est / isf_nominal if isf_nominal else 1.0
            cr_ratio = cr_est / cr_nominal if cr_nominal else 1.0
            isf_ratio = np.clip(isf_ratio, AUTOSENS_MIN, AUTOSENS_MAX)
            cr_ratio = np.clip(cr_ratio, AUTOSENS_MIN, AUTOSENS_MAX)
            drift_labels[i, 0] = float(isf_ratio - 1.0)
            drift_labels[i, 1] = float(cr_ratio - 1.0)
            continue

        # ── Compute glucose residual ──
        glucose_residual = (g_mid - g_start) - (
            -iob_delta * isf_nominal + cob_delta * (isf_nominal / cr_nominal)
        )

        # ── Low BG protection (autosens rule) ──
        # oref0: "set positive deviations to zero if BG is below 80"
        # Prevents false sensitivity detection during hypoglycemia recovery
        if g_mid < LOW_BG_THRESHOLD_MGDL and glucose_residual > 0:
            glucose_residual = 0.0
            n_low_bg_suppressed += 1

        # ── Kalman update ──
        state = tracker.update(glucose_residual, iob_delta, cob_delta)

        # ── Convert to autosens-bounded ratio ──
        isf_est, cr_est = tracker.state[0], tracker.state[1]
        isf_ratio = isf_est / isf_nominal if isf_nominal else 1.0
        cr_ratio = cr_est / cr_nominal if cr_nominal else 1.0

        # Clamp to autosens bounds [0.7, 1.2]
        isf_ratio = np.clip(isf_ratio, AUTOSENS_MIN, AUTOSENS_MAX)
        cr_ratio = np.clip(cr_ratio, AUTOSENS_MIN, AUTOSENS_MAX)

        # Express as signed deviation from 1.0
        # -0.3 = ratio 0.7 = max resistance
        # +0.2 = ratio 1.2 = max sensitivity
        drift_labels[i, 0] = float(isf_ratio - 1.0)
        drift_labels[i, 1] = float(cr_ratio - 1.0)

    return drift_labels


def _generate_state_labels(drift_labels, isf_nominal, cr_nominal):
    """Classify drift labels into metabolic state categories.

    Uses autosens-aligned ratio thresholds instead of fixed percentages.
    This aligns with how oref0/AAPS/Trio classify sensitivity states:
      - oref0: median deviation < 0 → sensitivity, > 0 → resistance
      - Our approach: ISF ratio relative to autosens bounds
        ratio < RESISTANCE_RATIO (0.90) → resistance
        ratio > SENSITIVITY_RATIO (1.10) → sensitivity
        otherwise → stable
      - CR drift without ISF change → carb_change

    The old 15% fixed threshold produced 73% resistance labels because
    the Kalman filter routinely drifted >15% from nominal on noisy data.
    The new approach uses bounded ratios [0.7, 1.2] with tighter
    classification bands [0.9, 1.1] for ±10% state changes, matching
    the clinical significance level that autosens acts on.

    Args:
        drift_labels: (N_windows, 2) from _generate_drift_labels
            Values are signed deviations from ratio 1.0:
              col 0: ISF ratio deviation (-0.3 to +0.2)
              col 1: CR ratio deviation (-0.3 to +0.2)
        isf_nominal: patient nominal ISF (unused, kept for API compat)
        cr_nominal: patient nominal CR (unused, kept for API compat)

    Returns:
        state_labels: (N_windows,) int64 array with STATE_LABEL_MAP values
    """
    n = drift_labels.shape[0]
    state_labels = np.zeros(n, dtype=np.int64)

    # Thresholds in ratio-deviation space:
    # ISF ratio deviation of -0.10 means ratio=0.90 → mild resistance
    # ISF ratio deviation of +0.10 means ratio=1.10 → mild sensitivity
    isf_resist_thresh = RESISTANCE_RATIO - 1.0   # -0.10
    isf_sens_thresh = SENSITIVITY_RATIO - 1.0     # +0.10
    cr_thresh = 0.10  # ±10% CR change for carb_change state

    for i in range(n):
        isf_dev = drift_labels[i, 0]
        cr_dev = drift_labels[i, 1]

        if np.isnan(isf_dev) or np.isnan(cr_dev):
            state_labels[i] = -1  # invalid — will be masked in loss
            continue

        if isf_dev < isf_resist_thresh:
            # ISF below 90% of nominal → resistance
            state_labels[i] = STATE_LABEL_MAP['resistance']
        elif isf_dev > isf_sens_thresh:
            # ISF above 110% of nominal → sensitivity
            state_labels[i] = STATE_LABEL_MAP['sensitivity']
        elif abs(cr_dev) > cr_thresh and abs(isf_dev) <= isf_sens_thresh:
            # CR changed >10% but ISF is stable → carb_change
            state_labels[i] = STATE_LABEL_MAP['carb_change']
        else:
            state_labels[i] = STATE_LABEL_MAP['stable']

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

    # Convert event timestamps to 5-min step indices relative to grid start.
    # extract_override_events returns events with 'timestamp' (datetime) but
    # no 'step_index'. We need to compute step indices from the grid.
    import pandas as pd
    try:
        grid_df, _ = build_nightscout_grid(patient_path, verbose=False)
        if grid_df is not None and len(grid_df) > 0:
            grid_start = grid_df.index[0]
            for ev in events:
                ts = ev.get('timestamp')
                if ts is not None:
                    if isinstance(ts, str):
                        ts = pd.Timestamp(ts)
                    delta = (ts - grid_start).total_seconds() / 300  # 5-min steps
                    ev['step_index'] = int(round(delta))
    except Exception:
        pass  # fall through — events without step_index are skipped below

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
            n_drift = int(((~np.isnan(drift_labels[:, 0])) & (np.abs(drift_labels[:, 0]) > 0.05)).sum())
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

    # Compute class weights for loss balancing (EXP-154/158)
    event_weights = compute_class_weights(data['event_labels'], N_EVENT_CLASSES)
    state_weights = compute_class_weights(data['state_labels'], N_STATE_CLASSES)

    # Label quality diagnostics
    drift_vals = data['drift_targets'][drift_valid]
    max_class_pct = max(
        (v / n * 100) for v in state_dist.values()
    ) if n > 0 else 0.0
    isf_drift_range = (float(drift_vals[:, 0].min()), float(drift_vals[:, 0].max())) if len(drift_vals) > 0 else (0.0, 0.0)
    cr_drift_range = (float(drift_vals[:, 1].min()), float(drift_vals[:, 1].max())) if len(drift_vals) > 0 else (0.0, 0.0)

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
        # EXP-154: class weights and quality diagnostics
        'event_class_weights': event_weights.tolist(),
        'state_class_weights': state_weights.tolist(),
        'label_quality': {
            'max_state_class_pct': round(max_class_pct, 1),
            'isf_drift_range': isf_drift_range,
            'cr_drift_range': cr_drift_range,
            'autosens_bounds': [AUTOSENS_MIN, AUTOSENS_MAX],
            'state_thresholds': [RESISTANCE_RATIO, SENSITIVITY_RATIO],
        },
    }

    if verbose:
        print(f'  Total: {n} windows ({split_idx} train, {n-split_idx} val)')
        print(f'  Events: {sum(v for k, v in event_dist.items() if k != "none")} labeled')
        print(f'  Drift: {drift_valid.sum()} valid observations')
        print(f'  States: {state_dist}')
        print(f'  Label quality:')
        print(f'    Max state class: {max_class_pct:.1f}% (target <50%)')
        print(f'    ISF drift range: [{isf_drift_range[0]:.3f}, {isf_drift_range[1]:.3f}]'
              f' (autosens bounds: [{AUTOSENS_MIN-1:.1f}, {AUTOSENS_MAX-1:.1f}])')
        print(f'    Event weights: {dict(zip(list(EXTENDED_LABEL_MAP.keys())[:4], event_weights[:4].tolist()))}')
        print(f'    State weights: {dict(zip(STATE_LABEL_MAP.keys(), state_weights.tolist()))}')

    return train_ds, val_ds, meta
