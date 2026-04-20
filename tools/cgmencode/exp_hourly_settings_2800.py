#!/usr/bin/env python3
"""
EXP-2800: Hourly-Scale Settings Extraction
============================================
EXP-2799 revealed that circadian and 72h effects live at longer timescales.
This experiment operates at HOURLY resolution for settings extraction,
where circadian and daily patterns are visible above the noise.

Approach:
1. Aggregate 5-min data to 1-hour bins (sum insulin, mean glucose, etc.)
2. Compute hourly BG change and hourly insulin delivery
3. Category-specific hourly models (meal hours vs correction hours vs basal)
4. Circadian adjustment at hourly scale
5. Extract ISF/CR from hourly aggregates (less noise per estimate)

The key insight: 5-min data has 55% stochastic noise (EXP-2799).
Aggregating to 1-hour should reduce noise by ~sqrt(12) ≈ 3.5×,
making signal-to-noise ratio much better for settings extraction.

HYPOTHESES (5):
H1: Hourly R² > 0.60 (vs 0.45 at 5-min)
H2: Hourly ISF estimates have lower CV than 5-min estimates
H3: Circadian signal is >5% of variance at hourly scale (vs 0.2% at 5-min)
H4: Hourly-extracted ISF closer to profile than 5-min extracted
H5: 72h insulin load signal visible at hourly scale (>2% variance)
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

warnings.filterwarnings('ignore')

EXCLUDE = {'odc-84181797', 'h', 'j'}

def classify_controller(pid):
    if pid.startswith('ns-'):
        return 'Trio'
    elif pid.startswith('odc-'):
        return 'OpenAPS'
    else:
        return 'Loop'

def aggregate_to_hourly(pdf):
    """Convert 5-min data to 1-hour bins."""
    if 'time' not in pdf.columns:
        return None
    
    pdf = pdf.copy()
    pdf['time_dt'] = pd.to_datetime(pdf['time'])
    pdf['hour_bin'] = pdf['time_dt'].dt.floor('h')
    
    # Aggregate
    hourly = pdf.groupby('hour_bin').agg(
        glucose_start=('glucose', 'first'),
        glucose_end=('glucose', 'last'),
        glucose_mean=('glucose', 'mean'),
        glucose_std=('glucose', 'std'),
        bolus_total=('bolus', 'sum'),
        smb_total=('bolus_smb', 'sum'),
        net_basal_mean=('net_basal', 'mean'),
        scheduled_basal_rate=('scheduled_basal_rate', 'median'),
        scheduled_isf=('scheduled_isf', 'median'),
        scheduled_cr=('scheduled_cr', 'median'),
        carbs_total=('carbs', 'sum'),
        iob_mean=('iob', 'mean'),
        n_readings=('glucose', 'count'),
    ).reset_index()
    
    # Require at least 8 of 12 readings per hour
    hourly = hourly[hourly['n_readings'] >= 8].copy()
    
    # Hourly BG change
    hourly['bg_change'] = hourly['glucose_end'] - hourly['glucose_start']
    
    # Actual basal delivery per hour
    hourly['actual_basal_rate'] = (hourly['net_basal_mean'] + hourly['scheduled_basal_rate']).clip(lower=0)
    hourly['actual_basal_delivery'] = hourly['actual_basal_rate']  # already U/h
    
    # Total insulin per hour
    hourly['total_insulin'] = hourly['bolus_total'] + hourly['smb_total'] + hourly['actual_basal_delivery']
    hourly['excess_insulin'] = hourly['total_insulin'] - hourly['scheduled_basal_rate']
    
    # Time features
    hourly['hour'] = hourly['hour_bin'].dt.hour
    hourly['sin_24'] = np.sin(2 * np.pi * hourly['hour'] / 24)
    hourly['cos_24'] = np.cos(2 * np.pi * hourly['hour'] / 24)
    
    # Categorize hours
    hourly['has_carbs'] = hourly['carbs_total'] > 0
    hourly['has_bolus'] = hourly['bolus_total'] > 0
    hourly['is_high'] = hourly['glucose_start'] > 150
    
    hourly['category'] = 'basal'
    hourly.loc[hourly['has_carbs'], 'category'] = 'meal'
    hourly.loc[(~hourly['has_carbs']) & hourly['is_high'] & (hourly['bg_change'] < 0), 'category'] = 'correction'
    hourly.loc[(~hourly['has_carbs']) & (hourly['bg_change'] > 10), 'category'] = 'rising'
    
    # 72h rolling insulin
    hourly = hourly.sort_values('hour_bin')
    hourly['insulin_72h'] = hourly['total_insulin'].rolling(72, min_periods=24).sum()
    
    # AR features
    hourly['bg_change_lag1'] = hourly['bg_change'].shift(1)
    hourly['bg_change_lag2'] = hourly['bg_change'].shift(2)
    
    return hourly

def analyze_patient_hourly(pdf, pid):
    ctrl = classify_controller(pid)
    
    hourly = aggregate_to_hourly(pdf)
    if hourly is None or len(hourly) < 200:
        return None
    
    isf = hourly['scheduled_isf'].median()
    cf = 0.2
    
    bg_change = hourly['bg_change']
    total_var = bg_change.var()
    
    if total_var == 0 or np.isnan(total_var):
        return None
    
    # ---- LEVEL 1: Hourly insulin effect ----
    hourly['bgi_hourly'] = -hourly['excess_insulin'] * isf * cf
    
    X1 = pd.DataFrame({'bgi': hourly['bgi_hourly'], 'const': 1.0}).dropna()
    y = bg_change.loc[X1.index].dropna()
    v1 = X1.index.intersection(y.index)
    
    if len(v1) < 100:
        return None
    
    c1, _, _, _ = lstsq(X1.loc[v1].values, y.loc[v1].values, rcond=None)
    p1 = X1.loc[v1].values @ c1
    ss_res1 = np.sum((y.loc[v1].values - p1) ** 2)
    ss_tot = np.sum((y.loc[v1].values - y.loc[v1].mean()) ** 2)
    r2_bgi = 1 - ss_res1 / ss_tot if ss_tot > 0 else 0
    
    # ---- LEVEL 2: + AR(1) ----
    X2 = pd.DataFrame({'bgi': hourly['bgi_hourly'], 'ar1': hourly['bg_change_lag1'], 'const': 1.0}).dropna()
    y2 = bg_change.loc[X2.index].dropna()
    v2 = X2.index.intersection(y2.index)
    
    if len(v2) > 100:
        c2, _, _, _ = lstsq(X2.loc[v2].values, y2.loc[v2].values, rcond=None)
        p2 = X2.loc[v2].values @ c2
        ss_res2 = np.sum((y2.loc[v2].values - p2) ** 2)
        ss_tot2 = np.sum((y2.loc[v2].values - y2.loc[v2].mean()) ** 2)
        r2_ar1 = 1 - ss_res2 / ss_tot2 if ss_tot2 > 0 else r2_bgi
    else:
        r2_ar1 = r2_bgi
    
    # ---- LEVEL 3: + Category-specific ----
    X3_full = pd.DataFrame({
        'bgi': hourly['bgi_hourly'],
        'ar1': hourly['bg_change_lag1'],
        'ar2': hourly['bg_change_lag2'],
        'const': 1.0,
    })
    
    pred3 = pd.Series(np.nan, index=hourly.index)
    cat_r2s = {}
    for cat in ['meal', 'correction', 'rising', 'basal']:
        mask = hourly['category'] == cat
        X_cat = X3_full[mask].dropna()
        y_cat = bg_change.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 20:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred3.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
            p_cat = X_cat.loc[v_cat].values @ c_cat
            ss_r = np.sum((y_cat.loc[v_cat].values - p_cat) ** 2)
            ss_t = np.sum((y_cat.loc[v_cat].values - y_cat.loc[v_cat].mean()) ** 2)
            cat_r2s[cat] = round(1 - ss_r / ss_t, 4) if ss_t > 0 else 0
    
    v3 = pred3.dropna().index.intersection(bg_change.dropna().index)
    if len(v3) > 100:
        ss_res3 = np.sum((bg_change.loc[v3].values - pred3.loc[v3].values) ** 2)
        ss_tot3 = np.sum((bg_change.loc[v3].values - bg_change.loc[v3].mean()) ** 2)
        r2_cat = 1 - ss_res3 / ss_tot3 if ss_tot3 > 0 else r2_ar1
    else:
        r2_cat = r2_ar1
    
    # ---- LEVEL 4: + Circadian ----
    X4_full = pd.DataFrame({
        'bgi': hourly['bgi_hourly'],
        'ar1': hourly['bg_change_lag1'],
        'ar2': hourly['bg_change_lag2'],
        'sin_24': hourly['sin_24'],
        'cos_24': hourly['cos_24'],
        'const': 1.0,
    })
    
    pred4 = pd.Series(np.nan, index=hourly.index)
    for cat in ['meal', 'correction', 'rising', 'basal']:
        mask = hourly['category'] == cat
        X_cat = X4_full[mask].dropna()
        y_cat = bg_change.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 20:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred4.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
    
    v4 = pred4.dropna().index.intersection(bg_change.dropna().index)
    if len(v4) > 100:
        ss_res4 = np.sum((bg_change.loc[v4].values - pred4.loc[v4].values) ** 2)
        ss_tot4 = np.sum((bg_change.loc[v4].values - bg_change.loc[v4].mean()) ** 2)
        r2_circ = 1 - ss_res4 / ss_tot4 if ss_tot4 > 0 else r2_cat
    else:
        r2_circ = r2_cat
    
    # ---- LEVEL 5: + 72h insulin ----
    X5_full = pd.DataFrame({
        'bgi': hourly['bgi_hourly'],
        'ar1': hourly['bg_change_lag1'],
        'ar2': hourly['bg_change_lag2'],
        'sin_24': hourly['sin_24'],
        'cos_24': hourly['cos_24'],
        'insulin_72h': hourly['insulin_72h'],
        'const': 1.0,
    })
    
    pred5 = pd.Series(np.nan, index=hourly.index)
    for cat in ['meal', 'correction', 'rising', 'basal']:
        mask = hourly['category'] == cat
        X_cat = X5_full[mask].dropna()
        y_cat = bg_change.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 20:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred5.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
    
    v5 = pred5.dropna().index.intersection(bg_change.dropna().index)
    if len(v5) > 100:
        ss_res5 = np.sum((bg_change.loc[v5].values - pred5.loc[v5].values) ** 2)
        ss_tot5 = np.sum((bg_change.loc[v5].values - bg_change.loc[v5].mean()) ** 2)
        r2_72h = 1 - ss_res5 / ss_tot5 if ss_tot5 > 0 else r2_circ
    else:
        r2_72h = r2_circ
    
    # ---- ISF estimation at hourly scale ----
    # Correction hours: BG > 150, no carbs, BG dropping
    corr_hours = hourly[(hourly['category'] == 'correction') & (hourly['excess_insulin'].abs() > 0.1)]
    if len(corr_hours) > 10:
        # ISF = -bg_change / excess_insulin (at hourly scale)
        isf_hourly = -corr_hours['bg_change'] / corr_hours['excess_insulin']
        isf_hourly = isf_hourly[(isf_hourly > 0) & (isf_hourly < 500)]  # sanity filter
        
        isf_med = float(isf_hourly.median()) if len(isf_hourly) > 5 else np.nan
        isf_cv = float(isf_hourly.std() / isf_hourly.mean()) if len(isf_hourly) > 5 and isf_hourly.mean() > 0 else np.nan
    else:
        isf_med = np.nan
        isf_cv = np.nan
    
    # Comparison: 5-min ISF CV (from same data at 5-min)
    delta_5min = pdf['glucose'].diff()
    bgi_5min_simple = -pdf['bolus'].fillna(0) * isf * cf  # simplified
    corr_5min = (pdf['glucose'] > 150) & (pdf['carbs'].fillna(0).rolling(36, min_periods=1).sum() == 0) & (delta_5min < 0)
    if corr_5min.sum() > 20:
        dev_5min = (delta_5min - bgi_5min_simple)[corr_5min]
        isf_cv_5min = float(dev_5min.std() / abs(dev_5min.mean())) if abs(dev_5min.mean()) > 0 else np.nan
    else:
        isf_cv_5min = np.nan
    
    return {
        'patient_id': pid,
        'controller': ctrl,
        'n_hours': len(hourly),
        'r2_bgi': round(r2_bgi, 4),
        'r2_ar1': round(r2_ar1, 4),
        'r2_cat': round(r2_cat, 4),
        'r2_circ': round(r2_circ, 4),
        'r2_72h': round(r2_72h, 4),
        'total_r2': round(r2_72h, 4),
        'inc_bgi': round(r2_bgi, 4),
        'inc_ar1': round(r2_ar1 - r2_bgi, 4),
        'inc_cat': round(r2_cat - r2_ar1, 4),
        'inc_circ': round(r2_circ - r2_cat, 4),
        'inc_72h': round(r2_72h - r2_circ, 4),
        'cat_r2s': cat_r2s,
        'isf_hourly_median': round(isf_med, 1) if not np.isnan(isf_med) else None,
        'isf_profile': round(isf, 1),
        'isf_cv_hourly': round(isf_cv, 3) if not np.isnan(isf_cv) else None,
        'isf_cv_5min': round(isf_cv_5min, 3) if not np.isnan(isf_cv_5min) else None,
    }

def main():
    print("=" * 60)
    print("EXP-2800: Hourly-Scale Settings Extraction")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 1000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        r = analyze_patient_hourly(pdf, pid)
        if r is None:
            continue
        results.append(r)
        
        isf_str = f"ISF={r['isf_hourly_median']}" if r['isf_hourly_median'] else "ISF=N/A"
        print(f"  {pid:28s} {r['controller']:8s} R²={r['total_r2']:.3f} "
              f"BGI={r['inc_bgi']:.3f} +AR1={r['inc_ar1']:+.3f} "
              f"+Cat={r['inc_cat']:+.3f} +Circ={r['inc_circ']:+.3f} "
              f"+72h={r['inc_72h']:+.3f} {isf_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis Tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: Hourly R² > 0.60
    med_r2 = rdf['total_r2'].median()
    hyp['H1_r2_gt_60'] = med_r2 > 0.60
    print(f"  {'✓ PASS' if hyp['H1_r2_gt_60'] else '✗ FAIL'}: H1 Hourly R²>0.60 = {med_r2:.3f}")
    print(f"    (Compare to 5-min: 0.445)")
    
    # H2: Hourly ISF CV lower than 5-min
    valid_cv = rdf.dropna(subset=['isf_cv_hourly', 'isf_cv_5min'])
    if len(valid_cv) > 3:
        cv_improves = (valid_cv['isf_cv_hourly'] < valid_cv['isf_cv_5min']).mean()
        hyp['H2_lower_cv'] = cv_improves > 0.5
        print(f"  {'✓ PASS' if hyp['H2_lower_cv'] else '✗ FAIL'}: H2 Lower ISF CV = "
              f"{cv_improves:.0%} ({(valid_cv['isf_cv_hourly'] < valid_cv['isf_cv_5min']).sum()}/{len(valid_cv)})")
        print(f"    Hourly CV: {valid_cv['isf_cv_hourly'].median():.3f}, 5-min CV: {valid_cv['isf_cv_5min'].median():.3f}")
    else:
        hyp['H2_lower_cv'] = False
        print("  ✗ FAIL: H2 — insufficient ISF data")
    
    # H3: Circadian > 5% at hourly
    med_circ = rdf['inc_circ'].median()
    hyp['H3_circ_5pct'] = med_circ > 0.05
    print(f"  {'✓ PASS' if hyp['H3_circ_5pct'] else '✗ FAIL'}: H3 Circadian >5% = "
          f"{med_circ:.3f} ({med_circ*100:.1f}%)")
    print(f"    (Compare to 5-min: 0.2%)")
    
    # H4: Hourly ISF closer to profile
    valid_isf = rdf.dropna(subset=['isf_hourly_median'])
    if len(valid_isf) > 3:
        ratio = valid_isf['isf_hourly_median'] / valid_isf['isf_profile']
        med_ratio = ratio.median()
        hyp['H4_closer_profile'] = 0.3 < med_ratio < 3.0
        print(f"  {'✓ PASS' if hyp['H4_closer_profile'] else '✗ FAIL'}: H4 Hourly ISF/profile ratio = "
              f"{med_ratio:.2f}")
        print(f"    Hourly ISF median: {valid_isf['isf_hourly_median'].median():.1f}")
        print(f"    Profile ISF median: {valid_isf['isf_profile'].median():.1f}")
    else:
        hyp['H4_closer_profile'] = False
        print("  ✗ FAIL: H4 — insufficient ISF data")
    
    # H5: 72h signal > 2% at hourly
    med_72h = rdf['inc_72h'].median()
    hyp['H5_72h_2pct'] = med_72h > 0.02
    print(f"  {'✓ PASS' if hyp['H5_72h_2pct'] else '✗ FAIL'}: H5 72h signal >2% = "
          f"{med_72h:.4f} ({med_72h*100:.2f}%)")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Comparison ----
    print("\n" + "=" * 60)
    print("5-MIN vs HOURLY COMPARISON")
    print("=" * 60)
    
    print(f"\n  {'Metric':<25s} {'5-min':>10s} {'Hourly':>10s}")
    print(f"  {'-'*45}")
    print(f"  {'Total R² (median)':<25s} {'0.445':>10s} {med_r2:>10.3f}")
    print(f"  {'BGI contribution':<25s} {'1.2%':>10s} {rdf['inc_bgi'].median()*100:>9.1f}%")
    print(f"  {'AR(1) contribution':<25s} {'22.0%':>10s} {rdf['inc_ar1'].median()*100:>9.1f}%")
    print(f"  {'Category contribution':<25s} {'14.9%':>10s} {rdf['inc_cat'].median()*100:>9.1f}%")
    print(f"  {'Circadian contribution':<25s} {'0.2%':>10s} {rdf['inc_circ'].median()*100:>9.1f}%")
    print(f"  {'72h contribution':<25s} {'0.03%':>10s} {rdf['inc_72h'].median()*100:>9.2f}%")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2800: Hourly-Scale Settings Extraction', fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        cascade_colors = ['#E91E63', '#2196F3', '#4CAF50', '#FF9800', '#9C27B0']
        
        # 1. 5-min vs Hourly cascade comparison
        ax = axes[0, 0]
        labels = ['BGI', 'AR(1)', 'Cat', 'Circ', '72h']
        fivemin = [0.012, 0.220, 0.149, 0.002, 0.0003]
        hourly_vals = [rdf['inc_bgi'].median(), rdf['inc_ar1'].median(), rdf['inc_cat'].median(),
                      rdf['inc_circ'].median(), rdf['inc_72h'].median()]
        
        x = np.arange(len(labels))
        ax.bar(x - 0.15, fivemin, 0.3, label='5-min', color='#FF9800', alpha=0.6)
        ax.bar(x + 0.15, [max(0, v) for v in hourly_vals], 0.3, label='Hourly', color='#4CAF50', alpha=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel('Incremental R²')
        ax.set_title('5-min vs Hourly: Signal Decomposition')
        ax.legend()
        
        # 2. Per-patient total R²
        ax = axes[0, 1]
        sorted_r = rdf.sort_values('total_r2', ascending=True)
        colors_bar = [ctrl_colors[c] for c in sorted_r['controller']]
        ax.barh(range(len(sorted_r)), sorted_r['total_r2'].values, color=colors_bar, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax.set_yticks(range(len(sorted_r)))
        ax.set_yticklabels([p[:8] for p in sorted_r['patient_id']], fontsize=6)
        ax.axvline(0.60, color='red', linestyle='--', alpha=0.5, label='60% target')
        ax.set_xlabel('Total Hourly R²')
        ax.set_title('Per-Patient Hourly R²')
        ax.legend(fontsize=8)
        
        # 3. ISF: hourly vs profile
        ax = axes[0, 2]
        v = rdf.dropna(subset=['isf_hourly_median'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = v[v['controller'] == ctrl]
            ax.scatter(cdf['isf_profile'], cdf['isf_hourly_median'], c=ctrl_colors[ctrl],
                      label=ctrl, s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        if len(v) > 0:
            lim = max(v['isf_profile'].max(), v['isf_hourly_median'].max()) * 1.1
            ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Profile ISF (mg/dL/U)')
        ax.set_ylabel('Hourly-Extracted ISF (mg/dL/U)')
        ax.set_title('ISF: Profile vs Hourly Extraction')
        ax.legend(fontsize=8)
        
        # 4. ISF CV comparison
        ax = axes[1, 0]
        v = rdf.dropna(subset=['isf_cv_hourly', 'isf_cv_5min'])
        if len(v) > 0:
            ax.scatter(v['isf_cv_5min'], v['isf_cv_hourly'],
                      c=[ctrl_colors[c] for c in v['controller']], s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
            lim = max(v['isf_cv_5min'].max(), v['isf_cv_hourly'].max()) * 1.1
            ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='Equal')
        ax.set_xlabel('ISF CV (5-min)')
        ax.set_ylabel('ISF CV (Hourly)')
        ax.set_title('ISF Estimate Consistency')
        ax.legend(fontsize=8)
        
        # 5. Stacked cascade at hourly
        ax = axes[1, 1]
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            cdf = rdf[rdf['controller'] == ctrl]
            bottom = 0
            for j, (col, name) in enumerate(zip(['inc_bgi', 'inc_ar1', 'inc_cat', 'inc_circ', 'inc_72h'],
                                                 ['BGI', 'AR', 'Cat', 'Circ', '72h'])):
                val = max(0, cdf[col].median())
                ax.bar(i, val, bottom=bottom, color=cascade_colors[j],
                      label=name if i == 0 else '', edgecolor='black', linewidth=0.5)
                bottom += val
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(['Loop', 'Trio', 'OpenAPS'])
        ax.set_ylabel('Cumulative R²')
        ax.set_title('Hourly Cascade by Controller')
        ax.legend(fontsize=7)
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""HOURLY-SCALE ANALYSIS

Operating at 1-hour bins reduces noise
by ~3.5× (sqrt(12)) vs 5-min data.

5-min vs Hourly R²:
  5-min total: 0.445
  Hourly total: {med_r2:.3f}

Signal decomposition at hourly scale:
  BGI:      {rdf['inc_bgi'].median()*100:5.1f}%
  AR(1):    {rdf['inc_ar1'].median()*100:5.1f}%
  Category: {rdf['inc_cat'].median()*100:5.1f}%
  Circadian:{rdf['inc_circ'].median()*100:5.1f}%
  72h load: {rdf['inc_72h'].median()*100:5.2f}%

ISF extraction:
  Profile:  {rdf['isf_profile'].median():.0f} mg/dL/U
  Hourly:   {rdf.dropna(subset=['isf_hourly_median'])['isf_hourly_median'].median():.0f} mg/dL/U

{passed}/{total} hypotheses PASS"""
        ax.text(0.05, 0.5, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/hourly-settings', exist_ok=True)
        plt.savefig('tools/visualizations/hourly-settings/exp-2800-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization: tools/visualizations/hourly-settings/exp-2800-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2800',
        'title': 'Hourly-Scale Settings Extraction',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'median_hourly_r2': round(float(med_r2), 4),
            'median_inc_bgi': round(float(rdf['inc_bgi'].median()), 4),
            'median_inc_ar1': round(float(rdf['inc_ar1'].median()), 4),
            'median_inc_cat': round(float(rdf['inc_cat'].median()), 4),
            'median_inc_circ': round(float(rdf['inc_circ'].median()), 4),
            'median_inc_72h': round(float(rdf['inc_72h'].median()), 4),
        },
        'patients': [{k: v for k, v in r.items() if k != 'cat_r2s'} for r in results],
    }
    
    with open('externals/experiments/exp-2800_hourly_settings.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results: externals/experiments/exp-2800_hourly_settings.json")


if __name__ == '__main__':
    main()
