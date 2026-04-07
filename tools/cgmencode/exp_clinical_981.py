#!/usr/bin/env python3
"""EXP-981 through EXP-990: AID-Aware Clinical Intelligence.

Building on EXP-971-980's discovery that AID loop action confounds ALL naive
settings assessment, these experiments properly deconfound loop behavior from
profile settings using the basal_ratio PK channel and insulin delivery data.

Key insight from EXP-972: Only 0.5% of time has near-scheduled basal (ratio
0.9-1.1). The loop is always compensating — 54% high temp, 38% suspended.

Experiment registry:
    EXP-981: Loop aggressiveness score (how much does loop compensate?)
    EXP-982: AID-deconfounded basal adequacy
    EXP-983: Total insulin ISF validation (bolus + loop corrections)
    EXP-984: Loop intervention patterns by time-of-day
    EXP-985: Settings stability windows (when is the loop NOT intervening?)
    EXP-986: 3-day glucose trajectory clustering
    EXP-987: Patient difficulty decomposition
    EXP-988: Circadian supply-demand signatures
    EXP-989: Sensor age effect on prediction quality
    EXP-990: Glycemic control fidelity composite score

Usage:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_981 --detail --save --max-patients 11
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import (
    load_patients, _extract_isf_scalar, _extract_cr_scalar, save_results,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]


def _get_local_hour(df):
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        local = df.index.tz_convert(tz)
    except Exception:
        local = df.index
    return np.array(local.hour + local.minute / 60.0)


def _get_basal_ratio(pk):
    """Extract actual basal_ratio from PK channel 2 (denormalize by 2.0)."""
    return pk[:, 2] * PK_NORMS[2]  # norm=2.0


def _get_insulin_total(pk):
    """Extract total insulin activity from PK channel 0 (U/min)."""
    return pk[:, 0] * PK_NORMS[0]


def _get_insulin_net(pk):
    """Extract net insulin deviation from PK channel 1 (U/min)."""
    return pk[:, 1] * PK_NORMS[1]


# ===================================================================
# EXP-981: Loop Aggressiveness Score
# ===================================================================

def run_exp981(patients, args):
    """Measure how aggressively the AID loop deviates from scheduled basal.

    Loop aggressiveness = mean |basal_ratio - 1.0|
    High aggressiveness may indicate settings need adjustment — the loop is
    constantly compensating for inadequate basal rates.
    """
    print("\n" + "=" * 60)
    print("Running EXP-981: Loop Aggressiveness Score")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        valid = bg > 30

        # Overall aggressiveness
        aggressiveness = np.mean(np.abs(br[valid] - 1.0))
        pct_suspended = np.mean(br[valid] < 0.1)
        pct_high_temp = np.mean(br[valid] > 1.5)
        pct_nominal = np.mean((br[valid] >= 0.9) & (br[valid] <= 1.1))
        mean_ratio = np.mean(br[valid])

        # Direction bias: does the loop mostly increase or decrease?
        upward_bias = np.mean(br[valid] > 1.0)  # fraction of time delivering MORE

        # By time of day
        tod_aggr = {}
        for block in [0, 6, 12, 18]:
            mask = valid & (hours >= block) & (hours < block + 6)
            if np.sum(mask) > 100:
                br_block = br[mask]
                tod_aggr[f"{block:02d}-{block+6:02d}h"] = {
                    'aggressiveness': round(np.mean(np.abs(br_block - 1.0)), 3),
                    'mean_ratio': round(np.mean(br_block), 3),
                    'pct_suspended': round(np.mean(br_block < 0.1), 3),
                    'pct_high_temp': round(np.mean(br_block > 1.5), 3),
                }

        # Correlate aggressiveness with TIR
        n_days = np.sum(valid) // STEPS_PER_DAY
        daily_aggr = []
        daily_tir = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            dbg = bg[start:end]
            dbr = br[start:end]
            v = dbg > 30
            if np.sum(v) > 200:
                daily_aggr.append(np.mean(np.abs(dbr[v] - 1.0)))
                daily_tir.append(np.mean((dbg[v] >= 70) & (dbg[v] <= 180)))

        if len(daily_aggr) > 10:
            aggr_tir_corr = np.corrcoef(daily_aggr, daily_tir)[0, 1]
        else:
            aggr_tir_corr = float('nan')

        per_patient.append({
            'patient': p['name'],
            'aggressiveness': round(aggressiveness, 3),
            'mean_basal_ratio': round(mean_ratio, 3),
            'pct_suspended': round(pct_suspended, 3),
            'pct_high_temp': round(pct_high_temp, 3),
            'pct_nominal': round(pct_nominal, 3),
            'upward_bias': round(upward_bias, 3),
            'aggressiveness_tir_corr': round(aggr_tir_corr, 3) if np.isfinite(aggr_tir_corr) else None,
            'by_time_of_day': tod_aggr,
        })

    aggrs = [pp['aggressiveness'] for pp in per_patient]
    detail = (f"mean_aggr={np.mean(aggrs):.3f}, "
              f"range=[{min(aggrs):.3f}, {max(aggrs):.3f}]")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-981', 'name': 'Loop Aggressiveness Score',
        'status': 'pass', 'detail': detail,
        'results': {'mean_aggressiveness': round(np.mean(aggrs), 3),
                     'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-982: AID-Deconfounded Basal Adequacy
# ===================================================================

def run_exp982(patients, args):
    """Assess basal by looking at glucose drift ONLY when the loop is
    delivering near-scheduled basal (ratio 0.8-1.2) for at least 1 hour.

    Also assess using net_basal: when net deviation is near zero, the loop
    is not intervening, revealing true basal-glucose equilibrium.
    """
    print("\n" + "=" * 60)
    print("Running EXP-982: AID-Deconfounded Basal Adequacy")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Find windows where: ratio in [0.8, 1.2] AND no bolus AND no carbs
        # for at least 1 hour continuously
        nominal = (br >= 0.8) & (br <= 1.2) & (bolus < 0.05) & (carbs < 2.0) & (bg > 30)

        min_run = STEPS_PER_HOUR  # 1 hour
        windows = []
        start = None
        for i in range(len(nominal)):
            if nominal[i]:
                if start is None:
                    start = i
            else:
                if start is not None and (i - start) >= min_run:
                    windows.append((start, i))
                start = None
        if start is not None and (len(nominal) - start) >= min_run:
            windows.append((start, len(nominal)))

        # Measure glucose drift in each window
        SEGMENTS = {'overnight': (0, 6), 'morning': (6, 12),
                    'afternoon': (12, 18), 'evening': (18, 24)}
        seg_drifts = {name: [] for name in SEGMENTS}
        total_nominal_hours = 0

        for ws, we in windows:
            window_bg = bg[ws:we]
            window_hours = hours[ws:we]
            if np.sum(window_bg > 30) < min_run:
                continue

            valid = window_bg > 30
            x = np.arange(np.sum(valid))
            y = window_bg[valid]
            if len(x) < 6:
                continue
            slope, _, _, _, _ = stats.linregress(x, y)
            drift_per_hour = slope * STEPS_PER_HOUR
            total_nominal_hours += (we - ws) / STEPS_PER_HOUR

            mid_hour = np.median(window_hours)
            for name, (h_start, h_end) in SEGMENTS.items():
                if h_start <= mid_hour < h_end:
                    seg_drifts[name].append(drift_per_hour)
                    break

        # Summarize
        seg_results = {}
        for name, drifts in seg_drifts.items():
            if drifts:
                mean_drift = np.mean(drifts)
                seg_results[name] = {
                    'mean_drift_mgdl_per_h': round(mean_drift, 2),
                    'n_windows': len(drifts),
                    'adequacy': ('good' if abs(mean_drift) < 5.0
                                 else 'low_basal' if mean_drift > 5.0
                                 else 'high_basal'),
                }
            else:
                seg_results[name] = {'n_windows': 0, 'adequacy': 'no_nominal_periods'}

        scored = [s for s in seg_results.values() if s.get('mean_drift_mgdl_per_h') is not None]
        adequate = sum(1 for s in scored if abs(s['mean_drift_mgdl_per_h']) < 5.0)
        composite = adequate / max(len(scored), 1)

        per_patient.append({
            'patient': p['name'],
            'total_nominal_hours': round(total_nominal_hours, 1),
            'pct_time_nominal': round(total_nominal_hours / (len(bg) / STEPS_PER_HOUR) * 100, 1),
            'n_nominal_windows': len(windows),
            'composite_score': round(composite, 2),
            'segments': seg_results,
        })

    composites = [pp['composite_score'] for pp in per_patient]
    nominal_hours = [pp['total_nominal_hours'] for pp in per_patient]
    detail = (f"mean_adequacy={np.mean(composites):.2f}, "
              f"mean_nominal_hours={np.mean(nominal_hours):.0f}")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-982', 'name': 'AID-Deconfounded Basal Adequacy',
        'status': 'pass', 'detail': detail,
        'results': {'mean_composite': round(np.mean(composites), 3),
                     'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-983: Total Insulin ISF Validation
# ===================================================================

def run_exp983(patients, args):
    """Validate ISF using TOTAL insulin delivered (bolus + loop adjustments),
    not just manual correction boluses.

    Find periods of >150 BG with no carbs, measure total insulin_net activity
    and actual glucose drop over 3 hours.
    """
    print("\n" + "=" * 60)
    print("Running EXP-983: Total Insulin ISF Validation")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        isf_profile = _extract_isf_scalar(df)
        ins_net = _get_insulin_net(pk)  # U/min, net above scheduled
        ins_total = _get_insulin_total(pk)  # U/min, all sources
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        window = 3 * STEPS_PER_HOUR
        isf_actuals = []
        isf_ratios = []

        # Scan for high-BG correction episodes
        i = 0
        while i < len(bg) - window:
            if bg[i] > 150 and bg[i] > 30:
                # Check no carbs in window
                carb_sum = np.sum(carbs[i:i + window])
                if carb_sum < 3.0:
                    # Total insulin activity in window
                    total_ins = np.sum(ins_total[i:i + window]) * 5.0  # U/min * 5min = U
                    net_ins = np.sum(ins_net[i:i + window]) * 5.0

                    # Glucose drop
                    window_bg = bg[i:i + window]
                    valid = window_bg > 30
                    if np.sum(valid) > 12:
                        nadir = np.min(window_bg[valid])
                        drop = bg[i] - nadir

                        if drop > 10 and total_ins > 0.1:
                            isf_actual = drop / total_ins
                            ratio = isf_profile / isf_actual
                            isf_actuals.append(isf_actual)
                            isf_ratios.append(ratio)

                i += window  # skip ahead
            else:
                i += 1

        if isf_actuals:
            per_patient.append({
                'patient': p['name'],
                'isf_profile': round(isf_profile, 1),
                'n_episodes': len(isf_actuals),
                'mean_isf_actual': round(np.mean(isf_actuals), 1),
                'median_isf_actual': round(np.median(isf_actuals), 1),
                'mean_isf_ratio': round(np.mean(isf_ratios), 2),
                'std_isf_ratio': round(np.std(isf_ratios), 2),
                'assessment': ('accurate' if 0.5 <= np.mean(isf_ratios) <= 1.5
                               else 'isf_too_high' if np.mean(isf_ratios) > 1.5
                               else 'isf_too_low'),
            })
        else:
            per_patient.append({
                'patient': p['name'], 'isf_profile': round(isf_profile, 1),
                'n_episodes': 0, 'assessment': 'insufficient_data',
            })

    ratios = [pp['mean_isf_ratio'] for pp in per_patient if pp.get('mean_isf_ratio')]
    detail = (f"patients_with_data={sum(1 for pp in per_patient if pp['n_episodes'] > 0)}/{len(per_patient)}, "
              f"mean_ratio={np.mean(ratios):.2f}" if ratios else "no data")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-983', 'name': 'Total Insulin ISF Validation',
        'status': 'pass', 'detail': detail,
        'results': {'mean_isf_ratio': round(np.mean(ratios), 3) if ratios else None,
                     'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-984: Loop Intervention Patterns by Time-of-Day
# ===================================================================

def run_exp984(patients, args):
    """Map when the loop intervenes most aggressively. Circadian pattern of
    loop action reveals where settings are most misaligned.
    """
    print("\n" + "=" * 60)
    print("Running EXP-984: Loop Intervention Patterns by Time-of-Day")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        valid = bg > 30

        # Hourly intervention profile
        hourly = {}
        for h in range(24):
            mask = valid & (hours >= h) & (hours < h + 1)
            if np.sum(mask) > 50:
                br_h = br[mask]
                bg_h = bg[mask]
                hourly[h] = {
                    'mean_ratio': round(np.mean(br_h), 3),
                    'mean_deviation': round(np.mean(np.abs(br_h - 1.0)), 3),
                    'pct_suspended': round(np.mean(br_h < 0.1), 3),
                    'pct_high': round(np.mean(br_h > 1.5), 3),
                    'mean_bg': round(np.mean(bg_h), 1),
                }

        # Find peak intervention hours
        if hourly:
            deviations = {h: v['mean_deviation'] for h, v in hourly.items()}
            peak_hour = max(deviations, key=deviations.get)
            min_hour = min(deviations, key=deviations.get)

            # Dawn phenomenon: compare 4-7 AM ratio to 0-3 AM
            dawn_hours = [h for h in [4, 5, 6] if h in hourly]
            night_hours = [h for h in [0, 1, 2] if h in hourly]
            if dawn_hours and night_hours:
                dawn_ratio = np.mean([hourly[h]['mean_ratio'] for h in dawn_hours])
                night_ratio = np.mean([hourly[h]['mean_ratio'] for h in night_hours])
                dawn_effect = dawn_ratio - night_ratio
            else:
                dawn_effect = None

            per_patient.append({
                'patient': p['name'],
                'peak_intervention_hour': peak_hour,
                'min_intervention_hour': min_hour,
                'peak_deviation': round(deviations[peak_hour], 3),
                'min_deviation': round(deviations[min_hour], 3),
                'dawn_effect': round(dawn_effect, 3) if dawn_effect is not None else None,
                'hourly_profile': hourly,
            })

    dawn_effects = [pp['dawn_effect'] for pp in per_patient if pp.get('dawn_effect') is not None]
    detail = (f"patients={len(per_patient)}, "
              f"mean_dawn_effect={np.mean(dawn_effects):.3f}" if dawn_effects else
              f"patients={len(per_patient)}")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-984', 'name': 'Loop Intervention Patterns by Time-of-Day',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient),
                     'mean_dawn_effect': round(np.mean(dawn_effects), 3) if dawn_effects else None,
                     'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-985: Settings Stability Windows
# ===================================================================

def run_exp985(patients, args):
    """Find natural periods where loop is minimally active (ratio near 1.0
    for extended time). These reveal true basal-glucose equilibrium.
    Characterize how long and how often these occur.
    """
    print("\n" + "=" * 60)
    print("Running EXP-985: Settings Stability Windows")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        br = _get_basal_ratio(pk)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # "Stable" = ratio in [0.8, 1.2], no bolus, no carbs, BG in range
        stable = ((br >= 0.8) & (br <= 1.2) & (bolus < 0.05) &
                  (carbs < 2.0) & (bg >= 70) & (bg <= 180))

        # Find runs of stability
        runs = []
        start = None
        for i in range(len(stable)):
            if stable[i]:
                if start is None:
                    start = i
            else:
                if start is not None:
                    run_len = i - start
                    if run_len >= 6:  # at least 30 min
                        runs.append((start, i, run_len))
                start = None
        if start is not None and (len(stable) - start) >= 6:
            runs.append((start, len(stable), len(stable) - start))

        # Characterize runs
        if runs:
            run_lengths_min = [r[2] * 5 for r in runs]
            total_stable_hours = sum(run_lengths_min) / 60.0
            total_hours = len(bg) / STEPS_PER_HOUR
            pct_stable = total_stable_hours / total_hours * 100

            # BG statistics during stable windows
            stable_bgs = []
            stable_drifts = []
            for ws, we, rl in runs:
                wbg = bg[ws:we]
                stable_bgs.extend(wbg[wbg > 30])
                if rl >= 12:  # at least 1 hour
                    valid = wbg > 30
                    if np.sum(valid) >= 6:
                        x = np.arange(np.sum(valid))
                        slope, _, _, _, _ = stats.linregress(x, wbg[valid])
                        stable_drifts.append(slope * STEPS_PER_HOUR)

            per_patient.append({
                'patient': p['name'],
                'n_stable_windows': len(runs),
                'total_stable_hours': round(total_stable_hours, 1),
                'pct_time_stable': round(pct_stable, 1),
                'median_window_min': round(np.median(run_lengths_min), 0),
                'max_window_min': round(max(run_lengths_min), 0),
                'stable_mean_bg': round(np.mean(stable_bgs), 1) if stable_bgs else None,
                'stable_std_bg': round(np.std(stable_bgs), 1) if stable_bgs else None,
                'mean_drift_when_stable': round(np.mean(stable_drifts), 2) if stable_drifts else None,
                'true_basal_assessment': (
                    'good' if stable_drifts and abs(np.mean(stable_drifts)) < 3.0
                    else 'high_basal' if stable_drifts and np.mean(stable_drifts) < -3.0
                    else 'low_basal' if stable_drifts and np.mean(stable_drifts) > 3.0
                    else 'insufficient_data'),
            })
        else:
            per_patient.append({
                'patient': p['name'],
                'n_stable_windows': 0,
                'pct_time_stable': 0.0,
                'true_basal_assessment': 'never_stable',
            })

    pcts = [pp['pct_time_stable'] for pp in per_patient]
    detail = (f"mean_pct_stable={np.mean(pcts):.1f}%, "
              f"range=[{min(pcts):.1f}%, {max(pcts):.1f}%]")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-985', 'name': 'Settings Stability Windows',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-986: 3-Day Glucose Trajectory Clustering
# ===================================================================

def run_exp986(patients, args):
    """Cluster 3-day glucose trajectories to find recurring multi-day patterns.
    Uses the lag-1 autocorrelation (r=0.22 from EXP-971) to extract meaningful
    multi-day structure.
    """
    print("\n" + "=" * 60)
    print("Running EXP-986: 3-Day Glucose Trajectory Clustering")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)

        TRAJ_LEN = 3 * STEPS_PER_DAY  # 3 days
        STRIDE = STEPS_PER_DAY  # 1 day stride
        n_trajs = (len(bg) - TRAJ_LEN) // STRIDE

        if n_trajs < 10:
            continue

        # Extract trajectories (normalized to zero mean)
        trajectories = []
        traj_stats = []
        for t in range(n_trajs):
            start = t * STRIDE
            traj = bg[start:start + TRAJ_LEN]
            valid = traj > 30
            if np.sum(valid) > TRAJ_LEN * 0.7:
                mean_bg = np.mean(traj[valid])
                std_bg = np.std(traj[valid])
                tir = np.mean((traj[valid] >= 70) & (traj[valid] <= 180))
                # Normalize
                norm_traj = (traj - mean_bg) / max(std_bg, 1.0)
                trajectories.append(norm_traj)
                traj_stats.append({
                    'mean_bg': mean_bg, 'std_bg': std_bg, 'tir': tir
                })

        if len(trajectories) < 10:
            continue

        trajectories = np.array(trajectories)

        # Simple k-means-like clustering using hourly means
        # Reduce each 3-day trajectory to 72 hourly means
        hourly = np.zeros((len(trajectories), 72))
        for i, traj in enumerate(trajectories):
            for h in range(72):
                start = h * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                hourly[i, h] = np.mean(traj[start:end])

        # Use 3 clusters via simple distance-based assignment
        n_clusters = 3
        # Initialize with spread trajectories
        idx = np.linspace(0, len(hourly) - 1, n_clusters, dtype=int)
        centroids = hourly[idx].copy()

        for iteration in range(20):
            # Assign
            distances = np.zeros((len(hourly), n_clusters))
            for c in range(n_clusters):
                distances[:, c] = np.sum((hourly - centroids[c]) ** 2, axis=1)
            labels = np.argmin(distances, axis=1)

            # Update
            new_centroids = np.zeros_like(centroids)
            for c in range(n_clusters):
                mask = labels == c
                if np.sum(mask) > 0:
                    new_centroids[c] = np.mean(hourly[mask], axis=0)
                else:
                    new_centroids[c] = centroids[c]
            if np.allclose(centroids, new_centroids, atol=1e-6):
                break
            centroids = new_centroids

        # Characterize clusters
        cluster_info = []
        for c in range(n_clusters):
            mask = labels == c
            if np.sum(mask) > 0:
                cluster_tirs = [traj_stats[i]['tir'] for i in range(len(labels)) if labels[i] == c]
                cluster_means = [traj_stats[i]['mean_bg'] for i in range(len(labels)) if labels[i] == c]
                cluster_info.append({
                    'cluster': c,
                    'n_trajectories': int(np.sum(mask)),
                    'pct': round(np.sum(mask) / len(labels), 3),
                    'mean_tir': round(np.mean(cluster_tirs), 3),
                    'mean_bg': round(np.mean(cluster_means), 1),
                })

        # Does cluster assignment predict next-day TIR?
        next_day_tir = [traj_stats[i + 1]['tir'] for i in range(len(labels) - 1)]
        cluster_labels = labels[:-1]
        if len(set(cluster_labels)) > 1:
            groups = [np.array([next_day_tir[j] for j in range(len(cluster_labels))
                       if cluster_labels[j] == c])
                      for c in range(n_clusters) if np.sum(cluster_labels == c) > 3]
            if len(groups) >= 2:
                f_stat, p_val = stats.f_oneway(*groups)
            else:
                f_stat, p_val = 0, 1
        else:
            f_stat, p_val = 0, 1

        per_patient.append({
            'patient': p['name'],
            'n_trajectories': len(trajectories),
            'clusters': cluster_info,
            'next_day_predictive_f': round(f_stat, 2),
            'next_day_predictive_p': round(p_val, 4),
            'predictive': p_val < 0.05,
        })

    predictive = sum(1 for pp in per_patient if pp.get('predictive', False))
    detail = f"patients={len(per_patient)}, predictive={predictive}/{len(per_patient)}"
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-986', 'name': '3-Day Glucose Trajectory Clustering',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-987: Patient Difficulty Decomposition
# ===================================================================

def run_exp987(patients, args):
    """Why is patient i so hard (RMSE=17.5) and k so easy (RMSE=5.9)?
    Decompose difficulty into: glucose variability, meal regularity,
    insulin sensitivity stability, sensor quality, and loop behavior.
    """
    print("\n" + "=" * 60)
    print("Running EXP-987: Patient Difficulty Decomposition")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        valid = bg > 30

        if np.sum(valid) < 1000:
            continue

        bg_v = bg[valid]

        # 1. Glucose variability
        tir = np.mean((bg_v >= 70) & (bg_v <= 180))
        cv = np.std(bg_v) / np.mean(bg_v) if np.mean(bg_v) > 0 else 0
        mean_bg = np.mean(bg_v)

        # 5-min glucose changes
        delta_bg = np.diff(bg_v)
        bg_roughness = np.mean(np.abs(delta_bg))  # mean absolute 5-min change

        # 2. Meal regularity
        meal_times = []
        for i in range(len(carbs)):
            if carbs[i] > 5:
                meal_times.append(hours[i])
        if meal_times:
            meal_time_std = np.std(meal_times)
            meals_per_day = len(meal_times) / (len(bg) / STEPS_PER_DAY)
        else:
            meal_time_std = 0
            meals_per_day = 0

        # 3. Insulin sensitivity stability (rolling ISF from supply/demand)
        supply = sd['supply']
        demand = sd['demand']
        # Weekly supply/demand ratio
        WEEK = 7 * STEPS_PER_DAY
        n_weeks = len(bg) // WEEK
        weekly_ratios = []
        for w in range(n_weeks):
            start = w * WEEK
            end = start + WEEK
            ws = supply[start:end]
            wd = demand[start:end]
            v = bg[start:end] > 30
            if np.sum(v) > WEEK * 0.5 and np.sum(np.abs(wd[v])) > 0:
                weekly_ratios.append(np.sum(np.abs(ws[v])) / (np.sum(np.abs(wd[v])) + 1e-6))
        isf_stability = np.std(weekly_ratios) if len(weekly_ratios) > 2 else 0

        # 4. Loop aggressiveness
        loop_aggr = np.mean(np.abs(br[valid] - 1.0))

        # 5. Sensor quality proxy (glucose jump frequency)
        jumps = np.abs(delta_bg) > 15  # >15 mg/dL in 5 min
        jump_rate = np.mean(jumps) if len(jumps) > 0 else 0

        # 6. Conservation violation (from EXP-980 results)
        delta_bg_obs = np.zeros_like(bg)
        delta_bg_obs[1:] = bg[1:] - bg[:-1]
        violation = delta_bg_obs - sd['net']
        conservation_rmse = np.sqrt(np.mean(violation[valid]**2))

        per_patient.append({
            'patient': p['name'],
            'glucose_variability': {
                'mean_bg': round(mean_bg, 1),
                'cv': round(cv, 3),
                'tir': round(tir, 3),
                'roughness_mgdl_per_5min': round(bg_roughness, 2),
            },
            'meal_regularity': {
                'meals_per_day': round(meals_per_day, 1),
                'meal_time_std_hours': round(meal_time_std, 1),
            },
            'isf_stability': round(isf_stability, 3),
            'loop_aggressiveness': round(loop_aggr, 3),
            'sensor_quality': {
                'jump_rate': round(jump_rate, 4),
            },
            'conservation_rmse': round(conservation_rmse, 2),
        })

    # Rank patients by composite difficulty
    for pp in per_patient:
        difficulty = (pp['glucose_variability']['cv'] * 100 +
                      pp['isf_stability'] * 10 +
                      pp['loop_aggressiveness'] * 10 +
                      pp['conservation_rmse'])
        pp['composite_difficulty'] = round(difficulty, 1)

    per_patient.sort(key=lambda x: x['composite_difficulty'])
    for rank, pp in enumerate(per_patient):
        pp['difficulty_rank'] = rank + 1

    detail = f"easiest={per_patient[0]['patient']}, hardest={per_patient[-1]['patient']}"
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-987', 'name': 'Patient Difficulty Decomposition',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-988: Circadian Supply-Demand Signatures
# ===================================================================

def run_exp988(patients, args):
    """Compute mean hourly supply/demand profiles. Do they reveal
    interpretable metabolic phenotypes?
    """
    print("\n" + "=" * 60)
    print("Running EXP-988: Circadian Supply-Demand Signatures")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        hourly_profile = {}
        for h in range(24):
            mask = valid & (hours >= h) & (hours < h + 1)
            if np.sum(mask) > 50:
                hourly_profile[h] = {
                    'mean_supply': round(np.mean(sd['supply'][mask]), 3),
                    'mean_demand': round(np.mean(sd['demand'][mask]), 3),
                    'mean_net': round(np.mean(sd['net'][mask]), 3),
                    'mean_ratio': round(np.mean(sd['ratio'][mask]), 3),
                    'mean_bg': round(np.mean(bg[mask]), 1),
                }

        # Extract circadian features
        if len(hourly_profile) >= 20:
            nets = [hourly_profile[h]['mean_net'] for h in sorted(hourly_profile.keys())]
            ratios = [hourly_profile[h]['mean_ratio'] for h in sorted(hourly_profile.keys())]

            # Dawn surge: net flux at 4-7 AM vs 0-3 AM
            dawn_net = np.mean([hourly_profile[h]['mean_net'] for h in [4, 5, 6] if h in hourly_profile])
            night_net = np.mean([hourly_profile[h]['mean_net'] for h in [0, 1, 2] if h in hourly_profile])
            dawn_surge = dawn_net - night_net

            # Postprandial peaks (find hours with highest supply)
            supply_hours = {h: v['mean_supply'] for h, v in hourly_profile.items()}
            peak_supply_hour = max(supply_hours, key=supply_hours.get)

            # Overall circadian amplitude
            net_amplitude = max(nets) - min(nets)

            per_patient.append({
                'patient': p['name'],
                'dawn_surge': round(dawn_surge, 3),
                'peak_supply_hour': peak_supply_hour,
                'net_amplitude': round(net_amplitude, 3),
                'hourly_profile': hourly_profile,
            })

    dawn_surges = [pp['dawn_surge'] for pp in per_patient]
    amplitudes = [pp['net_amplitude'] for pp in per_patient]
    detail = (f"mean_dawn_surge={np.mean(dawn_surges):.3f}, "
              f"mean_amplitude={np.mean(amplitudes):.3f}")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-988', 'name': 'Circadian Supply-Demand Signatures',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-989: Sensor Age Effect on Prediction Quality
# ===================================================================

def run_exp989(patients, args):
    """Does sensor age affect glucose prediction quality?
    Measure conservation violation by sensor day.
    """
    print("\n" + "=" * 60)
    print("Running EXP-989: Sensor Age Effect on Prediction Quality")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        valid = bg > 30

        if 'sage_hours' not in df.columns:
            continue

        sage = np.nan_to_num(df['sage_hours'].values, nan=-1)
        delta_bg_obs = np.zeros_like(bg)
        delta_bg_obs[1:] = bg[1:] - bg[:-1]
        violation = np.abs(delta_bg_obs - sd['net'])

        # Bin by sensor day
        day_stats = {}
        for day in range(0, 11):
            mask = valid & (sage >= day * 24) & (sage < (day + 1) * 24)
            if np.sum(mask) > 200:
                bg_m = bg[mask]
                viol_m = violation[mask]
                day_stats[day] = {
                    'n_points': int(np.sum(mask)),
                    'mean_abs_violation': round(np.mean(viol_m), 3),
                    'mean_bg': round(np.mean(bg_m), 1),
                    'cv': round(np.std(bg_m) / np.mean(bg_m), 3),
                    'roughness': round(np.mean(np.abs(np.diff(bg_m))), 2),
                }

        if len(day_stats) >= 3:
            # Test for trend in violation with sensor age
            days = sorted(day_stats.keys())
            violations = [day_stats[d]['mean_abs_violation'] for d in days]
            slope, _, r_val, p_val, _ = stats.linregress(days, violations)

            per_patient.append({
                'patient': p['name'],
                'n_sensor_days': len(day_stats),
                'violation_trend_slope': round(slope, 4),
                'violation_trend_p': round(p_val, 4),
                'degradation_detected': p_val < 0.05 and slope > 0,
                'by_day': day_stats,
            })

    n_degrading = sum(1 for pp in per_patient if pp.get('degradation_detected', False))
    detail = f"patients_with_sage={len(per_patient)}, degradation={n_degrading}/{len(per_patient)}"
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-989', 'name': 'Sensor Age Effect on Prediction Quality',
        'status': 'pass', 'detail': detail,
        'results': {'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-990: Glycemic Control Fidelity Composite Score
# ===================================================================

def run_exp990(patients, args):
    """Composite score combining all clinical assessments into a single
    0-100 fidelity metric. Incorporates:
    - Supply/demand balance (EXP-976)
    - Loop aggressiveness (EXP-981)
    - Conservation violation (EXP-980)
    - TIR (direct outcome)
    - Glucose variability (CV)
    """
    print("\n" + "=" * 60)
    print("Running EXP-990: Glycemic Control Fidelity Composite Score")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        br = _get_basal_ratio(pk)
        valid = bg > 30

        if np.sum(valid) < 1000:
            continue

        bg_v = bg[valid]

        # Component 1: TIR (0-25 points)
        tir = np.mean((bg_v >= 70) & (bg_v <= 180))
        tir_score = min(25, tir * 25 / 0.7)  # 70% TIR = 25 points

        # Component 2: Glucose CV (0-25 points, lower is better)
        cv = np.std(bg_v) / np.mean(bg_v)
        cv_score = max(0, 25 * (1 - cv / 0.5))  # CV=0.5 = 0 points

        # Component 3: Supply/demand balance (0-25 points)
        supply = sd['supply']
        demand = sd['demand']
        net = sd['net']
        total_flux = np.sum(np.abs(supply[valid]) + np.abs(demand[valid]))
        net_integral = np.abs(np.sum(net[valid]))
        if total_flux > 0:
            balance = 1.0 - net_integral / total_flux
        else:
            balance = 0
        balance_score = max(0, balance * 25)

        # Component 4: Loop calmness (0-25 points, less intervention = better settings)
        loop_aggr = np.mean(np.abs(br[valid] - 1.0))
        # Typical range: 0.3 (calm) to 2.0 (aggressive)
        calm_score = max(0, 25 * (1 - loop_aggr / 2.0))

        composite = round(tir_score + cv_score + balance_score + calm_score, 1)

        per_patient.append({
            'patient': p['name'],
            'composite_score': composite,
            'components': {
                'tir_score': round(tir_score, 1),
                'cv_score': round(cv_score, 1),
                'balance_score': round(balance_score, 1),
                'calm_score': round(calm_score, 1),
            },
            'raw_metrics': {
                'tir': round(tir, 3),
                'cv': round(cv, 3),
                'balance': round(balance, 3),
                'loop_aggressiveness': round(loop_aggr, 3),
            },
        })

    # Sort by composite score
    per_patient.sort(key=lambda x: x['composite_score'], reverse=True)
    for rank, pp in enumerate(per_patient):
        pp['rank'] = rank + 1

    scores = [pp['composite_score'] for pp in per_patient]
    detail = (f"best={per_patient[0]['patient']}({per_patient[0]['composite_score']}), "
              f"worst={per_patient[-1]['patient']}({per_patient[-1]['composite_score']}), "
              f"mean={np.mean(scores):.1f}")
    print(f"  Status: pass\n  Detail: {detail}")
    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-990', 'name': 'Glycemic Control Fidelity Composite Score',
        'status': 'pass', 'detail': detail,
        'results': {'mean_composite': round(np.mean(scores), 1),
                     'n_patients': len(per_patient), 'per_patient': per_patient},
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# Main
# ===================================================================

EXPERIMENTS = {
    981: ('Loop Aggressiveness Score', run_exp981),
    982: ('AID-Deconfounded Basal Adequacy', run_exp982),
    983: ('Total Insulin ISF Validation', run_exp983),
    984: ('Loop Intervention Patterns by Time-of-Day', run_exp984),
    985: ('Settings Stability Windows', run_exp985),
    986: ('3-Day Glucose Trajectory Clustering', run_exp986),
    987: ('Patient Difficulty Decomposition', run_exp987),
    988: ('Circadian Supply-Demand Signatures', run_exp988),
    989: ('Sensor Age Effect on Prediction Quality', run_exp989),
    990: ('Glycemic Control Fidelity Composite Score', run_exp990),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-981-990: AID-Aware Clinical Intelligence')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all')
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)

    if args.experiments == 'all':
        exp_nums = sorted(EXPERIMENTS.keys())
    else:
        exp_nums = [int(x.strip()) for x in args.experiments.split(',')]

    for num in exp_nums:
        if num not in EXPERIMENTS:
            print(f"Unknown experiment: {num}")
            continue
        name, func = EXPERIMENTS[num]
        try:
            result = func(patients, args)
            if args.save and result and result.get('status') != 'error':
                save_dir = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
                save_dir.mkdir(parents=True, exist_ok=True)
                safe_name = name.lower().replace(' ', '_').replace('+', '_').replace('/', '_').replace('-', '_')
                fname = save_dir / f"exp_exp_{num}_{safe_name}.json"
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fname}")
        except Exception as e:
            print(f"  ERROR in EXP-{num}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("All experiments complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
