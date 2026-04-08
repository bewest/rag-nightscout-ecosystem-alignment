#!/usr/bin/env python3
"""EXP-1031 to EXP-1040: Adaptive Ensembles, Ablation, and Best Practices Pipeline.

Building on EXP-1021-1030's finding that residual CNN + cross-patient fine-tuning
yields the strongest results, this batch focuses on:
1. Learned ensemble weights (meta-learner stacking)
2. Residual CNN + fine-tune stack
3. Patient h deep dive (hardest patient analysis)
4. Derivative physics channels
5. Patient-specific DIA optimization
6. Multi-horizon joint training
7. Sliding window online learning
8. Physics channel permutation importance
9. Glucose regime segmentation
10. Grand summary best-practices pipeline

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1031 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.metrics import r2_score
from scipy import stats as sp_stats

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


class MultiHorizonCNN(nn.Module):
    """CNN that predicts at multiple horizons simultaneously."""
    def __init__(self, in_channels, n_horizons=4):
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
            nn.Linear(32, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x):
        feat = self.conv(x.permute(0, 2, 1)).squeeze(-1)
        return self.head(feat)


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


def build_multihorizon_data(df, pk_array, supply_demand, history_steps=WINDOW,
                            horizons=(3, 6, 12, 24), stride=STRIDE):
    """Build windows with multiple target horizons."""
    glucose = df['glucose'].values / GLUCOSE_SCALE
    N = len(glucose)
    max_h = max(horizons)
    total = history_steps + max_h

    supply = supply_demand['supply'] / 20.0
    demand = supply_demand['demand'] / 20.0
    hepatic = supply_demand['hepatic'] / 5.0
    net = supply_demand['net'] / 20.0

    x_wins, tgts = [], []

    for i in range(0, N - total, stride):
        g = glucose[i:i+history_steps]
        if np.isnan(g).mean() > 0.2:
            continue
        targets = [glucose[i + history_steps + h - 1] for h in horizons]
        if any(np.isnan(t) for t in targets):
            continue
        g = np.nan_to_num(g, nan=np.nanmean(g) if np.any(~np.isnan(g)) else 0.4)
        phys = np.stack([supply[i:i+history_steps], demand[i:i+history_steps],
                         hepatic[i:i+history_steps], net[i:i+history_steps]], axis=1)
        combined = np.concatenate([g.reshape(-1, 1), phys], axis=1)
        x_wins.append(combined)
        tgts.append(targets)

    return np.array(x_wins), np.array(tgts)


def build_derivative_data(df, pk_array, supply_demand, history_steps=WINDOW,
                          horizon_steps=HORIZON, stride=STRIDE):
    """Build windows with derivative physics channels appended."""
    glucose = df['glucose'].values / GLUCOSE_SCALE
    N = len(glucose)
    total = history_steps + horizon_steps

    supply = supply_demand['supply'] / 20.0
    demand = supply_demand['demand'] / 20.0
    hepatic = supply_demand['hepatic'] / 5.0
    net = supply_demand['net'] / 20.0

    # Compute derivatives (rate of change per 5-min step)
    d_supply = np.gradient(supply)
    d_demand = np.gradient(demand)
    d_hepatic = np.gradient(hepatic)
    d_net = np.gradient(net)

    x_base, x_deriv, tgts = [], [], []

    for i in range(0, N - total, stride):
        g = glucose[i:i+history_steps]
        if np.isnan(g).mean() > 0.2:
            continue
        target = glucose[i+history_steps+horizon_steps-1]
        if np.isnan(target):
            continue
        g = np.nan_to_num(g, nan=np.nanmean(g) if np.any(~np.isnan(g)) else 0.4)

        phys = np.stack([supply[i:i+history_steps], demand[i:i+history_steps],
                         hepatic[i:i+history_steps], net[i:i+history_steps]], axis=1)
        base = np.concatenate([g.reshape(-1, 1), phys], axis=1)  # (24, 5)

        deriv = np.stack([d_supply[i:i+history_steps], d_demand[i:i+history_steps],
                          d_hepatic[i:i+history_steps], d_net[i:i+history_steps]], axis=1)
        full = np.concatenate([base, deriv], axis=1)  # (24, 9)

        x_base.append(base)
        x_deriv.append(full)
        tgts.append(target)

    return np.array(x_base), np.array(x_deriv), np.array(tgts)


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


def train_multihorizon_cnn(model, train_data, val_data, epochs=60,
                           batch_size=256, patience=12, lr=1e-3):
    """Train multi-output CNN; returns (model, per-horizon R² list)."""
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
            pred = model(batch[0])
            loss = criterion(pred, batch[-1])
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
        pred = model(val_t[0]).cpu().numpy()
        y = val_t[-1].cpu().numpy()

    r2s = []
    for h in range(pred.shape[1]):
        r2s.append(r2_score(y[:, h], pred[:, h]))
    return model, r2s


def predict_cnn(model, X):
    """Get numpy predictions from a trained CNN."""
    model.eval()
    with torch.no_grad():
        pred = model(torch.from_numpy(X).float().to(DEVICE))
        return pred.cpu().numpy()


# ─── Experiments ───

def exp_1031_adaptive_ensemble_weighting(patients, detail=False):
    """Learned ensemble weights via validation-set stacking meta-learner."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Split train into train/meta-val for stacking
        meta_split = int(len(train[0]) * 0.7)
        train_inner = [a[:meta_split] for a in train]
        meta_val = [a[meta_split:] for a in train]

        # Model 1: Ridge
        tr_flat = train_inner[0].reshape(len(train_inner[0]), -1)
        mv_flat = meta_val[0].reshape(len(meta_val[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)

        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train_inner[1])
        ridge_meta_pred = ridge.predict(mv_flat)
        ridge_val_pred = ridge.predict(vl_flat)

        # Model 2: Residual CNN (learns Ridge errors)
        ridge_train_pred = ridge.predict(tr_flat)
        train_resid = train_inner[1] - ridge_train_pred
        meta_resid = meta_val[1] - ridge_meta_pred

        m_res = ResidualCNN(in_channels=5)
        m_res, _ = train_cnn(m_res, [train_inner[0], train_resid],
                             [meta_val[0], meta_resid], epochs=50)
        res_meta_pred = predict_cnn(m_res, meta_val[0])
        res_val_pred = predict_cnn(m_res, val[0])

        # Model 3: Fine-tuned CNN (direct prediction)
        m_ft = ResidualCNN(in_channels=5)
        m_ft, _ = train_cnn(m_ft, [train_inner[0], train_inner[1]],
                            [meta_val[0], meta_val[1]], epochs=50)
        ft_meta_pred = predict_cnn(m_ft, meta_val[0])
        ft_val_pred = predict_cnn(m_ft, val[0])

        # Meta-learner: train on meta-val predictions
        meta_X = np.column_stack([ridge_meta_pred,
                                  ridge_meta_pred + res_meta_pred,
                                  ft_meta_pred])
        meta_lr = LinearRegression()
        meta_lr.fit(meta_X, meta_val[1])

        # Equal-weight ensemble
        eq_pred = (ridge_val_pred + (ridge_val_pred + res_val_pred) + ft_val_pred) / 3.0
        r2_equal = r2_score(val[1], eq_pred)

        # Learned-weight ensemble
        val_meta_X = np.column_stack([ridge_val_pred,
                                      ridge_val_pred + res_val_pred,
                                      ft_val_pred])
        learned_pred = meta_lr.predict(val_meta_X)
        r2_learned = r2_score(val[1], learned_pred)

        # Individual baselines
        r2_ridge = r2_score(val[1], ridge_val_pred)
        r2_res_combined = r2_score(val[1], ridge_val_pred + 0.5 * res_val_pred)

        weights = meta_lr.coef_ / (meta_lr.coef_.sum() + 1e-8)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_residual_combined': round(r2_res_combined, 4),
            'r2_equal_weight': round(r2_equal, 4),
            'r2_learned_weight': round(r2_learned, 4),
            'learned_weights': [round(w, 3) for w in weights],
            'learned_vs_equal': round(r2_learned - r2_equal, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_ridge:.4f} eq={r2_equal:.4f} "
                  f"learned={r2_learned:.4f} Δ={r2_learned - r2_equal:+.4f} "
                  f"w={[f'{w:.2f}' for w in weights]}")

    gains = [r['learned_vs_equal'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_learned_gain={np.mean(gains):+.4f}, '
                  f'positive={sum(1 for g in gains if g > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1032_residual_cnn_finetune_stack(patients, detail=False):
    """Residual CNN + fine-tune stack: pretrain LOPO, fine-tune on target."""
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
        test = patient_data[test_name]
        train, val = test['train'], test['val']

        # Ridge for residual computation
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        ridge_train_pred = ridge.predict(tr_flat)
        ridge_val_pred = ridge.predict(vl_flat)
        r2_ridge = r2_score(val[1], ridge_val_pred)

        train_resid = train[1] - ridge_train_pred
        val_resid = val[1] - ridge_val_pred

        # (a) Per-patient residual CNN
        m_pp = ResidualCNN(in_channels=5)
        m_pp, _ = train_cnn(m_pp, [train[0], train_resid],
                            [val[0], val_resid], epochs=50)
        pp_resid_pred = predict_cnn(m_pp, val[0])
        r2_pp = r2_score(val[1], ridge_val_pred + 0.5 * pp_resid_pred)

        # Build cross-patient residuals
        other_X = np.concatenate([d['train'][0] for n, d in patient_data.items()
                                  if n != test_name])
        other_y = np.concatenate([d['train'][1] for n, d in patient_data.items()
                                  if n != test_name])
        other_flat = other_X.reshape(len(other_X), -1)
        ridge_cp = Ridge(alpha=1.0)
        ridge_cp.fit(other_flat, other_y)
        other_resid = other_y - ridge_cp.predict(other_flat)

        # (b) LOPO residual CNN
        m_lopo = ResidualCNN(in_channels=5)
        m_lopo, _ = train_cnn(m_lopo, [other_X, other_resid],
                              [val[0], val_resid], epochs=50, batch_size=512)
        lopo_resid_pred = predict_cnn(m_lopo, val[0])
        r2_lopo = r2_score(val[1], ridge_val_pred + 0.5 * lopo_resid_pred)

        # (c) LOPO pretrain + fine-tune residual CNN
        m_ft = ResidualCNN(in_channels=5)
        m_ft, _ = train_cnn(m_ft, [other_X, other_resid],
                            [val[0], val_resid], epochs=30, batch_size=512)
        m_ft, _ = train_cnn(m_ft, [train[0], train_resid],
                            [val[0], val_resid], epochs=30, lr=1e-4, patience=8)
        ft_resid_pred = predict_cnn(m_ft, val[0])
        r2_ft = r2_score(val[1], ridge_val_pred + 0.5 * ft_resid_pred)

        res = {
            'patient': test_name,
            'r2_ridge': round(r2_ridge, 4),
            'r2_per_patient_resid': round(r2_pp, 4),
            'r2_lopo_resid': round(r2_lopo, 4),
            'r2_lopo_finetune_resid': round(r2_ft, 4),
            'ft_vs_pp': round(r2_ft - r2_pp, 4),
            'ft_vs_lopo': round(r2_ft - r2_lopo, 4),
        }
        results.append(res)
        if detail:
            print(f"    {test_name}: ridge={r2_ridge:.4f} pp={r2_pp:.4f} "
                  f"lopo={r2_lopo:.4f} ft={r2_ft:.4f} Δ(pp)={r2_ft - r2_pp:+.4f}")

    ft_gains = [r['ft_vs_pp'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_ft_gain_vs_pp={np.mean(ft_gains):+.4f}, '
                  f'positive={sum(1 for g in ft_gains if g > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1033_patient_h_deep_dive(patients, detail=False):
    """Analyze what makes patient h uniquely difficult."""
    all_stats = {}

    for p in patients:
        glucose = p['df']['glucose'].values
        valid = glucose[~np.isnan(glucose)]
        pk = p['pk']

        # (a) Glucose distribution
        g_mean = float(np.mean(valid)) if len(valid) > 0 else 0.0
        g_std = float(np.std(valid)) if len(valid) > 0 else 0.0
        g_skew = float(sp_stats.skew(valid)) if len(valid) > 10 else 0.0
        g_kurt = float(sp_stats.kurtosis(valid)) if len(valid) > 10 else 0.0

        # (b) Missing data rate
        missing_rate = float(np.isnan(glucose).mean())

        # (c) Insulin delivery patterns
        insulin_total = pk[:, 0]  # channel 0
        insulin_net = pk[:, 1]    # channel 1
        insulin_variability = float(np.nanstd(insulin_total))
        bolus_frequency = float(np.nanmean(np.abs(insulin_net) > 0.01))

        # (d) Conservation violation rate
        net_balance = pk[:, 6]  # channel 6
        glucose_delta = np.diff(glucose) / GLUCOSE_SCALE
        glucose_delta = np.nan_to_num(glucose_delta)
        net_trimmed = net_balance[:len(glucose_delta)]
        violations = np.abs(glucose_delta - net_trimmed / 20.0) > 0.1
        violation_rate = float(np.mean(violations))

        # (e) Regime change metrics — count sign changes in net balance
        nb_sign = np.sign(np.nan_to_num(net_balance))
        sign_changes = np.sum(np.abs(np.diff(nb_sign)) > 0)
        regime_change_rate = float(sign_changes / max(len(nb_sign) - 1, 1))

        # Rolling 2h std of glucose
        win = 24
        rolling_std = []
        for i in range(0, len(valid) - win, win):
            rolling_std.append(np.std(valid[i:i+win]))
        volatility = float(np.mean(rolling_std)) if rolling_std else 0.0

        all_stats[p['name']] = {
            'glucose_mean': round(g_mean, 1),
            'glucose_std': round(g_std, 1),
            'glucose_skewness': round(g_skew, 3),
            'glucose_kurtosis': round(g_kurt, 3),
            'missing_rate': round(missing_rate, 4),
            'insulin_variability': round(insulin_variability, 4),
            'bolus_frequency': round(bolus_frequency, 4),
            'conservation_violation_rate': round(violation_rate, 4),
            'regime_change_rate': round(regime_change_rate, 4),
            'glucose_volatility': round(volatility, 1),
            'n_samples': len(glucose),
        }

    # Compare h vs others
    h_stats = all_stats.get('h', None)
    other_names = [n for n in all_stats if n != 'h']

    comparison = {}
    if h_stats and other_names:
        for metric in h_stats:
            if metric == 'n_samples':
                continue
            h_val = h_stats[metric]
            other_vals = [all_stats[n][metric] for n in other_names]
            other_mean = np.mean(other_vals)
            other_std = np.std(other_vals) if len(other_vals) > 1 else 1.0
            z_score = (h_val - other_mean) / other_std if other_std > 0 else 0.0
            comparison[metric] = {
                'h_value': h_val,
                'other_mean': round(other_mean, 4),
                'other_std': round(other_std, 4),
                'z_score': round(z_score, 2),
            }

    # Identify top distinguishing factors
    if comparison:
        ranked = sorted(comparison.items(), key=lambda x: abs(x[1]['z_score']),
                        reverse=True)
        top_factors = [f"{k} (z={v['z_score']:+.2f})" for k, v in ranked[:5]]
    else:
        top_factors = ['patient h not found in dataset']

    if detail:
        print("  Patient statistics:")
        for name, stats in sorted(all_stats.items()):
            marker = " ★" if name == 'h' else ""
            print(f"    {name}{marker}: mean={stats['glucose_mean']:.0f} "
                  f"std={stats['glucose_std']:.0f} missing={stats['missing_rate']:.3f} "
                  f"violations={stats['conservation_violation_rate']:.3f} "
                  f"regime_chg={stats['regime_change_rate']:.3f}")
        if comparison:
            print("  Patient h vs others (z-scores):")
            for factor in top_factors:
                print(f"    {factor}")

    return {
        'status': 'pass',
        'detail': f'top_h_factors: {", ".join(top_factors[:3])}',
        'results': {
            'per_patient': all_stats,
            'h_comparison': comparison,
            'top_distinguishing_factors': top_factors,
        },
    }


def exp_1034_derivative_physics_channels(patients, detail=False):
    """Add rate-of-change of physics channels as features."""
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        x_base, x_deriv, tgt = build_derivative_data(p['df'], p['pk'], sd)
        if len(x_base) < 200:
            continue

        # Ridge baseline (glucose + 4 physics = 5 channels)
        train_b, val_b = split_chrono([x_base, tgt])
        tr_flat_b = train_b[0].reshape(len(train_b[0]), -1)
        vl_flat_b = val_b[0].reshape(len(val_b[0]), -1)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(tr_flat_b, train_b[1])
        r2_ridge_base = r2_score(val_b[1], ridge_base.predict(vl_flat_b))

        # Ridge with derivatives (glucose + 4 physics + 4 derivatives = 9 channels)
        train_d, val_d = split_chrono([x_deriv, tgt])
        tr_flat_d = train_d[0].reshape(len(train_d[0]), -1)
        vl_flat_d = val_d[0].reshape(len(val_d[0]), -1)
        ridge_deriv = Ridge(alpha=1.0)
        ridge_deriv.fit(tr_flat_d, train_d[1])
        r2_ridge_deriv = r2_score(val_d[1], ridge_deriv.predict(vl_flat_d))

        # CNN baseline
        m_base = ResidualCNN(in_channels=5)
        _, r2_cnn_base = train_cnn(m_base, train_b, val_b, epochs=50)

        # CNN with derivatives
        m_deriv = ResidualCNN(in_channels=9)
        _, r2_cnn_deriv = train_cnn(m_deriv, train_d, val_d, epochs=50)

        res = {
            'patient': p['name'],
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_deriv': round(r2_ridge_deriv, 4),
            'ridge_improvement': round(r2_ridge_deriv - r2_ridge_base, 4),
            'r2_cnn_base': round(r2_cnn_base, 4),
            'r2_cnn_deriv': round(r2_cnn_deriv, 4),
            'cnn_improvement': round(r2_cnn_deriv - r2_cnn_base, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge {r2_ridge_base:.4f}→{r2_ridge_deriv:.4f} "
                  f"({r2_ridge_deriv - r2_ridge_base:+.4f})  "
                  f"cnn {r2_cnn_base:.4f}→{r2_cnn_deriv:.4f} "
                  f"({r2_cnn_deriv - r2_cnn_base:+.4f})")

    ridge_imp = [r['ridge_improvement'] for r in results]
    cnn_imp = [r['cnn_improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'ridge_deriv_gain={np.mean(ridge_imp):+.4f}, '
                  f'cnn_deriv_gain={np.mean(cnn_imp):+.4f}',
        'results': {'per_patient': results},
    }


def exp_1035_patient_specific_dia(patients, detail=False):
    """Sweep DIA per patient, minimize Ridge prediction error."""
    from cgmencode.continuous_pk import build_continuous_pk_features

    dia_values = np.arange(2.5, 6.5, 0.5)  # 2.5, 3.0, ..., 6.0
    results = []

    for p in patients:
        df = p['df'].copy()
        original_dia = df.attrs.get('patient_dia', 5.0)
        best_dia = original_dia
        best_r2 = -999.0
        dia_scores = {}

        for dia in dia_values:
            df.attrs['patient_dia'] = float(dia)
            try:
                pk_new = build_continuous_pk_features(df, dia_hours=float(dia))
            except Exception:
                continue

            if pk_new is None or len(pk_new) != len(df):
                continue

            sd_new = compute_supply_demand(df, pk_new)
            g, _, phys, tgt = build_windowed_data(df, pk_new, sd_new)
            if len(g) < 200:
                continue

            combined = np.concatenate([g, phys], axis=2)
            train, val = split_chrono([combined, tgt])

            tr_flat = train[0].reshape(len(train[0]), -1)
            vl_flat = val[0].reshape(len(val[0]), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, train[1])
            r2 = r2_score(val[1], ridge.predict(vl_flat))
            dia_scores[float(dia)] = round(r2, 4)

            if r2 > best_r2:
                best_r2 = r2
                best_dia = float(dia)

        # Restore original DIA
        df.attrs['patient_dia'] = original_dia

        original_r2 = dia_scores.get(round(original_dia * 2) / 2, None)
        if original_r2 is None:
            original_r2 = dia_scores.get(original_dia, best_r2)

        res = {
            'patient': p['name'],
            'original_dia': original_dia,
            'best_dia': best_dia,
            'best_r2': round(best_r2, 4),
            'original_r2': round(original_r2, 4) if original_r2 is not None else None,
            'improvement': round(best_r2 - original_r2, 4) if original_r2 is not None else None,
            'dia_scores': dia_scores,
        }
        results.append(res)
        if detail:
            scores_str = ' '.join(f"{d:.1f}:{r2:.3f}" for d, r2 in sorted(dia_scores.items()))
            print(f"    {p['name']}: orig_dia={original_dia:.1f} best_dia={best_dia:.1f} "
                  f"Δ={best_r2 - (original_r2 or best_r2):+.4f}  [{scores_str}]")

    improvements = [r['improvement'] for r in results if r['improvement'] is not None]
    return {
        'status': 'pass',
        'detail': f'mean_dia_opt_gain={np.mean(improvements):+.4f}, '
                  f'patients_with_different_best={sum(1 for r in results if r["best_dia"] != r["original_dia"])}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1036_multi_horizon_joint(patients, detail=False):
    """Single CNN predicting at 15, 30, 60, and 120 minutes simultaneously."""
    horizons = (3, 6, 12, 24)  # steps → 15, 30, 60, 120 min
    horizon_names = ['15min', '30min', '60min', '120min']
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])

        # Multi-horizon data
        x_mh, tgt_mh = build_multihorizon_data(p['df'], p['pk'], sd, horizons=horizons)
        if len(x_mh) < 200:
            continue

        train_mh, val_mh = split_chrono([x_mh, tgt_mh])

        # Joint multi-horizon CNN
        m_joint = MultiHorizonCNN(in_channels=5, n_horizons=len(horizons))
        _, r2_joint = train_multihorizon_cnn(m_joint, train_mh, val_mh, epochs=50)

        # Separate per-horizon CNNs
        r2_separate = []
        for hi, h in enumerate(horizons):
            g_h, _, phys_h, tgt_h = build_windowed_data(
                p['df'], p['pk'], sd, horizon_steps=h)
            if len(g_h) < 200:
                r2_separate.append(float('nan'))
                continue
            combined_h = np.concatenate([g_h, phys_h], axis=2)
            train_h, val_h = split_chrono([combined_h, tgt_h])
            m_sep = ResidualCNN(in_channels=5)
            _, r2_h = train_cnn(m_sep, train_h, val_h, epochs=50)
            r2_separate.append(r2_h)

        res = {
            'patient': p['name'],
        }
        for hi, hname in enumerate(horizon_names):
            res[f'r2_joint_{hname}'] = round(r2_joint[hi], 4)
            res[f'r2_separate_{hname}'] = round(r2_separate[hi], 4) if not np.isnan(r2_separate[hi]) else None
            if not np.isnan(r2_separate[hi]):
                res[f'joint_vs_separate_{hname}'] = round(r2_joint[hi] - r2_separate[hi], 4)

        results.append(res)
        if detail:
            parts = []
            for hi, hname in enumerate(horizon_names):
                sep = r2_separate[hi]
                jnt = r2_joint[hi]
                parts.append(f"{hname}: j={jnt:.3f} s={sep:.3f}")
            print(f"    {p['name']}: {' | '.join(parts)}")

    # Aggregate per-horizon
    summary = {}
    for hi, hname in enumerate(horizon_names):
        joint_vals = [r[f'r2_joint_{hname}'] for r in results if f'r2_joint_{hname}' in r]
        sep_key = f'r2_separate_{hname}'
        sep_vals = [r[sep_key] for r in results if r.get(sep_key) is not None]
        if joint_vals:
            summary[hname] = {
                'mean_joint': round(np.mean(joint_vals), 4),
                'mean_separate': round(np.mean(sep_vals), 4) if sep_vals else None,
            }

    return {
        'status': 'pass',
        'detail': f'joint_vs_separate: ' + ', '.join(
            f'{h}={s["mean_joint"]:.3f}vs{s.get("mean_separate", 0):.3f}'
            for h, s in summary.items()),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1037_sliding_window_online(patients, detail=False):
    """Rolling retrain: train on first 60d, predict 30d, retrain on 90d, etc."""
    results = []
    STEPS_PER_DAY = 288  # 5-min intervals

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)

        n = len(combined)
        initial_days = 60
        retrain_days = 30
        initial_windows = min(int(initial_days * STEPS_PER_DAY / STRIDE), int(n * 0.5))
        retrain_windows = int(retrain_days * STEPS_PER_DAY / STRIDE)

        if initial_windows < 100 or initial_windows + retrain_windows > n:
            # Fall back to simpler split for short data
            initial_windows = int(n * 0.4)
            retrain_windows = int(n * 0.2)

        # Sliding window predictions
        online_preds, online_true = [], []
        cursor = initial_windows
        while cursor + retrain_windows <= n:
            tr_X = combined[:cursor]
            tr_y = tgt[:cursor]
            vl_X = combined[cursor:cursor + retrain_windows]
            vl_y = tgt[cursor:cursor + retrain_windows]

            if len(vl_X) < 10:
                break

            tr_flat = tr_X.reshape(len(tr_X), -1)
            vl_flat = vl_X.reshape(len(vl_X), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, tr_y)
            preds = ridge.predict(vl_flat)
            online_preds.extend(preds.tolist())
            online_true.extend(vl_y.tolist())

            cursor += retrain_windows

        if len(online_preds) < 20:
            continue

        r2_online = r2_score(online_true, online_preds)

        # Static baseline: train on 80%, test on 20%
        train_static, val_static = split_chrono([combined, tgt])
        tr_flat_s = train_static[0].reshape(len(train_static[0]), -1)
        vl_flat_s = val_static[0].reshape(len(val_static[0]), -1)
        ridge_static = Ridge(alpha=1.0)
        ridge_static.fit(tr_flat_s, train_static[1])
        r2_static = r2_score(val_static[1], ridge_static.predict(vl_flat_s))

        res = {
            'patient': p['name'],
            'r2_static': round(r2_static, 4),
            'r2_online': round(r2_online, 4),
            'improvement': round(r2_online - r2_static, 4),
            'n_retrains': max(0, (cursor - initial_windows) // retrain_windows),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: static={r2_static:.4f} online={r2_online:.4f} "
                  f"Δ={r2_online - r2_static:+.4f} retrains={res['n_retrains']}")

    imp = [r['improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_online_gain={np.mean(imp):+.4f}, '
                  f'positive={sum(1 for i in imp if i > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1038_physics_permutation_importance(patients, detail=False):
    """Permutation importance of each decomposed physics channel."""
    channel_names = ['supply', 'demand', 'hepatic', 'net']
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)
        train, val = split_chrono([combined, tgt])

        # Baseline Ridge
        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(tr_flat, train[1])
        r2_baseline = r2_score(val[1], ridge.predict(vl_flat))

        # Permutation importance: shuffle each physics channel
        importance = {}
        rng = np.random.RandomState(42)
        for ch_idx, ch_name in enumerate(channel_names):
            # Channel index in combined: 0=glucose, 1-4=physics
            val_shuffled = val[0].copy()
            perm = rng.permutation(len(val_shuffled))
            val_shuffled[:, :, ch_idx + 1] = val_shuffled[perm, :, ch_idx + 1]
            vl_flat_s = val_shuffled.reshape(len(val_shuffled), -1)
            r2_shuffled = r2_score(val[1], ridge.predict(vl_flat_s))
            importance[ch_name] = round(r2_baseline - r2_shuffled, 4)

        # Single-channel models: each physics channel alone + glucose
        single_channel_r2 = {}
        for ch_idx, ch_name in enumerate(channel_names):
            single_X = np.concatenate([g, phys[:, :, ch_idx:ch_idx+1]], axis=2)
            train_s, val_s = split_chrono([single_X, tgt])
            tr_flat_s = train_s[0].reshape(len(train_s[0]), -1)
            vl_flat_s = val_s[0].reshape(len(val_s[0]), -1)
            ridge_s = Ridge(alpha=1.0)
            ridge_s.fit(tr_flat_s, train_s[1])
            single_channel_r2[ch_name] = round(r2_score(val_s[1], ridge_s.predict(vl_flat_s)), 4)

        # Glucose-only baseline
        train_go, val_go = split_chrono([g, tgt])
        tr_flat_go = train_go[0].reshape(len(train_go[0]), -1)
        vl_flat_go = val_go[0].reshape(len(val_go[0]), -1)
        ridge_go = Ridge(alpha=1.0)
        ridge_go.fit(tr_flat_go, train_go[1])
        r2_glucose_only = r2_score(val_go[1], ridge_go.predict(vl_flat_go))

        res = {
            'patient': p['name'],
            'r2_baseline': round(r2_baseline, 4),
            'r2_glucose_only': round(r2_glucose_only, 4),
            'permutation_importance': importance,
            'single_channel_r2': single_channel_r2,
        }
        results.append(res)
        if detail:
            imp_str = ' '.join(f"{k}={v:+.4f}" for k, v in importance.items())
            single_str = ' '.join(f"{k}={v:.3f}" for k, v in single_channel_r2.items())
            print(f"    {p['name']}: base={r2_baseline:.4f} g_only={r2_glucose_only:.4f} "
                  f"perm=[{imp_str}] single=[{single_str}]")

    # Aggregate importance across patients
    agg_importance = {}
    for ch in channel_names:
        vals = [r['permutation_importance'][ch] for r in results]
        agg_importance[ch] = {
            'mean': round(np.mean(vals), 4),
            'std': round(np.std(vals), 4),
        }

    ranked = sorted(agg_importance.items(), key=lambda x: x[1]['mean'], reverse=True)
    return {
        'status': 'pass',
        'detail': 'importance_rank: ' + ' > '.join(
            f'{k}({v["mean"]:+.4f})' for k, v in ranked),
        'results': {
            'per_patient': results,
            'aggregate_importance': agg_importance,
        },
    }


def exp_1039_glucose_regime_segmentation(patients, detail=False):
    """Segment glucose into regimes; train separate Ridge models per regime."""
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g, pk, phys, tgt = build_windowed_data(p['df'], p['pk'], sd)
        if len(g) < 200:
            continue
        combined = np.concatenate([g, phys], axis=2)

        # Classify each window's regime based on glucose trend in the window
        regimes = []
        for i in range(len(g)):
            g_win = g[i, :, 0]
            slope = np.polyfit(np.arange(len(g_win)), g_win, 1)[0]
            std_val = np.std(g_win)

            if std_val > 0.08:  # volatile
                regimes.append('volatile')
            elif slope > 0.002:
                regimes.append('rising')
            elif slope < -0.002:
                regimes.append('falling')
            else:
                regimes.append('stable')
        regimes = np.array(regimes)

        # Unified Ridge baseline
        train, val = split_chrono([combined, tgt])
        train_regimes = regimes[:len(train[0])]
        val_regimes = regimes[len(train[0]):]

        tr_flat = train[0].reshape(len(train[0]), -1)
        vl_flat = val[0].reshape(len(val[0]), -1)
        ridge_all = Ridge(alpha=1.0)
        ridge_all.fit(tr_flat, train[1])
        pred_unified = ridge_all.predict(vl_flat)
        r2_unified = r2_score(val[1], pred_unified)

        # Per-regime Ridge models
        pred_regime = np.copy(pred_unified)  # fallback to unified
        regime_stats = {}
        for regime in ['stable', 'rising', 'falling', 'volatile']:
            tr_mask = train_regimes == regime
            vl_mask = val_regimes == regime

            n_train = tr_mask.sum()
            n_val = vl_mask.sum()
            regime_stats[regime] = {
                'n_train': int(n_train),
                'n_val': int(n_val),
            }

            if n_train < 30 or n_val < 5:
                # Not enough data, keep unified predictions
                if n_val > 0:
                    regime_stats[regime]['r2'] = round(
                        r2_score(val[1][vl_mask], pred_unified[vl_mask]), 4
                    ) if n_val > 1 else None
                continue

            ridge_r = Ridge(alpha=1.0)
            ridge_r.fit(tr_flat[tr_mask], train[1][tr_mask])
            regime_pred = ridge_r.predict(vl_flat[vl_mask])
            pred_regime[vl_mask] = regime_pred

            if n_val > 1:
                regime_stats[regime]['r2'] = round(r2_score(val[1][vl_mask], regime_pred), 4)

        r2_regime = r2_score(val[1], pred_regime)

        res = {
            'patient': p['name'],
            'r2_unified': round(r2_unified, 4),
            'r2_regime': round(r2_regime, 4),
            'improvement': round(r2_regime - r2_unified, 4),
            'regime_distribution': {r: int((regimes == r).sum()) for r in
                                    ['stable', 'rising', 'falling', 'volatile']},
            'regime_stats': regime_stats,
        }
        results.append(res)
        if detail:
            dist = res['regime_distribution']
            print(f"    {p['name']}: unified={r2_unified:.4f} regime={r2_regime:.4f} "
                  f"Δ={r2_regime - r2_unified:+.4f}  "
                  f"dist=[s={dist['stable']} r={dist['rising']} f={dist['falling']} v={dist['volatile']}]")

    imp = [r['improvement'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_regime_gain={np.mean(imp):+.4f}, '
                  f'positive={sum(1 for i in imp if i > 0)}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1040_grand_summary_pipeline(patients, detail=False):
    """Best-practices pipeline: decomposed physics → Ridge → residual CNN → confidence.

    Definitive evaluation combining all insights from EXP-1001-1030.
    Reports final metrics with block CV.
    """
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

        fold_results = {
            'r2_glucose_only': [],
            'r2_ridge_physics': [],
            'r2_residual_cnn': [],
            'r2_ensemble': [],
            'mae_mg_dl': [],
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

            # Stage 3: Ensemble with confidence (train 3 seeds, average)
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

        if not fold_results['r2_ensemble']:
            continue

        res = {
            'patient': p['name'],
        }
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
                  f"mae={res['mae_mg_dl_mean']:.1f}mg/dL")

    # Grand summary
    summary = {}
    for key in ['r2_glucose_only_mean', 'r2_ridge_physics_mean',
                'r2_residual_cnn_mean', 'r2_ensemble_mean', 'mae_mg_dl_mean']:
        vals = [r[key] for r in results]
        summary[key] = round(np.mean(vals), 4)

    summary['physics_lift'] = round(np.mean([r['physics_lift'] for r in results]), 4)
    summary['residual_lift'] = round(np.mean([r['residual_lift'] for r in results]), 4)
    summary['ensemble_lift'] = round(np.mean([r['ensemble_lift'] for r in results]), 4)

    return {
        'status': 'pass',
        'detail': (f'pipeline: g_only={summary["r2_glucose_only_mean"]:.4f} → '
                   f'ridge+phys={summary["r2_ridge_physics_mean"]:.4f} → '
                   f'resid_cnn={summary["r2_residual_cnn_mean"]:.4f} → '
                   f'ensemble={summary["r2_ensemble_mean"]:.4f} '
                   f'(mae={summary["mae_mg_dl_mean"]:.1f}mg/dL)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1031', 'Adaptive Ensemble Weighting', exp_1031_adaptive_ensemble_weighting),
    ('EXP-1032', 'Residual CNN Fine-Tune Stack', exp_1032_residual_cnn_finetune_stack),
    ('EXP-1033', 'Patient h Deep Dive', exp_1033_patient_h_deep_dive),
    ('EXP-1034', 'Derivative Physics Channels', exp_1034_derivative_physics_channels),
    ('EXP-1035', 'Patient-Specific DIA Optimization', exp_1035_patient_specific_dia),
    ('EXP-1036', 'Multi-Horizon Joint Training', exp_1036_multi_horizon_joint),
    ('EXP-1037', 'Sliding Window Online Learning', exp_1037_sliding_window_online),
    ('EXP-1038', 'Physics Permutation Importance', exp_1038_physics_permutation_importance),
    ('EXP-1039', 'Glucose Regime Segmentation', exp_1039_glucose_regime_segmentation),
    ('EXP-1040', 'Grand Summary Pipeline', exp_1040_grand_summary_pipeline),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1031-1040: Adaptive Ensembles, Ablation & Best Practices')
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
