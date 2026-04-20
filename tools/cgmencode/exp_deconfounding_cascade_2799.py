#!/usr/bin/env python3
"""
EXP-2799: Multi-Timescale Deconfounding Cascade
=================================================
Implements the systematic layered subtraction approach:

At each timescale, measure what we CAN, subtract it from noise,
see what we're trying to measure.

TIMESCALES (nested):
1. 5-min: BG delta = BGI + AR(1) + noise
2. 30-min: Event window = meal/correction category + accumulated BGI
3. 3-hour: DIA window = insulin activity curve + carb absorption
4. 24-hour: Circadian = EGP cycle + insulin sensitivity variation
5. 72-hour: Insulin resistance = total insulin load + glycogen state

At each level, we subtract what we know → residual reveals next signal.

HYPOTHESES (5):
H1: Each timescale adds >1% variance explained over previous
H2: Cumulative R² > 0.50 (all timescales combined)
H3: Residual at finest scale (5-min) is reduced >60% vs raw
H4: 72-hour insulin load correlates with residual ISF (r > 0.15)
H5: Cascade decomposition accounts for >50% of within-patient variance
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from numpy.linalg import lstsq

warnings.filterwarnings('ignore')

EXCLUDE = {'odc-84181797', 'h', 'j'}

def classify_controller(pid):
    if pid.startswith('ns-'):
        return 'Trio'
    elif pid.startswith('odc-'):
        return 'OpenAPS'
    else:
        return 'Loop'

def make_activity_curve(dia_hours=6.0, peak_min=75.0, step_min=5.0):
    n_steps = int(dia_hours * 60 / step_min)
    t = np.arange(1, n_steps + 1) * step_min
    curve = (t / peak_min) * np.exp(1 - t / peak_min)
    return curve / curve.sum()

def compute_bgi(df, isf_cf, activity_curve):
    scheduled_rate = df['scheduled_basal_rate'].median() or 0
    bolus = df['bolus'].fillna(0).values
    smb = df['bolus_smb'].fillna(0).values
    net_basal = df['net_basal'].fillna(0).values
    actual_basal = np.clip(net_basal + scheduled_rate, 0, None) / 12.0
    delivery = bolus + smb + actual_basal
    excess = delivery - (scheduled_rate / 12.0)
    
    n = len(excess)
    nc = len(activity_curve)
    bgi = np.zeros(n)
    for i in range(n):
        w = min(i, nc)
        if w > 0:
            bgi[i] = -np.sum(excess[i-w:i] * activity_curve[:w][::-1]) * isf_cf
    return pd.Series(bgi, index=df.index)

def analyze_patient_cascade(pdf, pid, activity_curve):
    ctrl = classify_controller(pid)
    isf = pdf['scheduled_isf'].median()
    cf = 0.2
    
    delta = pdf['glucose'].diff()
    valid_delta = delta.dropna()
    total_var = valid_delta.var()
    
    if total_var == 0 or np.isnan(total_var):
        return None
    
    # Get time-of-day
    if 'time' in pdf.columns:
        hour = pd.to_datetime(pdf['time']).dt.hour + pd.to_datetime(pdf['time']).dt.minute / 60.0
    else:
        hour = ((np.arange(len(pdf)) % 288) * 5 / 60)
    hour = pd.Series(hour.values if hasattr(hour, 'values') else hour, index=pdf.index)
    
    cascade = {}
    residual = delta.copy()
    cumulative_r2 = 0
    
    # ---- LEVEL 1: 5-min BGI (insulin physics) ----
    bgi = compute_bgi(pdf, isf * cf, activity_curve)
    
    valid = residual.dropna().index.intersection(bgi.dropna().index)
    if len(valid) < 200:
        return None
    
    # Fit: delta ~ bgi
    X1 = pd.DataFrame({'bgi': bgi, 'const': 1.0}).loc[valid].dropna()
    y = residual.loc[X1.index]
    c1, _, _, _ = lstsq(X1.values, y.values, rcond=None)
    pred1 = X1.values @ c1
    
    ss_res1 = np.sum((y.values - pred1) ** 2)
    ss_tot = np.sum((y.values - y.mean()) ** 2)
    r2_bgi = 1 - ss_res1 / ss_tot if ss_tot > 0 else 0
    
    residual_1 = residual.copy()
    residual_1.loc[X1.index] = y.values - pred1
    
    cascade['L1_BGI'] = {
        'r2': round(r2_bgi, 4),
        'incremental_r2': round(r2_bgi, 4),
        'residual_var_pct': round(100 * (1 - r2_bgi), 1),
    }
    
    # ---- LEVEL 2: AR(1) — short-term momentum ----
    ar1 = delta.shift(1)
    X2 = pd.DataFrame({'bgi': bgi, 'ar1': ar1, 'const': 1.0}).loc[valid].dropna()
    y2 = delta.loc[X2.index]
    c2, _, _, _ = lstsq(X2.values, y2.values, rcond=None)
    pred2 = X2.values @ c2
    
    ss_res2 = np.sum((y2.values - pred2) ** 2)
    ss_tot2 = np.sum((y2.values - y2.mean()) ** 2)
    r2_ar1 = 1 - ss_res2 / ss_tot2 if ss_tot2 > 0 else 0
    
    residual_2 = delta.copy()
    residual_2.loc[X2.index] = y2.values - pred2
    
    cascade['L2_AR1'] = {
        'r2': round(r2_ar1, 4),
        'incremental_r2': round(r2_ar1 - r2_bgi, 4),
        'residual_var_pct': round(100 * (1 - r2_ar1), 1),
    }
    
    # ---- LEVEL 3: Category-specific AR(2) — event context ----
    carbs_active = pdf['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    categories = pd.Series('basal', index=pdf.index)
    categories[carbs_active] = 'CSF'
    isf_mask = (pdf['glucose'] > 130) & (~carbs_active) & (delta < 0)
    categories[isf_mask] = 'ISF'
    uam_mask = (~carbs_active) & (delta - bgi > 0) & (delta > 0)
    categories[uam_mask] = 'UAM'
    
    ar2 = delta.shift(2)
    X3_full = pd.DataFrame({
        'bgi': bgi, 'ar1': ar1, 'ar2': ar2, 'const': 1.0
    })
    
    pred3 = pd.Series(np.nan, index=pdf.index)
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        mask = categories == cat
        X_cat = X3_full[mask].dropna()
        y_cat = delta.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 50:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred3.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
    
    v3 = pred3.dropna().index.intersection(delta.dropna().index)
    if len(v3) > 200:
        ss_res3 = np.sum((delta.loc[v3].values - pred3.loc[v3].values) ** 2)
        ss_tot3 = np.sum((delta.loc[v3].values - delta.loc[v3].mean()) ** 2)
        r2_cat = 1 - ss_res3 / ss_tot3 if ss_tot3 > 0 else r2_ar1
    else:
        r2_cat = r2_ar1
    
    residual_3 = delta.copy()
    residual_3.loc[v3] = delta.loc[v3].values - pred3.loc[v3].values
    
    cascade['L3_CatAR2'] = {
        'r2': round(r2_cat, 4),
        'incremental_r2': round(r2_cat - r2_ar1, 4),
        'residual_var_pct': round(100 * (1 - r2_cat), 1),
    }
    
    # ---- LEVEL 4: Circadian (24h) ----
    sin_24 = np.sin(2 * np.pi * hour / 24)
    cos_24 = np.cos(2 * np.pi * hour / 24)
    
    X4_full = pd.DataFrame({
        'bgi': bgi, 'ar1': ar1, 'ar2': ar2,
        'sin_24': sin_24, 'cos_24': cos_24, 'const': 1.0
    })
    
    pred4 = pd.Series(np.nan, index=pdf.index)
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        mask = categories == cat
        X_cat = X4_full[mask].dropna()
        y_cat = delta.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 50:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred4.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
    
    v4 = pred4.dropna().index.intersection(delta.dropna().index)
    if len(v4) > 200:
        ss_res4 = np.sum((delta.loc[v4].values - pred4.loc[v4].values) ** 2)
        ss_tot4 = np.sum((delta.loc[v4].values - delta.loc[v4].mean()) ** 2)
        r2_circ = 1 - ss_res4 / ss_tot4 if ss_tot4 > 0 else r2_cat
    else:
        r2_circ = r2_cat
    
    cascade['L4_Circadian'] = {
        'r2': round(r2_circ, 4),
        'incremental_r2': round(r2_circ - r2_cat, 4),
        'residual_var_pct': round(100 * (1 - r2_circ), 1),
    }
    
    # ---- LEVEL 5: 72-hour insulin load ----
    # Rolling 72-hour total insulin as proxy for insulin resistance
    scheduled_rate = pdf['scheduled_basal_rate'].median() or 0
    actual_basal = np.clip(pdf['net_basal'].fillna(0) + scheduled_rate, 0, None) / 12.0
    total_delivery = pdf['bolus'].fillna(0) + pdf['bolus_smb'].fillna(0) + actual_basal
    
    # 72h rolling sum (864 5-min intervals)
    insulin_72h = total_delivery.rolling(864, min_periods=288).sum()
    
    X5_full = pd.DataFrame({
        'bgi': bgi, 'ar1': ar1, 'ar2': ar2,
        'sin_24': sin_24, 'cos_24': cos_24,
        'insulin_72h': insulin_72h,
        'const': 1.0
    })
    
    pred5 = pd.Series(np.nan, index=pdf.index)
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        mask = categories == cat
        X_cat = X5_full[mask].dropna()
        y_cat = delta.loc[X_cat.index].dropna()
        v_cat = X_cat.index.intersection(y_cat.index)
        if len(v_cat) > 50:
            c_cat, _, _, _ = lstsq(X_cat.loc[v_cat].values, y_cat.loc[v_cat].values, rcond=None)
            pred5.loc[v_cat] = X_cat.loc[v_cat].values @ c_cat
    
    v5 = pred5.dropna().index.intersection(delta.dropna().index)
    if len(v5) > 200:
        ss_res5 = np.sum((delta.loc[v5].values - pred5.loc[v5].values) ** 2)
        ss_tot5 = np.sum((delta.loc[v5].values - delta.loc[v5].mean()) ** 2)
        r2_72h = 1 - ss_res5 / ss_tot5 if ss_tot5 > 0 else r2_circ
    else:
        r2_72h = r2_circ
    
    cascade['L5_72h'] = {
        'r2': round(r2_72h, 4),
        'incremental_r2': round(r2_72h - r2_circ, 4),
        'residual_var_pct': round(100 * (1 - r2_72h), 1),
    }
    
    # ---- Residual reduction ----
    final_residual_var = (1 - r2_72h) * total_var if r2_72h > 0 else total_var
    reduction_pct = r2_72h * 100
    
    # ---- 72h insulin vs residual ISF correlation ----
    # After removing all above, does 72h insulin load predict residual ISF behavior?
    if len(v5) > 200:
        residual_5 = delta.loc[v5].values - pred5.loc[v5].values
        ins72 = insulin_72h.loc[v5].values
        valid_both = ~np.isnan(residual_5) & ~np.isnan(ins72)
        if valid_both.sum() > 100:
            from scipy import stats as sp_stats
            r_72h, p_72h = sp_stats.pearsonr(ins72[valid_both], residual_5[valid_both])
        else:
            r_72h, p_72h = 0, 1
    else:
        r_72h, p_72h = 0, 1
    
    return {
        'patient_id': pid,
        'controller': ctrl,
        'cascade': cascade,
        'total_r2': round(r2_72h, 4),
        'residual_reduction_pct': round(reduction_pct, 1),
        'r_72h_residual': round(r_72h, 4),
        'p_72h_residual': round(p_72h, 4),
        'n_rows': len(pdf),
    }

def main():
    print("=" * 60)
    print("EXP-2799: Multi-Timescale Deconfounding Cascade")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 1000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        r = analyze_patient_cascade(pdf, pid, activity_curve)
        if r is None:
            continue
        results.append(r)
        
        c = r['cascade']
        print(f"  {pid:28s} {r['controller']:8s} "
              f"BGI={c['L1_BGI']['r2']:.3f} "
              f"+AR1={c['L2_AR1']['incremental_r2']:+.3f} "
              f"+Cat={c['L3_CatAR2']['incremental_r2']:+.3f} "
              f"+Circ={c['L4_Circadian']['incremental_r2']:+.3f} "
              f"+72h={c['L5_72h']['incremental_r2']:+.3f} "
              f"= {r['total_r2']:.3f}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Aggregate cascade ----
    print("\n" + "=" * 60)
    print("CASCADE DECOMPOSITION (median across patients)")
    print("=" * 60)
    
    levels = ['L1_BGI', 'L2_AR1', 'L3_CatAR2', 'L4_Circadian', 'L5_72h']
    names = ['BGI (5-min insulin)', 'AR(1) momentum', 'Category-specific AR(2)',
             'Circadian (24h)', '72-hour insulin load']
    
    for level, name in zip(levels, names):
        r2s = [r['cascade'][level]['r2'] for r in results]
        inc_r2s = [r['cascade'][level]['incremental_r2'] for r in results]
        print(f"  {name:30s} R²={np.median(r2s):.3f}  +{np.median(inc_r2s):+.4f}")
    
    # ---- Hypotheses ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: Each timescale adds >1%
    increments = {}
    for level in levels:
        inc = [r['cascade'][level]['incremental_r2'] for r in results]
        increments[level] = np.median(inc)
    
    all_add_1pct = all(v > 0.01 for v in increments.values())
    hyp['H1_each_adds_1pct'] = all_add_1pct
    print(f"  {'✓ PASS' if all_add_1pct else '✗ FAIL'}: H1 Each timescale >1%")
    for level, v in increments.items():
        status = "✓" if v > 0.01 else "✗"
        print(f"    {status} {level}: {v:+.4f}")
    
    # H2: Cumulative > 0.50
    total_r2s = rdf['total_r2']
    med_total = total_r2s.median()
    hyp['H2_total_gt_50'] = med_total > 0.50
    print(f"  {'✓ PASS' if hyp['H2_total_gt_50'] else '✗ FAIL'}: H2 Total R²>0.50 = {med_total:.3f}")
    
    # H3: Residual reduced >60%
    reduction = rdf['residual_reduction_pct']
    med_reduction = reduction.median()
    hyp['H3_reduction_60'] = med_reduction > 60
    print(f"  {'✓ PASS' if hyp['H3_reduction_60'] else '✗ FAIL'}: H3 Residual reduced >60% = {med_reduction:.1f}%")
    
    # H4: 72h insulin correlates with residual (r > 0.15)
    r_72h_vals = rdf['r_72h_residual'].abs()
    med_r = r_72h_vals.median()
    hyp['H4_72h_corr'] = med_r > 0.15
    print(f"  {'✓ PASS' if hyp['H4_72h_corr'] else '✗ FAIL'}: H4 72h insulin |r|>0.15 = {med_r:.3f}")
    
    # H5: >50% within-patient variance explained
    hyp['H5_within_50'] = med_total > 0.50
    print(f"  {'✓ PASS' if hyp['H5_within_50'] else '✗ FAIL'}: H5 Within-patient >50% = {med_total:.3f}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- By controller ----
    print("\n" + "=" * 60)
    print("BY CONTROLLER")
    print("=" * 60)
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        print(f"\n  {ctrl} (N={len(cdf)}):")
        print(f"    Total R² (median): {cdf['total_r2'].median():.3f}")
        for level in levels:
            r2s = [r['cascade'][level]['incremental_r2'] for r in results if r['controller'] == ctrl]
            print(f"    {level}: +{np.median(r2s):+.4f}")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2799: Multi-Timescale Deconfounding Cascade', fontsize=14, fontweight='bold')
        
        colors_cascade = ['#E91E63', '#2196F3', '#4CAF50', '#FF9800', '#9C27B0']
        ctrl_colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. Stacked bar: variance decomposition
        ax = axes[0, 0]
        level_medians = []
        for level in levels:
            inc = [r['cascade'][level]['incremental_r2'] for r in results]
            level_medians.append(max(0, np.median(inc)))
        
        bottom = 0
        for i, (name, val) in enumerate(zip(['BGI', 'AR(1)', 'Cat-AR(2)', 'Circadian', '72h-insulin'], level_medians)):
            ax.bar('All Patients', val, bottom=bottom, color=colors_cascade[i], label=f'{name}: +{val:.3f}', edgecolor='black', linewidth=0.5)
            bottom += val
        
        ax.bar('All Patients', 1 - bottom, bottom=bottom, color='#E0E0E0', label=f'Residual: {1-bottom:.3f}', edgecolor='black', linewidth=0.5)
        ax.set_ylabel('Fraction of Variance')
        ax.set_title('Cascade Variance Decomposition')
        ax.legend(fontsize=7, loc='upper right')
        ax.set_ylim(0, 1.05)
        
        # 2. Per-patient total R²
        ax = axes[0, 1]
        sorted_r = rdf.sort_values('total_r2', ascending=True)
        colors_bar = [ctrl_colors[c] for c in sorted_r['controller']]
        ax.barh(range(len(sorted_r)), sorted_r['total_r2'].values, color=colors_bar, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax.set_yticks(range(len(sorted_r)))
        ax.set_yticklabels([p[:8] for p in sorted_r['patient_id']], fontsize=6)
        ax.axvline(0.5, color='red', linestyle='--', alpha=0.5, label='50% target')
        ax.set_xlabel('Total R²')
        ax.set_title('Per-Patient Total R² (all timescales)')
        ax.legend(fontsize=8)
        
        # 3. Cumulative R² curve
        ax = axes[0, 2]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cum_r2s = []
            for level in levels:
                r2s = [r['cascade'][level]['r2'] for r in results if r['controller'] == ctrl]
                cum_r2s.append(np.median(r2s))
            ax.plot(range(len(levels)), cum_r2s, 'o-', color=ctrl_colors[ctrl], label=ctrl, linewidth=2, markersize=6)
        
        ax.set_xticks(range(len(levels)))
        ax.set_xticklabels(['BGI', '+AR1', '+CatAR2', '+Circ', '+72h'], fontsize=8)
        ax.set_ylabel('Cumulative R²')
        ax.set_title('Cascade Accumulation by Controller')
        ax.legend(fontsize=8)
        ax.axhline(0.5, color='red', linestyle='--', alpha=0.3)
        
        # 4. Incremental R² distribution
        ax = axes[1, 0]
        data = []
        labels = []
        for level in levels:
            inc = [r['cascade'][level]['incremental_r2'] for r in results]
            data.append(inc)
            labels.append(level.split('_')[1])
        
        bp = ax.boxplot(data, labels=labels, patch_artist=True)
        for patch, color in zip(bp['boxes'], colors_cascade):
            patch.set_facecolor(color)
            patch.set_alpha(0.5)
        ax.axhline(0.01, color='red', linestyle='--', alpha=0.3, label='1% threshold')
        ax.set_ylabel('Incremental R²')
        ax.set_title('Incremental R² by Timescale')
        ax.legend(fontsize=8)
        
        # 5. 72h insulin vs residual
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = rdf[rdf['controller'] == ctrl]
            ax.scatter(cdf['r_72h_residual'].abs(), cdf['total_r2'],
                      c=ctrl_colors[ctrl], label=ctrl, s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
        ax.set_xlabel('|r| 72h Insulin vs Residual')
        ax.set_ylabel('Total R²')
        ax.set_title('72h Insulin Load Signal')
        ax.axvline(0.15, color='red', linestyle='--', alpha=0.3)
        ax.legend(fontsize=8)
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""MULTI-TIMESCALE DECONFOUNDING CASCADE

Layer-by-layer subtraction of known signals:

Level 1: BGI (insulin physics, 5-min)
  → R² = {level_medians[0]:.3f}

Level 2: + AR(1) momentum
  → R² = {sum(level_medians[:2]):.3f} (+{level_medians[1]:.3f})

Level 3: + Category-specific AR(2)
  → R² = {sum(level_medians[:3]):.3f} (+{level_medians[2]:.3f})

Level 4: + Circadian (24h EGP)
  → R² = {sum(level_medians[:4]):.3f} (+{level_medians[3]:.3f})

Level 5: + 72h insulin load
  → R² = {sum(level_medians[:5]):.3f} (+{level_medians[4]:.3f})

Residual: {1-sum(level_medians[:5]):.1%} unexplained

Median total R²: {med_total:.3f}
{passed}/{total} hypotheses PASS"""
        ax.text(0.05, 0.5, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/deconfounding-cascade', exist_ok=True)
        plt.savefig('tools/visualizations/deconfounding-cascade/exp-2799-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization: tools/visualizations/deconfounding-cascade/exp-2799-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2799',
        'title': 'Multi-Timescale Deconfounding Cascade',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'cascade_medians': {
            level: {
                'r2': round(float(np.median([r['cascade'][level]['r2'] for r in results])), 4),
                'incremental': round(float(np.median([r['cascade'][level]['incremental_r2'] for r in results])), 4),
            } for level in levels
        },
        'summary': {
            'median_total_r2': round(float(med_total), 4),
            'median_reduction_pct': round(float(med_reduction), 1),
            'median_72h_r': round(float(med_r), 4),
        },
        'patients': results,
    }
    
    with open('externals/experiments/exp-2799_deconfounding_cascade.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results: externals/experiments/exp-2799_deconfounding_cascade.json")


if __name__ == '__main__':
    main()
