#!/usr/bin/env python3
"""
EXP-1841 to EXP-1848: Split-Loss Therapy Deconfounding

The goal is NOT to improve glucose forecasting, but to use supply/demand
decomposition to DECONFOUND therapy setting estimation (ISF, CR, basal).

The AID loop creates tight coupling: when settings are wrong, the loop
compensates by adjusting temp basals, masking the error in the glucose trace.
If we can split the loss into supply-side and demand-side components, each
side may have different sensitivity to therapy parameters, giving us cleaner
gradients for estimating correct settings.

Key questions:
  1841: Does supply-loss respond differently to ISF perturbation than demand-loss?
  1842: Can demand-side loss during fasting isolate basal correctness?
  1843: Does supply-side loss during announced meals isolate CR accuracy?
  1844: At what timescales does each loss component give cleanest signal?
  1845: Can split-loss identify which therapy parameter is MOST wrong?
  1846: How does the AID loop's compensation appear in each loss component?
  1847: Cross-patient transfer: do split-loss therapy estimates generalize?
  1848: Combined split-loss therapy estimator vs existing methods

Prior work:
  - EXP-1291: Deconfounded ISF fails — AID dampens corrections (ratio 3.62×)
  - EXP-1301: Response-curve ISF (R²=0.805 fit) — best ISF method
  - EXP-1371: Bolus gate (≥2U) deconfounds ISF but loses most events
  - EXP-1795: ISF consistency CV=0.72 even in fasting
  - EXP-1816: Residual×supply r=-0.56 → model under-estimates supply
  - EXP-1817: Split losses ARE complementary
  - EXP-1822: Demand integral H=1.36 > supply H=1.24
"""

import argparse
import json
import os
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_441 import (
    load_patients, compute_supply_demand,
)

FIGURES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', '60-research', 'figures')


# ============================================================================
# Shared utilities
# ============================================================================

def get_profile_settings(df):
    """Extract profile therapy settings from DataFrame attrs."""
    attrs = df.attrs if hasattr(df, 'attrs') else {}
    
    isf_sched = attrs.get('isf_schedule', {})
    cr_sched = attrs.get('cr_schedule', {})
    basal_sched = attrs.get('basal_schedule', {})
    
    # Get mean values
    if isinstance(isf_sched, dict) and isf_sched:
        isf_vals = list(isf_sched.values())
        isf = np.mean([v for v in isf_vals if isinstance(v, (int, float)) and v > 0])
    else:
        isf = 50.0
    
    # ISF < 15 likely mmol → convert
    if isf < 15:
        isf *= 18.0182
    
    if isinstance(cr_sched, dict) and cr_sched:
        cr_vals = list(cr_sched.values())
        cr = np.mean([v for v in cr_vals if isinstance(v, (int, float)) and v > 0])
    else:
        cr = 10.0
    
    if isinstance(basal_sched, dict) and basal_sched:
        basal_vals = list(basal_sched.values())
        basal = np.mean([v for v in basal_vals if isinstance(v, (int, float)) and v >= 0])
    else:
        basal = 1.0
    
    return {'isf': isf, 'cr': cr, 'basal': basal}


def compute_split_loss(df, sd_data, glucose):
    """Compute supply-side and demand-side loss components.
    
    Supply loss: how well does modeled supply explain glucose rises?
    Demand loss: how well does modeled demand explain glucose falls?
    
    The key insight: the total glucose change = supply - demand + residual.
    If we split into rising (supply-dominated) and falling (demand-dominated)
    periods, each loss component is more sensitive to its respective parameter.
    """
    n = len(glucose)
    supply = sd_data['supply']
    demand = sd_data['demand']
    net = sd_data['net']  # supply - demand
    
    dg = np.diff(glucose, prepend=glucose[0])
    
    # Residual: actual dg/dt - modeled dg/dt
    residual = dg - net
    
    # Supply loss: residual during rising glucose (supply > demand)
    rising = dg > 0.5  # rising threshold
    supply_residual = np.where(rising, residual, np.nan)
    supply_loss = np.nanmean(supply_residual ** 2) if np.any(rising) else np.nan
    supply_bias = np.nanmean(supply_residual) if np.any(rising) else np.nan
    
    # Demand loss: residual during falling glucose (demand > supply)
    falling = dg < -0.5
    demand_residual = np.where(falling, residual, np.nan)
    demand_loss = np.nanmean(demand_residual ** 2) if np.any(falling) else np.nan
    demand_bias = np.nanmean(demand_residual) if np.any(falling) else np.nan
    
    return {
        'supply_loss': supply_loss,
        'demand_loss': demand_loss,
        'supply_bias': supply_bias,  # positive = model under-estimates supply
        'demand_bias': demand_bias,  # negative = model over-estimates demand
        'total_loss': np.nanmean(residual ** 2),
        'supply_residual': supply_residual,
        'demand_residual': demand_residual,
        'residual': residual,
        'rising_fraction': np.mean(rising),
        'falling_fraction': np.mean(falling),
    }


def perturb_and_recompute(df, param_name, scale_factor):
    """Recompute supply/demand with a perturbed therapy parameter.
    
    This simulates "what if ISF/CR/basal were different?" by scaling the
    relevant component of the supply/demand model.
    """
    sd_data = compute_supply_demand(df)
    supply = sd_data['supply'].copy()
    demand = sd_data['demand'].copy()
    
    if param_name == 'isf':
        # ISF affects demand: higher ISF → more glucose drop per unit insulin
        demand = demand * scale_factor
    elif param_name == 'cr':
        # CR affects carb supply: higher CR → less insulin per carb → less demand
        # But from supply side: CR affects how we estimate carb absorption
        carb_supply = sd_data.get('carb_supply', np.zeros_like(supply))
        supply = sd_data['hepatic'] + carb_supply * scale_factor
    elif param_name == 'basal':
        # Basal affects the baseline demand level
        hepatic = sd_data['hepatic']
        # Scale demand proportionally to basal change
        demand = demand * scale_factor
    
    net = supply - demand
    return {
        'supply': supply,
        'demand': demand,
        'net': net,
        'hepatic': sd_data['hepatic'],
        'carb_supply': sd_data.get('carb_supply', np.zeros_like(supply)),
    }


def classify_context_simple(df):
    """Simplified context classification."""
    n = len(df)
    ctx = np.full(n, 'fasting', dtype=object)
    glucose = df['glucose'].values
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
    
    # Post-meal: within 3h of carb entry > 1g
    carb_idx = np.where(np.nan_to_num(carbs) > 1)[0]
    for ci in carb_idx:
        end = min(ci + 36, n)
        ctx[ci:end] = 'post_meal'
    
    # Correction: bolus with no carbs, glucose > 150
    bolus_idx = np.where(np.nan_to_num(bolus) > 0.3)[0]
    for bi in bolus_idx:
        if glucose[bi] > 150 and np.nan_to_num(carbs[bi]) < 1:
            end = min(bi + 36, n)
            ctx[bi:end] = 'correction'
    
    return ctx


