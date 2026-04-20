#!/usr/bin/env python3
"""EXP-2775: Basal Rate Optimization from 50/50 Rule

EXP-2771 showed 16/30 patients have scheduled basal <35% of TDD (target: 50%).
EXP-2774 confirmed only 21% of time is in "basal" category.

This experiment computes recommended basal rate adjustments:
  1. Calculate actual TDD and basal fraction for each patient
  2. Compute target basal rate to achieve 50% TDD (accounting for controller redistribution)
  3. Validate: do patients with closer-to-50/50 splits have better outcomes?
  4. Cross-validate: temporal split to check stability of recommendations

The clinical insight: when basal is too low, the controller must compensate
by delivering extra insulin through SMBs/temp basals. This creates:
  - More glucose variability (reactive vs proactive dosing)
  - Higher TIR deviation from optimal
  - Controller working harder (more adjustments per hour)

Success criteria (3/5 to PASS):
  H1: Recommended basal increase median >20% for patients with basal <35%
  H2: Patients closer to 50/50 have better TIR (r>0.2 between basal_frac and TIR)
  H3: Recommendations are temporally stable (train/test correlation >0.7)
  H4: Controller adjustment frequency correlates with basal deviation (r>0.2)
  H5: >70% of patients would benefit from basal adjustment
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2775"
TITLE = "Basal Rate Optimization from 50/50 Rule"
OUT_JSON = Path("externals/experiments/exp-2775_basal_optimization.json")
OUT_VIS = Path("tools/visualizations/basal-optimization")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
TARGET_BASAL_FRACTION = 0.50
MIN_BASAL_FRACTION = 0.35  # below this = definitely too low
MAX_BASAL_FRACTION = 0.65  # above this = too high

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def compute_patient_metrics(patient_df, pid):
    """Compute basal metrics, TIR, and controller activity per patient."""
    df = patient_df.sort_values('time').copy()
    
    # Check for insulin data
    has_insulin = 'iob' in df.columns and df['iob'].notna().mean() > 0.5
    if not has_insulin:
        return None
    
    # TDD components
    scheduled_basal_rate = df['scheduled_basal_rate'].median() if 'scheduled_basal_rate' in df.columns else np.nan
    if pd.isna(scheduled_basal_rate) or scheduled_basal_rate <= 0:
        return None
    
    # Daily insulin accounting
    # Scheduled basal per day = rate × 24
    scheduled_basal_daily = scheduled_basal_rate * 24
    
    # Total bolus per day (manual + SMB)
    hours = (df['time'].max() - df['time'].min()).total_seconds() / 3600
    days = max(hours / 24, 1)
    
    bolus_total = df['bolus'].fillna(0).sum() if 'bolus' in df.columns else 0
    smb_total = df['bolus_smb'].fillna(0).sum() if 'bolus_smb' in df.columns else 0
    
    # Net basal adjustment (excess above scheduled)
    if 'net_basal' in df.columns:
        net_basal_total = df['net_basal'].fillna(0).sum() / 12  # U/hr → U per 5min
    else:
        net_basal_total = 0
    
    # TDD = scheduled_basal + bolus + smb + net_basal_adjustment
    bolus_daily = bolus_total / days
    smb_daily = smb_total / days
    net_basal_daily = net_basal_total / days
    
    tdd = scheduled_basal_daily + bolus_daily + smb_daily + net_basal_daily
    if tdd <= 0:
        return None
    
    basal_fraction = scheduled_basal_daily / tdd
    
    # TIR metrics
    glucose = df['glucose'].dropna()
    if len(glucose) < 100:
        return None
    
    tir = (glucose.between(70, 180).mean()) * 100
    tbr = (glucose < 70).mean() * 100
    tar = (glucose > 180).mean() * 100
    cv = (glucose.std() / glucose.mean()) * 100
    mean_bg = glucose.mean()
    
    # Controller activity: how often does the controller adjust?
    # Count non-zero net_basal adjustments per hour
    if 'net_basal' in df.columns:
        adjustments = (df['net_basal'].fillna(0).abs() > 0.01).sum()
        adj_per_hour = adjustments / max(hours, 1)
    else:
        adj_per_hour = np.nan
    
    # Recommended basal rate to achieve 50/50
    # target: scheduled_basal_daily = 0.5 × TDD
    target_basal_daily = TARGET_BASAL_FRACTION * tdd
    recommended_rate = target_basal_daily / 24
    pct_change = ((recommended_rate - scheduled_basal_rate) / scheduled_basal_rate) * 100
    
    # Basal deviation from 50/50
    basal_deviation = abs(basal_fraction - TARGET_BASAL_FRACTION)
    
    # Temporal split (first half vs second half)
    midpoint = df['time'].quantile(0.5)
    first_half = df[df['time'] <= midpoint]
    second_half = df[df['time'] > midpoint]
    
    fh_basal_frac = scheduled_basal_daily / max(
        scheduled_basal_daily + first_half['bolus'].fillna(0).sum() / (days/2) + 
        first_half['bolus_smb'].fillna(0).sum() / (days/2) +
        first_half['net_basal'].fillna(0).sum() / 12 / (days/2) if 'net_basal' in first_half.columns else 0, 
        0.1)
    
    sh_basal_frac = scheduled_basal_daily / max(
        scheduled_basal_daily + second_half['bolus'].fillna(0).sum() / (days/2) +
        second_half['bolus_smb'].fillna(0).sum() / (days/2) +
        second_half['net_basal'].fillna(0).sum() / 12 / (days/2) if 'net_basal' in second_half.columns else 0,
        0.1)
    
    # Determine controller type
    if pid in list('abcdefgik'):
        controller = 'Loop'
    elif pid.startswith('ns-'):
        controller = 'Trio'
    elif pid.startswith('odc-'):
        controller = 'OpenAPS'
    else:
        controller = 'Unknown'
    
    return {
        'patient_id': pid,
        'controller': controller,
        'scheduled_basal_rate': round(scheduled_basal_rate, 3),
        'tdd': round(tdd, 1),
        'scheduled_basal_daily': round(scheduled_basal_daily, 1),
        'basal_fraction': round(basal_fraction, 3),
        'bolus_daily': round(bolus_daily, 1),
        'smb_daily': round(smb_daily, 1),
        'recommended_rate': round(recommended_rate, 3),
        'pct_change': round(pct_change, 1),
        'needs_increase': basal_fraction < MIN_BASAL_FRACTION,
        'needs_decrease': basal_fraction > MAX_BASAL_FRACTION,
        'tir': round(tir, 1),
        'tbr': round(tbr, 1),
        'tar': round(tar, 1),
        'cv': round(cv, 1),
        'mean_bg': round(mean_bg, 1),
        'adj_per_hour': round(adj_per_hour, 2) if not np.isnan(adj_per_hour) else None,
        'basal_deviation': round(basal_deviation, 3),
        'first_half_basal_frac': round(fh_basal_frac, 3),
        'second_half_basal_frac': round(sh_basal_frac, 3),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2775: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = []
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        metrics = compute_patient_metrics(pdf, pid)
        
        if metrics is None:
            print(f"  {pid}: skipped (insufficient data)")
            continue
        
        results.append(metrics)
        flag = "⚠ LOW" if metrics['needs_increase'] else ("⚠ HIGH" if metrics['needs_decrease'] else "  OK")
        print(f"  {pid} [{metrics['controller']:7s}]: basal={metrics['basal_fraction']:.0%} "
              f"TDD={metrics['tdd']:.0f}U rate={metrics['scheduled_basal_rate']:.2f}→"
              f"{metrics['recommended_rate']:.2f} ({metrics['pct_change']:+.0f}%) "
              f"TIR={metrics['tir']:.0f}% {flag}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    rdf = pd.DataFrame(results)
    n_total = len(rdf)
    
    # Aggregate
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n_total})")
    print(f"{'='*60}")
    
    n_low = rdf['needs_increase'].sum()
    n_high = rdf['needs_decrease'].sum()
    n_ok = n_total - n_low - n_high
    n_benefit = n_low + n_high
    
    print(f"Basal too low (<35%):  {n_low}/{n_total}")
    print(f"Basal OK (35-65%):     {n_ok}/{n_total}")
    print(f"Basal too high (>65%): {n_high}/{n_total}")
    print(f"Need adjustment:       {n_benefit}/{n_total} ({100*n_benefit/n_total:.0f}%)")
    
    # For low-basal patients, recommended increase
    low_patients = rdf[rdf['needs_increase']]
    if len(low_patients) > 0:
        print(f"\nLow-basal patients ({len(low_patients)}):")
        print(f"  Current basal fraction: median {low_patients['basal_fraction'].median():.0%}")
        print(f"  Recommended increase:   median {low_patients['pct_change'].median():+.0f}%")
        print(f"  Current rate:           median {low_patients['scheduled_basal_rate'].median():.2f} U/hr")
        print(f"  Recommended rate:       median {low_patients['recommended_rate'].median():.2f} U/hr")
    
    # Correlation: basal fraction vs TIR
    r_tir, p_tir = stats.pearsonr(rdf['basal_deviation'], rdf['tir'])
    print(f"\nBasal deviation vs TIR: r={r_tir:.3f} (p={p_tir:.3f})")
    
    # Correlation: basal deviation vs controller activity
    adj_data = rdf.dropna(subset=['adj_per_hour'])
    if len(adj_data) > 5:
        r_adj, p_adj = stats.pearsonr(adj_data['basal_deviation'], adj_data['adj_per_hour'])
        print(f"Basal deviation vs adjustment freq: r={r_adj:.3f} (p={p_adj:.3f})")
    else:
        r_adj = 0
    
    # Temporal stability
    fh = rdf['first_half_basal_frac']
    sh = rdf['second_half_basal_frac']
    r_temporal, p_temporal = stats.pearsonr(fh, sh)
    print(f"Temporal stability (1st vs 2nd half): r={r_temporal:.3f}")
    
    # By controller
    print(f"\n--- BY CONTROLLER ---")
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        subset = rdf[rdf['controller'] == ctrl]
        if len(subset) > 0:
            print(f"  {ctrl} (N={len(subset)}): basal_frac={subset['basal_fraction'].median():.0%} "
                  f"TIR={subset['tir'].median():.0f}% TDD={subset['tdd'].median():.0f}U "
                  f"need_adjust={subset['needs_increase'].sum()}/{len(subset)}")
    
    # Hypothesis testing
    h1 = len(low_patients) > 0 and low_patients['pct_change'].median() > 20
    h2 = abs(r_tir) > 0.2  # note: might be negative (more deviation → less TIR)
    h3 = r_temporal > 0.7
    h4 = abs(r_adj) > 0.2
    h5 = n_benefit / n_total > 0.7
    
    hypotheses = {
        'H1_median_increase_gt20pct': {'pass': bool(h1), 
            'value': f"{low_patients['pct_change'].median():+.0f}%" if len(low_patients) > 0 else "N/A"},
        'H2_basal_deviation_vs_tir': {'pass': bool(h2), 'value': f"r={r_tir:.3f}"},
        'H3_temporal_stability': {'pass': bool(h3), 'value': f"r={r_temporal:.3f}"},
        'H4_controller_effort_correlation': {'pass': bool(h4), 'value': f"r={r_adj:.3f}"},
        'H5_gt70pct_need_adjustment': {'pass': bool(h5), 'value': f"{n_benefit}/{n_total}"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Actionable recommendations table
    print(f"\n{'='*60}")
    print(f"ACTIONABLE RECOMMENDATIONS")
    print(f"{'='*60}")
    print(f"{'Patient':<20s} {'Controller':<8s} {'Current':>8s} {'Target':>8s} {'Change':>8s} {'TIR':>6s}")
    print(f"{'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")
    for _, row in rdf.sort_values('basal_fraction').iterrows():
        flag = "⚠" if row['needs_increase'] or row['needs_decrease'] else " "
        print(f"{flag}{row['patient_id']:<19s} {row['controller']:<8s} "
              f"{row['scheduled_basal_rate']:>7.2f}U {row['recommended_rate']:>7.2f}U "
              f"{row['pct_change']:>+7.0f}% {row['tir']:>5.0f}%")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2775: Basal Optimization — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: Basal fraction vs TIR
        ax = axes[0, 0]
        colors = {'Loop': 'blue', 'Trio': 'green', 'OpenAPS': 'orange'}
        for ctrl, grp in rdf.groupby('controller'):
            ax.scatter(grp['basal_fraction']*100, grp['tir'], 
                      label=ctrl, color=colors.get(ctrl, 'gray'), s=60, alpha=0.7)
        ax.axvline(x=35, color='red', linestyle='--', alpha=0.5, label='Min threshold')
        ax.axvline(x=50, color='green', linestyle='--', alpha=0.5, label='Target')
        ax.set_xlabel('Basal Fraction of TDD (%)')
        ax.set_ylabel('Time in Range (%)')
        ax.set_title(f'Basal Fraction vs TIR (r={r_tir:.3f})')
        ax.legend(fontsize=8)
        
        # Panel 2: Recommended changes
        ax = axes[0, 1]
        sorted_rdf = rdf.sort_values('pct_change')
        colors_bar = ['red' if r['needs_increase'] else ('orange' if r['needs_decrease'] else 'green') 
                     for _, r in sorted_rdf.iterrows()]
        ax.barh(range(len(sorted_rdf)), sorted_rdf['pct_change'], color=colors_bar, alpha=0.7)
        ax.set_xlabel('Recommended Basal Change (%)')
        ax.set_ylabel('Patient')
        ax.set_title(f'Basal Rate Adjustments ({n_benefit}/{n_total} need change)')
        ax.axvline(x=0, color='black', linewidth=1)
        ax.set_yticks([])
        
        # Panel 3: Temporal stability
        ax = axes[1, 0]
        ax.scatter(rdf['first_half_basal_frac']*100, rdf['second_half_basal_frac']*100, 
                  alpha=0.6, s=50)
        lims = [0, 100]
        ax.plot(lims, lims, 'r--', alpha=0.5)
        ax.set_xlabel('First Half Basal Fraction (%)')
        ax.set_ylabel('Second Half Basal Fraction (%)')
        ax.set_title(f'Temporal Stability (r={r_temporal:.3f})')
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        
        # Panel 4: Controller comparison
        ax = axes[1, 1]
        ctrl_data = []
        ctrl_labels = []
        ctrl_colors = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            subset = rdf[rdf['controller'] == ctrl]['basal_fraction'] * 100
            if len(subset) > 0:
                ctrl_data.append(subset.values)
                ctrl_labels.append(f'{ctrl}\n(N={len(subset)})')
                ctrl_colors.append(colors.get(ctrl, 'gray'))
        
        if ctrl_data:
            bp = ax.boxplot(ctrl_data, patch_artist=True)
            for patch, color in zip(bp['boxes'], ctrl_colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.5)
            ax.set_xticklabels(ctrl_labels)
        ax.axhline(y=50, color='green', linestyle='--', label='50/50 target')
        ax.axhline(y=35, color='red', linestyle='--', label='Min threshold')
        ax.set_ylabel('Basal Fraction (%)')
        ax.set_title('Basal Fraction by Controller')
        ax.legend(fontsize=8)
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2775-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2775-dashboard.png'}")
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
            'n_low_basal': int(n_low),
            'n_ok': int(n_ok),
            'n_high_basal': int(n_high),
            'n_need_adjustment': int(n_benefit),
            'median_basal_fraction': round(rdf['basal_fraction'].median(), 3),
            'r_deviation_tir': round(r_tir, 3),
            'r_temporal': round(r_temporal, 3),
            'r_controller_effort': round(r_adj, 3),
        },
        'recommendations': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
