#!/usr/bin/env python3
"""
EXP-411 through EXP-420: Living Treatment Plan — Strategic Planning Horizon Experiments

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
  EXP-420: Hypo breakthrough — systematic ablation + feature engineering
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


def temporal_split(X, *extras, val_frac=0.2, pids=None):
    """Chronological train/val split.  Returns (train_parts, val_parts).

    When *pids* is provided, split is done per-patient to avoid the
    pathological case where pooled multi-patient data causes the
    validation set to contain only the last patient(s).
    """
    if pids is not None:
        pids = np.asarray(pids)
        train_mask = np.zeros(len(X), dtype=bool)
        for pid in np.unique(pids):
            idxs = np.where(pids == pid)[0]
            split = int(len(idxs) * (1 - val_frac))
            train_mask[idxs[:split]] = True
        val_mask = ~train_mask
        train = [X[train_mask]] + [e[train_mask] for e in extras]
        val   = [X[val_mask]]   + [e[val_mask]   for e in extras]
        return train, val

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
    pids   = np.array(all_pids)
    print(f"  Windows: {len(X)}, hypo rate: {y_hypo.mean():.2%}, high rate: {y_high.mean():.2%}")

    results = {}
    for target_name, target_y in [('hypo', y_hypo), ('high', y_high)]:
        print(f"\n  Target: {target_name}")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, target_y, pids=pids)

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
    X_tir, y_tir_clean, pids_tir = X[tir_valid], y_tir[tir_valid], pids[tir_valid]
    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_tir, y_tir_clean, pids=pids_tir)
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

    X_tab = np.nan_to_num(np.array(tab_features, dtype=np.float32), nan=0.0)
    X_seq = np.nan_to_num(np.stack(seq_features).astype(np.float32), nan=0.0)
    y_tir_arr = np.array(y_tir, dtype=np.float32)
    y_bad_arr = np.array(y_bad, dtype=np.int64)
    pids_arr  = np.array(pids)
    print(f"  Day-pairs: {len(X_tab)}, bad-day rate: {y_bad_arr.mean():.2%}")

    results = {}

    # --- XGBoost ---
    if HAS_XGB:
        print("\n  XGBoost TIR regression")
        (tr_tab, tr_tir), (va_tab, va_tir) = temporal_split(X_tab, y_tir_arr, pids=pids_arr)
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
        (tr_tab2, tr_bad), (va_tab2, va_bad) = temporal_split(X_tab, y_bad_arr, pids=pids_arr)
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
    (tr_seq, tr_tir), (va_seq, va_tir) = temporal_split(X_seq, y_tir_arr, pids=pids_arr)
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
    (tr_seq2, tr_bad), (va_seq2, va_bad) = temporal_split(X_seq, y_bad_arr, pids=pids_arr)
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
            all_X, all_y, all_pids = [], [], []

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
                    all_pids.append(pat['name'])

            if len(all_X) < 20:
                print(f"    Insufficient samples for {key}"); continue

            X = np.stack(all_X)                          # (N, 28, 4)
            y = np.array(all_y, dtype=np.int64)
            pids = np.array(all_pids)
            print(f"    Samples: {len(X)}, positive rate: {y.mean():.2%}")

            # XGBoost on flattened features
            X_flat = X.reshape(len(X), -1)
            (tr_flat, tr_y), (va_flat, va_y) = temporal_split(X_flat, y, pids=pids)
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
            (tr_seq, tr_y_s), (va_seq, va_y_s) = temporal_split(X, y, pids=pids)
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

                all_X, all_y, all_pids = [], [], []
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
                        all_pids.append(pat['name'])

                if len(all_X) < 20:
                    print(f"    Insufficient samples"); continue

                X = np.nan_to_num(np.stack(all_X).astype(np.float32), nan=0.0)
                y = np.array(all_y, dtype=np.int64)
                pids = np.array(all_pids)
                print(f"    N={len(X)}, pos={y.mean():.2%}, ch={X.shape[-1]}")
                (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y, pids=pids)

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
            all_raw, all_ema, all_y, all_pids = [], [], [], []
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
                    all_pids.append(pat['name'])

            if len(all_raw) < 20:
                print(f"  Insufficient samples"); continue

            y = np.array(all_y, dtype=np.int64)
            pids = np.array(all_pids)
            print(f"  N={len(all_raw)}, pos={y.mean():.2%}")

            for variant_name, X_list in [('raw', all_raw), ('ema_3ch', all_ema)]:
                X = np.nan_to_num(np.stack(X_list).astype(np.float32), nan=0.0)
                key = f"{scale_name}_{task_name}_{variant_name}"
                print(f"  {key}: shape {X.shape}")
                (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y, pids=pids)

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


def run_exp420(args):
    """EXP-420: Hypo Breakthrough — Systematic Feature + Loss Engineering.

    Hypo classification is stuck at AUC 0.67-0.73 across all tasks/horizons.
    HIGH prediction already hits 0.80+.  This experiment systematically tests
    approaches to close the gap:

    1. **Channel ablation**: 8ch (no PK) vs 16ch (with PK) to quantify PK benefit
    2. **Glucose rate features**: dBG/dt and d²BG/dt² as explicit channels —
       hypo = fast rate of descent, derivatives capture this directly
    3. **Focal loss**: Down-weight easy negatives, focus on hard-to-classify
       near-hypo examples (γ=2)
    4. **Asymmetric threshold**: Lower clinical threshold (75 mg/dL vs 70)
       to catch "near-hypo" events earlier
    5. **Combined best**: Stack winning features + loss

    All variants use the overnight risk framework (EXP-412) as baseline.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-420: Hypo Breakthrough — Systematic Feature + Loss")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    # ── Build windows with multiple feature sets ────────────────────
    windows = {'8ch': [], '16ch': [], '8ch_deriv': [], '16ch_deriv': [],
               '8ch_deriv_ema': []}
    all_y70, all_y75, all_pids = [], [], []

    for pat in patients:
        grid = pat['grid']          # (N, 8)
        pk   = pat['pk']            # (N, 8)
        glucose_raw = grid[:, 0] * 400  # de-normalise

        # Compute glucose derivatives (rate of change, acceleration)
        dbg = np.zeros_like(glucose_raw)
        dbg[1:] = glucose_raw[1:] - glucose_raw[:-1]
        d2bg = np.zeros_like(glucose_raw)
        d2bg[1:] = dbg[1:] - dbg[:-1]
        dbg_norm  = dbg / 40.0    # typical range ±20 mg/dL per 5min
        d2bg_norm = d2bg / 20.0

        # EMA spread (fast - slow divergence)
        ema_slow = np.zeros_like(glucose_raw)
        ema_fast = np.zeros_like(glucose_raw)
        ema_slow[0] = glucose_raw[0] if not np.isnan(glucose_raw[0]) else 0
        ema_fast[0] = glucose_raw[0] if not np.isnan(glucose_raw[0]) else 0
        for t in range(1, len(glucose_raw)):
            v = glucose_raw[t] if not np.isnan(glucose_raw[t]) else ema_slow[t-1]
            ema_slow[t] = 0.05 * v + 0.95 * ema_slow[t-1]
            ema_fast[t] = 0.3 * v + 0.7 * ema_fast[t-1]
        ema_spread = (ema_fast - ema_slow) / 400.0

        deriv_cols = np.column_stack([dbg_norm, d2bg_norm])       # (N, 2)
        ema_col    = ema_spread[:, None]                          # (N, 1)

        for start in range(0, len(grid) - STEPS_12H, STEPS_6H):
            s, e = start, start + STEPS_6H
            overnight_gluc = glucose_raw[e:start + STEPS_12H]
            if len(overnight_gluc) < STEPS_6H or np.isnan(overnight_gluc).mean() > 0.3:
                continue

            labels = extract_overnight_labels(
                glucose_raw[start:start + STEPS_12H],
                midnight_idx=STEPS_6H,
            )

            ctx_8ch     = grid[s:e]
            ctx_16ch    = np.concatenate([grid[s:e], pk[s:e]], axis=-1)
            ctx_8deriv  = np.concatenate([grid[s:e], deriv_cols[s:e]], axis=-1)
            ctx_16deriv = np.concatenate([grid[s:e], pk[s:e],
                                          deriv_cols[s:e]], axis=-1)
            ctx_8de     = np.concatenate([grid[s:e], deriv_cols[s:e],
                                          ema_col[s:e]], axis=-1)

            windows['8ch'].append(ctx_8ch)
            windows['16ch'].append(ctx_16ch)
            windows['8ch_deriv'].append(ctx_8deriv)
            windows['16ch_deriv'].append(ctx_16deriv)
            windows['8ch_deriv_ema'].append(ctx_8de)

            all_y70.append(int(labels['hypo']))
            overnight_g = overnight_gluc[~np.isnan(overnight_gluc)]
            all_y75.append(int(np.any(overnight_g < 75)) if len(overnight_g) > 0 else 0)
            all_pids.append(pat['name'])

    if len(all_y70) < 20:
        print("  Insufficient windows."); return {}

    y70  = np.array(all_y70)
    y75  = np.array(all_y75)
    pids = np.array(all_pids)
    print(f"  Windows: {len(y70)}, hypo70 rate: {y70.mean():.2%}, hypo75 rate: {y75.mean():.2%}")

    results = {}

    # ── Variant 1: Channel ablation (standard CE loss) ───────────────
    for feat_name in ['8ch', '16ch', '8ch_deriv', '16ch_deriv', '8ch_deriv_ema']:
        X = np.nan_to_num(np.stack(windows[feat_name]), nan=0.0)
        key = f'{feat_name}_hypo70_ce'
        print(f"\n  Config: {key} (ch={X.shape[-1]})")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y70, pids=pids)

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
        results[key] = {'seeds': seed_metrics, 'average': avg,
                        'n_channels': int(X.shape[-1])}

    # ── Variant 2: Focal loss on promising feature sets ──────────────
    for feat_name in ['16ch', '8ch_deriv', '16ch_deriv']:
        X = np.nan_to_num(np.stack(windows[feat_name]), nan=0.0)
        key = f'{feat_name}_hypo70_focal'
        print(f"\n  Config: {key} (focal γ=2)")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y70, pids=pids)

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
            m = _train_focal_classifier(
                model, tr_X, tr_y, va_X, va_y, device,
                epochs=cfg['epochs'], patience=cfg['patience'],
                gamma=2.0,
            )
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        results[key] = {'seeds': seed_metrics, 'average': avg,
                        'n_channels': int(X.shape[-1])}

    # ── Variant 3: Near-hypo threshold (75 mg/dL) ───────────────────
    for feat_name in ['16ch_deriv']:
        X = np.nan_to_num(np.stack(windows[feat_name]), nan=0.0)
        key = f'{feat_name}_hypo75_ce'
        print(f"\n  Config: {key} (threshold=75)")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y75, pids=pids)

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
        results[key] = {'seeds': seed_metrics, 'average': avg,
                        'n_channels': int(X.shape[-1]),
                        'threshold': 75}

    # ── Variant 4: Focal + near-hypo combined ────────────────────────
    for feat_name in ['16ch_deriv']:
        X = np.nan_to_num(np.stack(windows[feat_name]), nan=0.0)
        key = f'{feat_name}_hypo75_focal'
        print(f"\n  Config: {key} (threshold=75, focal γ=2)")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y75, pids=pids)

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
            m = _train_focal_classifier(
                model, tr_X, tr_y, va_X, va_y, device,
                epochs=cfg['epochs'], patience=cfg['patience'],
                gamma=2.0,
            )
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        results[key] = {'seeds': seed_metrics, 'average': avg,
                        'n_channels': int(X.shape[-1]),
                        'threshold': 75}

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n  {'Config':40s} {'AUC':>7s} {'F1':>7s}")
    print("  " + "-" * 58)
    for k, v in sorted(results.items(), key=lambda x: -x[1]['average'].get('auc_roc', 0)):
        a = v['average']
        print(f"  {k:40s} {a.get('auc_roc', 0):7.4f} {a.get('f1', 0):7.4f}")

    save_results(results, 'exp420_hypo_breakthrough')
    return results


