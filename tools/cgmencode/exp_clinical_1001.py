#!/usr/bin/env python3
"""EXP-1001 through EXP-1010: Multi-Scale and Meal Modeling.

Building on EXP-981-1000 findings:
- Physics augmentation helps 9/11 patients (+0.025 R2) (EXP-995)
- Postmeal residuals are most persistent (EXP-999)
- 3/11 have predictive 3-day patterns (EXP-986)
- Insulin-to-glucose lag varies 15-50 min (EXP-994)

This batch focuses on:
- Meal absorption modeling (biggest residual source)
- Multi-horizon physics augmentation
- Patient-specific lag compensation
- Multi-day feature engineering
- Conservation-penalized training

Usage:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1001 --detail --save --max-patients 11
"""

import sys
import json
import time
import argparse
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge

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


def _build_features(bg, pk, h_steps=12, horizon=12, start=24):
    """Build standard prediction features and targets."""
    valid = bg > 30
    features = []
    targets = []
    indices = []
    for i in range(start, len(bg) - horizon):
        if not valid[i]:
            continue
        hist = bg[i - h_steps:i]
        if np.any(hist <= 30):
            continue
        feat = np.concatenate([hist, pk[i, :]])
        features.append(feat)
        targets.append(bg[i + horizon] - bg[i])
        indices.append(i)
    if not features:
        return None, None, None
    return np.array(features), np.array(targets), np.array(indices)


def _eval_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot < 1e-6:
        return 0.0
    return 1 - ss_res / ss_tot


# ===================================================================
# EXP-1001: Postprandial Residual Characterization
# ===================================================================

def run_exp1001(patients, args):
    """Characterize prediction residuals in postprandial windows.
    What patterns do residuals show after meals?"""
    print("\n" + "=" * 60)
    print("Running EXP-1001: Postprandial Residual Characterization")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        delta_bg = np.zeros_like(bg)
        delta_bg[1:] = bg[1:] - bg[:-1]
        residual = delta_bg - sd['net']

        # Find meal events (carbs > 10g)
        meal_indices = np.where(carbs > 10)[0]
        if len(meal_indices) < 5:
            continue

        # Analyze residual pattern in 0-4h after each meal
        POSTMEAL_HOURS = 4
        POSTMEAL_STEPS = POSTMEAL_HOURS * STEPS_PER_HOUR
        time_bins = list(range(0, POSTMEAL_STEPS, STEPS_PER_HOUR))  # hourly bins

        hourly_residuals = {h: [] for h in range(POSTMEAL_HOURS)}
        hourly_bg_change = {h: [] for h in range(POSTMEAL_HOURS)}
        meal_sizes = []

        for mi in meal_indices:
            if mi + POSTMEAL_STEPS >= len(bg):
                continue
            meal_sizes.append(carbs[mi])

            for h in range(POSTMEAL_HOURS):
                start_idx = mi + h * STEPS_PER_HOUR
                end_idx = start_idx + STEPS_PER_HOUR
                if end_idx > len(bg):
                    break
                mask = valid[start_idx:end_idx]
                if np.sum(mask) > 6:
                    hourly_residuals[h].append(np.mean(residual[start_idx:end_idx][mask]))
                    hourly_bg_change[h].append(np.mean(delta_bg[start_idx:end_idx][mask]))

        profile = {}
        for h in range(POSTMEAL_HOURS):
            if hourly_residuals[h]:
                profile["hour_{}".format(h)] = {
                    'mean_residual': round(float(np.mean(hourly_residuals[h])), 3),
                    'std_residual': round(float(np.std(hourly_residuals[h])), 3),
                    'mean_bg_change': round(float(np.mean(hourly_bg_change[h])), 3),
                    'n_meals': len(hourly_residuals[h]),
                }

        # Does meal size correlate with residual magnitude?
        if len(meal_sizes) > 10 and hourly_residuals[1]:
            # Use hour-1 (peak absorption) residual
            first_hour_res = hourly_residuals[1][:len(meal_sizes)]
            if len(first_hour_res) == len(meal_sizes):
                r, p_val = stats.pearsonr(meal_sizes, first_hour_res)
            else:
                r, p_val = 0, 1
        else:
            r, p_val = 0, 1

        per_patient.append({
            'patient': p['name'],
            'n_meals': len(meal_indices),
            'mean_meal_size': round(float(np.mean(meal_sizes)), 1),
            'postprandial_profile': profile,
            'size_residual_corr': round(float(r), 3),
            'size_residual_p': round(float(p_val), 4),
        })

    detail = "patients={}, mean_meals={}".format(
        len(per_patient),
        round(np.mean([pp['n_meals'] for pp in per_patient]), 0))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1001', 'name': 'Postprandial Residual Characterization',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1002: Lag-Compensated Physics Augmentation
