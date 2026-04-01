"""
real_data_adapter.py — Bridge from real CGM datasets to cgmencode training pipeline.

Converts tabular CGM data (Nightscout, OhioT1DM, Tidepool, etc.) into the
8-feature (glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos)
tensor format used by cgmencode models.

Supports three input modes:
  1. Nightscout JSON directory (entries.json + treatments.json + devicestatus.json + profile.json)
  2. GluPredKit parser output (DataFrame with CGM, bolus, basal, carbs columns)
  3. Raw CSV/DataFrame with configurable column mapping

Usage:
    # From Nightscout JSON directory (preferred — has pre-computed IOB/COB):
    python3 -m tools.cgmencode.real_data_adapter --source nightscout \
        --data-path /path/to/ns-fixtures/90-day-history

    # From OhioT1DM via GluPredKit parser:
    python3 -m tools.cgmencode.real_data_adapter --source ohio --data-path /path/to/OhioT1DM --subject 559 --year 2020

    # From any CSV with glucose, insulin, carbs columns:
    python3 -m tools.cgmencode.real_data_adapter --csv /path/to/data.csv

    # Verify adapter with synthetic test data:
    python3 -m tools.cgmencode.real_data_adapter --test
"""

import argparse
import json
import sys
import os
import numpy as np
import pandas as pd
import torch
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from .encoder import CGMDataset, ConditionedDataset
from .schema import NORMALIZATION_SCALES, GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX


# Normalization constants from canonical schema
SCALE = NORMALIZATION_SCALES

# Default DIA for IOB approximation (hours)
DEFAULT_DIA = 5.0
# Default carb absorption time (hours)
DEFAULT_CARB_ABS = 3.0


def approximate_iob(bolus_series: pd.Series, dia_hours: float = DEFAULT_DIA,
                     interval_min: int = 5) -> pd.Series:
    """
    Approximate Insulin-on-Board from bolus history using exponential decay.

    Uses a simple exponential model: IOB(t) = sum of dose_i * exp(-k * (t - t_i))
    where k = ln(2) / (DIA/2) gives ~0 at DIA hours.
    """
    dia_steps = int(dia_hours * 60 / interval_min)
    half_life_steps = dia_steps // 2
    k = np.log(2) / max(half_life_steps, 1)

    iob = np.zeros(len(bolus_series))
    bolus_vals = bolus_series.fillna(0).values

    for i in range(len(bolus_vals)):
        if bolus_vals[i] > 0:
            for j in range(i, min(i + dia_steps, len(iob))):
                iob[j] += bolus_vals[i] * np.exp(-k * (j - i))

    return pd.Series(iob, index=bolus_series.index)


def approximate_cob(carbs_series: pd.Series, abs_hours: float = DEFAULT_CARB_ABS,
                     interval_min: int = 5) -> pd.Series:
    """
    Approximate Carbs-on-Board from carb intake history using linear decay.

    Carbs absorb linearly over abs_hours, so COB(t) = carbs * max(0, 1 - t/abs_time).
    """
    abs_steps = int(abs_hours * 60 / interval_min)

    cob = np.zeros(len(carbs_series))
    carbs_vals = carbs_series.fillna(0).values

    for i in range(len(carbs_vals)):
        if carbs_vals[i] > 0:
            for j in range(i, min(i + abs_steps, len(cob))):
                fraction_remaining = 1.0 - (j - i) / abs_steps
                cob[j] += carbs_vals[i] * fraction_remaining

    return pd.Series(cob, index=carbs_series.index)


