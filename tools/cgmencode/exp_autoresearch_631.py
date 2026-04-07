#!/usr/bin/env python3
"""EXP-631-640: Model refinement, clinical validation, multi-step horizons.

Ridge-tuned joint model, feature selection, hypo alert validation,
multi-step prediction, and production pipeline benchmarking.
"""

import argparse, json, sys, time, warnings
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
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    df = p['df']; pk = p.get('pk')
    if pk is None: return None
    sd = compute_supply_demand(df, pk)
    bg = df[_bg_col(df)].values.astype(float)
    n = len(bg)
    supply = sd['supply']; demand = sd['demand']
    hepatic = sd.get('hepatic', np.zeros(n))
    carb_supply = sd.get('carb_supply', np.zeros(n))
    net = sd.get('net', supply - demand)
    flux_pred = sd.get('sum_flux', net)

    valid = np.isfinite(bg)
    bg_v = bg[valid]; dbg_v = np.diff(bg_v)
    dbg = np.full(n, np.nan)
    vi = np.where(valid)[0]
    dbg[vi[1:]] = dbg_v

    resid = dbg - flux_pred
    split = int(n * train_frac)

    X_ar = np.column_stack([np.roll(resid, i+1) for i in range(ar_order)])
    mask = np.isfinite(X_ar).all(axis=1) & np.isfinite(resid)
    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < ar_order + 1: return None

    XtX = X_ar[train_mask].T @ X_ar[train_mask]
    Xty = X_ar[train_mask].T @ resid[train_mask]
    ar_coef = np.linalg.solve(XtX + 1e-6 * np.eye(ar_order), Xty)
    ar_pred = np.full(n, 0.0)
    ar_ok = np.isfinite(X_ar).all(axis=1)
    ar_pred[ar_ok] = X_ar[ar_ok] @ ar_coef

    combined = flux_pred + ar_pred
    return {
        'bg': bg, 'dbg': dbg, 'flux_pred': flux_pred, 'ar_pred': ar_pred,
        'combined': combined, 'resid': dbg - combined, 'valid': valid,
        'supply': supply, 'demand': demand, 'hepatic': hepatic,
        'carb_supply': carb_supply, 'net': net, 'split': split, 'n': n,
    }


def _build_joint_features(bg, demand, flux_resid, ar_order=6):
    """Build joint NL+AR feature matrix."""
    n = len(bg)
    X_ar = np.column_stack([np.roll(flux_resid, i+1) for i in range(ar_order)])
    bg_c = bg - 120
    bg2 = bg_c**2 / 10000
    dem2 = demand**2 / 100
    bg_dem = bg_c * demand / 1000
    sig_bg = 1.0 / (1.0 + np.exp(-bg_c / 30))
    return np.column_stack([X_ar, bg2, dem2, bg_dem, sig_bg])


def _fit_joint(X, y, split, lam=1e-4):
    """Fit joint model with ridge regularization."""
    n = len(y)
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    train_mask = mask.copy(); train_mask[split:] = False
    if train_mask.sum() < X.shape[1] + 1:
        return np.zeros(X.shape[1]), mask
    XtX = X[train_mask].T @ X[train_mask]
    Xty = X[train_mask].T @ y[train_mask]
    coef = np.linalg.solve(XtX + lam * np.eye(X.shape[1]), Xty)
    return coef, mask


