#!/usr/bin/env python3
"""EXP-1011 to EXP-1020: CNN Architecture with Decomposed Physics Features.

Building on the EXP-1003 breakthrough (decomposed supply/demand/hepatic channels
give +0.265 R²), this batch tests whether 1D-CNN temporal pattern extraction
can amplify that improvement beyond what Ridge regression captures.

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1011 --detail --save --max-patients 11
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

# ─── Imports ───
try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand

# PyTorch
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0  # Normalization factor for glucose
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ─── CNN Models ───

class PhysicsCNN(nn.Module):
    """1D-CNN with separate glucose and physics branches."""
    def __init__(self, glucose_channels, physics_channels, seq_len=24):
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
        # glucose: (B, T, C_g), physics: (B, T, C_p)
        g = self.glucose_conv(glucose.permute(0, 2, 1)).squeeze(-1)
        p = self.physics_conv(physics.permute(0, 2, 1)).squeeze(-1)
        combined = torch.cat([g, p], dim=1)
        return self.head(combined).squeeze(-1)


class SingleBranchCNN(nn.Module):
    """Standard 1D-CNN with all channels concatenated."""
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


class PhysicsConditionedCNN(nn.Module):
    """CNN where physics features condition the glucose encoder via FiLM."""
    def __init__(self, glucose_channels, physics_dim, seq_len=24):
        super().__init__()
        self.glucose_conv = nn.Sequential(
            nn.Conv1d(glucose_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        # FiLM: generate scale and shift from physics summary
        self.film_net = nn.Sequential(
            nn.Linear(physics_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 64),  # 32 gamma + 32 beta
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.head = nn.Sequential(
            nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(16, 1),
        )

    def forward(self, glucose, physics_summary):
        # glucose: (B, T, C_g), physics_summary: (B, D)
        g = self.glucose_conv(glucose.permute(0, 2, 1))  # (B, 32, T)
        film = self.film_net(physics_summary)  # (B, 64)
        gamma = film[:, :32].unsqueeze(-1)  # (B, 32, 1)
        beta = film[:, 32:].unsqueeze(-1)   # (B, 32, 1)
        g = gamma * g + beta  # FiLM conditioning
        g = torch.relu(g)
        g = self.pool(g).squeeze(-1)  # (B, 32)
        return self.head(g).squeeze(-1)


class ConservationPenalizedCNN(nn.Module):
    """CNN with auxiliary conservation violation prediction head."""
    def __init__(self, in_channels, seq_len=24):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.glucose_head = nn.Sequential(
            nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(16, 1),
        )
        self.conservation_head = nn.Sequential(
            nn.Linear(32, 16), nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        feat = self.backbone(x.permute(0, 2, 1)).squeeze(-1)
        glucose_pred = self.glucose_head(feat).squeeze(-1)
        conservation_pred = self.conservation_head(feat).squeeze(-1)
        return glucose_pred, conservation_pred


# ─── Data Preparation Helpers ───

def build_windowed_data(df, pk_array, supply_demand, history_steps=24,
                        horizon_steps=12, stride=6):
    """Build sliding windows with glucose, PK, and physics decomposition.

    Returns:
        glucose_windows: (N, history_steps, 1) - normalized glucose
        pk_windows: (N, history_steps, 8) - PK channels
        physics_windows: (N, history_steps, 4) - supply, demand, hepatic, net
        targets: (N,) - future glucose change (normalized)
        conservation_violations: (N,) - abs(predicted - actual change)
    """
    glucose = df['glucose'].values / GLUCOSE_SCALE
    N = len(glucose)
    total_steps = history_steps + horizon_steps

    supply = supply_demand['supply']
    demand = supply_demand['demand']
    hepatic = supply_demand['hepatic']
    net = supply_demand['net']

    # Normalize physics channels
    supply_norm = supply / 20.0
    demand_norm = demand / 20.0
    hepatic_norm = hepatic / 5.0
    net_norm = net / 20.0

    g_windows, pk_wins, phys_wins, tgts, cons_viols = [], [], [], [], []

    for i in range(0, N - total_steps, stride):
        g_win = glucose[i:i+history_steps]
        if np.isnan(g_win).mean() > 0.2:
            continue

        target_glucose = glucose[i+history_steps+horizon_steps-1]
        if np.isnan(target_glucose):
            continue

        # Fill NaN in history with forward fill
        g_win = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)

        g_windows.append(g_win.reshape(-1, 1))
        pk_wins.append(pk_array[i:i+history_steps])

        phys = np.stack([
            supply_norm[i:i+history_steps],
            demand_norm[i:i+history_steps],
            hepatic_norm[i:i+history_steps],
            net_norm[i:i+history_steps],
        ], axis=1)
        phys_wins.append(phys)

        # Target: glucose at horizon
        tgts.append(target_glucose)

        # Conservation violation: predicted vs actual glucose change
        predicted_change = np.sum(net[i:i+history_steps]) / GLUCOSE_SCALE
        actual_change = glucose[i+history_steps-1] - glucose[i]
        viol = abs(predicted_change - actual_change)
        cons_viols.append(viol if np.isfinite(viol) else 0.0)

    return (np.array(g_windows), np.array(pk_wins), np.array(phys_wins),
            np.array(tgts), np.array(cons_viols))


def split_chronological(arrays, train_frac=0.8):
    """Chronological train/val split for multiple arrays."""
    n = len(arrays[0])
    split = int(train_frac * n)
    train = [a[:split] for a in arrays]
    val = [a[split:] for a in arrays]
    return train, val


def train_cnn_model(model, train_data, val_data, epochs=60, batch_size=256,
                    patience=12, lr=1e-3, multi_input=False, conservation=False,
                    conservation_weight=0.1):
    """Generic CNN training loop.

    Args:
        model: nn.Module
        train_data: list of numpy arrays [x1, x2, ..., y] or [x, y]
        val_data: same structure
        multi_input: if True, model takes multiple inputs
        conservation: if True, model returns (glucose_pred, conservation_pred)
                     and train_data has extra conservation target
    """
    # Convert to tensors
    train_tensors = [torch.from_numpy(a).float() for a in train_data]
    val_tensors = [torch.from_numpy(a).float().to(DEVICE) for a in val_data]

    ds = TensorDataset(*train_tensors)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(DEVICE.type == 'cuda'))

    model = model.to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    best_loss = float('inf')
    best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    wait = 0

    for epoch in range(epochs):
        model.train()
        for batch in dl:
            batch = [b.to(DEVICE) for b in batch]
            if conservation:
                inputs, y_glucose, y_cons = batch[:-2], batch[-2], batch[-1]
            else:
                inputs, y = batch[:-1], batch[-1]

            if multi_input:
                pred = model(*inputs)
            else:
                pred = model(inputs[0])

            if conservation:
                g_pred, c_pred = pred
                loss = criterion(g_pred, y_glucose) + conservation_weight * criterion(c_pred, y_cons)
            else:
                loss = criterion(pred, y)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            if multi_input:
                val_pred = model(*val_tensors[:-1])
            else:
                val_pred = model(val_tensors[0])

            if conservation:
                val_pred = val_pred[0]  # glucose prediction only
                val_y = val_tensors[-2]
            else:
                val_y = val_tensors[-1]

            val_loss = criterion(val_pred, val_y).item()

        scheduler.step(val_loss)
        if val_loss < best_loss:
            best_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    # Load best and evaluate
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        if multi_input:
            final_pred = model(*val_tensors[:-1])
        else:
            final_pred = model(val_tensors[0])

        if conservation:
            final_pred = final_pred[0]
            val_y = val_tensors[-2]
        else:
            val_y = val_tensors[-1]

        pred_np = final_pred.cpu().numpy()
        y_np = val_y.cpu().numpy()

    r2 = r2_score(y_np, pred_np)
    mae = float(np.mean(np.abs(pred_np - y_np)) * GLUCOSE_SCALE)
    return {'r2': r2, 'mae_mg_dl': mae, 'val_loss': best_loss, 'epochs': epoch+1}


# ─── Experiments ───

def exp_1011_cnn_decomposed_physics(patients, detail=False):
    """CNN with decomposed physics channels vs Ridge baseline.

    Compare: Ridge(glucose+physics) vs CNN(glucose+physics)
    to see if temporal patterns in physics channels add value beyond linear.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        # Combine glucose + physics for CNN input
        combined = np.concatenate([g_win, phys_win], axis=2)  # (N, 24, 5)
        train, val = split_chronological([combined, targets])

        # Ridge baseline
        train_flat = train[0].reshape(len(train[0]), -1)
        val_flat = val[0].reshape(len(val[0]), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(train_flat, train[1])
        r2_ridge = r2_score(val[1], ridge.predict(val_flat))

        # CNN
        model = SingleBranchCNN(in_channels=5, seq_len=24)
        cnn_result = train_cnn_model(model, train, val, epochs=60, batch_size=256)

        res = {
            'patient': p['name'],
            'n_windows': len(g_win),
            'r2_ridge': round(r2_ridge, 4),
            'r2_cnn': round(cnn_result['r2'], 4),
            'cnn_improvement': round(cnn_result['r2'] - r2_ridge, 4),
            'mae_cnn': round(cnn_result['mae_mg_dl'], 1),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: Ridge={r2_ridge:.4f} CNN={cnn_result['r2']:.4f} Δ={cnn_result['r2']-r2_ridge:+.4f}")

    improvements = [r['cnn_improvement'] for r in results]
    mean_imp = np.mean(improvements) if improvements else 0
    positive = sum(1 for i in improvements if i > 0)
    return {
        'status': 'pass',
        'detail': f'mean_cnn_improvement={mean_imp:+.4f}, positive={positive}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1012_dual_branch_cnn(patients, detail=False):
    """Dual-branch CNN: separate glucose and physics encoders.

    Tests whether independent feature extraction prevents channel interference.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        train, val = split_chronological([g_win, phys_win, targets])

        # Single branch baseline (concatenated)
        combined = np.concatenate([g_win, phys_win], axis=2)
        train_c, val_c = split_chronological([combined, targets])
        model_single = SingleBranchCNN(in_channels=5, seq_len=24)
        r_single = train_cnn_model(model_single, train_c, val_c, epochs=60)

        # Dual branch
        model_dual = PhysicsCNN(glucose_channels=1, physics_channels=4, seq_len=24)
        r_dual = train_cnn_model(model_dual, train, val, epochs=60, multi_input=True)

        res = {
            'patient': p['name'],
            'n_windows': len(g_win),
            'r2_single_cnn': round(r_single['r2'], 4),
            'r2_dual_cnn': round(r_dual['r2'], 4),
            'improvement': round(r_dual['r2'] - r_single['r2'], 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: single={r_single['r2']:.4f} dual={r_dual['r2']:.4f} Δ={r_dual['r2']-r_single['r2']:+.4f}")

    improvements = [r['improvement'] for r in results]
    mean_imp = np.mean(improvements) if improvements else 0
    positive = sum(1 for i in improvements if i > 0)
    return {
        'status': 'pass',
        'detail': f'mean_dual_improvement={mean_imp:+.4f}, positive={positive}/{len(results)}',
        'results': {'per_patient': results},
    }


def exp_1013_film_conditioned_cnn(patients, detail=False):
    """Physics-conditioned CNN using FiLM (Feature-wise Linear Modulation).

    Physics summary vector conditions the glucose encoder — the glucose
    processing changes based on current metabolic state.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        # Physics summary: mean of physics channels over window
        physics_summary = phys_win.mean(axis=1)  # (N, 4)

        train, val = split_chronological([g_win, physics_summary, targets])

        # FiLM-conditioned CNN
        model = PhysicsConditionedCNN(glucose_channels=1, physics_dim=4, seq_len=24)
        r_film = train_cnn_model(model, train, val, epochs=60, multi_input=True)

        # Baseline: glucose-only CNN
        train_g, val_g = split_chronological([g_win, targets])
        model_base = SingleBranchCNN(in_channels=1, seq_len=24)
        r_base = train_cnn_model(model_base, train_g, val_g, epochs=60)

        res = {
            'patient': p['name'],
            'r2_glucose_cnn': round(r_base['r2'], 4),
            'r2_film_cnn': round(r_film['r2'], 4),
            'improvement': round(r_film['r2'] - r_base['r2'], 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r_base['r2']:.4f} film={r_film['r2']:.4f} Δ={r_film['r2']-r_base['r2']:+.4f}")

    improvements = [r['improvement'] for r in results]
    mean_imp = np.mean(improvements) if improvements else 0
    return {
        'status': 'pass',
        'detail': f'mean_film_improvement={mean_imp:+.4f}',
        'results': {'per_patient': results},
    }


def exp_1014_conservation_penalized(patients, detail=False):
    """Conservation-penalized CNN: auxiliary loss for physics consistency.

    Multi-task: predict glucose AND conservation violation magnitude.
    Hypothesis: physics regularization improves generalization.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, cons_viols = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        combined = np.concatenate([g_win, phys_win], axis=2)  # (N, 24, 5)
        cons_norm = cons_viols / cons_viols.std() if cons_viols.std() > 0 else cons_viols

        # Standard CNN (no conservation)
        train_std, val_std = split_chronological([combined, targets])
        model_std = SingleBranchCNN(in_channels=5, seq_len=24)
        r_std = train_cnn_model(model_std, train_std, val_std, epochs=60)

        # Conservation-penalized CNN
        train_cp, val_cp = split_chronological([combined, targets, cons_norm])
        model_cp = ConservationPenalizedCNN(in_channels=5, seq_len=24)
        r_cp = train_cnn_model(model_cp, train_cp, val_cp, epochs=60,
                               conservation=True, conservation_weight=0.1)

        res = {
            'patient': p['name'],
            'r2_standard': round(r_std['r2'], 4),
            'r2_conservation': round(r_cp['r2'], 4),
            'improvement': round(r_cp['r2'] - r_std['r2'], 4),
            'mean_violation': round(float(cons_viols.mean()), 3),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: std={r_std['r2']:.4f} cons={r_cp['r2']:.4f} Δ={r_cp['r2']-r_std['r2']:+.4f}")

    improvements = [r['improvement'] for r in results]
    mean_imp = np.mean(improvements) if improvements else 0
    return {
        'status': 'pass',
        'detail': f'mean_conservation_improvement={mean_imp:+.4f}',
        'results': {'per_patient': results},
    }


def exp_1015_dia_curve_optimization(patients, detail=False):
    """Optimize DIA curve parameters per patient to minimize conservation violations.

    Tests DIA values from 3.0 to 8.0 hours and measures which minimizes the
    residual between predicted and actual glucose changes.
    """
    results = []
    for p in patients:
        dia_results = {}
        base_dia = p['df'].attrs.get('patient_dia', 6.0)

        for test_dia in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]:
            # Modify DIA and recompute PK
            df_copy = p['df'].copy()
            df_copy.attrs = dict(p['df'].attrs)
            df_copy.attrs['patient_dia'] = test_dia

            try:
                from cgmencode.continuous_pk import build_continuous_pk_features
                pk_test = build_continuous_pk_features(df_copy)
                if pk_test is None:
                    continue
                n = min(len(pk_test), len(df_copy))
                pk_test = pk_test[:n]
                df_test = df_copy.iloc[:n]

                sd = compute_supply_demand(df_test, pk_test)
                glucose = df_test['glucose'].values
                net = sd['net']

                # Compute conservation violation over 2h windows
                violations = []
                for i in range(0, len(glucose) - 24, 12):
                    if np.isnan(glucose[i:i+24]).any():
                        continue
                    predicted = np.sum(net[i:i+24])
                    actual = glucose[i+23] - glucose[i]
                    violations.append(abs(predicted - actual))

                if violations:
                    dia_results[test_dia] = {
                        'mean_violation': float(np.mean(violations)),
                        'median_violation': float(np.median(violations)),
                    }
            except Exception:
                continue

        if not dia_results:
            continue

        best_dia = min(dia_results, key=lambda d: dia_results[d]['mean_violation'])
        res = {
            'patient': p['name'],
            'current_dia': base_dia,
            'optimal_dia': best_dia,
            'dia_sweep': {str(k): v for k, v in dia_results.items()},
            'violation_reduction': round(
                dia_results[base_dia]['mean_violation'] - dia_results[best_dia]['mean_violation']
                if base_dia in dia_results else 0, 2),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: current_dia={base_dia} optimal={best_dia} "
                  f"violation_reduction={res['violation_reduction']:+.1f}")

    return {
        'status': 'pass',
        'detail': f'patients={len(results)}, dia_shifts={sum(1 for r in results if r["optimal_dia"] != r["current_dia"])}',
        'results': {'per_patient': results},
    }


def exp_1016_fidelity_weighted_training(patients, detail=False):
    """Down-weight training samples from low-fidelity periods.

    Use conservation violation as proxy for sample quality. High-violation
    periods have unreliable physics features, so weight them less.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, cons_viols = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        combined = np.concatenate([g_win, phys_win], axis=2)
        train, val = split_chronological([combined, targets, cons_viols])

        train_X = train[0].reshape(len(train[0]), -1)
        val_X = val[0].reshape(len(val[0]), -1)

        # Unweighted Ridge
        ridge_uw = Ridge(alpha=1.0)
        ridge_uw.fit(train_X, train[1])
        r2_unweighted = r2_score(val[1], ridge_uw.predict(val_X))

        # Fidelity-weighted Ridge
        # Weight = 1 / (1 + violation), so high-violation samples get lower weight
        weights = 1.0 / (1.0 + train[2])
        weights = np.nan_to_num(weights, nan=1.0)
        weights = weights / weights.mean()  # normalize
        ridge_w = Ridge(alpha=1.0)
        ridge_w.fit(train_X, train[1], sample_weight=weights)
        r2_weighted = r2_score(val[1], ridge_w.predict(val_X))

        # Threshold-based: discard worst 20% by violation
        threshold = np.percentile(train[2], 80)
        mask = train[2] <= threshold
        ridge_thresh = Ridge(alpha=1.0)
        ridge_thresh.fit(train_X[mask], train[1][mask])
        r2_threshold = r2_score(val[1], ridge_thresh.predict(val_X))

        res = {
            'patient': p['name'],
            'r2_unweighted': round(r2_unweighted, 4),
            'r2_fidelity_weighted': round(r2_weighted, 4),
            'r2_threshold_80pct': round(r2_threshold, 4),
            'improvement_weighted': round(r2_weighted - r2_unweighted, 4),
            'improvement_threshold': round(r2_threshold - r2_unweighted, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: uw={r2_unweighted:.4f} fw={r2_weighted:.4f} th={r2_threshold:.4f}")

    imp_w = [r['improvement_weighted'] for r in results]
    imp_t = [r['improvement_threshold'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_weighted_imp={np.mean(imp_w):+.4f}, mean_threshold_imp={np.mean(imp_t):+.4f}',
        'results': {'per_patient': results},
    }


def exp_1017_cross_patient_cnn(patients, detail=False):
    """Multi-patient CNN with physics normalization.

    Train a single CNN on all patients, normalizing physics features by
    patient-specific ISF/CR to enable cross-patient generalization.
    """
    # Build per-patient windows
    patient_data = {}
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue
        combined = np.concatenate([g_win, phys_win], axis=2)

        # Per-patient normalization of physics channels
        for ch in range(1, 5):  # physics channels
            mu = combined[:, :, ch].mean()
            sigma = combined[:, :, ch].std()
            if sigma > 0:
                combined[:, :, ch] = (combined[:, :, ch] - mu) / sigma

        train, val = split_chronological([combined, targets])
        patient_data[p['name']] = {'train': train, 'val': val, 'n': len(g_win)}

    if len(patient_data) < 3:
        return {'status': 'pass', 'detail': 'insufficient patients', 'results': {}}

    # Per-patient CNN baseline
    per_patient_r2 = {}
    for name, data in patient_data.items():
        model = SingleBranchCNN(in_channels=5, seq_len=24)
        result = train_cnn_model(model, data['train'], data['val'], epochs=60)
        per_patient_r2[name] = result['r2']

    # Multi-patient CNN (LOPO: leave-one-patient-out)
    lopo_r2 = {}
    for test_name in list(patient_data.keys()):
        train_X = np.concatenate([d['train'][0] for n, d in patient_data.items() if n != test_name])
        train_y = np.concatenate([d['train'][1] for n, d in patient_data.items() if n != test_name])
        val_X = patient_data[test_name]['val'][0]
        val_y = patient_data[test_name]['val'][1]

        model = SingleBranchCNN(in_channels=5, seq_len=24)
        result = train_cnn_model(model, [train_X, train_y], [val_X, val_y],
                                 epochs=60, batch_size=512)
        lopo_r2[test_name] = result['r2']

    results = []
    for name in patient_data:
        res = {
            'patient': name,
            'r2_per_patient': round(per_patient_r2.get(name, 0), 4),
            'r2_lopo': round(lopo_r2.get(name, 0), 4),
            'generalization_gap': round(
                per_patient_r2.get(name, 0) - lopo_r2.get(name, 0), 4),
        }
        results.append(res)
        if detail:
            print(f"    {name}: per_pt={res['r2_per_patient']:.4f} lopo={res['r2_lopo']:.4f} gap={res['generalization_gap']:+.4f}")

    gaps = [r['generalization_gap'] for r in results]
    return {
        'status': 'pass',
        'detail': f'mean_gap={np.mean(gaps):+.4f}',
        'results': {'per_patient': results},
    }


def exp_1018_window_size_sweep(patients, detail=False):
    """Sweep history window sizes for CNN with physics.

    Test 1h, 2h, 4h, 6h history windows to find optimal.
    """
    results = []
    window_sizes = {'1h': 12, '2h': 24, '4h': 48, '6h': 72}

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        patient_results = {}

        for wname, wsteps in window_sizes.items():
            g_win, pk_win, phys_win, targets, _ = build_windowed_data(
                p['df'], p['pk'], sd, history_steps=wsteps, horizon_steps=12, stride=6)
            if len(g_win) < 200:
                continue

            combined = np.concatenate([g_win, phys_win], axis=2)
            train, val = split_chronological([combined, targets])

            # Ridge (fast baseline)
            train_flat = train[0].reshape(len(train[0]), -1)
            val_flat = val[0].reshape(len(val[0]), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(train_flat, train[1])
            r2_ridge = r2_score(val[1], ridge.predict(val_flat))

            # CNN
            model = SingleBranchCNN(in_channels=5, seq_len=wsteps)
            cnn_result = train_cnn_model(model, train, val, epochs=50)

            patient_results[wname] = {
                'r2_ridge': round(r2_ridge, 4),
                'r2_cnn': round(cnn_result['r2'], 4),
                'n_windows': len(g_win),
            }

        if patient_results:
            best_window = max(patient_results, key=lambda w: patient_results[w]['r2_cnn'])
            res = {
                'patient': p['name'],
                'window_results': patient_results,
                'best_window': best_window,
            }
            results.append(res)
            if detail:
                for wn, wr in patient_results.items():
                    mark = ' ★' if wn == best_window else ''
                    print(f"    {p['name']} {wn}: Ridge={wr['r2_ridge']:.4f} CNN={wr['r2_cnn']:.4f}{mark}")

    best_counts = {}
    for r in results:
        bw = r['best_window']
        best_counts[bw] = best_counts.get(bw, 0) + 1

    return {
        'status': 'pass',
        'detail': f'best_window_counts={best_counts}',
        'results': {'per_patient': results},
    }


def exp_1019_pk_channel_ablation(patients, detail=False):
    """Ablation study: which physics channels contribute most?

    Test all single-channel additions to find which supply/demand/hepatic/net
    is most valuable, then test all combinations.
    """
    channel_names = ['supply', 'demand', 'hepatic', 'net_balance']
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        train_g, val_g = split_chronological([g_win, targets])

        # Glucose-only baseline
        train_flat = train_g[0].reshape(len(train_g[0]), -1)
        val_flat = val_g[0].reshape(len(val_g[0]), -1)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(train_flat, train_g[1])
        r2_base = r2_score(val_g[1], ridge_base.predict(val_flat))

        # Single channel additions
        channel_r2s = {}
        for ch_idx, ch_name in enumerate(channel_names):
            aug = np.concatenate([g_win, phys_win[:, :, ch_idx:ch_idx+1]], axis=2)
            train_a, val_a = split_chronological([aug, targets])
            train_flat = train_a[0].reshape(len(train_a[0]), -1)
            val_flat = val_a[0].reshape(len(val_a[0]), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(train_flat, train_a[1])
            channel_r2s[ch_name] = r2_score(val_a[1], ridge.predict(val_flat))

        # All 4 channels
        aug_all = np.concatenate([g_win, phys_win], axis=2)
        train_all, val_all = split_chronological([aug_all, targets])
        train_flat = train_all[0].reshape(len(train_all[0]), -1)
        val_flat = val_all[0].reshape(len(val_all[0]), -1)
        ridge_all = Ridge(alpha=1.0)
        ridge_all.fit(train_flat, train_all[1])
        r2_all = r2_score(val_all[1], ridge_all.predict(val_flat))

        best_single = max(channel_r2s, key=channel_r2s.get)
        res = {
            'patient': p['name'],
            'r2_glucose_only': round(r2_base, 4),
            'r2_per_channel': {k: round(v, 4) for k, v in channel_r2s.items()},
            'r2_all_channels': round(r2_all, 4),
            'best_single_channel': best_single,
            'best_single_improvement': round(channel_r2s[best_single] - r2_base, 4),
        }
        results.append(res)
        if detail:
            parts = ' '.join(f'{k[:3]}={v:.4f}' for k, v in channel_r2s.items())
            print(f"    {p['name']}: base={r2_base:.4f} {parts} all={r2_all:.4f} best={best_single}")

    # Aggregate best channels
    best_counts = {}
    for r in results:
        bc = r['best_single_channel']
        best_counts[bc] = best_counts.get(bc, 0) + 1

    return {
        'status': 'pass',
        'detail': f'best_channel_counts={best_counts}',
        'results': {'per_patient': results},
    }


def exp_1020_grand_benchmark(patients, detail=False):
    """Grand benchmark: all architectures compared on same data.

    Ridge vs CNN vs Dual-Branch vs FiLM, with and without physics.
    Definitive comparison across all patients.
    """
    results = []
    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        g_win, pk_win, phys_win, targets, _ = build_windowed_data(
            p['df'], p['pk'], sd, history_steps=24, horizon_steps=12, stride=6)
        if len(g_win) < 200:
            continue

        combined = np.concatenate([g_win, phys_win], axis=2)
        physics_summary = phys_win.mean(axis=1)

        # All splits
        train_c, val_c = split_chronological([combined, targets])
        train_g, val_g = split_chronological([g_win, targets])
        train_gp, val_gp = split_chronological([g_win, phys_win, targets])
        train_film, val_film = split_chronological([g_win, physics_summary, targets])

        # 1. Ridge glucose-only
        ridge_g = Ridge(alpha=1.0)
        train_flat = train_g[0].reshape(len(train_g[0]), -1)
        val_flat = val_g[0].reshape(len(val_g[0]), -1)
        ridge_g.fit(train_flat, train_g[1])
        r2_ridge_g = r2_score(val_g[1], ridge_g.predict(val_flat))

        # 2. Ridge with physics
        ridge_p = Ridge(alpha=1.0)
        train_flat = train_c[0].reshape(len(train_c[0]), -1)
        val_flat = val_c[0].reshape(len(val_c[0]), -1)
        ridge_p.fit(train_flat, train_c[1])
        r2_ridge_p = r2_score(val_c[1], ridge_p.predict(val_flat))

        # 3. CNN glucose-only
        model_cnn_g = SingleBranchCNN(in_channels=1, seq_len=24)
        r_cnn_g = train_cnn_model(model_cnn_g, train_g, val_g, epochs=50)

        # 4. CNN with physics
        model_cnn_p = SingleBranchCNN(in_channels=5, seq_len=24)
        r_cnn_p = train_cnn_model(model_cnn_p, train_c, val_c, epochs=50)

        # 5. Dual-branch CNN
        model_dual = PhysicsCNN(glucose_channels=1, physics_channels=4, seq_len=24)
        r_dual = train_cnn_model(model_dual, train_gp, val_gp, epochs=50, multi_input=True)

        # 6. FiLM-conditioned CNN
        model_film = PhysicsConditionedCNN(glucose_channels=1, physics_dim=4, seq_len=24)
        r_film = train_cnn_model(model_film, train_film, val_film, epochs=50, multi_input=True)

        benchmarks = {
            'ridge_glucose': round(r2_ridge_g, 4),
            'ridge_physics': round(r2_ridge_p, 4),
            'cnn_glucose': round(r_cnn_g['r2'], 4),
            'cnn_physics': round(r_cnn_p['r2'], 4),
            'dual_branch': round(r_dual['r2'], 4),
            'film_conditioned': round(r_film['r2'], 4),
        }
        best_method = max(benchmarks, key=benchmarks.get)

        res = {
            'patient': p['name'],
            'n_windows': len(g_win),
            'benchmarks': benchmarks,
            'best_method': best_method,
            'best_r2': benchmarks[best_method],
        }
        results.append(res)
        if detail:
            parts = ' '.join(f'{k}={v:.3f}' for k, v in benchmarks.items())
            print(f"    {p['name']}: {parts} ★{best_method}")

    # Aggregate
    method_wins = {}
    for r in results:
        bm = r['best_method']
        method_wins[bm] = method_wins.get(bm, 0) + 1

    mean_r2s = {}
    for method in ['ridge_glucose', 'ridge_physics', 'cnn_glucose', 'cnn_physics', 'dual_branch', 'film_conditioned']:
        vals = [r['benchmarks'][method] for r in results]
        mean_r2s[method] = round(np.mean(vals), 4) if vals else 0

    return {
        'status': 'pass',
        'detail': f'method_wins={method_wins}, mean_r2s={mean_r2s}',
        'results': {'per_patient': results, 'mean_r2s': mean_r2s, 'method_wins': method_wins},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1011', 'CNN with Decomposed Physics', exp_1011_cnn_decomposed_physics),
    ('EXP-1012', 'Dual-Branch CNN', exp_1012_dual_branch_cnn),
    ('EXP-1013', 'FiLM-Conditioned CNN', exp_1013_film_conditioned_cnn),
    ('EXP-1014', 'Conservation-Penalized CNN', exp_1014_conservation_penalized),
    ('EXP-1015', 'DIA Curve Optimization', exp_1015_dia_curve_optimization),
    ('EXP-1016', 'Fidelity-Weighted Training', exp_1016_fidelity_weighted_training),
    ('EXP-1017', 'Cross-Patient CNN', exp_1017_cross_patient_cnn),
    ('EXP-1018', 'Window Size Sweep', exp_1018_window_size_sweep),
    ('EXP-1019', 'PK Channel Ablation', exp_1019_pk_channel_ablation),
    ('EXP-1020', 'Grand Benchmark', exp_1020_grand_benchmark),
]


def main():
    parser = argparse.ArgumentParser(description='EXP-1011 to EXP-1020: CNN + Physics')
    parser.add_argument('--detail', action='store_true', help='Print per-patient detail')
    parser.add_argument('--save', action='store_true', help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, help='Run single experiment (e.g. EXP-1011)')
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
            status = result.get('status', 'unknown')
            detail_str = result.get('detail', '')
            print(f"  Status: {status}")
            print(f"  Detail: {detail_str}")
            print(f"  Time: {elapsed:.1f}s")

            if args.save:
                save_data = {
                    'experiment': exp_id,
                    'name': name,
                    'status': status,
                    'detail': detail_str,
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
