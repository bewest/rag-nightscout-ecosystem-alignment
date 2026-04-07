#!/usr/bin/env python3
"""EXP-611-620: Nonlinear ISF, Combined Model, Transfer Learning, Clinical Score v2.

Builds on the piecewise model (EXP-610), testing nonlinear extensions,
cross-patient transfer, and advanced clinical scoring.
"""

import argparse, json, sys, warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"
RESULTS_DIR  = Path(__file__).parent.parent.parent / "externals" / "experiments"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers (reused from prior scripts) ─────────────────────────────────────

def load_patients(patients_dir, max_patients=11):
    from cgmencode.exp_metabolic_flux import load_patients as _lp
    return _lp(patients_dir, max_patients=max_patients)

def _bg_col(df):
    return 'glucose' if 'glucose' in df.columns else 'sgv'

def _compute_flux_and_ar(p, ar_order=6, train_frac=0.8):
    """Compute supply/demand decomposition + AR features, returns everything needed."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    df = p['df']; pk = p.get('pk')
    if pk is None:
        return None
    sd = compute_supply_demand(df, pk)
    bg = df[_bg_col(df)].values.astype(float)
    n = len(bg)

    supply = sd['supply']; demand = sd['demand']
    hepatic = sd.get('hepatic', np.zeros(n))
    carb_supply = sd.get('carb_supply', np.zeros(n))
    net = sd.get('net', supply - demand)
    flux_pred = sd.get('sum_flux', net)

    valid = np.isfinite(bg)
    bg_v = bg[valid]
    dbg_v = np.diff(bg_v)
    dbg = np.full(n, np.nan)
    vi = np.where(valid)[0]
    dbg[vi[1:]] = dbg_v

    resid = dbg - flux_pred
    split = int(n * train_frac)

    X_ar = np.column_stack([np.roll(resid, i+1) for i in range(ar_order)])
    mask = np.isfinite(X_ar).all(axis=1) & np.isfinite(resid)

    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < ar_order + 1:
        return None

    XtX = X_ar[train_mask].T @ X_ar[train_mask]
    Xty = X_ar[train_mask].T @ resid[train_mask]
    lam = 1e-6
    ar_coef = np.linalg.solve(XtX + lam * np.eye(ar_order), Xty)
    ar_pred = np.full(n, 0.0)
    ar_ok = np.isfinite(X_ar).all(axis=1)
    ar_pred[ar_ok] = X_ar[ar_ok] @ ar_coef

    combined = flux_pred + ar_pred
    final_resid = dbg - combined

    return {
        'bg': bg, 'dbg': dbg, 'flux_pred': flux_pred, 'ar_pred': ar_pred,
        'combined': combined, 'resid': final_resid, 'valid': valid,
        'supply': supply, 'demand': demand, 'hepatic': hepatic,
        'carb_supply': carb_supply, 'net': net, 'split': split,
        'ar_coef': ar_coef, 'n': n,
    }


def _compute_piecewise_bias(bg, resid, split, ranges=None):
    """Learn per-range bias from training data, return bias array and learned biases."""
    if ranges is None:
        ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]
    n = len(bg)
    train_biases = {}
    for lo, hi in ranges:
        mask = (bg >= lo) & (bg < hi) & np.isfinite(resid) & (np.arange(n) < split)
        if mask.sum() > 10:
            train_biases[(lo, hi)] = np.nanmean(resid[mask])
        else:
            train_biases[(lo, hi)] = 0.0
    bias = np.zeros(n)
    for (lo, hi), b in train_biases.items():
        mask = (bg >= lo) & (bg < hi)
        bias[mask] = b
    return bias, train_biases


def _r2_range(actual, pred, bg, lo, hi, idx_range=None):
    """R² for a BG sub-range, optionally restricted to index range."""
    mask = (bg >= lo) & (bg < hi) & np.isfinite(actual) & np.isfinite(pred)
    if idx_range is not None:
        i_mask = np.zeros(len(bg), dtype=bool)
        i_mask[idx_range[0]:idx_range[1]] = True
        mask &= i_mask
    if mask.sum() < 5:
        return np.nan
    ss_res = np.sum((actual[mask] - pred[mask])**2)
    ss_tot = np.sum((actual[mask] - np.mean(actual[mask]))**2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


# ── Experiments ─────────────────────────────────────────────────────────────

def exp_611_time_varying_bias(patients, detail=False):
    """EXP-611: Time-varying piecewise bias (bias varies by time-of-day × BG range)."""
    results = []
    periods = [(0, 6, 'night'), (6, 12, 'morning'), (12, 18, 'afternoon'), (18, 24, 'evening')]
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        resid = dbg - combined

        df = p['df']
        hour = np.zeros(n)
        if 'dateString' in df.columns:
            try:
                hour = df['dateString'].apply(lambda x: int(str(x)[11:13]) if len(str(x)) > 13 else 0).values.astype(float)
            except:
                pass

        # baseline: single piecewise bias
        bias_base, _ = _compute_piecewise_bias(bg, resid, split, ranges)
        corrected_base = combined + bias_base

        # time-varying: per-period × per-range bias
        bias_tv = np.zeros(n)
        period_biases = {}
        for ph_lo, ph_hi, ph_name in periods:
            for rlo, rhi in ranges:
                mask = (hour >= ph_lo) & (hour < ph_hi) & (bg >= rlo) & (bg < rhi) & np.isfinite(resid) & (np.arange(n) < split)
                b = np.nanmean(resid[mask]) if mask.sum() > 10 else 0.0
                period_biases[(ph_name, rlo, rhi)] = b
                apply_mask = (hour >= ph_lo) & (hour < ph_hi) & (bg >= rlo) & (bg < rhi)
                bias_tv[apply_mask] = b
        corrected_tv = combined + bias_tv

        # evaluate test set
        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() < 50: continue

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        r2_base = 1.0 - np.sum((dbg[test_mask] - corrected_base[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        r2_tv = 1.0 - np.sum((dbg[test_mask] - corrected_tv[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        delta = r2_tv - r2_base

        # find most varying period-range combinations
        max_range = 0; max_combo = ''
        for (ph_name, rlo, rhi), b in period_biases.items():
            base_b = 0
            for (lo, hi), bb in zip(ranges, [_[1] for _ in sorted(zip(ranges, [0]*len(ranges)))]):
                pass
            if abs(b) > max_range:
                max_range = abs(b)
                max_combo = f"{ph_name}_{rlo}-{rhi}"

        results.append({
            'patient': p['name'], 'r2_base_pw': round(r2_base, 4),
            'r2_time_varying': round(r2_tv, 4), 'delta': round(delta, 4),
            'n_test': int(test_mask.sum()),
        })

    improved = sum(1 for r in results if r['delta'] > 0)
    mean_delta = np.mean([r['delta'] for r in results]) if results else 0
    return {
        'name': 'Time-Varying Piecewise Bias',
        'summary': f"Mean ΔR²={mean_delta:.4f}, improved {improved}/{len(results)}",
        'mean_delta': round(mean_delta, 4), 'improved': improved, 'total': len(results),
        'patients': results,
    }


def exp_612_piecewise_kalman(patients, detail=False):
    """EXP-612: Piecewise-corrected predictions fed to Kalman filter."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        resid = dbg - combined

        # piecewise correction
        bias, _ = _compute_piecewise_bias(bg, resid, split)
        corrected = combined + bias

        # Kalman filter on baseline combined
        train_resid_base = dbg[:split] - combined[:split]
        base_var = np.nanvar(train_resid_base[np.isfinite(train_resid_base)])

        def run_kalman(pred, Q_frac=0.2, R_frac=0.8):
            innov_var = base_var
            Q = innov_var * Q_frac; R = innov_var * R_frac
            x = bg[0] if np.isfinite(bg[0]) else 120.0
            P = R
            preds = np.full(n, np.nan)
            for t in range(1, n):
                x_prior = x + pred[t]
                P_prior = P + Q
                if np.isfinite(bg[t]):
                    K = P_prior / (P_prior + R)
                    innov = bg[t] - x_prior
                    x = x_prior + K * innov
                    P = (1 - K) * P_prior
                else:
                    x = x_prior; P = P_prior
                preds[t] = x_prior
            return preds

        # baseline: Kalman on combined
        kf_base = run_kalman(combined)
        # piecewise: Kalman on corrected
        kf_pw = run_kalman(corrected)

        test_mask = (np.arange(n) >= split) & np.isfinite(bg) & np.isfinite(kf_base) & np.isfinite(kf_pw)
        if test_mask.sum() < 50: continue

        # compute Kalman skill (vs naive persistence)
        err_base = np.abs(bg[test_mask] - kf_base[test_mask])
        err_pw = np.abs(bg[test_mask] - kf_pw[test_mask])
        err_naive = np.abs(np.diff(bg[np.isfinite(bg)]))
        naive_mae = np.mean(err_naive[-test_mask.sum():]) if len(err_naive) > test_mask.sum() else np.mean(err_naive)

        skill_base = 1.0 - np.mean(err_base) / naive_mae if naive_mae > 0 else 0
        skill_pw = 1.0 - np.mean(err_pw) / naive_mae if naive_mae > 0 else 0
        delta = skill_pw - skill_base

        results.append({
            'patient': p['name'],
            'skill_base': round(skill_base, 4), 'skill_pw': round(skill_pw, 4),
            'delta': round(delta, 4),
        })

    improved = sum(1 for r in results if r['delta'] > 0)
    mean_delta = np.mean([r['delta'] for r in results]) if results else 0
    return {
        'name': 'Piecewise Plus Kalman',
        'summary': f"Mean Δskill={mean_delta:.4f}, improved {improved}/{len(results)}",
        'mean_delta': round(mean_delta, 4), 'improved': improved, 'total': len(results),
        'patients': results,
    }