def _focal_loss(logits, targets, gamma=2.0, pos_weight=None):
    """Focal loss for binary classification — focuses on hard examples."""
    ce = F.cross_entropy(logits, targets, weight=pos_weight, reduction='none')
    probs = torch.softmax(logits, dim=-1)
    pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)
    return ((1 - pt) ** gamma * ce).mean()


def _train_focal_classifier(model, train_X, train_y, val_X, val_y, device,
                             epochs=60, patience=12, batch_size=64, lr=1e-3,
                             gamma=2.0):
    """Train with focal loss — identical to _train_torch_classifier except loss."""
    pos_weight = len(train_y) / max(train_y.sum(), 1)
    weights = torch.tensor([1.0, float(pos_weight)], dtype=torch.float32).to(device)

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
            loss = _focal_loss(logits, t_y[idx], gamma=gamma, pos_weight=weights)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            v_logits = model(v_X)
            v_pred = v_logits.argmax(dim=-1).cpu().numpy()
            v_loss = F.cross_entropy(
                v_logits, torch.tensor(val_y, dtype=torch.long).to(device)
            ).item()
        scheduler.step(v_loss)

        metric = f1_score(val_y, v_pred, average='binary', zero_division=0)
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
        'f1': round(float(f1_score(val_y, v_pred, average='binary', zero_division=0)), 4),
        'accuracy': round(float(accuracy_score(val_y, v_pred)), 4),
    }
    try:
        results['auc_roc'] = round(float(roc_auc_score(val_y, v_probs[:, 1])), 4)
        results['ece'] = round(compute_ece(v_probs[:, 1], val_y), 4)
    except ValueError:
        pass

    return results


