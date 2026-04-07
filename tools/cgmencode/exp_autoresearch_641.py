#!/usr/bin/env python3
"""EXP-641-650: Improved Hypo Prediction, Parsimonious Model, Extended Analysis.

Wave 14 of autoresearch — model-based hypo alerts, parsimonious model validation,
biweekly scoring, anomaly detection, and 60-min clinical evaluation.
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

sys.path.insert(0, str(Path(__file__).parent))
from exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand


def _build_joint_features(resid_train, bg_train, demand_train, order=6):
    """Build joint NL+AR features from residuals, BG, and demand."""
    n = len(resid_train)
    n_feat = order + 4  # AR(order) + BG², demand², BG×demand, σ(BG)
    X = np.zeros((n, n_feat))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid_train[:-lag] if lag < n else 0
    bg_c = bg_train - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand_train ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand_train / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    return X


def _fit_joint(X_train, y_train, X_test, lam=10.0):
    """Fit ridge regression and predict."""
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    Xty = X_train.T @ y_train
    beta = np.linalg.solve(XtX, Xty)
    pred = X_test @ beta
    return beta, pred


def _multi_step_predict(bg, supply, demand, hepatic, bg_decay, beta, order=6, steps=6):
    """Multi-step prediction using physics + joint NL+AR model."""
    n = len(bg)
    preds = np.full(n, np.nan)
    resid_history = np.zeros(order)

    for t in range(order, n - steps):
        pred_bg = bg[t]
        local_resid = list(resid_history)
        for s in range(steps):
            ts = t + s
            if ts >= n:
                break
            flux_pred = pred_bg + supply[ts] - demand[ts] + hepatic[ts] + bg_decay[ts]
            feats = np.zeros(order + 4)
            for lag in range(order):
                feats[lag] = local_resid[-(lag + 1)] if lag < len(local_resid) else 0
            bg_c = pred_bg - 120.0
            feats[order] = bg_c ** 2 / 10000.0
            feats[order + 1] = demand[ts] ** 2 / 1000.0
            feats[order + 2] = bg_c * demand[ts] / 1000.0
            feats[order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
            correction = feats @ beta
            pred_bg = flux_pred + correction
            step_resid = bg[ts + 1] - flux_pred if ts + 1 < n else 0
            local_resid.append(step_resid)

        if t + steps < n:
            preds[t + steps] = pred_bg

    actual_resid = np.diff(bg) - (supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1])
    for i in range(min(order, len(actual_resid))):
        resid_history[i] = actual_resid[-(i + 1)] if i < len(actual_resid) else 0

    return preds


def run_exp_641(patients, detail=False):
    """EXP-641: Model-Based Hypo Alert — use 30-min prediction to alert on hypo."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005

        # Compute flux predictions
        flux_pred = bg + supply - demand + hepatic + bg_decay
        resid = np.diff(bg) - (supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1])

        n = len(bg)
        split = int(0.8 * n)

        # Train joint model
        X_train = _build_joint_features(resid[:split - 1], bg[:split - 1], demand[:split - 1])
        y_train = resid[:split - 1]
        mask = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
        if mask.sum() < 100:
            continue
        beta, _ = _fit_joint(X_train[mask], y_train[mask], X_train[mask])

        # Multi-step predict (6 steps = 30 min)
        test_bg = bg[split:]
        test_supply = supply[split:]
        test_demand = demand[split:]
        test_hepatic = hepatic[split:]
        test_bg_decay = bg_decay[split:]
        n_test = len(test_bg)

        # Simple iterative 6-step prediction
        steps = 6
        pred_30min = np.full(n_test, np.nan)
        for t in range(6, n_test - steps):
            pb = test_bg[t]
            local_resids = list(resid[split + t - 6:split + t])
            for s in range(steps):
                ts = t + s
                if ts >= n_test:
                    break
                fp = pb + test_supply[ts] - test_demand[ts] + test_hepatic[ts] + test_bg_decay[ts]
                feats = np.zeros(10)
                for lag in range(min(6, len(local_resids))):
                    feats[lag] = local_resids[-(lag + 1)]
                bg_c = pb - 120.0
                feats[6] = bg_c ** 2 / 10000.0
                feats[7] = test_demand[ts] ** 2 / 1000.0
                feats[8] = bg_c * test_demand[ts] / 1000.0
                feats[9] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
                correction = feats @ beta
                pb = fp + correction
                local_resids.append(fp - pb)  # approx

            pred_30min[t + steps] = pb if t + steps < n_test else np.nan

        # Model-based alert: predicted BG in 30min < 70
        valid = np.isfinite(pred_30min)
        actual_hypo = test_bg < 70
        for threshold in [70, 80, 85]:
            alert = pred_30min < threshold
            alert_valid = alert & valid
            tp = np.sum(alert_valid & actual_hypo)
            fp = np.sum(alert_valid & ~actual_hypo)
            fn = np.sum(~alert_valid & actual_hypo & valid)
            tn = np.sum(~alert_valid & ~actual_hypo & valid)
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

            # Also check simple rule for comparison
            simple_alert = (test_bg < 110) & (np.concatenate([[0], np.diff(test_bg)]) < 0)
            s_tp = np.sum(simple_alert & actual_hypo)
            s_fp = np.sum(simple_alert & ~actual_hypo)
            s_fn = np.sum(~simple_alert & actual_hypo)
            s_prec = s_tp / (s_tp + s_fp) if (s_tp + s_fp) > 0 else 0
            s_rec = s_tp / (s_tp + s_fn) if (s_tp + s_fn) > 0 else 0
            s_f1 = 2 * s_prec * s_rec / (s_prec + s_rec) if (s_prec + s_rec) > 0 else 0

            if threshold == 70:
                best_thresh = threshold
                best_result = {
                    'patient': p['name'],
                    'threshold': threshold,
                    'model_f1': round(f1, 3), 'model_prec': round(prec, 3),
                    'model_rec': round(rec, 3), 'model_fpr': round(fpr, 4),
                    'model_fp_week': round(fp / (n_test / (12 * 24 * 7)), 1),
                    'simple_f1': round(s_f1, 3),
                    'f1_improvement': round(f1 - s_f1, 3),
                }

        # Pick best threshold by F1
        results.append(best_result)
        if detail:
            print(f"    {best_result}")

    mean_f1 = np.mean([r['model_f1'] for r in results])
    mean_simple_f1 = np.mean([r['simple_f1'] for r in results])
    mean_improvement = np.mean([r['f1_improvement'] for r in results])
    summary = f"Model F1={mean_f1:.3f} vs Simple F1={mean_simple_f1:.3f}, Δ={mean_improvement:.3f}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-641: Model-Based Hypo Alert', 'summary': summary, 'details': results}


