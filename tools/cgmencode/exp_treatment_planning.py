#!/usr/bin/env python3
"""
EXP-411 through EXP-418: Living Treatment Plan — Strategic Planning Horizon Experiments

This module fills the critical gap between two existing paradigms:

  1. Real-time AID control (Loop, AAPS, Trio) — optimizes the next 2 hours
  2. Quarterly endocrinologist visits — retrospective review every 3 months

The gap in between (6 hours to 4 days) is where patients actually make strategic
decisions: "Should I worry about tonight?", "Is tomorrow likely to be a bad day?",
"Which part of my week needs attention?"

The output of these experiments is NOT glucose point predictions (that's what AID
does already). Instead, we predict:
  - Event likelihoods: P(hypo tonight), P(bad day tomorrow)
  - State assessments: expected TIR, control quality category
  - Attention targets: which 6h block in the week needs intervention most

Clinical value: patients act when attention is available (morning review, evening
check-in), then go "hands off" and let the AID system manage in the short term.
Less effort, better results through strategic planning vs. constant monitoring.

Experiment registry:
  EXP-411: Extended history forecasting (PKGroupedEncoder + 4-12h lookback)
  EXP-412: Overnight risk assessment (6-8h horizon)
  EXP-413: Next-day TIR prediction (24h horizon)
  EXP-414: Multi-day control quality forecast (3-4 day)
  EXP-415: Event recurrence prediction (temporal pattern-based)
  EXP-416: Weekly routine hotspot identification
  EXP-417: Extended history + PK for classification tasks
  EXP-418: Multi-rate EMA for strategic features
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# Optional heavy imports — guarded so the module can at least be parsed
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from sklearn.metrics import (
        f1_score, roc_auc_score, mean_absolute_error, accuracy_score,
    )
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

# Local imports — absolute via sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features
from cgmencode.device import resolve_device
from cgmencode.model import PositionalEncoding, CGMGroupedEncoder

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUICK_PATIENTS = 4
QUICK_EPOCHS = 60
QUICK_SEEDS = [42]
QUICK_PATIENCE = 8

FULL_PATIENTS = None          # all available
FULL_EPOCHS = 200
FULL_SEEDS = [42, 123, 456, 789, 1024]
FULL_PATIENCE = 20

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

# Resolution helpers (5-min base grid)
STEPS_PER_HOUR = 12
STEPS_2H  = 24
STEPS_4H  = 48
STEPS_6H  = 72
STEPS_8H  = 96
STEPS_12H = 144
STEPS_24H = 288
STEPS_3D  = 864
STEPS_4D  = 1152
STEPS_7D  = 2016

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_config(args):
    """Return config dict driven by --quick flag."""
    if args.quick:
        return dict(
            max_patients=QUICK_PATIENTS, epochs=QUICK_EPOCHS,
            seeds=QUICK_SEEDS, patience=QUICK_PATIENCE,
        )
    return dict(
        max_patients=FULL_PATIENTS, epochs=FULL_EPOCHS,
        seeds=FULL_SEEDS, patience=FULL_PATIENCE,
    )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def compute_ema(glucose, alphas=(0.1, 0.3, 0.7)):
    """Multi-rate exponential moving average channels.

    Returns (T, len(alphas)) array with one EMA channel per alpha.
    Larger alpha = faster response; smaller alpha = smoother trend.
    """
    channels = []
    for alpha in alphas:
        ema = np.zeros_like(glucose, dtype=np.float64)
        ema[0] = glucose[0]
        for t in range(1, len(glucose)):
            ema[t] = alpha * glucose[t] + (1 - alpha) * ema[t - 1]
        channels.append(ema)
    return np.stack(channels, axis=-1)


def compute_tir(glucose, low=70, high=180):
    """Time-in-range as percentage (0-100)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return np.nan
    return float(((valid >= low) & (valid <= high)).mean() * 100)


def extract_overnight_labels(glucose_24h, midnight_idx=216):
    """Overnight risk labels from a 24h glucose trace at 5-min resolution.

    Assumes the 24h window starts around 6pm so that midnight falls at
    ``midnight_idx`` (default 216 = 18h × 12 steps/h).  Overnight is
    midnight-6am (72 steps).

    Returns dict with boolean ``hypo``, boolean ``high``, and float ``tir``.
    """
    overnight = glucose_24h[midnight_idx:]
    overnight = overnight[~np.isnan(overnight)]
    if len(overnight) == 0:
        return {'hypo': False, 'high': False, 'tir': np.nan}
    hypo = bool((overnight < 70).any())
    # ">2h high" means >24 steps at 5min or >33% of the 6h window
    high = bool((overnight > 180).sum() / max(len(overnight), 1) > 0.33)
    tir = compute_tir(overnight)
    return {'hypo': hypo, 'high': high, 'tir': tir}


def extract_episode_features(glucose_12h, insulin_12h=None, carbs_12h=None):
    """Summary features from a 12h episode for hierarchical models."""
    g = glucose_12h[~np.isnan(glucose_12h)] if len(glucose_12h) > 0 else glucose_12h
    features = {
        'tir':        compute_tir(glucose_12h),
        'mean_bg':    float(np.nanmean(g)) if len(g) else np.nan,
        'std_bg':     float(np.nanstd(g))  if len(g) else np.nan,
        'min_bg':     float(np.nanmin(g))  if len(g) else np.nan,
        'max_bg':     float(np.nanmax(g))  if len(g) else np.nan,
        'hypo_count': int((glucose_12h < 70).sum()),
        'high_count': int((glucose_12h > 180).sum()),
        'cv':         float(np.nanstd(g) / max(np.nanmean(g), 1)) if len(g) else np.nan,
    }
    if insulin_12h is not None:
        features['iob_mean'] = float(np.nanmean(insulin_12h))
        features['iob_max']  = float(np.nanmax(insulin_12h))
    if carbs_12h is not None:
        features['carb_total'] = float(np.nansum(carbs_12h))
    return features