# ===================================================================

def run_exp1002(patients, args):
    """Use patient-specific lag from EXP-994 to time-shift the physics
    prediction before using it as a feature."""
    print("\n" + "=" * 60)
    print("Running EXP-1002: Lag-Compensated Physics Augmentation")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        X, y, indices = _build_features(bg, pk)
        if X is None or len(X) < 200:
            continue

        n_train = int(0.8 * len(X))

        # Baseline (no physics)
        model_base = Ridge(alpha=1.0)
        model_base.fit(X[:n_train], y[:n_train])
        r2_base = _eval_r2(y[n_train:], model_base.predict(X[n_train:]))

        # Test multiple lags
        best_lag = 0
        best_r2 = r2_base
        lag_results = {}

        for lag_steps in [0, 3, 6, 9, 12, 15, 18, 24]:
            # Physics prediction with lag compensation
            horizon = 12
            phys = np.zeros(len(indices))
            for j, idx in enumerate(indices):
                lag_start = idx - lag_steps
                lag_end = lag_start + horizon
                if 0 <= lag_start < len(sd['net']) and lag_end <= len(sd['net']):
                    phys[j] = np.sum(sd['net'][lag_start:lag_end])

            X_aug = np.column_stack([X, phys])
            model = Ridge(alpha=1.0)
            model.fit(X_aug[:n_train], y[:n_train])
            r2 = _eval_r2(y[n_train:], model.predict(X_aug[n_train:]))

            lag_min = lag_steps * 5
            lag_results[lag_min] = round(r2, 4)
            if r2 > best_r2:
                best_r2 = r2
                best_lag = lag_min

        per_patient.append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 4),
            'r2_best_lag': round(best_r2, 4),
            'best_lag_min': best_lag,
            'improvement': round(best_r2 - r2_base, 4),
            'lag_sweep': lag_results,
        })

    improvements = [pp['improvement'] for pp in per_patient]
    lags = [pp['best_lag_min'] for pp in per_patient]
    detail = "mean_improvement={:+.4f}, mean_best_lag={:.0f}min".format(
        np.mean(improvements), np.mean(lags))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1002', 'name': 'Lag-Compensated Physics Augmentation',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1003: Multi-Horizon Physics Augmentation
# ===================================================================

