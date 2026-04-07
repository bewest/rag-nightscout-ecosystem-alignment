#!/usr/bin/env python3
"""EXP-991 through EXP-1000: Deep Clinical Intelligence and Optimization.

Building on EXP-981-990 findings:
- 8/10 patients have basal too high (EXP-985)
- Loop aggressiveness quantified (EXP-981)
- Composite fidelity score established (EXP-990)

Usage:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_991 --detail --save --max-patients 11
"""

import sys
import json
import time
import argparse
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import (
    load_patients, _extract_isf_scalar, _extract_cr_scalar, save_results,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]


def _get_local_hour(df):
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        local = df.index.tz_convert(tz)
    except Exception:
        local = df.index
    return np.array(local.hour + local.minute / 60.0)


def _get_basal_ratio(pk):
    return pk[:, 2] * PK_NORMS[2]


def _get_insulin_total(pk):
    return pk[:, 0] * PK_NORMS[0]


def _get_insulin_net(pk):
    return pk[:, 1] * PK_NORMS[1]


# ===================================================================
# EXP-991: Loop-Adjusted ISF Decomposition
# ===================================================================

def run_exp991(patients, args):
    """Compute ISF using only correction-attributable insulin.
    Subtract estimated basal contribution during correction windows."""
    print("\n" + "=" * 60)
    print("Running EXP-991: Loop-Adjusted ISF Decomposition")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        isf_profile = _extract_isf_scalar(df)
        ins_total = _get_insulin_total(pk)
        br = _get_basal_ratio(pk)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        basal_sched = df.attrs.get('basal_schedule', [])
        if basal_sched:
            mean_basal_rate = np.mean([s['value'] for s in basal_sched])
        else:
            mean_basal_rate = 1.0

        basal_per_step = mean_basal_rate / 60.0

        window = 3 * STEPS_PER_HOUR
        isf_corrected = []
        isf_naive = []

        i = 0
        while i < len(bg) - window:
            if bg[i] > 150 and bg[i] > 30:
                if np.sum(carbs[i:i + window]) < 3.0:
                    wbg = bg[i:i + window]
                    valid = wbg > 30
                    if np.sum(valid) > 12:
                        nadir = np.min(wbg[valid])
                        drop = bg[i] - nadir
                        total_ins = np.sum(ins_total[i:i + window]) * 5.0
                        baseline_ins = basal_per_step * window * 5.0
                        correction_ins = max(total_ins - baseline_ins, 0.01)

                        if drop > 10 and total_ins > 0.1:
                            isf_naive.append(drop / total_ins)
                            isf_corrected.append(drop / correction_ins)

                i += window
            else:
                i += 1

        if isf_corrected:
            mean_corrected = np.mean(isf_corrected)
            mean_naive = np.mean(isf_naive)
            per_patient.append({
                'patient': p['name'],
                'isf_profile': round(isf_profile, 1),
                'n_episodes': len(isf_corrected),
                'isf_naive_mean': round(mean_naive, 1),
                'isf_corrected_mean': round(mean_corrected, 1),
                'isf_corrected_median': round(np.median(isf_corrected), 1),
                'profile_vs_corrected_ratio': round(isf_profile / mean_corrected, 2),
                'improvement': round(
                    abs(isf_profile / mean_corrected - 1.0) -
                    abs(isf_profile / mean_naive - 1.0), 3),
            })
        else:
            per_patient.append({'patient': p['name'], 'n_episodes': 0})

    ratios = [pp['profile_vs_corrected_ratio'] for pp in per_patient
              if pp.get('profile_vs_corrected_ratio')]
    detail = "mean_ratio={:.2f}".format(np.mean(ratios)) if ratios else "no data"
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-991', 'name': 'Loop-Adjusted ISF Decomposition',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-992: Basal Rate Optimization via Supply/Demand
# ===================================================================

