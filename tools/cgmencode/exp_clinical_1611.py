#!/usr/bin/env python3
"""EXP-1611–1618: Multi-Stage Alert Filtering

Batch 4: Hierarchical classifier pipeline for clinically useful alerts.
Target: ≤5 alerts/day at PPV≥0.50.

Prior art:
  - EXP-1141: Per-patient thresholds best: 23.7→6.0 alerts/day, PPV 0.24→0.43
  - EXP-1145: Production sim: 0.8 alerts/day but sensitivity=0.02
  - EXP-1541: Event-aware hypo prediction AUC unchanged (Δ=-0.001)
  - Fundamental PPV-sensitivity tradeoff at AUC=0.846
"""

import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

from cgmencode.exp_metabolic_flux import load_patients


def _load_patients():
    return load_patients(patients_dir=str(PATIENTS_DIR), max_patients=None)


def _compute_glucose_features(glucose, idx, lookback=12):
    """Compute local glucose features at index."""
    n = len(glucose)
    start = max(0, idx - lookback)
    window = glucose[start:idx + 1]
    valid = window[np.isfinite(window)]
    if len(valid) < 3:
        return None

    current = glucose[idx]
    if not np.isfinite(current):
        return None

    rate = (valid[-1] - valid[0]) / max(len(valid) - 1, 1) if len(valid) > 1 else 0
    accel = 0
    if len(valid) >= 5:
        mid = len(valid) // 2
        rate1 = (valid[mid] - valid[0]) / max(mid, 1)
        rate2 = (valid[-1] - valid[mid]) / max(len(valid) - mid - 1, 1)
        accel = rate2 - rate1

    return {
        'current': float(current),
        'rate': float(rate),          # mg/dL per 5-min step
        'acceleration': float(accel),
        'min_1h': float(np.nanmin(valid)),
        'max_1h': float(np.nanmax(valid)),
        'std_1h': float(np.nanstd(valid)),
        'below_80': float(current < 80),
        'below_100': float(current < 100),
        'rapid_drop': float(rate < -2),  # >10 mg/dL per 30min drop
    }


def _detect_hypo_events(glucose, threshold=70, horizon_steps=12):
    """Find timesteps where glucose goes below threshold within horizon."""
    n = len(glucose)
    labels = np.zeros(n, dtype=int)
    for i in range(n - horizon_steps):
        future = glucose[i + 1:i + 1 + horizon_steps]
        if np.any(future < threshold):
            labels[i] = 1
    return labels


def _detect_metabolic_state(df):
    """Simple metabolic state classification."""
    n = len(df)
    states = np.full(n, 'unknown', dtype=object)
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(n)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(n)
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(n)

    for i in range(n):
        # Recent carbs (last 2h)
        c_start = max(0, i - 24)
        recent_carbs = np.nansum(carbs[c_start:i + 1])

        if recent_carbs > 5:
            states[i] = 'postprandial'
        elif iob[i] > 0.5 if np.isfinite(iob[i]) else False:
            states[i] = 'correction_active'
        elif np.isfinite(glucose[i]) and glucose[i] < 80:
            states[i] = 'low_risk'
        else:
            states[i] = 'fasting'

    return states


def _save_result(exp_id, data, elapsed):
    out = RESULTS_DIR / f'exp-{exp_id}_alert_filtering.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ Saved → {out}  ({elapsed:.1f}s)")


