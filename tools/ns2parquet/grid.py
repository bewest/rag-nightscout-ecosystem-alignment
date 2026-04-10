"""
grid.py — Build 5-minute research grid from Nightscout JSON.

Reuses proven patterns from tools/cgmencode/real_data_adapter.py
(build_nightscout_grid) but outputs a DataFrame with column names matching
the GRID_SCHEMA for direct Parquet serialization.

The grid stores RAW values (mg/dL, units, grams) not normalized — normalization
is done at consumption time using the scales from cgmencode.schema.
"""

import json
import warnings

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple


def _normalize_timezone(tz_str: str) -> str:
    """Normalize Nightscout timezone (ETC/GMT+7 → Etc/GMT+7)."""
    if not tz_str:
        return 'UTC'
    if tz_str.upper().startswith('ETC/'):
        return 'Etc/' + tz_str[4:]
    return tz_str


def _to_local_index(index: pd.DatetimeIndex, patient_tz: str) -> pd.DatetimeIndex:
    """Convert DatetimeIndex to patient-local time for circadian features."""
    try:
        if index.tz is not None:
            return index.tz_convert(patient_tz)
        else:
            return index.tz_localize('UTC').tz_convert(patient_tz)
    except Exception:
        warnings.warn(
            f'Invalid patient timezone {patient_tz!r} — '
            f'circadian features (time_sin/cos) will use UTC.',
        )
        return index


def _lookup_schedule(sec_of_day: int, schedule: list, default: float = 0.0) -> float:
    """Look up current value from a time-varying schedule."""
    if not schedule:
        return default
    val = schedule[0].get('value', default)
    for entry in schedule:
        if entry.get('timeAsSeconds', 0) <= sec_of_day:
            val = entry.get('value', val)
    return float(val)


DIRECTION_MAP = {
    'DoubleUp': 2.0, 'SingleUp': 1.0, 'FortyFiveUp': 0.5,
    'Flat': 0.0,
    'FortyFiveDown': -0.5, 'SingleDown': -1.0, 'DoubleDown': -2.0,
}