def run_exp992(patients, args):
    """Compute optimal basal rate per time segment that minimizes
    supply/demand imbalance. Compare to scheduled."""
    print("\n" + "=" * 60)
    print("Running EXP-992: Basal Rate Optimization via Supply/Demand")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        valid = bg > 30

        BLOCKS = [(0, 6), (6, 12), (12, 18), (18, 24)]
        block_results = {}
        for b_start, b_end in BLOCKS:
            mask = valid & (hours >= b_start) & (hours < b_end)
            if np.sum(mask) < 200:
                continue

            mean_net = np.mean(sd['net'][mask])
            mean_supply = np.mean(sd['supply'][mask])
            mean_demand = np.mean(sd['demand'][mask])
            mean_ratio = np.mean(br[mask])

            if abs(mean_supply) > 0.01:
                optimal_ratio_adj = 1 - mean_net / abs(mean_supply)
            else:
                optimal_ratio_adj = 1.0

            label = "{:02d}-{:02d}h".format(b_start, b_end)
            block_results[label] = {
                'mean_net_flux': round(mean_net, 3),
                'mean_supply': round(mean_supply, 3),
                'mean_demand': round(mean_demand, 3),
                'current_mean_ratio': round(mean_ratio, 3),
                'suggested_ratio_adj': round(optimal_ratio_adj, 3),
                'direction': 'decrease' if mean_net < -1 else 'increase' if mean_net > 1 else 'adequate',
            }

        per_patient.append({'patient': p['name'], 'blocks': block_results})

    detail = "patients={}".format(len(per_patient))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-992', 'name': 'Basal Rate Optimization via Supply/Demand',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-993: Multi-Week Rolling Fidelity
# ===================================================================

def run_exp993(patients, args):
    """Track composite fidelity score weekly. Detect trends and breakpoints."""
    print("\n" + "=" * 60)
    print("Running EXP-993: Multi-Week Rolling Fidelity")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        valid = bg > 30

        WEEK = 7 * STEPS_PER_DAY
        n_weeks = len(bg) // WEEK
        weekly_scores = []

        for w in range(n_weeks):
            start = w * WEEK
            end = start + WEEK
            wbg = bg[start:end]
            wbr = br[start:end]
            ws = sd['supply'][start:end]
            wd = sd['demand'][start:end]
            wn = sd['net'][start:end]
            v = wbg > 30

            if np.sum(v) < WEEK * 0.5:
                continue

            bg_v = wbg[v]
            tir = np.mean((bg_v >= 70) & (bg_v <= 180))
            cv = np.std(bg_v) / np.mean(bg_v) if np.mean(bg_v) > 0 else 0
            total_flux = np.sum(np.abs(ws[v]) + np.abs(wd[v]))
            net_int = np.abs(np.sum(wn[v]))
            balance = 1.0 - net_int / max(total_flux, 1e-6)
            loop_aggr = np.mean(np.abs(wbr[v] - 1.0))

            tir_s = min(25, tir * 25 / 0.7)
            cv_s = max(0, 25 * (1 - cv / 0.5))
            bal_s = max(0, balance * 25)
            calm_s = max(0, 25 * (1 - loop_aggr / 2.0))
            composite = round(tir_s + cv_s + bal_s + calm_s, 1)

            weekly_scores.append({
                'week': w + 1, 'score': composite,
                'tir': round(tir, 3), 'cv': round(cv, 3),
            })

        if len(weekly_scores) >= 5:
            scores = [ws['score'] for ws in weekly_scores]
            weeks = [ws['week'] for ws in weekly_scores]
            slope, _, r_val, p_val, _ = stats.linregress(weeks, scores)
            if slope > 0.5 and p_val < 0.1:
                trend = 'improving'
            elif slope < -0.5 and p_val < 0.1:
                trend = 'degrading'
            else:
                trend = 'stable'

            per_patient.append({
                'patient': p['name'],
                'n_weeks': len(weekly_scores),
                'mean_score': round(np.mean(scores), 1),
                'trend_slope': round(slope, 3),
                'trend_p': round(p_val, 4),
                'trend': trend,
                'weekly_scores': weekly_scores,
            })

    trends = [pp['trend'] for pp in per_patient]
    detail = "improving={}, stable={}, degrading={}".format(
        trends.count('improving'), trends.count('stable'), trends.count('degrading'))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-993', 'name': 'Multi-Week Rolling Fidelity',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-994: Temporal Cross-Correlation (Lead/Lag)
