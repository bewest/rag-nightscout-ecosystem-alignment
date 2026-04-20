#!/usr/bin/env python3
"""
EXP-2756: ISF Correction Factor Diagnostic

Every patient shows ISF correction factor 0.05-0.56 (median ~0.18).
This means observed BG drop is only 5-56% of what profile ISF predicts.

Three possible explanations:
  A) Profile ISF is genuinely 2-20× too high (miscalibrated settings)
  B) Closed-loop confounding: controller reduces temp basal during corrections,
     so excess_insulin OVERESTIMATES true insulin impact
  C) Hepatic glucose production partially counteracts insulin during corrections

This experiment diagnoses WHICH explanation dominates.

Hypotheses:
  H1: Controller compensation: temp basal drops significantly during corrections
      (excess_basal should be strongly negative during correction episodes)
  H2: Correction factor correlates with excess_basal magnitude
      (more basal suspension → lower CF)
  H3: Removing basal compensation from insulin accounting raises CF toward 1.0
  H4: Bolus-only ISF (ignoring basal/SMB) gives CF closer to 1.0
  H5: CF varies by starting BG (higher BG → lower CF, suggesting EGP resistance)
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {
        'experiment': 'EXP-2756',
        'title': 'ISF Correction Factor Diagnostic',
        'hypotheses': {},
        'diagnostics': {}
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    all_episodes = []

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        glucose = pdf['glucose'].values
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        horizon = 24  # 2h

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
            excess_basal_units = np.nansum(
                (net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0 / 60.0
            )
            total_sched_basal = np.nansum(sched_basal[i:i+horizon] * 5.0 / 60.0)
            total_net_basal = np.nansum(net_basal[i:i+horizon] * 5.0 / 60.0)

            # Different insulin accounting methods
            full_insulin = total_bolus + total_smb + excess_basal_units
            bolus_only = total_bolus
            bolus_smb_only = total_bolus + total_smb
            all_insulin = total_bolus + total_smb + total_net_basal

            if full_insulin < 0.1 or bolus_only < 0.1:
                continue

            valid_future = future_glucose[~np.isnan(future_glucose)]
            if len(valid_future) < 5:
                continue
            actual_drop = glucose[i] - valid_future[-1]

            profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0

            all_episodes.append({
                'patient_id': pid,
                'start_bg': glucose[i],
                'actual_drop': actual_drop,
                'profile_isf': profile_isf_val,
                'total_bolus': total_bolus,
                'total_smb': total_smb,
                'excess_basal': excess_basal_units,
                'sched_basal': total_sched_basal,
                'net_basal': total_net_basal,
                'full_insulin': full_insulin,
                'bolus_only': bolus_only,
                'bolus_smb_only': bolus_smb_only,
                'all_insulin': all_insulin,
                # Correction factors under different accounting
                'cf_full': actual_drop / (full_insulin * profile_isf_val) if full_insulin * profile_isf_val > 0 else np.nan,
                'cf_bolus_only': actual_drop / (bolus_only * profile_isf_val) if bolus_only * profile_isf_val > 0 else np.nan,
                'cf_bolus_smb': actual_drop / (bolus_smb_only * profile_isf_val) if bolus_smb_only * profile_isf_val > 0 else np.nan,
                'cf_all_insulin': actual_drop / (all_insulin * profile_isf_val) if all_insulin * profile_isf_val > 0 else np.nan,
                # Actual ISF (drop per unit insulin)
                'actual_isf_full': actual_drop / full_insulin if full_insulin > 0 else np.nan,
                'actual_isf_bolus': actual_drop / bolus_only if bolus_only > 0 else np.nan,
            })

    df = pd.DataFrame(all_episodes)
    print(f"\nTotal correction episodes: {len(df)}")

    # ============================================================
    # DIAGNOSTIC 1: Controller compensation during corrections
    # ============================================================
    print("\n" + "=" * 70)
    print("D1: Controller Compensation During Corrections")
    print("=" * 70)

    mean_excess_basal = df['excess_basal'].mean()
    median_excess_basal = df['excess_basal'].median()
    pct_negative = (df['excess_basal'] < 0).mean() * 100
    print(f"  Mean excess basal: {mean_excess_basal:.3f} U")
    print(f"  Median excess basal: {median_excess_basal:.3f} U")
    print(f"  Negative (controller suspending): {pct_negative:.1f}%")
    print(f"  Mean scheduled basal (2h): {df['sched_basal'].mean():.2f} U")
    print(f"  Mean net basal (2h): {df['net_basal'].mean():.2f} U")

    # H1: Is excess_basal strongly negative?
    h1_pass = pct_negative > 60
    print(f"\n  H1: Controller suspends basal in >{pct_negative:.0f}% of corrections: {'✓' if h1_pass else '✗'}")

    # ============================================================
    # DIAGNOSTIC 2: CF vs excess_basal correlation
    # ============================================================
    print("\n" + "=" * 70)
    print("D2: CF vs Basal Compensation Correlation")
    print("=" * 70)

    valid = df.dropna(subset=['cf_full', 'excess_basal'])
    from scipy import stats
    r, p = stats.pearsonr(valid['excess_basal'], valid['cf_full'])
    print(f"  Correlation(excess_basal, CF): r={r:.3f}, p={p:.4e}")
    h2_pass = abs(r) > 0.1 and p < 0.01
    print(f"  H2: Significant correlation: {'✓' if h2_pass else '✗'}")

    # ============================================================
    # DIAGNOSTIC 3: Different insulin accounting methods
    # ============================================================
    print("\n" + "=" * 70)
    print("D3: CF Under Different Insulin Accounting")
    print("=" * 70)

    per_patient_cfs = {}
    for pid in df['patient_id'].unique():
        pdata = df[df['patient_id'] == pid]
        per_patient_cfs[pid] = {
            'cf_full': float(pdata['cf_full'].median()),
            'cf_bolus_only': float(pdata['cf_bolus_only'].median()),
            'cf_bolus_smb': float(pdata['cf_bolus_smb'].median()),
            'cf_all_insulin': float(pdata['cf_all_insulin'].median()),
            'actual_isf_full': float(pdata['actual_isf_full'].median()),
            'actual_isf_bolus': float(pdata['actual_isf_bolus'].median()),
            'profile_isf': float(pdata['profile_isf'].median()),
            'n': len(pdata)
        }

    cf_full_median = np.median([v['cf_full'] for v in per_patient_cfs.values()])
    cf_bolus_median = np.median([v['cf_bolus_only'] for v in per_patient_cfs.values()])
    cf_bsmb_median = np.median([v['cf_bolus_smb'] for v in per_patient_cfs.values()])
    cf_all_median = np.median([v['cf_all_insulin'] for v in per_patient_cfs.values()])

    print(f"  Full excess insulin:    median CF = {cf_full_median:.3f}")
    print(f"  Bolus-only:             median CF = {cf_bolus_median:.3f}")
    print(f"  Bolus + SMB:            median CF = {cf_bsmb_median:.3f}")
    print(f"  All insulin (net basal):median CF = {cf_all_median:.3f}")

    print(f"\n  Actual ISF (drop/U, full): {np.median([v['actual_isf_full'] for v in per_patient_cfs.values()]):.1f} mg/dL/U")
    print(f"  Actual ISF (drop/U, bolus): {np.median([v['actual_isf_bolus'] for v in per_patient_cfs.values()]):.1f} mg/dL/U")
    print(f"  Profile ISF (median): {np.median([v['profile_isf'] for v in per_patient_cfs.values()]):.1f} mg/dL/U")

    # H3: Bolus-only CF closer to 1.0?
    h3_pass = abs(cf_bolus_median - 1.0) < abs(cf_full_median - 1.0)
    print(f"\n  H3: Bolus-only CF closer to 1.0: {'✓' if h3_pass else '✗'}")
    print(f"       Full: |{cf_full_median:.3f} - 1.0| = {abs(cf_full_median-1.0):.3f}")
    print(f"       Bolus: |{cf_bolus_median:.3f} - 1.0| = {abs(cf_bolus_median-1.0):.3f}")

    # H4: Bolus-only CF significantly higher?
    h4_pass = cf_bolus_median > cf_full_median * 1.1
    print(f"\n  H4: Bolus-only CF > Full CF * 1.1: {'✓' if h4_pass else '✗'}")

    # ============================================================
    # DIAGNOSTIC 4: CF vs Starting BG
    # ============================================================
    print("\n" + "=" * 70)
    print("D4: CF vs Starting BG (EGP resistance?)")
    print("=" * 70)

    valid2 = df.dropna(subset=['cf_full', 'start_bg'])
    r2, p2 = stats.pearsonr(valid2['start_bg'], valid2['cf_full'])
    print(f"  Correlation(start_bg, CF): r={r2:.3f}, p={p2:.4e}")

    # Stratify by BG range
    for bg_low, bg_high in [(180, 220), (220, 260), (260, 300), (300, 400)]:
        subset = df[(df['start_bg'] >= bg_low) & (df['start_bg'] < bg_high)]
        if len(subset) > 10:
            med_cf = subset['cf_full'].median()
            med_drop = subset['actual_drop'].median()
            med_ins = subset['full_insulin'].median()
            print(f"  BG {bg_low}-{bg_high}: CF={med_cf:.3f}, drop={med_drop:.0f} mg/dL, insulin={med_ins:.1f}U, n={len(subset)}")

    h5_pass = abs(r2) > 0.05 and p2 < 0.05
    print(f"\n  H5: CF varies with starting BG: {'✓' if h5_pass else '✗'}")

    # ============================================================
    # DIAGNOSTIC 5: The "actual drop per unit" analysis
    # ============================================================
    print("\n" + "=" * 70)
    print("D5: Actual BG Drop Per Unit of Insulin")
    print("=" * 70)

    for pid in sorted(per_patient_cfs.keys())[:10]:
        v = per_patient_cfs[pid]
        print(f"  {pid}: actual_ISF={v['actual_isf_full']:.0f} (full) "
              f"{v['actual_isf_bolus']:.0f} (bolus), profile={v['profile_isf']:.0f}, "
              f"ratio={v['actual_isf_full']/v['profile_isf']:.2f}")

    # Key insight: what's the actual BG drop per unit?
    all_actual_isf = [v['actual_isf_full'] for v in per_patient_cfs.values()]
    all_profile_isf = [v['profile_isf'] for v in per_patient_cfs.values()]
    print(f"\n  Population actual ISF: {np.median(all_actual_isf):.0f} mg/dL/U (IQR: {np.percentile(all_actual_isf, 25):.0f}-{np.percentile(all_actual_isf, 75):.0f})")
    print(f"  Population profile ISF: {np.median(all_profile_isf):.0f} mg/dL/U (IQR: {np.percentile(all_profile_isf, 25):.0f}-{np.percentile(all_profile_isf, 75):.0f})")
    print(f"  Ratio: {np.median(all_actual_isf)/np.median(all_profile_isf):.2f}")

    # ============================================================
    # DIAGNOSTIC 6: Decompose the gap
    # ============================================================
    print("\n" + "=" * 70)
    print("D6: Decomposing the ISF Gap")
    print("=" * 70)

    # For each patient, compute:
    # - Profile predicts: bolus × ISF = expected_drop_bolus_only
    # - Actual drop observed
    # - The gap: expected - actual
    # - How much of the gap is explained by:
    #   a) Controller basal compensation (excess_basal × ISF)
    #   b) SMB dosing (SMB × ISF)
    #   c) Remaining (EGP/other)
    decomp = {}
    for pid in df['patient_id'].unique():
        pdata = df[df['patient_id'] == pid]
        med_isf = pdata['profile_isf'].median()
        med_bolus = pdata['total_bolus'].median()
        med_smb = pdata['total_smb'].median()
        med_excess_b = pdata['excess_basal'].median()
        med_actual_drop = pdata['actual_drop'].median()

        expected_bolus_drop = med_bolus * med_isf
        expected_smb_drop = med_smb * med_isf
        expected_basal_drop = med_excess_b * med_isf
        expected_full_drop = (med_bolus + med_smb + med_excess_b) * med_isf

        gap_from_profile = expected_bolus_drop - med_actual_drop
        smb_contribution = expected_smb_drop
        basal_contribution = expected_basal_drop  # negative = suspension reduces expected
        remaining = gap_from_profile - smb_contribution - basal_contribution

        decomp[pid] = {
            'expected_bolus_drop': float(expected_bolus_drop),
            'expected_full_drop': float(expected_full_drop),
            'actual_drop': float(med_actual_drop),
            'gap_total': float(expected_bolus_drop - med_actual_drop),
            'gap_smb': float(smb_contribution),
            'gap_basal': float(basal_contribution),
            'gap_remaining': float(remaining),
            'profile_isf': float(med_isf),
            'median_bolus': float(med_bolus),
            'median_smb': float(med_smb),
            'median_excess_basal': float(med_excess_b)
        }

    print(f"  {'Patient':<20} {'Expected':>8} {'Actual':>8} {'Gap':>8} {'SMB':>8} {'Basal':>8} {'Remain':>8}")
    for pid in sorted(decomp.keys()):
        d = decomp[pid]
        print(f"  {pid:<20} {d['expected_bolus_drop']:>8.0f} {d['actual_drop']:>8.0f} "
              f"{d['gap_total']:>8.0f} {d['gap_smb']:>8.0f} {d['gap_basal']:>8.0f} {d['gap_remaining']:>8.0f}")

    # Aggregate
    med_expected = np.median([d['expected_bolus_drop'] for d in decomp.values()])
    med_actual = np.median([d['actual_drop'] for d in decomp.values()])
    med_gap_total = np.median([d['gap_total'] for d in decomp.values()])
    med_gap_smb = np.median([d['gap_smb'] for d in decomp.values()])
    med_gap_basal = np.median([d['gap_basal'] for d in decomp.values()])
    med_gap_remaining = np.median([d['gap_remaining'] for d in decomp.values()])

    print(f"\n  Population medians:")
    print(f"    Expected drop (bolus × ISF): {med_expected:.0f} mg/dL")
    print(f"    Actual drop observed:        {med_actual:.0f} mg/dL")
    print(f"    Total gap:                   {med_gap_total:.0f} mg/dL")
    print(f"    Explained by SMB:            {med_gap_smb:.0f} mg/dL")
    print(f"    Explained by basal suspn:    {med_gap_basal:.0f} mg/dL")
    print(f"    REMAINING (EGP/other):       {med_gap_remaining:.0f} mg/dL")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    for label, passed in [('H1', h1_pass), ('H2', h2_pass), ('H3', h3_pass), ('H4', h4_pass), ('H5', h5_pass)]:
        print(f"  {'✓' if passed else '✗'} {label}")
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {
        'H1_basal_suspension': {'pass': bool(h1_pass), 'pct_negative': float(pct_negative)},
        'H2_cf_basal_corr': {'pass': bool(h2_pass), 'r': float(r), 'p': float(p)},
        'H3_bolus_cf_closer': {'pass': bool(h3_pass), 'cf_full': float(cf_full_median), 'cf_bolus': float(cf_bolus_median)},
        'H4_bolus_cf_higher': {'pass': bool(h4_pass)},
        'H5_bg_varies_cf': {'pass': bool(h5_pass), 'r': float(r2), 'p': float(p2)},
        'total_pass': n_pass
    }
    results['diagnostics'] = {
        'per_patient_cfs': per_patient_cfs,
        'decomposition': decomp,
        'population_actual_isf': float(np.median(all_actual_isf)),
        'population_profile_isf': float(np.median(all_profile_isf)),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2756: ISF Correction Factor Diagnostic', fontsize=16, fontweight='bold')

        # Panel 1: CF by accounting method
        ax = axes[0, 0]
        methods = ['Full\n(excess)', 'Bolus\nonly', 'Bolus\n+SMB', 'All\n(net basal)']
        medians = [cf_full_median, cf_bolus_median, cf_bsmb_median, cf_all_median]
        colors = ['#e74c3c', '#2ecc71', '#3498db', '#f39c12']
        ax.bar(methods, medians, color=colors, alpha=0.7, edgecolor='black')
        ax.axhline(1.0, color='black', linestyle='--', alpha=0.5, label='Profile correct')
        ax.set_ylabel('Median CF')
        ax.set_title('CF by Insulin Accounting Method')
        ax.legend()

        # Panel 2: Actual vs Profile ISF scatter
        ax = axes[0, 1]
        actual_isfs = [per_patient_cfs[p]['actual_isf_full'] for p in per_patient_cfs]
        profile_isfs = [per_patient_cfs[p]['profile_isf'] for p in per_patient_cfs]
        ax.scatter(profile_isfs, actual_isfs, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(profile_isfs), max(actual_isfs)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='1:1')
        ax.set_xlabel('Profile ISF (mg/dL/U)')
        ax.set_ylabel('Actual ISF (mg/dL/U)')
        ax.set_title('Profile vs Actual ISF')
        ax.legend()

        # Panel 3: Basal suspension histogram
        ax = axes[0, 2]
        ax.hist(df['excess_basal'], bins=50, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(0, color='red', linestyle='--', label='No compensation')
        ax.axvline(df['excess_basal'].median(), color='green', linestyle='-',
                   label=f'Median: {df["excess_basal"].median():.2f}U')
        ax.set_xlabel('Excess Basal (U, 2h window)')
        ax.set_ylabel('Count')
        ax.set_title('Controller Basal Compensation')
        ax.legend(fontsize=8)

        # Panel 4: Gap decomposition
        ax = axes[1, 0]
        pids_sorted = sorted(decomp.keys())
        x = range(len(pids_sorted))
        actual_drops = [decomp[p]['actual_drop'] for p in pids_sorted]
        gap_smbs = [decomp[p]['gap_smb'] for p in pids_sorted]
        gap_basals = [decomp[p]['gap_basal'] for p in pids_sorted]
        gap_remains = [decomp[p]['gap_remaining'] for p in pids_sorted]
        ax.bar(x, actual_drops, label='Actual drop', color='#2ecc71', alpha=0.7)
        ax.bar(x, gap_smbs, bottom=actual_drops, label='SMB effect', color='#3498db', alpha=0.7)
        bottom2 = [a + s for a, s in zip(actual_drops, gap_smbs)]
        ax.bar(x, gap_basals, bottom=bottom2, label='Basal comp.', color='#f39c12', alpha=0.7)
        bottom3 = [b + ba for b, ba in zip(bottom2, gap_basals)]
        ax.bar(x, gap_remains, bottom=bottom3, label='EGP/other', color='#e74c3c', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids_sorted], rotation=90, fontsize=6)
        ax.set_ylabel('mg/dL')
        ax.set_title('Expected vs Actual Drop Decomposition')
        ax.legend(fontsize=7)

        # Panel 5: CF vs starting BG
        ax = axes[1, 1]
        valid_plot = df.dropna(subset=['cf_full', 'start_bg'])
        valid_plot = valid_plot[(valid_plot['cf_full'] > 0) & (valid_plot['cf_full'] < 3)]
        ax.hexbin(valid_plot['start_bg'], valid_plot['cf_full'], gridsize=30, cmap='YlOrRd', mincnt=1)
        ax.axhline(1.0, color='black', linestyle='--', alpha=0.5)
        ax.set_xlabel('Starting BG (mg/dL)')
        ax.set_ylabel('Correction Factor')
        ax.set_title(f'CF vs Starting BG (r={r2:.3f})')
        plt.colorbar(ax.collections[0], ax=ax, label='Count')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2756: ISF CF Diagnostic

Population ISF:
  Profile: {np.median(all_profile_isf):.0f} mg/dL/U
  Actual:  {np.median(all_actual_isf):.0f} mg/dL/U
  Ratio:   {np.median(all_actual_isf)/np.median(all_profile_isf):.2f}

CF by method:
  Full excess:  {cf_full_median:.3f}
  Bolus only:   {cf_bolus_median:.3f}
  Bolus+SMB:    {cf_bsmb_median:.3f}
  All insulin:  {cf_all_median:.3f}

Gap decomposition (medians):
  Expected: {med_expected:.0f} mg/dL
  Actual:   {med_actual:.0f} mg/dL
  SMB:      {med_gap_smb:.0f} mg/dL
  Basal:    {med_gap_basal:.0f} mg/dL
  Remaining:{med_gap_remaining:.0f} mg/dL

Hypotheses: {n_pass}/5 PASS"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/isf-diagnostic', exist_ok=True)
        plt.savefig('tools/visualizations/isf-diagnostic/exp-2756-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/isf-diagnostic/exp-2756-dashboard.png")
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

    with open('externals/experiments/exp-2756_isf_diagnostic.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2756_isf_diagnostic.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
