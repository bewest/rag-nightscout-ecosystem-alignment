#!/usr/bin/env python3
"""
EXP-1881–1888: Loop-Deconfounded Therapy Estimation

The AID loop masks therapy parameter errors by compensating in real-time.
This batch isolates "true" therapy parameters by accounting for loop behavior.

Key findings motivating this batch:
  - CR is 38% too high (EXP-1874), loop compensates +2.0U (EXP-1876)
  - ISF is dose-dependent (EXP-1856/1861), loop is asymmetric (EXP-1854)
  - Split-loss captures 97% optimal (EXP-1848) but uses profile params
  - Announced meal RMSE 3.4× UAM RMSE (EXP-1877) — wrong CR contaminates

Questions:
  1. How much correction insulin does the loop add? (1881)
  2. What are therapy params in loop-inactive windows? (1882)
  3. Does subtracting loop corrections improve CR estimation? (1883)
  4. Basal rate assessment: scheduled vs actual delivery (1884)
  5. Overnight basal drift with loop-free segments (1885)
  6. Can we estimate "what the loop thinks is wrong"? (1886)
  7. Temporal stability of loop-deconfounded params (1887)
  8. Combined deconfounded therapy assessment (1888)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_loop_deconfound_1881.py [--figures]
"""

import argparse
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

STEPS_PER_HOUR = 12

def get_isf(patient):
    isf = patient['df'].attrs.get('isf_schedule', [{'value': 50}])
    val = isf[0]['value'] if isinstance(isf, list) else 50
    if val < 15:
        val *= 18.0182
    return val

def get_cr(patient):
    cr = patient['df'].attrs.get('cr_schedule', [{'value': 10}])
    return cr[0]['value'] if isinstance(cr, list) else 10

def get_basal(patient):
    basal = patient['df'].attrs.get('basal_schedule', [{'value': 1.0}])
    return basal[0]['value'] if isinstance(basal, list) else 1.0

def supply_demand_loss(sd, glucose, mask=None):
    net = sd['net']
    dg = np.gradient(glucose)
    residual = dg - net
    if mask is not None:
        residual = residual[mask]
    valid = np.isfinite(residual)
    if valid.sum() == 0:
        return np.nan, np.nan, np.nan
    residual = residual[valid]
    supply_resid = np.where(residual > 0, residual ** 2, 0)
    demand_resid = np.where(residual < 0, residual ** 2, 0)
    return np.mean(supply_resid), np.mean(demand_resid), np.mean(residual ** 2)


def find_loop_segments(df, min_length=6):
    """Find segments where loop is active vs inactive based on temp_rate variance.

    Returns dict with 'active' and 'inactive' boolean masks.
    """
    temp_rate = df.get('temp_rate', pd.Series(np.nan, index=df.index)).values
    basal_scheduled = df.get('basal', pd.Series(np.nan, index=df.index)).values

    # Rolling window: 30-min windows
    window = 6
    active = np.zeros(len(df), dtype=bool)
    inactive = np.zeros(len(df), dtype=bool)

    for i in range(window, len(df) - window):
        tr_w = temp_rate[i - window:i + window]
        tr_valid = tr_w[np.isfinite(tr_w)]
        if len(tr_valid) >= window:
            # Active if temp_rate varies meaningfully
            if np.std(tr_valid) > 0.05 or np.any(np.abs(tr_valid - np.nanmedian(temp_rate)) > 0.1):
                active[i] = True
            else:
                inactive[i] = True
        elif len(tr_valid) == 0:
            # No temp rate data = likely no loop
            inactive[i] = True

    return {'active': active, 'inactive': inactive}


def correction_insulin(df):
    """Estimate correction insulin = total insulin - scheduled basal - meal bolus.

    Returns array of correction insulin per step (may be negative = loop reducing).
    """
    temp_rate = df.get('temp_rate', pd.Series(np.nan, index=df.index)).fillna(0).values
    bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
    carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values

    basal_sched = df.attrs.get('basal_schedule', [{'value': 1.0}])
    scheduled_rate = basal_sched[0]['value'] if isinstance(basal_sched, list) else 1.0
    # Convert U/h to U per 5-min step
    scheduled_per_step = scheduled_rate / STEPS_PER_HOUR

    # Temp rate is actual delivery rate
    actual_basal_per_step = temp_rate / STEPS_PER_HOUR

    # Correction basal = (actual - scheduled) per step
    correction_basal = actual_basal_per_step - scheduled_per_step

    # Meal bolus = bolus associated with carbs (within ±30min)
    meal_bolus = np.zeros_like(bolus)
    for i in range(len(bolus)):
        if bolus[i] > 0.1:
            carb_window = carbs[max(0, i - 6):min(i + 6, len(carbs))]
            if np.any(carb_window > 1):
                meal_bolus[i] = bolus[i]

    # Correction bolus = non-meal bolus
    correction_bolus = bolus - meal_bolus

    return {
        'correction_basal': correction_basal,
        'correction_bolus': correction_bolus,
        'meal_bolus': meal_bolus,
        'scheduled_basal': np.full_like(bolus, scheduled_per_step),
        'total_correction': correction_basal + correction_bolus,
    }


# ===========================================================================
# EXP-1881: Loop Correction Insulin Quantification
# ===========================================================================