def run_exp1003(patients, args):
    """Add physics predictions at multiple horizons as features simultaneously."""
    print("\n" + "=" * 60)
    print("Running EXP-1003: Multi-Horizon Physics Augmentation")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])

        X, y, indices = _build_features(bg, pk)
        if X is None or len(X) < 200:
            continue

        n_train = int(0.8 * len(X))

        # Baseline
        model_base = Ridge(alpha=1.0)
        model_base.fit(X[:n_train], y[:n_train])
        r2_base = _eval_r2(y[n_train:], model_base.predict(X[n_train:]))

        # Single physics (60 min)
        phys_60 = np.array([np.sum(sd['net'][idx:idx + 12]) for idx in indices])
        X_single = np.column_stack([X, phys_60])
        model_single = Ridge(alpha=1.0)
        model_single.fit(X_single[:n_train], y[:n_train])
        r2_single = _eval_r2(y[n_train:], model_single.predict(X_single[n_train:]))

        # Multi-horizon: 15, 30, 60, 120 min physics predictions
        horizons = [3, 6, 12, 24]
        phys_multi = np.zeros((len(indices), len(horizons)))
        for j, idx in enumerate(indices):
            for h_i, h in enumerate(horizons):
                end = min(idx + h, len(sd['net']))
                phys_multi[j, h_i] = np.sum(sd['net'][idx:end])

        X_multi = np.column_stack([X, phys_multi])
        model_multi = Ridge(alpha=1.0)
        model_multi.fit(X_multi[:n_train], y[:n_train])
        r2_multi = _eval_r2(y[n_train:], model_multi.predict(X_multi[n_train:]))

        # Multi-horizon + supply/demand decomposition
        phys_decomp = np.zeros((len(indices), len(horizons) * 2))
        for j, idx in enumerate(indices):
            for h_i, h in enumerate(horizons):
                end = min(idx + h, len(sd['supply']))
                phys_decomp[j, h_i * 2] = np.sum(sd['supply'][idx:end])
                phys_decomp[j, h_i * 2 + 1] = np.sum(sd['demand'][idx:end])

        X_decomp = np.column_stack([X, phys_decomp])
        model_decomp = Ridge(alpha=1.0)
        model_decomp.fit(X_decomp[:n_train], y[:n_train])
        r2_decomp = _eval_r2(y[n_train:], model_decomp.predict(X_decomp[n_train:]))

        per_patient.append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 4),
            'r2_single_physics': round(r2_single, 4),
            'r2_multi_horizon': round(r2_multi, 4),
            'r2_decomposed': round(r2_decomp, 4),
            'improvement_single': round(r2_single - r2_base, 4),
            'improvement_multi': round(r2_multi - r2_base, 4),
            'improvement_decomp': round(r2_decomp - r2_base, 4),
        })

    imp_multi = [pp['improvement_multi'] for pp in per_patient]
    imp_decomp = [pp['improvement_decomp'] for pp in per_patient]
    detail = "multi={:+.4f}, decomp={:+.4f}".format(np.mean(imp_multi), np.mean(imp_decomp))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1003', 'name': 'Multi-Horizon Physics Augmentation',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1004: Meal Absorption Rate Estimation
# ===================================================================

def run_exp1004(patients, args):
    """Estimate actual meal absorption rates from glucose response patterns.
    Compare to the PK model's assumed absorption curve."""
    print("\n" + "=" * 60)
    print("Running EXP-1004: Meal Absorption Rate Estimation")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        # Find isolated meals (>10g carbs, no other meal within 3h)
        meal_indices = []
        for i in range(len(carbs)):
            if carbs[i] > 10:
                # Check isolation: no other carbs within +/- 3h
                window_start = max(0, i - 3 * STEPS_PER_HOUR)
                window_end = min(len(carbs), i + 3 * STEPS_PER_HOUR)
                other_carbs = np.sum(carbs[window_start:i]) + np.sum(carbs[i + 1:window_end])
                if other_carbs < 5:
                    meal_indices.append(i)

        if len(meal_indices) < 3:
            continue

        # For each meal, measure glucose response curve
        RESPONSE_HOURS = 4
        RESPONSE_STEPS = RESPONSE_HOURS * STEPS_PER_HOUR
        peak_times = []
        peak_rises = []
        return_times = []
        absorption_profiles = []

        for mi in meal_indices:
            if mi + RESPONSE_STEPS >= len(bg) or mi < 6:
                continue

            pre_bg = np.mean(bg[mi - 6:mi]) if bg[mi - 6:mi].mean() > 30 else bg[mi]
            response = bg[mi:mi + RESPONSE_STEPS] - pre_bg
            v = bg[mi:mi + RESPONSE_STEPS] > 30

            if np.sum(v) < RESPONSE_STEPS * 0.5:
                continue

            # Peak glucose rise
            peak_idx = np.argmax(response[:np.sum(v)])
            peak_time_min = peak_idx * 5
            peak_rise = response[peak_idx]

            peak_times.append(peak_time_min)
            peak_rises.append(peak_rise)

            # Time to return to baseline
            returned = False
            for ret_idx in range(peak_idx, np.sum(v)):
                if response[ret_idx] <= 0:
                    return_times.append(ret_idx * 5)
                    returned = True
                    break
            if not returned:
                return_times.append(RESPONSE_HOURS * 60)

            # Normalized absorption profile (glucose rise / carbs)
            meal_size = carbs[mi]
            if meal_size > 0:
                norm_response = response[:np.sum(v)] / meal_size
                absorption_profiles.append(norm_response[:24])  # 2h profile

        if peak_times:
            per_patient.append({
                'patient': p['name'],
                'n_isolated_meals': len(meal_indices),
                'n_analyzed': len(peak_times),
                'mean_peak_time_min': round(float(np.mean(peak_times)), 0),
                'median_peak_time_min': round(float(np.median(peak_times)), 0),
                'std_peak_time_min': round(float(np.std(peak_times)), 0),
                'mean_peak_rise': round(float(np.mean(peak_rises)), 1),
                'mean_return_time_min': round(float(np.mean(return_times)), 0),
            })

    peak_ts = [pp['mean_peak_time_min'] for pp in per_patient]
    detail = "patients={}, mean_peak={:.0f}min".format(len(per_patient), np.mean(peak_ts))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1004', 'name': 'Meal Absorption Rate Estimation',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1005: Daily Summary Features for Multi-Day Prediction