def dataframe_to_features(df: pd.DataFrame,
                           glucose_col: str = 'CGM',
                           bolus_col: str = 'bolus',
                           basal_col: str = 'basal',
                           carbs_col: str = 'carbs',
                           dia_hours: float = DEFAULT_DIA,
                           carb_abs_hours: float = DEFAULT_CARB_ABS,
                           scheduled_basal: float = None,
                           interval_min: int = 5) -> np.ndarray:
    """
    Convert a DataFrame of CGM data into (N, 8) normalized feature array.

    Parameters:
        df: DataFrame with DateTimeIndex at regular intervals
        glucose_col: Column name for glucose readings (mg/dL)
        bolus_col: Column name for bolus doses (U)
        basal_col: Column name for basal rate (U/hr or U per interval)
        carbs_col: Column name for carb intake (g)
        dia_hours: Duration of insulin action for IOB approximation
        carb_abs_hours: Carb absorption time for COB approximation
        scheduled_basal: If provided, net_basal = actual - scheduled. If None, uses median.
        interval_min: Time interval in minutes (default 5)

    Returns:
        (N, 8) numpy array with normalized features
    """
    # Extract columns, filling NaN with 0 for treatments
    glucose = df[glucose_col].interpolate(limit=6).values  # interpolate gaps up to 30min
    bolus = df[bolus_col].fillna(0).values if bolus_col in df.columns else np.zeros(len(df))
    basal = df[basal_col].ffill().values if basal_col in df.columns else np.zeros(len(df))
    carbs = df[carbs_col].fillna(0).values if carbs_col in df.columns else np.zeros(len(df))

    # Compute derived features
    iob = approximate_iob(pd.Series(bolus), dia_hours, interval_min).values
    cob = approximate_cob(pd.Series(carbs), carb_abs_hours, interval_min).values

    # Net basal: deviation from scheduled rate
    # OhioT1DM basal is in U per 5-min interval (already divided by 12)
    # Convert to U/hr for consistency
    basal_uhr = basal * (60 / interval_min) if basal.max() < 1.0 else basal
    if scheduled_basal is None:
        scheduled_basal = np.median(basal_uhr[basal_uhr > 0]) if np.any(basal_uhr > 0) else 0
    net_basal = basal_uhr - scheduled_basal

    # Circadian encoding from timestamps
    if hasattr(df.index, 'hour'):
        hours = df.index.hour + df.index.minute / 60.0
    else:
        hours = np.zeros(len(df))
    time_sin = np.sin(2 * np.pi * hours / 24.0)
    time_cos = np.cos(2 * np.pi * hours / 24.0)

    # Stack and normalize
    features = np.column_stack([
        glucose / SCALE['glucose'],
        iob / SCALE['iob'],
        cob / SCALE['cob'],
        net_basal / SCALE['net_basal'],
        bolus / SCALE['bolus'],
        carbs / SCALE['carbs'],
        time_sin,
        time_cos,
    ])

    return features.astype(np.float32)


def split_into_windows(features: np.ndarray, window_size: int = 24,
                        min_valid_fraction: float = 0.8) -> List[np.ndarray]:
    """
    Split feature array into overlapping windows, skipping windows with too many NaN glucose values.

    Parameters:
        features: (N, 8) array
        window_size: Window length in time steps
        min_valid_fraction: Minimum fraction of non-NaN glucose values per window

    Returns:
        List of (window_size, 8) arrays
    """
    windows = []
    stride = window_size // 2  # 50% overlap

    for start in range(0, len(features) - window_size + 1, stride):
        window = features[start:start + window_size]
        # Check glucose channel (0) for NaN
        glucose_valid = np.sum(~np.isnan(window[:, 0]))
        if glucose_valid / window_size >= min_valid_fraction:
            # Fill any remaining NaN with interpolation
            for col in range(window.shape[1]):
                mask = np.isnan(window[:, col])
                if mask.any():
                    valid = ~mask
                    if valid.sum() >= 2:
                        window[mask, col] = np.interp(
                            np.where(mask)[0], np.where(valid)[0], window[valid, col])
                    else:
                        window[mask, col] = 0.0
            windows.append(window)

    return windows


def load_nightscout_grid_timestamps(data_path: str) -> np.ndarray:
    """Return the 5-min grid timestamps (epoch ms) for Nightscout data.

    Matches the grid used by load_nightscout_to_dataset, so array index i
    corresponds to feature matrix row i.
    """
    data_dir = Path(data_path)
    with open(data_dir / 'entries.json') as f:
        entries = json.load(f)
    times = []
    for e in entries:
        if e.get('type') != 'sgv' or 'sgv' not in e:
            continue
        if 'date' in e:
            times.append(pd.Timestamp(e['date'], unit='ms', tz='UTC'))
        elif 'dateString' in e:
            times.append(pd.Timestamp(e['dateString']))
    if not times:
        return np.array([], dtype=np.int64)
    times.sort()
    grid_start = min(times).floor('5min')
    grid_end = max(times).ceil('5min')
    grid = pd.date_range(grid_start, grid_end, freq='5min')
    return np.array([int(t.timestamp() * 1000) for t in grid], dtype=np.int64)