# ===================================================================

def run_exp994(patients, args):
    """Cross-correlate insulin_net with glucose_delta at multiple lags.
    Find the true physiological response time per patient."""
    print("\n" + "=" * 60)
    print("Running EXP-994: Temporal Cross-Correlation (Lead/Lag)")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        ins_net = _get_insulin_net(pk)
        valid = bg > 30

        delta_bg = np.zeros_like(bg)
        delta_bg[1:] = bg[1:] - bg[:-1]

        max_lag = 24  # 120 min
        lag_range = list(range(-max_lag, max_lag + 1))
        correlations = []

        for lag in lag_range:
            if lag >= 0:
                ins_shifted = ins_net[:len(ins_net) - lag] if lag > 0 else ins_net
                bg_shifted = delta_bg[lag:] if lag > 0 else delta_bg
            else:
                ins_shifted = ins_net[-lag:]
                bg_shifted = delta_bg[:lag]

            n = min(len(ins_shifted), len(bg_shifted))
            ins_s = ins_shifted[:n]
            bg_s = bg_shifted[:n]

            v = bg_s != 0
            if np.sum(v) > 100:
                r = np.corrcoef(ins_s[v], bg_s[v])[0, 1]
            else:
                r = 0
            correlations.append(round(r, 4))

        peak_idx = np.argmin(correlations)
        peak_lag_min = lag_range[peak_idx] * 5
        peak_corr = correlations[peak_idx]

        per_patient.append({
            'patient': p['name'],
            'peak_lag_min': peak_lag_min,
            'peak_correlation': peak_corr,
            'lag_profile': dict(zip([l * 5 for l in lag_range], correlations)),
        })

    peak_lags = [pp['peak_lag_min'] for pp in per_patient]
    peak_corrs = [pp['peak_correlation'] for pp in per_patient]
    detail = "mean_peak_lag={:.0f}min, mean_peak_corr={:.3f}".format(
        np.mean(peak_lags), np.mean(peak_corrs))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-994', 'name': 'Temporal Cross-Correlation',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-995: Conservation-Constrained Prediction
# ===================================================================

def run_exp995(patients, args):
    """Add physics prediction as feature. Does conservation-aware
    prediction improve R2?"""
    print("\n" + "=" * 60)
    print("Running EXP-995: Conservation-Constrained Prediction")
    print("=" * 60)
    t0 = time.time()

    from sklearn.linear_model import Ridge

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        h_steps = 12
        horizon = 12  # 60 min
        start = max(24, h_steps)

        features = []
        targets = []
        physics_pred = []

        for i in range(start, len(bg) - horizon):
            if not valid[i]:
                continue
            hist = bg[i - h_steps:i]
            pk_feat = pk[i, :]
            if np.any(hist <= 30):
                continue

            feat = np.concatenate([hist, pk_feat])
            features.append(feat)
            targets.append(bg[i + horizon] - bg[i])
            physics_pred.append(np.sum(sd['net'][i:i + horizon]))

        if len(features) < 200:
            continue

        X = np.array(features)
        y = np.array(targets)
        phys = np.array(physics_pred)

        n_train = int(0.8 * len(X))
        X_tr, X_te = X[:n_train], X[n_train:]
        y_tr, y_te = y[:n_train], y[n_train:]
        phys_tr, phys_te = phys[:n_train], phys[n_train:]

        # Baseline: pure Ridge
        model = Ridge(alpha=1.0)
        model.fit(X_tr, y_tr)
        pred_base = model.predict(X_te)
        ss_res = np.sum((y_te - pred_base) ** 2)
        ss_tot = np.sum((y_te - np.mean(y_te)) ** 2)
        r2_base = 1 - ss_res / max(ss_tot, 1e-6)

        # Physics-augmented
        X_aug_tr = np.column_stack([X_tr, phys_tr])
        X_aug_te = np.column_stack([X_te, phys_te])
        model_aug = Ridge(alpha=1.0)
        model_aug.fit(X_aug_tr, y_tr)
        pred_aug = model_aug.predict(X_aug_te)
        ss_res_aug = np.sum((y_te - pred_aug) ** 2)
        r2_aug = 1 - ss_res_aug / max(ss_tot, 1e-6)

        # Physics-only
        r2_phys_only = 1 - np.sum((y_te - phys_te) ** 2) / max(ss_tot, 1e-6)

        per_patient.append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 4),
            'r2_physics_augmented': round(r2_aug, 4),
            'r2_physics_only': round(r2_phys_only, 4),
            'improvement': round(r2_aug - r2_base, 4),
            'physics_coef': round(float(model_aug.coef_[-1]), 4),
            'n_samples': len(X),
        })

    improvements = [pp['improvement'] for pp in per_patient]
    detail = "mean_improvement={:+.4f}, positive={}/{}".format(
        np.mean(improvements),
        sum(1 for i in improvements if i > 0),
        len(improvements))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-995', 'name': 'Conservation-Constrained Prediction',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-996: AID Action Classification