# ============================================================
# EXP-1611: Baseline Alert Performance
# ============================================================
def exp_1611(patients):
    """Measure baseline alert performance at various thresholds."""
    print("\n" + "─" * 60)
    print("EXP-1611: Baseline Alert Performance")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)
            days = n / STEPS_PER_DAY

            # True hypo events (1h horizon)
            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)
            hypo_rate = labels.sum() / max(days, 1)

            # Test various rate-of-change thresholds
            thresholds = [-1.0, -1.5, -2.0, -2.5, -3.0]
            threshold_results = {}

            for thr in thresholds:
                alerts = np.zeros(n)
                for i in range(12, n):
                    feat = _compute_glucose_features(glucose, i)
                    if feat and feat['rate'] < thr:
                        alerts[i] = 1

                # Suppress consecutive alerts (min 30 min gap)
                suppressed = np.zeros(n)
                last_alert = -999
                for i in range(n):
                    if alerts[i] and (i - last_alert) >= 6:
                        suppressed[i] = 1
                        last_alert = i

                alerts_per_day = suppressed.sum() / max(days, 1)
                tp = np.sum(suppressed * labels)
                fp = np.sum(suppressed * (1 - labels))
                fn = np.sum((1 - suppressed) * labels)
                ppv = tp / max(tp + fp, 1)
                sensitivity = tp / max(tp + fn, 1)

                threshold_results[str(thr)] = {
                    'alerts_per_day': float(alerts_per_day),
                    'ppv': float(ppv),
                    'sensitivity': float(sensitivity),
                    'tp': int(tp), 'fp': int(fp), 'fn': int(fn),
                }

            results[p['name']] = {
                'hypo_events_per_day': float(hypo_rate),
                'days': float(days),
                'thresholds': threshold_results,
            }

            best_thr = min(threshold_results.items(),
                          key=lambda x: abs(x[1]['alerts_per_day'] - 5))
            print(f"  {p['name']}: hypo={hypo_rate:.1f}/day  "
                  f"best@{best_thr[0]}→{best_thr[1]['alerts_per_day']:.1f}/day  "
                  f"PPV={best_thr[1]['ppv']:.2f}  sens={best_thr[1]['sensitivity']:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1611',
        'title': 'Baseline Alert Performance',
        'patients': results,
    }
    _save_result(1611, result, time.time() - t0)
    return results


# ============================================================
# EXP-1612: Metabolic State-Aware Filtering
# ============================================================
def exp_1612(patients):
    """Filter alerts by metabolic state (postprandial, fasting, correction)."""
    print("\n" + "─" * 60)
    print("EXP-1612: Metabolic State-Aware Filtering")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)
            states = _detect_metabolic_state(df)

            # Compute hypo risk per state
            state_types = ['fasting', 'postprandial', 'correction_active', 'low_risk']
            state_risk = {}

            for st in state_types:
                mask = states == st
                count = mask.sum()
                if count > 0:
                    hypo_in_state = labels[mask].sum()
                    state_risk[st] = {
                        'count': int(count),
                        'pct_of_total': float(count / n * 100),
                        'hypo_rate': float(hypo_in_state / count) if count > 0 else 0,
                        'hypo_count': int(hypo_in_state),
                    }

            # State-weighted alert: only alert in high-risk states
            alerts = np.zeros(n)
            high_risk_states = set()
            for st, info in state_risk.items():
                if info['hypo_rate'] > 0.05:  # >5% hypo rate = high risk
                    high_risk_states.add(st)

            for i in range(12, n):
                feat = _compute_glucose_features(glucose, i)
                if feat and feat['rate'] < -2.0 and states[i] in high_risk_states:
                    alerts[i] = 1

            # Suppress consecutive
            suppressed = np.zeros(n)
            last_alert = -999
            for i in range(n):
                if alerts[i] and (i - last_alert) >= 6:
                    suppressed[i] = 1
                    last_alert = i

            alerts_per_day = suppressed.sum() / max(days, 1)
            tp = np.sum(suppressed * labels)
            fp = np.sum(suppressed * (1 - labels))
            fn = np.sum((1 - suppressed) * labels)
            ppv = tp / max(tp + fp, 1)
            sensitivity = tp / max(tp + fn, 1)

            results[p['name']] = {
                'state_risk': state_risk,
                'high_risk_states': list(high_risk_states),
                'alerts_per_day': float(alerts_per_day),
                'ppv': float(ppv),
                'sensitivity': float(sensitivity),
            }

            print(f"  {p['name']}: high_risk={high_risk_states}  "
                  f"{alerts_per_day:.1f}/day  PPV={ppv:.2f}  sens={sensitivity:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1612',
        'title': 'Metabolic State-Aware Filtering',
        'patients': results,
    }
    _save_result(1612, result, time.time() - t0)
    return results