def build_nightscout_grid(data_path: str,
                          verbose: bool = True,
                          ) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray]]:
    """
    Build 5-min feature grid from Nightscout JSON directory.

    Returns the intermediate grid before windowing — useful for hindcast
    and other tools that need random access to the time series.

    Expects: entries.json, treatments.json, devicestatus.json, profile.json

    Returns:
        (df, features) where:
        - df: DataFrame with DateTimeIndex (5-min grid) and columns:
              glucose, iob, cob, bolus, carbs, net_basal (raw units)
        - features: (N, 8) normalized float32 array matching cgmencode schema
        Returns (None, None) on error.
    """
    data_dir = Path(data_path)
    required = ['entries.json', 'treatments.json', 'devicestatus.json', 'profile.json']
    for f in required:
        if not (data_dir / f).exists():
            if verbose:
                print(f"ERROR: Missing {f} in {data_path}")
            return None, None

    if verbose:
        print(f"=== Loading Nightscout data from {data_path} ===")

    # --- 1. Build 5-min grid from entries (CGM readings) ---
    with open(data_dir / 'entries.json') as f:
        entries = json.load(f)

    cgm_times = []
    cgm_values = []
    for e in entries:
        if e.get('type') != 'sgv' or 'sgv' not in e:
            continue
        if 'date' in e:
            ts = pd.Timestamp(e['date'], unit='ms', tz='UTC')
        elif 'dateString' in e:
            ts = pd.Timestamp(e['dateString'])
        else:
            continue
        cgm_times.append(ts)
        cgm_values.append(float(e['sgv']))

    cgm_df = pd.DataFrame({'glucose': cgm_values}, index=pd.DatetimeIndex(cgm_times))
    cgm_df = cgm_df.sort_index()
    cgm_df = cgm_df[~cgm_df.index.duplicated(keep='first')]

    grid_start = cgm_df.index.min().floor('5min')
    grid_end = cgm_df.index.max().ceil('5min')
    grid = pd.date_range(grid_start, grid_end, freq='5min')
    df = pd.DataFrame(index=grid)

    cgm_df.index = cgm_df.index.round('5min')
    cgm_grouped = cgm_df.groupby(level=0).mean()
    df['glucose'] = cgm_grouped['glucose']
    df['glucose'] = df['glucose'].interpolate(limit=6)

    if verbose:
        print(f"  CGM: {len(entries)} raw → {df['glucose'].notna().sum()}/{len(df)} grid points "
              f"({grid_start.strftime('%Y-%m-%d')} to {grid_end.strftime('%Y-%m-%d')})")

    # --- 2. Extract IOB/COB from devicestatus ---
    with open(data_dir / 'devicestatus.json') as f:
        devicestatus = json.load(f)

    ds_times = []
    ds_iob = []
    ds_cob = []
    for ds in devicestatus:
        loop = ds.get('loop', {})
        iob_data = loop.get('iob', {})
        cob_data = loop.get('cob', {})
        if not iob_data or 'iob' not in iob_data:
            continue
        ts = pd.Timestamp(ds.get('created_at'))
        ds_times.append(ts)
        ds_iob.append(float(iob_data['iob']))
        ds_cob.append(float(cob_data.get('cob', 0)))

    ds_df = pd.DataFrame({'iob': ds_iob, 'cob': ds_cob},
                          index=pd.DatetimeIndex(ds_times))
    ds_df = ds_df.sort_index()
    ds_df = ds_df[~ds_df.index.duplicated(keep='first')]
    ds_df.index = ds_df.index.round('5min')
    ds_grouped = ds_df.groupby(level=0).mean()
    df['iob'] = ds_grouped['iob']
    df['cob'] = ds_grouped['cob']
    df['iob'] = df['iob'].interpolate(limit=6).fillna(0)
    df['cob'] = df['cob'].interpolate(limit=6).fillna(0)

    if verbose:
        print(f"  DeviceStatus: {len(devicestatus)} raw → {ds_df.shape[0]} with IOB/COB")

    # --- 3. Parse treatments → bolus, carbs, temp basal ---
    with open(data_dir / 'treatments.json') as f:
        treatments = json.load(f)

    df['bolus'] = 0.0
    df['carbs'] = 0.0
    df['temp_rate'] = np.nan

    bolus_count = 0
    carb_count = 0
    temp_count = 0
    for tx in treatments:
        et = tx.get('eventType', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str).round('5min')
        if ts not in df.index:
            continue

        if 'Bolus' in et and (tx.get('insulin') or 0) > 0:
            df.loc[ts, 'bolus'] += float(tx['insulin'])
            bolus_count += 1
        if (tx.get('carbs') or 0) > 0:
            df.loc[ts, 'carbs'] += float(tx['carbs'])
            carb_count += 1
        if et == 'Temp Basal' and 'rate' in tx:
            rate = float(tx['rate'])
            dur_min = float(tx.get('duration', 5))
            n_slots = max(1, int(dur_min / 5))
            slot_idx = df.index.get_loc(ts)
            if isinstance(slot_idx, int):
                end_idx = min(slot_idx + n_slots, len(df))
                df.iloc[slot_idx:end_idx, df.columns.get_loc('temp_rate')] = rate
            temp_count += 1

    if verbose:
        print(f"  Treatments: {bolus_count} bolus, {carb_count} carbs, {temp_count} temp basals")

    # --- 4. Compute net_basal ---
    with open(data_dir / 'profile.json') as f:
        profiles = json.load(f)

    if isinstance(profiles, list) and profiles:
        store = profiles[0].get('store', {})
    else:
        store = profiles.get('store', {})
    default_profile = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}
    basal_schedule = default_profile.get('basal', [])

    scheduled = np.zeros(len(df))
    for i, ts in enumerate(df.index):
        sec_of_day = ts.hour * 3600 + ts.minute * 60 + ts.second
        rate = basal_schedule[0]['value'] if basal_schedule else 0
        for entry in basal_schedule:
            if entry.get('timeAsSeconds', 0) <= sec_of_day:
                rate = entry['value']
        scheduled[i] = rate

    df['temp_rate'] = df['temp_rate'].ffill()
    df['temp_rate'] = df['temp_rate'].fillna(pd.Series(scheduled, index=df.index))
    df['net_basal'] = df['temp_rate'].values - scheduled

    if verbose and basal_schedule:
        print(f"  Profile: {len(basal_schedule)} basal segments, "
              f"scheduled range [{min(e['value'] for e in basal_schedule):.1f}, "
              f"{max(e['value'] for e in basal_schedule):.1f}] U/hr")

    # --- 5. Build 8-feature array ---
    hours = df.index.hour + df.index.minute / 60.0
    time_sin = np.sin(2 * np.pi * hours / 24.0)
    time_cos = np.cos(2 * np.pi * hours / 24.0)

    features = np.column_stack([
        df['glucose'].values / SCALE['glucose'],
        df['iob'].values / SCALE['iob'],
        df['cob'].values / SCALE['cob'],
        df['net_basal'].values / SCALE['net_basal'],
        df['bolus'].values / SCALE['bolus'],
        df['carbs'].values / SCALE['carbs'],
        time_sin,
        time_cos,
    ]).astype(np.float32)

    if verbose:
        print(f"  Feature matrix: {features.shape}")
        print(f"  Glucose: [{df['glucose'].min():.0f}, {df['glucose'].max():.0f}] mg/dL")
        print(f"  IOB: [{df['iob'].min():.2f}, {df['iob'].max():.2f}] U")

    return df, features


