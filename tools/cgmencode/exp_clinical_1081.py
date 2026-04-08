#!/usr/bin/env python3
"""EXP-1081 to EXP-1090: Feature Engineering and Information Extraction.

Building on 80 experiments of findings (EXP-1001–1080):
- SOTA R²=0.532 (3-fold block CV), noise ceiling R²=0.854
- Error decomposition (EXP-1079): 76.3% of error is UNEXPLAINED (missing features)
- Model capacity is NOT the bottleneck — feature engineering is
- Physics channels universally beat naive baselines 11/11
- Residual CNN: +0.013, GB: +0.015, personalization essential

This batch shifts focus from model optimization to extracting more information
from available data:
  EXP-1081: Meal timing features from COB ★★
  EXP-1082: Bolus timing features from bolus IOB ★★
  EXP-1083: Glucose momentum features ★★★
  EXP-1084: Physics interaction terms ★
  EXP-1085: Time-in-window statistics ★
  EXP-1086: Lagged cross-correlation features ★★
  EXP-1087: Piecewise linear approximation ★
  EXP-1088: Glucose regime detection ★
  EXP-1089: Feature importance analysis ★★★
  EXP-1090: Best-of-breed feature set ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1081 --detail --save --max-patients 11
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
from sklearn.ensemble import GradientBoostingRegressor

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

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ─── Neural Network Models ───

class ResidualCNN(nn.Module):
    def __init__(self, in_channels, window_size=24):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 32, 3, padding=1)
        self.conv2 = nn.Conv1d(32, 32, 3, padding=1)
        self.conv3 = nn.Conv1d(32, 16, 3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(16, 1)
        self.relu = nn.ReLU()

    def forward(self, x):
        h = self.relu(self.conv1(x.permute(0, 2, 1)))
        h = self.relu(self.conv2(h))
        h = self.relu(self.conv3(h))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


# ─── Core Helper Functions ───

def make_windows(glucose, physics, window=WINDOW, horizon=HORIZON, stride=STRIDE):
    """Create X, y pairs from glucose and physics arrays."""
    X_list, y_list = [], []
    g = glucose / GLUCOSE_SCALE
    for i in range(0, len(g) - window - horizon, stride):
        g_win = g[i:i+window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i+window]
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


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred)**2)
    ss_tot = np.sum((y_true - y_true.mean())**2)
    if ss_tot == 0:
        return 0.0
    return 1 - ss_res / ss_tot


def compute_mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def eval_ridge(X_train, X_val, y_train, y_val, alpha=1.0):
    Xtr = X_train.reshape(len(X_train), -1)
    Xvl = X_val.reshape(len(X_val), -1)
    model = Ridge(alpha=alpha)
    model.fit(Xtr, y_train)
    pred = model.predict(Xvl)
    r2 = compute_r2(y_val, pred)
    return r2, pred, model


def block_cv_eval(X, y, eval_fn, n_folds=3):
    """Block cross-validation. eval_fn(X_train, X_val, y_train, y_val) -> r2."""
    n = len(X)
    fold_size = n // n_folds
    scores = []
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size if fold < n_folds - 1 else n
        mask = np.ones(n, dtype=bool)
        mask[val_start:val_end] = False
        r2 = eval_fn(X[mask], X[~mask], y[mask], y[~mask])
        scores.append(r2)
    return np.mean(scores), scores


def prepare_patient(p):
    """Standard patient preparation: compute physics, make windows."""
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    X, y = make_windows(glucose, physics)
    return X, y


def prepare_patient_raw(p):
    """Return physics channels and glucose separately for custom windowing."""
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    return glucose, physics


def train_cnn(model, X_train, y_train, X_val, y_val, epochs=50, lr=1e-3,
              batch_size=256):
    """Train CNN and return predictions on validation set."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()
    Xt = torch.FloatTensor(X_train).to(DEVICE)
    yt = torch.FloatTensor(y_train).to(DEVICE)
    Xv = torch.FloatTensor(X_val).to(DEVICE)
    best_val_loss = float('inf')
    best_state = None
    for epoch in range(epochs):
        model.train()
        indices = torch.randperm(len(Xt))
        for start in range(0, len(Xt), batch_size):
            idx = indices[start:start+batch_size]
            pred = model(Xt[idx])
            loss = criterion(pred, yt[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_pred = model(Xv)
            val_loss = criterion(val_pred, torch.FloatTensor(y_val).to(DEVICE)).item()
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        final_pred = model(Xv).cpu().numpy()
    return final_pred


# ─── Feature Extraction Helpers ───

def detect_meal_events(cob, threshold=0.01):
    """Detect meal events from COB (carb-on-board) channel.

    A meal event is detected when COB rises (positive delta exceeds threshold).
    Returns list of (start_idx, peak_cob) tuples.
    """
    delta_cob = np.zeros_like(cob)
    delta_cob[1:] = cob[1:] - cob[:-1]
    events = []
    in_meal = False
    meal_start = 0
    peak_cob = 0.0
    for i in range(len(cob)):
        if not in_meal and delta_cob[i] > threshold:
            in_meal = True
            meal_start = i
            peak_cob = cob[i]
        elif in_meal:
            peak_cob = max(peak_cob, cob[i])
            if delta_cob[i] <= 0 and cob[i] < peak_cob * 0.5:
                events.append((meal_start, peak_cob))
                in_meal = False
    if in_meal:
        events.append((meal_start, peak_cob))
    return events


def detect_bolus_events(bolus_iob, threshold=0.01):
    """Detect bolus events from bolus IOB channel.

    A bolus event is detected when bolus IOB jumps upward.
    Returns list of (start_idx, magnitude) tuples.
    """
    delta_iob = np.zeros_like(bolus_iob)
    delta_iob[1:] = bolus_iob[1:] - bolus_iob[:-1]
    events = []
    for i in range(1, len(bolus_iob)):
        if delta_iob[i] > threshold:
            events.append((i, float(delta_iob[i])))
    return events


def compute_meal_timing_features(pk, n):
    """Compute meal timing features from PK channels.

    pk[:,6] = carb_cob
    Returns (n, 4) array: minutes_since_meal, meal_size, meals_in_window, is_postprandial
    """
    cob = pk[:n, 6] if pk.shape[1] > 6 else np.zeros(n)
    meal_events = detect_meal_events(cob)

    minutes_since = np.full(n, 999.0)
    meal_size = np.zeros(n)
    is_postprandial = np.zeros(n)

    for i in range(n):
        best_dist = 999.0
        best_size = 0.0
        for (start, peak) in meal_events:
            dist = (i - start) * 5.0  # 5 min per step
            if 0 <= dist < best_dist:
                best_dist = dist
                best_size = peak
        minutes_since[i] = min(best_dist, 999.0)
        meal_size[i] = best_size
        # Postprandial: within 3 hours (36 steps) of a meal
        is_postprandial[i] = 1.0 if best_dist < 180.0 else 0.0

    # meals_in_window: count meal events in preceding WINDOW steps
    meals_in_window = np.zeros(n)
    for i in range(n):
        count = 0
        for (start, _) in meal_events:
            if i - WINDOW <= start <= i:
                count += 1
        meals_in_window[i] = count

    # Normalize
    minutes_since = minutes_since / 360.0  # max ~6h
    meal_size = meal_size / (np.max(meal_size) + 1e-8)

    return np.column_stack([minutes_since, meal_size, meals_in_window, is_postprandial])


def compute_bolus_timing_features(pk, n):
    """Compute bolus timing features from PK channels.

    pk[:,4] = bolus_iob, pk[:,6] = carb_cob
    Returns (n, 4) array: minutes_since_bolus, bolus_size, is_correction, bolus_carb_timing
    """
    bolus_iob = pk[:n, 4] if pk.shape[1] > 4 else np.zeros(n)
    cob = pk[:n, 6] if pk.shape[1] > 6 else np.zeros(n)

    bolus_events = detect_bolus_events(bolus_iob)
    meal_events = detect_meal_events(cob)

    minutes_since = np.full(n, 999.0)
    bolus_size = np.zeros(n)
    is_correction = np.zeros(n)
    bolus_carb_timing = np.zeros(n)

    for i in range(n):
        best_dist = 999.0
        best_mag = 0.0
        best_bolus_idx = -1
        for (idx, mag) in bolus_events:
            dist = (i - idx) * 5.0
            if 0 <= dist < best_dist:
                best_dist = dist
                best_mag = mag
                best_bolus_idx = idx
        minutes_since[i] = min(best_dist, 999.0)
        bolus_size[i] = best_mag

        # Check if this bolus is a correction (no meal within ±30 min)
        if best_bolus_idx >= 0:
            has_meal = False
            for (m_start, _) in meal_events:
                if abs(m_start - best_bolus_idx) <= 6:  # ±30 min = 6 steps
                    has_meal = True
                    break
            is_correction[i] = 0.0 if has_meal else 1.0

            # Bolus-carb timing (minutes between bolus and nearest carb entry)
            nearest_meal_dist = 999.0
            for (m_start, _) in meal_events:
                meal_dist = abs(m_start - best_bolus_idx) * 5.0
                nearest_meal_dist = min(nearest_meal_dist, meal_dist)
            bolus_carb_timing[i] = min(nearest_meal_dist, 999.0) / 360.0

    # Normalize
    minutes_since = minutes_since / 360.0
    bolus_size = bolus_size / (np.max(bolus_size) + 1e-8)

    return np.column_stack([minutes_since, bolus_size, is_correction, bolus_carb_timing])


def compute_glucose_momentum(glucose_scaled, window=WINDOW):
    """Compute glucose momentum features.

    Returns (n, 5) array: velocity_15, velocity_30, velocity_60, acceleration,
                          trend_consistency
    """
    n = len(glucose_scaled)
    # Velocities at different scales (per 5-min step)
    vel_15 = np.zeros(n)  # 15 min = 3 steps
    vel_30 = np.zeros(n)  # 30 min = 6 steps
    vel_60 = np.zeros(n)  # 60 min = 12 steps

    for lag, arr in [(3, vel_15), (6, vel_30), (12, vel_60)]:
        arr[lag:] = (glucose_scaled[lag:] - glucose_scaled[:-lag]) / lag
        # Handle NaN
        nan_mask = np.isnan(arr)
        arr[nan_mask] = 0.0

    # Acceleration: change in 15-min velocity
    accel = np.zeros(n)
    accel[1:] = vel_15[1:] - vel_15[:-1]

    # Trend consistency: fraction of intervals with same sign of change
    delta = np.zeros(n)
    delta[1:] = glucose_scaled[1:] - glucose_scaled[:-1]
    delta = np.nan_to_num(delta, nan=0.0)

    trend_consistency = np.zeros(n)
    for i in range(window, n):
        win = delta[i-window+1:i+1]
        positive = np.sum(win > 0)
        negative = np.sum(win < 0)
        total = len(win)
        if total > 0:
            trend_consistency[i] = max(positive, negative) / total

    return np.column_stack([vel_15, vel_30, vel_60, accel, trend_consistency])


def compute_excursion_features(glucose_scaled, window=WINDOW):
    """Compute max_excursion and excursion_speed per step.

    Returns (n, 2) array: max_excursion, excursion_speed
    """
    n = len(glucose_scaled)
    max_excursion = np.zeros(n)
    excursion_speed = np.zeros(n)

    for i in range(window, n):
        win = glucose_scaled[i-window:i]
        valid = win[~np.isnan(win)]
        if len(valid) < 2:
            continue
        mn, mx = np.min(valid), np.max(valid)
        exc = mx - mn
        max_excursion[i] = exc
        # Time to max excursion (from start of window)
        idx_max = np.nanargmax(win)
        time_to_max = max(idx_max, 1) * 5.0  # minutes
        excursion_speed[i] = exc / (time_to_max / 60.0)  # per hour

    # Normalize
    max_excursion = max_excursion / (np.max(max_excursion) + 1e-8)
    excursion_speed = excursion_speed / (np.max(excursion_speed) + 1e-8)

    return np.column_stack([max_excursion, excursion_speed])


def compute_window_statistics(glucose_window):
    """Compute statistical summaries of a glucose window.

    Input: (window_size,) array of normalized glucose values.
    Returns: (13,) feature vector.
    """
    valid = glucose_window[~np.isnan(glucose_window)]
    if len(valid) < 2:
        return np.zeros(13)

    mean = np.mean(valid)
    std = np.std(valid)
    mn = np.min(valid)
    mx = np.max(valid)
    rng = mx - mn
    q25, q50, q75 = np.percentile(valid, [25, 50, 75])

    # Skewness
    if std > 1e-8:
        skew = np.mean(((valid - mean) / std) ** 3)
        kurt = np.mean(((valid - mean) / std) ** 4) - 3.0
    else:
        skew = 0.0
        kurt = 0.0

    # Time above 180 mg/dL and below 70 mg/dL (in normalized space)
    high_thresh = 180.0 / GLUCOSE_SCALE
    low_thresh = 70.0 / GLUCOSE_SCALE
    frac_high = np.mean(valid > high_thresh)
    frac_low = np.mean(valid < low_thresh)

    # Coefficient of variation
    cv = std / (mean + 1e-8)

    return np.array([mean, std, mn, mx, rng, skew, kurt,
                     q25, q50, q75, frac_high, frac_low, cv])


def compute_lagged_crosscorr(glucose_win, channel_win, lags=(0, 3, 6, 12)):
    """Compute lagged cross-correlation between glucose and a physics channel.

    Returns: (3,) array: peak_corr, lag_at_peak, corr_at_lag0
    """
    g = np.nan_to_num(glucose_win, nan=0.0)
    c = np.nan_to_num(channel_win, nan=0.0)

    g_std = np.std(g)
    c_std = np.std(c)
    if g_std < 1e-8 or c_std < 1e-8:
        return np.zeros(3)

    g_centered = g - np.mean(g)
    c_centered = c - np.mean(c)

    best_corr = 0.0
    best_lag = 0
    corr_at_0 = 0.0

    for lag in lags:
        if lag >= len(g):
            continue
        if lag == 0:
            corr = np.sum(g_centered * c_centered) / (len(g) * g_std * c_std)
            corr_at_0 = corr
        else:
            g_shift = g_centered[lag:]
            c_shift = c_centered[:-lag]
            n_overlap = len(g_shift)
            if n_overlap < 2:
                continue
            corr = np.sum(g_shift * c_shift) / (n_overlap * g_std * c_std)
        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag

    return np.array([best_corr, best_lag / max(len(lags), 1), corr_at_0])


def piecewise_linear_fit(y, n_segments=4):
    """Fit piecewise linear approximation with n_segments segments.

    Returns: (3 * n_segments,) array of [slope, intercept, breakpoint] per segment.
    """
    n = len(y)
    valid = np.nan_to_num(y, nan=np.nanmean(y) if np.any(~np.isnan(y)) else 0.4)
    seg_len = max(n // n_segments, 2)
    features = []
    for s in range(n_segments):
        start = s * seg_len
        end = min(start + seg_len, n)
        if end - start < 2:
            features.extend([0.0, valid[start] if start < n else 0.0, start / n])
            continue
        seg = valid[start:end]
        x = np.arange(len(seg), dtype=float)
        # Linear fit: y = mx + b
        x_mean = np.mean(x)
        y_mean = np.mean(seg)
        denom = np.sum((x - x_mean) ** 2)
        if denom < 1e-8:
            slope = 0.0
        else:
            slope = np.sum((x - x_mean) * (seg - y_mean)) / denom
        intercept = y_mean - slope * x_mean
        breakpoint = start / n  # normalized position
        features.extend([slope, intercept, breakpoint])
    return np.array(features)


def classify_glucose_regime(g_val):
    """Classify glucose value into regime. g_val in mg/dL."""
    if g_val < 70:
        return 0  # hypo
    elif g_val < 100:
        return 1  # low_normal
    elif g_val < 140:
        return 2  # normal
    elif g_val < 180:
        return 3  # elevated
    else:
        return 4  # high


def compute_regime_features(glucose_mgdl, window=WINDOW):
    """Compute glucose regime features.

    Returns (n, 4): regime_onehot_index, time_in_regime, transitions, entropy
    """
    n = len(glucose_mgdl)
    g = np.nan_to_num(glucose_mgdl, nan=120.0)
    regimes = np.array([classify_glucose_regime(v) for v in g])

    current_regime = np.zeros(n)
    time_in_regime = np.zeros(n)
    transitions = np.zeros(n)
    entropy = np.zeros(n)

    for i in range(n):
        current_regime[i] = regimes[i]
        # Time in current regime
        t = 0
        for j in range(i, -1, -1):
            if regimes[j] == regimes[i]:
                t += 1
            else:
                break
        time_in_regime[i] = t * 5.0 / 60.0  # hours

        # Window-based features
        if i >= window:
            win_regimes = regimes[i-window:i]
            # Transitions
            trans = np.sum(np.abs(np.diff(win_regimes)) > 0)
            transitions[i] = trans
            # Shannon entropy
            counts = np.bincount(win_regimes.astype(int), minlength=5)
            probs = counts / counts.sum()
            probs = probs[probs > 0]
            entropy[i] = -np.sum(probs * np.log2(probs))

    # Normalize
    current_regime = current_regime / 4.0
    time_in_regime = time_in_regime / 6.0  # max ~6h
    transitions = transitions / (window + 1e-8)
    entropy = entropy / np.log2(5)  # max entropy

    return np.column_stack([current_regime, time_in_regime, transitions, entropy])


# ─── EXP-1081: Meal Timing Features ───

def exp_1081_meal_timing(patients, detail=False):
    """Extract meal timing features from COB channel.

    Uses pk[:,6] (carb_cob) to detect meal events. Creates features:
    - minutes_since_last_meal, meal_size_proxy, meals_in_window, is_postprandial
    Compare Ridge with and without these features.
    """
    results = []

    for p in patients:
        pk = p['pk']
        n = min(len(p['df']), len(pk))
        if n < WINDOW + HORIZON + 50:
            continue

        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics), len(pk))
        glucose = glucose[:n]
        physics = physics[:n]

        meal_feats = compute_meal_timing_features(pk, n)

        # Base: glucose + physics
        X_base, y_base = make_windows(glucose, physics)
        # Enhanced: glucose + physics + meal timing
        physics_meal = np.column_stack([physics, meal_feats[:len(physics)]])
        X_meal, y_meal = make_windows(glucose, physics_meal)

        if len(X_base) < 200 or len(X_meal) < 200:
            continue

        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_m_tr, X_m_vl, y_m_tr, y_m_vl = split_data(X_meal, y_meal)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_m_tr = X_m_tr.reshape(len(X_m_tr), -1)
        Xf_m_vl = X_m_vl.reshape(len(X_m_vl), -1)

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        r2_base = compute_r2(y_b_vl, ridge_base.predict(Xf_b_vl))

        ridge_meal = Ridge(alpha=1.0)
        ridge_meal.fit(Xf_m_tr, y_m_tr)
        r2_meal = compute_r2(y_m_vl, ridge_meal.predict(Xf_m_vl))

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_meal_timing': round(r2_meal, 4),
            'gain': round(r2_meal - r2_base, 4),
            'n_samples': len(X_base),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} meal={r2_meal:.4f} "
                  f"({r2_meal - r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_meal': round(np.mean([r['r2_meal_timing'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain'] for r in results]), 4),
        'n_positive': sum(1 for r in results if r['gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'meal={summary["mean_r2_meal"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_positive"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1082: Bolus Timing Features ───

def exp_1082_bolus_timing(patients, detail=False):
    """Extract bolus timing features from bolus IOB channel.

    Uses pk[:,4] (bolus_iob) to detect bolus events. Creates features:
    - minutes_since_last_bolus, bolus_size_proxy, is_correction_bolus, bolus_carb_timing
    Compare Ridge with and without these features.
    """
    results = []

    for p in patients:
        pk = p['pk']
        n = min(len(p['df']), len(pk))
        if n < WINDOW + HORIZON + 50:
            continue

        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics), len(pk))
        glucose = glucose[:n]
        physics = physics[:n]

        bolus_feats = compute_bolus_timing_features(pk, n)

        X_base, y_base = make_windows(glucose, physics)
        physics_bolus = np.column_stack([physics, bolus_feats[:len(physics)]])
        X_bolus, y_bolus = make_windows(glucose, physics_bolus)

        if len(X_base) < 200 or len(X_bolus) < 200:
            continue

        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_bl_tr, X_bl_vl, y_bl_tr, y_bl_vl = split_data(X_bolus, y_bolus)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_bl_tr = X_bl_tr.reshape(len(X_bl_tr), -1)
        Xf_bl_vl = X_bl_vl.reshape(len(X_bl_vl), -1)

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        r2_base = compute_r2(y_b_vl, ridge_base.predict(Xf_b_vl))

        ridge_bolus = Ridge(alpha=1.0)
        ridge_bolus.fit(Xf_bl_tr, y_bl_tr)
        r2_bolus = compute_r2(y_bl_vl, ridge_bolus.predict(Xf_bl_vl))

        # Fraction of correction boluses
        correction_frac = float(np.mean(bolus_feats[:, 2]))

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_bolus_timing': round(r2_bolus, 4),
            'gain': round(r2_bolus - r2_base, 4),
            'correction_bolus_frac': round(correction_frac, 4),
            'n_samples': len(X_base),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} bolus={r2_bolus:.4f} "
                  f"({r2_bolus - r2_base:+.4f}) corr_frac={correction_frac:.2f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_bolus': round(np.mean([r['r2_bolus_timing'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain'] for r in results]), 4),
        'n_positive': sum(1 for r in results if r['gain'] > 0),
        'mean_correction_frac': round(np.mean([r['correction_bolus_frac']
                                                for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'bolus={summary["mean_r2_bolus"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_positive"]}/{len(results)} positive) '
                   f'correction_frac={summary["mean_correction_frac"]:.2f}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1083: Glucose Momentum Features ───

def exp_1083_glucose_momentum(patients, detail=False):
    """Glucose momentum features: multi-scale velocity, acceleration, trend consistency.

    Goes beyond simple derivatives to capture trend momentum:
    - velocity at 15, 30, 60 min scales
    - acceleration (change in velocity)
    - trend consistency (fraction of intervals with same sign)
    - max_excursion and excursion_speed
    Compare Ridge and CNN with/without.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        glucose = glucose[:n]
        physics = physics[:n]

        g_scaled = glucose / GLUCOSE_SCALE
        momentum = compute_glucose_momentum(np.nan_to_num(g_scaled, nan=0.4), WINDOW)
        excursion = compute_excursion_features(np.nan_to_num(g_scaled, nan=0.4), WINDOW)

        # Base: glucose + physics
        X_base, y_base = make_windows(glucose, physics)
        # Enhanced: glucose + physics + momentum + excursion
        extra = np.column_stack([momentum[:len(physics)], excursion[:len(physics)]])
        physics_mom = np.column_stack([physics, extra])
        X_mom, y_mom = make_windows(glucose, physics_mom)

        if len(X_base) < 200 or len(X_mom) < 200:
            continue

        in_ch_base = X_base.shape[2]
        in_ch_mom = X_mom.shape[2]

        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_m_tr, X_m_vl, y_m_tr, y_m_vl = split_data(X_mom, y_mom)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_m_tr = X_m_tr.reshape(len(X_m_tr), -1)
        Xf_m_vl = X_m_vl.reshape(len(X_m_vl), -1)

        # Ridge comparison
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        pred_base = ridge_base.predict(Xf_b_vl)
        r2_ridge_base = compute_r2(y_b_vl, pred_base)

        ridge_mom = Ridge(alpha=1.0)
        ridge_mom.fit(Xf_m_tr, y_m_tr)
        pred_mom = ridge_mom.predict(Xf_m_vl)
        r2_ridge_mom = compute_r2(y_m_vl, pred_mom)

        # CNN comparison: residual correction on base and momentum
        pred_base_tr = ridge_base.predict(Xf_b_tr)
        resid_base_tr = y_b_tr - pred_base_tr

        torch.manual_seed(42)
        cnn_base = ResidualCNN(in_channels=in_ch_base).to(DEVICE)
        cnn_pred_base = train_cnn(cnn_base, X_b_tr, resid_base_tr, X_b_vl,
                                  y_b_vl - pred_base, epochs=50)
        r2_cnn_base = compute_r2(y_b_vl, pred_base + 0.5 * cnn_pred_base)

        pred_mom_tr = ridge_mom.predict(Xf_m_tr)
        resid_mom_tr = y_m_tr - pred_mom_tr

        torch.manual_seed(42)
        cnn_mom = ResidualCNN(in_channels=in_ch_mom).to(DEVICE)
        cnn_pred_mom = train_cnn(cnn_mom, X_m_tr, resid_mom_tr, X_m_vl,
                                 y_m_vl - pred_mom, epochs=50)
        r2_cnn_mom = compute_r2(y_m_vl, pred_mom + 0.5 * cnn_pred_mom)

        res = {
            'patient': p['name'],
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_momentum': round(r2_ridge_mom, 4),
            'r2_cnn_base': round(r2_cnn_base, 4),
            'r2_cnn_momentum': round(r2_cnn_mom, 4),
            'ridge_gain': round(r2_ridge_mom - r2_ridge_base, 4),
            'cnn_gain': round(r2_cnn_mom - r2_cnn_base, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge base={r2_ridge_base:.4f} "
                  f"mom={r2_ridge_mom:.4f}({r2_ridge_mom-r2_ridge_base:+.4f}) "
                  f"cnn base={r2_cnn_base:.4f} "
                  f"mom={r2_cnn_mom:.4f}({r2_cnn_mom-r2_cnn_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge_base': round(np.mean([r['r2_ridge_base'] for r in results]), 4),
        'mean_r2_ridge_momentum': round(np.mean([r['r2_ridge_momentum'] for r in results]), 4),
        'mean_r2_cnn_base': round(np.mean([r['r2_cnn_base'] for r in results]), 4),
        'mean_r2_cnn_momentum': round(np.mean([r['r2_cnn_momentum'] for r in results]), 4),
        'mean_ridge_gain': round(np.mean([r['ridge_gain'] for r in results]), 4),
        'mean_cnn_gain': round(np.mean([r['cnn_gain'] for r in results]), 4),
        'n_ridge_positive': sum(1 for r in results if r['ridge_gain'] > 0),
        'n_cnn_positive': sum(1 for r in results if r['cnn_gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge: base={summary["mean_r2_ridge_base"]:.4f} '
                   f'mom={summary["mean_r2_ridge_momentum"]:.4f} '
                   f'(+{summary["mean_ridge_gain"]:.4f}, '
                   f'{summary["n_ridge_positive"]}/{len(results)}) '
                   f'cnn: base={summary["mean_r2_cnn_base"]:.4f} '
                   f'mom={summary["mean_r2_cnn_momentum"]:.4f} '
                   f'(+{summary["mean_cnn_gain"]:.4f}, '
                   f'{summary["n_cnn_positive"]}/{len(results)})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1084: Physics Interaction Terms ───

def exp_1084_physics_interactions(patients, detail=False):
    """Explicit interaction features between physics channels.

    Creates:
    - supply_demand_ratio, net_flux_momentum, iob_cob_product
    - supply × glucose, demand × glucose interactions
    Compare Ridge with and without interactions.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pk = p['pk']
        n = min(len(glucose), len(physics), len(pk))
        glucose = glucose[:n]
        physics = physics[:n]

        g_scaled = np.nan_to_num(glucose / GLUCOSE_SCALE, nan=0.4)
        supply = physics[:, 0]
        demand = physics[:, 1]

        # Interaction features
        sd_ratio = supply / (demand + 1e-8)
        net_flux = physics[:, 3]  # net channel
        net_momentum = np.zeros(n)
        net_momentum[1:] = net_flux[1:] - net_flux[:-1]

        # IOB × COB from PK channels
        total_iob = pk[:n, 0] if pk.shape[1] > 0 else np.zeros(n)
        carb_cob = pk[:n, 6] if pk.shape[1] > 6 else np.zeros(n)
        iob_cob = total_iob * carb_cob

        supply_glucose = supply * g_scaled
        demand_glucose = demand * g_scaled

        # Normalize interaction features
        for arr in [sd_ratio, net_momentum, iob_cob, supply_glucose, demand_glucose]:
            mx = np.max(np.abs(arr)) + 1e-8
            arr /= mx

        interactions = np.column_stack([sd_ratio, net_momentum, iob_cob,
                                        supply_glucose, demand_glucose])

        X_base, y_base = make_windows(glucose, physics)
        physics_inter = np.column_stack([physics, interactions])
        X_inter, y_inter = make_windows(glucose, physics_inter)

        if len(X_base) < 200 or len(X_inter) < 200:
            continue

        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_i_tr, X_i_vl, y_i_tr, y_i_vl = split_data(X_inter, y_inter)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_i_tr = X_i_tr.reshape(len(X_i_tr), -1)
        Xf_i_vl = X_i_vl.reshape(len(X_i_vl), -1)

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        r2_base = compute_r2(y_b_vl, ridge_base.predict(Xf_b_vl))

        ridge_inter = Ridge(alpha=1.0)
        ridge_inter.fit(Xf_i_tr, y_i_tr)
        r2_inter = compute_r2(y_i_vl, ridge_inter.predict(Xf_i_vl))

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_interactions': round(r2_inter, 4),
            'gain': round(r2_inter - r2_base, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} inter={r2_inter:.4f} "
                  f"({r2_inter - r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_interactions': round(np.mean([r['r2_interactions'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain'] for r in results]), 4),
        'n_positive': sum(1 for r in results if r['gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'inter={summary["mean_r2_interactions"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_positive"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1085: Time-in-Window Statistics ───

def exp_1085_window_statistics(patients, detail=False):
    """Statistical summaries of the glucose window instead of raw values.

    Compare: raw window vs stats-only vs raw+stats for Ridge.
    Stats: mean, std, min, max, range, skewness, kurtosis, quantiles,
           time above 180, time below 70, CV.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        glucose = glucose[:n]
        physics = physics[:n]
        g_scaled = glucose / GLUCOSE_SCALE

        # Build windows manually for stats features
        X_raw_list, X_stats_list, X_combined_list, y_list = [], [], [], []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_scaled[i:i+WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            y_val = g_scaled[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue
            p_win = physics[i:i+WINDOW]
            p_win = np.nan_to_num(p_win, nan=0.0)

            raw_feats = np.concatenate([g_win, p_win.ravel()])
            stats = compute_window_statistics(g_win)
            combined = np.concatenate([raw_feats, stats])

            X_raw_list.append(raw_feats)
            X_stats_list.append(np.concatenate([stats, p_win.mean(axis=0)]))
            X_combined_list.append(combined)
            y_list.append(y_val)

        if len(y_list) < 200:
            continue

        X_raw = np.array(X_raw_list)
        X_stats = np.array(X_stats_list)
        X_combined = np.array(X_combined_list)
        y = np.array(y_list)

        split = int(len(y) * 0.8)

        def eval_set(X_set):
            ridge = Ridge(alpha=1.0)
            ridge.fit(X_set[:split], y[:split])
            pred = ridge.predict(X_set[split:])
            return compute_r2(y[split:], pred)

        r2_raw = eval_set(X_raw)
        r2_stats = eval_set(X_stats)
        r2_combined = eval_set(X_combined)

        res = {
            'patient': p['name'],
            'r2_raw': round(r2_raw, 4),
            'r2_stats_only': round(r2_stats, 4),
            'r2_combined': round(r2_combined, 4),
            'gain_combined_vs_raw': round(r2_combined - r2_raw, 4),
            'n_raw_features': X_raw.shape[1],
            'n_stats_features': X_stats.shape[1],
            'n_combined_features': X_combined.shape[1],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: raw={r2_raw:.4f} stats={r2_stats:.4f} "
                  f"combined={r2_combined:.4f} ({r2_combined - r2_raw:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_raw': round(np.mean([r['r2_raw'] for r in results]), 4),
        'mean_r2_stats': round(np.mean([r['r2_stats_only'] for r in results]), 4),
        'mean_r2_combined': round(np.mean([r['r2_combined'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain_combined_vs_raw'] for r in results]), 4),
        'n_combined_better': sum(1 for r in results if r['gain_combined_vs_raw'] > 0),
        'n_stats_better_than_raw': sum(1 for r in results
                                       if r['r2_stats_only'] > r['r2_raw']),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'raw={summary["mean_r2_raw"]:.4f} '
                   f'stats={summary["mean_r2_stats"]:.4f} '
                   f'combined={summary["mean_r2_combined"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_combined_better"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1086: Lagged Cross-Correlation Features ───

def exp_1086_lagged_crosscorr(patients, detail=False):
    """Lagged cross-correlations between glucose and each physics channel.

    Cross-correlate glucose with supply, demand, net at lags 0, 3, 6, 12 steps.
    Features per channel: peak_correlation, lag_at_peak, correlation_at_lag_0.
    """
    results = []
    lags = (0, 3, 6, 12)

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        glucose = glucose[:n]
        physics = physics[:n]
        g_scaled = np.nan_to_num(glucose / GLUCOSE_SCALE, nan=0.4)

        n_phys_channels = physics.shape[1]

        # Build windowed features with cross-correlation
        X_base_list, X_xcorr_list, y_list = [], [], []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_scaled[i:i+WINDOW]
            if np.sum(np.isnan(glucose[i:i+WINDOW])) > WINDOW * 0.3:
                continue
            g_win_clean = np.nan_to_num(g_win, nan=0.4)
            y_val = g_scaled[i + WINDOW + HORIZON - 1]
            if np.isnan(glucose[i + WINDOW + HORIZON - 1]):
                continue

            p_win = physics[i:i+WINDOW]
            p_win = np.nan_to_num(p_win, nan=0.0)

            base_feats = np.concatenate([g_win_clean, p_win.ravel()])

            # Cross-correlation features per channel
            xcorr_feats = []
            for ch in range(n_phys_channels):
                cc = compute_lagged_crosscorr(g_win_clean, p_win[:, ch], lags)
                xcorr_feats.extend(cc)

            combined = np.concatenate([base_feats, np.array(xcorr_feats)])
            X_base_list.append(base_feats)
            X_xcorr_list.append(combined)
            y_list.append(y_val)

        if len(y_list) < 200:
            continue

        X_base = np.array(X_base_list)
        X_xcorr = np.array(X_xcorr_list)
        y = np.array(y_list)
        split = int(len(y) * 0.8)

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_base[:split], y[:split])
        r2_base = compute_r2(y[split:], ridge_base.predict(X_base[split:]))

        ridge_xcorr = Ridge(alpha=1.0)
        ridge_xcorr.fit(X_xcorr[:split], y[:split])
        r2_xcorr = compute_r2(y[split:], ridge_xcorr.predict(X_xcorr[split:]))

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_xcorr': round(r2_xcorr, 4),
            'gain': round(r2_xcorr - r2_base, 4),
            'n_xcorr_features': n_phys_channels * 3,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} xcorr={r2_xcorr:.4f} "
                  f"({r2_xcorr - r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_xcorr': round(np.mean([r['r2_xcorr'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain'] for r in results]), 4),
        'n_positive': sum(1 for r in results if r['gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'xcorr={summary["mean_r2_xcorr"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_positive"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1087: Piecewise Linear Approximation ───

def exp_1087_piecewise_linear(patients, detail=False):
    """Piecewise linear approximation of the glucose window.

    Approximate the glucose curve with 4 segments, extracting slopes, intercepts,
    and breakpoints. This is a compact representation that may capture distinct
    phases (rise, plateau, fall) better than raw samples.
    Compare Ridge on raw vs piecewise vs combined.
    """
    N_SEGMENTS = 4
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        glucose = glucose[:n]
        physics = physics[:n]
        g_scaled = glucose / GLUCOSE_SCALE

        X_raw_list, X_pw_list, X_combined_list, y_list = [], [], [], []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_scaled[i:i+WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win_clean = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            y_val = g_scaled[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            p_win = physics[i:i+WINDOW]
            p_win = np.nan_to_num(p_win, nan=0.0)

            raw = np.concatenate([g_win_clean, p_win.ravel()])
            pw_feats = piecewise_linear_fit(g_win_clean, N_SEGMENTS)
            # Also add piecewise linear fits for each physics channel mean
            for ch in range(physics.shape[1]):
                pw_feats = np.concatenate([pw_feats,
                                           piecewise_linear_fit(p_win[:, ch], N_SEGMENTS)])

            combined = np.concatenate([raw, pw_feats])

            X_raw_list.append(raw)
            X_pw_list.append(pw_feats)
            X_combined_list.append(combined)
            y_list.append(y_val)

        if len(y_list) < 200:
            continue

        X_raw = np.array(X_raw_list)
        X_pw = np.array(X_pw_list)
        X_combined = np.array(X_combined_list)
        y = np.array(y_list)
        split = int(len(y) * 0.8)

        def eval_set(X_set):
            ridge = Ridge(alpha=1.0)
            ridge.fit(X_set[:split], y[:split])
            return compute_r2(y[split:], ridge.predict(X_set[split:]))

        r2_raw = eval_set(X_raw)
        r2_pw = eval_set(X_pw)
        r2_combined = eval_set(X_combined)

        res = {
            'patient': p['name'],
            'r2_raw': round(r2_raw, 4),
            'r2_piecewise': round(r2_pw, 4),
            'r2_combined': round(r2_combined, 4),
            'gain_combined_vs_raw': round(r2_combined - r2_raw, 4),
            'n_pw_features': X_pw.shape[1],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: raw={r2_raw:.4f} pw={r2_pw:.4f} "
                  f"combined={r2_combined:.4f} ({r2_combined - r2_raw:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_raw': round(np.mean([r['r2_raw'] for r in results]), 4),
        'mean_r2_piecewise': round(np.mean([r['r2_piecewise'] for r in results]), 4),
        'mean_r2_combined': round(np.mean([r['r2_combined'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain_combined_vs_raw'] for r in results]), 4),
        'n_combined_better': sum(1 for r in results if r['gain_combined_vs_raw'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'raw={summary["mean_r2_raw"]:.4f} '
                   f'pw={summary["mean_r2_piecewise"]:.4f} '
                   f'combined={summary["mean_r2_combined"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_combined_better"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1088: Glucose Regime Detection ───

def exp_1088_glucose_regime(patients, detail=False):
    """Classify current glucose state and use regime features.

    Features: regime class, time in regime, transitions in window, regime entropy.
    Thresholds: hypo <70, low_normal 70-100, normal 100-140, elevated 140-180, high >180.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        glucose = glucose[:n]
        physics = physics[:n]

        glucose_mgdl = np.nan_to_num(glucose, nan=120.0)
        regime_feats = compute_regime_features(glucose_mgdl, WINDOW)

        X_base, y_base = make_windows(glucose, physics)
        physics_regime = np.column_stack([physics, regime_feats[:len(physics)]])
        X_regime, y_regime = make_windows(glucose, physics_regime)

        if len(X_base) < 200 or len(X_regime) < 200:
            continue

        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_r_tr, X_r_vl, y_r_tr, y_r_vl = split_data(X_regime, y_regime)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_r_tr = X_r_tr.reshape(len(X_r_tr), -1)
        Xf_r_vl = X_r_vl.reshape(len(X_r_vl), -1)

        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        r2_base = compute_r2(y_b_vl, ridge_base.predict(Xf_b_vl))

        ridge_regime = Ridge(alpha=1.0)
        ridge_regime.fit(Xf_r_tr, y_r_tr)
        r2_regime = compute_r2(y_r_vl, ridge_regime.predict(Xf_r_vl))

        # Regime distribution
        regimes = np.array([classify_glucose_regime(v) for v in glucose_mgdl])
        regime_names = ['hypo', 'low_normal', 'normal', 'elevated', 'high']
        dist = {regime_names[i]: round(float(np.mean(regimes == i)), 3) for i in range(5)}

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_regime': round(r2_regime, 4),
            'gain': round(r2_regime - r2_base, 4),
            'regime_distribution': dist,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} regime={r2_regime:.4f} "
                  f"({r2_regime - r2_base:+.4f}) dist={dist}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_regime': round(np.mean([r['r2_regime'] for r in results]), 4),
        'mean_gain': round(np.mean([r['gain'] for r in results]), 4),
        'n_positive': sum(1 for r in results if r['gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_base"]:.4f} '
                   f'regime={summary["mean_r2_regime"]:.4f} '
                   f'(+{summary["mean_gain"]:.4f}, '
                   f'{summary["n_positive"]}/{len(results)} positive)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1089: Feature Importance Analysis ───

def exp_1089_feature_importance(patients, detail=False):
    """Permutation importance on all feature groups for Ridge and GB.

    Permute each feature group and measure R² drop:
    - glucose_raw, physics_supply, physics_demand, physics_hepatic,
      physics_net (4 standard physics channels)
    This tells us which physics channels matter and which are redundant.
    """
    results = []
    n_permutations = 5

    group_names = ['glucose', 'supply', 'demand', 'hepatic', 'net']

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        # Define feature groups by column indices in flattened X
        # X shape: (n, WINDOW, 5) -> flattened: (n, WINDOW*5)
        # Channel 0: glucose, 1: supply, 2: demand, 3: hepatic, 4: net
        n_channels = X.shape[2]
        groups = {}
        for ch_idx, name in enumerate(group_names[:n_channels]):
            cols = [t * n_channels + ch_idx for t in range(WINDOW)]
            groups[name] = cols

        # Train Ridge baseline
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_base = ridge.predict(Xf_vl)
        r2_base_ridge = compute_r2(y_vl, pred_base)

        # Train GB baseline
        gb = GradientBoostingRegressor(n_estimators=100, max_depth=4,
                                       learning_rate=0.1, random_state=42,
                                       subsample=0.8)
        gb.fit(Xf_tr, y_tr)
        r2_base_gb = compute_r2(y_vl, gb.predict(Xf_vl))

        # Permutation importance per group
        importance_ridge = {}
        importance_gb = {}
        rng = np.random.RandomState(42)

        for gname, cols in groups.items():
            drops_ridge = []
            drops_gb = []
            for _ in range(n_permutations):
                X_perm = Xf_vl.copy()
                perm_idx = rng.permutation(len(X_perm))
                for col in cols:
                    X_perm[:, col] = X_perm[perm_idx, col]

                r2_perm_ridge = compute_r2(y_vl, ridge.predict(X_perm))
                r2_perm_gb = compute_r2(y_vl, gb.predict(X_perm))
                drops_ridge.append(r2_base_ridge - r2_perm_ridge)
                drops_gb.append(r2_base_gb - r2_perm_gb)

            importance_ridge[gname] = {
                'mean_drop': round(float(np.mean(drops_ridge)), 4),
                'std_drop': round(float(np.std(drops_ridge)), 4),
            }
            importance_gb[gname] = {
                'mean_drop': round(float(np.mean(drops_gb)), 4),
                'std_drop': round(float(np.std(drops_gb)), 4),
            }

        # Rank by importance
        ridge_ranked = sorted(importance_ridge.items(),
                              key=lambda x: x[1]['mean_drop'], reverse=True)
        gb_ranked = sorted(importance_gb.items(),
                           key=lambda x: x[1]['mean_drop'], reverse=True)

        res = {
            'patient': p['name'],
            'r2_base_ridge': round(r2_base_ridge, 4),
            'r2_base_gb': round(r2_base_gb, 4),
            'importance_ridge': importance_ridge,
            'importance_gb': importance_gb,
            'ridge_rank': [name for name, _ in ridge_ranked],
            'gb_rank': [name for name, _ in gb_ranked],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge_r2={r2_base_ridge:.4f} gb_r2={r2_base_gb:.4f}")
            print(f"      Ridge importance: {', '.join(f'{n}={v['mean_drop']:.4f}' for n, v in ridge_ranked)}")
            print(f"      GB importance:    {', '.join(f'{n}={v['mean_drop']:.4f}' for n, v in gb_ranked)}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate importance across patients
    agg_ridge = {g: [] for g in group_names}
    agg_gb = {g: [] for g in group_names}
    for r in results:
        for g in group_names:
            if g in r['importance_ridge']:
                agg_ridge[g].append(r['importance_ridge'][g]['mean_drop'])
            if g in r['importance_gb']:
                agg_gb[g].append(r['importance_gb'][g]['mean_drop'])

    agg_ridge_mean = {g: round(float(np.mean(v)), 4) if v else 0.0
                      for g, v in agg_ridge.items()}
    agg_gb_mean = {g: round(float(np.mean(v)), 4) if v else 0.0
                   for g, v in agg_gb.items()}

    ridge_top = sorted(agg_ridge_mean.items(), key=lambda x: x[1], reverse=True)
    gb_top = sorted(agg_gb_mean.items(), key=lambda x: x[1], reverse=True)

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_base_ridge'] for r in results]), 4),
        'mean_r2_gb': round(np.mean([r['r2_base_gb'] for r in results]), 4),
        'aggregate_importance_ridge': agg_ridge_mean,
        'aggregate_importance_gb': agg_gb_mean,
        'ridge_rank': [n for n, _ in ridge_top],
        'gb_rank': [n for n, _ in gb_top],
        'n_patients': len(results),
    }

    top_ridge = ridge_top[0] if ridge_top else ('?', 0)
    top_gb = gb_top[0] if gb_top else ('?', 0)

    return {
        'status': 'pass',
        'detail': (f'ridge top={top_ridge[0]}({top_ridge[1]:.4f}) '
                   f'gb top={top_gb[0]}({top_gb[1]:.4f}) '
                   f'ridge_rank={[n for n, _ in ridge_top]} '
                   f'gb_rank={[n for n, _ in gb_top]}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1090: Best-of-Breed Feature Set ───

def exp_1090_best_of_breed(patients, detail=False):
    """Combine best features from EXP-1081–1088 into one comprehensive set.

    Build the grand feature set including:
    - Base: glucose window + 4 physics channels
    - Meal timing (EXP-1081)
    - Bolus timing (EXP-1082)
    - Glucose momentum + excursion (EXP-1083)
    - Physics interactions (EXP-1084)
    - Window statistics (EXP-1085)
    - Regime features (EXP-1088)
    Train Ridge, GB, and CNN; compare to baseline.
    """
    results = []

    for p in patients:
        pk = p['pk']
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics), len(pk))
        glucose = glucose[:n]
        physics = physics[:n]

        g_scaled = np.nan_to_num(glucose / GLUCOSE_SCALE, nan=0.4)

        # Compute all feature sets
        meal_feats = compute_meal_timing_features(pk, n)
        bolus_feats = compute_bolus_timing_features(pk, n)
        momentum = compute_glucose_momentum(np.nan_to_num(g_scaled, nan=0.4), WINDOW)
        excursion = compute_excursion_features(np.nan_to_num(g_scaled, nan=0.4), WINDOW)
        regime_feats = compute_regime_features(np.nan_to_num(glucose, nan=120.0), WINDOW)

        # Physics interactions (inline)
        supply = physics[:, 0]
        demand = physics[:, 1]
        net_flux = physics[:, 3]
        sd_ratio = supply / (demand + 1e-8)
        net_mom = np.zeros(n)
        net_mom[1:] = net_flux[1:] - net_flux[:-1]
        total_iob = pk[:n, 0] if pk.shape[1] > 0 else np.zeros(n)
        carb_cob = pk[:n, 6] if pk.shape[1] > 6 else np.zeros(n)
        iob_cob = total_iob * carb_cob
        supply_g = supply * g_scaled
        demand_g = demand * g_scaled

        for arr in [sd_ratio, net_mom, iob_cob, supply_g, demand_g]:
            mx = np.max(np.abs(arr)) + 1e-8
            arr /= mx

        interactions = np.column_stack([sd_ratio, net_mom, iob_cob,
                                        supply_g, demand_g])

        # Assemble grand feature array per time step
        all_extra = np.column_stack([
            meal_feats,       # 4 features
            bolus_feats,      # 4 features
            momentum,         # 5 features
            excursion,        # 2 features
            interactions,     # 5 features
            regime_feats,     # 4 features
        ])  # Total: 24 extra features

        # Build windows: base and grand
        X_base_list, X_grand_list, y_list = [], [], []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_scaled[i:i+WINDOW]
            if np.sum(np.isnan(glucose[i:i+WINDOW])) > WINDOW * 0.3:
                continue
            g_win_clean = np.nan_to_num(g_win, nan=0.4)
            y_val = g_scaled[i + WINDOW + HORIZON - 1]
            if np.isnan(glucose[i + WINDOW + HORIZON - 1]):
                continue

            p_win = physics[i:i+WINDOW]
            p_win = np.nan_to_num(p_win, nan=0.0)
            e_win = all_extra[i:i+WINDOW]
            e_win = np.nan_to_num(e_win, nan=0.0)

            base_flat = np.concatenate([g_win_clean, p_win.ravel()])
            # Window statistics
            stats = compute_window_statistics(g_win_clean)
            # Grand: base + extra channels (flattened) + statistics
            grand_flat = np.concatenate([base_flat, e_win.ravel(), stats])

            X_base_list.append(base_flat)
            X_grand_list.append(grand_flat)
            y_list.append(y_val)

        if len(y_list) < 200:
            continue

        X_base = np.array(X_base_list)
        X_grand = np.array(X_grand_list)
        y = np.array(y_list)
        split = int(len(y) * 0.8)

        X_b_tr, X_b_vl = X_base[:split], X_base[split:]
        X_g_tr, X_g_vl = X_grand[:split], X_grand[split:]
        y_tr, y_vl = y[:split], y[split:]

        # Ridge baseline
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_b_tr, y_tr)
        r2_ridge_base = compute_r2(y_vl, ridge_base.predict(X_b_vl))

        # Ridge grand
        ridge_grand = Ridge(alpha=1.0)
        ridge_grand.fit(X_g_tr, y_tr)
        pred_ridge_grand = ridge_grand.predict(X_g_vl)
        r2_ridge_grand = compute_r2(y_vl, pred_ridge_grand)

        # GB grand
        gb = GradientBoostingRegressor(n_estimators=100, max_depth=4,
                                       learning_rate=0.1, random_state=42,
                                       subsample=0.8)
        gb.fit(X_g_tr, y_tr)
        pred_gb = gb.predict(X_g_vl)
        r2_gb_grand = compute_r2(y_vl, pred_gb)

        # CNN on Ridge residuals (using windowed grand features)
        # Reshape for CNN: we need (N, time, channels) format
        n_base_channels = 1 + physics.shape[1]  # glucose + physics
        n_extra_channels = all_extra.shape[1]
        n_total_channels = n_base_channels + n_extra_channels
        # Build proper windowed arrays for CNN
        X_cnn_list = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_scaled[i:i+WINDOW]
            if np.sum(np.isnan(glucose[i:i+WINDOW])) > WINDOW * 0.3:
                continue
            g_win_clean = np.nan_to_num(g_win, nan=0.4)
            y_val = g_scaled[i + WINDOW + HORIZON - 1]
            if np.isnan(glucose[i + WINDOW + HORIZON - 1]):
                continue
            p_win = np.nan_to_num(physics[i:i+WINDOW], nan=0.0)
            e_win = np.nan_to_num(all_extra[i:i+WINDOW], nan=0.0)
            combined = np.column_stack([g_win_clean.reshape(-1, 1), p_win, e_win])
            X_cnn_list.append(combined)

        if len(X_cnn_list) != len(y_list):
            # Fallback: skip CNN for this patient
            r2_cnn_grand = r2_ridge_grand
        else:
            X_cnn = np.array(X_cnn_list)
            X_cnn_tr = X_cnn[:split]
            X_cnn_vl = X_cnn[split:]

            # Residual correction: CNN learns to correct Ridge errors
            pred_ridge_grand_tr = ridge_grand.predict(X_g_tr)
            resid_tr = y_tr - pred_ridge_grand_tr

            torch.manual_seed(42)
            cnn = ResidualCNN(in_channels=n_total_channels).to(DEVICE)
            cnn_pred = train_cnn(cnn, X_cnn_tr, resid_tr, X_cnn_vl,
                                 y_vl - pred_ridge_grand, epochs=50)
            r2_cnn_grand = compute_r2(y_vl, pred_ridge_grand + 0.5 * cnn_pred)

        res = {
            'patient': p['name'],
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_grand': round(r2_ridge_grand, 4),
            'r2_gb_grand': round(r2_gb_grand, 4),
            'r2_cnn_grand': round(r2_cnn_grand, 4),
            'ridge_gain': round(r2_ridge_grand - r2_ridge_base, 4),
            'best_method': ('cnn' if r2_cnn_grand >= r2_gb_grand and r2_cnn_grand >= r2_ridge_grand
                            else 'gb' if r2_gb_grand >= r2_ridge_grand
                            else 'ridge'),
            'best_r2': round(max(r2_ridge_grand, r2_gb_grand, r2_cnn_grand), 4),
            'n_base_features': X_base.shape[1],
            'n_grand_features': X_grand.shape[1],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_ridge_base:.4f} "
                  f"ridge_grand={r2_ridge_grand:.4f} gb={r2_gb_grand:.4f} "
                  f"cnn={r2_cnn_grand:.4f} best={res['best_method']}={res['best_r2']:.4f} "
                  f"(+{r2_ridge_grand - r2_ridge_base:+.4f} ridge gain)")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge_base': round(np.mean([r['r2_ridge_base'] for r in results]), 4),
        'mean_r2_ridge_grand': round(np.mean([r['r2_ridge_grand'] for r in results]), 4),
        'mean_r2_gb_grand': round(np.mean([r['r2_gb_grand'] for r in results]), 4),
        'mean_r2_cnn_grand': round(np.mean([r['r2_cnn_grand'] for r in results]), 4),
        'mean_ridge_gain': round(np.mean([r['ridge_gain'] for r in results]), 4),
        'mean_best_r2': round(np.mean([r['best_r2'] for r in results]), 4),
        'best_method_counts': {
            m: sum(1 for r in results if r['best_method'] == m)
            for m in ['ridge', 'gb', 'cnn']
        },
        'n_grand_better': sum(1 for r in results if r['ridge_gain'] > 0),
        'n_patients': len(results),
    }

    return {
        'status': 'pass',
        'detail': (f'base={summary["mean_r2_ridge_base"]:.4f} '
                   f'ridge_grand={summary["mean_r2_ridge_grand"]:.4f} '
                   f'gb_grand={summary["mean_r2_gb_grand"]:.4f} '
                   f'cnn_grand={summary["mean_r2_cnn_grand"]:.4f} '
                   f'best_avg={summary["mean_best_r2"]:.4f} '
                   f'(+{summary["mean_ridge_gain"]:.4f} ridge gain, '
                   f'{summary["n_grand_better"]}/{len(results)}) '
                   f'methods={summary["best_method_counts"]}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── Experiment Registry ───

EXPERIMENTS = [
    ('EXP-1081', 'Meal Timing Features', exp_1081_meal_timing),
    ('EXP-1082', 'Bolus Timing Features', exp_1082_bolus_timing),
    ('EXP-1083', 'Glucose Momentum Features', exp_1083_glucose_momentum),
    ('EXP-1084', 'Physics Interaction Terms', exp_1084_physics_interactions),
    ('EXP-1085', 'Window Statistics Features', exp_1085_window_statistics),
    ('EXP-1086', 'Lagged Cross-Correlation', exp_1086_lagged_crosscorr),
    ('EXP-1087', 'Piecewise Linear Approximation', exp_1087_piecewise_linear),
    ('EXP-1088', 'Glucose Regime Detection', exp_1088_glucose_regime),
    ('EXP-1089', 'Feature Importance Analysis', exp_1089_feature_importance),
    ('EXP-1090', 'Best-of-Breed Feature Set', exp_1090_best_of_breed),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1081-1090: Feature Engineering and Information Extraction')
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
