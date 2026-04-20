#!/usr/bin/env python3
"""
EXP-2762: IOB-Aware CF Extraction

Pre-existing IOB at correction time is median 2.9U (from EXP-2756).
If IOB confounds CF measurement, accounting for it could improve precision.

Two approaches:
  A) Include IOB in total excess insulin (additive)
  B) Use IOB as a covariate in regression (multiplicative/adjusted)

Hypotheses:
  H1: Pre-existing IOB correlates with CF (r ≥ 0.2)
  H2: IOB-adjusted CF reduces per-patient CF variance (≥10% IQR reduction)
  H3: IOB-adjusted CF improves test predictions (≥5% MAE improvement)
  H4: IOB effect is consistent across controllers
  H5: Multi-factor model (IOB + excess_insulin) outperforms single-factor
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_episodes(pdf, horizon=24, min_bg=180, min_bolus=0.5):
    """Extract correction episodes with IOB."""
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)
    iob = pdf['iob'].values if 'iob' in pdf.columns else np.full(len(pdf), np.nan)

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
        iob_val = iob[i] if not np.isnan(iob[i]) else np.nan

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'excess_insulin': excess_insulin,
            'expected': expected,
            'cf': cf,
            'profile_isf': profile_isf_val,
            'iob': iob_val,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {'experiment': 'EXP-2762', 'title': 'IOB-Aware CF Extraction', 'hypotheses': {}}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    patient_results = {}
    all_iob_cf_corrs = []

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train = pdf.iloc[:split]
        test = pdf.iloc[split:]

        train_eps = extract_episodes(train)
        test_eps = extract_episodes(test)

        if len(train_eps) < 20:
            continue

        # Check IOB availability
        has_iob = train_eps['iob'].notna().mean()
        if has_iob < 0.5:
            continue

        valid_mask = train_eps['cf'].notna() & train_eps['iob'].notna()
        if valid_mask.sum() < 15:
            continue

        train_valid = train_eps[valid_mask]

        # IOB-CF correlation
        r_iob_cf, p_iob_cf = stats.pearsonr(train_valid['iob'], train_valid['cf'])
        all_iob_cf_corrs.append(r_iob_cf)

        # Approach A: Simple CF (baseline)
        simple_cf = train_valid['cf'].median()
        simple_iqr = float(train_valid['cf'].quantile(0.75) - train_valid['cf'].quantile(0.25))

        # Approach B: Multi-factor regression: actual_drop = b0 + b1*excess_insulin + b2*iob
        from sklearn.linear_model import LinearRegression
        X_train = train_valid[['excess_insulin', 'iob']].values
        y_train = train_valid['actual_drop'].values
        X_single = train_valid[['excess_insulin']].values

        lr_multi = LinearRegression().fit(X_train, y_train)
        lr_single = LinearRegression().fit(X_single, y_train)

        train_pred_multi = lr_multi.predict(X_train)
        train_pred_single = lr_single.predict(X_single)

        # Residual-based CF IQR
        residuals_simple = train_valid['actual_drop'] - train_valid['expected'] * simple_cf
        residuals_multi = y_train - train_pred_multi
        iqr_simple_resid = float(np.percentile(residuals_simple, 75) - np.percentile(residuals_simple, 25))
        iqr_multi_resid = float(np.percentile(residuals_multi, 75) - np.percentile(residuals_multi, 25))
        iqr_reduction = (iqr_simple_resid - iqr_multi_resid) / iqr_simple_resid * 100 if iqr_simple_resid > 0 else 0

        # Test set evaluation
        test_valid = test_eps[test_eps['cf'].notna() & test_eps['iob'].notna()]
        if len(test_valid) < 5:
            continue

        X_test = test_valid[['excess_insulin', 'iob']].values
        X_test_single = test_valid[['excess_insulin']].values
        y_test = test_valid['actual_drop'].values

        # Simple CF prediction
        pred_simple = test_valid['expected'].values * simple_cf
        mae_simple = np.median(np.abs(y_test - pred_simple))

        # Multi-factor prediction
        pred_multi = lr_multi.predict(X_test)
        mae_multi = np.median(np.abs(y_test - pred_multi))

        # Single linear prediction
        pred_single = lr_single.predict(X_test_single)
        mae_single_lr = np.median(np.abs(y_test - pred_single))

        multi_improve = (mae_simple - mae_multi) / mae_simple * 100 if mae_simple > 0 else 0
        single_lr_improve = (mae_simple - mae_single_lr) / mae_simple * 100 if mae_simple > 0 else 0

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'n_episodes': len(train_valid),
            'iob_available': float(has_iob),
            'r_iob_cf': float(r_iob_cf),
            'p_iob_cf': float(p_iob_cf),
            'simple_cf': float(simple_cf),
            'simple_cf_iqr': float(simple_iqr),
            'iqr_reduction': float(iqr_reduction),
            'multi_coefs': {
                'intercept': float(lr_multi.intercept_),
                'excess_insulin': float(lr_multi.coef_[0]),
                'iob': float(lr_multi.coef_[1]),
            },
            'r2_multi_train': float(lr_multi.score(X_train, y_train)),
            'r2_single_train': float(lr_single.score(X_single, y_train)),
            'mae_simple': float(mae_simple),
            'mae_multi': float(mae_multi),
            'mae_single_lr': float(mae_single_lr),
            'multi_improve': float(multi_improve),
            'single_lr_improve': float(single_lr_improve),
        }

    print(f"\nPatients with IOB data: {len(patient_results)}")

    # ============================================================
    # RESULTS
    # ============================================================
    print(f"\n  {'Patient':<18} {'Ctrl':<5} {'r(IOB)':>7} {'IQR↓%':>6} {'Multi%':>7} {'IOB coef':>9}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['controller']:<5} {pr['r_iob_cf']:>7.3f} "
              f"{pr['iqr_reduction']:>5.1f}% {pr['multi_improve']:>6.1f}% "
              f"{pr['multi_coefs']['iob']:>9.2f}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    median_r = np.median(all_iob_cf_corrs)
    h1_pass = abs(median_r) >= 0.2
    print(f"  {'✓' if h1_pass else '✗'} H1: IOB-CF correlation ≥0.2: median r = {median_r:.3f}")

    iqr_reds = [patient_results[p]['iqr_reduction'] for p in patient_results]
    med_iqr_red = np.median(iqr_reds)
    h2_pass = med_iqr_red >= 10
    print(f"  {'✓' if h2_pass else '✗'} H2: ≥10% IQR reduction: median {med_iqr_red:.1f}%")

    multi_imps = [patient_results[p]['multi_improve'] for p in patient_results]
    med_multi_imp = np.median(multi_imps)
    h3_pass = med_multi_imp >= 5
    n_better = sum(1 for x in multi_imps if x > 0)
    print(f"  {'✓' if h3_pass else '✗'} H3: ≥5% MAE improvement: median {med_multi_imp:.1f}%, "
          f"{n_better}/{len(multi_imps)} improve")

    # H4: Consistent across controllers
    loop_rs = [patient_results[p]['r_iob_cf'] for p in patient_results
               if patient_results[p]['controller'] == 'Loop']
    trio_rs = [patient_results[p]['r_iob_cf'] for p in patient_results
               if patient_results[p]['controller'] == 'Trio']
    if loop_rs and trio_rs:
        h4_pass = abs(np.median(loop_rs) - np.median(trio_rs)) < 0.2
        print(f"  {'✓' if h4_pass else '✗'} H4: Consistent: Loop r={np.median(loop_rs):.3f}, "
              f"Trio r={np.median(trio_rs):.3f}")
    else:
        h4_pass = False
        print(f"  ✗ H4: Not enough controllers")

    # H5: Multi outperforms single-factor LR
    multi_vs_single = []
    for p in patient_results:
        pr = patient_results[p]
        delta = pr['multi_improve'] - pr['single_lr_improve']
        multi_vs_single.append(delta)
    med_delta = np.median(multi_vs_single)
    h5_pass = med_delta > 0 and sum(1 for x in multi_vs_single if x > 0) > len(multi_vs_single) / 2
    print(f"  {'✓' if h5_pass else '✗'} H5: Multi > single LR: median delta {med_delta:.1f}%, "
          f"{sum(1 for x in multi_vs_single if x > 0)}/{len(multi_vs_single)} better")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # IOB coefficient analysis
    iob_coefs = [patient_results[p]['multi_coefs']['iob'] for p in patient_results]
    print(f"\n  IOB coefficient: median {np.median(iob_coefs):.2f}, "
          f"mean {np.mean(iob_coefs):.2f}")
    print(f"  (Positive = more IOB → more drop, Negative = more IOB → less drop)")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'median_r': float(median_r)},
        'H2': {'pass': bool(h2_pass), 'median_iqr_reduction': float(med_iqr_red)},
        'H3': {'pass': bool(h3_pass), 'median_improve': float(med_multi_imp)},
        'H4': {'pass': bool(h4_pass)},
        'H5': {'pass': bool(h5_pass), 'median_delta': float(med_delta)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'n_patients': len(patient_results),
        'median_iob_cf_corr': float(median_r),
        'median_iqr_reduction': float(med_iqr_red),
        'median_multi_improve': float(med_multi_imp),
        'median_iob_coef': float(np.median(iob_coefs)),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2762: IOB-Aware CF Extraction', fontsize=16, fontweight='bold')

        ax = axes[0, 0]
        ax.hist(all_iob_cf_corrs, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(median_r, color='red', linewidth=2, label=f'Median={median_r:.3f}')
        ax.axvline(0, color='gray', linestyle='--')
        ax.set_xlabel('IOB-CF Correlation (r)')
        ax.set_ylabel('Count')
        ax.set_title('IOB vs CF Correlation')
        ax.legend()

        ax = axes[0, 1]
        ax.hist(iob_coefs, bins=20, color='coral', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(iob_coefs), color='red', linewidth=2)
        ax.axvline(0, color='gray', linestyle='--')
        ax.set_xlabel('IOB Regression Coefficient')
        ax.set_ylabel('Count')
        ax.set_title('IOB Effect on BG Drop')

        ax = axes[0, 2]
        ax.hist(iqr_reds, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(0, color='gray', linestyle='--')
        ax.set_xlabel('IQR Reduction (%)')
        ax.set_ylabel('Count')
        ax.set_title('CF Variance Reduction from IOB')

        ax = axes[1, 0]
        x = np.arange(len(patient_results))
        pids = sorted(patient_results.keys())
        mi = [patient_results[p]['multi_improve'] for p in pids]
        ax.bar(x, mi, color=['steelblue' if v > 0 else 'coral' for v in mi], alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Multi-factor improvement (%)')
        ax.set_title('IOB-Aware vs Simple CF')

        ax = axes[1, 1]
        r2_m = [patient_results[p]['r2_multi_train'] for p in pids]
        r2_s = [patient_results[p]['r2_single_train'] for p in pids]
        ax.scatter(r2_s, r2_m, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(r2_m), max(r2_s)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Single-factor R²')
        ax.set_ylabel('Multi-factor R²')
        ax.set_title('Train R²: Multi vs Single')

        ax = axes[1, 2]
        ax.axis('off')
        summary_text = f"""EXP-2762 Summary

Hypotheses: {n_pass}/5 PASS

IOB-CF Correlation:  {median_r:.3f}
IOB coefficient:     {np.median(iob_coefs):.2f} mg/dL per U IOB
IQR reduction:       {med_iqr_red:.1f}%
Multi-factor improve: {med_multi_imp:.1f}%
Multi > Single LR:   {med_delta:.1f}%

Patients improved: {n_better}/{len(multi_imps)}

IOB is {'a useful covariate' if n_pass >= 3 else 'NOT a useful covariate'}
for CF extraction."""
        ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/iob-aware-cf', exist_ok=True)
        plt.savefig('tools/visualizations/iob-aware-cf/exp-2762-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/iob-aware-cf/exp-2762-dashboard.png")
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

    with open('externals/experiments/exp-2762_iob_aware_cf.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2762_iob_aware_cf.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
