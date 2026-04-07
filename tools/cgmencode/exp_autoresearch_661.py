#!/usr/bin/env python3
"""EXP-661-670: Deep clinical validation, extended timescale, robustness.

EXP-661: Temporal anomaly patterns — hour-of-day distribution per category
EXP-662: CR/ISF sensitivity analysis — simulate ±10-20% changes
EXP-663: Hypo recovery dynamics — recovery rate vs flux context
EXP-664: Weekly periodicity — 7-day ACF and day-of-week anomaly rates
EXP-665: Seasonal/monthly drift — first vs last 30-day statistics
EXP-666: Cumulative learning curve — feature importance at different data sizes
EXP-667: Gap tolerance — model degradation with artificial CGM gaps
EXP-668: Outlier robustness — test on compression-artifact-like segments
EXP-669: Multi-patient ensemble — population model vs personal model
EXP-670: Production pipeline benchmark — end-to-end timing
"""

import argparse
import json
import time
import sys
from pathlib import Path
import numpy as np

# ── patient + flux helpers ──────────────────────────────────────────
PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


def _load_patients(max_patients=11):
    from cgmencode.exp_metabolic_flux import load_patients
    return load_patients(PATIENTS_DIR, max_patients=max_patients)


def _compute_flux(p):
    """Return (bg, supply, demand, hepatic, carb_supply, net, resid) arrays."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    df = p["df"]
    pk = p.get("pk")
    if pk is None:
        return None
    flux = compute_supply_demand(df, pk)
    bg_col = "glucose" if "glucose" in df.columns else "sgv"
    bg = df[bg_col].values.astype(float)
    supply = flux["supply"]
    demand = flux["demand"]
    hepatic = flux["hepatic"]
    carb_supply = flux["carb_supply"]
    net = flux["net"]
    n = min(len(bg), len(supply))
    bg = bg[:n]
    supply = supply[:n]
    demand = demand[:n]
    hepatic = hepatic[:n]
    carb_supply = carb_supply[:n]
    net = net[:n]
    # residual = actual change - predicted change
    resid = np.diff(bg) - net[:-1]
    return bg, supply, demand, hepatic, carb_supply, net, resid


def _build_joint_features(resid, bg, demand, order=6):
    """Build joint NL+AR features (matching working 651 implementation)."""
    n = len(resid)
    n_feat = order + 4
    X = np.zeros((n, n_feat))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid[:-lag] if lag < n else 0
    bg_c = bg[:n] - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand[:n] ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand[:n] / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    return X


def _fit_ridge(X_train, y_train, X_test, y_test=None, alpha=10.0):
    """Fit ridge regression, filtering NaN rows. Return R², predictions, coefficients."""
    # Filter NaN from training data
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    if mask_tr.sum() < 50:
        n_feat = X_train.shape[1]
        return 0.0, np.zeros(X_test.shape[0]), np.zeros(n_feat)
    Xtr = X_train[mask_tr]
    ytr = y_train[mask_tr]

    from numpy.linalg import solve
    XtX = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    Xty = Xtr.T @ ytr
    w = solve(XtX, Xty)

    # Filter NaN from test data
    mask_te = np.all(np.isfinite(X_test), axis=1)
    pred = np.full(X_test.shape[0], np.nan)
    if mask_te.sum() > 0:
        pred[mask_te] = X_test[mask_te] @ w

    if y_test is not None:
        valid = mask_te & np.isfinite(y_test)
        if valid.sum() < 10:
            return 0.0, pred, w
        ss_res = np.sum((y_test[valid] - pred[valid]) ** 2)
        ss_tot = np.sum((y_test[valid] - np.mean(y_test[valid])) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
        return r2, pred, w
    return 0.0, pred, w


def _compute_resid_with_flux(p):
    """Compute residuals using flux prediction (matching 651 implementation)."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    df = p["df"]
    pk = p.get("pk")
    if pk is None:
        return None
    bg_col = "glucose" if "glucose" in df.columns else "sgv"
    bg = df[bg_col].values.astype(float)
    sd = compute_supply_demand(df, pk)
    supply = sd["supply"]
    demand = sd["demand"]
    hepatic = sd["hepatic"]
    bg_decay = (120.0 - bg) * 0.005
    n = min(len(bg), len(supply))
    bg, supply, demand, hepatic = bg[:n], supply[:n], demand[:n], hepatic[:n]
    bg_decay = bg_decay[:n]
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    return bg, supply, demand, hepatic, sd.get("carb_supply", supply), sd["net"], resid


