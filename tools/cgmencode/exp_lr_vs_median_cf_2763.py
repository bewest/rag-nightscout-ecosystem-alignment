#!/usr/bin/env python3
"""
EXP-2763: Linear Regression vs Median CF — Formal Comparison

EXP-2762 revealed that using a linear regression (actual_drop = b * excess_insulin)
instead of median-CF (actual_drop = median_CF * expected) improves MAE by ~35%.

This experiment formally compares:
  A) Median CF: CF = median(actual_drop / expected), predict = CF * expected
  B) Per-patient LR: actual_drop = b1 * excess_insulin (intercept-free)
  C) Per-patient LR with intercept: actual_drop = b0 + b1 * excess_insulin

The intercept captures "baseline drop" — the average BG drop during a correction
episode that occurs regardless of dose (controller action, regression to mean).

Hypotheses:
  H1: LR (no intercept) beats median CF in ≥60% of patients on test data
  H2: LR with intercept beats no-intercept in ≥60% of patients
  H3: The intercept (b0) is significantly non-zero (median |b0| > 10 mg/dL)
  H4: LR generalizes (train/test R² ratio ≥ 0.7)
  H5: LR improvement is ≥10% median MAE reduction vs median-CF
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_episodes(pdf, horizon=24, min_bg=180, min_bolus=0.5):
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
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue

        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
        expected = excess_insulin * profile_isf_val
        cf = actual_drop / expected if expected > 0 else np.nan

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'excess_insulin': excess_insulin,
            'expected': expected,
            'cf': cf,
            'profile_isf': profile_isf_val,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {'experiment': 'EXP-2763', 'title': 'LR vs Median CF'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    patient_results = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train = pdf.iloc[:split]
        test = pdf.iloc[split:]

        train_eps = extract_episodes(train)
        test_eps = extract_episodes(test)

        if len(train_eps) < 20 or len(test_eps) < 5:
            continue

        valid_train = train_eps[train_eps['cf'].notna()]
        valid_test = test_eps[test_eps['cf'].notna()]
        if len(valid_train) < 15 or len(valid_test) < 5:
            continue

        # === METHOD A: Median CF ===
        median_cf = float(valid_train['cf'].median())

        # === METHOD B: LR no intercept (through origin) ===
        X_train = valid_train['excess_insulin'].values.reshape(-1, 1)
        y_train = valid_train['actual_drop'].values

        # actual_drop = b * excess_insulin  → b = observed ISF
        slope_noint = float(np.sum(X_train.ravel() * y_train) / np.sum(X_train.ravel() ** 2))

        # === METHOD C: LR with intercept ===
        slope_int, intercept, r_val, p_val, se = stats.linregress(
            valid_train['excess_insulin'], valid_train['actual_drop'])

        # Train predictions
        train_pred_median = valid_train['expected'].values * median_cf
        train_pred_noint = valid_train['excess_insulin'].values * slope_noint
        train_pred_int = intercept + slope_int * valid_train['excess_insulin'].values

        train_mae_median = float(np.median(np.abs(y_train - train_pred_median)))
        train_mae_noint = float(np.median(np.abs(y_train - train_pred_noint)))
        train_mae_int = float(np.median(np.abs(y_train - train_pred_int)))

        # Test predictions
        X_test = valid_test['excess_insulin'].values
        y_test = valid_test['actual_drop'].values

        test_pred_median = valid_test['expected'].values * median_cf
        test_pred_noint = X_test * slope_noint
        test_pred_int = intercept + slope_int * X_test

        test_mae_median = float(np.median(np.abs(y_test - test_pred_median)))
        test_mae_noint = float(np.median(np.abs(y_test - test_pred_noint)))
        test_mae_int = float(np.median(np.abs(y_test - test_pred_int)))

        # R² on test
        ss_tot = np.sum((y_test - np.mean(y_test))**2)
        r2_noint = 1 - np.sum((y_test - test_pred_noint)**2) / ss_tot if ss_tot > 0 else 0
        r2_int = 1 - np.sum((y_test - test_pred_int)**2) / ss_tot if ss_tot > 0 else 0
        r2_median = 1 - np.sum((y_test - test_pred_median)**2) / ss_tot if ss_tot > 0 else 0

        # Train R² for stability check
        ss_tot_train = np.sum((y_train - np.mean(y_train))**2)
        r2_int_train = 1 - np.sum((y_train - train_pred_int)**2) / ss_tot_train if ss_tot_train > 0 else 0

        noint_vs_median = (test_mae_median - test_mae_noint) / test_mae_median * 100 if test_mae_median > 0 else 0
        int_vs_noint = (test_mae_noint - test_mae_int) / test_mae_noint * 100 if test_mae_noint > 0 else 0
        int_vs_median = (test_mae_median - test_mae_int) / test_mae_median * 100 if test_mae_median > 0 else 0

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'n_train': len(valid_train),
            'n_test': len(valid_test),
            'median_cf': median_cf,
            'slope_noint': slope_noint,
            'slope_int': float(slope_int),
            'intercept': float(intercept),
            'train_mae_median': train_mae_median,
            'train_mae_noint': train_mae_noint,
            'train_mae_int': train_mae_int,
            'test_mae_median': test_mae_median,
            'test_mae_noint': test_mae_noint,
            'test_mae_int': test_mae_int,
            'noint_vs_median': noint_vs_median,
            'int_vs_noint': int_vs_noint,
            'int_vs_median': int_vs_median,
            'r2_test_noint': float(r2_noint),
            'r2_test_int': float(r2_int),
            'r2_test_median': float(r2_median),
            'r2_train_int': float(r2_int_train),
            'stability': float(r2_int / r2_int_train) if r2_int_train > 0 else 0,
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    print(f"\n  {'Patient':<18} {'CF':>6} {'slope':>6} {'b0':>7} "
          f"{'noint%':>7} {'int%':>7} {'R²test':>7}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['median_cf']:>6.3f} {pr['slope_noint']:>6.1f} "
              f"{pr['intercept']:>7.1f} {pr['noint_vs_median']:>6.1f}% "
              f"{pr['int_vs_median']:>6.1f}% {pr['r2_test_int']:>7.3f}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    n_noint_better = sum(1 for p in patient_results
                         if patient_results[p]['noint_vs_median'] > 0)
    h1_pass = n_noint_better / len(patient_results) >= 0.6
    print(f"  {'✓' if h1_pass else '✗'} H1: LR beats median CF ≥60%: "
          f"{n_noint_better}/{len(patient_results)} ({n_noint_better/len(patient_results)*100:.0f}%)")

    n_int_better = sum(1 for p in patient_results
                       if patient_results[p]['int_vs_noint'] > 0)
    h2_pass = n_int_better / len(patient_results) >= 0.6
    print(f"  {'✓' if h2_pass else '✗'} H2: LR+intercept beats LR ≥60%: "
          f"{n_int_better}/{len(patient_results)} ({n_int_better/len(patient_results)*100:.0f}%)")

    intercepts = [patient_results[p]['intercept'] for p in patient_results]
    med_intercept = np.median(np.abs(intercepts))
    h3_pass = med_intercept > 10
    print(f"  {'✓' if h3_pass else '✗'} H3: |intercept| > 10: median |b0| = {med_intercept:.1f} mg/dL")

    stabilities = [patient_results[p]['stability'] for p in patient_results
                   if patient_results[p]['r2_train_int'] > 0.01]
    med_stab = np.median(stabilities) if stabilities else 0
    h4_pass = med_stab >= 0.7
    print(f"  {'✓' if h4_pass else '✗'} H4: LR generalizes (stability ≥0.7): {med_stab:.3f}")

    int_vs_medians = [patient_results[p]['int_vs_median'] for p in patient_results]
    med_imp = np.median(int_vs_medians)
    h5_pass = med_imp >= 10
    print(f"  {'✓' if h5_pass else '✗'} H5: ≥10% improvement: median {med_imp:.1f}%")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Intercept analysis
    print(f"\n  Intercept (b0) analysis:")
    print(f"    Median: {np.median(intercepts):.1f} mg/dL")
    print(f"    Mean: {np.mean(intercepts):.1f} mg/dL")
    print(f"    IQR: {np.percentile(intercepts, 25):.1f} to {np.percentile(intercepts, 75):.1f}")
    print(f"    Positive b0 means: BG drops even with zero excess insulin (controller/regression)")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'n_better': n_noint_better},
        'H2': {'pass': bool(h2_pass), 'n_better': n_int_better},
        'H3': {'pass': bool(h3_pass), 'median_abs_intercept': float(med_intercept)},
        'H4': {'pass': bool(h4_pass), 'median_stability': float(med_stab)},
        'H5': {'pass': bool(h5_pass), 'median_improve': float(med_imp)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'n_patients': len(patient_results),
        'median_intercept': float(np.median(intercepts)),
        'median_improvement': float(med_imp),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2763: LR vs Median CF', fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: MAE comparison
        ax = axes[0, 0]
        x = np.arange(len(pids))
        m1 = [patient_results[p]['test_mae_median'] for p in pids]
        m2 = [patient_results[p]['test_mae_noint'] for p in pids]
        m3 = [patient_results[p]['test_mae_int'] for p in pids]
        ax.bar(x - 0.25, m1, 0.25, label='Median CF', color='coral', alpha=0.7)
        ax.bar(x, m2, 0.25, label='LR (no int)', color='steelblue', alpha=0.7)
        ax.bar(x + 0.25, m3, 0.25, label='LR (+ int)', color='green', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Test MAE (mg/dL)')
        ax.set_title('Test MAE by Method')
        ax.legend(fontsize=8)

        # Panel 2: Intercept distribution
        ax = axes[0, 1]
        ax.hist(intercepts, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(intercepts), color='red', linewidth=2,
                   label=f'Median={np.median(intercepts):.1f}')
        ax.axvline(0, color='gray', linestyle='--')
        ax.set_xlabel('Intercept b0 (mg/dL)')
        ax.set_ylabel('Count')
        ax.set_title('Intercept = "Baseline BG Drop"')
        ax.legend()

        # Panel 3: Improvement
        ax = axes[0, 2]
        imp_vals = [patient_results[p]['int_vs_median'] for p in pids]
        colors = ['steelblue' if v > 0 else 'coral' for v in imp_vals]
        ax.bar(x, imp_vals, color=colors, alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.axhline(np.median(imp_vals), color='red', linestyle='--',
                   label=f'Median={np.median(imp_vals):.1f}%')
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Improvement vs Median CF (%)')
        ax.set_title('LR+Intercept vs Median CF')
        ax.legend()

        # Panel 4: Slope (observed ISF) vs CF*profileISF
        ax = axes[1, 0]
        slopes = [patient_results[p]['slope_noint'] for p in pids]
        cf_isf = [patient_results[p]['median_cf'] * 50 for p in pids]  # approximate
        ax.scatter(cf_isf, slopes, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        ax.set_xlabel('CF × Profile ISF (approx)')
        ax.set_ylabel('LR Slope (observed ISF)')
        ax.set_title('Two ISF Estimates')

        # Panel 5: R² comparison
        ax = axes[1, 1]
        r2m = [patient_results[p]['r2_test_median'] for p in pids]
        r2i = [patient_results[p]['r2_test_int'] for p in pids]
        ax.scatter(r2m, r2i, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim_lo = min(min(r2m), min(r2i)) - 0.05
        lim_hi = max(max(r2m), max(r2i)) + 0.05
        ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], 'k--', alpha=0.3)
        ax.set_xlabel('R² Median CF')
        ax.set_ylabel('R² LR + Intercept')
        ax.set_title('Predictive Power')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2763 Summary

Hypotheses: {n_pass}/5 PASS

Median CF test MAE:  {np.median(m1):.1f} mg/dL
LR test MAE:         {np.median(m3):.1f} mg/dL
Improvement:         {med_imp:.1f}%

Intercept (b0):      {np.median(intercepts):.1f} mg/dL
  → Baseline drop unrelated to dose
  → Controller action + regression to mean

LR slope (observed ISF): {np.median(slopes):.1f} mg/dL/U
  → Per-unit insulin effect in closed-loop

LR beats CF: {n_noint_better}/{len(patient_results)}
Intercept helps: {n_int_better}/{len(patient_results)}"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/lr-vs-median-cf', exist_ok=True)
        plt.savefig('tools/visualizations/lr-vs-median-cf/exp-2763-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/lr-vs-median-cf/exp-2763-dashboard.png")
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

    with open('externals/experiments/exp-2763_lr_vs_median_cf.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2763_lr_vs_median_cf.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