def load_nightscout_to_dataset(data_path: str,
                                task: str = 'forecast',
                                window_size: int = 24,
                                val_fraction: float = 0.2,
                                conditioned: bool = False,
                                ) -> Tuple[Optional[object], Optional[object]]:
    """
    Load Nightscout JSON directory → cgmencode datasets.

    Expects a directory with:
      - entries.json: CGM readings (sgv field, ms timestamp)
      - treatments.json: Bolus, carbs, temp basal events
      - devicestatus.json: Loop IOB/COB (pre-computed by controller)
      - profile.json: Scheduled basal rates

    The key advantage over OhioT1DM: devicestatus has Loop's pre-computed IOB/COB,
    so we use actual controller state rather than exponential decay approximations.

    Returns:
        (train_dataset, val_dataset)
    """
    df, features = build_nightscout_grid(data_path, verbose=True)
    if df is None:
        return None, None

    # --- Window and split ---
    # For conditioned model: windows must be 2x window_size (history + future)
    actual_window = window_size * 2 if conditioned else window_size
    windows = split_into_windows(features, window_size=actual_window)
    if not windows:
        print("  WARNING: No valid windows extracted.")
        return None, None

    # Train/val split (chronological)
    split_idx = int(len(windows) * (1 - val_fraction))
    train_windows = windows[:split_idx]
    val_windows = windows[split_idx:]

    train_tensor = torch.tensor(np.array(train_windows), dtype=torch.float32)
    val_tensor = torch.tensor(np.array(val_windows), dtype=torch.float32)

    if conditioned:
        # ConditionedDataset splits at window_size: [:window_size] = history, [window_size:] = future
        train_ds = ConditionedDataset(train_tensor, window_size=window_size)
        val_ds = ConditionedDataset(val_tensor, window_size=window_size)
    else:
        train_ds = CGMDataset(train_tensor, task=task, window_size=window_size)
        val_ds = CGMDataset(val_tensor, task=task, window_size=window_size)

    print(f"  Windows: {len(windows)} total → {len(train_windows)} train, {len(val_windows)} val")

    return train_ds, val_ds


