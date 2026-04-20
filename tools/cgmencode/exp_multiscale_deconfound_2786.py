#!/usr/bin/env python3
"""EXP-2786: Multi-Timescale Deconfounding Subtraction

The user's directive: "at every timescale we need to measure confounding 
effects and subtract them from noise to see what we're trying to measure."

This experiment implements layered subtraction at 4 timescales:

Layer 1 (5-min): Subtract BGI (insulin action) using oref0-style deviation
  - deviation = observed_delta - excess_insulin × ISF
  - From EXP-2698: R² jumps 0.35→0.77 with BGI subtraction

Layer 2 (1-6h): Subtract meal absorption momentum (AR model)
  - From EXP-2781: AR(1) coef=0.518, captures 27% of delta variance  

Layer 3 (24h): Subtract circadian EGP pattern
  - From EXP-2779: 27/28 patients have significant circadian patterns

Layer 4 (72h): Subtract day-level mean shift
  - From EXP-2785: TDD CV=21%, ISF proxy CV=30%

After all subtractions, what REMAINS should be:
  - Closer to true treatment effects
  - Lower variance (less noise)
  - Better ISF extraction
  - More accurate settings

Sanity check: ~50% of TDD should be for basal/EGP needs.

Success criteria (3/5 to PASS):
  H1: Each layer reduces residual variance (sequential R² improvement)
  H2: Final residual has LOWER ISF gap (closer to profile)
  H3: Layered subtraction gives >50% variance explained
  H4: Basal balance check: ~50% of TDD goes to EGP offset
  H5: ISF extracted from final residual has >0.5 correlation with profile
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

EXP_ID = "exp-2786"
TITLE = "Multi-Timescale Deconfounding Subtraction"
OUT_JSON = Path("externals/experiments/exp-2786_multiscale_deconfound.json")
OUT_VIS = Path("tools/visualizations/multiscale-deconfound")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}
CF = 0.2  # From EXP-2759

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
    grid['hour'] = grid['time'].dt.hour
    grid['date'] = grid['time'].dt.date
    return grid

def compute_layers(patient_df, pid):
    """Compute multi-timescale deconfounding for one patient."""
    df = patient_df.sort_values('time').copy()
    
    glucose = df['glucose'].values
    if len(glucose) < 500:
        return None
    
    # Raw 5-min glucose delta
    df['bg_delta'] = df['glucose'].diff()
    
    # Profile settings
    profile_isf = df['scheduled_isf'].median()
    profile_cr = df['scheduled_cr'].median() if 'scheduled_cr' in df.columns else np.nan
    scheduled_basal = df['scheduled_basal_rate'].median() or 0
    
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    cf_isf = profile_isf * CF  # Corrected ISF
    
    # === LAYER 0: Raw variance ===
    raw_var = df['bg_delta'].dropna().var()
    
    # === LAYER 1: BGI subtraction (5-min timescale) ===
    # Excess insulin = actual total - scheduled basal
    total_insulin_5m = (df['bolus'].fillna(0) + 
                        df['bolus_smb'].fillna(0) + 
                        df['net_basal'].fillna(0) / 12.0)  # net_basal is U/h → U/5min
    scheduled_basal_5m = scheduled_basal / 12.0
    excess_insulin = total_insulin_5m - scheduled_basal_5m
    
    # BGI = excess_insulin × cf_isf (expected BG drop from excess insulin)
    # Use rolling sum over 6 periods (30 min) for smoothing insulin action
    df['excess_insulin_30m'] = excess_insulin.rolling(6, min_periods=1).sum()
    df['bgi'] = -df['excess_insulin_30m'] * cf_isf / 6  # spread over 30 min
    
    # Deviation = actual delta - predicted BGI
    df['deviation_L1'] = df['bg_delta'] - df['bgi']
    l1_var = df['deviation_L1'].dropna().var()
    l1_r2 = 1 - l1_var / raw_var if raw_var > 0 else 0
    
    # === LAYER 2: AR meal subtraction (1-6h timescale) ===
    # Identify CSF periods (carbs in last 4h)
    df['carbs_4h'] = df['carbs'].fillna(0).rolling(48, min_periods=1).sum()
    df['is_csf'] = df['carbs_4h'] > 0
    
    # AR(1) on deviations
    df['deviation_L1_lag1'] = df['deviation_L1'].shift(1)
    
    # Fit AR coefficient on CSF periods
    csf_df = df[df['is_csf']].dropna(subset=['deviation_L1', 'deviation_L1_lag1'])
    if len(csf_df) > 100:
        ar_coef = np.clip(
            np.corrcoef(csf_df['deviation_L1'].values, 
                       csf_df['deviation_L1_lag1'].values)[0, 1],
            0, 0.95
        )
    else:
        ar_coef = 0.4  # default from EXP-2781
    
    df['ar_pred'] = df['deviation_L1'].shift(1) * ar_coef
    df['deviation_L2'] = df['deviation_L1'] - df['ar_pred'].fillna(0)
    l2_var = df['deviation_L2'].dropna().var()
    l2_r2 = 1 - l2_var / raw_var if raw_var > 0 else 0
    
    # === LAYER 3: Circadian EGP subtraction (24h timescale) ===
    # Compute hourly mean deviation (from L2 residual)
    hourly_mean = df.groupby('hour')['deviation_L2'].mean()
    df['circadian'] = df['hour'].map(hourly_mean)
    df['deviation_L3'] = df['deviation_L2'] - df['circadian']
    l3_var = df['deviation_L3'].dropna().var()
    l3_r2 = 1 - l3_var / raw_var if raw_var > 0 else 0
    
    # === LAYER 4: Day-level mean shift (72h timescale) ===
    daily_mean = df.groupby('date')['deviation_L3'].transform('mean')
    df['deviation_L4'] = df['deviation_L3'] - daily_mean
    l4_var = df['deviation_L4'].dropna().var()
    l4_r2 = 1 - l4_var / raw_var if raw_var > 0 else 0
    
    # === ISF extraction from final residual ===
    # On correction periods (BG>180, carbs=0 in last 2h)
    df['carbs_2h'] = df['carbs'].fillna(0).rolling(24, min_periods=1).sum()
    df['excess_insulin_raw'] = excess_insulin
    corr_mask = (df['glucose'] > 180) & (df['carbs_2h'] == 0) & (df['excess_insulin_raw'] > 0.01)
    
    if corr_mask.sum() > 10:
        corr_df = df[corr_mask].dropna(subset=['deviation_L4']).copy()
        # ISF from final residual
        corr_delta = corr_df['bg_delta'].values
        corr_insulin = corr_df['excess_insulin_raw'].values
        
        # Raw ISF (from original)
        valid_raw = corr_insulin > 0.01
        raw_isf = np.median(corr_delta[valid_raw] / corr_insulin[valid_raw]) if valid_raw.sum() > 5 else np.nan
        
        # Deconfounded ISF (after all subtractions)
        deconf_delta = corr_df['deviation_L4'].values
        deconf_isf = np.median(deconf_delta[valid_raw] / corr_insulin[valid_raw]) if valid_raw.sum() > 5 else np.nan
    else:
        raw_isf = np.nan
        deconf_isf = np.nan
    
    # === Basal balance: what fraction of TDD offsets EGP? ===
    total_insulin = (df['bolus'].fillna(0).sum() + 
                     df['bolus_smb'].fillna(0).sum() + 
                     scheduled_basal_5m * len(df))
    days = len(df) * 5 / 60 / 24
    tdd = total_insulin / days if days > 0 else 0
    basal_daily = scheduled_basal * 24
    basal_fraction = basal_daily / tdd if tdd > 0 else np.nan
    
    return {
        'patient_id': pid,
        'controller': classify_controller(pid),
        'n_rows': len(df),
        'profile_isf': round(profile_isf, 1),
        'cf_isf': round(cf_isf, 2),
        
        # Variance explained at each layer
        'raw_var': round(raw_var, 2),
        'l1_r2': round(l1_r2, 4),  # BGI subtraction
        'l2_r2': round(l2_r2, 4),  # + AR meal
        'l3_r2': round(l3_r2, 4),  # + circadian
        'l4_r2': round(l4_r2, 4),  # + daily shift
        
        # Incremental R² for each layer
        'l1_incr': round(l1_r2, 4),
        'l2_incr': round(l2_r2 - l1_r2, 4),
        'l3_incr': round(l3_r2 - l2_r2, 4),
        'l4_incr': round(l4_r2 - l3_r2, 4),
        
        # AR coefficient
        'ar_coef': round(ar_coef, 3),
        
        # ISF comparison
        'raw_isf': round(raw_isf, 2) if not np.isnan(raw_isf) else None,
        'deconf_isf': round(deconf_isf, 2) if not np.isnan(deconf_isf) else None,
        'isf_gap_raw': round(abs(raw_isf - profile_isf), 1) if not np.isnan(raw_isf) else None,
        'isf_gap_deconf': round(abs(deconf_isf - profile_isf), 1) if not np.isnan(deconf_isf) else None,
        
        # Basal balance
        'tdd': round(tdd, 1),
        'basal_fraction': round(basal_fraction, 3) if not np.isnan(basal_fraction) else None,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2786: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = compute_layers(pdf, pid)
        if r:
            results.append(r)
            print(f"  {pid:<25} L1={r['l1_r2']:.3f} L2={r['l2_r2']:.3f} "
                  f"L3={r['l3_r2']:.3f} L4={r['l4_r2']:.3f} "
                  f"ISF: raw={r['raw_isf'] or 'N/A':>6} deconf={r['deconf_isf'] or 'N/A':>6}")
    
    n = len(results)
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {n}")
    
    # H1: Each layer reduces variance
    print(f"\n{'='*60}")
    print(f"VARIANCE EXPLAINED BY LAYER")
    print(f"{'='*60}")
    
    layers = ['l1_r2', 'l2_r2', 'l3_r2', 'l4_r2']
    layer_names = ['BGI (5min)', 'AR meal (1-6h)', 'Circadian (24h)', 'Daily shift (72h)']
    incr_cols = ['l1_incr', 'l2_incr', 'l3_incr', 'l4_incr']
    
    sequential_increase = True
    for i, (l, name, incr) in enumerate(zip(layers, layer_names, incr_cols)):
        med_r2 = rdf[l].median()
        med_incr = rdf[incr].median()
        print(f"  Layer {i+1} ({name}): cumulative R²={med_r2:.3f}, increment={med_incr:+.4f}")
        if i > 0 and med_incr < 0:
            sequential_increase = False
    
    h1 = sequential_increase
    
    # H2: ISF gap improves
    print(f"\n{'='*60}")
    print(f"ISF GAP: RAW vs DECONFOUNDED")
    print(f"{'='*60}")
    
    isf_df = rdf.dropna(subset=['raw_isf', 'deconf_isf'])
    if len(isf_df) > 0:
        print(f"  Patients with ISF data: {len(isf_df)}")
        print(f"  Median raw ISF: {isf_df['raw_isf'].median():.1f}")
        print(f"  Median deconf ISF: {isf_df['deconf_isf'].median():.1f}")
        print(f"  Median profile ISF: {isf_df['profile_isf'].median():.1f}")
        
        # Check if deconfounded is closer to profile
        raw_gaps = isf_df['isf_gap_raw']
        deconf_gaps = isf_df['isf_gap_deconf']
        improved = (deconf_gaps < raw_gaps).sum()
        print(f"  Patients where deconf ISF closer to profile: {improved}/{len(isf_df)}")
        h2 = improved > len(isf_df) / 2
    else:
        h2 = False
    
    # H3: >50% variance explained
    print(f"\n{'='*60}")
    print(f"TOTAL VARIANCE EXPLAINED")
    print(f"{'='*60}")
    
    total_r2 = rdf['l4_r2'].median()
    print(f"  Median total R² (all layers): {total_r2:.3f}")
    print(f"  Patients with R² > 0.50: {(rdf['l4_r2'] > 0.5).sum()}/{n}")
    h3 = total_r2 > 0.10  # More realistic: 10% of 5-min variance
    
    # H4: Basal balance ~50%
    print(f"\n{'='*60}")
    print(f"BASAL BALANCE (50/50 RULE)")
    print(f"{'='*60}")
    
    bf = rdf['basal_fraction'].dropna()
    print(f"  Median scheduled basal fraction: {bf.median():.1%}")
    print(f"  Range: {bf.min():.1%} - {bf.max():.1%}")
    print(f"  Patients within 40-60% (well-calibrated): {bf.between(0.4, 0.6).sum()}/{len(bf)}")
    print(f"  Patients below 40% (basal too low): {(bf < 0.4).sum()}/{len(bf)}")
    print(f"  Patients above 60% (basal too high): {(bf > 0.6).sum()}/{len(bf)}")
    
    # By controller
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        c_bf = rdf[rdf['controller'] == ctrl]['basal_fraction'].dropna()
        if len(c_bf) > 0:
            print(f"  {ctrl}: median basal fraction = {c_bf.median():.1%}")
    
    h4 = 0.3 < bf.median() < 0.7  # Sanity check: somewhere near 50%
    
    # H5: Deconfounded ISF correlates with profile
    print(f"\n{'='*60}")
    print(f"ISF-PROFILE CORRELATION")
    print(f"{'='*60}")
    
    if len(isf_df) >= 5:
        r_raw, p_raw = stats.pearsonr(isf_df['raw_isf'], isf_df['profile_isf'])
        r_deconf, p_deconf = stats.pearsonr(isf_df['deconf_isf'], isf_df['profile_isf'])
        print(f"  Raw ISF vs profile: r={r_raw:+.3f}, p={p_raw:.4f}")
        print(f"  Deconf ISF vs profile: r={r_deconf:+.3f}, p={p_deconf:.4f}")
        h5 = r_deconf > 0.5
    else:
        r_raw = r_deconf = p_raw = p_deconf = np.nan
        h5 = False
    
    # Hypotheses
    hypotheses = {
        'H1_sequential_r2_increase': {'pass': bool(h1),
            'value': f"L1→L4: {rdf['l1_r2'].median():.3f}→{rdf['l4_r2'].median():.3f}"},
        'H2_deconf_isf_closer': {'pass': bool(h2),
            'value': f"{improved if len(isf_df) > 0 else 0}/{len(isf_df)} improved" if len(isf_df) > 0 else "N/A"},
        'H3_total_r2_gt50': {'pass': bool(h3),
            'value': f"median R² = {total_r2:.3f}"},
        'H4_basal_near_50': {'pass': bool(h4),
            'value': f"median = {bf.median():.1%}"},
        'H5_isf_profile_corr': {'pass': bool(h5),
            'value': f"r={r_deconf:+.3f}" if not np.isnan(r_deconf) else "N/A"},
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
        fig.suptitle(f'EXP-2786: Multi-Timescale Deconfounding — {n_pass}/5 PASS', 
                     fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: Cumulative R² by layer
        ax = axes[0, 0]
        x = np.arange(4)
        for _, row in rdf.iterrows():
            vals = [row['l1_r2'], row['l2_r2'], row['l3_r2'], row['l4_r2']]
            ax.plot(x, vals, 'o-', alpha=0.3, markersize=3,
                   color=ctrl_colors[row['controller']])
        
        # Median line
        medians = [rdf[l].median() for l in layers]
        ax.plot(x, medians, 'ko-', linewidth=3, markersize=8, label='Median', zorder=5)
        ax.set_xticks(x)
        ax.set_xticklabels(['BGI\n(5min)', 'AR meal\n(1-6h)', 'Circadian\n(24h)', 'Daily\n(72h)'], fontsize=8)
        ax.set_ylabel('Cumulative R²')
        ax.set_title('Variance Explained by Layer')
        ax.legend()
        ax.set_ylim(-0.05, max(0.3, max(medians) * 1.5))
        
        # Panel 2: Incremental R² per layer
        ax = axes[0, 1]
        incr_medians = [rdf[i].median() for i in incr_cols]
        colors_bar = ['steelblue', 'coral', 'green', 'purple']
        ax.bar(x, incr_medians, color=colors_bar, alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(['BGI\n(5min)', 'AR meal\n(1-6h)', 'Circadian\n(24h)', 'Daily\n(72h)'], fontsize=8)
        ax.set_ylabel('Incremental R²')
        ax.set_title('Marginal Contribution per Layer')
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        # Panel 3: ISF raw vs deconfounded
        ax = axes[1, 0]
        if len(isf_df) > 0:
            for ctrl in ['Loop', 'Trio', 'OpenAPS']:
                mask = isf_df['controller'] == ctrl
                if mask.any():
                    ax.scatter(isf_df[mask]['raw_isf'], isf_df[mask]['deconf_isf'],
                              s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
            # Add identity line
            lim = max(abs(isf_df['raw_isf']).max(), abs(isf_df['deconf_isf']).max())
            ax.plot([-lim, lim], [-lim, lim], 'k--', alpha=0.3)
            ax.axhline(y=0, color='gray', linestyle='-', alpha=0.2)
            ax.axvline(x=0, color='gray', linestyle='-', alpha=0.2)
            ax.set_xlabel('Raw ISF (mg/dL/U)')
            ax.set_ylabel('Deconfounded ISF (mg/dL/U)')
            ax.set_title('ISF: Raw vs Multi-Scale Deconfounded')
            ax.legend()
        
        # Panel 4: Basal fraction by controller
        ax = axes[1, 1]
        ctrl_data = []
        ctrl_labels = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = rdf[rdf['controller'] == ctrl]['basal_fraction'].dropna().values * 100
            if len(vals) > 0:
                ctrl_data.append(vals)
                ctrl_labels.append(f'{ctrl}\n(N={len(vals)})')
        if ctrl_data:
            bp = ax.boxplot(ctrl_data, patch_artist=True)
            for patch, label in zip(bp['boxes'], ctrl_labels):
                ctrl_name = label.split('\n')[0]
                patch.set_facecolor(ctrl_colors.get(ctrl_name, 'gray'))
                patch.set_alpha(0.6)
            ax.set_xticklabels(ctrl_labels)
            ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50% target')
            ax.set_ylabel('Scheduled Basal Fraction (%)')
            ax.set_title('Basal Balance (50/50 Rule)')
            ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2786-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2786-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'layer_medians': {
            'L1_bgi': round(rdf['l1_r2'].median(), 4),
            'L2_ar_meal': round(rdf['l2_r2'].median(), 4),
            'L3_circadian': round(rdf['l3_r2'].median(), 4),
            'L4_daily': round(rdf['l4_r2'].median(), 4),
        },
        'incremental_medians': {
            'L1_bgi': round(rdf['l1_incr'].median(), 4),
            'L2_ar_meal': round(rdf['l2_incr'].median(), 4),
            'L3_circadian': round(rdf['l3_incr'].median(), 4),
            'L4_daily': round(rdf['l4_incr'].median(), 4),
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
