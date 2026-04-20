#!/usr/bin/env python3
"""
EXP-2759: DIA Window & Correction Factor Mechanism

EXP-2755 found Loop optimal DIA=60min, Trio=120min (p=0.022).
EXP-2758 confirmed correction factors work despite the ISF quantity mismatch.

This experiment investigates:
1. WHY does DIA differ between controllers?
2. What does the correction factor actually represent mechanistically?
3. Can we improve the CF by using the controller-optimal DIA window?
4. Is the CF stable across DIA windows (or window-dependent artifact)?

Hypotheses:
  H1: CF extracted at optimal DIA is more stable (lower variance) than at 2h
  H2: Trio's 120min optimal reflects SMB tail (SMBs delivered over longer window)
  H3: CF × profile ISF at optimal DIA falls in 15-40 mg/dL/U range (physiological)
  H4: DIA-optimized pipeline outperforms fixed-2h pipeline
  H5: CF at different windows is highly correlated (r>0.8) — patient characteristic
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
        'experiment': 'EXP-2759',
        'title': 'DIA Window & Correction Factor Mechanism',
        'hypotheses': {}
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    # Classify controllers
    controller_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = pdf['bolus_smb'].sum() > 0 if 'bolus_smb' in pdf.columns else False
        has_loop = 'loop_predicted_30' in pdf.columns and pdf['loop_predicted_30'].notna().sum() > 100
        if has_loop and not has_smb:
            controller_map[pid] = 'Loop'
        elif has_smb:
            controller_map[pid] = 'Trio'
        else:
            controller_map[pid] = 'Other'

    # ============================================================
    # PHASE 1: Multi-horizon CF extraction
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 1: Multi-Horizon CF Extraction")
    print("=" * 70)

    horizons = [6, 12, 18, 24, 30, 36, 48]  # 30min to 4h
    horizon_labels = ['30m', '1h', '1.5h', '2h', '2.5h', '3h', '4h']

    patient_results = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        horizon_data = {}

        for h in horizons:
            cfs = []
            for i in range(len(pdf) - h):
                if np.isnan(glucose[i]) or glucose[i] < 180:
                    continue
                if np.isnan(bolus[i]) or bolus[i] < 0.5:
                    continue
                future = glucose[i:i+h+1]
                if np.sum(np.isnan(future)) > h * 0.3:
                    continue
                valid_f = future[~np.isnan(future)]
                if len(valid_f) < max(3, h//4):
                    continue

                actual_drop = glucose[i] - valid_f[-1]
                total_bolus = np.nansum(bolus[i:i+h])
                total_smb = np.nansum(bolus_smb[i:i+h])
                excess_basal = np.nansum((net_basal[i:i+h] - sched_basal[i:i+h]) * 5.0/60.0)
                excess_insulin = total_bolus + total_smb + excess_basal

                if excess_insulin < 0.1:
                    continue
                profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
                expected = excess_insulin * profile_isf_val
                if expected > 0:
                    cfs.append(actual_drop / expected)

            if len(cfs) >= 10:
                horizon_data[h] = {
                    'median_cf': float(np.median(cfs)),
                    'var_cf': float(np.var(cfs)),
                    'std_cf': float(np.std(cfs)),
                    'iqr_cf': float(np.percentile(cfs, 75) - np.percentile(cfs, 25)),
                    'n': len(cfs),
                    'actual_isf': float(np.median(cfs) * np.nanmedian(isf[~np.isnan(isf)])),
                }

        if horizon_data:
            # Find optimal DIA (lowest CF variance / IQR relative to median)
            best_h = min(horizon_data.keys(),
                         key=lambda h: horizon_data[h]['iqr_cf'] / abs(horizon_data[h]['median_cf'] + 0.001))
            patient_results[pid] = {
                'horizons': horizon_data,
                'best_horizon': best_h,
                'best_horizon_min': best_h * 5,
                'controller': controller_map[pid],
                'cf_at_2h': horizon_data.get(24, {}).get('median_cf', np.nan),
                'cf_at_best': horizon_data[best_h]['median_cf'],
                'var_at_2h': horizon_data.get(24, {}).get('var_cf', np.nan),
                'var_at_best': horizon_data[best_h]['var_cf'],
            }

    print(f"  Patients analyzed: {len(patient_results)}")

    # ============================================================
    # PHASE 2: DIA by Controller
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 2: Optimal DIA by Controller")
    print("=" * 70)

    for ctrl in ['Loop', 'Trio', 'Other']:
        dias = [patient_results[p]['best_horizon_min'] for p in patient_results
                if patient_results[p]['controller'] == ctrl]
        if dias:
            print(f"  {ctrl:8s}: n={len(dias)}, median DIA={np.median(dias):.0f}min, "
                  f"mean={np.mean(dias):.0f}min, range={min(dias)}-{max(dias)}min")

    # ============================================================
    # PHASE 3: CF Stability Across Windows
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 3: CF Stability Across DIA Windows")
    print("=" * 70)

    # Check: are CFs correlated across windows?
    # Extract CF at 1h and 2h for each patient
    cf_1h = []
    cf_2h = []
    cf_3h = []
    pid_list = []
    for pid in patient_results:
        h_data = patient_results[pid]['horizons']
        if 12 in h_data and 24 in h_data and 36 in h_data:
            cf_1h.append(h_data[12]['median_cf'])
            cf_2h.append(h_data[24]['median_cf'])
            cf_3h.append(h_data[36]['median_cf'])
            pid_list.append(pid)

    if len(cf_1h) >= 5:
        r12, p12 = stats.pearsonr(cf_1h, cf_2h)
        r23, p23 = stats.pearsonr(cf_2h, cf_3h)
        r13, p13 = stats.pearsonr(cf_1h, cf_3h)
        print(f"  CF(1h) vs CF(2h): r={r12:.3f}, p={p12:.4e}")
        print(f"  CF(2h) vs CF(3h): r={r23:.3f}, p={p23:.4e}")
        print(f"  CF(1h) vs CF(3h): r={r13:.3f}, p={p13:.4e}")
        h5_pass = r12 > 0.8
    else:
        h5_pass = False
        r12 = 0

    # ============================================================
    # PHASE 4: SMB Timeline Analysis
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 4: SMB Delivery Timeline (Why Trio needs longer DIA?)")
    print("=" * 70)

    smb_timing = {}
    for pid in patients:
        ctrl = controller_map[pid]
        if ctrl != 'Trio':
            continue
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        bolus_vals = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        smb_vals = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))

        # Find correction episodes and track when SMBs come
        smb_delays = []
        for i in range(len(pdf) - 48):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus_vals[i]) or bolus_vals[i] < 0.5:
                continue
            # Track SMB delivery in the 4h after correction
            for j in range(1, 48):
                if smb_vals[i+j] > 0:
                    smb_delays.append(j * 5)  # minutes after correction

        if smb_delays:
            smb_timing[pid] = {
                'median_delay': float(np.median(smb_delays)),
                'pct_within_1h': float(np.sum(np.array(smb_delays) <= 60) / len(smb_delays) * 100),
                'pct_within_2h': float(np.sum(np.array(smb_delays) <= 120) / len(smb_delays) * 100),
                'n_smbs': len(smb_delays)
            }
            print(f"  {pid}: median SMB at {np.median(smb_delays):.0f}min post-correction, "
                  f"{smb_timing[pid]['pct_within_1h']:.0f}% within 1h, "
                  f"{smb_timing[pid]['pct_within_2h']:.0f}% within 2h")

    if smb_timing:
        all_pct_2h = [v['pct_within_2h'] for v in smb_timing.values()]
        all_delays = [v['median_delay'] for v in smb_timing.values()]
        print(f"\n  Population: median SMB delay={np.median(all_delays):.0f}min, "
              f"{np.median(all_pct_2h):.0f}% within 2h")
        h2_pass = np.median(all_delays) > 30  # SMBs continue beyond 30min
    else:
        h2_pass = False

    # ============================================================
    # PHASE 5: DIA-optimized vs fixed pipeline
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 5: DIA-Optimized vs Fixed-2h Pipeline")
    print("=" * 70)

    improvements = []
    for pid in patient_results:
        r = patient_results[pid]
        if 'var_at_2h' in r and not np.isnan(r['var_at_2h']) and r['var_at_best'] > 0:
            var_reduction = (r['var_at_2h'] - r['var_at_best']) / r['var_at_2h'] * 100
            improvements.append(var_reduction)
            print(f"  {pid}: best DIA={r['best_horizon_min']}min, "
                  f"var reduction={var_reduction:.1f}%, "
                  f"CF: {r['cf_at_2h']:.3f}→{r['cf_at_best']:.3f}")

    if improvements:
        median_improvement = np.median(improvements)
        h4_pass = median_improvement > 5
        print(f"\n  Median variance reduction: {median_improvement:.1f}%")
    else:
        h4_pass = False

    # H1: CF at optimal DIA has lower variance
    h1_pass = any(patient_results[p]['var_at_best'] < patient_results[p].get('var_at_2h', float('inf'))
                   for p in patient_results if not np.isnan(patient_results[p].get('var_at_2h', np.nan)))
    h1_count = sum(1 for p in patient_results
                   if not np.isnan(patient_results[p].get('var_at_2h', np.nan))
                   and patient_results[p]['var_at_best'] < patient_results[p]['var_at_2h'])
    h1_total = sum(1 for p in patient_results if not np.isnan(patient_results[p].get('var_at_2h', np.nan)))
    h1_pass = h1_count / h1_total >= 0.6 if h1_total > 0 else False

    # H3: CF × ISF at optimal DIA in 15-40 range
    actual_isfs = [patient_results[p]['horizons'][patient_results[p]['best_horizon']]['actual_isf']
                   for p in patient_results]
    in_range = sum(1 for isf in actual_isfs if 15 <= isf <= 40)
    h3_pass = in_range / len(actual_isfs) >= 0.5 if actual_isfs else False
    print(f"\n  H3: Actual ISF at best DIA in [15, 40]: {in_range}/{len(actual_isfs)}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)
    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    for label, passed, detail in [
        ('H1', h1_pass, f'{h1_count}/{h1_total} lower variance at optimal'),
        ('H2', h2_pass, f'SMB median delay={np.median(all_delays):.0f}min' if smb_timing else 'N/A'),
        ('H3', h3_pass, f'{in_range}/{len(actual_isfs)} in [15,40]'),
        ('H4', h4_pass, f'median var reduction={np.median(improvements):.1f}%' if improvements else 'N/A'),
        ('H5', h5_pass, f'r(1h,2h)={r12:.3f}')]:
        print(f"  {'✓' if passed else '✗'} {label}: {detail}")
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1_lower_var': {'pass': bool(h1_pass)},
        'H2_smb_tail': {'pass': bool(h2_pass)},
        'H3_physiological': {'pass': bool(h3_pass)},
        'H4_dia_optimized': {'pass': bool(h4_pass)},
        'H5_cf_stable': {'pass': bool(h5_pass), 'r_1h_2h': float(r12) if cf_1h else None},
        'total_pass': n_pass
    }
    results['patient_results'] = {k: {kk: vv for kk, vv in v.items() if kk != 'horizons'}
                                   for k, v in patient_results.items()}
    results['smb_timing'] = smb_timing

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2759: DIA Window & Correction Factor Mechanism', fontsize=16, fontweight='bold')

        # Panel 1: CF across horizons (mean + std across patients)
        ax = axes[0, 0]
        for ctrl, color in [('Loop', 'blue'), ('Trio', 'green')]:
            means, stds = [], []
            for h in horizons:
                cfs = [patient_results[p]['horizons'][h]['median_cf']
                       for p in patient_results
                       if patient_results[p]['controller'] == ctrl and h in patient_results[p]['horizons']]
                if cfs:
                    means.append(np.median(cfs))
                    stds.append(np.std(cfs))
                else:
                    means.append(np.nan)
                    stds.append(np.nan)
            ax.plot([h*5 for h in horizons], means, 'o-', color=color, label=ctrl)
            ax.fill_between([h*5 for h in horizons],
                           [m-s for m, s in zip(means, stds)],
                           [m+s for m, s in zip(means, stds)],
                           color=color, alpha=0.2)
        ax.set_xlabel('DIA Window (minutes)')
        ax.set_ylabel('Median CF')
        ax.set_title('CF by DIA Window')
        ax.legend()

        # Panel 2: Optimal DIA distribution
        ax = axes[0, 1]
        loop_dias = [patient_results[p]['best_horizon_min'] for p in patient_results
                     if patient_results[p]['controller'] == 'Loop']
        trio_dias = [patient_results[p]['best_horizon_min'] for p in patient_results
                     if patient_results[p]['controller'] == 'Trio']
        if loop_dias:
            ax.hist(loop_dias, bins=range(25, 250, 25), alpha=0.5, color='blue', label=f'Loop (n={len(loop_dias)})')
        if trio_dias:
            ax.hist(trio_dias, bins=range(25, 250, 25), alpha=0.5, color='green', label=f'Trio (n={len(trio_dias)})')
        ax.set_xlabel('Optimal DIA (minutes)')
        ax.set_ylabel('Count')
        ax.set_title('Optimal DIA Distribution')
        ax.legend()

        # Panel 3: CF(1h) vs CF(2h) scatter
        ax = axes[0, 2]
        if cf_1h:
            ax.scatter(cf_1h, cf_2h, s=40, alpha=0.7, c='steelblue')
            lim = max(max(cf_1h), max(cf_2h)) * 1.1
            ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
            ax.set_xlabel('CF at 1h')
            ax.set_ylabel('CF at 2h')
            ax.set_title(f'CF Stability: r={r12:.3f}')

        # Panel 4: SMB timing
        ax = axes[1, 0]
        if smb_timing:
            pids_smb = sorted(smb_timing.keys())[:15]
            pct1h = [smb_timing[p]['pct_within_1h'] for p in pids_smb]
            pct2h = [smb_timing[p]['pct_within_2h'] for p in pids_smb]
            x = np.arange(len(pids_smb))
            ax.bar(x, pct1h, label='Within 1h', color='steelblue', alpha=0.7)
            ax.bar(x, [p2-p1 for p1, p2 in zip(pct1h, pct2h)], bottom=pct1h,
                   label='1h-2h', color='coral', alpha=0.7)
            ax.set_xticks(x)
            ax.set_xticklabels([p[:6] for p in pids_smb], rotation=90, fontsize=7)
            ax.set_ylabel('% of SMBs')
            ax.set_title('SMB Timing After Correction')
            ax.legend(fontsize=8)

        # Panel 5: Variance reduction
        ax = axes[1, 1]
        if improvements:
            ax.hist(improvements, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
            ax.axvline(0, color='red', linestyle='--')
            ax.axvline(np.median(improvements), color='green', linestyle='-',
                       label=f'Median: {np.median(improvements):.1f}%')
            ax.set_xlabel('Variance Reduction (%)')
            ax.set_ylabel('Count')
            ax.set_title('DIA Optimization Benefit')
            ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2759 Summary

Hypotheses: {n_pass}/5 PASS

DIA by controller:
  Loop: {np.median(loop_dias):.0f}min (n={len(loop_dias)})
  Trio: {np.median(trio_dias):.0f}min (n={len(trio_dias)})

CF stability: r(1h,2h) = {r12:.3f}
{'→ CFs are patient characteristics' if r12 > 0.8 else '→ CFs are window-dependent'}

SMB timing:
  Median delay: {np.median(all_delays):.0f}min post-correction

Variance reduction with optimal DIA:
  Median: {np.median(improvements):.1f}%"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/dia-window', exist_ok=True)
        plt.savefig('tools/visualizations/dia-window/exp-2759-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/dia-window/exp-2759-dashboard.png")
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

    with open('externals/experiments/exp-2759_dia_window.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2759_dia_window.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
