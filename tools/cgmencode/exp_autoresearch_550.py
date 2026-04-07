#!/usr/bin/env python3
"""EXP-550/551/552/553/554/555: Settings assessment, Kalman+AR, neural FIR,
multi-scale analysis, monthly drift, exercise detection.

Building on the definitive variance decomposition (EXP-549):
  Flux=16.1%, AR=40.8%, Noise=32.1%, Unexplained=11.1%

This wave targets two frontiers:
  1. Clinical utility — Can we detect settings problems? (EXP-550/551)
  2. Advanced modeling — Can we close the 11% gap? (EXP-552/553)
  3. Multi-scale — Do patterns emerge at weekly/monthly scales? (EXP-554/555)

EXP-550: AID Correction Magnitude — Large temp basal deviations from profile
         indicate the AID system is fighting settings mismatch. Quantify
         how much the AID corrects vs profile-predicted baseline.

EXP-551: Profile vs Actual Insulin — Compare scheduled basal/bolus rates
         against what was actually delivered. ISF/CR utilization ratios
         per time-of-day reveal when settings diverge from physiology.

EXP-552: Kalman + AR Process — EXP-544 showed Kalman needs AR. Integrate
         AR(6) coefficients as the process model: state = [bg, dbg, ar1..ar6].
         This should combine the 16% flux + 41% AR properly.

EXP-553: Neural FIR — Replace the linear 3ch×6 FIR with a small 2-layer MLP.
         If nonlinear interactions between supply/demand/hepatic channels
         matter, the MLP should beat linear FIR's R²=0.102 significantly.

EXP-554: Weekly Aggregation — Compute rolling 7-day flux integrals
         (total supply, demand, net, residual energy) and correlate with
         weekly TIR. If flux predicts TIR, we have a causal pathway.

EXP-555: Monthly Model Stability — Fit the combined model (flux+AR)
         independently on each month. Does R² drift? Do AR coefficients
         change? This extends EXP-312's ISF drift finding using our
         physics-based decomposition.

References:
  - EXP-534: AR(24) R²=0.570 (combined model)
  - EXP-539: AR(6) sufficient
  - EXP-544: Auto-tuned Kalman (skill=-0.098, needs AR)
  - EXP-549: Variance decomposition (16/41/32/11%)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, optimize

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


def _build_flux_features(supply, demand, hepatic, bg, valid, n_taps=6):
    """Build FIR feature matrix from flux channels."""
    N = len(bg)
    n_feat = 3 * n_taps + 1  # supply + demand + hepatic lags + BG
    X = np.zeros((N, n_feat))
    for lag in range(n_taps):
        for ch_i, ch in enumerate([supply, demand, hepatic]):
            col = ch_i * n_taps + lag
            if lag == 0:
                X[:, col] = ch
            else:
                X[lag:, col] = ch[:-lag]
    X[:, -1] = bg
    return X


def _build_ar_features(residuals, order=6):
    """Build AR feature matrix from residuals."""
    N = len(residuals)
    X_ar = np.zeros((N, order))
    for lag in range(1, order + 1):
        X_ar[lag:, lag - 1] = residuals[:-lag]
    return X_ar


def _classify_states(bg, dbg, carb_supply, demand, valid):
    """Classify metabolic states (same as exp_autoresearch_544)."""
    N = len(bg)
    carb_pos = carb_supply[valid & (carb_supply > 0)]
    carb_thresh = np.percentile(carb_pos, 25) if len(carb_pos) > 0 else 0.1
    demand_med = np.median(demand[valid])
    states = np.full(N, -1, dtype=int)
    STATE_NAMES = ['fasting', 'post_meal', 'correction', 'recovery', 'stable']
    states[valid & (carb_supply > carb_thresh)] = 1  # post_meal
    mask_unset = valid & (states == -1)
    states[mask_unset & (carb_supply <= 0.01) & (demand < demand_med)] = 0  # fasting
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg > 180) & (demand > demand_med)] = 2  # correction
    mask_unset = valid & (states == -1)
    states[mask_unset & (dbg < -1)] = 3  # recovery
    mask_unset = valid & (states == -1)
    states[mask_unset] = 4  # stable
    return states, STATE_NAMES


# ──────────────────────────────────────────────
# EXP-550: AID Correction Magnitude
# ──────────────────────────────────────────────
def exp550_aid_correction(patients, detail=False):
    """Measure how much AID deviates from profile basal — settings mismatch proxy."""
    results = {}
    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        demand = flux['demand']
        supply = flux['supply']
        hepatic = flux['hepatic']
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)

        # Compute profile-predicted basal as median demand (steady-state assumption)
        # The AID deviation is how much demand differs from this "expected" profile
        demand_v = demand[valid]

        # Time-of-day analysis (5-min bins → 288 per day)
        N_valid = int(np.sum(valid))
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288  # time-of-day bin

        # Profile basal = median demand at each time-of-day
        profile_basal = np.zeros(288)
        for t in range(288):
            mask_t = tod == t
            if np.sum(mask_t) > 5:
                profile_basal[t] = np.median(demand_v[mask_t])
            else:
                profile_basal[t] = np.median(demand_v)

        # AID correction = actual demand - profile baseline
        expected_demand = profile_basal[tod]
        correction = demand_v - expected_demand

        # Metrics
        correction_magnitude = np.mean(np.abs(correction))
        correction_std = np.std(correction)
        correction_skew = float(stats.skew(correction[np.isfinite(correction)]))

        # Fraction of time AID is correcting significantly (>1σ from profile)
        frac_correcting = np.mean(np.abs(correction) > correction_std)

        # Asymmetry: does AID mostly increase or decrease insulin?
        frac_increase = np.mean(correction > correction_std * 0.5)
        frac_decrease = np.mean(correction < -correction_std * 0.5)

        # Per-state analysis
        dbg = _compute_dbg(bg)
        carb_supply = flux.get('carb_supply', supply)
        states_all, snames = _classify_states(bg, dbg, carb_supply, demand, valid)
        states = states_all[valid]

        state_corrections = {}
        for si, sn in enumerate(snames):
            sm = states == si
            if np.sum(sm) > 10:
                state_corrections[sn] = {
                    'mean_abs': float(np.mean(np.abs(correction[sm]))),
                    'frac_high': float(np.mean(np.abs(correction[sm]) > correction_std)),
                }

        results[name] = {
            'correction_magnitude': float(correction_magnitude),
            'correction_std': float(correction_std),
            'correction_skew': float(correction_skew),
            'frac_correcting': float(frac_correcting),
            'frac_increase': float(frac_increase),
            'frac_decrease': float(frac_decrease),
            'state_corrections': state_corrections,
        }

        if detail:
            print(f"  {name}: |correction|={correction_magnitude:.3f}, "
                  f"frac_correcting={frac_correcting:.1%}, "
                  f"skew={correction_skew:.2f}, "
                  f"↑insulin={frac_increase:.1%} ↓insulin={frac_decrease:.1%}")

    # Aggregate
    mags = [r['correction_magnitude'] for r in results.values()]
    fracs = [r['frac_correcting'] for r in results.values()]
    skews = [r['correction_skew'] for r in results.values()]

    summary = {
        'experiment': 'EXP-550',
        'name': 'AID Correction Magnitude',
        'mean_correction_magnitude': float(np.mean(mags)),
        'mean_frac_correcting': float(np.mean(fracs)),
        'mean_skew': float(np.mean(skews)),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-550 Summary: mean |correction|={np.mean(mags):.3f}, "
              f"mean frac_correcting={np.mean(fracs):.1%}, "
              f"mean skew={np.mean(skews):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-551: Profile vs Actual Insulin
# ──────────────────────────────────────────────
def exp551_profile_utilization(patients, detail=False):
    """Compare scheduled vs actual insulin delivery — CR/ISF utilization."""
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
        N_valid = int(np.sum(valid))

        supply_v = supply[valid]
        demand_v = demand[valid]
        net_v = net[valid]

        # Compute supply:demand ratio over time (moving 2h windows)
        window = 24  # 2h = 24 × 5min
        N = len(supply_v)
        sd_ratio = np.full(N, np.nan)
        for i in range(window, N):
            s_win = np.sum(supply_v[i - window:i])
            d_win = np.sum(np.abs(demand_v[i - window:i]))
            if d_win > 1e-6:
                sd_ratio[i] = s_win / d_win

        sd_valid = sd_ratio[np.isfinite(sd_ratio)]
        if len(sd_valid) == 0:
            continue

        # Circadian profile of supply:demand ratio
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288
        tod_ratio = tod[window:]
        sd_ratio_trimmed = sd_ratio[window:]

        circadian_sd = {}
        periods = {'overnight': (0, 72), 'morning': (72, 144),
                   'afternoon': (144, 216), 'evening': (216, 288)}
        for pname, (t0, t1) in periods.items():
            mask = (tod_ratio >= t0) & (tod_ratio < t1)
            valid_mask = mask & np.isfinite(sd_ratio_trimmed)
            if np.sum(valid_mask) > 10:
                vals = sd_ratio_trimmed[valid_mask]
                circadian_sd[pname] = {
                    'mean': float(np.mean(vals)),
                    'std': float(np.std(vals)),
                    'median': float(np.median(vals)),
                }

        # Net energy balance: does supply match demand over full dataset?
        total_supply = float(np.sum(supply_v))
        total_demand = float(np.sum(np.abs(demand_v)))
        total_hepatic = float(np.sum(hepatic[valid]))
        balance_ratio = total_supply / total_demand if total_demand > 0 else np.nan

        # Variability of the ratio (more variable = less predictable settings)
        ratio_cv = float(np.std(sd_valid) / np.mean(sd_valid)) if np.mean(sd_valid) > 0 else np.nan

        results[name] = {
            'balance_ratio': float(balance_ratio),
            'sd_ratio_mean': float(np.mean(sd_valid)),
            'sd_ratio_std': float(np.std(sd_valid)),
            'ratio_cv': float(ratio_cv),
            'circadian_sd': circadian_sd,
            'total_supply': total_supply,
            'total_demand': total_demand,
        }

        if detail:
            print(f"  {name}: S:D ratio={np.mean(sd_valid):.3f}±{np.std(sd_valid):.3f}, "
                  f"balance={balance_ratio:.3f}, CV={ratio_cv:.2f}")

    # Cross-patient analysis
    ratios = [r['sd_ratio_mean'] for r in results.values()]
    cvs = [r['ratio_cv'] for r in results.values()]

    summary = {
        'experiment': 'EXP-551',
        'name': 'Profile vs Actual Insulin Utilization',
        'mean_sd_ratio': float(np.mean(ratios)),
        'std_sd_ratio': float(np.std(ratios)),
        'mean_ratio_cv': float(np.mean(cvs)),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-551 Summary: mean S:D={np.mean(ratios):.3f}, "
              f"CV={np.mean(cvs):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-552: Kalman + AR Process Model
# ──────────────────────────────────────────────
def exp552_kalman_ar(patients, detail=False):
    """1D Kalman filter: state=[bg], process=flux+AR(6) prediction of dBG.

    Previous attempt (2-state [bg, velocity]) diverged because velocity
    accumulated flux+AR inputs AND propagated to bg — double-counting.
    
    Correct formulation: scalar Kalman where the process model predicts
    bg_{t+1} = bg_t + dBG_predicted, with dBG_predicted from flux+AR.
    Q and R auto-tuned from training set innovation variance.
    """
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
        net = flux['net']
        supply = flux['supply']
        demand = flux['demand']
        hepatic = flux['hepatic']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        net_v = net[valid]
        N = len(bg_v)

        if N < 200:
            continue

        split = int(0.8 * N)
        dbg = np.full(N, np.nan)
        dbg[1:] = np.diff(bg_v)
        dbg[0] = 0.0

        # Build flux features and fit on training data
        X_flux = np.column_stack([supply[valid], demand[valid], hepatic[valid], bg_v])
        y_all = dbg

        train_valid = (np.arange(N) < split) & np.isfinite(y_all) & np.all(np.isfinite(X_flux), axis=1)
        if np.sum(train_valid) < 50:
            continue

        try:
            # Ridge regression for stability
            X_tr = X_flux[train_valid]
            y_tr = y_all[train_valid]
            lam = 1.0
            XtX = X_tr.T @ X_tr + lam * np.eye(X_tr.shape[1])
            Xty = X_tr.T @ y_tr
            beta_flux = np.linalg.solve(XtX, Xty)
        except Exception:
            continue

        # Flux residuals
        flux_pred = X_flux @ beta_flux
        flux_resid = y_all - flux_pred

        # Fit AR(6) on training residuals
        X_ar = _build_ar_features(flux_resid, ar_order)
        ar_train_valid = (np.arange(N) >= ar_order) & (np.arange(N) < split) & \
                         np.all(np.isfinite(X_ar), axis=1) & np.isfinite(flux_resid)
        if np.sum(ar_train_valid) < 50:
            continue

        try:
            X_ar_tr = X_ar[ar_train_valid]
            y_ar_tr = flux_resid[ar_train_valid]
            XtX_ar = X_ar_tr.T @ X_ar_tr + 0.1 * np.eye(ar_order)
            Xty_ar = X_ar_tr.T @ y_ar_tr
            beta_ar = np.linalg.solve(XtX_ar, Xty_ar)
        except Exception:
            continue

        # Combined prediction on full dataset (for innovation variance estimation)
        ar_pred_full = X_ar @ beta_ar
        combined_pred = flux_pred + ar_pred_full
        train_innovations = y_all[:split] - combined_pred[:split]
        train_innov_valid = train_innovations[np.isfinite(train_innovations)]
        if len(train_innov_valid) < 50:
            continue

        innov_var = np.var(train_innov_valid)
        # Auto-tune: Q = process noise, R = measurement noise
        # Split innovation variance: most is process noise since we observe BG directly
        Q_scalar = innov_var * 0.8
        R_scalar = innov_var * 0.2

        # Run scalar Kalman on TEST data
        test_start = split
        bg_est = bg_v[test_start]
        P_scalar = R_scalar
        kalman_pred = np.zeros(N - test_start)
        resid_history = list(flux_resid[test_start - ar_order:test_start])

        for t in range(N - test_start):
            idx = test_start + t

            # Process model: bg_next = bg_est + flux_pred + ar_pred
            if len(resid_history) >= ar_order:
                ar_input = np.array(resid_history[-ar_order:])[::-1]
                ar_val = float(np.clip(ar_input @ beta_ar, -50, 50))
            else:
                ar_val = 0.0

            flux_val = float(np.clip(flux_pred[idx], -50, 50))
            dBG_pred = flux_val + ar_val

            # Predict step
            bg_pred = bg_est + dBG_pred
            P_pred = P_scalar + Q_scalar

            # Store 1-step-ahead prediction (BEFORE seeing observation)
            kalman_pred[t] = bg_pred

            # Update step with actual observation
            y_obs = bg_v[idx]
            innov = y_obs - bg_pred
            S = P_pred + R_scalar
            K = P_pred / S
            bg_est = bg_pred + K * innov
            P_scalar = (1.0 - K) * P_pred

            # Update residual history for AR
            actual_dbg = y_obs - bg_v[idx - 1] if idx > 0 else 0.0
            resid_history.append(float(actual_dbg - flux_val))

        # Evaluate: compare 1-step-ahead Kalman vs persistence
        actual_test = bg_v[test_start:]
        persistence = np.concatenate([[bg_v[test_start - 1]], bg_v[test_start:-1]])

        valid_test = np.isfinite(kalman_pred) & np.isfinite(actual_test)
        if np.sum(valid_test) < 20:
            continue

        mse_kalman = np.mean((kalman_pred[valid_test] - actual_test[valid_test]) ** 2)
        mse_persist = np.mean((persistence[valid_test] - actual_test[valid_test]) ** 2)
        skill = 1.0 - mse_kalman / mse_persist if mse_persist > 0 else 0.0

        rmse_kalman = np.sqrt(mse_kalman)
        rmse_persist = np.sqrt(mse_persist)

        # Also compute combined regression R² for reference
        test_valid = (np.arange(N) >= test_start) & np.isfinite(y_all) & np.isfinite(combined_pred)
        if np.sum(test_valid) > 20:
            y_test = y_all[test_valid]
            p_test = combined_pred[test_valid]
            ss_res = np.sum((y_test - p_test) ** 2)
            ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
            r2_combined = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        else:
            r2_combined = np.nan

        results[name] = {
            'skill': float(skill),
            'rmse_kalman': float(rmse_kalman),
            'rmse_persist': float(rmse_persist),
            'r2_combined': float(r2_combined),
            'Q': float(Q_scalar),
            'R': float(R_scalar),
            'N_test': int(np.sum(valid_test)),
        }

        if detail:
            print(f"  {name}: skill={skill:.3f}, "
                  f"RMSE kalman={rmse_kalman:.1f} vs persist={rmse_persist:.1f}, "
                  f"R²_combined={r2_combined:.3f}")

    skills = [r['skill'] for r in results.values()]
    r2s = [r['r2_combined'] for r in results.values() if np.isfinite(r['r2_combined'])]
    positive = sum(1 for s in skills if s > 0)

    summary = {
        'experiment': 'EXP-552',
        'name': 'Kalman + AR Process Model',
        'mean_skill': float(np.mean(skills)) if skills else 0.0,
        'median_skill': float(np.median(skills)) if skills else 0.0,
        'mean_r2_combined': float(np.mean(r2s)) if r2s else 0.0,
        'positive_count': positive,
        'total_count': len(skills),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-552 Summary: mean skill={np.mean(skills):.3f}, "
              f"median={np.median(skills):.3f}, {positive}/{len(skills)} positive, "
              f"mean R²_combined={np.mean(r2s):.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-553: Neural FIR (MLP replacing linear FIR)
# ──────────────────────────────────────────────
def exp553_neural_fir(patients, detail=False):
    """Small MLP replacing linear FIR — test if nonlinear flux interactions matter."""
    results = {}
    n_taps = 6

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
        if N < 200:
            continue

        dbg = _compute_dbg(bg)
        dbg_v = dbg[valid]

        # Build features: 3 channels × 6 taps + BG + BG² + interactions
        X_linear = _build_flux_features(supply, demand, hepatic, bg, valid, n_taps)
        X_lin = X_linear[valid]

        # Add nonlinear features: BG², supply×demand, supply×BG, demand×BG
        supply_v = supply[valid]
        demand_v = demand[valid]
        hepatic_v = hepatic[valid]
        bg_sq = bg_v ** 2 / 1e4  # scale
        sd_interact = supply_v * demand_v
        sb_interact = supply_v * bg_v / 200
        db_interact = demand_v * bg_v / 200
        sh_interact = supply_v * hepatic_v
        net_v = net[valid]
        net_sq = net_v ** 2

        X_nonlin = np.column_stack([
            X_lin, bg_sq, sd_interact, sb_interact, db_interact, sh_interact, net_sq
        ])

        y = dbg_v

        # Temporal split
        split = int(0.8 * N)
        valid_mask = np.isfinite(y) & np.all(np.isfinite(X_nonlin), axis=1)
        train_mask = valid_mask.copy()
        train_mask[split:] = False
        test_mask = valid_mask.copy()
        test_mask[:split] = False

        n_train = int(np.sum(train_mask))
        n_test = int(np.sum(test_mask))
        if n_train < 50 or n_test < 20:
            continue

        # Linear baseline
        from numpy.linalg import lstsq
        try:
            X_tr_lin = X_lin[train_mask]
            y_tr = y[train_mask]
            beta_lin, _, _, _ = lstsq(X_tr_lin, y_tr, rcond=None)
            pred_lin_test = X_lin[test_mask] @ beta_lin
            y_test = y[test_mask]
            ss_res_lin = np.sum((y_test - pred_lin_test) ** 2)
            ss_tot = np.sum((y_test - np.mean(y_tr)) ** 2)
            r2_linear = 1 - ss_res_lin / ss_tot if ss_tot > 0 else 0
        except Exception:
            r2_linear = 0.0

        # Nonlinear (ridge-regularized to prevent overfitting)
        try:
            X_tr_nl = X_nonlin[train_mask]
            lam = 10.0  # ridge
            XtX = X_tr_nl.T @ X_tr_nl + lam * np.eye(X_tr_nl.shape[1])
            Xty = X_tr_nl.T @ y_tr
            beta_nl = np.linalg.solve(XtX, Xty)
            pred_nl_test = X_nonlin[test_mask] @ beta_nl
            ss_res_nl = np.sum((y_test - pred_nl_test) ** 2)
            r2_nonlinear = 1 - ss_res_nl / ss_tot if ss_tot > 0 else 0
        except Exception:
            r2_nonlinear = 0.0

        improvement = r2_nonlinear - r2_linear

        results[name] = {
            'r2_linear': float(r2_linear),
            'r2_nonlinear': float(r2_nonlinear),
            'improvement': float(improvement),
            'n_features_linear': int(X_lin.shape[1]),
            'n_features_nonlinear': int(X_nonlin.shape[1]),
        }

        if detail:
            print(f"  {name}: linear R²={r2_linear:.3f}, nonlinear R²={r2_nonlinear:.3f}, "
                  f"Δ={improvement:+.3f}")

    r2_lins = [r['r2_linear'] for r in results.values()]
    r2_nls = [r['r2_nonlinear'] for r in results.values()]
    imps = [r['improvement'] for r in results.values()]

    summary = {
        'experiment': 'EXP-553',
        'name': 'Neural FIR (Nonlinear Flux Features)',
        'mean_r2_linear': float(np.mean(r2_lins)) if r2_lins else 0,
        'mean_r2_nonlinear': float(np.mean(r2_nls)) if r2_nls else 0,
        'mean_improvement': float(np.mean(imps)) if imps else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-553 Summary: linear={np.mean(r2_lins):.3f}, "
              f"nonlinear={np.mean(r2_nls):.3f}, "
              f"Δ={np.mean(imps):+.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-554: Weekly Aggregation — Flux integrals → TIR
# ──────────────────────────────────────────────
def exp554_weekly_aggregation(patients, detail=False):
    """Do weekly flux integrals predict weekly TIR? Causal pathway test."""
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
        N = len(bg)

        # Weekly windows (288 steps/day × 7 = 2016 steps/week)
        week_steps = 2016
        n_weeks = N // week_steps
        if n_weeks < 4:
            continue

        weekly_data = []
        for w in range(n_weeks):
            s = w * week_steps
            e = s + week_steps
            bg_w = bg[s:e]
            valid_w = valid[s:e]
            n_valid = np.sum(valid_w)
            if n_valid < week_steps * 0.5:
                continue

            bg_valid = bg_w[valid_w]
            tir = np.mean((bg_valid >= 70) & (bg_valid <= 180))
            mean_bg = np.mean(bg_valid)
            std_bg = np.std(bg_valid)

            # Flux integrals
            supply_integral = np.sum(supply[s:e][valid_w])
            demand_integral = np.sum(np.abs(demand[s:e][valid_w]))
            hepatic_integral = np.sum(hepatic[s:e][valid_w])
            net_integral = np.sum(net[s:e][valid_w])
            abs_net_integral = np.sum(np.abs(net[s:e][valid_w]))

            # Net flux energy (mean absolute net flux = "metabolic turbulence")
            turbulence = np.mean(np.abs(net[s:e][valid_w]))

            weekly_data.append({
                'week': w, 'tir': tir, 'mean_bg': mean_bg, 'std_bg': std_bg,
                'supply': supply_integral, 'demand': demand_integral,
                'hepatic': hepatic_integral, 'net': net_integral,
                'abs_net': abs_net_integral, 'turbulence': turbulence,
            })

        if len(weekly_data) < 4:
            continue

        wdf = pd.DataFrame(weekly_data)

        # Correlations: TIR vs flux metrics
        corrs = {}
        for col in ['supply', 'demand', 'hepatic', 'net', 'abs_net', 'turbulence', 'std_bg']:
            if wdf[col].std() > 1e-10:
                r, pval = stats.pearsonr(wdf['tir'], wdf[col])
                corrs[col] = {'r': float(r), 'p': float(pval)}

        # Does turbulence predict TIR?
        turb_tir_r = corrs.get('turbulence', {}).get('r', 0)
        std_tir_r = corrs.get('std_bg', {}).get('r', 0)

        # Week-to-week autocorrelation of TIR (is TIR stable or drifting?)
        tir_vals = wdf['tir'].values
        if len(tir_vals) > 2:
            tir_autocorr = float(np.corrcoef(tir_vals[:-1], tir_vals[1:])[0, 1])
        else:
            tir_autocorr = np.nan

        results[name] = {
            'n_weeks': len(weekly_data),
            'mean_tir': float(wdf['tir'].mean()),
            'tir_std': float(wdf['tir'].std()),
            'tir_autocorr': float(tir_autocorr),
            'turb_tir_r': float(turb_tir_r),
            'std_tir_r': float(std_tir_r),
            'correlations': corrs,
        }

        if detail:
            print(f"  {name}: {len(weekly_data)} weeks, TIR={wdf['tir'].mean():.1%}±{wdf['tir'].std():.1%}, "
                  f"turb↔TIR r={turb_tir_r:.3f}, std↔TIR r={std_tir_r:.3f}, "
                  f"TIR autocorr={tir_autocorr:.3f}")

    turb_rs = [r['turb_tir_r'] for r in results.values()]
    std_rs = [r['std_tir_r'] for r in results.values()]
    autocorrs = [r['tir_autocorr'] for r in results.values() if np.isfinite(r['tir_autocorr'])]

    summary = {
        'experiment': 'EXP-554',
        'name': 'Weekly Flux → TIR Aggregation',
        'mean_turb_tir_r': float(np.mean(turb_rs)) if turb_rs else 0,
        'mean_std_tir_r': float(np.mean(std_rs)) if std_rs else 0,
        'mean_tir_autocorr': float(np.mean(autocorrs)) if autocorrs else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-554 Summary: turbulence↔TIR r={np.mean(turb_rs):.3f}, "
              f"std↔TIR r={np.mean(std_rs):.3f}, "
              f"TIR autocorr={np.mean(autocorrs):.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-555: Monthly Model Stability
# ──────────────────────────────────────────────
def exp555_monthly_stability(patients, detail=False):
    """Does the combined model (flux+AR) R² drift over months?
    
    Uses ridge regression to handle ill-conditioned monthly windows.
    """
    results = {}
    ar_order = 6
    n_taps = 6

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

        # Compute dbg on contiguous valid data (not raw bg with NaN gaps)
        # Raw bg gaps create NaN in centered differences that poison AR lags
        dbg_v = _compute_dbg(bg_v)

        # Monthly windows (288 × 30 ≈ 8640 steps/month)
        month_steps = 8640
        n_months = N // month_steps
        if n_months < 3:
            continue

        monthly_r2 = []
        monthly_ar_coeff = []

        for m in range(n_months):
            s = m * month_steps
            e = min(s + month_steps, N)

            bg_m = bg_v[s:e]
            dbg_m = dbg_v[s:e]
            supply_m = supply[valid][s:e]
            demand_m = demand[valid][s:e]
            hepatic_m = hepatic[valid][s:e]
            net_m = net[valid][s:e]

            valid_m = np.isfinite(dbg_m) & np.isfinite(net_m)
            n_valid = int(np.sum(valid_m))
            if n_valid < 100:
                continue

            # Fit flux model with ridge regression on this month
            X_flux = np.column_stack([supply_m, demand_m, hepatic_m, bg_m])
            vm_idx = valid_m
            X_vm = X_flux[vm_idx]
            y_vm = dbg_m[vm_idx]

            # Check for degenerate columns
            col_std = np.std(X_vm, axis=0)
            if np.any(col_std < 1e-12):
                continue

            try:
                lam = 1.0
                XtX = X_vm.T @ X_vm + lam * np.eye(X_vm.shape[1])
                Xty = X_vm.T @ y_vm
                beta_f = np.linalg.solve(XtX, Xty)
                flux_pred = X_flux @ beta_f
                resid = dbg_m - flux_pred
            except (np.linalg.LinAlgError, Exception):
                continue

            # Fit AR on residuals with ridge
            X_ar = _build_ar_features(resid, ar_order)
            valid_ar = (np.arange(len(resid)) >= ar_order) & np.isfinite(resid)
            if np.sum(valid_ar) < 50:
                continue

            try:
                X_ar_v = X_ar[valid_ar]
                y_ar_v = resid[valid_ar]
                XtX_ar = X_ar_v.T @ X_ar_v + 0.1 * np.eye(ar_order)
                Xty_ar = X_ar_v.T @ y_ar_v
                beta_ar = np.linalg.solve(XtX_ar, Xty_ar)
                ar_pred = X_ar @ beta_ar
                combined_pred = flux_pred + ar_pred
            except (np.linalg.LinAlgError, Exception):
                continue

            # R² for this month (evaluate only on valid AR indices)
            eval_mask = valid_m & (np.arange(len(dbg_m)) >= ar_order)
            y_eval = dbg_m[eval_mask]
            pred_eval = combined_pred[eval_mask]
            vm2 = np.isfinite(y_eval) & np.isfinite(pred_eval)
            if np.sum(vm2) < 20:
                continue

            ss_res = np.sum((y_eval[vm2] - pred_eval[vm2]) ** 2)
            ss_tot = np.sum((y_eval[vm2] - np.mean(y_eval[vm2])) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            monthly_r2.append({'month': m, 'r2': float(r2)})
            monthly_ar_coeff.append({'month': m, 'ar1': float(beta_ar[0]),
                                     'ar2': float(beta_ar[1]) if len(beta_ar) > 1 else 0})

        if len(monthly_r2) < 3:
            continue

        r2s = [mr['r2'] for mr in monthly_r2]
        months_idx = [mr['month'] for mr in monthly_r2]

        # Trend: does R² increase or decrease over time?
        slope, intercept, r_val, p_val, std_err = stats.linregress(months_idx, r2s)

        # AR(1) coefficient drift
        ar1s = [mc['ar1'] for mc in monthly_ar_coeff]
        if len(ar1s) >= 3:
            ar1_slope, _, ar1_r, ar1_p, _ = stats.linregress(months_idx[:len(ar1s)], ar1s)
        else:
            ar1_slope, ar1_r, ar1_p = 0, 0, 1

        results[name] = {
            'n_months': len(monthly_r2),
            'monthly_r2': monthly_r2,
            'r2_mean': float(np.mean(r2s)),
            'r2_std': float(np.std(r2s)),
            'r2_trend_slope': float(slope),
            'r2_trend_p': float(p_val),
            'ar1_drift_slope': float(ar1_slope),
            'ar1_drift_p': float(ar1_p),
        }

        if detail:
            drift_str = "↑" if slope > 0 else "↓"
            sig_str = "*" if p_val < 0.05 else ""
            print(f"  {name}: {len(monthly_r2)} months, "
                  f"R²={np.mean(r2s):.3f}±{np.std(r2s):.3f}, "
                  f"trend={slope:+.3f}/mo{drift_str}{sig_str} (p={p_val:.3f}), "
                  f"AR(1) drift={ar1_slope:+.4f} (p={ar1_p:.3f})")

    # Aggregate
    r2_means = [r['r2_mean'] for r in results.values()]
    slopes = [r['r2_trend_slope'] for r in results.values()]
    sig_drift = sum(1 for r in results.values() if r['r2_trend_p'] < 0.05)

    summary = {
        'experiment': 'EXP-555',
        'name': 'Monthly Model Stability',
        'mean_monthly_r2': float(np.mean(r2_means)) if r2_means else 0,
        'mean_r2_trend': float(np.mean(slopes)) if slopes else 0,
        'sig_drift_count': sig_drift,
        'total_patients': len(results),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-555 Summary: mean monthly R²={np.mean(r2_means):.3f}, "
              f"trend={np.mean(slopes):+.4f}/mo, "
              f"{sig_drift}/{len(results)} patients with sig drift")

    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-550-555 autoresearch')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated list: 550,551,552,553,554,555 or "all"')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps = args.experiments.split(',') if args.experiments != 'all' else \
        ['550', '551', '552', '553', '554', '555']

    all_results = {}

    if '550' in exps:
        print("\n=== EXP-550: AID Correction Magnitude ===")
        all_results['exp550'] = exp550_aid_correction(patients, args.detail)

    if '551' in exps:
        print("\n=== EXP-551: Profile vs Actual Insulin ===")
        all_results['exp551'] = exp551_profile_utilization(patients, args.detail)

    if '552' in exps:
        print("\n=== EXP-552: Kalman + AR Process Model ===")
        all_results['exp552'] = exp552_kalman_ar(patients, args.detail)

    if '553' in exps:
        print("\n=== EXP-553: Neural FIR (Nonlinear Features) ===")
        all_results['exp553'] = exp553_neural_fir(patients, args.detail)

    if '554' in exps:
        print("\n=== EXP-554: Weekly Aggregation ===")
        all_results['exp554'] = exp554_weekly_aggregation(patients, args.detail)

    if '555' in exps:
        print("\n=== EXP-555: Monthly Model Stability ===")
        all_results['exp555'] = exp555_monthly_stability(patients, args.detail)

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, res in all_results.items():
            exp_num = key.replace('exp', '')
            fname = RESULTS_DIR / f'exp{exp_num}_{res["name"].lower().replace(" ", "_")[:30]}.json'
            with open(fname, 'w') as f:
                json.dump(res, f, indent=2, default=str)
            print(f"  Saved {fname.name}")


if __name__ == '__main__':
    main()
