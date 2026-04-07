#!/usr/bin/env python3
"""EXP-562/563/564/565/568/569/570: Information theory, ensemble prediction,
exploring the 11% unknown residual.

Building on 50 experiments (EXP-511-561):
  - Flux+AR explains 57% of dBG variance (16% flux + 41% AR)
  - Kalman+AR: skill=0.174, best at 20-30min horizons (EXP-552/557)
  - Correction energy predicts TIR (r=-0.35, EXP-559)
  - Circadian mismatch is actionable (9/11 need dawn review, EXP-560)
  - Granger causality bidirectional (10/11, EXP-561)

This wave targets:
  1. Information theory — Transfer entropy & MI profiles (EXP-562/563)
  2. Prediction — State-specific Kalman & ensemble (EXP-564/565)
  3. The 11% unknown — Meal variability, stress proxy, residual memory (EXP-568/569/570)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


def _get_bg(df):
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[bg_col].values.astype(float)


def _compute_dbg(bg):
    N = len(bg)
    dbg = np.full(N, np.nan)
    dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
    if N > 1:
        dbg[0] = bg[1] - bg[0]
        dbg[-1] = bg[-1] - bg[-2]
    return dbg


def _build_ar_features(residuals, order=6):
    N = len(residuals)
    X_ar = np.zeros((N, order))
    for lag in range(1, order + 1):
        X_ar[lag:, lag - 1] = residuals[:-lag]
    return X_ar


def _classify_states(bg, dbg, carb_supply, demand, valid):
    N = len(bg)
    carb_pos = carb_supply[valid & (carb_supply > 0)]
    carb_thresh = np.percentile(carb_pos, 25) if len(carb_pos) > 0 else 0.1
    demand_med = np.median(demand[valid])
    states = np.full(N, -1, dtype=int)
    STATE_NAMES = ['fasting', 'post_meal', 'correction', 'recovery', 'stable']
    states[valid & (carb_supply > carb_thresh)] = 1
    mask_unset = valid & (states == -1)
    states[mask_unset & (carb_supply <= 0.01) & (demand < demand_med)] = 0
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg > 180) & (demand > demand_med)] = 2
    mask_unset = valid & (states == -1)
    states[mask_unset & (dbg < -1)] = 3
    mask_unset = valid & (states == -1)
    states[mask_unset] = 4
    return states, STATE_NAMES


def _fit_flux_ar(bg_v, supply_v, demand_v, hepatic_v, split, ar_order=6, lam=1.0):
    """Fit flux + AR model, return predictions and coefficients."""
    N = len(bg_v)
    dbg = np.full(N, np.nan)
    dbg[1:] = np.diff(bg_v)
    dbg[0] = 0.0

    X_flux = np.column_stack([supply_v, demand_v, hepatic_v, bg_v])
    y_all = dbg

    train_valid = (np.arange(N) < split) & np.isfinite(y_all) & np.all(np.isfinite(X_flux), axis=1)
    if np.sum(train_valid) < 50:
        return None

    try:
        X_tr = X_flux[train_valid]
        y_tr = y_all[train_valid]
        XtX = X_tr.T @ X_tr + lam * np.eye(X_tr.shape[1])
        Xty = X_tr.T @ y_tr
        beta_flux = np.linalg.solve(XtX, Xty)
    except Exception:
        return None

    flux_pred = X_flux @ beta_flux
    flux_resid = y_all - flux_pred

    X_ar = _build_ar_features(flux_resid, ar_order)
    ar_train_valid = (np.arange(N) >= ar_order) & (np.arange(N) < split) & \
                     np.all(np.isfinite(X_ar), axis=1) & np.isfinite(flux_resid)
    if np.sum(ar_train_valid) < 50:
        return None

    try:
        X_ar_tr = X_ar[ar_train_valid]
        y_ar_tr = flux_resid[ar_train_valid]
        XtX_ar = X_ar_tr.T @ X_ar_tr + 0.1 * np.eye(ar_order)
        Xty_ar = X_ar_tr.T @ y_ar_tr
        beta_ar = np.linalg.solve(XtX_ar, Xty_ar)
    except Exception:
        return None

    ar_pred = X_ar @ beta_ar
    combined_pred = flux_pred + ar_pred
    combined_resid = y_all - combined_pred

    return {
        'dbg': dbg, 'flux_pred': flux_pred, 'flux_resid': flux_resid,
        'ar_pred': ar_pred, 'combined_pred': combined_pred,
        'combined_resid': combined_resid,
        'beta_flux': beta_flux, 'beta_ar': beta_ar,
    }


# ──────────────────────────────────────────────
# EXP-562: Transfer Entropy
# ──────────────────────────────────────────────
def _estimate_transfer_entropy(source, target, lag=1, n_bins=8):
    """Estimate transfer entropy T(source → target) using binned MI.

    TE(X→Y) = H(Y_t | Y_{t-lag}) - H(Y_t | Y_{t-lag}, X_{t-lag})
    """
    N = len(source)
    if N < 200:
        return np.nan

    # Discretize into bins
    s_bins = np.digitize(source, np.linspace(np.nanmin(source), np.nanmax(source), n_bins + 1)[:-1])
    t_bins = np.digitize(target, np.linspace(np.nanmin(target), np.nanmax(target), n_bins + 1)[:-1])

    # Build joint distributions
    # p(y_t, y_{t-lag}) and p(y_t, y_{t-lag}, x_{t-lag})
    y_now = t_bins[lag:]
    y_past = t_bins[:-lag]
    x_past = s_bins[:-lag]

    # H(Y_t | Y_{t-lag}) via joint entropy
    # H(Y|X) = H(Y,X) - H(X)
    def joint_entropy(*arrays):
        combined = np.zeros(len(arrays[0]), dtype=int)
        multiplier = 1
        for arr in reversed(arrays):
            combined += arr * multiplier
            multiplier *= (n_bins + 2)
        _, counts = np.unique(combined, return_counts=True)
        probs = counts / counts.sum()
        return -np.sum(probs * np.log2(probs + 1e-12))

    h_yt_ypast = joint_entropy(y_now, y_past)
    h_ypast = joint_entropy(y_past)
    h_cond_no_x = h_yt_ypast - h_ypast

    h_yt_ypast_xpast = joint_entropy(y_now, y_past, x_past)
    h_ypast_xpast = joint_entropy(y_past, x_past)
    h_cond_with_x = h_yt_ypast_xpast - h_ypast_xpast

    te = h_cond_no_x - h_cond_with_x
    return float(te)


def exp562_transfer_entropy(patients, detail=False):
    """Measure directional information flow: flux→BG vs BG→flux."""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        net = flux['net']
        supply = flux['supply']
        demand = flux['demand']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        net_v = net[valid]
        dbg_v = _compute_dbg(bg_v)

        valid_both = np.isfinite(dbg_v) & np.isfinite(net_v)
        dbg_clean = dbg_v[valid_both]
        net_clean = net_v[valid_both]

        # Transfer entropy at multiple lags
        te_flux_to_bg = {}
        te_bg_to_flux = {}
        for lag in [1, 2, 3, 6, 12]:
            te_fb = _estimate_transfer_entropy(net_clean, dbg_clean, lag=lag)
            te_bf = _estimate_transfer_entropy(dbg_clean, net_clean, lag=lag)
            te_flux_to_bg[lag] = te_fb
            te_bg_to_flux[lag] = te_bf

        # Per-channel transfer entropy (lag=1)
        supply_v = supply[valid][valid_both]
        demand_v = demand[valid][valid_both]
        te_supply = _estimate_transfer_entropy(supply_v, dbg_clean, lag=1)
        te_demand = _estimate_transfer_entropy(demand_v, dbg_clean, lag=1)

        # Dominant direction at lag=1
        te_fb_1 = te_flux_to_bg.get(1, 0)
        te_bf_1 = te_bg_to_flux.get(1, 0)
        asymmetry = te_fb_1 - te_bf_1
        dominant = 'flux→BG' if asymmetry > 0.01 else 'BG→flux' if asymmetry < -0.01 else 'symmetric'

        results[name] = {
            'te_flux_to_bg': {str(k): float(v) for k, v in te_flux_to_bg.items()},
            'te_bg_to_flux': {str(k): float(v) for k, v in te_bg_to_flux.items()},
            'te_supply_to_bg': float(te_supply),
            'te_demand_to_bg': float(te_demand),
            'asymmetry_lag1': float(asymmetry),
            'dominant': dominant,
        }

        if detail:
            print(f"  {name}: flux→BG TE={te_fb_1:.4f}, BG→flux TE={te_bf_1:.4f}, "
                  f"Δ={asymmetry:+.4f} ({dominant}), "
                  f"supply→BG={te_supply:.4f}, demand→BG={te_demand:.4f}")

    asym = [r['asymmetry_lag1'] for r in results.values()]
    dirs = [r['dominant'] for r in results.values()]
    dir_counts = {d: dirs.count(d) for d in set(dirs)}

    summary = {
        'experiment': 'EXP-562',
        'name': 'Transfer Entropy',
        'mean_asymmetry': float(np.mean(asym)) if asym else 0,
        'direction_counts': dir_counts,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-562 Summary: mean asymmetry={np.mean(asym):+.4f}, directions={dir_counts}")

    return summary


# ──────────────────────────────────────────────
# EXP-563: Mutual Information Lag Profiles
# ──────────────────────────────────────────────
def exp563_mi_profiles(patients, detail=False):
    """MI between flux channels and dBG at different lags."""
    results = {}

    def _binned_mi(x, y, n_bins=10):
        """Estimate MI(X;Y) via binning."""
        N = len(x)
        if N < 100:
            return 0.0
        x_bins = np.digitize(x, np.linspace(np.nanmin(x), np.nanmax(x), n_bins + 1)[:-1])
        y_bins = np.digitize(y, np.linspace(np.nanmin(y), np.nanmax(y), n_bins + 1)[:-1])

        # Joint
        joint = np.zeros((n_bins + 1, n_bins + 1))
        for i in range(N):
            joint[x_bins[i], y_bins[i]] += 1
        joint /= N

        # Marginals
        px = joint.sum(axis=1)
        py = joint.sum(axis=0)

        mi = 0.0
        for i in range(n_bins + 1):
            for j in range(n_bins + 1):
                if joint[i, j] > 1e-12 and px[i] > 1e-12 and py[j] > 1e-12:
                    mi += joint[i, j] * np.log2(joint[i, j] / (px[i] * py[j]))
        return float(mi)

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        dbg_v = _compute_dbg(bg_v)

        channels = {
            'supply': supply[valid],
            'demand': demand[valid],
            'hepatic': hepatic[valid],
            'net': net[valid],
        }

        lags = list(range(0, 13))  # 0-60 min in 5-min steps
        mi_profiles = {}

        for ch_name, ch_data in channels.items():
            lag_mis = []
            for lag in lags:
                if lag == 0:
                    x = ch_data
                    y = dbg_v
                else:
                    x = ch_data[:-lag]
                    y = dbg_v[lag:]

                valid_both = np.isfinite(x) & np.isfinite(y)
                if np.sum(valid_both) < 200:
                    lag_mis.append(0.0)
                    continue

                mi = _binned_mi(x[valid_both], y[valid_both])
                lag_mis.append(mi)

            mi_profiles[ch_name] = lag_mis
            peak_lag = lags[np.argmax(lag_mis)]
            peak_mi = max(lag_mis)

        # Find best channel and lag
        best_ch = max(mi_profiles, key=lambda c: max(mi_profiles[c]))
        best_lag = lags[np.argmax(mi_profiles[best_ch])]
        best_mi = max(mi_profiles[best_ch])

        results[name] = {
            'mi_profiles': {k: [float(v) for v in vals] for k, vals in mi_profiles.items()},
            'lags_min': [l * 5 for l in lags],
            'best_channel': best_ch,
            'best_lag_min': best_lag * 5,
            'best_mi': float(best_mi),
        }

        if detail:
            peaks = {ch: (lags[np.argmax(mi_profiles[ch])] * 5, max(mi_profiles[ch]))
                     for ch in mi_profiles}
            parts = [f"{ch}:{lag}min MI={mi:.4f}" for ch, (lag, mi) in peaks.items()]
            print(f"  {name}: {', '.join(parts)} → best={best_ch}@{best_lag * 5}min")

    summary = {
        'experiment': 'EXP-563',
        'name': 'Mutual Information Lag Profiles',
        'patients': results,
    }

    if detail:
        best_chs = [r['best_channel'] for r in results.values()]
        best_lags = [r['best_lag_min'] for r in results.values()]
        ch_counts = {c: best_chs.count(c) for c in set(best_chs)}
        print(f"\n  EXP-563 Summary: best channels={ch_counts}, "
              f"mean best lag={np.mean(best_lags):.0f}min")

    return summary


# ──────────────────────────────────────────────
# EXP-564: State-Specific Kalman
# ──────────────────────────────────────────────
def exp564_state_kalman(patients, detail=False):
    """Per-state Q/R tuning for Kalman filter."""
    results = {}
    ar_order = 6

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']
        net = flux['net']
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        N = len(bg_v)
        if N < 500:
            continue

        split = int(0.8 * N)
        dbg_v = _compute_dbg(bg_v)

        # Classify states on valid data
        states_all, snames = _classify_states(bg_v, dbg_v, carb_supply[valid],
                                              demand[valid], np.ones(N, dtype=bool))

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        flux_pred = model['flux_pred']
        beta_ar = model['beta_ar']
        flux_resid = model['flux_resid']
        combined_resid = model['combined_resid']

        # Compute per-state innovation variance from training data
        train_resid = combined_resid[:split]
        train_states = states_all[:split]
        state_innov_var = {}
        for si, sn in enumerate(snames):
            mask = (train_states == si) & np.isfinite(train_resid)
            if np.sum(mask) > 20:
                state_innov_var[si] = float(np.var(train_resid[mask]))
            else:
                state_innov_var[si] = float(np.var(train_resid[np.isfinite(train_resid)]))

        # Global Kalman (baseline, same as EXP-552)
        global_innov_var = np.var(train_resid[np.isfinite(train_resid)])
        Q_global = global_innov_var * 0.8
        R_global = global_innov_var * 0.2

        # Run both global and state-specific Kalman on test data
        def run_kalman(Q_func, R_func):
            bg_est = bg_v[split]
            P = R_func(0)
            preds = []
            resid_hist = list(flux_resid[split - ar_order:split])

            for t in range(split, N):
                state = states_all[t]
                Q = Q_func(state)
                R = R_func(state)

                if len(resid_hist) >= ar_order:
                    ar_input = np.array(resid_hist[-ar_order:])[::-1]
                    ar_val = float(np.clip(ar_input @ beta_ar, -50, 50))
                else:
                    ar_val = 0.0

                flux_val = float(np.clip(flux_pred[t], -50, 50))
                bg_pred = bg_est + flux_val + ar_val
                P_pred = P + Q

                preds.append(bg_pred)

                y_obs = bg_v[t]
                S = P_pred + R
                K = P_pred / S
                bg_est = bg_pred + K * (y_obs - bg_pred)
                P = (1.0 - K) * P_pred

                actual_dbg = y_obs - bg_v[t - 1] if t > 0 else 0.0
                resid_hist.append(float(actual_dbg - flux_val))

            return np.array(preds)

        # Global Kalman
        global_preds = run_kalman(lambda s: Q_global, lambda s: R_global)

        # State-specific Kalman
        state_preds = run_kalman(
            lambda s: state_innov_var.get(s, global_innov_var) * 0.8,
            lambda s: state_innov_var.get(s, global_innov_var) * 0.2
        )

        # Evaluate
        actual_test = bg_v[split:]
        persist_test = np.concatenate([[bg_v[split - 1]], bg_v[split:-1]])

        valid_test = np.isfinite(global_preds) & np.isfinite(state_preds) & np.isfinite(actual_test)
        if np.sum(valid_test) < 20:
            continue

        mse_global = np.mean((global_preds[valid_test] - actual_test[valid_test]) ** 2)
        mse_state = np.mean((state_preds[valid_test] - actual_test[valid_test]) ** 2)
        mse_persist = np.mean((persist_test[valid_test] - actual_test[valid_test]) ** 2)

        skill_global = 1.0 - mse_global / mse_persist if mse_persist > 0 else 0
        skill_state = 1.0 - mse_state / mse_persist if mse_persist > 0 else 0
        improvement = skill_state - skill_global

        results[name] = {
            'skill_global': float(skill_global),
            'skill_state': float(skill_state),
            'improvement': float(improvement),
            'state_innov_var': {snames[k]: float(v) for k, v in state_innov_var.items()},
        }

        if detail:
            print(f"  {name}: global={skill_global:.3f}, state={skill_state:.3f}, "
                  f"Δ={improvement:+.3f}")

    skills_g = [r['skill_global'] for r in results.values()]
    skills_s = [r['skill_state'] for r in results.values()]
    imps = [r['improvement'] for r in results.values()]

    summary = {
        'experiment': 'EXP-564',
        'name': 'State-Specific Kalman',
        'mean_skill_global': float(np.mean(skills_g)) if skills_g else 0,
        'mean_skill_state': float(np.mean(skills_s)) if skills_s else 0,
        'mean_improvement': float(np.mean(imps)) if imps else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-564 Summary: global={np.mean(skills_g):.3f}, "
              f"state={np.mean(skills_s):.3f}, Δ={np.mean(imps):+.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-565: Ensemble Prediction
# ──────────────────────────────────────────────
def exp565_ensemble(patients, detail=False):
    """Combine Kalman + AR-only + persistence with optimal weights."""
    results = {}
    ar_order = 6

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        N = len(bg_v)
        if N < 500:
            continue

        split = int(0.8 * N)
        val_split = int(0.6 * N)  # 60% train, 20% val, 20% test

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], val_split)
        if model is None:
            continue

        flux_pred = model['flux_pred']
        beta_ar = model['beta_ar']
        flux_resid = model['flux_resid']
        combined_resid = model['combined_resid']
        combined_pred = model['combined_pred']

        # Three predictors for dBG:
        # 1. Persistence: dBG = 0 → BG_{t+1} = BG_t
        # 2. AR-only: dBG = AR(6) on raw dBG
        # 3. Kalman (flux+AR)

        dbg = np.full(N, np.nan)
        dbg[1:] = np.diff(bg_v)
        dbg[0] = 0.0

        # AR-only model (no flux)
        X_ar_raw = _build_ar_features(dbg, ar_order)
        ar_train = (np.arange(N) >= ar_order) & (np.arange(N) < val_split) & \
                   np.all(np.isfinite(X_ar_raw), axis=1) & np.isfinite(dbg)
        if np.sum(ar_train) < 50:
            continue

        try:
            X_art = X_ar_raw[ar_train]
            y_art = dbg[ar_train]
            XtX = X_art.T @ X_art + 0.1 * np.eye(ar_order)
            beta_ar_only = np.linalg.solve(XtX, X_art.T @ y_art)
        except Exception:
            continue

        ar_only_pred = X_ar_raw @ beta_ar_only

        # Generate all three predictions on validation set (val_split:split)
        val_mask = (np.arange(N) >= val_split) & (np.arange(N) < split)
        valid_val = val_mask & np.isfinite(dbg) & np.isfinite(combined_pred) & \
                    np.isfinite(ar_only_pred)
        n_val = int(np.sum(valid_val))
        if n_val < 50:
            continue

        y_val = dbg[valid_val]
        pred_persist = np.zeros(n_val)  # persistence predicts dBG=0
        pred_ar = ar_only_pred[valid_val]
        pred_kalman = combined_pred[valid_val]

        # Find optimal ensemble weights via least squares on validation
        X_ens = np.column_stack([pred_persist, pred_ar, pred_kalman])
        try:
            XtX = X_ens.T @ X_ens + 0.01 * np.eye(3)
            weights = np.linalg.solve(XtX, X_ens.T @ y_val)
            # Normalize to sum to 1
            weights = weights / np.sum(weights) if np.sum(weights) != 0 else np.array([1 / 3] * 3)
        except Exception:
            weights = np.array([1 / 3] * 3)

        # Evaluate on test set (split:)
        test_mask = (np.arange(N) >= split)
        valid_test = test_mask & np.isfinite(dbg) & np.isfinite(combined_pred) & \
                     np.isfinite(ar_only_pred)
        n_test = int(np.sum(valid_test))
        if n_test < 20:
            continue

        y_test = dbg[valid_test]
        pred_test = np.column_stack([
            np.zeros(n_test),
            ar_only_pred[valid_test],
            combined_pred[valid_test]
        ])
        ensemble_pred = pred_test @ weights

        # MSEs
        mse_persist = np.mean(y_test ** 2)
        mse_ar = np.mean((y_test - ar_only_pred[valid_test]) ** 2)
        mse_kalman = np.mean((y_test - combined_pred[valid_test]) ** 2)
        mse_ensemble = np.mean((y_test - ensemble_pred) ** 2)

        r2_ar = 1 - mse_ar / mse_persist if mse_persist > 0 else 0
        r2_kalman = 1 - mse_kalman / mse_persist if mse_persist > 0 else 0
        r2_ensemble = 1 - mse_ensemble / mse_persist if mse_persist > 0 else 0

        results[name] = {
            'weights': {'persist': float(weights[0]), 'ar_only': float(weights[1]),
                       'kalman': float(weights[2])},
            'r2_ar_only': float(r2_ar),
            'r2_kalman': float(r2_kalman),
            'r2_ensemble': float(r2_ensemble),
            'ensemble_improvement': float(r2_ensemble - r2_kalman),
        }

        if detail:
            print(f"  {name}: AR={r2_ar:.3f}, Kalman={r2_kalman:.3f}, "
                  f"Ensemble={r2_ensemble:.3f} (Δ={r2_ensemble - r2_kalman:+.3f}), "
                  f"w=[{weights[0]:.2f},{weights[1]:.2f},{weights[2]:.2f}]")

    r2_ks = [r['r2_kalman'] for r in results.values()]
    r2_es = [r['r2_ensemble'] for r in results.values()]
    imps = [r['ensemble_improvement'] for r in results.values()]

    summary = {
        'experiment': 'EXP-565',
        'name': 'Ensemble Prediction',
        'mean_r2_kalman': float(np.mean(r2_ks)) if r2_ks else 0,
        'mean_r2_ensemble': float(np.mean(r2_es)) if r2_es else 0,
        'mean_improvement': float(np.mean(imps)) if imps else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-565 Summary: Kalman={np.mean(r2_ks):.3f}, "
              f"Ensemble={np.mean(r2_es):.3f}, Δ={np.mean(imps):+.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-568: Meal Absorption Variability
# ──────────────────────────────────────────────
def exp568_meal_variability(patients, detail=False):
    """Compare residual variance in post-meal vs fasting windows."""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']
        net = flux['net']
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        N = len(bg_v)
        split = int(0.8 * N)
        dbg_v = _compute_dbg(bg_v)

        states, snames = _classify_states(bg_v, dbg_v, carb_supply[valid],
                                          demand[valid], np.ones(N, dtype=bool))

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']

        # Compare residual statistics by state
        state_resid_stats = {}
        for si, sn in enumerate(snames):
            mask = (states == si) & np.isfinite(resid)
            if np.sum(mask) > 50:
                r = resid[mask]
                state_resid_stats[sn] = {
                    'mean': float(np.mean(r)),
                    'std': float(np.std(r)),
                    'var': float(np.var(r)),
                    'skew': float(stats.skew(r)),
                    'kurtosis': float(stats.kurtosis(r)),
                    'n': int(np.sum(mask)),
                }

        if 'fasting' not in state_resid_stats or 'post_meal' not in state_resid_stats:
            continue

        fasting_var = state_resid_stats['fasting']['var']
        meal_var = state_resid_stats['post_meal']['var']
        variance_ratio = meal_var / fasting_var if fasting_var > 0 else np.nan

        # F-test for variance equality
        n_fast = state_resid_stats['fasting']['n']
        n_meal = state_resid_stats['post_meal']['n']
        f_stat = meal_var / fasting_var if fasting_var > 0 else np.nan
        p_value = 2 * (1 - stats.f.cdf(f_stat, n_meal - 1, n_fast - 1)) if np.isfinite(f_stat) else 1.0

        results[name] = {
            'state_resid_stats': state_resid_stats,
            'meal_vs_fasting_var_ratio': float(variance_ratio),
            'f_test_p': float(p_value),
            'significant': bool(p_value < 0.01),
        }

        if detail:
            sig = "*" if p_value < 0.01 else ""
            print(f"  {name}: meal_var/fasting_var={variance_ratio:.2f}{sig}, "
                  f"meal std={state_resid_stats['post_meal']['std']:.2f}, "
                  f"fasting std={state_resid_stats['fasting']['std']:.2f}")

    ratios = [r['meal_vs_fasting_var_ratio'] for r in results.values() if np.isfinite(r['meal_vs_fasting_var_ratio'])]
    sig_count = sum(1 for r in results.values() if r['significant'])

    summary = {
        'experiment': 'EXP-568',
        'name': 'Meal Absorption Variability',
        'mean_variance_ratio': float(np.mean(ratios)) if ratios else 0,
        'sig_count': sig_count,
        'total': len(results),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-568 Summary: mean meal/fasting var ratio={np.mean(ratios):.2f}, "
              f"{sig_count}/{len(results)} significant")

    return summary


# ──────────────────────────────────────────────
# EXP-569: Stress/Cortisol Proxy
# ──────────────────────────────────────────────
def exp569_stress_proxy(patients, detail=False):
    """Quantify dawn-phenomenon-like events outside morning hours."""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        net = flux['net']
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        N = len(bg_v)
        dbg_v = _compute_dbg(bg_v)
        split = int(0.8 * N)

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], flux['hepatic'][valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        resid_std = np.std(resid[np.isfinite(resid)])

        # Dawn phenomenon signature: BG rising (positive residual) despite
        # low carb supply and normal/elevated insulin. This is hepatic glucose
        # output driven by cortisol/growth hormone.
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288  # time-of-day bin

        # Define dawn events: positive residual > 1σ, low carb supply
        carb_v = carb_supply[valid]
        carb_median = np.median(carb_v[carb_v > 0]) if np.sum(carb_v > 0) > 0 else 0.1

        dawn_like = np.isfinite(resid) & (resid > resid_std) & (carb_v < carb_median * 0.5)

        # Count by time of day
        periods = {
            'overnight': (0, 72),    # 00:00-06:00
            'morning': (72, 144),    # 06:00-12:00 (actual dawn)
            'afternoon': (144, 216), # 12:00-18:00
            'evening': (216, 288),   # 18:00-24:00
        }

        period_rates = {}
        for pname, (t0, t1) in periods.items():
            mask = (tod >= t0) & (tod < t1)
            total = np.sum(mask)
            dawn_in_period = np.sum(dawn_like & mask)
            rate = dawn_in_period / total if total > 0 else 0
            period_rates[pname] = {
                'rate': float(rate),
                'count': int(dawn_in_period),
                'total': int(total),
            }

        # Stress events = dawn-like events OUTSIDE morning (unexpected hepatic rises)
        non_morning = ~((tod >= 72) & (tod < 144))
        stress_events = np.sum(dawn_like & non_morning)
        stress_rate = stress_events / np.sum(non_morning) if np.sum(non_morning) > 0 else 0

        # Compare morning vs afternoon ratio
        morning_rate = period_rates.get('morning', {}).get('rate', 0)
        afternoon_rate = period_rates.get('afternoon', {}).get('rate', 0)
        dawn_specificity = morning_rate / afternoon_rate if afternoon_rate > 0.001 else np.nan

        results[name] = {
            'period_rates': period_rates,
            'stress_rate': float(stress_rate),
            'stress_events': int(stress_events),
            'dawn_specificity': float(dawn_specificity) if np.isfinite(dawn_specificity) else None,
        }

        if detail:
            parts = [f"{pn}:{pr['rate']:.1%}" for pn, pr in period_rates.items()]
            dawn_spec = f", dawn specificity={dawn_specificity:.2f}" if np.isfinite(dawn_specificity) else ""
            print(f"  {name}: {', '.join(parts)}, stress_rate={stress_rate:.1%}{dawn_spec}")

    stress_rates = [r['stress_rate'] for r in results.values()]
    dawn_specs = [r['dawn_specificity'] for r in results.values()
                  if r['dawn_specificity'] is not None]

    summary = {
        'experiment': 'EXP-569',
        'name': 'Stress/Cortisol Proxy',
        'mean_stress_rate': float(np.mean(stress_rates)) if stress_rates else 0,
        'mean_dawn_specificity': float(np.mean(dawn_specs)) if dawn_specs else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-569 Summary: mean stress_rate={np.mean(stress_rates):.1%}, "
              f"dawn specificity={np.mean(dawn_specs):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-570: Residual Autocorrelation Structure
# ──────────────────────────────────────────────
def exp570_residual_acf(patients, detail=False):
    """Do combined residuals have memory beyond AR(6)?"""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        N = len(bg_v)
        split = int(0.8 * N)

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        valid_r = np.isfinite(resid)
        resid_clean = resid[valid_r]
        N_r = len(resid_clean)

        if N_r < 500:
            continue

        # Compute ACF up to 144 lags (12 hours at 5-min intervals)
        max_lag = 144
        resid_demean = resid_clean - np.mean(resid_clean)
        var_r = np.var(resid_clean)
        if var_r < 1e-12:
            continue

        acf = np.zeros(max_lag + 1)
        for lag in range(max_lag + 1):
            if lag == 0:
                acf[0] = 1.0
            else:
                acf[lag] = np.mean(resid_demean[lag:] * resid_demean[:-lag]) / var_r

        # Key lag thresholds
        # Where does ACF first cross zero?
        zero_cross = max_lag
        for i in range(1, max_lag + 1):
            if acf[i] <= 0:
                zero_cross = i
                break

        # ACF at key lags
        acf_at_lags = {
            '5min': float(acf[1]),
            '30min': float(acf[6]),
            '1h': float(acf[12]),
            '2h': float(acf[24]),
            '4h': float(acf[48]),
            '6h': float(acf[72]),
            '12h': float(acf[144]) if max_lag >= 144 else float(acf[-1]),
        }

        # Significance threshold (approximate 95% CI)
        sig_threshold = 1.96 / np.sqrt(N_r)

        # How many lags are significant?
        n_significant = 0
        for i in range(1, max_lag + 1):
            if abs(acf[i]) > sig_threshold:
                n_significant += 1
            else:
                break  # First non-significant lag

        results[name] = {
            'acf_at_lags': acf_at_lags,
            'zero_crossing_min': int(zero_cross * 5),
            'n_significant_lags': n_significant,
            'significant_memory_min': int(n_significant * 5),
            'sig_threshold': float(sig_threshold),
        }

        if detail:
            print(f"  {name}: ACF@5m={acf[1]:.3f}, @30m={acf[6]:.3f}, "
                  f"@1h={acf[12]:.3f}, @2h={acf[24]:.3f}, @6h={acf[72]:.3f}, "
                  f"zero={zero_cross * 5}min, sig_lags={n_significant}")

    zero_xs = [r['zero_crossing_min'] for r in results.values()]
    sig_lags = [r['n_significant_lags'] for r in results.values()]
    acf_1h = [r['acf_at_lags']['1h'] for r in results.values()]

    summary = {
        'experiment': 'EXP-570',
        'name': 'Residual Autocorrelation Structure',
        'mean_zero_crossing_min': float(np.mean(zero_xs)) if zero_xs else 0,
        'mean_significant_lags': float(np.mean(sig_lags)) if sig_lags else 0,
        'mean_acf_1h': float(np.mean(acf_1h)) if acf_1h else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-570 Summary: mean zero crossing={np.mean(zero_xs):.0f}min, "
              f"mean sig lags={np.mean(sig_lags):.0f}, mean ACF@1h={np.mean(acf_1h):.3f}")

    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-562-570 autoresearch')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated: 562,563,564,565,568,569,570 or "all"')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps = args.experiments.split(',') if args.experiments != 'all' else \
        ['562', '563', '564', '565', '568', '569', '570']

    all_results = {}

    if '562' in exps:
        print("\n=== EXP-562: Transfer Entropy ===")
        all_results['exp562'] = exp562_transfer_entropy(patients, args.detail)

    if '563' in exps:
        print("\n=== EXP-563: MI Lag Profiles ===")
        all_results['exp563'] = exp563_mi_profiles(patients, args.detail)

    if '564' in exps:
        print("\n=== EXP-564: State-Specific Kalman ===")
        all_results['exp564'] = exp564_state_kalman(patients, args.detail)

    if '565' in exps:
        print("\n=== EXP-565: Ensemble Prediction ===")
        all_results['exp565'] = exp565_ensemble(patients, args.detail)

    if '568' in exps:
        print("\n=== EXP-568: Meal Absorption Variability ===")
        all_results['exp568'] = exp568_meal_variability(patients, args.detail)

    if '569' in exps:
        print("\n=== EXP-569: Stress/Cortisol Proxy ===")
        all_results['exp569'] = exp569_stress_proxy(patients, args.detail)

    if '570' in exps:
        print("\n=== EXP-570: Residual ACF Structure ===")
        all_results['exp570'] = exp570_residual_acf(patients, args.detail)

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, res in all_results.items():
            exp_num = key.replace('exp', '')
            safe_name = res["name"].lower().replace(" ", "_").replace("/", "_")[:30]
            fname = RESULTS_DIR / f'exp{exp_num}_{safe_name}.json'
            with open(fname, 'w') as f:
                json.dump(res, f, indent=2, default=str)
            print(f"  Saved {fname.name}")


if __name__ == '__main__':
    main()