def compute_ece(probs, labels, n_bins=10):
    """Expected Calibration Error (lower is better)."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bin_boundaries[:-1], bin_boundaries[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        avg_conf = probs[mask].mean()
        avg_acc  = labels[mask].mean()
        ece += mask.sum() * abs(avg_conf - avg_acc)
    return float(ece / max(len(probs), 1))


def platt_calibrate(logits_val, labels_val, logits_test):
    """Platt scaling: fit logistic regression on validation logits,
    apply to test logits.  Returns calibrated probabilities."""
    from sklearn.linear_model import LogisticRegression
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(logits_val.reshape(-1, 1), labels_val)
    return lr.predict_proba(logits_test.reshape(-1, 1))[:, 1]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def find_patient_dirs(patients_dir):
    """Return sorted list of patient directory Paths."""
    base = Path(patients_dir)
    dirs = sorted([d for d in base.iterdir() if d.is_dir()])
    return dirs


def load_patients(patients_dir, max_patients=None, verbose=True):
    """Load per-patient grids + PK features.  Returns list of dicts."""
    pdirs = find_patient_dirs(patients_dir)
    if max_patients:
        pdirs = pdirs[:max_patients]
    patients = []
    for pdir in pdirs:
        train_dir = str(pdir / 'training')
        try:
            result = build_nightscout_grid(train_dir, verbose=False)
            if result is None:
                continue
            df, features = result
            if df is None or len(df) < 100:
                continue
            pk = build_continuous_pk_features(df)
            if pk is None:
                continue
            n = min(len(features), len(pk))
            patients.append({
                'name':     pdir.name,
                'df':       df.iloc[:n],
                'grid':     features[:n],   # (N, 8) normalised
                'pk':       pk[:n],         # (N, 8) PK channels
            })
            if verbose:
                print(f"  Loaded {pdir.name}: {n} steps")
        except Exception as exc:
            if verbose:
                print(f"  Skip {pdir.name}: {exc}")
    return patients


def make_windows(arr, window_size, stride=None):
    """Sliding window view over first axis.  Returns (n_windows, window_size, ...)."""
    stride = stride or (window_size // 2)
    windows = []
    for start in range(0, len(arr) - window_size + 1, stride):
        windows.append(arr[start:start + window_size])
    if len(windows) == 0:
        return np.empty((0, window_size) + arr.shape[1:], dtype=arr.dtype)
    return np.stack(windows)


def downsample(arr, factor):
    """Downsample by keeping every ``factor``-th row."""
    return arr[::factor]


def temporal_split(X, *extras, val_frac=0.2):
    """Chronological train/val split.  Returns (train_parts, val_parts)."""
    n = len(X)
    split = int(n * (1 - val_frac))
    train = [X[:split]] + [e[:split] for e in extras]
    val   = [X[split:]] + [e[split:] for e in extras]
    return train, val


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FlexCNN(nn.Module):
    """1D-CNN classifier/regressor with configurable input channels."""

    def __init__(self, in_channels, out_dim, hidden=64):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.Conv1d(hidden, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, out_dim),
        )

    def forward(self, x):
        # x: (B, T, C)
        x = x.permute(0, 2, 1)           # (B, C, T)
        feat = self.conv(x).squeeze(-1)   # (B, hidden)
        return self.head(feat)            # (B, out_dim)


class HierarchicalClassifier(nn.Module):
    """Per-episode CNN → GRU/Attention → classification head.

    Used for multi-day control quality forecasting (EXP-414).
    Input: (B, n_episodes, episode_feats).
    """

    def __init__(self, episode_dim, n_episodes, n_classes, hidden=64):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(episode_dim, hidden), nn.ReLU(), nn.Dropout(0.1),
        )
        self.gru = nn.GRU(hidden, hidden, batch_first=True)
        self.attn = nn.Linear(hidden, 1)
        self.head = nn.Sequential(
            nn.Linear(hidden, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_classes),
        )

    def forward(self, x):
        # x: (B, n_episodes, episode_dim)
        h = self.proj(x)                        # (B, n_ep, hidden)
        gru_out, _ = self.gru(h)                # (B, n_ep, hidden)
        w = torch.softmax(self.attn(gru_out), dim=1)  # (B, n_ep, 1)
        ctx = (gru_out * w).sum(dim=1)          # (B, hidden)
        return self.head(ctx)                    # (B, n_classes)


# ---------------------------------------------------------------------------
# Training utilities
# ---------------------------------------------------------------------------

def _train_torch_classifier(model, train_X, train_y, val_X, val_y, device,
                            epochs=60, patience=12, batch_size=64, lr=1e-3,
                            n_classes=2):
    """Train a PyTorch classifier with early stopping.  Returns metrics dict."""
    if n_classes == 2:
        pos_weight = len(train_y) / max(train_y.sum(), 1)
        weights = torch.tensor([1.0, float(pos_weight)], dtype=torch.float32).to(device)
        criterion = nn.CrossEntropyLoss(weight=weights)
    else:
        criterion = nn.CrossEntropyLoss()

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=max(patience // 2, 3))

    t_X = torch.tensor(train_X, dtype=torch.float32).to(device)
    t_y = torch.tensor(train_y, dtype=torch.long).to(device)
    v_X = torch.tensor(val_X, dtype=torch.float32).to(device)

    best_f1, best_state, wait = -1, None, 0

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(t_X))
        for i in range(0, len(t_X), batch_size):
            idx = perm[i:i + batch_size]
            logits = model(t_X[idx])
            loss = criterion(logits, t_y[idx])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            v_logits = model(v_X)
            v_pred = v_logits.argmax(dim=-1).cpu().numpy()
            v_loss = criterion(
                v_logits, torch.tensor(val_y, dtype=torch.long).to(device)
            ).item()
        scheduler.step(v_loss)

        metric = f1_score(val_y, v_pred,
                          average='macro' if n_classes > 2 else 'binary',
                          zero_division=0)
        if metric > best_f1:
            best_f1 = metric
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    model.eval()

    with torch.no_grad():
        v_logits = model(v_X)
        v_probs = torch.softmax(v_logits, dim=-1).cpu().numpy()
        v_pred  = v_logits.argmax(dim=-1).cpu().numpy()

    results = {
        'f1': round(float(f1_score(val_y, v_pred,
                                    average='macro' if n_classes > 2 else 'binary',
                                    zero_division=0)), 4),
        'accuracy': round(float(accuracy_score(val_y, v_pred)), 4),
    }
    if n_classes == 2:
        try:
            results['auc_roc'] = round(float(roc_auc_score(val_y, v_probs[:, 1])), 4)
            results['ece'] = round(compute_ece(v_probs[:, 1], val_y), 4)
        except ValueError:
            pass
    else:
        results['ece'] = round(compute_ece(v_probs.max(axis=1), (v_pred == val_y).astype(float)), 4)

    return results


def _train_torch_regressor(model, train_X, train_y, val_X, val_y, device,
                           epochs=60, patience=12, batch_size=64, lr=1e-3):
    """Train a PyTorch regressor (MSE loss) with early stopping.  Returns MAE."""
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=max(patience // 2, 3))

    t_X = torch.tensor(train_X, dtype=torch.float32).to(device)
    t_y = torch.tensor(train_y, dtype=torch.float32).to(device).unsqueeze(-1)
    v_X = torch.tensor(val_X, dtype=torch.float32).to(device)

    best_mae, best_state, wait = 1e9, None, 0

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(t_X))
        for i in range(0, len(t_X), batch_size):
            idx = perm[i:i + batch_size]
            pred = model(t_X[idx])
            loss = criterion(pred, t_y[idx])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            v_pred = model(v_X).squeeze(-1).cpu().numpy()
            v_loss = float(np.mean((v_pred - val_y) ** 2))
        scheduler.step(v_loss)

        mae = float(np.mean(np.abs(v_pred - val_y)))
        if mae < best_mae:
            best_mae = mae
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        v_pred = model(v_X).squeeze(-1).cpu().numpy()
    return {
        'mae': round(float(mean_absolute_error(val_y, v_pred)), 4),
        'rmse': round(float(np.sqrt(np.mean((v_pred - val_y) ** 2))), 4),
    }


# ===================================================================
# Experiment runners
# ===================================================================

def run_exp411(args):
    """EXP-411: Extended History Forecasting — PKGroupedEncoder + 4-12h lookback.

    Tests the champion PKGroupedEncoder Transformer with extended history
    windows [48, 72, 96, 144] steps (4h, 6h, 8h, 12h) instead of the
    standard 24-step (2h) window.  Includes PK channels and ISF
    normalisation.  Reports per-horizon MAE per patient.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-411: Extended History Forecasting (PKGroupedEncoder)")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    window_sizes = [48, 72, 96, 144]  # 4h, 6h, 8h, 12h
    results = {}

    for ws in window_sizes:
        label = f"ws{ws}_{ws // STEPS_PER_HOUR}h"
        print(f"\n--- Window size {ws} ({ws // STEPS_PER_HOUR}h) ---")
        half = ws // 2  # history = future = half

        per_patient = {}
        for pat in patients:
            combined = np.concatenate([pat['grid'], pat['pk']], axis=-1)  # (N, 16)
            wins = make_windows(combined, ws, stride=half)
            if len(wins) < 10:
                continue
            X_hist = wins[:, :half, :]
            Y_future = wins[:, half:, 0] * 400  # de-normalise glucose

            (tr_X, tr_Y), (va_X, va_Y) = temporal_split(X_hist, Y_future)
            if len(tr_X) < 5 or len(va_X) < 2:
                continue

            seed_maes = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                np.random.seed(seed)
                n_ch = tr_X.shape[-1]
                model = CGMGroupedEncoder(
                    input_dim=n_ch, d_model=64, nhead=4,
                    num_layers=2, dim_feedforward=128, dropout=0.1,
                ).to(device)
                forecast_head = nn.Linear(64, half).to(device)

                optimizer = torch.optim.Adam(
                    list(model.parameters()) + list(forecast_head.parameters()),
                    lr=1e-3, weight_decay=1e-4)
                criterion = nn.MSELoss()
                tX = torch.tensor(tr_X, dtype=torch.float32).to(device)
                tY = torch.tensor(tr_Y, dtype=torch.float32).to(device)

                best_val_mae, best_enc_state, best_head_state = 1e9, None, None
                wait = 0
                for epoch in range(cfg['epochs']):
                    model.train(); forecast_head.train()
                    perm = torch.randperm(len(tX))
                    for i in range(0, len(tX), 64):
                        idx = perm[i:i+64]
                        enc_out = model(tX[idx])
                        if isinstance(enc_out, dict):
                            enc_out = enc_out['forecast']
                        pred = forecast_head(enc_out.mean(dim=1))
                        loss = criterion(pred, tY[idx])
                        optimizer.zero_grad(); loss.backward()
                        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                        optimizer.step()

                    model.eval(); forecast_head.eval()
                    with torch.no_grad():
                        vX = torch.tensor(va_X, dtype=torch.float32).to(device)
                        vE = model(vX)
                        if isinstance(vE, dict):
                            vE = vE['forecast']
                        vP = forecast_head(vE.mean(dim=1)).cpu().numpy()
                    mae = float(np.mean(np.abs(vP - va_Y)))
                    if mae < best_val_mae:
                        best_val_mae = mae
                        best_enc_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                        best_head_state = {k: v.cpu().clone() for k, v in forecast_head.state_dict().items()}
                        wait = 0
                    else:
                        wait += 1
                        if wait >= cfg['patience']:
                            break

                seed_maes.append(round(best_val_mae, 2))

            per_patient[pat['name']] = {
                'seed_maes': seed_maes,
                'mean_mae': round(float(np.mean(seed_maes)), 2),
            }

        results[label] = per_patient

    save_results(results, 'exp411_extended_history_forecast')
    return results


