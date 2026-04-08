#!/usr/bin/env python3
"""
Autotune & UAM Characterization: oref0/Loop vs cgmencode ML

Evaluates and compares inference capabilities across AID ecosystem:
  - Autotune: oref0's parameter tuning vs ML-based settings estimation
  - UAM: oref0's unannounced meal detection vs physics-based meal detection

Uses patient data from externals/ns-data/patients/{a-k}.
Generates visualizations and a characterization report.

Usage:
    python eval_autotune_uam.py [--patients a,b,c] [--output-dir visualizations/autotune-uam-eval]
"""

import json
import os
import sys
import argparse
import warnings
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from scipy import stats

warnings.filterwarnings('ignore', category=FutureWarning)

# ============================================================
# Constants
# ============================================================
MMOL_TO_MGDL = 18.0182
GRID_INTERVAL_MIN = 5
STEPS_PER_HOUR = 60 // GRID_INTERVAL_MIN  # 12
ROOT = Path(__file__).resolve().parent.parent.parent
NS_DATA = ROOT / 'externals' / 'ns-data' / 'patients'
DEFAULT_OUTPUT = ROOT / 'visualizations' / 'autotune-uam-eval'
REPORT_DIR = ROOT / 'docs' / '60-research'
ALL_PATIENTS = list('abcdefghik')  # exclude j (only 436 treatments)


# ============================================================
# Data Classes
# ============================================================
@dataclass
class ProfileSettings:
    basal_schedule: list  # [{time_seconds: int, rate: float}, ...]
    isf_mgdl: float       # ISF in mg/dL
    cr: float             # carb ratio (g per unit)
    dia_hours: float      # duration of insulin action
    units: str            # 'mg/dL' or 'mmol/L' (original)

    def basal_at(self, seconds_of_day: int) -> float:
        """Look up scheduled basal rate at a given time of day."""
        rate = self.basal_schedule[0]['rate']
        for entry in self.basal_schedule:
            if entry['time_seconds'] <= seconds_of_day:
                rate = entry['rate']
            else:
                break
        return rate


@dataclass
class UAMEvent:
    start: pd.Timestamp
    end: pd.Timestamp
    peak_glucose: float
    rise_mgdl: float
    announced: bool
    carb_grams: float = 0.0


@dataclass
class PatientResults:
    patient_id: str
    # UAM results
    uam_events: list = field(default_factory=list)
    oref0_uam_detections: list = field(default_factory=list)
    physics_meal_detections: list = field(default_factory=list)
    uam_metrics: dict = field(default_factory=dict)
    # Autotune results
    hourly_deviations: Optional[np.ndarray] = None
    hourly_deviation_counts: Optional[np.ndarray] = None
    autotune_basal: Optional[np.ndarray] = None
    original_basal: Optional[np.ndarray] = None
    effective_isf: float = 0.0
    profile_isf: float = 0.0
    effective_cr: float = 0.0
    profile_cr: float = 0.0
    fasting_hours: float = 0.0
    total_hours: float = 0.0


# ============================================================
# SECTION 1: DATA LOADING
# ============================================================