def _eval_r2(actual, pred, mask):
    """Compute R² on masked indices."""
    if mask.sum() < 5: return np.nan
    ss_res = np.sum((actual[mask] - pred[mask])**2)
    ss_tot = np.sum((actual[mask] - np.mean(actual[mask]))**2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


# ── Experiments ─────────────────────────────────────────────────────────────

def exp_631_ridge_tuned(patients, detail=False):
    """EXP-631: Cross-validate ridge regularization for joint NL+AR model."""
    results = []
    lambdas = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 1.0, 10.0]

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']
        demand = fa['demand']

        X = _build_joint_features(bg, demand, flux_resid)
        mask = np.isfinite(X).all(axis=1) & np.isfinite(flux_resid)

        # 3-fold CV on training data
        train_idx = np.where(mask & (np.arange(n) < split))[0]
        if len(train_idx) < 100: continue

        fold_size = len(train_idx) // 3
        best_lam = 1e-4; best_cv_r2 = -np.inf

        for lam in lambdas:
            cv_r2s = []
            for fold in range(3):
                val_start = fold * fold_size
                val_end = val_start + fold_size
                val_idx = train_idx[val_start:val_end]
                tr_idx = np.concatenate([train_idx[:val_start], train_idx[val_end:]])

                XtX = X[tr_idx].T @ X[tr_idx]
                Xty = X[tr_idx].T @ flux_resid[tr_idx]
                coef = np.linalg.solve(XtX + lam * np.eye(X.shape[1]), Xty)

                pred = X[val_idx] @ coef
                actual = flux_resid[val_idx]
                ss_res = np.sum((actual - pred)**2)
                ss_tot = np.sum((actual - np.mean(actual))**2)
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0
                cv_r2s.append(r2)

            mean_cv = np.mean(cv_r2s)
            if mean_cv > best_cv_r2:
                best_cv_r2 = mean_cv; best_lam = lam

        # Retrain with best lambda and evaluate on test
        coef, _ = _fit_joint(X, flux_resid, split, lam=best_lam)
        test_mask = mask.copy(); test_mask[:split] = False
        pred = np.zeros(n)
        ok = np.isfinite(X).all(axis=1)
        pred[ok] = X[ok] @ coef
        r2_test = _eval_r2(flux_resid, pred, test_mask)

        # Compare with default lambda
        coef_default, _ = _fit_joint(X, flux_resid, split, lam=1e-4)
        pred_default = np.zeros(n)
        pred_default[ok] = X[ok] @ coef_default
        r2_default = _eval_r2(flux_resid, pred_default, test_mask)

        results.append({
            'patient': p['name'],
            'best_lambda': best_lam, 'cv_r2': round(best_cv_r2, 4),
            'r2_tuned': round(r2_test, 4), 'r2_default': round(r2_default, 4),
            'delta': round(r2_test - r2_default, 4),
        })

    improved = sum(1 for r in results if r['delta'] > 0)
    mean_delta = np.mean([r['delta'] for r in results]) if results else 0
    common_lambda = max(set(r['best_lambda'] for r in results), key=lambda x: sum(1 for r in results if r['best_lambda'] == x)) if results else 1e-4

    return {
        'name': 'Ridge-Tuned Joint Model',
        'summary': f"Tuning improves {improved}/{len(results)}, ΔR²={mean_delta:.4f}, "
                   f"most common λ={common_lambda}",
        'improved': improved, 'total': len(results),
        'mean_delta': round(mean_delta, 4),
        'common_lambda': common_lambda,
        'patients': results,
    }


