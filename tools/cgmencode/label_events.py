"""EXP-023: Mine event labels from Nightscout treatment logs.

Extracts meal events, bolus events, and override events from treatment
data, then annotates CGM windows with binary labels for event classification.

Usage:
    python3 -m tools.cgmencode.label_events \
        --patients-dir externals/ns-data/patients \
        --output externals/experiments/event_labels.json

Output: JSON with per-patient labeled windows ready for XGBoost training.
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .real_data_adapter import build_nightscout_grid
from .schema import (
    NORMALIZATION_SCALES, FEATURE_NAMES, IDX_GLUCOSE,
    OVERRIDE_TYPES,
)


# Event detection configuration
MEAL_CARB_THRESHOLD = 1.0     # minimum carbs (g) to count as meal
BOLUS_THRESHOLD = 0.1         # minimum insulin (U) to count as bolus
WINDOW_BEFORE_MIN = 15        # look-back window (minutes) for pre-event features
WINDOW_AFTER_MIN = 60         # look-ahead window (minutes) for post-event features
GRID_INTERVAL_MIN = 5         # 5-minute grid

# Override reason → category mapping (fuzzy match on lowercased reason)
OVERRIDE_REASON_MAP = {
    'eating soon': 'eating_soon',
    'eating': 'eating_soon',
    'pre-meal': 'eating_soon',
    'exercise': 'exercise',
    'workout': 'exercise',
    'running': 'exercise',
    'walking': 'exercise',
    'gym': 'exercise',
    'sleep': 'sleep',
    'sleeping': 'sleep',
    'bedtime': 'sleep',
    'night': 'sleep',
    'sick': 'sick',
    'illness': 'sick',
    'ill': 'sick',
    'sickness': 'sick',
}

# Extended label map: adds override subtypes
EXTENDED_LABEL_MAP = {
    'none': 0,
    'meal': 1,
    'correction_bolus': 2,
    'override': 3,           # generic/unknown override
    'eating_soon': 4,
    'exercise': 5,
    'sleep': 6,
    'sick': 7,
    'custom_override': 8,
}

# Pre-event lead times in 5-min steps
LEAD_TIME_STEPS = [3, 6, 9, 12]  # 15, 30, 45, 60 minutes


def extract_events_from_treatments(treatments_path):
    """Parse treatments.json and extract labeled events.

    Returns a list of event dicts:
      {'timestamp': pd.Timestamp, 'event_type': str, 'carbs': float,
       'insulin': float, 'absorption_time': int, ...}
    """
    with open(treatments_path) as f:
        treatments = json.load(f)

    events = []
    event_type_counts = Counter()

    for tx in treatments:
        et = tx.get('eventType', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str).round(f'{GRID_INTERVAL_MIN}min')

        event_type_counts[et] += 1

        carbs = float(tx.get('carbs') or 0)
        insulin = float(tx.get('insulin') or 0)

        # Meal event
        if carbs >= MEAL_CARB_THRESHOLD:
            events.append({
                'timestamp': ts,
                'event_type': 'meal',
                'carbs': carbs,
                'insulin': insulin,
                'food_type': tx.get('foodType', ''),
                'absorption_time': tx.get('absorptionTime', 180),
                'raw_event_type': et,
            })

        # Bolus-only event (correction, not paired with meal)
        elif insulin >= BOLUS_THRESHOLD and carbs < MEAL_CARB_THRESHOLD:
            events.append({
                'timestamp': ts,
                'event_type': 'correction_bolus',
                'carbs': carbs,
                'insulin': insulin,
                'raw_event_type': et,
            })

        # Override event
        elif et == 'Temporary Override':
            events.append({
                'timestamp': ts,
                'event_type': 'override',
                'duration': tx.get('duration', 0),
                'reason': tx.get('reason', ''),
                'raw_event_type': et,
            })

    return events, dict(event_type_counts)


def build_feature_windows(grid_df, events, window_steps=12):
    """Build labeled windows around each event.

    For each event, extract a window of features from the grid
    centered on the event timestamp. Also extract negative (no-event)
    windows for balanced classification.

    Args:
        grid_df: DataFrame with 5-min grid (from build_nightscout_grid)
        events: list of event dicts from extract_events_from_treatments
        window_steps: number of 5-min steps for the feature window

    Returns:
        features: (N, window_steps, n_features) array
        labels: (N,) array of event type indices
        metadata: list of dicts with event info
    """
    feature_cols = ['glucose', 'iob', 'cob', 'net_basal', 'bolus',
                    'carbs', 'time_sin', 'time_cos']
    scales = [NORMALIZATION_SCALES.get(c, 1.0) for c in feature_cols]

    # Ensure grid is sorted and has DatetimeIndex
    if not isinstance(grid_df.index, pd.DatetimeIndex):
        grid_df.index = pd.to_datetime(grid_df.index)
    grid_df = grid_df.sort_index()

    # Build lookup: timestamp → grid index
    ts_to_idx = {ts: i for i, ts in enumerate(grid_df.index)}

    # Collect positive windows
    pos_features = []
    pos_labels = []
    pos_meta = []
    event_indices = set()  # grid indices that have events

    label_map = {'meal': 1, 'correction_bolus': 2, 'override': 3}

    for ev in events:
        ts = ev['timestamp']
        idx = ts_to_idx.get(ts)
        if idx is None:
            # Try nearest grid point
            diffs = np.abs((grid_df.index - ts).total_seconds())
            nearest = int(np.argmin(diffs))
            if diffs[nearest] <= GRID_INTERVAL_MIN * 60:
                idx = nearest
            else:
                continue

        # Need window_steps before event for context
        start = idx - window_steps
        end = idx
        if start < 0 or end >= len(grid_df):
            continue

        # Extract normalized features
        window_data = grid_df.iloc[start:end][feature_cols].values
        # Normalize
        window_norm = window_data / np.array(scales)

        # Check for valid glucose (no NaN, no zeros)
        glucose_col = window_norm[:, 0]
        if np.any(np.isnan(glucose_col)) or np.any(glucose_col <= 0):
            continue

        pos_features.append(window_norm)
        pos_labels.append(label_map.get(ev['event_type'], 0))
        pos_meta.append({
            'event_type': ev['event_type'],
            'timestamp': str(ts),
            'carbs': ev.get('carbs', 0),
            'insulin': ev.get('insulin', 0),
        })
        event_indices.add(idx)

    # Collect negative windows (no event within ±30 min)
    neg_features = []
    neg_labels = []
    neg_meta = []
    buffer_steps = 6  # 30 min buffer around events

    # Sample ~3x negative windows for balance
    n_neg_target = len(pos_features) * 3
    rng = np.random.RandomState(42)
    candidate_indices = []
    for i in range(window_steps, len(grid_df)):
        # Check no event within buffer
        if not any(abs(i - ei) <= buffer_steps for ei in event_indices):
            candidate_indices.append(i)

    if candidate_indices:
        chosen = rng.choice(candidate_indices,
                            size=min(n_neg_target, len(candidate_indices)),
                            replace=False)
        for idx in chosen:
            start = idx - window_steps
            end = idx
            window_data = grid_df.iloc[start:end][feature_cols].values
            window_norm = window_data / np.array(scales)
            glucose_col = window_norm[:, 0]
            if np.any(np.isnan(glucose_col)) or np.any(glucose_col <= 0):
                continue
            neg_features.append(window_norm)
            neg_labels.append(0)  # no event
            neg_meta.append({
                'event_type': 'none',
                'timestamp': str(grid_df.index[idx]),
            })

    # Combine
    all_features = pos_features + neg_features
    all_labels = pos_labels + neg_labels
    all_meta = pos_meta + neg_meta

    if not all_features:
        return np.array([]), np.array([]), []

    features = np.stack(all_features, axis=0)
    labels = np.array(all_labels)

    return features, labels, all_meta


def extract_tabular_features(windows):
    """Convert windowed features to flat tabular features for XGBoost.

    From each (window_steps, 8) window, extract:
    - Last-step values (current state)
    - Trends (slope over window)
    - Statistics (mean, std, min, max of glucose)
    - Action summaries (total carbs, total bolus in window)

    Returns: (N, n_tabular_features) array
    """
    N, T, F = windows.shape
    features = []

    for i in range(N):
        w = windows[i]  # (T, 8)
        row = []

        # Current state (last timestep)
        row.extend(w[-1, :].tolist())  # 8 features

        # Glucose trend (slope over window, mg/dL per 5min)
        glucose = w[:, 0] * NORMALIZATION_SCALES['glucose']
        if T > 1:
            trend = (glucose[-1] - glucose[0]) / (T - 1)
            row.append(trend)
        else:
            row.append(0.0)

        # Glucose statistics
        row.append(float(np.mean(glucose)))
        row.append(float(np.std(glucose)))
        row.append(float(np.min(glucose)))
        row.append(float(np.max(glucose)))

        # IOB trend
        iob = w[:, 1] * NORMALIZATION_SCALES['iob']
        row.append(float(iob[-1] - iob[0]))  # IOB change

        # Total carbs and bolus in window
        carbs_total = float(np.sum(w[:, 5]) * NORMALIZATION_SCALES['carbs'])
        bolus_total = float(np.sum(w[:, 4]) * NORMALIZATION_SCALES['bolus'])
        row.append(carbs_total)
        row.append(bolus_total)

        # Time features (already sin/cos in last 2 columns)
        # Hour of day (decode from sin/cos)
        sin_t = w[-1, 6]
        cos_t = w[-1, 7]
        hour = np.arctan2(sin_t, cos_t) * 12 / np.pi
        if hour < 0:
            hour += 24
        row.append(hour)

        features.append(row)

    feature_names = [
        'glucose_now', 'iob_now', 'cob_now', 'net_basal_now',
        'bolus_now', 'carbs_now', 'time_sin', 'time_cos',
        'glucose_trend', 'glucose_mean', 'glucose_std',
        'glucose_min', 'glucose_max', 'iob_change',
        'carbs_total', 'bolus_total', 'hour_of_day',
    ]

    return np.array(features), feature_names


def mine_patient_events(patient_dir, window_steps=12):
    """Mine events from a single patient directory.

    Returns:
        dict with event counts, features, labels, tabular features
    """
    patient_dir = str(patient_dir)
    treatments_path = os.path.join(patient_dir, 'treatments.json')
    if not os.path.exists(treatments_path):
        return None

    # Extract events
    events, et_counts = extract_events_from_treatments(treatments_path)

    # Build grid
    grid_df, stats = build_nightscout_grid(patient_dir)
    if grid_df is None:
        return None

    # Add time encoding columns (sin/cos of hour-of-day)
    hours = grid_df.index.hour + grid_df.index.minute / 60.0
    grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
    grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)

    # Build windows
    features, labels, meta = build_feature_windows(grid_df, events, window_steps)
    if len(features) == 0:
        return None

    # Extract tabular features
    tabular, tab_names = extract_tabular_features(features)

    event_counts = Counter(m['event_type'] for m in meta)

    return {
        'event_type_counts': et_counts,
        'event_counts': dict(event_counts),
        'n_windows': len(features),
        'n_positive': int(np.sum(labels > 0)),
        'n_negative': int(np.sum(labels == 0)),
        'features': features,       # (N, T, 8) windowed
        'tabular': tabular,          # (N, 17) flat
        'tabular_names': tab_names,
        'labels': labels,            # (N,) int
        'metadata': meta,
    }


def mine_all_patients(patients_dir, window_steps=12):
    """Mine events from all patients in a directory.

    Returns combined dataset + per-patient summaries.
    """
    patients_dir = Path(patients_dir)
    patient_dirs = sorted(
        d / 'training' for d in patients_dir.iterdir()
        if d.is_dir() and (d / 'training').is_dir()
    )

    all_tabular = []
    all_labels = []
    all_meta = []
    patient_summaries = {}

    for pd_path in patient_dirs:
        patient_name = pd_path.parent.name
        print(f'  Patient {patient_name}: {pd_path}')

        result = mine_patient_events(str(pd_path), window_steps)
        if result is None:
            print(f'    SKIP — no valid data')
            continue

        print(f'    Events: {result["event_counts"]}')
        print(f'    Windows: {result["n_positive"]} positive, '
              f'{result["n_negative"]} negative')

        patient_summaries[patient_name] = {
            'event_type_counts': result['event_type_counts'],
            'event_counts': result['event_counts'],
            'n_windows': result['n_windows'],
            'n_positive': result['n_positive'],
            'n_negative': result['n_negative'],
        }

        all_tabular.append(result['tabular'])
        all_labels.append(result['labels'])
        for m in result['metadata']:
            m['patient'] = patient_name
        all_meta.extend(result['metadata'])

    if not all_tabular:
        return None

    combined_tabular = np.concatenate(all_tabular, axis=0)
    combined_labels = np.concatenate(all_labels, axis=0)

    total_counts = Counter(m['event_type'] for m in all_meta)

    return {
        'tabular': combined_tabular,
        'labels': combined_labels,
        'tabular_names': result['tabular_names'],
        'metadata': all_meta,
        'patient_summaries': patient_summaries,
        'total_event_counts': dict(total_counts),
        'n_patients': len(patient_summaries),
    }


def classify_override_reason(reason_str):
    """Classify an override reason string into a canonical category.

    Uses fuzzy matching (lowercase substring) against OVERRIDE_REASON_MAP.

    Returns one of: 'eating_soon', 'exercise', 'sleep', 'sick', 'custom_override'
    """
    if not reason_str:
        return 'custom_override'
    lower = reason_str.lower().strip()
    for keyword, category in OVERRIDE_REASON_MAP.items():
        if keyword in lower:
            return category
    return 'custom_override'


def extract_override_events(treatments_path, devicestatus_path=None):
    """Extract rich override events from treatments and devicestatus.

    Unlike extract_events_from_treatments (which lumps all overrides),
    this classifies overrides into subtypes: eating_soon, exercise, sleep, sick.

    Also mines Loop overrideStatus from devicestatus.json if provided.

    Returns:
        events: list of event dicts with 'event_type' in EXTENDED_LABEL_MAP keys
        stats: dict of extraction statistics
    """
    events = []
    stats = Counter()

    # --- Mine treatments.json ---
    with open(treatments_path) as f:
        treatments = json.load(f)

    for tx in treatments:
        et = tx.get('eventType', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str).round(f'{GRID_INTERVAL_MIN}min')

        carbs = float(tx.get('carbs') or 0)
        insulin = float(tx.get('insulin') or 0)

        # Standard meal/bolus events (same as original)
        if carbs >= MEAL_CARB_THRESHOLD:
            events.append({
                'timestamp': ts,
                'event_type': 'meal',
                'carbs': carbs,
                'insulin': insulin,
                'food_type': tx.get('foodType', ''),
                'absorption_time': tx.get('absorptionTime', 180),
            })
            stats['meal'] += 1

        elif insulin >= BOLUS_THRESHOLD and carbs < MEAL_CARB_THRESHOLD:
            events.append({
                'timestamp': ts,
                'event_type': 'correction_bolus',
                'insulin': insulin,
            })
            stats['correction_bolus'] += 1

        # Richer override extraction
        elif et in ('Temporary Override', 'Override'):
            reason = tx.get('reason', tx.get('notes', ''))
            category = classify_override_reason(reason)
            duration = float(tx.get('duration') or tx.get('durationInMilliseconds', 0) / 60000 or 0)
            scale = float(tx.get('insulinNeedsScaleFactor', 1.0))

            events.append({
                'timestamp': ts,
                'event_type': category,
                'duration_min': duration,
                'insulin_needs_scale': scale,
                'reason_raw': reason,
            })
            stats[category] += 1

    # --- Mine devicestatus.json for Loop overrides ---
    if devicestatus_path and os.path.exists(devicestatus_path):
        with open(devicestatus_path) as f:
            statuses = json.load(f)

        seen_ts = set()
        for ds in statuses:
            override = (ds.get('override') or
                        ds.get('overrideStatus') or
                        (ds.get('loop', {}) or {}).get('override'))
            if not override or not override.get('active', False):
                continue

            ts_str = ds.get('created_at') or ds.get('timestamp')
            if not ts_str:
                continue
            ts = pd.Timestamp(ts_str).round(f'{GRID_INTERVAL_MIN}min')

            # Deduplicate: only first entry per 5-min slot
            ts_key = str(ts)
            if ts_key in seen_ts:
                continue
            seen_ts.add(ts_key)

            name = override.get('name', override.get('reason', ''))
            category = classify_override_reason(name)
            duration = float(override.get('duration', 0))
            scale = float(override.get('insulinNeedsScaleFactor',
                                       override.get('currentCorrectionRange', {}).get('override', 1.0)))

            events.append({
                'timestamp': ts,
                'event_type': category,
                'duration_min': duration,
                'insulin_needs_scale': scale,
                'reason_raw': name,
                'source': 'devicestatus',
            })
            stats[f'ds_{category}'] += 1

    # Sort by timestamp
    events.sort(key=lambda e: e['timestamp'])
    return events, dict(stats)


def build_pre_event_windows(grid_df, events, window_steps=12,
                            lead_steps=None, neg_ratio=3):
    """Build labeled windows BEFORE events for prospective prediction.

    Unlike build_feature_windows (which places the window ending AT the event),
    this creates windows ending lead_steps BEFORE the event. This trains the
    classifier to recognize "what does glucose look like 30 min before a meal?"

    Args:
        grid_df: DataFrame with 5-min grid
        events: list of event dicts (from extract_override_events)
        window_steps: lookback window size (5-min steps, default 12 = 1hr)
        lead_steps: list of lead times in 5-min steps (default: [3,6,9,12])
        neg_ratio: negative:positive sampling ratio (default 3)

    Returns:
        features: (N, window_steps, n_features) array
        labels: (N,) array with EXTENDED_LABEL_MAP values
        metadata: list of dicts with event info + lead_time_min
    """
    if lead_steps is None:
        lead_steps = LEAD_TIME_STEPS

    feature_cols = ['glucose', 'iob', 'cob', 'net_basal', 'bolus',
                    'carbs', 'time_sin', 'time_cos']
    scales = [NORMALIZATION_SCALES.get(c, 1.0) for c in feature_cols]

    if not isinstance(grid_df.index, pd.DatetimeIndex):
        grid_df.index = pd.to_datetime(grid_df.index)
    grid_df = grid_df.sort_index()

    ts_to_idx = {ts: i for i, ts in enumerate(grid_df.index)}

    pos_features = []
    pos_labels = []
    pos_meta = []
    event_zones = set()  # grid indices near events (exclusion zone for negatives)

    for ev in events:
        ts = ev['timestamp']
        event_idx = ts_to_idx.get(ts)
        if event_idx is None:
            diffs = np.abs((grid_df.index - ts).total_seconds())
            nearest = int(np.argmin(diffs))
            if diffs[nearest] <= GRID_INTERVAL_MIN * 60:
                event_idx = nearest
            else:
                continue

        label = EXTENDED_LABEL_MAP.get(ev['event_type'], 0)
        if label == 0:
            continue

        # Mark exclusion zone around event
        for offset in range(-max(lead_steps) - window_steps,
                            max(lead_steps) + window_steps + 1):
            event_zones.add(event_idx + offset)

        # Create windows at each lead time
        for lead in lead_steps:
            # Window ends `lead` steps BEFORE the event
            end_idx = event_idx - lead
            start_idx = end_idx - window_steps

            if start_idx < 0 or end_idx > len(grid_df):
                continue

            window_data = grid_df.iloc[start_idx:end_idx][feature_cols].values
            window_norm = window_data / np.array(scales)

            glucose_col = window_norm[:, 0]
            if np.any(np.isnan(glucose_col)) or np.any(glucose_col <= 0):
                continue

            pos_features.append(window_norm)
            pos_labels.append(label)
            pos_meta.append({
                'event_type': ev['event_type'],
                'timestamp': str(ts),
                'lead_time_min': lead * GRID_INTERVAL_MIN,
                'lead_steps': lead,
                'carbs': ev.get('carbs', 0),
                'insulin': ev.get('insulin', 0),
                'duration_min': ev.get('duration_min', 0),
                'insulin_needs_scale': ev.get('insulin_needs_scale', 1.0),
            })

    # Negative windows: no event within exclusion zone
    neg_features = []
    neg_labels = []
    neg_meta = []

    n_neg_target = len(pos_features) * neg_ratio
    rng = np.random.RandomState(42)
    candidates = [i for i in range(window_steps, len(grid_df))
                  if i not in event_zones]

    if candidates:
        chosen = rng.choice(candidates,
                            size=min(n_neg_target, len(candidates)),
                            replace=False)
        for idx in chosen:
            start = idx - window_steps
            window_data = grid_df.iloc[start:idx][feature_cols].values
            window_norm = window_data / np.array(scales)
            glucose_col = window_norm[:, 0]
            if np.any(np.isnan(glucose_col)) or np.any(glucose_col <= 0):
                continue
            neg_features.append(window_norm)
            neg_labels.append(0)
            neg_meta.append({
                'event_type': 'none',
                'timestamp': str(grid_df.index[idx]),
                'lead_time_min': 0,
                'lead_steps': 0,
            })

    all_features = pos_features + neg_features
    all_labels = pos_labels + neg_labels
    all_meta = pos_meta + neg_meta

    if not all_features:
        return np.array([]), np.array([]), []

    return np.stack(all_features), np.array(all_labels), all_meta


def extract_extended_tabular(windows, labels, metadata):
    """Extract tabular features including lead-time and override context.

    Extends extract_tabular_features with:
    - lead_time_min as a feature (enables lead-time-aware scoring)
    - glucose acceleration (2nd derivative)
    - IOB velocity
    - COB velocity

    Returns: (N, n_features) array, feature_names list
    """
    base_tabular, base_names = extract_tabular_features(windows)

    N = base_tabular.shape[0]
    extra = np.zeros((N, 4))

    for i in range(N):
        w = windows[i]
        # Lead time
        extra[i, 0] = metadata[i].get('lead_time_min', 0) / 60.0  # hours

        # Glucose acceleration (2nd derivative)
        glucose = w[:, 0] * NORMALIZATION_SCALES['glucose']
        if len(glucose) >= 3:
            roc = np.diff(glucose)
            accel = np.diff(roc)
            extra[i, 1] = float(np.mean(accel))
        # IOB velocity
        iob = w[:, 1] * NORMALIZATION_SCALES['iob']
        if len(iob) >= 2:
            extra[i, 2] = float(iob[-1] - iob[-2])
        # COB velocity
        cob = w[:, 2] * NORMALIZATION_SCALES.get('cob', 1.0)
        if len(cob) >= 2:
            extra[i, 3] = float(cob[-1] - cob[-2])

    extended_names = base_names + [
        'lead_time_hr', 'glucose_accel', 'iob_velocity', 'cob_velocity',
    ]
    return np.hstack([base_tabular, extra]), extended_names


def compute_rolling_features(grid_df, windows_1hr=12, windows_3hr=36, windows_6hr=72):
    """Compute rolling temporal features from the full grid.

    Adds rolling statistics at multiple horizons for each grid point:
    - 1hr, 3hr, 6hr glucose: mean, std, min, max, range
    - 1hr, 3hr IOB: mean, max
    - 1hr, 3hr COB: mean, max

    Args:
        grid_df: DataFrame with glucose, iob, cob columns and DatetimeIndex

    Returns:
        DataFrame with rolling feature columns appended
    """
    df = grid_df.copy()
    glucose = df['glucose'] if 'glucose' in df.columns else df.iloc[:, 0]

    for label, steps in [('1hr', windows_1hr), ('3hr', windows_3hr), ('6hr', windows_6hr)]:
        roll = glucose.rolling(steps, min_periods=1)
        df[f'glucose_mean_{label}'] = roll.mean()
        df[f'glucose_std_{label}'] = roll.std().fillna(0)
        df[f'glucose_min_{label}'] = roll.min()
        df[f'glucose_max_{label}'] = roll.max()
        df[f'glucose_range_{label}'] = df[f'glucose_max_{label}'] - df[f'glucose_min_{label}']

    # IOB/COB rolling
    if 'iob' in df.columns:
        for label, steps in [('1hr', windows_1hr), ('3hr', windows_3hr)]:
            df[f'iob_mean_{label}'] = df['iob'].rolling(steps, min_periods=1).mean()
            df[f'iob_max_{label}'] = df['iob'].rolling(steps, min_periods=1).max()
    if 'cob' in df.columns:
        for label, steps in [('1hr', windows_1hr), ('3hr', windows_3hr)]:
            df[f'cob_mean_{label}'] = df['cob'].rolling(steps, min_periods=1).mean()
            df[f'cob_max_{label}'] = df['cob'].rolling(steps, min_periods=1).max()

    return df


def build_classifier_dataset(patients_dir, window_steps=12, lead_steps=None):
    """End-to-end pipeline: patient data → XGBoost-ready tabular dataset.

    Chains: extract_override_events → build_pre_event_windows →
    extract_extended_tabular → optional rolling features.

    Args:
        patients_dir: path to patient directory with subdirs
        window_steps: lookback window (5-min steps)
        lead_steps: lead times for pre-event windows

    Returns:
        dict with tabular features, labels, feature names, metadata
    """
    patients_dir = Path(patients_dir)
    patient_dirs = sorted(
        d / 'training' for d in patients_dir.iterdir()
        if d.is_dir() and (d / 'training').is_dir()
    )

    all_tabular = []
    all_labels = []
    all_meta = []
    patient_stats = {}

    for pd_path in patient_dirs:
        patient_name = pd_path.parent.name
        tx_path = pd_path / 'treatments.json'
        ds_path = pd_path / 'devicestatus.json'

        if not tx_path.exists():
            continue

        # Extract events
        events, stats = extract_override_events(
            str(tx_path),
            str(ds_path) if ds_path.exists() else None
        )
        if not events:
            continue

        # Build grid
        grid_df, _ = build_nightscout_grid(str(pd_path))
        if grid_df is None:
            continue

        # Add time encoding
        hours = grid_df.index.hour + grid_df.index.minute / 60.0
        grid_df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
        grid_df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)

        # Build pre-event windows
        features, labels, meta = build_pre_event_windows(
            grid_df, events, window_steps=window_steps, lead_steps=lead_steps
        )
        if len(features) == 0:
            continue

        # Extract extended tabular
        tabular, tab_names = extract_extended_tabular(features, labels, meta)

        for m in meta:
            m['patient'] = patient_name
        all_tabular.append(tabular)
        all_labels.append(labels)
        all_meta.extend(meta)
        patient_stats[patient_name] = {
            'n_events': len(events),
            'n_windows': len(labels),
            'n_positive': int(np.sum(labels > 0)),
            'stats': stats,
        }

    if not all_tabular:
        return None

    return {
        'tabular': np.concatenate(all_tabular),
        'labels': np.concatenate(all_labels),
        'feature_names': tab_names,
        'metadata': all_meta,
        'patient_stats': patient_stats,
        'label_map': EXTENDED_LABEL_MAP,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Mine event labels from Nightscout treatment logs')
    parser.add_argument('--patients-dir', required=True,
                        help='Directory containing patient subdirs')
    parser.add_argument('--output', default='externals/experiments/event_labels.json',
                        help='Output file path')
    parser.add_argument('--window', type=int, default=12,
                        help='Feature window size in 5-min steps (default: 12 = 1hr)')
    args = parser.parse_args()

    print('=' * 60)
    print('EXP-023: Mining Event Labels from Nightscout')
    print('=' * 60)

    result = mine_all_patients(args.patients_dir, args.window)

    if result is None:
        print('ERROR: No valid patient data found')
        return

    print(f'\n=== Summary ===')
    print(f'  Patients: {result["n_patients"]}')
    print(f'  Total windows: {len(result["labels"])}')
    print(f'  Event distribution: {result["total_event_counts"]}')
    print(f'  Positive rate: {np.mean(result["labels"] > 0):.1%}')

    # Save results (without numpy arrays — save those as .npz)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save tabular features as npz
    npz_path = output_path.with_suffix('.npz')
    np.savez_compressed(str(npz_path),
                        tabular=result['tabular'],
                        labels=result['labels'])
    print(f'  Features → {npz_path}')

    # Save metadata as JSON
    summary = {
        'experiment': 'EXP-023',
        'n_patients': result['n_patients'],
        'n_windows': len(result['labels']),
        'n_positive': int(np.sum(result['labels'] > 0)),
        'n_negative': int(np.sum(result['labels'] == 0)),
        'total_event_counts': result['total_event_counts'],
        'patient_summaries': result['patient_summaries'],
        'tabular_feature_names': result['tabular_names'],
        'label_map': {'none': 0, 'meal': 1, 'correction_bolus': 2, 'override': 3},
        'features_file': str(npz_path),
    }

    with open(str(output_path), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'  Summary → {output_path}')


if __name__ == '__main__':
    main()
