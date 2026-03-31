"""
real_data_adapter.py — Bridge from real CGM datasets to cgmencode training pipeline.

Converts tabular CGM data (OhioT1DM, Nightscout, Tidepool, etc.) into the
8-feature (glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos)
tensor format used by cgmencode models.

Supports two input modes:
  1. GluPredKit parser output (DataFrame with CGM, bolus, basal, carbs columns)
  2. Raw CSV/DataFrame with configurable column mapping

Usage:
    # From OhioT1DM via GluPredKit parser:
    python3 -m tools.cgmencode.real_data_adapter --source ohio --data-path /path/to/OhioT1DM --subject 559 --year 2020

    # From any CSV with glucose, insulin, carbs columns:
    python3 -m tools.cgmencode.real_data_adapter --csv /path/to/data.csv --glucose-col CGM --bolus-col bolus --basal-col basal --carbs-col carbs

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


# Normalization constants matching encoder.py / sim_adapter.py
SCALE = {
    'glucose': 400.0,    # mg/dL
    'iob': 20.0,         # units
    'cob': 100.0,        # grams
    'net_basal': 5.0,    # U/hr
    'bolus': 10.0,       # units
    'carbs': 100.0,      # grams
}

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
    parser.add_argument('--source', choices=['ohio', 'csv', 'test'], default='test',
                        help='Data source type')
    parser.add_argument('--data-path', help='Path to dataset root (OhioT1DM parent dir)')
    parser.add_argument('--subject', default='559', help='Subject ID for OhioT1DM')
    parser.add_argument('--year', default='2020', help='Dataset year')
    parser.add_argument('--csv', help='Path to CSV file')
    parser.add_argument('--window', type=int, default=24, help='Window size (5-min steps)')
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

    if args.source == 'ohio':
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
