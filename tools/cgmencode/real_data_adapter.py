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
from .schema import (
    NORMALIZATION_SCALES, GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX,
    NUM_FEATURES_EXTENDED, OVERRIDE_TYPES, TIME_SINCE_CAP_MIN,
    FEATURE_NAMES, EXTENDED_FEATURE_NAMES,
)


# Normalization constants from canonical schema
SCALE = NORMALIZATION_SCALES

# Default DIA for IOB approximation (hours)
DEFAULT_DIA = 5.0


def _normalize_timezone(tz_str: str) -> str:
    """Normalize Nightscout timezone string to Python-compatible IANA format.

    Nightscout stores 'ETC/GMT+7' (uppercase) while Python/pandas needs 'Etc/GMT+7'.
    Note: In IANA convention, Etc/GMT+7 = UTC-7 (signs are inverted).
    """
    if not tz_str:
        return 'UTC'
    # Nightscout uses uppercase 'ETC/' prefix
    if tz_str.upper().startswith('ETC/'):
        return 'Etc/' + tz_str[4:]
    return tz_str


def _to_local_index(index: pd.DatetimeIndex, patient_tz: str) -> pd.DatetimeIndex:
    """Convert a DatetimeIndex to patient-local time for circadian features.

    Returns the index in local time. Falls back to original index on error.
    """
    try:
        if index.tz is not None:
            return index.tz_convert(patient_tz)
        else:
            return index.tz_localize('UTC').tz_convert(patient_tz)
    except Exception:
        return index
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

    # --- 3b. Extract Site Change (CAGE) and Sensor Start (SAGE) events ---
    site_change_times = []
    sensor_start_times = []
    for tx in treatments:
        et = tx.get('eventType', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        if et == 'Site Change':
            site_change_times.append(pd.Timestamp(ts_str))
        elif et == 'Sensor Start':
            sensor_start_times.append(pd.Timestamp(ts_str))

    site_change_times.sort()
    sensor_start_times.sort()

    # Compute hours since last Site Change (cannula age) for each grid point
    df['cage_hours'] = np.nan
    if site_change_times:
        sc_idx = 0
        for i, ts in enumerate(df.index):
            while sc_idx < len(site_change_times) - 1 and site_change_times[sc_idx + 1] <= ts:
                sc_idx += 1
            if site_change_times[sc_idx] <= ts:
                delta_h = (ts - site_change_times[sc_idx]).total_seconds() / 3600.0
                df.iloc[i, df.columns.get_loc('cage_hours')] = delta_h

    # Compute hours since last Sensor Start (sensor age) for each grid point
    df['sage_hours'] = np.nan
    if sensor_start_times:
        ss_idx = 0
        for i, ts in enumerate(df.index):
            while ss_idx < len(sensor_start_times) - 1 and sensor_start_times[ss_idx + 1] <= ts:
                ss_idx += 1
            if sensor_start_times[ss_idx] <= ts:
                delta_h = (ts - sensor_start_times[ss_idx]).total_seconds() / 3600.0
                df.iloc[i, df.columns.get_loc('sage_hours')] = delta_h

    # Detect sensor warmup: first 2 hours after Sensor Start
    df['sensor_warmup'] = 0.0
    for ss_ts in sensor_start_times:
        warmup_end = ss_ts + pd.Timedelta(hours=2)
        mask = (df.index >= ss_ts) & (df.index < warmup_end)
        df.loc[mask, 'sensor_warmup'] = 1.0

    if verbose:
        print(f"  CAGE: {len(site_change_times)} site changes, "
              f"SAGE: {len(sensor_start_times)} sensor starts, "
              f"warmup windows: {int(df['sensor_warmup'].sum())} steps")

    # Store raw event timestamps for downstream use
    df.attrs['site_change_times'] = site_change_times
    df.attrs['sensor_start_times'] = sensor_start_times

    # --- 4. Compute net_basal ---
    with open(data_dir / 'profile.json') as f:
        profiles = json.load(f)

    if isinstance(profiles, list) and profiles:
        store = profiles[0].get('store', {})
    else:
        store = profiles.get('store', {})
    default_profile = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}
    basal_schedule = default_profile.get('basal', [])

    # Extract patient timezone for circadian features and basal schedule
    patient_tz = _normalize_timezone(default_profile.get('timezone', ''))
    df.attrs['patient_tz'] = patient_tz
    local_index = _to_local_index(df.index, patient_tz)

    if verbose:
        tz_offset = ''
        if local_index is not df.index and len(local_index) > 0:
            offset = local_index[0].utcoffset()
            tz_offset = f" (UTC{offset})" if offset else ''
        print(f"  Patient timezone: {patient_tz}{tz_offset}")

    # Use LOCAL time for basal schedule lookup (timeAsSeconds is local midnight-relative)
    scheduled = np.zeros(len(df))
    for i, ts in enumerate(local_index):
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
    # Use LOCAL time for circadian encoding (patient's actual time-of-day)
    local_hours = local_index.hour + local_index.minute / 60.0
    time_sin = np.sin(2 * np.pi * local_hours / 24.0)
    time_cos = np.cos(2 * np.pi * local_hours / 24.0)

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


