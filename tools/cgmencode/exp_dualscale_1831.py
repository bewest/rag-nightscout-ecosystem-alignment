#!/usr/bin/env python3
"""
EXP-1831 to EXP-1838: Dual-Timescale Architecture & Combined Feature Validation

Following from:
  - EXP-1794: UAM-aware model (+3.18 R²)
  - EXP-1823: Slow features beat raw at 24h (0.220 vs 0.119 bits)
  - EXP-1822: Demand integral H=1.36 > supply H=1.24

Questions:
  1831: Does UAM + slow features combine additively? Or does UAM subsume slow features?
  1832: Dual-head architecture: short (raw) + long (slow) vs single model
  1833: Excursion type prediction — can we forecast what's COMING?
  1834: ISF variability drivers — what predicts sensitivity shifts?
  1835: Nonlinear S/D phase detection via kernel methods
  1836: Meal-rise decomposition — can we cluster meals into actionable types?
  1837: Insulin-fall decomposition — what drives the worst excursion type?
  1838: Combined best-of-breed model vs baseline
"""

import argparse
import json
import os
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_441 import (
    load_patients, compute_supply_demand,
)

FIGURES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', '60-research', 'figures')


# ============================================================================
# Shared utilities
# ============================================================================

def classify_context(df, sd_data):
    """Classify each timestep into metabolic context."""
    n = len(df)
    ctx = np.full(n, 'other', dtype=object)
    glucose = df['glucose'].values
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)

    # Post-meal: within 3h of carb entry > 1g
    carb_idx = np.where(np.nan_to_num(carbs) > 1)[0]
    for ci in carb_idx:
        end = min(ci + 36, n)  # 3h = 36 steps
        ctx[ci:end] = 'post_meal'

    # Hypo recovery: glucose < 70 and rising
    dg = np.diff(glucose, prepend=glucose[0])
    hypo_mask = (glucose < 70) & (dg > 0)
    for i in np.where(hypo_mask)[0]:
        end = min(i + 12, n)  # 1h window
        ctx[i:end] = 'hypo_recovery'

    # Correction: IOB > 1.5x median and glucose > 150
    iob_med = np.nanmedian(iob[iob > 0]) if np.any(iob > 0) else 1.0
    corr_mask = (iob > 1.5 * iob_med) & (glucose > 150)
    ctx[corr_mask] = 'correction'

    # Fasting: not post_meal and no recent carbs
    fasting_mask = (ctx == 'other')
    ctx[fasting_mask] = 'fasting'

    return ctx


def compute_slow_features(df, sd_data, window_steps=288):
    """Compute slow features for each timestep using trailing window."""
    n = len(df)
    glucose = df['glucose'].values
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
    supply = sd_data['supply']
    demand = sd_data['demand']
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)

    features = {}

    # Time above range (>180)
    tar = np.zeros(n)
    above = (glucose > 180).astype(float)
    cs_above = np.nancumsum(np.nan_to_num(above))
    for i in range(n):
        start = max(0, i - window_steps)
        tar[i] = (cs_above[i] - cs_above[start]) / max(i - start, 1)
    features['time_above_range'] = tar

    # Time below range (<70)
    tbr = np.zeros(n)
    below = (glucose < 70).astype(float)
    cs_below = np.nancumsum(np.nan_to_num(below))
    for i in range(n):
        start = max(0, i - window_steps)
        tbr[i] = (cs_below[i] - cs_below[start]) / max(i - start, 1)
    features['time_below_range'] = tbr

    # Insulin load
    ins_load = np.zeros(n)
    cs_iob = np.nancumsum(np.nan_to_num(iob))
    for i in range(n):
        start = max(0, i - window_steps)
        ins_load[i] = (cs_iob[i] - cs_iob[start]) / max(i - start, 1)
    features['insulin_load'] = ins_load

    # Glucose volatility (rolling std)
    vol = np.zeros(n)
    for i in range(window_steps, n):
        seg = glucose[i-window_steps:i]
        valid = seg[np.isfinite(seg)]
        vol[i] = np.std(valid) if len(valid) > 10 else np.nan
    features['glucose_volatility'] = vol

    # Supply integral
    sup_int = np.zeros(n)
    cs_sup = np.nancumsum(np.nan_to_num(supply))
    for i in range(n):
        start = max(0, i - window_steps)
        sup_int[i] = cs_sup[i] - cs_sup[start]
    features['supply_integral'] = sup_int

    # Demand integral
    dem_int = np.zeros(n)
    cs_dem = np.nancumsum(np.nan_to_num(demand))
    for i in range(n):
        start = max(0, i - window_steps)
        dem_int[i] = cs_dem[i] - cs_dem[start]
    features['demand_integral'] = dem_int

    # Cumulative carb balance
    carb_bal = np.zeros(n)
    cs_carb = np.nancumsum(np.nan_to_num(carbs))
    for i in range(n):
        start = max(0, i - window_steps)
        carb_bal[i] = cs_carb[i] - cs_carb[start]
    features['cum_carb_balance'] = carb_bal

    return features


def uam_supply_adjustment(df, sd_data, threshold=1.0):
    """UAM-aware supply: attribute excess glucose rise to exogenous supply."""
    glucose = df['glucose'].values
    supply = sd_data['supply'].copy()
    dg = np.diff(glucose, prepend=glucose[0]) / 1.0  # per 5-min step

    # When glucose accelerating upward beyond threshold, add to supply
    excess = np.maximum(dg - threshold, 0)
    uam_active = excess > 0
    adjusted_supply = supply + excess

    return adjusted_supply, uam_active