# ============================================================
# EXP-1613: Multi-Feature Alert Scoring
# ============================================================
def exp_1613(patients):
    """Score alerts using multiple glucose features, not just rate."""
    print("\n" + "─" * 60)
    print("EXP-1613: Multi-Feature Alert Scoring")
    print("─" * 60)
    t0 = time.time()

    results = {}
    all_features = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(glucose))
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)

            # Build feature matrix
            X = []
            y = []
            indices = []
            for i in range(24, n - 12):
                feat = _compute_glucose_features(glucose, i, lookback=24)
                if feat is None:
                    continue
                iob_val = iob[i] if np.isfinite(iob[i]) else 0
                features = [
                    feat['current'],
                    feat['rate'],
                    feat['acceleration'],
                    feat['std_1h'],
                    feat['min_1h'],
                    iob_val,
                    feat['below_100'],
                    feat['rapid_drop'],
                ]
                X.append(features)
                y.append(labels[i])
                indices.append(i)

            if len(X) < 100:
                results[p['name']] = {'error': 'insufficient_data'}
                continue

            X = np.array(X)
            y = np.array(y)

            # Logistic regression scoring
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import cross_val_predict
            from sklearn.preprocessing import StandardScaler
            from sklearn.metrics import roc_auc_score, precision_recall_curve

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # 5-fold cross-validated predictions
            lr = LogisticRegression(max_iter=1000, class_weight='balanced')
            probs = cross_val_predict(lr, X_scaled, y, cv=5, method='predict_proba')[:, 1]

            auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0.5

            # Find threshold for ≤5 alerts/day
            best_thr = 0.5
            best_diff = 999
            for thr in np.arange(0.1, 0.95, 0.01):
                raw_alerts = (probs > thr).astype(int)
                # Suppress consecutive
                suppressed = np.zeros(len(raw_alerts))
                last_a = -999
                for i in range(len(raw_alerts)):
                    if raw_alerts[i] and (indices[i] - last_a) >= 6:
                        suppressed[i] = 1
                        last_a = indices[i]
                apd = suppressed.sum() / max(days, 1)
                if abs(apd - 5) < best_diff:
                    best_diff = abs(apd - 5)
                    best_thr = thr

            # Compute metrics at best threshold
            raw_alerts = (probs > best_thr).astype(int)
            suppressed = np.zeros(len(raw_alerts))
            last_a = -999
            for i in range(len(raw_alerts)):
                if raw_alerts[i] and (indices[i] - last_a) >= 6:
                    suppressed[i] = 1
                    last_a = indices[i]

            tp = np.sum(suppressed * y)
            fp = np.sum(suppressed * (1 - y))
            fn = np.sum((1 - suppressed) * y)
            ppv = float(tp / max(tp + fp, 1))
            sensitivity = float(tp / max(tp + fn, 1))
            alerts_per_day = float(suppressed.sum() / max(days, 1))

            # Feature importance
            lr.fit(X_scaled, y)
            feat_names = ['current', 'rate', 'acceleration', 'std_1h', 'min_1h', 'iob', 'below_100', 'rapid_drop']
            importance = dict(zip(feat_names, [float(c) for c in lr.coef_[0]]))

            results[p['name']] = {
                'auc': float(auc),
                'optimal_threshold': float(best_thr),
                'alerts_per_day': alerts_per_day,
                'ppv': ppv,
                'sensitivity': sensitivity,
                'feature_importance': importance,
            }
            all_features[p['name']] = {'X': X, 'y': y, 'indices': indices}

            print(f"  {p['name']}: AUC={auc:.3f}  @thr={best_thr:.2f}→{alerts_per_day:.1f}/day  "
                  f"PPV={ppv:.2f}  sens={sensitivity:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1613',
        'title': 'Multi-Feature Alert Scoring',
        'patients': results,
    }
    _save_result(1613, result, time.time() - t0)
    return results, all_features


