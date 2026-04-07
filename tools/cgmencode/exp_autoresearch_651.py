#!/usr/bin/env python3
"""EXP-651-660: Ensemble hypo, anomaly classification, clinical dashboard, live validation.

Wave 15 of autoresearch — combining hypo methods, residual characterization,
clinical reporting, settings recommendations, and production validation.
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

sys.path.insert(0, str(Path(__file__).parent))
from exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand


def _build_joint_features(resid, bg, demand, order=6):
    """Build joint NL+AR features."""
    n = len(resid)
    n_feat = order + 4
    X = np.zeros((n, n_feat))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid[:-lag] if lag < n else 0
    bg_c = bg[:n] - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand[:n] ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand[:n] / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    return X


def _fit_ridge(X_train, y_train, X_test, lam=10.0):
    """Fit ridge regression and predict."""
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    Xty = X_train.T @ y_train
    beta = np.linalg.solve(XtX, Xty)
    pred = X_test @ beta
    return beta, pred


def _compute_flux(df, pk, bg):
    """Compute supply-demand decomposition and flux prediction."""
    sd = compute_supply_demand(df, pk)
    supply = sd['supply']
    demand = sd['demand']
    hepatic = sd['hepatic']
    bg_decay = (120.0 - bg) * 0.005
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    return sd, flux_pred, resid, bg_decay


def run_exp_651(patients, detail=False):
    """EXP-651: Ensemble hypo alert — combine flux-trajectory + adaptive threshold."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd = compute_supply_demand(df, pk)
        net = sd['supply'] - sd['demand'] + sd['hepatic']

        n = len(bg)
        split = int(0.8 * n)
        test_bg = bg[split:]
        test_net = net[split:]
        n_test = len(test_bg)

        actual_hypo = test_bg < 70
        if actual_hypo.sum() < 5:
            continue

        slope = np.concatenate([[0], np.diff(test_bg)])

        # Method 1: Adaptive threshold (BG<80 + slope<-0.5)
        alert_adaptive = (test_bg < 80) & (slope < -0.5)

        # Method 2: Flux trajectory (BG + cumulative 30min net < 70)
        cum_flux = np.zeros(n_test)
        for step in range(1, 7):
            shifted = np.roll(test_net, -step)
            shifted[-step:] = 0
            cum_flux += shifted
        pred_30 = test_bg + cum_flux
        alert_flux = pred_30 < 70

        # Ensemble: OR (maximize recall)
        alert_or = alert_adaptive | alert_flux
        # Ensemble: AND (maximize precision)
        alert_and = alert_adaptive & alert_flux
        # Ensemble: weighted vote (alert if either strong or both mild)
        alert_vote = alert_flux | (alert_adaptive & (test_bg < 75))

        test_weeks = (n - split) / (12 * 24 * 7)
        methods = {
            'adaptive': alert_adaptive,
            'flux': alert_flux,
            'ensemble_or': alert_or,
            'ensemble_and': alert_and,
            'ensemble_vote': alert_vote,
        }

        row = {'patient': p['name'], 'n_hypo': int(actual_hypo.sum())}
        for name, alert in methods.items():
            tp = np.sum(alert & actual_hypo)
            fp = np.sum(alert & ~actual_hypo)
            fn = np.sum(~alert & actual_hypo)
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            row[f'{name}_f1'] = round(float(f1), 3)
            row[f'{name}_prec'] = round(float(prec), 3)
            row[f'{name}_fp_wk'] = round(float(fp / test_weeks), 1) if test_weeks > 0 else 0

        results.append(row)
        if detail:
            print(f"    {p['name']}: adapt={row['adaptive_f1']:.3f} flux={row['flux_f1']:.3f} "
                  f"OR={row['ensemble_or_f1']:.3f} AND={row['ensemble_and_f1']:.3f} "
                  f"vote={row['ensemble_vote_f1']:.3f}")

    mean_adapt = np.mean([r['adaptive_f1'] for r in results])
    mean_flux = np.mean([r['flux_f1'] for r in results])
    mean_or = np.mean([r['ensemble_or_f1'] for r in results])
    mean_and = np.mean([r['ensemble_and_f1'] for r in results])
    mean_vote = np.mean([r['ensemble_vote_f1'] for r in results])
    best = max([('adapt', mean_adapt), ('flux', mean_flux), ('OR', mean_or),
                ('AND', mean_and), ('vote', mean_vote)], key=lambda x: x[1])
    summary = (f"adapt={mean_adapt:.3f} flux={mean_flux:.3f} OR={mean_or:.3f} "
               f"AND={mean_and:.3f} vote={mean_vote:.3f}, best={best[0]}")
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-651: Ensemble Hypo Alert', 'summary': summary, 'details': results}


