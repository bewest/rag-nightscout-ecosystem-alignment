#!/usr/bin/env python3
"""
EXP-2798: Cross-Patient Transfer Learning
===========================================
Tests whether settings correction patterns transfer across patients.

If ISF is universally over-estimated, and CR corrections correlate with
controller type, can we use POPULATION-LEVEL priors to improve
per-patient settings extraction?

This has direct practical impact:
- New AID users could get better starting settings based on controller + profile
- AID authors could provide data-driven defaults
- Patients with little data benefit from population patterns

Approach:
1. Leave-one-out: for each patient, train on ALL others, predict their settings
2. Within-controller transfer: only use same-controller patients
3. Population vs individual: compare population average to per-patient optimal
4. Feature-based transfer: use profile settings as features to predict corrections

HYPOTHESES (5):
H1: Population-average ISF correction predicts individual direction >70%
H2: Within-controller transfer outperforms across-controller
H3: Profile-based regression predicts correction magnitude (R² > 0.15)
H4: Population prior + minimal individual data beats pure individual (cold-start)
H5: Controller type is a significant feature for correction prediction
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

def extract_patient_features(pdf, pid, activity_curve):
    """Extract per-patient features and correction targets."""
    ctrl = classify_controller(pid)
    isf = pdf['scheduled_isf'].median()
    cr = pdf['scheduled_cr'].median()
    basal_rate = pdf['scheduled_basal_rate'].median()
    cf = 0.2
    
    bgi = compute_bgi(pdf, isf * cf, activity_curve)
    delta = pdf['glucose'].diff()
    
    # Categorize
    carbs_active = pdf['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    
    # ISF correction: median deviation during corrections at BG > 150
    corr_mask = (pdf['glucose'] > 150) & (~carbs_active) & (delta < 0)
    isf_dev = (delta - bgi)[corr_mask].median() if corr_mask.sum() > 20 else np.nan
    
    # CR correction: median deviation during meals
    meal_mask = carbs_active & (delta > 0)
    cr_dev = (delta - bgi)[meal_mask].median() if meal_mask.sum() > 20 else np.nan
    
    # Insulin accounting
    scheduled_rate_val = basal_rate or 0
    actual_basal = np.clip(pdf['net_basal'].fillna(0) + scheduled_rate_val, 0, None) / 12.0
    bolus = pdf['bolus'].fillna(0)
    smb = pdf['bolus_smb'].fillna(0)
    tdd = (actual_basal + bolus + smb).sum() / (len(pdf) / 288)
    basal_pct = actual_basal.sum() / (actual_basal + bolus + smb).sum() if (actual_basal + bolus + smb).sum() > 0 else np.nan
    bolus_pct = bolus.sum() / (actual_basal + bolus + smb).sum() if (actual_basal + bolus + smb).sum() > 0 else np.nan
    smb_pct = smb.sum() / (actual_basal + bolus + smb).sum() if (actual_basal + bolus + smb).sum() > 0 else np.nan
    
    # BG stats
    tir = ((pdf['glucose'] >= 70) & (pdf['glucose'] <= 180)).mean()
    glucose_cv = pdf['glucose'].std() / pdf['glucose'].mean() if pdf['glucose'].mean() > 0 else np.nan
    mean_bg = pdf['glucose'].mean()
    
    # Prediction R² (v4 pipeline baseline)
    ar1 = delta.shift(1)
    ar2 = delta.shift(2)
    X = pd.DataFrame({'bgi': bgi, 'ar1': ar1, 'ar2': ar2, 'const': 1.0}).dropna()
    y = delta.loc[X.index].dropna()
    valid = X.index.intersection(y.index)
    
    if len(valid) > 200:
        coefs, _, _, _ = lstsq(X.loc[valid].values, y.loc[valid].values, rcond=None)
        pred = X.loc[valid].values @ coefs
        ss_res = np.sum((y.loc[valid].values - pred) ** 2)
        ss_tot = np.sum((y.loc[valid].values - y.loc[valid].mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    else:
        r2 = np.nan
    
    return {
        'patient_id': pid,
        'controller': ctrl,
        'isf_setting': isf,
        'cr_setting': cr,
        'basal_rate': basal_rate,
        'tdd': tdd,
        'basal_pct': basal_pct,
        'bolus_pct': bolus_pct,
        'smb_pct': smb_pct,
        'tir': tir,
        'glucose_cv': glucose_cv,
        'mean_bg': mean_bg,
        'isf_correction': isf_dev,  # target: how much ISF should change
        'cr_correction': cr_dev,    # target: how much CR should change
        'r2_baseline': r2,
        'n_rows': len(pdf),
        'n_corrections': int(corr_mask.sum()),
        'n_meals': int(meal_mask.sum()),
    }

def main():
    print("=" * 60)
    print("EXP-2798: Cross-Patient Transfer Learning")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    # Step 1: Extract features for all patients
    features = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 1000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        f = extract_patient_features(pdf, pid, activity_curve)
        features.append(f)
        print(f"  {pid:28s} {f['controller']:8s} ISF_corr={f['isf_correction']:.2f} CR_corr={f['cr_correction']:.2f}")
    
    fdf = pd.DataFrame(features)
    print(f"\nValid patients: {len(fdf)}")
    
    # ---- H1: Population average predicts individual direction ----
    print("\n" + "=" * 60)
    print("H1: Population-average ISF correction direction")
    print("=" * 60)
    
    valid_isf = fdf.dropna(subset=['isf_correction'])
    pop_mean_isf = valid_isf['isf_correction'].mean()
    pop_sign = np.sign(pop_mean_isf)
    
    direction_correct = (np.sign(valid_isf['isf_correction']) == pop_sign).mean()
    print(f"  Population mean ISF correction: {pop_mean_isf:.3f}")
    print(f"  Population direction: {'decrease' if pop_sign < 0 else 'increase'}")
    print(f"  Individual direction matches: {direction_correct:.0%} ({(np.sign(valid_isf['isf_correction']) == pop_sign).sum()}/{len(valid_isf)})")
    
    h1_pass = direction_correct > 0.70
    
    # ---- H2: Within-controller vs across-controller ----
    print("\n" + "=" * 60)
    print("H2: Within-controller transfer")
    print("=" * 60)
    
    loo_within = []
    loo_across = []
    
    for i, row in valid_isf.iterrows():
        pid = row['patient_id']
        ctrl = row['controller']
        actual = row['isf_correction']
        
        # Within-controller: mean of same controller (excluding self)
        same_ctrl = valid_isf[(valid_isf['controller'] == ctrl) & (valid_isf['patient_id'] != pid)]
        if len(same_ctrl) > 0:
            within_pred = same_ctrl['isf_correction'].mean()
            loo_within.append({'pid': pid, 'actual': actual, 'pred': within_pred, 'err': abs(actual - within_pred)})
        
        # Across-controller: mean of ALL others
        others = valid_isf[valid_isf['patient_id'] != pid]
        across_pred = others['isf_correction'].mean()
        loo_across.append({'pid': pid, 'actual': actual, 'pred': across_pred, 'err': abs(actual - across_pred)})
    
    within_df = pd.DataFrame(loo_within)
    across_df = pd.DataFrame(loo_across)
    
    within_mae = within_df['err'].mean() if len(within_df) > 0 else np.nan
    across_mae = across_df['err'].mean()
    
    print(f"  Within-controller MAE: {within_mae:.3f}")
    print(f"  Across-controller MAE: {across_mae:.3f}")
    h2_pass = within_mae < across_mae
    print(f"  Within < Across: {h2_pass}")
    
    # ---- H3: Feature-based regression ----
    print("\n" + "=" * 60)
    print("H3: Profile-based regression for ISF correction")
    print("=" * 60)
    
    feature_cols = ['isf_setting', 'cr_setting', 'basal_rate', 'tdd', 'basal_pct', 'glucose_cv', 'mean_bg']
    target = 'isf_correction'
    
    reg_df = fdf.dropna(subset=feature_cols + [target])
    
    if len(reg_df) > 10:
        X = reg_df[feature_cols].values
        X = np.column_stack([X, np.ones(len(X))])
        y = reg_df[target].values
        
        # LOO cross-validation
        loo_preds = []
        for i in range(len(reg_df)):
            X_train = np.delete(X, i, axis=0)
            y_train = np.delete(y, i)
            X_test = X[i:i+1]
            
            coefs, _, _, _ = lstsq(X_train, y_train, rcond=None)
            pred = X_test @ coefs
            loo_preds.append(pred[0])
        
        loo_preds = np.array(loo_preds)
        ss_res = np.sum((y - loo_preds) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        loo_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        
        # Direction accuracy
        dir_accuracy = (np.sign(loo_preds) == np.sign(y)).mean()
        
        print(f"  LOO R²: {loo_r2:.3f}")
        print(f"  Direction accuracy: {dir_accuracy:.0%}")
        
        # Feature importance (full model)
        coefs_full, _, _, _ = lstsq(X, y, rcond=None)
        print(f"  Feature importances:")
        for j, col in enumerate(feature_cols):
            print(f"    {col}: {coefs_full[j]:+.4f}")
    else:
        loo_r2 = 0
        dir_accuracy = 0
        print("  Insufficient data")
    
    h3_pass = loo_r2 > 0.15
    
    # ---- H4: Population prior + minimal data ----
    print("\n" + "=" * 60)
    print("H4: Cold-start — population prior + 10% data")
    print("=" * 60)
    
    cold_start_results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 2000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        ctrl = classify_controller(pid)
        isf = pdf['scheduled_isf'].median()
        cf = 0.2
        
        n = len(pdf)
        tiny = pdf.iloc[:int(n * 0.1)]   # First 10%
        full = pdf.iloc[:int(n * 0.7)]    # First 70%
        test = pdf.iloc[int(n * 0.7):]    # Last 30%
        
        # Population prior: mean ISF correction from ALL OTHER patients of same controller
        other_same = fdf[(fdf['controller'] == ctrl) & (fdf['patient_id'] != pid)]
        pop_prior = other_same['isf_correction'].mean() if len(other_same) > 0 else fdf[fdf['patient_id'] != pid]['isf_correction'].mean()
        
        # Individual from tiny sample
        bgi_tiny = compute_bgi(tiny, isf * cf, activity_curve)
        delta_tiny = tiny['glucose'].diff()
        corr_mask_tiny = (tiny['glucose'] > 150) & (tiny['carbs'].fillna(0).rolling(36, min_periods=1).sum() == 0) & (delta_tiny < 0)
        ind_tiny = (delta_tiny - bgi_tiny)[corr_mask_tiny].median() if corr_mask_tiny.sum() > 5 else np.nan
        
        # Individual from full sample
        bgi_full = compute_bgi(full, isf * cf, activity_curve)
        delta_full = full['glucose'].diff()
        corr_mask_full = (full['glucose'] > 150) & (full['carbs'].fillna(0).rolling(36, min_periods=1).sum() == 0) & (delta_full < 0)
        ind_full = (delta_full - bgi_full)[corr_mask_full].median() if corr_mask_full.sum() > 10 else np.nan
        
        # Blended: 50% pop prior + 50% individual tiny
        if not np.isnan(ind_tiny):
            blended = 0.5 * pop_prior + 0.5 * ind_tiny
        else:
            blended = pop_prior
        
        # Test: actual correction on test set
        bgi_test = compute_bgi(test, isf * cf, activity_curve)
        delta_test = test['glucose'].diff()
        corr_mask_test = (test['glucose'] > 150) & (test['carbs'].fillna(0).rolling(36, min_periods=1).sum() == 0) & (delta_test < 0)
        actual_test = (delta_test - bgi_test)[corr_mask_test].median() if corr_mask_test.sum() > 10 else np.nan
        
        if not np.isnan(actual_test) and not np.isnan(ind_full):
            cold_start_results.append({
                'pid': pid,
                'controller': ctrl,
                'pop_prior': pop_prior,
                'ind_tiny': ind_tiny if not np.isnan(ind_tiny) else None,
                'ind_full': ind_full,
                'blended': blended,
                'actual_test': actual_test,
                'err_pop': abs(actual_test - pop_prior),
                'err_ind_tiny': abs(actual_test - ind_tiny) if not np.isnan(ind_tiny) else np.nan,
                'err_ind_full': abs(actual_test - ind_full),
                'err_blended': abs(actual_test - blended),
            })
    
    csdf = pd.DataFrame(cold_start_results)
    
    if len(csdf) > 5:
        print(f"  Patients with cold-start data: {len(csdf)}")
        print(f"  MAE — Population prior: {csdf['err_pop'].mean():.3f}")
        valid_tiny = csdf.dropna(subset=['err_ind_tiny'])
        print(f"  MAE — Individual (10%): {valid_tiny['err_ind_tiny'].mean():.3f}" if len(valid_tiny) > 0 else "  Individual (10%): N/A")
        print(f"  MAE — Blended (50/50): {csdf['err_blended'].mean():.3f}")
        print(f"  MAE — Individual (70%): {csdf['err_ind_full'].mean():.3f}")
        
        # H4: blended beats pure individual tiny
        if len(valid_tiny) > 3:
            h4_pass = csdf['err_blended'].mean() < valid_tiny['err_ind_tiny'].mean()
        else:
            h4_pass = csdf['err_blended'].mean() < csdf['err_pop'].mean()
    else:
        h4_pass = False
        print("  Insufficient data")
    
    # ---- H5: Controller type as feature ----
    print("\n" + "=" * 60)
    print("H5: Controller type significance")
    print("=" * 60)
    
    valid_ctrl = fdf.dropna(subset=['isf_correction'])
    
    groups = {}
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        g = valid_ctrl[valid_ctrl['controller'] == ctrl]['isf_correction']
        if len(g) > 2:
            groups[ctrl] = g.values
            print(f"  {ctrl}: mean={g.mean():.3f}, std={g.std():.3f}, N={len(g)}")
    
    if len(groups) >= 2:
        group_vals = list(groups.values())
        f_stat, p_val = stats.f_oneway(*group_vals)
        print(f"  ANOVA F={f_stat:.2f}, p={p_val:.4f}")
        h5_pass = p_val < 0.05
    else:
        h5_pass = False
        p_val = np.nan
    
    # ---- Results ----
    hyp = {
        'H1_pop_direction': h1_pass,
        'H2_within_controller': h2_pass,
        'H3_feature_regression': h3_pass,
        'H4_cold_start': h4_pass,
        'H5_controller_significant': h5_pass,
    }
    
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    print(f"  {'✓ PASS' if h1_pass else '✗ FAIL'}: H1 Pop direction >70% = {direction_correct:.0%}")
    print(f"  {'✓ PASS' if h2_pass else '✗ FAIL'}: H2 Within-ctrl < Across-ctrl = {within_mae:.3f} vs {across_mae:.3f}")
    print(f"  {'✓ PASS' if h3_pass else '✗ FAIL'}: H3 Feature R² >0.15 = {loo_r2:.3f}")
    print(f"  {'✓ PASS' if h4_pass else '✗ FAIL'}: H4 Blended beats pure individual")
    print(f"  {'✓ PASS' if h5_pass else '✗ FAIL'}: H5 Controller significant = p={p_val:.4f}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2798: Cross-Patient Transfer Learning', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. ISF correction by controller
        ax = axes[0, 0]
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            cdf = valid_isf[valid_isf['controller'] == ctrl]
            ax.boxplot(cdf['isf_correction'].values, positions=[i],
                      widths=0.6, patch_artist=True,
                      boxprops=dict(facecolor=colors[ctrl], alpha=0.5))
        ax.axhline(0, color='black', linestyle='--', alpha=0.3)
        ax.axhline(pop_mean_isf, color='red', linestyle=':', label=f'Pop mean={pop_mean_isf:.2f}')
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(['Loop', 'Trio', 'OpenAPS'])
        ax.set_ylabel('ISF Correction (mg/dL/5min)')
        ax.set_title('ISF Corrections by Controller')
        ax.legend(fontsize=8)
        
        # 2. LOO prediction: actual vs predicted
        ax = axes[0, 1]
        if within_df is not None and len(within_df) > 0:
            ax.scatter(within_df['actual'], within_df['pred'], c='#4CAF50', label='Within-ctrl',
                      s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        ax.scatter(across_df['actual'], across_df['pred'], c='#FF9800', label='Across-ctrl',
                  s=40, alpha=0.4, edgecolors='black', linewidths=0.5)
        lims = [min(across_df['actual'].min(), across_df['pred'].min()),
                max(across_df['actual'].max(), across_df['pred'].max())]
        ax.plot(lims, lims, 'k--', alpha=0.3)
        ax.set_xlabel('Actual ISF Correction')
        ax.set_ylabel('Predicted ISF Correction')
        ax.set_title('LOO Prediction: Actual vs Predicted')
        ax.legend(fontsize=8)
        
        # 3. Feature importance
        ax = axes[0, 2]
        if loo_r2 > 0:
            imp = pd.Series(coefs_full[:-1], index=feature_cols)
            imp_abs = imp.abs().sort_values(ascending=True)
            imp_abs.plot.barh(ax=ax, color='#2196F3', alpha=0.7)
            ax.set_xlabel('|Coefficient|')
            ax.set_title(f'Feature Importance (LOO R²={loo_r2:.3f})')
        
        # 4. Cold-start comparison
        ax = axes[1, 0]
        if len(csdf) > 0:
            methods = ['Pop Prior', 'Ind 10%', 'Blended', 'Ind 70%']
            maes = [csdf['err_pop'].mean(),
                    csdf.dropna(subset=['err_ind_tiny'])['err_ind_tiny'].mean() if len(csdf.dropna(subset=['err_ind_tiny'])) > 0 else 0,
                    csdf['err_blended'].mean(),
                    csdf['err_ind_full'].mean()]
            bar_colors = ['#9E9E9E', '#FF9800', '#4CAF50', '#2196F3']
            ax.bar(methods, maes, color=bar_colors, alpha=0.7, edgecolor='black')
            ax.set_ylabel('Mean Absolute Error')
            ax.set_title('Cold-Start: How Much Data Needed?')
            for i, v in enumerate(maes):
                ax.text(i, v + 0.02, f'{v:.3f}', ha='center', fontsize=9, fontweight='bold')
        
        # 5. ISF setting vs correction
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = valid_isf[valid_isf['controller'] == ctrl]
            ax.scatter(cdf['isf_setting'], cdf['isf_correction'], c=colors[ctrl],
                      label=ctrl, s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        ax.axhline(0, color='black', linestyle='--', alpha=0.3)
        ax.set_xlabel('ISF Setting (mg/dL/U)')
        ax.set_ylabel('ISF Correction Needed')
        ax.set_title('ISF Setting vs Correction')
        ax.legend(fontsize=8)
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""CROSS-PATIENT TRANSFER LEARNING

Q: Can population patterns help individual patients?

Population Direction Accuracy: {direction_correct:.0%}
Within-Controller MAE: {within_mae:.3f}
Across-Controller MAE: {across_mae:.3f}
Feature-Based LOO R²: {loo_r2:.3f}
Controller ANOVA p: {p_val:.4f}

Cold-Start (10% data + population):
  Pop Prior MAE: {csdf['err_pop'].mean():.3f}
  Blended MAE: {csdf['err_blended'].mean():.3f}
  Full Ind MAE: {csdf['err_ind_full'].mean():.3f}

{passed}/{total} hypotheses PASS

IMPLICATION: {"Population priors useful" if h1_pass else "Individual data needed"}
for new patients."""
        ax.text(0.05, 0.5, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/cross-patient-transfer', exist_ok=True)
        plt.savefig('tools/visualizations/cross-patient-transfer/exp-2798-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization: tools/visualizations/cross-patient-transfer/exp-2798-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2798',
        'title': 'Cross-Patient Transfer Learning',
        'n_patients': len(fdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'pop_direction_accuracy': round(direction_correct, 3),
            'within_ctrl_mae': round(float(within_mae), 4),
            'across_ctrl_mae': round(float(across_mae), 4),
            'feature_loo_r2': round(float(loo_r2), 4),
            'controller_anova_p': round(float(p_val), 4) if not np.isnan(p_val) else None,
        },
        'patients': features,
        'cold_start': cold_start_results if cold_start_results else [],
    }
    
    with open('externals/experiments/exp-2798_cross_patient_transfer.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results: externals/experiments/exp-2798_cross_patient_transfer.json")


if __name__ == '__main__':
    main()