# ============================================================
# EXP-1614: Time-of-Day Alert Modulation
# ============================================================
def exp_1614(patients, baseline_results):
    """Modulate alert thresholds by time of day based on historical hypo patterns."""
    print("\n" + "─" * 60)
    print("EXP-1614: Time-of-Day Alert Modulation")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)

            # Compute hypo rate by hour
            hourly_hypo = np.zeros(24)
            hourly_count = np.zeros(24)
            for i in range(n):
                hour = int((i % STEPS_PER_DAY) / STEPS_PER_HOUR)
                hourly_count[hour] += 1
                hourly_hypo[hour] += labels[i]

            hourly_rate = hourly_hypo / np.maximum(hourly_count, 1)

            # Adaptive threshold: lower threshold (more sensitive) in high-risk hours
            base_rate_thr = -2.0
            adaptive_thr = np.full(24, base_rate_thr)
            mean_rate = np.mean(hourly_rate)
            for h in range(24):
                if hourly_rate[h] > mean_rate * 1.5:
                    adaptive_thr[h] = -1.5  # More sensitive
                elif hourly_rate[h] < mean_rate * 0.5:
                    adaptive_thr[h] = -2.5  # Less sensitive

            # Apply adaptive thresholds
            alerts = np.zeros(n)
            for i in range(12, n):
                hour = int((i % STEPS_PER_DAY) / STEPS_PER_HOUR)
                feat = _compute_glucose_features(glucose, i)
                if feat and feat['rate'] < adaptive_thr[hour]:
                    alerts[i] = 1

            # Suppress consecutive
            suppressed = np.zeros(n)
            last_alert = -999
            for i in range(n):
                if alerts[i] and (i - last_alert) >= 6:
                    suppressed[i] = 1
                    last_alert = i

            alerts_per_day = suppressed.sum() / max(days, 1)
            tp = np.sum(suppressed * labels)
            fp = np.sum(suppressed * (1 - labels))
            fn = np.sum((1 - suppressed) * labels)
            ppv = float(tp / max(tp + fp, 1))
            sensitivity = float(tp / max(tp + fn, 1))

            # Peak hypo hours
            peak_hours = sorted(range(24), key=lambda h: -hourly_rate[h])[:5]

            results[p['name']] = {
                'hourly_hypo_rate': [float(x) for x in hourly_rate],
                'adaptive_thresholds': [float(x) for x in adaptive_thr],
                'peak_hypo_hours': peak_hours,
                'alerts_per_day': float(alerts_per_day),
                'ppv': ppv,
                'sensitivity': sensitivity,
            }

            print(f"  {p['name']}: peak_hours={peak_hours[:3]}  "
                  f"{alerts_per_day:.1f}/day  PPV={ppv:.2f}  sens={sensitivity:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1614',
        'title': 'Time-of-Day Alert Modulation',
        'patients': results,
    }
    _save_result(1614, result, time.time() - t0)
    return results


