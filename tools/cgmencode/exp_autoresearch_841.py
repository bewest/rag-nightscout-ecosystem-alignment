#!/usr/bin/env python3
"""EXP-841–850: Residual Characterization & Information Frontier

With nonlinear models confirming the model-class ceiling (R²=0.536 vs linear
0.534), this wave shifts from "better models" to "better understanding."
We characterize WHERE and WHY the model fails, quantify irreducible error,
and identify the most promising information channels for future improvement.

EXP-841: Error Decomposition by Context (meal vs fasting vs overnight vs dawn)
EXP-842: Patient h Deep Dive (R²=0.153 outlier investigation)
EXP-843: Bias-Variance Decomposition (systematic vs random error)
EXP-844: Prediction Interval Coverage (conformal prediction)
EXP-845: Residual Clustering (latent error regimes)
EXP-846: Error Attribution by BG Dynamics (rising/falling/stable x low/normal/high)
EXP-847: Sensor Age Degradation Effect
EXP-848: Time-Since-Last-Bolus as Feature
EXP-849: Residual Autocorrelation Structure (multi-lag analysis)
EXP-850: Information-Theoretic Ceiling Estimation
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from exp_metabolic_441 import compute_supply_demand
from exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

EXPERIMENTS = {}

def _get_bg(df):
    col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[col]

def _compute_flux(p):
    df = p['df']
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(_get_bg(df)))
    fd = compute_supply_demand(df, pk)
    bg = np.asarray(_get_bg(df), dtype=float)
    n = len(fd['supply'])
    bg = bg[:n]
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.full(n, 0.5))
    flux_pred = supply - demand + hepatic + (120.0 - bg) * 0.005
    resid = bg[1:] - (bg[:-1] + flux_pred[:-1])
    return {'bg': bg, 'supply': supply, 'demand': demand,
            'hepatic': hepatic, 'flux_pred': flux_pred, 'resid': resid, 'n': n}

def _get_hours(df, n):
    import pandas as pd
    idx = df.index[:n]
    if isinstance(idx, pd.DatetimeIndex):
        return np.asarray(idx.hour + idx.minute / 60.0, dtype=float)
    return None

def _r2(pred, actual):
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    if ss_tot < 1e-10:
        return float('nan')
    return 1.0 - ss_res / ss_tot

def _mae(pred, actual):
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    return float(np.mean(np.abs(pred[mask] - actual[mask])))

def _build_features_base(fd, hours, n_pred, h_steps):
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    features = np.zeros((n_pred, 8))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
        features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
        features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
        features[i, 4] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 7] = 1.0
    return features

def _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start=24):
    """Build the 16-feature enhanced set."""
    base = _build_features_base(fd, hours, n_pred, h_steps)
    usable = n_pred - start
    base = base[start:start + usable]

    extra = np.zeros((usable, 8))
    for i in range(usable):
        orig = i + start
        if orig >= 1:
            extra[i, 0] = bg[orig] - bg[orig - 1]
        if orig >= 2:
            extra[i, 1] = bg[orig] - 2 * bg[orig - 1] + bg[orig - 2]
        if orig >= 6:
            extra[i, 2] = bg[orig - 6]
        if orig >= 12:
            extra[i, 3] = bg[orig - 12]
        w = bg[max(0, orig - 24):orig + 1]
        vw = w[np.isfinite(w)]
        if len(vw) >= 3:
            extra[i, 4] = np.mean(vw)
            extra[i, 5] = np.std(vw)
            x = np.arange(len(vw))
            extra[i, 6] = np.polyfit(x, vw, 1)[0]
        extra[i, 7] = bg[orig] ** 2 / 1000.0

    return np.hstack([base, extra]), usable

def _ridge_predict(X_train, y_train, X_val, lam=1.0):
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    try:
        w = np.linalg.solve(XtX, X_train.T @ y_train)
        return X_val @ w, w
    except np.linalg.LinAlgError:
        return np.full(X_val.shape[0], np.nan), None

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ── EXP-841: Error Decomposition by Context ──────────────────────────────────

@register('EXP-841', 'Error Decomposition by Context')
def exp_841(patients, detail=False):
    """Decompose prediction error into context-specific components.

    Classify each prediction point into one of:
    - Overnight (0:00-5:00)
    - Dawn (5:00-8:00)
    - Morning (8:00-12:00)
    - Afternoon (12:00-17:00)
    - Evening (17:00-21:00)
    - Night (21:00-0:00)

    Also cross with BG dynamics:
    - Rising: velocity > +2 mg/dL per 5min
    - Falling: velocity < -2 mg/dL per 5min
    - Stable: |velocity| <= 2

    Report MAE, R², and proportion for each context.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    contexts = {
        'overnight': (0, 5),
        'dawn': (5, 8),
        'morning': (8, 12),
        'afternoon': (12, 17),
        'evening': (17, 21),
        'night': (21, 24),
    }

    # Collect all residuals with context labels
    all_errors = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200 or hours is None:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        val_hours = hours[:n_pred][start:][split:]
        val_bg = bg[start:start + n_pred][split:]

        for i in range(len(y_val)):
            if not valid_val[i] or not np.isfinite(pred[i]):
                continue
            h = val_hours[i] if i < len(val_hours) else 12.0
            err = pred[i] - y_val[i]

            # Time context
            ctx = 'unknown'
            for name, (lo, hi) in contexts.items():
                if lo <= h < hi:
                    ctx = name
                    break

            # BG dynamics
            vel = features[split + i, 8] if features.shape[1] > 8 else 0
            if vel > 2:
                dyn = 'rising'
            elif vel < -2:
                dyn = 'falling'
            else:
                dyn = 'stable'

            # BG level
            curr = val_bg[i] if i < len(val_bg) else 120
            if curr < 70:
                level = 'low'
            elif curr < 180:
                level = 'target'
            else:
                level = 'high'

            all_errors.append({
                'error': err,
                'abs_error': abs(err),
                'actual': y_val[i],
                'predicted': pred[i],
                'context': ctx,
                'dynamics': dyn,
                'level': level,
                'patient': p['name'],
            })

    # Aggregate by context
    by_context = {}
    for ctx_name in list(contexts.keys()) + ['unknown']:
        ctx_errs = [e for e in all_errors if e['context'] == ctx_name]
        if len(ctx_errs) > 10:
            mae = np.mean([e['abs_error'] for e in ctx_errs])
            bias = np.mean([e['error'] for e in ctx_errs])
            actuals = np.array([e['actual'] for e in ctx_errs])
            preds = np.array([e['predicted'] for e in ctx_errs])
            r2 = _r2(preds, actuals)
            by_context[ctx_name] = {
                'n': len(ctx_errs),
                'mae': round(mae, 1),
                'bias': round(bias, 1),
                'r2': round(r2, 3),
                'pct': round(100 * len(ctx_errs) / len(all_errors), 1),
            }

    # Aggregate by dynamics
    by_dynamics = {}
    for dyn in ['rising', 'falling', 'stable']:
        dyn_errs = [e for e in all_errors if e['dynamics'] == dyn]
        if len(dyn_errs) > 10:
            mae = np.mean([e['abs_error'] for e in dyn_errs])
            bias = np.mean([e['error'] for e in dyn_errs])
            actuals = np.array([e['actual'] for e in dyn_errs])
            preds = np.array([e['predicted'] for e in dyn_errs])
            r2 = _r2(preds, actuals)
            by_dynamics[dyn] = {
                'n': len(dyn_errs),
                'mae': round(mae, 1),
                'bias': round(bias, 1),
                'r2': round(r2, 3),
                'pct': round(100 * len(dyn_errs) / len(all_errors), 1),
            }

    # Aggregate by level
    by_level = {}
    for lev in ['low', 'target', 'high']:
        lev_errs = [e for e in all_errors if e['level'] == lev]
        if len(lev_errs) > 10:
            mae = np.mean([e['abs_error'] for e in lev_errs])
            bias = np.mean([e['error'] for e in lev_errs])
            actuals = np.array([e['actual'] for e in lev_errs])
            preds = np.array([e['predicted'] for e in lev_errs])
            r2 = _r2(preds, actuals)
            by_level[lev] = {
                'n': len(lev_errs),
                'mae': round(mae, 1),
                'bias': round(bias, 1),
                'r2': round(r2, 3),
                'pct': round(100 * len(lev_errs) / len(all_errors), 1),
            }

    # Cross-tabulation: context x dynamics (top combinations)
    cross = {}
    for ctx_name in contexts:
        for dyn in ['rising', 'falling', 'stable']:
            key = f"{ctx_name}_{dyn}"
            sub = [e for e in all_errors
                   if e['context'] == ctx_name and e['dynamics'] == dyn]
            if len(sub) > 30:
                cross[key] = {
                    'n': len(sub),
                    'mae': round(np.mean([e['abs_error'] for e in sub]), 1),
                    'bias': round(np.mean([e['error'] for e in sub]), 1),
                }

    # Worst 5 cross combinations
    worst_5 = sorted(cross.items(), key=lambda x: x[1]['mae'], reverse=True)[:5]

    results = {
        'total_points': len(all_errors),
        'overall_mae': round(np.mean([e['abs_error'] for e in all_errors]), 1),
        'by_context': by_context,
        'by_dynamics': by_dynamics,
        'by_level': by_level,
        'worst_combinations': {k: v for k, v in worst_5},
    }

    return {
        'status': 'pass',
        'detail': f"total={len(all_errors)}, worst_ctx={worst_5[0][0] if worst_5 else '?'} MAE={worst_5[0][1]['mae'] if worst_5 else '?'}",
        'results': results,
    }