def load_multipatient_nightscout(data_paths: List[str],
                                  task: str = 'forecast',
                                  window_size: int = 24,
                                  val_fraction: float = 0.2,
                                  conditioned: bool = False,
                                  ) -> Tuple[Optional[object], Optional[object]]:
    """
    Load multiple patient Nightscout directories → single combined dataset.

    Each path should point to a patient's training/ directory containing
    entries.json, treatments.json, devicestatus.json, profile.json.

    Windows from each patient are extracted independently, then concatenated
    and shuffled. The val split is random (not chronological) since windows
    come from different patients with different time ranges.

    Returns:
        (train_dataset, val_dataset)
    """
    all_windows = []
    actual_window = window_size * 2 if conditioned else window_size

    for i, data_path in enumerate(data_paths):
        patient_id = Path(data_path).parent.name  # e.g. 'a', 'b', ...
        print(f"  Patient {patient_id} ({i+1}/{len(data_paths)}): {data_path}")

        df, features = build_nightscout_grid(data_path, verbose=False)
        if df is None:
            print(f"    SKIP: no valid data")
            continue

        windows = split_into_windows(features, window_size=actual_window)
        if not windows:
            print(f"    SKIP: no valid windows")
            continue

        print(f"    {len(df)} rows → {len(windows)} windows "
              f"({df['glucose'].min():.0f}-{df['glucose'].max():.0f} mg/dL)")
        all_windows.extend(windows)

    if not all_windows:
        print("  ERROR: no valid windows from any patient")
        return None, None

    # Shuffle to mix patients (prevents batch-level patient bias)
    rng = np.random.RandomState(42)
    rng.shuffle(all_windows)

    split_idx = int(len(all_windows) * (1 - val_fraction))
    train_windows = all_windows[:split_idx]
    val_windows = all_windows[split_idx:]

    train_tensor = torch.tensor(np.array(train_windows), dtype=torch.float32)
    val_tensor = torch.tensor(np.array(val_windows), dtype=torch.float32)

    if conditioned:
        train_ds = ConditionedDataset(train_tensor, window_size=window_size)
        val_ds = ConditionedDataset(val_tensor, window_size=window_size)
    else:
        train_ds = CGMDataset(train_tensor, task=task, window_size=window_size)
        val_ds = CGMDataset(val_tensor, task=task, window_size=window_size)

    print(f"  Multi-patient total: {len(all_windows)} windows from "
          f"{len(data_paths)} patients → {len(train_windows)} train, "
          f"{len(val_windows)} val")

    return train_ds, val_ds


def load_ohio_to_dataset(data_path: str, subject_id: str, year: str = '2020',
                          task: str = 'forecast', window_size: int = 24,
                          val_fraction: float = 0.2,
                          conditioned: bool = False,
                          ) -> Tuple[Optional[object], Optional[object]]:
    """
    Load OhioT1DM data via GluPredKit parser → cgmencode datasets.

    Parameters:
        data_path: Path to directory containing OhioT1DM/ folder
        subject_id: Patient ID (e.g., '559', '570')
        year: Dataset year ('2018' or '2020')
        task: CGMDataset task ('forecast', 'fill_readings', etc.)
        window_size: Window size in 5-min steps
        val_fraction: Fraction of windows held out for validation
        conditioned: If True, return ConditionedDataset instead

    Returns:
        (train_dataset, val_dataset)
    """
    # Import GluPredKit parser
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'GluPredKit'))
    try:
        from glupredkit.parsers.ohio_t1dm import Parser
    except ImportError:
        print("ERROR: GluPredKit not found. Run: make bootstrap")
        return None, None

    parser = Parser()
    try:
        df = parser(data_path, subject_id, year)
    except (FileNotFoundError, Exception) as e:
        print(f"ERROR loading OhioT1DM subject {subject_id}: {e}")
        return None, None

    print(f"  Loaded subject {subject_id}: {len(df)} rows ({len(df)*5/60:.0f} hours)")

    return _dataframe_to_datasets(df, task, window_size, val_fraction, conditioned)


