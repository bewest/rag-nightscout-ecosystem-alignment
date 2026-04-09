#!/usr/bin/env python3
"""EXP-1621–1628: Recommendation Confidence Intervals

Batch 5: Bootstrap/conformal prediction on therapy recommendations.
Quantify how stable recommendations are across data splits.

Prior art:
  - EXP-1601: Response-curve ISF fits R²=0.68-0.98, temporal CV=0.08-1.15
  - EXP-1531: Fidelity thresholds RMSE≤6/≤9/≤11, CE≤600/≤1000/≤1600
  - Production settings_advisor: 25% move toward effective ISF
  - ISF mismatch: 7/11 patients high (>2x profile)
"""

import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

from cgmencode.exp_metabolic_flux import load_patients


def _load_patients():
    return load_patients(patients_dir=str(PATIENTS_DIR), max_patients=None)


TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def _find_corrections(df):
    """Find isolated correction boluses."""
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    n = len(glucose)
    corrections = []
    for i in range(12, n - 36):
        if bolus[i] < 0.3 or glucose[i] <= 150:
            continue
        if np.nansum(carbs[max(0, i-6):min(n, i+6)]) > 2:
            continue
        if np.nansum(bolus[i+1:min(n, i+36)]) > 0.5:
            continue
        if np.nansum(carbs[i+1:min(n, i+36)]) > 2:
            continue
        traj = glucose[i:min(n, i+36)]
        valid = np.isfinite(traj)
        if valid.sum() < 18:
            continue
        corrections.append({
            'index': i, 'bolus': float(bolus[i]),
            'bg_start': float(glucose[i]),
            'trajectory': traj, 'valid_mask': valid,
        })
    return corrections


def _fit_isf(correction):
    """Fit exponential decay, return ISF and tau."""
    traj = correction['trajectory']
    valid = correction['valid_mask']
    bg_start = correction['bg_start']
    t_hours = np.arange(len(traj)) * 5.0 / 60.0
    best_sse, best_tau, best_amp = np.inf, 2.0, 0.0
    for tau in TAU_CANDIDATES:
        basis = 1.0 - np.exp(-t_hours / tau)
        bv = basis[valid]; tv = traj[valid] - bg_start
        denom = np.sum(bv ** 2)
        if denom < 1e-10: continue
        amp = -np.sum(bv * tv) / denom
        predicted = bg_start - amp * basis
        sse = float(np.sum((traj[valid] - predicted[valid]) ** 2))
        if sse < best_sse:
            best_sse, best_tau, best_amp = sse, tau, amp
    ss_tot = np.sum((traj[valid] - np.mean(traj[valid])) ** 2)
    r2 = 1 - best_sse / max(ss_tot, 1e-10)
    isf = best_amp / max(correction['bolus'], 0.01)
    return {'tau': best_tau, 'amplitude': best_amp, 'r2': float(r2),
            'isf': float(isf), 'bolus': correction['bolus'], 'bg_start': bg_start}


def _compute_cr(df):
    """Estimate carb ratio from meal events."""
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    n = len(glucose)
    crs = []
    for i in range(12, n - 24):
        if carbs[i] < 10 or bolus[i] < 0.3:
            continue
        cr = carbs[i] / bolus[i]
        if 2 < cr < 50:
            crs.append(cr)
    return crs


def _save_result(exp_id, data, elapsed):
    out = RESULTS_DIR / f'exp-{exp_id}_confidence.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ Saved → {out}  ({elapsed:.1f}s)")


