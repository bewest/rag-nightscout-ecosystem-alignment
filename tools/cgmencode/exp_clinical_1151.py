#!/usr/bin/env python3
"""EXP-1151 to EXP-1160: PK Lead Exploitation & Frontier Refinement.

Campaign status after 150 experiments:
- SOTA: R²=0.581 (XGBoost→LSTM pipeline, single split)
- 5-fold CV: R²=0.549 (definitive)
- Biggest discovery: PK lead 45min gives +0.042 R² (EXP-1144)
- Winners: derivatives(+0.011), time-of-day(+0.008), dawn(+0.009),
           interactions(+0.006), LSTM residual(+0.024), PK lead(+0.042)
- Dead ends: extended windows, stacking, online learning, Huber loss

This batch systematically exploits the PK lead discovery:
  EXP-1151: PK Lead + Combined Features ★★★★★
  EXP-1152: PK Lead + Stabilized LSTM Pipeline ★★★★
  EXP-1153: Fine-Grained PK Lead Optimization ★★★
  EXP-1154: PK Lead 5-Fold CV ★★★★
  EXP-1155: Full SOTA Pipeline ★★★★★
  EXP-1156: Asymmetric Lead by Channel Type ★★★
  EXP-1157: Lead + Lag Multi-View ★★★
  EXP-1158: Per-Patient Adaptive Lead Selection ★★★
  EXP-1159: PK Lead + Multi-Window Fusion ★★★★
  EXP-1160: Ablation: Which PK Channels Benefit from Lead? ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1151 --detail --save --max-patients 11
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
# Shared helpers
# ---------------------------------------------------------------------------

class ResidualLSTM(nn.Module):
    def __init__(self, hidden=32, n_layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True, num_layers=n_layers,
                           dropout=dropout if n_layers > 1 else 0.0)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


def prepare_patient_raw(p):
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    return glucose, physics


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def compute_mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def make_xgb(n_estimators=200, max_depth=3, learning_rate=0.08, **kwargs):
    if not XGB_AVAILABLE:
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=n_estimators, max_depth=max_depth,
            learning_rate=learning_rate, random_state=42)
    return xgb.XGBRegressor(
        n_estimators=n_estimators, max_depth=max_depth,
        learning_rate=learning_rate, tree_method='hist',
        device='cuda', random_state=42, verbosity=0, **kwargs)


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:], y[:s1], y[s1:s2], y[s2:])


def get_hour(p, idx):
    """Get hour of day for a given index."""
    df = p['df']
    if 'date' in df.columns:
        try:
            ts = np.datetime64(df['date'].values[idx], 'ns')
            return int((ts.astype('datetime64[h]') - ts.astype('datetime64[D]')).astype(int))
        except Exception:
            pass
    if df.index.dtype == 'datetime64[ns]':
        try:
            ts = df.index[idx]
            return ts.hour
        except Exception:
            pass
    return (idx * 5 // 60) % 24


def compute_derivative_features(g_win):
    """Compute derivative features from a glucose window."""
    d1 = np.diff(g_win)
    d2 = np.diff(d1) if len(d1) > 1 else np.array([0.0])
    feats = [
        d1[-1] if len(d1) > 0 else 0,
        np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1) if len(d1) > 0 else 0,
        np.mean(d1[-12:]) if len(d1) >= 12 else np.mean(d1) if len(d1) > 0 else 0,
        d2[-1] if len(d2) > 0 else 0,
        np.mean(d2[-6:]) if len(d2) >= 6 else np.mean(d2) if len(d2) > 0 else 0,
        np.average(d1[-6:], weights=np.exp(np.linspace(-1, 0, min(6, len(d1))))) if len(d1) > 0 else 0,
        np.std(g_win[-12:]) if len(g_win) >= 12 else np.std(g_win),
        np.std(g_win[-6:]) if len(g_win) >= 6 else np.std(g_win),
        np.max(np.abs(d1[-6:])) if len(d1) >= 6 else np.max(np.abs(d1)) if len(d1) > 0 else 0,
        np.sum(np.diff(np.sign(d1[-12:])) != 0) / 12.0 if len(d1) >= 12 else 0,
    ]
    return feats


def compute_time_features(hour):
    """Compute time-of-day + dawn features."""
    hour_rad = 2 * np.pi * hour / 24.0
    dawn_proximity = np.exp(-((hour - 5.0) ** 2) / (2 * 1.5 ** 2))
    dawn_ramp = max(0, min(1, (hour - 3) / 4.0)) if 3 <= hour <= 7 else 0.0
    post_dawn = max(0, min(1, (hour - 7) / 3.0)) if 7 <= hour <= 10 else 0.0
    cortisol = 0.5 * (1 + np.cos(2 * np.pi * (hour - 8) / 24))
    return [
        np.sin(hour_rad), np.cos(hour_rad),
        1.0 if 3 <= hour < 7 else 0.0,
        1.0 if 7 <= hour < 12 else 0.0,
        1.0 if 12 <= hour < 17 else 0.0,
        1.0 if 17 <= hour < 22 else 0.0,
        1.0 if hour >= 22 or hour < 3 else 0.0,
        dawn_proximity, dawn_ramp, post_dawn, cortisol,
    ]


def compute_interaction_features(g_win, pk_win):
    """Compute insulin-glucose interaction features."""
    iob = pk_win[:, 0]
    activity = pk_win[:, 1]
    cob = pk_win[:, 6]
    carb_act = pk_win[:, 7]
    g_last = g_win[-1]
    g_mean = np.mean(g_win)
    d1 = np.diff(g_win)
    g_trend = np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1) if len(d1) > 0 else 0

    return [
        g_last * np.mean(iob),
        g_last * np.mean(cob),
        g_trend * np.mean(iob),
        g_trend * np.mean(activity),
        g_last * np.mean(activity),
        g_mean * np.mean(carb_act),
        np.mean(iob) * np.mean(cob),
        g_trend * np.mean(carb_act),
        np.mean(iob) / (np.mean(cob) + 1e-6),
        np.mean(activity) / (np.mean(carb_act) + 1e-6),
    ]


def build_enhanced_features(p, glucose, physics, window=WINDOW, horizon=HORIZON,
                            stride=STRIDE, include_time=True, include_deriv=True,
                            include_interactions=True, pk_lead_steps=0):
    """Build features with all proven enhancements and optional PK lead."""
    g = glucose / GLUCOSE_SCALE
    pk = p['pk']
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    max_i = n - window - horizon - pk_lead_steps
    for i in range(0, max_i, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        # PK with optional lead shift
        pk_start = i + pk_lead_steps
        pk_end = pk_start + window
        if pk_end > n:
            continue
        pk_win = pk[pk_start:pk_end]
        if np.isnan(pk_win).any():
            pk_win = np.nan_to_num(pk_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]

        # Base features
        supply = p_win[:, 0]
        demand = p_win[:, 1]
        hepatic = p_win[:, 2]
        net = p_win[:, 3]
        g_mean = np.mean(g_win)

        base = np.concatenate([g_win, p_win.ravel()])

        # Physics interactions
        phys_inter = np.array([
            np.mean(supply * demand), np.mean(supply * g_mean),
            np.mean(demand * g_mean),
            np.mean(np.diff(net)) if len(net) > 1 else 0.0,
            np.mean(hepatic * supply),
        ])

        # Stats
        g_std = np.std(g_win)
        g_min, g_max = np.min(g_win), np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        # PK summary features (from lead-shifted PK)
        pk_mean = np.mean(pk_win, axis=0)  # 8 channels
        pk_last = pk_win[-1]               # 8 channels

        parts = [base, phys_inter, stats, pk_mean, pk_last]

        if include_deriv:
            parts.append(np.array(compute_derivative_features(g_win)))

        if include_time:
            hour = get_hour(p, i + window - 1)
            parts.append(np.array(compute_time_features(hour)))

        if include_interactions:
            parts.append(np.array(compute_interaction_features(g_win, pk_win)))

        feat = np.concatenate(parts)
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def build_lead_windows_basic(glucose, pk, physics, lead_steps=9,
                             window=WINDOW, horizon=HORIZON, stride=STRIDE):
    """Build basic windows with PK lead shift (no enhanced features)."""
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon - lead_steps, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)

        pk_start = i + lead_steps
        pk_end = pk_start + window
        if pk_end > n:
            continue
        pk_win = pk[pk_start:pk_end]
        if np.isnan(pk_win).any():
            pk_win = np.nan_to_num(pk_win, nan=0.0)

        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]
        pk_mean = np.mean(pk_win, axis=0)
        feat = np.concatenate([g_win, p_win.ravel(), pk_mean])
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def train_lstm_residual(residuals_val, residuals_test, seq_len=12, epochs=10,
                        hidden=32, dropout=0.0, weight_decay=1e-4,
                        patience=15, clip_grad=1.0):
    """Train LSTM on validation residuals, predict test corrections."""
    if len(residuals_val) < seq_len + 10:
        return np.zeros_like(residuals_test)

    X_seq, y_seq = [], []
    for i in range(len(residuals_val) - seq_len):
        X_seq.append(residuals_val[i:i + seq_len])
        y_seq.append(residuals_val[i + seq_len])
    X_seq = torch.FloatTensor(np.array(X_seq)).unsqueeze(-1).to(DEVICE)
    y_seq = torch.FloatTensor(np.array(y_seq)).to(DEVICE)

    model = ResidualLSTM(hidden=hidden, dropout=dropout).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=weight_decay)
    loss_fn = nn.MSELoss()

    best_loss = float('inf')
    best_state = None
    wait = 0

    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        pred = model(X_seq)
        loss = loss_fn(pred, y_seq)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip_grad)
        opt.step()

        cur_loss = loss.item()
        if cur_loss < best_loss:
            best_loss = cur_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    corrections = np.zeros(len(residuals_test))
    buffer = list(residuals_val[-seq_len:])
    with torch.no_grad():
        for i in range(len(residuals_test)):
            seq = torch.FloatTensor(np.array(buffer[-seq_len:])).unsqueeze(0).unsqueeze(-1).to(DEVICE)
            corrections[i] = model(seq).item()
            buffer.append(residuals_test[i])
    return corrections


# ---------------------------------------------------------------------------
# EXP-1151: PK Lead + Combined Features
# ---------------------------------------------------------------------------

def exp_1151_pk_lead_combined(patients, detail=False):
    """Combine PK lead (45 min) with all enhanced features — key experiment."""
    per_patient = {}
    scores = {'base': [], 'enhanced': [], 'lead_enhanced': []}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        # Base: no enhancements, no lead
        X_base, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=False, include_deriv=False,
            include_interactions=False, pk_lead_steps=0)
        # Enhanced: all enhancements, no lead
        X_enh, y_e, g_cur_e = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, pk_lead_steps=0)
        # Lead + enhanced: all enhancements + 45min PK lead
        X_lead, y_l, g_cur_l = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, pk_lead_steps=9)

        results_p = {}
        for X_feat, y_f, g_f, key in [
            (X_base, y, g_cur, 'base'),
            (X_enh, y_e, g_cur_e, 'enhanced'),
            (X_lead, y_l, g_cur_l, 'lead_enhanced'),
        ]:
            if len(X_feat) < 100:
                results_p[key] = 0.0
                continue
            X_feat = np.nan_to_num(X_feat, nan=0.0)
            y_dg = y_f - g_f
            X_tr, X_te, y_tr, y_te = split_data(X_feat, y_dg)
            g_cur_te = g_f[len(X_feat) - len(X_te):]

            xgb_m = make_xgb(n_estimators=300, max_depth=3)
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            scores[key].append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" enh={r.get('enhanced',0):.4f}"
                  f" lead+enh={r.get('lead_enhanced',0):.4f}"
                  f" Δ={r.get('lead_enhanced',0) - r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0 for k, v in scores.items()}
    wins = sum(1 for p in per_patient.values()
               if p.get('lead_enhanced', 0) > p.get('base', 0))

    return {
        'name': 'EXP-1151',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} enh={means['enhanced']:.4f}"
                   f" lead+enh={means['lead_enhanced']:.4f}"
                   f" Δ={means['lead_enhanced']-means['base']:+.4f}"
                   f" (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1152: PK Lead + Stabilized LSTM Pipeline
# ---------------------------------------------------------------------------

def exp_1152_lead_stabilized_lstm(patients, detail=False):
    """PK lead features + XGBoost → LSTM with stronger regularization."""
    per_patient = {}
    scores_xgb, scores_pipeline = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, pk_lead_steps=9)

        if len(X_all) < 200:
            per_patient[pname] = {'xgb': 0, 'pipeline': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X_all, y_dg)
        g_cur_te = g_cur[len(X_all) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # XGBoost with lead features
        xgb_m = make_xgb(n_estimators=300, max_depth=3)
        xgb_m.fit(X_tr, y_tr)
        pred_val = xgb_m.predict(X_val)
        pred_te = xgb_m.predict(X_te)
        r2_xgb = compute_r2(y_abs_te, pred_te + g_cur_te)

        # Stabilized LSTM residual (dropout=0.5, weight_decay=1e-3, patience=10, clip=0.5)
        resid_val = y_val - pred_val
        resid_te = y_te - pred_te
        corrections = train_lstm_residual(
            resid_val, resid_te, seq_len=12, epochs=30,
            hidden=32, dropout=0.5, weight_decay=1e-3,
            patience=10, clip_grad=0.5)
        pred_pipeline = pred_te + corrections
        r2_pipeline = compute_r2(y_abs_te, pred_pipeline + g_cur_te)

        per_patient[pname] = {
            'xgb': r2_xgb, 'pipeline': r2_pipeline,
            'delta_lstm': r2_pipeline - r2_xgb,
        }
        scores_xgb.append(r2_xgb)
        scores_pipeline.append(r2_pipeline)

        if detail:
            print(f"  {pname}: xgb={r2_xgb:.4f} pipeline={r2_pipeline:.4f}"
                  f" Δ_lstm={r2_pipeline - r2_xgb:+.4f}")

    mean_x = float(np.mean(scores_xgb)) if scores_xgb else 0
    mean_p = float(np.mean(scores_pipeline)) if scores_pipeline else 0
    wins = sum(1 for p in per_patient.values()
               if p.get('pipeline', 0) > p.get('xgb', 0))

    return {
        'name': 'EXP-1152',
        'status': 'pass',
        'detail': (f"xgb={mean_x:.4f} pipeline={mean_p:.4f}"
                   f" Δ={mean_p-mean_x:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'xgb': mean_x, 'pipeline': mean_p},
    }


# ---------------------------------------------------------------------------
# EXP-1153: Fine-Grained PK Lead Optimization
# ---------------------------------------------------------------------------

def exp_1153_fine_grained_lead(patients, detail=False):
    """Test lead times from 15 to 75 min in 5-min steps (3 to 15 steps)."""
    per_patient = {}
    lead_range = list(range(3, 16))  # 3..15 steps = 15..75 min
    lead_names = {s: f"lead{s*5}min" for s in lead_range}
    all_scores = {lead_names[s]: [] for s in lead_range}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pk = p['pk']
        pname = p['name']

        results_p = {}
        for lead_steps in lead_range:
            X, y, g_cur = build_lead_windows_basic(
                glucose, pk, physics, lead_steps=lead_steps)

            if len(X) < 100:
                results_p[lead_names[lead_steps]] = 0.0
                continue

            X = np.nan_to_num(X, nan=0.0)
            y_dg = y - g_cur
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur[len(X) - len(X_te):]

            xgb_m = make_xgb()
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[lead_names[lead_steps]] = r2
            all_scores[lead_names[lead_steps]].append(r2)

        per_patient[pname] = results_p
        if detail:
            best_key = max(results_p, key=results_p.get) if results_p else 'none'
            best_val = results_p.get(best_key, 0)
            print(f"  {pname}: best={best_key} R²={best_val:.4f}")

    means = {k: float(np.mean(v)) if v else 0 for k, v in all_scores.items()}
    best_lead = max(means, key=means.get) if means else 'none'
    optimal_minutes = int(best_lead.replace('lead', '').replace('min', '')) if best_lead != 'none' else 45

    # Per-patient optimal lead
    patient_optima = {}
    for pname, results_p in per_patient.items():
        if results_p:
            best = max(results_p, key=results_p.get)
            patient_optima[pname] = best

    return {
        'name': 'EXP-1153',
        'status': 'pass',
        'detail': (f"best_mean={best_lead}(R²={means.get(best_lead,0):.4f})"
                   f" optimal={optimal_minutes}min"
                   f" range=[{min(means.values()):.4f},{max(means.values()):.4f}]"),
        'per_patient': per_patient,
        'results': {'means': means, 'best_lead': best_lead,
                    'optimal_minutes': optimal_minutes,
                    'patient_optima': patient_optima},
    }


# ---------------------------------------------------------------------------
# EXP-1154: PK Lead 5-Fold CV
# ---------------------------------------------------------------------------

def exp_1154_lead_cv(patients, detail=False):
    """Rigorous 5-fold TimeSeriesSplit validation of PK lead (45min)."""
    from sklearn.model_selection import TimeSeriesSplit

    per_patient = {}
    all_base_cv, all_lead_cv = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pk = p['pk']
        pname = p['name']

        # Base (no lead)
        X_base, y_base, g_cur_base = build_lead_windows_basic(
            glucose, pk, physics, lead_steps=0)
        # Lead 45min
        X_lead, y_lead, g_cur_lead = build_lead_windows_basic(
            glucose, pk, physics, lead_steps=9)

        results_p = {}
        for X, y, g_cur, key in [
            (X_base, y_base, g_cur_base, 'base'),
            (X_lead, y_lead, g_cur_lead, 'lead45'),
        ]:
            if len(X) < 200:
                results_p[key] = {'mean': 0, 'std': 0}
                continue

            X = np.nan_to_num(X, nan=0.0)
            y_dg = y - g_cur

            tscv = TimeSeriesSplit(n_splits=5)
            fold_scores = []
            for train_idx, test_idx in tscv.split(X):
                X_tr, X_te = X[train_idx], X[test_idx]
                y_tr, y_te = y_dg[train_idx], y_dg[test_idx]
                g_te = g_cur[test_idx]

                xgb_m = make_xgb(n_estimators=300, max_depth=3)
                xgb_m.fit(X_tr, y_tr)
                pred = xgb_m.predict(X_te) + g_te
                y_abs = y_te + g_te
                fold_scores.append(compute_r2(y_abs, pred))

            results_p[key] = {
                'mean': float(np.mean(fold_scores)),
                'std': float(np.std(fold_scores)),
                'folds': fold_scores,
            }

        per_patient[pname] = results_p
        base_mean = results_p.get('base', {}).get('mean', 0)
        lead_mean = results_p.get('lead45', {}).get('mean', 0)
        all_base_cv.append(base_mean)
        all_lead_cv.append(lead_mean)

        if detail:
            lead_std = results_p.get('lead45', {}).get('std', 0)
            print(f"  {pname}: base_cv={base_mean:.4f}"
                  f" lead_cv={lead_mean:.4f}±{lead_std:.3f}"
                  f" Δ={lead_mean - base_mean:+.4f}")

    mean_base = float(np.mean(all_base_cv)) if all_base_cv else 0
    mean_lead = float(np.mean(all_lead_cv)) if all_lead_cv else 0
    wins = sum(1 for p in per_patient.values()
               if p.get('lead45', {}).get('mean', 0) > p.get('base', {}).get('mean', 0))

    return {
        'name': 'EXP-1154',
        'status': 'pass',
        'detail': (f"5-fold CV: base={mean_base:.4f} lead45={mean_lead:.4f}"
                   f" Δ={mean_lead-mean_base:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'base_cv': mean_base, 'lead_cv': mean_lead,
                    'delta': mean_lead - mean_base},
    }


# ---------------------------------------------------------------------------
# EXP-1155: Full SOTA Pipeline
# ---------------------------------------------------------------------------

def exp_1155_full_sota(patients, detail=False):
    """PK lead 45min + enhanced features + 3 XGBoost ensemble → SOTA attempt."""
    per_patient = {}
    scores_single, scores_ens = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, pk_lead_steps=9)

        if len(X_all) < 200:
            per_patient[pname] = {'xgb_single': 0, 'ensemble': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X_all, y_dg)
        g_cur_te = g_cur[len(X_all) - len(X_te):]
        g_cur_val = g_cur[len(X_tr):len(X_tr) + len(X_val)]
        y_abs_te = y_te + g_cur_te
        y_abs_val = y_val + g_cur_val

        # 3 XGBoost variants with different depths
        configs = [
            {'n_estimators': 300, 'max_depth': 3, 'learning_rate': 0.08},
            {'n_estimators': 300, 'max_depth': 4, 'learning_rate': 0.05},
            {'n_estimators': 300, 'max_depth': 5, 'learning_rate': 0.03},
        ]
        preds_val, preds_te = [], []
        for cfg in configs:
            m = make_xgb(**cfg)
            m.fit(X_tr, y_tr)
            preds_val.append(m.predict(X_val) + g_cur_val)
            preds_te.append(m.predict(X_te) + g_cur_te)

        # Single best (depth 3) for comparison
        r2_single = compute_r2(y_abs_te, preds_te[0])

        # Optimal weight search on validation
        best_r2_val = -999
        best_weights = (0.34, 0.33, 0.33)
        for w1 in np.arange(0, 1.05, 0.1):
            for w2 in np.arange(0, 1.05 - w1, 0.1):
                w3 = 1.0 - w1 - w2
                if w3 < -0.01:
                    continue
                w3 = max(w3, 0.0)
                pred_ens = w1 * preds_val[0] + w2 * preds_val[1] + w3 * preds_val[2]
                r2 = compute_r2(y_abs_val, pred_ens)
                if r2 > best_r2_val:
                    best_r2_val = r2
                    best_weights = (w1, w2, w3)

        pred_ens_te = (best_weights[0] * preds_te[0] +
                       best_weights[1] * preds_te[1] +
                       best_weights[2] * preds_te[2])
        r2_ens = compute_r2(y_abs_te, pred_ens_te)

        per_patient[pname] = {
            'xgb_single': r2_single, 'ensemble': r2_ens,
            'weights': list(best_weights),
            'delta': r2_ens - r2_single,
        }
        scores_single.append(r2_single)
        scores_ens.append(r2_ens)

        if detail:
            w = best_weights
            print(f"  {pname}: single={r2_single:.4f} ens={r2_ens:.4f}"
                  f" Δ={r2_ens - r2_single:+.4f}"
                  f" w=({w[0]:.1f},{w[1]:.1f},{w[2]:.1f})")

    mean_s = float(np.mean(scores_single)) if scores_single else 0
    mean_e = float(np.mean(scores_ens)) if scores_ens else 0
    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)

    return {
        'name': 'EXP-1155',
        'status': 'pass',
        'detail': (f"single={mean_s:.4f} ensemble={mean_e:.4f}"
                   f" Δ={mean_e-mean_s:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'xgb_single': mean_s, 'ensemble': mean_e},
    }


# ---------------------------------------------------------------------------
# EXP-1156: Asymmetric Lead by Channel Type
# ---------------------------------------------------------------------------

def exp_1156_asymmetric_lead(patients, detail=False):
    """Lead insulin channels by 45min but carb channels by only 20min."""
    per_patient = {}
    scores_uniform, scores_asym = [], []

    # PK channel layout: [total_iob(0), total_act(1), basal_iob(2), basal_act(3),
    #                      bolus_iob(4), bolus_act(5), carb_cob(6), carb_act(7)]
    INSULIN_LEAD = 9   # 45 min
    CARB_LEAD = 4      # 20 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        max_lead = max(INSULIN_LEAD, CARB_LEAD)
        results_p = {}

        for mode, label in [('uniform', 'uniform'), ('asymmetric', 'asymmetric')]:
            X_list, y_list, g_cur_list = [], [], []

            for i in range(0, n - WINDOW - HORIZON - max_lead, STRIDE):
                g_win = g[i:i + WINDOW]
                if np.isnan(g_win).mean() > 0.3:
                    continue
                g_win = np.nan_to_num(
                    g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
                p_win = physics[i:i + WINDOW]
                if np.isnan(p_win).any():
                    p_win = np.nan_to_num(p_win, nan=0.0)

                y_val = g[i + WINDOW + HORIZON - 1]
                if np.isnan(y_val):
                    continue

                if mode == 'uniform':
                    pk_start = i + INSULIN_LEAD
                    pk_end = pk_start + WINDOW
                    if pk_end > n:
                        continue
                    pk_win = pk[pk_start:pk_end]
                else:
                    # Asymmetric: insulin channels from lead=9, carb channels from lead=4
                    ins_start = i + INSULIN_LEAD
                    ins_end = ins_start + WINDOW
                    carb_start = i + CARB_LEAD
                    carb_end = carb_start + WINDOW
                    if ins_end > n or carb_end > n:
                        continue
                    pk_ins = pk[ins_start:ins_end, :6]   # channels 0-5
                    pk_carb = pk[carb_start:carb_end, 6:]  # channels 6-7
                    pk_win = np.column_stack([pk_ins, pk_carb])

                if np.isnan(pk_win).any():
                    pk_win = np.nan_to_num(pk_win, nan=0.0)

                g_current = g_win[-1]
                pk_mean = np.mean(pk_win, axis=0)
                feat = np.concatenate([g_win, p_win.ravel(), pk_mean])
                X_list.append(feat)
                y_list.append(y_val)
                g_cur_list.append(g_current)

            if len(X_list) < 100:
                results_p[label] = 0.0
                continue

            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y = np.array(y_list)
            g_cur = np.array(g_cur_list)
            y_dg = y - g_cur
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur[len(X) - len(X_te):]

            xgb_m = make_xgb()
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[label] = r2
            if label == 'uniform':
                scores_uniform.append(r2)
            else:
                scores_asym.append(r2)

        per_patient[pname] = results_p
        if detail:
            delta = results_p.get('asymmetric', 0) - results_p.get('uniform', 0)
            print(f"  {pname}: uniform={results_p.get('uniform',0):.4f}"
                  f" asymmetric={results_p.get('asymmetric',0):.4f}"
                  f" Δ={delta:+.4f}")

    mean_u = float(np.mean(scores_uniform)) if scores_uniform else 0
    mean_a = float(np.mean(scores_asym)) if scores_asym else 0
    wins = sum(1 for p in per_patient.values()
               if p.get('asymmetric', 0) > p.get('uniform', 0))

    return {
        'name': 'EXP-1156',
        'status': 'pass',
        'detail': (f"uniform={mean_u:.4f} asymmetric={mean_a:.4f}"
                   f" Δ={mean_a-mean_u:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'uniform': mean_u, 'asymmetric': mean_a},
    }


# ---------------------------------------------------------------------------
# EXP-1157: Lead + Lag Multi-View
# ---------------------------------------------------------------------------

def exp_1157_lead_lag_multiview(patients, detail=False):
    """Use BOTH current PK (lag0) AND lead45 PK as features — dual temporal view."""
    per_patient = {}
    scores_lag0, scores_lead, scores_dual = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)
        lead_steps = 9

        X_lag0, X_lead, X_dual = [], [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            # Current PK
            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)
            # Lead PK
            pk_lead_start = i + lead_steps
            pk_lead_end = pk_lead_start + WINDOW
            if pk_lead_end > n:
                continue
            pk_lead = pk[pk_lead_start:pk_lead_end]
            if np.isnan(pk_lead).any():
                pk_lead = np.nan_to_num(pk_lead, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base = np.concatenate([g_win, p_win.ravel()])
            pk_cur_mean = np.mean(pk_cur, axis=0)
            pk_lead_mean = np.mean(pk_lead, axis=0)

            # Lag0 only
            feat_lag0 = np.concatenate([base, pk_cur_mean])
            # Lead only
            feat_lead = np.concatenate([base, pk_lead_mean])
            # Dual view: both current and lead
            feat_dual = np.concatenate([base, pk_cur_mean, pk_lead_mean])

            X_lag0.append(feat_lag0)
            X_lead.append(feat_lead)
            X_dual.append(feat_dual)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        for X_arr, key, score_list in [
            (X_lag0, 'lag0', scores_lag0),
            (X_lead, 'lead45', scores_lead),
            (X_dual, 'dual', scores_dual),
        ]:
            if len(X_arr) < 100:
                results_p[key] = 0.0
                continue

            X = np.nan_to_num(np.array(X_arr), nan=0.0)
            y = np.array(y_list)
            g_cur = np.array(g_cur_list)
            y_dg = y - g_cur
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur[len(X) - len(X_te):]

            xgb_m = make_xgb(n_estimators=300, max_depth=3)
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            print(f"  {pname}: lag0={results_p.get('lag0',0):.4f}"
                  f" lead={results_p.get('lead45',0):.4f}"
                  f" dual={results_p.get('dual',0):.4f}"
                  f" Δ_dual={results_p.get('dual',0)-results_p.get('lag0',0):+.4f}")

    mean_l0 = float(np.mean(scores_lag0)) if scores_lag0 else 0
    mean_ld = float(np.mean(scores_lead)) if scores_lead else 0
    mean_du = float(np.mean(scores_dual)) if scores_dual else 0
    wins = sum(1 for p in per_patient.values()
               if p.get('dual', 0) > p.get('lead45', 0))

    return {
        'name': 'EXP-1157',
        'status': 'pass',
        'detail': (f"lag0={mean_l0:.4f} lead45={mean_ld:.4f} dual={mean_du:.4f}"
                   f" Δ_dual_vs_lead={mean_du-mean_ld:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'lag0': mean_l0, 'lead45': mean_ld, 'dual': mean_du},
    }


# ---------------------------------------------------------------------------
# EXP-1158: Per-Patient Adaptive Lead Selection
# ---------------------------------------------------------------------------

def exp_1158_adaptive_lead(patients, detail=False):
    """Train with multiple leads, select best per-patient on val, evaluate on test."""
    per_patient = {}
    scores_fixed, scores_adaptive = [], []
    lead_options = [0, 3, 6, 9, 12]  # 0, 15, 30, 45, 60 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pk = p['pk']
        pname = p['name']
        n = len(glucose)

        max_lead = max(lead_options)
        # Build data for each lead setting
        lead_data = {}
        for ls in lead_options:
            X, y, g_cur = build_lead_windows_basic(
                glucose, pk, physics, lead_steps=ls)
            if len(X) >= 200:
                lead_data[ls] = (
                    np.nan_to_num(X, nan=0.0), y, g_cur)

        if not lead_data:
            per_patient[pname] = {'fixed45': 0, 'adaptive': 0}
            continue

        # For each lead, do 3-way split and evaluate on val
        val_scores = {}
        test_preds = {}
        test_truth = {}
        for ls, (X, y, g_cur) in lead_data.items():
            y_dg = y - g_cur
            X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X, y_dg)
            g_cur_val = g_cur[len(X_tr):len(X_tr) + len(X_val)]
            g_cur_te = g_cur[len(X) - len(X_te):]

            xgb_m = make_xgb(n_estimators=300, max_depth=3)
            xgb_m.fit(X_tr, y_tr)

            pred_val = xgb_m.predict(X_val) + g_cur_val
            y_abs_val = y_val + g_cur_val
            val_scores[ls] = compute_r2(y_abs_val, pred_val)

            pred_te = xgb_m.predict(X_te) + g_cur_te
            y_abs_te = y_te + g_cur_te
            test_preds[ls] = pred_te
            test_truth[ls] = y_abs_te

        # Fixed lead=9 (45 min)
        r2_fixed = compute_r2(test_truth.get(9, np.array([0])),
                              test_preds.get(9, np.array([0]))) if 9 in test_preds else 0

        # Adaptive: select best lead on validation
        best_lead = max(val_scores, key=val_scores.get)
        r2_adaptive = compute_r2(test_truth[best_lead], test_preds[best_lead])

        per_patient[pname] = {
            'fixed45': r2_fixed, 'adaptive': r2_adaptive,
            'best_lead_min': best_lead * 5,
            'val_scores': {f"{k*5}min": v for k, v in val_scores.items()},
            'delta': r2_adaptive - r2_fixed,
        }
        scores_fixed.append(r2_fixed)
        scores_adaptive.append(r2_adaptive)

        if detail:
            print(f"  {pname}: fixed45={r2_fixed:.4f} adaptive={r2_adaptive:.4f}"
                  f" best={best_lead*5}min Δ={r2_adaptive-r2_fixed:+.4f}")

    mean_f = float(np.mean(scores_fixed)) if scores_fixed else 0
    mean_a = float(np.mean(scores_adaptive)) if scores_adaptive else 0
    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)

    # Distribution of optimal leads
    lead_dist = {}
    for p in per_patient.values():
        bl = p.get('best_lead_min', 45)
        lead_dist[bl] = lead_dist.get(bl, 0) + 1

    return {
        'name': 'EXP-1158',
        'status': 'pass',
        'detail': (f"fixed45={mean_f:.4f} adaptive={mean_a:.4f}"
                   f" Δ={mean_a-mean_f:+.4f} (wins={wins}/11)"
                   f" dist={lead_dist}"),
        'per_patient': per_patient,
        'results': {'fixed45': mean_f, 'adaptive': mean_a,
                    'lead_distribution': lead_dist},
    }


# ---------------------------------------------------------------------------
# EXP-1159: PK Lead + Multi-Window Fusion
# ---------------------------------------------------------------------------

def exp_1159_lead_multiwindow(patients, detail=False):
    """Combine PK lead with multi-window summary stats (4h, 6h lookback)."""
    per_patient = {}
    scores_lead, scores_fusion = [], []
    lead_steps = 9  # 45 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_lead_list, X_fuse_list, y_list, g_cur_list = [], [], [], []

        # Need 6h (72 steps) lookback + lead margin
        for i in range(0, n - 72 - HORIZON - lead_steps, STRIDE):
            g_win = g[i + 48:i + 72]  # Last 2h
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i + 48:i + 72]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            # Lead PK from the 2h window region
            pk_lead_start = i + 48 + lead_steps
            pk_lead_end = pk_lead_start + WINDOW
            if pk_lead_end > n:
                continue
            pk_win = pk[pk_lead_start:pk_lead_end]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y_val = g[i + 72 + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            base_lead = np.concatenate([g_win, p_win.ravel(), pk_mean])
            X_lead_list.append(base_lead)

            # Multi-window summary stats
            g_4h = g[i + 24:i + 72]
            g_6h = g[i:i + 72]
            g_4h = np.nan_to_num(g_4h, nan=np.nanmean(g_4h) if np.any(~np.isnan(g_4h)) else 0.4)
            g_6h = np.nan_to_num(g_6h, nan=np.nanmean(g_6h) if np.any(~np.isnan(g_6h)) else 0.4)

            summary_4h = [np.mean(g_4h), np.std(g_4h), np.min(g_4h), np.max(g_4h),
                          np.mean(np.diff(g_4h)) if len(g_4h) > 1 else 0]
            summary_6h = [np.mean(g_6h), np.std(g_6h), np.min(g_6h), np.max(g_6h),
                          np.mean(np.diff(g_6h)) if len(g_6h) > 1 else 0]

            # PK summary from longer windows (with lead)
            pk_4h_start = i + 24 + lead_steps
            pk_4h_end = pk_4h_start + 48
            pk_6h_start = i + lead_steps
            pk_6h_end = pk_6h_start + 72
            if pk_6h_end > n:
                continue
            pk_4h = pk[pk_4h_start:min(pk_4h_end, n)]
            pk_6h = pk[pk_6h_start:min(pk_6h_end, n)]
            pk_4h = np.nan_to_num(pk_4h, nan=0.0)
            pk_6h = np.nan_to_num(pk_6h, nan=0.0)
            pk_summary_4h = np.mean(pk_4h, axis=0).tolist() if len(pk_4h) > 0 else [0.0] * 8
            pk_summary_6h = np.mean(pk_6h, axis=0).tolist() if len(pk_6h) > 0 else [0.0] * 8

            fusion = base_lead.tolist() + summary_4h + summary_6h + pk_summary_4h + pk_summary_6h
            X_fuse_list.append(fusion)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_lead_list) < 100 or len(X_fuse_list) < 100:
            per_patient[pname] = {'lead': 0, 'fusion': 0}
            continue

        # Trim to same length (fusion may be shorter due to extra bounds check)
        min_len = min(len(X_lead_list), len(X_fuse_list))
        X_lead_list = X_lead_list[:min_len]
        X_fuse_list = X_fuse_list[:min_len]
        y_list_trim = y_list[:min_len]
        g_cur_list_trim = g_cur_list[:min_len]

        X_lead = np.nan_to_num(np.array(X_lead_list), nan=0.0)
        X_fuse = np.nan_to_num(np.array(X_fuse_list), nan=0.0)
        y = np.array(y_list_trim)
        g_cur = np.array(g_cur_list_trim)
        y_dg = y - g_cur

        X_tr_l, X_te_l, y_tr, y_te = split_data(X_lead, y_dg)
        X_tr_f, X_te_f, _, _ = split_data(X_fuse, y_dg)
        g_cur_te = g_cur[len(X_lead) - len(X_te_l):]
        y_abs_te = y_te + g_cur_te

        xgb_l = make_xgb(n_estimators=300, max_depth=3)
        xgb_l.fit(X_tr_l, y_tr)
        r2_lead = compute_r2(y_abs_te, xgb_l.predict(X_te_l) + g_cur_te)

        xgb_f = make_xgb(n_estimators=300, max_depth=3)
        xgb_f.fit(X_tr_f, y_tr)
        r2_fusion = compute_r2(y_abs_te, xgb_f.predict(X_te_f) + g_cur_te)

        per_patient[pname] = {
            'lead': r2_lead, 'fusion': r2_fusion,
            'delta': r2_fusion - r2_lead,
        }
        scores_lead.append(r2_lead)
        scores_fusion.append(r2_fusion)

        if detail:
            print(f"  {pname}: lead={r2_lead:.4f} fusion={r2_fusion:.4f}"
                  f" Δ={r2_fusion - r2_lead:+.4f}")

    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)
    mean_l = float(np.mean(scores_lead)) if scores_lead else 0
    mean_f = float(np.mean(scores_fusion)) if scores_fusion else 0

    return {
        'name': 'EXP-1159',
        'status': 'pass',
        'detail': (f"lead={mean_l:.4f} fusion={mean_f:.4f}"
                   f" Δ={mean_f-mean_l:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'lead': mean_l, 'fusion': mean_f},
    }


# ---------------------------------------------------------------------------
# EXP-1160: Ablation: Which PK Channels Benefit from Lead?
# ---------------------------------------------------------------------------

def exp_1160_channel_ablation(patients, detail=False):
    """Test leading individual PK channel groups to find which benefit most."""
    per_patient = {}

    # Channel groups:
    #   IOB: channels 0,2,4 (total_iob, basal_iob, bolus_iob)
    #   Activity: channels 1,3,5 (total_act, basal_act, bolus_act)
    #   Carbs: channels 6,7 (carb_cob, carb_act)
    #   All: channels 0-7
    channel_groups = {
        'no_lead': None,
        'iob_lead': [0, 2, 4],
        'activity_lead': [1, 3, 5],
        'carb_lead': [6, 7],
        'all_lead': list(range(8)),
    }
    all_scores = {k: [] for k in channel_groups}
    lead_steps = 9  # 45 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        results_p = {}
        for group_name, lead_channels in channel_groups.items():
            X_list, y_list, g_cur_list = [], [], []

            for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
                g_win = g[i:i + WINDOW]
                if np.isnan(g_win).mean() > 0.3:
                    continue
                g_win = np.nan_to_num(
                    g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
                p_win = physics[i:i + WINDOW]
                if np.isnan(p_win).any():
                    p_win = np.nan_to_num(p_win, nan=0.0)

                y_val = g[i + WINDOW + HORIZON - 1]
                if np.isnan(y_val):
                    continue

                # Build PK features with selective lead
                pk_cur = pk[i:i + WINDOW].copy()
                if np.isnan(pk_cur).any():
                    pk_cur = np.nan_to_num(pk_cur, nan=0.0)

                if lead_channels is not None:
                    pk_lead_start = i + lead_steps
                    pk_lead_end = pk_lead_start + WINDOW
                    if pk_lead_end > n:
                        continue
                    pk_led = pk[pk_lead_start:pk_lead_end]
                    if np.isnan(pk_led).any():
                        pk_led = np.nan_to_num(pk_led, nan=0.0)
                    # Replace only the selected channels with lead versions
                    for ch in lead_channels:
                        pk_cur[:, ch] = pk_led[:, ch]

                g_current = g_win[-1]
                pk_mean = np.mean(pk_cur, axis=0)
                feat = np.concatenate([g_win, p_win.ravel(), pk_mean])
                X_list.append(feat)
                y_list.append(y_val)
                g_cur_list.append(g_current)

            if len(X_list) < 100:
                results_p[group_name] = 0.0
                continue

            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y = np.array(y_list)
            g_cur = np.array(g_cur_list)
            y_dg = y - g_cur
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur[len(X) - len(X_te):]

            xgb_m = make_xgb()
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[group_name] = r2
            all_scores[group_name].append(r2)

        per_patient[pname] = results_p
        if detail:
            no_lead = results_p.get('no_lead', 0)
            parts = []
            for k in ['iob_lead', 'activity_lead', 'carb_lead', 'all_lead']:
                delta = results_p.get(k, 0) - no_lead
                parts.append(f"{k.replace('_lead','')}={delta:+.4f}")
            print(f"  {pname}: base={no_lead:.4f} " + ' '.join(parts))

    means = {k: float(np.mean(v)) if v else 0 for k, v in all_scores.items()}
    base_r2 = means.get('no_lead', 0)

    # Rank channel contributions
    contributions = {}
    for k in ['iob_lead', 'activity_lead', 'carb_lead', 'all_lead']:
        contributions[k] = means.get(k, 0) - base_r2
    ranked = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
    rank_str = ' > '.join(f"{k.replace('_lead','')}({v:+.4f})" for k, v in ranked)

    return {
        'name': 'EXP-1160',
        'status': 'pass',
        'detail': f"base={base_r2:.4f} {rank_str}",
        'per_patient': per_patient,
        'results': {'means': means, 'contributions': contributions,
                    'ranking': [r[0] for r in ranked]},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1151', 'PK Lead + Combined Features', exp_1151_pk_lead_combined),
    ('EXP-1152', 'PK Lead + Stabilized LSTM Pipeline', exp_1152_lead_stabilized_lstm),
    ('EXP-1153', 'Fine-Grained PK Lead Optimization', exp_1153_fine_grained_lead),
    ('EXP-1154', 'PK Lead 5-Fold CV', exp_1154_lead_cv),
    ('EXP-1155', 'Full SOTA Pipeline', exp_1155_full_sota),
    ('EXP-1156', 'Asymmetric Lead by Channel Type', exp_1156_asymmetric_lead),
    ('EXP-1157', 'Lead + Lag Multi-View', exp_1157_lead_lag_multiview),
    ('EXP-1158', 'Per-Patient Adaptive Lead Selection', exp_1158_adaptive_lead),
    ('EXP-1159', 'PK Lead + Multi-Window Fusion', exp_1159_lead_multiwindow),
    ('EXP-1160', 'Ablation - PK Channel Lead Contribution', exp_1160_channel_ablation),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1151-1160: PK Lead Exploitation & Frontier Refinement')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1151)')
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
                             f"{name.lower().replace(' ', '_').replace('-', '_')}"
                             .replace('/', '_').replace(':', '_'))
                save_path = save_results(save_data, save_name)
                print(f"  → Saved {save_path}")

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