# ── EXP-842: Patient h Deep Dive ─────────────────────────────────────────────

@register('EXP-842', 'Patient h Deep Dive')
def exp_842(patients, detail=False):
    """Investigate why patient h has R²=0.153 (vs mean 0.509).

    Compare patient h's data characteristics against others:
    - BG variability (CV, range, TIR)
    - Treatment density (boluses/day, carbs/day)
    - Data quality (missing %, gap lengths)
    - Flux dynamics (supply/demand magnitudes)
    - Feature distributions
    """
    h_steps = 12
    lam = 10.0
    start = 24

    patient_stats = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        features = features[start:start + usable]

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, w = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
        r2 = _r2(pred[valid_val], y_val[valid_val])
        mae = _mae(pred[valid_val], y_val[valid_val])

        # BG statistics
        bg_valid = bg[np.isfinite(bg)]
        bg_mean = float(np.mean(bg_valid))
        bg_std = float(np.std(bg_valid))
        bg_cv = bg_std / bg_mean if bg_mean > 0 else 0
        bg_range = float(np.ptp(bg_valid))
        tir = float(np.mean((bg_valid >= 70) & (bg_valid <= 180)))

        # Data quality
        n_total = len(bg)
        n_valid = int(np.sum(np.isfinite(bg)))
        pct_valid = n_valid / n_total if n_total > 0 else 0
        days = n_total * 5.0 / (60 * 24)

        # Gap analysis
        finite_mask = np.isfinite(bg)
        diffs = np.diff(finite_mask.astype(int))
        gap_starts = np.where(diffs == -1)[0]
        gap_ends = np.where(diffs == 1)[0]
        if len(gap_starts) > 0 and len(gap_ends) > 0:
            if gap_ends[0] < gap_starts[0]:
                gap_ends = gap_ends[1:]
            n_gaps = min(len(gap_starts), len(gap_ends))
            gap_lens = gap_ends[:n_gaps] - gap_starts[:n_gaps]
            max_gap = int(np.max(gap_lens)) if len(gap_lens) > 0 else 0
            mean_gap = float(np.mean(gap_lens)) if len(gap_lens) > 0 else 0
        else:
            max_gap = 0
            mean_gap = 0

        # Flux statistics
        supply_mean = float(np.nanmean(fd['supply']))
        demand_mean = float(np.nanmean(fd['demand']))
        supply_std = float(np.nanstd(fd['supply']))
        demand_std = float(np.nanstd(fd['demand']))
        resid_std = float(np.nanstd(fd['resid']))

        # BG velocity statistics
        velocity = np.diff(bg_valid) if len(bg_valid) > 1 else np.array([0])
        vel_std = float(np.std(velocity))
        vel_mean = float(np.mean(np.abs(velocity)))

        # Feature weight magnitudes
        feat_names = ['bg', 'supply', 'demand', 'hepatic', 'resid', 'sin_h', 'cos_h', 'bias']
        weights = {}
        if w is not None:
            for j, fn in enumerate(feat_names):
                if j < len(w):
                    weights[fn] = round(float(w[j]), 4)

        patient_stats.append({
            'patient': p['name'],
            'r2': round(float(r2), 3) if np.isfinite(r2) else None,
            'mae': round(float(mae), 1) if np.isfinite(mae) else None,
            'bg_mean': round(bg_mean, 1),
            'bg_std': round(bg_std, 1),
            'bg_cv': round(bg_cv, 3),
            'bg_range': round(bg_range, 1),
            'tir': round(tir, 3),
            'days': round(days, 1),
            'pct_valid': round(pct_valid, 3),
            'max_gap_steps': max_gap,
            'mean_gap_steps': round(mean_gap, 1),
            'supply_mean': round(supply_mean, 4),
            'supply_std': round(supply_std, 4),
            'demand_mean': round(demand_mean, 4),
            'demand_std': round(demand_std, 4),
            'resid_std': round(resid_std, 2),
            'vel_std': round(vel_std, 2),
            'vel_mean_abs': round(vel_mean, 2),
            'n_steps': n_total,
            'weights': weights,
        })

    # Sort by R² for comparison
    patient_stats.sort(key=lambda x: x.get('r2', 0) or 0)

    # Find patient h
    h_data = [s for s in patient_stats if s['patient'] == 'h']
    others = [s for s in patient_stats if s['patient'] != 'h']

    # Compute z-scores for patient h against others
    if h_data and others:
        h_stat = h_data[0]
        z_scores = {}
        for key in ['bg_cv', 'bg_std', 'resid_std', 'vel_std', 'supply_std', 'demand_std',
                     'pct_valid', 'tir']:
            vals = [s[key] for s in others if s[key] is not None]
            if len(vals) > 2:
                mean_v = np.mean(vals)
                std_v = np.std(vals)
                if std_v > 1e-10:
                    z = (h_stat[key] - mean_v) / std_v
                    z_scores[key] = round(float(z), 2)
    else:
        z_scores = {}

    results = {
        'patient_stats': patient_stats,
        'patient_h_z_scores': z_scores,
    }

    return {
        'status': 'pass',
        'detail': f"patient_h R²={h_data[0]['r2'] if h_data else '?'}, outlier_dims={sum(1 for v in z_scores.values() if abs(v) > 2)}",
        'results': results,
    }


