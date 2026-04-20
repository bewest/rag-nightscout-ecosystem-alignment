#!/usr/bin/env python3
"""
EXP-2769: 72-Hour Total Insulin Accounting

User requested: "total insulin accounting over 72 hours as a smell/sanity check"

This experiment computes rolling 72h insulin summaries per patient:
  - Total delivered insulin (bolus + SMB + basal)
  - Expected from profile (scheduled_basal_rate × 72h)
  - Over/under delivery ratio
  - Correlation with outcomes (mean BG, TIR, hypo frequency)

The 72h window captures:
  - Full insulin activity tail (DIA 6-10h, well contained)
  - Hepatic glycogen cycling (~72h for full turnover)
  - Multi-day pattern stability

Hypotheses:
  H1: Total insulin varies >2× between 72h windows within patients
  H2: Over-delivery ratio correlates with lower mean BG (r<-0.2)
  H3: Profile basal accounts for 40-70% of total insulin
  H4: Bolus fraction varies with controller type (Loop vs Trio)
  H5: 72h insulin correlates with next-24h outcomes (predictive)
"""

import json, sys, os, traceback
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {'experiment': 'EXP-2769', 'title': '72h Total Insulin Accounting'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    # 72h = 864 5-min intervals
    WINDOW_72H = 864
    WINDOW_24H = 288

    patient_results = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)

        if len(pdf) < WINDOW_72H + WINDOW_24H:
            continue

        has_smb = 'bolus_smb' in pdf.columns and (pdf['bolus_smb'].fillna(0) > 0).any()
        ctrl = 'Trio' if has_smb else 'Loop'

        # Compute 5-min insulin amounts
        bolus = pdf['bolus'].fillna(0).values
        smb = pdf['bolus_smb'].fillna(0).values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].fillna(0).values  # U/hr
        sched_basal = pdf['scheduled_basal_rate'].fillna(0).values  # U/hr
        glucose = pdf['glucose'].values

        # Convert rates to 5-min amounts
        basal_delivered = net_basal * 5.0 / 60.0  # U per 5min
        basal_scheduled = sched_basal * 5.0 / 60.0

        windows = []
        step = WINDOW_24H  # 24h non-overlapping steps

        for start in range(0, len(pdf) - WINDOW_72H - WINDOW_24H, step):
            end = start + WINDOW_72H
            future_end = end + WINDOW_24H

            # 72h insulin sums
            total_bolus = np.nansum(bolus[start:end])
            total_smb = np.nansum(smb[start:end])
            total_basal = np.nansum(basal_delivered[start:end])
            total_sched_basal = np.nansum(basal_scheduled[start:end])
            total_insulin = total_bolus + total_smb + total_basal

            if total_insulin <= 0 or total_sched_basal <= 0:
                continue

            delivery_ratio = total_insulin / total_sched_basal
            basal_frac = total_basal / total_insulin if total_insulin > 0 else 0
            bolus_frac = total_bolus / total_insulin if total_insulin > 0 else 0
            smb_frac = total_smb / total_insulin if total_insulin > 0 else 0

            # 72h glucose summary
            g72 = glucose[start:end]
            valid_g = g72[~np.isnan(g72)]
            if len(valid_g) < 100:
                continue
            mean_bg = np.mean(valid_g)
            tir = np.mean((valid_g >= 70) & (valid_g <= 180)) * 100
            hypo_frac = np.mean(valid_g < 70) * 100

            # Next 24h outcomes
            g_next = glucose[end:future_end]
            valid_next = g_next[~np.isnan(g_next)]
            if len(valid_next) < 50:
                continue
            next_mean_bg = np.mean(valid_next)
            next_tir = np.mean((valid_next >= 70) & (valid_next <= 180)) * 100
            next_hypo = np.mean(valid_next < 70) * 100

            windows.append({
                'total_insulin': total_insulin,
                'total_bolus': total_bolus,
                'total_smb': total_smb,
                'total_basal': total_basal,
                'total_sched_basal': total_sched_basal,
                'delivery_ratio': delivery_ratio,
                'basal_frac': basal_frac,
                'bolus_frac': bolus_frac,
                'smb_frac': smb_frac,
                'mean_bg': mean_bg,
                'tir': tir,
                'hypo_frac': hypo_frac,
                'next_mean_bg': next_mean_bg,
                'next_tir': next_tir,
                'next_hypo': next_hypo,
            })

        if len(windows) < 3:
            continue

        wdf = pd.DataFrame(windows)

        # H1: Variability
        cv_insulin = wdf['total_insulin'].std() / wdf['total_insulin'].mean()
        max_min_ratio = wdf['total_insulin'].max() / wdf['total_insulin'].min() if wdf['total_insulin'].min() > 0 else 0

        # H2: Delivery ratio vs BG
        if wdf['delivery_ratio'].std() > 0 and wdf['mean_bg'].std() > 0:
            r_delivery_bg, p_delivery_bg = stats.pearsonr(wdf['delivery_ratio'], wdf['mean_bg'])
        else:
            r_delivery_bg, p_delivery_bg = 0, 1

        # H5: Predictive
        if wdf['total_insulin'].std() > 0 and wdf['next_mean_bg'].std() > 0:
            r_predictive, p_predictive = stats.pearsonr(wdf['total_insulin'], wdf['next_mean_bg'])
        else:
            r_predictive, p_predictive = 0, 1

        patient_results[pid] = {
            'controller': ctrl,
            'n_windows': len(windows),
            'med_total_insulin': float(wdf['total_insulin'].median()),
            'med_daily_insulin': float(wdf['total_insulin'].median() / 3),
            'cv_insulin': float(cv_insulin),
            'max_min_ratio': float(max_min_ratio),
            'med_delivery_ratio': float(wdf['delivery_ratio'].median()),
            'med_basal_frac': float(wdf['basal_frac'].median()),
            'med_bolus_frac': float(wdf['bolus_frac'].median()),
            'med_smb_frac': float(wdf['smb_frac'].median()),
            'med_mean_bg': float(wdf['mean_bg'].median()),
            'med_tir': float(wdf['tir'].median()),
            'r_delivery_bg': float(r_delivery_bg),
            'r_predictive': float(r_predictive),
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # Summary table
    print(f"\n  {'Patient':<18} {'Ctrl':<5} {'TDD':>5} {'72hU':>6} {'Del%':>5} "
          f"{'Bas%':>5} {'Bol%':>5} {'SMB%':>5} {'BG':>5} {'TIR':>4}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['controller']:<5} {pr['med_daily_insulin']:>5.1f} "
              f"{pr['med_total_insulin']:>6.1f} {pr['med_delivery_ratio']*100:>4.0f}% "
              f"{pr['med_basal_frac']*100:>4.0f}% {pr['med_bolus_frac']*100:>4.0f}% "
              f"{pr['med_smb_frac']*100:>4.0f}% {pr['med_mean_bg']:>5.0f} "
              f"{pr['med_tir']:>4.0f}")

    # Hypotheses
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    ratios = [patient_results[p]['max_min_ratio'] for p in patient_results]
    h1_pass = np.median(ratios) >= 2.0
    print(f"  {'✓' if h1_pass else '✗'} H1: 72h max/min ≥2×: median {np.median(ratios):.1f}×")

    r_del_bgs = [patient_results[p]['r_delivery_bg'] for p in patient_results]
    med_r = np.median(r_del_bgs)
    h2_pass = med_r < -0.2
    print(f"  {'✓' if h2_pass else '✗'} H2: Delivery ratio vs BG r<-0.2: median r={med_r:.3f}")

    basal_fracs = [patient_results[p]['med_basal_frac'] for p in patient_results]
    med_bf = np.median(basal_fracs)
    h3_pass = 0.40 <= med_bf <= 0.70
    print(f"  {'✓' if h3_pass else '✗'} H3: Basal 40-70%: median {med_bf*100:.0f}%")

    # H4: Controller type comparison
    loop_bf = [patient_results[p]['med_bolus_frac'] for p in patient_results
               if patient_results[p]['controller'] == 'Loop']
    trio_bf = [patient_results[p]['med_bolus_frac'] for p in patient_results
               if patient_results[p]['controller'] == 'Trio']
    if len(loop_bf) >= 2 and len(trio_bf) >= 2:
        t, p_val = stats.mannwhitneyu(loop_bf, trio_bf, alternative='two-sided')
        h4_pass = p_val < 0.05
        print(f"  {'✓' if h4_pass else '✗'} H4: Loop vs Trio bolus%: "
              f"Loop={np.median(loop_bf)*100:.0f}% Trio={np.median(trio_bf)*100:.0f}% p={p_val:.3f}")
    else:
        h4_pass = False
        print(f"  ✗ H4: Insufficient controller type data")

    r_preds = [patient_results[p]['r_predictive'] for p in patient_results]
    med_rp = np.median(r_preds)
    h5_pass = abs(med_rp) > 0.2
    print(f"  {'✓' if h5_pass else '✗'} H5: Predictive r>|0.2|: median r={med_rp:.3f}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Population summary
    tdds = [patient_results[p]['med_daily_insulin'] for p in patient_results]
    del_ratios = [patient_results[p]['med_delivery_ratio'] for p in patient_results]
    smb_fracs = [patient_results[p]['med_smb_frac'] for p in patient_results
                 if patient_results[p]['controller'] == 'Trio']
    print(f"\n  POPULATION STATISTICS:")
    print(f"    Daily insulin (TDD): median {np.median(tdds):.1f}U "
          f"(IQR {np.percentile(tdds, 25):.1f}-{np.percentile(tdds, 75):.1f})")
    print(f"    Delivery ratio: median {np.median(del_ratios):.2f}× "
          f"(1.0 = exactly profile basal)")
    print(f"    Basal fraction: median {med_bf*100:.0f}%")
    print(f"    Bolus fraction: median {np.median([patient_results[p]['med_bolus_frac'] for p in patient_results])*100:.0f}%")
    if smb_fracs:
        print(f"    SMB fraction (Trio): median {np.median(smb_fracs)*100:.0f}%")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'med_ratio': float(np.median(ratios))},
        'H2': {'pass': bool(h2_pass), 'med_r': float(med_r)},
        'H3': {'pass': bool(h3_pass), 'med_basal_frac': float(med_bf)},
        'H4': {'pass': bool(h4_pass)},
        'H5': {'pass': bool(h5_pass), 'med_r': float(med_rp)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2769: 72-Hour Total Insulin Accounting', fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: TDD distribution
        ax = axes[0, 0]
        ax.hist(tdds, bins=15, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(np.median(tdds), color='red', linewidth=2,
                   label=f'Median={np.median(tdds):.1f}U')
        ax.set_xlabel('Total Daily Dose (U)')
        ax.set_ylabel('Count')
        ax.set_title('Daily Insulin Distribution')
        ax.legend()

        # Panel 2: Stacked bar — insulin composition
        ax = axes[0, 1]
        x = np.arange(len(pids))
        basals = [patient_results[p]['med_basal_frac'] for p in pids]
        boluses = [patient_results[p]['med_bolus_frac'] for p in pids]
        smbs = [patient_results[p]['med_smb_frac'] for p in pids]
        ax.bar(x, basals, color='steelblue', alpha=0.7, label='Basal')
        ax.bar(x, boluses, bottom=basals, color='coral', alpha=0.7, label='Bolus')
        bottom2 = [b + bo for b, bo in zip(basals, boluses)]
        ax.bar(x, smbs, bottom=bottom2, color='green', alpha=0.7, label='SMB')
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Fraction')
        ax.set_title('Insulin Composition')
        ax.legend(fontsize=8)

        # Panel 3: Delivery ratio vs mean BG
        ax = axes[0, 2]
        drs = [patient_results[p]['med_delivery_ratio'] for p in pids]
        bgs = [patient_results[p]['med_mean_bg'] for p in pids]
        colors = ['green' if patient_results[p]['controller'] == 'Trio' else 'blue' for p in pids]
        ax.scatter(drs, bgs, c=colors, s=60, alpha=0.7, edgecolors='black')
        ax.set_xlabel('Delivery Ratio (vs profile)')
        ax.set_ylabel('Mean BG (mg/dL)')
        ax.set_title(f'Delivery vs Outcome (r={med_r:.2f})')

        # Panel 4: Variability (CV)
        ax = axes[1, 0]
        cvs = [patient_results[p]['cv_insulin'] for p in pids]
        ax.bar(range(len(pids)), cvs, color='orange', alpha=0.7)
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('CV of 72h Insulin')
        ax.set_title(f'Insulin Variability (med max/min={np.median(ratios):.1f}×)')

        # Panel 5: TDD vs TIR
        ax = axes[1, 1]
        tirs = [patient_results[p]['med_tir'] for p in pids]
        ax.scatter(tdds, tirs, c=colors, s=60, alpha=0.7, edgecolors='black')
        ax.set_xlabel('TDD (U)')
        ax.set_ylabel('TIR %')
        ax.set_title('Dose vs Control Quality')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2769: 72h Insulin Accounting

Hypotheses: {n_pass}/5 PASS

POPULATION (N={len(patient_results)}):
  TDD: {np.median(tdds):.1f}U (IQR {np.percentile(tdds, 25):.1f}-{np.percentile(tdds, 75):.1f})
  Delivery ratio: {np.median(del_ratios):.2f}×
  Basal: {med_bf*100:.0f}%  Bolus: {np.median([patient_results[p]['med_bolus_frac'] for p in patient_results])*100:.0f}%

VARIABILITY:
  72h max/min: {np.median(ratios):.1f}×
  CV: {np.median(cvs):.2f}

CORRELATIONS:
  Delivery ratio → BG: r={med_r:.3f}
  72h insulin → next 24h BG: r={med_rp:.3f}

SANITY CHECK:
  Over-delivery correlates with lower BG: {'YES' if med_r < 0 else 'NO'}"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/insulin-72h', exist_ok=True)
        plt.savefig('tools/visualizations/insulin-72h/exp-2769-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/insulin-72h/exp-2769-dashboard.png")
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

    with open('externals/experiments/exp-2769_insulin_72h.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2769_insulin_72h.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