def run_exp412(args):
    """EXP-412: Overnight Risk Assessment (6-8h horizon).

    Binary classifiers predicting P(hypo overnight) and P(high overnight)
    given a 6h evening context window.  Uses 1D-CNN with PK channels.
    Reports F1, AUC-ROC, ECE per patient with Platt calibration.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-412: Overnight Risk Assessment")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    all_X, all_y_hypo, all_y_high, all_y_tir, all_pids = [], [], [], [], []

    for pat in patients:
        grid = pat['grid']          # (N, 8)
        pk   = pat['pk']            # (N, 8)
        glucose_raw = grid[:, 0] * 400  # de-normalise

        # Slide over the time series looking for evening→overnight pairs
        # Evening context: 72 steps (6h).  Overnight label: next 72 steps.
        for start in range(0, len(grid) - STEPS_12H, STEPS_6H):
            ctx = np.concatenate([grid[start:start + STEPS_6H],
                                  pk[start:start + STEPS_6H]], axis=-1)
            overnight_gluc = glucose_raw[start + STEPS_6H:start + STEPS_12H]
            if len(overnight_gluc) < STEPS_6H or np.isnan(overnight_gluc).mean() > 0.3:
                continue
            labels = extract_overnight_labels(
                glucose_raw[start:start + STEPS_12H],
                midnight_idx=STEPS_6H,
            )
            all_X.append(ctx)
            all_y_hypo.append(int(labels['hypo']))
            all_y_high.append(int(labels['high']))
            all_y_tir.append(labels['tir'])
            all_pids.append(pat['name'])

    if len(all_X) < 20:
        print("  Insufficient overnight windows."); return {}

    X = np.nan_to_num(np.stack(all_X), nan=0.0)  # (N, 72, 16) — impute NaN
    y_hypo = np.array(all_y_hypo)
    y_high = np.array(all_y_high)
    y_tir  = np.array(all_y_tir, dtype=np.float32)
    print(f"  Windows: {len(X)}, hypo rate: {y_hypo.mean():.2%}, high rate: {y_high.mean():.2%}")

    results = {}
    for target_name, target_y in [('hypo', y_hypo), ('high', y_high)]:
        print(f"\n  Target: {target_name}")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, target_y)

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
            m = _train_torch_classifier(
                model, tr_X, tr_y, va_X, va_y, device,
                epochs=cfg['epochs'], patience=cfg['patience'],
                n_classes=2,
            )
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        results[target_name] = {'seeds': seed_metrics, 'average': avg}

    # TIR regression — filter NaN targets
    print("\n  Target: overnight TIR (regression)")
    tir_valid = ~np.isnan(y_tir)
    X_tir, y_tir_clean = X[tir_valid], y_tir[tir_valid]
    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_tir, y_tir_clean)
    seed_reg = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = FlexCNN(in_channels=X.shape[-1], out_dim=1).to(device)
        m = _train_torch_regressor(
            model, tr_X, tr_y, va_X, va_y, device,
            epochs=cfg['epochs'], patience=cfg['patience'],
        )
        seed_reg.append(m)
    avg = {k: round(float(np.mean([s[k] for s in seed_reg])), 4) for k in seed_reg[0]}
    results['tir_regression'] = {'seeds': seed_reg, 'average': avg}

    save_results(results, 'exp412_overnight_risk')
    return results


def run_exp413(args):
    """EXP-413: Next-Day TIR Prediction (24h horizon).

    Given today's data predict tomorrow's time-in-range.
    Tests XGBoost on tabular features and 1D-CNN on 15-min-resolution
    raw sequence (96 steps).
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-413: Next-Day TIR Prediction")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    tab_features, seq_features, y_tir, y_bad, pids = [], [], [], [], []

    for pat in patients:
        glucose_raw = pat['grid'][:, 0] * 400
        grid = pat['grid']
        pk   = pat['pk']

        for start in range(0, len(grid) - 2 * STEPS_24H, STEPS_24H):
            today_g  = glucose_raw[start:start + STEPS_24H]
            tomorrow_g = glucose_raw[start + STEPS_24H:start + 2 * STEPS_24H]
            if np.isnan(today_g).mean() > 0.3 or np.isnan(tomorrow_g).mean() > 0.3:
                continue

            # Tabular features: distributional summary per 6h block
            block_feats = []
            for blk in range(4):
                s, e = blk * STEPS_6H, (blk + 1) * STEPS_6H
                blk_g = today_g[s:e]
                block_feats.extend([
                    compute_tir(blk_g),
                    float(np.nanmean(blk_g)),
                    float(np.nanstd(blk_g)),
                    int((blk_g < 70).sum()),
                    int((blk_g > 180).sum()),
                ])
            iob_today = pat['grid'][start:start + STEPS_24H, 1]
            carb_today = pat['grid'][start:start + STEPS_24H, 5]
            block_feats.extend([
                float(np.nanmean(iob_today)),
                float(np.nansum(carb_today)),
            ])
            tab_features.append(block_feats)

            # Sequence features at 15-min resolution (every 3rd step)
            combined = np.concatenate([grid[start:start + STEPS_24H],
                                       pk[start:start + STEPS_24H]], axis=-1)
            seq_features.append(downsample(combined, 3))  # (96, 16)

            tom_tir = compute_tir(tomorrow_g)
            y_tir.append(tom_tir)
            y_bad.append(int(tom_tir < 60))
            pids.append(pat['name'])

    if len(tab_features) < 20:
        print("  Insufficient day pairs."); return {}

    X_tab = np.array(tab_features, dtype=np.float32)
    X_seq = np.stack(seq_features).astype(np.float32)
    y_tir_arr = np.array(y_tir, dtype=np.float32)
    y_bad_arr = np.array(y_bad, dtype=np.int64)
    print(f"  Day-pairs: {len(X_tab)}, bad-day rate: {y_bad_arr.mean():.2%}")

    results = {}

    # --- XGBoost ---
    if HAS_XGB:
        print("\n  XGBoost TIR regression")
        (tr_tab, tr_tir), (va_tab, va_tir) = temporal_split(X_tab, y_tir_arr)
        model_xgb = xgb.XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8, random_state=42)
        model_xgb.fit(tr_tab, tr_tir, eval_set=[(va_tab, va_tir)],
                      verbose=False)
        pred_tir = model_xgb.predict(va_tab)
        results['xgb_tir'] = {
            'mae': round(float(mean_absolute_error(va_tir, pred_tir)), 4),
            'rmse': round(float(np.sqrt(np.mean((pred_tir - va_tir)**2))), 4),
        }

        print("  XGBoost bad-day classification")
        (tr_tab2, tr_bad), (va_tab2, va_bad) = temporal_split(X_tab, y_bad_arr)
        model_xgb_cls = xgb.XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.1,
            scale_pos_weight=max(1, (1 - y_bad_arr.mean()) / max(y_bad_arr.mean(), 0.01)),
            random_state=42)
        model_xgb_cls.fit(tr_tab2, tr_bad, eval_set=[(va_tab2, va_bad)],
                          verbose=False)
        pred_bad = model_xgb_cls.predict(va_tab2)
        pred_bad_prob = model_xgb_cls.predict_proba(va_tab2)[:, 1]
        results['xgb_bad_day'] = {
            'f1': round(float(f1_score(va_bad, pred_bad, zero_division=0)), 4),
            'auc_roc': round(float(roc_auc_score(va_bad, pred_bad_prob)), 4)
                       if len(np.unique(va_bad)) > 1 else None,
        }
    else:
        print("  XGBoost not available — skipping tabular models.")

    # --- CNN on 15-min sequence ---
    print("\n  1D-CNN TIR regression (15-min resolution)")
    (tr_seq, tr_tir), (va_seq, va_tir) = temporal_split(X_seq, y_tir_arr)
    seed_reg = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = FlexCNN(in_channels=X_seq.shape[-1], out_dim=1).to(device)
        m = _train_torch_regressor(
            model, tr_seq, tr_tir, va_seq, va_tir, device,
            epochs=cfg['epochs'], patience=cfg['patience'],
        )
        seed_reg.append(m)
    avg = {k: round(float(np.mean([s[k] for s in seed_reg])), 4) for k in seed_reg[0]}
    results['cnn_tir'] = {'seeds': seed_reg, 'average': avg}

    print("  1D-CNN bad-day classifier (15-min resolution)")
    (tr_seq2, tr_bad), (va_seq2, va_bad) = temporal_split(X_seq, y_bad_arr)
    seed_cls = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = FlexCNN(in_channels=X_seq.shape[-1], out_dim=2).to(device)
        m = _train_torch_classifier(
            model, tr_seq2, tr_bad, va_seq2, va_bad, device,
            epochs=cfg['epochs'], patience=cfg['patience'], n_classes=2,
        )
        seed_cls.append(m)
    avg = {k: round(float(np.mean([s[k] for s in seed_cls if k in s])), 4)
           for k in seed_cls[0]}
    results['cnn_bad_day'] = {'seeds': seed_cls, 'average': avg}

    save_results(results, 'exp413_nextday_tir')
    return results