# ── EXP-843: Bias-Variance Decomposition ─────────────────────────────────────

@register('EXP-843', 'Bias-Variance Decomposition')
def exp_843(patients, detail=False):
    """Decompose error into bias² + variance + noise components.

    Use bootstrap resampling of training data to estimate:
    - Bias²: (E[prediction] - actual)² — systematic error
    - Variance: E[(prediction - E[prediction])²] — model instability
    - Noise: Irreducible error from data
    """
    h_steps = 12
    lam = 10.0
    start = 24
    n_bootstrap = 20

    patient_results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        valid_tr_base = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)

        # Bootstrap predictions
        rng = np.random.RandomState(42)
        predictions = np.zeros((n_bootstrap, len(y_val)))

        for b in range(n_bootstrap):
            # Sample with replacement from training data
            idx_valid = np.where(valid_tr_base)[0]
            boot_idx = rng.choice(idx_valid, size=len(idx_valid), replace=True)
            pred_b, _ = _ridge_predict(X_tr[boot_idx], y_tr[boot_idx], X_val, lam=lam * 3)
            predictions[b] = pred_b

        # Compute bias and variance per point
        valid = valid_val & np.all(np.isfinite(predictions), axis=0)
        if valid.sum() < 10:
            continue

        mean_pred = np.mean(predictions[:, valid], axis=0)
        bias_sq = (mean_pred - y_val[valid]) ** 2
        variance = np.mean((predictions[:, valid] - mean_pred[np.newaxis, :]) ** 2, axis=0)

        total_error = np.mean((predictions[:, valid] - y_val[valid][np.newaxis, :]) ** 2, axis=0)

        # Noise = total - bias² - variance (should be ~0 for deterministic model)
        noise = total_error - bias_sq - variance

        patient_results.append({
            'patient': p['name'],
            'mean_bias_sq': round(float(np.mean(bias_sq)), 1),
            'mean_variance': round(float(np.mean(variance)), 1),
            'mean_noise': round(float(np.mean(noise)), 1),
            'mean_total': round(float(np.mean(total_error)), 1),
            'bias_pct': round(100 * float(np.mean(bias_sq) / (np.mean(total_error) + 1e-10)), 1),
            'variance_pct': round(100 * float(np.mean(variance) / (np.mean(total_error) + 1e-10)), 1),
            'n_valid': int(valid.sum()),
        })

    if not patient_results:
        return {'status': 'fail', 'detail': 'No valid patient data'}

    avg_bias_pct = np.mean([r['bias_pct'] for r in patient_results])
    avg_var_pct = np.mean([r['variance_pct'] for r in patient_results])

    results = {
        'per_patient': patient_results,
        'summary': {
            'avg_bias_pct': round(float(avg_bias_pct), 1),
            'avg_variance_pct': round(float(avg_var_pct), 1),
            'interpretation': 'bias_dominated' if avg_bias_pct > 70 else
                            'variance_dominated' if avg_var_pct > 30 else 'mixed',
        }
    }

    return {
        'status': 'pass',
        'detail': f"bias={avg_bias_pct:.1f}%, variance={avg_var_pct:.1f}%",
        'results': results,
    }