def exp_632_feature_selection(patients, detail=False):
    """EXP-632: LASSO-style feature importance for the 10-feature joint model."""
    results = []
    feature_names = ['AR1', 'AR2', 'AR3', 'AR4', 'AR5', 'AR6',
                     'BG²', 'demand²', 'BG×demand', 'σ(BG)']

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']
        demand = fa['demand']

        X = _build_joint_features(bg, demand, flux_resid)
        mask = np.isfinite(X).all(axis=1) & np.isfinite(flux_resid)
        train_mask = mask.copy(); train_mask[split:] = False
        test_mask = mask.copy(); test_mask[:split] = False

        if train_mask.sum() < 20 or test_mask.sum() < 20: continue

        # Full model
        coef_full, _ = _fit_joint(X, flux_resid, split, lam=1e-4)
        pred_full = np.zeros(n); ok = np.isfinite(X).all(axis=1)
        pred_full[ok] = X[ok] @ coef_full
        r2_full = _eval_r2(flux_resid, pred_full, test_mask)

        # Drop-one feature importance
        importances = []
        for f in range(10):
            X_drop = np.delete(X, f, axis=1)
            coef_drop, _ = _fit_joint(X_drop, flux_resid, split, lam=1e-4)
            pred_drop = np.zeros(n)
            ok_drop = np.isfinite(X_drop).all(axis=1)
            pred_drop[ok_drop] = X_drop[ok_drop] @ coef_drop
            r2_drop = _eval_r2(flux_resid, pred_drop, test_mask)
            importances.append(r2_full - r2_drop)

        # AR-only vs NL-only
        X_ar = X[:, :6]
        coef_ar, _ = _fit_joint(X_ar, flux_resid, split, lam=1e-4)
        pred_ar = np.zeros(n); ok_ar = np.isfinite(X_ar).all(axis=1)
        pred_ar[ok_ar] = X_ar[ok_ar] @ coef_ar
        r2_ar = _eval_r2(flux_resid, pred_ar, test_mask)

        X_nl = X[:, 6:]
        coef_nl, _ = _fit_joint(X_nl, flux_resid, split, lam=1e-4)
        pred_nl = np.zeros(n); ok_nl = np.isfinite(X_nl).all(axis=1)
        pred_nl[ok_nl] = X_nl[ok_nl] @ coef_nl
        r2_nl = _eval_r2(flux_resid, pred_nl, test_mask)

        results.append({
            'patient': p['name'], 'r2_full': round(r2_full, 4),
            'r2_ar_only': round(r2_ar, 4), 'r2_nl_only': round(r2_nl, 4),
            'importances': {feature_names[i]: round(importances[i], 4) for i in range(10)},
            'most_important': feature_names[np.argmax(importances)],
            'least_important': feature_names[np.argmin(importances)],
        })

    # Population average importances
    avg_imp = {}
    for f in feature_names:
        vals = [r['importances'][f] for r in results if f in r['importances']]
        avg_imp[f] = round(np.mean(vals), 4) if vals else 0

    sorted_imp = sorted(avg_imp.items(), key=lambda x: x[1], reverse=True)

    return {
        'name': 'Feature Selection',
        'summary': f"Top: {sorted_imp[0][0]}={sorted_imp[0][1]}, "
                   f"Bottom: {sorted_imp[-1][0]}={sorted_imp[-1][1]}",
        'avg_importances': avg_imp,
        'ranking': [f[0] for f in sorted_imp],
        'patients': results,
    }


