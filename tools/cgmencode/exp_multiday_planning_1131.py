#!/usr/bin/env python3
"""
EXP-1131 through EXP-1138: Multi-Day Advance Planning Research

Can we predict glucose control quality 1-7 days ahead and schedule
overrides/recommendations before bad days happen?

Current capabilities this builds on:
  - Meal predictor (AUC=0.846 proactive, 17min lead)
  - Settings advisor (point-in-time basal/CR/ISF recommendations)
  - Changepoint detector (EXP-696, rolling RMSD)
  - Supply/demand decomposition (EXP-441)

Experiment registry:
    EXP-1131: Multi-Day Baseline
              Predict next-day quality (good/bad), TIR, hypo risk from
              7-day lookback of daily metrics. GBT + temporal block CV.
    EXP-1132: Weekly Pattern Features
              Day-of-week profiles, weekday vs weekend effects, DOW
              feature importance and incremental AUC.
    EXP-1133: Settings Drift as Planning Signal
              Rolling RMSD changepoint detection; test whether days
              after changepoints are predictably bad.
    EXP-1134: Multi-Day Override Scheduler
              Predict tomorrow's meal windows from past week; compute
              schedule reliability for pre-planned eating-soon overrides.
    EXP-1135: Overnight Risk Prediction
              Predict P(nocturnal hypo) from daytime features collected
              by 6 PM; actionable alert before bedtime.
    EXP-1136: Combined Multi-Day Model
              Union all features from 1131-1135; predict "attention
              needed in next 3 days" with ablation analysis.
    EXP-1137: Planning Horizon Decay
              AUC vs forecast horizon (1d-7d) to find maximum useful
              planning window.
    EXP-1138: Honest Evaluation with Bootstrap CI
              5-fold temporal block CV, bootstrap 1000 iterations,
              comparison to naive baselines.

Usage:
    python tools/cgmencode/exp_multiday_planning_1131.py --exp 1131
    python tools/cgmencode/exp_multiday_planning_1131.py --exp 1131 1132 1133
    python tools/cgmencode/exp_multiday_planning_1131.py --exp 1131 1132 1133 1134 1135 1136 1137 1138
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from tools.cgmencode.exp_metabolic_flux import load_patients
from tools.cgmencode.exp_metabolic_441 import compute_supply_demand

try:
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.metrics import (
        roc_auc_score, r2_score, mean_absolute_error,
        precision_recall_curve, confusion_matrix,
    )
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from scipy.stats import ttest_ind
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS_PER_DAY = 288          # 5-min intervals
STEPS_PER_HOUR = 12
MIN_DAYS = 28                # skip patients with fewer days
LOOKBACK_DAYS = 7
GLUCOSE_SCALE = 400.0
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients')

# Clinical thresholds
TIR_LOW = 70
TIR_HIGH = 180
HYPO_THRESHOLD = 70
SEVERE_HIGH = 250
BAD_TIR = 0.60
BAD_HYPO_EVENTS = 2
BAD_TBR = 0.04

# GBT defaults
GBT_PARAMS = dict(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    min_samples_leaf=10,
    random_state=42,
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_data():
    """Load patients and compute supply/demand for each."""
    print("[DATA] Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"[DATA] Loaded {len(patients)} patients")

    enriched = []
    for p in patients:
        df = p['df']
        n_steps = len(df)
        n_days = n_steps // STEPS_PER_DAY
        if n_days < MIN_DAYS:
            print(f"  Skip {p['name']}: only {n_days} days (need {MIN_DAYS})")
            continue

        print(f"  Processing {p['name']}: {n_days} days ({n_steps} steps)...")
        sd = compute_supply_demand(df, pk_array=p['pk'])

        glucose = df['glucose'].values.astype(float) if 'glucose' in df.columns else np.full(n_steps, np.nan)
        glucose = np.nan_to_num(glucose, nan=0.0, posinf=0.0, neginf=0.0)
        net_flux = np.nan_to_num(sd['net'], nan=0.0, posinf=0.0, neginf=0.0)
        supply = np.nan_to_num(sd['supply'], nan=0.0, posinf=0.0, neginf=0.0)
        demand = np.nan_to_num(sd['demand'], nan=0.0, posinf=0.0, neginf=0.0)

        enriched.append({
            'name': p['name'],
            'df': df,
            'pk': p['pk'],
            'glucose': glucose,
            'net_flux': net_flux,
            'supply': supply,
            'demand': demand,
            'n_days': n_days,
            'n_steps': n_steps,
        })
    print(f"[DATA] {len(enriched)} patients with >= {MIN_DAYS} days")
    return enriched


# ---------------------------------------------------------------------------
# Daily metrics computation
# ---------------------------------------------------------------------------

def compute_daily_metrics(glucose, net_flux, supply, demand, day_index):
    """Compute summary metrics for a single day (288 steps).

    Returns dict with 16 features or None if insufficient data.
    """
    start = day_index * STEPS_PER_DAY
    end = min(start + STEPS_PER_DAY, len(glucose))
    if end - start < STEPS_PER_DAY // 2:
        return None

    g = glucose[start:end].copy()
    nf = net_flux[start:end].copy()
    sup = supply[start:end].copy()
    dem = demand[start:end].copy()

    g = np.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0)
    nf = np.nan_to_num(nf, nan=0.0, posinf=0.0, neginf=0.0)
    sup = np.nan_to_num(sup, nan=0.0, posinf=0.0, neginf=0.0)
    dem = np.nan_to_num(dem, nan=0.0, posinf=0.0, neginf=0.0)

    valid_mask = g > 10  # exclude zeroed-out readings
    valid = g[valid_mask]
    if len(valid) < 144:  # need at least 50% data
        return None

    tir = float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH)))
    tar = float(np.mean(valid > TIR_HIGH))
    tbr = float(np.mean(valid < TIR_LOW))

    # Count hypo episodes (consecutive < 70)
    below = g < TIR_LOW
    hypo_events = 0
    in_hypo = False
    hypo_min = 0
    for v in below:
        if v and not in_hypo:
            hypo_events += 1
            in_hypo = True
            hypo_min += 5
        elif v:
            hypo_min += 5
        else:
            in_hypo = False

    # High events (> 250)
    high_transitions = np.diff((valid > SEVERE_HIGH).astype(int))
    high_events = int(np.sum(high_transitions == 1))

    # Overnight (steps 0-72 = 00:00-06:00)
    overnight = g[:72]
    on_mask = overnight > 10
    on_valid = overnight[on_mask]
    overnight_mean = float(np.mean(on_valid)) if len(on_valid) > 10 else 120.0
    overnight_min = float(np.min(on_valid)) if len(on_valid) > 10 else 70.0

    # Daytime variability (06:00-22:00 = steps 72-264)
    daytime = g[72:264]
    dt_mask = daytime > 10
    dt_valid = daytime[dt_mask]
    if len(dt_valid) > 10:
        daytime_variability = float(np.std(dt_valid))
    else:
        daytime_variability = 0.0

    # Meal detection from flux bursts
    meal_count = 0
    in_burst = False
    integral = 0.0
    for i in range(len(nf)):
        if nf[i] > 0.15 and not in_burst:
            in_burst = True
            integral = nf[i]
        elif nf[i] > 0.15 and in_burst:
            integral += nf[i]
        elif in_burst:
            in_burst = False
            if integral > 1.0:
                meal_count += 1

    mean_valid = float(np.mean(valid))
    return {
        'tir': tir,
        'tar': tar,
        'tbr': tbr,
        'mean_glucose': mean_valid,
        'glucose_cv': float(np.std(valid) / mean_valid) if mean_valid > 0 else 0.0,
        'hypo_events': hypo_events,
        'hypo_minutes': hypo_min,
        'high_events': high_events,
        'mean_flux': float(np.mean(nf)),
        'flux_variability': float(np.std(nf)),
        'meal_count': meal_count,
        'overnight_mean': overnight_mean,
        'overnight_min': overnight_min,
        'daytime_variability': daytime_variability,
        'supply_integral': float(np.sum(sup)),
        'demand_integral': float(np.sum(dem)),
    }


def compute_all_daily_metrics(patient):
    """Compute daily metrics for every day in a patient's data."""
    metrics = []
    for d in range(patient['n_days']):
        m = compute_daily_metrics(
            patient['glucose'], patient['net_flux'],
            patient['supply'], patient['demand'], d
        )
        metrics.append(m)
    return metrics


# ---------------------------------------------------------------------------
# Day quality labeling
# ---------------------------------------------------------------------------

def label_day_quality(metrics):
    """Label a day as good (0) or bad (1) based on clinical thresholds.

    Bad day: TIR < 0.60 OR hypo_events >= 2 OR tbr > 0.04
    """
    if metrics is None:
        return None
    if (metrics['tir'] < BAD_TIR or
            metrics['hypo_events'] >= BAD_HYPO_EVENTS or
            metrics['tbr'] > BAD_TBR):
        return 1  # bad day
    return 0  # good day


# ---------------------------------------------------------------------------
# Multi-day feature builder
# ---------------------------------------------------------------------------

DAILY_METRIC_KEYS = [
    'tir', 'tar', 'tbr', 'mean_glucose', 'glucose_cv',
    'hypo_events', 'hypo_minutes', 'high_events',
    'mean_flux', 'flux_variability', 'meal_count',
    'overnight_mean', 'overnight_min', 'daytime_variability',
    'supply_integral', 'demand_integral',
]

FEATURE_NAMES_BASE = []
for _key in ['tir', 'glucose_cv', 'hypo_events', 'meal_count', 'mean_flux']:
    FEATURE_NAMES_BASE.extend([f'{_key}_mean', f'{_key}_std', f'{_key}_trend'])


