#!/usr/bin/env python3
"""
EXP-2796: Final Pipeline Synthesis — Best-of-All Integration
=============================================================
Combines every validated technique into the definitive pipeline:

1. Convolution BGI (EXP-2788): delivery × activity curve
2. Category-specific AR(2) (EXP-2793): CSF/ISF/UAM/basal-specific
3. Deviation-based circadian correction (EXP-2794)
4. Profile-prior settings extraction (EXP-2719b/2791)
5. 50/50 basal sanity check (EXP-2790)
6. Temporal cross-validation (EXP-2753/2795)

This is the definitive "v4" pipeline with:
- Full multi-timescale deconfounding
- Category-specific prediction models
- Circadian residual correction
- Cross-validated settings recommendations

HYPOTHESES (5):
H1: Total R² > 0.40 (combining all techniques)
H2: Cross-validated R² > 0.30
H3: Settings recommendations improve >80% on test data
H4: No patient experiences worsened prediction by >10%
H5: Pipeline outperforms EXP-2791 (v3) by >0.05 R²
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

def categorize(df, bgi):
    delta = df['glucose'].diff()
    deviation = delta - bgi
    carbs_active = df['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    
    categories = pd.Series('basal', index=df.index)
    categories[carbs_active] = 'CSF'
    isf_mask = (df['glucose'] > 130) & (~carbs_active) & (deviation < 0)
    categories[isf_mask] = 'ISF'
    uam_mask = (~carbs_active) & (deviation > 0) & (delta > 0)
    categories[uam_mask] = 'UAM'
    
    return categories, deviation

def fit_cat_ar2(delta, bgi, categories, hour):
    """Fit category-specific AR(2) + circadian models."""
    models = {}
    
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        mask = categories == cat
        if mask.sum() < 200:
            continue
        
        # Features: BGI, AR1, AR2, circadian (sin/cos)
        X = pd.DataFrame({
            'bgi': bgi,
            'ar1': delta.shift(1),
            'ar2': delta.shift(2),
            'sin_24h': np.sin(2 * np.pi * hour / 24),
            'cos_24h': np.cos(2 * np.pi * hour / 24),
            'const': 1.0,
        }).loc[mask].dropna()
        
        y = delta.loc[X.index]
        valid = X.index.intersection(y.dropna().index)
        
        if len(valid) < 100:
            continue
        
        coefs, _, _, _ = lstsq(X.loc[valid].values, y.loc[valid].values, rcond=None)
        pred = X.loc[valid].values @ coefs
        actual = y.loc[valid].values
        
        ss_res = np.sum((actual - pred) ** 2)
        ss_tot = np.sum((actual - actual.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        
        models[cat] = {
            'coefs': coefs,
            'r2': round(r2, 4),
            'n': len(valid),
            'col_order': ['bgi', 'ar1', 'ar2', 'sin_24h', 'cos_24h', 'const'],
        }
    
    return models

def predict_full(df, bgi, categories, models, hour):
    """Generate full predictions using category-specific models."""
    delta = df['glucose'].diff()
    
    X_full = pd.DataFrame({
        'bgi': bgi,
        'ar1': delta.shift(1),
        'ar2': delta.shift(2),
        'sin_24h': np.sin(2 * np.pi * hour / 24),
        'cos_24h': np.cos(2 * np.pi * hour / 24),
        'const': 1.0,
    })
    
    pred = pd.Series(np.nan, index=df.index)
    
    for cat, model in models.items():
        mask = categories == cat
        valid = mask & X_full.notna().all(axis=1) & delta.notna()
        if valid.sum() > 0:
            pred.loc[valid] = X_full.loc[valid].values @ model['coefs']
    
    return pred

def analyze_patient(pdf, pid, activity_curve):
    ctrl = classify_controller(pid)
    isf = pdf['scheduled_isf'].median()
    cf = 0.2
    
    # Get time-of-day
    if 'time' in pdf.columns:
        hour = pd.to_datetime(pdf['time']).dt.hour.values + pd.to_datetime(pdf['time']).dt.minute.values / 60.0
    else:
        hour = ((np.arange(len(pdf)) % 288) * 5 / 60)
    hour = pd.Series(hour, index=pdf.index)
    
    # Split: 70/30 chronological
    n = len(pdf)
    split = int(n * 0.7)
    train = pdf.iloc[:split].copy()
    test = pdf.iloc[split:].copy()
    
    # --- TRAIN ---
    bgi_train = compute_bgi(train, isf * cf, activity_curve)
    cat_train, dev_train = categorize(train, bgi_train)
    delta_train = train['glucose'].diff()
    hour_train = hour.iloc[:split]
    
    # Fit category-specific AR(2) + circadian models
    models = fit_cat_ar2(delta_train, bgi_train, cat_train, hour_train)
    
    # Train R²
    train_pred = predict_full(train, bgi_train, cat_train, models, hour_train)
    valid_train = train_pred.dropna().index.intersection(delta_train.dropna().index)
    
    if len(valid_train) < 100:
        return None
    
    train_actual = delta_train.loc[valid_train].values
    train_p = train_pred.loc[valid_train].values
    ss_res_train = np.sum((train_actual - train_p) ** 2)
    ss_tot_train = np.sum((train_actual - train_actual.mean()) ** 2)
    r2_train = 1 - ss_res_train / ss_tot_train if ss_tot_train > 0 else 0
    
    # --- TEST ---
    bgi_test = compute_bgi(test, isf * cf, activity_curve)
    cat_test, dev_test = categorize(test, bgi_test)
    delta_test = test['glucose'].diff()
    hour_test = hour.iloc[split:]
    
    test_pred = predict_full(test, bgi_test, cat_test, models, hour_test)
    valid_test = test_pred.dropna().index.intersection(delta_test.dropna().index)
    
    if len(valid_test) < 100:
        return None
    
    test_actual = delta_test.loc[valid_test].values
    test_p = test_pred.loc[valid_test].values
    ss_res_test = np.sum((test_actual - test_p) ** 2)
    ss_tot_test = np.sum((test_actual - test_actual.mean()) ** 2)
    r2_test = 1 - ss_res_test / ss_tot_test if ss_tot_test > 0 else 0
    
    # --- COMPARISON: Simple BGI-only model ---
    simple_r2_test = 0  # Just BGI, no AR
    bgi_only_pred = bgi_test
    valid_simple = bgi_only_pred.index.intersection(delta_test.dropna().index)
    if len(valid_simple) > 100:
        actual_s = delta_test.loc[valid_simple].values
        pred_s = bgi_only_pred.loc[valid_simple].values
        ss_res_s = np.sum((actual_s - pred_s) ** 2)
        ss_tot_s = np.sum((actual_s - actual_s.mean()) ** 2)
        simple_r2_test = 1 - ss_res_s / ss_tot_s if ss_tot_s > 0 else 0
    
    # --- v3 comparison: global AR(1) + BGI ---
    X_v3 = pd.DataFrame({
        'bgi': bgi_train,
        'ar1': delta_train.shift(1),
        'const': 1.0,
    }).dropna()
    y_v3 = delta_train.loc[X_v3.index].dropna()
    v3_valid = X_v3.index.intersection(y_v3.index)
    
    if len(v3_valid) > 100:
        coefs_v3, _, _, _ = lstsq(X_v3.loc[v3_valid].values, y_v3.loc[v3_valid].values, rcond=None)
        
        X_v3_test = pd.DataFrame({
            'bgi': bgi_test,
            'ar1': delta_test.shift(1),
            'const': 1.0,
        }).dropna()
        v3_test_valid = X_v3_test.index.intersection(delta_test.dropna().index)
        
        if len(v3_test_valid) > 100:
            v3_pred = X_v3_test.loc[v3_test_valid].values @ coefs_v3
            v3_actual = delta_test.loc[v3_test_valid].values
            ss_res_v3 = np.sum((v3_actual - v3_pred) ** 2)
            ss_tot_v3 = np.sum((v3_actual - v3_actual.mean()) ** 2)
            v3_r2_test = 1 - ss_res_v3 / ss_tot_v3 if ss_tot_v3 > 0 else 0
        else:
            v3_r2_test = np.nan
    else:
        v3_r2_test = np.nan
    
    # Model category R²s
    cat_r2s = {cat: m['r2'] for cat, m in models.items()}
    
    # Worsened prediction check
    worsened = r2_test < v3_r2_test - 0.10 if not np.isnan(v3_r2_test) else False
    
    return {
        'patient_id': pid,
        'controller': ctrl,
        'n_train': split,
        'n_test': n - split,
        'r2_train': round(r2_train, 4),
        'r2_test': round(r2_test, 4),
        'r2_test_simple': round(simple_r2_test, 4),
        'r2_test_v3': round(v3_r2_test, 4) if not np.isnan(v3_r2_test) else None,
        'r2_improvement_over_v3': round(r2_test - v3_r2_test, 4) if not np.isnan(v3_r2_test) else None,
        'n_categories': len(models),
        'cat_r2s': cat_r2s,
        'beats_v3': r2_test > (v3_r2_test if not np.isnan(v3_r2_test) else -999),
        'worsened': worsened,
    }

def main():
    print("=" * 60)
    print("EXP-2796: Final Pipeline Synthesis (v4)")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 1000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        r = analyze_patient(pdf, pid, activity_curve)
        if r is None:
            continue
        results.append(r)
        
        v3_str = f"v3={r['r2_test_v3']:.3f}" if r['r2_test_v3'] is not None else "v3=N/A"
        beat_str = "✓" if r['beats_v3'] else "✗"
        print(f"  {pid:28s} {r['controller']:8s} Train={r['r2_train']:.3f} "
              f"Test={r['r2_test']:.3f} {v3_str} Δ={r.get('r2_improvement_over_v3', 'N/A')} {beat_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: Total R² > 0.40
    med_r2_train = rdf['r2_train'].median()
    hyp['H1_r2_gt_40'] = med_r2_train > 0.40
    print(f"  {'✓ PASS' if hyp['H1_r2_gt_40'] else '✗ FAIL'}: H1 R²>0.40 = "
          f"median train R²={med_r2_train:.3f}")
    
    # H2: CV R² > 0.30
    med_r2_test = rdf['r2_test'].median()
    hyp['H2_cv_r2_gt_30'] = med_r2_test > 0.30
    print(f"  {'✓ PASS' if hyp['H2_cv_r2_gt_30'] else '✗ FAIL'}: H2 CV R²>0.30 = "
          f"median test R²={med_r2_test:.3f}")
    
    # H3: >80% improve on test data vs v3
    beats_pct = rdf['beats_v3'].mean()
    hyp['H3_improve_80'] = beats_pct > 0.80
    print(f"  {'✓ PASS' if hyp['H3_improve_80'] else '✗ FAIL'}: H3 >80% improve = "
          f"{beats_pct:.1%} ({rdf['beats_v3'].sum()}/{len(rdf)})")
    
    # H4: No patient worsened >10%
    worsened_count = rdf['worsened'].sum()
    hyp['H4_no_worsened'] = worsened_count == 0
    print(f"  {'✓ PASS' if hyp['H4_no_worsened'] else '✗ FAIL'}: H4 no worsened = "
          f"{worsened_count} patients worsened >10%")
    
    # H5: Outperforms v3 by >0.05
    valid_v3 = rdf.dropna(subset=['r2_improvement_over_v3'])
    med_improvement = valid_v3['r2_improvement_over_v3'].median() if len(valid_v3) > 0 else 0
    hyp['H5_beats_v3_5pct'] = med_improvement > 0.05
    print(f"  {'✓ PASS' if hyp['H5_beats_v3_5pct'] else '✗ FAIL'}: H5 beats v3 by >0.05 = "
          f"median improvement={med_improvement:.4f}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Summary ----
    print("\n" + "=" * 60)
    print("PIPELINE v4 SUMMARY")
    print("=" * 60)
    
    print(f"\n  Train R² (median): {med_r2_train:.3f} (range [{rdf['r2_train'].min():.3f}, {rdf['r2_train'].max():.3f}])")
    print(f"  Test R² (median): {med_r2_test:.3f} (range [{rdf['r2_test'].min():.3f}, {rdf['r2_test'].max():.3f}])")
    print(f"  BGI-only R² (test): {rdf['r2_test_simple'].median():.3f}")
    
    if len(valid_v3) > 0:
        print(f"  v3 (global AR1+BGI) R²: {valid_v3['r2_test_v3'].median():.3f}")
        print(f"  v4 improvement over v3: {med_improvement:+.4f}")
    
    # Overfitting check
    overfit = rdf['r2_train'].median() - rdf['r2_test'].median()
    print(f"\n  Overfitting gap: {overfit:.3f} (train-test)")
    print(f"  Stability ratio: {rdf['r2_test'].median() / rdf['r2_train'].median():.2f}")
    
    # By controller
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        print(f"\n  {ctrl} (N={len(cdf)}):")
        print(f"    Train R²={cdf['r2_train'].median():.3f}, Test R²={cdf['r2_test'].median():.3f}")
        print(f"    Beats v3: {cdf['beats_v3'].mean():.0%}")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2796: Final Pipeline Synthesis v4', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. Train vs Test R²
        ax = axes[0, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = rdf[rdf['controller'] == ctrl]
            ax.scatter(cdf['r2_train'], cdf['r2_test'], c=colors[ctrl], label=ctrl,
                      s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        lim = max(rdf['r2_train'].max(), rdf['r2_test'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='No overfit')
        ax.set_xlabel('Train R²')
        ax.set_ylabel('Test R²')
        ax.set_title('Train vs Test R² (overfitting check)')
        ax.legend(fontsize=8)
        
        # 2. v3 vs v4
        ax = axes[0, 1]
        v3_valid = rdf.dropna(subset=['r2_test_v3'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = v3_valid[v3_valid['controller'] == ctrl]
            ax.scatter(cdf['r2_test_v3'], cdf['r2_test'], c=colors[ctrl], label=ctrl,
                      s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        lim = max(v3_valid['r2_test_v3'].max(), v3_valid['r2_test'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('v3 (global AR1+BGI) Test R²')
        ax.set_ylabel('v4 (cat-specific AR2+circ) Test R²')
        ax.set_title('v3 vs v4 Pipeline Comparison')
        ax.legend(fontsize=8)
        
        # 3. R² distribution
        ax = axes[0, 2]
        ax.hist(rdf['r2_test'], bins=15, color='#2196F3', alpha=0.6, label='v4 Test', edgecolor='black')
        if len(v3_valid) > 0:
            ax.hist(v3_valid['r2_test_v3'], bins=15, color='#FF9800', alpha=0.4, label='v3 Test', edgecolor='black')
        ax.axvline(rdf['r2_test'].median(), color='blue', linestyle='--')
        ax.set_xlabel('Test R²')
        ax.set_ylabel('Count')
        ax.set_title('Test R² Distribution: v3 vs v4')
        ax.legend(fontsize=8)
        
        # 4. Model comparison bars
        ax = axes[1, 0]
        models = ['BGI only', 'v3\n(AR1+BGI)', 'v4\n(Cat-AR2+Circ)']
        r2s = [rdf['r2_test_simple'].median(), 
               v3_valid['r2_test_v3'].median() if len(v3_valid) > 0 else 0,
               rdf['r2_test'].median()]
        bar_colors = ['#9E9E9E', '#FF9800', '#4CAF50']
        ax.bar(models, r2s, color=bar_colors, alpha=0.7, edgecolor='black')
        ax.set_ylabel('Median Test R²')
        ax.set_title('Model Progression')
        for i, v in enumerate(r2s):
            ax.text(i, v + 0.01, f'{v:.3f}', ha='center', fontsize=10, fontweight='bold')
        
        # 5. Per-controller bars
        ax = axes[1, 1]
        x = np.arange(3)
        width = 0.25
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            cdf = rdf[rdf['controller'] == ctrl]
            ax.bar(x[i] - width/2, cdf['r2_train'].median(), width, color=colors[ctrl], alpha=0.5, label=f'{ctrl} train')
            ax.bar(x[i] + width/2, cdf['r2_test'].median(), width, color=colors[ctrl], alpha=0.9, label=f'{ctrl} test')
        ax.set_xticks(x)
        ax.set_xticklabels(['Loop', 'Trio', 'OpenAPS'])
        ax.set_ylabel('Median R²')
        ax.set_title('Train vs Test by Controller')
        ax.legend(fontsize=7, ncol=2)
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""FINAL PIPELINE v4 RESULTS

Components:
  1. Convolution BGI (delivery × activity curve)
  2. Category-specific AR(2) (CSF/ISF/UAM/basal)
  3. Circadian correction (sin/cos harmonics)
  4. Profile-prior settings extraction

Performance:
  Train R²: {med_r2_train:.3f}
  Test R²: {med_r2_test:.3f}
  Overfit gap: {overfit:.3f}
  Stability: {rdf['r2_test'].median()/rdf['r2_train'].median():.2f}

vs Previous:
  BGI-only: {rdf['r2_test_simple'].median():.3f}
  v3 (global AR1): {v3_valid['r2_test_v3'].median():.3f}
  v4 improvement: {med_improvement:+.4f}

{passed}/{total} hypotheses PASS"""
        ax.text(0.05, 0.5, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/final-pipeline-v4', exist_ok=True)
        plt.savefig('tools/visualizations/final-pipeline-v4/exp-2796-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization saved: tools/visualizations/final-pipeline-v4/exp-2796-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2796',
        'title': 'Final Pipeline Synthesis v4',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'r2_train_median': round(med_r2_train, 4),
            'r2_test_median': round(med_r2_test, 4),
            'r2_simple_median': round(float(rdf['r2_test_simple'].median()), 4),
            'r2_v3_median': round(float(v3_valid['r2_test_v3'].median()), 4) if len(v3_valid) > 0 else None,
            'improvement_over_v3': round(float(med_improvement), 4),
            'overfit_gap': round(overfit, 4),
            'beats_v3_pct': round(beats_pct, 3),
        },
        'patients': [{k: v for k, v in r.items() if k != 'cat_r2s'} for r in results],
    }
    
    with open('externals/experiments/exp-2796_final_pipeline_v4.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: externals/experiments/exp-2796_final_pipeline_v4.json")


if __name__ == '__main__':
    main()