def exp_633_ar_order_sweep(patients, detail=False):
    """EXP-633: Sweep AR order (1-12) per patient to find optimal."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']
        demand = fa['demand']

        best_order = 6; best_r2 = -np.inf
        order_r2s = {}

        for order in range(1, 13):
            X = _build_joint_features(bg, demand, flux_resid, ar_order=order)
            mask = np.isfinite(X).all(axis=1) & np.isfinite(flux_resid)
            test_mask = mask.copy(); test_mask[:split] = False

            if mask.sum() < X.shape[1] + 10: continue

            coef, _ = _fit_joint(X, flux_resid, split, lam=1e-4)
            pred = np.zeros(n); ok = np.isfinite(X).all(axis=1)
            pred[ok] = X[ok] @ coef
            r2 = _eval_r2(flux_resid, pred, test_mask)
            order_r2s[order] = round(r2, 4)

            if r2 > best_r2:
                best_r2 = r2; best_order = order

        results.append({
            'patient': p['name'],
            'best_order': best_order,
            'best_r2': round(best_r2, 4),
            'r2_at_6': order_r2s.get(6, np.nan),
            'delta_vs_6': round(best_r2 - order_r2s.get(6, best_r2), 4),
            'order_r2s': order_r2s,
        })

    orders = [r['best_order'] for r in results]
    mode_order = max(set(orders), key=orders.count)
    mean_delta = np.mean([r['delta_vs_6'] for r in results])

    return {
        'name': 'AR Order Sweep',
        'summary': f"Most common optimal: AR({mode_order}), mean Δ vs AR(6)={mean_delta:.4f}",
        'mode_order': mode_order, 'mean_delta_vs_6': round(mean_delta, 4),
        'patients': results,
    }


def exp_634_hypo_alert_specificity(patients, detail=False):
    """EXP-634: Measure false positive rate of BG<110+falling hypo alert."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, n, split = fa['bg'], fa['dbg'], fa['n'], fa['split']

        # Only evaluate on test data
        tp = 0; fp = 0; fn = 0; tn = 0

        for i in range(split + 6, n):
            if not np.isfinite(bg[i]): continue
            bg_30 = bg[max(i-6, 0)]
            slope = np.nanmean(dbg[max(i-6, 0):i]) if np.any(np.isfinite(dbg[max(i-6, 0):i])) else 0

            alert = np.isfinite(bg_30) and bg_30 < 110 and slope < 0
            hypo = bg[i] < 70

            if alert and hypo: tp += 1
            elif alert and not hypo: fp += 1
            elif not alert and hypo: fn += 1
            else: tn += 1

        total = tp + fp + fn + tn
        if total < 100: continue

        precision = tp / (tp + fp) if tp + fp > 0 else 0
        recall = tp / (tp + fn) if tp + fn > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0
        fpr = fp / (fp + tn) if fp + tn > 0 else 0

        # FP per week
        n_days = (n - split) / 288
        fp_per_week = fp / (n_days / 7) if n_days > 0 else 0

        results.append({
            'patient': p['name'],
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(f1, 3), 'fpr': round(fpr, 4),
            'fp_per_week': round(fp_per_week, 1),
        })

    mean_f1 = np.mean([r['f1'] for r in results])
    mean_fpr = np.mean([r['fpr'] for r in results])
    mean_fp_wk = np.mean([r['fp_per_week'] for r in results])

    return {
        'name': 'Hypo Alert Specificity',
        'summary': f"Mean F1={mean_f1:.3f}, FPR={mean_fpr:.4f}, "
                   f"FP/week={mean_fp_wk:.1f}",
        'mean_f1': round(mean_f1, 3), 'mean_fpr': round(mean_fpr, 4),
        'mean_fp_per_week': round(mean_fp_wk, 1),
        'patients': results,
    }


