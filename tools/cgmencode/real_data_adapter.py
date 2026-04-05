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
    cgm_directions = []
    cgm_trend_rates = []
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
        cgm_directions.append(e.get('direction', ''))
        cgm_trend_rates.append(e.get('trendRate', np.nan))

    cgm_df = pd.DataFrame({
        'glucose': cgm_values,
        'direction': cgm_directions,
        'trend_rate': cgm_trend_rates,
    }, index=pd.DatetimeIndex(cgm_times))
    cgm_df = cgm_df.sort_index()
    cgm_df = cgm_df[~cgm_df.index.duplicated(keep='first')]

    grid_start = cgm_df.index.min().floor('5min')
    grid_end = cgm_df.index.max().ceil('5min')
    grid = pd.date_range(grid_start, grid_end, freq='5min')
    df = pd.DataFrame(index=grid)

    cgm_df.index = cgm_df.index.round('5min')
    cgm_grouped = cgm_df.groupby(level=0).first()
    df['glucose'] = cgm_grouped['glucose']
    df['glucose'] = df['glucose'].interpolate(limit=6)

    # Preserve CGM-provided direction and trendRate for enriched features
    df['direction'] = cgm_grouped['direction']
    df['trend_rate_raw'] = pd.to_numeric(cgm_grouped['trend_rate'], errors='coerce')

    if verbose:
        print(f"  CGM: {len(entries)} raw → {df['glucose'].notna().sum()}/{len(df)} grid points "
              f"({grid_start.strftime('%Y-%m-%d')} to {grid_end.strftime('%Y-%m-%d')})")

    # --- 2. Extract IOB/COB from devicestatus ---
    with open(data_dir / 'devicestatus.json') as f:
        devicestatus = json.load(f)

    ds_times = []
    ds_iob = []
    ds_cob = []
    ds_predicted_30 = []
    ds_predicted_60 = []
    ds_predicted_min = []
    ds_hypo_risk = []
    ds_recommended_bolus = []
    ds_enacted_rate = []
    ds_enacted_bolus = []
    ds_pump_battery = []
    ds_pump_reservoir = []
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

        # Loop predicted glucose trajectory
        predicted = loop.get('predicted', {})
        pred_values = predicted.get('values', []) if isinstance(predicted, dict) else []
        ds_predicted_30.append(float(pred_values[6]) if len(pred_values) > 6 else np.nan)
        ds_predicted_60.append(float(pred_values[12]) if len(pred_values) > 12 else np.nan)
        ds_predicted_min.append(float(min(pred_values)) if pred_values else np.nan)
        ds_hypo_risk.append(float(sum(1 for v in pred_values if v < 70)))

        # Loop recommendations and enacted actions
        ds_recommended_bolus.append(float(loop.get('recommendedBolus', 0) or 0))
        enacted = loop.get('enacted', {})
        if isinstance(enacted, dict):
            ds_enacted_rate.append(float(enacted.get('rate', np.nan)))
            ds_enacted_bolus.append(float(enacted.get('bolusVolume', 0) or 0))
        else:
            ds_enacted_rate.append(np.nan)
            ds_enacted_bolus.append(0.0)

        # Pump hardware state
        pump = ds.get('pump', {})
        batt = pump.get('battery', {})
        ds_pump_battery.append(float(batt.get('percent', np.nan)) if isinstance(batt, dict) else np.nan)
        ds_pump_reservoir.append(float(pump.get('reservoir', np.nan)))

    ds_df = pd.DataFrame({
        'iob': ds_iob, 'cob': ds_cob,
        'predicted_30': ds_predicted_30, 'predicted_60': ds_predicted_60,
        'predicted_min': ds_predicted_min, 'hypo_risk': ds_hypo_risk,
        'recommended_bolus': ds_recommended_bolus,
        'enacted_rate': ds_enacted_rate, 'enacted_bolus': ds_enacted_bolus,
        'pump_battery': ds_pump_battery, 'pump_reservoir': ds_pump_reservoir,
    }, index=pd.DatetimeIndex(ds_times))
    ds_df = ds_df.sort_index()
    ds_df = ds_df[~ds_df.index.duplicated(keep='first')]
    ds_df.index = ds_df.index.round('5min')
    ds_grouped = ds_df.groupby(level=0).first()
    df['iob'] = ds_grouped['iob']
    df['cob'] = ds_grouped['cob']
    df['iob'] = df['iob'].interpolate(limit=6).fillna(0)
    df['cob'] = df['cob'].interpolate(limit=6).fillna(0)

    # Preserve enriched devicestatus fields for Gen-4 features
    for col in ['predicted_30', 'predicted_60', 'predicted_min', 'hypo_risk',
                'recommended_bolus', 'enacted_rate', 'enacted_bolus',
                'pump_battery', 'pump_reservoir']:
        df[col] = ds_grouped[col] if col in ds_grouped.columns else np.nan
        df[col] = df[col].interpolate(limit=6) if col != 'hypo_risk' else df[col].ffill(limit=6)

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

    # --- 3c. Extract insulin suspension events ---
    suspension_times = []
    for tx in treatments:
        et = tx.get('eventType', '')
        reason = tx.get('reason', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        if et == 'Temp Basal' and (reason == 'suspend' or float(tx.get('rate', 1)) == 0):
            suspension_times.append(pd.Timestamp(ts_str))
    suspension_times.sort()
    df.attrs['suspension_times'] = suspension_times

    # --- 4. Compute net_basal ---
    with open(data_dir / 'profile.json') as f:
        profiles = json.load(f)

    if isinstance(profiles, list) and profiles:
        store = profiles[0].get('store', {})
    else:
        store = profiles.get('store', {})
    default_profile = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}
    basal_schedule = default_profile.get('basal', [])

    # Extract patient-specific DIA (fixes hardcoded DEFAULT_DIA=5.0 bug)
    patient_dia = float(default_profile.get('dia', DEFAULT_DIA))
    df.attrs['patient_dia'] = patient_dia

    # Extract ISF schedule (insulin sensitivity factor — mg/dL per unit)
    isf_schedule = default_profile.get('sens', default_profile.get('isfProfile', {}).get('sensitivities', []))
    if not isf_schedule:
        isf_schedule = [{'time': '00:00', 'timeAsSeconds': 0, 'value': 100}]

    # Extract CR schedule (carb ratio — grams per unit)
    cr_schedule = default_profile.get('carbratio', default_profile.get('carbRatio', []))
    if not cr_schedule:
        cr_schedule = [{'time': '00:00', 'timeAsSeconds': 0, 'value': 10}]

    # Extract glucose targets
    target_low_schedule = default_profile.get('target_low', [])
    target_high_schedule = default_profile.get('target_high', [])
    if not target_low_schedule:
        target_low_schedule = [{'time': '00:00', 'timeAsSeconds': 0, 'value': 100}]
    if not target_high_schedule:
        target_high_schedule = [{'time': '00:00', 'timeAsSeconds': 0, 'value': 120}]

    # Store schedules for downstream feature computation
    df.attrs['isf_schedule'] = isf_schedule
    df.attrs['cr_schedule'] = cr_schedule
    df.attrs['target_low_schedule'] = target_low_schedule
    df.attrs['target_high_schedule'] = target_high_schedule

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
        print(f"  Patient DIA: {patient_dia:.1f}h")
        n_with_trend = df['trend_rate_raw'].notna().sum()
        n_with_dir = (df['direction'].fillna('') != '').sum()
        n_with_pred = df['predicted_30'].notna().sum()
        print(f"  Enriched fields: {n_with_trend} trendRate, {n_with_dir} direction, "
              f"{n_with_pred} loop.predicted, {len(suspension_times)} suspensions")

    return df, features


