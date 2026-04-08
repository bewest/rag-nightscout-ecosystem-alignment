#!/usr/bin/env python3
"""EXP-1111 to EXP-1118: Meal Prediction Deep-Dive — Ablation, Thresholds & Head-to-Head.

Building on the EXP-1101–1110 campaign (AUC=0.861, 11 patients, personal models win 10/11):
- Binary meal periodicity is weak (ACF=0.003)
- Phase jitter ~35 min per meal window
- Carb logging delay = 100 min (physics detection is the ground truth)
- Features: hour_sin/cos, time_since_meal, meals_today, day_of_week,
            glucose_trend_15/30, glucose, net_flux, hist_meal_prob

This batch deepens the analysis with:
  EXP-1111: Feature Ablation ★★★
  EXP-1112: Threshold Optimization ★★★
  EXP-1113: Cold Start / Online Learning ★★★
  EXP-1114: Smoothed Periodicity (Kernel Density) ★★★
  EXP-1115: Conditional Inter-Meal Interval ★★★
  EXP-1116: Alert Fatigue Simulation ★★
  EXP-1117: Glucose-Aware Prediction ★★★
  EXP-1118: ML vs Gaussian Head-to-Head ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_meal_periodicity_1111 --detail --save
    PYTHONPATH=tools python -m cgmencode.exp_meal_periodicity_1111 --exp 1111
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import argparse
import time
import warnings
from collections import defaultdict

import numpy as np
from scipy import stats

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_flux import load_patients, save_results
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = str(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'externals', 'ns-data', 'patients'))

STEPS_PER_DAY = 288
GLUCOSE_SCALE = 400.0

FEATURE_NAMES = [
    'hour_sin', 'hour_cos', 'time_since_meal', 'meals_today',
    'day_of_week', 'glucose_trend_15', 'glucose_trend_30',
    'glucose', 'net_flux', 'hist_meal_prob',
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def detect_meals_from_physics(df, sd, threshold=0.15):
    """Detect meals from supply-demand physics residuals."""
    net = sd['net']
    N = len(net)
    meals = []
    in_burst = False
    burst_start = None
    burst_integral = 0

    for i in range(N):
        if net[i] > threshold and not in_burst:
            in_burst = True
            burst_start = i
            burst_integral = net[i]
        elif net[i] > threshold and in_burst:
            burst_integral += net[i]
        elif in_burst:
            in_burst = False
            duration = (i - burst_start) * 5  # minutes
            if duration >= 15 and burst_integral > 1.0:
                hour = (burst_start % STEPS_PER_DAY) * 5.0 / 60.0
                # Check for matching carb entry
                carb_col = 'carbs' if 'carbs' in df.columns else None
                announced = False
                if carb_col:
                    window = slice(max(0, burst_start - 12), min(N, i + 12))
                    announced = bool(df[carb_col].iloc[window].sum() > 0)
                meals.append({
                    'step': burst_start,
                    'hour': hour,
                    'duration_min': duration,
                    'integral': burst_integral,
                    'announced': announced,
                })
    return meals


def assign_meal_window(hour):
    """Assign a meal to breakfast/lunch/dinner/snack window."""
    if 5.0 <= hour < 10.0:
        return 'breakfast'
    elif 10.0 <= hour < 14.0:
        return 'lunch'
    elif 17.0 <= hour < 21.0:
        return 'dinner'
    else:
        return 'snack'


def build_features_and_labels(df, sd, meals, horizon_min=30):
    """Build the 10-feature matrix and binary label used by EXP-1106.

    Returns (features, labels, split_idx) where split_idx is the 80% point.
    """
    N = len(df)
    glucose = df['glucose'].values

    # Meal step lookup
    meal_steps = sorted(set(m['step'] for m in meals))

    # Next-meal distance
    next_meal_dist = np.full(N, 9999, dtype=np.float32)
    for ms in reversed(meal_steps):
        for i in range(max(0, ms - STEPS_PER_DAY), ms):
            dist = (ms - i) * 5
            if dist < next_meal_dist[i]:
                next_meal_dist[i] = dist

    # Previous-meal distance
    prev_meal_dist = np.full(N, 9999, dtype=np.float32)
    for ms in meal_steps:
        for i in range(ms, min(N, ms + STEPS_PER_DAY)):
            d = (i - ms) * 5.0
            if d < prev_meal_dist[i]:
                prev_meal_dist[i] = d

    # Meals so far today
    meals_today = np.zeros(N)
    current_day = -1
    count = 0
    meal_set = set(meal_steps)
    for i in range(N):
        day = i // STEPS_PER_DAY
        if day != current_day:
            current_day = day
            count = 0
        if i in meal_set:
            count += 1
        meals_today[i] = count

    # Historical meal probability (from training portion)
    split = int(N * 0.8)
    train_meals = [m for m in meals if m['step'] < split]
    hour_hist = np.zeros(24)
    for m in train_meals:
        h = int(m['hour']) % 24
        hour_hist[h] += 1
    if hour_hist.sum() > 0:
        hour_hist = hour_hist / hour_hist.sum()

    # Build features
    features = np.zeros((N, 10))
    for i in range(N):
        hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
        features[i, 0] = np.sin(2 * np.pi * hour / 24)
        features[i, 1] = np.cos(2 * np.pi * hour / 24)
        features[i, 2] = prev_meal_dist[i]
        features[i, 3] = meals_today[i]
        features[i, 4] = (i // STEPS_PER_DAY) % 7
        if i >= 3:
            features[i, 5] = glucose[i] - glucose[i - 3]
        if i >= 6:
            features[i, 6] = glucose[i] - glucose[i - 6]
        features[i, 7] = glucose[i] / GLUCOSE_SCALE
        features[i, 8] = sd['net'][i] if i < len(sd['net']) else 0
        h_idx = int(hour) % 24
        features[i, 9] = hour_hist[h_idx]

    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    labels = (next_meal_dist <= horizon_min).astype(int)

    return features, labels, split, next_meal_dist, meal_steps, hour_hist


def train_model(X_train, y_train):
    """Train the canonical EXP-1106 GradientBoostingClassifier."""
    from sklearn.ensemble import GradientBoostingClassifier
    clf = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, random_state=42)
    clf.fit(X_train, y_train)
    return clf


def safe_auc(y_true, y_score):
    """Compute ROC AUC safely, returning 0.5 if degenerate."""
    from sklearn.metrics import roc_auc_score
    if len(np.unique(y_true)) < 2:
        return 0.5
    try:
        return roc_auc_score(y_true, y_score)
    except ValueError:
        return 0.5


# ═══════════════════════════════════════════════════════════════════════
# EXP-1111: Feature Ablation
# ═══════════════════════════════════════════════════════════════════════

def exp_1111_feature_ablation(patients, detail=False):
    """Drop-one-out and group ablation to identify critical features.

    1. Drop each of the 10 features one-at-a-time; measure AUC drop.
    2. Group ablation: time-only, glucose-only, physics-only, combinations.
    """
    from sklearn.ensemble import GradientBoostingClassifier

    GROUP_DEFS = {
        'time_only':     [0, 1, 2, 3, 4, 9],     # sin, cos, time_since, meals_today, dow, hist_prob
        'glucose_only':  [5, 6, 7],               # trend_15, trend_30, glucose
        'physics_only':  [8],                      # net_flux
        'time+glucose':  [0, 1, 2, 3, 4, 5, 6, 7, 9],
        'time+physics':  [0, 1, 2, 3, 4, 8, 9],
    }

    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, *_ = build_features_and_labels(df, sd, meals)
        X_tr, X_va = features[:split], features[split:]
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # --- Full model baseline ---
        clf_full = train_model(X_tr, y_tr)
        proba_full = clf_full.predict_proba(X_va)[:, 1]
        auc_full = safe_auc(y_va, proba_full)

        # --- Drop-one-out ---
        drop_one = {}
        for fi in range(10):
            X_tr_drop = np.delete(X_tr, fi, axis=1)
            X_va_drop = np.delete(X_va, fi, axis=1)
            clf_d = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42)
            clf_d.fit(X_tr_drop, y_tr)
            proba_d = clf_d.predict_proba(X_va_drop)[:, 1]
            auc_d = safe_auc(y_va, proba_d)
            drop_one[FEATURE_NAMES[fi]] = {
                'auc_without': round(auc_d, 4),
                'auc_drop': round(auc_full - auc_d, 4),
            }

        # --- Group ablation ---
        group_results = {}
        for gname, idx_list in GROUP_DEFS.items():
            X_tr_g = X_tr[:, idx_list]
            X_va_g = X_va[:, idx_list]
            clf_g = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42)
            clf_g.fit(X_tr_g, y_tr)
            proba_g = clf_g.predict_proba(X_va_g)[:, 1]
            auc_g = safe_auc(y_va, proba_g)
            group_results[gname] = {
                'auc': round(auc_g, 4),
                'auc_diff_vs_full': round(auc_g - auc_full, 4),
                'n_features': len(idx_list),
            }

        # Most impactful single feature to drop
        worst_drop = max(drop_one.items(), key=lambda x: x[1]['auc_drop'])

        per_patient[name] = {
            'auc_full': round(auc_full, 4),
            'drop_one': drop_one,
            'groups': group_results,
            'most_impactful_feature': worst_drop[0],
            'most_impactful_drop': worst_drop[1]['auc_drop'],
        }

        summary_rows.append({
            'patient': name,
            'full': auc_full,
            'top_feat': worst_drop[0],
            'top_drop': worst_drop[1]['auc_drop'],
            'time': group_results['time_only']['auc'],
            'gluc': group_results['glucose_only']['auc'],
            'phys': group_results['physics_only']['auc'],
        })

    # --- Aggregate ---
    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    # Mean AUC drop per feature across patients
    feat_drops = defaultdict(list)
    for pr in per_patient.values():
        if 'drop_one' in pr:
            for fn, vals in pr['drop_one'].items():
                feat_drops[fn].append(vals['auc_drop'])
    mean_drops = {fn: round(float(np.mean(v)), 4) for fn, v in feat_drops.items()}
    sorted_drops = sorted(mean_drops.items(), key=lambda x: x[1], reverse=True)

    print(f"\n{'='*75}")
    print(f"EXP-1111: Feature Ablation")
    print(f"{'='*75}")
    print(f"\n--- Drop-One-Out (mean AUC drop across patients) ---")
    print(f"{'Feature':>20s} {'Mean ΔAUC':>10s}")
    print('-' * 32)
    for fn, drop in sorted_drops:
        print(f"{fn:>20s} {drop:+10.4f}")

    print(f"\n--- Per-Patient Summary ---")
    print(f"{'Patient':>8s} {'Full':>7s} {'Top Feature':>18s} {'Drop':>7s} "
          f"{'Time':>6s} {'Gluc':>6s} {'Phys':>6s}")
    print('-' * 75)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['full']:7.4f} {row['top_feat']:>18s} "
              f"{row['top_drop']:+7.4f} {row['time']:6.4f} {row['gluc']:6.4f} "
              f"{row['phys']:6.4f}")

    mean_full = float(np.mean([r['full'] for r in summary_rows]))
    top_feat = sorted_drops[0][0] if sorted_drops else 'N/A'

    return {
        'status': 'OK',
        'summary': f'Mean AUC={mean_full:.4f}; most impactful feature: '
                   f'{top_feat} (ΔAUC={sorted_drops[0][1]:+.4f})',
        'results': per_patient,
        'mean_auc_full': round(mean_full, 4),
        'feature_ranking': sorted_drops,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1112: Threshold Optimization
# ═══════════════════════════════════════════════════════════════════════

def exp_1112_threshold_optimization(patients, detail=False):
    """Sweep classifier thresholds to find the deployment sweet spot.

    Constraints: max 3 alerts/day, precision ≥ 0.5.
    Metrics per threshold: alerts/day, precision, recall, F1, lead_time.
    """
    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, next_meal_dist, meal_steps, _ = \
            build_features_and_labels(df, sd, meals)
        X_tr, X_va = features[:split], features[split:]
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        clf = train_model(X_tr, y_tr)
        proba = clf.predict_proba(X_va)[:, 1]

        val_days = max(1, (len(X_va)) / STEPS_PER_DAY)
        meal_steps_val = sorted([ms for ms in meal_steps if ms >= split])

        thresholds = np.arange(0.1, 0.91, 0.05)
        sweep = []

        for t in thresholds:
            pred = (proba >= t).astype(int)
            n_alerts = int(pred.sum())
            alerts_per_day = n_alerts / val_days

            tp = int(((pred == 1) & (y_va == 1)).sum())
            fp = int(((pred == 1) & (y_va == 0)).sum())
            fn = int(((pred == 0) & (y_va == 1)).sum())

            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

            # Lead time: for each val-set meal, find earliest alert within 60 min before
            lead_times = []
            for ms in meal_steps_val:
                vi = ms - split
                for offset in range(min(12, vi)):
                    check = vi - offset - 1
                    if 0 <= check < len(pred) and pred[check]:
                        lead_times.append((offset + 1) * 5)
                        break
            mean_lead = float(np.mean(lead_times)) if lead_times else 0.0

            sweep.append({
                'threshold': round(float(t), 2),
                'alerts_per_day': round(alerts_per_day, 2),
                'precision': round(prec, 4),
                'recall': round(rec, 4),
                'f1': round(f1, 4),
                'lead_time_min': round(mean_lead, 1),
            })

        # Find sweet spot: max F1 where alerts/day ≤ 3 and precision ≥ 0.5
        candidates = [s for s in sweep
                      if s['alerts_per_day'] <= 3.0 and s['precision'] >= 0.5]
        if candidates:
            optimal = max(candidates, key=lambda s: s['f1'])
        else:
            # Relax: just best F1
            optimal = max(sweep, key=lambda s: s['f1'])

        per_patient[name] = {
            'sweep': sweep,
            'optimal': optimal,
        }

        summary_rows.append({
            'patient': name,
            'opt_t': optimal['threshold'],
            'a/d': optimal['alerts_per_day'],
            'prec': optimal['precision'],
            'rec': optimal['recall'],
            'f1': optimal['f1'],
            'lead': optimal['lead_time_min'],
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*75}")
    print(f"EXP-1112: Threshold Optimization")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'Thresh':>7s} {'A/day':>6s} {'Prec':>6s} "
          f"{'Rec':>6s} {'F1':>6s} {'Lead':>6s}")
    print('-' * 55)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['opt_t']:7.2f} {row['a/d']:6.2f} "
              f"{row['prec']:6.4f} {row['rec']:6.4f} {row['f1']:6.4f} "
              f"{row['lead']:6.1f}")

    mean_thresh = float(np.mean([r['opt_t'] for r in summary_rows]))
    mean_f1 = float(np.mean([r['f1'] for r in summary_rows]))
    mean_lead = float(np.mean([r['lead'] for r in summary_rows]))

    print(f"\nMean optimal threshold: {mean_thresh:.2f}")
    print(f"Mean F1 at sweet spot: {mean_f1:.4f}")
    print(f"Mean lead time: {mean_lead:.1f} min")

    return {
        'status': 'OK',
        'summary': f'Mean optimal thresh={mean_thresh:.2f}, F1={mean_f1:.4f}, '
                   f'lead={mean_lead:.1f}min',
        'results': per_patient,
        'mean_optimal_threshold': round(mean_thresh, 2),
        'mean_f1': round(mean_f1, 4),
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1113: Cold Start / Online Learning
# ═══════════════════════════════════════════════════════════════════════

def exp_1113_cold_start(patients, detail=False):
    """Train on first N days, evaluate on next 30 days.

    N = 3, 7, 14, 30, 60, 90, full.
    Also compare XGBoost vs per-window Gaussian at each training size.
    Key question: at what day count does ML exceed Gaussian?
    """
    from sklearn.ensemble import GradientBoostingClassifier

    TRAIN_DAYS = [3, 7, 14, 30, 60, 90]
    EVAL_WINDOW_DAYS = 30

    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        total_days = len(df) // STEPS_PER_DAY
        if len(meals) < 30 or total_days < 40:
            per_patient[name] = {'status': 'insufficient_data'}
            continue

        N = len(df)
        glucose = df['glucose'].values
        meal_steps = sorted(set(m['step'] for m in meals))

        # Pre-compute reusable arrays
        next_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in reversed(meal_steps):
            for i in range(max(0, ms - STEPS_PER_DAY), ms):
                dist = (ms - i) * 5
                if dist < next_meal_dist[i]:
                    next_meal_dist[i] = dist

        prev_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in meal_steps:
            for i in range(ms, min(N, ms + STEPS_PER_DAY)):
                d = (i - ms) * 5.0
                if d < prev_meal_dist[i]:
                    prev_meal_dist[i] = d

        meals_today_arr = np.zeros(N)
        current_day = -1
        cnt = 0
        meal_set = set(meal_steps)
        for i in range(N):
            day = i // STEPS_PER_DAY
            if day != current_day:
                current_day = day
                cnt = 0
            if i in meal_set:
                cnt += 1
            meals_today_arr[i] = cnt

        labels = (next_meal_dist <= 30).astype(int)

        curves = []
        crossover_day = None

        all_train_days = TRAIN_DAYS + [total_days]  # include 'full'
        for n_days in all_train_days:
            if n_days > total_days:
                continue

            train_end = n_days * STEPS_PER_DAY
            eval_start = train_end
            eval_end = min(N, eval_start + EVAL_WINDOW_DAYS * STEPS_PER_DAY)
            if eval_end - eval_start < STEPS_PER_DAY:
                continue

            # Build hour_hist from training portion
            train_meals_local = [m for m in meals if m['step'] < train_end]
            hour_hist = np.zeros(24)
            for m in train_meals_local:
                h = int(m['hour']) % 24
                hour_hist[h] += 1
            if hour_hist.sum() > 0:
                hour_hist = hour_hist / hour_hist.sum()

            # Build features for full range
            def build_feat_row(i):
                row = np.zeros(10)
                hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
                row[0] = np.sin(2 * np.pi * hour / 24)
                row[1] = np.cos(2 * np.pi * hour / 24)
                row[2] = prev_meal_dist[i]
                row[3] = meals_today_arr[i]
                row[4] = (i // STEPS_PER_DAY) % 7
                if i >= 3:
                    row[5] = glucose[i] - glucose[i - 3]
                if i >= 6:
                    row[6] = glucose[i] - glucose[i - 6]
                row[7] = glucose[i] / GLUCOSE_SCALE
                row[8] = sd['net'][i] if i < len(sd['net']) else 0
                row[9] = hour_hist[int(hour) % 24]
                return row

            X_tr = np.array([build_feat_row(i) for i in range(train_end)])
            X_va = np.array([build_feat_row(i) for i in range(eval_start, eval_end)])
            y_tr = labels[:train_end]
            y_va = labels[eval_start:eval_end]

            X_tr = np.nan_to_num(X_tr, nan=0.0, posinf=0.0, neginf=0.0)
            X_va = np.nan_to_num(X_va, nan=0.0, posinf=0.0, neginf=0.0)

            if y_tr.sum() < 5 or y_va.sum() < 3:
                continue

            # --- XGBoost ---
            clf = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42)
            clf.fit(X_tr, y_tr)
            ml_proba = clf.predict_proba(X_va)[:, 1]
            ml_auc = safe_auc(y_va, ml_proba)

            # --- Per-window Gaussian baseline ---
            window_stats_g = defaultdict(list)
            for m in train_meals_local:
                w = assign_meal_window(m['hour'])
                window_stats_g[w].append(m['hour'])

            gauss_params = {}
            for w, hours in window_stats_g.items():
                if len(hours) >= 3:
                    gauss_params[w] = (float(np.mean(hours)), max(float(np.std(hours)), 0.5))

            gauss_proba = np.zeros(len(X_va))
            for j in range(len(X_va)):
                idx = eval_start + j
                hour = (idx % STEPS_PER_DAY) * 5.0 / 60.0
                best_p = 0.0
                for w, (mu, sigma) in gauss_params.items():
                    p = stats.norm.pdf(hour, mu, sigma)
                    if p > best_p:
                        best_p = p
                gauss_proba[j] = best_p
            # Normalize to [0, 1]
            if gauss_proba.max() > 0:
                gauss_proba = gauss_proba / gauss_proba.max()

            gauss_auc = safe_auc(y_va, gauss_proba)

            label = n_days if n_days < total_days else 'full'
            curves.append({
                'train_days': label,
                'ml_auc': round(ml_auc, 4),
                'gauss_auc': round(gauss_auc, 4),
                'ml_wins': ml_auc > gauss_auc,
                'n_train_meals': len(train_meals_local),
                'n_val_positives': int(y_va.sum()),
            })

            if crossover_day is None and ml_auc > gauss_auc and isinstance(label, int):
                crossover_day = label

        per_patient[name] = {
            'curves': curves,
            'crossover_day': crossover_day,
        }

        # Find full-data ML AUC for summary
        full_ml = [c['ml_auc'] for c in curves if c['train_days'] == 'full']
        full_ml_auc = full_ml[0] if full_ml else 0.0

        summary_rows.append({
            'patient': name,
            'crossover': crossover_day if crossover_day else '>90',
            'full_ml': full_ml_auc,
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*75}")
    print(f"EXP-1113: Cold Start / Online Learning")
    print(f"{'='*75}")

    # Print learning curves for first patient as example
    if detail:
        for name, pr in per_patient.items():
            if 'curves' not in pr:
                continue
            print(f"\n  {name}:")
            print(f"  {'Days':>6s} {'ML_AUC':>7s} {'Gauss':>7s} {'ML>G?':>6s}")
            print(f"  {'-'*30}")
            for c in pr['curves']:
                win = '✓' if c['ml_wins'] else ''
                print(f"  {str(c['train_days']):>6s} {c['ml_auc']:7.4f} "
                      f"{c['gauss_auc']:7.4f} {win:>6s}")

    print(f"\n--- Crossover Summary ---")
    print(f"{'Patient':>8s} {'Crossover':>10s} {'Full ML AUC':>11s}")
    print('-' * 32)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {str(row['crossover']):>10s} {row['full_ml']:11.4f}")

    crossover_vals = [r['crossover'] for r in summary_rows
                      if isinstance(r['crossover'], int)]
    median_crossover = int(np.median(crossover_vals)) if crossover_vals else None

    return {
        'status': 'OK',
        'summary': f'Median ML>Gaussian crossover: {median_crossover} days; '
                   f'{len(crossover_vals)}/{len(summary_rows)} patients cross over',
        'results': per_patient,
        'median_crossover_days': median_crossover,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1114: Smoothed Periodicity (Kernel Density)
# ═══════════════════════════════════════════════════════════════════════

def exp_1114_smoothed_periodicity(patients, detail=False):
    """Von Mises kernel density on circular meal hours.

    - Shannon entropy of KDE → low = highly periodic
    - Compare with EXP-1101 binary ACF
    - Week-to-week KDE cross-correlation for stability
    """
    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        meal_hours = np.array([m['hour'] for m in meals])
        # Convert hours to radians for circular statistics
        meal_radians = meal_hours * 2 * np.pi / 24.0

        # --- Von Mises KDE ---
        # Evaluate density on a fine grid
        grid_hours = np.linspace(0, 24, 288)
        grid_rad = grid_hours * 2 * np.pi / 24.0

        # Estimate concentration parameter κ via MLE
        # For a mixture, use a moderate bandwidth
        kappa = 3.0  # moderate concentration (~1h bandwidth)

        kde_vals = np.zeros(len(grid_hours))
        for mr in meal_radians:
            # von Mises PDF: exp(kappa * cos(x - mu)) / (2π I0(kappa))
            kde_vals += np.exp(kappa * np.cos(grid_rad - mr))
        kde_vals /= (len(meal_radians) * 2 * np.pi *
                     float(np.i0(kappa)))  # type: ignore[attr-defined]

        # Normalize to proper density
        dx = 24.0 / len(grid_hours)
        total_area = kde_vals.sum() * dx
        if total_area > 0:
            kde_vals = kde_vals / total_area

        # --- Shannon entropy ---
        kde_nonzero = kde_vals[kde_vals > 0]
        entropy = -float(np.sum(kde_nonzero * np.log2(kde_nonzero) * dx))
        # Maximum entropy for uniform = log2(24) ≈ 4.585
        max_entropy = np.log2(24.0)
        normalized_entropy = entropy / max_entropy  # 0=peaked, 1=uniform

        # --- Peak detection ---
        peaks = []
        for i in range(1, len(kde_vals) - 1):
            if kde_vals[i] > kde_vals[i - 1] and kde_vals[i] > kde_vals[i + 1]:
                if kde_vals[i] > np.mean(kde_vals) * 1.5:
                    peaks.append({
                        'hour': round(grid_hours[i], 2),
                        'density': round(float(kde_vals[i]), 4),
                    })

        # --- Binary ACF for comparison (same as EXP-1101) ---
        N_sig = len(df)
        meal_signal = np.zeros(N_sig)
        for m in meals:
            idx = m['step']
            if 0 <= idx < N_sig:
                meal_signal[idx] = 1.0

        centered = meal_signal - meal_signal.mean()
        fft_size = 1
        while fft_size < 2 * N_sig:
            fft_size *= 2
        fft_x = np.fft.rfft(centered, n=fft_size)
        acf_full = np.fft.irfft(fft_x * np.conj(fft_x))
        acf = acf_full[:N_sig]
        acf = acf / acf[0] if acf[0] > 0 else acf
        lag_24 = min(24 * 12, N_sig - 1)
        binary_acf_24h = float(acf[lag_24])

        # --- Week-to-week KDE correlation ---
        n_weeks = total_days // 7
        if n_weeks >= 4:
            weekly_kdes = []
            for w in range(n_weeks):
                start_day = w * 7
                end_day = start_day + 7
                week_meals = [m['hour'] for m in meals
                              if start_day <= m.get('step', 0) // STEPS_PER_DAY < end_day]
                if len(week_meals) >= 3:
                    week_rad = np.array(week_meals) * 2 * np.pi / 24.0
                    wk = np.zeros(len(grid_hours))
                    for mr in week_rad:
                        wk += np.exp(kappa * np.cos(grid_rad - mr))
                    wk /= max(wk.sum(), 1e-8)
                    weekly_kdes.append(wk)

            if len(weekly_kdes) >= 3:
                corrs = []
                for i in range(len(weekly_kdes) - 1):
                    c = float(np.corrcoef(weekly_kdes[i], weekly_kdes[i + 1])[0, 1])
                    if np.isfinite(c):
                        corrs.append(c)
                mean_week_corr = float(np.mean(corrs)) if corrs else 0.0
            else:
                mean_week_corr = 0.0
        else:
            mean_week_corr = 0.0

        per_patient[name] = {
            'n_meals': len(meals),
            'entropy': round(entropy, 3),
            'normalized_entropy': round(normalized_entropy, 3),
            'n_peaks': len(peaks),
            'peaks': peaks,
            'binary_acf_24h': round(binary_acf_24h, 4),
            'week_to_week_corr': round(mean_week_corr, 4),
            'kde_reveals_more': normalized_entropy < 0.7 and abs(binary_acf_24h) < 0.01,
        }

        summary_rows.append({
            'patient': name,
            'entropy': normalized_entropy,
            'peaks': len(peaks),
            'acf24': binary_acf_24h,
            'wk_corr': mean_week_corr,
            'kde_better': '✓' if per_patient[name]['kde_reveals_more'] else '',
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*70}")
    print(f"EXP-1114: Smoothed Periodicity (KDE)")
    print(f"{'='*70}")
    print(f"{'Patient':>8s} {'Entropy':>8s} {'Peaks':>6s} {'ACF24h':>7s} "
          f"{'WkCorr':>7s} {'KDE>ACF':>7s}")
    print('-' * 50)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['entropy']:8.3f} {row['peaks']:6d} "
              f"{row['acf24']:7.4f} {row['wk_corr']:7.4f} {row['kde_better']:>7s}")

    mean_entropy = float(np.mean([r['entropy'] for r in summary_rows]))
    kde_better_count = sum(1 for r in summary_rows if r['kde_better'] == '✓')

    print(f"\nMean normalized entropy: {mean_entropy:.3f} (0=peaked, 1=uniform)")
    print(f"KDE reveals structure missed by ACF: {kde_better_count}/{len(summary_rows)}")

    return {
        'status': 'OK',
        'summary': f'Mean entropy={mean_entropy:.3f}; '
                   f'KDE reveals more in {kde_better_count}/{len(summary_rows)} patients',
        'results': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1115: Conditional Inter-Meal Interval
# ═══════════════════════════════════════════════════════════════════════

def exp_1115_conditional_interval(patients, detail=False):
    """Given that you just ate, predict time until next meal.

    For each consecutive meal pair: (time_since_last, hour_of_day, meal_size) → interval_to_next.
    Compare XGBoost regressor vs unconditional mean baseline.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 40:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        sorted_meals = sorted(meals, key=lambda m: m['step'])

        # Build feature/target pairs from consecutive meals
        X_pairs = []
        y_pairs = []

        for i in range(1, len(sorted_meals) - 1):
            prev_m = sorted_meals[i - 1]
            curr_m = sorted_meals[i]
            next_m = sorted_meals[i + 1]

            time_since_last_h = (curr_m['step'] - prev_m['step']) * 5.0 / 60.0
            if time_since_last_h > 24:
                continue  # skip overnight gaps

            interval_to_next_h = (next_m['step'] - curr_m['step']) * 5.0 / 60.0
            if interval_to_next_h > 24:
                continue

            hour = curr_m['hour']
            meal_size = curr_m['integral']
            window_code = {'breakfast': 0, 'lunch': 1, 'dinner': 2, 'snack': 3}
            win = window_code.get(assign_meal_window(hour), 3)

            X_pairs.append([
                time_since_last_h,
                np.sin(2 * np.pi * hour / 24),
                np.cos(2 * np.pi * hour / 24),
                meal_size,
                win,
                1.0 if curr_m['announced'] else 0.0,
            ])
            y_pairs.append(interval_to_next_h)

        if len(X_pairs) < 30:
            per_patient[name] = {'status': 'too_few_pairs', 'n_pairs': len(X_pairs)}
            continue

        X = np.array(X_pairs)
        y = np.array(y_pairs)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Temporal split
        split = int(len(X) * 0.8)
        X_tr, X_va = X[:split], X[split:]
        y_tr, y_va = y[:split], y[split:]

        # --- Unconditional baseline ---
        baseline_pred = float(np.mean(y_tr))
        baseline_mae = float(np.mean(np.abs(y_va - baseline_pred)))
        baseline_mae_min = baseline_mae * 60

        # --- Per-window baseline ---
        window_means = defaultdict(list)
        for i in range(split):
            win = int(X_tr[i, 4])
            window_means[win].append(y_tr[i])
        window_avgs = {w: float(np.mean(v)) for w, v in window_means.items()}
        win_preds = np.array([window_avgs.get(int(x[4]), baseline_pred) for x in X_va])
        win_mae = float(np.mean(np.abs(y_va - win_preds)))
        win_mae_min = win_mae * 60

        # --- XGBoost regressor ---
        reg = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        reg.fit(X_tr, y_tr)
        ml_pred = reg.predict(X_va)
        ml_mae = float(np.mean(np.abs(y_va - ml_pred)))
        ml_mae_min = ml_mae * 60

        # Feature importance
        feat_names_local = ['time_since_last', 'hour_sin', 'hour_cos',
                            'meal_size', 'window', 'announced']
        importances = dict(zip(feat_names_local,
                               [round(float(x), 4) for x in reg.feature_importances_]))

        # Correlation: does knowing when you last ate help?
        corr_interval = float(np.corrcoef(X[:, 0], y)[0, 1])

        per_patient[name] = {
            'n_pairs': len(X_pairs),
            'baseline_mae_min': round(baseline_mae_min, 1),
            'window_mae_min': round(win_mae_min, 1),
            'ml_mae_min': round(ml_mae_min, 1),
            'ml_vs_baseline_min': round(baseline_mae_min - ml_mae_min, 1),
            'ml_vs_baseline_pct': round((1 - ml_mae / baseline_mae) * 100, 1)
                                  if baseline_mae > 0 else 0,
            'interval_correlation': round(corr_interval, 3),
            'feature_importance': importances,
            'mean_interval_h': round(float(np.mean(y)), 2),
            'std_interval_h': round(float(np.std(y)), 2),
        }

        summary_rows.append({
            'patient': name,
            'pairs': len(X_pairs),
            'base_mae': baseline_mae_min,
            'win_mae': win_mae_min,
            'ml_mae': ml_mae_min,
            'Δ_min': baseline_mae_min - ml_mae_min,
            'corr': corr_interval,
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*75}")
    print(f"EXP-1115: Conditional Inter-Meal Interval")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'Pairs':>6s} {'Base':>7s} {'Window':>7s} "
          f"{'ML':>7s} {'Δ_min':>7s} {'Corr':>6s}")
    print('-' * 55)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['pairs']:6d} {row['base_mae']:7.1f} "
              f"{row['win_mae']:7.1f} {row['ml_mae']:7.1f} {row['Δ_min']:+7.1f} "
              f"{row['corr']:6.3f}")

    mean_ml_mae = float(np.mean([r['ml_mae'] for r in summary_rows]))
    mean_base_mae = float(np.mean([r['base_mae'] for r in summary_rows]))
    ml_wins = sum(1 for r in summary_rows if r['Δ_min'] > 0)

    print(f"\nMean ML MAE: {mean_ml_mae:.1f} min vs Baseline: {mean_base_mae:.1f} min")
    print(f"ML wins: {ml_wins}/{len(summary_rows)}")

    return {
        'status': 'OK',
        'summary': f'ML MAE={mean_ml_mae:.1f}min vs baseline={mean_base_mae:.1f}min; '
                   f'ML wins {ml_wins}/{len(summary_rows)}',
        'results': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1116: Alert Fatigue Simulation
# ═══════════════════════════════════════════════════════════════════════

def exp_1116_alert_fatigue(patients, detail=False):
    """Simulate 30-day deployment with minimum 2h between alerts.

    Uses EXP-1106 model with threshold 0.3 (default; override with EXP-1112).
    Metrics: alerts/day, TP, FP, missed_meals, PPV.
    """
    DEFAULT_THRESHOLD = 0.3
    MIN_ALERT_GAP_STEPS = 24  # 2 hours = 24 × 5 min
    SIM_DAYS = 30

    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, next_meal_dist, meal_steps, _ = \
            build_features_and_labels(df, sd, meals)
        X_tr, X_va = features[:split], features[split:]
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        clf = train_model(X_tr, y_tr)
        proba = clf.predict_proba(X_va)[:, 1]

        # Simulate with alert suppression
        sim_len = min(len(proba), SIM_DAYS * STEPS_PER_DAY)
        alerts = []
        last_alert_step = -MIN_ALERT_GAP_STEPS * 2  # allow first alert

        for i in range(sim_len):
            if proba[i] >= DEFAULT_THRESHOLD:
                if (i - last_alert_step) >= MIN_ALERT_GAP_STEPS:
                    alerts.append(i)
                    last_alert_step = i

        # Evaluate alerts against actual meals in val set
        val_meal_steps = sorted([ms - split for ms in meal_steps
                                 if split <= ms < split + sim_len])

        tp = 0
        fp = 0
        matched_meals = set()

        for a in alerts:
            # An alert is TP if a meal occurs within 60 min after the alert
            is_tp = False
            for vm in val_meal_steps:
                if 0 <= (vm - a) * 5 <= 60 and vm not in matched_meals:
                    is_tp = True
                    matched_meals.add(vm)
                    break
            if is_tp:
                tp += 1
            else:
                fp += 1

        missed = len(val_meal_steps) - len(matched_meals)
        sim_days_actual = max(1, sim_len / STEPS_PER_DAY)
        alerts_per_day = len(alerts) / sim_days_actual
        ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        sensitivity = tp / (tp + missed) if (tp + missed) > 0 else 0.0

        per_patient[name] = {
            'sim_days': round(sim_days_actual, 1),
            'total_alerts': len(alerts),
            'alerts_per_day': round(alerts_per_day, 2),
            'true_positives': tp,
            'false_positives': fp,
            'missed_meals': missed,
            'total_meals_in_sim': len(val_meal_steps),
            'ppv': round(ppv, 4),
            'sensitivity': round(sensitivity, 4),
            'threshold': DEFAULT_THRESHOLD,
            'min_gap_hours': 2,
        }

        summary_rows.append({
            'patient': name,
            'a/d': alerts_per_day,
            'tp': tp,
            'fp': fp,
            'miss': missed,
            'ppv': ppv,
            'sens': sensitivity,
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*70}")
    print(f"EXP-1116: Alert Fatigue Simulation (threshold={DEFAULT_THRESHOLD}, gap=2h)")
    print(f"{'='*70}")
    print(f"{'Patient':>8s} {'A/day':>6s} {'TP':>4s} {'FP':>4s} "
          f"{'Miss':>5s} {'PPV':>6s} {'Sens':>6s}")
    print('-' * 45)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['a/d']:6.2f} {row['tp']:4d} {row['fp']:4d} "
              f"{row['miss']:5d} {row['ppv']:6.4f} {row['sens']:6.4f}")

    mean_ppv = float(np.mean([r['ppv'] for r in summary_rows]))
    mean_sens = float(np.mean([r['sens'] for r in summary_rows]))
    mean_apd = float(np.mean([r['a/d'] for r in summary_rows]))

    print(f"\nMean alerts/day: {mean_apd:.2f}")
    print(f"Mean PPV: {mean_ppv:.4f}, Mean Sensitivity: {mean_sens:.4f}")

    return {
        'status': 'OK',
        'summary': f'Alerts/day={mean_apd:.2f}, PPV={mean_ppv:.4f}, '
                   f'Sensitivity={mean_sens:.4f}',
        'results': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1117: Glucose-Aware Prediction
# ═══════════════════════════════════════════════════════════════════════

def exp_1117_glucose_aware(patients, detail=False):
    """Extended feature set with glucose dynamics.

    Extra features: glucose_acceleration (2nd derivative),
    glucose_range_1h, glucose_range_3h, time_below_70,
    time_above_180_recent, glucose_CV_1h.
    """
    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features_base, labels, split, *_ = build_features_and_labels(df, sd, meals)
        N = len(df)
        glucose = df['glucose'].values

        # Build extended glucose features
        n_extra = 6
        extra = np.zeros((N, n_extra))

        for i in range(N):
            # Glucose acceleration (2nd derivative, ~15 min)
            if i >= 6:
                d1_now = glucose[i] - glucose[i - 3]
                d1_prev = glucose[i - 3] - glucose[i - 6]
                extra[i, 0] = d1_now - d1_prev

            # Glucose range 1h (12 steps)
            if i >= 12:
                window_1h = glucose[i - 12:i + 1]
                extra[i, 1] = np.max(window_1h) - np.min(window_1h)

            # Glucose range 3h (36 steps)
            if i >= 36:
                window_3h = glucose[i - 36:i + 1]
                extra[i, 2] = np.max(window_3h) - np.min(window_3h)

            # Time below 70 in last 1h (fraction)
            if i >= 12:
                extra[i, 3] = np.mean(glucose[i - 12:i + 1] < 70)

            # Time above 180 in last 1h (fraction)
            if i >= 12:
                extra[i, 4] = np.mean(glucose[i - 12:i + 1] > 180)

            # Glucose CV in last 1h
            if i >= 12:
                win = glucose[i - 12:i + 1]
                mu = np.mean(win)
                if mu > 0:
                    extra[i, 5] = np.std(win) / mu

        extra = np.nan_to_num(extra, nan=0.0, posinf=0.0, neginf=0.0)

        # Combine base + extra
        features_extended = np.hstack([features_base, extra])
        features_extended = np.nan_to_num(features_extended, nan=0.0,
                                          posinf=0.0, neginf=0.0)

        X_base_tr = features_base[:split]
        X_base_va = features_base[split:]
        X_ext_tr = features_extended[:split]
        X_ext_va = features_extended[split:]
        y_tr = labels[:split]
        y_va = labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # --- Base model (10 features) ---
        clf_base = train_model(X_base_tr, y_tr)
        proba_base = clf_base.predict_proba(X_base_va)[:, 1]
        auc_base = safe_auc(y_va, proba_base)

        # --- Extended model (16 features) ---
        from sklearn.ensemble import GradientBoostingClassifier
        clf_ext = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_ext.fit(X_ext_tr, y_tr)
        proba_ext = clf_ext.predict_proba(X_ext_va)[:, 1]
        auc_ext = safe_auc(y_va, proba_ext)

        # Feature importance of extended model
        ext_names = FEATURE_NAMES + [
            'glucose_accel', 'range_1h', 'range_3h',
            'time_below_70', 'time_above_180', 'glucose_CV_1h',
        ]
        importances = dict(zip(ext_names,
                               [round(float(x), 4) for x in clf_ext.feature_importances_]))

        # Rank new features
        new_feat_imp = {k: v for k, v in importances.items()
                        if k in ['glucose_accel', 'range_1h', 'range_3h',
                                 'time_below_70', 'time_above_180', 'glucose_CV_1h']}
        total_new_imp = sum(new_feat_imp.values())

        per_patient[name] = {
            'auc_base': round(auc_base, 4),
            'auc_extended': round(auc_ext, 4),
            'auc_lift': round(auc_ext - auc_base, 4),
            'extended_wins': auc_ext > auc_base,
            'feature_importance': importances,
            'new_feature_importance_total': round(total_new_imp, 4),
            'top_new_feature': max(new_feat_imp, key=new_feat_imp.get)
                               if new_feat_imp else 'N/A',
        }

        summary_rows.append({
            'patient': name,
            'base': auc_base,
            'ext': auc_ext,
            'lift': auc_ext - auc_base,
            'new_imp': total_new_imp,
            'top_new': per_patient[name]['top_new_feature'],
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*75}")
    print(f"EXP-1117: Glucose-Aware Prediction")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'Base':>7s} {'Extended':>8s} {'Lift':>7s} "
          f"{'NewImp':>7s} {'TopNew':>15s}")
    print('-' * 60)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['base']:7.4f} {row['ext']:8.4f} "
              f"{row['lift']:+7.4f} {row['new_imp']:7.4f} {row['top_new']:>15s}")

    mean_base = float(np.mean([r['base'] for r in summary_rows]))
    mean_ext = float(np.mean([r['ext'] for r in summary_rows]))
    ext_wins = sum(1 for r in summary_rows if r['lift'] > 0)

    print(f"\nMean AUC: base={mean_base:.4f}, extended={mean_ext:.4f}, "
          f"lift={mean_ext - mean_base:+.4f}")
    print(f"Extended wins: {ext_wins}/{len(summary_rows)}")

    return {
        'status': 'OK',
        'summary': f'Extended AUC={mean_ext:.4f} vs base={mean_base:.4f} '
                   f'(lift={mean_ext - mean_base:+.4f}); '
                   f'Extended wins {ext_wins}/{len(summary_rows)}',
        'results': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1118: ML vs Gaussian Head-to-Head
# ═══════════════════════════════════════════════════════════════════════

def exp_1118_ml_vs_gaussian(patients, detail=False):
    """Rigorous head-to-head: XGBoost vs per-window Gaussian on same val set.

    Metrics: AUC, F1, Brier score, precision@recall=0.5.
    """
    from sklearn.metrics import brier_score_loss, precision_recall_curve

    per_patient = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, next_meal_dist, meal_steps, hour_hist = \
            build_features_and_labels(df, sd, meals)
        N = len(df)
        X_tr, X_va = features[:split], features[split:]
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # --- ML model ---
        clf = train_model(X_tr, y_tr)
        ml_proba = clf.predict_proba(X_va)[:, 1]
        ml_auc = safe_auc(y_va, ml_proba)

        # --- Gaussian model ---
        # Fit per-window Gaussian from training meals
        train_meals = [m for m in meals if m['step'] < split]
        window_stats_g = defaultdict(list)
        for m in train_meals:
            w = assign_meal_window(m['hour'])
            window_stats_g[w].append(m['hour'])

        gauss_params = {}
        for w, hours in window_stats_g.items():
            if len(hours) >= 3:
                gauss_params[w] = (float(np.mean(hours)), max(float(np.std(hours)), 0.5))

        gauss_proba = np.zeros(len(X_va))
        for j in range(len(X_va)):
            idx = split + j
            hour = (idx % STEPS_PER_DAY) * 5.0 / 60.0
            best_p = 0.0
            for w, (mu, sigma) in gauss_params.items():
                p_val = stats.norm.pdf(hour, mu, sigma)
                if p_val > best_p:
                    best_p = p_val
            gauss_proba[j] = best_p

        # Normalize Gaussian to [0, 1]
        if gauss_proba.max() > 0:
            gauss_proba = gauss_proba / gauss_proba.max()

        gauss_auc = safe_auc(y_va, gauss_proba)

        # --- Brier score ---
        ml_brier = brier_score_loss(y_va, ml_proba)
        gauss_brier = brier_score_loss(y_va, gauss_proba)

        # --- Best F1 ---
        def best_f1(y_true, proba):
            prec, rec, thresholds = precision_recall_curve(y_true, proba)
            f1s = 2 * prec * rec / (prec + rec + 1e-8)
            idx = np.argmax(f1s)
            return float(f1s[idx])

        ml_f1 = best_f1(y_va, ml_proba)
        gauss_f1 = best_f1(y_va, gauss_proba)

        # --- Precision @ recall = 0.5 ---
        def prec_at_recall(y_true, proba, target_recall=0.5):
            prec, rec, _ = precision_recall_curve(y_true, proba)
            # Find precision where recall is closest to target
            diffs = np.abs(rec - target_recall)
            idx = np.argmin(diffs)
            return float(prec[idx])

        ml_p_at_r50 = prec_at_recall(y_va, ml_proba)
        gauss_p_at_r50 = prec_at_recall(y_va, gauss_proba)

        per_patient[name] = {
            'ml_auc': round(ml_auc, 4),
            'gauss_auc': round(gauss_auc, 4),
            'ml_f1': round(ml_f1, 4),
            'gauss_f1': round(gauss_f1, 4),
            'ml_brier': round(ml_brier, 4),
            'gauss_brier': round(gauss_brier, 4),
            'ml_prec_at_r50': round(ml_p_at_r50, 4),
            'gauss_prec_at_r50': round(gauss_p_at_r50, 4),
            'ml_wins_auc': ml_auc > gauss_auc,
            'ml_wins_f1': ml_f1 > gauss_f1,
            'ml_wins_brier': ml_brier < gauss_brier,
        }

        summary_rows.append({
            'patient': name,
            'ml_auc': ml_auc,
            'g_auc': gauss_auc,
            'ml_f1': ml_f1,
            'g_f1': gauss_f1,
            'ml_brier': ml_brier,
            'g_brier': gauss_brier,
            'ml_p@r50': ml_p_at_r50,
            'g_p@r50': gauss_p_at_r50,
        })

    if not summary_rows:
        return {'status': 'FAIL', 'summary': 'No valid patients'}

    print(f"\n{'='*80}")
    print(f"EXP-1118: ML vs Gaussian Head-to-Head")
    print(f"{'='*80}")
    print(f"{'':>8s} {'--- AUC ---':>14s} {'--- F1 ---':>14s} "
          f"{'--- Brier ---':>14s} {'- P@R50 -':>14s}")
    print(f"{'Patient':>8s} {'ML':>7s} {'Gauss':>6s} {'ML':>7s} {'Gauss':>6s} "
          f"{'ML':>7s} {'Gauss':>6s} {'ML':>7s} {'Gauss':>6s}")
    print('-' * 80)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['ml_auc']:7.4f} {row['g_auc']:6.4f} "
              f"{row['ml_f1']:7.4f} {row['g_f1']:6.4f} "
              f"{row['ml_brier']:7.4f} {row['g_brier']:6.4f} "
              f"{row['ml_p@r50']:7.4f} {row['g_p@r50']:6.4f}")

    # Aggregate wins
    auc_wins = sum(1 for r in per_patient.values() if r.get('ml_wins_auc'))
    f1_wins = sum(1 for r in per_patient.values() if r.get('ml_wins_f1'))
    brier_wins = sum(1 for r in per_patient.values() if r.get('ml_wins_brier'))
    total = len(summary_rows)

    mean_ml_auc = float(np.mean([r['ml_auc'] for r in summary_rows]))
    mean_g_auc = float(np.mean([r['g_auc'] for r in summary_rows]))
    mean_ml_brier = float(np.mean([r['ml_brier'] for r in summary_rows]))
    mean_g_brier = float(np.mean([r['g_brier'] for r in summary_rows]))

    print('-' * 80)
    print(f"{'MEAN':>8s} {mean_ml_auc:7.4f} {mean_g_auc:6.4f} "
          f"{float(np.mean([r['ml_f1'] for r in summary_rows])):7.4f} "
          f"{float(np.mean([r['g_f1'] for r in summary_rows])):6.4f} "
          f"{mean_ml_brier:7.4f} {mean_g_brier:6.4f} "
          f"{float(np.mean([r['ml_p@r50'] for r in summary_rows])):7.4f} "
          f"{float(np.mean([r['g_p@r50'] for r in summary_rows])):6.4f}")

    print(f"\nML wins — AUC: {auc_wins}/{total}, F1: {f1_wins}/{total}, "
          f"Brier: {brier_wins}/{total}")

    return {
        'status': 'OK',
        'summary': f'ML wins AUC {auc_wins}/{total}, F1 {f1_wins}/{total}, '
                   f'Brier {brier_wins}/{total}; '
                   f'ML AUC={mean_ml_auc:.4f} vs Gauss={mean_g_auc:.4f}',
        'results': per_patient,
        'aggregate': {
            'ml_wins_auc': auc_wins,
            'ml_wins_f1': f1_wins,
            'ml_wins_brier': brier_wins,
            'total': total,
            'mean_ml_auc': round(mean_ml_auc, 4),
            'mean_gauss_auc': round(mean_g_auc, 4),
            'mean_ml_brier': round(mean_ml_brier, 4),
            'mean_gauss_brier': round(mean_g_brier, 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Main dispatcher
# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients\n")

    experiments = [
        (1111, 'Feature Ablation', exp_1111_feature_ablation),
        (1112, 'Threshold Optimization', exp_1112_threshold_optimization),
        (1113, 'Cold Start / Online Learning', exp_1113_cold_start),
        (1114, 'Smoothed Periodicity (KDE)', exp_1114_smoothed_periodicity),
        (1115, 'Conditional Inter-Meal Interval', exp_1115_conditional_interval),
        (1116, 'Alert Fatigue Simulation', exp_1116_alert_fatigue),
        (1117, 'Glucose-Aware Prediction', exp_1117_glucose_aware),
        (1118, 'ML vs Gaussian Head-to-Head', exp_1118_ml_vs_gaussian),
    ]

    for exp_id, name, func in experiments:
        if args.exp and args.exp != exp_id:
            continue
        print(f"\n{'━'*70}")
        print(f"  EXP-{exp_id}: {name}")
        print(f"{'━'*70}\n")

        import time
        t0 = time.time()
        result = func(patients, detail=args.detail)
        elapsed = time.time() - t0

        # one-line summary
        summary = result.get('summary', '')
        status = result.get('status', 'OK')
        print(f"\n  → EXP-{exp_id} [{status}] {elapsed:.1f}s — {summary}")

        if args.save:
            filename = f"exp_{exp_id}_{name.lower().replace(' ', '_').replace('/', '_')}"
            save_results(result, filename)
            print(f"  → Saved {filename}")


if __name__ == '__main__':
    main()