def build_extended_features(df: pd.DataFrame, features: np.ndarray,
                            treatments: list = None,
                            verbose: bool = False,
                            ) -> np.ndarray:
    """
    Extend the 8-feature grid with agentic context features (→ 19 features).

    Adds: day-of-week encoding, override state, glucose dynamics, temporal gaps,
    CAGE (cannula age), SAGE (sensor age), and sensor warmup flag.
    The first 8 columns are identical to the input features array.

    Args:
        df: DataFrame from build_nightscout_grid (DatetimeIndex, raw columns)
        features: (N, 8) normalized array from build_nightscout_grid
        treatments: Optional pre-loaded treatments list. If None, skips override
                    extraction (override channels will be zero).
        verbose: Print progress

    Returns:
        (N, 19) normalized float32 array matching EXTENDED_FEATURE_NAMES
    """
    N = len(features)
    extended = np.zeros((N, NUM_FEATURES_EXTENDED), dtype=np.float32)
    extended[:, :8] = features

    # --- Channel 8–9: Day-of-week encoding (sin/cos, period=7 days) ---
    # Use patient-local time so day-of-week reflects actual local calendar
    patient_tz = df.attrs.get('patient_tz', 'UTC')
    local_index = _to_local_index(df.index, patient_tz)
    dow = local_index.dayofweek.values.astype(np.float64)  # 0=Monday .. 6=Sunday
    extended[:, 8] = np.sin(2 * np.pi * dow / 7.0).astype(np.float32)
    extended[:, 9] = np.cos(2 * np.pi * dow / 7.0).astype(np.float32)

    # --- Channel 10–11: Override state ---
    if treatments is not None:
        _fill_override_channels(df, extended, treatments)

    # --- Channel 12: Glucose rate of change (mg/dL per 5 min) ---
    glucose_raw = df['glucose'].values
    roc = np.zeros(N, dtype=np.float32)
    roc[1:] = np.diff(glucose_raw)
    roc[0] = roc[1] if N > 1 else 0.0
    # NaN propagation: if glucose was NaN, roc is NaN → fill with 0
    roc = np.nan_to_num(roc, nan=0.0)
    extended[:, 12] = roc / NORMALIZATION_SCALES['glucose_roc']

    # --- Channel 13: Glucose acceleration (Δ rate-of-change) ---
    accel = np.zeros(N, dtype=np.float32)
    accel[1:] = np.diff(roc)
    accel = np.nan_to_num(accel, nan=0.0)
    extended[:, 13] = accel / NORMALIZATION_SCALES['glucose_accel']

    # --- Channel 14: Time since last bolus (minutes, capped at 6 hr) ---
    extended[:, 14] = _time_since_last_nonzero(
        df['bolus'].values, TIME_SINCE_CAP_MIN
    ) / NORMALIZATION_SCALES['time_since_bolus']

    # --- Channel 15: Time since last carb entry (minutes, capped at 6 hr) ---
    extended[:, 15] = _time_since_last_nonzero(
        df['carbs'].values, TIME_SINCE_CAP_MIN
    ) / NORMALIZATION_SCALES['time_since_carb']

    # --- Channel 16: Cannula age (hours since last Site Change) ---
    if 'cage_hours' in df.columns:
        cage = df['cage_hours'].fillna(NORMALIZATION_SCALES['cage_hours']).values
        extended[:, 16] = (cage / NORMALIZATION_SCALES['cage_hours']).astype(np.float32)

    # --- Channel 17: Sensor age (hours since last Sensor Start) ---
    if 'sage_hours' in df.columns:
        sage = df['sage_hours'].fillna(NORMALIZATION_SCALES['sage_hours']).values
        extended[:, 17] = (sage / NORMALIZATION_SCALES['sage_hours']).astype(np.float32)

    # --- Channel 18: Sensor warmup flag (binary, 1.0 during first 2h after Sensor Start) ---
    if 'sensor_warmup' in df.columns:
        extended[:, 18] = df['sensor_warmup'].values.astype(np.float32)

    if verbose:
        print(f"  Extended features: {extended.shape}")
        print(f"  Glucose ROC range: [{roc.min():.1f}, {roc.max():.1f}] mg/dL/5min")
        n_overrides = int(np.sum(extended[:, 10] > 0))
        print(f"  Override active steps: {n_overrides} ({100*n_overrides/max(N,1):.1f}%)")
        if 'cage_hours' in df.columns:
            cage_valid = df['cage_hours'].notna().sum()
            print(f"  CAGE coverage: {cage_valid}/{N} ({100*cage_valid/max(N,1):.1f}%)")
        if 'sage_hours' in df.columns:
            sage_valid = df['sage_hours'].notna().sum()
            warmup_steps = int(df.get('sensor_warmup', pd.Series([0])).sum())
            print(f"  SAGE coverage: {sage_valid}/{N} ({100*sage_valid/max(N,1):.1f}%), "
                  f"warmup steps: {warmup_steps}")

    return extended


