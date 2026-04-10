#!/usr/bin/env python3
"""
IOB-Dependent Validation Experiment
====================================

Purpose: Verify that the oref0/Trio IOB inclusion fix materially changes
analysis that depends on the grid IOB column. Compares:
  - "Full IOB" (parquet terrarium, Loop+oref0/Trio)
  - "Loop-only IOB" (simulated: zero out IOB where controller != 'loop')

This is the experiment that SHOULD show differences for patient b,
confirming the fix matters for IOB-dependent downstream analysis.

Analyses:
  1. IOB as predictor of 1-hour glucose change (regression R²)
  2. IOB-stratified glucose outcomes (high/mid/low IOB → mean Δglucose)
  3. Controller suspend/active pattern detection
  4. IOB-glucose correlation by time of day (circadian IOB signal)
"""

import sys, os, json, warnings
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TERRARIUM = os.environ.get('NS_PARQUET', str(_REPO_ROOT / 'externals' / 'ns-parquet' / 'training'))
OUTPUT_DIR = str(_REPO_ROOT / 'externals' / 'experiments')


def load_grid():
    """Load the full parquet grid."""
    return pd.read_parquet(os.path.join(TERRARIUM, 'grid.parquet'))


def simulate_loop_only_iob(grid_df, ds_path=None):
    """
    Simulate the old bug: zero out IOB/COB for non-Loop devicestatus rows.
    For patients where controller is always Loop, this is a no-op.
    For patient b (98% Trio/oref0), this zeros out most IOB.
    """
    if ds_path is None:
        ds_path = os.path.join(TERRARIUM, 'devicestatus.parquet')

    ds = pd.read_parquet(ds_path, columns=['patient_id', 'created_at', 'controller'])
    ds['time'] = pd.to_datetime(ds['created_at'], utc=True)

    result = grid_df.copy()
    result['_sim_iob'] = result['iob'].copy()
    result['_sim_cob'] = result['cob'].copy()

    for pid in result['patient_id'].unique():
        p_ds = ds[ds['patient_id'] == pid]
        if 'loop' not in p_ds['controller'].values:
            # All non-Loop → zero everything (simulates old bug)
            mask = result['patient_id'] == pid
            result.loc[mask, '_sim_iob'] = 0.0
            result.loc[mask, '_sim_cob'] = 0.0
        elif set(p_ds['controller'].unique()) != {'loop'}:
            # Mixed controller — zero non-Loop intervals
            # Find Loop time ranges and only keep IOB within them
            loop_times = sorted(p_ds[p_ds['controller'] == 'loop']['time'].values)
            if len(loop_times) == 0:
                mask = result['patient_id'] == pid
                result.loc[mask, '_sim_iob'] = 0.0
                result.loc[mask, '_sim_cob'] = 0.0
            else:
                # Simple: mark grid rows that are >30min from any Loop DS record
                p_mask = result['patient_id'] == pid
                p_grid = result.loc[p_mask].copy()
                grid_times = pd.to_datetime(p_grid['time'], utc=True).values

                # For each grid row, check if nearest Loop DS is within 30 min
                loop_arr = np.array(loop_times, dtype='datetime64[ns]')
                grid_arr = np.array(grid_times, dtype='datetime64[ns]')

                # Use searchsorted for efficient nearest-neighbor
                idx = np.searchsorted(loop_arr, grid_arr)
                idx = np.clip(idx, 0, len(loop_arr) - 1)

                # Check distance to nearest Loop record
                dist_ns = np.abs((grid_arr - loop_arr[idx]).astype('int64'))
                # Also check idx-1
                idx_prev = np.clip(idx - 1, 0, len(loop_arr) - 1)
                dist_prev = np.abs((grid_arr - loop_arr[idx_prev]).astype('int64'))
                min_dist = np.minimum(dist_ns, dist_prev)

                # 30 minutes in nanoseconds
                threshold = 30 * 60 * 1e9
                not_loop = min_dist > threshold

                result.loc[p_mask & pd.Series(not_loop, index=p_grid.index), '_sim_iob'] = 0.0
                result.loc[p_mask & pd.Series(not_loop, index=p_grid.index), '_sim_cob'] = 0.0

    return result