# ===================================================================

def run_exp1005(patients, args):
    """Create daily summary features (TIR, mean BG, CV, supply/demand balance)
    and test if previous days' summaries improve next-day prediction."""
    print("\n" + "=" * 60)
    print("Running EXP-1005: Daily Summary Features for Multi-Day Prediction")
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

        n_days = len(bg) // STEPS_PER_DAY
        if n_days < 14:
            continue

        # Compute daily features
        daily_features = []
        daily_targets = []  # next-day mean TIR

        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            dbg = bg[start:end]
            v = dbg > 30

            if np.sum(v) < STEPS_PER_DAY * 0.5:
                daily_features.append(None)
                daily_targets.append(None)
                continue

            bg_v = dbg[v]
            tir = np.mean((bg_v >= 70) & (bg_v <= 180))
            mean_bg = np.mean(bg_v)
            cv_d = np.std(bg_v) / np.mean(bg_v)
            loop_aggr = np.mean(np.abs(br[start:end][v] - 1.0))
            net_supply = np.sum(sd['supply'][start:end][v])
            net_demand = np.sum(sd['demand'][start:end][v])
            balance = net_supply / (abs(net_demand) + 1e-6)

            daily_features.append([tir, mean_bg, cv_d, loop_aggr, balance])
            daily_targets.append(tir)

        # Build multi-day prediction dataset
        LOOKBACK_DAYS = 3
        X_daily = []
        y_daily = []

        for d in range(LOOKBACK_DAYS, n_days - 1):
            # Check all lookback days have data
            all_valid = True
            feat = []
            for lb in range(LOOKBACK_DAYS):
                df_idx = d - LOOKBACK_DAYS + lb
                if daily_features[df_idx] is None:
                    all_valid = False
                    break
                feat.extend(daily_features[df_idx])

            if not all_valid or daily_targets[d + 1] is None:
                continue

            X_daily.append(feat)
            y_daily.append(daily_targets[d + 1])

        if len(X_daily) < 20:
            continue

        X_d = np.array(X_daily)
        y_d = np.array(y_daily)

        n_train = int(0.8 * len(X_d))

        # Baseline: predict tomorrow = today
        persistence = y_d[:-1]
        if len(persistence) > n_train:
            r2_persist = _eval_r2(y_d[n_train:], np.array([y_d[n_train - 1]] + list(y_d[n_train:-1])))
        else:
            r2_persist = 0

        # Multi-day model
        model = Ridge(alpha=1.0)
        model.fit(X_d[:n_train], y_d[:n_train])
        r2_multi = _eval_r2(y_d[n_train:], model.predict(X_d[n_train:]))

        per_patient.append({
            'patient': p['name'],
            'n_days': n_days,
            'n_samples': len(X_daily),
            'r2_persistence': round(r2_persist, 4),
            'r2_multiday': round(r2_multi, 4),
            'improvement': round(r2_multi - r2_persist, 4),
            'features_used': LOOKBACK_DAYS * 5,
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
    return {'experiment': 'EXP-1005', 'name': 'Daily Summary Features',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1006: Meal-Aware Prediction (Postprandial Indicator Features)
# ===================================================================

def run_exp1006(patients, args):
    """Add meal-context features to the prediction model.
    Time-since-last-meal, meal-size, postprandial-phase indicator."""
    print("\n" + "=" * 60)
    print("Running EXP-1006: Meal-Aware Prediction Features")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        # Pre-compute meal context for each timestep
        time_since_meal = np.full(len(bg), 999.0)  # minutes since last meal
        last_meal_size = np.zeros(len(bg))
        cumulative_carbs_3h = np.zeros(len(bg))

        last_meal_idx = -1
        last_meal_carbs = 0
        for i in range(len(carbs)):
            if carbs[i] > 5:
                last_meal_idx = i
                last_meal_carbs = carbs[i]
            if last_meal_idx >= 0:
                time_since_meal[i] = (i - last_meal_idx) * 5
                last_meal_size[i] = last_meal_carbs

            # Cumulative carbs in last 3h
            start = max(0, i - 3 * STEPS_PER_HOUR)
            cumulative_carbs_3h[i] = np.sum(carbs[start:i + 1])

        X, y, indices = _build_features(bg, pk)
        if X is None or len(X) < 200:
            continue

        n_train = int(0.8 * len(X))

        # Baseline
        model_base = Ridge(alpha=1.0)
        model_base.fit(X[:n_train], y[:n_train])
        r2_base = _eval_r2(y[n_train:], model_base.predict(X[n_train:]))

        # Meal-aware features
        meal_feats = np.zeros((len(indices), 4))
        for j, idx in enumerate(indices):
            meal_feats[j, 0] = min(time_since_meal[idx], 240) / 240.0  # normalized
            meal_feats[j, 1] = last_meal_size[idx] / 100.0  # normalized
            meal_feats[j, 2] = cumulative_carbs_3h[idx] / 100.0
            meal_feats[j, 3] = 1.0 if time_since_meal[idx] < 120 else 0.0  # postprandial flag

        X_meal = np.column_stack([X, meal_feats])
        model_meal = Ridge(alpha=1.0)
        model_meal.fit(X_meal[:n_train], y[:n_train])
        r2_meal = _eval_r2(y[n_train:], model_meal.predict(X_meal[n_train:]))

        # Combined: meal + physics
        phys = np.array([np.sum(sd['net'][idx:idx + 12]) for idx in indices])
        X_combined = np.column_stack([X, meal_feats, phys.reshape(-1, 1)])
        model_comb = Ridge(alpha=1.0)
        model_comb.fit(X_combined[:n_train], y[:n_train])
        r2_comb = _eval_r2(y[n_train:], model_comb.predict(X_combined[n_train:]))

        per_patient.append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 4),
            'r2_meal_aware': round(r2_meal, 4),
            'r2_meal_plus_physics': round(r2_comb, 4),
            'improvement_meal': round(r2_meal - r2_base, 4),
            'improvement_combined': round(r2_comb - r2_base, 4),
        })

    imp_meal = [pp['improvement_meal'] for pp in per_patient]
    imp_comb = [pp['improvement_combined'] for pp in per_patient]
    detail = "meal={:+.4f}, combined={:+.4f}".format(np.mean(imp_meal), np.mean(imp_comb))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1006', 'name': 'Meal-Aware Prediction Features',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1007: Conservation Violation as Training Signal