def _fill_override_channels(df: pd.DataFrame, extended: np.ndarray,
                            treatments: list) -> None:
    """Populate override_active and override_type channels from treatments."""
    override_map = {
        'eating soon': 'eating_soon',
        'exercise': 'exercise',
        'sleep': 'sleep',
        'sick': 'sick',
        'pre-meal': 'eating_soon',
    }

    for tx in treatments:
        et = tx.get('eventType', '')
        if et != 'Temporary Override':
            continue
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue

        ts = pd.Timestamp(ts_str).round('5min')
        dur_min = float(tx.get('duration', 0))
        reason = (tx.get('reason') or '').lower().strip()

        # Map reason to override type
        otype = 'custom'
        for key, val in override_map.items():
            if key in reason:
                otype = val
                break

        otype_val = OVERRIDE_TYPES.get(otype, OVERRIDE_TYPES['custom'])
        n_slots = max(1, int(dur_min / 5))
        if ts in df.index:
            slot_idx = df.index.get_loc(ts)
            if isinstance(slot_idx, int):
                end_idx = min(slot_idx + n_slots, len(df))
                extended[slot_idx:end_idx, 10] = 1.0         # override_active
                extended[slot_idx:end_idx, 11] = otype_val   # override_type


def _time_since_last_nonzero(values: np.ndarray, cap_min: float,
                              interval_min: float = 5.0) -> np.ndarray:
    """Compute minutes since last non-zero value, capped at cap_min."""
    N = len(values)
    result = np.full(N, cap_min, dtype=np.float32)
    last_nonzero_idx = -1

    for i in range(N):
        if not np.isnan(values[i]) and values[i] > 0:
            last_nonzero_idx = i
        if last_nonzero_idx >= 0:
            minutes = (i - last_nonzero_idx) * interval_min
            result[i] = min(minutes, cap_min)

    return result


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


# ── Coarse-grid downsampling for multi-horizon forecasting ───────────────

# Aggregation rules per column type
_AGG_MEAN = {'glucose', 'net_basal'}
_AGG_SUM  = {'bolus', 'carbs'}
_AGG_LAST = {'iob', 'cob', 'time_sin', 'time_cos'}