def analysis_1_iob_predictive_power(grid_df):
    """
    How well does DS IOB predict 1-hour glucose change?
    Compare full IOB vs loop-only IOB for each patient.
    """
    print("\n═══ Analysis 1: IOB Predictive Power (1-hour glucose Δ) ═══")
    results = {}

    for pid in sorted(grid_df['patient_id'].unique()):
        p = grid_df[grid_df['patient_id'] == pid].sort_values('time').copy()

        # Compute 1-hour glucose delta
        p['delta_1h'] = p['glucose'].shift(-12) - p['glucose']

        for iob_col, label in [('iob', 'full'), ('_sim_iob', 'loop_only')]:
            mask = p[iob_col].notna() & p['delta_1h'].notna() & (p[iob_col] > 0)
            n = mask.sum()
            if n < 30:
                if label == 'full':
                    results.setdefault(pid, {})['full_n'] = n
                    results[pid]['full_r2'] = None
                    results[pid]['loop_only_r2'] = None
                    results[pid]['loop_only_n'] = n
                continue

            r, pval = stats.pearsonr(p.loc[mask, iob_col], p.loc[mask, 'delta_1h'])

            results.setdefault(pid, {})[f'{label}_r'] = round(r, 3)
            results[pid][f'{label}_r2'] = round(r**2, 4)
            results[pid][f'{label}_n'] = n
            results[pid][f'{label}_p'] = pval

        pr = results.get(pid, {})
        full_r2 = pr.get('full_r2')
        lo_r2 = pr.get('loop_only_r2')
        full_n = pr.get('full_n', 0)
        lo_n = pr.get('loop_only_n', 0)

        if full_r2 is not None and lo_r2 is not None:
            delta = (full_r2 - lo_r2) if lo_r2 else full_r2
            print(f"  {pid}: full R²={full_r2:.4f} (n={full_n}), "
                  f"loop-only R²={lo_r2:.4f} (n={lo_n}), "
                  f"Δ={delta:+.4f}")
        elif full_r2 is not None:
            print(f"  {pid}: full R²={full_r2:.4f} (n={full_n}), "
                  f"loop-only: insufficient (n={lo_n})")
        else:
            print(f"  {pid}: insufficient data (n={full_n})")

    return results


def analysis_2_iob_stratified_outcomes(grid_df):
    """
    Stratify by IOB level → mean 1-hour glucose change.
    With the old bug, patient b had essentially no IOB stratification.
    """
    print("\n═══ Analysis 2: IOB-Stratified Glucose Outcomes ═══")
    results = {}

    for pid in sorted(grid_df['patient_id'].unique()):
        p = grid_df[grid_df['patient_id'] == pid].sort_values('time').copy()
        p['delta_1h'] = p['glucose'].shift(-12) - p['glucose']

        for iob_col, label in [('iob', 'full'), ('_sim_iob', 'loop_only')]:
            mask = p[iob_col].notna() & p['delta_1h'].notna()
            valid = p.loc[mask]
            if len(valid) < 100:
                continue

            # Tertile split on IOB
            iob_vals = valid[iob_col]
            try:
                q33, q67 = np.percentile(iob_vals[iob_vals > 0], [33, 67]) if (iob_vals > 0).sum() > 30 else (0, 0)
            except Exception:
                q33, q67 = 0, 0

            if q33 == q67 == 0:
                results.setdefault(pid, {})[f'{label}_low_delta'] = None
                continue

            low = valid[iob_vals <= q33]['delta_1h'].mean()
            mid = valid[(iob_vals > q33) & (iob_vals <= q67)]['delta_1h'].mean()
            high = valid[iob_vals > q67]['delta_1h'].mean()

            results.setdefault(pid, {})[f'{label}_low_delta'] = round(low, 1)
            results[pid][f'{label}_mid_delta'] = round(mid, 1)
            results[pid][f'{label}_high_delta'] = round(high, 1)
            results[pid][f'{label}_spread'] = round(high - low, 1)

        pr = results.get(pid, {})
        full_spread = pr.get('full_spread')
        lo_spread = pr.get('loop_only_spread')

        if full_spread is not None:
            lo_str = f"loop-only spread={lo_spread}" if lo_spread is not None else "loop-only: no stratification"
            print(f"  {pid}: full spread={full_spread:+.1f} mg/dL/hr, {lo_str}")
        else:
            print(f"  {pid}: insufficient data")

    return results


def analysis_3_controller_patterns(grid_df):
    """
    Detect controller suspend/active patterns using IOB.
    With real IOB for patient b, we can now see oref0 suspend behavior.
    """
    print("\n═══ Analysis 3: Controller Suspend Patterns (IOB-based) ═══")
    results = {}

    for pid in sorted(grid_df['patient_id'].unique()):
        p = grid_df[grid_df['patient_id'] == pid].sort_values('time').copy()

        for iob_col, label in [('iob', 'full'), ('_sim_iob', 'loop_only')]:
            mask = p[iob_col].notna()
            valid = p.loc[mask, iob_col]
            if len(valid) < 100:
                continue

            # Suspend = IOB near zero (< 0.05 U)
            n_suspend = (valid < 0.05).sum()
            n_active = (valid >= 0.05).sum()
            suspend_pct = n_suspend / len(valid) if len(valid) > 0 else 0

            # IOB variability
            iob_cv = valid.std() / valid.mean() if valid.mean() > 0.01 else float('inf')

            results.setdefault(pid, {})[f'{label}_suspend_pct'] = round(suspend_pct, 3)
            results[pid][f'{label}_iob_mean'] = round(valid.mean(), 2)
            results[pid][f'{label}_iob_cv'] = round(iob_cv, 2)
            results[pid][f'{label}_n'] = len(valid)

        pr = results.get(pid, {})
        full_susp = pr.get('full_suspend_pct')
        lo_susp = pr.get('loop_only_suspend_pct')

        if full_susp is not None:
            lo_str = f"loop-only={lo_susp:.0%}" if lo_susp is not None else "loop-only: N/A"
            delta = ""
            if lo_susp is not None and abs(full_susp - lo_susp) > 0.01:
                delta = f" (Δ={full_susp - lo_susp:+.0%})"
            print(f"  {pid}: full suspend={full_susp:.0%}, {lo_str}{delta}")

    return results


