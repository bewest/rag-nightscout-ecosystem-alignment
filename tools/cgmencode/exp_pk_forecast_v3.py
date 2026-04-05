#!/usr/bin/env python3
"""EXP-360 through EXP-363: Dual-Branch & Feature Engineering Experiments

Inspired by:
- GluPredKit's Double LSTM (state-transfer from glucose to treatment branch)
- symmetry-sparsity-feature-selection-2026-04-05.md (ISF normalization,
  conservation regularization, multi-resolution encoding)
- EXP-356 breakthrough: future PK projection = -10 mg/dL at h120

EXP-360 — Dual-Branch CNN (GluPredKit-inspired)
  Branch 1: CNN processes glucose history → produces embedding
  Branch 2: CNN processes PK channels (history + future), conditioned by
  Branch 1's embedding (via state-transfer / FiLM conditioning).
  Hypothesis: Forced separation prevents glucose dominance, improves upon
  simple concatenation from EXP-356.

EXP-361 — ISF-Normalized Glucose + Future PK
  Normalize glucose by per-patient ISF instead of fixed /400.
  Hypothesis: ISF normalization improves cross-patient learning. Combined
  with future PK from EXP-356, should improve long horizons further.

EXP-362 — Conservation-Regularized Forecaster
  Physics residual regularization: L_total = L_mse + λ|∫(pred - physics)dt|²
  Uses net_balance as physics proxy for dBG/dt.
  Hypothesis: Constraining predictions to respect insulin:glucose energy
  balance improves extrapolation at h180+.

EXP-363 — Learned PK Kernels
  Replace fixed oref0 PK convolution kernels with learnable B-spline
  parameterized kernels. Model optimizes DIA/absorption shape jointly with
  forecast loss.
  Hypothesis: Data-driven PK kernels outperform hardcoded oref0 model,
  especially for patients with atypical absorption profiles.

Usage:
    python tools/cgmencode/exp_pk_forecast_v3.py --experiment 360 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v3.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ─── Constants ───

SEEDS = [42, 123, 456]
SEEDS_QUICK = [42]
GLUCOSE_SCALE = 400.0
QUICK_PATIENTS = 4
QUICK_EPOCHS = 30
QUICK_PATIENCE = 8

HORIZONS_EXTENDED = {
    'h30': 6, 'h60': 12, 'h120': 24, 'h180': 36,
    'h240': 48, 'h360': 72, 'h480': 96, 'h720': 144,
}
HORIZONS_STANDARD = {'h30': 6, 'h60': 12, 'h120': 24}

PK_IDX = {
    'insulin_total': 0, 'insulin_net': 1, 'basal_ratio': 2,
    'carb_rate': 3, 'carb_accel': 4, 'hepatic_production': 5,
    'net_balance': 6, 'isf_curve': 7,
}
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
FUTURE_PK_INDICES = [1, 2, 3, 6]  # insulin_net, basal_ratio, carb_rate, net_balance


# ─── Data Loading ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile_isf(train_dir):
    """Load ISF from patient profile for normalization."""
    profile_path = os.path.join(train_dir, 'profile.json')
    if not os.path.exists(profile_path):
        return None
    try:
        with open(profile_path) as f:
            profile = json.load(f)
        # Check for store (Nightscout format)
        store = profile.get('store', {})
        default_profile = store.get('Default', store.get(next(iter(store), ''), {}))
        sens = default_profile.get('sens', [])
        if sens:
            isf_values = [s.get('value', 0) for s in sens]
            mean_isf = np.mean([v for v in isf_values if v > 0])
            # Detect mmol/L units (ISF < 15 likely mmol/L)
            if mean_isf < 15:
                mean_isf *= 18.0182  # convert to mg/dL
            return float(mean_isf) if mean_isf > 0 else None
        return None
    except Exception:
        return None


def load_forecast_data(patients_dir, history_steps=72, max_horizon=48,
                       max_patients=None, load_isf=False):
    """Load base + PK features with extended future window.

    Returns:
        base_train, base_val: (N, T_total, 8)
        pk_train, pk_val: (N, T_total, 8)
        isf_train, isf_val: (N,) per-window ISF values (if load_isf=True)
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    all_isf_train, all_isf_val = [], []
    window_size = history_steps + max_horizon
    stride = history_steps // 2

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir)
        pk_grid = build_continuous_pk_features(df)

        n_pts = min(len(base_grid), len(pk_grid))
        base_grid = base_grid[:n_pts].astype(np.float32)
        pk_grid = pk_grid[:n_pts].astype(np.float32)
        np.nan_to_num(base_grid, copy=False)
        np.nan_to_num(pk_grid, copy=False)

        isf = load_patient_profile_isf(train_dir) if load_isf else None

        windows_b, windows_p = [], []
        for start in range(0, n_pts - window_size + 1, stride):
            w_b = base_grid[start:start + window_size]
            w_p = pk_grid[start:start + window_size]
            glucose_hist = w_b[:history_steps, 0]
            if np.isnan(glucose_hist).mean() > 0.2:
                continue
            glucose_future = w_b[history_steps:, 0]
            if np.isnan(glucose_future).any():
                continue
            windows_b.append(w_b)
            windows_p.append(w_p)

        if not windows_b:
            continue

        windows_b = np.array(windows_b)
        windows_p = np.array(windows_p)
        n = len(windows_b)
        split = int(0.8 * n)

        all_base_train.append(windows_b[:split])
        all_base_val.append(windows_b[split:])
        all_pk_train.append(windows_p[:split])
        all_pk_val.append(windows_p[split:])

        if load_isf and isf is not None:
            all_isf_train.append(np.full(split, isf, dtype=np.float32))
            all_isf_val.append(np.full(n - split, isf, dtype=np.float32))
        elif load_isf:
            # Fallback: estimate ISF=50 mg/dL/U (typical rapid-acting)
            all_isf_train.append(np.full(split, 50.0, dtype=np.float32))
            all_isf_val.append(np.full(n - split, 50.0, dtype=np.float32))

        print(f"  {pdir.name}: {n} windows ({split} train, {n-split} val)"
              f"{f', ISF={isf:.1f}' if isf else ''}")

    bt = np.concatenate(all_base_train)
    bv = np.concatenate(all_base_val)
    pt = np.concatenate(all_pk_train)
    pv = np.concatenate(all_pk_val)
    print(f"Total: {len(bt)} train, {len(bv)} val")

    if load_isf:
        it = np.concatenate(all_isf_train)
        iv = np.concatenate(all_isf_val)
        return bt, bv, pt, pv, it, iv
    return bt, bv, pt, pv