# ============================================================
# EXP-1615: Hierarchical Two-Stage Filter
# ============================================================
def exp_1615(patients):
    """Two-stage: broad detection → precision filtering."""
    print("\n" + "─" * 60)
    print("EXP-1615: Hierarchical Two-Stage Filter")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(glucose))
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)
            states = _detect_metabolic_state(df)

            # Stage 1: Broad detection (high sensitivity)
            stage1 = np.zeros(n)
            for i in range(12, n):
                feat = _compute_glucose_features(glucose, i)
                if feat is None:
                    continue
                # Trigger if any of: dropping fast, low already, or high IOB + dropping
                if feat['rate'] < -1.0:  # Any noticeable drop
                    stage1[i] = 1
                elif feat['current'] < 90 and feat['rate'] < -0.5:
                    stage1[i] = 1
                elif iob[i] > 2.0 and np.isfinite(iob[i]) and feat['rate'] < -0.5:
                    stage1[i] = 1

            stage1_rate = stage1.sum() / max(days, 1)

            # Stage 2: Precision filter using composite score
            stage2 = np.zeros(n)
            for i in range(12, n):
                if not stage1[i]:
                    continue
                feat = _compute_glucose_features(glucose, i)
                if feat is None:
                    continue

                # Composite risk score
                score = 0
                score += max(0, (100 - feat['current']) / 30)   # Proximity to 70
                score += max(0, -feat['rate'] / 2)               # Drop rate
                score += max(0, -feat['acceleration'] / 1)       # Accelerating drop
                iob_val = iob[i] if np.isfinite(iob[i]) else 0
                score += min(2, iob_val / 2)                     # IOB risk
                if states[i] == 'correction_active':
                    score += 0.5
                if states[i] == 'fasting':
                    score += 0.3  # Fasting hypos are more dangerous

                if score >= 2.5:  # Precision threshold
                    stage2[i] = 1

            # Suppress consecutive (30 min gap)
            suppressed = np.zeros(n)
            last_alert = -999
            for i in range(n):
                if stage2[i] and (i - last_alert) >= 6:
                    suppressed[i] = 1
                    last_alert = i

            alerts_per_day = suppressed.sum() / max(days, 1)
            tp = np.sum(suppressed * labels)
            fp = np.sum(suppressed * (1 - labels))
            fn = np.sum((1 - suppressed) * labels)
            ppv = float(tp / max(tp + fp, 1))
            sensitivity = float(tp / max(tp + fn, 1))

            results[p['name']] = {
                'stage1_triggers_per_day': float(stage1_rate),
                'stage2_alerts_per_day': float(alerts_per_day),
                'reduction_ratio': float(1 - alerts_per_day / max(stage1_rate, 0.1)),
                'ppv': ppv,
                'sensitivity': sensitivity,
            }

            print(f"  {p['name']}: stage1={stage1_rate:.0f}/day → stage2={alerts_per_day:.1f}/day  "
                  f"({1 - alerts_per_day / max(stage1_rate, 0.1):.0%} reduction)  "
                  f"PPV={ppv:.2f}  sens={sensitivity:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1615',
        'title': 'Hierarchical Two-Stage Filter',
        'patients': results,
    }
    _save_result(1615, result, time.time() - t0)
    return results


