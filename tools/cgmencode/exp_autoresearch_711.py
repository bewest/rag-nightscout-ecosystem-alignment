#!/usr/bin/env python3
"""EXP-711-720: AR Breakthrough, Residual Characterization, and Forward Simulation.

Based on EXP-701-710 findings:
- AR_lag1 = 92% of importance => explore minimal models
- Nonlinearity exhausted => improve physics, not ML
- Multi-horizon fails for AR => try physics forward simulation
- Warm-start needs adaptive alpha => tune regularization
- Midnight bias +2.04 => expand dawn window
- Insulin stacking 11% hypo conversion => tune thresholds
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


# === shared spike cleaning ===
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


# === shared model infrastructure ===
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
    bg = bg[:n]
    supply = supply[:n]
    demand = demand[:n]
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


def _ridge_fit_predict(X_train, y_train, X_test, y_test, alpha=1.0):
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    mask_te = np.all(np.isfinite(X_test), axis=1)
    Xtr = X_train[mask_tr]
    ytr = y_train[mask_tr]
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


def _ridge_fit(X_train, y_train, alpha=1.0):
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    Xtr = X_train[mask_tr]
    ytr = y_train[mask_tr]
    if len(Xtr) < X_train.shape[1] + 5:
        return np.zeros(X_train.shape[1])
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    w = np.linalg.solve(A, Xtr.T @ ytr)
    return w


def _eval_r2(X_test, y_test, w):
    mask_te = np.all(np.isfinite(X_test), axis=1) & np.isfinite(y_test)
    if mask_te.sum() < 10:
        return np.nan
    pred = X_test[mask_te] @ w
    actual = y_test[mask_te]
    ss_res = np.sum((actual - pred) ** 2)
    ss_tot = np.sum((actual - np.mean(actual)) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


# === Experiments ===

def exp_711_adaptive_warmstart(patients, detail=False):
    """EXP-711: Adaptive alpha warm-start -- alpha decreases with data volume."""
    personal_days = [1, 3, 7, 14]
    results = []

    for i, p in enumerate(patients):
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        X = _build_features(resid_clean, bg, demand, order=6)
        y = resid_clean
        split = int(n * 0.8)
        Xte, yte = X[split:], y[split:]

        # Population model
        pop_X, pop_y = [], []
        for j, q in enumerate(patients):
            if j == i:
                continue
            fdq = _compute_flux(q)
            rq, _ = _clean_residuals(fdq['resid'])
            Xq = _build_features(rq, fdq['bg'], fdq['demand'], order=6)
            mask = np.all(np.isfinite(Xq), axis=1) & np.isfinite(rq)
            pop_X.append(Xq[mask])
            pop_y.append(rq[mask])
        pop_X = np.vstack(pop_X)
        pop_y = np.concatenate(pop_y)
        w_pop = _ridge_fit(pop_X, pop_y, alpha=1.0)

        # Evaluate population
        r2_pop = _eval_r2(Xte, yte, w_pop)
        # Personal
        r2_personal, _, _ = _ridge_fit_predict(X[:split], y[:split], Xte, yte)

        row = {'patient': p['name'], 'r2_pop': float(r2_pop), 'r2_personal': float(r2_personal)}

        steps_per_day = 288
        mask_te_valid = np.all(np.isfinite(Xte), axis=1) & np.isfinite(yte)
        ss_tot = np.sum((yte[mask_te_valid] - np.mean(yte[mask_te_valid])) ** 2)

        for days in personal_days:
            n_ft = min(days * steps_per_day, split)
            if n_ft < 20:
                row[f'fixed_{days}d'] = float(r2_pop)
                row[f'adaptive_{days}d'] = float(r2_pop)
                continue
            X_ft = X[:n_ft]
            y_ft = y[:n_ft]
            mask_ft = np.all(np.isfinite(X_ft), axis=1) & np.isfinite(y_ft)
            Xf = X_ft[mask_ft]
            yf = y_ft[mask_ft]

            # Fixed alpha=10 (from EXP-703)
            A_fixed = Xf.T @ Xf + 10.0 * np.eye(Xf.shape[1])
            w_fixed = np.linalg.solve(A_fixed, Xf.T @ yf + 10.0 * w_pop)
            r2_fixed = _eval_r2(Xte, yte, w_fixed)

            # Adaptive alpha: decreases with data volume
            alpha_adapt = max(0.5, 50.0 / days)
            A_adapt = Xf.T @ Xf + alpha_adapt * np.eye(Xf.shape[1])
            w_adapt = np.linalg.solve(A_adapt, Xf.T @ yf + alpha_adapt * w_pop)
            r2_adapt = _eval_r2(Xte, yte, w_adapt)

            row[f'fixed_{days}d'] = float(r2_fixed) if np.isfinite(r2_fixed) else np.nan
            row[f'adaptive_{days}d'] = float(r2_adapt) if np.isfinite(r2_adapt) else np.nan

        results.append(row)

    # Summarize
    summary = {}
    for days in personal_days:
        fixed_vals = [r[f'fixed_{days}d'] for r in results if np.isfinite(r.get(f'fixed_{days}d', np.nan))]
        adapt_vals = [r[f'adaptive_{days}d'] for r in results if np.isfinite(r.get(f'adaptive_{days}d', np.nan))]
        summary[f'{days}d'] = {
            'fixed': float(np.mean(fixed_vals)) if fixed_vals else np.nan,
            'adaptive': float(np.mean(adapt_vals)) if adapt_vals else np.nan,
        }

    return {
        'name': 'EXP-711 Adaptive Warmstart',
        'status': 'pass',
        'summary': summary,
        'results': results,
        'detail': ", ".join(f"{k}: fixed={v['fixed']:.3f} adapt={v['adaptive']:.3f}" for k, v in summary.items())
    }


def exp_712_minimal_model(patients, detail=False):
    """EXP-712: AR(1)+sigmoid minimal model vs full AR(6)+NL."""
    results = []
    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        # Full model: AR(6) + 4 NL features = 10 features
        X_full = _build_features(resid_clean, bg, demand, order=6)
        y = resid_clean
        split = int(n * 0.8)
        r2_full, _, _ = _ridge_fit_predict(X_full[:split], y[:split], X_full[split:], y[split:])

        # Minimal: AR(1) + sigmoid = 2 features
        bg_c = bg[:n] - 120.0
        X_min = np.zeros((n, 2))
        X_min[1:, 0] = resid_clean[:-1]  # AR(1)
        X_min[:, 1] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5  # sigmoid
        r2_min, _, _ = _ridge_fit_predict(X_min[:split], y[:split], X_min[split:], y[split:])

        # AR(3) + sigmoid = 4 features
        X_ar3 = np.zeros((n, 4))
        for lag in range(1, 4):
            X_ar3[lag:, lag-1] = resid_clean[:-lag]
        X_ar3[:, 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
        r2_ar3, _, _ = _ridge_fit_predict(X_ar3[:split], y[:split], X_ar3[split:], y[split:])

        # AR(1) only = 1 feature
        X_ar1 = np.zeros((n, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        r2_ar1, _, _ = _ridge_fit_predict(X_ar1[:split], y[:split], X_ar1[split:], y[split:])

        results.append({
            'patient': p['name'],
            'r2_full_10feat': float(r2_full) if np.isfinite(r2_full) else np.nan,
            'r2_ar3_sig_4feat': float(r2_ar3) if np.isfinite(r2_ar3) else np.nan,
            'r2_ar1_sig_2feat': float(r2_min) if np.isfinite(r2_min) else np.nan,
            'r2_ar1_only_1feat': float(r2_ar1) if np.isfinite(r2_ar1) else np.nan,
        })

    means = {}
    for key in ['r2_full_10feat', 'r2_ar3_sig_4feat', 'r2_ar1_sig_2feat', 'r2_ar1_only_1feat']:
        vals = [r[key] for r in results if np.isfinite(r[key])]
        means[key] = float(np.mean(vals)) if vals else np.nan

    return {
        'name': 'EXP-712 Minimal Model',
        'status': 'pass',
        'means': means,
        'results': results,
        'detail': (f"Full(10)={means['r2_full_10feat']:.3f}, AR3+sig(4)={means['r2_ar3_sig_4feat']:.3f}, "
                   f"AR1+sig(2)={means['r2_ar1_sig_2feat']:.3f}, AR1(1)={means['r2_ar1_only_1feat']:.3f}")
    }


def exp_713_physics_forward_sim(patients, detail=False):
    """EXP-713: Physics-based forward simulation for multi-step prediction."""
    horizons = [1, 3, 6, 12, 24]  # 5min, 15min, 30min, 60min, 120min
    horizon_names = ['5min', '15min', '30min', '60min', '120min']
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']

        # Train AR(1) model for 1-step residual correction
        X_ar1 = np.zeros((n-1, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        y = resid_clean
        split = int((n-1) * 0.8)
        w = _ridge_fit(X_ar1[:split], y[:split], alpha=1.0)

        # For each test point, simulate forward using physics + AR correction
        test_start = split
        for h in horizons:
            r2_vals = []
            preds = []
            actuals = []
            for t in range(test_start, n - h - 1):
                # Forward simulate from bg[t]
                bg_sim = bg[t]
                resid_est = resid_clean[t] if t < len(resid_clean) else 0.0

                for step in range(h):
                    t_s = t + step
                    if t_s >= n - 1:
                        break
                    bg_decay = (120.0 - bg_sim) * 0.005
                    # Physics prediction
                    bg_next = bg_sim + supply[t_s] - demand[t_s] + hepatic[t_s] + bg_decay
                    # AR correction
                    ar_correction = w[0] * resid_est if len(w) > 0 else 0.0
                    bg_next += ar_correction
                    # Update residual estimate (decay toward 0)
                    resid_est = resid_est * 0.8  # exponential decay
                    bg_sim = bg_next

                if t + h < n:
                    preds.append(bg_sim)
                    actuals.append(bg[t + h])

            preds = np.array(preds)
            actuals = np.array(actuals)
            valid = np.isfinite(preds) & np.isfinite(actuals)
            if valid.sum() > 10:
                ss_res = np.sum((actuals[valid] - preds[valid]) ** 2)
                ss_tot = np.sum((actuals[valid] - np.mean(actuals[valid])) ** 2)
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
                rmse = np.sqrt(ss_res / valid.sum())
            else:
                r2 = np.nan
                rmse = np.nan

            results_by_h[h].append({
                'patient': p['name'],
                'r2': float(r2) if np.isfinite(r2) else np.nan,
                'rmse': float(rmse) if np.isfinite(rmse) else np.nan,
            })

    summary = {}
    for h, name in zip(horizons, horizon_names):
        vals = [r['r2'] for r in results_by_h[h] if np.isfinite(r['r2'])]
        rmses = [r['rmse'] for r in results_by_h[h] if np.isfinite(r['rmse'])]
        summary[name] = {
            'mean_r2': float(np.mean(vals)) if vals else np.nan,
            'mean_rmse': float(np.mean(rmses)) if rmses else np.nan,
        }

    return {
        'name': 'EXP-713 Physics Forward Sim',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: R2={summary[n]['mean_r2']:.3f}" for n in horizon_names)
    }


def exp_714_stacking_threshold(patients, detail=False):
    """EXP-714: Insulin stacking threshold tuning (2x, 3x, 4x, 5x)."""
    thresholds = [2.0, 3.0, 4.0, 5.0]
    results_by_thresh = {t: [] for t in thresholds}

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        demand = fd['demand']
        supply = fd['supply']
        n = fd['n']

        window = 24
        demand_rolling = np.convolve(demand, np.ones(window)/window, mode='same')
        supply_rolling = np.convolve(supply, np.ones(window)/window, mode='same')
        bg_change = np.zeros(n)
        bg_change[1:] = bg[1:] - bg[:-1]
        bg_change_smooth = np.convolve(bg_change, np.ones(6)/6, mode='same')
        hypo_mask = bg < 70

        for thresh in thresholds:
            stacking_mask = (demand_rolling > thresh * supply_rolling) & (bg_change_smooth < -1.0)
            n_events = int(stacking_mask.sum())

            # Count hypo within 1h of stacking
            stack_to_hypo = 0
            stack_events = np.where(stacking_mask)[0]
            for se in stack_events:
                window_end = min(n, se + 12)
                if np.any(hypo_mask[se:window_end]):
                    stack_to_hypo += 1

            results_by_thresh[thresh].append({
                'patient': p['name'],
                'n_events': n_events,
                'n_hypo': stack_to_hypo,
                'conversion': float(stack_to_hypo / max(n_events, 1)),
                'event_rate': float(n_events / n * 100),
            })

    summary = {}
    for thresh in thresholds:
        total_events = sum(r['n_events'] for r in results_by_thresh[thresh])
        total_hypo = sum(r['n_hypo'] for r in results_by_thresh[thresh])
        summary[f'{thresh}x'] = {
            'total_events': total_events,
            'total_hypo': total_hypo,
            'conversion': float(total_hypo / max(total_events, 1)),
            'mean_rate': float(np.mean([r['event_rate'] for r in results_by_thresh[thresh]])),
        }

    return {
        'name': 'EXP-714 Stacking Threshold',
        'status': 'pass',
        'summary': summary,
        'results': {f'{t}x': results_by_thresh[t] for t in thresholds},
        'detail': ", ".join(f"{k}: {v['total_events']}ev/{v['conversion']:.0%}hypo" for k, v in summary.items())
    }


def exp_715_expanded_dawn(patients, detail=False):
    """EXP-715: Expanded dawn window (00:00-08:00 vs 04:00-08:00) to address midnight bias."""
    results = []
    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        df = fd['df']
        n = len(resid_clean)

        # Get hours
        if 'dateString' in df.columns:
            try:
                hours = pd.to_datetime(df['dateString']).dt.hour.values[:n]
            except Exception:
                hours = np.zeros(n, dtype=int)
        else:
            hours = np.zeros(n, dtype=int)

        # Standard dawn (04:00-08:00)
        dawn_std = ((hours >= 4) & (hours < 8)).astype(float).reshape(-1, 1)
        overnight_std = ((hours >= 0) & (hours < 4)).astype(float).reshape(-1, 1)
        extra_std = np.hstack([dawn_std, overnight_std])[:n]

        # Expanded dawn (00:00-08:00)
        dawn_exp = ((hours >= 0) & (hours < 8)).astype(float).reshape(-1, 1)[:n]

        # Gradual dawn (sinusoidal ramp 00:00-08:00)
        dawn_grad = np.zeros((n, 1))
        for idx in range(n):
            h = hours[idx]
            if 0 <= h < 8:
                dawn_grad[idx, 0] = np.sin(h / 8.0 * np.pi / 2)

        configs = {
            'baseline': None,
            'std_dawn_04_08': extra_std,
            'expanded_00_08': dawn_exp,
            'gradual_ramp': dawn_grad,
        }

        row = {'patient': p['name']}
        split = int(n * 0.8)
        for name, extra in configs.items():
            X = _build_features(resid_clean, bg, demand, order=6, extra_cols=extra)
            r2, _, _ = _ridge_fit_predict(X[:split], resid_clean[:split], X[split:], resid_clean[split:])
            row[name] = float(r2) if np.isfinite(r2) else np.nan

        results.append(row)

    means = {}
    for key in ['baseline', 'std_dawn_04_08', 'expanded_00_08', 'gradual_ramp']:
        vals = [r[key] for r in results if np.isfinite(r.get(key, np.nan))]
        means[key] = float(np.mean(vals)) if vals else np.nan

    return {
        'name': 'EXP-715 Expanded Dawn',
        'status': 'pass',
        'means': means,
        'results': results,
        'detail': ", ".join(f"{k}={v:.4f}" for k, v in means.items())
    }


def exp_716_noise_floor(patients, detail=False):
    """EXP-716: Estimate CGM noise floor from consecutive stable readings."""
    results = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid_clean, _ = _clean_residuals(fd['resid'])
        n = fd['n']

        # Consecutive differences
        diffs = np.diff(bg)
        valid = np.isfinite(diffs)

        # Stable periods: BG rate of change < 1 mg/dL per 5min for 30min
        stable_mask = np.zeros(n - 1, dtype=bool)
        for i in range(5, n - 1):
            window = diffs[i-5:i+1]
            if np.all(np.isfinite(window)) and np.all(np.abs(window) < 1.0):
                stable_mask[i] = True

        stable_diffs = diffs[stable_mask]
        if len(stable_diffs) > 20:
            # Noise floor = std of consecutive diffs during stable periods / sqrt(2)
            noise_std = float(np.std(stable_diffs) / np.sqrt(2))
            noise_pct = float(stable_mask.sum() / valid.sum() * 100)
        else:
            noise_std = np.nan
            noise_pct = 0.0

        # Overall residual std for comparison
        resid_std = float(np.nanstd(resid_clean))

        results.append({
            'patient': p['name'],
            'noise_floor_mgdl': noise_std,
            'stable_pct': noise_pct,
            'resid_std': resid_std,
            'noise_to_resid_ratio': noise_std / resid_std if resid_std > 0 and np.isfinite(noise_std) else np.nan,
        })

    mean_noise = np.nanmean([r['noise_floor_mgdl'] for r in results])
    mean_ratio = np.nanmean([r['noise_to_resid_ratio'] for r in results])

    return {
        'name': 'EXP-716 Noise Floor',
        'status': 'pass',
        'mean_noise_floor': float(mean_noise),
        'mean_noise_to_resid': float(mean_ratio),
        'results': results,
        'detail': f"Noise floor={mean_noise:.1f} mg/dL, {mean_ratio:.0%} of residual std"
    }


def exp_717_bg_dependent_noise(patients, detail=False):
    """EXP-717: CGM noise increases with BG level."""
    bg_ranges = [(40, 80), (80, 120), (120, 180), (180, 250), (250, 400)]
    range_names = ['hypo', 'low_normal', 'high_normal', 'high', 'very_high']
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        n = len(resid_clean)

        row = {'patient': p['name']}
        for (lo, hi), name in zip(bg_ranges, range_names):
            mask = (bg[:n] >= lo) & (bg[:n] < hi)
            if mask.sum() > 20:
                row[f'{name}_std'] = float(np.nanstd(resid_clean[mask]))
                row[f'{name}_count'] = int(mask.sum())
            else:
                row[f'{name}_std'] = np.nan
                row[f'{name}_count'] = 0
        results.append(row)

    means = {}
    for name in range_names:
        vals = [r[f'{name}_std'] for r in results if np.isfinite(r.get(f'{name}_std', np.nan))]
        means[name] = float(np.mean(vals)) if vals else np.nan

    return {
        'name': 'EXP-717 BG-Dependent Noise',
        'status': 'pass',
        'means': means,
        'results': results,
        'detail': ", ".join(f"{k}={v:.1f}" for k, v in means.items() if np.isfinite(v))
    }


def exp_718_meal_residual_profile(patients, detail=False):
    """EXP-718: Aligned post-meal residual profile at 30/60/90/120 min."""
    offsets = [0, 6, 12, 18, 24, 36, 48, 60]  # steps (5min each)
    offset_names = ['0min', '30min', '60min', '90min', '120min', '180min', '240min', '300min']
    profiles = {o: [] for o in offsets}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        carb_supply = fd['carb_supply']
        n = len(resid_clean)

        # Find meal starts (carb_supply transitions from <0.5 to >0.5)
        cs = carb_supply[:n]
        above = cs > 0.5
        transitions = np.diff(above.astype(int))
        meal_starts = np.where(transitions > 0)[0] + 1

        for offset in offsets:
            vals = []
            for ms in meal_starts:
                idx = ms + offset
                if 0 <= idx < n:
                    v = resid_clean[idx]
                    if np.isfinite(v):
                        vals.append(v)
            profiles[offset].extend(vals)

    summary = {}
    for offset, name in zip(offsets, offset_names):
        vals = profiles[offset]
        if vals:
            summary[name] = {
                'mean': float(np.mean(vals)),
                'std': float(np.std(vals)),
                'count': len(vals),
            }
        else:
            summary[name] = {'mean': 0.0, 'std': 0.0, 'count': 0}

    return {
        'name': 'EXP-718 Meal Residual Profile',
        'status': 'pass',
        'summary': summary,
        'detail': ", ".join(f"{k}={v['mean']:+.2f}" for k, v in summary.items() if v['count'] > 0)
    }


def exp_719_rolling_retrain(patients, detail=False):
    """EXP-719: Rolling window retraining every 7 days vs static model."""
    results = []
    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        X = _build_features(resid_clean, bg, demand, order=6)
        y = resid_clean
        split = int(n * 0.8)

        # Static model: train on first 80%, test on last 20%
        r2_static, _, _ = _ridge_fit_predict(X[:split], y[:split], X[split:], y[split:])

        # Rolling: retrain every 7 days (2016 steps) using last 30 days (8640 steps)
        window_size = 8640  # 30 days
        retrain_interval = 2016  # 7 days
        rolling_preds = np.full(n - split, np.nan)
        rolling_actuals = y[split:]

        for t_start in range(0, n - split, retrain_interval):
            t_abs = split + t_start
            # Training window: last 30 days before t_abs
            train_start = max(0, t_abs - window_size)
            Xtr = X[train_start:t_abs]
            ytr = y[train_start:t_abs]
            w = _ridge_fit(Xtr, ytr, alpha=1.0)

            # Predict next 7 days
            t_end = min(t_start + retrain_interval, n - split)
            Xte_chunk = X[split + t_start:split + t_end]
            mask_valid = np.all(np.isfinite(Xte_chunk), axis=1)
            if mask_valid.any():
                rolling_preds[t_start:t_end][mask_valid] = Xte_chunk[mask_valid] @ w

        valid = np.isfinite(rolling_preds) & np.isfinite(rolling_actuals)
        if valid.sum() > 10:
            ss_res = np.sum((rolling_actuals[valid] - rolling_preds[valid]) ** 2)
            ss_tot = np.sum((rolling_actuals[valid] - np.mean(rolling_actuals[valid])) ** 2)
            r2_rolling = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
        else:
            r2_rolling = np.nan

        results.append({
            'patient': p['name'],
            'r2_static': float(r2_static) if np.isfinite(r2_static) else np.nan,
            'r2_rolling': float(r2_rolling) if np.isfinite(r2_rolling) else np.nan,
            'delta': float(r2_rolling - r2_static) if np.isfinite(r2_rolling) and np.isfinite(r2_static) else np.nan,
        })

    mean_static = np.nanmean([r['r2_static'] for r in results])
    mean_rolling = np.nanmean([r['r2_rolling'] for r in results])

    return {
        'name': 'EXP-719 Rolling Retrain',
        'status': 'pass',
        'mean_static': float(mean_static),
        'mean_rolling': float(mean_rolling),
        'mean_delta': float(mean_rolling - mean_static),
        'results': results,
        'detail': f"Static R2={mean_static:.3f}, Rolling R2={mean_rolling:.3f}, delta={mean_rolling - mean_static:+.3f}"
    }


def exp_720_ensemble_horizon(patients, detail=False):
    """EXP-720: Horizon-specific models + physics ensemble for multi-step."""
    horizons = [1, 6, 12, 24]  # 5min, 30min, 60min, 120min
    horizon_names = ['5min', '30min', '60min', '120min']
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = len(resid_clean)

        X = _build_features(resid_clean, bg, demand, order=6)
        split = int(n * 0.8)

        for h in horizons:
            # Method 1: Direct h-step AR prediction (from EXP-704)
            y_direct = np.full(n, np.nan)
            if h == 1:
                y_direct = resid_clean.copy()
            else:
                y_direct[:n-h] = resid_clean[h:]
            r2_direct, _, w_direct = _ridge_fit_predict(X[:split], y_direct[:split], X[split:], y_direct[split:])

            # Method 2: Physics forward sim with AR correction
            w_ar1 = _ridge_fit(X[:split, :1], resid_clean[:split], alpha=1.0)
            preds_phys = []
            actuals_phys = []
            for t in range(split, n - h):
                bg_sim = bg[t]
                resid_est = resid_clean[t] if t < len(resid_clean) else 0.0
                for step in range(h):
                    t_s = t + step
                    if t_s >= n - 1:
                        break
                    bg_decay = (120.0 - bg_sim) * 0.005
                    bg_next = bg_sim + supply[t_s] - demand[t_s] + hepatic[t_s] + bg_decay
                    bg_next += w_ar1[0] * resid_est if len(w_ar1) > 0 else 0.0
                    resid_est *= 0.8
                    bg_sim = bg_next
                if t + h < n:
                    preds_phys.append(bg_sim)
                    actuals_phys.append(bg[t + h])

            preds_phys = np.array(preds_phys)
            actuals_phys = np.array(actuals_phys)
            valid = np.isfinite(preds_phys) & np.isfinite(actuals_phys)
            if valid.sum() > 10:
                ss_res = np.sum((actuals_phys[valid] - preds_phys[valid]) ** 2)
                ss_tot = np.sum((actuals_phys[valid] - np.mean(actuals_phys[valid])) ** 2)
                r2_phys = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
            else:
                r2_phys = np.nan

            results_by_h[h].append({
                'patient': p['name'],
                'r2_direct_ar': float(r2_direct) if np.isfinite(r2_direct) else np.nan,
                'r2_physics_sim': float(r2_phys) if np.isfinite(r2_phys) else np.nan,
            })

    summary = {}
    for h, name in zip(horizons, horizon_names):
        ar_vals = [r['r2_direct_ar'] for r in results_by_h[h] if np.isfinite(r['r2_direct_ar'])]
        phys_vals = [r['r2_physics_sim'] for r in results_by_h[h] if np.isfinite(r['r2_physics_sim'])]
        summary[name] = {
            'ar_r2': float(np.mean(ar_vals)) if ar_vals else np.nan,
            'phys_r2': float(np.mean(phys_vals)) if phys_vals else np.nan,
        }

    return {
        'name': 'EXP-720 Ensemble Horizon',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: AR={summary[n]['ar_r2']:.3f}/Phys={summary[n]['phys_r2']:.3f}" for n in horizon_names)
    }


# === registry & runner ===

EXPERIMENTS = {
    'EXP-711': exp_711_adaptive_warmstart,
    'EXP-712': exp_712_minimal_model,
    'EXP-713': exp_713_physics_forward_sim,
    'EXP-714': exp_714_stacking_threshold,
    'EXP-715': exp_715_expanded_dawn,
    'EXP-716': exp_716_noise_floor,
    'EXP-717': exp_717_bg_dependent_noise,
    'EXP-718': exp_718_meal_residual_profile,
    'EXP-719': exp_719_rolling_retrain,
    'EXP-720': exp_720_ensemble_horizon,
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
            status = res.get('status', 'unknown')
            print(f"  Status: {status} ({elapsed:.1f}s)")
            if 'detail' in res:
                print(f"  Detail: {res['detail']}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            results.append({
                'name': eid, 'status': 'fail', 'error': str(e), 'elapsed': elapsed,
            })

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r.get('status') == 'pass')
    failed = sum(1 for r in results if r.get('status') == 'fail')
    print(f"Passed: {passed}/{len(results)}, Failed: {failed}/{len(results)}")
    for r in results:
        sym = 'V' if r.get('status') == 'pass' else 'X'
        detail_str = r.get('detail', r.get('error', ''))[:80]
        print(f"  {sym} {r.get('name', '?')}: {detail_str}")

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
                print(f"  Save error for {safe_name}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="EXP-711-720: AR Breakthrough and Residual Characterization")
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