def build_grid(data_path: str, patient_id: str,
               verbose: bool = False) -> Optional[pd.DataFrame]:
    """Build a 5-minute research grid from a Nightscout JSON directory.

    Args:
        data_path: Directory containing entries.json, treatments.json,
                   devicestatus.json, profile.json
        patient_id: Identifier for this patient/site
        verbose: Print progress messages

    Returns:
        DataFrame with columns matching GRID_SCHEMA, or None on error.
    """
    data_dir = Path(data_path)
    required = ['entries.json', 'treatments.json', 'devicestatus.json', 'profile.json']
    for f in required:
        if not (data_dir / f).exists():
            if verbose:
                print(f'  SKIP: missing {f} in {data_path}')
            return None

    # ── 1. Entries → glucose grid ────────────────────────────────────
    with open(data_dir / 'entries.json') as f:
        entries = json.load(f)

    cgm_times, cgm_values, cgm_dirs, cgm_rates = [], [], [], []
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
        cgm_dirs.append(e.get('direction', ''))
        cgm_rates.append(e.get('trendRate', np.nan))

    if not cgm_times:
        if verbose:
            print(f'  SKIP: no CGM data in {data_path}')
        return None

    cgm_df = pd.DataFrame({
        'glucose': cgm_values,
        'direction': cgm_dirs,
        'trend_rate_raw': pd.to_numeric(cgm_rates, errors='coerce'),
    }, index=pd.DatetimeIndex(cgm_times))
    cgm_df = cgm_df.sort_index()
    cgm_df = cgm_df[~cgm_df.index.duplicated(keep='first')]

    grid_start = cgm_df.index.min().floor('5min')
    grid_end = cgm_df.index.max().ceil('5min')
    grid = pd.date_range(grid_start, grid_end, freq='5min')
    df = pd.DataFrame(index=grid)

    cgm_rounded = cgm_df.copy()
    cgm_rounded.index = cgm_rounded.index.round('5min')
    cgm_grouped = cgm_rounded.groupby(level=0).first()
    df['glucose'] = cgm_grouped['glucose']
    df['glucose'] = df['glucose'].interpolate(limit=6)
    df['direction'] = cgm_grouped['direction']
    df['trend_rate_raw'] = cgm_grouped['trend_rate_raw']

    if verbose:
        n_valid = df['glucose'].notna().sum()
        print(f'  CGM: {len(entries)} raw → {n_valid}/{len(df)} grid points')

    # ── 2. DeviceStatus → IOB, COB, predictions, pump ───────────────
    with open(data_dir / 'devicestatus.json') as f:
        devicestatus = json.load(f)

    ds_data = {k: [] for k in [
        'ts', 'iob', 'cob', 'predicted_30', 'predicted_60', 'predicted_min',
        'hypo_risk', 'recommended_bolus', 'enacted_rate', 'enacted_bolus',
        'pump_battery', 'pump_reservoir',
    ]}

    for ds in devicestatus:
        loop = ds.get('loop', {}) or {}
        openaps = ds.get('openaps', {}) or {}

        # Try Loop structure first, then oref0
        iob_val = None
        cob_val = None
        pred_values = []

        if loop and isinstance(loop, dict):
            iob_data = loop.get('iob', {}) or {}
            cob_data = loop.get('cob', {}) or {}
            if 'iob' in iob_data:
                iob_val = float(iob_data['iob'])
                cob_val = float(cob_data.get('cob', 0))
                predicted = loop.get('predicted', {}) or {}
                pred_values = predicted.get('values', []) if isinstance(predicted, dict) else []

        if iob_val is None and openaps and isinstance(openaps, dict):
            iob_data = openaps.get('iob', {}) or {}
            if isinstance(iob_data, list) and iob_data:
                iob_data = iob_data[0]
            suggested = openaps.get('suggested', {}) or {}
            if 'iob' in iob_data:
                iob_val = float(iob_data.get('iob', 0))
            if 'IOB' in suggested:
                iob_val = iob_val or float(suggested['IOB'])
            cob_val = float(suggested.get('COB', 0))
            # Use best available prediction curve
            pred_bgs = suggested.get('predBGs', {}) or {}
            for curve in ['COB', 'UAM', 'IOB', 'ZT']:
                if curve in pred_bgs and pred_bgs[curve]:
                    pred_values = pred_bgs[curve]
                    break

        if iob_val is None:
            continue

        ts = pd.Timestamp(ds.get('created_at'))
        ds_data['ts'].append(ts)
        ds_data['iob'].append(iob_val)
        ds_data['cob'].append(cob_val or 0.0)
        ds_data['predicted_30'].append(float(pred_values[6]) if len(pred_values) > 6 else np.nan)
        ds_data['predicted_60'].append(float(pred_values[12]) if len(pred_values) > 12 else np.nan)
        ds_data['predicted_min'].append(float(min(pred_values)) if pred_values else np.nan)
        ds_data['hypo_risk'].append(float(sum(1 for v in pred_values if v < 70)))

        # Loop recommendations
        if loop:
            ds_data['recommended_bolus'].append(float(loop.get('recommendedBolus', 0) or 0))
            enacted = loop.get('enacted', {}) or {}
            ds_data['enacted_rate'].append(float(enacted.get('rate', np.nan)) if isinstance(enacted, dict) else np.nan)
            ds_data['enacted_bolus'].append(float(enacted.get('bolusVolume', 0) or 0) if isinstance(enacted, dict) else 0.0)
        else:
            enacted = openaps.get('enacted', {}) or {}
            ds_data['recommended_bolus'].append(0.0)
            ds_data['enacted_rate'].append(float(enacted.get('rate', np.nan)) if isinstance(enacted, dict) else np.nan)
            ds_data['enacted_bolus'].append(float(enacted.get('units', 0) or 0) if isinstance(enacted, dict) else 0.0)

        # Pump state
        pump = ds.get('pump', {}) or {}
        batt = pump.get('battery', {})
        ds_data['pump_battery'].append(
            float(batt.get('percent', np.nan)) if isinstance(batt, dict) else np.nan)
        ds_data['pump_reservoir'].append(float(pump.get('reservoir', np.nan)))

    if ds_data['ts']:
        ds_df = pd.DataFrame({k: v for k, v in ds_data.items() if k != 'ts'},
                             index=pd.DatetimeIndex(ds_data['ts']))
        ds_df = ds_df.sort_index()
        ds_df = ds_df[~ds_df.index.duplicated(keep='first')]
        ds_df.index = ds_df.index.round('5min')
        ds_grouped = ds_df.groupby(level=0).first()

        for col in ds_grouped.columns:
            df[col] = ds_grouped[col]
            if col != 'hypo_risk':
                df[col] = df[col].interpolate(limit=6)
            else:
                df[col] = df[col].ffill(limit=6)

    # Fill IOB/COB defaults
    for col in ['iob', 'cob']:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0)

    if verbose:
        print(f'  DeviceStatus: {len(devicestatus)} raw → {len(ds_data["ts"])} with IOB/COB')

    # ── 3. Treatments → bolus, carbs, temp basal, CAGE/SAGE ─────────
    with open(data_dir / 'treatments.json') as f:
        treatments = json.load(f)

    df['bolus'] = 0.0
    df['carbs'] = 0.0
    df['temp_rate'] = np.nan
    site_change_times = []
    sensor_start_times = []
    suspension_times = []

    for tx in treatments:
        et = tx.get('eventType', '')
        ts_str = tx.get('created_at') or tx.get('timestamp')
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str)
        if ts.tzinfo is None:
            ts = ts.tz_localize('UTC')
        else:
            ts = ts.tz_convert('UTC')
        ts = ts.round('5min')
        if ts not in df.index:
            continue

        if 'Bolus' in et and (tx.get('insulin') or 0) > 0:
            df.loc[ts, 'bolus'] += float(tx['insulin'])
        if (tx.get('carbs') or 0) > 0:
            df.loc[ts, 'carbs'] += float(tx['carbs'])
        if et == 'Temp Basal' and 'rate' in tx:
            rate = float(tx['rate'])
            dur_min = float(tx.get('duration', 5))
            n_slots = max(1, int(dur_min / 5))
            slot_idx = df.index.get_loc(ts)
            if isinstance(slot_idx, int):
                end_idx = min(slot_idx + n_slots, len(df))
                df.iloc[slot_idx:end_idx, df.columns.get_loc('temp_rate')] = rate

        if et == 'Site Change':
            site_change_times.append(pd.Timestamp(ts_str))
        elif et == 'Sensor Start':
            sensor_start_times.append(pd.Timestamp(ts_str))
        if et == 'Temp Basal' and (tx.get('reason') == 'suspend' or float(tx.get('rate', 1)) == 0):
            suspension_times.append(pd.Timestamp(ts_str))

    site_change_times.sort()
    sensor_start_times.sort()
    suspension_times.sort()

    # CAGE / SAGE
    df['cage_hours'] = np.nan
    if site_change_times:
        sc_idx = 0
        for i, ts in enumerate(df.index):
            while sc_idx < len(site_change_times) - 1 and site_change_times[sc_idx + 1] <= ts:
                sc_idx += 1
            if site_change_times[sc_idx] <= ts:
                df.iloc[i, df.columns.get_loc('cage_hours')] = (ts - site_change_times[sc_idx]).total_seconds() / 3600.0

    df['sage_hours'] = np.nan
    if sensor_start_times:
        ss_idx = 0
        for i, ts in enumerate(df.index):
            while ss_idx < len(sensor_start_times) - 1 and sensor_start_times[ss_idx + 1] <= ts:
                ss_idx += 1
            if sensor_start_times[ss_idx] <= ts:
                df.iloc[i, df.columns.get_loc('sage_hours')] = (ts - sensor_start_times[ss_idx]).total_seconds() / 3600.0

    df['sensor_warmup'] = 0.0
    for ss_ts in sensor_start_times:
        warmup_end = ss_ts + pd.Timedelta(hours=2)
        mask = (df.index >= ss_ts) & (df.index < warmup_end)
        df.loc[mask, 'sensor_warmup'] = 1.0

    if verbose:
        n_bolus = (df['bolus'] > 0).sum()
        n_carbs = (df['carbs'] > 0).sum()
        print(f'  Treatments: {n_bolus} bolus slots, {n_carbs} carb slots')

    # ── 4. Profile → basal schedule, ISF, CR, targets ────────────────
    with open(data_dir / 'profile.json') as f:
        profiles = json.load(f)

    if isinstance(profiles, list) and profiles:
        store = profiles[0].get('store', {})
    else:
        store = profiles.get('store', {}) if isinstance(profiles, dict) else {}
    default_profile = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}

    basal_schedule = default_profile.get('basal', [])
    isf_schedule = default_profile.get('sens', [])
    cr_schedule = default_profile.get('carbratio', [])
    target_low_schedule = default_profile.get('target_low', [])
    target_high_schedule = default_profile.get('target_high', [])
    patient_tz = _normalize_timezone(default_profile.get('timezone', ''))

    # Convert mmol/L profiles to mg/dL for cross-patient consistency.
    # Glucose in the grid is always mg/dL (Nightscout entries store sgv in mg/dL).
    # Profile values (ISF, targets) may be in mmol/L if that's the user's display unit.
    profile_units = (default_profile.get('units') or '').lower().replace('/', '')

    # Fallback: if profile has no units field, check settings.json from the site
    if not profile_units:
        settings_path = data_dir / 'settings.json'
        if settings_path.exists():
            with open(settings_path) as f:
                status_doc = json.load(f)
            site_settings = status_doc.get('settings', status_doc)
            profile_units = (site_settings.get('units') or 'mg/dL').lower().replace('/', '')
            if verbose:
                print(f'  Units from settings.json: {site_settings.get("units", "?")}')
        else:
            profile_units = 'mgdl'

    is_mmol = profile_units in ('mmoll', 'mmol')
    MMOLL_TO_MGDL = 18.01559  # Nightscout canonical constant (lib/constants.json)
    if is_mmol:
        for sched in [isf_schedule, target_low_schedule, target_high_schedule]:
            for entry in sched:
                if 'value' in entry:
                    entry['value'] = entry['value'] * MMOLL_TO_MGDL
        if verbose:
            print(f'  Profile units: mmol/L → converted ISF/targets to mg/dL')
    local_index = _to_local_index(df.index, patient_tz)

    # Net basal
    scheduled = np.zeros(len(df))
    for i, ts in enumerate(local_index):
        sec_of_day = ts.hour * 3600 + ts.minute * 60 + ts.second
        scheduled[i] = _lookup_schedule(sec_of_day, basal_schedule)

    df['temp_rate'] = df['temp_rate'].ffill()
    df['temp_rate'] = df['temp_rate'].fillna(pd.Series(scheduled, index=df.index))
    df['net_basal'] = df['temp_rate'].values - scheduled
    df['scheduled_basal_rate'] = scheduled
    df['actual_basal_rate'] = df['temp_rate'].values

    # ── 5. Circadian / temporal encodings ────────────────────────────
    local_hours = local_index.hour + local_index.minute / 60.0
    df['time_sin'] = np.sin(2 * np.pi * local_hours / 24.0)
    df['time_cos'] = np.cos(2 * np.pi * local_hours / 24.0)

    local_dow = local_index.dayofweek
    df['day_sin'] = np.sin(2 * np.pi * local_dow / 7.0)
    df['day_cos'] = np.cos(2 * np.pi * local_dow / 7.0)

    local_dom = local_index.day
    df['month_sin'] = np.sin(2 * np.pi * local_dom / 30.4)
    df['month_cos'] = np.cos(2 * np.pi * local_dom / 30.4)

    # ── 6. Glucose dynamics ──────────────────────────────────────────
    glucose = df['glucose'].values
    df['glucose_roc'] = np.concatenate([[np.nan], np.diff(glucose)])
    roc = df['glucose_roc'].values
    df['glucose_accel'] = np.concatenate([[np.nan], np.diff(roc)])

    # Rolling noise: std of glucose diffs over 1hr (12 steps)
    glucose_diff = pd.Series(np.diff(glucose, prepend=np.nan), index=df.index)
    df['rolling_noise'] = glucose_diff.rolling(12, min_periods=3).std()

    # Hours since last CGM reading
    has_cgm = cgm_grouped['glucose'].reindex(df.index).notna()
    hours_since = np.zeros(len(df))
    last_cgm_idx = -1
    for i in range(len(df)):
        if has_cgm.iloc[i]:
            last_cgm_idx = i
        if last_cgm_idx >= 0:
            hours_since[i] = (i - last_cgm_idx) * 5.0 / 60.0
        else:
            hours_since[i] = np.nan
    df['hours_since_cgm'] = hours_since

    # Trend direction (ordinal)
    df['trend_direction'] = df['direction'].map(DIRECTION_MAP)
    # Trend rate from CGM
    df['trend_rate'] = df['trend_rate_raw']

    # ── 7. Time-since features ───────────────────────────────────────
    bolus_vals = df['bolus'].values
    carb_vals = df['carbs'].values
    time_since_bolus = np.full(len(df), 360.0)  # cap at 6 hours
    time_since_carb = np.full(len(df), 360.0)
    last_bolus = -99999
    last_carb = -99999
    for i in range(len(df)):
        if bolus_vals[i] > 0:
            last_bolus = i
        if carb_vals[i] > 0:
            last_carb = i
        if last_bolus >= 0:
            time_since_bolus[i] = min((i - last_bolus) * 5.0, 360.0)
        if last_carb >= 0:
            time_since_carb[i] = min((i - last_carb) * 5.0, 360.0)
    df['time_since_bolus_min'] = time_since_bolus
    df['time_since_carb_min'] = time_since_carb

    # ── 8. Override (placeholder — requires treatment parsing) ───────
    df['override_active'] = 0.0
    df['override_type'] = 0.0

    # ── 9. Profile-derived context ───────────────────────────────────
    isf_vals = np.zeros(len(df))
    cr_vals = np.zeros(len(df))
    target_mid = np.zeros(len(df))
    for i, ts in enumerate(local_index):
        sec = ts.hour * 3600 + ts.minute * 60 + ts.second
        isf_vals[i] = _lookup_schedule(sec, isf_schedule, 100.0)
        cr_vals[i] = _lookup_schedule(sec, cr_schedule, 10.0)
        t_low = _lookup_schedule(sec, target_low_schedule, 100.0)
        t_high = _lookup_schedule(sec, target_high_schedule, 120.0)
        target_mid[i] = (t_low + t_high) / 2.0

    df['scheduled_isf'] = isf_vals
    df['scheduled_cr'] = cr_vals
    df['glucose_vs_target'] = df['glucose'].values - target_mid

    # ── 10. Loop/AID context (from devicestatus) ─────────────────────
    for col in ['predicted_30', 'predicted_60', 'predicted_min',
                'hypo_risk', 'recommended_bolus', 'enacted_rate', 'enacted_bolus',
                'pump_battery', 'pump_reservoir']:
        if col not in df.columns:
            df[col] = np.nan

    # Rename to match grid schema
    df = df.rename(columns={
        'hypo_risk': 'loop_hypo_risk',
        'recommended_bolus': 'loop_recommended',
        'predicted_30': 'loop_predicted_30',
        'predicted_60': 'loop_predicted_60',
        'predicted_min': 'loop_predicted_min',
        'enacted_rate': 'loop_enacted_rate',
        'enacted_bolus': 'loop_enacted_bolus',
    })

    # ── 11. Sensor lifecycle ─────────────────────────────────────────
    sage = df['sage_hours'].values
    df['sensor_phase'] = np.where(
        sage < 2, 0.0,
        np.where(sage < 24, 0.25,
        np.where(sage < 168, 0.5,
        np.where(sage < 240, 0.75, 1.0))))
    df.loc[df['sage_hours'].isna(), 'sensor_phase'] = np.nan

    # Suspension time (vectorized)
    suspension_min = np.full(len(df), 360.0)
    if suspension_times:
        sus_idx = 0
        last_sus_step = -99999
        for i, ts in enumerate(df.index):
            while sus_idx < len(suspension_times) and suspension_times[sus_idx] <= ts:
                sus_step = int((ts - suspension_times[sus_idx]).total_seconds() / 300)
                last_sus_step = i - sus_step
                sus_idx += 1
            if last_sus_step >= 0:
                suspension_min[i] = min((i - last_sus_step) * 5.0, 360.0)
    df['suspension_time_min'] = suspension_min

    # ── 12. Add patient_id and prepare output ────────────────────────
    df['patient_id'] = patient_id
    df.index.name = 'time'
    df = df.reset_index()

    # Select and order columns to match GRID_SCHEMA
    grid_columns = [
        'patient_id', 'time',
        'glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs',
        'time_sin', 'time_cos',
        'day_sin', 'day_cos', 'override_active', 'override_type',
        'glucose_roc', 'glucose_accel', 'time_since_bolus_min', 'time_since_carb_min',
        'cage_hours', 'sage_hours', 'sensor_warmup',
        'month_sin', 'month_cos',
        'trend_direction', 'trend_rate', 'rolling_noise', 'hours_since_cgm',
        'loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min',
        'loop_hypo_risk', 'loop_recommended',
        'loop_enacted_rate', 'loop_enacted_bolus',
        'scheduled_isf', 'scheduled_cr', 'glucose_vs_target',
        'pump_battery', 'pump_reservoir',
        'sensor_phase', 'suspension_time_min',
        'scheduled_basal_rate', 'actual_basal_rate',
        'direction',
    ]

    # Add any missing columns
    for col in grid_columns:
        if col not in df.columns:
            df[col] = np.nan

    df = df[grid_columns]

    if verbose:
        n_days = (df['time'].max() - df['time'].min()).total_seconds() / 86400
        print(f'  Grid: {len(df)} rows, {n_days:.1f} days')

    return df