def exp_613_insulin_resistance_index(patients, detail=False):
    """EXP-613: Insulin resistance index from piecewise bias slope."""
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]
    midpoints = [55, 85, 125, 165, 215, 325]

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split = fa['bg'], fa['dbg'], fa['combined'], fa['split']
        resid = dbg - combined
        _, train_biases = _compute_piecewise_bias(bg, resid, split, ranges)

        bias_values = [train_biases.get(r, 0) for r in ranges]
        # fit linear slope: bias vs midpoint BG
        x = np.array(midpoints); y = np.array(bias_values)
        valid = np.isfinite(y) & (y != 0)
        if valid.sum() < 3: continue

        slope = np.polyfit(x[valid], y[valid], 1)[0]
        # negative slope = bias goes from positive (hypo) to negative (hyper) = insulin resistance gradient
        ir_index = -slope * 100  # scale for readability

        # also compute as hypo_bias - hyper_bias
        hypo_bias = bias_values[0]  # <70
        hyper_bias = np.mean(bias_values[3:])  # >150
        spread = hypo_bias - hyper_bias

        results.append({
            'patient': p['name'],
            'ir_index': round(ir_index, 3), 'slope': round(slope, 5),
            'hypo_bias': round(hypo_bias, 2), 'hyper_bias': round(hyper_bias, 2),
            'spread': round(spread, 2), 'biases': [round(b, 2) for b in bias_values],
        })

    if not results: return {'name': 'Insulin Resistance Index', 'summary': 'No data', 'patients': []}

    indices = [r['ir_index'] for r in results]
    spreads = [r['spread'] for r in results]
    sorted_by_ir = sorted(results, key=lambda x: x['ir_index'], reverse=True)

    return {
        'name': 'Insulin Resistance Index',
        'summary': f"Mean IR index={np.mean(indices):.2f}, spread={np.mean(spreads):.2f}, "
                   f"most resistant={sorted_by_ir[0]['patient']}, least={sorted_by_ir[-1]['patient']}",
        'mean_ir_index': round(np.mean(indices), 3),
        'mean_spread': round(np.mean(spreads), 2),
        'most_resistant': sorted_by_ir[0]['patient'],
        'least_resistant': sorted_by_ir[-1]['patient'],
        'patients': results,
    }


