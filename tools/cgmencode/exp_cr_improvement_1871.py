#!/usr/bin/env python3
"""
EXP-1871–1878: Carb Ratio Improvement & Meal Analysis

Following the data:
  - EXP-1845: CR is most-wrong for 8/11 patients (73%)
  - EXP-1853: Wrong CR contaminates announced meals more than UAM
  - EXP-1866: Dose-adjusted CR shifts by -30%
  - EXP-1856/1865: ISF is dose-dependent (SMBs 4.6× more efficient)

This batch investigates WHY CR estimates are wrong and HOW to improve them.

Key questions:
  1. Is the CR error from absorption timing or magnitude? (1871)
  2. Do meal excursions follow predictable patterns by meal size? (1872)
  3. Does carb-to-bolus timing affect apparent CR? (1873)
  4. Can we estimate effective CR from post-meal glucose curves? (1874)
  5. Is CR time-of-day dependent (breakfast > dinner)? (1875)
  6. Does AID loop compensation mask CR errors? (1876)
  7. UAM meals vs announced: is the model error structural? (1877)
  8. Combined CR estimator: excursion + timing + context (1878)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_cr_improvement_1871.py [--figures]
"""

import argparse
import json
import os
import sys
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

def get_isf(patient):
    isf = patient['df'].attrs.get('isf_schedule', [{'value': 50}])
    val = isf[0]['value'] if isinstance(isf, list) else 50
    if val < 15:
        val *= 18.0182
    return val


def get_cr(patient):
    cr = patient['df'].attrs.get('cr_schedule', [{'value': 10}])
    return cr[0]['value'] if isinstance(cr, list) else 10


STEPS_PER_HOUR = 12  # 5-min steps


def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    """Find meal events and characterize the post-meal glucose excursion.

    Returns list of dicts with meal and excursion properties.
    """
    glucose = df['glucose'].values
    carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
    bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
    iob = df.get('iob', pd.Series(0, index=df.index)).fillna(0).values

    meals = []
    for i in range(pre_window, len(glucose) - post_window):
        if carbs[i] < min_carbs:
            continue

        g_pre = glucose[i]
        if np.isnan(g_pre):
            # Try nearby
            g_pre = np.nanmean(glucose[max(0, i - 3):i + 1])
            if np.isnan(g_pre):
                continue

        g_post = glucose[i:i + post_window]
        if np.all(np.isnan(g_post)):
            continue

        g_peak = np.nanmax(g_post)
        peak_idx = np.nanargmax(g_post)  # steps to peak
        g_3h = glucose[min(i + 36, len(glucose) - 1)]
        excursion = g_peak - g_pre
        g_return = g_3h - g_pre if not np.isnan(g_3h) else np.nan

        # Find associated bolus (within ±30min)
        bolus_window = bolus[max(0, i - 6):i + 6]
        total_bolus = np.sum(bolus_window)

        # Time of day (step index mod steps per day)
        steps_per_day = 288  # 24h * 12 steps/h
        tod_step = i % steps_per_day
        hour = tod_step / STEPS_PER_HOUR

        # Bolus timing relative to carbs
        bolus_before = np.sum(bolus[max(0, i - 6):i])
        bolus_after = np.sum(bolus[i:i + 6])
        pre_bolus = bolus_before > bolus_after

        # IOB at meal time
        iob_at_meal = iob[i] if not np.isnan(iob[i]) else 0

        meals.append({
            'idx': i,
            'carbs': carbs[i],
            'bolus': total_bolus,
            'effective_cr': carbs[i] / total_bolus if total_bolus > 0.1 else np.nan,
            'g_pre': g_pre,
            'g_peak': g_peak,
            'excursion': excursion,
            'peak_time_min': peak_idx * 5,
            'g_return': g_return,
            'hour': hour,
            'pre_bolus': pre_bolus,
            'iob_at_meal': iob_at_meal,
        })

    return meals


def supply_demand_loss(sd, glucose, mask=None):
    """Compute supply/demand/total loss with NaN handling."""
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


# ===========================================================================
# EXP-1871: Is CR Error from Timing or Magnitude?
# ===========================================================================