def load_csv_to_dataset(csv_path: str, column_map: Dict[str, str] = None,
                         task: str = 'forecast', window_size: int = 24,
                         val_fraction: float = 0.2,
                         conditioned: bool = False,
                         ) -> Tuple[Optional[object], Optional[object]]:
    """
    Load any CSV with glucose/insulin/carb columns → cgmencode datasets.

    Parameters:
        csv_path: Path to CSV file
        column_map: Dict mapping canonical names to CSV column names:
                    {'glucose': 'bg', 'bolus': 'bolus_dose', ...}
        task: CGMDataset task
        window_size: Window size in 5-min steps
        val_fraction: Fraction held out for validation
        conditioned: If True, return ConditionedDataset

    Returns:
        (train_dataset, val_dataset)
    """
    df = pd.read_csv(csv_path, parse_dates=[0], index_col=0)

    # Apply column mapping
    if column_map:
        reverse_map = {v: k for k, v in column_map.items()}
        df = df.rename(columns=reverse_map)

    # Standardize column names
    col_mapping = {
        'glucose': 'CGM', 'bg': 'CGM', 'sgv': 'CGM', 'blood_glucose': 'CGM',
    }
    df = df.rename(columns={k: v for k, v in col_mapping.items() if k in df.columns})

    print(f"  Loaded CSV: {len(df)} rows, columns: {list(df.columns)}")

    return _dataframe_to_datasets(df, task, window_size, val_fraction, conditioned,
                                   glucose_col='CGM')


def _dataframe_to_datasets(df: pd.DataFrame, task: str, window_size: int,
                             val_fraction: float, conditioned: bool,
                             glucose_col: str = 'CGM',
                             bolus_col: str = 'bolus',
                             basal_col: str = 'basal',
                             carbs_col: str = 'carbs',
                             ) -> Tuple[Optional[object], Optional[object]]:
    """Convert DataFrame → feature windows → train/val datasets."""

    features = dataframe_to_features(
        df, glucose_col=glucose_col, bolus_col=bolus_col,
        basal_col=basal_col, carbs_col=carbs_col,
    )

    windows = split_into_windows(features, window_size=window_size)

    if not windows:
        print("  WARNING: No valid windows extracted.")
        return None, None

    print(f"  Extracted {len(windows)} windows of {window_size} steps ({window_size*5} min)")

    # Train/val split (chronological — last N% is validation)
    split_idx = int(len(windows) * (1 - val_fraction))
    train_windows = windows[:split_idx]
    val_windows = windows[split_idx:]

    train_tensor = torch.tensor(np.array(train_windows), dtype=torch.float32)
    val_tensor = torch.tensor(np.array(val_windows), dtype=torch.float32)

    if conditioned:
        train_ds = ConditionedDataset(train_tensor, window_size=window_size)
        val_ds = ConditionedDataset(val_tensor, window_size=window_size)
    else:
        train_ds = CGMDataset(train_tensor, task=task, window_size=window_size)
        val_ds = CGMDataset(val_tensor, task=task, window_size=window_size)

    return train_ds, val_ds