def exp_1881(patients, figures_dir):
    """Quantify how much correction insulin the AID loop delivers.
    Decompose total insulin into: scheduled basal + meal bolus + loop correction.
    """
    print("=" * 70)
    print("EXP-1881: Loop Correction Insulin Quantification")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()

        ci = correction_insulin(df)
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values

        # Daily totals (steps per day = 288)
        n_days = len(df) / 288
        if n_days < 1:
            continue

        daily_scheduled = np.nansum(ci['scheduled_basal']) / n_days * STEPS_PER_HOUR
        daily_meal = np.nansum(ci['meal_bolus']) / n_days
        daily_correction_basal = np.nansum(ci['correction_basal']) / n_days * STEPS_PER_HOUR
        daily_correction_bolus = np.nansum(ci['correction_bolus']) / n_days
        daily_total = np.nansum(bolus) / n_days + np.nansum(df.get('temp_rate', pd.Series(0, index=df.index)).fillna(0).values) / n_days

        # Fraction of insulin that is correction
        total_daily = daily_scheduled + daily_meal + daily_correction_basal + daily_correction_bolus
        correction_frac = (daily_correction_basal + daily_correction_bolus) / max(total_daily, 0.1)

        # Is loop mostly increasing or decreasing?
        cb = ci['correction_basal']
        valid_cb = cb[np.isfinite(cb)]
        increasing_frac = (valid_cb > 0.001).sum() / max(len(valid_cb), 1)
        mean_adjustment = np.nanmean(cb) * STEPS_PER_HOUR  # U/h

        print(f"  {name}: sched_basal={daily_scheduled:.1f}U/d meal={daily_meal:.1f}U/d "
              f"corr_basal={daily_correction_basal:.1f}U/d corr_bolus={daily_correction_bolus:.1f}U/d "
              f"corr_frac={correction_frac:.0%} loop_inc={increasing_frac:.0%}")

        results.append({
            'patient': name,
            'daily_scheduled_basal': round(daily_scheduled, 1),
            'daily_meal_bolus': round(daily_meal, 1),
            'daily_correction_basal': round(daily_correction_basal, 1),
            'daily_correction_bolus': round(daily_correction_bolus, 1),
            'correction_fraction': round(correction_frac, 3),
            'loop_increasing_fraction': round(increasing_frac, 3),
            'mean_adjustment_U_h': round(mean_adjustment, 3),
        })

    valid = [r for r in results]
    mean_corr_frac = np.mean([r['correction_fraction'] for r in valid])
    mean_inc_frac = np.mean([r['loop_increasing_fraction'] for r in valid])

    print(f"\n  Population loop correction:")
    print(f"    Mean correction fraction: {mean_corr_frac:.0%}")
    print(f"    Mean increasing fraction: {mean_inc_frac:.0%}")

    if mean_corr_frac > 0.3:
        verdict = 'HEAVY_LOOP_CORRECTION'
    elif mean_corr_frac > 0.15:
        verdict = 'MODERATE_LOOP_CORRECTION'
    else:
        verdict = 'MINIMAL_LOOP_CORRECTION'

    print(f"\n  ✓ EXP-1881 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        sched = [r['daily_scheduled_basal'] for r in valid]
        meal = [r['daily_meal_bolus'] for r in valid]
        cb = [r['daily_correction_basal'] for r in valid]
        cbx = [r['daily_correction_bolus'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x, sched, label='Scheduled basal', color='#9E9E9E')
        ax.bar(x, meal, bottom=sched, label='Meal bolus', color='#4CAF50')
        ax.bar(x, cb, bottom=[s + m for s, m in zip(sched, meal)],
               label='Loop correction (basal)', color='#FF9800')
        ax.bar(x, cbx, bottom=[s + m + c for s, m, c in zip(sched, meal, cb)],
               label='Correction bolus', color='#F44336')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Daily Insulin (U)')
        ax.set_title('EXP-1881: Insulin Decomposition per Patient')
        ax.legend(fontsize=7)

        ax = axes[1]
        fracs = [r['correction_fraction'] * 100 for r in valid]
        ax.bar(names, fracs, color='#FF9800')
        ax.axhline(30, color='r', linestyle='--', alpha=0.3, label='Heavy correction')
        ax.set_ylabel('Correction Fraction (%)')
        ax.set_title('EXP-1881: How Much Insulin Is Loop Corrections?')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig01-insulin-decomposition.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig01-insulin-decomposition.png")

    return {
        'experiment': 'EXP-1881',
        'title': 'Loop Correction Insulin Quantification',
        'verdict': verdict,
        'mean_correction_fraction': round(mean_corr_frac, 3),
        'mean_increasing_fraction': round(mean_inc_frac, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1882: Therapy Params in Loop-Inactive Windows
# ===========================================================================

def exp_1882(patients, figures_dir):
    """Estimate therapy parameters using ONLY loop-inactive windows.
    These windows show "natural" glucose dynamics without loop correction.
    """
    print("=" * 70)
    print("EXP-1882: Therapy Params in Loop-Inactive Windows")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_base = get_isf(p)

        segments = find_loop_segments(df)
        n_inactive = segments['inactive'].sum()
        n_active = segments['active'].sum()
        inactive_frac = n_inactive / max(n_inactive + n_active, 1)

        if n_inactive < 200:
            print(f"  {name}: insufficient inactive windows ({n_inactive} steps)")
            results.append({
                'patient': name,
                'n_inactive': int(n_inactive),
                'inactive_fraction': round(inactive_frac, 3),
                'skip': True,
            })
            continue

        # Loss in active vs inactive windows
        sd = compute_supply_demand(df)
        _, _, tl_active = supply_demand_loss(sd, glucose, segments['active'])
        _, _, tl_inactive = supply_demand_loss(sd, glucose, segments['inactive'])

        # Optimize ISF for inactive windows only
        scales = np.array([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 2.5, 3.0])
        best_scale = 1.0
        best_loss = tl_inactive

        for s in scales:
            df_s = df.copy()
            df_s.attrs = dict(df.attrs)
            isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_base}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = isf_base * s
            df_s.attrs['isf_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            _, _, tl_s = supply_demand_loss(sd_s, glucose, segments['inactive'])
            if not np.isnan(tl_s) and tl_s < best_loss:
                best_loss = tl_s
                best_scale = s

        print(f"  {name}: inactive={inactive_frac:.0%} ({n_inactive} steps) "
              f"loss_active={tl_active:.1f} loss_inactive={tl_inactive:.1f} "
              f"optimal_ISF_scale={best_scale:.2f}×")

        results.append({
            'patient': name,
            'n_inactive': int(n_inactive),
            'n_active': int(n_active),
            'inactive_fraction': round(inactive_frac, 3),
            'loss_active': round(float(tl_active), 2) if not np.isnan(tl_active) else None,
            'loss_inactive': round(float(tl_inactive), 2) if not np.isnan(tl_inactive) else None,
            'optimal_isf_scale_inactive': round(best_scale, 2),
            'isf_profile': isf_base,
            'skip': False,
        })

    valid = [r for r in results if not r.get('skip')]
    mean_inactive = np.mean([r['inactive_fraction'] for r in valid]) if valid else 0
    mean_scale = np.mean([r['optimal_isf_scale_inactive'] for r in valid]) if valid else 1

    print(f"\n  Population loop-inactive analysis:")
    print(f"    Mean inactive fraction: {mean_inactive:.0%}")
    print(f"    Mean optimal ISF scale (inactive): {mean_scale:.2f}×")

    if mean_inactive < 0.1:
        verdict = 'INSUFFICIENT_INACTIVE_WINDOWS'
    elif abs(mean_scale - 1.0) > 0.15:
        verdict = 'LOOP_INACTIVE_ISF_DIFFERS'
    else:
        verdict = 'LOOP_INACTIVE_ISF_SIMILAR'

    print(f"\n  ✓ EXP-1882 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        inactive_fracs = [r['inactive_fraction'] * 100 for r in valid]
        ax.bar(names, inactive_fracs, color='#2196F3')
        ax.set_ylabel('Loop-Inactive Time (%)')
        ax.set_title('EXP-1882: How Often Is the Loop Inactive?')

        ax = axes[1]
        isf_scales = [r['optimal_isf_scale_inactive'] for r in valid]
        colors = ['#4CAF50' if abs(s - 1) < 0.15 else '#FF9800' for s in isf_scales]
        ax.bar(names, isf_scales, color=colors)
        ax.axhline(1.0, color='k', linestyle='--', alpha=0.3)
        ax.set_ylabel('Optimal ISF Scale (inactive windows)')
        ax.set_title('EXP-1882: ISF in Loop-Free Windows')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig02-inactive-windows.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig02-inactive-windows.png")

    return {
        'experiment': 'EXP-1882',
        'title': 'Therapy Params in Loop-Inactive Windows',
        'verdict': verdict,
        'mean_inactive_fraction': round(mean_inactive, 3),
        'mean_optimal_isf_scale': round(mean_scale, 2),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1883: Loop-Deconfounded CR
# ===========================================================================

def exp_1883(patients, figures_dir):
    """Subtract loop correction insulin from total insulin at meal time
    to get a "deconfounded" CR estimate. Compare with raw effective CR.
    """
    print("=" * 70)
    print("EXP-1883: Loop-Deconfounded CR Estimation")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)

        glucose = df['glucose'].values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values

        ci = correction_insulin(df)

        # Find meals and compute deconfounded CR
        raw_crs = []
        deconf_crs = []

        for i in range(12, len(glucose) - 36):
            if carbs[i] < 10 or bolus[i] < 0.5:
                continue

            g_pre = glucose[i]
            g_peak = np.nanmax(glucose[i:i + 24])
            if np.isnan(g_pre) or np.isnan(g_peak):
                continue
            excursion = g_peak - g_pre
            if excursion <= 0:
                continue

            # Raw CR: carbs / bolus
            raw_cr = carbs[i] / bolus[i]
            raw_crs.append(raw_cr)

            # Loop correction in 3h post-meal window
            corr_window = ci['total_correction'][i:min(i + 36, len(ci['total_correction']))]
            total_corr = np.nansum(corr_window) * STEPS_PER_HOUR  # U
            # Deconfounded bolus = meal bolus only (without loop adding/subtracting)
            meal_only_insulin = bolus[i]  # just the explicit meal bolus
            total_insulin = bolus[i] + total_corr  # bolus + loop corrections

            if total_insulin > 0.3:
                deconf_cr = carbs[i] / total_insulin
                if 0.5 < deconf_cr < 100:
                    deconf_crs.append(deconf_cr)

        if len(raw_crs) < 15 or len(deconf_crs) < 15:
            print(f"  {name}: insufficient meals (raw={len(raw_crs)}, deconf={len(deconf_crs)})")
            continue

        raw_median = np.median(raw_crs)
        deconf_median = np.median(deconf_crs)
        shift = (deconf_median - raw_median) / raw_median
        mismatch_raw = (raw_median - cr_profile) / cr_profile
        mismatch_deconf = (deconf_median - cr_profile) / cr_profile

        print(f"  {name}: profile={cr_profile:.0f} raw={raw_median:.1f} "
              f"deconf={deconf_median:.1f} shift={shift:+.0%} "
              f"mismatch_raw={mismatch_raw:+.0%} mismatch_deconf={mismatch_deconf:+.0%}")

        results.append({
            'patient': name,
            'cr_profile': cr_profile,
            'cr_raw_median': round(raw_median, 1),
            'cr_deconfounded_median': round(deconf_median, 1),
            'shift': round(shift, 3),
            'mismatch_raw': round(mismatch_raw, 3),
            'mismatch_deconf': round(mismatch_deconf, 3),
            'n_raw': len(raw_crs),
            'n_deconf': len(deconf_crs),
        })

    valid = [r for r in results]
    mean_shift = np.mean([r['shift'] for r in valid]) if valid else 0
    mean_mismatch_raw = np.mean([r['mismatch_raw'] for r in valid]) if valid else 0
    mean_mismatch_deconf = np.mean([r['mismatch_deconf'] for r in valid]) if valid else 0

    print(f"\n  Population loop-deconfounded CR:")
    print(f"    Mean CR shift (deconf vs raw): {mean_shift:+.0%}")
    print(f"    Mean mismatch vs profile (raw): {mean_mismatch_raw:+.0%}")
    print(f"    Mean mismatch vs profile (deconf): {mean_mismatch_deconf:+.0%}")

    if abs(mean_shift) > 0.15:
        verdict = 'LOOP_SIGNIFICANTLY_AFFECTS_CR'
    elif abs(mean_shift) > 0.05:
        verdict = 'LOOP_MODERATELY_AFFECTS_CR'
    else:
        verdict = 'LOOP_MINIMAL_CR_EFFECT'

    print(f"\n  ✓ EXP-1883 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(12, 5))
        names = [r['patient'] for r in valid]
        profiles = [r['cr_profile'] for r in valid]
        raws = [r['cr_raw_median'] for r in valid]
        deconfs = [r['cr_deconfounded_median'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.25, profiles, 0.25, label='Profile CR', color='#9E9E9E')
        ax.bar(x, raws, 0.25, label='Raw effective CR', color='#FF9800')
        ax.bar(x + 0.25, deconfs, 0.25, label='Loop-deconfounded CR', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Carb Ratio (g/U)')
        ax.set_title(f'EXP-1883: Deconfounded vs Raw CR (shift: {mean_shift:+.0%})')
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig03-deconfounded-cr.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig03-deconfounded-cr.png")

    return {
        'experiment': 'EXP-1883',
        'title': 'Loop-Deconfounded CR Estimation',
        'verdict': verdict,
        'mean_shift': round(mean_shift, 3),
        'mean_mismatch_raw': round(mean_mismatch_raw, 3),
        'mean_mismatch_deconf': round(mean_mismatch_deconf, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1884: Basal Rate Assessment
# ===========================================================================

def exp_1884(patients, figures_dir):
    """Compare scheduled basal rate vs actual delivery rate.
    How much does the loop deviate from scheduled basal?
    """
    print("=" * 70)
    print("EXP-1884: Basal Rate — Scheduled vs Actual Delivery")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        scheduled = get_basal(p)

        temp_rate = df.get('temp_rate', pd.Series(np.nan, index=df.index)).values
        valid_tr = temp_rate[np.isfinite(temp_rate)]

        if len(valid_tr) < 1000:
            print(f"  {name}: insufficient temp rate data ({len(valid_tr)})")
            continue

        actual_median = np.median(valid_tr)
        actual_mean = np.mean(valid_tr)

        # What fraction of time is loop at scheduled rate (±10%)?
        at_scheduled = np.abs(valid_tr - scheduled) < scheduled * 0.1
        at_scheduled_frac = at_scheduled.sum() / len(valid_tr)

        # Distribution: how often is loop above vs below scheduled?
        above_frac = (valid_tr > scheduled * 1.1).sum() / len(valid_tr)
        below_frac = (valid_tr < scheduled * 0.9).sum() / len(valid_tr)

        # Zero/suspend fraction
        zero_frac = (valid_tr < 0.05).sum() / len(valid_tr)

        # Ratio of actual to scheduled
        ratio = actual_median / scheduled if scheduled > 0 else 1

        print(f"  {name}: sched={scheduled:.2f}U/h actual={actual_median:.2f}U/h "
              f"ratio={ratio:.2f} at_sched={at_scheduled_frac:.0%} "
              f"above={above_frac:.0%} below={below_frac:.0%} zero={zero_frac:.0%}")

        results.append({
            'patient': name,
            'scheduled_rate': round(scheduled, 2),
            'actual_median': round(float(actual_median), 2),
            'actual_mean': round(float(actual_mean), 2),
            'ratio': round(float(ratio), 3),
            'at_scheduled_fraction': round(float(at_scheduled_frac), 3),
            'above_fraction': round(float(above_frac), 3),
            'below_fraction': round(float(below_frac), 3),
            'zero_fraction': round(float(zero_frac), 3),
        })

    valid = [r for r in results]
    mean_ratio = np.mean([r['ratio'] for r in valid]) if valid else 1
    mean_at_sched = np.mean([r['at_scheduled_fraction'] for r in valid]) if valid else 0

    print(f"\n  Population basal assessment:")
    print(f"    Mean actual/scheduled ratio: {mean_ratio:.2f}")
    print(f"    Mean at-scheduled fraction: {mean_at_sched:.0%}")

    if mean_at_sched < 0.3:
        verdict = 'RARELY_AT_SCHEDULED'
    elif mean_at_sched < 0.5:
        verdict = 'OFTEN_DEVIATES'
    else:
        verdict = 'MOSTLY_AT_SCHEDULED'

    print(f"\n  ✓ EXP-1884 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        sched = [r['scheduled_rate'] for r in valid]
        actual = [r['actual_median'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, sched, 0.4, label='Scheduled', color='#9E9E9E')
        ax.bar(x + 0.2, actual, 0.4, label='Actual (median)', color='#2196F3')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Basal Rate (U/h)')
        ax.set_title('EXP-1884: Scheduled vs Actual Basal')
        ax.legend()

        ax = axes[1]
        at_s = [r['at_scheduled_fraction'] * 100 for r in valid]
        above = [r['above_fraction'] * 100 for r in valid]
        below = [r['below_fraction'] * 100 for r in valid]
        ax.bar(x, at_s, label='At scheduled', color='#4CAF50')
        ax.bar(x, above, bottom=at_s, label='Above', color='#F44336')
        ax.bar(x, below, bottom=[a + b for a, b in zip(at_s, above)],
               label='Below/suspend', color='#2196F3')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Time (%)')
        ax.set_title('EXP-1884: Basal Distribution')
        ax.legend(fontsize=8)

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig04-basal-assessment.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig04-basal-assessment.png")

    return {
        'experiment': 'EXP-1884',
        'title': 'Basal Rate — Scheduled vs Actual',
        'verdict': verdict,
        'mean_ratio': round(mean_ratio, 3),
        'mean_at_scheduled': round(mean_at_sched, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1885: Overnight Basal Drift Analysis
# ===========================================================================

def exp_1885(patients, figures_dir):
    """Analyze overnight glucose drift (midnight-6am) to assess basal accuracy.
    Overnight is the cleanest signal because: no meals, minimal boluses,
    counter-regulatory responses are lowest.
    """
    print("=" * 70)
    print("EXP-1885: Overnight Basal Drift Analysis")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values

        # Extract overnight segments (midnight=0 to 6am=72 steps)
        steps_per_day = 288
        overnight_drifts = []
        overnight_means = []

        for day_start in range(0, len(glucose) - steps_per_day, steps_per_day):
            # midnight to 6am
            seg = glucose[day_start:day_start + 72]
            valid = np.isfinite(seg)
            if valid.sum() < 50:
                continue

            g_start = np.nanmean(seg[:6])  # first 30 min
            g_end = np.nanmean(seg[-6:])   # last 30 min
            if np.isnan(g_start) or np.isnan(g_end):
                continue

            drift = (g_end - g_start) / 5  # mg/dL per hour (6 hours)
            overnight_drifts.append(drift)
            overnight_means.append(np.nanmean(seg))

        if len(overnight_drifts) < 10:
            print(f"  {name}: insufficient overnight segments ({len(overnight_drifts)})")
            continue

        drifts = np.array(overnight_drifts)
        means = np.array(overnight_means)

        mean_drift = np.mean(drifts)
        median_drift = np.median(drifts)
        drift_std = np.std(drifts)
        rising_frac = (drifts > 1).sum() / len(drifts)
        falling_frac = (drifts < -1).sum() / len(drifts)

        # Drift by glucose level (does it depend on starting glucose?)
        low_mask = means < 100
        high_mask = means > 150
        drift_low = np.mean(drifts[low_mask]) if low_mask.sum() > 5 else np.nan
        drift_high = np.mean(drifts[high_mask]) if high_mask.sum() > 5 else np.nan

        print(f"  {name}: n={len(drifts)} drift={mean_drift:+.1f}±{drift_std:.1f} mg/dL/h "
              f"rising={rising_frac:.0%} falling={falling_frac:.0%}" +
              (f" low_drift={drift_low:+.1f}" if not np.isnan(drift_low) else "") +
              (f" high_drift={drift_high:+.1f}" if not np.isnan(drift_high) else ""))

        results.append({
            'patient': name,
            'n_nights': len(drifts),
            'mean_drift_mg_dl_h': round(float(mean_drift), 2),
            'median_drift': round(float(median_drift), 2),
            'drift_std': round(float(drift_std), 2),
            'rising_fraction': round(float(rising_frac), 3),
            'falling_fraction': round(float(falling_frac), 3),
            'drift_low_glucose': round(float(drift_low), 2) if not np.isnan(drift_low) else None,
            'drift_high_glucose': round(float(drift_high), 2) if not np.isnan(drift_high) else None,
        })

    valid = [r for r in results]
    mean_drift_pop = np.mean([r['mean_drift_mg_dl_h'] for r in valid]) if valid else 0
    mean_rising = np.mean([r['rising_fraction'] for r in valid]) if valid else 0

    print(f"\n  Population overnight drift:")
    print(f"    Mean drift: {mean_drift_pop:+.1f} mg/dL/h")
    print(f"    Rising nights: {mean_rising:.0%}")

    if abs(mean_drift_pop) > 3:
        verdict = 'BASAL_SIGNIFICANTLY_WRONG'
    elif abs(mean_drift_pop) > 1:
        verdict = 'BASAL_MODERATELY_WRONG'
    else:
        verdict = 'BASAL_APPROXIMATELY_CORRECT'

    print(f"\n  ✓ EXP-1885 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        drifts_pop = [r['mean_drift_mg_dl_h'] for r in valid]
        stds = [r['drift_std'] for r in valid]
        colors = ['#F44336' if abs(d) > 3 else '#FF9800' if abs(d) > 1 else '#4CAF50'
                  for d in drifts_pop]
        ax.bar(names, drifts_pop, color=colors, yerr=stds, capsize=3)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Overnight Drift (mg/dL/h)')
        ax.set_title('EXP-1885: Overnight Glucose Drift')

        ax = axes[1]
        # Drift by glucose level
        low_drifts = [r['drift_low_glucose'] if r['drift_low_glucose'] is not None else 0
                      for r in valid]
        high_drifts = [r['drift_high_glucose'] if r['drift_high_glucose'] is not None else 0
                       for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, low_drifts, 0.4, label='Low glucose (<100)', color='#2196F3')
        ax.bar(x + 0.2, high_drifts, 0.4, label='High glucose (>150)', color='#F44336')
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Drift (mg/dL/h)')
        ax.set_title('EXP-1885: Drift Depends on Glucose Level?')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig05-overnight-drift.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig05-overnight-drift.png")

    return {
        'experiment': 'EXP-1885',
        'title': 'Overnight Basal Drift Analysis',
        'verdict': verdict,
        'mean_drift': round(mean_drift_pop, 2),
        'mean_rising_fraction': round(mean_rising, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1886: What Does the Loop Think Is Wrong?
# ===========================================================================

def exp_1886(patients, figures_dir):
    """Analyze loop correction patterns to infer what the loop "thinks" is wrong.
    If loop always increases, basal is too low. If post-meal always corrects,
    CR is wrong. Map loop corrections to therapy parameter domains.
    """
    print("=" * 70)
    print("EXP-1886: Loop Correction Pattern Analysis")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values

        ci = correction_insulin(df)
        cb = ci['correction_basal']

        steps_per_day = 288
        # Decompose corrections by context
        # 1. Overnight (midnight-6am): basal domain
        # 2. Post-meal (2h after carbs): CR domain
        # 3. Daytime non-meal: ISF domain

        overnight_mask = np.zeros(len(df), dtype=bool)
        postmeal_mask = np.zeros(len(df), dtype=bool)
        daytime_mask = np.zeros(len(df), dtype=bool)

        for i in range(len(df)):
            tod = (i % steps_per_day) / STEPS_PER_HOUR  # hour of day
            if 0 <= tod < 6:
                overnight_mask[i] = True
            else:
                daytime_mask[i] = True

        # Post-meal: within 3h of carb entry
        for i in range(len(df)):
            if carbs[i] > 5:
                end = min(i + 36, len(df))
                postmeal_mask[i:end] = True
                daytime_mask[i:end] = False

        valid_cb = np.isfinite(cb)

        # Mean correction in each domain
        overnight_corr = np.nanmean(cb[valid_cb & overnight_mask]) * STEPS_PER_HOUR if (valid_cb & overnight_mask).sum() > 100 else np.nan
        postmeal_corr = np.nanmean(cb[valid_cb & postmeal_mask]) * STEPS_PER_HOUR if (valid_cb & postmeal_mask).sum() > 100 else np.nan
        daytime_corr = np.nanmean(cb[valid_cb & daytime_mask]) * STEPS_PER_HOUR if (valid_cb & daytime_mask).sum() > 100 else np.nan

        # Direction: positive = loop increasing insulin, negative = decreasing
        # Basal assessment: overnight correction direction
        if not np.isnan(overnight_corr):
            if overnight_corr > 0.05:
                basal_verdict = 'TOO_LOW'
            elif overnight_corr < -0.05:
                basal_verdict = 'TOO_HIGH'
            else:
                basal_verdict = 'ABOUT_RIGHT'
        else:
            basal_verdict = 'NO_DATA'

        if not np.isnan(postmeal_corr):
            if postmeal_corr > 0.05:
                cr_verdict = 'CR_TOO_HIGH'
            elif postmeal_corr < -0.05:
                cr_verdict = 'CR_TOO_LOW'
            else:
                cr_verdict = 'CR_OK'
        else:
            cr_verdict = 'NO_DATA'

        print(f"  {name}: overnight={overnight_corr:+.2f}U/h ({basal_verdict}) "
              f"postmeal={postmeal_corr:+.2f}U/h ({cr_verdict}) " +
              (f"daytime={daytime_corr:+.2f}U/h" if not np.isnan(daytime_corr) else ""))

        results.append({
            'patient': name,
            'overnight_correction_U_h': round(float(overnight_corr), 3) if not np.isnan(overnight_corr) else None,
            'postmeal_correction_U_h': round(float(postmeal_corr), 3) if not np.isnan(postmeal_corr) else None,
            'daytime_correction_U_h': round(float(daytime_corr), 3) if not np.isnan(daytime_corr) else None,
            'basal_verdict': basal_verdict,
            'cr_verdict': cr_verdict,
        })

    valid = [r for r in results]
    basal_counts = {}
    cr_counts = {}
    for r in valid:
        basal_counts[r['basal_verdict']] = basal_counts.get(r['basal_verdict'], 0) + 1
        cr_counts[r['cr_verdict']] = cr_counts.get(r['cr_verdict'], 0) + 1

    print(f"\n  Population loop pattern analysis:")
    print(f"    Basal: {basal_counts}")
    print(f"    CR: {cr_counts}")

    verdict = f"BASAL:{max(basal_counts, key=basal_counts.get)}_CR:{max(cr_counts, key=cr_counts.get)}"
    print(f"\n  ✓ EXP-1886 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(12, 5))
        names = [r['patient'] for r in valid]
        overnight = [r['overnight_correction_U_h'] or 0 for r in valid]
        postmeal = [r['postmeal_correction_U_h'] or 0 for r in valid]
        daytime = [r['daytime_correction_U_h'] or 0 for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.25, overnight, 0.25, label='Overnight (→basal)', color='#2196F3')
        ax.bar(x, postmeal, 0.25, label='Post-meal (→CR)', color='#FF9800')
        ax.bar(x + 0.25, daytime, 0.25, label='Daytime non-meal (→ISF)', color='#4CAF50')
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Mean Correction (U/h)')
        ax.set_title('EXP-1886: Loop Corrections by Context')
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig06-correction-patterns.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig06-correction-patterns.png")

    return {
        'experiment': 'EXP-1886',
        'title': 'Loop Correction Pattern Analysis',
        'verdict': verdict,
        'basal_counts': basal_counts,
        'cr_counts': cr_counts,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1887: Temporal Stability of Deconfounded Params
# ===========================================================================

def exp_1887(patients, figures_dir):
    """Are loop-deconfounded therapy parameters more or less stable over time
    than raw parameters?
    """
    print("=" * 70)
    print("EXP-1887: Temporal Stability of Deconfounded Parameters")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        mid = len(df) // 2

        # Split into halves
        for half_label, df_half in [('h1', df.iloc[:mid].copy()), ('h2', df.iloc[mid:].copy())]:
            df_half.attrs = dict(df.attrs)
            glucose = df_half['glucose'].values
            carbs_arr = df_half.get('carbs', pd.Series(0, index=df_half.index)).fillna(0).values
            bolus_arr = df_half.get('bolus', pd.Series(0, index=df_half.index)).fillna(0).values

            # Raw effective CR
            raw_crs = []
            for i in range(12, len(glucose) - 36):
                if carbs_arr[i] < 10 or bolus_arr[i] < 0.5:
                    continue
                raw_crs.append(carbs_arr[i] / bolus_arr[i])

            raw_median = np.median(raw_crs) if len(raw_crs) >= 10 else np.nan

            # Deconfounded CR (using correction insulin)
            ci = correction_insulin(df_half)
            deconf_crs = []
            for i in range(12, len(glucose) - 36):
                if carbs_arr[i] < 10 or bolus_arr[i] < 0.5:
                    continue
                corr_w = ci['total_correction'][i:min(i + 36, len(ci['total_correction']))]
                total_corr = np.nansum(corr_w) * STEPS_PER_HOUR
                total_ins = bolus_arr[i] + total_corr
                if total_ins > 0.3:
                    dc = carbs_arr[i] / total_ins
                    if 0.5 < dc < 100:
                        deconf_crs.append(dc)

            deconf_median = np.median(deconf_crs) if len(deconf_crs) >= 10 else np.nan

            if half_label == 'h1':
                raw_h1, deconf_h1 = raw_median, deconf_median
            else:
                raw_h2, deconf_h2 = raw_median, deconf_median

        if np.isnan(raw_h1) or np.isnan(raw_h2):
            print(f"  {name}: insufficient data for temporal comparison")
            continue

        raw_change = abs(raw_h2 - raw_h1) / raw_h1 if raw_h1 > 0 else np.nan
        deconf_change = abs(deconf_h2 - deconf_h1) / deconf_h1 if not np.isnan(deconf_h1) and deconf_h1 > 0 else np.nan

        more_stable = 'deconf' if (not np.isnan(deconf_change) and deconf_change < raw_change) else 'raw'

        print(f"  {name}: raw(h1={raw_h1:.1f} h2={raw_h2:.1f} Δ={raw_change:.0%}) "
              f"deconf(h1={deconf_h1:.1f} h2={deconf_h2:.1f}" +
              (f" Δ={deconf_change:.0%})" if not np.isnan(deconf_change) else ")") +
              f" more_stable={more_stable}")

        results.append({
            'patient': name,
            'raw_h1': round(float(raw_h1), 1),
            'raw_h2': round(float(raw_h2), 1),
            'raw_change': round(float(raw_change), 3),
            'deconf_h1': round(float(deconf_h1), 1) if not np.isnan(deconf_h1) else None,
            'deconf_h2': round(float(deconf_h2), 1) if not np.isnan(deconf_h2) else None,
            'deconf_change': round(float(deconf_change), 3) if not np.isnan(deconf_change) else None,
            'more_stable': more_stable,
        })

    valid = [r for r in results]
    deconf_more_stable = sum(1 for r in valid if r['more_stable'] == 'deconf')
    mean_raw_change = np.mean([r['raw_change'] for r in valid])
    deconf_changes = [r['deconf_change'] for r in valid if r['deconf_change'] is not None]
    mean_deconf_change = np.mean(deconf_changes) if deconf_changes else np.nan

    print(f"\n  Population temporal stability:")
    print(f"    Deconfounded more stable: {deconf_more_stable}/{len(valid)}")
    print(f"    Mean raw change: {mean_raw_change:.0%}")
    print(f"    Mean deconfounded change: {mean_deconf_change:.0%}" if not np.isnan(mean_deconf_change) else "")

    if deconf_more_stable > len(valid) * 0.6:
        verdict = 'DECONFOUNDED_MORE_STABLE'
    elif deconf_more_stable > len(valid) * 0.4:
        verdict = 'SIMILAR_STABILITY'
    else:
        verdict = 'RAW_MORE_STABLE'

    print(f"\n  ✓ EXP-1887 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(12, 5))
        names = [r['patient'] for r in valid]
        raw_ch = [r['raw_change'] * 100 for r in valid]
        deconf_ch = [r['deconf_change'] * 100 if r['deconf_change'] else 0 for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, raw_ch, 0.4, label='Raw CR change', color='#FF9800')
        ax.bar(x + 0.2, deconf_ch, 0.4, label='Deconfounded CR change', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Change Between Halves (%)')
        ax.set_title(f'EXP-1887: Temporal Stability (deconf better: {deconf_more_stable}/{len(valid)})')
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig07-temporal-stability.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig07-temporal-stability.png")

    return {
        'experiment': 'EXP-1887',
        'title': 'Temporal Stability of Deconfounded Parameters',
        'verdict': verdict,
        'deconf_more_stable': deconf_more_stable,
        'mean_raw_change': round(mean_raw_change, 3),
        'mean_deconf_change': round(float(mean_deconf_change), 3) if not np.isnan(mean_deconf_change) else None,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1888: Combined Deconfounded Therapy Assessment
# ===========================================================================

def exp_1888(patients, figures_dir):
    """Combine all deconfounding signals into a unified therapy assessment.
    Score each therapy parameter (ISF, CR, basal) based on:
    - Loop correction magnitude and direction
    - Direct estimation from glucose curves
    - Temporal stability
    """
    print("=" * 70)
    print("EXP-1888: Combined Deconfounded Therapy Assessment")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_profile = get_isf(p)
        cr_profile = get_cr(p)
        basal_profile = get_basal(p)

        if len(glucose) < 1000:
            continue

        # --- Basal assessment ---
        # Overnight drift
        steps_per_day = 288
        overnight_drifts = []
        for day_start in range(0, len(glucose) - steps_per_day, steps_per_day):
            seg = glucose[day_start:day_start + 72]
            valid = np.isfinite(seg)
            if valid.sum() < 50:
                continue
            g_start = np.nanmean(seg[:6])
            g_end = np.nanmean(seg[-6:])
            if not np.isnan(g_start) and not np.isnan(g_end):
                overnight_drifts.append((g_end - g_start) / 5)

        basal_drift = np.mean(overnight_drifts) if len(overnight_drifts) > 5 else np.nan

        # Basal direction from loop
        ci = correction_insulin(df)
        cb = ci['correction_basal']
        overnight_mask = np.zeros(len(df), dtype=bool)
        for i in range(len(df)):
            tod = (i % steps_per_day) / STEPS_PER_HOUR
            if 0 <= tod < 6:
                overnight_mask[i] = True
        valid_cb_on = np.isfinite(cb) & overnight_mask
        overnight_corr = np.nanmean(cb[valid_cb_on]) * STEPS_PER_HOUR if valid_cb_on.sum() > 100 else np.nan

        if not np.isnan(basal_drift):
            if basal_drift > 2:
                basal_score = 'TOO_LOW'
            elif basal_drift < -2:
                basal_score = 'TOO_HIGH'
            else:
                basal_score = 'ADEQUATE'
        else:
            basal_score = 'UNKNOWN'

        # --- CR assessment ---
        carbs_arr = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        bolus_arr = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values

        raw_crs = []
        for i in range(12, len(glucose) - 36):
            if carbs_arr[i] < 10 or bolus_arr[i] < 0.5:
                continue
            g_pre = glucose[i]
            g_peak = np.nanmax(glucose[i:i + 24])
            if np.isnan(g_pre) or np.isnan(g_peak):
                continue
            excursion = g_peak - g_pre
            if excursion <= 0:
                continue
            denom = excursion + bolus_arr[i] * isf_profile
            if denom > 0:
                cr_eff = carbs_arr[i] * isf_profile / denom
                if 1 < cr_eff < 100:
                    raw_crs.append(cr_eff)

        cr_effective = np.median(raw_crs) if len(raw_crs) >= 10 else np.nan
        cr_mismatch = (cr_effective - cr_profile) / cr_profile if not np.isnan(cr_effective) else np.nan

        if not np.isnan(cr_mismatch):
            if cr_mismatch < -0.3:
                cr_score = 'SIGNIFICANTLY_HIGH'
            elif cr_mismatch < -0.15:
                cr_score = 'MODERATELY_HIGH'
            elif cr_mismatch > 0.15:
                cr_score = 'TOO_LOW'
            else:
                cr_score = 'ADEQUATE'
        else:
            cr_score = 'UNKNOWN'

        # --- ISF assessment ---
        # Use split-loss approach: optimize ISF via total loss
        sd_base = compute_supply_demand(df)
        _, _, tl_base = supply_demand_loss(sd_base, glucose)
        scales = np.array([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 2.5, 3.0])
        best_scale = 1.0
        best_loss = tl_base
        for s in scales:
            df_s = df.copy()
            df_s.attrs = dict(df.attrs)
            isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_profile}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = isf_profile * s
            df_s.attrs['isf_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            _, _, tl_s = supply_demand_loss(sd_s, glucose)
            if not np.isnan(tl_s) and tl_s < best_loss:
                best_loss = tl_s
                best_scale = s

        isf_mismatch = best_scale - 1.0
        if abs(isf_mismatch) > 0.3:
            isf_score = 'SIGNIFICANTLY_WRONG'
        elif abs(isf_mismatch) > 0.15:
            isf_score = 'MODERATELY_WRONG'
        else:
            isf_score = 'ADEQUATE'

        # --- Combined assessment ---
        n_wrong = sum(1 for s in [basal_score, cr_score, isf_score]
                      if 'ADEQUATE' not in s and 'UNKNOWN' not in s)

        print(f"  {name}: basal={basal_score}(drift={basal_drift:+.1f}" if not np.isnan(basal_drift) else f"  {name}: basal={basal_score}",
              f") CR={cr_score}(mismatch={cr_mismatch:+.0%}" if not np.isnan(cr_mismatch) else f" CR={cr_score}",
              f") ISF={isf_score}(scale={best_scale:.2f}×) wrong_params={n_wrong}/3")

        results.append({
            'patient': name,
            'basal_score': basal_score,
            'basal_drift': round(float(basal_drift), 2) if not np.isnan(basal_drift) else None,
            'basal_overnight_corr': round(float(overnight_corr), 3) if not np.isnan(overnight_corr) else None,
            'cr_score': cr_score,
            'cr_effective': round(float(cr_effective), 1) if not np.isnan(cr_effective) else None,
            'cr_mismatch': round(float(cr_mismatch), 3) if not np.isnan(cr_mismatch) else None,
            'cr_profile': cr_profile,
            'isf_score': isf_score,
            'isf_optimal_scale': round(best_scale, 2),
            'isf_profile': isf_profile,
            'n_wrong_params': n_wrong,
        })

    valid = [r for r in results]
    mean_wrong = np.mean([r['n_wrong_params'] for r in valid]) if valid else 0

    # Summary counts
    basal_wrong = sum(1 for r in valid if r['basal_score'] != 'ADEQUATE')
    cr_wrong = sum(1 for r in valid if 'ADEQUATE' not in r['cr_score'] and r['cr_score'] != 'UNKNOWN')
    isf_wrong = sum(1 for r in valid if r['isf_score'] != 'ADEQUATE')

    print(f"\n  Population therapy assessment:")
    print(f"    Basal wrong: {basal_wrong}/{len(valid)}")
    print(f"    CR wrong: {cr_wrong}/{len(valid)}")
    print(f"    ISF wrong: {isf_wrong}/{len(valid)}")
    print(f"    Mean wrong params per patient: {mean_wrong:.1f}/3")

    verdict = f"BASAL:{basal_wrong}_CR:{cr_wrong}_ISF:{isf_wrong}_of_{len(valid)}"
    print(f"\n  ✓ EXP-1888 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        # Heatmap-style per-patient assessment
        names = [r['patient'] for r in valid]
        params = ['Basal', 'CR', 'ISF']
        scores = []
        for r in valid:
            row = []
            for score in [r['basal_score'], r['cr_score'], r['isf_score']]:
                if 'ADEQUATE' in score:
                    row.append(0)
                elif 'MODERATE' in score:
                    row.append(1)
                elif 'SIGNIFICANT' in score or 'TOO' in score:
                    row.append(2)
                else:
                    row.append(-1)
            scores.append(row)

        scores_arr = np.array(scores)
        cmap = plt.cm.RdYlGn_r
        im = ax.imshow(scores_arr.T, cmap=cmap, aspect='auto', vmin=-1, vmax=2)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names)
        ax.set_yticks(range(3))
        ax.set_yticklabels(params)
        ax.set_title('EXP-1888: Therapy Parameter Assessment')
        # Add text annotations
        for i in range(len(names)):
            for j in range(3):
                score_text = [valid[i]['basal_score'], valid[i]['cr_score'], valid[i]['isf_score']][j]
                short = score_text.split('_')[0][:4]
                ax.text(i, j, short, ha='center', va='center', fontsize=7)

        ax = axes[1]
        ax.bar(['Basal', 'CR', 'ISF'],
               [basal_wrong, cr_wrong, isf_wrong],
               color=['#2196F3', '#FF9800', '#4CAF50'])
        ax.set_ylabel(f'Patients with Wrong Parameter (of {len(valid)})')
        ax.set_title(f'EXP-1888: Which Parameters Are Wrong?')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'loop-fig08-combined-assessment.png'), dpi=150)
        plt.close()
        print(f"  → Saved loop-fig08-combined-assessment.png")

    return {
        'experiment': 'EXP-1888',
        'title': 'Combined Deconfounded Therapy Assessment',
        'verdict': verdict,
        'basal_wrong': basal_wrong,
        'cr_wrong': cr_wrong,
        'isf_wrong': isf_wrong,
        'mean_wrong_params': round(mean_wrong, 1),
        'per_patient': results,
    }


# ===========================================================================
# Main
# ===========================================================================

EXPERIMENTS = [
    ('EXP-1881', exp_1881),
    ('EXP-1882', exp_1882),
    ('EXP-1883', exp_1883),
    ('EXP-1884', exp_1884),
    ('EXP-1885', exp_1885),
    ('EXP-1886', exp_1886),
    ('EXP-1887', exp_1887),
    ('EXP-1888', exp_1888),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--only', type=str, help='Run only this experiment')
    args = parser.parse_args()

    figures_dir = 'docs/60-research/figures' if args.figures else None
    if figures_dir:
        os.makedirs(figures_dir, exist_ok=True)

    print("=" * 70)
    print("EXP-1881–1888: Loop-Deconfounded Therapy Estimation")
    print("=" * 70)

    patients = load_patients('externals/ns-data/patients/')
    print(f"Loaded {len(patients)} patients\n")

    all_results = {}
    for exp_id, func in EXPERIMENTS:
        if args.only and exp_id != args.only:
            continue
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}: {func.__doc__.strip().split(chr(10))[0]}")
        print(f"{'#' * 70}\n")
        try:
            result = func(patients, figures_dir)
            all_results[exp_id] = result
        except Exception as e:
            print(f"\n  ✗ {exp_id} FAILED: {e}")
            import traceback
            traceback.print_exc()
            all_results[exp_id] = {'experiment': exp_id, 'verdict': f'FAILED: {e}'}

    out_path = 'externals/experiments/exp-1881_loop_deconfound.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {out_path}")

    print(f"\n{'=' * 70}")
    print("SYNTHESIS: Loop-Deconfounded Therapy Estimation")
    print(f"{'=' * 70}")
    for exp_id, result in all_results.items():
        print(f"  {exp_id}: {result.get('verdict', 'N/A')}")
    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
