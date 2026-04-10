#!/usr/bin/env python3
"""
EXP-1851–1858: Harmonic + Context Therapy Estimation

Following the data from EXP-1841–1848 (split-loss therapy deconfounding):
  - EXP-1841: Supply/demand disagree on ISF (Δ=0.32×) → time-varying ISF
  - EXP-1844: Both losses peak at 24h → 4-harmonic is the natural basis
  - EXP-1833: Context is predictable (AUC 0.71–0.95) → context-dependent params
  - EXP-1845: CR most-wrong for 8/11 → improve carb modeling
  - EXP-1846: Loop creates asymmetric loss → formalize deconfounding
  - EXP-1834: ISF depends on dose → Hill-equation ISF(dose)

Key philosophical constraint: this is about deconfounding therapy parameters
(ISF, CR, basal), NOT about improving glucose forecasting.

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_harmonic_therapy_1851.py [--figures]
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

def harmonic_features(timestamps, periods_h=(24, 12, 8, 6)):
    """Build 4-harmonic sin/cos features from timestamps (in steps of 5 min)."""
    # Convert steps to hours
    hours = np.arange(len(timestamps)) * 5.0 / 60.0
    # Use time-of-day from index if available
    if hasattr(timestamps, 'hour'):
        hours = timestamps.hour + timestamps.minute / 60.0
    feats = {}
    for p in periods_h:
        feats[f'sin_{p}h'] = np.sin(2 * np.pi * hours / p)
        feats[f'cos_{p}h'] = np.cos(2 * np.pi * hours / p)
    return pd.DataFrame(feats, index=timestamps)


def get_isf(patient):
    """Get ISF in mg/dL from patient attrs."""
    isf = patient['df'].attrs.get('isf_schedule', [{'value': 50}])
    val = isf[0]['value'] if isinstance(isf, list) else 50
    if val < 15:
        val *= 18.0182  # mmol/L → mg/dL
    return val


def get_cr(patient):
    """Get CR from patient attrs."""
    cr = patient['df'].attrs.get('cr_schedule', [{'value': 10}])
    return cr[0]['value'] if isinstance(cr, list) else 10


def get_basal(patient):
    """Get basal rate from patient attrs."""
    basal = patient['df'].attrs.get('basal_schedule', [{'value': 1.0}])
    return basal[0]['value'] if isinstance(basal, list) else 1.0


def supply_demand_loss(sd, glucose, mask=None):
    """Compute supply-side and demand-side loss separately.

    Supply loss: residual when supply model is wrong (glucose rises unexplained)
    Demand loss: residual when demand model is wrong (glucose falls unexplained)
    """
    net = sd['net']
    dg = np.gradient(glucose)
    residual = dg - net
    if mask is not None:
        residual = residual[mask]
        dg = dg[mask]

    # Filter out NaN values
    valid = np.isfinite(residual)
    if valid.sum() == 0:
        return np.nan, np.nan, np.nan
    residual = residual[valid]

    # Supply residual: positive residual means glucose rose more than model predicts
    supply_resid = np.where(residual > 0, residual ** 2, 0)
    # Demand residual: negative residual means glucose fell more than model predicts
    demand_resid = np.where(residual < 0, residual ** 2, 0)

    supply_loss = np.mean(supply_resid)
    demand_loss = np.mean(demand_resid)
    total_loss = np.mean(residual ** 2)
    return supply_loss, demand_loss, total_loss


def classify_context(df, sd):
    """Classify each timestep into metabolic context.
    Returns array of labels: 'fasting', 'post_meal', 'correction', 'hypo_recovery'
    """
    glucose = df['glucose'].values
    carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
    bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
    iob = df.get('iob', pd.Series(0, index=df.index)).fillna(0).values

    n = len(glucose)
    ctx = np.full(n, 'fasting', dtype='U15')

    for i in range(n):
        # Post-meal: within 3h (36 steps) of carbs > 5g
        carb_window = carbs[max(0, i-36):i+1]
        if np.any(carb_window > 5):
            ctx[i] = 'post_meal'
            continue

        # Hypo recovery: glucose < 70 in last 1h (12 steps)
        g_window = glucose[max(0, i-12):i+1]
        if np.any(g_window < 70) and glucose[i] >= 70:
            ctx[i] = 'hypo_recovery'
            continue

        # Correction: bolus in last 2h (24 steps) without carbs
        bolus_window = bolus[max(0, i-24):i+1]
        if np.any(bolus_window > 0.5):
            ctx[i] = 'correction'
            continue

        # Default: fasting
        ctx[i] = 'fasting'

    return ctx


# ===========================================================================
# EXP-1851: Harmonic ISF(t) via Demand-Side Loss
# ===========================================================================

def exp_1851(patients, figures_dir):
    """Test whether time-varying ISF(t) using 4-harmonic basis explains more
    variance in demand-side loss than a scalar ISF.

    Approach: For each patient, fit ISF(t) = ISF_base × (1 + Σ aₖ sin(2π t/Tₖ) + bₖ cos(2π t/Tₖ))
    using demand-side loss as the objective. Compare R² vs scalar ISF.
    """
    print("=" * 70)
    print("EXP-1851: Harmonic ISF(t) via Demand-Side Loss")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        isf_base = get_isf(p)

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        # Build harmonic features from time index
        h_feats = harmonic_features(df.index)

        # Compute baseline S/D at profile ISF
        sd_base = compute_supply_demand(df)
        _, dl_base, tl_base = supply_demand_loss(sd_base, glucose)

        # Grid search over harmonic amplitudes
        # For efficiency, fit linear regression: demand_residual ~ harmonics
        net = sd_base['net']
        dg = np.gradient(glucose)
        residual = dg - net

        # Demand residual only (where residual < 0)
        demand_mask = residual < 0

        if demand_mask.sum() < 100:
            print(f"  {name}: insufficient demand residuals ({demand_mask.sum()})")
            continue

        # Fit: demand_residual = Σ (aₖ sin + bₖ cos) × insulin_effect
        # This tells us how much ISF varies by time of day
        from numpy.linalg import lstsq

        X = h_feats.values[demand_mask]
        y = residual[demand_mask]

        # Add constant
        X_aug = np.column_stack([np.ones(X.shape[0]), X])
        coeffs, res, rank, sv = lstsq(X_aug, y, rcond=None)

        y_pred = X_aug @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2_harmonic = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Scalar baseline (just mean)
        r2_scalar = 0.0  # by definition, mean explains 0% of variance

        # Amplitude of ISF variation (peak-to-trough as fraction of mean)
        # Generate full-day prediction
        hours_full = np.linspace(0, 24, 289)  # 5-min steps
        h_full = pd.DataFrame({
            f'sin_{p}h': np.sin(2 * np.pi * hours_full / p)
            for p in [24, 12, 8, 6]
        })
        for p in [24, 12, 8, 6]:
            h_full[f'cos_{p}h'] = np.cos(2 * np.pi * hours_full / p)

        X_full = np.column_stack([np.ones(len(hours_full)), h_full.values])
        isf_curve = X_full @ coeffs
        isf_amplitude = (isf_curve.max() - isf_curve.min()) / np.abs(coeffs[0]) if coeffs[0] != 0 else 0

        # Which harmonic dominates?
        harmonic_power = {}
        for idx, p in enumerate([24, 12, 8, 6]):
            sin_coeff = coeffs[1 + idx * 2] if 1 + idx * 2 < len(coeffs) else 0
            cos_coeff = coeffs[2 + idx * 2] if 2 + idx * 2 < len(coeffs) else 0
            harmonic_power[f'{p}h'] = sin_coeff ** 2 + cos_coeff ** 2
        dominant = max(harmonic_power, key=harmonic_power.get)

        print(f"  {name}: ISF={isf_base:.0f} R²_harmonic={r2_harmonic:.4f} "
              f"amplitude={isf_amplitude:.2f} dominant={dominant}")

        results.append({
            'patient': name,
            'isf_base': isf_base,
            'r2_harmonic': round(r2_harmonic, 4),
            'r2_scalar': round(r2_scalar, 4),
            'isf_amplitude': round(isf_amplitude, 3),
            'dominant_harmonic': dominant,
            'harmonic_power': {k: round(v, 4) for k, v in harmonic_power.items()},
            'coeffs': [round(c, 4) for c in coeffs.tolist()],
            'isf_curve_min': round(float(isf_curve.min()), 2),
            'isf_curve_max': round(float(isf_curve.max()), 2),
        })

    # Population summary
    valid = [r for r in results if r['r2_harmonic'] > 0]
    mean_r2 = np.mean([r['r2_harmonic'] for r in valid]) if valid else 0
    mean_amp = np.mean([r['isf_amplitude'] for r in valid]) if valid else 0

    # Count dominant harmonics
    dom_counts = {}
    for r in valid:
        d = r['dominant_harmonic']
        dom_counts[d] = dom_counts.get(d, 0) + 1

    print(f"\n  Population harmonic ISF(t):")
    print(f"    Mean R² (harmonic): {mean_r2:.4f}")
    print(f"    Mean ISF amplitude (peak-to-trough/mean): {mean_amp:.2f}")
    print(f"    Dominant harmonics: {dom_counts}")

    # Verdict
    if mean_r2 > 0.05 and mean_amp > 0.3:
        verdict = 'TIME_VARYING_ISF'
        print(f"\n  ✓ EXP-1851 verdict: {verdict}")
        print(f"    → ISF varies meaningfully by time of day")
    elif mean_amp > 0.2:
        verdict = 'WEAK_CIRCADIAN_ISF'
        print(f"\n  ✓ EXP-1851 verdict: {verdict}")
    else:
        verdict = 'SCALAR_ISF_SUFFICIENT'
        print(f"\n  ✓ EXP-1851 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: ISF curves for all patients
        ax = axes[0]
        hours = np.linspace(0, 24, 289)
        for r in valid:
            coeffs_r = np.array(r['coeffs'])
            h_full_r = np.column_stack([np.ones(len(hours))] + [
                np.sin(2 * np.pi * hours / p) for p in [24, 12, 8, 6]
            ] + [
                np.cos(2 * np.pi * hours / p) for p in [24, 12, 8, 6]
            ])
            curve = h_full_r @ coeffs_r
            # Normalize to fraction of mean
            if coeffs_r[0] != 0:
                curve_frac = curve / coeffs_r[0]
            else:
                curve_frac = curve
            ax.plot(hours, curve_frac, alpha=0.6, label=r['patient'])
        ax.axhline(1.0, color='k', linestyle='--', alpha=0.3)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('ISF Demand Residual (relative to mean)')
        ax.set_title('EXP-1851: Harmonic ISF(t) Curves')
        ax.legend(fontsize=7)

        # Right: Harmonic power spectrum
        ax = axes[1]
        periods = ['24h', '12h', '8h', '6h']
        pop_power = {p: np.mean([r['harmonic_power'].get(p, 0) for r in valid]) for p in periods}
        ax.bar(periods, [pop_power[p] for p in periods], color=['#2196F3', '#FF9800', '#4CAF50', '#9C27B0'])
        ax.set_xlabel('Harmonic Period')
        ax.set_ylabel('Mean Power (coefficient²)')
        ax.set_title('EXP-1851: Dominant Harmonics')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig01-isf-time-varying.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig01-isf-time-varying.png")

    return {
        'experiment': 'EXP-1851',
        'title': 'Harmonic ISF(t) via Demand-Side Loss',
        'verdict': verdict,
        'mean_r2_harmonic': round(mean_r2, 4),
        'mean_isf_amplitude': round(mean_amp, 3),
        'dominant_harmonics': dom_counts,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1852: Context-Dependent ISF Estimation
# ===========================================================================

def exp_1852(patients, figures_dir):
    """Test whether ISF estimated separately per metabolic context reduces
    the massive per-event ISF variability (CV=0.84–1.84 from EXP-1834).

    Contexts: fasting, post_meal, correction, hypo_recovery
    Method: Optimal ISF scale per context via demand-side loss minimization.
    """
    print("=" * 70)
    print("EXP-1852: Context-Dependent ISF Estimation")
    print("=" * 70)

    results = []
    scales = np.array([0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 1.7, 2.0, 2.5, 3.0])
    contexts = ['fasting', 'post_meal', 'correction', 'hypo_recovery']

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        sd_base = compute_supply_demand(df)
        ctx = classify_context(df, sd_base)

        # For each context, find optimal ISF scale via demand-side loss
        ctx_optima = {}
        ctx_counts = {}
        for c in contexts:
            mask = ctx == c
            ctx_counts[c] = int(mask.sum())
            if mask.sum() < 100:
                ctx_optima[c] = np.nan
                continue

            best_scale = 1.0
            best_loss = np.inf
            for s in scales:
                df_s = df.copy()
                isf_orig = get_isf(p)
                # Scale ISF in attrs
                df_s.attrs = dict(df.attrs)
                isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_orig}])
                new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
                for e in new_sched:
                    e['value'] = isf_orig * s
                df_s.attrs['isf_schedule'] = new_sched

                sd_s = compute_supply_demand(df_s)
                _, dl, _ = supply_demand_loss(sd_s, glucose, mask=mask)
                if dl < best_loss:
                    best_loss = dl
                    best_scale = s

            ctx_optima[c] = best_scale

        # Scalar ISF (whole dataset)
        best_scalar = 1.0
        best_scalar_loss = np.inf
        for s in scales:
            df_s = df.copy()
            isf_orig = get_isf(p)
            df_s.attrs = dict(df.attrs)
            isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_orig}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = isf_orig * s
            df_s.attrs['isf_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            _, dl, _ = supply_demand_loss(sd_s, glucose)
            if dl < best_scalar_loss:
                best_scalar_loss = dl
                best_scalar = s

        # Context ISF spread
        valid_ctx = [v for v in ctx_optima.values() if not np.isnan(v)]
        ctx_spread = np.std(valid_ctx) if len(valid_ctx) > 1 else 0

        print(f"  {name}: scalar={best_scalar:.2f}× " +
              " ".join(f"{c}={ctx_optima[c]:.2f}×" for c in contexts if not np.isnan(ctx_optima.get(c, np.nan))) +
              f" spread={ctx_spread:.2f}")

        results.append({
            'patient': name,
            'scalar_optimal': best_scalar,
            'context_optima': {c: round(v, 2) if not np.isnan(v) else None for c, v in ctx_optima.items()},
            'context_counts': ctx_counts,
            'context_spread': round(ctx_spread, 3),
        })

    # Population
    valid = [r for r in results if r['context_spread'] > 0]
    mean_spread = np.mean([r['context_spread'] for r in valid]) if valid else 0

    # Do contexts consistently differ?
    ctx_means = {}
    for c in contexts:
        vals = [r['context_optima'][c] for r in valid if r['context_optima'].get(c) is not None]
        ctx_means[c] = np.mean(vals) if vals else np.nan

    print(f"\n  Population context-dependent ISF:")
    print(f"    Mean context ISF spread: {mean_spread:.3f}")
    for c in contexts:
        print(f"    {c}: mean optimal ISF = {ctx_means.get(c, np.nan):.2f}×")

    n_differ = sum(1 for r in valid if r['context_spread'] > 0.2)
    print(f"    Patients with spread > 0.2: {n_differ}/{len(valid)}")

    if mean_spread > 0.3:
        verdict = 'CONTEXT_DEPENDENT_ISF'
    elif mean_spread > 0.15:
        verdict = 'WEAK_CONTEXT_DEPENDENCE'
    else:
        verdict = 'CONTEXT_INDEPENDENT'

    print(f"\n  ✓ EXP-1852 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: context ISF heatmap
        ax = axes[0]
        names = [r['patient'] for r in valid]
        data = []
        for r in valid:
            row = [r['context_optima'].get(c, np.nan) or np.nan for c in contexts]
            data.append(row)
        data = np.array(data)
        im = ax.imshow(data, aspect='auto', cmap='RdYlBu_r', vmin=0.3, vmax=2.5)
        ax.set_xticks(range(len(contexts)))
        ax.set_xticklabels(contexts, rotation=45, ha='right')
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.set_title('EXP-1852: Optimal ISF Scale by Context')
        plt.colorbar(im, ax=ax, label='ISF scale')

        # Annotate
        for i in range(len(names)):
            for j in range(len(contexts)):
                v = data[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=8)

        # Right: context mean ISF
        ax = axes[1]
        ctx_vals = []
        ctx_labels = []
        for c in contexts:
            vals = [r['context_optima'][c] for r in valid if r['context_optima'].get(c) is not None]
            if vals:
                ctx_vals.append(vals)
                ctx_labels.append(c)
        ax.boxplot(ctx_vals, labels=ctx_labels)
        ax.axhline(1.0, color='r', linestyle='--', alpha=0.5, label='Profile ISF')
        ax.set_ylabel('Optimal ISF Scale')
        ax.set_title('EXP-1852: ISF by Context (Population)')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig02-context-isf.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig02-context-isf.png")

    return {
        'experiment': 'EXP-1852',
        'title': 'Context-Dependent ISF Estimation',
        'verdict': verdict,
        'mean_context_spread': round(mean_spread, 3),
        'context_means': {k: round(v, 2) if not np.isnan(v) else None for k, v in ctx_means.items()},
        'n_context_dependent': n_differ,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1853: UAM-Aware CR Estimation
# ===========================================================================

def exp_1853(patients, figures_dir):
    """Since CR is the most-wrong parameter for 8/11 patients (EXP-1845),
    and 76.5% of meals are UAM (EXP-1341), test whether we can estimate
    effective CR from supply-side loss during UAM events.

    Idea: During UAM rises (glucose rising without carb entry), supply-side
    loss captures unmodeled glucose appearance. If we attribute this to
    "hidden carbs" with a CR, we can estimate effective CR.
    """
    print("=" * 70)
    print("EXP-1853: UAM-Aware CR Estimation from Supply Loss")
    print("=" * 70)

    UAM_THRESHOLD = 1.0  # mg/dL per 5-min step

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        sd = compute_supply_demand(df)
        dg = np.gradient(glucose)
        net = sd['net']
        residual = dg - net

        # Identify UAM events: glucose rising > threshold, no recent carbs
        is_rising = dg > UAM_THRESHOLD
        no_carbs = np.ones(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            if np.any(carbs[max(0, i-36):i+1] > 1):
                no_carbs[i] = False

        uam_mask = is_rising & no_carbs
        n_uam = uam_mask.sum()

        # Announced meal events
        has_carbs = ~no_carbs & is_rising
        n_announced = has_carbs.sum()

        if n_uam < 50:
            print(f"  {name}: insufficient UAM events ({n_uam})")
            continue

        # Supply loss during UAM vs announced meals
        sl_uam, _, _ = supply_demand_loss(sd, glucose, mask=uam_mask)
        sl_ann, _, _ = supply_demand_loss(sd, glucose, mask=has_carbs) if has_carbs.sum() > 50 else (np.nan, 0, 0)

        # Effective CR from UAM: mean unexplained supply per UAM event
        # supply_residual during UAM = unmodeled glucose appearance
        uam_supply_resid = residual[uam_mask]
        mean_uam_supply = np.mean(np.abs(uam_supply_resid))

        # For announced meals: how much of the rise is explained?
        if has_carbs.sum() > 50:
            ann_supply_resid = residual[has_carbs]
            mean_ann_supply = np.mean(np.abs(ann_supply_resid))
        else:
            mean_ann_supply = np.nan

        # UAM/announced ratio tells us about missing carb entries
        uam_fraction = n_uam / (n_uam + n_announced) if (n_uam + n_announced) > 0 else 0

        # Effective "hidden CR" — if we assume UAM rises are from unbolused carbs,
        # what CR would explain the supply residual?
        # mean bolus near UAM events
        uam_boluses = []
        for i in np.where(uam_mask)[0]:
            window = bolus[max(0, i-6):i+7]  # ±30 min
            if window.sum() > 0:
                uam_boluses.append(window.sum())
        mean_uam_bolus = np.mean(uam_boluses) if uam_boluses else 0

        print(f"  {name}: UAM={n_uam} announced={n_announced} fraction={uam_fraction:.2f} "
              f"supply_resid_UAM={mean_uam_supply:.2f} announced={mean_ann_supply:.2f}")

        results.append({
            'patient': name,
            'n_uam': int(n_uam),
            'n_announced': int(n_announced),
            'uam_fraction': round(uam_fraction, 3),
            'supply_loss_uam': round(float(sl_uam), 2),
            'supply_loss_announced': round(float(sl_ann), 2) if not np.isnan(sl_ann) else None,
            'mean_uam_supply_residual': round(float(mean_uam_supply), 3),
            'mean_announced_supply_residual': round(float(mean_ann_supply), 3) if not np.isnan(mean_ann_supply) else None,
            'mean_uam_bolus': round(mean_uam_bolus, 2),
        })

    # Population
    valid = [r for r in results]
    mean_uam_frac = np.mean([r['uam_fraction'] for r in valid])
    mean_supply_uam = np.mean([r['mean_uam_supply_residual'] for r in valid])
    mean_supply_ann = np.mean([r['mean_announced_supply_residual'] for r in valid
                               if r['mean_announced_supply_residual'] is not None])

    supply_ratio = mean_supply_uam / mean_supply_ann if mean_supply_ann > 0 else np.inf

    print(f"\n  Population UAM-aware CR assessment:")
    print(f"    UAM fraction: {mean_uam_frac:.2f}")
    print(f"    Mean supply residual (UAM): {mean_supply_uam:.3f}")
    print(f"    Mean supply residual (announced): {mean_supply_ann:.3f}")
    print(f"    UAM/announced supply ratio: {supply_ratio:.2f}")

    if supply_ratio > 1.5:
        verdict = 'UAM_UNDERMODELED'
    elif supply_ratio > 1.1:
        verdict = 'WEAK_UAM_SIGNAL'
    else:
        verdict = 'UAM_WELL_MODELED'

    print(f"\n  ✓ EXP-1853 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        uam_vals = [r['mean_uam_supply_residual'] for r in valid]
        ann_vals = [r['mean_announced_supply_residual'] or 0 for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, uam_vals, 0.4, label='UAM events', color='#FF5722')
        ax.bar(x + 0.2, ann_vals, 0.4, label='Announced meals', color='#2196F3')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Mean |Supply Residual|')
        ax.set_title('EXP-1853: Supply Residual by Meal Type')
        ax.legend()

        ax = axes[1]
        fracs = [r['uam_fraction'] for r in valid]
        ax.bar(names, fracs, color='#FF9800')
        ax.axhline(0.765, color='r', linestyle='--', alpha=0.5, label='EXP-1341 population (76.5%)')
        ax.set_ylabel('UAM Fraction')
        ax.set_title('EXP-1853: UAM Fraction per Patient')
        ax.legend()

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig03-uam-cr.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig03-uam-cr.png")

    return {
        'experiment': 'EXP-1853',
        'title': 'UAM-Aware CR Estimation from Supply Loss',
        'verdict': verdict,
        'mean_uam_fraction': round(mean_uam_frac, 3),
        'supply_ratio_uam_vs_announced': round(supply_ratio, 2),
        'per_patient': results,
    }


# ===========================================================================
# EXP-1854: Loop Compensation Deconfounding Algorithm
# ===========================================================================

def exp_1854(patients, figures_dir):
    """Formalize EXP-1846's finding: AID loop creates asymmetric loss signatures.

    When loop is active: supply loss ↑, demand loss ↓
    Direction of asymmetry tells us WHAT the loop is compensating for.

    Build: compensation_direction = sign(supply_loss_ratio - demand_loss_ratio)
    If positive: loop is increasing insulin → ISF too low or CR too low
    If negative: loop is reducing insulin → ISF too high or basal too high
    """
    print("=" * 70)
    print("EXP-1854: Loop Compensation Deconfounding")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        temp_rate = df.get('temp_rate', pd.Series(0, index=df.index)).fillna(0).values
        basal_rate = get_basal(p)

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        sd = compute_supply_demand(df)

        # Loop is "active" when temp_rate != basal (adjusting delivery)
        loop_active = np.abs(temp_rate - basal_rate) > 0.05
        loop_increasing = temp_rate > basal_rate + 0.05
        loop_decreasing = temp_rate < basal_rate - 0.05

        n_active = loop_active.sum()
        n_increasing = loop_increasing.sum()
        n_decreasing = loop_decreasing.sum()

        if n_active < 100:
            print(f"  {name}: insufficient loop adjustments ({n_active})")
            continue

        # S/D loss during increasing vs decreasing
        if n_increasing > 50:
            sl_inc, dl_inc, _ = supply_demand_loss(sd, glucose, mask=loop_increasing)
        else:
            sl_inc, dl_inc = np.nan, np.nan

        if n_decreasing > 50:
            sl_dec, dl_dec, _ = supply_demand_loss(sd, glucose, mask=loop_decreasing)
        else:
            sl_dec, dl_dec = np.nan, np.nan

        # Inactive baseline
        inactive = ~loop_active
        if inactive.sum() > 50:
            sl_base, dl_base, _ = supply_demand_loss(sd, glucose, mask=inactive)
        else:
            sl_base, dl_base = np.nan, np.nan

        # Compensation asymmetry
        if not np.isnan(sl_inc) and not np.isnan(sl_dec):
            # When increasing: supply loss should rise (more insulin → demand satisfied but supply excess)
            # When decreasing: demand loss should rise (less insulin → demand unsatisfied)
            asymmetry = (sl_inc / (sl_dec + 1e-10)) - (dl_inc / (dl_dec + 1e-10))
        else:
            asymmetry = np.nan

        # Inferred compensation direction
        if not np.isnan(asymmetry):
            if asymmetry > 0.2:
                comp_direction = 'ISF_TOO_LOW'
            elif asymmetry < -0.2:
                comp_direction = 'ISF_TOO_HIGH'
            else:
                comp_direction = 'BALANCED'
        else:
            comp_direction = 'INSUFFICIENT_DATA'

        inc_frac = n_increasing / n_active if n_active > 0 else 0

        print(f"  {name}: active={n_active} inc={n_increasing} dec={n_decreasing} "
              f"asymmetry={asymmetry:.2f} → {comp_direction}" if not np.isnan(asymmetry) else
              f"  {name}: active={n_active} → {comp_direction}")

        results.append({
            'patient': name,
            'loop_active': int(n_active),
            'loop_increasing': int(n_increasing),
            'loop_decreasing': int(n_decreasing),
            'increasing_fraction': round(inc_frac, 3),
            'supply_loss_increasing': round(float(sl_inc), 2) if not np.isnan(sl_inc) else None,
            'demand_loss_increasing': round(float(dl_inc), 2) if not np.isnan(dl_inc) else None,
            'supply_loss_decreasing': round(float(sl_dec), 2) if not np.isnan(sl_dec) else None,
            'demand_loss_decreasing': round(float(dl_dec), 2) if not np.isnan(dl_dec) else None,
            'asymmetry': round(float(asymmetry), 3) if not np.isnan(asymmetry) else None,
            'compensation_direction': comp_direction,
        })

    # Population
    valid = [r for r in results if r['asymmetry'] is not None]
    mean_asym = np.mean([r['asymmetry'] for r in valid]) if valid else np.nan
    directions = {}
    for r in valid:
        d = r['compensation_direction']
        directions[d] = directions.get(d, 0) + 1

    print(f"\n  Population loop compensation analysis (n={len(valid)}):")
    print(f"    Mean asymmetry: {mean_asym:.3f}")
    print(f"    Compensation directions: {directions}")
    print(f"    Mean increasing fraction: {np.mean([r['increasing_fraction'] for r in valid]):.2f}")

    if abs(mean_asym) > 0.2:
        verdict = 'ASYMMETRIC_COMPENSATION'
    else:
        verdict = 'SYMMETRIC_COMPENSATION'

    print(f"\n  ✓ EXP-1854 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        asyms = [r['asymmetry'] for r in valid]
        colors = ['#F44336' if a > 0.2 else '#2196F3' if a < -0.2 else '#9E9E9E' for a in asyms]
        ax.barh(names, asyms, color=colors)
        ax.axvline(0, color='k', linewidth=0.5)
        ax.axvline(0.2, color='r', linestyle='--', alpha=0.3)
        ax.axvline(-0.2, color='b', linestyle='--', alpha=0.3)
        ax.set_xlabel('Asymmetry (+ → ISF too low, - → ISF too high)')
        ax.set_title('EXP-1854: Loop Compensation Direction')

        ax = axes[1]
        inc_fracs = [r['increasing_fraction'] for r in valid]
        ax.bar(names, inc_fracs, color='#FF9800')
        ax.axhline(0.5, color='k', linestyle='--', alpha=0.3)
        ax.set_ylabel('Fraction of Adjustments That INCREASE Insulin')
        ax.set_title('EXP-1854: Loop Adjustment Direction')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig04-loop-deconfounding.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig04-loop-deconfounding.png")

    return {
        'experiment': 'EXP-1854',
        'title': 'Loop Compensation Deconfounding',
        'verdict': verdict,
        'mean_asymmetry': round(float(mean_asym), 3) if not np.isnan(mean_asym) else None,
        'compensation_directions': directions,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1855: Demand-Only Basal Estimator
# ===========================================================================

def exp_1855(patients, figures_dir):
    """Develop demand-side loss as a basal rate estimator, using overnight
    fasting periods where the AID loop is inactive.

    EXP-1842 showed demand-optimal scale (1.43) is more reasonable than
    supply-optimal (always 0.50). This experiment refines with:
    1. Overnight-only fasting (11pm–6am)
    2. AID-inactive filter
    3. Demand-side gradient direction as adjustment signal
    """
    print("=" * 70)
    print("EXP-1855: Demand-Only Overnight Basal Estimator")
    print("=" * 70)

    results = []
    scales = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.7, 2.0])

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        temp_rate = df.get('temp_rate', pd.Series(0, index=df.index)).fillna(0).values
        basal_rate = get_basal(p)

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        # Overnight fasting: 11pm–6am, no carbs in last 4h
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values
        overnight = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            if hasattr(df.index[i], 'hour'):
                h = df.index[i].hour
                if h >= 23 or h < 6:
                    # No carbs in last 4h (48 steps)
                    if np.all(carbs[max(0, i-48):i+1] < 1):
                        overnight[i] = True

        # AID inactive filter
        loop_inactive = np.abs(temp_rate - basal_rate) < 0.05
        clean_fasting = overnight & loop_inactive

        n_clean = clean_fasting.sum()
        if n_clean < 100:
            print(f"  {name}: insufficient clean fasting ({n_clean} steps)")
            # Fall back to all overnight
            clean_fasting = overnight
            n_clean = clean_fasting.sum()
            if n_clean < 100:
                print(f"  {name}: insufficient overnight ({n_clean} steps)")
                continue

        # Optimal basal scale via demand-side loss
        best_scale = 1.0
        best_dl = np.inf
        dl_curve = []
        for s in scales:
            df_s = df.copy()
            df_s.attrs = dict(df.attrs)
            b_sched = df_s.attrs.get('basal_schedule', [{'value': basal_rate}])
            new_sched = [dict(e) for e in (b_sched if isinstance(b_sched, list) else [b_sched])]
            for e in new_sched:
                e['value'] = basal_rate * s
            df_s.attrs['basal_schedule'] = new_sched

            sd_s = compute_supply_demand(df_s)
            _, dl, _ = supply_demand_loss(sd_s, glucose, mask=clean_fasting)
            dl_curve.append(dl)
            if dl < best_dl:
                best_dl = dl
                best_scale = s

        # Overnight glucose drift
        dg = np.gradient(glucose)
        drift = np.nanmean(dg[clean_fasting]) * 12  # mg/dL per hour

        print(f"  {name}: basal={basal_rate:.2f}U/h clean_fasting={n_clean} "
              f"drift={drift:+.2f}mg/dL/h demand_opt={best_scale:.2f}×")

        results.append({
            'patient': name,
            'basal_rate': basal_rate,
            'n_clean_fasting': int(n_clean),
            'overnight_drift': round(float(drift), 2),
            'demand_optimal_scale': best_scale,
            'demand_loss_curve': [round(float(d), 2) for d in dl_curve],
        })

    # Population
    valid = [r for r in results]
    mean_opt = np.mean([r['demand_optimal_scale'] for r in valid])
    mean_drift = np.mean([r['overnight_drift'] for r in valid])

    # Correlation: does drift direction predict needed adjustment?
    drifts = [r['overnight_drift'] for r in valid]
    opts = [r['demand_optimal_scale'] for r in valid]
    if len(valid) > 3:
        corr = np.corrcoef(drifts, opts)[0, 1]
    else:
        corr = np.nan

    print(f"\n  Population overnight basal assessment (n={len(valid)}):")
    print(f"    Mean demand-optimal scale: {mean_opt:.2f}×")
    print(f"    Mean overnight drift: {mean_drift:+.2f} mg/dL/h")
    print(f"    Drift ↔ optimal_scale correlation: {corr:.3f}")

    if abs(corr) > 0.5:
        verdict = 'DRIFT_PREDICTS_BASAL'
    elif abs(mean_opt - 1.0) > 0.2:
        verdict = 'BASAL_MISCALIBRATED'
    else:
        verdict = 'BASAL_ADEQUATE'

    print(f"\n  ✓ EXP-1855 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        drifts_plot = [r['overnight_drift'] for r in valid]
        colors = ['#F44336' if d > 2 else '#2196F3' if d < -2 else '#4CAF50' for d in drifts_plot]
        ax.bar(names, drifts_plot, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.axhline(2, color='r', linestyle='--', alpha=0.3, label='Rising (+2)')
        ax.axhline(-2, color='b', linestyle='--', alpha=0.3, label='Falling (-2)')
        ax.set_ylabel('Overnight Glucose Drift (mg/dL/h)')
        ax.set_title('EXP-1855: Overnight Fasting Drift')
        ax.legend(fontsize=8)

        ax = axes[1]
        ax.scatter(drifts_plot, [r['demand_optimal_scale'] for r in valid], s=80)
        for i, r in enumerate(valid):
            ax.annotate(r['patient'], (r['overnight_drift'], r['demand_optimal_scale']),
                       fontsize=8, ha='center', va='bottom')
        ax.axhline(1.0, color='r', linestyle='--', alpha=0.3)
        ax.axvline(0, color='k', linestyle='--', alpha=0.3)
        ax.set_xlabel('Overnight Drift (mg/dL/h)')
        ax.set_ylabel('Demand-Optimal Basal Scale')
        ax.set_title(f'EXP-1855: Drift vs Optimal Basal (r={corr:.2f})')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig05-overnight-basal.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig05-overnight-basal.png")

    return {
        'experiment': 'EXP-1855',
        'title': 'Demand-Only Overnight Basal Estimator',
        'verdict': verdict,
        'mean_demand_optimal': round(mean_opt, 2),
        'mean_overnight_drift': round(mean_drift, 2),
        'drift_basal_correlation': round(float(corr), 3) if not np.isnan(corr) else None,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1856: ISF Dose-Response Curve
# ===========================================================================

def exp_1856(patients, figures_dir):
    """EXP-1834 showed dose size is the top ISF driver — larger boluses show
    smaller per-unit effect (saturation). Test whether ISF follows a
    Hill-equation dose-response: ISF(dose) = ISF_max × Kd^n / (Kd^n + dose^n)

    This would mean ISF isn't a constant — it's a function of how much insulin
    you give, which has profound implications for AID algorithms.
    """
    print("=" * 70)
    print("EXP-1856: ISF Dose-Response Curve (Hill Equation)")
    print("=" * 70)

    results = []
    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values
        bolus = df.get('bolus', pd.Series(0, index=df.index)).fillna(0).values
        carbs = df.get('carbs', pd.Series(0, index=df.index)).fillna(0).values

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        # Find correction boluses (bolus > 0.5U, no carbs within ±30min)
        corrections = []
        for i in range(24, len(glucose) - 72):  # Need 6h post window
            if bolus[i] < 0.5:
                continue
            # No carbs within ±1h
            if np.any(carbs[max(0, i-12):i+12] > 1):
                continue
            # Measure glucose drop in 2h window
            g_pre = glucose[i]
            g_post = np.nanmin(glucose[i:i+36])  # nadir in 3h
            if np.isnan(g_pre) or np.isnan(g_post):
                continue
            drop = g_pre - g_post
            if drop > 0:  # Must be a glucose decrease
                isf_event = drop / bolus[i]
                corrections.append({
                    'dose': bolus[i],
                    'drop': drop,
                    'isf': isf_event,
                    'g_pre': g_pre,
                })

        n_corr = len(corrections)
        if n_corr < 5:
            print(f"  {name}: insufficient corrections ({n_corr})")
            continue

        doses = np.array([c['dose'] for c in corrections])
        isfs = np.array([c['isf'] for c in corrections])

        # Fit Hill equation: ISF(dose) = ISF_max * Kd^n / (Kd^n + dose^n)
        # Use log-linear approximation: log(ISF) = a - b * log(dose)
        # This captures saturation if b > 0
        from numpy.linalg import lstsq

        valid_mask = (doses > 0) & (isfs > 0) & np.isfinite(doses) & np.isfinite(isfs)
        if valid_mask.sum() < 5:
            continue

        log_dose = np.log(doses[valid_mask])
        log_isf = np.log(isfs[valid_mask])

        X = np.column_stack([np.ones(log_dose.shape[0]), log_dose])
        coeffs, _, _, _ = lstsq(X, log_isf, rcond=None)

        slope = coeffs[1]  # Negative slope = saturation
        r2_loglog = 1 - np.sum((log_isf - X @ coeffs) ** 2) / np.sum((log_isf - log_isf.mean()) ** 2)

        # Simple stats
        dose_bins = [(0, 2), (2, 5), (5, 100)]
        bin_means = {}
        for lo, hi in dose_bins:
            mask_bin = (doses >= lo) & (doses < hi)
            if mask_bin.sum() >= 3:
                bin_means[f'{lo}-{hi}U'] = round(float(np.median(isfs[mask_bin])), 1)

        mean_isf = np.median(isfs)
        isf_cv = np.std(isfs) / mean_isf if mean_isf > 0 else 0

        print(f"  {name}: corrections={n_corr} slope={slope:.3f} R²={r2_loglog:.3f} "
              f"median_ISF={mean_isf:.0f} CV={isf_cv:.2f} bins={bin_means}")

        results.append({
            'patient': name,
            'n_corrections': n_corr,
            'dose_isf_slope': round(float(slope), 3),
            'r2_loglog': round(float(r2_loglog), 3),
            'median_isf': round(float(mean_isf), 1),
            'isf_cv': round(float(isf_cv), 3),
            'dose_bin_isf': bin_means,
            'intercept': round(float(coeffs[0]), 3),
        })

    # Population
    valid = [r for r in results]
    mean_slope = np.mean([r['dose_isf_slope'] for r in valid]) if valid else 0
    n_saturating = sum(1 for r in valid if r['dose_isf_slope'] < -0.2)

    print(f"\n  Population ISF dose-response (n={len(valid)}):")
    print(f"    Mean log-log slope: {mean_slope:.3f}")
    print(f"    Patients with saturation (slope < -0.2): {n_saturating}/{len(valid)}")
    print(f"    Mean ISF CV: {np.mean([r['isf_cv'] for r in valid]):.2f}")

    if n_saturating > len(valid) * 0.5:
        verdict = 'DOSE_DEPENDENT_ISF'
    elif mean_slope < -0.1:
        verdict = 'WEAK_DOSE_DEPENDENCE'
    else:
        verdict = 'DOSE_INDEPENDENT_ISF'

    print(f"\n  ✓ EXP-1856 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        for r in valid:
            ax.bar(r['patient'], r['dose_isf_slope'],
                   color='#F44336' if r['dose_isf_slope'] < -0.2 else '#4CAF50')
        ax.axhline(0, color='k', linewidth=0.5)
        ax.axhline(-0.2, color='r', linestyle='--', alpha=0.3, label='Saturation threshold')
        ax.set_ylabel('Log-log Slope (dose → ISF)')
        ax.set_title('EXP-1856: ISF Dose-Response Slope')
        ax.legend(fontsize=8)

        ax = axes[1]
        for r in valid:
            bins = r['dose_bin_isf']
            if len(bins) >= 2:
                ax.plot(list(bins.keys()), list(bins.values()), 'o-', label=r['patient'], alpha=0.6)
        ax.set_xlabel('Dose Bin')
        ax.set_ylabel('Median ISF (mg/dL/U)')
        ax.set_title('EXP-1856: ISF by Dose Size')
        ax.legend(fontsize=7)

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig06-dose-response.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig06-dose-response.png")

    return {
        'experiment': 'EXP-1856',
        'title': 'ISF Dose-Response Curve',
        'verdict': verdict,
        'mean_dose_isf_slope': round(float(mean_slope), 3),
        'n_saturating': n_saturating,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1857: Combined Harmonic + Context Therapy Estimator
# ===========================================================================

def exp_1857(patients, figures_dir):
    """Capstone: combine harmonic ISF(t), context classification, and
    split-loss into a unified therapy parameter estimator.

    For each patient, estimate:
    1. ISF(t, context) = ISF_base × harmonic(t) × context_factor(c)
    2. CR from supply-side loss during meals
    3. Basal from demand-side loss during overnight fasting

    Compare total loss with combined estimates vs profile settings.
    """
    print("=" * 70)
    print("EXP-1857: Combined Harmonic + Context Therapy Estimator")
    print("=" * 70)

    results = []
    scales = np.array([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0])

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values

        if len(glucose) < 1000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        isf_base = get_isf(p)
        cr_base = get_cr(p)
        basal_base = get_basal(p)

        # Baseline loss
        sd_base = compute_supply_demand(df)
        sl_base, dl_base, tl_base = supply_demand_loss(sd_base, glucose)

        # Step 1: Context classification
        ctx = classify_context(df, sd_base)

        # Step 2: Per-context ISF optimization (demand-side)
        ctx_isf = {}
        for c in ['fasting', 'post_meal', 'correction', 'hypo_recovery']:
            mask = ctx == c
            if mask.sum() < 100:
                ctx_isf[c] = 1.0
                continue

            best_s, best_dl_c = 1.0, np.inf
            for s in scales:
                df_s = df.copy()
                df_s.attrs = dict(df.attrs)
                isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_base}])
                new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
                for e in new_sched:
                    e['value'] = isf_base * s
                df_s.attrs['isf_schedule'] = new_sched
                sd_s = compute_supply_demand(df_s)
                _, dl_c, _ = supply_demand_loss(sd_s, glucose, mask=mask)
                if dl_c < best_dl_c:
                    best_dl_c = dl_c
                    best_s = s
            ctx_isf[c] = best_s

        # Step 3: CR optimization (supply-side, post-meal only)
        meal_mask = ctx == 'post_meal'
        best_cr_s, best_sl_cr = 1.0, np.inf
        if meal_mask.sum() > 100:
            for s in scales:
                df_s = df.copy()
                df_s.attrs = dict(df.attrs)
                cr_sched = df_s.attrs.get('cr_schedule', [{'value': cr_base}])
                new_sched = [dict(e) for e in (cr_sched if isinstance(cr_sched, list) else [cr_sched])]
                for e in new_sched:
                    e['value'] = cr_base * s
                df_s.attrs['cr_schedule'] = new_sched
                sd_s = compute_supply_demand(df_s)
                sl_cr, _, _ = supply_demand_loss(sd_s, glucose, mask=meal_mask)
                if sl_cr < best_sl_cr:
                    best_sl_cr = sl_cr
                    best_cr_s = s

        # Step 4: Basal optimization (demand-side, fasting)
        fast_mask = ctx == 'fasting'
        best_basal_s, best_dl_basal = 1.0, np.inf
        if fast_mask.sum() > 100:
            for s in scales:
                df_s = df.copy()
                df_s.attrs = dict(df.attrs)
                b_sched = df_s.attrs.get('basal_schedule', [{'value': basal_base}])
                new_sched = [dict(e) for e in (b_sched if isinstance(b_sched, list) else [b_sched])]
                for e in new_sched:
                    e['value'] = basal_base * s
                df_s.attrs['basal_schedule'] = new_sched
                sd_s = compute_supply_demand(df_s)
                _, dl_basal, _ = supply_demand_loss(sd_s, glucose, mask=fast_mask)
                if dl_basal < best_dl_basal:
                    best_dl_basal = dl_basal
                    best_basal_s = s

        # Step 5: Evaluate combined estimate vs profile
        # Apply best per-context ISF (weighted by context prevalence)
        weighted_isf = sum(
            ctx_isf[c] * (ctx == c).sum() for c in ctx_isf
        ) / len(glucose)

        df_combined = df.copy()
        df_combined.attrs = dict(df.attrs)
        isf_sched = df_combined.attrs.get('isf_schedule', [{'value': isf_base}])
        new_isf = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
        for e in new_isf:
            e['value'] = isf_base * weighted_isf
        df_combined.attrs['isf_schedule'] = new_isf

        cr_sched = df_combined.attrs.get('cr_schedule', [{'value': cr_base}])
        new_cr = [dict(e) for e in (cr_sched if isinstance(cr_sched, list) else [cr_sched])]
        for e in new_cr:
            e['value'] = cr_base * best_cr_s
        df_combined.attrs['cr_schedule'] = new_cr

        sd_combined = compute_supply_demand(df_combined)
        _, _, tl_combined = supply_demand_loss(sd_combined, glucose)

        improvement = tl_base - tl_combined
        pct_improvement = improvement / tl_base * 100 if tl_base > 0 else 0

        print(f"  {name}: ISF(ctx)={ctx_isf} CR×{best_cr_s:.2f} basal×{best_basal_s:.2f} "
              f"loss {tl_base:.1f}→{tl_combined:.1f} ({pct_improvement:+.1f}%)")

        results.append({
            'patient': name,
            'context_isf': {k: round(v, 2) for k, v in ctx_isf.items()},
            'cr_scale': round(best_cr_s, 2),
            'basal_scale': round(best_basal_s, 2),
            'weighted_isf': round(weighted_isf, 3),
            'baseline_loss': round(float(tl_base), 2),
            'combined_loss': round(float(tl_combined), 2),
            'improvement': round(float(improvement), 2),
            'pct_improvement': round(float(pct_improvement), 1),
        })

    # Population
    valid = [r for r in results]
    mean_pct = np.mean([r['pct_improvement'] for r in valid]) if valid else 0
    n_improved = sum(1 for r in valid if r['improvement'] > 0)

    print(f"\n  Population combined therapy assessment (n={len(valid)}):")
    print(f"    Mean improvement: {mean_pct:.1f}%")
    print(f"    Patients improved: {n_improved}/{len(valid)}")

    if mean_pct > 20:
        verdict = 'COMBINED_ESTIMATION_WORKS'
    elif mean_pct > 5:
        verdict = 'MODERATE_IMPROVEMENT'
    else:
        verdict = 'PROFILE_ADEQUATE'

    print(f"\n  ✓ EXP-1857 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        base_losses = [r['baseline_loss'] for r in valid]
        comb_losses = [r['combined_loss'] for r in valid]
        x = np.arange(len(names))
        ax.bar(x - 0.2, base_losses, 0.4, label='Profile', color='#9E9E9E')
        ax.bar(x + 0.2, comb_losses, 0.4, label='Combined estimate', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Total Loss')
        ax.set_title('EXP-1857: Profile vs Combined Therapy Estimate')
        ax.legend()

        ax = axes[1]
        pcts = [r['pct_improvement'] for r in valid]
        colors = ['#4CAF50' if p > 0 else '#F44336' for p in pcts]
        ax.bar(names, pcts, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Improvement (%)')
        ax.set_title(f'EXP-1857: Loss Improvement ({n_improved}/{len(valid)} improved)')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig07-combined-therapy.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig07-combined-therapy.png")

    return {
        'experiment': 'EXP-1857',
        'title': 'Combined Harmonic + Context Therapy Estimator',
        'verdict': verdict,
        'mean_pct_improvement': round(mean_pct, 1),
        'n_improved': n_improved,
        'per_patient': results,
    }


# ===========================================================================
# EXP-1858: Temporal Validation — First Half → Second Half
# ===========================================================================

def exp_1858(patients, figures_dir):
    """Validation: estimate therapy parameters from the first half of data,
    evaluate glucose quality metrics in the second half.

    Does better parameter estimation → better glucose outcome prediction?
    """
    print("=" * 70)
    print("EXP-1858: Temporal Validation (Train on Half 1, Eval on Half 2)")
    print("=" * 70)

    results = []
    scales = np.array([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0])

    for p in patients:
        name = p['name']
        df = p['df'].copy()
        glucose = df['glucose'].values

        if len(glucose) < 2000 or np.isnan(glucose).sum() > len(glucose) * 0.5:
            continue

        mid = len(glucose) // 2
        df_h1 = df.iloc[:mid].copy()
        df_h2 = df.iloc[mid:].copy()
        # Preserve attrs
        df_h1.attrs = dict(df.attrs)
        df_h2.attrs = dict(df.attrs)
        g1 = df_h1['glucose'].values
        g2 = df_h2['glucose'].values

        isf_base = get_isf(p)
        cr_base = get_cr(p)

        # Train: find optimal ISF and CR on half 1 (demand-side for ISF, supply for CR)
        sd_h1 = compute_supply_demand(df_h1)

        best_isf_s, best_isf_dl = 1.0, np.inf
        for s in scales:
            df_s = df_h1.copy()
            df_s.attrs = dict(df_h1.attrs)
            isf_sched = df_s.attrs.get('isf_schedule', [{'value': isf_base}])
            new_sched = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
            for e in new_sched:
                e['value'] = isf_base * s
            df_s.attrs['isf_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            _, dl, _ = supply_demand_loss(sd_s, g1)
            if dl < best_isf_dl:
                best_isf_dl = dl
                best_isf_s = s

        best_cr_s, best_cr_sl = 1.0, np.inf
        for s in scales:
            df_s = df_h1.copy()
            df_s.attrs = dict(df_h1.attrs)
            cr_sched = df_s.attrs.get('cr_schedule', [{'value': cr_base}])
            new_sched = [dict(e) for e in (cr_sched if isinstance(cr_sched, list) else [cr_sched])]
            for e in new_sched:
                e['value'] = cr_base * s
            df_s.attrs['cr_schedule'] = new_sched
            sd_s = compute_supply_demand(df_s)
            sl, _, _ = supply_demand_loss(sd_s, g1)
            if sl < best_cr_sl:
                best_cr_sl = sl
                best_cr_s = s

        # Eval: total loss on half 2 with profile vs estimated params
        sd_h2_profile = compute_supply_demand(df_h2)
        _, _, tl_profile = supply_demand_loss(sd_h2_profile, g2)

        # Apply estimated params to half 2
        df_h2_est = df_h2.copy()
        df_h2_est.attrs = dict(df_h2.attrs)
        isf_sched = df_h2_est.attrs.get('isf_schedule', [{'value': isf_base}])
        new_isf = [dict(e) for e in (isf_sched if isinstance(isf_sched, list) else [isf_sched])]
        for e in new_isf:
            e['value'] = isf_base * best_isf_s
        df_h2_est.attrs['isf_schedule'] = new_isf

        cr_sched = df_h2_est.attrs.get('cr_schedule', [{'value': cr_base}])
        new_cr = [dict(e) for e in (cr_sched if isinstance(cr_sched, list) else [cr_sched])]
        for e in new_cr:
            e['value'] = cr_base * best_cr_s
        df_h2_est.attrs['cr_schedule'] = new_cr

        sd_h2_est = compute_supply_demand(df_h2_est)
        _, _, tl_estimated = supply_demand_loss(sd_h2_est, g2)

        improvement = tl_profile - tl_estimated
        pct = improvement / tl_profile * 100 if tl_profile > 0 else 0

        # Also compute glucose quality metrics on half 2
        g2_valid = g2[~np.isnan(g2)]
        tir = np.mean((g2_valid >= 70) & (g2_valid <= 180)) * 100 if len(g2_valid) > 0 else np.nan
        tbr = np.mean(g2_valid < 70) * 100 if len(g2_valid) > 0 else np.nan
        tar = np.mean(g2_valid > 180) * 100 if len(g2_valid) > 0 else np.nan
        cv = np.std(g2_valid) / np.mean(g2_valid) * 100 if len(g2_valid) > 0 else np.nan

        print(f"  {name}: ISF×{best_isf_s:.2f} CR×{best_cr_s:.2f} → "
              f"loss {tl_profile:.1f}→{tl_estimated:.1f} ({pct:+.1f}%) "
              f"TIR={tir:.0f}% TBR={tbr:.1f}%")

        results.append({
            'patient': name,
            'estimated_isf_scale': best_isf_s,
            'estimated_cr_scale': best_cr_s,
            'profile_loss_h2': round(float(tl_profile), 2),
            'estimated_loss_h2': round(float(tl_estimated), 2),
            'improvement': round(float(improvement), 2),
            'pct_improvement': round(float(pct), 1),
            'tir': round(float(tir), 1),
            'tbr': round(float(tbr), 1),
            'tar': round(float(tar), 1),
            'cv': round(float(cv), 1),
        })

    # Population
    valid = [r for r in results]
    mean_pct = np.mean([r['pct_improvement'] for r in valid]) if valid else 0
    n_improved = sum(1 for r in valid if r['improvement'] > 0)

    # Does estimated improvement correlate with glucose quality?
    if len(valid) > 3:
        imprs = [r['pct_improvement'] for r in valid]
        tirs = [r['tir'] for r in valid]
        corr_tir = np.corrcoef(imprs, tirs)[0, 1] if not any(np.isnan(tirs)) else np.nan
    else:
        corr_tir = np.nan

    print(f"\n  Population temporal validation (n={len(valid)}):")
    print(f"    Mean improvement on held-out half: {mean_pct:.1f}%")
    print(f"    Patients improved: {n_improved}/{len(valid)}")
    print(f"    Improvement ↔ TIR correlation: {corr_tir:.3f}" if not np.isnan(corr_tir) else
          "    Improvement ↔ TIR correlation: N/A")

    if n_improved > len(valid) * 0.7:
        verdict = 'ESTIMATION_GENERALIZES'
    elif n_improved > len(valid) * 0.5:
        verdict = 'PARTIAL_GENERALIZATION'
    else:
        verdict = 'OVERFITTING'

    print(f"\n  ✓ EXP-1858 verdict: {verdict}")

    # Figure
    if HAS_MPL and figures_dir and valid:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        names = [r['patient'] for r in valid]
        pcts = [r['pct_improvement'] for r in valid]
        colors = ['#4CAF50' if p > 0 else '#F44336' for p in pcts]
        ax.bar(names, pcts, color=colors)
        ax.axhline(0, color='k', linewidth=0.5)
        ax.set_ylabel('Improvement on Held-Out Half (%)')
        ax.set_title(f'EXP-1858: Temporal Validation ({n_improved}/{len(valid)} generalize)')

        ax = axes[1]
        tirs = [r['tir'] for r in valid]
        tbrs = [r['tbr'] for r in valid]
        isf_scales = [r['estimated_isf_scale'] for r in valid]
        scatter = ax.scatter(isf_scales, tirs, c=tbrs, cmap='RdYlGn_r', s=80, edgecolors='k')
        for i, r in enumerate(valid):
            ax.annotate(r['patient'], (r['estimated_isf_scale'], r['tir']),
                       fontsize=8, ha='center', va='bottom')
        plt.colorbar(scatter, ax=ax, label='TBR %')
        ax.set_xlabel('Estimated ISF Scale')
        ax.set_ylabel('Time in Range (%)')
        ax.set_title('EXP-1858: ISF Estimate vs Glucose Quality')

        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'harmonic-fig08-temporal-validation.png'), dpi=150)
        plt.close()
        print(f"  → Saved harmonic-fig08-temporal-validation.png")

    return {
        'experiment': 'EXP-1858',
        'title': 'Temporal Validation',
        'verdict': verdict,
        'mean_pct_improvement': round(mean_pct, 1),
        'n_improved': n_improved,
        'improvement_tir_correlation': round(float(corr_tir), 3) if not np.isnan(corr_tir) else None,
        'per_patient': results,
    }


# ===========================================================================
# Main
# ===========================================================================

EXPERIMENTS = [
    ('EXP-1851', exp_1851),
    ('EXP-1852', exp_1852),
    ('EXP-1853', exp_1853),
    ('EXP-1854', exp_1854),
    ('EXP-1855', exp_1855),
    ('EXP-1856', exp_1856),
    ('EXP-1857', exp_1857),
    ('EXP-1858', exp_1858),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--only', type=str, help='Run only this experiment (e.g., EXP-1851)')
    args = parser.parse_args()

    figures_dir = 'docs/60-research/figures' if args.figures else None
    if figures_dir:
        os.makedirs(figures_dir, exist_ok=True)

    print("=" * 70)
    print("EXP-1851–1858: Harmonic + Context Therapy Estimation")
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

    # Save results
    out_path = 'externals/experiments/exp-1851_harmonic_therapy.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Results saved to {out_path}")

    # Synthesis
    print(f"\n{'=' * 70}")
    print("SYNTHESIS: Harmonic + Context Therapy Estimation")
    print(f"{'=' * 70}")
    for exp_id, result in all_results.items():
        verdict = result.get('verdict', 'N/A')
        print(f"  {exp_id}: {verdict}")

    print(f"\n✓ All experiments complete")


if __name__ == '__main__':
    main()