def extract_targets(base_windows, history_steps, horizons):
    targets = []
    for name, offset in horizons.items():
        idx = history_steps + offset - 1
        targets.append(base_windows[:, idx, 0])
    return np.stack(targets, axis=1)


def persistence_baseline(base_val, history_steps, horizons):
    last_glucose = base_val[:, history_steps - 1, 0]
    targets = extract_targets(base_val, history_steps, horizons)
    per_horizon = {}
    for i, (name, _) in enumerate(horizons.items()):
        mae = float(np.mean(np.abs(last_glucose - targets[:, i])) * GLUCOSE_SCALE)
        per_horizon[name] = mae
    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }


# ─── Models ───

class ForecastCNN(nn.Module):
    """Standard 1D-CNN forecaster (baseline)."""
    def __init__(self, in_channels, n_horizons=3):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        feat = self.conv(x).squeeze(-1)
        return self.head(feat)


class ForecastCNNWithFuture(nn.Module):
    """CNN with separate history + future PK branches (EXP-356 winner)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=3):
        super().__init__()
        self.hist_conv = nn.Sequential(
            nn.Conv1d(hist_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.Conv1d(16, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x_hist, x_future):
        x_h = x_hist.permute(0, 2, 1)
        x_f = x_future.permute(0, 2, 1)
        h_feat = self.hist_conv(x_h).squeeze(-1)
        f_feat = self.future_conv(x_f).squeeze(-1)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


# ─── EXP-360: Dual-Branch CNN with State Transfer ───

class DualBranchCNN(nn.Module):
    """GluPredKit-inspired dual-branch architecture.

    Branch 1 (glucose): CNN on glucose history → produces glucose embedding
    Branch 2 (PK): CNN on PK history + future, conditioned via FiLM on
      glucose embedding. The glucose context modulates PK processing.

    Compared to simple concatenation (EXP-356), this forces the PK branch
    to learn in the context of glucose dynamics, not independently.

    FiLM conditioning: gamma, beta = Linear(glucose_embed)
    PK_features = gamma * PK_raw + beta

    Reference: Perez et al., "FiLM: Visual Reasoning with a General
    Conditioning Layer", AAAI 2018
    """
    def __init__(self, pk_channels, n_horizons=3, glucose_dim=64, pk_dim=32):
        super().__init__()
        # Branch 1: glucose history only
        self.glucose_conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, glucose_dim, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(glucose_dim),
            nn.AdaptiveAvgPool1d(1),
        )
        # FiLM: project glucose embedding → gamma, beta for PK conditioning
        self.film_gamma = nn.Linear(glucose_dim, pk_dim)
        self.film_beta = nn.Linear(glucose_dim, pk_dim)

        # Branch 2: PK channels (history + future), conditioned by glucose
        self.pk_conv = nn.Sequential(
            nn.Conv1d(pk_channels, pk_dim, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(pk_dim),
            nn.Conv1d(pk_dim, pk_dim, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(pk_dim),
        )
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        # Fusion head
        self.head = nn.Sequential(
            nn.Linear(glucose_dim + pk_dim, 64), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(64, 32), nn.ReLU(),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x_glucose_hist, x_pk_full):
        """
        x_glucose_hist: (B, T_hist, 1) - glucose history only
        x_pk_full: (B, T_hist+T_future, pk_channels) - PK over full window
        """
        # Branch 1: glucose context
        g = x_glucose_hist.permute(0, 2, 1)  # (B, 1, T)
        g_feat = self.glucose_conv(g).squeeze(-1)  # (B, glucose_dim)

        # Branch 2: PK features
        p = x_pk_full.permute(0, 2, 1)  # (B, C, T)
        p_feat = self.pk_conv(p)  # (B, pk_dim, T)

        # FiLM conditioning: modulate PK features with glucose context
        gamma = self.film_gamma(g_feat).unsqueeze(-1)  # (B, pk_dim, 1)
        beta = self.film_beta(g_feat).unsqueeze(-1)    # (B, pk_dim, 1)
        p_conditioned = gamma * p_feat + beta           # (B, pk_dim, T)

        p_pooled = self.pk_pool(p_conditioned).squeeze(-1)  # (B, pk_dim)

        # Fuse and predict
        combined = torch.cat([g_feat, p_pooled], dim=1)
        return self.head(combined)


class StateTransferCNN(nn.Module):
    """Direct analog of GluPredKit Double LSTM, but with CNN + LSTM hybrid.

    Branch 1: CNN on glucose history → (h, c) states
    Branch 2: LSTM on PK sequence, initialized with (h, c) from Branch 1
    The LSTM sees PK in temporal order, conditioned by glucose context.

    This is the closest adaptation of the paper architecture
    (https://ieeexplore.ieee.org/document/8856940) to our CNN pipeline.
    """
    def __init__(self, pk_channels, n_horizons=3, hidden_dim=32):
        super().__init__()
        # Branch 1: CNN encoder for glucose → hidden state
        self.glucose_conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        # Map CNN output → LSTM initial states
        self.proj_h = nn.Linear(64, hidden_dim)
        self.proj_c = nn.Linear(64, hidden_dim)

        # Branch 2: LSTM for PK sequence, conditioned by glucose state
        self.pk_lstm = nn.LSTM(pk_channels, hidden_dim, num_layers=1,
                               batch_first=True)

        # Forecast head
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x_glucose_hist, x_pk_full):
        """
        x_glucose_hist: (B, T_hist, 1)
        x_pk_full: (B, T_full, pk_channels)
        """
        # Branch 1: glucose → initial LSTM state
        g = x_glucose_hist.permute(0, 2, 1)
        g_feat = self.glucose_conv(g).squeeze(-1)  # (B, 64)
        h0 = torch.tanh(self.proj_h(g_feat)).unsqueeze(0)  # (1, B, hidden)
        c0 = torch.tanh(self.proj_c(g_feat)).unsqueeze(0)

        # Branch 2: PK LSTM conditioned by glucose
        _, (hn, _) = self.pk_lstm(x_pk_full, (h0, c0))
        pk_feat = hn.squeeze(0)  # (B, hidden)

        return self.head(pk_feat)


# ─── EXP-362: Conservation Regularizer ───

class ConservationRegularizer:
    """Enforce glucose integral ≈ physics integral over absorption windows.

    physics_proxy: net_balance channel approximates dBG/dt.
    The cumulative sum of net_balance should predict glucose trajectory.
    Penalize divergence between predicted and physics-implied trajectories.
    """
    def __init__(self, lambda_cons=0.01):
        self.lambda_cons = lambda_cons

    def compute_loss(self, predictions, targets, pk_future, history_steps, horizons):
        """
        predictions: (B, n_horizons) - predicted glucose at horizons
        targets: (B, n_horizons) - actual glucose at horizons
        pk_future: (B, T_future, 8) - PK channels over future window
        """
        mse_loss = F.mse_loss(predictions, targets)

        # Physics prediction from net_balance integration
        net_balance_idx = 6  # net_balance channel
        nb = pk_future[:, :, net_balance_idx]  # (B, T_future)
        # Integrate net_balance (cumsum * dt, dt=5min)
        nb_integral = torch.cumsum(nb, dim=1) * (5.0 / 60.0)  # hours

        # Sample physics trajectory at horizon points
        physics_deltas = []
        for name, offset in horizons.items():
            idx = min(offset - 1, nb_integral.shape[1] - 1)
            physics_deltas.append(nb_integral[:, idx])
        physics_deltas = torch.stack(physics_deltas, dim=1)  # (B, n_horizons)

        # Scale to glucose units: net_balance is in mg/dL/h, integral gives mg/dL
        # Prediction is in normalized glucose [0, 1], so scale physics too
        physics_deltas_norm = physics_deltas / GLUCOSE_SCALE

        # Conservation loss: predicted change should correlate with physics change
        pred_change = predictions - predictions[:, :1]  # relative to first horizon
        physics_change = physics_deltas_norm - physics_deltas_norm[:, :1]

        # Penalize mismatched signs (direction disagreement)
        sign_disagreement = F.relu(-pred_change * physics_change)
        conservation_loss = sign_disagreement.mean()

        return mse_loss + self.lambda_cons * conservation_loss, {
            'mse': mse_loss.item(),
            'conservation': conservation_loss.item(),
        }


# ─── EXP-363: Learned PK Kernels ───

class LearnedPKEncoder(nn.Module):
    """Replace fixed oref0 PK kernels with learnable parameters.

    Instead of using pre-computed continuous_pk curves, learn the
    convolution kernel shape directly. The kernel is parameterized
    as a B-spline-like curve with learnable control points.

    For insulin: kernel represents the activity curve (rise → peak → decay)
    For carbs: kernel represents absorption rate (rise → linear decay)
    """
    def __init__(self, kernel_length=72, n_knots=8):
        super().__init__()
        self.kernel_length = kernel_length

        # Learnable control points for insulin activity curve
        # Initialize with approximate Fiasp/NovoRapid curve shape
        t = torch.linspace(0, 1, n_knots)
        # Roughly: 0, rise, peak, decay...
        init_insulin = torch.tensor([0.0, 0.3, 0.8, 1.0, 0.7, 0.3, 0.1, 0.0])
        self.insulin_knots = nn.Parameter(init_insulin[:n_knots].clone())

        # Learnable control points for carb absorption
        init_carbs = torch.tensor([0.0, 0.5, 1.0, 0.9, 0.6, 0.3, 0.1, 0.0])
        self.carb_knots = nn.Parameter(init_carbs[:n_knots].clone())

        # Learnable DIA/absorption time scaling
        self.insulin_dia_logscale = nn.Parameter(torch.tensor(0.0))  # exp(0)=1 → 6h
        self.carb_abs_logscale = nn.Parameter(torch.tensor(0.0))

    def _interpolate_kernel(self, knots, scale):
        """Interpolate control points to full kernel length."""
        n_knots = len(knots)
        knots_soft = F.softplus(knots)  # ensure positive
        knots_norm = knots_soft / (knots_soft.sum() + 1e-8)  # normalize to unit area

        # Time scaling
        effective_length = int(self.kernel_length * torch.exp(scale).item())
        effective_length = max(8, min(effective_length, self.kernel_length * 2))

        # Interpolate knots to kernel
        knots_expanded = knots_norm.unsqueeze(0).unsqueeze(0)  # (1, 1, n_knots)
        kernel = F.interpolate(knots_expanded, size=effective_length,
                               mode='linear', align_corners=True)
        kernel = kernel.squeeze()  # (effective_length,)

        # Pad or truncate to kernel_length
        if len(kernel) >= self.kernel_length:
            return kernel[:self.kernel_length]
        else:
            pad = torch.zeros(self.kernel_length - len(kernel),
                              device=kernel.device)
            return torch.cat([kernel, pad])

    def forward(self, bolus_sparse, carbs_sparse):
        """Convolve sparse events with learned kernels.

        bolus_sparse: (B, T) - sparse bolus events
        carbs_sparse: (B, T) - sparse carb events

        Returns:
            insulin_activity: (B, T) - learned insulin activity curve
            carb_absorption: (B, T) - learned carb absorption curve
        """
        insulin_kernel = self._interpolate_kernel(
            self.insulin_knots, self.insulin_dia_logscale)
        carb_kernel = self._interpolate_kernel(
            self.carb_knots, self.carb_abs_logscale)

        # 1D convolution (causal: pad left only)
        B, T = bolus_sparse.shape
        # Reshape for conv1d
        bolus = bolus_sparse.unsqueeze(1)  # (B, 1, T)
        carbs = carbs_sparse.unsqueeze(1)  # (B, 1, T)

        # Causal padding
        pad_len = self.kernel_length - 1
        bolus_padded = F.pad(bolus, (pad_len, 0))
        carbs_padded = F.pad(carbs, (pad_len, 0))

        # Convolution with learned kernel
        ik = insulin_kernel.flip(0).reshape(1, 1, -1)  # (1, 1, K)
        ck = carb_kernel.flip(0).reshape(1, 1, -1)

        insulin_activity = F.conv1d(bolus_padded, ik).squeeze(1)  # (B, T)
        carb_absorption = F.conv1d(carbs_padded, ck).squeeze(1)

        return insulin_activity, carb_absorption


class ForecastCNNWithLearnedPK(nn.Module):
    """CNN forecaster that learns its own PK kernels end-to-end."""
    def __init__(self, n_horizons=3, kernel_length=72, history_steps=72):
        super().__init__()
        self.history_steps = history_steps
        self.pk_encoder = LearnedPKEncoder(kernel_length=kernel_length)

        # Process: glucose + learned_insulin + learned_carbs = 3 channels
        self.hist_conv = nn.Sequential(
            nn.Conv1d(3, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        # Also process learned future PK
        self.future_conv = nn.Sequential(
            nn.Conv1d(2, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.Conv1d(16, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x_glucose, x_bolus, x_carbs):
        """
        x_glucose: (B, T_total, 1)
        x_bolus: (B, T_total) - sparse bolus events
        x_carbs: (B, T_total) - sparse carb events
        """
        # Learn PK curves from sparse events
        insulin_act, carb_abs = self.pk_encoder(x_bolus, x_carbs)

        # Split history and future
        T_hist = self.history_steps
        glucose_hist = x_glucose[:, :T_hist, :]  # (B, T_hist, 1)
        insulin_hist = insulin_act[:, :T_hist].unsqueeze(-1)  # (B, T_hist, 1)
        carb_hist = carb_abs[:, :T_hist].unsqueeze(-1)

        hist_input = torch.cat([glucose_hist, insulin_hist, carb_hist], dim=-1)
        h = hist_input.permute(0, 2, 1)
        h_feat = self.hist_conv(h).squeeze(-1)

        # Future PK (known from past events)
        insulin_future = insulin_act[:, T_hist:].unsqueeze(-1)
        carb_future = carb_abs[:, T_hist:].unsqueeze(-1)
        future_input = torch.cat([insulin_future, carb_future], dim=-1)
        f = future_input.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        combined = torch.cat([h_feat, f_feat], dim=1)
        return self.head(combined)


# ─── Training Utilities ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, extra_loss_fn=None):
    """Train with MSE loss + optional extra loss (conservation, etc.)."""
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    best_val_loss = float('inf')
    best_state = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        train_losses = []
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)

            optimizer.zero_grad()
            preds = model(*inputs)

            if extra_loss_fn is not None:
                loss, _ = extra_loss_fn(preds, targets)
            else:
                loss = F.mse_loss(preds, targets)

            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                targets = batch[-1].to(device)
                preds = model(*inputs)
                val_losses.append(F.mse_loss(preds, targets).item())

        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    return model


def evaluate_model(model, val_loader, device, horizons):
    """Evaluate forecast MAE per horizon."""
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            preds = model(*inputs)
            all_preds.append(preds.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    per_horizon = {}
    horizon_names = list(horizons.keys())
    for i, name in enumerate(horizon_names):
        mae = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        per_horizon[name] = mae

    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }


# ─── Experiment Runners ───

def run_exp_360(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-360: Dual-Branch CNN (GluPredKit-inspired).

    Compare:
    1. glucose_only — just glucose CNN (EXP-356 baseline)
    2. concat_future_pk — glucose + future PK concatenation (EXP-356 winner)
    3. dual_branch_film — FiLM-conditioned PK on glucose embedding
    4. state_transfer — CNN→LSTM state transfer (GluPredKit architecture)
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    epochs = train_kw.get('epochs', 60)
    patience = train_kw.get('patience', 15)
    horizons = HORIZONS_EXTENDED if not args.quick else HORIZONS_STANDARD

    patients_dir = args.patients_dir
    max_horizon = max(horizons.values())
    history_steps = 72

    bt, bv, pt, pv = load_forecast_data(
        patients_dir, history_steps, max_horizon, max_patients)
    targets_train = extract_targets(bt, history_steps, horizons)
    targets_val = extract_targets(bv, history_steps, horizons)
    n_horizons = len(horizons)

    results = {'experiment': 'EXP-360', 'description': 'Dual-branch CNN architectures',
               'horizons': list(horizons.keys()), 'variants': {}}

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        print(f"\n  seed={seed}:")

        for variant_name in ['glucose_only', 'concat_future_pk',
                             'dual_branch_film', 'state_transfer']:
            print(f"    {variant_name}...", end=' ', flush=True)
            t0 = time.time()

            if variant_name == 'glucose_only':
                x_hist = bt[:, :history_steps, :1]
                x_val_hist = bv[:, :history_steps, :1]
                model = ForecastCNN(1, n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(targets_val))

            elif variant_name == 'concat_future_pk':
                # EXP-356 winner: history glucose + future PK
                x_hist = bt[:, :history_steps, :1]
                x_val_hist = bv[:, :history_steps, :1]
                pk_future = pt[:, history_steps:, :][:, :, FUTURE_PK_INDICES]
                pk_future_val = pv[:, history_steps:, :][:, :, FUTURE_PK_INDICES]
                # Normalize PK
                for i, idx in enumerate(FUTURE_PK_INDICES):
                    pk_future[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                    pk_future_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

                model = ForecastCNNWithFuture(1, len(FUTURE_PK_INDICES), n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_future),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_future_val),
                    torch.from_numpy(targets_val))

            elif variant_name == 'dual_branch_film':
                # Glucose history + full PK window, FiLM conditioned
                x_hist = bt[:, :history_steps, :1]
                x_val_hist = bv[:, :history_steps, :1]
                # Full PK window (history + future)
                pk_full = pt[:, :, FUTURE_PK_INDICES].copy()
                pk_full_val = pv[:, :, FUTURE_PK_INDICES].copy()
                for i, idx in enumerate(FUTURE_PK_INDICES):
                    pk_full[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                    pk_full_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

                model = DualBranchCNN(len(FUTURE_PK_INDICES), n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_full),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_full_val),
                    torch.from_numpy(targets_val))

            elif variant_name == 'state_transfer':
                # GluPredKit-style: glucose CNN → LSTM initial state, PK LSTM
                x_hist = bt[:, :history_steps, :1]
                x_val_hist = bv[:, :history_steps, :1]
                pk_full = pt[:, :, FUTURE_PK_INDICES].copy()
                pk_full_val = pv[:, :, FUTURE_PK_INDICES].copy()
                for i, idx in enumerate(FUTURE_PK_INDICES):
                    pk_full[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                    pk_full_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

                model = StateTransferCNN(len(FUTURE_PK_INDICES), n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_full),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_full_val),
                    torch.from_numpy(targets_val))

            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                epochs=epochs, patience=patience)
            res = evaluate_model(model, val_loader, device, horizons)

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")

            key = f"{variant_name}_s{seed}"
            results['variants'][key] = res

    # Aggregate
    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_361(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-361: ISF-Normalized Glucose + Future PK.

    Compare:
    1. glucose_fixed_norm — BG/400 (standard)
    2. glucose_isf_norm — BG/ISF (per-patient)
    Both with future PK projection (EXP-356 winner architecture).
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    epochs = train_kw.get('epochs', 60)
    patience = train_kw.get('patience', 15)
    horizons = HORIZONS_EXTENDED if not args.quick else HORIZONS_STANDARD

    patients_dir = args.patients_dir
    max_horizon = max(horizons.values())
    history_steps = 72

    bt, bv, pt, pv, isf_t, isf_v = load_forecast_data(
        patients_dir, history_steps, max_horizon, max_patients, load_isf=True)
    n_horizons = len(horizons)

    results = {'experiment': 'EXP-361', 'description': 'ISF normalization',
               'horizons': list(horizons.keys()), 'variants': {}}

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        print(f"\n  seed={seed}:")

        for variant_name in ['fixed_norm_future_pk', 'isf_norm_future_pk']:
            print(f"    {variant_name}...", end=' ', flush=True)
            t0 = time.time()

            if variant_name == 'fixed_norm_future_pk':
                # Standard: glucose already normalized by /400
                glucose_hist = bt[:, :history_steps, :1]
                glucose_hist_val = bv[:, :history_steps, :1]
                targets_train = extract_targets(bt, history_steps, horizons)
                targets_val = extract_targets(bv, history_steps, horizons)
            else:
                # ISF normalization: BG * (400/ISF) so output space stays similar
                glucose_hist = bt[:, :history_steps, :1].copy()
                glucose_hist_val = bv[:, :history_steps, :1].copy()
                # Renormalize: current is BG/400, want BG/ISF
                # BG/ISF = (BG/400) * (400/ISF)
                scale_t = (GLUCOSE_SCALE / isf_t).reshape(-1, 1, 1)
                scale_v = (GLUCOSE_SCALE / isf_v).reshape(-1, 1, 1)
                glucose_hist = glucose_hist * scale_t
                glucose_hist_val = glucose_hist_val * scale_v
                # Clip to prevent extreme values
                glucose_hist = np.clip(glucose_hist, 0, 10)
                glucose_hist_val = np.clip(glucose_hist_val, 0, 10)
                # Targets also renormalized
                targets_train = extract_targets(bt, history_steps, horizons)
                targets_val = extract_targets(bv, history_steps, horizons)
                # Scale targets same way
                targets_train = targets_train * (GLUCOSE_SCALE / isf_t.reshape(-1, 1))
                targets_val = targets_val * (GLUCOSE_SCALE / isf_v.reshape(-1, 1))

            # Future PK (same for both)
            pk_future = pt[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
            pk_future_val = pv[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
            for i, idx in enumerate(FUTURE_PK_INDICES):
                pk_future[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                pk_future_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

            model = ForecastCNNWithFuture(1, len(FUTURE_PK_INDICES), n_horizons)
            train_ds = TensorDataset(
                torch.from_numpy(glucose_hist.astype(np.float32)),
                torch.from_numpy(pk_future.astype(np.float32)),
                torch.from_numpy(targets_train.astype(np.float32)))
            val_ds = TensorDataset(
                torch.from_numpy(glucose_hist_val.astype(np.float32)),
                torch.from_numpy(pk_future_val.astype(np.float32)),
                torch.from_numpy(targets_val.astype(np.float32)))

            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                epochs=epochs, patience=patience)

            # Evaluate in original glucose space for fair comparison
            model.eval()
            all_preds, all_targets_raw = [], []
            with torch.no_grad():
                for batch in val_loader:
                    inputs = [b.to(device) for b in batch[:-1]]
                    targets_b = batch[-1]
                    preds = model(*inputs).cpu().numpy()
                    all_preds.append(preds)
                    all_targets_raw.append(targets_b.numpy())

            preds = np.concatenate(all_preds)
            targets_raw = np.concatenate(all_targets_raw)

            # Convert back to mg/dL
            if variant_name == 'isf_norm_future_pk':
                # Predictions are in ISF-normalized space, convert back
                inv_scale = (isf_v / GLUCOSE_SCALE).reshape(-1, 1)
                preds_mgdl = preds * inv_scale * GLUCOSE_SCALE
                targets_mgdl = targets_raw * inv_scale * GLUCOSE_SCALE
            else:
                preds_mgdl = preds * GLUCOSE_SCALE
                targets_mgdl = targets_raw * GLUCOSE_SCALE

            per_horizon = {}
            for i, name in enumerate(horizons.keys()):
                mae = float(np.mean(np.abs(preds_mgdl[:, i] - targets_mgdl[:, i])))
                per_horizon[name] = mae

            res = {
                'mae_overall': float(np.mean(list(per_horizon.values()))),
                'mae_per_horizon': per_horizon,
            }
            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")

            key = f"{variant_name}_s{seed}"
            results['variants'][key] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_362(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-362: Conservation-Regularized Forecaster.

    Compare:
    1. future_pk_mse_only — standard MSE loss (EXP-356 winner)
    2. future_pk_conservation — MSE + conservation regularization
    3. future_pk_conservation_strong — MSE + 10× conservation weight
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    epochs = train_kw.get('epochs', 60)
    patience = train_kw.get('patience', 15)
    horizons = HORIZONS_EXTENDED if not args.quick else HORIZONS_STANDARD

    patients_dir = args.patients_dir
    max_horizon = max(horizons.values())
    history_steps = 72

    bt, bv, pt, pv = load_forecast_data(
        patients_dir, history_steps, max_horizon, max_patients)
    targets_train = extract_targets(bt, history_steps, horizons)
    targets_val = extract_targets(bv, history_steps, horizons)
    n_horizons = len(horizons)

    results = {'experiment': 'EXP-362', 'description': 'Conservation regularization',
               'horizons': list(horizons.keys()), 'variants': {}}

    lambda_values = {'mse_only': 0.0, 'conservation': 0.01, 'conservation_strong': 0.1}

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        print(f"\n  seed={seed}:")

        for variant_name, lambda_cons in lambda_values.items():
            print(f"    {variant_name} (λ={lambda_cons})...", end=' ', flush=True)
            t0 = time.time()

            x_hist = bt[:, :history_steps, :1]
            x_val_hist = bv[:, :history_steps, :1]
            pk_future = pt[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
            pk_future_val = pv[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
            for i, idx in enumerate(FUTURE_PK_INDICES):
                pk_future[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                pk_future_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

            model = ForecastCNNWithFuture(1, len(FUTURE_PK_INDICES), n_horizons)

            if lambda_cons > 0:
                # Need full PK future for conservation loss (unnormalized net_balance)
                pk_future_raw = pt[:, history_steps:, :].copy()
                pk_future_raw_val = pv[:, history_steps:, :].copy()

                def make_conservation_loss(pk_raw_batch, horizons_dict, lam):
                    reg = ConservationRegularizer(lambda_cons=lam)
                    def loss_fn(preds, targets):
                        return reg.compute_loss(preds, targets, pk_raw_batch,
                                                history_steps, horizons_dict)
                    return loss_fn

                # Custom training loop with conservation
                model.to(device)
                optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
                sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
                    optimizer, patience=5, factor=0.5)
                best_val_loss = float('inf')
                best_state = None
                wait_count = 0

                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_future),
                    torch.from_numpy(pk_future_raw),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_future_val),
                    torch.from_numpy(pk_future_raw_val),
                    torch.from_numpy(targets_val))
                train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
                val_loader_full = DataLoader(val_ds, batch_size=256)

                reg = ConservationRegularizer(lambda_cons=lambda_cons)

                for epoch in range(epochs):
                    model.train()
                    for batch in train_loader:
                        x_h, x_pk, x_pk_raw, tgt = [b.to(device) for b in batch]
                        optimizer.zero_grad()
                        preds = model(x_h, x_pk)
                        loss, _ = reg.compute_loss(preds, tgt, x_pk_raw,
                                                   history_steps, horizons)
                        loss.backward()
                        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                        optimizer.step()

                    model.eval()
                    val_losses = []
                    with torch.no_grad():
                        for batch in val_loader_full:
                            x_h, x_pk, x_pk_raw, tgt = [b.to(device) for b in batch]
                            preds = model(x_h, x_pk)
                            val_losses.append(F.mse_loss(preds, tgt).item())
                    vl = np.mean(val_losses)
                    sched.step(vl)
                    if vl < best_val_loss:
                        best_val_loss = vl
                        best_state = {k: v.cpu().clone()
                                      for k, v in model.state_dict().items()}
                        wait_count = 0
                    else:
                        wait_count += 1
                        if wait_count >= patience:
                            break

                if best_state:
                    model.load_state_dict(best_state)

                # Evaluate
                val_ds_eval = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_future_val),
                    torch.from_numpy(targets_val))
                val_loader_eval = DataLoader(val_ds_eval, batch_size=256)
                res = evaluate_model(model, val_loader_eval, device, horizons)

            else:
                # Standard MSE training
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_future),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_future_val),
                    torch.from_numpy(targets_val))
                train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
                val_loader = DataLoader(val_ds, batch_size=256)
                model = train_model(model, train_loader, val_loader, device,
                                    epochs=epochs, patience=patience)
                res = evaluate_model(model, val_loader, device, horizons)

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")

            key = f"{variant_name}_s{seed}"
            results['variants'][key] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_363(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-363: Learned PK Kernels (end-to-end).

    Compare:
    1. fixed_pk_future — pre-computed oref0 PK + future projection (EXP-356)
    2. learned_pk_future — learnable PK kernels + future projection
    3. learned_pk_no_future — learnable PK kernels, history only

    Tests whether data-driven PK kernel shapes outperform hardcoded oref0.
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    epochs = train_kw.get('epochs', 60)
    patience = train_kw.get('patience', 15)
    horizons = HORIZONS_EXTENDED if not args.quick else HORIZONS_STANDARD

    patients_dir = args.patients_dir
    max_horizon = max(horizons.values())
    history_steps = 72

    bt, bv, pt, pv = load_forecast_data(
        patients_dir, history_steps, max_horizon, max_patients)
    targets_train = extract_targets(bt, history_steps, horizons)
    targets_val = extract_targets(bv, history_steps, horizons)
    n_horizons = len(horizons)

    # Extract sparse bolus and carbs channels from base grid
    BOLUS_IDX = 4  # bolus channel in base grid
    CARBS_IDX = 5  # carbs channel in base grid
    bolus_train = bt[:, :, BOLUS_IDX]
    bolus_val = bv[:, :, BOLUS_IDX]
    carbs_train = bt[:, :, CARBS_IDX]
    carbs_val = bv[:, :, CARBS_IDX]

    results = {'experiment': 'EXP-363', 'description': 'Learned PK kernels',
               'horizons': list(horizons.keys()), 'variants': {}}

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        print(f"\n  seed={seed}:")

        for variant_name in ['fixed_pk_future', 'learned_pk_future']:
            print(f"    {variant_name}...", end=' ', flush=True)
            t0 = time.time()

            if variant_name == 'fixed_pk_future':
                # Standard: pre-computed PK + future (EXP-356 winner)
                x_hist = bt[:, :history_steps, :1]
                x_val_hist = bv[:, :history_steps, :1]
                pk_future = pt[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
                pk_future_val = pv[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
                for i, idx in enumerate(FUTURE_PK_INDICES):
                    pk_future[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                    pk_future_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

                model = ForecastCNNWithFuture(1, len(FUTURE_PK_INDICES), n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(x_hist),
                    torch.from_numpy(pk_future),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(x_val_hist),
                    torch.from_numpy(pk_future_val),
                    torch.from_numpy(targets_val))

            elif variant_name == 'learned_pk_future':
                # Learned PK kernels from sparse events
                glucose_full = bt[:, :, :1]
                glucose_full_val = bv[:, :, :1]

                model = ForecastCNNWithLearnedPK(
                    n_horizons=n_horizons,
                    kernel_length=72,
                    history_steps=history_steps)
                train_ds = TensorDataset(
                    torch.from_numpy(glucose_full),
                    torch.from_numpy(bolus_train),
                    torch.from_numpy(carbs_train),
                    torch.from_numpy(targets_train))
                val_ds = TensorDataset(
                    torch.from_numpy(glucose_full_val),
                    torch.from_numpy(bolus_val),
                    torch.from_numpy(carbs_val),
                    torch.from_numpy(targets_val))

            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                epochs=epochs, patience=patience)
            res = evaluate_model(model, val_loader, device, horizons)

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")

            key = f"{variant_name}_s{seed}"
            results['variants'][key] = res

            # For learned PK, report learned kernel parameters
            if variant_name == 'learned_pk_future':
                pk_enc = model.pk_encoder
                results['learned_params'] = results.get('learned_params', {})
                results['learned_params'][f's{seed}'] = {
                    'insulin_knots': pk_enc.insulin_knots.detach().cpu().numpy().tolist(),
                    'carb_knots': pk_enc.carb_knots.detach().cpu().numpy().tolist(),
                    'insulin_dia_scale': float(torch.exp(pk_enc.insulin_dia_logscale).item()),
                    'carb_abs_scale': float(torch.exp(pk_enc.carb_abs_logscale).item()),
                }

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_364(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-364: Combined Best — ISF normalization + 8ch + Future PK at extended horizons.

    Combines the two validated improvements:
    - EXP-356: 8ch + future_pk = best architecture (MAE 37.6 vs 44.2 glucose_only)
    - EXP-361: ISF normalization = -1.2 MAE improvement

    Variants:
    1. glucose_only — baseline
    2. 8ch_future_pk — EXP-356 champion (fixed /400 normalization)
    3. isf_8ch_future_pk — ISF normalization + 8ch + future PK
    4. isf_glucose_future_pk — ISF normalization + glucose-only + future PK

    Run at extended horizons to test full horizon sweep.
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    epochs = train_kw.get('epochs', 60)
    patience = train_kw.get('patience', 15)
    horizons = HORIZONS_EXTENDED if not args.quick else HORIZONS_STANDARD

    patients_dir = args.patients_dir
    max_horizon = max(horizons.values())
    history_steps = 72

    bt, bv, pt, pv, isf_t, isf_v = load_forecast_data(
        patients_dir, history_steps, max_horizon, max_patients, load_isf=True)
    n_horizons = len(horizons)

    results = {'experiment': 'EXP-364',
               'description': 'Combined ISF + 8ch + future PK',
               'horizons': list(horizons.keys()), 'variants': {}}

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        print(f"\n  seed={seed}:")

        for variant_name in ['glucose_only', '8ch_future_pk',
                             'isf_8ch_future_pk', 'isf_glucose_future_pk']:
            print(f"    {variant_name}...", end=' ', flush=True)
            t0 = time.time()

            use_isf = variant_name.startswith('isf_')
            use_future = 'future_pk' in variant_name
            use_8ch = '8ch' in variant_name

            # Prepare glucose history
            if use_8ch:
                hist_raw = bt[:, :history_steps, :].copy()
                hist_raw_val = bv[:, :history_steps, :].copy()
            else:
                hist_raw = bt[:, :history_steps, :1].copy()
                hist_raw_val = bv[:, :history_steps, :1].copy()

            # ISF normalization on glucose channel
            if use_isf:
                scale_t = (GLUCOSE_SCALE / isf_t).reshape(-1, 1, 1)
                scale_v = (GLUCOSE_SCALE / isf_v).reshape(-1, 1, 1)
                hist_raw[:, :, 0:1] = hist_raw[:, :, 0:1] * scale_t
                hist_raw_val[:, :, 0:1] = hist_raw_val[:, :, 0:1] * scale_v
                np.clip(hist_raw[:, :, 0:1], 0, 10, out=hist_raw[:, :, 0:1])
                np.clip(hist_raw_val[:, :, 0:1], 0, 10, out=hist_raw_val[:, :, 0:1])

            # Targets
            targets_train = extract_targets(bt, history_steps, horizons)
            targets_val = extract_targets(bv, history_steps, horizons)
            if use_isf:
                scale_t_flat = (GLUCOSE_SCALE / isf_t).reshape(-1, 1)
                scale_v_flat = (GLUCOSE_SCALE / isf_v).reshape(-1, 1)
                targets_train = targets_train * scale_t_flat
                targets_val = targets_val * scale_v_flat

            hist_channels = hist_raw.shape[-1]

            if use_future:
                pk_future = pt[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
                pk_future_val = pv[:, history_steps:, :][:, :, FUTURE_PK_INDICES].copy()
                for i, idx in enumerate(FUTURE_PK_INDICES):
                    pk_future[:, :, i] /= (PK_NORMS[idx] + 1e-8)
                    pk_future_val[:, :, i] /= (PK_NORMS[idx] + 1e-8)

                model = ForecastCNNWithFuture(
                    hist_channels, len(FUTURE_PK_INDICES), n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(hist_raw.astype(np.float32)),
                    torch.from_numpy(pk_future.astype(np.float32)),
                    torch.from_numpy(targets_train.astype(np.float32)))
                val_ds = TensorDataset(
                    torch.from_numpy(hist_raw_val.astype(np.float32)),
                    torch.from_numpy(pk_future_val.astype(np.float32)),
                    torch.from_numpy(targets_val.astype(np.float32)))
            else:
                model = ForecastCNN(hist_channels, n_horizons)
                train_ds = TensorDataset(
                    torch.from_numpy(hist_raw.astype(np.float32)),
                    torch.from_numpy(targets_train.astype(np.float32)))
                val_ds = TensorDataset(
                    torch.from_numpy(hist_raw_val.astype(np.float32)),
                    torch.from_numpy(targets_val.astype(np.float32)))

            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                epochs=epochs, patience=patience)

            # Evaluate — convert back to mg/dL for fair comparison
            model.eval()
            all_preds, all_tgts = [], []
            with torch.no_grad():
                for batch in val_loader:
                    inputs = [b.to(device) for b in batch[:-1]]
                    tgt = batch[-1]
                    preds = model(*inputs).cpu().numpy()
                    all_preds.append(preds)
                    all_tgts.append(tgt.numpy())

            preds = np.concatenate(all_preds)
            tgts = np.concatenate(all_tgts)

            if use_isf:
                inv_scale = (isf_v / GLUCOSE_SCALE).reshape(-1, 1)
                preds_mg = preds * inv_scale * GLUCOSE_SCALE
                tgts_mg = tgts * inv_scale * GLUCOSE_SCALE
            else:
                preds_mg = preds * GLUCOSE_SCALE
                tgts_mg = tgts * GLUCOSE_SCALE

            per_horizon = {}
            for i, name in enumerate(horizons.keys()):
                mae = float(np.mean(np.abs(preds_mg[:, i] - tgts_mg[:, i])))
                per_horizon[name] = mae

            res = {
                'mae_overall': float(np.mean(list(per_horizon.values()))),
                'mae_per_horizon': per_horizon,
            }
            h_str = ', '.join(f"{k}={v:.1f}"
                              for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")

            key = f"{variant_name}_s{seed}"
            results['variants'][key] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


# ─── Aggregation ───

def _aggregate_results(variants, seeds, horizons):
    """Aggregate per-seed results into mean ± std."""
    # Group by variant name (strip _sXX suffix)
    from collections import defaultdict
    grouped = defaultdict(list)
    for key, res in variants.items():
        # variant_name_sXX → variant_name
        parts = key.rsplit('_s', 1)
        variant = parts[0]
        grouped[variant].append(res)

    summary = {}
    for variant, runs in grouped.items():
        overall_maes = [r['mae_overall'] for r in runs]
        per_h = {}
        for hname in horizons:
            vals = [r['mae_per_horizon'].get(hname, float('nan')) for r in runs]
            per_h[hname] = {
                'mean': float(np.mean(vals)),
                'std': float(np.std(vals)),
            }
        summary[variant] = {
            'mae_overall_mean': float(np.mean(overall_maes)),
            'mae_overall_std': float(np.std(overall_maes)),
            'mae_per_horizon': per_h,
            'n_seeds': len(runs),
        }
    return summary


# ─── CLI ───

def save_results(results, experiment_id):
    out_dir = Path('externals/experiments')
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{experiment_id}.json"
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description='EXP-360-363: Dual-branch & feature engineering')
    parser.add_argument('--experiment', type=str, default='360',
                        help='Experiment: 360, 361, 362, 363, or all')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 1 seed, 4 patients, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '360': ('exp360_dual_branch', run_exp_360),
        '361': ('exp361_isf_norm', run_exp_361),
        '362': ('exp362_conservation', run_exp_362),
        '363': ('exp363_learned_pk', run_exp_363),
        '364': ('exp364_combined_best', run_exp_364),
    }

    if args.quick:
        seeds = SEEDS_QUICK
        train_kw = {'epochs': QUICK_EPOCHS, 'patience': QUICK_PATIENCE}
        max_patients = QUICK_PATIENTS
    else:
        seeds = SEEDS
        train_kw = {'epochs': 60, 'patience': 15}
        max_patients = None

    to_run = list(experiments.keys()) if args.experiment == 'all' else [args.experiment]

    for exp_id in to_run:
        if exp_id not in experiments:
            print(f"Unknown experiment: {exp_id}")
            continue
        name, runner = experiments[exp_id]
        print(f"\n{'='*60}")
        print(f"{name}")
        print(f"{'='*60}")
        results = runner(args, seeds=seeds, train_kw=train_kw,
                         max_patients=max_patients)
        save_results(results, name)

        # Print summary
        if 'summary' in results:
            print(f"\n─── Summary ───")
            for variant, stats in results['summary'].items():
                h_str = ', '.join(
                    f"{k}={v['mean']:.1f}±{v['std']:.1f}"
                    for k, v in stats['mae_per_horizon'].items())
                print(f"  {variant}: MAE={stats['mae_overall_mean']:.1f}"
                      f"±{stats['mae_overall_std']:.1f} [{h_str}]")


if __name__ == '__main__':
    main()
