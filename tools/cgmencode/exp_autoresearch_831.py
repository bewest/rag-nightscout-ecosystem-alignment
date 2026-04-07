#!/usr/bin/env python3
"""EXP-831–840: Nonlinear Models & the Beyond-Linear Frontier

With validated linear R²=0.534 at 60min (87% of linear oracle ceiling 0.613),
this wave explores nonlinear approaches to capture dynamics beyond linear
combinations. Uses simple nonlinear models implementable without deep learning
frameworks.

EXP-831: Kernel Ridge Regression (RBF kernel for nonlinear mapping)
EXP-832: Piecewise Linear Models (BG-range-specific linear models)
EXP-833: Recursive Multi-Step Prediction (chain short-horizon predictions)
EXP-834: BG-Regime Switching (detect and model regimes separately)
EXP-835: Nonlinear Supply-Demand Interaction (saturating insulin response)
EXP-836: Residual Boosting (iterative residual fitting)
EXP-837: Feature Binning + One-Hot (discretize continuous features)
EXP-838: Nearest-Neighbor Correction (similar historical patterns)
EXP-839: Physics-Informed Nonlinear Constraints (enforce BG bounds)
EXP-840: Best Nonlinear Combined Benchmark
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
    """Build the 16-feature enhanced set from EXP-830."""
    base = _build_features_base(fd, hours, n_pred, h_steps)
    usable = n_pred - start
    base = base[start:start + usable]
    
    extra = np.zeros((usable, 8))
    supply = fd['supply']
    for i in range(usable):
        orig = i + start
        if orig >= 1:
            extra[i, 0] = bg[orig] - bg[orig - 1]  # velocity
        if orig >= 2:
            extra[i, 1] = bg[orig] - 2 * bg[orig - 1] + bg[orig - 2]  # accel
        if orig >= 6:
            extra[i, 2] = bg[orig - 6]  # lag-6
        if orig >= 12:
            extra[i, 3] = bg[orig - 12]  # lag-12
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


# ── EXP-831: Kernel Ridge Regression ─────────────────────────────────────────

@register('EXP-831', 'Kernel Ridge Regression')
def exp_831(patients, detail=False):
    """Approximate kernel ridge regression using random Fourier features (RFF).
    
    RFF approximates the RBF kernel with random projections, enabling
    nonlinear prediction without O(n³) kernel matrix inversion.
    """
    h_steps = 12  # 60min
    n_rff_configs = [50, 100, 200]
    gamma_configs = [0.01, 0.1, 1.0]
    
    results = {}
    
    for n_rff in n_rff_configs:
        for gamma in gamma_configs:
            key = f"rff{n_rff}_g{gamma}"
            r2s = []
            
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
                
                # Standardize features
                feat_mean = np.nanmean(features, axis=0)
                feat_std = np.nanstd(features, axis=0)
                feat_std[feat_std < 1e-10] = 1.0
                features_norm = (features - feat_mean) / feat_std
                features_norm = np.nan_to_num(features_norm, 0)
                
                # Random Fourier Features
                rng = np.random.RandomState(42)
                W_rff = rng.normal(0, np.sqrt(2 * gamma), (features.shape[1], n_rff))
                b_rff = rng.uniform(0, 2 * np.pi, n_rff)
                
                Z = np.sqrt(2.0 / n_rff) * np.cos(features_norm @ W_rff + b_rff)
                # Add bias
                Z = np.hstack([Z, np.ones((Z.shape[0], 1))])
                
                split = int(0.8 * n_pred)
                Z_tr, Z_val = Z[:split], Z[split:]
                y_tr, y_val = actual[:split], actual[split:]
                
                valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(Z_tr), axis=1)
                valid_val = np.isfinite(y_val) & np.all(np.isfinite(Z_val), axis=1)
                
                pred, _ = _ridge_predict(Z_tr[valid_tr], y_tr[valid_tr], Z_val, lam=10.0)
                r2 = _r2(pred[valid_val], y_val[valid_val])
                if np.isfinite(r2):
                    r2s.append(r2)
            
            if r2s:
                results[key] = round(np.mean(r2s), 3)
    
    # Baseline
    base_r2s = []
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
        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2 = _r2(pred[valid_val], y_val[valid_val])
        if np.isfinite(r2):
            base_r2s.append(r2)
    
    baseline = round(np.mean(base_r2s), 3) if base_r2s else 0
    best_config = max(results, key=results.get) if results else 'none'
    
    return {
        'status': 'pass',
        'detail': f"baseline={baseline}, best={best_config}(R²={results.get(best_config,0)}), "
                  f"Δ={results.get(best_config,baseline)-baseline:+.3f}. Top configs: "
                  f"{dict(sorted(results.items(), key=lambda x:-x[1])[:5])}",
        'results': {'configs': results, 'baseline': baseline, 'best': best_config}
    }


# ── EXP-832: Piecewise Linear Models ────────────────────────────────────────

@register('EXP-832', 'Piecewise Linear Models')
def exp_832(patients, detail=False):
    """Train separate ridge models for different BG ranges.
    
    The prediction error analysis (EXP-825) showed that error varies
    dramatically by BG level. Separate models for each regime may help.
    """
    h_steps = 12  # 60min
    bg_regimes = [(0, 100), (100, 180), (180, 500)]
    
    global_r2s, piecewise_r2s = [], []
    
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
        curr_bg_tr = features[:split, 0]
        curr_bg_val = features[split:, 0]
        
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        
        # Global model
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])
        global_r2s.append(r2_global)
        
        # Piecewise model
        pred_pw = np.copy(pred_global)  # fallback
        for lo, hi in bg_regimes:
            tr_mask = valid_tr & (curr_bg_tr >= lo) & (curr_bg_tr < hi)
            val_mask = (curr_bg_val >= lo) & (curr_bg_val < hi)
            
            if tr_mask.sum() < 50 or val_mask.sum() < 10:
                continue
            
            pred_regime, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                             X_val[val_mask], lam=10.0)
            pred_pw[val_mask] = pred_regime
        
        r2_pw = _r2(pred_pw[valid_val], y_val[valid_val])
        piecewise_r2s.append(r2_pw)
    
    results = {
        'global': round(np.mean(global_r2s), 3),
        'piecewise': round(np.mean(piecewise_r2s), 3),
        'improvement': round(np.mean(piecewise_r2s) - np.mean(global_r2s), 3),
    }
    
    return {
        'status': 'pass',
        'detail': f"global={results['global']}, piecewise={results['piecewise']}, "
                  f"Δ={results['improvement']:+.3f}",
        'results': results
    }


# ── EXP-833: Recursive Multi-Step Prediction ────────────────────────────────

@register('EXP-833', 'Recursive Multi-Step')
def exp_833(patients, detail=False):
    """Chain 5min predictions recursively to reach 60min.
    
    Train a 1-step (5min) model, then iterate 12 times to reach 60min.
    Compare direct 60min prediction vs recursive approach.
    """
    results = {'per_patient': []}
    direct_r2s, recursive_r2s = [], []
    
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        
        # Build 1-step features (h_steps=1)
        n_pred_1 = nr - 1
        if n_pred_1 < 200:
            continue
        
        actual_1 = bg[2: 2 + n_pred_1]
        features_1 = _build_features_base(fd, hours, n_pred_1, 1)
        
        # Direct 60min features (h_steps=12)
        n_pred_12 = nr - 12
        actual_12 = bg[13: 13 + n_pred_12]
        features_12 = _build_features_base(fd, hours, n_pred_12, 12)
        
        split = int(0.8 * min(n_pred_1, n_pred_12))
        
        # Train 1-step model
        X_tr_1 = features_1[:split]
        y_tr_1 = actual_1[:split]
        valid_tr_1 = np.isfinite(y_tr_1) & np.all(np.isfinite(X_tr_1), axis=1)
        _, w_1 = _ridge_predict(X_tr_1[valid_tr_1], y_tr_1[valid_tr_1],
                                 X_tr_1[:1], lam=0.001)
        
        if w_1 is None:
            continue
        
        # Direct 60min model
        X_tr_12 = features_12[:split]
        y_tr_12 = actual_12[:split]
        X_val_12 = features_12[split:split + (n_pred_12 - split)]
        y_val_12 = actual_12[split:split + (n_pred_12 - split)]
        valid_tr_12 = np.isfinite(y_tr_12) & np.all(np.isfinite(X_tr_12), axis=1)
        valid_val_12 = np.isfinite(y_val_12) & np.all(np.isfinite(X_val_12), axis=1)
        
        pred_direct, _ = _ridge_predict(X_tr_12[valid_tr_12], y_tr_12[valid_tr_12],
                                         X_val_12, lam=10.0)
        r2_direct = _r2(pred_direct[valid_val_12], y_val_12[valid_val_12])
        
        # Recursive: iterate 1-step model 12 times
        n_val = min(len(y_val_12), n_pred_1 - split)
        pred_recursive = np.full(n_val, np.nan)
        
        for i in range(n_val):
            curr = bg[split + i]
            if not np.isfinite(curr):
                continue
            
            # Iterate 12 steps
            pred_bg = curr
            valid_iter = True
            for step in range(12):
                # Build feature vector for this step
                idx = split + i + step
                if idx >= n_pred_1:
                    valid_iter = False
                    break
                feat = features_1[idx].copy()
                feat[0] = pred_bg  # use predicted BG instead of actual
                pred_bg = feat @ w_1
                
                if not np.isfinite(pred_bg) or pred_bg < 20 or pred_bg > 600:
                    valid_iter = False
                    break
            
            if valid_iter:
                pred_recursive[i] = pred_bg
        
        valid_rec = np.isfinite(pred_recursive) & valid_val_12[:n_val]
        if valid_rec.sum() > 10:
            r2_rec = _r2(pred_recursive[valid_rec], y_val_12[:n_val][valid_rec])
        else:
            r2_rec = float('nan')
        
        if np.isfinite(r2_direct) and np.isfinite(r2_rec):
            direct_r2s.append(r2_direct)
            recursive_r2s.append(r2_rec)
            results['per_patient'].append({
                'patient': p['name'],
                'direct': round(r2_direct, 3),
                'recursive': round(r2_rec, 3),
            })
    
    results['summary'] = {
        'direct': round(np.mean(direct_r2s), 3) if direct_r2s else 0,
        'recursive': round(np.mean(recursive_r2s), 3) if recursive_r2s else 0,
        'difference': round(np.mean(recursive_r2s) - np.mean(direct_r2s), 3) if direct_r2s else 0,
    }
    
    s = results['summary']
    return {
        'status': 'pass',
        'detail': f"direct={s['direct']}, recursive={s['recursive']}, Δ={s['difference']:+.3f}",
        'results': results
    }


# ── EXP-834: BG-Regime Switching ────────────────────────────────────────────

@register('EXP-834', 'BG-Regime Switching')
def exp_834(patients, detail=False):
    """Detect BG regime (rising/falling/stable) and use regime-specific models.
    
    Unlike EXP-832 (BG level), this uses BG *dynamics* (velocity) to
    switch between models tuned for different metabolic states.
    """
    h_steps = 12
    velocity_thresholds = [(-999, -2), (-2, 2), (2, 999)]  # falling, stable, rising
    regime_names = ['falling', 'stable', 'rising']
    
    global_r2s, regime_r2s = [], []
    
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
        
        # Compute velocity
        velocity = np.zeros(n_pred)
        for i in range(1, n_pred):
            velocity[i] = bg[i] - bg[i - 1]
        
        split = int(0.8 * n_pred)
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        vel_tr, vel_val = velocity[:split], velocity[split:]
        
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        
        # Global
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])
        global_r2s.append(r2_global)
        
        # Regime-switching
        pred_regime = np.copy(pred_global)
        for (vlo, vhi), rname in zip(velocity_thresholds, regime_names):
            tr_mask = valid_tr & (vel_tr >= vlo) & (vel_tr < vhi)
            val_mask = (vel_val >= vlo) & (vel_val < vhi)
            
            if tr_mask.sum() < 50 or val_mask.sum() < 10:
                continue
            
            pred_r, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                        X_val[val_mask], lam=10.0)
            pred_regime[val_mask] = pred_r
        
        r2_regime = _r2(pred_regime[valid_val], y_val[valid_val])
        regime_r2s.append(r2_regime)
    
    results = {
        'global': round(np.mean(global_r2s), 3),
        'regime': round(np.mean(regime_r2s), 3),
        'improvement': round(np.mean(regime_r2s) - np.mean(global_r2s), 3),
    }
    
    return {
        'status': 'pass',
        'detail': f"global={results['global']}, regime={results['regime']}, "
                  f"Δ={results['improvement']:+.3f}",
        'results': results
    }


# ── EXP-835: Nonlinear Supply-Demand Interaction ────────────────────────────

@register('EXP-835', 'Nonlinear Supply-Demand')
def exp_835(patients, detail=False):
    """Model saturating insulin response: diminishing returns at high doses.
    
    Insulin sensitivity is known to be nonlinear — higher insulin doses
    have diminishing glucose-lowering effect. Model this with log/sqrt
    transformations of demand.
    """
    h_steps = 12
    results = {}
    base_r2s, nonlinear_r2s = [], []
    
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
        
        # Nonlinear features: log and sqrt of supply/demand (shifted to avoid log(0))
        nl_feats = np.zeros((n_pred, 6))
        for i in range(n_pred):
            s = features[i, 1]  # supply
            d = features[i, 2]  # demand
            nl_feats[i, 0] = np.log1p(max(s, 0))         # log supply
            nl_feats[i, 1] = np.sqrt(max(s, 0))          # sqrt supply
            nl_feats[i, 2] = np.log1p(max(d, 0))         # log demand
            nl_feats[i, 3] = np.sqrt(max(d, 0))          # sqrt demand
            # Saturating BG response: log(bg) captures diminishing sensitivity
            nl_feats[i, 4] = np.log(max(bg[i], 20))
            # Supply-demand balance ratio
            nl_feats[i, 5] = s / (d + 0.01) if d > 0 else s
        
        combined = np.hstack([features, nl_feats])
        
        split = int(0.8 * n_pred)
        y_tr, y_val = actual[:split], actual[split:]
        
        # Base
        X_tr, X_val = features[:split], features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        
        # Nonlinear
        X_tr_nl, X_val_nl = combined[:split], combined[split:]
        valid_tr_nl = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_nl), axis=1)
        valid_val_nl = np.isfinite(y_val) & np.all(np.isfinite(X_val_nl), axis=1)
        pred_nl, _ = _ridge_predict(X_tr_nl[valid_tr_nl], y_tr[valid_tr_nl],
                                     X_val_nl, lam=10.0)
        r2_nl = _r2(pred_nl[valid_val_nl], y_val[valid_val_nl])
        
        if np.isfinite(r2_base) and np.isfinite(r2_nl):
            base_r2s.append(r2_base)
            nonlinear_r2s.append(r2_nl)
    
    results = {
        'base': round(np.mean(base_r2s), 3),
        'nonlinear': round(np.mean(nonlinear_r2s), 3),
        'improvement': round(np.mean(nonlinear_r2s) - np.mean(base_r2s), 3),
    }
    
    return {
        'status': 'pass',
        'detail': f"base={results['base']}, nonlinear={results['nonlinear']}, "
                  f"Δ={results['improvement']:+.3f}",
        'results': results
    }


# ── EXP-836: Residual Boosting ──────────────────────────────────────────────

@register('EXP-836', 'Residual Boosting')
def exp_836(patients, detail=False):
    """Iteratively fit ridge models on residuals (gradient boosting analog).
    
    Stage 1: fit ridge on features → get residuals
    Stage 2: fit ridge on (features, residuals_squared, |residuals|) → correct
    Stage 3: repeat with stage-2 residuals
    """
    h_steps = 12
    n_stages = [1, 2, 3, 5]
    results = {}
    
    for n_boost in n_stages:
        r2s = []
        
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
            y_tr = actual[:split]
            y_val = actual[split:]
            
            valid_tr = np.isfinite(y_tr)
            valid_val = np.isfinite(y_val)
            
            # Boosting loop
            pred_tr_accum = np.zeros(split)
            pred_val_accum = np.zeros(len(y_val))
            current_target_tr = y_tr.copy()
            learning_rate = 0.5
            
            for stage in range(n_boost):
                X_tr = features[:split]
                X_val = features[split:]
                
                stage_valid = valid_tr & np.all(np.isfinite(X_tr), axis=1)
                if stage > 0:
                    # Add residual-based features from previous stage
                    prev_resid_tr = current_target_tr
                    resid_feats_tr = np.column_stack([
                        prev_resid_tr ** 2 / 1000.0,
                        np.abs(prev_resid_tr),
                    ])
                    prev_resid_val = y_val - pred_val_accum
                    resid_feats_val = np.column_stack([
                        prev_resid_val ** 2 / 1000.0,
                        np.abs(prev_resid_val),
                    ])
                    X_tr = np.hstack([X_tr, resid_feats_tr])
                    X_val = np.hstack([X_val, resid_feats_val])
                    stage_valid = valid_tr & np.all(np.isfinite(X_tr), axis=1)
                
                pred_stage_tr, w = _ridge_predict(
                    X_tr[stage_valid], current_target_tr[stage_valid],
                    X_tr, lam=10.0)
                if w is None:
                    break
                pred_stage_val = X_val @ w
                
                pred_tr_accum += learning_rate * pred_stage_tr
                pred_val_accum += learning_rate * pred_stage_val
                current_target_tr = y_tr - pred_tr_accum
            
            val_valid = valid_val & np.isfinite(pred_val_accum)
            r2 = _r2(pred_val_accum[val_valid], y_val[val_valid])
            if np.isfinite(r2):
                r2s.append(r2)
        
        if r2s:
            results[f"stages_{n_boost}"] = round(np.mean(r2s), 3)
    
    best = max(results, key=results.get) if results else 'none'
    
    return {
        'status': 'pass',
        'detail': f"results: {results}, best={best}",
        'results': results
    }


# ── EXP-837: Feature Binning ────────────────────────────────────────────────

@register('EXP-837', 'Feature Binning')
def exp_837(patients, detail=False):
    """Discretize BG into bins and use one-hot encoding.
    
    This captures nonlinear BG-dependent effects without explicit
    polynomial or kernel features.
    """
    h_steps = 12
    bg_bins = [0, 54, 70, 80, 100, 120, 140, 160, 180, 200, 250, 300, 500]
    n_bins = len(bg_bins) - 1
    
    base_r2s, binned_r2s = [], []
    
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
        
        # One-hot BG bins
        bg_onehot = np.zeros((n_pred, n_bins))
        for i in range(n_pred):
            for b in range(n_bins):
                if bg_bins[b] <= bg[i] < bg_bins[b + 1]:
                    bg_onehot[i, b] = 1.0
                    break
        
        combined = np.hstack([features, bg_onehot])
        
        split = int(0.8 * n_pred)
        y_tr, y_val = actual[:split], actual[split:]
        
        # Base
        X_tr, X_val = features[:split], features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        
        # Binned
        X_tr_b, X_val_b = combined[:split], combined[split:]
        valid_tr_b = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val_b = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        pred_bin, _ = _ridge_predict(X_tr_b[valid_tr_b], y_tr[valid_tr_b],
                                      X_val_b, lam=10.0)
        r2_bin = _r2(pred_bin[valid_val_b], y_val[valid_val_b])
        
        if np.isfinite(r2_base) and np.isfinite(r2_bin):
            base_r2s.append(r2_base)
            binned_r2s.append(r2_bin)
    
    results = {
        'base': round(np.mean(base_r2s), 3),
        'binned': round(np.mean(binned_r2s), 3),
        'improvement': round(np.mean(binned_r2s) - np.mean(base_r2s), 3),
        'n_bins': n_bins,
    }
    
    return {
        'status': 'pass',
        'detail': f"base={results['base']}, binned={results['binned']}, "
                  f"Δ={results['improvement']:+.3f} ({n_bins} bins)",
        'results': results
    }


# ── EXP-838: Nearest-Neighbor Correction ────────────────────────────────────

@register('EXP-838', 'Nearest-Neighbor Correction')
def exp_838(patients, detail=False):
    """Correct ridge predictions using K-nearest training examples.
    
    For each test point, find K nearest training points (in feature space),
    compute their average prediction error, and apply as correction.
    """
    h_steps = 12
    k_values = [5, 10, 20, 50]
    results = {}
    
    base_r2s = []
    knn_r2s = {k: [] for k in k_values}
    
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
        
        pred_tr, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_tr, lam=10.0)
        pred_val, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        
        r2_base = _r2(pred_val[valid_val], y_val[valid_val])
        base_r2s.append(r2_base)
        
        # Training errors
        tr_errors = y_tr - pred_tr
        
        # Normalize features for distance computation
        feat_std = np.nanstd(X_tr[valid_tr], axis=0)
        feat_std[feat_std < 1e-10] = 1.0
        X_tr_norm = X_tr / feat_std
        X_val_norm = X_val / feat_std
        
        # Subsample training for speed (KNN is O(n*m))
        valid_indices = np.where(valid_tr & np.isfinite(tr_errors))[0]
        if len(valid_indices) > 2000:
            rng = np.random.RandomState(42)
            valid_indices = rng.choice(valid_indices, 2000, replace=False)
        
        X_tr_sub = X_tr_norm[valid_indices]
        err_sub = tr_errors[valid_indices]
        
        for k in k_values:
            corrected = np.copy(pred_val)
            
            for i in range(len(y_val)):
                if not valid_val[i]:
                    continue
                # Compute distances to training subset
                diffs = X_tr_sub - X_val_norm[i]
                dists = np.sum(diffs ** 2, axis=1)
                
                # Find K nearest
                if len(dists) < k:
                    continue
                nn_idx = np.argpartition(dists, k)[:k]
                nn_errors = err_sub[nn_idx]
                valid_nn = np.isfinite(nn_errors)
                if valid_nn.sum() > 0:
                    correction = np.mean(nn_errors[valid_nn])
                    corrected[i] += 0.3 * correction  # dampened correction
            
            r2_knn = _r2(corrected[valid_val], y_val[valid_val])
            knn_r2s[k].append(r2_knn if np.isfinite(r2_knn) else r2_base)
    
    results = {
        'base': round(np.mean(base_r2s), 3),
        'knn': {str(k): round(np.mean(v), 3) for k, v in knn_r2s.items()},
    }
    best_k = max(knn_r2s, key=lambda k: np.mean(knn_r2s[k]))
    results['best_k'] = best_k
    results['best_r2'] = round(np.mean(knn_r2s[best_k]), 3)
    results['improvement'] = round(np.mean(knn_r2s[best_k]) - np.mean(base_r2s), 3)
    
    return {
        'status': 'pass',
        'detail': f"base={results['base']}, best_k={best_k}(R²={results['best_r2']}), "
                  f"Δ={results['improvement']:+.3f}",
        'results': results
    }


# ── EXP-839: Physics-Informed Constraints ───────────────────────────────────

@register('EXP-839', 'Physics-Informed Constraints')
def exp_839(patients, detail=False):
    """Apply physics-informed post-processing to ridge predictions.
    
    1. Clip predictions to physiological range [39, 400] mg/dL
    2. Limit rate of change to ±4 mg/dL/min (±20 per 5min step)
    3. Apply mean-reversion toward 120 mg/dL for extreme predictions
    """
    h_steps = 12
    results = {'per_patient': []}
    raw_r2s, constrained_r2s = [], []
    
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
        
        pred_raw, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=10.0)
        r2_raw = _r2(pred_raw[valid_val], y_val[valid_val])
        
        # Apply physics constraints
        pred_const = np.copy(pred_raw)
        
        # 1. Physiological range clipping
        pred_const = np.clip(pred_const, 39, 400)
        
        # 2. Rate-of-change limiting (relative to current BG)
        curr_bg_val = features[split:, 0]
        max_change = 20.0 * h_steps  # max ±20 mg/dL per 5min step × h_steps
        for i in range(len(pred_const)):
            if np.isfinite(curr_bg_val[i]):
                delta = pred_const[i] - curr_bg_val[i]
                if abs(delta) > max_change:
                    pred_const[i] = curr_bg_val[i] + np.sign(delta) * max_change
        
        # 3. Mean reversion for extreme predictions
        for i in range(len(pred_const)):
            if pred_const[i] > 300:
                # Pull toward 200 (mean reversion strength increases with extremity)
                excess = pred_const[i] - 300
                pred_const[i] -= 0.3 * excess
            elif pred_const[i] < 60:
                deficit = 60 - pred_const[i]
                pred_const[i] += 0.3 * deficit
        
        r2_const = _r2(pred_const[valid_val], y_val[valid_val])
        
        if np.isfinite(r2_raw) and np.isfinite(r2_const):
            raw_r2s.append(r2_raw)
            constrained_r2s.append(r2_const)
            results['per_patient'].append({
                'patient': p['name'],
                'raw': round(r2_raw, 3),
                'constrained': round(r2_const, 3),
            })
    
    results['summary'] = {
        'raw': round(np.mean(raw_r2s), 3),
        'constrained': round(np.mean(constrained_r2s), 3),
        'improvement': round(np.mean(constrained_r2s) - np.mean(raw_r2s), 3),
    }
    
    s = results['summary']
    return {
        'status': 'pass',
        'detail': f"raw={s['raw']}, constrained={s['constrained']}, Δ={s['improvement']:+.3f}",
        'results': results
    }


# ── EXP-840: Best Nonlinear Combined Benchmark ─────────────────────────────

@register('EXP-840', 'Best Nonlinear Benchmark')
def exp_840(patients, detail=False):
    """Combine best nonlinear approaches from 831-839 with enhanced features.
    
    Uses: enhanced features (EXP-830) + nonlinear supply-demand (EXP-835)
    + feature binning (EXP-837) + physics constraints (EXP-839).
    """
    h_steps = 12
    start = 24
    bg_bins = [0, 70, 100, 140, 180, 250, 500]
    n_bins = len(bg_bins) - 1
    
    base_r2s, enhanced_r2s, nonlinear_r2s = [], [], []
    
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
        
        # Base features
        base_feats = _build_features_base(fd, hours, n_pred, h_steps)
        base_feats = base_feats[start:start + usable]
        
        # Enhanced features (from EXP-830)
        enhanced_feats, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        
        # Nonlinear additions
        nl_feats = np.zeros((usable, n_bins + 4))
        for i in range(usable):
            orig = i + start
            s = base_feats[i, 1]
            d = base_feats[i, 2]
            nl_feats[i, 0] = np.log1p(max(s, 0))
            nl_feats[i, 1] = np.sqrt(max(d, 0))
            nl_feats[i, 2] = np.log(max(bg[orig], 20))
            nl_feats[i, 3] = s / (d + 0.01) if d > 0 else s
            # BG bins
            for b in range(n_bins):
                if bg_bins[b] <= bg[orig] < bg_bins[b + 1]:
                    nl_feats[i, 4 + b] = 1.0
                    break
        
        combined = np.hstack([enhanced_feats, nl_feats])
        
        split = int(0.8 * usable)
        y_tr, y_val = actual[:split], actual[split:]
        
        lam = 10.0
        
        # Base 8-feature
        X_tr, X_val = base_feats[:split], base_feats[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        
        # Enhanced 16-feature
        X_tr_e, X_val_e = enhanced_feats[:split], enhanced_feats[split:]
        valid_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
        valid_val_e = np.isfinite(y_val) & np.all(np.isfinite(X_val_e), axis=1)
        pred_enh, _ = _ridge_predict(X_tr_e[valid_tr_e], y_tr[valid_tr_e],
                                      X_val_e, lam=lam * 3)
        r2_enh = _r2(pred_enh[valid_val_e], y_val[valid_val_e])
        
        # Full nonlinear combined
        X_tr_nl, X_val_nl = combined[:split], combined[split:]
        valid_tr_nl = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_nl), axis=1)
        valid_val_nl = np.isfinite(y_val) & np.all(np.isfinite(X_val_nl), axis=1)
        pred_nl, _ = _ridge_predict(X_tr_nl[valid_tr_nl], y_tr[valid_tr_nl],
                                     X_val_nl, lam=lam * 5)
        
        # Apply physics constraints
        pred_nl_c = np.clip(pred_nl, 39, 400)
        curr_bg = base_feats[split:, 0]
        max_change = 20.0 * h_steps
        for i in range(len(pred_nl_c)):
            if np.isfinite(curr_bg[i]):
                delta = pred_nl_c[i] - curr_bg[i]
                if abs(delta) > max_change:
                    pred_nl_c[i] = curr_bg[i] + np.sign(delta) * max_change
        
        r2_nl = _r2(pred_nl_c[valid_val_nl], y_val[valid_val_nl])
        
        if np.isfinite(r2_base) and np.isfinite(r2_enh) and np.isfinite(r2_nl):
            base_r2s.append(r2_base)
            enhanced_r2s.append(r2_enh)
            nonlinear_r2s.append(r2_nl)
    
    results = {
        'base_8feat': round(np.mean(base_r2s), 3),
        'enhanced_16feat': round(np.mean(enhanced_r2s), 3),
        'nonlinear_combined': round(np.mean(nonlinear_r2s), 3),
        'improvement_over_base': round(np.mean(nonlinear_r2s) - np.mean(base_r2s), 3),
        'improvement_over_enhanced': round(np.mean(nonlinear_r2s) - np.mean(enhanced_r2s), 3),
    }
    
    return {
        'status': 'pass',
        'detail': (f"base={results['base_8feat']}, enhanced={results['enhanced_16feat']}, "
                   f"nonlinear={results['nonlinear_combined']}, "
                   f"Δbase={results['improvement_over_base']:+.3f}, "
                   f"Δenh={results['improvement_over_enhanced']:+.3f}"),
        'results': results
    }


# ── CLI harness ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-831–840: Nonlinear Models')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    results_dir = Path(__file__).parent.parent.parent / "externals" / "experiments"
    results_dir.mkdir(parents=True, exist_ok=True)

    passed, failed, total = 0, 0, 0
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
            det = result.get('detail', '')
            print(f"  Status: {status} ({elapsed:.1f}s)")
            if det:
                print(f"  Detail: {det[:250]}")
            if status == 'pass':
                passed += 1
                summaries.append(f"  V {exp_id} {exp['name']}: {det[:80]}")
            else:
                failed += 1
                summaries.append(f"  X {exp_id} {exp['name']}: {det[:80]}")

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