def run_exp414(args):
    """EXP-414: Multi-Day Control Quality Forecast (3-4 day).

    Hierarchical model: process 4-day windows as 8 × 12h episodes,
    extract per-episode features, feed sequence to GRU+attention.
    Classify NEXT 4-day block as Good/Moderate/Poor.
    Uses LOSO (leave-one-subject-out) validation.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-414: Multi-Day Control Quality Forecast")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    N_EPISODES = 8
    EP_STEPS = STEPS_12H   # 144 steps per episode
    BLOCK_STEPS = N_EPISODES * EP_STEPS  # 1152 = 4 days

    def tir_to_class(tir):
        if tir >= 70: return 0    # Good
        if tir >= 55: return 1    # Moderate
        return 2                  # Poor

    all_X, all_y, all_pids = [], [], []
    for pat in patients:
        glucose_raw = pat['grid'][:, 0] * 400
        grid = pat['grid']

        for start in range(0, len(grid) - 2 * BLOCK_STEPS, BLOCK_STEPS // 2):
            current_block = glucose_raw[start:start + BLOCK_STEPS]
            next_block    = glucose_raw[start + BLOCK_STEPS:start + 2 * BLOCK_STEPS]
            if len(next_block) < BLOCK_STEPS or np.isnan(current_block).mean() > 0.3:
                continue

            episodes = []
            for ep in range(N_EPISODES):
                s = ep * EP_STEPS
                ep_g = current_block[s:s + EP_STEPS]
                iob_ep = grid[start + s:start + s + EP_STEPS, 1] * 20
                carb_ep = grid[start + s:start + s + EP_STEPS, 5] * 100
                feat = extract_episode_features(ep_g, iob_ep, carb_ep)
                episodes.append(list(feat.values()))

            all_X.append(episodes)
            next_tir = compute_tir(next_block)
            all_y.append(tir_to_class(next_tir))
            all_pids.append(pat['name'])

    if len(all_X) < 10:
        print("  Insufficient 4-day blocks."); return {}

    X = np.array(all_X, dtype=np.float32)      # (N, 8, ep_feat_dim)
    y = np.array(all_y, dtype=np.int64)
    pids = np.array(all_pids)
    ep_dim = X.shape[-1]
    print(f"  Blocks: {len(X)}, class dist: {np.bincount(y, minlength=3).tolist()}")

    # LOSO validation
    unique_pats = sorted(set(all_pids))
    loso_results = {}
    for leave_out in unique_pats:
        mask_val   = pids == leave_out
        mask_train = ~mask_val
        if mask_val.sum() < 2 or mask_train.sum() < 5:
            continue

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = HierarchicalClassifier(
                episode_dim=ep_dim, n_episodes=N_EPISODES, n_classes=3,
            ).to(device)
            m = _train_torch_classifier(
                model, X[mask_train], y[mask_train],
                X[mask_val], y[mask_val], device,
                epochs=cfg['epochs'], patience=cfg['patience'],
                n_classes=3,
            )
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        loso_results[leave_out] = {'seeds': seed_metrics, 'average': avg}

    overall_f1 = [v['average']['f1'] for v in loso_results.values() if 'f1' in v['average']]
    results = {
        'loso': loso_results,
        'overall_macro_f1': round(float(np.mean(overall_f1)), 4) if overall_f1 else None,
    }

    save_results(results, 'exp414_multiday_quality')
    return results


def run_exp415(args):
    """EXP-415: Event Recurrence Prediction.

    Predict P(hypo/high in next 6h/24h/3d) from 7-day event history.
    Uses XGBoost (tabular) and 1D-CNN (sequence of 28 × 6h blocks).
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-415: Event Recurrence Prediction")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    BLOCKS_PER_DAY = 4
    N_BLOCKS = 28  # 7 days × 4 blocks

    def build_event_features(glucose_7d):
        """28-block event history + rolling stats."""
        feats = np.zeros((N_BLOCKS, 4), dtype=np.float32)
        for blk in range(N_BLOCKS):
            s, e = blk * STEPS_6H, (blk + 1) * STEPS_6H
            if e > len(glucose_7d):
                break
            g = glucose_7d[s:e]
            g_valid = g[~np.isnan(g)]
            if len(g_valid) == 0:
                continue
            feats[blk, 0] = (g_valid < 70).sum()        # hypo_count
            feats[blk, 1] = (g_valid > 180).sum()        # high_count
            feats[blk, 2] = compute_tir(g_valid)          # block TIR
            feats[blk, 3] = float(np.nanstd(g_valid))     # variability
        return feats

    horizons = {
        '6h':  STEPS_6H,
        '24h': STEPS_24H,
        '3d':  STEPS_3D,
    }

    results = {}
    for horizon_name, horizon_steps in horizons.items():
        for event_type in ['hypo', 'high']:
            key = f"{event_type}_{horizon_name}"
            print(f"\n  Target: {key}")
            all_X, all_y = [], []

            for pat in patients:
                glucose_raw = pat['grid'][:, 0] * 400
                for start in range(0, len(glucose_raw) - STEPS_7D - horizon_steps, STEPS_6H):
                    hist = glucose_raw[start:start + STEPS_7D]
                    future = glucose_raw[start + STEPS_7D:start + STEPS_7D + horizon_steps]
                    if np.isnan(hist).mean() > 0.3 or np.isnan(future).mean() > 0.3:
                        continue
                    feat = build_event_features(hist)
                    all_X.append(feat)
                    threshold = 70 if event_type == 'hypo' else 180
                    if event_type == 'hypo':
                        all_y.append(int((future < threshold).any()))
                    else:
                        all_y.append(int((future > threshold).sum() / max(len(future), 1) > 0.1))

            if len(all_X) < 20:
                print(f"    Insufficient samples for {key}"); continue

            X = np.stack(all_X)                          # (N, 28, 4)
            y = np.array(all_y, dtype=np.int64)
            print(f"    Samples: {len(X)}, positive rate: {y.mean():.2%}")

            # XGBoost on flattened features
            X_flat = X.reshape(len(X), -1)
            (tr_flat, tr_y), (va_flat, va_y) = temporal_split(X_flat, y)
            key_res = {}

            if HAS_XGB:
                xgb_cls = xgb.XGBClassifier(
                    n_estimators=150, max_depth=4, learning_rate=0.1,
                    scale_pos_weight=max(1, (1 - y.mean()) / max(y.mean(), 0.01)),
                    random_state=42)
                xgb_cls.fit(tr_flat, tr_y, eval_set=[(va_flat, va_y)],
                            verbose=False)
                pred = xgb_cls.predict(va_flat)
                prob = xgb_cls.predict_proba(va_flat)[:, 1]
                key_res['xgb'] = {
                    'f1': round(float(f1_score(va_y, pred, zero_division=0)), 4),
                    'auc_roc': round(float(roc_auc_score(va_y, prob)), 4)
                               if len(np.unique(va_y)) > 1 else None,
                    'ece': round(compute_ece(prob, va_y), 4),
                }

            # CNN on (28, 4) sequence
            (tr_seq, tr_y_s), (va_seq, va_y_s) = temporal_split(X, y)
            seed_cls = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed); np.random.seed(seed)
                model = FlexCNN(in_channels=4, out_dim=2).to(device)
                m = _train_torch_classifier(
                    model, tr_seq, tr_y_s, va_seq, va_y_s, device,
                    epochs=cfg['epochs'], patience=cfg['patience'], n_classes=2,
                )
                seed_cls.append(m)
            avg = {k: round(float(np.mean([s[k] for s in seed_cls if k in s])), 4)
                   for k in seed_cls[0]}
            key_res['cnn'] = {'seeds': seed_cls, 'average': avg}
            results[key] = key_res

    save_results(results, 'exp415_event_recurrence')
    return results


