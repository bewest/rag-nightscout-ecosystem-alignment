#!/usr/bin/env python3
"""EXP-2790: Total Insulin Accounting & Delivery Decomposition

The user asked: "is it worthwhile to do total insulin accounting over 
72 hours as a smell/sanity check?"

This experiment does comprehensive insulin accounting using ACTUAL
delivered insulin (not scheduled), decomposed into channels:
  1. User bolus (manual corrections + meal boluses)
  2. SMB (controller micro-boluses)
  3. Actual basal (temp basal adjustments)

Sanity checks:
- ~50% of TDD should go to "basal/EGP needs" 
- ~50% should go to "food/corrections"
- Trio's low basal rate should be compensated by SMBs
- Total insulin should be physiologically reasonable (0.3-1.5 U/kg/day)

This also tests whether our delivery data is self-consistent and
suitable for the deconfounding pipeline.

Success criteria (3/5 to PASS):
  H1: Bolus+SMB accounts for 40-70% of total delivered insulin
  H2: Actual basal (via net_basal) accounts for 30-60%
  H3: TDD is stable (day-to-day CV < 30%)
  H4: Channel fractions differ by controller (ANOVA p<0.05)
  H5: 3-day total insulin within 10% of 7-day average (stability)
"""

import json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2790"
TITLE = "Total Insulin Accounting & Delivery Decomposition"
OUT_JSON = Path("externals/experiments/exp-2790_insulin_accounting.json")
OUT_VIS = Path("tools/visualizations/insulin-accounting")
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
    df = patient_df.sort_values('time').copy()
    
    if len(df) < 500:
        return None
    
    days = len(df) * 5 / 60 / 24
    
    # Channel totals
    user_bolus = df['bolus'].fillna(0).sum()
    smb_total = df['bolus_smb'].fillna(0).sum()
    
    # Scheduled basal rate
    scheduled_basal_rate = df['scheduled_basal_rate'].median() or 0
    
    # net_basal = DEVIATION from scheduled (actual - scheduled) in U/h
    # actual basal delivery = (net_basal + scheduled_basal_rate) / 12 per 5min
    actual_basal_rate = df['net_basal'].fillna(0) + scheduled_basal_rate
    actual_basal = (actual_basal_rate.clip(lower=0) / 12.0).sum()
    
    # Scheduled basal for comparison
    scheduled_basal = scheduled_basal_rate / 12.0 * len(df)
    
    # Net basal DEVIATION (what controller changed)
    basal_deviation = (df['net_basal'].fillna(0) / 12.0).sum()
    
    # Store actual basal rate for daily aggregation
    df['actual_basal_delivery_5m'] = actual_basal_rate.clip(lower=0) / 12.0
    
    total_delivered = user_bolus + smb_total + actual_basal
    
    if total_delivered <= 0 or days <= 0:
        return None
    
    tdd = total_delivered / days
    
    # Fractions
    bolus_frac = user_bolus / total_delivered
    smb_frac = smb_total / total_delivered
    basal_frac = actual_basal / total_delivered
    scheduled_basal_frac = scheduled_basal / total_delivered
    
    # Non-basal (bolus + SMB) should be ~50%
    non_basal_frac = (user_bolus + smb_total) / total_delivered
    
    # Daily totals for variability
    daily = df.groupby('date').agg(
        bolus=('bolus', lambda x: x.fillna(0).sum()),
        smb=('bolus_smb', lambda x: x.fillna(0).sum()),
        basal=('actual_basal_delivery_5m', 'sum'),
        n_rows=('glucose', 'count'),
    ).reset_index()
    
    daily = daily[daily['n_rows'] >= 200]  # At least 16h data
    daily['total'] = daily['bolus'] + daily['smb'] + daily['basal']
    daily['bolus_frac'] = daily['bolus'] / daily['total'].clip(lower=0.1)
    daily['non_basal_frac'] = (daily['bolus'] + daily['smb']) / daily['total'].clip(lower=0.1)
    
    tdd_cv = daily['total'].std() / daily['total'].mean() * 100 if daily['total'].mean() > 0 else 0
    
    # 3-day vs 7-day stability
    if len(daily) >= 7:
        three_day = daily['total'].iloc[:3].mean()
        seven_day = daily['total'].iloc[:7].mean()
        stability = abs(three_day - seven_day) / seven_day * 100 if seven_day > 0 else 0
    else:
        stability = np.nan
    
    # Per-day channel fractions
    daily_bolus_frac_mean = daily['bolus_frac'].mean() if len(daily) > 0 else np.nan
    daily_non_basal_mean = daily['non_basal_frac'].mean() if len(daily) > 0 else np.nan
    
    return {
        'patient_id': pid,
        'controller': classify_controller(pid),
        'days': round(days, 1),
        'n_valid_days': len(daily),
        
        # Daily totals
        'tdd': round(tdd, 2),
        'tdd_cv': round(tdd_cv, 1),
        
        # Channel fractions (of ACTUAL delivered)
        'bolus_frac': round(bolus_frac * 100, 1),
        'smb_frac': round(smb_frac * 100, 1),
        'basal_frac': round(basal_frac * 100, 1),
        'non_basal_frac': round(non_basal_frac * 100, 1),
        
        # Scheduled vs actual basal
        'scheduled_basal_frac': round(scheduled_basal_frac * 100, 1),
        'basal_actual_vs_sched': round(actual_basal / scheduled_basal * 100, 1) if scheduled_basal > 0 else None,
        
        # Daily variability
        'daily_non_basal_mean': round(daily_non_basal_mean * 100, 1) if not np.isnan(daily_non_basal_mean) else None,
        
        # Stability
        'stability_3v7': round(stability, 1) if not np.isnan(stability) else None,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2790: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_patient(pdf, pid)
        if r:
            results.append(r)
            print(f"  {pid:<25} {r['controller']:<8} TDD={r['tdd']:>5.1f}U "
                  f"bolus={r['bolus_frac']:>4.1f}% SMB={r['smb_frac']:>4.1f}% "
                  f"basal={r['basal_frac']:>5.1f}% | nonbasal={r['non_basal_frac']:>4.1f}%")
    
    n = len(results)
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {n}")
    
    # Overall summary
    print(f"\n{'='*60}")
    print(f"OVERALL INSULIN ACCOUNTING")
    print(f"{'='*60}")
    print(f"  Median TDD: {rdf['tdd'].median():.1f} U/day")
    print(f"  Median bolus fraction: {rdf['bolus_frac'].median():.1f}%")
    print(f"  Median SMB fraction: {rdf['smb_frac'].median():.1f}%")
    print(f"  Median actual basal fraction: {rdf['basal_frac'].median():.1f}%")
    print(f"  Median non-basal (bolus+SMB): {rdf['non_basal_frac'].median():.1f}%")
    
    # How much actual basal vs scheduled?
    bvs = rdf['basal_actual_vs_sched'].dropna()
    print(f"\n  Actual basal / scheduled basal: {bvs.median():.0f}%")
    print(f"  (100% = running exactly as scheduled)")
    
    # Controller comparison
    print(f"\n{'='*60}")
    print(f"BY CONTROLLER")
    print(f"{'='*60}")
    
    ctrl_data = {}
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        mask = rdf['controller'] == ctrl
        cdf = rdf[mask]
        if len(cdf) == 0:
            continue
        ctrl_data[ctrl] = cdf
        print(f"\n  {ctrl} (N={len(cdf)}):")
        print(f"    TDD: {cdf['tdd'].median():.1f} U/day")
        print(f"    Bolus: {cdf['bolus_frac'].median():.1f}%")
        print(f"    SMB: {cdf['smb_frac'].median():.1f}%")
        print(f"    Actual basal: {cdf['basal_frac'].median():.1f}%")
        print(f"    Non-basal: {cdf['non_basal_frac'].median():.1f}%")
        print(f"    Actual/scheduled basal: {cdf['basal_actual_vs_sched'].dropna().median():.0f}%")
    
    # ANOVA on non-basal fraction
    groups = [rdf[rdf['controller'] == c]['non_basal_frac'].values for c in ['Loop', 'Trio', 'OpenAPS']]
    groups = [g for g in groups if len(g) > 1]
    if len(groups) >= 2:
        f_stat, p_anova = stats.f_oneway(*groups)
    else:
        f_stat, p_anova = 0, 1
    
    # Hypotheses
    nb = rdf['non_basal_frac'].median()
    h1 = 40 < nb < 70
    
    bf = rdf['basal_frac'].median()
    h2 = 30 < bf < 60
    
    tdd_cv = rdf['tdd_cv'].median()
    h3 = tdd_cv < 30
    
    h4 = p_anova < 0.05
    
    stability = rdf['stability_3v7'].dropna().median()
    h5 = stability < 10 if not np.isnan(stability) else False
    
    hypotheses = {
        'H1_nonbasal_40_70': {'pass': bool(h1),
            'value': f"median non-basal = {nb:.1f}%"},
        'H2_basal_30_60': {'pass': bool(h2),
            'value': f"median actual basal = {bf:.1f}%"},
        'H3_tdd_cv_lt30': {'pass': bool(h3),
            'value': f"median TDD CV = {tdd_cv:.1f}%"},
        'H4_controller_diff': {'pass': bool(h4),
            'value': f"ANOVA F={f_stat:.2f}, p={p_anova:.4f}"},
        'H5_3v7_lt10pct': {'pass': bool(h5),
            'value': f"median 3v7 diff = {stability:.1f}%"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # 50/50 rule assessment
    print(f"\n{'='*60}")
    print(f"50/50 RULE ASSESSMENT (ACTUAL DELIVERY)")
    print(f"{'='*60}")
    near_50 = rdf['non_basal_frac'].between(40, 60).sum()
    print(f"  Patients within 40-60% non-basal: {near_50}/{n} ({near_50/n*100:.0f}%)")
    too_high = (rdf['non_basal_frac'] > 60).sum()
    too_low = (rdf['non_basal_frac'] < 40).sum()
    print(f"  Too much non-basal (>60%): {too_high}/{n}")
    print(f"  Too little non-basal (<40%): {too_low}/{n}")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2790: Insulin Accounting — {n_pass}/5 PASS', 
                     fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: Stacked bar of channel fractions
        ax = axes[0, 0]
        patients_sorted = rdf.sort_values('non_basal_frac')
        x = range(len(patients_sorted))
        ax.bar(x, patients_sorted['bolus_frac'], label='User Bolus', color='steelblue', alpha=0.7)
        ax.bar(x, patients_sorted['smb_frac'], bottom=patients_sorted['bolus_frac'], 
               label='SMB', color='coral', alpha=0.7)
        ax.bar(x, patients_sorted['basal_frac'], 
               bottom=patients_sorted['bolus_frac'] + patients_sorted['smb_frac'],
               label='Actual Basal', color='green', alpha=0.7)
        ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50%')
        ax.set_xlabel('Patient (sorted by non-basal %)')
        ax.set_ylabel('Fraction of TDD (%)')
        ax.set_title('Insulin Channel Decomposition')
        ax.legend(fontsize=8)
        
        # Panel 2: Non-basal by controller
        ax = axes[0, 1]
        ctrl_data_box = []
        ctrl_labels = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = rdf[rdf['controller'] == ctrl]['non_basal_frac'].values
            if len(vals) > 0:
                ctrl_data_box.append(vals)
                ctrl_labels.append(f'{ctrl}\n(N={len(vals)})')
        bp = ax.boxplot(ctrl_data_box, patch_artist=True)
        for patch, label in zip(bp['boxes'], ctrl_labels):
            cn = label.split('\n')[0]
            patch.set_facecolor(ctrl_colors.get(cn, 'gray'))
            patch.set_alpha(0.6)
        ax.set_xticklabels(ctrl_labels)
        ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50% target')
        ax.set_ylabel('Non-Basal Fraction (%)')
        ax.set_title(f'Non-Basal by Controller (p={p_anova:.3f})')
        ax.legend()
        
        # Panel 3: Actual vs Scheduled basal
        ax = axes[1, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = rdf['controller'] == ctrl
            vals = rdf[mask]['basal_actual_vs_sched'].dropna()
            if len(vals) > 0:
                ax.scatter([ctrl] * len(vals), vals, s=60, alpha=0.7, color=ctrl_colors[ctrl])
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.5, label='100% = as scheduled')
        ax.set_ylabel('Actual / Scheduled Basal (%)')
        ax.set_title('Basal Delivery vs Schedule')
        ax.legend()
        
        # Panel 4: TDD distribution
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = rdf['controller'] == ctrl
            ax.hist(rdf[mask]['tdd'], bins=10, alpha=0.5, label=ctrl, color=ctrl_colors[ctrl])
        ax.set_xlabel('TDD (U/day)')
        ax.set_ylabel('Count')
        ax.set_title(f'TDD Distribution (median={rdf["tdd"].median():.1f}U)')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2790-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2790-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'summary': {
            'median_tdd': round(rdf['tdd'].median(), 1),
            'median_bolus_frac': round(rdf['bolus_frac'].median(), 1),
            'median_smb_frac': round(rdf['smb_frac'].median(), 1),
            'median_basal_frac': round(rdf['basal_frac'].median(), 1),
            'median_non_basal_frac': round(rdf['non_basal_frac'].median(), 1),
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