def run_exp421(args):
    """EXP-421: Hypo Architecture + Context Sweep.

    EXP-420 showed feature/loss engineering can't break 0.69 AUC for hypo.
    This experiment tests whether the bottleneck is:
      (a) Model architecture (CNN vs XGBoost vs Transformer)
      (b) Context length (6h vs 12h vs 24h evening window)
      (c) Problem framing (binary vs regression → min glucose)

    Hypotheses:
      H1: XGBoost on tabular features may find patterns CNN misses
      H2: Longer context captures more insulin history (DIA Valley)
      H3: Predicting min glucose (regression) then thresholding may beat
          direct classification (richer gradient signal)
      H4: Transformer attention may focus on critical time segments

    Uses 8ch (no PK — EXP-420 showed PK hurts hypo).
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-421: Hypo Architecture + Context Sweep")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    results = {}

    # ── Build windows at multiple context lengths ────────────────────
    for ctx_hours, ctx_steps in [(6, STEPS_6H), (12, STEPS_12H), (24, STEPS_24H)]:
        label_steps = STEPS_6H  # always predict next 6h
        total_steps = ctx_steps + label_steps

        all_X, all_y_binary, all_y_mingluc, all_pids = [], [], [], []
        all_tabular = []

        for pat in patients:
            grid = pat['grid']  # (N, 8)
            glucose_raw = grid[:, 0] * 400

            for start in range(0, len(grid) - total_steps, STEPS_6H):
                ctx_end = start + ctx_steps
                label_end = ctx_end + label_steps

                ctx = grid[start:ctx_end]                    # (ctx_steps, 8)
                future_gluc = glucose_raw[ctx_end:label_end]

                if len(future_gluc) < label_steps or np.isnan(future_gluc).mean() > 0.3:
                    continue

                future_valid = future_gluc[~np.isnan(future_gluc)]
                if len(future_valid) == 0:
                    continue

                min_gluc = float(np.min(future_valid))
                is_hypo = int(min_gluc < 70)

                all_X.append(ctx)
                all_y_binary.append(is_hypo)
                all_y_mingluc.append(min_gluc)
                all_pids.append(pat['name'])

                # Tabular features for XGBoost
                ctx_gluc = glucose_raw[start:ctx_end]
                valid_gluc = ctx_gluc[~np.isnan(ctx_gluc)]
                if len(valid_gluc) < 5:
                    valid_gluc = np.array([120.0] * 5)
                feats = [
                    float(np.mean(valid_gluc)),                  # mean glucose
                    float(np.std(valid_gluc)),                   # glucose variability
                    float(np.min(valid_gluc)),                   # min in context
                    float(np.max(valid_gluc)),                   # max in context
                    float(valid_gluc[-1]),                       # last glucose
                    float(valid_gluc[-1] - valid_gluc[-min(6,len(valid_gluc))]),  # 30min trend
                    float(np.mean(valid_gluc < 80)),             # time near-hypo
                    float(np.mean(valid_gluc < 70)),             # time in hypo
                    float(np.mean(valid_gluc > 180)),            # time high
                    float(np.sum(np.abs(np.diff(valid_gluc)))),  # glucose excursion
                ]
                # Add insulin/carb features from grid channels
                for ch_idx in [1, 2, 3, 4]:  # IOB, COB, net_basal, bolus
                    ch_data = grid[start:ctx_end, ch_idx]
                    ch_valid = ch_data[~np.isnan(ch_data)]
                    if len(ch_valid) == 0:
                        ch_valid = np.array([0.0])
                    feats.extend([float(np.mean(ch_valid)), float(np.sum(ch_valid)),
                                  float(ch_valid[-1])])
                all_tabular.append(feats)

        if len(all_X) < 20:
            print(f"  {ctx_hours}h context: insufficient windows"); continue

        X_seq = np.nan_to_num(np.stack(all_X), nan=0.0)
        X_tab = np.nan_to_num(np.array(all_tabular), nan=0.0)
        y_bin = np.array(all_y_binary)
        y_min = np.array(all_y_mingluc, dtype=np.float32)
        pids  = np.array(all_pids)

        hypo_rate = y_bin.mean()
        print(f"\n  Context: {ctx_hours}h — {len(y_bin)} windows, "
              f"hypo rate: {hypo_rate:.2%}, mean min glucose: {y_min.mean():.0f}")

        # ── XGBoost on tabular features ────────────────────────────
        if HAS_XGB:
            key = f'{ctx_hours}h_xgb_binary'
            print(f"  Config: {key}")
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X_tab, y_bin, pids=pids)

            scale = max(tr_y.sum(), 1) / max(len(tr_y) - tr_y.sum(), 1)
            clf = xgb.XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                scale_pos_weight=float(1.0 / scale),
                eval_metric='logloss', verbosity=0,
                tree_method='hist', device='cuda' if device.type == 'cuda' else 'cpu',
            )
            clf.fit(tr_X, tr_y, eval_set=[(va_X, va_y)],
                    verbose=False)
            va_probs = clf.predict_proba(va_X)[:, 1]
            va_pred = (va_probs > 0.5).astype(int)
            m = {
                'f1': round(float(f1_score(va_y, va_pred, average='binary', zero_division=0)), 4),
                'accuracy': round(float(accuracy_score(va_y, va_pred)), 4),
            }
            try:
                m['auc_roc'] = round(float(roc_auc_score(va_y, va_probs)), 4)
                m['ece'] = round(compute_ece(va_probs, va_y), 4)
            except ValueError:
                pass
            results[key] = {'average': m, 'n_features': X_tab.shape[1]}

        # ── XGBoost regression on min glucose ──────────────────────
        if HAS_XGB:
            key = f'{ctx_hours}h_xgb_mingluc'
            print(f"  Config: {key}")
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X_tab, y_min, pids=pids)
            (_, tr_yb), (_, va_yb) = temporal_split(X_tab, y_bin, pids=pids)

            reg = xgb.XGBRegressor(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                eval_metric='mae', verbosity=0,
                tree_method='hist', device='cuda' if device.type == 'cuda' else 'cpu',
            )
            reg.fit(tr_X, tr_y, eval_set=[(va_X, va_y)], verbose=False)
            va_pred_mg = reg.predict(va_X)
            va_pred_bin = (va_pred_mg < 70).astype(int)
            m = {
                'mae_mg': round(float(np.mean(np.abs(va_pred_mg - va_y))), 2),
                'f1': round(float(f1_score(va_yb, va_pred_bin, average='binary', zero_division=0)), 4),
                'accuracy': round(float(accuracy_score(va_yb, va_pred_bin)), 4),
            }
            try:
                m['auc_roc'] = round(float(roc_auc_score(va_yb, -va_pred_mg)), 4)
            except ValueError:
                pass
            results[key] = {'average': m, 'n_features': X_tab.shape[1]}

        # ── CNN baseline (8ch, same as EXP-420 winner) ─────────────
        key = f'{ctx_hours}h_cnn_binary'
        print(f"  Config: {key}")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X_seq, y_bin, pids=pids)

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=8, out_dim=2).to(device)
            m = _train_torch_classifier(
                model, tr_X, tr_y, va_X, va_y, device,
                epochs=cfg['epochs'], patience=cfg['patience'],
                n_classes=2,
            )
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        results[key] = {'seeds': seed_metrics, 'average': avg}

        # ── CNN regression on min glucose ──────────────────────────
        key = f'{ctx_hours}h_cnn_mingluc'
        print(f"  Config: {key}")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X_seq, y_min, pids=pids)
        (_, tr_yb), (_, va_yb) = temporal_split(X_seq, y_bin, pids=pids)

        seed_metrics = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=8, out_dim=1).to(device)
            m = _train_torch_regressor(
                model, tr_X, tr_y, va_X, va_y, device,
                epochs=cfg['epochs'], patience=cfg['patience'],
            )
            # Also compute classification metrics from thresholded regression
            model.eval()
            with torch.no_grad():
                vX = torch.tensor(va_X, dtype=torch.float32).to(device)
                pred_mg = model(vX).cpu().numpy().squeeze()
            pred_bin = (pred_mg < 70).astype(int)
            m['f1_thresh'] = round(float(f1_score(va_yb, pred_bin, average='binary', zero_division=0)), 4)
            try:
                m['auc_roc_thresh'] = round(float(roc_auc_score(va_yb, -pred_mg)), 4)
            except ValueError:
                pass
            seed_metrics.append(m)

        avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
               for k in seed_metrics[0]}
        results[key] = {'seeds': seed_metrics, 'average': avg}

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n  {'Config':35s} {'AUC':>7s} {'F1':>7s} {'Notes':>15s}")
    print("  " + "-" * 65)
    for k, v in sorted(results.items(), key=lambda x: -x[1]['average'].get('auc_roc', 0)):
        a = v['average']
        notes = ''
        if 'mae_mg' in a:
            notes = f"MAE={a['mae_mg']}mg"
        if 'auc_roc_thresh' in a:
            notes = f"regAUC={a['auc_roc_thresh']}"
        print(f"  {k:35s} {a.get('auc_roc', 0):7.4f} {a.get('f1', 0):7.4f} {notes:>15s}")

    save_results(results, 'exp421_hypo_architecture_context')
    return results


def run_exp422(args):
    """EXP-422: Metabolic Phase Signal for Hypo Prediction.

    Core hypothesis: The phase mismatch between carb absorption (peaks ~15-30 min)
    and insulin absorption (peaks ~55 min) creates a detectable metabolic activity
    signature. Even when absolute glucose doesn't change (AID compensates), the
    INTERACTION of carb and insulin dynamics reveals meal events and predicts
    whether insulin will overshoot carbs → hypo.

    Current PK channels track announced events only. The metabolic flux approach
    inverts the model: use OBSERVED GLUCOSE to infer the true metabolic state,
    capturing unannounced meals, exercise, and stress.

    Novel channels:
      1. metabolic_flux: dBG/dt + insulin_effect - hepatic (= residual carb absorption)
      2. phase_balance: carb_rate - insulin_net (instantaneous phase mismatch)
      3. flux_integral: cumulative unresolved energy over rolling window
      4. overshoot_risk: insulin_net / max(carb_rate, ε) — ratio >1 = hypo risk

    Conservation insight: ∫(BG - baseline)dt ≈ carbs×factor - insulin×ISF.
    Over full absorption these cancel. At short timescales, phase mismatch
    creates detectable "metabolic current" even when glucose "voltage" is stable.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-422: Metabolic Phase Signal for Hypo Prediction")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    # ── Feature sets ────────────────────────────────────────────────
    windows = {
        'baseline_8ch': [],        # grid only (EXP-421 best = 0.696)
        'pk_16ch': [],             # grid + PK (EXP-420 showed hurts)
        'flux_12ch': [],           # grid + 4 novel metabolic channels
        'flux_pk_20ch': [],        # grid + PK + 4 novel channels
        'flux_only_4ch': [],       # JUST the 4 novel channels (ablation)
        'glucose_flux_5ch': [],    # glucose + 4 novel (minimal but physics-rich)
    }
    all_y_hypo, all_y_high, all_pids = [], [], []

    for pat in patients:
        grid = pat['grid']          # (N, 8)
        pk   = pat['pk']            # (N, 8)
        glucose_raw = grid[:, 0] * 400  # de-normalise to mg/dL

        # ── Compute observed metabolic flux channels ────────────────
        # Channel 1: dBG/dt (observed glucose rate of change, mg/dL per 5min)
        dbg_dt = np.zeros_like(glucose_raw)
        dbg_dt[1:] = glucose_raw[1:] - glucose_raw[:-1]

        # Channel 2: insulin_net activity (from PK, U/min denormalised)
        # PK channel 1 = insulin_net, normalised by 0.05
        insulin_net = pk[:, 1] * 0.05  # U/min

        # Channel 3: carb_rate (from PK, g/min denormalised)
        # PK channel 3 = carb_rate, normalised by 0.5
        carb_rate = pk[:, 3] * 0.5  # g/min

        # Channel 4: hepatic_production (from PK, mg/dL per 5min denormalised)
        # PK channel 5 = hepatic_production, normalised by 3.0
        hepatic = pk[:, 5] * 3.0  # mg/dL per 5min

        # Channel 5: ISF (from PK, mg/dL per U denormalised)
        # PK channel 7 = isf_curve, normalised by 200.0
        isf = pk[:, 7] * 200.0  # mg/dL per U

        # ── Novel metabolic phase channels ──────────────────────────

        # 1. Metabolic flux: what the glucose SHOULD be doing based on
        #    known insulin + hepatic, minus what it IS doing.
        #    Residual = actual dBG/dt - expected_from_insulin_and_liver
        #    = unaccounted carb absorption + exercise + stress + noise
        #    Positive = unannounced carbs being absorbed
        #    Negative = unexplained glucose drop (exercise, stress)
        insulin_effect = insulin_net * 5.0 * np.where(isf > 0, isf, 50.0)  # mg/dL per 5min
        expected_change = hepatic - insulin_effect  # expected dBG/dt from known sources
        metabolic_flux = dbg_dt - expected_change   # residual = unknown sources
        # Normalise: typical range ±30 mg/dL per 5min
        metabolic_flux_norm = metabolic_flux / 30.0

        # 2. Phase balance: carb_rate vs insulin_net activity
        #    Positive = carbs dominating (early meal phase)
        #    Negative = insulin dominating (late phase, hypo risk)
        #    This captures the INTERACTION, not just individual rates.
        #    Normalise carb_rate to same units as insulin for comparison:
        safe_cr = 10.0  # approximate carb ratio (g per U)
        carb_as_insulin_equiv = carb_rate / safe_cr  # U/min equivalent
        phase_balance = carb_as_insulin_equiv - insulin_net
        phase_balance_norm = phase_balance / 0.05

        # 3. Flux integral: cumulative unresolved energy over 1h rolling window
        #    Tracks whether metabolic flux has been persistently positive or
        #    negative — sustained positive = ongoing meal, sustained negative
        #    = ongoing insulin dominance (hypo building)
        window_steps = STEPS_PER_HOUR  # 12 steps = 1 hour
        flux_integral = np.zeros_like(metabolic_flux)
        for t in range(window_steps, len(metabolic_flux)):
            flux_integral[t] = np.nansum(metabolic_flux[t - window_steps:t])
        flux_integral_norm = flux_integral / 200.0  # typical range ±100

        # 4. Overshoot risk: ratio of insulin activity to carb activity
        #    >1 means insulin is winning → glucose will fall → hypo risk
        #    <1 means carbs are winning → glucose will rise
        #    Uses smoothed (30min EMA) to avoid divide-by-zero noise
        alpha = 0.3  # 30min EMA on 5min data ≈ 6 steps
        smooth_ins = np.zeros_like(insulin_net)
        smooth_carb = np.zeros_like(carb_as_insulin_equiv)
        smooth_ins[0] = insulin_net[0]
        smooth_carb[0] = carb_as_insulin_equiv[0]
        for t in range(1, len(insulin_net)):
            smooth_ins[t] = alpha * insulin_net[t] + (1 - alpha) * smooth_ins[t - 1]
            smooth_carb[t] = alpha * carb_as_insulin_equiv[t] + (1 - alpha) * smooth_carb[t - 1]
        epsilon = 1e-6
        overshoot_risk = smooth_ins / (smooth_carb + epsilon)
        # Clip and normalise: range [0, 10], centred at 1
        overshoot_risk = np.clip(overshoot_risk, 0, 10) / 5.0

        # Stack the 4 novel channels
        novel_4ch = np.column_stack([
            metabolic_flux_norm,
            phase_balance_norm,
            flux_integral_norm,
            overshoot_risk,
        ])  # (N, 4)

        # ── Build overnight windows ────────────────────────────────
        for start in range(0, len(grid) - STEPS_12H, STEPS_6H):
            s, e = start, start + STEPS_6H
            overnight_gluc = glucose_raw[e:start + STEPS_12H]
            if len(overnight_gluc) < STEPS_6H or np.isnan(overnight_gluc).mean() > 0.3:
                continue

            labels = extract_overnight_labels(
                glucose_raw[start:start + STEPS_12H],
                midnight_idx=STEPS_6H,
            )

            windows['baseline_8ch'].append(grid[s:e])
            windows['pk_16ch'].append(np.concatenate([grid[s:e], pk[s:e]], axis=-1))
            windows['flux_12ch'].append(np.concatenate([grid[s:e], novel_4ch[s:e]], axis=-1))
            windows['flux_pk_20ch'].append(np.concatenate([grid[s:e], pk[s:e], novel_4ch[s:e]], axis=-1))
            windows['flux_only_4ch'].append(novel_4ch[s:e])
            windows['glucose_flux_5ch'].append(
                np.concatenate([grid[s:e, :1], novel_4ch[s:e]], axis=-1))

            all_y_hypo.append(int(labels['hypo']))
            all_y_high.append(int(labels['high']))
            all_pids.append(pat['name'])

    if len(all_y_hypo) < 20:
        print("  Insufficient windows."); return {}

    y_hypo = np.array(all_y_hypo)
    y_high = np.array(all_y_high)
    pids = np.array(all_pids)
    print(f"  Windows: {len(y_hypo)}, hypo rate: {y_hypo.mean():.2%}, high rate: {y_high.mean():.2%}")

    results = {}

    # ── Test each feature set for both hypo and high ─────────────────
    for target_name, target_y in [('hypo', y_hypo), ('high', y_high)]:
        for feat_name, feat_windows in windows.items():
            X = np.nan_to_num(np.stack(feat_windows), nan=0.0)
            key = f'{feat_name}_{target_name}'
            print(f"\n  Config: {key} (ch={X.shape[-1]})")
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X, target_y, pids=pids)

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
            results[key] = {'seeds': seed_metrics, 'average': avg,
                            'n_channels': int(X.shape[-1])}

    # ── XGBoost on flux features (tabular) ───────────────────────────
    if HAS_XGB:
        for target_name, target_y in [('hypo', y_hypo)]:
            X_flux = np.nan_to_num(np.stack(windows['flux_12ch']), nan=0.0)
            # Extract tabular stats from flux channels
            all_tab = []
            for i in range(len(X_flux)):
                feats = []
                for ch in range(X_flux.shape[-1]):
                    ch_data = X_flux[i, :, ch]
                    feats.extend([
                        float(np.mean(ch_data)),
                        float(np.std(ch_data)),
                        float(ch_data[-1]),  # last value
                        float(np.min(ch_data)),
                        float(np.max(ch_data)),
                    ])
                all_tab.append(feats)
            X_tab = np.array(all_tab)

            key = f'xgb_flux_tabular_{target_name}'
            print(f"\n  Config: {key} (features={X_tab.shape[1]})")
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X_tab, target_y, pids=pids)

            scale = max(tr_y.sum(), 1) / max(len(tr_y) - tr_y.sum(), 1)
            clf = xgb.XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                scale_pos_weight=float(1.0 / scale),
                eval_metric='logloss', verbosity=0,
                tree_method='hist', device='cuda' if device.type == 'cuda' else 'cpu',
            )
            clf.fit(tr_X, tr_y, eval_set=[(va_X, va_y)], verbose=False)
            va_probs = clf.predict_proba(va_X)[:, 1]
            va_pred = (va_probs > 0.5).astype(int)
            m = {
                'f1': round(float(f1_score(va_y, va_pred, average='binary', zero_division=0)), 4),
                'accuracy': round(float(accuracy_score(va_y, va_pred)), 4),
            }
            try:
                m['auc_roc'] = round(float(roc_auc_score(va_y, va_probs)), 4)
                m['ece'] = round(compute_ece(va_probs, va_y), 4)
            except ValueError:
                pass
            results[key] = {'average': m, 'n_features': X_tab.shape[1]}

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n  {'Config':40s} {'AUC':>7s} {'F1':>7s} {'ch':>4s}")
    print("  " + "-" * 58)
    # Group by target
    for target in ['hypo', 'high']:
        print(f"\n  --- {target.upper()} ---")
        target_items = [(k, v) for k, v in results.items() if target in k]
        for k, v in sorted(target_items, key=lambda x: -x[1]['average'].get('auc_roc', 0)):
            a = v['average']
            nch = v.get('n_channels', v.get('n_features', '?'))
            print(f"  {k:40s} {a.get('auc_roc', 0):7.4f} {a.get('f1', 0):7.4f} {nch!s:>4s}")

    save_results(results, 'exp422_metabolic_phase_signal')
    return results


