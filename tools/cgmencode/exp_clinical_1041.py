#!/usr/bin/env python3
"""EXP-1041 to EXP-1050: Hepatic Deep Dive, Clinical Metrics & Attention Architectures.

Building on EXP-1031-1040's highest-leverage findings:
- Hepatic production is #1 physics channel (EXP-1038: importance +0.024)
- Residual CNN is universally reliable (EXP-1024: +0.024, 11/11 positive)
- Block CV R²=0.505 is honest SOTA (EXP-1040)
- Patient h has 64% missing data (EXP-1033) — needs special handling
- Time-of-day conditioning hurts (EXP-1027: -0.064)

This batch focuses on:
1. Hepatic production deep dive (dawn phenomenon, hourly profiles)
2. Attention mechanism over physics channels
3. Clarke Error Grid clinical analysis
4. Selective prediction with reject option (ensemble confidence)
5. Hypo/hyper alert binary classification
6. Longer context windows (4h, 6h, 12h)
7. Gap-aware architecture for patient h
8. Residual structure analysis (what the CNN learns)
9. Feature interaction terms for Ridge
10. Grand benchmark with exclusion criteria

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1041 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import (r2_score, mean_absolute_error,
                             precision_score, recall_score, f1_score,
                             roc_auc_score)

warnings.filterwarnings('ignore')

try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ─── Models ───

class ResidualCNN(nn.Module):
    """CNN that learns to predict Ridge residuals."""
    def __init__(self, in_channels, seq_len=24):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        feat = self.conv(x.permute(0, 2, 1)).squeeze(-1)
        return self.head(feat).squeeze(-1)


class AttentionPhysicsCNN(nn.Module):
    """CNN with learned attention over physics channels."""
    def __init__(self, n_physics=4, seq_len=24):
        super().__init__()
        # Attention weights over physics channels
        self.attn_fc = nn.Linear(n_physics, n_physics)
        # Glucose branch
        self.glucose_conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=5, padding=2), nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=5, padding=2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        # Physics branch (attention-weighted single channel)
        self.physics_conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=5, padding=2), nn.ReLU(),
            nn.Conv1d(32, 32, kernel_size=5, padding=2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(96, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, glucose, physics):
        """glucose: (B, seq_len), physics: (B, seq_len, 4)"""
        # Compute attention over physics channels
        phys_mean = physics.mean(dim=1)  # (B, 4)
        attn_logits = self.attn_fc(phys_mean)  # (B, 4)
        attn_weights = torch.softmax(attn_logits, dim=1)  # (B, 4)
        # Weighted sum of physics channels: (B, seq_len)
        weighted_phys = (physics * attn_weights.unsqueeze(1)).sum(dim=2)

        g_feat = self.glucose_conv(glucose.unsqueeze(1)).squeeze(-1)  # (B, 64)
        p_feat = self.physics_conv(weighted_phys.unsqueeze(1)).squeeze(-1)  # (B, 32)
        return self.head(torch.cat([g_feat, p_feat], dim=1)).squeeze(-1), attn_weights


# ─── Data Helpers ───

def build_windowed_data(df, pk_array, supply_demand, history_steps=WINDOW,
                        horizon_steps=HORIZON, stride=STRIDE):
    """Build sliding windows with glucose + physics decomposition."""
    glucose = df['glucose'].values / GLUCOSE_SCALE
    N = len(glucose)
    total = history_steps + horizon_steps

    supply = supply_demand['supply'] / 20.0
    demand = supply_demand['demand'] / 20.0
    hepatic = supply_demand['hepatic'] / 5.0
    net = supply_demand['net'] / 20.0

    g_wins, pk_wins, phys_wins, tgts = [], [], [], []

    for i in range(0, N - total, stride):
        g = glucose[i:i+history_steps]
        if np.isnan(g).mean() > 0.2:
            continue
        target = glucose[i+history_steps+horizon_steps-1]
        if np.isnan(target):
            continue
        g = np.nan_to_num(g, nan=np.nanmean(g) if np.any(~np.isnan(g)) else 0.4)
        g_wins.append(g.reshape(-1, 1))
        pk_wins.append(pk_array[i:i+history_steps])
        phys = np.stack([supply[i:i+history_steps], demand[i:i+history_steps],
                         hepatic[i:i+history_steps], net[i:i+history_steps]], axis=1)
        phys_wins.append(phys)
        tgts.append(target)

    return np.array(g_wins), np.array(pk_wins), np.array(phys_wins), np.array(tgts)


def build_windowed_data_flexible(df, pk_array, supply_demand, history_steps=WINDOW,
                                 horizon_steps=HORIZON, stride=STRIDE,
                                 nan_threshold=0.2):
    """Like build_windowed_data but with configurable NaN tolerance."""
    glucose = df['glucose'].values / GLUCOSE_SCALE
    N = len(glucose)
    total = history_steps + horizon_steps

    supply = supply_demand['supply'] / 20.0
    demand = supply_demand['demand'] / 20.0
    hepatic = supply_demand['hepatic'] / 5.0
    net = supply_demand['net'] / 20.0

    g_wins, phys_wins, tgts, masks = [], [], [], []

    for i in range(0, N - total, stride):
        g = glucose[i:i+history_steps]
        nan_frac = np.isnan(g).mean()
        if nan_frac > nan_threshold:
            continue
        target = glucose[i+history_steps+horizon_steps-1]
        if np.isnan(target):
            continue
        mask = (~np.isnan(g)).astype(np.float32)
        g = np.nan_to_num(g, nan=np.nanmean(g) if np.any(~np.isnan(g)) else 0.4)
        g_wins.append(g.reshape(-1, 1))
        phys = np.stack([supply[i:i+history_steps], demand[i:i+history_steps],
                         hepatic[i:i+history_steps], net[i:i+history_steps]], axis=1)
        phys_wins.append(phys)
        tgts.append(target)
        masks.append(mask.reshape(-1, 1))

    if not g_wins:
        return np.array([]), np.array([]), np.array([]), np.array([])
    return np.array(g_wins), np.array(phys_wins), np.array(tgts), np.array(masks)


def split_chrono(arrays, frac=0.8):
    n = len(arrays[0])
    s = int(frac * n)
    return [a[:s] for a in arrays], [a[s:] for a in arrays]


def train_cnn(model, train_data, val_data, epochs=60, batch_size=256,
              patience=12, lr=1e-3):
    """Train CNN and return (model, R²) on validation set."""
    train_t = [torch.from_numpy(a).float() for a in train_data]
    val_t = [torch.from_numpy(a).float().to(DEVICE) for a in val_data]

    ds = TensorDataset(*train_t)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(DEVICE.type == 'cuda'))

    model = model.to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    best_loss = float('inf')
    best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    wait = 0

    for epoch in range(epochs):
        model.train()
        for batch in dl:
            batch = [b.to(DEVICE) for b in batch]
            x, y = batch[0], batch[-1]
            pred = model(x)
            loss = criterion(pred, y)
            if not np.isfinite(loss.item()):
                continue
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(val_t[0])
            val_loss = criterion(val_pred, val_t[-1]).item()

        if np.isnan(val_loss):
            continue

        scheduler.step(val_loss)
        if val_loss < best_loss:
            best_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred = model(val_t[0])
        pred_np = pred.cpu().numpy()
        y_np = val_t[-1].cpu().numpy()

    return model, r2_score(y_np, pred_np)


def predict_cnn(model, X):
    """Get numpy predictions from a trained CNN."""
    model.eval()
    with torch.no_grad():
        pred = model(torch.from_numpy(X).float().to(DEVICE))
        return pred.cpu().numpy()


# ─── Clarke Error Grid ───

def clarke_zone(ref_mgdl, pred_mgdl):
    """Classify a (reference, prediction) pair into Clarke Error Grid zone A-E.

    Both values should be in mg/dL.
    Returns one of: 'A', 'B', 'C', 'D', 'E'.
    """
    ref, pred = float(ref_mgdl), float(pred_mgdl)

    # Zone D: dangerous failure to detect
    if ref < 70 and pred > 180:
        return 'D'
    if ref > 240 and pred < 70:
        return 'D'

    # Zone E: gross misclassification (opposite extremes)
    if ref >= 180 and pred <= 70:
        return 'E'
    if ref <= 70 and pred >= 180:
        return 'E'

    # Zone A: clinically accurate
    if ref < 70:
        if abs(pred - ref) <= 20:
            return 'A'
    else:
        if abs(pred - ref) / ref <= 0.20:
            return 'A'

    # Zone C: overcorrection errors
    if ref >= 70 and ref <= 180:
        if pred > ref + 110:
            return 'C'
    if ref >= 130 and ref <= 180:
        if pred < (7.0 / 5.0) * ref - 182:
            return 'C'

    # Remaining cases: Zone B (benign errors)
    return 'B'


def compute_clarke_zones(refs_mgdl, preds_mgdl):
    """Compute zone distribution for arrays of references and predictions."""
    zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    for r, p in zip(refs_mgdl, preds_mgdl):
        z = clarke_zone(r, p)
        zones[z] += 1
    total = sum(zones.values())
    pcts = {z: round(100.0 * c / max(total, 1), 1) for z, c in zones.items()}
    return zones, pcts


# ─── Experiments ───

def exp_1041_hepatic_deep_dive(patients, detail=False):
    """Hepatic production deep dive: hourly profiles, dawn phenomenon, feature impact."""
    results = []
    STEPS_PER_HOUR = 12  # 60 min / 5 min

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        hepatic = sd['hepatic']
        glucose_raw = p['df']['glucose'].values

        # Compute hour-of-day for each sample (assume 5-min intervals from midnight)
        n = len(hepatic)
        hours = np.array([(i * 5 // 60) % 24 for i in range(n)])

        # (a) Hour-of-day hepatic profile
        hourly_hepatic = {}
        for h in range(24):
            mask = hours == h
            vals = hepatic[mask]
            valid = vals[~np.isnan(vals)]
            hourly_hepatic[h] = float(np.mean(valid)) if len(valid) > 0 else 0.0

        mean_hepatic = float(np.nanmean(hepatic))

        # (b) Dawn phenomenon: amplitude = max(hepatic[4am-8am]) - mean(hepatic)
        dawn_hours = [4, 5, 6, 7]
        dawn_vals = [hourly_hepatic[h] for h in dawn_hours]
        dawn_amplitude = max(dawn_vals) - mean_hepatic

        # (c) Build features and test Ridge with dawn_amplitude
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)

        # Baseline Ridge
        train, val = split_chrono([combined, tgt])
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(tr_flat, train[1])
        r2_base = r2_score(val[1], ridge_base.predict(vl_flat))

        # Ridge + dawn_amplitude feature
        dawn_feat = np.full((len(g), 1), dawn_amplitude)
        tr_dawn, vl_dawn = split_chrono([dawn_feat])
        tr_flat_dawn = np.concatenate([tr_flat, tr_dawn[0]], axis=1)
        vl_flat_dawn = np.concatenate([vl_flat, vl_dawn[0]], axis=1)
        ridge_dawn = Ridge(alpha=1.0)
        ridge_dawn.fit(tr_flat_dawn, train[1])
        r2_dawn = r2_score(val[1], ridge_dawn.predict(vl_flat_dawn))

        # Ridge + full 24-point hourly hepatic profile
        profile_feat = np.array([list(hourly_hepatic.values())] * len(g))
        tr_prof, vl_prof = split_chrono([profile_feat])
        tr_flat_prof = np.concatenate([tr_flat, tr_prof[0]], axis=1)
        vl_flat_prof = np.concatenate([vl_flat, vl_prof[0]], axis=1)
        ridge_prof = Ridge(alpha=1.0)
        ridge_prof.fit(tr_flat_prof, train[1])
        r2_profile = r2_score(val[1], ridge_prof.predict(vl_flat_prof))

        # (d) Compare hepatic importance: dawn (4-8am) vs rest-of-day
        # Permutation importance on dawn vs non-dawn windows
        # Identify which validation windows fall in dawn hours
        val_start_idx = int(len(g) * 0.8)
        val_hours = hours_for_windows(val_start_idx, len(val[0]), WINDOW, STRIDE, n)

        dawn_mask = np.array([h in dawn_hours for h in val_hours])
        rest_mask = ~dawn_mask

        # Permutation importance of hepatic channel (index 3 in phys = index 3+1=4 in combined)
        rng = np.random.RandomState(42)
        hepatic_ch_idx = 3  # supply=1, demand=2, hepatic=3, net=4 in combined (0=glucose)

        imp_dawn, imp_rest = np.nan, np.nan
        if dawn_mask.sum() > 10:
            val_shuf = val[0].copy()
            perm = rng.permutation(len(val_shuf))
            val_shuf[:, :, hepatic_ch_idx] = val_shuf[perm, :, hepatic_ch_idx]
            vl_flat_shuf = val_shuf.reshape(len(val_shuf), -1)
            pred_shuf = ridge_base.predict(vl_flat_shuf)
            pred_orig = ridge_base.predict(vl_flat)

            if dawn_mask.sum() > 1:
                r2_orig_dawn = r2_score(val[1][dawn_mask], pred_orig[dawn_mask])
                r2_shuf_dawn = r2_score(val[1][dawn_mask], pred_shuf[dawn_mask])
                imp_dawn = r2_orig_dawn - r2_shuf_dawn

            if rest_mask.sum() > 1:
                r2_orig_rest = r2_score(val[1][rest_mask], pred_orig[rest_mask])
                r2_shuf_rest = r2_score(val[1][rest_mask], pred_shuf[rest_mask])
                imp_rest = r2_orig_rest - r2_shuf_rest

        res = {
            'patient': p['name'],
            'mean_hepatic': round(mean_hepatic, 4),
            'dawn_amplitude': round(dawn_amplitude, 4),
            'r2_base': round(r2_base, 4),
            'r2_plus_dawn': round(r2_dawn, 4),
            'r2_plus_profile': round(r2_profile, 4),
            'dawn_gain': round(r2_dawn - r2_base, 4),
            'profile_gain': round(r2_profile - r2_base, 4),
            'hepatic_importance_dawn': round(imp_dawn, 4) if np.isfinite(imp_dawn) else None,
            'hepatic_importance_rest': round(imp_rest, 4) if np.isfinite(imp_rest) else None,
            'hourly_hepatic': {str(h): round(v, 4) for h, v in hourly_hepatic.items()},
        }
        results.append(res)
        if detail:
            id_str = f"{imp_dawn:.4f}" if np.isfinite(imp_dawn) else "N/A"
            ir_str = f"{imp_rest:.4f}" if np.isfinite(imp_rest) else "N/A"
            print(f"    {p['name']}: dawn_amp={dawn_amplitude:.4f} "
                  f"base={r2_base:.4f} +dawn={r2_dawn:.4f}({r2_dawn-r2_base:+.4f}) "
                  f"+profile={r2_profile:.4f}({r2_profile-r2_base:+.4f}) "
                  f"imp_dawn={id_str} imp_rest={ir_str}")

    dawn_gains = [r['dawn_gain'] for r in results]
    prof_gains = [r['profile_gain'] for r in results]
    return {
        'status': 'pass',
        'detail': (f'dawn_gain={np.mean(dawn_gains):+.4f}, '
                   f'profile_gain={np.mean(prof_gains):+.4f}, '
                   f'n={len(results)}'),
        'results': {'per_patient': results},
    }


def hours_for_windows(start_idx, n_windows, window_size, stride, total_len):
    """Compute approximate hour-of-day for the center of each validation window."""
    hours = []
    for w in range(n_windows):
        center = (start_idx * stride + w * stride + window_size // 2) * 5  # minutes
        h = (center // 60) % 24
        hours.append(h)
    return hours


def exp_1042_attention_over_physics(patients, detail=False):
    """Attention-weighted physics channels vs equal weighting."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        glucose_1d = g[:, :, 0]  # (N, 24)
        train_idx = int(len(g) * 0.8)

        g_tr, g_val = glucose_1d[:train_idx], glucose_1d[train_idx:]
        p_tr, p_val = phys[:train_idx], phys[train_idx:]
        y_tr, y_val = tgt[:train_idx], tgt[train_idx:]

        # (a) Train attention model
        model_attn = AttentionPhysicsCNN(n_physics=4, seq_len=WINDOW).to(DEVICE)
        optimizer = torch.optim.Adam(model_attn.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.MSELoss()
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

        g_tr_t = torch.from_numpy(g_tr).float()
        p_tr_t = torch.from_numpy(p_tr).float()
        y_tr_t = torch.from_numpy(y_tr).float()
        g_val_t = torch.from_numpy(g_val).float().to(DEVICE)
        p_val_t = torch.from_numpy(p_val).float().to(DEVICE)
        y_val_t = torch.from_numpy(y_val).float().to(DEVICE)

        ds = TensorDataset(g_tr_t, p_tr_t, y_tr_t)
        dl = DataLoader(ds, batch_size=256, shuffle=True)

        best_loss = float('inf')
        best_state = {k: v.cpu().clone() for k, v in model_attn.state_dict().items()}
        wait = 0

        for epoch in range(50):
            model_attn.train()
            for bg, bp, by in dl:
                bg, bp, by = bg.to(DEVICE), bp.to(DEVICE), by.to(DEVICE)
                pred, _ = model_attn(bg, bp)
                loss = criterion(pred, by)
                if not np.isfinite(loss.item()):
                    continue
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model_attn.eval()
            with torch.no_grad():
                val_pred, val_attn = model_attn(g_val_t, p_val_t)
                val_loss = criterion(val_pred, y_val_t).item()

            if np.isnan(val_loss):
                continue

            scheduler.step(val_loss)
            if val_loss < best_loss:
                best_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in model_attn.state_dict().items()}
                wait = 0
            else:
                wait += 1
                if wait >= 12:
                    break

        model_attn.load_state_dict(best_state)
        model_attn.eval()
        with torch.no_grad():
            pred_attn, attn_weights = model_attn(g_val_t, p_val_t)
            r2_attn = r2_score(y_val_t.cpu().numpy(), pred_attn.cpu().numpy())
            mean_attn = attn_weights.mean(dim=0).cpu().numpy()

        # (b) Equal-weight baseline: average physics channels, same architecture shape
        # Use Ridge as comparable simple baseline
        combined = np.concatenate([g, phys], axis=2)
        train_c, val_c = split_chrono([combined, tgt])
        tr_flat = train_c[0].reshape(len(train_c[0]), -1)
        vl_flat = val_c[0].reshape(len(val_c[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train_c[1])
        r2_ridge = r2_score(val_c[1], ridge.predict(vl_flat))

        # (c) Unweighted CNN (equal physics channel weighting) via ResidualCNN
        m_eq = ResidualCNN(in_channels=5)
        m_eq, r2_equal_cnn = train_cnn(m_eq, [combined[:train_idx], tgt[:train_idx]],
                                        [combined[train_idx:], tgt[train_idx:]],
                                        epochs=50)

        channel_names = ['supply', 'demand', 'hepatic', 'net']
        attn_dict = {ch: round(float(mean_attn[i]), 4) for i, ch in enumerate(channel_names)}

        res = {
            'patient': p['name'],
            'r2_attention': round(r2_attn, 4),
            'r2_equal_cnn': round(r2_equal_cnn, 4),
            'r2_ridge': round(r2_ridge, 4),
            'attn_vs_equal': round(r2_attn - r2_equal_cnn, 4),
            'attention_weights': attn_dict,
        }
        results.append(res)
        if detail:
            attn_str = ' '.join(f'{k}={v:.3f}' for k, v in attn_dict.items())
            print(f"    {p['name']}: attn={r2_attn:.4f} eq_cnn={r2_equal_cnn:.4f} "
                  f"Δ={r2_attn - r2_equal_cnn:+.4f} weights=[{attn_str}]")

    # Aggregate attention weights
    agg_attn = {}
    for ch in ['supply', 'demand', 'hepatic', 'net']:
        vals = [r['attention_weights'][ch] for r in results]
        agg_attn[ch] = round(np.mean(vals), 4)
    ranked = sorted(agg_attn.items(), key=lambda x: x[1], reverse=True)

    gains = [r['attn_vs_equal'] for r in results]
    return {
        'status': 'pass',
        'detail': (f'attn_vs_equal={np.mean(gains):+.4f}, '
                   f'rank: {" > ".join(f"{k}({v:.3f})" for k, v in ranked)}'),
        'results': {'per_patient': results, 'aggregate_attention': agg_attn},
    }


def exp_1043_clarke_error_grid(patients, detail=False):
    """Clarke Error Grid analysis for clinical relevance."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # (a) Ridge-only predictions
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_pred = ridge.predict(vl_flat)

        # (b) Ridge + Residual CNN pipeline
        ridge_train_pred = ridge.predict(tr_flat)
        train_resid = train[1] - ridge_train_pred
        val_resid = val[1] - ridge_pred

        m_res = ResidualCNN(in_channels=5)
        m_res, _ = train_cnn(m_res, [train[0], train_resid],
                             [val[0], val_resid], epochs=50)
        cnn_resid = predict_cnn(m_res, val[0])
        pipeline_pred = ridge_pred + 0.5 * cnn_resid

        # Convert to mg/dL
        ref_mgdl = val[1] * GLUCOSE_SCALE
        ridge_mgdl = ridge_pred * GLUCOSE_SCALE
        pipe_mgdl = pipeline_pred * GLUCOSE_SCALE

        # Clarke zones
        _, ridge_pcts = compute_clarke_zones(ref_mgdl, ridge_mgdl)
        _, pipe_pcts = compute_clarke_zones(ref_mgdl, pipe_mgdl)

        r2_ridge = r2_score(val[1], ridge_pred)
        r2_pipe = r2_score(val[1], pipeline_pred)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_pipeline': round(r2_pipe, 4),
            'ridge_clarke': {
                'A': ridge_pcts['A'], 'B': ridge_pcts['B'],
                'A+B': round(ridge_pcts['A'] + ridge_pcts['B'], 1),
                'D+E': round(ridge_pcts['D'] + ridge_pcts['E'], 1),
            },
            'pipeline_clarke': {
                'A': pipe_pcts['A'], 'B': pipe_pcts['B'],
                'A+B': round(pipe_pcts['A'] + pipe_pcts['B'], 1),
                'D+E': round(pipe_pcts['D'] + pipe_pcts['E'], 1),
            },
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge A={ridge_pcts['A']:.1f}% A+B={ridge_pcts['A']+ridge_pcts['B']:.1f}% "
                  f"| pipe A={pipe_pcts['A']:.1f}% A+B={pipe_pcts['A']+pipe_pcts['B']:.1f}% "
                  f"D+E: {ridge_pcts['D']+ridge_pcts['E']:.1f}%→{pipe_pcts['D']+pipe_pcts['E']:.1f}%")

    # Aggregate
    ridge_a = np.mean([r['ridge_clarke']['A'] for r in results])
    pipe_a = np.mean([r['pipeline_clarke']['A'] for r in results])
    ridge_ab = np.mean([r['ridge_clarke']['A+B'] for r in results])
    pipe_ab = np.mean([r['pipeline_clarke']['A+B'] for r in results])

    return {
        'status': 'pass',
        'detail': (f'ridge: A={ridge_a:.1f}% A+B={ridge_ab:.1f}% | '
                   f'pipeline: A={pipe_a:.1f}% A+B={pipe_ab:.1f}%'),
        'results': {'per_patient': results},
    }


def exp_1044_selective_prediction(patients, detail=False):
    """Ensemble disagreement for selective prediction with reject option."""
    N_SEEDS = 5
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Ridge baseline
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_pred_tr = ridge.predict(tr_flat)
        ridge_pred_vl = ridge.predict(vl_flat)
        train_resid = train[1] - ridge_pred_tr

        r2_ridge = r2_score(val[1], ridge_pred_vl)

        # Train N_SEEDS CNNs on residuals
        cnn_preds = []
        val_resid = val[1] - ridge_pred_vl
        for seed in range(N_SEEDS):
            torch.manual_seed(seed * 42 + 7)
            np.random.seed(seed * 42 + 7)
            m = ResidualCNN(in_channels=5)
            m, _ = train_cnn(m, [train[0], train_resid],
                             [val[0], val_resid], epochs=40, patience=10)
            cnn_pred = predict_cnn(m, val[0])
            cnn_preds.append(ridge_pred_vl + 0.5 * cnn_pred)

        cnn_preds = np.array(cnn_preds)  # (N_SEEDS, n_val)
        ensemble_mean = np.mean(cnn_preds, axis=0)
        ensemble_std = np.std(cnn_preds, axis=0)

        r2_full = r2_score(val[1], ensemble_mean)

        # Sweep rejection thresholds
        thresholds = np.percentile(ensemble_std, [10, 20, 30, 40, 50, 60, 70, 80, 90])
        sweep = []
        r2_at_06 = None
        coverage_at_06 = None

        for thresh in thresholds:
            keep = ensemble_std <= thresh
            coverage = keep.mean()
            if keep.sum() < 10:
                continue
            r2_kept = r2_score(val[1][keep], ensemble_mean[keep])
            sweep.append({
                'threshold': round(float(thresh), 6),
                'coverage': round(float(coverage), 4),
                'r2': round(r2_kept, 4),
            })
            if r2_kept > 0.6 and (r2_at_06 is None or coverage > coverage_at_06):
                r2_at_06 = r2_kept
                coverage_at_06 = coverage

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_full_ensemble': round(r2_full, 4),
            'mean_std': round(float(np.mean(ensemble_std)), 6),
            'sweep': sweep,
            'r2_above_06_coverage': round(coverage_at_06, 4) if coverage_at_06 is not None else None,
        }
        results.append(res)
        if detail:
            cov_str = f"{coverage_at_06:.1%}" if coverage_at_06 is not None else "N/A"
            print(f"    {p['name']}: ridge={r2_ridge:.4f} ensemble={r2_full:.4f} "
                  f"mean_std={np.mean(ensemble_std):.5f} R²>0.6_coverage={cov_str}")

    coverages = [r['r2_above_06_coverage'] for r in results if r['r2_above_06_coverage'] is not None]
    return {
        'status': 'pass',
        'detail': (f'mean_ensemble_r2={np.mean([r["r2_full_ensemble"] for r in results]):.4f}, '
                   f'R²>0.6 coverage: {np.mean(coverages):.1%} ({len(coverages)}/{len(results)} patients)'),
        'results': {'per_patient': results},
    }


def exp_1045_hypo_hyper_alerts(patients, detail=False):
    """Binary classification: will glucose go below 70 or above 180 mg/dL?"""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        tgt_mgdl = tgt * GLUCOSE_SCALE
        combined = np.concatenate([g, phys], axis=2)
        flat = combined.reshape(len(combined), -1)
        train_idx = int(len(flat) * 0.8)

        X_tr, X_val = flat[:train_idx], flat[train_idx:]
        y_tr_mgdl = tgt_mgdl[:train_idx]
        y_val_mgdl = tgt_mgdl[train_idx:]

        alert_results = {}
        for alert_name, threshold, direction in [('hypo', 70, 'below'), ('hyper', 180, 'above')]:
            if direction == 'below':
                y_tr_bin = (y_tr_mgdl < threshold).astype(int)
                y_val_bin = (y_val_mgdl < threshold).astype(int)
            else:
                y_tr_bin = (y_tr_mgdl > threshold).astype(int)
                y_val_bin = (y_val_mgdl > threshold).astype(int)

            n_pos_tr = y_tr_bin.sum()
            n_pos_val = y_val_bin.sum()

            if n_pos_tr < 5 or n_pos_val < 2:
                alert_results[alert_name] = {
                    'n_positive_train': int(n_pos_tr),
                    'n_positive_val': int(n_pos_val),
                    'status': 'insufficient_positives',
                }
                continue

            lr = LogisticRegression(max_iter=1000, class_weight='balanced', C=1.0)
            lr.fit(X_tr, y_tr_bin)
            y_prob = lr.predict_proba(X_val)[:, 1]
            y_pred = lr.predict(X_val)

            sens = recall_score(y_val_bin, y_pred, zero_division=0)
            spec = recall_score(1 - y_val_bin, 1 - y_pred, zero_division=0)
            prec = precision_score(y_val_bin, y_pred, zero_division=0)
            f1 = f1_score(y_val_bin, y_pred, zero_division=0)

            try:
                auc = roc_auc_score(y_val_bin, y_prob)
            except ValueError:
                auc = np.nan

            alert_results[alert_name] = {
                'sensitivity': round(sens, 4),
                'specificity': round(spec, 4),
                'precision': round(prec, 4),
                'f1': round(f1, 4),
                'auc': round(auc, 4) if np.isfinite(auc) else None,
                'n_positive_train': int(n_pos_tr),
                'n_positive_val': int(n_pos_val),
                'prevalence': round(float(y_val_bin.mean()), 4),
            }

        res = {'patient': p['name'], **alert_results}
        results.append(res)
        if detail:
            for alert_name in ['hypo', 'hyper']:
                ar = alert_results[alert_name]
                if ar.get('status') == 'insufficient_positives':
                    print(f"    {p['name']} {alert_name}: insufficient data "
                          f"(tr={ar['n_positive_train']} val={ar['n_positive_val']})")
                else:
                    print(f"    {p['name']} {alert_name}: sens={ar['sensitivity']:.3f} "
                          f"spec={ar['specificity']:.3f} prec={ar['precision']:.3f} "
                          f"F1={ar['f1']:.3f} AUC={ar.get('auc', 'N/A')}")

    # Aggregate where we have results
    summary = {}
    for alert_name in ['hypo', 'hyper']:
        valid = [r[alert_name] for r in results
                 if r[alert_name].get('status') != 'insufficient_positives']
        if valid:
            summary[alert_name] = {
                'mean_sensitivity': round(np.mean([v['sensitivity'] for v in valid]), 4),
                'mean_specificity': round(np.mean([v['specificity'] for v in valid]), 4),
                'mean_f1': round(np.mean([v['f1'] for v in valid]), 4),
                'mean_auc': round(np.nanmean([v['auc'] for v in valid if v['auc'] is not None]), 4),
                'n_patients': len(valid),
            }
        else:
            summary[alert_name] = {'n_patients': 0}

    return {
        'status': 'pass',
        'detail': (f'hypo: F1={summary["hypo"].get("mean_f1", "N/A")} '
                   f'AUC={summary["hypo"].get("mean_auc", "N/A")} '
                   f'(n={summary["hypo"]["n_patients"]}) | '
                   f'hyper: F1={summary["hyper"].get("mean_f1", "N/A")} '
                   f'AUC={summary["hyper"].get("mean_auc", "N/A")} '
                   f'(n={summary["hyper"]["n_patients"]})'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1046_longer_context_windows(patients, detail=False):
    """Test 4h, 6h, 12h context windows vs standard 2h."""
    window_configs = [
        ('2h', 24),    # baseline
        ('4h', 48),
        ('6h', 72),
        ('12h', 144),
    ]
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        window_r2 = {}

        for wname, wsize in window_configs:
            g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd,
                                                    history_steps=wsize)
            if len(g) < 200:
                window_r2[wname] = None
                continue

            combined = np.concatenate([g, phys], axis=2)
            train, val = split_chrono([combined, tgt])
            tr_flat = train[0].reshape(len(train[0]), -1)
            vl_flat = val[0].reshape(len(val[0]), -1)

            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, train[1])
            r2 = r2_score(val[1], ridge.predict(vl_flat))
            window_r2[wname] = round(r2, 4)

        base_r2 = window_r2.get('2h')
        if base_r2 is None:
            continue

        res = {
            'patient': p['name'],
            'r2_by_window': window_r2,
        }
        for wname, _ in window_configs:
            if window_r2[wname] is not None and base_r2 is not None:
                res[f'delta_{wname}'] = round(window_r2[wname] - base_r2, 4)

        results.append(res)
        if detail:
            parts = [f"{wn}={window_r2[wn]:.4f}" if window_r2[wn] is not None else f"{wn}=N/A"
                     for wn, _ in window_configs]
            print(f"    {p['name']}: {' | '.join(parts)}")

    # Aggregate per window
    summary = {}
    for wname, _ in window_configs:
        vals = [r['r2_by_window'][wname] for r in results if r['r2_by_window'].get(wname) is not None]
        if vals:
            summary[wname] = round(np.mean(vals), 4)

    deltas = {}
    for wname, _ in window_configs[1:]:
        dkey = f'delta_{wname}'
        vals = [r[dkey] for r in results if dkey in r]
        if vals:
            deltas[wname] = round(np.mean(vals), 4)

    return {
        'status': 'pass',
        'detail': ('R² by window: ' +
                   ', '.join(f'{wn}={summary.get(wn, "N/A")}' for wn, _ in window_configs) +
                   ' | deltas: ' +
                   ', '.join(f'{wn}={deltas.get(wn, "N/A"):+.4f}' for wn, _ in window_configs[1:]
                             if wn in deltas)),
        'results': {'per_patient': results, 'summary': summary, 'deltas': deltas},
    }


def exp_1047_gap_aware_patient_h(patients, detail=False):
    """Gap-aware architectures for handling missing data (especially patient h)."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        glucose = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose).mean())

        # Strategy 1: Mask-and-impute (last-valid fill + binary mask channel)
        g1, phys1, tgt1, masks1 = build_windowed_data_flexible(
            p['df'], p['pk'], sd, nan_threshold=0.8)
        r2_s1 = None
        if len(g1) >= 100:
            # Append mask as extra channel
            combined_s1 = np.concatenate([g1, phys1, masks1], axis=2)  # glucose + 4 phys + 1 mask = 6
            train_s1, val_s1 = split_chrono([combined_s1, tgt1])
            tr_flat = train_s1[0].reshape(len(train_s1[0]), -1)
            vl_flat = val_s1[0].reshape(len(val_s1[0]), -1)
            ridge_s1 = Ridge(alpha=1.0)
            ridge_s1.fit(tr_flat, train_s1[1])
            r2_s1 = r2_score(val_s1[1], ridge_s1.predict(vl_flat))

        # Strategy 2: Strict filter — skip windows with >50% missing
        g2, phys2, tgt2, _ = build_windowed_data_flexible(
            p['df'], p['pk'], sd, nan_threshold=0.5)
        r2_s2 = None
        if len(g2) >= 100:
            combined_s2 = np.concatenate([g2, phys2], axis=2)
            train_s2, val_s2 = split_chrono([combined_s2, tgt2])
            tr_flat = train_s2[0].reshape(len(train_s2[0]), -1)
            vl_flat = val_s2[0].reshape(len(val_s2[0]), -1)
            ridge_s2 = Ridge(alpha=1.0)
            ridge_s2.fit(tr_flat, train_s2[1])
            r2_s2 = r2_score(val_s2[1], ridge_s2.predict(vl_flat))

        # Strategy 3: Only consecutive-valid segments ≥2h (24 steps)
        valid_mask = ~np.isnan(glucose)
        segments = []
        start = None
        for i in range(len(valid_mask)):
            if valid_mask[i]:
                if start is None:
                    start = i
            else:
                if start is not None and (i - start) >= WINDOW + HORIZON:
                    segments.append((start, i))
                start = None
        if start is not None and (len(valid_mask) - start) >= WINDOW + HORIZON:
            segments.append((start, len(valid_mask)))

        r2_s3 = None
        if segments:
            all_g, all_phys, all_tgt = [], [], []
            for seg_start, seg_end in segments:
                seg_df = p['df'].iloc[seg_start:seg_end].copy()
                seg_pk = p['pk'][seg_start:seg_end]
                seg_sd = compute_supply_demand(seg_df, seg_pk)
                g3, _, phys3, tgt3 = build_windowed_data(seg_df, seg_pk, seg_sd)
                if len(g3) > 0:
                    all_g.append(g3)
                    all_phys.append(phys3)
                    all_tgt.append(tgt3)

            if all_g:
                g_cat = np.concatenate(all_g)
                phys_cat = np.concatenate(all_phys)
                tgt_cat = np.concatenate(all_tgt)
                if len(g_cat) >= 100:
                    combined_s3 = np.concatenate([g_cat, phys_cat], axis=2)
                    train_s3, val_s3 = split_chrono([combined_s3, tgt_cat])
                    tr_flat = train_s3[0].reshape(len(train_s3[0]), -1)
                    vl_flat = val_s3[0].reshape(len(val_s3[0]), -1)
                    ridge_s3 = Ridge(alpha=1.0)
                    ridge_s3.fit(tr_flat, train_s3[1])
                    r2_s3 = r2_score(val_s3[1], ridge_s3.predict(vl_flat))

        # Default baseline (standard 20% NaN threshold)
        g0, pk0, phys0, tgt0 = build_windowed_data(p['df'], p['pk'], sd)
        r2_default = None
        n_windows_default = len(g0)
        if len(g0) >= 100:
            combined_d = np.concatenate([g0, phys0], axis=2)
            train_d, val_d = split_chrono([combined_d, tgt0])
            tr_flat = train_d[0].reshape(len(train_d[0]), -1)
            vl_flat = val_d[0].reshape(len(val_d[0]), -1)
            ridge_d = Ridge(alpha=1.0)
            ridge_d.fit(tr_flat, train_d[1])
            r2_default = r2_score(val_d[1], ridge_d.predict(vl_flat))

        res = {
            'patient': p['name'],
            'missing_rate': round(missing_rate, 4),
            'n_windows_default': n_windows_default,
            'n_windows_mask_impute': len(g1) if len(g1) > 0 else 0,
            'n_windows_strict': len(g2) if len(g2) > 0 else 0,
            'n_segments': len(segments),
            'r2_default': round(r2_default, 4) if r2_default is not None else None,
            'r2_mask_impute': round(r2_s1, 4) if r2_s1 is not None else None,
            'r2_strict_filter': round(r2_s2, 4) if r2_s2 is not None else None,
            'r2_consecutive': round(r2_s3, 4) if r2_s3 is not None else None,
        }
        # Best strategy
        strats = {'default': r2_default, 'mask_impute': r2_s1,
                  'strict_filter': r2_s2, 'consecutive': r2_s3}
        valid_strats = {k: v for k, v in strats.items() if v is not None}
        if valid_strats:
            res['best_strategy'] = max(valid_strats, key=valid_strats.get)
            res['best_r2'] = round(max(valid_strats.values()), 4)

        results.append(res)
        if detail:
            parts = []
            for sname, r2 in [('default', r2_default), ('mask', r2_s1),
                              ('strict', r2_s2), ('consec', r2_s3)]:
                parts.append(f"{sname}={r2:.4f}" if r2 is not None else f"{sname}=N/A")
            marker = " ★" if p['name'] == 'h' else ""
            print(f"    {p['name']}{marker}: miss={missing_rate:.3f} "
                  f"{' | '.join(parts)} best={res.get('best_strategy', 'N/A')}")

    # Special focus on patient h
    h_result = next((r for r in results if r['patient'] == 'h'), None)

    return {
        'status': 'pass',
        'detail': (f'patient_h: {h_result["best_strategy"]}={h_result["best_r2"]:.4f}'
                   if h_result and 'best_strategy' in h_result
                   else 'patient_h: not_in_dataset'),
        'results': {'per_patient': results, 'patient_h': h_result},
    }


def exp_1048_residual_structure_analysis(patients, detail=False):
    """Analyze what the residual CNN learns from Ridge's errors."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Fit Ridge and get residuals
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        val_pred = ridge.predict(vl_flat)
        residuals = val[1] - val_pred

        # Feature correlates of residuals
        val_g = val[0][:, :, 0]  # glucose windows (n_val, 24)
        val_phys = val[0][:, :, 1:]  # physics windows (n_val, 24, 4)

        correlates = {}

        # (a) Glucose level (mean of window)
        g_mean = np.mean(val_g, axis=1)
        if np.std(g_mean) > 1e-8 and np.std(residuals) > 1e-8:
            correlates['glucose_level'] = round(float(np.corrcoef(g_mean, residuals)[0, 1]), 4)

        # (b) Glucose variability (std of window)
        g_std = np.std(val_g, axis=1)
        if np.std(g_std) > 1e-8 and np.std(residuals) > 1e-8:
            correlates['glucose_variability'] = round(float(np.corrcoef(g_std, residuals)[0, 1]), 4)

        # (c) Physics channel means
        channel_names = ['supply', 'demand', 'hepatic', 'net']
        for ci, cname in enumerate(channel_names):
            ch_mean = np.mean(val_phys[:, :, ci], axis=1)
            if np.std(ch_mean) > 1e-8 and np.std(residuals) > 1e-8:
                correlates[cname] = round(float(np.corrcoef(ch_mean, residuals)[0, 1]), 4)

        # (d) Time-of-day proxy: position in validation set (later = different time)
        time_proxy = np.arange(len(residuals), dtype=float)
        if np.std(time_proxy) > 1e-8 and np.std(residuals) > 1e-8:
            correlates['temporal_position'] = round(float(np.corrcoef(time_proxy, residuals)[0, 1]), 4)

        # (e) Glucose rate of change (slope over window)
        g_slope = np.array([np.polyfit(np.arange(val_g.shape[1]), val_g[i], 1)[0]
                            for i in range(len(val_g))])
        if np.std(g_slope) > 1e-8 and np.std(residuals) > 1e-8:
            correlates['glucose_slope'] = round(float(np.corrcoef(g_slope, residuals)[0, 1]), 4)

        # (f) Autocorrelation of residuals
        if len(residuals) > 10:
            resid_centered = residuals - np.mean(residuals)
            var = np.var(resid_centered)
            autocorr = {}
            for lag in [1, 3, 6, 12]:
                if lag < len(resid_centered):
                    c = np.mean(resid_centered[lag:] * resid_centered[:-lag]) / max(var, 1e-10)
                    autocorr[f'lag_{lag}'] = round(float(c), 4)
        else:
            autocorr = {}

        # Rank correlates by absolute value
        ranked = sorted(correlates.items(), key=lambda x: abs(x[1]), reverse=True)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_score(val[1], val_pred), 4),
            'residual_mean': round(float(np.mean(residuals)), 6),
            'residual_std': round(float(np.std(residuals)), 6),
            'correlates': correlates,
            'autocorrelation': autocorr,
            'top_correlates': [f"{k}(r={v:+.3f})" for k, v in ranked[:3]],
        }
        results.append(res)
        if detail:
            top = ' '.join(res['top_correlates'])
            ac_str = ' '.join(f"L{k.split('_')[1]}={v:.3f}" for k, v in autocorr.items())
            print(f"    {p['name']}: resid_std={np.std(residuals):.5f} "
                  f"top=[{top}] autocorr=[{ac_str}]")

    # Aggregate: which features most consistently correlate with residuals?
    all_features = set()
    for r in results:
        all_features.update(r['correlates'].keys())

    agg_correlates = {}
    for feat in all_features:
        vals = [r['correlates'].get(feat, 0) for r in results]
        agg_correlates[feat] = {
            'mean_abs_corr': round(np.mean(np.abs(vals)), 4),
            'mean_corr': round(np.mean(vals), 4),
        }

    ranked_agg = sorted(agg_correlates.items(), key=lambda x: x[1]['mean_abs_corr'], reverse=True)

    return {
        'status': 'pass',
        'detail': ('top_residual_correlates: ' +
                   ', '.join(f'{k}(|r|={v["mean_abs_corr"]:.3f})' for k, v in ranked_agg[:3])),
        'results': {'per_patient': results, 'aggregate_correlates': agg_correlates},
    }


def exp_1049_feature_interactions(patients, detail=False):
    """Test interaction and quadratic terms for Ridge."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        # Build feature vectors: mean of each physics channel over window
        phys_means = np.mean(phys, axis=1)  # (n, 4): supply, demand, hepatic, net
        g_flat = g[:, :, 0]  # (n, 24) glucose window

        # Base features: glucose window + physics means
        X_base = np.concatenate([g_flat, phys_means], axis=1)  # (n, 28)

        # Pairwise interactions (6 terms)
        s, d, h, net = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
        interactions = np.column_stack([
            s * d,      # supply × demand
            s * h,      # supply × hepatic
            s * net,    # supply × net
            d * h,      # demand × hepatic
            d * net,    # demand × net
            h * net,    # hepatic × net
        ])

        # Quadratic terms (4 terms)
        quadratics = np.column_stack([s**2, d**2, h**2, net**2])

        X_interact = np.concatenate([X_base, interactions], axis=1)
        X_full = np.concatenate([X_base, interactions, quadratics], axis=1)

        # Chronological split
        split = int(len(X_base) * 0.8)

        # (a) Base Ridge
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_base[:split], tgt[:split])
        r2_base = r2_score(tgt[split:], ridge_base.predict(X_base[split:]))

        # (b) Ridge + interactions only
        ridge_inter = Ridge(alpha=1.0)
        ridge_inter.fit(X_interact[:split], tgt[:split])
        r2_interact = r2_score(tgt[split:], ridge_inter.predict(X_interact[split:]))

        # (c) Ridge + interactions + quadratics
        ridge_full = Ridge(alpha=1.0)
        ridge_full.fit(X_full[:split], tgt[:split])
        r2_full = r2_score(tgt[split:], ridge_full.predict(X_full[split:]))

        # (d) Individual interaction importance
        interaction_names = ['supply×demand', 'supply×hepatic', 'supply×net',
                             'demand×hepatic', 'demand×net', 'hepatic×net']
        interaction_importance = {}
        for idx, iname in enumerate(interaction_names):
            # Ablation: use full model but zero out this interaction
            X_ablate = X_full.copy()
            X_ablate[:, len(X_base[0]) + idx] = 0.0
            r2_ablate = r2_score(tgt[split:], ridge_full.predict(X_ablate[split:]))
            interaction_importance[iname] = round(r2_full - r2_ablate, 4)

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_interactions': round(r2_interact, 4),
            'r2_full': round(r2_full, 4),
            'interact_gain': round(r2_interact - r2_base, 4),
            'full_gain': round(r2_full - r2_base, 4),
            'interaction_importance': interaction_importance,
        }
        results.append(res)
        if detail:
            top_inter = sorted(interaction_importance.items(),
                               key=lambda x: abs(x[1]), reverse=True)[:3]
            top_str = ' '.join(f'{k}={v:+.4f}' for k, v in top_inter)
            print(f"    {p['name']}: base={r2_base:.4f} +inter={r2_interact:.4f}"
                  f"({r2_interact-r2_base:+.4f}) +quad={r2_full:.4f}"
                  f"({r2_full-r2_base:+.4f}) top=[{top_str}]")

    interact_gains = [r['interact_gain'] for r in results]
    full_gains = [r['full_gain'] for r in results]
    return {
        'status': 'pass',
        'detail': (f'interact_gain={np.mean(interact_gains):+.4f}, '
                   f'full_gain={np.mean(full_gains):+.4f}, '
                   f'positive_interact={sum(1 for g in interact_gains if g > 0)}/{len(results)}'),
        'results': {'per_patient': results},
    }