def run_exp_652(patients, detail=False):
    """EXP-652: Hypo Lead Time — how early does each method warn?"""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd = compute_supply_demand(df, pk)
        net = sd['supply'] - sd['demand'] + sd['hepatic']

        n = len(bg)
        split = int(0.8 * n)
        test_bg = bg[split:]
        test_net = net[split:]
        n_test = len(test_bg)

        slope = np.concatenate([[0], np.diff(test_bg)])

        # Identify hypo events (BG drops below 70 and stays for at least 2 steps)
        hypo_starts = []
        in_hypo = False
        for t in range(n_test):
            if test_bg[t] < 70 and not in_hypo:
                hypo_starts.append(t)
                in_hypo = True
            elif test_bg[t] >= 80:
                in_hypo = False

        if len(hypo_starts) < 3:
            continue

        # For each hypo event, find earliest alert from each method
        alert_adaptive = (test_bg < 80) & (slope < -0.5)
        cum_flux = np.zeros(n_test)
        for step in range(1, 7):
            shifted = np.roll(test_net, -step)
            shifted[-step:] = 0
            cum_flux += shifted
        alert_flux = (test_bg + cum_flux) < 70

        lead_adaptive = []
        lead_flux = []
        for hs in hypo_starts:
            # Look back up to 60 min (12 steps) for earliest alert
            lookback = max(0, hs - 12)
            adapt_lead = None
            flux_lead = None
            for t in range(lookback, hs):
                if alert_adaptive[t] and adapt_lead is None:
                    adapt_lead = (hs - t) * 5  # minutes
                if alert_flux[t] and flux_lead is None:
                    flux_lead = (hs - t) * 5
            if adapt_lead is not None:
                lead_adaptive.append(adapt_lead)
            if flux_lead is not None:
                lead_flux.append(flux_lead)

        result = {
            'patient': p['name'],
            'n_events': len(hypo_starts),
            'adaptive_alerts': len(lead_adaptive),
            'adaptive_mean_lead_min': round(np.mean(lead_adaptive), 1) if lead_adaptive else 0,
            'flux_alerts': len(lead_flux),
            'flux_mean_lead_min': round(np.mean(lead_flux), 1) if lead_flux else 0,
            'flux_caught_pct': round(len(lead_flux) / len(hypo_starts) * 100, 1),
            'adaptive_caught_pct': round(len(lead_adaptive) / len(hypo_starts) * 100, 1),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_adapt_lead = np.mean([r['adaptive_mean_lead_min'] for r in results if r['adaptive_mean_lead_min'] > 0])
    mean_flux_lead = np.mean([r['flux_mean_lead_min'] for r in results if r['flux_mean_lead_min'] > 0])
    mean_flux_caught = np.mean([r['flux_caught_pct'] for r in results])
    summary = f"Adapt lead={mean_adapt_lead:.0f}min, Flux lead={mean_flux_lead:.0f}min, Flux caught={mean_flux_caught:.0f}%"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-652: Hypo Lead Time', 'summary': summary, 'details': results}


def run_exp_653(patients, detail=False):
    """EXP-653: Hypo Severity — flux integral predicts nadir depth."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd = compute_supply_demand(df, pk)
        net = sd['supply'] - sd['demand'] + sd['hepatic']

        n = len(bg)
        split = int(0.8 * n)
        test_bg = bg[split:]
        test_net = net[split:]

        # Find hypo events and measure nadir
        hypo_events = []
        in_hypo = False
        event_start = 0
        for t in range(len(test_bg)):
            if test_bg[t] < 70 and not in_hypo:
                event_start = t
                in_hypo = True
            elif test_bg[t] >= 80 and in_hypo:
                nadir = np.min(test_bg[event_start:t + 1])
                # Compute flux integral in 30-min window before event
                pre_start = max(0, event_start - 6)
                flux_integral = np.sum(test_net[pre_start:event_start])
                hypo_events.append({
                    'nadir': float(nadir),
                    'flux_integral': float(flux_integral),
                    'pre_bg': float(test_bg[max(0, event_start - 6)]),
                    'duration_min': (t - event_start) * 5,
                })
                in_hypo = False

        if len(hypo_events) < 5:
            continue

        nadirs = np.array([e['nadir'] for e in hypo_events])
        flux_ints = np.array([e['flux_integral'] for e in hypo_events])
        pre_bgs = np.array([e['pre_bg'] for e in hypo_events])
        durations = np.array([e['duration_min'] for e in hypo_events])

        # Correlation: flux integral vs nadir
        valid = np.isfinite(flux_ints) & np.isfinite(nadirs)
        if valid.sum() < 5:
            continue
        corr_flux_nadir = np.corrcoef(flux_ints[valid], nadirs[valid])[0, 1]
        corr_prebg_nadir = np.corrcoef(pre_bgs[valid], nadirs[valid])[0, 1]

        result = {
            'patient': p['name'],
            'n_events': len(hypo_events),
            'mean_nadir': round(float(np.mean(nadirs)), 1),
            'mean_duration_min': round(float(np.mean(durations)), 1),
            'corr_flux_nadir': round(float(corr_flux_nadir), 3),
            'corr_prebg_nadir': round(float(corr_prebg_nadir), 3),
            'mean_pre_flux': round(float(np.mean(flux_ints)), 2),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_corr = np.mean([r['corr_flux_nadir'] for r in results])
    mean_prebg_corr = np.mean([r['corr_prebg_nadir'] for r in results])
    summary = f"r(flux,nadir)={mean_corr:.3f}, r(preBG,nadir)={mean_prebg_corr:.3f}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-653: Hypo Severity Prediction', 'summary': summary, 'details': results}


def run_exp_654(patients, detail=False):
    """EXP-654: Anomaly Classification — classify 3σ events by context."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd, flux_pred, resid, bg_decay = _compute_flux(df, pk, bg)
        carb_supply = sd['carb_supply']

        valid = np.isfinite(resid)
        mu = np.mean(resid[valid])
        sigma = np.std(resid[valid])
        if sigma < 0.1:
            continue

        anomaly_mask = np.abs(resid - mu) > 3 * sigma
        anomaly_idx = np.where(anomaly_mask & valid)[0]

        # Classify by context
        categories = {'meal_related': 0, 'high_bg': 0, 'low_bg': 0,
                       'dawn': 0, 'overnight': 0, 'daytime': 0}
        for idx in anomaly_idx:
            # Time of day (assuming 288 steps/day)
            tod = (idx % 288) / 12  # hour of day
            bg_val = bg[idx + 1] if idx + 1 < len(bg) else bg[idx]

            if carb_supply[idx] > 1.0:
                categories['meal_related'] += 1
            elif bg_val > 200:
                categories['high_bg'] += 1
            elif bg_val < 80:
                categories['low_bg'] += 1
            elif 4 <= tod <= 8:
                categories['dawn'] += 1
            elif tod < 6 or tod >= 22:
                categories['overnight'] += 1
            else:
                categories['daytime'] += 1

        total = len(anomaly_idx)
        pcts = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in categories.items()}
        result = {
            'patient': p['name'],
            'total_anomalies': total,
            'categories': pcts,
            'dominant': max(pcts, key=pcts.get) if pcts else 'none',
        }
        results.append(result)
        if detail:
            print(f"    {p['name']}: {total} anomalies — {pcts}")

    # Aggregate
    all_cats = {}
    for r in results:
        for k, v in r['categories'].items():
            all_cats.setdefault(k, []).append(v)
    mean_cats = {k: round(np.mean(v), 1) for k, v in all_cats.items()}
    summary = f"Mean categories: {mean_cats}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-654: Anomaly Classification', 'summary': summary, 'details': results}