# ===================================================================

def run_exp1007(patients, args):
    """Train model to predict conservation violation. If the model can
    predict where conservation fails, those regions need extra modeling."""
    print("\n" + "=" * 60)
    print("Running EXP-1007: Conservation Violation as Training Signal")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        hours = _get_local_hour(df)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        delta_bg = np.zeros_like(bg)
        delta_bg[1:] = bg[1:] - bg[:-1]
        violation = delta_bg - sd['net']

        # Features for violation prediction
        h_steps = 12
        features = []
        targets = []
        for i in range(h_steps, len(bg)):
            if not valid[i]:
                continue
            hist = bg[i - h_steps:i]
            if np.any(hist <= 30):
                continue

            feat = list(hist) + list(pk[i, :])
            feat.append(hours[i] / 24.0)
            feat.append(np.sum(carbs[max(0, i - 36):i]) / 100.0)
            features.append(feat)
            targets.append(violation[i])

        if len(features) < 200:
            continue

        X = np.array(features)
        y_viol = np.array(targets)
        n_train = int(0.8 * len(X))

        model = Ridge(alpha=1.0)
        model.fit(X[:n_train], y_viol[:n_train])
        pred_viol = model.predict(X[n_train:])
        r2_violation = _eval_r2(y_viol[n_train:], pred_viol)

        # Feature importance for violation prediction
        coefs = np.abs(model.coef_)
        feat_names = ['bg_h{}'.format(i) for i in range(h_steps)] + \
                     ['pk_{}'.format(i) for i in range(8)] + ['hour', 'carbs_3h']
        top_features = sorted(zip(feat_names, coefs), key=lambda x: -x[1])[:5]

        per_patient.append({
            'patient': p['name'],
            'r2_violation_predicted': round(r2_violation, 4),
            'mean_abs_violation': round(float(np.mean(np.abs(y_viol))), 3),
            'top_violation_predictors': [
                {'feature': name, 'importance': round(float(imp), 4)}
                for name, imp in top_features
            ],
        })

    r2s = [pp['r2_violation_predicted'] for pp in per_patient]
    detail = "mean_r2_violation={:.4f}".format(np.mean(r2s))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1007', 'name': 'Conservation Violation Prediction',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1008: Adaptive Horizon Selection
