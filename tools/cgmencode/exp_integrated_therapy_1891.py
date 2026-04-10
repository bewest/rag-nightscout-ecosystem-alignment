#!/usr/bin/env python3
"""EXP-1891–1898: Integrated Therapy Assessment & Production Pipeline.

Combines findings from all prior experiment batches into a unified therapy
assessment pipeline. Tests cross-validation, cross-patient transfer,
glycemic quality metrics, and produces per-patient therapy report cards.

Prior findings leveraged:
  EXP-1848: Split-loss ISF (supply+demand model, 97% of optimal)
  EXP-1856: Dose-dependent ISF (Hill equation, slope -0.89)
  EXP-1874: CR 38% too high (all 11 patients)
  EXP-1878: Equation-based CR (+20% improvement)
  EXP-1885: Overnight drift basal assessment
  EXP-1888: Combined deconfounded assessment (2.5/3 wrong)
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
RESULTS_PATH = Path('externals/experiments/exp-1891_integrated_therapy.json')

# --- Helpers reused from prior scripts ---

def get_isf(patient):
    isf_sched = patient['df'].attrs.get('isf_schedule', None)
    if isf_sched and isinstance(isf_sched, list) and len(isf_sched) > 0:
        val = isf_sched[0].get('value', isf_sched[0].get('sensitivity', 50))
        if val < 15:
            val *= 18.0182
        return val
    return 50

def get_cr(patient):
    cr_sched = patient['df'].attrs.get('cr_schedule', None)
    if cr_sched and isinstance(cr_sched, list) and len(cr_sched) > 0:
        return cr_sched[0].get('value', cr_sched[0].get('ratio', 10))
    return 10

def get_basal(patient):
    basal_sched = patient['df'].attrs.get('basal_schedule', None)
    if basal_sched and isinstance(basal_sched, list) and len(basal_sched) > 0:
        return basal_sched[0].get('value', basal_sched[0].get('rate', 1.0))
    return 1.0

def supply_demand_loss(sd, glucose, mask=None):
    """Compute supply/demand model loss (mean squared residual)."""
    net = sd.get('net', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])
    residual = dg - net
    if mask is not None:
        residual = residual[mask]
    valid = np.isfinite(residual)
    if valid.sum() < 10:
        return np.nan
    return float(np.mean(residual[valid] ** 2))

def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    """Find meal events."""
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    glucose = df['glucose'].values
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    meals = []
    i = 0
    while i < len(carbs):
        if carbs[i] >= min_carbs:
            g_pre = glucose[max(0, i - pre_window):i]
            g_pre_val = np.nanmean(g_pre) if len(g_pre) > 0 and np.any(np.isfinite(g_pre)) else np.nan
            end = min(len(glucose), i + post_window)
            g_post = glucose[i:end]
            if len(g_post) > 6 and np.sum(np.isfinite(g_post)) > 6:
                g_peak = np.nanmax(g_post)
                excursion = g_peak - g_pre_val if np.isfinite(g_pre_val) else np.nan
                # Sum bolus within ±6 steps of meal
                b_start = max(0, i - 6)
                b_end = min(len(bolus), i + 6)
                total_bolus = np.nansum(bolus[b_start:b_end])
                meals.append({
                    'index': i,
                    'carbs': float(carbs[i]),
                    'glucose_pre': float(g_pre_val),
                    'glucose_peak': float(g_peak),
                    'excursion': float(excursion),
                    'bolus': float(total_bolus),
                })
            i += post_window
        else:
            i += 1
    return meals

def overnight_drift(df):
    """Compute overnight glucose drift (midnight-6am) per night."""
    glucose = df['glucose'].values
    n = len(glucose)
    steps_per_day = 288
    drifts = []
    for day_start in range(0, n - steps_per_day, steps_per_day):
        # Midnight = day_start, 6am = day_start + 72
        midnight_idx = day_start
        sixam_idx = day_start + 72
        if sixam_idx >= n:
            continue
        g_window = glucose[midnight_idx:sixam_idx]
        valid = np.isfinite(g_window)
        if valid.sum() < 60:
            continue
        g_start = np.nanmean(g_window[:6])
        g_end = np.nanmean(g_window[-6:])
        if np.isfinite(g_start) and np.isfinite(g_end):
            drift_per_h = (g_end - g_start) / 6.0
            drifts.append(drift_per_h)
    return drifts

def glycemic_metrics(glucose):
    """Compute standard glycemic quality metrics."""
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 100:
        return {}
    mean_g = np.mean(valid)
    std_g = np.std(valid)
    cv = std_g / mean_g if mean_g > 0 else np.nan
    # Time in range
    tir = np.mean((valid >= 70) & (valid <= 180))
    tbr = np.mean(valid < 70)
    tbr_severe = np.mean(valid < 54)
    tar = np.mean(valid > 180)
    tar_severe = np.mean(valid > 250)
    # Estimated A1C (eA1C)
    ea1c = (mean_g + 46.7) / 28.7
    # LBGI / HBGI (simplified)
    f_bg = 1.509 * (np.log(np.maximum(valid, 1)) ** 1.084 - 5.381)
    rl = np.where(f_bg < 0, 10 * f_bg ** 2, 0)
    rh = np.where(f_bg > 0, 10 * f_bg ** 2, 0)
    lbgi = np.mean(rl)
    hbgi = np.mean(rh)
    # GVI (Glycemic Variability Index) = path_length / ideal_path
    diffs = np.abs(np.diff(valid))
    path_length = np.sum(diffs)
    ideal_length = abs(valid[-1] - valid[0])
    gvi = path_length / max(ideal_length, 1)
    return {
        'mean_glucose': round(float(mean_g), 1),
        'std_glucose': round(float(std_g), 1),
        'cv': round(float(cv), 3),
        'tir': round(float(tir), 3),
        'tbr': round(float(tbr), 4),
        'tbr_severe': round(float(tbr_severe), 4),
        'tar': round(float(tar), 3),
        'tar_severe': round(float(tar_severe), 3),
        'ea1c': round(float(ea1c), 2),
        'lbgi': round(float(lbgi), 2),
        'hbgi': round(float(hbgi), 2),
        'gvi': round(float(gvi), 1),
        'n_readings': len(valid),
    }


# ======================================================================
# EXP-1891: Unified Therapy Estimator
# ======================================================================

def exp_1891(patients, figures_dir):
    """Combine equation-based CR, split-loss ISF, and overnight drift basal
    into a unified therapy estimator. Compare to profile settings."""
    print("\n" + "=" * 70)
    print("EXP-1891: Unified Therapy Estimator")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        isf_profile = get_isf(p)
        cr_profile = get_cr(p)
        basal_profile = get_basal(p)

        # 1. Split-loss ISF: grid search for optimal scale
        sd = compute_supply_demand(df)
        best_isf_scale = 1.0
        best_loss = np.inf
        for scale in np.arange(0.1, 3.01, 0.05):
            sd_scaled = dict(sd)
            supply = sd.get('supply', np.zeros_like(glucose))
            demand = sd.get('demand', np.zeros_like(glucose))
            sd_scaled['net'] = supply - demand * scale
            loss = supply_demand_loss(sd_scaled, glucose)
            if np.isfinite(loss) and loss < best_loss:
                best_loss = loss
                best_isf_scale = scale
        optimal_isf = isf_profile * best_isf_scale

        # 2. Equation-based CR from meals
        meals = find_meals(df)
        cr_estimates = []
        for m in meals:
            if m['bolus'] > 0.1 and np.isfinite(m['excursion']) and m['carbs'] > 0:
                # CR = carbs * ISF / (excursion + bolus * ISF)
                denom = m['excursion'] + m['bolus'] * optimal_isf
                if denom > 0:
                    cr_est = m['carbs'] * optimal_isf / denom
                    if 0.5 < cr_est < 50:
                        cr_estimates.append(cr_est)
        optimal_cr = float(np.median(cr_estimates)) if cr_estimates else cr_profile

        # 3. Overnight drift for basal
        drifts = overnight_drift(df)
        mean_drift = float(np.nanmean(drifts)) if drifts else 0.0
        # Positive drift → basal too low → increase
        # Each +1 mg/dL/h of drift needs ~ISF correction
        basal_adjustment = mean_drift / optimal_isf if optimal_isf > 0 else 0
        optimal_basal = max(0, basal_profile + basal_adjustment)

        # Mismatches
        isf_mismatch = (optimal_isf - isf_profile) / isf_profile if isf_profile > 0 else 0
        cr_mismatch = (optimal_cr - cr_profile) / cr_profile if cr_profile > 0 else 0
        basal_mismatch = (optimal_basal - basal_profile) / basal_profile if basal_profile > 0 else 0

        result = {
            'patient': name,
            'isf_profile': isf_profile, 'isf_optimal': round(optimal_isf, 1),
            'isf_scale': round(best_isf_scale, 2), 'isf_mismatch': round(isf_mismatch, 2),
            'cr_profile': cr_profile, 'cr_optimal': round(optimal_cr, 1),
            'cr_mismatch': round(cr_mismatch, 2), 'n_meals': len(cr_estimates),
            'basal_profile': basal_profile, 'basal_optimal': round(optimal_basal, 2),
            'basal_mismatch': round(basal_mismatch, 2),
            'overnight_drift': round(mean_drift, 2),
            'sd_loss_profile': round(supply_demand_loss(sd, glucose), 2),
            'sd_loss_optimal': round(best_loss, 2),
        }
        results.append(result)
        print(f"  {name}: ISF {isf_profile}→{optimal_isf:.0f} ({isf_mismatch:+.0%})"
              f"  CR {cr_profile}→{optimal_cr:.1f} ({cr_mismatch:+.0%})"
              f"  Basal {basal_profile}→{optimal_basal:.2f} ({basal_mismatch:+.0%})")

    # Population
    isf_mismatches = [r['isf_mismatch'] for r in results]
    cr_mismatches = [r['cr_mismatch'] for r in results]
    basal_mismatches = [r['basal_mismatch'] for r in results]
    print(f"\n  Population unified estimator:")
    print(f"    Mean ISF mismatch: {np.mean(isf_mismatches):+.0%}")
    print(f"    Mean CR mismatch: {np.mean(cr_mismatches):+.0%}")
    print(f"    Mean basal mismatch: {np.mean(basal_mismatches):+.0%}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # ISF comparison
        axes[0].bar(x - 0.15, [r['isf_profile'] for r in results], 0.3, label='Profile', alpha=0.7)
        axes[0].bar(x + 0.15, [r['isf_optimal'] for r in results], 0.3, label='Optimal', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('ISF (mg/dL per U)')
        axes[0].set_title('ISF: Profile vs Optimal')
        axes[0].legend()

        # CR comparison
        axes[1].bar(x - 0.15, [r['cr_profile'] for r in results], 0.3, label='Profile', alpha=0.7)
        axes[1].bar(x + 0.15, [r['cr_optimal'] for r in results], 0.3, label='Optimal', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('CR (g carbs per U)')
        axes[1].set_title('CR: Profile vs Optimal')
        axes[1].legend()

        # Basal comparison
        axes[2].bar(x - 0.15, [r['basal_profile'] for r in results], 0.3, label='Profile', alpha=0.7)
        axes[2].bar(x + 0.15, [r['basal_optimal'] for r in results], 0.3, label='Optimal', alpha=0.7)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(names)
        axes[2].set_ylabel('Basal Rate (U/h)')
        axes[2].set_title('Basal: Profile vs Optimal')
        axes[2].legend()

        plt.suptitle('EXP-1891: Unified Therapy Estimator — Profile vs Optimal', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig01-unified-estimator.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = "UNIFIED_ESTIMATOR_COMPLETE"
    print(f"\n  ✓ EXP-1891 verdict: {verdict}")
    return {
        'experiment': 'EXP-1891', 'title': 'Unified Therapy Estimator',
        'verdict': verdict,
        'mean_isf_mismatch': round(float(np.mean(isf_mismatches)), 3),
        'mean_cr_mismatch': round(float(np.mean(cr_mismatches)), 3),
        'mean_basal_mismatch': round(float(np.mean(basal_mismatches)), 3),
        'per_patient': results,
    }


# ======================================================================
# EXP-1892: Temporal Cross-Validation
# ======================================================================

def exp_1892(patients, figures_dir):
    """Estimate therapy params on first half, evaluate glucose quality on second half.
    Compare profile settings vs optimized settings."""
    print("\n" + "=" * 70)
    print("EXP-1892: Temporal Cross-Validation")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        n = len(glucose)
        mid = n // 2

        # Split
        df_h1 = df.iloc[:mid].copy()
        df_h2 = df.iloc[mid:].copy()
        g_h1 = glucose[:mid]
        g_h2 = glucose[mid:]

        isf_profile = get_isf(p)
        cr_profile = get_cr(p)

        # Estimate ISF on half 1
        sd_h1 = compute_supply_demand(df_h1)
        best_scale = 1.0
        best_loss = np.inf
        for scale in np.arange(0.1, 3.01, 0.1):
            sd_s = dict(sd_h1)
            sd_s['net'] = sd_h1.get('supply', np.zeros(mid)) - sd_h1.get('demand', np.zeros(mid)) * scale
            loss = supply_demand_loss(sd_s, g_h1)
            if np.isfinite(loss) and loss < best_loss:
                best_loss = loss
                best_scale = scale

        # Evaluate on half 2
        sd_h2 = compute_supply_demand(df_h2)
        # Profile loss
        loss_profile_h2 = supply_demand_loss(sd_h2, g_h2)
        # Optimized loss (using half-1 scale)
        sd_opt = dict(sd_h2)
        sd_opt['net'] = sd_h2.get('supply', np.zeros(len(g_h2))) - sd_h2.get('demand', np.zeros(len(g_h2))) * best_scale
        loss_optimized_h2 = supply_demand_loss(sd_opt, g_h2)

        # Glycemic metrics for half 2
        metrics_h2 = glycemic_metrics(g_h2)

        improvement = (loss_profile_h2 - loss_optimized_h2) / loss_profile_h2 if loss_profile_h2 > 0 else 0

        result = {
            'patient': name,
            'isf_scale_h1': round(best_scale, 2),
            'loss_profile_h2': round(float(loss_profile_h2), 2) if np.isfinite(loss_profile_h2) else None,
            'loss_optimized_h2': round(float(loss_optimized_h2), 2) if np.isfinite(loss_optimized_h2) else None,
            'improvement': round(float(improvement), 3),
            'tir_h2': metrics_h2.get('tir', None),
            'cv_h2': metrics_h2.get('cv', None),
            'ea1c_h2': metrics_h2.get('ea1c', None),
        }
        results.append(result)
        imp_str = f"{improvement:+.1%}" if np.isfinite(improvement) else "N/A"
        print(f"  {name}: scale_h1={best_scale:.2f} loss_profile={loss_profile_h2:.1f}"
              f" loss_opt={loss_optimized_h2:.1f} improvement={imp_str}"
              f" TIR={metrics_h2.get('tir', 0):.1%}")

    improvements = [r['improvement'] for r in results if r['improvement'] is not None]
    transfers = sum(1 for i in improvements if i > 0)
    print(f"\n  Population cross-validation:")
    print(f"    Mean improvement: {np.mean(improvements):+.1%}")
    print(f"    Transfer success: {transfers}/{len(improvements)}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # Loss comparison
        l_prof = [r['loss_profile_h2'] or 0 for r in results]
        l_opt = [r['loss_optimized_h2'] or 0 for r in results]
        axes[0].bar(x - 0.15, l_prof, 0.3, label='Profile', alpha=0.7, color='salmon')
        axes[0].bar(x + 0.15, l_opt, 0.3, label='Optimized (from H1)', alpha=0.7, color='steelblue')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('S/D Model Loss')
        axes[0].set_title('Half-2 Loss: Profile vs Optimized-from-Half-1')
        axes[0].legend()

        # Improvement bars
        imps = [r['improvement'] or 0 for r in results]
        colors = ['green' if i > 0 else 'red' for i in imps]
        axes[1].bar(x, [i * 100 for i in imps], color=colors, alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Improvement (%)')
        axes[1].set_title('Cross-Temporal Transfer: H1→H2 Improvement')
        axes[1].axhline(0, color='black', linewidth=0.5)

        plt.suptitle('EXP-1892: Temporal Cross-Validation', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig02-temporal-crossval.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"TRANSFERS_{transfers}_OF_{len(improvements)}"
    print(f"\n  ✓ EXP-1892 verdict: {verdict}")
    return {
        'experiment': 'EXP-1892', 'title': 'Temporal Cross-Validation',
        'verdict': verdict,
        'mean_improvement': round(float(np.mean(improvements)), 3),
        'transfer_success': transfers,
        'n_patients': len(improvements),
        'per_patient': results,
    }


# ======================================================================
# EXP-1893: Cross-Patient Transfer
# ======================================================================

def exp_1893(patients, figures_dir):
    """Test if therapy estimation methods generalize across patients.
    For each patient pair (A→B), estimate ISF scale on A and apply to B."""
    print("\n" + "=" * 70)
    print("EXP-1893: Cross-Patient Transfer")
    print("=" * 70)

    # First, compute each patient's optimal ISF scale
    patient_scales = {}
    patient_losses = {}
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        best_scale = 1.0
        best_loss = np.inf
        for scale in np.arange(0.1, 3.01, 0.1):
            sd_s = dict(sd)
            sd_s['net'] = sd.get('supply', np.zeros_like(glucose)) - sd.get('demand', np.zeros_like(glucose)) * scale
            loss = supply_demand_loss(sd_s, glucose)
            if np.isfinite(loss) and loss < best_loss:
                best_loss = loss
                best_scale = scale
        patient_scales[name] = best_scale
        patient_losses[name] = {'sd': sd, 'glucose': glucose, 'best_loss': best_loss}

    # Cross-patient transfer matrix
    n_patients = len(patients)
    transfer_matrix = np.zeros((n_patients, n_patients))
    names = [p['name'] for p in patients]

    for i, source in enumerate(patients):
        source_scale = patient_scales[source['name']]
        for j, target in enumerate(patients):
            tgt = patient_losses[target['name']]
            sd = tgt['sd']
            glucose = tgt['glucose']
            # Apply source's scale to target
            sd_s = dict(sd)
            sd_s['net'] = sd.get('supply', np.zeros_like(glucose)) - sd.get('demand', np.zeros_like(glucose)) * source_scale
            loss_transfer = supply_demand_loss(sd_s, glucose)
            loss_own = tgt['best_loss']
            # Improvement relative to own optimal
            if loss_own > 0 and np.isfinite(loss_transfer):
                transfer_matrix[i, j] = (loss_own - loss_transfer) / loss_own
            else:
                transfer_matrix[i, j] = np.nan

    # Diagonal should be ~0 (own scale on own data)
    # Off-diagonal: positive = source scale helps target
    off_diag = []
    for i in range(n_patients):
        for j in range(n_patients):
            if i != j and np.isfinite(transfer_matrix[i, j]):
                off_diag.append(transfer_matrix[i, j])

    positive_transfers = sum(1 for v in off_diag if v >= -0.1)  # within 10% of optimal
    mean_degradation = np.mean(off_diag)

    # Population scale statistics
    scales = list(patient_scales.values())
    scale_std = np.std(scales)
    scale_mean = np.mean(scales)

    for name, scale in patient_scales.items():
        print(f"  {name}: optimal_scale={scale:.2f}")
    print(f"\n  Population ISF scale: mean={scale_mean:.2f} std={scale_std:.2f}")
    print(f"  Cross-patient transfer: {positive_transfers}/{len(off_diag)} within 10% of optimal")
    print(f"  Mean degradation from cross-patient: {mean_degradation:+.1%}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Transfer matrix heatmap
        im = axes[0].imshow(transfer_matrix * 100, cmap='RdYlGn', vmin=-50, vmax=10, aspect='auto')
        axes[0].set_xticks(range(n_patients))
        axes[0].set_xticklabels(names, fontsize=8)
        axes[0].set_yticks(range(n_patients))
        axes[0].set_yticklabels(names, fontsize=8)
        axes[0].set_xlabel('Target Patient')
        axes[0].set_ylabel('Source Patient (scale donor)')
        axes[0].set_title('Transfer Matrix (% vs optimal)')
        plt.colorbar(im, ax=axes[0], label='% improvement')

        # Scale distribution
        axes[1].bar(range(n_patients), scales, alpha=0.7, color='steelblue')
        axes[1].axhline(scale_mean, color='red', linestyle='--', label=f'Mean={scale_mean:.2f}')
        axes[1].set_xticks(range(n_patients))
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Optimal ISF Scale')
        axes[1].set_title('Per-Patient Optimal ISF Scale')
        axes[1].legend()

        plt.suptitle('EXP-1893: Cross-Patient Transfer', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig03-cross-patient.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"CROSS_PATIENT_{'WORKS' if positive_transfers > len(off_diag) * 0.5 else 'FAILS'}"
    print(f"\n  ✓ EXP-1893 verdict: {verdict}")
    return {
        'experiment': 'EXP-1893', 'title': 'Cross-Patient Transfer',
        'verdict': verdict,
        'scale_mean': round(float(scale_mean), 2),
        'scale_std': round(float(scale_std), 2),
        'positive_transfers': positive_transfers,
        'total_pairs': len(off_diag),
        'mean_degradation': round(float(mean_degradation), 3),
        'per_patient': [{'patient': n, 'optimal_scale': round(s, 2)} for n, s in patient_scales.items()],
    }


# ======================================================================
# EXP-1894: Glycemic Variability Metrics
# ======================================================================

def exp_1894(patients, figures_dir):
    """Compute comprehensive glycemic quality metrics for each patient.
    Establish baseline for evaluating therapy optimization."""
    print("\n" + "=" * 70)
    print("EXP-1894: Glycemic Variability Metrics")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        glucose = p['df']['glucose'].values
        metrics = glycemic_metrics(glucose)
        metrics['patient'] = name
        results.append(metrics)
        print(f"  {name}: TIR={metrics.get('tir',0):.1%} eA1c={metrics.get('ea1c',0):.1f}"
              f" CV={metrics.get('cv',0):.3f} LBGI={metrics.get('lbgi',0):.1f}"
              f" HBGI={metrics.get('hbgi',0):.1f} GVI={metrics.get('gvi',0):.0f}")

    # Population
    tirs = [r.get('tir', 0) for r in results]
    cvs = [r.get('cv', 0) for r in results]
    ea1cs = [r.get('ea1c', 0) for r in results]
    print(f"\n  Population glycemic metrics:")
    print(f"    Mean TIR: {np.mean(tirs):.1%}")
    print(f"    Mean CV: {np.mean(cvs):.3f}")
    print(f"    Mean eA1c: {np.mean(ea1cs):.1f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # TIR
        axes[0, 0].bar(x, [r.get('tir', 0) * 100 for r in results], alpha=0.7, color='green')
        axes[0, 0].axhline(70, color='red', linestyle='--', label='Target (70%)')
        axes[0, 0].set_xticks(x)
        axes[0, 0].set_xticklabels(names)
        axes[0, 0].set_ylabel('Time in Range (%)')
        axes[0, 0].set_title('Time in Range (70–180 mg/dL)')
        axes[0, 0].legend()

        # eA1c
        axes[0, 1].bar(x, [r.get('ea1c', 0) for r in results], alpha=0.7, color='steelblue')
        axes[0, 1].axhline(7.0, color='red', linestyle='--', label='Target (7.0%)')
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(names)
        axes[0, 1].set_ylabel('Estimated A1c (%)')
        axes[0, 1].set_title('Estimated A1c')
        axes[0, 1].legend()

        # LBGI vs HBGI
        axes[1, 0].bar(x - 0.15, [r.get('lbgi', 0) for r in results], 0.3, label='LBGI', alpha=0.7, color='blue')
        axes[1, 0].bar(x + 0.15, [r.get('hbgi', 0) for r in results], 0.3, label='HBGI', alpha=0.7, color='red')
        axes[1, 0].set_xticks(x)
        axes[1, 0].set_xticklabels(names)
        axes[1, 0].set_ylabel('Risk Index')
        axes[1, 0].set_title('Low/High Blood Glucose Index')
        axes[1, 0].legend()

        # CV
        axes[1, 1].bar(x, [r.get('cv', 0) for r in results], alpha=0.7, color='orange')
        axes[1, 1].axhline(0.36, color='red', linestyle='--', label='Threshold (36%)')
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels(names)
        axes[1, 1].set_ylabel('CV')
        axes[1, 1].set_title('Coefficient of Variation')
        axes[1, 1].legend()

        plt.suptitle('EXP-1894: Glycemic Variability Metrics', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig04-glycemic-metrics.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    high_tir = sum(1 for t in tirs if t >= 0.70)
    verdict = f"TIR≥70%:{high_tir}/11_CV_mean={np.mean(cvs):.2f}"
    print(f"\n  ✓ EXP-1894 verdict: {verdict}")
    return {
        'experiment': 'EXP-1894', 'title': 'Glycemic Variability Metrics',
        'verdict': verdict,
        'mean_tir': round(float(np.mean(tirs)), 3),
        'mean_cv': round(float(np.mean(cvs)), 3),
        'mean_ea1c': round(float(np.mean(ea1cs)), 2),
        'high_tir_count': high_tir,
        'per_patient': results,
    }


# ======================================================================
# EXP-1895: Improvement Potential
# ======================================================================

def exp_1895(patients, figures_dir):
    """Quantify how much better glycemic control COULD be with corrected settings.
    Use the S/D model to estimate improvement potential per patient."""
    print("\n" + "=" * 70)
    print("EXP-1895: Improvement Potential Estimation")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)

        # Profile loss
        loss_profile = supply_demand_loss(sd, glucose)

        # Optimal loss (grid search ISF scale)
        best_scale = 1.0
        best_loss = np.inf
        for scale in np.arange(0.1, 3.01, 0.05):
            sd_s = dict(sd)
            sd_s['net'] = sd.get('supply', np.zeros_like(glucose)) - sd.get('demand', np.zeros_like(glucose)) * scale
            loss = supply_demand_loss(sd_s, glucose)
            if np.isfinite(loss) and loss < best_loss:
                best_loss = loss
                best_scale = scale

        improvement_pct = (loss_profile - best_loss) / loss_profile * 100 if loss_profile > 0 else 0

        # Estimate "residual error" — what the model CANNOT explain
        net_opt = sd.get('supply', np.zeros_like(glucose)) - sd.get('demand', np.zeros_like(glucose)) * best_scale
        dg = np.diff(glucose, prepend=glucose[0])
        residual = dg - net_opt
        valid = np.isfinite(residual)
        residual_std = float(np.std(residual[valid])) if valid.sum() > 10 else np.nan

        # Current metrics
        metrics = glycemic_metrics(glucose)
        tir = metrics.get('tir', 0)
        cv = metrics.get('cv', 0)

        result = {
            'patient': name,
            'loss_profile': round(float(loss_profile), 2) if np.isfinite(loss_profile) else None,
            'loss_optimal': round(float(best_loss), 2),
            'improvement_pct': round(float(improvement_pct), 1),
            'optimal_scale': round(float(best_scale), 2),
            'residual_std': round(float(residual_std), 2) if np.isfinite(residual_std) else None,
            'current_tir': round(float(tir), 3),
            'current_cv': round(float(cv), 3),
        }
        results.append(result)
        print(f"  {name}: improvement={improvement_pct:+.1f}% scale={best_scale:.2f}"
              f" residual_std={residual_std:.1f} TIR={tir:.1%}")

    improvements = [r['improvement_pct'] for r in results if r['improvement_pct'] is not None]
    print(f"\n  Population improvement potential:")
    print(f"    Mean improvement: {np.mean(improvements):+.1f}%")
    print(f"    Max improvement: {np.max(improvements):+.1f}%")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # Improvement potential
        imps = [r['improvement_pct'] for r in results]
        colors = ['green' if i > 10 else 'orange' if i > 0 else 'red' for i in imps]
        axes[0].bar(x, imps, color=colors, alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Improvement (%)')
        axes[0].set_title('S/D Model Loss Improvement with Optimal ISF')
        axes[0].axhline(0, color='black', linewidth=0.5)

        # TIR vs improvement
        tirs = [r['current_tir'] * 100 for r in results]
        axes[1].scatter(tirs, imps, c='steelblue', s=80, alpha=0.7)
        for i, name in enumerate(names):
            axes[1].annotate(name, (tirs[i], imps[i]), fontsize=8, ha='center', va='bottom')
        axes[1].set_xlabel('Current TIR (%)')
        axes[1].set_ylabel('Improvement Potential (%)')
        axes[1].set_title('TIR vs Improvement Potential')

        plt.suptitle('EXP-1895: Improvement Potential', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig05-improvement-potential.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"MEAN_IMPROVEMENT_{np.mean(improvements):+.0f}%"
    print(f"\n  ✓ EXP-1895 verdict: {verdict}")
    return {
        'experiment': 'EXP-1895', 'title': 'Improvement Potential',
        'verdict': verdict,
        'mean_improvement': round(float(np.mean(improvements)), 1),
        'max_improvement': round(float(np.max(improvements)), 1),
        'per_patient': results,
    }


# ======================================================================
# EXP-1896: Parameter Evolution Over Time
# ======================================================================

def exp_1896(patients, figures_dir):
    """Track how optimal ISF scale changes over monthly windows.
    Assess parameter stability and drift."""
    print("\n" + "=" * 70)
    print("EXP-1896: Parameter Evolution Over Time")
    print("=" * 70)

    STEPS_PER_MONTH = 288 * 30  # ~30 days
    results = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        n = len(glucose)

        monthly_scales = []
        for start in range(0, n - STEPS_PER_MONTH // 2, STEPS_PER_MONTH):
            end = min(start + STEPS_PER_MONTH, n)
            df_month = df.iloc[start:end].copy()
            g_month = glucose[start:end]

            if len(g_month) < STEPS_PER_MONTH // 2:
                continue

            sd = compute_supply_demand(df_month)
            best_scale = 1.0
            best_loss = np.inf
            for scale in np.arange(0.1, 3.01, 0.1):
                sd_s = dict(sd)
                sd_s['net'] = sd.get('supply', np.zeros(len(g_month))) - sd.get('demand', np.zeros(len(g_month))) * scale
                loss = supply_demand_loss(sd_s, g_month)
                if np.isfinite(loss) and loss < best_loss:
                    best_loss = loss
                    best_scale = scale
            monthly_scales.append(best_scale)

        if len(monthly_scales) >= 2:
            drift = abs(monthly_scales[-1] - monthly_scales[0])
            cv_scale = np.std(monthly_scales) / np.mean(monthly_scales) if np.mean(monthly_scales) > 0 else 0
        else:
            drift = 0
            cv_scale = 0

        result = {
            'patient': name,
            'n_months': len(monthly_scales),
            'monthly_scales': [round(s, 2) for s in monthly_scales],
            'scale_cv': round(float(cv_scale), 3),
            'scale_drift': round(float(drift), 2),
            'scale_range': round(float(max(monthly_scales) - min(monthly_scales)), 2) if monthly_scales else 0,
        }
        results.append(result)
        scales_str = ', '.join(f'{s:.2f}' for s in monthly_scales[:6])
        print(f"  {name}: months={len(monthly_scales)} scales=[{scales_str}] CV={cv_scale:.3f} drift={drift:.2f}")

    mean_cv = np.mean([r['scale_cv'] for r in results])
    print(f"\n  Population parameter evolution:")
    print(f"    Mean scale CV: {mean_cv:.3f}")
    print(f"    Mean drift: {np.mean([r['scale_drift'] for r in results]):.2f}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Monthly scale trajectories
        for r in results:
            if r['n_months'] >= 2:
                axes[0].plot(range(r['n_months']), r['monthly_scales'],
                           marker='o', markersize=3, label=r['patient'], alpha=0.7)
        axes[0].set_xlabel('Month')
        axes[0].set_ylabel('Optimal ISF Scale')
        axes[0].set_title('ISF Scale Evolution Over Time')
        axes[0].legend(fontsize=7, ncol=2)

        # Scale CV per patient
        names = [r['patient'] for r in results]
        cvs = [r['scale_cv'] for r in results]
        x = np.arange(len(names))
        axes[1].bar(x, cvs, alpha=0.7, color='steelblue')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Scale CV')
        axes[1].set_title('ISF Scale Variability (CV)')
        axes[1].axhline(np.mean(cvs), color='red', linestyle='--', label=f'Mean={np.mean(cvs):.3f}')
        axes[1].legend()

        plt.suptitle('EXP-1896: Parameter Evolution Over Time', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig06-parameter-evolution.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    stable = sum(1 for r in results if r['scale_cv'] < 0.15)
    verdict = f"STABLE_{stable}_OF_{len(results)}_CV={mean_cv:.3f}"
    print(f"\n  ✓ EXP-1896 verdict: {verdict}")
    return {
        'experiment': 'EXP-1896', 'title': 'Parameter Evolution',
        'verdict': verdict,
        'mean_cv': round(float(mean_cv), 3),
        'stable_count': stable,
        'per_patient': results,
    }


# ======================================================================
# EXP-1897: AID System Fingerprinting
# ======================================================================

def exp_1897(patients, figures_dir):
    """Attempt to classify AID system type from insulin delivery patterns.
    Features: zero_fraction, correction_frequency, SMB_frequency, temp_rate_variance."""
    print("\n" + "=" * 70)
    print("EXP-1897: AID System Fingerprinting")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        n = len(df)

        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(n)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)

        # Features
        zero_frac = np.mean(temp_rate == 0)
        nonzero_rates = temp_rate[temp_rate > 0]
        rate_cv = float(np.std(nonzero_rates) / np.mean(nonzero_rates)) if len(nonzero_rates) > 10 and np.mean(nonzero_rates) > 0 else 0

        # Small boluses (< 0.5U) as SMB proxy
        small_bolus = np.sum((bolus > 0) & (bolus < 0.5))
        large_bolus = np.sum(bolus >= 0.5)
        smb_ratio = small_bolus / max(large_bolus, 1)

        # Rate change frequency (how often does temp_rate change?)
        rate_changes = np.sum(np.abs(np.diff(temp_rate)) > 0.01)
        rate_change_freq = rate_changes / n

        # Max temp rate
        max_rate = float(np.max(temp_rate)) if len(temp_rate) > 0 else 0
        median_rate = float(np.median(temp_rate))

        # Classification heuristic
        if smb_ratio > 2:
            system_guess = 'oref1/AAPS'  # Heavy SMB usage
        elif zero_frac > 0.6 and rate_change_freq > 0.3:
            system_guess = 'Loop'  # Frequent suspend/resume
        elif zero_frac > 0.8:
            system_guess = 'MDI/Open'  # Mostly no delivery data
        else:
            system_guess = 'Loop-like'  # Moderate adjustment

        result = {
            'patient': name,
            'zero_fraction': round(float(zero_frac), 3),
            'rate_cv': round(float(rate_cv), 3),
            'smb_ratio': round(float(smb_ratio), 2),
            'rate_change_freq': round(float(rate_change_freq), 3),
            'max_rate': round(float(max_rate), 2),
            'median_rate': round(float(median_rate), 3),
            'system_guess': system_guess,
        }
        results.append(result)
        print(f"  {name}: zero={zero_frac:.1%} rate_cv={rate_cv:.2f} smb_ratio={smb_ratio:.1f}"
              f" change_freq={rate_change_freq:.3f} → {system_guess}")

    # Count system types
    systems = {}
    for r in results:
        g = r['system_guess']
        systems[g] = systems.get(g, 0) + 1

    print(f"\n  System fingerprinting:")
    for sys, count in sorted(systems.items()):
        print(f"    {sys}: {count}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        names = [r['patient'] for r in results]
        x = np.arange(len(names))

        # Feature comparison
        axes[0].bar(x - 0.2, [r['zero_fraction'] for r in results], 0.2, label='Zero %', alpha=0.7)
        axes[0].bar(x, [r['rate_change_freq'] for r in results], 0.2, label='Change Freq', alpha=0.7)
        axes[0].bar(x + 0.2, [min(r['smb_ratio'] / 10, 1) for r in results], 0.2, label='SMB Ratio/10', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_title('AID Delivery Pattern Features')
        axes[0].legend(fontsize=8)

        # System classification
        system_colors = {'Loop': 'blue', 'Loop-like': 'steelblue', 'oref1/AAPS': 'green', 'MDI/Open': 'gray'}
        colors = [system_colors.get(r['system_guess'], 'gray') for r in results]
        axes[1].scatter([r['zero_fraction'] for r in results],
                       [r['rate_change_freq'] for r in results],
                       c=colors, s=100, alpha=0.7)
        for i, r in enumerate(results):
            axes[1].annotate(r['patient'], (r['zero_fraction'], r['rate_change_freq']),
                           fontsize=8, ha='center', va='bottom')
        axes[1].set_xlabel('Zero Delivery Fraction')
        axes[1].set_ylabel('Rate Change Frequency')
        axes[1].set_title('AID System Fingerprint Space')

        plt.suptitle('EXP-1897: AID System Fingerprinting', fontsize=14)
        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig07-aid-fingerprinting.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"SYSTEMS:{systems}"
    print(f"\n  ✓ EXP-1897 verdict: {verdict}")
    return {
        'experiment': 'EXP-1897', 'title': 'AID System Fingerprinting',
        'verdict': str(verdict),
        'system_counts': systems,
        'per_patient': results,
    }


# ======================================================================
# EXP-1898: Therapy Report Card
# ======================================================================

def exp_1898(patients, figures_dir):
    """Generate a unified per-patient therapy report card combining all signals.
    This is the production-ready summary of all findings."""
    print("\n" + "=" * 70)
    print("EXP-1898: Therapy Report Card")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        isf_profile = get_isf(p)
        cr_profile = get_cr(p)
        basal_profile = get_basal(p)

        # Glycemic metrics
        metrics = glycemic_metrics(glucose)

        # Optimal ISF via S/D model
        sd = compute_supply_demand(df)
        best_scale = 1.0
        best_loss = np.inf
        for scale in np.arange(0.1, 3.01, 0.05):
            sd_s = dict(sd)
            sd_s['net'] = sd.get('supply', np.zeros_like(glucose)) - sd.get('demand', np.zeros_like(glucose)) * scale
            loss = supply_demand_loss(sd_s, glucose)
            if np.isfinite(loss) and loss < best_loss:
                best_loss = loss
                best_scale = scale
        optimal_isf = isf_profile * best_scale

        # Equation-based CR
        meals = find_meals(df)
        cr_estimates = []
        for m in meals:
            if m['bolus'] > 0.1 and np.isfinite(m['excursion']) and m['carbs'] > 0:
                denom = m['excursion'] + m['bolus'] * optimal_isf
                if denom > 0:
                    cr_est = m['carbs'] * optimal_isf / denom
                    if 0.5 < cr_est < 50:
                        cr_estimates.append(cr_est)
        optimal_cr = float(np.median(cr_estimates)) if cr_estimates else cr_profile

        # Overnight drift for basal
        drifts = overnight_drift(df)
        mean_drift = float(np.nanmean(drifts)) if drifts else 0.0

        # Scoring
        isf_score = 'GOOD' if abs(best_scale - 1.0) < 0.2 else ('MODERATE' if abs(best_scale - 1.0) < 0.4 else 'POOR')
        cr_score = 'GOOD' if abs(optimal_cr - cr_profile) / max(cr_profile, 1) < 0.15 else ('MODERATE' if abs(optimal_cr - cr_profile) / max(cr_profile, 1) < 0.30 else 'POOR')
        basal_score = 'GOOD' if abs(mean_drift) < 2 else ('MODERATE' if abs(mean_drift) < 5 else 'POOR')
        tir_score = 'GOOD' if metrics.get('tir', 0) >= 0.70 else ('MODERATE' if metrics.get('tir', 0) >= 0.50 else 'POOR')

        scores = [isf_score, cr_score, basal_score, tir_score]
        n_good = scores.count('GOOD')
        n_poor = scores.count('POOR')
        overall = 'EXCELLENT' if n_good >= 3 and n_poor == 0 else ('ADEQUATE' if n_poor <= 1 else 'NEEDS_ATTENTION')

        result = {
            'patient': name,
            'tir': metrics.get('tir', 0),
            'ea1c': metrics.get('ea1c', 0),
            'cv': metrics.get('cv', 0),
            'lbgi': metrics.get('lbgi', 0),
            'hbgi': metrics.get('hbgi', 0),
            'isf_profile': isf_profile,
            'isf_optimal': round(optimal_isf, 1),
            'isf_scale': round(best_scale, 2),
            'isf_score': isf_score,
            'cr_profile': cr_profile,
            'cr_optimal': round(optimal_cr, 1),
            'cr_score': cr_score,
            'basal_profile': basal_profile,
            'overnight_drift': round(mean_drift, 2),
            'basal_score': basal_score,
            'tir_score': tir_score,
            'overall': overall,
            'n_meals': len(cr_estimates),
        }
        results.append(result)
        print(f"  {name}: overall={overall} ISF={isf_score}({best_scale:.2f}×)"
              f" CR={cr_score}({optimal_cr:.1f}) Basal={basal_score}(drift={mean_drift:+.1f})"
              f" TIR={tir_score}({metrics.get('tir',0):.1%})")

    # Population summary
    overalls = [r['overall'] for r in results]
    print(f"\n  Population report card:")
    print(f"    EXCELLENT: {overalls.count('EXCELLENT')}")
    print(f"    ADEQUATE: {overalls.count('ADEQUATE')}")
    print(f"    NEEDS_ATTENTION: {overalls.count('NEEDS_ATTENTION')}")

    # Figure
    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(14, 7))
        names = [r['patient'] for r in results]
        n_patients = len(names)

        # Create a heatmap-style report card
        categories = ['ISF', 'CR', 'Basal', 'TIR', 'Overall']
        score_map = {'GOOD': 3, 'EXCELLENT': 3, 'MODERATE': 2, 'ADEQUATE': 2, 'POOR': 1, 'NEEDS_ATTENTION': 1}
        color_map = {3: '#2ecc71', 2: '#f39c12', 1: '#e74c3c'}

        for i, r in enumerate(results):
            scores_vals = [
                score_map.get(r['isf_score'], 0),
                score_map.get(r['cr_score'], 0),
                score_map.get(r['basal_score'], 0),
                score_map.get(r['tir_score'], 0),
                score_map.get(r['overall'], 0),
            ]
            labels = [
                f"{r['isf_score']}\n({r['isf_scale']}×)",
                f"{r['cr_score']}\n({r['cr_optimal']:.0f})",
                f"{r['basal_score']}\n({r['overnight_drift']:+.1f})",
                f"{r['tir_score']}\n({r['tir']:.0%})",
                f"{r['overall']}",
            ]
            for j, (val, label) in enumerate(zip(scores_vals, labels)):
                rect = plt.Rectangle((i - 0.4, j - 0.4), 0.8, 0.8,
                                    facecolor=color_map.get(val, 'gray'), alpha=0.6)
                ax.add_patch(rect)
                ax.text(i, j, label, ha='center', va='center', fontsize=7, fontweight='bold')

        ax.set_xlim(-0.5, n_patients - 0.5)
        ax.set_ylim(-0.5, len(categories) - 0.5)
        ax.set_xticks(range(n_patients))
        ax.set_xticklabels(names, fontsize=10)
        ax.set_yticks(range(len(categories)))
        ax.set_yticklabels(categories, fontsize=10)
        ax.set_title('EXP-1898: Therapy Report Card', fontsize=14)

        plt.tight_layout()
        fig_path = figures_dir / 'integrated-fig08-report-card.png'
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {fig_path.name}")

    verdict = f"EXCELLENT:{overalls.count('EXCELLENT')}_ADEQUATE:{overalls.count('ADEQUATE')}_ATTENTION:{overalls.count('NEEDS_ATTENTION')}"
    print(f"\n  ✓ EXP-1898 verdict: {verdict}")
    return {
        'experiment': 'EXP-1898', 'title': 'Therapy Report Card',
        'verdict': verdict,
        'excellent': overalls.count('EXCELLENT'),
        'adequate': overalls.count('ADEQUATE'),
        'needs_attention': overalls.count('NEEDS_ATTENTION'),
        'per_patient': results,
    }


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1891–1898: Integrated Therapy Assessment')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--experiment', type=int, help='Run single experiment (1891–1898)')
    args = parser.parse_args()

    figures_dir = FIGURES_DIR if args.figures else None
    if figures_dir:
        figures_dir.mkdir(parents=True, exist_ok=True)

    # Load patients
    patients = load_patients('externals/ns-data/patients/')
    print(f"Loaded {len(patients)} patients")

    experiments = {
        1891: exp_1891,
        1892: exp_1892,
        1893: exp_1893,
        1894: exp_1894,
        1895: exp_1895,
        1896: exp_1896,
        1897: exp_1897,
        1898: exp_1898,
    }

    if args.experiment:
        to_run = {args.experiment: experiments[args.experiment]}
    else:
        to_run = experiments

    all_results = {}
    print(f"\n{'=' * 70}")
    print(f"EXP-1891–1898: Integrated Therapy Assessment")
    print(f"{'=' * 70}")

    for exp_id, exp_fn in sorted(to_run.items()):
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{exp_id}: {exp_fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'#' * 70}")
        result = exp_fn(patients, figures_dir)
        all_results[f'EXP-{exp_id}'] = result

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {RESULTS_PATH}")

    # Synthesis
    print(f"\n{'=' * 70}")
    print(f"SYNTHESIS: Integrated Therapy Assessment")
    print(f"{'=' * 70}")
    for k in sorted(all_results.keys()):
        v = all_results[k]
        print(f"  {k}: {v.get('verdict', '?')}")
    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