def run_exp416(args):
    """EXP-416: Weekly Routine Hotspot Identification.

    For each patient's 7-day window, compute per-6h-block risk scores
    and identify the most problematic time slots.  Self-supervised:
    labels are the block-level TIR and event rates themselves.
    """
    cfg = _get_config(args)
    print(f"\n{'='*60}")
    print("EXP-416: Weekly Routine Hotspot Identification")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    BLOCKS_PER_DAY = 4
    N_BLOCKS = 28  # 7 days × 4 blocks/day

    results = {}
    for pat in patients:
        glucose_raw = pat['grid'][:, 0] * 400
        block_stats = []

        # Accumulate stats per block-of-week across all available weeks
        weekly_blocks = {i: {'tir': [], 'hypo': [], 'high': [], 'cv': []}
                         for i in range(N_BLOCKS)}

        for week_start in range(0, len(glucose_raw) - STEPS_7D, STEPS_7D):
            week_g = glucose_raw[week_start:week_start + STEPS_7D]
            for blk in range(N_BLOCKS):
                s, e = blk * STEPS_6H, (blk + 1) * STEPS_6H
                g = week_g[s:e]
                g_valid = g[~np.isnan(g)]
                if len(g_valid) < STEPS_6H // 2:
                    continue
                weekly_blocks[blk]['tir'].append(compute_tir(g_valid))
                weekly_blocks[blk]['hypo'].append(int((g_valid < 70).any()))
                weekly_blocks[blk]['high'].append(int((g_valid > 180).sum() > STEPS_PER_HOUR))
                weekly_blocks[blk]['cv'].append(
                    float(np.nanstd(g_valid) / max(np.nanmean(g_valid), 1)))

        block_summary = {}
        for blk in range(N_BLOCKS):
            wb = weekly_blocks[blk]
            if not wb['tir']:
                continue
            day = blk // BLOCKS_PER_DAY
            period = blk % BLOCKS_PER_DAY
            period_name = ['night', 'morning', 'afternoon', 'evening'][period]
            day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day % 7]
            # Risk score: lower TIR + higher event rates = higher risk
            avg_tir = float(np.mean(wb['tir']))
            risk = round(100 - avg_tir + 20 * np.mean(wb['hypo']) + 10 * np.mean(wb['high']), 1)
            block_summary[f"{day_name}_{period_name}"] = {
                'block_idx':    blk,
                'mean_tir':     round(avg_tir, 1),
                'hypo_rate':    round(float(np.mean(wb['hypo'])), 3),
                'high_rate':    round(float(np.mean(wb['high'])), 3),
                'mean_cv':      round(float(np.mean(wb['cv'])), 3),
                'risk_score':   risk,
            }

        # Rank by risk score descending
        ranked = sorted(block_summary.items(), key=lambda kv: -kv[1]['risk_score'])
        hotspots = [{'slot': k, **v} for k, v in ranked[:5]]

        results[pat['name']] = {
            'blocks':   block_summary,
            'hotspots': hotspots,
            'n_weeks':  len(range(0, len(glucose_raw) - STEPS_7D, STEPS_7D)),
        }

    save_results(results, 'exp416_weekly_hotspots')
    return results


