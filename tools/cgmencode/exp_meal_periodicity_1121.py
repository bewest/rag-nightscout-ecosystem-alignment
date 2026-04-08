#!/usr/bin/env python3
"""EXP-1121 to EXP-1128: Proactive Meal Prediction — Beyond Reactive Detection.

Building on Phases 1-2 (EXP-1101–1118):
- AUC=0.936 with net_flux is reactive (7.5min lead time)
- Time-only AUC=0.642 is the proactive ceiling to beat
- Periodicity is absent — must use conditional prediction
- Personal models win 10/11 over pooled

This batch focuses on purely PROACTIVE features:
  EXP-1121: Proactive-Only Baseline ★★★
  EXP-1122: Multi-Harmonic Time Features ★★★
  EXP-1123: Conditional Hazard Model ★★★
  EXP-1124: History Window Features ★★★
  EXP-1125: Pre-Meal Glucose Signatures ★★★
  EXP-1126: Proactive+Reactive Ensemble ★★★
  EXP-1127: Lead Time Analysis ★★★
  EXP-1128: Production Proactive Predictor ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_meal_periodicity_1121 --detail --save
    PYTHONPATH=tools python -m cgmencode.exp_meal_periodicity_1121 --exp 1121
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
# Shared helpers (copied from 1111 — do not import across experiment files)
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

    Returns (features, labels, split_idx, next_meal_dist, meal_steps, hour_hist).
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
# EXP-1121: Proactive-Only Baseline
# ═══════════════════════════════════════════════════════════════════════

def exp_1121_proactive_baseline(patients, detail=False):
    """Establish proactive AUC ceiling by training WITHOUT net_flux.

    Three models per patient:
      - full: all 10 features (reactive reference)
      - proactive: 9 features (drop net_flux idx 8)
      - time_only: 6 features [0,1,2,3,4,9]
    Key metric: glucose feature lift = proactive_auc - time_only_auc
    """
    from sklearn.ensemble import GradientBoostingClassifier

    PROACTIVE_IDX = [0, 1, 2, 3, 4, 5, 6, 7, 9]
    TIME_ONLY_IDX = [0, 1, 2, 3, 4, 9]

    per_patient = {}
    auc_full_all, auc_pro_all, auc_time_all = [], [], []

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

        # Full model (reactive reference)
        clf_full = train_model(X_tr, y_tr)
        auc_full = safe_auc(y_va, clf_full.predict_proba(X_va)[:, 1])

        # Proactive model (no net_flux)
        X_tr_pro = np.nan_to_num(X_tr[:, PROACTIVE_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        X_va_pro = np.nan_to_num(X_va[:, PROACTIVE_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_pro = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_pro.fit(X_tr_pro, y_tr)
        auc_pro = safe_auc(y_va, clf_pro.predict_proba(X_va_pro)[:, 1])

        # Time-only model
        X_tr_time = np.nan_to_num(X_tr[:, TIME_ONLY_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        X_va_time = np.nan_to_num(X_va[:, TIME_ONLY_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_time = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_time.fit(X_tr_time, y_tr)
        auc_time = safe_auc(y_va, clf_time.predict_proba(X_va_time)[:, 1])

        glucose_lift = auc_pro - auc_time
        reactive_gap = auc_full - auc_pro

        per_patient[name] = {
            'auc_full': round(auc_full, 4),
            'auc_proactive': round(auc_pro, 4),
            'auc_time_only': round(auc_time, 4),
            'glucose_lift': round(glucose_lift, 4),
            'reactive_gap': round(reactive_gap, 4),
            'n_meals': len(meals),
        }
        auc_full_all.append(auc_full)
        auc_pro_all.append(auc_pro)
        auc_time_all.append(auc_time)

        if detail:
            print(f"  {name:>8s}: full={auc_full:.3f}  proactive={auc_pro:.3f}  "
                  f"time_only={auc_time:.3f}  gluc_lift={glucose_lift:+.3f}  "
                  f"reactive_gap={reactive_gap:.3f}")

    mean_full = np.mean(auc_full_all) if auc_full_all else 0
    mean_pro = np.mean(auc_pro_all) if auc_pro_all else 0
    mean_time = np.mean(auc_time_all) if auc_time_all else 0
    mean_gluc_lift = mean_pro - mean_time

    if detail and auc_full_all:
        print(f"\n  Aggregate: full={mean_full:.3f}  proactive={mean_pro:.3f}  "
              f"time_only={mean_time:.3f}  glucose_lift={mean_gluc_lift:+.3f}")

    return {
        'status': 'OK',
        'summary': (f"proactive={mean_pro:.3f} vs full={mean_full:.3f} vs "
                    f"time={mean_time:.3f}, glucose_lift={mean_gluc_lift:+.3f}"),
        'results': per_patient,
        'aggregate': {
            'mean_auc_full': round(mean_full, 4),
            'mean_auc_proactive': round(mean_pro, 4),
            'mean_auc_time_only': round(mean_time, 4),
            'mean_glucose_lift': round(mean_gluc_lift, 4),
            'n_patients': len(auc_full_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1122: Multi-Harmonic Time Features
# ═══════════════════════════════════════════════════════════════════════

def exp_1122_multi_harmonic(patients, detail=False):
    """Test whether sub-daily harmonics (12h, 8h, 6h) capture tri-modal meals.

    Basic time features (6): hour_sin/cos_24, time_since_meal, meals_today, day_of_week, hist_meal_prob
    Multi-harmonic (12): basic + sin/cos at 12h, 8h, 6h periods
    No net_flux, no glucose — pure time/schedule features.
    """
    from sklearn.ensemble import GradientBoostingClassifier

    BASIC_TIME_IDX = [0, 1, 2, 3, 4, 9]

    per_patient = {}
    auc_basic_all, auc_harmonic_all = [], []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, _, _, _ = build_features_and_labels(df, sd, meals)
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # Basic time-only
        X_basic = np.nan_to_num(features[:, BASIC_TIME_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_basic = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_basic.fit(X_basic[:split], y_tr)
        auc_basic = safe_auc(y_va, clf_basic.predict_proba(X_basic[split:])[:, 1])

        # Build extended harmonic features
        hours = np.array([(i % STEPS_PER_DAY) * 5.0 / 60.0 for i in range(N)])
        harmonic_extra = np.zeros((N, 6))
        for idx, period in enumerate([12, 8, 6]):
            harmonic_extra[:, idx * 2] = np.sin(2 * np.pi * hours / period)
            harmonic_extra[:, idx * 2 + 1] = np.cos(2 * np.pi * hours / period)

        X_harmonic = np.hstack([features[:, BASIC_TIME_IDX], harmonic_extra])
        X_harmonic = np.nan_to_num(X_harmonic, nan=0.0, posinf=0.0, neginf=0.0)

        clf_harmonic = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_harmonic.fit(X_harmonic[:split], y_tr)
        auc_harmonic = safe_auc(y_va, clf_harmonic.predict_proba(X_harmonic[split:])[:, 1])

        # Per-harmonic ablation to find which adds most
        harmonic_contrib = {}
        for period in [12, 8, 6]:
            idx_offset = {12: 0, 8: 2, 6: 4}[period]
            drop_mask = list(range(6))  # basic features
            for h_period in [12, 8, 6]:
                if h_period != period:
                    h_off = {12: 0, 8: 2, 6: 4}[h_period]
                    drop_mask.extend([6 + h_off, 6 + h_off + 1])
            X_drop = np.nan_to_num(X_harmonic[:, drop_mask], nan=0.0, posinf=0.0, neginf=0.0)
            clf_drop = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42)
            clf_drop.fit(X_drop[:split], y_tr)
            auc_drop = safe_auc(y_va, clf_drop.predict_proba(X_drop[split:])[:, 1])
            harmonic_contrib[f'{period}h'] = round(auc_harmonic - auc_drop, 4)

        per_patient[name] = {
            'auc_basic_time': round(auc_basic, 4),
            'auc_multi_harmonic': round(auc_harmonic, 4),
            'harmonic_lift': round(auc_harmonic - auc_basic, 4),
            'per_harmonic_contrib': harmonic_contrib,
            'n_meals': len(meals),
        }
        auc_basic_all.append(auc_basic)
        auc_harmonic_all.append(auc_harmonic)

        if detail:
            print(f"  {name:>8s}: basic={auc_basic:.3f}  harmonic={auc_harmonic:.3f}  "
                  f"lift={auc_harmonic - auc_basic:+.3f}  "
                  f"contrib=[12h:{harmonic_contrib['12h']:+.3f} "
                  f"8h:{harmonic_contrib['8h']:+.3f} "
                  f"6h:{harmonic_contrib['6h']:+.3f}]")

    mean_basic = np.mean(auc_basic_all) if auc_basic_all else 0
    mean_harm = np.mean(auc_harmonic_all) if auc_harmonic_all else 0

    if detail and auc_basic_all:
        print(f"\n  Aggregate: basic={mean_basic:.3f}  harmonic={mean_harm:.3f}  "
              f"lift={mean_harm - mean_basic:+.3f}")

    return {
        'status': 'OK',
        'summary': f"harmonic={mean_harm:.3f} vs basic={mean_basic:.3f}, lift={mean_harm - mean_basic:+.3f}",
        'results': per_patient,
        'aggregate': {
            'mean_auc_basic': round(mean_basic, 4),
            'mean_auc_harmonic': round(mean_harm, 4),
            'mean_harmonic_lift': round(mean_harm - mean_basic, 4),
            'n_patients': len(auc_basic_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1123: Conditional Hazard Model
# ═══════════════════════════════════════════════════════════════════════

def exp_1123_hazard_model(patients, detail=False):
    """Model P(meal in next 30min | time_since_last=t, hour=h) as survival.

    Fit Weibull, Log-Normal, and Exponential to inter-meal intervals.
    Compute conditional hazard h(t) = f(t)/S(t) and condition on 4-hour blocks.
    Evaluate as binary classifier vs GBT time-only baseline.
    """
    from sklearn.ensemble import GradientBoostingClassifier

    TIME_ONLY_IDX = [0, 1, 2, 3, 4, 9]

    per_patient = {}
    auc_weibull_all, auc_lognorm_all, auc_exp_all, auc_cond_all, auc_time_all = (
        [], [], [], [], [])

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
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # Inter-meal intervals (minutes)
        sorted_steps = sorted(meal_steps)
        intervals = []
        for j in range(1, len(sorted_steps)):
            gap_min = (sorted_steps[j] - sorted_steps[j - 1]) * 5.0
            if 15 < gap_min < 1440:  # filter implausible gaps
                intervals.append(gap_min)
        intervals = np.array(intervals)

        if len(intervals) < 10:
            per_patient[name] = {'status': 'insufficient_intervals'}
            continue

        # Fit distributions
        dist_aucs = {}
        try:
            wb_shape, _, wb_scale = stats.weibull_min.fit(intervals, floc=0)
            wb_dist = stats.weibull_min(wb_shape, loc=0, scale=wb_scale)
        except Exception:
            wb_dist = None

        try:
            ln_shape, ln_loc, ln_scale = stats.lognorm.fit(intervals, floc=0)
            ln_dist = stats.lognorm(ln_shape, loc=0, scale=ln_scale)
        except Exception:
            ln_dist = None

        try:
            exp_loc, exp_scale = stats.expon.fit(intervals, floc=0)
            exp_dist = stats.expon(loc=0, scale=exp_scale)
        except Exception:
            exp_dist = None

        # Previous meal distance for each timestep (feature index 2)
        prev_dist = features[:, 2].copy()  # in minutes

        # Compute hazard scores for each distribution
        def compute_hazard_score(dist, t_vals):
            """h(t) = f(t)/S(t) where S(t)=1-CDF(t)."""
            t_vals = np.clip(t_vals, 1.0, 1440.0)
            pdf_vals = dist.pdf(t_vals)
            sf_vals = dist.sf(t_vals)
            sf_vals = np.clip(sf_vals, 1e-10, None)
            return pdf_vals / sf_vals

        for dist_name, dist_obj in [('weibull', wb_dist), ('lognorm', ln_dist),
                                     ('expon', exp_dist)]:
            if dist_obj is None:
                dist_aucs[dist_name] = 0.5
                continue
            scores = compute_hazard_score(dist_obj, prev_dist[split:])
            scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
            dist_aucs[dist_name] = safe_auc(y_va, scores)

        # Conditional hazard: stratify by 4-hour blocks
        hours = np.array([(i % STEPS_PER_DAY) * 5.0 / 60.0 for i in range(N)])
        hour_blocks = (hours // 4).astype(int)  # 0-5 for 6 blocks

        # Fit per-block Weibull
        train_meal_hours = [m['hour'] for m in meals if m['step'] < split]
        block_intervals = defaultdict(list)
        for j in range(1, len(sorted_steps)):
            if sorted_steps[j] >= split:
                continue
            gap_min = (sorted_steps[j] - sorted_steps[j - 1]) * 5.0
            if 15 < gap_min < 1440:
                h = (sorted_steps[j - 1] % STEPS_PER_DAY) * 5.0 / 60.0
                blk = int(h // 4)
                block_intervals[blk].append(gap_min)

        block_dists = {}
        for blk in range(6):
            bi = block_intervals.get(blk, [])
            if len(bi) >= 5:
                try:
                    shape, _, scale = stats.weibull_min.fit(bi, floc=0)
                    block_dists[blk] = stats.weibull_min(shape, loc=0, scale=scale)
                except Exception:
                    block_dists[blk] = wb_dist  # fallback
            else:
                block_dists[blk] = wb_dist  # fallback to global

        # Conditional hazard scores on validation set
        cond_scores = np.zeros(N - split)
        for idx in range(N - split):
            i = split + idx
            blk = hour_blocks[i]
            dist_obj = block_dists.get(blk)
            if dist_obj is not None:
                t = max(prev_dist[i], 1.0)
                t = min(t, 1440.0)
                sf = max(dist_obj.sf(t), 1e-10)
                cond_scores[idx] = dist_obj.pdf(t) / sf
        cond_scores = np.nan_to_num(cond_scores, nan=0.0, posinf=0.0, neginf=0.0)
        auc_cond = safe_auc(y_va, cond_scores)

        # GBT time-only baseline for comparison
        X_time = np.nan_to_num(features[:, TIME_ONLY_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_time = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_time.fit(X_time[:split], y_tr)
        auc_time = safe_auc(y_va, clf_time.predict_proba(X_time[split:])[:, 1])

        best_param = max(dist_aucs, key=dist_aucs.get)

        per_patient[name] = {
            'auc_weibull': round(dist_aucs.get('weibull', 0.5), 4),
            'auc_lognorm': round(dist_aucs.get('lognorm', 0.5), 4),
            'auc_expon': round(dist_aucs.get('expon', 0.5), 4),
            'auc_conditional': round(auc_cond, 4),
            'auc_time_only': round(auc_time, 4),
            'best_parametric': best_param,
            'n_intervals': len(intervals),
            'mean_interval_min': round(float(np.mean(intervals)), 1),
            'std_interval_min': round(float(np.std(intervals)), 1),
        }

        auc_weibull_all.append(dist_aucs.get('weibull', 0.5))
        auc_lognorm_all.append(dist_aucs.get('lognorm', 0.5))
        auc_exp_all.append(dist_aucs.get('expon', 0.5))
        auc_cond_all.append(auc_cond)
        auc_time_all.append(auc_time)

        if detail:
            print(f"  {name:>8s}: weibull={dist_aucs.get('weibull', 0.5):.3f}  "
                  f"lognorm={dist_aucs.get('lognorm', 0.5):.3f}  "
                  f"expon={dist_aucs.get('expon', 0.5):.3f}  "
                  f"cond={auc_cond:.3f}  time_gbt={auc_time:.3f}  "
                  f"best={best_param}")

    mean_wb = np.mean(auc_weibull_all) if auc_weibull_all else 0
    mean_ln = np.mean(auc_lognorm_all) if auc_lognorm_all else 0
    mean_cond = np.mean(auc_cond_all) if auc_cond_all else 0
    mean_time = np.mean(auc_time_all) if auc_time_all else 0

    if detail and auc_weibull_all:
        print(f"\n  Aggregate: weibull={mean_wb:.3f}  lognorm={mean_ln:.3f}  "
              f"conditional={mean_cond:.3f}  time_gbt={mean_time:.3f}")

    return {
        'status': 'OK',
        'summary': (f"conditional_hazard={mean_cond:.3f} vs time_gbt={mean_time:.3f}, "
                    f"weibull={mean_wb:.3f}"),
        'results': per_patient,
        'aggregate': {
            'mean_auc_weibull': round(mean_wb, 4),
            'mean_auc_lognorm': round(mean_ln, 4),
            'mean_auc_conditional': round(mean_cond, 4),
            'mean_auc_time_only': round(mean_time, 4),
            'n_patients': len(auc_weibull_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1124: History Window Features
# ═══════════════════════════════════════════════════════════════════════

def exp_1124_history_features(patients, detail=False):
    """Test whether YESTERDAY's meal times predict TODAY's meals.

    Additional features (no net_flux, no glucose):
      - yesterday_meal_dist: time to same-clock-time meal yesterday
      - yesterday_had_meal_this_hour: binary
      - last_3_day_meal_prob_this_hour: fraction of last 3 days with meal at hour
      - rolling_7d_meal_rate: meals per day over last 7 days
      - same_window_yesterday: meal time in same B/L/D window yesterday (min offset)
    """
    from sklearn.ensemble import GradientBoostingClassifier

    TIME_ONLY_IDX = [0, 1, 2, 3, 4, 9]

    per_patient = {}
    auc_time_all, auc_hist_all = [], []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            per_patient[name] = {'status': 'insufficient_meals'}
            continue

        features, labels, split, _, meal_steps, _ = build_features_and_labels(df, sd, meals)
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        meal_set = set(meal_steps)

        # Build per-day meal hour lookup: day -> list of (hour, step, window)
        day_meals = defaultdict(list)
        for ms in meal_steps:
            day = ms // STEPS_PER_DAY
            hour = (ms % STEPS_PER_DAY) * 5.0 / 60.0
            day_meals[day].append((hour, ms, assign_meal_window(hour)))

        # Build history features
        hist_features = np.zeros((N, 5))
        for i in range(N):
            day = i // STEPS_PER_DAY
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
            hour_int = int(hour) % 24
            window = assign_meal_window(hour)

            # yesterday_meal_dist: distance from same clock-time yesterday
            yesterday = day - 1
            if yesterday in day_meals and day_meals[yesterday]:
                dists = [abs(hour - mh) * 60.0 for mh, _, _ in day_meals[yesterday]]
                hist_features[i, 0] = min(dists)
            else:
                hist_features[i, 0] = 1440.0  # no data

            # yesterday_had_meal_this_hour
            if yesterday in day_meals:
                hist_features[i, 1] = float(any(
                    int(mh) == hour_int for mh, _, _ in day_meals[yesterday]))

            # last_3_day_meal_prob_this_hour
            days_with_meal = 0
            days_checked = 0
            for d_offset in range(1, 4):
                check_day = day - d_offset
                if check_day in day_meals:
                    days_checked += 1
                    if any(int(mh) == hour_int for mh, _, _ in day_meals[check_day]):
                        days_with_meal += 1
            hist_features[i, 2] = days_with_meal / max(days_checked, 1)

            # rolling_7d_meal_rate: meals per day over last 7 days
            total_meals_7d = 0
            days_7d = 0
            for d_offset in range(1, 8):
                check_day = day - d_offset
                if check_day in day_meals:
                    total_meals_7d += len(day_meals[check_day])
                    days_7d += 1
            hist_features[i, 3] = total_meals_7d / max(days_7d, 1)

            # same_window_yesterday: minutes from window-start of yesterday's meal
            if yesterday in day_meals:
                same_win_meals = [mh for mh, _, mw in day_meals[yesterday] if mw == window]
                if same_win_meals:
                    window_starts = {'breakfast': 5.0, 'lunch': 10.0,
                                     'dinner': 17.0, 'snack': 0.0}
                    ws = window_starts.get(window, 0.0)
                    hist_features[i, 4] = (same_win_meals[0] - ws) * 60.0
                else:
                    hist_features[i, 4] = -1.0  # no same-window meal
            else:
                hist_features[i, 4] = -1.0

        hist_features = np.nan_to_num(hist_features, nan=0.0, posinf=0.0, neginf=0.0)

        # Time-only baseline
        X_time = np.nan_to_num(features[:, TIME_ONLY_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_time = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_time.fit(X_time[:split], y_tr)
        auc_time = safe_auc(y_va, clf_time.predict_proba(X_time[split:])[:, 1])

        # Time + history
        X_hist = np.hstack([features[:, TIME_ONLY_IDX], hist_features])
        X_hist = np.nan_to_num(X_hist, nan=0.0, posinf=0.0, neginf=0.0)
        clf_hist = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_hist.fit(X_hist[:split], y_tr)
        auc_hist = safe_auc(y_va, clf_hist.predict_proba(X_hist[split:])[:, 1])

        hist_lift = auc_hist - auc_time

        per_patient[name] = {
            'auc_time_only': round(auc_time, 4),
            'auc_time_history': round(auc_hist, 4),
            'history_lift': round(hist_lift, 4),
            'n_meals': len(meals),
            'n_days': N // STEPS_PER_DAY,
        }
        auc_time_all.append(auc_time)
        auc_hist_all.append(auc_hist)

        if detail:
            print(f"  {name:>8s}: time={auc_time:.3f}  time+hist={auc_hist:.3f}  "
                  f"lift={hist_lift:+.3f}  ({N // STEPS_PER_DAY}d, {len(meals)} meals)")

    mean_time = np.mean(auc_time_all) if auc_time_all else 0
    mean_hist = np.mean(auc_hist_all) if auc_hist_all else 0

    if detail and auc_time_all:
        print(f"\n  Aggregate: time={mean_time:.3f}  time+hist={mean_hist:.3f}  "
              f"lift={mean_hist - mean_time:+.3f}")

    return {
        'status': 'OK',
        'summary': f"time+history={mean_hist:.3f} vs time_only={mean_time:.3f}, lift={mean_hist - mean_time:+.3f}",
        'results': per_patient,
        'aggregate': {
            'mean_auc_time_only': round(mean_time, 4),
            'mean_auc_time_history': round(mean_hist, 4),
            'mean_history_lift': round(mean_hist - mean_time, 4),
            'n_patients': len(auc_time_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1125: Pre-Meal Glucose Signatures
# ═══════════════════════════════════════════════════════════════════════

def exp_1125_premeal_glucose(patients, detail=False):
    """Find glucose patterns that PRECEDE meals by 30-60 min.

    For each detected meal, extract 60-min pre-meal window and compute:
      glucose_mean, glucose_std, glucose_slope, glucose_flatness,
      fasting_duration, iob_proxy
    Compare with random non-meal windows at the same hour.
    Train GBT on pre-meal features alone, and combined with time-only.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold

    TIME_ONLY_IDX = [0, 1, 2, 3, 4, 9]

    per_patient = {}
    auc_premeal_all, auc_time_all, auc_combined_all = [], [], []

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
        N = len(features)
        glucose = np.nan_to_num(df['glucose'].values, nan=0.0)
        supply = sd.get('supply', np.zeros(N))
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # Build pre-meal glucose features for every timestep
        premeal_features = np.zeros((N, 6))
        for i in range(N):
            window_start = max(0, i - 12)  # 60 min lookback (12 steps)
            gluc_window = glucose[window_start:i + 1]

            if len(gluc_window) < 3:
                continue

            premeal_features[i, 0] = np.mean(gluc_window)  # glucose_mean
            premeal_features[i, 1] = np.std(gluc_window)   # glucose_std

            # glucose_slope: linear fit over window
            if len(gluc_window) >= 2:
                x_fit = np.arange(len(gluc_window))
                try:
                    coeffs = np.polyfit(x_fit, np.nan_to_num(gluc_window, nan=0.0), 1)
                    premeal_features[i, 2] = coeffs[0] if np.isfinite(coeffs[0]) else 0.0
                except (np.linalg.LinAlgError, TypeError, ValueError):
                    premeal_features[i, 2] = 0.0

            # glucose_flatness: 1/std (capped)
            std_val = premeal_features[i, 1]
            premeal_features[i, 3] = min(1.0 / max(std_val, 0.1), 100.0)

            # fasting_duration: steps since glucose was > mean+15
            mean_g = np.mean(glucose[max(0, i - STEPS_PER_DAY):i + 1])
            threshold_g = mean_g + 15
            fasting_steps = 0
            for j in range(i, max(0, i - STEPS_PER_DAY), -1):
                if glucose[j] > threshold_g:
                    break
                fasting_steps += 1
            premeal_features[i, 4] = fasting_steps * 5.0  # in minutes

            # iob_proxy: sum of supply in 60-min window
            supply_window = supply[window_start:i + 1]
            premeal_features[i, 5] = np.sum(supply_window)

        premeal_features = np.nan_to_num(premeal_features, nan=0.0, posinf=0.0, neginf=0.0)

        # Pre-meal features only
        X_pre = premeal_features
        clf_pre = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_pre.fit(X_pre[:split], y_tr)
        auc_premeal = safe_auc(y_va, clf_pre.predict_proba(X_pre[split:])[:, 1])

        # Time-only baseline
        X_time = np.nan_to_num(features[:, TIME_ONLY_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_time = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_time.fit(X_time[:split], y_tr)
        auc_time = safe_auc(y_va, clf_time.predict_proba(X_time[split:])[:, 1])

        # Combined: time + pre-meal glucose
        X_comb = np.hstack([features[:, TIME_ONLY_IDX], premeal_features])
        X_comb = np.nan_to_num(X_comb, nan=0.0, posinf=0.0, neginf=0.0)
        clf_comb = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_comb.fit(X_comb[:split], y_tr)
        auc_combined = safe_auc(y_va, clf_comb.predict_proba(X_comb[split:])[:, 1])

        # Analyze pre-meal vs non-meal feature distributions
        meal_mask_va = labels[split:] == 1
        nonmeal_mask_va = labels[split:] == 0
        feature_separability = {}
        premeal_feat_names = ['gluc_mean', 'gluc_std', 'gluc_slope',
                              'gluc_flatness', 'fasting_dur', 'iob_proxy']
        for fi, fn in enumerate(premeal_feat_names):
            meal_vals = premeal_features[split:][meal_mask_va, fi]
            nonmeal_vals = premeal_features[split:][nonmeal_mask_va, fi]
            if len(meal_vals) > 5 and len(nonmeal_vals) > 5:
                try:
                    stat, pval = stats.mannwhitneyu(meal_vals, nonmeal_vals,
                                                    alternative='two-sided')
                    feature_separability[fn] = round(pval, 6)
                except ValueError:
                    feature_separability[fn] = 1.0
            else:
                feature_separability[fn] = 1.0

        per_patient[name] = {
            'auc_premeal_only': round(auc_premeal, 4),
            'auc_time_only': round(auc_time, 4),
            'auc_time_premeal': round(auc_combined, 4),
            'premeal_lift': round(auc_combined - auc_time, 4),
            'feature_pvalues': feature_separability,
            'n_meals': len(meals),
        }
        auc_premeal_all.append(auc_premeal)
        auc_time_all.append(auc_time)
        auc_combined_all.append(auc_combined)

        if detail:
            sig_feats = sum(1 for v in feature_separability.values() if v < 0.05)
            print(f"  {name:>8s}: premeal={auc_premeal:.3f}  time={auc_time:.3f}  "
                  f"combined={auc_combined:.3f}  lift={auc_combined - auc_time:+.3f}  "
                  f"sig_feats={sig_feats}/6")

    mean_pre = np.mean(auc_premeal_all) if auc_premeal_all else 0
    mean_time = np.mean(auc_time_all) if auc_time_all else 0
    mean_comb = np.mean(auc_combined_all) if auc_combined_all else 0

    if detail and auc_premeal_all:
        print(f"\n  Aggregate: premeal={mean_pre:.3f}  time={mean_time:.3f}  "
              f"combined={mean_comb:.3f}  lift={mean_comb - mean_time:+.3f}")

    return {
        'status': 'OK',
        'summary': (f"premeal_only={mean_pre:.3f}, time+premeal={mean_comb:.3f}, "
                    f"lift={mean_comb - mean_time:+.3f}"),
        'results': per_patient,
        'aggregate': {
            'mean_auc_premeal_only': round(mean_pre, 4),
            'mean_auc_time_only': round(mean_time, 4),
            'mean_auc_time_premeal': round(mean_comb, 4),
            'mean_premeal_lift': round(mean_comb - mean_time, 4),
            'n_patients': len(auc_premeal_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1126: Proactive + Reactive Ensemble
# ═══════════════════════════════════════════════════════════════════════

def exp_1126_ensemble(patients, detail=False):
    """Two-model system maximizing both lead time and precision.

    Model A (proactive): no net_flux (features [0,1,2,3,4,5,6,7,9])
    Model B (reactive): full 10-feature model
    Ensemble: alert on proactive, confirm/cancel on reactive.
    Sweep threshold pairs, report Pareto frontier of (lead_time, precision).
    """
    from sklearn.ensemble import GradientBoostingClassifier

    PROACTIVE_IDX = [0, 1, 2, 3, 4, 5, 6, 7, 9]

    per_patient = {}
    pareto_all = []

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
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # Train proactive model
        X_pro = np.nan_to_num(features[:, PROACTIVE_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf_pro = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_pro.fit(X_pro[:split], y_tr)
        proba_pro = clf_pro.predict_proba(X_pro[split:])[:, 1]

        # Train reactive model
        X_full = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
        clf_react = train_model(X_full[:split], y_tr)
        proba_react = clf_react.predict_proba(X_full[split:])[:, 1]

        # Sweep threshold pairs for Pareto frontier
        threshold_pro_range = np.arange(0.1, 0.8, 0.1)
        threshold_react_range = np.arange(0.1, 0.8, 0.1)

        best_pareto = []
        nmd_va = next_meal_dist[split:]
        meal_set_va = set(ms - split for ms in meal_steps if ms >= split)

        for thr_p in threshold_pro_range:
            for thr_r in threshold_react_range:
                # Proactive fires first, reactive confirms
                proactive_alerts = proba_pro >= thr_p
                reactive_confirms = proba_react >= thr_r
                combined = proactive_alerts & reactive_confirms

                tp = np.sum(combined & (y_va == 1))
                fp = np.sum(combined & (y_va == 0))
                fn = np.sum(~combined & (y_va == 1))

                precision = tp / max(tp + fp, 1)
                recall = tp / max(tp + fn, 1)

                # Measure lead time for true positives
                lead_times = []
                for idx in range(len(y_va)):
                    if combined[idx] and y_va[idx] == 1:
                        lead_times.append(nmd_va[idx])

                mean_lead = np.mean(lead_times) if lead_times else 0

                best_pareto.append({
                    'thr_proactive': round(float(thr_p), 2),
                    'thr_reactive': round(float(thr_r), 2),
                    'precision': round(float(precision), 4),
                    'recall': round(float(recall), 4),
                    'mean_lead_min': round(float(mean_lead), 1),
                    'n_alerts': int(np.sum(combined)),
                })

        # Filter Pareto-optimal points (maximize lead time + precision)
        pareto_frontier = []
        for pt in best_pareto:
            dominated = False
            for other in best_pareto:
                if (other['precision'] >= pt['precision'] and
                        other['mean_lead_min'] >= pt['mean_lead_min'] and
                        (other['precision'] > pt['precision'] or
                         other['mean_lead_min'] > pt['mean_lead_min'])):
                    dominated = True
                    break
            if not dominated and pt['precision'] > 0 and pt['mean_lead_min'] > 0:
                pareto_frontier.append(pt)

        # Sort by lead time
        pareto_frontier.sort(key=lambda x: -x['mean_lead_min'])

        # Find best point with >=70% precision and >=30min lead
        target_pts = [pt for pt in best_pareto
                      if pt['precision'] >= 0.7 and pt['mean_lead_min'] >= 30]
        best_target = max(target_pts, key=lambda x: x['recall']) if target_pts else None

        per_patient[name] = {
            'pareto_frontier': pareto_frontier[:10],  # top 10
            'best_70prec_30lead': best_target,
            'n_pareto_points': len(pareto_frontier),
            'auc_proactive': round(safe_auc(y_va, proba_pro), 4),
            'auc_reactive': round(safe_auc(y_va, proba_react), 4),
            'n_meals': len(meals),
        }

        if best_target:
            pareto_all.append(best_target)

        if detail:
            auc_p = safe_auc(y_va, proba_pro)
            auc_r = safe_auc(y_va, proba_react)
            target_str = (f"prec={best_target['precision']:.2f} "
                          f"lead={best_target['mean_lead_min']:.0f}min"
                          if best_target else "NO TARGET MET")
            print(f"  {name:>8s}: pro_auc={auc_p:.3f}  react_auc={auc_r:.3f}  "
                  f"pareto={len(pareto_frontier)}pts  {target_str}")

    # Aggregate
    n_target_met = len(pareto_all)
    mean_prec = np.mean([pt['precision'] for pt in pareto_all]) if pareto_all else 0
    mean_lead = np.mean([pt['mean_lead_min'] for pt in pareto_all]) if pareto_all else 0

    if detail:
        print(f"\n  Aggregate: {n_target_met} patients met >=70% prec + >=30min lead")
        if pareto_all:
            print(f"  Mean precision={mean_prec:.3f}  Mean lead={mean_lead:.1f}min")

    return {
        'status': 'OK',
        'summary': (f"{n_target_met} patients met target, "
                    f"mean_prec={mean_prec:.3f}, mean_lead={mean_lead:.1f}min"),
        'results': per_patient,
        'aggregate': {
            'n_target_met': n_target_met,
            'mean_precision_at_target': round(mean_prec, 4),
            'mean_lead_at_target': round(mean_lead, 1),
            'n_patients': len([v for v in per_patient.values()
                               if v.get('auc_proactive')]),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1127: Lead Time Analysis
# ═══════════════════════════════════════════════════════════════════════

def exp_1127_lead_time(patients, detail=False):
    """Measure actual lead time of proactive model at each operating point.

    For each threshold:
      - mean/median lead time for true positives
      - fraction with >=30min lead
    Also: evaluate ONLY on timesteps >=30min before any meal (honest AUC).
    """
    from sklearn.ensemble import GradientBoostingClassifier

    PROACTIVE_IDX = [0, 1, 2, 3, 4, 5, 6, 7, 9]

    per_patient = {}
    honest_auc_all, full_proactive_auc_all = [], []

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
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        # Train proactive model
        X_pro = np.nan_to_num(features[:, PROACTIVE_IDX], nan=0.0, posinf=0.0, neginf=0.0)
        clf = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf.fit(X_pro[:split], y_tr)
        proba_va = clf.predict_proba(X_pro[split:])[:, 1]

        full_pro_auc = safe_auc(y_va, proba_va)

        # Lead time analysis across thresholds
        nmd_va = next_meal_dist[split:]
        threshold_sweep = np.arange(0.1, 0.95, 0.05)
        threshold_results = []

        for thr in threshold_sweep:
            preds = proba_va >= thr
            tp_mask = preds & (y_va == 1)
            tp_lead_times = nmd_va[tp_mask]

            n_tp = int(np.sum(tp_mask))
            n_fp = int(np.sum(preds & (y_va == 0)))
            n_fn = int(np.sum(~preds & (y_va == 1)))

            if n_tp > 0:
                mean_lead = float(np.mean(tp_lead_times))
                median_lead = float(np.median(tp_lead_times))
                frac_30 = float(np.mean(tp_lead_times >= 30))
            else:
                mean_lead = 0.0
                median_lead = 0.0
                frac_30 = 0.0

            precision = n_tp / max(n_tp + n_fp, 1)
            recall = n_tp / max(n_tp + n_fn, 1)

            threshold_results.append({
                'threshold': round(float(thr), 2),
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'mean_lead_min': round(mean_lead, 1),
                'median_lead_min': round(median_lead, 1),
                'frac_30min_lead': round(frac_30, 3),
                'n_tp': n_tp,
                'n_fp': n_fp,
            })

        # Honest proactive AUC: only evaluate >=30min before any meal
        # For positive examples: next_meal_dist >= 30 AND next_meal_dist <= horizon (30min)
        # This is impossible: if >=30min before AND <=30min label → only the 30min boundary
        # Instead: honest = mask out timesteps where next_meal_dist < 30 AND NOT a meal label
        # Actually: honest evaluation = only timesteps >=30min from nearest meal step
        meal_step_set = set(meal_steps)
        honest_mask = np.ones(N - split, dtype=bool)
        for idx in range(N - split):
            i = split + idx
            # Find min distance to any meal step
            min_dist_to_meal = min(abs(i - ms) * 5 for ms in meal_steps) if meal_steps else 9999
            # Mask out the "reactive window" (within 30min of a meal, but label could be 0 or 1)
            # Keep: steps >=30min before next meal OR steps that are meal-adjacent for positives
            if 0 < nmd_va[idx] < 30:
                # This step is within 30min of a meal — reactive zone
                honest_mask[idx] = False

        # Relabel for honest evaluation: "meal in 30-60min" bucket
        # positive = next_meal_dist between 30 and 60 (approaching, but not yet reactive)
        honest_labels = ((nmd_va >= 30) & (nmd_va <= 60)).astype(int)

        if honest_mask.sum() > 50 and honest_labels[honest_mask].sum() > 5:
            honest_auc = safe_auc(honest_labels[honest_mask], proba_va[honest_mask])
        else:
            honest_auc = 0.5

        per_patient[name] = {
            'auc_proactive': round(full_pro_auc, 4),
            'auc_honest_proactive': round(honest_auc, 4),
            'threshold_sweep': threshold_results,
            'n_meals': len(meals),
        }
        honest_auc_all.append(honest_auc)
        full_proactive_auc_all.append(full_pro_auc)

        if detail:
            # Find threshold with best F1
            best_f1_row = max(threshold_results,
                              key=lambda r: (2 * r['precision'] * r['recall'] /
                                             max(r['precision'] + r['recall'], 1e-10)))
            print(f"  {name:>8s}: pro_auc={full_pro_auc:.3f}  honest_auc={honest_auc:.3f}  "
                  f"best_thr={best_f1_row['threshold']:.2f} "
                  f"(prec={best_f1_row['precision']:.2f} "
                  f"rec={best_f1_row['recall']:.2f} "
                  f"lead={best_f1_row['mean_lead_min']:.0f}min "
                  f"frac30={best_f1_row['frac_30min_lead']:.2f})")

    mean_honest = np.mean(honest_auc_all) if honest_auc_all else 0
    mean_pro = np.mean(full_proactive_auc_all) if full_proactive_auc_all else 0

    if detail and honest_auc_all:
        print(f"\n  Aggregate: proactive_auc={mean_pro:.3f}  "
              f"honest_proactive_auc={mean_honest:.3f}")

    return {
        'status': 'OK',
        'summary': f"proactive_auc={mean_pro:.3f}, honest_auc={mean_honest:.3f}",
        'results': per_patient,
        'aggregate': {
            'mean_auc_proactive': round(mean_pro, 4),
            'mean_auc_honest': round(mean_honest, 4),
            'n_patients': len(honest_auc_all),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1128: Production Proactive Predictor
# ═══════════════════════════════════════════════════════════════════════

def exp_1128_production(patients, detail=False):
    """Package the best proactive model into production-ready form.

    Uses the proactive feature set (no net_flux).
    Trains on each patient's full data.
    Reports: feature_importance, calibration, optimal_threshold,
    production metrics (alerts/day, PPV, sensitivity, mean_lead).
    Defines ProactiveMealModel interface as a dict.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import calibration_curve

    PROACTIVE_IDX = [0, 1, 2, 3, 4, 5, 6, 7, 9]
    PROACTIVE_NAMES = [FEATURE_NAMES[i] for i in PROACTIVE_IDX]

    per_patient = {}
    all_alerts_per_day, all_ppv, all_sensitivity, all_lead = [], [], [], []

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
        N = len(features)
        y_tr, y_va = labels[:split], labels[split:]

        if y_tr.sum() < 10 or y_va.sum() < 5:
            per_patient[name] = {'status': 'insufficient_positives'}
            continue

        X_pro = np.nan_to_num(features[:, PROACTIVE_IDX], nan=0.0, posinf=0.0, neginf=0.0)

        # Train on training set, evaluate on validation
        clf = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf.fit(X_pro[:split], y_tr)
        proba_va = clf.predict_proba(X_pro[split:])[:, 1]

        auc_val = safe_auc(y_va, proba_va)

        # Feature importance
        importances = dict(zip(PROACTIVE_NAMES,
                               [round(float(v), 4) for v in clf.feature_importances_]))

        # Calibration curve
        try:
            prob_true, prob_pred = calibration_curve(y_va, proba_va, n_bins=5,
                                                     strategy='uniform')
            calibration = {
                'prob_true': [round(float(v), 4) for v in prob_true],
                'prob_pred': [round(float(v), 4) for v in prob_pred],
            }
        except ValueError:
            calibration = {'prob_true': [], 'prob_pred': []}

        # Find optimal threshold (maximize F1)
        best_f1, best_thr = 0, 0.3
        nmd_va = next_meal_dist[split:]
        for thr in np.arange(0.1, 0.9, 0.02):
            preds = proba_va >= thr
            tp = np.sum(preds & (y_va == 1))
            fp = np.sum(preds & (y_va == 0))
            fn = np.sum(~preds & (y_va == 1))
            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            f1 = 2 * prec * rec / max(prec + rec, 1e-10)
            if f1 > best_f1:
                best_f1 = f1
                best_thr = float(thr)

        # Production metrics at optimal threshold
        preds_opt = proba_va >= best_thr
        tp = int(np.sum(preds_opt & (y_va == 1)))
        fp = int(np.sum(preds_opt & (y_va == 0)))
        fn = int(np.sum(~preds_opt & (y_va == 1)))
        n_alerts = int(np.sum(preds_opt))
        n_val_days = max((N - split) / STEPS_PER_DAY, 1)
        alerts_per_day = n_alerts / n_val_days
        ppv = tp / max(tp + fp, 1)
        sensitivity = tp / max(tp + fn, 1)

        # Mean lead time at optimal threshold
        tp_mask = preds_opt & (y_va == 1)
        lead_times = nmd_va[tp_mask]
        mean_lead = float(np.mean(lead_times)) if len(lead_times) > 0 else 0

        # Train final model on ALL data for production
        clf_full = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf_full.fit(X_pro, labels)
        final_importances = dict(zip(PROACTIVE_NAMES,
                                     [round(float(v), 4)
                                      for v in clf_full.feature_importances_]))

        # ProactiveMealModel interface definition
        model_spec = {
            'feature_names': PROACTIVE_NAMES,
            'model_params': {
                'n_estimators': 100,
                'max_depth': 4,
                'learning_rate': 0.1,
                'subsample': 0.8,
            },
            'threshold': round(best_thr, 3),
            'calibration': calibration,
            'cold_start_days': 7,
            'min_meals_to_train': 30,
        }

        per_patient[name] = {
            'auc_validation': round(auc_val, 4),
            'optimal_threshold': round(best_thr, 3),
            'best_f1': round(best_f1, 4),
            'alerts_per_day': round(alerts_per_day, 2),
            'ppv': round(ppv, 4),
            'sensitivity': round(sensitivity, 4),
            'mean_lead_min': round(mean_lead, 1),
            'feature_importance_val': importances,
            'feature_importance_full': final_importances,
            'model_spec': model_spec,
            'n_meals': len(meals),
            'n_val_days': round(n_val_days, 1),
        }

        all_alerts_per_day.append(alerts_per_day)
        all_ppv.append(ppv)
        all_sensitivity.append(sensitivity)
        all_lead.append(mean_lead)

        if detail:
            top_feat = max(final_importances, key=final_importances.get)
            print(f"  {name:>8s}: auc={auc_val:.3f}  thr={best_thr:.2f}  "
                  f"alerts/day={alerts_per_day:.1f}  ppv={ppv:.2f}  "
                  f"sens={sensitivity:.2f}  lead={mean_lead:.0f}min  "
                  f"top_feat={top_feat}")

    mean_ppv = np.mean(all_ppv) if all_ppv else 0
    mean_sens = np.mean(all_sensitivity) if all_sensitivity else 0
    mean_alerts = np.mean(all_alerts_per_day) if all_alerts_per_day else 0
    mean_lead = np.mean(all_lead) if all_lead else 0

    if detail and all_ppv:
        print(f"\n  Aggregate: alerts/day={mean_alerts:.1f}  ppv={mean_ppv:.3f}  "
              f"sensitivity={mean_sens:.3f}  lead={mean_lead:.1f}min")

    return {
        'status': 'OK',
        'summary': (f"ppv={mean_ppv:.3f}, sens={mean_sens:.3f}, "
                    f"alerts/day={mean_alerts:.1f}, lead={mean_lead:.1f}min"),
        'results': per_patient,
        'aggregate': {
            'mean_ppv': round(mean_ppv, 4),
            'mean_sensitivity': round(mean_sens, 4),
            'mean_alerts_per_day': round(mean_alerts, 2),
            'mean_lead_min': round(mean_lead, 1),
            'n_patients': len(all_ppv),
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
        (1121, 'Proactive Baseline', exp_1121_proactive_baseline),
        (1122, 'Multi-Harmonic Time', exp_1122_multi_harmonic),
        (1123, 'Conditional Hazard', exp_1123_hazard_model),
        (1124, 'History Window Features', exp_1124_history_features),
        (1125, 'Pre-Meal Glucose Signatures', exp_1125_premeal_glucose),
        (1126, 'Proactive+Reactive Ensemble', exp_1126_ensemble),
        (1127, 'Lead Time Analysis', exp_1127_lead_time),
        (1128, 'Production Proactive Predictor', exp_1128_production),
    ]

    for exp_id, name, func in experiments:
        if args.exp and args.exp != exp_id:
            continue
        print(f"\n{'━'*70}")
        print(f"  EXP-{exp_id}: {name}")
        print(f"{'━'*70}\n")

        t0 = time.time()
        result = func(patients, detail=args.detail)
        elapsed = time.time() - t0

        summary = result.get('summary', '')
        status = result.get('status', 'OK')
        print(f"\n  → EXP-{exp_id} [{status}] {elapsed:.1f}s — {summary}")

        if args.save:
            filename = f"exp_{exp_id}_{name.lower().replace(' ', '_').replace('/', '_').replace('+', '_')}"
            save_results(result, filename)
            print(f"  → Saved {filename}")


if __name__ == '__main__':
    main()
