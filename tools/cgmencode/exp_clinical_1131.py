#!/usr/bin/env python3
"""EXP-1131 to EXP-1140: Remaining High-Value Opportunities.

Campaign status after 130 experiments:
- SOTA: R²≈0.55 (full pipeline, block CV)
- Residual LSTM: +0.024 R² on top of ensemble
- Noise ceiling: R²=0.854 (σ=15 mg/dL)
- Remaining gap: ~0.30 (still ~55% unexplained beyond noise floor)

This batch targets specific high-value opportunities not yet covered:
  EXP-1131: Extended Context Window (4h, 6h) ★★★
  EXP-1132: Time-of-Day Conditioning ★★
  EXP-1133: Stacked Generalization (Level-2 Meta-Learner) ★★★
  EXP-1134: Patient-Adaptive Online Learning ★★
  EXP-1135: Glucose Derivative Features ★★★
  EXP-1136: Insulin-Glucose Interaction Terms ★★
  EXP-1137: Residual Boosting Chain ★★★
  EXP-1138: Robust Loss Functions ★★
  EXP-1139: Feature Importance & Selection ★★★
  EXP-1140: Dawn Phenomenon Conditioning ★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1131 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, Lasso, ElasticNet

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
# EXP-1131: Extended Context Window (4h, 6h)
# ---------------------------------------------------------------------------

def exp_1131_extended_context(patients, detail=False):
    """Compare 2h vs 4h vs 6h context windows for Ridge and XGBoost.

    Hypothesis: longer context captures dawn phenomenon and meal patterns,
    improving prediction especially for slow-moving trends.
    """
    WINDOWS = {
        '2h': {'window': 24, 'stride': 6},
        '4h': {'window': 48, 'stride': 12},
        '6h': {'window': 72, 'stride': 18},
    }

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < 72 + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        res = {'patient': p['name']}

        for label, cfg in WINDOWS.items():
            w = cfg['window']
            s = cfg['stride']

            X, y_abs, g_cur = build_grand_features(glucose, physics,
                                                    window=w, horizon=HORIZON,
                                                    stride=s)
            if len(X) < 200:
                res[f'r2_ridge_{label}'] = None
                res[f'r2_xgb_{label}'] = None
                continue

            y_delta = y_abs - g_cur
            X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
            _, _, ya_tr, ya_vl = split_data(X, y_abs)
            gc_vl = g_cur[len(X_tr):]

            # Ridge on Δg
            ridge = Ridge(alpha=1.0)
            X_tr_clean = np.nan_to_num(X_tr)
            X_vl_clean = np.nan_to_num(X_vl)
            ridge.fit(X_tr_clean, yd_tr)
            pred_ridge = ridge.predict(X_vl_clean) + gc_vl
            r2_ridge = compute_r2(ya_vl, pred_ridge)

            # XGBoost on Δg
            xgb_m = make_xgb()
            xgb_m.fit(X_tr_clean, yd_tr)
            pred_xgb = xgb_m.predict(X_vl_clean) + gc_vl
            r2_xgb = compute_r2(ya_vl, pred_xgb)

            res[f'r2_ridge_{label}'] = round(r2_ridge, 4)
            res[f'r2_xgb_{label}'] = round(r2_xgb, 4)
            res[f'n_samples_{label}'] = len(X)

        # Compute gains vs 2h baseline
        if res.get('r2_ridge_2h') is not None:
            for label in ['4h', '6h']:
                if res.get(f'r2_ridge_{label}') is not None:
                    res[f'ridge_gain_{label}'] = round(
                        res[f'r2_ridge_{label}'] - res['r2_ridge_2h'], 4)
                    res[f'xgb_gain_{label}'] = round(
                        res[f'r2_xgb_{label}'] - res['r2_xgb_2h'], 4)

        results.append(res)

        if detail:
            parts = []
            for label in ['2h', '4h', '6h']:
                r = res.get(f'r2_ridge_{label}')
                x = res.get(f'r2_xgb_{label}')
                if r is not None:
                    parts.append(f"{label}: ridge={r:.4f} xgb={x:.4f}")
            print(f"  {p['name']}: {' | '.join(parts)}")

    # Summarize
    means = {}
    for label in ['2h', '4h', '6h']:
        for model in ['ridge', 'xgb']:
            key = f'r2_{model}_{label}'
            vals = [r[key] for r in results if r.get(key) is not None]
            if vals:
                means[key] = round(np.mean(vals), 4)

    ridge_4h_wins = sum(1 for r in results
                        if r.get('ridge_gain_4h', 0) > 0.001)
    ridge_6h_wins = sum(1 for r in results
                        if r.get('ridge_gain_6h', 0) > 0.001)

    return {
        'status': 'pass',
        'detail': (f"Ridge 2h={means.get('r2_ridge_2h', 0):.4f} "
                   f"4h={means.get('r2_ridge_4h', 0):.4f} "
                   f"6h={means.get('r2_ridge_6h', 0):.4f} | "
                   f"XGB 2h={means.get('r2_xgb_2h', 0):.4f} "
                   f"4h={means.get('r2_xgb_4h', 0):.4f} "
                   f"6h={means.get('r2_xgb_6h', 0):.4f} "
                   f"(4h_wins={ridge_4h_wins} 6h_wins={ridge_6h_wins}"
                   f"/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1132: Time-of-Day Conditioning
# ---------------------------------------------------------------------------

def exp_1132_time_of_day(patients, detail=False):
    """Add time-of-day features: sin/cos hour + categorical bins.

    Prior EXP-419-426 showed time-invariance holds ≤6h but fails ≥12h,
    so conditioning should help at longer horizons even at 1h.
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur

        # Build time-of-day features per window
        g = glucose / GLUCOSE_SCALE
        tod_feats = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            # Time index → fractional hour (assuming 5-min intervals from t=0)
            center_idx = i + WINDOW // 2
            fractional_hour = (center_idx * 5.0 / 60.0) % 24.0
            hour_rad = 2.0 * np.pi * fractional_hour / 24.0

            sin_h = np.sin(hour_rad)
            cos_h = np.cos(hour_rad)

            # Categorical bins: dawn(3-7), morning(7-12), afternoon(12-17),
            # evening(17-22), night(22-3)
            bins = np.zeros(5)
            if 3 <= fractional_hour < 7:
                bins[0] = 1.0   # dawn
            elif 7 <= fractional_hour < 12:
                bins[1] = 1.0   # morning
            elif 12 <= fractional_hour < 17:
                bins[2] = 1.0   # afternoon
            elif 17 <= fractional_hour < 22:
                bins[3] = 1.0   # evening
            else:
                bins[4] = 1.0   # night

            tod_feats.append(np.concatenate([[sin_h, cos_h], bins]))

        tod_feats = np.array(tod_feats)
        if len(tod_feats) != len(X):
            tod_feats = np.zeros((len(X), 7))

        X_aug = np.column_stack([X, tod_feats])

        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        Xa_tr, Xa_vl = X_aug[:len(X_tr)], X_aug[len(X_tr):]
        gc_vl = g_cur[len(X_tr):]

        # Ridge baseline (no time features)
        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr_clean, yd_tr)
        r2_ridge_base = compute_r2(ya_vl, ridge_base.predict(X_vl_clean) + gc_vl)

        # Ridge + time features
        Xa_tr_clean = np.nan_to_num(Xa_tr)
        Xa_vl_clean = np.nan_to_num(Xa_vl)
        ridge_tod = Ridge(alpha=1.0)
        ridge_tod.fit(Xa_tr_clean, yd_tr)
        r2_ridge_tod = compute_r2(ya_vl, ridge_tod.predict(Xa_vl_clean) + gc_vl)

        # XGBoost baseline
        xgb_base = make_xgb()
        xgb_base.fit(X_tr_clean, yd_tr)
        r2_xgb_base = compute_r2(ya_vl, xgb_base.predict(X_vl_clean) + gc_vl)

        # XGBoost + time features
        xgb_tod = make_xgb()
        xgb_tod.fit(Xa_tr_clean, yd_tr)
        r2_xgb_tod = compute_r2(ya_vl, xgb_tod.predict(Xa_vl_clean) + gc_vl)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_tod': round(r2_ridge_tod, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_tod': round(r2_xgb_tod, 4),
            'ridge_gain': round(r2_ridge_tod - r2_ridge_base, 4),
            'xgb_gain': round(r2_xgb_tod - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge Δ={r2_ridge_tod-r2_ridge_base:+.4f} "
                  f"xgb Δ={r2_xgb_tod-r2_xgb_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_base', 'r2_ridge_tod', 'r2_xgb_base', 'r2_xgb_tod']}
    ridge_wins = sum(1 for r in results if r['ridge_gain'] > 0.001)
    xgb_wins = sum(1 for r in results if r['xgb_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: {means['r2_ridge_base']:.4f}→{means['r2_ridge_tod']:.4f} "
                   f"(wins={ridge_wins}) | xgb: {means['r2_xgb_base']:.4f}→"
                   f"{means['r2_xgb_tod']:.4f} (wins={xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1133: Stacked Generalization (Level-2 Meta-Learner)
# ---------------------------------------------------------------------------

def exp_1133_stacked_generalization(patients, detail=False):
    """Proper stacking with K-fold base predictions → level-2 meta-learner.

    Base models: Ridge, XGBoost, GradientBoosting (sklearn), TCN.
    Level-2: ElasticNet on out-of-fold base predictions.
    No data leakage: base predictions generated via K-fold cross-val.
    """
    N_FOLDS = 3

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 300:
            continue

        y_delta = y_abs - g_cur

        # Split: 80% for stacking, 20% for final test
        split_idx = int(0.8 * len(X))
        X_stack, X_test = X[:split_idx], X[split_idx:]
        yd_stack, yd_test = y_delta[:split_idx], y_delta[split_idx:]
        ya_stack, ya_test = y_abs[:split_idx], y_abs[split_idx:]
        gc_stack, gc_test = g_cur[:split_idx], g_cur[split_idx:]

        X_stack_clean = np.nan_to_num(X_stack)
        X_test_clean = np.nan_to_num(X_test)

        # Generate out-of-fold predictions for base models
        n_stack = len(X_stack_clean)
        fold_size = n_stack // N_FOLDS
        oof_ridge = np.zeros(n_stack)
        oof_xgb = np.zeros(n_stack)
        oof_gb = np.zeros(n_stack)

        # Also accumulate test predictions from each fold
        test_ridge_all = np.zeros((N_FOLDS, len(X_test_clean)))
        test_xgb_all = np.zeros((N_FOLDS, len(X_test_clean)))
        test_gb_all = np.zeros((N_FOLDS, len(X_test_clean)))

        for fold in range(N_FOLDS):
            vs = fold * fold_size
            ve = vs + fold_size if fold < N_FOLDS - 1 else n_stack
            mask = np.ones(n_stack, dtype=bool)
            mask[vs:ve] = False

            Xf_tr, yf_tr = X_stack_clean[mask], yd_stack[mask]
            Xf_vl = X_stack_clean[~mask]

            # Ridge
            r = Ridge(alpha=1.0)
            r.fit(Xf_tr, yf_tr)
            oof_ridge[vs:ve] = r.predict(Xf_vl)
            test_ridge_all[fold] = r.predict(X_test_clean)

            # XGBoost
            xm = make_xgb()
            xm.fit(Xf_tr, yf_tr)
            oof_xgb[vs:ve] = xm.predict(Xf_vl)
            test_xgb_all[fold] = xm.predict(X_test_clean)

            # Gradient Boosting (sklearn fallback for diversity)
            from sklearn.ensemble import GradientBoostingRegressor
            gb = GradientBoostingRegressor(
                n_estimators=100, max_depth=3, learning_rate=0.05,
                random_state=42)
            gb.fit(Xf_tr, yf_tr)
            oof_gb[vs:ve] = gb.predict(Xf_vl)
            test_gb_all[fold] = gb.predict(X_test_clean)

        # Average test predictions across folds
        test_ridge = test_ridge_all.mean(axis=0)
        test_xgb = test_xgb_all.mean(axis=0)
        test_gb = test_gb_all.mean(axis=0)

        # Level-2: ElasticNet on OOF predictions
        meta_X_stack = np.column_stack([oof_ridge, oof_xgb, oof_gb])
        meta_X_test = np.column_stack([test_ridge, test_xgb, test_gb])

        meta = ElasticNet(alpha=0.01, l1_ratio=0.5, random_state=42)
        meta.fit(meta_X_stack, yd_stack)
        pred_meta = meta.predict(meta_X_test) + gc_test
        r2_stacked = compute_r2(ya_test, pred_meta)

        # Individual model scores on test
        r2_ridge = compute_r2(ya_test, test_ridge + gc_test)
        r2_xgb = compute_r2(ya_test, test_xgb + gc_test)
        r2_gb = compute_r2(ya_test, test_gb + gc_test)

        # Simple average baseline
        pred_avg = (test_ridge + test_xgb + test_gb) / 3.0 + gc_test
        r2_avg = compute_r2(ya_test, pred_avg)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge': round(r2_ridge, 4),
            'r2_xgb': round(r2_xgb, 4),
            'r2_gb': round(r2_gb, 4),
            'r2_avg_ensemble': round(r2_avg, 4),
            'r2_stacked': round(r2_stacked, 4),
            'stacked_vs_best_base': round(r2_stacked - max(r2_ridge, r2_xgb, r2_gb), 4),
            'stacked_vs_avg': round(r2_stacked - r2_avg, 4),
            'meta_weights': [round(float(c), 4) for c in meta.coef_],
        })

        if detail:
            best_base = max(r2_ridge, r2_xgb, r2_gb)
            print(f"  {p['name']}: ridge={r2_ridge:.4f} xgb={r2_xgb:.4f} "
                  f"gb={r2_gb:.4f} avg={r2_avg:.4f} stacked={r2_stacked:.4f} "
                  f"Δ_vs_best={r2_stacked-best_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_xgb', 'r2_gb', 'r2_avg_ensemble', 'r2_stacked']}
    stack_wins = sum(1 for r in results if r['stacked_vs_avg'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge={means['r2_ridge']:.4f} xgb={means['r2_xgb']:.4f} "
                   f"avg={means['r2_avg_ensemble']:.4f} "
                   f"stacked={means['r2_stacked']:.4f} "
                   f"(stack>avg={stack_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1134: Patient-Adaptive Online Learning
# ---------------------------------------------------------------------------

def exp_1134_online_learning(patients, detail=False):
    """Simulate online learning: train on first 60%, then fine-tune on
    sliding windows of recent data. Compare static vs update every 6h/12h/24h.
    """
    UPDATE_INTERVALS = {
        'static': None,
        '6h': 72,     # 6h * 12 samples/h
        '12h': 144,   # 12h * 12 samples/h
        '24h': 288,   # 24h * 12 samples/h
    }
    RECENT_WINDOW = 288  # Use last 24h of data for fine-tuning

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 200:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 400:
            continue

        y_delta = y_abs - g_cur

        # 60% train, 40% test (online period)
        train_end = int(0.6 * len(X))
        X_init = np.nan_to_num(X[:train_end])
        yd_init = y_delta[:train_end]
        X_online = np.nan_to_num(X[train_end:])
        yd_online = y_delta[train_end:]
        ya_online = y_abs[train_end:]
        gc_online = g_cur[train_end:]

        res = {'patient': p['name'], 'n_samples': len(X),
               'n_online': len(X_online)}

        for label, interval in UPDATE_INTERVALS.items():
            if interval is None:
                # Static: train once on initial data
                ridge = Ridge(alpha=1.0)
                ridge.fit(X_init, yd_init)
                pred = ridge.predict(X_online) + gc_online
                r2 = compute_r2(ya_online, pred)
            else:
                # Online: retrain every `interval` samples
                pred = np.zeros(len(X_online))
                X_all = np.vstack([X_init, X_online])
                yd_all = np.concatenate([yd_init, yd_online])

                last_train = 0
                ridge = Ridge(alpha=1.0)
                ridge.fit(X_init, yd_init)

                for i in range(len(X_online)):
                    pred[i] = ridge.predict(X_online[i:i+1])[0] + gc_online[i]

                    if (i + 1) % interval == 0 and i > 0:
                        # Retrain on recent data
                        abs_idx = train_end + i
                        start = max(0, abs_idx - RECENT_WINDOW)
                        X_recent = np.nan_to_num(X_all[start:abs_idx])
                        yd_recent = yd_all[start:abs_idx]
                        if len(X_recent) > 50:
                            ridge = Ridge(alpha=1.0)
                            ridge.fit(X_recent, yd_recent)

                r2 = compute_r2(ya_online, pred)

            res[f'r2_{label}'] = round(r2, 4)

        # Gains vs static
        for label in ['6h', '12h', '24h']:
            res[f'gain_{label}'] = round(
                res[f'r2_{label}'] - res['r2_static'], 4)

        results.append(res)

        if detail:
            parts = [f"{k}={res[f'r2_{k}']:.4f}" for k in UPDATE_INTERVALS]
            print(f"  {p['name']}: {' '.join(parts)}")

    means = {f'r2_{k}': round(np.mean([r[f'r2_{k}'] for r in results]), 4)
             for k in UPDATE_INTERVALS}
    best_update = max(means, key=means.get)
    wins_6h = sum(1 for r in results if r.get('gain_6h', 0) > 0.001)

    return {
        'status': 'pass',
        'detail': (' '.join(f"{k}={v:.4f}" for k, v in means.items()) +
                   f" best={best_update} (6h_wins={wins_6h}/{len(results)})"),
        'results': {'per_patient': results, 'summary': {
            'means': means, 'best_update': best_update,
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1135: Glucose Derivative Features
# ---------------------------------------------------------------------------

def exp_1135_derivative_features(patients, detail=False):
    """Add explicit derivative features: 1st/2nd derivative, momentum, volatility.

    Physics-inspired features that may capture dynamics flat windows miss.
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur

        # Build derivative features per window
        g = glucose / GLUCOSE_SCALE
        deriv_feats = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            gw = np.nan_to_num(
                gw, nan=np.nanmean(gw) if np.any(~np.isnan(gw)) else 0.4)
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            # 1st derivative (rate of change) at multiple scales
            d1_fast = np.diff(gw)                                # 5-min RoC
            d1_med = gw[3:] - gw[:-3]                            # 15-min RoC
            d1_slow = gw[6:] - gw[:-6]                           # 30-min RoC

            # 2nd derivative (acceleration)
            d2 = np.diff(d1_fast)

            # Momentum: exponentially weighted recent trend
            weights = np.exp(np.linspace(-2, 0, len(d1_fast)))
            weights /= weights.sum()
            momentum = np.sum(d1_fast * weights)

            # Volatility: rolling std over different windows
            vol_5 = np.std(d1_fast[-5:]) if len(d1_fast) >= 5 else np.std(d1_fast)
            vol_10 = np.std(d1_fast[-10:]) if len(d1_fast) >= 10 else np.std(d1_fast)
            vol_full = np.std(d1_fast)

            # Jerk (3rd derivative approx)
            if len(d2) > 1:
                jerk = np.mean(np.diff(d2[-6:])) if len(d2) >= 6 else np.mean(np.diff(d2))
            else:
                jerk = 0.0

            feat = np.array([
                np.mean(d1_fast), np.std(d1_fast), d1_fast[-1],    # fast RoC
                np.mean(d1_med), np.std(d1_med), d1_med[-1],       # medium RoC
                np.mean(d1_slow), np.std(d1_slow), d1_slow[-1],    # slow RoC
                np.mean(d2), np.std(d2), d2[-1],                   # acceleration
                momentum,                                          # weighted trend
                vol_5, vol_10, vol_full,                            # volatility
                jerk,                                               # jerk
                np.max(d1_fast) - np.min(d1_fast),                  # RoC range
            ])
            deriv_feats.append(feat)

        deriv_feats = np.array(deriv_feats)
        if len(deriv_feats) != len(X):
            deriv_feats = np.zeros((len(X), 18))

        X_aug = np.column_stack([X, deriv_feats])

        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        Xa_tr, Xa_vl = X_aug[:len(X_tr)], X_aug[len(X_tr):]
        gc_vl = g_cur[len(X_tr):]

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)
        Xa_tr_clean = np.nan_to_num(Xa_tr)
        Xa_vl_clean = np.nan_to_num(Xa_vl)

        # Ridge baseline
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr_clean, yd_tr)
        r2_ridge_base = compute_r2(ya_vl, ridge_base.predict(X_vl_clean) + gc_vl)

        # Ridge + derivatives
        ridge_deriv = Ridge(alpha=1.0)
        ridge_deriv.fit(Xa_tr_clean, yd_tr)
        r2_ridge_deriv = compute_r2(ya_vl, ridge_deriv.predict(Xa_vl_clean) + gc_vl)

        # XGBoost baseline
        xgb_base = make_xgb()
        xgb_base.fit(X_tr_clean, yd_tr)
        r2_xgb_base = compute_r2(ya_vl, xgb_base.predict(X_vl_clean) + gc_vl)

        # XGBoost + derivatives
        xgb_deriv = make_xgb()
        xgb_deriv.fit(Xa_tr_clean, yd_tr)
        r2_xgb_deriv = compute_r2(ya_vl, xgb_deriv.predict(Xa_vl_clean) + gc_vl)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_deriv': round(r2_ridge_deriv, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_deriv': round(r2_xgb_deriv, 4),
            'ridge_gain': round(r2_ridge_deriv - r2_ridge_base, 4),
            'xgb_gain': round(r2_xgb_deriv - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge Δ={r2_ridge_deriv-r2_ridge_base:+.4f} "
                  f"xgb Δ={r2_xgb_deriv-r2_xgb_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_base', 'r2_ridge_deriv',
                        'r2_xgb_base', 'r2_xgb_deriv']}
    ridge_wins = sum(1 for r in results if r['ridge_gain'] > 0.001)
    xgb_wins = sum(1 for r in results if r['xgb_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: {means['r2_ridge_base']:.4f}→"
                   f"{means['r2_ridge_deriv']:.4f} (wins={ridge_wins}) | "
                   f"xgb: {means['r2_xgb_base']:.4f}→"
                   f"{means['r2_xgb_deriv']:.4f} "
                   f"(wins={xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1136: Insulin-Glucose Interaction Terms
# ---------------------------------------------------------------------------

def exp_1136_interaction_terms(patients, detail=False):
    """Create explicit interaction features: glucose×IOB, glucose×COB,
    trend×IOB, derivative×IOB. Captures nonlinear insulin-glucose coupling.
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur

        # Build interaction features per window
        g = glucose / GLUCOSE_SCALE
        interaction_feats = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            gw = np.nan_to_num(
                gw, nan=np.nanmean(gw) if np.any(~np.isnan(gw)) else 0.4)
            pw = physics[i:i + WINDOW]
            if np.isnan(pw).any():
                pw = np.nan_to_num(pw, nan=0.0)
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            # Physics channels: supply(~IOB), demand(~COB), hepatic, net
            supply = pw[:, 0]   # ≈ IOB proxy
            demand = pw[:, 1]   # ≈ COB proxy
            g_last = gw[-1]
            g_mean = np.mean(gw)

            # Glucose rate of change
            d1 = np.diff(gw)
            g_trend = np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1)
            g_deriv_last = d1[-1] if len(d1) > 0 else 0.0

            # Interaction terms
            iob_last = supply[-1]
            cob_last = demand[-1]
            iob_mean = np.mean(supply)
            cob_mean = np.mean(demand)

            feat = np.array([
                g_last * iob_last,           # glucose × IOB
                g_last * cob_last,           # glucose × COB
                g_mean * iob_mean,           # mean glucose × mean IOB
                g_mean * cob_mean,           # mean glucose × mean COB
                g_trend * iob_last,          # trend × IOB
                g_trend * cob_last,          # trend × COB
                g_deriv_last * iob_last,     # derivative × IOB
                g_deriv_last * cob_last,     # derivative × COB
                iob_last * cob_last,         # IOB × COB
                g_last * iob_last * cob_last,  # triple interaction
                (g_last - 0.3) * iob_last,   # glucose deviation × IOB (120 mg/dL center)
                g_trend * iob_mean * cob_mean, # trend × mean IOB × mean COB
            ])
            interaction_feats.append(feat)

        interaction_feats = np.array(interaction_feats)
        if len(interaction_feats) != len(X):
            interaction_feats = np.zeros((len(X), 12))

        X_aug = np.column_stack([X, interaction_feats])

        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        Xa_tr, Xa_vl = X_aug[:len(X_tr)], X_aug[len(X_tr):]
        gc_vl = g_cur[len(X_tr):]

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)
        Xa_tr_clean = np.nan_to_num(Xa_tr)
        Xa_vl_clean = np.nan_to_num(Xa_vl)

        # Ridge baseline (can't learn interactions)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr_clean, yd_tr)
        r2_ridge_base = compute_r2(ya_vl, ridge_base.predict(X_vl_clean) + gc_vl)

        # Ridge + explicit interactions (should help Ridge the most)
        ridge_int = Ridge(alpha=1.0)
        ridge_int.fit(Xa_tr_clean, yd_tr)
        r2_ridge_int = compute_r2(ya_vl, ridge_int.predict(Xa_vl_clean) + gc_vl)

        # XGBoost baseline (can learn interactions implicitly)
        xgb_base = make_xgb()
        xgb_base.fit(X_tr_clean, yd_tr)
        r2_xgb_base = compute_r2(ya_vl, xgb_base.predict(X_vl_clean) + gc_vl)

        # XGBoost + explicit interactions (may or may not help)
        xgb_int = make_xgb()
        xgb_int.fit(Xa_tr_clean, yd_tr)
        r2_xgb_int = compute_r2(ya_vl, xgb_int.predict(Xa_vl_clean) + gc_vl)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_interactions': round(r2_ridge_int, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_interactions': round(r2_xgb_int, 4),
            'ridge_gain': round(r2_ridge_int - r2_ridge_base, 4),
            'xgb_gain': round(r2_xgb_int - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge Δ={r2_ridge_int-r2_ridge_base:+.4f} "
                  f"xgb Δ={r2_xgb_int-r2_xgb_base:+.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_base', 'r2_ridge_interactions',
                        'r2_xgb_base', 'r2_xgb_interactions']}
    ridge_wins = sum(1 for r in results if r['ridge_gain'] > 0.001)
    xgb_wins = sum(1 for r in results if r['xgb_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: {means['r2_ridge_base']:.4f}→"
                   f"{means['r2_ridge_interactions']:.4f} (wins={ridge_wins}) | "
                   f"xgb: {means['r2_xgb_base']:.4f}→"
                   f"{means['r2_xgb_interactions']:.4f} "
                   f"(wins={xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1137: Residual Boosting Chain
# ---------------------------------------------------------------------------

def exp_1137_residual_chain(patients, detail=False):
    """Multi-stage residual chain: Ridge→XGBoost→LSTM→final XGBoost.
    Each stage targets what the previous couldn't capture.
    Stop when marginal gain < 0.002.
    """
    RESIDUAL_WINDOW = 12

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 100:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 400:
            continue

        y_delta = y_abs - g_cur
        X_tr, X_vl, X_te, yd_tr, yd_vl, yd_te = split_3way(X, y_delta)
        _, _, _, ya_tr, ya_vl, ya_te = split_3way(X, y_abs)
        gc_tr, gc_vl, gc_te = split_3way(X, g_cur)[3:]

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)
        X_te_clean = np.nan_to_num(X_te)

        stage_r2s = {}

        # Stage 1: Ridge on Δg
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr_clean, yd_tr)
        pred_te_1 = ridge.predict(X_te_clean) + gc_te
        pred_vl_1 = ridge.predict(X_vl_clean) + gc_vl
        r2_s1 = compute_r2(ya_te, pred_te_1)
        stage_r2s['ridge'] = r2_s1

        # Stage 2: XGBoost on Ridge residuals
        resid_tr_1 = ya_tr - (ridge.predict(X_tr_clean) + gc_tr)
        resid_vl_1 = ya_vl - pred_vl_1

        xgb_s2 = make_xgb(n_estimators=100, max_depth=3)
        xgb_s2.fit(X_tr_clean, resid_tr_1)
        pred_te_2 = pred_te_1 + xgb_s2.predict(X_te_clean)
        pred_vl_2 = pred_vl_1 + xgb_s2.predict(X_vl_clean)
        r2_s2 = compute_r2(ya_te, pred_te_2)
        stage_r2s['ridge_xgb'] = r2_s2
        gain_s2 = r2_s2 - r2_s1

        # Stage 3: LSTM on XGBoost residuals (if gain > 0.002)
        r2_s3 = r2_s2
        gain_s3 = 0.0
        if gain_s2 > 0.002:
            resid_vl_2 = ya_vl - pred_vl_2

            resid_X, resid_y = [], []
            for i in range(RESIDUAL_WINDOW, len(resid_vl_2)):
                resid_X.append(resid_vl_2[i-RESIDUAL_WINDOW:i])
                resid_y.append(resid_vl_2[i])

            if len(resid_X) >= 50:
                resid_X_arr = np.array(resid_X).reshape(-1, RESIDUAL_WINDOW, 1)
                resid_y_arr = np.array(resid_y)

                lstm = ResidualLSTM(hidden=32, seq_len=RESIDUAL_WINDOW).to(DEVICE)
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
                corrected = pred_te_2.copy()
                resid_buffer = list(resid_vl_2[-RESIDUAL_WINDOW:])

                lstm.eval()
                with torch.no_grad():
                    for i in range(len(ya_te)):
                        if len(resid_buffer) >= RESIDUAL_WINDOW:
                            w = np.array(resid_buffer[-RESIDUAL_WINDOW:]).reshape(
                                1, RESIDUAL_WINDOW, 1)
                            wt = torch.tensor(w, dtype=torch.float32).to(DEVICE)
                            correction = lstm(wt).cpu().numpy()[0]
                            corrected[i] = pred_te_2[i] + correction
                        actual_resid = ya_te[i] - pred_te_2[i]
                        resid_buffer.append(actual_resid)

                r2_s3 = compute_r2(ya_te, corrected)
                gain_s3 = r2_s3 - r2_s2
                stage_r2s['ridge_xgb_lstm'] = r2_s3

                # Stage 4: Final XGBoost on LSTM residuals (if gain > 0.002)
                if gain_s3 > 0.002:
                    resid_tr_3 = ya_tr - (ridge.predict(X_tr_clean) + gc_tr +
                                          xgb_s2.predict(X_tr_clean))
                    xgb_s4 = make_xgb(n_estimators=50, max_depth=2)
                    xgb_s4.fit(X_tr_clean, resid_tr_3)
                    pred_te_4 = corrected + xgb_s4.predict(X_te_clean)
                    r2_s4 = compute_r2(ya_te, pred_te_4)
                    stage_r2s['ridge_xgb_lstm_xgb'] = r2_s4
                    stage_r2s['final'] = r2_s4
                else:
                    stage_r2s['final'] = r2_s3
            else:
                stage_r2s['final'] = r2_s2
        else:
            stage_r2s['final'] = r2_s2

        n_stages = len(stage_r2s) - 1  # exclude 'final' key
        total_gain = stage_r2s['final'] - r2_s1

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'stage_r2s': {k: round(v, 4) for k, v in stage_r2s.items()},
            'n_stages': n_stages,
            'total_gain': round(total_gain, 4),
        })

        if detail:
            stages_str = ' → '.join(f"{k}={v:.4f}" for k, v in stage_r2s.items()
                                     if k != 'final')
            print(f"  {p['name']}: {stages_str} total_gain={total_gain:+.4f}")

    mean_base = np.mean([r['stage_r2s']['ridge'] for r in results])
    mean_final = np.mean([r['stage_r2s']['final'] for r in results])
    mean_gain = np.mean([r['total_gain'] for r in results])
    mean_stages = np.mean([r['n_stages'] for r in results])

    return {
        'status': 'pass',
        'detail': (f"base={mean_base:.4f} final={mean_final:.4f} "
                   f"gain={mean_gain:+.4f} avg_stages={mean_stages:.1f} "
                   f"({len(results)} patients)"),
        'results': {'per_patient': results, 'summary': {
            'mean_base': round(mean_base, 4),
            'mean_final': round(mean_final, 4),
            'mean_gain': round(mean_gain, 4),
            'mean_stages': round(mean_stages, 1),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1138: Robust Loss Functions
# ---------------------------------------------------------------------------

def exp_1138_robust_loss(patients, detail=False):
    """Compare MSE vs Huber vs quantile loss for XGBoost and Ridge.

    Glucose data has outliers from sensor errors and compression artifacts.
    Huber loss may be more robust than MSE.
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur
        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        gc_vl = g_cur[len(X_tr):]

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)

        res = {'patient': p['name'], 'n_samples': len(X)}

        # Ridge MSE (standard)
        ridge_mse = Ridge(alpha=1.0)
        ridge_mse.fit(X_tr_clean, yd_tr)
        r2_ridge_mse = compute_r2(ya_vl, ridge_mse.predict(X_vl_clean) + gc_vl)
        res['r2_ridge_mse'] = round(r2_ridge_mse, 4)

        # Ridge with Huber-like behavior via weighted refit
        # Fit, find outliers, downweight, refit
        pred_init = ridge_mse.predict(X_tr_clean)
        residuals = yd_tr - pred_init
        mad = np.median(np.abs(residuals - np.median(residuals)))
        huber_delta = 1.345 * mad if mad > 0 else 1.0
        weights = np.where(np.abs(residuals) <= huber_delta, 1.0,
                           huber_delta / (np.abs(residuals) + 1e-8))
        # Weighted Ridge via sample weighting
        W_sqrt = np.sqrt(weights)
        ridge_huber = Ridge(alpha=1.0)
        ridge_huber.fit(X_tr_clean * W_sqrt[:, None], yd_tr * W_sqrt)
        pred_huber = ridge_huber.predict(X_vl_clean) + gc_vl
        r2_ridge_huber = compute_r2(ya_vl, pred_huber)
        res['r2_ridge_huber'] = round(r2_ridge_huber, 4)

        # XGBoost MSE
        xgb_mse = make_xgb()
        xgb_mse.fit(X_tr_clean, yd_tr)
        r2_xgb_mse = compute_r2(ya_vl, xgb_mse.predict(X_vl_clean) + gc_vl)
        res['r2_xgb_mse'] = round(r2_xgb_mse, 4)

        # XGBoost Huber loss
        xgb_huber = make_xgb(objective='reg:pseudohubererror')
        xgb_huber.fit(X_tr_clean, yd_tr)
        r2_xgb_huber = compute_r2(ya_vl, xgb_huber.predict(X_vl_clean) + gc_vl)
        res['r2_xgb_huber'] = round(r2_xgb_huber, 4)

        # XGBoost quantile loss (median regression, τ=0.5)
        try:
            xgb_quant = make_xgb(objective='reg:quantileerror',
                                  quantile_alpha=0.5)
            xgb_quant.fit(X_tr_clean, yd_tr)
            r2_xgb_quant = compute_r2(ya_vl, xgb_quant.predict(X_vl_clean) + gc_vl)
            res['r2_xgb_quantile'] = round(r2_xgb_quant, 4)
        except Exception:
            res['r2_xgb_quantile'] = None

        # Compute MAE for each (robust models should have lower MAE)
        pred_mse_vl = xgb_mse.predict(X_vl_clean) + gc_vl
        pred_hub_vl = xgb_huber.predict(X_vl_clean) + gc_vl
        res['mae_xgb_mse'] = round(compute_mae(ya_vl * GLUCOSE_SCALE,
                                                 pred_mse_vl * GLUCOSE_SCALE), 1)
        res['mae_xgb_huber'] = round(compute_mae(ya_vl * GLUCOSE_SCALE,
                                                   pred_hub_vl * GLUCOSE_SCALE), 1)

        res['ridge_huber_gain'] = round(r2_ridge_huber - r2_ridge_mse, 4)
        res['xgb_huber_gain'] = round(r2_xgb_huber - r2_xgb_mse, 4)

        results.append(res)

        if detail:
            print(f"  {p['name']}: ridge mse={r2_ridge_mse:.4f} huber={r2_ridge_huber:.4f} | "
                  f"xgb mse={r2_xgb_mse:.4f} huber={r2_xgb_huber:.4f} "
                  f"quant={res.get('r2_xgb_quantile', 'N/A')}")

    means = {}
    for k in ['r2_ridge_mse', 'r2_ridge_huber', 'r2_xgb_mse', 'r2_xgb_huber']:
        means[k] = round(np.mean([r[k] for r in results]), 4)
    quant_vals = [r['r2_xgb_quantile'] for r in results if r['r2_xgb_quantile'] is not None]
    if quant_vals:
        means['r2_xgb_quantile'] = round(np.mean(quant_vals), 4)

    ridge_huber_wins = sum(1 for r in results if r['ridge_huber_gain'] > 0.001)
    xgb_huber_wins = sum(1 for r in results if r['xgb_huber_gain'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: mse={means['r2_ridge_mse']:.4f} "
                   f"huber={means['r2_ridge_huber']:.4f} "
                   f"(wins={ridge_huber_wins}) | "
                   f"xgb: mse={means['r2_xgb_mse']:.4f} "
                   f"huber={means['r2_xgb_huber']:.4f} "
                   f"(wins={xgb_huber_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1139: Feature Importance & Selection
# ---------------------------------------------------------------------------

def exp_1139_feature_selection(patients, detail=False):
    """Run XGBoost with full features, extract importances, retrain with top-K.
    Also try L1 (Lasso) selection. Hypothesis: removing noisy features
    improves generalization.
    """
    TOP_KS = [10, 20, 50]

    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur
        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        gc_vl = g_cur[len(X_tr):]

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)

        res = {'patient': p['name'], 'n_features_total': X.shape[1]}

        # Full XGBoost baseline
        xgb_full = make_xgb()
        xgb_full.fit(X_tr_clean, yd_tr)
        pred_full = xgb_full.predict(X_vl_clean) + gc_vl
        r2_full = compute_r2(ya_vl, pred_full)
        res['r2_xgb_full'] = round(r2_full, 4)

        # Get feature importances
        if XGB_AVAILABLE:
            importances = xgb_full.feature_importances_
        else:
            importances = np.abs(xgb_full.feature_importances_)

        sorted_idx = np.argsort(importances)[::-1]

        # Train with top-K features
        for k in TOP_KS:
            if k >= X.shape[1]:
                res[f'r2_xgb_top{k}'] = round(r2_full, 4)
                continue
            top_k_idx = sorted_idx[:k]
            Xk_tr = X_tr_clean[:, top_k_idx]
            Xk_vl = X_vl_clean[:, top_k_idx]

            xgb_k = make_xgb()
            xgb_k.fit(Xk_tr, yd_tr)
            pred_k = xgb_k.predict(Xk_vl) + gc_vl
            r2_k = compute_r2(ya_vl, pred_k)
            res[f'r2_xgb_top{k}'] = round(r2_k, 4)
            res[f'gain_top{k}'] = round(r2_k - r2_full, 4)

        # L1 (Lasso) feature selection
        lasso = Lasso(alpha=0.001, max_iter=5000, random_state=42)
        lasso.fit(X_tr_clean, yd_tr)
        selected_mask = np.abs(lasso.coef_) > 1e-6
        n_selected = int(np.sum(selected_mask))
        res['lasso_n_selected'] = n_selected

        if n_selected > 5:
            Xl_tr = X_tr_clean[:, selected_mask]
            Xl_vl = X_vl_clean[:, selected_mask]
            xgb_lasso = make_xgb()
            xgb_lasso.fit(Xl_tr, yd_tr)
            pred_lasso = xgb_lasso.predict(Xl_vl) + gc_vl
            r2_lasso = compute_r2(ya_vl, pred_lasso)
            res['r2_xgb_lasso'] = round(r2_lasso, 4)
            res['lasso_gain'] = round(r2_lasso - r2_full, 4)
        else:
            res['r2_xgb_lasso'] = round(r2_full, 4)
            res['lasso_gain'] = 0.0

        # Top 5 feature indices
        res['top5_feature_idx'] = sorted_idx[:5].tolist()

        results.append(res)

        if detail:
            print(f"  {p['name']}: full={r2_full:.4f} "
                  f"top10={res.get('r2_xgb_top10', 'N/A')} "
                  f"top20={res.get('r2_xgb_top20', 'N/A')} "
                  f"top50={res.get('r2_xgb_top50', 'N/A')} "
                  f"lasso(n={n_selected})={res.get('r2_xgb_lasso', 'N/A')}")

    means = {'r2_xgb_full': round(np.mean([r['r2_xgb_full'] for r in results]), 4)}
    for k in TOP_KS:
        key = f'r2_xgb_top{k}'
        vals = [r[key] for r in results if r.get(key) is not None]
        if vals:
            means[key] = round(np.mean(vals), 4)
    lasso_vals = [r['r2_xgb_lasso'] for r in results]
    means['r2_xgb_lasso'] = round(np.mean(lasso_vals), 4)

    best_k = max(means, key=means.get)
    top20_wins = sum(1 for r in results
                     if r.get('gain_top20', 0) > 0.001)

    return {
        'status': 'pass',
        'detail': (f"full={means['r2_xgb_full']:.4f} " +
                   ' '.join(f"{k}={v:.4f}" for k, v in means.items()
                            if k != 'r2_xgb_full') +
                   f" best={best_k} (top20_wins={top20_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# EXP-1140: Dawn Phenomenon Conditioning
# ---------------------------------------------------------------------------

def exp_1140_dawn_conditioning(patients, detail=False):
    """Exploit EXP-422 finding: universal −48 mg/dL dawn effect.

    Add dawn-specific conditioning channel with enhanced resolution
    around 3-7 AM. Compare: plain time → dawn channel → learned dawn.
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]
        glucose, _ = impute_glucose(glucose_raw)

        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        y_delta = y_abs - g_cur

        # Build dawn features per window
        g = glucose / GLUCOSE_SCALE
        dawn_feats_list = []
        tod_feats_list = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            gw = g[i:i + WINDOW]
            if np.isnan(gw).mean() > 0.3:
                continue
            yv = g[i + WINDOW + HORIZON - 1]
            if np.isnan(yv):
                continue

            center_idx = i + WINDOW // 2
            fractional_hour = (center_idx * 5.0 / 60.0) % 24.0

            # Plain time-of-day (for comparison)
            hour_rad = 2.0 * np.pi * fractional_hour / 24.0
            tod_feats_list.append([np.sin(hour_rad), np.cos(hour_rad)])

            # Dawn conditioning: enhanced resolution around 3-7 AM
            # Hours since midnight
            h = fractional_hour

            # Dawn proximity: peaked around 3-7 AM
            dawn_center = 5.0  # peak of dawn effect
            dawn_width = 2.0
            dawn_proximity = np.exp(-0.5 * ((h - dawn_center) / dawn_width) ** 2)

            # Dawn phase: linear ramp through 3-7 AM window
            if 3 <= h < 7:
                dawn_phase = (h - 3.0) / 4.0  # 0 at 3AM, 1 at 7AM
            else:
                dawn_phase = 0.0

            # Hours since 3 AM (with wrap-around)
            hours_since_3am = (h - 3.0) % 24.0
            dawn_distance = min(hours_since_3am, 24.0 - hours_since_3am)

            # Expected dawn magnitude (−48 mg/dL = −0.12 scaled)
            dawn_magnitude = -0.12 * dawn_proximity

            # Second harmonic for pre-dawn dip
            pre_dawn_rad = 2.0 * np.pi * (h - 3.0) / 4.0 if 3 <= h < 7 else 0.0
            pre_dawn_sin = np.sin(pre_dawn_rad)
            pre_dawn_cos = np.cos(pre_dawn_rad)

            dawn_feats_list.append([
                dawn_proximity, dawn_phase, dawn_distance,
                dawn_magnitude, pre_dawn_sin, pre_dawn_cos,
            ])

        dawn_feats = np.array(dawn_feats_list)
        tod_feats = np.array(tod_feats_list)

        if len(dawn_feats) != len(X):
            dawn_feats = np.zeros((len(X), 6))
            tod_feats = np.zeros((len(X), 2))

        X_tod = np.column_stack([X, tod_feats])
        X_dawn = np.column_stack([X, dawn_feats])
        X_both = np.column_stack([X, tod_feats, dawn_feats])

        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        gc_vl = g_cur[len(X_tr):]

        split_idx = len(X_tr)

        X_tr_clean = np.nan_to_num(X_tr)
        X_vl_clean = np.nan_to_num(X_vl)

        # Baseline (no time features)
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_tr_clean, yd_tr)
        r2_base = compute_r2(ya_vl, ridge_base.predict(X_vl_clean) + gc_vl)

        # Plain time-of-day
        Xt_tr = np.nan_to_num(X_tod[:split_idx])
        Xt_vl = np.nan_to_num(X_tod[split_idx:])
        ridge_tod = Ridge(alpha=1.0)
        ridge_tod.fit(Xt_tr, yd_tr)
        r2_tod = compute_r2(ya_vl, ridge_tod.predict(Xt_vl) + gc_vl)

        # Dawn conditioning only
        Xd_tr = np.nan_to_num(X_dawn[:split_idx])
        Xd_vl = np.nan_to_num(X_dawn[split_idx:])
        ridge_dawn = Ridge(alpha=1.0)
        ridge_dawn.fit(Xd_tr, yd_tr)
        r2_dawn = compute_r2(ya_vl, ridge_dawn.predict(Xd_vl) + gc_vl)

        # Both time + dawn
        Xb_tr = np.nan_to_num(X_both[:split_idx])
        Xb_vl = np.nan_to_num(X_both[split_idx:])
        ridge_both = Ridge(alpha=1.0)
        ridge_both.fit(Xb_tr, yd_tr)
        r2_both = compute_r2(ya_vl, ridge_both.predict(Xb_vl) + gc_vl)

        # XGBoost with dawn conditioning
        xgb_base = make_xgb()
        xgb_base.fit(X_tr_clean, yd_tr)
        r2_xgb_base = compute_r2(ya_vl, xgb_base.predict(X_vl_clean) + gc_vl)

        xgb_dawn = make_xgb()
        xgb_dawn.fit(Xd_tr, yd_tr)
        r2_xgb_dawn = compute_r2(ya_vl, xgb_dawn.predict(Xd_vl) + gc_vl)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_base': round(r2_base, 4),
            'r2_tod': round(r2_tod, 4),
            'r2_dawn': round(r2_dawn, 4),
            'r2_both': round(r2_both, 4),
            'r2_xgb_base': round(r2_xgb_base, 4),
            'r2_xgb_dawn': round(r2_xgb_dawn, 4),
            'dawn_gain_ridge': round(r2_dawn - r2_base, 4),
            'dawn_gain_xgb': round(r2_xgb_dawn - r2_xgb_base, 4),
        })

        if detail:
            print(f"  {p['name']}: base={r2_base:.4f} tod={r2_tod:.4f} "
                  f"dawn={r2_dawn:.4f} both={r2_both:.4f} | "
                  f"xgb: {r2_xgb_base:.4f}→{r2_xgb_dawn:.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_base', 'r2_tod', 'r2_dawn', 'r2_both',
                        'r2_xgb_base', 'r2_xgb_dawn']}
    dawn_ridge_wins = sum(1 for r in results if r['dawn_gain_ridge'] > 0.001)
    dawn_xgb_wins = sum(1 for r in results if r['dawn_gain_xgb'] > 0.001)

    return {
        'status': 'pass',
        'detail': (f"ridge: base={means['r2_base']:.4f} tod={means['r2_tod']:.4f} "
                   f"dawn={means['r2_dawn']:.4f} both={means['r2_both']:.4f} "
                   f"(dawn_wins={dawn_ridge_wins}) | "
                   f"xgb: {means['r2_xgb_base']:.4f}→{means['r2_xgb_dawn']:.4f} "
                   f"(wins={dawn_xgb_wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': means},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1131', 'Extended Context Window (4h, 6h)', exp_1131_extended_context),
    ('EXP-1132', 'Time-of-Day Conditioning', exp_1132_time_of_day),
    ('EXP-1133', 'Stacked Generalization (Level-2 Meta-Learner)', exp_1133_stacked_generalization),
    ('EXP-1134', 'Patient-Adaptive Online Learning', exp_1134_online_learning),
    ('EXP-1135', 'Glucose Derivative Features', exp_1135_derivative_features),
    ('EXP-1136', 'Insulin-Glucose Interaction Terms', exp_1136_interaction_terms),
    ('EXP-1137', 'Residual Boosting Chain', exp_1137_residual_chain),
    ('EXP-1138', 'Robust Loss Functions', exp_1138_robust_loss),
    ('EXP-1139', 'Feature Importance & Selection', exp_1139_feature_selection),
    ('EXP-1140', 'Dawn Phenomenon Conditioning', exp_1140_dawn_conditioning),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1131-1140: Remaining High-Value Opportunities')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1131)')
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