def exp_614_auto_settings_recommendation(patients, detail=False):
    """EXP-614: Derive recommended CR/ISF from flux balance analysis."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        df = p['df']; bg = fa['bg']; n = fa['n']
        supply = fa['supply']; demand = fa['demand']
        carb_supply = fa['carb_supply']; net = fa['net']

        # Get current settings
        isf_schedule = df.attrs.get('isf_schedule', [])
        cr_schedule = df.attrs.get('cr_schedule', [])
        units = df.attrs.get('profile_units', 'mg/dL')

        if not isf_schedule or not cr_schedule: continue

        current_isf = np.mean([e['value'] for e in isf_schedule])
        current_cr = np.mean([e['value'] for e in cr_schedule])
        if units == 'mmol/L' or current_isf < 15:
            current_isf *= 18.0182

        # Analyze effectiveness: when demand is high, how much does BG actually drop?
        # High demand windows (corrections/boluses)
        demand_thresh = np.percentile(demand[demand > 0], 75) if (demand > 0).sum() > 0 else 1
        high_demand = demand > demand_thresh

        # For ISF estimation: measure actual BG change per unit demand
        dbg = fa['dbg']
        valid = high_demand & np.isfinite(dbg) & (demand > 0)
        if valid.sum() < 20: continue

        # effective ISF = BG drop per unit insulin action
        actual_isf_eff = -dbg[valid] / demand[valid]
        actual_isf_mean = np.nanmedian(actual_isf_eff[np.isfinite(actual_isf_eff)])

        # For CR estimation: measure supply response to carb events
        high_carb = carb_supply > np.percentile(carb_supply[carb_supply > 0.1], 75) if (carb_supply > 0.1).sum() > 10 else carb_supply > 0.5
        carb_valid = high_carb & np.isfinite(dbg)
        if carb_valid.sum() < 10:
            cr_ratio = np.nan
        else:
            cr_ratio = np.nanmedian(carb_supply[carb_valid] / demand[carb_valid]) if np.nanmedian(demand[carb_valid]) > 0 else np.nan

        # Basal adequacy: overnight flux balance
        hour = np.zeros(n)
        if 'dateString' in df.columns:
            try:
                hour = df['dateString'].apply(lambda x: int(str(x)[11:13]) if len(str(x)) > 13 else 0).values.astype(float)
            except:
                pass

        overnight = (hour >= 0) & (hour < 6) & (carb_supply < 0.5)
        overnight_net = net[overnight & np.isfinite(net)]
        basal_balance = np.mean(overnight_net) if len(overnight_net) > 20 else 0
        # positive = rising (too little basal), negative = falling (too much)

        basal_assessment = 'adequate' if abs(basal_balance) < 0.3 else ('too_low' if basal_balance > 0 else 'too_high')

        results.append({
            'patient': p['name'],
            'current_isf': round(current_isf, 1),
            'effective_isf': round(actual_isf_mean, 2) if np.isfinite(actual_isf_mean) else None,
            'isf_ratio': round(actual_isf_mean / current_isf, 2) if np.isfinite(actual_isf_mean) and current_isf > 0 else None,
            'current_cr': round(current_cr, 1),
            'basal_balance': round(basal_balance, 3),
            'basal_assessment': basal_assessment,
        })

    isf_ratios = [r['isf_ratio'] for r in results if r['isf_ratio'] is not None]
    basal_issues = sum(1 for r in results if r['basal_assessment'] != 'adequate')

    return {
        'name': 'Auto Settings Recommendation',
        'summary': f"Mean ISF ratio (effective/profile)={np.mean(isf_ratios):.2f}, "
                   f"basal issues: {basal_issues}/{len(results)}",
        'mean_isf_ratio': round(np.mean(isf_ratios), 3) if isf_ratios else None,
        'basal_issues': basal_issues,
        'total': len(results),
        'patients': results,
    }


def exp_615_correction_protocol(patients, detail=False):
    """EXP-615: Evidence-based correction protocol from flux analysis."""
    results = []
    all_corrections = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, demand, n = fa['bg'], fa['demand'], fa['n']
        carb_supply = fa['carb_supply']

        # Find correction events: high demand, BG>160, low carb supply
        demand_thresh = np.percentile(demand[demand > 0], 70) if (demand > 0).sum() > 0 else 1
        corrections = []
        i = 0
        while i < n - 24:  # need 2h follow-up
            if demand[i] > demand_thresh and bg[i] > 160 and carb_supply[i] < 0.5 and np.isfinite(bg[i]):
                # track outcome
                bg_start = bg[i]
                bg_2h = bg[min(i+24, n-1)] if np.isfinite(bg[min(i+24, n-1)]) else np.nan
                bg_nadir = np.nanmin(bg[i:min(i+36, n)]) if np.any(np.isfinite(bg[i:min(i+36, n)])) else np.nan
                time_to_target = np.nan
                for j in range(i+1, min(i+48, n)):
                    if np.isfinite(bg[j]) and bg[j] < 150:
                        time_to_target = (j - i) * 5  # minutes
                        break

                # check IOB proxy (demand in preceding 3h)
                lookback = max(0, i-36)
                iob_proxy = np.mean(demand[lookback:i])

                delta_bg = bg_2h - bg_start if np.isfinite(bg_2h) else np.nan
                success = 1 if np.isfinite(bg_2h) and bg_2h < 150 else 0

                corrections.append({
                    'bg_start': bg_start, 'bg_2h': bg_2h, 'delta': delta_bg,
                    'nadir': bg_nadir, 'time_to_target': time_to_target,
                    'success': success, 'iob_proxy': iob_proxy,
                    'demand': demand[i],
                })
                all_corrections.append(corrections[-1])
                i += 24  # skip 2h
            else:
                i += 1

        if not corrections: continue

        success_rate = np.mean([c['success'] for c in corrections])
        mean_delta = np.nanmean([c['delta'] for c in corrections])
        mean_ttt = np.nanmean([c['time_to_target'] for c in corrections if np.isfinite(c['time_to_target'])])

        results.append({
            'patient': p['name'],
            'n_corrections': len(corrections),
            'success_rate': round(success_rate, 3),
            'mean_delta_bg': round(mean_delta, 1) if np.isfinite(mean_delta) else None,
            'mean_time_to_target': round(mean_ttt, 0) if np.isfinite(mean_ttt) else None,
        })

    # Population protocol analysis
    if all_corrections:
        # Stratify by starting BG
        bg_strata = [(160, 200, 'mild_high'), (200, 250, 'high'), (250, 350, 'very_high')]
        strata_results = []
        for lo, hi, name in bg_strata:
            stratum = [c for c in all_corrections if lo <= c['bg_start'] < hi]
            if stratum:
                strata_results.append({
                    'range': name, 'n': len(stratum),
                    'success_rate': round(np.mean([c['success'] for c in stratum]), 3),
                    'mean_delta': round(np.nanmean([c['delta'] for c in stratum]), 1),
                })
    else:
        strata_results = []

    total_corr = len(all_corrections)
    overall_success = np.mean([c['success'] for c in all_corrections]) if all_corrections else 0

    return {
        'name': 'Correction Protocol',
        'summary': f"{total_corr} corrections, {overall_success:.1%} success, "
                   f"stratified by starting BG",
        'total_corrections': total_corr,
        'overall_success': round(overall_success, 3),
        'strata': strata_results,
        'patients': results,
    }


def exp_616_weekly_report_card(patients, detail=False):
    """EXP-616: Automated weekly assessment combining all metrics."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, demand, supply, n = fa['bg'], fa['demand'], fa['supply'], fa['n']
        carb_supply = fa['carb_supply']; net = fa['net']

        # Divide into weeks
        steps_per_week = 7 * 288  # 7 days × 288 5-min steps
        n_weeks = n // steps_per_week
        if n_weeks < 2: continue

        weekly_scores = []
        for w in range(n_weeks):
            s = w * steps_per_week
            e = s + steps_per_week
            bg_w = bg[s:e]
            valid_bg = bg_w[np.isfinite(bg_w)]
            if len(valid_bg) < 100: continue

            tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))
            tbr = np.mean(valid_bg < 70)
            tar = np.mean(valid_bg > 180)
            cv = np.std(valid_bg) / np.mean(valid_bg) if np.mean(valid_bg) > 0 else 1
            mean_bg = np.mean(valid_bg)

            # flux balance score
            net_w = net[s:e]
            flux_var = np.nanvar(net_w[np.isfinite(net_w)])

            # stacking proxy: demand peaks close together
            d_w = demand[s:e]
            d_thresh = np.percentile(d_w[d_w > 0], 80) if (d_w > 0).sum() > 10 else 1
            peaks = np.where(d_w > d_thresh)[0]
            if len(peaks) > 1:
                gaps = np.diff(peaks) * 5  # minutes
                stacking_rate = np.mean(gaps < 120) if len(gaps) > 0 else 0
            else:
                stacking_rate = 0

            # composite
            score = (tir * 40 + (1 - tbr) * 20 + (1 - min(cv, 0.5)/0.5) * 20 +
                     (1 - min(stacking_rate, 0.5)/0.5) * 10 + (1 - min(tar, 0.5)/0.5) * 10)

            weekly_scores.append({
                'week': w + 1, 'tir': round(tir, 3), 'tbr': round(tbr, 4),
                'tar': round(tar, 3), 'cv': round(cv, 3), 'mean_bg': round(mean_bg, 1),
                'stacking_rate': round(stacking_rate, 3), 'score': round(score, 1),
            })

        if len(weekly_scores) < 2: continue

        scores = [w['score'] for w in weekly_scores]
        # trend
        x = np.arange(len(scores))
        if len(scores) > 1:
            slope = np.polyfit(x, scores, 1)[0]
        else:
            slope = 0

        trajectory = 'improving' if slope > 0.5 else ('declining' if slope < -0.5 else 'stable')

        results.append({
            'patient': p['name'],
            'n_weeks': len(weekly_scores),
            'mean_score': round(np.mean(scores), 1),
            'score_trend': round(slope, 2),
            'trajectory': trajectory,
            'first_week_score': weekly_scores[0]['score'],
            'last_week_score': weekly_scores[-1]['score'],
            'best_week': max(weekly_scores, key=lambda w: w['score'])['week'],
            'worst_week': min(weekly_scores, key=lambda w: w['score'])['week'],
        })

    trajectories = [r['trajectory'] for r in results]
    improving = trajectories.count('improving')
    declining = trajectories.count('declining')
    stable = trajectories.count('stable')

    return {
        'name': 'Weekly Report Card',
        'summary': f"Trajectories: {improving} improving, {stable} stable, {declining} declining",
        'improving': improving, 'stable': stable, 'declining': declining,
        'total': len(results),
        'patients': results,
    }


