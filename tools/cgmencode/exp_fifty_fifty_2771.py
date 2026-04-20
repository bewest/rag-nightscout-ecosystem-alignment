#!/usr/bin/env python3
"""
EXP-2771: 50/50 Rule Validation & Bilateral Insulin Decomposition

User insight: "A guiding rule of thumb is that 50% of total daily dose is for
'basal' needs, and 50% are for food/corrections."

This decomposes insulin into physiological channels:
  SUPPLY-SIDE (EGP coverage = "basal need"):
    - scheduled_basal_rate = clinician's estimate of EGP counterbalance
    - Should be ~50% of TDD

  DEMAND-SIDE (food + corrections):
    - User bolus = meal + correction doses
    - Controller SMB = automated micro-boluses
    - Excess basal = temp basal above schedule (controller adds demand)

  CONTROLLER REDISTRIBUTION:
    - Basal suspension = controller removes scheduled basal
    - Net effect: scheduled basal is redistributed to SMB channel

Sanity checks:
  1. Scheduled basal ≈ 50% of TDD?
  2. After subtracting EGP balance, remaining ≈ 50%?
  3. Patients where 50/50 holds → better outcomes (TIR)?
  4. 50/50 deviation correlates with settings accuracy?

Hypotheses:
  H1: Scheduled basal is 35-65% of TDD for ≥60% of patients
  H2: Patients closer to 50/50 have higher TIR (r > 0.2)
  H3: Controller redistribution (SMB replacing suspended basal) ≥20% of TDD
  H4: Loop patients are closer to 50/50 than Trio (lower redistribution)
  H5: 50/50 deviation correlates with ISF CF (settings accuracy, |r| > 0.2)
"""