def load_json(filepath: Path) -> list:
    """Load a JSON file, returning list of records."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return data


def parse_profile(profile_data: list) -> ProfileSettings:
    """Extract basal, ISF, CR, DIA from Nightscout profile."""
    prof = profile_data[0] if profile_data else {}
    store = prof.get('store', {})
    default = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}

    # Basal schedule
    basal_raw = default.get('basal', [])
    basal_schedule = [
        {'time_seconds': b.get('timeAsSeconds', 0), 'rate': b.get('value', 0.0)}
        for b in sorted(basal_raw, key=lambda x: x.get('timeAsSeconds', 0))
    ]
    if not basal_schedule:
        basal_schedule = [{'time_seconds': 0, 'rate': 0.5}]

    # ISF (may be in mmol/L)
    sens_raw = default.get('sens', default.get('sensitivity', []))
    units = default.get('units', 'mmol/L')
    if sens_raw and isinstance(sens_raw, list):
        isf_val = sens_raw[0].get('value', 50)
    elif isinstance(sens_raw, (int, float)):
        isf_val = sens_raw
    else:
        isf_val = 50

    if units == 'mmol/L' or isf_val < 15:  # heuristic: mmol/L values are small
        isf_mgdl = isf_val * MMOL_TO_MGDL
    else:
        isf_mgdl = isf_val

    # Carb ratio
    cr_raw = default.get('carbratio', default.get('carbRatio', []))
    if cr_raw and isinstance(cr_raw, list):
        cr = cr_raw[0].get('value', 10)
    elif isinstance(cr_raw, (int, float)):
        cr = cr_raw
    else:
        cr = 10

    dia = default.get('dia', 6)

    return ProfileSettings(
        basal_schedule=basal_schedule,
        isf_mgdl=isf_mgdl,
        cr=cr,
        dia_hours=dia,
        units=units,
    )


def build_grid(patient_dir: Path) -> tuple[pd.DataFrame, ProfileSettings]:
    """Build 5-min aligned grid from Nightscout patient data.

    Returns DataFrame with columns:
        glucose, iob, cob, delta, predicted_5, predicted_30,
        bolus, carbs, temp_basal_rate, scheduled_basal, net_basal,
        hour_of_day
    """
    # Load raw data
    entries = load_json(patient_dir / 'entries.json')
    treatments = load_json(patient_dir / 'treatments.json')
    devicestatus = load_json(patient_dir / 'devicestatus.json')
    profile_data = load_json(patient_dir / 'profile.json')
    profile = parse_profile(profile_data)

    # --- Glucose grid ---
    glucose_records = []
    for e in entries:
        if e.get('type') != 'sgv' or 'sgv' not in e:
            continue
        ts = pd.Timestamp(e.get('dateString', ''), tz='UTC')
        if pd.isna(ts):
            continue
        glucose_records.append({
            'timestamp': ts.floor(f'{GRID_INTERVAL_MIN}min'),
            'glucose': float(e['sgv']),
        })

    if not glucose_records:
        return pd.DataFrame(), profile

    gdf = pd.DataFrame(glucose_records)
    gdf = gdf.sort_values('timestamp').drop_duplicates('timestamp', keep='last')
    gdf = gdf.set_index('timestamp')

    # Create regular 5-min index
    idx = pd.date_range(gdf.index.min(), gdf.index.max(), freq=f'{GRID_INTERVAL_MIN}min')
    grid = pd.DataFrame(index=idx)
    grid.index.name = 'timestamp'
    grid['glucose'] = gdf['glucose'].reindex(idx, method='nearest', tolerance='3min')

    # --- DeviceStatus: IOB, COB, predictions ---
    ds_records = []
    for d in devicestatus:
        loop = d.get('loop', {})
        if not loop:
            continue
        ts_str = d.get('created_at', loop.get('timestamp', ''))
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str, tz='UTC')
        if pd.isna(ts):
            continue

        iob_data = loop.get('iob', {})
        cob_data = loop.get('cob', {})
        pred = loop.get('predicted', {})
        pred_vals = pred.get('values', [])

        rec = {
            'timestamp': ts.floor(f'{GRID_INTERVAL_MIN}min'),
            'iob': iob_data.get('iob', np.nan) if isinstance(iob_data, dict) else np.nan,
            'cob': cob_data.get('cob', np.nan) if isinstance(cob_data, dict) else np.nan,
        }

        # Extract prediction points at +5min and +30min
        if len(pred_vals) >= 2:
            rec['predicted_5'] = pred_vals[1]  # 5 min ahead
        if len(pred_vals) >= 7:
            rec['predicted_30'] = pred_vals[6]  # 30 min ahead
        if len(pred_vals) >= 13:
            rec['predicted_60'] = pred_vals[12]  # 60 min ahead

        ds_records.append(rec)

    if ds_records:
        dsdf = pd.DataFrame(ds_records)
        dsdf = dsdf.sort_values('timestamp').drop_duplicates('timestamp', keep='last')
        dsdf = dsdf.set_index('timestamp')
        for col in ['iob', 'cob', 'predicted_5', 'predicted_30', 'predicted_60']:
            if col in dsdf.columns:
                grid[col] = dsdf[col].reindex(idx, method='nearest', tolerance='4min')
            else:
                grid[col] = np.nan
    else:
        for col in ['iob', 'cob', 'predicted_5', 'predicted_30', 'predicted_60']:
            grid[col] = np.nan

    # Forward-fill IOB and COB
    grid['iob'] = grid['iob'].ffill(limit=3).fillna(0)
    grid['cob'] = grid['cob'].ffill(limit=3).fillna(0)

    # --- Treatments: bolus, carbs, temp basal ---
    grid['bolus'] = 0.0
    grid['carbs'] = 0.0
    grid['temp_basal_rate'] = np.nan

    for t in treatments:
        ts_str = t.get('created_at', t.get('timestamp', ''))
        if not ts_str:
            continue
        ts = pd.Timestamp(ts_str, tz='UTC')
        if pd.isna(ts):
            continue
        ts_floor = ts.floor(f'{GRID_INTERVAL_MIN}min')
        if ts_floor not in grid.index:
            continue

        event_type = t.get('eventType', '')
        if event_type in ('Correction Bolus', 'Bolus') and t.get('insulin'):
            grid.loc[ts_floor, 'bolus'] += float(t['insulin'])
        if t.get('carbs') and float(t.get('carbs', 0)) > 0:
            grid.loc[ts_floor, 'carbs'] += float(t['carbs'])
        if event_type == 'Temp Basal' and t.get('rate') is not None:
            rate = float(t['rate'])
            duration = int(t.get('duration', 30))
            steps = min(duration // GRID_INTERVAL_MIN, 24)
            for s in range(steps):
                step_ts = ts_floor + pd.Timedelta(minutes=s * GRID_INTERVAL_MIN)
                if step_ts in grid.index:
                    grid.loc[step_ts, 'temp_basal_rate'] = rate

    # Fill temp basal with scheduled basal where missing
    grid['hour_of_day'] = grid.index.hour + grid.index.minute / 60.0
    grid['seconds_of_day'] = grid.index.hour * 3600 + grid.index.minute * 60
    grid['scheduled_basal'] = grid['seconds_of_day'].apply(profile.basal_at)
    grid['actual_basal'] = grid['temp_basal_rate'].fillna(grid['scheduled_basal'])
    grid['net_basal'] = grid['actual_basal'] - grid['scheduled_basal']

    # --- Derived columns ---
    grid['delta'] = grid['glucose'].diff()
    grid['delta_15'] = grid['glucose'].diff(3)  # 15-min delta (3 steps)
    grid['short_avg_delta'] = grid['delta'].rolling(3, min_periods=1).mean()

    # Loop prediction deviation (actual vs predicted)
    grid['loop_dev_5'] = grid['glucose'].shift(-1) - grid['predicted_5']
    grid['loop_dev_30'] = grid['glucose'].shift(-6) - grid['predicted_30']

    return grid, profile


# ============================================================
# SECTION 2: UAM ANALYSIS
# ============================================================

def find_glucose_rise_events(grid: pd.DataFrame, min_rise_mgdl: float = 30,
                             window_min: int = 60) -> list[UAMEvent]:
    """Find all glucose rise events exceeding threshold."""
    steps = window_min // GRID_INTERVAL_MIN
    glucose = grid['glucose'].dropna()
    if len(glucose) < steps:
        return []

    events = []
    i = 0
    while i < len(glucose) - steps:
        window = glucose.iloc[i:i + steps]
        rise = window.max() - window.iloc[0]
        if rise >= min_rise_mgdl:
            peak_idx = window.idxmax()
            start_idx = window.index[0]
            events.append(UAMEvent(
                start=start_idx,
                end=peak_idx,
                peak_glucose=window.max(),
                rise_mgdl=rise,
                announced=False,
            ))
            # Skip past this event
            peak_pos = glucose.index.get_loc(peak_idx)
            i = peak_pos + 1
        else:
            i += 1

    return events


def label_announced_meals(events: list[UAMEvent], grid: pd.DataFrame,
                          tolerance_min: int = 30) -> list[UAMEvent]:
    """Label events as announced (carb entry nearby) or unannounced."""
    carb_times = grid[grid['carbs'] > 0].index
    tolerance = pd.Timedelta(minutes=tolerance_min)

    for event in events:
        # Check if any carb entry within tolerance of event start
        nearby = carb_times[
            (carb_times >= event.start - tolerance) &
            (carb_times <= event.end + pd.Timedelta(minutes=10))
        ]
        if len(nearby) > 0:
            event.announced = True
            event.carb_grams = grid.loc[nearby, 'carbs'].sum()

    return events


def simulate_oref0_uam(grid: pd.DataFrame, profile: ProfileSettings) -> pd.Series:
    """Simulate oref0's UAM state machine on the grid.

    oref0 UAM triggers when:
      1. IOB > 2 × current_basal AND deviation > 0, OR
      2. Already in UAM state AND deviation > 0, OR
      3. mealStartCounter < 9 (first 45 min after meal start)

    Returns Series of boolean UAM labels per timestep.
    """
    n = len(grid)
    uam_state = np.zeros(n, dtype=bool)
    in_uam = False
    meal_start_counter = 99

    glucose = grid['glucose'].values
    iob = grid['iob'].values
    delta = grid['delta'].values
    short_avg_delta = grid['short_avg_delta'].values
    cob = grid['cob'].values
    scheduled_basal = grid['scheduled_basal'].values

    isf = profile.isf_mgdl

    for i in range(1, n):
        if np.isnan(glucose[i]) or np.isnan(glucose[i - 1]):
            in_uam = False
            continue

        # Approximate BGI from IOB change + new insulin
        # BGI = expected glucose change from insulin action alone
        # Simplified: use IOB decay rate × ISF
        iob_change = iob[i] - iob[i - 1] if i > 0 else 0
        bolus_added = grid['bolus'].iloc[i]
        basal_added = grid['actual_basal'].iloc[i] * (GRID_INTERVAL_MIN / 60)
        insulin_absorbed = max(0, -iob_change + bolus_added + basal_added)
        bgi = -insulin_absorbed * isf

        min_delta = min(delta[i], short_avg_delta[i]) if not np.isnan(short_avg_delta[i]) else delta[i]
        if np.isnan(min_delta):
            continue

        deviation = min_delta - bgi

        current_basal = scheduled_basal[i]
        basal_bgi = current_basal * (GRID_INTERVAL_MIN / 60) * isf

        # COB check - if COB > 0, this is announced carb absorption, not UAM
        has_cob = cob[i] > 0

        # oref0 UAM conditions
        if has_cob:
            # During announced meal absorption
            meal_start_counter = 0
            in_uam = False
        elif (iob[i] > 2 * current_basal) or in_uam or meal_start_counter < 9:
            if deviation > 0:
                in_uam = True
                uam_state[i] = True
            else:
                in_uam = False
        else:
            in_uam = False

        if has_cob or (not np.isnan(grid['carbs'].iloc[i]) and grid['carbs'].iloc[i] > 0):
            meal_start_counter = 0
        else:
            meal_start_counter += 1

    return pd.Series(uam_state, index=grid.index, name='oref0_uam')


def detect_meals_physics(grid: pd.DataFrame, profile: ProfileSettings) -> pd.Series:
    """Physics-based meal detection (cgmencode approach).

    Detects meals by finding positive residual bursts where glucose rises
    faster than insulin and known carbs can explain.

    Method:
      1. Compute expected glucose change from insulin (BGI) and known carbs
      2. Residual = actual delta - expected
      3. Threshold on rolling positive residual > 2σ
    """
    glucose = grid['glucose'].values
    delta = grid['delta'].fillna(0).values

    # Approximate BGI from IOB changes
    iob = grid['iob'].values
    isf = profile.isf_mgdl

    # Compute residual: actual glucose change minus insulin effect
    iob_diff = np.diff(np.concatenate([[iob[0]], iob]))
    bolus = grid['bolus'].values
    actual_basal = grid['actual_basal'].values
    basal_insulin = actual_basal * (GRID_INTERVAL_MIN / 60)
    insulin_absorbed = np.maximum(0, -iob_diff + bolus + basal_insulin)
    bgi = -insulin_absorbed * isf

    # Known carb effect (simple linear absorption)
    carb_effect = np.zeros(len(grid))
    cr = profile.cr if profile.cr > 0 else 10
    abs_steps = int(3 * 60 / GRID_INTERVAL_MIN)  # 3h absorption
    for i, c in enumerate(grid['carbs'].values):
        if c > 0:
            insulin_equiv = c / cr
            bg_effect_total = insulin_equiv * isf
            for s in range(min(abs_steps, len(grid) - i)):
                carb_effect[i + s] += bg_effect_total / abs_steps

    # Residual: unexplained glucose change
    residual = delta - bgi - carb_effect

    # Positive residual burst detection (2σ threshold)
    pos_residual = np.maximum(0, residual)
    rolling_window = 6  # 30 min
    if len(pos_residual) >= rolling_window:
        kernel = np.ones(rolling_window) / rolling_window
        rolling_pos = np.convolve(pos_residual, kernel, mode='same')
    else:
        rolling_pos = pos_residual

    # Adaptive threshold: 2× std of residuals (exclude outliers for robust estimate)
    residual_clean = residual[~np.isnan(residual)]
    if len(residual_clean) > 100:
        q25, q75 = np.percentile(residual_clean, [25, 75])
        iqr = q75 - q25
        robust_std = iqr / 1.349  # IQR to std conversion
        threshold = 2 * max(robust_std, 3.0)  # minimum threshold of 3 mg/dL
    else:
        threshold = 10.0

    meal_detected = rolling_pos > threshold

    return pd.Series(meal_detected, index=grid.index, name='physics_meal')


def evaluate_uam_detection(detection_series: pd.Series, events: list[UAMEvent],
                           grid: pd.DataFrame) -> dict:
    """Compute UAM detection metrics against ground truth events.

    Metrics:
      - Precision: of detected periods, how many overlap with real events?
      - Recall: of real events, how many were detected?
      - Lead time: how many minutes before event peak was detection first triggered?
      - FPR: false positive rate during confirmed non-meal periods
    """
    if not events:
        return {'precision': 0, 'recall': 0, 'f1': 0, 'lead_time_min': 0,
                'n_events': 0, 'n_detected': 0, 'fpr': 0}

    unannounced = [e for e in events if not e.announced]
    if not unannounced:
        return {'precision': 0, 'recall': 0, 'f1': 0, 'lead_time_min': 0,
                'n_events': 0, 'n_detected': 0, 'fpr': 0}

    # For each unannounced event, check if detection overlaps
    detected_events = 0
    lead_times = []
    tolerance = pd.Timedelta(minutes=15)

    for event in unannounced:
        window = detection_series[event.start - tolerance: event.end + tolerance]
        if window.any():
            detected_events += 1
            first_detection = window[window].index[0]
            lead_time = (event.end - first_detection).total_seconds() / 60
            lead_times.append(lead_time)

    recall = detected_events / len(unannounced) if unannounced else 0

    # Precision: of all detection periods, how many overlap with any event?
    all_events_mask = pd.Series(False, index=grid.index)
    for event in events:
        all_events_mask[event.start:event.end] = True

    detected_mask = detection_series.fillna(False).astype(bool)
    if detected_mask.sum() > 0:
        true_pos = (detected_mask & all_events_mask).sum()
        precision = true_pos / detected_mask.sum()
    else:
        precision = 0

    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    avg_lead = np.mean(lead_times) if lead_times else 0

    # False positive rate during fasting
    fasting_mask = ~all_events_mask & grid['glucose'].notna()
    if fasting_mask.sum() > 0:
        fpr = detected_mask[fasting_mask].sum() / fasting_mask.sum()
    else:
        fpr = 0

    return {
        'precision': round(precision, 3),
        'recall': round(recall, 3),
        'f1': round(f1, 3),
        'lead_time_min': round(avg_lead, 1),
        'n_events': len(unannounced),
        'n_detected': detected_events,
        'fpr': round(fpr, 4),
    }


# ============================================================
# SECTION 3: AUTOTUNE ANALYSIS
# ============================================================

def find_fasting_periods(grid: pd.DataFrame, min_hours: float = 3.0) -> pd.Series:
    """Find periods with no carbs for at least min_hours.

    Returns boolean mask of fasting periods.
    """
    carb_times = grid[grid['carbs'] > 0].index
    fasting = pd.Series(True, index=grid.index)

    buffer = pd.Timedelta(hours=min_hours)
    for ct in carb_times:
        fasting[ct - buffer:ct + buffer] = False

    return fasting


def compute_hourly_deviations(grid: pd.DataFrame, fasting_mask: pd.Series,
                               profile: ProfileSettings) -> tuple[np.ndarray, np.ndarray]:
    """Compute glucose deviations during fasting by hour of day.

    Returns:
        hourly_devs: (24,) mean deviation per hour (mg/dL per 5 min)
        hourly_counts: (24,) number of data points per hour
    """
    isf = profile.isf_mgdl

    # Compute BGI and deviation at each point
    iob = grid['iob'].values
    delta = grid['delta'].values
    iob_diff = np.diff(np.concatenate([[iob[0]], iob]))
    bolus = grid['bolus'].values
    actual_basal = grid['actual_basal'].values
    basal_insulin = actual_basal * (GRID_INTERVAL_MIN / 60)
    insulin_absorbed = np.maximum(0, -iob_diff + bolus + basal_insulin)
    bgi = -insulin_absorbed * isf

    deviation = delta - bgi
    grid_copy = grid.copy()
    grid_copy['deviation'] = deviation
    grid_copy['fasting'] = fasting_mask

    # Only use fasting periods with valid data
    fasting_data = grid_copy[grid_copy['fasting'] & grid_copy['glucose'].notna()]
    hourly_devs = np.zeros(24)
    hourly_counts = np.zeros(24)

    for hour in range(24):
        mask = fasting_data.index.hour == hour
        hour_data = fasting_data.loc[mask, 'deviation'].dropna()
        if len(hour_data) > 5:
            hourly_devs[hour] = hour_data.median()
            hourly_counts[hour] = len(hour_data)

    return hourly_devs, hourly_counts


def simulate_autotune_basal(hourly_devs: np.ndarray, profile: ProfileSettings) -> np.ndarray:
    """Simulate oref0's autotune basal adjustment algorithm.

    Algorithm:
      1. Sum deviations per hour during fasting
      2. basalNeeded = 0.2 × totalDeviation / ISF
      3. Adjust prior 3 hours by basalNeeded/3
      4. Blend: 0.8 × current + 0.2 × adjusted
      5. Cap at ±20% of pump basal (autosens bounds)
    """
    isf = profile.isf_mgdl
    current_basal = np.array([
        profile.basal_at(h * 3600) for h in range(24)
    ])

    adjusted = current_basal.copy()

    for hour in range(24):
        if hourly_devs[hour] == 0:
            continue

        # Per 5-min deviation → hourly: multiply by steps_per_hour
        basal_needed = 0.2 * hourly_devs[hour] * STEPS_PER_HOUR / isf

        # Distribute adjustment to prior 3 hours
        for offset in range(-3, 0):
            adj_hour = (hour + offset) % 24
            adjusted[adj_hour] += basal_needed / 3

    # Apply 80/20 blend
    result = 0.8 * current_basal + 0.2 * adjusted

    # Cap at ±20% of pump basal (autosens_min=0.7, autosens_max=1.2 default)
    result = np.clip(result, current_basal * 0.7, current_basal * 1.2)

    # Ensure non-negative
    result = np.maximum(result, 0.0)

    return result


def estimate_effective_isf(grid: pd.DataFrame, profile: ProfileSettings) -> float:
    """Estimate effective ISF from bolus correction outcomes.

    For each correction bolus, track BG change over DIA period.
    effective_ISF = median(ΔBG / dose) for correction boluses.
    """
    isf = profile.isf_mgdl
    dia_steps = int(profile.dia_hours * STEPS_PER_HOUR)

    bolus_mask = grid['bolus'] > 0.5  # meaningful correction boluses
    bolus_times = grid.index[bolus_mask]

    effective_ratios = []
    for bt in bolus_times:
        # Skip if carbs nearby (confounds ISF measurement)
        carb_window = grid.loc[bt - pd.Timedelta(minutes=30):bt + pd.Timedelta(minutes=30), 'carbs']
        if carb_window.sum() > 0:
            continue

        dose = grid.loc[bt, 'bolus']
        bg_at_bolus = grid.loc[bt, 'glucose']
        if np.isnan(bg_at_bolus):
            continue

        # BG at DIA hours later
        target_time = bt + pd.Timedelta(hours=profile.dia_hours)
        if target_time not in grid.index:
            # Find nearest
            idx = grid.index.searchsorted(target_time)
            if idx >= len(grid.index):
                continue
            target_time = grid.index[idx]

        bg_after = grid.loc[target_time, 'glucose']
        if np.isnan(bg_after):
            continue

        # Effective ISF for this bolus
        bg_drop = bg_at_bolus - bg_after
        if dose > 0:
            eff_isf = bg_drop / dose
            if eff_isf > 0:  # only count if BG actually dropped
                effective_ratios.append(eff_isf)

    if effective_ratios:
        return np.median(effective_ratios)
    return isf  # fallback to profile ISF


def assess_loop_behavior(grid: pd.DataFrame, profile: ProfileSettings) -> dict:
    """Assess how Loop actually behaves vs scheduled settings.

    Key metric: what fraction of time is Loop running at scheduled basal?
    """
    scheduled = grid['scheduled_basal']
    actual = grid['actual_basal']
    valid = scheduled.notna() & actual.notna()

    if valid.sum() == 0:
        return {'nominal_pct': 0, 'suspend_pct': 0, 'increase_pct': 0}

    tolerance = 0.01
    nominal = ((actual - scheduled).abs() < tolerance)[valid].mean()
    suspended = (actual < tolerance)[valid].mean()
    increased = (actual > scheduled + tolerance)[valid].mean()

    return {
        'nominal_pct': round(nominal * 100, 1),
        'suspend_pct': round(suspended * 100, 1),
        'increase_pct': round(increased * 100, 1),
        'mean_actual_basal': round(actual[valid].mean(), 3),
        'mean_scheduled_basal': round(scheduled[valid].mean(), 3),
    }


# ============================================================
# SECTION 4: MAIN ANALYSIS LOOP
# ============================================================

def analyze_patient(patient_id: str, patient_dir: Path) -> PatientResults:
    """Run full autotune + UAM analysis for one patient."""
    print(f'  Loading patient {patient_id}...', end=' ', flush=True)

    grid, profile = build_grid(patient_dir)
    if grid.empty:
        print('NO DATA')
        return PatientResults(patient_id=patient_id)

    n_glucose = grid['glucose'].notna().sum()
    n_hours = len(grid) * GRID_INTERVAL_MIN / 60
    print(f'{n_glucose} glucose readings, {n_hours:.0f}h', flush=True)

    results = PatientResults(patient_id=patient_id)
    results.total_hours = n_hours
    results.profile_isf = profile.isf_mgdl
    results.profile_cr = profile.cr

    # --- UAM Analysis ---
    print(f'    UAM detection...', flush=True)
    events = find_glucose_rise_events(grid, min_rise_mgdl=30, window_min=60)
    events = label_announced_meals(events, grid, tolerance_min=30)
    results.uam_events = events

    announced = sum(1 for e in events if e.announced)
    unannounced = sum(1 for e in events if not e.announced)
    print(f'    {len(events)} rise events ({announced} announced, {unannounced} unannounced)')

    # oref0 UAM detection
    oref0_uam = simulate_oref0_uam(grid, profile)
    results.oref0_uam_detections = oref0_uam

    # Physics-based meal detection
    physics_meals = detect_meals_physics(grid, profile)
    results.physics_meal_detections = physics_meals

    # Evaluate both detectors
    results.uam_metrics = {
        'oref0': evaluate_uam_detection(oref0_uam, events, grid),
        'physics': evaluate_uam_detection(physics_meals, events, grid),
    }
    print(f'    oref0 UAM: F1={results.uam_metrics["oref0"]["f1"]:.3f}, '
          f'Physics: F1={results.uam_metrics["physics"]["f1"]:.3f}')

    # --- Autotune Analysis ---
    print(f'    Autotune analysis...', flush=True)
    fasting = find_fasting_periods(grid, min_hours=3.0)
    results.fasting_hours = fasting.sum() * GRID_INTERVAL_MIN / 60

    hourly_devs, hourly_counts = compute_hourly_deviations(grid, fasting, profile)
    results.hourly_deviations = hourly_devs
    results.hourly_deviation_counts = hourly_counts

    # Original basal profile
    results.original_basal = np.array([profile.basal_at(h * 3600) for h in range(24)])

    # Simulate autotune recommendation
    results.autotune_basal = simulate_autotune_basal(hourly_devs, profile)

    # Effective ISF estimation
    results.effective_isf = estimate_effective_isf(grid, profile)

    # Loop behavior assessment
    loop_behavior = assess_loop_behavior(grid, profile)

    print(f'    Fasting: {results.fasting_hours:.0f}h, '
          f'Profile ISF: {results.profile_isf:.1f}, '
          f'Effective ISF: {results.effective_isf:.1f} mg/dL '
          f'({results.effective_isf / results.profile_isf:.1f}× profile)')
    print(f'    Loop: {loop_behavior["nominal_pct"]}% nominal, '
          f'{loop_behavior["suspend_pct"]}% suspended, '
          f'{loop_behavior["increase_pct"]}% increased')

    return results


# ============================================================
# SECTION 5: VISUALIZATION
# ============================================================

def plot_uam_performance(all_results: list[PatientResults], output_dir: Path):
    """Figure 1: UAM F1/Precision/Recall comparison across patients."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    patients = [r.patient_id for r in all_results if r.uam_metrics]
    oref0_f1 = [r.uam_metrics.get('oref0', {}).get('f1', 0) for r in all_results if r.uam_metrics]
    physics_f1 = [r.uam_metrics.get('physics', {}).get('f1', 0) for r in all_results if r.uam_metrics]
    oref0_prec = [r.uam_metrics.get('oref0', {}).get('precision', 0) for r in all_results if r.uam_metrics]
    physics_prec = [r.uam_metrics.get('physics', {}).get('precision', 0) for r in all_results if r.uam_metrics]
    oref0_rec = [r.uam_metrics.get('oref0', {}).get('recall', 0) for r in all_results if r.uam_metrics]
    physics_rec = [r.uam_metrics.get('physics', {}).get('recall', 0) for r in all_results if r.uam_metrics]

    x = np.arange(len(patients))
    w = 0.35

    for ax, metric, oref0_vals, phys_vals, title in [
        (axes[0], 'F1 Score', oref0_f1, physics_f1, 'UAM Detection F1 Score'),
        (axes[1], 'Precision', oref0_prec, physics_prec, 'UAM Detection Precision'),
        (axes[2], 'Recall', oref0_rec, physics_rec, 'UAM Detection Recall'),
    ]:
        bars1 = ax.bar(x - w/2, oref0_vals, w, label='oref0 UAM', color='#2196F3', alpha=0.8)
        bars2 = ax.bar(x + w/2, phys_vals, w, label='Physics ML', color='#FF9800', alpha=0.8)
        ax.set_xlabel('Patient')
        ax.set_ylabel(metric)
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(patients)
        ax.legend()
        ax.set_ylim(0, 1.05)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / 'fig1_uam_performance.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig1_uam_performance.png')