# Extended features all use 'last' (point-in-time state or end-of-interval)
_EXTENDED_ONLY = set(EXTENDED_FEATURE_NAMES) - set(FEATURE_NAMES)


def downsample_grid(grid_df: pd.DataFrame,
                    target_interval_min: int = 15) -> pd.DataFrame:
    """Downsample a 5-min grid to coarser resolution for extended-horizon forecasting.

    Aggregation rules:
      - glucose: mean (smooths sensor noise)
      - iob, cob: last (point-in-time state)
      - net_basal: mean (average rate over interval)
      - bolus, carbs: sum (total delivered in interval)
      - time_sin, time_cos: last (end-of-interval time)
      - Extended features (if present): last

    Args:
        grid_df: DataFrame with DatetimeIndex at 5-min intervals
        target_interval_min: Target interval (15 or 60)

    Returns:
        Downsampled DataFrame with same columns
    """
    if target_interval_min <= 5:
        return grid_df.copy()

    freq = f'{target_interval_min}min'
    present_cols = set(grid_df.columns)

    agg_dict = {}
    for col in grid_df.columns:
        if col in _AGG_MEAN:
            agg_dict[col] = 'mean'
        elif col in _AGG_SUM:
            agg_dict[col] = 'sum'
        elif col in _AGG_LAST:
            agg_dict[col] = 'last'
        elif col in _EXTENDED_ONLY:
            agg_dict[col] = 'last'
        else:
            # Unknown columns default to last
            agg_dict[col] = 'last'

    resampled = grid_df.resample(freq)

    result_parts = {}
    for col, method in agg_dict.items():
        if method == 'sum':
            result_parts[col] = resampled[col].sum(min_count=1)
        elif method == 'mean':
            result_parts[col] = resampled[col].mean()
        else:
            result_parts[col] = resampled[col].last()

    result = pd.DataFrame(result_parts, columns=grid_df.columns)
    return result


_DEFAULT_HORIZONS = [
    {'interval_min': 5,  'history_steps': 12, 'forecast_steps': 12, 'label': '1hr@5min'},
    {'interval_min': 15, 'history_steps': 12, 'forecast_steps': 24, 'label': '6hr@15min'},
    {'interval_min': 60, 'history_steps': 12, 'forecast_steps': 72, 'label': '3day@1hr'},
]


def build_multihorizon_windows(grid_df: pd.DataFrame,
                               horizons: List[Dict] = None) -> Dict:
    """Build training windows at multiple time resolutions.

    Args:
        grid_df: 5-min base grid DataFrame
        horizons: list of dicts, each with:
            - 'interval_min': grid resolution (5, 15, 60)
            - 'history_steps': number of history timesteps
            - 'forecast_steps': number of forecast timesteps
            - 'label': human-readable label (e.g., '3hr@15min')

    Returns:
        dict mapping label → {'features': np.array, 'grid': DataFrame, 'interval_min': int}

    Default horizons if None:
        [{'interval_min': 5,  'history_steps': 12, 'forecast_steps': 12, 'label': '1hr@5min'},
         {'interval_min': 15, 'history_steps': 12, 'forecast_steps': 24, 'label': '6hr@15min'},
         {'interval_min': 60, 'history_steps': 12, 'forecast_steps': 72, 'label': '3day@1hr'}]
    """
    if horizons is None:
        horizons = _DEFAULT_HORIZONS

    results = {}
    for h in horizons:
        interval = h['interval_min']
        label = h['label']

        if interval <= 5:
            grid = grid_df.copy()
        else:
            grid = downsample_grid(grid_df, target_interval_min=interval)

        # Build feature array from the grid columns that match schema names
        all_names = EXTENDED_FEATURE_NAMES if len(grid.columns) > len(FEATURE_NAMES) else FEATURE_NAMES
        cols = [c for c in all_names if c in grid.columns]
        features = grid[cols].values.astype(np.float32)

        results[label] = {
            'features': features,
            'grid': grid,
            'interval_min': interval,
        }

    return results


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