def build_extended_features(df: pd.DataFrame, features: np.ndarray,
                            treatments: list = None,
                            verbose: bool = False,
                            ) -> np.ndarray:
    """
    Extend the 8-feature grid with agentic context features (→ 21 features).

    Adds: day-of-week encoding, override state, glucose dynamics, temporal gaps,
    CAGE (cannula age), SAGE (sensor age), sensor warmup flag, and monthly phase.
    The first 8 columns are identical to the input features array.

    Args:
        df: DataFrame from build_nightscout_grid (DatetimeIndex, raw columns)
        features: (N, 8) normalized array from build_nightscout_grid
        treatments: Optional pre-loaded treatments list. If None, skips override
                    extraction (override channels will be zero).
        verbose: Print progress

    Returns:
        (N, 21) normalized float32 array matching EXTENDED_FEATURE_NAMES
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

    # --- Channel 19–20: Month-of-year encoding (sin/cos, period ≈ 30.4 days) ---
    # Use patient-local time for day-of-month
    dom = local_index.day.values.astype(np.float64)  # 1–31
    MEAN_MONTH_DAYS = 30.4375  # average days per month
    extended[:, 19] = np.sin(2 * np.pi * dom / MEAN_MONTH_DAYS).astype(np.float32)
    extended[:, 20] = np.cos(2 * np.pi * dom / MEAN_MONTH_DAYS).astype(np.float32)

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


def _lookup_schedule_value(sec_of_day: int, schedule: list, default: float = 0.0) -> float:
    """Look up value from a time-of-day schedule (ISF, CR, target)."""
    value = default
    for entry in schedule:
        if entry.get('timeAsSeconds', 0) <= sec_of_day:
            value = float(entry.get('value', default))
    return value


# Trend arrow direction encoding (Dexcom standard)
_DIRECTION_MAP = {
    'DoubleDown': -2.0, 'SingleDown': -1.0, 'FortyFiveDown': -0.5,
    'Flat': 0.0,
    'FortyFiveUp': 0.5, 'SingleUp': 1.0, 'DoubleUp': 2.0,
    'NOT COMPUTABLE': 0.0, 'RATE OUT OF RANGE': 0.0, 'NONE': 0.0, '': 0.0,
}


def build_enriched_features(df: pd.DataFrame, features_21: np.ndarray,
                            verbose: bool = False) -> np.ndarray:
    """
    Extend the 21-feature array with Gen-4 enrichment (→ 39 features).

    Adds diabetes-relevant signals derivable from existing Nightscout data:
    - CGM signal quality: trend arrows, hardware trendRate, rolling noise, gap proxy
    - AID algorithm context: Loop predicted glucose, enacted actions, recommendations
    - Profile-derived: scheduled ISF/CR, glucose-vs-target offset
    - Device hardware: pump battery, reservoir
    - Enhanced lifecycle: sensor phase encoding, suspension tracking

    Args:
        df: DataFrame from build_nightscout_grid (with enriched columns)
        features_21: (N, 21) normalized array from build_extended_features
        verbose: Print progress

    Returns:
        (N, 39) normalized float32 array matching ENRICHED_FEATURE_NAMES
    """
    from .schema import (NUM_FEATURES_ENRICHED, NORMALIZATION_SCALES,
                         IDX_TREND_DIRECTION, IDX_TREND_RATE, IDX_ROLLING_NOISE,
                         IDX_HOURS_SINCE_CGM, IDX_LOOP_PREDICTED_30,
                         IDX_LOOP_PREDICTED_60, IDX_LOOP_PREDICTED_MIN,
                         IDX_LOOP_HYPO_RISK, IDX_LOOP_RECOMMENDED,
                         IDX_LOOP_ENACTED_RATE, IDX_LOOP_ENACTED_BOLUS,
                         IDX_SCHEDULED_ISF, IDX_SCHEDULED_CR,
                         IDX_GLUCOSE_VS_TARGET, IDX_PUMP_BATTERY,
                         IDX_PUMP_RESERVOIR, IDX_SENSOR_PHASE,
                         IDX_SUSPENSION_TIME)

    N = len(features_21)
    enriched = np.zeros((N, NUM_FEATURES_ENRICHED), dtype=np.float32)
    enriched[:, :21] = features_21

    SCALE = NORMALIZATION_SCALES

    # --- Channel 21: Trend direction (ordinal from CGM arrows) ---
    if 'direction' in df.columns:
        directions = df['direction'].fillna('').values
        dir_vals = np.array([_DIRECTION_MAP.get(str(d).strip(), 0.0) for d in directions],
                           dtype=np.float32)
        enriched[:, IDX_TREND_DIRECTION] = dir_vals / SCALE['trend_direction']

    # --- Channel 22: CGM-provided trendRate (cleaner than computed ROC) ---
    if 'trend_rate_raw' in df.columns:
        tr = df['trend_rate_raw'].interpolate(limit=6).fillna(0).values.astype(np.float32)
        enriched[:, IDX_TREND_RATE] = tr / SCALE['trend_rate']

    # --- Channel 23: Rolling glucose noise (1hr std of glucose diffs) ---
    glucose_raw = df['glucose'].values
    diffs = np.diff(glucose_raw, prepend=glucose_raw[0])
    diffs = np.nan_to_num(diffs, nan=0.0)
    # Rolling std with 12-step window (1 hour at 5min intervals)
    rolling_std = pd.Series(diffs).rolling(12, min_periods=3).std().fillna(0).values
    enriched[:, IDX_ROLLING_NOISE] = rolling_std.astype(np.float32) / SCALE['rolling_noise']

    # --- Channel 24: Hours since last valid CGM reading (gap proxy) ---
    cgm_valid = ~np.isnan(df['glucose'].values)
    hours_since = np.zeros(N, dtype=np.float32)
    last_valid_idx = -1
    for i in range(N):
        if cgm_valid[i]:
            last_valid_idx = i
        if last_valid_idx >= 0:
            hours_since[i] = (i - last_valid_idx) * 5.0 / 60.0
        else:
            hours_since[i] = 24.0  # cap
    enriched[:, IDX_HOURS_SINCE_CGM] = np.clip(hours_since, 0, 24) / SCALE['hours_since_cgm']

    # --- Channels 25-28: Loop predicted glucose summary ---
    for col, idx, scale_key in [
        ('predicted_30', IDX_LOOP_PREDICTED_30, 'loop_predicted'),
        ('predicted_60', IDX_LOOP_PREDICTED_60, 'loop_predicted'),
        ('predicted_min', IDX_LOOP_PREDICTED_MIN, 'loop_predicted'),
        ('hypo_risk', IDX_LOOP_HYPO_RISK, 'loop_hypo_risk'),
    ]:
        if col in df.columns:
            vals = df[col].fillna(0).values.astype(np.float32)
            enriched[:, idx] = vals / SCALE[scale_key]

    # --- Channel 29: Loop recommended bolus ---
    if 'recommended_bolus' in df.columns:
        enriched[:, IDX_LOOP_RECOMMENDED] = (
            df['recommended_bolus'].fillna(0).values.astype(np.float32) / SCALE['loop_recommended']
        )

    # --- Channels 30-31: Loop enacted actions ---
    if 'enacted_rate' in df.columns:
        enriched[:, IDX_LOOP_ENACTED_RATE] = (
            df['enacted_rate'].interpolate(limit=6).fillna(0).values.astype(np.float32)
            / SCALE['loop_enacted_rate']
        )
    if 'enacted_bolus' in df.columns:
        enriched[:, IDX_LOOP_ENACTED_BOLUS] = (
            df['enacted_bolus'].fillna(0).values.astype(np.float32)
            / SCALE['loop_enacted_bolus']
        )

    # --- Channels 32-33: Scheduled ISF and CR from profile ---
    patient_tz = df.attrs.get('patient_tz', 'UTC')
    local_index = _to_local_index(df.index, patient_tz)
    isf_schedule = df.attrs.get('isf_schedule', [{'timeAsSeconds': 0, 'value': 100}])
    cr_schedule = df.attrs.get('cr_schedule', [{'timeAsSeconds': 0, 'value': 10}])
    target_low_schedule = df.attrs.get('target_low_schedule', [{'timeAsSeconds': 0, 'value': 100}])
    target_high_schedule = df.attrs.get('target_high_schedule', [{'timeAsSeconds': 0, 'value': 120}])

    for i, ts in enumerate(local_index):
        sec_of_day = ts.hour * 3600 + ts.minute * 60 + ts.second
        enriched[i, IDX_SCHEDULED_ISF] = (
            _lookup_schedule_value(sec_of_day, isf_schedule, 100.0) / SCALE['scheduled_isf']
        )
        enriched[i, IDX_SCHEDULED_CR] = (
            _lookup_schedule_value(sec_of_day, cr_schedule, 10.0) / SCALE['scheduled_cr']
        )
        # Channel 34: Glucose vs target midpoint
        t_low = _lookup_schedule_value(sec_of_day, target_low_schedule, 100.0)
        t_high = _lookup_schedule_value(sec_of_day, target_high_schedule, 120.0)
        t_mid = (t_low + t_high) / 2.0
        if not np.isnan(glucose_raw[i]):
            enriched[i, IDX_GLUCOSE_VS_TARGET] = (
                (glucose_raw[i] - t_mid) / SCALE['glucose_vs_target']
            )

    # --- Channels 35-36: Pump hardware state ---
    if 'pump_battery' in df.columns:
        enriched[:, IDX_PUMP_BATTERY] = (
            df['pump_battery'].interpolate(limit=12).fillna(100).values.astype(np.float32)
            / SCALE['pump_battery']
        )
    if 'pump_reservoir' in df.columns:
        enriched[:, IDX_PUMP_RESERVOIR] = (
            df['pump_reservoir'].interpolate(limit=12).fillna(300).values.astype(np.float32)
            / SCALE['pump_reservoir']
        )

    # --- Channel 37: Sensor phase (discrete lifecycle encoding) ---
    if 'sage_hours' in df.columns:
        sage = df['sage_hours'].values
        phase = np.zeros(N, dtype=np.float32)
        for i in range(N):
            s = sage[i]
            if np.isnan(s):
                phase[i] = 0.5  # assume peak if unknown
            elif s < 2:
                phase[i] = 0.0    # warmup
            elif s < 48:
                phase[i] = 0.25   # early
            elif s < 168:
                phase[i] = 0.5    # peak (days 2-7)
            elif s < 240:
                phase[i] = 0.75   # late (days 7-10)
            else:
                phase[i] = 1.0    # extended (>10 days)
        enriched[:, IDX_SENSOR_PHASE] = phase

    # --- Channel 38: Time since last insulin suspension ---
    suspension_times = df.attrs.get('suspension_times', [])
    if suspension_times:
        susp_minutes = np.full(N, SCALE['suspension_time'], dtype=np.float32)
        s_idx = 0
        for i, ts in enumerate(df.index):
            while s_idx < len(suspension_times) - 1 and suspension_times[s_idx + 1] <= ts:
                s_idx += 1
            if suspension_times[s_idx] <= ts:
                delta_min = (ts - suspension_times[s_idx]).total_seconds() / 60.0
                susp_minutes[i] = min(delta_min, SCALE['suspension_time'])
        enriched[:, IDX_SUSPENSION_TIME] = susp_minutes / SCALE['suspension_time']
    else:
        enriched[:, IDX_SUSPENSION_TIME] = 1.0  # capped (no suspensions known)

    if verbose:
        print(f"  Enriched features: {enriched.shape} ({NUM_FEATURES_ENRICHED} channels)")
        n_trend = int(np.sum(enriched[:, IDX_TREND_DIRECTION] != 0))
        n_pred = int(np.sum(enriched[:, IDX_LOOP_PREDICTED_30] != 0))
        n_enacted = int(np.sum(enriched[:, IDX_LOOP_ENACTED_RATE] != 0))
        print(f"    Trend arrows: {n_trend}/{N}, Loop predicted: {n_pred}/{N}, "
              f"Enacted: {n_enacted}/{N}")
        noise_mean = float(np.mean(rolling_std))
        print(f"    Rolling noise mean: {noise_mean:.2f} mg/dL/5min")

    return enriched


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
                                  extended_features: bool = False,
                                  enriched_features: bool = False,
                                  ) -> Tuple[Optional[object], Optional[object]]:
    """
    Load multiple patient Nightscout directories → single combined dataset.

    Each path should point to a patient's training/ directory containing
    entries.json, treatments.json, devicestatus.json, profile.json.

    Windows from each patient are extracted independently, then split
    chronologically per patient (first 80% train, last 20% val). Training
    windows are shuffled across patients for batch diversity; validation
    windows preserve temporal ordering.

    Args:
        extended_features: If True, build 21-feature extended arrays (includes
            CAGE/SAGE, monthly phase, ROC/accel, etc.) and use doubled window
            size (window_size*2 total steps = window_size history + future).
            Returns TensorDataset pairs for use with train_forecast().
        enriched_features: If True, build 39-feature Gen-4 arrays (includes
            CGM quality, AID context, profile, pump state, sensor lifecycle).
            Implies extended_features=True. Overrides extended_features flag.

    Returns:
        (train_dataset, val_dataset)
    """
    if enriched_features:
        extended_features = True  # enriched builds on top of extended

    per_patient_windows = []

    if extended_features:
        # Extended path: 21+ features, doubled window for history+future
        actual_window = window_size * 2
    elif conditioned:
        actual_window = window_size * 2
    else:
        actual_window = window_size

    for i, data_path in enumerate(data_paths):
        patient_id = Path(data_path).parent.name  # e.g. 'a', 'b', ...
        print(f"  Patient {patient_id} ({i+1}/{len(data_paths)}): {data_path}")

        df, features = build_nightscout_grid(data_path, verbose=False)
        if df is None:
            print(f"    SKIP: no valid data")
            continue

        if extended_features:
            features = build_extended_features(df, features, verbose=False)

        if enriched_features:
            features = build_enriched_features(df, features, verbose=False)

        windows = split_into_windows(features, window_size=actual_window)
        if not windows:
            print(f"    SKIP: no valid windows")
            continue

        n_feat = features.shape[1] if hasattr(features, 'shape') else '?'
        print(f"    {len(df)} rows → {len(windows)} windows "
              f"({n_feat}f, {df['glucose'].min():.0f}-{df['glucose'].max():.0f} mg/dL)")
        per_patient_windows.append(windows)

    if not per_patient_windows:
        print("  ERROR: no valid windows from any patient")
        return None, None

    # Per-patient chronological split: within each patient, first (1-val_fraction)
    # windows become training, last val_fraction become validation. This ensures
    # val windows are always temporally AFTER train windows for each patient,
    # preventing temporal proximity leakage from random shuffling.
    train_windows = []
    val_windows = []
    for patient_windows in per_patient_windows:
        split_idx = int(len(patient_windows) * (1 - val_fraction))
        train_windows.extend(patient_windows[:split_idx])
        val_windows.extend(patient_windows[split_idx:])

    # Shuffle training set to mix patients (prevents batch-level patient bias).
    # Validation set is NOT shuffled to preserve temporal ordering for analysis.
    rng = np.random.RandomState(42)
    rng.shuffle(train_windows)

    train_tensor = torch.tensor(np.array(train_windows), dtype=torch.float32)
    val_tensor = torch.tensor(np.array(val_windows), dtype=torch.float32)

    if extended_features:
        # TensorDataset (x, x) pairs for train_forecast() which handles its own masking
        train_ds = torch.utils.data.TensorDataset(train_tensor, train_tensor)
        val_ds = torch.utils.data.TensorDataset(val_tensor, val_tensor)
    elif conditioned:
        train_ds = ConditionedDataset(train_tensor, window_size=window_size)
        val_ds = ConditionedDataset(val_tensor, window_size=window_size)
    else:
        train_ds = CGMDataset(train_tensor, task=task, window_size=window_size)
        val_ds = CGMDataset(val_tensor, task=task, window_size=window_size)

    total_windows = len(train_windows) + len(val_windows)
    print(f"  Multi-patient total: {total_windows} windows from "
          f"{len(data_paths)} patients → {len(train_windows)} train, "
          f"{len(val_windows)} val (chronological split per patient)")

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
