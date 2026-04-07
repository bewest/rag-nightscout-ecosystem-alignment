#!/usr/bin/env python3
"""EXP-701-710: Variance Decomposition, AR Optimization, and Multi-Horizon Prediction.

Focus: Understanding what the remaining 53.7% unexplained variance represents,
optimizing model architecture, and extending to multi-step prediction horizons.

Key questions:
- What's the optimal AR order for spike-cleaned data?
- Can nonlinear models capture more of the residual variance?
- How does prediction quality degrade at longer horizons?
- What do the remaining residuals represent physiologically?
- Can population priors + personal fine-tuning beat either alone?
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

# -- imports --
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


# === shared spike cleaning (from EXP-681) ===
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
    # compute residuals
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
    n_base = order + 4  # AR lags + BG^2 + demand^2 + BG*demand + sigmoid
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


def _train_test_split(arr, frac=0.8):
    n = len(arr)
    split = int(n * frac)
    return arr[:split], arr[split:]


# === Experiments ===

def exp_701_ar_order_selection(patients, detail=False):
    """EXP-701: Find optimal AR lag order for spike-cleaned data."""
    orders = [1, 2, 3, 4, 6, 8, 10, 12, 15, 20]
    results_by_order = {o: [] for o in orders}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        for order in orders:
            X = _build_features(resid_clean, bg, demand, order=order)
            y = resid_clean
            Xtr, Xte = _train_test_split(X)
            ytr, yte = _train_test_split(y)
            r2, rmse, w = _ridge_fit_predict(Xtr, ytr, Xte, yte)
            results_by_order[order].append(r2)

    summary = {}
    for order in orders:
        vals = [v for v in results_by_order[order] if np.isfinite(v)]
        summary[order] = {
            'mean_r2': float(np.mean(vals)) if vals else np.nan,
            'std_r2': float(np.std(vals)) if vals else np.nan,
            'min_r2': float(np.min(vals)) if vals else np.nan,
            'max_r2': float(np.max(vals)) if vals else np.nan,
        }

    best_order = max(summary, key=lambda o: summary[o]['mean_r2'])
    sorted_orders = sorted(summary.keys())
    plateau_order = sorted_orders[0]
    for i in range(1, len(sorted_orders)):
        prev = summary[sorted_orders[i-1]]['mean_r2']
        curr = summary[sorted_orders[i]]['mean_r2']
        if curr - prev < 0.005:
            plateau_order = sorted_orders[i-1]
            break
        plateau_order = sorted_orders[i]

    return {
        'name': 'EXP-701 AR Order Selection',
        'status': 'pass',
        'best_order': best_order,
        'best_r2': summary[best_order]['mean_r2'],
        'plateau_order': plateau_order,
        'plateau_r2': summary[plateau_order]['mean_r2'],
        'summary': {str(k): v for k, v in summary.items()},
        'detail': (f"Best AR({best_order}) R2={summary[best_order]['mean_r2']:.3f}, "
                   f"plateau at AR({plateau_order}) R2={summary[plateau_order]['mean_r2']:.3f}")
    }


def exp_702_variance_decomposition(patients, detail=False):
    """EXP-702: Decompose residual variance into physiological components."""
    components = []
    for p in patients:
        fd = _compute_flux(p)
        resid_clean, spike_idx = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        carb_supply = fd['carb_supply']
        n = len(resid_clean)
        df = fd['df']

        total_var = float(np.nanvar(resid_clean))
        if total_var < 1e-10:
            continue

        # 1. AR-explained variance (temporal autocorrelation)
        X_ar = _build_features(resid_clean, bg, demand, order=6)
        y = resid_clean
        Xtr, Xte = _train_test_split(X_ar)
        ytr, yte = _train_test_split(y)
        r2_full, _, _ = _ridge_fit_predict(Xtr, ytr, Xte, yte)
        ar_var = r2_full * total_var if np.isfinite(r2_full) else 0.0

        # 2. Spike variance (removed by cleaning)
        raw_var = float(np.nanvar(fd['resid']))
        spike_var = raw_var - total_var

        # 3. Post-meal variance (within 2h of carb events)
        meal_mask = np.zeros(n, dtype=bool)
        cs = carb_supply[:n]
        meal_times = np.where(cs > 0.5)[0]
        for mt in meal_times:
            lo, hi = mt, min(n, mt + 24)  # 24 steps = 2h at 5min
            meal_mask[lo:hi] = True
        meal_resid = resid_clean[meal_mask]
        fasting_resid = resid_clean[~meal_mask]
        meal_var = float(np.nanvar(meal_resid)) if len(meal_resid) > 10 else 0.0
        fasting_var = float(np.nanvar(fasting_resid)) if len(fasting_resid) > 10 else 0.0
        meal_frac = meal_mask.sum() / n if n > 0 else 0.0

        # 4. Dawn period variance (04:00-08:00)
        if 'dateString' in df.columns:
            try:
                times = pd.to_datetime(df['dateString']).dt.hour.values[:n]
            except Exception:
                times = np.zeros(n)
        else:
            times = np.zeros(n)
        dawn_mask = (times >= 4) & (times < 8)
        dawn_var = float(np.nanvar(resid_clean[dawn_mask])) if dawn_mask.sum() > 10 else 0.0

        # 5. High-BG nonlinearity (BG > 200 vs BG < 200)
        high_mask = bg[:n] > 200
        low_mask = bg[:n] <= 200
        high_var = float(np.nanvar(resid_clean[high_mask])) if high_mask.sum() > 10 else 0.0
        low_var = float(np.nanvar(resid_clean[low_mask])) if low_mask.sum() > 10 else 0.0

        components.append({
            'patient': p['name'],
            'total_var': total_var,
            'spike_var': spike_var,
            'ar_explained_frac': float(r2_full) if np.isfinite(r2_full) else 0.0,
            'meal_var': meal_var,
            'fasting_var': fasting_var,
            'meal_frac': meal_frac,
            'dawn_var': dawn_var,
            'high_bg_var': high_var,
            'low_bg_var': low_var,
            'meal_vs_fasting_ratio': meal_var / fasting_var if fasting_var > 0 else np.nan,
        })

    mean_ar = np.mean([c['ar_explained_frac'] for c in components])
    mean_meal_ratio = np.nanmean([c['meal_vs_fasting_ratio'] for c in components])
    mean_spike = np.mean([c['spike_var'] for c in components])

    return {
        'name': 'EXP-702 Variance Decomposition',
        'status': 'pass',
        'n_patients': len(components),
        'mean_ar_explained': float(mean_ar),
        'mean_meal_vs_fasting_ratio': float(mean_meal_ratio),
        'mean_spike_variance': float(mean_spike),
        'components': components,
        'detail': f"AR explains {mean_ar:.1%}, meal variance {mean_meal_ratio:.1f}x fasting"
    }


def exp_703_population_warmstart(patients, detail=False):
    """EXP-703: Population prior + personal fine-tuning warm-start scheme."""
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

        # Population model (train on all OTHER patients)
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
        A = pop_X.T @ pop_X + 1.0 * np.eye(pop_X.shape[1])
        w_pop = np.linalg.solve(A, pop_X.T @ pop_y)

        # Pure personal model
        r2_personal, _, _ = _ridge_fit_predict(X[:split], y[:split], Xte, yte)

        # Pure population model on test
        mask_te = np.all(np.isfinite(Xte), axis=1)
        valid = mask_te & np.isfinite(yte)
        if valid.sum() < 10:
            continue
        pred_pop = Xte[valid] @ w_pop
        ss_res = np.sum((yte[valid] - pred_pop) ** 2)
        ss_tot = np.sum((yte[valid] - np.mean(yte[valid])) ** 2)
        r2_pop = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        row = {
            'patient': p['name'],
            'r2_pop': float(r2_pop),
            'r2_personal': float(r2_personal),
        }

        # Warm-start: fine-tune with N days, L2 penalty toward w_pop
        steps_per_day = 288
        for days in personal_days:
            n_ft = min(days * steps_per_day, split)
            if n_ft < 20:
                row[f'r2_warmstart_{days}d'] = float(r2_pop)
                continue
            X_ft = X[:n_ft]
            y_ft = y[:n_ft]
            mask_ft = np.all(np.isfinite(X_ft), axis=1) & np.isfinite(y_ft)
            Xf = X_ft[mask_ft]
            yf = y_ft[mask_ft]
            alpha_ft = 10.0  # strong prior toward population
            A_ft = Xf.T @ Xf + alpha_ft * np.eye(Xf.shape[1])
            w_ws = np.linalg.solve(A_ft, Xf.T @ yf + alpha_ft * w_pop)
            pred_ws = Xte[valid] @ w_ws
            ss_res_ws = np.sum((yte[valid] - pred_ws) ** 2)
            r2_ws = 1.0 - ss_res_ws / ss_tot if ss_tot > 0 else np.nan
            row[f'r2_warmstart_{days}d'] = float(r2_ws)

        results.append(row)

    mean_pop = np.mean([r['r2_pop'] for r in results if np.isfinite(r['r2_pop'])])
    mean_pers = np.mean([r['r2_personal'] for r in results if np.isfinite(r['r2_personal'])])
    warmstart_means = {}
    for days in personal_days:
        key = f'r2_warmstart_{days}d'
        vals = [r[key] for r in results if key in r and np.isfinite(r[key])]
        warmstart_means[f'{days}d'] = float(np.mean(vals)) if vals else np.nan

    return {
        'name': 'EXP-703 Population Warmstart',
        'status': 'pass',
        'n_patients': len(results),
        'mean_population_r2': float(mean_pop),
        'mean_personal_r2': float(mean_pers),
        'warmstart_means': warmstart_means,
        'results': results,
        'detail': (f"Pop R2={mean_pop:.3f}, Personal={mean_pers:.3f}, "
                   + ", ".join(f"WS-{k}={v:.3f}" for k, v in warmstart_means.items()))
    }


def exp_704_multi_horizon(patients, detail=False):
    """EXP-704: Multi-step prediction horizons (5-120 min)."""
    horizons = [1, 3, 6, 12, 24]  # steps: 5min, 15min, 30min, 60min, 120min
    horizon_names = ['5min', '15min', '30min', '60min', '120min']
    results_by_h = {h: [] for h in horizons}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = len(resid_clean)

        for h in horizons:
            if h == 1:
                y = resid_clean
                X = _build_features(resid_clean, bg, demand, order=6)
            else:
                # h-step-ahead target
                y = np.full(n, np.nan)
                y[:n-h] = resid_clean[h:]
                X = _build_features(resid_clean, bg, demand, order=6)

            split = int(n * 0.8)
            r2, rmse, _ = _ridge_fit_predict(X[:split], y[:split], X[split:], y[split:])
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
        'name': 'EXP-704 Multi-Horizon Prediction',
        'status': 'pass',
        'summary': summary,
        'results_by_horizon': {n: results_by_h[h] for h, n in zip(horizons, horizon_names)},
        'detail': ", ".join(f"{n}: R2={summary[n]['mean_r2']:.3f}" for n in horizon_names)
    }


def exp_705_feature_importance(patients, detail=False):
    """EXP-705: Feature importance via ablation (drop-one-out)."""
    feature_names = [f'AR_lag{i}' for i in range(1, 7)] + [
        'BG_squared', 'demand_squared', 'BG_x_demand', 'sigmoid'
    ]
    n_features = len(feature_names)
    importance_scores = {name: [] for name in feature_names}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']

        X_full = _build_features(resid_clean, bg, demand, order=6)
        y = resid_clean
        Xtr, Xte = _train_test_split(X_full)
        ytr, yte = _train_test_split(y)

        r2_full, _, _ = _ridge_fit_predict(Xtr, ytr, Xte, yte)
        if not np.isfinite(r2_full):
            continue

        for fi, fname in enumerate(feature_names):
            keep = [j for j in range(n_features) if j != fi]
            r2_drop, _, _ = _ridge_fit_predict(Xtr[:, keep], ytr, Xte[:, keep], yte)
            drop = r2_full - r2_drop if np.isfinite(r2_drop) else r2_full
            importance_scores[fname].append(float(drop))

    avg_importance = {}
    for name in feature_names:
        vals = importance_scores[name]
        avg_importance[name] = float(np.mean(vals)) if vals else 0.0

    ranked = sorted(avg_importance.items(), key=lambda x: -x[1])

    return {
        'name': 'EXP-705 Feature Importance',
        'status': 'pass',
        'ranked_importance': ranked,
        'avg_importance': avg_importance,
        'per_patient': {k: v for k, v in importance_scores.items()},
        'detail': "Top: " + ", ".join(f"{n}={v:.4f}" for n, v in ranked[:5])
    }


def exp_706_nonlinear_residual_boost(patients, detail=False):
    """EXP-706: Gradient boosting on residuals (manual decision stumps)."""
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

        # Linear baseline
        r2_linear, _, w_lin = _ridge_fit_predict(X[:split], y[:split], X[split:], y[split:])

        # Boosted stumps on residuals of linear model
        mask_tr = np.all(np.isfinite(X[:split]), axis=1) & np.isfinite(y[:split])
        mask_te = np.all(np.isfinite(X[split:]), axis=1) & np.isfinite(y[split:])

        pred_tr = X[:split][mask_tr] @ w_lin
        pred_te = X[split:][mask_te] @ w_lin
        resid_tr = y[:split][mask_tr] - pred_tr

        # 50 rounds of gradient boosting with decision stumps
        lr = 0.1
        n_rounds = 50
        boost_pred_tr = np.zeros(mask_tr.sum())
        boost_pred_te = np.zeros(mask_te.sum())

        Xtr_good = X[:split][mask_tr]
        Xte_good = X[split:][mask_te]
        target = resid_tr.copy()

        for round_i in range(n_rounds):
            best_gain = -np.inf
            best_feat = 0
            best_thresh = 0.0
            best_left = 0.0
            best_right = 0.0

            for fi in range(Xtr_good.shape[1]):
                feat = Xtr_good[:, fi]
                valid_f = np.isfinite(feat)
                if valid_f.sum() < 20:
                    continue
                qs = np.quantile(feat[valid_f], np.linspace(0.1, 0.9, 9))
                for thresh in qs:
                    left_mask = feat <= thresh
                    right_mask = feat > thresh
                    if left_mask.sum() < 5 or right_mask.sum() < 5:
                        continue
                    left_mean = np.mean(target[left_mask])
                    right_mean = np.mean(target[right_mask])
                    pred_stump = np.where(left_mask, left_mean, right_mean)
                    gain = -np.sum((target - pred_stump) ** 2)
                    if gain > best_gain:
                        best_gain = gain
                        best_feat = fi
                        best_thresh = thresh
                        best_left = left_mean
                        best_right = right_mean

            stump_tr = np.where(Xtr_good[:, best_feat] <= best_thresh,
                                best_left, best_right)
            stump_te = np.where(Xte_good[:, best_feat] <= best_thresh,
                                best_left, best_right)
            boost_pred_tr += lr * stump_tr
            boost_pred_te += lr * stump_te
            target = resid_tr - boost_pred_tr

        # Combined prediction
        actual_te = y[split:][mask_te]
        ss_res = np.sum((actual_te - (pred_te + boost_pred_te)) ** 2)
        ss_tot = np.sum((actual_te - np.mean(actual_te)) ** 2)
        r2_boosted = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        results.append({
            'patient': p['name'],
            'r2_linear': float(r2_linear) if np.isfinite(r2_linear) else np.nan,
            'r2_boosted': float(r2_boosted) if np.isfinite(r2_boosted) else np.nan,
            'delta': float(r2_boosted - r2_linear) if np.isfinite(r2_boosted) and np.isfinite(r2_linear) else np.nan,
        })

    mean_lin = np.mean([r['r2_linear'] for r in results if np.isfinite(r['r2_linear'])])
    mean_boost = np.mean([r['r2_boosted'] for r in results if np.isfinite(r['r2_boosted'])])

    return {
        'name': 'EXP-706 Nonlinear Residual Boost',
        'status': 'pass',
        'n_patients': len(results),
        'mean_linear_r2': float(mean_lin),
        'mean_boosted_r2': float(mean_boost),
        'mean_delta': float(mean_boost - mean_lin),
        'results': results,
        'detail': f"Linear R2={mean_lin:.3f}, Boosted R2={mean_boost:.3f}, delta={mean_boost - mean_lin:+.3f}"
    }


def exp_707_tod_residual_profile(patients, detail=False):
    """EXP-707: Time-of-day residual profiles -- what does the model miss by hour?"""
    hourly_profiles = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        df = fd['df']
        n = len(resid_clean)

        if 'dateString' in df.columns:
            try:
                hours = pd.to_datetime(df['dateString']).dt.hour.values[:n]
            except Exception:
                hours = np.zeros(n, dtype=int)
        else:
            hours = np.zeros(n, dtype=int)

        hourly = {}
        for h in range(24):
            mask = hours == h
            if mask.sum() < 10:
                hourly[h] = {'mean': 0.0, 'std': 0.0, 'count': 0}
                continue
            hr = resid_clean[mask]
            hourly[h] = {
                'mean': float(np.nanmean(hr)),
                'std': float(np.nanstd(hr)),
                'count': int(mask.sum()),
            }

        hourly_profiles.append({
            'patient': p['name'],
            'hourly': hourly,
        })

    avg_hourly = {}
    for h in range(24):
        means = [hp['hourly'][h]['mean'] for hp in hourly_profiles if hp['hourly'][h]['count'] > 0]
        stds = [hp['hourly'][h]['std'] for hp in hourly_profiles if hp['hourly'][h]['count'] > 0]
        avg_hourly[h] = {
            'mean_residual': float(np.mean(means)) if means else 0.0,
            'mean_std': float(np.mean(stds)) if stds else 0.0,
        }

    worst_hours = sorted(avg_hourly.items(), key=lambda x: -abs(x[1]['mean_residual']))[:5]
    most_variable = sorted(avg_hourly.items(), key=lambda x: -x[1]['mean_std'])[:5]

    return {
        'name': 'EXP-707 Time-of-Day Residual Profile',
        'status': 'pass',
        'n_patients': len(hourly_profiles),
        'avg_hourly': {str(k): v for k, v in avg_hourly.items()},
        'worst_hours': [(h, v['mean_residual']) for h, v in worst_hours],
        'most_variable_hours': [(h, v['mean_std']) for h, v in most_variable],
        'profiles': hourly_profiles,
        'detail': ("Worst hours: " +
                   ', '.join(f"{h}:00 ({v:+.2f})" for h, v in [(h, v['mean_residual']) for h, v in worst_hours[:3]]))
    }


def exp_708_meal_context_residual(patients, detail=False):
    """EXP-708: Post-meal vs fasting residual structure and lag analysis."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        carb_supply = fd['carb_supply']
        n = len(resid_clean)

        cs = carb_supply[:n]
        meal_starts = np.where(np.diff(cs > 0.5, prepend=False))[0]

        # Analyze residuals at different post-meal lags
        post_meal_lags = [0, 6, 12, 18, 24, 36, 48]  # 0-4h in 30min chunks
        lag_stats = {}
        for lag in post_meal_lags:
            lag_resids = []
            for ms in meal_starts:
                idx = ms + lag
                if idx < n and idx + 6 < n:
                    chunk = resid_clean[idx:idx+6]
                    lag_resids.extend(chunk[np.isfinite(chunk)])
            if lag_resids:
                lag_stats[lag * 5] = {
                    'mean': float(np.mean(lag_resids)),
                    'std': float(np.std(lag_resids)),
                    'count': len(lag_resids),
                }

        # Fasting residuals (>3h from any meal)
        meal_proximity = np.full(n, 999)
        for ms in meal_starts:
            for offset in range(-36, 72):
                idx = ms + offset
                if 0 <= idx < n:
                    meal_proximity[idx] = min(meal_proximity[idx], abs(offset))
        fasting_mask = meal_proximity > 36  # >3h from meal
        fasting_resid = resid_clean[fasting_mask]
        fasting_mean = float(np.nanmean(fasting_resid)) if fasting_mask.sum() > 10 else 0.0
        fasting_std = float(np.nanstd(fasting_resid)) if fasting_mask.sum() > 10 else 0.0

        # Lag autocorrelation in meal periods vs fasting
        meal_mask = meal_proximity <= 24  # within 2h of meal
        meal_resid = resid_clean[meal_mask]
        if len(meal_resid) > 20:
            meal_ac1 = float(np.corrcoef(meal_resid[:-1], meal_resid[1:])[0, 1])
        else:
            meal_ac1 = np.nan
        if len(fasting_resid) > 20:
            fast_ac1 = float(np.corrcoef(fasting_resid[:-1], fasting_resid[1:])[0, 1])
        else:
            fast_ac1 = np.nan

        results.append({
            'patient': p['name'],
            'n_meals': len(meal_starts),
            'lag_stats': lag_stats,
            'fasting_mean': fasting_mean,
            'fasting_std': fasting_std,
            'meal_ac1': meal_ac1,
            'fasting_ac1': fast_ac1,
            'fasting_frac': float(fasting_mask.sum() / n) if n > 0 else 0.0,
        })

    mean_meal_ac = np.nanmean([r['meal_ac1'] for r in results])
    mean_fast_ac = np.nanmean([r['fasting_ac1'] for r in results])

    return {
        'name': 'EXP-708 Meal-Context Residual',
        'status': 'pass',
        'n_patients': len(results),
        'mean_meal_autocorr': float(mean_meal_ac),
        'mean_fasting_autocorr': float(mean_fast_ac),
        'results': results,
        'detail': (f"Meal AC={mean_meal_ac:.3f}, Fasting AC={mean_fast_ac:.3f}, "
                   f"delta={mean_meal_ac - mean_fast_ac:+.3f}")
    }