# ===================================================================

def run_exp996(patients, args):
    """Classify loop actions from glucose context.
    What BG patterns trigger suspend vs high-temp?"""
    print("\n" + "=" * 60)
    print("Running EXP-996: AID Action Classification")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        br = _get_basal_ratio(pk)
        valid = bg > 30

        h_steps = 6  # 30 min history
        features = []
        labels = []

        for i in range(h_steps, len(bg)):
            if not valid[i]:
                continue
            hist = bg[i - h_steps:i]
            if np.any(hist <= 30):
                continue

            mean_bg = np.mean(hist)
            trend = (hist[-1] - hist[0]) / h_steps
            current = bg[i]

            feat = [current, mean_bg, trend, np.std(hist)]
            features.append(feat)

            if br[i] < 0.1:
                labels.append(0)  # suspended
            elif br[i] > 1.5:
                labels.append(2)  # high temp
            else:
                labels.append(1)  # nominal

        if len(features) < 500:
            continue

        X = np.array(features)
        y = np.array(labels)

        class_profiles = {}
        for cls, name in [(0, 'suspended'), (1, 'nominal'), (2, 'high_temp')]:
            mask = y == cls
            if np.sum(mask) > 10:
                class_profiles[name] = {
                    'count': int(np.sum(mask)),
                    'pct': round(float(np.mean(mask)), 3),
                    'mean_bg': round(float(np.mean(X[mask, 0])), 1),
                    'mean_trend': round(float(np.mean(X[mask, 2])), 3),
                    'mean_std': round(float(np.mean(X[mask, 3])), 2),
                }

        from sklearn.linear_model import LogisticRegression
        n_train = int(0.8 * len(X))
        lr = LogisticRegression(max_iter=1000)
        lr.fit(X[:n_train], y[:n_train])
        acc = lr.score(X[n_train:], y[n_train:])
        baseline_acc = float(max(np.bincount(y))) / len(y)

        per_patient.append({
            'patient': p['name'],
            'n_samples': len(X),
            'class_profiles': class_profiles,
            'classification_accuracy': round(acc, 3),
            'baseline_accuracy': round(baseline_acc, 3),
            'lift': round(acc - baseline_acc, 3),
        })

    accs = [pp['classification_accuracy'] for pp in per_patient]
    lifts = [pp['lift'] for pp in per_patient]
    detail = "mean_acc={:.3f}, mean_lift={:+.3f}".format(np.mean(accs), np.mean(lifts))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-996', 'name': 'AID Action Classification',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-997: Cross-Patient Transfer with Fidelity Matching
# ===================================================================

