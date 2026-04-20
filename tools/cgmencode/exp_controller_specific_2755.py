#!/usr/bin/env python3
"""
EXP-2755: Controller-Specific Settings Extraction

EXP-2754 revealed controller type explains 47.5% of ISF correction variance.
This experiment tests whether controller-specific extraction methods improve
accuracy vs. the unified pipeline.

Hypotheses:
  H1: Controller-specific ISF improves over unified ISF for ≥60% of patients
  H2: SMB-capable (Trio) benefits from separate SMB insulin accounting
  H3: Controller-specific CR improves over unified CR for ≥60%
  H4: Combined controller-specific pipeline beats unified by ≥5% MAE
  H5: Loop vs Trio have significantly different optimal DIA windows

Method:
  For each controller type:
    1. Extract ISF using only patients of that controller type
    2. Account for controller-specific insulin delivery patterns
    3. For Trio/OpenAPS: separate bolus vs SMB insulin accounting
    4. Compare per-controller extraction vs unified extraction
"""

import json
import sys
import os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {
        'experiment': 'EXP-2755',
        'title': 'Controller-Specific Settings Extraction',
        'hypotheses': {},
        'controller_analysis': {},
        'comparison': {}
    }

    # Load data
    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    # Classify patients by controller
    controller_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = pdf['bolus_smb'].sum() > 0 if 'bolus_smb' in pdf.columns else False
        # Check for loop-specific markers
        has_loop = 'loop_predicted_30' in pdf.columns and pdf['loop_predicted_30'].notna().sum() > 100
        has_oref = 'pred_iob_30' in pdf.columns and pdf['pred_iob_30'].notna().sum() > 100

        if has_loop and not has_smb:
            controller_map[pid] = 'Loop'
        elif has_smb and has_oref:
            controller_map[pid] = 'Trio'
        elif has_oref:
            controller_map[pid] = 'OpenAPS'
        elif has_smb:
            controller_map[pid] = 'Trio'
        else:
            controller_map[pid] = 'Unknown'

    ctrl_counts = {}
    for c in controller_map.values():
        ctrl_counts[c] = ctrl_counts.get(c, 0) + 1
    print(f"\nController distribution: {ctrl_counts}")

    # ============================================================
    # UNIFIED ISF EXTRACTION (baseline from EXP-2719b method)
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 1: Unified ISF Extraction (baseline)")
    print("=" * 70)

    def extract_correction_episodes(pdf, min_bg=180, min_bolus=0.5, horizon=24):
        """Extract correction episodes: BG≥180, bolus>0.5, track 2h."""
        episodes = []
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        for i in range(len(pdf) - horizon):
            if np.isnan(glucose[i]) or glucose[i] < min_bg:
                continue
            if np.isnan(bolus[i]) or bolus[i] < min_bolus:
                continue
            # Check enough glucose data in horizon
            future_glucose = glucose[i:i+horizon+1]
            if np.sum(np.isnan(future_glucose)) > horizon * 0.3:
                continue

            # Compute excess insulin over 2h
            total_bolus = np.nansum(bolus[i:i+horizon])
            total_smb = np.nansum(bolus_smb[i:i+horizon])
            excess_basal = np.nansum(
                (net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0 / 60.0
            )
            excess_insulin = total_bolus + total_smb + excess_basal

            if excess_insulin < 0.1:
                continue

            # Actual BG drop
            valid_future = future_glucose[~np.isnan(future_glucose)]
            if len(valid_future) < 5:
                continue
            actual_drop = glucose[i] - valid_future[-1]

            # Expected drop
            profile_isf = isf[i] if not np.isnan(isf[i]) else 50.0
            expected_drop = excess_insulin * profile_isf

            episodes.append({
                'start_bg': glucose[i],
                'actual_drop': actual_drop,
                'expected_drop': expected_drop,
                'excess_insulin': excess_insulin,
                'bolus': total_bolus,
                'smb': total_smb,
                'excess_basal': excess_basal,
                'profile_isf': profile_isf,
                'correction_factor': actual_drop / expected_drop if expected_drop > 0 else np.nan
            })

        return episodes

    unified_isf = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        episodes = extract_correction_episodes(pdf)
        if len(episodes) >= 10:
            cfs = [e['correction_factor'] for e in episodes if not np.isnan(e['correction_factor'])]
            if cfs:
                unified_isf[pid] = {
                    'correction_factor': float(np.median(cfs)),
                    'n_episodes': len(episodes),
                    'controller': controller_map[pid]
                }
                print(f"  {pid}: cf={np.median(cfs):.3f}, n={len(episodes)}, ctrl={controller_map[pid]}")

    # ============================================================
    # CONTROLLER-SPECIFIC ISF EXTRACTION
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 2: Controller-Specific ISF Extraction")
    print("=" * 70)

    def extract_isf_controller_specific(pdf, controller, horizon=24):
        """
        Controller-specific ISF extraction:
        - Loop: Standard bolus-only accounting (no SMB)
        - Trio: Separate bolus + SMB channels with different weights
        - OpenAPS: Similar to Trio but different DIA assumptions
        """
        episodes = []
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        for i in range(len(pdf) - horizon):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            future_glucose = glucose[i:i+horizon+1]
            if np.sum(np.isnan(future_glucose)) > horizon * 0.3:
                continue

            total_bolus = np.nansum(bolus[i:i+horizon])
            total_smb = np.nansum(bolus_smb[i:i+horizon])
            excess_basal = np.nansum(
                (net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0 / 60.0
            )

            if controller == 'Loop':
                # Loop: no SMB, bolus is the primary delivery
                # Weight excess basal less (Loop aggressively modulates temp basal)
                effective_insulin = total_bolus + 0.5 * excess_basal
            elif controller in ('Trio', 'OpenAPS'):
                # Trio/OpenAPS: SMB is a significant channel
                # SMB has slightly different dynamics (smaller, more frequent)
                effective_insulin = total_bolus + total_smb * 0.95 + 0.7 * excess_basal
            else:
                effective_insulin = total_bolus + total_smb + excess_basal

            if effective_insulin < 0.1:
                continue

            valid_future = future_glucose[~np.isnan(future_glucose)]
            if len(valid_future) < 5:
                continue
            actual_drop = glucose[i] - valid_future[-1]

            profile_isf = isf[i] if not np.isnan(isf[i]) else 50.0
            expected_drop = effective_insulin * profile_isf

            episodes.append({
                'actual_drop': actual_drop,
                'expected_drop': expected_drop,
                'effective_insulin': effective_insulin,
                'bolus': total_bolus,
                'smb': total_smb,
                'excess_basal': excess_basal,
                'profile_isf': profile_isf,
                'correction_factor': actual_drop / expected_drop if expected_drop > 0 else np.nan
            })

        return episodes

    controller_isf = {}
    for pid in patients:
        ctrl = controller_map[pid]
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        episodes = extract_isf_controller_specific(pdf, ctrl)
        if len(episodes) >= 10:
            cfs = [e['correction_factor'] for e in episodes if not np.isnan(e['correction_factor'])]
            if cfs:
                controller_isf[pid] = {
                    'correction_factor': float(np.median(cfs)),
                    'n_episodes': len(episodes),
                    'controller': ctrl
                }
                print(f"  {pid}: cf={np.median(cfs):.3f} (ctrl-specific), n={len(episodes)}")

    # ============================================================
    # SMB-SPECIFIC ANALYSIS (Trio patients)
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 3: SMB Channel Analysis (Trio/OpenAPS)")
    print("=" * 70)

    smb_analysis = {}
    for pid in patients:
        ctrl = controller_map[pid]
        if ctrl not in ('Trio', 'OpenAPS'):
            continue
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        total_smb = pdf['bolus_smb'].sum() if 'bolus_smb' in pdf.columns else 0
        total_bolus = pdf['bolus'].sum() if 'bolus' in pdf.columns else 0
        total_basal = pdf['net_basal'].sum() * 5.0 / 60.0 if 'net_basal' in pdf.columns else 0

        smb_frac = total_smb / (total_bolus + total_smb + 0.001)
        smb_analysis[pid] = {
            'smb_fraction': float(smb_frac),
            'total_smb': float(total_smb),
            'total_bolus': float(total_bolus),
            'total_basal': float(total_basal),
            'controller': ctrl
        }
        print(f"  {pid}: SMB={smb_frac:.1%} of bolus+SMB, bolus={total_bolus:.0f}U, smb={total_smb:.0f}U")

    # ============================================================
    # DIA WINDOW COMPARISON
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 4: DIA Window Comparison")
    print("=" * 70)

    dia_results = {}
    horizons = [12, 18, 24, 30, 36]  # 1h, 1.5h, 2h, 2.5h, 3h
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        ctrl = controller_map[pid]
        best_horizon = None
        best_variance = float('inf')
        horizon_cfs = {}

        for h in horizons:
            episodes = extract_correction_episodes(pdf, horizon=h)
            if len(episodes) < 10:
                continue
            cfs = [e['correction_factor'] for e in episodes if not np.isnan(e['correction_factor'])]
            if not cfs:
                continue
            # Best horizon = lowest variance in correction factors (most consistent)
            var = np.var(cfs)
            horizon_cfs[h] = {'median_cf': float(np.median(cfs)), 'var': float(var), 'n': len(cfs)}
            if var < best_variance:
                best_variance = var
                best_horizon = h

        if best_horizon:
            dia_results[pid] = {
                'best_horizon': best_horizon,
                'best_horizon_minutes': best_horizon * 5,
                'controller': ctrl,
                'all_horizons': horizon_cfs
            }
            print(f"  {pid}: best DIA={best_horizon*5}min, ctrl={ctrl}")

    # ============================================================
    # COMPARISON: Unified vs Controller-Specific
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 5: Unified vs Controller-Specific Comparison")
    print("=" * 70)

    # For patients with both methods, simulate with each ISF and compare
    comparison = {}
    unified_better = 0
    ctrl_better = 0
    tie = 0

    for pid in patients:
        if pid not in unified_isf or pid not in controller_isf:
            continue

        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        isf_val = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)
        cr_val = pdf['scheduled_cr'].values if 'scheduled_cr' in pdf.columns else np.full(len(pdf), 10.0)
        carbs = pdf['carbs'].values if 'carbs' in pdf.columns else np.zeros(len(pdf))

        unified_cf = unified_isf[pid]['correction_factor']
        ctrl_cf = controller_isf[pid]['correction_factor']

        # Compare on correction episodes: predict BG drop with each ISF
        episodes = extract_correction_episodes(pdf)
        if len(episodes) < 10:
            continue

        unified_errors = []
        ctrl_errors = []
        for ep in episodes:
            actual = ep['actual_drop']
            # Unified prediction
            unified_pred = ep['excess_insulin'] * ep['profile_isf'] * unified_cf
            # Controller-specific prediction
            ctrl_pred = ep['excess_insulin'] * ep['profile_isf'] * ctrl_cf
            unified_errors.append(abs(actual - unified_pred))
            ctrl_errors.append(abs(actual - ctrl_pred))

        unified_mae = np.median(unified_errors)
        ctrl_mae = np.median(ctrl_errors)
        improvement = (unified_mae - ctrl_mae) / unified_mae * 100 if unified_mae > 0 else 0

        comparison[pid] = {
            'unified_cf': float(unified_cf),
            'ctrl_cf': float(ctrl_cf),
            'unified_mae': float(unified_mae),
            'ctrl_mae': float(ctrl_mae),
            'improvement_pct': float(improvement),
            'controller': controller_map[pid],
            'n_episodes': len(episodes)
        }

        if improvement > 2:
            ctrl_better += 1
        elif improvement < -2:
            unified_better += 1
        else:
            tie += 1

        print(f"  {pid}: unified_cf={unified_cf:.3f} ctrl_cf={ctrl_cf:.3f} "
              f"improvement={improvement:+.1f}% ({controller_map[pid]})")

    total = ctrl_better + unified_better + tie
    print(f"\n  Controller-specific better: {ctrl_better}/{total} ({ctrl_better/total*100:.0f}%)")
    print(f"  Unified better: {unified_better}/{total} ({unified_better/total*100:.0f}%)")
    print(f"  Tie (<2% diff): {tie}/{total} ({tie/total*100:.0f}%)")

    # ============================================================
    # HYPOTHESES EVALUATION
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    # H1: Controller-specific ISF improves ≥60%
    h1_pass = ctrl_better / total >= 0.6 if total > 0 else False
    h1_detail = f"{ctrl_better}/{total} ({ctrl_better/total*100:.0f}%)" if total > 0 else "N/A"
    print(f"  {'✓' if h1_pass else '✗'} H1: Controller-specific ISF improves ≥60%: {h1_detail}")

    # H2: SMB-capable benefits from separate SMB accounting
    trio_improvements = [comparison[p]['improvement_pct'] for p in comparison
                         if comparison[p]['controller'] in ('Trio', 'OpenAPS')]
    h2_pass = np.median(trio_improvements) > 2 if trio_improvements else False
    h2_detail = f"median={np.median(trio_improvements):.1f}%" if trio_improvements else "N/A"
    print(f"  {'✓' if h2_pass else '✗'} H2: SMB-capable benefits: {h2_detail}")

    # H3: Controller-specific CR (not implemented — would need bilateral per-controller)
    h3_pass = False  # Placeholder — would need per-controller bilateral deconfounding
    print(f"  {'✓' if h3_pass else '✗'} H3: Controller-specific CR: NOT TESTED (need per-ctrl bilateral)")

    # H4: Combined pipeline beats unified by ≥5%
    median_improvement = np.median([comparison[p]['improvement_pct'] for p in comparison])
    h4_pass = median_improvement >= 5
    print(f"  {'✓' if h4_pass else '✗'} H4: ≥5% median improvement: {median_improvement:.1f}%")

    # H5: Loop vs Trio different optimal DIA
    loop_dias = [dia_results[p]['best_horizon_minutes'] for p in dia_results
                 if dia_results[p]['controller'] == 'Loop']
    trio_dias = [dia_results[p]['best_horizon_minutes'] for p in dia_results
                 if dia_results[p]['controller'] in ('Trio', 'OpenAPS')]
    if loop_dias and trio_dias:
        from scipy import stats
        stat, p_val = stats.mannwhitneyu(loop_dias, trio_dias, alternative='two-sided') if len(loop_dias) >= 2 else (0, 1.0)
        h5_pass = p_val < 0.05
        h5_detail = f"Loop median={np.median(loop_dias):.0f}min, Trio={np.median(trio_dias):.0f}min, p={p_val:.4f}"
    else:
        h5_pass = False
        h5_detail = "Insufficient data"
    print(f"  {'✓' if h5_pass else '✗'} H5: DIA differs by controller: {h5_detail}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1_ctrl_isf_improves': {'pass': bool(h1_pass), 'detail': h1_detail},
        'H2_smb_benefits': {'pass': bool(h2_pass), 'detail': h2_detail},
        'H3_ctrl_cr': {'pass': bool(h3_pass), 'detail': 'NOT TESTED'},
        'H4_combined_5pct': {'pass': bool(h4_pass), 'detail': f'{median_improvement:.1f}%'},
        'H5_dia_differs': {'pass': bool(h5_pass), 'detail': h5_detail},
        'total_pass': n_pass
    }
    results['controller_analysis'] = {
        'controller_map': controller_map,
        'smb_analysis': smb_analysis,
        'dia_results': {k: v for k, v in dia_results.items()},
    }
    results['comparison'] = comparison

    # ============================================================
    # DASHBOARD
    # ============================================================
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2755: Controller-Specific Settings Extraction', fontsize=16, fontweight='bold')

        # Panel 1: ISF correction by controller
        ax = axes[0, 0]
        for ctrl_name, color in [('Loop', 'blue'), ('Trio', 'green'), ('OpenAPS', 'red'), ('Unknown', 'gray')]:
            cfs = [unified_isf[p]['correction_factor'] for p in unified_isf
                   if unified_isf[p]['controller'] == ctrl_name]
            if cfs:
                ax.hist(cfs, bins=15, alpha=0.5, label=f'{ctrl_name} (n={len(cfs)})', color=color)
        ax.axvline(1.0, color='black', linestyle='--', alpha=0.5, label='Profile correct')
        ax.set_xlabel('ISF Correction Factor')
        ax.set_ylabel('Count')
        ax.set_title('ISF Correction by Controller')
        ax.legend(fontsize=8)

        # Panel 2: Unified vs Controller-specific
        ax = axes[0, 1]
        if comparison:
            pids = sorted(comparison.keys())
            unified_cfs = [comparison[p]['unified_cf'] for p in pids]
            ctrl_cfs = [comparison[p]['ctrl_cf'] for p in pids]
            colors = ['blue' if comparison[p]['controller'] == 'Loop'
                      else 'green' if comparison[p]['controller'] in ('Trio', 'OpenAPS')
                      else 'red' for p in pids]
            ax.scatter(unified_cfs, ctrl_cfs, c=colors, alpha=0.7, s=60)
            lims = [min(min(unified_cfs), min(ctrl_cfs)) * 0.9,
                    max(max(unified_cfs), max(ctrl_cfs)) * 1.1]
            ax.plot(lims, lims, 'k--', alpha=0.3)
            ax.set_xlabel('Unified ISF CF')
            ax.set_ylabel('Controller-Specific ISF CF')
            ax.set_title('Unified vs Controller-Specific ISF')

        # Panel 3: SMB fraction by patient
        ax = axes[0, 2]
        if smb_analysis:
            pids_smb = sorted(smb_analysis.keys())
            fracs = [smb_analysis[p]['smb_fraction'] for p in pids_smb]
            ctrls = [smb_analysis[p]['controller'] for p in pids_smb]
            colors_smb = ['green' if c == 'Trio' else 'red' for c in ctrls]
            ax.barh(range(len(pids_smb)), fracs, color=colors_smb, alpha=0.7)
            ax.set_yticks(range(len(pids_smb)))
            ax.set_yticklabels([p[:8] for p in pids_smb], fontsize=7)
            ax.set_xlabel('SMB Fraction of Total Bolus')
            ax.set_title('SMB Usage (Trio/OpenAPS)')

        # Panel 4: DIA by controller
        ax = axes[1, 0]
        if dia_results:
            loop_d = [dia_results[p]['best_horizon_minutes'] for p in dia_results
                      if dia_results[p]['controller'] == 'Loop']
            trio_d = [dia_results[p]['best_horizon_minutes'] for p in dia_results
                      if dia_results[p]['controller'] in ('Trio', 'OpenAPS')]
            other_d = [dia_results[p]['best_horizon_minutes'] for p in dia_results
                       if dia_results[p]['controller'] not in ('Loop', 'Trio', 'OpenAPS')]
            data = [d for d in [loop_d, trio_d, other_d] if d]
            labels = [l for l, d in [('Loop', loop_d), ('Trio/OAPS', trio_d), ('Other', other_d)] if d]
            if data:
                ax.boxplot(data, labels=labels)
            ax.set_ylabel('Optimal DIA Window (min)')
            ax.set_title('DIA Window by Controller')

        # Panel 5: Improvement distribution
        ax = axes[1, 1]
        if comparison:
            improvements = [comparison[p]['improvement_pct'] for p in comparison]
            ax.hist(improvements, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
            ax.axvline(0, color='red', linestyle='--', alpha=0.7, label='Break-even')
            ax.axvline(np.median(improvements), color='green', linestyle='-',
                       label=f'Median: {np.median(improvements):.1f}%')
            ax.set_xlabel('Improvement (%)')
            ax.set_ylabel('Count')
            ax.set_title('Controller-Specific vs Unified Improvement')
            ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary_text = f"""EXP-2755 Summary

Hypotheses: {n_pass}/5 PASS

Controller-specific better: {ctrl_better}/{total}
Unified better: {unified_better}/{total}
Tie: {tie}/{total}

Median improvement: {median_improvement:.1f}%

Key findings:
• Controller explains {47.5:.0f}% of ISF variance
• SMB accounting {"helps" if h2_pass else "minimal benefit"}
• DIA window {"differs" if h5_pass else "similar"} across controllers
"""
        ax.text(0.1, 0.9, summary_text, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/controller-specific', exist_ok=True)
        plt.savefig('tools/visualizations/controller-specific/exp-2755-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/controller-specific/exp-2755-dashboard.png")
    except Exception as e:
        print(f"  Dashboard error: {e}")
        traceback.print_exc()

    # Save results
    output_path = 'externals/experiments/exp-2755_controller_specific.json'

    # Convert for JSON
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return obj

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            r = convert(obj)
            if r is not obj:
                return r
            return super().default(obj)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: {output_path}")

    return results

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