# ===================================================================
# EXP-430: Forecast→Classification Bridge
# ===================================================================

def _load_forecast_models(patient_name, experiments_dir, device, n_seeds=5):
    """Load pre-trained per-patient forecast models from EXP-419/410.

    Returns list of loaded PKGroupedEncoder models (one per seed).
    Falls back from EXP-419 → EXP-410 checkpoints.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from exp_pk_forecast_v14 import PKGroupedEncoder

    seeds = [42, 123, 456, 789, 1024][:n_seeds]
    models = []
    for seed in seeds:
        for prefix in [f'exp419_ft_{patient_name}_s{seed}',
                       f'exp410_ft_{patient_name}_s{seed}']:
            ckpt_path = os.path.join(experiments_dir, f'{prefix}.pth')
            if os.path.exists(ckpt_path):
                model = PKGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4)
                ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
                model.load_state_dict(ckpt['model_state'])
                model.to(device)
                model.eval()
                models.append(model)
                break
    return models


def _generate_forecast_features(models, history_grid, history_pk, isf, device,
                                glucose_scale=400.0):
    """Generate forecast-derived features from ensemble of forecast models.

    Takes the last 12 steps of history (1h) as context, predicts next 12 steps (1h).
    Returns dict of scalar features extracted from the predicted trajectory.

    Input channels for PKGroupedEncoder:
      [glucose/400, IOB, COB, net_basal, insulin_net/0.05, carb_rate/0.5, sin, net_balance/20]
    """
    PK_NORMS = [1.0, 0.05, 1.0, 0.5, 0.05, 1.0, 20.0, 1.0]  # from exp_pk_forecast_v14

    half = 12  # 12 steps history + 12 steps future = 24 total (w24)
    # Need at least 24 steps of data to form a w24 window
    if len(history_grid) < 24 or len(history_pk) < 24:
        return None

    # Build a 24-step window: last 24 steps of history
    base = history_grid[-24:].copy()  # (24, 8)
    pk = history_pk[-24:]

    # Replace channels 4,5 with PK and add net_balance (PK-future format)
    x = base.copy()
    x[:, 4] = pk[:, 1] / PK_NORMS[1]  # insulin_net
    x[:, 5] = pk[:, 3] / PK_NORMS[3]  # carb_rate
    x[:, 7] = pk[:, 6] / PK_NORMS[6]  # net_balance replaces cos

    # ISF normalization (if available)
    if isf is not None and isf > 0:
        x[:, 0] *= (glucose_scale / isf)
        x[:, 0] = np.clip(x[:, 0], 0, 10)

    # Mask future glucose (steps 12-23)
    x_tensor = torch.tensor(x, dtype=torch.float32).unsqueeze(0).to(device)
    x_masked = x_tensor.clone()
    x_masked[:, half:, 0] = 0.0  # mask future glucose

    # Get ensemble predictions
    all_preds = []
    with torch.no_grad():
        for model in models:
            pred = model(x_masked, causal=True)
            p = pred[0, half:, 0].cpu().numpy()  # future glucose predictions
            # Undo ISF normalization
            if isf is not None and isf > 0:
                p = p * (isf / glucose_scale) * glucose_scale
            else:
                p = p * glucose_scale
            all_preds.append(p)

    if not all_preds:
        return None

    preds = np.stack(all_preds)  # (n_models, 12)
    mean_pred = preds.mean(axis=0)  # (12,) — ensemble mean trajectory

    # Extract features from predicted trajectory
    features = {
        'pred_min':          float(np.min(mean_pred)),
        'pred_max':          float(np.max(mean_pred)),
        'pred_mean':         float(np.mean(mean_pred)),
        'pred_end':          float(mean_pred[-1]),
        'pred_slope':        float(mean_pred[-1] - mean_pred[0]),
        'pred_below_70':     float(np.sum(mean_pred < 70)),
        'pred_below_80':     float(np.sum(mean_pred < 80)),
        'pred_above_180':    float(np.sum(mean_pred > 180)),
        'pred_above_250':    float(np.sum(mean_pred > 250)),
        'pred_time_to_min':  float(np.argmin(mean_pred)),
        'pred_range':        float(np.max(mean_pred) - np.min(mean_pred)),
        'pred_volatility':   float(np.std(np.diff(mean_pred))),
    }

    # Ensemble uncertainty features
    if len(all_preds) > 1:
        features['ens_spread_mean'] = float(np.std(preds, axis=0).mean())
        features['ens_spread_at_min'] = float(np.std(preds[:, np.argmin(mean_pred)]))
        mins_per_model = preds.min(axis=1)
        features['ens_min_spread'] = float(np.std(mins_per_model))
        features['ens_worst_case'] = float(np.min(mins_per_model))
    else:
        features['ens_spread_mean'] = 0.0
        features['ens_spread_at_min'] = 0.0
        features['ens_min_spread'] = 0.0
        features['ens_worst_case'] = features['pred_min']

    return features


def run_exp430(args):
    """EXP-430: Forecast→Classification Bridge.

    Use pre-trained glucose forecast models (EXP-419/410 PKGroupedEncoder)
    to generate predicted trajectories, then extract features for
    classification.  Tests whether forecast-derived features can break
    the hypo AUC ~0.69 ceiling.

    Variants:
      - baseline_tabular: hand-crafted features only (control)
      - forecast_only: forecast-derived features only
      - combined: hand-crafted + forecast features
      - combined_cnn: CNN on raw history + forecast features as side input
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)
    experiments_dir = str(RESULTS_DIR)

    print(f"\n{'='*60}")
    print("EXP-430: Forecast→Classification Bridge")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    # Check forecast model availability
    n_seeds_forecast = 5 if not args.quick else 1
    available_patients = []
    for pat in patients:
        models = _load_forecast_models(pat['name'], experiments_dir, device,
                                       n_seeds=n_seeds_forecast)
        if models:
            available_patients.append((pat, models))
            print(f"  {pat['name']}: {len(models)} forecast model(s) loaded")
        else:
            print(f"  {pat['name']}: no forecast models found, skipping")

    if not available_patients:
        print("  No patients with forecast models. Run EXP-419 or EXP-410 first.")
        return {}

    # Load ISF per patient (for forecast model normalization)
    from exp_pk_forecast_v14 import load_patient_profile_isf
    patient_isfs = {}
    for pat, _ in available_patients:
        pdir = [d for d in find_patient_dirs(args.patients_dir) if d.name == pat['name']]
        if pdir:
            train_dir = str(pdir[0] / 'training')
            patient_isfs[pat['name']] = load_patient_profile_isf(train_dir)
        else:
            patient_isfs[pat['name']] = None

    results = {}

    for task_name, threshold, above in [('hypo', 70, False), ('high', 180, True)]:
        print(f"\n  --- {task_name.upper()} prediction ---")

        future_steps = STEPS_2H  # predict 2h ahead
        history_steps = STEPS_2H  # 2h history context

        all_baseline_feats, all_forecast_feats, all_combined_feats = [], [], []
        all_y, all_pids = [], []

        for pat, forecast_models in available_patients:
            grid = pat['grid']
            pk = pat['pk']
            glucose_raw = grid[:, 0] * 400
            isf = patient_isfs.get(pat['name'])
            total = history_steps + future_steps

            for start in range(0, len(grid) - total, STEPS_PER_HOUR):
                ctx_end = start + history_steps
                label_end = ctx_end + future_steps

                future_g = glucose_raw[ctx_end:label_end]
                if np.isnan(future_g).mean() > 0.3:
                    continue
                future_valid = future_g[~np.isnan(future_g)]
                if len(future_valid) == 0:
                    continue

                if above:
                    label = int(np.sum(future_valid > threshold) / len(future_valid) > 0.2)
                else:
                    label = int((future_valid < threshold).any())

                # Baseline tabular features (same as EXP-421)
                ctx_gluc = glucose_raw[start:ctx_end]
                valid_gluc = ctx_gluc[~np.isnan(ctx_gluc)]
                if len(valid_gluc) < 5:
                    valid_gluc = np.array([120.0] * 5)
                baseline = [
                    float(np.mean(valid_gluc)),
                    float(np.std(valid_gluc)),
                    float(np.min(valid_gluc)),
                    float(np.max(valid_gluc)),
                    float(valid_gluc[-1]),
                    float(valid_gluc[-1] - valid_gluc[-min(6, len(valid_gluc))]),
                    float(np.mean(valid_gluc < 80)),
                    float(np.mean(valid_gluc < 70)),
                    float(np.mean(valid_gluc > 180)),
                    float(np.sum(np.abs(np.diff(valid_gluc)))),
                ]
                for ch_idx in [1, 2, 3, 4]:
                    ch = grid[start:ctx_end, ch_idx]
                    ch_v = ch[~np.isnan(ch)]
                    if len(ch_v) == 0:
                        ch_v = np.array([0.0])
                    baseline.extend([float(np.mean(ch_v)), float(np.sum(ch_v)),
                                     float(ch_v[-1])])

                # Forecast features
                ff = _generate_forecast_features(
                    forecast_models,
                    grid[start:ctx_end],
                    pk[start:ctx_end],
                    isf, device)
                if ff is None:
                    continue

                forecast_vec = list(ff.values())
                all_baseline_feats.append(baseline)
                all_forecast_feats.append(forecast_vec)
                all_combined_feats.append(baseline + forecast_vec)
                all_y.append(label)
                all_pids.append(pat['name'])

        if len(all_y) < 50:
            print(f"    Insufficient samples: {len(all_y)}"); continue

        y = np.array(all_y)
        pids = np.array(all_pids)
        X_base = np.nan_to_num(np.array(all_baseline_feats, dtype=np.float32), nan=0.0)
        X_fore = np.nan_to_num(np.array(all_forecast_feats, dtype=np.float32), nan=0.0)
        X_comb = np.nan_to_num(np.array(all_combined_feats, dtype=np.float32), nan=0.0)

        pos_rate = y.mean()
        print(f"    N={len(y)}, pos_rate={pos_rate:.2%}, "
              f"base={X_base.shape[1]}f, fore={X_fore.shape[1]}f, comb={X_comb.shape[1]}f")

        variants = [
            ('baseline_tabular', X_base),
            ('forecast_only', X_fore),
            ('combined', X_comb),
        ]

        for vname, X in variants:
            key = f"{vname}_{task_name}"
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y, pids=pids)

            seed_metrics = []
            for seed in cfg['seeds']:
                np.random.seed(seed)
                # XGBoost for tabular features
                scale_pos = max(1.0, (tr_y == 0).sum() / max((tr_y == 1).sum(), 1))
                clf = xgb.XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    scale_pos_weight=float(scale_pos),
                    eval_metric='logloss', random_state=seed, verbosity=0,
                    use_label_encoder=False)
                clf.fit(tr_X, tr_y, eval_set=[(va_X, va_y)], verbose=False)

                va_prob = clf.predict_proba(va_X)[:, 1]
                va_pred = clf.predict(va_X)
                m = {
                    'f1': round(float(f1_score(va_y, va_pred, zero_division=0)), 4),
                    'accuracy': round(float(accuracy_score(va_y, va_pred)), 4),
                }
                try:
                    m['auc_roc'] = round(float(roc_auc_score(va_y, va_prob)), 4)
                except ValueError:
                    pass
                seed_metrics.append(m)

            avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
                   for k in seed_metrics[0]}
            results[key] = {
                'seeds': seed_metrics, 'average': avg,
                'n_samples': len(X), 'n_features': int(X.shape[1]),
            }
            auc = avg.get('auc_roc', 0)
            print(f"    {key:40s}  AUC={auc:.4f}  F1={avg['f1']:.4f}  ({X.shape[1]}f)")

    # Summary
    print(f"\n  {'='*58}")
    print(f"  {'Config':40s} {'AUC':>7s} {'F1':>7s} {'feat':>5s}")
    print(f"  {'-'*58}")
    for target in ['hypo', 'high']:
        print(f"\n  --- {target.upper()} ---")
        items = [(k, v) for k, v in results.items() if target in k]
        for k, v in sorted(items, key=lambda x: -x[1]['average'].get('auc_roc', 0)):
            a = v['average']
            nf = v.get('n_features', '?')
            print(f"  {k:40s} {a.get('auc_roc',0):7.4f} {a.get('f1',0):7.4f} {nf!s:>5s}")

    save_results(results, 'exp430_forecast_bridge')
    return results


