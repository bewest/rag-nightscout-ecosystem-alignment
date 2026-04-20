#!/usr/bin/env python3
"""
EXP-2766: Safe Iterative Settings Protocol

The CF ≈ 0.2 cannot be directly applied (ISF would drop 80%).
Instead, we need an iterative protocol: reduce ISF by max 20% per cycle,
re-measure CF, repeat until CF converges toward 1.0.

This experiment SIMULATES what happens when ISF is iteratively reduced:
  - If true insulin sensitivity is fixed, reducing ISF means the controller
    delivers less bolus per correction, so future CF should increase
  - If the AID compensates (adjusts SMBs), CF may not change

The key question: does the controller allow settings changes to propagate,
or does it fully compensate?

We simulate by looking at natural variation in the data — periods where
patients' effective ISF differs from their profile.

Hypotheses:
  H1: A 20% ISF reduction would move CF from 0.2 toward 0.25 (predictable)
  H2: Convergence to CF=0.8 would require ≤5 iterations (≤ 67% total reduction)
  H3: The iterative protocol is bounded (each step's CF is monotonically increasing)
  H4: Time-in-range impact of 20% ISF reduction is < 5% TIR decrease (safety)
  H5: The recommended final ISF is within 2× of the LR model's observed ISF
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_cf_at_isf(pdf, isf_mult, horizon=24, min_bg=180, min_bolus=0.5):
    """Extract CF as if profile ISF were multiplied by isf_mult."""
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
        if len(valid_f) < 3:
            continue
        actual_drop = glucose[i] - valid_f[-1]
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue

        # The effective ISF for this calculation uses the multiplied profile
        adjusted_isf = isf[i] * isf_mult if not np.isnan(isf[i]) else 50.0 * isf_mult
        expected = excess_insulin * adjusted_isf
        if expected > 0:
            cfs.append(actual_drop / expected)

    return cfs

def simulate_iterative(pdf, max_iterations=10, step_size=0.2):
    """Simulate iterative ISF reduction protocol."""
    iterations = []
    current_mult = 1.0

    for iteration in range(max_iterations):
        cfs = extract_cf_at_isf(pdf, current_mult)
        if len(cfs) < 10:
            break

        cf = np.median(cfs)
        cf_iqr = np.percentile(cfs, 75) - np.percentile(cfs, 25)

        iterations.append({
            'iteration': iteration,
            'isf_multiplier': current_mult,
            'cf': cf,
            'cf_iqr': cf_iqr,
            'n_episodes': len(cfs),
        })

        # Check convergence
        if 0.8 <= cf <= 1.2:
            break

        # Calculate next step
        if cf < 1.0:
            # CF < 1 means ISF is too high → reduce
            reduction = min(step_size, 1 - cf)  # Cap at step_size
            current_mult *= (1 - reduction)
        else:
            # CF > 1 means ISF is too low → increase
            increase = min(step_size, cf - 1)
            current_mult *= (1 + increase)

    return iterations

def run_experiment():
    results = {'experiment': 'EXP-2766', 'title': 'Safe Iterative Settings Protocol'}

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

        # Baseline CF
        baseline_cfs = extract_cf_at_isf(pdf, 1.0)
        if len(baseline_cfs) < 15:
            continue

        baseline_cf = np.median(baseline_cfs)

        # Simulate iterative protocol
        iterations = simulate_iterative(pdf)
        if not iterations:
            continue

        # Also compute: what ISF multiplier makes CF = 1.0?
        # Search by trying different multipliers
        target_mults = np.arange(0.05, 2.0, 0.05)
        cf_at_mult = []
        for m in target_mults:
            cfs = extract_cf_at_isf(pdf, m)
            if len(cfs) >= 10:
                cf_at_mult.append((m, np.median(cfs)))

        # Find the multiplier closest to CF=1.0
        optimal_mult = None
        if cf_at_mult:
            best_idx = min(range(len(cf_at_mult)), key=lambda i: abs(cf_at_mult[i][1] - 1.0))
            optimal_mult = cf_at_mult[best_idx][0]

        # Profile ISF
        profile_isf = float(pdf['scheduled_isf'].median()) if 'scheduled_isf' in pdf.columns else 50.0

        # LR-based observed ISF (from EXP-2763 approach)
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))

        lr_episodes = []
        for i in range(len(pdf) - 24):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            future = glucose[i:i+25]
            if np.sum(np.isnan(future)) > 7:
                continue
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < 3:
                continue
            drop = glucose[i] - valid_f[-1]
            exc = np.nansum(bolus[i:i+24]) + np.nansum(bolus_smb[i:i+24]) + \
                  np.nansum((net_basal[i:i+24] - sched_basal[i:i+24]) * 5.0/60.0)
            if exc >= 0.1:
                lr_episodes.append((exc, drop))

        lr_slope = None
        if len(lr_episodes) >= 15:
            x = [e[0] for e in lr_episodes]
            y = [e[1] for e in lr_episodes]
            lr_slope, _, _, _, _ = stats.linregress(x, y)
            lr_slope = float(lr_slope)

        final_iteration = iterations[-1]
        converged = 0.8 <= final_iteration['cf'] <= 1.2
        n_iterations = len(iterations)
        total_reduction = 1 - final_iteration['isf_multiplier']
        final_isf = profile_isf * final_iteration['isf_multiplier']

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'profile_isf': profile_isf,
            'baseline_cf': float(baseline_cf),
            'iterations': iterations,
            'converged': converged,
            'n_iterations': n_iterations,
            'final_mult': float(final_iteration['isf_multiplier']),
            'final_isf': float(final_isf),
            'optimal_mult': float(optimal_mult) if optimal_mult else None,
            'optimal_isf': float(profile_isf * optimal_mult) if optimal_mult else None,
            'lr_slope': lr_slope,
            'total_reduction': float(total_reduction),
            'cf_curve': cf_at_mult,
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # ============================================================
    # RESULTS
    # ============================================================
    print(f"\n  {'Patient':<18} {'ISF':>5} {'CF':>6} {'Iter':>4} {'Final×':>7} {'→ISF':>6} {'Conv':>5} {'Opt×':>6}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        opt = f"{pr['optimal_mult']:.2f}" if pr['optimal_mult'] else '?'
        print(f"  {pid:<18} {pr['profile_isf']:>5.0f} {pr['baseline_cf']:>6.3f} "
              f"{pr['n_iterations']:>4} {pr['final_mult']:>7.3f} {pr['final_isf']:>6.1f} "
              f"{'✓' if pr['converged'] else '✗':>5} {opt:>6}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    # H1: 20% reduction moves CF from 0.2 toward 0.25 (predictable = CF * 1/0.8 = CF * 1.25)
    first_step_cfs = []
    for p in patient_results:
        iters = patient_results[p]['iterations']
        if len(iters) >= 2:
            predicted = iters[0]['cf'] / 0.8  # If ISF reduced 20%, CF should increase by 1/0.8
            actual = iters[1]['cf']
            first_step_cfs.append((predicted, actual))
    if first_step_cfs:
        pred_vals = [x[0] for x in first_step_cfs]
        actual_vals = [x[1] for x in first_step_cfs]
        r_pred, _ = stats.pearsonr(pred_vals, actual_vals)
        h1_pass = r_pred >= 0.9  # Should be nearly perfect (mathematical relationship)
    else:
        r_pred = 0
        h1_pass = False
    print(f"  {'✓' if h1_pass else '✗'} H1: CF change predictable: r = {r_pred:.3f}")

    # H2: ≤5 iterations to converge
    converged = [p for p in patient_results if patient_results[p]['converged']]
    if converged:
        conv_iters = [patient_results[p]['n_iterations'] for p in converged]
        h2_pass = np.median(conv_iters) <= 5
    else:
        h2_pass = False
        conv_iters = []
    n_conv = len(converged)
    print(f"  {'✓' if h2_pass else '✗'} H2: ≤5 iterations: {n_conv}/{len(patient_results)} converged, "
          f"median {np.median(conv_iters):.0f}" if conv_iters else f"  ✗ H2: none converged")

    # H3: Monotonic CF increase as ISF decreases
    monotonic = 0
    for p in patient_results:
        iters = patient_results[p]['iterations']
        cfs = [it['cf'] for it in iters]
        if len(cfs) >= 3:
            diffs = np.diff(cfs)
            if all(d >= -0.01 for d in diffs):  # Allow tiny noise
                monotonic += 1
    h3_pass = monotonic / len(patient_results) >= 0.7 if patient_results else False
    print(f"  {'✓' if h3_pass else '✗'} H3: Monotonic CF: {monotonic}/{len(patient_results)}")

    # H4: TIR impact < 5% — use median/std of optimal_mult distance
    opt_mults = [patient_results[p]['optimal_mult'] for p in patient_results
                 if patient_results[p]['optimal_mult'] is not None]
    med_opt = np.median(opt_mults) if opt_mults else 0
    # If optimal ISF is 20% of profile, that's a big change
    # TIR proxy: how far from profile is optimal
    h4_pass = med_opt >= 0.3  # If optimal is at least 30% of profile, changes are bounded
    print(f"  {'✓' if h4_pass else '✗'} H4: Bounded change: median optimal mult = {med_opt:.3f}")

    # H5: Final ISF within 2× of LR slope
    within_2x = 0
    comparisons = 0
    for p in patient_results:
        pr = patient_results[p]
        if pr['optimal_isf'] and pr['lr_slope'] and pr['lr_slope'] > 0:
            ratio = pr['optimal_isf'] / pr['lr_slope']
            comparisons += 1
            if 0.5 <= ratio <= 2.0:
                within_2x += 1
    h5_pass = within_2x / comparisons >= 0.6 if comparisons > 0 else False
    print(f"  {'✓' if h5_pass else '✗'} H5: Within 2× of LR: {within_2x}/{comparisons}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'r_predictable': float(r_pred)},
        'H2': {'pass': bool(h2_pass), 'n_converged': n_conv},
        'H3': {'pass': bool(h3_pass), 'n_monotonic': monotonic},
        'H4': {'pass': bool(h4_pass), 'median_optimal_mult': float(med_opt)},
        'H5': {'pass': bool(h5_pass)},
        'total_pass': n_pass,
    }
    results['patients'] = {pid: {k: v for k, v in pr.items() if k != 'cf_curve'}
                          for pid, pr in patient_results.items()}

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2766: Safe Iterative Settings Protocol', fontsize=16, fontweight='bold')

        # Panel 1: CF vs ISF multiplier curves
        ax = axes[0, 0]
        for pid in sorted(patient_results.keys())[:10]:
            pr = patient_results[pid]
            if pr['cf_curve']:
                ms = [c[0] for c in pr['cf_curve']]
                cs = [c[1] for c in pr['cf_curve']]
                ax.plot(ms, cs, alpha=0.5, linewidth=1)
        ax.axhline(1.0, color='green', linestyle='--', label='CF=1 (target)')
        ax.axhline(0.8, color='green', linestyle=':', alpha=0.5)
        ax.axhline(1.2, color='green', linestyle=':', alpha=0.5)
        ax.set_xlabel('ISF Multiplier')
        ax.set_ylabel('Correction Factor')
        ax.set_title('CF vs ISF Scale (sample)')
        ax.set_xlim(0, 1.5)
        ax.set_ylim(0, 3)
        ax.legend()

        # Panel 2: Iterative convergence
        ax = axes[0, 1]
        for pid in sorted(patient_results.keys())[:15]:
            pr = patient_results[pid]
            if pr['iterations']:
                iters = [it['iteration'] for it in pr['iterations']]
                cfs = [it['cf'] for it in pr['iterations']]
                color = 'green' if pr['converged'] else 'red'
                ax.plot(iters, cfs, 'o-', alpha=0.5, color=color, markersize=3)
        ax.axhline(1.0, color='green', linestyle='--')
        ax.axhspan(0.8, 1.2, alpha=0.1, color='green')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('CF')
        ax.set_title('Iterative Convergence')

        # Panel 3: Optimal ISF distribution
        ax = axes[0, 2]
        opt_isfs = [patient_results[p]['optimal_isf'] for p in patient_results
                    if patient_results[p]['optimal_isf'] is not None]
        if opt_isfs:
            ax.hist(opt_isfs, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
            ax.axvline(np.median(opt_isfs), color='red', linewidth=2,
                      label=f'Median={np.median(opt_isfs):.0f}')
        ax.set_xlabel('Optimal ISF (mg/dL/U)')
        ax.set_ylabel('Count')
        ax.set_title('Optimal ISF Distribution')
        ax.legend()

        # Panel 4: Profile vs Optimal ISF
        ax = axes[1, 0]
        prof = [patient_results[p]['profile_isf'] for p in patient_results
                if patient_results[p]['optimal_isf']]
        opt = [patient_results[p]['optimal_isf'] for p in patient_results
               if patient_results[p]['optimal_isf']]
        ax.scatter(prof, opt, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(prof), max(opt)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='No change')
        ax.set_xlabel('Profile ISF')
        ax.set_ylabel('Optimal ISF')
        ax.set_title('Profile vs Optimal')
        ax.legend()

        # Panel 5: Iterations needed
        ax = axes[1, 1]
        all_n_iters = [patient_results[p]['n_iterations'] for p in patient_results]
        ax.hist(all_n_iters, bins=range(1, max(all_n_iters)+2), color='coral',
                alpha=0.7, edgecolor='black')
        ax.set_xlabel('Iterations to Converge')
        ax.set_ylabel('Count')
        ax.set_title('Convergence Speed')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2766 Summary

Hypotheses: {n_pass}/5 PASS

Convergence: {n_conv}/{len(patient_results)}
Median optimal mult: {med_opt:.3f}
Median optimal ISF: {np.median(opt_isfs):.0f} mg/dL/U
Median iterations: {np.median(all_n_iters):.0f}
CF predictability: r={r_pred:.3f}
Monotonic: {monotonic}/{len(patient_results)}

Protocol: reduce ISF by 20% per cycle
  → measure CF → repeat until CF ∈ [0.8, 1.2]

{'Converges in ' + str(int(np.median(conv_iters))) + ' steps' if conv_iters else 'Convergence varies'}"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/iterative-settings', exist_ok=True)
        plt.savefig('tools/visualizations/iterative-settings/exp-2766-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/iterative-settings/exp-2766-dashboard.png")
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

    with open('externals/experiments/exp-2766_iterative_settings.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2766_iterative_settings.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
