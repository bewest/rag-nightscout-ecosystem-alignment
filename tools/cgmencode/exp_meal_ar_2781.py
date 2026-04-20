#!/usr/bin/env python3
"""EXP-2781: Meal Absorption AR Model for CSF Deconfounding

EXP-2779 found CSF autocorrelation = 0.944 — meal absorption is highly
persistent. This means we can PREDICT the next BG change from the current
trajectory during meals, and SUBTRACT this prediction to isolate the
insulin effect.

This is the same principle as oref0's deviation analysis:
  deviation = actual_delta - predicted_delta
Where predicted_delta accounts for known factors (meal absorption, insulin).

Approach:
  1. During CSF (meal) periods, build AR(1) model: delta[t+1] = a × delta[t] + b
  2. Use AR prediction as "expected BG change from meal absorption"
  3. Deviation = actual - AR_predicted = insulin effect + noise
  4. Extract ISF from deviations (should be cleaner than raw data)

If successful, this gives us:
  - Better ISF extraction during meals (42% of data)
  - Quantified meal absorption rates per patient
  - A principled way to separate meal effects from insulin effects

Success criteria (3/5 to PASS):
  H1: AR(1) explains >50% of CSF delta variance (R²>0.5)
  H2: Deviations from AR have NEGATIVE insulin correlation (insulin lowers BG)
  H3: ISF from deviations is more positive than ISF from raw deltas
  H4: AR-based ISF correlates with profile ISF (r>0.4)
  H5: Meal absorption rate varies by meal size (>30g vs <30g carbs)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2781"
TITLE = "Meal Absorption AR Model"
OUT_JSON = Path("externals/experiments/exp-2781_meal_ar.json")
OUT_VIS = Path("tools/visualizations/meal-ar")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
CF = 0.2

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def categorize_csf(df):
    """Simple CSF detection: COB > 0 or recent carbs."""
    df = df.copy()
    df['recent_carbs_3h'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    cob = df.get('cob', pd.Series(0, index=df.index)).fillna(0)
    return (df['recent_carbs_3h'] > 0) | (cob > 0)

def analyze_patient(patient_df, pid):
    """Build AR model for meal periods and extract deviations."""
    df = patient_df.sort_values('time').copy()
    
    profile_isf = df['scheduled_isf'].median()
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    # Short-term delta (5min)
    df['delta_5m'] = df['glucose'].diff()
    df['prev_delta_5m'] = df['delta_5m'].shift(1)
    
    # 1h delta for ISF extraction
    df['delta_1h'] = df['glucose'].shift(-12) - df['glucose']
    df['starting_bg'] = df['glucose']
    
    # Insulin features
    df['excess_insulin_1h'] = (
        df['bolus'].fillna(0).rolling(12, min_periods=1).sum() +
        (df['bolus_smb'].fillna(0).rolling(12, min_periods=1).sum() if 'bolus_smb' in df.columns else 0) +
        (df['net_basal'].fillna(0) / 12.0).rolling(12, min_periods=1).sum() if 'net_basal' in df.columns else
        df['bolus'].fillna(0).rolling(12, min_periods=1).sum()
    )
    
    # CSF identification
    df['is_csf'] = categorize_csf(df)
    df['is_non_csf'] = ~df['is_csf']
    
    # Recent meal size
    df['meal_size'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    
    # --- AR(1) model on CSF periods ---
    csf_df = df[df['is_csf']].dropna(subset=['delta_5m', 'prev_delta_5m'])
    
    if len(csf_df) < 100:
        return None
    
    # AR(1): delta[t] = a * delta[t-1] + b
    y_ar = csf_df['delta_5m'].values
    x_ar = csf_df['prev_delta_5m'].values.reshape(-1, 1)
    
    ar_model = LinearRegression().fit(x_ar, y_ar)
    ar_r2 = ar_model.score(x_ar, y_ar)
    ar_coef = ar_model.coef_[0]
    ar_intercept = ar_model.intercept_
    
    # AR predictions and deviations
    csf_df = csf_df.copy()
    csf_df['ar_predicted'] = ar_model.predict(x_ar)
    csf_df['deviation'] = csf_df['delta_5m'] - csf_df['ar_predicted']
    
    # Cumulative deviation over 1h
    csf_with_1h = csf_df.dropna(subset=['delta_1h']).copy()
    csf_with_1h['excess_insulin_1h'] = df.loc[csf_with_1h.index, 'excess_insulin_1h']
    csf_with_1h['starting_bg'] = df.loc[csf_with_1h.index, 'starting_bg']
    csf_with_1h['meal_size'] = df.loc[csf_with_1h.index, 'meal_size']
    
    if len(csf_with_1h) < 50:
        return None
    
    # --- ISF from raw CSF data ---
    y_raw = csf_with_1h['delta_1h'].values
    X_raw = csf_with_1h[['starting_bg', 'excess_insulin_1h']].fillna(0).values
    
    raw_model = LinearRegression().fit(X_raw, y_raw)
    raw_isf = -raw_model.coef_[1]
    raw_r2 = raw_model.score(X_raw, y_raw)
    
    # --- ISF from deviation-adjusted data ---
    # Predict cumulative AR deviation over 1h
    ar_pred_1h = csf_with_1h['ar_predicted'].rolling(12, min_periods=1).sum()
    csf_with_1h['delta_minus_ar'] = csf_with_1h['delta_1h'] - ar_pred_1h
    
    y_dev = csf_with_1h['delta_minus_ar'].dropna().values
    X_dev = csf_with_1h.loc[csf_with_1h['delta_minus_ar'].notna(), 
                            ['starting_bg', 'excess_insulin_1h']].fillna(0).values
    
    if len(y_dev) < 30:
        return None
    
    dev_model = LinearRegression().fit(X_dev, y_dev)
    dev_isf = -dev_model.coef_[1]
    dev_r2 = dev_model.score(X_dev, y_dev)
    
    # --- Non-CSF ISF for comparison ---
    non_csf = df[df['is_non_csf']].dropna(subset=['delta_1h']).copy()
    if len(non_csf) >= 50:
        y_nc = non_csf['delta_1h'].values
        X_nc = non_csf[['starting_bg', 'excess_insulin_1h']].fillna(0).values
        nc_model = LinearRegression().fit(X_nc, y_nc)
        non_csf_isf = -nc_model.coef_[1]
    else:
        non_csf_isf = np.nan
    
    # --- Meal size effect ---
    large_meals = csf_with_1h[csf_with_1h['meal_size'] > 30]
    small_meals = csf_with_1h[csf_with_1h['meal_size'].between(1, 30)]
    
    large_rate = large_meals['delta_5m'].mean() if len(large_meals) > 20 else np.nan
    small_rate = small_meals['delta_5m'].mean() if len(small_meals) > 20 else np.nan
    
    # Insulin-deviation correlation
    ins_dev_corr = np.corrcoef(
        csf_with_1h['excess_insulin_1h'].fillna(0).values,
        csf_with_1h['deviation'].values
    )[0, 1] if len(csf_with_1h) > 30 else 0
    
    return {
        'patient_id': pid,
        'n_csf': len(csf_df),
        'pct_csf': round(len(csf_df) / len(df) * 100, 1),
        'ar_model': {
            'r2': round(ar_r2, 4),
            'coef': round(ar_coef, 4),
            'intercept': round(ar_intercept, 4),
        },
        'raw_isf': round(raw_isf, 2),
        'raw_r2': round(raw_r2, 4),
        'deviation_isf': round(dev_isf, 2),
        'deviation_r2': round(dev_r2, 4),
        'non_csf_isf': round(non_csf_isf, 2) if not np.isnan(non_csf_isf) else None,
        'profile_isf': round(profile_isf, 1),
        'insulin_deviation_corr': round(ins_dev_corr, 3),
        'large_meal_rate': round(large_rate, 2) if not np.isnan(large_rate) else None,
        'small_meal_rate': round(small_rate, 2) if not np.isnan(small_rate) else None,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2781: {TITLE}")
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
        
        print(f"  {pid}: AR_R²={r['ar_model']['r2']:.3f} raw_ISF={r['raw_isf']:.1f} "
              f"dev_ISF={r['deviation_isf']:.1f} profile={r['profile_isf']:.0f} "
              f"corr={r['insulin_deviation_corr']:.2f}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n = len(results)
    
    # Aggregate
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n})")
    print(f"{'='*60}")
    
    ar_r2s = [r['ar_model']['r2'] for r in results.values()]
    raw_isfs = [r['raw_isf'] for r in results.values()]
    dev_isfs = [r['deviation_isf'] for r in results.values()]
    profile_isfs = [r['profile_isf'] for r in results.values()]
    
    print(f"\nAR(1) model on CSF periods:")
    print(f"  Median R²: {np.median(ar_r2s):.3f}")
    print(f"  Median AR coefficient: {np.median([r['ar_model']['coef'] for r in results.values()]):.3f}")
    
    print(f"\nISF comparison:")
    print(f"  Profile ISF (median):         {np.median(profile_isfs):.0f}")
    print(f"  Raw CSF ISF (median):         {np.median(raw_isfs):.1f}")
    print(f"  Deviation-adjusted ISF:       {np.median(dev_isfs):.1f}")
    
    # Correlations with profile
    r_raw, _ = stats.pearsonr(profile_isfs, raw_isfs)
    r_dev, _ = stats.pearsonr(profile_isfs, dev_isfs)
    
    print(f"\nCorrelation with profile:")
    print(f"  Raw ISF: r={r_raw:.3f}")
    print(f"  Deviation ISF: r={r_dev:.3f}")
    
    # Insulin-deviation correlation
    ins_devs = [r['insulin_deviation_corr'] for r in results.values()]
    print(f"\nInsulin-deviation correlation:")
    print(f"  Median: {np.median(ins_devs):.3f}")
    n_neg = sum(1 for c in ins_devs if c < 0)
    print(f"  Negative (insulin lowers BG): {n_neg}/{n}")
    
    # Meal size effect
    large_rates = [r['large_meal_rate'] for r in results.values() if r['large_meal_rate'] is not None]
    small_rates = [r['small_meal_rate'] for r in results.values() if r['small_meal_rate'] is not None]
    if large_rates and small_rates:
        print(f"\nMeal absorption rate (mg/dL per 5min):")
        print(f"  Large meals (>30g): {np.median(large_rates):.1f}")
        print(f"  Small meals (<30g): {np.median(small_rates):.1f}")
    
    # Hypothesis testing
    h1 = np.median(ar_r2s) > 0.5
    h2 = np.median(ins_devs) < 0
    h3 = np.median(dev_isfs) > np.median(raw_isfs)
    h4 = r_dev > 0.4
    
    h5 = False
    if large_rates and small_rates:
        h5 = abs(np.median(large_rates) - np.median(small_rates)) > 0.5
    
    hypotheses = {
        'H1_ar_r2_gt50': {'pass': bool(h1),
            'value': f"median R²={np.median(ar_r2s):.3f}"},
        'H2_negative_insulin_deviation': {'pass': bool(h2),
            'value': f"median corr={np.median(ins_devs):.3f}, {n_neg}/{n} negative"},
        'H3_deviation_isf_more_positive': {'pass': bool(h3),
            'value': f"dev_ISF={np.median(dev_isfs):.1f} vs raw_ISF={np.median(raw_isfs):.1f}"},
        'H4_deviation_isf_correlates': {'pass': bool(h4),
            'value': f"r={r_dev:.3f}"},
        'H5_meal_size_effect': {'pass': bool(h5),
            'value': f"large={np.median(large_rates):.1f} vs small={np.median(small_rates):.1f}" if large_rates and small_rates else "N/A"},
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
        fig.suptitle(f'EXP-2781: Meal Absorption AR Model — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: AR R² distribution
        ax = axes[0, 0]
        ax.hist(ar_r2s, bins=15, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(x=0.5, color='red', linestyle='--', label='50% target')
        ax.axvline(x=np.median(ar_r2s), color='green', linestyle='-', linewidth=2,
                   label=f'Median={np.median(ar_r2s):.3f}')
        ax.set_xlabel('AR(1) R²')
        ax.set_ylabel('Count')
        ax.set_title('AR(1) Model Fit on CSF Periods')
        ax.legend()
        
        # Panel 2: ISF comparison
        ax = axes[0, 1]
        x = np.arange(n)
        sorted_pids = sorted(results.keys(), key=lambda p: results[p]['profile_isf'])
        ax.bar(x - 0.3, [results[p]['profile_isf'] for p in sorted_pids], 0.3,
               label='Profile', color='gold', alpha=0.7)
        ax.bar(x, [results[p]['deviation_isf'] for p in sorted_pids], 0.3,
               label='Deviation ISF', color='steelblue', alpha=0.7)
        ax.bar(x + 0.3, [results[p]['raw_isf'] for p in sorted_pids], 0.3,
               label='Raw ISF', color='coral', alpha=0.7)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_xlabel('Patient')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title('ISF: Profile vs AR-Deviation vs Raw')
        ax.legend(fontsize=8)
        ax.set_xticks([])
        
        # Panel 3: Insulin-deviation correlation
        ax = axes[1, 0]
        sorted_corrs = sorted(ins_devs)
        colors = ['green' if c < 0 else 'red' for c in sorted_corrs]
        ax.barh(range(len(sorted_corrs)), sorted_corrs, color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linestyle='-')
        ax.set_xlabel('Insulin-Deviation Correlation')
        ax.set_title(f'Insulin Effect in Deviations ({n_neg}/{n} negative)')
        
        # Panel 4: Scatter — profile vs deviation ISF
        ax = axes[1, 1]
        ax.scatter(profile_isfs, dev_isfs, alpha=0.6, s=60, label=f'Deviation (r={r_dev:.2f})')
        ax.scatter(profile_isfs, raw_isfs, alpha=0.4, s=40, marker='s', label=f'Raw (r={r_raw:.2f})')
        max_v = max(profile_isfs) + 10
        ax.plot([0, max_v], [0, max_v], 'r--', alpha=0.3)
        ax.set_xlabel('Profile ISF (mg/dL/U)')
        ax.set_ylabel('Extracted ISF (mg/dL/U)')
        ax.set_title('Profile vs Extracted ISF')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2781-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2781-dashboard.png'}")
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
            'median_ar_r2': round(np.median(ar_r2s), 4),
            'median_raw_isf': round(np.median(raw_isfs), 2),
            'median_dev_isf': round(np.median(dev_isfs), 2),
            'median_profile_isf': round(np.median(profile_isfs), 1),
            'r_raw_profile': round(r_raw, 3),
            'r_dev_profile': round(r_dev, 3),
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