def _safe_trend(values):
    """Compute linear trend (slope) over a 1-D array."""
    vals = np.nan_to_num(np.array(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    if len(vals) < 2:
        return 0.0
    x = np.arange(len(vals), dtype=float)
    x_mean = np.mean(x)
    y_mean = np.mean(vals)
    denom = np.sum((x - x_mean) ** 2)
    if denom < 1e-12:
        return 0.0
    return float(np.sum((x - x_mean) * (vals - y_mean)) / denom)


def build_multiday_features(daily_metrics_list, day_index, lookback_days=LOOKBACK_DAYS):
    """Build features for predicting day d+horizon from days d-lookback...d.

    Features:
      - mean/std/trend of: tir, glucose_cv, hypo_events, meal_count, mean_flux  (15)
      - day-of-week sin/cos (2)
      - recent bad day count: last 3 days, last 7 days (2)
      - overnight trend: slope of overnight_mean over lookback (1)
      - supply trend: slope of supply_integral over lookback (1)
      - yesterday's raw metrics (16)
      Total: 37 features
    """
    if day_index < lookback_days:
        return None

    window = daily_metrics_list[day_index - lookback_days:day_index]
    valid = [m for m in window if m is not None]
    if len(valid) < lookback_days // 2:
        return None

    features = []
    # mean/std/trend for key metrics
    for key in ['tir', 'glucose_cv', 'hypo_events', 'meal_count', 'mean_flux']:
        vals = [m[key] for m in valid]
        features.append(np.mean(vals))
        features.append(np.std(vals))
        features.append(_safe_trend(vals))

    # DOW encoding
    dow = day_index % 7
    features.append(np.sin(2 * np.pi * dow / 7))
    features.append(np.cos(2 * np.pi * dow / 7))

    # Recent bad day counts
    labels_3 = [label_day_quality(m) for m in daily_metrics_list[max(0, day_index - 3):day_index]]
    labels_7 = [label_day_quality(m) for m in daily_metrics_list[max(0, day_index - 7):day_index]]
    features.append(sum(1 for lb in labels_3 if lb == 1))
    features.append(sum(1 for lb in labels_7 if lb == 1))

    # Overnight trend
    on_vals = [m['overnight_mean'] for m in valid]
    features.append(_safe_trend(on_vals))

    # Supply trend
    sup_vals = [m['supply_integral'] for m in valid]
    features.append(_safe_trend(sup_vals))

    # Yesterday's raw metrics
    yesterday = daily_metrics_list[day_index - 1]
    if yesterday is None:
        features.extend([0.0] * len(DAILY_METRIC_KEYS))
    else:
        for key in DAILY_METRIC_KEYS:
            features.append(float(yesterday[key]))

    arr = np.array(features, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return arr


def get_multiday_feature_names():
    """Return list of feature names matching build_multiday_features output."""
    names = list(FEATURE_NAMES_BASE)
    names.extend(['dow_sin', 'dow_cos'])
    names.extend(['bad_days_3', 'bad_days_7'])
    names.extend(['overnight_trend', 'supply_trend'])
    for key in DAILY_METRIC_KEYS:
        names.append(f'yesterday_{key}')
    return names


# ---------------------------------------------------------------------------
# Temporal block CV helper
# ---------------------------------------------------------------------------

def temporal_block_split(n_days, train_frac=0.6, val_frac=0.2):
    """Split days into train/val/test by temporal blocks (60/20/20)."""
    train_end = int(n_days * train_frac)
    val_end = int(n_days * (train_frac + val_frac))
    return (0, train_end), (train_end, val_end), (val_end, n_days)


def temporal_kfold_splits(n_days, k=5):
    """Generate k non-overlapping temporal block folds.

    Each fold uses one block as test, everything before as train.
    Returns list of (train_range, test_range) tuples.
    """
    block_size = n_days // k
    if block_size < 5:
        return []
    folds = []
    for i in range(1, k):
        test_start = i * block_size
        test_end = min((i + 1) * block_size, n_days)
        train_start = 0
        train_end = test_start
        folds.append(((train_start, train_end), (test_start, test_end)))
    return folds


# ---------------------------------------------------------------------------
# GBT training helpers
# ---------------------------------------------------------------------------

def _fit_gbt_classifier(X_train, y_train, X_val, y_val):
    """Fit GBT classifier with nan_to_num safety."""
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
    y_train = np.nan_to_num(np.array(y_train, dtype=float), nan=0.0, posinf=0.0, neginf=0.0).astype(int)
    y_val = np.nan_to_num(np.array(y_val, dtype=float), nan=0.0, posinf=0.0, neginf=0.0).astype(int)

    if len(np.unique(y_train)) < 2:
        return None, {'auc': 0.5, 'n_train': len(y_train), 'n_val': len(y_val)}

    clf = GradientBoostingClassifier(**GBT_PARAMS)
    clf.fit(X_train, y_train)

    probs = clf.predict_proba(X_val)
    if probs.shape[1] < 2:
        return clf, {'auc': 0.5, 'n_train': len(y_train), 'n_val': len(y_val)}

    y_score = probs[:, 1]
    try:
        auc = roc_auc_score(y_val, y_score)
    except ValueError:
        auc = 0.5

    preds = clf.predict(X_val)
    cm = confusion_matrix(y_val, preds, labels=[0, 1])
    tn = int(cm[0, 0]) if cm.shape[0] > 0 else 0
    fp = int(cm[0, 1]) if cm.shape[1] > 1 else 0
    fn = int(cm[1, 0]) if cm.shape[0] > 1 else 0
    tp = int(cm[1, 1]) if cm.shape[0] > 1 and cm.shape[1] > 1 else 0
    sens = tp / max(tp + fn, 1)
    spec = tn / max(tn + fp, 1)

    return clf, {
        'auc': float(auc),
        'sensitivity': float(sens),
        'specificity': float(spec),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'n_train': len(y_train),
        'n_val': len(y_val),
        'pos_rate_train': float(np.mean(y_train)),
        'pos_rate_val': float(np.mean(y_val)),
    }


def _fit_gbt_regressor(X_train, y_train, X_val, y_val):
    """Fit GBT regressor with nan_to_num safety."""
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
    y_train = np.nan_to_num(np.array(y_train, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    y_val = np.nan_to_num(np.array(y_val, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)

    reg = GradientBoostingRegressor(**GBT_PARAMS)
    reg.fit(X_train, y_train)

    preds = reg.predict(X_val)
    r2 = r2_score(y_val, preds)
    mae = mean_absolute_error(y_val, preds)

    return reg, {
        'r2': float(r2),
        'mae': float(mae),
        'n_train': len(y_train),
        'n_val': len(y_val),
    }


def _feature_importance(model, feature_names):
    """Extract feature importance from fitted GBT model."""
    if model is None or not hasattr(model, 'feature_importances_'):
        return {}
    imp = model.feature_importances_
    names = feature_names[:len(imp)]
    ranked = sorted(zip(names, imp.tolist()), key=lambda x: -x[1])
    return {name: round(val, 4) for name, val in ranked[:20]}


def _sensitivity_at_ppv(y_true, y_score, target_ppv=0.50):
    """Find sensitivity at a given positive predictive value threshold."""
    y_true = np.array(y_true, dtype=int)
    y_score = np.nan_to_num(np.array(y_score, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    if len(np.unique(y_true)) < 2:
        return 0.0
    try:
        precision, recall, _ = precision_recall_curve(y_true, y_score)
        for p, r in zip(precision, recall):
            if p >= target_ppv:
                return float(r)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------

def _save_results(result, exp_id, label):
    """Save experiment results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"exp-{exp_id}_{label}.json"
    path = RESULTS_DIR / filename
    with open(str(path), 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  → Saved {path}")
    return str(path)


# ---------------------------------------------------------------------------
# DOW feature builder (EXP-1132)
# ---------------------------------------------------------------------------

def build_dow_features(daily_metrics_list, day_index, dow_profiles=None):
    """Build day-of-week features for day_index.

    Features:
      - dow_sin, dow_cos (2)
      - is_weekend (1)
      - historical DOW TIR (from profiles) (1)
      - historical DOW hypo_events (1)
      - historical DOW glucose_cv (1)
    Total: 6
    """
    dow = day_index % 7
    feats = [
        np.sin(2 * np.pi * dow / 7),
        np.cos(2 * np.pi * dow / 7),
        1.0 if dow in (5, 6) else 0.0,  # weekend flag
    ]
    if dow_profiles is not None and dow in dow_profiles:
        prof = dow_profiles[dow]
        feats.append(prof.get('tir', 0.7))
        feats.append(prof.get('hypo_events', 0.5))
        feats.append(prof.get('glucose_cv', 0.2))
    else:
        feats.extend([0.7, 0.5, 0.2])

    return np.nan_to_num(np.array(feats, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)


def compute_dow_profiles(daily_metrics_list, end_day):
    """Compute per-DOW average metrics from days 0..end_day (training data)."""
    profiles = {}
    for dow in range(7):
        tirs, hypos, cvs = [], [], []
        for d in range(end_day):
            if d % 7 == dow and daily_metrics_list[d] is not None:
                tirs.append(daily_metrics_list[d]['tir'])
                hypos.append(daily_metrics_list[d]['hypo_events'])
                cvs.append(daily_metrics_list[d]['glucose_cv'])
        if tirs:
            profiles[dow] = {
                'tir': float(np.mean(tirs)),
                'hypo_events': float(np.mean(hypos)),
                'glucose_cv': float(np.mean(cvs)),
                'n_samples': len(tirs),
            }
    return profiles


def get_dow_feature_names():
    return ['dow_sin', 'dow_cos', 'is_weekend', 'dow_hist_tir', 'dow_hist_hypo', 'dow_hist_cv']


# ---------------------------------------------------------------------------
# Changepoint / drift features (EXP-1133)
# ---------------------------------------------------------------------------

def detect_changepoints(glucose, window=STEPS_PER_DAY):
    """Detect changepoints via rolling RMSD difference.

    For each day boundary, compute RMSD of left window vs right window.
    A changepoint occurs where the difference exceeds median + 2*std.
    """
    n = len(glucose)
    glucose = np.nan_to_num(glucose, nan=0.0, posinf=0.0, neginf=0.0)
    rmsd_diffs = []
    positions = []

    for i in range(window, n - window, STEPS_PER_DAY):
        left = glucose[i - window:i]
        right = glucose[i:i + window]
        left_valid = left[left > 10]
        right_valid = right[right > 10]
        if len(left_valid) < window // 4 or len(right_valid) < window // 4:
            rmsd_diffs.append(0.0)
            positions.append(i)
            continue
        rmsd_left = np.sqrt(np.mean((left_valid - np.mean(left_valid)) ** 2))
        rmsd_right = np.sqrt(np.mean((right_valid - np.mean(right_valid)) ** 2))
        rmsd_diffs.append(abs(rmsd_right - rmsd_left))
        positions.append(i)

    if len(rmsd_diffs) < 3:
        return [], np.array([]), np.array([])

    rmsd_arr = np.array(rmsd_diffs)
    median_rmsd = np.median(rmsd_arr)
    std_rmsd = np.std(rmsd_arr)
    threshold = median_rmsd + 2.0 * std_rmsd

    cp_indices = []
    for idx, (pos, val) in enumerate(zip(positions, rmsd_arr)):
        if val > threshold:
            cp_indices.append(pos // STEPS_PER_DAY)

    return cp_indices, rmsd_arr, np.array(positions)


def build_drift_features(daily_metrics_list, day_index, changepoint_days, rmsd_values):
    """Build drift/changepoint features for a given day.

    Features:
      - days_since_last_changepoint (1)
      - changepoint_count_last_7d (1)
      - rolling_rmsd (1)
      - rmsd_trend_7d (1)
    Total: 4
    """
    # Days since last changepoint
    past_cps = [cp for cp in changepoint_days if cp < day_index]
    if past_cps:
        days_since = day_index - max(past_cps)
    else:
        days_since = day_index  # no changepoint seen yet

    # Count changepoints in last 7 days
    cp_count_7d = sum(1 for cp in past_cps if day_index - cp <= 7)

    # Rolling RMSD at this day
    if day_index < len(rmsd_values):
        rolling_rmsd = float(rmsd_values[day_index])
    else:
        rolling_rmsd = 0.0

    # RMSD trend over last 7 days
    start_idx = max(0, day_index - 7)
    end_idx = min(day_index, len(rmsd_values))
    if end_idx > start_idx:
        rmsd_window = rmsd_values[start_idx:end_idx]
        rmsd_trend = _safe_trend(rmsd_window)
    else:
        rmsd_trend = 0.0

    feats = np.array([float(days_since), float(cp_count_7d), rolling_rmsd, rmsd_trend], dtype=float)
    return np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)


def get_drift_feature_names():
    return ['days_since_cp', 'cp_count_7d', 'rolling_rmsd', 'rmsd_trend_7d']


# ---------------------------------------------------------------------------
# Meal schedule features (EXP-1134)
# ---------------------------------------------------------------------------

MEAL_WINDOWS = [
    ('breakfast', 72, 120),    # 06:00-10:00
    ('lunch', 132, 180),       # 11:00-15:00
    ('dinner', 204, 252),      # 17:00-21:00
    ('snack_am', 120, 144),    # 10:00-12:00
    ('snack_pm', 180, 216),    # 15:00-18:00
]


def detect_meal_times(net_flux, day_index):
    """Detect meal events in a given day from net flux bursts.

    Returns list of (step_within_day, integral) for detected meals.
    """
    start = day_index * STEPS_PER_DAY
    end = min(start + STEPS_PER_DAY, len(net_flux))
    nf = net_flux[start:end]
    nf = np.nan_to_num(nf, nan=0.0, posinf=0.0, neginf=0.0)

    meals = []
    in_burst = False
    burst_start = 0
    integral = 0.0
    for i in range(len(nf)):
        if nf[i] > 0.15 and not in_burst:
            in_burst = True
            burst_start = i
            integral = nf[i]
        elif nf[i] > 0.15 and in_burst:
            integral += nf[i]
        elif in_burst:
            in_burst = False
            if integral > 1.0:
                meals.append((burst_start, float(integral)))

    return meals


def build_meal_schedule_features(net_flux, daily_metrics_list, day_index, lookback=LOOKBACK_DAYS):
    """Build meal schedule features for predicting tomorrow's meal windows.

    Features:
      - per meal window (5 windows):
        - occupancy_rate: fraction of past days with a meal in this window (5)
        - mean_integral: average meal size in this window (5)
        - time_std: std of meal time within window (5)
      - overall:
        - meal_count_mean: mean meals per day (1)
        - meal_count_std: std of meals per day (1)
        - schedule_consistency: 1 - normalized entropy of meal timing (1)
    Total: 18
    """
    if day_index < lookback:
        return None

    window_occupancies = {name: [] for name, _, _ in MEAL_WINDOWS}
    window_integrals = {name: [] for name, _, _ in MEAL_WINDOWS}
    window_times = {name: [] for name, _, _ in MEAL_WINDOWS}
    meal_counts = []

    for d in range(day_index - lookback, day_index):
        meals = detect_meal_times(net_flux, d)
        meal_counts.append(len(meals))

        for name, wstart, wend in MEAL_WINDOWS:
            in_window = [m for m in meals if wstart <= m[0] < wend]
            window_occupancies[name].append(1.0 if in_window else 0.0)
            if in_window:
                window_integrals[name].append(sum(m[1] for m in in_window))
                window_times[name].append(np.mean([m[0] for m in in_window]))

    features = []
    for name, _, _ in MEAL_WINDOWS:
        occ = window_occupancies[name]
        features.append(float(np.mean(occ)) if occ else 0.0)
        ints = window_integrals[name]
        features.append(float(np.mean(ints)) if ints else 0.0)
        times = window_times[name]
        features.append(float(np.std(times)) if len(times) > 1 else 0.0)

    features.append(float(np.mean(meal_counts)) if meal_counts else 0.0)
    features.append(float(np.std(meal_counts)) if len(meal_counts) > 1 else 0.0)

    # Schedule consistency: how predictable is meal timing?
    all_times = []
    for d in range(day_index - lookback, day_index):
        meals = detect_meal_times(net_flux, d)
        for m in meals:
            all_times.append(m[0])
    if all_times:
        bins = np.histogram(all_times, bins=12, range=(0, STEPS_PER_DAY))[0]
        probs = bins / max(np.sum(bins), 1)
        probs = probs[probs > 0]
        if len(probs) > 0:
            entropy = -np.sum(probs * np.log(probs + 1e-12))
            max_entropy = np.log(12)
            consistency = 1.0 - entropy / max(max_entropy, 1e-12)
        else:
            consistency = 0.5
    else:
        consistency = 0.5
    features.append(float(consistency))

    arr = np.array(features, dtype=float)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def get_meal_schedule_feature_names():
    names = []
    for wname, _, _ in MEAL_WINDOWS:
        names.extend([f'{wname}_occupancy', f'{wname}_mean_integral', f'{wname}_time_std'])
    names.extend(['meal_count_mean', 'meal_count_std', 'schedule_consistency'])
    return names


# ---------------------------------------------------------------------------
# Overnight risk features (EXP-1135)
# ---------------------------------------------------------------------------

def build_overnight_risk_features(glucose, net_flux, supply, demand, day_index):
    """Build daytime features collected by 6 PM (step 216) to predict
    overnight hypo risk.

    Features from 06:00-18:00 (steps 72-216):
      - glucose: mean, min, cv, time_below_100 (4)
      - meals: count, last_meal_step, total_flux_integral (3)
      - flux: mean_daytime_flux, flux_trend (2)
      - insulin: supply_integral_daytime, demand_at_6pm_proxy (2)
    Total: 11
    """
    start = day_index * STEPS_PER_DAY
    end = min(start + STEPS_PER_DAY, len(glucose))
    if end - start < STEPS_PER_DAY:
        return None

    g = glucose[start:end]
    nf = net_flux[start:end]
    sup = supply[start:end]
    dem = demand[start:end]

    g = np.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0)
    nf = np.nan_to_num(nf, nan=0.0, posinf=0.0, neginf=0.0)
    sup = np.nan_to_num(sup, nan=0.0, posinf=0.0, neginf=0.0)
    dem = np.nan_to_num(dem, nan=0.0, posinf=0.0, neginf=0.0)

    # Daytime window: steps 72-216 (06:00-18:00)
    dt_g = g[72:216]
    dt_nf = nf[72:216]
    dt_sup = sup[72:216]
    dt_dem = dem[72:216]

    valid_mask = dt_g > 10
    dt_valid = dt_g[valid_mask]
    if len(dt_valid) < 36:  # need at least 3 hours
        return None

    glucose_mean = float(np.mean(dt_valid))
    glucose_min = float(np.min(dt_valid))
    glucose_cv = float(np.std(dt_valid) / glucose_mean) if glucose_mean > 0 else 0.0
    time_below_100 = float(np.mean(dt_valid < 100))

    # Meals from flux
    meals = detect_meal_times(net_flux, day_index)
    daytime_meals = [m for m in meals if 72 <= m[0] < 216]
    meal_count = len(daytime_meals)
    last_meal_step = float(daytime_meals[-1][0]) if daytime_meals else 72.0
    total_flux_integral = float(sum(m[1] for m in daytime_meals)) if daytime_meals else 0.0

    # Flux features
    mean_daytime_flux = float(np.mean(dt_nf))
    flux_trend = _safe_trend(dt_nf)

    # Insulin features
    supply_integral_daytime = float(np.sum(dt_sup))
    # IOB proxy at 6PM: demand in last 2 hours (steps 192-216)
    demand_at_6pm = float(np.mean(dem[192:216])) if len(dem) > 216 else 0.0

    feats = np.array([
        glucose_mean, glucose_min, glucose_cv, time_below_100,
        float(meal_count), last_meal_step, total_flux_integral,
        mean_daytime_flux, flux_trend,
        supply_integral_daytime, demand_at_6pm,
    ], dtype=float)
    return np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)


def label_overnight_hypo(glucose, day_index):
    """Label 1 if any glucose < 70 between 22:00-06:00 (steps 264-360).

    Steps 264-288 of current day + steps 0-72 of next day.
    """
    start = day_index * STEPS_PER_DAY
    # Evening: steps 264-288 of current day
    evening_start = start + 264
    evening_end = start + STEPS_PER_DAY
    # Next morning: steps 0-72 of next day
    morning_start = start + STEPS_PER_DAY
    morning_end = morning_start + 72

    segments = []
    if evening_start < len(glucose):
        seg = glucose[evening_start:min(evening_end, len(glucose))]
        segments.append(seg)
    if morning_start < len(glucose):
        seg = glucose[morning_start:min(morning_end, len(glucose))]
        segments.append(seg)

    if not segments:
        return None
    combined = np.concatenate(segments)
    combined = np.nan_to_num(combined, nan=120.0, posinf=120.0, neginf=120.0)
    valid = combined[combined > 10]
    if len(valid) < 18:  # need at least 1.5 hours
        return None

    return 1 if np.any(valid < HYPO_THRESHOLD) else 0


def get_overnight_feature_names():
    return [
        'dt_glucose_mean', 'dt_glucose_min', 'dt_glucose_cv', 'dt_time_below_100',
        'dt_meal_count', 'dt_last_meal_step', 'dt_total_flux_integral',
        'dt_mean_flux', 'dt_flux_trend',
        'dt_supply_integral', 'dt_demand_at_6pm',
    ]


# ===========================================================================
# EXP-1131: Multi-Day Baseline
# ===========================================================================

def exp_1131_multiday_baseline():
    """Predict next-day quality, TIR, and hypo risk from 7-day lookback."""
    print("\n" + "=" * 70)
    print("[EXP-1131] Multi-Day Baseline: Next-Day Prediction")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()
    feature_names = get_multiday_feature_names()

    all_results = {
        'experiment': 'EXP-1131',
        'title': 'Multi-Day Baseline: Next-Day Quality, TIR, Hypo Risk',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_quality_auc = []
    agg_tir_r2 = []
    agg_hypo_auc = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1131] Processing {pname} ({p['n_days']} days)...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        print(f"  Valid days: {valid_count}/{p['n_days']}")

        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        # Build feature/label arrays
        X_all, y_quality, y_tir, y_hypo = [], [], [], []
        day_indices = []

        for d in range(LOOKBACK_DAYS, p['n_days'] - 1):
            feats = build_multiday_features(daily_metrics, d)
            if feats is None:
                continue
            target_metrics = daily_metrics[d + 1]  # next day
            if target_metrics is None:
                continue

            quality_label = label_day_quality(target_metrics)
            if quality_label is None:
                continue

            X_all.append(feats)
            y_quality.append(quality_label)
            y_tir.append(target_metrics['tir'])
            y_hypo.append(1 if target_metrics['hypo_events'] >= 1 else 0)
            day_indices.append(d)

        if len(X_all) < 20:
            print(f"  Skip {pname}: only {len(X_all)} samples")
            continue

        X_all = np.array(X_all, dtype=float)
        X_all = np.nan_to_num(X_all, nan=0.0, posinf=0.0, neginf=0.0)
        y_quality = np.array(y_quality, dtype=int)
        y_tir = np.array(y_tir, dtype=float)
        y_hypo = np.array(y_hypo, dtype=int)

        n = len(X_all)
        train_end = int(n * 0.6)
        val_end = int(n * 0.8)

        X_train, X_val, X_test = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]
        yq_tr, yq_val, yq_te = y_quality[:train_end], y_quality[train_end:val_end], y_quality[val_end:]
        yt_tr, yt_val, yt_te = y_tir[:train_end], y_tir[train_end:val_end], y_tir[val_end:]
        yh_tr, yh_val, yh_te = y_hypo[:train_end], y_hypo[train_end:val_end], y_hypo[val_end:]

        print(f"  Split: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")
        print(f"  Bad day rate: train={np.mean(yq_tr):.2f}, val={np.mean(yq_val):.2f}, test={np.mean(yq_te):.2f}")

        # 1) Quality prediction (binary)
        X_trainval = np.vstack([X_train, X_val])
        yq_trainval = np.concatenate([yq_tr, yq_val])
        clf_q, quality_metrics = _fit_gbt_classifier(X_trainval, yq_trainval, X_test, yq_te)
        quality_fi = _feature_importance(clf_q, feature_names)
        print(f"  Quality AUC: {quality_metrics['auc']:.3f}")

        # 2) TIR prediction (regression)
        yt_trainval = np.concatenate([yt_tr, yt_val])
        reg_t, tir_metrics = _fit_gbt_regressor(X_trainval, yt_trainval, X_test, yt_te)
        tir_fi = _feature_importance(reg_t, feature_names)
        print(f"  TIR R²: {tir_metrics['r2']:.3f}, MAE: {tir_metrics['mae']:.3f}")

        # 3) Hypo risk (binary)
        yh_trainval = np.concatenate([yh_tr, yh_val])
        clf_h, hypo_metrics = _fit_gbt_classifier(X_trainval, yh_trainval, X_test, yh_te)
        hypo_fi = _feature_importance(clf_h, feature_names)
        print(f"  Hypo AUC: {hypo_metrics['auc']:.3f}")

        patient_result = {
            'n_days': p['n_days'],
            'valid_days': valid_count,
            'n_samples': n,
            'bad_day_rate': float(np.mean(y_quality)),
            'quality_prediction': quality_metrics,
            'quality_feature_importance': quality_fi,
            'tir_prediction': tir_metrics,
            'tir_feature_importance': tir_fi,
            'hypo_prediction': hypo_metrics,
            'hypo_feature_importance': hypo_fi,
        }
        all_results['per_patient'][pname] = patient_result

        agg_quality_auc.append(quality_metrics['auc'])
        agg_tir_r2.append(tir_metrics['r2'])
        agg_hypo_auc.append(hypo_metrics['auc'])

    # Aggregate
    if agg_quality_auc:
        all_results['aggregate'] = {
            'n_patients': len(agg_quality_auc),
            'quality_auc': {
                'mean': float(np.mean(agg_quality_auc)),
                'std': float(np.std(agg_quality_auc)),
                'min': float(np.min(agg_quality_auc)),
                'max': float(np.max(agg_quality_auc)),
            },
            'tir_r2': {
                'mean': float(np.mean(agg_tir_r2)),
                'std': float(np.std(agg_tir_r2)),
                'min': float(np.min(agg_tir_r2)),
                'max': float(np.max(agg_tir_r2)),
            },
            'hypo_auc': {
                'mean': float(np.mean(agg_hypo_auc)),
                'std': float(np.std(agg_hypo_auc)),
                'min': float(np.min(agg_hypo_auc)),
                'max': float(np.max(agg_hypo_auc)),
            },
        }

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1131] Complete in {elapsed:.1f}s")
    if agg_quality_auc:
        print(f"  Aggregate Quality AUC: {np.mean(agg_quality_auc):.3f} ± {np.std(agg_quality_auc):.3f}")
        print(f"  Aggregate TIR R²: {np.mean(agg_tir_r2):.3f} ± {np.std(agg_tir_r2):.3f}")
        print(f"  Aggregate Hypo AUC: {np.mean(agg_hypo_auc):.3f} ± {np.std(agg_hypo_auc):.3f}")

    return all_results


# ===========================================================================
# EXP-1132: Weekly Pattern Features
# ===========================================================================

def exp_1132_weekly_patterns():
    """Test day-of-week features: DOW alone vs daily metrics vs combined."""
    print("\n" + "=" * 70)
    print("[EXP-1132] Weekly Pattern Features: Day-of-Week Effects")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()

    all_results = {
        'experiment': 'EXP-1132',
        'title': 'Weekly Pattern Features: DOW effects on glucose control',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_dow_only = []
    agg_daily_only = []
    agg_combined = []
    agg_weekend_effect = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1132] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        # Temporal split
        n_days = p['n_days']
        train_end = int(n_days * 0.6)
        val_end = int(n_days * 0.8)

        # Compute DOW profiles from training data
        dow_profiles = compute_dow_profiles(daily_metrics, train_end)

        # Build three feature sets
        X_dow, X_daily, X_combined, y_all = [], [], [], []
        day_map = []

        for d in range(LOOKBACK_DAYS, n_days - 1):
            target = daily_metrics[d + 1]
            if target is None:
                continue
            label = label_day_quality(target)
            if label is None:
                continue

            base_feats = build_multiday_features(daily_metrics, d)
            if base_feats is None:
                continue
            dow_feats = build_dow_features(daily_metrics, d, dow_profiles)

            X_dow.append(dow_feats)
            X_daily.append(base_feats)
            X_combined.append(np.concatenate([base_feats, dow_feats]))
            y_all.append(label)
            day_map.append(d)

        if len(X_dow) < 20:
            print(f"  Skip {pname}: only {len(X_dow)} samples")
            continue

        X_dow = np.nan_to_num(np.array(X_dow, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        X_daily = np.nan_to_num(np.array(X_daily, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        X_combined = np.nan_to_num(np.array(X_combined, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = np.array(y_all, dtype=int)

        n = len(y_all)
        tr_end = int(n * 0.6)
        va_end = int(n * 0.8)

        X_tr_val = slice(0, va_end)
        X_te = slice(va_end, n)

        # DOW only
        _, dow_res = _fit_gbt_classifier(X_dow[X_tr_val], y_all[X_tr_val], X_dow[X_te], y_all[X_te])
        # Daily only
        _, daily_res = _fit_gbt_classifier(X_daily[X_tr_val], y_all[X_tr_val], X_daily[X_te], y_all[X_te])
        # Combined
        clf_comb, comb_res = _fit_gbt_classifier(
            X_combined[X_tr_val], y_all[X_tr_val], X_combined[X_te], y_all[X_te]
        )

        combined_names = get_multiday_feature_names() + get_dow_feature_names()
        comb_fi = _feature_importance(clf_comb, combined_names)

        print(f"  DOW-only AUC: {dow_res['auc']:.3f}")
        print(f"  Daily-only AUC: {daily_res['auc']:.3f}")
        print(f"  Combined AUC: {comb_res['auc']:.3f}")

        # Weekday vs weekend t-test
        weekday_tir = [daily_metrics[d]['tir'] for d in range(n_days)
                       if daily_metrics[d] is not None and d % 7 < 5]
        weekend_tir = [daily_metrics[d]['tir'] for d in range(n_days)
                       if daily_metrics[d] is not None and d % 7 >= 5]

        weekend_test = {}
        if HAS_SCIPY and len(weekday_tir) > 5 and len(weekend_tir) > 5:
            stat, pval = ttest_ind(weekday_tir, weekend_tir)
            weekend_test = {
                'weekday_tir_mean': float(np.mean(weekday_tir)),
                'weekend_tir_mean': float(np.mean(weekend_tir)),
                'ttest_statistic': float(stat),
                'ttest_pvalue': float(pval),
                'significant': pval < 0.05,
                'n_weekdays': len(weekday_tir),
                'n_weekends': len(weekend_tir),
            }
            print(f"  Weekend effect: weekday TIR={np.mean(weekday_tir):.3f}, "
                  f"weekend TIR={np.mean(weekend_tir):.3f}, p={pval:.4f}")
        else:
            weekend_test = {
                'weekday_tir_mean': float(np.mean(weekday_tir)) if weekday_tir else 0.0,
                'weekend_tir_mean': float(np.mean(weekend_tir)) if weekend_tir else 0.0,
                'significant': False,
            }

        patient_result = {
            'n_samples': n,
            'dow_only_auc': dow_res['auc'],
            'daily_only_auc': daily_res['auc'],
            'combined_auc': comb_res['auc'],
            'auc_improvement_from_dow': comb_res['auc'] - daily_res['auc'],
            'feature_importance': comb_fi,
            'weekend_effect': weekend_test,
            'dow_profiles': {str(k): v for k, v in dow_profiles.items()},
        }
        all_results['per_patient'][pname] = patient_result

        agg_dow_only.append(dow_res['auc'])
        agg_daily_only.append(daily_res['auc'])
        agg_combined.append(comb_res['auc'])
        if 'significant' in weekend_test:
            agg_weekend_effect.append(1 if weekend_test['significant'] else 0)

    if agg_combined:
        all_results['aggregate'] = {
            'n_patients': len(agg_combined),
            'dow_only_auc': {'mean': float(np.mean(agg_dow_only)), 'std': float(np.std(agg_dow_only))},
            'daily_only_auc': {'mean': float(np.mean(agg_daily_only)), 'std': float(np.std(agg_daily_only))},
            'combined_auc': {'mean': float(np.mean(agg_combined)), 'std': float(np.std(agg_combined))},
            'mean_auc_improvement': float(np.mean(np.array(agg_combined) - np.array(agg_daily_only))),
            'patients_with_weekend_effect': int(sum(agg_weekend_effect)) if agg_weekend_effect else 0,
        }

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1132] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1133: Settings Drift as Planning Signal
# ===========================================================================

def exp_1133_settings_drift():
    """Test whether changepoint/drift features improve bad-day prediction."""
    print("\n" + "=" * 70)
    print("[EXP-1133] Settings Drift as Planning Signal")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()

    all_results = {
        'experiment': 'EXP-1133',
        'title': 'Settings Drift: Changepoint Detection as Planning Signal',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_without_drift = []
    agg_with_drift = []
    agg_cp_counts = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1133] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        # Detect changepoints
        cp_days, rmsd_values, rmsd_positions = detect_changepoints(p['glucose'])
        n_changepoints = len(cp_days)
        print(f"  Changepoints detected: {n_changepoints}")

        # Pad rmsd_values to n_days length
        rmsd_daily = np.zeros(p['n_days'])
        for i, pos in enumerate(rmsd_positions):
            day_idx = int(pos) // STEPS_PER_DAY
            if day_idx < p['n_days']:
                rmsd_daily[day_idx] = rmsd_values[i] if i < len(rmsd_values) else 0.0

        # Build features with and without drift
        X_base, X_with_drift, y_all = [], [], []

        for d in range(LOOKBACK_DAYS, p['n_days'] - 1):
            base_feats = build_multiday_features(daily_metrics, d)
            if base_feats is None:
                continue
            target = daily_metrics[d + 1]
            if target is None:
                continue
            label = label_day_quality(target)
            if label is None:
                continue

            drift_feats = build_drift_features(daily_metrics, d, cp_days, rmsd_daily)

            X_base.append(base_feats)
            X_with_drift.append(np.concatenate([base_feats, drift_feats]))
            y_all.append(label)

        if len(X_base) < 20:
            print(f"  Skip {pname}: only {len(X_base)} samples")
            continue

        X_base = np.nan_to_num(np.array(X_base, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        X_drift = np.nan_to_num(np.array(X_with_drift, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = np.array(y_all, dtype=int)

        n = len(y_all)
        split = int(n * 0.8)

        # Without drift
        _, base_res = _fit_gbt_classifier(X_base[:split], y_all[:split], X_base[split:], y_all[split:])
        # With drift
        clf_d, drift_res = _fit_gbt_classifier(X_drift[:split], y_all[:split], X_drift[split:], y_all[split:])

        drift_names = get_multiday_feature_names() + get_drift_feature_names()
        drift_fi = _feature_importance(clf_d, drift_names)

        improvement = drift_res['auc'] - base_res['auc']
        print(f"  Without drift AUC: {base_res['auc']:.3f}")
        print(f"  With drift AUC: {drift_res['auc']:.3f} (Δ={improvement:+.3f})")

        # Analyze post-changepoint days
        post_cp_bad_rate = 0.0
        non_cp_bad_rate = 0.0
        if cp_days:
            post_cp_labels = []
            non_cp_labels = []
            for d in range(p['n_days']):
                label = label_day_quality(daily_metrics[d])
                if label is None:
                    continue
                is_post_cp = any(0 < d - cp <= 3 for cp in cp_days)
                if is_post_cp:
                    post_cp_labels.append(label)
                else:
                    non_cp_labels.append(label)
            if post_cp_labels:
                post_cp_bad_rate = float(np.mean(post_cp_labels))
            if non_cp_labels:
                non_cp_bad_rate = float(np.mean(non_cp_labels))
            print(f"  Post-CP bad rate: {post_cp_bad_rate:.3f} vs non-CP: {non_cp_bad_rate:.3f}")

        patient_result = {
            'n_changepoints': n_changepoints,
            'changepoint_days': [int(c) for c in cp_days[:20]],
            'without_drift_auc': base_res['auc'],
            'with_drift_auc': drift_res['auc'],
            'auc_improvement': improvement,
            'feature_importance': drift_fi,
            'post_cp_bad_rate': post_cp_bad_rate,
            'non_cp_bad_rate': non_cp_bad_rate,
        }
        all_results['per_patient'][pname] = patient_result

        agg_without_drift.append(base_res['auc'])
        agg_with_drift.append(drift_res['auc'])
        agg_cp_counts.append(n_changepoints)

    if agg_with_drift:
        improvements = np.array(agg_with_drift) - np.array(agg_without_drift)
        all_results['aggregate'] = {
            'n_patients': len(agg_with_drift),
            'without_drift_auc': {'mean': float(np.mean(agg_without_drift)), 'std': float(np.std(agg_without_drift))},
            'with_drift_auc': {'mean': float(np.mean(agg_with_drift)), 'std': float(np.std(agg_with_drift))},
            'mean_improvement': float(np.mean(improvements)),
            'patients_improved': int(np.sum(improvements > 0)),
            'mean_changepoints': float(np.mean(agg_cp_counts)),
        }

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1133] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1134: Multi-Day Override Scheduler
# ===========================================================================

def exp_1134_override_scheduler():
    """Predict tomorrow's meal windows for pre-planned eating-soon overrides."""
    print("\n" + "=" * 70)
    print("[EXP-1134] Multi-Day Override Scheduler: Meal Window Prediction")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()

    all_results = {
        'experiment': 'EXP-1134',
        'title': 'Multi-Day Override Scheduler: Meal Pattern Prediction',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_window_accuracy = []
    agg_schedule_reliability = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1134] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        n_days = p['n_days']

        # Compute per-day meal stability across whole dataset
        all_meals_by_day = []
        for d in range(n_days):
            meals = detect_meal_times(p['net_flux'], d)
            all_meals_by_day.append(meals)

        # Per-window analysis: predict tomorrow's meal window occupancy
        window_results = {}
        for wname, wstart, wend in MEAL_WINDOWS:
            print(f"  Window '{wname}' ({wstart}-{wend})...")

            # Build dataset: features = past 7 days occupancy + meal_schedule_features
            X_w, y_w = [], []
            for d in range(LOOKBACK_DAYS, n_days - 1):
                # Features: occupancy in past 7 days for this window
                past_occ = []
                past_times = []
                for dd in range(d - LOOKBACK_DAYS, d):
                    meals_dd = all_meals_by_day[dd]
                    in_win = [m for m in meals_dd if wstart <= m[0] < wend]
                    past_occ.append(1.0 if in_win else 0.0)
                    if in_win:
                        past_times.append(np.mean([m[0] for m in in_win]))

                sched_feats = build_meal_schedule_features(p['net_flux'], daily_metrics, d)
                if sched_feats is None:
                    continue

                feats = np.concatenate([
                    np.array(past_occ, dtype=float),
                    np.array([
                        np.mean(past_occ),
                        np.std(past_times) if len(past_times) > 1 else 0.0,
                        float(d % 7),  # DOW
                    ], dtype=float),
                    sched_feats,
                ])
                feats = np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)

                # Label: does tomorrow have a meal in this window?
                tomorrow_meals = all_meals_by_day[d + 1]
                in_win_tomorrow = any(wstart <= m[0] < wend for m in tomorrow_meals)
                y_w.append(1 if in_win_tomorrow else 0)
                X_w.append(feats)

            if len(X_w) < 20:
                window_results[wname] = {'auc': 0.5, 'n_samples': len(X_w), 'skipped': True}
                continue

            X_w = np.nan_to_num(np.array(X_w, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
            y_w = np.array(y_w, dtype=int)

            n = len(y_w)
            split = int(n * 0.8)
            _, w_res = _fit_gbt_classifier(X_w[:split], y_w[:split], X_w[split:], y_w[split:])

            # Schedule reliability: when we predict a meal, how often does one
            # actually occur within ±30 min (±6 steps) of the window center?
            reliability = 0.0
            if split < n:
                clf_temp = GradientBoostingClassifier(**GBT_PARAMS)
                clf_temp.fit(
                    np.nan_to_num(X_w[:split], nan=0.0, posinf=0.0, neginf=0.0),
                    y_w[:split]
                )
                preds = clf_temp.predict(np.nan_to_num(X_w[split:], nan=0.0, posinf=0.0, neginf=0.0))
                predicted_positive = np.sum(preds == 1)
                if predicted_positive > 0:
                    window_center = (wstart + wend) // 2
                    correct_within_30 = 0
                    for i, pred in enumerate(preds):
                        if pred == 1:
                            test_day = split + LOOKBACK_DAYS + i
                            if test_day + 1 < n_days:
                                tomorrow_meals_check = all_meals_by_day[test_day + 1]
                                for m in tomorrow_meals_check:
                                    if abs(m[0] - window_center) <= 6:
                                        correct_within_30 += 1
                                        break
                    reliability = correct_within_30 / max(predicted_positive, 1)

            window_results[wname] = {
                'auc': w_res['auc'],
                'occupancy_rate': float(np.mean(y_w)),
                'reliability_30min': float(reliability),
                'n_samples': n,
            }
            print(f"    AUC: {w_res['auc']:.3f}, occupancy: {np.mean(y_w):.2f}, "
                  f"reliability: {reliability:.3f}")

        # Meal time consistency per window
        time_consistency = {}
        for wname, wstart, wend in MEAL_WINDOWS:
            meal_times_in_window = []
            for d in range(n_days):
                meals_d = all_meals_by_day[d]
                for m in meals_d:
                    if wstart <= m[0] < wend:
                        meal_times_in_window.append(m[0])
            if meal_times_in_window:
                time_consistency[wname] = {
                    'mean_time_step': float(np.mean(meal_times_in_window)),
                    'std_time_step': float(np.std(meal_times_in_window)),
                    'std_minutes': float(np.std(meal_times_in_window) * 5),
                    'n_occurrences': len(meal_times_in_window),
                }

        # Aggregate per-window accuracy
        valid_windows = [v for v in window_results.values() if not v.get('skipped')]
        mean_window_acc = float(np.mean([v['auc'] for v in valid_windows])) if valid_windows else 0.5
        mean_reliability = float(np.mean([v['reliability_30min'] for v in valid_windows])) if valid_windows else 0.0

        patient_result = {
            'n_days': n_days,
            'window_predictions': window_results,
            'time_consistency': time_consistency,
            'mean_window_auc': mean_window_acc,
            'mean_schedule_reliability': mean_reliability,
        }
        all_results['per_patient'][pname] = patient_result
        agg_window_accuracy.append(mean_window_acc)
        agg_schedule_reliability.append(mean_reliability)

    if agg_window_accuracy:
        all_results['aggregate'] = {
            'n_patients': len(agg_window_accuracy),
            'mean_window_auc': {'mean': float(np.mean(agg_window_accuracy)), 'std': float(np.std(agg_window_accuracy))},
            'mean_schedule_reliability': {'mean': float(np.mean(agg_schedule_reliability)), 'std': float(np.std(agg_schedule_reliability))},
            'clinical_note': 'Reliability > 0.7 suggests pre-planned eating-soon overrides are viable',
        }

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1134] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1135: Overnight Risk Prediction
# ===========================================================================

def exp_1135_overnight_risk():
    """Predict P(nocturnal hypo) from daytime features by 6 PM."""
    print("\n" + "=" * 70)
    print("[EXP-1135] Overnight Risk Prediction: Nocturnal Hypo from Daytime")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()
    feature_names = get_overnight_feature_names()

    all_results = {
        'experiment': 'EXP-1135',
        'title': 'Overnight Risk Prediction: Nocturnal Hypoglycemia',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_auc = []
    agg_sensitivity = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1135] Processing {pname}...")

        n_days = p['n_days']
        X_all, y_all = [], []

        for d in range(n_days - 1):  # need next day for overnight label
            feats = build_overnight_risk_features(
                p['glucose'], p['net_flux'], p['supply'], p['demand'], d
            )
            if feats is None:
                continue
            label = label_overnight_hypo(p['glucose'], d)
            if label is None:
                continue
            X_all.append(feats)
            y_all.append(label)

        if len(X_all) < 20:
            print(f"  Skip {pname}: only {len(X_all)} samples")
            continue

        X_all = np.nan_to_num(np.array(X_all, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = np.array(y_all, dtype=int)

        hypo_rate = float(np.mean(y_all))
        print(f"  Overnight hypo rate: {hypo_rate:.3f} ({np.sum(y_all)}/{len(y_all)})")

        n = len(y_all)
        split = int(n * 0.8)

        clf, metrics = _fit_gbt_classifier(X_all[:split], y_all[:split], X_all[split:], y_all[split:])
        fi = _feature_importance(clf, feature_names)

        # Sensitivity at PPV=0.50
        sens_at_ppv50 = 0.0
        if clf is not None and split < n:
            probs = clf.predict_proba(np.nan_to_num(X_all[split:], nan=0.0, posinf=0.0, neginf=0.0))
            if probs.shape[1] >= 2:
                sens_at_ppv50 = _sensitivity_at_ppv(y_all[split:], probs[:, 1], target_ppv=0.50)

        print(f"  AUC: {metrics['auc']:.3f}, Sens@PPV50: {sens_at_ppv50:.3f}")

        patient_result = {
            'n_days': n_days,
            'n_samples': n,
            'overnight_hypo_rate': hypo_rate,
            'prediction': metrics,
            'sensitivity_at_ppv50': sens_at_ppv50,
            'feature_importance': fi,
        }
        all_results['per_patient'][pname] = patient_result

        agg_auc.append(metrics['auc'])
        agg_sensitivity.append(sens_at_ppv50)

    if agg_auc:
        all_results['aggregate'] = {
            'n_patients': len(agg_auc),
            'auc': {'mean': float(np.mean(agg_auc)), 'std': float(np.std(agg_auc))},
            'sensitivity_at_ppv50': {'mean': float(np.mean(agg_sensitivity)), 'std': float(np.std(agg_sensitivity))},
        }
        print(f"\n  Aggregate AUC: {np.mean(agg_auc):.3f} ± {np.std(agg_auc):.3f}")

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1135] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1136: Combined Multi-Day Model
# ===========================================================================

def _build_all_features(patient, daily_metrics, day_index, dow_profiles,
                        cp_days, rmsd_daily):
    """Build union of all features from EXP-1131 through EXP-1135."""
    # Base multiday features (37)
    base = build_multiday_features(daily_metrics, day_index)
    if base is None:
        return None

    # DOW features (6)
    dow = build_dow_features(daily_metrics, day_index, dow_profiles)

    # Drift features (4)
    drift = build_drift_features(daily_metrics, day_index, cp_days, rmsd_daily)

    # Meal schedule features (18)
    meal = build_meal_schedule_features(patient['net_flux'], daily_metrics, day_index)
    if meal is None:
        meal = np.zeros(18, dtype=float)

    # Overnight risk features (11)
    overnight = build_overnight_risk_features(
        patient['glucose'], patient['net_flux'], patient['supply'], patient['demand'], day_index
    )
    if overnight is None:
        overnight = np.zeros(11, dtype=float)

    combined = np.concatenate([base, dow, drift, meal, overnight])
    return np.nan_to_num(combined, nan=0.0, posinf=0.0, neginf=0.0)


def _get_all_feature_names():
    """Return combined feature names (37 + 6 + 4 + 18 + 11 = 76)."""
    names = get_multiday_feature_names()
    names += get_dow_feature_names()
    names += get_drift_feature_names()
    names += get_meal_schedule_feature_names()
    names += get_overnight_feature_names()
    return names


def _label_attention_needed(daily_metrics, day_index, horizon=3):
    """Label 1 if any of the next `horizon` days is a bad day."""
    for h in range(1, horizon + 1):
        d = day_index + h
        if d >= len(daily_metrics):
            return None
        label = label_day_quality(daily_metrics[d])
        if label is None:
            continue
        if label == 1:
            return 1
    return 0


def exp_1136_combined_multiday():
    """Union all features, predict 'attention needed in next 3 days', ablation."""
    print("\n" + "=" * 70)
    print("[EXP-1136] Combined Multi-Day Model with Ablation")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()
    feature_names = _get_all_feature_names()

    # Feature group indices for ablation
    n_base = len(get_multiday_feature_names())          # 37
    n_dow = len(get_dow_feature_names())                # 6
    n_drift = len(get_drift_feature_names())            # 4
    n_meal = len(get_meal_schedule_feature_names())      # 18
    n_overnight = len(get_overnight_feature_names())     # 11
    total_feats = n_base + n_dow + n_drift + n_meal + n_overnight

    groups = {
        'base_multiday': (0, n_base),
        'dow': (n_base, n_base + n_dow),
        'drift': (n_base + n_dow, n_base + n_dow + n_drift),
        'meal_schedule': (n_base + n_dow + n_drift, n_base + n_dow + n_drift + n_meal),
        'overnight': (n_base + n_dow + n_drift + n_meal, total_feats),
    }

    all_results = {
        'experiment': 'EXP-1136',
        'title': 'Combined Multi-Day Model: Attention Needed in Next 3 Days',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'feature_groups': {k: {'start': v[0], 'end': v[1], 'size': v[1] - v[0]}
                           for k, v in groups.items()},
        'per_patient': {},
        'aggregate': {},
    }

    agg_full_auc = []
    agg_ablation = {gname: [] for gname in groups}

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1136] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        n_days = p['n_days']
        train_end = int(n_days * 0.6)

        # Compute auxiliary structures
        dow_profiles = compute_dow_profiles(daily_metrics, train_end)
        cp_days, rmsd_values, rmsd_positions = detect_changepoints(p['glucose'])
        rmsd_daily = np.zeros(n_days)
        for i, pos in enumerate(rmsd_positions):
            day_idx = int(pos) // STEPS_PER_DAY
            if day_idx < n_days and i < len(rmsd_values):
                rmsd_daily[day_idx] = rmsd_values[i]

        # Build features + labels
        X_all, y_all = [], []
        for d in range(LOOKBACK_DAYS, n_days - 3):
            feats = _build_all_features(p, daily_metrics, d, dow_profiles, cp_days, rmsd_daily)
            if feats is None:
                continue
            label = _label_attention_needed(daily_metrics, d, horizon=3)
            if label is None:
                continue
            X_all.append(feats)
            y_all.append(label)

        if len(X_all) < 20:
            print(f"  Skip {pname}: only {len(X_all)} samples")
            continue

        X_all = np.nan_to_num(np.array(X_all, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = np.array(y_all, dtype=int)

        n = len(y_all)
        split = int(n * 0.8)
        attention_rate = float(np.mean(y_all))
        print(f"  Attention-needed rate: {attention_rate:.3f} ({np.sum(y_all)}/{n})")

        # Full model
        clf_full, full_res = _fit_gbt_classifier(X_all[:split], y_all[:split], X_all[split:], y_all[split:])
        full_fi = _feature_importance(clf_full, feature_names)
        print(f"  Full model AUC: {full_res['auc']:.3f}")

        # Ablation: remove each feature group and measure AUC drop
        ablation_results = {}
        for gname, (gstart, gend) in groups.items():
            # Create ablated feature set (zero out the group)
            X_ablated = X_all.copy()
            X_ablated[:, gstart:gend] = 0.0

            _, ablated_res = _fit_gbt_classifier(
                X_ablated[:split], y_all[:split], X_ablated[split:], y_all[split:]
            )
            auc_drop = full_res['auc'] - ablated_res['auc']
            ablation_results[gname] = {
                'ablated_auc': ablated_res['auc'],
                'auc_drop': auc_drop,
            }
            agg_ablation[gname].append(auc_drop)
            print(f"    Ablation -{gname}: AUC={ablated_res['auc']:.3f} (Δ={auc_drop:+.3f})")

        patient_result = {
            'n_samples': n,
            'attention_needed_rate': attention_rate,
            'full_model': full_res,
            'feature_importance': full_fi,
            'ablation': ablation_results,
        }
        all_results['per_patient'][pname] = patient_result
        agg_full_auc.append(full_res['auc'])

    if agg_full_auc:
        ablation_summary = {}
        for gname, drops in agg_ablation.items():
            if drops:
                ablation_summary[gname] = {
                    'mean_auc_drop': float(np.mean(drops)),
                    'std_auc_drop': float(np.std(drops)),
                }
        all_results['aggregate'] = {
            'n_patients': len(agg_full_auc),
            'full_model_auc': {'mean': float(np.mean(agg_full_auc)), 'std': float(np.std(agg_full_auc))},
            'ablation': ablation_summary,
        }
        print(f"\n  Aggregate Full AUC: {np.mean(agg_full_auc):.3f} ± {np.std(agg_full_auc):.3f}")
        for gname, summary in ablation_summary.items():
            print(f"    -{gname}: mean drop = {summary['mean_auc_drop']:+.3f}")

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1136] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1137: Planning Horizon Decay
# ===========================================================================

def exp_1137_horizon_decay():
    """Evaluate prediction quality at horizons 1d, 2d, 3d, 5d, 7d."""
    print("\n" + "=" * 70)
    print("[EXP-1137] Planning Horizon Decay: AUC vs Forecast Horizon")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()
    horizons = [1, 2, 3, 5, 7]

    all_results = {
        'experiment': 'EXP-1137',
        'title': 'Planning Horizon Decay: AUC vs Forecast Distance',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'horizons_tested': horizons,
        'per_patient': {},
        'aggregate': {},
    }

    # Collect per-horizon AUC across patients
    agg_by_horizon = {h: [] for h in horizons}

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1137] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        n_days = p['n_days']
        train_end = int(n_days * 0.6)

        dow_profiles = compute_dow_profiles(daily_metrics, train_end)
        cp_days, rmsd_values, rmsd_positions = detect_changepoints(p['glucose'])
        rmsd_daily = np.zeros(n_days)
        for i, pos in enumerate(rmsd_positions):
            day_idx = int(pos) // STEPS_PER_DAY
            if day_idx < n_days and i < len(rmsd_values):
                rmsd_daily[day_idx] = rmsd_values[i]

        horizon_results = {}
        for h in horizons:
            print(f"  Horizon h={h}d...")

            X_h, y_h = [], []
            for d in range(LOOKBACK_DAYS, n_days - h):
                feats = _build_all_features(p, daily_metrics, d, dow_profiles, cp_days, rmsd_daily)
                if feats is None:
                    continue
                # Label: is day d+h a bad day?
                target = daily_metrics[d + h] if d + h < len(daily_metrics) else None
                if target is None:
                    continue
                label = label_day_quality(target)
                if label is None:
                    continue
                X_h.append(feats)
                y_h.append(label)

            if len(X_h) < 20:
                horizon_results[f'h{h}d'] = {'auc': 0.5, 'n_samples': len(X_h), 'skipped': True}
                continue

            X_h = np.nan_to_num(np.array(X_h, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
            y_h = np.array(y_h, dtype=int)

            n = len(y_h)
            split = int(n * 0.8)
            _, h_res = _fit_gbt_classifier(X_h[:split], y_h[:split], X_h[split:], y_h[split:])

            horizon_results[f'h{h}d'] = {
                'auc': h_res['auc'],
                'n_samples': n,
                'bad_rate': float(np.mean(y_h)),
            }
            agg_by_horizon[h].append(h_res['auc'])
            print(f"    AUC: {h_res['auc']:.3f} (n={n}, bad_rate={np.mean(y_h):.2f})")

        # Compute decay rate (linear fit of AUC vs horizon)
        valid_h = [(h, horizon_results[f'h{h}d']['auc'])
                   for h in horizons if not horizon_results.get(f'h{h}d', {}).get('skipped')]
        decay_rate = 0.0
        if len(valid_h) >= 2:
            h_arr = np.array([v[0] for v in valid_h], dtype=float)
            a_arr = np.array([v[1] for v in valid_h], dtype=float)
            decay_rate = float(_safe_trend(a_arr))

        patient_result = {
            'horizons': horizon_results,
            'decay_rate': decay_rate,
        }
        all_results['per_patient'][pname] = patient_result

    # Aggregate
    if any(len(v) > 0 for v in agg_by_horizon.values()):
        horizon_summary = {}
        for h in horizons:
            aucs = agg_by_horizon[h]
            if aucs:
                horizon_summary[f'h{h}d'] = {
                    'mean_auc': float(np.mean(aucs)),
                    'std_auc': float(np.std(aucs)),
                    'n_patients': len(aucs),
                }

        # Find maximum useful horizon (AUC >= 0.60)
        max_useful_horizon = 0
        for h in horizons:
            key = f'h{h}d'
            if key in horizon_summary and horizon_summary[key]['mean_auc'] >= 0.60:
                max_useful_horizon = h

        # Aggregate decay rate
        all_h_aucs = []
        all_h_vals = []
        for h in horizons:
            key = f'h{h}d'
            if key in horizon_summary:
                all_h_vals.append(h)
                all_h_aucs.append(horizon_summary[key]['mean_auc'])
        agg_decay = _safe_trend(all_h_aucs) if len(all_h_aucs) >= 2 else 0.0

        all_results['aggregate'] = {
            'horizon_summary': horizon_summary,
            'max_useful_horizon_days': max_useful_horizon,
            'aggregate_decay_rate_per_day': agg_decay,
            'clinical_assessment': (
                f"Prediction useful up to {max_useful_horizon}d ahead. "
                f"AUC decays at ~{abs(agg_decay):.3f}/day."
                if max_useful_horizon > 0 else
                "No horizon achieved AUC >= 0.60."
            ),
        }
        print(f"\n  Horizon summary:")
        for key, val in horizon_summary.items():
            print(f"    {key}: AUC = {val['mean_auc']:.3f} ± {val['std_auc']:.3f}")
        print(f"  Max useful horizon: {max_useful_horizon}d")

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1137] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# EXP-1138: Honest Evaluation with Bootstrap CI
# ===========================================================================

def _bootstrap_auc(y_true, y_score, n_iterations=1000, ci=0.95):
    """Compute bootstrap CI for AUC."""
    y_true = np.array(y_true, dtype=int)
    y_score = np.nan_to_num(np.array(y_score, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)

    if len(np.unique(y_true)) < 2:
        return {'auc': 0.5, 'ci_lower': 0.5, 'ci_upper': 0.5, 'n_boot': 0}

    rng = np.random.RandomState(42)
    aucs = []
    n = len(y_true)
    for _ in range(n_iterations):
        idx = rng.randint(0, n, size=n)
        yt = y_true[idx]
        ys = y_score[idx]
        if len(np.unique(yt)) < 2:
            continue
        try:
            aucs.append(roc_auc_score(yt, ys))
        except ValueError:
            continue

    if not aucs:
        return {'auc': 0.5, 'ci_lower': 0.5, 'ci_upper': 0.5, 'n_boot': 0}

    alpha = (1 - ci) / 2
    return {
        'auc': float(np.mean(aucs)),
        'ci_lower': float(np.percentile(aucs, 100 * alpha)),
        'ci_upper': float(np.percentile(aucs, 100 * (1 - alpha))),
        'std': float(np.std(aucs)),
        'n_boot': len(aucs),
    }


def _bootstrap_metric(values, n_iterations=1000, ci=0.95):
    """Compute bootstrap CI for a generic metric array."""
    values = np.nan_to_num(np.array(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    if len(values) < 2:
        m = float(np.mean(values)) if len(values) > 0 else 0.0
        return {'mean': m, 'ci_lower': m, 'ci_upper': m}

    rng = np.random.RandomState(42)
    boot_means = []
    n = len(values)
    for _ in range(n_iterations):
        idx = rng.randint(0, n, size=n)
        boot_means.append(float(np.mean(values[idx])))

    alpha = (1 - ci) / 2
    return {
        'mean': float(np.mean(boot_means)),
        'ci_lower': float(np.percentile(boot_means, 100 * alpha)),
        'ci_upper': float(np.percentile(boot_means, 100 * (1 - alpha))),
    }


def exp_1138_honest_evaluation():
    """5-fold temporal block CV, bootstrap CI, comparison to baselines."""
    print("\n" + "=" * 70)
    print("[EXP-1138] Honest Evaluation with Bootstrap CI")
    print("=" * 70)
    t0 = time.time()

    patients = _load_data()

    all_results = {
        'experiment': 'EXP-1138',
        'title': 'Honest Evaluation: Bootstrap CI and Baseline Comparison',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {},
        'aggregate': {},
    }

    agg_model_auc = []
    agg_baseline_same = []
    agg_baseline_dow = []
    agg_baseline_always_good = []

    for p in patients:
        pname = p['name']
        print(f"\n[EXP-1138] Processing {pname}...")

        daily_metrics = compute_all_daily_metrics(p)
        valid_count = sum(1 for m in daily_metrics if m is not None)
        if valid_count < MIN_DAYS:
            print(f"  Skip {pname}: insufficient valid days")
            continue

        n_days = p['n_days']
        train_end_global = int(n_days * 0.6)
        dow_profiles = compute_dow_profiles(daily_metrics, train_end_global)
        cp_days, rmsd_values, rmsd_positions = detect_changepoints(p['glucose'])
        rmsd_daily = np.zeros(n_days)
        for i, pos in enumerate(rmsd_positions):
            day_idx = int(pos) // STEPS_PER_DAY
            if day_idx < n_days and i < len(rmsd_values):
                rmsd_daily[day_idx] = rmsd_values[i]

        # Build full feature/label set
        X_all, y_all, day_indices = [], [], []
        for d in range(LOOKBACK_DAYS, n_days - 1):
            feats = _build_all_features(p, daily_metrics, d, dow_profiles, cp_days, rmsd_daily)
            if feats is None:
                continue
            target = daily_metrics[d + 1]
            if target is None:
                continue
            label = label_day_quality(target)
            if label is None:
                continue
            X_all.append(feats)
            y_all.append(label)
            day_indices.append(d)

        if len(X_all) < 30:
            print(f"  Skip {pname}: only {len(X_all)} samples")
            continue

        X_all = np.nan_to_num(np.array(X_all, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = np.array(y_all, dtype=int)
        day_indices = np.array(day_indices, dtype=int)

        # 5-fold temporal block CV
        folds = temporal_kfold_splits(len(X_all), k=5)
        if len(folds) < 2:
            print(f"  Skip {pname}: insufficient data for 5-fold CV")
            continue

        fold_y_true_all = []
        fold_y_score_all = []
        fold_aucs = []
        fold_sensitivities = []
        fold_specificities = []

        # Baseline predictions
        baseline_same_scores = []  # predict same as yesterday
        baseline_dow_scores = []   # predict based on DOW average
        baseline_always_good = []  # always predict good

        for fold_idx, ((tr_start, tr_end), (te_start, te_end)) in enumerate(folds):
            X_tr = X_all[tr_start:tr_end]
            y_tr = y_all[tr_start:tr_end]
            X_te = X_all[te_start:te_end]
            y_te = y_all[te_start:te_end]

            if len(X_te) < 5 or len(np.unique(y_tr)) < 2:
                continue

            # Model prediction
            clf = GradientBoostingClassifier(**GBT_PARAMS)
            clf.fit(
                np.nan_to_num(X_tr, nan=0.0, posinf=0.0, neginf=0.0),
                y_tr
            )
            probs = clf.predict_proba(np.nan_to_num(X_te, nan=0.0, posinf=0.0, neginf=0.0))
            if probs.shape[1] < 2:
                continue
            y_score = probs[:, 1]

            fold_y_true_all.extend(y_te.tolist())
            fold_y_score_all.extend(y_score.tolist())

            try:
                fold_auc = roc_auc_score(y_te, y_score)
            except ValueError:
                fold_auc = 0.5
            fold_aucs.append(fold_auc)

            preds = clf.predict(np.nan_to_num(X_te, nan=0.0, posinf=0.0, neginf=0.0))
            cm = confusion_matrix(y_te, preds, labels=[0, 1])
            tn = int(cm[0, 0]) if cm.shape[0] > 0 else 0
            fp = int(cm[0, 1]) if cm.shape[1] > 1 else 0
            fn = int(cm[1, 0]) if cm.shape[0] > 1 else 0
            tp = int(cm[1, 1]) if cm.shape[0] > 1 and cm.shape[1] > 1 else 0
            fold_sensitivities.append(tp / max(tp + fn, 1))
            fold_specificities.append(tn / max(tn + fp, 1))

            # Baseline 1: "same as yesterday" — use yesterday's quality
            te_day_indices = day_indices[te_start:te_end]
            for i, d in enumerate(te_day_indices):
                yesterday_label = label_day_quality(daily_metrics[d])
                baseline_same_scores.append(
                    (int(y_te[i]), float(yesterday_label) if yesterday_label is not None else 0.0)
                )

            # Baseline 2: DOW historical average
            for i, d in enumerate(te_day_indices):
                dow_idx = d % 7
                if dow_idx in dow_profiles:
                    dow_tir = dow_profiles[dow_idx].get('tir', 0.7)
                    dow_pred = 1.0 if dow_tir < BAD_TIR else 0.0
                else:
                    dow_pred = 0.0
                baseline_dow_scores.append((int(y_te[i]), dow_pred))

            # Baseline 3: always predict "good day"
            for val in y_te:
                baseline_always_good.append((int(val), 0.0))

            print(f"  Fold {fold_idx}: AUC={fold_auc:.3f}, "
                  f"sens={fold_sensitivities[-1]:.3f}, spec={fold_specificities[-1]:.3f}")

        if not fold_y_true_all:
            print(f"  Skip {pname}: no valid folds")
            continue

        # Bootstrap CI on pooled predictions
        y_true_arr = np.array(fold_y_true_all, dtype=int)
        y_score_arr = np.array(fold_y_score_all, dtype=float)
        bootstrap_result = _bootstrap_auc(y_true_arr, y_score_arr, n_iterations=1000)

        # Bootstrap CI for sensitivity and specificity
        sens_boot = _bootstrap_metric(np.array(fold_sensitivities))
        spec_boot = _bootstrap_metric(np.array(fold_specificities))

        print(f"  Model AUC: {bootstrap_result['auc']:.3f} "
              f"[{bootstrap_result['ci_lower']:.3f}, {bootstrap_result['ci_upper']:.3f}]")

        # Baseline AUCs
        baseline_results = {}

        # Baseline 1: same as yesterday
        if baseline_same_scores:
            bs_true = np.array([x[0] for x in baseline_same_scores], dtype=int)
            bs_score = np.array([x[1] for x in baseline_same_scores], dtype=float)
            try:
                bs1_auc = roc_auc_score(bs_true, bs_score)
            except ValueError:
                bs1_auc = 0.5
            baseline_results['same_as_yesterday'] = {'auc': float(bs1_auc)}
            agg_baseline_same.append(bs1_auc)
            print(f"  Baseline (same as yesterday): AUC={bs1_auc:.3f}")

        # Baseline 2: DOW average
        if baseline_dow_scores:
            bd_true = np.array([x[0] for x in baseline_dow_scores], dtype=int)
            bd_score = np.array([x[1] for x in baseline_dow_scores], dtype=float)
            try:
                bs2_auc = roc_auc_score(bd_true, bd_score)
            except ValueError:
                bs2_auc = 0.5
            baseline_results['dow_historical'] = {'auc': float(bs2_auc)}
            agg_baseline_dow.append(bs2_auc)
            print(f"  Baseline (DOW historical): AUC={bs2_auc:.3f}")

        # Baseline 3: always good
        if baseline_always_good:
            bg_true = np.array([x[0] for x in baseline_always_good], dtype=int)
            bg_score = np.array([x[1] for x in baseline_always_good], dtype=float)
            try:
                bs3_auc = roc_auc_score(bg_true, bg_score)
            except ValueError:
                bs3_auc = 0.5
            baseline_results['always_good'] = {'auc': float(bs3_auc)}
            agg_baseline_always_good.append(bs3_auc)
            print(f"  Baseline (always good): AUC={bs3_auc:.3f}")

        patient_result = {
            'n_samples': len(X_all),
            'n_folds': len(fold_aucs),
            'model': {
                'auc_bootstrap': bootstrap_result,
                'sensitivity_bootstrap': sens_boot,
                'specificity_bootstrap': spec_boot,
                'fold_aucs': [round(a, 4) for a in fold_aucs],
            },
            'baselines': baseline_results,
        }
        all_results['per_patient'][pname] = patient_result
        agg_model_auc.append(bootstrap_result['auc'])

    # Aggregate
    if agg_model_auc:
        model_boot = _bootstrap_metric(np.array(agg_model_auc))

        baseline_comparison = {}
        if agg_baseline_same:
            baseline_comparison['same_as_yesterday'] = {
                'mean_auc': float(np.mean(agg_baseline_same)),
                'improvement_over_baseline': float(np.mean(agg_model_auc) - np.mean(agg_baseline_same)),
            }
        if agg_baseline_dow:
            baseline_comparison['dow_historical'] = {
                'mean_auc': float(np.mean(agg_baseline_dow)),
                'improvement_over_baseline': float(np.mean(agg_model_auc) - np.mean(agg_baseline_dow)),
            }
        if agg_baseline_always_good:
            baseline_comparison['always_good'] = {
                'mean_auc': float(np.mean(agg_baseline_always_good)),
                'improvement_over_baseline': float(np.mean(agg_model_auc) - np.mean(agg_baseline_always_good)),
            }

        all_results['aggregate'] = {
            'n_patients': len(agg_model_auc),
            'model_auc': model_boot,
            'baseline_comparison': baseline_comparison,
            'conclusion': (
                f"Model AUC: {model_boot['mean']:.3f} "
                f"[{model_boot['ci_lower']:.3f}, {model_boot['ci_upper']:.3f}]. "
                f"{'Outperforms' if model_boot['mean'] > 0.60 else 'Does not outperform'} "
                f"naive baselines."
            ),
        }
        print(f"\n  Aggregate model AUC: {model_boot['mean']:.3f} "
              f"[{model_boot['ci_lower']:.3f}, {model_boot['ci_upper']:.3f}]")

    elapsed = time.time() - t0
    all_results['elapsed_seconds'] = round(elapsed, 1)
    print(f"\n[EXP-1138] Complete in {elapsed:.1f}s")
    return all_results


# ===========================================================================
# Main
# ===========================================================================

EXPERIMENTS = {
    1131: exp_1131_multiday_baseline,
    1132: exp_1132_weekly_patterns,
    1133: exp_1133_settings_drift,
    1134: exp_1134_override_scheduler,
    1135: exp_1135_overnight_risk,
    1136: exp_1136_combined_multiday,
    1137: exp_1137_horizon_decay,
    1138: exp_1138_honest_evaluation,
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='EXP-1131 to EXP-1138: Multi-Day Advance Planning Research'
    )
    parser.add_argument(
        '--exp', type=int, nargs='+', default=[1131],
        help='Experiment IDs to run (default: 1131). Use 0 for all.',
    )
    parser.add_argument(
        '--patients-dir', default=None,
        help='Override patients directory path.',
    )
    args = parser.parse_args()

    if args.patients_dir:
        PATIENTS_DIR = args.patients_dir

    if not HAS_SKLEARN:
        print("ERROR: scikit-learn is required. Install with: pip install scikit-learn")
        sys.exit(1)

    exp_ids = list(EXPERIMENTS.keys()) if 0 in args.exp else args.exp

    print(f"Running experiments: {exp_ids}")
    print(f"Patients dir: {PATIENTS_DIR}")
    print()

    for eid in exp_ids:
        if eid not in EXPERIMENTS:
            print(f"[WARN] Unknown experiment EXP-{eid}, skipping")
            continue

        result = EXPERIMENTS[eid]()
        out_path = _save_results(result, eid, result.get('title', '').replace(' ', '_').replace(':', '')[:60])
        print(f"[EXP-{eid}] Saved to {out_path}\n")