def run_exp_655(patients, detail=False):
    """EXP-655: Residual Autocorrelation — structure at longer lags."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd, flux_pred, resid, bg_decay = _compute_flux(df, pk, bg)

        valid = np.isfinite(resid)
        r = resid[valid]
        r = r - np.mean(r)
        n = len(r)

        # Compute ACF at specific lags
        var = np.var(r)
        if var < 1e-10:
            continue

        lags = [1, 3, 6, 12, 24, 36, 48, 72, 144, 288]  # 5min to 24h
        acf = {}
        for lag in lags:
            if lag >= n:
                continue
            c = np.mean(r[lag:] * r[:-lag]) / var
            acf[lag] = round(float(c), 4)

        # Find first lag where ACF drops below 0.05
        decorrelation_lag = None
        for lag in sorted(acf.keys()):
            if abs(acf[lag]) < 0.05:
                decorrelation_lag = lag
                break

        result = {
            'patient': p['name'],
            'acf': acf,
            'decorrelation_lag': decorrelation_lag,
            'decorrelation_min': decorrelation_lag * 5 if decorrelation_lag else None,
            'acf_1step': acf.get(1, 0),
            'acf_30min': acf.get(6, 0),
            'acf_2h': acf.get(24, 0),
            'acf_6h': acf.get(72, 0),
            'acf_24h': acf.get(288, 0),
        }
        results.append(result)
        if detail:
            print(f"    {p['name']}: ACF(5m)={acf.get(1, 0):.3f} ACF(30m)={acf.get(6, 0):.3f} "
                  f"ACF(2h)={acf.get(24, 0):.3f} ACF(24h)={acf.get(288, 0):.3f} "
                  f"decorr={result['decorrelation_min']}min")

    mean_acf1 = np.mean([r['acf_1step'] for r in results])
    mean_acf30 = np.mean([r['acf_30min'] for r in results])
    mean_acf2h = np.mean([r['acf_2h'] for r in results])
    mean_acf24h = np.mean([r['acf_24h'] for r in results])
    decorr_vals = [r['decorrelation_min'] for r in results if r['decorrelation_min'] is not None]
    mean_decorr = np.mean(decorr_vals) if decorr_vals else 0
    summary = (f"ACF: 5m={mean_acf1:.3f}, 30m={mean_acf30:.3f}, 2h={mean_acf2h:.3f}, "
               f"24h={mean_acf24h:.3f}, decorr={mean_decorr:.0f}min")
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-655: Residual Autocorrelation', 'summary': summary, 'details': results}


def run_exp_656(patients, detail=False):
    """EXP-656: Biweekly Report Card — actionable clinical summary."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd = compute_supply_demand(df, pk)
        net = sd['supply'] - sd['demand'] + sd['hepatic']
        resid_raw = np.diff(bg) - (sd['supply'][:-1] - sd['demand'][:-1] + sd['hepatic'][:-1] + (120.0 - bg[:-1]) * 0.005)

        n = len(bg)
        # Last biweekly window
        window = 4032
        if n < window:
            continue
        w_start = n - window
        w_bg = bg[w_start:]
        w_net = net[w_start:]
        w_resid = resid_raw[w_start:] if w_start < len(resid_raw) else resid_raw[-window:]
        valid = np.isfinite(w_bg)

        tir = np.mean((w_bg[valid] >= 70) & (w_bg[valid] <= 180)) * 100
        tbr = np.mean(w_bg[valid] < 70) * 100
        tar = np.mean(w_bg[valid] > 180) * 100
        mean_bg = np.mean(w_bg[valid])
        sd_bg = np.std(w_bg[valid])
        cv = sd_bg / mean_bg * 100

        # Count hypo events
        hypo_events = 0
        in_hypo = False
        for t in range(len(w_bg)):
            if w_bg[t] < 70 and not in_hypo:
                hypo_events += 1
                in_hypo = True
            elif w_bg[t] >= 80:
                in_hypo = False

        # Anomaly count
        w_resid_v = w_resid[np.isfinite(w_resid)] if len(w_resid) > 0 else np.array([])
        if len(w_resid_v) > 0:
            sigma = np.std(w_resid_v)
            anomalies = np.sum(np.abs(w_resid_v - np.mean(w_resid_v)) > 3 * sigma)
        else:
            anomalies = 0

        # Net flux bias (positive = settings too aggressive, negative = not enough insulin)
        mean_net = np.mean(w_net[valid]) if valid.sum() > 0 else 0
        flux_bias = 'balanced' if abs(mean_net) < 0.5 else ('surplus' if mean_net > 0 else 'deficit')

        # Grade
        if tir >= 70 and tbr < 4:
            grade = 'A'
        elif tir >= 60 and tbr < 6:
            grade = 'B'
        elif tir >= 50:
            grade = 'C'
        else:
            grade = 'D'

        result = {
            'patient': p['name'],
            'grade': grade,
            'tir': round(tir, 1),
            'tbr': round(tbr, 1),
            'tar': round(tar, 1),
            'mean_bg': round(float(mean_bg), 0),
            'cv': round(float(cv), 1),
            'hypo_events': hypo_events,
            'anomalies': int(anomalies),
            'flux_bias': flux_bias,
            'mean_net_flux': round(float(mean_net), 2),
        }
        results.append(result)
        if detail:
            print(f"    {p['name']}: Grade={grade} TIR={tir:.0f}% TBR={tbr:.1f}% "
                  f"CV={cv:.0f}% hypos={hypo_events} anomalies={anomalies} flux={flux_bias}")

    grades = [r['grade'] for r in results]
    grade_dist = {g: grades.count(g) for g in 'ABCD'}
    summary = f"Grades: A={grade_dist.get('A', 0)} B={grade_dist.get('B', 0)} C={grade_dist.get('C', 0)} D={grade_dist.get('D', 0)}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-656: Biweekly Report Card', 'summary': summary, 'details': results}


