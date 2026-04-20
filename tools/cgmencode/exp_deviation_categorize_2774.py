#!/usr/bin/env python3
"""EXP-2774: oref0-Style Deviation Categorization

Implements oref0's categorize.js logic on our 5-min grid data.
Each data point is categorized into one of 4 buckets:

  CSF  - Carb absorption period (COB > 0 or positive deviation after meal)
  UAM  - Unannounced meal (IOB > 2×basal_rate AND positive deviation, no COB)
  ISF  - Insulin sensitivity (BGI dominates, BG falling from insulin)
  Basal - Baseline (scheduled basal dominates, low insulin activity)

Key oref0 rules (from categorize.js:299-365):
  - deviation = avgDelta - BGI (actual change minus insulin-predicted)
  - If COB>0 or absorbing: CSF
  - Elif IOB>2×basal OR deviation>6 or uam continuation: UAM
  - Elif basalBGI > -4×BGI: Basal (scheduled basal dominates)
  - Elif avgDelta > 0 and avgDelta > -2×BGI: Basal (unexplained rise)
  - Else: ISF (insulin acting dominates)

Then we analyze: what fraction of time is each category? 
How does the EXP-2773 regression model perform within each category?

Success criteria (3/5 to PASS):
  H1: >50% of data points are categorized as Basal (between meals)
  H2: CSF + UAM combined account for >15% (meal-related deviations exist)
  H3: ISF category shows the strongest insulin coefficient (<-5 mg/dL/U)
  H4: Basal category regression R² > full-data R² (less confounding when quiet)
  H5: Category distribution is consistent across controller types (p>0.05)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

EXP_ID = "exp-2774"
TITLE = "oref0-Style Deviation Categorization"
OUT_JSON = Path("externals/experiments/exp-2774_deviation_categorize.json")
OUT_VIS = Path("tools/visualizations/deviation-categorize")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def categorize_oref0(patient_df):
    """Categorize each 5-min data point using oref0 logic."""
    df = patient_df.sort_values('time').copy()
    
    # Basic calculations
    isf = df['scheduled_isf'].median()
    cr = df['scheduled_cr'].median()
    basal_rate = df['scheduled_basal_rate'].median() if 'scheduled_basal_rate' in df.columns else 0.5
    
    if pd.isna(isf) or isf <= 0:
        return None
    
    # avgDelta: average BG change over 15min (3 readings)
    df['delta_5m'] = df['glucose'].diff()
    df['avg_delta'] = df['delta_5m'].rolling(3, min_periods=1).mean()
    
    # BGI from IOB activity: BGI = -activity × ISF × 5min
    # We approximate activity from IOB change per 5min
    if 'iob' in df.columns:
        df['iob_change'] = df['iob'].diff()
        # Activity ≈ -IOB_change (when IOB decreases, activity is positive)
        df['activity'] = -df['iob_change']
        # Use CF=0.2 for BGI calculation (from EXP-2759)
        df['bgi'] = -df['activity'] * isf * 0.2
    else:
        return None
    
    # Deviation = avgDelta - BGI (what's NOT explained by insulin)
    df['deviation'] = df['avg_delta'] - df['bgi']
    
    # basalBGI: the BGI that would come from scheduled basal alone
    # basal_rate U/hr → basal_rate/12 U per 5min → activity ≈ rate/12/DIA_hours
    # Simplified: basalBGI ≈ -basal_rate/12 × ISF × 0.2
    df['basal_bgi'] = -(basal_rate / 12.0) * isf * 0.2
    
    # COB estimate: rolling 3h sum of carbs (simplified — no decay model)
    if 'carbs' in df.columns:
        df['recent_carbs'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()  # 3h
    else:
        df['recent_carbs'] = 0
    
    # Categorize each row
    categories = []
    uam_active = False
    absorbing = False
    last_type = 'basal'
    
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
        
        # Rule 1: CSF — during carb absorption
        if cob > 0 or (absorbing and dev > 0):
            if cob > 0:
                absorbing = True
            elif iob_val < basal_rate / 2:
                absorbing = False
            cat = 'CSF'
            last_type = 'csf'
        
        # Rule 2: UAM — unannounced meal
        elif (iob_val > 2 * basal_rate or dev > 6 or uam_active):
            if dev > 0:
                uam_active = True
                cat = 'UAM'
            else:
                uam_active = False
                cat = 'Basal'  # UAM ended
            last_type = 'uam' if cat == 'UAM' else 'basal'
        
        # Rule 3: Basal vs ISF
        elif bbgi > -4 * bgi:
            cat = 'Basal'
            last_type = 'basal'
        elif avg_d > 0 and avg_d > -2 * bgi:
            cat = 'Basal'  # unexplained rise
            last_type = 'basal'
        else:
            cat = 'ISF'
            last_type = 'isf'
        
        categories.append(cat)
    
    df['category'] = categories
    
    # Add features for regression (same as EXP-2773)
    steps = 24  # 2h
    df['glucose_delta_2h'] = df['glucose'].shift(-steps) - df['glucose']
    
    # Insulin absorbed
    df['iob_delta_2h'] = df['iob'].shift(-steps) - df['iob']
    df['insulin_rate'] = 0.0
    for col in ['bolus', 'bolus_smb']:
        if col in df.columns:
            df['insulin_rate'] += df[col].fillna(0)
    if 'net_basal' in df.columns:
        df['insulin_rate'] += df['net_basal'].fillna(0).clip(lower=0) / 12.0
    df['excess_insulin_2h'] = df['insulin_rate'].rolling(steps, min_periods=1).sum()
    df['insulin_absorbed_2h'] = df['excess_insulin_2h'] - df['iob_delta_2h']
    
    # Carbs
    if 'carbs' in df.columns:
        df['carbs_window'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    else:
        df['carbs_window'] = 0
    
    df['starting_bg'] = df['glucose']
    df['hour'] = df['time'].dt.hour
    
    return df.dropna(subset=['glucose_delta_2h', 'insulin_absorbed_2h', 'deviation'])

def fit_category_model(df):
    """Fit regression within a category."""
    if len(df) < 50:
        return None
    
    y = df['glucose_delta_2h'].values
    X = df[['starting_bg', 'insulin_absorbed_2h', 'carbs_window']].values
    
    model = LinearRegression().fit(X, y)
    return {
        'r2': round(model.score(X, y), 4),
        'n': len(df),
        'coefs': {
            'intercept': round(model.intercept_, 2),
            'starting_bg': round(model.coef_[0], 4),
            'insulin_absorbed': round(model.coef_[1], 2),
            'carbs': round(model.coef_[2], 4),
        }
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2774: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    all_results = {}
    all_data = []
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        cat_df = categorize_oref0(pdf)
        
        if cat_df is None or len(cat_df) < 200:
            print(f"  {pid}: skipped")
            continue
        
        # Category distribution
        cat_counts = cat_df['category'].value_counts()
        total = len(cat_df)
        dist = {c: round(cat_counts.get(c, 0) / total * 100, 1) for c in ['Basal', 'CSF', 'UAM', 'ISF', 'unknown']}
        
        # Regression within each category
        cat_models = {}
        for cat in ['Basal', 'CSF', 'UAM', 'ISF']:
            subset = cat_df[cat_df['category'] == cat]
            if len(subset) >= 50:
                cat_models[cat] = fit_category_model(subset)
        
        # Full model for comparison
        full_model = fit_category_model(cat_df)
        
        all_results[pid] = {
            'n_total': total,
            'distribution': dist,
            'category_models': cat_models,
            'full_model': full_model,
        }
        
        cat_df['patient_id'] = pid
        all_data.append(cat_df)
        
        print(f"  {pid}: Basal={dist.get('Basal',0)}% CSF={dist.get('CSF',0)}% "
              f"UAM={dist.get('UAM',0)}% ISF={dist.get('ISF',0)}%"
              f" | Full R²={full_model['r2']:.3f}" if full_model else "")
    
    if not all_results:
        print("ERROR: No results")
        sys.exit(1)
    
    all_df = pd.concat(all_data, ignore_index=True)
    n_total = len(all_results)
    
    # Aggregate distributions
    basal_pcts = [r['distribution'].get('Basal', 0) for r in all_results.values()]
    csf_pcts = [r['distribution'].get('CSF', 0) for r in all_results.values()]
    uam_pcts = [r['distribution'].get('UAM', 0) for r in all_results.values()]
    isf_pcts = [r['distribution'].get('ISF', 0) for r in all_results.values()]
    meal_pcts = [c + u for c, u in zip(csf_pcts, uam_pcts)]
    
    print(f"\n{'='*60}")
    print(f"AGGREGATE RESULTS (N={n_total})")
    print(f"{'='*60}")
    print(f"\nCategory Distribution (median):")
    print(f"  Basal:  {np.median(basal_pcts):.1f}%")
    print(f"  CSF:    {np.median(csf_pcts):.1f}%")
    print(f"  UAM:    {np.median(uam_pcts):.1f}%")
    print(f"  ISF:    {np.median(isf_pcts):.1f}%")
    print(f"  Meal (CSF+UAM): {np.median(meal_pcts):.1f}%")
    
    # Pooled category models
    print(f"\n--- POOLED CATEGORY MODELS ---")
    for cat in ['Basal', 'CSF', 'UAM', 'ISF']:
        subset = all_df[all_df['category'] == cat]
        model = fit_category_model(subset)
        if model:
            print(f"  {cat} (N={model['n']}): R²={model['r2']:.4f}")
            print(f"    insulin_b={model['coefs']['insulin_absorbed']:.1f} "
                  f"carb_b={model['coefs']['carbs']:.4f} "
                  f"bg_b={model['coefs']['starting_bg']:.4f}")
    
    # Full pooled
    full_pooled = fit_category_model(all_df)
    print(f"  ALL (N={full_pooled['n']}): R²={full_pooled['r2']:.4f}")
    
    # Hypothesis testing
    # H1: >50% Basal
    h1 = np.median(basal_pcts) > 50
    
    # H2: CSF+UAM > 15%
    h2 = np.median(meal_pcts) > 15
    
    # H3: ISF category has strongest insulin coefficient
    isf_ins_coefs = []
    for r in all_results.values():
        if 'ISF' in r['category_models']:
            isf_ins_coefs.append(r['category_models']['ISF']['coefs']['insulin_absorbed'])
    h3 = len(isf_ins_coefs) > 0 and np.median(isf_ins_coefs) < -5
    
    # H4: Basal R² > full R²
    basal_better = 0
    for r in all_results.values():
        if 'Basal' in r['category_models'] and r['full_model']:
            if r['category_models']['Basal']['r2'] > r['full_model']['r2']:
                basal_better += 1
    h4 = basal_better > n_total * 0.5
    
    # H5: Category distribution consistent across controllers
    # Compare Loop (a-k) vs Trio (ns-*) vs OpenAPS (odc-*)
    loop_basal = [r['distribution'].get('Basal', 0) for pid, r in all_results.items() 
                  if pid in 'abcdefgik']
    trio_basal = [r['distribution'].get('Basal', 0) for pid, r in all_results.items()
                  if pid.startswith('ns-')]
    oaps_basal = [r['distribution'].get('Basal', 0) for pid, r in all_results.items()
                  if pid.startswith('odc-')]
    
    # Simple consistency check: max group median differs by <20 percentage points
    group_medians = []
    if loop_basal: group_medians.append(np.median(loop_basal))
    if trio_basal: group_medians.append(np.median(trio_basal))
    if oaps_basal: group_medians.append(np.median(oaps_basal))
    h5 = len(group_medians) >= 2 and (max(group_medians) - min(group_medians)) < 20
    
    hypotheses = {
        'H1_basal_gt50pct': {'pass': bool(h1), 'value': f"{np.median(basal_pcts):.1f}%"},
        'H2_meal_gt15pct': {'pass': bool(h2), 'value': f"{np.median(meal_pcts):.1f}%"},
        'H3_isf_insulin_lt_neg5': {'pass': bool(h3), 
            'value': f"{np.median(isf_ins_coefs):.1f}" if isf_ins_coefs else "N/A"},
        'H4_basal_r2_better': {'pass': bool(h4), 'value': f"{basal_better}/{n_total}"},
        'H5_consistent_across_controllers': {'pass': bool(h5),
            'value': f"range={max(group_medians)-min(group_medians):.1f}pp" if len(group_medians) >= 2 else "N/A"},
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
        fig.suptitle(f'EXP-2774: Deviation Categorization — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: Category distribution by patient
        ax = axes[0, 0]
        sorted_pids = sorted(all_results.keys())
        x = np.arange(n_total)
        bottoms = np.zeros(n_total)
        for cat, color in [('Basal', 'lightblue'), ('CSF', 'orange'), 
                            ('UAM', 'red'), ('ISF', 'green')]:
            vals = [all_results[p]['distribution'].get(cat, 0) for p in sorted_pids]
            ax.bar(x, vals, bottom=bottoms, label=cat, color=color, alpha=0.8)
            bottoms += np.array(vals)
        ax.set_xlabel('Patient')
        ax.set_ylabel('% of Data Points')
        ax.set_title('Category Distribution')
        ax.legend(fontsize=8)
        ax.set_xticks([])
        
        # Panel 2: Circadian pattern by category
        ax = axes[0, 1]
        for cat, color, marker in [('Basal', 'lightblue', 'o'), ('CSF', 'orange', 's'),
                                    ('UAM', 'red', '^'), ('ISF', 'green', 'D')]:
            subset = all_df[all_df['category'] == cat]
            if len(subset) > 100:
                hourly = subset.groupby('hour')['deviation'].mean()
                ax.plot(hourly.index, hourly.values, f'-{marker}', color=color, 
                        label=f'{cat} (N={len(subset)})', markersize=4, alpha=0.7)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Mean Deviation (mg/dL/5min)')
        ax.set_title('Circadian Deviation by Category')
        ax.legend(fontsize=8)
        ax.axhline(y=0, color='black', linewidth=0.5)
        
        # Panel 3: R² by category
        ax = axes[1, 0]
        cat_r2s = {}
        for cat in ['Basal', 'CSF', 'UAM', 'ISF']:
            r2s = [r['category_models'][cat]['r2'] for r in all_results.values() 
                   if cat in r['category_models']]
            if r2s:
                cat_r2s[cat] = r2s
        
        positions = []
        labels = []
        data = []
        for i, (cat, r2s) in enumerate(cat_r2s.items()):
            positions.append(i)
            labels.append(f'{cat}\n(N={len(r2s)})')
            data.append(r2s)
        
        if data:
            bp = ax.boxplot(data, positions=positions, patch_artist=True)
            colors_bp = ['lightblue', 'orange', 'red', 'green']
            for patch, color in zip(bp['boxes'], colors_bp[:len(data)]):
                patch.set_facecolor(color)
                patch.set_alpha(0.6)
            ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel('R² (full bilateral model)')
        ax.set_title('Model Performance by Category')
        
        # Panel 4: Insulin coefficient by category
        ax = axes[1, 1]
        cat_ins = {}
        for cat in ['Basal', 'CSF', 'UAM', 'ISF']:
            coefs = [r['category_models'][cat]['coefs']['insulin_absorbed'] 
                     for r in all_results.values() if cat in r['category_models']]
            if coefs:
                cat_ins[cat] = coefs
        
        positions2 = []
        labels2 = []
        data2 = []
        for i, (cat, coefs) in enumerate(cat_ins.items()):
            positions2.append(i)
            labels2.append(cat)
            data2.append(coefs)
        
        if data2:
            bp2 = ax.boxplot(data2, positions=positions2, patch_artist=True)
            for patch, color in zip(bp2['boxes'], colors_bp[:len(data2)]):
                patch.set_facecolor(color)
                patch.set_alpha(0.6)
            ax.set_xticklabels(labels2, fontsize=9)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_ylabel('Insulin Coefficient (mg/dL per U)')
        ax.set_title('Empirical ISF by Category')
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2774-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2774-dashboard.png'}")
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
            'median_basal_pct': round(np.median(basal_pcts), 1),
            'median_csf_pct': round(np.median(csf_pcts), 1),
            'median_uam_pct': round(np.median(uam_pcts), 1),
            'median_isf_pct': round(np.median(isf_pcts), 1),
            'median_meal_pct': round(np.median(meal_pcts), 1),
        },
        'controller_groups': {
            'loop_basal_median': round(np.median(loop_basal), 1) if loop_basal else None,
            'trio_basal_median': round(np.median(trio_basal), 1) if trio_basal else None,
            'openaps_basal_median': round(np.median(oaps_basal), 1) if oaps_basal else None,
        },
        'per_patient': {pid: {k: v for k, v in r.items()} for pid, r in all_results.items()},
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
