#!/usr/bin/env python3
"""EXP-1791 to EXP-1796: Context-Adaptive Model and Meal Absorption Improvement.

Follows from EXP-1789 finding that post-meal R²=-20.1 is THE bottleneck
(vs fasting R²=-0.32). This batch tests whether context-aware modeling
can close the gap.

  EXP-1791: Post-meal residual structure — are post-meal residuals systematic
            and learnable, or random noise?  Fit patient-specific absorption
            curve templates from historical meals and measure residual reduction.
  EXP-1792: Context-adaptive R² — switch between models by detected metabolic
            context: fasting uses S×D, post-meal uses absorption template +
            UAM features.  Compare to uniform model.
  EXP-1793: Meal absorption curve diversity — cluster meal responses by shape
            (fast/slow absorbers, fat-delayed, etc.) and test whether per-cluster
            templates improve post-meal R².
  EXP-1794: UAM-aware post-meal model — since 76.5% of meals are unannounced,
            test a model that uses UAM onset detection + glucose acceleration as
            the primary post-meal signal (no carb entry needed).
  EXP-1795: Fasting-weighted therapy assessment — compare therapy recommendations
            derived from all-context analysis vs fasting-only analysis.  Hypothesis:
            fasting-only recommendations are more consistent and actionable.
  EXP-1796: Excursion-type-specific R² — decompose R² by excursion type (from
            our 10-type taxonomy) to find which types the model handles vs fails.

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_context_adaptive_1791.py --figures
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats, optimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path('externals/ns-data/patients')
RESULTS_DIR = Path('externals/experiments')
FIGURES_DIR = Path('docs/60-research/figures')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
LOW, HIGH = 70.0, 180.0


def _get_isf(pat):
    sched = pat['df'].attrs.get('isf_schedule', [])
    if not sched:
        return 50.0
    vals = [e.get('value', e.get('sensitivity', 50)) for e in sched]
    v = float(np.median(vals))
    return v * 18.0182 if v < 15 else v


def _get_cr(pat):
    sched = pat['df'].attrs.get('cr_schedule', [])
    if not sched:
        return 10.0
    vals = [e.get('value', e.get('carbratio', 10)) for e in sched]
    return float(np.median(vals))


# ── Meal detection ───────────────────────────────────────────────────────

def detect_meals(glucose, carbs, min_rise=15.0, window_steps=24):
    """Detect meal events from carb entries or UAM rises.

    Returns list of (start_idx, announced, carb_grams) tuples.
    """
    meals = []

    # Announced meals from carb entries
    for i in range(len(carbs)):
        if carbs[i] > 5:
            meals.append((i, True, float(carbs[i])))

    # UAM meals from rapid glucose rises without carbs
    i = 0
    while i < len(glucose) - 6:
        if np.isnan(glucose[i]):
            i += 1
            continue
        # Check for 15+ mg/dL rise in 30 min
        for j in range(3, min(7, len(glucose) - i)):
            if not np.isnan(glucose[i + j]) and glucose[i + j] - glucose[i] >= min_rise:
                # Check no carbs in recent window
                carb_window = max(0, i - 12)
                if np.sum(carbs[carb_window:i + j]) < 2:
                    meals.append((i, False, 0.0))
                    i = i + j + 6  # skip ahead
                    break
        else:
            i += 1

    # Deduplicate (keep meals >30 min apart)
    meals.sort(key=lambda x: x[0])
    deduped = []
    for m in meals:
        if not deduped or m[0] - deduped[-1][0] >= 6:
            deduped.append(m)
    return deduped


# ── Absorption curve template ────────────────────────────────────────────

def fit_absorption_template(glucose, meal_idx, window_h=4):
    """Fit a mean absorption residual curve from meal events.

    Returns (template, n_meals) where template is the mean dBG profile
    over window_h hours following meal onset.
    """
    window_steps = window_h * STEPS_PER_HOUR
    profiles = []

    for idx, _, _ in meal_idx:
        if idx + window_steps > len(glucose):
            continue
        window = glucose[idx:idx + window_steps]
        if np.sum(np.isnan(window)) > window_steps * 0.3:
            continue
        # Relative to starting glucose
        profile = window - glucose[idx]
        # Linear interpolation for NaN gaps
        nans = np.isnan(profile)
        if nans.any() and not nans.all():
            profile[nans] = np.interp(
                np.where(nans)[0],
                np.where(~nans)[0],
                profile[~nans]
            )
        profiles.append(profile)

    if len(profiles) < 5:
        return np.zeros(window_steps), len(profiles)

    return np.nanmean(profiles, axis=0), len(profiles)


def gamma_absorption(t, peak_time, amplitude, shape=2.0):
    """Gamma-function absorption curve. t in steps, peak_time in steps."""
    rate = shape / max(peak_time, 1)
    curve = amplitude * (rate * t) ** (shape - 1) * np.exp(-rate * t) / max(
        np.max((rate * t) ** (shape - 1) * np.exp(-rate * t)), 1e-10)
    return curve


# ── Metabolic context classification (reused from EXP-1789) ─────────────

CONTEXT_NAMES = ['fasting', 'post_meal', 'correction', 'hypo_recovery',
                 'exercise_like', 'stable']


def classify_metabolic_context(glucose, carbs, iob, bolus):
    N = len(glucose)
    ctx = np.full(N, 5, dtype=np.int32)
    for i in range(N):
        g = glucose[i]
        if np.isnan(g):
            continue
        carb_window_2h = max(0, i - 24)
        carb_window_3h = max(0, i - 36)
        recent_carbs_2h = np.nansum(carbs[carb_window_2h:i + 1])
        recent_carbs_3h = np.nansum(carbs[carb_window_3h:i + 1])
        bolus_window = max(0, i - 12)
        recent_bolus = np.nansum(bolus[bolus_window:i + 1])
        recent_carbs_1h = np.nansum(carbs[bolus_window:i + 1])
        hypo_window = max(0, i - 6)
        recent_hypo = np.any(glucose[hypo_window:i + 1] < 80)
        if i >= 3:
            trend = (glucose[i] - glucose[max(0, i - 3)]) / 3.0
        else:
            trend = 0.0
        if recent_hypo and g < 100:
            ctx[i] = 3
        elif recent_carbs_2h > 2:
            ctx[i] = 1
        elif recent_bolus > 0.5 and recent_carbs_1h < 2:
            ctx[i] = 2
        elif recent_carbs_3h < 2 and iob[i] < 0.5:
            ctx[i] = 0
        elif trend < -1.0 and iob[i] < 0.3 and recent_carbs_2h < 2:
            ctx[i] = 4
    return ctx


# ── Experiment implementations ───────────────────────────────────────────

def exp_1791_postmeal_residual_structure(patients):
    """Post-meal residual structure: systematic or random?"""
    print("\n=== EXP-1791: Post-Meal Residual Structure ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df)
        net = sd['net']

        # Actual dBG
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]
        residual = dbg - net

        # Detect meals
        meals = detect_meals(glucose, carbs)
        announced = [m for m in meals if m[1]]
        uam = [m for m in meals if not m[1]]

        # Fit absorption template (mean residual profile after meals)
        template_all, n_all = fit_absorption_template(glucose, meals, window_h=4)
        template_ann, n_ann = fit_absorption_template(glucose, announced, window_h=4)

        # Fit residual template (mean model residual after meals)
        window_steps = 4 * STEPS_PER_HOUR
        residual_profiles = []
        for idx, _, _ in meals:
            if idx + window_steps > len(residual):
                continue
            rp = residual[idx:idx + window_steps]
            if np.sum(np.isnan(rp)) < window_steps * 0.3:
                nans = np.isnan(rp)
                if nans.any() and not nans.all():
                    rp = rp.copy()
                    rp[nans] = np.interp(np.where(nans)[0],
                                         np.where(~nans)[0], rp[~nans])
                residual_profiles.append(rp)

        if len(residual_profiles) < 10:
            results.append({'name': name, 'n_meals': len(meals), 'status': 'insufficient'})
            print(f"  {name}: insufficient meal profiles ({len(residual_profiles)})")
            continue

        mean_residual = np.mean(residual_profiles, axis=0)
        # How much of post-meal residual is systematic (captured by template)?
        # R² of template fit to individual residuals
        ss_res_template = 0
        ss_tot = 0
        for rp in residual_profiles:
            ss_res_template += np.sum((rp - mean_residual) ** 2)
            ss_tot += np.sum((rp - np.mean(rp)) ** 2)

        template_r2 = 1.0 - ss_res_template / max(ss_tot, 1e-10)

        # Peak residual timing and magnitude
        peak_idx = np.argmax(np.abs(mean_residual))
        peak_time_min = peak_idx * 5
        peak_magnitude = mean_residual[peak_idx]

        # How much variance would template subtraction remove?
        # Original post-meal R² vs template-corrected
        postmeal_dbg = []
        postmeal_net = []
        postmeal_corrected = []
        for idx, _, _ in meals:
            for t in range(min(window_steps, len(dbg) - idx)):
                if not np.isnan(dbg[idx + t]):
                    postmeal_dbg.append(dbg[idx + t])
                    postmeal_net.append(net[idx + t])
                    postmeal_corrected.append(net[idx + t] + mean_residual[t])

        if len(postmeal_dbg) > 100:
            pm_actual = np.array(postmeal_dbg)
            pm_net = np.array(postmeal_net)
            pm_corrected = np.array(postmeal_corrected)

            ss_tot_pm = np.sum((pm_actual - np.mean(pm_actual)) ** 2)
            r2_before = 1.0 - np.sum((pm_actual - pm_net) ** 2) / max(ss_tot_pm, 1e-10)
            r2_after = 1.0 - np.sum((pm_actual - pm_corrected) ** 2) / max(ss_tot_pm, 1e-10)
        else:
            r2_before = r2_after = None

        results.append({
            'name': name,
            'n_meals': len(meals),
            'n_announced': len(announced),
            'n_uam': len(uam),
            'n_profiles': len(residual_profiles),
            'template_r2': float(template_r2),
            'peak_time_min': int(peak_time_min),
            'peak_magnitude': float(peak_magnitude),
            'postmeal_r2_before': float(r2_before) if r2_before is not None else None,
            'postmeal_r2_after': float(r2_after) if r2_after is not None else None,
        })

        improvement = (r2_after - r2_before) if r2_before is not None and r2_after is not None else 0
        print(f"  {name}: {len(meals)} meals, template R²={template_r2:.3f}, "
              f"peak at {peak_time_min}min ({peak_magnitude:+.1f} mg/dL/step), "
              f"post-meal R²: {r2_before:.2f} → {r2_after:.2f} ({improvement:+.3f})"
              if r2_before is not None else f"  {name}: {len(meals)} meals, template R²={template_r2:.3f}")

    # Population summary
    valid = [r for r in results if r.get('postmeal_r2_before') is not None]
    if valid:
        mean_before = np.mean([r['postmeal_r2_before'] for r in valid])
        mean_after = np.mean([r['postmeal_r2_after'] for r in valid])
        mean_template_r2 = np.mean([r['template_r2'] for r in valid])
        improved = sum(1 for r in valid if r['postmeal_r2_after'] > r['postmeal_r2_before'])
        print(f"\n  Population: template R²={mean_template_r2:.3f}")
        print(f"  Post-meal R²: {mean_before:.2f} → {mean_after:.2f}")
        print(f"  Improved: {improved}/{len(valid)} patients")

    exp_result = {
        'experiment': 'EXP-1791',
        'title': 'Post-Meal Residual Structure',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1791_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1792_context_adaptive_model(patients):
    """Context-adaptive model: switch strategies by metabolic context."""
    print("\n=== EXP-1792: Context-Adaptive Model ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0) if 'bolus' in df.columns else np.zeros(len(glucose))

        sd = compute_supply_demand(df)
        net = sd['net']
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        ctx = classify_metabolic_context(glucose, carbs, iob, bolus)
        valid = ~np.isnan(glucose) & ~np.isnan(dbg)
        valid[0] = False

        # Strategy 1: Uniform model (S×D everywhere)
        r2_uniform_by_ctx = {}
        for c_idx, c_name in enumerate(CONTEXT_NAMES):
            mask = valid & (ctx == c_idx)
            n = mask.sum()
            if n < 50:
                r2_uniform_by_ctx[c_name] = {'n': int(n), 'r2': None}
                continue
            actual = dbg[mask]
            predicted = net[mask]
            ss_res = np.sum((actual - predicted) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            r2_uniform_by_ctx[c_name] = {
                'n': int(n),
                'r2': float(1.0 - ss_res / max(ss_tot, 1e-10)),
            }

        # Strategy 2: Context-adaptive
        # Fasting: use S×D (it's best there)
        # Post-meal: use template-corrected S×D
        # Correction: scale demand by AID dampening factor
        # Hypo recovery: use zero prediction (mean dBG ≈ 0 during recovery)
        # Stable: use S×D

        # Fit post-meal template
        meals = detect_meals(glucose, carbs)
        window_steps = 4 * STEPS_PER_HOUR
        residual_profiles = []
        for idx, _, _ in meals:
            if idx + window_steps > len(dbg):
                continue
            rp = (dbg - net)[idx:idx + window_steps]
            if np.sum(np.isnan(rp)) < window_steps * 0.3:
                nans = np.isnan(rp)
                if nans.any() and not nans.all():
                    rp = rp.copy()
                    rp[nans] = np.interp(np.where(nans)[0],
                                         np.where(~nans)[0], rp[~nans])
                residual_profiles.append(rp)

        mean_template = np.mean(residual_profiles, axis=0) if len(residual_profiles) >= 5 else np.zeros(window_steps)

        # Build adaptive predictions
        adaptive_pred = net.copy()

        # Post-meal: add template correction for recent meals
        for idx, _, _ in meals:
            for t in range(min(window_steps, len(adaptive_pred) - idx)):
                if ctx[idx + t] == 1:  # post_meal context
                    adaptive_pred[idx + t] += mean_template[t]

        # Correction: scale demand by 0.6 (AID typically reduces basal by ~40% during corrections)
        correction_mask = ctx == 2
        adaptive_pred[correction_mask] *= 0.6

        # Hypo recovery: predict zero change (counter-reg + rescue = unpredictable)
        recovery_mask = ctx == 3
        adaptive_pred[recovery_mask] = 0.0

        # Measure context-specific R² for adaptive model
        r2_adaptive_by_ctx = {}
        for c_idx, c_name in enumerate(CONTEXT_NAMES):
            mask = valid & (ctx == c_idx)
            n = mask.sum()
            if n < 50:
                r2_adaptive_by_ctx[c_name] = {'n': int(n), 'r2': None}
                continue
            actual = dbg[mask]
            predicted = adaptive_pred[mask]
            ss_res = np.sum((actual - predicted) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            r2_adaptive_by_ctx[c_name] = {
                'n': int(n),
                'r2': float(1.0 - ss_res / max(ss_tot, 1e-10)),
            }

        # Overall R²
        overall_mask = valid
        actual_all = dbg[overall_mask]
        ss_tot_all = np.sum((actual_all - np.mean(actual_all)) ** 2)
        r2_uniform_overall = 1.0 - np.sum((actual_all - net[overall_mask]) ** 2) / max(ss_tot_all, 1e-10)
        r2_adaptive_overall = 1.0 - np.sum((actual_all - adaptive_pred[overall_mask]) ** 2) / max(ss_tot_all, 1e-10)

        results.append({
            'name': name,
            'n_meals': len(meals),
            'n_meal_profiles': len(residual_profiles),
            'r2_uniform_overall': float(r2_uniform_overall),
            'r2_adaptive_overall': float(r2_adaptive_overall),
            'r2_improvement': float(r2_adaptive_overall - r2_uniform_overall),
            'uniform_by_context': r2_uniform_by_ctx,
            'adaptive_by_context': r2_adaptive_by_ctx,
        })

        print(f"  {name}: uniform R²={r2_uniform_overall:.3f} → adaptive R²={r2_adaptive_overall:.3f} "
              f"({r2_adaptive_overall - r2_uniform_overall:+.3f})")

    # Summary
    valid = [r for r in results if r.get('r2_improvement') is not None]
    if valid:
        mean_uniform = np.mean([r['r2_uniform_overall'] for r in valid])
        mean_adaptive = np.mean([r['r2_adaptive_overall'] for r in valid])
        improved = sum(1 for r in valid if r['r2_improvement'] > 0)
        print(f"\n  Population: uniform R²={mean_uniform:.3f} → adaptive R²={mean_adaptive:.3f}")
        print(f"  Improved: {improved}/{len(valid)} patients")

        # Context-level comparison
        for c_name in CONTEXT_NAMES:
            u_r2s = [r['uniform_by_context'][c_name]['r2'] for r in valid
                     if r['uniform_by_context'][c_name].get('r2') is not None]
            a_r2s = [r['adaptive_by_context'][c_name]['r2'] for r in valid
                     if r['adaptive_by_context'][c_name].get('r2') is not None]
            if u_r2s and a_r2s:
                print(f"    {c_name:20s}: {np.mean(u_r2s):+.3f} → {np.mean(a_r2s):+.3f}")

    exp_result = {
        'experiment': 'EXP-1792',
        'title': 'Context-Adaptive Model',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1792_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1793_meal_absorption_diversity(patients):
    """Cluster meal responses by absorption shape."""
    print("\n=== EXP-1793: Meal Absorption Curve Diversity ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        meals = detect_meals(glucose, carbs)
        window_steps = 3 * STEPS_PER_HOUR  # 3h window

        # Extract glucose profiles after meals
        profiles = []
        for idx, announced, carb_g in meals:
            if idx + window_steps > len(glucose):
                continue
            window = glucose[idx:idx + window_steps]
            if np.sum(np.isnan(window)) > window_steps * 0.3:
                continue
            profile = window - glucose[idx]
            nans = np.isnan(profile)
            if nans.any() and not nans.all():
                profile = profile.copy()
                profile[nans] = np.interp(np.where(nans)[0],
                                          np.where(~nans)[0], profile[~nans])
            profiles.append({
                'profile': profile,
                'announced': announced,
                'carb_g': carb_g,
                'peak_time': int(np.argmax(profile)) * 5,
                'peak_magnitude': float(np.max(profile)),
                'return_time': int(np.argmax(profile < 0) * 5) if np.any(profile < 0) else window_steps * 5,
            })

        if len(profiles) < 20:
            results.append({'name': name, 'n_meals': len(meals), 'status': 'insufficient'})
            continue

        # Classify by peak timing
        peak_times = [p['peak_time'] for p in profiles]
        peak_mags = [p['peak_magnitude'] for p in profiles]

        # Simple classification: fast (<45min peak), medium (45-90), slow (>90)
        fast = [p for p in profiles if p['peak_time'] < 45]
        medium = [p for p in profiles if 45 <= p['peak_time'] < 90]
        slow = [p for p in profiles if p['peak_time'] >= 90]

        results.append({
            'name': name,
            'n_meals': len(profiles),
            'n_fast': len(fast),
            'n_medium': len(medium),
            'n_slow': len(slow),
            'fast_fraction': len(fast) / len(profiles),
            'medium_fraction': len(medium) / len(profiles),
            'slow_fraction': len(slow) / len(profiles),
            'mean_peak_time': float(np.mean(peak_times)),
            'std_peak_time': float(np.std(peak_times)),
            'mean_peak_magnitude': float(np.mean(peak_mags)),
            'fast_mean_peak': float(np.mean([p['peak_magnitude'] for p in fast])) if fast else None,
            'slow_mean_peak': float(np.mean([p['peak_magnitude'] for p in slow])) if slow else None,
        })

        print(f"  {name}: {len(profiles)} meals — fast={len(fast)} ({len(fast)/len(profiles)*100:.0f}%), "
              f"medium={len(medium)}, slow={len(slow)}, "
              f"mean peak={np.mean(peak_times):.0f}min ±{np.std(peak_times):.0f}")

    # Population
    valid = [r for r in results if r.get('mean_peak_time') is not None]
    if valid:
        pop_peak = np.mean([r['mean_peak_time'] for r in valid])
        pop_std = np.mean([r['std_peak_time'] for r in valid])
        pop_fast = np.mean([r['fast_fraction'] for r in valid])
        print(f"\n  Population: mean peak={pop_peak:.0f}min ±{pop_std:.0f}")
        print(f"  Fast absorbers: {pop_fast*100:.0f}% of meals")

    exp_result = {
        'experiment': 'EXP-1793',
        'title': 'Meal Absorption Curve Diversity',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1793_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1794_uam_postmeal_model(patients):
    """UAM-aware post-meal model (no carb entry needed).

    Uses glucose acceleration (second derivative) as the primary signal
    for detecting and characterizing meal absorption.
    """
    print("\n=== EXP-1794: UAM-Aware Post-Meal Model ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0) if 'bolus' in df.columns else np.zeros(len(glucose))

        sd = compute_supply_demand(df)
        net = sd['net']
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        # Compute acceleration (second derivative)
        accel = np.zeros_like(glucose)
        accel[2:] = dbg[2:] - dbg[1:-1]

        # Residual = actual - model
        residual = dbg - net

        # UAM detection: residual > 1.0 mg/dL/step AND acceleration > 0.5
        uam_onset = (residual > 1.0) & (accel > 0.3)

        # For UAM periods, use residual persistence model:
        # prediction = net + running_mean(recent_residual, 6 steps)
        uam_pred = net.copy()
        running_residual = np.zeros_like(residual)
        alpha = 0.3  # EMA decay
        for i in range(1, len(residual)):
            if not np.isnan(residual[i]):
                running_residual[i] = alpha * residual[i] + (1 - alpha) * running_residual[i - 1]
            else:
                running_residual[i] = running_residual[i - 1]

        # Apply UAM correction where UAM detected (and for 12 steps after)
        uam_active = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            if uam_onset[i]:
                end = min(i + 12, len(glucose))
                uam_active[i:end] = True

        uam_pred[uam_active] = net[uam_active] + running_residual[uam_active]

        ctx = classify_metabolic_context(glucose, carbs, iob, bolus)
        valid = ~np.isnan(glucose) & ~np.isnan(dbg)
        valid[0] = False

        # Compare models on post-meal context
        postmeal = valid & (ctx == 1)
        if postmeal.sum() < 100:
            results.append({'name': name, 'status': 'insufficient'})
            continue

        actual_pm = dbg[postmeal]
        ss_tot_pm = np.sum((actual_pm - np.mean(actual_pm)) ** 2)
        r2_base_pm = 1.0 - np.sum((actual_pm - net[postmeal]) ** 2) / max(ss_tot_pm, 1e-10)
        r2_uam_pm = 1.0 - np.sum((actual_pm - uam_pred[postmeal]) ** 2) / max(ss_tot_pm, 1e-10)

        # Overall comparison
        actual_all = dbg[valid]
        ss_tot_all = np.sum((actual_all - np.mean(actual_all)) ** 2)
        r2_base_all = 1.0 - np.sum((actual_all - net[valid]) ** 2) / max(ss_tot_all, 1e-10)
        r2_uam_all = 1.0 - np.sum((actual_all - uam_pred[valid]) ** 2) / max(ss_tot_all, 1e-10)

        uam_frac = uam_active[valid].mean()

        results.append({
            'name': name,
            'uam_active_fraction': float(uam_frac),
            'postmeal_r2_base': float(r2_base_pm),
            'postmeal_r2_uam': float(r2_uam_pm),
            'postmeal_improvement': float(r2_uam_pm - r2_base_pm),
            'overall_r2_base': float(r2_base_all),
            'overall_r2_uam': float(r2_uam_all),
            'overall_improvement': float(r2_uam_all - r2_base_all),
        })

        print(f"  {name}: UAM active {uam_frac*100:.0f}%, "
              f"post-meal R²: {r2_base_pm:.2f} → {r2_uam_pm:.2f} ({r2_uam_pm - r2_base_pm:+.3f}), "
              f"overall: {r2_base_all:.3f} → {r2_uam_all:.3f}")

    valid = [r for r in results if r.get('postmeal_improvement') is not None]
    if valid:
        mean_pm_before = np.mean([r['postmeal_r2_base'] for r in valid])
        mean_pm_after = np.mean([r['postmeal_r2_uam'] for r in valid])
        mean_overall_before = np.mean([r['overall_r2_base'] for r in valid])
        mean_overall_after = np.mean([r['overall_r2_uam'] for r in valid])
        improved = sum(1 for r in valid if r['postmeal_improvement'] > 0)
        print(f"\n  Population post-meal: {mean_pm_before:.2f} → {mean_pm_after:.2f}")
        print(f"  Population overall: {mean_overall_before:.3f} → {mean_overall_after:.3f}")
        print(f"  Improved: {improved}/{len(valid)} patients")

    exp_result = {
        'experiment': 'EXP-1794',
        'title': 'UAM-Aware Post-Meal Model',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1794_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1795_fasting_weighted_therapy(patients):
    """Fasting-weighted vs all-context therapy assessment.

    Since fasting R² is 62× better than post-meal, therapy recommendations
    derived from fasting windows should be more reliable.
    """
    print("\n=== EXP-1795: Fasting-Weighted Therapy Assessment ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0) if 'bolus' in df.columns else np.zeros(len(glucose))

        isf = _get_isf(pat)
        cr = _get_cr(pat)

        ctx = classify_metabolic_context(glucose, carbs, iob, bolus)
        sd = compute_supply_demand(df)
        net = sd['net']
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        valid = ~np.isnan(glucose) & ~np.isnan(dbg)
        valid[0] = False

        # Measure "effective ISF" by context
        # During fasting: effective_isf = observed glucose lowering per unit IOB change
        context_isf = {}
        for c_idx, c_name in enumerate(CONTEXT_NAMES):
            mask = valid & (ctx == c_idx)
            n = mask.sum()
            if n < 100:
                context_isf[c_name] = {'n': int(n), 'effective_isf': None, 'bias': None}
                continue

            actual = dbg[mask]
            modeled = net[mask]
            bias = float(np.mean(actual - modeled))

            # Effective ISF: glucose change per unit IOB change
            diob = np.zeros_like(iob)
            diob[1:] = iob[1:] - iob[:-1]
            diob_ctx = diob[mask]
            dbg_ctx = actual

            # Where IOB is changing meaningfully
            active_insulin = np.abs(diob_ctx) > 0.01
            if active_insulin.sum() > 50:
                # Linear regression: dbg = slope * diob
                slope, _, r, p, _ = stats.linregress(diob_ctx[active_insulin],
                                                      dbg_ctx[active_insulin])
                eff_isf = abs(slope) if p < 0.05 else None
            else:
                eff_isf = None

            context_isf[c_name] = {
                'n': int(n),
                'effective_isf': float(eff_isf) if eff_isf is not None else None,
                'bias': float(bias),
                'mean_glucose': float(np.mean(glucose[mask][~np.isnan(glucose[mask])])),
            }

        # Fasting-derived recommendation
        fasting_bias = context_isf['fasting'].get('bias', 0) if context_isf['fasting'].get('bias') is not None else 0
        fasting_isf = context_isf['fasting'].get('effective_isf')

        # All-context recommendation
        all_biases = [c['bias'] for c in context_isf.values() if c.get('bias') is not None]
        all_context_bias = np.mean(all_biases) if all_biases else 0

        # ISF mismatch
        isf_mismatch_fasting = fasting_isf / isf if fasting_isf and isf > 0 else None
        all_isfs = [c['effective_isf'] for c in context_isf.values() if c.get('effective_isf') is not None]
        isf_mismatch_all = np.mean(all_isfs) / isf if all_isfs and isf > 0 else None

        # Consistency: variance of ISF across contexts
        isf_consistency = np.std(all_isfs) / np.mean(all_isfs) if len(all_isfs) >= 2 else None

        results.append({
            'name': name,
            'profile_isf': float(isf),
            'profile_cr': float(cr),
            'context_isf': context_isf,
            'fasting_bias': float(fasting_bias),
            'all_context_bias': float(all_context_bias),
            'isf_mismatch_fasting': float(isf_mismatch_fasting) if isf_mismatch_fasting else None,
            'isf_mismatch_all': float(isf_mismatch_all) if isf_mismatch_all else None,
            'isf_consistency_cv': float(isf_consistency) if isf_consistency else None,
        })

        print(f"  {name}: fasting bias={fasting_bias:+.2f}, all bias={all_context_bias:+.2f}, "
              f"ISF mismatch: fasting={isf_mismatch_fasting:.2f}×, all={isf_mismatch_all:.2f}×"
              if isf_mismatch_fasting and isf_mismatch_all else
              f"  {name}: fasting bias={fasting_bias:+.2f}")

    valid = [r for r in results if r.get('isf_consistency_cv') is not None]
    if valid:
        mean_cv = np.mean([r['isf_consistency_cv'] for r in valid])
        print(f"\n  Population ISF consistency CV across contexts: {mean_cv:.2f}")
        print(f"  (Lower = more consistent across contexts)")

    exp_result = {
        'experiment': 'EXP-1795',
        'title': 'Fasting-Weighted Therapy Assessment',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1795_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1796_excursion_type_r2(patients):
    """R² by excursion type from our 10-type taxonomy."""
    print("\n=== EXP-1796: Excursion-Type-Specific R² ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0) if 'bolus' in df.columns else np.zeros(len(glucose))

        sd = compute_supply_demand(df)
        net = sd['net']
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        # Simple excursion type classification
        ctx = classify_metabolic_context(glucose, carbs, iob, bolus)

        # Tag excursion windows
        # Rise excursions: 3+ consecutive steps with dBG > 0.5
        # Fall excursions: 3+ consecutive steps with dBG < -0.5
        excursion_type = np.full(len(glucose), 'none', dtype='U20')

        for i in range(3, len(glucose)):
            if np.isnan(dbg[i]):
                continue

            # Classify based on context + direction
            direction = 'rise' if dbg[i] > 0.5 else ('fall' if dbg[i] < -0.5 else 'flat')

            if direction == 'rise':
                if ctx[i] == 1:  # post_meal
                    excursion_type[i] = 'meal_rise'
                elif ctx[i] == 3:  # hypo_recovery
                    excursion_type[i] = 'recovery_rise'
                elif carbs[max(0, i - 36):i].sum() < 2 and iob[i] < 0.5:
                    excursion_type[i] = 'uam_rise'
                else:
                    excursion_type[i] = 'other_rise'
            elif direction == 'fall':
                if ctx[i] == 2:  # correction
                    excursion_type[i] = 'correction_fall'
                elif glucose[i] < 85:
                    excursion_type[i] = 'hypo_fall'
                elif iob[i] > 2.0:
                    excursion_type[i] = 'insulin_fall'
                else:
                    excursion_type[i] = 'natural_fall'

        # Compute R² by excursion type
        valid = ~np.isnan(glucose) & ~np.isnan(dbg)
        valid[0] = False

        type_r2 = {}
        for etype in ['meal_rise', 'uam_rise', 'recovery_rise', 'other_rise',
                       'correction_fall', 'hypo_fall', 'insulin_fall', 'natural_fall']:
            mask = valid & (excursion_type == etype)
            n = mask.sum()
            if n < 50:
                type_r2[etype] = {'n': int(n), 'r2': None}
                continue

            actual = dbg[mask]
            predicted = net[mask]
            ss_res = np.sum((actual - predicted) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            r2 = 1.0 - ss_res / max(ss_tot, 1e-10)
            rmse = np.sqrt(np.mean((actual - predicted) ** 2))

            type_r2[etype] = {
                'n': int(n),
                'r2': float(r2),
                'rmse': float(rmse),
                'fraction': float(n / valid.sum()),
            }

        results.append({
            'name': name,
            'type_r2': type_r2,
        })

        # Find best and worst
        typed = {k: v for k, v in type_r2.items() if v.get('r2') is not None}
        if typed:
            best = max(typed.items(), key=lambda x: x[1]['r2'])
            worst = min(typed.items(), key=lambda x: x[1]['r2'])
            print(f"  {name}: best={best[0]} R²={best[1]['r2']:.3f}, "
                  f"worst={worst[0]} R²={worst[1]['r2']:.3f}")

    # Population summary
    print(f"\n  Excursion-type R² (population mean):")
    for etype in ['meal_rise', 'uam_rise', 'recovery_rise', 'other_rise',
                   'correction_fall', 'hypo_fall', 'insulin_fall', 'natural_fall']:
        r2s = [r['type_r2'][etype]['r2'] for r in results
               if r['type_r2'][etype].get('r2') is not None]
        if r2s:
            print(f"    {etype:20s}: R²={np.mean(r2s):+.3f} ({len(r2s)}/{len(results)} patients)")

    exp_result = {
        'experiment': 'EXP-1796',
        'title': 'Excursion-Type-Specific R²',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1796_context_adaptive.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(all_results):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Figure 14: Context-adaptive comparison (EXP-1792)
    r1792 = all_results.get('1792')
    if r1792:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        valid = r1792['patients']
        names = [r['name'] for r in valid]
        uniform = [r['r2_uniform_overall'] for r in valid]
        adaptive = [r['r2_adaptive_overall'] for r in valid]

        x = np.arange(len(names))
        w = 0.35
        axes[0].bar(x - w/2, uniform, w, label='Uniform S×D', color='#F44336', alpha=0.8)
        axes[0].bar(x + w/2, adaptive, w, label='Context-adaptive', color='#4CAF50', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('R²')
        axes[0].set_title('Overall Model R²')
        axes[0].legend()
        axes[0].axhline(0, color='black', linewidth=0.5)

        # Context-level comparison
        ctx_data = {c: {'uniform': [], 'adaptive': []} for c in CONTEXT_NAMES}
        for r in valid:
            for c in CONTEXT_NAMES:
                u = r['uniform_by_context'][c].get('r2')
                a = r['adaptive_by_context'][c].get('r2')
                if u is not None:
                    ctx_data[c]['uniform'].append(u)
                if a is not None:
                    ctx_data[c]['adaptive'].append(a)

        ctx_names_plot = [c for c in CONTEXT_NAMES if ctx_data[c]['uniform']]
        u_means = [np.mean(ctx_data[c]['uniform']) for c in ctx_names_plot]
        a_means = [np.mean(ctx_data[c]['adaptive']) for c in ctx_names_plot]

        x2 = np.arange(len(ctx_names_plot))
        axes[1].bar(x2 - w/2, u_means, w, label='Uniform', color='#F44336', alpha=0.8)
        axes[1].bar(x2 + w/2, a_means, w, label='Adaptive', color='#4CAF50', alpha=0.8)
        axes[1].set_xticks(x2)
        axes[1].set_xticklabels(ctx_names_plot, rotation=45, ha='right')
        axes[1].set_ylabel('R²')
        axes[1].set_title('R² by Metabolic Context')
        axes[1].legend()
        axes[1].axhline(0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'context-fig14-adaptive-comparison.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'context-fig14-adaptive-comparison.png'}")

    # Figure 15: Meal absorption diversity (EXP-1793) + UAM model (EXP-1794)
    r1793 = all_results.get('1793')
    r1794 = all_results.get('1794')
    if r1793 or r1794:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        if r1793:
            valid = [r for r in r1793['patients'] if r.get('mean_peak_time') is not None]
            names = [r['name'] for r in valid]
            peak_times = [r['mean_peak_time'] for r in valid]
            peak_stds = [r['std_peak_time'] for r in valid]

            axes[0].bar(range(len(names)), peak_times, yerr=peak_stds,
                       color='#FF9800', capsize=3)
            axes[0].set_xticks(range(len(names)))
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Peak absorption time (min)')
            axes[0].set_title('Meal Absorption Timing\n(mean ± std per patient)')

        if r1794:
            valid = [r for r in r1794['patients'] if r.get('postmeal_improvement') is not None]
            names = [r['name'] for r in valid]
            improvements = [r['postmeal_improvement'] for r in valid]
            colors = ['#4CAF50' if i > 0 else '#F44336' for i in improvements]

            axes[1].bar(range(len(names)), improvements, color=colors)
            axes[1].set_xticks(range(len(names)))
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Post-meal R² improvement')
            axes[1].set_title('UAM-Aware Model\nPost-Meal R² Change')
            axes[1].axhline(0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'context-fig15-meal-diversity-uam.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'context-fig15-meal-diversity-uam.png'}")

    # Figure 16: Excursion-type R² (EXP-1796)
    r1796 = all_results.get('1796')
    if r1796:
        fig, ax = plt.subplots(figsize=(10, 5))

        etypes = ['meal_rise', 'uam_rise', 'recovery_rise', 'other_rise',
                  'correction_fall', 'hypo_fall', 'insulin_fall', 'natural_fall']
        mean_r2 = []
        for et in etypes:
            r2s = [r['type_r2'][et]['r2'] for r in r1796['patients']
                   if r['type_r2'][et].get('r2') is not None]
            mean_r2.append(np.mean(r2s) if r2s else 0)

        colors = ['#FF9800', '#FF5722', '#4CAF50', '#9E9E9E',
                  '#2196F3', '#F44336', '#3F51B5', '#607D8B']
        ax.barh(range(len(etypes)), mean_r2, color=colors)
        ax.set_yticks(range(len(etypes)))
        ax.set_yticklabels(etypes)
        ax.set_xlabel('R² (population mean)')
        ax.set_title('Supply/Demand Model R² by Excursion Type')
        ax.axvline(0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'context-fig16-excursion-type-r2.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'context-fig16-excursion-type-r2.png'}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1791–1796: Context-Adaptive Model')
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--experiments', type=str, default='all')
    args = parser.parse_args()

    print("Loading patient data...")
    patients = load_patients(str(PATIENTS_DIR))

    exp_map = {
        '1791': exp_1791_postmeal_residual_structure,
        '1792': exp_1792_context_adaptive_model,
        '1793': exp_1793_meal_absorption_diversity,
        '1794': exp_1794_uam_postmeal_model,
        '1795': exp_1795_fasting_weighted_therapy,
        '1796': exp_1796_excursion_type_r2,
    }

    if args.experiments == 'all':
        to_run = list(exp_map.keys())
    else:
        to_run = [e.strip() for e in args.experiments.split(',')]

    all_results = {}
    for exp_id in to_run:
        if exp_id in exp_map:
            result = exp_map[exp_id](patients)
            all_results[exp_id] = result

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(all_results)

    print("\n=== All experiments complete ===")


if __name__ == '__main__':
    main()
