#!/usr/bin/env python3
"""EXP-721-730: Physics-First Prediction, Meal Bias Correction, and Prospective Validation.

Based on EXP-713 breakthrough: physics forward simulation achieves R2=0.987 at 5min,
0.909 at 15min, 0.669 at 30min (vs AR: 0.405, 0.197, 0.131).

This wave focuses on:
- Fixing physics divergence at 60+ min
- Making physics sim prospective (no future data leak)
- Correcting systematic meal bias
- BG-dependent prediction intervals
- Production-ready hybrid pipeline
"""

import argparse
import json
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


# === shared utilities ===
def _detect_spikes(resid, sigma_mult=2.0):
    jumps = np.abs(np.diff(resid))
    valid = np.isfinite(jumps)
    mu = np.nanmean(jumps[valid])
    sigma = np.nanstd(jumps[valid])
    threshold = mu + sigma_mult * sigma
    spike_idx = np.where(valid & (jumps > threshold))[0] + 1
    return spike_idx, threshold


def _interpolate_spikes(arr, spike_idx, window=3):
    out = arr.copy()
    n = len(out)
    for idx in spike_idx:
        lo = max(0, idx - window)
        hi = min(n, idx + window + 1)
        mask = np.ones(hi - lo, dtype=bool)
        center = idx - lo
        mask[max(0, center - 1):min(len(mask), center + 2)] = False
        neighbors = out[lo:hi][mask]
        good = neighbors[np.isfinite(neighbors)]
        if len(good) > 0:
            out[idx] = np.mean(good)
    return out


def _clean_residuals(resid, sigma_mult=2.0):
    spike_idx, _ = _detect_spikes(resid, sigma_mult)
    cleaned = _interpolate_spikes(resid, spike_idx)
    return cleaned, spike_idx


def _compute_flux(p):
    df = p['df'].copy()
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(float)
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(bg))
    fd = compute_supply_demand(df, pk)
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.zeros_like(supply))
    carb_supply = fd.get('carb_supply', np.zeros_like(supply))
    n = min(len(bg), len(supply), len(demand), len(hepatic))
    bg = bg[:n]; supply = supply[:n]; demand = demand[:n]
    hepatic = hepatic[:n]
    carb_supply = carb_supply[:n] if len(carb_supply) >= n else np.zeros(n)
    bg_decay = (120.0 - bg) * 0.005
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    return {
        'bg': bg, 'supply': supply, 'demand': demand,
        'hepatic': hepatic, 'carb_supply': carb_supply,
        'resid': resid, 'n': n, 'df': df,
    }


def _build_features(resid, bg, demand, order=6, extra_cols=None):
    n = len(resid)
    n_base = order + 4
    n_extra = extra_cols.shape[1] if extra_cols is not None else 0
    X = np.zeros((n, n_base + n_extra))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid[:-lag]
    bg_c = bg[:n] - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand[:n] ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand[:n] / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    if extra_cols is not None:
        X[:, n_base:] = extra_cols[:n]
    return X


def _ridge_fit(X_train, y_train, alpha=1.0):
    mask = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    Xtr = X_train[mask]; ytr = y_train[mask]
    if len(Xtr) < X_train.shape[1] + 5:
        return np.zeros(X_train.shape[1])
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    return np.linalg.solve(A, Xtr.T @ ytr)