# ── EXP-844: Prediction Interval Coverage ────────────────────────────────────

@register('EXP-844', 'Prediction Interval Coverage')
def exp_844(patients, detail=False):
    """Conformal prediction intervals for uncertainty quantification.

    Use split conformal prediction:
    1. Split training into proper-train and calibration
    2. Fit model on proper-train
    3. Compute nonconformity scores on calibration set
    4. Use calibration quantiles to form prediction intervals on test
    5. Check coverage at 50%, 80%, 90%, 95% levels
    """
    h_steps = 12
    lam = 10.0
    start = 24
    target_coverages = [0.50, 0.80, 0.90, 0.95]

    patient_results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        # Three-way split: train (60%) / calibration (20%) / test (20%)
        split1 = int(0.6 * usable)
        split2 = int(0.8 * usable)

        X_tr = features[:split1]
        y_tr = actual[:split1]
        X_cal = features[split1:split2]
        y_cal = actual[split1:split2]
        X_test = features[split2:]
        y_test = actual[split2:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)

        # Fit model on training
        pred_cal, w = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_cal, lam=lam * 3)
        if w is None:
            continue
        pred_test = X_test @ w

        # Nonconformity scores on calibration
        valid_cal = np.isfinite(y_cal) & np.isfinite(pred_cal)
        nc_scores = np.abs(y_cal[valid_cal] - pred_cal[valid_cal])

        valid_test = np.isfinite(y_test) & np.isfinite(pred_test)

        coverages = {}
        widths = {}
        for target in target_coverages:
            q = np.quantile(nc_scores, target)
            covered = np.abs(y_test[valid_test] - pred_test[valid_test]) <= q
            actual_coverage = float(np.mean(covered))
            interval_width = 2 * q
            coverages[str(target)] = round(actual_coverage, 3)
            widths[str(target)] = round(float(interval_width), 1)

        patient_results.append({
            'patient': p['name'],
            'coverages': coverages,
            'widths': widths,
            'n_cal': int(valid_cal.sum()),
            'n_test': int(valid_test.sum()),
        })

    if not patient_results:
        return {'status': 'fail', 'detail': 'No valid patient data'}

    # Average coverages across patients
    avg_coverages = {}
    avg_widths = {}
    for target in target_coverages:
        key = str(target)
        avg_coverages[key] = round(float(np.mean(
            [r['coverages'][key] for r in patient_results])), 3)
        avg_widths[key] = round(float(np.mean(
            [r['widths'][key] for r in patient_results])), 1)

    results = {
        'per_patient': patient_results,
        'avg_coverages': avg_coverages,
        'avg_widths': avg_widths,
        'calibration_quality': 'good' if all(
            abs(avg_coverages[str(t)] - t) < 0.05 for t in target_coverages
        ) else 'poor',
    }

    return {
        'status': 'pass',
        'detail': f"90% coverage={avg_coverages['0.9']}, width={avg_widths['0.9']}mg/dL",
        'results': results,
    }


# ── EXP-845: Residual Clustering ─────────────────────────────────────────────