def exp_617_loo_piecewise(patients, detail=False):
    """EXP-617: Leave-one-out validation of population piecewise bias."""
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    # First, compute all patients' biases
    all_biases = {}
    all_fa = {}
    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        all_fa[p['name']] = fa
        bg, dbg, combined, split = fa['bg'], fa['dbg'], fa['combined'], fa['split']
        resid = dbg - combined
        _, biases = _compute_piecewise_bias(bg, resid, split, ranges)
        all_biases[p['name']] = biases

    if len(all_biases) < 3:
        return {'name': 'LOO Piecewise', 'summary': 'Insufficient patients', 'patients': []}

    patient_names = list(all_biases.keys())

    for held_out in patient_names:
        # Population bias from all except held_out
        pop_bias = {}
        for r in ranges:
            vals = [all_biases[pn][r] for pn in patient_names if pn != held_out]
            pop_bias[r] = np.mean(vals)

        # Apply to held_out test data
        fa = all_fa[held_out]
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']

        # personal bias
        personal_bias = np.zeros(n)
        for (lo, hi), b in all_biases[held_out].items():
            mask = (bg >= lo) & (bg < hi)
            personal_bias[mask] = b

        # population bias
        pop_bias_arr = np.zeros(n)
        for (lo, hi), b in pop_bias.items():
            mask = (bg >= lo) & (bg < hi)
            pop_bias_arr[mask] = b

        # evaluate test set
        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() < 50: continue

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        r2_none = 1.0 - np.sum((dbg[test_mask] - combined[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        r2_personal = 1.0 - np.sum((dbg[test_mask] - (combined + personal_bias)[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        r2_pop = 1.0 - np.sum((dbg[test_mask] - (combined + pop_bias_arr)[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        results.append({
            'patient': held_out,
            'r2_none': round(r2_none, 4), 'r2_personal': round(r2_personal, 4),
            'r2_population': round(r2_pop, 4),
            'delta_pop_vs_none': round(r2_pop - r2_none, 4),
            'delta_personal_vs_pop': round(r2_personal - r2_pop, 4),
        })

    pop_improved = sum(1 for r in results if r['delta_pop_vs_none'] > 0)
    mean_pop_delta = np.mean([r['delta_pop_vs_none'] for r in results])
    mean_personal_advantage = np.mean([r['delta_personal_vs_pop'] for r in results])

    return {
        'name': 'Leave-One-Out Piecewise Transfer',
        'summary': f"Population bias improves {pop_improved}/{len(results)}, "
                   f"mean ΔR²={mean_pop_delta:.4f}, personal advantage={mean_personal_advantage:.4f}",
        'pop_improved': pop_improved, 'total': len(results),
        'mean_pop_delta': round(mean_pop_delta, 4),
        'mean_personal_advantage': round(mean_personal_advantage, 4),
        'patients': results,
    }


def exp_618_cluster_specific_bias(patients, detail=False):
    """EXP-618: Cluster-specific piecewise bias vs population vs personal."""
    from sklearn.cluster import KMeans
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    # Compute features for clustering + biases
    all_fa = {}; all_biases = {}; features = []
    names = []
    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        all_fa[p['name']] = fa
        bg, dbg, combined, split = fa['bg'], fa['dbg'], fa['combined'], fa['split']
        resid = dbg - combined
        _, biases = _compute_piecewise_bias(bg, resid, split, ranges)
        all_biases[p['name']] = biases

        valid_bg = bg[np.isfinite(bg)]
        feat = [np.mean(valid_bg), np.std(valid_bg),
                np.mean(valid_bg < 70), np.mean(valid_bg > 180)]
        features.append(feat)
        names.append(p['name'])

    if len(names) < 6:
        return {'name': 'Cluster-Specific Bias', 'summary': 'Too few patients', 'patients': []}

    # Cluster
    X = np.array(features)
    X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    km = KMeans(n_clusters=3, random_state=42, n_init=10)
    labels = km.fit_predict(X_norm)
    name_to_cluster = {n: int(l) for n, l in zip(names, labels)}

    # For each patient, compare: no bias, personal, cluster, population
    for held_out in names:
        my_cluster = name_to_cluster[held_out]

        # cluster bias (from same cluster, excluding self)
        cluster_bias = {}
        for r in ranges:
            vals = [all_biases[n][r] for n in names if n != held_out and name_to_cluster[n] == my_cluster]
            cluster_bias[r] = np.mean(vals) if vals else 0

        # population bias (excluding self)
        pop_bias = {}
        for r in ranges:
            vals = [all_biases[n][r] for n in names if n != held_out]
            pop_bias[r] = np.mean(vals)

        fa = all_fa[held_out]
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']

        # Apply biases
        def apply_bias(bias_dict):
            arr = np.zeros(n)
            for (lo, hi), b in bias_dict.items():
                mask = (bg >= lo) & (bg < hi)
                arr[mask] = b
            return arr

        bias_personal = apply_bias(all_biases[held_out])
        bias_cluster = apply_bias(cluster_bias)
        bias_pop = apply_bias(pop_bias)

        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() < 50: continue

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        if ss_tot == 0: continue

        r2_none = 1.0 - np.sum((dbg[test_mask] - combined[test_mask])**2) / ss_tot
        r2_personal = 1.0 - np.sum((dbg[test_mask] - (combined + bias_personal)[test_mask])**2) / ss_tot
        r2_cluster = 1.0 - np.sum((dbg[test_mask] - (combined + bias_cluster)[test_mask])**2) / ss_tot
        r2_pop = 1.0 - np.sum((dbg[test_mask] - (combined + bias_pop)[test_mask])**2) / ss_tot

        results.append({
            'patient': held_out, 'cluster': my_cluster,
            'r2_none': round(r2_none, 4), 'r2_personal': round(r2_personal, 4),
            'r2_cluster': round(r2_cluster, 4), 'r2_population': round(r2_pop, 4),
            'cluster_vs_pop': round(r2_cluster - r2_pop, 4),
        })

    cluster_better = sum(1 for r in results if r['cluster_vs_pop'] > 0)
    mean_cluster_adv = np.mean([r['cluster_vs_pop'] for r in results]) if results else 0

    return {
        'name': 'Cluster-Specific Bias',
        'summary': f"Cluster beats population {cluster_better}/{len(results)}, "
                   f"mean advantage={mean_cluster_adv:.4f}",
        'cluster_better': cluster_better, 'total': len(results),
        'mean_cluster_advantage': round(mean_cluster_adv, 4),
        'patients': results,
    }


def exp_619_nonlinear_flux(patients, detail=False):
    """EXP-619: Nonlinear flux model with quadratic and sigmoid terms."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        demand = fa['demand']; supply = fa['supply']

        # Current model is linear: dbg ≈ flux + AR
        # Try adding nonlinear terms
        resid = dbg - combined

        # Feature engineering: bg², demand², bg×demand, sigmoid(bg)
        bg_centered = bg - 120  # center around normal
        bg2 = bg_centered**2 / 10000  # scaled
        dem2 = demand**2 / 100
        bg_dem = bg_centered * demand / 1000
        sig_bg = 1.0 / (1.0 + np.exp(-bg_centered / 30))  # sigmoid around 120

        X_nl = np.column_stack([bg2, dem2, bg_dem, sig_bg])
        mask = np.isfinite(X_nl).all(axis=1) & np.isfinite(resid)

        train_mask = mask.copy(); train_mask[split:] = False
        test_mask = mask.copy(); test_mask[:split] = False

        if train_mask.sum() < 20 or test_mask.sum() < 20: continue

        # fit on train
        XtX = X_nl[train_mask].T @ X_nl[train_mask]
        Xty = X_nl[train_mask].T @ resid[train_mask]
        lam = 1e-4
        coef = np.linalg.solve(XtX + lam * np.eye(4), Xty)

        nl_pred = np.zeros(n)
        nl_ok = np.isfinite(X_nl).all(axis=1)
        nl_pred[nl_ok] = X_nl[nl_ok] @ coef

        corrected = combined + nl_pred

        # compare
        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        r2_base = 1.0 - np.sum((dbg[test_mask] - combined[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        r2_nl = 1.0 - np.sum((dbg[test_mask] - corrected[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        # also compare with piecewise
        bias, _ = _compute_piecewise_bias(bg, dbg - combined, split)
        r2_pw = 1.0 - np.sum((dbg[test_mask] - (combined + bias)[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        results.append({
            'patient': p['name'],
            'r2_base': round(r2_base, 4), 'r2_nonlinear': round(r2_nl, 4),
            'r2_piecewise': round(r2_pw, 4),
            'nl_vs_base': round(r2_nl - r2_base, 4),
            'nl_vs_pw': round(r2_nl - r2_pw, 4),
            'coefs': {
                'bg_squared': round(coef[0], 5),
                'demand_squared': round(coef[1], 5),
                'bg_x_demand': round(coef[2], 5),
                'sigmoid_bg': round(coef[3], 5),
            }
        })

    nl_beats_base = sum(1 for r in results if r['nl_vs_base'] > 0)
    nl_beats_pw = sum(1 for r in results if r['nl_vs_pw'] > 0)
    mean_nl_delta = np.mean([r['nl_vs_base'] for r in results]) if results else 0

    return {
        'name': 'Nonlinear Flux Model',
        'summary': f"NL beats base {nl_beats_base}/{len(results)} (ΔR²={mean_nl_delta:.4f}), "
                   f"NL beats piecewise {nl_beats_pw}/{len(results)}",
        'nl_beats_base': nl_beats_base, 'nl_beats_piecewise': nl_beats_pw,
        'total': len(results), 'mean_nl_delta': round(mean_nl_delta, 4),
        'patients': results,
    }


def exp_620_composite_score_v2(patients, detail=False):
    """EXP-620: Enhanced clinical score v2 with piecewise R² and stacking."""
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        demand = fa['demand']; supply = fa['supply']
        carb_supply = fa['carb_supply']; net = fa['net']
        resid = dbg - combined

        valid_bg = bg[np.isfinite(bg)]
        if len(valid_bg) < 500: continue

        # Component 1: TIR (0-20 pts)
        tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))
        tir_score = tir * 20

        # Component 2: Hypo safety (0-20 pts)
        tbr = np.mean(valid_bg < 70)
        hypo_score = max(0, (1 - tbr / 0.04)) * 20  # 4% = 0 points

        # Component 3: Variability (0-15 pts)
        cv = np.std(valid_bg) / np.mean(valid_bg) if np.mean(valid_bg) > 0 else 1
        cv_score = max(0, (1 - cv / 0.5)) * 15

        # Component 4: Model fit (0-15 pts) - NEW: piecewise R²
        bias, _ = _compute_piecewise_bias(bg, resid, split, ranges)
        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() > 50:
            ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
            r2_pw = 1.0 - np.sum((dbg[test_mask] - (combined + bias)[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        else:
            r2_pw = 0
        model_score = max(0, r2_pw) * 15

        # Component 5: Stacking avoidance (0-10 pts) - NEW
        demand_thresh = np.percentile(demand[demand > 0], 80) if (demand > 0).sum() > 10 else 1
        peaks = np.where(demand > demand_thresh)[0]
        if len(peaks) > 1:
            gaps = np.diff(peaks) * 5
            stacking_rate = np.mean(gaps < 120)
        else:
            stacking_rate = 0
        stacking_score = max(0, (1 - stacking_rate / 0.3)) * 10

        # Component 6: Flux balance (0-10 pts) - overnight balance
        hour = np.zeros(n)
        if 'dateString' in p['df'].columns:
            try:
                hour = p['df']['dateString'].apply(
                    lambda x: int(str(x)[11:13]) if len(str(x)) > 13 else 0
                ).values.astype(float)
            except:
                pass
        overnight = (hour >= 0) & (hour < 6) & (carb_supply < 0.5)
        overnight_net = net[overnight & np.isfinite(net)]
        balance = abs(np.mean(overnight_net)) if len(overnight_net) > 20 else 1.0
        balance_score = max(0, (1 - balance / 1.0)) * 10

        # Component 7: IR gradient (0-10 pts) - NEW: smaller gradient = better
        _, biases = _compute_piecewise_bias(bg, resid, split, ranges)
        hypo_bias = biases.get((0, 70), 0)
        hyper_bias = np.mean([biases.get(r, 0) for r in [(180, 250), (250, 500)]])
        ir_spread = hypo_bias - hyper_bias
        ir_score = max(0, (1 - abs(ir_spread) / 15)) * 10

        total_v2 = tir_score + hypo_score + cv_score + model_score + stacking_score + balance_score + ir_score

        # Also compute v1 for comparison
        # v1: TIR(40) + safety(20) + CV(20) + stacking(10) + TAR(10)
        tar = np.mean(valid_bg > 180)
        v1 = tir * 40 + (1 - tbr) * 20 + (1 - min(cv, 0.5)/0.5) * 20 + (1 - min(stacking_rate, 0.5)/0.5) * 10 + (1 - min(tar, 0.5)/0.5) * 10

        results.append({
            'patient': p['name'],
            'score_v1': round(v1, 1), 'score_v2': round(total_v2, 1),
            'components': {
                'tir': round(tir_score, 1), 'hypo_safety': round(hypo_score, 1),
                'cv': round(cv_score, 1), 'model_fit': round(model_score, 1),
                'stacking': round(stacking_score, 1), 'balance': round(balance_score, 1),
                'ir_gradient': round(ir_score, 1),
            },
            'delta_v2_v1': round(total_v2 - v1, 1),
        })

    # Grade assignments
    for r in results:
        s = r['score_v2']
        r['grade'] = 'A' if s >= 80 else ('B' if s >= 65 else ('C' if s >= 50 else 'D'))

    grades = [r['grade'] for r in results]
    sorted_results = sorted(results, key=lambda x: x['score_v2'], reverse=True)
    corr_v1_v2 = np.corrcoef([r['score_v1'] for r in results], [r['score_v2'] for r in results])[0, 1] if len(results) > 2 else 0

    return {
        'name': 'Composite Clinical Score v2',
        'summary': f"7-component score: A={grades.count('A')}, B={grades.count('B')}, "
                   f"C={grades.count('C')}, D={grades.count('D')}, r(v1,v2)={corr_v1_v2:.3f}",
        'grades': {'A': grades.count('A'), 'B': grades.count('B'),
                   'C': grades.count('C'), 'D': grades.count('D')},
        'correlation_v1_v2': round(corr_v1_v2, 3),
        'best': sorted_results[0]['patient'] if sorted_results else None,
        'worst': sorted_results[-1]['patient'] if sorted_results else None,
        'patients': results,
    }


# ── Main ────────────────────────────────────────────────────────────────────

EXPERIMENTS = [
    ('EXP-611', exp_611_time_varying_bias),
    ('EXP-612', exp_612_piecewise_kalman),
    ('EXP-613', exp_613_insulin_resistance_index),
    ('EXP-614', exp_614_auto_settings_recommendation),
    ('EXP-615', exp_615_correction_protocol),
    ('EXP-616', exp_616_weekly_report_card),
    ('EXP-617', exp_617_loo_piecewise),
    ('EXP-618', exp_618_cluster_specific_bias),
    ('EXP-619', exp_619_nonlinear_flux),
    ('EXP-620', exp_620_composite_score_v2),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-patients', type=int, default=11)
    ap.add_argument('--detail', action='store_true')
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--exp', type=str, help='Run single experiment, e.g. EXP-611')
    args = ap.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    exps = EXPERIMENTS
    if args.exp:
        exps = [(eid, fn) for eid, fn in EXPERIMENTS if eid == args.exp]
        if not exps:
            print(f"Unknown experiment: {args.exp}")
            sys.exit(1)

    for eid, fn in exps:
        print(f"{'='*60}")
        print(f"Running {eid}: {fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'='*60}")
        try:
            result = fn(patients, detail=args.detail)
            print(f"\n  RESULT: {result.get('summary', 'done')}")
            if args.detail and 'patients' in result:
                for pr in result['patients']:
                    print(f"    {pr}")
            if args.save:
                safe_name = result['name'].lower().replace(' ', '_').replace('/', '_')[:30]
                fname = RESULTS_DIR / f"{eid.lower()}_{safe_name}.json"
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fname.name}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            import traceback; traceback.print_exc()
        print()


if __name__ == '__main__':
    main()
