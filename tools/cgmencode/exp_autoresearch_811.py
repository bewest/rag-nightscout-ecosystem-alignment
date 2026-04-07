#!/usr/bin/env python3
"""EXP-811–820: Two-Stage Ridge+AR, Lagged Features & Nonlinear Extensions

Following EXP-807's discovery that ridge residuals have autocorrelation=0.925,
this wave builds two-stage prediction (ridge → AR residual correction),
explores lagged BG features, polynomial features, quantile regression,
warm-start population→personal transfer, and confidence estimation.

EXP-811: Two-Stage Ridge+AR (exploit residual autocorrelation)
EXP-812: Lagged BG Features (t-1, t-2, ..., t-6 as additional features)
EXP-813: Polynomial Feature Expansion (quadratic interactions)
EXP-814: Rolling 2-Month + AR Residual Correction (combine best of 806+811)
EXP-815: Population Warm-Start + Fine-Tune (close LOO gap)
EXP-816: Per-Horizon Feature Selection (different features per horizon)
EXP-817: Confidence Estimation via Residual Variance
EXP-818: BG Velocity & Acceleration Features
EXP-819: Ensemble of Ridge Models (multiple λ values)
EXP-820: Two-Stage Ridge+AR Sweep (optimal AR order and λ)
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
    """Build the base 8-feature matrix from EXP-792/800."""
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


# ── EXP-811: Two-Stage Ridge+AR ──────────────────────────────────────────────

@register('EXP-811', 'Two-Stage Ridge+AR')
def exp_811(patients, detail=False):
    """Ridge regression followed by AR correction on residuals.
    
    EXP-807 found residual AC=0.925. This experiment exploits that
    autocorrelation by fitting an AR(p) model on ridge residuals and
    adding the AR correction to ridge predictions.
    """
    horizons = {'30min': 6, '60min': 12}
    ar_orders = [1, 2, 3, 6, 12]
    results = {}
    
    for hname, h_steps in horizons.items():
        ridge_only_r2s = []
        best_ar_r2s = []
        best_ar_orders = []
        per_patient = []
        
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
            
            valid = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_v = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            
            lam = 1.0 if hname == '30min' else 10.0
            ridge_pred_tr, w = _ridge_predict(X_tr[valid], y_tr[valid], X_tr, lam=lam)
            ridge_pred_val, _ = _ridge_predict(X_tr[valid], y_tr[valid], X_val, lam=lam)
            
            if w is None:
                continue
            
            ridge_r2 = _r2(ridge_pred_val[valid_v], y_val[valid_v])
            ridge_only_r2s.append(ridge_r2)
            
            # Compute ridge residuals on training set
            ridge_resid_tr = y_tr - ridge_pred_tr
            
            # Try different AR orders
            order_results = {}
            for p_order in ar_orders:
                if split < p_order + 50:
                    continue
                
                # Build AR design matrix from training ridge residuals
                n_ar = split - p_order
                X_ar = np.zeros((n_ar, p_order + 1))  # AR coefficients + bias
                y_ar = np.zeros(n_ar)
                
                tr_valid = np.isfinite(ridge_resid_tr)
                for i in range(n_ar):
                    idx = i + p_order
                    if not tr_valid[idx]:
                        X_ar[i] = np.nan
                        y_ar[i] = np.nan
                        continue
                    all_valid = True
                    for j in range(p_order):
                        if not tr_valid[idx - j - 1]:
                            all_valid = False
                            break
                        X_ar[i, j] = ridge_resid_tr[idx - j - 1]
                    if not all_valid:
                        X_ar[i] = np.nan
                        y_ar[i] = np.nan
                        continue
                    X_ar[i, p_order] = 1.0
                    y_ar[i] = ridge_resid_tr[idx]
                
                ar_valid = np.all(np.isfinite(X_ar), axis=1) & np.isfinite(y_ar)
                if ar_valid.sum() < p_order + 10:
                    continue
                
                # Fit AR model
                ar_pred_val_corr, ar_w = _ridge_predict(
                    X_ar[ar_valid], y_ar[ar_valid],
                    np.zeros((1, p_order + 1)),  # placeholder
                    lam=0.01
                )
                if ar_w is None:
                    continue
                
                # Apply AR correction to validation predictions
                ridge_resid_val = y_val - ridge_pred_val
                n_val = len(y_val)
                
                # Build full residual sequence (train + val) for AR input
                full_resid = np.concatenate([ridge_resid_tr, ridge_resid_val])
                corrected_val = np.copy(ridge_pred_val)
                
                for i in range(n_val):
                    global_idx = split + i
                    if global_idx < p_order:
                        continue
                    x_ar_i = np.zeros(p_order + 1)
                    all_ok = True
                    for j in range(p_order):
                        prev_idx = global_idx - j - 1
                        if prev_idx < 0 or not np.isfinite(full_resid[prev_idx]):
                            all_ok = False
                            break
                        x_ar_i[j] = full_resid[prev_idx]
                    if not all_ok:
                        continue
                    x_ar_i[p_order] = 1.0
                    corrected_val[i] += x_ar_i @ ar_w
                
                ar_r2 = _r2(corrected_val[valid_v], y_val[valid_v])
                order_results[p_order] = ar_r2
            
            if order_results:
                best_order = max(order_results, key=order_results.get)
                best_r2 = order_results[best_order]
                best_ar_r2s.append(best_r2)
                best_ar_orders.append(best_order)
                per_patient.append({
                    'patient': p['name'],
                    'ridge_r2': round(ridge_r2, 3),
                    'best_ar_r2': round(best_r2, 3),
                    'improvement': round(best_r2 - ridge_r2, 3),
                    'best_order': best_order,
                    'all_orders': {str(k): round(v, 3) for k, v in order_results.items()}
                })
            else:
                best_ar_r2s.append(ridge_r2)
                best_ar_orders.append(0)
        
        if ridge_only_r2s:
            mean_ridge = np.mean(ridge_only_r2s)
            mean_ar = np.mean(best_ar_r2s)
            results[hname] = {
                'ridge_r2': round(mean_ridge, 3),
                'ridge_ar_r2': round(mean_ar, 3),
                'improvement': round(mean_ar - mean_ridge, 3),
                'per_patient': per_patient
            }
    
    detail_parts = []
    for hname, r in results.items():
        imp = r['improvement']
        detail_parts.append(f"{hname}: ridge={r['ridge_r2']}, +AR={r['ridge_ar_r2']}, Δ={imp:+.3f}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-812: Lagged BG Features ─────────────────────────────────────────────

@register('EXP-812', 'Lagged BG Features')
def exp_812(patients, detail=False):
    """Add lagged BG values (t-1, t-2, ..., t-k) as features.
    
    Current model uses only bg[t]. Adding bg[t-1]..bg[t-k] captures
    BG velocity and trajectory implicitly.
    """
    lag_configs = {
        'lag0': 0,  # baseline (no lags)
        'lag1': 1,
        'lag3': 3,
        'lag6': 6,
        'lag12': 12,
    }
    horizons = {'30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        config_results = {}
        
        for lag_name, n_lags in lag_configs.items():
            r2s = []
            
            for p in patients:
                fd = _compute_flux(p)
                bg = fd['bg']
                n = fd['n']
                hours = _get_hours(p['df'], n)
                nr = len(fd['resid'])
                n_pred = nr - h_steps
                
                # Need n_lags history points before each prediction
                start = max(n_lags, 0)
                usable = n_pred - start
                if usable < 100:
                    continue
                
                actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
                
                # Build base features for usable range
                base_feats = _build_features_base(fd, hours, n_pred, h_steps)
                base_feats = base_feats[start:start + usable]
                
                # Add lagged BG columns
                if n_lags > 0:
                    lag_feats = np.zeros((usable, n_lags))
                    for i in range(usable):
                        orig_idx = i + start
                        for lag in range(n_lags):
                            lag_idx = orig_idx - lag - 1
                            if lag_idx >= 0:
                                lag_feats[i, lag] = bg[lag_idx]
                    features = np.hstack([base_feats, lag_feats])
                else:
                    features = base_feats
                
                split = int(0.8 * usable)
                X_tr, X_val = features[:split], features[split:]
                y_tr, y_val = actual[:split], actual[split:]
                
                valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
                valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
                
                lam = 1.0 if hname == '30min' else 10.0
                pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
                r2 = _r2(pred[valid_val], y_val[valid_val])
                if np.isfinite(r2):
                    r2s.append(r2)
            
            if r2s:
                config_results[lag_name] = round(np.mean(r2s), 3)
        
        if config_results:
            best_config = max(config_results, key=config_results.get)
            baseline = config_results.get('lag0', 0)
            results[hname] = {
                'configs': config_results,
                'best': best_config,
                'best_r2': config_results[best_config],
                'improvement': round(config_results[best_config] - baseline, 3)
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(f"{hname}: best={r['best']}(R²={r['best_r2']}), Δ={r['improvement']:+.3f}")
        detail_parts.append(f"  configs: {r['configs']}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-813: Polynomial Feature Expansion ────────────────────────────────────

@register('EXP-813', 'Polynomial Features')
def exp_813(patients, detail=False):
    """Add polynomial (degree-2) feature interactions.
    
    Tests whether quadratic terms and pairwise interactions between
    physics features improve predictions.
    """
    horizons = {'30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        base_r2s, poly_r2s = [], []
        
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
            
            # Polynomial expansion: add squares and pairwise products
            # of physics-relevant features (bg, supply, demand, hepatic, resid)
            physics_cols = features[:, :5]  # first 5 columns
            n_phys = physics_cols.shape[1]
            
            # Squares
            squares = physics_cols ** 2
            
            # Pairwise interactions
            interactions = []
            for i in range(n_phys):
                for j in range(i + 1, n_phys):
                    interactions.append(physics_cols[:, i] * physics_cols[:, j])
            interactions = np.column_stack(interactions) if interactions else np.zeros((n_pred, 0))
            
            poly_features = np.hstack([features, squares, interactions])
            
            split = int(0.8 * n_pred)
            
            # Base model
            X_tr, X_val = features[:split], features[split:]
            y_tr, y_val = actual[:split], actual[split:]
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            lam = 1.0 if hname == '30min' else 10.0
            pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
            base_r2 = _r2(pred_base[valid_val], y_val[valid_val])
            
            # Poly model (higher regularization for more features)
            Xp_tr, Xp_val = poly_features[:split], poly_features[split:]
            valid_tr_p = np.isfinite(y_tr) & np.all(np.isfinite(Xp_tr), axis=1)
            valid_val_p = np.isfinite(y_val) & np.all(np.isfinite(Xp_val), axis=1)
            lam_poly = lam * 10  # increase regularization for expanded features
            pred_poly, _ = _ridge_predict(Xp_tr[valid_tr_p], y_tr[valid_tr_p], Xp_val, lam=lam_poly)
            poly_r2 = _r2(pred_poly[valid_val_p], y_val[valid_val_p])
            
            if np.isfinite(base_r2) and np.isfinite(poly_r2):
                base_r2s.append(base_r2)
                poly_r2s.append(poly_r2)
        
        if base_r2s:
            results[hname] = {
                'base_r2': round(np.mean(base_r2s), 3),
                'poly_r2': round(np.mean(poly_r2s), 3),
                'improvement': round(np.mean(poly_r2s) - np.mean(base_r2s), 3),
                'n_base_features': 8,
                'n_poly_features': 8 + 5 + 10  # base + squares + C(5,2) interactions
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(
            f"{hname}: base={r['base_r2']}, poly={r['poly_r2']}, "
            f"Δ={r['improvement']:+.3f} ({r['n_poly_features']} features)"
        )
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-814: Rolling 2-Month + AR Correction ────────────────────────────────

@register('EXP-814', 'Rolling Ridge + AR Correction')
def exp_814(patients, detail=False):
    """Combine rolling 2-month ridge (EXP-806 best) with AR residual correction.
    
    This is the synthesis experiment: best window + best post-processing.
    """
    h_steps = 12  # 60min
    window_days = 60  # 2 months
    window_steps = window_days * 24 * 12  # 5min intervals
    ar_order = 3  # moderate order
    
    results = {'per_patient': []}
    full_r2s, rolling_r2s, rolling_ar_r2s = [], [], []
    
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
        
        # 1. Full training ridge
        pred_full, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_full = _r2(pred_full[valid_val], y_val[valid_val])
        
        # 2. Rolling 2-month ridge
        pred_rolling = np.full(len(y_val), np.nan)
        for i in range(len(y_val)):
            global_idx = split + i
            start_idx = max(0, global_idx - window_steps)
            X_win = features[start_idx:global_idx]
            y_win = actual[start_idx:global_idx]
            win_valid = np.isfinite(y_win) & np.all(np.isfinite(X_win), axis=1)
            if win_valid.sum() < 50:
                pred_rolling[i] = pred_full[i] if np.isfinite(pred_full[i]) else np.nan
                continue
            p_i, _ = _ridge_predict(X_win[win_valid], y_win[win_valid],
                                     features[global_idx:global_idx+1], lam=10.0)
            pred_rolling[i] = p_i[0]
        
        r2_rolling = _r2(pred_rolling[valid_val], y_val[valid_val])
        
        # 3. Rolling + AR correction
        # First get rolling residuals on training set for AR fitting
        pred_tr_rolling = np.full(split, np.nan)
        for i in range(split):
            start_idx = max(0, i - window_steps)
            X_win = features[start_idx:i]
            y_win = actual[start_idx:i]
            if len(X_win) < 50:
                continue
            win_valid = np.isfinite(y_win) & np.all(np.isfinite(X_win), axis=1)
            if win_valid.sum() < 50:
                continue
            p_i, _ = _ridge_predict(X_win[win_valid], y_win[win_valid],
                                     features[i:i+1], lam=10.0)
            pred_tr_rolling[i] = p_i[0]
        
        tr_resid = y_tr - pred_tr_rolling
        
        # Fit AR on training residuals
        n_ar = split - ar_order
        X_ar = np.zeros((n_ar, ar_order + 1))
        y_ar = np.zeros(n_ar)
        for i in range(n_ar):
            idx = i + ar_order
            if not np.isfinite(tr_resid[idx]):
                X_ar[i] = np.nan
                y_ar[i] = np.nan
                continue
            all_ok = True
            for j in range(ar_order):
                if not np.isfinite(tr_resid[idx - j - 1]):
                    all_ok = False
                    break
                X_ar[i, j] = tr_resid[idx - j - 1]
            if not all_ok:
                X_ar[i] = np.nan
                y_ar[i] = np.nan
                continue
            X_ar[i, ar_order] = 1.0
            y_ar[i] = tr_resid[idx]
        
        ar_valid = np.all(np.isfinite(X_ar), axis=1) & np.isfinite(y_ar)
        pred_rolling_ar = np.copy(pred_rolling)
        
        if ar_valid.sum() > ar_order + 10:
            _, ar_w = _ridge_predict(X_ar[ar_valid], y_ar[ar_valid],
                                      np.zeros((1, ar_order + 1)), lam=0.01)
            if ar_w is not None:
                # Apply AR correction to validation
                full_resid = np.concatenate([tr_resid, y_val - pred_rolling])
                for i in range(len(y_val)):
                    global_idx = split + i
                    x_i = np.zeros(ar_order + 1)
                    all_ok = True
                    for j in range(ar_order):
                        prev = global_idx - j - 1
                        if prev < 0 or not np.isfinite(full_resid[prev]):
                            all_ok = False
                            break
                        x_i[j] = full_resid[prev]
                    if not all_ok:
                        continue
                    x_i[ar_order] = 1.0
                    pred_rolling_ar[i] += x_i @ ar_w
        
        r2_rolling_ar = _r2(pred_rolling_ar[valid_val], y_val[valid_val])
        
        full_r2s.append(r2_full)
        rolling_r2s.append(r2_rolling)
        rolling_ar_r2s.append(r2_rolling_ar)
        
        results['per_patient'].append({
            'patient': p['name'],
            'full': round(r2_full, 3),
            'rolling': round(r2_rolling, 3),
            'rolling_ar': round(r2_rolling_ar, 3),
        })
    
    results['summary'] = {
        'full_r2': round(np.mean(full_r2s), 3),
        'rolling_r2': round(np.mean(rolling_r2s), 3),
        'rolling_ar_r2': round(np.mean(rolling_ar_r2s), 3),
        'rolling_improvement': round(np.mean(rolling_r2s) - np.mean(full_r2s), 3),
        'ar_improvement': round(np.mean(rolling_ar_r2s) - np.mean(rolling_r2s), 3),
        'total_improvement': round(np.mean(rolling_ar_r2s) - np.mean(full_r2s), 3),
    }
    
    s = results['summary']
    return {
        'status': 'pass',
        'detail': (f"full={s['full_r2']}, rolling={s['rolling_r2']}, "
                   f"rolling+AR={s['rolling_ar_r2']}, total Δ={s['total_improvement']:+.3f}"),
        'results': results
    }


# ── EXP-815: Population Warm-Start + Fine-Tune ──────────────────────────────

@register('EXP-815', 'Population Warm-Start')
def exp_815(patients, detail=False):
    """Train population model, then fine-tune on target patient.
    
    EXP-804 showed LOO gap of -0.144. This tests whether warm-starting
    from population weights and fine-tuning with limited personal data
    can close that gap.
    """
    h_steps = 12  # 60min
    finetune_fractions = [0.05, 0.1, 0.2, 0.5]  # of training data
    results = {'per_patient': []}
    
    # First collect all patient features
    all_feats = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        if n_pred < 100:
            actual = bg[h_steps + 1: h_steps + 1 + max(n_pred, 0)]
            all_feats.append({'features': np.zeros((0, 8)), 'actual': np.array([]),
                             'n_pred': 0, 'name': p['name']})
            continue
        
        actual = bg[h_steps + 1: h_steps + 1 + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        all_feats.append({'features': features, 'actual': actual,
                         'n_pred': n_pred, 'name': p['name']})
    
    personal_r2s = []
    pop_r2s = []
    finetune_r2s = {f: [] for f in finetune_fractions}
    
    for test_idx in range(len(all_feats)):
        test = all_feats[test_idx]
        if test['n_pred'] < 100:
            continue
        
        split = int(0.8 * test['n_pred'])
        X_test_tr = test['features'][:split]
        y_test_tr = test['actual'][:split]
        X_test_val = test['features'][split:]
        y_test_val = test['actual'][split:]
        
        valid_tr = np.isfinite(y_test_tr) & np.all(np.isfinite(X_test_tr), axis=1)
        valid_val = np.isfinite(y_test_val) & np.all(np.isfinite(X_test_val), axis=1)
        
        # 1. Personal model (full training data)
        pred_personal, _ = _ridge_predict(X_test_tr[valid_tr], y_test_tr[valid_tr],
                                           X_test_val, lam=10.0)
        r2_personal = _r2(pred_personal[valid_val], y_test_val[valid_val])
        personal_r2s.append(r2_personal)
        
        # 2. Population model (trained on all other patients)
        pop_X = []
        pop_y = []
        for i, af in enumerate(all_feats):
            if i == test_idx or af['n_pred'] < 100:
                continue
            valid_i = np.isfinite(af['actual']) & np.all(np.isfinite(af['features']), axis=1)
            pop_X.append(af['features'][valid_i])
            pop_y.append(af['actual'][valid_i])
        
        if not pop_X:
            continue
        
        pop_X = np.vstack(pop_X)
        pop_y = np.concatenate(pop_y)
        
        pred_pop, w_pop = _ridge_predict(pop_X, pop_y, X_test_val, lam=10.0)
        r2_pop = _r2(pred_pop[valid_val], y_test_val[valid_val])
        pop_r2s.append(r2_pop)
        
        # 3. Fine-tune: use population weights as initialization
        patient_info = {'patient': test['name'], 'personal': round(r2_personal, 3),
                       'population': round(r2_pop, 3)}
        
        for frac in finetune_fractions:
            n_ft = max(int(frac * valid_tr.sum()), 20)
            # Use last n_ft valid training samples (most recent)
            valid_indices = np.where(valid_tr)[0]
            ft_indices = valid_indices[-n_ft:]
            
            X_ft = X_test_tr[ft_indices]
            y_ft = y_test_tr[ft_indices]
            
            # Fine-tune: combine population prior with personal data
            # Ridge with population weights as regularization target
            # w = (X'X + λI)^{-1} (X'y + λ w_pop)
            if w_pop is not None:
                XtX = X_ft.T @ X_ft + 10.0 * np.eye(X_ft.shape[1])
                Xty = X_ft.T @ y_ft + 10.0 * w_pop
                try:
                    w_ft = np.linalg.solve(XtX, Xty)
                    pred_ft = X_test_val @ w_ft
                    r2_ft = _r2(pred_ft[valid_val], y_test_val[valid_val])
                except np.linalg.LinAlgError:
                    r2_ft = float('nan')
            else:
                r2_ft = float('nan')
            
            finetune_r2s[frac].append(r2_ft)
            patient_info[f'ft_{frac}'] = round(r2_ft, 3) if np.isfinite(r2_ft) else None
        
        results['per_patient'].append(patient_info)
    
    results['summary'] = {
        'personal_r2': round(np.mean(personal_r2s), 3),
        'population_r2': round(np.mean(pop_r2s), 3),
        'gap': round(np.mean(pop_r2s) - np.mean(personal_r2s), 3),
    }
    for frac in finetune_fractions:
        vals = [v for v in finetune_r2s[frac] if np.isfinite(v)]
        if vals:
            results['summary'][f'finetune_{frac}_r2'] = round(np.mean(vals), 3)
            results['summary'][f'finetune_{frac}_gap'] = round(
                np.mean(vals) - np.mean(personal_r2s), 3)
    
    s = results['summary']
    ft_parts = [f"ft_{f}={s.get(f'finetune_{f}_r2', '?')}" for f in finetune_fractions]
    return {
        'status': 'pass',
        'detail': f"personal={s['personal_r2']}, pop={s['population_r2']}, " + ', '.join(ft_parts),
        'results': results
    }


# ── EXP-816: Per-Horizon Feature Selection ───────────────────────────────────

@register('EXP-816', 'Per-Horizon Feature Selection')
def exp_816(patients, detail=False):
    """Test different feature subsets optimized per horizon.
    
    Short horizons may need only BG + velocity. Long horizons may need
    physics features more. Test systematically.
    """
    horizons = {'5min': 1, '15min': 3, '30min': 6, '60min': 12}
    
    feature_sets = {
        'full': list(range(8)),              # all 8 features
        'bg_only': [0, 7],                   # bg + bias
        'bg_physics': [0, 1, 2, 3, 7],       # bg + supply/demand/hepatic + bias
        'bg_resid': [0, 4, 7],               # bg + residual + bias
        'bg_resid_circ': [0, 4, 5, 6, 7],    # bg + resid + circadian + bias
        'physics_only': [1, 2, 3, 4, 7],     # supply/demand/hepatic/resid + bias (no bg!)
    }
    
    results = {}
    
    for hname, h_steps in horizons.items():
        set_results = {}
        
        for set_name, cols in feature_sets.items():
            r2s = []
            
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
                features = _build_features_base(fd, hours, n_pred, h_steps)[:, cols]
                
                split = int(0.8 * n_pred)
                X_tr, X_val = features[:split], features[split:]
                y_tr, y_val = actual[:split], actual[split:]
                
                valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
                valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
                
                lam_map = {'5min': 0.001, '15min': 0.01, '30min': 1.0, '60min': 10.0}
                pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val,
                                          lam=lam_map.get(hname, 1.0))
                r2 = _r2(pred[valid_val], y_val[valid_val])
                if np.isfinite(r2):
                    r2s.append(r2)
            
            if r2s:
                set_results[set_name] = round(np.mean(r2s), 3)
        
        if set_results:
            best_set = max(set_results, key=set_results.get)
            results[hname] = {
                'sets': set_results,
                'best': best_set,
                'best_r2': set_results[best_set]
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(f"{hname}: best={r['best']}({r['best_r2']})")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-817: Confidence Estimation ──────────────────────────────────────────

@register('EXP-817', 'Confidence Estimation')
def exp_817(patients, detail=False):
    """Estimate prediction confidence via local residual variance.
    
    Bin predictions by BG level and compute expected error per bin.
    Also test whether prediction uncertainty correlates with actual error.
    """
    h_steps = 12  # 60min
    bg_bins = [(0, 80), (80, 120), (120, 180), (180, 250), (250, 500)]
    
    all_pred = []
    all_actual = []
    all_bg = []
    
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
        
        # Collect valid predictions
        for i in range(len(y_val)):
            if valid_val[i] and np.isfinite(pred[i]):
                all_pred.append(pred[i])
                all_actual.append(y_val[i])
                all_bg.append(features[split + i, 0])  # current BG
    
    all_pred = np.array(all_pred)
    all_actual = np.array(all_actual)
    all_bg = np.array(all_bg)
    errors = np.abs(all_actual - all_pred)
    
    bin_results = {}
    for lo, hi in bg_bins:
        mask = (all_bg >= lo) & (all_bg < hi)
        if mask.sum() < 20:
            continue
        bin_results[f'{lo}-{hi}'] = {
            'count': int(mask.sum()),
            'mae': round(float(np.mean(errors[mask])), 1),
            'std': round(float(np.std(errors[mask])), 1),
            'mean_bg': round(float(np.mean(all_bg[mask])), 1),
            'r2': round(_r2(all_pred[mask], all_actual[mask]), 3),
        }
    
    # Calibration check: do predictions correlate with confidence?
    # Use prediction distance from mean as proxy for uncertainty
    pred_dist = np.abs(all_pred - np.mean(all_pred))
    # Sort by distance and check if error increases
    sort_idx = np.argsort(pred_dist)
    n_quartile = len(sort_idx) // 4
    quartile_maes = []
    for q in range(4):
        q_idx = sort_idx[q * n_quartile: (q + 1) * n_quartile]
        quartile_maes.append(round(float(np.mean(errors[q_idx])), 1))
    
    results = {
        'bins': bin_results,
        'quartile_mae_by_pred_distance': quartile_maes,
        'total_mae': round(float(np.mean(errors)), 1),
        'total_count': len(all_pred),
    }
    
    detail_parts = [f"n={len(all_pred)}, MAE={results['total_mae']}"]
    for bname, b in bin_results.items():
        detail_parts.append(f"  BG {bname}: MAE={b['mae']}, R²={b['r2']}, n={b['count']}")
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-818: BG Velocity & Acceleration Features ────────────────────────────

@register('EXP-818', 'BG Velocity & Acceleration')
def exp_818(patients, detail=False):
    """Add BG first and second derivatives as features.
    
    Velocity (ΔBG/Δt) and acceleration (Δ²BG/Δt²) capture the
    trajectory beyond the current BG level.
    """
    horizons = {'30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        base_r2s, vel_r2s, accel_r2s = [], [], []
        
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            hours = _get_hours(p['df'], n)
            nr = len(fd['resid'])
            n_pred = nr - h_steps
            
            # Need at least 2 points of history for acceleration
            start = 2
            usable = n_pred - start
            if usable < 100:
                continue
            
            actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
            base_feats = _build_features_base(fd, hours, n_pred, h_steps)
            base_feats = base_feats[start:start + usable]
            
            # Compute velocity and acceleration
            velocity = np.zeros(usable)
            acceleration = np.zeros(usable)
            for i in range(usable):
                orig = i + start
                if orig >= 1:
                    velocity[i] = bg[orig] - bg[orig - 1]
                if orig >= 2:
                    acceleration[i] = (bg[orig] - 2 * bg[orig - 1] + bg[orig - 2])
            
            vel_feats = np.hstack([base_feats, velocity.reshape(-1, 1)])
            accel_feats = np.hstack([base_feats, velocity.reshape(-1, 1),
                                     acceleration.reshape(-1, 1)])
            
            split = int(0.8 * usable)
            y_tr, y_val = actual[:split], actual[split:]
            
            lam = 1.0 if hname == '30min' else 10.0
            
            # Base
            X_tr, X_val = base_feats[:split], base_feats[split:]
            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
            r2_base = _r2(pred_base[valid_val], y_val[valid_val])
            
            # Velocity
            X_tr_v, X_val_v = vel_feats[:split], vel_feats[split:]
            valid_tr_v = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_v), axis=1)
            valid_val_v = np.isfinite(y_val) & np.all(np.isfinite(X_val_v), axis=1)
            pred_vel, _ = _ridge_predict(X_tr_v[valid_tr_v], y_tr[valid_tr_v], X_val_v, lam=lam)
            r2_vel = _r2(pred_vel[valid_val_v], y_val[valid_val_v])
            
            # Velocity + Acceleration
            X_tr_a, X_val_a = accel_feats[:split], accel_feats[split:]
            valid_tr_a = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_a), axis=1)
            valid_val_a = np.isfinite(y_val) & np.all(np.isfinite(X_val_a), axis=1)
            pred_accel, _ = _ridge_predict(X_tr_a[valid_tr_a], y_tr[valid_tr_a], X_val_a, lam=lam)
            r2_accel = _r2(pred_accel[valid_val_a], y_val[valid_val_a])
            
            if np.isfinite(r2_base) and np.isfinite(r2_vel) and np.isfinite(r2_accel):
                base_r2s.append(r2_base)
                vel_r2s.append(r2_vel)
                accel_r2s.append(r2_accel)
        
        if base_r2s:
            results[hname] = {
                'base_r2': round(np.mean(base_r2s), 3),
                'velocity_r2': round(np.mean(vel_r2s), 3),
                'accel_r2': round(np.mean(accel_r2s), 3),
                'vel_improvement': round(np.mean(vel_r2s) - np.mean(base_r2s), 3),
                'accel_improvement': round(np.mean(accel_r2s) - np.mean(base_r2s), 3),
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(
            f"{hname}: base={r['base_r2']}, +vel={r['velocity_r2']}(Δ={r['vel_improvement']:+.3f}), "
            f"+accel={r['accel_r2']}(Δ={r['accel_improvement']:+.3f})"
        )
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-819: Ridge Ensemble ─────────────────────────────────────────────────

@register('EXP-819', 'Ridge Ensemble')
def exp_819(patients, detail=False):
    """Ensemble of ridge models with different λ values.
    
    Average predictions from multiple regularization strengths to
    balance bias-variance tradeoff.
    """
    lambdas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
    horizons = {'30min': 6, '60min': 12}
    results = {}
    
    for hname, h_steps in horizons.items():
        individual_r2s = {lam: [] for lam in lambdas}
        ensemble_r2s = []
        best_single_r2s = []
        
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
            
            preds = {}
            for lam in lambdas:
                pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
                preds[lam] = pred
                r2 = _r2(pred[valid_val], y_val[valid_val])
                if np.isfinite(r2):
                    individual_r2s[lam].append(r2)
            
            # Ensemble: simple average of all predictions
            ensemble_pred = np.mean(list(preds.values()), axis=0)
            r2_ensemble = _r2(ensemble_pred[valid_val], y_val[valid_val])
            if np.isfinite(r2_ensemble):
                ensemble_r2s.append(r2_ensemble)
            
            # Best single model for this patient
            best_lam = max(preds.keys(),
                          key=lambda l: _r2(preds[l][valid_val], y_val[valid_val])
                              if np.isfinite(_r2(preds[l][valid_val], y_val[valid_val])) else -999)
            best_r2 = _r2(preds[best_lam][valid_val], y_val[valid_val])
            if np.isfinite(best_r2):
                best_single_r2s.append(best_r2)
        
        if ensemble_r2s:
            ind_means = {str(lam): round(np.mean(individual_r2s[lam]), 3)
                        for lam in lambdas if individual_r2s[lam]}
            results[hname] = {
                'individual': ind_means,
                'ensemble_r2': round(np.mean(ensemble_r2s), 3),
                'best_single_r2': round(np.mean(best_single_r2s), 3),
                'ensemble_vs_best': round(np.mean(ensemble_r2s) - np.mean(best_single_r2s), 3),
            }
    
    detail_parts = []
    for hname, r in results.items():
        detail_parts.append(
            f"{hname}: ensemble={r['ensemble_r2']}, best_single={r['best_single_r2']}, "
            f"Δ={r['ensemble_vs_best']:+.3f}"
        )
    
    return {
        'status': 'pass',
        'detail': '; '.join(detail_parts),
        'results': results
    }


# ── EXP-820: Two-Stage Ridge+AR Sweep ───────────────────────────────────────

@register('EXP-820', 'Ridge+AR Sweep')
def exp_820(patients, detail=False):
    """Systematic sweep of AR order × ridge λ for two-stage model.
    
    Find optimal combination of ridge regularization and AR order
    for maximum prediction accuracy at 60min.
    """
    h_steps = 12  # 60min
    ar_orders = [1, 2, 3, 6]
    ridge_lambdas = [0.1, 1.0, 10.0, 100.0]
    
    grid_r2s = {}
    
    for lam in ridge_lambdas:
        for ar_p in ar_orders:
            key = f"λ={lam}_AR({ar_p})"
            r2s = []
            
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
                
                # Stage 1: Ridge
                ridge_pred_tr, w = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_tr, lam=lam)
                ridge_pred_val, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
                
                if w is None:
                    continue
                
                # Stage 2: AR on ridge residuals
                ridge_resid_tr = y_tr - ridge_pred_tr
                
                n_ar = split - ar_p
                X_ar = np.zeros((n_ar, ar_p + 1))
                y_ar = np.zeros(n_ar)
                
                for i in range(n_ar):
                    idx = i + ar_p
                    if not np.isfinite(ridge_resid_tr[idx]):
                        X_ar[i] = np.nan
                        y_ar[i] = np.nan
                        continue
                    all_ok = True
                    for j in range(ar_p):
                        if not np.isfinite(ridge_resid_tr[idx - j - 1]):
                            all_ok = False
                            break
                        X_ar[i, j] = ridge_resid_tr[idx - j - 1]
                    if not all_ok:
                        X_ar[i] = np.nan
                        y_ar[i] = np.nan
                        continue
                    X_ar[i, ar_p] = 1.0
                    y_ar[i] = ridge_resid_tr[idx]
                
                ar_valid = np.all(np.isfinite(X_ar), axis=1) & np.isfinite(y_ar)
                if ar_valid.sum() < ar_p + 10:
                    r2 = _r2(ridge_pred_val[valid_val], y_val[valid_val])
                    if np.isfinite(r2):
                        r2s.append(r2)
                    continue
                
                _, ar_w = _ridge_predict(X_ar[ar_valid], y_ar[ar_valid],
                                          np.zeros((1, ar_p + 1)), lam=0.01)
                
                if ar_w is None:
                    r2 = _r2(ridge_pred_val[valid_val], y_val[valid_val])
                    if np.isfinite(r2):
                        r2s.append(r2)
                    continue
                
                # Apply AR correction
                full_resid = np.concatenate([ridge_resid_tr,
                                            y_val - ridge_pred_val])
                corrected = np.copy(ridge_pred_val)
                
                for i in range(len(y_val)):
                    gi = split + i
                    x_i = np.zeros(ar_p + 1)
                    ok = True
                    for j in range(ar_p):
                        prev = gi - j - 1
                        if prev < 0 or not np.isfinite(full_resid[prev]):
                            ok = False
                            break
                        x_i[j] = full_resid[prev]
                    if not ok:
                        continue
                    x_i[ar_p] = 1.0
                    corrected[i] += x_i @ ar_w
                
                r2 = _r2(corrected[valid_val], y_val[valid_val])
                if np.isfinite(r2):
                    r2s.append(r2)
            
            if r2s:
                grid_r2s[key] = round(np.mean(r2s), 3)
    
    # Also get ridge-only baseline
    baseline_r2s = []
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
        r2 = _r2(pred[valid_val], y_val[valid_val])
        if np.isfinite(r2):
            baseline_r2s.append(r2)
    
    baseline = round(np.mean(baseline_r2s), 3) if baseline_r2s else 0
    best_config = max(grid_r2s, key=grid_r2s.get) if grid_r2s else 'none'
    best_r2 = grid_r2s.get(best_config, 0)
    
    results = {
        'grid': grid_r2s,
        'baseline_ridge': baseline,
        'best_config': best_config,
        'best_r2': best_r2,
        'improvement': round(best_r2 - baseline, 3),
    }
    
    return {
        'status': 'pass',
        'detail': (f"baseline={baseline}, best={best_config}(R²={best_r2}), "
                   f"Δ={results['improvement']:+.3f}. Grid: {grid_r2s}"),
        'results': results
    }


# ── CLI harness ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-811–820: Two-Stage Ridge+AR')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None,
                        help='Run only this experiment, e.g. EXP-811')
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
            detail = result.get('detail', '')
            print(f"  Status: {status} ({elapsed:.1f}s)")
            if detail:
                print(f"  Detail: {detail[:200]}")
            if status == 'pass':
                passed += 1
                summaries.append(f"  V {exp_id} {exp['name']}: {detail[:80]}")
            else:
                failed += 1
                summaries.append(f"  X {exp_id} {exp['name']}: {detail[:80]}")

            if args.save:
                fname = f"exp_{exp_id.split('-')[1]}_{exp['name'].lower().replace(' ', '_').replace('+', '-')}.json"
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
