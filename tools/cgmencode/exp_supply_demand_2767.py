#!/usr/bin/env python3
"""
EXP-2767: Supply vs Demand Final Decomposition

Using EXP-2764's model (drop = 73 - 6×insulin + 0.8×BG), we now formally
decompose BG corrections into three causal channels:

  DEMAND SIDE (insulin lowers glucose):
    1. User bolus: the correction dose the user delivered
    2. Controller automated: SMBs + basal adjustments
    3. Pre-existing IOB: insulin already in action

  SUPPLY SIDE (glucose production / regulation):
    4. Regression to mean: homeostatic tendency to return to setpoint
    5. Liver glycogen: hepatic glucose output over time

The key question from the user: "In a homeostatic system, to deconfound both
sides, don't we need to model or develop empirical evidence for both sides?"

This experiment measures each channel's contribution empirically.

Hypotheses:
  H1: Regression-to-mean (BG distance from target) explains ≥50% of BG drop
  H2: Controller compensation (basal suspension + SMB) accounts for ≥20%
  H3: User bolus alone accounts for ≤30% of total drop
  H4: The 3-channel decomposition has R² ≥ 0.3 on test data
  H5: Supply-side (channels 4+5) exceeds demand-side user (channel 1)
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_decomposed_episodes(pdf, horizon=24, min_bg=180, min_bolus=0.5, target_bg=110):
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

    episodes = []
    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue
        if np.isnan(bolus[i]) or bolus[i] < min_bolus:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < 3:
            continue

        actual_drop = glucose[i] - valid_f[-1]
        bg_above_target = glucose[i] - target_bg

        # Demand channels
        user_bolus = bolus[i]  # Just the initial correction bolus
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        basal_diff = net_basal[i:i+horizon] - sched_basal[i:i+horizon]
        basal_suspended_units = np.nansum(np.minimum(basal_diff, 0) * 5.0/60.0)
        basal_extra_units = np.nansum(np.maximum(basal_diff, 0) * 5.0/60.0)

        # Total excess insulin
        excess_insulin = np.nansum(bolus[i:i+horizon]) + total_smb + \
                        np.nansum(basal_diff * 5.0/60.0)

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'bg_above_target': bg_above_target,
            'user_bolus': user_bolus,
            'total_smb': total_smb,
            'basal_suspended': basal_suspended_units,
            'basal_extra': basal_extra_units,
            'excess_insulin': excess_insulin,
            'profile_isf': isf[i] if not np.isnan(isf[i]) else 50.0,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {'experiment': 'EXP-2767', 'title': 'Supply vs Demand Decomposition'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    patient_results = {}
    all_channel_fractions = []

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train = pdf.iloc[:split]
        test = pdf.iloc[split:]

        train_eps = extract_decomposed_episodes(train)
        test_eps = extract_decomposed_episodes(test)

        if len(train_eps) < 20 or len(test_eps) < 5:
            continue

        # Multi-channel regression on train
        from sklearn.linear_model import LinearRegression

        # 3-channel model: bg_above_target, user_bolus, controller (smb + basal)
        controller_insulin = train_eps['total_smb'] + train_eps['basal_suspended'] + train_eps['basal_extra']
        X_train = np.column_stack([
            train_eps['bg_above_target'],
            train_eps['user_bolus'],
            controller_insulin,
        ])
        y_train = train_eps['actual_drop'].values

        lr = LinearRegression().fit(X_train, y_train)

        # Channel contributions at median values
        med_bg_above = train_eps['bg_above_target'].median()
        med_bolus = train_eps['user_bolus'].median()
        med_ctrl = (controller_insulin).median()

        # Contribution = coefficient × median value
        bg_contribution = lr.coef_[0] * med_bg_above
        bolus_contribution = lr.coef_[1] * med_bolus
        ctrl_contribution = lr.coef_[2] * med_ctrl
        intercept_contribution = lr.intercept_
        total_predicted = bg_contribution + bolus_contribution + ctrl_contribution + intercept_contribution

        # Fractions
        total_abs = abs(bg_contribution) + abs(bolus_contribution) + abs(ctrl_contribution) + abs(intercept_contribution)
        if total_abs > 0:
            bg_frac = abs(bg_contribution) / total_abs
            bolus_frac = abs(bolus_contribution) / total_abs
            ctrl_frac = abs(ctrl_contribution) / total_abs
            intercept_frac = abs(intercept_contribution) / total_abs
        else:
            bg_frac = bolus_frac = ctrl_frac = intercept_frac = 0.25

        # Test R²
        controller_test = test_eps['total_smb'] + test_eps['basal_suspended'] + test_eps['basal_extra']
        X_test = np.column_stack([
            test_eps['bg_above_target'],
            test_eps['user_bolus'],
            controller_test,
        ])
        y_test = test_eps['actual_drop'].values
        r2_test = lr.score(X_test, y_test)
        r2_train = lr.score(X_train, y_train)

        # Alternative: BG-only model
        lr_bg = LinearRegression().fit(train_eps[['bg_above_target']].values, y_train)
        r2_bg_only = lr_bg.score(test_eps[['bg_above_target']].values, y_test)

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'n_episodes': len(train_eps),
            'coef_bg': float(lr.coef_[0]),
            'coef_bolus': float(lr.coef_[1]),
            'coef_ctrl': float(lr.coef_[2]),
            'intercept': float(lr.intercept_),
            'bg_contribution': float(bg_contribution),
            'bolus_contribution': float(bolus_contribution),
            'ctrl_contribution': float(ctrl_contribution),
            'bg_frac': float(bg_frac),
            'bolus_frac': float(bolus_frac),
            'ctrl_frac': float(ctrl_frac),
            'intercept_frac': float(intercept_frac),
            'r2_train': float(r2_train),
            'r2_test': float(r2_test),
            'r2_bg_only': float(r2_bg_only),
            'med_bg_above': float(med_bg_above),
            'med_bolus': float(med_bolus),
            'med_ctrl': float(med_ctrl),
        }

        all_channel_fractions.append({
            'bg': bg_frac,
            'bolus': bolus_frac,
            'ctrl': ctrl_frac,
            'intercept': intercept_frac,
        })

    print(f"\nPatients analyzed: {len(patient_results)}")

    # ============================================================
    # RESULTS
    # ============================================================
    print(f"\n  {'Patient':<18} {'β(BG)':>6} {'β(bol)':>7} {'β(ctrl)':>7} "
          f"{'BG%':>5} {'Bol%':>5} {'R²test':>7}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['coef_bg']:>6.3f} {pr['coef_bolus']:>7.2f} "
              f"{pr['coef_ctrl']:>7.2f} {pr['bg_frac']*100:>4.0f}% "
              f"{pr['bolus_frac']*100:>4.0f}% {pr['r2_test']:>7.3f}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    bg_fracs = [patient_results[p]['bg_frac'] for p in patient_results]
    med_bg_frac = np.median(bg_fracs)
    h1_pass = med_bg_frac >= 0.50
    print(f"  {'✓' if h1_pass else '✗'} H1: BG regression ≥50%: median {med_bg_frac*100:.1f}%")

    ctrl_fracs = [patient_results[p]['ctrl_frac'] for p in patient_results]
    med_ctrl_frac = np.median(ctrl_fracs)
    h2_pass = med_ctrl_frac >= 0.20
    print(f"  {'✓' if h2_pass else '✗'} H2: Controller ≥20%: median {med_ctrl_frac*100:.1f}%")

    bolus_fracs = [patient_results[p]['bolus_frac'] for p in patient_results]
    med_bolus_frac = np.median(bolus_fracs)
    h3_pass = med_bolus_frac <= 0.30
    print(f"  {'✓' if h3_pass else '✗'} H3: User bolus ≤30%: median {med_bolus_frac*100:.1f}%")

    r2_tests = [patient_results[p]['r2_test'] for p in patient_results]
    med_r2 = np.median(r2_tests)
    h4_pass = med_r2 >= 0.30
    print(f"  {'✓' if h4_pass else '✗'} H4: R² ≥0.30: median {med_r2:.3f}")

    # H5: Supply (BG) > demand user (bolus)
    supply_gt_demand = sum(1 for p in patient_results
                          if patient_results[p]['bg_frac'] > patient_results[p]['bolus_frac'])
    h5_pass = supply_gt_demand / len(patient_results) >= 0.70
    print(f"  {'✓' if h5_pass else '✗'} H5: Supply > demand-user: "
          f"{supply_gt_demand}/{len(patient_results)}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Summary statistics
    print(f"\n  Channel decomposition (median across patients):")
    print(f"    BG regression to mean:  {med_bg_frac*100:.1f}% (supply-side)")
    print(f"    Controller automated:   {med_ctrl_frac*100:.1f}% (demand-side auto)")
    print(f"    User bolus:             {med_bolus_frac*100:.1f}% (demand-side user)")
    med_int_frac = np.median([patient_results[p]['intercept_frac'] for p in patient_results])
    print(f"    Intercept (baseline):   {med_int_frac*100:.1f}% (unattributed)")

    # BG-only vs full model
    r2_bg_onlys = [patient_results[p]['r2_bg_only'] for p in patient_results]
    print(f"\n  BG-only R²: {np.median(r2_bg_onlys):.3f}")
    print(f"  Full model R²: {med_r2:.3f}")
    print(f"  Delta: {(np.median(r2_tests) - np.median(r2_bg_onlys)):.3f}")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'median_bg_frac': float(med_bg_frac)},
        'H2': {'pass': bool(h2_pass), 'median_ctrl_frac': float(med_ctrl_frac)},
        'H3': {'pass': bool(h3_pass), 'median_bolus_frac': float(med_bolus_frac)},
        'H4': {'pass': bool(h4_pass), 'median_r2': float(med_r2)},
        'H5': {'pass': bool(h5_pass), 'supply_gt_demand': supply_gt_demand},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'n_patients': len(patient_results),
        'median_bg_frac': float(med_bg_frac),
        'median_ctrl_frac': float(med_ctrl_frac),
        'median_bolus_frac': float(med_bolus_frac),
        'median_r2': float(med_r2),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2767: Supply vs Demand Decomposition', fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: Stacked bar — channel fractions
        ax = axes[0, 0]
        x = np.arange(len(pids))
        bg_bars = [patient_results[p]['bg_frac'] for p in pids]
        ctrl_bars = [patient_results[p]['ctrl_frac'] for p in pids]
        bolus_bars = [patient_results[p]['bolus_frac'] for p in pids]
        int_bars = [patient_results[p]['intercept_frac'] for p in pids]
        ax.bar(x, bg_bars, color='green', alpha=0.7, label='BG regression (supply)')
        ax.bar(x, ctrl_bars, bottom=bg_bars, color='steelblue', alpha=0.7, label='Controller (demand auto)')
        bottom2 = [b + c for b, c in zip(bg_bars, ctrl_bars)]
        ax.bar(x, bolus_bars, bottom=bottom2, color='coral', alpha=0.7, label='User bolus (demand user)')
        bottom3 = [b + c for b, c in zip(bottom2, bolus_bars)]
        ax.bar(x, int_bars, bottom=bottom3, color='gray', alpha=0.5, label='Intercept')
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Fraction')
        ax.set_title('Channel Contributions')
        ax.legend(fontsize=7)

        # Panel 2: Pie chart — median fractions
        ax = axes[0, 1]
        sizes = [med_bg_frac, med_ctrl_frac, med_bolus_frac, med_int_frac]
        labels = [f'BG regression\n{med_bg_frac*100:.0f}%',
                  f'Controller\n{med_ctrl_frac*100:.0f}%',
                  f'User bolus\n{med_bolus_frac*100:.0f}%',
                  f'Intercept\n{med_int_frac*100:.0f}%']
        colors = ['green', 'steelblue', 'coral', 'gray']
        ax.pie(sizes, labels=labels, colors=colors, autopct='', startangle=90)
        ax.set_title('Median Channel Decomposition')

        # Panel 3: BG coefficient
        ax = axes[0, 2]
        bg_coefs = [patient_results[p]['coef_bg'] for p in pids]
        ax.hist(bg_coefs, bins=20, color='green', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(bg_coefs), color='red', linewidth=2,
                   label=f'Median={np.median(bg_coefs):.3f}')
        ax.set_xlabel('BG Coefficient')
        ax.set_ylabel('Count')
        ax.set_title('BG Regression Strength')
        ax.legend()

        # Panel 4: Bolus vs Controller coefficients
        ax = axes[1, 0]
        bolus_coefs = [patient_results[p]['coef_bolus'] for p in pids]
        ctrl_coefs = [patient_results[p]['coef_ctrl'] for p in pids]
        ax.scatter(bolus_coefs, ctrl_coefs, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.axvline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlabel('Bolus Coefficient')
        ax.set_ylabel('Controller Coefficient')
        ax.set_title('Demand: User vs Auto')

        # Panel 5: R² comparison
        ax = axes[1, 1]
        r2_bg = [patient_results[p]['r2_bg_only'] for p in pids]
        r2_full = [patient_results[p]['r2_test'] for p in pids]
        ax.scatter(r2_bg, r2_full, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(r2_bg + [0.1]), max(r2_full + [0.1])) * 1.1
        ax.plot([min(r2_bg + r2_full) - 0.05, lim], [min(r2_bg + r2_full) - 0.05, lim], 'k--', alpha=0.3)
        ax.set_xlabel('BG-only R²')
        ax.set_ylabel('Full Model R²')
        ax.set_title('BG-only vs Full Model')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary_text = f"""EXP-2767: Supply vs Demand

Hypotheses: {n_pass}/5 PASS

SUPPLY SIDE (homeostatic):
  BG regression to mean: {med_bg_frac*100:.0f}%
  → Distance from target predicts drop
  → BG coef: {np.median(bg_coefs):.3f}/mg/dL

DEMAND SIDE (automated):
  Controller compensation: {med_ctrl_frac*100:.0f}%
  → Basal suspension + SMBs

DEMAND SIDE (user):
  User bolus: {med_bolus_frac*100:.0f}%
  → Manual correction dose

Model performance:
  BG-only R²:  {np.median(r2_bg_onlys):.3f}
  Full model R²: {med_r2:.3f}

Supply > demand-user: {supply_gt_demand}/{len(patient_results)}"""
        ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/supply-demand', exist_ok=True)
        plt.savefig('tools/visualizations/supply-demand/exp-2767-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/supply-demand/exp-2767-dashboard.png")
    except Exception as e:
        print(f"  Dashboard error: {e}")
        traceback.print_exc()

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, (np.bool_,)): return bool(obj)
            return super().default(obj)

    with open('externals/experiments/exp-2767_supply_demand.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2767_supply_demand.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
