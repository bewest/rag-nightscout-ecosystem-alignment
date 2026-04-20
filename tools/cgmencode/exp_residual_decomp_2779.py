#!/usr/bin/env python3
"""EXP-2779: Category-Stratified Residual Decomposition

The bilateral model (EXP-2773) explains 41% of variance, leaving 59% residual.
oref0 categorization (EXP-2774) splits data into Basal/CSF/UAM/ISF categories.

Hypothesis: Residuals have DIFFERENT structure in each category:
  - Basal residuals: circadian EGP patterns (time-of-day structure)
  - CSF residuals: carb absorption kinetics (temporal autocorrelation)
  - ISF residuals: insulin PK curves (exponential decay pattern)
  - UAM residuals: unannounced meals (large positive spikes)

If category-specific residuals have exploitable structure, we can build
category-specific correction models to reduce the 59% residual.

Also tests: does the bilateral model R² IMPROVE when fit per-category?
If yes, that means categories separate confounding regimes.

Success criteria (3/5 to PASS):
  H1: Per-category R² is >5% better than full-model R² for at least 2 categories
  H2: Basal residuals show circadian pattern (time-of-day p<0.05)
  H3: CSF residuals show temporal autocorrelation (lag-1 r>0.3)
  H4: ISF category has strongest insulin coefficient (|coef| > other categories)
  H5: Category-specific models reduce median residual MAE by >10%
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2779"
TITLE = "Category-Stratified Residual Decomposition"
OUT_JSON = Path("externals/experiments/exp-2779_residual_decomp.json")
OUT_VIS = Path("tools/visualizations/residual-decomp")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
CF = 0.2  # correction factor from EXP-2759

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def categorize_oref0(df):
    """Apply oref0-style categorization (from EXP-2774)."""
    cats = []
    in_uam = False
    
    for _, row in df.iterrows():
        iob = row.get('iob', 0) or 0
        cob = row.get('cob', 0) or 0
        glucose = row.get('glucose', 120) or 120
        prev_glucose = row.get('prev_glucose', glucose) or glucose
        delta = glucose - prev_glucose
        
        basal_rate = row.get('scheduled_basal_rate', 0) or 0
        isf = row.get('scheduled_isf', 50) or 50
        
        # BGI estimate (insulin effect on glucose per 5min)
        bgi = -iob * isf * CF / 12.0
        avg_delta = delta
        
        # oref0 categorization logic
        if cob > 0 or (delta > 0 and avg_delta > 0 and abs(avg_delta) > abs(bgi)):
            cat = 'CSF'
            in_uam = False
        elif (iob > 2 * basal_rate / 12.0 or delta > 6) and delta > 0:
            cat = 'UAM'
            in_uam = True
        elif in_uam and delta > 0:
            cat = 'UAM'
        elif bgi > -4 * abs(bgi) or (avg_delta > 0 and avg_delta > -2 * bgi):
            cat = 'Basal'
            in_uam = False
        else:
            cat = 'ISF'
            in_uam = False
        
        cats.append(cat)
    
    return cats

def analyze_patient(patient_df, pid):
    """Analyze residuals by category for one patient."""
    df = patient_df.sort_values('time').copy()
    
    # Basic features
    profile_isf = df['scheduled_isf'].median()
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    steps = 24  # 2h window
    
    df['glucose_delta'] = df['glucose'].shift(-steps) - df['glucose']
    df['starting_bg'] = df['glucose']
    df['prev_glucose'] = df['glucose'].shift(1)
    
    # Insulin features
    df['bolus_2h'] = df['bolus'].fillna(0).rolling(steps, min_periods=1).sum()
    smb_col = df['bolus_smb'].fillna(0) if 'bolus_smb' in df.columns else pd.Series(0, index=df.index)
    df['smb_2h'] = smb_col.rolling(steps, min_periods=1).sum()
    nb = df['net_basal'].fillna(0) / 12.0 if 'net_basal' in df.columns else pd.Series(0, index=df.index)
    df['net_basal_2h'] = nb.rolling(steps, min_periods=1).sum()
    df['excess_insulin'] = df['bolus_2h'] + df['smb_2h'] + df['net_basal_2h']
    df['carbs_2h'] = df['carbs'].fillna(0).rolling(steps, min_periods=1).sum()
    df['hour'] = df['time'].dt.hour
    
    # Categorize
    df['category'] = categorize_oref0(df)
    
    # Drop NaN
    valid = df.dropna(subset=['glucose_delta']).copy()
    if len(valid) < 100:
        return None
    
    # --- Full model ---
    X_cols = ['starting_bg', 'excess_insulin', 'carbs_2h']
    y = valid['glucose_delta'].values
    X = valid[X_cols].fillna(0).values
    
    full_model = LinearRegression().fit(X, y)
    full_r2 = full_model.score(X, y)
    full_pred = full_model.predict(X)
    full_residuals = y - full_pred
    full_mae = np.mean(np.abs(full_residuals))
    
    valid['full_residual'] = full_residuals
    
    # --- Per-category models ---
    cat_results = {}
    cat_residual_mae = {}
    
    for cat in ['Basal', 'CSF', 'ISF', 'UAM']:
        cat_df = valid[valid['category'] == cat]
        n_cat = len(cat_df)
        
        if n_cat < 30:
            cat_results[cat] = {'n': n_cat, 'r2': None, 'insulin_coef': None}
            continue
        
        y_cat = cat_df['glucose_delta'].values
        X_cat = cat_df[X_cols].fillna(0).values
        
        cat_model = LinearRegression().fit(X_cat, y_cat)
        cat_r2 = cat_model.score(X_cat, y_cat)
        cat_pred = cat_model.predict(X_cat)
        cat_resid = y_cat - cat_pred
        cat_mae = np.mean(np.abs(cat_resid))
        
        # Full-model residual MAE for this category
        full_resid_cat = cat_df['full_residual'].values
        full_mae_cat = np.mean(np.abs(full_resid_cat))
        
        # Circadian structure in residuals (for Basal)
        if cat == 'Basal':
            hours = cat_df['hour'].values
            resid_by_hour = {}
            for h in range(24):
                mask = hours == h
                if mask.sum() > 5:
                    resid_by_hour[h] = np.mean(full_resid_cat[mask])
            circadian_range = max(resid_by_hour.values()) - min(resid_by_hour.values()) if len(resid_by_hour) > 12 else 0
            # ANOVA for hour effect
            hour_groups = [full_resid_cat[hours == h] for h in range(24) if (hours == h).sum() > 5]
            if len(hour_groups) > 12:
                f_stat, p_val = stats.f_oneway(*hour_groups)
            else:
                f_stat, p_val = 0, 1
        else:
            circadian_range = None
            f_stat, p_val = None, None
        
        # Autocorrelation (for CSF)
        if cat == 'CSF' and n_cat > 50:
            autocorr_lag1 = np.corrcoef(full_resid_cat[:-1], full_resid_cat[1:])[0, 1]
        else:
            autocorr_lag1 = None
        
        cat_results[cat] = {
            'n': n_cat,
            'pct': round(n_cat / len(valid) * 100, 1),
            'r2': round(cat_r2, 4),
            'insulin_coef': round(cat_model.coef_[1], 3),
            'carb_coef': round(cat_model.coef_[2], 3),
            'bg_coef': round(cat_model.coef_[0], 3),
            'cat_mae': round(cat_mae, 1),
            'full_mae': round(full_mae_cat, 1),
            'mae_improvement': round((full_mae_cat - cat_mae) / full_mae_cat * 100, 1) if full_mae_cat > 0 else 0,
            'circadian_range': round(circadian_range, 1) if circadian_range is not None else None,
            'circadian_p': round(p_val, 4) if p_val is not None else None,
            'autocorr_lag1': round(autocorr_lag1, 3) if autocorr_lag1 is not None else None,
        }
    
    return {
        'patient_id': pid,
        'n_total': len(valid),
        'full_r2': round(full_r2, 4),
        'full_mae': round(full_mae, 1),
        'full_insulin_coef': round(full_model.coef_[1], 3),
        'categories': cat_results,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2779: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_patient(pdf, pid)
        if r is None:
            print(f"  {pid}: skipped")
            continue
        results[pid] = r
        
        cats = r['categories']
        parts = []
        for c in ['Basal', 'CSF', 'ISF', 'UAM']:
            if c in cats and cats[c]['r2'] is not None:
                parts.append(f"{c}:{cats[c]['r2']:.2f}")
        print(f"  {pid}: full_R²={r['full_r2']:.3f} | {' '.join(parts)}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n = len(results)
    
    # Aggregate
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n})")
    print(f"{'='*60}")
    
    full_r2s = [r['full_r2'] for r in results.values()]
    print(f"\nMedian full-model R²: {np.median(full_r2s):.3f}")
    
    for cat in ['Basal', 'CSF', 'ISF', 'UAM']:
        cat_r2s = [r['categories'][cat]['r2'] for r in results.values() 
                   if cat in r['categories'] and r['categories'][cat]['r2'] is not None]
        cat_insulins = [r['categories'][cat]['insulin_coef'] for r in results.values()
                       if cat in r['categories'] and r['categories'][cat]['insulin_coef'] is not None]
        cat_maes = [r['categories'][cat]['mae_improvement'] for r in results.values()
                   if cat in r['categories'] and r['categories'][cat].get('mae_improvement') is not None]
        
        if cat_r2s:
            r2_diff = np.median(cat_r2s) - np.median(full_r2s)
            print(f"\n  {cat} (N={len(cat_r2s)}):")
            print(f"    Median R²: {np.median(cat_r2s):.3f} (Δ={r2_diff:+.3f} vs full)")
            print(f"    Median insulin coef: {np.median(cat_insulins):.2f}")
            if cat_maes:
                print(f"    Median MAE improvement: {np.median(cat_maes):.1f}%")
        
        if cat == 'Basal':
            circ_ps = [r['categories']['Basal']['circadian_p'] for r in results.values()
                      if 'Basal' in r['categories'] and r['categories']['Basal'].get('circadian_p') is not None]
            if circ_ps:
                n_sig = sum(1 for p in circ_ps if p < 0.05)
                print(f"    Circadian p<0.05: {n_sig}/{len(circ_ps)}")
        
        if cat == 'CSF':
            acs = [r['categories']['CSF']['autocorr_lag1'] for r in results.values()
                  if 'CSF' in r['categories'] and r['categories']['CSF'].get('autocorr_lag1') is not None]
            if acs:
                print(f"    Median autocorrelation lag-1: {np.median(acs):.3f}")
    
    # Hypothesis testing
    # H1: Per-category R² >5% better for ≥2 categories
    n_better = 0
    for cat in ['Basal', 'CSF', 'ISF', 'UAM']:
        cat_r2s = [r['categories'][cat]['r2'] for r in results.values()
                   if cat in r['categories'] and r['categories'][cat]['r2'] is not None]
        if cat_r2s and np.median(cat_r2s) > np.median(full_r2s) + 0.05:
            n_better += 1
    h1 = n_better >= 2
    
    # H2: Basal circadian p<0.05
    circ_ps = [r['categories']['Basal']['circadian_p'] for r in results.values()
              if 'Basal' in r['categories'] and r['categories']['Basal'].get('circadian_p') is not None]
    n_sig = sum(1 for p in circ_ps if p < 0.05) if circ_ps else 0
    h2 = n_sig > len(circ_ps) * 0.5 if circ_ps else False
    
    # H3: CSF autocorrelation >0.3
    acs = [r['categories']['CSF']['autocorr_lag1'] for r in results.values()
          if 'CSF' in r['categories'] and r['categories']['CSF'].get('autocorr_lag1') is not None]
    median_ac = np.median(acs) if acs else 0
    h3 = median_ac > 0.3
    
    # H4: ISF has strongest insulin coefficient
    cat_medians = {}
    for cat in ['Basal', 'CSF', 'ISF', 'UAM']:
        vals = [r['categories'][cat]['insulin_coef'] for r in results.values()
               if cat in r['categories'] and r['categories'][cat]['insulin_coef'] is not None]
        if vals:
            cat_medians[cat] = abs(np.median(vals))
    h4 = cat_medians.get('ISF', 0) == max(cat_medians.values()) if cat_medians else False
    
    # H5: Category-specific MAE >10% improvement
    all_mae_impr = []
    for cat in ['Basal', 'CSF', 'ISF', 'UAM']:
        vals = [r['categories'][cat]['mae_improvement'] for r in results.values()
               if cat in r['categories'] and r['categories'][cat].get('mae_improvement') is not None]
        all_mae_impr.extend(vals)
    median_mae_impr = np.median(all_mae_impr) if all_mae_impr else 0
    h5 = median_mae_impr > 10
    
    hypotheses = {
        'H1_per_cat_r2_better': {'pass': bool(h1),
            'value': f"{n_better}/4 categories >5% better"},
        'H2_basal_circadian': {'pass': bool(h2),
            'value': f"{n_sig}/{len(circ_ps)} patients p<0.05"},
        'H3_csf_autocorr': {'pass': bool(h3),
            'value': f"median lag-1 = {median_ac:.3f}"},
        'H4_isf_strongest_insulin': {'pass': bool(h4),
            'value': ', '.join(f"{c}:{v:.2f}" for c, v in sorted(cat_medians.items(), key=lambda x: -x[1]))},
        'H5_cat_mae_improvement': {'pass': bool(h5),
            'value': f"median MAE improvement = {median_mae_impr:.1f}%"},
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
        fig.suptitle(f'EXP-2779: Residual Decomposition by Category — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: R² by category
        ax = axes[0, 0]
        cats = ['Full', 'Basal', 'CSF', 'ISF', 'UAM']
        cat_r2_medians = [np.median(full_r2s)]
        for c in ['Basal', 'CSF', 'ISF', 'UAM']:
            vals = [r['categories'][c]['r2'] for r in results.values()
                   if c in r['categories'] and r['categories'][c]['r2'] is not None]
            cat_r2_medians.append(np.median(vals) if vals else 0)
        colors = ['gray', 'green', 'orange', 'steelblue', 'red']
        ax.bar(cats, cat_r2_medians, color=colors, alpha=0.7, edgecolor='black')
        for i, v in enumerate(cat_r2_medians):
            ax.text(i, v + 0.01, f'{v:.3f}', ha='center', fontsize=9)
        ax.set_ylabel('Median R²')
        ax.set_title('R² by Category (category-specific model)')
        
        # Panel 2: Insulin coefficient by category
        ax = axes[0, 1]
        cats_plot = ['Full', 'Basal', 'CSF', 'ISF', 'UAM']
        coef_medians = [np.median([r['full_insulin_coef'] for r in results.values()])]
        for c in ['Basal', 'CSF', 'ISF', 'UAM']:
            vals = [r['categories'][c]['insulin_coef'] for r in results.values()
                   if c in r['categories'] and r['categories'][c]['insulin_coef'] is not None]
            coef_medians.append(np.median(vals) if vals else 0)
        ax.bar(cats_plot, coef_medians, color=colors, alpha=0.7, edgecolor='black')
        for i, v in enumerate(coef_medians):
            ax.text(i, v - 0.3, f'{v:.2f}', ha='center', fontsize=9)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_ylabel('Median Insulin Coefficient')
        ax.set_title('Insulin Effect by Category')
        
        # Panel 3: Basal circadian residuals (aggregate)
        ax = axes[1, 0]
        hour_resids = {h: [] for h in range(24)}
        for r in results.values():
            # We don't have per-hour data in results, so show circadian p-values
            pass
        # Instead show circadian significance
        circ_data = [(r['patient_id'], r['categories']['Basal']['circadian_p']) 
                     for r in results.values()
                     if 'Basal' in r['categories'] and r['categories']['Basal'].get('circadian_p') is not None]
        if circ_data:
            circ_data.sort(key=lambda x: x[1])
            pids = [c[0][:12] for c in circ_data]
            pvals = [c[1] for c in circ_data]
            ax.barh(range(len(pvals)), [-np.log10(max(p, 1e-10)) for p in pvals], 
                    color=['red' if p < 0.05 else 'gray' for p in pvals], alpha=0.7)
            ax.axvline(x=-np.log10(0.05), color='red', linestyle='--', label='p=0.05')
            ax.set_xlabel('-log10(p)')
            ax.set_ylabel('Patient')
            ax.set_title('Basal Circadian Significance')
            ax.legend()
        
        # Panel 4: CSF autocorrelation
        ax = axes[1, 1]
        ac_data = [(r['patient_id'], r['categories']['CSF']['autocorr_lag1'])
                   for r in results.values()
                   if 'CSF' in r['categories'] and r['categories']['CSF'].get('autocorr_lag1') is not None]
        if ac_data:
            ac_data.sort(key=lambda x: x[1], reverse=True)
            pids = [a[0][:12] for a in ac_data]
            acs = [a[1] for a in ac_data]
            colors_ac = ['coral' if a > 0.3 else 'steelblue' for a in acs]
            ax.barh(range(len(acs)), acs, color=colors_ac, alpha=0.7)
            ax.axvline(x=0.3, color='red', linestyle='--', label='r=0.3 threshold')
            ax.set_xlabel('Lag-1 Autocorrelation')
            ax.set_title('CSF Residual Autocorrelation')
            ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2779-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2779-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'aggregate': {
            'median_full_r2': round(np.median(full_r2s), 4),
            'cat_r2_medians': {c: round(np.median([r['categories'][c]['r2'] for r in results.values()
                             if c in r['categories'] and r['categories'][c]['r2'] is not None]), 4)
                             for c in ['Basal', 'CSF', 'ISF', 'UAM']},
            'cat_insulin_medians': {c: round(np.median([r['categories'][c]['insulin_coef'] for r in results.values()
                                  if c in r['categories'] and r['categories'][c]['insulin_coef'] is not None]), 3)
                                  for c in ['Basal', 'CSF', 'ISF', 'UAM']},
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