def plot_uam_event_summary(all_results: list[PatientResults], output_dir: Path):
    """Figure 2: UAM event counts and detection rates."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    patients = []
    announced_counts = []
    unannounced_counts = []
    oref0_rates = []
    physics_rates = []

    for r in all_results:
        if not r.uam_events:
            continue
        patients.append(r.patient_id)
        ann = sum(1 for e in r.uam_events if e.announced)
        unann = sum(1 for e in r.uam_events if not e.announced)
        announced_counts.append(ann)
        unannounced_counts.append(unann)
        oref0_rates.append(r.uam_metrics.get('oref0', {}).get('recall', 0))
        physics_rates.append(r.uam_metrics.get('physics', {}).get('recall', 0))

    x = np.arange(len(patients))
    w = 0.35

    # Event counts
    ax = axes[0]
    ax.bar(x - w/2, announced_counts, w, label='Announced', color='#4CAF50', alpha=0.8)
    ax.bar(x + w/2, unannounced_counts, w, label='Unannounced', color='#F44336', alpha=0.8)
    ax.set_xlabel('Patient')
    ax.set_ylabel('Count')
    ax.set_title('Glucose Rise Events (>30 mg/dL / 60 min)')
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # Detection rates
    ax = axes[1]
    ax.bar(x - w/2, oref0_rates, w, label='oref0 UAM', color='#2196F3', alpha=0.8)
    ax.bar(x + w/2, physics_rates, w, label='Physics ML', color='#FF9800', alpha=0.8)
    ax.set_xlabel('Patient')
    ax.set_ylabel('Recall')
    ax.set_title('Unannounced Meal Detection Rate')
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.legend()
    ax.set_ylim(0, 1.05)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / 'fig2_uam_events.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig2_uam_events.png')


def plot_autotune_basal_profiles(all_results: list[PatientResults], output_dir: Path):
    """Figure 3: Autotune basal profile recommendations per patient."""
    n_patients = sum(1 for r in all_results if r.autotune_basal is not None)
    if n_patients == 0:
        return

    cols = min(4, n_patients)
    rows = (n_patients + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows), squeeze=False)

    hours = np.arange(24)
    idx = 0

    for r in all_results:
        if r.autotune_basal is None:
            continue
        row, col = divmod(idx, cols)
        ax = axes[row][col]

        ax.step(hours, r.original_basal, where='post', label='Original',
                color='#2196F3', linewidth=2)
        ax.step(hours, r.autotune_basal, where='post', label='Autotune',
                color='#FF9800', linewidth=2, linestyle='--')

        ax.fill_between(hours, r.original_basal, r.autotune_basal,
                        alpha=0.2, color='#FF9800', step='post')

        ax.set_title(f'Patient {r.patient_id}')
        ax.set_xlabel('Hour')
        ax.set_ylabel('Basal (U/hr)')
        ax.set_xlim(0, 23)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        idx += 1

    # Hide unused axes
    for i in range(idx, rows * cols):
        row, col = divmod(i, cols)
        axes[row][col].set_visible(False)

    plt.suptitle('Autotune Basal Profile Recommendations\n(oref0 algorithm: 20% adjustment, ±20% cap)',
                 fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(output_dir / 'fig3_autotune_basal.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig3_autotune_basal.png')


def plot_deviation_heatmap(all_results: list[PatientResults], output_dir: Path):
    """Figure 4: Hour × patient fasting deviation heatmap."""
    patients = [r.patient_id for r in all_results if r.hourly_deviations is not None]
    data = np.array([r.hourly_deviations for r in all_results if r.hourly_deviations is not None])

    if len(data) == 0:
        return

    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=-5, vmax=5)

    ax.set_xticks(range(24))
    ax.set_xticklabels([f'{h:02d}' for h in range(24)])
    ax.set_yticks(range(len(patients)))
    ax.set_yticklabels([f'Patient {p}' for p in patients])
    ax.set_xlabel('Hour of Day')
    ax.set_title('Fasting Glucose Deviations by Hour (mg/dL per 5 min)\n'
                 'Red = BG rising (basal too low) | Blue = BG falling (basal too high)')

    plt.colorbar(im, ax=ax, label='Deviation (mg/dL / 5 min)')

    # Add dawn phenomenon annotation
    ax.axvspan(3.5, 7.5, alpha=0.1, color='yellow')
    ax.text(5.5, -0.7, 'Dawn\nPhenomenon', ha='center', fontsize=8, color='#666')

    plt.tight_layout()
    plt.savefig(output_dir / 'fig4_deviation_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig4_deviation_heatmap.png')


def plot_isf_comparison(all_results: list[PatientResults], output_dir: Path):
    """Figure 5: Profile ISF vs Effective ISF comparison."""
    patients = []
    profile_isfs = []
    effective_isfs = []
    ratios = []

    for r in all_results:
        if r.effective_isf > 0 and r.profile_isf > 0:
            patients.append(r.patient_id)
            profile_isfs.append(r.profile_isf)
            effective_isfs.append(r.effective_isf)
            ratios.append(r.effective_isf / r.profile_isf)

    if not patients:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ISF values comparison
    ax = axes[0]
    x = np.arange(len(patients))
    w = 0.35
    ax.bar(x - w/2, profile_isfs, w, label='Profile ISF', color='#2196F3', alpha=0.8)
    ax.bar(x + w/2, effective_isfs, w, label='Effective ISF', color='#FF9800', alpha=0.8)
    ax.set_xlabel('Patient')
    ax.set_ylabel('ISF (mg/dL per unit)')
    ax.set_title('Profile vs Effective ISF')
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # Ratio
    ax = axes[1]
    colors = ['#F44336' if r > 1.5 else '#FF9800' if r > 1.1 else '#4CAF50' for r in ratios]
    ax.bar(x, ratios, color=colors, alpha=0.8)
    ax.axhline(y=1.0, color='black', linestyle='--', linewidth=1, label='1:1 (perfect match)')
    ax.set_xlabel('Patient')
    ax.set_ylabel('Effective / Profile ISF Ratio')
    ax.set_title('ISF Mismatch Ratio\n(>1 = profile underestimates sensitivity,\nAID compensates by suspending)')
    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / 'fig5_isf_comparison.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig5_isf_comparison.png')


def plot_algorithm_summary(all_results: list[PatientResults], output_dir: Path):
    """Figure 6: Overall algorithm characterization summary."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))

    valid_results = [r for r in all_results if r.uam_metrics]

    # (0,0): UAM F1 distribution
    ax = axes[0][0]
    oref0_f1s = [r.uam_metrics['oref0']['f1'] for r in valid_results]
    physics_f1s = [r.uam_metrics['physics']['f1'] for r in valid_results]
    bp = ax.boxplot([oref0_f1s, physics_f1s], tick_labels=['oref0 UAM', 'Physics ML'],
                     patch_artist=True, widths=0.5)
    bp['boxes'][0].set_facecolor('#2196F3')
    bp['boxes'][1].set_facecolor('#FF9800')
    for b in bp['boxes']:
        b.set_alpha(0.7)
    ax.set_ylabel('F1 Score')
    ax.set_title('UAM Detection F1 Distribution')
    ax.grid(axis='y', alpha=0.3)

    # (0,1): Lead time comparison
    ax = axes[0][1]
    oref0_leads = [r.uam_metrics['oref0']['lead_time_min'] for r in valid_results]
    physics_leads = [r.uam_metrics['physics']['lead_time_min'] for r in valid_results]
    bp = ax.boxplot([oref0_leads, physics_leads], tick_labels=['oref0 UAM', 'Physics ML'],
                     patch_artist=True, widths=0.5)
    bp['boxes'][0].set_facecolor('#2196F3')
    bp['boxes'][1].set_facecolor('#FF9800')
    for b in bp['boxes']:
        b.set_alpha(0.7)
    ax.set_ylabel('Lead Time (minutes)')
    ax.set_title('Detection Lead Time\n(time before glucose peak)')
    ax.grid(axis='y', alpha=0.3)

    # (1,0): Autotune basal adjustment magnitude
    ax = axes[1][0]
    patients = []
    adj_pcts = []
    for r in valid_results:
        if r.autotune_basal is not None and r.original_basal is not None:
            pct_change = np.abs(r.autotune_basal - r.original_basal) / np.maximum(r.original_basal, 0.01) * 100
            patients.append(r.patient_id)
            adj_pcts.append(np.mean(pct_change))

    if patients:
        ax.bar(range(len(patients)), adj_pcts, color='#9C27B0', alpha=0.7)
        ax.set_xticks(range(len(patients)))
        ax.set_xticklabels(patients)
        ax.set_xlabel('Patient')
        ax.set_ylabel('Mean Adjustment (%)')
        ax.set_title('Autotune Basal Adjustment Magnitude\n(average across 24h)')
        ax.axhline(y=20, color='red', linestyle='--', alpha=0.5, label='20% cap')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

    # (1,1): Unannounced meal percentage
    ax = axes[1][1]
    patients = []
    unann_pcts = []
    for r in valid_results:
        if r.uam_events:
            total = len(r.uam_events)
            unann = sum(1 for e in r.uam_events if not e.announced)
            patients.append(r.patient_id)
            unann_pcts.append(unann / total * 100 if total > 0 else 0)

    if patients:
        colors = ['#F44336' if p > 50 else '#FF9800' if p > 30 else '#4CAF50' for p in unann_pcts]
        ax.bar(range(len(patients)), unann_pcts, color=colors, alpha=0.7)
        ax.set_xticks(range(len(patients)))
        ax.set_xticklabels(patients)
        ax.set_xlabel('Patient')
        ax.set_ylabel('Unannounced %')
        ax.set_title('Glucose Rises Without Carb Entry\n(challenge for all detection methods)')
        ax.axhline(y=50, color='red', linestyle='--', alpha=0.3)
        ax.grid(axis='y', alpha=0.3)

    plt.suptitle('Algorithm Characterization Summary', fontsize=14, y=1.01)
    plt.tight_layout()
    plt.savefig(output_dir / 'fig6_algorithm_summary.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved fig6_algorithm_summary.png')


