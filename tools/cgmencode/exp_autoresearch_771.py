#!/usr/bin/env python3
"""EXP-771-780: Physics-Informed ML, Schedule Optimization & Production Pipeline.

Key experiments:
- EXP-771: Physics features for CNN classification (supply/demand/residual as channels)
- EXP-772: Cage-hours aware cannula age effect
- EXP-773: ISF schedule optimizer (piecewise-constant from EXP-765 data)
- EXP-774: Basal schedule optimizer (from EXP-764 time-block residuals)
- EXP-775: Meal announcement compliance score
- EXP-776: Settings quality trend over time (rolling window)
- EXP-777: Population warm-start with personal refinement
- EXP-778: FFT of physics residual (circadian/ultradian components)
- EXP-779: Prediction confidence bands (quantile regression)
- EXP-780: End-to-end integrated settings report
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_bg(df):
    return df['glucose'].values if 'glucose' in df.columns else df['sgv'].values

def _physics_sim(bg_start, supply, demand, hepatic, resid_start, ar_w, decay, n_steps):
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

def _compute_flux(p):
    df = p['df']
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(_get_bg(df)))
    fd = compute_supply_demand(df, pk)
    bg = _get_bg(df)
    n = len(fd['supply'])
    bg = bg[:n]
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.full(n, 0.5))
    flux_pred = supply - demand + hepatic + (120.0 - bg) * 0.005
    resid = bg[1:] - (bg[:-1] + flux_pred[:-1])
    return {
        'bg': bg, 'supply': supply, 'demand': demand,
        'hepatic': hepatic, 'flux_pred': flux_pred,
        'resid': resid, 'n': n,
    }

def _get_hours(df, n):
    import pandas as pd
    idx = df.index[:n]
    if isinstance(idx, pd.DatetimeIndex):
        return idx.hour
    return None

def _r2(pred, actual):
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    if ss_tot < 1e-10:
        return float('nan')
    return 1.0 - ss_res / ss_tot

EXPERIMENTS = {}

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-771: Physics Features for CNN Classification
# ---------------------------------------------------------------------------
@register('EXP-771', 'Physics CNN Features')
def exp_771(patients, detail=False):
    """Test if physics-derived channels improve simple pattern classification."""
    from collections import Counter

    results = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        resid = fd['resid']
        n = fd['n']
        nr = len(resid)

        # Create classification targets: next-2h BG direction
        # 0=drop, 1=stable, 2=rise
        window = 24  # 2h = 24 steps
        labels = []
        features_bg = []
        features_phys = []

        hist_len = 12  # 1h history
        for i in range(hist_len, nr - window):
            bg_change = bg[i + window] - bg[i]
            if bg_change < -20:
                label = 0  # drop
            elif bg_change > 20:
                label = 2  # rise
            else:
                label = 1  # stable

            # BG-only features: last 1h of BG values
            bg_hist = bg[i-hist_len:i]
            bg_feat = np.array([np.mean(bg_hist), np.std(bg_hist),
                               bg_hist[-1] - bg_hist[0],  # trend
                               bg_hist[-1]])  # current

            # Physics features: supply, demand, residual stats
            s_hist = supply[i-hist_len:i]
            d_hist = demand[i-hist_len:i]
            r_hist = resid[i-hist_len:i] if i >= hist_len else np.zeros(hist_len)
            phys_feat = np.array([np.mean(s_hist), np.mean(d_hist),
                                  np.mean(s_hist) - np.mean(d_hist),  # net flux
                                  np.std(r_hist), np.mean(r_hist)])

            labels.append(label)
            features_bg.append(bg_feat)
            features_phys.append(phys_feat)

        if len(labels) < 500:
            continue

        labels = np.array(labels)
        features_bg = np.array(features_bg)
        features_phys = np.array(features_phys)
        features_all = np.hstack([features_bg, features_phys])

        # Simple nearest-centroid classifier (no sklearn needed)
        split = int(len(labels) * 0.7)
        train_l, val_l = labels[:split], labels[split:]

        def classify(train_feat, val_feat, train_l, val_l):
            centroids = {}
            for c in [0, 1, 2]:
                mask = train_l == c
                if mask.sum() > 0:
                    centroids[c] = np.mean(train_feat[mask], axis=0)
            preds = []
            for f in val_feat:
                best_c = min(centroids.keys(),
                            key=lambda c: np.sum((f - centroids[c])**2))
                preds.append(best_c)
            return np.mean(np.array(preds) == val_l)

        acc_bg = classify(features_bg[:split], features_bg[split:], train_l, val_l)
        acc_all = classify(features_all[:split], features_all[split:], train_l, val_l)
        delta = acc_all - acc_bg

        class_dist = Counter(labels.tolist())
        majority = max(class_dist.values()) / len(labels)

        results.append({
            'patient': p['name'],
            'acc_bg': round(acc_bg, 3),
            'acc_phys': round(acc_all, 3),
            'delta': round(delta, 3),
            'majority': round(majority, 3),
            'n_samples': len(labels),
        })

    mean_bg = np.mean([r['acc_bg'] for r in results]) if results else float('nan')
    mean_phys = np.mean([r['acc_phys'] for r in results]) if results else float('nan')
    mean_delta = mean_phys - mean_bg
    detail_parts = [f'{r["patient"]}: bg={r["acc_bg"]}/phys={r["acc_phys"]}/Δ={r["delta"]:+.3f}' for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'mean bg_acc={mean_bg:.3f}, phys_acc={mean_phys:.3f}, Δ={mean_delta:+.3f}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-772: Cage-Hours Aware Cannula Age
# ---------------------------------------------------------------------------
@register('EXP-772', 'Cage-Aware Cannula Age')
def exp_772(patients, detail=False):
    """Use actual cage_hours column for precise infusion site age analysis."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid = fd['resid']
        nr = len(resid)
        df = p['df']

        if 'cage_hours' not in df.columns:
            continue

        cage = df['cage_hours'].values[:nr]
        valid = np.isfinite(cage) & np.isfinite(resid)
        if valid.sum() < 1000:
            continue

        cage_v = cage[valid]
        resid_v = np.abs(resid[valid])

        # Bin by cage age (day 1, 2, 3, 4+)
        bins = [(0, 24, 'Day1'), (24, 48, 'Day2'), (48, 72, 'Day3'), (72, 168, 'Day4+')]
        bin_results = {}
        for lo, hi, name in bins:
            mask = (cage_v >= lo) & (cage_v < hi)
            if mask.sum() > 100:
                bin_results[name] = {
                    'mean_resid': round(float(np.nanmean(resid_v[mask])), 3),
                    'n': int(mask.sum()),
                }

        if len(bin_results) >= 2:
            first_val = list(bin_results.values())[0]['mean_resid']
            last_val = list(bin_results.values())[-1]['mean_resid']
            degradation = (last_val - first_val) / first_val * 100 if first_val > 0 else 0

            results.append({
                'patient': p['name'],
                'bins': bin_results,
                'degradation_pct': round(degradation, 1),
            })

    detail_parts = []
    for r in results[:8]:
        bins_str = '/'.join(f'{k}={v["mean_resid"]}' for k, v in r['bins'].items())
        detail_parts.append(f'{r["patient"]}: {bins_str} ({r["degradation_pct"]:+.1f}%)')

    mean_deg = np.mean([r['degradation_pct'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean_deg={mean_deg:.1f}%. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-773: ISF Schedule Optimizer
# ---------------------------------------------------------------------------
@register('EXP-773', 'ISF Schedule Optimizer')
def exp_773(patients, detail=False):
    """Generate optimal piecewise-constant ISF schedule from physics data."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        demand = fd['demand']
        supply = fd['supply']
        resid = fd['resid']
        n = fd['n']
        df = p['df']
        nr = len(resid)

        hours = _get_hours(df, n)
        if hours is None:
            continue

        # Get current ISF
        attrs = df.attrs if hasattr(df, 'attrs') else {}
        isf_schedule = attrs.get('isf_schedule', None)
        if not isf_schedule:
            continue

        if isinstance(isf_schedule, list):
            mean_isf = np.mean([float(s.get('value', 50)) for s in isf_schedule])
        else:
            mean_isf = float(isf_schedule)
        if mean_isf < 15:
            mean_isf *= 18.0182

        # Compute effective ISF by 4-hour blocks
        d_mean = np.nanmean(demand)
        d_std = np.nanstd(demand)
        s_med = np.nanmedian(supply)

        block_isfs = {}
        for block_start in range(0, 24, 4):
            block_end = block_start + 4
            effective_isfs = []

            for i in range(nr - 12):
                if hours[i] < block_start or hours[i] >= block_end:
                    continue
                if demand[i] > d_mean + 0.5 * d_std and supply[i] < s_med * 1.5:
                    d_integral = np.sum(demand[i:min(i+12, n)]) * 5.0 / 60.0
                    if d_integral < 3.0:
                        continue
                    end_idx = min(i + 12, n - 1)
                    bg_drop = bg[i] - bg[end_idx]
                    if bg_drop > 5 and d_integral > 0:
                        eff_isf = bg_drop / (d_integral / 50.0)
                        if 5 < eff_isf < 200:
                            effective_isfs.append(eff_isf)

            if len(effective_isfs) >= 5:
                block_isfs[f'{block_start:02d}:00'] = round(float(np.median(effective_isfs)), 1)

        if len(block_isfs) >= 3:
            isf_values = list(block_isfs.values())
            variation = (max(isf_values) - min(isf_values)) / np.mean(isf_values) * 100

            # Scale to match profile ISF magnitude
            scale = mean_isf / np.mean(isf_values) if np.mean(isf_values) > 0 else 1.0
            optimized = {k: round(v * scale, 1) for k, v in block_isfs.items()}

            results.append({
                'patient': p['name'],
                'current_isf': round(mean_isf, 1),
                'optimized_schedule': optimized,
                'variation_pct': round(variation, 1),
                'n_blocks': len(block_isfs),
            })

    detail_parts = [f'{r["patient"]}: current={r["current_isf"]}, var={r["variation_pct"]}%, '
                   f'schedule={r["optimized_schedule"]}' for r in results[:4]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-774: Basal Schedule Optimizer
# ---------------------------------------------------------------------------
@register('EXP-774', 'Basal Schedule Optimizer')
def exp_774(patients, detail=False):
    """Generate optimal basal rate adjustments from 2-hour block residuals."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']
        nr = len(resid)
        df = p['df']

        hours = _get_hours(df, n)
        if hours is None:
            continue

        # Current basal
        attrs = df.attrs if hasattr(df, 'attrs') else {}
        basal_schedule = attrs.get('basal_schedule', None)
        if not basal_schedule:
            continue

        if isinstance(basal_schedule, list):
            mean_basal = np.mean([float(s.get('value', 1.0)) for s in basal_schedule])
        else:
            mean_basal = float(basal_schedule)

        # Quiet periods only
        s_med = np.nanmedian(supply)
        d_med = np.nanmedian(demand)
        quiet = (supply[:nr] < s_med * 1.2) & (demand[:nr] < d_med * 1.2)

        block_adjustments = {}
        for block_start in range(0, 24, 2):
            block_end = block_start + 2
            mask = quiet & (hours[:nr] >= block_start) & (hours[:nr] < block_end)
            if mask.sum() > 50:
                mean_resid = float(np.nanmean(resid[mask]))
                # Positive residual = BG drifting up = basal too low
                # Convert to U/h adjustment (rough: 1 mg/dL/5min ≈ 0.05 U/h)
                adj_uh = -mean_resid * 0.05
                adj_pct = adj_uh / mean_basal * 100 if mean_basal > 0 else 0

                block_adjustments[f'{block_start:02d}:00'] = {
                    'resid': round(mean_resid, 2),
                    'adj_uh': round(adj_uh, 3),
                    'adj_pct': round(float(adj_pct), 1),
                    'new_rate': round(mean_basal + adj_uh, 3),
                }

        if len(block_adjustments) >= 6:
            max_adj = max(block_adjustments.values(), key=lambda x: abs(x['adj_pct']))
            results.append({
                'patient': p['name'],
                'current_basal': round(mean_basal, 3),
                'n_blocks': len(block_adjustments),
                'max_adj_pct': round(max_adj['adj_pct'], 1),
                'schedule': block_adjustments,
            })

    detail_parts = [f'{r["patient"]}: basal={r["current_basal"]}U/h, max_adj={r["max_adj_pct"]:+.1f}%, '
                   f'{r["n_blocks"]} blocks' for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-775: Meal Announcement Compliance Score
# ---------------------------------------------------------------------------
@register('EXP-775', 'Meal Announcement Score')
def exp_775(patients, detail=False):
    """Quantify meal announcement compliance from bolused vs unbolused supply events."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']

        s_mean = np.nanmean(supply)
        s_std = np.nanstd(supply)
        d_mean = np.nanmean(demand)
        d_std = np.nanstd(demand)
        threshold = s_mean + 1.0 * s_std

        # Find supply bursts
        total_meals = 0
        bolused = 0

        i = 0
        while i < n:
            if supply[i] > threshold:
                start = i
                while i < n and supply[i] > threshold:
                    i += 1
                burst_size = np.sum(supply[start:i]) * 5.0 / 60.0
                if burst_size < 15.0:
                    continue
                total_meals += 1

                # Check for bolus within ±30min
                window_start = max(0, start - 6)
                window_end = min(n, start + 6)
                if np.max(demand[window_start:window_end]) > d_mean + 1.5 * d_std:
                    bolused += 1
            else:
                i += 1

        if total_meals > 0:
            compliance = bolused / total_meals * 100
            results.append({
                'patient': p['name'],
                'total_meals': total_meals,
                'bolused': bolused,
                'unbolused': total_meals - bolused,
                'compliance_pct': round(compliance, 1),
            })

    detail_parts = [f'{r["patient"]}: {r["compliance_pct"]}% ({r["bolused"]}/{r["total_meals"]})' for r in results[:11]]
    mean_comp = np.mean([r['compliance_pct'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean compliance={mean_comp:.1f}%. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-776: Settings Quality Trend
# ---------------------------------------------------------------------------
@register('EXP-776', 'Settings Quality Trend')
def exp_776(patients, detail=False):
    """Track settings quality score over time in 2-week rolling windows."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']
        nr = len(resid)

        window = 14 * 288  # 2 weeks
        step = 7 * 288     # 1 week step

        scores = []
        for w_start in range(0, nr - window, step):
            w_end = w_start + window
            w_bg = bg[w_start:w_end]
            w_resid = resid[w_start:min(w_end, nr)]

            # TIR component
            tir = np.mean((w_bg >= 70) & (w_bg <= 180))

            # Residual magnitude (lower = better settings)
            resid_mag = np.nanmean(np.abs(w_resid))
            resid_score = max(0, 100 - resid_mag * 10)

            # Combined
            score = tir * 50 + resid_score * 0.5
            scores.append({
                'week': len(scores),
                'tir': round(float(tir) * 100, 1),
                'resid_mag': round(float(resid_mag), 2),
                'score': round(float(score), 1),
            })

        if len(scores) >= 4:
            # Trend: linear fit on scores
            score_vals = [s['score'] for s in scores]
            x = np.arange(len(score_vals))
            trend = np.polyfit(x, score_vals, 1)[0]

            results.append({
                'patient': p['name'],
                'n_windows': len(scores),
                'first_score': scores[0]['score'],
                'last_score': scores[-1]['score'],
                'mean_score': round(np.mean(score_vals), 1),
                'trend_per_week': round(float(trend), 2),
                'improving': trend > 0.5,
                'deteriorating': trend < -0.5,
            })

    detail_parts = [f'{r["patient"]}: {r["first_score"]}→{r["last_score"]} '
                   f'(trend={r["trend_per_week"]:+.2f}/wk)' for r in results[:8]]
    improving = sum(1 for r in results if r['improving'])
    deteriorating = sum(1 for r in results if r['deteriorating'])
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, ↑{improving} improving, ↓{deteriorating} deteriorating. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-777: Population Warm-Start + Personal Refinement
# ---------------------------------------------------------------------------
@register('EXP-777', 'Population Warm-Start')
def exp_777(patients, detail=False):
    """Start with population physics params, refine with 1 week of personal data."""
    if len(patients) < 3:
        return {'status': 'skip', 'detail': 'Need ≥3 patients'}

    # Compute population params from all patients
    all_optimal = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        nr = len(resid)
        h_steps = 6  # 30min
        n_pred = nr - h_steps
        if n_pred < 100:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        best_r2 = -999
        best_w = 0.15
        best_d = 0.95

        for w in [0.05, 0.10, 0.15, 0.20, 0.30]:
            for d in [0.80, 0.90, 0.95, 0.99]:
                pred = np.full(n_pred, np.nan)
                for i in range(0, n_pred, 10):
                    pred[i] = _physics_sim(
                        bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                        fd['hepatic'][i:i+h_steps], resid[i], w, d, h_steps
                    )
                r2 = _r2(pred, actual)
                if np.isfinite(r2) and r2 > best_r2:
                    best_r2 = r2
                    best_w = w
                    best_d = d

        all_optimal.append({'name': p['name'], 'w': best_w, 'd': best_d, 'r2': best_r2})

    pop_w = np.mean([o['w'] for o in all_optimal])
    pop_d = np.mean([o['d'] for o in all_optimal])

    results = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        nr = len(resid)
        h_steps = 6
        n_pred = nr - h_steps
        if n_pred < 500:
            continue

        actual = bg[h_steps:h_steps + n_pred]

        # 1 week of data for refinement
        one_week = min(7 * 288, n_pred // 2)
        refine_end = one_week

        # Refine: grid search on first week only
        best_r2 = -999
        best_w = pop_w
        best_d = pop_d
        for w in [pop_w - 0.05, pop_w, pop_w + 0.05]:
            for d in [pop_d - 0.05, pop_d, pop_d + 0.05]:
                if w < 0.01 or d < 0.5:
                    continue
                pred = np.full(refine_end, np.nan)
                for i in range(0, refine_end, 10):
                    pred[i] = _physics_sim(
                        bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                        fd['hepatic'][i:i+h_steps], resid[i], w, d, h_steps
                    )
                r2 = _r2(pred, actual[:refine_end])
                if np.isfinite(r2) and r2 > best_r2:
                    best_r2 = r2
                    best_w = w
                    best_d = d

        # Evaluate all three approaches on REMAINING data (after first week)
        eval_start = refine_end
        eval_actual = actual[eval_start:]
        n_eval = len(eval_actual)
        if n_eval < 200:
            continue

        def eval_params(w, d):
            pred = np.full(n_eval, np.nan)
            for i in range(0, n_eval, 10):
                idx = eval_start + i
                pred[i] = _physics_sim(
                    bg[idx], fd['supply'][idx:idx+h_steps], fd['demand'][idx:idx+h_steps],
                    fd['hepatic'][idx:idx+h_steps], resid[idx], w, d, h_steps
                )
            return _r2(pred, eval_actual)

        r2_pop = eval_params(pop_w, pop_d)
        r2_refined = eval_params(best_w, best_d)
        personal = [o for o in all_optimal if o['name'] == p['name']]
        r2_personal = eval_params(personal[0]['w'], personal[0]['d']) if personal else r2_refined

        results.append({
            'patient': p['name'],
            'r2_pop': round(r2_pop, 3),
            'r2_refined': round(r2_refined, 3),
            'r2_personal': round(r2_personal, 3),
            'pop_to_refined': round(r2_refined - r2_pop, 3),
            'refined_to_personal': round(r2_personal - r2_refined, 3),
        })

    mean_pop = np.mean([r['r2_pop'] for r in results]) if results else float('nan')
    mean_ref = np.mean([r['r2_refined'] for r in results]) if results else float('nan')
    mean_pers = np.mean([r['r2_personal'] for r in results]) if results else float('nan')
    detail_parts = [f'{r["patient"]}: pop={r["r2_pop"]}/ref={r["r2_refined"]}/pers={r["r2_personal"]}' for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'pop={mean_pop:.3f}, refined={mean_ref:.3f}, personal={mean_pers:.3f}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-778: FFT of Physics Residual
# ---------------------------------------------------------------------------
@register('EXP-778', 'Residual FFT Analysis')
def exp_778(patients, detail=False):
    """Identify periodic components in physics residual via FFT."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid = fd['resid']
        nr = len(resid)

        if nr < 288 * 7:  # Need at least 1 week
            continue

        # Use first complete weeks
        n_use = (nr // 288) * 288
        r = resid[:n_use]
        r = r - np.nanmean(r)
        r = np.nan_to_num(r, nan=0.0)

        # FFT
        fft_vals = np.abs(np.fft.rfft(r))
        freqs = np.fft.rfftfreq(n_use, d=5.0/60.0)  # in cycles per hour

        # Find peaks at known physiological frequencies
        # Circadian: 1/24h = 0.0417 cycles/h
        # Ultradian: ~1/4h to 1/8h = 0.125 to 0.25 cycles/h
        # Meal-related: ~1/5h to 1/6h = 0.167 to 0.2 cycles/h

        def power_at_freq(target_freq, bandwidth=0.01):
            mask = np.abs(freqs - target_freq) < bandwidth
            return float(np.sum(fft_vals[mask]**2)) if mask.any() else 0

        total_power = float(np.sum(fft_vals[1:]**2))  # Exclude DC
        if total_power < 1e-10:
            continue

        circadian = power_at_freq(1.0/24.0, 0.005)
        ultradian_4h = power_at_freq(1.0/4.0, 0.02)
        ultradian_8h = power_at_freq(1.0/8.0, 0.01)
        meal_6h = power_at_freq(1.0/6.0, 0.015)

        # Top 5 frequency peaks
        top_idx = np.argsort(fft_vals[1:])[-5:] + 1  # Skip DC
        top_freqs = freqs[top_idx]
        top_periods = [round(1.0/f, 1) if f > 0 else float('inf') for f in top_freqs]

        results.append({
            'patient': p['name'],
            'circadian_pct': round(circadian / total_power * 100, 1),
            'ultradian_4h_pct': round(ultradian_4h / total_power * 100, 1),
            'ultradian_8h_pct': round(ultradian_8h / total_power * 100, 1),
            'meal_6h_pct': round(meal_6h / total_power * 100, 1),
            'top_periods_h': sorted(top_periods),
        })

    detail_parts = [f'{r["patient"]}: circ={r["circadian_pct"]}%, 4h={r["ultradian_4h_pct"]}%, '
                   f'8h={r["ultradian_8h_pct"]}%' for r in results[:8]]
    mean_circ = np.mean([r['circadian_pct'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean circadian={mean_circ:.1f}%. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-779: Prediction Confidence Bands
# ---------------------------------------------------------------------------
@register('EXP-779', 'Confidence Bands')
def exp_779(patients, detail=False):
    """Generate prediction intervals using quantile analysis of physics errors."""
    horizons = {1: '5min', 3: '15min', 6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        all_errors = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            supply = fd['supply']
            demand = fd['demand']
            hepatic = fd['hepatic']
            resid = fd['resid']
            nr = len(resid)
            n_pred = nr - h_steps
            if n_pred < 100:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            for i in range(0, n_pred, 5):  # Subsample for speed
                pred = _physics_sim(
                    bg[i], supply[i:i+h_steps], demand[i:i+h_steps],
                    hepatic[i:i+h_steps], resid[i], 0.15, 0.95, h_steps
                )
                if np.isfinite(pred) and np.isfinite(actual[i]):
                    all_errors.append(actual[i] - pred)

        errors = np.array(all_errors)
        if len(errors) < 100:
            continue

        results[h_name] = {
            'n': len(errors),
            'p10': round(float(np.percentile(errors, 10)), 1),
            'p25': round(float(np.percentile(errors, 25)), 1),
            'p50': round(float(np.percentile(errors, 50)), 1),
            'p75': round(float(np.percentile(errors, 75)), 1),
            'p90': round(float(np.percentile(errors, 90)), 1),
            'std': round(float(np.std(errors)), 1),
            'coverage_80': round(float(np.mean((errors >= np.percentile(errors, 10)) &
                                                (errors <= np.percentile(errors, 90)))) * 100, 1),
        }

    detail_str = ', '.join(f'{h}: [{v["p10"]},{v["p90"]}] std={v["std"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-780: End-to-End Settings Report
# ---------------------------------------------------------------------------
@register('EXP-780', 'Integrated Settings Report')
def exp_780(patients, detail=False):
    """Generate comprehensive per-patient settings report integrating all analyses."""
    reports = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']
        nr = len(resid)
        df = p['df']

        hours = _get_hours(df, n)

        report = {'patient': p['name']}

        # 1. TIR
        tir = float(np.mean((bg >= 70) & (bg <= 180))) * 100
        report['tir'] = round(tir, 1)

        # 2. Mean residual magnitude (lower = better physics fit = better settings)
        report['mean_abs_resid'] = round(float(np.nanmean(np.abs(resid))), 2)

        # 3. Basal adequacy (overnight if timestamps available)
        if hours is not None:
            s_med = np.nanmedian(supply)
            d_med = np.nanmedian(demand)
            quiet = (supply[:nr] < s_med * 1.2) & (demand[:nr] < d_med * 1.2)
            night = (hours[:nr] >= 0) & (hours[:nr] < 6)
            mask = quiet & night
            if mask.sum() > 50:
                report['overnight_drift'] = round(float(np.nanmean(resid[mask])), 2)
            else:
                report['overnight_drift'] = float('nan')
        else:
            report['overnight_drift'] = float('nan')

        # 4. Meal compliance
        s_mean = np.nanmean(supply)
        s_std = np.nanstd(supply)
        d_mean = np.nanmean(demand)
        d_std = np.nanstd(demand)
        threshold = s_mean + 1.0 * s_std

        total_meals = 0
        bolused = 0
        i = 0
        while i < n:
            if supply[i] > threshold:
                start = i
                while i < n and supply[i] > threshold:
                    i += 1
                if np.sum(supply[start:i]) * 5.0 / 60.0 >= 15.0:
                    total_meals += 1
                    ws = max(0, start - 6)
                    we = min(n, start + 6)
                    if np.max(demand[ws:we]) > d_mean + 1.5 * d_std:
                        bolused += 1
            else:
                i += 1

        report['meal_compliance_pct'] = round(bolused / total_meals * 100, 1) if total_meals > 0 else float('nan')
        report['total_meals'] = total_meals

        # 5. Hypo risk (% time below 70)
        hypo_pct = float(np.mean(bg < 70)) * 100
        report['hypo_pct'] = round(hypo_pct, 1)

        # 6. Hyper risk (% time above 250)
        hyper_pct = float(np.mean(bg > 250)) * 100
        report['hyper_pct'] = round(hyper_pct, 1)

        # 7. Overall score: weighted combination
        tir_score = tir
        resid_score = max(0, 100 - report['mean_abs_resid'] * 8)
        hypo_penalty = min(30, hypo_pct * 3)  # Up to 30 point penalty
        hyper_penalty = min(20, hyper_pct * 2)

        overall = (tir_score * 0.4 + resid_score * 0.3 +
                  (100 - hypo_penalty) * 0.15 + (100 - hyper_penalty) * 0.15)
        report['overall_score'] = round(float(overall), 1)

        # 8. Top recommendation
        issues = []
        if report['overnight_drift'] > 2.0:
            issues.append(f'Increase basal (overnight drift +{report["overnight_drift"]:.1f} mg/dL/5min)')
        elif report['overnight_drift'] < -2.0:
            issues.append(f'Decrease basal (overnight drift {report["overnight_drift"]:.1f} mg/dL/5min)')
        if hypo_pct > 4:
            issues.append(f'Reduce insulin (hypo {hypo_pct:.1f}% of time)')
        if hyper_pct > 10:
            issues.append(f'Increase insulin (hyper {hyper_pct:.1f}% of time)')
        if report['meal_compliance_pct'] < 60:
            issues.append(f'Improve meal bolusing ({report["meal_compliance_pct"]:.0f}% compliance)')

        report['issues'] = issues if issues else ['Settings appear reasonable']
        reports.append(report)

    detail_parts = [f'{r["patient"]}: {r["overall_score"]}/100 TIR={r["tir"]}% '
                   f'issues={len(r["issues"])}' for r in reports[:8]]
    mean_score = np.mean([r['overall_score'] for r in reports]) if reports else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(reports)}, mean score={mean_score:.1f}. ' + '; '.join(detail_parts),
        'reports': reports,
    }


# ===========================================================================
# Runner
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-771-780')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--only', type=str, default=None)
    args = parser.parse_args()

    print(f'Loading patients (max={args.max_patients})...')
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f'Loaded {len(patients)} patients\n')

    passed = 0
    failed = 0
    results_all = []

    exps = EXPERIMENTS
    if args.only:
        exps = {k: v for k, v in EXPERIMENTS.items() if k == args.only}
        if not exps:
            print(f'Unknown experiment: {args.only}')
            sys.exit(1)

    for exp_id, exp_info in exps.items():
        print(f'\n{"="*60}')
        print(f'Running {exp_id}: {exp_info["name"]}')
        print(f'{"="*60}')

        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            elapsed = time.time() - t0
            status = result.get('status', 'pass')
            detail = result.get('detail', '')
            print(f'  Status: {status} ({elapsed:.1f}s)')
            print(f'  Detail: {detail}')
            if status == 'pass':
                passed += 1
            else:
                failed += 1
            result['exp_id'] = exp_id
            result['name'] = exp_info['name']
            result['elapsed'] = round(elapsed, 1)
            results_all.append(result)
        except Exception as e:
            elapsed = time.time() - t0
            print(f'  Status: FAIL ({elapsed:.1f}s)')
            print(f'  Error: {e}')
            traceback.print_exc()
            failed += 1
            results_all.append({
                'exp_id': exp_id, 'name': exp_info['name'],
                'status': 'fail', 'error': str(e),
            })

    print(f'\n{"="*60}')
    print(f'SUMMARY')
    print(f'{"="*60}')
    print(f'Passed: {passed}/{passed+failed}, Failed: {failed}/{passed+failed}')

    for r in results_all:
        status_char = 'V' if r['status'] == 'pass' else 'X'
        detail = r.get('detail', r.get('error', ''))[:80]
        print(f'  {status_char} {r["exp_id"]} {r["name"]}: {detail}')

    if args.save:
        save_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
        save_dir.mkdir(parents=True, exist_ok=True)
        for r in results_all:
            safe_name = r['name'].lower().replace(' ', '_').replace('/', '-')[:25]
            fname = f'exp_{r["exp_id"].split("-")[1]}_{r["exp_id"].lower()}_{safe_name}.json'
            with open(save_dir / fname, 'w') as f:
                clean = {}
                for k, v in r.items():
                    try:
                        json.dumps(v)
                        clean[k] = v
                    except (TypeError, ValueError):
                        clean[k] = str(v)
                json.dump(clean, f, indent=2)
            print(f'  Saved: {fname}')


if __name__ == '__main__':
    main()
