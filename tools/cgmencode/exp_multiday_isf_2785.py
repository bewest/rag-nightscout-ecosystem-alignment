#!/usr/bin/env python3
"""EXP-2785: Multi-Day Insulin Sensitivity Dynamics

Examines the 72-hour timescale: does insulin sensitivity shift over days?
Hepatic glycogen cycling, illness, stress, exercise create multi-day
patterns. If we can measure day-to-day ISF variation, we can:
1. Subtract it from noise (deconfounding)
2. Recommend autosens-style adjustments
3. Quantify how much of glucose variance is day-level vs within-day

This addresses the user's directive: "at every timescale we need to 
measure confounding effects and subtract them."

Timescales covered so far:
  - 5-min: insulin action, meal absorption (EXP-2781 AR model)
  - 1-6h: ISF window, correction events (EXP-2778)
  - 24h: circadian EGP (EXP-2779/2780)
  - 72h: THIS EXPERIMENT — multi-day sensitivity shifts

Success criteria (3/5 to PASS):
  H1: Day-to-day TDD varies >15% within patients (CV)
  H2: High-TDD days predict lower mean BG (insulin works)
  H3: Prior-day TDD influences next-day BG (72h carryover)
  H4: Day-to-day ISF (BG_drop/dose) varies >20% within patients
  H5: Multi-day moving average improves BG prediction vs static
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2785"
TITLE = "Multi-Day Insulin Sensitivity Dynamics"
OUT_JSON = Path("externals/experiments/exp-2785_multiday_isf.json")
OUT_VIS = Path("tools/visualizations/multiday-isf")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}

def classify_controller(pid):
    if pid in LOOP_IDS or len(pid) == 1:
        return 'Loop'
    if pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Trio'

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    grid['date'] = grid['time'].dt.date
    return grid

def analyze_patient(patient_df, pid):
    """Compute daily summaries and multi-day dynamics."""
    df = patient_df.sort_values('time').copy()
    
    # Daily aggregations
    daily = df.groupby('date').agg(
        mean_bg=('glucose', 'mean'),
        std_bg=('glucose', 'std'),
        tir=('glucose', lambda x: ((x >= 70) & (x <= 180)).mean() * 100),
        tdd_bolus=('bolus', lambda x: x.fillna(0).sum()),
        tdd_smb=('bolus_smb', lambda x: x.fillna(0).sum()),
        carbs=('carbs', lambda x: x.fillna(0).sum()),
        n_rows=('glucose', 'count'),
    ).reset_index()
    
    # Add scheduled basal
    basal_rate = df['scheduled_basal_rate'].median() or 0
    daily['tdd_basal'] = basal_rate * 24  # scheduled daily basal
    daily['tdd'] = daily['tdd_bolus'] + daily['tdd_smb'] + daily['tdd_basal']
    
    # Filter days with sufficient data (>200 rows = >16h)
    daily = daily[daily['n_rows'] >= 200].copy()
    
    if len(daily) < 5:
        return None
    
    # Day-to-day variability
    tdd_cv = daily['tdd'].std() / daily['tdd'].mean() if daily['tdd'].mean() > 0 else 0
    bg_cv = daily['mean_bg'].std() / daily['mean_bg'].mean() if daily['mean_bg'].mean() > 0 else 0
    tir_cv = daily['tir'].std() / daily['tir'].mean() if daily['tir'].mean() > 0 else 0
    
    # Same-day: TDD vs mean BG
    r_tdd_bg, p_tdd_bg = stats.pearsonr(daily['tdd'], daily['mean_bg'])
    
    # Lag analysis: prior-day TDD → next-day BG
    daily['tdd_lag1'] = daily['tdd'].shift(1)
    daily['tdd_lag2'] = daily['tdd'].shift(2)
    daily['bg_lag1'] = daily['mean_bg'].shift(1)
    
    lag_df = daily.dropna(subset=['tdd_lag1'])
    r_lag1_bg = np.nan
    p_lag1_bg = np.nan
    if len(lag_df) >= 5:
        r_lag1_bg, p_lag1_bg = stats.pearsonr(lag_df['tdd_lag1'], lag_df['mean_bg'])
    
    # Daily effective ISF proxy: BG_std / TDD (variability per unit insulin)
    daily['isf_proxy'] = daily['std_bg'] / daily['tdd'].clip(lower=1)
    isf_proxy_cv = daily['isf_proxy'].std() / daily['isf_proxy'].mean() if daily['isf_proxy'].mean() > 0 else 0
    
    # Carb effect: high-carb days vs low-carb days
    carb_median = daily['carbs'].median()
    high_carb = daily[daily['carbs'] >= carb_median]['mean_bg'].mean()
    low_carb = daily[daily['carbs'] < carb_median]['mean_bg'].mean()
    carb_bg_diff = high_carb - low_carb
    
    # 3-day moving average for prediction
    daily['bg_ma3'] = daily['mean_bg'].rolling(3, center=False).mean()
    daily['bg_pred_static'] = daily['mean_bg'].mean()  # static prediction
    
    ma_df = daily.dropna(subset=['bg_ma3'])
    if len(ma_df) >= 3:
        mae_static = np.abs(ma_df['mean_bg'] - ma_df['bg_pred_static']).mean()
        mae_ma3 = np.abs(ma_df['mean_bg'].shift(-1).dropna() - 
                         ma_df['bg_ma3'].iloc[:-1]).mean() if len(ma_df) > 1 else mae_static
        improvement = (mae_static - mae_ma3) / mae_static * 100 if mae_static > 0 else 0
    else:
        mae_static = mae_ma3 = improvement = 0
    
    return {
        'patient_id': pid,
        'controller': classify_controller(pid),
        'n_days': len(daily),
        'tdd_cv': round(tdd_cv * 100, 1),  # as percentage
        'bg_cv': round(bg_cv * 100, 1),
        'tir_cv': round(tir_cv * 100, 1),
        'mean_tdd': round(daily['tdd'].mean(), 1),
        'mean_bg': round(daily['mean_bg'].mean(), 1),
        'r_tdd_bg': round(r_tdd_bg, 3),
        'p_tdd_bg': round(p_tdd_bg, 4),
        'r_lag1_bg': round(r_lag1_bg, 3) if not np.isnan(r_lag1_bg) else None,
        'p_lag1_bg': round(p_lag1_bg, 4) if not np.isnan(p_lag1_bg) else None,
        'isf_proxy_cv': round(isf_proxy_cv * 100, 1),
        'carb_bg_diff': round(carb_bg_diff, 1),
        'mae_static': round(mae_static, 1),
        'mae_ma3': round(mae_ma3, 1),
        'ma3_improvement': round(improvement, 1),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2785: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_patient(pdf, pid)
        if r:
            results.append(r)
            print(f"  {pid:<25} {r['controller']:<8} days={r['n_days']:>3} "
                  f"TDD_CV={r['tdd_cv']:>5.1f}% BG_CV={r['bg_cv']:>5.1f}% "
                  f"r(TDD→BG)={r['r_tdd_bg']:+.3f} lag1={r['r_lag1_bg'] or 0:+.3f}")
    
    n = len(results)
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {n}")
    
    # H1: TDD day-to-day CV > 15%
    print(f"\n{'='*60}")
    print(f"H1: TDD Day-to-Day Variability")
    print(f"{'='*60}")
    tdd_cvs = rdf['tdd_cv']
    print(f"  Median TDD CV: {tdd_cvs.median():.1f}%")
    print(f"  Range: {tdd_cvs.min():.1f}% - {tdd_cvs.max():.1f}%")
    print(f"  Patients with CV > 15%: {(tdd_cvs > 15).sum()}/{n} ({(tdd_cvs > 15).mean()*100:.0f}%)")
    h1 = tdd_cvs.median() > 15
    
    # H2: High-TDD days → lower BG
    print(f"\n{'='*60}")
    print(f"H2: Same-Day TDD → BG Correlation")
    print(f"{'='*60}")
    r_vals = rdf['r_tdd_bg']
    print(f"  Median r(TDD, BG): {r_vals.median():+.3f}")
    print(f"  Negative r (insulin works): {(r_vals < 0).sum()}/{n} ({(r_vals < 0).mean()*100:.0f}%)")
    sig = rdf[rdf['p_tdd_bg'] < 0.05]
    print(f"  Significant (p<0.05): {len(sig)}/{n}")
    h2 = r_vals.median() < 0
    
    # H3: Prior-day TDD → next-day BG
    print(f"\n{'='*60}")
    print(f"H3: Prior-Day TDD → Next-Day BG (72h Carryover)")
    print(f"{'='*60}")
    lag_vals = rdf['r_lag1_bg'].dropna()
    print(f"  Median r(TDD_lag1, BG): {lag_vals.median():+.3f}")
    print(f"  Negative (prior insulin helps): {(lag_vals < 0).sum()}/{len(lag_vals)}")
    h3 = abs(lag_vals.median()) > 0.05  # Any detectable effect
    
    # H4: ISF proxy CV > 20%
    print(f"\n{'='*60}")
    print(f"H4: Day-to-Day ISF Variability")
    print(f"{'='*60}")
    isf_cvs = rdf['isf_proxy_cv']
    print(f"  Median ISF_proxy CV: {isf_cvs.median():.1f}%")
    print(f"  Patients with CV > 20%: {(isf_cvs > 20).sum()}/{n}")
    h4 = isf_cvs.median() > 20
    
    # H5: Moving average improves prediction
    print(f"\n{'='*60}")
    print(f"H5: 3-Day Moving Average vs Static Prediction")
    print(f"{'='*60}")
    improvements = rdf['ma3_improvement']
    print(f"  Median improvement: {improvements.median():+.1f}%")
    print(f"  Patients with improvement: {(improvements > 0).sum()}/{n}")
    print(f"  MAE static: {rdf['mae_static'].median():.1f} mg/dL")
    print(f"  MAE MA(3): {rdf['mae_ma3'].median():.1f} mg/dL")
    h5 = improvements.median() > 5  # At least 5% improvement
    
    # Summary
    hypotheses = {
        'H1_tdd_cv_gt15': {'pass': bool(h1),
            'value': f"median TDD CV = {tdd_cvs.median():.1f}%"},
        'H2_tdd_lowers_bg': {'pass': bool(h2),
            'value': f"median r = {r_vals.median():+.3f}"},
        'H3_prior_day_effect': {'pass': bool(h3),
            'value': f"median lag1 r = {lag_vals.median():+.3f}"},
        'H4_isf_cv_gt20': {'pass': bool(h4),
            'value': f"median ISF_proxy CV = {isf_cvs.median():.1f}%"},
        'H5_ma3_improves': {'pass': bool(h5),
            'value': f"median improvement = {improvements.median():+.1f}%"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Controller breakdown
    print(f"\n{'='*60}")
    print(f"CONTROLLER BREAKDOWN")
    print(f"{'='*60}")
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        mask = rdf['controller'] == ctrl
        cdf = rdf[mask]
        if len(cdf) == 0:
            continue
        print(f"  {ctrl} (N={len(cdf)}):")
        print(f"    TDD CV: {cdf['tdd_cv'].median():.1f}%")
        print(f"    BG CV: {cdf['bg_cv'].median():.1f}%")
        print(f"    r(TDD→BG): {cdf['r_tdd_bg'].median():+.3f}")
        print(f"    ISF proxy CV: {cdf['isf_proxy_cv'].median():.1f}%")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2785: Multi-Day Insulin Sensitivity — {n_pass}/5 PASS', 
                     fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: TDD CV distribution
        ax = axes[0, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = rdf[rdf['controller'] == ctrl]['tdd_cv']
            ax.hist(vals, bins=10, alpha=0.5, label=ctrl, color=ctrl_colors[ctrl])
        ax.axvline(x=15, color='red', linestyle='--', alpha=0.5, label='15% threshold')
        ax.set_xlabel('TDD CV (%)')
        ax.set_ylabel('Count')
        ax.set_title('Day-to-Day TDD Variability')
        ax.legend()
        
        # Panel 2: Same-day TDD→BG correlation
        ax = axes[0, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = rdf['controller'] == ctrl
            ax.scatter(rdf[mask]['tdd_cv'], rdf[mask]['r_tdd_bg'],
                      s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax.set_xlabel('TDD CV (%)')
        ax.set_ylabel('r(TDD, mean BG)')
        ax.set_title('TDD Variability vs Insulin Effect')
        ax.legend()
        
        # Panel 3: ISF proxy CV
        ax = axes[1, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = rdf[rdf['controller'] == ctrl]['isf_proxy_cv']
            ax.hist(vals, bins=10, alpha=0.5, label=ctrl, color=ctrl_colors[ctrl])
        ax.axvline(x=20, color='red', linestyle='--', alpha=0.5, label='20% threshold')
        ax.set_xlabel('ISF Proxy CV (%)')
        ax.set_ylabel('Count')
        ax.set_title('Day-to-Day Insulin Sensitivity Variation')
        ax.legend()
        
        # Panel 4: MA improvement
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = rdf['controller'] == ctrl
            ax.scatter(rdf[mask]['bg_cv'], rdf[mask]['ma3_improvement'],
                      s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax.set_xlabel('BG CV (%)')
        ax.set_ylabel('MA(3) Improvement (%)')
        ax.set_title('Moving Average Prediction Improvement')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2785-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2785-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'summary': {
            'median_tdd_cv': round(tdd_cvs.median(), 1),
            'median_r_tdd_bg': round(r_vals.median(), 3),
            'median_r_lag1_bg': round(lag_vals.median(), 3),
            'median_isf_proxy_cv': round(isf_cvs.median(), 1),
            'median_ma3_improvement': round(improvements.median(), 1),
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
