#!/usr/bin/env python3
"""EXP-1141 to EXP-1150: Combined Winners & Frontier Push.

Campaign status after 140 experiments:
- SOTA: R²=0.581 (XGBoost→LSTM pipeline, single split)
- 5-fold CV: R²=0.549 (definitive)
- Winners: derivatives(+0.011), time-of-day(+0.008), dawn(+0.009),
           interactions(+0.006), LSTM residual(+0.024)
- Dead ends: extended windows, stacking, online learning, Huber loss

This batch combines all proven techniques and explores the frontier:
  EXP-1141: Combined Feature Engineering (all winners) ★★★★
  EXP-1142: Combined Features + LSTM Residual Pipeline ★★★★★
  EXP-1143: Per-Patient Feature Importance Analysis ★★
  EXP-1144: Temporal Lead/Lag Optimization ★★★
  EXP-1145: Multi-Window Feature Fusion ★★★
  EXP-1146: Glucose Percentile Features ★★
  EXP-1147: PK Decomposition Features ★★★
  EXP-1148: Optimal Ensemble with All Features ★★★★
  EXP-1149: Definitive 5-fold CV with All Winners ★★★★★
  EXP-1150: Clinical Metrics with Best Pipeline ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1141 --detail --save --max-patients 11
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
WINDOW = 24
HORIZON = 12
STRIDE = 6
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class ResidualLSTM(nn.Module):
    def __init__(self, hidden=32, n_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True, num_layers=n_layers)
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
        1.0 if 3 <= hour < 7 else 0.0,   # dawn bin
        1.0 if 7 <= hour < 12 else 0.0,   # morning bin
        1.0 if 12 <= hour < 17 else 0.0,  # afternoon bin
        1.0 if 17 <= hour < 22 else 0.0,  # evening bin
        1.0 if hour >= 22 or hour < 3 else 0.0,  # night bin
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
                            include_interactions=True):
    """Build features with all proven enhancements."""
    g = glucose / GLUCOSE_SCALE
    pk = p['pk']
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
        pk_win = pk[i:i + window]
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

        # Physics interactions (always included)
        phys_inter = np.array([
            np.mean(supply * demand), np.mean(supply * g_mean),
            np.mean(demand * g_mean),
            np.mean(np.diff(net)) if len(net) > 1 else 0.0,
            np.mean(hepatic * supply),
        ])

        # Stats (always included)
        g_std = np.std(g_win)
        g_min, g_max = np.min(g_win), np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        parts = [base, phys_inter, stats]

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


def train_lstm_residual(residuals_val, residuals_test, seq_len=12, epochs=10,
                        hidden=32):
    """Train LSTM on validation residuals, predict test corrections."""
    if len(residuals_val) < seq_len + 10:
        return np.zeros_like(residuals_test)

    X_seq, y_seq = [], []
    for i in range(len(residuals_val) - seq_len):
        X_seq.append(residuals_val[i:i + seq_len])
        y_seq.append(residuals_val[i + seq_len])
    X_seq = torch.FloatTensor(np.array(X_seq)).unsqueeze(-1).to(DEVICE)
    y_seq = torch.FloatTensor(np.array(y_seq)).to(DEVICE)

    model = ResidualLSTM(hidden=hidden).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        pred = model(X_seq)
        loss = loss_fn(pred, y_seq)
        loss.backward()
        opt.step()

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
# EXP-1141: Combined Feature Engineering
# ---------------------------------------------------------------------------

def exp_1141_combined_features(patients, detail=False):
    """Combine all winning features: derivatives + time + dawn + interactions."""
    per_patient = {}
    scores = {'base': [], 'deriv': [], 'time': [], 'all': []}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        # Base features (no enhancements)
        X_base, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=False, include_deriv=False,
            include_interactions=False)
        # Derivatives only
        X_deriv, _, _ = build_enhanced_features(
            p, glucose, physics, include_time=False, include_deriv=True,
            include_interactions=False)
        # Time only
        X_time, _, _ = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=False,
            include_interactions=False)
        # All features
        X_all, _, _ = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_base) < 100:
            per_patient[pname] = {k: 0 for k in scores}
            continue

        y_dg = y - g_cur
        for X_feat, key in [(X_base, 'base'), (X_deriv, 'deriv'),
                            (X_time, 'time'), (X_all, 'all')]:
            X_feat = np.nan_to_num(X_feat, nan=0.0)
            X_tr, X_te, y_tr, y_te = split_data(X_feat, y_dg)
            g_cur_te = g_cur[len(X_feat) - len(X_te):]

            xgb_m = make_xgb()
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            if key not in per_patient.get(pname, {}):
                per_patient[pname] = per_patient.get(pname, {})
            per_patient[pname][key] = r2
            scores[key].append(r2)

        if detail:
            r = per_patient[pname]
            print(f"  {pname}: base={r['base']:.4f} +deriv={r['deriv']:.4f}"
                  f" +time={r['time']:.4f} all={r['all']:.4f}"
                  f" Δ={r['all'] - r['base']:+.4f}")

    means = {k: float(np.mean(v)) if v else 0 for k, v in scores.items()}
    all_wins = sum(1 for p in per_patient.values()
                   if p.get('all', 0) > p.get('base', 0))

    return {
        'name': 'EXP-1141',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} +deriv={means['deriv']:.4f}"
                   f" +time={means['time']:.4f} all={means['all']:.4f}"
                   f" Δ={means['all']-means['base']:+.4f} (wins={all_wins}/11)"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1142: Combined Features + LSTM Residual Pipeline
# ---------------------------------------------------------------------------

def exp_1142_full_enhanced_pipeline(patients, detail=False):
    """XGBoost with all features → LSTM residual correction."""
    per_patient = {}
    scores_base, scores_xgb, scores_pipeline = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_all) < 200:
            per_patient[pname] = {'base': 0, 'xgb': 0, 'pipeline': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X_all, y_dg)
        g_cur_te = g_cur[len(X_all) - len(X_te):]
        g_cur_val = g_cur[len(X_tr):len(X_tr) + len(X_val)]
        y_abs_te = y_te + g_cur_te

        # Base Ridge (no enhancements)
        X_base, _, _ = build_enhanced_features(
            p, glucose, physics, include_time=False, include_deriv=False,
            include_interactions=False)
        X_base = np.nan_to_num(X_base, nan=0.0)
        X_base_tr, _, X_base_te, _, _, _ = split_3way(X_base, y_dg)
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_base_tr, y_tr)
        r2_base = compute_r2(y_abs_te, ridge.predict(X_base_te) + g_cur_te)

        # XGBoost with all features
        xgb_m = make_xgb(n_estimators=300, max_depth=3)
        xgb_m.fit(X_tr, y_tr)
        pred_val = xgb_m.predict(X_val)
        pred_te = xgb_m.predict(X_te)
        r2_xgb = compute_r2(y_abs_te, pred_te + g_cur_te)

        # LSTM residual correction
        resid_val = y_val - pred_val
        resid_te = y_te - pred_te
        corrections = train_lstm_residual(resid_val, resid_te)
        pred_pipeline = pred_te + corrections
        r2_pipeline = compute_r2(y_abs_te, pred_pipeline + g_cur_te)

        per_patient[pname] = {
            'base': r2_base, 'xgb': r2_xgb, 'pipeline': r2_pipeline,
            'delta_total': r2_pipeline - r2_base,
            'delta_lstm': r2_pipeline - r2_xgb,
        }
        scores_base.append(r2_base)
        scores_xgb.append(r2_xgb)
        scores_pipeline.append(r2_pipeline)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} xgb={r2_xgb:.4f}"
                  f" pipeline={r2_pipeline:.4f}"
                  f" Δ_total={r2_pipeline - r2_base:+.4f}"
                  f" Δ_lstm={r2_pipeline - r2_xgb:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_x = float(np.mean(scores_xgb)) if scores_xgb else 0
    mean_p = float(np.mean(scores_pipeline)) if scores_pipeline else 0
    wins = sum(1 for p in per_patient.values()
               if p.get('pipeline', 0) > p.get('base', 0))

    return {
        'name': 'EXP-1142',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} xgb={mean_x:.4f} pipeline={mean_p:.4f}"
                   f" Δ={mean_p-mean_b:+.4f} (wins={wins}/11)"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'xgb': mean_x, 'pipeline': mean_p},
    }


# ---------------------------------------------------------------------------
# EXP-1143: Per-Patient Feature Importance
# ---------------------------------------------------------------------------

def exp_1143_feature_importance(patients, detail=False):
    """Analyze which feature categories matter most per patient."""
    per_patient = {}
    # Feature category boundaries (approximate)
    # base: 0..window-1 (glucose) + window..(window+4*window-1) (physics)
    # phys_inter: next 5
    # stats: next 6
    # derivs: next 10
    # time: next 11
    # interactions: next 10
    n_glucose = WINDOW  # 24
    n_physics = WINDOW * 4  # 96
    n_phys_inter = 5
    n_stats = 6
    n_deriv = 10
    n_time = 11
    n_inter = 10

    categories = [
        ('glucose', 0, n_glucose),
        ('physics', n_glucose, n_glucose + n_physics),
        ('phys_inter', n_glucose + n_physics, n_glucose + n_physics + n_phys_inter),
        ('stats', n_glucose + n_physics + n_phys_inter,
         n_glucose + n_physics + n_phys_inter + n_stats),
        ('derivatives', n_glucose + n_physics + n_phys_inter + n_stats,
         n_glucose + n_physics + n_phys_inter + n_stats + n_deriv),
        ('time', n_glucose + n_physics + n_phys_inter + n_stats + n_deriv,
         n_glucose + n_physics + n_phys_inter + n_stats + n_deriv + n_time),
        ('interactions',
         n_glucose + n_physics + n_phys_inter + n_stats + n_deriv + n_time,
         n_glucose + n_physics + n_phys_inter + n_stats + n_deriv + n_time + n_inter),
    ]

    category_importance = {c[0]: [] for c in categories}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_all) < 100:
            per_patient[pname] = {}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur
        X_tr, X_te, y_tr, y_te = split_data(X_all, y_dg)

        xgb_m = make_xgb()
        xgb_m.fit(X_tr, y_tr)

        if hasattr(xgb_m, 'feature_importances_'):
            imp = xgb_m.feature_importances_
        else:
            imp = np.ones(X_all.shape[1]) / X_all.shape[1]

        result_p = {}
        for cat_name, start, end in categories:
            if end <= len(imp):
                cat_imp = float(np.sum(imp[start:end]))
            else:
                cat_imp = 0.0
            result_p[cat_name] = cat_imp
            category_importance[cat_name].append(cat_imp)

        per_patient[pname] = result_p
        if detail:
            top = sorted(result_p.items(), key=lambda x: x[1], reverse=True)
            top_str = ' '.join(f"{k}={v:.3f}" for k, v in top[:4])
            print(f"  {pname}: {top_str}")

    mean_imp = {k: float(np.mean(v)) if v else 0
                for k, v in category_importance.items()}
    ranked = sorted(mean_imp.items(), key=lambda x: x[1], reverse=True)
    rank_str = ' > '.join(f"{k}({v:.3f})" for k, v in ranked)

    return {
        'name': 'EXP-1143',
        'status': 'pass',
        'detail': f"Ranking: {rank_str}",
        'per_patient': per_patient,
        'results': {'mean_importance': mean_imp, 'ranking': [r[0] for r in ranked]},
    }


# ---------------------------------------------------------------------------
# EXP-1144: Temporal Lead/Lag Optimization
# ---------------------------------------------------------------------------

def exp_1144_lead_lag(patients, detail=False):
    """Test different PK temporal offsets to account for glucose response delay."""
    per_patient = {}
    scores = {'lag0': [], 'lead15': [], 'lead30': [], 'lead45': []}
    leads = {'lag0': 0, 'lead15': 3, 'lead30': 6, 'lead45': 9}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        results_p = {}
        for lag_name, lead_steps in leads.items():
            X_list, y_list, g_cur_list = [], [], []

            for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
                g_win = g[i:i + WINDOW]
                if np.isnan(g_win).mean() > 0.3:
                    continue
                g_win = np.nan_to_num(
                    g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)

                # Shift PK channels forward by lead_steps
                pk_start = i + lead_steps
                pk_end = pk_start + WINDOW
                if pk_end > n:
                    continue
                pk_win = pk[pk_start:pk_end]
                if np.isnan(pk_win).any():
                    pk_win = np.nan_to_num(pk_win, nan=0.0)

                p_win = physics[i:i + WINDOW]
                if np.isnan(p_win).any():
                    p_win = np.nan_to_num(p_win, nan=0.0)

                y_val = g[i + WINDOW + HORIZON - 1]
                if np.isnan(y_val):
                    continue

                g_current = g_win[-1]
                # PK summary features
                pk_mean = np.mean(pk_win, axis=0)  # 8 channels
                feat = np.concatenate([g_win, p_win.ravel(), pk_mean])
                X_list.append(feat)
                y_list.append(y_val)
                g_cur_list.append(g_current)

            if len(X_list) < 100:
                results_p[lag_name] = 0.0
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
            results_p[lag_name] = r2
            scores[lag_name].append(r2)

        per_patient[pname] = results_p
        if detail:
            parts = [f"{k}={v:.4f}" for k, v in results_p.items()]
            best = max(results_p, key=results_p.get)
            print(f"  {pname}: {' '.join(parts)} best={best}")

    means = {k: float(np.mean(v)) if v else 0 for k, v in scores.items()}
    best_lag = max(means, key=means.get)

    return {
        'name': 'EXP-1144',
        'status': 'pass',
        'detail': ' '.join(f"{k}={v:.4f}" for k, v in means.items()) + f" best={best_lag}",
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1145: Multi-Window Feature Fusion
# ---------------------------------------------------------------------------

def exp_1145_multi_window_fusion(patients, detail=False):
    """Instead of extending window, use summary stats from multiple scales."""
    per_patient = {}
    scores_base, scores_fusion = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        X_base_list, X_fuse_list, y_list, g_cur_list = [], [], [], []

        for i in range(0, n - 72 - HORIZON, STRIDE):  # Need 6h lookback
            g_win = g[i + 48:i + 72]  # Last 2h (same as standard)
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i + 48:i + 72]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + 72 + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base = np.concatenate([g_win, p_win.ravel()])
            X_base_list.append(base)

            # Multi-window summary stats
            g_4h = g[i + 24:i + 72]  # 4h window
            g_6h = g[i:i + 72]       # 6h window
            g_4h = np.nan_to_num(g_4h, nan=np.nanmean(g_4h) if np.any(~np.isnan(g_4h)) else 0.4)
            g_6h = np.nan_to_num(g_6h, nan=np.nanmean(g_6h) if np.any(~np.isnan(g_6h)) else 0.4)

            summary_4h = [np.mean(g_4h), np.std(g_4h), np.min(g_4h), np.max(g_4h),
                          np.mean(np.diff(g_4h)) if len(g_4h) > 1 else 0]
            summary_6h = [np.mean(g_6h), np.std(g_6h), np.min(g_6h), np.max(g_6h),
                          np.mean(np.diff(g_6h)) if len(g_6h) > 1 else 0]

            # PK summary from longer windows
            pk_4h = p['pk'][i + 24:i + 72]
            pk_6h = p['pk'][i:i + 72]
            pk_4h = np.nan_to_num(pk_4h, nan=0.0)
            pk_6h = np.nan_to_num(pk_6h, nan=0.0)
            pk_summary_4h = np.mean(pk_4h, axis=0).tolist()  # 8 vals
            pk_summary_6h = np.mean(pk_6h, axis=0).tolist()

            fusion_feats = base.tolist() + summary_4h + summary_6h + pk_summary_4h + pk_summary_6h
            X_fuse_list.append(fusion_feats)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 100:
            per_patient[pname] = {'base': 0, 'fusion': 0}
            continue

        X_base = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_fuse = np.nan_to_num(np.array(X_fuse_list), nan=0.0)
        y = np.array(y_list)
        g_cur = np.array(g_cur_list)
        y_dg = y - g_cur

        X_tr_b, X_te_b, y_tr, y_te = split_data(X_base, y_dg)
        X_tr_f, X_te_f, _, _ = split_data(X_fuse, y_dg)
        g_cur_te = g_cur[len(X_base) - len(X_te_b):]
        y_abs_te = y_te + g_cur_te

        xgb_b = make_xgb()
        xgb_b.fit(X_tr_b, y_tr)
        r2_base = compute_r2(y_abs_te, xgb_b.predict(X_te_b) + g_cur_te)

        xgb_f = make_xgb()
        xgb_f.fit(X_tr_f, y_tr)
        r2_fusion = compute_r2(y_abs_te, xgb_f.predict(X_te_f) + g_cur_te)

        per_patient[pname] = {
            'base': r2_base, 'fusion': r2_fusion,
            'delta': r2_fusion - r2_base,
        }
        scores_base.append(r2_base)
        scores_fusion.append(r2_fusion)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} fusion={r2_fusion:.4f}"
                  f" Δ={r2_fusion - r2_base:+.4f}")

    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)
    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_f = float(np.mean(scores_fusion)) if scores_fusion else 0

    return {
        'name': 'EXP-1145',
        'status': 'pass',
        'detail': f"base={mean_b:.4f} fusion={mean_f:.4f} Δ={mean_f-mean_b:+.4f} (wins={wins}/11)",
        'per_patient': per_patient,
        'results': {'base': mean_b, 'fusion': mean_f},
    }


# ---------------------------------------------------------------------------
# EXP-1146: Glucose Percentile Features
# ---------------------------------------------------------------------------

def exp_1146_percentile_features(patients, detail=False):
    """Add glucose percentile features (where current glucose sits in history)."""
    per_patient = {}
    scores_base, scores_pct = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        X_list, y_list, g_cur_list, pct_list = [], [], [], []

        # Build running glucose history for percentile calculation
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
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

            g_current = g_win[-1]
            base = np.concatenate([g_win, p_win.ravel()])
            X_list.append(base)
            y_list.append(y_val)
            g_cur_list.append(g_current)

            # Percentile features using history up to this point
            history = g[:i + WINDOW]
            history = history[~np.isnan(history)]
            if len(history) > 100:
                current_pct = np.searchsorted(np.sort(history), g_current) / len(history)
                p10 = np.percentile(history, 10)
                p25 = np.percentile(history, 25)
                p50 = np.percentile(history, 50)
                p75 = np.percentile(history, 75)
                p90 = np.percentile(history, 90)
                dist_from_median = g_current - p50
                iqr = p75 - p25
                relative_pos = (g_current - p25) / iqr if iqr > 0 else 0.5
            else:
                current_pct = 0.5
                p10 = p25 = p50 = p75 = p90 = g_current
                dist_from_median = 0
                iqr = 0
                relative_pos = 0.5

            pct_feats = [current_pct, dist_from_median, relative_pos,
                         g_current - p10, g_current - p90, iqr]
            pct_list.append(pct_feats)

        if len(X_list) < 100:
            per_patient[pname] = {'base': 0, 'percentile': 0}
            continue

        X_base = np.nan_to_num(np.array(X_list), nan=0.0)
        X_pct = np.hstack([X_base, np.nan_to_num(np.array(pct_list), nan=0.0)])
        y = np.array(y_list)
        g_cur = np.array(g_cur_list)
        y_dg = y - g_cur

        X_tr_b, X_te_b, y_tr, y_te = split_data(X_base, y_dg)
        X_tr_p, X_te_p, _, _ = split_data(X_pct, y_dg)
        g_cur_te = g_cur[len(X_base) - len(X_te_b):]
        y_abs_te = y_te + g_cur_te

        xgb_b = make_xgb()
        xgb_b.fit(X_tr_b, y_tr)
        r2_base = compute_r2(y_abs_te, xgb_b.predict(X_te_b) + g_cur_te)

        xgb_p = make_xgb()
        xgb_p.fit(X_tr_p, y_tr)
        r2_pct = compute_r2(y_abs_te, xgb_p.predict(X_te_p) + g_cur_te)

        per_patient[pname] = {
            'base': r2_base, 'percentile': r2_pct,
            'delta': r2_pct - r2_base,
        }
        scores_base.append(r2_base)
        scores_pct.append(r2_pct)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} +pct={r2_pct:.4f}"
                  f" Δ={r2_pct - r2_base:+.4f}")

    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)
    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_p = float(np.mean(scores_pct)) if scores_pct else 0

    return {
        'name': 'EXP-1146',
        'status': 'pass',
        'detail': f"base={mean_b:.4f} +pct={mean_p:.4f} Δ={mean_p-mean_b:+.4f} (wins={wins}/11)",
        'per_patient': per_patient,
        'results': {'base': mean_b, 'percentile': mean_p},
    }


# ---------------------------------------------------------------------------
# EXP-1147: PK Decomposition Features
# ---------------------------------------------------------------------------

def exp_1147_pk_decomposition(patients, detail=False):
    """Use decomposed PK channels (basal vs bolus IOB/activity) as separate features."""
    per_patient = {}
    scores_base, scores_pk = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']  # N×8: [total_iob, total_act, basal_iob, basal_act, bolus_iob, bolus_act, carb_cob, carb_act]
        n = len(g)

        X_list, y_list, g_cur_list, pk_list = [], [], [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base = np.concatenate([g_win, p_win.ravel()])
            X_list.append(base)
            y_list.append(y_val)
            g_cur_list.append(g_current)

            # PK decomposition features
            basal_iob = pk_win[:, 2]
            bolus_iob = pk_win[:, 4]
            basal_act = pk_win[:, 3]
            bolus_act = pk_win[:, 5]
            cob = pk_win[:, 6]
            carb_act = pk_win[:, 7]

            pk_feats = [
                np.mean(basal_iob), np.mean(bolus_iob),
                np.mean(basal_act), np.mean(bolus_act),
                np.mean(cob), np.mean(carb_act),
                # Ratios
                np.mean(bolus_iob) / (np.mean(basal_iob) + 1e-6),  # bolus/basal ratio
                np.mean(bolus_act) / (np.mean(basal_act) + 1e-6),
                # Trends
                np.mean(np.diff(basal_iob)) if len(basal_iob) > 1 else 0,
                np.mean(np.diff(bolus_iob)) if len(bolus_iob) > 1 else 0,
                np.mean(np.diff(cob)) if len(cob) > 1 else 0,
                # Net balance
                np.mean(bolus_act + basal_act) - np.mean(carb_act),  # insulin-carb balance
                # Peak timing
                np.argmax(bolus_act) / WINDOW if np.max(bolus_act) > 0 else 0.5,
                np.argmax(carb_act) / WINDOW if np.max(carb_act) > 0 else 0.5,
            ]
            pk_list.append(pk_feats)

        if len(X_list) < 100:
            per_patient[pname] = {'base': 0, 'pk_decomp': 0}
            continue

        X_base = np.nan_to_num(np.array(X_list), nan=0.0)
        X_pk = np.hstack([X_base, np.nan_to_num(np.array(pk_list), nan=0.0)])
        y = np.array(y_list)
        g_cur = np.array(g_cur_list)
        y_dg = y - g_cur

        X_tr_b, X_te_b, y_tr, y_te = split_data(X_base, y_dg)
        X_tr_p, X_te_p, _, _ = split_data(X_pk, y_dg)
        g_cur_te = g_cur[len(X_base) - len(X_te_b):]
        y_abs_te = y_te + g_cur_te

        xgb_b = make_xgb()
        xgb_b.fit(X_tr_b, y_tr)
        r2_base = compute_r2(y_abs_te, xgb_b.predict(X_te_b) + g_cur_te)

        xgb_p = make_xgb()
        xgb_p.fit(X_tr_p, y_tr)
        r2_pk = compute_r2(y_abs_te, xgb_p.predict(X_te_p) + g_cur_te)

        per_patient[pname] = {
            'base': r2_base, 'pk_decomp': r2_pk,
            'delta': r2_pk - r2_base,
        }
        scores_base.append(r2_base)
        scores_pk.append(r2_pk)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} +pk={r2_pk:.4f}"
                  f" Δ={r2_pk - r2_base:+.4f}")

    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)
    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_p = float(np.mean(scores_pk)) if scores_pk else 0

    return {
        'name': 'EXP-1147',
        'status': 'pass',
        'detail': f"base={mean_b:.4f} +pk={mean_p:.4f} Δ={mean_p-mean_b:+.4f} (wins={wins}/11)",
        'per_patient': per_patient,
        'results': {'base': mean_b, 'pk_decomp': mean_p},
    }


# ---------------------------------------------------------------------------
# EXP-1148: Optimal Ensemble with All Features
# ---------------------------------------------------------------------------

def exp_1148_optimal_ensemble(patients, detail=False):
    """Weighted ensemble of Ridge + XGBoost + Ridge-enhanced, all with enhanced features."""
    per_patient = {}
    scores_single, scores_ens = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_all) < 200:
            per_patient[pname] = {'xgb': 0, 'ensemble': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X_all, y_dg)
        g_cur_te = g_cur[len(X_all) - len(X_te):]
        g_cur_val = g_cur[len(X_tr):len(X_tr) + len(X_val)]
        y_abs_te = y_te + g_cur_te
        y_abs_val = y_val + g_cur_val

        # Models
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr)
        pred_ridge_val = ridge.predict(X_val) + g_cur_val
        pred_ridge_te = ridge.predict(X_te) + g_cur_te

        xgb_m = make_xgb(n_estimators=300, max_depth=3)
        xgb_m.fit(X_tr, y_tr)
        pred_xgb_val = xgb_m.predict(X_val) + g_cur_val
        pred_xgb_te = xgb_m.predict(X_te) + g_cur_te

        xgb2 = make_xgb(n_estimators=200, max_depth=4, learning_rate=0.05)
        xgb2.fit(X_tr, y_tr)
        pred_xgb2_val = xgb2.predict(X_val) + g_cur_val
        pred_xgb2_te = xgb2.predict(X_te) + g_cur_te

        # Find optimal weights on validation
        best_r2 = -999
        best_weights = (0.33, 0.33, 0.34)
        for w1 in np.arange(0, 1.05, 0.1):
            for w2 in np.arange(0, 1.05 - w1, 0.1):
                w3 = 1.0 - w1 - w2
                if w3 < 0:
                    continue
                pred_ens = w1 * pred_ridge_val + w2 * pred_xgb_val + w3 * pred_xgb2_val
                r2 = compute_r2(y_abs_val, pred_ens)
                if r2 > best_r2:
                    best_r2 = r2
                    best_weights = (w1, w2, w3)

        # Apply to test
        pred_ens_te = (best_weights[0] * pred_ridge_te +
                       best_weights[1] * pred_xgb_te +
                       best_weights[2] * pred_xgb2_te)
        r2_ens = compute_r2(y_abs_te, pred_ens_te)
        r2_xgb = compute_r2(y_abs_te, pred_xgb_te)

        per_patient[pname] = {
            'xgb': r2_xgb, 'ensemble': r2_ens,
            'weights': list(best_weights),
            'delta': r2_ens - r2_xgb,
        }
        scores_single.append(r2_xgb)
        scores_ens.append(r2_ens)

        if detail:
            w = best_weights
            print(f"  {pname}: xgb={r2_xgb:.4f} ens={r2_ens:.4f}"
                  f" Δ={r2_ens - r2_xgb:+.4f}"
                  f" w=({w[0]:.1f},{w[1]:.1f},{w[2]:.1f})")

    wins = sum(1 for p in per_patient.values() if p.get('delta', 0) > 0)
    mean_s = float(np.mean(scores_single)) if scores_single else 0
    mean_e = float(np.mean(scores_ens)) if scores_ens else 0

    return {
        'name': 'EXP-1148',
        'status': 'pass',
        'detail': f"xgb={mean_s:.4f} ensemble={mean_e:.4f} Δ={mean_e-mean_s:+.4f} (wins={wins}/11)",
        'per_patient': per_patient,
        'results': {'xgb': mean_s, 'ensemble': mean_e},
    }


# ---------------------------------------------------------------------------
# EXP-1149: Definitive 5-Fold CV with All Winners
# ---------------------------------------------------------------------------

def exp_1149_definitive_cv(patients, detail=False):
    """Rigorous 5-fold temporal CV with all winning features and pipeline."""
    per_patient = {}
    all_r2 = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_all) < 200:
            per_patient[pname] = {'r2_mean': 0, 'r2_std': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        n = len(X_all)
        n_folds = 5
        fold_size = n // n_folds
        fold_scores = []

        for fold in range(n_folds):
            # Temporal block CV
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < n_folds - 1 else n
            mask = np.ones(n, dtype=bool)
            mask[val_start:val_end] = False

            X_tr, y_tr = X_all[mask], y_dg[mask]
            X_vl, y_vl = X_all[~mask], y_dg[~mask]
            g_cur_vl = g_cur[~mask]
            y_abs_vl = y_vl + g_cur_vl

            xgb_m = make_xgb(n_estimators=300, max_depth=3)
            xgb_m.fit(X_tr, y_tr)
            pred = xgb_m.predict(X_vl) + g_cur_vl
            r2 = compute_r2(y_abs_vl, pred)
            fold_scores.append(r2)

        mean_r2 = float(np.mean(fold_scores))
        std_r2 = float(np.std(fold_scores))

        per_patient[pname] = {
            'r2_mean': mean_r2, 'r2_std': std_r2,
            'fold_scores': fold_scores,
        }
        all_r2.append(mean_r2)

        if detail:
            folds_str = ' '.join(f"{s:.3f}" for s in fold_scores)
            print(f"  {pname}: {mean_r2:.4f}±{std_r2:.3f} [{folds_str}]")

    grand_mean = float(np.mean(all_r2)) if all_r2 else 0

    # Also compute without enhanced features for comparison
    baseline_r2 = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X_base, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=False, include_deriv=False,
            include_interactions=False)
        if len(X_base) < 200:
            continue
        X_base = np.nan_to_num(X_base, nan=0.0)
        y_dg = y - g_cur
        n = len(X_base)
        fold_size = n // 5
        fold_r2s = []
        for fold in range(5):
            vs = fold * fold_size
            ve = vs + fold_size if fold < 4 else n
            mask = np.ones(n, dtype=bool)
            mask[vs:ve] = False
            xgb_m = make_xgb()
            xgb_m.fit(X_base[mask], y_dg[mask])
            pred = xgb_m.predict(X_base[~mask]) + g_cur[~mask]
            fold_r2s.append(compute_r2(y_dg[~mask] + g_cur[~mask], pred))
        baseline_r2.append(float(np.mean(fold_r2s)))

    baseline_mean = float(np.mean(baseline_r2)) if baseline_r2 else 0

    return {
        'name': 'EXP-1149',
        'status': 'pass',
        'detail': (f"5-fold CV: enhanced={grand_mean:.4f} baseline={baseline_mean:.4f}"
                   f" Δ={grand_mean-baseline_mean:+.4f}"),
        'per_patient': per_patient,
        'results': {
            'enhanced_cv': grand_mean, 'baseline_cv': baseline_mean,
            'delta': grand_mean - baseline_mean,
        },
    }


# ---------------------------------------------------------------------------
# EXP-1150: Clinical Metrics with Best Pipeline
# ---------------------------------------------------------------------------

def exp_1150_clinical_metrics(patients, detail=False):
    """Full clinical evaluation: MAE, Clarke, TIR, hypo detection."""
    per_patient = {}
    all_mae, all_clarke_a = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_all, y, g_cur = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True)

        if len(X_all) < 200:
            per_patient[pname] = {'mae': 99, 'clarke_a': 0}
            continue

        X_all = np.nan_to_num(X_all, nan=0.0)
        y_dg = y - g_cur

        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X_all, y_dg)
        g_cur_te = g_cur[len(X_all) - len(X_te):]
        y_abs_te = (y_te + g_cur_te) * GLUCOSE_SCALE

        # Best pipeline: XGBoost → LSTM
        xgb_m = make_xgb(n_estimators=300, max_depth=3)
        xgb_m.fit(X_tr, y_tr)
        pred_val = xgb_m.predict(X_val)
        pred_te = xgb_m.predict(X_te)

        resid_val = y_val - pred_val
        resid_te = y_te - pred_te
        corrections = train_lstm_residual(resid_val, resid_te)
        pred_final = (pred_te + corrections + g_cur_te) * GLUCOSE_SCALE

        # Clinical metrics
        mae = compute_mae(y_abs_te, pred_final)

        # Clarke Error Grid Zone A
        ref = y_abs_te
        pred = pred_final
        n_samples = len(ref)
        zone_a = 0
        for j in range(n_samples):
            r, pr = ref[j], pred[j]
            if r <= 70:
                if pr <= 70:
                    zone_a += 1
                elif abs(pr - r) <= 20:
                    zone_a += 1
            elif r <= 180:
                if abs(pr - r) <= 20 or abs(pr - r) / r <= 0.20:
                    zone_a += 1
            else:
                if pr >= 70 and abs(pr - r) / r <= 0.20:
                    zone_a += 1
        clarke_a = zone_a / n_samples * 100 if n_samples > 0 else 0

        # Time in Range (70-180)
        tir_ref = np.mean((ref >= 70) & (ref <= 180)) * 100
        tir_pred = np.mean((pred >= 70) & (pred <= 180)) * 100

        # Hypo detection
        hypo_mask = ref < 70
        n_hypo = int(np.sum(hypo_mask))
        if n_hypo > 5:
            hypo_mae = compute_mae(ref[hypo_mask], pred[hypo_mask])
            hypo_detected = np.mean(pred[hypo_mask] < 80)  # within 10 of threshold
        else:
            hypo_mae = 0
            hypo_detected = 0

        per_patient[pname] = {
            'mae': mae, 'clarke_a': clarke_a,
            'tir_ref': tir_ref, 'tir_pred': tir_pred,
            'hypo_n': n_hypo, 'hypo_mae': hypo_mae,
            'hypo_detected': hypo_detected,
        }
        all_mae.append(mae)
        all_clarke_a.append(clarke_a)

        if detail:
            print(f"  {pname}: MAE={mae:.1f} Clarke_A={clarke_a:.1f}%"
                  f" TIR={tir_ref:.1f}% hypo_n={n_hypo}")

    mean_mae = float(np.mean(all_mae)) if all_mae else 99
    mean_clarke = float(np.mean(all_clarke_a)) if all_clarke_a else 0

    return {
        'name': 'EXP-1150',
        'status': 'pass',
        'detail': f"MAE={mean_mae:.1f} Clarke_A={mean_clarke:.1f}% ({len(all_mae)} patients)",
        'per_patient': per_patient,
        'results': {'mae': mean_mae, 'clarke_a': mean_clarke},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1141', 'Combined Feature Engineering', exp_1141_combined_features),
    ('EXP-1142', 'Combined Features + LSTM Pipeline', exp_1142_full_enhanced_pipeline),
    ('EXP-1143', 'Per-Patient Feature Importance', exp_1143_feature_importance),
    ('EXP-1144', 'Temporal Lead/Lag Optimization', exp_1144_lead_lag),
    ('EXP-1145', 'Multi-Window Feature Fusion', exp_1145_multi_window_fusion),
    ('EXP-1146', 'Glucose Percentile Features', exp_1146_percentile_features),
    ('EXP-1147', 'PK Decomposition Features', exp_1147_pk_decomposition),
    ('EXP-1148', 'Optimal Ensemble with All Features', exp_1148_optimal_ensemble),
    ('EXP-1149', 'Definitive 5-Fold CV (All Winners)', exp_1149_definitive_cv),
    ('EXP-1150', 'Clinical Metrics (Best Pipeline)', exp_1150_clinical_metrics),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1141-1150: Combined Winners & Frontier Push')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1141)')
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
