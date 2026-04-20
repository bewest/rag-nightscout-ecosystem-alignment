#!/usr/bin/env python3
"""
EXP-2758: Full ISF Gap Reconciliation with Joint EGP-ISF Estimation

EXP-2756 found: profile predicts 295 mg/dL drop but actual is 46 mg/dL.
EXP-2757 found: EGP accounts for ~80 mg/dL, but used circular ISF assumption.

This experiment:
1. Avoids circularity: estimate EGP from glucose drift ONLY (no ISF assumption)
2. Accounts for ALL insulin (bolus + SMB + net_basal, not just excess)
3. Accounts for pre-existing IOB contributing to the drop
4. Performs full accounting: observed_drop = insulin_effect - EGP + noise

The key insight: during a correction episode, the BG change is:
  ΔBG = -(all_active_insulin × true_ISF) + EGP_2h + noise
  
We can estimate:
  true_ISF = (observed_drop + EGP_2h) / all_active_insulin

Where EGP is measured from pure fasting (no ISF needed).

Hypotheses:
  H1: Fasting glucose drift (ISF-independent EGP measure) is 0-2 mg/dL/5min
  H2: Full accounting (EGP + total insulin) gives ISF within 50% of profile
  H3: Adding IOB to insulin accounting further improves the estimate
  H4: Reconciled ISF is in physiological range (20-100 mg/dL/U)
  H5: Reconciliation closes >80% of the original 6× gap
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {
        'experiment': 'EXP-2758',
        'title': 'Full ISF Gap Reconciliation',
        'hypotheses': {},
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    # ============================================================
    # PHASE 1: ISF-Independent EGP Measurement
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 1: ISF-Independent EGP (Pure Fasting Glucose Drift)")
    print("=" * 70)
    print("  Method: Find windows with no carbs (3h), no bolus (2h), no SMB (1h)")
    print("  EGP = raw glucose drift (we DON'T subtract basal insulin effect)")
    print("  This gives NET EGP = EGP_true - basal_insulin_effect")
    print("  The 'net EGP' is what actually counteracts bolus insulin in corrections")

    net_egp_by_patient = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        carbs = pdf['carbs'].values if 'carbs' in pdf.columns else np.zeros(len(pdf))
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))

        fasting_drifts = []
        window = 12  # 1h
        carb_lookback = 36  # 3h
        bolus_lookback = 24  # 2h

        for i in range(carb_lookback, len(pdf) - window):
            if np.nansum(carbs[i-carb_lookback:i+window]) > 0:
                continue
            if np.nansum(bolus[i-bolus_lookback:i+window]) > 0.1:
                continue
            if np.nansum(bolus_smb[i-12:i+window]) > 0.1:
                continue

            gluc = glucose[i:i+window+1]
            if np.sum(np.isnan(gluc)) > 3:
                continue
            valid = gluc[~np.isnan(gluc)]
            if len(valid) < 6:
                continue

            slope, _, _, _, _ = stats.linregress(np.arange(len(valid)), valid)
            fasting_drifts.append(float(slope))

        if len(fasting_drifts) >= 10:
            net_egp_by_patient[pid] = {
                'drift_per_5min': float(np.median(fasting_drifts)),
                'drift_per_hour': float(np.median(fasting_drifts) * 12),
                'drift_2h': float(np.median(fasting_drifts) * 24),
                'n_windows': len(fasting_drifts),
                'std': float(np.std(fasting_drifts))
            }
            d = np.median(fasting_drifts)
            print(f"  {pid}: net drift={d:.2f} mg/dL/5min ({d*12:.1f}/h, {d*24:.0f}/2h), n={len(fasting_drifts)}")

    all_drifts = [v['drift_per_5min'] for v in net_egp_by_patient.values()]
    print(f"\n  Patients with data: {len(net_egp_by_patient)}/{len(patients)}")
    print(f"  Population median net EGP: {np.median(all_drifts):.2f} mg/dL/5min ({np.median(all_drifts)*12:.1f}/h)")
    print(f"  Over 2h: {np.median(all_drifts)*24:.0f} mg/dL")

    # H1: Drift is 0-2 mg/dL/5min
    h1_in_range = sum(1 for d in all_drifts if -1 <= d <= 2)
    h1_pass = h1_in_range / len(all_drifts) >= 0.7
    print(f"\n  H1: Net EGP in [-1, 2] range: {h1_in_range}/{len(all_drifts)} ({h1_in_range/len(all_drifts)*100:.0f}%)")

    # ============================================================
    # PHASE 2: Full Insulin Accounting for Corrections
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 2: Full Insulin Accounting")
    print("=" * 70)
    print("  For each correction episode, compute:")
    print("  - Total active insulin: bolus + SMB + net_basal (ALL insulin delivered)")
    print("  - Pre-existing IOB: insulin already active before correction")
    print("  - Net new insulin: total - IOB_prior")

    reconciliation = {}

    for pid in patients:
        if pid not in net_egp_by_patient:
            continue

        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        bolus_v = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb_v = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal_v = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal_v = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        iob_v = pdf['iob'].values if 'iob' in pdf.columns else np.full(len(pdf), np.nan)
        isf_v = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        net_egp_2h = net_egp_by_patient[pid]['drift_2h']
        horizon = 24

        episodes = []
        for i in range(len(pdf) - horizon):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus_v[i]) or bolus_v[i] < 0.5:
                continue
            future = glucose[i:i+horizon+1]
            if np.sum(np.isnan(future)) > 7:
                continue
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < 5:
                continue

            actual_drop = glucose[i] - valid_f[-1]

            # All insulin delivered in 2h window
            total_bolus = np.nansum(bolus_v[i:i+horizon])
            total_smb = np.nansum(bolus_smb_v[i:i+horizon])
            total_net_basal = np.nansum(net_basal_v[i:i+horizon] * 5.0 / 60.0)
            excess_basal = np.nansum((net_basal_v[i:i+horizon] - sched_basal_v[i:i+horizon]) * 5.0 / 60.0)
            sched_basal_total = np.nansum(sched_basal_v[i:i+horizon] * 5.0 / 60.0)

            # Total insulin (all sources)
            all_insulin = total_bolus + total_smb + total_net_basal
            excess_insulin = total_bolus + total_smb + excess_basal

            # Pre-existing IOB
            iob_at_start = iob_v[i] if not np.isnan(iob_v[i]) else np.nan

            profile_isf = isf_v[i] if not np.isnan(isf_v[i]) else 50.0

            if all_insulin < 0.1 or excess_insulin < 0.1:
                continue

            # Method 1: Original (excess insulin × profile ISF)
            cf_original = actual_drop / (excess_insulin * profile_isf) if excess_insulin * profile_isf > 0 else np.nan

            # Method 2: EGP-corrected drop / excess insulin
            egp_corrected_drop = actual_drop + net_egp_2h
            isf_method2 = egp_corrected_drop / excess_insulin if excess_insulin > 0 else np.nan
            cf_method2 = isf_method2 / profile_isf if profile_isf > 0 and not np.isnan(isf_method2) else np.nan

            # Method 3: EGP-corrected drop / ALL insulin (including scheduled basal)
            isf_method3 = egp_corrected_drop / all_insulin if all_insulin > 0 else np.nan
            cf_method3 = isf_method3 / profile_isf if profile_isf > 0 and not np.isnan(isf_method3) else np.nan

            # Method 4: Account for IOB as well
            # The IOB at start will produce additional drop beyond what's delivered in the window
            # IOB contributes: IOB × true_ISF worth of drop over its remaining DIA
            # For now, just add IOB to the insulin accounting
            total_with_iob = all_insulin + (iob_at_start if not np.isnan(iob_at_start) else 0)
            isf_method4 = egp_corrected_drop / total_with_iob if total_with_iob > 0 else np.nan
            cf_method4 = isf_method4 / profile_isf if profile_isf > 0 and not np.isnan(isf_method4) else np.nan

            episodes.append({
                'actual_drop': actual_drop,
                'egp_corrected_drop': egp_corrected_drop,
                'excess_insulin': excess_insulin,
                'all_insulin': all_insulin,
                'total_with_iob': total_with_iob,
                'iob': iob_at_start if not np.isnan(iob_at_start) else 0,
                'profile_isf': profile_isf,
                'cf_original': cf_original,
                'cf_egp': cf_method2,
                'cf_all_insulin': cf_method3,
                'cf_full': cf_method4,
                'isf_original': actual_drop / excess_insulin if excess_insulin > 0 else np.nan,
                'isf_egp': isf_method2,
                'isf_all': isf_method3,
                'isf_full': isf_method4,
            })

        if len(episodes) >= 10:
            ep_df = pd.DataFrame(episodes)
            reconciliation[pid] = {
                'n': len(episodes),
                'profile_isf': float(ep_df['profile_isf'].median()),
                'cf_original': float(ep_df['cf_original'].median()),
                'cf_egp': float(ep_df['cf_egp'].median()),
                'cf_all_insulin': float(ep_df['cf_all_insulin'].median()),
                'cf_full': float(ep_df['cf_full'].median()),
                'isf_original': float(ep_df['isf_original'].median()),
                'isf_egp': float(ep_df['isf_egp'].median()),
                'isf_all': float(ep_df['isf_all'].median()),
                'isf_full': float(ep_df['isf_full'].median()),
                'median_excess_ins': float(ep_df['excess_insulin'].median()),
                'median_all_ins': float(ep_df['all_insulin'].median()),
                'median_iob': float(ep_df['iob'].median()),
                'net_egp_2h': float(net_egp_2h),
            }

    print(f"\n  Patients reconciled: {len(reconciliation)}/{len(patients)}")
    print(f"\n  {'Patient':<18} {'Prof ISF':>8} {'Raw ISF':>8} {'EGP ISF':>8} {'All ISF':>8} {'Full ISF':>8} {'CF_orig':>8} {'CF_full':>8}")
    for pid in sorted(reconciliation.keys()):
        r = reconciliation[pid]
        print(f"  {pid:<18} {r['profile_isf']:>8.0f} {r['isf_original']:>8.0f} {r['isf_egp']:>8.0f} "
              f"{r['isf_all']:>8.0f} {r['isf_full']:>8.0f} {r['cf_original']:>8.3f} {r['cf_full']:>8.3f}")

    # Population summary
    prof_isfs = [reconciliation[p]['profile_isf'] for p in reconciliation]
    raw_isfs = [reconciliation[p]['isf_original'] for p in reconciliation]
    egp_isfs = [reconciliation[p]['isf_egp'] for p in reconciliation]
    all_isfs = [reconciliation[p]['isf_all'] for p in reconciliation]
    full_isfs = [reconciliation[p]['isf_full'] for p in reconciliation]
    raw_cfs = [reconciliation[p]['cf_original'] for p in reconciliation]
    full_cfs = [reconciliation[p]['cf_full'] for p in reconciliation]

    print(f"\n  Population medians:")
    print(f"    Profile ISF:       {np.median(prof_isfs):>6.0f} mg/dL/U")
    print(f"    Raw actual ISF:    {np.median(raw_isfs):>6.0f} mg/dL/U  (CF={np.median(raw_cfs):.3f})")
    print(f"    + EGP correction:  {np.median(egp_isfs):>6.0f} mg/dL/U")
    print(f"    + All insulin:     {np.median(all_isfs):>6.0f} mg/dL/U")
    print(f"    + IOB (full):      {np.median(full_isfs):>6.0f} mg/dL/U  (CF={np.median(full_cfs):.3f})")

    # Gap closure
    original_gap = abs(np.median(raw_isfs) - np.median(prof_isfs))
    final_gap = abs(np.median(full_isfs) - np.median(prof_isfs))
    closure = (original_gap - final_gap) / original_gap * 100 if original_gap > 0 else 0
    print(f"\n  Gap closure: {closure:.0f}%")
    print(f"    Original gap: |{np.median(raw_isfs):.0f} - {np.median(prof_isfs):.0f}| = {original_gap:.0f}")
    print(f"    Final gap:    |{np.median(full_isfs):.0f} - {np.median(prof_isfs):.0f}| = {final_gap:.0f}")

    # H2: Full accounting ISF within 50% of profile
    ratio = np.median(full_isfs) / np.median(prof_isfs)
    h2_pass = 0.5 <= ratio <= 1.5
    print(f"\n  H2: Full ISF / Profile = {ratio:.2f} (within 50%: {'✓' if h2_pass else '✗'})")

    # H3: Adding IOB improves over EGP-only
    egp_gap = abs(np.median(egp_isfs) - np.median(prof_isfs))
    h3_pass = final_gap < egp_gap
    print(f"  H3: IOB improves over EGP-only: {'✓' if h3_pass else '✗'} (gap: {egp_gap:.0f} → {final_gap:.0f})")

    # H4: Reconciled ISF in physiological range (20-100)
    in_range = sum(1 for isf in full_isfs if 20 <= isf <= 100)
    h4_pass = in_range / len(full_isfs) >= 0.6
    print(f"  H4: ISF in [20, 100]: {in_range}/{len(full_isfs)} ({in_range/len(full_isfs)*100:.0f}%)")

    # H5: >80% gap closure
    h5_pass = closure >= 80
    print(f"  H5: Gap closure ≥80%: {closure:.0f}% {'✓' if h5_pass else '✗'}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1_egp_range': {'pass': bool(h1_pass)},
        'H2_within_50pct': {'pass': bool(h2_pass), 'ratio': float(ratio)},
        'H3_iob_helps': {'pass': bool(h3_pass)},
        'H4_physiological': {'pass': bool(h4_pass), 'in_range': in_range, 'total': len(full_isfs)},
        'H5_gap_closure': {'pass': bool(h5_pass), 'closure_pct': float(closure)},
        'total_pass': n_pass
    }
    results['reconciliation'] = reconciliation
    results['net_egp'] = {k: {kk: vv for kk, vv in v.items()} for k, v in net_egp_by_patient.items()}
    results['population'] = {
        'median_profile_isf': float(np.median(prof_isfs)),
        'median_raw_isf': float(np.median(raw_isfs)),
        'median_egp_isf': float(np.median(egp_isfs)),
        'median_all_isf': float(np.median(all_isfs)),
        'median_full_isf': float(np.median(full_isfs)),
        'gap_closure_pct': float(closure),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2758: Full ISF Gap Reconciliation', fontsize=16, fontweight='bold')

        # Panel 1: ISF waterfall (population)
        ax = axes[0, 0]
        methods = ['Profile', 'Raw\n(observed)', '+EGP', '+All\nInsulin', '+IOB\n(full)']
        values = [np.median(prof_isfs), np.median(raw_isfs), np.median(egp_isfs),
                  np.median(all_isfs), np.median(full_isfs)]
        colors = ['gray', '#e74c3c', '#f39c12', '#3498db', '#2ecc71']
        bars = ax.bar(methods, values, color=colors, alpha=0.8, edgecolor='black')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title('ISF Reconciliation Steps')
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1,
                    f'{val:.0f}', ha='center', va='bottom', fontweight='bold')

        # Panel 2: Per-patient raw vs reconciled
        ax = axes[0, 1]
        ax.scatter(prof_isfs, raw_isfs, s=40, alpha=0.5, c='red', label='Raw')
        ax.scatter(prof_isfs, full_isfs, s=40, alpha=0.7, c='green', label='Reconciled')
        lim = max(max(prof_isfs), max(full_isfs)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='1:1')
        ax.set_xlabel('Profile ISF')
        ax.set_ylabel('Estimated ISF')
        ax.set_title('Profile vs Estimated ISF')
        ax.legend()

        # Panel 3: CF improvement
        ax = axes[0, 2]
        pids_r = sorted(reconciliation.keys())
        x = np.arange(len(pids_r))
        raw_cf_vals = [reconciliation[p]['cf_original'] for p in pids_r]
        full_cf_vals = [reconciliation[p]['cf_full'] for p in pids_r]
        ax.bar(x - 0.2, raw_cf_vals, 0.4, label='Raw CF', color='coral', alpha=0.7)
        ax.bar(x + 0.2, full_cf_vals, 0.4, label='Reconciled CF', color='steelblue', alpha=0.7)
        ax.axhline(1.0, color='black', linestyle='--', alpha=0.5, label='Perfect')
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids_r], rotation=90, fontsize=6)
        ax.set_ylabel('Correction Factor')
        ax.set_title('CF: Raw vs Reconciled')
        ax.legend(fontsize=8)

        # Panel 4: Net EGP distribution
        ax = axes[1, 0]
        ax.hist(all_drifts, bins=20, color='coral', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(all_drifts), color='red', linestyle='-',
                   label=f'Median: {np.median(all_drifts):.2f}')
        ax.axvline(0, color='black', linestyle='--', alpha=0.5)
        ax.set_xlabel('Net EGP (mg/dL per 5min)')
        ax.set_ylabel('Count')
        ax.set_title('Net EGP Distribution (Fasting)')
        ax.legend()

        # Panel 5: Contribution decomposition (stacked)
        ax = axes[1, 1]
        categories = ['Observed\nDrop', 'EGP\n(adds back)', 'Basal\nInsulin', 'IOB']
        med_drop = np.median([reconciliation[p].get('cf_original', 0) * reconciliation[p]['profile_isf'] * reconciliation[p]['median_excess_ins'] for p in reconciliation])
        contributions = [
            np.median(prof_isfs) * 0.192,  # Raw actual ISF proxy
            np.median([net_egp_by_patient[p]['drift_2h'] for p in net_egp_by_patient if p in reconciliation]),
            0,  # placeholder
            0   # placeholder
        ]
        ax.text(0.5, 0.5, f"Gap Closure: {closure:.0f}%\n\n"
                f"Profile ISF: {np.median(prof_isfs):.0f}\n"
                f"Raw ISF: {np.median(raw_isfs):.0f}\n"
                f"→ EGP-corrected: {np.median(egp_isfs):.0f}\n"
                f"→ Full reconciled: {np.median(full_isfs):.0f}\n\n"
                f"Factors:\n"
                f"  Net EGP/2h: {np.median(all_drifts)*24:.0f} mg/dL\n"
                f"  Median IOB: {np.median([reconciliation[p]['median_iob'] for p in reconciliation]):.1f}U",
                transform=ax.transAxes, fontsize=11, va='center', ha='center',
                fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow'))
        ax.set_title('Reconciliation Accounting')
        ax.axis('off')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2758: Full ISF Reconciliation

Hypotheses: {n_pass}/5 PASS

ISF Progression (population medians):
  Profile:     {np.median(prof_isfs):>5.0f} mg/dL/U
  Raw:         {np.median(raw_isfs):>5.0f} mg/dL/U (CF=0.19)
  +EGP:        {np.median(egp_isfs):>5.0f} mg/dL/U
  +All insulin:{np.median(all_isfs):>5.0f} mg/dL/U
  +IOB (full): {np.median(full_isfs):>5.0f} mg/dL/U (CF={np.median(full_cfs):.2f})

Gap closure: {closure:.0f}%
  |{np.median(raw_isfs):.0f} - {np.median(prof_isfs):.0f}| → |{np.median(full_isfs):.0f} - {np.median(prof_isfs):.0f}|

Net EGP: {np.median(all_drifts):.2f} mg/dL/5min
  ({np.median(all_drifts)*24:.0f} mg/dL over 2h)
  This is ISF-INDEPENDENT measurement"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/isf-reconciliation', exist_ok=True)
        plt.savefig('tools/visualizations/isf-reconciliation/exp-2758-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/isf-reconciliation/exp-2758-dashboard.png")
    except Exception as e:
        print(f"  Dashboard error: {e}")
        traceback.print_exc()

    # Save
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, (np.bool_,)): return bool(obj)
            return super().default(obj)

    with open('externals/experiments/exp-2758_isf_reconciliation.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2758_isf_reconciliation.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
