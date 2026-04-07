#!/usr/bin/env python3
"""EXP-671-680: Spike detection, multi-scale, clinical tools, deployment hardening.

EXP-671: Spike detector — 3σ threshold on residual jumps
EXP-672: Spike interpolation — restore R² after spike removal
EXP-673: Hourly aggregation — clinical interpretability
EXP-674: Daily summary stats — predict next-day TIR
EXP-675: Dawn phenomenon quantification — per-patient
EXP-676: Meal response profiling — time-of-day variation
EXP-677: Exercise detection — negative demand residuals
EXP-678: Error bounds — bootstrap prediction intervals
EXP-679: Model staleness — accuracy decay without retraining
EXP-680: Clinical action validation — compare with standard rules
"""

import argparse
import json
import time
import sys
from pathlib import Path
import numpy as np

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


def _load_patients(max_patients=11):
    from cgmencode.exp_metabolic_flux import load_patients
    return load_patients(PATIENTS_DIR, max_patients=max_patients)


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
    carb_supply = sd.get("carb_supply", supply)
    bg_decay = (120.0 - bg) * 0.005
    n = min(len(bg), len(supply))
    bg, supply, demand, hepatic = bg[:n], supply[:n], demand[:n], hepatic[:n]
    carb_supply = carb_supply[:n]
    bg_decay = bg_decay[:n]
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    net = supply - demand
    return bg, supply, demand, hepatic, carb_supply, net, resid


def _build_joint_features(resid, bg, demand, order=6):
    """Build joint NL+AR features (matching 651)."""
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
    """Fit ridge, filtering NaN rows."""
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    if mask_tr.sum() < 50:
        return 0.0, np.zeros(X_test.shape[0]), np.zeros(X_train.shape[1])
    Xtr, ytr = X_train[mask_tr], y_train[mask_tr]
    XtX = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    Xty = Xtr.T @ ytr
    w = np.linalg.solve(XtX, Xty)
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


def _get_timestamps(p):
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

