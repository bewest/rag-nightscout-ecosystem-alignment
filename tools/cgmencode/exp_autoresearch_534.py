#!/usr/bin/env python3
"""EXP-534/535/536/537: Advanced transfer functions and generalization.

EXP-534: Residual Autoregression — The residual from our best model
         (state-FIR+BG, R²=0.161) still contains 84% of dBG variance.
         If residuals are autocorrelated, an AR model can capture the
         "momentum" that flux alone misses.

EXP-535: BG-Dependent FIR (Bilinear) — Modulate FIR taps by current BG
         level. Insulin is more effective at high BG (steep dose-response)
         and less effective near target. This is the bilinear extension
         of the FIR model.

EXP-536: Cross-Patient FIR Transfer — Train FIR on N-1 patients, test
         on holdout. If taps generalize, the transfer function is
         universal (physics-based). If not, individual calibration needed.

EXP-537: Phase-Space Embedding — Map trajectories in (BG, dBG/dt,
         supply, demand) space. Look for attractor structure (limit
         cycles around target BG) and bifurcation behavior.

References:
  - exp_combined_531.py: EXP-531 (state FIR+BG R²=0.161)
  - exp_fir_528.py: EXP-528 (3ch FIR R²=0.102)
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


def _classify_states(bg, dbg, carb_supply, demand, valid):
    """Classify each timestep into metabolic state."""
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
    states[mask_unset & (bg > 140) & (dbg < -1)] = 3
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg >= 70) & (bg <= 180)] = 4

    return states, STATE_NAMES


def _build_fir_features(channels, valid, states, bg, dbg, L=6):
    """Build FIR feature matrix. Returns X, y, state_arr, bg_arr, indices."""
    N = len(bg)
    start = L - 1
    all_X, all_y, all_s, all_bg, all_idx = [], [], [], [], []

    for t in range(start, N):
        if not valid[t] or states[t] < 0:
            continue
        row = []
        ok = True
        for ch in channels:
            taps = ch[t - L + 1:t + 1][::-1]
            if len(taps) != L or not np.all(np.isfinite(taps)):
                ok = False
                break
            row.extend(taps)
        if ok and np.isfinite(dbg[t]):
            all_X.append(row)
            all_y.append(dbg[t])
            all_s.append(states[t])
            all_bg.append(bg[t])
            all_idx.append(t)

    if len(all_X) < 100:
        return None, None, None, None, None
    return (np.array(all_X), np.array(all_y), np.array(all_s),
            np.array(all_bg), np.array(all_idx))


def _fit_state_fir_bg(X, y, s_arr, bg_arr, state_names):
    """Fit state-specific FIR+BG model. Returns predictions."""
    pred = np.full(len(y), np.nan)
    for s_idx in range(len(state_names)):
        mask = s_arr == s_idx
        n_s = mask.sum()
        if n_s < 50:
            pred[mask] = np.mean(y[mask]) if n_s > 0 else 0
            continue
        X_s = np.column_stack([X[mask], bg_arr[mask], np.ones(n_s)])
        y_s = y[mask]
        try:
            c = np.linalg.lstsq(X_s, y_s, rcond=None)[0]
            pred[mask] = X_s @ c
        except Exception:
            pred[mask] = np.mean(y_s)
    return pred


# ── EXP-534: Residual Autoregression ────────────────────────────────────

def run_exp534(patients, detail=False):
    """AR model on residuals from state-FIR+BG model.

    If residuals have temporal structure (autocorrelation), an AR(p)
    model captures the "momentum" component missing from flux modeling.
    """
    L_fir = 6
    ar_orders = [3, 6, 12, 24]  # 15min to 2hrs
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        channels = [sd['supply'], sd['demand'], sd['hepatic']]
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg)
        for ch in channels:
            valid = valid & np.isfinite(ch)

        states, STATE_NAMES = _classify_states(
            bg, dbg, sd['carb_supply'], sd['demand'], valid)

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            channels, valid, states, bg, dbg, L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        y_var = np.var(y)
        if y_var < 1e-6:
            results[name] = {'error': 'zero variance'}
            continue

        # Get residuals from state-FIR+BG
        pred_base = _fit_state_fir_bg(X, y, s_arr, bg_arr, STATE_NAMES)
        resid = y - pred_base

        # Measure autocorrelation of residuals
        resid_valid = resid[np.isfinite(resid)]
        if len(resid_valid) < 100:
            results[name] = {'error': 'insufficient residuals'}
            continue

        # Autocorrelation at various lags
        autocorr = {}
        for lag in [1, 3, 6, 12, 24]:
            if lag < len(resid_valid):
                r = np.corrcoef(resid_valid[:-lag], resid_valid[lag:])[0, 1]
                autocorr[f'lag_{lag*5}min'] = round(float(r), 4)

        # Fit AR(p) models on residuals
        r2_base = 1.0 - np.var(resid[np.isfinite(resid)]) / y_var
        ar_results = {}

        for order in ar_orders:
            # Build AR feature matrix
            ar_X, ar_y = [], []
            for t in range(order, len(resid)):
                if not np.isfinite(resid[t]):
                    continue
                history = resid[t - order:t][::-1]
                if np.all(np.isfinite(history)):
                    ar_X.append(history)
                    ar_y.append(resid[t])

            if len(ar_X) < 500:
                ar_results[f'AR({order})'] = {'error': 'insufficient'}
                continue

            ar_X = np.array(ar_X)
            ar_y = np.array(ar_y)

            # Add bias
            ar_Xb = np.column_stack([ar_X, np.ones(len(ar_X))])
            try:
                c = np.linalg.lstsq(ar_Xb, ar_y, rcond=None)[0]
                ar_pred = ar_Xb @ c
                # How much of ORIGINAL y variance does AR explain?
                # Total model: base_pred + ar_pred
                # We need to evaluate on the subset where AR is valid
                ar_resid_var = np.var(ar_y - ar_pred)
                ar_r2_of_residual = 1.0 - ar_resid_var / np.var(ar_y)

                # Combined R² relative to original y
                # R²_combined ≈ R²_base + (1 - R²_base) × R²_AR
                r2_combined = r2_base + (1.0 - r2_base) * ar_r2_of_residual

                ar_results[f'AR({order})'] = {
                    'n': len(ar_y),
                    'r2_of_residual': round(float(ar_r2_of_residual), 4),
                    'r2_combined': round(float(r2_combined), 4),
                    'improvement': round(float(r2_combined - r2_base), 4),
                }
            except Exception:
                ar_results[f'AR({order})'] = {'error': 'fit failed'}

        results[name] = {
            'r2_base_model': round(float(r2_base), 4),
            'autocorrelation': autocorr,
            'ar_models': ar_results,
        }

        if detail:
            best_ar = max(
                [(k, v.get('r2_combined', 0)) for k, v in ar_results.items()
                 if isinstance(v.get('r2_combined'), (int, float))],
                key=lambda x: x[1], default=('none', 0))
            print(f"  {name}: base R²={r2_base:.3f}, "
                  f"AR autocorr@5min={autocorr.get('lag_5min', '?')}, "
                  f"best AR={best_ar[0]} → R²={best_ar[1]:.3f}")

    # Summary
    base_vals = [v['r2_base_model'] for v in results.values()
                 if 'r2_base_model' in v]
    # Best AR improvement per patient
    improvements = []
    for v in results.values():
        if 'ar_models' not in v:
            continue
        best_imp = max(
            [ar.get('improvement', 0) for ar in v['ar_models'].values()
             if isinstance(ar.get('improvement'), (int, float))],
            default=0)
        improvements.append(best_imp)

    summary = {
        'mean_base_r2': round(float(np.mean(base_vals)), 4) if base_vals else None,
        'mean_ar_improvement': round(float(np.mean(improvements)), 4) if improvements else None,
        'mean_combined_r2': round(float(np.mean(base_vals) + np.mean(improvements)), 4) if base_vals and improvements else None,
    }

    return {'exp': 'EXP-534', 'title': 'Residual Autoregression',
            'summary': summary, 'patients': results}


# ── EXP-535: BG-Dependent FIR (Bilinear Model) ──────────────────────────

def run_exp535(patients, detail=False):
    """Bilinear FIR: taps modulated by current BG level.

    Model: dBG/dt = sum_k h_k * flux[t-k] + sum_k g_k * flux[t-k] * bg_norm[t]
    This captures BG-dependent insulin sensitivity: at high BG, insulin
    is more effective (steeper dose-response curve).
    """
    L = 6
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        channels = [sd['supply'], sd['demand'], sd['hepatic']]
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg)
        for ch in channels:
            valid = valid & np.isfinite(ch)

        states, STATE_NAMES = _classify_states(
            bg, dbg, sd['carb_supply'], sd['demand'], valid)

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            channels, valid, states, bg, dbg, L)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        y_var = np.var(y)
        if y_var < 1e-6:
            results[name] = {'error': 'zero variance'}
            continue

        # Normalize BG for interaction
        bg_norm = (bg_arr - np.nanmean(bg_arr)) / max(np.nanstd(bg_arr), 1.0)

        # Model 1: Linear FIR (baseline)
        X_lin = np.column_stack([X, np.ones(len(X))])
        c_lin = np.linalg.lstsq(X_lin, y, rcond=None)[0]
        r2_linear = 1.0 - np.var(y - X_lin @ c_lin) / y_var

        # Model 2: FIR + BG feature (additive)
        X_add = np.column_stack([X, bg_norm, np.ones(len(X))])
        c_add = np.linalg.lstsq(X_add, y, rcond=None)[0]
        r2_additive = 1.0 - np.var(y - X_add @ c_add) / y_var

        # Model 3: Bilinear FIR — flux × bg interaction terms
        X_interaction = X * bg_norm[:, None]  # element-wise modulation
        X_bilinear = np.column_stack([X, X_interaction, bg_norm, np.ones(len(X))])
        c_bi = np.linalg.lstsq(X_bilinear, y, rcond=None)[0]
        r2_bilinear = 1.0 - np.var(y - X_bilinear @ c_bi) / y_var

        # Model 4: State-specific bilinear
        pred_state_bi = np.full(len(y), np.nan)
        state_results = {}

        for s_idx, s_name in enumerate(STATE_NAMES):
            mask = s_arr == s_idx
            n_s = mask.sum()
            if n_s < 100:
                pred_state_bi[mask] = np.mean(y[mask]) if n_s > 0 else 0
                state_results[s_name] = {'n': int(n_s), 'error': 'too few'}
                continue

            X_s = X[mask]
            bg_s = bg_norm[mask]
            X_s_inter = X_s * bg_s[:, None]
            X_s_full = np.column_stack([X_s, X_s_inter, bg_s, np.ones(n_s)])
            y_s = y[mask]

            try:
                c_s = np.linalg.lstsq(X_s_full, y_s, rcond=None)[0]
                pred_state_bi[mask] = X_s_full @ c_s
                r2_s = 1.0 - np.var(y_s - X_s_full @ c_s) / np.var(y_s)
                state_results[s_name] = {'n': int(n_s), 'r2': round(float(r2_s), 4)}
            except Exception:
                pred_state_bi[mask] = np.mean(y_s)
                state_results[s_name] = {'n': int(n_s), 'error': 'fit failed'}

        has_pred = np.isfinite(pred_state_bi)
        r2_state_bilinear = (1.0 - np.var(y[has_pred] - pred_state_bi[has_pred])
                             / np.var(y[has_pred])) if has_pred.sum() > 1000 else None

        results[name] = {
            'r2_linear_fir': round(float(r2_linear), 4),
            'r2_additive_bg': round(float(r2_additive), 4),
            'r2_bilinear': round(float(r2_bilinear), 4),
            'r2_state_bilinear': round(float(r2_state_bilinear), 4) if r2_state_bilinear else None,
            'n_params': {'linear': X_lin.shape[1], 'bilinear': X_bilinear.shape[1],
                         'state_bilinear': f'~{X_bilinear.shape[1]} × 5 states'},
            'state_detail': state_results,
        }

        if detail:
            print(f"  {name}: linear={r2_linear:.3f}, +bg={r2_additive:.3f}, "
                  f"bilinear={r2_bilinear:.3f}, state_bi={r2_state_bilinear:.3f}" if r2_state_bilinear else
                  f"  {name}: linear={r2_linear:.3f}, +bg={r2_additive:.3f}, bilinear={r2_bilinear:.3f}")

    # Summary
    keys = ['r2_linear_fir', 'r2_additive_bg', 'r2_bilinear', 'r2_state_bilinear']
    summary = {}
    for k in keys:
        vals = [v[k] for v in results.values() if isinstance(v.get(k), (int, float))]
        summary[f'mean_{k}'] = round(float(np.mean(vals)), 4) if vals else None

    return {'exp': 'EXP-535', 'title': 'BG-Dependent FIR (Bilinear)',
            'summary': summary, 'patients': results}


# ── EXP-536: Cross-Patient FIR Transfer ─────────────────────────────────

def run_exp536(patients, detail=False):
    """Leave-one-out FIR: train on N-1, test on holdout.

    Tests whether the FIR transfer function is universal (rooted in
    shared physics of insulin/glucose dynamics) or patient-specific.
    """
    L = 6
    # First, collect all data per patient
    patient_data = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        channels = [sd['supply'], sd['demand'], sd['hepatic']]
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg)
        for ch in channels:
            valid = valid & np.isfinite(ch)

        states, STATE_NAMES = _classify_states(
            bg, dbg, sd['carb_supply'], sd['demand'], valid)

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            channels, valid, states, bg, dbg, L)
        if X is not None and len(X) > 500:
            patient_data[name] = {
                'X': X, 'y': y, 's': s_arr, 'bg': bg_arr, 'idx': idx
            }

    if len(patient_data) < 3:
        return {'exp': 'EXP-536', 'title': 'Cross-Patient FIR Transfer',
                'error': 'insufficient patients'}

    results = {}
    names = list(patient_data.keys())

    for holdout_name in names:
        holdout = patient_data[holdout_name]

        # Train on all others
        train_X = np.vstack([patient_data[n]['X'] for n in names if n != holdout_name])
        train_y = np.concatenate([patient_data[n]['y'] for n in names if n != holdout_name])

        # Global FIR on training set
        X_train_b = np.column_stack([train_X, np.ones(len(train_X))])
        try:
            c_global = np.linalg.lstsq(X_train_b, train_y, rcond=None)[0]
        except Exception:
            results[holdout_name] = {'error': 'training failed'}
            continue

        # Test on holdout
        X_test = holdout['X']
        y_test = holdout['y']
        y_var = np.var(y_test)

        if y_var < 1e-6:
            results[holdout_name] = {'error': 'zero variance'}
            continue

        X_test_b = np.column_stack([X_test, np.ones(len(X_test))])
        pred_transfer = X_test_b @ c_global
        r2_transfer = 1.0 - np.var(y_test - pred_transfer) / y_var

        # Compare with holdout's own FIR
        c_own = np.linalg.lstsq(X_test_b, y_test, rcond=None)[0]
        pred_own = X_test_b @ c_own
        r2_own = 1.0 - np.var(y_test - pred_own) / y_var

        # Also: train on all (including holdout) — "population" model
        all_X = np.vstack([pd['X'] for pd in patient_data.values()])
        all_y = np.concatenate([pd['y'] for pd in patient_data.values()])
        X_all_b = np.column_stack([all_X, np.ones(len(all_X))])
        c_pop = np.linalg.lstsq(X_all_b, all_y, rcond=None)[0]
        pred_pop = X_test_b @ c_pop
        r2_pop = 1.0 - np.var(y_test - pred_pop) / y_var

        transfer_ratio = r2_transfer / r2_own if r2_own > 0.001 else None

        results[holdout_name] = {
            'r2_own': round(float(r2_own), 4),
            'r2_transfer': round(float(r2_transfer), 4),
            'r2_population': round(float(r2_pop), 4),
            'transfer_ratio': round(float(transfer_ratio), 3) if transfer_ratio else None,
            'n_train': len(train_y),
            'n_test': len(y_test),
        }

        if detail:
            print(f"  {holdout_name}: own={r2_own:.3f}, transfer={r2_transfer:.3f}, "
                  f"ratio={transfer_ratio:.2f}" if transfer_ratio else
                  f"  {holdout_name}: own={r2_own:.3f}, transfer={r2_transfer:.3f}")

    # Summary
    own_vals = [v['r2_own'] for v in results.values() if 'r2_own' in v]
    xfer_vals = [v['r2_transfer'] for v in results.values() if 'r2_transfer' in v]
    ratios = [v['transfer_ratio'] for v in results.values()
              if isinstance(v.get('transfer_ratio'), (int, float))]

    summary = {
        'mean_r2_own': round(float(np.mean(own_vals)), 4) if own_vals else None,
        'mean_r2_transfer': round(float(np.mean(xfer_vals)), 4) if xfer_vals else None,
        'mean_transfer_ratio': round(float(np.mean(ratios)), 3) if ratios else None,
        'n_patients': len(results),
        'interpretation': ('Transfer ratio >0.8 = universal physics, '
                          '<0.5 = patient-specific dynamics'),
    }

    return {'exp': 'EXP-536', 'title': 'Cross-Patient FIR Transfer',
            'summary': summary, 'patients': results}


# ── EXP-537: Phase-Space Embedding ──────────────────────────────────────

def run_exp537(patients, detail=False):
    """Map trajectories in (BG, dBG/dt, supply, demand) phase space.

    Look for attractor structure (limit cycles, fixed points) and
    measure trajectory properties per metabolic state.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        supply = sd['supply']
        demand = sd['demand']

        valid = (np.isfinite(bg) & np.isfinite(dbg) &
                 np.isfinite(supply) & np.isfinite(demand))

        if valid.sum() < 1000:
            results[name] = {'error': 'insufficient data'}
            continue

        # Build 4D phase space: (bg, dbg, supply, demand)
        bg_v = bg[valid]
        dbg_v = dbg[valid]
        sup_v = supply[valid]
        dem_v = demand[valid]

        # Normalize each axis to z-scores
        bg_z = (bg_v - np.mean(bg_v)) / max(np.std(bg_v), 1)
        dbg_z = (dbg_v - np.mean(dbg_v)) / max(np.std(dbg_v), 0.1)
        sup_z = (sup_v - np.mean(sup_v)) / max(np.std(sup_v), 0.01)
        dem_z = (dem_v - np.mean(dem_v)) / max(np.std(dem_v), 0.01)

        phase = np.column_stack([bg_z, dbg_z, sup_z, dem_z])

        # 1. Recurrence analysis: how often does trajectory return near a point?
        # Sample 1000 reference points, compute return statistics
        n_pts = len(phase)
        n_sample = min(1000, n_pts)
        rng = np.random.RandomState(42)
        sample_idx = rng.choice(n_pts, n_sample, replace=False)

        # Euclidean distance to 100 nearest temporal neighbors (not sequential)
        distances = []
        for i in sample_idx[:200]:  # keep it fast
            # Exclude temporal neighbors (within 12 steps = 1hr)
            far_mask = np.abs(np.arange(n_pts) - i) > 12
            if far_mask.sum() < 100:
                continue
            d = np.sqrt(np.sum((phase[far_mask] - phase[i]) ** 2, axis=1))
            distances.append(np.percentile(d, [5, 25, 50]))

        if not distances:
            results[name] = {'error': 'recurrence failed'}
            continue

        dist_stats = np.array(distances)

        # 2. Trajectory curvature (how smooth is the path?)
        velocity = np.diff(phase, axis=0)
        speed = np.sqrt(np.sum(velocity ** 2, axis=1))
        accel = np.diff(velocity, axis=0)
        accel_mag = np.sqrt(np.sum(accel ** 2, axis=1))
        curvature = accel_mag / (speed[1:] ** 2 + 1e-6)

        # 3. Lyapunov-like divergence: how fast do nearby trajectories separate?
        # Simple estimate: for close pairs, measure separation after 12 steps
        divergence_rates = []
        for i in sample_idx[:200]:
            d0 = np.sqrt(np.sum((phase - phase[i]) ** 2, axis=1))
            # Find points within 0.5 std that are >2hr away temporally
            close = (d0 < 0.5) & (np.abs(np.arange(n_pts) - i) > 24)
            close_idx = np.where(close)[0]
            if len(close_idx) < 5:
                continue

            for j in close_idx[:10]:
                # Measure separation 1hr later
                t_future = 12
                if i + t_future < n_pts and j + t_future < n_pts:
                    d_future = np.sqrt(np.sum(
                        (phase[i + t_future] - phase[j + t_future]) ** 2))
                    d_init = d0[j]
                    if d_init > 1e-6:
                        divergence_rates.append(d_future / d_init)

        results[name] = {
            'n_points': int(n_pts),
            'recurrence': {
                'p5_distance': round(float(np.mean(dist_stats[:, 0])), 3),
                'p25_distance': round(float(np.mean(dist_stats[:, 1])), 3),
                'median_distance': round(float(np.mean(dist_stats[:, 2])), 3),
            },
            'trajectory': {
                'mean_speed': round(float(np.nanmean(speed)), 4),
                'mean_curvature': round(float(np.nanmedian(curvature[np.isfinite(curvature)])), 4)
                    if np.any(np.isfinite(curvature)) else None,
                'speed_cv': round(float(np.nanstd(speed) / max(np.nanmean(speed), 1e-6)), 3),
            },
            'divergence': {
                'mean_ratio': round(float(np.mean(divergence_rates)), 3) if divergence_rates else None,
                'median_ratio': round(float(np.median(divergence_rates)), 3) if divergence_rates else None,
                'n_pairs': len(divergence_rates),
                'chaotic_threshold': 'ratio > 2.0 suggests deterministic chaos',
            }
        }

        if detail:
            div = results[name]['divergence']
            rec = results[name]['recurrence']
            print(f"  {name}: recurrence p5={rec['p5_distance']:.2f}, "
                  f"divergence={div['mean_ratio']:.2f}" if div['mean_ratio'] else
                  f"  {name}: recurrence p5={rec['p5_distance']:.2f}, no divergence data")

    # Summary
    rec_p5 = [v['recurrence']['p5_distance'] for v in results.values() if 'recurrence' in v]
    div_means = [v['divergence']['mean_ratio'] for v in results.values()
                 if v.get('divergence', {}).get('mean_ratio') is not None]
    speeds = [v['trajectory']['mean_speed'] for v in results.values() if 'trajectory' in v]

    summary = {
        'mean_recurrence_p5': round(float(np.mean(rec_p5)), 3) if rec_p5 else None,
        'mean_divergence': round(float(np.mean(div_means)), 3) if div_means else None,
        'mean_speed': round(float(np.mean(speeds)), 4) if speeds else None,
        'interpretation': {
            'recurrence_p5 < 1.0': 'Strong attractor — system revisits similar states',
            'divergence > 2.0': 'Chaotic regime — small differences amplify',
            'divergence ≈ 1.0': 'Neutral — neither converging nor diverging',
        },
    }

    return {'exp': 'EXP-537', 'title': 'Phase-Space Embedding',
            'summary': summary, 'patients': results}


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-534/535/536/537')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', nargs='*', default=['534', '535', '536', '537'])
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    all_results = {}

    if '534' in args.experiments:
        print("\n── EXP-534: Residual Autoregression ──")
        r534 = run_exp534(patients, detail=args.detail)
        all_results['exp534'] = r534
        s = r534['summary']
        print(f"  Base R²={s['mean_base_r2']}, "
              f"AR improvement={s['mean_ar_improvement']}, "
              f"combined={s['mean_combined_r2']}")

    if '535' in args.experiments:
        print("\n── EXP-535: BG-Dependent FIR (Bilinear) ──")
        r535 = run_exp535(patients, detail=args.detail)
        all_results['exp535'] = r535
        s = r535['summary']
        print(f"  Linear={s['mean_r2_linear_fir']}, "
              f"Additive BG={s['mean_r2_additive_bg']}, "
              f"Bilinear={s['mean_r2_bilinear']}, "
              f"State bilinear={s['mean_r2_state_bilinear']}")

    if '536' in args.experiments:
        print("\n── EXP-536: Cross-Patient FIR Transfer ──")
        r536 = run_exp536(patients, detail=args.detail)
        all_results['exp536'] = r536
        s = r536['summary']
        print(f"  Own R²={s['mean_r2_own']}, "
              f"Transfer R²={s['mean_r2_transfer']}, "
              f"Ratio={s['mean_transfer_ratio']}")

    if '537' in args.experiments:
        print("\n── EXP-537: Phase-Space Embedding ──")
        r537 = run_exp537(patients, detail=args.detail)
        all_results['exp537'] = r537
        s = r537['summary']
        print(f"  Recurrence p5={s['mean_recurrence_p5']}, "
              f"Divergence={s['mean_divergence']}, "
              f"Speed={s['mean_speed']}")

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, result in all_results.items():
            path = RESULTS_DIR / f'{key.replace("exp", "exp")}_result.json'
            # Use standard naming
            fname = {
                'exp534': 'exp534_residual_ar.json',
                'exp535': 'exp535_bilinear_fir.json',
                'exp536': 'exp536_cross_patient.json',
                'exp537': 'exp537_phase_space.json',
            }.get(key, f'{key}.json')
            path = RESULTS_DIR / fname
            with open(path, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved {path}")

    print("\n── Done ──")


if __name__ == '__main__':
    main()