@register('EXP-845', 'Residual Clustering')
def exp_845(patients, detail=False):
    """Cluster prediction residuals to identify latent error regimes.

    Use K-means on (residual, |residual|, BG_level, velocity, hour)
    to find natural groupings of error patterns.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    all_features = []
    all_errors = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200 or hours is None:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        val_hours = hours[:n_pred][start:][split:]
        for i in range(len(y_val)):
            if not valid_val[i] or not np.isfinite(pred[i]):
                continue
            err = pred[i] - y_val[i]
            bg_level = X_val[i, 0]
            velocity = X_val[i, 8] if X_val.shape[1] > 8 else 0
            supply = X_val[i, 1]
            demand = X_val[i, 2]
            h = val_hours[i] if i < len(val_hours) else 12.0

            all_features.append([
                bg_level / 100.0,
                velocity / 10.0,
                h / 24.0,
                supply * 10,
                demand * 10,
            ])
            all_errors.append(err)

    if len(all_features) < 100:
        return {'status': 'fail', 'detail': 'Not enough data'}

    X = np.array(all_features)
    errors = np.array(all_errors)

    # Simple K-means clustering
    best_k = 3
    cluster_results = {}

    for k in [3, 5, 7]:
        rng = np.random.RandomState(42)
        # K-means++ initialization
        centers = [X[rng.randint(len(X))]]
        for _ in range(k - 1):
            dists = np.min([np.sum((X - c) ** 2, axis=1) for c in centers], axis=0)
            probs = dists / dists.sum()
            centers.append(X[rng.choice(len(X), p=probs)])
        centers = np.array(centers)

        # Iterate
        for _ in range(50):
            dists = np.array([np.sum((X - c) ** 2, axis=1) for c in centers])
            labels = np.argmin(dists, axis=0)
            new_centers = np.array([X[labels == j].mean(axis=0) if (labels == j).any()
                                    else centers[j] for j in range(k)])
            if np.allclose(centers, new_centers, atol=1e-6):
                break
            centers = new_centers

        # Characterize each cluster
        clusters = []
        for j in range(k):
            mask = labels == j
            if mask.sum() < 10:
                continue
            c_errors = errors[mask]
            c_features = X[mask]
            clusters.append({
                'cluster': j,
                'n': int(mask.sum()),
                'pct': round(100 * mask.sum() / len(errors), 1),
                'mae': round(float(np.mean(np.abs(c_errors))), 1),
                'bias': round(float(np.mean(c_errors)), 1),
                'std': round(float(np.std(c_errors)), 1),
                'avg_bg': round(float(np.mean(c_features[:, 0]) * 100), 1),
                'avg_vel': round(float(np.mean(c_features[:, 1]) * 10), 2),
                'avg_hour': round(float(np.mean(c_features[:, 2]) * 24), 1),
            })

        # Within-cluster variance / total variance
        wcss = sum(np.sum((X[labels == j] - centers[j]) ** 2) for j in range(k))
        tcss = np.sum((X - X.mean(axis=0)) ** 2)
        explained = 1 - wcss / tcss if tcss > 0 else 0

        cluster_results[f'k={k}'] = {
            'clusters': clusters,
            'explained_variance': round(float(explained), 3),
        }

    # Find worst cluster
    all_clusters = []
    for kr in cluster_results.values():
        all_clusters.extend(kr['clusters'])
    if all_clusters:
        worst = max(all_clusters, key=lambda c: c['mae'])
        best = min(all_clusters, key=lambda c: c['mae'])
    else:
        worst = best = {'mae': 0}

    results = {
        'total_points': len(errors),
        'overall_mae': round(float(np.mean(np.abs(errors))), 1),
        'cluster_results': cluster_results,
        'worst_cluster_mae': worst['mae'],
        'best_cluster_mae': best['mae'],
        'error_range_ratio': round(worst['mae'] / best['mae'], 2) if best['mae'] > 0 else 0,
    }

    return {
        'status': 'pass',
        'detail': f"worst_cluster MAE={worst['mae']}, best MAE={best['mae']}, ratio={results['error_range_ratio']}",
        'results': results,
    }


# ── EXP-846: Error Attribution by BG Dynamics ────────────────────────────────

@register('EXP-846', 'Error Attribution by BG Dynamics')
def exp_846(patients, detail=False):
    """Quantify how much prediction error comes from each BG dynamic regime.

    Cross-tabulate (Rising/Falling/Stable) x (Low/Target/High) x (WithTreatment/NoTreatment)
    to determine error contribution weighted by frequency.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    # Treatment detection threshold: supply > threshold means recent bolus/carbs
    supply_thresh = 0.01

    regime_errors = {}

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        for i in range(len(y_val)):
            if not valid_val[i] or not np.isfinite(pred[i]):
                continue

            err = pred[i] - y_val[i]
            bg_now = X_val[i, 0]
            velocity = X_val[i, 8] if X_val.shape[1] > 8 else 0
            supply = X_val[i, 1]

            # Classify dynamics
            if velocity > 2:
                dyn = 'rising'
            elif velocity < -2:
                dyn = 'falling'
            else:
                dyn = 'stable'

            # Classify level
            if bg_now < 70:
                level = 'low'
            elif bg_now < 180:
                level = 'target'
            else:
                level = 'high'

            # Treatment active
            treatment = 'treated' if supply > supply_thresh else 'untreated'

            key = f"{dyn}_{level}_{treatment}"
            if key not in regime_errors:
                regime_errors[key] = {'errors': [], 'sq_errors': []}
            regime_errors[key]['errors'].append(err)
            regime_errors[key]['sq_errors'].append(err ** 2)

    # Compute error budget
    total_sq_error = sum(sum(v['sq_errors']) for v in regime_errors.values())
    total_n = sum(len(v['errors']) for v in regime_errors.values())

    regimes = {}
    for key, data in sorted(regime_errors.items()):
        n_pts = len(data['errors'])
        if n_pts < 10:
            continue
        mae = float(np.mean(np.abs(data['errors'])))
        mse = float(np.mean(data['sq_errors']))
        bias = float(np.mean(data['errors']))
        pct_error = 100 * sum(data['sq_errors']) / total_sq_error if total_sq_error > 0 else 0
        pct_freq = 100 * n_pts / total_n if total_n > 0 else 0

        regimes[key] = {
            'n': n_pts,
            'pct_frequency': round(pct_freq, 1),
            'mae': round(mae, 1),
            'mse': round(mse, 1),
            'bias': round(bias, 1),
            'pct_total_error': round(pct_error, 1),
            'error_density': round(pct_error / pct_freq, 2) if pct_freq > 0 else 0,
        }

    # Top 3 error contributors
    top_error = sorted(regimes.items(), key=lambda x: x[1]['pct_total_error'], reverse=True)[:5]

    results = {
        'total_n': total_n,
        'total_mse': round(total_sq_error / total_n, 1) if total_n > 0 else 0,
        'regimes': regimes,
        'top_error_contributors': {k: v for k, v in top_error},
    }

    return {
        'status': 'pass',
        'detail': f"top_error={top_error[0][0]} ({top_error[0][1]['pct_total_error']}% of error)" if top_error else 'no data',
        'results': results,
    }


