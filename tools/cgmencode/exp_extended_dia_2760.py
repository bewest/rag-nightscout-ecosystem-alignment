#!/usr/bin/env python3
"""
EXP-2760: Extended DIA Pipeline Comparison

EXP-2759 showed optimal DIA ~240min and CF stability r=0.881.
This experiment tests whether using 4h (48-step) window instead of 2h (24-step)
improves the full settings pipeline.

Uses temporal cross-validation (train/test split) from EXP-2753 approach.

Hypotheses:
  H1: 4h ISF correction improves more patients than 2h ISF correction
  H2: 4h CF has lower IQR (more precise per patient)
  H3: 4h temporal stability ≥ 2h (test/train ratio ≥ 0.95)
  H4: Combined (4h ISF + bilateral CR) outperforms 2h pipeline
  H5: Median MAE improvement is ≥5% better with 4h vs 2h
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_isf_cf(pdf, horizon=24, min_bg=180, min_bolus=0.5):
    """Extract ISF correction factor for a given horizon."""
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

    cfs = []
    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue
        if np.isnan(bolus[i]) or bolus[i] < min_bolus:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < max(3, horizon//4):
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
        if expected > 0:
            cfs.append(actual_drop / expected)

    return cfs

def evaluate_prediction(pdf, cf, horizon=24, min_bg=180, min_bolus=0.5):
    """Evaluate prediction quality with given CF and horizon."""
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

    errors_cf = []
    errors_profile = []

    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue
        if np.isnan(bolus[i]) or bolus[i] < min_bolus:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < max(3, horizon//4):
            continue

        actual_drop = glucose[i] - valid_f[-1]
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue

        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0

        pred_profile = excess_insulin * profile_isf_val
        pred_cf = excess_insulin * profile_isf_val * cf

        errors_profile.append(abs(actual_drop - pred_profile))
        errors_cf.append(abs(actual_drop - pred_cf))

    return errors_profile, errors_cf

def run_experiment():
    results = {
        'experiment': 'EXP-2760',
        'title': 'Extended DIA Pipeline Comparison',
        'hypotheses': {}
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    comparison = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train = pdf.iloc[:split]
        test = pdf.iloc[split:]

        results_pid = {}

        for horizon, label in [(24, '2h'), (48, '4h')]:
            # Extract CF on train
            cfs = extract_isf_cf(train, horizon=horizon)
            if len(cfs) < 10:
                continue

            cf = float(np.median(cfs))
            cf_iqr = float(np.percentile(cfs, 75) - np.percentile(cfs, 25))

            # Evaluate on train
            train_profile_err, train_cf_err = evaluate_prediction(train, cf, horizon=horizon)
            # Evaluate on test
            test_profile_err, test_cf_err = evaluate_prediction(test, cf, horizon=horizon)

            if train_cf_err and test_cf_err:
                train_mae_profile = np.median(train_profile_err)
                train_mae_cf = np.median(train_cf_err)
                test_mae_profile = np.median(test_profile_err)
                test_mae_cf = np.median(test_cf_err)

                train_improve = (train_mae_profile - train_mae_cf) / train_mae_profile * 100
                test_improve = (test_mae_profile - test_mae_cf) / test_mae_profile * 100

                results_pid[label] = {
                    'cf': cf,
                    'cf_iqr': cf_iqr,
                    'n_episodes_train': len(cfs),
                    'train_mae_profile': float(train_mae_profile),
                    'train_mae_cf': float(train_mae_cf),
                    'test_mae_profile': float(test_mae_profile),
                    'test_mae_cf': float(test_mae_cf),
                    'train_improve': float(train_improve),
                    'test_improve': float(test_improve),
                    'stability': float(test_improve / train_improve) if train_improve > 0 else 0,
                }

        if '2h' in results_pid and '4h' in results_pid:
            comparison[pid] = results_pid

    print(f"\nPatients with both 2h and 4h: {len(comparison)}")

    # ============================================================
    # COMPARISON
    # ============================================================
    print("\n" + "=" * 70)
    print("Comparison: 2h vs 4h Pipeline")
    print("=" * 70)

    print(f"\n  {'Patient':<18} {'2h CF':>6} {'4h CF':>6} {'2h test%':>8} {'4h test%':>8} {'Winner':>8}")
    h1_4h_better = 0
    h1_total = 0
    for pid in sorted(comparison.keys()):
        r2 = comparison[pid]['2h']
        r4 = comparison[pid]['4h']
        winner = '4h' if r4['test_improve'] > r2['test_improve'] else '2h'
        if r4['test_improve'] > r2['test_improve']:
            h1_4h_better += 1
        h1_total += 1
        print(f"  {pid:<18} {r2['cf']:>6.3f} {r4['cf']:>6.3f} "
              f"{r2['test_improve']:>7.1f}% {r4['test_improve']:>7.1f}% {winner:>8}")

    # Aggregate
    improve_2h = [comparison[p]['2h']['test_improve'] for p in comparison]
    improve_4h = [comparison[p]['4h']['test_improve'] for p in comparison]
    cf_iqr_2h = [comparison[p]['2h']['cf_iqr'] for p in comparison]
    cf_iqr_4h = [comparison[p]['4h']['cf_iqr'] for p in comparison]
    stab_2h = [comparison[p]['2h']['stability'] for p in comparison]
    stab_4h = [comparison[p]['4h']['stability'] for p in comparison]

    print(f"\n  2h median test improvement: {np.median(improve_2h):.1f}%")
    print(f"  4h median test improvement: {np.median(improve_4h):.1f}%")
    print(f"  2h median CF IQR: {np.median(cf_iqr_2h):.3f}")
    print(f"  4h median CF IQR: {np.median(cf_iqr_4h):.3f}")
    print(f"  2h median stability: {np.median(stab_2h):.3f}")
    print(f"  4h median stability: {np.median(stab_4h):.3f}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    h1_pass = h1_4h_better / h1_total >= 0.5 if h1_total > 0 else False
    print(f"  {'✓' if h1_pass else '✗'} H1: 4h improves more patients: {h1_4h_better}/{h1_total}")

    h2_iqr_better = sum(1 for p in comparison if comparison[p]['4h']['cf_iqr'] < comparison[p]['2h']['cf_iqr'])
    h2_pass = np.median(cf_iqr_4h) < np.median(cf_iqr_2h)
    print(f"  {'✓' if h2_pass else '✗'} H2: 4h lower IQR: {h2_iqr_better}/{len(comparison)}, "
          f"median {np.median(cf_iqr_2h):.3f}→{np.median(cf_iqr_4h):.3f}")

    h3_pass = np.median(stab_4h) >= 0.95
    print(f"  {'✓' if h3_pass else '✗'} H3: 4h stability ≥0.95: {np.median(stab_4h):.3f}")

    h4_pass = np.median(improve_4h) > np.median(improve_2h)
    print(f"  {'✓' if h4_pass else '✗'} H4: 4h outperforms 2h: {np.median(improve_4h):.1f}% vs {np.median(improve_2h):.1f}%")

    delta = np.median(improve_4h) - np.median(improve_2h)
    h5_pass = delta >= 5
    print(f"  {'✓' if h5_pass else '✗'} H5: ≥5% delta: {delta:.1f}%")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1_4h_more_patients': {'pass': bool(h1_pass), 'count': h1_4h_better, 'total': h1_total},
        'H2_lower_iqr': {'pass': bool(h2_pass)},
        'H3_stability': {'pass': bool(h3_pass), 'median_stability': float(np.median(stab_4h))},
        'H4_outperforms': {'pass': bool(h4_pass)},
        'H5_5pct_delta': {'pass': bool(h5_pass), 'delta': float(delta)},
        'total_pass': n_pass
    }
    results['comparison'] = {pid: comparison[pid] for pid in comparison}
    results['summary'] = {
        'median_2h_improve': float(np.median(improve_2h)),
        'median_4h_improve': float(np.median(improve_4h)),
        'median_2h_iqr': float(np.median(cf_iqr_2h)),
        'median_4h_iqr': float(np.median(cf_iqr_4h)),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2760: Extended DIA Pipeline (2h vs 4h)', fontsize=16, fontweight='bold')

        # Panel 1: Test improvement comparison
        ax = axes[0, 0]
        x = np.arange(len(comparison))
        pids = sorted(comparison.keys())
        i2h = [comparison[p]['2h']['test_improve'] for p in pids]
        i4h = [comparison[p]['4h']['test_improve'] for p in pids]
        ax.bar(x - 0.2, i2h, 0.4, label='2h', color='coral', alpha=0.7)
        ax.bar(x + 0.2, i4h, 0.4, label='4h', color='steelblue', alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Test Improvement (%)')
        ax.set_title('2h vs 4h Test Improvement')
        ax.legend()

        # Panel 2: CF scatter
        ax = axes[0, 1]
        cf2 = [comparison[p]['2h']['cf'] for p in pids]
        cf4 = [comparison[p]['4h']['cf'] for p in pids]
        ax.scatter(cf2, cf4, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(cf2), max(cf4)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('CF at 2h')
        ax.set_ylabel('CF at 4h')
        ax.set_title('CF: 2h vs 4h')

        # Panel 3: IQR comparison
        ax = axes[0, 2]
        ax.scatter(cf_iqr_2h, cf_iqr_4h, s=60, alpha=0.7, c='coral', edgecolors='black')
        lim = max(max(cf_iqr_2h), max(cf_iqr_4h)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='Equal')
        ax.set_xlabel('CF IQR at 2h')
        ax.set_ylabel('CF IQR at 4h')
        ax.set_title('CF Precision (lower = better)')
        ax.legend()

        # Panel 4: Improvement distribution
        ax = axes[1, 0]
        ax.hist(improve_2h, bins=20, alpha=0.5, color='coral', label='2h')
        ax.hist(improve_4h, bins=20, alpha=0.5, color='steelblue', label='4h')
        ax.axvline(np.median(improve_2h), color='red', linestyle='-')
        ax.axvline(np.median(improve_4h), color='blue', linestyle='-')
        ax.set_xlabel('Test Improvement (%)')
        ax.set_ylabel('Count')
        ax.set_title('Improvement Distributions')
        ax.legend()

        # Panel 5: Stability scatter
        ax = axes[1, 1]
        ax.scatter(stab_2h, stab_4h, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        ax.axhline(1.0, color='green', linestyle='--', alpha=0.5)
        ax.axvline(1.0, color='green', linestyle='--', alpha=0.5)
        ax.set_xlabel('2h Stability (test/train)')
        ax.set_ylabel('4h Stability (test/train)')
        ax.set_title('Temporal Stability')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2760 Summary

Hypotheses: {n_pass}/5 PASS

2h Pipeline:
  Median improvement: {np.median(improve_2h):.1f}%
  Median CF IQR:      {np.median(cf_iqr_2h):.3f}
  Median stability:   {np.median(stab_2h):.3f}

4h Pipeline:
  Median improvement: {np.median(improve_4h):.1f}%
  Median CF IQR:      {np.median(cf_iqr_4h):.3f}
  Median stability:   {np.median(stab_4h):.3f}

4h better: {h1_4h_better}/{h1_total} patients
Delta:     {delta:+.1f}%"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/extended-dia', exist_ok=True)
        plt.savefig('tools/visualizations/extended-dia/exp-2760-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/extended-dia/exp-2760-dashboard.png")
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

    with open('externals/experiments/exp-2760_extended_dia.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2760_extended_dia.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
