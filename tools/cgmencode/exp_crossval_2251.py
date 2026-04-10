#!/usr/bin/env python3
"""
EXP-2251 through EXP-2258: Cross-Validation & Production Readiness
===================================================================

Validates therapy estimates on held-out time windows and characterizes
convergence, confidence, and minimum data requirements.

EXP-2251: Temporal split validation (train months 1-3, test months 4-6)
EXP-2252: Rolling window convergence (how fast do estimates stabilize?)
EXP-2253: Bootstrap confidence intervals for therapy estimates
EXP-2254: Minimum data requirements (how many days for reliable estimates?)
EXP-2255: Cross-patient transferability (universal vs personalized)
EXP-2256: Settings change detection (simulated drift)
EXP-2257: Weekly stability assessment (week-to-week variability)
EXP-2258: Production readiness scorecard (composite pass/fail)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_crossval_2251.py --figures
"""

import json
import os
import sys
import argparse
import warnings
import numpy as np

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# ─────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def load_patients(data_dir='externals/ns-data/patients/'):
    from cgmencode.exp_metabolic_441 import load_patients as _lp
    return _lp(data_dir)


def get_schedule_value(schedule, hour):
    """Get value from a schedule list at a given hour."""
    if not schedule:
        return None
    val = None
    for entry in schedule:
        t = entry.get('timeAsSeconds', entry.get('time', 0))
        if isinstance(t, str):
            parts = t.split(':')
            t = int(parts[0]) * 3600
        entry_hour = t / 3600
        if entry_hour <= hour:
            val = entry.get('value', entry.get('rate', None))
    return val


def build_scheduled_array(schedule, hours):
    """Vectorized: build scheduled value array from schedule + hours array."""
    result = np.zeros(len(hours), dtype=np.float64)
    if not schedule:
        return result
    entries = []
    for entry in schedule:
        t = entry.get('timeAsSeconds', entry.get('time', 0))
        if isinstance(t, str):
            parts = t.split(':')
            t = int(parts[0]) * 3600
        entry_hour = t / 3600
        val = entry.get('value', entry.get('rate', 0))
        entries.append((entry_hour, val))
    entries.sort(key=lambda x: x[0])
    h_mod = hours % 24
    for i, (eh, ev) in enumerate(entries):
        if i < len(entries) - 1:
            mask = (h_mod >= eh) & (h_mod < entries[i + 1][0])
        else:
            mask = h_mod >= eh
        result[mask] = ev
    return result


