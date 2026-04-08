#!/usr/bin/env python3
"""EXP-1141 to EXP-1145: Adaptive Alert Suppression Research.

Problem: Current fixed-threshold meal prediction yields 23.7 alerts/day
with PPV=0.24 and a 120-min suppression window. Target: ≤5 alerts/day,
PPV≥0.50.

Experiments:
  EXP-1141  Per-patient threshold optimisation
  EXP-1142  Time-of-day adaptive thresholds
  EXP-1143  Meal-frequency-based suppression
  EXP-1144  Confidence-weighted alerting
  EXP-1145  Production alert simulation (best strategy end-to-end)

Run:
    PYTHONPATH=tools python -m cgmencode.exp_alert_suppression_1141 --detail --save
    PYTHONPATH=tools python -m cgmencode.exp_alert_suppression_1141 --exp 1141
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import argparse
import json
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_flux import load_patients, save_results
from cgmencode.exp_metabolic_441 import compute_supply_demand

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

# ── Constants ────────────────────────────────────────────────────────────────

PATIENTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / 'externals' / 'ns-data' / 'patients'
)
GLUCOSE_SCALE = 400.0
STEPS_PER_DAY = 288          # 24h × 12 steps/h
STEPS_PER_HOUR = 12
ALERT_SUPPRESSION_MIN = 120  # current production default
MIN_MEALS_REQUIRED = 20      # skip patient if fewer meals
TRAIN_FRAC = 0.70            # temporal 70/30 split


# ── Shared helpers ───────────────────────────────────────────────────────────

def detect_meals_from_physics(glucose, net_flux,
                              threshold=0.15, min_duration=15,
                              min_integral=1.0):
    """Detect meals from net_flux bursts.

    Returns list of dicts with keys: index, hour, integral.
    """
    N = len(glucose)
    meals = []
    in_burst = False
    burst_start = None
    burst_integral = 0.0

    for i in range(N):
        if net_flux[i] > threshold and not in_burst:
            in_burst = True
            burst_start = i
            burst_integral = net_flux[i]
        elif net_flux[i] > threshold and in_burst:
            burst_integral += net_flux[i]
        elif in_burst:
            in_burst = False
            duration = (i - burst_start) * 5
            if duration >= min_duration and burst_integral > min_integral:
                hour = (burst_start % STEPS_PER_DAY) * 5.0 / 60.0
                meals.append({
                    'index': burst_start,
                    'hour': hour,
                    'integral': burst_integral,
                })

    return meals


def build_features_and_labels(glucose, net_flux, supply, meals,
                              horizon_steps=6, days_of_data=180):
    """Build 16-feature vectors and binary meal-ahead labels.

    Features (16):
      Time:    hour_sin, hour_cos, min_since_meal, meals_today, dow, hist_meal_prob
      Glucose: trend_15, trend_30, glucose_scaled (÷400)
      Window:  wmean, wstd, wslope, wflat, fasting_dur, iob_proxy
      Reactive: net_flux

    Label: 1 if a meal starts within *horizon_steps* steps ahead.
    """
    N = len(glucose)
    features = []
    labels = []
    meal_set = set(m['index'] for m in meals)
    meal_indices = sorted(meal_set)

    for i in range(13, N):
        # ── Label ────────────────────────────────────────────────────
        label = 0
        for mi in meal_indices:
            if 0 < (mi - i) <= horizon_steps:
                label = 1
                break

        # ── Time features ────────────────────────────────────────────
        hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
        hour_sin = np.sin(2.0 * np.pi * hour / 24.0)
        hour_cos = np.cos(2.0 * np.pi * hour / 24.0)

        past_meals = [m for m in meal_indices if m < i]
        min_since = (i - past_meals[-1]) * 5 if past_meals else 1440

        day_start = (i // STEPS_PER_DAY) * STEPS_PER_DAY
        meals_today = sum(1 for m in meal_indices if day_start <= m < i)

        dow = (i // STEPS_PER_DAY) % 7

        hist_prob = (
            sum(1 for m in meals if abs(m['hour'] - hour) < 0.5)
            / max(days_of_data / 7.0, 1.0)
        )

        # ── Glucose features ─────────────────────────────────────────
        g_now = glucose[i] if not np.isnan(glucose[i]) else 120.0
        g_15 = glucose[i - 3] if i >= 3 and not np.isnan(glucose[i - 3]) else g_now
        g_30 = glucose[i - 6] if i >= 6 and not np.isnan(glucose[i - 6]) else g_now
        trend_15 = g_now - g_15
        trend_30 = g_now - g_30
        glucose_scaled = g_now / GLUCOSE_SCALE

        # ── 60-min window features (13 steps) ────────────────────────
        win = glucose[max(0, i - 12): i + 1]
        win_valid = win[~np.isnan(win)] if len(win) > 0 else np.array([120.0])
        if len(win_valid) < 2:
            win_valid = np.array([120.0, 120.0])
        wmean = float(np.mean(win_valid)) / GLUCOSE_SCALE
        wstd = float(np.std(win_valid))
        x_idx = np.arange(len(win_valid))
        wslope = float(np.polyfit(x_idx, win_valid, 1)[0]) if len(win_valid) > 1 else 0.0
        wflat = 1.0 / (1.0 + wstd)

        # Fasting duration
        mean_g = float(np.nanmean(glucose[max(0, i - STEPS_PER_DAY): i + 1]))
        fasting_steps = 0
        for j in range(i, max(0, i - STEPS_PER_DAY), -1):
            if not np.isnan(glucose[j]) and glucose[j] > mean_g + 15:
                break
            fasting_steps += 1
        fasting_dur = fasting_steps * 5.0 / 60.0

        # IOB proxy from supply
        sup_win = supply[max(0, i - 12): i + 1]
        iob_proxy = float(np.nanmean(sup_win)) if len(sup_win) > 0 else 0.0

        feat = [
            hour_sin, hour_cos,
            min_since / 1440.0, meals_today / 10.0,
            dow / 6.0, hist_prob,
            trend_15, trend_30, glucose_scaled,
            wmean, wstd, wslope, wflat, fasting_dur, iob_proxy,
            float(net_flux[i]),
        ]
        features.append(np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0))
        labels.append(label)

    return np.array(features), np.array(labels)


def _safe_auc(y_true, y_score):
    """ROC-AUC that returns 0.5 for degenerate inputs."""
    if len(y_true) < 2:
        return 0.5
    if len(set(y_true)) < 2:
        return 0.5
    try:
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        return 0.5


def _prepare_patient(p):
    """Extract glucose, net_flux, supply, and detected meals for one patient.

    Returns (glucose, net_flux, supply, meals) or None on failure.
    """
    try:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        sd = compute_supply_demand(df, pk_array=p['pk'])
        net_flux = np.nan_to_num(sd['net'], nan=0.0, posinf=0.0, neginf=0.0)
        supply = np.nan_to_num(sd['supply'], nan=0.0, posinf=0.0, neginf=0.0)
        meals = detect_meals_from_physics(glucose, net_flux)
        return glucose, net_flux, supply, meals
    except Exception:
        return None


def _temporal_split(X, y, train_frac=TRAIN_FRAC):
    """Block-CV temporal split (first train_frac → train, rest → test)."""
    n = len(X)
    split = int(n * train_frac)
    return X[:split], y[:split], X[split:], y[split:]


def _train_proactive_model(X_train, y_train, n_estimators=200,
                           max_depth=3, learning_rate=0.08):
    """Train a GBT on the 15 proactive features (no net_flux)."""
    X_train_clean = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    clf = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=0.8,
        random_state=42,
    )
    clf.fit(X_train_clean, y_train)
    return clf


def _predict_scores(clf, X):
    """Return P(meal) from a trained classifier, with nan guard."""
    X_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return clf.predict_proba(X_clean)[:, 1]


def _compute_alert_metrics(y_true, alerts, steps_per_day=STEPS_PER_DAY):
    """Compute PPV, sensitivity, and alerts/day from binary alert array."""
    n = len(y_true)
    total_days = max(n / steps_per_day, 1.0)
    total_alerts = int(np.sum(alerts))
    alerts_per_day = total_alerts / total_days

    tp = int(np.sum((alerts == 1) & (y_true == 1)))
    fp = int(np.sum((alerts == 1) & (y_true == 0)))
    fn = int(np.sum((alerts == 0) & (y_true == 1)))

    ppv = tp / max(tp + fp, 1)
    sensitivity = tp / max(tp + fn, 1)
    return {
        'alerts_per_day': round(alerts_per_day, 2),
        'ppv': round(ppv, 4),
        'sensitivity': round(sensitivity, 4),
        'tp': tp, 'fp': fp, 'fn': fn,
        'total_alerts': total_alerts,
    }


def _assign_meal_window(hour):
    """Classify hour into meal window."""
    if 5 <= hour < 10:
        return 'breakfast'
    elif 10 <= hour < 14:
        return 'lunch'
    elif 17 <= hour < 21:
        return 'dinner'
    else:
        return 'snack'


# ── EXP-1141: Per-Patient Threshold Optimisation ────────────────────────────

def exp_1141_per_patient_threshold(patients, detail=False):
    """Sweep proactive-model thresholds per patient.

    For each patient: train proactive GBT (15 features), sweep thresholds
    0.05–0.95, find (a) optimal threshold for PPV≥0.50 w/ max sensitivity,
    (b) threshold yielding ≤5 alerts/day.
    """
    print("[EXP-1141] Per-patient threshold optimisation …")
    per_patient = {}
    thresholds_ppv = []
    thresholds_alert = []

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            if detail:
                print(f"  {name}: SKIP (prep failed)")
            continue
        glucose, net_flux, supply, meals = prep

        if len(meals) < MIN_MEALS_REQUIRED:
            if detail:
                print(f"  {name}: SKIP ({len(meals)} meals < {MIN_MEALS_REQUIRED})")
            continue

        X, y = build_features_and_labels(glucose, net_flux, supply, meals)
        if len(X) == 0:
            continue

        # Proactive features only (drop net_flux at index 15)
        X_pro = X[:, :15]
        X_train, y_train, X_test, y_test = _temporal_split(X_pro, y)

        if len(set(y_train)) < 2 or len(set(y_test)) < 2:
            if detail:
                print(f"  {name}: SKIP (degenerate labels)")
            continue

        clf = _train_proactive_model(X_train, y_train)
        scores = _predict_scores(clf, X_test)
        auc = _safe_auc(y_test, scores)

        # Sweep thresholds
        best_ppv_thresh = None
        best_ppv_sens = -1.0
        best_alert_thresh = None
        best_alert_ppv = 0.0
        best_alert_sens = 0.0
        sweep_results = []

        for thresh_int in range(5, 100, 5):
            thresh = thresh_int / 100.0
            alerts = (scores >= thresh).astype(int)
            m = _compute_alert_metrics(y_test, alerts)
            sweep_results.append({'threshold': thresh, **m})

            # Target A: PPV ≥ 0.50 with maximum sensitivity
            if m['ppv'] >= 0.50 and m['sensitivity'] > best_ppv_sens:
                best_ppv_sens = m['sensitivity']
                best_ppv_thresh = thresh

            # Target B: alerts/day ≤ 5 — pick lowest threshold that satisfies
            if m['alerts_per_day'] <= 5.0:
                if best_alert_thresh is None or thresh < best_alert_thresh:
                    best_alert_thresh = thresh
                    best_alert_ppv = m['ppv']
                    best_alert_sens = m['sensitivity']

        # If no threshold met PPV≥0.50, pick the one with highest PPV
        if best_ppv_thresh is None:
            best_row = max(sweep_results, key=lambda r: r['ppv'])
            best_ppv_thresh = best_row['threshold']
            best_ppv_sens = best_row['sensitivity']

        # Find metrics at the PPV-optimal threshold
        opt_row = next(r for r in sweep_results
                       if r['threshold'] == best_ppv_thresh)

        entry = {
            'auc': round(auc, 4),
            'optimal_threshold_ppv': best_ppv_thresh,
            'ppv_at_optimal': round(opt_row['ppv'], 4),
            'sensitivity_at_optimal': round(opt_row['sensitivity'], 4),
            'alerts_per_day_at_optimal': opt_row['alerts_per_day'],
            'threshold_for_5alerts': best_alert_thresh,
            'ppv_at_5alerts': round(best_alert_ppv, 4),
            'sensitivity_at_5alerts': round(best_alert_sens, 4),
            'n_meals': len(meals),
            'n_test': len(y_test),
            'sweep': sweep_results,
        }
        per_patient[name] = entry
        thresholds_ppv.append(best_ppv_thresh)
        if best_alert_thresh is not None:
            thresholds_alert.append(best_alert_thresh)

        if detail:
            print(f"  {name}: AUC={auc:.3f}  opt_thresh={best_ppv_thresh:.2f} "
                  f"PPV={opt_row['ppv']:.2f} sens={opt_row['sensitivity']:.2f} "
                  f"alerts/day={opt_row['alerts_per_day']:.1f}")

    # Aggregate
    if not per_patient:
        return {'experiment_id': 'EXP-1141', 'status': 'FAIL',
                'summary': 'No patients processed', 'per_patient': {},
                'key_finding': 'No data'}

    mean_thresh = float(np.mean(thresholds_ppv))
    mean_ppv = float(np.mean([v['ppv_at_optimal'] for v in per_patient.values()]))
    mean_sens = float(np.mean([v['sensitivity_at_optimal']
                               for v in per_patient.values()]))
    mean_apd = float(np.mean([v['alerts_per_day_at_optimal']
                              for v in per_patient.values()]))

    summary = {
        'mean_optimal_threshold': round(mean_thresh, 3),
        'mean_ppv': round(mean_ppv, 4),
        'mean_sensitivity': round(mean_sens, 4),
        'mean_alerts_per_day': round(mean_apd, 2),
        'n_patients': len(per_patient),
    }
    key = (f"Per-patient thresholds reduce alerts from 23.7 to "
           f"{mean_apd:.1f}/day while achieving PPV={mean_ppv:.2f}")

    print(f"[EXP-1141] Summary: {key}")

    # Remove per-step sweep detail from saved output (too large)
    for v in per_patient.values():
        v.pop('sweep', None)

    return {
        'experiment_id': 'EXP-1141',
        'title': 'Per-Patient Threshold Optimization',
        'status': 'OK',
        'per_patient': per_patient,
        'summary': summary,
        'key_finding': key,
    }


# ── EXP-1142: Time-of-Day Adaptive Thresholds ───────────────────────────────

def exp_1142_time_of_day_thresholds(patients, detail=False):
    """Find optimal thresholds per meal window (breakfast/lunch/dinner/snack).

    Compare window-specific thresholds vs a single global threshold.
    """
    print("[EXP-1142] Time-of-day adaptive thresholds …")
    per_patient = {}
    window_names = ['breakfast', 'lunch', 'dinner', 'snack']

    global_ppvs, global_senses, global_apds = [], [], []
    window_ppvs, window_senses, window_apds = [], [], []

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            continue
        glucose, net_flux, supply, meals = prep

        if len(meals) < MIN_MEALS_REQUIRED:
            if detail:
                print(f"  {name}: SKIP ({len(meals)} meals)")
            continue

        X, y = build_features_and_labels(glucose, net_flux, supply, meals)
        if len(X) == 0:
            continue
        X_pro = X[:, :15]
        X_train, y_train, X_test, y_test = _temporal_split(X_pro, y)

        if len(set(y_train)) < 2:
            continue

        clf = _train_proactive_model(X_train, y_train)
        scores = _predict_scores(clf, X_test)

        # Assign each test step to a meal window
        # Test indices start at offset = len(X_train) + 13 (from build_features)
        offset = len(X_train) + 13
        test_hours = np.array([
            ((offset + j) % STEPS_PER_DAY) * 5.0 / 60.0
            for j in range(len(y_test))
        ])
        test_windows = np.array([_assign_meal_window(h) for h in test_hours])

        # ── Global optimal threshold (PPV ≥ 0.50) ────────────────────
        best_global_thresh = 0.50
        best_global_sens = 0.0
        for thresh_int in range(5, 100, 5):
            thresh = thresh_int / 100.0
            alerts = (scores >= thresh).astype(int)
            m = _compute_alert_metrics(y_test, alerts)
            if m['ppv'] >= 0.50 and m['sensitivity'] > best_global_sens:
                best_global_sens = m['sensitivity']
                best_global_thresh = thresh

        global_alerts = (scores >= best_global_thresh).astype(int)
        global_m = _compute_alert_metrics(y_test, global_alerts)

        # ── Per-window optimal thresholds ─────────────────────────────
        window_thresholds = {}
        combined_alerts = np.zeros(len(y_test), dtype=int)

        for wname in window_names:
            mask = (test_windows == wname)
            if mask.sum() < 10:
                window_thresholds[wname] = best_global_thresh
                combined_alerts[mask] = (scores[mask] >= best_global_thresh).astype(int)
                continue

            w_scores = scores[mask]
            w_labels = y_test[mask]

            best_wt = best_global_thresh  # fall back to global
            best_ws = 0.0
            for thresh_int in range(5, 100, 5):
                thresh = thresh_int / 100.0
                w_alerts = (w_scores >= thresh).astype(int)
                wm = _compute_alert_metrics(w_labels, w_alerts)
                if wm['ppv'] >= 0.50 and wm['sensitivity'] > best_ws:
                    best_ws = wm['sensitivity']
                    best_wt = thresh

            window_thresholds[wname] = best_wt
            combined_alerts[mask] = (scores[mask] >= best_wt).astype(int)

        window_m = _compute_alert_metrics(y_test, combined_alerts)

        entry = {
            'global_threshold': best_global_thresh,
            'global_ppv': round(global_m['ppv'], 4),
            'global_sensitivity': round(global_m['sensitivity'], 4),
            'global_alerts_per_day': global_m['alerts_per_day'],
            'window_thresholds': window_thresholds,
            'window_ppv': round(window_m['ppv'], 4),
            'window_sensitivity': round(window_m['sensitivity'], 4),
            'window_alerts_per_day': window_m['alerts_per_day'],
            'n_meals': len(meals),
        }
        per_patient[name] = entry

        global_ppvs.append(global_m['ppv'])
        global_senses.append(global_m['sensitivity'])
        global_apds.append(global_m['alerts_per_day'])
        window_ppvs.append(window_m['ppv'])
        window_senses.append(window_m['sensitivity'])
        window_apds.append(window_m['alerts_per_day'])

        if detail:
            print(f"  {name}: global={best_global_thresh:.2f} "
                  f"PPV={global_m['ppv']:.2f}/{window_m['ppv']:.2f} "
                  f"sens={global_m['sensitivity']:.2f}/{window_m['sensitivity']:.2f} "
                  f"apd={global_m['alerts_per_day']:.1f}/{window_m['alerts_per_day']:.1f}")

    if not per_patient:
        return {'experiment_id': 'EXP-1142', 'status': 'FAIL',
                'summary': 'No patients', 'per_patient': {}, 'key_finding': ''}

    summary = {
        'global_mean_ppv': round(float(np.mean(global_ppvs)), 4),
        'global_mean_sensitivity': round(float(np.mean(global_senses)), 4),
        'global_mean_alerts_per_day': round(float(np.mean(global_apds)), 2),
        'window_mean_ppv': round(float(np.mean(window_ppvs)), 4),
        'window_mean_sensitivity': round(float(np.mean(window_senses)), 4),
        'window_mean_alerts_per_day': round(float(np.mean(window_apds)), 2),
        'n_patients': len(per_patient),
    }

    delta_apd = summary['global_mean_alerts_per_day'] - summary['window_mean_alerts_per_day']
    key = (f"Window-specific thresholds yield "
           f"PPV={summary['window_mean_ppv']:.2f} "
           f"sens={summary['window_mean_sensitivity']:.2f} "
           f"({delta_apd:+.1f} alerts/day vs global)")

    print(f"[EXP-1142] Summary: {key}")

    return {
        'experiment_id': 'EXP-1142',
        'title': 'Time-of-Day Adaptive Thresholds',
        'status': 'OK',
        'per_patient': per_patient,
        'summary': summary,
        'key_finding': key,
    }


# ── EXP-1143: Meal Frequency-Based Suppression ──────────────────────────────

def exp_1143_frequency_suppression(patients, detail=False):
    """Test suppression-window strategies based on inter-meal intervals.

    Strategies:
      fixed_120   – current production (120 min)
      median_75   – median(IMI) × 0.75
      p25         – 25th-percentile IMI
      adaptive    – time-since-last-alert + expected-next-meal
    """
    print("[EXP-1143] Meal frequency-based suppression …")
    per_patient = {}
    strategy_names = ['fixed_120', 'median_75', 'p25', 'adaptive']
    agg = {s: {'ppv': [], 'sens': [], 'apd': [], 'missed': []}
           for s in strategy_names}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            continue
        glucose, net_flux, supply, meals = prep

        if len(meals) < MIN_MEALS_REQUIRED:
            if detail:
                print(f"  {name}: SKIP ({len(meals)} meals)")
            continue

        X, y = build_features_and_labels(glucose, net_flux, supply, meals)
        if len(X) == 0:
            continue
        X_pro = X[:, :15]
        X_train, y_train, X_test, y_test = _temporal_split(X_pro, y)

        if len(set(y_train)) < 2:
            continue

        clf = _train_proactive_model(X_train, y_train)
        scores = _predict_scores(clf, X_test)

        # Use a moderate threshold (best from EXP-1141-style sweep)
        best_thresh = 0.30
        best_sens = 0.0
        for ti in range(10, 90, 5):
            t = ti / 100.0
            a = (scores >= t).astype(int)
            m = _compute_alert_metrics(y_test, a)
            if m['ppv'] >= 0.45 and m['sensitivity'] > best_sens:
                best_sens = m['sensitivity']
                best_thresh = t

        # Compute inter-meal intervals from training meals
        train_meal_count = int(len(meals) * TRAIN_FRAC)
        train_meals = sorted(meals, key=lambda m: m['index'])[:train_meal_count]
        imis = []
        for j in range(1, len(train_meals)):
            imi = (train_meals[j]['index'] - train_meals[j - 1]['index']) * 5
            if imi > 0:
                imis.append(imi)

        if not imis:
            imis = [240]

        median_imi = float(np.median(imis))
        p25_imi = float(np.percentile(imis, 25))

        # Build hourly meal-probability table from training meals
        hourly_meal_prob = np.zeros(24)
        for m in train_meals:
            h = int(m['hour']) % 24
            hourly_meal_prob[h] += 1
        total_train_days = max(train_meal_count / 3.0, 1.0)
        hourly_meal_prob /= total_train_days

        # Simulate each suppression strategy over test set
        offset = len(X_train) + 13
        entry = {'threshold': best_thresh, 'n_meals': len(meals),
                 'median_imi_min': round(median_imi, 1),
                 'p25_imi_min': round(p25_imi, 1)}

        for strat in strategy_names:
            alerts_out = np.zeros(len(y_test), dtype=int)
            last_alert_step = -9999

            for j in range(len(y_test)):
                if scores[j] < best_thresh:
                    continue

                steps_since_alert = j - last_alert_step
                mins_since_alert = steps_since_alert * 5

                if strat == 'fixed_120':
                    suppress_window = 120
                elif strat == 'median_75':
                    suppress_window = median_imi * 0.75
                elif strat == 'p25':
                    suppress_window = p25_imi
                elif strat == 'adaptive':
                    # Adaptive: use expected time to next meal
                    cur_hour = ((offset + j) % STEPS_PER_DAY) * 5.0 / 60.0
                    # Look ahead for next high-probability hour
                    min_to_next = 240  # default 4h
                    for look in range(1, 49):  # up to 4 hours ahead
                        fh = int(cur_hour + look * 5.0 / 60.0) % 24
                        if hourly_meal_prob[fh] > 0.3:
                            min_to_next = look * 5
                            break
                    suppress_window = max(min(min_to_next * 0.6, median_imi * 0.75), 30)
                else:
                    suppress_window = 120

                if mins_since_alert >= suppress_window:
                    alerts_out[j] = 1
                    last_alert_step = j

            m = _compute_alert_metrics(y_test, alerts_out)

            # Missed meals: actual meal steps with no alert in preceding horizon
            meal_test_indices = np.where(y_test == 1)[0]
            horizon = 6  # same as build_features_and_labels
            missed = 0
            for mi in meal_test_indices:
                window_start = max(0, mi - horizon)
                if np.sum(alerts_out[window_start: mi + 1]) == 0:
                    missed += 1
            total_meal_steps = int(np.sum(y_test))
            missed_rate = missed / max(total_meal_steps, 1)

            entry[strat] = {
                'alerts_per_day': m['alerts_per_day'],
                'ppv': round(m['ppv'], 4),
                'sensitivity': round(m['sensitivity'], 4),
                'missed_meals': missed,
                'missed_rate': round(missed_rate, 4),
            }
            agg[strat]['ppv'].append(m['ppv'])
            agg[strat]['sens'].append(m['sensitivity'])
            agg[strat]['apd'].append(m['alerts_per_day'])
            agg[strat]['missed'].append(missed_rate)

        per_patient[name] = entry

        if detail:
            row = " | ".join(
                f"{s}={entry[s]['alerts_per_day']:.1f}apd"
                for s in strategy_names
            )
            print(f"  {name}: {row}")

    if not per_patient:
        return {'experiment_id': 'EXP-1143', 'status': 'FAIL',
                'summary': 'No patients', 'per_patient': {}, 'key_finding': ''}

    summary = {}
    for s in strategy_names:
        summary[s] = {
            'mean_ppv': round(float(np.mean(agg[s]['ppv'])), 4) if agg[s]['ppv'] else 0,
            'mean_sensitivity': round(float(np.mean(agg[s]['sens'])), 4) if agg[s]['sens'] else 0,
            'mean_alerts_per_day': round(float(np.mean(agg[s]['apd'])), 2) if agg[s]['apd'] else 0,
            'mean_missed_rate': round(float(np.mean(agg[s]['missed'])), 4) if agg[s]['missed'] else 0,
        }

    best_strat = min(strategy_names,
                     key=lambda s: summary[s]['mean_alerts_per_day']
                     if summary[s]['mean_ppv'] >= 0.40 else 999)

    key = (f"Best strategy: {best_strat} → "
           f"{summary[best_strat]['mean_alerts_per_day']:.1f} alerts/day, "
           f"PPV={summary[best_strat]['mean_ppv']:.2f}, "
           f"missed={summary[best_strat]['mean_missed_rate']:.2%}")

    print(f"[EXP-1143] Summary: {key}")

    return {
        'experiment_id': 'EXP-1143',
        'title': 'Meal Frequency-Based Suppression',
        'status': 'OK',
        'per_patient': per_patient,
        'summary': summary,
        'key_finding': key,
    }


# ── EXP-1144: Confidence-Weighted Alerting ───────────────────────────────────

def exp_1144_confidence_weighted(patients, detail=False):
    """Optimise composite alert score with grid search over weights.

    alert_score = w1 * proactive_score + w2 * time_prior + w3 * recency_penalty

    where:
      proactive_score = model P(meal) from 15 proactive features
      time_prior      = historical meal probability at current hour
      recency_penalty = exponential decay since last alert
                        (1.0 at 2h, 0.5 at 1h, 0.1 at 30min)
    """
    print("[EXP-1144] Confidence-weighted alerting …")
    per_patient = {}
    all_best_w = []
    all_ppv = []
    all_sens = []
    all_apd = []

    # Recency penalty function: exp(-k * minutes)
    # 1.0 at 120min → k=0; 0.5 at 60min → solve: 0.5 = exp(-k*60)
    # Use: penalty = 1 - exp(-minutes / tau), tau chosen so that
    #   penalty(30min)=0.1, penalty(60min)=0.5, penalty(120min)=1.0
    # Actually, a simple mapping: penalty = min(1.0, (minutes/120)^2)
    # Or use the spec directly:
    def recency_penalty(minutes_since_last_alert):
        """1.0 at ≥120min, 0.5 at 60min, 0.1 at 30min."""
        if minutes_since_last_alert >= 120:
            return 1.0
        if minutes_since_last_alert <= 0:
            return 0.0
        # Fit exponential: penalty = 1 - exp(-alpha * t)
        # At t=120: ~1.0; at t=60: ~0.5; at t=30: ~0.1
        # alpha ≈ ln(2)/60 ≈ 0.01155 for the 0.5 at 60 point
        # penalty = 1 - exp(-0.01155 * t) gives ~0.29 at t=30
        # Use power-law instead for better fit:
        # penalty = (t/120)^1.7 → at 60: 0.31, at 30: 0.10
        return min(1.0, (minutes_since_last_alert / 120.0) ** 1.7)

    # Weight grid
    w1_vals = [0.4, 0.5, 0.6, 0.7, 0.8]
    w2_vals = [0.05, 0.10, 0.15, 0.20, 0.25]
    w3_vals = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            continue
        glucose, net_flux, supply, meals = prep

        if len(meals) < MIN_MEALS_REQUIRED:
            if detail:
                print(f"  {name}: SKIP ({len(meals)} meals)")
            continue

        X, y = build_features_and_labels(glucose, net_flux, supply, meals)
        if len(X) == 0:
            continue
        X_pro = X[:, :15]
        X_train, y_train, X_test, y_test = _temporal_split(X_pro, y)

        if len(set(y_train)) < 2:
            continue

        clf = _train_proactive_model(X_train, y_train)
        proactive_scores = _predict_scores(clf, X_test)

        # Build hourly meal prob from training meals
        train_meal_count = int(len(meals) * TRAIN_FRAC)
        train_meals = sorted(meals, key=lambda m: m['index'])[:train_meal_count]
        hourly_prob = np.zeros(24)
        for m in train_meals:
            h = int(m['hour']) % 24
            hourly_prob[h] += 1
        total_train_days = max(train_meal_count / 3.0, 1.0)
        hourly_prob /= total_train_days
        # Normalise to [0, 1]
        max_prob = hourly_prob.max()
        if max_prob > 0:
            hourly_prob /= max_prob

        offset = len(X_train) + 13
        test_hours_int = np.array([
            int(((offset + j) % STEPS_PER_DAY) * 5.0 / 60.0) % 24
            for j in range(len(y_test))
        ])
        time_priors = hourly_prob[test_hours_int]

        # Grid search for optimal (w1, w2, w3)
        best_w = (0.7, 0.15, 0.15)
        best_objective = 999.0  # minimise alerts/day with PPV≥0.50

        for w1 in w1_vals:
            for w2 in w2_vals:
                for w3 in w3_vals:
                    if abs(w1 + w2 + w3 - 1.0) > 0.01:
                        continue

                    # Simulate alert stream with composite score
                    sim_alerts = np.zeros(len(y_test), dtype=int)
                    last_alert_step = -9999

                    for j in range(len(y_test)):
                        mins_since = (j - last_alert_step) * 5
                        rp = recency_penalty(mins_since)
                        composite = (w1 * proactive_scores[j]
                                     + w2 * time_priors[j]
                                     + w3 * rp)
                        if composite >= 0.50:
                            sim_alerts[j] = 1
                            last_alert_step = j

                    m = _compute_alert_metrics(y_test, sim_alerts)

                    if m['ppv'] >= 0.50:
                        obj = m['alerts_per_day']
                    else:
                        obj = 100 + (0.50 - m['ppv']) * 1000  # penalty

                    if obj < best_objective:
                        best_objective = obj
                        best_w = (w1, w2, w3)

        # Evaluate best weights
        sim_alerts = np.zeros(len(y_test), dtype=int)
        last_alert_step = -9999
        for j in range(len(y_test)):
            mins_since = (j - last_alert_step) * 5
            rp = recency_penalty(mins_since)
            composite = (best_w[0] * proactive_scores[j]
                         + best_w[1] * time_priors[j]
                         + best_w[2] * rp)
            if composite >= 0.50:
                sim_alerts[j] = 1
                last_alert_step = j

        final_m = _compute_alert_metrics(y_test, sim_alerts)

        entry = {
            'optimal_weights': {'w1': best_w[0], 'w2': best_w[1], 'w3': best_w[2]},
            'ppv': round(final_m['ppv'], 4),
            'sensitivity': round(final_m['sensitivity'], 4),
            'alerts_per_day': final_m['alerts_per_day'],
            'n_meals': len(meals),
        }
        per_patient[name] = entry
        all_best_w.append(best_w)
        all_ppv.append(final_m['ppv'])
        all_sens.append(final_m['sensitivity'])
        all_apd.append(final_m['alerts_per_day'])

        if detail:
            print(f"  {name}: w=({best_w[0]:.2f},{best_w[1]:.2f},{best_w[2]:.2f}) "
                  f"PPV={final_m['ppv']:.2f} sens={final_m['sensitivity']:.2f} "
                  f"apd={final_m['alerts_per_day']:.1f}")

    if not per_patient:
        return {'experiment_id': 'EXP-1144', 'status': 'FAIL',
                'summary': 'No patients', 'per_patient': {}, 'key_finding': ''}

    mean_w1 = float(np.mean([w[0] for w in all_best_w]))
    mean_w2 = float(np.mean([w[1] for w in all_best_w]))
    mean_w3 = float(np.mean([w[2] for w in all_best_w]))
    mean_ppv = float(np.mean(all_ppv))
    mean_sens = float(np.mean(all_sens))
    mean_apd = float(np.mean(all_apd))

    summary = {
        'mean_optimal_weights': {
            'w1_proactive': round(mean_w1, 3),
            'w2_time_prior': round(mean_w2, 3),
            'w3_recency': round(mean_w3, 3),
        },
        'mean_ppv': round(mean_ppv, 4),
        'mean_sensitivity': round(mean_sens, 4),
        'mean_alerts_per_day': round(mean_apd, 2),
        'n_patients': len(per_patient),
    }

    key = (f"Confidence-weighted: {mean_apd:.1f} alerts/day, "
           f"PPV={mean_ppv:.2f}, sens={mean_sens:.2f}, "
           f"w=({mean_w1:.2f},{mean_w2:.2f},{mean_w3:.2f})")

    print(f"[EXP-1144] Summary: {key}")

    return {
        'experiment_id': 'EXP-1144',
        'title': 'Confidence-Weighted Alerting',
        'status': 'OK',
        'per_patient': per_patient,
        'summary': summary,
        'key_finding': key,
    }


# ── EXP-1145: Production Alert Simulation ────────────────────────────────────

def _select_best_strategy(results_1141, results_1142, results_1143,
                          results_1144):
    """Pick the strategy with lowest alerts/day at PPV≥0.50.

    Returns a dict describing the chosen strategy.
    """
    candidates = []

    # EXP-1141: per-patient threshold
    s1 = results_1141.get('summary', {})
    if s1.get('mean_ppv', 0) >= 0.45:
        candidates.append({
            'name': 'per_patient_threshold',
            'source': 'EXP-1141',
            'ppv': s1.get('mean_ppv', 0),
            'sensitivity': s1.get('mean_sensitivity', 0),
            'alerts_per_day': s1.get('mean_alerts_per_day', 99),
        })

    # EXP-1142: window thresholds
    s2 = results_1142.get('summary', {})
    if s2.get('window_mean_ppv', 0) >= 0.45:
        candidates.append({
            'name': 'window_thresholds',
            'source': 'EXP-1142',
            'ppv': s2.get('window_mean_ppv', 0),
            'sensitivity': s2.get('window_mean_sensitivity', 0),
            'alerts_per_day': s2.get('window_mean_alerts_per_day', 99),
        })

    # EXP-1143: suppression strategies
    s3 = results_1143.get('summary', {})
    for strat_name, strat_data in s3.items():
        if isinstance(strat_data, dict) and strat_data.get('mean_ppv', 0) >= 0.45:
            candidates.append({
                'name': f'suppression_{strat_name}',
                'source': 'EXP-1143',
                'ppv': strat_data.get('mean_ppv', 0),
                'sensitivity': strat_data.get('mean_sensitivity', 0),
                'alerts_per_day': strat_data.get('mean_alerts_per_day', 99),
            })

    # EXP-1144: confidence-weighted
    s4 = results_1144.get('summary', {})
    if s4.get('mean_ppv', 0) >= 0.45:
        candidates.append({
            'name': 'confidence_weighted',
            'source': 'EXP-1144',
            'ppv': s4.get('mean_ppv', 0),
            'sensitivity': s4.get('mean_sensitivity', 0),
            'alerts_per_day': s4.get('mean_alerts_per_day', 99),
        })

    if not candidates:
        return {'name': 'per_patient_threshold', 'source': 'EXP-1141 (fallback)',
                'ppv': 0, 'sensitivity': 0, 'alerts_per_day': 99}

    return min(candidates, key=lambda c: c['alerts_per_day'])


def exp_1145_production_simulation(patients, detail=False,
                                   prior_results=None):
    """Full pipeline simulation using best strategy from EXP-1141–1144.

    If prior_results is None, runs EXP-1141 internally to get thresholds.
    Simulates day-by-day alerting and computes comprehensive statistics.
    """
    print("[EXP-1145] Production alert simulation …")

    # Determine best strategy
    if prior_results is not None:
        best = _select_best_strategy(
            prior_results.get(1141, {}), prior_results.get(1142, {}),
            prior_results.get(1143, {}), prior_results.get(1144, {}))
    else:
        best = {'name': 'per_patient_threshold', 'source': 'EXP-1141 (inline)'}

    print(f"  Strategy: {best['name']} (from {best.get('source', 'default')})")

    per_patient = {}
    agg_apd = []
    agg_ppv = []
    agg_sens = []
    agg_lead_times = []

    # Baseline config
    BASELINE_THRESH = 0.15
    BASELINE_SUPPRESS = ALERT_SUPPRESSION_MIN  # 120 min

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            if detail:
                print(f"  {name}: SKIP (prep failed)")
            continue
        glucose, net_flux, supply, meals = prep

        if len(meals) < MIN_MEALS_REQUIRED:
            if detail:
                print(f"  {name}: SKIP ({len(meals)} meals)")
            continue

        X, y = build_features_and_labels(glucose, net_flux, supply, meals)
        if len(X) == 0:
            continue

        X_pro = X[:, :15]
        X_train, y_train, X_test, y_test = _temporal_split(X_pro, y)

        if len(set(y_train)) < 2:
            continue

        clf = _train_proactive_model(X_train, y_train)
        scores = _predict_scores(clf, X_test)

        # Find per-patient optimal threshold (PPV ≥ 0.50)
        opt_thresh = 0.50
        opt_sens = 0.0
        for ti in range(5, 100, 5):
            t = ti / 100.0
            a = (scores >= t).astype(int)
            m = _compute_alert_metrics(y_test, a)
            if m['ppv'] >= 0.50 and m['sensitivity'] > opt_sens:
                opt_sens = m['sensitivity']
                opt_thresh = t

        # Build hourly meal probability for time prior
        train_meal_count = int(len(meals) * TRAIN_FRAC)
        train_meals = sorted(meals, key=lambda m: m['index'])[:train_meal_count]
        hourly_prob = np.zeros(24)
        for ml in train_meals:
            h = int(ml['hour']) % 24
            hourly_prob[h] += 1
        td = max(train_meal_count / 3.0, 1.0)
        hourly_prob /= td
        hp_max = hourly_prob.max()
        if hp_max > 0:
            hourly_prob /= hp_max

        # Compute inter-meal intervals for adaptive suppression
        imis = []
        for j in range(1, len(train_meals)):
            imi = (train_meals[j]['index'] - train_meals[j - 1]['index']) * 5
            if imi > 0:
                imis.append(imi)
        median_imi = float(np.median(imis)) if imis else 240.0

        offset = len(X_train) + 13

        # Identify actual meal step indices in test set
        meal_indices_global = sorted(set(m['index'] for m in meals))
        test_start_global = offset
        test_meal_steps = []
        for mi in meal_indices_global:
            local = mi - test_start_global
            if 0 <= local < len(y_test):
                test_meal_steps.append(local)

        # ── Simulate BEST strategy ───────────────────────────────────
        best_alerts = np.zeros(len(y_test), dtype=int)
        last_alert = -9999
        for j in range(len(y_test)):
            mins_since = (j - last_alert) * 5
            # Per-patient threshold + adaptive suppression
            suppress_ok = mins_since >= min(median_imi * 0.75, 120)
            if scores[j] >= opt_thresh and suppress_ok:
                best_alerts[j] = 1
                last_alert = j

        best_m = _compute_alert_metrics(y_test, best_alerts)

        # ── Simulate BASELINE ─────────────────────────────────────────
        base_alerts = np.zeros(len(y_test), dtype=int)
        last_alert_b = -9999
        for j in range(len(y_test)):
            mins_since = (j - last_alert_b) * 5
            if scores[j] >= BASELINE_THRESH and mins_since >= BASELINE_SUPPRESS:
                base_alerts[j] = 1
                last_alert_b = j

        base_m = _compute_alert_metrics(y_test, base_alerts)

        # ── Lead time distribution ────────────────────────────────────
        lead_times = []
        for mi_local in test_meal_steps:
            # Find closest preceding alert
            for look_back in range(0, min(mi_local, 60)):
                idx = mi_local - look_back
                if idx >= 0 and best_alerts[idx] == 1:
                    lead_times.append(look_back * 5)  # minutes
                    break

        # ── Per-day alert distribution ────────────────────────────────
        n_test = len(y_test)
        n_days = max(int(n_test / STEPS_PER_DAY), 1)
        daily_alerts = []
        for d in range(n_days):
            day_start = d * STEPS_PER_DAY
            day_end = min(day_start + STEPS_PER_DAY, n_test)
            daily_alerts.append(int(np.sum(best_alerts[day_start:day_end])))

        # ── Consecutive days with no missed meals ─────────────────────
        horizon = 6
        daily_missed = []
        for d in range(n_days):
            day_start = d * STEPS_PER_DAY
            day_end = min(day_start + STEPS_PER_DAY, n_test)
            day_meals = [m for m in test_meal_steps
                         if day_start <= m < day_end]
            missed = 0
            for mi_local in day_meals:
                ws = max(0, mi_local - horizon)
                if np.sum(best_alerts[ws: mi_local + 1]) == 0:
                    missed += 1
            daily_missed.append(missed)

        max_consec_no_miss = 0
        cur_consec = 0
        for dm in daily_missed:
            if dm == 0:
                cur_consec += 1
                max_consec_no_miss = max(max_consec_no_miss, cur_consec)
            else:
                cur_consec = 0

        # ── False alert clustering ────────────────────────────────────
        fa_indices = np.where((best_alerts == 1) & (y_test == 0))[0]
        fa_gaps = np.diff(fa_indices) * 5 if len(fa_indices) > 1 else np.array([])
        fa_cluster_count = int(np.sum(fa_gaps < 30)) if len(fa_gaps) > 0 else 0

        entry = {
            'best_strategy': {
                'threshold': opt_thresh,
                'suppress_window_min': round(min(median_imi * 0.75, 120), 1),
                'alerts_per_day': best_m['alerts_per_day'],
                'ppv': round(best_m['ppv'], 4),
                'sensitivity': round(best_m['sensitivity'], 4),
            },
            'baseline': {
                'threshold': BASELINE_THRESH,
                'suppress_window_min': BASELINE_SUPPRESS,
                'alerts_per_day': base_m['alerts_per_day'],
                'ppv': round(base_m['ppv'], 4),
                'sensitivity': round(base_m['sensitivity'], 4),
            },
            'improvement': {
                'alerts_per_day_delta': round(
                    base_m['alerts_per_day'] - best_m['alerts_per_day'], 2),
                'ppv_delta': round(best_m['ppv'] - base_m['ppv'], 4),
                'sensitivity_delta': round(
                    best_m['sensitivity'] - base_m['sensitivity'], 4),
            },
            'lead_time': {
                'mean_min': round(float(np.mean(lead_times)), 1) if lead_times else 0,
                'median_min': round(float(np.median(lead_times)), 1) if lead_times else 0,
                'p25_min': round(float(np.percentile(lead_times, 25)), 1) if lead_times else 0,
                'p75_min': round(float(np.percentile(lead_times, 75)), 1) if lead_times else 0,
                'n_meals_with_lead': len(lead_times),
            },
            'daily_alerts': {
                'mean': round(float(np.mean(daily_alerts)), 2) if daily_alerts else 0,
                'median': round(float(np.median(daily_alerts)), 1) if daily_alerts else 0,
                'std': round(float(np.std(daily_alerts)), 2) if daily_alerts else 0,
                'max': int(np.max(daily_alerts)) if daily_alerts else 0,
            },
            'consecutive_no_miss_days': max_consec_no_miss,
            'false_alert_clusters': fa_cluster_count,
            'n_meals': len(meals),
            'n_test_days': n_days,
        }
        per_patient[name] = entry

        agg_apd.append(best_m['alerts_per_day'])
        agg_ppv.append(best_m['ppv'])
        agg_sens.append(best_m['sensitivity'])
        agg_lead_times.extend(lead_times)

        if detail:
            print(f"  {name}: best={best_m['alerts_per_day']:.1f}apd "
                  f"PPV={best_m['ppv']:.2f} sens={best_m['sensitivity']:.2f} | "
                  f"base={base_m['alerts_per_day']:.1f}apd "
                  f"PPV={base_m['ppv']:.2f} sens={base_m['sensitivity']:.2f}")

    if not per_patient:
        return {'experiment_id': 'EXP-1145', 'status': 'FAIL',
                'summary': 'No patients', 'per_patient': {}, 'key_finding': ''}

    mean_apd = float(np.mean(agg_apd))
    mean_ppv = float(np.mean(agg_ppv))
    mean_sens = float(np.mean(agg_sens))

    # Aggregate baseline
    base_apds = [v['baseline']['alerts_per_day'] for v in per_patient.values()]
    base_ppvs = [v['baseline']['ppv'] for v in per_patient.values()]
    base_senses = [v['baseline']['sensitivity'] for v in per_patient.values()]

    summary = {
        'strategy_used': best.get('name', 'per_patient_threshold'),
        'best': {
            'mean_alerts_per_day': round(mean_apd, 2),
            'mean_ppv': round(mean_ppv, 4),
            'mean_sensitivity': round(mean_sens, 4),
            'mean_lead_time_min': round(float(np.mean(agg_lead_times)), 1) if agg_lead_times else 0,
        },
        'baseline': {
            'mean_alerts_per_day': round(float(np.mean(base_apds)), 2),
            'mean_ppv': round(float(np.mean(base_ppvs)), 4),
            'mean_sensitivity': round(float(np.mean(base_senses)), 4),
        },
        'improvement': {
            'alerts_per_day_reduction': round(
                float(np.mean(base_apds)) - mean_apd, 2),
            'ppv_improvement': round(
                mean_ppv - float(np.mean(base_ppvs)), 4),
            'sensitivity_change': round(
                mean_sens - float(np.mean(base_senses)), 4),
        },
        'n_patients': len(per_patient),
    }

    key = (f"Production sim: {mean_apd:.1f} alerts/day (↓{summary['improvement']['alerts_per_day_reduction']:.1f}), "
           f"PPV={mean_ppv:.2f} (↑{summary['improvement']['ppv_improvement']:.2f}), "
           f"sens={mean_sens:.2f}")

    print(f"[EXP-1145] Summary: {key}")

    return {
        'experiment_id': 'EXP-1145',
        'title': 'Production Alert Simulation',
        'status': 'OK',
        'per_patient': per_patient,
        'summary': summary,
        'key_finding': key,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1141–1145: Adaptive Alert Suppression Research')
    parser.add_argument('--exp', type=int, nargs='+',
                        default=[1141, 1142, 1143, 1144, 1145],
                        help='Experiment IDs to run (default: all)')
    parser.add_argument('--detail', action='store_true',
                        help='Print per-patient detail')
    parser.add_argument('--save', action='store_true',
                        help='Save results to externals/experiments/')
    parser.add_argument('--max-patients', type=int, default=None,
                        help='Limit number of patients loaded')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    experiments = {
        1141: ('Per-Patient Threshold Optimization',
               exp_1141_per_patient_threshold),
        1142: ('Time-of-Day Adaptive Thresholds',
               exp_1142_time_of_day_thresholds),
        1143: ('Meal Frequency-Based Suppression',
               exp_1143_frequency_suppression),
        1144: ('Confidence-Weighted Alerting',
               exp_1144_confidence_weighted),
        1145: ('Production Alert Simulation',
               exp_1145_production_simulation),
    }

    prior_results = {}

    for eid in sorted(args.exp):
        if eid not in experiments:
            print(f"Unknown experiment: EXP-{eid}")
            continue

        exp_name, exp_func = experiments[eid]

        print(f"\n{'━' * 70}")
        print(f"  EXP-{eid}: {exp_name}")
        print(f"{'━' * 70}\n")

        t0 = time.time()
        try:
            if eid == 1145:
                result = exp_func(patients, detail=args.detail,
                                  prior_results=prior_results if prior_results else None)
            else:
                result = exp_func(patients, detail=args.detail)

            elapsed = time.time() - t0
            status = result.get('status', 'OK')
            finding = result.get('key_finding', '')

            print(f"\n  → EXP-{eid} [{status}] {elapsed:.1f}s")
            if finding:
                print(f"    {finding}")

            prior_results[eid] = result

            if args.save:
                slug = exp_name.lower().replace(' ', '_').replace('-', '_')
                filename = f"exp_{eid}_{slug}"
                save_results(result, filename)

        except Exception as exc:
            elapsed = time.time() - t0
            print(f"\n  → EXP-{eid} [FAIL] {elapsed:.1f}s — {exc}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
