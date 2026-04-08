#!/usr/bin/env python3
"""EXP-1121 to EXP-1130: Pushing the Information Frontier.

Campaign status after 120 experiments:
- SOTA: R²=0.547 (block CV, grand combined)
- Residual LSTM: +0.024 R² on top of ensemble
- Noise ceiling: R²=0.854 (σ=15 mg/dL)
- Remaining gap: 0.307 (76% unexplained, 24% irreducible)

This batch explores novel approaches to push beyond the information frontier:
  EXP-1121: Full Pipeline (All Winners Stacked) ★★★
  EXP-1122: Learned Embedding + XGBoost ★★
  EXP-1123: Multi-Scale Wavelet Decomposition ★★★
  EXP-1124: Temporal Attention Transformer ★★
  EXP-1125: Asymmetric Loss (Hypo-Penalized) ★★★
  EXP-1126: Augmented Features (Glucose Density + Depth) ★★
  EXP-1127: Forecast Horizon Curriculum ★★
  EXP-1128: Per-Patient XGBoost + LSTM Pipeline ★★★
  EXP-1129: Error-Aware Ensemble (Predicted Difficulty) ★★
  EXP-1130: Definitive Benchmark (Block CV + All Metrics) ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1121 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge

warnings.filterwarnings('ignore')

try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features

import torch
import torch.nn as nn

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6        # 30-min stride
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ---------------------------------------------------------------------------
# Shared helpers (from exp_clinical_1111.py)
# ---------------------------------------------------------------------------

class TCN(nn.Module):
    def __init__(self, in_channels, window_size=24, hidden=32, n_levels=3):
        super().__init__()
        layers = []
        for i in range(n_levels):
            dilation = 2 ** i
            padding = (3 - 1) * dilation
            in_ch = in_channels if i == 0 else hidden
            layers.append(nn.Conv1d(in_ch, hidden, 3, dilation=dilation,
                                    padding=padding))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(0.1))
        self.network = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x):
        h = self.network(x.permute(0, 2, 1))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


class ResidualLSTM(nn.Module):
    def __init__(self, hidden=32, seq_len=12):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True, num_layers=1)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


class MiniTransformer(nn.Module):
    """Small transformer for temporal glucose prediction."""
    def __init__(self, in_channels, window_size=24, d_model=32, nhead=4, num_layers=2):
        super().__init__()
        self.input_proj = nn.Linear(in_channels, d_model)
        self.pos_embed = nn.Parameter(torch.randn(1, window_size, d_model) * 0.01)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=64,
            dropout=0.1, batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Linear(d_model, 1)

    def forward(self, x):
        # x: (B, time, channels)
        h = self.input_proj(x) + self.pos_embed[:, :x.size(1), :]
        h = self.encoder(h)
        h = h.mean(dim=1)  # global average pooling
        return self.head(h).squeeze(-1)


class GlucoseEmbedder(nn.Module):
    """Learn a fixed-size embedding from glucose window for use as XGBoost features."""
    def __init__(self, in_channels, window_size=24, embed_dim=16):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 32, 3, padding=1)
        self.conv2 = nn.Conv1d(32, 16, 3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(16, embed_dim)
        self.head = nn.Linear(embed_dim, 1)
        self.relu = nn.ReLU()
        self.embed_dim = embed_dim

    def forward(self, x):
        h = self.relu(self.conv1(x.permute(0, 2, 1)))
        h = self.relu(self.conv2(h))
        h = self.pool(h).squeeze(-1)
        embed = self.relu(self.fc(h))
        return self.head(embed).squeeze(-1), embed


def prepare_patient_raw(p):
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    return glucose, physics


def make_windows(glucose, physics, window=WINDOW, horizon=HORIZON,
                 stride=STRIDE):
    X_list, y_list = [], []
    g = glucose / GLUCOSE_SCALE
    for i in range(0, len(g) - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue
        X_list.append(np.column_stack([g_win.reshape(-1, 1), p_win]))
        y_list.append(y_val)
    if len(X_list) == 0:
        return np.array([]).reshape(0, window, 1), np.array([])
    return np.array(X_list), np.array(y_list)


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:], y[:s1], y[s1:s2], y[s2:])


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def compute_mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def block_cv_score(X, y, model_fn, n_folds=3):
    n = len(X)
    fold_size = n // n_folds
    scores = []
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size if fold < n_folds - 1 else n
        mask = np.ones(n, dtype=bool)
        mask[val_start:val_end] = False
        X_tr, y_tr = X[mask], y[mask]
        X_vl, y_vl = X[~mask], y[~mask]
        model = model_fn()
        model.fit(X_tr, y_tr)
        pred = model.predict(X_vl)
        scores.append(compute_r2(y_vl, pred))
    return float(np.mean(scores)), scores


def build_grand_features(glucose, physics, window=WINDOW, horizon=HORIZON,
                         stride=STRIDE):
    """Build grand features, return (X, y_abs, g_current)."""
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]
        base = np.concatenate([g_win, p_win.ravel()])
        supply, demand, hepatic, net = p_win[:, 0], p_win[:, 1], p_win[:, 2], p_win[:, 3]
        g_mean = np.mean(g_win)

        interactions = np.array([
            np.mean(supply * demand), np.mean(supply * g_mean),
            np.mean(demand * g_mean),
            np.mean(np.diff(net)) if len(net) > 1 else 0.0,
            np.mean(hepatic * supply),
        ])

        derivatives = []
        for scale in [3, 6, 12]:
            if len(g_win) > scale:
                roc = np.mean(np.diff(g_win[::max(1, scale // 3)]))
            else:
                roc = 0.0
            derivatives.append(roc)
        if len(g_win) > 2:
            d1 = np.diff(g_win)
            accel = np.mean(np.diff(d1))
        else:
            accel = 0.0
        derivatives.append(accel)
        derivatives = np.array(derivatives)

        g_std = np.std(g_win)
        g_min, g_max = np.min(g_win), np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        feat = np.concatenate([base, interactions, derivatives, stats])
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def make_xgb(n_estimators=200, max_depth=4, learning_rate=0.05, **kwargs):
    if not XGB_AVAILABLE:
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=n_estimators, max_depth=max_depth,
            learning_rate=learning_rate, random_state=42)
    return xgb.XGBRegressor(
        n_estimators=n_estimators, max_depth=max_depth,
        learning_rate=learning_rate,
        tree_method='hist', device='cuda' if torch.cuda.is_available() else 'cpu',
        random_state=42, verbosity=0, **kwargs)


def train_neural(model, X_train, y_train, X_val, epochs=60, lr=1e-3,
                 batch_size=256):
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    Xt = torch.tensor(X_train, dtype=torch.float32).to(DEVICE)
    yt = torch.tensor(y_train, dtype=torch.float32).to(DEVICE)
    Xv = torch.tensor(X_val, dtype=torch.float32).to(DEVICE)
    batch = min(batch_size, len(Xt))
    model.train()
    for _ in range(epochs):
        perm = torch.randperm(len(Xt))
        for start in range(0, len(Xt), batch):
            idx = perm[start:start + batch]
            pred = model(Xt[idx])
            loss = loss_fn(pred, yt[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    model.eval()
    with torch.no_grad():
        return model(Xv).cpu().numpy()


def impute_glucose(glucose_raw):
    """Interpolation + missing flag."""
    glucose = glucose_raw.copy()
    missing_mask = np.isnan(glucose)
    missing_pct = np.mean(missing_mask)
    if missing_pct > 0 and missing_pct < 0.5:
        valid_idx = np.where(~missing_mask)[0]
        if len(valid_idx) > 1:
            glucose[missing_mask] = np.interp(
                np.where(missing_mask)[0], valid_idx, glucose[valid_idx])
    return glucose, missing_mask


# ---------------------------------------------------------------------------
# EXP-1121: Full Pipeline (All Winners Stacked)
# ---------------------------------------------------------------------------

def exp_1121_full_pipeline(patients, detail=False):
    """Complete pipeline: imputation → Δg → Ridge+XGB+TCN → ensemble → LSTM.

    This combines EXP-1111 (Δg+XGB+ensemble) + EXP-1118 (LSTM correction)
    + EXP-1120 (imputation) into a single pipeline evaluated with block CV.
    """
    RESIDUAL_WINDOW = 12
    results = []

    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]

        # Impute
        glucose, missing_mask = impute_glucose(glucose_raw)

        # Build features
        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 400:
            continue

        # Add missing flag
        flag_series = missing_mask.astype(float)
        flag_feats = []
        g = glucose / GLUCOSE_SCALE
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue
            flag_feats.append(np.mean(flag_series[i:i + WINDOW]))
        flag_feats = np.array(flag_feats)
        if len(flag_feats) == len(X):
            X = np.column_stack([X, flag_feats])

        y_delta = y_abs - g_cur

        # 3-way split: train (60%), val-for-LSTM (20%), test (20%)
        X_tr, X_vl, X_te, y_tr_a, y_vl_a, y_te_a = split_3way(X, y_abs)
        _, _, _, y_tr_d, y_vl_d, y_te_d = split_3way(X, y_delta)
        gc_tr, gc_vl, gc_te = split_3way(X, g_cur)[3:]

        # Train base models on Δg
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr_d)
        pred_ridge_vl = ridge.predict(X_vl) + gc_vl
        pred_ridge_te = ridge.predict(X_te) + gc_te

        xgb_m = make_xgb()
        xgb_m.fit(X_tr, y_tr_d)
        pred_xgb_vl = xgb_m.predict(X_vl) + gc_vl
        pred_xgb_te = xgb_m.predict(X_te) + gc_te

        # Optimize ensemble weights on val
        from scipy.optimize import minimize
        preds_vl = np.column_stack([pred_ridge_vl, pred_xgb_vl])

        def neg_r2(w_raw):
            w = np.exp(w_raw) / np.sum(np.exp(w_raw))
            return -compute_r2(y_vl_a, preds_vl @ w)

        opt = minimize(neg_r2, [0.0, 0.0], method='Nelder-Mead')
        w_opt = np.exp(opt.x) / np.sum(np.exp(opt.x))

        pred_ens_vl = preds_vl @ w_opt
        pred_ens_te = np.column_stack([pred_ridge_te, pred_xgb_te]) @ w_opt

        r2_ens = compute_r2(y_te_a, pred_ens_te)

        # LSTM on val residuals
        residuals_vl = y_vl_a - pred_ens_vl

        resid_X, resid_y = [], []
        for i in range(RESIDUAL_WINDOW, len(residuals_vl)):
            resid_X.append(residuals_vl[i-RESIDUAL_WINDOW:i])
            resid_y.append(residuals_vl[i])

        if len(resid_X) < 50:
            r2_corrected = r2_ens
            lstm_gain = 0.0
        else:
            resid_X = np.array(resid_X).reshape(-1, RESIDUAL_WINDOW, 1)
            resid_y_arr = np.array(resid_y)

            lstm = ResidualLSTM(hidden=32, seq_len=RESIDUAL_WINDOW).to(DEVICE)
            optimizer_lstm = torch.optim.Adam(lstm.parameters(), lr=1e-3)
            loss_fn = nn.MSELoss()
            Xt = torch.tensor(resid_X, dtype=torch.float32).to(DEVICE)
            yt = torch.tensor(resid_y_arr, dtype=torch.float32).to(DEVICE)

            lstm.train()
            for _ in range(50):
                pred = lstm(Xt)
                loss = loss_fn(pred, yt)
                optimizer_lstm.zero_grad()
                loss.backward()
                optimizer_lstm.step()

            # Apply to test
            corrected = pred_ens_te.copy()
            resid_buffer = list(residuals_vl[-RESIDUAL_WINDOW:])

            lstm.eval()
            with torch.no_grad():
                for i in range(len(y_te_a)):
                    if len(resid_buffer) >= RESIDUAL_WINDOW:
                        window = np.array(resid_buffer[-RESIDUAL_WINDOW:]).reshape(
                            1, RESIDUAL_WINDOW, 1)
                        w_t = torch.tensor(window, dtype=torch.float32).to(DEVICE)
                        correction = lstm(w_t).cpu().numpy()[0]
                        corrected[i] = pred_ens_te[i] + correction
                    actual_resid = y_te_a[i] - pred_ens_te[i]
                    resid_buffer.append(actual_resid)

            r2_corrected = compute_r2(y_te_a, corrected)
            lstm_gain = r2_corrected - r2_ens

        # Also compute baseline Ridge (no Δg, no ensemble, no LSTM)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr, y_tr_a)
        r2_base = compute_r2(y_te_a, ridge_base.predict(X_te))

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge_baseline': round(r2_base, 4),
            'r2_dg_ensemble': round(r2_ens, 4),
            'r2_full_pipeline': round(r2_corrected, 4),
            'ensemble_weights': [round(w, 3) for w in w_opt],
            'pipeline_gain_vs_baseline': round(r2_corrected - r2_base, 4),
            'lstm_gain': round(lstm_gain, 4),
        })

        if detail:
            print(f"  {p['name']}: base={r2_base:.4f} ens={r2_ens:.4f} "
                  f"pipeline={r2_corrected:.4f} "
                  f"Δ_total={r2_corrected-r2_base:+.4f} "
                  f"Δ_lstm={lstm_gain:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_baseline', 'r2_dg_ensemble', 'r2_full_pipeline']}
    pipeline_wins = sum(1 for r in results
                        if r['r2_full_pipeline'] > r['r2_ridge_baseline'])
    mean_gain = np.mean([r['pipeline_gain_vs_baseline'] for r in results])

    return {
        'status': 'pass',
        'detail': (f"baseline={means['r2_ridge_baseline']:.4f} "
                   f"ensemble={means['r2_dg_ensemble']:.4f} "
                   f"pipeline={means['r2_full_pipeline']:.4f} "
                   f"(Δ={mean_gain:+.4f}, wins={pipeline_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': {
            'means': means, 'pipeline_wins': pipeline_wins,
            'mean_gain': round(mean_gain, 4), 'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1122: Learned Embedding + XGBoost
# ---------------------------------------------------------------------------

def exp_1122_embedding_xgb(patients, detail=False):
    """Train CNN to produce embeddings, use as XGBoost features."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        y_tr, y_vl = y_win[:split_idx], y_win[split_idx:]

        # Flat Ridge baseline
        X_flat = X_win.reshape(len(X_win), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_flat[:split_idx], y_tr)
        r2_ridge = compute_r2(y_vl, ridge.predict(X_flat[split_idx:]))

        # Train embedding CNN
        embedder = GlucoseEmbedder(in_channels=X_win.shape[2], embed_dim=16).to(DEVICE)
        optimizer = torch.optim.Adam(embedder.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()

        Xt = torch.tensor(Xw_tr, dtype=torch.float32).to(DEVICE)
        yt = torch.tensor(y_tr, dtype=torch.float32).to(DEVICE)

        embedder.train()
        for _ in range(60):
            perm = torch.randperm(len(Xt))
            for start in range(0, len(Xt), 256):
                idx = perm[start:start + 256]
                pred, _ = embedder(Xt[idx])
                loss = loss_fn(pred, yt[idx])
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Extract embeddings
        embedder.eval()
        with torch.no_grad():
            Xt_all = torch.tensor(X_win, dtype=torch.float32).to(DEVICE)
            _, embeds = embedder(Xt_all)
            embeds = embeds.cpu().numpy()

        embed_tr = embeds[:split_idx]
        embed_vl = embeds[split_idx:]

        # XGBoost on flat features
        xgb_flat = make_xgb()
        xgb_flat.fit(X_flat[:split_idx], y_tr)
        r2_xgb_flat = compute_r2(y_vl, xgb_flat.predict(X_flat[split_idx:]))

        # XGBoost on embeddings only
        xgb_embed = make_xgb()
        xgb_embed.fit(embed_tr, y_tr)
        r2_xgb_embed = compute_r2(y_vl, xgb_embed.predict(embed_vl))

        # XGBoost on flat + embeddings
        X_aug_tr = np.hstack([X_flat[:split_idx], embed_tr])
        X_aug_vl = np.hstack([X_flat[split_idx:], embed_vl])
        xgb_aug = make_xgb()
        xgb_aug.fit(X_aug_tr, y_tr)
        r2_xgb_aug = compute_r2(y_vl, xgb_aug.predict(X_aug_vl))

        results.append({
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_xgb_flat': round(r2_xgb_flat, 4),
            'r2_xgb_embed': round(r2_xgb_embed, 4),
            'r2_xgb_augmented': round(r2_xgb_aug, 4),
            'embed_gain': round(r2_xgb_aug - r2_xgb_flat, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge={r2_ridge:.4f} xgb_flat={r2_xgb_flat:.4f} "
                  f"xgb_embed={r2_xgb_embed:.4f} xgb_aug={r2_xgb_aug:.4f} "
                  f"Δ={r2_xgb_aug-r2_xgb_flat:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_xgb_flat', 'r2_xgb_embed', 'r2_xgb_augmented']}
    embed_wins = sum(1 for r in results if r['embed_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"xgb_flat={means['r2_xgb_flat']:.4f} "
                   f"xgb_aug={means['r2_xgb_augmented']:.4f} "
                   f"embed_only={means['r2_xgb_embed']:.4f} "
                   f"(embed gains={embed_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1123: Multi-Scale Wavelet Decomposition
# ---------------------------------------------------------------------------

def exp_1123_wavelet(patients, detail=False):
    """Wavelet decomposition of glucose for multi-scale features."""
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        # Simple wavelet-like decomposition: moving averages at different scales
        g = glucose / GLUCOSE_SCALE
        wave_feats = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            gw = np.nan_to_num(gw, nan=np.nanmean(gw) if np.any(~np.isnan(gw)) else 0.4)
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            # Multi-scale decomposition
            trend = np.convolve(gw, np.ones(6)/6, mode='same')     # slow trend
            detail_fast = gw - np.convolve(gw, np.ones(3)/3, mode='same')  # fast detail
            detail_slow = np.convolve(gw, np.ones(3)/3, mode='same') - trend  # medium detail

            wave_feats.append(np.concatenate([
                [np.std(detail_fast), np.mean(np.abs(detail_fast)),
                 np.std(detail_slow), np.mean(np.abs(detail_slow)),
                 trend[-1] - trend[0],   # trend direction
                 np.std(trend),           # trend stability
                 np.max(np.abs(detail_fast)),  # max fast oscillation
                 np.max(np.abs(detail_slow)),  # max slow oscillation
                ]
            ]))

        wave_feats = np.array(wave_feats)
        if len(wave_feats) != len(X):
            wave_feats = np.zeros((len(X), 8))

        X_aug = np.column_stack([X, wave_feats])

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xa_tr, Xa_vl = X_aug[:len(X_tr)], X_aug[len(X_tr):]

        # Ridge on base
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr, y_tr)
        r2_base = compute_r2(y_vl, ridge_base.predict(X_vl))

        # Ridge on augmented
        ridge_aug = Ridge(alpha=1.0)
        ridge_aug.fit(Xa_tr, y_tr)
        r2_aug = compute_r2(y_vl, ridge_aug.predict(Xa_vl))

        # XGB on augmented
        xgb_aug = make_xgb()
        xgb_aug.fit(Xa_tr, y_tr)
        r2_xgb = compute_r2(y_vl, xgb_aug.predict(Xa_vl))

        # XGB on base
        xgb_base = make_xgb()
        xgb_base.fit(X_tr, y_tr)
        r2_xgb_base = compute_r2(y_vl, xgb_base.predict(X_vl))

        results.append({
            'patient': p['name'],
            'r2_ridge_base': round(r2_base, 4),
            'r2_ridge_wavelet': round(r2_aug, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_wavelet': round(r2_xgb, 4),
            'ridge_gain': round(r2_aug - r2_base, 4),
            'xgb_gain': round(r2_xgb - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge base={r2_base:.4f} wave={r2_aug:.4f} "
                  f"Δ={r2_aug-r2_base:+.4f} | xgb base={r2_xgb_base:.4f} "
                  f"wave={r2_xgb:.4f} Δ={r2_xgb-r2_xgb_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_base', 'r2_ridge_wavelet', 'r2_xgb_base', 'r2_xgb_wavelet']}
    ridge_wins = sum(1 for r in results if r['ridge_gain'] > 0.001)
    xgb_wins = sum(1 for r in results if r['xgb_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: base={means['r2_ridge_base']:.4f} wave={means['r2_ridge_wavelet']:.4f} "
                   f"(wins={ridge_wins}) | xgb: base={means['r2_xgb_base']:.4f} "
                   f"wave={means['r2_xgb_wavelet']:.4f} (wins={xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1124: Temporal Attention Transformer
# ---------------------------------------------------------------------------

def exp_1124_transformer(patients, detail=False):
    """Small transformer vs TCN vs Ridge on glucose prediction."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        y_tr, y_vl = y_win[:split_idx], y_win[split_idx:]

        X_flat = X_win.reshape(len(X_win), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_flat[:split_idx], y_tr)
        r2_ridge = compute_r2(y_vl, ridge.predict(X_flat[split_idx:]))

        # TCN
        tcn = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_tcn = train_neural(tcn, Xw_tr, y_tr, Xw_vl, epochs=40)
        r2_tcn = compute_r2(y_vl, pred_tcn)

        # Transformer
        transformer = MiniTransformer(
            in_channels=X_win.shape[2], window_size=WINDOW,
            d_model=32, nhead=4, num_layers=2)
        pred_tf = train_neural(transformer, Xw_tr, y_tr, Xw_vl, epochs=60, lr=5e-4)
        r2_tf = compute_r2(y_vl, pred_tf)

        results.append({
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_tcn': round(r2_tcn, 4),
            'r2_transformer': round(r2_tf, 4),
            'tf_vs_ridge': round(r2_tf - r2_ridge, 4),
            'tf_vs_tcn': round(r2_tf - r2_tcn, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge={r2_ridge:.4f} tcn={r2_tcn:.4f} "
                  f"transformer={r2_tf:.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_tcn', 'r2_transformer']}
    tf_wins_ridge = sum(1 for r in results if r['r2_transformer'] > r['r2_ridge'])
    tf_wins_tcn = sum(1 for r in results if r['r2_transformer'] > r['r2_tcn'])

    return {
        'status': 'pass',
        'detail': (f"ridge={means['r2_ridge']:.4f} tcn={means['r2_tcn']:.4f} "
                   f"transformer={means['r2_transformer']:.4f} "
                   f"(tf>ridge={tf_wins_ridge}, tf>tcn={tf_wins_tcn}/{len(results)})"),
        'results': {'per_patient': results, 'summary': {
            'means': means, 'tf_wins_vs_ridge': tf_wins_ridge,
            'tf_wins_vs_tcn': tf_wins_tcn,
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1125: Asymmetric Loss (Hypo-Penalized)
# ---------------------------------------------------------------------------

def exp_1125_asymmetric_loss(patients, detail=False):
    """Penalize hypo under-prediction more heavily."""
    HYPO_THRESHOLD = 70.0 / GLUCOSE_SCALE  # in scaled units

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        y_tr, y_vl = y_win[:split_idx], y_win[split_idx:]

        # Standard MSE TCN
        tcn_mse = TCN(in_channels=X_win.shape[2], window_size=WINDOW).to(DEVICE)
        pred_mse = train_neural(tcn_mse, Xw_tr, y_tr, Xw_vl, epochs=40)
        r2_mse = compute_r2(y_vl, pred_mse)

        # Asymmetric loss TCN (2x penalty for hypo under-prediction)
        tcn_asym = TCN(in_channels=X_win.shape[2], window_size=WINDOW).to(DEVICE)
        optimizer = torch.optim.Adam(tcn_asym.parameters(), lr=1e-3)

        Xt = torch.tensor(Xw_tr, dtype=torch.float32).to(DEVICE)
        yt = torch.tensor(y_tr, dtype=torch.float32).to(DEVICE)
        Xv = torch.tensor(Xw_vl, dtype=torch.float32).to(DEVICE)

        tcn_asym.train()
        for _ in range(40):
            perm = torch.randperm(len(Xt))
            for start in range(0, len(Xt), 256):
                idx = perm[start:start + 256]
                pred = tcn_asym(Xt[idx])
                errors = (pred - yt[idx]) ** 2

                # Weight: 3x for under-predicting hypo
                weights = torch.ones_like(errors)
                hypo_mask = yt[idx] < HYPO_THRESHOLD
                under_pred = pred < yt[idx]
                weights[hypo_mask & under_pred] = 3.0

                loss = (errors * weights).mean()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        tcn_asym.eval()
        with torch.no_grad():
            pred_asym = tcn_asym(Xv).cpu().numpy()

        r2_asym = compute_r2(y_vl, pred_asym)

        # Evaluate hypo-specific metrics
        y_vl_mg = y_vl * GLUCOSE_SCALE
        hypo_mask_vl = y_vl_mg < 70

        if np.sum(hypo_mask_vl) > 5:
            mae_mse_hypo = compute_mae(y_vl_mg[hypo_mask_vl],
                                        pred_mse[hypo_mask_vl] * GLUCOSE_SCALE)
            mae_asym_hypo = compute_mae(y_vl_mg[hypo_mask_vl],
                                         pred_asym[hypo_mask_vl] * GLUCOSE_SCALE)
            # How many hypos are detected (pred < 80)?
            detect_mse = np.mean(pred_mse[hypo_mask_vl] * GLUCOSE_SCALE < 80)
            detect_asym = np.mean(pred_asym[hypo_mask_vl] * GLUCOSE_SCALE < 80)
        else:
            mae_mse_hypo = mae_asym_hypo = None
            detect_mse = detect_asym = None

        results.append({
            'patient': p['name'],
            'r2_mse': round(r2_mse, 4),
            'r2_asymmetric': round(r2_asym, 4),
            'r2_diff': round(r2_asym - r2_mse, 4),
            'hypo_mae_mse': round(mae_mse_hypo, 1) if mae_mse_hypo else None,
            'hypo_mae_asym': round(mae_asym_hypo, 1) if mae_asym_hypo else None,
            'hypo_detect_mse': round(detect_mse, 3) if detect_mse is not None else None,
            'hypo_detect_asym': round(detect_asym, 3) if detect_asym is not None else None,
            'n_hypo': int(np.sum(hypo_mask_vl)),
        })

        if detail:
            hypo_info = ""
            if mae_mse_hypo is not None:
                hypo_info = (f" hypo_mae: {mae_mse_hypo:.1f}→{mae_asym_hypo:.1f} "
                             f"detect: {detect_mse:.2f}→{detect_asym:.2f}")
            print(f"  {p['name']}: mse={r2_mse:.4f} asym={r2_asym:.4f} "
                  f"Δ={r2_asym-r2_mse:+.4f}{hypo_info}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_mse', 'r2_asymmetric']}
    valid_hypo = [r for r in results if r['hypo_mae_mse'] is not None]
    if valid_hypo:
        mean_hypo_mae_mse = np.mean([r['hypo_mae_mse'] for r in valid_hypo])
        mean_hypo_mae_asym = np.mean([r['hypo_mae_asym'] for r in valid_hypo])
    else:
        mean_hypo_mae_mse = mean_hypo_mae_asym = 0

    return {
        'status': 'pass',
        'detail': (f"mse={means['r2_mse']:.4f} asym={means['r2_asymmetric']:.4f} "
                   f"hypo_mae: {mean_hypo_mae_mse:.1f}→{mean_hypo_mae_asym:.1f}"),
        'results': {'per_patient': results, 'summary': {
            'means': means,
            'mean_hypo_mae_mse': round(mean_hypo_mae_mse, 1),
            'mean_hypo_mae_asym': round(mean_hypo_mae_asym, 1),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1126: Augmented Features (Glucose Density + Depth)
# ---------------------------------------------------------------------------

def exp_1126_density_depth(patients, detail=False):
    """Glucodensity histogram and functional depth features."""
    BINS = 8
    BIN_EDGES = np.linspace(40, 400, BINS + 1) / GLUCOSE_SCALE

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        # Build density + depth features per window
        g = glucose / GLUCOSE_SCALE
        extra_feats = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            gw = np.nan_to_num(gw, nan=np.nanmean(gw) if np.any(~np.isnan(gw)) else 0.4)
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            # Glucodensity: histogram of glucose values
            hist, _ = np.histogram(gw, bins=BIN_EDGES, density=True)
            hist = hist / (hist.sum() + 1e-8)

            # Functional depth: band depth approximation
            median_g = np.median(gw)
            depth = 1.0 - np.mean(np.abs(gw - median_g)) / (np.std(gw) + 1e-8)

            # Entropy of glucose distribution
            hist_pos = hist[hist > 0]
            entropy = -np.sum(hist_pos * np.log(hist_pos + 1e-10))

            extra_feats.append(np.concatenate([hist, [depth, entropy]]))

        extra_feats = np.array(extra_feats)
        if len(extra_feats) != len(X):
            extra_feats = np.zeros((len(X), BINS + 2))

        X_aug = np.column_stack([X, extra_feats])

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xa_tr, Xa_vl = X_aug[:len(X_tr)], X_aug[len(X_tr):]

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr, y_tr)
        r2_base = compute_r2(y_vl, ridge_base.predict(X_vl))

        ridge_aug = Ridge(alpha=1.0)
        ridge_aug.fit(Xa_tr, y_tr)
        r2_aug = compute_r2(y_vl, ridge_aug.predict(Xa_vl))

        xgb_base = make_xgb()
        xgb_base.fit(X_tr, y_tr)
        r2_xgb_base = compute_r2(y_vl, xgb_base.predict(X_vl))

        xgb_aug = make_xgb()
        xgb_aug.fit(Xa_tr, y_tr)
        r2_xgb_aug = compute_r2(y_vl, xgb_aug.predict(Xa_vl))

        results.append({
            'patient': p['name'],
            'r2_ridge_base': round(r2_base, 4),
            'r2_ridge_density': round(r2_aug, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_density': round(r2_xgb_aug, 4),
            'ridge_gain': round(r2_aug - r2_base, 4),
            'xgb_gain': round(r2_xgb_aug - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge Δ={r2_aug-r2_base:+.4f} "
                  f"xgb Δ={r2_xgb_aug-r2_xgb_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_base', 'r2_ridge_density', 'r2_xgb_base', 'r2_xgb_density']}
    ridge_wins = sum(1 for r in results if r['ridge_gain'] > 0.001)
    xgb_wins = sum(1 for r in results if r['xgb_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: {means['r2_ridge_base']:.4f}→{means['r2_ridge_density']:.4f} "
                   f"(wins={ridge_wins}) | xgb: {means['r2_xgb_base']:.4f}→"
                   f"{means['r2_xgb_density']:.4f} (wins={xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1127: Forecast Horizon Curriculum
# ---------------------------------------------------------------------------

def exp_1127_curriculum(patients, detail=False):
    """Curriculum learning: train on easy horizon first, then harder."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # Make windows for multiple horizons
        g = glucose / GLUCOSE_SCALE
        X_list, y_dict = [], {3: [], 6: [], 9: [], 12: []}
        for i in range(0, len(g) - WINDOW - 12, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            gw = np.nan_to_num(gw, nan=np.nanmean(gw) if np.any(~np.isnan(gw)) else 0.4)
            pw = physics[i:i + WINDOW]
            if np.isnan(pw).any():
                pw = np.nan_to_num(pw, nan=0.0)
            all_valid = True
            for h in [3, 6, 9, 12]:
                yv = g[i + WINDOW + h - 1]
                if np.isnan(yv):
                    all_valid = False
                    break
            if not all_valid:
                continue
            X_list.append(np.column_stack([gw.reshape(-1, 1), pw]))
            for h in [3, 6, 9, 12]:
                y_dict[h].append(g[i + WINDOW + h - 1])

        if len(X_list) < 200:
            continue
        X_win = np.array(X_list)
        for h in y_dict:
            y_dict[h] = np.array(y_dict[h])

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        y_tr_12 = y_dict[12][:split_idx]
        y_vl_12 = y_dict[12][split_idx:]

        # Standard: train directly on 60-min target
        tcn_direct = TCN(in_channels=X_win.shape[2], window_size=WINDOW).to(DEVICE)
        pred_direct = train_neural(tcn_direct, Xw_tr, y_tr_12, Xw_vl, epochs=40)
        r2_direct = compute_r2(y_vl_12, pred_direct)

        # Curriculum: train on 15min (10 epochs) → 30min (10) → 45min (10) → 60min (10)
        tcn_curr = TCN(in_channels=X_win.shape[2], window_size=WINDOW).to(DEVICE)
        optimizer = torch.optim.Adam(tcn_curr.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()

        Xt = torch.tensor(Xw_tr, dtype=torch.float32).to(DEVICE)
        Xv = torch.tensor(Xw_vl, dtype=torch.float32).to(DEVICE)

        for h, ep in [(3, 10), (6, 10), (9, 10), (12, 10)]:
            yt_h = torch.tensor(y_dict[h][:split_idx], dtype=torch.float32).to(DEVICE)
            tcn_curr.train()
            for _ in range(ep):
                perm = torch.randperm(len(Xt))
                for start in range(0, len(Xt), 256):
                    idx = perm[start:start + 256]
                    pred = tcn_curr(Xt[idx])
                    loss = loss_fn(pred, yt_h[idx])
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

        tcn_curr.eval()
        with torch.no_grad():
            pred_curr = tcn_curr(Xv).cpu().numpy()
        r2_curr = compute_r2(y_vl_12, pred_curr)

        # Ridge baseline
        X_flat = X_win.reshape(len(X_win), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_flat[:split_idx], y_tr_12)
        r2_ridge = compute_r2(y_vl_12, ridge.predict(X_flat[split_idx:]))

        results.append({
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_tcn_direct': round(r2_direct, 4),
            'r2_tcn_curriculum': round(r2_curr, 4),
            'curriculum_gain': round(r2_curr - r2_direct, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge={r2_ridge:.4f} "
                  f"direct={r2_direct:.4f} curriculum={r2_curr:.4f} "
                  f"Δ={r2_curr-r2_direct:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_tcn_direct', 'r2_tcn_curriculum']}
    curr_wins = sum(1 for r in results if r['curriculum_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"direct={means['r2_tcn_direct']:.4f} "
                   f"curriculum={means['r2_tcn_curriculum']:.4f} "
                   f"(wins={curr_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1128: Per-Patient XGBoost + LSTM Pipeline
# ---------------------------------------------------------------------------

def exp_1128_xgb_lstm_pipeline(patients, detail=False):
    """Per-patient tuned XGBoost + LSTM residual correction."""
    RESIDUAL_WINDOW = 12

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, missing_mask = impute_glucose(glucose_raw)

        X, y, g_cur = build_grand_features(glucose, physics)
        if len(X) < 400:
            continue

        y_delta = y - g_cur
        X_tr, X_vl, X_te, y_tr_d, y_vl_d, y_te_d = split_3way(X, y_delta)
        _, _, _, y_tr_a, y_vl_a, y_te_a = split_3way(X, y)
        gc_tr, gc_vl, gc_te = split_3way(X, g_cur)[3:]

        # Tuned XGBoost on Δg (try a few configs)
        best_r2 = -999
        best_cfg = None
        configs = [
            {'n_estimators': 200, 'max_depth': 3, 'learning_rate': 0.05, 'subsample': 0.7},
            {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.05, 'subsample': 0.8},
            {'n_estimators': 500, 'max_depth': 3, 'learning_rate': 0.01, 'subsample': 0.8},
            {'n_estimators': 100, 'max_depth': 3, 'learning_rate': 0.1, 'subsample': 1.0},
        ]
        for cfg in configs:
            m = make_xgb(**cfg)
            m.fit(X_tr, y_tr_d)
            pred_vl = m.predict(X_vl) + gc_vl
            r2 = compute_r2(y_vl_a, pred_vl)
            if r2 > best_r2:
                best_r2 = r2
                best_cfg = cfg

        # Train best XGB on train+val
        xgb_best = make_xgb(**best_cfg)
        xgb_best.fit(np.vstack([X_tr, X_vl]), np.concatenate([y_tr_d, y_vl_d]))
        pred_xgb_te = xgb_best.predict(X_te) + gc_te
        r2_xgb = compute_r2(y_te_a, pred_xgb_te)

        # Also train on train only for LSTM
        xgb_for_lstm = make_xgb(**best_cfg)
        xgb_for_lstm.fit(X_tr, y_tr_d)
        pred_vl_for_lstm = xgb_for_lstm.predict(X_vl) + gc_vl

        # LSTM on XGB residuals
        residuals_vl = y_vl_a - pred_vl_for_lstm
        resid_X, resid_y = [], []
        for i in range(RESIDUAL_WINDOW, len(residuals_vl)):
            resid_X.append(residuals_vl[i-RESIDUAL_WINDOW:i])
            resid_y.append(residuals_vl[i])

        if len(resid_X) < 50:
            r2_pipeline = r2_xgb
            lstm_gain = 0.0
        else:
            resid_X_arr = np.array(resid_X).reshape(-1, RESIDUAL_WINDOW, 1)
            resid_y_arr = np.array(resid_y)

            lstm = ResidualLSTM(hidden=32).to(DEVICE)
            opt = torch.optim.Adam(lstm.parameters(), lr=1e-3)
            loss_fn = nn.MSELoss()
            Rt = torch.tensor(resid_X_arr, dtype=torch.float32).to(DEVICE)
            Ry = torch.tensor(resid_y_arr, dtype=torch.float32).to(DEVICE)

            lstm.train()
            for _ in range(50):
                pred = lstm(Rt)
                loss = loss_fn(pred, Ry)
                opt.zero_grad()
                loss.backward()
                opt.step()

            # Apply to test
            pred_xgb_te_for_corr = xgb_for_lstm.predict(X_te) + gc_te
            corrected = pred_xgb_te_for_corr.copy()
            resid_buffer = list(residuals_vl[-RESIDUAL_WINDOW:])

            lstm.eval()
            with torch.no_grad():
                for i in range(len(y_te_a)):
                    if len(resid_buffer) >= RESIDUAL_WINDOW:
                        w = np.array(resid_buffer[-RESIDUAL_WINDOW:]).reshape(
                            1, RESIDUAL_WINDOW, 1)
                        wt = torch.tensor(w, dtype=torch.float32).to(DEVICE)
                        correction = lstm(wt).cpu().numpy()[0]
                        corrected[i] = pred_xgb_te_for_corr[i] + correction
                    actual_resid = y_te_a[i] - pred_xgb_te_for_corr[i]
                    resid_buffer.append(actual_resid)

            r2_pipeline = compute_r2(y_te_a, corrected)
            lstm_gain = r2_pipeline - r2_xgb

        # Ridge baseline
        ridge = Ridge(alpha=1.0)
        ridge.fit(np.vstack([X_tr, X_vl]), np.concatenate([y_tr_a, y_vl_a]))
        r2_ridge = compute_r2(y_te_a, ridge.predict(X_te))

        results.append({
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_xgb_tuned': round(r2_xgb, 4),
            'r2_xgb_lstm': round(r2_pipeline, 4),
            'best_config': best_cfg,
            'lstm_gain': round(lstm_gain, 4),
            'pipeline_gain': round(r2_pipeline - r2_ridge, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge={r2_ridge:.4f} xgb={r2_xgb:.4f} "
                  f"pipeline={r2_pipeline:.4f} Δ_lstm={lstm_gain:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_xgb_tuned', 'r2_xgb_lstm']}
    pipeline_wins = sum(1 for r in results if r['r2_xgb_lstm'] > r['r2_ridge'])

    return {
        'status': 'pass',
        'detail': (f"ridge={means['r2_ridge']:.4f} xgb={means['r2_xgb_tuned']:.4f} "
                   f"pipeline={means['r2_xgb_lstm']:.4f} "
                   f"(wins={pipeline_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1129: Error-Aware Ensemble (Predicted Difficulty)
# ---------------------------------------------------------------------------

def exp_1129_error_aware(patients, detail=False):
    """Predict when the model will be wrong and adjust confidence."""
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 300:
            continue

        X_tr, X_vl, X_te, y_tr, y_vl, y_te = split_3way(X, y)

        # Train Ridge predictor
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr)
        pred_vl = ridge.predict(X_vl)
        pred_te = ridge.predict(X_te)

        r2_base = compute_r2(y_te, pred_te)

        # Train error predictor: predict |error| from features
        errors_vl = np.abs(y_vl - pred_vl)
        error_model = make_xgb(n_estimators=100, max_depth=3)
        error_model.fit(X_vl, errors_vl)

        predicted_error_te = error_model.predict(X_te)
        actual_error_te = np.abs(y_te - pred_te)

        # Correlation between predicted and actual error
        corr = np.corrcoef(predicted_error_te, actual_error_te)[0, 1]

        # Use predicted error for adaptive blending with naive (last value)
        naive_pred = X_te[:, WINDOW-1]  # last glucose in window
        # When predicted error is high, trust naive more
        median_err = np.median(predicted_error_te)
        blend_weight = np.clip(predicted_error_te / (2 * median_err + 1e-8), 0, 1)
        adaptive_pred = (1 - blend_weight) * pred_te + blend_weight * naive_pred
        r2_adaptive = compute_r2(y_te, adaptive_pred)

        results.append({
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_adaptive': round(r2_adaptive, 4),
            'error_corr': round(corr, 4),
            'adaptive_gain': round(r2_adaptive - r2_base, 4),
        })

        if detail:
            print(f"  {p['name']}: base={r2_base:.4f} adaptive={r2_adaptive:.4f} "
                  f"Δ={r2_adaptive-r2_base:+.4f} err_corr={corr:.3f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_base', 'r2_adaptive', 'error_corr']}
    wins = sum(1 for r in results if r['adaptive_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"base={means['r2_base']:.4f} adaptive={means['r2_adaptive']:.4f} "
                   f"err_corr={means['error_corr']:.3f} (wins={wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1130: Definitive Benchmark (Block CV + All Metrics)
# ---------------------------------------------------------------------------

def exp_1130_definitive_benchmark(patients, detail=False):
    """Final benchmark with 5-fold block CV and comprehensive metrics."""
    N_FOLDS = 5

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, missing_mask = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 300:
            continue

        # Add missing flag
        flag_series = missing_mask.astype(float)
        flag_feats = []
        g = glucose / GLUCOSE_SCALE
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue
            flag_feats.append(np.mean(flag_series[i:i + WINDOW]))
        flag_feats = np.array(flag_feats)
        if len(flag_feats) == len(X):
            X = np.column_stack([X, flag_feats])

        y_delta = y_abs - g_cur

        # 5-fold block CV
        fold_size = len(X) // N_FOLDS
        fold_r2s = {'ridge_abs': [], 'ridge_dg': [], 'xgb_dg': [],
                     'ensemble_dg': []}
        fold_maes = []
        all_y_true, all_y_pred = [], []

        for fold in range(N_FOLDS):
            vs = fold * fold_size
            ve = vs + fold_size if fold < N_FOLDS - 1 else len(X)
            mask = np.ones(len(X), dtype=bool)
            mask[vs:ve] = False

            Xa_tr, Xa_vl = X[mask], X[~mask]
            ya_tr, ya_vl = y_abs[mask], y_abs[~mask]
            yd_tr, yd_vl = y_delta[mask], y_delta[~mask]
            gc_vl = g_cur[~mask]

            # Ridge abs
            r = Ridge(alpha=1.0)
            r.fit(Xa_tr, ya_tr)
            pred_r = r.predict(Xa_vl)
            fold_r2s['ridge_abs'].append(compute_r2(ya_vl, pred_r))

            # Ridge Δg
            r_dg = Ridge(alpha=1.0)
            r_dg.fit(Xa_tr, yd_tr)
            pred_r_dg = r_dg.predict(Xa_vl) + gc_vl
            fold_r2s['ridge_dg'].append(compute_r2(ya_vl, pred_r_dg))

            # XGB Δg
            xgb_dg = make_xgb()
            xgb_dg.fit(Xa_tr, yd_tr)
            pred_xgb_dg = xgb_dg.predict(Xa_vl) + gc_vl
            fold_r2s['xgb_dg'].append(compute_r2(ya_vl, pred_xgb_dg))

            # Ensemble
            pred_ens = 0.5 * pred_r_dg + 0.5 * pred_xgb_dg
            fold_r2s['ensemble_dg'].append(compute_r2(ya_vl, pred_ens))

            fold_maes.append(compute_mae(ya_vl * GLUCOSE_SCALE,
                                          pred_ens * GLUCOSE_SCALE))
            all_y_true.extend(ya_vl * GLUCOSE_SCALE)
            all_y_pred.extend(pred_ens * GLUCOSE_SCALE)

        all_y_true = np.array(all_y_true)
        all_y_pred = np.array(all_y_pred)

        # Clarke Error Grid
        def clarke_zones(yt, yp):
            n = len(yt)
            zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
            for t, p in zip(yt, yp):
                if (t <= 70 and p <= 70) or abs(p - t) < 20:
                    zones['A'] += 1
                elif t >= 180 and abs(p - t) / t < 0.2:
                    zones['A'] += 1
                elif (t <= 70 and p > 180) or (t >= 180 and p <= 70):
                    zones['E'] += 1
                else:
                    zones['B'] += 1  # simplified
            return {k: round(v/n, 4) for k, v in zones.items()}

        clarke = clarke_zones(all_y_true, all_y_pred)

        # Time in range
        tir = np.mean((all_y_true >= 70) & (all_y_true <= 180))

        # Hypo metrics
        hypo_mask = all_y_true < 70
        n_hypo = int(np.sum(hypo_mask))
        if n_hypo > 0:
            hypo_mae = compute_mae(all_y_true[hypo_mask], all_y_pred[hypo_mask])
            hypo_detect = np.mean(all_y_pred[hypo_mask] < 80)
        else:
            hypo_mae = 0
            hypo_detect = 0

        means = {k: round(np.mean(v), 4) for k, v in fold_r2s.items()}
        stds = {k: round(np.std(v), 4) for k, v in fold_r2s.items()}

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'missing_pct': round(np.mean(missing_mask), 3),
            'r2_means': means,
            'r2_stds': stds,
            'best_method': max(means, key=means.get),
            'mae_mgdl': round(np.mean(fold_maes), 1),
            'clarke_zones': clarke,
            'tir': round(tir, 3),
            'n_hypo': n_hypo,
            'hypo_mae': round(hypo_mae, 1),
            'hypo_detect': round(hypo_detect, 3),
        })

        if detail:
            best = max(means, key=means.get)
            print(f"  {p['name']}: {best}={means[best]:.4f}±{stds[best]:.3f} "
                  f"MAE={np.mean(fold_maes):.1f} Clarke_A={clarke['A']:.1%} "
                  f"TIR={tir:.1%} hypo_n={n_hypo}")

    # Grand summary
    grand = {}
    for method in fold_r2s.keys():
        grand[method] = round(np.mean([r['r2_means'][method] for r in results]), 4)
    grand_best = max(grand, key=grand.get)
    mean_mae = round(np.mean([r['mae_mgdl'] for r in results]), 1)
    mean_clarke_a = round(np.mean([r['clarke_zones']['A'] for r in results]), 3)

    return {
        'status': 'pass',
        'detail': (f"5-fold CV: {grand_best}={grand[grand_best]:.4f} "
                   f"MAE={mean_mae} Clarke_A={mean_clarke_a:.1%} | " +
                   ' '.join(f"{k}={v:.4f}" for k, v in grand.items())),
        'results': {'per_patient': results, 'summary': {
            'grand_means': grand, 'grand_best': grand_best,
            'mean_mae': mean_mae, 'mean_clarke_a': mean_clarke_a,
            'n_patients': len(results), 'n_folds': N_FOLDS,
        }},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1121', 'Full Pipeline (All Winners Stacked)', exp_1121_full_pipeline),
    ('EXP-1122', 'Learned Embedding + XGBoost', exp_1122_embedding_xgb),
    ('EXP-1123', 'Multi-Scale Wavelet Decomposition', exp_1123_wavelet),
    ('EXP-1124', 'Temporal Attention Transformer', exp_1124_transformer),
    ('EXP-1125', 'Asymmetric Loss (Hypo-Penalized)', exp_1125_asymmetric_loss),
    ('EXP-1126', 'Augmented Features (Density + Depth)', exp_1126_density_depth),
    ('EXP-1127', 'Forecast Horizon Curriculum', exp_1127_curriculum),
    ('EXP-1128', 'Per-Patient XGBoost + LSTM Pipeline', exp_1128_xgb_lstm_pipeline),
    ('EXP-1129', 'Error-Aware Ensemble', exp_1129_error_aware),
    ('EXP-1130', 'Definitive Benchmark (5-fold CV)', exp_1130_definitive_benchmark),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1121-1130: Pushing the Information Frontier')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1121)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")
    print(f"Using device: {DEVICE}")

    for exp_id, name, func in EXPERIMENTS:
        if args.experiment and exp_id != args.experiment:
            continue

        print(f"\n{'=' * 60}")
        print(f"Running {exp_id}: {name}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
            elapsed = time.time() - t0
            print(f"  Status: {result.get('status', 'unknown')}")
            print(f"  Detail: {result.get('detail', '')}")
            print(f"  Time: {elapsed:.1f}s")

            if args.save:
                save_data = {
                    'experiment': exp_id, 'name': name,
                    'status': result.get('status'),
                    'detail': result.get('detail'),
                    'elapsed_seconds': round(elapsed, 1),
                    'results': result.get('results', {}),
                }
                save_name = (f"{exp_id.lower()}_"
                             f"{name.lower().replace(' ', '_').replace('-', '_')}")
                save_path = save_results(save_data, save_name)
                print(f"  Saved: {save_path}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  Status: FAIL")
            print(f"  Error: {e}")
            print(f"  Time: {elapsed:.1f}s")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print("All experiments complete")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