def exp_671_spike_detector(patients, detail=False):
    """EXP-671: Spike detector — 3σ threshold on residual jumps."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        valid = np.isfinite(resid)
        mu = np.nanmean(resid[valid])
        sigma = np.nanstd(resid[valid])

        # test multiple thresholds
        thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]
        spike_rates = {}
        for thr in thresholds:
            spikes = np.abs(resid - mu) > thr * sigma
            spikes = spikes & valid
            spike_rates[f"{thr}σ"] = round(float(spikes.mean() * 100), 3)

        # characterize 3σ spikes
        spikes_3s = (np.abs(resid - mu) > 3 * sigma) & valid
        n_spikes = int(spikes_3s.sum())

        # consecutive spike runs (clusters)
        runs = 0
        in_run = False
        for i in range(len(spikes_3s)):
            if spikes_3s[i]:
                if not in_run:
                    runs += 1
                    in_run = True
            else:
                in_run = False

        # spike magnitude
        spike_mags = np.abs(resid[spikes_3s] - mu) if n_spikes > 0 else np.array([0])

        pr = {
            "patient": p["name"],
            "n_spikes_3s": n_spikes,
            "spike_rate_3s": spike_rates.get("3.0σ", 0),
            "spike_clusters": runs,
            "mean_spike_mag": round(float(np.mean(spike_mags)), 1),
            "max_spike_mag": round(float(np.max(spike_mags)), 1),
            "rates": spike_rates,
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {n_spikes} spikes ({spike_rates['3.0σ']}%) "
                  f"in {runs} clusters, mean_mag={np.mean(spike_mags):.1f}")

    return {
        "name": "EXP-671: Spike detector",
        "mean_3s_rate": round(float(np.mean([r["spike_rate_3s"] for r in results])), 3),
        "mean_clusters_per_patient": round(float(np.mean([r["spike_clusters"] for r in results]))),
        "per_patient": results,
    }


def exp_672_spike_interpolation(patients, detail=False):
    """EXP-672: Restore R² after spike removal via interpolation."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid
        n = len(y)
        split = int(n * 0.7)

        # baseline R²
        r2_base, _, _ = _fit_ridge(X[:split], y[:split], X[split:], y[split:])

        # inject 1% spikes into test features
        rng = np.random.RandomState(42)
        X_test = X[split:].copy()
        y_test = y[split:]
        n_test = len(y_test)
        n_spikes = max(1, n_test // 100)
        spike_idx = rng.choice(n_test, n_spikes, replace=False)
        X_spiked = X_test.copy()
        X_spiked[spike_idx, :6] += rng.choice([-50, 50], (n_spikes, 1))

        r2_spiked, _, _ = _fit_ridge(X[:split], y[:split], X_spiked, y_test)

        # method 1: detect and zero-out spikes
        X_zeroed = X_spiked.copy()
        valid = np.isfinite(X_spiked[:, 0])
        mu_f = np.nanmean(X_spiked[valid, 0])
        sigma_f = np.nanstd(X_spiked[valid, 0])
        detected = np.abs(X_spiked[:, 0] - mu_f) > 3 * sigma_f
        X_zeroed[detected, :6] = 0
        r2_zeroed, _, _ = _fit_ridge(X[:split], y[:split], X_zeroed, y_test)

        # method 2: detect and interpolate
        X_interp = X_spiked.copy()
        for col in range(6):
            for i in np.where(detected)[0]:
                # linear interpolation from neighbors
                left = X_spiked[max(0, i - 1), col] if i > 0 and not detected[max(0, i - 1)] else 0
                right = X_spiked[min(n_test - 1, i + 1), col] if i < n_test - 1 and not detected[min(n_test - 1, i + 1)] else 0
                X_interp[i, col] = (left + right) / 2
        r2_interp, _, _ = _fit_ridge(X[:split], y[:split], X_interp, y_test)

        recovery_zero = (r2_zeroed - r2_spiked) / max(r2_base - r2_spiked, 0.001) * 100
        recovery_interp = (r2_interp - r2_spiked) / max(r2_base - r2_spiked, 0.001) * 100

        pr = {
            "patient": p["name"],
            "r2_base": round(float(r2_base), 3),
            "r2_spiked": round(float(r2_spiked), 3),
            "r2_zeroed": round(float(r2_zeroed), 3),
            "r2_interp": round(float(r2_interp), 3),
            "recovery_zero_pct": round(float(recovery_zero), 1),
            "recovery_interp_pct": round(float(recovery_interp), 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: base={r2_base:.3f} spiked={r2_spiked:.3f} "
                  f"zeroed={r2_zeroed:.3f}({recovery_zero:.0f}% recovery) "
                  f"interp={r2_interp:.3f}({recovery_interp:.0f}% recovery)")

    return {
        "name": "EXP-672: Spike interpolation",
        "mean_recovery_zero": round(float(np.mean([r["recovery_zero_pct"] for r in results])), 1),
        "mean_recovery_interp": round(float(np.mean([r["recovery_interp_pct"] for r in results])), 1),
        "per_patient": results,
    }


def exp_673_hourly_aggregation(patients, detail=False):
    """EXP-673: Hourly-averaged flux for clinical interpretability."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(bg), len(ts))

        hours = pd.DatetimeIndex(ts[:n]).hour
        hourly = {}
        for h in range(24):
            mask = hours == h
            if mask.sum() < 10:
                continue
            hourly[h] = {
                "mean_bg": round(float(np.nanmean(bg[:n][mask])), 1),
                "mean_supply": round(float(np.nanmean(supply[:n][mask])), 1),
                "mean_demand": round(float(np.nanmean(demand[:n][mask])), 1),
                "mean_net": round(float(np.nanmean(net[:n][mask])), 1),
                "tir": round(float(np.mean((bg[:n][mask] >= 70) & (bg[:n][mask] <= 180)) * 100), 1),
            }

        # find worst and best hours
        if hourly:
            worst_hour = min(hourly, key=lambda h: hourly[h]["tir"])
            best_hour = max(hourly, key=lambda h: hourly[h]["tir"])
            tir_range = hourly[best_hour]["tir"] - hourly[worst_hour]["tir"]
        else:
            worst_hour = best_hour = 0
            tir_range = 0

        pr = {
            "patient": p["name"],
            "worst_hour": worst_hour,
            "worst_tir": hourly.get(worst_hour, {}).get("tir", 0),
            "best_hour": best_hour,
            "best_tir": hourly.get(best_hour, {}).get("tir", 0),
            "tir_range": round(tir_range, 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: worst={worst_hour}:00 TIR={hourly.get(worst_hour, {}).get('tir', 0):.0f}% "
                  f"best={best_hour}:00 TIR={hourly.get(best_hour, {}).get('tir', 0):.0f}% "
                  f"range={tir_range:.0f}pp")

    return {
        "name": "EXP-673: Hourly aggregation",
        "mean_tir_range": round(float(np.mean([r["tir_range"] for r in results])), 1),
        "per_patient": results,
    }


def exp_674_daily_summary(patients, detail=False):
    """EXP-674: Daily flux summaries predict next-day TIR."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(bg), len(ts))

        dates = pd.DatetimeIndex(ts[:n]).date
        unique_dates = sorted(set(dates))
        if len(unique_dates) < 14:
            continue

        # compute daily summaries
        daily_tir = []
        daily_mean_net = []
        daily_cv = []
        daily_demand = []
        for d in unique_dates:
            mask = dates == d
            bg_d = bg[:n][mask]
            valid = np.isfinite(bg_d)
            if valid.sum() < 100:
                daily_tir.append(np.nan)
                daily_mean_net.append(np.nan)
                daily_cv.append(np.nan)
                daily_demand.append(np.nan)
                continue
            daily_tir.append(np.mean((bg_d[valid] >= 70) & (bg_d[valid] <= 180)) * 100)
            daily_cv.append(np.nanstd(bg_d[valid]) / np.nanmean(bg_d[valid]) * 100)
            net_d = net[:n][mask]
            daily_mean_net.append(np.nanmean(net_d))
            daily_demand.append(np.nanmean(demand[:n][mask]))

        daily_tir = np.array(daily_tir)
        daily_mean_net = np.array(daily_mean_net)
        daily_cv = np.array(daily_cv)
        daily_demand = np.array(daily_demand)

        # predict next-day TIR from today's stats
        valid_pairs = ~(np.isnan(daily_tir[:-1]) | np.isnan(daily_tir[1:]) |
                        np.isnan(daily_mean_net[:-1]) | np.isnan(daily_cv[:-1]))
        if valid_pairs.sum() < 10:
            continue

        # today's TIR → tomorrow's TIR
        corr_tir = np.corrcoef(daily_tir[:-1][valid_pairs], daily_tir[1:][valid_pairs])[0, 1]
        corr_net = np.corrcoef(daily_mean_net[:-1][valid_pairs], daily_tir[1:][valid_pairs])[0, 1]
        corr_cv = np.corrcoef(daily_cv[:-1][valid_pairs], daily_tir[1:][valid_pairs])[0, 1]

        pr = {
            "patient": p["name"],
            "n_days": len(unique_dates),
            "corr_tir_tir": round(float(corr_tir), 3),
            "corr_net_tir": round(float(corr_net), 3),
            "corr_cv_tir": round(float(corr_cv), 3),
            "mean_daily_tir": round(float(np.nanmean(daily_tir)), 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {len(unique_dates)} days, "
                  f"r(TIR→TIR)={corr_tir:.3f} r(net→TIR)={corr_net:.3f} r(CV→TIR)={corr_cv:.3f}")

    return {
        "name": "EXP-674: Daily summary stats",
        "mean_corr_tir_tir": round(float(np.nanmean([r["corr_tir_tir"] for r in results])), 3),
        "mean_corr_net_tir": round(float(np.nanmean([r["corr_net_tir"] for r in results])), 3),
        "mean_corr_cv_tir": round(float(np.nanmean([r["corr_cv_tir"] for r in results])), 3),
        "per_patient": results,
    }


def exp_675_dawn_phenomenon(patients, detail=False):
    """EXP-675: Dawn phenomenon quantification per patient."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(bg), len(ts))

        hours = pd.DatetimeIndex(ts[:n]).hour

        # dawn = 04:00-08:00
        dawn_mask = (hours >= 4) & (hours < 8)
        # control = 00:00-04:00 (pre-dawn baseline)
        control_mask = (hours >= 0) & (hours < 4)
        # daytime = 10:00-16:00
        day_mask = (hours >= 10) & (hours < 16)

        if dawn_mask.sum() < 100 or control_mask.sum() < 100:
            continue

        dawn_bg = np.nanmean(bg[:n][dawn_mask])
        control_bg = np.nanmean(bg[:n][control_mask])
        day_bg = np.nanmean(bg[:n][day_mask])
        dawn_rise = dawn_bg - control_bg

        # dawn flux pattern
        dawn_supply = np.nanmean(supply[:n][dawn_mask])
        dawn_demand = np.nanmean(demand[:n][dawn_mask])
        control_supply = np.nanmean(supply[:n][control_mask])
        control_demand = np.nanmean(demand[:n][control_mask])

        # dawn residual (unexplained rise)
        n_resid = min(len(resid), n - 1)
        resid_hours = hours[1:n_resid + 1] if n_resid < n else hours[:n_resid]
        dawn_resid_mask = (resid_hours >= 4) & (resid_hours < 8)
        control_resid_mask = (resid_hours >= 0) & (resid_hours < 4)
        dawn_resid = np.nanmean(resid[:n_resid][dawn_resid_mask]) if dawn_resid_mask.sum() > 0 else 0
        control_resid = np.nanmean(resid[:n_resid][control_resid_mask]) if control_resid_mask.sum() > 0 else 0

        pr = {
            "patient": p["name"],
            "dawn_bg": round(float(dawn_bg), 1),
            "control_bg": round(float(control_bg), 1),
            "dawn_rise_mgdl": round(float(dawn_rise), 1),
            "dawn_supply": round(float(dawn_supply), 2),
            "dawn_demand": round(float(dawn_demand), 2),
            "dawn_residual": round(float(dawn_resid), 2),
            "control_residual": round(float(control_resid), 2),
            "residual_dawn_effect": round(float(dawn_resid - control_resid), 2),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: dawn={dawn_bg:.0f} control={control_bg:.0f} "
                  f"rise={dawn_rise:+.0f} mg/dL, resid_effect={dawn_resid - control_resid:+.2f}")

    return {
        "name": "EXP-675: Dawn phenomenon quantification",
        "mean_dawn_rise": round(float(np.mean([r["dawn_rise_mgdl"] for r in results])), 1),
        "mean_residual_effect": round(float(np.mean([r["residual_dawn_effect"] for r in results])), 2),
        "patients_with_dawn": sum(1 for r in results if r["dawn_rise_mgdl"] > 10),
        "per_patient": results,
    }


def exp_676_meal_response_profiling(patients, detail=False):
    """EXP-676: Meal response varies by time of day."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(bg), len(supply))
        hours = pd.DatetimeIndex(ts[:n]).hour

        # detect meals: carb_supply > 2.0 (significant carb activity)
        meal_mask = carb_supply[:n] > 2.0

        # meal windows
        windows = {
            "breakfast": (6, 10),
            "lunch": (11, 14),
            "dinner": (17, 21),
        }

        meal_profiles = {}
        for name, (h_start, h_end) in windows.items():
            window_mask = (hours >= h_start) & (hours < h_end) & meal_mask
            if window_mask.sum() < 50:
                meal_profiles[name] = {"n": 0}
                continue

            # mean carb supply during meals
            mean_carb = float(np.nanmean(carb_supply[:n][window_mask]))
            mean_demand = float(np.nanmean(demand[:n][window_mask]))
            mean_bg = float(np.nanmean(bg[:n][window_mask]))

            # post-meal BG peak (look 1-2h after meal start)
            # simplified: BG during meal window
            meal_profiles[name] = {
                "n": int(window_mask.sum()),
                "mean_carb_supply": round(mean_carb, 2),
                "mean_demand": round(mean_demand, 2),
                "mean_bg": round(mean_bg, 1),
                "supply_demand_ratio": round(mean_carb / max(mean_demand, 0.1), 2),
            }

        pr = {
            "patient": p["name"],
            **{f"{k}_n": v.get("n", 0) for k, v in meal_profiles.items()},
            **{f"{k}_ratio": v.get("supply_demand_ratio", 0) for k, v in meal_profiles.items() if v.get("n", 0) > 0},
            **{f"{k}_bg": v.get("mean_bg", 0) for k, v in meal_profiles.items() if v.get("n", 0) > 0},
        }
        results.append(pr)
        if detail:
            parts = []
            for name in ["breakfast", "lunch", "dinner"]:
                mp = meal_profiles[name]
                if mp.get("n", 0) > 0:
                    parts.append(f"{name}: BG={mp['mean_bg']:.0f} ratio={mp['supply_demand_ratio']:.2f}")
            print(f"    {p['name']}: {', '.join(parts) if parts else 'no meals detected'}")

    return {
        "name": "EXP-676: Meal response profiling",
        "n_patients": len(results),
        "per_patient": results,
    }


def exp_677_exercise_detection(patients, detail=False):
    """EXP-677: Exercise detection via negative demand residuals."""
    import pandas as pd
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(resid), len(ts) - 1)

        valid = np.isfinite(resid[:n])
        # exercise signature: BG drops but demand is LOW (not insulin-driven)
        # detect: resid < -2σ AND demand < median AND carb_supply < 0.5 (no meal)
        mu = np.nanmean(resid[:n][valid])
        sigma = np.nanstd(resid[:n][valid])
        median_demand = np.nanmedian(demand[:n])

        exercise_mask = (
            (resid[:n] < mu - 2 * sigma) &
            (demand[1:n + 1] < median_demand) &
            (carb_supply[1:n + 1] < 0.5) &
            valid
        )

        n_exercise = int(exercise_mask.sum())
        exercise_rate = float(exercise_mask.mean() * 100)

        # timing distribution
        hours = pd.DatetimeIndex(ts[1:n + 1]).hour
        if n_exercise > 10:
            exercise_hours = hours[exercise_mask]
            morning = int(np.sum((exercise_hours >= 6) & (exercise_hours < 12)))
            afternoon = int(np.sum((exercise_hours >= 12) & (exercise_hours < 18)))
            evening = int(np.sum((exercise_hours >= 18) & (exercise_hours < 22)))
            night = n_exercise - morning - afternoon - evening
        else:
            morning = afternoon = evening = night = 0

        # BG during detected exercise
        exercise_bg = np.nanmean(bg[1:n + 1][exercise_mask]) if n_exercise > 0 else np.nan

        pr = {
            "patient": p["name"],
            "n_exercise_events": n_exercise,
            "exercise_rate_pct": round(exercise_rate, 2),
            "exercise_bg": round(float(exercise_bg), 1) if not np.isnan(exercise_bg) else None,
            "morning": morning,
            "afternoon": afternoon,
            "evening": evening,
            "night": night,
        }
        results.append(pr)
        if detail:
            bg_str = f"{exercise_bg:.0f}" if not np.isnan(exercise_bg) else "N/A"
            print(f"    {p['name']}: {n_exercise} events ({exercise_rate:.1f}%) "
                  f"bg={bg_str} "
                  f"morning={morning} afternoon={afternoon} evening={evening}")

    return {
        "name": "EXP-677: Exercise detection",
        "mean_exercise_rate": round(float(np.mean([r["exercise_rate_pct"] for r in results])), 2),
        "per_patient": results,
    }


def exp_678_error_bounds(patients, detail=False):
    """EXP-678: Bootstrap prediction intervals."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid
        n = len(y)
        split = int(n * 0.7)

        # point prediction
        r2_base, pred_base, w_base = _fit_ridge(X[:split], y[:split], X[split:], y[split:])

        # bootstrap: resample training data 50 times
        rng = np.random.RandomState(42)
        boot_preds = []
        X_tr, y_tr = X[:split], y[:split]
        mask_tr = np.all(np.isfinite(X_tr), axis=1) & np.isfinite(y_tr)
        X_tr_clean = X_tr[mask_tr]
        y_tr_clean = y_tr[mask_tr]
        n_clean = len(y_tr_clean)

        for _ in range(50):
            idx = rng.choice(n_clean, n_clean, replace=True)
            _, pred_b, _ = _fit_ridge(X_tr_clean[idx], y_tr_clean[idx], X[split:])
            boot_preds.append(pred_b)

        boot_preds = np.array(boot_preds)  # (50, n_test)

        # compute 95% PI: parameter uncertainty + residual noise
        mask_te = np.all(np.isfinite(X[split:]), axis=1) & np.isfinite(y[split:])
        valid_cols = np.all(np.isfinite(boot_preds), axis=0) & mask_te

        if valid_cols.sum() < 100:
            continue

        # residual noise on training set
        mask_tr_full = np.all(np.isfinite(X[:split]), axis=1) & np.isfinite(y[:split])
        if mask_tr_full.sum() > 100:
            train_resid = y[:split][mask_tr_full] - X[:split][mask_tr_full] @ w_base
            resid_std = float(np.std(train_resid))
        else:
            resid_std = float(np.nanstd(y[:split]))

        # PI = bootstrap percentile ± residual noise
        boot_valid = boot_preds[:, valid_cols]
        param_lower = np.percentile(boot_valid, 2.5, axis=0)
        param_upper = np.percentile(boot_valid, 97.5, axis=0)
        lower = param_lower - 1.96 * resid_std
        upper = param_upper + 1.96 * resid_std
        ci_width = upper - lower
        mean_ci = float(np.mean(ci_width))

        # coverage: what fraction of true values fall within the PI?
        y_valid = y[split:][valid_cols]
        pred_valid = pred_base[valid_cols]
        coverage = float(np.mean((y_valid >= lower) & (y_valid <= upper)) * 100)

        pr = {
            "patient": p["name"],
            "r2": round(float(r2_base), 3),
            "mean_ci_width": round(mean_ci, 2),
            "coverage_pct": round(coverage, 1),
            "target_coverage": 95.0,
            "calibrated": abs(coverage - 95.0) < 5,
        }
        results.append(pr)
        if detail:
            cal = "✓" if pr["calibrated"] else "✗"
            print(f"    {p['name']}: R²={r2_base:.3f} CI_width={mean_ci:.2f} "
                  f"coverage={coverage:.1f}% {cal}")

    n_cal = sum(1 for r in results if r["calibrated"])

    return {
        "name": "EXP-678: Error bounds",
        "mean_coverage": round(float(np.mean([r["coverage_pct"] for r in results])), 1),
        "mean_ci_width": round(float(np.mean([r["mean_ci_width"] for r in results])), 2),
        "n_calibrated": n_cal,
        "per_patient": results,
    }


def exp_679_model_staleness(patients, detail=False):
    """EXP-679: Model accuracy decay without retraining."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        X = _build_joint_features(resid, bg, demand)
        y = resid
        n = len(y)

        # train on first 30 days
        train_end = min(30 * 288, int(n * 0.3))
        if train_end < 1000:
            continue

        # test at different time horizons
        _, _, w = _fit_ridge(X[:train_end], y[:train_end], X[:train_end])

        horizons = [30, 60, 90, 120, 150]
        day_r2s = {}
        for days in horizons:
            test_start = days * 288
            test_end = min((days + 30) * 288, n)
            if test_start >= n or test_end - test_start < 288:
                continue
            X_te = X[test_start:test_end]
            y_te = y[test_start:test_end]
            mask = np.all(np.isfinite(X_te), axis=1) & np.isfinite(y_te)
            if mask.sum() < 100:
                continue
            pred = X_te[mask] @ w
            ss_res = np.sum((y_te[mask] - pred) ** 2)
            ss_tot = np.sum((y_te[mask] - np.mean(y_te[mask])) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
            day_r2s[days] = round(float(r2), 3)

        if not day_r2s:
            continue

        # fresh model at each horizon for comparison
        fresh_r2s = {}
        for days in horizons:
            test_start = days * 288
            test_end = min((days + 30) * 288, n)
            if test_start >= n or test_end - test_start < 288:
                continue
            train_start = max(0, test_start - 30 * 288)
            r2_fresh, _, _ = _fit_ridge(X[train_start:test_start], y[train_start:test_start],
                                         X[test_start:test_end], y[test_start:test_end])
            fresh_r2s[days] = round(float(r2_fresh), 3)

        pr = {
            "patient": p["name"],
            "stale_r2": day_r2s,
            "fresh_r2": fresh_r2s,
        }
        results.append(pr)
        if detail:
            parts = []
            for d in sorted(day_r2s):
                stale = day_r2s[d]
                fresh = fresh_r2s.get(d, "?")
                parts.append(f"{d}d: stale={stale} fresh={fresh}")
            print(f"    {p['name']}: {', '.join(parts)}")

    return {
        "name": "EXP-679: Model staleness",
        "n_patients": len(results),
        "per_patient": results,
    }


def exp_680_clinical_validation(patients, detail=False):
    """EXP-680: Compare flux-based recommendations with standard clinical rules."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out

        valid = np.isfinite(bg)
        tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)) * 100)
        tbr = float(np.mean(bg[valid] < 70) * 100)
        tar = float(np.mean(bg[valid] > 180) * 100)
        cv = float(np.nanstd(bg[valid]) / np.nanmean(bg[valid]) * 100)
        mean_bg = float(np.nanmean(bg[valid]))

        # standard clinical rules
        clinical_actions = []
        if tar > 30:
            clinical_actions.append("increase_total_daily_insulin")
        if tbr > 4:
            clinical_actions.append("decrease_basal_or_CR")
        if cv > 36:
            clinical_actions.append("review_meal_timing")
        if mean_bg > 180:
            clinical_actions.append("tighten_ISF")

        # flux-based recommendations (from EXP-657 approach)
        flux_actions = []
        mean_net = float(np.nanmean(net))
        if mean_net > 1.0:
            flux_actions.append("increase_total_daily_insulin")
        elif mean_net < -1.0:
            flux_actions.append("decrease_total_daily_insulin")

        # carb-specific
        meal_mask = carb_supply > 2.0
        if meal_mask.sum() > 100:
            meal_net = float(np.nanmean(net[meal_mask]))
            if meal_net > 2.0:
                flux_actions.append("decrease_CR")
            elif meal_net < -2.0:
                flux_actions.append("increase_CR")

        # basal-specific
        basal_mask = carb_supply < 0.5
        if basal_mask.sum() > 100:
            basal_net = float(np.nanmean(net[basal_mask]))
            if basal_net > 1.0:
                flux_actions.append("increase_basal")
            elif basal_net < -1.0:
                flux_actions.append("decrease_basal")

        # agreement
        clinical_set = set(clinical_actions)
        flux_set = set(flux_actions)
        overlap = clinical_set & flux_set
        agreement = len(overlap) / max(len(clinical_set | flux_set), 1) * 100

        pr = {
            "patient": p["name"],
            "tir": round(tir, 1),
            "tbr": round(tbr, 1),
            "tar": round(tar, 1),
            "cv": round(cv, 1),
            "clinical_actions": clinical_actions,
            "flux_actions": flux_actions,
            "agreement_pct": round(agreement, 0),
            "n_clinical": len(clinical_actions),
            "n_flux": len(flux_actions),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: clinical={clinical_actions} flux={flux_actions} "
                  f"agreement={agreement:.0f}%")

    return {
        "name": "EXP-680: Clinical action validation",
        "mean_agreement": round(float(np.mean([r["agreement_pct"] for r in results])), 1),
        "per_patient": results,
    }


# ── runner ──────────────────────────────────────────────────────────

ALL_EXPERIMENTS = [
    ("EXP-671", exp_671_spike_detector),
    ("EXP-672", exp_672_spike_interpolation),
    ("EXP-673", exp_673_hourly_aggregation),
    ("EXP-674", exp_674_daily_summary),
    ("EXP-675", exp_675_dawn_phenomenon),
    ("EXP-676", exp_676_meal_response_profiling),
    ("EXP-677", exp_677_exercise_detection),
    ("EXP-678", exp_678_error_bounds),
    ("EXP-679", exp_679_model_staleness),
    ("EXP-680", exp_680_clinical_validation),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-patients", type=int, default=11)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--only", type=str, default=None)
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