# ============================================================
# EXP-1616: Per-Patient Threshold Optimization
# ============================================================
def exp_1616(patients):
    """Optimize alert threshold per patient to hit target PPV."""
    print("\n" + "─" * 60)
    print("EXP-1616: Per-Patient Threshold Optimization")
    print("─" * 60)
    t0 = time.time()

    TARGET_PPV = 0.50
    MAX_ALERTS_PER_DAY = 5.0

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(glucose))
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)

            # Compute composite scores for all timesteps
            scores = np.full(n, -999.0)
            for i in range(12, n):
                feat = _compute_glucose_features(glucose, i)
                if feat is None:
                    continue
                score = 0
                score += max(0, (100 - feat['current']) / 30)
                score += max(0, -feat['rate'] / 2)
                score += max(0, -feat['acceleration'] / 1)
                iob_val = iob[i] if np.isfinite(iob[i]) else 0
                score += min(2, iob_val / 2)
                scores[i] = score

            # Search for optimal threshold
            best_thr = 2.0
            best_score = -1
            for thr in np.arange(1.0, 5.0, 0.1):
                raw = (scores >= thr).astype(int)
                suppressed = np.zeros(n)
                last_a = -999
                for i in range(n):
                    if raw[i] and (i - last_a) >= 6:
                        suppressed[i] = 1
                        last_a = i

                apd = suppressed.sum() / max(days, 1)
                if apd > MAX_ALERTS_PER_DAY:
                    continue

                tp = np.sum(suppressed * labels)
                fp = np.sum(suppressed * (1 - labels))
                ppv = float(tp / max(tp + fp, 1))
                fn = np.sum((1 - suppressed) * labels)
                sens = float(tp / max(tp + fn, 1))

                # Objective: maximize F1 subject to PPV and alert constraints
                f1 = 2 * ppv * sens / max(ppv + sens, 1e-10)
                composite = f1 * (1 if ppv >= TARGET_PPV else ppv / TARGET_PPV)

                if composite > best_score:
                    best_score = composite
                    best_thr = thr

            # Apply best threshold
            raw = (scores >= best_thr).astype(int)
            suppressed = np.zeros(n)
            last_a = -999
            for i in range(n):
                if raw[i] and (i - last_a) >= 6:
                    suppressed[i] = 1
                    last_a = i

            apd = suppressed.sum() / max(days, 1)
            tp = np.sum(suppressed * labels)
            fp = np.sum(suppressed * (1 - labels))
            fn = np.sum((1 - suppressed) * labels)
            ppv = float(tp / max(tp + fp, 1))
            sens = float(tp / max(tp + fn, 1))

            results[p['name']] = {
                'optimal_threshold': float(best_thr),
                'alerts_per_day': float(apd),
                'ppv': ppv,
                'sensitivity': sens,
                'meets_ppv_target': ppv >= TARGET_PPV,
                'meets_alert_target': apd <= MAX_ALERTS_PER_DAY,
            }

            met = "✓" if ppv >= TARGET_PPV and apd <= MAX_ALERTS_PER_DAY else "✗"
            print(f"  {p['name']}: {met} thr={best_thr:.1f}  {apd:.1f}/day  "
                  f"PPV={ppv:.2f}  sens={sens:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    # Summary
    meeting_both = sum(1 for v in results.values()
                       if v.get('meets_ppv_target') and v.get('meets_alert_target'))
    print(f"\n  Meeting both targets: {meeting_both}/{len(results)}")

    result = {
        'experiment': 'EXP-1616',
        'title': 'Per-Patient Threshold Optimization',
        'patients': results,
        'summary': {'meeting_both_targets': meeting_both},
    }
    _save_result(1616, result, time.time() - t0)
    return results


# ============================================================
# EXP-1617: Alert Fatigue Analysis
# ============================================================
def exp_1617(patients, baseline_results):
    """Analyze alert fatigue patterns: consecutive alerts, clustering, timing."""
    print("\n" + "─" * 60)
    print("EXP-1617: Alert Fatigue Analysis")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)
            days = n / STEPS_PER_DAY

            labels = _detect_hypo_events(glucose, threshold=70, horizon_steps=12)

            # Generate alerts at -2.0 threshold (common baseline)
            alert_times = []
            for i in range(12, n):
                feat = _compute_glucose_features(glucose, i)
                if feat and feat['rate'] < -2.0:
                    alert_times.append(i)

            if not alert_times:
                results[p['name']] = {'error': 'no_alerts'}
                continue

            # Cluster analysis: how many alerts come in bursts?
            gaps = np.diff(alert_times)
            burst_alerts = np.sum(gaps <= 6)  # Within 30 min = burst
            isolated_alerts = np.sum(gaps > 6)

            # Hour-of-day distribution
            alert_hours = [(t % STEPS_PER_DAY) / STEPS_PER_HOUR for t in alert_times]
            hour_dist = np.zeros(24)
            for h in alert_hours:
                hour_dist[int(h)] += 1
            hour_dist /= max(days, 1)

            # Actionability: what % of alerts are followed by actual hypo?
            actionable = 0
            for t in alert_times:
                future = glucose[t:min(n, t + 12)]
                if np.any(future < 70):
                    actionable += 1
            actionability = actionable / max(len(alert_times), 1)

            results[p['name']] = {
                'total_alerts': len(alert_times),
                'alerts_per_day': float(len(alert_times) / max(days, 1)),
                'burst_pct': float(burst_alerts / max(len(gaps), 1) * 100),
                'actionability': float(actionability),
                'peak_hour': int(np.argmax(hour_dist)),
                'peak_hour_rate': float(np.max(hour_dist)),
            }

            print(f"  {p['name']}: {len(alert_times)} alerts  "
                  f"burst={burst_alerts / max(len(gaps), 1) * 100:.0f}%  "
                  f"actionable={actionability:.0%}  "
                  f"peak hour={int(np.argmax(hour_dist)):02d}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1617',
        'title': 'Alert Fatigue Analysis',
        'patients': results,
    }
    _save_result(1617, result, time.time() - t0)
    return results