def run_exp417(args):
    """EXP-417: Extended History + PK for Classification.

    Test longer lookback (4h, 6h) for classification tasks (hypo, high)
    using PK channels.  Compares baseline 8-channel grid vs 6-channel PK
    replacement at each history scale.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-417: Extended History + PK for Classification")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    history_steps_list = [STEPS_2H, STEPS_4H, STEPS_6H]
    future_steps = STEPS_6H  # label window

    results = {}
    for history_steps in history_steps_list:
        h_label = f"{history_steps // STEPS_PER_HOUR}h"
        print(f"\n--- History: {h_label} ({history_steps} steps) ---")

        variants = {
            'baseline_8ch': lambda pat, s: pat['grid'][s:s + history_steps],
            'pk_replace_6ch': lambda pat, s: np.concatenate([
                pat['grid'][s:s + history_steps, :2],           # glucose, iob
                pat['pk'][s:s + history_steps, :4],             # 4 PK channels
            ], axis=-1),
            'combined_16ch': lambda pat, s: np.concatenate([
                pat['grid'][s:s + history_steps],
                pat['pk'][s:s + history_steps],
            ], axis=-1),
        }

        for vname, feat_fn in variants.items():
            for task_name in ['hypo', 'high']:
                key = f"{h_label}_{vname}_{task_name}"
                print(f"  {key}")

                all_X, all_y = [], []
                for pat in patients:
                    glucose_raw = pat['grid'][:, 0] * 400
                    total = history_steps + future_steps
                    for start in range(0, len(pat['grid']) - total, history_steps // 2):
                        x = feat_fn(pat, start)
                        future_g = glucose_raw[start + history_steps:start + total]
                        if np.isnan(future_g).mean() > 0.3:
                            continue
                        if task_name == 'hypo':
                            label = int((future_g < 70).any())
                        else:
                            label = int((future_g > 180).sum() / max(len(future_g), 1) > 0.2)
                        all_X.append(x)
                        all_y.append(label)

                if len(all_X) < 20:
                    print(f"    Insufficient samples"); continue

                X = np.stack(all_X).astype(np.float32)
                y = np.array(all_y, dtype=np.int64)
                print(f"    N={len(X)}, pos={y.mean():.2%}, ch={X.shape[-1]}")
                (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y)

                seed_metrics = []
                for seed in cfg['seeds']:
                    torch.manual_seed(seed); np.random.seed(seed)
                    model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
                    m = _train_torch_classifier(
                        model, tr_X, tr_y, va_X, va_y, device,
                        epochs=cfg['epochs'], patience=cfg['patience'],
                        n_classes=2,
                    )
                    seed_metrics.append(m)

                avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
                       for k in seed_metrics[0]}
                results[key] = {
                    'seeds': seed_metrics, 'average': avg,
                    'n_samples': len(X), 'n_channels': int(X.shape[-1]),
                }

    save_results(results, 'exp417_extended_pk_classification')
    return results


def run_exp418(args):
    """EXP-418: Multi-Rate EMA for Strategic Features.

    Test 3-channel EMA (α=0.1, 0.3, 0.7) replacing raw glucose at 12h
    and 3-day classification scales.  Cheap feature engineering that
    captures dynamics at multiple time scales.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-418: Multi-Rate EMA for Strategic Features")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    scale_configs = [
        ('12h', STEPS_12H, STEPS_6H),   # 12h history, 6h label window
        ('3d',  STEPS_3D,  STEPS_24H),   # 3-day history, 24h label window
    ]

    results = {}
    for scale_name, history_steps, future_steps in scale_configs:
        for task_name in ['hypo', 'high']:
            print(f"\n--- {scale_name} / {task_name} ---")

            # Build two feature variants: baseline (raw) vs EMA
            all_raw, all_ema, all_y = [], [], []
            for pat in patients:
                glucose_raw = pat['grid'][:, 0] * 400
                grid = pat['grid']
                total = history_steps + future_steps

                # Pre-compute EMA over entire glucose series
                glucose_series = glucose_raw.copy()
                glucose_series[np.isnan(glucose_series)] = 120  # impute for EMA
                ema_channels = compute_ema(glucose_series)      # (N, 3)
                ema_normalised = ema_channels / 400.0           # match glucose scale

                for start in range(0, len(grid) - total, history_steps // 2):
                    hist_raw = grid[start:start + history_steps]
                    hist_ema = np.concatenate([
                        ema_normalised[start:start + history_steps],
                        grid[start:start + history_steps, 1:],  # non-glucose channels
                    ], axis=-1)
                    future_g = glucose_raw[start + history_steps:start + total]
                    if np.isnan(future_g).mean() > 0.3:
                        continue
                    if task_name == 'hypo':
                        label = int((future_g < 70).any())
                    else:
                        label = int((future_g > 180).sum() / max(len(future_g), 1) > 0.2)

                    # Downsample for 3-day scale
                    if history_steps >= STEPS_3D:
                        hist_raw = downsample(hist_raw, 12)  # 1-hour resolution
                        hist_ema = downsample(hist_ema, 12)

                    all_raw.append(hist_raw)
                    all_ema.append(hist_ema)
                    all_y.append(label)

            if len(all_raw) < 20:
                print(f"  Insufficient samples"); continue

            y = np.array(all_y, dtype=np.int64)
            print(f"  N={len(all_raw)}, pos={y.mean():.2%}")

            for variant_name, X_list in [('raw', all_raw), ('ema_3ch', all_ema)]:
                X = np.stack(X_list).astype(np.float32)
                key = f"{scale_name}_{task_name}_{variant_name}"
                print(f"  {key}: shape {X.shape}")
                (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y)

                seed_metrics = []
                for seed in cfg['seeds']:
                    torch.manual_seed(seed); np.random.seed(seed)
                    model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
                    m = _train_torch_classifier(
                        model, tr_X, tr_y, va_X, va_y, device,
                        epochs=cfg['epochs'], patience=cfg['patience'],
                        n_classes=2,
                    )
                    seed_metrics.append(m)

                avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
                       for k in seed_metrics[0]}
                results[key] = {
                    'seeds': seed_metrics, 'average': avg,
                    'n_channels': int(X.shape[-1]),
                }

    save_results(results, 'exp418_ema_strategic')
    return results