def _get_timestamps(p):
    """Get datetime array from patient dataframe."""
    import pandas as pd
    df = p["df"]
    if "dateString" in df.columns:
        ts = pd.to_datetime(df["dateString"], utc=True, errors="coerce")
    elif "date" in df.columns:
        ts = pd.to_datetime(df["date"], utc=True, errors="coerce")
    else:
        ts = pd.Series(df.index)
    return ts.values if hasattr(ts, 'values') else np.array(ts)


# ── experiments ─────────────────────────────────────────────────────

def exp_661_temporal_anomaly_patterns(patients, detail=False):
    """EXP-661: Hour-of-day distribution of anomaly categories."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(resid), len(ts) - 1)
        resid_c = resid[:n]
        ts_r = pd.DatetimeIndex(ts[1:n + 1])

        # detect anomalies (3σ)
        valid = np.isfinite(resid_c)
        mu = np.nanmean(resid_c[valid])
        sig = np.nanstd(resid_c[valid])
        anom_mask = np.abs(resid_c - mu) > 3 * sig
        anom_mask = anom_mask & valid
        if anom_mask.sum() < 5:
            continue

        hours = ts_r[anom_mask].hour.values
        bg_anom = bg[1:n + 1][anom_mask]
        cs_anom = carb_supply[:n][anom_mask]

        # classify by hour bins
        hour_dist = np.zeros(24)
        for h in hours:
            hour_dist[int(h)] += 1
        hour_dist = hour_dist / hour_dist.sum() * 100

        # meal vs non-meal by hour
        meal_hours = np.sum((hours >= 6) & (hours <= 9) |
                            (hours >= 11) & (hours <= 14) |
                            (hours >= 17) & (hours <= 21))
        meal_pct = meal_hours / len(hours) * 100

        # peak anomaly hour
        peak_hour = int(np.argmax(hour_dist))

        pr = {
            "patient": p["name"],
            "n_anomalies": int(anom_mask.sum()),
            "peak_hour": peak_hour,
            "peak_pct": round(hour_dist[peak_hour], 1),
            "meal_window_pct": round(meal_pct, 1),
            "overnight_pct": round(np.sum(hour_dist[0:6]), 1),
            "morning_pct": round(np.sum(hour_dist[6:12]), 1),
            "afternoon_pct": round(np.sum(hour_dist[12:18]), 1),
            "evening_pct": round(np.sum(hour_dist[18:24]), 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: peak={peak_hour}:00 ({hour_dist[peak_hour]:.1f}%) "
                  f"meal_window={meal_pct:.0f}% overnight={np.sum(hour_dist[0:6]):.0f}%")

    mean_meal = np.mean([r["meal_window_pct"] for r in results])
    mean_overnight = np.mean([r["overnight_pct"] for r in results])
    peak_hours = [r["peak_hour"] for r in results]

    return {
        "name": "EXP-661: Temporal anomaly patterns",
        "mean_meal_window_pct": round(mean_meal, 1),
        "mean_overnight_pct": round(mean_overnight, 1),
        "most_common_peak_hour": int(np.median(peak_hours)),
        "per_patient": results,
    }


def exp_662_cr_isf_sensitivity(patients, detail=False):
    """EXP-662: Simulate ±10-20% CR/ISF changes and measure flux impact."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out

        # baseline stats
        valid = np.isfinite(bg)
        base_tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)) * 100)

        # Local perturbation approach: adjust BG by per-step flux change
        # (avoids divergent open-loop simulation)
        sims = {}
        for pct in [-20, -10, 10, 20]:
            factor = 1 + pct / 100.0
            # CR change → demand changes by carb_supply * (factor-1) per step
            delta_demand = carb_supply * (factor - 1)
            # Each step: BG changes by -delta_demand (more demand → lower BG)
            sim_bg = bg.copy()
            sim_bg[1:] = bg[1:] - np.nancumsum(delta_demand[:-1]) * 0.01  # damped cumulative
            # But really, local effect is what matters for sensitivity
            sim_bg_local = bg - delta_demand * 5  # 5-step lookahead effect
            sim_bg_local = np.clip(sim_bg_local, 20, 500)
            v = np.isfinite(sim_bg_local)
            sim_tir = float(np.mean((sim_bg_local[v] >= 70) & (sim_bg_local[v] <= 180)) * 100)
            sim_tbr = float(np.mean(sim_bg_local[v] < 70) * 100)
            sims[f"cr_{pct:+d}pct_tir"] = round(sim_tir, 1)
            sims[f"cr_{pct:+d}pct_tbr"] = round(sim_tbr, 1)

        # ISF sensitivity: correction portion of demand scales
        for pct in [-20, -10, 10, 20]:
            factor = 1 + pct / 100.0
            correction_demand = np.clip(demand - carb_supply, 0, None)
            delta_corr = correction_demand * (factor - 1)
            sim_bg_local = bg - delta_corr * 5
            sim_bg_local = np.clip(sim_bg_local, 20, 500)
            v = np.isfinite(sim_bg_local)
            sim_tir = float(np.mean((sim_bg_local[v] >= 70) & (sim_bg_local[v] <= 180)) * 100)
            sim_tbr = float(np.mean(sim_bg_local[v] < 70) * 100)
            sims[f"isf_{pct:+d}pct_tir"] = round(sim_tir, 1)
            sims[f"isf_{pct:+d}pct_tbr"] = round(sim_tbr, 1)

        pr = {"patient": p["name"], "base_tir": round(base_tir, 1), **sims}
        results.append(pr)
        if detail:
            print(f"    {p['name']}: base TIR={base_tir:.0f}% "
                  f"CR-10%→{sims.get('cr_-10pct_tir', '?')}% "
                  f"CR+10%→{sims.get('cr_+10pct_tir', '?')}% "
                  f"ISF-10%→{sims.get('isf_-10pct_tir', '?')}% "
                  f"ISF+10%→{sims.get('isf_+10pct_tir', '?')}%")

    # summarize sensitivity
    cr_sens = np.mean([abs(r.get("cr_-10pct_tir", r["base_tir"]) - r["base_tir"]) for r in results])
    isf_sens = np.mean([abs(r.get("isf_-10pct_tir", r["base_tir"]) - r["base_tir"]) for r in results])

    return {
        "name": "EXP-662: CR/ISF sensitivity analysis",
        "mean_cr_10pct_tir_delta": round(cr_sens, 1),
        "mean_isf_10pct_tir_delta": round(isf_sens, 1),
        "per_patient": results,
    }