def run_exp997(patients, args):
    """Transfer prediction model from high-fidelity to low-fidelity patients."""
    print("\n" + "=" * 60)
    print("Running EXP-997: Cross-Patient Transfer with Fidelity Matching")
    print("=" * 60)
    t0 = time.time()

    from sklearn.linear_model import Ridge
    import random

    fidelity = {}
    patient_data = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        valid = bg > 30
        bg_v = bg[valid]

        if np.sum(valid) < 1000:
            continue

        tir = np.mean((bg_v >= 70) & (bg_v <= 180))
        cv = np.std(bg_v) / np.mean(bg_v)
        loop_aggr = np.mean(np.abs(br[valid] - 1.0))

        score = min(25, tir * 25 / 0.7) + max(0, 25 * (1 - cv / 0.5)) + max(0, 25 * (1 - loop_aggr / 2.0))
        fidelity[p['name']] = round(score, 1)

        h_steps = 12
        horizon = 12
        features = []
        targets = []
        for i in range(24, len(bg) - horizon):
            if not valid[i]:
                continue
            hist = bg[i - h_steps:i]
            if np.any(hist <= 30):
                continue
            feat = np.concatenate([hist, pk[i, :]])
            features.append(feat)
            targets.append(bg[i + horizon] - bg[i])

        if len(features) > 200:
            patient_data[p['name']] = (np.array(features), np.array(targets))

    results = []
    for target_name in sorted(patient_data.keys()):
        X_target, y_target = patient_data[target_name]
        n_test = len(X_target) // 5
        X_te, y_te = X_target[-n_test:], y_target[-n_test:]
        ss_tot = np.sum((y_te - np.mean(y_te)) ** 2)
        if ss_tot < 1e-6:
            continue

        X_tr_self = X_target[:-n_test]
        y_tr_self = y_target[:-n_test]
        model_self = Ridge(alpha=1.0)
        model_self.fit(X_tr_self, y_tr_self)
        r2_self = 1 - np.sum((y_te - model_self.predict(X_te)) ** 2) / ss_tot

        donors = sorted([(f, n) for n, f in fidelity.items() if n != target_name], reverse=True)
        if not donors:
            continue

        best_donor = donors[0][1]
        X_donor, y_donor = patient_data[best_donor]
        model_donor = Ridge(alpha=1.0)
        model_donor.fit(X_donor, y_donor)
        r2_transfer = 1 - np.sum((y_te - model_donor.predict(X_te)) ** 2) / ss_tot

        random.seed(42)
        rand_donor = random.choice([n for n in patient_data if n != target_name])
        X_rand, y_rand = patient_data[rand_donor]
        model_rand = Ridge(alpha=1.0)
        model_rand.fit(X_rand, y_rand)
        r2_random = 1 - np.sum((y_te - model_rand.predict(X_te)) ** 2) / ss_tot

        results.append({
            'target': target_name,
            'target_fidelity': fidelity[target_name],
            'best_donor': best_donor,
            'donor_fidelity': fidelity[best_donor],
            'r2_self': round(r2_self, 4),
            'r2_fidelity_transfer': round(r2_transfer, 4),
            'r2_random_transfer': round(r2_random, 4),
            'fidelity_vs_random': round(r2_transfer - r2_random, 4),
            'fidelity_vs_self': round(r2_transfer - r2_self, 4),
        })

    fidelity_wins = sum(1 for r in results if r['fidelity_vs_random'] > 0)
    detail = "fidelity_beats_random={}/{}".format(fidelity_wins, len(results))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-997', 'name': 'Cross-Patient Transfer with Fidelity Matching',
            'status': 'pass', 'detail': detail,
            'results': {'transfers': results}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-998: Overnight Basal Titration Protocol
# ===================================================================

