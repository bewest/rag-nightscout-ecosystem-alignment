import json
import pandas as pd
import numpy as np
import torch
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from .schema import (
    NORMALIZATION_SCALES, GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX,
    STATE_IDX, ACTION_IDX, ALL_VALS_IDX, NUM_FEATURES,
)

# SILENCE PANDAS WARNINGS
pd.set_option('future.no_silent_downcasting', True)

class FixtureEncoder:
    """Encoder for converting T1Pal fixtures to time-aligned vectors."""
    
    def __init__(self, basal_rate: float = 0.0):
        self.default_basal_rate = basal_rate

    def _get_basal_at(self, timestamp: datetime, profile: Dict) -> float:
        if not profile or 'basalSchedule' not in profile:
            return self.default_basal_rate
        
        # basalSchedule uses local-time startSeconds, so convert timestamp if tz-aware
        if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
            tz_str = profile.get('timezone', '') if isinstance(profile, dict) else ''
            if tz_str:
                if tz_str.upper().startswith('ETC/'):
                    tz_str = 'Etc/' + tz_str[4:]
                try:
                    import pytz
                    timestamp = timestamp.astimezone(pytz.timezone(tz_str))
                except Exception:
                    try:
                        from zoneinfo import ZoneInfo
                        timestamp = timestamp.astimezone(ZoneInfo(tz_str))
                    except Exception:
                        pass  # Use UTC if conversion fails

        seconds = timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second
        active_rate = self.default_basal_rate
        for entry in sorted(profile['basalSchedule'], key=lambda x: x['startSeconds']):
            if seconds >= entry['startSeconds']:
                active_rate = entry['value']
            else:
                break
        return active_rate

    def fixture_to_df(self, file_path: str) -> pd.DataFrame:
        """Loads and aligns fixture data to a 5-min DataFrame."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Determine format
        if isinstance(data, list):
            # scenario format: loop objects contain iob, cob, enacted, etc.
            device_status = []
            for item in data:
                loop = item.get('loop', {})
                status = {
                    'timestamp': item.get('created_at'),
                    'iob': loop.get('iob', {}).get('iob'),
                    'cob': loop.get('cob', {}).get('cob'),
                }
                enacted = loop.get('enacted', {})
                if enacted:
                    status['temp_basal_rate'] = enacted.get('rate')
                    status['bolusVolume'] = enacted.get('bolusVolume')
                device_status.append(status)
            entries, treatments, profile = [], [], {}
        else:
            device_status = data.get('deviceStatus', [])
            entries = data.get('entries', [])
            treatments = data.get('treatments', [])
            profile = data.get('profile', {})

        # --- PROCESS GLUCOSE ---
        df_entries = pd.DataFrame(entries)
        if not df_entries.empty and 'timestamp' in df_entries.columns:
            df_entries['timestamp'] = pd.to_datetime(df_entries['timestamp'])
            if 'sgv' in df_entries.columns:
                df_entries = df_entries.rename(columns={'sgv': 'glucose'})
            elif 'glucose' in df_entries.columns:
                pass # already named glucose
            else:
                df_entries['glucose'] = np.nan
            df_entries = df_entries[['timestamp', 'glucose']].dropna()
        else:
            df_entries = pd.DataFrame(columns=['timestamp', 'glucose'])

        # --- PROCESS STATE (IOB/COB) ---
        df_status = pd.DataFrame(device_status)
        if not df_status.empty and 'timestamp' in df_status.columns:
            df_status['timestamp'] = pd.to_datetime(df_status['timestamp'])
            col_map = {'loopIOB': 'iob', 'iob': 'iob', 'loopCOB': 'cob', 'cob': 'cob',
                       'enactedSMB': 'smb', 'enactedTempBasalRate': 'temp_basal_rate'}
            df_status = df_status.rename(columns={c: v for c, v in col_map.items() if c in df_status.columns})
            keep_cols = ['timestamp', 'iob', 'cob', 'smb', 'temp_basal_rate']
            df_status = df_status[[c for c in keep_cols if c in df_status.columns]]
        else:
            df_status = pd.DataFrame(columns=['timestamp', 'iob', 'cob'])

        # --- PROCESS TREATMENTS ---
        df_tx = pd.DataFrame(treatments)
        if not df_tx.empty and 'timestamp' in df_tx.columns:
            df_tx['timestamp'] = pd.to_datetime(df_tx['timestamp'])
            boluses = df_tx[df_tx['eventType'].str.contains('Bolus', case=False, na=False)] if 'eventType' in df_tx.columns else pd.DataFrame()
            carbs = df_tx[df_tx['eventType'].str.contains('Meal|Carb', case=False, na=False)] if 'eventType' in df_tx.columns else pd.DataFrame()
            
            if not boluses.empty:
                boluses = boluses.rename(columns={'amount': 'bolus', 'insulin': 'bolus'})
                boluses = boluses[['timestamp', 'bolus']] if 'bolus' in boluses.columns else pd.DataFrame(columns=['timestamp', 'bolus'])
            else:
                boluses = pd.DataFrame(columns=['timestamp', 'bolus'])

            if not carbs.empty:
                carbs = carbs.rename(columns={'carbs': 'carbs', 'amount': 'carbs'})
                carbs = carbs[['timestamp', 'carbs']] if 'carbs' in carbs.columns else pd.DataFrame(columns=['timestamp', 'carbs'])
            else:
                carbs = pd.DataFrame(columns=['timestamp', 'carbs'])
        else:
            boluses, carbs = pd.DataFrame(columns=['timestamp', 'bolus']), pd.DataFrame(columns=['timestamp', 'carbs'])

        # --- ALIGNMENT GRID ---
        ts_objs = [ts for ts in [df_entries['timestamp'], df_status['timestamp'], boluses['timestamp'], carbs['timestamp']] if not ts.empty]
        if not ts_objs: return pd.DataFrame()
        all_ts = pd.concat(ts_objs)
        
        grid = pd.date_range(start=all_ts.min().floor('5min'), end=all_ts.max().ceil('5min'), freq='5min')
        df = pd.DataFrame(index=grid); df.index.name = 'timestamp'

        if not df_entries.empty: df = df.join(df_entries.set_index('timestamp').resample('5min').mean(), how='left')
        if not df_status.empty: df = df.join(df_status.set_index('timestamp').resample('5min').mean(), how='left')
        if not boluses.empty: df = df.join(boluses.set_index('timestamp').resample('5min').sum(), how='left')
        if not carbs.empty: df = df.join(carbs.set_index('timestamp').resample('5min').sum(), how='left')

        # --- CLEANUP & DERIVE ---
        for col in ['glucose', 'iob', 'cob', 'bolus', 'carbs']:
            if col not in df.columns: df[col] = 0.0
        
        df['glucose'] = df['glucose'].interpolate(method='time', limit=3)
        df['iob'] = df['iob'].ffill().fillna(0)
        df['cob'] = df['cob'].ffill().fillna(0)
        df['bolus'] = df['bolus'].fillna(0)
        df['carbs'] = df['carbs'].fillna(0)
        
        temp_rate = df['temp_basal_rate'].ffill() if 'temp_basal_rate' in df.columns else pd.Series(np.nan, index=df.index)
        sched_basal = [self._get_basal_at(ts, profile) for ts in df.index]
        df['net_basal'] = temp_rate.fillna(pd.Series(sched_basal, index=df.index)) - sched_basal
        
        if 'smb' in df.columns: df['bolus'] += df['smb'].fillna(0)

        # --- NEW: CIRCADIAN TIME FEATURES ---
        # Use patient-local time for circadian encoding when profile has timezone
        tz_str = profile.get('timezone', '') if isinstance(profile, dict) else ''
        if tz_str:
            # Normalize Nightscout timezone format (ETC/GMT+7 → Etc/GMT+7)
            if tz_str.upper().startswith('ETC/'):
                tz_str = 'Etc/' + tz_str[4:]
            try:
                if df.index.tz is not None:
                    local_idx = df.index.tz_convert(tz_str)
                else:
                    local_idx = df.index.tz_localize('UTC').tz_convert(tz_str)
                hours = local_idx.hour + local_idx.minute / 60.0
            except Exception:
                hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = df.index.hour + df.index.minute / 60.0
        df['time_sin'] = np.sin(2 * np.pi * hours / 24.0)
        df['time_cos'] = np.cos(2 * np.pi * hours / 24.0)

        # Final Feature selection (8 features now)
        cols = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos']
        return df[cols].fillna(0)

def generate_training_vectors(df: pd.DataFrame, window_size: int = 72, lead_time: int = 12, result_window: int = 12) -> np.ndarray:
    """Creates fixed-length vectors for NN training. Also applies simple scaling."""
    data = df.values.copy().astype(np.float64)
    
    # Clip glucose to valid sensor range before normalization
    data[:, 0] = np.clip(data[:, 0], GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX)
    
    # Normalize using canonical scales from schema.py
    data[:, 0] /= NORMALIZATION_SCALES['glucose']
    data[:, 1] /= NORMALIZATION_SCALES['iob']
    data[:, 2] /= NORMALIZATION_SCALES['cob']
    data[:, 3] /= NORMALIZATION_SCALES['net_basal']
    data[:, 4] /= NORMALIZATION_SCALES['bolus']
    data[:, 5] /= NORMALIZATION_SCALES['carbs']
    # time_sin/cos are already -1..1
    
    total_len = window_size + lead_time + result_window
    vectors = [data[i : i + total_len] for i in range(len(data) - total_len + 1)]
    return np.array(vectors) if vectors else np.empty((0, total_len, 8), dtype=np.float64)

class CGMDataset(torch.utils.data.Dataset):
    """
    PyTorch Dataset for CGM Autoencoder tasks.
    
    Feature Indices:
    0: glucose, 1: iob, 2: cob, 3: net_basal, 4: bolus, 5: carbs, 6: time_sin, 7: time_cos
    """
    def __init__(self, vectors: np.ndarray, task: str = 'reconstruct', window_size: int = 72):
        self.vectors = torch.FloatTensor(vectors)
        self.task = task
        self.window_size = window_size
        
    def __len__(self):
        return len(self.vectors)
    
    def __getitem__(self, idx):
        x = self.vectors[idx].clone()
        y = self.vectors[idx].clone()

        if self.task == 'fill_actions':
            x[:self.window_size, ACTION_IDX] = 0.0
        elif self.task == 'fill_readings':
            x[:self.window_size, STATE_IDX] = 0.0
        elif self.task == 'forecast':
            x[self.window_size:, ALL_VALS_IDX] = 0.0
        elif self.task == 'denoise':
            x[:self.window_size, ALL_VALS_IDX] += torch.randn_like(x[:self.window_size, ALL_VALS_IDX]) * 0.05
        elif self.task == 'random_patch':
            patch_len = min(torch.randint(6, 13, (1,)).item(), self.window_size)
            start = torch.randint(0, self.window_size - patch_len + 1, (1,)).item()
            x[start : start + patch_len, ALL_VALS_IDX] = 0.0
        elif self.task == 'shuffled_mask':
            mask = torch.rand_like(x[:self.window_size, ALL_VALS_IDX]) < 0.15
            x[:self.window_size, ALL_VALS_IDX][mask] = 0.0

        return x, y

class ConditionedDataset(torch.utils.data.Dataset):
    """
    Dataset for Action-Conditioned Prediction.
    Input: (History_All_Features, Future_Actions)
    Target: Future_Glucose
    """
    def __init__(self, vectors: np.ndarray, window_size: int = 72):
        self.vectors = torch.FloatTensor(vectors)
        self.window_size = window_size
        
    def __len__(self):
        return len(self.vectors)
        
    def __getitem__(self, idx):
        full_vec = self.vectors[idx]
        
        # History: all features up to window_size
        history = full_vec[:self.window_size, :]
        
        # Future Actions: indices 3, 4, 5 after window_size
        future_actions = full_vec[self.window_size:, [3, 4, 5]]
        
        # Target: future glucose (index 0) after window_size
        target_glucose = full_vec[self.window_size:, 0]
        
        return (history, future_actions), target_glucose

def load_fixtures_to_dataset(dirs: List[str], task='reconstruct', window_size=72, val_split=0.2, conditioned=False) -> Tuple:
    """Loads fixtures and returns (train_ds, val_ds)."""
    enc = FixtureEncoder()
    all_v = []
    for d in dirs:
        for p in Path(d).glob('*.json'):
            df = enc.fixture_to_df(str(p))
            if not df.empty and len(df) >= (window_size + 6): 
                all_v.append(generate_training_vectors(df, window_size=window_size, lead_time=3, result_window=3))
    
    if not all_v: return None, None
    
    data = np.concatenate(all_v, axis=0)
    np.random.shuffle(data)
    
    split_idx = int(len(data) * (1 - val_split))
    train_v, val_v = data[:split_idx], data[split_idx:]
    
    if conditioned:
        return (ConditionedDataset(train_v, window_size=window_size),
                ConditionedDataset(val_v, window_size=window_size))
    
    return (CGMDataset(train_v, task=task, window_size=window_size),
            CGMDataset(val_v, task=task, window_size=window_size))

if __name__ == "__main__":
    # Example: Modern ML training loop setup
    TASK = 'random_patch'
    WINDOW = 12 # 1 hour for testing
    
    ds = load_fixtures_to_dataset(
        ['fixtures/algorithm-replays', 'fixtures/scenarios'], 
        task=TASK,
        window_size=WINDOW
    )
    
    if ds:
        from torch.utils.data import DataLoader
        
        # Best Practice: Use DataLoader with shuffling
        loader = DataLoader(ds, batch_size=32, shuffle=True)
        
        print(f"Dataset created with {len(ds)} samples.")
        print(f"Selected task: {TASK}")
        
        # Inspect a batch
        for x_batch, y_batch in loader:
            print(f"Batch X shape: {x_batch.shape}")
            print(f"Batch Y shape: {y_batch.shape}")
            
            # Show a sample of the mask
            sample_idx = 0
            has_zeros = (x_batch[sample_idx] == 0).any()
            print(f"Sample 0 has masked (zeroed) values: {has_zeros}")
            break
    else:
        print("No fixtures found or data insufficient.")
