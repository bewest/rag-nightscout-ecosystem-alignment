#!/usr/bin/env python3
"""EXP-538/539/540/541/542/543: AR refinement, temporal validation, Kalman.

Now that AR(24)+flux reaches R²=0.570 (near the noise ceiling), we need:

EXP-538: Temporal Cross-Validation — Are we overfitting? Train on first
         60% of each patient's data, test on last 40%. This is the gold
         standard for time-series validation.

EXP-539: AR Order Selection — Find minimal AR order via AIC/BIC.
         AR(24) = 120 min of history. Is AR(12)=60min sufficient?
         Parsimony matters for production systems.

EXP-540: State-AR Interaction — Different AR dynamics per metabolic state.
         Fasting may need fewer AR terms (smoother dynamics) while
         meal states may need more (complex absorption kinetics).

EXP-541: Kalman Filter — Sequential state estimation with flux as control
         input and AR as process model. This is the "proper" way to
         combine physics (flux) with statistical prediction (AR).

EXP-542: Prediction Horizon — How far ahead can we predict? Evaluate
         at 15, 30, 60, 90, 120 min horizons. The chaos finding
         (divergence=5.2) predicts rapid degradation beyond 1hr.

EXP-543: Device Age Effect — Does sensor age (day 1-10) affect model
         performance? Sensor accuracy degrades over wear time.

References:
  - exp_autoresearch_534.py: EXP-534 (AR(24) R²=0.570)
  - exp_combined_531.py: EXP-531 (state-FIR+BG R²=0.161)
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


def _prepare_patient(p):
    """Common patient data preparation. Returns dict or None."""
    df = p['df']
    pk = p.get('pk')
    sd = compute_supply_demand(df, pk)
    channels = [sd['supply'], sd['demand'], sd['hepatic']]
    bg = _get_bg(df)
    dbg = _compute_dbg(bg)

    valid = np.isfinite(bg) & np.isfinite(dbg)
    for ch in channels:
        valid = valid & np.isfinite(ch)

    states, STATE_NAMES = _classify_states(
        bg, dbg, sd['carb_supply'], sd['demand'], valid)

    return {
        'sd': sd, 'channels': channels, 'bg': bg, 'dbg': dbg,
        'valid': valid, 'states': states, 'STATE_NAMES': STATE_NAMES,
    }


# ── EXP-538: Temporal Cross-Validation ──────────────────────────────────

def run_exp538(patients, detail=False):
    """Train on first 60% of data, test on last 40%. No temporal leakage.

    Tests: (1) state-FIR+BG alone, (2) + AR(24), (3) + AR(12)
    """
    L_fir = 6
    results = {}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            prep['channels'], prep['valid'], prep['states'],
            prep['bg'], prep['dbg'], L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        n = len(y)
        split = int(n * 0.6)
        if split < 500 or (n - split) < 200:
            results[name] = {'error': 'insufficient split'}
            continue

        STATE_NAMES = prep['STATE_NAMES']

        # --- Model 1: State-FIR+BG (deterministic) ---
        # Train
        pred_train = np.full(split, np.nan)
        coeffs = {}
        for s_idx, s_name in enumerate(STATE_NAMES):
            tr_mask = s_arr[:split] == s_idx
            n_s = tr_mask.sum()
            if n_s < 50:
                pred_train[tr_mask] = np.mean(y[:split][tr_mask]) if n_s > 0 else 0
                coeffs[s_idx] = None
                continue
            X_s = np.column_stack([X[:split][tr_mask], bg_arr[:split][tr_mask], np.ones(n_s)])
            y_s = y[:split][tr_mask]
            try:
                c = np.linalg.lstsq(X_s, y_s, rcond=None)[0]
                pred_train[tr_mask] = X_s @ c
                coeffs[s_idx] = c
            except Exception:
                pred_train[tr_mask] = np.mean(y_s)
                coeffs[s_idx] = None

        # Test
        pred_test = np.full(n - split, np.nan)
        for s_idx, s_name in enumerate(STATE_NAMES):
            te_mask = s_arr[split:] == s_idx
            n_s = te_mask.sum()
            if n_s == 0:
                continue
            if coeffs[s_idx] is None:
                pred_test[te_mask] = np.mean(y[:split])
                continue
            X_s = np.column_stack([X[split:][te_mask], bg_arr[split:][te_mask], np.ones(n_s)])
            pred_test[te_mask] = X_s @ coeffs[s_idx]

        y_test = y[split:]
        y_var_test = np.var(y_test)
        has_pred = np.isfinite(pred_test)
        r2_det_train = 1.0 - np.var(y[:split] - pred_train) / np.var(y[:split])
        r2_det_test = (1.0 - np.var(y_test[has_pred] - pred_test[has_pred]) / y_var_test
                       if has_pred.sum() > 100 and y_var_test > 1e-6 else None)

        # --- Model 2: + AR(12) on residuals ---
        resid_train = y[:split] - pred_train
        resid_all = np.full(n, np.nan)
        resid_all[:split] = resid_train
        # For test, use deterministic prediction to get residuals
        resid_all[split:] = y_test - pred_test

        ar_results = {}
        for ar_order in [6, 12, 24]:
            # Build AR features from training residuals
            ar_X_tr, ar_y_tr = [], []
            for t in range(ar_order, split):
                if not np.isfinite(resid_all[t]):
                    continue
                hist = resid_all[t - ar_order:t][::-1]
                if np.all(np.isfinite(hist)):
                    ar_X_tr.append(hist)
                    ar_y_tr.append(resid_all[t])

            if len(ar_X_tr) < 200:
                ar_results[f'AR({ar_order})'] = {'error': 'insufficient'}
                continue

            ar_X_tr = np.array(ar_X_tr)
            ar_y_tr = np.array(ar_y_tr)
            ar_X_trb = np.column_stack([ar_X_tr, np.ones(len(ar_X_tr))])

            try:
                ar_c = np.linalg.lstsq(ar_X_trb, ar_y_tr, rcond=None)[0]
            except Exception:
                ar_results[f'AR({ar_order})'] = {'error': 'fit failed'}
                continue

            # Test AR on holdout
            # Use TRUE residuals for AR prediction (causal: only past residuals)
            # Simulate forward: at each test step, use actual past residuals
            ar_pred_test = np.full(n - split, np.nan)
            for t_rel in range(n - split):
                t_abs = split + t_rel
                if t_abs < ar_order:
                    continue
                hist = resid_all[t_abs - ar_order:t_abs][::-1]
                if np.all(np.isfinite(hist)):
                    ar_pred_test[t_rel] = np.append(hist, 1.0) @ ar_c

            # Combined test prediction
            comb_test = pred_test.copy()
            ar_valid = np.isfinite(ar_pred_test) & has_pred
            comb_test[ar_valid] = pred_test[ar_valid] + ar_pred_test[ar_valid]

            comb_valid = np.isfinite(comb_test)
            if comb_valid.sum() > 100 and y_var_test > 1e-6:
                r2_comb = 1.0 - np.var(y_test[comb_valid] - comb_test[comb_valid]) / y_var_test
            else:
                r2_comb = None

            ar_results[f'AR({ar_order})'] = {
                'r2_test': round(float(r2_comb), 4) if r2_comb is not None else None,
                'n_ar_valid': int(ar_valid.sum()),
            }

        results[name] = {
            'n_train': split,
            'n_test': n - split,
            'r2_det_train': round(float(r2_det_train), 4),
            'r2_det_test': round(float(r2_det_test), 4) if r2_det_test is not None else None,
            'overfit_gap': round(float(r2_det_train - (r2_det_test or 0)), 4),
            'ar_test': ar_results,
        }

        if detail:
            best_ar = max(
                [(k, v.get('r2_test', 0) or 0) for k, v in ar_results.items()],
                key=lambda x: x[1], default=('none', 0))
            print(f"  {name}: det train={r2_det_train:.3f}, test={r2_det_test:.3f}, "
                  f"overfit={r2_det_train - (r2_det_test or 0):.3f}, "
                  f"best AR test={best_ar[0]}→{best_ar[1]:.3f}")

    # Summary
    det_train = [v['r2_det_train'] for v in results.values() if 'r2_det_train' in v]
    det_test = [v['r2_det_test'] for v in results.values()
                if isinstance(v.get('r2_det_test'), (int, float))]
    gaps = [v['overfit_gap'] for v in results.values() if 'overfit_gap' in v]

    # Best AR per patient
    ar_test_vals = []
    for v in results.values():
        if 'ar_test' not in v:
            continue
        best = max([ar.get('r2_test', 0) or 0 for ar in v['ar_test'].values()], default=0)
        ar_test_vals.append(best)

    summary = {
        'mean_det_train': round(float(np.mean(det_train)), 4) if det_train else None,
        'mean_det_test': round(float(np.mean(det_test)), 4) if det_test else None,
        'mean_overfit_gap': round(float(np.mean(gaps)), 4) if gaps else None,
        'mean_ar_test': round(float(np.mean(ar_test_vals)), 4) if ar_test_vals else None,
    }

    return {'exp': 'EXP-538', 'title': 'Temporal Cross-Validation',
            'summary': summary, 'patients': results}


# ── EXP-539: AR Order Selection ─────────────────────────────────────────

def run_exp539(patients, detail=False):
    """Find minimal AR order via AIC/BIC and out-of-sample performance."""
    L_fir = 6
    ar_orders = list(range(1, 37))  # AR(1) to AR(36) = 5min to 3hrs
    results = {}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            prep['channels'], prep['valid'], prep['states'],
            prep['bg'], prep['dbg'], L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        # Get residuals from state-FIR+BG
        pred_base = _fit_state_fir_bg(X, y, s_arr, bg_arr, prep['STATE_NAMES'])
        resid = y - pred_base
        resid_valid = resid[np.isfinite(resid)]
        n_resid = len(resid_valid)

        if n_resid < 1000:
            results[name] = {'error': 'insufficient residuals'}
            continue

        # Test each AR order
        order_results = []
        for order in ar_orders:
            ar_X, ar_y = [], []
            for t in range(order, n_resid):
                hist = resid_valid[t - order:t][::-1]
                ar_X.append(hist)
                ar_y.append(resid_valid[t])

            ar_X = np.array(ar_X)
            ar_y = np.array(ar_y)
            n = len(ar_y)

            ar_Xb = np.column_stack([ar_X, np.ones(n)])
            try:
                c = np.linalg.lstsq(ar_Xb, ar_y, rcond=None)[0]
                pred = ar_Xb @ c
                rss = np.sum((ar_y - pred) ** 2)
                sigma2 = rss / n

                # AIC and BIC
                k_params = order + 1  # AR coefficients + intercept
                aic = n * np.log(sigma2 + 1e-12) + 2 * k_params
                bic = n * np.log(sigma2 + 1e-12) + k_params * np.log(n)

                r2 = 1.0 - np.var(ar_y - pred) / np.var(ar_y)

                order_results.append({
                    'order': order,
                    'aic': round(float(aic), 1),
                    'bic': round(float(bic), 1),
                    'r2': round(float(r2), 4),
                    'n': n,
                })
            except Exception:
                continue

        if not order_results:
            results[name] = {'error': 'all fits failed'}
            continue

        # Find optimal orders
        best_aic = min(order_results, key=lambda x: x['aic'])
        best_bic = min(order_results, key=lambda x: x['bic'])

        # Diminishing returns: where does R² plateau? (first order where
        # marginal improvement < 0.005)
        r2_vals = [r['r2'] for r in order_results]
        plateau_order = ar_orders[0]
        for i in range(1, len(r2_vals)):
            if r2_vals[i] - r2_vals[i-1] < 0.002:
                plateau_order = ar_orders[i]
                break

        results[name] = {
            'best_aic_order': best_aic['order'],
            'best_bic_order': best_bic['order'],
            'plateau_order': plateau_order,
            'r2_at_aic': best_aic['r2'],
            'r2_at_bic': best_bic['r2'],
            'r2_at_ar6': next((r['r2'] for r in order_results if r['order'] == 6), None),
            'r2_at_ar12': next((r['r2'] for r in order_results if r['order'] == 12), None),
            'r2_at_ar24': next((r['r2'] for r in order_results if r['order'] == 24), None),
            'r2_curve': [(r['order'], r['r2']) for r in order_results[::3]],  # every 3rd
        }

        if detail:
            print(f"  {name}: AIC→AR({best_aic['order']}), BIC→AR({best_bic['order']}), "
                  f"plateau@AR({plateau_order}), "
                  f"R²: AR6={results[name]['r2_at_ar6']}, AR12={results[name]['r2_at_ar12']}, "
                  f"AR24={results[name]['r2_at_ar24']}")

    # Summary
    aic_orders = [v['best_aic_order'] for v in results.values() if 'best_aic_order' in v]
    bic_orders = [v['best_bic_order'] for v in results.values() if 'best_bic_order' in v]
    plat_orders = [v['plateau_order'] for v in results.values() if 'plateau_order' in v]

    summary = {
        'median_aic_order': int(np.median(aic_orders)) if aic_orders else None,
        'median_bic_order': int(np.median(bic_orders)) if bic_orders else None,
        'median_plateau_order': int(np.median(plat_orders)) if plat_orders else None,
        'mean_r2_ar6': round(float(np.mean([v['r2_at_ar6'] for v in results.values()
                                             if v.get('r2_at_ar6')])), 4) if aic_orders else None,
        'mean_r2_ar12': round(float(np.mean([v['r2_at_ar12'] for v in results.values()
                                              if v.get('r2_at_ar12')])), 4) if aic_orders else None,
        'mean_r2_ar24': round(float(np.mean([v['r2_at_ar24'] for v in results.values()
                                              if v.get('r2_at_ar24')])), 4) if aic_orders else None,
    }

    return {'exp': 'EXP-539', 'title': 'AR Order Selection (AIC/BIC)',
            'summary': summary, 'patients': results}


# ── EXP-540: State-AR Interaction ───────────────────────────────────────

def run_exp540(patients, detail=False):
    """Different AR models per metabolic state.

    Hypothesis: fasting states have smoother dynamics (lower AR order),
    while meal states have complex absorption kinetics (higher AR order).
    """
    L_fir = 6
    ar_order = 12  # Fixed order, compare across states
    results = {}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            prep['channels'], prep['valid'], prep['states'],
            prep['bg'], prep['dbg'], L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        pred_base = _fit_state_fir_bg(X, y, s_arr, bg_arr, prep['STATE_NAMES'])
        resid = y - pred_base

        # Global AR for comparison
        resid_v = resid[np.isfinite(resid)]
        if len(resid_v) < 500:
            results[name] = {'error': 'insufficient residuals'}
            continue

        # State-specific AR
        state_ar = {}
        pred_state_ar = np.full(len(y), np.nan)

        for s_idx, s_name in enumerate(prep['STATE_NAMES']):
            # Find contiguous runs of this state
            s_mask = (s_arr == s_idx) & np.isfinite(resid)
            s_indices = np.where(s_mask)[0]

            if len(s_indices) < ar_order + 50:
                state_ar[s_name] = {'n': int(len(s_indices)), 'error': 'too few'}
                continue

            # Build AR features (respecting temporal ordering within state)
            ar_X, ar_y, ar_idx = [], [], []
            for i in range(ar_order, len(s_indices)):
                # Check if previous ar_order indices are contiguous
                t = s_indices[i]
                prev_indices = s_indices[i - ar_order:i]
                # They must be from nearby timesteps (within 2× ar_order spacing)
                if prev_indices[-1] - prev_indices[0] > ar_order * 3:
                    continue
                hist = resid[prev_indices][::-1]
                if np.all(np.isfinite(hist)):
                    ar_X.append(hist)
                    ar_y.append(resid[t])
                    ar_idx.append(t)

            if len(ar_X) < 50:
                state_ar[s_name] = {'n': int(len(s_indices)), 'error': 'non-contiguous'}
                continue

            ar_X = np.array(ar_X)
            ar_y = np.array(ar_y)
            ar_Xb = np.column_stack([ar_X, np.ones(len(ar_X))])

            try:
                c = np.linalg.lstsq(ar_Xb, ar_y, rcond=None)[0]
                ar_pred = ar_Xb @ c
                r2_ar = 1.0 - np.var(ar_y - ar_pred) / np.var(ar_y) if np.var(ar_y) > 1e-6 else 0

                # Autocorrelation decay (how quickly does state-specific AR lose memory?)
                autocorr_1 = np.corrcoef(ar_y[:-1], ar_y[1:])[0, 1] if len(ar_y) > 10 else None

                state_ar[s_name] = {
                    'n': int(len(s_indices)),
                    'n_ar_samples': len(ar_y),
                    'r2_ar': round(float(r2_ar), 4),
                    'autocorr_5min': round(float(autocorr_1), 4) if autocorr_1 is not None else None,
                    'resid_std': round(float(np.std(ar_y)), 4),
                    'dominant_coeff': round(float(c[0]), 4),  # AR(1) coefficient
                }
            except Exception:
                state_ar[s_name] = {'n': int(len(s_indices)), 'error': 'fit failed'}

        results[name] = {'state_ar': state_ar}

        if detail:
            for s_name, s_data in state_ar.items():
                if 'r2_ar' in s_data:
                    print(f"  {name}/{s_name}: R²={s_data['r2_ar']:.3f}, "
                          f"autocorr={s_data.get('autocorr_5min', '?')}, "
                          f"AR(1)={s_data['dominant_coeff']:.3f}")

    # Summary: average AR performance by state
    state_summary = {}
    for s_name in ['fasting', 'post_meal', 'correction', 'recovery', 'stable']:
        r2_vals = [v['state_ar'][s_name]['r2_ar']
                   for v in results.values()
                   if s_name in v.get('state_ar', {}) and 'r2_ar' in v['state_ar'][s_name]]
        ac_vals = [v['state_ar'][s_name]['autocorr_5min']
                   for v in results.values()
                   if s_name in v.get('state_ar', {}) and
                   isinstance(v['state_ar'][s_name].get('autocorr_5min'), (int, float))]

        state_summary[s_name] = {
            'mean_r2': round(float(np.mean(r2_vals)), 4) if r2_vals else None,
            'mean_autocorr': round(float(np.mean(ac_vals)), 4) if ac_vals else None,
            'n_patients': len(r2_vals),
        }

    return {'exp': 'EXP-540', 'title': 'State-AR Interaction',
            'summary': state_summary, 'patients': results}


# ── EXP-541: Simple Kalman Filter ───────────────────────────────────────

def run_exp541(patients, detail=False):
    """Kalman filter combining flux model with AR prediction.

    State: [bg, dbg/dt, flux_bias]
    Observation: bg_measured
    Control: net_flux (from supply-demand model)
    Process: AR(1) on dbg/dt innovation
    """
    results = {}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        bg = prep['bg']
        dbg = prep['dbg']
        net = prep['sd']['net']
        valid = prep['valid'] & np.isfinite(net)

        # Get contiguous segments (at least 100 steps)
        N = len(bg)
        segments = []
        start = None
        for t in range(N):
            if valid[t]:
                if start is None:
                    start = t
            else:
                if start is not None and t - start >= 100:
                    segments.append((start, t))
                start = None
        if start is not None and N - start >= 100:
            segments.append((start, N))

        if not segments:
            results[name] = {'error': 'no contiguous segments'}
            continue

        # Run Kalman on each segment
        all_innov = []
        all_pred_err = []
        all_naive_err = []

        for seg_start, seg_end in segments:
            seg_bg = bg[seg_start:seg_end]
            seg_net = net[seg_start:seg_end]
            seg_n = seg_end - seg_start

            # Kalman parameters (hand-tuned from physics)
            dt = 5.0  # 5 min steps
            # State: [bg, velocity (dbg/dt)]
            # Transition: bg[t+1] = bg[t] + dt * vel[t] + dt * flux[t]
            #             vel[t+1] = alpha * vel[t]  (AR(1) decay)
            alpha = 0.8  # velocity persistence

            # Process noise
            q_bg = 1.0       # BG process noise (mg/dL)²
            q_vel = 0.5      # velocity process noise
            r_obs = 9.0      # observation noise (3 mg/dL std → 9 variance)

            # Initialize state
            x = np.array([seg_bg[0], 0.0])  # [bg, velocity]
            P = np.diag([25.0, 1.0])  # initial covariance

            innovations = []
            pred_errors = []
            naive_errors = []

            for t in range(1, seg_n):
                # Predict
                F = np.array([[1.0, dt], [0.0, alpha]])
                B = np.array([dt, 0.0])  # flux enters via BG equation
                Q = np.diag([q_bg, q_vel])

                x_pred = F @ x + B * seg_net[t-1]
                P_pred = F @ P @ F.T + Q

                # Update
                z = seg_bg[t]
                if not np.isfinite(z):
                    continue
                H = np.array([1.0, 0.0])
                S = H @ P_pred @ H + r_obs
                K = P_pred @ H / S
                innov = z - H @ x_pred

                x = x_pred + K * innov
                P = (np.eye(2) - np.outer(K, H)) @ P_pred

                innovations.append(innov)
                pred_errors.append((z - x_pred[0]) ** 2)  # Kalman prediction error
                naive_errors.append((z - seg_bg[t-1]) ** 2)  # naive persistence

            all_innov.extend(innovations)
            all_pred_err.extend(pred_errors)
            all_naive_err.extend(naive_errors)

        if not all_pred_err:
            results[name] = {'error': 'no predictions'}
            continue

        kalman_rmse = np.sqrt(np.mean(all_pred_err))
        naive_rmse = np.sqrt(np.mean(all_naive_err))
        skill = 1.0 - kalman_rmse / naive_rmse if naive_rmse > 0 else 0

        innov_arr = np.array(all_innov)
        innov_autocorr = np.corrcoef(innov_arr[:-1], innov_arr[1:])[0, 1] if len(innov_arr) > 10 else None

        results[name] = {
            'kalman_rmse': round(float(kalman_rmse), 2),
            'naive_rmse': round(float(naive_rmse), 2),
            'skill_score': round(float(skill), 4),
            'innovation_std': round(float(np.std(innov_arr)), 2),
            'innovation_autocorr': round(float(innov_autocorr), 4) if innov_autocorr is not None else None,
            'n_steps': len(all_pred_err),
        }

        if detail:
            print(f"  {name}: Kalman RMSE={kalman_rmse:.1f}, naive={naive_rmse:.1f}, "
                  f"skill={skill:.3f}, innov AC={innov_autocorr:.3f}" if innov_autocorr else
                  f"  {name}: Kalman RMSE={kalman_rmse:.1f}, skill={skill:.3f}")

    # Summary
    skills = [v['skill_score'] for v in results.values() if 'skill_score' in v]
    k_rmse = [v['kalman_rmse'] for v in results.values() if 'kalman_rmse' in v]
    n_rmse = [v['naive_rmse'] for v in results.values() if 'naive_rmse' in v]

    summary = {
        'mean_skill': round(float(np.mean(skills)), 4) if skills else None,
        'mean_kalman_rmse': round(float(np.mean(k_rmse)), 2) if k_rmse else None,
        'mean_naive_rmse': round(float(np.mean(n_rmse)), 2) if n_rmse else None,
        'interpretation': 'skill > 0 = Kalman beats persistence, > 0.3 = strong',
    }

    return {'exp': 'EXP-541', 'title': 'Kalman Filter',
            'summary': summary, 'patients': results}


# ── EXP-542: Prediction Horizon ─────────────────────────────────────────

def run_exp542(patients, detail=False):
    """Evaluate prediction accuracy at different horizons: 5,15,30,60,90,120 min.

    Uses AR model trained on state-FIR+BG residuals. At each horizon h,
    predict BG[t+h] from data available at time t.
    """
    L_fir = 6
    ar_order = 12
    horizons = [1, 3, 6, 12, 18, 24]  # in steps (×5min = 5,15,30,60,90,120min)
    results = {}

    for p in patients:
        name = p['name']
        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        bg = prep['bg']
        dbg = prep['dbg']

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            prep['channels'], prep['valid'], prep['states'],
            bg, dbg, L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        # Fit state-FIR+BG model
        pred_base = _fit_state_fir_bg(X, y, s_arr, bg_arr, prep['STATE_NAMES'])
        resid = y - pred_base

        # Fit AR model on residuals
        ar_X, ar_y = [], []
        for t in range(ar_order, len(resid)):
            if not np.isfinite(resid[t]):
                continue
            hist = resid[t - ar_order:t][::-1]
            if np.all(np.isfinite(hist)):
                ar_X.append(hist)
                ar_y.append(resid[t])

        if len(ar_X) < 500:
            results[name] = {'error': 'insufficient for AR'}
            continue

        ar_X = np.array(ar_X)
        ar_y = np.array(ar_y)
        ar_Xb = np.column_stack([ar_X, np.ones(len(ar_X))])
        ar_c = np.linalg.lstsq(ar_Xb, ar_y, rcond=None)[0]

        # Evaluate at each horizon
        # For simplicity: use 1-step model R² and extrapolate via iterated prediction
        # But more realistic: measure actual dBG at horizon h
        horizon_results = {}

        for h in horizons:
            h_min = h * 5
            # For each valid point, compute BG change over horizon h
            errors_model = []
            errors_naive = []

            for i in range(len(idx) - h):
                t_now = idx[i]
                t_future = idx[i + h] if i + h < len(idx) else None
                if t_future is None:
                    continue

                # Check that future is actually h steps away (no gaps)
                if t_future - t_now != h:
                    # Not exactly h steps — skip
                    continue

                actual_change = bg[t_future] - bg[t_now]
                if not np.isfinite(actual_change):
                    continue

                # Model prediction: dBG/dt × h (simple scaling)
                # Use the model's predicted dBG/dt at current time
                if i < len(pred_base) and np.isfinite(pred_base[i]):
                    model_change = pred_base[i] * h
                else:
                    continue

                errors_model.append((actual_change - model_change) ** 2)
                errors_naive.append(actual_change ** 2)  # naive: predict no change

            if len(errors_model) > 100:
                rmse_model = np.sqrt(np.mean(errors_model))
                rmse_naive = np.sqrt(np.mean(errors_naive))
                skill = 1.0 - rmse_model / rmse_naive if rmse_naive > 0 else 0

                horizon_results[f'{h_min}min'] = {
                    'rmse_model': round(float(rmse_model), 2),
                    'rmse_naive': round(float(rmse_naive), 2),
                    'skill': round(float(skill), 4),
                    'n_samples': len(errors_model),
                }

        results[name] = {'horizons': horizon_results}

        if detail:
            for h_name, h_data in sorted(horizon_results.items()):
                print(f"  {name}@{h_name}: RMSE={h_data['rmse_model']:.1f}, "
                      f"skill={h_data['skill']:.3f}")

    # Summary by horizon
    summary = {}
    for h in horizons:
        h_name = f'{h*5}min'
        skills = [v['horizons'][h_name]['skill'] for v in results.values()
                  if h_name in v.get('horizons', {})]
        rmses = [v['horizons'][h_name]['rmse_model'] for v in results.values()
                 if h_name in v.get('horizons', {})]
        if skills:
            summary[h_name] = {
                'mean_skill': round(float(np.mean(skills)), 4),
                'mean_rmse': round(float(np.mean(rmses)), 2),
                'n_patients': len(skills),
            }

    return {'exp': 'EXP-542', 'title': 'Prediction Horizon Degradation',
            'summary': summary, 'patients': results}


# ── EXP-543: Device/Sensor Age Effect ───────────────────────────────────

def run_exp543(patients, detail=False):
    """Does model performance vary with sensor wear time?

    CGM sensors degrade over 10-day wear period. If model R² drops
    on day 8-10 vs day 1-3, sensor noise is a confirmed confounder.
    """
    L_fir = 6
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        # Check if we have device/sensor info
        # Use dateTime to partition into ~10-day segments
        # (proxy for sensor sessions)
        if 'dateString' in df.columns:
            try:
                times = pd.to_datetime(df['dateString'])
            except Exception:
                times = pd.RangeIndex(len(df))
        else:
            times = pd.RangeIndex(len(df))

        prep = _prepare_patient(p)
        if prep is None:
            results[name] = {'error': 'preparation failed'}
            continue

        X, y, s_arr, bg_arr, idx = _build_fir_features(
            prep['channels'], prep['valid'], prep['states'],
            prep['bg'], prep['dbg'], L_fir)
        if X is None:
            results[name] = {'error': 'insufficient data'}
            continue

        n = len(y)

        # Partition into ~10-day blocks (2880 steps = 10 days at 5min)
        block_size = 2880
        n_blocks = max(1, n // block_size)

        block_results = []
        for b in range(n_blocks):
            b_start = b * block_size
            b_end = min((b + 1) * block_size, n)
            if b_end - b_start < 500:
                continue

            # Fit model on this block
            X_b = X[b_start:b_end]
            y_b = y[b_start:b_end]
            s_b = s_arr[b_start:b_end]
            bg_b = bg_arr[b_start:b_end]

            y_var = np.var(y_b)
            if y_var < 1e-6:
                continue

            # Simple FIR fit
            X_bias = np.column_stack([X_b, bg_b, np.ones(len(X_b))])
            try:
                c = np.linalg.lstsq(X_bias, y_b, rcond=None)[0]
                pred = X_bias @ c
                r2 = 1.0 - np.var(y_b - pred) / y_var
            except Exception:
                continue

            # High-frequency noise estimate
            hf_noise = np.var(np.diff(y_b)) / 2  # Differencing estimator
            noise_pct = hf_noise / y_var if y_var > 0 else 0

            block_results.append({
                'block': b,
                'day_start': b * 10,
                'day_end': min((b + 1) * 10, n * 5 / (60 * 24)),
                'n': b_end - b_start,
                'r2': round(float(r2), 4),
                'noise_pct': round(float(noise_pct), 3),
                'bg_mean': round(float(np.mean(bg_b)), 1),
                'bg_std': round(float(np.std(bg_b)), 1),
            })

        if not block_results:
            results[name] = {'error': 'no valid blocks'}
            continue

        # Look for temporal trend in R² and noise
        r2_vals = [b['r2'] for b in block_results]
        noise_vals = [b['noise_pct'] for b in block_results]
        blocks = list(range(len(r2_vals)))

        if len(blocks) > 3:
            r2_trend = stats.spearmanr(blocks, r2_vals)
            noise_trend = stats.spearmanr(blocks, noise_vals)
        else:
            r2_trend = type('obj', (), {'statistic': 0, 'pvalue': 1})()
            noise_trend = type('obj', (), {'statistic': 0, 'pvalue': 1})()

        # Compare first quarter vs last quarter
        q1_end = max(1, len(block_results) // 4)
        q4_start = len(block_results) - q1_end
        r2_early = np.mean([b['r2'] for b in block_results[:q1_end]])
        r2_late = np.mean([b['r2'] for b in block_results[q4_start:]])
        noise_early = np.mean([b['noise_pct'] for b in block_results[:q1_end]])
        noise_late = np.mean([b['noise_pct'] for b in block_results[q4_start:]])

        results[name] = {
            'n_blocks': len(block_results),
            'r2_trend_rho': round(float(r2_trend.statistic), 3),
            'r2_trend_p': round(float(r2_trend.pvalue), 4),
            'noise_trend_rho': round(float(noise_trend.statistic), 3),
            'noise_trend_p': round(float(noise_trend.pvalue), 4),
            'r2_early': round(float(r2_early), 4),
            'r2_late': round(float(r2_late), 4),
            'r2_degradation': round(float(r2_early - r2_late), 4),
            'noise_early': round(float(noise_early), 3),
            'noise_late': round(float(noise_late), 3),
            'blocks': block_results,
        }

        if detail:
            print(f"  {name}: {len(block_results)} blocks, "
                  f"R² trend ρ={r2_trend.statistic:.3f} (p={r2_trend.pvalue:.3f}), "
                  f"early={r2_early:.3f} → late={r2_late:.3f}")

    # Summary
    trends = [v['r2_trend_rho'] for v in results.values() if 'r2_trend_rho' in v]
    degs = [v['r2_degradation'] for v in results.values() if 'r2_degradation' in v]
    sig = sum(1 for v in results.values() if v.get('r2_trend_p', 1) < 0.05)

    summary = {
        'mean_r2_trend': round(float(np.mean(trends)), 3) if trends else None,
        'mean_degradation': round(float(np.mean(degs)), 4) if degs else None,
        'n_significant': sig,
        'n_patients': len(trends),
    }

    return {'exp': 'EXP-543', 'title': 'Device/Sensor Age Effect',
            'summary': summary, 'patients': results}


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-538/539/540/541/542/543')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', nargs='*',
                        default=['538', '539', '540', '541', '542', '543'])
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    all_results = {}

    if '538' in args.experiments:
        print("\n── EXP-538: Temporal Cross-Validation ──")
        r = run_exp538(patients, detail=args.detail)
        all_results['exp538'] = r
        s = r['summary']
        print(f"  Det: train={s['mean_det_train']}, test={s['mean_det_test']}, "
              f"gap={s['mean_overfit_gap']}, AR test={s['mean_ar_test']}")

    if '539' in args.experiments:
        print("\n── EXP-539: AR Order Selection ──")
        r = run_exp539(patients, detail=args.detail)
        all_results['exp539'] = r
        s = r['summary']
        print(f"  AIC→AR({s['median_aic_order']}), BIC→AR({s['median_bic_order']}), "
              f"plateau→AR({s['median_plateau_order']})")
        print(f"  R²: AR6={s['mean_r2_ar6']}, AR12={s['mean_r2_ar12']}, AR24={s['mean_r2_ar24']}")

    if '540' in args.experiments:
        print("\n── EXP-540: State-AR Interaction ──")
        r = run_exp540(patients, detail=args.detail)
        all_results['exp540'] = r
        for s_name, s_data in r['summary'].items():
            if s_data.get('mean_r2'):
                print(f"  {s_name}: R²={s_data['mean_r2']}, "
                      f"autocorr={s_data.get('mean_autocorr', '?')}")

    if '541' in args.experiments:
        print("\n── EXP-541: Kalman Filter ──")
        r = run_exp541(patients, detail=args.detail)
        all_results['exp541'] = r
        s = r['summary']
        print(f"  Skill={s['mean_skill']}, "
              f"Kalman RMSE={s['mean_kalman_rmse']}, "
              f"Naive RMSE={s['mean_naive_rmse']}")

    if '542' in args.experiments:
        print("\n── EXP-542: Prediction Horizon ──")
        r = run_exp542(patients, detail=args.detail)
        all_results['exp542'] = r
        for h_name, h_data in sorted(r['summary'].items()):
            print(f"  @{h_name}: skill={h_data['mean_skill']}, RMSE={h_data['mean_rmse']}")

    if '543' in args.experiments:
        print("\n── EXP-543: Device/Sensor Age ──")
        r = run_exp543(patients, detail=args.detail)
        all_results['exp543'] = r
        s = r['summary']
        print(f"  R² trend ρ={s['mean_r2_trend']}, "
              f"degradation={s['mean_degradation']}, "
              f"{s['n_significant']}/{s['n_patients']} significant")

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        fnames = {
            'exp538': 'exp538_temporal_cv.json',
            'exp539': 'exp539_ar_order.json',
            'exp540': 'exp540_state_ar.json',
            'exp541': 'exp541_kalman.json',
            'exp542': 'exp542_horizon.json',
            'exp543': 'exp543_device_age.json',
        }
        for key, result in all_results.items():
            path = RESULTS_DIR / fnames.get(key, f'{key}.json')
            with open(path, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved {path}")

    print("\n── Done ──")


if __name__ == '__main__':
    main()