def run_exp998(patients, args):
    """Virtual overnight basal titration: find basal rate producing zero
    glucose drift overnight."""
    print("\n" + "=" * 60)
    print("Running EXP-998: Overnight Basal Titration Protocol")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        basal_sched = df.attrs.get('basal_schedule', [])
        if not basal_sched:
            continue

        NIGHT_LEN = 6 * STEPS_PER_HOUR
        n_days = len(bg) // STEPS_PER_DAY

        night_drifts = []
        night_ratios = []
        night_bgs = []

        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + NIGHT_LEN
            if end > len(bg):
                break

            wbg = bg[start:end]
            wcarbs = carbs[start:end]
            wbolus = bolus[start:end]
            wbr = br[start:end]
            v = wbg > 30

            if np.sum(wcarbs) > 3 or np.sum(wbolus) > 0.1:
                continue
            if np.sum(v) < NIGHT_LEN * 0.7:
                continue

            x = np.arange(np.sum(v))
            y_vals = wbg[v]
            if len(x) < 12:
                continue
            slope, _, _, _, _ = stats.linregress(x, y_vals)
            drift_per_hour = slope * STEPS_PER_HOUR

            night_drifts.append(drift_per_hour)
            night_ratios.append(np.mean(wbr[v]))
            night_bgs.append(np.mean(wbg[v]))

        if len(night_drifts) < 5:
            continue

        mean_drift = np.mean(night_drifts)
        isf = _extract_isf_scalar(df)
        midnight_basal = basal_sched[0]['value']
        adjustment_u_per_hr = mean_drift / isf if isf > 0 else 0
        optimal_basal = max(0.05, midnight_basal + adjustment_u_per_hr)

        per_patient.append({
            'patient': p['name'],
            'n_valid_nights': len(night_drifts),
            'mean_overnight_drift': round(mean_drift, 2),
            'mean_overnight_ratio': round(np.mean(night_ratios), 3),
            'mean_overnight_bg': round(np.mean(night_bgs), 1),
            'scheduled_basal': round(midnight_basal, 2),
            'optimal_basal': round(optimal_basal, 2),
            'adjustment': round(optimal_basal - midnight_basal, 3),
            'pct_change': round((optimal_basal - midnight_basal) / max(midnight_basal, 0.01) * 100, 1),
        })

    adjustments = [pp['pct_change'] for pp in per_patient]
    detail = "mean_adjustment={:+.1f}%, patients={}".format(
        np.mean(adjustments), len(per_patient))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-998', 'name': 'Overnight Basal Titration Protocol',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-999: Residual Autocorrelation by Clinical Context
# ===================================================================

def run_exp999(patients, args):
    """Map residual persistence to clinical context."""
    print("\n" + "=" * 60)
    print("Running EXP-999: Residual Autocorrelation by Clinical Context")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        delta_bg = np.zeros_like(bg)
        delta_bg[1:] = bg[1:] - bg[:-1]
        residual = delta_bg - sd['net']

        context_results = {}

        # Define context filters
        ctx_defs = [
            ('fasting', lambda i: valid[i] and carbs[max(0, i - 36):i].sum() < 3),
            ('postmeal', lambda i: valid[i] and carbs[max(0, i - 36):i].sum() >= 5),
            ('overnight', lambda i: valid[i] and 0 <= hours[i] < 6),
            ('daytime', lambda i: valid[i] and 8 <= hours[i] < 20),
            ('loop_active', lambda i: valid[i] and (br[i] < 0.5 or br[i] > 1.5)),
            ('loop_nominal', lambda i: valid[i] and 0.8 <= br[i] <= 1.2),
        ]

        for ctx_name, ctx_fn in ctx_defs:
            indices = [i for i in range(36, len(bg) - 12) if ctx_fn(i)]
            if len(indices) < 200:
                context_results[ctx_name] = {'n_points': len(indices), 'insufficient': True}
                continue

            ctx_residuals = residual[indices]

            autocorrs = []
            for lag in [1, 2, 3, 6, 12]:
                r_shifted = np.array([
                    residual[i + lag] if i + lag < len(residual) else 0
                    for i in indices
                ])
                valid_both = (ctx_residuals != 0) & (r_shifted != 0)
                if np.sum(valid_both) > 50:
                    corr = np.corrcoef(ctx_residuals[valid_both], r_shifted[valid_both])[0, 1]
                else:
                    corr = 0
                autocorrs.append(round(float(corr), 3))

            if autocorrs[2] > 0.3:
                persistence = 'high'
            elif autocorrs[2] > 0.1:
                persistence = 'medium'
            else:
                persistence = 'low'

            context_results[ctx_name] = {
                'n_points': len(indices),
                'mean_abs_residual': round(float(np.mean(np.abs(ctx_residuals))), 3),
                'autocorr_5min': autocorrs[0],
                'autocorr_10min': autocorrs[1],
                'autocorr_15min': autocorrs[2],
                'autocorr_30min': autocorrs[3],
                'autocorr_60min': autocorrs[4],
                'persistence': persistence,
            }

        per_patient.append({'patient': p['name'], 'contexts': context_results})

    ctx_persistence = {}
    for ctx in ['fasting', 'postmeal', 'overnight', 'daytime', 'loop_active', 'loop_nominal']:
        autocorrs = [
            pp['contexts'].get(ctx, {}).get('autocorr_15min', 0)
            for pp in per_patient
        ]
        valid_autocorrs = [a for a in autocorrs if a != 0]
        if valid_autocorrs:
            ctx_persistence[ctx] = round(np.mean(valid_autocorrs), 3)

    most_persistent = max(ctx_persistence, key=ctx_persistence.get) if ctx_persistence else 'unknown'
    detail = "most_persistent={}({:.3f})".format(
        most_persistent, ctx_persistence.get(most_persistent, 0))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-999', 'name': 'Residual Autocorrelation by Clinical Context',
            'status': 'pass', 'detail': detail,
            'results': {'ctx_persistence': ctx_persistence, 'per_patient': per_patient},
            'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1000: Grand Fidelity Assessment
