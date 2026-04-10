#!/usr/bin/env python3
"""
EXP-1861–1868: Dose-Dependent ISF & Therapy Assessment

Following EXP-1856's breakthrough: ISF is dose-dependent (10/10 patients,
slope = -0.89). This batch formalizes the Hill-equation ISF(dose) model
and tests whether dose-aware ISF improves therapy parameter estimation.

Key questions:
  1. Does Hill-equation ISF(dose) fit better than linear ISF? (1861)
  2. Is the dose-response consistent across time? (1862)
  3. Can dose-ISF + combined split-loss improve therapy estimation? (1863)
  4. Does dose-ISF explain the ISF "variability" (CV=0.84-1.84)? (1864)
  5. Does dose-ISF justify SMB dosing strategy? (1865)
  6. Can we estimate effective CR from dose-adjusted supply loss? (1866)
  7. Does dose-ISF improve the supply/demand model fit? (1867)
  8. Temporal validation: train dose-ISF on half 1, eval half 2? (1868)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_dose_isf_1861.py [--figures]
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


def find_corrections(df, min_dose=0.5, carb_window=12, post_window=36):
    """Find isolated correction events (bolus without carbs).

    Returns list of dicts with: idx, dose, g_pre, g_nadir, drop, isf_observed
    """
    glucose = df['glucose'].values
    bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
    carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values

    corrections = []
    for i in range(carb_window, len(glucose) - post_window):
        if bolus[i] < min_dose:
            continue
        # No carbs within ±1h
        if np.any(carbs[max(0, i - carb_window):i + carb_window] > 1):
            continue
        g_pre = glucose[i]
        g_window = glucose[i:i + post_window]
        if np.all(np.isnan(g_window)):
            continue
        g_nadir = np.nanmin(g_window)
        if np.isnan(g_pre) or np.isnan(g_nadir):
            continue
        drop = g_pre - g_nadir
        if drop <= 0:
            continue
        corrections.append({
            'idx': i,
            'dose': bolus[i],
            'g_pre': g_pre,
            'g_nadir': g_nadir,
            'drop': drop,
            'isf_observed': drop / bolus[i],
        })
    return corrections


def hill_equation(dose, isf_max, kd, n=1):
    """Hill equation: ISF(dose) = ISF_max × Kd^n / (Kd^n + dose^n)"""
    return isf_max * kd**n / (kd**n + dose**n)


def fit_hill(doses, isfs, n_fixed=1):
    """Fit Hill equation parameters ISF_max and Kd (fixed n=1 for simplicity).

    Uses grid search since the function is simple and we want robustness.
    """
    best_loss = np.inf
    best_params = (100, 1.0)

    for isf_max in np.arange(20, 500, 10):
        for kd in np.arange(0.2, 10, 0.2):
            pred = hill_equation(doses, isf_max, kd, n_fixed)
            loss = np.mean((isfs - pred) ** 2)
            if loss < best_loss:
                best_loss = loss
                best_params = (isf_max, kd)

    isf_max, kd = best_params
    pred = hill_equation(doses, isf_max, kd, n_fixed)
    ss_res = np.sum((isfs - pred) ** 2)
    ss_tot = np.sum((isfs - isfs.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {'isf_max': isf_max, 'kd': kd, 'n': n_fixed, 'r2': r2, 'rmse': np.sqrt(best_loss)}


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
# EXP-1861: Hill Equation vs Linear ISF
# ===========================================================================

def exp_1861(patients, figures_dir):
    """Fit Hill-equation ISF(dose) vs linear (constant) ISF for each patient.
    Compare R² and residual variance.
    """
    print("=" * 70)
    print("EXP-1861: Hill Equation ISF(dose) vs Linear ISF")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        corrections = find_corrections(df)

        if len(corrections) < 10:
            print(f"  {name}: insufficient corrections ({len(corrections)})")
            continue

        doses = np.array([c['dose'] for c in corrections])
        isfs = np.array([c['isf_observed'] for c in corrections])

        # Filter outliers (ISF > 500 or < 1)
        valid = (isfs > 1) & (isfs < 500) & (doses > 0)
        doses = doses[valid]
        isfs = isfs[valid]

        if len(doses) < 10:
            continue

        # Linear model: ISF = constant (mean)
        linear_pred = np.full_like(isfs, isfs.mean())
        ss_tot = np.sum((isfs - isfs.mean()) ** 2)
        r2_linear = 0.0  # by definition

        # Hill equation fit
        hill_params = fit_hill(doses, isfs)
        hill_pred = hill_equation(doses, hill_params['isf_max'], hill_params['kd'])
        ss_res_hill = np.sum((isfs - hill_pred) ** 2)
        r2_hill = hill_params['r2']

        # Log-linear fit for comparison
        from numpy.linalg import lstsq
        log_d = np.log(doses)
        log_i = np.log(isfs)
        X = np.column_stack([np.ones_like(log_d), log_d])
        coeffs, _, _, _ = lstsq(X, log_i, rcond=None)
        log_pred = X @ coeffs
        ss_res_log = np.sum((log_i - log_pred) ** 2)
        ss_tot_log = np.sum((log_i - log_i.mean()) ** 2)
        r2_loglog = 1 - ss_res_log / ss_tot_log if ss_tot_log > 0 else 0

        # Residual CV after accounting for dose
        resid_hill = isfs - hill_pred
        cv_raw = np.std(isfs) / np.mean(isfs)
        cv_after_hill = np.std(resid_hill) / np.mean(isfs) if np.mean(isfs) > 0 else 0
        cv_reduction = 1 - cv_after_hill / cv_raw if cv_raw > 0 else 0

        print(f"  {name}: n={len(doses)} R²_hill={r2_hill:.3f} R²_loglog={r2_loglog:.3f} "
              f"ISF_max={hill_params['isf_max']:.0f} Kd={hill_params['kd']:.1f} "
              f"CV: {cv_raw:.2f}→{cv_after_hill:.2f} ({cv_reduction:.0%} reduction)")

        results.append({
            'patient': name,
            'n_corrections': len(doses),
            'r2_linear': round(r2_linear, 3),
            'r2_hill': round(r2_hill, 3),
            'r2_loglog': round(r2_loglog, 3),
            'isf_max': round(hill_params['isf_max'], 1),
            'kd': round(hill_params['kd'], 2),
            'isf_profile': get_isf(p),
            'cv_raw': round(cv_raw, 3),
            'cv_after_hill': round(cv_after_hill, 3),
            'cv_reduction': round(cv_reduction, 3),
            'slope_loglog': round(coeffs[1], 3),
            'dose_range': [round(float(doses.min()), 1), round(float(doses.max()), 1)],
        })

    valid = [r for r in results]
    mean_r2_hill = np.mean([r['r2_hill'] for r in valid])
    mean_cv_reduction = np.mean([r['cv_reduction'] for r in valid])

    print(f"\n  Population Hill-equation ISF(dose):")
    print(f"    Mean R² (Hill): {mean_r2_hill:.3f}")
    print(f"    Mean R² (log-log): {np.mean([r['r2_loglog'] for r in valid]):.3f}")
    print(f"    Mean CV reduction: {mean_cv_reduction:.1%}")
    print(f"    Mean ISF_max: {np.mean([r['isf_max'] for r in valid]):.0f} mg/dL/U")
    print(f"    Mean Kd: {np.mean([r['kd'] for r in valid]):.1f} U")

    if mean_r2_hill > 0.15:
        verdict = 'HILL_EQUATION_FITS'
    elif mean_r2_hill > 0.05:
        verdict = 'WEAK_HILL_FIT'
    else:
        verdict = 'LINEAR_SUFFICIENT'

    print(f"\n  ✓ EXP-1861 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        n_patients = len(valid)
        cols = min(4, n_patients)
        rows = (n_patients + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows), squeeze=False)

        for idx, r in enumerate(valid):
            ax = axes[idx // cols][idx % cols]
            # Re-extract corrections for plotting
            p = [p for p in patients if p['name'] == r['patient']][0]
            corrections = find_corrections(p['df'].copy())
            doses_p = np.array([c['dose'] for c in corrections])
            isfs_p = np.array([c['isf_observed'] for c in corrections])
            vm = (isfs_p > 1) & (isfs_p < 500) & (doses_p > 0)
            doses_p, isfs_p = doses_p[vm], isfs_p[vm]

            ax.scatter(doses_p, isfs_p, alpha=0.3, s=10, color='#2196F3')

            # Hill curve
            d_range = np.linspace(0.3, max(doses_p.max(), 8), 100)
            hill_curve = hill_equation(d_range, r['isf_max'], r['kd'])
            ax.plot(d_range, hill_curve, 'r-', linewidth=2,
                    label=f"Hill: max={r['isf_max']:.0f}, Kd={r['kd']:.1f}")

            # Profile ISF
            ax.axhline(r['isf_profile'], color='gray', linestyle='--', alpha=0.5,
                       label=f"Profile: {r['isf_profile']:.0f}")

            ax.set_xlabel('Dose (U)')
            ax.set_ylabel('ISF (mg/dL/U)')
            ax.set_title(f"{r['patient']}: R²={r['r2_hill']:.2f}")
            ax.legend(fontsize=7)
            ax.set_ylim(0, min(isfs_p.max() * 1.2, 400))

        # Hide empty axes
        for idx in range(n_patients, rows * cols):
            axes[idx // cols][idx % cols].set_visible(False)

        plt.suptitle('EXP-1861: Hill-Equation ISF(dose) per Patient', fontsize=14)
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig01-hill-fits.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig01-hill-fits.png")

    return {
        'experiment': 'EXP-1861',
        'title': 'Hill Equation ISF(dose) vs Linear ISF',
        'verdict': verdict,
        'mean_r2_hill': round(mean_r2_hill, 3),
        'mean_cv_reduction': round(mean_cv_reduction, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1862: Temporal Stability of Dose-Response
# ===========================================================================

def exp_1862(patients, figures_dir):
    """Test whether the Hill-equation parameters are stable over time
    (first half vs second half of data).
    """
    print("=" * 70)
    print("EXP-1862: Temporal Stability of ISF Dose-Response")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        mid = len(df) // 2

        df_h1 = df.iloc[:mid]
        df_h2 = df.iloc[mid:]

        corr_h1 = find_corrections(df_h1)
        corr_h2 = find_corrections(df_h2)

        if len(corr_h1) < 10 or len(corr_h2) < 10:
            print(f"  {name}: insufficient corrections (h1={len(corr_h1)}, h2={len(corr_h2)})")
            continue

        for label, corrs in [('h1', corr_h1), ('h2', corr_h2)]:
            doses = np.array([c['dose'] for c in corrs])
            isfs = np.array([c['isf_observed'] for c in corrs])
            valid = (isfs > 1) & (isfs < 500) & (doses > 0)
            if label == 'h1':
                d1, i1 = doses[valid], isfs[valid]
            else:
                d2, i2 = doses[valid], isfs[valid]

        if len(d1) < 10 or len(d2) < 10:
            continue

        hill_h1 = fit_hill(d1, i1)
        hill_h2 = fit_hill(d2, i2)

        # Stability metrics
        isf_max_change = abs(hill_h1['isf_max'] - hill_h2['isf_max']) / hill_h1['isf_max']
        kd_change = abs(hill_h1['kd'] - hill_h2['kd']) / max(hill_h1['kd'], 0.1)

        # Cross-prediction: train on h1, predict h2
        pred_h2 = hill_equation(d2, hill_h1['isf_max'], hill_h1['kd'])
        ss_res = np.sum((i2 - pred_h2) ** 2)
        ss_tot = np.sum((i2 - i2.mean()) ** 2)
        r2_cross = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        print(f"  {name}: h1(max={hill_h1['isf_max']:.0f},Kd={hill_h1['kd']:.1f}) "
              f"h2(max={hill_h2['isf_max']:.0f},Kd={hill_h2['kd']:.1f}) "
              f"Δmax={isf_max_change:.2f} ΔKd={kd_change:.2f} R²_cross={r2_cross:.3f}")

        results.append({
            'patient': name,
            'hill_h1': {'isf_max': hill_h1['isf_max'], 'kd': hill_h1['kd'], 'r2': hill_h1['r2']},
            'hill_h2': {'isf_max': hill_h2['isf_max'], 'kd': hill_h2['kd'], 'r2': hill_h2['r2']},
            'isf_max_change': round(isf_max_change, 3),
            'kd_change': round(kd_change, 3),
            'r2_cross': round(r2_cross, 3),
            'n_h1': len(d1),
            'n_h2': len(d2),
        })

    valid = [r for r in results]
    mean_max_change = np.mean([r['isf_max_change'] for r in valid]) if valid else 0
    mean_r2_cross = np.mean([r['r2_cross'] for r in valid]) if valid else 0
    n_stable = sum(1 for r in valid if r['isf_max_change'] < 0.3)

    print(f"\n  Population temporal stability:")
    print(f"    Mean ISF_max change: {mean_max_change:.2%}")
    print(f"    Mean cross-prediction R²: {mean_r2_cross:.3f}")
    print(f"    Stable patients (Δmax < 30%): {n_stable}/{len(valid)}")

    if n_stable >= len(valid) * 0.7:
        verdict = 'TEMPORALLY_STABLE'
    elif n_stable >= len(valid) * 0.5:
        verdict = 'MOSTLY_STABLE'
    else:
        verdict = 'UNSTABLE'

    print(f"\n  ✓ EXP-1862 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        names = [r['patient'] for r in valid]

        ax = axes[0]
        h1_max = [r['hill_h1']['isf_max'] for r in valid]
        h2_max = [r['hill_h2']['isf_max'] for r in valid]
        ax.scatter(h1_max, h2_max, s=80, edgecolors='k')
        for i, r in enumerate(valid):
            ax.annotate(r['patient'], (h1_max[i], h2_max[i]), fontsize=8)
        lim = max(max(h1_max), max(h2_max)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('ISF_max (First Half)')
        ax.set_ylabel('ISF_max (Second Half)')
        ax.set_title('EXP-1862: ISF_max Temporal Stability')

        ax = axes[1]
        r2s = [r['r2_cross'] for r in valid]
        colors = ['#4CAF50' if r > 0 else '#F44336' for r in r2s]
        ax.bar(names, r2s, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Cross-Prediction R²')
        ax.set_title('EXP-1862: Train Half1 → Predict Half2')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig02-temporal-stability.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig02-temporal-stability.png")

    return {
        'experiment': 'EXP-1862',
        'title': 'Temporal Stability of ISF Dose-Response',
        'verdict': verdict,
        'mean_isf_max_change': round(mean_max_change, 3),
        'mean_r2_cross': round(mean_r2_cross, 3),
        'n_stable': n_stable,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1863: Dose-ISF + Combined Split-Loss Therapy Assessment
# ===========================================================================

def exp_1863(patients, figures_dir):
    """Use Hill-equation ISF(dose) with combined split-loss (EXP-1848 approach)
    to assess therapy parameters. Does dose-aware ISF improve the combined
    estimator?
    """
    print("=" * 70)
    print("EXP-1863: Dose-ISF + Combined Split-Loss Therapy Assessment")
    print("=" * 70)

    results = []
    scales = np.array([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 2.5, 3.0])

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_base = get_isf(p)

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        # Baseline loss
        sd_base = compute_supply_demand(df)
        sl_base, dl_base, tl_base = supply_demand_loss(sd_base, glucose)
        if np.isnan(tl_base):
            continue

        # Standard combined optimization (constant ISF scale)
        best_const_scale = 1.0
        best_const_loss = tl_base
        for s in scales:
            df_s = df.copy()
            df_s.attrs = dict(df.attrs)
            isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_base}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = isf_base * s
            df_s.attrs['isf_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            sl, dl, tl = supply_demand_loss(sd_s, glucose)
            if not np.isnan(tl) and tl < best_const_loss:
                best_const_loss = tl
                best_const_scale = s

        # Fit Hill equation for this patient
        corrections = find_corrections(df)
        if len(corrections) >= 10:
            doses_c = np.array([c['dose'] for c in corrections])
            isfs_c = np.array([c['isf_observed'] for c in corrections])
            vm = (isfs_c > 1) & (isfs_c < 500) & (doses_c > 0)
            if vm.sum() >= 10:
                hill = fit_hill(doses_c[vm], isfs_c[vm])
                has_hill = True
            else:
                has_hill = False
        else:
            has_hill = False

        if has_hill:
            # Dose-aware ISF: effective ISF at median dose
            bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
            typical_dose = np.median(bolus[bolus > 0.5]) if (bolus > 0.5).sum() > 0 else 2.0
            hill_isf_typical = hill_equation(typical_dose, hill['isf_max'], hill['kd'])
            hill_scale = hill_isf_typical / isf_base if isf_base > 0 else 1.0

            # Apply Hill-derived ISF
            df_hill = df.copy()
            df_hill.attrs = dict(df.attrs)
            isf_sched = df_hill.attrs.get('isf_schedule', [{'value': isf_base}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = hill_isf_typical
            df_hill.attrs['isf_schedule'] = new_sched
            sd_hill = compute_supply_demand(df_hill)
            sl_hill, dl_hill, tl_hill = supply_demand_loss(sd_hill, glucose)
        else:
            hill_isf_typical = isf_base
            hill_scale = 1.0
            tl_hill = tl_base
            hill = {'isf_max': isf_base, 'kd': 1.0, 'r2': 0}

        const_improvement = (tl_base - best_const_loss) / tl_base * 100 if tl_base > 0 else 0
        hill_improvement = (tl_base - tl_hill) / tl_base * 100 if tl_base > 0 and not np.isnan(tl_hill) else 0

        print(f"  {name}: profile_ISF={isf_base:.0f} hill_ISF={hill_isf_typical:.0f} "
              f"const_opt={best_const_scale:.2f}× hill_scale={hill_scale:.2f}× "
              f"const_Δ={const_improvement:+.1f}% hill_Δ={hill_improvement:+.1f}%")

        results.append({
            'patient': name,
            'isf_profile': isf_base,
            'hill_isf_typical': round(hill_isf_typical, 1),
            'hill_scale': round(hill_scale, 2),
            'hill_params': {'isf_max': hill['isf_max'], 'kd': hill['kd'], 'r2': hill['r2']},
            'const_optimal_scale': best_const_scale,
            'baseline_loss': round(float(tl_base), 2),
            'const_loss': round(float(best_const_loss), 2),
            'hill_loss': round(float(tl_hill), 2) if not np.isnan(tl_hill) else None,
            'const_improvement_pct': round(const_improvement, 1),
            'hill_improvement_pct': round(hill_improvement, 1),
            'has_hill': has_hill,
        })

    valid = [r for r in results]
    hill_patients = [r for r in valid if r['has_hill']]
    mean_const_imp = np.mean([r['const_improvement_pct'] for r in valid])
    mean_hill_imp = np.mean([r['hill_improvement_pct'] for r in hill_patients]) if hill_patients else 0
    n_hill_better = sum(1 for r in hill_patients
                        if r['hill_improvement_pct'] > r['const_improvement_pct'])

    print(f"\n  Population therapy assessment:")
    print(f"    Mean constant-ISF improvement: {mean_const_imp:.1f}%")
    print(f"    Mean Hill-ISF improvement: {mean_hill_imp:.1f}%")
    print(f"    Hill beats constant: {n_hill_better}/{len(hill_patients)}")

    if n_hill_better > len(hill_patients) * 0.6:
        verdict = 'HILL_IMPROVES_THERAPY'
    elif mean_hill_imp > mean_const_imp:
        verdict = 'HILL_MARGINALLY_BETTER'
    else:
        verdict = 'CONSTANT_ISF_SUFFICIENT'

    print(f"\n  ✓ EXP-1863 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        names = [r['patient'] for r in valid]
        const_imps = [r['const_improvement_pct'] for r in valid]
        hill_imps = [r['hill_improvement_pct'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, const_imps, 0.4, label='Constant ISF', color='#9E9E9E')
        ax.bar(x + 0.2, hill_imps, 0.4, label='Hill ISF(dose)', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Loss Improvement (%)')
        ax.set_title(f'EXP-1863: Constant vs Hill-Equation ISF')
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig03-therapy-assessment.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig03-therapy-assessment.png")

    return {
        'experiment': 'EXP-1863',
        'title': 'Dose-ISF + Combined Split-Loss Therapy Assessment',
        'verdict': verdict,
        'mean_const_improvement': round(mean_const_imp, 1),
        'mean_hill_improvement': round(mean_hill_imp, 1),
        'n_hill_better': n_hill_better,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1864: Does Dose-ISF Explain Variability?
# ===========================================================================

def exp_1864(patients, figures_dir):
    """Test whether conditioning on dose explains the ISF CV of 0.84–1.84.
    Partition ISF variance into dose-explained vs residual.
    """
    print("=" * 70)
    print("EXP-1864: Dose-ISF Explains ISF Variability")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        corrections = find_corrections(df)

        if len(corrections) < 20:
            print(f"  {name}: insufficient corrections ({len(corrections)})")
            continue

        doses = np.array([c['dose'] for c in corrections])
        isfs = np.array([c['isf_observed'] for c in corrections])
        valid = (isfs > 1) & (isfs < 500) & (doses > 0)
        doses, isfs = doses[valid], isfs[valid]

        if len(doses) < 20:
            continue

        # Raw ISF stats
        cv_raw = np.std(isfs) / np.mean(isfs)
        iqr_raw = np.percentile(isfs, 75) - np.percentile(isfs, 25)

        # Hill fit
        hill = fit_hill(doses, isfs)
        hill_pred = hill_equation(doses, hill['isf_max'], hill['kd'])
        residual = isfs - hill_pred

        cv_residual = np.std(residual) / np.mean(isfs) if np.mean(isfs) > 0 else 0
        variance_explained = 1 - np.var(residual) / np.var(isfs) if np.var(isfs) > 0 else 0

        # Dose-bin analysis
        bins = [(0, 1.5), (1.5, 3), (3, 6), (6, 100)]
        bin_cvs = {}
        for lo, hi in bins:
            mask = (doses >= lo) & (doses < hi)
            if mask.sum() >= 5:
                bin_isfs = isfs[mask]
                bin_cvs[f'{lo}-{hi}U'] = round(np.std(bin_isfs) / np.mean(bin_isfs), 2)

        print(f"  {name}: n={len(doses)} CV_raw={cv_raw:.2f} CV_residual={cv_residual:.2f} "
              f"variance_explained={variance_explained:.1%} bin_CVs={bin_cvs}")

        results.append({
            'patient': name,
            'n_corrections': len(doses),
            'cv_raw': round(cv_raw, 3),
            'cv_residual': round(cv_residual, 3),
            'variance_explained_by_dose': round(variance_explained, 3),
            'hill_r2': round(hill['r2'], 3),
            'bin_cvs': bin_cvs,
        })

    valid = [r for r in results]
    mean_cv_raw = np.mean([r['cv_raw'] for r in valid])
    mean_cv_resid = np.mean([r['cv_residual'] for r in valid])
    mean_var_expl = np.mean([r['variance_explained_by_dose'] for r in valid])

    print(f"\n  Population ISF variability decomposition:")
    print(f"    Mean raw CV: {mean_cv_raw:.2f}")
    print(f"    Mean residual CV (after dose): {mean_cv_resid:.2f}")
    print(f"    Mean variance explained by dose: {mean_var_expl:.1%}")

    if mean_var_expl > 0.3:
        verdict = 'DOSE_EXPLAINS_VARIABILITY'
    elif mean_var_expl > 0.1:
        verdict = 'DOSE_PARTIAL_EXPLANATION'
    else:
        verdict = 'DOSE_INSUFFICIENT'

    print(f"\n  ✓ EXP-1864 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        raw = [r['cv_raw'] for r in valid]
        resid = [r['cv_residual'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, raw, 0.4, label='Raw ISF CV', color='#F44336')
        ax.bar(x + 0.2, resid, 0.4, label='After dose adjustment', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Coefficient of Variation')
        ax.set_title('EXP-1864: ISF Variability Before/After Dose')
        ax.legend()

        ax = axes[1]
        var_expl = [r['variance_explained_by_dose'] * 100 for r in valid]
        ax.bar(names, var_expl, color='#2196F3')
        ax.axhline(30, color='r', linestyle='--', alpha=0.3, label='30% threshold')
        ax.set_ylabel('Variance Explained by Dose (%)')
        ax.set_title('EXP-1864: How Much ISF Variance Is Dose?')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig04-variability.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig04-variability.png")

    return {
        'experiment': 'EXP-1864',
        'title': 'Dose-ISF Explains ISF Variability',
        'verdict': verdict,
        'mean_cv_raw': round(mean_cv_raw, 3),
        'mean_cv_residual': round(mean_cv_resid, 3),
        'mean_variance_explained': round(mean_var_expl, 3),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1865: SMB Efficiency — Data-Driven Justification
# ===========================================================================

def exp_1865(patients, figures_dir):
    """Test whether Super Micro Boluses (SMBs, < 1U) are genuinely more
    efficient per unit than larger boluses. Compare ISF at different dose
    tiers and compute the efficiency ratio.
    """
    print("=" * 70)
    print("EXP-1865: SMB Efficiency — Data-Driven Justification")
    print("=" * 70)

    results = []
    # Dose tiers aligned with clinical practice
    tiers = [
        ('micro', 0, 0.5),
        ('smb', 0.5, 1.5),
        ('small', 1.5, 3.0),
        ('medium', 3.0, 6.0),
        ('large', 6.0, 100),
    ]

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        corrections = find_corrections(df, min_dose=0.3)

        if len(corrections) < 20:
            print(f"  {name}: insufficient corrections ({len(corrections)})")
            continue

        doses = np.array([c['dose'] for c in corrections])
        isfs = np.array([c['isf_observed'] for c in corrections])
        drops = np.array([c['drop'] for c in corrections])
        valid = (isfs > 1) & (isfs < 500) & (doses > 0)
        doses, isfs, drops = doses[valid], isfs[valid], drops[valid]

        tier_stats = {}
        for tier_name, lo, hi in tiers:
            mask = (doses >= lo) & (doses < hi)
            if mask.sum() >= 3:
                tier_stats[tier_name] = {
                    'n': int(mask.sum()),
                    'median_isf': round(float(np.median(isfs[mask])), 1),
                    'median_drop': round(float(np.median(drops[mask])), 1),
                    'median_dose': round(float(np.median(doses[mask])), 2),
                    'efficiency': round(float(np.median(isfs[mask])), 1),  # ISF = efficiency
                }

        # SMB efficiency ratio
        smb_isf = tier_stats.get('smb', {}).get('median_isf', np.nan)
        large_isf = None
        for tier_name in ['large', 'medium', 'small']:
            if tier_name in tier_stats:
                large_isf = tier_stats[tier_name]['median_isf']
                large_tier = tier_name
                break

        if not np.isnan(smb_isf) and large_isf is not None and large_isf > 0:
            smb_ratio = smb_isf / large_isf
        else:
            smb_ratio = np.nan

        # Total drop comparison: do larger doses achieve meaningfully more drop?
        smb_drop = tier_stats.get('smb', {}).get('median_drop', np.nan)
        large_drop = None
        for tier_name in ['large', 'medium', 'small']:
            if tier_name in tier_stats:
                large_drop = tier_stats[tier_name]['median_drop']
                break

        if not np.isnan(smb_drop) and large_drop is not None and large_drop > 0:
            drop_ratio = large_drop / smb_drop
        else:
            drop_ratio = np.nan

        print(f"  {name}: tiers={list(tier_stats.keys())} "
              f"SMB_ISF={smb_isf:.0f} large_ISF={large_isf:.0f}" +
              (f" ratio={smb_ratio:.1f}×" if not np.isnan(smb_ratio) else "") +
              (f" drop_ratio={drop_ratio:.1f}×" if not np.isnan(drop_ratio) else ""))

        results.append({
            'patient': name,
            'tier_stats': tier_stats,
            'smb_efficiency_ratio': round(float(smb_ratio), 2) if not np.isnan(smb_ratio) else None,
            'drop_ratio': round(float(drop_ratio), 2) if not np.isnan(drop_ratio) else None,
        })

    valid = [r for r in results if r['smb_efficiency_ratio'] is not None]
    mean_ratio = np.mean([r['smb_efficiency_ratio'] for r in valid]) if valid else 0
    mean_drop_ratio = np.mean([r['drop_ratio'] for r in valid
                               if r['drop_ratio'] is not None]) if valid else 0

    print(f"\n  Population SMB efficiency:")
    print(f"    Mean SMB efficiency ratio: {mean_ratio:.1f}× (vs larger boluses)")
    print(f"    Mean drop ratio (large/SMB): {mean_drop_ratio:.1f}× (larger drops but not proportional)")
    print(f"    Patients with data: {len(valid)}")

    if mean_ratio > 2.0:
        verdict = 'SMB_HIGHLY_EFFICIENT'
    elif mean_ratio > 1.3:
        verdict = 'SMB_MODERATELY_EFFICIENT'
    else:
        verdict = 'SMB_NO_ADVANTAGE'

    print(f"\n  ✓ EXP-1865 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        ratios = [r['smb_efficiency_ratio'] for r in valid]
        names = [r['patient'] for r in valid]
        ax.bar(names, ratios, color='#4CAF50')
        ax.axhline(1.0, color='k', linestyle='--', alpha=0.3, label='Equal efficiency')
        ax.axhline(2.0, color='r', linestyle='--', alpha=0.3, label='2× more efficient')
        ax.set_ylabel('SMB Efficiency Ratio (SMB ISF / Large ISF)')
        ax.set_title('EXP-1865: SMB Efficiency per Patient')
        ax.legend(fontsize=8)

        ax = axes[1]
        # Population dose-ISF curve
        all_doses = []
        all_isfs = []
        for p_data in patients:
            corrs = find_corrections(p_data['df'].copy(), min_dose=0.3)
            for c in corrs:
                if 1 < c['isf_observed'] < 500:
                    all_doses.append(c['dose'])
                    all_isfs.append(c['isf_observed'])
        all_doses = np.array(all_doses)
        all_isfs = np.array(all_isfs)

        # Bin means
        bin_edges = [0.3, 0.5, 1, 1.5, 2, 3, 5, 8, 15]
        bin_means = []
        bin_centers = []
        for i in range(len(bin_edges) - 1):
            mask = (all_doses >= bin_edges[i]) & (all_doses < bin_edges[i + 1])
            if mask.sum() >= 5:
                bin_means.append(np.median(all_isfs[mask]))
                bin_centers.append((bin_edges[i] + bin_edges[i + 1]) / 2)

        ax.scatter(all_doses, all_isfs, alpha=0.05, s=5, color='gray')
        ax.plot(bin_centers, bin_means, 'ro-', markersize=8, linewidth=2, label='Binned median')
        ax.set_xlabel('Dose (U)')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title('EXP-1865: Population ISF vs Dose')
        ax.set_xlim(0, 15)
        ax.set_ylim(0, 200)
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig05-smb-efficiency.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig05-smb-efficiency.png")

    return {
        'experiment': 'EXP-1865',
        'title': 'SMB Efficiency — Data-Driven Justification',
        'verdict': verdict,
        'mean_smb_efficiency_ratio': round(mean_ratio, 2),
        'mean_drop_ratio': round(mean_drop_ratio, 2),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1866: Dose-Adjusted CR Estimation
# ===========================================================================

def exp_1866(patients, figures_dir):
    """Since CR is most-wrong for 8/11 patients, and ISF is dose-dependent,
    test whether adjusting for dose-dependent ISF changes the effective CR estimate.

    Idea: If ISF is higher at small doses, meal boluses (often small due to CR)
    should produce more glucose drop per unit. This means CR estimates that
    don't account for dose-dependent ISF are biased.
    """
    print("=" * 70)
    print("EXP-1866: Dose-Adjusted CR Estimation")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
        cr_profile = get_cr(p)

        if len(glucose) < 1000:
            continue

        # Find meal events (carbs > 10g with bolus)
        meals = []
        for i in range(12, len(glucose) - 36):
            if carbs[i] < 10 or bolus[i] < 0.5:
                continue
            g_pre = glucose[i]
            g_peak = np.nanmax(glucose[i:i + 24])  # peak in 2h
            if np.isnan(g_pre) or np.isnan(g_peak):
                continue
            excursion = g_peak - g_pre
            meals.append({
                'carbs': carbs[i],
                'bolus': bolus[i],
                'excursion': excursion,
                'effective_cr': carbs[i] / bolus[i],
            })

        if len(meals) < 10:
            print(f"  {name}: insufficient meals ({len(meals)})")
            continue

        meal_carbs = np.array([m['carbs'] for m in meals])
        meal_bolus = np.array([m['bolus'] for m in meals])
        meal_excursion = np.array([m['excursion'] for m in meals])
        effective_crs = meal_carbs / meal_bolus

        # Fit Hill equation for corrections
        corrections = find_corrections(df)
        if len(corrections) >= 10:
            doses_c = np.array([c['dose'] for c in corrections])
            isfs_c = np.array([c['isf_observed'] for c in corrections])
            vm = (isfs_c > 1) & (isfs_c < 500) & (doses_c > 0)
            if vm.sum() >= 10:
                hill = fit_hill(doses_c[vm], isfs_c[vm])
                # ISF at meal bolus doses
                hill_isf_at_meal = hill_equation(meal_bolus, hill['isf_max'], hill['kd'])
                profile_isf = get_isf(p)

                # Dose-adjusted excursion: expected drop from bolus with Hill ISF
                expected_drop = hill_isf_at_meal * meal_bolus
                # Adjusted CR: if excursion is positive (rise), CR is too low
                # Net effect = carb_rise - insulin_drop = excursion
                # carb_rise = excursion + expected_drop
                # adjusted_CR = carbs / (carb_rise / Hill_ISF)
                carb_rise = meal_excursion + expected_drop
                dose_adjusted_cr = np.where(
                    carb_rise > 0,
                    meal_carbs / (carb_rise / hill_isf_at_meal),
                    np.nan
                )
                valid_adj = np.isfinite(dose_adjusted_cr) & (dose_adjusted_cr > 0)
                median_adj_cr = np.median(dose_adjusted_cr[valid_adj]) if valid_adj.sum() > 5 else np.nan
            else:
                median_adj_cr = np.nan
        else:
            median_adj_cr = np.nan

        median_effective_cr = np.median(effective_crs)
        cr_shift = (median_adj_cr - median_effective_cr) / median_effective_cr if not np.isnan(median_adj_cr) and median_effective_cr > 0 else np.nan

        print(f"  {name}: meals={len(meals)} profile_CR={cr_profile:.0f} "
              f"effective_CR={median_effective_cr:.1f} dose_adj_CR={median_adj_cr:.1f}" +
              (f" shift={cr_shift:+.1%}" if not np.isnan(cr_shift) else ""))

        results.append({
            'patient': name,
            'n_meals': len(meals),
            'cr_profile': cr_profile,
            'median_effective_cr': round(float(median_effective_cr), 1),
            'median_dose_adjusted_cr': round(float(median_adj_cr), 1) if not np.isnan(median_adj_cr) else None,
            'cr_shift': round(float(cr_shift), 3) if not np.isnan(cr_shift) else None,
            'median_excursion': round(float(np.median(meal_excursion)), 1),
        })

    valid = [r for r in results if r['cr_shift'] is not None]
    mean_shift = np.mean([r['cr_shift'] for r in valid]) if valid else 0

    print(f"\n  Population dose-adjusted CR:")
    print(f"    Mean CR shift from dose adjustment: {mean_shift:+.1%}")
    print(f"    Patients with data: {len(valid)}")

    if abs(mean_shift) > 0.15:
        verdict = 'DOSE_ISF_CHANGES_CR'
    elif abs(mean_shift) > 0.05:
        verdict = 'WEAK_CR_SHIFT'
    else:
        verdict = 'CR_UNAFFECTED'

    print(f"\n  ✓ EXP-1866 verdict: {verdict}")

    if HAS_MPL and figures_dir and results:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        names = [r['patient'] for r in results]
        profiles = [r['cr_profile'] for r in results]
        effectives = [r['median_effective_cr'] for r in results]
        adjusted = [r['median_dose_adjusted_cr'] or 0 for r in results]
        x = np.arange(len(names))
        ax.bar(x - 0.25, profiles, 0.25, label='Profile CR', color='#9E9E9E')
        ax.bar(x, effectives, 0.25, label='Effective CR', color='#FF9800')
        ax.bar(x + 0.25, adjusted, 0.25, label='Dose-adjusted CR', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Carb Ratio (g/U)')
        ax.set_title('EXP-1866: CR Estimation Methods')
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig06-cr-adjusted.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig06-cr-adjusted.png")

    return {
        'experiment': 'EXP-1866',
        'title': 'Dose-Adjusted CR Estimation',
        'verdict': verdict,
        'mean_cr_shift': round(mean_shift, 3) if valid else None,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1867: Does Dose-ISF Improve Supply/Demand Model?
# ===========================================================================

def exp_1867(patients, figures_dir):
    """Test whether incorporating dose-dependent ISF into the supply/demand
    model reduces total prediction error.
    """
    print("=" * 70)
    print("EXP-1867: Dose-ISF in Supply/Demand Model")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_base = get_isf(p)

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        # Baseline S/D
        sd_base = compute_supply_demand(df)
        net = sd_base['net']
        dg = np.gradient(glucose)
        resid_base = dg - net
        valid_mask = np.isfinite(resid_base)
        rmse_base = np.sqrt(np.mean(resid_base[valid_mask] ** 2)) if valid_mask.sum() > 0 else np.nan

        # Fit Hill from corrections
        corrections = find_corrections(df)
        if len(corrections) < 10:
            print(f"  {name}: insufficient corrections ({len(corrections)})")
            continue

        doses_c = np.array([c['dose'] for c in corrections])
        isfs_c = np.array([c['isf_observed'] for c in corrections])
        vm = (isfs_c > 1) & (isfs_c < 500) & (doses_c > 0)
        if vm.sum() < 10:
            continue

        hill = fit_hill(doses_c[vm], isfs_c[vm])

        # Apply Hill-equation ISF at typical bolus dose
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
        typical_dose = np.median(bolus[bolus > 0.5]) if (bolus > 0.5).sum() > 0 else 2.0
        hill_isf = hill_equation(typical_dose, hill['isf_max'], hill['kd'])

        # Run S/D with Hill ISF
        df_hill = df.copy()
        df_hill.attrs = dict(df.attrs)
        isf_sched = df_hill.attrs.get('isf_schedule', [{'value': isf_base}])
        new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
        for e in new_sched:
            e['value'] = hill_isf
        df_hill.attrs['isf_schedule'] = new_sched

        sd_hill = compute_supply_demand(df_hill)
        net_hill = sd_hill['net']
        resid_hill = dg - net_hill
        valid_h = np.isfinite(resid_hill)
        rmse_hill = np.sqrt(np.mean(resid_hill[valid_h] ** 2)) if valid_h.sum() > 0 else np.nan

        # Improvement
        if not np.isnan(rmse_base) and not np.isnan(rmse_hill):
            rmse_change = (rmse_base - rmse_hill) / rmse_base * 100
        else:
            rmse_change = 0

        print(f"  {name}: ISF {isf_base:.0f}→{hill_isf:.0f} RMSE {rmse_base:.2f}→{rmse_hill:.2f} "
              f"({rmse_change:+.1f}%)")

        results.append({
            'patient': name,
            'isf_profile': isf_base,
            'isf_hill': round(hill_isf, 1),
            'rmse_baseline': round(float(rmse_base), 3),
            'rmse_hill': round(float(rmse_hill), 3),
            'rmse_change_pct': round(rmse_change, 1),
            'hill_r2': round(hill['r2'], 3),
        })

    valid = [r for r in results]
    mean_change = np.mean([r['rmse_change_pct'] for r in valid]) if valid else 0
    n_improved = sum(1 for r in valid if r['rmse_change_pct'] > 0)

    print(f"\n  Population S/D model improvement:")
    print(f"    Mean RMSE change: {mean_change:+.1f}%")
    print(f"    Patients improved: {n_improved}/{len(valid)}")

    if n_improved > len(valid) * 0.6 and mean_change > 2:
        verdict = 'DOSE_ISF_IMPROVES_MODEL'
    elif mean_change > 0:
        verdict = 'MARGINAL_IMPROVEMENT'
    else:
        verdict = 'NO_IMPROVEMENT'

    print(f"\n  ✓ EXP-1867 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        names = [r['patient'] for r in valid]
        changes = [r['rmse_change_pct'] for r in valid]
        colors = ['#4CAF50' if c > 0 else '#F44336' for c in changes]
        ax.bar(names, changes, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('RMSE Change (%)')
        ax.set_title(f'EXP-1867: S/D Model RMSE with Hill ISF ({n_improved}/{len(valid)} improved)')
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig07-model-improvement.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig07-model-improvement.png")

    return {
        'experiment': 'EXP-1867',
        'title': 'Dose-ISF in Supply/Demand Model',
        'verdict': verdict,
        'mean_rmse_change': round(mean_change, 1),
        'n_improved': n_improved,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1868: Temporal Validation of Dose-ISF
# ===========================================================================

def exp_1868(patients, figures_dir):
    """Temporal validation: fit Hill ISF on first half, evaluate S/D model
    on second half. Does dose-ISF generalize?
    """
    print("=" * 70)
    print("EXP-1868: Temporal Validation of Dose-ISF")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_base = get_isf(p)
        mid = len(glucose) // 2

        df_h1 = df.iloc[:mid].copy()
        df_h2 = df.iloc[mid:].copy()
        df_h1.attrs = dict(df.attrs)
        df_h2.attrs = dict(df.attrs)

        # Fit Hill on half 1
        corr_h1 = find_corrections(df_h1)
        if len(corr_h1) < 10:
            print(f"  {name}: insufficient h1 corrections ({len(corr_h1)})")
            continue

        doses = np.array([c['dose'] for c in corr_h1])
        isfs = np.array([c['isf_observed'] for c in corr_h1])
        vm = (isfs > 1) & (isfs < 500) & (doses > 0)
        if vm.sum() < 10:
            continue

        hill = fit_hill(doses[vm], isfs[vm])

        # Eval on half 2: profile ISF vs Hill ISF
        g2 = df_h2['glucose'].values
        bolus_h2 = df_h2.get('bolus', pd.Series(0, index=df_h2.index)).fillna(0).values
        typical_dose = np.median(bolus_h2[bolus_h2 > 0.5]) if (bolus_h2 > 0.5).sum() > 0 else 2.0
        hill_isf = hill_equation(typical_dose, hill['isf_max'], hill['kd'])

        # Profile baseline
        sd_profile = compute_supply_demand(df_h2)
        _, _, tl_profile = supply_demand_loss(sd_profile, g2)

        # Hill ISF
        df_h2_hill = df_h2.copy()
        df_h2_hill.attrs = dict(df_h2.attrs)
        isf_sched = df_h2_hill.attrs.get('isf_schedule', [{'value': isf_base}])
        new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
        for e in new_sched:
            e['value'] = hill_isf
        df_h2_hill.attrs['isf_schedule'] = new_sched
        sd_hill = compute_supply_demand(df_h2_hill)
        _, _, tl_hill = supply_demand_loss(sd_hill, g2)

        if np.isnan(tl_profile) or np.isnan(tl_hill):
            continue

        improvement = (tl_profile - tl_hill) / tl_profile * 100

        print(f"  {name}: ISF {isf_base:.0f}→{hill_isf:.0f} loss {tl_profile:.1f}→{tl_hill:.1f} "
              f"({improvement:+.1f}%)")

        results.append({
            'patient': name,
            'isf_profile': isf_base,
            'isf_hill_h1': round(hill_isf, 1),
            'loss_profile_h2': round(float(tl_profile), 2),
            'loss_hill_h2': round(float(tl_hill), 2),
            'improvement_pct': round(improvement, 1),
            'hill_params': {'isf_max': hill['isf_max'], 'kd': hill['kd'], 'r2': hill['r2']},
        })

    valid = [r for r in results]
    mean_imp = np.mean([r['improvement_pct'] for r in valid]) if valid else 0
    n_improved = sum(1 for r in valid if r['improvement_pct'] > 0)

    print(f"\n  Population temporal validation:")
    print(f"    Mean improvement on held-out half: {mean_imp:.1f}%")
    print(f"    Patients generalize: {n_improved}/{len(valid)}")

    if n_improved > len(valid) * 0.6:
        verdict = 'DOSE_ISF_GENERALIZES'
    elif n_improved > len(valid) * 0.4:
        verdict = 'PARTIAL_GENERALIZATION'
    else:
        verdict = 'DOES_NOT_GENERALIZE'

    print(f"\n  ✓ EXP-1868 verdict: {verdict}")

    if HAS_MPL and figures_dir and valid:
        fig, ax = plt.subplots(1, 1, figsize=(10, 5))
        names = [r['patient'] for r in valid]
        imps = [r['improvement_pct'] for r in valid]
        colors = ['#4CAF50' if i > 0 else '#F44336' for i in imps]
        ax.bar(names, imps, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Improvement on Held-Out Half (%)')
        ax.set_title(f'EXP-1868: Dose-ISF Temporal Validation ({n_improved}/{len(valid)})')
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'dose-fig08-temporal-validation.png'), dpi=150)
        plt.close()
        print(f"  → Saved dose-fig08-temporal-validation.png")

    return {
        'experiment': 'EXP-1868',
        'title': 'Temporal Validation of Dose-ISF',
        'verdict': verdict,
        'mean_improvement': round(mean_imp, 1),
        'n_generalize': n_improved,
        'per_patient': results,
    }


# ===========================================================================
# Main
# ===========================================================================

EXPERIMENTS = [
    ('EXP-1861', exp_1861),
    ('EXP-1862', exp_1862),
    ('EXP-1863', exp_1863),
    ('EXP-1864', exp_1864),
    ('EXP-1865', exp_1865),
    ('EXP-1866', exp_1866),
    ('EXP-1867', exp_1867),
    ('EXP-1868', exp_1868),
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
    print("EXP-1861–1868: Dose-Dependent ISF & Therapy Assessment")
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

    out_path = 'externals/experiments/exp-1861_dose_isf.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {out_path}")

    print(f"\n{'=' * 70}")
    print("SYNTHESIS: Dose-Dependent ISF & Therapy Assessment")
    print(f"{'=' * 70}")
    for exp_id, result in all_results.items():
        print(f"  {exp_id}: {result.get('verdict', 'N/A')}")
    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