def run_exp_657(patients, detail=False):
    """EXP-657: Settings Recommendation — flux imbalance → CR/ISF adjustment."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd = compute_supply_demand(df, pk)

        n = len(bg)
        split = int(0.8 * n)

        # Analyze time-of-day flux patterns in test set
        test_bg = bg[split:]
        test_supply = sd['supply'][split:]
        test_demand = sd['demand'][split:]
        test_net = test_supply - test_demand + sd['hepatic'][split:]
        n_test = len(test_bg)

        # 4-hour bins (48 steps each)
        bin_size = 48
        bins = {}
        for t in range(n_test):
            tod_bin = (t % 288) // bin_size  # 0-5 (6 bins per day)
            bins.setdefault(tod_bin, {'bg': [], 'net': [], 'supply': [], 'demand': []})
            if np.isfinite(test_bg[t]):
                bins[tod_bin]['bg'].append(test_bg[t])
                bins[tod_bin]['net'].append(test_net[t])
                bins[tod_bin]['supply'].append(test_supply[t])
                bins[tod_bin]['demand'].append(test_demand[t])

        recommendations = []
        tod_labels = ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24']
        for b in range(6):
            if b not in bins or len(bins[b]['bg']) < 100:
                continue
            mean_bg = np.mean(bins[b]['bg'])
            mean_net = np.mean(bins[b]['net'])
            tar_pct = np.mean(np.array(bins[b]['bg']) > 180) * 100
            tbr_pct = np.mean(np.array(bins[b]['bg']) < 70) * 100

            rec = 'OK'
            if tar_pct > 30 and mean_net > 0.5:
                rec = 'increase_basal'
            elif tar_pct > 30 and mean_net < -0.5:
                rec = 'decrease_CR'  # meals causing highs despite insulin
            elif tbr_pct > 10:
                rec = 'decrease_basal'
            elif mean_bg > 180:
                rec = 'increase_ISF'
            elif mean_bg < 80:
                rec = 'decrease_ISF'

            recommendations.append({
                'period': tod_labels[b],
                'mean_bg': round(float(mean_bg), 0),
                'tar': round(float(tar_pct), 1),
                'tbr': round(float(tbr_pct), 1),
                'mean_net': round(float(mean_net), 2),
                'recommendation': rec,
            })

        n_actions = sum(1 for r in recommendations if r['recommendation'] != 'OK')
        result = {
            'patient': p['name'],
            'n_periods': len(recommendations),
            'n_actions_needed': n_actions,
            'recommendations': recommendations,
        }
        results.append(result)
        if detail:
            actions = [f"{r['period']}:{r['recommendation']}" for r in recommendations if r['recommendation'] != 'OK']
            print(f"    {p['name']}: {n_actions} actions — {', '.join(actions) if actions else 'all OK'}")

    mean_actions = np.mean([r['n_actions_needed'] for r in results])
    summary = f"Mean {mean_actions:.1f} settings adjustments per patient"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-657: Settings Recommendation', 'summary': summary, 'details': results}


def run_exp_658(patients, detail=False):
    """EXP-658: Live Data Validation — test on live-split unsegmented data."""
    live_dir = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "live-split"
    if not live_dir.exists():
        print("  RESULT: live-split directory not found, skipping")
        return {'name': 'EXP-658: Live Data Validation', 'summary': 'skipped — no data', 'details': []}

    results = []
    # Try to load live data using same patient loader
    try:
        live_patients = load_patients(live_dir, max_patients=5)
    except Exception as e:
        # Try manual loading
        import pandas as pd
        live_patients = []
        for csv_file in sorted(live_dir.glob("*.csv"))[:5]:
            try:
                df = pd.read_csv(csv_file)
                if 'sgv' not in df.columns and 'glucose' not in df.columns:
                    continue
                live_patients.append({'name': csv_file.stem, 'df': df, 'pk': None})
            except Exception:
                continue

    if not live_patients:
        # Try loading as patient directories
        for subdir in sorted(live_dir.iterdir())[:5]:
            if subdir.is_dir():
                try:
                    pts = load_patients(subdir.parent, max_patients=1)
                    if pts:
                        live_patients.extend(pts)
                except Exception:
                    continue

    if not live_patients:
        print("  RESULT: Could not load live data")
        return {'name': 'EXP-658: Live Data Validation', 'summary': 'no loadable data', 'details': []}

    for p in live_patients:
        df, pk = p['df'].copy(), p.get('pk')
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        if bg_col not in df.columns:
            continue
        bg = df[bg_col].values.astype(float)
        n_valid = np.sum(np.isfinite(bg))

        if pk is None:
            result = {
                'patient': p['name'],
                'n_steps': len(bg),
                'n_valid': int(n_valid),
                'has_pk': False,
                'note': 'No PK data — need profile for flux computation',
            }
        else:
            try:
                sd = compute_supply_demand(df, pk)
                result = {
                    'patient': p['name'],
                    'n_steps': len(bg),
                    'n_valid': int(n_valid),
                    'has_pk': True,
                    'mean_supply': round(float(np.nanmean(sd['supply'])), 2),
                    'mean_demand': round(float(np.nanmean(sd['demand'])), 2),
                }
            except Exception as e:
                result = {
                    'patient': p['name'],
                    'n_steps': len(bg),
                    'error': str(e)[:100],
                }

        results.append(result)
        if detail:
            print(f"    {result}")

    n_loaded = len(results)
    n_with_pk = sum(1 for r in results if r.get('has_pk', False))
    summary = f"Loaded {n_loaded} live datasets, {n_with_pk} with PK data"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-658: Live Data Validation', 'summary': summary, 'details': results}


def run_exp_659(patients, detail=False):
    """EXP-659: Cold Start — population bias for first 7 days."""
    results = []
    for p_idx, p in enumerate(patients):
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd, flux_pred, resid, bg_decay = _compute_flux(df, pk, bg)

        # Population bias: mean piecewise bias from OTHER patients
        pop_biases = {'low': [], 'mid': [], 'high': []}
        for q_idx, q in enumerate(patients):
            if q_idx == p_idx:
                continue
            qdf, qpk = q['df'].copy(), q.get('pk')
            if qpk is None:
                continue
            qbg_col = 'glucose' if 'glucose' in qdf.columns else 'sgv'
            qbg = qdf[qbg_col].values.astype(float)
            qsd, qflux, qresid, _ = _compute_flux(qdf, qpk, qbg)
            valid = np.isfinite(qresid)
            for i in range(len(qresid)):
                if not valid[i]:
                    continue
                if qbg[i] < 100:
                    pop_biases['low'].append(qresid[i])
                elif qbg[i] < 180:
                    pop_biases['mid'].append(qresid[i])
                else:
                    pop_biases['high'].append(qresid[i])

        pop_bias = {k: np.mean(v) for k, v in pop_biases.items() if v}

        # First 7 days (2016 steps)
        first_week = min(2016, len(bg) // 2)
        test_bg = bg[:first_week]
        test_resid = resid[:first_week - 1] if first_week - 1 <= len(resid) else resid[:len(resid)]

        # Apply population bias correction
        corrected = np.zeros(len(test_resid))
        for i in range(len(test_resid)):
            if test_bg[i] < 100:
                corrected[i] = test_resid[i] - pop_bias.get('low', 0)
            elif test_bg[i] < 180:
                corrected[i] = test_resid[i] - pop_bias.get('mid', 0)
            else:
                corrected[i] = test_resid[i] - pop_bias.get('high', 0)

        valid = np.isfinite(test_resid)
        if valid.sum() < 100:
            continue

        mae_raw = np.mean(np.abs(test_resid[valid]))
        mae_corrected = np.mean(np.abs(corrected[valid]))
        improvement = (mae_raw - mae_corrected) / mae_raw * 100

        result = {
            'patient': p['name'],
            'first_week_steps': first_week,
            'mae_raw': round(float(mae_raw), 2),
            'mae_pop_corrected': round(float(mae_corrected), 2),
            'improvement_pct': round(float(improvement), 1),
            'pop_bias_low': round(float(pop_bias.get('low', 0)), 3),
            'pop_bias_mid': round(float(pop_bias.get('mid', 0)), 3),
            'pop_bias_high': round(float(pop_bias.get('high', 0)), 3),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    n_improved = sum(1 for r in results if r['improvement_pct'] > 0)
    mean_improv = np.mean([r['improvement_pct'] for r in results])
    summary = f"Pop bias improves {n_improved}/{len(results)} patients in first week, mean Δ={mean_improv:.1f}%"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-659: Cold Start Performance', 'summary': summary, 'details': results}


def run_exp_660(patients, detail=False):
    """EXP-660: Minimal Data Requirement — R² vs training days."""
    results = []
    test_days = [1, 3, 7, 14, 30, 60, 90, 120]

    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        sd, flux_pred, resid, bg_decay = _compute_flux(df, pk, bg)

        n = len(resid)
        # Fixed test set: last 20%
        test_start = int(0.8 * n)
        X_test = _build_joint_features(resid[test_start:], bg[test_start:test_start + n - test_start],
                                        sd['demand'][test_start:test_start + n - test_start])
        y_test = resid[test_start:]
        mask_test = np.all(np.isfinite(X_test), axis=1) & np.isfinite(y_test)
        if mask_test.sum() < 100:
            continue

        ss_tot = np.sum((y_test[mask_test] - y_test[mask_test].mean()) ** 2)
        if ss_tot < 1e-10:
            continue

        day_r2s = {}
        for days in test_days:
            train_n = min(days * 288, test_start)
            if train_n < 100:
                continue

            X_train = _build_joint_features(resid[:train_n], bg[:train_n],
                                             sd['demand'][:train_n])
            y_train = resid[:train_n]
            mask = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
            if mask.sum() < 50:
                continue

            _, pred = _fit_ridge(X_train[mask], y_train[mask], X_test[mask_test])
            ss_res = np.sum((y_test[mask_test] - pred) ** 2)
            r2 = 1 - ss_res / ss_tot
            day_r2s[days] = round(float(r2), 4)

        if not day_r2s:
            continue

        # Find minimum days for 90% of max performance
        max_r2 = max(day_r2s.values())
        threshold_r2 = max_r2 * 0.9
        min_days = None
        for d in sorted(day_r2s.keys()):
            if day_r2s[d] >= threshold_r2:
                min_days = d
                break

        result = {
            'patient': p['name'],
            'day_r2s': day_r2s,
            'max_r2': max_r2,
            'min_days_90pct': min_days,
        }
        results.append(result)
        if detail:
            r2_str = ' '.join(f"{d}d={r:.3f}" for d, r in sorted(day_r2s.items()))
            print(f"    {p['name']}: {r2_str} | min={min_days}d for 90%")

    # Aggregate
    for d in test_days:
        vals = [r['day_r2s'].get(d) for r in results if d in r['day_r2s']]
        if vals:
            pass  # will compute below

    mean_min_days = np.mean([r['min_days_90pct'] for r in results if r['min_days_90pct'] is not None])
    r2_at_7 = np.mean([r['day_r2s'].get(7, 0) for r in results])
    r2_at_30 = np.mean([r['day_r2s'].get(30, 0) for r in results])
    r2_max = np.mean([r['max_r2'] for r in results])
    summary = f"Min {mean_min_days:.0f} days for 90% perf. R²: 7d={r2_at_7:.3f}, 30d={r2_at_30:.3f}, max={r2_max:.3f}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-660: Minimal Data Requirement', 'summary': summary, 'details': results}


EXPERIMENTS = [
    ("EXP-651", "EXP-651: Ensemble hypo alert — combine flux-trajectory + adaptive threshold.", run_exp_651),
    ("EXP-652", "EXP-652: Hypo lead time — minutes of warning before BG<70.", run_exp_652),
    ("EXP-653", "EXP-653: Hypo severity prediction — flux integral vs nadir depth.", run_exp_653),
    ("EXP-654", "EXP-654: Anomaly classification — 3σ events by meal/BG/time context.", run_exp_654),
    ("EXP-655", "EXP-655: Residual autocorrelation — structure at longer lags.", run_exp_655),
    ("EXP-656", "EXP-656: Biweekly report card with actionable clinical metrics.", run_exp_656),
    ("EXP-657", "EXP-657: Settings recommendation from flux imbalance patterns.", run_exp_657),
    ("EXP-658", "EXP-658: Live data validation on unsegmented streaming data.", run_exp_658),
    ("EXP-659", "EXP-659: Cold start — population bias for Day 1-7 predictions.", run_exp_659),
    ("EXP-660", "EXP-660: Minimal data requirement — R² vs training days.", run_exp_660),
]


def main():
    parser = argparse.ArgumentParser(description="EXP-651-660")
    parser.add_argument("--max-patients", type=int, default=11)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--only", type=str, help="Run only specific experiment")
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    all_results = []
    for eid, desc, func in EXPERIMENTS:
        if args.only and args.only != eid:
            continue
        print(f"{'=' * 60}")
        print(f"Running {eid}: {desc}")
        print(f"{'=' * 60}\n")
        result = func(patients, detail=args.detail)
        all_results.append(result)

        if args.save:
            safe_name = result['name'].lower().replace(' ', '_').replace('/', '_').replace(':', '')[:30]
            fname = f"{eid.lower()}_{safe_name}.json"
            out_dir = Path(__file__).parent / "results"
            out_dir.mkdir(exist_ok=True)

            def convert(obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                if isinstance(obj, (np.floating,)):
                    return float(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                if isinstance(obj, (np.bool_,)):
                    return bool(obj)
                return obj

            with open(out_dir / fname, 'w') as f:
                json.dump(result, f, indent=2, default=convert)
            print(f"  Saved: {fname}")
        print()


if __name__ == "__main__":
    main()