# ── EXP-847: Sensor Age Degradation Effect ───────────────────────────────────

@register('EXP-847', 'Sensor Age Degradation Effect')
def exp_847(patients, detail=False):
    """Test whether prediction error increases with sensor age.

    Proxy for sensor age: count consecutive valid readings before a gap of >=6h.
    Each "sensor session" resets the age counter at gaps.
    Bin by sensor day (0-1, 1-2, ..., 9-10) and check error trend.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    age_errors = {}

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        # Compute sensor age: consecutive valid readings since last gap (>=72 steps = 6h)
        sensor_age = np.zeros(n)
        gap_threshold = 72  # 6 hours
        consecutive = 0
        for i in range(n):
            if np.isfinite(bg[i]):
                consecutive += 1
                sensor_age[i] = consecutive
            else:
                if consecutive > 0 and consecutive < gap_threshold:
                    # Small gap, don't reset
                    consecutive += 1
                    sensor_age[i] = consecutive
                else:
                    consecutive = 0
                    sensor_age[i] = 0

        # Map sensor age to validation set
        val_age = sensor_age[start + split: start + split + len(y_val)]

        for i in range(len(y_val)):
            if not valid_val[i] or not np.isfinite(pred[i]):
                continue
            if i >= len(val_age):
                continue

            age_days = val_age[i] * 5.0 / (60 * 24)  # Convert steps to days
            day_bin = min(int(age_days), 10)

            if day_bin not in age_errors:
                age_errors[day_bin] = []
            age_errors[day_bin].append(abs(pred[i] - y_val[i]))

    # Compute MAE per sensor day
    by_day = {}
    for day, errs in sorted(age_errors.items()):
        if len(errs) > 30:
            by_day[str(day)] = {
                'n': len(errs),
                'mae': round(float(np.mean(errs)), 1),
                'std': round(float(np.std(errs)), 1),
            }

    # Linear trend
    days = sorted([int(d) for d in by_day.keys()])
    maes = [by_day[str(d)]['mae'] for d in days]
    if len(days) > 2:
        slope, intercept = np.polyfit(days, maes, 1)
        trend = 'increasing' if slope > 0.5 else 'decreasing' if slope < -0.5 else 'flat'
    else:
        slope, intercept = 0, 0
        trend = 'insufficient_data'

    results = {
        'by_sensor_day': by_day,
        'trend_slope': round(float(slope), 2),
        'trend_intercept': round(float(intercept), 1),
        'trend_direction': trend,
    }

    return {
        'status': 'pass',
        'detail': f"trend={trend}, slope={slope:.2f} mg/dL/day",
        'results': results,
    }


# ── EXP-848: Time-Since-Last-Bolus as Feature ────────────────────────────────

@register('EXP-848', 'Time-Since-Last-Bolus as Feature')
def exp_848(patients, detail=False):
    """Test whether time-since-last-bolus improves prediction.

    Proxy: Find steps where demand spikes (bolus delivery), compute
    time since last spike for each prediction point.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, bolus_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        # Detect bolus events: demand > 90th percentile
        demand = fd['demand']
        demand_valid = demand[np.isfinite(demand) & (demand > 0)]
        if len(demand_valid) < 100:
            bolus_thresh = 0.1
        else:
            bolus_thresh = np.percentile(demand_valid, 90)

        # Compute time-since-last-bolus for each step
        tslb = np.zeros(n)
        last_bolus = -1000
        for i in range(n):
            if demand[i] > bolus_thresh:
                last_bolus = i
            tslb[i] = (i - last_bolus) * 5.0 / 60.0  # hours

        # Extract for usable range
        tslb_usable = tslb[start:start + usable]

        # Also compute time-since-last-carb (supply spike)
        supply = fd['supply']
        supply_valid = supply[np.isfinite(supply) & (supply > 0)]
        if len(supply_valid) < 100:
            carb_thresh = 0.01
        else:
            carb_thresh = np.percentile(supply_valid, 90)

        tslc = np.zeros(n)
        last_carb = -1000
        for i in range(n):
            if supply[i] > carb_thresh:
                last_carb = i
            tslc[i] = (i - last_carb) * 5.0 / 60.0

        tslc_usable = tslc[start:start + usable]

        # Add bolus/carb timing features
        extra_feats = np.column_stack([
            tslb_usable,
            np.minimum(tslb_usable, 6),  # Capped at 6h
            1.0 / (tslb_usable + 0.5),   # Inverse (decaying relevance)
            tslc_usable,
            np.minimum(tslc_usable, 6),
            1.0 / (tslc_usable + 0.5),
        ])

        combined = np.hstack([features, extra_feats])

        split = int(0.8 * usable)
        y_tr, y_val = actual[:split], actual[split:]

        # Base model
        X_tr_b, X_val_b = features[:split], features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])

        # Enhanced model with bolus timing
        X_tr_e, X_val_e = combined[:split], combined[split:]
        valid_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
        valid_val_e = np.isfinite(y_val) & np.all(np.isfinite(X_val_e), axis=1)
        pred_enh, _ = _ridge_predict(X_tr_e[valid_tr_e], y_tr[valid_tr_e],
                                      X_val_e, lam=lam * 4)
        r2_enh = _r2(pred_enh[valid_val_e], y_val[valid_val_e])

        if np.isfinite(r2_base) and np.isfinite(r2_enh):
            base_r2s.append(r2_base)
            bolus_r2s.append(r2_enh)

    if not base_r2s:
        return {'status': 'fail', 'detail': 'No valid data'}

    results = {
        'base_r2': round(float(np.mean(base_r2s)), 3),
        'with_bolus_timing': round(float(np.mean(bolus_r2s)), 3),
        'improvement': round(float(np.mean(bolus_r2s) - np.mean(base_r2s)), 3),
        'per_patient': [{'base': round(b, 3), 'enhanced': round(e, 3)}
                        for b, e in zip(base_r2s, bolus_r2s)],
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base_r2']}, +bolus_timing={results['with_bolus_timing']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-849: Residual Autocorrelation Structure ──────────────────────────────

@register('EXP-849', 'Residual Autocorrelation Structure')
def exp_849(patients, detail=False):
    """Multi-lag autocorrelation analysis of prediction residuals.

    Compute AC at lags 1-48 (5min-4h) to understand temporal structure
    of errors. High AC at certain lags suggests exploitable patterns;
    rapid decay to zero suggests irreducible noise.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    max_lag = 48

    patient_acs = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        # Compute residuals
        residuals = np.full(len(y_val), np.nan)
        for i in range(len(y_val)):
            if valid_val[i] and np.isfinite(pred[i]):
                residuals[i] = y_val[i] - pred[i]

        valid_resid = residuals[np.isfinite(residuals)]
        if len(valid_resid) < max_lag + 50:
            continue

        # Compute autocorrelation at each lag
        mean_r = np.mean(valid_resid)
        var_r = np.var(valid_resid)
        if var_r < 1e-10:
            continue

        acs = {}
        for lag in range(1, max_lag + 1):
            ac = np.mean((valid_resid[:-lag] - mean_r) * (valid_resid[lag:] - mean_r)) / var_r
            acs[lag] = round(float(ac), 4)

        # Find decorrelation time (first lag where |AC| < 0.1)
        decorr_lag = max_lag
        for lag in range(1, max_lag + 1):
            if abs(acs[lag]) < 0.1:
                decorr_lag = lag
                break

        patient_acs.append({
            'patient': p['name'],
            'acs': acs,
            'decorr_lag': decorr_lag,
            'decorr_minutes': decorr_lag * 5,
            'ac_at_12': acs.get(12, 0),  # At prediction horizon
            'ac_at_24': acs.get(24, 0),  # At 2h
            'ac_at_36': acs.get(36, 0),  # At 3h
        })

    if not patient_acs:
        return {'status': 'fail', 'detail': 'No valid data'}

    # Average AC curve
    avg_acs = {}
    for lag in range(1, max_lag + 1):
        vals = [pac['acs'].get(lag, 0) for pac in patient_acs]
        avg_acs[str(lag)] = round(float(np.mean(vals)), 4)

    avg_decorr = np.mean([pac['decorr_lag'] for pac in patient_acs])
    avg_ac_12 = np.mean([pac['ac_at_12'] for pac in patient_acs])

    results = {
        'per_patient': [{k: v for k, v in pac.items() if k != 'acs'} for pac in patient_acs],
        'avg_ac_curve': avg_acs,
        'avg_decorr_lag': round(float(avg_decorr), 1),
        'avg_decorr_minutes': round(float(avg_decorr * 5), 0),
        'avg_ac_at_horizon': round(float(avg_ac_12), 4),
        'exploitable': avg_ac_12 > 0.15,
    }

    return {
        'status': 'pass',
        'detail': f"decorr={avg_decorr:.1f} lags ({avg_decorr*5:.0f}min), AC@60min={avg_ac_12:.3f}",
        'results': results,
    }


# ── EXP-850: Information-Theoretic Ceiling Estimation ─────────────────────────

@register('EXP-850', 'Information-Theoretic Ceiling Estimation')
def exp_850(patients, detail=False):
    """Estimate the information-theoretic prediction ceiling.

    Multiple ceiling estimates:
    1. Oracle with future BG velocity (EXP-826 baseline)
    2. Oracle with future BG + velocity + acceleration
    3. Nearest-neighbor oracle: for each test point, use the training point
       with the most similar features and report its actual outcome
    4. Conditional variance lower bound: Var(BG_future | features)
    5. Autoregressive ceiling: AR(1) on BG at short horizons extrapolated
    """
    h_steps = 12
    lam = 10.0
    start = 24

    results_per_patient = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)

        split = int(0.8 * usable)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # 1. Base model
        pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])

        # 2. Oracle with future velocity
        bg_orig_start = h_steps + 1 + start
        future_vel = np.zeros(usable)
        for i in range(usable):
            t_future = bg_orig_start + i
            if t_future + 1 < len(bg) and t_future >= 1:
                future_vel[i] = bg[t_future] - bg[t_future - 1]

        X_oracle1 = np.hstack([features, future_vel.reshape(-1, 1)])
        X_tr_o1, X_val_o1 = X_oracle1[:split], X_oracle1[split:]
        valid_tr_o1 = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_o1), axis=1)
        pred_o1, _ = _ridge_predict(X_tr_o1[valid_tr_o1], y_tr[valid_tr_o1], X_val_o1, lam=lam * 3)
        r2_oracle_vel = _r2(pred_o1[valid_val], y_val[valid_val])

        # 3. Oracle with future velocity + acceleration
        future_accel = np.zeros(usable)
        for i in range(usable):
            t_future = bg_orig_start + i
            if t_future + 1 < len(bg) and t_future >= 2:
                future_accel[i] = bg[t_future] - 2 * bg[t_future - 1] + bg[t_future - 2]

        X_oracle2 = np.hstack([features, future_vel.reshape(-1, 1), future_accel.reshape(-1, 1)])
        X_tr_o2, X_val_o2 = X_oracle2[:split], X_oracle2[split:]
        valid_tr_o2 = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_o2), axis=1)
        pred_o2, _ = _ridge_predict(X_tr_o2[valid_tr_o2], y_tr[valid_tr_o2], X_val_o2, lam=lam * 3)
        r2_oracle_va = _r2(pred_o2[valid_val], y_val[valid_val])

        # 4. KNN oracle: find nearest training point, report its actual outcome
        # Use L2 distance in normalized feature space
        X_tr_norm = X_tr[valid_tr].copy()
        X_val_norm = X_val.copy()
        tr_std = np.std(X_tr_norm, axis=0) + 1e-10
        X_tr_norm /= tr_std
        X_val_norm /= tr_std

        y_tr_valid = y_tr[valid_tr]
        knn_preds = np.full(len(y_val), np.nan)
        for i in range(len(y_val)):
            if not valid_val[i]:
                continue
            dists = np.sum((X_tr_norm - X_val_norm[i]) ** 2, axis=1)
            k = min(5, len(dists))
            nearest_idx = np.argpartition(dists, k)[:k]
            knn_preds[i] = np.mean(y_tr_valid[nearest_idx])

        r2_knn = _r2(knn_preds[valid_val], y_val[valid_val])

        # 5. Conditional variance estimate via KNN
        cond_vars = []
        for i in range(min(500, int(valid_val.sum()))):
            valid_indices = np.where(valid_val)[0]
            if i >= len(valid_indices):
                break
            idx = valid_indices[i]
            dists = np.sum((X_tr_norm - X_val_norm[idx]) ** 2, axis=1)
            k = min(20, len(dists))
            nearest_idx = np.argpartition(dists, k)[:k]
            cond_vars.append(np.var(y_tr_valid[nearest_idx]))

        avg_cond_var = np.mean(cond_vars) if cond_vars else 0
        total_var = np.var(y_val[valid_val])
        theoretical_max_r2 = 1 - avg_cond_var / total_var if total_var > 0 else 0

        results_per_patient.append({
            'patient': p['name'],
            'r2_base': round(float(r2_base), 3) if np.isfinite(r2_base) else None,
            'r2_oracle_vel': round(float(r2_oracle_vel), 3) if np.isfinite(r2_oracle_vel) else None,
            'r2_oracle_vel_accel': round(float(r2_oracle_va), 3) if np.isfinite(r2_oracle_va) else None,
            'r2_knn_oracle': round(float(r2_knn), 3) if np.isfinite(r2_knn) else None,
            'theoretical_max_r2': round(float(theoretical_max_r2), 3),
            'avg_cond_var': round(float(avg_cond_var), 1),
        })

    if not results_per_patient:
        return {'status': 'fail', 'detail': 'No valid data'}

    # Averages
    def avg_key(key):
        vals = [r[key] for r in results_per_patient if r[key] is not None]
        return round(float(np.mean(vals)), 3) if vals else None

    summary = {
        'r2_base': avg_key('r2_base'),
        'r2_oracle_vel': avg_key('r2_oracle_vel'),
        'r2_oracle_vel_accel': avg_key('r2_oracle_vel_accel'),
        'r2_knn_oracle': avg_key('r2_knn_oracle'),
        'theoretical_max_r2': avg_key('theoretical_max_r2'),
        'gap_to_oracle': round(avg_key('r2_oracle_vel') - avg_key('r2_base'), 3)
                         if avg_key('r2_oracle_vel') and avg_key('r2_base') else None,
    }

    results = {
        'per_patient': results_per_patient,
        'summary': summary,
    }

    return {
        'status': 'pass',
        'detail': (f"base={summary['r2_base']}, oracle_vel={summary['r2_oracle_vel']}, "
                   f"knn={summary['r2_knn_oracle']}, theoretical_max={summary['theoretical_max_r2']}"),
        'results': results,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-841-850: Residual Characterization')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None,
                        help='Run single experiment (e.g. EXP-841)')
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exp_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
    exp_dir.mkdir(exist_ok=True)

    for exp_id in sorted(EXPERIMENTS.keys(), key=lambda x: int(x.split('-')[1])):
        if args.experiment and exp_id != args.experiment:
            continue

        exp = EXPERIMENTS[exp_id]
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp['name']}")
        print(f"{'='*60}")

        t0 = time.time()
        try:
            result = exp['func'](patients, detail=args.detail)
        except Exception as e:
            import traceback
            traceback.print_exc()
            result = {'status': 'fail', 'detail': str(e)}

        elapsed = time.time() - t0
        status = result.get('status', 'unknown')
        detail = result.get('detail', '')

        print(f"  Status: {status}")
        print(f"  Detail: {detail}")
        print(f"  Time: {elapsed:.1f}s")

        if args.save and 'results' in result:
            fname = f"exp_{exp_id.split('-')[1]}_{exp['name'].lower().replace(' ', '_')}.json"
            fpath = exp_dir / fname
            save_data = {
                'experiment': exp_id,
                'name': exp['name'],
                'status': status,
                'detail': detail,
                'elapsed_seconds': round(elapsed, 1),
                'results': result['results'],
            }
            with open(fpath, 'w') as f:
                json.dump(save_data, f, indent=2, default=str)
            print(f"  Saved: {fpath}")

    print(f"\n{'='*60}")
    print("All experiments complete")


if __name__ == '__main__':
    main()