# ===================================================================
# EXP-431: Phenotype-Adaptive Classification
# ===================================================================

def _classify_phenotype(glucose_raw):
    """Classify patient phenotype based on EXP-416 findings.

    Returns 'morning_high' or 'night_hypo' based on when risk events
    cluster.  Uses the dawn phenomenon vs overnight sensitivity distinction
    discovered in EXP-416.
    """
    morning_start, morning_end = 72, 144    # 06:00-12:00 (indices in 24h)
    night_start, night_end = 0, 72          # 00:00-06:00

    morning_highs, night_hypos = 0, 0
    n_days = len(glucose_raw) // STEPS_24H
    for d in range(n_days):
        day = glucose_raw[d * STEPS_24H:(d + 1) * STEPS_24H]
        if len(day) < STEPS_24H:
            continue
        morning = day[morning_start:morning_end]
        night = day[night_start:night_end]
        morning_valid = morning[~np.isnan(morning)]
        night_valid = night[~np.isnan(night)]
        if len(morning_valid) > 10:
            morning_highs += int((morning_valid > 180).sum() > STEPS_PER_HOUR)
        if len(night_valid) > 10:
            night_hypos += int((night_valid < 70).any())

    if n_days == 0:
        return 'morning_high'
    if night_hypos / max(n_days, 1) > morning_highs / max(n_days, 1):
        return 'night_hypo'
    return 'morning_high'


