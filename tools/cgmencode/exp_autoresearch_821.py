#!/usr/bin/env python3
"""EXP-821–830: Multi-Horizon Cascade, Proper AR, and Extended Windows

Following the data leakage discovery in EXP-811, this wave explores:
1. Multi-horizon cascade (5→15→30→60min chain with valid-lag AR)
2. Proper causal AR with minimum lag = h_steps  
3. Extended BG history windows for richer context
4. Combined best features from EXP-812-818
5. Residual characterization to understand the prediction ceiling

EXP-821: Multi-Horizon Cascade (chain of predictions with valid corrections)
EXP-822: Proper Causal AR (lag ≥ h_steps, verified no leakage)
EXP-823: Extended History Window (use 1h, 2h, 4h of BG history)
EXP-824: Combined Best Features (velocity + lags + polynomial)
EXP-825: Residual Decomposition (what drives prediction error?)
EXP-826: Per-Patient Ceiling Analysis (patient-specific R² limits)
EXP-827: Meal-Aware Features (post-meal BG trajectory detection)
EXP-828: Time-of-Day Stratified Prediction (morning/afternoon/night models)
EXP-829: Adaptive λ (per-patient optimal regularization)
EXP-830: Final Validated Benchmark (all valid improvements combined)
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
    """Build the base 8-feature matrix."""
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

def _ridge_predict(X_train, y_train, X_val, lam=1.0):
    """Fit ridge regression and predict."""
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    try:
        w = np.linalg.solve(XtX, X_train.T @ y_train)
        return X_val @ w, w
    except np.linalg.LinAlgError:
        return np.full(X_val.shape[0], np.nan), None

FEATURE_NAMES = ['bg', 'Σsupply', 'Σdemand', 'Σhepatic', 'resid', 'sin_h', 'cos_h', 'bias']

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ── EXP-821: Multi-Horizon Cascade ──────────────────────────────────────────

@register('EXP-821', 'Multi-Horizon Cascade')
def exp_821(patients, detail=False):
    """Chain of predictions: 5→15→30→60min with valid-lag AR corrections.
    
    At each cascade stage, use properly-lagged AR from the previous 
    horizon's verified predictions. E.g., for 30min prediction, use
    the 15min prediction error (now resolved) as a correction signal.
    """
    horizons = [('5min', 1), ('15min', 3), ('30min', 6), ('60min', 12)]
    results = {}
    
    # Compare: independent models vs cascade
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
    
    independent_r2s = {h: [] for h, _ in horizons}
    cascade_r2s = {h: [] for h, _ in horizons}
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        
        # Use the longest horizon to determine n_pred
        max_h = 12
        n_pred = nr - max_h
        if n_pred < 200:
            continue
        
        split = int(0.8 * n_pred)
        
        # Stage 1: Independent models at each horizon
        prev_pred_errors = None  # for cascade
        
        for hname, h_steps in horizons:
            n_pred_h = nr - h_steps
            actual = bg[h_steps + 1: h_steps + 1 + n_pred]
            features = _build_features_base(fd, hours, n_pred, h_steps)
            
            X_tr, X_val = features[:split], features[split:]
            y_tr, y_val = actual[:split], actual[split:]
            
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            
            lam = {1: 0.001, 3: 0.01, 6: 1.0, 12: 10.0}[h_steps]
            
            # Independent model
            pred_ind, w = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
            r2_ind = _r2(pred_ind[valid_val], y_val[valid_val])
            if np.isfinite(r2_ind):
                independent_r2s[hname].append(r2_ind)
            
            # Cascade model: add previous horizon's prediction error as feature
            if prev_pred_errors is not None and w is not None:
                # The previous horizon's error is available with proper lag
                # For h_steps prediction, we need errors from predictions made
                # at least h_steps ago. Previous horizon's error at lag=h_steps
                # is the most useful signal that doesn't leak.
                prev_h = horizons[horizons.index((hname, h_steps)) - 1][1]
                lag = h_steps  # proper lag to avoid leakage
                
                # Get previous horizon's training errors (for fitting)
                prev_pred_tr = X_tr @ w  # approximate — use current model as proxy
                
                # Add cascade feature: previous error at proper lag
                cascade_feat_tr = np.zeros((split, 1))
                cascade_feat_val = np.zeros((len(y_val), 1))
                
                for i in range(split):
                    if i >= lag and np.isfinite(prev_pred_errors[i - lag]):
                        cascade_feat_tr[i, 0] = prev_pred_errors[i - lag]
                
                for i in range(len(y_val)):
                    gi = split + i
                    if gi >= lag and gi - lag < len(prev_pred_errors):
                        if np.isfinite(prev_pred_errors[gi - lag]):
                            cascade_feat_val[i, 0] = prev_pred_errors[gi - lag]
                
                X_tr_c = np.hstack([X_tr, cascade_feat_tr])
                X_val_c = np.hstack([X_val, cascade_feat_val])
                
                valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
                valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
                
                pred_casc, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c],
                                               X_val_c, lam=lam)
                r2_casc = _r2(pred_casc[valid_val_c], y_val[valid_val_c])
                if np.isfinite(r2_casc):
                    cascade_r2s[hname].append(r2_casc)
                else:
                    cascade_r2s[hname].append(r2_ind)
            else:
                cascade_r2s[hname].append(r2_ind if np.isfinite(r2_ind) else float('nan'))
            
            # Store prediction errors for next cascade stage
            pred_full, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], features, lam=lam)
            prev_pred_errors = actual - pred_full
    
    for hname, _ in horizons:
        if independent_r2s[hname]:
            ind_mean = np.nanmean(independent_r2s[hname])
            casc_mean = np.nanmean(cascade_r2s[hname])
            results[hname] = {
                'independent': round(ind_mean, 3),
                'cascade': round(casc_mean, 3),
                'improvement': round(casc_mean - ind_mean, 3)
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(f"{hname}: ind={r['independent']}, casc={r['cascade']}, Δ={r['improvement']:+.3f}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-822: Proper Causal AR ───────────────────────────────────────────────

@register('EXP-822', 'Proper Causal AR')
def exp_822(patients, detail=False):
    """AR correction with lag ≥ h_steps (verified no data leakage).
    
    Tests various lags from h_steps to 2*h_steps to find if any
    properly-lagged residual information helps prediction.
    """
    horizons = {'15min': 3, '30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        lag_results = {}
        baseline_r2s = []
        
        # Test lags from h_steps to 3*h_steps
        test_lags = [h_steps, h_steps + 3, h_steps + 6, 2 * h_steps, 3 * h_steps]
        
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            hours = _get_hours(p['df'], n)
            nr = len(fd['resid'])
            n_pred = nr - h_steps
            if n_pred < 200:
                continue
            
            actual = bg[h_steps + 1: h_steps + 1 + n_pred]
            features = _build_features_base(fd, hours, n_pred, h_steps)
            
            split = int(0.8 * n_pred)
            X_tr, X_val = features[:split], features[split:]
            y_tr, y_val = actual[:split], actual[split:]
            
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            
            lam = {3: 0.01, 6: 1.0, 12: 10.0}[h_steps]
            
            # Baseline ridge
            pred_tr, w = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_tr, lam=lam)
            pred_val, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
            
            if w is None:
                continue
            
            r2_base = _r2(pred_val[valid_val], y_val[valid_val])
            baseline_r2s.append(r2_base)
            
            # Full prediction for residual computation
            pred_full, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], features, lam=lam)
            full_resid = actual - pred_full
            
            for lag in test_lags:
                if lag >= split:
                    continue
                
                # Add lagged residual as feature (PROPERLY LAGGED — NO LEAKAGE)
                # residual[i - lag] is the error from prediction at step i-lag
                # which targeted step i-lag+h_steps. Since lag >= h_steps,
                # i-lag+h_steps <= i, so the target has been observed.
                lag_feat_tr = np.zeros((split, 1))
                lag_feat_val = np.zeros((len(y_val), 1))
                
                for i in range(split):
                    if i >= lag and np.isfinite(full_resid[i - lag]):
                        lag_feat_tr[i, 0] = full_resid[i - lag]
                
                for i in range(len(y_val)):
                    gi = split + i
                    if gi >= lag and gi - lag < len(full_resid) and np.isfinite(full_resid[gi - lag]):
                        lag_feat_val[i, 0] = full_resid[gi - lag]
                
                X_tr_aug = np.hstack([X_tr, lag_feat_tr])
                X_val_aug = np.hstack([X_val, lag_feat_val])
                
                valid_tr_a = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_aug), axis=1)
                valid_val_a = np.isfinite(y_val) & np.all(np.isfinite(X_val_aug), axis=1)
                
                pred_aug, _ = _ridge_predict(X_tr_aug[valid_tr_a], y_tr[valid_tr_a],
                                              X_val_aug, lam=lam)
                r2_aug = _r2(pred_aug[valid_val_a], y_val[valid_val_a])
                
                lag_key = f"lag_{lag}"
                if lag_key not in lag_results:
                    lag_results[lag_key] = []
                lag_results[lag_key].append(r2_aug if np.isfinite(r2_aug) else r2_base)
        
        if baseline_r2s:
            base_mean = np.mean(baseline_r2s)
            lag_means = {}
            for k, v in lag_results.items():
                lag_means[k] = round(np.mean(v), 3)
            
            best_lag = max(lag_means, key=lag_means.get) if lag_means else 'none'
            results[hname] = {
                'baseline': round(base_mean, 3),
                'lag_results': lag_means,
                'best_lag': best_lag,
                'best_r2': lag_means.get(best_lag, 0),
                'improvement': round(lag_means.get(best_lag, base_mean) - base_mean, 3)
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(f"{hname}: base={r['baseline']}, best={r['best_lag']}({r['best_r2']}), Δ={r['improvement']:+.3f}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-823: Extended History Window ─────────────────────────────────────────

@register('EXP-823', 'Extended History Window')
def exp_823(patients, detail=False):
    """Use extended BG history as features (1h, 2h, 4h summary statistics).
    
    Instead of individual lagged values, compute summary statistics
    (mean, std, min, max, slope) over windows of varying length.
    """
    h_steps = 12  # 60min
    window_configs = {
        'base': 0,      # no history
        '1h': 12,       # 12 steps = 1h
        '2h': 24,       # 24 steps = 2h
        '4h': 48,       # 48 steps = 4h
    }
    results = {}
    
    for wname, w_steps in window_configs.items():
        r2s = []
        
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            hours = _get_hours(p['df'], n)
            nr = len(fd['resid'])
            n_pred = nr - h_steps
            
            start = max(w_steps, 0)
            usable = n_pred - start
            if usable < 100:
                continue
            
            actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
            base_feats = _build_features_base(fd, hours, n_pred, h_steps)
            base_feats = base_feats[start:start + usable]
            
            if w_steps > 0:
                # Compute window statistics: mean, std, min, max, slope
                win_feats = np.zeros((usable, 5))
                for i in range(usable):
                    orig = i + start
                    window = bg[max(0, orig - w_steps):orig + 1]
                    valid_w = window[np.isfinite(window)]
                    if len(valid_w) >= 3:
                        win_feats[i, 0] = np.mean(valid_w)
                        win_feats[i, 1] = np.std(valid_w)
                        win_feats[i, 2] = np.min(valid_w)
                        win_feats[i, 3] = np.max(valid_w)
                        # Linear slope over window
                        x = np.arange(len(valid_w))
                        if len(x) > 1:
                            win_feats[i, 4] = np.polyfit(x, valid_w, 1)[0]
                    else:
                        win_feats[i, :] = bg[orig] if np.isfinite(bg[orig]) else 0
                
                features = np.hstack([base_feats, win_feats])
            else:
                features = base_feats
            
            split = int(0.8 * usable)
            X_tr, X_val = features[:split], features[split:]
            y_tr, y_val = actual[:split], actual[split:]
            
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            
            pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
            r2 = _r2(pred[valid_val], y_val[valid_val])
            if np.isfinite(r2):
                r2s.append(r2)
        
        if r2s:
            results[wname] = round(np.mean(r2s), 3)
    
    base = results.get('base', 0)
    best_w = max(results, key=results.get) if results else 'none'
    
    return {
        'status': 'pass',
        'detail': f"base={base}, 1h={results.get('1h','?')}, 2h={results.get('2h','?')}, "
                  f"4h={results.get('4h','?')}, best={best_w}(Δ={results.get(best_w,0)-base:+.3f})",
        'results': {'windows': results, 'best': best_w, 'improvement': round(results.get(best_w, 0) - base, 3)}
    }


# ── EXP-824: Combined Best Features ─────────────────────────────────────────

@register('EXP-824', 'Combined Best Features')
def exp_824(patients, detail=False):
    """Combine all validated improvements: velocity, acceleration,
    lagged BG, window statistics, polynomial terms.
    
    Tests whether improvements from EXP-812, 813, 818, 823 stack.
    """
    horizons = {'30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        base_r2s, combined_r2s = [], []
        
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            hours = _get_hours(p['df'], n)
            nr = len(fd['resid'])
            n_pred = nr - h_steps
            
            # Need history for lags + window stats
            start = 24  # 2h history
            usable = n_pred - start
            if usable < 100:
                continue
            
            actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
            base_feats = _build_features_base(fd, hours, n_pred, h_steps)
            base_feats = base_feats[start:start + usable]
            
            # Additional features
            extra_feats = np.zeros((usable, 10))
            for i in range(usable):
                orig = i + start
                # Velocity (EXP-818)
                if orig >= 1:
                    extra_feats[i, 0] = bg[orig] - bg[orig - 1]
                # Acceleration (EXP-818)
                if orig >= 2:
                    extra_feats[i, 1] = bg[orig] - 2 * bg[orig - 1] + bg[orig - 2]
                # Lagged BG (EXP-812): t-3, t-6
                if orig >= 3:
                    extra_feats[i, 2] = bg[orig - 3]
                if orig >= 6:
                    extra_feats[i, 3] = bg[orig - 6]
                # Window stats (EXP-823): 2h mean, std, slope
                w_start = max(0, orig - 24)
                window = bg[w_start:orig + 1]
                valid_w = window[np.isfinite(window)]
                if len(valid_w) >= 3:
                    extra_feats[i, 4] = np.mean(valid_w)
                    extra_feats[i, 5] = np.std(valid_w)
                    x = np.arange(len(valid_w))
                    extra_feats[i, 6] = np.polyfit(x, valid_w, 1)[0]
                # Polynomial: bg², supply*demand (EXP-813)
                extra_feats[i, 7] = bg[orig] ** 2 / 1000.0  # normalize
                extra_feats[i, 8] = (fd['supply'][orig] * fd['demand'][orig])
                # Range indicator
                extra_feats[i, 9] = 1.0 if bg[orig] > 180 else (
                    -1.0 if bg[orig] < 80 else 0.0)
            
            combined_feats = np.hstack([base_feats, extra_feats])
            
            split = int(0.8 * usable)
            y_tr, y_val = actual[:split], actual[split:]
            
            lam = 1.0 if hname == '30min' else 10.0
            
            # Base model
            X_tr_b, X_val_b = base_feats[:split], base_feats[split:]
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
            pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam)
            r2_base = _r2(pred_base[valid_val], y_val[valid_val])
            
            # Combined model (increased regularization for more features)
            X_tr_c, X_val_c = combined_feats[:split], combined_feats[split:]
            valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
            valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
            pred_comb, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c],
                                           X_val_c, lam=lam * 5)
            r2_comb = _r2(pred_comb[valid_val_c], y_val[valid_val_c])
            
            if np.isfinite(r2_base) and np.isfinite(r2_comb):
                base_r2s.append(r2_base)
                combined_r2s.append(r2_comb)
        
        if base_r2s:
            results[hname] = {
                'base': round(np.mean(base_r2s), 3),
                'combined': round(np.mean(combined_r2s), 3),
                'improvement': round(np.mean(combined_r2s) - np.mean(base_r2s), 3),
                'n_features_base': 8,
                'n_features_combined': 18
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(f"{hname}: base={r['base']}, combined={r['combined']}, Δ={r['improvement']:+.3f}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-825: Residual Decomposition ─────────────────────────────────────────

@register('EXP-825', 'Residual Decomposition')
def exp_825(patients, detail=False):
    """Decompose prediction residuals into explainable components.
    
    Categories: meal-related, overnight, high-BG, low-BG, rapid change.
    Identifies where the model fails most.
    """
    h_steps = 12  # 60min
    results = {'categories': {}, 'per_patient': []}
    
    all_errors = {'meal': [], 'overnight': [], 'high_bg': [], 'low_bg': [],
                  'rising': [], 'falling': [], 'stable': []}
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 100:
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        
        split = int(0.8 * n_pred)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        
        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        
        pred_hours = hours[:n_pred][split:] if hours is not None else None
        
        patient_cats = {}
        for i in range(len(y_val)):
            if not (valid_val[i] and np.isfinite(pred[i])):
                continue
            
            error = abs(y_val[i] - pred[i])
            curr_bg = features[split + i, 0]
            supply = features[split + i, 1]
            hour = pred_hours[i] if pred_hours is not None else 12
            
            # Classify the context
            velocity = bg[split + i] - bg[split + i - 1] if split + i > 0 else 0
            
            if supply > 2.0:  # active carb absorption = meal
                all_errors['meal'].append(error)
            elif 0 <= hour < 6:  # overnight
                all_errors['overnight'].append(error)
            
            if curr_bg > 200:
                all_errors['high_bg'].append(error)
            elif curr_bg < 80:
                all_errors['low_bg'].append(error)
            
            if velocity > 3:
                all_errors['rising'].append(error)
            elif velocity < -3:
                all_errors['falling'].append(error)
            else:
                all_errors['stable'].append(error)
        
        # Overall for this patient
        errors = np.abs(y_val[valid_val] - pred[valid_val])
        results['per_patient'].append({
            'patient': p['name'],
            'mae': round(float(np.mean(errors)), 1),
            'p90_error': round(float(np.percentile(errors, 90)), 1),
            'max_error': round(float(np.max(errors)), 1),
        })
    
    for cat, errs in all_errors.items():
        if errs:
            arr = np.array(errs)
            results['categories'][cat] = {
                'count': len(errs),
                'mae': round(float(np.mean(arr)), 1),
                'median': round(float(np.median(arr)), 1),
                'p90': round(float(np.percentile(arr, 90)), 1),
            }
    
    detail_parts = []
    for cat, r in sorted(results['categories'].items(), key=lambda x: -x[1]['mae']):
        detail_parts.append(f"{cat}: MAE={r['mae']}, p90={r['p90']}, n={r['count']}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-826: Per-Patient Ceiling Analysis ───────────────────────────────────

@register('EXP-826', 'Per-Patient Ceiling')
def exp_826(patients, detail=False):
    """Estimate per-patient prediction ceiling using oracle features.
    
    Add future BG velocity and future supply/demand as 'oracle' features
    to measure how much information is missing from the feature set.
    """
    h_steps = 12  # 60min
    results = {'per_patient': []}
    base_r2s, oracle_r2s = [], []
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 100:
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        
        # Oracle features: future BG change and future flux info
        oracle_feats = np.zeros((n_pred, 3))
        for i in range(n_pred):
            # Future BG velocity at midpoint (h_steps/2 ahead)
            mid = i + h_steps // 2
            if mid + 1 < n:
                oracle_feats[i, 0] = bg[mid + 1] - bg[mid]
            # Future supply integral (next h_steps)
            oracle_feats[i, 1] = np.sum(fd['supply'][i:i+h_steps])
            # Future demand integral (next h_steps)
            oracle_feats[i, 2] = np.sum(fd['demand'][i:i+h_steps])
        
        split = int(0.8 * n_pred)
        y_tr, y_val = actual[:split], actual[split:]
        
        # Base model
        X_tr_b, X_val_b = features[:split], features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=10.0)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        
        # Oracle model
        X_tr_o = np.hstack([features[:split], oracle_feats[:split]])
        X_val_o = np.hstack([features[split:], oracle_feats[split:]])
        valid_tr_o = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_o), axis=1)
        valid_val_o = np.isfinite(y_val) & np.all(np.isfinite(X_val_o), axis=1)
        pred_oracle, _ = _ridge_predict(X_tr_o[valid_tr_o], y_tr[valid_tr_o],
                                         X_val_o, lam=10.0)
        r2_oracle = _r2(pred_oracle[valid_val_o], y_val[valid_val_o])
        
        if np.isfinite(r2_base) and np.isfinite(r2_oracle):
            base_r2s.append(r2_base)
            oracle_r2s.append(r2_oracle)
            results['per_patient'].append({
                'patient': p['name'],
                'base_r2': round(r2_base, 3),
                'oracle_r2': round(r2_oracle, 3),
                'gap': round(r2_oracle - r2_base, 3),
            })
    
    results['summary'] = {
        'base_mean': round(np.mean(base_r2s), 3),
        'oracle_mean': round(np.mean(oracle_r2s), 3),
        'gap': round(np.mean(oracle_r2s) - np.mean(base_r2s), 3),
    }
    
    s = results['summary']
    return {
        'status': 'pass',
        'detail': f"base={s['base_mean']}, oracle={s['oracle_mean']}, gap={s['gap']:+.3f}",
        'results': results
    }


# ── EXP-827: Meal-Aware Features ────────────────────────────────────────────

@register('EXP-827', 'Meal-Aware Features')
def exp_827(patients, detail=False):
    """Add meal-timing features: time since last high supply,
    supply magnitude, and post-meal phase indicator.
    """
    h_steps = 12  # 60min
    results = {}
    base_r2s, meal_r2s = [], []
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 100:
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        
        # Meal-aware features
        meal_feats = np.zeros((n_pred, 4))
        supply = fd['supply']
        meal_threshold = np.percentile(supply[np.isfinite(supply) & (supply > 0)], 75) \
            if np.sum(supply > 0) > 100 else 2.0
        
        for i in range(n_pred):
            # Time since last meal (high supply)
            time_since_meal = 999
            peak_supply = 0
            for j in range(min(i, 72)):  # look back up to 6h
                if supply[i - j] > meal_threshold:
                    time_since_meal = j
                    peak_supply = max(peak_supply, supply[i - j])
                    break
            
            meal_feats[i, 0] = min(time_since_meal, 72) / 72.0  # normalized
            meal_feats[i, 1] = peak_supply
            meal_feats[i, 2] = 1.0 if time_since_meal < 24 else 0.0  # post-meal flag (2h)
            meal_feats[i, 3] = supply[i]  # current supply
        
        combined = np.hstack([features, meal_feats])
        
        split = int(0.8 * n_pred)
        y_tr, y_val = actual[:split], actual[split:]
        
        # Base
        X_tr_b, X_val_b = features[:split], features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=10.0)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        
        # Meal-aware
        X_tr_m, X_val_m = combined[:split], combined[split:]
        valid_tr_m = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_m), axis=1)
        valid_val_m = np.isfinite(y_val) & np.all(np.isfinite(X_val_m), axis=1)
        pred_meal, _ = _ridge_predict(X_tr_m[valid_tr_m], y_tr[valid_tr_m],
                                       X_val_m, lam=10.0)
        r2_meal = _r2(pred_meal[valid_val_m], y_val[valid_val_m])
        
        if np.isfinite(r2_base) and np.isfinite(r2_meal):
            base_r2s.append(r2_base)
            meal_r2s.append(r2_meal)
    
    if base_r2s:
        results = {
            'base': round(np.mean(base_r2s), 3),
            'meal_aware': round(np.mean(meal_r2s), 3),
            'improvement': round(np.mean(meal_r2s) - np.mean(base_r2s), 3),
        }
    
    return {
        'status': 'pass',
        'detail': f"base={results.get('base','?')}, meal={results.get('meal_aware','?')}, "
                  f"Δ={results.get('improvement',0):+.3f}",
        'results': results
    }


# ── EXP-828: Time-of-Day Stratified ─────────────────────────────────────────

@register('EXP-828', 'Time-of-Day Stratified')
def exp_828(patients, detail=False):
    """Train separate models for morning/afternoon/evening/night.
    
    Tests whether time-specific models outperform a single universal model.
    """
    h_steps = 12  # 60min
    time_bands = {
        'night': (0, 6),
        'morning': (6, 12),
        'afternoon': (12, 18),
        'evening': (18, 24),
    }
    
    global_r2s, stratified_r2s = [], []
    band_r2s = {b: [] for b in time_bands}
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        if hours is None:
            continue
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 200:
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        pred_hours = hours[:n_pred]
        
        split = int(0.8 * n_pred)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        hours_tr, hours_val = pred_hours[:split], pred_hours[split:]
        
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        
        # Global model
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])
        global_r2s.append(r2_global)
        
        # Stratified prediction
        pred_strat = np.full(len(y_val), np.nan)
        
        for band_name, (h_lo, h_hi) in time_bands.items():
            tr_mask = valid_tr & (hours_tr >= h_lo) & (hours_tr < h_hi)
            val_mask = (hours_val >= h_lo) & (hours_val < h_hi)
            
            if tr_mask.sum() < 30 or val_mask.sum() < 10:
                # Fall back to global for this band
                pred_strat[val_mask] = pred_global[val_mask]
                continue
            
            pred_band, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                           X_val[val_mask], lam=10.0)
            pred_strat[val_mask] = pred_band
            
            # Per-band R²
            val_band_valid = valid_val[val_mask]
            r2_band = _r2(pred_band[val_band_valid], y_val[val_mask][val_band_valid])
            r2_global_band = _r2(pred_global[val_mask][val_band_valid],
                                y_val[val_mask][val_band_valid])
            if np.isfinite(r2_band):
                band_r2s[band_name].append(r2_band)
        
        r2_strat = _r2(pred_strat[valid_val], y_val[valid_val])
        stratified_r2s.append(r2_strat)
    
    results = {
        'global': round(np.nanmean(global_r2s), 3),
        'stratified': round(np.nanmean(stratified_r2s), 3),
        'improvement': round(np.nanmean(stratified_r2s) - np.nanmean(global_r2s), 3),
        'per_band': {b: round(np.nanmean(v), 3) if v else None for b, v in band_r2s.items()},
    }
    
    return {
        'status': 'pass',
        'detail': f"global={results['global']}, strat={results['stratified']}, "
                  f"Δ={results['improvement']:+.3f}, bands={results['per_band']}",
        'results': results
    }


# ── EXP-829: Adaptive λ ─────────────────────────────────────────────────────

@register('EXP-829', 'Adaptive Lambda')
def exp_829(patients, detail=False):
    """Find per-patient optimal λ via cross-validation.
    
    Tests whether patient-specific regularization improves over
    the global λ=10.0 default.
    """
    h_steps = 12  # 60min
    lambdas = [0.001, 0.01, 0.1, 1.0, 5.0, 10.0, 50.0, 100.0]
    
    results = {'per_patient': []}
    default_r2s, adaptive_r2s = [], []
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 200:
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        
        split = int(0.8 * n_pred)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        
        # Default λ=10
        pred_default, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_default = _r2(pred_default[valid_val], y_val[valid_val])
        
        # Cross-validation to find best λ
        cv_split = int(0.6 * n_pred)  # 60% train, 20% CV, 20% test
        X_cv_tr = features[:cv_split]
        y_cv_tr = actual[:cv_split]
        X_cv_val = features[cv_split:split]
        y_cv_val = actual[cv_split:split]
        
        valid_cv_tr = np.isfinite(y_cv_tr) & np.all(np.isfinite(X_cv_tr), axis=1)
        valid_cv_val = np.isfinite(y_cv_val) & np.all(np.isfinite(X_cv_val), axis=1)
        
        best_lam = 10.0
        best_cv_r2 = -999
        
        for lam in lambdas:
            pred_cv, _ = _ridge_predict(X_cv_tr[valid_cv_tr], y_cv_tr[valid_cv_tr],
                                         X_cv_val, lam=lam)
            r2_cv = _r2(pred_cv[valid_cv_val], y_cv_val[valid_cv_val])
            if np.isfinite(r2_cv) and r2_cv > best_cv_r2:
                best_cv_r2 = r2_cv
                best_lam = lam
        
        # Test with best λ
        pred_adaptive, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=best_lam)
        r2_adaptive = _r2(pred_adaptive[valid_val], y_val[valid_val])
        
        if np.isfinite(r2_default) and np.isfinite(r2_adaptive):
            default_r2s.append(r2_default)
            adaptive_r2s.append(r2_adaptive)
            results['per_patient'].append({
                'patient': p['name'],
                'default_r2': round(r2_default, 3),
                'adaptive_r2': round(r2_adaptive, 3),
                'best_lambda': best_lam,
                'improvement': round(r2_adaptive - r2_default, 3),
            })
    
    results['summary'] = {
        'default_mean': round(np.mean(default_r2s), 3),
        'adaptive_mean': round(np.mean(adaptive_r2s), 3),
        'improvement': round(np.mean(adaptive_r2s) - np.mean(default_r2s), 3),
    }
    
    s = results['summary']
    return {
        'status': 'pass',
        'detail': f"default={s['default_mean']}, adaptive={s['adaptive_mean']}, "
                  f"Δ={s['improvement']:+.3f}",
        'results': results
    }


# ── EXP-830: Final Validated Benchmark ──────────────────────────────────────

@register('EXP-830', 'Final Validated Benchmark')
def exp_830(patients, detail=False):
    """Combine all valid improvements into a final benchmark.
    
    Compares: naive, physics, ridge baseline, ridge+best features,
    ridge+adaptive λ. No AR correction (leakage-free).
    """
    horizons = {'5min': 1, '15min': 3, '30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        naive_r2s, base_r2s, enhanced_r2s = [], [], []
        
        start = 24  # need 2h history
        
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
            
            # Naive: last BG value
            naive_pred = bg[start:start + usable]
            
            # Base ridge (8 features)
            base_feats = _build_features_base(fd, hours, n_pred, h_steps)
            base_feats = base_feats[start:start + usable]
            
            # Enhanced: base + velocity + accel + lags + window stats
            supply = fd['supply']
            extra = np.zeros((usable, 8))
            for i in range(usable):
                orig = i + start
                # Velocity & acceleration
                if orig >= 1:
                    extra[i, 0] = bg[orig] - bg[orig - 1]
                if orig >= 2:
                    extra[i, 1] = bg[orig] - 2 * bg[orig - 1] + bg[orig - 2]
                # Lagged BG
                if orig >= 6:
                    extra[i, 2] = bg[orig - 6]
                if orig >= 12:
                    extra[i, 3] = bg[orig - 12]
                # Window stats (2h)
                w = bg[max(0, orig - 24):orig + 1]
                vw = w[np.isfinite(w)]
                if len(vw) >= 3:
                    extra[i, 4] = np.mean(vw)
                    extra[i, 5] = np.std(vw)
                    x = np.arange(len(vw))
                    extra[i, 6] = np.polyfit(x, vw, 1)[0]
                # bg²
                extra[i, 7] = bg[orig] ** 2 / 1000.0
            
            enhanced_feats = np.hstack([base_feats, extra])
            
            split = int(0.8 * usable)
            y_tr, y_val = actual[:split], actual[split:]
            
            # Naive
            valid_n = np.isfinite(y_val) & np.isfinite(naive_pred[split:])
            r2_naive = _r2(naive_pred[split:][valid_n], y_val[valid_n])
            
            lam_map = {1: 0.001, 3: 0.01, 6: 1.0, 12: 10.0}
            lam = lam_map.get(h_steps, 1.0)
            
            # Base ridge
            X_tr_b, X_val_b = base_feats[:split], base_feats[split:]
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
            pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam)
            r2_base = _r2(pred_base[valid_val], y_val[valid_val])
            
            # Enhanced ridge
            X_tr_e, X_val_e = enhanced_feats[:split], enhanced_feats[split:]
            valid_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
            valid_val_e = np.isfinite(y_val) & np.all(np.isfinite(X_val_e), axis=1)
            pred_enh, _ = _ridge_predict(X_tr_e[valid_tr_e], y_tr[valid_tr_e],
                                          X_val_e, lam=lam * 3)
            r2_enh = _r2(pred_enh[valid_val_e], y_val[valid_val_e])
            
            if np.isfinite(r2_naive) and np.isfinite(r2_base) and np.isfinite(r2_enh):
                naive_r2s.append(r2_naive)
                base_r2s.append(r2_base)
                enhanced_r2s.append(r2_enh)
        
        if naive_r2s:
            results[hname] = {
                'naive': round(np.mean(naive_r2s), 3),
                'ridge_base': round(np.mean(base_r2s), 3),
                'ridge_enhanced': round(np.mean(enhanced_r2s), 3),
                'improvement_over_base': round(np.mean(enhanced_r2s) - np.mean(base_r2s), 3),
                'improvement_over_naive': round(np.mean(enhanced_r2s) - np.mean(naive_r2s), 3),
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(
            f"{hname}: naive={r['naive']}, base={r['ridge_base']}, "
            f"enhanced={r['ridge_enhanced']}(Δ={r['improvement_over_base']:+.3f})"
        )
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── CLI harness ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-821–830: Multi-Horizon Cascade & Validated Extensions')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    results_dir = Path(__file__).parent.parent.parent / "externals" / "experiments"
    results_dir.mkdir(parents=True, exist_ok=True)

    passed = 0
    failed = 0
    total = 0
    summaries = []

    for exp_id in sorted(EXPERIMENTS.keys(), key=lambda x: int(x.split('-')[1])):
        if args.only and exp_id != args.only:
            continue
        exp = EXPERIMENTS[exp_id]
        total += 1
        print(f"\n{'=' * 60}")
        print(f"Running {exp_id}: {exp['name']}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = exp['func'](patients, detail=args.detail)
            elapsed = time.time() - t0
            status = result.get('status', 'unknown')
            detail_str = result.get('detail', '')
            print(f"  Status: {status} ({elapsed:.1f}s)")
            if detail_str:
                print(f"  Detail: {detail_str[:250]}")
            if status == 'pass':
                passed += 1
                summaries.append(f"  V {exp_id} {exp['name']}: {detail_str[:80]}")
            else:
                failed += 1
                summaries.append(f"  X {exp_id} {exp['name']}: {detail_str[:80]}")

            if args.save:
                fname = f"exp_{exp_id.split('-')[1]}_{exp['name'].lower().replace(' ', '_').replace('+', '-').replace('/', '-')}.json"
                out = {**result, 'exp_id': exp_id, 'name': exp['name'], 'elapsed': round(elapsed, 1)}
                with open(results_dir / fname, 'w') as f:
                    json.dump(out, f, indent=2, default=str)
                print(f"  Saved: {fname}")

        except Exception as e:
            elapsed = time.time() - t0
            failed += 1
            print(f"  FAILED ({elapsed:.1f}s): {e}")
            import traceback
            traceback.print_exc()
            summaries.append(f"  X {exp_id} {exp['name']}: EXCEPTION {e}")

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}/{total}, Failed: {failed}/{total}")
    for s in summaries:
        print(s)


if __name__ == '__main__':
    main()
