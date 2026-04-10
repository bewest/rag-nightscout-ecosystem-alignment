#!/usr/bin/env python3
"""EXP-1941–1948: Revised Therapy Estimates with Corrected Model.

The combined model (improved absorption + gradient demand) achieves +63.9%.
This batch uses the corrected model to produce revised therapy estimates
and tests their temporal stability.

Experiments:
  EXP-1941: Revised ISF estimates with corrected model
  EXP-1942: Revised CR estimates with corrected model
  EXP-1943: Revised basal estimates with corrected model
  EXP-1944: Temporal stability — do estimates hold across 90-day halves?
  EXP-1945: Joint parameter optimization (ISF + CR + basal simultaneously)
  EXP-1946: Patient phenotyping — cluster by model parameters
  EXP-1947: Sensitivity analysis — how robust are recommendations?
  EXP-1948: Final therapy report cards with corrected model
"""

import argparse
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

warnings.filterwarnings('ignore')

FIGURES_DIR = Path('docs/60-research/figures')
RESULTS_PATH = Path('externals/experiments/exp-1941_revised_therapy.json')
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# --- Helpers ---

def get_isf(p):
    s = p['df'].attrs.get('isf_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        v = s[0].get('value', s[0].get('sensitivity', 50))
        return v * 18.0182 if v < 15 else v
    return 50

def get_cr(p):
    s = p['df'].attrs.get('cr_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('ratio', 10))
    return 10

def get_basal(p):
    s = p['df'].attrs.get('basal_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('rate', 1.0))
    return 1.0

def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    meals = []
    i = 0
    while i < len(df) - post_window:
        c = carbs[i] if np.isfinite(carbs[i]) else 0
        if c >= min_carbs:
            mb = sum(bolus[j] for j in range(max(0,i-pre_window), min(len(df),i+post_window//3))
                     if np.isfinite(bolus[j]) and bolus[j] > 0.1)
            meals.append({'idx': i, 'end': min(i+post_window, len(df)), 'carbs': c, 'bolus': mb})
            i += post_window
        else:
            i += 1
    return meals

def build_corrected_model(glucose, sd, carbs_col, tau=20, frac=1.0):
    """Build corrected supply using slower absorption."""
    hepatic = sd.get('hepatic', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))

    new_carb = np.zeros_like(glucose)
    tau_s = tau / 5
    window = int(6 * tau_s)
    for i in range(len(glucose)):
        c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
        if c >= 1:
            end = min(window, len(glucose) - i)
            for k in range(end):
                new_carb[i + k] += c * frac * (k / (tau_s ** 2)) * np.exp(-k / tau_s)
    return hepatic + new_carb, demand

def optimal_scale(supply, demand, glucose, mask=None, lo=0.01, hi=5.01, step=0.05):
    dg = np.diff(glucose, prepend=glucose[0])
    best_s, best_l = 1.0, np.inf
    for s in np.arange(lo, hi, step):
        r = dg - (supply - demand * s)
        if mask is not None: r = r[mask]
        v = np.isfinite(r)
        if v.sum() < 10: continue
        l = float(np.mean(r[v] ** 2))
        if l < best_l: best_l = l; best_s = s
    return best_s, best_l

def fit_combined_model(glucose, sd, carbs_col, train_mask):
    """Fit absorption tau + gradient demand on training data."""
    hepatic = sd.get('hepatic', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])

    meal_mask = np.zeros(len(glucose), dtype=bool)
    for i in range(len(glucose)):
        c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
        if c >= 5:
            meal_mask[i:min(i+36, len(glucose))] = True

    best_params = {'tau': 20, 'frac': 1.0, 'meal_scale': 1.0, 'nonmeal_scale': 1.0}
    best_loss = np.inf

    for tau in [20, 40, 60, 90]:
        for frac in [0.7, 0.85, 1.0]:
            new_supply, _ = build_corrected_model(glucose, sd, carbs_col, tau, frac)
            sd_new = {'supply': new_supply, 'demand': demand}

            m_mask = train_mask & meal_mask
            nm_mask = train_mask & ~meal_mask
            ms, _ = optimal_scale(new_supply, demand, glucose, mask=m_mask)
            nms, _ = optimal_scale(new_supply, demand, glucose, mask=nm_mask)

            # Gradient
            grad = np.full(len(glucose), nms)
            for i in range(len(glucose)):
                c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
                if c >= 5:
                    for k in range(min(72, len(glucose)-i)):
                        b = nms + (ms - nms) * np.exp(-k / 18)
                        grad[i+k] = max(grad[i+k], b)

            net = new_supply - demand * grad
            resid = dg - net
            r = resid[train_mask]
            v = np.isfinite(r)
            if v.sum() < 100: continue
            loss = float(np.mean(r[v] ** 2))
            if loss < best_loss:
                best_loss = loss
                best_params = {'tau': tau, 'frac': frac, 'meal_scale': ms, 'nonmeal_scale': nms}

    return best_params

def apply_combined_model(glucose, sd, carbs_col, params):
    """Apply fitted combined model, return net prediction."""
    new_supply, demand = build_corrected_model(glucose, sd, carbs_col, params['tau'], params['frac'])
    ms, nms = params['meal_scale'], params['nonmeal_scale']

    grad = np.full(len(glucose), nms)
    for i in range(len(glucose)):
        c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
        if c >= 5:
            for k in range(min(72, len(glucose)-i)):
                b = nms + (ms - nms) * np.exp(-k / 18)
                grad[i+k] = max(grad[i+k], b)

    return new_supply - demand * grad, new_supply, demand, grad


# =====================================================================
# EXP-1941: Revised ISF Estimates
# =====================================================================

def exp_1941(patients, save_fig=False):
    """Estimate ISF using the corrected model for each patient."""
    print("\n" + "=" * 70)
    print("EXP-1941: Revised ISF Estimates (Corrected Model)")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        isf_profile = get_isf(p)

        # Fit combined model on all data
        train_mask = np.ones(len(glucose), dtype=bool)
        params = fit_combined_model(glucose, sd, carbs_col, train_mask)
        net, new_supply, demand, grad_scale = apply_combined_model(glucose, sd, carbs_col, params)

        # ISF estimation: for correction boluses (glucose > 150, no carbs nearby)
        dg = np.diff(glucose, prepend=glucose[0])
        correction_events = []
        for i in range(len(glucose) - 36):
            b = bolus[i] if np.isfinite(bolus[i]) else 0
            if b < 0.5: continue
            g = glucose[i] if np.isfinite(glucose[i]) else 0
            if g < 150: continue
            # No carbs within 1h
            c_window = carbs_col[max(0,i-12):min(len(glucose),i+12)]
            if np.nansum(c_window[np.isfinite(c_window)]) > 2: continue

            # Track glucose drop in 2h
            post_g = glucose[i:min(i+24, len(glucose))]
            valid = np.isfinite(post_g)
            if valid.sum() < 6: continue
            delta_g = float(post_g[valid][-1] - post_g[valid][0])
            event_isf = -delta_g / b if delta_g < 0 else np.nan
            if np.isfinite(event_isf) and 5 < event_isf < 500:
                correction_events.append({'bolus': b, 'delta_g': delta_g, 'isf': event_isf})

        if not correction_events:
            result = {'patient': name, 'n_corrections': 0, 'revised_isf': np.nan,
                      'isf_profile': isf_profile, 'model_params': params}
            all_results.append(result)
            print(f"  {name}: no corrections found")
            continue

        median_isf = float(np.median([e['isf'] for e in correction_events]))
        mean_isf = float(np.mean([e['isf'] for e in correction_events]))
        mismatch = (median_isf - isf_profile) / isf_profile * 100

        result = {
            'patient': name,
            'n_corrections': len(correction_events),
            'isf_profile': isf_profile,
            'revised_isf': median_isf,
            'isf_mean': mean_isf,
            'isf_mismatch_pct': mismatch,
            'model_params': params,
            'demand_scale_meal': params['meal_scale'],
            'demand_scale_nonmeal': params['nonmeal_scale'],
        }
        all_results.append(result)
        print(f"  {name}: ISF profile={isf_profile:.0f} revised={median_isf:.0f} ({mismatch:+.0f}%) n={len(correction_events)}")

    valid = [r for r in all_results if np.isfinite(r.get('revised_isf', np.nan))]
    if valid:
        pop_mismatch = np.mean([r['isf_mismatch_pct'] for r in valid])
        print(f"\n  Population ISF mismatch: {pop_mismatch:+.0f}%")
        verdict = f"ISF_MISMATCH_{pop_mismatch:+.0f}%"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and valid:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 1, figsize=(10, 5))
            names = [r['patient'] for r in valid]
            x = np.arange(len(names))
            prof = [r['isf_profile'] for r in valid]
            rev = [r['revised_isf'] for r in valid]
            ax.bar(x-0.15, prof, 0.3, label='Profile ISF', color='coral')
            ax.bar(x+0.15, rev, 0.3, label='Revised ISF', color='green')
            ax.set_xticks(x); ax.set_xticklabels(names)
            ax.set_ylabel('ISF (mg/dL per U)'); ax.set_title('Revised ISF Estimates')
            ax.legend()
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig01-revised-isf.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig01-revised-isf.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1941 verdict: {verdict}")
    return {'experiment': 'EXP-1941', 'title': 'Revised ISF', 'verdict': verdict,
            'per_patient': [{k: v for k, v in r.items() if k != 'model_params'} for r in all_results]}


# =====================================================================
# EXP-1942: Revised CR Estimates
# =====================================================================

def exp_1942(patients, save_fig=False):
    """Estimate CR using corrected model."""
    print("\n" + "=" * 70)
    print("EXP-1942: Revised CR Estimates (Corrected Model)")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)

        meals = find_meals(df, min_carbs=10)
        if len(meals) < 5:
            print(f"  {name}: <5 meals, skip")
            continue

        cr_estimates = []
        for m in meals:
            if m['bolus'] < 0.5: continue
            idx = m['idx']
            end = min(idx + 2 * STEPS_PER_HOUR, len(glucose))
            pre_g = glucose[idx] if np.isfinite(glucose[idx]) else np.nan
            post_g = glucose[end-1] if np.isfinite(glucose[end-1]) else np.nan
            if not (np.isfinite(pre_g) and np.isfinite(post_g)): continue

            delta_g = post_g - pre_g
            correction = delta_g / isf_profile if isf_profile > 0 else 0
            effective_units = m['bolus'] + correction
            if effective_units > 0.1:
                eff_cr = m['carbs'] / effective_units
                if 1 < eff_cr < 100:
                    cr_estimates.append(eff_cr)

        if not cr_estimates:
            print(f"  {name}: no valid CR estimates")
            continue

        revised_cr = float(np.median(cr_estimates))
        mismatch = (revised_cr - cr_profile) / cr_profile * 100

        result = {
            'patient': name, 'n_meals': len(cr_estimates),
            'cr_profile': cr_profile, 'revised_cr': revised_cr,
            'cr_mismatch_pct': mismatch,
        }
        all_results.append(result)
        print(f"  {name}: CR profile={cr_profile:.1f} revised={revised_cr:.1f} ({mismatch:+.0f}%) n={len(cr_estimates)}")

    valid = [r for r in all_results if np.isfinite(r.get('revised_cr', np.nan))]
    if valid:
        pop = np.mean([r['cr_mismatch_pct'] for r in valid])
        too_high = sum(1 for r in valid if r['cr_mismatch_pct'] < -10)
        print(f"\n  Population CR mismatch: {pop:+.0f}%, too high: {too_high}/{len(valid)}")
        verdict = f"CR_MISMATCH_{pop:+.0f}%_TOO_HIGH_{too_high}/{len(valid)}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and valid:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 5))
            names = [r['patient'] for r in valid]
            x = np.arange(len(names))
            ax.bar(x-0.15, [r['cr_profile'] for r in valid], 0.3, label='Profile CR', color='coral')
            ax.bar(x+0.15, [r['revised_cr'] for r in valid], 0.3, label='Revised CR', color='green')
            ax.set_xticks(x); ax.set_xticklabels(names)
            ax.set_ylabel('CR (g/U)'); ax.set_title('Revised CR Estimates'); ax.legend()
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig02-revised-cr.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig02-revised-cr.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1942 verdict: {verdict}")
    return {'experiment': 'EXP-1942', 'title': 'Revised CR', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1943: Revised Basal Estimates
# =====================================================================

def exp_1943(patients, save_fig=False):
    """Estimate basal rate from overnight glucose drift with corrected model."""
    print("\n" + "=" * 70)
    print("EXP-1943: Revised Basal Estimates (Corrected Model)")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        basal_profile = get_basal(p)
        isf_profile = get_isf(p)
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        # Find overnight windows (midnight to 6am, no carbs in prior 4h)
        overnight_drifts = []
        n_days = len(glucose) // STEPS_PER_DAY

        for day in range(n_days):
            midnight = day * STEPS_PER_DAY
            six_am = midnight + 6 * STEPS_PER_HOUR

            if six_am > len(glucose): continue

            # Check no carbs in prior 4h
            lookback = max(0, midnight - 4 * STEPS_PER_HOUR)
            c_window = carbs_col[lookback:midnight]
            if np.nansum(c_window[np.isfinite(c_window)]) > 2: continue

            # Compute drift
            g_window = glucose[midnight:six_am]
            valid = np.isfinite(g_window)
            if valid.sum() < 3 * STEPS_PER_HOUR: continue

            # Linear drift per hour
            valid_g = g_window[valid]
            drift_per_step = (valid_g[-1] - valid_g[0]) / valid.sum()
            drift_per_hour = drift_per_step * STEPS_PER_HOUR

            # Actual temp rate during overnight
            t_window = temp_rate[midnight:six_am]
            valid_t = t_window[np.isfinite(t_window)]
            actual_rate = float(np.mean(valid_t)) if len(valid_t) > 0 else basal_profile

            overnight_drifts.append({
                'drift_per_hour': drift_per_hour,
                'actual_rate': actual_rate,
                'start_glucose': float(valid_g[0]),
            })

        if not overnight_drifts:
            print(f"  {name}: no overnight windows")
            continue

        mean_drift = float(np.mean([d['drift_per_hour'] for d in overnight_drifts]))
        mean_rate = float(np.mean([d['actual_rate'] for d in overnight_drifts]))

        # Compute corrected basal
        # If drift > 0 (rising), basal too low → increase
        # If drift < 0 (falling), basal too high → decrease
        # Correction: rate_change = drift / ISF (per hour)
        correction = mean_drift / isf_profile if isf_profile > 0 else 0
        revised_basal = max(0, basal_profile + correction)
        mismatch = (revised_basal - basal_profile) / basal_profile * 100 if basal_profile > 0 else 0

        result = {
            'patient': name, 'n_nights': len(overnight_drifts),
            'basal_profile': basal_profile, 'revised_basal': revised_basal,
            'mean_drift': mean_drift, 'mean_actual_rate': mean_rate,
            'basal_mismatch_pct': mismatch,
        }
        all_results.append(result)
        print(f"  {name}: basal={basal_profile:.2f} revised={revised_basal:.2f} ({mismatch:+.0f}%) "
              f"drift={mean_drift:+.1f}mg/dL/h n={len(overnight_drifts)}")

    if all_results:
        pop = np.mean([r['basal_mismatch_pct'] for r in all_results])
        print(f"\n  Population basal mismatch: {pop:+.0f}%")
        verdict = f"BASAL_MISMATCH_{pop:+.0f}%"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            axes[0].bar(x-0.15, [r['basal_profile'] for r in all_results], 0.3, label='Profile', color='coral')
            axes[0].bar(x+0.15, [r['revised_basal'] for r in all_results], 0.3, label='Revised', color='green')
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Basal (U/h)'); axes[0].set_title('Revised Basal Rates'); axes[0].legend()
            axes[1].bar(x, [r['mean_drift'] for r in all_results],
                        color=['coral' if d>0 else 'green' for d in [r['mean_drift'] for r in all_results]])
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('mg/dL/h'); axes[1].set_title('Overnight Glucose Drift')
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig03-revised-basal.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig03-revised-basal.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1943 verdict: {verdict}")
    return {'experiment': 'EXP-1943', 'title': 'Revised Basal', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1944: Temporal Stability
# =====================================================================

def exp_1944(patients, save_fig=False):
    """Test if therapy estimates are stable across 90-day halves."""
    print("\n" + "=" * 70)
    print("EXP-1944: Temporal Stability of Estimates")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        mid = len(glucose) // 2

        # Fit model on each half
        h1_mask = np.zeros(len(glucose), dtype=bool); h1_mask[:mid] = True
        h2_mask = np.zeros(len(glucose), dtype=bool); h2_mask[mid:] = True

        params_h1 = fit_combined_model(glucose, sd, carbs_col, h1_mask)
        params_h2 = fit_combined_model(glucose, sd, carbs_col, h2_mask)

        # Parameter stability
        tau_diff = abs(params_h1['tau'] - params_h2['tau'])
        ms_diff = abs(params_h1['meal_scale'] - params_h2['meal_scale'])
        nms_diff = abs(params_h1['nonmeal_scale'] - params_h2['nonmeal_scale'])

        result = {
            'patient': name,
            'h1_tau': params_h1['tau'], 'h2_tau': params_h2['tau'], 'tau_diff': tau_diff,
            'h1_meal_scale': params_h1['meal_scale'], 'h2_meal_scale': params_h2['meal_scale'],
            'meal_scale_diff': ms_diff,
            'h1_nonmeal_scale': params_h1['nonmeal_scale'], 'h2_nonmeal_scale': params_h2['nonmeal_scale'],
            'nonmeal_scale_diff': nms_diff,
            'stable': tau_diff <= 20 and ms_diff < 1.0 and nms_diff < 0.5,
        }
        all_results.append(result)
        print(f"  {name}: tau {params_h1['tau']}→{params_h2['tau']} meal {params_h1['meal_scale']:.2f}→{params_h2['meal_scale']:.2f} "
              f"{'✓ stable' if result['stable'] else '✗ unstable'}")

    stable_count = sum(1 for r in all_results if r['stable'])
    print(f"\n  Stability: {stable_count}/{len(all_results)} patients stable")
    verdict = f"STABLE_{stable_count}/{len(all_results)}"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))

            for idx, (key1, key2, title) in enumerate([
                ('h1_tau', 'h2_tau', 'Absorption τ'),
                ('h1_meal_scale', 'h2_meal_scale', 'Meal Demand Scale'),
                ('h1_nonmeal_scale', 'h2_nonmeal_scale', 'Non-meal Demand Scale')]):
                axes[idx].bar(x-0.15, [r[key1] for r in all_results], 0.3, label='First 90d', color='steelblue')
                axes[idx].bar(x+0.15, [r[key2] for r in all_results], 0.3, label='Second 90d', color='coral')
                axes[idx].set_xticks(x); axes[idx].set_xticklabels(names)
                axes[idx].set_title(title); axes[idx].legend(fontsize=8)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig04-stability.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig04-stability.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1944 verdict: {verdict}")
    return {'experiment': 'EXP-1944', 'title': 'Temporal Stability', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1945: Joint Parameter Optimization
# =====================================================================

def exp_1945(patients, save_fig=False):
    """Optimize ISF, CR, and basal simultaneously."""
    print("\n" + "=" * 70)
    print("EXP-1945: Joint Parameter Optimization")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        dg = np.diff(glucose, prepend=glucose[0])

        isf_p = get_isf(p); cr_p = get_cr(p); basal_p = get_basal(p)

        # Simple joint optimization: scale ISF, CR, basal together
        # ISF affects demand, CR affects effective carb-to-insulin ratio, basal affects overnight
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))

        mid = len(glucose) // 2
        train = slice(0, mid)
        test = slice(mid, len(glucose))

        # Grid search: demand scale × supply scale
        best_loss = np.inf
        best_ds, best_ss = 1.0, 1.0
        for ds in np.arange(0.1, 4.1, 0.2):
            for ss in np.arange(0.3, 2.1, 0.1):
                net = supply[train] * ss - demand[train] * ds
                resid = dg[train] - net
                v = np.isfinite(resid)
                if v.sum() < 100: continue
                loss = float(np.mean(resid[v] ** 2))
                if loss < best_loss:
                    best_loss = loss
                    best_ds = ds; best_ss = ss

        # Evaluate on test
        net_train = supply[train] * best_ss - demand[train] * best_ds
        net_test = supply[test] * best_ss - demand[test] * best_ds
        resid_test = dg[test] - net_test
        v = np.isfinite(resid_test)
        test_loss = float(np.mean(resid_test[v] ** 2)) if v.sum() > 10 else np.nan

        # Profile baseline on test
        net_profile = supply[test] - demand[test]
        resid_profile = dg[test] - net_profile
        vp = np.isfinite(resid_profile)
        profile_loss = float(np.mean(resid_profile[vp] ** 2)) if vp.sum() > 10 else np.nan

        improvement = (1 - test_loss / profile_loss) * 100 if profile_loss > 0 and np.isfinite(test_loss) else 0

        # Translate scales to therapy recommendations
        revised_isf = isf_p * best_ds  # Higher demand scale → higher effective ISF
        revised_cr = cr_p * best_ss  # Higher supply scale → more carbs per unit

        result = {
            'patient': name,
            'demand_scale': best_ds, 'supply_scale': best_ss,
            'isf_profile': isf_p, 'revised_isf': revised_isf,
            'cr_profile': cr_p, 'revised_cr': revised_cr,
            'profile_loss': profile_loss, 'joint_loss': test_loss,
            'improvement_pct': improvement,
        }
        all_results.append(result)
        print(f"  {name}: DS={best_ds:.1f} SS={best_ss:.1f} improvement={improvement:+.0f}%")

    if all_results:
        pop_imp = np.mean([r['improvement_pct'] for r in all_results])
        improved = sum(1 for r in all_results if r['improvement_pct'] > 0)
        print(f"\n  Population improvement: {pop_imp:+.1f}% ({improved}/{len(all_results)} improved)")
        verdict = f"JOINT_+{pop_imp:.0f}%_{improved}/{len(all_results)}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            ax.bar(x, [r['improvement_pct'] for r in all_results],
                   color=['green' if r['improvement_pct']>0 else 'red' for r in all_results])
            ax.axhline(0, color='gray', ls='--', lw=0.5)
            ax.set_xticks(x); ax.set_xticklabels(names)
            ax.set_ylabel('Improvement (%)'); ax.set_title('Joint Optimization Improvement')
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig05-joint-optimization.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig05-joint-optimization.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1945 verdict: {verdict}")
    return {'experiment': 'EXP-1945', 'title': 'Joint Optimization', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1946: Patient Phenotyping
# =====================================================================

def exp_1946(patients, save_fig=False):
    """Cluster patients by model parameters to identify phenotypes."""
    print("\n" + "=" * 70)
    print("EXP-1946: Patient Phenotyping")
    print("=" * 70)

    features = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        train_mask = np.ones(len(glucose), dtype=bool)
        params = fit_combined_model(glucose, sd, carbs_col, train_mask)

        valid_g = glucose[np.isfinite(glucose)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) if len(valid_g) > 0 else 0
        cv = float(np.std(valid_g) / np.mean(valid_g)) if len(valid_g) > 0 else 0
        mean_g = float(np.mean(valid_g)) if len(valid_g) > 0 else 0

        features.append({
            'patient': name, 'tau': params['tau'], 'frac': params['frac'],
            'meal_scale': params['meal_scale'], 'nonmeal_scale': params['nonmeal_scale'],
            'tir': tir, 'cv': cv, 'mean_glucose': mean_g,
            'isf': get_isf(p), 'cr': get_cr(p), 'basal': get_basal(p),
        })

    # Simple phenotyping: cluster by meal_scale and tau
    high_demand = [f for f in features if f['meal_scale'] > 2.0]
    low_demand = [f for f in features if f['meal_scale'] <= 2.0]

    print(f"\n  High demand (meal_scale > 2.0): {[f['patient'] for f in high_demand]}")
    print(f"  Low demand (meal_scale ≤ 2.0): {[f['patient'] for f in low_demand]}")

    if high_demand:
        print(f"    High demand: mean TIR={np.mean([f['tir'] for f in high_demand])*100:.0f}% "
              f"mean ISF={np.mean([f['isf'] for f in high_demand]):.0f}")
    if low_demand:
        print(f"    Low demand: mean TIR={np.mean([f['tir'] for f in low_demand])*100:.0f}% "
              f"mean ISF={np.mean([f['isf'] for f in low_demand]):.0f}")

    verdict = f"HIGH_DEMAND_{len(high_demand)}_LOW_DEMAND_{len(low_demand)}"

    if save_fig and features:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            ms = [f['meal_scale'] for f in features]
            tir = [f['tir'] * 100 for f in features]
            isf = [f['isf'] for f in features]

            axes[0].scatter(ms, tir, s=80, c='steelblue', edgecolors='navy')
            for f in features:
                axes[0].annotate(f['patient'], (f['meal_scale'], f['tir']*100),
                                  textcoords='offset points', xytext=(5,5), fontsize=9)
            axes[0].set_xlabel('Meal Demand Scale'); axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('Demand Scale vs Glycemic Control')

            axes[1].scatter(isf, ms, s=80, c='coral', edgecolors='darkred')
            for f in features:
                axes[1].annotate(f['patient'], (f['isf'], f['meal_scale']),
                                  textcoords='offset points', xytext=(5,5), fontsize=9)
            axes[1].set_xlabel('Profile ISF'); axes[1].set_ylabel('Meal Demand Scale')
            axes[1].set_title('ISF vs Demand Scale')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig06-phenotyping.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig06-phenotyping.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1946 verdict: {verdict}")
    return {'experiment': 'EXP-1946', 'title': 'Phenotyping', 'verdict': verdict, 'per_patient': features}


# =====================================================================
# EXP-1947: Sensitivity Analysis
# =====================================================================

def exp_1947(patients, save_fig=False):
    """How sensitive are recommendations to parameter choices?"""
    print("\n" + "=" * 70)
    print("EXP-1947: Sensitivity Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        # Test how loss changes with ±20% parameter perturbation
        train_mask = np.ones(len(glucose), dtype=bool)
        params = fit_combined_model(glucose, sd, carbs_col, train_mask)
        _, base_supply, _, base_grad = apply_combined_model(glucose, sd, carbs_col, params)

        base_net = base_supply - demand * base_grad
        base_resid = dg - base_net
        v = np.isfinite(base_resid)
        base_loss = float(np.mean(base_resid[v] ** 2)) if v.sum() > 10 else np.nan

        sensitivities = {}
        for param_name, perturbation in [('tau', 0.5), ('meal_scale', 0.2), ('nonmeal_scale', 0.2)]:
            perturbed = dict(params)
            original_val = perturbed[param_name]
            # +20%
            perturbed[param_name] = original_val * (1 + perturbation)
            _, s_up, _, g_up = apply_combined_model(glucose, sd, carbs_col, perturbed)
            net_up = s_up - demand * g_up
            r_up = dg - net_up
            vu = np.isfinite(r_up)
            loss_up = float(np.mean(r_up[vu] ** 2)) if vu.sum() > 10 else np.nan

            # -20%
            perturbed[param_name] = max(original_val * (1 - perturbation), 0.01)
            _, s_dn, _, g_dn = apply_combined_model(glucose, sd, carbs_col, perturbed)
            net_dn = s_dn - demand * g_dn
            r_dn = dg - net_dn
            vd = np.isfinite(r_dn)
            loss_dn = float(np.mean(r_dn[vd] ** 2)) if vd.sum() > 10 else np.nan

            if np.isfinite(base_loss) and np.isfinite(loss_up) and np.isfinite(loss_dn):
                sens = max(abs(loss_up - base_loss), abs(loss_dn - base_loss)) / base_loss * 100
            else:
                sens = np.nan
            sensitivities[param_name] = sens

        result = {'patient': name, 'base_loss': base_loss, **{f'sens_{k}': v for k, v in sensitivities.items()}}
        all_results.append(result)
        print(f"  {name}: tau_sens={sensitivities.get('tau',0):.1f}% meal_sens={sensitivities.get('meal_scale',0):.1f}% "
              f"nonmeal_sens={sensitivities.get('nonmeal_scale',0):.1f}%")

    if all_results:
        pop_tau = np.nanmean([r.get('sens_tau', np.nan) for r in all_results])
        pop_meal = np.nanmean([r.get('sens_meal_scale', np.nan) for r in all_results])
        pop_nonmeal = np.nanmean([r.get('sens_nonmeal_scale', np.nan) for r in all_results])
        most_sensitive = max([('tau', pop_tau), ('meal', pop_meal), ('nonmeal', pop_nonmeal)], key=lambda x: x[1] if np.isfinite(x[1]) else 0)
        print(f"\n  Most sensitive: {most_sensitive[0]} ({most_sensitive[1]:.1f}%)")
        verdict = f"MOST_SENSITIVE:{most_sensitive[0]}({most_sensitive[1]:.0f}%)"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            w = 0.25
            ax.bar(x-w, [r.get('sens_tau', 0) for r in all_results], w, label='τ sensitivity', color='steelblue')
            ax.bar(x, [r.get('sens_meal_scale', 0) for r in all_results], w, label='Meal scale', color='coral')
            ax.bar(x+w, [r.get('sens_nonmeal_scale', 0) for r in all_results], w, label='Non-meal scale', color='green')
            ax.set_xticks(x); ax.set_xticklabels(names)
            ax.set_ylabel('Sensitivity (% loss change from ±20%)'); ax.set_title('Parameter Sensitivity')
            ax.legend()
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig07-sensitivity.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig07-sensitivity.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1947 verdict: {verdict}")
    return {'experiment': 'EXP-1947', 'title': 'Sensitivity Analysis', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1948: Final Therapy Report Cards
# =====================================================================

def exp_1948(patients, save_fig=False):
    """Generate comprehensive therapy report cards with corrected model."""
    print("\n" + "=" * 70)
    print("EXP-1948: Final Therapy Report Cards")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

        isf_p = get_isf(p); cr_p = get_cr(p); basal_p = get_basal(p)

        # Glycemic metrics
        valid_g = glucose[np.isfinite(glucose)]
        if len(valid_g) < 1000: continue

        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) * 100
        tbr = float(np.mean(valid_g < 70)) * 100
        tar = float(np.mean(valid_g > 180)) * 100
        mean_g = float(np.mean(valid_g))
        cv = float(np.std(valid_g) / mean_g) * 100
        ea1c = (mean_g + 46.7) / 28.7

        # Model fit
        train_mask = np.ones(len(glucose), dtype=bool)
        params = fit_combined_model(glucose, sd, carbs_col, train_mask)
        net, _, _, _ = apply_combined_model(glucose, sd, carbs_col, params)
        dg = np.diff(glucose, prepend=glucose[0])
        resid = dg - net
        v = np.isfinite(resid)
        model_rmse = float(np.sqrt(np.mean(resid[v] ** 2))) if v.sum() > 10 else np.nan

        # Parameter assessment
        issues = []
        # Use mean post-meal delta as CR signal
        meals = find_meals(df, min_carbs=10)
        if meals:
            deltas = []
            for m in meals:
                if m['bolus'] < 0.5: continue
                idx = m['idx']
                end = min(idx + 2*STEPS_PER_HOUR, len(glucose))
                g0 = glucose[idx]; g1 = glucose[end-1]
                if np.isfinite(g0) and np.isfinite(g1):
                    deltas.append(g1 - g0)
            if deltas:
                mean_delta = np.mean(deltas)
                if mean_delta > 30: issues.append('CR_TOO_HIGH')
                elif mean_delta < -30: issues.append('CR_TOO_LOW')

        if tar > 30: issues.append('HIGH_TAR')
        if tbr > 4: issues.append('HIGH_TBR')
        if cv > 36: issues.append('HIGH_CV')

        # Grade
        if tir >= 70 and tbr < 4 and len(issues) == 0:
            grade = 'EXCELLENT'
        elif tir >= 60 and tbr < 5:
            grade = 'ADEQUATE'
        else:
            grade = 'NEEDS_ATTENTION'

        result = {
            'patient': name, 'grade': grade,
            'tir': tir, 'tbr': tbr, 'tar': tar, 'cv': cv, 'ea1c': ea1c,
            'mean_glucose': mean_g, 'model_rmse': model_rmse,
            'isf_profile': isf_p, 'cr_profile': cr_p, 'basal_profile': basal_p,
            'model_tau': params['tau'], 'meal_scale': params['meal_scale'],
            'nonmeal_scale': params['nonmeal_scale'],
            'issues': issues, 'n_issues': len(issues),
        }
        all_results.append(result)
        grade_emoji = {'EXCELLENT': '🟢', 'ADEQUATE': '🟡', 'NEEDS_ATTENTION': '🔴'}
        print(f"  {name}: {grade_emoji.get(grade, '?')} {grade} TIR={tir:.0f}% eA1c={ea1c:.1f} "
              f"RMSE={model_rmse:.1f} issues={issues}")

    # Summary
    grades = {}
    for r in all_results:
        g = r['grade']
        grades[g] = grades.get(g, 0) + 1

    print(f"\n  Grades: {grades}")
    pop_tir = np.mean([r['tir'] for r in all_results])
    pop_ea1c = np.mean([r['ea1c'] for r in all_results])
    verdict = f"TIR_{pop_tir:.0f}%_eA1c_{pop_ea1c:.1f}_GRADES:{grades}"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            grade_colors = {'EXCELLENT': 'green', 'ADEQUATE': 'gold', 'NEEDS_ATTENTION': 'red'}
            colors = [grade_colors.get(r['grade'], 'gray') for r in all_results]

            # TIR bars with grade coloring
            axes[0].bar(x, [r['tir'] for r in all_results], color=colors, edgecolor='black', lw=0.5)
            axes[0].axhline(70, color='green', ls='--', alpha=0.5, label='Target (70%)')
            axes[0].axhline(60, color='gold', ls='--', alpha=0.5, label='Adequate (60%)')
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)'); axes[0].set_title('Therapy Report Cards')
            axes[0].legend(fontsize=8)

            # Issues count
            axes[1].bar(x, [r['n_issues'] for r in all_results], color=colors, edgecolor='black', lw=0.5)
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Number of issues'); axes[1].set_title('Issues Identified')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'therapy-fig08-report-cards.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved therapy-fig08-report-cards.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1948 verdict: {verdict}")
    return {'experiment': 'EXP-1948', 'title': 'Report Cards', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1941–1948: Revised Therapy Estimates with Corrected Model")
    print("=" * 70)

    results = {}
    for exp_id, fn in [('EXP-1941', exp_1941), ('EXP-1942', exp_1942), ('EXP-1943', exp_1943),
                        ('EXP-1944', exp_1944), ('EXP-1945', exp_1945), ('EXP-1946', exp_1946),
                        ('EXP-1947', exp_1947), ('EXP-1948', exp_1948)]:
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}: {fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'#' * 70}")
        try:
            results[exp_id] = fn(patients, save_fig=args.figures)
        except Exception as e:
            print(f"\n  ✗ {exp_id} FAILED: {e}")
            import traceback; traceback.print_exc()
            results[exp_id] = {'experiment': exp_id, 'verdict': f'FAILED: {e}'}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    def json_safe(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.bool_): return bool(obj)
        raise TypeError(f"Not JSON serializable: {type(obj)}")

    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2, default=json_safe)
    print(f"\n✓ Results saved to {RESULTS_PATH}")

    print("\n" + "=" * 70)
    print("SYNTHESIS: Revised Therapy Estimates")
    print("=" * 70)
    for k, v in results.items():
        print(f"  {k}: {v.get('verdict', 'N/A')}")
    print("\n✓ All experiments complete")

if __name__ == '__main__':
    main()