def exp_635_stacking_detection(patients, detail=False):
    """EXP-635: Real-time stacking detection — IOB threshold before correction."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, demand, n = fa['bg'], fa['demand'], fa['n']
        carb_supply = fa['carb_supply']

        demand_thresh = np.percentile(demand[demand > 0], 70) if (demand > 0).sum() > 10 else 1

        # Find correction events
        corrections = []
        i = 0
        while i < n - 24:
            if demand[i] > demand_thresh and bg[i] > 160 and carb_supply[i] < 0.5 and np.isfinite(bg[i]):
                # IOB proxy: demand in prior 3h
                iob = np.mean(demand[max(0, i-36):i])
                bg_2h = bg[min(i+24, n-1)] if np.isfinite(bg[min(i+24, n-1)]) else np.nan
                success = 1 if np.isfinite(bg_2h) and bg_2h < 150 else 0
                corrections.append({'iob': iob, 'success': success, 'bg_start': bg[i]})
                i += 24
            else:
                i += 1

        if len(corrections) < 20: continue

        # Find IOB threshold that maximizes stacking detection
        iobs = [c['iob'] for c in corrections]
        successes = [c['success'] for c in corrections]

        best_thresh = np.median(iobs); best_diff = 0
        for pct in range(20, 81, 5):
            thresh = np.percentile(iobs, pct)
            low_iob = [s for c, s in zip(corrections, successes) if c['iob'] < thresh]
            high_iob = [s for c, s in zip(corrections, successes) if c['iob'] >= thresh]
            if len(low_iob) > 5 and len(high_iob) > 5:
                diff = np.mean(low_iob) - np.mean(high_iob)
                if diff > best_diff:
                    best_diff = diff; best_thresh = thresh

        low = [c for c in corrections if c['iob'] < best_thresh]
        high = [c for c in corrections if c['iob'] >= best_thresh]

        results.append({
            'patient': p['name'],
            'n_corrections': len(corrections),
            'iob_threshold': round(best_thresh, 2),
            'low_iob_success': round(np.mean([c['success'] for c in low]), 3) if low else 0,
            'high_iob_success': round(np.mean([c['success'] for c in high]), 3) if high else 0,
            'success_difference': round(best_diff, 3),
            'stacking_detectable': best_diff > 0.05,
        })

    detectable = sum(1 for r in results if r['stacking_detectable'])
    mean_diff = np.mean([r['success_difference'] for r in results]) if results else 0

    return {
        'name': 'Stacking Detection',
        'summary': f"Stacking detectable in {detectable}/{len(results)} patients, "
                   f"mean success diff={mean_diff:.3f}",
        'detectable': detectable, 'total': len(results),
        'mean_success_diff': round(mean_diff, 3),
        'patients': results,
    }


def exp_636_score_change_detection(patients, detail=False):
    """EXP-636: Bootstrap CI on weekly scores for significant change detection."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, n = fa['bg'], fa['n']
        demand = fa['demand']; carb_supply = fa['carb_supply']

        steps_per_week = 7 * 288
        n_weeks = n // steps_per_week
        if n_weeks < 4: continue

        weekly_scores = []
        for w in range(n_weeks):
            s = w * steps_per_week; e = s + steps_per_week
            bg_w = bg[s:e]
            valid = bg_w[np.isfinite(bg_w)]
            if len(valid) < 100: continue

            tir = np.mean((valid >= 70) & (valid <= 180))
            tbr = np.mean(valid < 70)
            cv = np.std(valid) / np.mean(valid) if np.mean(valid) > 0 else 1
            tar = np.mean(valid > 180)

            d_w = demand[s:e]
            d_thresh = np.percentile(d_w[d_w > 0], 80) if (d_w > 0).sum() > 10 else 1
            peaks = np.where(d_w > d_thresh)[0]
            stacking = np.mean(np.diff(peaks) * 5 < 120) if len(peaks) > 1 else 0

            score = tir * 40 + (1-tbr)*20 + (1-min(cv,0.5)/0.5)*20 + (1-min(stacking,0.5)/0.5)*10 + (1-min(tar,0.5)/0.5)*10
            weekly_scores.append(score)

        if len(weekly_scores) < 4: continue

        # Bootstrap CI for each week
        n_boot = 200
        cis = []
        for i, score in enumerate(weekly_scores):
            # Resample neighboring weeks (±2) for CI
            neighborhood = weekly_scores[max(0,i-2):i+3]
            boots = [np.mean(np.random.choice(neighborhood, len(neighborhood), replace=True)) for _ in range(n_boot)]
            ci_lo, ci_hi = np.percentile(boots, [5, 95])
            cis.append((round(ci_lo, 1), round(ci_hi, 1)))

        # Detect significant changes (non-overlapping CIs)
        sig_changes = 0
        for i in range(1, len(cis)):
            if cis[i][0] > cis[i-1][1] or cis[i][1] < cis[i-1][0]:
                sig_changes += 1

        ci_widths = [c[1] - c[0] for c in cis]

        results.append({
            'patient': p['name'],
            'n_weeks': len(weekly_scores),
            'sig_changes': sig_changes,
            'mean_score': round(np.mean(weekly_scores), 1),
            'score_sd': round(np.std(weekly_scores), 1),
            'mean_ci_width': round(np.mean(ci_widths), 1),
        })

    total_changes = sum(r['sig_changes'] for r in results)
    mean_ci = np.mean([r['mean_ci_width'] for r in results])

    return {
        'name': 'Score Change Detection',
        'summary': f"Total significant changes: {total_changes}, mean CI width={mean_ci:.1f}",
        'total_significant_changes': total_changes,
        'mean_ci_width': round(mean_ci, 1),
        'patients': results,
    }