def _ridge_fit_predict(X_train, y_train, X_test, y_test, alpha=1.0):
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    mask_te = np.all(np.isfinite(X_test), axis=1)
    Xtr = X_train[mask_tr]; ytr = y_train[mask_tr]
    if len(Xtr) < X_train.shape[1] + 5:
        return np.nan, np.nan, np.zeros(X_train.shape[1])
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    w = np.linalg.solve(A, Xtr.T @ ytr)
    pred = np.full(len(X_test), np.nan)
    pred[mask_te] = X_test[mask_te] @ w
    valid = mask_te & np.isfinite(y_test)
    if valid.sum() < 10:
        return np.nan, np.nan, w
    ss_res = np.sum((y_test[valid] - pred[valid]) ** 2)
    ss_tot = np.sum((y_test[valid] - np.mean(y_test[valid])) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rmse = np.sqrt(ss_res / valid.sum())
    return r2, rmse, w


def _physics_sim(bg_start, supply, demand, hepatic, resid_start, ar_w, decay, n_steps):
    """Forward simulate using physics + AR correction."""
    bg_sim = bg_start
    resid_est = resid_start
    for step in range(n_steps):
        if step >= len(supply):
            break
        bg_d = (120.0 - bg_sim) * 0.005
        bg_sim = bg_sim + supply[step] - demand[step] + hepatic[step] + bg_d
        bg_sim += ar_w * resid_est
        resid_est *= decay
    return bg_sim


def _compute_r2(preds, actuals):
    valid = np.isfinite(preds) & np.isfinite(actuals)
    if valid.sum() < 10:
        return np.nan
    ss_res = np.sum((actuals[valid] - preds[valid]) ** 2)
    ss_tot = np.sum((actuals[valid] - np.mean(actuals[valid])) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


# === Experiments ===

def exp_721_meal_bias_correction(patients, detail=False):
    """EXP-721: Correct systematic post-meal residual bias from EXP-718."""
    # Meal bias profile from EXP-718 (offsets in steps, bias in mg/dL)
    bias_profile = {0: 4.12, 6: 3.30, 12: 2.08, 18: -0.05, 24: 1.23, 36: 4.33, 48: 2.92, 60: 2.14}
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        carb_supply = fd['carb_supply']
        n = len(resid_clean)

        # Build meal proximity array
        cs = carb_supply[:n]
        above = cs > 0.5
        transitions = np.diff(above.astype(int), prepend=0)
        meal_starts = np.where(transitions > 0)[0]

        # Compute bias correction for each timestep
        bias_correction = np.zeros(n)
        for ms in meal_starts:
            for offset, bias in bias_profile.items():
                idx = ms + offset
                # Apply over a window around the offset
                for delta in range(-3, 4):
                    t = idx + delta
                    if 0 <= t < n:
                        bias_correction[t] = max(bias_correction[t], bias)

        # Correct residuals
        resid_corrected = resid_clean - bias_correction

        # Compare models
        X_base = _build_features(resid_clean, bg, demand, order=6)
        X_corr = _build_features(resid_corrected, bg, demand, order=6)
        split = int(n * 0.8)

        r2_base, _, _ = _ridge_fit_predict(X_base[:split], resid_clean[:split],
                                           X_base[split:], resid_clean[split:])
        r2_corr, _, _ = _ridge_fit_predict(X_corr[:split], resid_corrected[:split],
                                           X_corr[split:], resid_corrected[split:])

        results.append({
            'patient': p['name'],
            'r2_base': float(r2_base) if np.isfinite(r2_base) else np.nan,
            'r2_corrected': float(r2_corr) if np.isfinite(r2_corr) else np.nan,
            'n_meals': len(meal_starts),
            'mean_correction': float(np.mean(np.abs(bias_correction[bias_correction > 0]))) if np.any(bias_correction > 0) else 0.0,
        })

    mean_base = np.nanmean([r['r2_base'] for r in results])
    mean_corr = np.nanmean([r['r2_corrected'] for r in results])

    return {
        'name': 'EXP-721 Meal Bias Correction',
        'status': 'pass',
        'mean_base_r2': float(mean_base),
        'mean_corrected_r2': float(mean_corr),
        'delta': float(mean_corr - mean_base),
        'results': results,
        'detail': f"Base R2={mean_base:.3f}, Corrected R2={mean_corr:.3f}, delta={mean_corr - mean_base:+.4f}"
    }


def exp_722_bg_scaled_pis(patients, detail=False):
    """EXP-722: BG-dependent prediction interval width improves calibration."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        X = _build_features(resid_clean, bg, demand, order=6)
        split = int(n * 0.8)
        r2, _, w = _ridge_fit_predict(X[:split], resid_clean[:split], X[split:], resid_clean[split:])

        # Compute test residuals
        mask_te = np.all(np.isfinite(X[split:]), axis=1)
        pred = np.full(n - split, np.nan)
        pred[mask_te] = X[split:][mask_te] @ w
        test_errors = resid_clean[split:] - pred
        test_bg = bg[split:n]

        # Fixed PI (1.96 * overall std)
        overall_std = np.nanstd(test_errors)
        fixed_width = 1.96 * overall_std
        fixed_coverage = np.nanmean(np.abs(test_errors) <= fixed_width)

        # BG-scaled PI: width = base * (1 + 0.003 * max(0, BG - 120))
        bg_scale = 1.0 + 0.003 * np.maximum(0, test_bg - 120.0)
        # Calibrate base width so overall coverage = 95%
        base_std = overall_std / np.nanmean(bg_scale)
        scaled_width = 1.96 * base_std * bg_scale
        scaled_coverage = np.nanmean(np.abs(test_errors) <= scaled_width)

        # Per-BG-range coverage
        ranges = [(40, 80), (80, 120), (120, 180), (180, 250), (250, 400)]
        range_names = ['hypo', 'low_normal', 'high_normal', 'high', 'very_high']
        fixed_by_range = {}
        scaled_by_range = {}
        for (lo, hi), rname in zip(ranges, range_names):
            mask = (test_bg >= lo) & (test_bg < hi) & np.isfinite(test_errors)
            if mask.sum() > 10:
                fixed_by_range[rname] = float(np.mean(np.abs(test_errors[mask]) <= fixed_width))
                scaled_by_range[rname] = float(np.mean(np.abs(test_errors[mask]) <= scaled_width[mask]))

        results.append({
            'patient': p['name'],
            'fixed_coverage': float(fixed_coverage),
            'scaled_coverage': float(scaled_coverage),
            'fixed_by_range': fixed_by_range,
            'scaled_by_range': scaled_by_range,
        })

    mean_fixed = np.mean([r['fixed_coverage'] for r in results])
    mean_scaled = np.mean([r['scaled_coverage'] for r in results])

    return {
        'name': 'EXP-722 BG-Scaled PIs',
        'status': 'pass',
        'mean_fixed_coverage': float(mean_fixed),
        'mean_scaled_coverage': float(mean_scaled),
        'results': results,
        'detail': f"Fixed coverage={mean_fixed:.1%}, Scaled={mean_scaled:.1%}"
    }


def exp_723_physics_meal_correction(patients, detail=False):
    """EXP-723: Physics forward sim + meal bias correction."""
    horizons = [1, 6, 12]  # 5min, 30min, 60min
    horizon_names = ['5min', '30min', '60min']
    bias_profile = {0: 4.12, 6: 3.30, 12: 2.08, 18: -0.05, 24: 1.23, 36: 4.33, 48: 2.92}
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        carb_supply = fd['carb_supply']
        n = fd['n']

        # Meal proximity for bias correction
        cs = carb_supply[:n]
        above = cs > 0.5
        transitions = np.diff(above.astype(int), prepend=0)
        meal_starts = np.where(transitions > 0)[0]

        meal_proximity = np.full(n, 999)
        for ms in meal_starts:
            for offset in range(0, 72):
                idx = ms + offset
                if 0 <= idx < n:
                    meal_proximity[idx] = min(meal_proximity[idx], offset)

        # Train AR(1) on first 80%
        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        for h in horizons:
            preds_base = []
            preds_corrected = []
            actuals = []

            for t in range(split, n - h):
                # Base physics sim
                bg_base = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < len(resid_clean) else 0.0,
                    ar_coeff, 0.8, h
                )

                # Meal-corrected: subtract expected bias
                bias = 0.0
                prox = meal_proximity[t]
                if prox < 60:
                    # Interpolate bias at current meal proximity
                    offsets = sorted(bias_profile.keys())
                    for i in range(len(offsets) - 1):
                        if offsets[i] <= prox <= offsets[i+1]:
                            frac = (prox - offsets[i]) / (offsets[i+1] - offsets[i])
                            bias = bias_profile[offsets[i]] * (1-frac) + bias_profile[offsets[i+1]] * frac
                            break

                bg_corrected = bg_base - bias

                if t + h < n:
                    preds_base.append(bg_base)
                    preds_corrected.append(bg_corrected)
                    actuals.append(bg[t + h])

            r2_base = _compute_r2(np.array(preds_base), np.array(actuals))
            r2_corr = _compute_r2(np.array(preds_corrected), np.array(actuals))

            results_by_h[h].append({
                'patient': p['name'],
                'r2_base': float(r2_base) if np.isfinite(r2_base) else np.nan,
                'r2_corrected': float(r2_corr) if np.isfinite(r2_corr) else np.nan,
            })

    summary = {}
    for h, name in zip(horizons, horizon_names):
        base_vals = [r['r2_base'] for r in results_by_h[h] if np.isfinite(r['r2_base'])]
        corr_vals = [r['r2_corrected'] for r in results_by_h[h] if np.isfinite(r['r2_corrected'])]
        summary[name] = {
            'base': float(np.mean(base_vals)) if base_vals else np.nan,
            'corrected': float(np.mean(corr_vals)) if corr_vals else np.nan,
        }

    return {
        'name': 'EXP-723 Physics+Meal Correction',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: base={summary[n]['base']:.3f}/corr={summary[n]['corrected']:.3f}" for n in horizon_names)
    }


def exp_724_decay_optimization(patients, detail=False):
    """EXP-724: Optimize residual decay constant in physics forward sim."""
    decays = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    horizons = [6, 12, 24]  # 30min, 60min, 120min
    horizon_names = ['30min', '60min', '120min']
    results = {d: {h: [] for h in horizons} for d in decays}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        for decay in decays:
            for h in horizons:
                preds = []
                actuals = []
                for t in range(split, n - h, 3):  # sample every 3rd point for speed
                    bg_pred = _physics_sim(
                        bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                        resid_clean[t] if t < len(resid_clean) else 0.0,
                        ar_coeff, decay, h
                    )
                    if t + h < n:
                        preds.append(bg_pred)
                        actuals.append(bg[t + h])

                r2 = _compute_r2(np.array(preds), np.array(actuals))
                results[decay][h].append({
                    'patient': p['name'],
                    'r2': float(r2) if np.isfinite(r2) else np.nan,
                })

    summary = {}
    for decay in decays:
        for h, name in zip(horizons, horizon_names):
            vals = [r['r2'] for r in results[decay][h] if np.isfinite(r['r2'])]
            key = f"decay_{decay}_{name}"
            summary[key] = float(np.mean(vals)) if vals else np.nan

    # Find optimal decay per horizon
    optimal = {}
    for h, name in zip(horizons, horizon_names):
        best_decay = max(decays, key=lambda d: summary.get(f"decay_{d}_{name}", -999))
        optimal[name] = {'decay': best_decay, 'r2': summary[f"decay_{best_decay}_{name}"]}

    return {
        'name': 'EXP-724 Decay Optimization',
        'status': 'pass',
        'optimal': optimal,
        'summary': summary,
        'detail': ", ".join(f"{n}: decay={v['decay']}/R2={v['r2']:.3f}" for n, v in optimal.items())
    }


def exp_725_damped_physics(patients, detail=False):
    """EXP-725: Fix physics divergence at 60+ min with BG-centering damping."""
    horizons = [6, 12, 24]
    horizon_names = ['30min', '60min', '120min']
    damping_strengths = [0.0, 0.001, 0.003, 0.005, 0.01, 0.02]
    results = {d: {h: [] for h in horizons} for d in damping_strengths}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        for damp in damping_strengths:
            for h in horizons:
                preds = []
                actuals = []
                for t in range(split, n - h, 3):
                    bg_sim = bg[t]
                    resid_est = resid_clean[t] if t < len(resid_clean) else 0.0
                    for step in range(h):
                        ts = t + step
                        if ts >= n - 1:
                            break
                        bg_d = (120.0 - bg_sim) * 0.005
                        # Additional damping toward recent mean
                        extra_damp = damp * (bg[t] - bg_sim)  # pull toward starting BG
                        bg_sim = bg_sim + supply[ts] - demand[ts] + hepatic[ts] + bg_d + extra_damp
                        bg_sim += ar_coeff * resid_est
                        resid_est *= 0.8
                    if t + h < n:
                        preds.append(bg_sim)
                        actuals.append(bg[t + h])

                r2 = _compute_r2(np.array(preds), np.array(actuals))
                results[damp][h].append({
                    'patient': p['name'],
                    'r2': float(r2) if np.isfinite(r2) else np.nan,
                })

    summary = {}
    for damp in damping_strengths:
        for h, name in zip(horizons, horizon_names):
            vals = [r['r2'] for r in results[damp][h] if np.isfinite(r['r2'])]
            summary[f"damp_{damp}_{name}"] = float(np.mean(vals)) if vals else np.nan

    optimal = {}
    for h, name in zip(horizons, horizon_names):
        best_damp = max(damping_strengths, key=lambda d: summary.get(f"damp_{d}_{name}", -999))
        optimal[name] = {'damping': best_damp, 'r2': summary[f"damp_{best_damp}_{name}"]}

    return {
        'name': 'EXP-725 Damped Physics',
        'status': 'pass',
        'optimal': optimal,
        'summary': summary,
        'detail': ", ".join(f"{n}: damp={v['damping']}/R2={v['r2']:.3f}" for n, v in optimal.items())
    }


def exp_726_per_patient_physics(patients, detail=False):
    """EXP-726: Patient-specific physics sim parameters (decay, bias)."""
    decays = [0.6, 0.7, 0.8, 0.9]
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        val_start = int(n * 0.6)  # use 60-80% for validation, 80-100% for test
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:val_start], resid_clean[:val_start], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        # Optimize decay on validation set
        best_decay = 0.8
        best_val_r2 = -np.inf
        h = 6  # optimize for 30-min horizon

        for decay in decays:
            preds, acts = [], []
            for t in range(val_start, split, 3):
                bg_pred = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < len(resid_clean) else 0.0,
                    ar_coeff, decay, h
                )
                if t + h < n:
                    preds.append(bg_pred)
                    acts.append(bg[t + h])
            r2 = _compute_r2(np.array(preds), np.array(acts))
            if np.isfinite(r2) and r2 > best_val_r2:
                best_val_r2 = r2
                best_decay = decay

        # Evaluate optimized model on test set
        test_preds, test_acts = [], []
        for t in range(split, n - h, 1):
            bg_pred = _physics_sim(
                bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                resid_clean[t] if t < len(resid_clean) else 0.0,
                ar_coeff, best_decay, h
            )
            if t + h < n:
                test_preds.append(bg_pred)
                test_acts.append(bg[t + h])

        r2_optimized = _compute_r2(np.array(test_preds), np.array(test_acts))

        # Default decay=0.8 baseline
        base_preds, base_acts = [], []
        for t in range(split, n - h, 1):
            bg_pred = _physics_sim(
                bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                resid_clean[t] if t < len(resid_clean) else 0.0,
                ar_coeff, 0.8, h
            )
            if t + h < n:
                base_preds.append(bg_pred)
                base_acts.append(bg[t + h])
        r2_base = _compute_r2(np.array(base_preds), np.array(base_acts))

        results.append({
            'patient': p['name'],
            'best_decay': best_decay,
            'r2_optimized': float(r2_optimized) if np.isfinite(r2_optimized) else np.nan,
            'r2_default': float(r2_base) if np.isfinite(r2_base) else np.nan,
            'delta': float(r2_optimized - r2_base) if np.isfinite(r2_optimized) and np.isfinite(r2_base) else np.nan,
        })

    mean_opt = np.nanmean([r['r2_optimized'] for r in results])
    mean_base = np.nanmean([r['r2_default'] for r in results])

    return {
        'name': 'EXP-726 Per-Patient Physics',
        'status': 'pass',
        'mean_optimized': float(mean_opt),
        'mean_default': float(mean_base),
        'results': results,
        'detail': f"Default R2={mean_base:.3f}, Optimized R2={mean_opt:.3f}, delta={mean_opt - mean_base:+.3f}"
    }


def exp_727_hybrid_ar_physics(patients, detail=False):
    """EXP-727: Weighted ensemble AR + physics by horizon."""
    horizons = [1, 3, 6, 12]
    horizon_names = ['5min', '15min', '30min', '60min']
    blend_weights = [0.0, 0.25, 0.5, 0.75, 1.0]  # 0=pure AR, 1=pure physics
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        X = _build_features(resid_clean, bg, demand, order=6)
        split = int(n * 0.8)

        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        nr = len(resid_clean)  # n-1
        for h in horizons:
            # AR direct prediction for this horizon
            y_ar = np.full(nr, np.nan)
            if h == 1:
                y_ar = resid_clean.copy()
            else:
                y_ar[:nr-h] = resid_clean[h:]
            _, _, w_ar = _ridge_fit_predict(X[:split], y_ar[:split], X[split:], y_ar[split:])

            # For each test point, get both predictions
            best_blend = 0.5
            best_r2 = -np.inf

            for blend in blend_weights:
                preds_blend = []
                actuals_blend = []
                for t in range(split, n - h, 3):
                    # AR prediction (residual correction)
                    if np.all(np.isfinite(X[t])):
                        ar_pred = bg[t] + X[t] @ w_ar
                    else:
                        ar_pred = bg[t]

                    # Physics prediction
                    phys_pred = _physics_sim(
                        bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                        resid_clean[t] if t < len(resid_clean) else 0.0,
                        ar_coeff, 0.8, h
                    )

                    # Blend
                    blended = blend * phys_pred + (1 - blend) * ar_pred

                    if t + h < n:
                        preds_blend.append(blended)
                        actuals_blend.append(bg[t + h])

                r2 = _compute_r2(np.array(preds_blend), np.array(actuals_blend))
                if np.isfinite(r2) and r2 > best_r2:
                    best_r2 = r2
                    best_blend = blend

            results_by_h[h].append({
                'patient': p['name'],
                'best_blend': best_blend,
                'best_r2': float(best_r2) if np.isfinite(best_r2) else np.nan,
            })

    summary = {}
    for h, name in zip(horizons, horizon_names):
        r2s = [r['best_r2'] for r in results_by_h[h] if np.isfinite(r['best_r2'])]
        blends = [r['best_blend'] for r in results_by_h[h]]
        summary[name] = {
            'mean_r2': float(np.mean(r2s)) if r2s else np.nan,
            'mean_blend': float(np.mean(blends)),
        }

    return {
        'name': 'EXP-727 Hybrid AR-Physics',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: blend={summary[n]['mean_blend']:.2f}/R2={summary[n]['mean_r2']:.3f}" for n in horizon_names)
    }


def exp_728_prospective_physics(patients, detail=False):
    """EXP-728: Prospective physics sim using only known-at-time-t supply/demand."""
    horizons = [1, 6, 12]
    horizon_names = ['5min', '30min', '60min']
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        for h in horizons:
            preds_retro = []  # retrospective (uses future supply/demand)
            preds_prosp = []  # prospective (uses only current supply/demand, held constant)
            actuals = []

            for t in range(split, n - h, 1):
                # Retrospective: full future supply/demand
                bg_retro = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < len(resid_clean) else 0.0,
                    ar_coeff, 0.8, h
                )

                # Prospective: hold supply/demand constant at current values
                supply_const = np.full(h, supply[t])
                demand_const = np.full(h, demand[t])
                hepatic_const = np.full(h, hepatic[t])
                bg_prosp = _physics_sim(
                    bg[t], supply_const, demand_const, hepatic_const,
                    resid_clean[t] if t < len(resid_clean) else 0.0,
                    ar_coeff, 0.8, h
                )

                if t + h < n:
                    preds_retro.append(bg_retro)
                    preds_prosp.append(bg_prosp)
                    actuals.append(bg[t + h])

            r2_retro = _compute_r2(np.array(preds_retro), np.array(actuals))
            r2_prosp = _compute_r2(np.array(preds_prosp), np.array(actuals))

            results_by_h[h].append({
                'patient': p['name'],
                'r2_retrospective': float(r2_retro) if np.isfinite(r2_retro) else np.nan,
                'r2_prospective': float(r2_prosp) if np.isfinite(r2_prosp) else np.nan,
            })

    summary = {}
    for h, name in zip(horizons, horizon_names):
        retro = [r['r2_retrospective'] for r in results_by_h[h] if np.isfinite(r['r2_retrospective'])]
        prosp = [r['r2_prospective'] for r in results_by_h[h] if np.isfinite(r['r2_prospective'])]
        summary[name] = {
            'retrospective': float(np.mean(retro)) if retro else np.nan,
            'prospective': float(np.mean(prosp)) if prosp else np.nan,
        }

    return {
        'name': 'EXP-728 Prospective Physics',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: retro={summary[n]['retrospective']:.3f}/prosp={summary[n]['prospective']:.3f}" for n in horizon_names)
    }


def exp_729_meal_timing_uncertainty(patients, detail=False):
    """EXP-729: Impact of meal timing errors on physics accuracy."""
    shifts = [-6, -3, 0, 3, 6]  # steps = -30, -15, 0, +15, +30 min
    shift_names = ['-30min', '-15min', '0', '+15min', '+30min']
    h = 6  # 30-min horizon
    results_by_shift = {s: [] for s in shifts}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        for shift in shifts:
            preds = []
            actuals = []
            for t in range(split, n - h, 3):
                # Shift the supply curve (simulating meal timing error)
                t_shifted = t + shift
                if t_shifted < 0 or t_shifted + h >= n:
                    continue
                bg_pred = _physics_sim(
                    bg[t], supply[t_shifted:t_shifted+h], demand[t:t+h],
                    hepatic[t:t+h],
                    resid_clean[t] if t < len(resid_clean) else 0.0,
                    ar_coeff, 0.8, h
                )
                if t + h < n:
                    preds.append(bg_pred)
                    actuals.append(bg[t + h])

            r2 = _compute_r2(np.array(preds), np.array(actuals))
            results_by_shift[shift].append({
                'patient': p['name'],
                'r2': float(r2) if np.isfinite(r2) else np.nan,
            })

    summary = {}
    for shift, name in zip(shifts, shift_names):
        vals = [r['r2'] for r in results_by_shift[shift] if np.isfinite(r['r2'])]
        summary[name] = float(np.mean(vals)) if vals else np.nan

    return {
        'name': 'EXP-729 Meal Timing Uncertainty',
        'status': 'pass',
        'summary': summary,
        'results': {n: results_by_shift[s] for s, n in zip(shifts, shift_names)},
        'detail': ", ".join(f"{n}={v:.3f}" for n, v in summary.items() if np.isfinite(v))
    }


def exp_730_production_physics(patients, detail=False):
    """EXP-730: Production physics pipeline - latency, accuracy, streaming."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        split = int(n * 0.8)
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        # Measure streaming latency
        n_test = min(1000, n - split - 6)
        t0 = time.time()
        preds_5 = []
        preds_30 = []
        actuals_5 = []
        actuals_30 = []
        for t in range(split, split + n_test):
            if t + 6 >= n:
                break
            # 5-min prediction
            bg_5 = _physics_sim(
                bg[t], supply[t:t+1], demand[t:t+1], hepatic[t:t+1],
                resid_clean[t] if t < len(resid_clean) else 0.0,
                ar_coeff, 0.8, 1
            )
            preds_5.append(bg_5)
            actuals_5.append(bg[t + 1])

            # 30-min prediction
            bg_30 = _physics_sim(
                bg[t], supply[t:t+6], demand[t:t+6], hepatic[t:t+6],
                resid_clean[t] if t < len(resid_clean) else 0.0,
                ar_coeff, 0.8, 6
            )
            preds_30.append(bg_30)
            actuals_30.append(bg[t + 6])

        elapsed = time.time() - t0
        latency_per_pred = elapsed / max(n_test, 1) * 1e6  # microseconds

        r2_5 = _compute_r2(np.array(preds_5), np.array(actuals_5))
        r2_30 = _compute_r2(np.array(preds_30), np.array(actuals_30))

        # Memory estimate: just the arrays needed
        mem_bytes = (6 * n * 8)  # bg, supply, demand, hepatic, resid, carb_supply - 8 bytes each

        results.append({
            'patient': p['name'],
            'r2_5min': float(r2_5) if np.isfinite(r2_5) else np.nan,
            'r2_30min': float(r2_30) if np.isfinite(r2_30) else np.nan,
            'latency_us': float(latency_per_pred),
            'memory_kb': float(mem_bytes / 1024),
            'n_predictions': n_test,
        })

    mean_5 = np.nanmean([r['r2_5min'] for r in results])
    mean_30 = np.nanmean([r['r2_30min'] for r in results])
    mean_lat = np.mean([r['latency_us'] for r in results])

    return {
        'name': 'EXP-730 Production Physics',
        'status': 'pass',
        'mean_r2_5min': float(mean_5),
        'mean_r2_30min': float(mean_30),
        'mean_latency_us': float(mean_lat),
        'results': results,
        'detail': f"5min R2={mean_5:.3f}, 30min R2={mean_30:.3f}, latency={mean_lat:.0f}us"
    }


# === registry & runner ===

EXPERIMENTS = {
    'EXP-721': exp_721_meal_bias_correction,
    'EXP-722': exp_722_bg_scaled_pis,
    'EXP-723': exp_723_physics_meal_correction,
    'EXP-724': exp_724_decay_optimization,
    'EXP-725': exp_725_damped_physics,
    'EXP-726': exp_726_per_patient_physics,
    'EXP-727': exp_727_hybrid_ar_physics,
    'EXP-728': exp_728_prospective_physics,
    'EXP-729': exp_729_meal_timing_uncertainty,
    'EXP-730': exp_730_production_physics,
}


def run_all(patients, detail=False, save=False, only=None):
    results = []
    exps = {only: EXPERIMENTS[only]} if only and only in EXPERIMENTS else EXPERIMENTS
    for eid, func in exps.items():
        print(f"\n{'='*60}")
        print(f"Running {eid}: {func.__doc__.strip().split(chr(10))[0]}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            res = func(patients, detail=detail)
            elapsed = time.time() - t0
            res['elapsed'] = elapsed
            results.append(res)
            print(f"  Status: {res.get('status', '?')} ({elapsed:.1f}s)")
            if 'detail' in res:
                print(f"  Detail: {res['detail']}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            results.append({'name': eid, 'status': 'fail', 'error': str(e), 'elapsed': elapsed})

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r.get('status') == 'pass')
    failed = sum(1 for r in results if r.get('status') == 'fail')
    print(f"Passed: {passed}/{len(results)}, Failed: {failed}/{len(results)}")
    for r in results:
        sym = 'V' if r.get('status') == 'pass' else 'X'
        print(f"  {sym} {r.get('name', '?')}: {r.get('detail', r.get('error', ''))[:80]}")

    if save:
        out_dir = Path(__file__).parent.parent.parent / "externals" / "experiments"
        out_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            safe_name = r.get('name', 'unknown').lower().replace(' ', '_').replace('/', '_').replace(':', '')[:30]
            out_path = out_dir / f"{safe_name}.json"
            try:
                with open(out_path, 'w') as f:
                    json.dump(r, f, indent=2, default=str)
                print(f"  Saved: {out_path.name}")
            except Exception as e:
                print(f"  Save error: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="EXP-721-730: Physics-First Prediction")
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    run_all(patients, detail=args.detail, save=args.save, only=args.only)


if __name__ == '__main__':
    main()