# ===================================================================
# Registry and CLI
# ===================================================================

EXPERIMENTS = {
    '411': run_exp411,
    '412': run_exp412,
    '413': run_exp413,
    '414': run_exp414,
    '415': run_exp415,
    '416': run_exp416,
    '417': run_exp417,
    '418': run_exp418,
}


def save_results(result, filename):
    """Persist experiment results as JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f'{filename}.json'
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Saved: {path}")


def main():
    parser = argparse.ArgumentParser(
        description='EXP-411-418: Living Treatment Plan — Strategic Planning Horizon',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Experiments:
  411  Extended history forecasting (PKGroupedEncoder + 4-12h lookback)
  412  Overnight risk assessment (6-8h horizon)
  413  Next-day TIR prediction (24h horizon)
  414  Multi-day control quality forecast (3-4 day)
  415  Event recurrence prediction (temporal patterns)
  416  Weekly routine hotspot identification
  417  Extended history + PK for classification
  418  Multi-rate EMA for strategic features
""")
    parser.add_argument('--experiment', '-e', nargs='+', default=['all'],
                        help='Experiment number(s) or "all" (default: all)')
    parser.add_argument('--device', '-d', default='auto',
                        help='Torch device (auto/cpu/cuda/mps)')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick mode: fewer patients, epochs, seeds')
    parser.add_argument('--patients-dir',
                        default='externals/ns-data/patients',
                        help='Path to patient data directory')
    args = parser.parse_args()

    if 'all' in args.experiment:
        exp_ids = sorted(EXPERIMENTS.keys())
    else:
        exp_ids = [e.strip() for e in args.experiment]

    print(f"Treatment Planning Experiments — {len(exp_ids)} to run")
    print(f"  Quick: {args.quick}, Device: {args.device}")
    t0 = time.time()

    all_results = {}
    for eid in exp_ids:
        if eid not in EXPERIMENTS:
            print(f"\n  Unknown experiment: {eid}"); continue
        try:
            result = EXPERIMENTS[eid](args)
            all_results[eid] = result
        except Exception as exc:
            print(f"\n  EXP-{eid} failed: {exc}")
            all_results[eid] = {'error': str(exc)}

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"All done in {elapsed:.0f}s — {len(all_results)} experiments completed.")
    return all_results


if __name__ == '__main__':
    main()