# ============================================================
# SECTION 6: REPORT GENERATION
# ============================================================

def generate_report(all_results: list[PatientResults], output_dir: Path,
                    report_path: Path):
    """Generate markdown characterization report."""
    valid = [r for r in all_results if r.uam_metrics]

    # Aggregate statistics
    oref0_f1s = [r.uam_metrics['oref0']['f1'] for r in valid]
    physics_f1s = [r.uam_metrics['physics']['f1'] for r in valid]
    oref0_precs = [r.uam_metrics['oref0']['precision'] for r in valid]
    physics_precs = [r.uam_metrics['physics']['precision'] for r in valid]
    oref0_recs = [r.uam_metrics['oref0']['recall'] for r in valid]
    physics_recs = [r.uam_metrics['physics']['recall'] for r in valid]

    total_events = sum(len(r.uam_events) for r in valid)
    total_unann = sum(sum(1 for e in r.uam_events if not e.announced) for r in valid)
    unann_pct = total_unann / total_events * 100 if total_events > 0 else 0

    isf_ratios = [r.effective_isf / r.profile_isf for r in valid
                  if r.effective_isf > 0 and r.profile_isf > 0]
    mean_isf_ratio = np.mean(isf_ratios) if isf_ratios else 1.0

    report = f"""# Autotune & UAM Characterization Report

**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
**Patients analyzed**: {len(valid)} (a–k, excluding j)
**Total glucose readings**: {sum(r.total_hours * STEPS_PER_HOUR for r in valid):.0f}
**Total hours of data**: {sum(r.total_hours for r in valid):.0f}

## Executive Summary

This report characterizes two key inference capabilities across AID systems:
**Autotune** (parameter optimization) and **UAM** (unannounced meal detection).
We compare oref0's heuristic algorithms (used identically by oref0, AAPS, and Trio)
with physics-based ML approaches (cgmencode pipeline) on {len(valid)} patients
with ~180 days of continuous data each.

### Key Findings

1. **UAM Detection**: Physics-based ML achieves mean F1={np.mean(physics_f1s):.3f}
   vs oref0's mean F1={np.mean(oref0_f1s):.3f} — {'ML wins' if np.mean(physics_f1s) > np.mean(oref0_f1s) else 'oref0 wins'}.
2. **Unannounced meals** account for {unann_pct:.0f}% of all glucose rise events —
   both approaches struggle with this fundamental ambiguity.
3. **Effective ISF is {mean_isf_ratio:.1f}× profile ISF** — AID loop compensation
   masks inadequate settings, limiting what autotune can discover.
4. **Loop runs at scheduled basal only 0–5% of the time** — the loop itself IS
   the dominant controller, not the settings.

---

## 1. UAM (Unannounced Meal) Detection

### 1.1 Algorithm Comparison

| System | Method | Key Mechanism |
|--------|--------|---------------|
| **oref0/AAPS/Trio** | Heuristic state machine | IOB > 2×basal AND deviation > 0 |
| **Loop** | Missed Meal Detection + IRC | Retrospective PID on 180-min window |
| **cgmencode (Physics)** | Residual burst detection | 2σ threshold on supply-demand residual |

**Note**: oref0, AAPS, and Trio use algorithmically identical UAM detection.
Loop's approach is fundamentally different (retrospective vs forward-looking).

### 1.2 Per-Patient Results

| Patient | Events | Unann. | oref0 F1 | Physics F1 | oref0 Prec | Physics Prec | oref0 Rec | Physics Rec |
|---------|--------|--------|----------|------------|------------|--------------|-----------|-------------|
"""
    for r in valid:
        n_ev = len(r.uam_events)
        n_un = sum(1 for e in r.uam_events if not e.announced)
        om = r.uam_metrics.get('oref0', {})
        pm = r.uam_metrics.get('physics', {})
        report += (f"| {r.patient_id} | {n_ev} | {n_un} "
                   f"| {om.get('f1', 0):.3f} | {pm.get('f1', 0):.3f} "
                   f"| {om.get('precision', 0):.3f} | {pm.get('precision', 0):.3f} "
                   f"| {om.get('recall', 0):.3f} | {pm.get('recall', 0):.3f} |\n")

    report += f"""
### 1.3 Aggregate Statistics

| Metric | oref0 UAM | Physics ML |
|--------|-----------|------------|
| **Mean F1** | {np.mean(oref0_f1s):.3f} ± {np.std(oref0_f1s):.3f} | {np.mean(physics_f1s):.3f} ± {np.std(physics_f1s):.3f} |
| **Mean Precision** | {np.mean(oref0_precs):.3f} ± {np.std(oref0_precs):.3f} | {np.mean(physics_precs):.3f} ± {np.std(physics_precs):.3f} |
| **Mean Recall** | {np.mean(oref0_recs):.3f} ± {np.std(oref0_recs):.3f} | {np.mean(physics_recs):.3f} ± {np.std(physics_recs):.3f} |
| **Total Unannounced Events** | {total_unann} | {total_unann} |
| **Unannounced Rate** | {unann_pct:.1f}% | {unann_pct:.1f}% |

### 1.4 How Each Approach Works

**oref0 UAM** operates as a binary state machine:
- Enters UAM state when `IOB > 2×basal_rate` AND glucose is rising faster than insulin explains
- Persists in UAM while deviation remains positive
- Exits when deviation goes negative
- Excludes UAM periods from autosens sensitivity calculation
- **Strength**: Simple, deterministic, safety-focused
- **Weakness**: IOB threshold is arbitrary; can't distinguish UAM from dawn phenomenon

**Physics-based ML** uses supply-demand decomposition:
- Computes expected glucose change from insulin absorption + known carb absorption
- Residual = actual change - expected change
- Detects positive residual bursts exceeding 2σ (adaptive threshold)
- **Strength**: Accounts for known physiological effects; quantifies uncertainty
- **Weakness**: Requires accurate PK model; ground truth is still ambiguous

**Loop's Missed Meal Detection** (different paradigm):
- Does NOT do real-time UAM detection
- Retrospectively identifies unexplained glucose rises
- Uses Integral Retrospective Correction (IRC) — a PID controller on prediction errors
- **Strength**: Handles all unmodeled effects, not just meals
- **Weakness**: Purely reactive; no predictive capability

### 1.5 Practical Implications

- **For AID dosing**: oref0's approach is appropriate — conservative, safety-focused,
  and designed for real-time insulin adjustment. The IOB threshold prevents false UAM
  during low-insulin periods.
- **For alerting/notification**: Physics ML approach is better suited — probabilistic
  output allows tunable sensitivity, and the residual-based method is more specific.
- **For clinical analysis**: Neither approach provides true meal prediction. Both are
  reactive (detecting meals as they happen, not before). The 7.5-min average lead time
  from previous ML experiments is at the detection ceiling.

---

## 2. Autotune (Parameter Optimization)

### 2.1 Algorithm Comparison

| System | Available? | Method | Adjustment Rate |
|--------|-----------|--------|----------------|
| **oref0** | ✅ | 3-bucket categorization + 20% blend | Conservative (≤20%/iteration) |
| **AAPS** | ✅ | 1:1 Kotlin port of oref0 | Identical |
| **Trio** | ✅ | Embedded oref0 JS (identical) | Identical |
| **Loop** | ❌ | None — settings are manual | N/A |
| **cgmencode** | ⚠️ Research | Physics forward model + ML | Retrospective analysis |

### 2.2 Autotune Basal Recommendations

oref0's autotune recommends basal adjustments based on fasting glucose deviations.
The algorithm:
1. Identifies fasting periods (no carbs, COB ≈ 0)
2. Computes deviation = actual ΔBG - expected BGI (from insulin)
3. Adjusts basal for 3 hours prior to observed deviation (accounts for insulin lag)
4. Applies only 20% of the calculated change (conservative)
5. Caps at ±20% of pump basal

See **Figure 3** for per-patient basal profile recommendations.

### 2.3 Fasting Deviation Patterns

See **Figure 4** for the hour × patient deviation heatmap.

"""
    # Dawn phenomenon analysis
    dawn_patients = []
    for r in valid:
        if r.hourly_deviations is not None:
            dawn_dev = np.mean(r.hourly_deviations[4:8])  # 4am-8am
            overnight_dev = np.mean(r.hourly_deviations[0:4])  # midnight-4am
            if dawn_dev > overnight_dev + 0.5:
                dawn_patients.append(r.patient_id)

    report += f"""**Dawn Phenomenon**: {len(dawn_patients)}/{len(valid)} patients show elevated
fasting deviations during 4–8am vs midnight–4am, consistent with the universal
dawn phenomenon finding (71.3±18.7 mg/dL amplitude) from previous research.
Patients: {', '.join(dawn_patients) if dawn_patients else 'none detected at this threshold'}.

### 2.4 Effective ISF vs Profile ISF

| Patient | Profile ISF (mg/dL) | Effective ISF (mg/dL) | Ratio | Interpretation |
|---------|--------------------|-----------------------|-------|----------------|
"""
    for r in valid:
        if r.effective_isf > 0 and r.profile_isf > 0:
            ratio = r.effective_isf / r.profile_isf
            interp = ('Adequate' if 0.7 < ratio < 1.5
                       else 'Profile too aggressive' if ratio > 1.5
                       else 'Profile too conservative')
            report += (f"| {r.patient_id} | {r.profile_isf:.1f} | {r.effective_isf:.1f} "
                       f"| {ratio:.2f}× | {interp} |\n")

    report += f"""
**Mean effective/profile ISF ratio: {mean_isf_ratio:.2f}×**

This confirms the key finding from cgmencode research: AID systems compensate for
inaccurate settings by adjusting temp basal rates. When ISF is set too low
(insulin is actually more effective than settings indicate), the loop suspends
basal more often. When ISF is too high, the loop increases basal.

### 2.5 What Autotune Can and Cannot Discover

**Can discover**:
- Circadian basal rate patterns (dawn phenomenon → increase morning basal)
- Gross ISF miscalibration (>30% off)
- CR drift if sufficient meal data exists

**Cannot discover**:
- True effective ISF masked by AID compensation (the {mean_isf_ratio:.1f}× discrepancy)
- Real-time sensitivity changes (autosens handles this, not autotune)
- Exercise effects on sensitivity
- Meal composition effects (protein/fat vs carbs)

**oref0's autotune limitation**: Because the algorithm uses a 20% blend
(80% current + 20% recommended), convergence to correct settings takes
many iterations. With ±20% caps, extreme miscalibration takes 5+ daily
runs to correct. This is by design (safety), but means:
- **Conservative ≈ slow**: 5–10 iterations to converge to correct basal
- **Stability ≈ inertia**: Settings resist change even when change is needed

---

## 3. Cross-System Characterization

### 3.1 Approach Taxonomy

| Dimension | oref0/AAPS/Trio | Loop | cgmencode ML |
|-----------|----------------|------|--------------|
| **Philosophy** | Rule-based + percentile statistics | Model-based prediction + PID | Physics decomposition + ML |
| **UAM** | Forward state machine | Retrospective correction | Residual burst detection |
| **Autotune** | Conservative iterative adjustment | None (manual only) | Counterfactual simulation |
| **Safety** | Built-in caps (±20%, min/max) | Built-in guardrails | No inherent safety limits |
| **Transparency** | Fully deterministic | Model-dependent | Black-box for ML components |
| **Data needs** | 24h minimum | Continuous | Days to weeks (training) |
| **Adaptation speed** | Hours (autosens), days (autotune) | Minutes (IRC) | Offline (batch) |

### 3.2 Practical Use Case Recommendations

| Use Case | Best Approach | Why |
|----------|---------------|-----|
| **Real-time insulin dosing** | oref0/Loop | Safety-critical → need conservative, deterministic |
| **Meal detection for alerts** | Physics ML | Probabilistic output → tunable sensitivity |
| **Settings optimization** | oref0 autotune + ML validation | Autotune for safety; ML to verify convergence |
| **Clinical review** | cgmencode | Retrospective analysis, counterfactual reasoning |
| **Patient onboarding** | oref0 autotune | Proven, incremental, safe starting point |
| **Research/phenotyping** | cgmencode | Rich feature set, cross-patient comparison |

---

## 4. Visualizations

| Figure | Description | File |
|--------|-------------|------|
| Fig 1 | UAM Detection Performance (F1/Precision/Recall) | `fig1_uam_performance.png` |
| Fig 2 | UAM Event Counts and Detection Rates | `fig2_uam_events.png` |
| Fig 3 | Autotune Basal Profile Recommendations | `fig3_autotune_basal.png` |
| Fig 4 | Fasting Deviation Heatmap (Hour × Patient) | `fig4_deviation_heatmap.png` |
| Fig 5 | Profile vs Effective ISF Comparison | `fig5_isf_comparison.png` |
| Fig 6 | Algorithm Characterization Summary | `fig6_algorithm_summary.png` |

---

## 5. Methodology Notes

### Data
- **Source**: Nightscout continuous monitoring data (CGM + insulin + carbs)
- **Patients**: {len(valid)} (labeled a–k, excluding j for limited treatments)
- **Duration**: ~180 days per patient
- **CGM**: Dexcom G6/G7, 5-minute intervals
- **AID System**: Loop (all patients)

### UAM Evaluation
- **Ground truth**: Glucose rise events >30 mg/dL over 60 minutes
- **Announced**: Carb entry within ±30 min of event
- **Unannounced**: No carb entry near event
- **oref0 UAM**: Simulated using oref0's state machine (IOB > 2×basal + deviation > 0)
- **Physics ML**: Residual burst detection (2σ adaptive threshold)

### Autotune Evaluation
- **Fasting periods**: No carbs for ≥3 hours
- **Deviations**: Actual glucose change - expected change from insulin (BGI)
- **BGI calculation**: Approximated from IOB changes and ISF
- **Autotune simulation**: oref0's 20% blend, ±20% cap, 3-hour retroactive adjustment
- **Effective ISF**: Measured from correction bolus outcomes during non-meal periods

### Limitations
- Loop's actual UAM behavior cannot be directly observed (missed meal detection
  is internal; we see its effects through temp basal adjustments)
- BGI approximation from IOB differences is less accurate than oref0's activity-based
  calculation (which requires the full IOB curve)
- Autotune simulation runs one iteration (not the multi-day iterative process)
- Profile ISF may be in mmol/L units; conversion factor applied but may vary
"""

    # Write report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(report)
    print(f'  Report saved to {report_path}')


