#!/usr/bin/env python3
"""EXP-2776: Category-Stratified Settings Extraction

EXP-2774 showed data categorizes into Basal(21%), CSF(42%), UAM(5%), ISF(30%).
oref0's autotune uses these categories to tune specific settings:
  - ISF data → tune ISF (insulin sensitivity factor)
  - CSF data → tune CSF/CR (carb sensitivity/carb ratio)
  - Basal data → tune basal rates

This experiment extracts settings from category-appropriate subsets:
  1. ISF extraction from ISF-category windows only
  2. CR extraction from CSF-category windows only
  3. Basal extraction from Basal-category windows only
  4. Compare to our production pipeline (EXP-2719b, EXP-2741)

This directly mimics oref0-autotune's methodology with our regression approach.

Success criteria (3/5 to PASS):
  H1: ISF-category model has higher R² than full-data model for ISF
  H2: CSF-category model explains carb effect better (carb coef > full-data)
  H3: Basal-category model shows least confounding (smallest insulin coef abs)
  H4: Category-extracted ISF correlates with production ISF (r>0.5)
  H5: Category-stratified CR correlates with production CR (r>0.5)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2776"
TITLE = "Category-Stratified Settings Extraction"
OUT_JSON = Path("externals/experiments/exp-2776_category_settings.json")
OUT_VIS = Path("tools/visualizations/category-settings")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def categorize_oref0(patient_df):
    """Same categorization as EXP-2774."""
    df = patient_df.sort_values('time').copy()
    isf = df['scheduled_isf'].median()
    basal_rate = df['scheduled_basal_rate'].median() if 'scheduled_basal_rate' in df.columns else 0.5
    
    if pd.isna(isf) or isf <= 0:
        return None
    
    df['delta_5m'] = df['glucose'].diff()
    df['avg_delta'] = df['delta_5m'].rolling(3, min_periods=1).mean()
    
    if 'iob' not in df.columns:
        return None
    
    df['iob_change'] = df['iob'].diff()
    df['activity'] = -df['iob_change']
    df['bgi'] = -df['activity'] * isf * 0.2
    df['deviation'] = df['avg_delta'] - df['bgi']
    df['basal_bgi'] = -(basal_rate / 12.0) * isf * 0.2
    
    if 'carbs' in df.columns:
        df['recent_carbs'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    else:
        df['recent_carbs'] = 0
    
    categories = []
    uam_active = False
    absorbing = False
    
    for idx, row in df.iterrows():
        dev = row.get('deviation', 0)
        bgi = row.get('bgi', 0)
        bbgi = row.get('basal_bgi', 0)
        iob_val = row.get('iob', 0)
        avg_d = row.get('avg_delta', 0)
        cob = row.get('recent_carbs', 0)
        
        if pd.isna(dev) or pd.isna(bgi):
            categories.append('unknown')
            continue
        
        if cob > 0 or (absorbing and dev > 0):
            if cob > 0:
                absorbing = True
            elif iob_val < basal_rate / 2:
                absorbing = False
            cat = 'CSF'
        elif (iob_val > 2 * basal_rate or dev > 6 or uam_active):
            if dev > 0:
                uam_active = True
                cat = 'UAM'
            else:
                uam_active = False
                cat = 'Basal'
        elif bbgi > -4 * bgi:
            cat = 'Basal'
        elif avg_d > 0 and avg_d > -2 * bgi:
            cat = 'Basal'
        else:
            cat = 'ISF'
        
        categories.append(cat)
    
    df['category'] = categories
    
    # Add 2h window features
    steps = 24
    df['glucose_delta_2h'] = df['glucose'].shift(-steps) - df['glucose']
    df['iob_delta_2h'] = df['iob'].shift(-steps) - df['iob']
    
    df['insulin_rate'] = 0.0
    for col in ['bolus', 'bolus_smb']:
        if col in df.columns:
            df['insulin_rate'] += df[col].fillna(0)
    if 'net_basal' in df.columns:
        df['insulin_rate'] += df['net_basal'].fillna(0).clip(lower=0) / 12.0
    df['excess_insulin_2h'] = df['insulin_rate'].rolling(steps, min_periods=1).sum()
    df['insulin_absorbed_2h'] = df['excess_insulin_2h'] - df['iob_delta_2h']
    
    if 'carbs' in df.columns:
        df['carbs_window'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    else:
        df['carbs_window'] = 0
    
    df['starting_bg'] = df['glucose']
    
    return df.dropna(subset=['glucose_delta_2h', 'insulin_absorbed_2h'])

def extract_settings(df, category=None):
    """Extract ISF, CR, and basal from regression, optionally within a category."""
    if category:
        subset = df[df['category'] == category]
    else:
        subset = df
    
    if len(subset) < 100:
        return None
    
    y = subset['glucose_delta_2h'].values
    X = subset[['starting_bg', 'insulin_absorbed_2h', 'carbs_window']].values
    
    model = LinearRegression().fit(X, y)
    r2 = model.score(X, y)
    
    # Extract settings from coefficients
    # insulin coefficient = -empirical_ISF (negative because insulin lowers BG)
    empirical_isf = -model.coef_[1]  # positive value = mg/dL per U
    
    # carb coefficient = ISF/CR → CR = ISF / carb_coef
    carb_coef = model.coef_[2]
    if carb_coef > 0.01:
        empirical_cr = empirical_isf / carb_coef
    else:
        empirical_cr = np.nan
    
    # BG coefficient = regression to mean rate
    bg_coef = model.coef_[0]
    
    return {
        'n': len(subset),
        'r2': round(r2, 4),
        'empirical_isf': round(empirical_isf, 2),
        'empirical_cr': round(empirical_cr, 1) if not np.isnan(empirical_cr) else None,
        'bg_coef': round(bg_coef, 4),
        'insulin_coef': round(model.coef_[1], 2),
        'carb_coef': round(carb_coef, 4),
        'intercept': round(model.intercept_, 2),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2776: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        cat_df = categorize_oref0(pdf)
        
        if cat_df is None or len(cat_df) < 500:
            print(f"  {pid}: skipped")
            continue
        
        profile_isf = pdf['scheduled_isf'].median()
        profile_cr = pdf['scheduled_cr'].median()
        
        # Extract settings from each category
        full = extract_settings(cat_df)
        isf_cat = extract_settings(cat_df, 'ISF')
        csf_cat = extract_settings(cat_df, 'CSF')
        basal_cat = extract_settings(cat_df, 'Basal')
        
        if full is None:
            continue
        
        results[pid] = {
            'profile_isf': round(profile_isf, 1) if not pd.isna(profile_isf) else None,
            'profile_cr': round(profile_cr, 1) if not pd.isna(profile_cr) else None,
            'full_data': full,
            'isf_category': isf_cat,
            'csf_category': csf_cat,
            'basal_category': basal_cat,
        }
        
        isf_str = f"ISF: {isf_cat['empirical_isf']:.1f}" if isf_cat else "ISF: N/A"
        csf_cr = f"CR: {csf_cat['empirical_cr']:.0f}" if csf_cat and csf_cat['empirical_cr'] else "CR: N/A"
        full_isf = f"full_ISF: {full['empirical_isf']:.1f}"
        
        print(f"  {pid}: profile_ISF={profile_isf:.0f} {full_isf} {isf_str} | "
              f"profile_CR={profile_cr:.0f} {csf_cr}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n_total = len(results)
    
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n_total})")
    print(f"{'='*60}")
    
    # Compare R² across categories
    full_r2s = [r['full_data']['r2'] for r in results.values()]
    isf_r2s = [r['isf_category']['r2'] for r in results.values() if r['isf_category']]
    csf_r2s = [r['csf_category']['r2'] for r in results.values() if r['csf_category']]
    basal_r2s = [r['basal_category']['r2'] for r in results.values() if r['basal_category']]
    
    print(f"\nR² by category (median):")
    print(f"  Full data:  {np.median(full_r2s):.3f}")
    print(f"  ISF-only:   {np.median(isf_r2s):.3f} (N={len(isf_r2s)})")
    print(f"  CSF-only:   {np.median(csf_r2s):.3f} (N={len(csf_r2s)})")
    print(f"  Basal-only: {np.median(basal_r2s):.3f} (N={len(basal_r2s)})")
    
    # Compare ISF extraction
    profile_isfs = []
    full_isfs = []
    cat_isfs = []
    for r in results.values():
        if r['profile_isf'] and r['isf_category']:
            profile_isfs.append(r['profile_isf'])
            full_isfs.append(r['full_data']['empirical_isf'])
            cat_isfs.append(r['isf_category']['empirical_isf'])
    
    if len(profile_isfs) > 5:
        r_full_profile, _ = stats.pearsonr(profile_isfs, full_isfs)
        r_cat_profile, _ = stats.pearsonr(profile_isfs, cat_isfs)
        r_full_cat, _ = stats.pearsonr(full_isfs, cat_isfs)
        print(f"\nISF correlations:")
        print(f"  Profile vs Full-data:    r={r_full_profile:.3f}")
        print(f"  Profile vs ISF-category: r={r_cat_profile:.3f}")
        print(f"  Full-data vs ISF-cat:    r={r_full_cat:.3f}")
        print(f"  Median profile ISF:      {np.median(profile_isfs):.0f}")
        print(f"  Median full-data ISF:    {np.median(full_isfs):.1f}")
        print(f"  Median ISF-category ISF: {np.median(cat_isfs):.1f}")
    
    # Compare CR extraction
    profile_crs = []
    csf_crs = []
    full_crs = []
    for r in results.values():
        if r['profile_cr'] and r['csf_category'] and r['csf_category']['empirical_cr']:
            if r['full_data']['empirical_cr']:
                profile_crs.append(r['profile_cr'])
                csf_crs.append(r['csf_category']['empirical_cr'])
                full_crs.append(r['full_data']['empirical_cr'])
    
    if len(profile_crs) > 5:
        r_full_cr, _ = stats.pearsonr(profile_crs, full_crs)
        r_csf_cr, _ = stats.pearsonr(profile_crs, csf_crs)
        print(f"\nCR correlations:")
        print(f"  Profile vs Full-data: r={r_full_cr:.3f}")
        print(f"  Profile vs CSF-cat:   r={r_csf_cr:.3f}")
        print(f"  Median profile CR:    {np.median(profile_crs):.0f}")
        print(f"  Median full-data CR:  {np.median(full_crs):.0f}")
        print(f"  Median CSF-cat CR:    {np.median(csf_crs):.0f}")
    
    # Compare insulin coefficients by category
    print(f"\nInsulin coefficient by category (median):")
    full_ins = [r['full_data']['insulin_coef'] for r in results.values()]
    isf_ins = [r['isf_category']['insulin_coef'] for r in results.values() if r['isf_category']]
    csf_ins = [r['csf_category']['insulin_coef'] for r in results.values() if r['csf_category']]
    basal_ins = [r['basal_category']['insulin_coef'] for r in results.values() if r['basal_category']]
    
    print(f"  Full:  {np.median(full_ins):.1f}")
    print(f"  ISF:   {np.median(isf_ins):.1f}")
    print(f"  CSF:   {np.median(csf_ins):.1f}")
    print(f"  Basal: {np.median(basal_ins):.1f}")
    
    # Hypothesis testing
    h1 = np.median(isf_r2s) > np.median(full_r2s)
    
    csf_carbs = [r['csf_category']['carb_coef'] for r in results.values() if r['csf_category']]
    full_carbs = [r['full_data']['carb_coef'] for r in results.values()]
    h2 = np.median(csf_carbs) > np.median(full_carbs) if csf_carbs else False
    
    h3 = abs(np.median(basal_ins)) < abs(np.median(full_ins)) if basal_ins else False
    
    h4 = len(profile_isfs) > 5 and r_cat_profile > 0.5
    
    h5 = len(profile_crs) > 5 and r_csf_cr > 0.5
    
    hypotheses = {
        'H1_isf_cat_r2_better': {'pass': bool(h1), 
            'value': f"{np.median(isf_r2s):.3f} vs {np.median(full_r2s):.3f}"},
        'H2_csf_carb_coef_better': {'pass': bool(h2),
            'value': f"{np.median(csf_carbs):.4f} vs {np.median(full_carbs):.4f}" if csf_carbs else "N/A"},
        'H3_basal_least_confounded': {'pass': bool(h3),
            'value': f"|{np.median(basal_ins):.1f}| vs |{np.median(full_ins):.1f}|" if basal_ins else "N/A"},
        'H4_isf_cat_correlates_profile': {'pass': bool(h4),
            'value': f"r={r_cat_profile:.3f}" if len(profile_isfs) > 5 else "N/A"},
        'H5_cr_cat_correlates_profile': {'pass': bool(h5),
            'value': f"r={r_csf_cr:.3f}" if len(profile_crs) > 5 else "N/A"},
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
        fig.suptitle(f'EXP-2776: Category-Stratified Settings — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: ISF comparison (profile vs category-extracted)
        ax = axes[0, 0]
        if profile_isfs and cat_isfs:
            ax.scatter(profile_isfs, cat_isfs, alpha=0.6, s=50, label='ISF-category')
            ax.scatter(profile_isfs, full_isfs, alpha=0.6, s=50, marker='s', label='Full-data')
            max_val = max(max(profile_isfs), max(cat_isfs), max(full_isfs)) + 10
            ax.plot([0, max_val], [0, max_val], 'r--', alpha=0.3)
            ax.set_xlabel('Profile ISF (mg/dL/U)')
            ax.set_ylabel('Extracted ISF (mg/dL/U)')
            ax.set_title(f'ISF: Profile vs Extracted')
            ax.legend(fontsize=8)
        
        # Panel 2: R² comparison by category
        ax = axes[0, 1]
        categories = ['Full', 'ISF', 'CSF', 'Basal']
        r2_medians = [np.median(full_r2s), 
                      np.median(isf_r2s) if isf_r2s else 0,
                      np.median(csf_r2s) if csf_r2s else 0, 
                      np.median(basal_r2s) if basal_r2s else 0]
        colors = ['gray', 'green', 'orange', 'lightblue']
        bars = ax.bar(categories, r2_medians, color=colors, edgecolor='black', alpha=0.7)
        for bar, val in zip(bars, r2_medians):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                    f'{val:.3f}', ha='center', fontsize=10)
        ax.set_ylabel('Median R²')
        ax.set_title('Model Performance by Category')
        
        # Panel 3: Insulin coefficient by category
        ax = axes[1, 0]
        data_bp = [full_ins]
        labels_bp = ['Full']
        cols_bp = ['gray']
        for cat, vals, col in [('ISF', isf_ins, 'green'), ('CSF', csf_ins, 'orange'), ('Basal', basal_ins, 'lightblue')]:
            if vals:
                data_bp.append(vals)
                labels_bp.append(cat)
                cols_bp.append(col)
        bp = ax.boxplot(data_bp, patch_artist=True)
        for patch, col in zip(bp['boxes'], cols_bp):
            patch.set_facecolor(col)
            patch.set_alpha(0.6)
        ax.set_xticklabels(labels_bp)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_ylabel('Insulin Coefficient (mg/dL/U)')
        ax.set_title('Insulin Effect by Category')
        
        # Panel 4: CR comparison
        ax = axes[1, 1]
        if profile_crs and csf_crs:
            ax.scatter(profile_crs, csf_crs, alpha=0.6, s=50, label='CSF-category')
            ax.scatter(profile_crs, full_crs, alpha=0.6, s=50, marker='s', label='Full-data')
            max_cr = max(max(profile_crs), max(csf_crs) if csf_crs else 0, max(full_crs) if full_crs else 0) + 5
            ax.plot([0, max_cr], [0, max_cr], 'r--', alpha=0.3)
            ax.set_xlabel('Profile CR (g/U)')
            ax.set_ylabel('Extracted CR (g/U)')
            ax.set_title('CR: Profile vs Extracted')
            ax.legend(fontsize=8)
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2776-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2776-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save JSON
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n_total,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