def exp_637_multi_step(patients, detail=False):
    """EXP-637: Multi-step prediction (1-6 steps = 5-30 minutes ahead)."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']; flux_pred = fa['flux_pred']
        demand = fa['demand']

        X = _build_joint_features(bg, demand, flux_resid)
        coef, mask = _fit_joint(X, flux_resid, split)

        # Multi-step: iterate predictions
        horizons = [1, 2, 3, 6, 12]  # steps (5, 10, 15, 30, 60 min)
        horizon_mae = {}

        for h in horizons:
            errors = []
            for i in range(split, n - h):
                if not np.isfinite(bg[i]) or not np.isfinite(bg[i+h]): continue

                # Simulate h steps of prediction
                bg_sim = bg[i]
                for step in range(h):
                    t = i + step
                    if t >= n: break
                    # Use flux prediction + model correction
                    change = flux_pred[t]
                    if np.isfinite(X[t]).all():
                        change += X[t] @ coef
                    bg_sim += change

                errors.append(abs(bg[i+h] - bg_sim))

            if errors:
                horizon_mae[h] = round(np.mean(errors), 2)

        # Naive persistence MAE at each horizon
        naive_mae = {}
        for h in horizons:
            errs = []
            for i in range(split, n - h):
                if np.isfinite(bg[i]) and np.isfinite(bg[i+h]):
                    errs.append(abs(bg[i+h] - bg[i]))
            if errs:
                naive_mae[h] = round(np.mean(errs), 2)

        skills = {}
        for h in horizons:
            if h in horizon_mae and h in naive_mae and naive_mae[h] > 0:
                skills[h] = round(1.0 - horizon_mae[h] / naive_mae[h], 4)

        results.append({
            'patient': p['name'],
            'model_mae': horizon_mae,
            'naive_mae': naive_mae,
            'skills': skills,
        })

    # Average across patients
    avg_skills = {}
    for h in [1, 2, 3, 6, 12]:
        vals = [r['skills'].get(h, np.nan) for r in results if h in r['skills']]
        avg_skills[h] = round(np.mean(vals), 4) if vals else np.nan

    return {
        'name': 'Multi-Step Prediction',
        'summary': ', '.join(f"{h*5}min: skill={avg_skills.get(h, 'N/A')}" for h in [1, 2, 3, 6, 12]),
        'avg_skills': avg_skills,
        'patients': results,
    }


def exp_638_horizon_kalman(patients, detail=False):
    """EXP-638: Kalman tuned for different prediction horizons."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']; flux_pred = fa['flux_pred']
        demand = fa['demand']

        X = _build_joint_features(bg, demand, flux_resid)
        coef, _ = _fit_joint(X, flux_resid, split)

        pred = flux_pred.copy()
        ok = np.isfinite(X).all(axis=1)
        pred[ok] += X[ok] @ coef

        train_resid = dbg[:split] - pred[:split]
        base_var = np.nanvar(train_resid[np.isfinite(train_resid)])

        # Test different Q/R ratios for different horizons
        horizons = {'5min': 1, '15min': 3, '30min': 6, '60min': 12}
        q_fracs = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7]

        horizon_results = {}
        for horizon_name, h in horizons.items():
            best_mae = np.inf; best_q = 0.2

            for qf in q_fracs:
                rf = 1.0 - qf
                Q = base_var * qf; R = base_var * rf
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

                # Evaluate at horizon h
                errors = []
                for i in range(split, n - h):
                    if np.isfinite(preds[i]) and np.isfinite(bg[i+h]):
                        errors.append(abs(bg[i+h] - preds[i]))

                if errors:
                    mae = np.mean(errors)
                    if mae < best_mae:
                        best_mae = mae; best_q = qf

            horizon_results[horizon_name] = {
                'best_q_frac': best_q, 'mae': round(best_mae, 2),
            }

        results.append({
            'patient': p['name'],
            'horizons': horizon_results,
        })

    # Average
    avg_horizons = {}
    for h_name in ['5min', '15min', '30min', '60min']:
        maes = [r['horizons'][h_name]['mae'] for r in results if h_name in r['horizons']]
        qs = [r['horizons'][h_name]['best_q_frac'] for r in results if h_name in r['horizons']]
        avg_horizons[h_name] = {
            'mean_mae': round(np.mean(maes), 2) if maes else np.nan,
            'common_q': max(set(qs), key=qs.count) if qs else 0.2,
        }

    return {
        'name': 'Horizon-Tuned Kalman',
        'summary': ', '.join(f"{k}: MAE={v['mean_mae']}, Q={v['common_q']}" for k, v in avg_horizons.items()),
        'horizons': avg_horizons,
        'patients': results,
    }


