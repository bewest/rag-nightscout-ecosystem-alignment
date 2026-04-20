#!/usr/bin/env python3
"""
EXP-2764: Intercept Decomposition and Pipeline Integration

EXP-2763 found actual_drop = 73 + 3.4 × excess_insulin (median).
The 73 mg/dL intercept is the dose-independent "baseline drop".

This experiment:
  1) Decomposes the intercept into controller action vs regression-to-mean
  2) Tests if the intercept varies with starting BG (regression-to-mean component)
  3) Integrates the LR model into the full pipeline with temporal cross-validation
  4) Compares: Median CF pipeline vs LR pipeline vs LR+BG pipeline

Hypotheses:
  H1: Intercept correlates with starting BG (r ≥ 0.3) → regression-to-mean component
  H2: LR pipeline (b0 + b1*excess_insulin) beats median CF in temporal cross-val
  H3: BG-adjusted LR (b0 + b1*excess + b2*bg) beats plain LR
  H4: Controller action explains ≥30% of intercept (basal suspension measurable)
  H5: LR pipeline stability ≥ 0.90 on temporal split
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
        # Controller action: how much basal was suspended
        basal_diff = net_basal[i:i+horizon] - sched_basal[i:i+horizon]
        excess_basal = np.nansum(basal_diff * 5.0/60.0)
        basal_suspended = np.nansum(np.minimum(basal_diff, 0) * 5.0/60.0)  # negative = suspended
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue

        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
        expected = excess_insulin * profile_isf_val

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'excess_insulin': excess_insulin,
            'expected': expected,
            'profile_isf': profile_isf_val,
            'basal_suspended': basal_suspended,
            'total_smb': total_smb,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {'experiment': 'EXP-2764', 'title': 'Intercept Decomposition'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    patient_results = {}
    all_bg_intercept_corr = []

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

        # ===== Model A: Median CF =====
        cf = (train_eps['actual_drop'] / train_eps['expected']).median()

        # ===== Model B: LR (b0 + b1*excess) =====
        slope_b, intercept_b, _, _, _ = stats.linregress(
            train_eps['excess_insulin'], train_eps['actual_drop'])

        # ===== Model C: LR + BG (b0 + b1*excess + b2*bg) =====
        from sklearn.linear_model import LinearRegression
        X_train_c = train_eps[['excess_insulin', 'bg']].values
        y_train = train_eps['actual_drop'].values
        lr_c = LinearRegression().fit(X_train_c, y_train)

        # Decompose intercept: residual analysis
        # At zero excess insulin, how much does BG predict the drop?
        # Use episodes with minimal bolus
        low_insulin = train_eps[train_eps['excess_insulin'] < train_eps['excess_insulin'].quantile(0.25)]
        if len(low_insulin) >= 5:
            # Residual of drop not explained by insulin
            residual_drop = low_insulin['actual_drop'] - slope_b * low_insulin['excess_insulin']
            bg_resid_corr, bg_resid_p = stats.pearsonr(low_insulin['bg'], residual_drop)
        else:
            bg_resid_corr, bg_resid_p = np.nan, np.nan
        all_bg_intercept_corr.append(bg_resid_corr)

        # Controller action: how much of drop is from basal suspension
        if 'basal_suspended' in train_eps.columns:
            med_basal_susp = train_eps['basal_suspended'].median()
            basal_susp_effect = med_basal_susp * (train_eps['profile_isf'].median())
            ctrl_fraction = abs(basal_susp_effect) / abs(intercept_b) if intercept_b != 0 else 0
        else:
            ctrl_fraction = np.nan

        # ===== Evaluate all 3 on test =====
        y_test = test_eps['actual_drop'].values

        pred_a = test_eps['expected'].values * cf
        pred_b = intercept_b + slope_b * test_eps['excess_insulin'].values
        X_test_c = test_eps[['excess_insulin', 'bg']].values
        pred_c = lr_c.predict(X_test_c)

        mae_a = float(np.median(np.abs(y_test - pred_a)))
        mae_b = float(np.median(np.abs(y_test - pred_b)))
        mae_c = float(np.median(np.abs(y_test - pred_c)))

        b_vs_a = (mae_a - mae_b) / mae_a * 100 if mae_a > 0 else 0
        c_vs_b = (mae_b - mae_c) / mae_b * 100 if mae_b > 0 else 0
        c_vs_a = (mae_a - mae_c) / mae_a * 100 if mae_a > 0 else 0

        # Stability: train MAE vs test MAE ratio
        train_pred_b = intercept_b + slope_b * train_eps['excess_insulin'].values
        train_mae_b = float(np.median(np.abs(y_train - train_pred_b)))
        stability = 1 - abs(mae_b - train_mae_b) / train_mae_b if train_mae_b > 0 else 0

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'n_train': len(train_eps),
            'n_test': len(test_eps),
            'median_cf': float(cf),
            'intercept': float(intercept_b),
            'slope': float(slope_b),
            'bg_coef': float(lr_c.coef_[1]),
            'bg_resid_corr': float(bg_resid_corr) if np.isfinite(bg_resid_corr) else None,
            'ctrl_fraction': float(ctrl_fraction) if np.isfinite(ctrl_fraction) else None,
            'mae_median_cf': mae_a,
            'mae_lr': mae_b,
            'mae_lr_bg': mae_c,
            'lr_vs_cf': float(b_vs_a),
            'lrbg_vs_lr': float(c_vs_b),
            'lrbg_vs_cf': float(c_vs_a),
            'stability': float(stability),
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    print(f"\n  {'Patient':<18} {'b0':>7} {'b1':>6} {'b2(bg)':>7} {'LR%':>6} {'BG%':>6} {'ctrl%':>6}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        ctrl_str = f"{pr['ctrl_fraction']*100:.0f}" if pr['ctrl_fraction'] is not None else '?'
        print(f"  {pid:<18} {pr['intercept']:>7.1f} {pr['slope']:>6.1f} "
              f"{pr['bg_coef']:>7.3f} {pr['lr_vs_cf']:>5.1f}% "
              f"{pr['lrbg_vs_lr']:>5.1f}% {ctrl_str:>5}%")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    valid_corrs = [x for x in all_bg_intercept_corr if np.isfinite(x)]
    med_bg_corr = np.median(valid_corrs) if valid_corrs else 0
    h1_pass = med_bg_corr >= 0.3
    print(f"  {'✓' if h1_pass else '✗'} H1: BG-intercept corr ≥0.3: median r = {med_bg_corr:.3f}")

    lr_wins = [patient_results[p]['lr_vs_cf'] for p in patient_results]
    n_lr_better = sum(1 for x in lr_wins if x > 0)
    h2_pass = n_lr_better / len(lr_wins) >= 0.6 and np.median(lr_wins) > 0
    print(f"  {'✓' if h2_pass else '✗'} H2: LR beats CF: {n_lr_better}/{len(lr_wins)} "
          f"(median {np.median(lr_wins):.1f}%)")

    bg_wins = [patient_results[p]['lrbg_vs_lr'] for p in patient_results]
    n_bg_better = sum(1 for x in bg_wins if x > 0)
    h3_pass = n_bg_better / len(bg_wins) >= 0.6 and np.median(bg_wins) > 0
    print(f"  {'✓' if h3_pass else '✗'} H3: LR+BG beats LR: {n_bg_better}/{len(bg_wins)} "
          f"(median {np.median(bg_wins):.1f}%)")

    ctrl_fracs = [patient_results[p]['ctrl_fraction'] for p in patient_results
                  if patient_results[p]['ctrl_fraction'] is not None]
    med_ctrl = np.median(ctrl_fracs) if ctrl_fracs else 0
    h4_pass = med_ctrl >= 0.3
    print(f"  {'✓' if h4_pass else '✗'} H4: Controller ≥30% of intercept: {med_ctrl*100:.1f}%")

    stabilities = [patient_results[p]['stability'] for p in patient_results]
    med_stab = np.median(stabilities)
    h5_pass = med_stab >= 0.90
    print(f"  {'✓' if h5_pass else '✗'} H5: Stability ≥0.90: {med_stab:.3f}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Intercept decomposition summary
    intercepts = [patient_results[p]['intercept'] for p in patient_results]
    bg_coefs = [patient_results[p]['bg_coef'] for p in patient_results]
    print(f"\n  Intercept decomposition:")
    print(f"    Median intercept: {np.median(intercepts):.1f} mg/dL")
    print(f"    Median BG coefficient: {np.median(bg_coefs):.3f} mg/dL per mg/dL starting BG")
    print(f"    → At BG=250: BG contribution = {np.median(bg_coefs)*250:.1f} mg/dL")
    print(f"    Median controller fraction: {med_ctrl*100:.1f}%")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'median_r': float(med_bg_corr)},
        'H2': {'pass': bool(h2_pass)},
        'H3': {'pass': bool(h3_pass)},
        'H4': {'pass': bool(h4_pass), 'median_fraction': float(med_ctrl)},
        'H5': {'pass': bool(h5_pass), 'median_stability': float(med_stab)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'median_intercept': float(np.median(intercepts)),
        'median_bg_coef': float(np.median(bg_coefs)),
        'median_ctrl_fraction': float(med_ctrl),
        'median_lr_improve': float(np.median(lr_wins)),
        'median_stability': float(med_stab),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2764: Intercept Decomposition & Pipeline Integration',
                     fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: Intercept components
        ax = axes[0, 0]
        ctrl_parts = [abs(patient_results[p]['ctrl_fraction'] * patient_results[p]['intercept'])
                      if patient_results[p]['ctrl_fraction'] is not None else 0 for p in pids]
        remaining = [abs(patient_results[p]['intercept']) - c for p, c in zip(pids, ctrl_parts)]
        x = np.arange(len(pids))
        ax.bar(x, ctrl_parts, color='steelblue', alpha=0.7, label='Controller')
        ax.bar(x, remaining, bottom=ctrl_parts, color='coral', alpha=0.7, label='Regression/Other')
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Intercept (mg/dL)')
        ax.set_title('Intercept Decomposition')
        ax.legend()

        # Panel 2: 3-way MAE comparison
        ax = axes[0, 1]
        m_cf = [patient_results[p]['mae_median_cf'] for p in pids]
        m_lr = [patient_results[p]['mae_lr'] for p in pids]
        m_bg = [patient_results[p]['mae_lr_bg'] for p in pids]
        ax.bar(x - 0.25, m_cf, 0.25, label='Median CF', color='coral', alpha=0.7)
        ax.bar(x, m_lr, 0.25, label='LR', color='steelblue', alpha=0.7)
        ax.bar(x + 0.25, m_bg, 0.25, label='LR+BG', color='green', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Test MAE (mg/dL)')
        ax.set_title('3-Way Model Comparison')
        ax.legend(fontsize=8)

        # Panel 3: BG coefficient
        ax = axes[0, 2]
        ax.hist(bg_coefs, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(bg_coefs), color='red', linewidth=2,
                   label=f'Median={np.median(bg_coefs):.3f}')
        ax.set_xlabel('BG Coefficient')
        ax.set_ylabel('Count')
        ax.set_title('Starting BG Effect on Drop')
        ax.legend()

        # Panel 4: Improvement cascade
        ax = axes[1, 0]
        ax.bar(x - 0.2, lr_wins, 0.4, label='LR vs CF', color='steelblue', alpha=0.7)
        ax.bar(x + 0.2, [patient_results[p]['lrbg_vs_cf'] for p in pids], 0.4,
               label='LR+BG vs CF', color='green', alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Improvement vs CF (%)')
        ax.set_title('Pipeline Improvement')
        ax.legend()

        # Panel 5: Stability
        ax = axes[1, 1]
        ax.hist(stabilities, bins=20, color='coral', alpha=0.7, edgecolor='black')
        ax.axvline(med_stab, color='red', linewidth=2, label=f'Median={med_stab:.3f}')
        ax.axvline(0.9, color='green', linestyle='--', label='Threshold')
        ax.set_xlabel('Stability (1 - |test-train|/train)')
        ax.set_ylabel('Count')
        ax.set_title('LR Temporal Stability')
        ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2764 Summary

Hypotheses: {n_pass}/5 PASS

Intercept: {np.median(intercepts):.1f} mg/dL
  Controller fraction: {med_ctrl*100:.1f}%
  BG coefficient:      {np.median(bg_coefs):.3f}/mg/dL

Model comparison (test MAE):
  Median CF: {np.median(m_cf):.1f} mg/dL
  LR:        {np.median(m_lr):.1f} mg/dL ({np.median(lr_wins):.1f}% better)
  LR+BG:     {np.median(m_bg):.1f} mg/dL ({np.median([patient_results[p]['lrbg_vs_cf'] for p in pids]):.1f}% better)

Stability: {med_stab:.3f}

The intercept decomposes into:
  ~{med_ctrl*100:.0f}% controller action (basal suspension)
  ~{(1-med_ctrl)*100:.0f}% regression to mean + other"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/intercept-decomposition', exist_ok=True)
        plt.savefig('tools/visualizations/intercept-decomposition/exp-2764-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/intercept-decomposition/exp-2764-dashboard.png")
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

    with open('externals/experiments/exp-2764_intercept_decomposition.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2764_intercept_decomposition.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
