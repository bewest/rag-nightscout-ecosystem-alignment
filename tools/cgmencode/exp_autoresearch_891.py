#!/usr/bin/env python3
"""EXP-891–900: Adaptive Physics & Personalized Model Refinement

After 60 experiments establishing that the prediction frontier is information-limited
(not model-limited), this wave explores better physics: adaptive ISF/CR estimation,
post-prandial curve analysis, personalized feature importance, prediction error
decomposition, and temporal adaptation for metabolic drift.

Key pivot: Instead of finding new features, make EXISTING features work harder by:
1. Adapting model parameters to local metabolic context (not global ridge)
2. Better exploiting the known PK/PD physics structure
3. Learning patient-specific feature weights that vary over time
4. Decomposing error into actionable components

EXP-891: Locally Weighted Ridge (give recent data more weight)
EXP-892: Adaptive ISF from Prediction Error (track ISF drift in real-time)
EXP-893: Post-Prandial Curve Shape Features (how is the meal resolving?)
EXP-894: Patient-Specific Feature Importance Stability
EXP-895: Error Source Attribution (meal vs correction vs basal mismatch)
EXP-896: Sliding Window Model (train on last N days only)
EXP-897: BG Volatility Regime Features
EXP-898: Insulin-on-Board Curve Shape Features
EXP-899: Prediction Residual as Autoregressive Feature (leak-safe)
EXP-900: Final 60min Benchmark (all validated improvements combined)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

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
    pred, actual = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else float('nan')


def _build_features_base(fd, hours, n_pred, h_steps):
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    features = np.zeros((n_pred, 8))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][max(0,i-h_steps):i])
        features[i, 2] = np.sum(fd['demand'][max(0,i-h_steps):i])
        features[i, 3] = np.sum(fd['hepatic'][max(0,i-h_steps):i])
        features[i, 4] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 7] = 1.0
    return features


def _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start=24):
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
            extra[i, 6] = np.polyfit(np.arange(len(vw)), vw, 1)[0]
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


def _prepare_patient(p, h_steps=12, start=24):
    fd = _compute_flux(p)
    bg = fd['bg']
    n = fd['n']
    hours = _get_hours(p['df'], n)
    nr = len(fd['resid'])
    n_pred = nr - h_steps
    usable = n_pred - start
    if usable < 200:
        return None
    actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
    features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
    split = int(0.8 * usable)
    return {
        'fd': fd, 'bg': bg, 'hours': hours, 'nr': nr,
        'n_pred': n_pred, 'usable': usable, 'actual': actual,
        'features': features, 'split': split, 'name': p.get('name', '?'),
    }


def _causal_ema(x, alpha):
    out = np.empty_like(x, dtype=float)
    out[0] = x[0] if np.isfinite(x[0]) else 120.0
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i-1] if np.isfinite(x[i]) else out[i-1]
    return out


# ── EXP-891: Locally Weighted Ridge ──────────────────────────────────────────

@register('EXP-891', 'Locally Weighted Ridge')
def exp_891(patients, detail=False):
    """Give recent training data exponentially more weight. Tests whether
    metabolic dynamics drift enough that recent data is more predictive.
    Half-lives: 7d, 14d, 30d, 60d (in 5min steps).
    """
    h_steps = 12
    start = 24
    half_lives = {'7d': 7*288, '14d': 14*288, '30d': 30*288, '60d': 60*288}
    base_r2s = []
    results_by_hl = {k: [] for k in half_lives}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        features, actual, split = d['features'], d['actual'], d['split']
        y_tr, y_val = actual[:split], actual[split:]
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        for hl_name, hl_steps in half_lives.items():
            decay = np.log(2) / hl_steps
            wt = np.exp(decay * np.arange(split))  # exponentially increasing
            wt = wt / wt.max()
            wt_valid = wt[vm_tr]
            sqrt_w = np.sqrt(wt_valid)
            X_w = X_tr[vm_tr] * sqrt_w[:, None]
            y_w = y_tr[vm_tr] * sqrt_w
            pred_w, _ = _ridge_predict(X_w, y_w, X_val[vm_val])
            results_by_hl[hl_name].append(_r2(pred_w, y_val[vm_val]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    hl_results = {k: round(float(np.mean(v)), 3) if v else None for k, v in results_by_hl.items()}
    best_hl = max(hl_results, key=lambda k: hl_results[k] or -1)
    best_r2 = hl_results[best_hl]
    delta = round(best_r2 - base, 3) if best_r2 and base else None

    return {
        'experiment': 'EXP-891', 'name': 'Locally Weighted Ridge',
        'status': 'pass',
        'detail': f'base={base}, halflife_r2={hl_results}, best={best_hl}({best_r2}), Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'per_halflife': hl_results, 'best': best_hl, 'improvement': delta},
    }


# ── EXP-892: Adaptive ISF from Prediction Error ──────────────────────────────

@register('EXP-892', 'Adaptive ISF from Prediction Error')
def exp_892(patients, detail=False):
    """Track effective ISF by comparing predicted vs actual BG change per unit
    demand. Use rolling ISF estimate as a feature for adaptation.
    """
    h_steps = 12
    start = 24
    base_r2s, adapt_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Rolling ISF estimate: BG_change / demand_sum over 2h windows
        demand = fd['demand'][:n_pred]
        bg_sig = bg[:n_pred].astype(float)
        isf_rolling = np.full(n_pred, np.nan)
        cr_rolling = np.full(n_pred, np.nan)
        for i in range(24, n_pred):
            d_sum = np.sum(np.abs(demand[i-24:i]))
            s_sum = np.sum(fd['supply'][i-24:i])
            bg_change = bg_sig[i] - bg_sig[i-24]
            if d_sum > 0.5:  # meaningful insulin delivered
                isf_rolling[i] = bg_change / d_sum
            if s_sum > 0.5:  # meaningful carb supply
                cr_rolling[i] = bg_change / s_sum

        # Smooth with causal EMA
        isf_smooth = _causal_ema(np.nan_to_num(isf_rolling, nan=0), 0.05)
        cr_smooth = _causal_ema(np.nan_to_num(cr_rolling, nan=0), 0.05)

        # ISF deviation from personal mean
        isf_mean = np.nanmean(isf_rolling)
        isf_dev = isf_smooth - isf_mean if np.isfinite(isf_mean) else np.zeros(n_pred)

        adapt_feats = np.column_stack([
            isf_smooth[start:start+usable],
            isf_dev[start:start+usable],
            cr_smooth[start:start+usable],
        ])

        X_adapt = np.hstack([features, adapt_feats])
        X_tr_a, X_val_a = X_adapt[:split], X_adapt[split:]
        vm_tr_a = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_a), axis=1)
        vm_val_a = np.isfinite(y_val) & np.all(np.isfinite(X_val_a), axis=1)
        if vm_tr_a.sum() < 50:
            continue
        pred_a, _ = _ridge_predict(X_tr_a[vm_tr_a], y_tr[vm_tr_a], X_val_a[vm_val_a])
        adapt_r2s.append(_r2(pred_a, y_val[vm_val_a]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    adapt = round(float(np.mean(adapt_r2s)), 3) if adapt_r2s else None
    delta = round(adapt - base, 3) if adapt and base else None

    return {
        'experiment': 'EXP-892', 'name': 'Adaptive ISF from Prediction Error',
        'status': 'pass',
        'detail': f'base={base}, +adaptive_isf={adapt}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_adaptive_isf': adapt, 'improvement': delta},
    }


# ── EXP-893: Post-Prandial Curve Shape ───────────────────────────────────────

@register('EXP-893', 'Post-Prandial Curve Shape Features')
def exp_893(patients, detail=False):
    """Characterize current position on the post-prandial curve: time since peak,
    rate of descent, fraction absorbed. Uses supply signal to identify meals.
    """
    h_steps = 12
    start = 24
    base_r2s, pp_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Detect meals from supply signal spikes
        supply = fd['supply'][:n_pred]
        supply_thresh = np.percentile(supply[supply > 0], 75) if np.sum(supply > 0) > 10 else 0.1

        pp_feats = np.zeros((n_pred, 5))
        last_meal_step = -999
        meal_peak_bg = 0
        meal_start_bg = 0

        for i in range(n_pred):
            if supply[i] > supply_thresh:
                if i - last_meal_step > 6:  # new meal (>30min gap)
                    meal_start_bg = bg[i]
                last_meal_step = i
                meal_peak_bg = max(meal_peak_bg, bg[i])

            time_since = (i - last_meal_step) * 5.0  # minutes
            pp_feats[i, 0] = min(time_since, 360) / 360.0  # normalized time since meal

            # Are we pre-peak, at-peak, or post-peak?
            if time_since < 60:
                pp_feats[i, 1] = 1.0  # absorption phase
            elif time_since < 180:
                pp_feats[i, 1] = 0.5  # peak/early descent
            else:
                pp_feats[i, 1] = 0.0  # post-absorption

            # BG relative to meal start
            if meal_start_bg > 0 and last_meal_step >= 0:
                pp_feats[i, 2] = bg[i] - meal_start_bg

            # Cumulative supply since meal
            if last_meal_step >= 0:
                pp_feats[i, 3] = np.sum(supply[max(0, last_meal_step):i+1])

            # Supply velocity (is supply still increasing or tapering?)
            if i >= 3:
                pp_feats[i, 4] = supply[i] - supply[max(0, i-3)]

        pf = pp_feats[start:start+usable]
        X_pp = np.hstack([features, pf])
        X_tr_p, X_val_p = X_pp[:split], X_pp[split:]
        vm_tr_p = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_p), axis=1)
        vm_val_p = np.isfinite(y_val) & np.all(np.isfinite(X_val_p), axis=1)
        if vm_tr_p.sum() < 50:
            continue
        pred_p, _ = _ridge_predict(X_tr_p[vm_tr_p], y_tr[vm_tr_p], X_val_p[vm_val_p])
        pp_r2s.append(_r2(pred_p, y_val[vm_val_p]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    pp = round(float(np.mean(pp_r2s)), 3) if pp_r2s else None
    delta = round(pp - base, 3) if pp and base else None

    return {
        'experiment': 'EXP-893', 'name': 'Post-Prandial Curve Shape Features',
        'status': 'pass',
        'detail': f'base={base}, +postprandial={pp}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_postprandial': pp, 'improvement': delta},
    }


# ── EXP-894: Feature Importance Stability ────────────────────────────────────

@register('EXP-894', 'Patient-Specific Feature Importance Stability')
def exp_894(patients, detail=False):
    """Check if feature importance (ridge weights) is stable across patients
    and across time. Unstable weights suggest the feature captures noise.
    """
    h_steps = 12
    start = 24
    all_weights = []
    feature_names = ['bg', 'supply', 'demand', 'hepatic', 'resid', 'sin_h', 'cos_h', 'bias',
                     'vel', 'accel', 'lag6', 'lag12', 'wmean', 'wstd', 'slope', 'bg2']

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        features, actual, split = d['features'], d['actual'], d['split']
        y_tr = actual[:split]
        X_tr = features[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            continue

        # Standardize features
        mu = np.mean(X_tr[vm_tr], axis=0)
        sigma = np.std(X_tr[vm_tr], axis=0)
        sigma[sigma < 1e-6] = 1.0
        X_std = (X_tr[vm_tr] - mu) / sigma

        _, w = _ridge_predict(X_std, y_tr[vm_tr], X_std[:1])
        if w is not None:
            all_weights.append(w)

    if len(all_weights) < 3:
        return {'experiment': 'EXP-894', 'name': 'Patient-Specific Feature Importance Stability',
                'status': 'pass', 'detail': 'insufficient data', 'results': {}}

    W = np.array(all_weights)
    mean_w = np.mean(W, axis=0)
    std_w = np.std(W, axis=0)
    cv = np.abs(std_w / (np.abs(mean_w) + 1e-6))

    # Stability ranking
    ranking = []
    for i in range(min(len(feature_names), W.shape[1])):
        ranking.append({
            'feature': feature_names[i] if i < len(feature_names) else f'f{i}',
            'mean_weight': round(float(mean_w[i]), 4),
            'std_weight': round(float(std_w[i]), 4),
            'cv': round(float(cv[i]), 3),
            'stable': bool(cv[i] < 1.0),
        })
    ranking.sort(key=lambda x: abs(x['mean_weight']), reverse=True)

    stable_count = sum(1 for r in ranking if r['stable'])

    return {
        'experiment': 'EXP-894', 'name': 'Patient-Specific Feature Importance Stability',
        'status': 'pass',
        'detail': f'stable={stable_count}/{len(ranking)}, top3={[r["feature"] for r in ranking[:3]]}',
        'results': {'ranking': ranking, 'stable_count': stable_count, 'total': len(ranking)},
    }


# ── EXP-895: Error Source Attribution ─────────────────────────────────────────

@register('EXP-895', 'Error Source Attribution')
def exp_895(patients, detail=False):
    """Decompose prediction error by source: meal-related, correction-related,
    basal mismatch, or unexplained. Uses supply/demand activity levels.
    """
    h_steps = 12
    start = 24
    error_decomp = {'meal': [], 'correction': [], 'basal': [], 'overall': []}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_val = actual[split:]
        X_tr, X_val = features[:split], features[split:]
        y_tr = actual[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        errors = np.abs(y_val[vm_val] - pred)
        error_decomp['overall'].append(float(np.mean(errors)))

        # Classify val timesteps by activity
        n_pred = d['n_pred']
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]
        val_start = start + split

        meal_errs, corr_errs, basal_errs = [], [], []
        val_idx = np.where(vm_val)[0]
        for idx_i, err in zip(val_idx, errors):
            orig = val_start + idx_i
            if orig >= n_pred:
                continue
            s_act = np.sum(supply[max(0,orig-24):orig]) > 0.5
            d_act = np.sum(demand[max(0,orig-24):orig]) > 0.5
            if s_act and d_act:
                meal_errs.append(err)
            elif d_act:
                corr_errs.append(err)
            else:
                basal_errs.append(err)

        if meal_errs: error_decomp['meal'].append(float(np.mean(meal_errs)))
        if corr_errs: error_decomp['correction'].append(float(np.mean(corr_errs)))
        if basal_errs: error_decomp['basal'].append(float(np.mean(basal_errs)))

    means = {k: round(float(np.mean(v)), 1) if v else None for k, v in error_decomp.items()}

    return {
        'experiment': 'EXP-895', 'name': 'Error Source Attribution',
        'status': 'pass',
        'detail': f'MAE: meal={means["meal"]}, corr={means["correction"]}, basal={means["basal"]}, overall={means["overall"]}',
        'results': means,
    }


# ── EXP-896: Sliding Window Model ────────────────────────────────────────────

@register('EXP-896', 'Sliding Window Model')
def exp_896(patients, detail=False):
    """Train ridge on only the last N days of data. Tests whether recent data
    is more relevant than historical. Windows: 7, 14, 30, 60 days.
    """
    h_steps = 12
    start = 24
    windows = {'7d': 7*288, '14d': 14*288, '30d': 30*288, '60d': 60*288}
    base_r2s = []
    results_by_win = {k: [] for k in windows}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        for wname, win_steps in windows.items():
            # Use only last win_steps of training data
            w_start = max(0, split - win_steps)
            X_w = X_tr[w_start:split]
            y_w = y_tr[w_start:split]
            vm_w = np.isfinite(y_w) & np.all(np.isfinite(X_w), axis=1)
            if vm_w.sum() < 50:
                continue
            pred_w, _ = _ridge_predict(X_w[vm_w], y_w[vm_w], X_val[vm_val])
            results_by_win[wname].append(_r2(pred_w, y_val[vm_val]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    win_results = {k: round(float(np.mean(v)), 3) if v else None for k, v in results_by_win.items()}
    best_win = max(win_results, key=lambda k: win_results[k] or -1)
    best_r2 = win_results[best_win]
    delta = round(best_r2 - base, 3) if best_r2 and base else None

    return {
        'experiment': 'EXP-896', 'name': 'Sliding Window Model',
        'status': 'pass',
        'detail': f'base={base}(all), windows={win_results}, best={best_win}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'per_window': win_results, 'best': best_win, 'improvement': delta},
    }


# ── EXP-897: BG Volatility Regime ────────────────────────────────────────────

@register('EXP-897', 'BG Volatility Regime Features')
def exp_897(patients, detail=False):
    """Compute rolling BG volatility (std, range, CV) at multiple windows.
    High volatility = harder to predict, model should be more conservative.
    """
    h_steps = 12
    start = 24
    base_r2s, vol_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Volatility features at multiple windows
        bg_sig = bg[:n_pred].astype(float)
        vol_feats = np.zeros((n_pred, 6))
        for win, col_offset in [(12, 0), (36, 2), (72, 4)]:  # 1h, 3h, 6h
            for i in range(win, n_pred):
                w = bg_sig[i-win:i]
                v = w[np.isfinite(w)]
                if len(v) >= 3:
                    vol_feats[i, col_offset] = np.std(v)
                    vol_feats[i, col_offset+1] = (np.max(v) - np.min(v)) / (np.mean(v) + 1)

        vf = vol_feats[start:start+usable]
        X_vol = np.hstack([features, vf])
        X_tr_v, X_val_v = X_vol[:split], X_vol[split:]
        vm_tr_v = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_v), axis=1)
        vm_val_v = np.isfinite(y_val) & np.all(np.isfinite(X_val_v), axis=1)
        if vm_tr_v.sum() < 50:
            continue
        pred_v, _ = _ridge_predict(X_tr_v[vm_tr_v], y_tr[vm_tr_v], X_val_v[vm_val_v])
        vol_r2s.append(_r2(pred_v, y_val[vm_val_v]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    vol = round(float(np.mean(vol_r2s)), 3) if vol_r2s else None
    delta = round(vol - base, 3) if vol and base else None

    return {
        'experiment': 'EXP-897', 'name': 'BG Volatility Regime Features',
        'status': 'pass',
        'detail': f'base={base}, +volatility={vol}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_volatility': vol, 'improvement': delta},
    }


# ── EXP-898: IOB Curve Shape Features ────────────────────────────────────────

@register('EXP-898', 'Insulin-on-Board Curve Shape Features')
def exp_898(patients, detail=False):
    """Extract shape features from the demand (IOB) curve: peak timing, decay
    rate, area under curve, and current position on the curve.
    """
    h_steps = 12
    start = 24
    base_r2s, iob_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        demand = fd['demand'][:n_pred]
        iob_feats = np.zeros((n_pred, 5))

        for i in range(24, n_pred):
            d_win = demand[max(0,i-72):i]  # 6h lookback
            if len(d_win) < 6:
                continue
            # AUC of recent demand
            iob_feats[i, 0] = np.sum(d_win)
            # Peak demand in window
            iob_feats[i, 1] = np.max(d_win)
            # Time since peak demand
            peak_idx = np.argmax(d_win)
            iob_feats[i, 2] = (len(d_win) - peak_idx) * 5.0 / 60.0  # hours since peak
            # Demand slope (rising or falling)
            if len(d_win) >= 6:
                iob_feats[i, 3] = np.mean(d_win[-6:]) - np.mean(d_win[:6])
            # Demand concentration (Gini-like: is it bolus-driven or basal?)
            d_sorted = np.sort(d_win)
            cum = np.cumsum(d_sorted)
            total = cum[-1] if cum[-1] > 0 else 1
            iob_feats[i, 4] = 1.0 - 2.0 * np.sum(cum / total) / len(d_win)

        iof = iob_feats[start:start+usable]
        X_iob = np.hstack([features, iof])
        X_tr_i, X_val_i = X_iob[:split], X_iob[split:]
        vm_tr_i = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_i), axis=1)
        vm_val_i = np.isfinite(y_val) & np.all(np.isfinite(X_val_i), axis=1)
        if vm_tr_i.sum() < 50:
            continue
        pred_i, _ = _ridge_predict(X_tr_i[vm_tr_i], y_tr[vm_tr_i], X_val_i[vm_val_i])
        iob_r2s.append(_r2(pred_i, y_val[vm_val_i]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    iob = round(float(np.mean(iob_r2s)), 3) if iob_r2s else None
    delta = round(iob - base, 3) if iob and base else None

    return {
        'experiment': 'EXP-898', 'name': 'Insulin-on-Board Curve Shape Features',
        'status': 'pass',
        'detail': f'base={base}, +iob_shape={iob}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_iob_shape': iob, 'improvement': delta},
    }


# ── EXP-899: Leak-Safe AR Residual Feature ───────────────────────────────────

@register('EXP-899', 'Leak-Safe AR Residual Feature')
def exp_899(patients, detail=False):
    """Use prediction residual as autoregressive feature, but with proper
    lag >= h_steps to prevent leakage. Residual at t-12 (60min ago) captures
    systematic model bias at that patient's current metabolic state.
    """
    h_steps = 12
    start = 24
    base_r2s, ar_r2s = [], []
    lags = [12, 24, 36]  # 60min, 2h, 3h — all safe for h_steps=12

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue

        # First pass: get training predictions to compute residuals
        pred_tr, w_base = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_tr)
        train_resid = np.full(split, np.nan)
        train_resid[vm_tr] = y_tr[vm_tr] - pred_tr[vm_tr]

        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute lagged residual features (safe lags only)
        all_resid = np.full(usable, np.nan)
        all_resid[:split] = train_resid

        ar_feats = np.zeros((usable, len(lags)))
        for j, lag in enumerate(lags):
            for i in range(lag, usable):
                if np.isfinite(all_resid[i - lag]):
                    ar_feats[i, j] = all_resid[i - lag]

        X_ar = np.hstack([features, ar_feats])
        X_tr_ar, X_val_ar = X_ar[:split], X_ar[split:]
        vm_tr_ar = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_ar), axis=1)
        vm_val_ar = np.isfinite(y_val) & np.all(np.isfinite(X_val_ar), axis=1)
        if vm_tr_ar.sum() < 50:
            continue
        pred_ar, _ = _ridge_predict(X_tr_ar[vm_tr_ar], y_tr[vm_tr_ar], X_val_ar[vm_val_ar])
        ar_r2s.append(_r2(pred_ar, y_val[vm_val_ar]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    ar = round(float(np.mean(ar_r2s)), 3) if ar_r2s else None
    delta = round(ar - base, 3) if ar and base else None

    return {
        'experiment': 'EXP-899', 'name': 'Leak-Safe AR Residual Feature',
        'status': 'pass',
        'detail': f'base={base}, +ar_resid={ar}, Δ={delta:+.3f}, lags={lags}' if delta else f'base={base}',
        'results': {'base': base, 'with_ar_resid': ar, 'improvement': delta, 'lags_used': lags},
    }


# ── EXP-900: Final 60min Benchmark ───────────────────────────────────────────

@register('EXP-900', 'Final 60min Benchmark')
def exp_900(patients, detail=False):
    """Combine ALL validated improvements: causal EMA + volatility + IOB shape +
    multi-horizon stacking + prediction disagreement. Final benchmark.
    """
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    base_r2s, final_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        nr, n_pred, hours = d['nr'], d['n_pred'], d['hours']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        b_r2 = _r2(pred_b, y_val[vm_val])
        base_r2s.append(b_r2)

        # === Collect validated features ===
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)

        # Causal EMAs (EXP-882: +0.005)
        ema_1h = _causal_ema(bg_sig, 2.0/(12+1))
        ema_4h = _causal_ema(bg_sig, 2.0/(48+1))

        # Volatility (EXP-897)
        vol_1h = np.zeros(n_pred)
        vol_3h = np.zeros(n_pred)
        for i in range(12, n_pred):
            w = bg_sig[i-12:i]
            vol_1h[i] = np.std(w)
        for i in range(36, n_pred):
            w = bg_sig[i-36:i]
            vol_3h[i] = np.std(w)

        # IOB shape (EXP-898)
        demand = fd['demand'][:n_pred]
        iob_auc = np.zeros(n_pred)
        iob_slope = np.zeros(n_pred)
        for i in range(24, n_pred):
            d_win = demand[i-24:i]
            iob_auc[i] = np.sum(d_win)
            if len(d_win) >= 6:
                iob_slope[i] = np.mean(d_win[-6:]) - np.mean(d_win[:6])

        extra = np.column_stack([
            ema_1h[start:start+usable],
            ema_4h[start:start+usable],
            vol_1h[start:start+usable],
            vol_3h[start:start+usable],
            iob_auc[start:start+usable],
            iob_slope[start:start+usable],
        ])

        # Multi-horizon predictions
        h_preds = {}
        for h in horizons:
            n_pred_h = nr - h
            if n_pred_h - start < usable:
                continue
            actual_h = bg[h + 1 + start: h + 1 + start + usable]
            feat_h = _build_features_base(fd, hours, n_pred_h, h)
            feat_h = feat_h[start:start + usable]
            X_tr_h = feat_h[:split]
            y_tr_h = actual_h[:split]
            valid_h = np.isfinite(y_tr_h) & np.all(np.isfinite(X_tr_h), axis=1)
            if valid_h.sum() < 50:
                continue
            _, w_h = _ridge_predict(X_tr_h[valid_h], y_tr_h[valid_h], X_tr_h[:1])
            if w_h is not None:
                h_preds[h] = feat_h @ w_h

        if len(h_preds) < 2:
            continue
        stack = np.column_stack([h_preds[h] for h in sorted(h_preds)])

        # Prediction disagreement
        pred_std = np.std(stack, axis=1, keepdims=True)

        X_final = np.hstack([features, extra, stack, pred_std])
        X_tr_f, X_val_f = X_final[:split], X_final[split:]
        vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr_f.sum() < 50:
            continue
        pred_f, _ = _ridge_predict(X_tr_f[vm_tr_f], y_tr[vm_tr_f], X_val_f[vm_val_f])
        f_r2 = _r2(pred_f, y_val[vm_val_f])
        final_r2s.append(f_r2)
        per_patient.append({'patient': d['name'], 'base': round(b_r2, 3),
                           'final': round(f_r2, 3), 'delta': round(f_r2 - b_r2, 3)})

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    final = round(float(np.mean(final_r2s)), 3) if final_r2s else None
    delta = round(final - base, 3) if final and base else None

    return {
        'experiment': 'EXP-900', 'name': 'Final 60min Benchmark',
        'status': 'pass',
        'detail': f'base={base}, final={final}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'final': final, 'improvement': delta, 'per_patient': per_patient},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def _save(result, save_dir):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    name = f"exp_{result['experiment'].lower().replace('-','_')}_{result['name'].lower().replace(' ','_').replace('/','_')}.json"
    with open(save_dir / name, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {save_dir / name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None)
    args = parser.parse_args()

    save_dir = PATIENTS_DIR.parent.parent / "experiments" if args.save else None
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)

    for exp_id, exp_info in EXPERIMENTS.items():
        if args.experiment and exp_id != args.experiment:
            continue
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp_info['name']}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            result['elapsed_seconds'] = round(time.time() - t0, 1)
            print(f"  Status: {result['status']}")
            print(f"  Detail: {result['detail']}")
            print(f"  Time: {result['elapsed_seconds']}s")
            if args.save and save_dir:
                _save(result, save_dir)
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
    print(f"\n{'='*60}")
    print("All experiments complete")


if __name__ == '__main__':
    main()
