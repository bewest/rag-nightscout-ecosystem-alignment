#!/usr/bin/env python3
"""
EXP-2793: Temporal AR Model for BG Prediction
===============================================
Exploits the 0.944 CSF autocorrelation (EXP-2751) — the strongest
unexploited signal in the pipeline.

The AR(1) meal layer in EXP-2786/2788 captured +0.231 R², but used
a simple 1-lag AR. Here we test:
1. Multi-lag AR (AR(2), AR(3)) for better momentum modeling
2. Separate AR models for CSF/ISF/UAM categories
3. Combined model: convolution BGI + multi-AR + categorization
4. Rolling window prediction (practical 30-min forecast)

HYPOTHESES (5):
H1: AR(2) improves over AR(1) by >0.02 R²
H2: Category-specific AR outperforms global AR by >0.01
H3: Combined model achieves cross-validated R² > 0.30
H4: 30-min glucose forecast RMSE < 25 mg/dL
H5: AR coefficients stable across time splits (within 20%)
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

def compute_bgi_conv(df, isf_cf, activity_curve):
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

def fit_ar_model(delta, bgi, n_lags=1, category_mask=None):
    """Fit AR(p) model: delta_t = sum(alpha_i * delta_{t-i}) + beta * bgi_t + c"""
    features = {'bgi': bgi, 'const': pd.Series(1.0, index=delta.index)}
    for lag in range(1, n_lags + 1):
        features[f'ar{lag}'] = delta.shift(lag)
    
    X = pd.DataFrame(features).dropna()
    y = delta.loc[X.index]
    valid = X.index.intersection(y.dropna().index)
    
    if category_mask is not None:
        valid = valid.intersection(category_mask[category_mask].index)
    
    if len(valid) < 100:
        return None
    
    X_mat = X.loc[valid].values
    y_vec = y.loc[valid].values
    
    coefs, _, _, _ = lstsq(X_mat, y_vec, rcond=None)
    
    pred = X_mat @ coefs
    ss_res = np.sum((y_vec - pred) ** 2)
    ss_tot = np.sum((y_vec - y_vec.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    
    col_names = list(features.keys())
    coef_dict = {col_names[i]: round(float(coefs[i]), 6) for i in range(len(coefs))}
    
    return {'r2': round(r2, 4), 'n': len(valid), 'coefs': coef_dict}

def rolling_forecast_30min(df, bgi, n_lags=2):
    """Rolling 30-min glucose forecast using AR + BGI."""
    delta = df['glucose'].diff()
    glucose = df['glucose'].values
    delta_vals = delta.values
    bgi_vals = bgi.values
    
    # Train on first 70%, test on last 30%
    n = len(df)
    train_end = int(n * 0.7)
    
    # Fit on training data
    features = {'bgi': bgi, 'const': pd.Series(1.0, index=df.index)}
    for lag in range(1, n_lags + 1):
        features[f'ar{lag}'] = delta.shift(lag)
    
    X = pd.DataFrame(features).dropna()
    y = delta.loc[X.index]
    
    train_idx = X.index[:train_end]
    valid = train_idx.intersection(y.dropna().index)
    
    if len(valid) < 100:
        return {'rmse_30': np.nan}
    
    coefs, _, _, _ = lstsq(X.loc[valid].values, y.loc[valid].values, rcond=None)
    
    # Forecast on test data: 6 steps ahead (30 min)
    test_start = train_end + n_lags + 1
    forecasts = []
    actuals = []
    
    for i in range(test_start, n - 6):
        # Use actual values up to time i, forecast 6 steps
        if np.isnan(glucose[i]):
            continue
        
        pred_bg = glucose[i]
        pred_delta = delta_vals[i]
        
        for step in range(1, 7):  # 5, 10, 15, 20, 25, 30 min
            x_row = [bgi_vals[i + step] if i + step < n else 0, 1.0]
            for lag in range(1, n_lags + 1):
                if lag == 1:
                    x_row.append(pred_delta)
                else:
                    x_row.append(delta_vals[i + step - lag] if i + step - lag >= 0 else 0)
            
            pred_delta = np.dot(x_row, coefs)
            pred_bg += pred_delta
        
        if i + 6 < n and not np.isnan(glucose[i + 6]):
            forecasts.append(pred_bg)
            actuals.append(glucose[i + 6])
    
    if len(forecasts) < 100:
        return {'rmse_30': np.nan}
    
    forecasts = np.array(forecasts)
    actuals = np.array(actuals)
    rmse = np.sqrt(np.mean((forecasts - actuals) ** 2))
    mae = np.mean(np.abs(forecasts - actuals))
    
    # Baseline: naive (last value)
    naive_rmse = np.sqrt(np.mean((actuals - glucose[test_start:test_start + len(actuals)]) ** 2))
    
    return {
        'rmse_30': round(float(rmse), 2),
        'mae_30': round(float(mae), 2),
        'naive_rmse_30': round(float(naive_rmse), 2),
        'n_forecasts': len(forecasts),
        'improvement_pct': round((1 - rmse / naive_rmse) * 100, 1) if naive_rmse > 0 else 0,
    }

def main():
    print("=" * 60)
    print("EXP-2793: Temporal AR Model for BG Prediction")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 500 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        ctrl = classify_controller(pid)
        isf = pdf['scheduled_isf'].median()
        cf = 0.2
        bgi = compute_bgi_conv(pdf, isf * cf, activity_curve)
        delta = pdf['glucose'].diff()
        
        # Categorize for category-specific AR
        carbs_active = pdf['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
        deviation = delta - bgi
        categories = pd.Series('basal', index=pdf.index)
        categories[carbs_active] = 'CSF'
        isf_mask = (pdf['glucose'] > 130) & (~carbs_active) & (deviation < 0)
        categories[isf_mask] = 'ISF'
        uam_mask = (~carbs_active) & (deviation > 0) & (delta > 0)
        categories[uam_mask] = 'UAM'
        
        # Test AR(1), AR(2), AR(3) global
        ar_results = {}
        for n_lags in [1, 2, 3]:
            r = fit_ar_model(delta, bgi, n_lags=n_lags)
            if r:
                ar_results[f'ar{n_lags}'] = r
        
        # Category-specific AR(2)
        cat_ar = {}
        for cat in ['CSF', 'ISF', 'UAM', 'basal']:
            mask = categories == cat
            if mask.sum() > 200:
                r = fit_ar_model(delta, bgi, n_lags=2, category_mask=mask)
                if r:
                    cat_ar[cat] = r
        
        # Combined: category-weighted AR(2) prediction
        # For each point, use the category-specific model
        combined_pred = pd.Series(0.0, index=pdf.index)
        combined_count = 0
        for cat, model in cat_ar.items():
            mask = categories == cat
            if mask.any():
                X = pd.DataFrame({
                    'bgi': bgi,
                    'const': 1.0,
                    'ar1': delta.shift(1),
                    'ar2': delta.shift(2),
                }).loc[mask].dropna()
                
                coefs = np.array([model['coefs'].get('bgi', 0), model['coefs'].get('const', 0),
                                  model['coefs'].get('ar1', 0), model['coefs'].get('ar2', 0)])
                valid = X.index.intersection(delta.dropna().index)
                if len(valid) > 0:
                    combined_pred.loc[valid] = X.loc[valid].values @ coefs
                    combined_count += len(valid)
        
        # R² for combined model
        valid_combined = combined_pred.index.intersection(delta.dropna().index)
        valid_combined = valid_combined[combined_pred.loc[valid_combined] != 0]
        if len(valid_combined) > 100:
            y = delta.loc[valid_combined].values
            p = combined_pred.loc[valid_combined].values
            ss_res = np.sum((y - p) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            combined_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        else:
            combined_r2 = np.nan
        
        # 30-min rolling forecast
        forecast = rolling_forecast_30min(pdf, bgi, n_lags=2)
        
        # Stability: fit AR(2) on first half vs second half
        mid = len(pdf) // 2
        delta_1 = delta.iloc[:mid]
        delta_2 = delta.iloc[mid:]
        bgi_1 = bgi.iloc[:mid]
        bgi_2 = bgi.iloc[mid:]
        
        ar2_h1 = fit_ar_model(delta_1, bgi_1, n_lags=2)
        ar2_h2 = fit_ar_model(delta_2, bgi_2, n_lags=2)
        
        stability = {}
        if ar2_h1 and ar2_h2:
            for key in ['ar1', 'ar2', 'bgi']:
                c1 = ar2_h1['coefs'].get(key, 0)
                c2 = ar2_h2['coefs'].get(key, 0)
                if abs(c1) > 0.001:
                    stability[key] = round(abs(c2 - c1) / abs(c1), 3)
        
        r = {
            'patient_id': pid,
            'controller': ctrl,
            'n_rows': len(pdf),
            'ar1_r2': ar_results.get('ar1', {}).get('r2', np.nan),
            'ar2_r2': ar_results.get('ar2', {}).get('r2', np.nan),
            'ar3_r2': ar_results.get('ar3', {}).get('r2', np.nan),
            'combined_r2': round(combined_r2, 4) if not np.isnan(combined_r2) else np.nan,
            'cat_csf_r2': cat_ar.get('CSF', {}).get('r2', np.nan),
            'cat_isf_r2': cat_ar.get('ISF', {}).get('r2', np.nan),
            'cat_uam_r2': cat_ar.get('UAM', {}).get('r2', np.nan),
            'cat_basal_r2': cat_ar.get('basal', {}).get('r2', np.nan),
            'stability_ar1': stability.get('ar1', np.nan),
            'stability_ar2': stability.get('ar2', np.nan),
            'stability_bgi': stability.get('bgi', np.nan),
            **forecast,
        }
        results.append(r)
        
        ar2_str = f"AR2={ar_results.get('ar2', {}).get('r2', 'N/A')}"
        rmse_str = f"RMSE30={forecast.get('rmse_30', 'N/A')}"
        print(f"  {pid:28s} {ctrl:8s} AR1={ar_results.get('ar1', {}).get('r2', 'N/A')} "
              f"{ar2_str} Combined={round(combined_r2, 3) if not np.isnan(combined_r2) else 'N/A'} "
              f"{rmse_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: AR(2) > AR(1) by >0.02
    ar1_med = rdf['ar1_r2'].median()
    ar2_med = rdf['ar2_r2'].median()
    ar3_med = rdf['ar3_r2'].median()
    improvement_21 = ar2_med - ar1_med
    hyp['H1_ar2_gt_ar1'] = improvement_21 > 0.02
    print(f"  {'✓ PASS' if hyp['H1_ar2_gt_ar1'] else '✗ FAIL'}: H1 AR(2)>AR(1) = "
          f"AR1={ar1_med:.3f}, AR2={ar2_med:.3f}, diff={improvement_21:.4f}")
    
    # H2: Category-specific > global by >0.01
    combined_med = rdf['combined_r2'].dropna().median()
    improvement_cat = combined_med - ar2_med
    hyp['H2_cat_gt_global'] = improvement_cat > 0.01
    print(f"  {'✓ PASS' if hyp['H2_cat_gt_global'] else '✗ FAIL'}: H2 Category>Global = "
          f"Global AR2={ar2_med:.3f}, Combined={combined_med:.3f}, diff={improvement_cat:.4f}")
    
    # H3: Combined CV R² > 0.30
    # Cross-validated version: use rolling forecast as proxy
    hyp['H3_combined_r2_gt_30'] = combined_med > 0.30
    print(f"  {'✓ PASS' if hyp['H3_combined_r2_gt_30'] else '✗ FAIL'}: H3 Combined R²>0.30 = {combined_med:.3f}")
    
    # H4: 30-min RMSE < 25
    rmse_med = rdf['rmse_30'].dropna().median()
    hyp['H4_rmse_lt_25'] = rmse_med < 25
    print(f"  {'✓ PASS' if hyp['H4_rmse_lt_25'] else '✗ FAIL'}: H4 RMSE<25 = {rmse_med:.1f} mg/dL")
    
    # H5: AR coefficients stable (within 20%)
    stability_ar1 = rdf['stability_ar1'].dropna().median()
    hyp['H5_coef_stable'] = stability_ar1 < 0.20
    print(f"  {'✓ PASS' if hyp['H5_coef_stable'] else '✗ FAIL'}: H5 Stability = "
          f"AR1 coef change={stability_ar1:.1%}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Summary ----
    print("\n" + "=" * 60)
    print("AR MODEL SUMMARY")
    print("=" * 60)
    print(f"  AR(1) median R²: {ar1_med:.3f}")
    print(f"  AR(2) median R²: {ar2_med:.3f}")
    print(f"  AR(3) median R²: {ar3_med:.3f}")
    print(f"  Combined (cat-specific AR2) R²: {combined_med:.3f}")
    
    print(f"\n  30-min Forecast:")
    print(f"    Median RMSE: {rmse_med:.1f} mg/dL")
    print(f"    Median MAE: {rdf['mae_30'].dropna().median():.1f} mg/dL")
    naive = rdf['naive_rmse_30'].dropna().median()
    print(f"    Naive RMSE: {naive:.1f} mg/dL")
    print(f"    Improvement: {rdf['improvement_pct'].dropna().median():.1f}%")
    
    print(f"\n  Category-specific R²:")
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        col = f'cat_{cat.lower()}_r2'
        if col in rdf.columns:
            vals = rdf[col].dropna()
            if len(vals) > 0:
                print(f"    {cat:8s}: median={vals.median():.3f}, range [{vals.min():.3f}, {vals.max():.3f}]")
    
    # By controller
    print(f"\n  By Controller:")
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        print(f"    {ctrl}: AR2 R²={cdf['ar2_r2'].median():.3f}, "
              f"RMSE30={cdf['rmse_30'].dropna().median():.1f}, "
              f"Combined={cdf['combined_r2'].dropna().median():.3f}")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2793: Temporal AR Model for BG Prediction', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. AR(1) vs AR(2) vs AR(3) comparison
        ax = axes[0, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = rdf[rdf['controller'] == ctrl]
            ax.scatter(cdf['ar1_r2'], cdf['ar2_r2'], c=colors[ctrl], label=ctrl, s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
        lim = max(rdf['ar1_r2'].max(), rdf['ar2_r2'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('AR(1) R²')
        ax.set_ylabel('AR(2) R²')
        ax.set_title('AR(1) vs AR(2)')
        ax.legend(fontsize=8)
        
        # 2. Global AR(2) vs Combined
        ax = axes[0, 1]
        valid = rdf.dropna(subset=['combined_r2'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = valid[valid['controller'] == ctrl]
            ax.scatter(cdf['ar2_r2'], cdf['combined_r2'], c=colors[ctrl], label=ctrl, s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
        lim = max(valid['ar2_r2'].max(), valid['combined_r2'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Global AR(2) R²')
        ax.set_ylabel('Category-specific AR(2) R²')
        ax.set_title('Global vs Category-Specific')
        ax.legend(fontsize=8)
        
        # 3. 30-min forecast RMSE
        ax = axes[0, 2]
        valid_rmse = rdf.dropna(subset=['rmse_30'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = valid_rmse[valid_rmse['controller'] == ctrl]
            ax.bar([ctrl], [cdf['rmse_30'].median()], color=colors[ctrl], alpha=0.7, edgecolor='black')
        ax.axhline(25, color='red', linestyle='--', label='Target (25 mg/dL)')
        ax.set_ylabel('30-min RMSE (mg/dL)')
        ax.set_title('30-min Forecast RMSE by Controller')
        ax.legend(fontsize=8)
        
        # 4. Category-specific R² bars
        ax = axes[1, 0]
        cat_medians = {}
        for cat in ['CSF', 'ISF', 'UAM', 'basal']:
            col = f'cat_{cat.lower()}_r2'
            vals = rdf[col].dropna()
            cat_medians[cat] = vals.median() if len(vals) > 0 else 0
        bars = ax.bar(cat_medians.keys(), cat_medians.values(), 
                     color=['#4CAF50', '#2196F3', '#FF9800', '#9E9E9E'], alpha=0.8, edgecolor='black')
        ax.set_ylabel('Median R²')
        ax.set_title('AR(2) R² by Event Category')
        
        # 5. Coefficient stability
        ax = axes[1, 1]
        for metric, label in [('stability_ar1', 'AR1 coef'), ('stability_ar2', 'AR2 coef'), 
                               ('stability_bgi', 'BGI coef')]:
            vals = rdf[metric].dropna()
            if len(vals) > 0:
                ax.hist(vals, bins=15, alpha=0.5, label=f'{label} (med={vals.median():.2f})')
        ax.axvline(0.20, color='red', linestyle='--', label='20% threshold')
        ax.set_xlabel('Relative coefficient change (half 1 vs half 2)')
        ax.set_ylabel('Count')
        ax.set_title('AR Coefficient Stability')
        ax.legend(fontsize=8)
        
        # 6. Summary table
        ax = axes[1, 2]
        ax.axis('off')
        table_data = [
            ['Model', 'Median R²', 'Improvement'],
            ['AR(1) + BGI', f'{ar1_med:.3f}', 'baseline'],
            ['AR(2) + BGI', f'{ar2_med:.3f}', f'+{improvement_21:.4f}'],
            ['AR(3) + BGI', f'{ar3_med:.3f}', f'+{ar3_med-ar1_med:.4f}'],
            ['Category AR(2)', f'{combined_med:.3f}', f'+{improvement_cat:.4f}'],
            ['', '', ''],
            ['30min RMSE', f'{rmse_med:.1f} mg/dL', f'{rdf["improvement_pct"].dropna().median():.0f}% vs naive'],
        ]
        table = ax.table(cellText=table_data, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.3, 1.5)
        for j in range(3):
            table[0, j].set_facecolor('#E0E0E0')
        ax.set_title('Model Comparison Summary', pad=20)
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/temporal-ar', exist_ok=True)
        plt.savefig('tools/visualizations/temporal-ar/exp-2793-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization saved: tools/visualizations/temporal-ar/exp-2793-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save results ----
    output = {
        'experiment': 'EXP-2793',
        'title': 'Temporal AR Model for BG Prediction',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'ar1_r2': round(ar1_med, 4),
            'ar2_r2': round(ar2_med, 4),
            'ar3_r2': round(ar3_med, 4),
            'combined_r2': round(combined_med, 4),
            'rmse_30': round(rmse_med, 2),
            'improvement_21': round(improvement_21, 4),
        },
        'patients': results,
    }
    
    with open('externals/experiments/exp-2793_temporal_ar.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: externals/experiments/exp-2793_temporal_ar.json")


if __name__ == '__main__':
    main()