# ===================================================================

def run_exp1008(patients, args):
    """Test if prediction accuracy varies by forecast horizon (15/30/60/120 min).
    Which horizons benefit most from physics augmentation?"""
    print("\n" + "=" * 60)
    print("Running EXP-1008: Adaptive Horizon Selection")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        horizon_results = {}
        for horizon_min, horizon_steps in [(15, 3), (30, 6), (60, 12), (120, 24)]:
            X, y, indices = _build_features(bg, pk, horizon=horizon_steps)
            if X is None or len(X) < 200:
                continue

            n_train = int(0.8 * len(X))

            # Baseline
            model_base = Ridge(alpha=1.0)
            model_base.fit(X[:n_train], y[:n_train])
            r2_base = _eval_r2(y[n_train:], model_base.predict(X[n_train:]))

            # Physics-augmented
            phys = np.array([
                np.sum(sd['net'][idx:min(idx + horizon_steps, len(sd['net']))])
                for idx in indices
            ])
            X_aug = np.column_stack([X, phys])
            model_aug = Ridge(alpha=1.0)
            model_aug.fit(X_aug[:n_train], y[:n_train])
            r2_aug = _eval_r2(y[n_train:], model_aug.predict(X_aug[n_train:]))

            horizon_results[horizon_min] = {
                'r2_baseline': round(r2_base, 4),
                'r2_physics': round(r2_aug, 4),
                'improvement': round(r2_aug - r2_base, 4),
            }

        if horizon_results:
            per_patient.append({
                'patient': p['name'],
                'horizons': horizon_results,
            })

    # Find which horizon benefits most
    horizon_improvements = {}
    for h in [15, 30, 60, 120]:
        imps = [pp['horizons'].get(h, {}).get('improvement', 0) for pp in per_patient]
        horizon_improvements[h] = round(np.mean(imps), 4)

    best_horizon = max(horizon_improvements, key=horizon_improvements.get)
    detail = "best_horizon={}min({:+.4f})".format(best_horizon, horizon_improvements[best_horizon])
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1008', 'name': 'Adaptive Horizon Selection',
            'status': 'pass', 'detail': detail,
            'results': {'horizon_improvements': horizon_improvements,
                        'per_patient': per_patient},
            'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1009: Rolling Regime Detection for Settings Assessment
