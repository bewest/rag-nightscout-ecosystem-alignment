#!/usr/bin/env python3
"""EXP-2773: Bilateral BGI — Empirical Regression on Bounded Windows

Prior attempt: physical BGI (insulin_absorbed × ISF × CF) failed with R²<0
because CF calibration and PK approximation are too crude.

New approach: empirical regression (like oref0's autotune)
  glucose_delta_2h = b0 + b1×insulin_absorbed + b2×carbs_window + b3×starting_BG
  
This learns the ACTUAL coefficients from data, avoiding the CF problem.
b1 = empirical ISF (demand-side effect per unit insulin)
b2 = empirical carb sensitivity (supply-side per gram carbs)
b3 = regression-to-mean coefficient (supply-side homeostatic)
b0 = baseline drift (EGP/hepatic)

Then we decompose variance: how much does each factor explain?

Success criteria (3/5 to PASS):
  H1: Full model R² > 0.20 (insulin + carbs + BG baseline)
  H2: Adding carbs improves R² by >5 percentage points vs insulin-only
  H3: Insulin coefficient is NEGATIVE (as physically expected) for >80% of patients
  H4: Carb coefficient is POSITIVE for >80% of patients
  H5: Starting BG coefficient is NEGATIVE (regression to mean) for >80% of patients
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

EXP_ID = "exp-2773"
TITLE = "Bilateral BGI — Empirical Regression"
OUT_JSON = Path("externals/experiments/exp-2773_bilateral_bgi.json")
OUT_VIS = Path("tools/visualizations/bilateral-bgi")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
WINDOW_H = 2  # 2-hour bounded windows
CARB_ABSORPTION_H = 3

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def compute_features(patient_df):
    """Compute 2h window features for regression."""
    df = patient_df.sort_values('time').copy()
    steps = int(WINDOW_H * 12)
    
    # Target: glucose change over 2h
    df['glucose_delta_2h'] = df['glucose'].shift(-steps) - df['glucose']
    
    # Feature 1: Starting BG (supply-side: regression to mean)
    df['starting_bg'] = df['glucose']
    
    # Feature 2: IOB change (demand-side proxy)
    if 'iob' in df.columns:
        df['iob_delta_2h'] = df['iob'].shift(-steps) - df['iob']
    else:
        return None
    
    # Feature 3: Total excess insulin delivered in 2h window
    df['excess_insulin_rate'] = 0.0
    if 'bolus' in df.columns:
        df['excess_insulin_rate'] += df['bolus'].fillna(0)
    if 'bolus_smb' in df.columns:
        df['excess_insulin_rate'] += df['bolus_smb'].fillna(0)
    if 'net_basal' in df.columns:
        df['excess_insulin_rate'] += df['net_basal'].fillna(0) / 12.0
    df['excess_insulin_2h'] = df['excess_insulin_rate'].rolling(steps, min_periods=1).sum()
    
    # Feature 4: Insulin absorbed = delivered - ΔIOB
    df['insulin_absorbed_2h'] = df['excess_insulin_2h'] - df['iob_delta_2h']
    
    # Feature 5: Carbs in window (supply-side: meal effect)
    if 'carbs' in df.columns:
        carb_lookback = int(CARB_ABSORPTION_H * 12)
        df['carbs_window'] = df['carbs'].fillna(0).rolling(
            carb_lookback, min_periods=1).sum()
    else:
        df['carbs_window'] = 0.0
    
    # Feature 6: Starting IOB (pre-existing demand)
    df['starting_iob'] = df['iob'].fillna(0)
    
    # Hour for circadian analysis
    df['hour'] = df['time'].dt.hour
    
    return df.dropna(subset=['glucose_delta_2h', 'insulin_absorbed_2h'])

def fit_models(df):
    """Fit progressive regression models to decompose variance."""
    y = df['glucose_delta_2h'].values
    
    results = {}
    
    # Model 1: Starting BG only (supply-side homeostatic)
    X_bg = df[['starting_bg']].values
    m1 = LinearRegression().fit(X_bg, y)
    results['bg_only'] = {
        'r2': round(m1.score(X_bg, y), 4),
        'coefs': {'intercept': round(m1.intercept_, 2), 'starting_bg': round(m1.coef_[0], 4)},
    }
    
    # Model 2: Insulin absorbed only (demand-side)
    X_ins = df[['insulin_absorbed_2h']].values
    m2 = LinearRegression().fit(X_ins, y)
    results['insulin_only'] = {
        'r2': round(m2.score(X_ins, y), 4),
        'coefs': {'intercept': round(m2.intercept_, 2), 'insulin_absorbed': round(m2.coef_[0], 2)},
    }
    
    # Model 3: BG + Insulin (bilateral demand)
    X_bi = df[['starting_bg', 'insulin_absorbed_2h']].values
    m3 = LinearRegression().fit(X_bi, y)
    results['bg_insulin'] = {
        'r2': round(m3.score(X_bi, y), 4),
        'coefs': {
            'intercept': round(m3.intercept_, 2),
            'starting_bg': round(m3.coef_[0], 4),
            'insulin_absorbed': round(m3.coef_[1], 2),
        },
    }
    
    # Model 4: BG + Insulin + Carbs (full bilateral)
    X_full = df[['starting_bg', 'insulin_absorbed_2h', 'carbs_window']].values
    m4 = LinearRegression().fit(X_full, y)
    results['full_bilateral'] = {
        'r2': round(m4.score(X_full, y), 4),
        'coefs': {
            'intercept': round(m4.intercept_, 2),
            'starting_bg': round(m4.coef_[0], 4),
            'insulin_absorbed': round(m4.coef_[1], 2),
            'carbs': round(m4.coef_[2], 4),
        },
    }
    
    # Model 5: Full + IOB (kitchen sink)
    X_all = df[['starting_bg', 'insulin_absorbed_2h', 'carbs_window', 'starting_iob']].values
    m5 = LinearRegression().fit(X_all, y)
    results['full_plus_iob'] = {
        'r2': round(m5.score(X_all, y), 4),
        'coefs': {
            'intercept': round(m5.intercept_, 2),
            'starting_bg': round(m5.coef_[0], 4),
            'insulin_absorbed': round(m5.coef_[1], 2),
            'carbs': round(m5.coef_[2], 4),
            'starting_iob': round(m5.coef_[3], 2),
        },
    }
    
    return results

def main():
    print(f"{'='*60}")
    print(f"EXP-2773: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    all_results = {}
    all_data = []
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        feat_df = compute_features(pdf)
        
        if feat_df is None or len(feat_df) < 200:
            print(f"  {pid}: skipped (insufficient data)")
            continue
        
        models = fit_models(feat_df)
        
        # Extract key coefficients from full bilateral model
        fb = models['full_bilateral']['coefs']
        
        all_results[pid] = {
            'n_windows': len(feat_df),
            'models': models,
            'insulin_coef_negative': fb['insulin_absorbed'] < 0,
            'carbs_coef_positive': fb['carbs'] > 0,
            'bg_coef_negative': fb['starting_bg'] < 0,
            'carb_adds_value': models['full_bilateral']['r2'] - models['bg_insulin']['r2'],
        }
        
        feat_df['patient_id'] = pid
        all_data.append(feat_df)
        
        fb_r2 = models['full_bilateral']['r2']
        bg_r2 = models['bg_only']['r2']
        ins_r2 = models['insulin_only']['r2']
        bi_r2 = models['bg_insulin']['r2']
        
        print(f"  {pid}: BG={bg_r2:.3f} Ins={ins_r2:.3f} BG+Ins={bi_r2:.3f} "
              f"Full={fb_r2:.3f} | ins_b={fb['insulin_absorbed']:.1f} "
              f"carb_b={fb['carbs']:.3f} bg_b={fb['starting_bg']:.4f}")
    
    if not all_results:
        print("ERROR: No valid results")
        sys.exit(1)
    
    all_df = pd.concat(all_data, ignore_index=True)
    n_total = len(all_results)
    
    # Aggregate metrics
    full_r2s = [r['models']['full_bilateral']['r2'] for r in all_results.values()]
    bg_r2s = [r['models']['bg_only']['r2'] for r in all_results.values()]
    bi_r2s = [r['models']['bg_insulin']['r2'] for r in all_results.values()]
    ins_r2s = [r['models']['insulin_only']['r2'] for r in all_results.values()]
    carb_adds = [r['carb_adds_value'] for r in all_results.values()]
    
    n_ins_neg = sum(1 for r in all_results.values() if r['insulin_coef_negative'])
    n_carb_pos = sum(1 for r in all_results.values() if r['carbs_coef_positive'])
    n_bg_neg = sum(1 for r in all_results.values() if r['bg_coef_negative'])
    
    print(f"\n{'='*60}")
    print(f"AGGREGATE RESULTS (N={n_total} patients)")
    print(f"{'='*60}")
    print(f"\nProgressive R² (median):")
    print(f"  Starting BG only:      {np.median(bg_r2s):.3f}")
    print(f"  Insulin absorbed only:  {np.median(ins_r2s):.3f}")
    print(f"  BG + Insulin:           {np.median(bi_r2s):.3f}")
    print(f"  BG + Insulin + Carbs:   {np.median(full_r2s):.3f}")
    print(f"\nCarb improvement:        median +{np.median(carb_adds)*100:.1f} pp")
    print(f"Insulin coef negative:   {n_ins_neg}/{n_total} ({100*n_ins_neg/n_total:.0f}%)")
    print(f"Carb coef positive:      {n_carb_pos}/{n_total} ({100*n_carb_pos/n_total:.0f}%)")
    print(f"BG coef negative:        {n_bg_neg}/{n_total} ({100*n_bg_neg/n_total:.0f}%)")
    
    # Aggregate model on all data pooled
    print(f"\n--- POOLED MODEL (all patients) ---")
    pooled = fit_models(all_df)
    for mname, mdata in pooled.items():
        print(f"  {mname}: R²={mdata['r2']:.4f}")
        for cname, cval in mdata['coefs'].items():
            print(f"    {cname}: {cval}")
    
    # Hypothesis testing
    h1 = np.median(full_r2s) > 0.20
    h2 = np.median(carb_adds) > 0.05
    h3 = n_ins_neg > n_total * 0.8
    h4 = n_carb_pos > n_total * 0.8
    h5 = n_bg_neg > n_total * 0.8
    
    hypotheses = {
        'H1_full_r2_gt20': {'pass': bool(h1), 'value': f"{np.median(full_r2s)*100:.1f}%"},
        'H2_carb_adds_5pp': {'pass': bool(h2), 'value': f"+{np.median(carb_adds)*100:.1f} pp"},
        'H3_insulin_negative_80pct': {'pass': bool(h3), 'value': f"{n_ins_neg}/{n_total}"},
        'H4_carb_positive_80pct': {'pass': bool(h4), 'value': f"{n_carb_pos}/{n_total}"},
        'H5_bg_negative_80pct': {'pass': bool(h5), 'value': f"{n_bg_neg}/{n_total}"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Key insight: variance decomposition
    print(f"\n--- VARIANCE DECOMPOSITION (median across patients) ---")
    bg_contribution = np.median(bg_r2s)
    insulin_marginal = np.median(bi_r2s) - np.median(bg_r2s)
    carb_marginal = np.median(full_r2s) - np.median(bi_r2s)
    residual = 1.0 - np.median(full_r2s)
    print(f"  Starting BG (supply homeostatic): {bg_contribution*100:.1f}%")
    print(f"  Insulin absorbed (demand):         {insulin_marginal*100:.1f}%")
    print(f"  Carbs (supply meal):               {carb_marginal*100:.1f}%")
    print(f"  Residual (unexplained):            {residual*100:.1f}%")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2773: Bilateral BGI Regression — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: Progressive R² by patient
        ax = axes[0, 0]
        sorted_pids = sorted(all_results.keys(), key=lambda p: all_results[p]['models']['full_bilateral']['r2'])
        x = np.arange(n_total)
        ax.bar(x, [all_results[p]['models']['bg_only']['r2'] for p in sorted_pids], 
               label='BG only', alpha=0.5, color='gold')
        ax.bar(x, [all_results[p]['models']['bg_insulin']['r2'] for p in sorted_pids],
               label='+ Insulin', alpha=0.5, color='steelblue')
        ax.bar(x, [all_results[p]['models']['full_bilateral']['r2'] for p in sorted_pids],
               label='+ Carbs', alpha=0.5, color='coral')
        ax.set_xlabel('Patient (sorted)')
        ax.set_ylabel('R²')
        ax.set_title('Progressive Model R²')
        ax.legend(fontsize=8)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.set_xticks([])
        
        # Panel 2: Coefficient signs
        ax = axes[0, 1]
        ins_coefs = [all_results[p]['models']['full_bilateral']['coefs']['insulin_absorbed'] for p in all_results]
        carb_coefs = [all_results[p]['models']['full_bilateral']['coefs']['carbs'] for p in all_results]
        ax.scatter(ins_coefs, carb_coefs, alpha=0.6, s=50)
        ax.axhline(y=0, color='gray', linestyle='--')
        ax.axvline(x=0, color='gray', linestyle='--')
        ax.set_xlabel('Insulin coefficient (expected < 0)')
        ax.set_ylabel('Carb coefficient (expected > 0)')
        ax.set_title(f'Coefficient Signs ({n_ins_neg}/{n_total} insulin neg, {n_carb_pos}/{n_total} carb pos)')
        # Highlight quadrant
        ax.fill_between([min(ins_coefs)-1, 0], [0]*2, [max(carb_coefs)+1]*2, 
                        alpha=0.1, color='green', label='Expected quadrant')
        ax.legend(fontsize=8)
        
        # Panel 3: Variance decomposition (stacked bar)
        ax = axes[1, 0]
        categories = ['BG\n(homeostatic)', 'Insulin\n(demand)', 'Carbs\n(meal)', 'Residual']
        values = [bg_contribution*100, insulin_marginal*100, carb_marginal*100, residual*100]
        colors = ['gold', 'steelblue', 'coral', 'lightgray']
        bars = ax.bar(categories, values, color=colors, edgecolor='black')
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{val:.1f}%', ha='center', fontsize=10)
        ax.set_ylabel('Variance Explained (%)')
        ax.set_title('2h Glucose Change Decomposition')
        ax.set_ylim(bottom=min(0, min(values)-5))
        
        # Panel 4: Carb marginal value distribution  
        ax = axes[1, 1]
        ax.hist([c*100 for c in carb_adds], bins=20, color='coral', edgecolor='black', alpha=0.7)
        ax.axvline(x=0, color='red', linestyle='--', linewidth=2)
        ax.axvline(x=np.median(carb_adds)*100, color='blue', linestyle='-', linewidth=2, 
                   label=f'Median: {np.median(carb_adds)*100:+.1f} pp')
        ax.set_xlabel('R² improvement from adding carbs (pp)')
        ax.set_ylabel('Patients')
        ax.set_title('Marginal Value of Carb Data')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2773-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2773-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save JSON
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n_total,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'aggregate': {
            'median_r2_bg_only': round(np.median(bg_r2s), 4),
            'median_r2_insulin_only': round(np.median(ins_r2s), 4),
            'median_r2_bg_insulin': round(np.median(bi_r2s), 4),
            'median_r2_full_bilateral': round(np.median(full_r2s), 4),
            'median_carb_marginal': round(np.median(carb_adds), 4),
            'n_insulin_negative': n_ins_neg,
            'n_carb_positive': n_carb_pos,
            'n_bg_negative': n_bg_neg,
            'variance_decomposition': {
                'starting_bg_pct': round(bg_contribution * 100, 1),
                'insulin_pct': round(insulin_marginal * 100, 1),
                'carbs_pct': round(carb_marginal * 100, 1),
                'residual_pct': round(residual * 100, 1),
            },
        },
        'pooled_model': pooled,
        'per_patient': {pid: {k: v for k, v in r.items() if k != 'n_windows'} 
                        for pid, r in all_results.items()},
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()

if __name__ == '__main__':
    main()
