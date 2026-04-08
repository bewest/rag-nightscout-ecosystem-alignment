#!/usr/bin/env python3
"""EXP-1051 to EXP-1060: Advanced residual models, stacking, and clinical optimization.

Building on EXP-1021-1050's highest-leverage findings:
- Residual CNN helps ALL 11/11 patients (+0.024) — L1 autocorrelation in Ridge residuals = 0.52
- Feature interactions help 10/11 (+0.004) — cross-channel nonlinearity (demand×hepatic, hepatic×net)
- Hypo prediction has low F1=0.16 due to class imbalance (AUC=0.804 is good)
- 2h window optimal but patient a gains at 6h
- Transfer learning helps hard patients (j: +0.075, k: +0.087)
- Block CV shows ~7% R² inflation over simple split

This batch focuses on:
1. Autoregressive residual features (exploit lag-1..3 autocorrelation)
2. Interaction terms + residual CNN stacking (combine two best levers)
3. Hypo prediction with class rebalancing (fix F1=0.16)
4. Per-patient optimal window length (individualized context)
5. Noise ceiling analysis (how much R² room remains)
6. Stacked generalization (level-2 meta-learner)
7. Physics channel temporal derivatives (rate-of-change features)
8. Patient clustering by difficulty (tier-specific models)
9. Lagged physics features (longer-term metabolic context)
10. Definitive grand benchmark (block CV, full pipeline)

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1051 --detail --save --max-patients 11
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
    """Classify a (reference, prediction) pair into Clarke Error Grid zone A-E."""
    ref, pred = float(ref_mgdl), float(pred_mgdl)

    if ref < 70 and pred > 180:
        return 'D'
    if ref > 240 and pred < 70:
        return 'D'
    if ref >= 180 and pred <= 70:
        return 'E'
    if ref <= 70 and pred >= 180:
        return 'E'
    if ref < 70:
        if abs(pred - ref) <= 20:
            return 'A'
    else:
        if abs(pred - ref) / ref <= 0.20:
            return 'A'
    if ref >= 70 and ref <= 180:
        if pred > ref + 110:
            return 'C'
    if ref >= 130 and ref <= 180:
        if pred < (7.0 / 5.0) * ref - 182:
            return 'C'
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


# ─── Block CV Helper ───

def block_cv_ridge(X, y, n_folds=3, alpha=1.0):
    """Block (temporal) cross-validation for Ridge."""
    n = len(X)
    fold_size = n // n_folds
    r2_scores = []
    preds_all, trues_all = [], []
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size if fold < n_folds - 1 else n
        mask = np.ones(n, dtype=bool)
        mask[val_start:val_end] = False
        Xtr = X[mask].reshape(mask.sum(), -1)
        Xvl = X[~mask].reshape((~mask).sum(), -1)
        ytr = y[mask]
        yvl = y[~mask]
        model = Ridge(alpha=alpha)
        model.fit(Xtr, ytr)
        pred = model.predict(Xvl)
        ss_res = np.sum((yvl - pred)**2)
        ss_tot = np.sum((yvl - yvl.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        r2_scores.append(r2)
        preds_all.append(pred)
        trues_all.append(yvl)
    return np.mean(r2_scores), r2_scores, preds_all, trues_all


# ─── Experiments ───

def exp_1051_autoregressive_residuals(patients, detail=False):
    """Autoregressive residual features: exploit lag-1..3 autocorrelation in Ridge residuals.

    Ridge residuals have L1 autocorrelation of 0.52. Fit a first-stage Ridge on physics
    features, compute training residuals, then fit a second-stage Ridge using original
    features PLUS lag-1, lag-2, lag-3 residuals from the first stage.
    """
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)

        # Stage 1: baseline Ridge
        ridge1 = Ridge(alpha=1.0)
        ridge1.fit(tr_flat, train[1])
        tr_pred1 = ridge1.predict(tr_flat)
        vl_pred1 = ridge1.predict(vl_flat)
        r2_base = r2_score(val[1], vl_pred1)

        # Compute training residuals
        tr_resid = train[1] - tr_pred1

        # Compute lag-1, lag-2, lag-3 residual features for training set
        n_tr = len(tr_resid)
        max_lag = 3
        tr_lag_feats = np.zeros((n_tr, max_lag))
        for lag in range(1, max_lag + 1):
            tr_lag_feats[lag:, lag - 1] = tr_resid[:-lag]

        # For validation set, use validation residuals from first-stage Ridge
        vl_resid = val[1] - vl_pred1
        n_vl = len(vl_resid)
        vl_lag_feats = np.zeros((n_vl, max_lag))
        for lag in range(1, max_lag + 1):
            vl_lag_feats[lag:, lag - 1] = vl_resid[:-lag]

        # Stage 2: Ridge with original features + lag residuals
        tr_flat2 = np.concatenate([tr_flat, tr_lag_feats], axis=1)
        vl_flat2 = np.concatenate([vl_flat, vl_lag_feats], axis=1)
        ridge2 = Ridge(alpha=1.0)
        ridge2.fit(tr_flat2, train[1])
        vl_pred2 = ridge2.predict(vl_flat2)
        r2_ar = r2_score(val[1], vl_pred2)

        # Also test lag-1 only
        tr_flat_l1 = np.concatenate([tr_flat, tr_lag_feats[:, :1]], axis=1)
        vl_flat_l1 = np.concatenate([vl_flat, vl_lag_feats[:, :1]], axis=1)
        ridge_l1 = Ridge(alpha=1.0)
        ridge_l1.fit(tr_flat_l1, train[1])
        r2_l1 = r2_score(val[1], ridge_l1.predict(vl_flat_l1))

        # Measure residual autocorrelation
        resid_centered = tr_resid - np.mean(tr_resid)
        var = np.var(resid_centered)
        autocorr = {}
        for lag in [1, 2, 3]:
            if lag < len(resid_centered) and var > 1e-10:
                c = np.mean(resid_centered[lag:] * resid_centered[:-lag]) / var
                autocorr[f'lag_{lag}'] = round(float(c), 4)

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_lag1_only': round(r2_l1, 4),
            'r2_lag123': round(r2_ar, 4),
            'gain_lag1': round(r2_l1 - r2_base, 4),
            'gain_lag123': round(r2_ar - r2_base, 4),
            'autocorrelation': autocorr,
        }
        results.append(res)
        if detail:
            ac_str = ' '.join(f'L{k.split("_")[1]}={v:.3f}' for k, v in autocorr.items())
            print(f"    {p['name']}: base={r2_base:.4f} +lag1={r2_l1:.4f}"
                  f"({r2_l1-r2_base:+.4f}) +lag123={r2_ar:.4f}"
                  f"({r2_ar-r2_base:+.4f}) autocorr=[{ac_str}]")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    gains_l1 = [r['gain_lag1'] for r in results]
    gains_l123 = [r['gain_lag123'] for r in results]
    n_positive = sum(1 for g in gains_l123 if g > 0)
    return {
        'status': 'pass',
        'detail': (f'lag1_gain={np.mean(gains_l1):+.4f}, '
                   f'lag123_gain={np.mean(gains_l123):+.4f}, '
                   f'positive={n_positive}/{len(results)}'),
        'results': {'per_patient': results, 'summary': {
            'mean_gain_lag1': round(np.mean(gains_l1), 4),
            'mean_gain_lag123': round(np.mean(gains_l123), 4),
            'n_positive_lag123': n_positive,
            'n_patients': len(results),
        }},
    }


def exp_1052_interaction_residual_cnn_stack(patients, detail=False):
    """Combine interaction terms (EXP-1049: +0.004) with residual CNN (EXP-1024: +0.024).

    Compare four configurations:
    1. Base Ridge (physics only)
    2. Ridge + interactions
    3. Ridge + residual CNN
    4. Ridge + interactions + residual CNN
    """
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        combined = np.concatenate([g, phys], axis=2)  # (n, 24, 5)

        # Compute interaction features: mean physics then pairwise products
        phys_means = np.mean(phys, axis=1)  # (n, 4)
        s, d, h, net = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
        interactions = np.column_stack([
            s * d, s * h, s * net, d * h, d * net, h * net,
        ])

        train_c, val_c = split_chrono([combined, tgt])
        train_int, val_int = split_chrono([interactions])

        tr_flat = train_c[0].reshape(len(train_c[0]), -1)
        vl_flat = val_c[0].reshape(len(val_c[0]), -1)
        tr_flat_int = np.concatenate([tr_flat, train_int[0]], axis=1)
        vl_flat_int = np.concatenate([vl_flat, val_int[0]], axis=1)

        # 1. Base Ridge
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(tr_flat, train_c[1])
        pred_base = ridge_base.predict(vl_flat)
        r2_base = r2_score(val_c[1], pred_base)

        # 2. Ridge + interactions
        ridge_int = Ridge(alpha=1.0)
        ridge_int.fit(tr_flat_int, train_c[1])
        pred_int = ridge_int.predict(vl_flat_int)
        r2_int = r2_score(val_c[1], pred_int)

        # 3. Ridge + residual CNN (on base Ridge residuals)
        tr_resid_base = train_c[1] - ridge_base.predict(tr_flat)
        vl_resid_base = val_c[1] - pred_base

        torch.manual_seed(42)
        cnn_base = ResidualCNN(in_channels=5)
        cnn_base, _ = train_cnn(cnn_base, [train_c[0], tr_resid_base],
                                [val_c[0], vl_resid_base], epochs=40)
        cnn_pred_base = predict_cnn(cnn_base, val_c[0])
        pred_base_cnn = pred_base + 0.5 * cnn_pred_base
        r2_base_cnn = r2_score(val_c[1], pred_base_cnn)

        # 4. Ridge + interactions + residual CNN (on interaction Ridge residuals)
        tr_resid_int = train_c[1] - ridge_int.predict(tr_flat_int)
        vl_resid_int = val_c[1] - pred_int

        torch.manual_seed(42)
        cnn_int = ResidualCNN(in_channels=5)
        cnn_int, _ = train_cnn(cnn_int, [train_c[0], tr_resid_int],
                               [val_c[0], vl_resid_int], epochs=40)
        cnn_pred_int = predict_cnn(cnn_int, val_c[0])
        pred_int_cnn = pred_int + 0.5 * cnn_pred_int
        r2_int_cnn = r2_score(val_c[1], pred_int_cnn)

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_interactions': round(r2_int, 4),
            'r2_base_cnn': round(r2_base_cnn, 4),
            'r2_int_cnn': round(r2_int_cnn, 4),
            'gain_interactions': round(r2_int - r2_base, 4),
            'gain_cnn': round(r2_base_cnn - r2_base, 4),
            'gain_combined': round(r2_int_cnn - r2_base, 4),
            'additive_check': round((r2_int_cnn - r2_base) -
                                    (r2_int - r2_base) - (r2_base_cnn - r2_base), 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} +int={r2_int:.4f}"
                  f"({r2_int-r2_base:+.4f}) +cnn={r2_base_cnn:.4f}"
                  f"({r2_base_cnn-r2_base:+.4f}) +both={r2_int_cnn:.4f}"
                  f"({r2_int_cnn-r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_interactions': round(np.mean([r['r2_interactions'] for r in results]), 4),
        'mean_r2_base_cnn': round(np.mean([r['r2_base_cnn'] for r in results]), 4),
        'mean_r2_int_cnn': round(np.mean([r['r2_int_cnn'] for r in results]), 4),
        'mean_gain_combined': round(np.mean([r['gain_combined'] for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} → '
                   f'+int={summary["mean_r2_interactions"]:.4f} → '
                   f'+cnn={summary["mean_r2_base_cnn"]:.4f} → '
                   f'+both={summary["mean_r2_int_cnn"]:.4f} '
                   f'(combined_gain={summary["mean_gain_combined"]:+.4f})'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1053_hypo_class_rebalancing(patients, detail=False):
    """Hypo prediction with class rebalancing to fix F1=0.16.

    EXP-1045 showed hypo F1=0.16 due to class imbalance (AUC=0.804 is good).
    Try three strategies:
    1. Class-weighted logistic regression (weight inversely proportional to frequency)
    2. Random oversampling of minority class
    3. Threshold optimization (F1-optimal threshold on train set)
    Compare all three to unweighted baseline. Target: glucose < 70 mg/dL within horizon.
    """
    HYPO_THRESHOLD = 70.0  # mg/dL
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        combined = np.concatenate([g, phys], axis=2)
        tgt_mgdl = tgt * GLUCOSE_SCALE
        flat = combined.reshape(len(combined), -1)
        split_idx = int(len(flat) * 0.8)

        X_tr, X_val = flat[:split_idx], flat[split_idx:]
        y_tr_mgdl, y_val_mgdl = tgt_mgdl[:split_idx], tgt_mgdl[split_idx:]
        y_tr_bin = (y_tr_mgdl < HYPO_THRESHOLD).astype(int)
        y_val_bin = (y_val_mgdl < HYPO_THRESHOLD).astype(int)

        n_pos_tr = y_tr_bin.sum()
        n_pos_val = y_val_bin.sum()

        if n_pos_tr < 5 or n_pos_val < 2:
            results.append({
                'patient': p['name'],
                'status': 'insufficient_positives',
                'n_positive_train': int(n_pos_tr),
                'n_positive_val': int(n_pos_val),
            })
            if detail:
                print(f"    {p['name']}: insufficient hypo events "
                      f"(tr={n_pos_tr} val={n_pos_val})")
            continue

        # 0. Unweighted baseline
        lr_base = LogisticRegression(max_iter=1000, C=1.0)
        lr_base.fit(X_tr, y_tr_bin)
        y_prob_base = lr_base.predict_proba(X_val)[:, 1]
        y_pred_base = lr_base.predict(X_val)
        f1_base = f1_score(y_val_bin, y_pred_base, zero_division=0)
        try:
            auc_base = roc_auc_score(y_val_bin, y_prob_base)
        except ValueError:
            auc_base = np.nan

        # 1. Class-weighted logistic regression
        lr_weighted = LogisticRegression(max_iter=1000, C=1.0, class_weight='balanced')
        lr_weighted.fit(X_tr, y_tr_bin)
        y_prob_w = lr_weighted.predict_proba(X_val)[:, 1]
        y_pred_w = lr_weighted.predict(X_val)
        f1_weighted = f1_score(y_val_bin, y_pred_w, zero_division=0)
        sens_weighted = recall_score(y_val_bin, y_pred_w, zero_division=0)
        prec_weighted = precision_score(y_val_bin, y_pred_w, zero_division=0)

        # 2. Random oversampling of minority class
        pos_idx = np.where(y_tr_bin == 1)[0]
        neg_idx = np.where(y_tr_bin == 0)[0]
        rng = np.random.RandomState(42)
        n_oversample = len(neg_idx) - len(pos_idx)
        if n_oversample > 0 and len(pos_idx) > 0:
            oversampled_idx = rng.choice(pos_idx, size=n_oversample, replace=True)
            all_idx = np.concatenate([np.arange(len(X_tr)), oversampled_idx])
            X_tr_os = X_tr[all_idx]
            y_tr_os = y_tr_bin[all_idx]
        else:
            X_tr_os = X_tr
            y_tr_os = y_tr_bin

        lr_os = LogisticRegression(max_iter=1000, C=1.0)
        lr_os.fit(X_tr_os, y_tr_os)
        y_prob_os = lr_os.predict_proba(X_val)[:, 1]
        y_pred_os = lr_os.predict(X_val)
        f1_oversample = f1_score(y_val_bin, y_pred_os, zero_division=0)

        # 3. Threshold optimization (F1-optimal threshold on train set)
        y_prob_tr_w = lr_weighted.predict_proba(X_tr)[:, 1]
        best_thresh, best_f1_tr = 0.5, 0.0
        for thresh in np.arange(0.05, 0.95, 0.01):
            y_pred_tr_th = (y_prob_tr_w >= thresh).astype(int)
            f1_th = f1_score(y_tr_bin, y_pred_tr_th, zero_division=0)
            if f1_th > best_f1_tr:
                best_f1_tr = f1_th
                best_thresh = thresh

        y_pred_opt = (y_prob_w >= best_thresh).astype(int)
        f1_threshold = f1_score(y_val_bin, y_pred_opt, zero_division=0)
        sens_threshold = recall_score(y_val_bin, y_pred_opt, zero_division=0)
        prec_threshold = precision_score(y_val_bin, y_pred_opt, zero_division=0)

        res = {
            'patient': p['name'],
            'n_positive_train': int(n_pos_tr),
            'n_positive_val': int(n_pos_val),
            'prevalence': round(float(y_val_bin.mean()), 4),
            'f1_unweighted': round(f1_base, 4),
            'f1_weighted': round(f1_weighted, 4),
            'f1_oversampled': round(f1_oversample, 4),
            'f1_threshold_opt': round(f1_threshold, 4),
            'optimal_threshold': round(best_thresh, 3),
            'auc_baseline': round(auc_base, 4) if np.isfinite(auc_base) else None,
            'sens_weighted': round(sens_weighted, 4),
            'prec_weighted': round(prec_weighted, 4),
            'sens_threshold': round(sens_threshold, 4),
            'prec_threshold': round(prec_threshold, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base_F1={f1_base:.3f} weighted={f1_weighted:.3f} "
                  f"oversample={f1_oversample:.3f} thresh_opt={f1_threshold:.3f}"
                  f"(t={best_thresh:.2f}) AUC={auc_base:.3f}")

    valid = [r for r in results if r.get('status') != 'insufficient_positives']
    if not valid:
        return {'status': 'FAIL', 'detail': 'No patients with sufficient hypo events'}

    summary = {
        'mean_f1_unweighted': round(np.mean([r['f1_unweighted'] for r in valid]), 4),
        'mean_f1_weighted': round(np.mean([r['f1_weighted'] for r in valid]), 4),
        'mean_f1_oversampled': round(np.mean([r['f1_oversampled'] for r in valid]), 4),
        'mean_f1_threshold_opt': round(np.mean([r['f1_threshold_opt'] for r in valid]), 4),
        'n_patients_valid': len(valid),
        'n_patients_insufficient': len(results) - len(valid),
    }
    best_method = max(['unweighted', 'weighted', 'oversampled', 'threshold_opt'],
                      key=lambda m: summary[f'mean_f1_{m}'])
    summary['best_method'] = best_method

    return {
        'status': 'pass',
        'detail': (f'F1: base={summary["mean_f1_unweighted"]:.3f} '
                   f'weighted={summary["mean_f1_weighted"]:.3f} '
                   f'oversample={summary["mean_f1_oversampled"]:.3f} '
                   f'thresh_opt={summary["mean_f1_threshold_opt"]:.3f} '
                   f'best={best_method} (n={len(valid)})'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1054_per_patient_optimal_window(patients, detail=False):
    """Per-patient optimal window length.

    EXP-1046 showed 2h is best on average but patient a gains at 6h.
    For each patient, evaluate windows of 1h, 2h, 3h, 4h, 6h (12, 24, 36, 48, 72 steps)
    and select the best. Report per-patient optimal and mean R² with individualized windows.
    """
    window_configs = [
        ('1h', 12),
        ('2h', 24),
        ('3h', 36),
        ('4h', 48),
        ('6h', 72),
    ]
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        window_r2 = {}

        for wname, wsize in window_configs:
            g, pk_w, phys, tgt = build_windowed_data(p['df'], p['pk'], sd,
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

        # Find optimal
        valid_windows = {k: v for k, v in window_r2.items() if v is not None}
        if not valid_windows:
            continue

        best_window = max(valid_windows, key=valid_windows.get)
        best_r2 = valid_windows[best_window]
        default_r2 = window_r2.get('2h')

        res = {
            'patient': p['name'],
            'r2_by_window': window_r2,
            'best_window': best_window,
            'best_r2': best_r2,
            'default_r2': default_r2,
            'gain_from_optimal': round(best_r2 - default_r2, 4) if default_r2 is not None else None,
        }
        results.append(res)
        if detail:
            parts = [f"{wn}={window_r2[wn]:.4f}" if window_r2[wn] is not None else f"{wn}=N/A"
                     for wn, _ in window_configs]
            marker = " ★" if best_window != '2h' else ""
            print(f"    {p['name']}: {' | '.join(parts)} → best={best_window}{marker}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate
    mean_default = np.mean([r['default_r2'] for r in results if r['default_r2'] is not None])
    mean_optimal = np.mean([r['best_r2'] for r in results])
    gains = [r['gain_from_optimal'] for r in results if r['gain_from_optimal'] is not None]
    window_counts = {}
    for r in results:
        w = r['best_window']
        window_counts[w] = window_counts.get(w, 0) + 1

    summary = {
        'mean_r2_default_2h': round(mean_default, 4),
        'mean_r2_optimal': round(mean_optimal, 4),
        'mean_gain': round(np.mean(gains), 4) if gains else 0.0,
        'window_distribution': window_counts,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'default_2h={summary["mean_r2_default_2h"]:.4f} → '
                   f'optimal={summary["mean_r2_optimal"]:.4f} '
                   f'(gain={summary["mean_gain"]:+.4f}) '
                   f'distribution={window_counts}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1055_noise_ceiling_analysis(patients, detail=False):
    """Noise ceiling analysis: estimate theoretical max R² given CGM sensor noise.

    Add Gaussian noise to validation glucose targets (sigma = 5, 10, 15, 20 mg/dL),
    compute R² between noisy and clean targets. This gives the upper bound on R²
    at each noise level. Compare to achieved R² to estimate remaining room.
    """
    noise_levels = [5, 10, 15, 20]  # mg/dL
    n_trials = 50  # average over random noise samples
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Achieved R² (Ridge baseline)
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        pred = ridge.predict(vl_flat)
        r2_achieved = r2_score(val[1], pred)

        # Clean validation targets in mg/dL
        y_clean_mgdl = val[1] * GLUCOSE_SCALE
        y_var = np.var(y_clean_mgdl)

        noise_ceilings = {}
        for sigma in noise_levels:
            rng = np.random.RandomState(42)
            r2_trials = []
            for _ in range(n_trials):
                noise = rng.normal(0, sigma, len(y_clean_mgdl))
                y_noisy = y_clean_mgdl + noise
                ss_res = np.sum(noise**2)
                ss_tot = np.sum((y_clean_mgdl - y_clean_mgdl.mean())**2)
                if ss_tot > 0:
                    r2_ceiling = 1 - ss_res / ss_tot
                else:
                    r2_ceiling = 0.0
                r2_trials.append(r2_ceiling)
            noise_ceilings[f'sigma_{sigma}'] = round(np.mean(r2_trials), 4)

        # Theoretical formula: R² ceiling = 1 - sigma²/var(y)
        theoretical_ceilings = {}
        for sigma in noise_levels:
            if y_var > 0:
                theoretical_ceilings[f'sigma_{sigma}'] = round(1 - (sigma**2) / y_var, 4)
            else:
                theoretical_ceilings[f'sigma_{sigma}'] = 0.0

        # Glucose variability (CV)
        glucose_cv = float(np.std(y_clean_mgdl) / np.mean(y_clean_mgdl)) if np.mean(y_clean_mgdl) > 0 else 0.0

        res = {
            'patient': p['name'],
            'r2_achieved': round(r2_achieved, 4),
            'noise_ceilings_empirical': noise_ceilings,
            'noise_ceilings_theoretical': theoretical_ceilings,
            'glucose_std_mgdl': round(float(np.std(y_clean_mgdl)), 1),
            'glucose_cv': round(glucose_cv, 4),
        }

        # Room remaining: ceiling - achieved (at sigma=15 as typical CGM noise)
        ceiling_15 = noise_ceilings.get('sigma_15', 1.0)
        res['room_at_sigma15'] = round(ceiling_15 - r2_achieved, 4)
        res['pct_ceiling_achieved_sigma15'] = round(
            100 * r2_achieved / ceiling_15 if ceiling_15 > 0 else 0, 1)

        results.append(res)
        if detail:
            ceiling_str = ' '.join(f'σ{s}={noise_ceilings[f"sigma_{s}"]:.3f}'
                                   for s in noise_levels)
            print(f"    {p['name']}: achieved={r2_achieved:.4f} "
                  f"ceilings=[{ceiling_str}] "
                  f"room@σ15={res['room_at_sigma15']:.4f} "
                  f"({res['pct_ceiling_achieved_sigma15']:.0f}% of ceiling)")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_achieved': round(np.mean([r['r2_achieved'] for r in results]), 4),
        'mean_glucose_std': round(np.mean([r['glucose_std_mgdl'] for r in results]), 1),
    }
    for sigma in noise_levels:
        key = f'sigma_{sigma}'
        summary[f'mean_ceiling_{key}'] = round(
            np.mean([r['noise_ceilings_empirical'][key] for r in results]), 4)
    summary['mean_room_sigma15'] = round(np.mean([r['room_at_sigma15'] for r in results]), 4)
    summary['mean_pct_ceiling_sigma15'] = round(
        np.mean([r['pct_ceiling_achieved_sigma15'] for r in results]), 1)

    return {
        'status': 'pass',
        'detail': (f'achieved={summary["mean_r2_achieved"]:.4f} | '
                   f'ceilings: σ5={summary.get("mean_ceiling_sigma_5", "N/A")} '
                   f'σ10={summary.get("mean_ceiling_sigma_10", "N/A")} '
                   f'σ15={summary.get("mean_ceiling_sigma_15", "N/A")} '
                   f'σ20={summary.get("mean_ceiling_sigma_20", "N/A")} | '
                   f'room@σ15={summary["mean_room_sigma15"]:.4f} '
                   f'({summary["mean_pct_ceiling_sigma15"]:.0f}% of ceiling)'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1056_stacked_generalization(patients, detail=False):
    """Stacked generalization: level-2 Ridge meta-learner on out-of-fold predictions.

    Train a level-2 Ridge on the out-of-fold predictions of 5 base models:
    1. Ridge (physics only)
    2. Ridge + interaction features
    3. Glucose-only Ridge
    4. Residual CNN on Ridge errors
    5. Ridge + lag-1 residual feature

    Uses 5-fold block CV for base models to generate meta-features.
    """
    N_FOLDS = 5
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 300:
            continue

        combined = np.concatenate([g, phys], axis=2)  # (n, 24, 5)
        n = len(combined)

        # Compute interaction features
        phys_means = np.mean(phys, axis=1)
        s, d, h, net_f = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
        interactions = np.column_stack([s * d, s * h, s * net_f, d * h, d * net_f, h * net_f])

        # Prepare flat features for Ridge variants
        flat = combined.reshape(n, -1)
        flat_int = np.concatenate([flat, interactions], axis=1)
        flat_g = g.reshape(n, -1)

        # Generate out-of-fold predictions for each base model (5-fold block CV)
        fold_size = n // N_FOLDS
        oof_preds = np.zeros((n, 5))  # 5 base models
        oof_valid = np.zeros(n, dtype=bool)

        for fold in range(N_FOLDS):
            val_start = fold * fold_size
            val_end = min((fold + 1) * fold_size, n)
            tr_mask = np.ones(n, dtype=bool)
            tr_mask[val_start:val_end] = False

            Xtr_flat = flat[tr_mask]
            Xvl_flat = flat[val_start:val_end]
            ytr = tgt[tr_mask]
            yvl = tgt[val_start:val_end]

            if len(yvl) < 10:
                continue

            oof_valid[val_start:val_end] = True

            # Model 1: Ridge (physics)
            m1 = Ridge(alpha=1.0)
            m1.fit(Xtr_flat, ytr)
            oof_preds[val_start:val_end, 0] = m1.predict(Xvl_flat)

            # Model 2: Ridge + interactions
            Xtr_int = flat_int[tr_mask]
            Xvl_int = flat_int[val_start:val_end]
            m2 = Ridge(alpha=1.0)
            m2.fit(Xtr_int, ytr)
            oof_preds[val_start:val_end, 1] = m2.predict(Xvl_int)

            # Model 3: Glucose-only Ridge
            Xtr_g = flat_g[tr_mask]
            Xvl_g = flat_g[val_start:val_end]
            m3 = Ridge(alpha=1.0)
            m3.fit(Xtr_g, ytr)
            oof_preds[val_start:val_end, 2] = m3.predict(Xvl_g)

            # Model 4: Residual CNN
            tr_resid = ytr - m1.predict(Xtr_flat)
            vl_resid = yvl - m1.predict(Xvl_flat)
            torch.manual_seed(42)
            cnn = ResidualCNN(in_channels=5)
            tr_X_cnn = combined[tr_mask]
            vl_X_cnn = combined[val_start:val_end]
            cnn, _ = train_cnn(cnn, [tr_X_cnn, tr_resid],
                               [vl_X_cnn, vl_resid], epochs=30)
            cnn_pred = predict_cnn(cnn, vl_X_cnn)
            oof_preds[val_start:val_end, 3] = m1.predict(Xvl_flat) + 0.5 * cnn_pred

            # Model 5: Ridge + lag-1 residual
            tr_resid_full = ytr - m1.predict(Xtr_flat)
            lag1_tr = np.zeros(len(Xtr_flat))
            lag1_tr[1:] = tr_resid_full[:-1]
            Xtr_lag = np.column_stack([Xtr_flat, lag1_tr])

            vl_resid_full = yvl - m1.predict(Xvl_flat)
            lag1_vl = np.zeros(len(Xvl_flat))
            lag1_vl[1:] = vl_resid_full[:-1]
            Xvl_lag = np.column_stack([Xvl_flat, lag1_vl])

            m5 = Ridge(alpha=1.0)
            m5.fit(Xtr_lag, ytr)
            oof_preds[val_start:val_end, 4] = m5.predict(Xvl_lag)

        # Now train/val split for meta-learner
        oof_valid_idx = np.where(oof_valid)[0]
        if len(oof_valid_idx) < 100:
            continue

        meta_X = oof_preds[oof_valid_idx]
        meta_y = tgt[oof_valid_idx]

        # Use last 20% as meta-validation
        meta_split = int(len(meta_X) * 0.8)
        meta_Xtr = meta_X[:meta_split]
        meta_Xvl = meta_X[meta_split:]
        meta_ytr = meta_y[:meta_split]
        meta_yvl = meta_y[meta_split:]

        # Level-2 Ridge
        meta_ridge = Ridge(alpha=0.1)
        meta_ridge.fit(meta_Xtr, meta_ytr)
        meta_pred = meta_ridge.predict(meta_Xvl)
        r2_stacked = r2_score(meta_yvl, meta_pred)

        # Simple average baseline
        avg_pred = np.mean(meta_Xvl, axis=1)
        r2_avg = r2_score(meta_yvl, avg_pred)

        # Best individual model on meta-val
        individual_r2 = {}
        model_names = ['ridge_physics', 'ridge_interactions', 'glucose_only',
                       'residual_cnn', 'ridge_lag1']
        for mi, mname in enumerate(model_names):
            individual_r2[mname] = round(r2_score(meta_yvl, meta_Xvl[:, mi]), 4)

        best_individual = max(individual_r2, key=individual_r2.get)

        # Meta-learner weights
        meta_weights = {mname: round(float(w), 4)
                        for mname, w in zip(model_names, meta_ridge.coef_)}

        res = {
            'patient': p['name'],
            'r2_stacked': round(r2_stacked, 4),
            'r2_simple_avg': round(r2_avg, 4),
            'r2_best_individual': individual_r2[best_individual],
            'best_individual': best_individual,
            'individual_r2': individual_r2,
            'stacking_gain_vs_best': round(r2_stacked - individual_r2[best_individual], 4),
            'stacking_gain_vs_avg': round(r2_stacked - r2_avg, 4),
            'meta_weights': meta_weights,
        }
        results.append(res)
        if detail:
            w_str = ' '.join(f'{k[:6]}={v:.3f}' for k, v in meta_weights.items())
            print(f"    {p['name']}: stacked={r2_stacked:.4f} "
                  f"avg={r2_avg:.4f} best_ind={individual_r2[best_individual]:.4f}"
                  f"({best_individual}) weights=[{w_str}]")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_stacked': round(np.mean([r['r2_stacked'] for r in results]), 4),
        'mean_r2_avg': round(np.mean([r['r2_simple_avg'] for r in results]), 4),
        'mean_r2_best_ind': round(np.mean([r['r2_best_individual'] for r in results]), 4),
        'mean_gain_vs_best': round(np.mean([r['stacking_gain_vs_best'] for r in results]), 4),
        'mean_gain_vs_avg': round(np.mean([r['stacking_gain_vs_avg'] for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'stacked={summary["mean_r2_stacked"]:.4f} '
                   f'avg={summary["mean_r2_avg"]:.4f} '
                   f'best_ind={summary["mean_r2_best_ind"]:.4f} '
                   f'gain_vs_best={summary["mean_gain_vs_best"]:+.4f} '
                   f'gain_vs_avg={summary["mean_gain_vs_avg"]:+.4f}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1057_physics_temporal_derivatives(patients, detail=False):
    """Add first and second temporal derivatives of physics channels as features.

    The rate of change of metabolic fluxes (d_supply/dt, d_demand/dt, etc.) and
    acceleration (d2_supply/dt2, etc.) may carry predictive signal beyond levels.
    Adds 8 extra channels: 4 first derivatives + 4 second derivatives.
    """
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        # Base: glucose + 4 physics channels
        combined_base = np.concatenate([g, phys], axis=2)  # (n, 24, 5)

        # Compute derivatives within each window
        # First derivative: diff along time axis, pad with 0 at start
        phys_d1 = np.diff(phys, axis=1, prepend=phys[:, :1, :])   # (n, 24, 4)
        # Second derivative: diff of first derivative
        phys_d2 = np.diff(phys_d1, axis=1, prepend=phys_d1[:, :1, :])  # (n, 24, 4)

        # Combined features
        combined_d1 = np.concatenate([g, phys, phys_d1], axis=2)        # (n, 24, 9)
        combined_d2 = np.concatenate([g, phys, phys_d2], axis=2)        # (n, 24, 9)
        combined_all = np.concatenate([g, phys, phys_d1, phys_d2], axis=2)  # (n, 24, 13)

        configs = [
            ('base', combined_base),
            ('plus_d1', combined_d1),
            ('plus_d2', combined_d2),
            ('plus_d1_d2', combined_all),
        ]

        r2_results = {}
        for cname, comb in configs:
            train, val = split_chrono([comb, tgt])
            tr_flat = train[0].reshape(len(train[0]), -1)
            vl_flat = val[0].reshape(len(val[0]), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, train[1])
            r2 = r2_score(val[1], ridge.predict(vl_flat))
            r2_results[cname] = round(r2, 4)

        res = {
            'patient': p['name'],
            **r2_results,
            'gain_d1': round(r2_results['plus_d1'] - r2_results['base'], 4),
            'gain_d2': round(r2_results['plus_d2'] - r2_results['base'], 4),
            'gain_d1_d2': round(r2_results['plus_d1_d2'] - r2_results['base'], 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_results['base']:.4f} "
                  f"+d1={r2_results['plus_d1']:.4f}({res['gain_d1']:+.4f}) "
                  f"+d2={r2_results['plus_d2']:.4f}({res['gain_d2']:+.4f}) "
                  f"+both={r2_results['plus_d1_d2']:.4f}({res['gain_d1_d2']:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {}
    for key in ['base', 'plus_d1', 'plus_d2', 'plus_d1_d2']:
        vals = [r[key] for r in results]
        summary[f'mean_{key}'] = round(np.mean(vals), 4)

    for key in ['gain_d1', 'gain_d2', 'gain_d1_d2']:
        vals = [r[key] for r in results]
        summary[f'mean_{key}'] = round(np.mean(vals), 4)
        summary[f'n_positive_{key}'] = sum(1 for v in vals if v > 0)

    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_base"]:.4f} '
                   f'+d1={summary["mean_plus_d1"]:.4f}({summary["mean_gain_d1"]:+.4f}) '
                   f'+d2={summary["mean_plus_d2"]:.4f}({summary["mean_gain_d2"]:+.4f}) '
                   f'+both={summary["mean_plus_d1_d2"]:.4f}({summary["mean_gain_d1_d2"]:+.4f}) '
                   f'positive: d1={summary["n_positive_gain_d1"]}/{len(results)} '
                   f'd2={summary["n_positive_gain_d2"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1058_patient_clustering(patients, detail=False):
    """Cluster patients by difficulty characteristics and train tier-specific models.

    Features for clustering: R² (difficulty), residual autocorrelation,
    missing rate, glucose variability, bolus frequency.
    Then train tier-specific models vs per-patient models.
    """
    # Phase 1: compute difficulty features for each patient
    patient_features = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue

        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)

        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        pred = ridge.predict(vl_flat)
        r2 = r2_score(val[1], pred)

        # Residual autocorrelation (lag-1)
        residuals = val[1] - pred
        resid_centered = residuals - np.mean(residuals)
        var = np.var(resid_centered)
        autocorr_l1 = float(np.mean(resid_centered[1:] * resid_centered[:-1]) / max(var, 1e-10))

        # Missing rate
        glucose_raw = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose_raw).mean())

        # Glucose variability (CV on validation set)
        y_mgdl = val[1] * GLUCOSE_SCALE
        glucose_cv = float(np.std(y_mgdl) / np.mean(y_mgdl)) if np.mean(y_mgdl) > 0 else 0.0

        # Bolus frequency (fraction of non-zero bolus entries)
        if 'bolus' in p['df'].columns:
            bolus_vals = p['df']['bolus'].values
            bolus_freq = float(np.sum(bolus_vals > 0) / max(len(bolus_vals), 1))
        else:
            bolus_freq = 0.0

        patient_features.append({
            'name': p['name'],
            'r2': r2,
            'autocorr_l1': autocorr_l1,
            'missing_rate': missing_rate,
            'glucose_cv': glucose_cv,
            'bolus_freq': bolus_freq,
            'n_windows': len(g),
            'combined': combined,
            'tgt': tgt,
        })

    if len(patient_features) < 3:
        return {'status': 'FAIL', 'detail': 'Insufficient patients for clustering'}

    # Phase 2: cluster by difficulty (simple median split on R²)
    r2_vals = [pf['r2'] for pf in patient_features]
    median_r2 = np.median(r2_vals)

    easy_patients = [pf for pf in patient_features if pf['r2'] >= median_r2]
    hard_patients = [pf for pf in patient_features if pf['r2'] < median_r2]

    # Phase 3: train tier-specific models (pool data within tier)
    results = []

    def train_pooled_model(tier_patients, tier_name):
        """Train a Ridge model on pooled data from all patients in a tier."""
        all_X, all_y = [], []
        for pf in tier_patients:
            train, _ = split_chrono([pf['combined'], pf['tgt']])
            all_X.append(train[0])
            all_y.append(train[1])
        pooled_X = np.concatenate(all_X).reshape(sum(len(x) for x in all_X), -1)
        pooled_y = np.concatenate(all_y)
        pooled_ridge = Ridge(alpha=1.0)
        pooled_ridge.fit(pooled_X, pooled_y)
        return pooled_ridge

    # Train tier-specific models
    if easy_patients:
        easy_model = train_pooled_model(easy_patients, 'easy')
    if hard_patients:
        hard_model = train_pooled_model(hard_patients, 'hard')

    # Also train a global model on all patients
    global_model = train_pooled_model(patient_features, 'global')

    for pf in patient_features:
        _, val = split_chrono([pf['combined'], pf['tgt']])
        vl_flat = val[0].reshape(len(val[0]), -1)
        y_val = val[1]

        # Per-patient model
        train_data, _ = split_chrono([pf['combined'], pf['tgt']])
        tr_flat = train_data[0].reshape(len(train_data[0]), -1)
        per_patient_ridge = Ridge(alpha=1.0)
        per_patient_ridge.fit(tr_flat, train_data[1])
        r2_per_patient = r2_score(y_val, per_patient_ridge.predict(vl_flat))

        # Tier model
        tier = 'easy' if pf['r2'] >= median_r2 else 'hard'
        tier_model = easy_model if tier == 'easy' else hard_model
        r2_tier = r2_score(y_val, tier_model.predict(vl_flat))

        # Global model
        r2_global = r2_score(y_val, global_model.predict(vl_flat))

        res = {
            'patient': pf['name'],
            'tier': tier,
            'r2_per_patient': round(r2_per_patient, 4),
            'r2_tier': round(r2_tier, 4),
            'r2_global': round(r2_global, 4),
            'tier_vs_per_patient': round(r2_tier - r2_per_patient, 4),
            'global_vs_per_patient': round(r2_global - r2_per_patient, 4),
            'difficulty_features': {
                'r2': round(pf['r2'], 4),
                'autocorr_l1': round(pf['autocorr_l1'], 4),
                'missing_rate': round(pf['missing_rate'], 4),
                'glucose_cv': round(pf['glucose_cv'], 4),
                'bolus_freq': round(pf['bolus_freq'], 4),
            },
        }
        results.append(res)
        if detail:
            print(f"    {pf['name']}: tier={tier} per_patient={r2_per_patient:.4f} "
                  f"tier_model={r2_tier:.4f}({r2_tier-r2_per_patient:+.4f}) "
                  f"global={r2_global:.4f}({r2_global-r2_per_patient:+.4f})")

    summary = {
        'n_easy': len(easy_patients),
        'n_hard': len(hard_patients),
        'median_r2_threshold': round(median_r2, 4),
        'mean_r2_per_patient': round(np.mean([r['r2_per_patient'] for r in results]), 4),
        'mean_r2_tier': round(np.mean([r['r2_tier'] for r in results]), 4),
        'mean_r2_global': round(np.mean([r['r2_global'] for r in results]), 4),
        'mean_tier_gain': round(np.mean([r['tier_vs_per_patient'] for r in results]), 4),
        'mean_global_gain': round(np.mean([r['global_vs_per_patient'] for r in results]), 4),
        'n_tier_helps': sum(1 for r in results if r['tier_vs_per_patient'] > 0),
    }
    return {
        'status': 'pass',
        'detail': (f'per_patient={summary["mean_r2_per_patient"]:.4f} '
                   f'tier={summary["mean_r2_tier"]:.4f}({summary["mean_tier_gain"]:+.4f}) '
                   f'global={summary["mean_r2_global"]:.4f}({summary["mean_global_gain"]:+.4f}) '
                   f'tier_helps={summary["n_tier_helps"]}/{len(results)} '
                   f'(easy={summary["n_easy"]}, hard={summary["n_hard"]})'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1059_lagged_physics_features(patients, detail=False):
    """Lagged physics features: summary statistics from preceding 4h and 8h windows.

    Instead of using only the current 2h window of physics channels, also include
    mean, std, and slope of physics channels from the preceding 4h and 8h windows.
    This gives longer-term metabolic context without curse of dimensionality.
    """
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        glucose = p['df']['glucose'].values / GLUCOSE_SCALE

        supply = sd['supply'] / 20.0
        demand = sd['demand'] / 20.0
        hepatic = sd['hepatic'] / 5.0
        net = sd['net'] / 20.0

        N = len(glucose)
        total = WINDOW + HORIZON
        lookback_4h = 48  # 4 hours at 5-min
        lookback_8h = 96  # 8 hours at 5-min
        max_lookback = lookback_8h

        g_wins, phys_wins, tgts = [], [], []
        lag_4h_feats, lag_8h_feats = [], []

        channels = [supply, demand, hepatic, net]
        channel_names = ['supply', 'demand', 'hepatic', 'net']

        for i in range(max_lookback, N - total, STRIDE):
            g = glucose[i:i + WINDOW]
            if np.isnan(g).mean() > 0.2:
                continue
            target = glucose[i + WINDOW + HORIZON - 1]
            if np.isnan(target):
                continue
            g = np.nan_to_num(g, nan=np.nanmean(g) if np.any(~np.isnan(g)) else 0.4)

            # Current window physics
            phys = np.stack([ch[i:i + WINDOW] for ch in channels], axis=1)

            # 4h lookback summary statistics
            feat_4h = []
            for ch in channels:
                seg = ch[i - lookback_4h:i]
                seg = np.nan_to_num(seg, nan=0.0)
                feat_4h.extend([
                    np.mean(seg),
                    np.std(seg),
                    np.polyfit(np.arange(len(seg)), seg, 1)[0] if len(seg) > 1 else 0.0,
                ])

            # 8h lookback summary statistics
            feat_8h = []
            for ch in channels:
                seg = ch[i - lookback_8h:i]
                seg = np.nan_to_num(seg, nan=0.0)
                feat_8h.extend([
                    np.mean(seg),
                    np.std(seg),
                    np.polyfit(np.arange(len(seg)), seg, 1)[0] if len(seg) > 1 else 0.0,
                ])

            g_wins.append(g.reshape(-1, 1))
            phys_wins.append(phys)
            tgts.append(target)
            lag_4h_feats.append(feat_4h)
            lag_8h_feats.append(feat_8h)

        if len(g_wins) < 200:
            continue

        g_arr = np.array(g_wins)
        phys_arr = np.array(phys_wins)
        tgt_arr = np.array(tgts)
        lag_4h_arr = np.array(lag_4h_feats)  # (n, 12): 4 channels × 3 stats
        lag_8h_arr = np.array(lag_8h_feats)  # (n, 12)

        combined = np.concatenate([g_arr, phys_arr], axis=2)

        # Configs to test
        train_c, val_c = split_chrono([combined, tgt_arr, lag_4h_arr, lag_8h_arr])

        tr_flat = train_c[0].reshape(len(train_c[0]), -1)
        vl_flat = val_c[0].reshape(len(val_c[0]), -1)

        # 1. Base (2h window only)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(tr_flat, train_c[1])
        r2_base = r2_score(val_c[1], ridge_base.predict(vl_flat))

        # 2. Base + 4h lag
        tr_flat_4h = np.concatenate([tr_flat, train_c[2]], axis=1)
        vl_flat_4h = np.concatenate([vl_flat, val_c[2]], axis=1)
        ridge_4h = Ridge(alpha=1.0)
        ridge_4h.fit(tr_flat_4h, train_c[1])
        r2_4h = r2_score(val_c[1], ridge_4h.predict(vl_flat_4h))

        # 3. Base + 8h lag
        tr_flat_8h = np.concatenate([tr_flat, train_c[3]], axis=1)
        vl_flat_8h = np.concatenate([vl_flat, val_c[3]], axis=1)
        ridge_8h = Ridge(alpha=1.0)
        ridge_8h.fit(tr_flat_8h, train_c[1])
        r2_8h = r2_score(val_c[1], ridge_8h.predict(vl_flat_8h))

        # 4. Base + 4h + 8h lag
        tr_flat_all = np.concatenate([tr_flat, train_c[2], train_c[3]], axis=1)
        vl_flat_all = np.concatenate([vl_flat, val_c[2], val_c[3]], axis=1)
        ridge_all = Ridge(alpha=1.0)
        ridge_all.fit(tr_flat_all, train_c[1])
        r2_all = r2_score(val_c[1], ridge_all.predict(vl_flat_all))

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_plus_4h': round(r2_4h, 4),
            'r2_plus_8h': round(r2_8h, 4),
            'r2_plus_4h_8h': round(r2_all, 4),
            'gain_4h': round(r2_4h - r2_base, 4),
            'gain_8h': round(r2_8h - r2_base, 4),
            'gain_4h_8h': round(r2_all - r2_base, 4),
            'n_windows': len(g_wins),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} "
                  f"+4h={r2_4h:.4f}({r2_4h-r2_base:+.4f}) "
                  f"+8h={r2_8h:.4f}({r2_8h-r2_base:+.4f}) "
                  f"+both={r2_all:.4f}({r2_all-r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {}
    for key in ['r2_base', 'r2_plus_4h', 'r2_plus_8h', 'r2_plus_4h_8h']:
        vals = [r[key] for r in results]
        summary[f'mean_{key}'] = round(np.mean(vals), 4)

    for key in ['gain_4h', 'gain_8h', 'gain_4h_8h']:
        vals = [r[key] for r in results]
        summary[f'mean_{key}'] = round(np.mean(vals), 4)
        summary[f'n_positive_{key}'] = sum(1 for v in vals if v > 0)

    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'+4h={summary["mean_r2_plus_4h"]:.4f}({summary["mean_gain_4h"]:+.4f}) '
                   f'+8h={summary["mean_r2_plus_8h"]:.4f}({summary["mean_gain_8h"]:+.4f}) '
                   f'+both={summary["mean_r2_plus_4h_8h"]:.4f}({summary["mean_gain_4h_8h"]:+.4f}) '
                   f'positive_4h={summary["n_positive_gain_4h"]}/{len(results)} '
                   f'positive_8h={summary["n_positive_gain_8h"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1060_definitive_grand_benchmark(patients, detail=False):
    """Definitive grand benchmark using block CV (3-fold temporal blocks).

    Full pipeline: glucose-only -> Ridge+physics+interactions -> Residual CNN -> Stacked.
    Excludes patient h. Reports R², MAE, Clarke Error Grid for each patient and overall.
    This is the authoritative performance number.
    """
    N_FOLDS = 3
    results = []
    excluded = []

    for p in patients:
        glucose_raw = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose_raw).mean())

        # Exclude patient h (excessive missing data)
        if p['name'] == 'h':
            excluded.append({'patient': p['name'], 'reason': 'excluded_by_protocol',
                             'missing_rate': round(missing_rate, 4)})
            if detail:
                print(f"    {p['name']}: EXCLUDED (protocol, missing={missing_rate:.1%})")
            continue

        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            excluded.append({'patient': p['name'], 'reason': 'insufficient_windows',
                             'n_windows': len(g)})
            if detail:
                print(f"    {p['name']}: EXCLUDED (insufficient windows={len(g)})")
            continue

        combined = np.concatenate([g, phys], axis=2)  # (n, 24, 5)

        # Compute interaction features
        phys_means = np.mean(phys, axis=1)
        s, d, h_ch, net_f = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
        interactions = np.column_stack([
            s * d, s * h_ch, s * net_f, d * h_ch, d * net_f, h_ch * net_f,
        ])

        flat = combined.reshape(len(combined), -1)
        flat_int = np.concatenate([flat, interactions], axis=1)
        flat_g = g.reshape(len(g), -1)

        n = len(combined)
        fold_size = n // N_FOLDS

        fold_results = {
            'r2_glucose_only': [],
            'r2_ridge_physics': [],
            'r2_ridge_interactions': [],
            'r2_residual_cnn': [],
            'r2_stacked': [],
            'mae_mg_dl': [],
            'clarke_A_pct': [],
            'clarke_AB_pct': [],
        }

        for fold in range(N_FOLDS):
            val_start = fold * fold_size
            val_end = min((fold + 1) * fold_size, n)
            tr_mask = np.ones(n, dtype=bool)
            tr_mask[val_start:val_end] = False

            tr_X = combined[tr_mask]
            tr_y = tgt[tr_mask]
            vl_X = combined[val_start:val_end]
            vl_y = tgt[val_start:val_end]

            if len(vl_X) < 10:
                continue

            tr_flat = flat[tr_mask]
            vl_flat = flat[val_start:val_end]
            tr_flat_int = flat_int[tr_mask]
            vl_flat_int = flat_int[val_start:val_end]

            # Stage 0: Glucose-only
            tr_g = flat_g[tr_mask]
            vl_g = flat_g[val_start:val_end]
            ridge_g = Ridge(alpha=1.0)
            ridge_g.fit(tr_g, tr_y)
            r2_g = r2_score(vl_y, ridge_g.predict(vl_g))
            fold_results['r2_glucose_only'].append(r2_g)

            # Stage 1: Ridge + physics
            ridge_p = Ridge(alpha=1.0)
            ridge_p.fit(tr_flat, tr_y)
            pred_p = ridge_p.predict(vl_flat)
            r2_p = r2_score(vl_y, pred_p)
            fold_results['r2_ridge_physics'].append(r2_p)

            # Stage 2: Ridge + physics + interactions
            ridge_pi = Ridge(alpha=1.0)
            ridge_pi.fit(tr_flat_int, tr_y)
            pred_pi = ridge_pi.predict(vl_flat_int)
            r2_pi = r2_score(vl_y, pred_pi)
            fold_results['r2_ridge_interactions'].append(r2_pi)

            # Stage 3: Residual CNN on Ridge+interactions residuals
            tr_resid = tr_y - ridge_pi.predict(tr_flat_int)
            vl_resid = vl_y - pred_pi

            torch.manual_seed(42)
            cnn = ResidualCNN(in_channels=5)
            cnn, _ = train_cnn(cnn, [tr_X, tr_resid], [vl_X, vl_resid], epochs=40)
            cnn_pred = predict_cnn(cnn, vl_X)
            pred_cnn = pred_pi + 0.5 * cnn_pred
            r2_cnn = r2_score(vl_y, pred_cnn)
            fold_results['r2_residual_cnn'].append(r2_cnn)

            # Stage 4: Simple stack (average of Ridge+int and ResidualCNN predictions)
            # Two additional seed runs for ensemble
            ensemble_preds = [pred_cnn]
            for seed in [1, 2]:
                torch.manual_seed(seed * 77)
                m_s = ResidualCNN(in_channels=5)
                m_s, _ = train_cnn(m_s, [tr_X, tr_resid], [vl_X, vl_resid], epochs=40)
                cnn_s = predict_cnn(m_s, vl_X)
                ensemble_preds.append(pred_pi + 0.5 * cnn_s)

            stacked_pred = np.mean(ensemble_preds, axis=0)
            r2_stacked = r2_score(vl_y, stacked_pred)
            fold_results['r2_stacked'].append(r2_stacked)

            # MAE in mg/dL
            mae = float(np.mean(np.abs(stacked_pred - vl_y)) * GLUCOSE_SCALE)
            fold_results['mae_mg_dl'].append(mae)

            # Clarke Error Grid
            ref_mgdl = vl_y * GLUCOSE_SCALE
            pred_mgdl = stacked_pred * GLUCOSE_SCALE
            _, pcts = compute_clarke_zones(ref_mgdl, pred_mgdl)
            fold_results['clarke_A_pct'].append(pcts['A'])
            fold_results['clarke_AB_pct'].append(pcts['A'] + pcts['B'])

        if not fold_results['r2_stacked']:
            excluded.append({'patient': p['name'], 'reason': 'no_valid_folds'})
            continue

        res = {'patient': p['name'], 'missing_rate': round(missing_rate, 4)}
        for key, vals in fold_results.items():
            res[f'{key}_mean'] = round(np.mean(vals), 4)
            res[f'{key}_std'] = round(np.std(vals), 4)
        res['n_folds'] = len(fold_results['r2_stacked'])
        res['physics_lift'] = round(
            res['r2_ridge_physics_mean'] - res['r2_glucose_only_mean'], 4)
        res['interaction_lift'] = round(
            res['r2_ridge_interactions_mean'] - res['r2_ridge_physics_mean'], 4)
        res['cnn_lift'] = round(
            res['r2_residual_cnn_mean'] - res['r2_ridge_interactions_mean'], 4)
        res['stacking_lift'] = round(
            res['r2_stacked_mean'] - res['r2_residual_cnn_mean'], 4)

        results.append(res)
        if detail:
            print(f"    {p['name']}: g_only={res['r2_glucose_only_mean']:.4f} "
                  f"ridge+phys={res['r2_ridge_physics_mean']:.4f} "
                  f"+int={res['r2_ridge_interactions_mean']:.4f} "
                  f"+cnn={res['r2_residual_cnn_mean']:.4f} "
                  f"stacked={res['r2_stacked_mean']:.4f} "
                  f"mae={res['mae_mg_dl_mean']:.1f}mg/dL "
                  f"clarke_A={res['clarke_A_pct_mean']:.1f}%")

    if not results:
        return {'status': 'FAIL', 'detail': 'No patients completed the benchmark'}

    # Grand summary
    summary = {}
    for key in ['r2_glucose_only_mean', 'r2_ridge_physics_mean',
                'r2_ridge_interactions_mean', 'r2_residual_cnn_mean',
                'r2_stacked_mean', 'mae_mg_dl_mean',
                'clarke_A_pct_mean', 'clarke_AB_pct_mean']:
        vals = [r[key] for r in results if key in r]
        if vals:
            summary[key] = round(np.mean(vals), 4)

    summary['physics_lift'] = round(np.mean([r['physics_lift'] for r in results]), 4)
    summary['interaction_lift'] = round(np.mean([r['interaction_lift'] for r in results]), 4)
    summary['cnn_lift'] = round(np.mean([r['cnn_lift'] for r in results]), 4)
    summary['stacking_lift'] = round(np.mean([r['stacking_lift'] for r in results]), 4)
    summary['n_included'] = len(results)
    summary['n_excluded'] = len(excluded)

    return {
        'status': 'pass',
        'detail': (f'pipeline ({summary["n_included"]} pts, {summary["n_excluded"]} excl, '
                   f'{N_FOLDS}-fold block CV): '
                   f'g_only={summary.get("r2_glucose_only_mean", "N/A")} -> '
                   f'ridge+phys={summary.get("r2_ridge_physics_mean", "N/A")} -> '
                   f'+int={summary.get("r2_ridge_interactions_mean", "N/A")} -> '
                   f'+cnn={summary.get("r2_residual_cnn_mean", "N/A")} -> '
                   f'stacked={summary.get("r2_stacked_mean", "N/A")} '
                   f'(mae={summary.get("mae_mg_dl_mean", "N/A")}mg/dL, '
                   f'clarke_A={summary.get("clarke_A_pct_mean", "N/A")}%)'),
        'results': {'per_patient': results, 'excluded': excluded, 'summary': summary},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1051', 'Autoregressive Residual Features', exp_1051_autoregressive_residuals),
    ('EXP-1052', 'Interaction + Residual CNN Stack', exp_1052_interaction_residual_cnn_stack),
    ('EXP-1053', 'Hypo Class Rebalancing', exp_1053_hypo_class_rebalancing),
    ('EXP-1054', 'Per-Patient Optimal Window', exp_1054_per_patient_optimal_window),
    ('EXP-1055', 'Noise Ceiling Analysis', exp_1055_noise_ceiling_analysis),
    ('EXP-1056', 'Stacked Generalization Meta-Learner', exp_1056_stacked_generalization),
    ('EXP-1057', 'Physics Temporal Derivatives', exp_1057_physics_temporal_derivatives),
    ('EXP-1058', 'Patient Clustering by Difficulty', exp_1058_patient_clustering),
    ('EXP-1059', 'Lagged Physics Features', exp_1059_lagged_physics_features),
    ('EXP-1060', 'Definitive Grand Benchmark Block CV', exp_1060_definitive_grand_benchmark),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1051-1060: Advanced residual models, stacking, and clinical optimization')
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