def exp_663_hypo_recovery(patients, detail=False):
    """EXP-663: Hypo recovery dynamics — recovery rate vs flux context at nadir."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(bg)

        # find hypo events (BG<70 for ≥3 consecutive points)
        hypo_mask = bg < 70
        events = []
        i = 0
        while i < n:
            if hypo_mask[i]:
                start = i
                while i < n and hypo_mask[i]:
                    i += 1
                end = i
                if end - start >= 3:
                    events.append((start, end))
            else:
                i += 1

        if len(events) < 3:
            continue

        recoveries = []
        for start, end in events:
            nadir_idx = start + np.argmin(bg[start:end])
            nadir_bg = bg[nadir_idx]

            # recovery: how long to get back to 90 mg/dL
            recovery_time = None
            for t in range(end, min(end + 36, n)):  # up to 3 hours
                if bg[t] >= 90:
                    recovery_time = (t - nadir_idx) * 5  # minutes
                    break

            # flux context at nadir
            if nadir_idx < len(net):
                nadir_net = net[nadir_idx]
                nadir_supply = supply[nadir_idx]
                nadir_demand = demand[nadir_idx]
            else:
                continue

            # recovery rate (mg/dL per 5 min over first 30 min after nadir)
            if nadir_idx + 6 < n:
                recovery_rate = (bg[nadir_idx + 6] - bg[nadir_idx]) / 6.0
            else:
                recovery_rate = np.nan

            recoveries.append({
                "nadir_bg": nadir_bg,
                "recovery_time_min": recovery_time,
                "recovery_rate": recovery_rate,
                "nadir_net_flux": nadir_net,
                "nadir_supply": nadir_supply,
                "nadir_demand": nadir_demand,
            })

        if len(recoveries) < 3:
            continue

        rates = [r["recovery_rate"] for r in recoveries if not np.isnan(r["recovery_rate"])]
        net_fluxes = [r["nadir_net_flux"] for r in recoveries if not np.isnan(r["recovery_rate"])]
        rec_times = [r["recovery_time_min"] for r in recoveries if r["recovery_time_min"] is not None]

        corr = float(np.corrcoef(net_fluxes, rates)[0, 1]) if len(rates) >= 3 else np.nan

        pr = {
            "patient": p["name"],
            "n_events": len(recoveries),
            "mean_recovery_rate": round(float(np.nanmean(rates)), 2),
            "mean_recovery_time": round(float(np.mean(rec_times)), 1) if rec_times else None,
            "corr_flux_recovery": round(corr, 3),
            "mean_nadir_bg": round(float(np.mean([r["nadir_bg"] for r in recoveries])), 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {len(recoveries)} events, "
                  f"recovery={np.nanmean(rates):.2f} mg/dL/5min, "
                  f"r(flux,recovery)={corr:.3f}, "
                  f"mean_time={np.mean(rec_times) if rec_times else 0:.0f}min")

    mean_rate = np.nanmean([r["mean_recovery_rate"] for r in results])
    mean_corr = np.nanmean([r["corr_flux_recovery"] for r in results])

    return {
        "name": "EXP-663: Hypo recovery dynamics",
        "mean_recovery_rate_per_5min": round(float(mean_rate), 2),
        "mean_flux_recovery_corr": round(float(mean_corr), 3),
        "n_patients": len(results),
        "per_patient": results,
    }


def exp_664_weekly_periodicity(patients, detail=False):
    """EXP-664: 7-day periodicity in residuals and anomaly rates."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(resid), len(ts) - 1)

        # day-of-week anomaly rates
        mu, sig = np.nanmean(resid[:n]), np.nanstd(resid[:n])
        anom_mask = np.abs(resid[:n] - mu) > 3 * sig
        import pandas as pd
        ts_arr = _get_timestamps(p)
        dow = pd.DatetimeIndex(ts_arr[1:n + 1]).dayofweek.values

        dow_rates = {}
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for d in range(7):
            mask = dow == d
            if mask.sum() > 0:
                dow_rates[dow_names[d]] = round(float(anom_mask[mask].mean() * 100), 2)
            else:
                dow_rates[dow_names[d]] = 0.0

        # 7-day lag ACF
        lag_7d = 7 * 288  # 7 days at 5-min intervals
        if n > lag_7d + 100:
            r1 = resid[:n - lag_7d]
            r2 = resid[lag_7d:n]
            min_len = min(len(r1), len(r2))
            r1, r2 = r1[:min_len], r2[:min_len]
            valid = ~(np.isnan(r1) | np.isnan(r2))
            if valid.sum() > 100:
                acf_7d = float(np.corrcoef(r1[valid], r2[valid])[0, 1])
            else:
                acf_7d = np.nan
        else:
            acf_7d = np.nan

        # weekend vs weekday
        weekend_mask = (dow >= 5)
        weekday_mask = (dow < 5)
        weekend_anom = float(anom_mask[weekend_mask].mean() * 100) if weekend_mask.sum() > 0 else 0
        weekday_anom = float(anom_mask[weekday_mask].mean() * 100) if weekday_mask.sum() > 0 else 0

        # weekend vs weekday mean BG
        bg_r = bg[1:n + 1]
        weekend_bg = float(np.nanmean(bg_r[weekend_mask])) if weekend_mask.sum() > 0 else np.nan
        weekday_bg = float(np.nanmean(bg_r[weekday_mask])) if weekday_mask.sum() > 0 else np.nan

        pr = {
            "patient": p["name"],
            "acf_7day": round(acf_7d, 3) if not np.isnan(acf_7d) else None,
            "weekend_anom_rate": round(weekend_anom, 2),
            "weekday_anom_rate": round(weekday_anom, 2),
            "weekend_mean_bg": round(weekend_bg, 1),
            "weekday_mean_bg": round(weekday_bg, 1),
            "dow_rates": dow_rates,
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: ACF(7d)={acf_7d:.3f} "
                  f"weekend_anom={weekend_anom:.1f}% weekday={weekday_anom:.1f}% "
                  f"weekend_BG={weekend_bg:.0f} weekday_BG={weekday_bg:.0f}")

    valid_acf = [r["acf_7day"] for r in results if r["acf_7day"] is not None]
    mean_acf = np.mean(valid_acf) if valid_acf else np.nan
    we_bg = np.mean([r["weekend_mean_bg"] for r in results])
    wd_bg = np.mean([r["weekday_mean_bg"] for r in results])

    return {
        "name": "EXP-664: Weekly periodicity",
        "mean_acf_7day": round(float(mean_acf), 3),
        "mean_weekend_bg": round(float(we_bg), 1),
        "mean_weekday_bg": round(float(wd_bg), 1),
        "weekend_weekday_delta": round(float(we_bg - wd_bg), 1),
        "per_patient": results,
    }