# ===================================================================

def run_exp1000(patients, args):
    """Combine all clinical metrics into comprehensive per-patient report."""
    print("\n" + "=" * 60)
    print("Running EXP-1000: Grand Fidelity Assessment")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        valid = bg > 30
        bg_v = bg[valid]

        if np.sum(valid) < 1000:
            continue

        isf_profile = _extract_isf_scalar(df)
        cr_profile = _extract_cr_scalar(df)
        dia = df.attrs.get('patient_dia', 6.0)

        # Glucose metrics
        tir = np.mean((bg_v >= 70) & (bg_v <= 180))
        tbr = np.mean(bg_v < 70)
        tar = np.mean(bg_v > 180)
        cv = np.std(bg_v) / np.mean(bg_v)
        mean_bg = np.mean(bg_v)
        gmi = 3.31 + 0.02392 * mean_bg

        # Loop metrics
        loop_aggr = np.mean(np.abs(br[valid] - 1.0))
        pct_suspended = np.mean(br[valid] < 0.1)
        pct_high = np.mean(br[valid] > 1.5)
        pct_nominal = np.mean((br[valid] >= 0.9) & (br[valid] <= 1.1))

        # Supply/demand metrics
        supply = sd['supply'][valid]
        demand = sd['demand'][valid]
        net = sd['net'][valid]
        total_flux = np.sum(np.abs(supply) + np.abs(demand))
        balance = 1 - np.abs(np.sum(net)) / max(total_flux, 1e-6)

        # Conservation quality
        delta_bg = np.zeros_like(bg)
        delta_bg[1:] = bg[1:] - bg[:-1]
        violation = np.abs(delta_bg[valid] - sd['net'][valid])
        conservation_rmse = np.sqrt(np.mean(violation ** 2))

        # Fidelity score
        tir_s = min(25, tir * 25 / 0.7)
        cv_s = max(0, 25 * (1 - cv / 0.5))
        bal_s = max(0, balance * 25)
        calm_s = max(0, 25 * (1 - loop_aggr / 2.0))
        fidelity_score = round(tir_s + cv_s + bal_s + calm_s, 1)

        # Recommendations
        recommendations = []
        if pct_suspended > 0.5:
            recommendations.append('Consider reducing overnight basal rate')
        if loop_aggr > 1.5:
            recommendations.append('Settings may need comprehensive review')
        if tbr > 0.04:
            recommendations.append('Time below range {:.1%} exceeds 4% target'.format(tbr))
        if tar > 0.25:
            recommendations.append('Time above range {:.1%} exceeds 25% target'.format(tar))
        if cv > 0.36:
            recommendations.append('Glucose variability (CV={:.2f}) exceeds 36% target'.format(cv))
        if fidelity_score < 50:
            recommendations.append('Low fidelity score suggests significant settings miscalibration')

        per_patient.append({
            'patient': p['name'],
            'glucose_metrics': {
                'mean_bg': round(mean_bg, 1),
                'tir': round(tir, 3),
                'tbr': round(tbr, 3),
                'tar': round(tar, 3),
                'cv': round(cv, 3),
                'gmi': round(gmi, 1),
            },
            'loop_metrics': {
                'aggressiveness': round(loop_aggr, 3),
                'pct_suspended': round(pct_suspended, 3),
                'pct_high_temp': round(pct_high, 3),
                'pct_nominal': round(pct_nominal, 3),
            },
            'physics_metrics': {
                'supply_demand_balance': round(balance, 3),
                'conservation_rmse': round(conservation_rmse, 2),
            },
            'profile_settings': {
                'isf': round(isf_profile, 1),
                'cr': round(cr_profile, 1),
                'dia': dia,
            },
            'fidelity_score': fidelity_score,
            'fidelity_components': {
                'tir': round(tir_s, 1),
                'cv': round(cv_s, 1),
                'balance': round(bal_s, 1),
                'calm': round(calm_s, 1),
            },
            'n_recommendations': len(recommendations),
            'recommendations': recommendations,
        })

    per_patient.sort(key=lambda x: x['fidelity_score'], reverse=True)
    for rank, pp in enumerate(per_patient):
        pp['rank'] = rank + 1

    scores = [pp['fidelity_score'] for pp in per_patient]
    n_recs = sum(pp['n_recommendations'] for pp in per_patient)
    detail = "mean_fidelity={:.1f}/100, total_recommendations={}".format(
        np.mean(scores), n_recs)
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1000', 'name': 'Grand Fidelity Assessment',
            'status': 'pass', 'detail': detail,
            'results': {'mean_fidelity': round(np.mean(scores), 1),
                        'per_patient': per_patient},
            'elapsed_seconds': elapsed}


