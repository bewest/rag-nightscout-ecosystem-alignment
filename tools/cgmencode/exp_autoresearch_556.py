#!/usr/bin/env python3
"""EXP-556/557/558/559/560/561: Exercise detection, multi-step Kalman,
correction energy, circadian mismatch, Granger causality, transfer entropy.

Building on EXP-550-555 findings:
  - Kalman+AR beats persistence (skill=0.174, EXP-552)
  - Weekly turbulence predicts TIR (r=-0.49, EXP-554)
  - Model stable over months (R²=0.657, EXP-555)
  - Nonlinear features don't help (EXP-553)

This wave targets:
  1. Anomaly characterization — Can we detect exercise? (EXP-556)
  2. Kalman horizon extension — How far ahead can we predict? (EXP-557)
  3. Clinical scores — Settings mismatch by time-of-day (EXP-559/560)
  4. Information-theoretic validation — Granger + transfer entropy (EXP-561)

References:
  - EXP-547: Anomaly detection (post-meal 2-3× fasting)
  - EXP-552: Kalman+AR skill=0.174 (9/11 positive)
  - EXP-550: AID correction magnitude
  - EXP-554: Weekly turbulence → TIR (r=-0.49)
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
# EXP-556: Exercise Detection via Anomaly Clustering
# ──────────────────────────────────────────────
def exp556_exercise_detection(patients, detail=False):
    """Cluster anomaly events by temporal signature to detect exercise."""
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
        resid_std = np.std(resid[valid_r])
        if resid_std < 1e-6:
            continue

        # Identify anomaly events (|residual| > 2σ)
        anomaly_mask = valid_r & (np.abs(resid) > 2 * resid_std)
        anomaly_idx = np.where(anomaly_mask)[0]

        if len(anomaly_idx) < 10:
            continue

        # Cluster anomalies by temporal proximity (events within 6 steps = 30min)
        clusters = []
        current_cluster = [anomaly_idx[0]]
        for i in range(1, len(anomaly_idx)):
            if anomaly_idx[i] - anomaly_idx[i - 1] <= 6:
                current_cluster.append(anomaly_idx[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [anomaly_idx[i]]
        clusters.append(current_cluster)

        # Characterize clusters
        cluster_features = []
        for cl in clusters:
            cl = np.array(cl)
            duration = len(cl)  # in 5-min steps
            mean_resid = np.mean(resid[cl])
            max_abs_resid = np.max(np.abs(resid[cl]))
            bg_change = bg_v[cl[-1]] - bg_v[cl[0]] if len(cl) > 1 else 0

            # Demand context (insulin activity during anomaly)
            demand_during = np.mean(demand[valid][cl])
            supply_during = np.mean(supply[valid][cl])

            # Time of day
            tod_start = cl[0] % 288

            # Exercise signature: BG dropping, low supply (no meal), moderate demand
            # Exercise increases insulin sensitivity → BG drops faster than expected
            is_exercise_like = (mean_resid < -resid_std) and (supply_during < np.median(supply[valid]))

            cluster_features.append({
                'start': int(cl[0]),
                'duration_steps': int(duration),
                'mean_resid': float(mean_resid),
                'max_abs_resid': float(max_abs_resid),
                'bg_change': float(bg_change),
                'demand_during': float(demand_during),
                'supply_during': float(supply_during),
                'tod_bin': int(tod_start),
                'exercise_like': bool(is_exercise_like),
            })

        n_clusters = len(cluster_features)
        n_exercise = sum(1 for c in cluster_features if c['exercise_like'])
        exercise_frac = n_exercise / n_clusters if n_clusters > 0 else 0

        # Characterize exercise-like events
        exercise_events = [c for c in cluster_features if c['exercise_like']]
        if exercise_events:
            mean_duration = np.mean([c['duration_steps'] for c in exercise_events])
            mean_bg_drop = np.mean([c['bg_change'] for c in exercise_events])
            # Time-of-day distribution
            tod_bins = [c['tod_bin'] for c in exercise_events]
            morning = sum(1 for t in tod_bins if 72 <= t < 144) / len(tod_bins)
            afternoon = sum(1 for t in tod_bins if 144 <= t < 216) / len(tod_bins)
            evening = sum(1 for t in tod_bins if 216 <= t < 288) / len(tod_bins)
        else:
            mean_duration = 0
            mean_bg_drop = 0
            morning = afternoon = evening = 0

        results[name] = {
            'n_anomaly_events': int(len(anomaly_idx)),
            'n_clusters': n_clusters,
            'n_exercise_like': n_exercise,
            'exercise_frac': float(exercise_frac),
            'mean_exercise_duration': float(mean_duration) * 5,  # convert to minutes
            'mean_exercise_bg_drop': float(mean_bg_drop),
            'exercise_tod': {'morning': float(morning), 'afternoon': float(afternoon),
                            'evening': float(evening)},
        }

        if detail:
            print(f"  {name}: {n_clusters} clusters, {n_exercise} exercise-like ({exercise_frac:.0%}), "
                  f"mean drop={mean_bg_drop:.0f} mg/dL, mean dur={mean_duration * 5:.0f}min, "
                  f"AM={morning:.0%} PM={afternoon:.0%} EVE={evening:.0%}")

    n_ex = [r['n_exercise_like'] for r in results.values()]
    fracs = [r['exercise_frac'] for r in results.values()]

    summary = {
        'experiment': 'EXP-556',
        'name': 'Exercise Detection via Anomaly Clustering',
        'mean_exercise_like': float(np.mean(n_ex)) if n_ex else 0,
        'mean_exercise_frac': float(np.mean(fracs)) if fracs else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-556 Summary: mean {np.mean(n_ex):.0f} exercise-like events/patient, "
              f"frac={np.mean(fracs):.0%}")

    return summary


# ──────────────────────────────────────────────
# EXP-557: Multi-Step Kalman Prediction
# ──────────────────────────────────────────────
def exp557_multistep_kalman(patients, detail=False):
    """Extend EXP-552 scalar Kalman to 2/3/4/6 step-ahead (10/15/20/30min)."""
    results = {}
    ar_order = 6
    horizons = [1, 2, 3, 4, 6]  # steps (5, 10, 15, 20, 30 min)

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
        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        flux_pred = model['flux_pred']
        beta_ar = model['beta_ar']
        flux_resid = model['flux_resid']

        # Compute innovation variance from training
        combined_resid = model['combined_resid']
        train_resid = combined_resid[:split]
        train_valid = np.isfinite(train_resid)
        if np.sum(train_valid) < 50:
            continue
        innov_var = np.var(train_resid[train_valid])
        Q_scalar = innov_var * 0.8
        R_scalar = innov_var * 0.2

        # Run Kalman for each horizon
        horizon_results = {}
        for h in horizons:
            test_start = split
            bg_est = bg_v[test_start]
            P_scalar = R_scalar
            resid_history = list(flux_resid[test_start - ar_order:test_start])

            predictions = []
            actuals = []

            for t in range(test_start, N - h):
                # h-step-ahead prediction: recursive predict without update
                bg_curr = bg_est
                P_curr = P_scalar
                resid_hist_curr = list(resid_history)

                for step in range(h):
                    idx = t + step
                    if idx >= N:
                        break
                    if len(resid_hist_curr) >= ar_order:
                        ar_input = np.array(resid_hist_curr[-ar_order:])[::-1]
                        ar_val = float(np.clip(ar_input @ beta_ar, -50, 50))
                    else:
                        ar_val = 0.0
                    flux_val = float(np.clip(flux_pred[idx], -50, 50))
                    bg_curr = bg_curr + flux_val + ar_val
                    P_curr = P_curr + Q_scalar
                    # For multi-step, update residual history with predicted values
                    resid_hist_curr.append(float(ar_val))

                predictions.append(bg_curr)
                actuals.append(bg_v[t + h])

                # Now do the actual 1-step Kalman update for the filter state
                if len(resid_history) >= ar_order:
                    ar_input = np.array(resid_history[-ar_order:])[::-1]
                    ar_val = float(np.clip(ar_input @ beta_ar, -50, 50))
                else:
                    ar_val = 0.0
                flux_val = float(np.clip(flux_pred[t], -50, 50))
                bg_pred = bg_est + flux_val + ar_val
                P_pred = P_scalar + Q_scalar
                y_obs = bg_v[t]
                innov = y_obs - bg_pred
                S = P_pred + R_scalar
                K = P_pred / S
                bg_est = bg_pred + K * innov
                P_scalar = (1.0 - K) * P_pred
                actual_dbg = y_obs - bg_v[t - 1] if t > 0 else 0.0
                resid_history.append(float(actual_dbg - flux_val))

            predictions = np.array(predictions)
            actuals = np.array(actuals)
            valid_pred = np.isfinite(predictions) & np.isfinite(actuals)
            if np.sum(valid_pred) < 20:
                continue

            mse_kalman = np.mean((predictions[valid_pred] - actuals[valid_pred]) ** 2)
            # Persistence for this horizon: bg_v[t] predicts bg_v[t+h]
            persist_pred = bg_v[test_start:N - h][:len(actuals)]
            valid_both = valid_pred & np.isfinite(persist_pred)
            mse_persist = np.mean((persist_pred[valid_both] - actuals[valid_both]) ** 2)
            skill = 1.0 - mse_kalman / mse_persist if mse_persist > 0 else 0.0

            horizon_results[f'{h * 5}min'] = {
                'skill': float(skill),
                'rmse_kalman': float(np.sqrt(mse_kalman)),
                'rmse_persist': float(np.sqrt(mse_persist)),
            }

        results[name] = horizon_results

        if detail:
            parts = [f"{k}: skill={v['skill']:.3f}" for k, v in sorted(horizon_results.items())]
            print(f"  {name}: {', '.join(parts)}")

    # Aggregate by horizon
    horizon_summary = {}
    for h_name in [f'{h * 5}min' for h in horizons]:
        skills = [r[h_name]['skill'] for r in results.values() if h_name in r]
        if skills:
            horizon_summary[h_name] = {
                'mean_skill': float(np.mean(skills)),
                'median_skill': float(np.median(skills)),
                'positive_count': sum(1 for s in skills if s > 0),
                'total': len(skills),
            }

    summary = {
        'experiment': 'EXP-557',
        'name': 'Multi-Step Kalman Prediction',
        'horizon_summary': horizon_summary,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-557 Summary:")
        for h_name, hs in sorted(horizon_summary.items()):
            print(f"    {h_name}: skill={hs['mean_skill']:.3f}, "
                  f"{hs['positive_count']}/{hs['total']} positive")

    return summary


# ──────────────────────────────────────────────
# EXP-559: Correction Energy Score
# ──────────────────────────────────────────────
def exp559_correction_energy(patients, detail=False):
    """Integrate AID correction magnitude over 24h windows → predict TIR."""
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
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        demand_v = demand[valid]
        N = len(bg_v)

        # Compute profile baseline (median demand per time-of-day bin)
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288
        profile_demand = np.zeros(288)
        for t in range(288):
            mask_t = tod == t
            if np.sum(mask_t) > 5:
                profile_demand[t] = np.median(demand_v[mask_t])
            else:
                profile_demand[t] = np.median(demand_v)

        # Correction = actual - profile
        correction = demand_v - profile_demand[tod]
        abs_correction = np.abs(correction)

        # Daily windows (288 steps/day)
        day_steps = 288
        n_days = N // day_steps
        if n_days < 7:
            continue

        daily_data = []
        for d in range(n_days):
            s = d * day_steps
            e = s + day_steps
            bg_day = bg_v[s:e]
            tir = np.mean((bg_day >= 70) & (bg_day <= 180))
            correction_energy = np.sum(abs_correction[s:e])
            mean_correction = np.mean(abs_correction[s:e])
            bg_std = np.std(bg_day)

            daily_data.append({
                'day': d, 'tir': tir,
                'correction_energy': correction_energy,
                'mean_correction': mean_correction,
                'bg_std': bg_std,
            })

        ddf = pd.DataFrame(daily_data)

        # Correlations
        corr_energy, p_energy = stats.pearsonr(ddf['tir'], ddf['correction_energy'])
        corr_mean, p_mean = stats.pearsonr(ddf['tir'], ddf['mean_correction'])
        corr_std, p_std = stats.pearsonr(ddf['tir'], ddf['bg_std'])

        # Rolling 7-day windows
        if n_days >= 14:
            weekly_tir = ddf['tir'].rolling(7).mean().dropna()
            weekly_energy = ddf['correction_energy'].rolling(7).mean().dropna()
            if len(weekly_tir) > 5:
                corr_weekly, p_weekly = stats.pearsonr(weekly_tir, weekly_energy)
            else:
                corr_weekly, p_weekly = np.nan, 1.0
        else:
            corr_weekly, p_weekly = np.nan, 1.0

        results[name] = {
            'n_days': n_days,
            'daily_energy_tir_r': float(corr_energy),
            'daily_energy_tir_p': float(p_energy),
            'daily_mean_corr_tir_r': float(corr_mean),
            'weekly_energy_tir_r': float(corr_weekly) if np.isfinite(corr_weekly) else None,
            'mean_tir': float(ddf['tir'].mean()),
            'mean_daily_energy': float(ddf['correction_energy'].mean()),
        }

        if detail:
            weekly_str = f", weekly r={corr_weekly:.3f}" if np.isfinite(corr_weekly) else ""
            print(f"  {name}: {n_days} days, daily energy↔TIR r={corr_energy:.3f} (p={p_energy:.3f})"
                  f"{weekly_str}, TIR={ddf['tir'].mean():.1%}")

    daily_rs = [r['daily_energy_tir_r'] for r in results.values()]
    weekly_rs = [r['weekly_energy_tir_r'] for r in results.values()
                 if r['weekly_energy_tir_r'] is not None]

    summary = {
        'experiment': 'EXP-559',
        'name': 'Correction Energy Score',
        'mean_daily_energy_tir_r': float(np.mean(daily_rs)) if daily_rs else 0,
        'mean_weekly_energy_tir_r': float(np.mean(weekly_rs)) if weekly_rs else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-559 Summary: daily energy↔TIR r={np.mean(daily_rs):.3f}, "
              f"weekly r={np.mean(weekly_rs):.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-560: Circadian Settings Mismatch
# ──────────────────────────────────────────────
def exp560_circadian_mismatch(patients, detail=False):
    """Time-of-day correction patterns reveal WHEN settings are wrong."""
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
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        demand_v = demand[valid]
        N = len(bg_v)

        # Profile baseline
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288
        profile_demand = np.zeros(288)
        for t in range(288):
            mask_t = tod == t
            if np.sum(mask_t) > 5:
                profile_demand[t] = np.median(demand_v[mask_t])
            else:
                profile_demand[t] = np.median(demand_v)

        correction = demand_v - profile_demand[tod]

        # Circadian periods (4 × 6-hour blocks)
        periods = {
            'overnight': (0, 72),    # 00:00-06:00
            'morning': (72, 144),    # 06:00-12:00
            'afternoon': (144, 216), # 12:00-18:00
            'evening': (216, 288),   # 18:00-24:00
        }

        period_stats = {}
        for pname, (t0, t1) in periods.items():
            mask = (tod >= t0) & (tod < t1)
            if np.sum(mask) < 100:
                continue

            corr_period = correction[mask]
            bg_period = bg_v[mask]
            tir_period = np.mean((bg_period >= 70) & (bg_period <= 180))

            # Mean correction (positive = AID increasing insulin, negative = decreasing)
            mean_corr = np.mean(corr_period)
            abs_corr = np.mean(np.abs(corr_period))
            # Correction direction asymmetry
            frac_increase = np.mean(corr_period > 0)
            # BG outcome
            mean_bg = np.mean(bg_period)
            # Time below range
            tbr = np.mean(bg_period < 70)
            tar = np.mean(bg_period > 180)

            period_stats[pname] = {
                'mean_correction': float(mean_corr),
                'abs_correction': float(abs_corr),
                'frac_increase': float(frac_increase),
                'tir': float(tir_period),
                'mean_bg': float(mean_bg),
                'tbr': float(tbr),
                'tar': float(tar),
            }

        if not period_stats:
            continue

        # Identify worst period (highest absolute correction)
        worst_period = max(period_stats.items(), key=lambda x: x[1]['abs_correction'])
        best_period = min(period_stats.items(), key=lambda x: x[1]['abs_correction'])
        mismatch_ratio = worst_period[1]['abs_correction'] / best_period[1]['abs_correction'] \
            if best_period[1]['abs_correction'] > 0.01 else np.nan

        results[name] = {
            'period_stats': period_stats,
            'worst_period': worst_period[0],
            'best_period': best_period[0],
            'mismatch_ratio': float(mismatch_ratio) if np.isfinite(mismatch_ratio) else None,
        }

        if detail:
            parts = [f"{pn}:{ps['abs_correction']:.2f}(TIR={ps['tir']:.0%})"
                     for pn, ps in period_stats.items()]
            print(f"  {name}: {', '.join(parts)} | "
                  f"worst={worst_period[0]}, ratio={mismatch_ratio:.2f}")

    # Aggregate: which period is worst most often?
    worst_counts = {}
    for r in results.values():
        wp = r['worst_period']
        worst_counts[wp] = worst_counts.get(wp, 0) + 1

    ratios = [r['mismatch_ratio'] for r in results.values()
              if r['mismatch_ratio'] is not None]

    summary = {
        'experiment': 'EXP-560',
        'name': 'Circadian Settings Mismatch',
        'worst_period_counts': worst_counts,
        'mean_mismatch_ratio': float(np.mean(ratios)) if ratios else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-560 Summary: worst periods={worst_counts}, "
              f"mean mismatch ratio={np.mean(ratios):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-561: Granger Causality
# ──────────────────────────────────────────────
def exp561_granger_causality(patients, detail=False):
    """Does flux Granger-cause BG changes? VAR model with F-test."""
    results = {}
    max_lag = 6

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
        supply_v = supply[valid]
        demand_v = demand[valid]
        N = len(bg_v)

        if N < 500:
            continue

        # Compute dBG on contiguous valid data
        dbg = _compute_dbg(bg_v)

        # Granger test: does net flux help predict dBG beyond its own lags?
        # Restricted model: dBG_t = Σ a_i * dBG_{t-i}
        # Unrestricted model: dBG_t = Σ a_i * dBG_{t-i} + Σ b_i * net_{t-i}

        # Build feature matrices
        Y = dbg[max_lag:]
        X_restricted = np.zeros((N - max_lag, max_lag))
        X_unrestricted = np.zeros((N - max_lag, 2 * max_lag))

        for lag in range(max_lag):
            X_restricted[:, lag] = dbg[max_lag - lag - 1:N - lag - 1]
            X_unrestricted[:, lag] = dbg[max_lag - lag - 1:N - lag - 1]
            X_unrestricted[:, max_lag + lag] = net_v[max_lag - lag - 1:N - lag - 1]

        valid_mask = np.isfinite(Y) & np.all(np.isfinite(X_unrestricted), axis=1)
        Y_v = Y[valid_mask]
        X_r_v = X_restricted[valid_mask]
        X_u_v = X_unrestricted[valid_mask]
        n_obs = len(Y_v)

        if n_obs < 100:
            continue

        # Fit restricted and unrestricted models (ridge for stability)
        lam = 0.1
        try:
            # Restricted
            XtX_r = X_r_v.T @ X_r_v + lam * np.eye(X_r_v.shape[1])
            beta_r = np.linalg.solve(XtX_r, X_r_v.T @ Y_v)
            resid_r = Y_v - X_r_v @ beta_r
            ss_r = np.sum(resid_r ** 2)

            # Unrestricted
            XtX_u = X_u_v.T @ X_u_v + lam * np.eye(X_u_v.shape[1])
            beta_u = np.linalg.solve(XtX_u, X_u_v.T @ Y_v)
            resid_u = Y_v - X_u_v @ beta_u
            ss_u = np.sum(resid_u ** 2)
        except Exception:
            continue

        # F-test for Granger causality
        df1 = max_lag  # additional parameters
        df2 = n_obs - 2 * max_lag
        if df2 <= 0 or ss_u <= 0:
            continue

        f_stat = ((ss_r - ss_u) / df1) / (ss_u / df2)
        p_value = 1.0 - stats.f.cdf(f_stat, df1, df2)

        # Also test reverse: does dBG Granger-cause net flux?
        Y_rev = net_v[max_lag:]
        X_r_rev = np.zeros((N - max_lag, max_lag))
        X_u_rev = np.zeros((N - max_lag, 2 * max_lag))
        for lag in range(max_lag):
            X_r_rev[:, lag] = net_v[max_lag - lag - 1:N - lag - 1]
            X_u_rev[:, lag] = net_v[max_lag - lag - 1:N - lag - 1]
            X_u_rev[:, max_lag + lag] = dbg[max_lag - lag - 1:N - lag - 1]

        Y_rev_v = Y_rev[valid_mask]
        X_r_rev_v = X_r_rev[valid_mask]
        X_u_rev_v = X_u_rev[valid_mask]

        try:
            XtX_rr = X_r_rev_v.T @ X_r_rev_v + lam * np.eye(max_lag)
            beta_rr = np.linalg.solve(XtX_rr, X_r_rev_v.T @ Y_rev_v)
            resid_rr = Y_rev_v - X_r_rev_v @ beta_rr
            ss_rr = np.sum(resid_rr ** 2)

            XtX_ur = X_u_rev_v.T @ X_u_rev_v + lam * np.eye(2 * max_lag)
            beta_ur = np.linalg.solve(XtX_ur, X_u_rev_v.T @ Y_rev_v)
            resid_ur = Y_rev_v - X_u_rev_v @ beta_ur
            ss_ur = np.sum(resid_ur ** 2)

            f_rev = ((ss_rr - ss_ur) / df1) / (ss_ur / df2)
            p_rev = 1.0 - stats.f.cdf(f_rev, df1, df2)
        except Exception:
            f_rev, p_rev = np.nan, 1.0

        results[name] = {
            'flux_causes_bg': {
                'f_stat': float(f_stat), 'p_value': float(p_value),
                'significant': bool(p_value < 0.01),
            },
            'bg_causes_flux': {
                'f_stat': float(f_rev), 'p_value': float(p_rev),
                'significant': bool(p_rev < 0.01),
            },
            'direction': 'bidirectional' if (p_value < 0.01 and p_rev < 0.01)
                else 'flux→BG' if p_value < 0.01
                else 'BG→flux' if p_rev < 0.01
                else 'none',
            'n_obs': n_obs,
        }

        if detail:
            print(f"  {name}: flux→BG F={f_stat:.1f} (p={p_value:.1e}), "
                  f"BG→flux F={f_rev:.1f} (p={p_rev:.1e}) → {results[name]['direction']}")

    directions = [r['direction'] for r in results.values()]
    dir_counts = {d: directions.count(d) for d in set(directions)}

    summary = {
        'experiment': 'EXP-561',
        'name': 'Granger Causality',
        'direction_counts': dir_counts,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-561 Summary: {dir_counts}")

    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-556-561 autoresearch')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated: 556,557,559,560,561 or "all"')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps = args.experiments.split(',') if args.experiments != 'all' else \
        ['556', '557', '559', '560', '561']

    all_results = {}

    if '556' in exps:
        print("\n=== EXP-556: Exercise Detection ===")
        all_results['exp556'] = exp556_exercise_detection(patients, args.detail)

    if '557' in exps:
        print("\n=== EXP-557: Multi-Step Kalman ===")
        all_results['exp557'] = exp557_multistep_kalman(patients, args.detail)

    if '559' in exps:
        print("\n=== EXP-559: Correction Energy Score ===")
        all_results['exp559'] = exp559_correction_energy(patients, args.detail)

    if '560' in exps:
        print("\n=== EXP-560: Circadian Settings Mismatch ===")
        all_results['exp560'] = exp560_circadian_mismatch(patients, args.detail)

    if '561' in exps:
        print("\n=== EXP-561: Granger Causality ===")
        all_results['exp561'] = exp561_granger_causality(patients, args.detail)

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