# ============================================================
# EXP-1621: ISF Bootstrap Confidence Intervals
# ============================================================
def exp_1621(patients):
    """Bootstrap ISF estimates to get confidence intervals."""
    print("\n" + "─" * 60)
    print("EXP-1621: ISF Bootstrap Confidence Intervals")
    print("─" * 60)
    t0 = time.time()
    N_BOOTSTRAP = 500
    results = {}

    for p in patients:
        try:
            corrections = _find_corrections(p['df'])
            fits = [_fit_isf(c) for c in corrections]
            good = [f for f in fits if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            if len(good) < 5:
                results[p['name']] = {'error': 'insufficient', 'n': len(good)}
                print(f"  {p['name']}: SKIPPED ({len(good)} good fits)")
                continue

            isfs = np.array([f['isf'] for f in good])
            point_est = float(np.median(isfs))

            # Bootstrap
            boot_medians = []
            rng = np.random.RandomState(42)
            for _ in range(N_BOOTSTRAP):
                sample = rng.choice(isfs, size=len(isfs), replace=True)
                boot_medians.append(float(np.median(sample)))

            boot_medians = np.array(boot_medians)
            ci_lo = float(np.percentile(boot_medians, 2.5))
            ci_hi = float(np.percentile(boot_medians, 97.5))
            ci_width = ci_hi - ci_lo
            ci_pct = ci_width / max(point_est, 1) * 100

            results[p['name']] = {
                'n_corrections': len(good),
                'point_estimate': point_est,
                'ci_95_low': ci_lo,
                'ci_95_high': ci_hi,
                'ci_width': ci_width,
                'ci_pct': ci_pct,
            }
            print(f"  {p['name']}: ISF={point_est:.0f}  95%CI=[{ci_lo:.0f}, {ci_hi:.0f}]  "
                  f"width={ci_pct:.0f}%  n={len(good)}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1621', 'title': 'ISF Bootstrap CIs', 'patients': results}
    _save_result(1621, result, time.time() - t0)
    return results


# ============================================================
# EXP-1622: CR Bootstrap Confidence Intervals
# ============================================================
def exp_1622(patients):
    """Bootstrap carb ratio estimates."""
    print("\n" + "─" * 60)
    print("EXP-1622: CR Bootstrap Confidence Intervals")
    print("─" * 60)
    t0 = time.time()
    N_BOOTSTRAP = 500
    results = {}

    for p in patients:
        try:
            crs = _compute_cr(p['df'])
            if len(crs) < 5:
                results[p['name']] = {'error': 'insufficient', 'n': len(crs)}
                print(f"  {p['name']}: SKIPPED ({len(crs)} meals)")
                continue

            crs = np.array(crs)
            point_est = float(np.median(crs))
            rng = np.random.RandomState(42)
            boot_medians = []
            for _ in range(N_BOOTSTRAP):
                sample = rng.choice(crs, size=len(crs), replace=True)
                boot_medians.append(float(np.median(sample)))

            boot_medians = np.array(boot_medians)
            ci_lo = float(np.percentile(boot_medians, 2.5))
            ci_hi = float(np.percentile(boot_medians, 97.5))
            ci_width = ci_hi - ci_lo
            ci_pct = ci_width / max(point_est, 1) * 100

            results[p['name']] = {
                'n_meals': len(crs),
                'point_estimate': point_est,
                'ci_95_low': ci_lo,
                'ci_95_high': ci_hi,
                'ci_width': ci_width,
                'ci_pct': ci_pct,
            }
            print(f"  {p['name']}: CR={point_est:.1f}  95%CI=[{ci_lo:.1f}, {ci_hi:.1f}]  "
                  f"width={ci_pct:.0f}%  n={len(crs)}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1622', 'title': 'CR Bootstrap CIs', 'patients': results}
    _save_result(1622, result, time.time() - t0)
    return results


# ============================================================
# EXP-1623: Temporal Split Stability
# ============================================================
def exp_1623(patients):
    """Compare ISF estimates from first half vs second half of data."""
    print("\n" + "─" * 60)
    print("EXP-1623: Temporal Split Stability")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            df = p['df']
            n = len(df)
            mid = n // 2

            # First half
            df1 = df.iloc[:mid].copy()
            df1.attrs = df.attrs
            corrections1 = _find_corrections(df1)
            fits1 = [_fit_isf(c) for c in corrections1]
            good1 = [f for f in fits1 if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            # Second half (adjust indices)
            df2 = df.iloc[mid:].reset_index(drop=True).copy()
            df2.attrs = df.attrs
            corrections2 = _find_corrections(df2)
            fits2 = [_fit_isf(c) for c in corrections2]
            good2 = [f for f in fits2 if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            if len(good1) < 3 or len(good2) < 3:
                results[p['name']] = {'error': 'insufficient_in_half'}
                print(f"  {p['name']}: SKIPPED (half1={len(good1)}, half2={len(good2)})")
                continue

            isf1 = float(np.median([f['isf'] for f in good1]))
            isf2 = float(np.median([f['isf'] for f in good2]))
            drift = (isf2 - isf1) / max(isf1, 1)

            cr1 = _compute_cr(df1)
            cr2 = _compute_cr(df2)
            cr_drift = 0
            if len(cr1) >= 5 and len(cr2) >= 5:
                cr_med1 = float(np.median(cr1))
                cr_med2 = float(np.median(cr2))
                cr_drift = (cr_med2 - cr_med1) / max(cr_med1, 1)
            else:
                cr_med1 = cr_med2 = None

            results[p['name']] = {
                'isf_half1': isf1, 'isf_half2': isf2,
                'isf_drift': float(drift),
                'isf_stable': abs(drift) < 0.3,
                'cr_half1': cr_med1, 'cr_half2': cr_med2,
                'cr_drift': float(cr_drift),
            }

            stable = "STABLE" if abs(drift) < 0.3 else "DRIFT"
            cr1_str = f"{cr_med1:.1f}" if cr_med1 else "N/A"
            cr2_str = f"{cr_med2:.1f}" if cr_med2 else "N/A"
            print(f"  {p['name']}: ISF {isf1:.0f}→{isf2:.0f} ({drift:+.0%}) {stable}  "
                  f"CR {cr1_str}→{cr2_str}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1623', 'title': 'Temporal Split Stability', 'patients': results}
    _save_result(1623, result, time.time() - t0)
    return results


# ============================================================
# EXP-1624: Leave-One-Out Correction Sensitivity
# ============================================================
def exp_1624(patients):
    """How much does removing one correction change the ISF estimate?"""
    print("\n" + "─" * 60)
    print("EXP-1624: Leave-One-Out Correction Sensitivity")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            corrections = _find_corrections(p['df'])
            fits = [_fit_isf(c) for c in corrections]
            good = [f for f in fits if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            if len(good) < 5:
                results[p['name']] = {'error': 'insufficient'}
                print(f"  {p['name']}: SKIPPED")
                continue

            isfs = [f['isf'] for f in good]
            full_median = float(np.median(isfs))

            # Leave-one-out
            loo_medians = []
            for i in range(len(isfs)):
                subset = isfs[:i] + isfs[i+1:]
                loo_medians.append(float(np.median(subset)))

            loo_range = max(loo_medians) - min(loo_medians)
            loo_pct = loo_range / max(full_median, 1) * 100
            max_influence = max(abs(m - full_median) for m in loo_medians)
            max_influence_pct = max_influence / max(full_median, 1) * 100

            results[p['name']] = {
                'n': len(isfs),
                'full_median': full_median,
                'loo_range': float(loo_range),
                'loo_range_pct': float(loo_pct),
                'max_influence': float(max_influence),
                'max_influence_pct': float(max_influence_pct),
                'robust': max_influence_pct < 10,
            }

            robust = "ROBUST" if max_influence_pct < 10 else "FRAGILE"
            print(f"  {p['name']}: ISF={full_median:.0f}  LOO range={loo_pct:.1f}%  "
                  f"max influence={max_influence_pct:.1f}%  {robust}  n={len(isfs)}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1624', 'title': 'LOO Correction Sensitivity', 'patients': results}
    _save_result(1624, result, time.time() - t0)
    return results


# ============================================================
# EXP-1625: Recommendation Stability Under Resampling
# ============================================================
def exp_1625(patients, isf_ci, cr_ci):
    """How stable are therapy recommendations under parameter uncertainty?"""
    print("\n" + "─" * 60)
    print("EXP-1625: Recommendation Stability Under Resampling")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        pname = p['name']
        df = p['df']
        isf_data = isf_ci.get(pname, {})
        cr_data = cr_ci.get(pname, {})

        if isf_data.get('error') or cr_data.get('error'):
            results[pname] = {'error': 'missing_ci'}
            print(f"  {pname}: SKIPPED — missing CI data")
            continue

        try:
            profile_isf = float(np.median([s['value'] for s in
                                           df.attrs.get('isf_schedule', [{'value': 50}])]))
            profile_cr = float(np.median([s['value'] for s in
                                          df.attrs.get('cr_schedule', [{'value': 10}])]))

            effective_isf = isf_data['point_estimate']
            effective_cr = cr_data['point_estimate']

            # Simulate recommendations at different CI bounds
            scenarios = {
                'point': (effective_isf, effective_cr),
                'isf_low_cr_low': (isf_data['ci_95_low'], cr_data['ci_95_low']),
                'isf_high_cr_high': (isf_data['ci_95_high'], cr_data['ci_95_high']),
                'isf_low_cr_high': (isf_data['ci_95_low'], cr_data['ci_95_high']),
                'isf_high_cr_low': (isf_data['ci_95_high'], cr_data['ci_95_low']),
            }

            # Compute recommended changes for each scenario
            recs = {}
            for name, (isf, cr) in scenarios.items():
                # ISF recommendation: 25% move toward effective
                isf_rec = profile_isf + 0.25 * (isf - profile_isf)
                cr_rec = profile_cr + 0.25 * (cr - profile_cr)
                isf_change_pct = (isf_rec - profile_isf) / max(profile_isf, 1) * 100
                cr_change_pct = (cr_rec - profile_cr) / max(profile_cr, 1) * 100
                recs[name] = {
                    'isf_rec': float(isf_rec),
                    'cr_rec': float(cr_rec),
                    'isf_change_pct': float(isf_change_pct),
                    'cr_change_pct': float(cr_change_pct),
                }

            # Recommendation range
            isf_recs = [r['isf_rec'] for r in recs.values()]
            cr_recs = [r['cr_rec'] for r in recs.values()]
            isf_rec_range = max(isf_recs) - min(isf_recs)
            cr_rec_range = max(cr_recs) - min(cr_recs)

            # Directional consistency: do all scenarios agree on direction?
            isf_directions = [np.sign(r['isf_change_pct']) for r in recs.values()]
            cr_directions = [np.sign(r['cr_change_pct']) for r in recs.values()]
            isf_consistent = len(set(isf_directions)) == 1
            cr_consistent = len(set(cr_directions)) == 1

            results[pname] = {
                'profile_isf': profile_isf,
                'profile_cr': profile_cr,
                'scenarios': recs,
                'isf_rec_range': float(isf_rec_range),
                'cr_rec_range': float(cr_rec_range),
                'isf_direction_consistent': isf_consistent,
                'cr_direction_consistent': cr_consistent,
            }

            print(f"  {pname}: ISF rec range={isf_rec_range:.0f}  "
                  f"CR rec range={cr_rec_range:.1f}  "
                  f"ISF consistent={'✓' if isf_consistent else '✗'}  "
                  f"CR consistent={'✓' if cr_consistent else '✗'}")

        except Exception as e:
            print(f"  {pname}: FAILED — {e}")
            traceback.print_exc()
            results[pname] = {'error': str(e)}

    result = {'experiment': 'EXP-1625', 'title': 'Recommendation Stability', 'patients': results}
    _save_result(1625, result, time.time() - t0)
    return results


# ============================================================
# EXP-1626: Conformal Prediction Bands
# ============================================================
def exp_1626(patients):
    """Conformal prediction: non-parametric coverage-guaranteed CIs."""
    print("\n" + "─" * 60)
    print("EXP-1626: Conformal Prediction Bands")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            corrections = _find_corrections(p['df'])
            fits = [_fit_isf(c) for c in corrections]
            good = [f for f in fits if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            if len(good) < 10:
                results[p['name']] = {'error': 'insufficient'}
                print(f"  {p['name']}: SKIPPED")
                continue

            isfs = np.array([f['isf'] for f in good])
            n = len(isfs)

            # Split conformal: calibration (70%) + test (30%)
            rng = np.random.RandomState(42)
            perm = rng.permutation(n)
            cal_idx = perm[:int(0.7 * n)]
            test_idx = perm[int(0.7 * n):]

            cal_isfs = isfs[cal_idx]
            test_isfs = isfs[test_idx]
            cal_median = np.median(cal_isfs)

            # Nonconformity scores on calibration set
            cal_scores = np.abs(cal_isfs - cal_median)

            # Target coverage levels
            coverages_target = [0.80, 0.90, 0.95]
            coverage_results = {}

            for alpha in coverages_target:
                q = np.percentile(cal_scores, alpha * 100)
                ci_lo = cal_median - q
                ci_hi = cal_median + q

                # Test coverage
                covered = np.sum((test_isfs >= ci_lo) & (test_isfs <= ci_hi))
                actual_coverage = covered / max(len(test_isfs), 1)

                coverage_results[str(alpha)] = {
                    'ci_low': float(ci_lo),
                    'ci_high': float(ci_hi),
                    'ci_width': float(ci_hi - ci_lo),
                    'target_coverage': alpha,
                    'actual_coverage': float(actual_coverage),
                    'calibrated': abs(actual_coverage - alpha) < 0.1,
                }

            results[p['name']] = {
                'n_total': n,
                'n_cal': len(cal_idx),
                'n_test': len(test_idx),
                'cal_median': float(cal_median),
                'coverages': coverage_results,
            }

            c90 = coverage_results['0.9']
            print(f"  {p['name']}: 90%CI=[{c90['ci_low']:.0f}, {c90['ci_high']:.0f}]  "
                  f"actual={c90['actual_coverage']:.0%}  "
                  f"width={c90['ci_width']:.0f}  "
                  f"{'CALIBRATED' if c90['calibrated'] else 'MISCALIBRATED'}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1626', 'title': 'Conformal Prediction Bands', 'patients': results}
    _save_result(1626, result, time.time() - t0)
    return results


# ============================================================
# EXP-1627: Sample Size vs CI Width
# ============================================================
def exp_1627(patients):
    """How many corrections needed for a given CI width?"""
    print("\n" + "─" * 60)
    print("EXP-1627: Sample Size vs CI Width")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            corrections = _find_corrections(p['df'])
            fits = [_fit_isf(c) for c in corrections]
            good = [f for f in fits if f['r2'] > 0.3 and 5 < f['isf'] < 500]

            if len(good) < 10:
                results[p['name']] = {'error': 'insufficient'}
                print(f"  {p['name']}: SKIPPED")
                continue

            isfs = np.array([f['isf'] for f in good])
            full_median = np.median(isfs)

            # Subsample at different sizes
            sample_sizes = [5, 10, 15, 20, 30, 50, min(len(good), 75)]
            sample_sizes = [s for s in sample_sizes if s <= len(good)]
            rng = np.random.RandomState(42)

            size_results = {}
            for ss in sample_sizes:
                widths = []
                for _ in range(200):
                    sample = rng.choice(isfs, size=ss, replace=True)
                    boot_medians = [np.median(rng.choice(sample, size=ss, replace=True))
                                   for _ in range(100)]
                    ci_lo = np.percentile(boot_medians, 2.5)
                    ci_hi = np.percentile(boot_medians, 97.5)
                    widths.append((ci_hi - ci_lo) / max(full_median, 1) * 100)

                size_results[str(ss)] = {
                    'mean_ci_pct': float(np.mean(widths)),
                    'median_ci_pct': float(np.median(widths)),
                }

            # Find minimum n for <20% CI width
            min_n_20 = None
            for ss in sample_sizes:
                if size_results[str(ss)]['median_ci_pct'] < 20:
                    min_n_20 = ss
                    break

            results[p['name']] = {
                'n_available': len(good),
                'size_results': size_results,
                'min_n_for_20pct_ci': min_n_20,
            }

            print(f"  {p['name']}: n={len(good)}  min_n_20%={min_n_20}  "
                  f"@5={size_results['5']['median_ci_pct']:.0f}%  "
                  f"@{sample_sizes[-1]}={size_results[str(sample_sizes[-1])]['median_ci_pct']:.0f}%")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1627', 'title': 'Sample Size vs CI Width', 'patients': results}
    _save_result(1627, result, time.time() - t0)
    return results


# ============================================================
# EXP-1628: Confidence Grade System
# ============================================================
def exp_1628(patients, isf_ci, cr_ci, temporal, loo):
    """Synthesize a confidence grade for each recommendation."""
    print("\n" + "─" * 60)
    print("EXP-1628: Confidence Grade System")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        pname = p['name']
        isf = isf_ci.get(pname, {})
        cr = cr_ci.get(pname, {})
        temp = temporal.get(pname, {})
        lo = loo.get(pname, {})

        # Score components (0-1 each)
        scores = {}

        # 1. Sample size (more corrections = better)
        n_corr = isf.get('n_corrections', 0)
        scores['sample_size'] = min(1.0, n_corr / 30)

        # 2. CI tightness (narrower = better)
        ci_pct = isf.get('ci_pct', 100)
        scores['ci_tightness'] = max(0, 1 - ci_pct / 100)

        # 3. Temporal stability (less drift = better)
        drift = abs(temp.get('isf_drift', 1))
        scores['temporal_stability'] = max(0, 1 - drift)

        # 4. LOO robustness
        loo_pct = lo.get('max_influence_pct', 50)
        scores['loo_robustness'] = max(0, 1 - loo_pct / 20)

        # 5. CR availability
        scores['cr_available'] = 1.0 if not cr.get('error') else 0.0

        # Weighted composite
        weights = {'sample_size': 0.25, 'ci_tightness': 0.25,
                   'temporal_stability': 0.25, 'loo_robustness': 0.15,
                   'cr_available': 0.10}
        composite = sum(scores[k] * weights[k] for k in weights)

        # Grade
        if composite >= 0.7:
            grade = 'A'
        elif composite >= 0.5:
            grade = 'B'
        elif composite >= 0.3:
            grade = 'C'
        else:
            grade = 'D'

        results[pname] = {
            'scores': {k: round(v, 3) for k, v in scores.items()},
            'composite': round(composite, 3),
            'grade': grade,
        }

        print(f"  {pname}: grade={grade}  composite={composite:.2f}  "
              f"n={n_corr}  ci={ci_pct:.0f}%  drift={drift:.0%}")

    # Summary
    grades = [v['grade'] for v in results.values()]
    from collections import Counter
    grade_dist = Counter(grades)
    print(f"\n  Grade distribution: {dict(grade_dist)}")

    result = {
        'experiment': 'EXP-1628',
        'title': 'Confidence Grade System',
        'patients': results,
        'grade_distribution': dict(grade_dist),
    }
    _save_result(1628, result, time.time() - t0)
    return results


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 70)
    print("EXP-1621-1628: Recommendation Confidence Intervals")
    print("=" * 70)

    patients = _load_patients()
    print(f"Loaded {len(patients)} patients\n")

    isf_ci = exp_1621(patients)
    cr_ci = exp_1622(patients)
    temporal = exp_1623(patients)
    loo = exp_1624(patients)
    exp_1625(patients, isf_ci, cr_ci)
    exp_1626(patients)
    exp_1627(patients)
    exp_1628(patients, isf_ci, cr_ci, temporal, loo)

    print("\n" + "=" * 70)
    print("COMPLETE: 8/8 experiments")
    print("=" * 70)