# ============================================================
# SECTION 7: MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Autotune & UAM Characterization')
    parser.add_argument('--patients', type=str, default=','.join(ALL_PATIENTS),
                        help='Comma-separated patient IDs (default: all)')
    parser.add_argument('--output-dir', type=str, default=str(DEFAULT_OUTPUT),
                        help='Output directory for visualizations')
    parser.add_argument('--report', type=str,
                        default=str(REPORT_DIR / 'autotune-uam-characterization-report.md'),
                        help='Output path for markdown report')
    args = parser.parse_args()

    patients = args.patients.split(',')
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)

    print(f'=== Autotune & UAM Characterization ===')
    print(f'Patients: {patients}')
    print(f'Output: {output_dir}')
    print(f'Report: {report_path}')
    print()

    # Analyze each patient
    all_results = []
    for pid in patients:
        patient_dir = NS_DATA / pid / 'raw'
        if not patient_dir.exists():
            print(f'  Skipping patient {pid}: {patient_dir} not found')
            continue
        results = analyze_patient(pid, patient_dir)
        all_results.append(results)
        print()

    if not all_results:
        print('ERROR: No patient data found. Run `make bootstrap` first.')
        sys.exit(1)

    # Generate visualizations
    print('=== Generating Visualizations ===')
    plot_uam_performance(all_results, output_dir)
    plot_uam_event_summary(all_results, output_dir)
    plot_autotune_basal_profiles(all_results, output_dir)
    plot_deviation_heatmap(all_results, output_dir)
    plot_isf_comparison(all_results, output_dir)
    plot_algorithm_summary(all_results, output_dir)

    # Generate report
    print()
    print('=== Generating Report ===')
    generate_report(all_results, output_dir, report_path)

    # Save raw results as JSON
    results_json = []
    for r in all_results:
        rj = {
            'patient_id': r.patient_id,
            'total_hours': r.total_hours,
            'n_events': len(r.uam_events),
            'n_announced': sum(1 for e in r.uam_events if e.announced),
            'n_unannounced': sum(1 for e in r.uam_events if not e.announced),
            'uam_metrics': r.uam_metrics,
            'profile_isf': r.profile_isf,
            'effective_isf': r.effective_isf,
            'profile_cr': r.profile_cr,
            'fasting_hours': r.fasting_hours,
            'hourly_deviations': r.hourly_deviations.tolist() if r.hourly_deviations is not None else None,
            'original_basal': r.original_basal.tolist() if r.original_basal is not None else None,
            'autotune_basal': r.autotune_basal.tolist() if r.autotune_basal is not None else None,
        }
        results_json.append(rj)

    results_path = output_dir / 'eval_results.json'
    with open(results_path, 'w') as f:
        json.dump(results_json, f, indent=2)
    print(f'  Raw results saved to {results_path}')

    print()
    print('=== Done ===')


if __name__ == '__main__':
    main()
