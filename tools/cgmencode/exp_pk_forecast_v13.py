#!/usr/bin/env python3
"""EXP-403 & EXP-404: Feature Engineering for Forecasting

WHEN TO RUN: After v12 (EXP-399–402) is complete. These experiments add new
feature channels to the champion architecture, complementing v12's training
and fine-tuning improvements.

These experiments apply the two most promising UNTESTED feature engineering
techniques from the evidence synthesis report (§1.6, §3.5, §3.6):

EXP-403: Multi-Rate EMA Channels for Forecasting
  - Add 4 EMA channels (α=0.7/0.3/0.1/0.03) to glucose input
  - Half-lives: 10min, 30min, 95min, 5.5h — captures multi-scale trends
  - Constant-width representation regardless of history length
  - Particularly relevant for longer history windows (8h+)
  - Evidence: Multi-rate EMA is theoretically the cleanest long-horizon
    representation (§1.6.5). EMA at α=0.1 approximates STL trend component.
  - Test on: Champion dual encoder + shared ResNet ensemble (EXP-387 arch)
  - Hypothesis: -0.5 to -1.5 MAE (adds trend info without smoothing destruction)

EXP-404: Glucodensity Head Injection for Forecasting
  - Add 8-bin glucodensity histogram at forecast head (NOT as conv input)
  - Head injection proven: EXP-338 Override F1 +0.006, ECE -16%
  - Glucodensity: EXP-330 Silhouette = 0.965 vs TIR = 0.422
  - Distributional summary tells the model "what range was glucose in?"
    which helps forecast: if glucose has been in tight range, predict tighter
  - Also add functional depth (1 scalar) as atypicality signal
  - Hypothesis: -0.3 to -1.0 MAE (distributional context helps prediction)

IMPORTS: Uses feature_helpers.py for multi_rate_ema_batch(), glucodensity_head_features(),
  functional_depth_features(). These are new shared utilities.

ARCHITECTURE NOTE: Glucodensity/depth are head-injected (after conv pooling),
  NOT as input channels. Tiling scalars into CNN gives zero temporal gradient
  (EXP-359 lesson). Head injection avoids this.

Usage:
    python tools/cgmencode/exp_pk_forecast_v13.py --experiment 403 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v13.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse, copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import champion architecture and data loading from v12
try:
    from exp_pk_forecast_v12 import (
        load_forecast_data, load_patient_profile_isf,
        ResBlock1d, ResNetCNNWithFuture, DualEncoderWithFuture,
        train_model, evaluate_model,
        GLUCOSE_SCALE, HORIZONS_STANDARD, HORIZONS_EXTENDED,
        _save_results,
    )
except ImportError:
    print("ERROR: exp_pk_forecast_v12.py must be available (champion architecture)")
    print("Run from tools/cgmencode/ directory or add to path")
    sys.exit(1)

from feature_helpers import (
    multi_rate_ema_batch, glucodensity_head_features,
    functional_depth_features, compute_head_features,
)

# Clinical metrics are wired into v12's evaluate_model() — every call to
# evaluate_model() automatically computes MARD, Clarke zones, ISO 15197,
# and trend accuracy. Results are stored in result['clinical'].
# No additional code needed here.

# ---------------------------------------------------------------------------
# EXP-403: Multi-Rate EMA Channels
# ---------------------------------------------------------------------------

EMA_ALPHAS = (0.7, 0.3, 0.1, 0.03)


class DualEncoderWithEMA(nn.Module):
    """Champion dual encoder + extra EMA channels on glucose branch.

    The glucose branch gets 4 additional EMA channels (total: 1+4=5 glucose
    channels) while the PK/ISF branch stays unchanged. This lets the temporal
    encoder see smoothed trend information at multiple rates.
    """

    def __init__(self, n_glucose_ch=5, n_pk_ch=7, hidden=64,
                 n_horizons=3, n_ema=4):
        super().__init__()
        # Glucose branch: raw glucose + EMA channels
        self.glucose_enc = nn.Sequential(
            nn.Conv1d(n_glucose_ch, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            ResBlock1d(hidden, hidden),
            ResBlock1d(hidden, hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        # PK branch (unchanged from champion)
        self.pk_enc = nn.Sequential(
            nn.Conv1d(n_pk_ch, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            ResBlock1d(hidden, hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(hidden, n_horizons),
        )

    def forward(self, x_glucose, x_pk):
        # x_glucose: (B, T, 1+n_ema) → (B, 1+n_ema, T)
        g = self.glucose_enc(x_glucose.permute(0, 2, 1)).squeeze(-1)
        p = self.pk_enc(x_pk.permute(0, 2, 1)).squeeze(-1)
        return self.head(torch.cat([g, p], dim=1))


def prepare_ema_data(base_windows, pk_windows, history_steps):
    """Add EMA channels to glucose data.

    Args:
        base_windows: (N, T, C_base) base feature windows
        pk_windows: (N, T, C_pk) PK feature windows
        history_steps: Number of history steps

    Returns:
        glucose_with_ema: (N, history_steps, 1+n_ema) glucose + EMA channels
        pk_history: (N, history_steps, C_pk) PK channels (history only)
    """
    # Extract glucose channel (index 0) from history portion
    glucose = base_windows[:, :history_steps, 0:1]  # (N, H, 1)

    # Compute multi-rate EMA on glucose
    ema_channels = multi_rate_ema_batch(
        base_windows[:, :history_steps, :],
        glucose_channel=0, alphas=EMA_ALPHAS
    )  # (N, H, 4)

    glucose_with_ema = np.concatenate([glucose, ema_channels], axis=2)  # (N, H, 5)

    # PK channels: history portion
    pk_history = pk_windows[:, :history_steps, :]  # (N, H, C_pk)

    return glucose_with_ema, pk_history


def run_exp403(args):
    """EXP-403: Multi-Rate EMA Channels for Forecasting."""
    print("\n" + "=" * 70)
    print("EXP-403: Multi-Rate EMA Channels for Forecasting")
    print("=" * 70)

    device = torch.device(args.device)
    horizons = HORIZONS_STANDARD if args.quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)

    # Load data (same as v12)
    data = load_forecast_data(
        args.patients_dir,
        max_patients=4 if args.quick else 11,
        max_horizon=max(horizons.values()),
    )

    base_train, pk_train = data['train_base'], data['train_pk']
    base_val, pk_val = data['val_base'], data['val_pk']
    targets_train, targets_val = data['train_targets'], data['val_targets']
    history_steps = data['history_steps']

    # Prepare EMA-augmented glucose data
    glu_ema_train, pk_hist_train = prepare_ema_data(base_train, pk_train, history_steps)
    glu_ema_val, pk_hist_val = prepare_ema_data(base_val, pk_val, history_steps)

    results = {}
    seeds = [42] if args.quick else [42, 123, 456]

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)

        # --- Variant A: Champion without EMA (control) ---
        print(f"\n  [seed={seed}] Control: champion dual encoder (no EMA)...")
        ctrl_glu = base_train[:, :history_steps, 0:1]
        ctrl_glu_val = base_val[:, :history_steps, 0:1]

        model_ctrl = DualEncoderWithEMA(
            n_glucose_ch=1, n_pk_ch=pk_hist_train.shape[2],
            hidden=64, n_horizons=n_horizons, n_ema=0
        ).to(device)

        train_ds = TensorDataset(
            torch.FloatTensor(ctrl_glu), torch.FloatTensor(pk_hist_train),
            torch.FloatTensor(targets_train[:, list(horizons.values())])
        )
        val_ds = TensorDataset(
            torch.FloatTensor(ctrl_glu_val), torch.FloatTensor(pk_hist_val),
            torch.FloatTensor(targets_val[:, list(horizons.values())])
        )
        train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=512)

        # Simple training loop (adapted for dual-input model)
        optimizer = torch.optim.Adam(model_ctrl.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)
        epochs = 30 if args.quick else 80

        best_val_loss = float('inf')
        best_state = None
        for epoch in range(epochs):
            model_ctrl.train()
            for glu_b, pk_b, tgt_b in train_loader:
                glu_b, pk_b, tgt_b = glu_b.to(device), pk_b.to(device), tgt_b.to(device)
                pred = model_ctrl(glu_b, pk_b)
                loss = F.mse_loss(pred, tgt_b)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model_ctrl.eval()
            val_losses = []
            with torch.no_grad():
                for glu_b, pk_b, tgt_b in val_loader:
                    glu_b, pk_b, tgt_b = glu_b.to(device), pk_b.to(device), tgt_b.to(device)
                    pred = model_ctrl(glu_b, pk_b)
                    val_losses.append(F.mse_loss(pred, tgt_b).item())
            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = copy.deepcopy(model_ctrl.state_dict())

        model_ctrl.load_state_dict(best_state)
        ctrl_res = evaluate_model(model_ctrl, val_loader, device, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ctrl_res['mae_per_horizon'].items())
        print(f"    Control: MAE={ctrl_res['mae_overall']:.1f} [{h_str}]")
        results[f'control_no_ema_s{seed}'] = ctrl_res

        # --- Variant B: Champion + 4 EMA channels ---
        print(f"  [seed={seed}] With EMA: 4 multi-rate channels...")

        model_ema = DualEncoderWithEMA(
            n_glucose_ch=1 + len(EMA_ALPHAS),
            n_pk_ch=pk_hist_train.shape[2],
            hidden=64, n_horizons=n_horizons,
            n_ema=len(EMA_ALPHAS)
        ).to(device)

        train_ds_ema = TensorDataset(
            torch.FloatTensor(glu_ema_train), torch.FloatTensor(pk_hist_train),
            torch.FloatTensor(targets_train[:, list(horizons.values())])
        )
        val_ds_ema = TensorDataset(
            torch.FloatTensor(glu_ema_val), torch.FloatTensor(pk_hist_val),
            torch.FloatTensor(targets_val[:, list(horizons.values())])
        )
        train_loader_ema = DataLoader(train_ds_ema, batch_size=256, shuffle=True)
        val_loader_ema = DataLoader(val_ds_ema, batch_size=512)

        optimizer = torch.optim.Adam(model_ema.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)

        best_val_loss = float('inf')
        best_state = None
        for epoch in range(epochs):
            model_ema.train()
            for glu_b, pk_b, tgt_b in train_loader_ema:
                glu_b, pk_b, tgt_b = glu_b.to(device), pk_b.to(device), tgt_b.to(device)
                pred = model_ema(glu_b, pk_b)
                loss = F.mse_loss(pred, tgt_b)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model_ema.eval()
            val_losses = []
            with torch.no_grad():
                for glu_b, pk_b, tgt_b in val_loader_ema:
                    glu_b, pk_b, tgt_b = glu_b.to(device), pk_b.to(device), tgt_b.to(device)
                    pred = model_ema(glu_b, pk_b)
                    val_losses.append(F.mse_loss(pred, tgt_b).item())
            val_loss = np.mean(val_losses)
            scheduler.step(val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = copy.deepcopy(model_ema.state_dict())

        model_ema.load_state_dict(best_state)
        ema_res = evaluate_model(model_ema, val_loader_ema, device, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ema_res['mae_per_horizon'].items())
        delta = ema_res['mae_overall'] - ctrl_res['mae_overall']
        print(f"    With EMA: MAE={ema_res['mae_overall']:.1f} [{h_str}] Δ={delta:+.1f}")
        results[f'with_ema_s{seed}'] = ema_res

    _save_results('exp403_multi_rate_ema',
                  'Multi-rate EMA channels for forecasting',
                  results, horizons,
                  'externals/experiments/exp403_multi_rate_ema.json')


# ---------------------------------------------------------------------------
# EXP-404: Glucodensity + Depth Head Injection for Forecasting
# ---------------------------------------------------------------------------

class DualEncoderWithHeadFeatures(nn.Module):
    """Champion dual encoder + glucodensity/depth injected at forecast head.

    Architecture:
      glucose_enc: Conv1d → ResBlock → pool → (B, hidden)
      pk_enc: Conv1d → ResBlock → pool → (B, hidden)
      head: Linear(hidden*2 + n_head_features, hidden) → Linear(hidden, n_horizons)

    The n_head_features bypass the convolutional layers entirely, avoiding the
    zero-gradient problem with scalar features in conv input channels.
    """

    def __init__(self, n_glucose_ch=1, n_pk_ch=7, hidden=64,
                 n_horizons=3, n_head_features=9):
        super().__init__()
        self.glucose_enc = nn.Sequential(
            nn.Conv1d(n_glucose_ch, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            ResBlock1d(hidden, hidden),
            ResBlock1d(hidden, hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        self.pk_enc = nn.Sequential(
            nn.Conv1d(n_pk_ch, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            ResBlock1d(hidden, hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden * 2 + n_head_features, hidden),
            nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(hidden, n_horizons),
        )

    def forward(self, x_glucose, x_pk, head_features):
        g = self.glucose_enc(x_glucose.permute(0, 2, 1)).squeeze(-1)
        p = self.pk_enc(x_pk.permute(0, 2, 1)).squeeze(-1)
        combined = torch.cat([g, p, head_features], dim=1)
        return self.head(combined)


def run_exp404(args):
    """EXP-404: Glucodensity + Depth Head Injection for Forecasting."""
    print("\n" + "=" * 70)
    print("EXP-404: Glucodensity + Depth Head Injection for Forecasting")
    print("=" * 70)

    device = torch.device(args.device)
    horizons = HORIZONS_STANDARD if args.quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    N_GD_BINS = 8

    data = load_forecast_data(
        args.patients_dir,
        max_patients=4 if args.quick else 11,
        max_horizon=max(horizons.values()),
    )

    base_train, pk_train = data['train_base'], data['train_pk']
    base_val, pk_val = data['val_base'], data['val_pk']
    targets_train, targets_val = data['train_targets'], data['val_targets']
    history_steps = data['history_steps']

    # Compute head features: glucodensity (8 bins) + depth (1 scalar) = 9 features
    print("  Computing glucodensity + depth features...")
    head_train, feat_names = compute_head_features(
        base_train[:, :history_steps, :], glucose_channel=0, n_gd_bins=N_GD_BINS)
    head_val, _ = compute_head_features(
        base_val[:, :history_steps, :], glucose_channel=0, n_gd_bins=N_GD_BINS)
    n_head = head_train.shape[1]
    print(f"  Head features: {n_head} dims ({feat_names})")

    # Glucose and PK history
    glu_train = base_train[:, :history_steps, 0:1]
    glu_val = base_val[:, :history_steps, 0:1]
    pk_hist_train = pk_train[:, :history_steps, :]
    pk_hist_val = pk_val[:, :history_steps, :]

    results = {}
    seeds = [42] if args.quick else [42, 123, 456]

    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)

        # --- Variant A: Control (no head features) ---
        print(f"\n  [seed={seed}] Control (no head features)...")
        zeros_train = np.zeros((len(glu_train), n_head), dtype=np.float32)
        zeros_val = np.zeros((len(glu_val), n_head), dtype=np.float32)

        model_ctrl = DualEncoderWithHeadFeatures(
            n_glucose_ch=1, n_pk_ch=pk_hist_train.shape[2],
            hidden=64, n_horizons=n_horizons, n_head_features=n_head
        ).to(device)

        tgt_train = targets_train[:, list(horizons.values())]
        tgt_val = targets_val[:, list(horizons.values())]

        train_ds = TensorDataset(
            torch.FloatTensor(glu_train), torch.FloatTensor(pk_hist_train),
            torch.FloatTensor(zeros_train), torch.FloatTensor(tgt_train))
        val_ds = TensorDataset(
            torch.FloatTensor(glu_val), torch.FloatTensor(pk_hist_val),
            torch.FloatTensor(zeros_val), torch.FloatTensor(tgt_val))
        train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=512)

        epochs = 30 if args.quick else 80
        optimizer = torch.optim.Adam(model_ctrl.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)

        best_val_loss, best_state = float('inf'), None
        for epoch in range(epochs):
            model_ctrl.train()
            for glu_b, pk_b, hf_b, tgt_b in train_loader:
                glu_b = glu_b.to(device)
                pk_b = pk_b.to(device)
                hf_b = hf_b.to(device)
                tgt_b = tgt_b.to(device)
                pred = model_ctrl(glu_b, pk_b, hf_b)
                loss = F.mse_loss(pred, tgt_b)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model_ctrl.eval()
            vl = []
            with torch.no_grad():
                for glu_b, pk_b, hf_b, tgt_b in val_loader:
                    pred = model_ctrl(glu_b.to(device), pk_b.to(device),
                                      hf_b.to(device))
                    vl.append(F.mse_loss(pred, tgt_b.to(device)).item())
            val_loss = np.mean(vl)
            scheduler.step(val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = copy.deepcopy(model_ctrl.state_dict())

        model_ctrl.load_state_dict(best_state)
        ctrl_res = evaluate_model(model_ctrl, val_loader, device, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ctrl_res['mae_per_horizon'].items())
        print(f"    Control: MAE={ctrl_res['mae_overall']:.1f} [{h_str}]")
        results[f'control_no_head_s{seed}'] = ctrl_res

        # --- Variant B: With glucodensity + depth ---
        print(f"  [seed={seed}] With glucodensity ({N_GD_BINS} bins) + depth...")

        model_hf = DualEncoderWithHeadFeatures(
            n_glucose_ch=1, n_pk_ch=pk_hist_train.shape[2],
            hidden=64, n_horizons=n_horizons, n_head_features=n_head
        ).to(device)

        train_ds_hf = TensorDataset(
            torch.FloatTensor(glu_train), torch.FloatTensor(pk_hist_train),
            torch.FloatTensor(head_train), torch.FloatTensor(tgt_train))
        val_ds_hf = TensorDataset(
            torch.FloatTensor(glu_val), torch.FloatTensor(pk_hist_val),
            torch.FloatTensor(head_val), torch.FloatTensor(tgt_val))
        train_loader_hf = DataLoader(train_ds_hf, batch_size=256, shuffle=True)
        val_loader_hf = DataLoader(val_ds_hf, batch_size=512)

        optimizer = torch.optim.Adam(model_hf.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)

        best_val_loss, best_state = float('inf'), None
        for epoch in range(epochs):
            model_hf.train()
            for glu_b, pk_b, hf_b, tgt_b in train_loader_hf:
                glu_b = glu_b.to(device)
                pk_b = pk_b.to(device)
                hf_b = hf_b.to(device)
                tgt_b = tgt_b.to(device)
                pred = model_hf(glu_b, pk_b, hf_b)
                loss = F.mse_loss(pred, tgt_b)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model_hf.eval()
            vl = []
            with torch.no_grad():
                for glu_b, pk_b, hf_b, tgt_b in val_loader_hf:
                    pred = model_hf(glu_b.to(device), pk_b.to(device),
                                    hf_b.to(device))
                    vl.append(F.mse_loss(pred, tgt_b.to(device)).item())
            val_loss = np.mean(vl)
            scheduler.step(val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = copy.deepcopy(model_hf.state_dict())

        model_hf.load_state_dict(best_state)
        hf_res = evaluate_model(model_hf, val_loader_hf, device, horizons)
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in hf_res['mae_per_horizon'].items())
        delta = hf_res['mae_overall'] - ctrl_res['mae_overall']
        print(f"    With head: MAE={hf_res['mae_overall']:.1f} [{h_str}] Δ={delta:+.1f}")
        results[f'with_gd_depth_s{seed}'] = hf_res

    _save_results('exp404_glucodensity_head',
                  'Glucodensity + depth head injection for forecasting',
                  results, horizons,
                  'externals/experiments/exp404_glucodensity_head.json')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='EXP-403–404: Feature engineering for forecasting')
    parser.add_argument('--experiment', type=str, default='all',
                        help='403, 404, or "all"')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, fewer epochs')
    args = parser.parse_args()

    experiments = {
        '403': run_exp403,
        '404': run_exp404,
    }

    if args.experiment == 'all':
        for name, fn in experiments.items():
            fn(args)
    elif args.experiment in experiments:
        experiments[args.experiment](args)
    else:
        print(f"Unknown experiment: {args.experiment}")
        print(f"Available: {', '.join(experiments.keys())}, all")
        sys.exit(1)


if __name__ == '__main__':
    main()