def compute_tir_tbr_tar(glucose):
    """Compute TIR/TBR/TAR from glucose array."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0, 0, 0
    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
    tbr = np.mean(valid < 70) * 100
    tar = np.mean(valid > 180) * 100
    return float(tir), float(tbr), float(tar)


def compute_actual_delivery(df_slice, scheduled):
    """Compute actual insulin delivery from enacted_rate or net_basal fallback."""
    n = len(scheduled)
    actual = np.full(n, np.nan)
    if 'enacted_rate' in df_slice.columns:
        enacted = df_slice['enacted_rate'].values[:n]
        valid_enacted = ~np.isnan(enacted)
        actual[valid_enacted] = enacted[valid_enacted]
    if 'net_basal' in df_slice.columns:
        net = df_slice['net_basal'].values[:n]
        missing = np.isnan(actual)
        valid_net = ~np.isnan(net) & missing
        actual[valid_net] = scheduled[valid_net] + net[valid_net]
    still_missing = np.isnan(actual)
    actual[still_missing] = scheduled[still_missing]
    return actual


def compute_delivery_ratio_sum(actual, scheduled, valid_mask=None):
    """Sum-based delivery ratio: total delivered / total scheduled."""
    if valid_mask is None:
        valid_mask = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
    total_sched = np.sum(scheduled[valid_mask])
    total_actual = np.sum(actual[valid_mask])
    if total_sched <= 0:
        return 1.0
    return float(total_actual / total_sched)


# ─────────────────────────────────────────────────────────────────
# Core estimation functions (operate on arbitrary slices)
# ─────────────────────────────────────────────────────────────────
def estimate_basal_dr(df_slice, basal_schedule):
    """Estimate delivery ratio from a data slice."""
    n = len(df_slice)
    hours = np.arange(n) / STEPS_PER_HOUR
    hour_of_day = hours % 24
    scheduled = build_scheduled_array(basal_schedule, hour_of_day)
    actual = compute_actual_delivery(df_slice, scheduled)
    valid = ~np.isnan(actual) & (scheduled > 0)
    return compute_delivery_ratio_sum(actual, scheduled, valid)


def estimate_isf(df_slice, isf_schedule):
    """Estimate effective ISF from correction boluses (vectorized)."""
    glucose = df_slice['glucose'].values.astype(np.float64)
    bolus = df_slice['bolus'].values.astype(np.float64) if 'bolus' in df_slice.columns else None
    carbs = df_slice['carbs'].values.astype(np.float64) if 'carbs' in df_slice.columns else np.zeros(len(glucose))
    n = len(glucose)
    if bolus is None or n < STEPS_PER_HOUR * 4:
        return None, 0

    # Vectorized candidate filtering
    valid_range = np.zeros(n, dtype=bool)
    valid_range[STEPS_PER_HOUR:n - STEPS_PER_HOUR * 4] = True
    has_bolus = ~np.isnan(bolus) & (bolus >= 0.1)
    has_glucose = ~np.isnan(glucose) & (glucose >= 120)
    candidates = np.where(valid_range & has_bolus & has_glucose)[0]

    if len(candidates) == 0:
        return None, 0

    # Carb window check via cumsum
    carbs_safe = np.where(np.isnan(carbs), 0, carbs)
    carb_cumsum = np.cumsum(carbs_safe)

    isf_vals = []
    for i in candidates:
        lo = max(0, i - 6)
        hi = min(i + 6, n)
        c_sum = carb_cumsum[hi - 1] - (carb_cumsum[lo - 1] if lo > 0 else 0)
        if c_sum > 1:
            continue
        g3h_idx = min(i + STEPS_PER_HOUR * 3, n - 1)
        if np.isnan(glucose[g3h_idx]):
            continue
        isf_eff = (glucose[i] - glucose[g3h_idx]) / bolus[i]
        if isf_eff > 0:
            isf_vals.append(isf_eff)

    if len(isf_vals) < 3:
        return None, len(isf_vals)

    profile_isf = get_schedule_value(isf_schedule, 12)
    if profile_isf and profile_isf < 15:
        profile_isf *= 18.0182

    median_isf = float(np.median(isf_vals))
    ratio = median_isf / profile_isf if profile_isf and profile_isf > 0 else None
    return ratio, len(isf_vals)


def estimate_cr(df_slice, cr_schedule):
    """Estimate effective CR from meal responses (vectorized)."""
    glucose = df_slice['glucose'].values.astype(np.float64)
    bolus = df_slice['bolus'].values.astype(np.float64) if 'bolus' in df_slice.columns else None
    carbs = df_slice['carbs'].values.astype(np.float64) if 'carbs' in df_slice.columns else None
    n = len(glucose)
    if bolus is None or carbs is None or n < STEPS_PER_HOUR * 4:
        return None, 0

    # Vectorized candidate filtering
    valid_range = np.zeros(n, dtype=bool)
    valid_range[:n - STEPS_PER_HOUR * 4] = True
    has_carbs = ~np.isnan(carbs) & (carbs >= 10)
    has_glucose = ~np.isnan(glucose)
    candidates = np.where(valid_range & has_carbs & has_glucose)[0]

    if len(candidates) == 0:
        return None, 0

    # Bolus cumsum for window queries
    bolus_safe = np.where(np.isnan(bolus), 0, bolus)
    bolus_cumsum = np.cumsum(bolus_safe)

    cr_vals = []
    for i in candidates:
        lo = max(0, i - 6)
        hi = min(i + 6, n)
        total_bolus = bolus_cumsum[hi - 1] - (bolus_cumsum[lo - 1] if lo > 0 else 0)
        if total_bolus < 0.5:
            continue
        g2h_idx = min(i + STEPS_PER_HOUR * 2, n - 1)
        if np.isnan(glucose[g2h_idx]):
            continue
        cr_eff = carbs[i] / total_bolus
        if 2 < cr_eff < 50:
            cr_vals.append(cr_eff)

    if len(cr_vals) < 5:
        return None, len(cr_vals)

    profile_cr = get_schedule_value(cr_schedule, 12)
    median_cr = float(np.median(cr_vals))
    ratio = median_cr / profile_cr if profile_cr and profile_cr > 0 else None
    return ratio, len(cr_vals)


def estimate_all(df_slice, attrs):
    """Estimate all therapy parameters from a data slice."""
    basal_sched = attrs.get('basal_schedule', [])
    isf_sched = attrs.get('isf_schedule', [])
    cr_sched = attrs.get('cr_schedule', [])

    dr = estimate_basal_dr(df_slice, basal_sched)
    isf_ratio, n_isf = estimate_isf(df_slice, isf_sched)
    cr_ratio, n_cr = estimate_cr(df_slice, cr_sched)

    glucose = df_slice['glucose'].values
    tir, tbr, tar = compute_tir_tbr_tar(glucose)

    return {
        'delivery_ratio': round(dr, 3),
        'isf_ratio': round(isf_ratio, 2) if isf_ratio else None,
        'n_isf_corrections': n_isf,
        'cr_ratio': round(cr_ratio, 2) if cr_ratio else None,
        'n_cr_meals': n_cr,
        'tir': round(tir, 1),
        'tbr': round(tbr, 1),
        'tar': round(tar, 1),
    }


# ─────────────────────────────────────────────────────────────────
# EXP-2251: Temporal Split Validation
# ─────────────────────────────────────────────────────────────────
def exp_2251_temporal_split(patients):
    """Train on first half, test on second half. Compare estimates."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        mid = n // 2
        attrs = df.attrs

        first_half = df.iloc[:mid].copy()
        first_half.attrs = attrs
        second_half = df.iloc[mid:].copy()
        second_half.attrs = attrs
        full = df.copy()
        full.attrs = attrs

        est_first = estimate_all(first_half, attrs)
        est_second = estimate_all(second_half, attrs)
        est_full = estimate_all(full, attrs)

        # Compute agreement metrics
        dr_diff = abs(est_first['delivery_ratio'] - est_second['delivery_ratio'])
        isf_agree = None
        if est_first['isf_ratio'] and est_second['isf_ratio']:
            isf_agree = abs(est_first['isf_ratio'] - est_second['isf_ratio'])
        cr_agree = None
        if est_first['cr_ratio'] and est_second['cr_ratio']:
            cr_agree = abs(est_first['cr_ratio'] - est_second['cr_ratio'])

        results[name] = {
            'first_half': est_first,
            'second_half': est_second,
            'full': est_full,
            'days_per_half': round(mid / STEPS_PER_DAY, 0),
            'dr_agreement': round(dr_diff, 3),
            'isf_agreement': round(isf_agree, 2) if isf_agree is not None else None,
            'cr_agreement': round(cr_agree, 2) if cr_agree is not None else None,
            'stable': dr_diff < 0.3 and (isf_agree is None or isf_agree < 0.5),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2252: Rolling Window Convergence
# ─────────────────────────────────────────────────────────────────
def exp_2252_convergence(patients):
    """How quickly do estimates stabilize as more data accumulates?"""
    results = {}
    windows_days = [7, 14, 30, 60, 90, 120, 150, 180]

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs
        max_days = n / STEPS_PER_DAY

        trajectory = []
        for days in windows_days:
            steps = min(int(days * STEPS_PER_DAY), n)
            if steps < STEPS_PER_DAY:
                continue
            slice_df = df.iloc[:steps].copy()
            slice_df.attrs = attrs
            est = estimate_all(slice_df, attrs)
            est['days'] = days if days <= max_days else round(max_days, 0)
            trajectory.append(est)

        # Compute convergence: when does DR stabilize within 10%?
        final_dr = trajectory[-1]['delivery_ratio'] if trajectory else None
        converged_day = None
        for t in trajectory:
            if final_dr and final_dr > 0:
                if abs(t['delivery_ratio'] - final_dr) / max(final_dr, 0.01) < 0.10:
                    converged_day = t['days']
                    break

        # ISF convergence
        final_isf = trajectory[-1]['isf_ratio'] if trajectory and trajectory[-1]['isf_ratio'] else None
        isf_converged = None
        for t in trajectory:
            if final_isf and t['isf_ratio']:
                if abs(t['isf_ratio'] - final_isf) / max(final_isf, 0.01) < 0.10:
                    isf_converged = t['days']
                    break

        results[name] = {
            'trajectory': trajectory,
            'dr_converged_days': converged_day,
            'isf_converged_days': isf_converged,
            'final_dr': final_dr,
            'final_isf_ratio': final_isf,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2253: Bootstrap Confidence Intervals
# ─────────────────────────────────────────────────────────────────
def exp_2253_bootstrap_ci(patients, n_bootstrap=200):
    """Bootstrap CIs by resampling correction-level results (fast)."""
    results = {}
    rng = np.random.RandomState(42)

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs
        n_days = int(n / STEPS_PER_DAY)

        # Pre-compute per-day delivery ratios
        basal_sched = attrs.get('basal_schedule', [])
        hours_arr = np.arange(n) / STEPS_PER_HOUR
        hod = hours_arr % 24
        scheduled = build_scheduled_array(basal_sched, hod)
        actual = compute_actual_delivery(df, scheduled)
        day_dr = []
        for d in range(n_days):
            s = d * STEPS_PER_DAY
            e = min(s + STEPS_PER_DAY, n)
            sched_d = scheduled[s:e]
            act_d = actual[s:e]
            valid = ~np.isnan(act_d) & (sched_d > 0)
            if valid.sum() > 0:
                day_dr.append(float(np.sum(act_d[valid]) / np.sum(sched_d[valid])))
            else:
                day_dr.append(np.nan)
        day_dr = np.array(day_dr)

        # Pre-compute all ISF values
        glucose = df['glucose'].values.astype(np.float64)
        bolus = df['bolus'].values.astype(np.float64) if 'bolus' in df.columns else None
        carbs_arr = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(n)
        isf_day_map = {}  # day -> list of ISF values
        cr_day_map = {}   # day -> list of CR values

        if bolus is not None:
            carbs_safe = np.where(np.isnan(carbs_arr), 0, carbs_arr)
            carb_cs = np.cumsum(carbs_safe)
            bolus_safe = np.where(np.isnan(bolus), 0, bolus)
            bolus_cs = np.cumsum(bolus_safe)

            # ISF corrections
            valid_range = np.zeros(n, dtype=bool)
            valid_range[STEPS_PER_HOUR:n - STEPS_PER_HOUR * 4] = True
            has_bolus = ~np.isnan(bolus) & (bolus >= 0.1)
            has_glucose = ~np.isnan(glucose) & (glucose >= 120)
            isf_cands = np.where(valid_range & has_bolus & has_glucose)[0]

            for i in isf_cands:
                lo = max(0, i - 6)
                hi = min(i + 6, n)
                c_sum = carb_cs[hi - 1] - (carb_cs[lo - 1] if lo > 0 else 0)
                if c_sum > 1:
                    continue
                g3h = glucose[min(i + STEPS_PER_HOUR * 3, n - 1)]
                if np.isnan(g3h):
                    continue
                isf_eff = (glucose[i] - g3h) / bolus[i]
                if isf_eff > 0:
                    day = i // STEPS_PER_DAY
                    isf_day_map.setdefault(day, []).append(isf_eff)

            # CR meals
            cr_range = np.zeros(n, dtype=bool)
            cr_range[:n - STEPS_PER_HOUR * 4] = True
            has_carbs = ~np.isnan(carbs_arr) & (carbs_arr >= 10)
            cr_cands = np.where(cr_range & has_carbs & ~np.isnan(glucose))[0]

            for i in cr_cands:
                lo = max(0, i - 6)
                hi = min(i + 6, n)
                tb = bolus_cs[hi - 1] - (bolus_cs[lo - 1] if lo > 0 else 0)
                if tb < 0.5:
                    continue
                g2h = glucose[min(i + STEPS_PER_HOUR * 2, n - 1)]
                if np.isnan(g2h):
                    continue
                cr_eff = carbs_arr[i] / tb
                if 2 < cr_eff < 50:
                    day = i // STEPS_PER_DAY
                    cr_day_map.setdefault(day, []).append(cr_eff)

        # Now bootstrap by resampling days
        dr_samples = []
        isf_samples = []
        cr_samples = []

        valid_dr_days = np.where(~np.isnan(day_dr))[0]
        all_days = np.arange(n_days)

        for _ in range(n_bootstrap):
            boot_days = rng.choice(all_days, size=n_days, replace=True)

            # DR: weighted sum of resampled days
            boot_dr_vals = day_dr[boot_days]
            valid_boot = ~np.isnan(boot_dr_vals)
            if valid_boot.sum() > 0:
                dr_samples.append(float(np.mean(boot_dr_vals[valid_boot])))

            # ISF: collect all ISF vals from resampled days
            boot_isf = []
            for d in boot_days:
                boot_isf.extend(isf_day_map.get(int(d), []))
            if len(boot_isf) >= 3:
                isf_samples.append(float(np.median(boot_isf)))

            # CR: collect all CR vals from resampled days
            boot_cr = []
            for d in boot_days:
                boot_cr.extend(cr_day_map.get(int(d), []))
            if len(boot_cr) >= 5:
                cr_samples.append(float(np.median(boot_cr)))

        # Compute CIs
        def ci(samples, level=0.95):
            if len(samples) < 10:
                return None, None, None
            arr = np.array(samples)
            lo = np.percentile(arr, (1 - level) / 2 * 100)
            hi = np.percentile(arr, (1 + level) / 2 * 100)
            return round(float(np.median(arr)), 3), round(float(lo), 3), round(float(hi), 3)

        # ISF ratio CI (relative to profile)
        profile_isf = get_schedule_value(attrs.get('isf_schedule', []), 12)
        if profile_isf and profile_isf < 15:
            profile_isf *= 18.0182
        isf_ratio_samples = [s / profile_isf for s in isf_samples] if profile_isf and profile_isf > 0 else []

        dr_med, dr_lo, dr_hi = ci(dr_samples)
        isf_med, isf_lo, isf_hi = ci(isf_ratio_samples)

        # CR ratio CI
        profile_cr = get_schedule_value(attrs.get('cr_schedule', []), 12)
        cr_ratio_samples = [s / profile_cr for s in cr_samples] if profile_cr and profile_cr > 0 else []
        cr_med, cr_lo, cr_hi = ci(cr_ratio_samples)

        results[name] = {
            'dr': {'median': dr_med, 'ci_lo': dr_lo, 'ci_hi': dr_hi,
                   'width': round(dr_hi - dr_lo, 3) if dr_lo is not None else None},
            'isf_ratio': {'median': isf_med, 'ci_lo': isf_lo, 'ci_hi': isf_hi,
                          'width': round(isf_hi - isf_lo, 2) if isf_lo is not None else None},
            'cr_ratio': {'median': cr_med, 'ci_lo': cr_lo, 'ci_hi': cr_hi,
                         'width': round(cr_hi - cr_lo, 2) if cr_lo is not None else None},
            'n_bootstrap': n_bootstrap,
            'n_isf_corrections': sum(len(v) for v in isf_day_map.values()),
            'n_cr_meals': sum(len(v) for v in cr_day_map.values()),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2254: Minimum Data Requirements
# ─────────────────────────────────────────────────────────────────
def exp_2254_minimum_data(patients):
    """How many days of data are needed for reliable estimates?"""
    results = {}
    test_days = [3, 5, 7, 10, 14, 21, 30, 45, 60, 90]
    n_trials = 10
    rng = np.random.RandomState(123)

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs
        max_days = int(n / STEPS_PER_DAY)

        # Full-data estimate as reference
        full_est = estimate_all(df.copy(), attrs)

        requirements = []
        for days in test_days:
            if days > max_days - 7:
                continue
            steps = days * STEPS_PER_DAY
            dr_errors = []
            isf_errors = []

            for _ in range(n_trials):
                start = rng.randint(0, max(1, n - steps))
                slice_df = df.iloc[start:start + steps].copy()
                slice_df.attrs = attrs
                est = estimate_all(slice_df, attrs)

                if full_est['delivery_ratio'] > 0:
                    dr_err = abs(est['delivery_ratio'] - full_est['delivery_ratio']) / max(full_est['delivery_ratio'], 0.01)
                    dr_errors.append(dr_err)
                if est['isf_ratio'] and full_est['isf_ratio']:
                    isf_err = abs(est['isf_ratio'] - full_est['isf_ratio']) / max(full_est['isf_ratio'], 0.01)
                    isf_errors.append(isf_err)

            requirements.append({
                'days': days,
                'dr_median_error': round(float(np.median(dr_errors)), 3) if dr_errors else None,
                'dr_p90_error': round(float(np.percentile(dr_errors, 90)), 3) if dr_errors else None,
                'isf_median_error': round(float(np.median(isf_errors)), 3) if isf_errors else None,
                'isf_p90_error': round(float(np.percentile(isf_errors, 90)), 3) if isf_errors else None,
                'n_dr_trials': len(dr_errors),
                'n_isf_trials': len(isf_errors),
            })

        # Find minimum days for <10% error
        min_dr_days = None
        min_isf_days = None
        for req in requirements:
            if req['dr_p90_error'] is not None and req['dr_p90_error'] < 0.10 and min_dr_days is None:
                min_dr_days = req['days']
            if req['isf_p90_error'] is not None and req['isf_p90_error'] < 0.10 and min_isf_days is None:
                min_isf_days = req['days']

        results[name] = {
            'requirements': requirements,
            'min_dr_days': min_dr_days,
            'min_isf_days': min_isf_days,
            'full_dr': full_est['delivery_ratio'],
            'full_isf_ratio': full_est['isf_ratio'],
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2255: Cross-Patient Transferability
# ─────────────────────────────────────────────────────────────────
def exp_2255_cross_patient(patients):
    """Can population-level thresholds identify miscalibrated settings?"""
    results = {}

    # First, compute per-patient estimates
    all_estimates = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        attrs = df.attrs
        est = estimate_all(df.copy(), attrs)
        all_estimates[name] = est

    # Population statistics
    drs = [e['delivery_ratio'] for e in all_estimates.values()]
    isf_ratios = [e['isf_ratio'] for e in all_estimates.values() if e['isf_ratio']]
    cr_ratios = [e['cr_ratio'] for e in all_estimates.values() if e['cr_ratio']]

    pop_dr_median = float(np.median(drs))
    pop_isf_median = float(np.median(isf_ratios)) if isf_ratios else None
    pop_cr_median = float(np.median(cr_ratios)) if cr_ratios else None

    # For each patient, test if population threshold identifies their issue
    for pat in patients:
        name = pat['name']
        est = all_estimates[name]

        # Thresholds for "miscalibrated"
        basal_flag = est['delivery_ratio'] < 0.5 or est['delivery_ratio'] > 1.5
        isf_flag = est['isf_ratio'] is not None and (est['isf_ratio'] > 1.5 or est['isf_ratio'] < 0.7)
        cr_flag = est['cr_ratio'] is not None and (est['cr_ratio'] > 1.3 or est['cr_ratio'] < 0.7)

        # Check against TBR (ground truth proxy)
        high_tbr = est['tbr'] > 4.0

        results[name] = {
            'estimates': est,
            'basal_flagged': basal_flag,
            'isf_flagged': isf_flag,
            'cr_flagged': cr_flag,
            'any_flagged': basal_flag or isf_flag or cr_flag,
            'high_tbr': high_tbr,
            'correct_flag': (basal_flag or isf_flag or cr_flag) == high_tbr,
        }

    # Population summary
    n_flagged = sum(1 for r in results.values() if r['any_flagged'])
    n_correct = sum(1 for r in results.values() if r['correct_flag'])
    results['_population'] = {
        'dr_median': round(pop_dr_median, 3),
        'isf_ratio_median': round(pop_isf_median, 2) if pop_isf_median else None,
        'cr_ratio_median': round(pop_cr_median, 2) if pop_cr_median else None,
        'n_flagged': n_flagged,
        'n_correct': n_correct,
        'accuracy': round(n_correct / len(patients), 2),
    }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2256: Settings Change Detection
# ─────────────────────────────────────────────────────────────────
def exp_2256_change_detection(patients):
    """Can we detect simulated settings changes from data?"""
    results = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs

        # Split into 30-day windows and compute estimates
        window_size = 30 * STEPS_PER_DAY
        windows = []
        for start in range(0, n - window_size + 1, window_size):
            end = start + window_size
            slice_df = df.iloc[start:end].copy()
            slice_df.attrs = attrs
            est = estimate_all(slice_df, attrs)
            est['start_day'] = round(start / STEPS_PER_DAY, 0)
            est['end_day'] = round(end / STEPS_PER_DAY, 0)
            windows.append(est)

        if len(windows) < 2:
            results[name] = {'skip': True, 'reason': 'insufficient data for windows'}
            continue

        # Detect changes between consecutive windows
        changes = []
        for i in range(1, len(windows)):
            prev = windows[i - 1]
            curr = windows[i]
            dr_change = curr['delivery_ratio'] - prev['delivery_ratio']
            isf_change = None
            if curr['isf_ratio'] and prev['isf_ratio']:
                isf_change = curr['isf_ratio'] - prev['isf_ratio']

            significant = abs(dr_change) > 0.2 or (isf_change is not None and abs(isf_change) > 0.3)
            changes.append({
                'window': i,
                'dr_change': round(dr_change, 3),
                'isf_change': round(isf_change, 2) if isf_change is not None else None,
                'significant': significant,
            })

        # Overall stability
        dr_values = [w['delivery_ratio'] for w in windows]
        dr_cv = float(np.std(dr_values) / max(np.mean(dr_values), 0.01)) if dr_values else None

        results[name] = {
            'windows': windows,
            'changes': changes,
            'n_significant_changes': sum(1 for c in changes if c['significant']),
            'dr_cv': round(dr_cv, 3) if dr_cv is not None else None,
            'stable': all(not c['significant'] for c in changes),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2257: Weekly Stability Assessment
# ─────────────────────────────────────────────────────────────────
def exp_2257_weekly_stability(patients):
    """Week-to-week variability of therapy estimates."""
    results = {}
    week_steps = 7 * STEPS_PER_DAY

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs

        weekly_dr = []
        weekly_tir = []
        weekly_tbr = []
        weekly_isf = []

        for start in range(0, n - week_steps + 1, week_steps):
            end = start + week_steps
            slice_df = df.iloc[start:end].copy()
            slice_df.attrs = attrs
            est = estimate_all(slice_df, attrs)
            weekly_dr.append(est['delivery_ratio'])
            weekly_tir.append(est['tir'])
            weekly_tbr.append(est['tbr'])
            if est['isf_ratio'] is not None:
                weekly_isf.append(est['isf_ratio'])

        n_weeks = len(weekly_dr)

        # Compute variability metrics
        dr_arr = np.array(weekly_dr)
        tir_arr = np.array(weekly_tir)
        tbr_arr = np.array(weekly_tbr)

        results[name] = {
            'n_weeks': n_weeks,
            'dr_mean': round(float(np.mean(dr_arr)), 3),
            'dr_std': round(float(np.std(dr_arr)), 3),
            'dr_cv': round(float(np.std(dr_arr) / max(np.mean(dr_arr), 0.01)), 3),
            'dr_range': [round(float(np.min(dr_arr)), 3), round(float(np.max(dr_arr)), 3)],
            'tir_mean': round(float(np.mean(tir_arr)), 1),
            'tir_std': round(float(np.std(tir_arr)), 1),
            'tbr_mean': round(float(np.mean(tbr_arr)), 1),
            'tbr_std': round(float(np.std(tbr_arr)), 1),
            'isf_cv': round(float(np.std(weekly_isf) / max(np.mean(weekly_isf), 0.01)), 3) if len(weekly_isf) >= 3 else None,
            'worst_week_tir': round(float(np.min(tir_arr)), 1),
            'best_week_tir': round(float(np.max(tir_arr)), 1),
            'weekly_dr': [round(float(x), 3) for x in weekly_dr],
            'weekly_tir': [round(float(x), 1) for x in weekly_tir],
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2258: Production Readiness Scorecard
# ─────────────────────────────────────────────────────────────────
def exp_2258_readiness_scorecard(patients, all_results):
    """Composite pass/fail for production deployment."""
    results = {}

    for pat in patients:
        name = pat['name']
        checks = {}

        # Check 1: Temporal stability (from EXP-2251)
        split = all_results.get('exp_2251', {}).get(name, {})
        checks['temporal_stable'] = split.get('stable', False)

        # Check 2: Sufficient data (from EXP-2254)
        mindata = all_results.get('exp_2254', {}).get(name, {})
        min_dr = mindata.get('min_dr_days')
        checks['dr_converges'] = min_dr is not None and min_dr <= 30

        # Check 3: Narrow CI (from EXP-2253)
        boot = all_results.get('exp_2253', {}).get(name, {})
        dr_ci = boot.get('dr', {})
        checks['dr_ci_narrow'] = dr_ci.get('width') is not None and dr_ci.get('width') < 0.5

        # Check 4: ISF estimable
        isf_ci = boot.get('isf_ratio', {})
        checks['isf_estimable'] = isf_ci.get('median') is not None

        # Check 5: Weekly stability (from EXP-2257)
        weekly = all_results.get('exp_2257', {}).get(name, {})
        checks['weekly_cv_ok'] = weekly.get('dr_cv') is not None and weekly.get('dr_cv') < 1.0

        # Check 6: 30-day window stability (from EXP-2256)
        change = all_results.get('exp_2256', {}).get(name, {})
        checks['no_drift'] = change.get('stable', False)

        # Check 7: Convergence speed (from EXP-2252)
        conv = all_results.get('exp_2252', {}).get(name, {})
        checks['fast_convergence'] = conv.get('dr_converged_days') is not None and conv.get('dr_converged_days') <= 30

        # Composite score
        n_pass = sum(1 for v in checks.values() if v)
        n_total = len(checks)
        score = round(n_pass / n_total * 100, 0)

        results[name] = {
            'checks': checks,
            'n_pass': n_pass,
            'n_total': n_total,
            'score': score,
            'production_ready': score >= 70,  # 5/7 checks pass
        }

    # Population summary
    n_ready = sum(1 for r in results.values() if isinstance(r, dict) and r.get('production_ready'))
    results['_summary'] = {
        'n_ready': n_ready,
        'n_total': len(patients),
        'readiness_rate': round(n_ready / len(patients) * 100, 0),
    }
    return results


# ─────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────
def generate_figures(all_results, fig_dir):
    """Generate 8 figures for the cross-validation experiments."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(fig_dir, exist_ok=True)
    patients_list = sorted([k for k in all_results.get('exp_2251', {}).keys() if not k.startswith('_')])

    # ── Figure 1: Temporal Split Agreement ──
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    split = all_results['exp_2251']

    # DR agreement
    ax = axes[0]
    names = []
    first_dr = []
    second_dr = []
    for n in patients_list:
        r = split[n]
        names.append(n)
        first_dr.append(r['first_half']['delivery_ratio'])
        second_dr.append(r['second_half']['delivery_ratio'])
    x = np.arange(len(names))
    ax.bar(x - 0.15, first_dr, 0.3, label='First half', color='steelblue')
    ax.bar(x + 0.15, second_dr, 0.3, label='Second half', color='coral')
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('Basal DR: First vs Second Half')
    ax.legend()

    # ISF agreement
    ax = axes[1]
    first_isf = []
    second_isf = []
    isf_names = []
    for n in patients_list:
        r = split[n]
        f = r['first_half']['isf_ratio']
        s = r['second_half']['isf_ratio']
        if f is not None and s is not None:
            isf_names.append(n)
            first_isf.append(f)
            second_isf.append(s)
    x = np.arange(len(isf_names))
    ax.bar(x - 0.15, first_isf, 0.3, label='First half', color='steelblue')
    ax.bar(x + 0.15, second_isf, 0.3, label='Second half', color='coral')
    ax.set_xticks(x)
    ax.set_xticklabels(isf_names)
    ax.set_ylabel('ISF Ratio (effective/profile)')
    ax.set_title('ISF Ratio: First vs Second Half')
    ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
    ax.legend()

    # Stability flags
    ax = axes[2]
    stable = [1 if split[n]['stable'] else 0 for n in patients_list]
    colors = ['green' if s else 'red' for s in stable]
    ax.bar(range(len(patients_list)), stable, color=colors)
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Stable (1=yes)')
    ax.set_title('Temporal Stability')
    ax.set_ylim(0, 1.2)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig01-temporal-split.png'), dpi=150)
    plt.close()
    print('  Figure 1: temporal split')

    # ── Figure 2: Convergence Trajectories ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    conv = all_results['exp_2252']

    ax = axes[0]
    for n in patients_list:
        r = conv[n]
        traj = r['trajectory']
        days = [t['days'] for t in traj]
        drs = [t['delivery_ratio'] for t in traj]
        ax.plot(days, drs, 'o-', label=n, markersize=4)
    ax.set_xlabel('Days of data')
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('DR Convergence')
    ax.legend(fontsize=7, ncol=2)
    ax.set_xscale('log')

    ax = axes[1]
    for n in patients_list:
        r = conv[n]
        traj = r['trajectory']
        days = [t['days'] for t in traj if t['isf_ratio'] is not None]
        isfs = [t['isf_ratio'] for t in traj if t['isf_ratio'] is not None]
        if isfs:
            ax.plot(days, isfs, 'o-', label=n, markersize=4)
    ax.set_xlabel('Days of data')
    ax.set_ylabel('ISF Ratio')
    ax.set_title('ISF Convergence')
    ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
    ax.legend(fontsize=7, ncol=2)
    ax.set_xscale('log')

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig02-convergence.png'), dpi=150)
    plt.close()
    print('  Figure 2: convergence')

    # ── Figure 3: Bootstrap CIs ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    boot = all_results['exp_2253']

    ax = axes[0]
    for idx, n in enumerate(patients_list):
        r = boot[n]
        dr = r['dr']
        if dr['median'] is not None:
            ax.errorbar(idx, dr['median'],
                        yerr=[[dr['median'] - dr['ci_lo']], [dr['ci_hi'] - dr['median']]],
                        fmt='o', capsize=4, color='steelblue')
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('DR: Bootstrap 95% CI')

    ax = axes[1]
    isf_idx = 0
    isf_labels = []
    for n in patients_list:
        r = boot[n]
        isf = r['isf_ratio']
        if isf['median'] is not None:
            ax.errorbar(isf_idx, isf['median'],
                        yerr=[[isf['median'] - isf['ci_lo']], [isf['ci_hi'] - isf['median']]],
                        fmt='o', capsize=4, color='coral')
            isf_labels.append(n)
            isf_idx += 1
    ax.set_xticks(range(len(isf_labels)))
    ax.set_xticklabels(isf_labels)
    ax.set_ylabel('ISF Ratio')
    ax.set_title('ISF Ratio: Bootstrap 95% CI')
    ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig03-bootstrap-ci.png'), dpi=150)
    plt.close()
    print('  Figure 3: bootstrap CI')

    # ── Figure 4: Minimum Data Requirements ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    mindata = all_results['exp_2254']

    ax = axes[0]
    for n in patients_list:
        r = mindata[n]
        reqs = r['requirements']
        days = [rq['days'] for rq in reqs if rq['dr_median_error'] is not None]
        errs = [rq['dr_median_error'] for rq in reqs if rq['dr_median_error'] is not None]
        if errs:
            ax.plot(days, errs, 'o-', label=n, markersize=4)
    ax.axhline(y=0.10, color='red', linestyle='--', alpha=0.7, label='10% threshold')
    ax.set_xlabel('Days of data')
    ax.set_ylabel('Median relative error')
    ax.set_title('DR: Error vs Data Quantity')
    ax.legend(fontsize=7, ncol=2)
    ax.set_ylim(0, 1.0)

    ax = axes[1]
    for n in patients_list:
        r = mindata[n]
        reqs = r['requirements']
        days = [rq['days'] for rq in reqs if rq['isf_median_error'] is not None]
        errs = [rq['isf_median_error'] for rq in reqs if rq['isf_median_error'] is not None]
        if errs:
            ax.plot(days, errs, 'o-', label=n, markersize=4)
    ax.axhline(y=0.10, color='red', linestyle='--', alpha=0.7, label='10% threshold')
    ax.set_xlabel('Days of data')
    ax.set_ylabel('Median relative error')
    ax.set_title('ISF: Error vs Data Quantity')
    ax.legend(fontsize=7, ncol=2)
    ax.set_ylim(0, 1.0)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig04-minimum-data.png'), dpi=150)
    plt.close()
    print('  Figure 4: minimum data')

    # ── Figure 5: Cross-Patient Transferability ──
    fig, ax = plt.subplots(figsize=(10, 5))
    xpat = all_results['exp_2255']

    categories = ['basal_flagged', 'isf_flagged', 'cr_flagged', 'high_tbr']
    cat_labels = ['Basal Flag', 'ISF Flag', 'CR Flag', 'High TBR']
    bar_width = 0.18
    x = np.arange(len(patients_list))
    for ci, cat in enumerate(categories):
        vals = [1 if xpat.get(n, {}).get(cat, False) else 0 for n in patients_list]
        ax.bar(x + ci * bar_width, vals, bar_width, label=cat_labels[ci])
    ax.set_xticks(x + bar_width * 1.5)
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Flagged (1=yes)')
    ax.set_title('Cross-Patient: Settings Flags vs High TBR')
    ax.legend()
    ax.set_ylim(0, 1.3)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig05-cross-patient.png'), dpi=150)
    plt.close()
    print('  Figure 5: cross-patient')

    # ── Figure 6: 30-Day Change Detection ──
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    change = all_results['exp_2256']

    ax = axes[0]
    for n in patients_list:
        r = change.get(n, {})
        if r.get('skip'):
            continue
        wins = r.get('windows', [])
        days = [w['start_day'] for w in wins]
        drs = [w['delivery_ratio'] for w in wins]
        ax.plot(days, drs, 'o-', label=n, markersize=5)
    ax.set_xlabel('Start day')
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('30-Day Window DR Over Time')
    ax.legend(fontsize=7, ncol=3)

    ax = axes[1]
    stable_patients = sum(1 for n in patients_list if change.get(n, {}).get('stable', False))
    unstable = len(patients_list) - stable_patients
    ax.bar(['Stable', 'Unstable'], [stable_patients, unstable], color=['green', 'red'])
    ax.set_ylabel('# Patients')
    ax.set_title(f'30-Day Stability: {stable_patients}/{len(patients_list)} stable')

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig06-change-detection.png'), dpi=150)
    plt.close()
    print('  Figure 6: change detection')

    # ── Figure 7: Weekly Variability ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    weekly = all_results['exp_2257']

    ax = axes[0]
    for n in patients_list:
        r = weekly[n]
        wdr = r['weekly_dr']
        ax.plot(range(len(wdr)), wdr, 'o-', label=n, markersize=3, alpha=0.7)
    ax.set_xlabel('Week #')
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('Weekly DR Trajectory')
    ax.legend(fontsize=7, ncol=2)

    ax = axes[1]
    cvs = [weekly[n]['dr_cv'] for n in patients_list]
    colors = ['green' if cv < 0.5 else 'orange' if cv < 1.0 else 'red' for cv in cvs]
    ax.bar(range(len(patients_list)), cvs, color=colors)
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('CV (σ/μ)')
    ax.set_title('Weekly DR Coefficient of Variation')
    ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.5, label='CV=1.0 threshold')
    ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig07-weekly-variability.png'), dpi=150)
    plt.close()
    print('  Figure 7: weekly variability')

    # ── Figure 8: Production Readiness Scorecard ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    scorecard = all_results['exp_2258']

    ax = axes[0]
    scores = [scorecard[n]['score'] for n in patients_list]
    ready = [scorecard[n]['production_ready'] for n in patients_list]
    colors = ['green' if r else 'red' for r in ready]
    ax.bar(range(len(patients_list)), scores, color=colors)
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Readiness Score (%)')
    ax.set_title('Production Readiness Score')
    ax.axhline(y=70, color='orange', linestyle='--', label='70% threshold')
    ax.legend()

    ax = axes[1]
    check_names = ['temporal_stable', 'dr_converges', 'dr_ci_narrow',
                   'isf_estimable', 'weekly_cv_ok', 'no_drift', 'fast_convergence']
    check_labels = ['Temp.\nStable', 'DR\nConv.', 'DR CI\nNarrow',
                    'ISF\nEstim.', 'Weekly\nCV OK', 'No\nDrift', 'Fast\nConv.']
    heatmap = np.zeros((len(patients_list), len(check_names)))
    for i, n in enumerate(patients_list):
        for j, ck in enumerate(check_names):
            heatmap[i, j] = 1 if scorecard[n]['checks'].get(ck, False) else 0
    im = ax.imshow(heatmap.T, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_yticks(range(len(check_labels)))
    ax.set_yticklabels(check_labels, fontsize=8)
    ax.set_title('Check Matrix (green=pass)')
    for i in range(len(patients_list)):
        for j in range(len(check_names)):
            ax.text(i, j, '✓' if heatmap[i, j] else '✗',
                    ha='center', va='center', fontsize=9,
                    color='white' if heatmap[i, j] else 'black')

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'cv-fig08-readiness-scorecard.png'), dpi=150)
    plt.close()
    print('  Figure 8: readiness scorecard')


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/')
    args = parser.parse_args()

    print('Loading patients...')
    patients = load_patients(args.data_dir)
    print(f'Loaded {len(patients)} patients\n')

    all_results = {}

    experiments = [
        ('exp_2251', 'Temporal Split Validation', exp_2251_temporal_split),
        ('exp_2252', 'Rolling Window Convergence', exp_2252_convergence),
        ('exp_2253', 'Bootstrap Confidence Intervals', exp_2253_bootstrap_ci),
        ('exp_2254', 'Minimum Data Requirements', exp_2254_minimum_data),
        ('exp_2255', 'Cross-Patient Transferability', exp_2255_cross_patient),
        ('exp_2256', 'Settings Change Detection', exp_2256_change_detection),
        ('exp_2257', 'Weekly Stability Assessment', exp_2257_weekly_stability),
    ]

    for key, title, func in experiments:
        print(f'Running {key}: {title}...')
        try:
            result = func(patients)
            all_results[key] = result
            # Quick summary
            n_ok = sum(1 for k, v in result.items()
                       if not k.startswith('_') and isinstance(v, dict)
                       and not v.get('skip'))
            print(f'  ✓ {n_ok} patients processed')
        except Exception as e:
            print(f'  ✗ FAILED: {e}')
            import traceback
            traceback.print_exc()
            all_results[key] = {'error': str(e)}

    # EXP-2258 depends on all previous results
    print('Running exp_2258: Production Readiness Scorecard...')
    try:
        all_results['exp_2258'] = exp_2258_readiness_scorecard(patients, all_results)
        # Print scorecard
        sc = all_results['exp_2258']
        for name in sorted(k for k in sc.keys() if not k.startswith('_')):
            r = sc[name]
            status = '✓ READY' if r['production_ready'] else '✗ NOT READY'
            print(f'  {name}: {r["score"]:.0f}% ({r["n_pass"]}/{r["n_total"]}) {status}')
        summary = sc.get('_summary', {})
        print(f'  Population: {summary.get("n_ready", 0)}/{summary.get("n_total", 0)} ready')
    except Exception as e:
        print(f'  ✗ FAILED: {e}')
        import traceback
        traceback.print_exc()
        all_results['exp_2258'] = {'error': str(e)}

    # Save results
    out_path = 'externals/experiments/exp-2251-2258_crossval.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)
    print(f'\nResults saved to {out_path}')

    if args.figures:
        print('\nGenerating figures...')
        fig_dir = 'docs/60-research/figures'
        generate_figures(all_results, fig_dir)
        print('All figures generated.')


if __name__ == '__main__':
    main()
