#!/usr/bin/env python3
"""EXP-581–590: Clinical validation, longer time scales, model refinements.

Building on 66 experiments (EXP-511–580):
  - Settings Adequacy Score: 60.1±11.4 (EXP-580)
  - Basal adequacy: 8/11 adequate (EXP-576)
  - Residuals white noise (EXP-570)
  - Post-meal 38.7 mg/dL mean rise (EXP-575)
  - Weekly regimes K=2, silhouette=0.277 (EXP-577)

This wave:
  1. Clinical validation (EXP-581/582/583)
  2. Longer time scales (EXP-584/585/586)
  3. Model refinements (EXP-587/588/589/590)
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
    dbg[1:] = np.diff(bg)
    dbg[0] = 0.0
    return dbg


def _build_ar_features(residuals, order=6):
    N = len(residuals)
    X_ar = np.zeros((N, order))
    for lag in range(1, order + 1):
        X_ar[lag:, lag - 1] = residuals[:-lag]
    return X_ar


def _fit_flux_ar(bg_v, supply_v, demand_v, hepatic_v, split, ar_order=6, lam=1.0):
    """Fit flux + AR model, return predictions and coefficients."""
    N = len(bg_v)
    dbg = _compute_dbg(bg_v)
    X_flux = np.column_stack([supply_v, demand_v, hepatic_v, bg_v])
    y_all = dbg
    train_valid = (np.arange(N) < split) & np.isfinite(y_all) & np.all(np.isfinite(X_flux), axis=1)
    if np.sum(train_valid) < 50:
        return None
    try:
        X_tr = X_flux[train_valid]
        y_tr = y_all[train_valid]
        XtX = X_tr.T @ X_tr + lam * np.eye(X_tr.shape[1])
        beta_flux = np.linalg.solve(XtX, X_tr.T @ y_tr)
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
        beta_ar = np.linalg.solve(XtX_ar, X_ar_tr.T @ y_ar_tr)
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


def _compute_settings_score(bg_v, dbg, resid, net_v, carb_v, N):
    """Compute the EXP-580 settings adequacy composite score."""
    tir = np.sum((bg_v >= 70) & (bg_v <= 180)) / N

    carb_thresh = np.percentile(carb_v[carb_v > 0], 10) if np.sum(carb_v > 0) > 10 else 0.01
    fasting = np.zeros(N, dtype=bool)
    last_carb = -999
    for i in range(N):
        if carb_v[i] > carb_thresh:
            last_carb = i
        if i - last_carb > 24:
            fasting[i] = True

    if np.sum(fasting) > 50:
        fasting_dbg = dbg[fasting]
        v = np.isfinite(fasting_dbg)
        basal_balance = 1.0 - min(abs(np.mean(fasting_dbg[v])) / 2.0, 1.0) if np.sum(v) > 0 else 0.5
    else:
        basal_balance = 0.5

    resid_std = np.std(resid[np.isfinite(resid)])
    correction_eff = 1.0 - min(resid_std / 15.0, 1.0)

    cv = np.std(bg_v) / np.mean(bg_v) if np.mean(bg_v) > 0 else 0.5
    gv_score = 1.0 - min(cv / 0.5, 1.0)

    flux_balance = np.mean(net_v[np.isfinite(net_v)])
    balance_score = 1.0 - min(abs(flux_balance) / 5.0, 1.0)

    composite = tir * 35 + basal_balance * 20 + correction_eff * 20 + gv_score * 15 + balance_score * 10
    return composite, tir


# ──────────────────────────────────────────────
# EXP-581: Settings Score Predicts Future TIR
# ──────────────────────────────────────────────
def exp581_score_predicts_tir(patients, detail=False):
    """Does this month's settings score predict next month's TIR change?"""
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

        month_len = 8640
        n_months = N // month_len
        if n_months < 3:
            continue

        monthly_scores = []
        monthly_tirs = []

        for m in range(n_months):
            s = m * month_len
            e = s + month_len
            bg_m = bg_v[s:e]
            dbg_m = _compute_dbg(bg_m)
            supply_m = supply[valid][s:e]
            demand_m = demand[valid][s:e]
            hepatic_m = hepatic[valid][s:e]
            net_m = net[valid][s:e]
            carb_m = carb_supply[valid][s:e]

            split_m = int(0.8 * month_len)
            model = _fit_flux_ar(bg_m, supply_m, demand_m, hepatic_m, split_m)
            if model is None:
                monthly_scores.append(np.nan)
                monthly_tirs.append(np.nan)
                continue

            score, tir = _compute_settings_score(bg_m, dbg_m, model['combined_resid'],
                                                  net_m, carb_m, month_len)
            monthly_scores.append(score)
            monthly_tirs.append(tir)

        scores = np.array(monthly_scores)
        tirs = np.array(monthly_tirs)

        # Predict: score[m] → TIR_change[m+1] = TIR[m+1] - TIR[m]
        tir_changes = np.diff(tirs)
        scores_lag = scores[:-1]

        v = np.isfinite(scores_lag) & np.isfinite(tir_changes)
        if np.sum(v) < 2:
            continue

        r, p_val = stats.spearmanr(scores_lag[v], tir_changes[v])

        # Also: does low score predict TIR decline?
        median_score = np.median(scores_lag[v])
        low_score_change = np.mean(tir_changes[v & (scores_lag < median_score)])
        high_score_change = np.mean(tir_changes[v & (scores_lag >= median_score)])

        results[name] = {
            'n_months': n_months,
            'r_score_tir_change': float(r),
            'p_value': float(p_val),
            'monthly_scores': [float(s) if np.isfinite(s) else None for s in scores],
            'monthly_tirs': [float(t) if np.isfinite(t) else None for t in tirs],
            'low_score_tir_change': float(low_score_change) if np.isfinite(low_score_change) else 0,
            'high_score_tir_change': float(high_score_change) if np.isfinite(high_score_change) else 0,
        }

        if detail:
            sig = "*" if p_val < 0.1 else ""
            print(f"  {name}: r(score,ΔTIR)={r:.3f}{sig}, "
                  f"low score→ΔTIR={low_score_change:+.3f}, high→{high_score_change:+.3f}")

    rs = [r['r_score_tir_change'] for r in results.values()]
    summary = {
        'experiment': 'EXP-581',
        'name': 'Score Predicts Future TIR',
        'mean_r': float(np.mean(rs)) if rs else 0,
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-581 Summary: mean r(score,ΔTIR)={np.mean(rs):.3f}")
    return summary


# ──────────────────────────────────────────────
# EXP-582: Per-Period Basal Decomposition
# ──────────────────────────────────────────────
def exp582_basal_periods(patients, detail=False):
    """Break basal adequacy into 4 periods for targeted adjustment."""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)
        carb_supply = flux.get('carb_supply', flux['supply'])
        net = flux['net']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        carb_v = carb_supply[valid]
        N = len(bg_v)
        dbg = _compute_dbg(bg_v)

        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288

        # Fasting detection
        carb_thresh = np.percentile(carb_v[carb_v > 0], 10) if np.sum(carb_v > 0) > 10 else 0.01
        fasting = np.zeros(N, dtype=bool)
        last_carb = -999
        for i in range(N):
            if carb_v[i] > carb_thresh:
                last_carb = i
            if i - last_carb > 24:
                fasting[i] = True

        periods = {
            'overnight': (0, 72),
            'morning': (72, 144),
            'afternoon': (144, 216),
            'evening': (216, 288),
        }

        period_results = {}
        for pname, (t0, t1) in periods.items():
            mask = fasting & (tod >= t0) & (tod < t1)
            if np.sum(mask) < 50:
                continue
            fdbg = dbg[mask]
            v = np.isfinite(fdbg)
            if np.sum(v) < 20:
                continue

            mean_dbg = float(np.mean(fdbg[v]))
            # Basal adjustment suggestion (mg/dL per 5min → units/hr conceptual)
            direction = 'increase' if mean_dbg > 0.3 else 'decrease' if mean_dbg < -0.3 else 'ok'

            period_results[pname] = {
                'mean_fasting_dbg': mean_dbg,
                'std': float(np.std(fdbg[v])),
                'n': int(np.sum(v)),
                'recommendation': direction,
            }

        if not period_results:
            continue

        # Worst period
        worst = max(period_results, key=lambda p: abs(period_results[p]['mean_fasting_dbg']))
        needs_adjustment = [p for p, r in period_results.items() if r['recommendation'] != 'ok']

        results[name] = {
            'periods': period_results,
            'worst_period': worst,
            'needs_adjustment': needs_adjustment,
            'n_adjustments': len(needs_adjustment),
        }

        if detail:
            parts = [f"{p}:{r['mean_fasting_dbg']:+.2f}({r['recommendation']})"
                    for p, r in period_results.items()]
            print(f"  {name}: {', '.join(parts)}, needs adjust: {needs_adjustment}")

    adj_counts = [r['n_adjustments'] for r in results.values()]
    worst_periods = [r['worst_period'] for r in results.values()]
    wp_counts = {w: worst_periods.count(w) for w in set(worst_periods)}

    summary = {
        'experiment': 'EXP-582',
        'name': 'Per-Period Basal Decomposition',
        'mean_adjustments': float(np.mean(adj_counts)) if adj_counts else 0,
        'worst_period_counts': wp_counts,
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-582 Summary: mean adjustments={np.mean(adj_counts):.1f}, "
              f"worst periods={wp_counts}")
    return summary


# ──────────────────────────────────────────────
# EXP-583: Correction Event Taxonomy
# ──────────────────────────────────────────────
def exp583_correction_taxonomy(patients, detail=False):
    """Cluster corrections by magnitude, timing, and BG response."""
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
        carb_supply = flux.get('carb_supply', flux['supply'])

        valid = np.isfinite(bg) & np.isfinite(demand)
        bg_v = bg[valid]
        demand_v = demand[valid]
        carb_v = carb_supply[valid]
        N = len(bg_v)
        if N < 500:
            continue

        # Detect correction events: high demand (>75th percentile), BG > 150, low carbs
        demand_thresh = np.percentile(demand_v[demand_v > 0], 75) if np.sum(demand_v > 0) > 0 else 0.1
        correction_starts = []
        in_correction = False

        for i in range(N):
            if demand_v[i] > demand_thresh and bg_v[i] > 150 and carb_v[i] < 0.1:
                if not in_correction:
                    correction_starts.append(i)
                    in_correction = True
            else:
                if in_correction and (demand_v[i] < demand_thresh * 0.5 or bg_v[i] < 120):
                    in_correction = False

        if len(correction_starts) < 10:
            continue

        # Classify each correction
        fast_returns = 0  # BG < 150 within 1h
        slow_returns = 0  # BG < 150 within 2h
        failed = 0        # BG still > 150 at 2h
        overcorrections = 0  # BG < 80 within 2h

        bg_drops = []
        return_times = []

        for start in correction_starts:
            bg_start = bg_v[start]
            for dt in range(1, min(24, N - start)):
                bg_now = bg_v[start + dt]
                if bg_now < 150:
                    return_times.append(dt * 5)
                    if dt <= 12:
                        fast_returns += 1
                    else:
                        slow_returns += 1
                    break
                if bg_now < 80:
                    overcorrections += 1
                    break
            else:
                failed += 1

            # 2h BG drop
            end_idx = min(start + 24, N - 1)
            bg_drops.append(bg_start - bg_v[end_idx])

        total = len(correction_starts)
        results[name] = {
            'n_corrections': total,
            'fast_return_pct': float(fast_returns / total),
            'slow_return_pct': float(slow_returns / total),
            'failed_pct': float(failed / total),
            'overcorrection_pct': float(overcorrections / total),
            'mean_bg_drop': float(np.mean(bg_drops)),
            'median_return_min': float(np.median(return_times)) if return_times else 120,
        }

        if detail:
            print(f"  {name}: {total} corrections, fast={fast_returns / total:.0%}, "
                  f"slow={slow_returns / total:.0%}, failed={failed / total:.0%}, "
                  f"overcorr={overcorrections / total:.0%}, "
                  f"median return={np.median(return_times) if return_times else 120:.0f}min")

    summary = {
        'experiment': 'EXP-583',
        'name': 'Correction Event Taxonomy',
        'mean_fast_return': float(np.mean([r['fast_return_pct'] for r in results.values()])),
        'mean_failed': float(np.mean([r['failed_pct'] for r in results.values()])),
        'patients': results,
    }
    if detail:
        fast = np.mean([r['fast_return_pct'] for r in results.values()])
        failed = np.mean([r['failed_pct'] for r in results.values()])
        print(f"\n  EXP-583 Summary: fast return={fast:.0%}, failed={failed:.0%}")
    return summary


# ──────────────────────────────────────────────
# EXP-584: Biweekly Settings Tracking
# ──────────────────────────────────────────────
def exp584_biweekly_tracking(patients, detail=False):
    """Track settings score at 2-week intervals for temporal resolution."""
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

        period_len = 4032  # 14 days * 288
        n_periods = N // period_len
        if n_periods < 3:
            continue

        period_scores = []
        period_tirs = []

        for m in range(n_periods):
            s = m * period_len
            e = s + period_len
            bg_m = bg_v[s:e]
            dbg_m = _compute_dbg(bg_m)
            supply_m = supply[valid][s:e]
            demand_m = demand[valid][s:e]
            hepatic_m = hepatic[valid][s:e]
            net_m = net[valid][s:e]
            carb_m = carb_supply[valid][s:e]

            split_m = int(0.8 * period_len)
            model = _fit_flux_ar(bg_m, supply_m, demand_m, hepatic_m, split_m)
            if model is None:
                period_scores.append(np.nan)
                period_tirs.append(np.nan)
                continue

            score, tir = _compute_settings_score(bg_m, dbg_m, model['combined_resid'],
                                                  net_m, carb_m, period_len)
            period_scores.append(score)
            period_tirs.append(tir)

        scores = np.array(period_scores)
        tirs = np.array(period_tirs)
        v = np.isfinite(scores)

        if np.sum(v) < 3:
            continue

        # Trend analysis
        x = np.arange(len(scores))[v]
        slope, intercept, r, p_val, _ = stats.linregress(x, scores[v])
        tir_slope, _, tir_r, tir_p, _ = stats.linregress(x, tirs[v])

        # Score stability (CV)
        score_cv = float(np.std(scores[v]) / np.mean(scores[v])) if np.mean(scores[v]) > 0 else 0

        results[name] = {
            'n_periods': int(np.sum(v)),
            'scores': [float(s) if np.isfinite(s) else None for s in scores],
            'tirs': [float(t) if np.isfinite(t) else None for t in tirs],
            'score_trend': float(slope),
            'score_trend_p': float(p_val),
            'tir_trend': float(tir_slope),
            'tir_trend_p': float(tir_p),
            'score_cv': score_cv,
            'improving': bool(slope > 0 and p_val < 0.1),
            'declining': bool(slope < 0 and p_val < 0.1),
        }

        if detail:
            trend = "↑" if slope > 0 else "↓"
            sig = "*" if p_val < 0.1 else ""
            print(f"  {name}: {int(np.sum(v))} periods, score trend={slope:+.2f}{trend}{sig}, "
                  f"CV={score_cv:.2f}, mean={np.mean(scores[v]):.1f}")

    trends = [r['score_trend'] for r in results.values()]
    cvs = [r['score_cv'] for r in results.values()]
    improving = sum(1 for r in results.values() if r['improving'])
    declining = sum(1 for r in results.values() if r['declining'])

    summary = {
        'experiment': 'EXP-584',
        'name': 'Biweekly Settings Tracking',
        'mean_score_trend': float(np.mean(trends)) if trends else 0,
        'mean_cv': float(np.mean(cvs)) if cvs else 0,
        'improving': improving,
        'declining': declining,
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-584 Summary: mean trend={np.mean(trends):+.2f}, "
              f"CV={np.mean(cvs):.2f}, improving={improving}, declining={declining}")
    return summary


# ──────────────────────────────────────────────
# EXP-585: 90-Day Rolling A1c Proxy
# ──────────────────────────────────────────────
def exp585_rolling_a1c(patients, detail=False):
    """Compare 90-day rolling correction energy with GMI (glucose management indicator)."""
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
        demand = flux['demand']

        valid = np.isfinite(bg) & np.isfinite(net)
        bg_v = bg[valid]
        demand_v = demand[valid]
        net_v = net[valid]
        N = len(bg_v)

        if N < 288 * 30:  # Need at least 30 days
            continue

        # Compute daily metrics
        day_len = 288
        n_days = N // day_len

        daily_mean_bg = []
        daily_correction_energy = []
        daily_tir = []

        for d in range(n_days):
            s = d * day_len
            e = s + day_len
            bg_d = bg_v[s:e]
            net_d = net_v[s:e]
            demand_d = demand_v[s:e]

            v = np.isfinite(bg_d)
            daily_mean_bg.append(np.mean(bg_d[v]) if np.sum(v) > 0 else np.nan)

            # Correction energy = sum of |net flux| when BG out of range
            out_of_range = (bg_d > 180) | (bg_d < 70)
            v2 = v & np.isfinite(net_d)
            ce = np.sum(np.abs(net_d[v2 & out_of_range])) if np.sum(v2 & out_of_range) > 0 else 0
            daily_correction_energy.append(ce)

            tir = np.sum((bg_d[v] >= 70) & (bg_d[v] <= 180)) / np.sum(v) if np.sum(v) > 0 else np.nan
            daily_tir.append(tir)

        daily_bg = np.array(daily_mean_bg)
        daily_ce = np.array(daily_correction_energy)
        daily_tir_arr = np.array(daily_tir)

        # 90-day rolling averages
        window = 90
        if n_days < window:
            window = n_days

        rolling_gmi = []
        rolling_ce = []
        rolling_tir = []

        for d in range(window, n_days):
            w_bg = daily_bg[d - window:d]
            w_ce = daily_ce[d - window:d]
            w_tir = daily_tir_arr[d - window:d]

            v = np.isfinite(w_bg)
            if np.sum(v) < 30:
                continue

            mean_bg = np.mean(w_bg[v])
            # GMI formula: eA1c = (46.7 + mean_bg) / 28.7  (for mg/dL)
            gmi = (46.7 + mean_bg) / 28.7

            rolling_gmi.append(gmi)
            rolling_ce.append(np.mean(w_ce[np.isfinite(w_ce)]))
            rolling_tir.append(np.mean(w_tir[np.isfinite(w_tir)]))

        if len(rolling_gmi) < 5:
            continue

        gmi_arr = np.array(rolling_gmi)
        ce_arr = np.array(rolling_ce)
        tir_arr = np.array(rolling_tir)

        # Correlations
        r_ce_gmi, p_ce_gmi = stats.spearmanr(ce_arr, gmi_arr)
        r_tir_gmi, p_tir_gmi = stats.spearmanr(tir_arr, gmi_arr)

        results[name] = {
            'n_rolling_points': len(rolling_gmi),
            'gmi_range': [float(np.min(gmi_arr)), float(np.max(gmi_arr))],
            'gmi_mean': float(np.mean(gmi_arr)),
            'r_ce_gmi': float(r_ce_gmi),
            'p_ce_gmi': float(p_ce_gmi),
            'r_tir_gmi': float(r_tir_gmi),
            'p_tir_gmi': float(p_tir_gmi),
            'ce_mean': float(np.mean(ce_arr)),
        }

        if detail:
            print(f"  {name}: GMI={np.mean(gmi_arr):.1f}% ({np.min(gmi_arr):.1f}-{np.max(gmi_arr):.1f}), "
                  f"r(CE,GMI)={r_ce_gmi:.3f}, r(TIR,GMI)={r_tir_gmi:.3f}")

    summary = {
        'experiment': 'EXP-585',
        'name': '90-Day Rolling A1c Proxy',
        'mean_gmi': float(np.mean([r['gmi_mean'] for r in results.values()])),
        'mean_r_ce_gmi': float(np.mean([r['r_ce_gmi'] for r in results.values()])),
        'mean_r_tir_gmi': float(np.mean([r['r_tir_gmi'] for r in results.values()])),
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-585 Summary: mean GMI={summary['mean_gmi']:.1f}%, "
              f"r(CE,GMI)={summary['mean_r_ce_gmi']:.3f}, r(TIR,GMI)={summary['mean_r_tir_gmi']:.3f}")
    return summary


# ──────────────────────────────────────────────
# EXP-587: Meal-Aware Kalman
# ──────────────────────────────────────────────
def exp587_meal_kalman(patients, detail=False):
    """Increase Q during post-meal windows for adaptive Kalman."""
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
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
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
        combined_resid = model['combined_resid']

        # Compute meal state
        carb_v = carb_supply[valid]
        carb_thresh = np.percentile(carb_v[carb_v > 0], 25) if np.sum(carb_v > 0) > 0 else 0.01

        # Post-meal window: 24 steps (2h) after carb activity
        post_meal = np.zeros(N, dtype=bool)
        last_carb = -999
        for i in range(N):
            if carb_v[i] > carb_thresh:
                last_carb = i
            if 0 <= i - last_carb <= 24:
                post_meal[i] = True

        # Training innovation variance
        train_resid = combined_resid[:split]
        v_train = np.isfinite(train_resid)
        global_var = np.var(train_resid[v_train])

        meal_resid = train_resid[v_train & post_meal[:split]]
        fast_resid = train_resid[v_train & ~post_meal[:split]]
        meal_var = np.var(meal_resid) if len(meal_resid) > 50 else global_var
        fast_var = np.var(fast_resid) if len(fast_resid) > 50 else global_var

        def run_kalman(q_func, r_func):
            bg_est = bg_v[split]
            P = r_func(False)
            preds = []
            resid_hist = list(flux_resid[split - ar_order:split])

            for t in range(split, N):
                is_meal = post_meal[t]
                Q = q_func(is_meal)
                R = r_func(is_meal)

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
        global_preds = run_kalman(lambda m: global_var * 0.8, lambda m: global_var * 0.2)

        # Meal-aware Kalman: higher Q during meals (more trust in observations)
        meal_q_mult = meal_var / fast_var if fast_var > 0 else 1.5
        meal_preds = run_kalman(
            lambda m: (meal_var if m else fast_var) * 0.8,
            lambda m: (meal_var if m else fast_var) * 0.2
        )

        # Evaluate
        actual_test = bg_v[split:]
        persist_test = np.concatenate([[bg_v[split - 1]], bg_v[split:-1]])

        v_test = np.isfinite(global_preds) & np.isfinite(meal_preds) & np.isfinite(actual_test)
        if np.sum(v_test) < 20:
            continue

        mse_global = np.mean((global_preds[v_test] - actual_test[v_test]) ** 2)
        mse_meal = np.mean((meal_preds[v_test] - actual_test[v_test]) ** 2)
        mse_persist = np.mean((persist_test[v_test] - actual_test[v_test]) ** 2)

        skill_global = 1 - mse_global / mse_persist if mse_persist > 0 else 0
        skill_meal = 1 - mse_meal / mse_persist if mse_persist > 0 else 0

        # Evaluate only on post-meal test points
        post_meal_test = post_meal[split:]
        v_meal_test = v_test & post_meal_test
        if np.sum(v_meal_test) > 20:
            mse_global_meal = np.mean((global_preds[v_meal_test] - actual_test[v_meal_test]) ** 2)
            mse_meal_meal = np.mean((meal_preds[v_meal_test] - actual_test[v_meal_test]) ** 2)
            meal_improvement = (mse_global_meal - mse_meal_meal) / mse_global_meal if mse_global_meal > 0 else 0
        else:
            meal_improvement = 0

        results[name] = {
            'skill_global': float(skill_global),
            'skill_meal_aware': float(skill_meal),
            'improvement': float(skill_meal - skill_global),
            'meal_only_improvement': float(meal_improvement),
            'meal_q_multiplier': float(meal_q_mult),
        }

        if detail:
            print(f"  {name}: global={skill_global:.3f}, meal_aware={skill_meal:.3f}, "
                  f"Δ={skill_meal - skill_global:+.4f}, meal_q_mult={meal_q_mult:.2f}")

    imps = [r['improvement'] for r in results.values()]
    summary = {
        'experiment': 'EXP-587',
        'name': 'Meal-Aware Kalman',
        'mean_improvement': float(np.mean(imps)) if imps else 0,
        'mean_skill_global': float(np.mean([r['skill_global'] for r in results.values()])),
        'mean_skill_meal': float(np.mean([r['skill_meal_aware'] for r in results.values()])),
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-587 Summary: global={summary['mean_skill_global']:.3f}, "
              f"meal_aware={summary['mean_skill_meal']:.3f}, Δ={np.mean(imps):+.4f}")
    return summary


# ──────────────────────────────────────────────
# EXP-588: BG-Range Stratified Performance
# ──────────────────────────────────────────────
def exp588_bg_range_performance(patients, detail=False):
    """Evaluate model accuracy by BG range (hypo, normal, hyper)."""
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

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        N = len(bg_v)
        if N < 500:
            continue

        split = int(0.8 * N)
        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        dbg = model['dbg']

        ranges = {
            'hypo': (0, 70),
            'low_normal': (70, 100),
            'normal': (100, 180),
            'high': (180, 250),
            'very_high': (250, 500),
        }

        range_results = {}
        for rname, (lo, hi) in ranges.items():
            mask = (bg_v >= lo) & (bg_v < hi) & np.isfinite(resid)
            n_points = int(np.sum(mask))
            if n_points < 20:
                continue

            r = resid[mask]
            d = dbg[mask]

            # R² in this range
            ss_res = np.sum(r ** 2)
            ss_tot = np.sum((d - np.mean(d)) ** 2) if np.var(d) > 0 else 1
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            range_results[rname] = {
                'n': n_points,
                'fraction': float(n_points / np.sum(np.isfinite(resid))),
                'resid_mean': float(np.mean(r)),
                'resid_std': float(np.std(r)),
                'r2': float(r2),
                'bias': float(np.mean(r)),
            }

        # Find worst and best ranges
        ranges_with_r2 = {k: v['r2'] for k, v in range_results.items()}
        worst = min(ranges_with_r2, key=ranges_with_r2.get) if ranges_with_r2 else 'N/A'
        best = max(ranges_with_r2, key=ranges_with_r2.get) if ranges_with_r2 else 'N/A'

        results[name] = {
            'ranges': range_results,
            'worst_range': worst,
            'best_range': best,
        }

        if detail:
            parts = [f"{r}:R²={s['r2']:.3f}(n={s['n']})" for r, s in range_results.items()]
            print(f"  {name}: {', '.join(parts)}")

    worst_ranges = [r['worst_range'] for r in results.values()]
    wr_counts = {w: worst_ranges.count(w) for w in set(worst_ranges)}

    summary = {
        'experiment': 'EXP-588',
        'name': 'BG-Range Stratified Performance',
        'worst_range_counts': wr_counts,
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-588 Summary: worst ranges={wr_counts}")
    return summary


# ──────────────────────────────────────────────
# EXP-590: Anomaly Detection — Score Drops
# ──────────────────────────────────────────────
def exp590_anomaly_detection(patients, detail=False):
    """Detect settings score drops preceding severe hypo/hyper events."""
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

        # 3-day rolling windows
        window = 864  # 3 days * 288
        if N < window * 3:
            continue

        rolling_scores = []
        rolling_hypo_count = []
        rolling_hyper_count = []

        step = 288  # 1-day step
        for i in range(0, N - window, step):
            bg_w = bg_v[i:i + window]
            dbg_w = _compute_dbg(bg_w)
            supply_w = supply[valid][i:i + window]
            demand_w = demand[valid][i:i + window]
            hepatic_w = hepatic[valid][i:i + window]
            net_w = net[valid][i:i + window]
            carb_w = carb_supply[valid][i:i + window]

            split_w = int(0.8 * window)
            model = _fit_flux_ar(bg_w, supply_w, demand_w, hepatic_w, split_w)
            if model is None:
                rolling_scores.append(np.nan)
                rolling_hypo_count.append(0)
                rolling_hyper_count.append(0)
                continue

            score, _ = _compute_settings_score(bg_w, dbg_w, model['combined_resid'],
                                                net_w, carb_w, window)
            rolling_scores.append(score)

            # Count severe events in NEXT 3 days
            next_start = i + window
            next_end = min(next_start + window, N)
            if next_end > next_start:
                next_bg = bg_v[next_start:next_end]
                hypo_events = np.sum(next_bg < 54)  # Severe hypo
                hyper_events = np.sum(next_bg > 300)  # Severe hyper
            else:
                hypo_events = 0
                hyper_events = 0

            rolling_hypo_count.append(int(hypo_events))
            rolling_hyper_count.append(int(hyper_events))

        scores_arr = np.array(rolling_scores)
        hypo_arr = np.array(rolling_hypo_count)
        hyper_arr = np.array(rolling_hyper_count)

        v = np.isfinite(scores_arr) & (hypo_arr + hyper_arr >= 0)
        if np.sum(v) < 5:
            continue

        # Score drops: where score decreases by >10 from previous
        score_changes = np.diff(scores_arr[v])
        drops = score_changes < -5

        # Do score drops precede more adverse events?
        if len(drops) < 3:
            continue

        post_drop_events = hypo_arr[v][1:][drops].sum() + hyper_arr[v][1:][drops].sum()
        post_stable_events = hypo_arr[v][1:][~drops].sum() + hyper_arr[v][1:][~drops].sum()

        n_drops = int(np.sum(drops))
        n_stable = int(np.sum(~drops))

        drop_rate = post_drop_events / n_drops if n_drops > 0 else 0
        stable_rate = post_stable_events / n_stable if n_stable > 0 else 0

        results[name] = {
            'n_windows': int(np.sum(v)),
            'n_drops': n_drops,
            'drop_event_rate': float(drop_rate),
            'stable_event_rate': float(stable_rate),
            'event_ratio': float(drop_rate / stable_rate) if stable_rate > 0 else np.nan,
            'total_hypo_54': int(hypo_arr.sum()),
            'total_hyper_300': int(hyper_arr.sum()),
        }

        if detail:
            ratio = drop_rate / stable_rate if stable_rate > 0 else 0
            print(f"  {name}: {n_drops} drops, event rate: drop={drop_rate:.1f} vs stable={stable_rate:.1f}, "
                  f"ratio={ratio:.2f}")

    ratios = [r['event_ratio'] for r in results.values() if np.isfinite(r.get('event_ratio', np.nan))]
    summary = {
        'experiment': 'EXP-590',
        'name': 'Anomaly Detection Score Drops',
        'mean_event_ratio': float(np.mean(ratios)) if ratios else 0,
        'patients': results,
    }
    if detail:
        print(f"\n  EXP-590 Summary: mean event ratio (drop vs stable)={np.mean(ratios):.2f}")
    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-581-590 autoresearch')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps = args.experiments.split(',') if args.experiments != 'all' else \
        ['581', '582', '583', '584', '585', '587', '588', '590']

    all_results = {}

    if '581' in exps:
        print("\n=== EXP-581: Score Predicts Future TIR ===")
        all_results['exp581'] = exp581_score_predicts_tir(patients, args.detail)

    if '582' in exps:
        print("\n=== EXP-582: Per-Period Basal Decomposition ===")
        all_results['exp582'] = exp582_basal_periods(patients, args.detail)

    if '583' in exps:
        print("\n=== EXP-583: Correction Event Taxonomy ===")
        all_results['exp583'] = exp583_correction_taxonomy(patients, args.detail)

    if '584' in exps:
        print("\n=== EXP-584: Biweekly Settings Tracking ===")
        all_results['exp584'] = exp584_biweekly_tracking(patients, args.detail)

    if '585' in exps:
        print("\n=== EXP-585: 90-Day Rolling A1c Proxy ===")
        all_results['exp585'] = exp585_rolling_a1c(patients, args.detail)

    if '587' in exps:
        print("\n=== EXP-587: Meal-Aware Kalman ===")
        all_results['exp587'] = exp587_meal_kalman(patients, args.detail)

    if '588' in exps:
        print("\n=== EXP-588: BG-Range Stratified Performance ===")
        all_results['exp588'] = exp588_bg_range_performance(patients, args.detail)

    if '590' in exps:
        print("\n=== EXP-590: Anomaly Detection ===")
        all_results['exp590'] = exp590_anomaly_detection(patients, args.detail)

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
