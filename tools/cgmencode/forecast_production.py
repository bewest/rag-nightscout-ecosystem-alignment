#!/usr/bin/env python3
"""Production Forecast Inference Pipeline

Lightweight inference-only module for glucose forecasting.
Implements the composite champion routing system validated in EXP-619.

Champion architecture (settled from 600+ experiments):
  - PKGroupedEncoder (134K params) with prepare_pk_future (8ch)
  - pk_mode=True (future PK channels visible)
  - ISF normalization + per-patient fine-tuning
  - Horizon-adaptive routing with transfer learning

Inference engines:
  - w48 PKGroupedEncoder: h30-h120 (8ch pk_mode, ~134K params)
  - w72 PKGroupedEncoder: h30-h180 (8ch pk_mode, transfer from w48)
  - w96 PKGroupedEncoder: h120-h240 (8ch pk_mode, transfer from w48)
  - w144 PKGroupedEncoder: h240-h360 (8ch pk_mode, transfer from w48)

Usage:
  # Export models from training
  python -m cgmencode.forecast_production export --models-dir models/

  # Run inference benchmark
  python -m cgmencode.forecast_production benchmark --models-dir models/

  # Single-patient forecast
  python -m cgmencode.forecast_production forecast --patient a --horizon 120
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# Lazy torch import (not needed for Ridge-only inference)
torch = None
nn = None


def _ensure_torch():
    global torch, nn
    if torch is None:
        import torch as _torch
        import torch.nn as _nn
        torch = _torch
        nn = _nn


# ─── Constants (must match v14 training) ───

GLUCOSE_SCALE = 400.0
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]

# Champion feature channels (8ch from prepare_pk_future):
# [glucose, IOB, COB, net_basal, insulin_net, carb_rate, sin_time, net_balance]
CHAMPION_CHANNELS = 8

# Horizon map: name → step index in future prediction array
HORIZON_MAP = {
    'h5': 0, 'h10': 1, 'h15': 2, 'h20': 3, 'h25': 4,
    'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
    'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71,
}


# ─── Production Model Config ───

@dataclass
class EngineConfig:
    """Configuration for a single forecast engine."""
    name: str
    engine_type: str  # 'ridge' or 'transformer'
    window_size: int
    history_steps: int
    future_steps: int
    channels: int = CHAMPION_CHANNELS  # 8ch pk_mode (champion)
    horizons: List[str] = field(default_factory=list)
    model_path: Optional[str] = None
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 4

    @property
    def max_horizon_minutes(self):
        return self.future_steps * 5

    @property
    def history_minutes(self):
        return self.history_steps * 5


# Default routing configuration from EXP-619 composite champion
DEFAULT_ROUTING = {
    'engines': [
        EngineConfig(
            name='w48_short',
            engine_type='transformer',
            window_size=48,
            history_steps=24,
            future_steps=24,
            channels=8,
            horizons=['h30', 'h60', 'h90', 'h120'],
        ),
        EngineConfig(
            name='w72_mid',
            engine_type='transformer',
            window_size=72,
            history_steps=36,
            future_steps=36,
            channels=8,
            horizons=['h30', 'h60', 'h90', 'h120', 'h150', 'h180'],
        ),
        EngineConfig(
            name='w96_extended',
            engine_type='transformer',
            window_size=96,
            history_steps=48,
            future_steps=48,
            channels=8,
            horizons=['h120', 'h150', 'h180', 'h240'],
        ),
        EngineConfig(
            name='w144_strategic',
            engine_type='transformer',
            window_size=144,
            history_steps=72,
            future_steps=72,
            channels=8,
            horizons=['h240', 'h300', 'h360'],
        ),
    ],
    # Routing map from EXP-619 full-scale validation (11pt, 5-seed)
    # w48 wins h30-h120, w96 wins h150-h240, w144 wins h300-h360
    'routing_map': {
        'h30': 'w48_short', 'h60': 'w48_short',
        'h90': 'w48_short', 'h120': 'w48_short',
        'h150': 'w96_extended', 'h180': 'w96_extended',
        'h240': 'w96_extended',
        'h300': 'w144_strategic', 'h360': 'w144_strategic',
    },
    # Simplified 2-engine routing (minimal deployment)
    'routing_map_simple': {
        'h30': 'w48_short', 'h60': 'w48_short',
        'h90': 'w48_short', 'h120': 'w48_short',
        'h150': 'w96_extended', 'h180': 'w96_extended',
        'h240': 'w96_extended',
    },
}


# ─── Minimal model re-implementation (inference only) ───

class PositionalEncoding:
    """Positional encoding compatible with training code."""
    def __init__(self, d_model, max_len=512):
        _ensure_torch()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() *
                             (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.pe = pe.unsqueeze(0)  # (1, max_len, d_model)

    def __call__(self, x):
        return x + self.pe[:, :x.size(1), :].to(x.device)


class PKGroupedEncoderInference:
    """Inference-only PKGroupedEncoder (no nn.Module overhead when not training)."""

    def __init__(self, state_dict, input_dim=CHAMPION_CHANNELS, d_model=64, nhead=4,
                 num_layers=4, dim_feedforward=128, device='cpu'):
        _ensure_torch()
        from cgmencode.exp_pk_forecast_v14 import PKGroupedEncoder
        self.model = PKGroupedEncoder(
            input_dim=input_dim, d_model=d_model, nhead=nhead,
            num_layers=num_layers, dim_feedforward=dim_feedforward,
        )
        self.model.load_state_dict(state_dict)
        self.model.to(device)
        self.model.eval()
        self.device = device
        self.input_dim = input_dim

    def predict(self, x_input, future_steps=None):
        """Run inference on prepared input tensor.

        Args:
            x_input: (batch, seq_len, channels) tensor
            future_steps: number of future steps (default: seq_len // 2)

        Returns:
            predictions: (batch, future_steps) glucose predictions in normalized units
        """
        with torch.no_grad():
            x = x_input.to(self.device)
            half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
            pred = self.model(x, causal=True)
            return pred[:, half:, 0].cpu()

    def memory_bytes(self):
        """Total memory footprint of model parameters."""
        return sum(p.nelement() * p.element_size()
                   for p in self.model.parameters())


# ─── Forecast Router ───

class ForecastRouter:
    """Routes horizon requests to appropriate specialist engines.

    Production architecture (EXP-619 full-scale validated):
      h30-h120  → w48 specialist (26K windows, 2h context, 134K params)
      h150-h240 → w96 specialist (transfer from w48, 4h context)
      h300-h360 → w144 specialist (transfer from w48, 6h context)

    Validated MAEs (11pt, 5-seed):
      h30=11.1, h60=14.2, h90=16.1, h120=17.4,
      h150=17.9, h180=18.5, h240=20.0, h300=20.2, h360=21.9
    """

    def __init__(self, models_dir: str, device: str = 'cpu',
                 routing_config: Optional[dict] = None):
        _ensure_torch()
        self.models_dir = Path(models_dir)
        self.device = device
        self.config = routing_config or DEFAULT_ROUTING
        self.engines: Dict[str, PKGroupedEncoderInference] = {}
        self.engine_configs: Dict[str, EngineConfig] = {}
        self._load_timings = {}

    def load_engine(self, engine_cfg: EngineConfig) -> bool:
        """Load a single engine from checkpoint."""
        t0 = time.perf_counter()
        ckpt_path = engine_cfg.model_path or str(
            self.models_dir / f'{engine_cfg.name}.pth')

        if not os.path.exists(ckpt_path):
            print(f"  ⚠ Checkpoint not found: {ckpt_path}")
            return False

        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        state = ckpt.get('model_state', ckpt)

        engine = PKGroupedEncoderInference(
            state, input_dim=engine_cfg.channels,
            d_model=engine_cfg.d_model, nhead=engine_cfg.nhead,
            num_layers=engine_cfg.num_layers, device=self.device,
        )
        self.engines[engine_cfg.name] = engine
        self.engine_configs[engine_cfg.name] = engine_cfg
        elapsed = time.perf_counter() - t0
        self._load_timings[engine_cfg.name] = elapsed
        mem_kb = engine.memory_bytes() / 1024
        print(f"  ✓ {engine_cfg.name}: loaded in {elapsed*1000:.0f}ms, "
              f"{mem_kb:.0f}KB params")
        return True

    def load_all(self) -> Dict[str, bool]:
        """Load all engines defined in routing config."""
        print(f"Loading forecast engines from {self.models_dir}...")
        results = {}
        for ecfg in self.config['engines']:
            results[ecfg.name] = self.load_engine(ecfg)
        loaded = sum(results.values())
        total = len(results)
        print(f"  {loaded}/{total} engines loaded")
        return results

    def route(self, horizon: str) -> Optional[str]:
        """Return engine name for a given horizon."""
        return self.config['routing_map'].get(horizon)

    def available_horizons(self) -> List[str]:
        """Return horizons that have loaded engines."""
        return [h for h, eng in self.config['routing_map'].items()
                if eng in self.engines]

    def forecast(self, x_input, horizon: str,
                 isf: Optional[float] = None) -> Optional[np.ndarray]:
        """Run forecast for a specific horizon.

        Args:
            x_input: prepared input tensor (1, seq_len, channels)
            horizon: e.g., 'h60', 'h120', 'h180'
            isf: ISF value for denormalization (mg/dL per U)

        Returns:
            predicted glucose value(s) in mg/dL, or None if horizon unavailable
        """
        engine_name = self.route(horizon)
        if not engine_name or engine_name not in self.engines:
            return None

        engine = self.engines[engine_name]
        ecfg = self.engine_configs[engine_name]
        step_idx = HORIZON_MAP.get(horizon)
        if step_idx is None:
            return None

        pred = engine.predict(x_input, future_steps=ecfg.future_steps)
        pred_np = pred.numpy()

        # Denormalize
        if isf is not None:
            pred_np = pred_np * (isf / GLUCOSE_SCALE) * GLUCOSE_SCALE
        else:
            pred_np = pred_np * GLUCOSE_SCALE

        # Extract specific horizon step
        if step_idx < pred_np.shape[1]:
            return pred_np[:, step_idx]
        return None

    def forecast_all(self, inputs: Dict[str, any],
                     isf: Optional[float] = None) -> Dict[str, float]:
        """Run all available horizon forecasts.

        Args:
            inputs: dict mapping engine_name → prepared input tensor
            isf: ISF for denormalization

        Returns:
            dict mapping horizon_name → predicted glucose (mg/dL)
        """
        results = {}
        timings = {}

        for horizon in self.available_horizons():
            engine_name = self.route(horizon)
            if engine_name not in inputs:
                continue

            t0 = time.perf_counter()
            pred = self.forecast(inputs[engine_name], horizon, isf=isf)
            elapsed = time.perf_counter() - t0
            timings[horizon] = elapsed

            if pred is not None:
                results[horizon] = float(pred[0]) if pred.ndim > 0 else float(pred)

        results['_timings'] = timings
        return results

    def benchmark(self, n_iterations: int = 100) -> Dict[str, Dict]:
        """Benchmark inference timing for all loaded engines.

        Returns timing statistics per engine and overall.
        """
        print(f"\nBenchmarking {n_iterations} iterations per engine...")
        results = {}
        total_mem = 0

        for name, engine in self.engines.items():
            ecfg = self.engine_configs[name]
            # Create dummy input
            x = torch.randn(1, ecfg.window_size, ecfg.channels)

            # Warmup
            for _ in range(5):
                engine.predict(x, future_steps=ecfg.future_steps)

            # Timed runs
            times = []
            for _ in range(n_iterations):
                t0 = time.perf_counter()
                engine.predict(x, future_steps=ecfg.future_steps)
                times.append(time.perf_counter() - t0)

            times_ms = np.array(times) * 1000
            mem = engine.memory_bytes()
            total_mem += mem

            results[name] = {
                'mean_ms': round(float(np.mean(times_ms)), 2),
                'p50_ms': round(float(np.median(times_ms)), 2),
                'p95_ms': round(float(np.percentile(times_ms, 95)), 2),
                'p99_ms': round(float(np.percentile(times_ms, 99)), 2),
                'min_ms': round(float(np.min(times_ms)), 2),
                'max_ms': round(float(np.max(times_ms)), 2),
                'memory_kb': round(mem / 1024, 1),
                'params': sum(p.nelement() for p in engine.model.parameters()),
                'window': ecfg.window_size,
                'horizons': ecfg.horizons,
            }
            print(f"  {name}: mean={results[name]['mean_ms']:.2f}ms, "
                  f"p95={results[name]['p95_ms']:.2f}ms, "
                  f"{results[name]['memory_kb']:.0f}KB")

        # Combined routing benchmark (all 3 engines sequential)
        combined_times = []
        for _ in range(n_iterations):
            t0 = time.perf_counter()
            for name, engine in self.engines.items():
                ecfg = self.engine_configs[name]
                x = torch.randn(1, ecfg.window_size, ecfg.channels)
                engine.predict(x, future_steps=ecfg.future_steps)
            combined_times.append(time.perf_counter() - t0)

        combined_ms = np.array(combined_times) * 1000
        results['_combined'] = {
            'mean_ms': round(float(np.mean(combined_ms)), 2),
            'p95_ms': round(float(np.percentile(combined_ms, 95)), 2),
            'total_memory_kb': round(total_mem / 1024, 1),
            'total_params': sum(r['params'] for r in results.values()
                                if isinstance(r, dict) and 'params' in r),
            'n_engines': len(self.engines),
        }
        print(f"\n  Combined routing: mean={results['_combined']['mean_ms']:.2f}ms, "
              f"total={results['_combined']['total_memory_kb']:.0f}KB, "
              f"{results['_combined']['total_params']} params")

        return results

    def export_config(self) -> dict:
        """Export router configuration for deployment."""
        return {
            'routing_map': self.config['routing_map'],
            'engines': [
                {
                    'name': ecfg.name,
                    'type': ecfg.engine_type,
                    'window_size': ecfg.window_size,
                    'history_steps': ecfg.history_steps,
                    'future_steps': ecfg.future_steps,
                    'channels': ecfg.channels,
                    'horizons': ecfg.horizons,
                    'model_path': ecfg.model_path,
                    'd_model': ecfg.d_model,
                }
                for ecfg in self.config['engines']
            ],
            'benchmark': self.benchmark(50) if self.engines else {},
        }


# ─── Feature Preparation (production inference) ───

def prepare_pk_future_inference(glucose: np.ndarray, iob: np.ndarray,
                                 cob: np.ndarray, net_basal: np.ndarray,
                                 insulin_net: np.ndarray, carb_rate: np.ndarray,
                                 net_balance: np.ndarray,
                                 window_size: int = 48,
                                 isf: float = 50.0) -> np.ndarray:
    """Prepare 8ch input for production inference.

    Mirrors prepare_pk_future from training. All arrays must be same length
    (= window_size) at 5-minute intervals.

    Channels: [glucose, IOB, COB, net_basal, insulin_net, carb_rate, sin_time, net_balance]

    Args:
        glucose: BG values in mg/dL (NaN allowed in future portion)
        iob: Insulin on board (U)
        cob: Carbs on board (g)
        net_basal: Net basal rate (U/hr above programmed)
        insulin_net: Net insulin absorption rate
        carb_rate: Carb absorption rate
        net_balance: insulin_net + carb_rate (supply/demand)
        window_size: Total window length (history + future)
        isf: Patient ISF for normalization (mg/dL per U)

    Returns:
        (1, window_size, 8) float32 array ready for model input
    """
    half = window_size // 2
    n = len(glucose)
    assert n == window_size, f"Expected {window_size} timesteps, got {n}"

    # Normalize glucose by ISF
    gluc_norm = glucose / (isf / GLUCOSE_SCALE) / GLUCOSE_SCALE

    # Compute sin_time from position
    positions = np.arange(n, dtype=np.float32)
    sin_time = np.sin(2 * np.pi * positions / 288)  # 288 = 24h at 5min

    # Stack channels and normalize
    norms = np.array(PK_NORMS, dtype=np.float32)
    window = np.stack([
        gluc_norm, iob, cob, net_basal,
        insulin_net, carb_rate, sin_time, net_balance
    ], axis=-1).astype(np.float32)

    # Apply PK normalization (channels 1-7)
    for ch in range(1, 8):
        if norms[ch] > 0:
            window[:, ch] /= norms[ch]

    return window[np.newaxis, :, :]  # (1, window_size, 8)


# ─── PK Derivative Computation (LEGACY — 11ch approach, superseded by 8ch pk_mode) ───

def compute_pk_derivatives(window: np.ndarray, history_steps: int) -> np.ndarray:
    """[LEGACY] Compute PK derivative channels for a single window.

    NOTE: The 11ch d1-derivative approach was superseded by the 8ch pk_mode
    champion validated in EXP-619. This function is retained for backward
    compatibility with pre-EXP-619 model checkpoints.

    Takes an 8ch base window and returns 11ch (base + d_ins + d_carb + d_gluc).
    Matches _prepare_pk_derivatives_asymmetric from v14 but for single windows.

    Args:
        window: (seq_len, 8) array — [gluc, IOB, COB, net_basal, ins_net, carb_rate, sin, net_bal]
        history_steps: number of history steps (glucose derivatives zeroed after this)

    Returns:
        (seq_len, 11) array with derivative channels appended
    """
    seq_len = window.shape[0]

    # PK derivatives (deterministic, safe everywhere)
    d_ins = np.zeros((seq_len, 1), dtype=np.float32)
    d_ins[1:, 0] = window[1:, 4] - window[:-1, 4]

    d_carb = np.zeros((seq_len, 1), dtype=np.float32)
    d_carb[1:, 0] = window[1:, 5] - window[:-1, 5]

    # Glucose derivative (history-only)
    d_gluc = np.zeros((seq_len, 1), dtype=np.float32)
    h = history_steps
    d_gluc[1:h, 0] = window[1:h, 0] - window[:h-1, 0]

    # Scale (matches training)
    d_ins *= 10.0
    d_carb *= 10.0
    d_gluc *= 10.0

    return np.concatenate([window, d_ins, d_carb, d_gluc], axis=-1)


# ─── Ridge Forecaster (Tier 1 production) ───

class RidgeForecaster:
    """Lightweight Ridge regression forecaster for h5-h60.

    Uses 8 physics features from supply/demand decomposition.
    ~200 coefficients, <1ms inference, runs on any device.
    """

    def __init__(self, coefficients: Optional[Dict] = None):
        self.coefficients = coefficients or {}
        self.horizons = ['h5', 'h10', 'h15', 'h20', 'h25', 'h30', 'h60']

    def fit(self, X_train: np.ndarray, y_train: np.ndarray, alpha: float = 1.0):
        """Fit Ridge regression for each horizon.

        Args:
            X_train: (n_samples, n_features) feature matrix
            y_train: (n_samples, n_horizons) target matrix
        """
        n_features = X_train.shape[1]
        I = np.eye(n_features)

        for i, h in enumerate(self.horizons):
            if i >= y_train.shape[1]:
                break
            y = y_train[:, i]
            mask = ~np.isnan(y)
            X, y = X_train[mask], y[mask]
            # Closed-form Ridge: w = (X^TX + αI)^{-1} X^Ty
            XtX = X.T @ X + alpha * I
            Xty = X.T @ y
            w = np.linalg.solve(XtX, Xty)
            self.coefficients[h] = w.tolist()

    def predict(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """Predict glucose at each horizon.

        Args:
            X: (n_samples, n_features) or (n_features,) feature vector

        Returns:
            dict mapping horizon → predictions array
        """
        if X.ndim == 1:
            X = X.reshape(1, -1)

        results = {}
        for h, w in self.coefficients.items():
            w = np.array(w)
            results[h] = X @ w
        return results

    def save(self, path: str):
        with open(path, 'w') as f:
            json.dump({
                'type': 'ridge_forecaster',
                'horizons': self.horizons,
                'coefficients': self.coefficients,
                'n_features': len(next(iter(self.coefficients.values()), [])),
            }, f, indent=2)

    @classmethod
    def load(cls, path: str) -> 'RidgeForecaster':
        with open(path) as f:
            data = json.load(f)
        return cls(coefficients=data['coefficients'])

    def memory_bytes(self):
        total = 0
        for w in self.coefficients.values():
            total += len(w) * 8  # float64
        return total


# ─── Production Pipeline ───

class ProductionPipeline:
    """Complete production forecast pipeline.

    Combines Ridge (Tier 1) and Transformer routing (Tier 2)
    for h5-h360 glucose forecasting.
    """

    def __init__(self, models_dir: str, device: str = 'cpu'):
        self.models_dir = Path(models_dir)
        self.device = device
        self.ridge: Optional[RidgeForecaster] = None
        self.router: Optional[ForecastRouter] = None
        self._loaded = False

    def load(self) -> Dict[str, bool]:
        """Load all production models."""
        results = {}

        # Load Ridge (Tier 1)
        ridge_path = self.models_dir / 'ridge_forecaster.json'
        if ridge_path.exists():
            self.ridge = RidgeForecaster.load(str(ridge_path))
            results['ridge'] = True
            print(f"  ✓ Ridge: {self.ridge.memory_bytes()} bytes, "
                  f"{len(self.ridge.coefficients)} horizons")
        else:
            results['ridge'] = False

        # Load Transformer routing (Tier 2)
        self.router = ForecastRouter(str(self.models_dir), self.device)
        router_results = self.router.load_all()
        results.update(router_results)

        self._loaded = True
        return results

    def capabilities(self) -> Dict:
        """Return available capabilities summary."""
        caps = {
            'ridge_horizons': list(self.ridge.coefficients.keys()) if self.ridge else [],
            'transformer_horizons': self.router.available_horizons() if self.router else [],
            'total_memory_kb': 0,
        }
        if self.ridge:
            caps['total_memory_kb'] += self.ridge.memory_bytes() / 1024
        if self.router:
            for eng in self.router.engines.values():
                caps['total_memory_kb'] += eng.memory_bytes() / 1024
        caps['total_memory_kb'] = round(caps['total_memory_kb'], 1)
        return caps

    def full_benchmark(self, n_iterations: int = 100) -> Dict:
        """Benchmark entire pipeline."""
        results = {}

        # Ridge benchmark
        if self.ridge:
            n_feat = len(next(iter(self.ridge.coefficients.values()), []))
            X_dummy = np.random.randn(1, n_feat)
            times = []
            for _ in range(n_iterations):
                t0 = time.perf_counter()
                self.ridge.predict(X_dummy)
                times.append(time.perf_counter() - t0)
            times_us = np.array(times) * 1e6
            results['ridge'] = {
                'mean_us': round(float(np.mean(times_us)), 1),
                'p95_us': round(float(np.percentile(times_us, 95)), 1),
                'memory_bytes': self.ridge.memory_bytes(),
            }
            print(f"  Ridge: mean={results['ridge']['mean_us']:.1f}μs, "
                  f"{results['ridge']['memory_bytes']} bytes")

        # Transformer routing benchmark
        if self.router and self.router.engines:
            results['router'] = self.router.benchmark(n_iterations)

        return results


# ─── CLI ───

def cmd_benchmark(args):
    """Run inference benchmarks on loaded models."""
    pipeline = ProductionPipeline(args.models_dir, args.device)
    loaded = pipeline.load()
    print(f"\nLoaded: {sum(v for v in loaded.values() if v)}/{len(loaded)}")

    caps = pipeline.capabilities()
    print(f"\nCapabilities:")
    print(f"  Ridge horizons: {caps['ridge_horizons']}")
    print(f"  Transformer horizons: {caps['transformer_horizons']}")
    print(f"  Total memory: {caps['total_memory_kb']:.1f} KB")

    bench = pipeline.full_benchmark(args.iterations)

    out_path = os.path.join(args.output_dir, 'production_benchmark.json')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'capabilities': caps, 'benchmark': bench}, f, indent=2)
    print(f"\nSaved: {out_path}")


def cmd_export_config(args):
    """Export production configuration."""
    config = {
        'version': '2.0',
        'experiment': 'EXP-619',
        'validated': '11pt, 5-seed, 200ep base + 30ep FT',
        'routing': DEFAULT_ROUTING['routing_map'],
        'routing_simple': DEFAULT_ROUTING['routing_map_simple'],
        'engines': [
            {
                'name': ecfg.name,
                'type': ecfg.engine_type,
                'window_size': ecfg.window_size,
                'history_steps': ecfg.history_steps,
                'future_steps': ecfg.future_steps,
                'channels': ecfg.channels,
                'horizons': ecfg.horizons,
                'max_horizon_min': ecfg.max_horizon_minutes,
                'history_min': ecfg.history_minutes,
            }
            for ecfg in DEFAULT_ROUTING['engines']
        ],
        'validated_maes': {
            'h30': 11.1, 'h60': 14.2, 'h90': 16.1, 'h120': 17.4,
            'h150': 17.9, 'h180': 18.5, 'h240': 20.0,
            'h300': 20.2, 'h360': 21.9,
        },
        'champion': {
            'model': 'PKGroupedEncoder',
            'params': 134891,
            'channels': CHAMPION_CHANNELS,
            'feature_prep': 'prepare_pk_future',
            'pk_mode': True,
            'isf_normalize': True,
            'd_model': 64,
            'nhead': 4,
            'num_layers': 4,
        },
        'production_notes': {
            'tier2': 'Transformer routing h30-h360: ~1ms/engine, ~540KB/engine',
            'total_params': f'~{134891 * 4} (4 × 134K transformers)',
            'validated_at': 'EXP-619 full-scale (11pt, 5-seed, 162min)',
            'scaling_factor': '0.74x (quick → full)',
        },
    }
    out_path = os.path.join(args.output_dir, 'production_config.json')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"Exported: {out_path}")


def cmd_export_models(args):
    """Export production models from EXP-619 checkpoints.

    Packages best-seed checkpoints into a production directory structure:
      models/production/
        w48_short.pth          — base model for h30-h120
        w96_extended.pth       — base model for h150-h240
        w144_strategic.pth     — base model for h300-h360
        w48_short_ft_{pid}.pth — per-patient fine-tuned (optional)
        production_config.json — routing + metadata
    """
    src_dir = Path(args.source_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _ensure_torch()
    seed = args.seed

    # Map engine names to window sizes
    engine_windows = {
        'w48_short': 48,
        'w72_mid': 72,
        'w96_extended': 96,
        'w144_strategic': 144,
    }

    exported = {}
    patients = list('abcdefghijk')

    for engine_name, wsize in engine_windows.items():
        # Export base model
        base_path = src_dir / f'exp619_w{wsize}_base_s{seed}.pth'
        if base_path.exists():
            ckpt = torch.load(str(base_path), map_location='cpu', weights_only=False)
            out_path = out_dir / f'{engine_name}.pth'
            torch.save({
                'model_state': ckpt['model_state'],
                'input_dim': CHAMPION_CHANNELS,
                'd_model': 64,
                'nhead': 4,
                'num_layers': 4,
                'window_size': wsize,
                'source': f'EXP-619 w{wsize} base s{seed}',
                'val_loss': ckpt.get('val_loss'),
                'epoch': ckpt.get('epoch'),
            }, str(out_path))
            size_kb = out_path.stat().st_size / 1024
            print(f"  ✓ {engine_name}: {size_kb:.0f}KB (epoch {ckpt.get('epoch')})")
            exported[engine_name] = True

            # Export per-patient fine-tuned models
            if args.include_ft:
                ft_count = 0
                for pid in patients:
                    ft_path = src_dir / f'exp619_w{wsize}_ft_{pid}_s{seed}.pth'
                    if ft_path.exists():
                        ft_ckpt = torch.load(str(ft_path), map_location='cpu',
                                             weights_only=False)
                        ft_out = out_dir / f'{engine_name}_ft_{pid}.pth'
                        torch.save({
                            'model_state': ft_ckpt['model_state'],
                            'input_dim': CHAMPION_CHANNELS,
                            'd_model': 64,
                            'nhead': 4,
                            'num_layers': 4,
                            'window_size': wsize,
                            'patient': pid,
                            'source': f'EXP-619 w{wsize} ft_{pid} s{seed}',
                            'val_loss': ft_ckpt.get('val_loss'),
                            'epoch': ft_ckpt.get('epoch'),
                        }, str(ft_out))
                        ft_count += 1
                if ft_count:
                    print(f"    + {ft_count} fine-tuned models")
        else:
            print(f"  ⚠ {engine_name}: checkpoint not found ({base_path})")
            exported[engine_name] = False

    # Export production config alongside models
    config = {
        'version': '2.0',
        'experiment': 'EXP-619',
        'seed': seed,
        'routing': DEFAULT_ROUTING['routing_map'],
        'routing_simple': DEFAULT_ROUTING['routing_map_simple'],
        'channels': CHAMPION_CHANNELS,
        'pk_mode': True,
        'validated_maes': {
            'h30': 11.1, 'h60': 14.2, 'h90': 16.1, 'h120': 17.4,
            'h150': 17.9, 'h180': 18.5, 'h240': 20.0,
            'h300': 20.2, 'h360': 21.9,
        },
        'engines': {name: {'exported': v} for name, v in exported.items()},
    }
    cfg_path = out_dir / 'production_config.json'
    with open(str(cfg_path), 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\n  Config: {cfg_path}")
    print(f"  Exported {sum(exported.values())}/{len(exported)} engines to {out_dir}")


def main():
    parser = argparse.ArgumentParser(description='Production Forecast Pipeline')
    sub = parser.add_subparsers(dest='command')

    bench = sub.add_parser('benchmark', help='Run inference benchmarks')
    bench.add_argument('--models-dir', default='externals/models/production')
    bench.add_argument('--device', default='cpu')
    bench.add_argument('--iterations', type=int, default=100)
    bench.add_argument('--output-dir', default='externals/experiments')

    export_cfg = sub.add_parser('export-config', help='Export production config')
    export_cfg.add_argument('--output-dir', default='externals/experiments')

    export_mdl = sub.add_parser('export', help='Export models from EXP-619')
    export_mdl.add_argument('--source-dir', default='externals/experiments',
                            help='Directory containing EXP-619 checkpoints')
    export_mdl.add_argument('--output-dir', default='externals/models/production',
                            help='Production model output directory')
    export_mdl.add_argument('--seed', type=int, default=42,
                            help='Seed to export (default: 42)')
    export_mdl.add_argument('--include-ft', action='store_true',
                            help='Include per-patient fine-tuned models')

    args = parser.parse_args()
    if args.command == 'benchmark':
        cmd_benchmark(args)
    elif args.command == 'export-config':
        cmd_export_config(args)
    elif args.command == 'export':
        cmd_export_models(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