# ===================================================================

def run_exp1009(patients, args):
    """Detect regime changes in supply/demand balance over time.
    Identify when settings adjustments likely occurred."""
    print("\n" + "=" * 60)
    print("Running EXP-1009: Rolling Regime Detection")
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

        # Compute weekly metrics
        WEEK = 7 * STEPS_PER_DAY
        n_weeks = len(bg) // WEEK
        if n_weeks < 6:
            continue

        weekly_metrics = []
        for w in range(n_weeks):
            start = w * WEEK
            end = start + WEEK
            wbg = bg[start:end]
            v = wbg > 30
            if np.sum(v) < WEEK * 0.3:
                weekly_metrics.append(None)
                continue

            bg_v = wbg[v]
            tir = np.mean((bg_v >= 70) & (bg_v <= 180))
            mean_bg = np.mean(bg_v)
            loop_aggr = np.mean(np.abs(br[start:end][v] - 1.0))
            net_flux = np.mean(sd['net'][start:end][v])

            weekly_metrics.append({
                'week': w,
                'tir': tir,
                'mean_bg': mean_bg,
                'loop_aggr': loop_aggr,
                'net_flux': net_flux,
            })

        # Detect changepoints using cumulative sum
        valid_metrics = [m for m in weekly_metrics if m is not None]
        if len(valid_metrics) < 6:
            continue

        tir_series = np.array([m['tir'] for m in valid_metrics])
        aggr_series = np.array([m['loop_aggr'] for m in valid_metrics])

        # CUSUM on TIR for regime detection
        tir_mean = np.mean(tir_series)
        cusum = np.cumsum(tir_series - tir_mean)
        max_deviation_idx = np.argmax(np.abs(cusum))
        max_deviation = cusum[max_deviation_idx]

        # Test significance with permutation
        n_perms = 100
        perm_max = []
        for _ in range(n_perms):
            perm = np.random.permutation(tir_series)
            perm_cusum = np.cumsum(perm - tir_mean)
            perm_max.append(np.max(np.abs(perm_cusum)))

        p_val = np.mean(np.array(perm_max) >= abs(max_deviation))

        per_patient.append({
            'patient': p['name'],
            'n_weeks': len(valid_metrics),
            'changepoint_week': int(valid_metrics[max_deviation_idx]['week']),
            'cusum_max': round(float(max_deviation), 3),
            'changepoint_p': round(float(p_val), 3),
            'significant': p_val < 0.05,
            'tir_before': round(float(np.mean(tir_series[:max_deviation_idx + 1])), 3),
            'tir_after': round(float(np.mean(tir_series[max_deviation_idx + 1:])), 3)
                if max_deviation_idx < len(tir_series) - 1 else None,
        })

    n_sig = sum(1 for pp in per_patient if pp['significant'])
    detail = "changepoints={}/{} patients".format(n_sig, len(per_patient))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1009', 'name': 'Rolling Regime Detection',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# EXP-1010: Integrated Feature Stack Benchmark
# ===================================================================

