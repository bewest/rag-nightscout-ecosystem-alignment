#!/usr/bin/env python3
"""EXP-571–580: Meal absorption deep dive, settings optimization from flux,
and multi-week/month analysis.

Building on 57 experiments (EXP-511–570):
  - Residuals are WHITE NOISE (EXP-570) — no temporal structure remains
  - Meal absorption variability is 1.45× fasting (EXP-568) — largest unknown source
  - Circadian mismatch: morning/overnight worst (EXP-560)
  - Monthly model stable at R²=0.657 (EXP-555)
  - Correction energy ↔ TIR: r=-0.35 (EXP-559)

This wave:
  1. Meal absorption deep dive (EXP-571/572/573)
  2. Settings optimization from flux (EXP-574/575/576)
  3. Multi-week/month analysis (EXP-577/578/579/580)
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


def _detect_meal_events(carb_supply, bg_v, valid_mask, min_gap=12):
    """Detect meal events as contiguous blocks of carb_supply > threshold.
    Returns list of (start_idx, peak_idx, end_idx) into valid-only arrays.
    min_gap: minimum 5-min steps between meals (default 60 min).
    """
    carb_pos = carb_supply[carb_supply > 0]
    if len(carb_pos) < 10:
        return []
    thresh = np.percentile(carb_pos, 25)

    N = len(carb_supply)
    meals = []
    in_meal = False
    start = 0
    peak_val = 0
    peak_idx = 0

    for i in range(N):
        if carb_supply[i] > thresh:
            if not in_meal:
                start = i
                in_meal = True
                peak_val = carb_supply[i]
                peak_idx = i
            else:
                if carb_supply[i] > peak_val:
                    peak_val = carb_supply[i]
                    peak_idx = i
        else:
            if in_meal:
                # Check gap — if next carb spike is within min_gap, continue meal
                if i + min_gap < N and np.any(carb_supply[i:i + min_gap] > thresh):
                    continue
                meals.append((start, peak_idx, i))
                in_meal = False

    if in_meal:
        meals.append((start, peak_idx, N - 1))

    return meals


# ──────────────────────────────────────────────
# EXP-571: Meal Size vs Residual
# ──────────────────────────────────────────────
def exp571_meal_size_residual(patients, detail=False):
    """Correlate announced carb size with post-meal residual magnitude."""
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
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        N = len(bg_v)
        split = int(0.8 * N)

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        carb_v = carb_supply[valid]

        meals = _detect_meal_events(carb_v, bg_v, np.ones(N, dtype=bool))
        if len(meals) < 10:
            continue

        # For each meal: compute meal size (integral of carb_supply) and
        # post-meal residual statistics (next 2 hours = 24 steps)
        meal_sizes = []
        meal_resid_mags = []
        meal_resid_means = []
        meal_bg_excursions = []

        for start, peak, end in meals:
            # Meal size = integral of carb supply during meal
            meal_size = np.sum(carb_v[start:end + 1])
            if meal_size < 0.1:
                continue

            # Post-meal window: peak to peak+24 steps (2h)
            post_start = peak
            post_end = min(peak + 24, N)
            if post_end - post_start < 6:
                continue

            post_resid = resid[post_start:post_end]
            valid_resid = np.isfinite(post_resid)
            if np.sum(valid_resid) < 3:
                continue

            meal_sizes.append(meal_size)
            meal_resid_mags.append(float(np.std(post_resid[valid_resid])))
            meal_resid_means.append(float(np.mean(post_resid[valid_resid])))

            # BG excursion
            bg_post = bg_v[post_start:post_end]
            bg_excursion = np.max(bg_post) - bg_post[0] if len(bg_post) > 1 else 0
            meal_bg_excursions.append(float(bg_excursion))

        if len(meal_sizes) < 10:
            continue

        meal_sizes = np.array(meal_sizes)
        meal_resid_mags = np.array(meal_resid_mags)
        meal_resid_means = np.array(meal_resid_means)
        meal_bg_excursions = np.array(meal_bg_excursions)

        # Correlations
        r_size_resid, p_size_resid = stats.spearmanr(meal_sizes, meal_resid_mags)
        r_size_excur, p_size_excur = stats.spearmanr(meal_sizes, meal_bg_excursions)

        # Quartile analysis
        q25, q50, q75 = np.percentile(meal_sizes, [25, 50, 75])
        small_resid = meal_resid_mags[meal_sizes <= q25]
        large_resid = meal_resid_mags[meal_sizes >= q75]

        results[name] = {
            'n_meals': len(meal_sizes),
            'r_size_vs_resid_std': float(r_size_resid),
            'p_size_vs_resid_std': float(p_size_resid),
            'r_size_vs_excursion': float(r_size_excur),
            'p_size_vs_excursion': float(p_size_excur),
            'mean_small_meal_resid': float(np.mean(small_resid)),
            'mean_large_meal_resid': float(np.mean(large_resid)),
            'large_to_small_ratio': float(np.mean(large_resid) / np.mean(small_resid))
            if np.mean(small_resid) > 0 else 1.0,
            'meal_size_q50': float(q50),
        }

        if detail:
            sig = "*" if p_size_resid < 0.05 else ""
            print(f"  {name}: {len(meal_sizes)} meals, r(size,resid)={r_size_resid:.3f}{sig}, "
                  f"r(size,excur)={r_size_excur:.3f}, "
                  f"large/small resid={np.mean(large_resid) / np.mean(small_resid):.2f}×")

    rs = [r['r_size_vs_resid_std'] for r in results.values()]
    ratios = [r['large_to_small_ratio'] for r in results.values()]
    sig_count = sum(1 for r in results.values() if r['p_size_vs_resid_std'] < 0.05)

    summary = {
        'experiment': 'EXP-571',
        'name': 'Meal Size vs Residual',
        'mean_r_size_resid': float(np.mean(rs)) if rs else 0,
        'mean_large_small_ratio': float(np.mean(ratios)) if ratios else 0,
        'sig_count': sig_count,
        'total': len(results),
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-571 Summary: mean r(size,resid)={np.mean(rs):.3f}, "
              f"large/small={np.mean(ratios):.2f}×, {sig_count}/{len(results)} sig")

    return summary


# ──────────────────────────────────────────────
# EXP-572: Meal Time-of-Day Effect
# ──────────────────────────────────────────────
def exp572_meal_tod(patients, detail=False):
    """Compare meal residual profiles by meal timing."""
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
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        N = len(bg_v)
        split = int(0.8 * N)

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        carb_v = carb_supply[valid]

        meals = _detect_meal_events(carb_v, bg_v, np.ones(N, dtype=bool))
        if len(meals) < 10:
            continue

        idx_valid = np.where(valid)[0]

        # Classify meals by time of day
        period_resids = {
            'breakfast': [],   # 06-10
            'lunch': [],       # 10-14
            'afternoon': [],   # 14-18
            'dinner': [],      # 18-22
            'late_night': [],  # 22-06
        }

        for start, peak, end in meals:
            # Determine time of day from index position
            tod_bin = idx_valid[peak] % 288 if peak < len(idx_valid) else 0
            hour = (tod_bin * 5) / 60.0

            if 6 <= hour < 10:
                period = 'breakfast'
            elif 10 <= hour < 14:
                period = 'lunch'
            elif 14 <= hour < 18:
                period = 'afternoon'
            elif 18 <= hour < 22:
                period = 'dinner'
            else:
                period = 'late_night'

            # Post-meal residual (2h window)
            post_end = min(peak + 24, N)
            if post_end - peak < 6:
                continue
            post_resid = resid[peak:post_end]
            valid_r = np.isfinite(post_resid)
            if np.sum(valid_r) < 3:
                continue

            period_resids[period].append({
                'std': float(np.std(post_resid[valid_r])),
                'mean': float(np.mean(post_resid[valid_r])),
                'peak_resid': float(np.max(np.abs(post_resid[valid_r]))),
            })

        period_stats = {}
        for pname, meals_in_period in period_resids.items():
            if len(meals_in_period) >= 5:
                stds = [m['std'] for m in meals_in_period]
                means = [m['mean'] for m in meals_in_period]
                period_stats[pname] = {
                    'n': len(meals_in_period),
                    'mean_std': float(np.mean(stds)),
                    'mean_bias': float(np.mean(means)),
                    'std_of_std': float(np.std(stds)),
                }

        if len(period_stats) < 2:
            continue

        # Find worst and best periods
        worst = max(period_stats, key=lambda p: period_stats[p]['mean_std'])
        best = min(period_stats, key=lambda p: period_stats[p]['mean_std'])
        ratio = period_stats[worst]['mean_std'] / period_stats[best]['mean_std'] \
            if period_stats[best]['mean_std'] > 0 else 1.0

        results[name] = {
            'period_stats': period_stats,
            'worst_period': worst,
            'best_period': best,
            'worst_to_best_ratio': float(ratio),
        }

        if detail:
            parts = [f"{p}:{s['mean_std']:.1f}({s['n']})" for p, s in period_stats.items()]
            print(f"  {name}: {', '.join(parts)}, worst={worst}, ratio={ratio:.2f}")

    worsts = [r['worst_period'] for r in results.values()]
    ratios = [r['worst_to_best_ratio'] for r in results.values()]
    worst_counts = {w: worsts.count(w) for w in set(worsts)}

    summary = {
        'experiment': 'EXP-572',
        'name': 'Meal Time-of-Day Effect',
        'mean_worst_best_ratio': float(np.mean(ratios)) if ratios else 0,
        'worst_period_counts': worst_counts,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-572 Summary: worst periods={worst_counts}, "
              f"mean worst/best ratio={np.mean(ratios):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-573: Fat/Protein Extended Absorption Tail
# ──────────────────────────────────────────────
def exp573_fat_protein_tail(patients, detail=False):
    """Detect extended absorption (>3h) as positive residual runs post-meal."""
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
        carb_supply = flux.get('carb_supply', supply)

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        N = len(bg_v)
        split = int(0.8 * N)

        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue

        resid = model['combined_resid']
        carb_v = carb_supply[valid]

        meals = _detect_meal_events(carb_v, bg_v, np.ones(N, dtype=bool))
        if len(meals) < 10:
            continue

        # For each meal, look at residuals in windows:
        # acute: 0-1h (0-12 steps), mid: 1-3h (12-36 steps), tail: 3-6h (36-72 steps)
        tail_positive = 0
        tail_negative = 0
        tail_neutral = 0
        tail_means = []
        acute_means = []

        for start, peak, end in meals:
            for window_name, w_start, w_end in [
                ('acute', 0, 12), ('mid', 12, 36), ('tail', 36, 72)
            ]:
                ws = peak + w_start
                we = min(peak + w_end, N)
                if we - ws < 3:
                    continue
                w_resid = resid[ws:we]
                valid_r = np.isfinite(w_resid)
                if np.sum(valid_r) < 3:
                    continue
                mean_r = np.mean(w_resid[valid_r])

                if window_name == 'tail':
                    tail_means.append(mean_r)
                    if mean_r > 1.0:
                        tail_positive += 1
                    elif mean_r < -1.0:
                        tail_negative += 1
                    else:
                        tail_neutral += 1
                elif window_name == 'acute':
                    acute_means.append(mean_r)

        total_meals = tail_positive + tail_negative + tail_neutral
        if total_meals < 5:
            continue

        fat_protein_fraction = tail_positive / total_meals

        results[name] = {
            'n_meals': total_meals,
            'tail_positive': tail_positive,
            'tail_negative': tail_negative,
            'tail_neutral': tail_neutral,
            'fat_protein_fraction': float(fat_protein_fraction),
            'mean_tail_resid': float(np.mean(tail_means)) if tail_means else 0,
            'mean_acute_resid': float(np.mean(acute_means)) if acute_means else 0,
        }

        if detail:
            print(f"  {name}: {total_meals} meals, tail+={tail_positive}({fat_protein_fraction:.0%}), "
                  f"tail-={tail_negative}, neutral={tail_neutral}, "
                  f"mean_tail={np.mean(tail_means):.2f}")

    fps = [r['fat_protein_fraction'] for r in results.values()]
    tails = [r['mean_tail_resid'] for r in results.values()]

    summary = {
        'experiment': 'EXP-573',
        'name': 'Fat Protein Tail Detection',
        'mean_fat_protein_fraction': float(np.mean(fps)) if fps else 0,
        'mean_tail_resid': float(np.mean(tails)) if tails else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-573 Summary: mean fat/protein fraction={np.mean(fps):.0%}, "
              f"mean tail resid={np.mean(tails):+.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-574: Counterfactual ISF from Flux
# ──────────────────────────────────────────────
def exp574_counterfactual_isf(patients, detail=False):
    """Compare flux-derived ISF (from demand slope) vs profile ISF."""
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

        valid = np.isfinite(bg) & np.isfinite(demand)
        bg_v = bg[valid]
        demand_v = demand[valid]
        N = len(bg_v)
        if N < 500:
            continue

        dbg = _compute_dbg(bg_v)

        # Profile ISF from df.attrs (list of {time, value, timeAsSeconds} dicts)
        isf_schedule = df.attrs.get('isf_schedule', [])
        profile_isf = None
        if isf_schedule:
            isf_vals = [entry['value'] for entry in isf_schedule if isinstance(entry, dict) and entry.get('value', 0) > 0]
            if isf_vals:
                profile_isf = np.mean(isf_vals)
                # Convert mmol/L ISF to mg/dL if needed
                if profile_isf < 15:
                    profile_isf *= 18.0182

        # Flux-derived ISF: during correction periods (high BG, active insulin, no carbs)
        # ISF ≈ -dBG / demand_normalized
        # Where demand is already in insulin-activity units, we need the BG response
        high_bg = bg_v > 150
        active_demand = demand_v > np.percentile(demand_v[demand_v > 0], 50) if np.sum(demand_v > 0) > 0 else demand_v > 0
        low_carb = flux.get('carb_supply', flux['supply'])[valid] < 0.1
        correction_mask = high_bg & active_demand & low_carb & np.isfinite(dbg)

        if np.sum(correction_mask) < 50:
            continue

        # ISF proxy: how much does BG drop per unit of demand?
        # Simple: regress dBG on demand during correction periods
        demand_corr = demand_v[correction_mask]
        dbg_corr = dbg[correction_mask]

        try:
            slope, intercept, r_val, p_val, std_err = stats.linregress(demand_corr, dbg_corr)
        except Exception:
            continue

        # flux_isf = magnitude of BG change per demand unit
        flux_isf = abs(slope) if slope != 0 else 0

        # Time-of-day ISF variation
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288

        tod_isf = {}
        for period, (t0, t1) in [('overnight', (0, 72)), ('morning', (72, 144)),
                                   ('afternoon', (144, 216)), ('evening', (216, 288))]:
            mask = correction_mask & (tod >= t0) & (tod < t1)
            if np.sum(mask) > 20:
                d_period = demand_v[mask]
                dbg_period = dbg[mask]
                try:
                    s, _, _, _, _ = stats.linregress(d_period, dbg_period)
                    tod_isf[period] = float(abs(s))
                except Exception:
                    pass

        isf_ratio = flux_isf / profile_isf if profile_isf and profile_isf > 0 else None

        results[name] = {
            'profile_isf': float(profile_isf) if profile_isf else None,
            'flux_isf': float(flux_isf),
            'isf_ratio': float(isf_ratio) if isf_ratio is not None else None,
            'regression_r2': float(r_val ** 2),
            'regression_p': float(p_val),
            'n_correction_points': int(np.sum(correction_mask)),
            'tod_isf': tod_isf,
        }

        if detail:
            ratio_str = f", ratio={isf_ratio:.2f}" if isf_ratio is not None else ""
            prof_str = f"profile={profile_isf:.0f}" if profile_isf else "profile=N/A"
            print(f"  {name}: {prof_str}, flux={flux_isf:.1f}, R²={r_val ** 2:.3f}{ratio_str}")

    ratios = [r['isf_ratio'] for r in results.values() if r['isf_ratio'] is not None]
    r2s = [r['regression_r2'] for r in results.values()]

    summary = {
        'experiment': 'EXP-574',
        'name': 'Counterfactual ISF from Flux',
        'mean_isf_ratio': float(np.mean(ratios)) if ratios else 0,
        'mean_r2': float(np.mean(r2s)) if r2s else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-574 Summary: mean ISF ratio={np.mean(ratios):.2f}, "
              f"mean R²={np.mean(r2s):.3f}")

    return summary


# ──────────────────────────────────────────────
# EXP-575: Counterfactual CR from Flux
# ──────────────────────────────────────────────
def exp575_counterfactual_cr(patients, detail=False):
    """Compare flux-derived CR (from supply response) vs profile CR."""
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
        carb_supply = flux.get('carb_supply', supply)
        demand = flux['demand']

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        carb_v = carb_supply[valid]
        demand_v = demand[valid]
        N = len(bg_v)
        if N < 500:
            continue

        dbg = _compute_dbg(bg_v)

        # Profile CR from df.attrs (list of {time, value, timeAsSeconds} dicts)
        cr_schedule = df.attrs.get('cr_schedule', [])
        profile_cr = None
        if cr_schedule:
            cr_vals = [entry['value'] for entry in cr_schedule if isinstance(entry, dict) and entry.get('value', 0) > 0]
            if cr_vals:
                profile_cr = np.mean(cr_vals)

        meals = _detect_meal_events(carb_v, bg_v, np.ones(N, dtype=bool))
        if len(meals) < 5:
            continue

        # For each meal: compute carb supply integral and BG excursion
        meal_carb_integrals = []
        meal_bg_rises = []
        meal_demand_integrals = []

        for start, peak, end in meals:
            carb_integral = np.sum(carb_v[start:end + 1])
            if carb_integral < 0.1:
                continue

            # BG rise in first 2h post-meal
            post_end = min(peak + 24, N)
            if post_end - peak < 6:
                continue
            bg_post = bg_v[peak:post_end]
            bg_rise = np.max(bg_post) - bg_post[0]

            # Demand integral (insulin delivered)
            demand_integral = np.sum(demand_v[start:post_end])

            meal_carb_integrals.append(carb_integral)
            meal_bg_rises.append(bg_rise)
            meal_demand_integrals.append(demand_integral)

        if len(meal_carb_integrals) < 5:
            continue

        carb_arr = np.array(meal_carb_integrals)
        rise_arr = np.array(meal_bg_rises)
        demand_arr = np.array(meal_demand_integrals)

        # Flux CR: how much BG rises per unit of carb supply
        r_cr, p_cr = stats.spearmanr(carb_arr, rise_arr)

        # Effective CR ratio: compare supply/demand energy balance
        # If CR is correct, the supply energy should match demand energy per meal
        energy_ratios = carb_arr / demand_arr
        energy_ratios = energy_ratios[np.isfinite(energy_ratios) & (energy_ratios > 0)]

        results[name] = {
            'profile_cr': float(profile_cr) if profile_cr else None,
            'n_meals': len(carb_arr),
            'r_carb_vs_rise': float(r_cr),
            'p_carb_vs_rise': float(p_cr),
            'mean_bg_rise': float(np.mean(rise_arr)),
            'median_energy_ratio': float(np.median(energy_ratios)) if len(energy_ratios) > 0 else None,
            'energy_ratio_cv': float(np.std(energy_ratios) / np.mean(energy_ratios))
            if len(energy_ratios) > 0 and np.mean(energy_ratios) > 0 else None,
        }

        if detail:
            cr_str = f"profile_CR={profile_cr:.1f}" if profile_cr else "profile_CR=N/A"
            sig = "*" if p_cr < 0.05 else ""
            print(f"  {name}: {cr_str}, {len(carb_arr)} meals, r(carb,rise)={r_cr:.3f}{sig}, "
                  f"mean_rise={np.mean(rise_arr):.1f} mg/dL")

    rs = [r['r_carb_vs_rise'] for r in results.values()]
    rises = [r['mean_bg_rise'] for r in results.values()]
    sig_count = sum(1 for r in results.values() if r['p_carb_vs_rise'] < 0.05)

    summary = {
        'experiment': 'EXP-575',
        'name': 'Counterfactual CR from Flux',
        'mean_r_carb_rise': float(np.mean(rs)) if rs else 0,
        'mean_bg_rise': float(np.mean(rises)) if rises else 0,
        'sig_count': sig_count,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-575 Summary: mean r(carb,rise)={np.mean(rs):.3f}, "
              f"mean rise={np.mean(rises):.1f}, {sig_count}/{len(results)} sig")

    return summary


# ──────────────────────────────────────────────
# EXP-576: Basal Adequacy Score
# ──────────────────────────────────────────────
def exp576_basal_adequacy(patients, detail=False):
    """Measure net flux during fasting-only windows to assess basal correctness."""
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
        demand_v = demand[valid]
        supply_v = supply[valid]
        hepatic_v = hepatic[valid]
        net_v = net[valid]
        carb_v = carb_supply[valid]
        N = len(bg_v)
        if N < 500:
            continue

        dbg = _compute_dbg(bg_v)
        idx_valid = np.where(valid)[0]
        tod = idx_valid % 288

        # Fasting: low carb supply, no recent meal (>2h since carbs)
        carb_thresh = np.percentile(carb_v[carb_v > 0], 10) if np.sum(carb_v > 0) > 10 else 0.01
        fasting = np.zeros(N, dtype=bool)
        last_carb = -999
        for i in range(N):
            if carb_v[i] > carb_thresh:
                last_carb = i
            if i - last_carb > 24:  # >2h since carbs
                fasting[i] = True

        if np.sum(fasting) < 200:
            continue

        # Basal adequacy: during fasting, net flux should be ~0
        # Positive net = BG rising (basal too low or EGP too high)
        # Negative net = BG dropping (basal too high)
        fasting_net = net_v[fasting]
        fasting_dbg = dbg[fasting]

        valid_both = np.isfinite(fasting_net) & np.isfinite(fasting_dbg)
        if np.sum(valid_both) < 50:
            continue

        net_mean = float(np.mean(fasting_net[valid_both]))
        net_std = float(np.std(fasting_net[valid_both]))
        dbg_mean = float(np.mean(fasting_dbg[valid_both]))

        # Per-period basal adequacy
        period_adequacy = {}
        for period, (t0, t1) in [('overnight', (0, 72)), ('morning', (72, 144)),
                                   ('afternoon', (144, 216)), ('evening', (216, 288))]:
            mask = fasting & (tod >= t0) & (tod < t1)
            if np.sum(mask) > 50:
                fnet = net_v[mask]
                fdbg = dbg[mask]
                v = np.isfinite(fnet) & np.isfinite(fdbg)
                if np.sum(v) > 20:
                    period_adequacy[period] = {
                        'mean_net_flux': float(np.mean(fnet[v])),
                        'mean_dbg': float(np.mean(fdbg[v])),
                        'n': int(np.sum(v)),
                    }

        # Basal adequacy score: |mean_fasting_dbg| — closer to 0 = better
        basal_score = abs(dbg_mean)

        # Direction: positive = basal too low, negative = basal too high
        direction = 'too_low' if dbg_mean > 0.5 else 'too_high' if dbg_mean < -0.5 else 'adequate'

        results[name] = {
            'fasting_mean_net_flux': net_mean,
            'fasting_mean_dbg': dbg_mean,
            'fasting_net_std': net_std,
            'basal_score': float(basal_score),
            'direction': direction,
            'n_fasting_points': int(np.sum(fasting)),
            'fasting_fraction': float(np.sum(fasting) / N),
            'period_adequacy': period_adequacy,
        }

        if detail:
            print(f"  {name}: fasting dBG={dbg_mean:+.2f} mg/dL/5min ({direction}), "
                  f"score={basal_score:.2f}, "
                  f"fasting={np.sum(fasting) / N:.0%} of time")

    scores = [r['basal_score'] for r in results.values()]
    directions = [r['direction'] for r in results.values()]
    dir_counts = {d: directions.count(d) for d in set(directions)}

    summary = {
        'experiment': 'EXP-576',
        'name': 'Basal Adequacy Score',
        'mean_basal_score': float(np.mean(scores)) if scores else 0,
        'direction_counts': dir_counts,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-576 Summary: mean basal score={np.mean(scores):.2f}, "
              f"directions={dir_counts}")

    return summary


# ──────────────────────────────────────────────
# EXP-577: Weekly Regime Detection
# ──────────────────────────────────────────────
def exp577_weekly_regimes(patients, detail=False):
    """Detect distinct behavioral patterns by clustering weekly flux vectors."""
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p.get('pk')
        if pk is None:
            continue

        bg = _get_bg(df)
        flux = compute_supply_demand(df, pk)

        valid = np.isfinite(bg) & np.isfinite(flux['net'])
        bg_v = bg[valid]
        N = len(bg_v)
        if N < 2016:  # Need at least 1 week
            continue

        supply_v = flux['supply'][valid]
        demand_v = flux['demand'][valid]
        net_v = flux['net'][valid]

        dbg = _compute_dbg(bg_v)

        # Build weekly feature vectors
        week_len = 2016  # 7 * 288
        n_weeks = N // week_len
        if n_weeks < 3:
            continue

        weekly_features = []
        for w in range(n_weeks):
            start = w * week_len
            end = start + week_len
            week_bg = bg_v[start:end]
            week_supply = supply_v[start:end]
            week_demand = demand_v[start:end]
            week_net = net_v[start:end]
            week_dbg = dbg[start:end]

            v = np.isfinite(week_bg) & np.isfinite(week_net) & np.isfinite(week_dbg)
            if np.sum(v) < week_len * 0.7:
                continue

            features = [
                np.mean(week_bg[v]),
                np.std(week_bg[v]),
                np.mean(week_dbg[v]),
                np.std(week_dbg[v]),
                np.mean(week_supply[v]),
                np.mean(week_demand[v]),
                np.mean(week_net[v]),
                np.std(week_net[v]),
                np.sum(week_bg[v] > 180) / np.sum(v),  # time above range
                np.sum(week_bg[v] < 70) / np.sum(v),   # time below range
                np.sum((week_bg[v] >= 70) & (week_bg[v] <= 180)) / np.sum(v),  # TIR
            ]
            weekly_features.append(features)

        if len(weekly_features) < 3:
            continue

        X = np.array(weekly_features)
        # Standardize
        X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12)

        # Simple K-means with K=2,3
        best_k = 1
        best_sil = -1

        for k in [2, 3]:
            if len(X_std) < k + 1:
                continue
            # Simple K-means
            rng = np.random.RandomState(42)
            centers = X_std[rng.choice(len(X_std), k, replace=False)]

            for _ in range(20):
                dists = np.array([[np.sum((x - c) ** 2) for c in centers] for x in X_std])
                labels = np.argmin(dists, axis=1)
                for j in range(k):
                    if np.sum(labels == j) > 0:
                        centers[j] = X_std[labels == j].mean(axis=0)

            # Silhouette score (simplified)
            if len(set(labels)) < 2:
                continue
            sil_scores = []
            for i in range(len(X_std)):
                same = X_std[labels == labels[i]]
                if len(same) < 2:
                    continue
                a = np.mean([np.sqrt(np.sum((X_std[i] - s) ** 2)) for s in same if not np.array_equal(s, X_std[i])])
                b_vals = []
                for j in range(k):
                    if j != labels[i] and np.sum(labels == j) > 0:
                        other = X_std[labels == j]
                        b_vals.append(np.mean([np.sqrt(np.sum((X_std[i] - o) ** 2)) for o in other]))
                if not b_vals:
                    continue
                b = min(b_vals)
                sil_scores.append((b - a) / max(a, b))

            sil = np.mean(sil_scores) if sil_scores else -1
            if sil > best_sil:
                best_sil = sil
                best_k = k

        # Week-to-week variability
        weekly_tir = X[:, 10]
        weekly_bg_mean = X[:, 0]
        tir_cv = float(np.std(weekly_tir) / np.mean(weekly_tir)) if np.mean(weekly_tir) > 0 else 0

        results[name] = {
            'n_weeks': len(weekly_features),
            'best_k': best_k,
            'silhouette': float(best_sil),
            'weekly_tir_cv': tir_cv,
            'weekly_tir_mean': float(np.mean(weekly_tir)),
            'weekly_tir_std': float(np.std(weekly_tir)),
            'weekly_bg_mean': float(np.mean(weekly_bg_mean)),
        }

        if detail:
            print(f"  {name}: {len(weekly_features)} weeks, K={best_k}, "
                  f"silhouette={best_sil:.3f}, TIR CV={tir_cv:.2f}")

    sils = [r['silhouette'] for r in results.values()]
    cvs = [r['weekly_tir_cv'] for r in results.values()]

    summary = {
        'experiment': 'EXP-577',
        'name': 'Weekly Regime Detection',
        'mean_silhouette': float(np.mean(sils)) if sils else 0,
        'mean_tir_cv': float(np.mean(cvs)) if cvs else 0,
        'patients': results,
    }

    if detail:
        print(f"\n  EXP-577 Summary: mean silhouette={np.mean(sils):.3f}, "
              f"mean TIR CV={np.mean(cvs):.2f}")

    return summary


# ──────────────────────────────────────────────
# EXP-578: Monthly Flux Coefficient Drift
# ──────────────────────────────────────────────
def exp578_monthly_drift(patients, detail=False):
    """Track month-over-month flux coefficient changes to detect ISF/CR drift."""
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
        supply_v = supply[valid]
        demand_v = demand[valid]
        hepatic_v = hepatic[valid]
        N = len(bg_v)

        month_len = 8640  # ~30 days * 288
        n_months = N // month_len
        if n_months < 2:
            continue

        monthly_betas = []
        for m in range(n_months):
            start = m * month_len
            end = start + month_len
            bg_m = bg_v[start:end]
            dbg_m = _compute_dbg(bg_m)

            X = np.column_stack([supply_v[start:end], demand_v[start:end],
                                 hepatic_v[start:end], bg_m])
            y = dbg_m
            v = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
            if np.sum(v) < 200:
                continue

            try:
                X_v = X[v]
                y_v = y[v]
                XtX = X_v.T @ X_v + 1.0 * np.eye(4)
                beta = np.linalg.solve(XtX, X_v.T @ y_v)
                monthly_betas.append(beta)
            except Exception:
                continue

        if len(monthly_betas) < 2:
            continue

        betas = np.array(monthly_betas)
        coef_names = ['supply', 'demand', 'hepatic', 'bg_decay']

        # Test for linear trend in each coefficient
        drift_results = {}
        months = np.arange(len(betas))
        for j, cname in enumerate(coef_names):
            slope, intercept, r_val, p_val, std_err = stats.linregress(months, betas[:, j])
            drift_results[cname] = {
                'slope': float(slope),
                'r2': float(r_val ** 2),
                'p': float(p_val),
                'significant': bool(p_val < 0.05),
                'first_month': float(betas[0, j]),
                'last_month': float(betas[-1, j]),
            }

        sig_drifts = [c for c, d in drift_results.items() if d['significant']]

        results[name] = {
            'n_months': len(monthly_betas),
            'drift': drift_results,
            'n_significant_drifts': len(sig_drifts),
            'significant_channels': sig_drifts,
        }

        if detail:
            drift_parts = [f"{c}:{d['slope']:+.4f}{'*' if d['significant'] else ''}"
                          for c, d in drift_results.items()]
            print(f"  {name}: {len(monthly_betas)} months, {', '.join(drift_parts)}")

    sig_counts = [r['n_significant_drifts'] for r in results.values()]

    summary = {
        'experiment': 'EXP-578',
        'name': 'Monthly Flux Coefficient Drift',
        'mean_sig_drifts': float(np.mean(sig_counts)) if sig_counts else 0,
        'patients': results,
    }

    if detail:
        all_sigs = []
        for r in results.values():
            all_sigs.extend(r['significant_channels'])
        ch_counts = {c: all_sigs.count(c) for c in set(all_sigs)}
        print(f"\n  EXP-578 Summary: mean sig drifts={np.mean(sig_counts):.1f}, "
              f"channels={ch_counts}")

    return summary


# ──────────────────────────────────────────────
# EXP-580: Settings Adequacy Composite Score
# ──────────────────────────────────────────────
def exp580_settings_score(patients, detail=False):
    """Composite score: basal balance + ISF match + CR match + TIR."""
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
        demand_v = demand[valid]
        supply_v = supply[valid]
        net_v = net[valid]
        carb_v = carb_supply[valid]
        N = len(bg_v)
        if N < 500:
            continue

        split = int(0.8 * N)
        dbg = _compute_dbg(bg_v)

        # Component 1: TIR
        tir = np.sum((bg_v >= 70) & (bg_v <= 180)) / N

        # Component 2: Basal balance (fasting dBG near 0)
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

        # Component 3: Correction efficiency (how well corrections bring BG to target)
        model = _fit_flux_ar(bg_v, supply[valid], demand[valid], hepatic[valid], split)
        if model is None:
            continue
        resid = model['combined_resid']
        resid_std = np.std(resid[np.isfinite(resid)])
        correction_eff = 1.0 - min(resid_std / 15.0, 1.0)  # 15 mg/dL = poor

        # Component 4: Glycemic variability (CV < 36% is target)
        cv = np.std(bg_v) / np.mean(bg_v)
        gv_score = 1.0 - min(cv / 0.5, 1.0)  # 50% CV = worst

        # Component 5: Flux balance (supply ≈ demand over time)
        flux_balance = np.mean(net_v[np.isfinite(net_v)])
        balance_score = 1.0 - min(abs(flux_balance) / 5.0, 1.0)

        # Composite score (0-100)
        composite = (
            tir * 35 +                # TIR worth 35%
            basal_balance * 20 +       # Basal adequacy 20%
            correction_eff * 20 +      # Correction efficiency 20%
            gv_score * 15 +            # Glycemic variability 15%
            balance_score * 10         # Flux balance 10%
        )

        results[name] = {
            'composite_score': float(composite),
            'tir': float(tir),
            'basal_balance': float(basal_balance),
            'correction_efficiency': float(correction_eff),
            'gv_score': float(gv_score),
            'balance_score': float(balance_score),
            'cv': float(cv),
            'residual_std': float(resid_std),
        }

        if detail:
            print(f"  {name}: score={composite:.1f}/100, TIR={tir:.0%}, "
                  f"basal={basal_balance:.2f}, corr_eff={correction_eff:.2f}, "
                  f"GV={gv_score:.2f}, balance={balance_score:.2f}")

    scores = [r['composite_score'] for r in results.values()]
    tirs = [r['tir'] for r in results.values()]

    summary = {
        'experiment': 'EXP-580',
        'name': 'Settings Adequacy Composite Score',
        'mean_score': float(np.mean(scores)) if scores else 0,
        'std_score': float(np.std(scores)) if scores else 0,
        'mean_tir': float(np.mean(tirs)) if tirs else 0,
        'patients': results,
    }

    if detail:
        ranked = sorted(results.items(), key=lambda x: x[1]['composite_score'], reverse=True)
        print(f"\n  EXP-580 Ranking:")
        for rank, (n, r) in enumerate(ranked, 1):
            print(f"    #{rank} {n}: {r['composite_score']:.1f}/100 (TIR={r['tir']:.0%})")

    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-571-580 autoresearch')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated: 571-580 or "all"')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps = args.experiments.split(',') if args.experiments != 'all' else \
        ['571', '572', '573', '574', '575', '576', '577', '578', '580']

    all_results = {}

    if '571' in exps:
        print("\n=== EXP-571: Meal Size vs Residual ===")
        all_results['exp571'] = exp571_meal_size_residual(patients, args.detail)

    if '572' in exps:
        print("\n=== EXP-572: Meal Time-of-Day Effect ===")
        all_results['exp572'] = exp572_meal_tod(patients, args.detail)

    if '573' in exps:
        print("\n=== EXP-573: Fat/Protein Tail Detection ===")
        all_results['exp573'] = exp573_fat_protein_tail(patients, args.detail)

    if '574' in exps:
        print("\n=== EXP-574: Counterfactual ISF ===")
        all_results['exp574'] = exp574_counterfactual_isf(patients, args.detail)

    if '575' in exps:
        print("\n=== EXP-575: Counterfactual CR ===")
        all_results['exp575'] = exp575_counterfactual_cr(patients, args.detail)

    if '576' in exps:
        print("\n=== EXP-576: Basal Adequacy Score ===")
        all_results['exp576'] = exp576_basal_adequacy(patients, args.detail)

    if '577' in exps:
        print("\n=== EXP-577: Weekly Regime Detection ===")
        all_results['exp577'] = exp577_weekly_regimes(patients, args.detail)

    if '578' in exps:
        print("\n=== EXP-578: Monthly Coefficient Drift ===")
        all_results['exp578'] = exp578_monthly_drift(patients, args.detail)

    if '580' in exps:
        print("\n=== EXP-580: Settings Adequacy Score ===")
        all_results['exp580'] = exp580_settings_score(patients, args.detail)

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