def analysis_4_circadian_iob(grid_df):
    """
    IOB by hour of day — reveals controller dosing rhythm.
    Patient b should show a meaningful circadian IOB pattern with oref0 data.
    """
    print("\n═══ Analysis 4: Circadian IOB Pattern ═══")
    results = {}

    for pid in sorted(grid_df['patient_id'].unique()):
        p = grid_df[grid_df['patient_id'] == pid].copy()
        p['hour'] = pd.to_datetime(p['time']).dt.hour

        for iob_col, label in [('iob', 'full'), ('_sim_iob', 'loop_only')]:
            hourly = p.groupby('hour')[iob_col].agg(['mean', 'std', 'count'])
            if hourly['mean'].sum() < 0.1:
                continue

            peak_hour = hourly['mean'].idxmax()
            trough_hour = hourly['mean'].idxmin()
            ratio = hourly['mean'].max() / max(hourly['mean'].min(), 0.01)

            results.setdefault(pid, {})[f'{label}_peak_hour'] = int(peak_hour)
            results[pid][f'{label}_trough_hour'] = int(trough_hour)
            results[pid][f'{label}_ratio'] = round(ratio, 1)
            results[pid][f'{label}_mean_iob'] = round(hourly['mean'].mean(), 2)

        pr = results.get(pid, {})
        full_ratio = pr.get('full_ratio')
        lo_ratio = pr.get('loop_only_ratio')

        if full_ratio is not None:
            lo_str = f"loop-only ratio={lo_ratio:.1f}×" if lo_ratio is not None else "loop-only: no signal"
            print(f"  {pid}: full peak={pr.get('full_peak_hour')}h, "
                  f"trough={pr.get('full_trough_hour')}h, "
                  f"ratio={full_ratio:.1f}×, {lo_str}")

    return results


def main():
    print("IOB-Dependent Validation Experiment")
    print("=" * 60)
    print(f"Terrarium: {TERRARIUM}")
    print(f"Time: {datetime.utcnow().isoformat()}Z")

    # Load data
    print("\nLoading grid...")
    grid = load_grid()
    print(f"  {len(grid)} rows, {grid['patient_id'].nunique()} patients")

    # Simulate old bug
    print("Simulating Loop-only IOB (old bug)...")
    grid = simulate_loop_only_iob(grid)

    # Quick comparison
    for pid in ['b', 'a', 'c']:
        p = grid[grid['patient_id'] == pid]
        full_nz = (p['iob'] > 0).mean()
        sim_nz = (p['_sim_iob'] > 0).mean()
        print(f"  {pid}: full IOB>0={full_nz:.1%}, simulated loop-only IOB>0={sim_nz:.1%}"
              f"{'  ← FIX IMPACT' if abs(full_nz - sim_nz) > 0.05 else ''}")

    # Run analyses
    r1 = analysis_1_iob_predictive_power(grid)
    r2 = analysis_2_iob_stratified_outcomes(grid)
    r3 = analysis_3_controller_patterns(grid)
    r4 = analysis_4_circadian_iob(grid)

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY: Impact of oref0/Trio IOB Inclusion")
    print("=" * 60)

    # Patient b specific
    b1 = r1.get('b', {})
    b3 = r3.get('b', {})
    b4 = r4.get('b', {})

    print(f"\n  Patient b (98% Trio/oref0):")
    print(f"    IOB predictive R² (full):       {b1.get('full_r2', 'N/A')}")
    print(f"    IOB predictive R² (loop-only):  {b1.get('loop_only_r2', 'N/A')}")
    print(f"    Suspend % (full):               {b3.get('full_suspend_pct', 'N/A')}")
    print(f"    Suspend % (loop-only):          {b3.get('loop_only_suspend_pct', 'N/A')}")
    print(f"    Circadian ratio (full):         {b4.get('full_ratio', 'N/A')}×")
    print(f"    Circadian ratio (loop-only):    {b4.get('loop_only_ratio', 'N/A')}")

    # Save results
    output = {
        'experiment': 'iob_dependent_validation',
        'title': 'IOB-Dependent Validation: oref0/Trio Fix Impact',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'data_source': TERRARIUM,
        'analyses': {
            'predictive_power': r1,
            'stratified_outcomes': r2,
            'controller_patterns': r3,
            'circadian_iob': r4,
        },
        'patient_b_impact': {
            'full_iob_r2': b1.get('full_r2'),
            'loop_only_iob_r2': b1.get('loop_only_r2'),
            'full_suspend_pct': b3.get('full_suspend_pct'),
            'loop_only_suspend_pct': b3.get('loop_only_suspend_pct'),
            'full_circadian_ratio': b4.get('full_ratio'),
            'loop_only_circadian_ratio': b4.get('loop_only_ratio'),
        }
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, 'iob-validation-experiment.json')
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results → {outpath}")


if __name__ == '__main__':
    main()