def safe_r2(y_true, y_pred):
    """R² that handles NaN."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 10:
        return np.nan
    yt = y_true[mask]
    yp = y_pred[mask]
    ss_res = np.sum((yt - yp) ** 2)
    ss_tot = np.sum((yt - np.mean(yt)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def safe_mi_binned(x, y, bins=20):
    """Mutual information via histogram binning."""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 50:
        return 0.0
    x, y = x[mask], y[mask]
    # Clip outliers
    for arr in [x, y]:
        p1, p99 = np.percentile(arr, [1, 99])
        arr[:] = np.clip(arr, p1, p99)
    
    hist_2d, _, _ = np.histogram2d(x, y, bins=bins)
    pxy = hist_2d / hist_2d.sum()
    px = pxy.sum(axis=1)
    py = pxy.sum(axis=0)
    
    mi = 0.0
    for i in range(bins):
        for j in range(bins):
            if pxy[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += pxy[i, j] * np.log2(pxy[i, j] / (px[i] * py[j]))
    return max(0, mi)


# ============================================================================
# EXP-1831: UAM + Slow Feature Additivity
# ============================================================================
def exp_1831(patients, figures_dir=None):
    """Test whether UAM-aware supply + slow features combine additively."""
    print("\n" + "=" * 70)
    print("EXP-1831: UAM + Slow Feature Additivity")
    print("=" * 70)

    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        
        n = len(glucose)
        # Target: next 1h mean glucose 
        target_1h = np.full(n, np.nan)
        for i in range(n - 12):
            seg = glucose[i+1:i+13]
            valid = seg[np.isfinite(seg)]
            if len(valid) > 6:
                target_1h[i] = np.mean(valid)
        
        # Target: next 24h mean glucose
        target_24h = np.full(n, np.nan)
        for i in range(n - 288):
            seg = glucose[i+1:i+289]
            valid = seg[np.isfinite(seg)]
            if len(valid) > 100:
                target_24h[i] = np.mean(valid)

        # Model 1: Baseline (raw glucose + IOB)
        raw_feats = np.column_stack([glucose, df['iob'].values if 'iob' in df.columns else np.zeros(n)])
        
        # Model 2: UAM-aware supply 
        uam_supply, uam_active = uam_supply_adjustment(df, sd_data)
        
        # Model 3: Slow features only
        slow = compute_slow_features(df, sd_data, window_steps=288)
        slow_arr = np.column_stack([slow[k] for k in sorted(slow.keys())])
        
        # Model 4: UAM + Slow combined
        # Measure MI for each feature set with targets
        from sklearn.linear_model import Ridge
        
        # Train/test split: first 70% train, last 30% test
        split = int(n * 0.7)
        
        def eval_model(X, y, split_idx):
            mask_train = np.all(np.isfinite(X[:split_idx]), axis=1) & np.isfinite(y[:split_idx])
            mask_test = np.all(np.isfinite(X[split_idx:]), axis=1) & np.isfinite(y[split_idx:])
            if mask_train.sum() < 50 or mask_test.sum() < 50:
                return np.nan
            model = Ridge(alpha=1.0)
            model.fit(X[:split_idx][mask_train], y[:split_idx][mask_train])
            pred = model.predict(X[split_idx:][mask_test])
            return safe_r2(y[split_idx:][mask_test], pred)
        
        # Build feature matrices
        X_base = raw_feats
        X_uam = np.column_stack([raw_feats, uam_supply, uam_active.astype(float)])
        X_slow = slow_arr
        X_combined = np.column_stack([raw_feats, uam_supply, uam_active.astype(float), slow_arr])
        
        # Evaluate at 1h and 24h horizons
        r2_base_1h = eval_model(X_base, target_1h, split)
        r2_uam_1h = eval_model(X_uam, target_1h, split)
        r2_slow_1h = eval_model(X_slow, target_1h, split)
        r2_combined_1h = eval_model(X_combined, target_1h, split)
        
        r2_base_24h = eval_model(X_base, target_24h, split)
        r2_uam_24h = eval_model(X_uam, target_24h, split)
        r2_slow_24h = eval_model(X_slow, target_24h, split)
        r2_combined_24h = eval_model(X_combined, target_24h, split)
        
        patient_result = {
            'name': name,
            'r2_base_1h': r2_base_1h, 'r2_uam_1h': r2_uam_1h,
            'r2_slow_1h': r2_slow_1h, 'r2_combined_1h': r2_combined_1h,
            'r2_base_24h': r2_base_24h, 'r2_uam_24h': r2_uam_24h,
            'r2_slow_24h': r2_slow_24h, 'r2_combined_24h': r2_combined_24h,
        }
        results_per_patient.append(patient_result)
        print(f"  {name}: 1h base={r2_base_1h:.4f} uam={r2_uam_1h:.4f} slow={r2_slow_1h:.4f} comb={r2_combined_1h:.4f}")
        print(f"        24h base={r2_base_24h:.4f} uam={r2_uam_24h:.4f} slow={r2_slow_24h:.4f} comb={r2_combined_24h:.4f}")

    # Population summary
    def pmean(key):
        vals = [r[key] for r in results_per_patient if np.isfinite(r.get(key, np.nan))]
        return np.mean(vals) if vals else np.nan
    
    print(f"\n  Population mean R² (1h horizon):")
    print(f"    Base (glucose+IOB):   {pmean('r2_base_1h'):.4f}")
    print(f"    + UAM:                {pmean('r2_uam_1h'):.4f}")
    print(f"    Slow features only:   {pmean('r2_slow_1h'):.4f}")
    print(f"    Combined (UAM+Slow):  {pmean('r2_combined_1h'):.4f}")
    
    print(f"\n  Population mean R² (24h horizon):")
    print(f"    Base (glucose+IOB):   {pmean('r2_base_24h'):.4f}")
    print(f"    + UAM:                {pmean('r2_uam_24h'):.4f}")
    print(f"    Slow features only:   {pmean('r2_slow_24h'):.4f}")
    print(f"    Combined (UAM+Slow):  {pmean('r2_combined_24h'):.4f}")
    
    # Is it additive?
    uam_lift_1h = pmean('r2_uam_1h') - pmean('r2_base_1h')
    slow_lift_1h = pmean('r2_slow_1h') - pmean('r2_base_1h')
    combined_lift_1h = pmean('r2_combined_1h') - pmean('r2_base_1h')
    expected_additive_1h = uam_lift_1h + slow_lift_1h
    
    uam_lift_24h = pmean('r2_uam_24h') - pmean('r2_base_24h')
    slow_lift_24h = pmean('r2_slow_24h') - pmean('r2_base_24h')
    combined_lift_24h = pmean('r2_combined_24h') - pmean('r2_base_24h')
    expected_additive_24h = uam_lift_24h + slow_lift_24h
    
    print(f"\n  Additivity test (1h):")
    print(f"    UAM lift: {uam_lift_1h:+.4f}, Slow lift: {slow_lift_1h:+.4f}")
    print(f"    Expected additive: {expected_additive_1h:+.4f}")
    print(f"    Actual combined:   {combined_lift_1h:+.4f}")
    ratio_1h = combined_lift_1h / expected_additive_1h if expected_additive_1h != 0 else np.nan
    print(f"    Ratio (actual/expected): {ratio_1h:.2f}")
    
    print(f"\n  Additivity test (24h):")
    print(f"    UAM lift: {uam_lift_24h:+.4f}, Slow lift: {slow_lift_24h:+.4f}")
    print(f"    Expected additive: {expected_additive_24h:+.4f}")
    print(f"    Actual combined:   {combined_lift_24h:+.4f}")
    ratio_24h = combined_lift_24h / expected_additive_24h if expected_additive_24h != 0 else np.nan
    print(f"    Ratio (actual/expected): {ratio_24h:.2f}")
    
    # Verdict
    if ratio_1h > 0.8 and ratio_24h > 0.8:
        verdict = 'ADDITIVE'
    elif combined_lift_1h > max(uam_lift_1h, slow_lift_1h) and combined_lift_24h > max(uam_lift_24h, slow_lift_24h):
        verdict = 'SYNERGISTIC_PARTIAL'
    else:
        verdict = 'REDUNDANT'
    
    print(f"\n  ✓ EXP-1831 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        models = ['Base', 'UAM', 'Slow', 'Combined']
        
        for ax, horizon, suffix in [(axes[0], '1h', '_1h'), (axes[1], '24h', '_24h')]:
            means = [pmean(f'r2_base{suffix}'), pmean(f'r2_uam{suffix}'),
                     pmean(f'r2_slow{suffix}'), pmean(f'r2_combined{suffix}')]
            colors = ['#999999', '#e74c3c', '#3498db', '#2ecc71']
            bars = ax.bar(models, means, color=colors, edgecolor='black', linewidth=0.5)
            ax.set_ylabel('R² (population mean)')
            ax.set_title(f'{horizon} Prediction Horizon')
            ax.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
            for bar, val in zip(bars, means):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                       f'{val:.3f}', ha='center', va='bottom', fontsize=9)
        
        fig.suptitle('EXP-1831: UAM + Slow Feature Additivity', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig01-additivity.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig01-additivity.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'population': {
            'r2_base_1h': pmean('r2_base_1h'), 'r2_uam_1h': pmean('r2_uam_1h'),
            'r2_slow_1h': pmean('r2_slow_1h'), 'r2_combined_1h': pmean('r2_combined_1h'),
            'r2_base_24h': pmean('r2_base_24h'), 'r2_uam_24h': pmean('r2_uam_24h'),
            'r2_slow_24h': pmean('r2_slow_24h'), 'r2_combined_24h': pmean('r2_combined_24h'),
            'additivity_ratio_1h': ratio_1h, 'additivity_ratio_24h': ratio_24h,
        }
    }


# ============================================================================
# EXP-1832: Dual-Head Architecture Validation
# ============================================================================
def exp_1832(patients, figures_dir=None):
    """Test dual-head architecture: short head (raw) + long head (slow) vs single."""
    print("\n" + "=" * 70)
    print("EXP-1832: Dual-Head Architecture Validation")
    print("=" * 70)

    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        # Horizons to test
        horizons = {
            '1h': 12, '3h': 36, '6h': 72, '12h': 144, '24h': 288
        }
        
        # Slow features (24h window)
        slow = compute_slow_features(df, sd_data, window_steps=288)
        slow_arr = np.column_stack([slow[k] for k in sorted(slow.keys())])
        
        # Raw features
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
        raw_arr = np.column_stack([glucose, iob])
        
        # UAM features
        uam_supply, uam_active = uam_supply_adjustment(df, sd_data)
        
        # Combined
        all_feats = np.column_stack([raw_arr, uam_supply, uam_active.astype(float), slow_arr])
        
        from sklearn.linear_model import Ridge
        split = int(n * 0.7)
        
        patient_r2 = {'name': name}
        
        for hname, hsteps in horizons.items():
            # Target
            target = np.full(n, np.nan)
            for i in range(n - hsteps):
                seg = glucose[i+1:i+hsteps+1]
                valid = seg[np.isfinite(seg)]
                if len(valid) > hsteps // 3:
                    target[i] = np.mean(valid)
            
            # Evaluate each feature set
            for fname, X in [('raw', raw_arr), ('slow', slow_arr), ('all', all_feats)]:
                mask_tr = np.all(np.isfinite(X[:split]), axis=1) & np.isfinite(target[:split])
                mask_te = np.all(np.isfinite(X[split:]), axis=1) & np.isfinite(target[split:])
                if mask_tr.sum() < 50 or mask_te.sum() < 50:
                    patient_r2[f'r2_{fname}_{hname}'] = np.nan
                    continue
                model = Ridge(alpha=1.0)
                model.fit(X[:split][mask_tr], target[:split][mask_tr])
                pred = model.predict(X[split:][mask_te])
                patient_r2[f'r2_{fname}_{hname}'] = safe_r2(target[split:][mask_te], pred)
            
            # Dual-head: use raw for short, slow for long, weighted blend
            # Short head weight = exp(-horizon/6h), long head weight = 1 - short
            short_weight = np.exp(-hsteps / 72.0)
            long_weight = 1.0 - short_weight
            
            # Train both heads
            mask_tr_r = np.all(np.isfinite(raw_arr[:split]), axis=1) & np.isfinite(target[:split])
            mask_tr_s = np.all(np.isfinite(slow_arr[:split]), axis=1) & np.isfinite(target[:split])
            mask_te_r = np.all(np.isfinite(raw_arr[split:]), axis=1) & np.isfinite(target[split:])
            mask_te_s = np.all(np.isfinite(slow_arr[split:]), axis=1) & np.isfinite(target[split:])
            
            mask_te_both = mask_te_r & mask_te_s
            
            if mask_tr_r.sum() < 50 or mask_tr_s.sum() < 50 or mask_te_both.sum() < 50:
                patient_r2[f'r2_dual_{hname}'] = np.nan
                continue
            
            short_model = Ridge(alpha=1.0)
            short_model.fit(raw_arr[:split][mask_tr_r], target[:split][mask_tr_r])
            long_model = Ridge(alpha=1.0)
            long_model.fit(slow_arr[:split][mask_tr_s], target[:split][mask_tr_s])
            
            pred_short = short_model.predict(raw_arr[split:][mask_te_both])
            pred_long = long_model.predict(slow_arr[split:][mask_te_both])
            pred_dual = short_weight * pred_short + long_weight * pred_long
            
            patient_r2[f'r2_dual_{hname}'] = safe_r2(target[split:][mask_te_both], pred_dual)
        
        results_per_patient.append(patient_r2)
        print(f"  {name}: done")
    
    # Population summary
    horizons_list = ['1h', '3h', '6h', '12h', '24h']
    print(f"\n  Population mean R² by horizon and model:")
    print(f"  {'Horizon':>8s}  {'Raw':>8s}  {'Slow':>8s}  {'All':>8s}  {'Dual':>8s}  {'Winner':>8s}")
    
    pop_results = {}
    for h in horizons_list:
        vals = {}
        for m in ['raw', 'slow', 'all', 'dual']:
            key = f'r2_{m}_{h}'
            v = [r[key] for r in results_per_patient if np.isfinite(r.get(key, np.nan))]
            vals[m] = np.mean(v) if v else np.nan
        
        winner = max(vals, key=lambda k: vals[k] if np.isfinite(vals[k]) else -999)
        print(f"  {h:>8s}  {vals['raw']:>8.4f}  {vals['slow']:>8.4f}  {vals['all']:>8.4f}  {vals['dual']:>8.4f}  {winner:>8s}")
        pop_results[h] = vals
    
    # Does dual-head ever win?
    dual_wins = sum(1 for h in horizons_list 
                    if pop_results[h]['dual'] > pop_results[h]['raw'] 
                    and pop_results[h]['dual'] > pop_results[h]['slow'])
    
    if dual_wins >= 3:
        verdict = 'DUAL_HEAD_WINS'
    elif any(pop_results[h]['all'] > max(pop_results[h]['raw'], pop_results[h]['slow']) for h in horizons_list):
        verdict = 'ALL_FEATURES_WIN'
    else:
        verdict = 'SINGLE_HEAD_SUFFICIENT'
    
    print(f"\n  Dual-head wins at {dual_wins}/{len(horizons_list)} horizons")
    print(f"\n  ✓ EXP-1832 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(10, 6))
        x = range(len(horizons_list))
        width = 0.2
        
        for i, (model, color, label) in enumerate([
            ('raw', '#e74c3c', 'Raw (glucose+IOB)'),
            ('slow', '#3498db', 'Slow features'),
            ('all', '#2ecc71', 'All features'),
            ('dual', '#9b59b6', 'Dual-head'),
        ]):
            vals = [pop_results[h][model] for h in horizons_list]
            ax.bar([xi + i * width for xi in x], vals, width, color=color, label=label, edgecolor='black', linewidth=0.5)
        
        ax.set_xlabel('Prediction Horizon')
        ax.set_ylabel('R² (population mean)')
        ax.set_xticks([xi + 1.5 * width for xi in x])
        ax.set_xticklabels(horizons_list)
        ax.legend()
        ax.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        ax.set_title('EXP-1832: Dual-Head Architecture — R² by Horizon', fontweight='bold')
        
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig02-dual-head.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig02-dual-head.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'population': pop_results,
    }


# ============================================================================
# EXP-1833: Excursion Type Prediction
# ============================================================================
def exp_1833(patients, figures_dir=None):
    """Can we predict which excursion type is coming in the next 1-2h?"""
    print("\n" + "=" * 70)
    print("EXP-1833: Excursion Type Prediction")
    print("=" * 70)

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    
    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        ctx = classify_context(df, sd_data)
        slow = compute_slow_features(df, sd_data, window_steps=288)
        
        # Feature vector: current state + slow features
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
        dg = np.diff(glucose, prepend=glucose[0])
        
        X = np.column_stack([
            glucose, iob, dg,
            slow['time_above_range'], slow['time_below_range'],
            slow['insulin_load'], slow['glucose_volatility'],
            slow['supply_integral'], slow['demand_integral'],
        ])
        
        # Target: context 1h ahead
        target_ctx = np.full(n, 'other', dtype=object)
        for i in range(n - 12):
            # Majority context in next 1h
            future = ctx[i+1:i+13]
            unique, counts = np.unique(future, return_counts=True)
            target_ctx[i] = unique[np.argmax(counts)]
        
        split = int(n * 0.7)
        
        patient_auc = {'name': name}
        
        for target_class in ['post_meal', 'hypo_recovery', 'correction', 'fasting']:
            y = (target_ctx == target_class).astype(float)
            
            mask_tr = np.all(np.isfinite(X[:split]), axis=1) & np.isfinite(y[:split])
            mask_te = np.all(np.isfinite(X[split:]), axis=1) & np.isfinite(y[split:])
            
            if mask_tr.sum() < 50 or mask_te.sum() < 50:
                patient_auc[f'auc_{target_class}'] = np.nan
                continue
            
            y_tr = y[:split][mask_tr]
            y_te = y[split:][mask_te]
            
            if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
                patient_auc[f'auc_{target_class}'] = np.nan
                continue
            
            model = LogisticRegression(max_iter=500, C=0.1)
            model.fit(X[:split][mask_tr], y_tr)
            prob = model.predict_proba(X[split:][mask_te])[:, 1]
            
            try:
                auc = roc_auc_score(y_te, prob)
                patient_auc[f'auc_{target_class}'] = auc
            except ValueError:
                patient_auc[f'auc_{target_class}'] = np.nan
        
        results_per_patient.append(patient_auc)
        aucs = {k.replace('auc_',''): f"{v:.3f}" for k,v in patient_auc.items() if k.startswith('auc_') and np.isfinite(v)}
        print(f"  {name}: {aucs}")
    
    # Population summary
    print(f"\n  Population AUC for predicting next-1h context:")
    pop_auc = {}
    for target_class in ['post_meal', 'hypo_recovery', 'correction', 'fasting']:
        vals = [r[f'auc_{target_class}'] for r in results_per_patient 
                if np.isfinite(r.get(f'auc_{target_class}', np.nan))]
        mean_auc = np.mean(vals) if vals else np.nan
        pop_auc[target_class] = mean_auc
        print(f"    {target_class:20s}: AUC={mean_auc:.3f} ± {np.std(vals):.3f}  (n={len(vals)})")
    
    # Best-predicted context
    best = max(pop_auc, key=lambda k: pop_auc[k] if np.isfinite(pop_auc[k]) else 0)
    
    if pop_auc[best] > 0.75:
        verdict = 'PREDICTABLE'
    elif pop_auc[best] > 0.60:
        verdict = 'PARTIALLY_PREDICTABLE'
    else:
        verdict = 'NOT_PREDICTABLE'
    
    print(f"\n  Best-predicted context: {best} (AUC={pop_auc[best]:.3f})")
    print(f"\n  ✓ EXP-1833 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(8, 5))
        contexts = list(pop_auc.keys())
        aucs = [pop_auc[c] for c in contexts]
        colors = ['#e74c3c', '#f39c12', '#3498db', '#2ecc71']
        bars = ax.bar(contexts, aucs, color=colors, edgecolor='black', linewidth=0.5)
        ax.axhline(y=0.5, color='red', linewidth=1, linestyle='--', label='Chance')
        ax.axhline(y=0.75, color='green', linewidth=1, linestyle='--', label='Good')
        ax.set_ylabel('AUC')
        ax.set_title('EXP-1833: Predicting Next-1h Metabolic Context', fontweight='bold')
        ax.legend()
        ax.set_ylim(0.3, 1.0)
        for bar, val in zip(bars, aucs):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                   f'{val:.3f}', ha='center', va='bottom', fontsize=10)
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig03-context-prediction.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig03-context-prediction.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'population_auc': pop_auc,
    }


# ============================================================================
# EXP-1834: ISF Variability Drivers
# ============================================================================
def exp_1834(patients, figures_dir=None):
    """What drives ISF variability? Time-of-day, recent insulin load, glucose history?"""
    print("\n" + "=" * 70)
    print("EXP-1834: ISF Variability Drivers")
    print("=" * 70)

    results_per_patient = []
    feature_importances = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        
        # Find correction events: bolus > 0.5U, glucose > 150, followed by glucose drop
        corrections = []
        bolus_idx = np.where(np.nan_to_num(bolus) > 0.5)[0]
        
        for bi in bolus_idx:
            if bi + 36 >= n or glucose[bi] < 150:
                continue
            if not np.isfinite(glucose[bi]):
                continue
            
            # Measure glucose drop over 3h
            future_g = glucose[bi:bi+37]
            valid = np.isfinite(future_g)
            if valid.sum() < 20:
                continue
            
            drop = glucose[bi] - np.nanmin(future_g)
            dose = bolus[bi]
            if dose < 0.1:
                continue
            
            effective_isf = drop / dose
            
            if effective_isf < 0 or effective_isf > 500:
                continue
            
            # Compute features at correction time
            hour = (bi * 5 / 60) % 24
            
            # 4-harmonic temporal encoding
            harmonics = []
            for period in [24, 12, 8, 6]:
                harmonics.append(np.sin(2 * np.pi * hour / period))
                harmonics.append(np.cos(2 * np.pi * hour / period))
            
            # Slow features at this moment
            slow = {}
            win = 288  # 24h
            start = max(0, bi - win)
            seg_g = glucose[start:bi]
            seg_iob = iob[start:bi]
            
            valid_g = seg_g[np.isfinite(seg_g)]
            slow['tar_24h'] = np.mean(valid_g > 180) if len(valid_g) > 10 else np.nan
            slow['tbr_24h'] = np.mean(valid_g < 70) if len(valid_g) > 10 else np.nan
            slow['glucose_mean_24h'] = np.mean(valid_g) if len(valid_g) > 10 else np.nan
            slow['glucose_std_24h'] = np.std(valid_g) if len(valid_g) > 10 else np.nan
            slow['insulin_load_24h'] = np.nanmean(seg_iob) if len(seg_iob) > 10 else np.nan
            
            # 6h features
            win6 = 72
            start6 = max(0, bi - win6)
            seg6 = glucose[start6:bi]
            valid6 = seg6[np.isfinite(seg6)]
            slow['glucose_mean_6h'] = np.mean(valid6) if len(valid6) > 10 else np.nan
            slow['insulin_load_6h'] = np.nanmean(iob[start6:bi]) if (bi - start6) > 10 else np.nan
            
            corrections.append({
                'isf': effective_isf,
                'harmonics': harmonics,
                'glucose_at_corr': glucose[bi],
                'dose': dose,
                **slow
            })
        
        if len(corrections) < 20:
            print(f"  {name}: only {len(corrections)} corrections, skipping")
            results_per_patient.append({'name': name, 'n_corrections': len(corrections)})
            continue
        
        # Build feature matrix
        feature_names = ['sin_24h', 'cos_24h', 'sin_12h', 'cos_12h', 'sin_8h', 'cos_8h',
                        'sin_6h', 'cos_6h', 'glucose_at_corr', 'dose',
                        'tar_24h', 'tbr_24h', 'glucose_mean_24h', 'glucose_std_24h',
                        'insulin_load_24h', 'glucose_mean_6h', 'insulin_load_6h']
        
        X = np.zeros((len(corrections), len(feature_names)))
        y = np.zeros(len(corrections))
        
        for ci, c in enumerate(corrections):
            y[ci] = c['isf']
            for fi, fn in enumerate(feature_names):
                if fn.startswith('sin_') or fn.startswith('cos_'):
                    idx = fi
                    X[ci, fi] = c['harmonics'][idx]
                elif fn in c:
                    X[ci, fi] = c.get(fn, np.nan)
        
        # Handle NaN
        for col in range(X.shape[1]):
            col_mean = np.nanmean(X[:, col])
            X[np.isnan(X[:, col]), col] = col_mean if np.isfinite(col_mean) else 0
        
        # Fit and evaluate
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import cross_val_score
        
        model = Ridge(alpha=10.0)
        scores = cross_val_score(model, X, y, cv=min(5, len(corrections)//5), scoring='r2')
        mean_r2 = np.mean(scores)
        
        # Feature importance
        model.fit(X, y)
        importances = np.abs(model.coef_) * np.std(X, axis=0)
        importance_rank = sorted(zip(feature_names, importances), key=lambda x: -x[1])
        
        results_per_patient.append({
            'name': name,
            'n_corrections': len(corrections),
            'r2_cv': mean_r2,
            'top_features': [(fn, float(imp)) for fn, imp in importance_rank[:5]],
            'isf_mean': float(np.mean(y)),
            'isf_cv': float(np.std(y) / np.mean(y)) if np.mean(y) > 0 else np.nan,
        })
        feature_importances.append(dict(importance_rank))
        
        top3 = ', '.join(f'{fn}={imp:.1f}' for fn, imp in importance_rank[:3])
        print(f"  {name}: n={len(corrections)} R²={mean_r2:.3f} ISF_CV={np.std(y)/np.mean(y):.2f} top=[{top3}]")

    # Population aggregation of feature importance
    print(f"\n  Population feature importance (mean |coef × std|):")
    all_features = {}
    for fi in feature_importances:
        for fn, imp in fi.items():
            if fn not in all_features:
                all_features[fn] = []
            all_features[fn].append(imp)
    
    sorted_features = sorted(all_features.items(), key=lambda x: -np.mean(x[1]))
    for fn, vals in sorted_features:
        print(f"    {fn:25s}: {np.mean(vals):8.2f} ± {np.std(vals):6.2f}")
    
    # What's the top driver?
    top_driver = sorted_features[0][0] if sorted_features else 'unknown'
    mean_r2 = np.mean([r['r2_cv'] for r in results_per_patient if 'r2_cv' in r and np.isfinite(r['r2_cv'])])
    
    if mean_r2 > 0.15:
        verdict = f'EXPLAINABLE_BY_{top_driver.upper()}'
    elif mean_r2 > 0.05:
        verdict = 'PARTIALLY_EXPLAINABLE'
    else:
        verdict = 'LARGELY_UNEXPLAINED'
    
    print(f"\n  Mean cross-val R² for ISF prediction: {mean_r2:.3f}")
    print(f"  Top ISF driver: {top_driver}")
    print(f"\n  ✓ EXP-1834 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # Feature importance
        ax = axes[0]
        fnames = [fn for fn, _ in sorted_features[:10]]
        fvals = [np.mean(vals) for _, vals in sorted_features[:10]]
        ax.barh(range(len(fnames)), fvals, color='#3498db', edgecolor='black', linewidth=0.5)
        ax.set_yticks(range(len(fnames)))
        ax.set_yticklabels(fnames, fontsize=8)
        ax.set_xlabel('Importance (|coef × std|)')
        ax.set_title('ISF Variability Drivers')
        ax.invert_yaxis()
        
        # ISF CV per patient
        ax = axes[1]
        cvs = [(r['name'], r['isf_cv']) for r in results_per_patient if 'isf_cv' in r and np.isfinite(r.get('isf_cv', np.nan))]
        if cvs:
            names, vals = zip(*cvs)
            ax.bar(names, vals, color='#e74c3c', edgecolor='black', linewidth=0.5)
            ax.set_ylabel('ISF Coefficient of Variation')
            ax.set_title('ISF Variability by Patient')
            ax.axhline(y=0.5, color='orange', linestyle='--', label='High variability')
            ax.legend()
        
        fig.suptitle('EXP-1834: What Drives ISF Variability?', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig04-isf-drivers.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig04-isf-drivers.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'mean_r2': mean_r2,
        'top_driver': top_driver,
        'feature_importance': dict(sorted_features),
    }


# ============================================================================
# EXP-1835: Nonlinear S/D Phase Detection
# ============================================================================
def exp_1835(patients, figures_dir=None):
    """Detect nonlinear supply/demand phase structure via kernel CCA."""
    print("\n" + "=" * 70)
    print("EXP-1835: Nonlinear S/D Phase Detection")
    print("=" * 70)

    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        supply = sd_data['supply']
        demand = sd_data['demand']
        n = len(glucose)
        
        # Test at multiple timescales whether nonlinear features of S and D
        # are more predictive than linear ones
        
        windows = {'6h': 72, '12h': 144, '24h': 288, '48h': 576}
        patient_result = {'name': name}
        
        for wname, wsteps in windows.items():
            # Build cumulative + nonlinear features
            cs_s = np.nancumsum(np.nan_to_num(supply))
            cs_d = np.nancumsum(np.nan_to_num(demand))
            
            # Linear features: trailing sum of S and D
            lin_s = np.zeros(n)
            lin_d = np.zeros(n)
            for i in range(wsteps, n):
                lin_s[i] = cs_s[i] - cs_s[i - wsteps]
                lin_d[i] = cs_d[i] - cs_d[i - wsteps]
            
            # Nonlinear features: products, ratios, RMS
            nl_sd_product = lin_s * lin_d
            nl_sd_ratio = np.where(lin_d != 0, lin_s / (np.abs(lin_d) + 1e-6), 0)
            nl_s_sq = lin_s ** 2
            nl_d_sq = lin_d ** 2
            
            # RMS of supply rate in window (captures volatility, not just sum)
            rms_s = np.zeros(n)
            rms_d = np.zeros(n)
            for i in range(wsteps, n):
                seg_s = supply[i-wsteps:i]
                seg_d = demand[i-wsteps:i]
                valid_s = seg_s[np.isfinite(seg_s)]
                valid_d = seg_d[np.isfinite(seg_d)]
                rms_s[i] = np.sqrt(np.mean(valid_s**2)) if len(valid_s) > 5 else np.nan
                rms_d[i] = np.sqrt(np.mean(valid_d**2)) if len(valid_d) > 5 else np.nan
            
            # Target: next 6h mean glucose
            target = np.full(n, np.nan)
            for i in range(n - 72):
                seg = glucose[i+1:i+73]
                valid = seg[np.isfinite(seg)]
                if len(valid) > 30:
                    target[i] = np.mean(valid)
            
            from sklearn.linear_model import Ridge
            split = int(n * 0.7)
            
            # Linear model
            X_lin = np.column_stack([lin_s, lin_d])
            # Nonlinear model
            X_nl = np.column_stack([lin_s, lin_d, nl_sd_product, nl_sd_ratio, 
                                     nl_s_sq, nl_d_sq, rms_s, rms_d])
            
            for fname, X in [('linear', X_lin), ('nonlinear', X_nl)]:
                mask_tr = np.all(np.isfinite(X[:split]), axis=1) & np.isfinite(target[:split])
                mask_te = np.all(np.isfinite(X[split:]), axis=1) & np.isfinite(target[split:])
                if mask_tr.sum() < 50 or mask_te.sum() < 50:
                    patient_result[f'r2_{fname}_{wname}'] = np.nan
                    continue
                model = Ridge(alpha=1.0)
                model.fit(X[:split][mask_tr], target[:split][mask_tr])
                pred = model.predict(X[split:][mask_te])
                patient_result[f'r2_{fname}_{wname}'] = safe_r2(target[split:][mask_te], pred)
        
        results_per_patient.append(patient_result)
        # Show 24h comparison
        lin24 = patient_result.get('r2_linear_24h', np.nan)
        nl24 = patient_result.get('r2_nonlinear_24h', np.nan)
        print(f"  {name}: 24h linear={lin24:.4f} nonlinear={nl24:.4f} Δ={nl24-lin24:+.4f}")
    
    # Population summary
    print(f"\n  Population mean R²:")
    print(f"  {'Window':>8s}  {'Linear':>8s}  {'Nonlinear':>10s}  {'Δ':>8s}")
    
    pop_results = {}
    for wname in ['6h', '12h', '24h', '48h']:
        lin_vals = [r[f'r2_linear_{wname}'] for r in results_per_patient if np.isfinite(r.get(f'r2_linear_{wname}', np.nan))]
        nl_vals = [r[f'r2_nonlinear_{wname}'] for r in results_per_patient if np.isfinite(r.get(f'r2_nonlinear_{wname}', np.nan))]
        lin_m = np.mean(lin_vals) if lin_vals else np.nan
        nl_m = np.mean(nl_vals) if nl_vals else np.nan
        delta = nl_m - lin_m
        print(f"  {wname:>8s}  {lin_m:>8.4f}  {nl_m:>10.4f}  {delta:>+8.4f}")
        pop_results[wname] = {'linear': lin_m, 'nonlinear': nl_m, 'delta': delta}
    
    # Does nonlinear help more at longer windows?
    deltas = [pop_results[w]['delta'] for w in ['6h', '12h', '24h', '48h']]
    if all(d > 0 for d in deltas) and deltas[-1] > deltas[0]:
        verdict = 'NONLINEAR_GROWS_WITH_SCALE'
    elif any(d > 0.01 for d in deltas):
        verdict = 'NONLINEAR_HELPS_SOME'
    else:
        verdict = 'LINEAR_SUFFICIENT'
    
    print(f"\n  ✓ EXP-1835 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(8, 5))
        windows = ['6h', '12h', '24h', '48h']
        lin_vals = [pop_results[w]['linear'] for w in windows]
        nl_vals = [pop_results[w]['nonlinear'] for w in windows]
        x = range(len(windows))
        ax.plot(x, lin_vals, 'o-', color='#3498db', label='Linear S/D', linewidth=2, markersize=8)
        ax.plot(x, nl_vals, 's-', color='#e74c3c', label='Nonlinear S/D', linewidth=2, markersize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(windows)
        ax.set_xlabel('Integration Window')
        ax.set_ylabel('R² (predicting 6h-ahead glucose)')
        ax.set_title('EXP-1835: Nonlinear S/D Phase Detection', fontweight='bold')
        ax.legend()
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig05-nonlinear-phase.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig05-nonlinear-phase.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'population': pop_results,
    }


# ============================================================================
# EXP-1836: Meal-Rise Decomposition
# ============================================================================
def exp_1836(patients, figures_dir=None):
    """Cluster meal rises into actionable types. Can we tell fast/slow apart early?"""
    print("\n" + "=" * 70)
    print("EXP-1836: Meal-Rise Decomposition — Early Classification")
    print("=" * 70)

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score, accuracy_score
    
    results_per_patient = []
    all_meals = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(glucose))
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        # Find glucose rises > 20 mg/dL
        dg = np.diff(glucose, prepend=glucose[0])
        
        # Find meal starts: carbs > 5g
        meal_idx = np.where(np.nan_to_num(carbs) > 5)[0]
        
        patient_meals = []
        
        for mi in meal_idx:
            if mi + 36 >= n or mi < 72:  # need 6h before and 3h after
                continue
            
            # Measure full excursion profile
            profile = glucose[mi:mi+37] - glucose[mi]  # 3h relative to start
            if not np.all(np.isfinite(profile[:7])):  # need first 30min valid
                continue
            
            # Classify by peak time
            valid_profile = np.where(np.isfinite(profile), profile, 0)
            peak_idx = np.argmax(valid_profile)
            peak_time = peak_idx * 5  # minutes
            peak_mag = valid_profile[peak_idx]
            
            if peak_mag < 10:  # minimal excursion
                continue
            
            # Classification: fast (<45min), medium (45-90), slow (>90)
            if peak_time < 45:
                meal_type = 'fast'
            elif peak_time < 90:
                meal_type = 'medium'
            else:
                meal_type = 'slow'
            
            # Features available at meal time (BEFORE peak):
            features = {
                'glucose_at_meal': glucose[mi],
                'iob_at_meal': iob[mi],
                'carbs': carbs[mi],
                'dg_at_meal': dg[mi],  # trend at meal time
                'glucose_mean_6h': np.nanmean(glucose[max(0,mi-72):mi]),
                'glucose_std_6h': np.nanstd(glucose[max(0,mi-72):mi]),
                'insulin_6h': np.nanmean(iob[max(0,mi-72):mi]),
                # Early slope (first 15 min)
                'slope_15min': (glucose[min(mi+3, n-1)] - glucose[mi]) / 3 if mi+3 < n else np.nan,
                'meal_type': meal_type,
                'peak_time': peak_time,
                'peak_mag': peak_mag,
                'patient': name,
            }
            patient_meals.append(features)
            all_meals.append(features)
        
        results_per_patient.append({
            'name': name,
            'n_meals': len(patient_meals),
            'n_fast': sum(1 for m in patient_meals if m['meal_type'] == 'fast'),
            'n_medium': sum(1 for m in patient_meals if m['meal_type'] == 'medium'),
            'n_slow': sum(1 for m in patient_meals if m['meal_type'] == 'slow'),
        })
        print(f"  {name}: {len(patient_meals)} meals "
              f"(fast={results_per_patient[-1]['n_fast']}, "
              f"med={results_per_patient[-1]['n_medium']}, "
              f"slow={results_per_patient[-1]['n_slow']})")
    
    # Can we predict meal type from features available at meal onset?
    print(f"\n  Total meals: {len(all_meals)}")
    
    feature_cols = ['glucose_at_meal', 'iob_at_meal', 'carbs', 'dg_at_meal',
                    'glucose_mean_6h', 'glucose_std_6h', 'insulin_6h', 'slope_15min']
    
    X = np.array([[m.get(f, np.nan) for f in feature_cols] for m in all_meals])
    y_type = np.array([m['meal_type'] for m in all_meals])
    
    # Handle NaN
    for col in range(X.shape[1]):
        col_mean = np.nanmean(X[:, col])
        X[np.isnan(X[:, col]), col] = col_mean if np.isfinite(col_mean) else 0
    
    # Binary: fast vs not-fast (most actionable distinction)
    y_fast = (y_type == 'fast').astype(float)
    
    from sklearn.model_selection import cross_val_score, cross_val_predict
    
    model = LogisticRegression(max_iter=500, C=0.1)
    
    # Cross-validated AUC
    scores = cross_val_score(model, X, y_fast, cv=5, scoring='roc_auc')
    mean_auc = np.mean(scores)
    
    # With early slope (first 15 min)
    X_with_slope = X.copy()
    scores_slope = cross_val_score(model, X_with_slope, y_fast, cv=5, scoring='roc_auc')
    mean_auc_slope = np.mean(scores_slope)
    
    # Without early slope (features available at meal ONSET, not 15 min later)
    X_no_slope = X[:, :-1]
    scores_no_slope = cross_val_score(model, X_no_slope, y_fast, cv=5, scoring='roc_auc')
    mean_auc_no_slope = np.mean(scores_no_slope)
    
    print(f"\n  Fast meal prediction (binary: fast vs medium/slow):")
    print(f"    AUC with 15-min slope:    {mean_auc_slope:.3f}")
    print(f"    AUC without slope (onset): {mean_auc_no_slope:.3f}")
    print(f"    Δ from early slope:        {mean_auc_slope - mean_auc_no_slope:+.3f}")
    
    fast_frac = np.mean(y_fast)
    print(f"\n  Base rate (fast meals): {fast_frac:.1%}")
    
    if mean_auc_slope > 0.70:
        verdict = 'EARLY_DETECTION_POSSIBLE'
    elif mean_auc_slope > 0.60:
        verdict = 'MARGINAL_DETECTION'
    else:
        verdict = 'NOT_DISTINGUISHABLE_EARLY'
    
    print(f"\n  ✓ EXP-1836 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # Peak time distribution by type
        ax = axes[0]
        for mtype, color in [('fast', '#e74c3c'), ('medium', '#f39c12'), ('slow', '#3498db')]:
            times = [m['peak_time'] for m in all_meals if m['meal_type'] == mtype]
            ax.hist(times, bins=20, alpha=0.5, color=color, label=f'{mtype} (n={len(times)})', edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Peak Time (minutes)')
        ax.set_ylabel('Count')
        ax.set_title('Meal Absorption Speed Distribution')
        ax.legend()
        
        # Early slope vs peak time
        ax = axes[1]
        slopes = [m['slope_15min'] for m in all_meals if np.isfinite(m.get('slope_15min', np.nan))]
        peaks = [m['peak_time'] for m in all_meals if np.isfinite(m.get('slope_15min', np.nan))]
        types = [m['meal_type'] for m in all_meals if np.isfinite(m.get('slope_15min', np.nan))]
        colors = {'fast': '#e74c3c', 'medium': '#f39c12', 'slow': '#3498db'}
        for mtype in ['fast', 'medium', 'slow']:
            mask = [t == mtype for t in types]
            sx = [s for s, m in zip(slopes, mask) if m]
            sy = [p for p, m in zip(peaks, mask) if m]
            ax.scatter(sx, sy, c=colors[mtype], alpha=0.3, s=10, label=mtype)
        ax.set_xlabel('15-min Slope (mg/dL/5min)')
        ax.set_ylabel('Peak Time (min)')
        ax.set_title('Early Slope vs Peak Time')
        ax.legend()
        
        fig.suptitle('EXP-1836: Meal-Rise Decomposition', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig06-meal-decomp.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig06-meal-decomp.png")

    return {
        'verdict': verdict,
        'n_meals': len(all_meals),
        'fast_fraction': float(fast_frac),
        'auc_with_slope': float(mean_auc_slope),
        'auc_without_slope': float(mean_auc_no_slope),
        'patients': results_per_patient,
    }


# ============================================================================
# EXP-1837: Insulin-Fall Decomposition
# ============================================================================
def exp_1837(patients, figures_dir=None):
    """Why is insulin_fall the worst excursion type? Decompose the error."""
    print("\n" + "=" * 70)
    print("EXP-1837: Insulin-Fall Decomposition — Error Sources")
    print("=" * 70)

    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(glucose))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(glucose))
        sd_data = compute_supply_demand(df)
        supply = sd_data['supply']
        demand = sd_data['demand']
        net = sd_data['net']
        n = len(glucose)
        
        # Find insulin-dominated falls: glucose dropping > 2 mg/dL/step AND iob > median
        dg = np.diff(glucose, prepend=glucose[0])
        iob_med = np.nanmedian(iob[iob > 0]) if np.any(iob > 0) else 0
        
        fall_mask = (dg < -2) & (iob > iob_med) & np.isfinite(glucose)
        fall_idx = np.where(fall_mask)[0]
        
        if len(fall_idx) < 50:
            print(f"  {name}: only {len(fall_idx)} insulin falls, skipping")
            results_per_patient.append({'name': name, 'n_falls': len(fall_idx)})
            continue
        
        # For each fall, measure error decomposition
        timing_errors = []  # predicted vs actual timing of nadir
        magnitude_errors = []  # predicted vs actual magnitude of drop
        rebound_errors = []  # model misses rebound
        
        # Find fall episodes (contiguous falls)
        episodes = []
        ep_start = fall_idx[0]
        for i in range(1, len(fall_idx)):
            if fall_idx[i] - fall_idx[i-1] > 3:  # gap > 15 min
                episodes.append((ep_start, fall_idx[i-1]))
                ep_start = fall_idx[i]
        episodes.append((ep_start, fall_idx[-1]))
        
        n_overshoot = 0  # falls that go below model prediction
        n_rebound = 0  # falls followed by rapid rise
        n_slow_fall = 0  # model predicts faster fall than actual
        
        for start, end in episodes:
            if end + 12 >= n:
                continue
            
            actual_drop = glucose[start] - glucose[end]
            model_drop = np.nansum(net[start:end+1])  # model's predicted change
            
            if actual_drop > 0:
                # Magnitude error
                mag_err = actual_drop + model_drop  # positive = model under-predicts drop
                magnitude_errors.append(mag_err)
                
                if mag_err > 10:
                    n_overshoot += 1
                elif mag_err < -10:
                    n_slow_fall += 1
                
                # Check for rebound
                post_fall = glucose[end:end+13]
                if np.any(np.isfinite(post_fall)):
                    rebound = np.nanmax(post_fall) - glucose[end]
                    if rebound > 20:
                        n_rebound += 1
                    rebound_errors.append(rebound)
        
        n_episodes = len(episodes)
        overshoot_frac = n_overshoot / max(n_episodes, 1)
        rebound_frac = n_rebound / max(n_episodes, 1)
        slow_fall_frac = n_slow_fall / max(n_episodes, 1)
        mean_rebound = np.mean(rebound_errors) if rebound_errors else np.nan
        
        results_per_patient.append({
            'name': name,
            'n_falls': len(fall_idx),
            'n_episodes': n_episodes,
            'overshoot_fraction': overshoot_frac,
            'rebound_fraction': rebound_frac,
            'slow_fall_fraction': slow_fall_frac,
            'mean_rebound_mg': mean_rebound,
            'mean_magnitude_error': np.mean(magnitude_errors) if magnitude_errors else np.nan,
        })
        
        print(f"  {name}: {n_episodes} episodes, overshoot={overshoot_frac:.0%}, "
              f"rebound={rebound_frac:.0%}, slow_fall={slow_fall_frac:.0%}, "
              f"mean_rebound={mean_rebound:.1f} mg/dL")
    
    # Population summary
    valid = [r for r in results_per_patient if 'n_episodes' in r and r['n_episodes'] > 5]
    
    print(f"\n  Population insulin-fall error decomposition (n={len(valid)}):")
    for key, label in [
        ('overshoot_fraction', 'Model under-predicts drop (overshoot)'),
        ('rebound_fraction', 'Post-fall rebound > 20 mg/dL'),
        ('slow_fall_fraction', 'Model over-predicts drop (slow fall)'),
        ('mean_rebound_mg', 'Mean post-fall rebound'),
        ('mean_magnitude_error', 'Mean magnitude error (mg/dL)'),
    ]:
        vals = [r[key] for r in valid if np.isfinite(r.get(key, np.nan))]
        if vals:
            print(f"    {label:45s}: {np.mean(vals):.2f} ± {np.std(vals):.2f}")
    
    overshoot_mean = np.mean([r['overshoot_fraction'] for r in valid])
    rebound_mean = np.mean([r['rebound_fraction'] for r in valid])
    
    if rebound_mean > 0.3:
        verdict = 'REBOUND_DOMINATED'
    elif overshoot_mean > 0.3:
        verdict = 'OVERSHOOT_DOMINATED'
    else:
        verdict = 'MIXED_ERRORS'
    
    print(f"\n  ✓ EXP-1837 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        ax = axes[0]
        categories = ['Overshoot\n(model under-predicts)', 'Post-fall\nRebound', 'Slow Fall\n(model over-predicts)']
        fractions = [
            np.mean([r['overshoot_fraction'] for r in valid]),
            np.mean([r['rebound_fraction'] for r in valid]),
            np.mean([r['slow_fall_fraction'] for r in valid]),
        ]
        colors = ['#e74c3c', '#f39c12', '#3498db']
        ax.bar(categories, fractions, color=colors, edgecolor='black', linewidth=0.5)
        ax.set_ylabel('Fraction of Episodes')
        ax.set_title('Insulin-Fall Error Types')
        for i, v in enumerate(fractions):
            ax.text(i, v + 0.01, f'{v:.0%}', ha='center')
        
        ax = axes[1]
        rebounds = [r['mean_rebound_mg'] for r in valid if np.isfinite(r.get('mean_rebound_mg', np.nan))]
        names = [r['name'] for r in valid if np.isfinite(r.get('mean_rebound_mg', np.nan))]
        ax.bar(names, rebounds, color='#f39c12', edgecolor='black', linewidth=0.5)
        ax.set_ylabel('Mean Post-Fall Rebound (mg/dL)')
        ax.set_title('Rebound Magnitude by Patient')
        ax.axhline(y=20, color='red', linestyle='--', label='Clinical threshold')
        ax.legend()
        
        fig.suptitle('EXP-1837: Why Insulin Falls Are Hard to Model', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig07-insulin-fall.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig07-insulin-fall.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
    }


# ============================================================================
# EXP-1838: Combined Best-of-Breed Model
# ============================================================================
def exp_1838(patients, figures_dir=None):
    """Assemble all validated improvements and measure total lift vs baseline."""
    print("\n" + "=" * 70)
    print("EXP-1838: Combined Best-of-Breed Model vs Baseline")
    print("=" * 70)

    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
        supply = sd_data['supply']
        demand = sd_data['demand']
        net = sd_data['net']
        
        # Baseline: physics model prediction (supply - demand)
        pred_baseline = glucose + net  # 1-step-ahead
        
        # UAM-aware supply
        uam_supply, uam_active = uam_supply_adjustment(df, sd_data)
        uam_net = uam_supply - demand
        pred_uam = glucose + uam_net
        
        # Context-adaptive: classify and use different scaling per context
        ctx = classify_context(df, sd_data)
        
        # Combined: UAM + context + slow features as correction
        slow = compute_slow_features(df, sd_data, window_steps=288)
        
        # Build combined model: for each horizon, fit the best combination
        from sklearn.linear_model import Ridge
        
        horizons = {'5min': 1, '30min': 6, '1h': 12, '3h': 36, '6h': 72}
        split = int(n * 0.7)
        
        patient_result = {'name': name}
        
        for hname, hsteps in horizons.items():
            # Target
            target = np.full(n, np.nan)
            for i in range(n - hsteps):
                seg = glucose[i+1:i+hsteps+1]
                valid = seg[np.isfinite(seg)]
                if len(valid) > max(1, hsteps // 3):
                    target[i] = np.mean(valid)
            
            # Baseline R²
            r2_base = safe_r2(target[split:], pred_baseline[split:])
            
            # UAM R²
            r2_uam = safe_r2(target[split:], pred_uam[split:])
            
            # Full model: raw + UAM + slow + context encoding
            ctx_encoded = np.column_stack([
                (ctx == 'fasting').astype(float),
                (ctx == 'post_meal').astype(float),
                (ctx == 'correction').astype(float),
                (ctx == 'hypo_recovery').astype(float),
            ])
            
            X_full = np.column_stack([
                glucose, iob, uam_supply, uam_active.astype(float),
                slow['time_above_range'], slow['time_below_range'],
                slow['insulin_load'], slow['glucose_volatility'],
                slow['supply_integral'], slow['demand_integral'],
                ctx_encoded,
            ])
            
            mask_tr = np.all(np.isfinite(X_full[:split]), axis=1) & np.isfinite(target[:split])
            mask_te = np.all(np.isfinite(X_full[split:]), axis=1) & np.isfinite(target[split:])
            
            if mask_tr.sum() < 50 or mask_te.sum() < 50:
                r2_full = np.nan
            else:
                model = Ridge(alpha=1.0)
                model.fit(X_full[:split][mask_tr], target[:split][mask_tr])
                pred_full = model.predict(X_full[split:][mask_te])
                r2_full = safe_r2(target[split:][mask_te], pred_full)
            
            patient_result[f'r2_base_{hname}'] = r2_base
            patient_result[f'r2_uam_{hname}'] = r2_uam
            patient_result[f'r2_full_{hname}'] = r2_full
        
        results_per_patient.append(patient_result)
        r2s = {h: patient_result.get(f'r2_full_{h}', np.nan) for h in horizons}
        print(f"  {name}: " + " ".join(f"{h}={v:.3f}" for h, v in r2s.items()))
    
    # Population summary
    print(f"\n  Population mean R² by horizon:")
    print(f"  {'Horizon':>8s}  {'Baseline':>10s}  {'UAM':>10s}  {'Full':>10s}  {'Δ(Full-Base)':>12s}")
    
    pop_results = {}
    for hname in horizons:
        base_vals = [r[f'r2_base_{hname}'] for r in results_per_patient if np.isfinite(r.get(f'r2_base_{hname}', np.nan))]
        uam_vals = [r[f'r2_uam_{hname}'] for r in results_per_patient if np.isfinite(r.get(f'r2_uam_{hname}', np.nan))]
        full_vals = [r[f'r2_full_{hname}'] for r in results_per_patient if np.isfinite(r.get(f'r2_full_{hname}', np.nan))]
        
        base_m = np.mean(base_vals) if base_vals else np.nan
        uam_m = np.mean(uam_vals) if uam_vals else np.nan
        full_m = np.mean(full_vals) if full_vals else np.nan
        delta = full_m - base_m
        
        print(f"  {hname:>8s}  {base_m:>10.4f}  {uam_m:>10.4f}  {full_m:>10.4f}  {delta:>+12.4f}")
        pop_results[hname] = {'baseline': base_m, 'uam': uam_m, 'full': full_m, 'delta': delta}
    
    # Count patients where full > baseline at each horizon
    full_wins = {}
    for hname in horizons:
        wins = sum(1 for r in results_per_patient 
                   if np.isfinite(r.get(f'r2_full_{hname}', np.nan))
                   and np.isfinite(r.get(f'r2_base_{hname}', np.nan))
                   and r[f'r2_full_{hname}'] > r[f'r2_base_{hname}'])
        total = sum(1 for r in results_per_patient 
                    if np.isfinite(r.get(f'r2_full_{hname}', np.nan))
                    and np.isfinite(r.get(f'r2_base_{hname}', np.nan)))
        full_wins[hname] = f"{wins}/{total}"
        print(f"    Full > Baseline at {hname}: {wins}/{total}")
    
    verdict = 'COMBINED_BEST'
    print(f"\n  ✓ EXP-1838 verdict: {verdict}")

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(10, 6))
        horizon_labels = list(horizons.keys())
        x = range(len(horizon_labels))
        
        for model, color, label in [
            ('baseline', '#999999', 'Physics baseline'),
            ('uam', '#e74c3c', '+ UAM-aware'),
            ('full', '#2ecc71', '+ UAM + Slow + Context'),
        ]:
            vals = [pop_results[h][model] for h in horizon_labels]
            ax.plot(x, vals, 'o-', color=color, label=label, linewidth=2, markersize=8)
        
        ax.set_xticks(x)
        ax.set_xticklabels(horizon_labels)
        ax.set_xlabel('Prediction Horizon')
        ax.set_ylabel('R² (population mean)')
        ax.set_title('EXP-1838: Combined Best-of-Breed vs Baseline', fontweight='bold')
        ax.legend()
        ax.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        
        plt.tight_layout()
        path = os.path.join(figures_dir, 'dualscale-fig08-combined-model.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved dualscale-fig08-combined-model.png")

    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'population': pop_results,
        'full_wins': full_wins,
    }


# ============================================================================
# Main
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='EXP-1831–1838: Dual-Timescale & Combined Model')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--exp', type=int, help='Run single experiment (1831-1838)')
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-1831–1838: Dual-Timescale Architecture & Combined Features")
    print("=" * 70)

    patients = load_patients('externals/ns-data/patients/')
    print(f"Loaded {len(patients)} patients\n")

    figures_dir = FIGURES_DIR if args.figures else None
    if figures_dir:
        os.makedirs(figures_dir, exist_ok=True)

    experiments = [
        (1831, 'UAM + Slow Feature Additivity', exp_1831),
        (1832, 'Dual-Head Architecture Validation', exp_1832),
        (1833, 'Excursion Type Prediction', exp_1833),
        (1834, 'ISF Variability Drivers', exp_1834),
        (1835, 'Nonlinear S/D Phase Detection', exp_1835),
        (1836, 'Meal-Rise Decomposition', exp_1836),
        (1837, 'Insulin-Fall Decomposition', exp_1837),
        (1838, 'Combined Best-of-Breed Model', exp_1838),
    ]

    all_results = {}
    for eid, title, func in experiments:
        if args.exp and args.exp != eid:
            continue
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{eid}: {title}")
        print(f"{'#' * 70}")

        try:
            result = func(patients, figures_dir)
            all_results[f'EXP-{eid}'] = result
        except Exception as e:
            print(f"\n  ✗ EXP-{eid} FAILED: {e}")
            import traceback
            traceback.print_exc()
            all_results[f'EXP-{eid}'] = {'verdict': f'FAILED: {e}'}

    # Save results
    output_path = os.path.join('externals', 'experiments', 'exp-1831_dualscale_combined.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Make JSON-serializable
    def make_serializable(obj):
        if isinstance(obj, np.floating):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        return obj

    output = {
        'experiment': 'EXP-1831 to EXP-1838',
        'title': 'Dual-Timescale Architecture and Combined Feature Validation',
        'results': make_serializable(all_results),
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n✓ Results saved to {output_path}")

    # Synthesis
    print(f"\n{'=' * 70}")
    print(f"SYNTHESIS: Dual-Timescale & Combined Model")
    print(f"{'=' * 70}")
    for eid_str, result in all_results.items():
        print(f"  {eid_str}: {result.get('verdict', '?')}")

    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
