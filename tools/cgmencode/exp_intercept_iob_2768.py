#!/usr/bin/env python3
"""
EXP-2768: Intercept & Pre-IOB Decomposition

EXP-2767 found 30% of BG correction is "intercept" — unattributed baseline.
This experiment decomposes it by adding pre-existing IOB at correction time
and carbs-on-board as additional channels.

Full model:
  actual_drop = β0 + β1×bg_above_target + β2×user_bolus +
                β3×controller_insulin + β4×pre_iob + β5×carbs

If pre-IOB absorbs significant intercept variance, the intercept should shrink.
The residual intercept after IOB is our best estimate of the supply-side
(hepatic/EGP) contribution.

Hypotheses:
  H1: Pre-IOB explains ≥10% of total drop (significant channel)
  H2: Adding IOB increases R² by ≥0.03 over 3-channel model
  H3: Intercept decreases ≥20% with IOB included
  H4: Carbs contribute ≥5% (meal overlap confounding)
  H5: Residual intercept (hepatic estimate) ≥10 mg/dL
"""

import json, sys, os, traceback
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_full_episodes(pdf, horizon=24, min_bg=180, min_bolus=0.5, target_bg=110):
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    iob = pdf['iob'].values if 'iob' in pdf.columns else np.zeros(len(pdf))
    carbs = pdf['carbs'].values if 'carbs' in pdf.columns else np.zeros(len(pdf))

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

        user_bolus = bolus[i]
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        basal_diff = net_basal[i:i+horizon] - sched_basal[i:i+horizon]
        controller_insulin = total_smb + np.nansum(basal_diff * 5.0/60.0)

        pre_iob = iob[i] if not np.isnan(iob[i]) else 0.0
        # Subtract the bolus we just gave to get pre-existing IOB
        pre_iob = max(0, pre_iob - bolus[i])

        carbs_window = np.nansum(carbs[max(0, i-12):i+horizon])  # 1h before + 2h after

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'bg_above_target': bg_above_target,
            'user_bolus': user_bolus,
            'controller_insulin': controller_insulin,
            'pre_iob': pre_iob,
            'carbs': carbs_window,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {'experiment': 'EXP-2768', 'title': 'Intercept & Pre-IOB Decomposition'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    patient_results = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train_eps = extract_full_episodes(pdf.iloc[:split])
        test_eps = extract_full_episodes(pdf.iloc[split:])

        if len(train_eps) < 20 or len(test_eps) < 5:
            continue

        y_train = train_eps['actual_drop'].values
        y_test = test_eps['actual_drop'].values

        # Model A: 3-channel (from EXP-2767)
        Xa_train = train_eps[['bg_above_target', 'user_bolus', 'controller_insulin']].values
        Xa_test = test_eps[['bg_above_target', 'user_bolus', 'controller_insulin']].values
        lr_a = LinearRegression().fit(Xa_train, y_train)
        r2_a = lr_a.score(Xa_test, y_test)

        # Model B: 5-channel (+ IOB + carbs)
        Xb_train = train_eps[['bg_above_target', 'user_bolus', 'controller_insulin',
                               'pre_iob', 'carbs']].values
        Xb_test = test_eps[['bg_above_target', 'user_bolus', 'controller_insulin',
                             'pre_iob', 'carbs']].values
        lr_b = LinearRegression().fit(Xb_train, y_train)
        r2_b = lr_b.score(Xb_test, y_test)

        # Channel contributions at median
        meds = train_eps[['bg_above_target', 'user_bolus', 'controller_insulin',
                           'pre_iob', 'carbs']].median()
        contributions = {}
        channel_names = ['bg_above_target', 'user_bolus', 'controller_insulin', 'pre_iob', 'carbs']
        total_abs = abs(lr_b.intercept_)
        for ci, cn in enumerate(channel_names):
            contributions[cn] = float(lr_b.coef_[ci] * meds.iloc[ci])
            total_abs += abs(contributions[cn])

        fractions = {}
        for cn in channel_names:
            fractions[cn] = abs(contributions[cn]) / total_abs if total_abs > 0 else 0
        fractions['intercept'] = abs(lr_b.intercept_) / total_abs if total_abs > 0 else 0

        patient_results[pid] = {
            'n_episodes': len(train_eps),
            'r2_3ch': float(r2_a),
            'r2_5ch': float(r2_b),
            'r2_delta': float(r2_b - r2_a),
            'intercept_3ch': float(lr_a.intercept_),
            'intercept_5ch': float(lr_b.intercept_),
            'coefs_5ch': {cn: float(lr_b.coef_[ci]) for ci, cn in enumerate(channel_names)},
            'contributions': contributions,
            'fractions': fractions,
            'med_pre_iob': float(meds['pre_iob']),
            'med_carbs': float(meds['carbs']),
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # Summary table
    print(f"\n  {'Patient':<18} {'R²_3ch':>7} {'R²_5ch':>7} {'Δ':>6} "
          f"{'Int3':>6} {'Int5':>6} {'IOB%':>5} {'Carb%':>5}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['r2_3ch']:>7.3f} {pr['r2_5ch']:>7.3f} "
              f"{pr['r2_delta']:>6.3f} {pr['intercept_3ch']:>6.1f} "
              f"{pr['intercept_5ch']:>6.1f} "
              f"{pr['fractions'].get('pre_iob', 0)*100:>4.0f}% "
              f"{pr['fractions'].get('carbs', 0)*100:>4.0f}%")

    # Hypotheses
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    iob_fracs = [patient_results[p]['fractions']['pre_iob'] for p in patient_results]
    med_iob_frac = np.median(iob_fracs)
    h1_pass = med_iob_frac >= 0.10
    print(f"  {'✓' if h1_pass else '✗'} H1: IOB ≥10%: median {med_iob_frac*100:.1f}%")

    r2_deltas = [patient_results[p]['r2_delta'] for p in patient_results]
    med_delta = np.median(r2_deltas)
    h2_pass = med_delta >= 0.03
    print(f"  {'✓' if h2_pass else '✗'} H2: R² delta ≥0.03: median {med_delta:.3f}")

    int3s = [patient_results[p]['intercept_3ch'] for p in patient_results]
    int5s = [patient_results[p]['intercept_5ch'] for p in patient_results]
    med_int3 = np.median(int3s)
    med_int5 = np.median(int5s)
    int_decrease = (abs(med_int3) - abs(med_int5)) / abs(med_int3) if abs(med_int3) > 0 else 0
    h3_pass = int_decrease >= 0.20
    print(f"  {'✓' if h3_pass else '✗'} H3: Intercept ↓≥20%: "
          f"{med_int3:.1f}→{med_int5:.1f} ({int_decrease*100:.0f}%)")

    carb_fracs = [patient_results[p]['fractions']['carbs'] for p in patient_results]
    med_carb_frac = np.median(carb_fracs)
    h4_pass = med_carb_frac >= 0.05
    print(f"  {'✓' if h4_pass else '✗'} H4: Carbs ≥5%: median {med_carb_frac*100:.1f}%")

    h5_pass = abs(med_int5) >= 10
    print(f"  {'✓' if h5_pass else '✗'} H5: Residual intercept ≥10: {med_int5:.1f} mg/dL")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Supply-side estimate
    print(f"\n  BILATERAL DECOMPOSITION:")
    bg_fracs = [patient_results[p]['fractions']['bg_above_target'] for p in patient_results]
    ctrl_fracs = [patient_results[p]['fractions']['controller_insulin'] for p in patient_results]
    bol_fracs = [patient_results[p]['fractions']['user_bolus'] for p in patient_results]
    int_fracs = [patient_results[p]['fractions']['intercept'] for p in patient_results]

    print(f"    BG regression (supply):    {np.median(bg_fracs)*100:.1f}%")
    print(f"    Pre-existing IOB (demand): {med_iob_frac*100:.1f}%")
    print(f"    Controller auto (demand):  {np.median(ctrl_fracs)*100:.1f}%")
    print(f"    User bolus (demand):       {np.median(bol_fracs)*100:.1f}%")
    print(f"    Carbs (supply-opposing):   {med_carb_frac*100:.1f}%")
    print(f"    Intercept (residual):      {np.median(int_fracs)*100:.1f}%")
    print(f"    Residual = hepatic estimate: {med_int5:.1f} mg/dL")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'med_iob_frac': float(med_iob_frac)},
        'H2': {'pass': bool(h2_pass), 'med_r2_delta': float(med_delta)},
        'H3': {'pass': bool(h3_pass), 'int3': float(med_int3), 'int5': float(med_int5)},
        'H4': {'pass': bool(h4_pass), 'med_carb_frac': float(med_carb_frac)},
        'H5': {'pass': bool(h5_pass), 'residual_intercept': float(med_int5)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'n_patients': len(patient_results),
        'med_r2_3ch': float(np.median([patient_results[p]['r2_3ch'] for p in patient_results])),
        'med_r2_5ch': float(np.median([patient_results[p]['r2_5ch'] for p in patient_results])),
        'med_iob_frac': float(med_iob_frac),
        'med_carb_frac': float(med_carb_frac),
        'residual_intercept': float(med_int5),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2768: Intercept & Pre-IOB Decomposition', fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: Intercept comparison 3ch vs 5ch
        ax = axes[0, 0]
        ax.scatter(int3s, int5s, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(int3s), max(int5s)) * 1.1
        ax.plot([min(int3s + int5s), lim], [min(int3s + int5s), lim], 'k--', alpha=0.3)
        ax.set_xlabel('3-Channel Intercept')
        ax.set_ylabel('5-Channel Intercept')
        ax.set_title(f'Intercept Change ({int_decrease*100:.0f}% decrease)')

        # Panel 2: R² improvement
        ax = axes[0, 1]
        r2_3 = [patient_results[p]['r2_3ch'] for p in pids]
        r2_5 = [patient_results[p]['r2_5ch'] for p in pids]
        ax.scatter(r2_3, r2_5, s=60, alpha=0.7, c='green', edgecolors='black')
        lim = max(max(r2_3 + [0.1]), max(r2_5 + [0.1])) * 1.1
        ax.plot([min(r2_3 + r2_5) - 0.05, lim], [min(r2_3 + r2_5) - 0.05, lim], 'k--', alpha=0.3)
        ax.set_xlabel('3-Channel R²')
        ax.set_ylabel('5-Channel R²')
        ax.set_title(f'Model Improvement (median Δ={med_delta:.3f})')

        # Panel 3: IOB fraction distribution
        ax = axes[0, 2]
        ax.hist(iob_fracs, bins=15, color='orange', alpha=0.7, edgecolor='black')
        ax.axvline(med_iob_frac, color='red', linewidth=2, label=f'Median={med_iob_frac*100:.1f}%')
        ax.set_xlabel('Pre-IOB Fraction')
        ax.set_ylabel('Count')
        ax.set_title('IOB Contribution')
        ax.legend()

        # Panel 4: 5-channel pie
        ax = axes[1, 0]
        sizes = [np.median(bg_fracs), np.median(ctrl_fracs), np.median(bol_fracs),
                 med_iob_frac, med_carb_frac, np.median(int_fracs)]
        labels = [f'BG regr\n{sizes[0]*100:.0f}%', f'Controller\n{sizes[1]*100:.0f}%',
                  f'User bolus\n{sizes[2]*100:.0f}%', f'Pre-IOB\n{sizes[3]*100:.0f}%',
                  f'Carbs\n{sizes[4]*100:.0f}%', f'Residual\n{sizes[5]*100:.0f}%']
        colors = ['green', 'steelblue', 'coral', 'orange', 'gold', 'gray']
        ax.pie(sizes, labels=labels, colors=colors, startangle=90)
        ax.set_title('5-Channel Decomposition')

        # Panel 5: IOB coefficient distribution
        ax = axes[1, 1]
        iob_coefs = [patient_results[p]['coefs_5ch']['pre_iob'] for p in pids]
        ax.hist(iob_coefs, bins=15, color='orange', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(iob_coefs), color='red', linewidth=2,
                   label=f'Median={np.median(iob_coefs):.1f}')
        ax.set_xlabel('Pre-IOB Coefficient (mg/dL per U)')
        ax.set_ylabel('Count')
        ax.set_title('IOB Effect Size')
        ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2768: Bilateral Decomposition

Hypotheses: {n_pass}/5 PASS

5-CHANNEL MODEL:
  BG regression:     {np.median(bg_fracs)*100:.0f}%  (supply)
  Controller auto:   {np.median(ctrl_fracs)*100:.0f}%  (demand)
  User bolus:        {np.median(bol_fracs)*100:.0f}%   (demand)
  Pre-existing IOB:  {med_iob_frac*100:.0f}%  (demand)
  Carbs:             {med_carb_frac*100:.0f}%   (supply-opposing)
  Residual:          {np.median(int_fracs)*100:.0f}%  (hepatic?)

Residual intercept: {med_int5:.1f} mg/dL

R² (3ch→5ch): {np.median(r2_3):.3f} → {np.median(r2_5):.3f}
Intercept: {med_int3:.1f} → {med_int5:.1f} mg/dL

Pre-IOB coef: {np.median(iob_coefs):.1f} mg/dL/U"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/intercept-iob', exist_ok=True)
        plt.savefig('tools/visualizations/intercept-iob/exp-2768-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/intercept-iob/exp-2768-dashboard.png")
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

    with open('externals/experiments/exp-2768_intercept_iob.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2768_intercept_iob.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