def exp_639_streaming_score(patients, detail=False):
    """EXP-639: Online streaming score with exponential moving average."""
    results = []

    for p in patients:
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        bg, n = fa['bg'], fa['n']
        demand = fa['demand']

        valid_bg = bg[np.isfinite(bg)]
        if len(valid_bg) < 1000: continue

        # Compute streaming metrics with EMA
        alpha = 2 / (288 * 7 + 1)  # 7-day EMA

        ema_tir = 0.7; ema_tbr = 0.02; ema_cv = 0.3
        streaming_scores = []

        window = 288  # 1-day lookback for instantaneous metrics
        for i in range(window, n, 12):  # every hour
            w = bg[i-window:i]
            valid = w[np.isfinite(w)]
            if len(valid) < 50: continue

            tir = np.mean((valid >= 70) & (valid <= 180))
            tbr = np.mean(valid < 70)
            cv = np.std(valid) / np.mean(valid) if np.mean(valid) > 0 else 0.5

            ema_tir = alpha * tir + (1 - alpha) * ema_tir
            ema_tbr = alpha * tbr + (1 - alpha) * ema_tbr
            ema_cv = alpha * cv + (1 - alpha) * ema_cv

            score = ema_tir * 40 + (1 - ema_tbr) * 20 + (1 - min(ema_cv, 0.5)/0.5) * 20 + 20  # simplified
            streaming_scores.append(score)

        if len(streaming_scores) < 24: continue

        # Compare streaming with batch
        batch_score = np.mean((valid_bg >= 70) & (valid_bg <= 180)) * 40 + (1 - np.mean(valid_bg < 70)) * 20 + (1 - min(np.std(valid_bg)/np.mean(valid_bg), 0.5)/0.5) * 20 + 20

        scores_arr = np.array(streaming_scores)
        final_streaming = scores_arr[-1]
        mean_streaming = np.mean(scores_arr)

        results.append({
            'patient': p['name'],
            'batch_score': round(batch_score, 1),
            'final_streaming': round(final_streaming, 1),
            'mean_streaming': round(mean_streaming, 1),
            'streaming_sd': round(np.std(scores_arr), 1),
            'delta_batch_streaming': round(final_streaming - batch_score, 1),
            'n_updates': len(streaming_scores),
        })

    mean_delta = np.mean([r['delta_batch_streaming'] for r in results]) if results else 0

    return {
        'name': 'Streaming Score',
        'summary': f"Mean Δ(streaming-batch)={mean_delta:.1f}, "
                   f"mean streaming SD={np.mean([r['streaming_sd'] for r in results]):.1f}",
        'mean_delta': round(mean_delta, 1),
        'patients': results,
    }