# ===================================================================
# Main
# ===================================================================

EXPERIMENTS = {
    991: ('Loop-Adjusted ISF Decomposition', run_exp991),
    992: ('Basal Rate Optimization via Supply/Demand', run_exp992),
    993: ('Multi-Week Rolling Fidelity', run_exp993),
    994: ('Temporal Cross-Correlation', run_exp994),
    995: ('Conservation-Constrained Prediction', run_exp995),
    996: ('AID Action Classification', run_exp996),
    997: ('Cross-Patient Transfer with Fidelity Matching', run_exp997),
    998: ('Overnight Basal Titration Protocol', run_exp998),
    999: ('Residual Autocorrelation by Clinical Context', run_exp999),
    1000: ('Grand Fidelity Assessment', run_exp1000),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-991-1000: Deep Clinical Intelligence')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all')
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)

    if args.experiments == 'all':
        exp_nums = sorted(EXPERIMENTS.keys())
    else:
        exp_nums = [int(x.strip()) for x in args.experiments.split(',')]

    for num in exp_nums:
        if num not in EXPERIMENTS:
            print("Unknown experiment: {}".format(num))
            continue
        name, func = EXPERIMENTS[num]
        try:
            result = func(patients, args)
            if args.save and result and result.get('status') != 'error':
                save_dir = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
                save_dir.mkdir(parents=True, exist_ok=True)
                safe_name = name.lower().replace(' ', '_').replace('+', '_').replace('/', '_').replace('-', '_')
                fname = save_dir / "exp_exp_{}_{}.json".format(num, safe_name)
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print("  Saved: {}".format(fname))
        except Exception as e:
            print("  ERROR in EXP-{}: {}".format(num, e))
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("All experiments complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
