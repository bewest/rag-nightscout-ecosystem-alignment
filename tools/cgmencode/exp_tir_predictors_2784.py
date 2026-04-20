#!/usr/bin/env python3
"""EXP-2784: Predictors of Time-in-Range

From EXP-2782/2783: Controllers compensate for wrong settings (r=0.18 
between settings score and TIR). 92% basal suspension means scheduled
basal barely matters. So what DOES predict TIR?

Candidate predictors:
1. Controller type (Loop/Trio/OpenAPS)
2. Total daily dose (TDD) — overall insulin needs
3. Bolus frequency (user engagement/carb counting)
4. Carb intake patterns
5. Glucose variability (CV)
6. Time above 180 / below 70 patterns
7. Mean glucose level
8. Correction frequency (how often BG>180)
9. Meal-to-bolus timing (if detectable)
10. Settings deviation from 50/50 rule

The goal is to identify ACTIONABLE predictors — things users or AID 
authors can change to improve TIR.

Success criteria (3/5 to PASS):
  H1: Controller type explains >15% of TIR variance
  H2: User engagement (bolus frequency) correlates with TIR (r>0.3)
  H3: Glucose CV inversely predicts TIR (r<-0.5)
  H4: Multi-factor model explains >40% of TIR variance
  H5: At least one ACTIONABLE factor has significant effect (p<0.01)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2784"
TITLE = "Predictors of Time-in-Range"
OUT_JSON = Path("externals/experiments/exp-2784_tir_predictors.json")
OUT_VIS = Path("tools/visualizations/tir-predictors")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def classify_controller(pid):
    if pid in LOOP_IDS or len(pid) == 1:
        return 'Loop'
    if pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Trio'

def extract_features(patient_df, pid):
    """Extract comprehensive per-patient features."""
    df = patient_df.sort_values('time').copy()
    
    glucose = df['glucose'].dropna()
    if len(glucose) < 100:
        return None
    
    hours = len(df) * 5 / 60
    days = hours / 24
    
    # Glycemic outcomes
    tir = (glucose.between(70, 180)).mean() * 100
    below_70 = (glucose < 70).mean() * 100
    above_180 = (glucose > 180).mean() * 100
    mean_bg = glucose.mean()
    std_bg = glucose.std()
    cv_bg = std_bg / mean_bg
    
    # Insulin features
    bolus_total = df['bolus'].fillna(0).sum()
    smb_total = df['bolus_smb'].fillna(0).sum() if 'bolus_smb' in df.columns else 0
    basal_rate = df['scheduled_basal_rate'].median() or 0
    scheduled_basal_total = (basal_rate / 12.0) * len(df)
    tdd = (bolus_total + smb_total + scheduled_basal_total) / days if days > 0 else 0
    
    # User engagement
    bolus_events = (df['bolus'].fillna(0) > 0).sum()
    bolus_per_day = bolus_events / days if days > 0 else 0
    
    # Carb features
    carb_events = (df['carbs'].fillna(0) > 0).sum()
    carbs_per_day = carb_events / days if days > 0 else 0
    total_carbs_per_day = df['carbs'].fillna(0).sum() / days if days > 0 else 0
    mean_meal_size = df['carbs'][df['carbs'] > 0].mean() if carb_events > 0 else 0
    
    # Correction frequency (BG>180 episodes)
    high_events = (glucose > 180).sum()
    high_per_day = high_events * 5 / 1440 / days * 24 if days > 0 else 0  # hours per day above 180
    
    # Low frequency
    low_events = (glucose < 70).sum()
    low_per_day = low_events * 5 / 1440 / days * 24 if days > 0 else 0
    
    # Basal fraction
    basal_fraction = scheduled_basal_total / (bolus_total + smb_total + scheduled_basal_total) if (bolus_total + smb_total + scheduled_basal_total) > 0 else np.nan
    
    # Controller type
    controller = classify_controller(pid)
    ctrl_loop = 1 if controller == 'Loop' else 0
    ctrl_trio = 1 if controller == 'Trio' else 0
    ctrl_openaps = 1 if controller == 'OpenAPS' else 0
    
    # Settings
    profile_isf = df['scheduled_isf'].median() or 0
    profile_cr = df['scheduled_cr'].median() if 'scheduled_cr' in df.columns else np.nan
    
    # Weight proxy: TDD (strongly correlated with weight)
    
    return {
        'patient_id': pid,
        'controller': controller,
        'days': round(days, 1),
        
        # Outcomes
        'tir': round(tir, 1),
        'below_70': round(below_70, 1),
        'above_180': round(above_180, 1),
        'mean_bg': round(mean_bg, 1),
        'cv_bg': round(cv_bg, 3),
        
        # Insulin
        'tdd': round(tdd, 1),
        'basal_fraction': round(basal_fraction, 3) if not np.isnan(basal_fraction) else None,
        
        # Engagement
        'bolus_per_day': round(bolus_per_day, 1),
        'carbs_per_day': round(carbs_per_day, 1),
        'total_carbs_per_day': round(total_carbs_per_day, 0),
        'mean_meal_size': round(mean_meal_size, 0),
        
        # Settings
        'profile_isf': round(profile_isf, 1),
        'profile_cr': round(profile_cr, 1) if not np.isnan(profile_cr) else None,
        
        # Controller dummies
        'ctrl_loop': ctrl_loop,
        'ctrl_trio': ctrl_trio,
        'ctrl_openaps': ctrl_openaps,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2784: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    features = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        f = extract_features(pdf, pid)
        if f:
            features[pid] = f
    
    n = len(features)
    print(f"Valid patients: {n}\n")
    
    # Create dataframe
    feat_df = pd.DataFrame(features.values())
    
    # --- Univariate correlations with TIR ---
    print(f"{'='*60}")
    print(f"UNIVARIATE CORRELATIONS WITH TIR")
    print(f"{'='*60}")
    
    tir = feat_df['tir'].values
    correlations = {}
    
    predictors = ['cv_bg', 'bolus_per_day', 'carbs_per_day', 'total_carbs_per_day',
                  'mean_meal_size', 'tdd', 'basal_fraction', 'mean_bg', 'profile_isf',
                  'ctrl_trio', 'ctrl_loop']
    
    for pred in predictors:
        vals = feat_df[pred].dropna()
        if len(vals) < 10:
            continue
        tir_subset = feat_df.loc[vals.index, 'tir']
        r, p = stats.pearsonr(vals, tir_subset)
        correlations[pred] = {'r': r, 'p': p}
        sig = " ***" if p < 0.01 else " *" if p < 0.05 else ""
        print(f"  {pred:<25} r={r:+.3f}  p={p:.4f}{sig}")
    
    # Sort by absolute r
    sorted_corrs = sorted(correlations.items(), key=lambda x: -abs(x[1]['r']))
    print(f"\nTop predictors (by |r|):")
    for pred, vals in sorted_corrs[:5]:
        print(f"  {pred}: r={vals['r']:+.3f}")
    
    # --- Controller effect ---
    print(f"\n{'='*60}")
    print(f"CONTROLLER TYPE EFFECT")
    print(f"{'='*60}")
    
    ctrl_groups = {}
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        vals = feat_df[feat_df['controller'] == ctrl]['tir'].values
        ctrl_groups[ctrl] = vals
        print(f"  {ctrl}: median TIR={np.median(vals):.0f}%, N={len(vals)}")
    
    f_stat, p_anova = stats.f_oneway(*ctrl_groups.values())
    print(f"  ANOVA: F={f_stat:.2f}, p={p_anova:.4f}")
    
    # Effect size (eta-squared)
    ss_between = sum(len(g) * (np.mean(g) - np.mean(tir))**2 for g in ctrl_groups.values())
    ss_total = np.sum((tir - np.mean(tir))**2)
    eta_sq = ss_between / ss_total if ss_total > 0 else 0
    print(f"  Controller η² = {eta_sq:.3f} ({eta_sq*100:.1f}% of variance)")
    
    # --- Multi-factor model ---
    print(f"\n{'='*60}")
    print(f"MULTI-FACTOR MODEL")
    print(f"{'='*60}")
    
    # Features for regression
    reg_cols = ['ctrl_trio', 'cv_bg', 'bolus_per_day', 'total_carbs_per_day', 
                'tdd', 'mean_meal_size']
    
    reg_df = feat_df[['tir'] + reg_cols].dropna()
    
    if len(reg_df) > 10:
        y = reg_df['tir'].values
        X = reg_df[reg_cols].values
        
        model = LinearRegression().fit(X, y)
        r2 = model.score(X, y)
        
        print(f"  R² = {r2:.3f} ({r2*100:.1f}% of variance)")
        print(f"  Coefficients:")
        for col, coef in zip(reg_cols, model.coef_):
            print(f"    {col:<25} {coef:+.3f}")
        print(f"    {'intercept':<25} {model.intercept_:+.3f}")
    else:
        r2 = 0
    
    # --- Actionable vs non-actionable ---
    print(f"\n{'='*60}")
    print(f"ACTIONABLE vs NON-ACTIONABLE FACTORS")
    print(f"{'='*60}")
    
    actionable = {
        'bolus_per_day': 'Bolus frequency (engagement)',
        'total_carbs_per_day': 'Daily carb intake',
        'mean_meal_size': 'Meal size',
    }
    
    non_actionable = {
        'cv_bg': 'Glucose variability',
        'ctrl_trio': 'Using Trio',
        'mean_bg': 'Mean glucose',
    }
    
    print("\n  Actionable (user can change):")
    for key, label in actionable.items():
        if key in correlations:
            r = correlations[key]['r']
            p = correlations[key]['p']
            print(f"    {label}: r={r:+.3f}, p={p:.4f}")
    
    print("\n  Non-actionable (structural):")
    for key, label in non_actionable.items():
        if key in correlations:
            r = correlations[key]['r']
            p = correlations[key]['p']
            print(f"    {label}: r={r:+.3f}, p={p:.4f}")
    
    # --- Hypothesis testing ---
    h1 = eta_sq > 0.15
    
    bolus_r = correlations.get('bolus_per_day', {}).get('r', 0)
    h2 = abs(bolus_r) > 0.3
    
    cv_r = correlations.get('cv_bg', {}).get('r', 0)
    h3 = cv_r < -0.5
    
    h4 = r2 > 0.4
    
    # H5: Any actionable factor p<0.01
    h5 = any(correlations.get(k, {}).get('p', 1) < 0.01 for k in actionable)
    
    hypotheses = {
        'H1_controller_gt15pct': {'pass': bool(h1),
            'value': f"η²={eta_sq:.3f} ({eta_sq*100:.1f}%), p={p_anova:.4f}"},
        'H2_bolus_freq_gt03': {'pass': bool(h2),
            'value': f"r={bolus_r:.3f}"},
        'H3_cv_lt_neg05': {'pass': bool(h3),
            'value': f"r={cv_r:.3f}"},
        'H4_multifactor_gt40pct': {'pass': bool(h4),
            'value': f"R²={r2:.3f}"},
        'H5_actionable_significant': {'pass': bool(h5),
            'value': ', '.join(f"{k}:p={correlations[k]['p']:.4f}" for k in actionable if k in correlations)},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2784: Predictors of TIR — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: Correlation bar chart
        ax = axes[0, 0]
        sorted_c = sorted(correlations.items(), key=lambda x: x[1]['r'])
        names = [s[0] for s in sorted_c]
        vals = [s[1]['r'] for s in sorted_c]
        colors = ['green' if abs(v) > 0.3 else 'steelblue' if abs(v) > 0.2 else 'gray' for v in vals]
        ax.barh(range(len(names)), vals, color=colors, alpha=0.7)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.axvline(x=0, color='black', linestyle='-')
        ax.set_xlabel('Correlation with TIR')
        ax.set_title('Univariate Predictors of TIR')
        
        # Panel 2: Controller type boxplot
        ax = axes[0, 1]
        ctrl_data = []
        ctrl_labels = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = feat_df[feat_df['controller'] == ctrl]['tir'].values
            if len(vals) > 0:
                ctrl_data.append(vals)
                ctrl_labels.append(f'{ctrl}\n(N={len(vals)})')
        bp = ax.boxplot(ctrl_data, patch_artist=True)
        for patch, label in zip(bp['boxes'], ctrl_labels):
            ctrl_name = label.split('\n')[0]
            patch.set_facecolor(ctrl_colors.get(ctrl_name, 'gray'))
            patch.set_alpha(0.6)
        ax.set_xticklabels(ctrl_labels)
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'TIR by Controller (η²={eta_sq:.2f}, p={p_anova:.3f})')
        ax.axhline(y=70, color='red', linestyle='--', alpha=0.3)
        
        # Panel 3: CV vs TIR
        ax = axes[1, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = feat_df['controller'] == ctrl
            ax.scatter(feat_df[mask]['cv_bg'] * 100, feat_df[mask]['tir'],
                      label=ctrl, s=60, alpha=0.7, color=ctrl_colors[ctrl])
        ax.set_xlabel('Glucose CV (%)')
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'Glucose Variability vs TIR (r={cv_r:.2f})')
        ax.legend()
        
        # Panel 4: Bolus frequency vs TIR
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = feat_df['controller'] == ctrl
            ax.scatter(feat_df[mask]['bolus_per_day'], feat_df[mask]['tir'],
                      label=ctrl, s=60, alpha=0.7, color=ctrl_colors[ctrl])
        ax.set_xlabel('Boluses per Day')
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'User Engagement vs TIR (r={bolus_r:.2f})')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2784-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2784-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'correlations': {k: {'r': round(v['r'], 4), 'p': round(v['p'], 4)} 
                        for k, v in correlations.items()},
        'controller_effect': {
            'eta_sq': round(eta_sq, 4),
            'p_anova': round(p_anova, 4),
        },
        'multi_factor_r2': round(r2, 4),
        'per_patient': features,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