# ============================================================================
# EXP-1841: Split-Loss Sensitivity to ISF Perturbation
# ============================================================================
def exp_1841(patients, figures_dir=None):
    """Does supply-loss respond differently to ISF perturbation than demand-loss?
    
    If split-loss gives different sensitivity gradients for ISF, then the two
    loss components carry different information about the correct ISF value.
    """
    print("\n" + "=" * 70)
    print("EXP-1841: Split-Loss ISF Sensitivity")
    print("=" * 70)
    
    results_per_patient = []
    
    isf_scales = [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0]
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        settings = get_profile_settings(df)
        
        supply_losses = []
        demand_losses = []
        total_losses = []
        supply_biases = []
        demand_biases = []
        
        for scale in isf_scales:
            sd_perturbed = perturb_and_recompute(df, 'isf', scale)
            losses = compute_split_loss(df, sd_perturbed, glucose)
            supply_losses.append(losses['supply_loss'])
            demand_losses.append(losses['demand_loss'])
            total_losses.append(losses['total_loss'])
            supply_biases.append(losses['supply_bias'])
            demand_biases.append(losses['demand_bias'])
        
        supply_losses = np.array(supply_losses)
        demand_losses = np.array(demand_losses)
        total_losses = np.array(total_losses)
        
        # Find ISF scale that minimizes each loss
        sl_min_idx = np.nanargmin(supply_losses) if np.any(np.isfinite(supply_losses)) else -1
        dl_min_idx = np.nanargmin(demand_losses) if np.any(np.isfinite(demand_losses)) else -1
        tl_min_idx = np.nanargmin(total_losses) if np.any(np.isfinite(total_losses)) else -1
        
        sl_optimal = isf_scales[sl_min_idx] if sl_min_idx >= 0 else np.nan
        dl_optimal = isf_scales[dl_min_idx] if dl_min_idx >= 0 else np.nan
        tl_optimal = isf_scales[tl_min_idx] if tl_min_idx >= 0 else np.nan
        
        # Sensitivity: d(loss)/d(ISF_scale) at scale=1.0
        idx_1 = isf_scales.index(1.0)
        if idx_1 > 0 and idx_1 < len(isf_scales) - 1:
            sl_sensitivity = (supply_losses[idx_1+1] - supply_losses[idx_1-1]) / (isf_scales[idx_1+1] - isf_scales[idx_1-1])
            dl_sensitivity = (demand_losses[idx_1+1] - demand_losses[idx_1-1]) / (isf_scales[idx_1+1] - isf_scales[idx_1-1])
        else:
            sl_sensitivity = dl_sensitivity = np.nan
        
        patient_result = {
            'name': name,
            'profile_isf': settings['isf'],
            'supply_optimal_scale': float(sl_optimal),
            'demand_optimal_scale': float(dl_optimal),
            'total_optimal_scale': float(tl_optimal),
            'supply_sensitivity': float(sl_sensitivity) if np.isfinite(sl_sensitivity) else None,
            'demand_sensitivity': float(dl_sensitivity) if np.isfinite(dl_sensitivity) else None,
            'supply_losses': [float(x) if np.isfinite(x) else None for x in supply_losses],
            'demand_losses': [float(x) if np.isfinite(x) else None for x in demand_losses],
            'supply_bias_at_1x': float(supply_biases[idx_1]),
            'demand_bias_at_1x': float(demand_biases[idx_1]),
        }
        results_per_patient.append(patient_result)
        
        print(f"  {name}: ISF={settings['isf']:.0f} "
              f"supply_opt={sl_optimal:.2f}× demand_opt={dl_optimal:.2f}× total_opt={tl_optimal:.2f}× "
              f"supply_sens={sl_sensitivity:.1f} demand_sens={dl_sensitivity:.1f}")
    
    # Population analysis
    print(f"\n  Population ISF sensitivity analysis:")
    sl_opts = [r['supply_optimal_scale'] for r in results_per_patient]
    dl_opts = [r['demand_optimal_scale'] for r in results_per_patient]
    tl_opts = [r['total_optimal_scale'] for r in results_per_patient]
    
    print(f"    Supply-optimal ISF scale: {np.mean(sl_opts):.2f} ± {np.std(sl_opts):.2f}")
    print(f"    Demand-optimal ISF scale: {np.mean(dl_opts):.2f} ± {np.std(dl_opts):.2f}")
    print(f"    Total-optimal ISF scale:  {np.mean(tl_opts):.2f} ± {np.std(tl_opts):.2f}")
    
    # Key question: do supply and demand disagree about optimal ISF?
    disagreement = np.abs(np.array(sl_opts) - np.array(dl_opts))
    mean_disagree = np.mean(disagreement)
    
    # Supply bias at 1x (positive = model under-estimates supply)
    sb = [r['supply_bias_at_1x'] for r in results_per_patient]
    db = [r['demand_bias_at_1x'] for r in results_per_patient]
    print(f"\n    Supply bias at profile ISF: {np.mean(sb):+.2f} ± {np.std(sb):.2f} mg/dL/step")
    print(f"    Demand bias at profile ISF: {np.mean(db):+.2f} ± {np.std(db):.2f} mg/dL/step")
    print(f"    Mean S/D disagreement on optimal ISF scale: {mean_disagree:.2f}")
    
    # Sensitivity comparison
    sl_sens = [r['supply_sensitivity'] for r in results_per_patient if r['supply_sensitivity'] is not None]
    dl_sens = [r['demand_sensitivity'] for r in results_per_patient if r['demand_sensitivity'] is not None]
    print(f"\n    Supply sensitivity to ISF: {np.mean(sl_sens):.1f} ± {np.std(sl_sens):.1f}")
    print(f"    Demand sensitivity to ISF: {np.mean(dl_sens):.1f} ± {np.std(dl_sens):.1f}")
    
    if mean_disagree > 0.2:
        verdict = 'DIFFERENT_OPTIMA'
    elif abs(np.mean(sl_sens) - np.mean(dl_sens)) > np.mean([np.std(sl_sens), np.std(dl_sens)]):
        verdict = 'DIFFERENT_SENSITIVITY'
    else:
        verdict = 'SIMILAR_RESPONSE'
    
    print(f"\n  ✓ EXP-1841 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
        # Loss curves for 3 representative patients
        for ax_idx, pidx in enumerate([0, len(results_per_patient)//2, -1]):
            ax = axes[ax_idx]
            r = results_per_patient[pidx]
            sl = [x if x is not None else np.nan for x in r['supply_losses']]
            dl = [x if x is not None else np.nan for x in r['demand_losses']]
            ax.plot(isf_scales, sl, 'o-', color='#e74c3c', label='Supply loss', linewidth=2)
            ax.plot(isf_scales, dl, 's-', color='#3498db', label='Demand loss', linewidth=2)
            ax.axvline(x=1.0, color='gray', linestyle='--', alpha=0.5, label='Profile ISF')
            ax.axvline(x=r['supply_optimal_scale'], color='#e74c3c', linestyle=':', alpha=0.7)
            ax.axvline(x=r['demand_optimal_scale'], color='#3498db', linestyle=':', alpha=0.7)
            ax.set_xlabel('ISF Scale Factor')
            ax.set_ylabel('MSE Loss')
            ax.set_title(f"Patient {r['name']} (ISF={r['profile_isf']:.0f})")
            ax.legend(fontsize=8)
        
        fig.suptitle('EXP-1841: How Supply vs Demand Loss Respond to ISF Changes', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig01-isf-sensitivity.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig01-isf-sensitivity.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'mean_disagreement': float(mean_disagree),
        'isf_scales': isf_scales,
    }


# ============================================================================
# EXP-1842: Demand-Side Loss for Basal Assessment
# ============================================================================
def exp_1842(patients, figures_dir=None):
    """Can demand-side loss during fasting isolate basal correctness?
    
    During fasting, supply ≈ hepatic (constant). So the demand-side loss
    is dominated by insulin-glucose mismatch. If basal is too high, demand
    exceeds supply → glucose falls → demand loss increases. If too low,
    glucose rises → supply loss increases.
    """
    print("\n" + "=" * 70)
    print("EXP-1842: Demand-Side Loss for Basal Assessment")
    print("=" * 70)
    
    results_per_patient = []
    
    basal_scales = [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0]
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        settings = get_profile_settings(df)
        ctx = classify_context_simple(df)
        
        # Fasting-only mask
        fasting = ctx == 'fasting'
        n_fasting = np.sum(fasting)
        
        if n_fasting < 500:
            print(f"  {name}: only {n_fasting} fasting steps, skipping")
            results_per_patient.append({'name': name, 'n_fasting': int(n_fasting), 'skipped': True})
            continue
        
        supply_losses_fasting = []
        demand_losses_fasting = []
        fasting_drift = []  # mean glucose change per hour during fasting
        
        for scale in basal_scales:
            sd_perturbed = perturb_and_recompute(df, 'basal', scale)
            
            # Compute loss on fasting periods only
            net = sd_perturbed['net']
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - net
            
            rising = (dg > 0.5) & fasting
            falling = (dg < -0.5) & fasting
            
            sl = np.nanmean(residual[rising] ** 2) if np.any(rising) else np.nan
            dl = np.nanmean(residual[falling] ** 2) if np.any(falling) else np.nan
            
            supply_losses_fasting.append(sl)
            demand_losses_fasting.append(dl)
            
            # Net glucose drift during fasting at this basal scale
            fasting_dg = dg[fasting]
            drift = np.nanmean(fasting_dg) * 12  # mg/dL per hour
            fasting_drift.append(drift)
        
        supply_losses_fasting = np.array(supply_losses_fasting)
        demand_losses_fasting = np.array(demand_losses_fasting)
        fasting_drift = np.array(fasting_drift)
        
        # Optimal basal scale from each component
        sl_opt = basal_scales[np.nanargmin(supply_losses_fasting)] if np.any(np.isfinite(supply_losses_fasting)) else np.nan
        dl_opt = basal_scales[np.nanargmin(demand_losses_fasting)] if np.any(np.isfinite(demand_losses_fasting)) else np.nan
        
        # Zero-drift basal: where does fasting glucose drift cross zero?
        drift_zero_scale = np.nan
        for i in range(len(fasting_drift) - 1):
            if fasting_drift[i] * fasting_drift[i+1] <= 0:
                # Linear interpolation
                frac = -fasting_drift[i] / (fasting_drift[i+1] - fasting_drift[i]) if fasting_drift[i+1] != fasting_drift[i] else 0
                drift_zero_scale = basal_scales[i] + frac * (basal_scales[i+1] - basal_scales[i])
                break
        
        patient_result = {
            'name': name,
            'profile_basal': settings['basal'],
            'n_fasting': int(n_fasting),
            'fasting_fraction': float(n_fasting / len(glucose)),
            'supply_optimal_scale': float(sl_opt),
            'demand_optimal_scale': float(dl_opt),
            'drift_zero_scale': float(drift_zero_scale) if np.isfinite(drift_zero_scale) else None,
            'fasting_drift_at_1x': float(fasting_drift[basal_scales.index(1.0)]),
            'supply_losses': [float(x) if np.isfinite(x) else None for x in supply_losses_fasting],
            'demand_losses': [float(x) if np.isfinite(x) else None for x in demand_losses_fasting],
            'fasting_drift': [float(x) for x in fasting_drift],
        }
        results_per_patient.append(patient_result)
        
        drift_1x = fasting_drift[basal_scales.index(1.0)]
        print(f"  {name}: basal={settings['basal']:.2f}U/h fasting={n_fasting} "
              f"drift={drift_1x:+.2f}mg/dL/h "
              f"supply_opt={sl_opt:.2f}× demand_opt={dl_opt:.2f}× drift_zero={drift_zero_scale:.2f}×")
    
    # Population summary
    valid = [r for r in results_per_patient if not r.get('skipped')]
    
    print(f"\n  Population fasting basal assessment (n={len(valid)}):")
    
    drifts = [r['fasting_drift_at_1x'] for r in valid]
    drift_zeros = [r['drift_zero_scale'] for r in valid if r['drift_zero_scale'] is not None]
    sl_opts = [r['supply_optimal_scale'] for r in valid]
    dl_opts = [r['demand_optimal_scale'] for r in valid]
    
    print(f"    Mean fasting drift at profile basal: {np.mean(drifts):+.2f} ± {np.std(drifts):.2f} mg/dL/h")
    print(f"    Drift-zero basal scale: {np.mean(drift_zeros):.2f} ± {np.std(drift_zeros):.2f}")
    print(f"    Supply-optimal scale:   {np.mean(sl_opts):.2f} ± {np.std(sl_opts):.2f}")
    print(f"    Demand-optimal scale:   {np.mean(dl_opts):.2f} ± {np.std(dl_opts):.2f}")
    
    # Agreement between methods
    methods_agree = []
    for r in valid:
        if r['drift_zero_scale'] is not None:
            spread = np.std([r['supply_optimal_scale'], r['demand_optimal_scale'], r['drift_zero_scale']])
            methods_agree.append(spread)
    
    mean_spread = np.mean(methods_agree) if methods_agree else np.nan
    print(f"    Method agreement (std of 3 estimates): {mean_spread:.2f}")
    
    # Does demand loss give a DIFFERENT answer than drift alone?
    divergence = np.abs(np.array(dl_opts) - np.array([r.get('drift_zero_scale') or np.nan for r in valid]))
    divergence = divergence[np.isfinite(divergence)]
    
    if np.mean(divergence) > 0.15:
        verdict = 'DEMAND_LOSS_ADDS_INFO'
    elif mean_spread < 0.1:
        verdict = 'METHODS_AGREE'
    else:
        verdict = 'METHODS_DISAGREE'
    
    print(f"\n  ✓ EXP-1842 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # Fasting drift vs basal scale
        ax = axes[0]
        for r in valid:
            ax.plot(basal_scales, r['fasting_drift'], 'o-', alpha=0.5, label=r['name'])
        ax.axhline(y=0, color='black', linewidth=1, linestyle='--')
        ax.axvline(x=1.0, color='gray', linewidth=1, linestyle='--', alpha=0.5)
        ax.set_xlabel('Basal Scale Factor')
        ax.set_ylabel('Fasting Glucose Drift (mg/dL/h)')
        ax.set_title('Fasting Drift vs Basal Setting')
        ax.legend(fontsize=7, ncol=2)
        
        # Demand loss vs supply loss optimal scales
        ax = axes[1]
        for r in valid:
            ax.scatter(r['supply_optimal_scale'], r['demand_optimal_scale'], s=80, zorder=5)
            ax.annotate(r['name'], (r['supply_optimal_scale'], r['demand_optimal_scale']),
                       fontsize=8, ha='left')
        ax.plot([0.4, 2.1], [0.4, 2.1], 'k--', alpha=0.3, label='Agreement line')
        ax.set_xlabel('Supply-Optimal Basal Scale')
        ax.set_ylabel('Demand-Optimal Basal Scale')
        ax.set_title('Do Supply & Demand Agree on Basal?')
        ax.legend()
        
        fig.suptitle('EXP-1842: Fasting Demand Loss → Basal Assessment', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig02-basal-fasting.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig02-basal-fasting.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'basal_scales': basal_scales,
    }


# ============================================================================
# EXP-1843: Supply-Side Loss for CR Assessment
# ============================================================================
def exp_1843(patients, figures_dir=None):
    """Does supply-side loss during announced meals isolate CR accuracy?
    
    During announced meals, supply is dominated by carb absorption.
    If CR is too aggressive (too much insulin per carb), demand is too high
    relative to actual carb absorption → glucose drops too much → supply
    loss increases. If CR is too weak, glucose stays high.
    """
    print("\n" + "=" * 70)
    print("EXP-1843: Supply-Side Loss for CR Assessment")
    print("=" * 70)
    
    results_per_patient = []
    
    cr_scales = [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0]
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        settings = get_profile_settings(df)
        n = len(glucose)
        
        # Post-meal windows only
        meal_mask = np.zeros(n, dtype=bool)
        carb_idx = np.where(np.nan_to_num(carbs) > 5)[0]  # announced meals > 5g
        for ci in carb_idx:
            end = min(ci + 36, n)  # 3h post-meal
            meal_mask[ci:end] = True
        
        n_meal = np.sum(meal_mask)
        n_meals = len(carb_idx)
        
        if n_meals < 10:
            print(f"  {name}: only {n_meals} meals, skipping")
            results_per_patient.append({'name': name, 'n_meals': n_meals, 'skipped': True})
            continue
        
        supply_losses_meal = []
        demand_losses_meal = []
        meal_excursion = []  # mean glucose rise in 2h post-meal
        
        for scale in cr_scales:
            sd_perturbed = perturb_and_recompute(df, 'cr', scale)
            net = sd_perturbed['net']
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - net
            
            rising = (dg > 0.5) & meal_mask
            falling = (dg < -0.5) & meal_mask
            
            sl = np.nanmean(residual[rising] ** 2) if np.any(rising) else np.nan
            dl = np.nanmean(residual[falling] ** 2) if np.any(falling) else np.nan
            
            supply_losses_meal.append(sl)
            demand_losses_meal.append(dl)
            
            # Mean excursion: glucose change in 2h post-meal
            excursions = []
            for ci in carb_idx:
                if ci + 24 < n:
                    rise = np.nanmax(glucose[ci:ci+25]) - glucose[ci]
                    excursions.append(rise)
            meal_excursion.append(np.mean(excursions) if excursions else np.nan)
        
        supply_losses_meal = np.array(supply_losses_meal)
        demand_losses_meal = np.array(demand_losses_meal)
        
        sl_opt = cr_scales[np.nanargmin(supply_losses_meal)] if np.any(np.isfinite(supply_losses_meal)) else np.nan
        dl_opt = cr_scales[np.nanargmin(demand_losses_meal)] if np.any(np.isfinite(demand_losses_meal)) else np.nan
        
        patient_result = {
            'name': name,
            'profile_cr': settings['cr'],
            'n_meals': n_meals,
            'supply_optimal_cr_scale': float(sl_opt),
            'demand_optimal_cr_scale': float(dl_opt),
            'mean_excursion_at_1x': float(meal_excursion[cr_scales.index(1.0)]),
            'supply_losses': [float(x) if np.isfinite(x) else None for x in supply_losses_meal],
            'demand_losses': [float(x) if np.isfinite(x) else None for x in demand_losses_meal],
        }
        results_per_patient.append(patient_result)
        
        print(f"  {name}: CR={settings['cr']:.1f} meals={n_meals} "
              f"excursion={meal_excursion[cr_scales.index(1.0)]:.1f}mg/dL "
              f"supply_opt={sl_opt:.2f}× demand_opt={dl_opt:.2f}×")
    
    valid = [r for r in results_per_patient if not r.get('skipped')]
    
    print(f"\n  Population CR assessment (n={len(valid)}):")
    sl_opts = [r['supply_optimal_cr_scale'] for r in valid]
    dl_opts = [r['demand_optimal_cr_scale'] for r in valid]
    excursions = [r['mean_excursion_at_1x'] for r in valid]
    
    print(f"    Supply-optimal CR scale: {np.mean(sl_opts):.2f} ± {np.std(sl_opts):.2f}")
    print(f"    Demand-optimal CR scale: {np.mean(dl_opts):.2f} ± {np.std(dl_opts):.2f}")
    print(f"    Mean post-meal excursion: {np.mean(excursions):.1f} ± {np.std(excursions):.1f} mg/dL")
    
    # Does supply loss give different CR estimate than demand loss?
    disagree = np.abs(np.array(sl_opts) - np.array(dl_opts))
    
    if np.mean(disagree) > 0.2:
        verdict = 'SPLIT_LOSS_SEPARATES_CR'
    else:
        verdict = 'UNIFIED_CR'
    
    print(f"\n  Mean S/D disagreement on CR scale: {np.mean(disagree):.2f}")
    print(f"\n  ✓ EXP-1843 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(8, 6))
        for r in valid:
            ax.scatter(r['supply_optimal_cr_scale'], r['demand_optimal_cr_scale'], s=80, zorder=5)
            ax.annotate(r['name'], (r['supply_optimal_cr_scale'], r['demand_optimal_cr_scale']),
                       fontsize=8, ha='left')
        ax.plot([0.4, 2.1], [0.4, 2.1], 'k--', alpha=0.3, label='Agreement')
        ax.set_xlabel('Supply-Optimal CR Scale')
        ax.set_ylabel('Demand-Optimal CR Scale')
        ax.set_title('EXP-1843: Do S/D Losses Agree on CR?', fontweight='bold')
        ax.legend()
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig03-cr-meal.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig03-cr-meal.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'cr_scales': cr_scales,
    }


# ============================================================================
# EXP-1844: Timescale-Dependent Deconfounding
# ============================================================================
def exp_1844(patients, figures_dir=None):
    """At what timescales does each loss component give cleanest therapy signal?
    
    Hypothesis: demand-side loss at DIA timescale (~5h) gives cleanest ISF.
    Supply-side loss at meal timescale (~2h) gives cleanest CR.
    Demand-side loss at overnight timescale (~8h) gives cleanest basal.
    """
    print("\n" + "=" * 70)
    print("EXP-1844: Timescale-Dependent Deconfounding")
    print("=" * 70)
    
    results_per_patient = []
    
    # Windows to test (in 5-min steps)
    windows = {
        '30min': 6, '1h': 12, '2h': 24, '3h': 36, '5h': 60, 
        '8h': 96, '12h': 144, '24h': 288
    }
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        supply = sd_data['supply']
        demand = sd_data['demand']
        net = sd_data['net']
        n = len(glucose)
        
        dg = np.diff(glucose, prepend=glucose[0])
        residual = dg - net
        
        patient_result = {'name': name}
        
        for wname, wsteps in windows.items():
            # Compute rolling supply-loss and demand-loss over this window
            supply_losses = []
            demand_losses = []
            
            # Also compute ISF sensitivity at this timescale
            # Perturb ISF by ±15% and measure which window gives sharpest gradient
            sd_up = perturb_and_recompute(df, 'isf', 1.15)
            sd_dn = perturb_and_recompute(df, 'isf', 0.85)
            
            res_up = dg - sd_up['net']
            res_dn = dg - sd_dn['net']
            
            for i in range(wsteps, n, wsteps):
                seg = slice(i - wsteps, i)
                dg_seg = dg[seg]
                
                rising = dg_seg > 0.5
                falling = dg_seg < -0.5
                
                if np.any(rising):
                    supply_losses.append(np.nanmean(residual[seg][rising] ** 2))
                if np.any(falling):
                    demand_losses.append(np.nanmean(residual[seg][falling] ** 2))
            
            # Compute gradient: how much does loss change with ISF perturbation?
            rising_all = dg > 0.5
            falling_all = dg < -0.5
            
            # Use rolling windows for gradient stability
            gradients_supply = []
            gradients_demand = []
            
            for i in range(wsteps, n, wsteps):
                seg = slice(i - wsteps, i)
                rising_seg = rising_all[seg]
                falling_seg = falling_all[seg]
                
                if np.sum(rising_seg) > 5:
                    sl_up = np.nanmean(res_up[seg][rising_seg] ** 2)
                    sl_dn = np.nanmean(res_dn[seg][rising_seg] ** 2)
                    gradients_supply.append(sl_up - sl_dn)
                
                if np.sum(falling_seg) > 5:
                    dl_up = np.nanmean(res_up[seg][falling_seg] ** 2)
                    dl_dn = np.nanmean(res_dn[seg][falling_seg] ** 2)
                    gradients_demand.append(dl_up - dl_dn)
            
            # Gradient signal-to-noise ratio
            if gradients_supply:
                s_grad_mean = np.mean(gradients_supply)
                s_grad_std = np.std(gradients_supply)
                s_snr = abs(s_grad_mean) / (s_grad_std + 1e-10)
            else:
                s_snr = 0
            
            if gradients_demand:
                d_grad_mean = np.mean(gradients_demand)
                d_grad_std = np.std(gradients_demand)
                d_snr = abs(d_grad_mean) / (d_grad_std + 1e-10)
            else:
                d_snr = 0
            
            patient_result[f'supply_snr_{wname}'] = float(s_snr)
            patient_result[f'demand_snr_{wname}'] = float(d_snr)
            patient_result[f'supply_loss_cv_{wname}'] = float(np.std(supply_losses) / (np.mean(supply_losses) + 1e-10)) if supply_losses else np.nan
            patient_result[f'demand_loss_cv_{wname}'] = float(np.std(demand_losses) / (np.mean(demand_losses) + 1e-10)) if demand_losses else np.nan
        
        results_per_patient.append(patient_result)
        # Show best SNR window
        best_s_snr = max((patient_result.get(f'supply_snr_{w}', 0), w) for w in windows)
        best_d_snr = max((patient_result.get(f'demand_snr_{w}', 0), w) for w in windows)
        print(f"  {name}: best supply SNR={best_s_snr[0]:.2f} at {best_s_snr[1]}, "
              f"best demand SNR={best_d_snr[0]:.2f} at {best_d_snr[1]}")
    
    # Population: at which timescale is each loss most informative for ISF?
    print(f"\n  Population ISF gradient SNR by timescale:")
    print(f"  {'Window':>8s}  {'Supply SNR':>12s}  {'Demand SNR':>12s}  {'Better':>8s}")
    
    pop_snr = {}
    for wname in windows:
        s_vals = [r.get(f'supply_snr_{wname}', 0) for r in results_per_patient]
        d_vals = [r.get(f'demand_snr_{wname}', 0) for r in results_per_patient]
        s_mean = np.mean(s_vals)
        d_mean = np.mean(d_vals)
        better = 'supply' if s_mean > d_mean else 'demand'
        print(f"  {wname:>8s}  {s_mean:>12.3f}  {d_mean:>12.3f}  {better:>8s}")
        pop_snr[wname] = {'supply': s_mean, 'demand': d_mean}
    
    # Find peak SNR windows
    best_supply_window = max(pop_snr, key=lambda w: pop_snr[w]['supply'])
    best_demand_window = max(pop_snr, key=lambda w: pop_snr[w]['demand'])
    
    print(f"\n  Best supply SNR window: {best_supply_window} ({pop_snr[best_supply_window]['supply']:.3f})")
    print(f"  Best demand SNR window: {best_demand_window} ({pop_snr[best_demand_window]['demand']:.3f})")
    
    if best_supply_window != best_demand_window:
        verdict = f'DIFFERENT_TIMESCALES'
    else:
        verdict = f'SAME_TIMESCALE'
    
    print(f"\n  ✓ EXP-1844 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(10, 6))
        wnames = list(windows.keys())
        s_snrs = [pop_snr[w]['supply'] for w in wnames]
        d_snrs = [pop_snr[w]['demand'] for w in wnames]
        
        x = range(len(wnames))
        ax.plot(x, s_snrs, 'o-', color='#e74c3c', label='Supply loss SNR', linewidth=2, markersize=8)
        ax.plot(x, d_snrs, 's-', color='#3498db', label='Demand loss SNR', linewidth=2, markersize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(wnames, rotation=45)
        ax.set_xlabel('Window Size')
        ax.set_ylabel('ISF Gradient SNR')
        ax.set_title('EXP-1844: At Which Timescale Does Each Loss Best Detect ISF Error?', fontweight='bold')
        ax.legend()
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig04-timescale-snr.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig04-timescale-snr.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'pop_snr': pop_snr,
        'best_supply_window': best_supply_window,
        'best_demand_window': best_demand_window,
    }


# ============================================================================
# EXP-1845: Parameter Identification — Which Setting Is Most Wrong?
# ============================================================================
def exp_1845(patients, figures_dir=None):
    """Can split-loss identify which therapy parameter is MOST wrong?
    
    For each patient, independently optimize ISF, CR, and basal to minimize
    supply-loss and demand-loss. If the two losses point at the SAME parameter
    as most wrong, that's strong evidence. If they disagree, the disagreement
    itself is informative.
    """
    print("\n" + "=" * 70)
    print("EXP-1845: Which Therapy Parameter Is Most Wrong?")
    print("=" * 70)
    
    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        settings = get_profile_settings(df)
        
        # For each parameter, find the scale that minimizes total loss
        param_opts = {}
        
        for param in ['isf', 'cr', 'basal']:
            def total_loss_fn(scale):
                sd = perturb_and_recompute(df, param, scale)
                dg = np.diff(glucose, prepend=glucose[0])
                residual = dg - sd['net']
                return np.nanmean(residual ** 2)
            
            def supply_loss_fn(scale):
                sd = perturb_and_recompute(df, param, scale)
                dg = np.diff(glucose, prepend=glucose[0])
                residual = dg - sd['net']
                rising = dg > 0.5
                return np.nanmean(residual[rising] ** 2) if np.any(rising) else 1e6
            
            def demand_loss_fn(scale):
                sd = perturb_and_recompute(df, param, scale)
                dg = np.diff(glucose, prepend=glucose[0])
                residual = dg - sd['net']
                falling = dg < -0.5
                return np.nanmean(residual[falling] ** 2) if np.any(falling) else 1e6
            
            # Optimize each
            total_opt = minimize_scalar(total_loss_fn, bounds=(0.3, 3.0), method='bounded')
            supply_opt = minimize_scalar(supply_loss_fn, bounds=(0.3, 3.0), method='bounded')
            demand_opt = minimize_scalar(demand_loss_fn, bounds=(0.3, 3.0), method='bounded')
            
            param_opts[param] = {
                'total_opt': float(total_opt.x),
                'supply_opt': float(supply_opt.x),
                'demand_opt': float(demand_opt.x),
                'total_improvement': float(total_loss_fn(1.0) - total_opt.fun),
                'supply_improvement': float(supply_loss_fn(1.0) - supply_opt.fun),
                'demand_improvement': float(demand_loss_fn(1.0) - demand_opt.fun),
            }
        
        # Which parameter gives most improvement when optimized?
        most_wrong_total = max(param_opts, key=lambda p: param_opts[p]['total_improvement'])
        most_wrong_supply = max(param_opts, key=lambda p: param_opts[p]['supply_improvement'])
        most_wrong_demand = max(param_opts, key=lambda p: param_opts[p]['demand_improvement'])
        
        patient_result = {
            'name': name,
            'settings': settings,
            'param_opts': param_opts,
            'most_wrong_total': most_wrong_total,
            'most_wrong_supply': most_wrong_supply,
            'most_wrong_demand': most_wrong_demand,
            'supply_demand_agree': most_wrong_supply == most_wrong_demand,
        }
        results_per_patient.append(patient_result)
        
        print(f"  {name}: most wrong → total={most_wrong_total} supply={most_wrong_supply} "
              f"demand={most_wrong_demand} {'✓AGREE' if most_wrong_supply == most_wrong_demand else '✗DISAGREE'}")
        for param in ['isf', 'cr', 'basal']:
            po = param_opts[param]
            print(f"    {param:6s}: total_opt={po['total_opt']:.2f}× supply_opt={po['supply_opt']:.2f}× "
                  f"demand_opt={po['demand_opt']:.2f}× Δtotal={po['total_improvement']:.2f}")
    
    # Population
    agree_count = sum(1 for r in results_per_patient if r['supply_demand_agree'])
    print(f"\n  S/D loss agree on most-wrong parameter: {agree_count}/{len(results_per_patient)}")
    
    # What's most commonly identified as most wrong?
    from collections import Counter
    total_votes = Counter(r['most_wrong_total'] for r in results_per_patient)
    supply_votes = Counter(r['most_wrong_supply'] for r in results_per_patient)
    demand_votes = Counter(r['most_wrong_demand'] for r in results_per_patient)
    
    print(f"  Most-wrong by total loss: {dict(total_votes)}")
    print(f"  Most-wrong by supply loss: {dict(supply_votes)}")
    print(f"  Most-wrong by demand loss: {dict(demand_votes)}")
    
    if agree_count >= 7:
        verdict = 'SPLIT_LOSS_CONSISTENT'
    elif agree_count >= 4:
        verdict = 'PARTIALLY_CONSISTENT'
    else:
        verdict = 'SPLIT_LOSS_DIVERGENT'
    
    print(f"\n  ✓ EXP-1845 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # Optimal scales by parameter and loss type
        ax = axes[0]
        params = ['isf', 'cr', 'basal']
        for i, param in enumerate(params):
            total_opts = [r['param_opts'][param]['total_opt'] for r in results_per_patient]
            supply_opts = [r['param_opts'][param]['supply_opt'] for r in results_per_patient]
            demand_opts = [r['param_opts'][param]['demand_opt'] for r in results_per_patient]
            
            x = i * 4
            ax.boxplot([total_opts], positions=[x], widths=0.6, patch_artist=True,
                      boxprops=dict(facecolor='#999999'))
            ax.boxplot([supply_opts], positions=[x+1], widths=0.6, patch_artist=True,
                      boxprops=dict(facecolor='#e74c3c'))
            ax.boxplot([demand_opts], positions=[x+2], widths=0.6, patch_artist=True,
                      boxprops=dict(facecolor='#3498db'))
        
        ax.set_xticks([1, 5, 9])
        ax.set_xticklabels(params)
        ax.axhline(y=1.0, color='black', linestyle='--', alpha=0.5)
        ax.set_ylabel('Optimal Scale Factor')
        ax.set_title('Optimal Therapy Scales\n(gray=total, red=supply, blue=demand)')
        
        # Improvement by parameter
        ax = axes[1]
        for i, param in enumerate(params):
            imps = [r['param_opts'][param]['total_improvement'] for r in results_per_patient]
            ax.bar(i, np.mean(imps), color=['#e74c3c', '#3498db', '#2ecc71'][i],
                   edgecolor='black', linewidth=0.5)
            ax.errorbar(i, np.mean(imps), yerr=np.std(imps), color='black', capsize=5)
        ax.set_xticks(range(3))
        ax.set_xticklabels(params)
        ax.set_ylabel('Loss Improvement (optimized - profile)')
        ax.set_title('Which Parameter Needs Most Adjustment?')
        
        fig.suptitle('EXP-1845: Split-Loss Parameter Identification', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig05-param-id.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig05-param-id.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
        'agreement_rate': agree_count / len(results_per_patient),
    }


# ============================================================================
# EXP-1846: AID Loop Compensation Signatures in Split Loss
# ============================================================================
def exp_1846(patients, figures_dir=None):
    """How does the AID loop's compensation appear in each loss component?
    
    The loop adjusts temp basals to compensate for setting errors. This
    compensation creates a signature: demand-loss should show higher variance
    when the loop is actively compensating (temp_rate ≠ scheduled_rate).
    """
    print("\n" + "=" * 70)
    print("EXP-1846: AID Loop Compensation in Split Loss")
    print("=" * 70)
    
    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd_data = compute_supply_demand(df)
        n = len(glucose)
        
        # Get temp rate and scheduled rate
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else None
        attrs = df.attrs if hasattr(df, 'attrs') else {}
        basal_sched = attrs.get('basal_schedule', {})
        
        if temp_rate is None or not basal_sched:
            print(f"  {name}: no temp_rate data, skipping")
            results_per_patient.append({'name': name, 'skipped': True})
            continue
        
        # Compute scheduled basal at each timestep
        sched_rate = np.full(n, np.nan)
        if isinstance(basal_sched, dict):
            mean_basal = np.mean([v for v in basal_sched.values() if isinstance(v, (int, float)) and v >= 0])
            sched_rate[:] = mean_basal
        
        # Loop activity: |temp_rate - scheduled_rate|
        loop_deviation = np.abs(np.nan_to_num(temp_rate) - np.nan_to_num(sched_rate))
        loop_active = loop_deviation > 0.05  # actively adjusting
        loop_inactive = ~loop_active
        
        # Compute split loss during active vs inactive loop
        dg = np.diff(glucose, prepend=glucose[0])
        net = sd_data['net']
        residual = dg - net
        
        rising = dg > 0.5
        falling = dg < -0.5
        
        # Supply loss: active vs inactive
        sl_active = np.nanmean(residual[rising & loop_active] ** 2) if np.any(rising & loop_active) else np.nan
        sl_inactive = np.nanmean(residual[rising & loop_inactive] ** 2) if np.any(rising & loop_inactive) else np.nan
        
        # Demand loss: active vs inactive
        dl_active = np.nanmean(residual[falling & loop_active] ** 2) if np.any(falling & loop_active) else np.nan
        dl_inactive = np.nanmean(residual[falling & loop_inactive] ** 2) if np.any(falling & loop_inactive) else np.nan
        
        loop_active_frac = np.mean(loop_active)
        
        # Correlation between loop deviation and each loss component
        # (rolling 1h windows)
        window = 12
        corrs_supply = []
        corrs_demand = []
        for i in range(window, n, window):
            seg = slice(i-window, i)
            r_seg = residual[seg]
            ld_seg = loop_deviation[seg]
            if np.all(np.isfinite(r_seg)) and np.std(ld_seg) > 0:
                r_rising = r_seg[dg[seg] > 0.5]
                r_falling = r_seg[dg[seg] < -0.5]
                if len(r_rising) > 3 and np.std(r_rising) > 0:
                    corrs_supply.append(np.corrcoef(np.abs(r_rising), ld_seg[dg[seg] > 0.5][:len(r_rising)])[0,1] if len(ld_seg[dg[seg] > 0.5]) == len(r_rising) else np.nan)
                if len(r_falling) > 3 and np.std(r_falling) > 0:
                    corrs_demand.append(np.corrcoef(np.abs(r_falling), ld_seg[dg[seg] < -0.5][:len(r_falling)])[0,1] if len(ld_seg[dg[seg] < -0.5]) == len(r_falling) else np.nan)
        
        corr_supply = np.nanmean(corrs_supply) if corrs_supply else np.nan
        corr_demand = np.nanmean(corrs_demand) if corrs_demand else np.nan
        
        patient_result = {
            'name': name,
            'loop_active_fraction': float(loop_active_frac),
            'supply_loss_active': float(sl_active) if np.isfinite(sl_active) else None,
            'supply_loss_inactive': float(sl_inactive) if np.isfinite(sl_inactive) else None,
            'demand_loss_active': float(dl_active) if np.isfinite(dl_active) else None,
            'demand_loss_inactive': float(dl_inactive) if np.isfinite(dl_inactive) else None,
            'supply_loss_ratio': float(sl_active / sl_inactive) if np.isfinite(sl_active) and np.isfinite(sl_inactive) and sl_inactive > 0 else None,
            'demand_loss_ratio': float(dl_active / dl_inactive) if np.isfinite(dl_active) and np.isfinite(dl_inactive) and dl_inactive > 0 else None,
        }
        results_per_patient.append(patient_result)
        
        sl_ratio = patient_result['supply_loss_ratio'] or np.nan
        dl_ratio = patient_result['demand_loss_ratio'] or np.nan
        print(f"  {name}: loop_active={loop_active_frac:.0%} "
              f"supply_ratio={sl_ratio:.2f} demand_ratio={dl_ratio:.2f}")
    
    valid = [r for r in results_per_patient if not r.get('skipped')]
    
    print(f"\n  Population AID loop compensation signatures (n={len(valid)}):")
    sl_ratios = [r['supply_loss_ratio'] for r in valid if r.get('supply_loss_ratio') is not None]
    dl_ratios = [r['demand_loss_ratio'] for r in valid if r.get('demand_loss_ratio') is not None]
    
    print(f"    Supply loss (active/inactive): {np.mean(sl_ratios):.2f} ± {np.std(sl_ratios):.2f}")
    print(f"    Demand loss (active/inactive): {np.mean(dl_ratios):.2f} ± {np.std(dl_ratios):.2f}")
    print(f"    Loop active fraction: {np.mean([r['loop_active_fraction'] for r in valid]):.0%}")
    
    # Does the loop create more demand-loss than supply-loss?
    if np.mean(dl_ratios) > np.mean(sl_ratios) * 1.2:
        verdict = 'LOOP_INFLATES_DEMAND_LOSS'
    elif np.mean(sl_ratios) > np.mean(dl_ratios) * 1.2:
        verdict = 'LOOP_INFLATES_SUPPLY_LOSS'
    else:
        verdict = 'LOOP_SYMMETRIC'
    
    print(f"\n  ✓ EXP-1846 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(8, 6))
        names = [r['name'] for r in valid]
        sl_r = [r.get('supply_loss_ratio', 1) or 1 for r in valid]
        dl_r = [r.get('demand_loss_ratio', 1) or 1 for r in valid]
        
        x = np.arange(len(names))
        width = 0.35
        ax.bar(x - width/2, sl_r, width, color='#e74c3c', label='Supply loss ratio', edgecolor='black', linewidth=0.5)
        ax.bar(x + width/2, dl_r, width, color='#3498db', label='Demand loss ratio', edgecolor='black', linewidth=0.5)
        ax.axhline(y=1.0, color='black', linestyle='--', alpha=0.5, label='No loop effect')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Loss Ratio (loop active / inactive)')
        ax.set_title('EXP-1846: AID Loop Impact on Split Loss', fontweight='bold')
        ax.legend()
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig06-loop-compensation.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig06-loop-compensation.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
    }


# ============================================================================
# EXP-1847: Cross-Patient Transfer of Split-Loss Therapy Estimates
# ============================================================================
def exp_1847(patients, figures_dir=None):
    """Do split-loss therapy estimates transfer across patients?
    
    If patient A's optimal ISF scale (from split loss) is similar when
    estimated from patient A's data vs inferred from population patterns,
    then the method generalizes.
    """
    print("\n" + "=" * 70)
    print("EXP-1847: Cross-Patient Transfer")
    print("=" * 70)
    
    # First, get each patient's optimal ISF scale from split loss
    per_patient_opts = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        settings = get_profile_settings(df)
        
        def total_loss(scale):
            sd = perturb_and_recompute(df, 'isf', scale)
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - sd['net']
            return np.nanmean(residual ** 2)
        
        opt = minimize_scalar(total_loss, bounds=(0.3, 3.0), method='bounded')
        
        # Also get from first half vs second half
        n = len(glucose)
        mid = n // 2
        
        def first_half_loss(scale):
            sd = perturb_and_recompute(df, 'isf', scale)
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg[:mid] - sd['net'][:mid]
            return np.nanmean(residual ** 2)
        
        def second_half_loss(scale):
            sd = perturb_and_recompute(df, 'isf', scale)
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg[mid:] - sd['net'][mid:]
            return np.nanmean(residual ** 2)
        
        opt_h1 = minimize_scalar(first_half_loss, bounds=(0.3, 3.0), method='bounded')
        opt_h2 = minimize_scalar(second_half_loss, bounds=(0.3, 3.0), method='bounded')
        
        per_patient_opts.append({
            'name': name,
            'isf_profile': settings['isf'],
            'optimal_scale': float(opt.x),
            'optimal_h1': float(opt_h1.x),
            'optimal_h2': float(opt_h2.x),
            'temporal_stability': float(abs(opt_h1.x - opt_h2.x)),
        })
        
        print(f"  {name}: ISF={settings['isf']:.0f} optimal={opt.x:.2f}× "
              f"h1={opt_h1.x:.2f}× h2={opt_h2.x:.2f}× stability={abs(opt_h1.x - opt_h2.x):.2f}")
    
    # Temporal stability
    stabilities = [r['temporal_stability'] for r in per_patient_opts]
    print(f"\n  Temporal stability (|h1 - h2|): {np.mean(stabilities):.3f} ± {np.std(stabilities):.3f}")
    
    # Leave-one-out: predict each patient's optimal from population mean
    opts = [r['optimal_scale'] for r in per_patient_opts]
    loo_errors = []
    for i in range(len(opts)):
        pop_mean = np.mean(opts[:i] + opts[i+1:])
        loo_errors.append(abs(opts[i] - pop_mean))
    
    print(f"  LOO prediction error: {np.mean(loo_errors):.3f} ± {np.std(loo_errors):.3f}")
    print(f"  Population optimal scale: {np.mean(opts):.2f} ± {np.std(opts):.2f}")
    
    if np.mean(stabilities) < 0.1 and np.mean(loo_errors) < 0.15:
        verdict = 'TRANSFERABLE'
    elif np.mean(stabilities) < 0.2:
        verdict = 'TEMPORALLY_STABLE'
    else:
        verdict = 'PATIENT_SPECIFIC'
    
    print(f"\n  ✓ EXP-1847 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        ax = axes[0]
        names = [r['name'] for r in per_patient_opts]
        h1s = [r['optimal_h1'] for r in per_patient_opts]
        h2s = [r['optimal_h2'] for r in per_patient_opts]
        x = range(len(names))
        ax.scatter(x, h1s, color='#e74c3c', s=80, label='First half', zorder=5)
        ax.scatter(x, h2s, color='#3498db', s=80, label='Second half', zorder=5)
        for i in x:
            ax.plot([i, i], [h1s[i], h2s[i]], 'k-', alpha=0.3)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
        ax.set_ylabel('Optimal ISF Scale')
        ax.set_title('Temporal Stability (1st vs 2nd half)')
        ax.legend()
        
        ax = axes[1]
        ax.scatter(opts, loo_errors, s=80, color='#2ecc71', edgecolor='black')
        for i, r in enumerate(per_patient_opts):
            ax.annotate(r['name'], (opts[i], loo_errors[i]), fontsize=8)
        ax.set_xlabel('Optimal ISF Scale')
        ax.set_ylabel('LOO Prediction Error')
        ax.set_title('Population Transfer Error')
        
        fig.suptitle('EXP-1847: Does Split-Loss ISF Estimation Transfer?', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig07-transfer.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig07-transfer.png")
    
    return {
        'verdict': verdict,
        'patients': per_patient_opts,
        'mean_stability': float(np.mean(stabilities)),
        'mean_loo_error': float(np.mean(loo_errors)),
    }


# ============================================================================
# EXP-1848: Combined Split-Loss Therapy Estimator
# ============================================================================
def exp_1848(patients, figures_dir=None):
    """Full split-loss therapy estimator: estimate ISF, CR, basal simultaneously.
    
    Compare against:
    1. Profile settings (status quo)
    2. Response-curve ISF (EXP-1301 method)
    3. Bolus-gate deconfounding (EXP-1371 method)
    """
    print("\n" + "=" * 70)
    print("EXP-1848: Combined Split-Loss Therapy Estimator")
    print("=" * 70)
    
    results_per_patient = []
    
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        settings = get_profile_settings(df)
        n = len(glucose)
        
        # Split-loss approach: optimize ISF, CR, basal jointly
        # Use supply loss for CR, demand loss for ISF/basal
        
        def combined_loss(params):
            isf_scale, cr_scale, basal_scale = params
            # Apply all perturbations
            sd = compute_supply_demand(df)
            supply = sd['hepatic'] + sd.get('carb_supply', np.zeros(n)) * cr_scale
            demand = sd['demand'] * isf_scale * basal_scale
            net = supply - demand
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - net
            return np.nanmean(residual ** 2)
        
        def supply_loss(params):
            isf_scale, cr_scale, basal_scale = params
            sd = compute_supply_demand(df)
            supply = sd['hepatic'] + sd.get('carb_supply', np.zeros(n)) * cr_scale
            demand = sd['demand'] * isf_scale * basal_scale
            net = supply - demand
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - net
            rising = dg > 0.5
            return np.nanmean(residual[rising] ** 2) if np.any(rising) else 1e6
        
        def demand_loss(params):
            isf_scale, cr_scale, basal_scale = params
            sd = compute_supply_demand(df)
            supply = sd['hepatic'] + sd.get('carb_supply', np.zeros(n)) * cr_scale
            demand = sd['demand'] * isf_scale * basal_scale
            net = supply - demand
            dg = np.diff(glucose, prepend=glucose[0])
            residual = dg - net
            falling = dg < -0.5
            return np.nanmean(residual[falling] ** 2) if np.any(falling) else 1e6
        
        from scipy.optimize import minimize
        
        # Optimize total loss
        res_total = minimize(combined_loss, [1.0, 1.0, 1.0], 
                            bounds=[(0.3, 3.0), (0.3, 3.0), (0.3, 3.0)],
                            method='L-BFGS-B')
        
        # Optimize supply + demand losses separately and combine
        res_supply = minimize(supply_loss, [1.0, 1.0, 1.0],
                             bounds=[(0.3, 3.0), (0.3, 3.0), (0.3, 3.0)],
                             method='L-BFGS-B')
        res_demand = minimize(demand_loss, [1.0, 1.0, 1.0],
                             bounds=[(0.3, 3.0), (0.3, 3.0), (0.3, 3.0)],
                             method='L-BFGS-B')
        
        # Split-loss estimate: CR from supply, ISF/basal from demand
        split_estimate = [res_demand.x[0], res_supply.x[1], res_demand.x[2]]
        
        # Evaluate all estimates
        baseline_loss = combined_loss([1.0, 1.0, 1.0])
        total_opt_loss = combined_loss(res_total.x)
        split_opt_loss = combined_loss(split_estimate)
        
        patient_result = {
            'name': name,
            'settings': settings,
            'baseline_loss': float(baseline_loss),
            'total_opt': [float(x) for x in res_total.x],
            'total_opt_loss': float(total_opt_loss),
            'supply_opt': [float(x) for x in res_supply.x],
            'demand_opt': [float(x) for x in res_demand.x],
            'split_estimate': [float(x) for x in split_estimate],
            'split_opt_loss': float(split_opt_loss),
            'improvement_total': float(baseline_loss - total_opt_loss),
            'improvement_split': float(baseline_loss - split_opt_loss),
        }
        results_per_patient.append(patient_result)
        
        print(f"  {name}: ISF={settings['isf']:.0f} CR={settings['cr']:.1f} basal={settings['basal']:.2f}")
        print(f"    Total opt: ISF×{res_total.x[0]:.2f} CR×{res_total.x[1]:.2f} basal×{res_total.x[2]:.2f} (loss={total_opt_loss:.2f})")
        print(f"    Split est: ISF×{split_estimate[0]:.2f} CR×{split_estimate[1]:.2f} basal×{split_estimate[2]:.2f} (loss={split_opt_loss:.2f})")
        print(f"    Baseline loss={baseline_loss:.2f} → total Δ={baseline_loss-total_opt_loss:.2f}, split Δ={baseline_loss-split_opt_loss:.2f}")
    
    # Population
    print(f"\n  Population therapy estimation comparison:")
    
    total_imps = [r['improvement_total'] for r in results_per_patient]
    split_imps = [r['improvement_split'] for r in results_per_patient]
    
    print(f"    Total optimization improvement: {np.mean(total_imps):.3f} ± {np.std(total_imps):.3f}")
    print(f"    Split-loss estimation improvement: {np.mean(split_imps):.3f} ± {np.std(split_imps):.3f}")
    print(f"    Split captures {np.mean(split_imps)/np.mean(total_imps)*100:.0f}% of total optimization")
    
    # Mean optimal scales
    total_isf = np.mean([r['total_opt'][0] for r in results_per_patient])
    total_cr = np.mean([r['total_opt'][1] for r in results_per_patient])
    total_basal = np.mean([r['total_opt'][2] for r in results_per_patient])
    split_isf = np.mean([r['split_estimate'][0] for r in results_per_patient])
    split_cr = np.mean([r['split_estimate'][1] for r in results_per_patient])
    split_basal = np.mean([r['split_estimate'][2] for r in results_per_patient])
    
    print(f"\n    Population mean optimal scales:")
    print(f"      Total opt: ISF×{total_isf:.2f} CR×{total_cr:.2f} basal×{total_basal:.2f}")
    print(f"      Split est: ISF×{split_isf:.2f} CR×{split_cr:.2f} basal×{split_basal:.2f}")
    
    ratio = np.mean(split_imps) / np.mean(total_imps) if np.mean(total_imps) > 0 else 0
    if ratio > 0.8:
        verdict = 'SPLIT_LOSS_NEAR_OPTIMAL'
    elif ratio > 0.5:
        verdict = 'SPLIT_LOSS_USEFUL'
    else:
        verdict = 'TOTAL_LOSS_BETTER'
    
    print(f"\n  ✓ EXP-1848 verdict: {verdict}")
    
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # Per-patient improvement
        ax = axes[0]
        names = [r['name'] for r in results_per_patient]
        x = range(len(names))
        ax.bar([xi - 0.2 for xi in x], total_imps, 0.35, color='#3498db', label='Total optimization', edgecolor='black', linewidth=0.5)
        ax.bar([xi + 0.2 for xi in x], split_imps, 0.35, color='#e74c3c', label='Split-loss estimate', edgecolor='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Loss Improvement over Profile')
        ax.set_title('Split-Loss vs Total Optimization')
        ax.legend()
        
        # Optimal ISF scales comparison
        ax = axes[1]
        t_isf = [r['total_opt'][0] for r in results_per_patient]
        s_isf = [r['split_estimate'][0] for r in results_per_patient]
        ax.scatter(t_isf, s_isf, s=80, color='#2ecc71', edgecolor='black')
        for i, r in enumerate(results_per_patient):
            ax.annotate(r['name'], (t_isf[i], s_isf[i]), fontsize=8)
        ax.plot([0.3, 3], [0.3, 3], 'k--', alpha=0.3)
        ax.set_xlabel('Total-Optimal ISF Scale')
        ax.set_ylabel('Split-Loss ISF Scale')
        ax.set_title('ISF Estimate Agreement')
        
        fig.suptitle('EXP-1848: Split-Loss Therapy Estimator', fontsize=14, fontweight='bold')
        plt.tight_layout()
        path = os.path.join(figures_dir, 'splitloss-fig08-combined-estimator.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved splitloss-fig08-combined-estimator.png")
    
    return {
        'verdict': verdict,
        'patients': results_per_patient,
    }


# ============================================================================
# Main
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='EXP-1841–1848: Split-Loss Therapy Deconfounding')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-1841–1848: Split-Loss Therapy Deconfounding")
    print("=" * 70)

    patients = load_patients('externals/ns-data/patients/')
    print(f"Loaded {len(patients)} patients\n")

    figures_dir = FIGURES_DIR if args.figures else None
    if figures_dir:
        os.makedirs(figures_dir, exist_ok=True)

    experiments = [
        (1841, 'Split-Loss ISF Sensitivity', exp_1841),
        (1842, 'Demand-Side Loss for Basal Assessment', exp_1842),
        (1843, 'Supply-Side Loss for CR Assessment', exp_1843),
        (1844, 'Timescale-Dependent Deconfounding', exp_1844),
        (1845, 'Which Therapy Parameter Is Most Wrong?', exp_1845),
        (1846, 'AID Loop Compensation in Split Loss', exp_1846),
        (1847, 'Cross-Patient Transfer', exp_1847),
        (1848, 'Combined Split-Loss Therapy Estimator', exp_1848),
    ]

    all_results = {}
    for eid, title, func in experiments:
        if args.exp and args.exp != eid:
            continue
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{eid}: {title}")
        print(f"{'#' * 70}")

        try:
            result = func(patients, figures_dir)
            all_results[f'EXP-{eid}'] = result
        except Exception as e:
            print(f"\n  ✗ EXP-{eid} FAILED: {e}")
            import traceback
            traceback.print_exc()
            all_results[f'EXP-{eid}'] = {'verdict': f'FAILED: {e}'}

    # Save results
    output_path = os.path.join('externals', 'experiments', 'exp-1841_splitloss_therapy.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def make_serializable(obj):
        if isinstance(obj, np.floating):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        return obj

    output = {
        'experiment': 'EXP-1841 to EXP-1848',
        'title': 'Split-Loss Therapy Deconfounding',
        'results': make_serializable(all_results),
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n✓ Results saved to {output_path}")

    print(f"\n{'=' * 70}")
    print(f"SYNTHESIS: Split-Loss Therapy Deconfounding")
    print(f"{'=' * 70}")
    for eid_str, result in all_results.items():
        print(f"  {eid_str}: {result.get('verdict', '?')}")

    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