import json, sys, os, traceback
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {'experiment': 'EXP-2771', 'title': '50/50 Rule Validation'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    patient_results = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n_days = len(pdf) / 288

        # Insulin channels (per day)
        bolus = pdf['bolus'].fillna(0)
        smb = pdf['bolus_smb'].fillna(0) if 'bolus_smb' in pdf.columns else pd.Series(np.zeros(len(pdf)))
        net_basal = pdf['net_basal'].fillna(0)
        sched_basal = pdf['scheduled_basal_rate'].fillna(0)
        glucose = pdf['glucose']

        # Skip patients with insufficient data
        bolus_per_day = bolus.sum() / n_days
        smb_per_day = smb.sum() / n_days
        sched_basal_per_day = (sched_basal * 5/60).sum() / n_days  # Convert rate to amount
        actual_basal_per_day = (net_basal.clip(lower=0) * 5/60).sum() / n_days

        if bolus_per_day + smb_per_day < 1.0 and sched_basal_per_day < 1.0:
            continue  # No meaningful insulin data

        # Controller type
        has_smb = (smb > 0).any()
        ctrl = 'Trio' if has_smb else 'Loop'

        # ==============================================
        # PHYSIOLOGICAL DECOMPOSITION
        # ==============================================

        # TDD = actual delivery = actual_basal + bolus + SMB
        tdd = actual_basal_per_day + bolus_per_day + smb_per_day
        if tdd < 3:
            continue  # Insufficient

        # Supply-side: scheduled basal = EGP estimate
        egp_estimate = sched_basal_per_day

        # Demand-side: everything else
        demand_total = bolus_per_day + smb_per_day

        # 50/50 check: scheduled basal as fraction of total need
        # Total need = scheduled_basal + bolus + SMB (what the clinician intended + what patient/controller added)
        total_intended = egp_estimate + demand_total
        basal_fraction = egp_estimate / total_intended if total_intended > 0 else 0

        # Controller redistribution: how much basal was shifted to SMB
        basal_suspension_per_day = ((sched_basal - net_basal.clip(lower=0)) * 5/60).clip(lower=0).sum() / n_days
        redistribution_pct = basal_suspension_per_day / tdd if tdd > 0 else 0

        # Outcomes
        valid_g = glucose.dropna()
        mean_bg = valid_g.mean() if len(valid_g) > 100 else np.nan
        tir = ((valid_g >= 70) & (valid_g <= 180)).mean() * 100 if len(valid_g) > 100 else np.nan
        hypo = (valid_g < 70).mean() * 100 if len(valid_g) > 100 else np.nan

        # 50/50 deviation: how far from ideal 50%
        deviation_from_50 = abs(basal_fraction - 0.5)

        # ISF CF from our pipeline (quick computation)
        isf = pdf['scheduled_isf'].fillna(50).values
        cf_list = []
        for i in range(len(pdf) - 24):
            if np.isnan(glucose.iloc[i]) or glucose.iloc[i] < 180 or bolus.iloc[i] < 0.5:
                continue
            future = glucose.iloc[i:i+25].dropna()
            if len(future) < 3:
                continue
            actual_drop = glucose.iloc[i] - future.iloc[-1]
            excess = bolus.iloc[i] + smb.iloc[i:i+24].sum()
            expected = excess * isf[i]
            if expected > 0:
                cf_list.append(actual_drop / expected)
        med_cf = np.median(cf_list) if cf_list else np.nan

        patient_results[pid] = {
            'controller': ctrl,
            'n_days': float(n_days),
            'tdd': float(tdd),
            'egp_estimate': float(egp_estimate),
            'demand_total': float(demand_total),
            'bolus_per_day': float(bolus_per_day),
            'smb_per_day': float(smb_per_day),
            'actual_basal_per_day': float(actual_basal_per_day),
            'sched_basal_per_day': float(sched_basal_per_day),
            'basal_fraction': float(basal_fraction),
            'deviation_from_50': float(deviation_from_50),
            'redistribution_pct': float(redistribution_pct),
            'mean_bg': float(mean_bg) if not np.isnan(mean_bg) else None,
            'tir': float(tir) if not np.isnan(tir) else None,
            'hypo': float(hypo) if not np.isnan(hypo) else None,
            'med_cf': float(med_cf) if not np.isnan(med_cf) else None,
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # Summary table
    print(f"\n  {'Patient':<18} {'Ctrl':<5} {'TDD':>5} {'EGP':>5} {'Demand':>6} "
          f"{'Bas%':>5} {'Redist':>6} {'TIR':>4} {'CF':>5}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        cf_str = f"{pr['med_cf']:.2f}" if pr['med_cf'] is not None else "  N/A"
        tir_str = f"{pr['tir']:.0f}" if pr['tir'] is not None else " N/A"
        print(f"  {pid:<18} {pr['controller']:<5} {pr['tdd']:>5.1f} "
              f"{pr['egp_estimate']:>5.1f} {pr['demand_total']:>6.1f} "
              f"{pr['basal_fraction']*100:>4.0f}% {pr['redistribution_pct']*100:>5.0f}% "
              f"{tir_str:>4} {cf_str:>5}")

    # ==============================================
    # HYPOTHESES
    # ==============================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    # H1: 35-65% for ≥60%
    in_range = sum(1 for p in patient_results
                   if 0.35 <= patient_results[p]['basal_fraction'] <= 0.65)
    h1_frac = in_range / len(patient_results)
    h1_pass = h1_frac >= 0.60
    print(f"  {'✓' if h1_pass else '✗'} H1: Basal 35-65%: {in_range}/{len(patient_results)} "
          f"({h1_frac*100:.0f}%)")

    # H2: Closer to 50/50 → higher TIR
    devs = [patient_results[p]['deviation_from_50'] for p in patient_results
            if patient_results[p]['tir'] is not None]
    tirs = [patient_results[p]['tir'] for p in patient_results
            if patient_results[p]['tir'] is not None]
    if len(devs) >= 5:
        r_dev_tir, p_dev_tir = stats.pearsonr(devs, tirs)
        h2_pass = r_dev_tir < -0.2  # More deviation → less TIR
        print(f"  {'✓' if h2_pass else '✗'} H2: 50/50 deviation vs TIR: r={r_dev_tir:.3f} "
              f"(p={p_dev_tir:.3f})")
    else:
        h2_pass = False
        print(f"  ✗ H2: Insufficient data")

    # H3: Redistribution ≥20%
    redists = [patient_results[p]['redistribution_pct'] for p in patient_results]
    med_redist = np.median(redists)
    h3_pass = med_redist >= 0.20
    print(f"  {'✓' if h3_pass else '✗'} H3: Controller redistribution ≥20%: "
          f"median {med_redist*100:.0f}%")

    # H4: Loop closer to 50/50
    loop_devs = [patient_results[p]['deviation_from_50'] for p in patient_results
                 if patient_results[p]['controller'] == 'Loop']
    trio_devs = [patient_results[p]['deviation_from_50'] for p in patient_results
                 if patient_results[p]['controller'] == 'Trio']
    if len(loop_devs) >= 2 and len(trio_devs) >= 2:
        u, p_val = stats.mannwhitneyu(loop_devs, trio_devs, alternative='less')
        h4_pass = np.median(loop_devs) < np.median(trio_devs)
        print(f"  {'✓' if h4_pass else '✗'} H4: Loop closer to 50/50: "
              f"Loop dev={np.median(loop_devs)*100:.0f}% "
              f"Trio dev={np.median(trio_devs)*100:.0f}% (p={p_val:.3f})")
    else:
        h4_pass = False
        print(f"  ✗ H4: Insufficient data")

    # H5: 50/50 deviation correlates with CF
    devs_cf = [(patient_results[p]['deviation_from_50'], patient_results[p]['med_cf'])
               for p in patient_results if patient_results[p]['med_cf'] is not None]
    if len(devs_cf) >= 5:
        d, c = zip(*devs_cf)
        r_dev_cf, p_dev_cf = stats.pearsonr(d, c)
        h5_pass = abs(r_dev_cf) > 0.2
        print(f"  {'✓' if h5_pass else '✗'} H5: 50/50 dev vs CF: |r|={abs(r_dev_cf):.3f} "
              f"(p={p_dev_cf:.3f})")
    else:
        h5_pass = False
        print(f"  ✗ H5: Insufficient data")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Population summary
    basal_fracs = [patient_results[p]['basal_fraction'] for p in patient_results]
    print(f"\n  POPULATION SUMMARY:")
    print(f"    Basal fraction: median {np.median(basal_fracs)*100:.0f}% "
          f"(IQR {np.percentile(basal_fracs, 25)*100:.0f}-{np.percentile(basal_fracs, 75)*100:.0f}%)")
    print(f"    Patients at 35-65%: {in_range}/{len(patient_results)}")
    print(f"    Patients at 40-60%: {sum(1 for p in patient_results if 0.40 <= patient_results[p]['basal_fraction'] <= 0.60)}/{len(patient_results)}")
    print(f"    Redistribution: median {med_redist*100:.0f}%")
    tdds = [patient_results[p]['tdd'] for p in patient_results]
    print(f"    TDD: median {np.median(tdds):.1f}U")

    # Implication for settings
    print(f"\n  SETTINGS IMPLICATIONS:")
    too_low = sum(1 for p in patient_results if patient_results[p]['basal_fraction'] < 0.35)
    too_high = sum(1 for p in patient_results if patient_results[p]['basal_fraction'] > 0.65)
    print(f"    Basal too low (<35%): {too_low} patients — may need basal increase")
    print(f"    Basal too high (>65%): {too_high} patients — may need basal decrease")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'in_range': in_range, 'fraction': float(h1_frac)},
        'H2': {'pass': bool(h2_pass), 'r': float(r_dev_tir) if len(devs) >= 5 else None},
        'H3': {'pass': bool(h3_pass), 'med_redistribution': float(med_redist)},
        'H4': {'pass': bool(h4_pass)},
        'H5': {'pass': bool(h5_pass)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2771: 50/50 Rule Validation & Bilateral Decomposition',
                     fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: Basal fraction distribution with 50% line
        ax = axes[0, 0]
        bfs = [patient_results[p]['basal_fraction'] * 100 for p in pids]
        colors = ['green' if 35 <= bf <= 65 else 'red' for bf in bfs]
        ax.bar(range(len(pids)), bfs, color=colors, alpha=0.7)
        ax.axhline(50, color='blue', linewidth=2, linestyle='--', label='50% target')
        ax.axhspan(35, 65, alpha=0.1, color='green', label='35-65% range')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Scheduled Basal % of TDD')
        ax.set_title(f'50/50 Rule Check ({in_range}/{len(patient_results)} pass)')
        ax.legend(fontsize=8)

        # Panel 2: Stacked bar — demand decomposition
        ax = axes[0, 1]
        egps = [patient_results[p]['egp_estimate'] for p in pids]
        bols = [patient_results[p]['bolus_per_day'] for p in pids]
        smbs = [patient_results[p]['smb_per_day'] for p in pids]
        ax.bar(range(len(pids)), egps, color='green', alpha=0.7, label='Sched Basal (EGP)')
        ax.bar(range(len(pids)), bols, bottom=egps, color='coral', alpha=0.7, label='Bolus')
        bottoms = [e + b for e, b in zip(egps, bols)]
        ax.bar(range(len(pids)), smbs, bottom=bottoms, color='steelblue', alpha=0.7, label='SMB')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Units/day')
        ax.set_title('Insulin Channel Decomposition')
        ax.legend(fontsize=8)

        # Panel 3: 50/50 deviation vs TIR
        ax = axes[0, 2]
        for pid in pids:
            pr = patient_results[pid]
            if pr['tir'] is not None:
                c = 'green' if pr['controller'] == 'Trio' else 'blue'
                ax.scatter(pr['deviation_from_50'] * 100, pr['tir'],
                          s=60, alpha=0.7, c=c, edgecolors='black')
        ax.set_xlabel('|50/50 Deviation| (%)')
        ax.set_ylabel('TIR %')
        if len(devs) >= 5:
            ax.set_title(f'50/50 Deviation vs Outcomes (r={r_dev_tir:.2f})')
        else:
            ax.set_title('50/50 Deviation vs Outcomes')

        # Panel 4: Redistribution
        ax = axes[1, 0]
        reds = [patient_results[p]['redistribution_pct'] * 100 for p in pids]
        c = ['green' if patient_results[p]['controller'] == 'Trio' else 'blue' for p in pids]
        ax.bar(range(len(pids)), reds, color=c, alpha=0.7)
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Redistribution %')
        ax.set_title(f'Controller Redistribution (med={med_redist*100:.0f}%)')

        # Panel 5: Basal fraction vs CF
        ax = axes[1, 1]
        for pid in pids:
            pr = patient_results[pid]
            if pr['med_cf'] is not None:
                c = 'green' if pr['controller'] == 'Trio' else 'blue'
                ax.scatter(pr['basal_fraction'] * 100, pr['med_cf'],
                          s=60, alpha=0.7, c=c, edgecolors='black')
        ax.axvline(50, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlabel('Basal Fraction %')
        ax.set_ylabel('Correction Factor')
        ax.set_title('Basal Profile vs ISF Accuracy')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2771: 50/50 Rule Validation

Hypotheses: {n_pass}/5 PASS

POPULATION (N={len(patient_results)}):
  Basal fraction: {np.median(basal_fracs)*100:.0f}% (IQR {np.percentile(basal_fracs, 25)*100:.0f}-{np.percentile(basal_fracs, 75)*100:.0f}%)
  TDD: {np.median(tdds):.1f}U
  Redistribution: {med_redist*100:.0f}%

50/50 COMPLIANCE:
  35-65%: {in_range}/{len(patient_results)} patients
  Basal too low (<35%): {too_low} patients
  Basal too high (>65%): {too_high} patients

SETTINGS INSIGHT:
  Patients with basal <35% likely need
  basal rate increase — controller is
  compensating with SMBs/temp basals.

  Green = Trio, Blue = Loop"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/fifty-fifty', exist_ok=True)
        plt.savefig('tools/visualizations/fifty-fifty/exp-2771-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/fifty-fifty/exp-2771-dashboard.png")
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

    with open('externals/experiments/exp-2771_fifty_fifty.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2771_fifty_fifty.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