def run_exp1010(patients, args):
    """Combine ALL promising features and measure cumulative improvement:
    glucose history + PK + physics + meal context + daily summaries."""
    print("\n" + "=" * 60)
    print("Running EXP-1010: Integrated Feature Stack Benchmark")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        valid = bg > 30

        h_steps = 12
        horizon = 12
        start = max(24, STEPS_PER_DAY + h_steps)

        # Pre-compute meal context
        time_since_meal = np.full(len(bg), 999.0)
        last_meal_size = np.zeros(len(bg))
        cum_carbs = np.zeros(len(bg))
        lm_idx = -1
        lm_carbs = 0
        for i in range(len(carbs)):
            if carbs[i] > 5:
                lm_idx = i
                lm_carbs = carbs[i]
            if lm_idx >= 0:
                time_since_meal[i] = (i - lm_idx) * 5
                last_meal_size[i] = lm_carbs
            s = max(0, i - 3 * STEPS_PER_HOUR)
            cum_carbs[i] = np.sum(carbs[s:i + 1])

        features_base = []
        features_full = []
        targets = []

        for i in range(start, len(bg) - horizon):
            if not valid[i]:
                continue
            hist = bg[i - h_steps:i]
            if np.any(hist <= 30):
                continue

            # Base: glucose + PK
            base = np.concatenate([hist, pk[i, :]])
            features_base.append(base)

            # Full: base + physics + meal + daily + time
            phys_multi = []
            for ph in [3, 6, 12, 24]:
                end = min(i + ph, len(sd['net']))
                phys_multi.append(np.sum(sd['net'][i:end]))
                phys_multi.append(np.sum(sd['supply'][i:end]))

            meal_feat = [
                min(time_since_meal[i], 240) / 240.0,
                last_meal_size[i] / 100.0,
                cum_carbs[i] / 100.0,
                1.0 if time_since_meal[i] < 120 else 0.0,
            ]

            # Previous day summary
            day_start = max(0, i - STEPS_PER_DAY)
            prev_bg = bg[day_start:i]
            pv = prev_bg > 30
            if np.sum(pv) > 100:
                day_feat = [
                    np.mean((prev_bg[pv] >= 70) & (prev_bg[pv] <= 180)),
                    np.mean(prev_bg[pv]) / 200.0,
                    np.std(prev_bg[pv]) / 100.0,
                ]
            else:
                day_feat = [0.7, 0.6, 0.2]

            full = np.concatenate([base, phys_multi, meal_feat, day_feat])
            features_full.append(full)

            targets.append(bg[i + horizon] - bg[i])

        if len(features_base) < 200:
            continue

        X_base = np.array(features_base)
        X_full = np.array(features_full)
        y = np.array(targets)
        n_train = int(0.8 * len(X_base))

        # Baseline
        m_base = Ridge(alpha=1.0)
        m_base.fit(X_base[:n_train], y[:n_train])
        r2_base = _eval_r2(y[n_train:], m_base.predict(X_base[n_train:]))

        # Full stack
        m_full = Ridge(alpha=1.0)
        m_full.fit(X_full[:n_train], y[:n_train])
        r2_full = _eval_r2(y[n_train:], m_full.predict(X_full[n_train:]))

        per_patient.append({
            'patient': p['name'],
            'n_features_base': X_base.shape[1],
            'n_features_full': X_full.shape[1],
            'r2_baseline': round(r2_base, 4),
            'r2_full_stack': round(r2_full, 4),
            'improvement': round(r2_full - r2_base, 4),
            'n_samples': len(X_base),
        })

    improvements = [pp['improvement'] for pp in per_patient]
    r2_fulls = [pp['r2_full_stack'] for pp in per_patient]
    detail = "mean_r2_full={:.4f}, mean_improvement={:+.4f}, positive={}/{}".format(
        np.mean(r2_fulls), np.mean(improvements),
        sum(1 for i in improvements if i > 0), len(improvements))
    print("  Status: pass")
    print("  Detail: " + detail)
    elapsed = round(time.time() - t0, 1)
    print("  Time: {}s".format(elapsed))
    return {'experiment': 'EXP-1010', 'name': 'Integrated Feature Stack Benchmark',
            'status': 'pass', 'detail': detail,
            'results': {'per_patient': per_patient}, 'elapsed_seconds': elapsed}


# ===================================================================
# Main
# ===================================================================

EXPERIMENTS = {
    1001: ('Postprandial Residual Characterization', run_exp1001),
    1002: ('Lag-Compensated Physics Augmentation', run_exp1002),
    1003: ('Multi-Horizon Physics Augmentation', run_exp1003),
    1004: ('Meal Absorption Rate Estimation', run_exp1004),
    1005: ('Daily Summary Features', run_exp1005),
    1006: ('Meal-Aware Prediction Features', run_exp1006),
    1007: ('Conservation Violation Prediction', run_exp1007),
    1008: ('Adaptive Horizon Selection', run_exp1008),
    1009: ('Rolling Regime Detection', run_exp1009),
    1010: ('Integrated Feature Stack Benchmark', run_exp1010),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1001-1010')
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