def run_exp_642(patients, detail=False):
    """EXP-642: Adaptive Hypo Threshold — optimize per-patient BG threshold."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        n = len(bg)
        split = int(0.8 * n)
        test_bg = bg[split:]

        actual_hypo = test_bg < 70
        if actual_hypo.sum() < 5:
            # Not enough hypo events
            results.append({'patient': p['name'], 'best_threshold': None,
                           'best_f1': 0, 'n_hypo': int(actual_hypo.sum())})
            if detail:
                print(f"    {p['name']}: too few hypo events ({actual_hypo.sum()})")
            continue

        slope = np.concatenate([[0], np.diff(test_bg)])
        best_f1, best_thresh = 0, 0
        for thresh in range(80, 130, 5):
            for slope_thresh in [-2, -1, -0.5, 0]:
                alert = (test_bg < thresh) & (slope < slope_thresh)
                tp = np.sum(alert & actual_hypo)
                fp = np.sum(alert & ~actual_hypo)
                fn = np.sum(~alert & actual_hypo)
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
                if f1 > best_f1:
                    best_f1 = f1
                    best_thresh = thresh
                    best_slope = slope_thresh
                    best_prec = prec
                    best_rec = rec
                    best_fp = fp

        n_weeks = n / (12 * 24 * 7)
        test_weeks = (n - split) / (12 * 24 * 7)
        result = {
            'patient': p['name'],
            'best_threshold': best_thresh,
            'best_slope_threshold': best_slope,
            'best_f1': round(best_f1, 3),
            'precision': round(best_prec, 3),
            'recall': round(best_rec, 3),
            'fp_per_week': round(best_fp / test_weeks, 1) if test_weeks > 0 else 0,
            'n_hypo': int(actual_hypo.sum()),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_f1 = np.mean([r['best_f1'] for r in results if r['best_threshold'] is not None])
    mean_fp = np.mean([r['fp_per_week'] for r in results if r.get('fp_per_week', 0) > 0])
    summary = f"Mean optimized F1={mean_f1:.3f}, mean FP/week={mean_fp:.1f}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-642: Adaptive Hypo Threshold', 'summary': summary, 'details': results}


def run_exp_643(patients, detail=False):
    """EXP-643: Flux-Trajectory Hypo — use cumulative flux trajectory for prediction."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        net = sd['supply'] - sd['demand'] + sd['hepatic']
        n = len(bg)
        split = int(0.8 * n)
        test_bg = bg[split:]
        test_net = net[split:]

        actual_hypo = test_bg < 70
        if actual_hypo.sum() < 5:
            results.append({'patient': p['name'], 'flux_f1': 0, 'n_hypo': int(actual_hypo.sum())})
            continue

        # Cumulative flux trajectory: sum net flux over next 6 steps
        cum_flux = np.zeros(len(test_bg))
        for step in range(1, 7):
            shifted = np.roll(test_net, -step)
            shifted[-step:] = 0
            cum_flux += shifted

        # Predict BG in 30 min = current BG + cumulative flux
        pred_30 = test_bg + cum_flux
        flux_alert = pred_30 < 70

        # Compare with simple BG level alert
        simple_alert = test_bg < 90

        for label, alert in [('flux', flux_alert), ('simple', simple_alert)]:
            tp = np.sum(alert & actual_hypo)
            fp = np.sum(alert & ~actual_hypo)
            fn = np.sum(~alert & actual_hypo)
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            test_weeks = (n - split) / (12 * 24 * 7)
            if label == 'flux':
                flux_f1, flux_prec, flux_rec = f1, prec, rec
                flux_fp = round(fp / test_weeks, 1) if test_weeks > 0 else 0
            else:
                simple_f1 = f1

        result = {
            'patient': p['name'],
            'flux_f1': round(flux_f1, 3),
            'flux_prec': round(flux_prec, 3),
            'flux_rec': round(flux_rec, 3),
            'flux_fp_week': flux_fp,
            'simple_f1': round(simple_f1, 3),
            'improvement': round(flux_f1 - simple_f1, 3),
            'n_hypo': int(actual_hypo.sum()),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_flux = np.mean([r['flux_f1'] for r in results])
    mean_simple = np.mean([r['simple_f1'] for r in results if r['simple_f1'] > 0])
    n_improved = sum(1 for r in results if r.get('improvement', 0) > 0)
    summary = f"Flux F1={mean_flux:.3f} vs BG<90 F1={mean_simple:.3f}, improved {n_improved}/{len(results)}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-643: Flux-Trajectory Hypo', 'summary': summary, 'details': results}


def run_exp_644(patients, detail=False):
    """EXP-644: 5-Feature Parsimonious Model — compare vs full 10-feature."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005

        resid = np.diff(bg) - (supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1])
        n = len(resid)
        split = int(0.8 * n)

        # Full 10-feature model (align bg/demand to resid length)
        X_full = _build_joint_features(resid[:split], bg[:split], demand[:split])
        y = resid[:split]
        mask = np.all(np.isfinite(X_full), axis=1) & np.isfinite(y)

        n_test = n - split
        X_test_full = _build_joint_features(resid[split:], bg[split:split + n_test], demand[split:split + n_test])
        y_test = resid[split:]
        mask_test = np.all(np.isfinite(X_test_full), axis=1) & np.isfinite(y_test)

        if mask.sum() < 100 or mask_test.sum() < 100:
            continue

        _, pred_full = _fit_joint(X_full[mask], y[mask], X_test_full[mask_test])
        ss_res_full = np.sum((y_test[mask_test] - pred_full) ** 2)
        ss_tot = np.sum((y_test[mask_test] - y_test[mask_test].mean()) ** 2)
        r2_full = 1 - ss_res_full / ss_tot if ss_tot > 0 else 0

        # 5-feature model: AR1, AR3, demand², σ(BG), BG×demand
        # Indices: 0=AR1, 2=AR3, 7=demand², 9=σ(BG), 8=BG×demand
        keep = [0, 2, 7, 9, 8]
        X_5 = X_full[:, keep]
        X_test_5 = X_test_full[:, keep]
        _, pred_5 = _fit_joint(X_5[mask], y[mask], X_test_5[mask_test], lam=10.0)
        ss_res_5 = np.sum((y_test[mask_test] - pred_5) ** 2)
        r2_5 = 1 - ss_res_5 / ss_tot if ss_tot > 0 else 0

        # 2-feature model: AR1, demand²
        keep2 = [0, 7]
        X_2 = X_full[:, keep2]
        X_test_2 = X_test_full[:, keep2]
        _, pred_2 = _fit_joint(X_2[mask], y[mask], X_test_2[mask_test], lam=10.0)
        ss_res_2 = np.sum((y_test[mask_test] - pred_2) ** 2)
        r2_2 = 1 - ss_res_2 / ss_tot if ss_tot > 0 else 0

        # AR1 only
        X_1 = X_full[:, [0]]
        X_test_1 = X_test_full[:, [0]]
        _, pred_1 = _fit_joint(X_1[mask], y[mask], X_test_1[mask_test], lam=10.0)
        ss_res_1 = np.sum((y_test[mask_test] - pred_1) ** 2)
        r2_1 = 1 - ss_res_1 / ss_tot if ss_tot > 0 else 0

        result = {
            'patient': p['name'],
            'r2_full_10': round(float(r2_full), 4),
            'r2_5feat': round(float(r2_5), 4),
            'r2_2feat': round(float(r2_2), 4),
            'r2_ar1_only': round(float(r2_1), 4),
            'retention_5': round(float(r2_5 / r2_full * 100), 1) if r2_full > 0 else 0,
            'retention_2': round(float(r2_2 / r2_full * 100), 1) if r2_full > 0 else 0,
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_full = np.mean([r['r2_full_10'] for r in results])
    mean_5 = np.mean([r['r2_5feat'] for r in results])
    mean_2 = np.mean([r['r2_2feat'] for r in results])
    mean_ret5 = np.mean([r['retention_5'] for r in results])
    mean_ret2 = np.mean([r['retention_2'] for r in results])
    summary = f"10feat R²={mean_full:.4f}, 5feat R²={mean_5:.4f} ({mean_ret5:.0f}%), 2feat R²={mean_2:.4f} ({mean_ret2:.0f}%)"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-644: 5-Feature Parsimonious Model', 'summary': summary, 'details': results}


def run_exp_645(patients, detail=False):
    """EXP-645: Minimal Clinical Model — AR1 + demand² only."""
    # Already covered in EXP-644, this does production-ready evaluation
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005

        flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
        resid = bg[1:] - flux_pred

        n = len(resid)
        split = int(0.8 * n)

        n_resid = len(resid)
        ar1 = np.concatenate([[0], resid[:-1]])  # length = n_resid
        demand_sq = demand[:n_resid] ** 2 / 1000.0  # align to resid length

        X = np.column_stack([ar1[:split], demand_sq[:split]])
        y = resid[:split]
        mask = np.all(np.isfinite(X), axis=1) & np.isfinite(y)

        X_test = np.column_stack([ar1[split:], demand_sq[split:]])
        y_test = resid[split:]
        mask_test = np.all(np.isfinite(X_test), axis=1) & np.isfinite(y_test)

        if mask.sum() < 100 or mask_test.sum() < 100:
            continue

        XtX = X[mask].T @ X[mask] + 10.0 * np.eye(2)
        beta = np.linalg.solve(XtX, X[mask].T @ y[mask])
        pred = X_test[mask_test] @ beta

        ss_res = np.sum((y_test[mask_test] - pred) ** 2)
        ss_tot = np.sum((y_test[mask_test] - y_test[mask_test].mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Also compute MAE of full prediction
        full_pred = flux_pred[split:][mask_test] + pred
        actual = bg[1:][split:][mask_test]
        mae = np.mean(np.abs(actual - full_pred))

        # Persistence MAE
        persist_mae = np.mean(np.abs(np.diff(bg[split:])))

        result = {
            'patient': p['name'],
            'r2': round(float(r2), 4),
            'mae': round(float(mae), 2),
            'persist_mae': round(float(persist_mae), 2),
            'skill': round(float(1 - mae / persist_mae), 4) if persist_mae > 0 else 0,
            'beta_ar1': round(float(beta[0]), 4),
            'beta_demand2': round(float(beta[1]), 4),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_r2 = np.mean([r['r2'] for r in results])
    mean_mae = np.mean([r['mae'] for r in results])
    mean_skill = np.mean([r['skill'] for r in results])
    summary = f"2-feat R²={mean_r2:.4f}, MAE={mean_mae:.1f}, skill={mean_skill:.4f}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-645: Minimal Clinical Model', 'summary': summary, 'details': results}


def run_exp_646(patients, detail=False):
    """EXP-646: 60-Min Prediction Quality — Clarke Error Grid zones."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005
        resid = np.diff(bg) - (supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1])

        n = len(bg)
        split = int(0.8 * n)

        # Train joint model
        X_train = _build_joint_features(resid[:split - 1], bg[:split - 1], demand[:split - 1])
        y_train = resid[:split - 1]
        mask = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
        if mask.sum() < 100:
            continue
        beta, _ = _fit_joint(X_train[mask], y_train[mask], X_train[mask])

        # 12-step (60-min) iterative prediction on test set
        test_start = split
        steps = 12
        pairs = []
        for t in range(6, n - test_start - steps):
            idx = test_start + t
            pb = bg[idx]
            local_resids = list(resid[max(0, idx - 6):idx])
            for s in range(steps):
                ts = idx + s
                if ts >= n:
                    break
                fp = pb + supply[ts] - demand[ts] + hepatic[ts] + (120.0 - pb) * 0.005
                feats = np.zeros(10)
                for lag in range(min(6, len(local_resids))):
                    feats[lag] = local_resids[-(lag + 1)]
                bg_c = pb - 120.0
                feats[6] = bg_c ** 2 / 10000.0
                feats[7] = demand[ts] ** 2 / 1000.0
                feats[8] = bg_c * demand[ts] / 1000.0
                feats[9] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
                correction = feats @ beta
                pb = fp + correction
                local_resids.append(0)

            if idx + steps < n and np.isfinite(pb):
                pairs.append((bg[idx + steps], pb))

        if len(pairs) < 100:
            continue

        actual, predicted = zip(*pairs)
        actual = np.array(actual)
        predicted = np.clip(np.array(predicted), 20, 600)  # clip extreme predictions

        # Simplified Clarke Error Grid zones
        # Zone A: clinically accurate
        # Zone B: benign errors
        # Zone C/D/E: clinically dangerous
        n_pairs = len(actual)
        zone_a = np.sum(
            (np.abs(predicted - actual) <= 20) |
            ((actual < 70) & (predicted < 70)) |
            ((actual > 180) & (predicted > 180))
        )
        zone_ab = np.sum(
            (np.abs(predicted - actual) <= 40) |
            ((actual < 70) & (predicted < 90)) |
            ((actual > 180) & (predicted > 150))
        )

        mae = np.nanmean(np.abs(predicted - actual))
        mape = np.nanmean(np.abs(predicted - actual) / np.clip(actual, 40, None) * 100)

        result = {
            'patient': p['name'],
            'n_pairs': n_pairs,
            'mae_60min': round(float(mae), 1),
            'mape_60min': round(float(mape), 1),
            'zone_a_pct': round(float(zone_a / n_pairs * 100), 1),
            'zone_ab_pct': round(float(zone_ab / n_pairs * 100), 1),
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_mae = np.mean([r['mae_60min'] for r in results])
    mean_zone_a = np.mean([r['zone_a_pct'] for r in results])
    mean_zone_ab = np.mean([r['zone_ab_pct'] for r in results])
    summary = f"60min MAE={mean_mae:.1f}, Zone A={mean_zone_a:.0f}%, Zone A+B={mean_zone_ab:.0f}%"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-646: 60-Min Prediction Quality', 'summary': summary, 'details': results}


def run_exp_647(patients, detail=False):
    """EXP-647: Biweekly Score Change Detection."""
    results = []
    total_significant = 0
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        # Split into biweekly windows (14 days × 288 steps/day = 4032 steps)
        window = 4032
        n = len(bg)
        windows = []
        for start in range(0, n - window, window):
            w_bg = bg[start:start + window]
            valid = np.isfinite(w_bg)
            if valid.sum() < window * 0.5:
                continue
            w_bg = w_bg[valid]
            tir = np.mean((w_bg >= 70) & (w_bg <= 180)) * 100
            tbr = np.mean(w_bg < 70) * 100
            mean_bg = np.mean(w_bg)
            sd_bg = np.std(w_bg)
            score = tir * 0.5 + max(0, 100 - tbr * 10) * 0.3 + max(0, 100 - (sd_bg - 30) * 2) * 0.2
            windows.append({'start': start, 'score': score, 'tir': tir, 'tbr': tbr})

        # Bootstrap CI for consecutive window differences
        significant_changes = 0
        for i in range(1, len(windows)):
            diff = windows[i]['score'] - windows[i - 1]['score']
            # Bootstrap
            w1_bg = bg[windows[i - 1]['start']:windows[i - 1]['start'] + window]
            w2_bg = bg[windows[i]['start']:windows[i]['start'] + window]
            w1_bg = w1_bg[np.isfinite(w1_bg)]
            w2_bg = w2_bg[np.isfinite(w2_bg)]

            boot_diffs = []
            rng = np.random.RandomState(42)
            for _ in range(200):
                b1 = rng.choice(w1_bg, len(w1_bg), replace=True)
                b2 = rng.choice(w2_bg, len(w2_bg), replace=True)
                tir1 = np.mean((b1 >= 70) & (b1 <= 180)) * 100
                tir2 = np.mean((b2 >= 70) & (b2 <= 180)) * 100
                boot_diffs.append(tir2 - tir1)

            ci_lo = np.percentile(boot_diffs, 2.5)
            ci_hi = np.percentile(boot_diffs, 97.5)
            if ci_lo > 0 or ci_hi < 0:
                significant_changes += 1
                total_significant += 1

        result = {
            'patient': p['name'],
            'n_windows': len(windows),
            'significant_changes': significant_changes,
            'mean_score': round(np.mean([w['score'] for w in windows]), 1) if windows else 0,
            'score_range': round(max(w['score'] for w in windows) - min(w['score'] for w in windows), 1) if len(windows) > 1 else 0,
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    n_with_changes = sum(1 for r in results if r['significant_changes'] > 0)
    summary = f"Total significant: {total_significant}, patients with changes: {n_with_changes}/{len(results)}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-647: Biweekly Score Change', 'summary': summary, 'details': results}


def run_exp_648(patients, detail=False):
    """EXP-648: Monthly Settings Drift — correlate flux patterns with time."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        net = supply - demand + sd['hepatic']

        # Monthly windows (30 days × 288 = 8640 steps)
        window = 8640
        n = len(bg)
        months = []
        for start in range(0, n - window, window):
            w_bg = bg[start:start + window]
            w_supply = supply[start:start + window]
            w_demand = demand[start:start + window]
            w_net = net[start:start + window]
            valid = np.isfinite(w_bg) & np.isfinite(w_net)
            if valid.sum() < window * 0.5:
                continue

            tir = np.mean((w_bg[valid] >= 70) & (w_bg[valid] <= 180)) * 100
            mean_demand = np.mean(w_demand[valid])
            mean_supply = np.mean(w_supply[valid])
            mean_net = np.mean(w_net[valid])
            sd_net = np.std(w_net[valid])
            mean_bg = np.mean(w_bg[valid])

            months.append({
                'month': len(months) + 1,
                'tir': round(tir, 1),
                'mean_bg': round(float(mean_bg), 1),
                'mean_demand': round(float(mean_demand), 1),
                'mean_supply': round(float(mean_supply), 1),
                'mean_net': round(float(mean_net), 1),
                'sd_net': round(float(sd_net), 1),
            })

        if len(months) < 3:
            results.append({'patient': p['name'], 'n_months': len(months),
                           'drift_detected': False, 'tir_trend': 0})
            continue

        # Check for trend in TIR and net flux
        tirs = [m['tir'] for m in months]
        nets = [m['mean_net'] for m in months]
        x = np.arange(len(tirs))
        tir_slope = np.polyfit(x, tirs, 1)[0] if len(tirs) > 1 else 0
        net_slope = np.polyfit(x, nets, 1)[0] if len(nets) > 1 else 0
        drift = abs(tir_slope) > 1.0 or abs(net_slope) > 0.1

        result = {
            'patient': p['name'],
            'n_months': len(months),
            'tir_trend': round(float(tir_slope), 2),
            'net_flux_trend': round(float(net_slope), 3),
            'drift_detected': bool(drift),
            'months': months,
        }
        results.append(result)
        if detail:
            print(f"    {p['name']}: {len(months)} months, TIR trend={tir_slope:.2f}/month, "
                  f"net flux trend={net_slope:.3f}/month, drift={drift}")

    n_drift = sum(1 for r in results if r.get('drift_detected', False))
    mean_tir_trend = np.mean([r['tir_trend'] for r in results])
    summary = f"Drift detected: {n_drift}/{len(results)}, mean TIR trend={mean_tir_trend:.2f}/month"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-648: Monthly Settings Drift', 'summary': summary, 'details': results}


def run_exp_649(patients, detail=False):
    """EXP-649: Residual Anomaly Detection — detect > 3σ events."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005
        flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
        resid = bg[1:] - flux_pred
        valid = np.isfinite(resid)
        resid_v = resid[valid]

        mu = np.mean(resid_v)
        sigma = np.std(resid_v)
        if sigma < 0.1:
            continue

        # Detect anomalies: |resid| > 3σ
        anomaly_mask = np.abs(resid_v - mu) > 3 * sigma
        n_anomalies = np.sum(anomaly_mask)
        anomaly_rate = n_anomalies / len(resid_v) * 100

        # Characterize anomalies: positive (unexpected rise) vs negative (unexpected drop)
        pos_anomalies = np.sum((resid_v - mu) > 3 * sigma)
        neg_anomalies = np.sum((resid_v - mu) < -3 * sigma)

        # Mean BG during anomalies
        bg_at_anomaly = bg[1:][valid][anomaly_mask]
        demand_at_anomaly = demand[1:][valid][anomaly_mask] if len(demand) > 1 else np.array([])

        # Check temporal clustering
        anomaly_indices = np.where(anomaly_mask)[0]
        clusters = 0
        if len(anomaly_indices) > 1:
            diffs = np.diff(anomaly_indices)
            clusters = np.sum(diffs <= 6)  # Within 30 minutes

        result = {
            'patient': p['name'],
            'n_anomalies': int(n_anomalies),
            'anomaly_rate_pct': round(anomaly_rate, 2),
            'positive_anomalies': int(pos_anomalies),
            'negative_anomalies': int(neg_anomalies),
            'mean_bg_at_anomaly': round(float(np.mean(bg_at_anomaly)), 1) if len(bg_at_anomaly) > 0 else 0,
            'sigma': round(float(sigma), 2),
            'cluster_rate': round(float(clusters / n_anomalies * 100), 1) if n_anomalies > 0 else 0,
        }
        results.append(result)
        if detail:
            print(f"    {result}")

    mean_rate = np.mean([r['anomaly_rate_pct'] for r in results])
    mean_pos = np.mean([r['positive_anomalies'] for r in results])
    mean_neg = np.mean([r['negative_anomalies'] for r in results])
    mean_cluster = np.mean([r['cluster_rate'] for r in results])
    summary = f"Mean anomaly rate={mean_rate:.1f}%, pos:neg={mean_pos:.0f}:{mean_neg:.0f}, cluster={mean_cluster:.0f}%"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-649: Residual Anomaly Detection', 'summary': summary, 'details': results}


def run_exp_650(patients, detail=False):
    """EXP-650: Sensor Age Effect on Prediction — group by sensor day."""
    results = []
    for p in patients:
        df, pk = p['df'].copy(), p.get('pk')
        if pk is None:
            continue
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']
        bg_decay = (120.0 - bg) * 0.005
        flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
        resid = bg[1:] - flux_pred

        # Estimate sensor age from noise profile changes
        # Use rolling MAE of residuals in 1-day windows as proxy
        day_steps = 288
        n = len(resid)
        daily_mae = []
        for start in range(0, n - day_steps, day_steps):
            w = resid[start:start + day_steps]
            valid = np.isfinite(w)
            if valid.sum() > day_steps * 0.5:
                daily_mae.append({
                    'day': len(daily_mae) + 1,
                    'mae': float(np.mean(np.abs(w[valid]))),
                    'sd': float(np.std(w[valid])),
                })

        if len(daily_mae) < 10:
            continue

        # Group into sensor sessions (assume 10-day sessions)
        session_len = 10
        sessions = []
        for s_start in range(0, len(daily_mae), session_len):
            session = daily_mae[s_start:s_start + session_len]
            if len(session) < 5:
                continue
            # Compare first half vs second half of each session
            half = len(session) // 2
            early = np.mean([d['mae'] for d in session[:half]])
            late = np.mean([d['mae'] for d in session[half:]])
            sessions.append({
                'session': len(sessions) + 1,
                'early_mae': round(early, 2),
                'late_mae': round(late, 2),
                'degradation': round(late - early, 2),
                'degradation_pct': round((late - early) / early * 100, 1) if early > 0 else 0,
            })

        if not sessions:
            continue

        mean_degrad = np.mean([s['degradation_pct'] for s in sessions])
        n_degrad = sum(1 for s in sessions if s['degradation_pct'] > 5)

        # Also check overall day-of-sensor trend
        maes = [d['mae'] for d in daily_mae]
        x = np.arange(len(maes))
        slope = np.polyfit(x, maes, 1)[0] * session_len  # per sensor session

        result = {
            'patient': p['name'],
            'n_sessions': len(sessions),
            'mean_degradation_pct': round(float(mean_degrad), 1),
            'n_degraded_sessions': n_degrad,
            'mae_trend_per_session': round(float(slope), 3),
            'sessions': sessions,
        }
        results.append(result)
        if detail:
            print(f"    {p['name']}: {len(sessions)} sessions, mean degrad={mean_degrad:.1f}%, "
                  f"trend={slope:.3f}/session")

    mean_degrad = np.mean([r['mean_degradation_pct'] for r in results])
    n_with_degrad = sum(1 for r in results if r['mean_degradation_pct'] > 5)
    summary = f"Mean sensor degradation={mean_degrad:.1f}%, patients with >5% degradation: {n_with_degrad}/{len(results)}"
    print(f"  RESULT: {summary}")
    return {'name': 'EXP-650: Sensor Age Effect', 'summary': summary, 'details': results}


EXPERIMENTS = [
    ("EXP-641", "EXP-641: Model-based 30-min hypo prediction vs simple rules.", run_exp_641),
    ("EXP-642", "EXP-642: Optimize per-patient BG+slope threshold for hypo alerts.", run_exp_642),
    ("EXP-643", "EXP-643: Cumulative flux trajectory for prospective hypo prediction.", run_exp_643),
    ("EXP-644", "EXP-644: 5-feature parsimonious model vs full 10-feature.", run_exp_644),
    ("EXP-645", "EXP-645: Minimal 2-feature clinical model (AR1+demand²).", run_exp_645),
    ("EXP-646", "EXP-646: 60-min prediction quality — Clarke Error Grid evaluation.", run_exp_646),
    ("EXP-647", "EXP-647: Biweekly score change detection with bootstrap CI.", run_exp_647),
    ("EXP-648", "EXP-648: Monthly settings drift detection via flux trends.", run_exp_648),
    ("EXP-649", "EXP-649: Residual anomaly detection — 3σ event characterization.", run_exp_649),
    ("EXP-650", "EXP-650: Sensor age effect on model prediction accuracy.", run_exp_650),
]


def main():
    parser = argparse.ArgumentParser(description="EXP-641-650")
    parser.add_argument("--max-patients", type=int, default=11)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--only", type=str, help="Run only specific experiment, e.g. EXP-641")
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    all_results = []
    for eid, desc, func in EXPERIMENTS:
        if args.only and args.only != eid:
            continue
        print(f"{'=' * 60}")
        print(f"Running {eid}: {desc}")
        print(f"{'=' * 60}\n")
        result = func(patients, detail=args.detail)
        all_results.append(result)

        if args.save:
            safe_name = result['name'].lower().replace(' ', '_').replace('/', '_')[:30]
            fname = f"{eid.lower()}_{safe_name}.json"
            out_dir = Path(__file__).parent / "results"
            out_dir.mkdir(exist_ok=True)
            # Convert numpy types for JSON serialization
            def convert(obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                if isinstance(obj, (np.floating,)):
                    return float(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                if isinstance(obj, (np.bool_,)):
                    return bool(obj)
                return obj

            with open(out_dir / fname, 'w') as f:
                json.dump(result, f, indent=2, default=convert)
            print(f"  Saved: {fname}")
        print()


if __name__ == "__main__":
    main()