def exp_1050_grand_benchmark(patients, detail=False):
    """Grand benchmark with data quality exclusion criteria.

    Excludes patients with >25% missing rate. Runs full pipeline:
    glucose-only → +physics → +residual CNN → +confidence.
    Reports block CV R², MAE, Clarke zone A%.
    """
    results = []
    excluded = []

    for p in patients:
        glucose = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose).mean())

        if missing_rate > 0.25:
            excluded.append({'patient': p['name'], 'missing_rate': round(missing_rate, 4)})
            if detail:
                print(f"    {p['name']}: EXCLUDED (missing={missing_rate:.1%})")
            continue

        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            excluded.append({'patient': p['name'], 'reason': 'insufficient_windows'})
            continue
        combined = np.concatenate([g, phys], axis=2)

        n = len(combined)
        n_folds = 5
        fold_size = n // n_folds

        fold_results = {
            'r2_glucose_only': [],
            'r2_ridge_physics': [],
            'r2_residual_cnn': [],
            'r2_ensemble': [],
            'mae_mg_dl': [],
            'clarke_A_pct': [],
            'clarke_AB_pct': [],
        }

        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = min((fold + 1) * fold_size, n)
            train_idx = np.concatenate([np.arange(0, val_start),
                                        np.arange(val_end, n)])

            tr_X = combined[train_idx]
            tr_y = tgt[train_idx]
            vl_X = combined[val_start:val_end]
            vl_y = tgt[val_start:val_end]

            if len(vl_X) < 10:
                continue

            tr_flat = tr_X.reshape(len(tr_X), -1)
            vl_flat = vl_X.reshape(len(vl_X), -1)

            # Stage 0: Glucose-only Ridge
            tr_g = g[train_idx].reshape(len(train_idx), -1)
            vl_g = g[val_start:val_end].reshape(val_end - val_start, -1)
            ridge_g = Ridge(alpha=1.0)
            ridge_g.fit(tr_g, tr_y)
            r2_g = r2_score(vl_y, ridge_g.predict(vl_g))
            fold_results['r2_glucose_only'].append(r2_g)

            # Stage 1: Ridge with physics
            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, tr_y)
            ridge_pred_train = ridge.predict(tr_flat)
            ridge_pred_val = ridge.predict(vl_flat)
            r2_ridge = r2_score(vl_y, ridge_pred_val)
            fold_results['r2_ridge_physics'].append(r2_ridge)

            # Stage 2: Residual CNN
            train_resid = tr_y - ridge_pred_train
            val_resid = vl_y - ridge_pred_val

            m_res = ResidualCNN(in_channels=5)
            m_res, _ = train_cnn(m_res, [tr_X, train_resid],
                                 [vl_X, val_resid], epochs=40)
            cnn_resid = predict_cnn(m_res, vl_X)
            combined_pred = ridge_pred_val + 0.5 * cnn_resid
            r2_resid = r2_score(vl_y, combined_pred)
            fold_results['r2_residual_cnn'].append(r2_resid)

            # Stage 3: Ensemble (3 seeds)
            ensemble_preds = [combined_pred]
            for seed in [1, 2]:
                torch.manual_seed(seed * 77)
                m_s = ResidualCNN(in_channels=5)
                m_s, _ = train_cnn(m_s, [tr_X, train_resid],
                                   [vl_X, val_resid], epochs=40)
                cnn_s = predict_cnn(m_s, vl_X)
                ensemble_preds.append(ridge_pred_val + 0.5 * cnn_s)

            ens_pred = np.mean(ensemble_preds, axis=0)
            r2_ens = r2_score(vl_y, ens_pred)
            fold_results['r2_ensemble'].append(r2_ens)

            mae = float(np.mean(np.abs(ens_pred - vl_y)) * GLUCOSE_SCALE)
            fold_results['mae_mg_dl'].append(mae)

            # Clarke Error Grid on ensemble predictions
            ref_mgdl = vl_y * GLUCOSE_SCALE
            pred_mgdl = ens_pred * GLUCOSE_SCALE
            _, pcts = compute_clarke_zones(ref_mgdl, pred_mgdl)
            fold_results['clarke_A_pct'].append(pcts['A'])
            fold_results['clarke_AB_pct'].append(pcts['A'] + pcts['B'])

        if not fold_results['r2_ensemble']:
            continue

        res = {'patient': p['name'], 'missing_rate': round(missing_rate, 4)}
        for key, vals in fold_results.items():
            res[f'{key}_mean'] = round(np.mean(vals), 4)
            res[f'{key}_std'] = round(np.std(vals), 4)
        res['n_folds'] = len(fold_results['r2_ensemble'])
        res['physics_lift'] = round(
            res['r2_ridge_physics_mean'] - res['r2_glucose_only_mean'], 4)
        res['residual_lift'] = round(
            res['r2_residual_cnn_mean'] - res['r2_ridge_physics_mean'], 4)
        res['ensemble_lift'] = round(
            res['r2_ensemble_mean'] - res['r2_residual_cnn_mean'], 4)

        results.append(res)
        if detail:
            print(f"    {p['name']}: g_only={res['r2_glucose_only_mean']:.4f} "
                  f"ridge+phys={res['r2_ridge_physics_mean']:.4f} "
                  f"resid_cnn={res['r2_residual_cnn_mean']:.4f} "
                  f"ensemble={res['r2_ensemble_mean']:.4f} "
                  f"mae={res['mae_mg_dl_mean']:.1f}mg/dL "
                  f"clarke_A={res['clarke_A_pct_mean']:.1f}%")

    # Grand summary
    summary = {}
    for key in ['r2_glucose_only_mean', 'r2_ridge_physics_mean',
                'r2_residual_cnn_mean', 'r2_ensemble_mean',
                'mae_mg_dl_mean', 'clarke_A_pct_mean', 'clarke_AB_pct_mean']:
        vals = [r[key] for r in results if key in r]
        if vals:
            summary[key] = round(np.mean(vals), 4)

    summary['physics_lift'] = round(np.mean([r['physics_lift'] for r in results]), 4)
    summary['residual_lift'] = round(np.mean([r['residual_lift'] for r in results]), 4)
    summary['ensemble_lift'] = round(np.mean([r['ensemble_lift'] for r in results]), 4)
    summary['n_included'] = len(results)
    summary['n_excluded'] = len(excluded)

    return {
        'status': 'pass',
        'detail': (f'pipeline ({summary["n_included"]} patients, {summary["n_excluded"]} excluded): '
                   f'g_only={summary.get("r2_glucose_only_mean", "N/A")} → '
                   f'ridge+phys={summary.get("r2_ridge_physics_mean", "N/A")} → '
                   f'resid_cnn={summary.get("r2_residual_cnn_mean", "N/A")} → '
                   f'ensemble={summary.get("r2_ensemble_mean", "N/A")} '
                   f'(mae={summary.get("mae_mg_dl_mean", "N/A")}mg/dL, '
                   f'clarke_A={summary.get("clarke_A_pct_mean", "N/A")}%)'),
        'results': {'per_patient': results, 'excluded': excluded, 'summary': summary},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1041', 'Hepatic Production Deep Dive', exp_1041_hepatic_deep_dive),
    ('EXP-1042', 'Attention Over Physics Channels', exp_1042_attention_over_physics),
    ('EXP-1043', 'Clarke Error Grid Analysis', exp_1043_clarke_error_grid),
    ('EXP-1044', 'Selective Prediction with Reject Option', exp_1044_selective_prediction),
    ('EXP-1045', 'Hypo/Hyper Alert Prediction', exp_1045_hypo_hyper_alerts),
    ('EXP-1046', 'Longer Context Windows', exp_1046_longer_context_windows),
    ('EXP-1047', 'Gap-Aware Architecture for Patient h', exp_1047_gap_aware_patient_h),
    ('EXP-1048', 'Residual Structure Analysis', exp_1048_residual_structure_analysis),
    ('EXP-1049', 'Feature Interaction Terms', exp_1049_feature_interactions),
    ('EXP-1050', 'Grand Benchmark with Exclusion Criteria', exp_1050_grand_benchmark),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1041-1050: Hepatic Deep Dive, Clinical Metrics & Attention')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Using device: {DEVICE}")

    for exp_id, name, func in EXPERIMENTS:
        if args.experiment and exp_id != args.experiment:
            continue

        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {name}")
        print(f"{'='*60}")

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
                    'status': result.get('status'), 'detail': result.get('detail'),
                    'elapsed_seconds': round(elapsed, 1),
                    'results': result.get('results', {}),
                }
                save_name = f"{exp_id.lower()}_{name.lower().replace(' ', '_').replace('-', '_')}"
                save_path = save_results(save_data, save_name)
                print(f"  Saved: {save_path}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  Status: FAIL")
            print(f"  Error: {e}")
            print(f"  Time: {elapsed:.1f}s")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print("All experiments complete")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