def exp_665_monthly_drift(patients, detail=False):
    """EXP-665: First 30 days vs last 30 days comparison."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out

        # 30 days = 30*288 = 8640 steps
        window = 8640
        if len(bg) < 2 * window + 100:
            continue

        # first 30 days
        bg_first = bg[:window]
        net_first = net[:window]
        demand_first = demand[:window]
        supply_first = supply[:window]

        # last 30 days
        bg_last = bg[-window:]
        net_last = net[-window:]
        demand_last = demand[-window:]
        supply_last = supply[-window:]

        first_tir = float(np.mean((bg_first >= 70) & (bg_first <= 180)) * 100)
        last_tir = float(np.mean((bg_last >= 70) & (bg_last <= 180)) * 100)
        first_cv = float(np.nanstd(bg_first) / np.nanmean(bg_first) * 100)
        last_cv = float(np.nanstd(bg_last) / np.nanmean(bg_last) * 100)
        first_mean_net = float(np.nanmean(net_first))
        last_mean_net = float(np.nanmean(net_last))
        first_mean_demand = float(np.nanmean(demand_first))
        last_mean_demand = float(np.nanmean(demand_last))

        # model performance drift
        n_resid = len(resid)
        r_first = resid[:min(window, n_resid)]
        r_last = resid[max(0, n_resid - window):]
        first_resid_std = float(np.nanstd(r_first))
        last_resid_std = float(np.nanstd(r_last))

        pr = {
            "patient": p["name"],
            "first30_tir": round(first_tir, 1),
            "last30_tir": round(last_tir, 1),
            "tir_delta": round(last_tir - first_tir, 1),
            "first30_cv": round(first_cv, 1),
            "last30_cv": round(last_cv, 1),
            "first30_mean_net": round(first_mean_net, 2),
            "last30_mean_net": round(last_mean_net, 2),
            "first30_demand": round(first_mean_demand, 2),
            "last30_demand": round(last_mean_demand, 2),
            "first30_resid_std": round(first_resid_std, 2),
            "last30_resid_std": round(last_resid_std, 2),
            "improving": last_tir > first_tir + 2,
            "declining": last_tir < first_tir - 2,
        }
        results.append(pr)
        if detail:
            direction = "↑" if pr["improving"] else ("↓" if pr["declining"] else "→")
            print(f"    {p['name']}: TIR {first_tir:.0f}%→{last_tir:.0f}% ({direction}) "
                  f"CV {first_cv:.0f}%→{last_cv:.0f}% "
                  f"demand {first_mean_demand:.1f}→{last_mean_demand:.1f}")

    improving = sum(1 for r in results if r["improving"])
    declining = sum(1 for r in results if r["declining"])
    stable = len(results) - improving - declining

    return {
        "name": "EXP-665: Seasonal/monthly drift",
        "improving": improving,
        "declining": declining,
        "stable": stable,
        "mean_tir_delta": round(float(np.mean([r["tir_delta"] for r in results])), 1),
        "per_patient": results,
    }


def exp_666_learning_curve_features(patients, detail=False):
    """EXP-666: Feature importance at different training data sizes."""
    results = []
    windows = [7, 30, 90]  # days
    feature_names = ["AR1", "AR2", "AR3", "AR4", "AR5", "AR6",
                     "BG²", "demand²", "BG×demand", "σ(BG)"]

    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid[1:]
        X = X[1:]
        n = len(y)

        pr = {"patient": p["name"]}
        for days in windows:
            steps = days * 288
            if steps > n * 0.7:
                continue
            X_tr, y_tr = X[:steps], y[:steps]
            X_te, y_te = X[steps:], y[steps:]
            if len(y_te) < 100:
                continue

            r2, pred, w = _fit_ridge(X_tr, y_tr, X_te, y_te)

            # feature importance (absolute weight × feature std)
            feat_imp = np.abs(w) * np.std(X_tr, axis=0)
            feat_imp = feat_imp / feat_imp.sum() * 100

            for i, fn in enumerate(feature_names):
                pr[f"{fn}_{days}d"] = round(float(feat_imp[i]), 1)
            pr[f"r2_{days}d"] = round(float(r2), 3)

        results.append(pr)
        if detail:
            parts = []
            for days in windows:
                if f"r2_{days}d" in pr:
                    top = max(feature_names, key=lambda fn: pr.get(f"{fn}_{days}d", 0))
                    parts.append(f"{days}d: R²={pr[f'r2_{days}d']:.3f} top={top}")
            print(f"    {p['name']}: {', '.join(parts)}")

    # aggregate: does feature ranking change with data size?
    ranking_changes = 0
    for fn in feature_names:
        ranks_7 = []
        ranks_90 = []
        for r in results:
            if f"{fn}_7d" in r and f"{fn}_90d" in r:
                ranks_7.append(r[f"{fn}_7d"])
                ranks_90.append(r[f"{fn}_90d"])
        if ranks_7 and ranks_90:
            if abs(np.mean(ranks_7) - np.mean(ranks_90)) > 5:
                ranking_changes += 1

    return {
        "name": "EXP-666: Learning curve feature importance",
        "ranking_changes": ranking_changes,
        "n_patients": len(results),
        "per_patient": results,
    }


def exp_667_gap_tolerance(patients, detail=False):
    """EXP-667: Model degradation with artificial CGM gaps."""
    results = []
    gap_sizes = [3, 6, 12, 24]  # gap sizes in 5-min steps (15, 30, 60, 120 min)

    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid[1:]
        X = X[1:]
        n = len(y)
        split = int(n * 0.7)

        # baseline (no gaps)
        r2_base, _, _ = _fit_ridge(X[:split], y[:split], X[split:], y[split:])

        pr = {"patient": p["name"], "r2_baseline": round(float(r2_base), 3)}

        for gap_size in gap_sizes:
            # inject random gaps in test data
            X_test_gap = X[split:].copy()
            y_test_gap = y[split:].copy()
            n_test = len(y_test_gap)
            n_gaps = max(1, n_test // (gap_size * 10))

            rng = np.random.RandomState(42)
            for _ in range(n_gaps):
                start = rng.randint(0, max(1, n_test - gap_size))
                end = min(start + gap_size, n_test)
                # simulate gap: zero out AR features (no recent residuals)
                X_test_gap[start:end, :6] = 0

            _, pred_gap, w = _fit_ridge(X[:split], y[:split], X_test_gap, y_test_gap)
            ss_res = np.nansum((y_test_gap - pred_gap) ** 2)
            ss_tot = np.nansum((y_test_gap - np.nanmean(y_test_gap)) ** 2)
            r2_gap = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

            gap_min = gap_size * 5
            pr[f"r2_gap_{gap_min}min"] = round(float(r2_gap), 3)
            pr[f"degradation_{gap_min}min_pct"] = round((r2_base - r2_gap) / max(r2_base, 0.001) * 100, 1)

        results.append(pr)
        if detail:
            parts = [f"{gs * 5}min: {pr.get(f'degradation_{gs * 5}min_pct', '?'):.1f}%↓"
                     for gs in gap_sizes]
            print(f"    {p['name']}: base R²={r2_base:.3f}, degradation: {', '.join(parts)}")

    # mean degradation per gap size
    mean_degrad = {}
    for gs in gap_sizes:
        key = f"degradation_{gs * 5}min_pct"
        vals = [r[key] for r in results if key in r]
        mean_degrad[f"{gs * 5}min"] = round(float(np.mean(vals)), 1) if vals else None

    return {
        "name": "EXP-667: Gap tolerance",
        "mean_degradation": mean_degrad,
        "per_patient": results,
    }


def exp_668_outlier_robustness(patients, detail=False):
    """EXP-668: Robustness to extreme CGM values and compression artifacts."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid[1:]
        X = X[1:]
        n = len(y)
        split = int(n * 0.7)

        # baseline
        r2_base, _, _ = _fit_ridge(X[:split], y[:split], X[split:], y[split:])

        # test 1: inject spike outliers into FEATURES (simulating bad CGM readings)
        X_test = X[split:].copy()
        y_test = y[split:]
        n_test = len(y_test)
        rng = np.random.RandomState(42)

        # inject 1% spike artifacts into AR features (columns 0-5)
        n_spikes = max(1, n_test // 100)
        spike_idx = rng.choice(n_test, n_spikes, replace=False)
        X_spike = X_test.copy()
        X_spike[spike_idx, :6] += rng.choice([-50, 50], (n_spikes, 1))

        r2_spike, _, _ = _fit_ridge(X[:split], y[:split], X_spike, y_test)

        # test 2: flat segments in AR features (compression artifact)
        X_flat = X_test.copy()
        for _ in range(n_test // 500):
            start = rng.randint(0, max(1, n_test - 12))
            X_flat[start:start + 12, :6] = X_flat[start, :6]

        r2_flat, _, _ = _fit_ridge(X[:split], y[:split], X_flat, y_test)

        # test 3: Gaussian noise injection into all features
        X_noisy = X_test.copy()
        for col in range(X_test.shape[1]):
            col_std = np.nanstd(X_test[:, col])
            if col_std > 0:
                X_noisy[:, col] += rng.normal(0, col_std * 0.1, n_test)

        r2_noisy, _, _ = _fit_ridge(X[:split], y[:split], X_noisy, y_test)

        pr = {
            "patient": p["name"],
            "r2_baseline": round(float(r2_base), 3),
            "r2_spikes_1pct": round(float(r2_spike), 3),
            "r2_flat_segments": round(float(r2_flat), 3),
            "r2_noise_10pct": round(float(r2_noisy), 3),
            "spike_degradation_pct": round((r2_base - r2_spike) / max(r2_base, 0.001) * 100, 1),
            "flat_degradation_pct": round((r2_base - r2_flat) / max(r2_base, 0.001) * 100, 1),
            "noise_degradation_pct": round((r2_base - r2_noisy) / max(r2_base, 0.001) * 100, 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: base={r2_base:.3f} "
                  f"spikes={r2_spike:.3f}({pr['spike_degradation_pct']:+.1f}%) "
                  f"flat={r2_flat:.3f}({pr['flat_degradation_pct']:+.1f}%) "
                  f"noise={r2_noisy:.3f}({pr['noise_degradation_pct']:+.1f}%)")

    return {
        "name": "EXP-668: Outlier robustness",
        "mean_spike_degradation": round(float(np.mean([r["spike_degradation_pct"] for r in results])), 1),
        "mean_flat_degradation": round(float(np.mean([r["flat_degradation_pct"] for r in results])), 1),
        "mean_noise_degradation": round(float(np.mean([r["noise_degradation_pct"] for r in results])), 1),
        "per_patient": results,
    }


def exp_669_multi_patient_ensemble(patients, detail=False):
    """EXP-669: Population ensemble model vs personal model."""
    all_X = []
    all_y = []
    patient_indices = []

    for idx, p in enumerate(patients):
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid[1:]
        X = X[1:]
        all_X.append(X)
        all_y.append(y)
        patient_indices.append((p["name"], idx, len(y)))

    results = []
    for name, idx, n in patient_indices:
        X_p = all_X[idx]
        y_p = all_y[idx]
        split = int(n * 0.7)

        # personal model
        r2_personal, _, _ = _fit_ridge(X_p[:split], y_p[:split], X_p[split:], y_p[split:])

        # population model (train on all OTHER patients)
        X_pop = np.vstack([all_X[j] for j_name, j, _ in patient_indices if j != idx])
        y_pop = np.concatenate([all_y[j] for j_name, j, _ in patient_indices if j != idx])

        # subsample population data to keep computation manageable
        if len(y_pop) > 50000:
            rng = np.random.RandomState(42)
            sub = rng.choice(len(y_pop), 50000, replace=False)
            X_pop = X_pop[sub]
            y_pop = y_pop[sub]

        r2_pop, _, _ = _fit_ridge(X_pop, y_pop, X_p[split:], y_p[split:])

        # blended model: average weights instead of predictions to avoid NaN
        _, _, w_personal = _fit_ridge(X_p[:split], y_p[:split], X_p[split:], y_p[split:])
        _, _, w_pop = _fit_ridge(X_pop, y_pop, X_p[split:], y_p[split:])
        w_blend = 0.5 * w_personal + 0.5 * w_pop
        X_te = X_p[split:]
        y_test = y_p[split:]
        # compute R² with NaN filtering
        mask_te = np.all(np.isfinite(X_te), axis=1) & np.isfinite(y_test)
        if mask_te.sum() > 10:
            pred_blend = X_te[mask_te] @ w_blend
            ss_res = np.sum((y_test[mask_te] - pred_blend) ** 2)
            ss_tot = np.sum((y_test[mask_te] - np.mean(y_test[mask_te])) ** 2)
            r2_blend = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
        else:
            r2_blend = 0.0

        pr = {
            "patient": name,
            "r2_personal": round(float(r2_personal), 3),
            "r2_population": round(float(r2_pop), 3),
            "r2_blend": round(float(r2_blend), 3),
            "best": "personal" if r2_personal >= max(r2_pop, r2_blend) else
                    ("blend" if r2_blend >= r2_pop else "population"),
        }
        results.append(pr)
        if detail:
            print(f"    {name}: personal={r2_personal:.3f} pop={r2_pop:.3f} "
                  f"blend={r2_blend:.3f} → {pr['best']}")

    personal_wins = sum(1 for r in results if r["best"] == "personal")
    blend_wins = sum(1 for r in results if r["best"] == "blend")
    pop_wins = sum(1 for r in results if r["best"] == "population")

    return {
        "name": "EXP-669: Multi-patient ensemble",
        "personal_wins": personal_wins,
        "blend_wins": blend_wins,
        "population_wins": pop_wins,
        "mean_personal_r2": round(float(np.mean([r["r2_personal"] for r in results])), 3),
        "mean_population_r2": round(float(np.mean([r["r2_population"] for r in results])), 3),
        "mean_blend_r2": round(float(np.mean([r["r2_blend"] for r in results])), 3),
        "per_patient": results,
    }


def exp_670_production_benchmark(patients, detail=False):
    """EXP-670: End-to-end production pipeline timing."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand

    timings = []
    for p in patients:
        df = p["df"]
        pk = p.get("pk")
        if pk is None:
            continue

        n_steps = len(df)
        bg_col = "glucose" if "glucose" in df.columns else "sgv"

        # phase 1: flux computation
        t0 = time.perf_counter()
        flux = compute_supply_demand(df, pk)
        t_flux = time.perf_counter() - t0

        # phase 2: feature engineering
        t0 = time.perf_counter()
        bg = df[bg_col].values.astype(float)
        supply = flux["supply"]
        demand = flux["demand"]
        hepatic = flux["hepatic"]
        net = flux["net"]
        n = min(len(bg), len(supply))
        bg, supply, demand, hepatic = bg[:n], supply[:n], demand[:n], hepatic[:n]
        resid = np.diff(bg) - net[:n - 1]
        X = _build_joint_features(resid, bg, demand)
        t_feat = time.perf_counter() - t0

        # phase 3: model training
        y = resid[1:]
        X = X[1:]
        split = int(len(y) * 0.7)
        t0 = time.perf_counter()
        r2, pred, w = _fit_ridge(X[:split], y[:split], X[split:], y[split:])
        t_train = time.perf_counter() - t0

        # phase 4: prediction (single step)
        t0 = time.perf_counter()
        for _ in range(100):  # 100 single-step predictions
            _ = X[-1:] @ w
        t_pred = (time.perf_counter() - t0) / 100

        # phase 5: anomaly detection + report card
        t0 = time.perf_counter()
        mu, sig = np.mean(resid), np.std(resid)
        anomalies = np.abs(resid - mu) > 3 * sig
        tir = np.mean((bg >= 70) & (bg <= 180))
        tbr = np.mean(bg < 70)
        cv = np.std(bg) / np.mean(bg)
        t_report = time.perf_counter() - t0

        total = t_flux + t_feat + t_train + t_pred + t_report

        pr = {
            "patient": p["name"],
            "n_steps": n_steps,
            "t_flux_ms": round(t_flux * 1000, 1),
            "t_features_ms": round(t_feat * 1000, 1),
            "t_train_ms": round(t_train * 1000, 1),
            "t_predict_ms": round(t_pred * 1000, 3),
            "t_report_ms": round(t_report * 1000, 1),
            "t_total_ms": round(total * 1000, 1),
            "steps_per_sec": round(n_steps / total),
        }
        timings.append(pr)
        if detail:
            print(f"    {p['name']}: {n_steps} steps in {total * 1000:.0f}ms "
                  f"(flux={t_flux * 1000:.0f} feat={t_feat * 1000:.0f} "
                  f"train={t_train * 1000:.0f} pred={t_pred * 1000:.3f} "
                  f"report={t_report * 1000:.1f}ms) = {n_steps / total:.0f} steps/s")

    mean_total = np.mean([t["t_total_ms"] for t in timings])
    mean_throughput = np.mean([t["steps_per_sec"] for t in timings])

    return {
        "name": "EXP-670: Production pipeline benchmark",
        "mean_total_ms": round(float(mean_total), 1),
        "mean_throughput_steps_per_sec": round(float(mean_throughput)),
        "single_prediction_us": round(float(np.mean([t["t_predict_ms"] for t in timings]) * 1000), 1),
        "per_patient": timings,
    }


# ── runner ──────────────────────────────────────────────────────────

ALL_EXPERIMENTS = [
    ("EXP-661", exp_661_temporal_anomaly_patterns),
    ("EXP-662", exp_662_cr_isf_sensitivity),
    ("EXP-663", exp_663_hypo_recovery),
    ("EXP-664", exp_664_weekly_periodicity),
    ("EXP-665", exp_665_monthly_drift),
    ("EXP-666", exp_666_learning_curve_features),
    ("EXP-667", exp_667_gap_tolerance),
    ("EXP-668", exp_668_outlier_robustness),
    ("EXP-669", exp_669_multi_patient_ensemble),
    ("EXP-670", exp_670_production_benchmark),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-patients", type=int, default=11)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--only", type=str, default=None, help="Run only this experiment, e.g. EXP-661")
    args = ap.parse_args()

    print("Loading patients...")
    patients = _load_patients(max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    out_dir = Path(__file__).parent.parent.parent / "externals" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    for exp_id, func in ALL_EXPERIMENTS:
        if args.only and args.only != exp_id:
            continue
        print("=" * 60)
        print(f"Running {exp_id}: {func.__doc__.strip().split(chr(10))[0]}")
        print("=" * 60)
        print()

        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue
        elapsed = time.time() - t0

        # print summary
        summary_keys = [k for k in result if k not in ("per_patient", "name")]
        summary = {k: result[k] for k in summary_keys}
        print(f"  RESULT: {summary}")

        if args.save:
            safe_name = result["name"].lower().replace(" ", "_").replace("/", "_").replace(":", "")[:30]
            fname = f"{exp_id.lower()}_{safe_name}.json"
            with open(out_dir / fname, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved: {fname}")

        print(f"  Time: {elapsed:.1f}s\n")


if __name__ == "__main__":
    main()