def run_exp431(args):
    """EXP-431: Phenotype-Adaptive Classification.

    Uses EXP-416 finding that patients cluster into 'morning-high' vs
    'night-hypo' phenotypes.  Tests whether phenotype-specific features
    or routing improves classification.

    Variants:
      - global: single model for all patients (baseline)
      - phenotype_feature: phenotype as additional feature
      - phenotype_routed: separate model per phenotype
      - time_of_day_feature: hour-of-day features (continuous proxy for phenotype)
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)

    print(f"\n{'='*60}")
    print("EXP-431: Phenotype-Adaptive Classification")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    # Classify phenotypes
    phenotypes = {}
    for pat in patients:
        glucose_raw = pat['grid'][:, 0] * 400
        ptype = _classify_phenotype(glucose_raw)
        phenotypes[pat['name']] = ptype
        print(f"  {pat['name']}: {ptype}")

    morning_count = sum(1 for v in phenotypes.values() if v == 'morning_high')
    night_count = sum(1 for v in phenotypes.values() if v == 'night_hypo')
    print(f"  Phenotype split: {morning_count} morning-high, {night_count} night-hypo")

    results = {}
    history_steps = STEPS_2H
    future_steps = STEPS_2H

    for task_name, threshold, above in [('hypo', 70, False), ('high', 180, True)]:
        print(f"\n  --- {task_name.upper()} ---")

        # Build features with phenotype + time-of-day annotations
        all_feats_base, all_feats_pheno, all_feats_time = [], [], []
        all_y, all_pids, all_phenos = [], [], []

        for pat in patients:
            grid = pat['grid']
            pk = pat['pk']
            glucose_raw = grid[:, 0] * 400
            ptype = phenotypes[pat['name']]
            pheno_code = 1.0 if ptype == 'night_hypo' else 0.0
            total = history_steps + future_steps

            for start in range(0, len(grid) - total, STEPS_PER_HOUR):
                ctx_end = start + history_steps
                future_g = glucose_raw[ctx_end:ctx_end + future_steps]
                if np.isnan(future_g).mean() > 0.3:
                    continue
                future_valid = future_g[~np.isnan(future_g)]
                if len(future_valid) == 0:
                    continue

                if above:
                    label = int(np.sum(future_valid > threshold) / len(future_valid) > 0.2)
                else:
                    label = int((future_valid < threshold).any())

                ctx_gluc = glucose_raw[start:ctx_end]
                valid_gluc = ctx_gluc[~np.isnan(ctx_gluc)]
                if len(valid_gluc) < 5:
                    valid_gluc = np.array([120.0] * 5)

                base = [
                    float(np.mean(valid_gluc)), float(np.std(valid_gluc)),
                    float(np.min(valid_gluc)), float(np.max(valid_gluc)),
                    float(valid_gluc[-1]),
                    float(valid_gluc[-1] - valid_gluc[-min(6, len(valid_gluc))]),
                    float(np.mean(valid_gluc < 80)), float(np.mean(valid_gluc < 70)),
                    float(np.mean(valid_gluc > 180)),
                    float(np.sum(np.abs(np.diff(valid_gluc)))),
                ]
                for ch_idx in [1, 2, 3, 4]:
                    ch = grid[start:ctx_end, ch_idx]
                    ch_v = ch[~np.isnan(ch)]
                    if len(ch_v) == 0: ch_v = np.array([0.0])
                    base.extend([float(np.mean(ch_v)), float(np.sum(ch_v)),
                                 float(ch_v[-1])])

                # Time-of-day: sin/cos of position within 24h cycle
                step_in_day = start % STEPS_24H
                hour_frac = step_in_day / STEPS_24H
                tod_sin = float(np.sin(2 * np.pi * hour_frac))
                tod_cos = float(np.cos(2 * np.pi * hour_frac))
                # Also add morning/night/afternoon/evening flags
                hour = (step_in_day / STEPS_PER_HOUR) % 24
                is_morning = float(6 <= hour < 12)
                is_afternoon = float(12 <= hour < 18)
                is_evening = float(18 <= hour < 24)
                is_night = float(0 <= hour < 6)

                all_feats_base.append(base)
                all_feats_pheno.append(base + [pheno_code])
                all_feats_time.append(base + [tod_sin, tod_cos,
                                              is_morning, is_afternoon,
                                              is_evening, is_night])
                all_y.append(label)
                all_pids.append(pat['name'])
                all_phenos.append(ptype)

        if len(all_y) < 50:
            print(f"    Insufficient samples"); continue

        y = np.array(all_y)
        pids = np.array(all_pids)
        phenos = np.array(all_phenos)
        X_base = np.nan_to_num(np.array(all_feats_base, dtype=np.float32), nan=0.0)
        X_pheno = np.nan_to_num(np.array(all_feats_pheno, dtype=np.float32), nan=0.0)
        X_time = np.nan_to_num(np.array(all_feats_time, dtype=np.float32), nan=0.0)

        print(f"    N={len(y)}, pos={y.mean():.2%}")

        # Variant 1-3: global models with different features
        for vname, X in [('global', X_base), ('phenotype_feat', X_pheno),
                         ('time_of_day', X_time)]:
            key = f"{vname}_{task_name}"
            (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y, pids=pids)

            seed_metrics = []
            for seed in cfg['seeds']:
                np.random.seed(seed)
                scale_pos = max(1.0, (tr_y == 0).sum() / max((tr_y == 1).sum(), 1))
                clf = xgb.XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    scale_pos_weight=float(scale_pos),
                    eval_metric='logloss', random_state=seed, verbosity=0,
                    use_label_encoder=False)
                clf.fit(tr_X, tr_y, eval_set=[(va_X, va_y)], verbose=False)
                va_prob = clf.predict_proba(va_X)[:, 1]
                va_pred = clf.predict(va_X)
                m = {'f1': round(float(f1_score(va_y, va_pred, zero_division=0)), 4),
                     'accuracy': round(float(accuracy_score(va_y, va_pred)), 4)}
                try: m['auc_roc'] = round(float(roc_auc_score(va_y, va_prob)), 4)
                except ValueError: pass
                seed_metrics.append(m)

            avg = {k: round(float(np.mean([s[k] for s in seed_metrics if k in s])), 4)
                   for k in seed_metrics[0]}
            results[key] = {'seeds': seed_metrics, 'average': avg,
                            'n_samples': len(X), 'n_features': int(X.shape[1])}
            print(f"    {key:40s}  AUC={avg.get('auc_roc',0):.4f}")

        # Variant 4: phenotype-routed (separate model per phenotype)
        key = f"phenotype_routed_{task_name}"
        (tr_X, tr_y, tr_pids, tr_phenos), (va_X, va_y, va_pids, va_phenos) = \
            temporal_split(X_base, y, pids, phenos, pids=pids)

        va_prob_routed = np.zeros(len(va_y))
        va_pred_routed = np.zeros(len(va_y), dtype=int)

        for ptype in ['morning_high', 'night_hypo']:
            tr_mask = tr_phenos == ptype
            va_mask = va_phenos == ptype
            if tr_mask.sum() < 10 or va_mask.sum() < 5:
                continue
            seed = cfg['seeds'][0]
            np.random.seed(seed)
            scale_pos = max(1.0, (tr_y[tr_mask] == 0).sum() / max((tr_y[tr_mask] == 1).sum(), 1))
            clf = xgb.XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                scale_pos_weight=float(scale_pos),
                eval_metric='logloss', random_state=seed, verbosity=0,
                use_label_encoder=False)
            clf.fit(tr_X[tr_mask], tr_y[tr_mask],
                    eval_set=[(va_X[va_mask], va_y[va_mask])], verbose=False)
            va_prob_routed[va_mask] = clf.predict_proba(va_X[va_mask])[:, 1]
            va_pred_routed[va_mask] = clf.predict(va_X[va_mask])

        m_routed = {'f1': round(float(f1_score(va_y, va_pred_routed, zero_division=0)), 4),
                     'accuracy': round(float(accuracy_score(va_y, va_pred_routed)), 4)}
        try: m_routed['auc_roc'] = round(float(roc_auc_score(va_y, va_prob_routed)), 4)
        except ValueError: pass
        results[key] = {'seeds': [m_routed], 'average': m_routed,
                        'n_samples': len(X_base), 'n_features': int(X_base.shape[1]),
                        'phenotype_counts': {'morning_high': int(morning_count),
                                             'night_hypo': int(night_count)}}
        print(f"    {key:40s}  AUC={m_routed.get('auc_roc',0):.4f}")

    # Summary
    print(f"\n  {'='*58}")
    print(f"  {'Config':40s} {'AUC':>7s} {'F1':>7s}")
    print(f"  {'-'*58}")
    for target in ['hypo', 'high']:
        print(f"\n  --- {target.upper()} ---")
        items = [(k, v) for k, v in results.items() if target in k]
        for k, v in sorted(items, key=lambda x: -x[1]['average'].get('auc_roc', 0)):
            a = v['average']
            print(f"  {k:40s} {a.get('auc_roc',0):7.4f} {a.get('f1',0):7.4f}")

    save_results(results, 'exp431_phenotype_adaptive')
    return results


# ===================================================================
# EXP-432: Operating Point Optimization
# ===================================================================

def run_exp432(args):
    """EXP-432: Operating Point Optimization for Deployable Models.

    For our deployable HIGH classifiers (AUC > 0.80), compute full
    sensitivity/specificity curves and find optimal alert thresholds
    for clinical deployment:
      - Sensitivity@90%: what specificity can we achieve with 90% recall?
      - PPV at practical threshold: positive predictive value
      - Alert fatigue: false alarm rate at various operating points

    Tests 2h HIGH, overnight HIGH, and recurrence models.
    """
    cfg = _get_config(args)
    device = resolve_device(args.device)

    print(f"\n{'='*60}")
    print("EXP-432: Operating Point Optimization")
    print(f"{'='*60}")

    patients = load_patients(args.patients_dir, cfg['max_patients'])
    if not patients:
        print("  No patient data found."); return {}

    from sklearn.metrics import precision_recall_curve, roc_curve

    results = {}

    # Task configurations matching our best models
    tasks = [
        {'name': '2h_high_16ch', 'history': STEPS_2H, 'future': STEPS_2H,
         'threshold': 180, 'above': True,
         'feat_fn': lambda pat, s, h: np.concatenate([
             pat['grid'][s:s+h], pat['pk'][s:s+h]], axis=-1)},  # 16ch
        {'name': 'overnight_high', 'history': STEPS_12H, 'future': STEPS_8H,
         'threshold': 180, 'above': True,
         'feat_fn': lambda pat, s, h: pat['grid'][s:s+h]},  # 8ch
        {'name': '2h_hypo_8ch', 'history': STEPS_2H, 'future': STEPS_2H,
         'threshold': 70, 'above': False,
         'feat_fn': lambda pat, s, h: pat['grid'][s:s+h]},  # 8ch baseline
        {'name': 'recurrence_high_24h', 'history': STEPS_12H, 'future': STEPS_24H,
         'threshold': 180, 'above': True,
         'feat_fn': lambda pat, s, h: pat['grid'][s:s+h]},
    ]

    for task in tasks:
        tname = task['name']
        print(f"\n  --- {tname} ---")
        history = task['history']
        future = task['future']
        total = history + future

        all_X, all_y, all_pids = [], [], []
        for pat in patients:
            glucose_raw = pat['grid'][:, 0] * 400
            stride = max(history // 2, STEPS_PER_HOUR)
            for start in range(0, len(pat['grid']) - total, stride):
                try:
                    x = task['feat_fn'](pat, start, history)
                except (IndexError, KeyError):
                    continue
                future_g = glucose_raw[start + history:start + total]
                if np.isnan(future_g).mean() > 0.3:
                    continue
                future_valid = future_g[~np.isnan(future_g)]
                if len(future_valid) == 0:
                    continue
                if task['above']:
                    label = int(np.sum(future_valid > task['threshold']) / len(future_valid) > 0.2)
                else:
                    label = int((future_valid < task['threshold']).any())
                all_X.append(x)
                all_y.append(label)
                all_pids.append(pat['name'])

        if len(all_X) < 50:
            print(f"    Insufficient samples: {len(all_X)}"); continue

        X = np.nan_to_num(np.stack(all_X).astype(np.float32), nan=0.0)
        y = np.array(all_y)
        pids = np.array(all_pids)
        print(f"    N={len(y)}, pos_rate={y.mean():.2%}, ch={X.shape[-1]}")
        (tr_X, tr_y), (va_X, va_y) = temporal_split(X, y, pids=pids)

        # Train CNN and collect probability scores across seeds
        all_probs = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = FlexCNN(in_channels=X.shape[-1], out_dim=2).to(device)
            _train_torch_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                    epochs=cfg['epochs'], patience=cfg['patience'])
            model.eval()
            with torch.no_grad():
                v_X_t = torch.tensor(va_X, dtype=torch.float32).to(device)
                logits = model(v_X_t)
                probs = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()
            all_probs.append(probs)

        # Ensemble probabilities
        ens_probs = np.mean(all_probs, axis=0)

        # Compute operating point curves
        try:
            fpr, tpr, roc_thresholds = roc_curve(va_y, ens_probs)
            prec, recall, pr_thresholds = precision_recall_curve(va_y, ens_probs)
            auc = float(roc_auc_score(va_y, ens_probs))
        except ValueError:
            print(f"    Cannot compute curves (single class?)"); continue

        # Find key operating points
        ops = {}

        # 1. Sensitivity@90%: what threshold gives ≥90% sensitivity?
        idx_90 = np.where(tpr >= 0.90)[0]
        if len(idx_90) > 0:
            i = idx_90[0]
            ops['sensitivity_90'] = {
                'threshold': round(float(roc_thresholds[i]), 4),
                'sensitivity': round(float(tpr[i]), 4),
                'specificity': round(float(1 - fpr[i]), 4),
                'fpr': round(float(fpr[i]), 4),
            }

        # 2. Sensitivity@95%
        idx_95 = np.where(tpr >= 0.95)[0]
        if len(idx_95) > 0:
            i = idx_95[0]
            ops['sensitivity_95'] = {
                'threshold': round(float(roc_thresholds[i]), 4),
                'sensitivity': round(float(tpr[i]), 4),
                'specificity': round(float(1 - fpr[i]), 4),
                'fpr': round(float(fpr[i]), 4),
            }

        # 3. Youden's J (optimal balanced point)
        j_scores = tpr - fpr
        best_j_idx = np.argmax(j_scores)
        ops['youden_optimal'] = {
            'threshold': round(float(roc_thresholds[best_j_idx]), 4),
            'sensitivity': round(float(tpr[best_j_idx]), 4),
            'specificity': round(float(1 - fpr[best_j_idx]), 4),
            'j_score': round(float(j_scores[best_j_idx]), 4),
        }

        # 4. Max PPV with recall ≥ 50%
        idx_r50 = np.where(recall >= 0.50)[0]
        if len(idx_r50) > 0:
            best_ppv_idx = idx_r50[np.argmax(prec[idx_r50])]
            ops['max_ppv_recall50'] = {
                'threshold': round(float(pr_thresholds[min(best_ppv_idx, len(pr_thresholds)-1)]), 4),
                'ppv': round(float(prec[best_ppv_idx]), 4),
                'recall': round(float(recall[best_ppv_idx]), 4),
            }

        # 5. Alert fatigue: FPR at sensitivity = 80%
        idx_80 = np.where(tpr >= 0.80)[0]
        if len(idx_80) > 0:
            i = idx_80[0]
            ops['alert_fatigue_sens80'] = {
                'false_alarm_rate': round(float(fpr[i]), 4),
                'sensitivity': round(float(tpr[i]), 4),
                'alerts_per_100': round(float(fpr[i] * (1 - va_y.mean()) * 100 + tpr[i] * va_y.mean() * 100), 1),
            }

        results[tname] = {
            'auc': round(auc, 4),
            'n_val': int(len(va_y)),
            'pos_rate': round(float(va_y.mean()), 4),
            'operating_points': ops,
            'n_seeds': len(cfg['seeds']),
        }

        print(f"    AUC={auc:.4f}")
        for op_name, op_data in ops.items():
            details = ', '.join(f'{k}={v}' for k, v in op_data.items())
            print(f"      {op_name}: {details}")

    # Deployability summary
    print(f"\n  {'='*60}")
    print(f"  DEPLOYABILITY ASSESSMENT")
    print(f"  {'='*60}")
    for tname, res in results.items():
        auc = res['auc']
        ops = res['operating_points']
        deployable = auc >= 0.80
        sens90 = ops.get('sensitivity_90', {})
        spec_at_90 = sens90.get('specificity', 0)
        status = '✅ DEPLOY' if (deployable and spec_at_90 > 0.40) else '❌ NOT READY'
        print(f"  {tname:35s}  AUC={auc:.3f}  Spec@Sens90={spec_at_90:.2f}  {status}")

    save_results(results, 'exp432_operating_points')
    return results


EXPERIMENTS = {
    '411': run_exp411,
    '412': run_exp412,
    '413': run_exp413,
    '414': run_exp414,
    '415': run_exp415,
    '416': run_exp416,
    '417': run_exp417,
    '418': run_exp418,
    '420': run_exp420,
    '421': run_exp421,
    '422': run_exp422,
    '430': run_exp430,
    '431': run_exp431,
    '432': run_exp432,
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
        description='EXP-411-420: Living Treatment Plan — Strategic Planning Horizon',
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
  420  Hypo breakthrough: feature + loss engineering
  421  Hypo architecture + context sweep (XGB/CNN × 6h/12h/24h)
  422  Metabolic phase signal (flux/phase/integral/overshoot channels)
  430  Forecast→Classification bridge (use forecast models as features)
  431  Phenotype-adaptive classification (morning-high vs night-hypo routing)
  432  Operating point optimization (sensitivity/specificity for deployment)
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
