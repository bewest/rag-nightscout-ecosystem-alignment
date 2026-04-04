"""
online_adaptation.py — Online/periodic model adaptation for temporal drift.

Addresses the 7.4% verification gap from temporal drift (EXP-249).
Models trained on historical data degrade as patient physiology, CGM sensor
characteristics, and therapy patterns evolve over time.

Approach:
  - SlidingWindowDataset: Extract recent time-ordered training windows
  - periodic_retrain: Fine-tune base model on most recent data
  - evaluate_temporal_stability: Detect degradation over time windows
  - AdaptiveRetrainer: Automated retrain trigger on MAE threshold

This module is additive — no changes to existing training infrastructure.
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from .schema import NORMALIZATION_SCALES, FUTURE_UNKNOWN_CHANNELS
from .experiment_lib import (
    create_model, mask_future_channels, forecast_mse,
    get_device, batch_to_device, set_seed, load_checkpoint, transfer_weights,
)


GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']


class SlidingWindowDataset:
    """Time-ordered sliding window over patient data for incremental training.

    Creates training windows from a specified recent time period, maintaining
    chronological order for temporal evaluation.

    Args:
        data: (N, T, C) tensor — full patient time series as windows
        window_weeks: Number of weeks of data to use (default: 4)
        stride_weeks: Stride for the sliding window (default: 1)
        samples_per_week: Approximate number of 5-min samples per week
            (default: 2016 = 7 * 24 * 12)

    Usage:
        swd = SlidingWindowDataset(data, window_weeks=4)
        for window_data in swd.windows():
            # window_data is a TensorDataset for that time window
            train_on(window_data)
    """

    def __init__(self, data, window_weeks=4, stride_weeks=1,
                 samples_per_week=2016):
        self.data = data
        self.window_weeks = window_weeks
        self.stride_weeks = stride_weeks
        self.samples_per_week = samples_per_week
        self.window_size = window_weeks * samples_per_week
        self.stride_size = stride_weeks * samples_per_week

    def windows(self):
        """Yield TensorDatasets for each sliding window in chronological order."""
        n_samples = len(self.data)
        start = 0
        while start + self.window_size <= n_samples:
            end = start + self.window_size
            window_data = self.data[start:end]
            yield TensorDataset(window_data)
            start += self.stride_size

        # Include final partial window if substantial (>50% of full)
        if start < n_samples and (n_samples - start) > self.window_size // 2:
            yield TensorDataset(self.data[start:])

    def n_windows(self):
        """Number of windows that will be yielded."""
        n = len(self.data)
        if n < self.window_size:
            return 1 if n > self.window_size // 2 else 0
        count = (n - self.window_size) // self.stride_size + 1
        remainder = n - (count - 1) * self.stride_size - self.window_size
        if remainder > 0 and remainder > self.window_size // 2:
            count += 1
        return count

    def latest_window(self):
        """Return the most recent window as a TensorDataset."""
        n = len(self.data)
        start = max(0, n - self.window_size)
        return TensorDataset(self.data[start:])


def periodic_retrain(base_model_path, patient_data, output_path,
                     input_dim=8, d_model=64, nhead=4, num_layers=2,
                     window_weeks=4, lr=5e-5, epochs=10, patience=5,
                     batch_size=32):
    """Fine-tune a base model on the most recent data window.

    Uses transfer_weights for flexible checkpoint loading, then fine-tunes
    with a low learning rate to preserve base model knowledge.

    Args:
        base_model_path: Path to base model checkpoint
        patient_data: (N, T, C) tensor — full patient windows
        output_path: Where to save retrained checkpoint
        input_dim, d_model, nhead, num_layers: Model architecture (must match base)
        window_weeks: How many weeks of recent data to use
        lr: Fine-tuning learning rate (low to prevent catastrophic forgetting)
        epochs, patience, batch_size: Training params

    Returns:
        dict with new_mae, old_mae, improvement_pct, epochs_run
    """
    device = get_device()

    # Create model and load base checkpoint
    model = create_model(arch='grouped', input_dim=input_dim, d_model=d_model,
                         nhead=nhead, num_layers=num_layers)
    ckpt = torch.load(base_model_path, map_location=device, weights_only=False)
    state_dict = ckpt.get('model_state', ckpt)
    model.load_state_dict(state_dict, strict=False)
    model.to(device)

    # Get recent window
    swd = SlidingWindowDataset(patient_data, window_weeks=window_weeks)
    recent_ds = swd.latest_window()

    # Split 80/20 for train/val
    n = len(recent_ds)
    n_train = int(n * 0.8)
    train_ds = TensorDataset(recent_ds.tensors[0][:n_train])
    val_ds = TensorDataset(recent_ds.tensors[0][n_train:])

    # Measure baseline MAE before fine-tuning
    old_mae = forecast_mse(model, val_ds, batch_size=batch_size)

    # Fine-tune
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=3, factor=0.5)
    crit = nn.MSELoss()
    best_val, stale = float('inf'), 0

    for ep in range(epochs):
        model.train()
        for b in DataLoader(train_ds, batch_size=batch_size, shuffle=True):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict):
                pred = pred['forecast']
            loss = crit(pred[:, half:, :1], x[:, half:, :1])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in DataLoader(val_ds, batch_size=64):
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_in = x.clone()
                mask_future_channels(x_in, half)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                vtl += crit(pred[:, half:, :1], x[:, half:, :1]).item() * x.size(0)
                vn += x.size(0)
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best_val:
            best_val, stale = vl, 0
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'epoch': ep,
                         'val_loss': vl, 'base_model': base_model_path}, output_path)
        else:
            stale += 1
        if patience > 0 and stale >= patience:
            break

    if os.path.exists(output_path):
        load_checkpoint(model, output_path)

    new_mae = forecast_mse(model, val_ds, batch_size=batch_size)
    improvement = (old_mae - new_mae) / old_mae * 100 if old_mae > 0 else 0.0

    return {
        'new_mae': round(float(new_mae), 6),
        'old_mae': round(float(old_mae), 6),
        'improvement_pct': round(float(improvement), 2),
        'epochs_run': ep + 1,
    }


def evaluate_temporal_stability(model, patient_data, n_windows=8,
                                window_weeks=4, input_dim=8,
                                batch_size=64):
    """Evaluate model on successive time windows to detect temporal degradation.

    Args:
        model: Trained model to evaluate (or path to checkpoint)
        patient_data: (N, T, C) tensor — full patient windows in chronological order
        n_windows: Number of windows to evaluate
        window_weeks: Size of each window
        input_dim: Model input dimension
        batch_size: Eval batch size

    Returns:
        dict with:
            mae_per_window: list of MAE values per window
            trend_slope: slope of MAE over time (positive = degrading)
            is_degrading: bool — whether model is getting worse
            n_windows_evaluated: int
    """
    device = get_device()
    if isinstance(model, str):
        m = create_model(arch='grouped', input_dim=input_dim)
        load_checkpoint(m, model)
        model = m
    model.to(device)
    model.eval()

    swd = SlidingWindowDataset(patient_data, window_weeks=window_weeks,
                               stride_weeks=max(1, window_weeks // 2))
    mae_list = []
    for i, window_ds in enumerate(swd.windows()):
        if i >= n_windows:
            break
        mse_val = forecast_mse(model, window_ds, batch_size=batch_size)
        mae_list.append(float(mse_val))

    if len(mae_list) < 2:
        return {
            'mae_per_window': mae_list,
            'trend_slope': 0.0,
            'is_degrading': False,
            'n_windows_evaluated': len(mae_list),
        }

    # Linear regression for trend
    x = np.arange(len(mae_list))
    slope = np.polyfit(x, mae_list, 1)[0]

    return {
        'mae_per_window': [round(m, 6) for m in mae_list],
        'trend_slope': round(float(slope), 6),
        'is_degrading': float(slope) > 0 and mae_list[-1] > mae_list[0] * 1.05,
        'n_windows_evaluated': len(mae_list),
    }


class AdaptiveRetrainer:
    """Monitors verification MAE and triggers retraining when degradation detected.

    Maintains a running history of evaluation metrics and automatically
    fine-tunes the model when MAE exceeds a threshold.

    Args:
        base_model_path: Path to the initial trained model
        patient_data: (N, T, C) tensor — patient windows
        config: dict with:
            - degradation_threshold: float — retrain if MAE increases by this % (default: 15)
            - window_weeks: int — retrain window size (default: 4)
            - lr: float — fine-tuning learning rate (default: 5e-5)
            - epochs: int — max fine-tuning epochs (default: 10)
            - input_dim, d_model, nhead, num_layers: model architecture
    """

    def __init__(self, base_model_path, patient_data, config=None):
        self.base_model_path = base_model_path
        self.patient_data = patient_data
        self.config = config or {}
        self.degradation_threshold = self.config.get('degradation_threshold', 15.0)
        self.history = []
        self.retrain_events = []
        self.current_model_path = base_model_path

    def evaluate(self, eval_data=None):
        """Evaluate current model on latest data.

        Args:
            eval_data: Optional TensorDataset. If None, uses latest window.

        Returns:
            float — current MAE
        """
        device = get_device()
        input_dim = self.config.get('input_dim', 8)
        model = create_model(
            arch='grouped', input_dim=input_dim,
            d_model=self.config.get('d_model', 64),
            nhead=self.config.get('nhead', 4),
            num_layers=self.config.get('num_layers', 2),
        )
        load_checkpoint(model, self.current_model_path)
        model.to(device)

        if eval_data is None:
            swd = SlidingWindowDataset(
                self.patient_data,
                window_weeks=self.config.get('window_weeks', 4))
            eval_data = swd.latest_window()

        mae = forecast_mse(model, eval_data, batch_size=64)
        self.history.append({
            'mae': round(float(mae), 6),
            'model_path': self.current_model_path,
        })
        return float(mae)

    def should_retrain(self):
        """Check if retraining is needed based on degradation threshold.

        Returns:
            bool — True if current MAE exceeds baseline by threshold %
        """
        if len(self.history) < 2:
            return False
        baseline = self.history[0]['mae']
        current = self.history[-1]['mae']
        degradation_pct = (current - baseline) / baseline * 100
        return degradation_pct > self.degradation_threshold

    def retrain(self):
        """Execute periodic retrain and update model path.

        Returns:
            dict with retrain results (new_mae, old_mae, improvement_pct)
        """
        output_path = self.current_model_path.replace('.pth', '_adapted.pth')
        if output_path == self.current_model_path:
            output_path = self.current_model_path + '.adapted'

        result = periodic_retrain(
            base_model_path=self.current_model_path,
            patient_data=self.patient_data,
            output_path=output_path,
            input_dim=self.config.get('input_dim', 8),
            d_model=self.config.get('d_model', 64),
            nhead=self.config.get('nhead', 4),
            num_layers=self.config.get('num_layers', 2),
            window_weeks=self.config.get('window_weeks', 4),
            lr=self.config.get('lr', 5e-5),
            epochs=self.config.get('epochs', 10),
            patience=self.config.get('patience', 5),
        )

        self.retrain_events.append(result)
        if result['improvement_pct'] > 0:
            self.current_model_path = output_path

        return result

    def check_and_retrain(self):
        """Evaluate and retrain if needed. Returns summary dict."""
        mae = self.evaluate()
        needs_retrain = self.should_retrain()
        result = {
            'current_mae': mae,
            'needs_retrain': needs_retrain,
            'retrain_result': None,
        }
        if needs_retrain:
            result['retrain_result'] = self.retrain()
        return result
