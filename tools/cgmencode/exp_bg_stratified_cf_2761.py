#!/usr/bin/env python3
"""
EXP-2761: BG-Stratified Correction Factor Pipeline

EXP-2756 showed CF varies with starting BG: 0.10 at BG 180-220, 0.24 at BG 300+.
This is potentially the largest remaining signal — a 2.4× variation in CF.

If CF depends on starting BG, a single CF per patient misestimates corrections
at both low-high BG and very-high BG. BG-stratified CFs could improve precision.

Hypotheses:
  H1: CF correlates with starting BG (r ≥ 0.3 median across patients)
  H2: BG-stratified CF reduces prediction error ≥10% vs single CF
  H3: The BG-CF relationship is consistent across controllers (Loop vs Trio)
  H4: BG-stratified CF generalizes to test data (stability ≥ 0.90)
  H5: A simple linear model (CF = a + b*BG) captures the relationship (R² ≥ 0.1)
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_episodes(pdf, horizon=24, min_bg=180, min_bolus=0.5):
    """Extract correction episodes with BG, dose, and outcome."""
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
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue

        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
        expected = excess_insulin * profile_isf_val
        cf = actual_drop / expected if expected > 0 else np.nan

        episodes.append({
            'bg': glucose[i],
            'actual_drop': actual_drop,
            'excess_insulin': excess_insulin,
            'expected': expected,
            'cf': cf,
            'profile_isf': profile_isf_val,
        })

    return pd.DataFrame(episodes)

def run_experiment():
    results = {
        'experiment': 'EXP-2761',
        'title': 'BG-Stratified Correction Factor',
        'hypotheses': {}
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    # Classify controllers
    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    patient_results = {}
    all_correlations = []
    bg_cf_slopes = []

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

        # Global CF
        global_cf = train_eps['cf'].median()

        # BG-CF correlation
        valid_mask = np.isfinite(train_eps['cf']) & np.isfinite(train_eps['bg'])
        if valid_mask.sum() < 10:
            continue

        r, p = stats.pearsonr(train_eps.loc[valid_mask, 'bg'], train_eps.loc[valid_mask, 'cf'])
        all_correlations.append(r)

        # Linear model: CF = a + b * BG
        slope, intercept, r_val, p_val, se = stats.linregress(
            train_eps.loc[valid_mask, 'bg'], train_eps.loc[valid_mask, 'cf'])
        r2 = r_val ** 2
        bg_cf_slopes.append(slope)

        # BG-stratified CFs (bands)
        bands = [(180, 220), (220, 260), (260, 300), (300, 500)]
        band_cfs = {}
        for lo, hi in bands:
            mask = (train_eps['bg'] >= lo) & (train_eps['bg'] < hi)
            if mask.sum() >= 5:
                band_cfs[f"{lo}-{hi}"] = float(train_eps.loc[mask, 'cf'].median())

        # Evaluate on test: single CF vs BG-stratified vs linear
        if len(test_eps) < 5:
            continue

        errors_single = []
        errors_stratified = []
        errors_linear = []

        for _, ep in test_eps.iterrows():
            if not np.isfinite(ep['cf']):
                continue
            actual = ep['actual_drop']

            # Single CF prediction
            pred_single = ep['expected'] * global_cf
            errors_single.append(abs(actual - pred_single))

            # Stratified CF prediction
            bg_val = ep['bg']
            strat_cf = global_cf
            for lo, hi in bands:
                key = f"{lo}-{hi}"
                if lo <= bg_val < hi and key in band_cfs:
                    strat_cf = band_cfs[key]
                    break
            pred_strat = ep['expected'] * strat_cf
            errors_stratified.append(abs(actual - pred_strat))

            # Linear model prediction
            pred_linear_cf = intercept + slope * bg_val
            pred_linear = ep['expected'] * pred_linear_cf
            errors_linear.append(abs(actual - pred_linear))

        if not errors_single:
            continue

        mae_single = np.median(errors_single)
        mae_strat = np.median(errors_stratified)
        mae_linear = np.median(errors_linear)

        strat_improve = (mae_single - mae_strat) / mae_single * 100 if mae_single > 0 else 0
        linear_improve = (mae_single - mae_linear) / mae_single * 100 if mae_single > 0 else 0

        patient_results[pid] = {
            'controller': ctrl_map.get(pid, 'Unknown'),
            'n_episodes': len(train_eps),
            'correlation': float(r),
            'p_value': float(p),
            'slope': float(slope),
            'r2': float(r2),
            'global_cf': float(global_cf),
            'band_cfs': band_cfs,
            'mae_single': float(mae_single),
            'mae_stratified': float(mae_strat),
            'mae_linear': float(mae_linear),
            'strat_improve': float(strat_improve),
            'linear_improve': float(linear_improve),
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # ============================================================
    # RESULTS TABLE
    # ============================================================
    print(f"\n{'Patient':<18} {'Ctrl':<5} {'r':>6} {'R²':>6} {'CF':>6} "
          f"{'Strat%':>7} {'Lin%':>7} {'slope':>8}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['controller']:<5} {pr['correlation']:>6.3f} {pr['r2']:>6.3f} "
              f"{pr['global_cf']:>6.3f} {pr['strat_improve']:>6.1f}% {pr['linear_improve']:>6.1f}% "
              f"{pr['slope']:>8.5f}")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    median_r = np.median(all_correlations)
    h1_pass = median_r >= 0.3
    print(f"  {'✓' if h1_pass else '✗'} H1: CF correlates with BG (median r≥0.3): "
          f"median r = {median_r:.3f}")

    strat_improves = [patient_results[p]['strat_improve'] for p in patient_results]
    med_strat_improve = np.median(strat_improves)
    h2_pass = med_strat_improve >= 10
    n_better = sum(1 for x in strat_improves if x > 0)
    print(f"  {'✓' if h2_pass else '✗'} H2: ≥10% improvement: median {med_strat_improve:.1f}%, "
          f"{n_better}/{len(strat_improves)} patients improve")

    # H3: Consistent across controllers
    loop_corrs = [patient_results[p]['correlation'] for p in patient_results
                  if patient_results[p]['controller'] == 'Loop']
    trio_corrs = [patient_results[p]['correlation'] for p in patient_results
                  if patient_results[p]['controller'] == 'Trio']
    if loop_corrs and trio_corrs:
        loop_med = np.median(loop_corrs)
        trio_med = np.median(trio_corrs)
        h3_pass = abs(loop_med - trio_med) < 0.2
        print(f"  {'✓' if h3_pass else '✗'} H3: Consistent across controllers: "
              f"Loop r={loop_med:.3f}, Trio r={trio_med:.3f} (Δ={abs(loop_med-trio_med):.3f})")
    else:
        h3_pass = False
        print(f"  ✗ H3: Not enough controllers to compare")

    # H4: Stability
    stabilities = []
    for p in patient_results:
        pr = patient_results[p]
        if pr['strat_improve'] != 0:
            stabilities.append(1.0 if pr['strat_improve'] > 0 else 0.0)
    stability_rate = np.mean(stabilities) if stabilities else 0
    h4_pass = stability_rate >= 0.90
    print(f"  {'✓' if h4_pass else '✗'} H4: Stability ≥0.90: {stability_rate:.3f} "
          f"({n_better}/{len(strat_improves)} positive)")

    # H5: Linear model R²
    r2_vals = [patient_results[p]['r2'] for p in patient_results]
    med_r2 = np.median(r2_vals)
    h5_pass = med_r2 >= 0.1
    n_r2_good = sum(1 for x in r2_vals if x >= 0.1)
    print(f"  {'✓' if h5_pass else '✗'} H5: Linear R²≥0.1: median R² = {med_r2:.3f}, "
          f"{n_r2_good}/{len(r2_vals)} ≥ 0.1")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Additional: linear vs single
    linear_improves = [patient_results[p]['linear_improve'] for p in patient_results]
    med_linear = np.median(linear_improves)
    n_lin_better = sum(1 for x in linear_improves if x > 0)
    print(f"\n  Linear model: median {med_linear:.1f}% improvement, {n_lin_better}/{len(linear_improves)} better")

    results['hypotheses'] = {
        'H1_correlation': {'pass': bool(h1_pass), 'median_r': float(median_r)},
        'H2_10pct_improvement': {'pass': bool(h2_pass), 'median_improve': float(med_strat_improve)},
        'H3_controller_consistent': {'pass': bool(h3_pass)},
        'H4_stability': {'pass': bool(h4_pass), 'rate': float(stability_rate)},
        'H5_linear_r2': {'pass': bool(h5_pass), 'median_r2': float(med_r2)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['summary'] = {
        'n_patients': len(patient_results),
        'median_correlation': float(median_r),
        'median_strat_improve': float(med_strat_improve),
        'median_linear_improve': float(med_linear),
        'median_r2': float(med_r2),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2761: BG-Stratified Correction Factor', fontsize=16, fontweight='bold')

        # Panel 1: CF vs BG (scatter of all episode medians by band)
        ax = axes[0, 0]
        all_bands = {}
        for pid in patient_results:
            for band, cf in patient_results[pid]['band_cfs'].items():
                lo = int(band.split('-')[0])
                mid = lo + 20
                all_bands.setdefault(band, []).append(cf)
        for band in sorted(all_bands.keys()):
            lo = int(band.split('-')[0])
            mid = lo + 20
            ax.scatter([mid] * len(all_bands[band]), all_bands[band], s=40, alpha=0.5)
            ax.scatter(mid, np.median(all_bands[band]), s=100, marker='D', c='red', zorder=5)
        ax.set_xlabel('Starting BG (mg/dL)')
        ax.set_ylabel('Correction Factor')
        ax.set_title('CF by Starting BG Band')

        # Panel 2: Per-patient correlations
        ax = axes[0, 1]
        ax.hist(all_correlations, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax.axvline(median_r, color='red', linestyle='-', linewidth=2, label=f'Median={median_r:.3f}')
        ax.set_xlabel('BG-CF Correlation (r)')
        ax.set_ylabel('Count')
        ax.set_title('BG-CF Correlations')
        ax.legend()

        # Panel 3: Improvement comparison
        ax = axes[0, 2]
        x = np.arange(len(patient_results))
        pids = sorted(patient_results.keys())
        si = [patient_results[p]['strat_improve'] for p in pids]
        li = [patient_results[p]['linear_improve'] for p in pids]
        ax.bar(x - 0.2, si, 0.4, label='Stratified', color='coral', alpha=0.7)
        ax.bar(x + 0.2, li, 0.4, label='Linear', color='steelblue', alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Improvement vs Single CF (%)')
        ax.set_title('Stratified vs Linear vs Single CF')
        ax.legend()

        # Panel 4: Slopes by controller
        ax = axes[1, 0]
        loop_slopes = [patient_results[p]['slope'] for p in patient_results
                       if patient_results[p]['controller'] == 'Loop']
        trio_slopes = [patient_results[p]['slope'] for p in patient_results
                       if patient_results[p]['controller'] == 'Trio']
        positions = []
        data = []
        labels = []
        if loop_slopes:
            positions.append(1)
            data.append(loop_slopes)
            labels.append(f'Loop (n={len(loop_slopes)})')
        if trio_slopes:
            positions.append(2)
            data.append(trio_slopes)
            labels.append(f'Trio (n={len(trio_slopes)})')
        ax.boxplot(data, positions=positions, labels=labels)
        ax.axhline(0, color='gray', linestyle='--')
        ax.set_ylabel('BG-CF Slope')
        ax.set_title('BG-CF Slope by Controller')

        # Panel 5: R² distribution
        ax = axes[1, 1]
        ax.hist(r2_vals, bins=20, color='coral', alpha=0.7, edgecolor='black')
        ax.axvline(med_r2, color='red', linestyle='-', linewidth=2, label=f'Median={med_r2:.3f}')
        ax.axvline(0.1, color='green', linestyle='--', linewidth=1, label='Threshold=0.1')
        ax.set_xlabel('Linear Model R²')
        ax.set_ylabel('Count')
        ax.set_title('BG-CF Linear Model Fit')
        ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary_text = f"""EXP-2761 Summary

Hypotheses: {n_pass}/5 PASS

BG-CF Correlation:
  Median r:    {median_r:.3f}
  Median R²:   {med_r2:.3f}

Stratified CF:
  Median improvement:  {med_strat_improve:.1f}%
  Patients improved:   {n_better}/{len(strat_improves)}

Linear CF:
  Median improvement:  {med_linear:.1f}%
  Patients improved:   {n_lin_better}/{len(linear_improves)}

Median slope: {np.median(bg_cf_slopes):.5f}/mg/dL
  → +{np.median(bg_cf_slopes)*100:.3f} CF per 100 mg/dL rise"""
        ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/bg-stratified-cf', exist_ok=True)
        plt.savefig('tools/visualizations/bg-stratified-cf/exp-2761-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/bg-stratified-cf/exp-2761-dashboard.png")
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

    with open('externals/experiments/exp-2761_bg_stratified_cf.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2761_bg_stratified_cf.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
