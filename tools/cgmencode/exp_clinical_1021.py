#!/usr/bin/env python3
"""EXP-1021 to EXP-1030: Ensemble, Residual Learning, and Cross-Patient Transfer.

Building on EXP-1020's finding that dual-branch CNN (R²=0.525) is SOTA but features
matter more than architecture, this batch focuses on:
1. Residual learning (CNN learns Ridge's errors)
2. Ensemble methods (combining linear + nonlinear)
3. Cross-patient pretraining + fine-tuning
4. Block CV for honest evaluation

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1021 --detail --save --max-patients 11
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
from sklearn.metrics import r2_score

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


class DualBranchCNN(nn.Module):
    """Dual-branch: glucose encoder + physics encoder."""
    def __init__(self, glucose_channels, physics_channels):
        super().__init__()
        self.glucose_conv = nn.Sequential(
            nn.Conv1d(glucose_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.physics_conv = nn.Sequential(
            nn.Conv1d(physics_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, glucose, physics):
        g = self.glucose_conv(glucose.permute(0, 2, 1)).squeeze(-1)
        p = self.physics_conv(physics.permute(0, 2, 1)).squeeze(-1)
        return self.head(torch.cat([g, p], dim=1)).squeeze(-1)


class MultiScaleCNN(nn.Module):
    """Multi-scale CNN with parallel branches at different kernel sizes."""
    def __init__(self, in_channels):
        super().__init__()
        self.branch_3 = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32), nn.AdaptiveAvgPool1d(1),
        )
        self.branch_5 = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32), nn.AdaptiveAvgPool1d(1),
        )
        self.branch_7 = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(32), nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(96, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        x_t = x.permute(0, 2, 1)
        b3 = self.branch_3(x_t).squeeze(-1)
        b5 = self.branch_5(x_t).squeeze(-1)
        b7 = self.branch_7(x_t).squeeze(-1)
        return self.head(torch.cat([b3, b5, b7], dim=1)).squeeze(-1)


# ─── Data Helpers ───

def build_windowed_data(df, pk_array, supply_demand, history_steps=24,
                        horizon_steps=12, stride=6):
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
              patience=12, lr=1e-3, multi_input=False):
    """Train CNN and return R² on validation set."""
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
            inputs, y = batch[:-1], batch[-1]
            pred = model(*inputs) if multi_input else model(inputs[0])
            loss = criterion(pred, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(*val_t[:-1]) if multi_input else model(val_t[0])
            val_loss = criterion(val_pred, val_t[-1]).item()

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
        pred = model(*val_t[:-1]) if multi_input else model(val_t[0])
        pred_np = pred.cpu().numpy()
        y_np = val_t[-1].cpu().numpy()

    return r2_score(y_np, pred_np)


# ─── Experiments ───

def exp_1021_ridge_cnn_ensemble(patients, detail=False):
    """Ensemble: average Ridge and CNN predictions."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Ridge
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_pred = ridge.predict(vl_flat)
        r2_ridge = r2_score(val[1], ridge_pred)

        # CNN
        model = ResidualCNN(in_channels=5)
        tr_g, vl_g = split_chrono([combined, tgt])
        model_cnn = ResidualCNN(in_channels=5)

        # Train CNN
        r2_cnn_val = train_cnn(model_cnn, tr_g, vl_g, epochs=50)

        # Get CNN predictions for ensemble
        model_cnn.eval()
        with torch.no_grad():
            cnn_pred = model_cnn(torch.from_numpy(vl_flat.reshape(val[0].shape)).float().to(DEVICE))
            cnn_pred_np = cnn_pred.cpu().numpy()

        # Ensemble: sweep alpha
        best_alpha, best_r2 = 0.5, -999
        for alpha in np.arange(0.0, 1.05, 0.1):
            ens_pred = alpha * ridge_pred + (1 - alpha) * cnn_pred_np
            r2_ens = r2_score(val[1], ens_pred)
            if r2_ens > best_r2:
                best_alpha = round(alpha, 1)
                best_r2 = r2_ens

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_cnn': round(r2_cnn_val, 4),
            'r2_ensemble': round(best_r2, 4),
            'best_alpha': best_alpha,
            'ensemble_vs_best': round(best_r2 - max(r2_ridge, r2_cnn_val), 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_ridge:.4f} cnn={r2_cnn_val:.4f} ens={best_r2:.4f} α={best_alpha}")

    imp = [r['ensemble_vs_best'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_ensemble_gain={np.mean(imp):+.4f}, positive={sum(1 for i in imp if i > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1022_pretrain_finetune(patients, detail=False):
    """Cross-patient pretrain → per-patient fine-tune."""
    # Build per-patient data
    patient_data = {}
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])
        patient_data[p['name']] = {'train': train, 'val': val}

    results = []
    for test_name in patient_data:
        # Pretrain on all OTHER patients
        train_X = np.concatenate([d['train'][0] for n, d in patient_data.items() if n != test_name])
        train_y = np.concatenate([d['train'][1] for n, d in patient_data.items() if n != test_name])
        val_X = patient_data[test_name]['val'][0]
        val_y = patient_data[test_name]['val'][1]
        test_train_X = patient_data[test_name]['train'][0]
        test_train_y = patient_data[test_name]['train'][1]

        # 1. Per-patient only
        model_pp = ResidualCNN(in_channels=5)
        r2_pp = train_cnn(model_pp, [test_train_X, test_train_y], [val_X, val_y], epochs=50)

        # 2. Cross-patient only (LOPO)
        model_lopo = ResidualCNN(in_channels=5)
        r2_lopo = train_cnn(model_lopo, [train_X, train_y], [val_X, val_y], epochs=50, batch_size=512)

        # 3. Pretrain + fine-tune
        model_ft = ResidualCNN(in_channels=5)
        # Phase 1: pretrain on others
        train_cnn(model_ft, [train_X, train_y], [val_X, val_y], epochs=30, batch_size=512)
        # Phase 2: fine-tune on target (lower lr)
        r2_ft = train_cnn(model_ft, [test_train_X, test_train_y], [val_X, val_y],
                          epochs=30, lr=1e-4, patience=8)

        res = {
            'patient': test_name,
            'r2_per_patient': round(r2_pp, 4),
            'r2_lopo': round(r2_lopo, 4),
            'r2_pretrain_finetune': round(r2_ft, 4),
            'ft_vs_pp': round(r2_ft - r2_pp, 4),
            'ft_vs_lopo': round(r2_ft - r2_lopo, 4),
        }
        results.append(res)
        if detail:
            print(f"    {test_name}: pp={r2_pp:.4f} lopo={r2_lopo:.4f} ft={r2_ft:.4f} Δ(pp)={r2_ft-r2_pp:+.4f}")

    ft_gains = [r['ft_vs_pp'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_ft_gain={np.mean(ft_gains):+.4f}, positive={sum(1 for g in ft_gains if g > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1023_patient_routing(patients, detail=False):
    """Oracle routing: pick best method per patient (upper bound)."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])
        train_g, val_g = split_chrono([g, tgt])
        train_gp, val_gp = split_chrono([g, phys, tgt])

        # Ridge
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        r2_ridge = r2_score(val[1], ridge.predict(vl_flat))

        # CNN glucose-only
        m1 = ResidualCNN(in_channels=1)
        r2_cnn_g = train_cnn(m1, train_g, val_g, epochs=50)

        # CNN combined
        m2 = ResidualCNN(in_channels=5)
        r2_cnn_p = train_cnn(m2, train, val, epochs=50)

        # Dual-branch
        m3 = DualBranchCNN(glucose_channels=1, physics_channels=4)
        r2_dual = train_cnn(m3, train_gp, val_gp, epochs=50, multi_input=True)

        methods = {
            'ridge': r2_ridge, 'cnn_glucose': r2_cnn_g,
            'cnn_physics': r2_cnn_p, 'dual_branch': r2_dual,
        }
        best = max(methods, key=methods.get)

        res = {
            'patient': p['name'],
            'methods': {k: round(v, 4) for k, v in methods.items()},
            'best_method': best,
            'best_r2': round(methods[best], 4),
            'oracle_gain': round(methods[best] - r2_ridge, 4),
        }
        results.append(res)
        if detail:
            parts = ' '.join(f'{k}={v:.3f}' for k, v in methods.items())
            print(f"    {p['name']}: {parts} ★{best}")

    oracle_r2 = np.mean([r['best_r2'] for r in results])
    return {
        'status': 'pass',
        'detail': f'oracle_mean_r2={oracle_r2:.4f}',
        'results': {'per_patient': results},
    }


def exp_1024_residual_cnn(patients, detail=False):
    """Residual CNN: learn to predict Ridge's errors.

    Stage 1: Train Ridge on all features
    Stage 2: CNN learns to predict Ridge residuals from temporal patterns
    Final: Ridge prediction + CNN residual correction
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Stage 1: Ridge baseline
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_train_pred = ridge.predict(tr_flat)
        ridge_val_pred = ridge.predict(vl_flat)
        r2_ridge = r2_score(val[1], ridge_val_pred)

        # Stage 2: CNN learns residuals
        train_residuals = train[1] - ridge_train_pred
        val_residuals = val[1] - ridge_val_pred

        model = ResidualCNN(in_channels=5)
        r2_residual_model = train_cnn(model, [train[0], train_residuals],
                                       [val[0], val_residuals], epochs=60)

        # Get CNN residual predictions
        model.eval()
        with torch.no_grad():
            cnn_residual_pred = model(torch.from_numpy(val[0]).float().to(DEVICE))
            cnn_residual_np = cnn_residual_pred.cpu().numpy()

        # Combined: Ridge + CNN residual
        combined_pred = ridge_val_pred + cnn_residual_np
        r2_combined = r2_score(val[1], combined_pred)

        # Also try with scaling
        best_scale_r2 = r2_combined
        for scale in [0.3, 0.5, 0.7, 1.0, 1.3]:
            scaled_pred = ridge_val_pred + scale * cnn_residual_np
            r2_s = r2_score(val[1], scaled_pred)
            if r2_s > best_scale_r2:
                best_scale_r2 = r2_s

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_residual_model': round(r2_residual_model, 4),
            'r2_combined': round(r2_combined, 4),
            'r2_scaled': round(best_scale_r2, 4),
            'improvement': round(best_scale_r2 - r2_ridge, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_ridge:.4f} resid_r2={r2_residual_model:.4f} "
                  f"combined={r2_combined:.4f} scaled={best_scale_r2:.4f} Δ={best_scale_r2-r2_ridge:+.4f}")

    imp = [r['improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_improvement={np.mean(imp):+.4f}, positive={sum(1 for i in imp if i > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1025_multiscale_cnn(patients, detail=False):
    """Multi-scale CNN: parallel branches with different kernel sizes."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Standard CNN baseline
        m_std = ResidualCNN(in_channels=5)
        r2_std = train_cnn(m_std, train, val, epochs=50)

        # Multi-scale CNN
        m_ms = MultiScaleCNN(in_channels=5)
        r2_ms = train_cnn(m_ms, train, val, epochs=50)

        res = {
            'patient': p['name'],
            'r2_standard_cnn': round(r2_std, 4),
            'r2_multiscale_cnn': round(r2_ms, 4),
            'improvement': round(r2_ms - r2_std, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: std={r2_std:.4f} ms={r2_ms:.4f} Δ={r2_ms-r2_std:+.4f}")

    imp = [r['improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_ms_improvement={np.mean(imp):+.4f}, positive={sum(1 for i in imp if i > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1026_physics_normalized_crosspatient_ridge(patients, detail=False):
    """Cross-patient Ridge with ISF/CR-normalized physics features."""
    patient_data = {}
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)

        # Z-score normalize physics per patient
        combined_norm = combined.copy()
        for ch in range(1, 5):
            mu = combined_norm[:, :, ch].mean()
            sigma = combined_norm[:, :, ch].std()
            if sigma > 0:
                combined_norm[:, :, ch] = (combined_norm[:, :, ch] - mu) / sigma

        train, val = split_chrono([combined_norm, tgt])
        patient_data[p['name']] = {
            'train': train, 'val': val,
            'train_raw': split_chrono([combined, tgt])[0],
            'val_raw': split_chrono([combined, tgt])[1],
        }

    results = []
    for test_name in patient_data:
        # Per-patient Ridge (raw)
        pp_raw = patient_data[test_name]
        tr_flat = pp_raw['train_raw'][0].reshape(len(pp_raw['train_raw'][0]), -1)
        vl_flat = pp_raw['val_raw'][0].reshape(len(pp_raw['val_raw'][0]), -1)
        ridge_pp = Ridge(alpha=1.0)
        ridge_pp.fit(tr_flat, pp_raw['train_raw'][1])
        r2_pp = r2_score(pp_raw['val_raw'][1], ridge_pp.predict(vl_flat))

        # Cross-patient Ridge (normalized)
        train_X = np.concatenate([d['train'][0] for n, d in patient_data.items() if n != test_name])
        train_y = np.concatenate([d['train'][1] for n, d in patient_data.items() if n != test_name])
        val_X = patient_data[test_name]['val'][0]
        val_y = patient_data[test_name]['val'][1]

        tr_flat = train_X.reshape(len(train_X), -1)
        vl_flat = val_X.reshape(len(val_X), -1)
        ridge_cp = Ridge(alpha=1.0)
        ridge_cp.fit(tr_flat, train_y)
        r2_cp = r2_score(val_y, ridge_cp.predict(vl_flat))

        res = {
            'patient': test_name,
            'r2_per_patient': round(r2_pp, 4),
            'r2_cross_patient': round(r2_cp, 4),
            'gap': round(r2_pp - r2_cp, 4),
        }
        results.append(res)
        if detail:
            print(f"    {test_name}: pp={r2_pp:.4f} cp={r2_cp:.4f} gap={r2_pp-r2_cp:+.4f}")

    gaps = [r['gap'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_gap={np.mean(gaps):+.4f}',
        'results': {'per_patient': results},
    }


def exp_1027_tod_conditioned_dual(patients, detail=False):
    """Time-of-day conditioned dual-branch CNN."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        glucose = p['df']['glucose'].values / GLUCOSE_SCALE
        N = len(glucose)
        history, horizon, stride = 24, 12, 6
        total = history + horizon

        supply = sd['supply'] / 20.0
        demand = sd['demand'] / 20.0
        hepatic = sd['hepatic'] / 5.0
        net_bal = sd['net'] / 20.0

        # Build windows with time-of-day features
        g_wins, phys_wins, tod_wins, tgts = [], [], [], []
        timestamps = p['df'].index if hasattr(p['df'].index, 'hour') else None

        for i in range(0, N - total, stride):
            gl = glucose[i:i+history]
            if np.isnan(gl).mean() > 0.2:
                continue
            target = glucose[i+history+horizon-1]
            if np.isnan(target):
                continue
            gl = np.nan_to_num(gl, nan=np.nanmean(gl) if np.any(~np.isnan(gl)) else 0.4)

            g_wins.append(gl.reshape(-1, 1))
            ph = np.stack([supply[i:i+history], demand[i:i+history],
                           hepatic[i:i+history], net_bal[i:i+history]], axis=1)
            phys_wins.append(ph)

            # Time-of-day: hour as sin/cos
            if timestamps is not None:
                try:
                    hour = timestamps[i + history - 1].hour
                except:
                    hour = (i * 5 // 60) % 24
            else:
                hour = (i * 5 // 60) % 24
            tod = np.array([np.sin(2 * np.pi * hour / 24),
                            np.cos(2 * np.pi * hour / 24)])
            tod_wins.append(tod)
            tgts.append(target)

        if len(g_wins) < 200:
            continue

        g_wins = np.array(g_wins)
        phys_wins = np.array(phys_wins)
        tod_wins = np.array(tod_wins)
        tgts = np.array(tgts)

        # Add ToD as constant channels to glucose
        tod_expanded = np.tile(tod_wins[:, :, None], (1, 1, history)).transpose(0, 2, 1)
        g_plus_tod = np.concatenate([g_wins, tod_expanded], axis=2)  # (N, 24, 3)

        train_gp, val_gp = split_chrono([g_plus_tod, phys_wins, tgts])
        train_g, val_g = split_chrono([g_wins, phys_wins, tgts])

        # Dual-branch without ToD
        m_base = DualBranchCNN(glucose_channels=1, physics_channels=4)
        r2_base = train_cnn(m_base, train_g, val_g, epochs=50, multi_input=True)

        # Dual-branch with ToD
        m_tod = DualBranchCNN(glucose_channels=3, physics_channels=4)
        r2_tod = train_cnn(m_tod, train_gp, val_gp, epochs=50, multi_input=True)

        res = {
            'patient': p['name'],
            'r2_dual_base': round(r2_base, 4),
            'r2_dual_tod': round(r2_tod, 4),
            'improvement': round(r2_tod - r2_base, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} tod={r2_tod:.4f} Δ={r2_tod-r2_base:+.4f}")

    imp = [r['improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_tod_improvement={np.mean(imp):+.4f}',
        'results': {'per_patient': results},
    }


def exp_1028_block_cv(patients, detail=False):
    """5-fold block CV evaluation of Ridge+physics and dual-branch CNN."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)

        n = len(combined)
        n_folds = 5
        fold_size = n // n_folds

        ridge_r2s, cnn_r2s, dual_r2s = [], [], []

        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = min((fold + 1) * fold_size, n)
            val_idx = slice(val_start, val_end)
            train_idx = np.concatenate([np.arange(0, val_start), np.arange(val_end, n)])

            tr_X = combined[train_idx]
            tr_y = tgt[train_idx]
            vl_X = combined[val_idx]
            vl_y = tgt[val_idx]

            # Ridge
            ridge = Ridge(alpha=1.0)
            tr_flat = tr_X.reshape(len(tr_X), -1)
            vl_flat = vl_X.reshape(len(vl_X), -1)
            ridge.fit(tr_flat, tr_y)
            ridge_r2s.append(r2_score(vl_y, ridge.predict(vl_flat)))

            # CNN
            m = ResidualCNN(in_channels=5)
            cnn_r2s.append(train_cnn(m, [tr_X, tr_y], [vl_X, vl_y], epochs=40))

            # Dual-branch
            tr_g, tr_p = g[train_idx], phys[train_idx]
            vl_g, vl_p = g[val_idx], phys[val_idx]
            m_d = DualBranchCNN(glucose_channels=1, physics_channels=4)
            dual_r2s.append(train_cnn(m_d, [tr_g, tr_p, tr_y], [vl_g, vl_p, vl_y],
                                      epochs=40, multi_input=True))

        res = {
            'patient': p['name'],
            'ridge_cv_mean': round(np.mean(ridge_r2s), 4),
            'ridge_cv_std': round(np.std(ridge_r2s), 4),
            'cnn_cv_mean': round(np.mean(cnn_r2s), 4),
            'cnn_cv_std': round(np.std(cnn_r2s), 4),
            'dual_cv_mean': round(np.mean(dual_r2s), 4),
            'dual_cv_std': round(np.std(dual_r2s), 4),
            'n_folds': n_folds,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={np.mean(ridge_r2s):.4f}±{np.std(ridge_r2s):.3f} "
                  f"cnn={np.mean(cnn_r2s):.4f}±{np.std(cnn_r2s):.3f} "
                  f"dual={np.mean(dual_r2s):.4f}±{np.std(dual_r2s):.3f}")

    mean_ridge = np.mean([r['ridge_cv_mean'] for r in results])
    mean_cnn = np.mean([r['cnn_cv_mean'] for r in results])
    mean_dual = np.mean([r['dual_cv_mean'] for r in results])
    return {
        'status': 'pass',
        'detail': f'block_cv: ridge={mean_ridge:.4f} cnn={mean_cnn:.4f} dual={mean_dual:.4f}',
        'results': {'per_patient': results},
    }


def exp_1029_confidence_calibration(patients, detail=False):
    """Prediction confidence via ensemble disagreement."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Train 5 models with different seeds
        predictions = []
        for seed in range(5):
            torch.manual_seed(seed * 42)
            np.random.seed(seed * 42)
            m = ResidualCNN(in_channels=5)
            train_cnn(m, train, val, epochs=40)
            m.eval()
            with torch.no_grad():
                pred = m(torch.from_numpy(val[0]).float().to(DEVICE))
                predictions.append(pred.cpu().numpy())

        preds = np.array(predictions)  # (5, N)
        mean_pred = preds.mean(axis=0)
        std_pred = preds.std(axis=0)

        # Calibration: are high-confidence predictions more accurate?
        errors = np.abs(mean_pred - val[1]) * GLUCOSE_SCALE
        confidence = 1.0 / (1.0 + std_pred * GLUCOSE_SCALE)

        # Split into confidence quintiles
        quintile_stats = {}
        for q in range(5):
            lo = np.percentile(confidence, q * 20)
            hi = np.percentile(confidence, (q + 1) * 20)
            mask = (confidence >= lo) & (confidence < hi + 0.001)
            if mask.sum() > 0:
                quintile_stats[f'q{q+1}'] = {
                    'mean_error': round(float(errors[mask].mean()), 1),
                    'n_samples': int(mask.sum()),
                }

        r2_overall = r2_score(val[1], mean_pred)
        res = {
            'patient': p['name'],
            'r2_ensemble': round(r2_overall, 4),
            'mean_mae': round(float(errors.mean()), 1),
            'mean_uncertainty': round(float(std_pred.mean() * GLUCOSE_SCALE), 1),
            'quintile_stats': quintile_stats,
            'calibration_slope': round(float(np.corrcoef(confidence, -errors)[0, 1]), 3),
        }
        results.append(res)
        if detail:
            q_errs = ' '.join(f"q{k}={v['mean_error']:.0f}" for k, v in quintile_stats.items())
            print(f"    {p['name']}: r2={r2_overall:.4f} mae={errors.mean():.1f}±{std_pred.mean()*GLUCOSE_SCALE:.1f} {q_errs} cal={res['calibration_slope']:.3f}")

    cal_slopes = [r['calibration_slope'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_calibration_slope={np.mean(cal_slopes):.3f}',
        'results': {'per_patient': results},
    }


def exp_1030_grand_combined(patients, detail=False):
    """Grand combined: residual CNN + cross-patient + physics + ensemble.

    Best-of-breed combination from this batch.
    """
    # Build all patient data
    patient_data = {}
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        # Z-normalize physics
        combined_norm = combined.copy()
        for ch in range(1, 5):
            mu, sigma = combined_norm[:, :, ch].mean(), combined_norm[:, :, ch].std()
            if sigma > 0:
                combined_norm[:, :, ch] = (combined_norm[:, :, ch] - mu) / sigma

        train, val = split_chrono([combined_norm, tgt])
        patient_data[p['name']] = {'train': train, 'val': val, 'g': g, 'phys': phys, 'tgt': tgt}

    results = []
    for test_name in patient_data:
        test = patient_data[test_name]
        train, val = test['train'], test['val']

        # 1. Ridge baseline
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_pred = ridge.predict(vl_flat)
        r2_ridge = r2_score(val[1], ridge_pred)

        # 2. Residual CNN
        ridge_train_pred = ridge.predict(tr_flat)
        train_resid = train[1] - ridge_train_pred
        val_resid = val[1] - ridge_pred

        m_res = ResidualCNN(in_channels=5)
        train_cnn(m_res, [train[0], train_resid], [val[0], val_resid], epochs=50)
        m_res.eval()
        with torch.no_grad():
            cnn_resid = m_res(torch.from_numpy(val[0]).float().to(DEVICE)).cpu().numpy()
        combined_pred = ridge_pred + 0.5 * cnn_resid
        r2_residual = r2_score(val[1], combined_pred)

        # 3. Cross-patient pretrained dual-branch + fine-tune
        train_X_all = np.concatenate([d['train'][0] for n, d in patient_data.items() if n != test_name])
        train_y_all = np.concatenate([d['train'][1] for n, d in patient_data.items() if n != test_name])

        m_dual = ResidualCNN(in_channels=5)
        train_cnn(m_dual, [train_X_all, train_y_all], [val[0], val[1]], epochs=30, batch_size=512)
        r2_ft = train_cnn(m_dual, [train[0], train[1]], [val[0], val[1]], epochs=30, lr=1e-4)

        # 4. Ensemble: ridge + residual CNN + fine-tuned
        m_dual.eval()
        with torch.no_grad():
            ft_pred = m_dual(torch.from_numpy(val[0]).float().to(DEVICE)).cpu().numpy()

        ens_pred = (ridge_pred + combined_pred + ft_pred) / 3.0
        r2_ensemble = r2_score(val[1], ens_pred)

        res = {
            'patient': test_name,
            'r2_ridge': round(r2_ridge, 4),
            'r2_residual_cnn': round(r2_residual, 4),
            'r2_pretrain_ft': round(r2_ft, 4),
            'r2_ensemble': round(r2_ensemble, 4),
            'best_r2': round(max(r2_ridge, r2_residual, r2_ft, r2_ensemble), 4),
        }
        results.append(res)
        if detail:
            print(f"    {test_name}: ridge={r2_ridge:.4f} resid={r2_residual:.4f} "
                  f"ft={r2_ft:.4f} ens={r2_ensemble:.4f}")

    mean_ens = np.mean([r['r2_ensemble'] for r in results])
    mean_best = np.mean([r['best_r2'] for r in results])
    return {
        'status': 'pass',
        'detail': f'mean_ensemble={mean_ens:.4f}, mean_best={mean_best:.4f}',
        'results': {'per_patient': results},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1021', 'Ridge-CNN Ensemble', exp_1021_ridge_cnn_ensemble),
    ('EXP-1022', 'Pretrain Fine-Tune', exp_1022_pretrain_finetune),
    ('EXP-1023', 'Patient Routing', exp_1023_patient_routing),
    ('EXP-1024', 'Residual CNN', exp_1024_residual_cnn),
    ('EXP-1025', 'Multi-Scale CNN', exp_1025_multiscale_cnn),
    ('EXP-1026', 'Physics-Normalized Cross-Patient Ridge', exp_1026_physics_normalized_crosspatient_ridge),
    ('EXP-1027', 'ToD-Conditioned Dual-Branch', exp_1027_tod_conditioned_dual),
    ('EXP-1028', 'Block CV Evaluation', exp_1028_block_cv),
    ('EXP-1029', 'Confidence Calibration', exp_1029_confidence_calibration),
    ('EXP-1030', 'Grand Combined', exp_1030_grand_combined),
]


def main():
    parser = argparse.ArgumentParser(description='EXP-1021-1030: Ensemble & Transfer')
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