def exp_640_pipeline_benchmark(patients, detail=False):
    """EXP-640: End-to-end processing time benchmark."""
    results = []

    for p in patients:
        t0 = time.time()

        # Step 1: Compute flux
        fa = _compute_flux_and_ar(p)
        if fa is None: continue
        t_flux = time.time() - t0

        bg, dbg, split, n = fa['bg'], fa['dbg'], fa['split'], fa['n']
        flux_resid = dbg - fa['flux_pred']
        demand = fa['demand']

        # Step 2: Build features + fit model
        t1 = time.time()
        X = _build_joint_features(bg, demand, flux_resid)
        coef, mask = _fit_joint(X, flux_resid, split)
        t_model = time.time() - t1

        # Step 3: Predict
        t2 = time.time()
        pred = fa['flux_pred'].copy()
        ok = np.isfinite(X).all(axis=1)
        pred[ok] += X[ok] @ coef
        t_predict = time.time() - t2

        # Step 4: Kalman filter
        t3 = time.time()
        train_resid = dbg[:split] - pred[:split]
        base_var = np.nanvar(train_resid[np.isfinite(train_resid)])
        Q = base_var * 0.2; R = base_var * 0.8
        x = bg[0] if np.isfinite(bg[0]) else 120.0; P = R
        for t in range(1, n):
            x_prior = x + pred[t]; P_prior = P + Q
            if np.isfinite(bg[t]):
                K = P_prior / (P_prior + R)
                x = x_prior + K * (bg[t] - x_prior)
                P = (1 - K) * P_prior
            else:
                x = x_prior; P = P_prior
        t_kalman = time.time() - t3

        # Step 5: Score computation
        t4 = time.time()
        valid_bg = bg[np.isfinite(bg)]
        tir = np.mean((valid_bg >= 70) & (valid_bg <= 180))
        tbr = np.mean(valid_bg < 70)
        cv = np.std(valid_bg) / np.mean(valid_bg) if np.mean(valid_bg) > 0 else 1
        score = tir * 40 + (1-tbr)*20 + (1-min(cv,0.5)/0.5)*20 + 20
        t_score = time.time() - t4

        total = time.time() - t0

        results.append({
            'patient': p['name'],
            'n_steps': n,
            'n_days': round(n / 288, 0),
            't_flux': round(t_flux, 3),
            't_model': round(t_model, 3),
            't_predict': round(t_predict, 3),
            't_kalman': round(t_kalman, 3),
            't_score': round(t_score, 3),
            't_total': round(total, 3),
            'steps_per_sec': round(n / total, 0),
        })

    mean_total = np.mean([r['t_total'] for r in results])
    mean_sps = np.mean([r['steps_per_sec'] for r in results])

    return {
        'name': 'Pipeline Benchmark',
        'summary': f"Mean total={mean_total:.3f}s per patient, "
                   f"mean {mean_sps:.0f} steps/sec",
        'mean_total_sec': round(mean_total, 3),
        'mean_steps_per_sec': round(mean_sps, 0),
        'patients': results,
    }


# ── Main ────────────────────────────────────────────────────────────────────

EXPERIMENTS = [
    ('EXP-631', exp_631_ridge_tuned),
    ('EXP-632', exp_632_feature_selection),
    ('EXP-633', exp_633_ar_order_sweep),
    ('EXP-634', exp_634_hypo_alert_specificity),
    ('EXP-635', exp_635_stacking_detection),
    ('EXP-636', exp_636_score_change_detection),
    ('EXP-637', exp_637_multi_step),
    ('EXP-638', exp_638_horizon_kalman),
    ('EXP-639', exp_639_streaming_score),
    ('EXP-640', exp_640_pipeline_benchmark),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-patients', type=int, default=11)
    ap.add_argument('--detail', action='store_true')
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--exp', type=str, help='Run single experiment, e.g. EXP-631')
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
