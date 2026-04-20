#!/usr/bin/env python3
"""EXP-2783: Controller Effort & Compensation Quantification

From EXP-2782: Trio has TIR=87% despite 10/12 patients having basal
too low (27% vs target 50%). This means the oref1 controller is
doing MASSIVE compensation work via SMBs.

This experiment quantifies:
1. Controller "effort" — how much extra insulin does the controller deliver?
2. SMB burden — frequency and size of SMBs across controllers
3. Basal suspension frequency — how often does controller zero-out basal?
4. Controller volatility — variance in insulin delivery rate

For AID authors, this reveals:
- Whether oref1's SMB compensation masks settings problems
- How much battery/communication overhead the extra SMBs create
- Whether Loop's more conservative approach is better for the patient

Success criteria (3/5 to PASS):
  H1: Trio SMB frequency >3x Loop SMB frequency
  H2: Trio has higher insulin delivery volatility than Loop
  H3: Basal suspension correlates with basal-too-low assessment
  H4: Controller effort correlates inversely with basal fraction (r<-0.3)
  H5: Net basal variance is higher for patients with wrong settings
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2783"
TITLE = "Controller Effort & Compensation"
OUT_JSON = Path("externals/experiments/exp-2783_controller_effort.json")
OUT_VIS = Path("tools/visualizations/controller-effort")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def classify_controller(pid):
    if pid in LOOP_IDS or len(pid) == 1:
        return 'Loop'
    if pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Trio'

def analyze_effort(patient_df, pid):
    """Quantify controller effort metrics."""
    df = patient_df.sort_values('time').copy()
    
    controller = classify_controller(pid)
    basal_rate = df['scheduled_basal_rate'].median()
    if pd.isna(basal_rate) or basal_rate <= 0:
        return None
    
    n_rows = len(df)
    hours = n_rows * 5 / 60  # total hours of data
    
    # SMB metrics
    smb_col = df['bolus_smb'].fillna(0) if 'bolus_smb' in df.columns else pd.Series(0, index=df.index)
    smb_events = (smb_col > 0).sum()
    smb_per_hour = smb_events / hours
    smb_total = smb_col.sum()
    smb_mean_size = smb_col[smb_col > 0].mean() if smb_events > 0 else 0
    
    # User bolus metrics
    bolus_events = (df['bolus'].fillna(0) > 0).sum()
    bolus_per_day = bolus_events / (hours / 24)
    bolus_total = df['bolus'].fillna(0).sum()
    
    # Net basal metrics (deviation from scheduled)
    net_basal = df['net_basal'].fillna(0) if 'net_basal' in df.columns else pd.Series(0, index=df.index)
    
    # Basal suspension: net_basal very negative (controller reducing basal)
    actual_basal_rate = basal_rate + net_basal * 12  # convert back to U/h
    suspension_pct = (actual_basal_rate < basal_rate * 0.1).mean() * 100  # <10% of scheduled
    high_temp_pct = (actual_basal_rate > basal_rate * 1.5).mean() * 100  # >150% of scheduled
    
    # Net basal volatility
    nb_std = net_basal.std()
    nb_cv = nb_std / (abs(net_basal.mean()) + 0.001)
    
    # Total insulin accounting
    scheduled_basal_total = (basal_rate / 12.0) * n_rows
    actual_basal_total = scheduled_basal_total + (net_basal / 12.0).sum()
    tdd = bolus_total + smb_total + actual_basal_total
    
    basal_fraction = actual_basal_total / tdd if tdd > 0 else np.nan
    smb_fraction = smb_total / tdd if tdd > 0 else 0
    
    # Controller "effort" = proportion of insulin delivered via active decisions
    # (SMBs + temp basal changes, NOT scheduled basal or user bolus)
    controller_insulin = smb_total + abs(net_basal / 12.0).sum()
    effort_fraction = controller_insulin / tdd if tdd > 0 else 0
    
    # TIR
    glucose = df['glucose'].dropna()
    tir = (glucose.between(70, 180)).mean() * 100 if len(glucose) > 0 else 0
    below = (glucose < 70).mean() * 100 if len(glucose) > 0 else 0
    above = (glucose > 180).mean() * 100 if len(glucose) > 0 else 0
    
    # Glucose volatility
    glucose_std = glucose.std()
    glucose_cv = glucose_std / glucose.mean() if glucose.mean() > 0 else 0
    
    return {
        'patient_id': pid,
        'controller': controller,
        'hours': round(hours, 0),
        'tir': round(tir, 1),
        'below_70': round(below, 1),
        'above_180': round(above, 1),
        'glucose_cv': round(glucose_cv, 3),
        'smb': {
            'events': smb_events,
            'per_hour': round(smb_per_hour, 2),
            'total_units': round(smb_total, 1),
            'mean_size': round(smb_mean_size, 3),
            'fraction_tdd': round(smb_fraction, 3),
        },
        'bolus': {
            'events': bolus_events,
            'per_day': round(bolus_per_day, 1),
            'total_units': round(bolus_total, 1),
        },
        'basal': {
            'scheduled_rate': round(basal_rate, 2),
            'fraction_tdd': round(basal_fraction, 3) if not np.isnan(basal_fraction) else None,
            'suspension_pct': round(suspension_pct, 1),
            'high_temp_pct': round(high_temp_pct, 1),
        },
        'effort': {
            'controller_fraction': round(effort_fraction, 3),
            'net_basal_std': round(nb_std, 4),
            'tdd': round(tdd, 1),
        },
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2783: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_effort(pdf, pid)
        if r is None:
            print(f"  {pid}: skipped")
            continue
        results[pid] = r
        
        print(f"  {pid} [{r['controller']:<7}] TIR={r['tir']:.0f}% "
              f"SMB/h={r['smb']['per_hour']:.1f} susp={r['basal']['suspension_pct']:.0f}% "
              f"effort={r['effort']['controller_fraction']:.0f}% "
              f"basal={r['basal']['fraction_tdd']*100:.0f}%" if r['basal']['fraction_tdd'] else "N/A")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n = len(results)
    
    # Controller comparison
    print(f"\n{'='*60}")
    print(f"CONTROLLER COMPARISON")
    print(f"{'='*60}")
    
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cr = {pid: r for pid, r in results.items() if r['controller'] == ctrl}
        if not cr:
            continue
        
        tirs = [r['tir'] for r in cr.values()]
        smb_rates = [r['smb']['per_hour'] for r in cr.values()]
        susp_pcts = [r['basal']['suspension_pct'] for r in cr.values()]
        efforts = [r['effort']['controller_fraction'] for r in cr.values()]
        basal_fracs = [r['basal']['fraction_tdd'] for r in cr.values() 
                      if r['basal']['fraction_tdd'] is not None]
        
        print(f"\n  {ctrl} (N={len(cr)}):")
        print(f"    TIR:              {np.median(tirs):.0f}%")
        print(f"    SMB/hour:         {np.median(smb_rates):.1f}")
        print(f"    Basal suspension: {np.median(susp_pcts):.0f}%")
        print(f"    Controller effort:{np.median(efforts)*100:.0f}% of TDD")
        print(f"    Basal fraction:   {np.median(basal_fracs)*100:.0f}%" if basal_fracs else "")
    
    # Hypothesis testing
    loop = {p: r for p, r in results.items() if r['controller'] == 'Loop'}
    trio = {p: r for p, r in results.items() if r['controller'] == 'Trio'}
    
    # H1: Trio SMB freq > 3x Loop
    loop_smb = [r['smb']['per_hour'] for r in loop.values()]
    trio_smb = [r['smb']['per_hour'] for r in trio.values()]
    h1 = np.median(trio_smb) > 3 * np.median(loop_smb) if loop_smb and trio_smb else False
    
    # H2: Trio higher delivery volatility
    loop_std = [r['effort']['net_basal_std'] for r in loop.values()]
    trio_std = [r['effort']['net_basal_std'] for r in trio.values()]
    h2 = np.median(trio_std) > np.median(loop_std) if loop_std and trio_std else False
    
    # H3: Suspension correlates with basal-too-low
    all_basal_fracs = [r['basal']['fraction_tdd'] for r in results.values() 
                      if r['basal']['fraction_tdd'] is not None]
    all_susp = [r['basal']['suspension_pct'] for r in results.values()
               if r['basal']['fraction_tdd'] is not None]
    if len(all_basal_fracs) > 5:
        r_susp, _ = stats.pearsonr(all_basal_fracs, all_susp)
        h3 = r_susp < -0.2  # Negative: lower basal → more suspension
    else:
        r_susp = 0
        h3 = False
    
    # H4: Effort inversely correlates with basal fraction
    all_efforts = [r['effort']['controller_fraction'] for r in results.values()
                  if r['basal']['fraction_tdd'] is not None]
    if len(all_basal_fracs) > 5 and len(all_efforts) == len(all_basal_fracs):
        r_effort, _ = stats.pearsonr(all_basal_fracs, all_efforts)
        h4 = r_effort < -0.3
    else:
        r_effort = 0
        h4 = False
    
    # H5: Net basal variance higher for wrong settings
    wrong = [r['effort']['net_basal_std'] for r in results.values()
            if r['basal']['fraction_tdd'] is not None and r['basal']['fraction_tdd'] < 0.4]
    right = [r['effort']['net_basal_std'] for r in results.values()
            if r['basal']['fraction_tdd'] is not None and r['basal']['fraction_tdd'] >= 0.4]
    h5 = np.median(wrong) > np.median(right) if wrong and right else False
    
    hypotheses = {
        'H1_trio_smb_gt3x_loop': {'pass': bool(h1),
            'value': f"Trio={np.median(trio_smb):.1f}/h vs Loop={np.median(loop_smb):.1f}/h ({np.median(trio_smb)/max(np.median(loop_smb),0.01):.1f}x)" if trio_smb and loop_smb else "N/A"},
        'H2_trio_higher_volatility': {'pass': bool(h2),
            'value': f"Trio={np.median(trio_std):.4f} vs Loop={np.median(loop_std):.4f}" if trio_std and loop_std else "N/A"},
        'H3_suspension_correlates_basal': {'pass': bool(h3),
            'value': f"r={r_susp:.3f}"},
        'H4_effort_inv_basal_fraction': {'pass': bool(h4),
            'value': f"r={r_effort:.3f}"},
        'H5_wrong_settings_more_volatile': {'pass': bool(h5),
            'value': f"wrong={np.median(wrong):.4f} vs right={np.median(right):.4f}" if wrong and right else "N/A"},
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
        fig.suptitle(f'EXP-2783: Controller Effort — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: SMB frequency by controller
        ax = axes[0, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = [r['smb']['per_hour'] for r in results.values() if r['controller'] == ctrl]
            if vals:
                ax.scatter([ctrl] * len(vals), vals, s=80, alpha=0.7, 
                          color=ctrl_colors[ctrl], edgecolors='black')
                ax.plot([ctrl], [np.median(vals)], 'D', color='black', markersize=10)
        ax.set_ylabel('SMBs per Hour')
        ax.set_title('SMB Frequency by Controller')
        
        # Panel 2: Basal fraction vs controller effort
        ax = axes[0, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            pts = [(r['basal']['fraction_tdd'], r['effort']['controller_fraction'])
                   for r in results.values() if r['controller'] == ctrl and r['basal']['fraction_tdd']]
            if pts:
                ax.scatter([p[0]*100 for p in pts], [p[1]*100 for p in pts],
                          label=ctrl, s=60, alpha=0.7, color=ctrl_colors[ctrl])
        ax.set_xlabel('Basal Fraction of TDD (%)')
        ax.set_ylabel('Controller Effort (%)')
        ax.set_title(f'Basal Fraction vs Controller Effort (r={r_effort:.2f})')
        ax.axvline(x=50, color='green', linestyle='--', alpha=0.5)
        ax.legend()
        
        # Panel 3: TIR vs effort
        ax = axes[1, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            pts = [(r['effort']['controller_fraction'], r['tir'])
                   for r in results.values() if r['controller'] == ctrl]
            if pts:
                ax.scatter([p[0]*100 for p in pts], [p[1] for p in pts],
                          label=ctrl, s=60, alpha=0.7, color=ctrl_colors[ctrl])
        ax.set_xlabel('Controller Effort (%)')
        ax.set_ylabel('TIR (%)')
        ax.set_title('TIR vs Controller Effort')
        ax.axhline(y=70, color='red', linestyle='--', alpha=0.3)
        ax.legend()
        
        # Panel 4: Suspension % by controller
        ax = axes[1, 1]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = [r['basal']['suspension_pct'] for r in results.values() if r['controller'] == ctrl]
            if vals:
                ax.scatter([ctrl] * len(vals), vals, s=80, alpha=0.7,
                          color=ctrl_colors[ctrl], edgecolors='black')
                ax.plot([ctrl], [np.median(vals)], 'D', color='black', markersize=10)
        ax.set_ylabel('Basal Suspension (%)')
        ax.set_title('Basal Suspension Frequency')
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2783-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2783-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
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