# ============================================================
# EXP-1618: Method Comparison Summary
# ============================================================
def exp_1618(patients, baseline, state_aware, multi_feat, tod, hierarchical, per_patient):
    """Compare all methods: which achieves best PPV at ≤5 alerts/day?"""
    print("\n" + "─" * 60)
    print("EXP-1618: Method Comparison Summary")
    print("─" * 60)
    t0 = time.time()

    methods = {
        'baseline_rate': baseline,
        'state_aware': state_aware,
        'multi_feature_lr': multi_feat,
        'time_of_day': tod,
        'hierarchical': hierarchical,
        'per_patient_opt': per_patient,
    }

    comparison = {}
    for method_name, method_results in methods.items():
        ppvs = []
        sensitivities = []
        apds = []

        for pname in sorted(method_results.keys()):
            pdata = method_results[pname]
            if isinstance(pdata, dict) and 'error' not in pdata:
                if method_name == 'baseline_rate':
                    # Use -2.0 threshold from baseline
                    thr_data = pdata.get('thresholds', {}).get('-2.0', {})
                    ppvs.append(thr_data.get('ppv', 0))
                    sensitivities.append(thr_data.get('sensitivity', 0))
                    apds.append(thr_data.get('alerts_per_day', 0))
                else:
                    ppvs.append(pdata.get('ppv', 0))
                    sensitivities.append(pdata.get('sensitivity', 0))
                    apds.append(pdata.get('alerts_per_day', pdata.get('stage2_alerts_per_day', 0)))

        comparison[method_name] = {
            'mean_ppv': float(np.mean(ppvs)) if ppvs else 0,
            'mean_sensitivity': float(np.mean(sensitivities)) if sensitivities else 0,
            'mean_alerts_per_day': float(np.mean(apds)) if apds else 0,
            'n_patients': len(ppvs),
        }

        print(f"  {method_name:25s}: PPV={comparison[method_name]['mean_ppv']:.3f}  "
              f"sens={comparison[method_name]['mean_sensitivity']:.3f}  "
              f"alerts={comparison[method_name]['mean_alerts_per_day']:.1f}/day")

    # Rank by F1 at ≤5 alerts/day
    print("\n  RANKING (by F1):")
    ranked = sorted(comparison.items(),
                    key=lambda x: 2 * x[1]['mean_ppv'] * x[1]['mean_sensitivity'] /
                    max(x[1]['mean_ppv'] + x[1]['mean_sensitivity'], 1e-10),
                    reverse=True)
    for i, (name, metrics) in enumerate(ranked):
        f1 = 2 * metrics['mean_ppv'] * metrics['mean_sensitivity'] / \
             max(metrics['mean_ppv'] + metrics['mean_sensitivity'], 1e-10)
        print(f"    {i+1}. {name}: F1={f1:.3f}")

    result = {
        'experiment': 'EXP-1618',
        'title': 'Method Comparison Summary',
        'comparison': comparison,
        'ranking': [{'method': name, 'f1': 2 * m['mean_ppv'] * m['mean_sensitivity'] /
                      max(m['mean_ppv'] + m['mean_sensitivity'], 1e-10)}
                     for name, m in ranked],
    }
    _save_result(1618, result, time.time() - t0)
    return comparison


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 70)
    print("EXP-1611-1618: Multi-Stage Alert Filtering")
    print("=" * 70)

    patients = _load_patients()
    print(f"Loaded {len(patients)} patients\n")

    # EXP-1611: Baseline
    baseline = exp_1611(patients)

    # EXP-1612: State-aware
    state_aware = exp_1612(patients)

    # EXP-1613: Multi-feature scoring
    multi_feat, all_features = exp_1613(patients)

    # EXP-1614: Time-of-day
    tod = exp_1614(patients, baseline)

    # EXP-1615: Hierarchical two-stage
    hierarchical = exp_1615(patients)

    # EXP-1616: Per-patient optimization
    per_patient = exp_1616(patients)

    # EXP-1617: Alert fatigue
    exp_1617(patients, baseline)

    # EXP-1618: Comparison summary
    exp_1618(patients, baseline, state_aware, multi_feat, tod, hierarchical, per_patient)

    print("\n" + "=" * 70)
    print("COMPLETE: 8/8 experiments")
    print("=" * 70)