def exp_709_insulin_stacking(patients, detail=False):
    """EXP-709: Detect insulin stacking via flux imbalance patterns."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        demand = fd['demand']
        supply = fd['supply']
        n = fd['n']

        # Rolling demand accumulation (2h window = 24 steps)
        window = 24
        demand_rolling = np.convolve(demand, np.ones(window)/window, mode='same')
        supply_rolling = np.convolve(supply, np.ones(window)/window, mode='same')

        # Stacking = high demand accumulation + falling BG
        bg_change = np.zeros(n)
        bg_change[1:] = bg[1:] - bg[:-1]
        bg_change_smooth = np.convolve(bg_change, np.ones(6)/6, mode='same')

        # Insulin stacking events: demand > 2x supply AND BG falling
        stacking_mask = (demand_rolling > 2 * supply_rolling) & (bg_change_smooth < -1.0)
        n_stacking = int(stacking_mask.sum())

        # Characterize stacking events
        if n_stacking > 0:
            stack_bg = bg[stacking_mask]
            stack_demand = demand_rolling[stacking_mask]
            stack_supply = supply_rolling[stacking_mask]
            mean_stack_bg = float(np.nanmean(stack_bg))
            mean_stack_ratio = float(np.nanmean(stack_demand / np.maximum(stack_supply, 0.01)))
        else:
            mean_stack_bg = np.nan
            mean_stack_ratio = np.nan

        # Hypo events within 1h of stacking
        hypo_mask = bg < 70
        stack_to_hypo = 0
        stack_events = np.where(stacking_mask)[0]
        for se in stack_events:
            window_end = min(n, se + 12)
            if np.any(hypo_mask[se:window_end]):
                stack_to_hypo += 1

        results.append({
            'patient': p['name'],
            'n_stacking_events': n_stacking,
            'stacking_rate_pct': float(n_stacking / n * 100) if n > 0 else 0.0,
            'mean_stacking_bg': mean_stack_bg,
            'mean_demand_supply_ratio': mean_stack_ratio,
            'stack_to_hypo': stack_to_hypo,
            'hypo_conversion_rate': float(stack_to_hypo / max(n_stacking, 1)),
        })

    total_stacking = sum(r['n_stacking_events'] for r in results)
    total_hypo = sum(r['stack_to_hypo'] for r in results)

    return {
        'name': 'EXP-709 Insulin Stacking Detection',
        'status': 'pass',
        'n_patients': len(results),
        'total_stacking_events': total_stacking,
        'total_stack_to_hypo': total_hypo,
        'overall_hypo_conversion': float(total_hypo / max(total_stacking, 1)),
        'results': results,
        'detail': (f"{total_stacking} stacking events, {total_hypo} led to hypo "
                   f"({total_hypo/max(total_stacking,1):.0%} conversion)")
    }


def exp_710_device_age_proxy(patients, detail=False):
    """EXP-710: Detect sensor/cannula age effects from residual patterns."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        df = fd['df']
        n = len(resid_clean)

        # Group by day and compute daily residual statistics
        if 'dateString' in df.columns:
            try:
                dates = pd.to_datetime(df['dateString']).dt.date.values[:n]
                unique_dates = sorted(set(dates))
            except Exception:
                unique_dates = []
        else:
            unique_dates = []

        if len(unique_dates) < 14:
            results.append({
                'patient': p['name'],
                'n_days': len(unique_dates),
                'sensor_cycle_detected': False,
                'detail': 'insufficient data'
            })
            continue

        daily_stats = []
        for d in unique_dates:
            mask = dates == d
            day_resid = resid_clean[mask]
            day_bg = bg[:n][mask]
            if len(day_resid) < 50:
                continue
            daily_stats.append({
                'date': str(d),
                'resid_std': float(np.nanstd(day_resid)),
                'resid_mean': float(np.nanmean(day_resid)),
                'bg_std': float(np.nanstd(day_bg)),
                'spike_rate': float(np.sum(np.abs(np.diff(day_resid)) > np.nanstd(day_resid) * 2) / max(len(day_resid), 1)),
            })

        if len(daily_stats) < 10:
            results.append({
                'patient': p['name'],
                'n_days': len(daily_stats),
                'sensor_cycle_detected': False,
                'detail': 'insufficient daily data'
            })
            continue

        resid_stds = np.array([d['resid_std'] for d in daily_stats])
        spike_rates = np.array([d['spike_rate'] for d in daily_stats])

        # Autocorrelation at lag 10 days (sensor sessions are 10 days)
        if len(resid_stds) > 20:
            centered = resid_stds - np.mean(resid_stds)
            ac = np.correlate(centered, centered, mode='full')
            ac = ac[len(ac)//2:]
            ac = ac / ac[0] if ac[0] > 0 else ac

            peak_lags = [7, 8, 9, 10, 11, 12, 13, 14]
            peak_acs = [float(ac[lag]) if lag < len(ac) else 0.0 for lag in peak_lags]
            max_ac = max(peak_acs) if peak_acs else 0.0
            sensor_cycle = max_ac > 0.15

            # Day-in-cycle analysis (assume 10-day sensor)
            cycle_day = np.arange(len(resid_stds)) % 10
            day_in_cycle_std = {}
            for d in range(10):
                mask_d = cycle_day == d
                if mask_d.sum() > 0:
                    day_in_cycle_std[d] = float(np.mean(resid_stds[mask_d]))

            # Trend within cycle
            if len(day_in_cycle_std) >= 8:
                days_list = sorted(day_in_cycle_std.keys())
                vals = [day_in_cycle_std[d] for d in days_list]
                trend = float(np.polyfit(days_list, vals, 1)[0])
            else:
                trend = 0.0
        else:
            max_ac = 0.0
            sensor_cycle = False
            day_in_cycle_std = {}
            trend = 0.0

        results.append({
            'patient': p['name'],
            'n_days': len(daily_stats),
            'sensor_cycle_detected': sensor_cycle,
            'max_periodic_ac': float(max_ac),
            'cycle_trend': float(trend),
            'day_in_cycle_std': {str(k): v for k, v in day_in_cycle_std.items()},
        })

    n_detected = sum(1 for r in results if r.get('sensor_cycle_detected', False))
    mean_ac = np.mean([r.get('max_periodic_ac', 0) for r in results])

    return {
        'name': 'EXP-710 Device Age Proxy',
        'status': 'pass',
        'n_patients': len(results),
        'n_cycle_detected': n_detected,
        'mean_periodic_ac': float(mean_ac),
        'results': results,
        'detail': (f"{n_detected}/{len(results)} patients show sensor cycle periodicity, "
                   f"mean AC={mean_ac:.3f}")
    }


# === registry & runner ===

EXPERIMENTS = {
    'EXP-701': exp_701_ar_order_selection,
    'EXP-702': exp_702_variance_decomposition,
    'EXP-703': exp_703_population_warmstart,
    'EXP-704': exp_704_multi_horizon,
    'EXP-705': exp_705_feature_importance,
    'EXP-706': exp_706_nonlinear_residual_boost,
    'EXP-707': exp_707_tod_residual_profile,
    'EXP-708': exp_708_meal_context_residual,
    'EXP-709': exp_709_insulin_stacking,
    'EXP-710': exp_710_device_age_proxy,
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
                'name': eid,
                'status': 'fail',
                'error': str(e),
                'elapsed': elapsed,
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
    parser = argparse.ArgumentParser(description="EXP-701-710: Variance Decomposition and AR Optimization")
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None, help='Run only one experiment, e.g. EXP-701')
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    run_all(patients, detail=args.detail, save=args.save, only=args.only)


if __name__ == '__main__':
    main()