def generate_synthetic_test_data(n_hours: int = 48, interval_min: int = 5) -> pd.DataFrame:
    """
    Generate synthetic test data mimicking OhioT1DM format.
    Used to verify the adapter without needing real data.
    """
    n_steps = n_hours * 60 // interval_min
    rng = np.random.RandomState(42)

    idx = pd.date_range('2024-01-01', periods=n_steps, freq='5min')

    # Simulate a realistic glucose trace with meals
    glucose = np.full(n_steps, 120.0)
    for t in range(1, n_steps):
        glucose[t] = glucose[t-1] + rng.normal(0, 2)
    # Add meal spikes at breakfast (8am), lunch (12pm), dinner (6pm)
    for day in range(n_hours // 24 + 1):
        for meal_hour, carbs_g in [(8, 45), (12, 60), (18, 50)]:
            meal_step = day * 288 + meal_hour * 12
            if meal_step < n_steps:
                for dt in range(36):  # 3-hour rise/fall
                    t = meal_step + dt
                    if t < n_steps:
                        glucose[t] += carbs_g * 1.5 * np.exp(-0.1 * dt) * np.sin(0.15 * dt)

    glucose = np.clip(glucose, 40, 400)

    # Bolus at meal times
    bolus = np.zeros(n_steps)
    for day in range(n_hours // 24 + 1):
        for meal_hour, dose in [(8, 3.5), (12, 5.0), (18, 4.0)]:
            step = day * 288 + meal_hour * 12
            if step < n_steps:
                bolus[step] = dose

    # Carbs at meals
    carbs = np.zeros(n_steps)
    for day in range(n_hours // 24 + 1):
        for meal_hour, g in [(8, 45), (12, 60), (18, 50)]:
            step = day * 288 + meal_hour * 12
            if step < n_steps:
                carbs[step] = g

    # Steady basal (U per 5-min = U/hr / 12)
    basal = np.full(n_steps, 1.0 / 12)

    df = pd.DataFrame({
        'CGM': glucose,
        'bolus': bolus,
        'basal': basal,
        'carbs': carbs,
    }, index=idx)

    return df


def main():
    parser = argparse.ArgumentParser(description='Convert real CGM data to cgmencode format')
    parser.add_argument('--source', choices=['nightscout', 'ohio', 'csv', 'test'], default='test',
                        help='Data source type')
    parser.add_argument('--data-path', help='Path to dataset directory')
    parser.add_argument('--subject', default='559', help='Subject ID for OhioT1DM')
    parser.add_argument('--year', default='2020', help='Dataset year')
    parser.add_argument('--csv', help='Path to CSV file')
    parser.add_argument('--window', type=int, default=24, help='Window size (5-min steps)')
    parser.add_argument('--conditioned', action='store_true', help='Build ConditionedDataset')
    parser.add_argument('--test', action='store_true', help='Run with synthetic test data')
    args = parser.parse_args()

    if args.test or args.source == 'test':
        print("=== Real Data Adapter — Synthetic Test ===")
        df = generate_synthetic_test_data(n_hours=48)
        print(f"Generated {len(df)} rows of synthetic data")

        features = dataframe_to_features(df)
        print(f"Features shape: {features.shape}")
        print(f"Glucose range: [{features[:, 0].min()*400:.0f}, {features[:, 0].max()*400:.0f}] mg/dL")
        print(f"IOB range:     [{features[:, 1].min()*20:.2f}, {features[:, 1].max()*20:.2f}] U")
        print(f"COB range:     [{features[:, 2].min()*100:.1f}, {features[:, 2].max()*100:.1f}] g")

        windows = split_into_windows(features, window_size=args.window)
        print(f"Windows: {len(windows)} of size {args.window}")

        # Build datasets
        train_ds, val_ds = _dataframe_to_datasets(df, 'forecast', args.window, 0.2, False)
        print(f"Datasets: {len(train_ds)} train, {len(val_ds)} val")

        # Verify shapes
        x, y = train_ds[0]
        print(f"Sample x: {x.shape}, y: {y.shape}")
        print("\n✓ Adapter works correctly.")
        return

    if args.source == 'nightscout':
        if not args.data_path:
            print("ERROR: --data-path required for Nightscout source")
            sys.exit(1)
        train_ds, val_ds = load_nightscout_to_dataset(
            args.data_path, window_size=args.window, conditioned=args.conditioned)
        if train_ds:
            print(f"\nDatasets: {len(train_ds)} train, {len(val_ds)} val")
            x, y = train_ds[0]
            print(f"Sample x: {x.shape}, y: {y.shape}")

    elif args.source == 'ohio':
        if not args.data_path:
            print("ERROR: --data-path required for OhioT1DM")
            sys.exit(1)
        train_ds, val_ds = load_ohio_to_dataset(
            args.data_path, args.subject, args.year, window_size=args.window)
        if train_ds:
            print(f"\nDatasets: {len(train_ds)} train, {len(val_ds)} val")

    elif args.source == 'csv':
        if not args.csv:
            print("ERROR: --csv required for CSV source")
            sys.exit(1)
        train_ds, val_ds = load_csv_to_dataset(args.csv, window_size=args.window)
        if train_ds:
            print(f"\nDatasets: {len(train_ds)} train, {len(val_ds)} val")


if __name__ == '__main__':
    main()
