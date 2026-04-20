#!/usr/bin/env python3
"""EXP-2777: ISF Gap Reconciliation — Controller Insulin Accounting

The fundamental problem: profile ISF ~55 but observed ISF ~5 (10× gap).

Why? In closed-loop, when BG=250 and drops to 180 (Δ=-70):
  - Profile says: should take 70/55 = 1.3U of insulin
  - But EXCESS insulin observed might be 14U (controller + bolus + SMB)
  - So observed_ISF = 70/14 = 5 mg/dL/U

The controller delivers MUCH more insulin than needed for the correction
because it's also delivering basal-replacement insulin (50/50 rule) and
reacting to transient glucose spikes. Not all observed insulin is 
"correction" insulin.

Approach: Separate insulin into:
  1. EGP-coverage insulin (scheduled basal — not correction)
  2. Controller-response insulin (reactive — confounded)
  3. User-bolus insulin (intentional correction — least confounded)

Then compute ISF from USER BOLUS only:
  ISF_user = BG_drop / user_bolus_dose

This should be much closer to profile ISF because user boluses are
intentional corrections, not confounded controller responses.

Success criteria (3/5 to PASS):
  H1: User-bolus ISF is >3x observed full-data ISF (less confounded)
  H2: User-bolus ISF correlates with profile ISF (r>0.5)
  H3: Controller-adjusted ISF is closer to profile than full-data ISF
  H4: The ISF gap narrows to <5x when accounting for controller contribution
  H5: User-bolus ISF is positive for >80% of patients
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2777"
TITLE = "ISF Gap Reconciliation — Controller Accounting"
OUT_JSON = Path("externals/experiments/exp-2777_isf_gap.json")
OUT_VIS = Path("tools/visualizations/isf-gap")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def analyze_isf_gap(patient_df, pid):
    """Decompose insulin into channels and extract ISF from each."""
    df = patient_df.sort_values('time').copy()
    
    profile_isf = df['scheduled_isf'].median()
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    if 'iob' not in df.columns:
        return None
    
    steps = 24  # 2h window
    
    # Glucose change
    df['glucose_delta_2h'] = df['glucose'].shift(-steps) - df['glucose']
    df['starting_bg'] = df['glucose']
    
    # Channel 1: User bolus (manual correction — least confounded)
    if 'bolus' in df.columns:
        df['user_bolus_2h'] = df['bolus'].fillna(0).rolling(steps, min_periods=1).sum()
    else:
        df['user_bolus_2h'] = 0
    
    # Channel 2: SMB (controller micro-bolus — confounded)
    if 'bolus_smb' in df.columns:
        df['smb_2h'] = df['bolus_smb'].fillna(0).rolling(steps, min_periods=1).sum()
    else:
        df['smb_2h'] = 0
    
    # Channel 3: Net basal (excess above scheduled — controller adjustment)
    if 'net_basal' in df.columns:
        df['net_basal_2h'] = (df['net_basal'].fillna(0) / 12.0).rolling(steps, min_periods=1).sum()
    else:
        df['net_basal_2h'] = 0
    
    # Channel 4: IOB change
    df['iob_delta_2h'] = df['iob'].shift(-steps) - df['iob']
    
    # Total excess = user_bolus + smb + net_basal
    df['total_excess_2h'] = df['user_bolus_2h'] + df['smb_2h'] + df['net_basal_2h']
    
    # Filter to correction episodes (BG > 150, non-zero insulin)
    valid = df.dropna(subset=['glucose_delta_2h']).copy()
    corrections = valid[(valid['starting_bg'] >= 150) & (valid['total_excess_2h'] > 0.1)].copy()
    
    if len(corrections) < 50:
        return None
    
    # --- Method 1: Full regression (all insulin, confounded) ---
    y = corrections['glucose_delta_2h'].values
    X_full = corrections[['starting_bg', 'total_excess_2h']].values
    m_full = LinearRegression().fit(X_full, y)
    full_isf = -m_full.coef_[1]
    full_r2 = m_full.score(X_full, y)
    
    # --- Method 2: User bolus only (corrections with manual bolus) ---
    bolus_corrections = corrections[corrections['user_bolus_2h'] > 0.1]
    if len(bolus_corrections) >= 30:
        X_user = bolus_corrections[['starting_bg', 'user_bolus_2h']].values
        y_user = bolus_corrections['glucose_delta_2h'].values
        m_user = LinearRegression().fit(X_user, y_user)
        user_isf = -m_user.coef_[1]
        user_r2 = m_user.score(X_user, y_user)
    else:
        user_isf = np.nan
        user_r2 = np.nan
    
    # --- Method 3: Multi-channel regression ---
    X_multi = corrections[['starting_bg', 'user_bolus_2h', 'smb_2h', 'net_basal_2h']].values
    m_multi = LinearRegression().fit(X_multi, y)
    multi_coefs = {
        'starting_bg': m_multi.coef_[0],
        'user_bolus': m_multi.coef_[1],
        'smb': m_multi.coef_[2],
        'net_basal': m_multi.coef_[3],
    }
    multi_r2 = m_multi.score(X_multi, y)
    
    # ISF from each channel
    user_bolus_isf = -multi_coefs['user_bolus']
    smb_isf = -multi_coefs['smb']
    net_basal_isf = -multi_coefs['net_basal']
    
    # --- Method 4: Controller-adjusted ISF ---
    # The controller delivers insulin in response to BG. If we control for
    # starting BG, the remaining insulin effect should be the true ISF.
    # Controller contribution ≈ total_excess - user_bolus
    controller_insulin = corrections['smb_2h'] + corrections['net_basal_2h']
    corrections_copy = corrections.copy()
    corrections_copy['controller_2h'] = controller_insulin
    
    X_adj = corrections_copy[['starting_bg', 'user_bolus_2h', 'controller_2h']].values
    m_adj = LinearRegression().fit(X_adj, y)
    adj_user_isf = -m_adj.coef_[1]
    adj_controller_isf = -m_adj.coef_[2]
    adj_r2 = m_adj.score(X_adj, y)
    
    # Gap ratios
    gap_full = profile_isf / full_isf if full_isf > 0 else np.nan
    gap_user = profile_isf / user_isf if not np.isnan(user_isf) and user_isf > 0 else np.nan
    gap_multi_user = profile_isf / user_bolus_isf if user_bolus_isf > 0 else np.nan
    
    return {
        'patient_id': pid,
        'profile_isf': round(profile_isf, 1),
        'n_corrections': len(corrections),
        'n_bolus_corrections': len(bolus_corrections) if 'bolus_corrections' in dir() else 0,
        'full_data': {
            'isf': round(full_isf, 2),
            'r2': round(full_r2, 4),
            'gap_ratio': round(gap_full, 1) if not np.isnan(gap_full) else None,
        },
        'user_bolus_only': {
            'isf': round(user_isf, 2) if not np.isnan(user_isf) else None,
            'r2': round(user_r2, 4) if not np.isnan(user_r2) else None,
            'gap_ratio': round(gap_user, 1) if not np.isnan(gap_user) else None,
        },
        'multi_channel': {
            'user_bolus_isf': round(user_bolus_isf, 2),
            'smb_isf': round(smb_isf, 2),
            'net_basal_isf': round(net_basal_isf, 2),
            'r2': round(multi_r2, 4),
            'gap_ratio': round(gap_multi_user, 1) if not np.isnan(gap_multi_user) else None,
        },
        'controller_adjusted': {
            'user_isf': round(adj_user_isf, 2),
            'controller_isf': round(adj_controller_isf, 2),
            'r2': round(adj_r2, 4),
        },
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2777: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_isf_gap(pdf, pid)
        
        if r is None:
            print(f"  {pid}: skipped")
            continue
        
        results[pid] = r
        
        full = r['full_data']
        user = r['user_bolus_only']
        multi = r['multi_channel']
        
        user_str = f"user_ISF={user['isf']:.1f}" if user['isf'] else "user_ISF=N/A"
        if multi['gap_ratio'] and full['gap_ratio']:
            gap_str = f"gap={full['gap_ratio']:.0f}x→{multi['gap_ratio']:.0f}x"
        elif full['gap_ratio']:
            gap_str = f"gap={full['gap_ratio']:.0f}x"
        else:
            gap_str = "gap=N/A"
        
        print(f"  {pid}: profile={r['profile_isf']:.0f} full_ISF={full['isf']:.1f} "
              f"{user_str} multi_user={multi['user_bolus_isf']:.1f} {gap_str}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n_total = len(results)
    
    # Aggregate
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n_total})")
    print(f"{'='*60}")
    
    profile_isfs = [r['profile_isf'] for r in results.values()]
    full_isfs = [r['full_data']['isf'] for r in results.values()]
    user_isfs = [r['user_bolus_only']['isf'] for r in results.values() if r['user_bolus_only']['isf']]
    multi_user_isfs = [r['multi_channel']['user_bolus_isf'] for r in results.values()]
    
    print(f"\nISF comparison (medians):")
    print(f"  Profile ISF:             {np.median(profile_isfs):.0f} mg/dL/U")
    print(f"  Full-data ISF:           {np.median(full_isfs):.1f} mg/dL/U (gap: {np.median(profile_isfs)/np.median(full_isfs):.0f}x)")
    if user_isfs:
        print(f"  User-bolus-only ISF:     {np.median(user_isfs):.1f} mg/dL/U (gap: {np.median(profile_isfs)/max(np.median(user_isfs), 0.01):.0f}x)")
    print(f"  Multi-channel user ISF:  {np.median(multi_user_isfs):.1f} mg/dL/U (gap: {np.median(profile_isfs)/max(np.median(multi_user_isfs), 0.01):.0f}x)")
    
    # Correlation with profile
    r_full, _ = stats.pearsonr(profile_isfs, full_isfs)
    
    multi_pos = [(r['profile_isf'], r['multi_channel']['user_bolus_isf']) for r in results.values() 
                 if r['multi_channel']['user_bolus_isf'] > 0]
    if len(multi_pos) > 5:
        r_multi, _ = stats.pearsonr([x[0] for x in multi_pos], [x[1] for x in multi_pos])
    else:
        r_multi = 0
    
    user_pos = [(r['profile_isf'], r['user_bolus_only']['isf']) for r in results.values() 
                if r['user_bolus_only']['isf'] and r['user_bolus_only']['isf'] > 0]
    if len(user_pos) > 5:
        r_user, _ = stats.pearsonr([x[0] for x in user_pos], [x[1] for x in user_pos])
    else:
        r_user = 0
    
    print(f"\nCorrelations with profile ISF:")
    print(f"  Full-data:          r={r_full:.3f}")
    print(f"  User-bolus-only:    r={r_user:.3f}")
    print(f"  Multi-channel user: r={r_multi:.3f}")
    
    # Channel ISFs
    smb_isfs = [r['multi_channel']['smb_isf'] for r in results.values()]
    nb_isfs = [r['multi_channel']['net_basal_isf'] for r in results.values()]
    
    print(f"\nMulti-channel ISF medians:")
    print(f"  User bolus:  {np.median(multi_user_isfs):.1f} mg/dL/U")
    print(f"  SMB:         {np.median(smb_isfs):.1f} mg/dL/U")
    print(f"  Net basal:   {np.median(nb_isfs):.1f} mg/dL/U")
    
    # Hypothesis testing
    h1 = np.median(multi_user_isfs) > 3 * np.median(full_isfs)
    h2 = r_user > 0.5 or r_multi > 0.5
    
    adj_isfs = [r['controller_adjusted']['user_isf'] for r in results.values()]
    adj_gap = np.median(profile_isfs) / max(np.median(adj_isfs), 0.01)
    full_gap = np.median(profile_isfs) / max(np.median(full_isfs), 0.01)
    h3 = adj_gap < full_gap
    
    h4 = np.median(profile_isfs) / max(np.median(multi_user_isfs), 0.01) < 5
    
    n_positive = sum(1 for r in results.values() if r['multi_channel']['user_bolus_isf'] > 0)
    h5 = n_positive > n_total * 0.8
    
    hypotheses = {
        'H1_user_isf_gt3x_full': {'pass': bool(h1),
            'value': f"{np.median(multi_user_isfs):.1f} vs {np.median(full_isfs):.1f} ({np.median(multi_user_isfs)/max(np.median(full_isfs),0.01):.1f}x)"},
        'H2_user_isf_correlates_profile': {'pass': bool(h2),
            'value': f"r_user={r_user:.3f}, r_multi={r_multi:.3f}"},
        'H3_adj_isf_closer_to_profile': {'pass': bool(h3),
            'value': f"adj_gap={adj_gap:.0f}x vs full_gap={full_gap:.0f}x"},
        'H4_gap_narrows_to_lt5x': {'pass': bool(h4),
            'value': f"{np.median(profile_isfs)/max(np.median(multi_user_isfs),0.01):.0f}x"},
        'H5_user_isf_positive_80pct': {'pass': bool(h5),
            'value': f"{n_positive}/{n_total}"},
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
        fig.suptitle(f'EXP-2777: ISF Gap Reconciliation — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: ISF comparison by method
        ax = axes[0, 0]
        sorted_pids = sorted(results.keys(), key=lambda p: results[p]['profile_isf'])
        x = np.arange(n_total)
        ax.bar(x - 0.3, [results[p]['profile_isf'] for p in sorted_pids], 0.3,
               label='Profile', alpha=0.7, color='gold')
        ax.bar(x, [results[p]['multi_channel']['user_bolus_isf'] for p in sorted_pids], 0.3,
               label='Multi-ch user', alpha=0.7, color='steelblue')
        ax.bar(x + 0.3, [results[p]['full_data']['isf'] for p in sorted_pids], 0.3,
               label='Full-data', alpha=0.7, color='coral')
        ax.set_xlabel('Patient (sorted by profile ISF)')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title('ISF by Extraction Method')
        ax.legend(fontsize=8)
        ax.set_xticks([])
        
        # Panel 2: Channel ISFs
        ax = axes[0, 1]
        channel_data = [multi_user_isfs, smb_isfs, nb_isfs]
        channel_labels = ['User\nBolus', 'SMB', 'Net\nBasal']
        channel_colors = ['steelblue', 'coral', 'green']
        bp = ax.boxplot(channel_data, patch_artist=True)
        for patch, col in zip(bp['boxes'], channel_colors):
            patch.set_facecolor(col)
            patch.set_alpha(0.6)
        ax.set_xticklabels(channel_labels)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.axhline(y=np.median(profile_isfs), color='gold', linestyle='--', 
                   label=f'Profile median ({np.median(profile_isfs):.0f})')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title('ISF by Insulin Channel')
        ax.legend(fontsize=8)
        
        # Panel 3: Gap ratio comparison
        ax = axes[1, 0]
        methods = ['Full\nData', 'Multi-ch\nUser', 'Controller\nAdjusted']
        gaps = [full_gap, 
                np.median(profile_isfs)/max(np.median(multi_user_isfs), 0.01),
                adj_gap]
        bars = ax.bar(methods, gaps, color=['coral', 'steelblue', 'green'], edgecolor='black', alpha=0.7)
        for bar, val in zip(bars, gaps):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                    f'{val:.0f}×', ha='center', fontsize=12)
        ax.axhline(y=1, color='green', linestyle='--', label='No gap (1×)')
        ax.set_ylabel('Gap Ratio (profile/observed)')
        ax.set_title('ISF Gap by Method')
        ax.legend(fontsize=8)
        
        # Panel 4: Profile vs extracted scatter
        ax = axes[1, 1]
        ax.scatter(profile_isfs, multi_user_isfs, alpha=0.6, s=50, label='Multi-ch user')
        ax.scatter(profile_isfs, full_isfs, alpha=0.6, s=50, marker='s', label='Full-data')
        max_val = max(profile_isfs) + 10
        ax.plot([0, max_val], [0, max_val], 'r--', alpha=0.3, label='1:1')
        ax.set_xlabel('Profile ISF (mg/dL/U)')
        ax.set_ylabel('Extracted ISF (mg/dL/U)')
        ax.set_title(f'Profile vs Extracted (r_multi={r_multi:.2f})')
        ax.legend(fontsize=8)
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2777-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2777-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n_total,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'aggregate': {
            'median_profile_isf': round(np.median(profile_isfs), 1),
            'median_full_isf': round(np.median(full_isfs), 2),
            'median_user_isf': round(np.median(user_isfs), 2) if user_isfs else None,
            'median_multi_user_isf': round(np.median(multi_user_isfs), 2),
            'median_smb_isf': round(np.median(smb_isfs), 2),
            'median_nb_isf': round(np.median(nb_isfs), 2),
            'gap_full': round(full_gap, 1),
            'gap_multi_user': round(np.median(profile_isfs)/max(np.median(multi_user_isfs), 0.01), 1),
            'r_full_profile': round(r_full, 3),
            'r_user_profile': round(r_user, 3),
            'r_multi_profile': round(r_multi, 3),
        },
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
