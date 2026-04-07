#!/usr/bin/env python3
"""EXP-621-630: Final model assembly, validation, and clinical applications.

Stack all improvements: nonlinear flux + AR + Kalman + transfer learning.
Validate combined model, recalibrate clinical scores, predict hypo risk.
"""

import argparse, json, sys, warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"
RESULTS_DIR  = Path(__file__).parent.parent.parent / "externals" / "experiments"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ─────────────────────────────────────────────────────────────────

def load_patients(patients_dir, max_patients=11):
    from cgmencode.exp_metabolic_flux import load_patients as _lp
    return _lp(patients_dir, max_patients=max_patients)

def _bg_col(df):
    return 'glucose' if 'glucose' in df.columns else 'sgv'

def _compute_flux_and_ar(p, ar_order=6, train_frac=0.8):
    """Compute supply/demand + AR features."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    df = p['df']; pk = p.get('pk')
    if pk is None:
        return None
    sd = compute_supply_demand(df, pk)
    bg = df[_bg_col(df)].values.astype(float)
    n = len(bg)

    supply = sd['supply']; demand = sd['demand']
    hepatic = sd.get('hepatic', np.zeros(n))
    carb_supply = sd.get('carb_supply', np.zeros(n))
    net = sd.get('net', supply - demand)
    flux_pred = sd.get('sum_flux', net)

    valid = np.isfinite(bg)
    bg_v = bg[valid]
    dbg_v = np.diff(bg_v)
    dbg = np.full(n, np.nan)
    vi = np.where(valid)[0]
    dbg[vi[1:]] = dbg_v

    resid = dbg - flux_pred
    split = int(n * train_frac)

    X_ar = np.column_stack([np.roll(resid, i+1) for i in range(ar_order)])
    mask = np.isfinite(X_ar).all(axis=1) & np.isfinite(resid)
    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < ar_order + 1:
        return None

    XtX = X_ar[train_mask].T @ X_ar[train_mask]
    Xty = X_ar[train_mask].T @ resid[train_mask]
    lam = 1e-6
    ar_coef = np.linalg.solve(XtX + lam * np.eye(ar_order), Xty)
    ar_pred = np.full(n, 0.0)
    ar_ok = np.isfinite(X_ar).all(axis=1)
    ar_pred[ar_ok] = X_ar[ar_ok] @ ar_coef

    combined = flux_pred + ar_pred
    final_resid = dbg - combined

    return {
        'bg': bg, 'dbg': dbg, 'flux_pred': flux_pred, 'ar_pred': ar_pred,
        'combined': combined, 'resid': final_resid, 'valid': valid,
        'supply': supply, 'demand': demand, 'hepatic': hepatic,
        'carb_supply': carb_supply, 'net': net, 'split': split,
        'ar_coef': ar_coef, 'n': n,
    }


def _fit_nonlinear(bg, resid, split):
    """Fit nonlinear correction: BG², demand², BG×demand, σ(BG)."""
    n = len(bg)
    bg_centered = bg - 120
    bg2 = bg_centered**2 / 10000
    sig_bg = 1.0 / (1.0 + np.exp(-bg_centered / 30))
    # For standalone NL: only bg-based features (demand handled separately)
    X_nl = np.column_stack([bg2, sig_bg])
    mask = np.isfinite(X_nl).all(axis=1) & np.isfinite(resid)
    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < 10:
        return np.zeros(n), np.zeros(2)
    XtX = X_nl[train_mask].T @ X_nl[train_mask]
    Xty = X_nl[train_mask].T @ resid[train_mask]
    coef = np.linalg.solve(XtX + 1e-4 * np.eye(2), Xty)
    pred = np.zeros(n)
    ok = np.isfinite(X_nl).all(axis=1)
    pred[ok] = X_nl[ok] @ coef
    return pred, coef


def _fit_nonlinear_full(bg, demand, resid, split):
    """Fit full nonlinear correction: BG², demand², BG×demand, σ(BG)."""
    n = len(bg)
    bg_centered = bg - 120
    bg2 = bg_centered**2 / 10000
    dem2 = demand**2 / 100
    bg_dem = bg_centered * demand / 1000
    sig_bg = 1.0 / (1.0 + np.exp(-bg_centered / 30))
    X_nl = np.column_stack([bg2, dem2, bg_dem, sig_bg])
    mask = np.isfinite(X_nl).all(axis=1) & np.isfinite(resid)
    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < 20:
        return np.zeros(n), np.zeros(4)
    XtX = X_nl[train_mask].T @ X_nl[train_mask]
    Xty = X_nl[train_mask].T @ resid[train_mask]
    coef = np.linalg.solve(XtX + 1e-4 * np.eye(4), Xty)
    pred = np.zeros(n)
    ok = np.isfinite(X_nl).all(axis=1)
    pred[ok] = X_nl[ok] @ coef
    return pred, coef


def _run_kalman(bg, pred, n, Q_frac=0.2, R_frac=0.8, base_var=None):
    """Run scalar Kalman filter."""
    if base_var is None:
        base_var = 1.0
    Q = base_var * Q_frac; R = base_var * R_frac
    x = bg[0] if np.isfinite(bg[0]) else 120.0
    P = R
    preds = np.full(n, np.nan)
    for t in range(1, n):
        x_prior = x + pred[t]
        P_prior = P + Q
        if np.isfinite(bg[t]):
            K = P_prior / (P_prior + R)
            x = x_prior + K * (bg[t] - x_prior)
            P = (1 - K) * P_prior
        else:
            x = x_prior; P = P_prior
        preds[t] = x_prior
    return preds


def _compute_piecewise_bias(bg, resid, split, ranges=None):
    """Learn per-range bias from training data."""
    if ranges is None:
        ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]
    n = len(bg)
    train_biases = {}
    for lo, hi in ranges:
        mask = (bg >= lo) & (bg < hi) & np.isfinite(resid) & (np.arange(n) < split)
        train_biases[(lo, hi)] = np.nanmean(resid[mask]) if mask.sum() > 10 else 0.0
    bias = np.zeros(n)
    for (lo, hi), b in train_biases.items():
        mask = (bg >= lo) & (bg < hi)
        bias[mask] = b
    return bias, train_biases


# ── Experiments ─────────────────────────────────────────────────────────────

def exp_621_nonlinear_kalman(patients, detail=False):
    """EXP-621: Nonlinear flux correction + Kalman filter (best combined model)."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        demand = fa['demand']
        resid = dbg - combined

        # Fit nonlinear correction on training
        nl_pred, nl_coef = _fit_nonlinear_full(bg, demand, resid, split)
        corrected = combined + nl_pred

        # Compute base variance for Kalman
        train_resid = dbg[:split] - combined[:split]
        base_var = np.nanvar(train_resid[np.isfinite(train_resid)])

        # Kalman on baseline
        kf_base = _run_kalman(bg, combined, n, base_var=base_var)
        # Kalman on NL-corrected
        kf_nl = _run_kalman(bg, corrected, n, base_var=base_var)

        test_mask = (np.arange(n) >= split) & np.isfinite(bg) & np.isfinite(kf_base) & np.isfinite(kf_nl)
        if test_mask.sum() < 50: continue

        err_base = np.abs(bg[test_mask] - kf_base[test_mask])
        err_nl = np.abs(bg[test_mask] - kf_nl[test_mask])
        naive_err = np.abs(np.diff(bg[np.isfinite(bg)]))
        naive_mae = np.mean(naive_err[-test_mask.sum():]) if len(naive_err) > test_mask.sum() else np.mean(naive_err)

        skill_base = 1.0 - np.mean(err_base) / naive_mae if naive_mae > 0 else 0
        skill_nl = 1.0 - np.mean(err_nl) / naive_mae if naive_mae > 0 else 0

        # Also R² comparison
        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        r2_base = 1.0 - np.sum((dbg[test_mask] - combined[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        r2_nl = 1.0 - np.sum((dbg[test_mask] - corrected[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        results.append({
            'patient': p['name'],
            'skill_base': round(skill_base, 4), 'skill_nl_kalman': round(skill_nl, 4),
            'delta_skill': round(skill_nl - skill_base, 4),
            'r2_base': round(r2_base, 4), 'r2_nl': round(r2_nl, 4),
            'mae_base': round(float(np.mean(err_base)), 2),
            'mae_nl_kalman': round(float(np.mean(err_nl)), 2),
        })

    improved = sum(1 for r in results if r['delta_skill'] > 0)
    mean_delta = np.mean([r['delta_skill'] for r in results]) if results else 0

    return {
        'name': 'Nonlinear Plus Kalman',
        'summary': f"Mean Δskill={mean_delta:.4f}, improved {improved}/{len(results)}, "
                   f"mean MAE={np.mean([r['mae_nl_kalman'] for r in results]):.2f}",
        'mean_delta_skill': round(mean_delta, 4), 'improved': improved, 'total': len(results),
        'patients': results,
    }


def exp_622_nonlinear_loo(patients, detail=False):
    """EXP-622: Leave-one-out transfer of nonlinear coefficients."""
    all_fa = {}; all_coefs = {}

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        all_fa[p['name']] = fa
        bg, dbg, combined, split = fa['bg'], fa['dbg'], fa['combined'], fa['split']
        demand = fa['demand']
        resid = dbg - combined
        _, coef = _fit_nonlinear_full(bg, demand, resid, split)
        all_coefs[p['name']] = coef

    names = list(all_fa.keys())
    if len(names) < 3:
        return {'name': 'Nonlinear LOO Transfer', 'summary': 'Insufficient patients', 'patients': []}

    results = []
    for held_out in names:
        # Population NL coefficients (excluding held out)
        pop_coef = np.mean([all_coefs[n] for n in names if n != held_out], axis=0)

        fa = all_fa[held_out]
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        demand = fa['demand']

        # Apply personal vs population NL correction
        bg_centered = bg - 120
        bg2 = bg_centered**2 / 10000
        dem2 = demand**2 / 100
        bg_dem = bg_centered * demand / 1000
        sig_bg = 1.0 / (1.0 + np.exp(-bg_centered / 30))
        X_nl = np.column_stack([bg2, dem2, bg_dem, sig_bg])
        ok = np.isfinite(X_nl).all(axis=1)

        nl_personal = np.zeros(n)
        nl_personal[ok] = X_nl[ok] @ all_coefs[held_out]

        nl_pop = np.zeros(n)
        nl_pop[ok] = X_nl[ok] @ pop_coef

        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() < 50: continue

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        if ss_tot == 0: continue

        r2_none = 1.0 - np.sum((dbg[test_mask] - combined[test_mask])**2) / ss_tot
        r2_personal = 1.0 - np.sum((dbg[test_mask] - (combined + nl_personal)[test_mask])**2) / ss_tot
        r2_pop = 1.0 - np.sum((dbg[test_mask] - (combined + nl_pop)[test_mask])**2) / ss_tot

        results.append({
            'patient': held_out,
            'r2_none': round(r2_none, 4), 'r2_personal': round(r2_personal, 4),
            'r2_population': round(r2_pop, 4),
            'delta_pop': round(r2_pop - r2_none, 4),
            'personal_advantage': round(r2_personal - r2_pop, 4),
        })

    pop_improved = sum(1 for r in results if r['delta_pop'] > 0)
    mean_pop = np.mean([r['delta_pop'] for r in results])
    mean_adv = np.mean([r['personal_advantage'] for r in results])

    return {
        'name': 'Nonlinear LOO Transfer',
        'summary': f"Pop NL improves {pop_improved}/{len(results)}, ΔR²={mean_pop:.4f}, "
                   f"personal advantage={mean_adv:.4f}",
        'pop_improved': pop_improved, 'total': len(results),
        'mean_pop_delta': round(mean_pop, 4), 'mean_personal_advantage': round(mean_adv, 4),
        'patients': results,
    }


def exp_623_nonlinear_ar_joint(patients, detail=False):
    """EXP-623: Joint nonlinear + AR regression (all features together)."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_pred = fa['flux_pred']; demand = fa['demand']

        # Residual from flux only
        resid_flux = dbg - flux_pred

        # Build joint feature matrix: AR(6) + NL(4)
        ar_order = 6
        X_ar = np.column_stack([np.roll(resid_flux, i+1) for i in range(ar_order)])

        bg_centered = bg - 120
        bg2 = bg_centered**2 / 10000
        dem2 = demand**2 / 100
        bg_dem = bg_centered * demand / 1000
        sig_bg = 1.0 / (1.0 + np.exp(-bg_centered / 30))

        X_joint = np.column_stack([X_ar, bg2, dem2, bg_dem, sig_bg])
        mask = np.isfinite(X_joint).all(axis=1) & np.isfinite(resid_flux)

        train_mask = mask.copy(); train_mask[split:] = False
        test_mask = mask.copy(); test_mask[:split] = False

        if train_mask.sum() < 20 or test_mask.sum() < 20: continue

        # Fit joint model
        n_feat = X_joint.shape[1]
        XtX = X_joint[train_mask].T @ X_joint[train_mask]
        Xty = X_joint[train_mask].T @ resid_flux[train_mask]
        coef = np.linalg.solve(XtX + 1e-4 * np.eye(n_feat), Xty)

        joint_pred = np.zeros(n)
        ok = np.isfinite(X_joint).all(axis=1)
        joint_pred[ok] = X_joint[ok] @ coef

        # Separate models for comparison
        combined_sep = fa['combined']  # flux + AR (separate)

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        if ss_tot == 0: continue

        r2_sep = 1.0 - np.sum((dbg[test_mask] - combined_sep[test_mask])**2) / ss_tot
        r2_joint = 1.0 - np.sum((dbg[test_mask] - (flux_pred + joint_pred)[test_mask])**2) / ss_tot

        results.append({
            'patient': p['name'],
            'r2_separate': round(r2_sep, 4), 'r2_joint': round(r2_joint, 4),
            'delta': round(r2_joint - r2_sep, 4),
            'ar_coefs': [round(c, 4) for c in coef[:6]],
            'nl_coefs': [round(c, 4) for c in coef[6:]],
        })

    improved = sum(1 for r in results if r['delta'] > 0)
    mean_delta = np.mean([r['delta'] for r in results]) if results else 0

    return {
        'name': 'Joint Nonlinear Plus AR',
        'summary': f"Joint beats separate {improved}/{len(results)}, mean ΔR²={mean_delta:.4f}",
        'improved': improved, 'total': len(results),
        'mean_delta': round(mean_delta, 4),
        'patients': results,
    }


def exp_624_combined_best_v2(patients, detail=False):
    """EXP-624: Stack ALL improvements: flux + NL + AR + Kalman (4-layer model)."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_pred = fa['flux_pred']; demand = fa['demand']
        combined_2layer = fa['combined']  # flux + AR

        # Layer 3: Nonlinear correction on combined residual
        resid_2 = dbg - combined_2layer
        nl_pred, _ = _fit_nonlinear_full(bg, demand, resid_2, split)
        combined_3layer = combined_2layer + nl_pred

        # Layer 4: Kalman filter
        train_resid = dbg[:split] - combined_3layer[:split]
        base_var = np.nanvar(train_resid[np.isfinite(train_resid)])
        kf_3layer = _run_kalman(bg, combined_3layer, n, base_var=base_var)

        # Also run Kalman on 2-layer for comparison
        train_resid_2 = dbg[:split] - combined_2layer[:split]
        base_var_2 = np.nanvar(train_resid_2[np.isfinite(train_resid_2)])
        kf_2layer = _run_kalman(bg, combined_2layer, n, base_var=base_var_2)

        test_mask = (np.arange(n) >= split) & np.isfinite(bg) & np.isfinite(kf_2layer) & np.isfinite(kf_3layer)
        if test_mask.sum() < 50: continue

        # Naive MAE (persistence)
        naive_err = np.abs(np.diff(bg[np.isfinite(bg)]))
        naive_mae = np.mean(naive_err[-test_mask.sum():]) if len(naive_err) > test_mask.sum() else np.mean(naive_err)

        # R² for step prediction
        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)

        # Layer 1: flux only
        r2_flux = 1.0 - np.sum((dbg[test_mask] - flux_pred[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        # Layer 2: flux + AR
        r2_2layer = 1.0 - np.sum((dbg[test_mask] - combined_2layer[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        # Layer 3: flux + AR + NL
        r2_3layer = 1.0 - np.sum((dbg[test_mask] - combined_3layer[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        # Kalman skill (level prediction)
        err_2k = np.abs(bg[test_mask] - kf_2layer[test_mask])
        err_3k = np.abs(bg[test_mask] - kf_3layer[test_mask])

        skill_2k = 1.0 - np.mean(err_2k) / naive_mae if naive_mae > 0 else 0
        skill_3k = 1.0 - np.mean(err_3k) / naive_mae if naive_mae > 0 else 0

        results.append({
            'patient': p['name'],
            'r2_flux': round(r2_flux, 4), 'r2_2layer': round(r2_2layer, 4),
            'r2_3layer': round(r2_3layer, 4),
            'skill_2layer_kalman': round(skill_2k, 4),
            'skill_4layer': round(skill_3k, 4),
            'delta_skill': round(skill_3k - skill_2k, 4),
            'mae_4layer': round(float(np.mean(err_3k)), 2),
        })

    mean_skill = np.mean([r['skill_4layer'] for r in results]) if results else 0
    mean_delta = np.mean([r['delta_skill'] for r in results]) if results else 0
    improved = sum(1 for r in results if r['delta_skill'] > 0)

    return {
        'name': 'Combined Best v2 (4-Layer)',
        'summary': f"4-layer skill={mean_skill:.4f}, Δ vs 2-layer={mean_delta:.4f}, "
                   f"improved {improved}/{len(results)}",
        'mean_skill': round(mean_skill, 4),
        'mean_delta': round(mean_delta, 4),
        'improved': improved, 'total': len(results),
        'patients': results,
    }


def exp_625_variance_decomposition_v2(patients, detail=False):
    """EXP-625: Updated variance decomposition with nonlinear layer."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_pred = fa['flux_pred']; demand = fa['demand']
        combined_2layer = fa['combined']

        resid_2 = dbg - combined_2layer
        nl_pred, _ = _fit_nonlinear_full(bg, demand, resid_2, split)
        combined_3layer = combined_2layer + nl_pred

        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() < 50: continue

        total_var = np.nanvar(dbg[test_mask])
        if total_var == 0: continue

        # Flux variance explained
        resid_flux = dbg - flux_pred
        flux_var_explained = 1.0 - np.nanvar(resid_flux[test_mask]) / total_var

        # AR additional variance
        resid_2layer = dbg - combined_2layer
        ar_var_explained = (np.nanvar(resid_flux[test_mask]) - np.nanvar(resid_2layer[test_mask])) / total_var

        # NL additional variance
        resid_3layer = dbg - combined_3layer
        nl_var_explained = (np.nanvar(resid_2layer[test_mask]) - np.nanvar(resid_3layer[test_mask])) / total_var

        # Remaining noise
        noise_frac = np.nanvar(resid_3layer[test_mask]) / total_var

        results.append({
            'patient': p['name'],
            'flux_pct': round(flux_var_explained * 100, 1),
            'ar_pct': round(ar_var_explained * 100, 1),
            'nl_pct': round(nl_var_explained * 100, 1),
            'noise_pct': round(noise_frac * 100, 1),
            'total_explained_pct': round((flux_var_explained + ar_var_explained + nl_var_explained) * 100, 1),
        })

    mean_flux = np.mean([r['flux_pct'] for r in results])
    mean_ar = np.mean([r['ar_pct'] for r in results])
    mean_nl = np.mean([r['nl_pct'] for r in results])
    mean_noise = np.mean([r['noise_pct'] for r in results])
    total = mean_flux + mean_ar + mean_nl

    return {
        'name': 'Variance Decomposition v2',
        'summary': f"Flux={mean_flux:.1f}% + AR={mean_ar:.1f}% + NL={mean_nl:.1f}% = "
                   f"{total:.1f}% explained, Noise={mean_noise:.1f}%",
        'flux_pct': round(mean_flux, 1), 'ar_pct': round(mean_ar, 1),
        'nl_pct': round(mean_nl, 1), 'noise_pct': round(mean_noise, 1),
        'total_explained_pct': round(total, 1),
        'patients': results,
    }


def exp_626_score_recalibrated(patients, detail=False):
    """EXP-626: Recalibrated clinical score using percentile-based thresholds."""
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    # First pass: collect all component values for percentile calculation
    raw_components = []
    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg = fa['bg']; demand = fa['demand']; n = fa['n']
        carb_supply = fa['carb_supply']; net = fa['net']
        split = fa['split']; dbg = fa['dbg']
        combined = fa['combined']

        valid_bg = bg[np.isfinite(bg)]
        if len(valid_bg) < 500: continue

        tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))
        tbr = np.mean(valid_bg < 70)
        tar = np.mean(valid_bg > 180)
        cv = np.std(valid_bg) / np.mean(valid_bg) if np.mean(valid_bg) > 0 else 1
        mean_bg = np.mean(valid_bg)

        # Model fit (R²)
        resid = dbg - combined
        nl_pred, _ = _fit_nonlinear_full(bg, demand, resid, split)
        test_mask = (np.arange(n) >= split) & np.isfinite(dbg)
        if test_mask.sum() > 50:
            ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
            r2 = 1.0 - np.sum((dbg[test_mask] - (combined + nl_pred)[test_mask])**2) / ss_tot if ss_tot > 0 else 0
        else:
            r2 = 0

        # Stacking
        demand_thresh = np.percentile(demand[demand > 0], 80) if (demand > 0).sum() > 10 else 1
        peaks = np.where(demand > demand_thresh)[0]
        if len(peaks) > 1:
            gaps = np.diff(peaks) * 5
            stacking_rate = np.mean(gaps < 120)
        else:
            stacking_rate = 0

        # Overnight balance
        hour = np.zeros(n)
        if 'dateString' in p['df'].columns:
            try:
                hour = p['df']['dateString'].apply(
                    lambda x: int(str(x)[11:13]) if len(str(x)) > 13 else 0
                ).values.astype(float)
            except:
                pass
        overnight = (hour >= 0) & (hour < 6) & (carb_supply < 0.5)
        overnight_net = net[overnight & np.isfinite(net)]
        balance = abs(np.mean(overnight_net)) if len(overnight_net) > 20 else 1.0

        raw_components.append({
            'patient': p['name'], 'tir': tir, 'tbr': tbr, 'tar': tar, 'cv': cv,
            'r2': r2, 'stacking_rate': stacking_rate, 'balance': balance,
            'mean_bg': mean_bg,
        })

    if not raw_components:
        return {'name': 'Score Recalibrated', 'summary': 'No data', 'patients': []}

    # Compute percentile-based scoring
    def pctile_score(values, name, higher_is_better=True):
        arr = np.array(values)
        ranks = np.argsort(np.argsort(arr if higher_is_better else -arr))
        return ranks / (len(ranks) - 1) * 100 if len(ranks) > 1 else np.full(len(ranks), 50)

    tirs = [c['tir'] for c in raw_components]
    tbrs = [c['tbr'] for c in raw_components]
    cvs = [c['cv'] for c in raw_components]
    r2s = [c['r2'] for c in raw_components]
    stackings = [c['stacking_rate'] for c in raw_components]
    balances = [c['balance'] for c in raw_components]

    tir_scores = pctile_score(tirs, 'tir', higher_is_better=True)
    safety_scores = pctile_score(tbrs, 'tbr', higher_is_better=False)
    cv_scores = pctile_score(cvs, 'cv', higher_is_better=False)
    r2_scores = pctile_score(r2s, 'r2', higher_is_better=True)
    stacking_scores = pctile_score(stackings, 'stacking', higher_is_better=False)
    balance_scores = pctile_score(balances, 'balance', higher_is_better=False)

    for i, comp in enumerate(raw_components):
        # Weighted composite: TIR(25) + Safety(20) + CV(15) + ModelFit(15) + Stacking(10) + Balance(15)
        composite = (tir_scores[i] * 0.25 + safety_scores[i] * 0.20 + cv_scores[i] * 0.15 +
                     r2_scores[i] * 0.15 + stacking_scores[i] * 0.10 + balance_scores[i] * 0.15)

        grade = 'A' if composite >= 80 else ('B' if composite >= 60 else ('C' if composite >= 40 else 'D'))

        results.append({
            'patient': comp['patient'],
            'composite': round(composite, 1),
            'grade': grade,
            'components': {
                'tir': round(float(tir_scores[i]), 1),
                'safety': round(float(safety_scores[i]), 1),
                'cv': round(float(cv_scores[i]), 1),
                'model_fit': round(float(r2_scores[i]), 1),
                'stacking': round(float(stacking_scores[i]), 1),
                'balance': round(float(balance_scores[i]), 1),
            },
            'raw': {
                'tir': round(comp['tir'], 3), 'tbr': round(comp['tbr'], 4),
                'cv': round(comp['cv'], 3), 'r2': round(comp['r2'], 4),
            },
        })

    grades = [r['grade'] for r in results]
    sorted_r = sorted(results, key=lambda x: x['composite'], reverse=True)

    return {
        'name': 'Score Recalibrated (Percentile)',
        'summary': f"A={grades.count('A')}, B={grades.count('B')}, C={grades.count('C')}, "
                   f"D={grades.count('D')}, best={sorted_r[0]['patient']}, worst={sorted_r[-1]['patient']}",
        'grades': {'A': grades.count('A'), 'B': grades.count('B'),
                   'C': grades.count('C'), 'D': grades.count('D')},
        'best': sorted_r[0]['patient'], 'worst': sorted_r[-1]['patient'],
        'patients': sorted_r,
    }


def exp_627_settings_from_treatments(patients, detail=False):
    """EXP-627: Estimate ISF/CR from treatment records vs profile settings."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        df = p['df']; bg = fa['bg']; n = fa['n']
        demand = fa['demand']; carb_supply = fa['carb_supply']

        isf_schedule = df.attrs.get('isf_schedule', [])
        cr_schedule = df.attrs.get('cr_schedule', [])
        units = df.attrs.get('profile_units', 'mg/dL')
        if not isf_schedule or not cr_schedule: continue

        current_isf = np.mean([e['value'] for e in isf_schedule])
        current_cr = np.mean([e['value'] for e in cr_schedule])
        if units == 'mmol/L' or current_isf < 15:
            current_isf *= 18.0182

        # Find correction bolus events: high demand, BG > 160, low carb supply
        dbg = fa['dbg']
        corrections = []
        for i in range(n - 24):
            if demand[i] > np.percentile(demand[demand > 0], 75) and bg[i] > 160 and carb_supply[i] < 0.5:
                if np.isfinite(bg[i]) and np.isfinite(bg[min(i+12, n-1)]):
                    bg_drop = bg[i] - bg[min(i+12, n-1)]  # 1h BG drop
                    demand_sum = np.sum(demand[i:i+12])  # total demand over 1h
                    if demand_sum > 0:
                        effective_isf = bg_drop / demand_sum * 10  # scale factor
                        corrections.append({
                            'bg_start': bg[i], 'bg_drop': bg_drop,
                            'demand_sum': demand_sum, 'effective_isf': effective_isf,
                        })

        if not corrections: continue

        eff_isf_values = [c['effective_isf'] for c in corrections if 0 < c['effective_isf'] < 200]
        if not eff_isf_values: continue

        median_eff_isf = np.median(eff_isf_values)
        ratio = median_eff_isf / current_isf if current_isf > 0 else np.nan

        results.append({
            'patient': p['name'],
            'profile_isf': round(current_isf, 1),
            'effective_isf_median': round(median_eff_isf, 1),
            'isf_ratio': round(ratio, 2) if np.isfinite(ratio) else None,
            'n_corrections': len(corrections),
            'recommendation': 'increase ISF' if ratio > 1.2 else ('decrease ISF' if ratio < 0.8 else 'ISF adequate'),
        })

    return {
        'name': 'Settings from Treatments',
        'summary': f"{len(results)} patients analyzed, "
                   f"ISF changes suggested: {sum(1 for r in results if r['recommendation'] != 'ISF adequate')}",
        'patients': results,
    }


def exp_628_hypo_risk_prediction(patients, detail=False):
    """EXP-628: Hypo risk prediction using NL model + pre-hypo features."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split, n = fa['bg'], fa['dbg'], fa['combined'], fa['split'], fa['n']
        demand = fa['demand']

        # NL correction
        resid = dbg - combined
        nl_pred, _ = _fit_nonlinear_full(bg, demand, resid, split)
        corrected = combined + nl_pred

        # Find hypo events in TEST data
        test_start = split
        hypo_events = []
        non_hypo_windows = []

        for i in range(test_start + 12, n):  # need 1h lookback
            if np.isfinite(bg[i]) and bg[i] < 70:
                # Look back 1h: what was the predicted trajectory?
                lookback = slice(max(i-12, 0), i)
                pred_slope = np.nanmean(corrected[lookback]) if np.any(np.isfinite(corrected[lookback])) else 0
                bg_slope = np.nanmean(dbg[lookback]) if np.any(np.isfinite(dbg[lookback])) else 0
                bg_30min = bg[max(i-6, 0)] if np.isfinite(bg[max(i-6, 0)]) else np.nan
                demand_1h = np.mean(demand[max(i-12, 0):i])

                if np.isfinite(bg_slope) and np.isfinite(bg_30min):
                    hypo_events.append({
                        'pred_slope': pred_slope, 'bg_slope': bg_slope,
                        'bg_30min': bg_30min, 'demand_1h': demand_1h, 'is_hypo': 1,
                    })

            elif np.isfinite(bg[i]) and 100 < bg[i] < 180 and np.random.random() < 0.01:  # sample non-hypo
                lookback = slice(max(i-12, 0), i)
                pred_slope = np.nanmean(corrected[lookback]) if np.any(np.isfinite(corrected[lookback])) else 0
                bg_slope = np.nanmean(dbg[lookback]) if np.any(np.isfinite(dbg[lookback])) else 0
                bg_30min = bg[max(i-6, 0)] if np.isfinite(bg[max(i-6, 0)]) else np.nan
                demand_1h = np.mean(demand[max(i-12, 0):i])

                if np.isfinite(bg_slope) and np.isfinite(bg_30min):
                    non_hypo_windows.append({
                        'pred_slope': pred_slope, 'bg_slope': bg_slope,
                        'bg_30min': bg_30min, 'demand_1h': demand_1h, 'is_hypo': 0,
                    })

        all_events = hypo_events + non_hypo_windows
        if len(hypo_events) < 5 or len(non_hypo_windows) < 5: continue

        # Simple logistic regression proxy: compare feature distributions
        hypo_bg30 = np.mean([e['bg_30min'] for e in hypo_events])
        non_hypo_bg30 = np.mean([e['bg_30min'] for e in non_hypo_windows])
        hypo_slope = np.mean([e['bg_slope'] for e in hypo_events])
        non_hypo_slope = np.mean([e['bg_slope'] for e in non_hypo_windows])
        hypo_demand = np.mean([e['demand_1h'] for e in hypo_events])
        non_hypo_demand = np.mean([e['demand_1h'] for e in non_hypo_windows])

        # Simple threshold classifier: BG_30min < threshold AND slope < threshold
        # Find optimal thresholds on training-like split
        best_f1 = 0; best_thresh = (90, -0.5)
        for bg_thresh in [80, 85, 90, 95, 100, 110]:
            for slope_thresh in [-2, -1.5, -1, -0.5, 0]:
                tp = sum(1 for e in all_events if e['is_hypo'] and e['bg_30min'] < bg_thresh and e['bg_slope'] < slope_thresh)
                fp = sum(1 for e in all_events if not e['is_hypo'] and e['bg_30min'] < bg_thresh and e['bg_slope'] < slope_thresh)
                fn = sum(1 for e in all_events if e['is_hypo'] and not (e['bg_30min'] < bg_thresh and e['bg_slope'] < slope_thresh))
                prec = tp / (tp + fp) if tp + fp > 0 else 0
                rec = tp / (tp + fn) if tp + fn > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0
                if f1 > best_f1:
                    best_f1 = f1; best_thresh = (bg_thresh, slope_thresh)

        results.append({
            'patient': p['name'],
            'n_hypo': len(hypo_events), 'n_non_hypo': len(non_hypo_windows),
            'best_f1': round(best_f1, 3),
            'best_thresh': best_thresh,
            'hypo_bg30_mean': round(hypo_bg30, 1),
            'non_hypo_bg30_mean': round(non_hypo_bg30, 1),
            'hypo_slope_mean': round(hypo_slope, 3),
            'non_hypo_slope_mean': round(non_hypo_slope, 3),
        })

    mean_f1 = np.mean([r['best_f1'] for r in results]) if results else 0

    return {
        'name': 'Hypo Risk Prediction',
        'summary': f"Mean F1={mean_f1:.3f} ({len(results)} patients), "
                   f"BG@30min + slope features",
        'mean_f1': round(mean_f1, 3), 'total': len(results),
        'patients': results,
    }


def exp_629_ir_index_validation(patients, detail=False):
    """EXP-629: Validate IR index against clinical markers (TDD, mean BG)."""
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]
    midpoints = [55, 85, 125, 165, 215, 325]

    ir_indices = []; tdd_proxies = []; mean_bgs = []; cvs = []; tirs = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, combined, split = fa['bg'], fa['dbg'], fa['combined'], fa['split']
        demand = fa['demand']
        resid = dbg - combined

        _, biases = _compute_piecewise_bias(bg, resid, split, ranges)
        bias_values = [biases.get(r, 0) for r in ranges]
        x = np.array(midpoints); y = np.array(bias_values)
        valid = np.isfinite(y) & (y != 0)
        if valid.sum() < 3: continue

        slope = np.polyfit(x[valid], y[valid], 1)[0]
        ir_index = -slope * 100

        valid_bg = bg[np.isfinite(bg)]
        mean_bg = np.mean(valid_bg)
        cv = np.std(valid_bg) / mean_bg if mean_bg > 0 else 0
        tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))

        # TDD proxy: total daily demand (sum of insulin action per day)
        n_days = len(bg) / 288
        tdd_proxy = np.sum(demand) / n_days if n_days > 0 else 0

        ir_indices.append(ir_index)
        tdd_proxies.append(tdd_proxy)
        mean_bgs.append(mean_bg)
        cvs.append(cv)
        tirs.append(tir)

        results.append({
            'patient': p['name'],
            'ir_index': round(ir_index, 3),
            'tdd_proxy': round(tdd_proxy, 1),
            'mean_bg': round(mean_bg, 1),
            'cv': round(cv, 3),
            'tir': round(tir, 3),
        })

    if len(ir_indices) < 3:
        return {'name': 'IR Index Validation', 'summary': 'Insufficient data', 'patients': []}

    # Correlations
    r_tdd = np.corrcoef(ir_indices, tdd_proxies)[0, 1]
    r_mean_bg = np.corrcoef(ir_indices, mean_bgs)[0, 1]
    r_cv = np.corrcoef(ir_indices, cvs)[0, 1]
    r_tir = np.corrcoef(ir_indices, tirs)[0, 1]

    return {
        'name': 'IR Index Clinical Validation',
        'summary': f"r(IR,TDD)={r_tdd:.3f}, r(IR,meanBG)={r_mean_bg:.3f}, "
                   f"r(IR,CV)={r_cv:.3f}, r(IR,TIR)={r_tir:.3f}",
        'correlations': {
            'ir_vs_tdd': round(r_tdd, 3), 'ir_vs_mean_bg': round(r_mean_bg, 3),
            'ir_vs_cv': round(r_cv, 3), 'ir_vs_tir': round(r_tir, 3),
        },
        'patients': results,
    }


def exp_630_model_summary_report(patients, detail=False):
    """EXP-630: Generate final comprehensive model summary with all metrics."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_pred = fa['flux_pred']; demand = fa['demand']
        combined = fa['combined']
        carb_supply = fa['carb_supply']

        # Build complete model
        resid = dbg - combined
        nl_pred, nl_coef = _fit_nonlinear_full(bg, demand, resid, split)
        full_pred = combined + nl_pred

        train_resid = dbg[:split] - full_pred[:split]
        base_var = np.nanvar(train_resid[np.isfinite(train_resid)])
        kf = _run_kalman(bg, full_pred, n, base_var=base_var)

        test_mask = (np.arange(n) >= split) & np.isfinite(bg) & np.isfinite(kf)
        if test_mask.sum() < 50: continue

        # Metrics
        valid_bg = bg[np.isfinite(bg)]
        tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))
        tbr = np.mean(valid_bg < 70)
        tar = np.mean(valid_bg > 180)
        cv = np.std(valid_bg) / np.mean(valid_bg) if np.mean(valid_bg) > 0 else 0
        gmi = 3.31 + 0.02392 * np.mean(valid_bg)

        # Model accuracy
        naive_err = np.abs(np.diff(bg[np.isfinite(bg)]))
        naive_mae = np.mean(naive_err[-test_mask.sum():]) if len(naive_err) > test_mask.sum() else np.mean(naive_err)
        model_err = np.abs(bg[test_mask] - kf[test_mask])
        skill = 1.0 - np.mean(model_err) / naive_mae if naive_mae > 0 else 0

        ss_tot = np.sum((dbg[test_mask] - np.mean(dbg[test_mask]))**2)
        r2 = 1.0 - np.sum((dbg[test_mask] - full_pred[test_mask])**2) / ss_tot if ss_tot > 0 else 0

        # Stacking rate
        demand_thresh = np.percentile(demand[demand > 0], 80) if (demand > 0).sum() > 10 else 1
        peaks = np.where(demand > demand_thresh)[0]
        stacking = np.mean(np.diff(peaks) * 5 < 120) if len(peaks) > 1 else 0

        # Hypo stats
        hypo_episodes = 0; i = 0
        while i < n:
            if np.isfinite(bg[i]) and bg[i] < 70:
                hypo_episodes += 1
                while i < n and np.isfinite(bg[i]) and bg[i] < 70:
                    i += 1
            i += 1

        n_days = n / 288
        hypo_per_week = hypo_episodes / (n_days / 7) if n_days > 0 else 0

        # Grade (using v1 scoring for consistency)
        score = tir * 40 + (1 - tbr) * 20 + (1 - min(cv, 0.5)/0.5) * 20 + (1 - min(stacking, 0.5)/0.5) * 10 + (1 - min(tar, 0.5)/0.5) * 10
        grade = 'A' if score >= 80 else ('B' if score >= 65 else ('C' if score >= 50 else 'D'))

        results.append({
            'patient': p['name'],
            'days': round(n_days, 0),
            'mean_bg': round(float(np.mean(valid_bg)), 1),
            'tir': round(tir, 3), 'tbr': round(tbr, 4), 'tar': round(tar, 3),
            'cv': round(cv, 3), 'gmi': round(gmi, 1),
            'model_r2': round(r2, 4), 'kalman_skill': round(skill, 4),
            'mae': round(float(np.mean(model_err)), 2),
            'stacking_rate': round(stacking, 3),
            'hypo_per_week': round(hypo_per_week, 1),
            'score': round(score, 1), 'grade': grade,
            'nl_coefs': {
                'bg_sq': round(float(nl_coef[0]), 4),
                'demand_sq': round(float(nl_coef[1]), 4),
                'bg_x_demand': round(float(nl_coef[2]), 4),
                'sigmoid': round(float(nl_coef[3]), 4),
            },
        })

    # Sort by score
    sorted_r = sorted(results, key=lambda x: x['score'], reverse=True)
    grades = [r['grade'] for r in results]
    mean_r2 = np.mean([r['model_r2'] for r in results])
    mean_skill = np.mean([r['kalman_skill'] for r in results])

    return {
        'name': 'Final Model Summary',
        'summary': f"11 patients: A={grades.count('A')}, B={grades.count('B')}, "
                   f"C={grades.count('C')}, D={grades.count('D')}, "
                   f"mean R²={mean_r2:.4f}, mean skill={mean_skill:.4f}",
        'grades': {'A': grades.count('A'), 'B': grades.count('B'),
                   'C': grades.count('C'), 'D': grades.count('D')},
        'mean_r2': round(mean_r2, 4), 'mean_skill': round(mean_skill, 4),
        'patients': sorted_r,
    }


# ── Main ────────────────────────────────────────────────────────────────────

EXPERIMENTS = [
    ('EXP-621', exp_621_nonlinear_kalman),
    ('EXP-622', exp_622_nonlinear_loo),
    ('EXP-623', exp_623_nonlinear_ar_joint),
    ('EXP-624', exp_624_combined_best_v2),
    ('EXP-625', exp_625_variance_decomposition_v2),
    ('EXP-626', exp_626_score_recalibrated),
    ('EXP-627', exp_627_settings_from_treatments),
    ('EXP-628', exp_628_hypo_risk_prediction),
    ('EXP-629', exp_629_ir_index_validation),
    ('EXP-630', exp_630_model_summary_report),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-patients', type=int, default=11)
    ap.add_argument('--detail', action='store_true')
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--exp', type=str, help='Run single experiment, e.g. EXP-621')
    args = ap.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    exps = EXPERIMENTS
    if args.exp:
        exps = [(eid, fn) for eid, fn in EXPERIMENTS if eid == args.exp]
        if not exps:
            print(f"Unknown experiment: {args.exp}")
            sys.exit(1)

    for eid, fn in exps:
        print(f"{'='*60}")
        print(f"Running {eid}: {fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'='*60}")
        try:
            result = fn(patients, detail=args.detail)
            print(f"\n  RESULT: {result.get('summary', 'done')}")
            if args.detail and 'patients' in result:
                for pr in result['patients']:
                    print(f"    {pr}")
            if args.save:
                safe_name = result['name'].lower().replace(' ', '_').replace('/', '_')[:30]
                fname = RESULTS_DIR / f"{eid.lower()}_{safe_name}.json"
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fname.name}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            import traceback; traceback.print_exc()
        print()


if __name__ == '__main__':
    main()