def exp_1871(patients, figures_dir):
    """Decompose post-meal glucose error into timing error (peak time) and
    magnitude error (excursion size). Which dominates?
    """
    print("=" * 70)
    print("EXP-1871: CR Error — Timing vs Magnitude")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)
        meals = find_meals(df, min_carbs=10)

        if len(meals) < 15:
            print(f"  {name}: insufficient meals ({len(meals)})")
            continue

        # Predicted excursion from profile CR: carbs / CR * ISF
        # This is the expected glucose rise if all carbs are absorbed
        excursions = np.array([m['excursion'] for m in meals])
        carbs_arr = np.array([m['carbs'] for m in meals])
        bolus_arr = np.array([m['bolus'] for m in meals])
        peak_times = np.array([m['peak_time_min'] for m in meals])

        # Expected excursion: (carbs - bolus * CR) / CR * ISF ≈ net carbs impact
        # Simplified: excursion = (carbs - bolus * CR) * ISF / CR
        predicted_excursion = (carbs_arr - bolus_arr * cr_profile) * isf_profile / max(cr_profile, 1)

        # Magnitude error: predicted vs actual excursion
        valid_e = np.isfinite(excursions) & np.isfinite(predicted_excursion)
        if valid_e.sum() < 10:
            continue

        mag_error = np.sqrt(np.mean((excursions[valid_e] - predicted_excursion[valid_e]) ** 2))
        mag_bias = np.mean(excursions[valid_e] - predicted_excursion[valid_e])

        # Timing error: variance in peak time
        valid_t = np.isfinite(peak_times) & (peak_times > 0)
        timing_cv = np.std(peak_times[valid_t]) / np.mean(peak_times[valid_t]) if valid_t.sum() > 5 else np.nan
        mean_peak = np.mean(peak_times[valid_t]) if valid_t.sum() > 5 else np.nan

        # Correlation: do bigger meals have predictable excursions?
        valid_both = valid_e & (bolus_arr > 0.1)
        if valid_both.sum() > 10:
            corr_carb_excursion = np.corrcoef(carbs_arr[valid_both], excursions[valid_both])[0, 1]
        else:
            corr_carb_excursion = np.nan

        print(f"  {name}: meals={len(meals)} mag_RMSE={mag_error:.0f} "
              f"mag_bias={mag_bias:+.0f} peak_mean={mean_peak:.0f}min "
              f"peak_CV={timing_cv:.2f} carb-exc_r={corr_carb_excursion:.2f}")

        results.append({
            'patient': name,
            'n_meals': len(meals),
            'magnitude_rmse': round(float(mag_error), 1),
            'magnitude_bias': round(float(mag_bias), 1),
            'mean_peak_time': round(float(mean_peak), 0) if not np.isnan(mean_peak) else None,
            'peak_time_cv': round(float(timing_cv), 3) if not np.isnan(timing_cv) else None,
            'carb_excursion_correlation': round(float(corr_carb_excursion), 3) if not np.isnan(corr_carb_excursion) else None,
            'cr_profile': cr_profile,
        })

    valid = [r for r in results]
    mean_rmse = np.mean([r['magnitude_rmse'] for r in valid])
    mean_bias = np.mean([r['magnitude_bias'] for r in valid])
    mean_peak_cv = np.mean([r['peak_time_cv'] for r in valid if r['peak_time_cv'] is not None])
    mean_corr = np.mean([r['carb_excursion_correlation'] for r in valid
                         if r['carb_excursion_correlation'] is not None])

    print(f"\n  Population meal analysis:")
    print(f"    Magnitude RMSE: {mean_rmse:.0f} mg/dL")
    print(f"    Magnitude bias: {mean_bias:+.0f} mg/dL (positive = model underpredicts rise)")
    print(f"    Peak time CV: {mean_peak_cv:.2f}")
    print(f"    Carb-excursion correlation: {mean_corr:.2f}")

    if mean_peak_cv > 0.5:
        timing_issue = True
    else:
        timing_issue = False

    if abs(mean_bias) > 30:
        magnitude_issue = True
    else:
        magnitude_issue = False

    if timing_issue and magnitude_issue:
        verdict = 'BOTH_TIMING_AND_MAGNITUDE'
    elif timing_issue:
        verdict = 'TIMING_DOMINANT'
    elif magnitude_issue:
        verdict = 'MAGNITUDE_DOMINANT'
    else:
        verdict = 'NEITHER_DOMINANT'

    print(f"\n  ✓ EXP-1871 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        biases = [r['magnitude_bias'] for r in valid]
        colors = ['#F44336' if b > 0 else '#2196F3' for b in biases]
        ax.bar(names, biases, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Excursion Bias (mg/dL)')
        ax.set_title('Magnitude: Model Under/Overpredicts Rise')

        ax = axes[1]
        cvs = [r['peak_time_cv'] if r['peak_time_cv'] else 0 for r in valid]
        ax.bar(names, cvs, color='#FF9800')
        ax.axhline(0.5, color='r', linestyle='--', alpha=0.3, label='High variability')
        ax.set_ylabel('Peak Time CV')
        ax.set_title('Timing: Absorption Time Variability')
        ax.legend()

        ax = axes[2]
        corrs = [r['carb_excursion_correlation'] if r['carb_excursion_correlation'] else 0 for r in valid]
        ax.bar(names, corrs, color='#4CAF50')
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Correlation (carbs vs excursion)')
        ax.set_title('Predictability: Do More Carbs = More Rise?')

        plt.suptitle('EXP-1871: Meal Error Decomposition', fontsize=14)
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig01-timing-vs-magnitude.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig01-timing-vs-magnitude.png")

    return {
        'experiment': 'EXP-1871',
        'title': 'CR Error — Timing vs Magnitude',
        'verdict': verdict,
        'mean_magnitude_rmse': round(mean_rmse, 1),
        'mean_magnitude_bias': round(mean_bias, 1),
        'mean_peak_time_cv': round(mean_peak_cv, 3),
        'mean_carb_excursion_corr': round(mean_corr, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1872: Meal Size Classification
# ===========================================================================

def exp_1872(patients, figures_dir):
    """Do meal excursions follow predictable patterns by meal size?
    Classify meals into tiers and analyze excursion characteristics.
    """
    print("=" * 70)
    print("EXP-1872: Meal Excursion Patterns by Size")
    print("=" * 70)

    # Aggregate all meals across patients
    all_meals = []
    for p in patients:
        meals = find_meals(p['df'].copy(), min_carbs=5)
        for m in meals:
            m['patient'] = p['name']
            all_meals.append(m)

    if len(all_meals) < 50:
        print(f"  Insufficient meals ({len(all_meals)})")
        return {'experiment': 'EXP-1872', 'verdict': 'INSUFFICIENT_DATA'}

    carbs = np.array([m['carbs'] for m in all_meals])
    excursions = np.array([m['excursion'] for m in all_meals])
    peak_times = np.array([m['peak_time_min'] for m in all_meals])
    boluses = np.array([m['bolus'] for m in all_meals])

    tiers = [
        ('snack', 5, 20),
        ('small', 20, 40),
        ('medium', 40, 70),
        ('large', 70, 200),
    ]

    tier_results = {}
    for tier_name, lo, hi in tiers:
        mask = (carbs >= lo) & (carbs < hi) & np.isfinite(excursions)
        if mask.sum() < 10:
            continue
        e = excursions[mask]
        pt = peak_times[mask]
        b = boluses[mask]
        c = carbs[mask]

        tier_results[tier_name] = {
            'n': int(mask.sum()),
            'median_carbs': round(float(np.median(c)), 0),
            'median_excursion': round(float(np.median(e)), 0),
            'excursion_iqr': [round(float(np.percentile(e, 25)), 0),
                              round(float(np.percentile(e, 75)), 0)],
            'median_peak_time': round(float(np.median(pt[np.isfinite(pt)])), 0),
            'median_bolus': round(float(np.median(b)), 1),
            'bolused_fraction': round(float((b > 0.1).sum() / max(mask.sum(), 1)), 2),
        }

        print(f"  {tier_name} ({lo}-{hi}g): n={mask.sum()} excursion={np.median(e):.0f} "
              f"peak={np.median(pt[np.isfinite(pt)]):.0f}min bolus={np.median(b):.1f}U "
              f"bolused={tier_results[tier_name]['bolused_fraction']:.0%}")

    # Key question: does excursion scale linearly with carbs?
    valid = np.isfinite(excursions) & (boluses > 0.1) & (excursions > 0)
    if valid.sum() > 20:
        # Net excursion per gram (after bolus)
        net_excursion_per_g = excursions[valid] / carbs[valid]
        mean_per_g = np.median(net_excursion_per_g)
        cv_per_g = np.std(net_excursion_per_g) / np.mean(net_excursion_per_g)
    else:
        mean_per_g = np.nan
        cv_per_g = np.nan

    print(f"\n  Population meal patterns (n={len(all_meals)} meals):")
    print(f"    Median excursion per gram: {mean_per_g:.1f} mg/dL/g")
    print(f"    Per-gram CV: {cv_per_g:.2f}")

    if cv_per_g < 0.5:
        verdict = 'PREDICTABLE_BY_SIZE'
    elif cv_per_g < 1.0:
        verdict = 'PARTIALLY_PREDICTABLE'
    else:
        verdict = 'UNPREDICTABLE'

    print(f"\n  ✓ EXP-1872 verdict: {verdict}")

    if HAS_MPL and figures_dir:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        v = np.isfinite(excursions) & (excursions > -50)
        ax.scatter(carbs[v], excursions[v], alpha=0.1, s=10, color='#2196F3')
        # Tier means
        for tier_name, stats in tier_results.items():
            ax.plot(stats['median_carbs'], stats['median_excursion'], 'ro', markersize=10)
            ax.annotate(tier_name, (stats['median_carbs'], stats['median_excursion']),
                       fontsize=9, fontweight='bold')
        ax.set_xlabel('Carbs (g)')
        ax.set_ylabel('Excursion (mg/dL)')
        ax.set_title(f'EXP-1872: Excursion vs Meal Size (n={len(all_meals)})')
        ax.set_ylim(-50, 200)

        ax = axes[1]
        tier_names = list(tier_results.keys())
        excursions_by_tier = [tier_results[t]['median_excursion'] for t in tier_names]
        iqr_lo = [tier_results[t]['excursion_iqr'][0] for t in tier_names]
        iqr_hi = [tier_results[t]['excursion_iqr'][1] for t in tier_names]
        errors = [[e - l for e, l in zip(excursions_by_tier, iqr_lo)],
                  [h - e for e, h in zip(excursions_by_tier, iqr_hi)]]
        ax.bar(tier_names, excursions_by_tier, color='#FF9800', yerr=errors, capsize=5)
        ax.set_ylabel('Median Excursion (mg/dL)')
        ax.set_title('EXP-1872: Excursion by Meal Tier (with IQR)')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig02-meal-size-patterns.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig02-meal-size-patterns.png")

    return {
        'experiment': 'EXP-1872',
        'title': 'Meal Excursion Patterns by Size',
        'verdict': verdict,
        'n_total_meals': len(all_meals),
        'tier_results': tier_results,
        'median_excursion_per_gram': round(float(mean_per_g), 2) if not np.isnan(mean_per_g) else None,
        'per_gram_cv': round(float(cv_per_g), 2) if not np.isnan(cv_per_g) else None,
    }


# ===========================================================================
# EXP-1873: Bolus Timing Effect on Apparent CR
# ===========================================================================

def exp_1873(patients, figures_dir):
    """Does pre-bolusing (bolus before meal) vs post-bolusing change the
    apparent CR? This tests whether timing is a confound in CR estimation.
    """
    print("=" * 70)
    print("EXP-1873: Bolus Timing Effect on Apparent CR")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        meals = find_meals(df, min_carbs=10)

        bolused_meals = [m for m in meals if m['bolus'] > 0.1]
        if len(bolused_meals) < 20:
            print(f"  {name}: insufficient bolused meals ({len(bolused_meals)})")
            continue

        pre = [m for m in bolused_meals if m['pre_bolus']]
        post = [m for m in bolused_meals if not m['pre_bolus']]

        if len(pre) < 5 or len(post) < 5:
            print(f"  {name}: insufficient pre/post split (pre={len(pre)}, post={len(post)})")
            continue

        pre_exc = np.median([m['excursion'] for m in pre])
        post_exc = np.median([m['excursion'] for m in post])
        pre_peak = np.median([m['peak_time_min'] for m in pre])
        post_peak = np.median([m['peak_time_min'] for m in post])
        pre_cr = np.median([m['effective_cr'] for m in pre if not np.isnan(m['effective_cr'])])
        post_cr = np.median([m['effective_cr'] for m in post if not np.isnan(m['effective_cr'])])

        exc_diff = post_exc - pre_exc
        peak_diff = post_peak - pre_peak

        print(f"  {name}: pre={len(pre)} post={len(post)} "
              f"exc(pre={pre_exc:.0f} post={post_exc:.0f} Δ={exc_diff:+.0f}) "
              f"peak(pre={pre_peak:.0f} post={post_peak:.0f} Δ={peak_diff:+.0f}min) "
              f"CR(pre={pre_cr:.1f} post={post_cr:.1f})")

        results.append({
            'patient': name,
            'n_pre': len(pre),
            'n_post': len(post),
            'excursion_pre': round(float(pre_exc), 0),
            'excursion_post': round(float(post_exc), 0),
            'excursion_diff': round(float(exc_diff), 0),
            'peak_time_pre': round(float(pre_peak), 0),
            'peak_time_post': round(float(post_peak), 0),
            'peak_time_diff': round(float(peak_diff), 0),
            'cr_pre': round(float(pre_cr), 1),
            'cr_post': round(float(post_cr), 1),
        })

    valid = [r for r in results]
    mean_exc_diff = np.mean([r['excursion_diff'] for r in valid]) if valid else 0
    mean_peak_diff = np.mean([r['peak_time_diff'] for r in valid]) if valid else 0

    print(f"\n  Population bolus timing effect:")
    print(f"    Mean excursion difference (post-pre): {mean_exc_diff:+.0f} mg/dL")
    print(f"    Mean peak time difference: {mean_peak_diff:+.0f} min")

    if mean_exc_diff > 15:
        verdict = 'PRE_BOLUS_REDUCES_EXCURSION'
    elif mean_exc_diff < -15:
        verdict = 'POST_BOLUS_REDUCES_EXCURSION'
    else:
        verdict = 'TIMING_MINIMAL_EFFECT'

    print(f"\n  ✓ EXP-1873 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        pre_exc = [r['excursion_pre'] for r in valid]
        post_exc = [r['excursion_post'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, pre_exc, 0.4, label='Pre-bolus', color='#4CAF50')
        ax.bar(x + 0.2, post_exc, 0.4, label='Post-bolus', color='#FF9800')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Median Excursion (mg/dL)')
        ax.set_title('EXP-1873: Pre vs Post Bolus Excursion')
        ax.legend()

        ax = axes[1]
        diffs = [r['excursion_diff'] for r in valid]
        colors = ['#F44336' if d > 0 else '#4CAF50' for d in diffs]
        ax.bar(names, diffs, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Excursion Diff (post - pre) mg/dL')
        ax.set_title('EXP-1873: Does Pre-Bolusing Help?')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig03-bolus-timing.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig03-bolus-timing.png")

    return {
        'experiment': 'EXP-1873',
        'title': 'Bolus Timing Effect on Apparent CR',
        'verdict': verdict,
        'mean_excursion_diff': round(mean_exc_diff, 0),
        'mean_peak_time_diff': round(mean_peak_diff, 0),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1874: Effective CR from Post-Meal Glucose Curves
# ===========================================================================

def exp_1874(patients, figures_dir):
    """Estimate effective CR by inverting the observed glucose curve after meals.
    Compare with profile CR to quantify mismatch.
    """
    print("=" * 70)
    print("EXP-1874: Effective CR from Post-Meal Glucose Curves")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)
        meals = find_meals(df, min_carbs=10)

        bolused_meals = [m for m in meals if m['bolus'] > 0.5]
        if len(bolused_meals) < 15:
            print(f"  {name}: insufficient bolused meals ({len(bolused_meals)})")
            continue

        # For each meal, compute effective CR:
        # excursion = (carbs/CR_eff - bolus) * ISF → CR_eff = carbs * ISF / (excursion + bolus * ISF)
        effective_crs = []
        for m in bolused_meals:
            if m['excursion'] <= 0 or np.isnan(m['excursion']):
                continue
            denominator = m['excursion'] + m['bolus'] * isf_profile
            if denominator > 0:
                cr_eff = m['carbs'] * isf_profile / denominator
                if 1 < cr_eff < 100:
                    effective_crs.append(cr_eff)

        if len(effective_crs) < 10:
            print(f"  {name}: insufficient valid CR estimates ({len(effective_crs)})")
            continue

        eff_arr = np.array(effective_crs)
        cr_effective = np.median(eff_arr)
        cr_mismatch = (cr_effective - cr_profile) / cr_profile
        cr_cv = np.std(eff_arr) / np.mean(eff_arr)

        print(f"  {name}: n={len(effective_crs)} profile_CR={cr_profile:.0f} "
              f"effective_CR={cr_effective:.1f} mismatch={cr_mismatch:+.0%} CV={cr_cv:.2f}")

        results.append({
            'patient': name,
            'n_estimates': len(effective_crs),
            'cr_profile': cr_profile,
            'cr_effective': round(float(cr_effective), 1),
            'cr_mismatch': round(float(cr_mismatch), 3),
            'cr_cv': round(float(cr_cv), 3),
            'cr_p25': round(float(np.percentile(eff_arr, 25)), 1),
            'cr_p75': round(float(np.percentile(eff_arr, 75)), 1),
        })

    valid = [r for r in results]
    mean_mismatch = np.mean([r['cr_mismatch'] for r in valid]) if valid else 0
    mean_cv = np.mean([r['cr_cv'] for r in valid]) if valid else 0

    print(f"\n  Population effective CR:")
    print(f"    Mean CR mismatch: {mean_mismatch:+.0%}")
    print(f"    Mean CR CV: {mean_cv:.2f}")

    if abs(mean_mismatch) > 0.2:
        verdict = 'CR_SIGNIFICANTLY_MISCALIBRATED'
    elif abs(mean_mismatch) > 0.1:
        verdict = 'CR_MODERATELY_MISCALIBRATED'
    else:
        verdict = 'CR_APPROXIMATELY_CORRECT'

    print(f"\n  ✓ EXP-1874 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        profiles = [r['cr_profile'] for r in valid]
        effectives = [r['cr_effective'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, profiles, 0.4, label='Profile CR', color='#9E9E9E')
        ax.bar(x + 0.2, effectives, 0.4, label='Effective CR', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Carb Ratio (g/U)')
        ax.set_title('EXP-1874: Profile vs Effective CR')
        ax.legend()

        ax = axes[1]
        mismatches = [r['cr_mismatch'] * 100 for r in valid]
        colors = ['#F44336' if abs(m) > 20 else '#FF9800' if abs(m) > 10 else '#4CAF50'
                  for m in mismatches]
        ax.bar(names, mismatches, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('CR Mismatch (%)')
        ax.set_title('EXP-1874: How Wrong Is the Profile CR?')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig04-effective-cr.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig04-effective-cr.png")

    return {
        'experiment': 'EXP-1874',
        'title': 'Effective CR from Post-Meal Glucose Curves',
        'verdict': verdict,
        'mean_cr_mismatch': round(mean_mismatch, 3),
        'mean_cr_cv': round(mean_cv, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1875: CR Time-of-Day Dependence
# ===========================================================================

def exp_1875(patients, figures_dir):
    """Is CR time-of-day dependent? Breakfast often requires more insulin
    per carb than dinner. Test with 4-period binning.
    """
    print("=" * 70)
    print("EXP-1875: CR Time-of-Day Dependence")
    print("=" * 70)

    results = []
    periods = [
        ('early_morning', 5, 9),    # 5am-9am
        ('late_morning', 9, 12),     # 9am-12pm
        ('afternoon', 12, 17),       # 12pm-5pm
        ('evening', 17, 22),         # 5pm-10pm
    ]

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        meals = find_meals(df, min_carbs=10)

        bolused_meals = [m for m in meals if m['bolus'] > 0.5 and not np.isnan(m['effective_cr'])]
        if len(bolused_meals) < 20:
            print(f"  {name}: insufficient bolused meals ({len(bolused_meals)})")
            continue

        period_crs = {}
        for period_name, start_h, end_h in periods:
            period_meals = [m for m in bolused_meals if start_h <= m['hour'] < end_h]
            if len(period_meals) >= 5:
                crs = [m['effective_cr'] for m in period_meals]
                excs = [m['excursion'] for m in period_meals]
                period_crs[period_name] = {
                    'n': len(period_meals),
                    'median_cr': round(float(np.median(crs)), 1),
                    'median_excursion': round(float(np.median(excs)), 0),
                    'cr_cv': round(float(np.std(crs) / np.mean(crs)), 2),
                }

        if len(period_crs) < 2:
            print(f"  {name}: insufficient period coverage ({list(period_crs.keys())})")
            continue

        crs_by_period = {k: v['median_cr'] for k, v in period_crs.items()}
        if len(crs_by_period) >= 2:
            cr_range = max(crs_by_period.values()) - min(crs_by_period.values())
            cr_range_pct = cr_range / np.mean(list(crs_by_period.values()))
        else:
            cr_range_pct = 0

        print(f"  {name}: {crs_by_period} range={cr_range_pct:.0%}")

        results.append({
            'patient': name,
            'period_crs': period_crs,
            'cr_range_pct': round(float(cr_range_pct), 3),
            'cr_profile': cr_profile,
        })

    valid = [r for r in results]
    mean_range = np.mean([r['cr_range_pct'] for r in valid]) if valid else 0

    # Check if breakfast CR is consistently lower (= needs more insulin)
    breakfast_lower = 0
    for r in valid:
        morning = r['period_crs'].get('early_morning', {}).get('median_cr', np.inf)
        evening = r['period_crs'].get('evening', {}).get('median_cr', 0)
        if morning < evening:
            breakfast_lower += 1

    print(f"\n  Population CR time-of-day:")
    print(f"    Mean CR range across day: {mean_range:.0%}")
    print(f"    Breakfast < evening CR: {breakfast_lower}/{len(valid)}")

    if mean_range > 0.3 and breakfast_lower > len(valid) * 0.6:
        verdict = 'STRONG_CIRCADIAN_CR'
    elif mean_range > 0.15:
        verdict = 'MODERATE_CIRCADIAN_CR'
    else:
        verdict = 'WEAK_CIRCADIAN_CR'

    print(f"\n  ✓ EXP-1875 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(12, 5))

        period_names = ['early_morning', 'late_morning', 'afternoon', 'evening']
        period_labels = ['5-9am', '9am-12pm', '12-5pm', '5-10pm']
        n_patients = len(valid)
        x = np.arange(len(period_names))
        width = 0.8 / n_patients

        for i, r in enumerate(valid):
            values = [r['period_crs'].get(pn, {}).get('median_cr', 0) for pn in period_names]
            ax.bar(x + i * width - 0.4 + width / 2, values, width,
                   label=r['patient'], alpha=0.7)

        ax.set_xticks(x)
        ax.set_xticklabels(period_labels)
        ax.set_ylabel('Median Effective CR (g/U)')
        ax.set_title(f'EXP-1875: CR by Time of Day (range: {mean_range:.0%})')
        ax.legend(fontsize=7, ncol=3)

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig05-time-of-day.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig05-time-of-day.png")

    return {
        'experiment': 'EXP-1875',
        'title': 'CR Time-of-Day Dependence',
        'verdict': verdict,
        'mean_cr_range_pct': round(mean_range, 3),
        'breakfast_lower_count': breakfast_lower,
        'n_valid': len(valid),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1876: AID Loop Compensation Masks CR Errors
# ===========================================================================

def exp_1876(patients, figures_dir):
    """How much does the AID loop compensate for CR errors at meal time?
    Compare pre-meal IOB and temp basal changes around meals.
    """
    print("=" * 70)
    print("EXP-1876: AID Loop Compensation at Meals")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        iob = df.get('iob', pd.Series(0, index=df.index)).fillna(0).values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
        temp_rate = df.get('temp_rate', pd.Series(np.nan, index=df.index)).values

        meals = find_meals(df, min_carbs=10)
        bolused_meals = [m for m in meals if m['bolus'] > 0.5]

        if len(bolused_meals) < 15:
            print(f"  {name}: insufficient meals ({len(bolused_meals)})")
            continue

        # For each meal, track IOB evolution and temp basal behavior
        iob_pre_list = []
        iob_post_list = []
        loop_active_list = []

        for m in bolused_meals:
            idx = m['idx']
            # IOB 1h before meal
            iob_pre = iob[max(0, idx - 12)] if not np.isnan(iob[max(0, idx - 12)]) else 0
            # IOB 2h after meal
            idx_post = min(idx + 24, len(iob) - 1)
            iob_post = iob[idx_post] if not np.isnan(iob[idx_post]) else 0

            # Was loop active? Check temp_rate variance in ±2h window
            tr_window = temp_rate[max(0, idx - 24):min(idx + 24, len(temp_rate))]
            tr_valid = tr_window[np.isfinite(tr_window)]
            loop_active = len(tr_valid) > 10 and np.std(tr_valid) > 0.05

            iob_pre_list.append(iob_pre)
            iob_post_list.append(iob_post)
            loop_active_list.append(loop_active)

        iob_pre_arr = np.array(iob_pre_list)
        iob_post_arr = np.array(iob_post_list)
        loop_active_arr = np.array(loop_active_list)

        # How much extra IOB does the loop add post-meal?
        iob_increase = iob_post_arr - iob_pre_arr
        loop_active_frac = loop_active_arr.mean()

        # Split meals by excursion outcome
        good_meals = [m for m in bolused_meals if m['excursion'] < 50]
        bad_meals = [m for m in bolused_meals if m['excursion'] > 80]

        print(f"  {name}: meals={len(bolused_meals)} loop_active={loop_active_frac:.0%} "
              f"ΔIOB={np.median(iob_increase):.1f}U good={len(good_meals)} bad={len(bad_meals)}")

        results.append({
            'patient': name,
            'n_meals': len(bolused_meals),
            'loop_active_fraction': round(float(loop_active_frac), 2),
            'median_iob_increase': round(float(np.median(iob_increase)), 2),
            'mean_iob_pre': round(float(np.mean(iob_pre_arr)), 2),
            'mean_iob_post': round(float(np.mean(iob_post_arr)), 2),
            'n_good_meals': len(good_meals),
            'n_bad_meals': len(bad_meals),
            'good_fraction': round(len(good_meals) / max(len(bolused_meals), 1), 2),
        })

    valid = [r for r in results]
    mean_loop_active = np.mean([r['loop_active_fraction'] for r in valid]) if valid else 0
    mean_iob_inc = np.mean([r['median_iob_increase'] for r in valid]) if valid else 0

    print(f"\n  Population AID compensation at meals:")
    print(f"    Mean loop active around meals: {mean_loop_active:.0%}")
    print(f"    Mean IOB increase post-meal: {mean_iob_inc:.1f}U")

    if mean_loop_active > 0.7 and abs(mean_iob_inc) > 0.5:
        verdict = 'LOOP_ACTIVELY_COMPENSATES'
    elif mean_loop_active > 0.5:
        verdict = 'LOOP_PARTIALLY_COMPENSATES'
    else:
        verdict = 'LOOP_MINIMAL_COMPENSATION'

    print(f"\n  ✓ EXP-1876 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        pre = [r['mean_iob_pre'] for r in valid]
        post = [r['mean_iob_post'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, pre, 0.4, label='IOB 1h before meal', color='#9E9E9E')
        ax.bar(x + 0.2, post, 0.4, label='IOB 2h after meal', color='#F44336')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('IOB (U)')
        ax.set_title('EXP-1876: IOB Before/After Meals')
        ax.legend()

        ax = axes[1]
        good_fracs = [r['good_fraction'] * 100 for r in valid]
        ax.bar(names, good_fracs, color='#4CAF50')
        ax.axhline(50, color='r', linestyle='--', alpha=0.3, label='50%')
        ax.set_ylabel('Meals with Excursion < 50 mg/dL (%)')
        ax.set_title('EXP-1876: Meal Outcome Quality')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig06-loop-compensation.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig06-loop-compensation.png")

    return {
        'experiment': 'EXP-1876',
        'title': 'AID Loop Compensation at Meals',
        'verdict': verdict,
        'mean_loop_active_fraction': round(mean_loop_active, 2),
        'mean_iob_increase': round(mean_iob_inc, 2),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1877: UAM vs Announced Meal Error Structure
# ===========================================================================

def exp_1877(patients, figures_dir):
    """Compare the glucose prediction error structure between UAM events
    and announced meals. Is the error fundamentally different?
    """
    print("=" * 70)
    print("EXP-1877: UAM vs Announced Meal Error Structure")
    print("=" * 70)

    results = []
    UAM_THRESHOLD = 1.0  # mg/dL per 5-min step (EXP-1320)

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values

        sd = compute_supply_demand(df)
        net = sd['net']
        dg = np.gradient(glucose)
        residual = dg - net

        # Classify timesteps
        dg_smooth = pd.Series(dg).rolling(3, center=True, min_periods=1).mean().values

        # Announced meal window: within 2h of carb entry > 5g
        announced_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            if carbs[i] > 5:
                start = i
                end = min(i + 24, len(glucose))
                announced_mask[start:end] = True

        # UAM: rising glucose without announced carbs
        rising = dg_smooth > UAM_THRESHOLD
        uam_mask = rising & ~announced_mask

        # Compute error in each context
        valid = np.isfinite(residual)
        ann_valid = valid & announced_mask
        uam_valid = valid & uam_mask
        other_valid = valid & ~announced_mask & ~uam_mask

        if ann_valid.sum() < 100 or uam_valid.sum() < 100:
            print(f"  {name}: insufficient events (ann={ann_valid.sum()}, uam={uam_valid.sum()})")
            continue

        ann_rmse = np.sqrt(np.mean(residual[ann_valid] ** 2))
        uam_rmse = np.sqrt(np.mean(residual[uam_valid] ** 2))
        other_rmse = np.sqrt(np.mean(residual[other_valid] ** 2)) if other_valid.sum() > 0 else np.nan

        ann_bias = np.mean(residual[ann_valid])
        uam_bias = np.mean(residual[uam_valid])

        # Key insight: is the error systematic (bias) or random (noise)?
        ann_systematic = abs(ann_bias) / ann_rmse if ann_rmse > 0 else 0
        uam_systematic = abs(uam_bias) / uam_rmse if uam_rmse > 0 else 0

        print(f"  {name}: ann_RMSE={ann_rmse:.1f} uam_RMSE={uam_rmse:.1f} "
              f"other_RMSE={other_rmse:.1f}" if not np.isnan(other_rmse) else f"  {name}: ann_RMSE={ann_rmse:.1f} uam_RMSE={uam_rmse:.1f}",
              f" ann_bias={ann_bias:+.1f} uam_bias={uam_bias:+.1f} "
              f"ann_systematic={ann_systematic:.2f} uam_systematic={uam_systematic:.2f}")

        results.append({
            'patient': name,
            'n_announced': int(ann_valid.sum()),
            'n_uam': int(uam_valid.sum()),
            'announced_rmse': round(float(ann_rmse), 2),
            'uam_rmse': round(float(uam_rmse), 2),
            'other_rmse': round(float(other_rmse), 2) if not np.isnan(other_rmse) else None,
            'announced_bias': round(float(ann_bias), 2),
            'uam_bias': round(float(uam_bias), 2),
            'announced_systematic': round(float(ann_systematic), 3),
            'uam_systematic': round(float(uam_systematic), 3),
        })

    valid = [r for r in results]
    mean_ann_rmse = np.mean([r['announced_rmse'] for r in valid]) if valid else 0
    mean_uam_rmse = np.mean([r['uam_rmse'] for r in valid]) if valid else 0
    mean_ann_sys = np.mean([r['announced_systematic'] for r in valid]) if valid else 0
    mean_uam_sys = np.mean([r['uam_systematic'] for r in valid]) if valid else 0

    print(f"\n  Population error structure:")
    print(f"    Announced meal RMSE: {mean_ann_rmse:.1f} (systematic: {mean_ann_sys:.2f})")
    print(f"    UAM RMSE: {mean_uam_rmse:.1f} (systematic: {mean_uam_sys:.2f})")

    if mean_ann_sys > mean_uam_sys + 0.1:
        verdict = 'ANNOUNCED_MORE_SYSTEMATIC'
    elif mean_uam_sys > mean_ann_sys + 0.1:
        verdict = 'UAM_MORE_SYSTEMATIC'
    else:
        verdict = 'SIMILAR_ERROR_STRUCTURE'

    print(f"\n  ✓ EXP-1877 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        ann_r = [r['announced_rmse'] for r in valid]
        uam_r = [r['uam_rmse'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, ann_r, 0.4, label='Announced meals', color='#4CAF50')
        ax.bar(x + 0.2, uam_r, 0.4, label='UAM events', color='#FF9800')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('RMSE (mg/dL/step)')
        ax.set_title('EXP-1877: Model Error by Context')
        ax.legend()

        ax = axes[1]
        ann_s = [r['announced_systematic'] for r in valid]
        uam_s = [r['uam_systematic'] for r in valid]
        ax.scatter(ann_s, uam_s, s=100, edgecolors='k')
        for i, r in enumerate(valid):
            ax.annotate(r['patient'], (ann_s[i], uam_s[i]), fontsize=9)
        lim = max(max(ann_s + uam_s) * 1.1, 1)
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Announced Systematic Fraction')
        ax.set_ylabel('UAM Systematic Fraction')
        ax.set_title('EXP-1877: Systematic vs Random Error')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig07-uam-vs-announced.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig07-uam-vs-announced.png")

    return {
        'experiment': 'EXP-1877',
        'title': 'UAM vs Announced Meal Error Structure',
        'verdict': verdict,
        'mean_announced_rmse': round(mean_ann_rmse, 2),
        'mean_uam_rmse': round(mean_uam_rmse, 2),
        'mean_announced_systematic': round(mean_ann_sys, 3),
        'mean_uam_systematic': round(mean_uam_sys, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1878: Combined CR Estimator
# ===========================================================================

def exp_1878(patients, figures_dir):
    """Combine multiple signals (excursion, timing, context, loop compensation)
    into a CR estimator and evaluate against profile CR. Temporal validation:
    train on first half, evaluate on second.
    """
    print("=" * 70)
    print("EXP-1878: Combined CR Estimator — Temporal Validation")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)
        mid = len(df) // 2

        df_h1 = df.iloc[:mid].copy()
        df_h2 = df.iloc[mid:].copy()
        df_h1.attrs = dict(df.attrs)
        df_h2.attrs = dict(df.attrs)

        # Estimate CR from each half
        for half_label, df_half in [('h1', df_h1), ('h2', df_h2)]:
            meals = find_meals(df_half, min_carbs=10)
            bolused = [m for m in meals if m['bolus'] > 0.5 and m['excursion'] > 0
                       and not np.isnan(m['effective_cr'])]

            if len(bolused) < 10:
                if half_label == 'h1':
                    break
                continue

            # Method 1: Median effective CR
            crs = np.array([m['effective_cr'] for m in bolused])
            cr_median = np.median(crs)

            # Method 2: Excursion-weighted CR (weight by inverse excursion — good meals count more)
            excursions = np.array([m['excursion'] for m in bolused])
            weights = 1.0 / (excursions + 10)  # avoid div-by-zero
            cr_weighted = np.average(crs, weights=weights)

            # Method 3: Excursion-based CR from insulin equation
            # CR_eff = carbs * ISF / (excursion + bolus * ISF)
            cr_eq_list = []
            for m in bolused:
                denom = m['excursion'] + m['bolus'] * isf_profile
                if denom > 0:
                    cr_eq = m['carbs'] * isf_profile / denom
                    if 1 < cr_eq < 100:
                        cr_eq_list.append(cr_eq)
            cr_equation = np.median(cr_eq_list) if cr_eq_list else np.nan

            if half_label == 'h1':
                cr_h1 = {
                    'median': float(cr_median),
                    'weighted': float(cr_weighted),
                    'equation': float(cr_equation) if not np.isnan(cr_equation) else None,
                    'n': len(bolused),
                }
            else:
                cr_h2 = {
                    'median': float(cr_median),
                    'weighted': float(cr_weighted),
                    'equation': float(cr_equation) if not np.isnan(cr_equation) else None,
                    'n': len(bolused),
                }
        else:
            # Both halves processed
            pass

        if 'cr_h1' not in dir() or 'cr_h2' not in dir():
            print(f"  {name}: insufficient data for temporal validation")
            cr_h1 = cr_h2 = None
            continue

        # Evaluate: apply h1 CR to h2 meals
        # Which h1 estimator best predicts h2 excursions?
        meals_h2 = find_meals(df_h2, min_carbs=10)
        bolused_h2 = [m for m in meals_h2 if m['bolus'] > 0.5 and m['excursion'] > 0]

        if len(bolused_h2) < 10:
            print(f"  {name}: insufficient h2 meals ({len(bolused_h2)})")
            cr_h1 = cr_h2 = None
            continue

        # For each estimator, compute prediction error on h2
        method_errors = {}
        for method_name, cr_est in [('profile', cr_profile),
                                     ('median', cr_h1['median']),
                                     ('weighted', cr_h1['weighted']),
                                     ('equation', cr_h1.get('equation', cr_profile))]:
            if cr_est is None:
                cr_est = cr_profile
            errors = []
            for m in bolused_h2:
                # Predicted excursion
                pred = (m['carbs'] - m['bolus'] * cr_est) * isf_profile / max(cr_est, 1)
                errors.append((m['excursion'] - pred) ** 2)
            method_errors[method_name] = np.sqrt(np.mean(errors))

        best_method = min(method_errors, key=method_errors.get)

        print(f"  {name}: profile_RMSE={method_errors['profile']:.0f} "
              f"median_RMSE={method_errors['median']:.0f} "
              f"weighted_RMSE={method_errors['weighted']:.0f} "
              f"equation_RMSE={method_errors['equation']:.0f} "
              f"best={best_method}")

        results.append({
            'patient': name,
            'cr_profile': cr_profile,
            'cr_h1': cr_h1,
            'cr_h2': cr_h2,
            'method_rmse': {k: round(float(v), 1) for k, v in method_errors.items()},
            'best_method': best_method,
        })

        cr_h1 = cr_h2 = None

    valid = [r for r in results]
    # Count how many times each method wins
    method_wins = {}
    for r in valid:
        m = r['best_method']
        method_wins[m] = method_wins.get(m, 0) + 1

    # Mean improvement of best non-profile over profile
    improvements = []
    for r in valid:
        profile_rmse = r['method_rmse']['profile']
        best_non_profile = min(v for k, v in r['method_rmse'].items() if k != 'profile')
        if profile_rmse > 0:
            improvements.append((profile_rmse - best_non_profile) / profile_rmse * 100)

    mean_improvement = np.mean(improvements) if improvements else 0

    print(f"\n  Population combined CR estimator:")
    print(f"    Method wins: {method_wins}")
    print(f"    Mean improvement over profile: {mean_improvement:.1f}%")

    if mean_improvement > 10:
        verdict = 'CR_ESTIMATOR_IMPROVES'
    elif mean_improvement > 0:
        verdict = 'MARGINAL_IMPROVEMENT'
    else:
        verdict = 'PROFILE_SUFFICIENT'

    print(f"\n  ✓ EXP-1878 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        methods = ['profile', 'median', 'weighted', 'equation']
        x = np.arange(len(names))
        width = 0.2
        for i, method in enumerate(methods):
            vals = [r['method_rmse'].get(method, 0) for r in valid]
            ax.bar(x + i * width - 0.3, vals, width, label=method)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Excursion RMSE (mg/dL)')
        ax.set_title('EXP-1878: CR Estimator Comparison')
        ax.legend(fontsize=8)

        ax = axes[1]
        cats = list(method_wins.keys())
        vals = [method_wins[c] for c in cats]
        ax.bar(cats, vals, color='#4CAF50')
        ax.set_ylabel('Number of Patients')
        ax.set_title(f'EXP-1878: Best Method per Patient (mean impr: {mean_improvement:.0f}%)')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cr-fig08-combined-estimator.png'), dpi=150)
        plt.close()
        print(f"  → Saved cr-fig08-combined-estimator.png")

    return {
        'experiment': 'EXP-1878',
        'title': 'Combined CR Estimator — Temporal Validation',
        'verdict': verdict,
        'method_wins': method_wins,
        'mean_improvement_over_profile': round(mean_improvement, 1),
        'per_patient': results,
    }


# ===========================================================================
# Main
# ===========================================================================

EXPERIMENTS = [
    ('EXP-1871', exp_1871),
    ('EXP-1872', exp_1872),
    ('EXP-1873', exp_1873),
    ('EXP-1874', exp_1874),
    ('EXP-1875', exp_1875),
    ('EXP-1876', exp_1876),
    ('EXP-1877', exp_1877),
    ('EXP-1878', exp_1878),
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
    print("EXP-1871–1878: Carb Ratio Improvement & Meal Analysis")
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

    out_path = 'externals/experiments/exp-1871_cr_improvement.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {out_path}")

    print(f"\n{'=' * 70}")
    print("SYNTHESIS: Carb Ratio Improvement & Meal Analysis")
    print(f"{'=' * 70}")
    for exp_id, result in all_results.items():
        print(f"  {exp_id}: {result.get('verdict', 'N/A')}")
    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
