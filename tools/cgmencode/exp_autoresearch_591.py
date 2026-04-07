#!/usr/bin/env python3
"""EXP-591–600: Hypo modeling, correction ISF, production readiness.

Addresses the two biggest gaps identified in EXP-511-590:
1. Hypo range R²=0.055 (model fails in <70 mg/dL)
2. 62% correction failures (ISF may be too low)
Plus production readiness experiments for deployment.
"""

import argparse, json, os, sys, warnings
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

# ── bootstrap ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

SAVE_DIR = Path("externals/experiments")
SAVE_DIR.mkdir(parents=True, exist_ok=True)
PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


# ── helpers from prior scripts ──────────────────────────────────

def _bg_col(df):
    return "glucose" if "glucose" in df.columns else "sgv"


def _compute_flux_and_ar(df, pk, lags=6, reg=1e-6):
    """Compute flux decomposition + AR(6) model. Returns dict with predictions."""
    sd = compute_supply_demand(df, pk)
    bg = df[_bg_col(df)].values.astype(float)
    valid = np.isfinite(bg)
    n = len(bg)

    # flux prediction on valid points
    flux_pred = np.full(n, np.nan)
    demand = sd.get("demand", np.zeros(n))
    supply = sd.get("supply", np.zeros(n))
    hepatic = sd.get("hepatic", np.zeros(n))
    bg_decay = sd.get("bg_decay", np.zeros(n))
    flux_pred = demand + supply + hepatic + bg_decay

    # dBG on contiguous valid
    idx_v = np.where(valid)[0]
    bg_v = bg[idx_v]
    dbg_full = np.full(n, np.nan)
    dbg_v = np.diff(bg_v)
    for i in range(len(dbg_v)):
        dbg_full[idx_v[i]] = dbg_v[i]

    # AR residuals
    flux_resid = np.full(n, np.nan)
    for i in range(n):
        if np.isfinite(dbg_full[i]) and np.isfinite(flux_pred[i]):
            flux_resid[i] = dbg_full[i] - flux_pred[i]

    # fit AR(6) on training (first 80%)
    fr = flux_resid.copy()
    n_train = int(0.8 * n)
    rows_X, rows_y = [], []
    for t in range(lags, n_train):
        lag_vals = [fr[t - l] for l in range(1, lags + 1)]
        if all(np.isfinite(lag_vals)) and np.isfinite(fr[t]):
            rows_X.append(lag_vals)
            rows_y.append(fr[t])

    ar_pred = np.full(n, np.nan)
    ar_coef = np.zeros(lags)
    if len(rows_X) > lags + 2:
        X = np.array(rows_X)
        y = np.array(rows_y)
        XtX = X.T @ X + reg * np.eye(lags)
        Xty = X.T @ y
        ar_coef = np.linalg.solve(XtX, Xty)

        # predict on all data
        for t in range(lags, n):
            lag_vals = [fr[t - l] for l in range(1, lags + 1)]
            if all(np.isfinite(lag_vals)):
                ar_pred[t] = np.sum(ar_coef * lag_vals)

    combined_pred = np.full(n, np.nan)
    for t in range(n):
        if np.isfinite(flux_pred[t]) and np.isfinite(ar_pred[t]):
            combined_pred[t] = flux_pred[t] + ar_pred[t]

    return {
        "bg": bg, "dbg": dbg_full, "flux_pred": flux_pred,
        "ar_pred": ar_pred, "combined_pred": combined_pred,
        "flux_resid": flux_resid, "demand": demand, "supply": supply,
        "hepatic": hepatic, "bg_decay": bg_decay, "valid": valid,
        "sd": sd, "ar_coef": ar_coef, "n_train": n_train,
    }


def _compute_settings_score(df, pk, result):
    """Compute 5-component settings score (0-100). Reused from EXP-580."""
    bg = result["bg"]
    valid = result["valid"]
    bg_v = bg[valid & np.isfinite(bg)]
    n = len(bg_v)
    if n < 100:
        return {"composite": 50.0, "components": {}}

    # 1. TIR (70-180)
    tir = np.mean((bg_v >= 70) & (bg_v <= 180)) * 100

    # 2. Coefficient of variation
    cv = np.std(bg_v) / np.mean(bg_v) * 100 if np.mean(bg_v) > 0 else 50

    # 3. Correction energy (mean absolute demand when BG > 180)
    demand = result["demand"]
    high_mask = (bg > 180) & valid
    ce = np.mean(np.abs(demand[high_mask])) if np.sum(high_mask) > 10 else 0

    # 4. Hypo frequency (% time < 70)
    hypo_pct = np.mean(bg_v < 70) * 100

    # 5. Model R²
    dbg = result["dbg"]
    comb = result["combined_pred"]
    m = np.isfinite(dbg) & np.isfinite(comb)
    if np.sum(m) > 10:
        ss_res = np.sum((dbg[m] - comb[m]) ** 2)
        ss_tot = np.sum((dbg[m] - np.mean(dbg[m])) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    else:
        r2 = 0

    # Score components (0-100 each, higher = better)
    s_tir = min(100, tir / 0.70)  # 70% TIR = 100
    s_cv = max(0, 100 - (cv - 20) * 3)  # CV<20 = 100, CV>53 = 0
    s_ce = max(0, 100 - ce * 20)  # low correction energy = good
    s_hypo = max(0, 100 - hypo_pct * 20)  # low hypo = good
    s_r2 = min(100, r2 * 150)  # R²=0.67 = 100

    composite = 0.30 * s_tir + 0.20 * s_cv + 0.20 * s_ce + 0.15 * s_hypo + 0.15 * s_r2
    return {
        "composite": round(composite, 1),
        "components": {
            "tir": round(s_tir, 1), "cv": round(s_cv, 1),
            "ce": round(s_ce, 1), "hypo": round(s_hypo, 1),
            "r2": round(s_r2, 1),
        },
        "raw": {
            "tir_pct": round(tir, 1), "cv_pct": round(cv, 1),
            "ce": round(ce, 3), "hypo_pct": round(hypo_pct, 2),
            "r2": round(r2, 3),
        },
    }


# ── EXP-591: Counter-regulatory response in hypo ──────────────────

def exp_591_counter_regulatory(patients, detail=False):
    """Model BG recovery from hypo using separate physics.

    In hypoglycemia (<70), counter-regulatory hormones (glucagon, epinephrine,
    cortisol) kick in, causing BG to rise faster than predicted by the linear
    flux model. We fit a separate model for the hypo range and compare R².
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        dbg = r["dbg"]
        comb = r["combined_pred"]
        valid = np.isfinite(dbg) & np.isfinite(comb) & np.isfinite(bg)

        # Split by BG range
        ranges = {
            "hypo": (0, 70),
            "low_normal": (70, 100),
            "normal": (100, 180),
            "high": (180, 250),
            "very_high": (250, 500),
        }

        range_r2 = {}
        for rname, (lo, hi) in ranges.items():
            mask = valid & (bg >= lo) & (bg < hi)
            if np.sum(mask) < 20:
                range_r2[rname] = {"r2": np.nan, "n": int(np.sum(mask))}
                continue
            ss_res = np.sum((dbg[mask] - comb[mask]) ** 2)
            ss_tot = np.sum((dbg[mask] - np.mean(dbg[mask])) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            range_r2[rname] = {"r2": round(r2, 4), "n": int(np.sum(mask))}

        # Counter-regulatory model: fit separate AR for hypo range
        hypo_mask = valid & (bg < 70) & np.isfinite(r["flux_resid"])
        hypo_idxs = np.where(hypo_mask)[0]

        # Recovery speed: mean dBG when BG < 70
        if len(hypo_idxs) > 5:
            hypo_dbg = dbg[hypo_mask]
            recovery_rate = float(np.mean(hypo_dbg))
            recovery_std = float(np.std(hypo_dbg))
            # How fast does BG exit hypo?
            exit_times = []
            in_hypo = False
            entry_t = 0
            for t in range(len(bg)):
                if not np.isfinite(bg[t]):
                    continue
                if bg[t] < 70 and not in_hypo:
                    in_hypo = True
                    entry_t = t
                elif bg[t] >= 70 and in_hypo:
                    exit_times.append(t - entry_t)
                    in_hypo = False
            mean_exit_time = float(np.mean(exit_times)) * 5 if exit_times else np.nan  # minutes
        else:
            recovery_rate = np.nan
            recovery_std = np.nan
            mean_exit_time = np.nan

        # Predicted vs actual recovery
        if len(hypo_idxs) > 10:
            # Model predicts dBG from flux+AR; actual dBG during hypo
            pred_hypo = comb[hypo_mask]
            actual_hypo = dbg[hypo_mask]
            # Bias: does model under-predict recovery?
            bias = float(np.mean(actual_hypo - pred_hypo))
            # Model says BG should change by X, actually changes by X+bias
        else:
            bias = np.nan

        results.append({
            "patient": p["name"],
            "range_r2": range_r2,
            "recovery_rate": round(recovery_rate, 2) if np.isfinite(recovery_rate) else None,
            "recovery_std": round(recovery_std, 2) if np.isfinite(recovery_std) else None,
            "mean_exit_min": round(mean_exit_time, 1) if np.isfinite(mean_exit_time) else None,
            "counter_reg_bias": round(bias, 3) if np.isfinite(bias) else None,
            "hypo_events": len([t for t in range(1, len(bg))
                               if np.isfinite(bg[t]) and bg[t] < 70
                               and np.isfinite(bg[t-1]) and bg[t-1] >= 70]),
        })

    # Summarize
    biases = [r["counter_reg_bias"] for r in results if r["counter_reg_bias"] is not None]
    exit_times = [r["mean_exit_min"] for r in results if r["mean_exit_min"] is not None]
    recovery_rates = [r["recovery_rate"] for r in results if r["recovery_rate"] is not None]

    summary = {
        "mean_counter_reg_bias": round(np.mean(biases), 3) if biases else None,
        "mean_exit_min": round(np.mean(exit_times), 1) if exit_times else None,
        "mean_recovery_rate": round(np.mean(recovery_rates), 2) if recovery_rates else None,
        "bias_positive_count": sum(1 for b in biases if b > 0),
        "n_patients_with_hypo": len(biases),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: exit={r['mean_exit_min']}min, "
                  f"bias={r['counter_reg_bias']}, events={r['hypo_events']}")

    return {"name": "Counter-Regulatory Response", "id": "EXP-591",
            "summary": summary, "patients": results}


# ── EXP-592: Hypo risk score from flux precursors ──────────────

def exp_592_hypo_risk(patients, detail=False):
    """Extract features 30-60min before hypo events to build risk score."""
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]
        supply = r["supply"]
        flux_resid = r["flux_resid"]

        # Find hypo onset events (first BG<70 after >=70)
        onsets = []
        for t in range(1, len(bg)):
            if (np.isfinite(bg[t]) and bg[t] < 70 and
                np.isfinite(bg[t-1]) and bg[t-1] >= 70):
                onsets.append(t)

        if len(onsets) < 3:
            results.append({"patient": p["name"], "n_hypos": len(onsets),
                            "features": None})
            continue

        # Extract features 30-60min (6-12 steps) before each onset
        pre_features = []
        for onset in onsets:
            window = slice(max(0, onset - 12), onset)
            bg_w = bg[window]
            dem_w = demand[window]
            sup_w = supply[window]
            fr_w = flux_resid[window]

            valid = np.isfinite(bg_w) & np.isfinite(dem_w)
            if np.sum(valid) < 4:
                continue

            feat = {
                "bg_at_onset": float(bg[onset]) if np.isfinite(bg[onset]) else None,
                "bg_30min_before": float(bg_w[valid][-1]) if np.sum(valid) > 0 else None,
                "bg_slope": float(np.polyfit(np.arange(np.sum(valid)),
                                            bg_w[valid], 1)[0]) if np.sum(valid) > 2 else None,
                "mean_demand": float(np.mean(dem_w[valid])),
                "mean_supply": float(np.mean(sup_w[np.isfinite(sup_w)])) if np.any(np.isfinite(sup_w)) else 0,
                "net_flux": float(np.mean(dem_w[valid])) + float(np.mean(sup_w[np.isfinite(sup_w)])) if np.any(np.isfinite(sup_w)) else 0,
                "residual_trend": float(np.mean(fr_w[np.isfinite(fr_w)])) if np.any(np.isfinite(fr_w)) else 0,
            }
            pre_features.append(feat)

        # Also extract features before NON-hypo periods (controls)
        non_hypo_features = []
        for t in range(12, len(bg), 50):  # sample every 50 steps
            if not (np.isfinite(bg[t]) and bg[t] >= 80 and bg[t] <= 150):
                continue
            window = slice(t - 12, t)
            bg_w = bg[window]
            dem_w = demand[window]
            valid_w = np.isfinite(bg_w) & np.isfinite(dem_w)
            if np.sum(valid_w) < 4:
                continue
            non_hypo_features.append({
                "bg_slope": float(np.polyfit(np.arange(np.sum(valid_w)),
                                            bg_w[valid_w], 1)[0]),
                "mean_demand": float(np.mean(dem_w[valid_w])),
            })

        # Compare pre-hypo vs control
        if pre_features and non_hypo_features:
            hypo_slopes = [f["bg_slope"] for f in pre_features if f["bg_slope"] is not None]
            ctrl_slopes = [f["bg_slope"] for f in non_hypo_features]
            hypo_demands = [f["mean_demand"] for f in pre_features]
            ctrl_demands = [f["mean_demand"] for f in non_hypo_features]

            slope_diff = float(np.mean(hypo_slopes) - np.mean(ctrl_slopes)) if hypo_slopes else None
            demand_diff = float(np.mean(hypo_demands) - np.mean(ctrl_demands))
        else:
            slope_diff = None
            demand_diff = None

        results.append({
            "patient": p["name"],
            "n_hypos": len(onsets),
            "n_features_extracted": len(pre_features),
            "mean_bg_slope_pre_hypo": round(np.mean([f["bg_slope"] for f in pre_features
                                                      if f["bg_slope"] is not None]), 3) if pre_features else None,
            "slope_diff_vs_control": round(slope_diff, 3) if slope_diff is not None else None,
            "demand_diff_vs_control": round(demand_diff, 3) if demand_diff is not None else None,
        })

    # Summary
    slope_diffs = [r["slope_diff_vs_control"] for r in results if r["slope_diff_vs_control"] is not None]
    demand_diffs = [r["demand_diff_vs_control"] for r in results if r["demand_diff_vs_control"] is not None]

    summary = {
        "mean_slope_diff": round(np.mean(slope_diffs), 3) if slope_diffs else None,
        "mean_demand_diff": round(np.mean(demand_diffs), 3) if demand_diffs else None,
        "slope_more_negative_pre_hypo": sum(1 for s in slope_diffs if s < 0),
        "n_patients_analyzable": len(slope_diffs),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: hypos={r['n_hypos']}, "
                  f"slope_diff={r['slope_diff_vs_control']}, "
                  f"demand_diff={r['demand_diff_vs_control']}")

    return {"name": "Hypo Risk Score", "id": "EXP-592",
            "summary": summary, "patients": results}


# ── EXP-593: Sensor noise floor characterization ──────────────

def exp_593_sensor_noise(patients, detail=False):
    """Characterize the CGM sensor noise structure across BG ranges.

    The 32% noise floor may have structure we can exploit:
    - Is noise constant across BG ranges? (MARD says no)
    - Is noise Gaussian? (important for Kalman assumptions)
    - Does noise change with sensor age?
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        dbg = r["dbg"]
        comb = r["combined_pred"]

        residuals = np.full(len(bg), np.nan)
        m = np.isfinite(dbg) & np.isfinite(comb)
        residuals[m] = dbg[m] - comb[m]

        # Noise by BG range
        ranges = {
            "hypo": (0, 70), "low": (70, 100), "normal": (100, 150),
            "high_normal": (150, 180), "high": (180, 250), "very_high": (250, 500),
        }
        noise_by_range = {}
        for rname, (lo, hi) in ranges.items():
            mask = np.isfinite(residuals) & (bg >= lo) & (bg < hi)
            if np.sum(mask) < 20:
                noise_by_range[rname] = None
                continue
            res_r = residuals[mask]
            noise_by_range[rname] = {
                "std": round(float(np.std(res_r)), 3),
                "mean": round(float(np.mean(res_r)), 3),
                "skew": round(float(np.mean(((res_r - np.mean(res_r)) / np.std(res_r)) ** 3)), 3)
                    if np.std(res_r) > 0 else 0,
                "kurtosis": round(float(np.mean(((res_r - np.mean(res_r)) / np.std(res_r)) ** 4) - 3), 3)
                    if np.std(res_r) > 0 else 0,
                "n": int(np.sum(mask)),
            }

        # Test Gaussianity: Kolmogorov-Smirnov-like via percentile comparison
        res_valid = residuals[np.isfinite(residuals)]
        if len(res_valid) > 100:
            # Compare empirical percentiles to Gaussian
            from scipy import stats
            _, ks_p = stats.normaltest(res_valid[:5000])  # limit for speed
            gaussian_p = round(float(ks_p), 6)
        else:
            gaussian_p = None

        # Noise vs time (sensor age proxy: use sequential position)
        n_valid = np.sum(np.isfinite(residuals))
        if n_valid > 100:
            quarters = np.array_split(np.where(np.isfinite(residuals))[0], 4)
            noise_by_quarter = []
            for q_idx in quarters:
                if len(q_idx) > 10:
                    noise_by_quarter.append(round(float(np.std(residuals[q_idx])), 3))
                else:
                    noise_by_quarter.append(None)
            noise_trend = (noise_by_quarter[-1] - noise_by_quarter[0]) / noise_by_quarter[0] \
                if noise_by_quarter[0] and noise_by_quarter[-1] else None
        else:
            noise_by_quarter = [None] * 4
            noise_trend = None

        results.append({
            "patient": p["name"],
            "noise_by_range": noise_by_range,
            "overall_std": round(float(np.std(res_valid)), 3) if len(res_valid) > 0 else None,
            "gaussian_p": gaussian_p,
            "is_gaussian": gaussian_p > 0.05 if gaussian_p is not None else None,
            "noise_by_quarter": noise_by_quarter,
            "noise_trend_pct": round(noise_trend * 100, 1) if noise_trend is not None else None,
        })

    # Summary
    hypo_stds = [r["noise_by_range"].get("hypo", {}).get("std") if r["noise_by_range"].get("hypo") else None for r in results]
    normal_stds = [r["noise_by_range"].get("normal", {}).get("std") if r["noise_by_range"].get("normal") else None for r in results]
    hypo_stds = [s for s in hypo_stds if s is not None]
    normal_stds = [s for s in normal_stds if s is not None]

    summary = {
        "mean_hypo_noise": round(np.mean(hypo_stds), 3) if hypo_stds else None,
        "mean_normal_noise": round(np.mean(normal_stds), 3) if normal_stds else None,
        "noise_ratio_hypo_vs_normal": round(np.mean(hypo_stds) / np.mean(normal_stds), 2)
            if hypo_stds and normal_stds else None,
        "gaussian_count": sum(1 for r in results if r.get("is_gaussian")),
        "n_patients": len(results),
        "mean_noise_trend_pct": round(np.mean([r["noise_trend_pct"] for r in results
                                                if r["noise_trend_pct"] is not None]), 1),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: overall_std={r['overall_std']}, "
                  f"gaussian={'Y' if r.get('is_gaussian') else 'N'}, "
                  f"trend={r['noise_trend_pct']}%")

    return {"name": "Sensor Noise Floor", "id": "EXP-593",
            "summary": summary, "patients": results}


# ── EXP-594: Effective vs Profile ISF ──────────────────────────

def exp_594_effective_isf(patients, detail=False):
    """Compare actual BG drop per correction unit to profile ISF.

    Profile ISF says "1U drops BG by X mg/dL", but what actually happens?
    Use high-demand periods when BG>180 to measure effective ISF.
    Note: demand is always positive (insulin action magnitude).
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]
        net = r["sd"].get("net", np.zeros(len(bg)))

        # Profile ISF
        isf_entries = df.attrs.get("isf_schedule", [])
        if isinstance(isf_entries, list) and isf_entries:
            isf_values = [e["value"] for e in isf_entries if "value" in e]
            profile_isf = float(np.mean(isf_values))
            if profile_isf < 15:
                profile_isf *= 18.0182
        else:
            profile_isf = None

        # Demand threshold: high demand = correction activity (top 20th percentile)
        dem_valid = demand[np.isfinite(demand)]
        if len(dem_valid) < 100:
            results.append({"patient": p["name"], "profile_isf": profile_isf,
                           "mean_effective_isf": None, "median_effective_isf": None,
                           "isf_ratio": None, "n_corrections": 0})
            continue
        dem_p80 = np.percentile(dem_valid, 80)

        # Find correction events: high BG (>160) with high demand (positive = insulin active)
        corrections = []
        t = 0
        while t < len(bg) - 24:
            if (np.isfinite(bg[t]) and bg[t] > 160 and
                np.isfinite(demand[t]) and demand[t] > dem_p80 and
                np.isfinite(net[t]) and net[t] < 0):  # net negative = insulin > supply
                bg_start = bg[t]
                window = bg[t:t+24]
                valid_w = np.isfinite(window)
                if np.sum(valid_w) > 4:
                    bg_min = np.nanmin(window)
                    bg_drop = bg_start - bg_min

                    # Demand integral over 2h (positive values = insulin action)
                    dem_window = demand[t:t+24]
                    dem_valid_w = dem_window[np.isfinite(dem_window)]
                    total_demand = float(np.sum(dem_valid_w)) * 5 / 60  # per-hour equivalent

                    if total_demand > 1.0 and bg_drop > 5:  # meaningful correction
                        effective_isf = bg_drop / (total_demand / profile_isf) if profile_isf else bg_drop
                        corrections.append({
                            "bg_start": float(bg_start),
                            "bg_drop": float(bg_drop),
                            "demand_integral": float(total_demand),
                            "bg_drop_per_demand": float(bg_drop / total_demand),
                        })
                t += 24
            else:
                t += 1

        if corrections:
            drop_per_demand = [c["bg_drop_per_demand"] for c in corrections]
            mean_dpd = float(np.mean(drop_per_demand))
            median_dpd = float(np.median(drop_per_demand))
        else:
            mean_dpd = None
            median_dpd = None

        # ISF ratio: how does effective drop compare to profile expectation?
        # Higher effective = ISF is working well; lower = ISF too conservative
        isf_ratio = mean_dpd / (profile_isf / 10) if (mean_dpd and profile_isf) else None

        results.append({
            "patient": p["name"],
            "profile_isf": round(profile_isf, 1) if profile_isf else None,
            "mean_bg_drop_per_demand": round(mean_dpd, 2) if mean_dpd else None,
            "median_bg_drop_per_demand": round(median_dpd, 2) if median_dpd else None,
            "isf_ratio": round(isf_ratio, 2) if isf_ratio else None,
            "n_corrections": len(corrections),
        })

    # Summary
    drops = [r["mean_bg_drop_per_demand"] for r in results if r["mean_bg_drop_per_demand"] is not None]
    n_corr = [r["n_corrections"] for r in results]
    summary = {
        "mean_bg_drop_per_demand": round(np.mean(drops), 2) if drops else None,
        "n_patients_with_corrections": sum(1 for n in n_corr if n > 0),
        "total_corrections": sum(n_corr),
        "mean_corrections_per_patient": round(np.mean(n_corr), 1),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: profile={r['profile_isf']}, "
                  f"drop/demand={r['mean_bg_drop_per_demand']}, "
                  f"n={r['n_corrections']}")

    return {"name": "Effective vs Profile ISF", "id": "EXP-594",
            "summary": summary, "patients": results}


# ── EXP-595: Insulin stacking detection ────────────────────────

def exp_595_stacking(patients, detail=False):
    """Detect insulin stacking (overlapping correction boluses).

    Stacking occurs when demand stays elevated for extended periods,
    indicating overlapping insulin action. Demand is always positive
    (represents insulin action magnitude). High demand spikes = corrections.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]

        # Detect demand spikes (correction boluses = HIGH positive demand)
        dem_valid = demand[np.isfinite(demand)]
        if len(dem_valid) < 100:
            continue
        spike_threshold = np.percentile(dem_valid, 95)  # top 5% = correction activity

        spikes = []
        for t in range(len(demand)):
            if np.isfinite(demand[t]) and demand[t] > spike_threshold:
                spikes.append(t)

        # Group into events (spikes within 3 steps are same event)
        events = []
        if spikes:
            current_event = [spikes[0]]
            for s in spikes[1:]:
                if s - current_event[-1] <= 3:
                    current_event.append(s)
                else:
                    events.append(current_event)
                    current_event = [s]
            events.append(current_event)

        # Detect stacking: events within DIA window (typically 6h = 72 steps)
        dia_steps = 72
        stacked_events = 0
        non_stacked_events = 0
        stacked_outcomes = []
        non_stacked_outcomes = []

        for i, event in enumerate(events):
            event_start = event[0]
            is_stacked = False
            for j in range(i + 1, len(events)):
                next_start = events[j][0]
                if next_start - event_start < dia_steps:
                    is_stacked = True
                    break
                elif next_start - event_start >= dia_steps:
                    break

            t_outcome = event_start + 24  # 2h
            if t_outcome < len(bg) and np.isfinite(bg[event_start]) and np.isfinite(bg[t_outcome]):
                bg_change = bg[t_outcome] - bg[event_start]
                if is_stacked:
                    stacked_events += 1
                    stacked_outcomes.append(float(bg_change))
                else:
                    non_stacked_events += 1
                    non_stacked_outcomes.append(float(bg_change))

        results.append({
            "patient": p["name"],
            "total_events": len(events),
            "stacked": stacked_events,
            "non_stacked": non_stacked_events,
            "stacking_rate": round(stacked_events / max(1, len(events)), 2),
            "mean_bg_change_stacked": round(float(np.mean(stacked_outcomes)), 1) if stacked_outcomes else None,
            "mean_bg_change_non_stacked": round(float(np.mean(non_stacked_outcomes)), 1) if non_stacked_outcomes else None,
        })

    # Summary
    stack_rates = [r["stacking_rate"] for r in results]
    stacked_bgs = [r["mean_bg_change_stacked"] for r in results if r["mean_bg_change_stacked"] is not None]
    non_stacked_bgs = [r["mean_bg_change_non_stacked"] for r in results if r["mean_bg_change_non_stacked"] is not None]

    summary = {
        "mean_stacking_rate": round(np.mean(stack_rates), 2),
        "mean_bg_change_stacked": round(np.mean(stacked_bgs), 1) if stacked_bgs else None,
        "mean_bg_change_non_stacked": round(np.mean(non_stacked_bgs), 1) if non_stacked_bgs else None,
        "stacking_helps": sum(1 for s, ns in zip(stacked_bgs, non_stacked_bgs)
                              if s is not None and ns is not None and s < ns),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: events={r['total_events']}, "
                  f"stacked={r['stacking_rate']:.0%}, "
                  f"ΔBG_stacked={r['mean_bg_change_stacked']}, "
                  f"ΔBG_non={r['mean_bg_change_non_stacked']}")

    return {"name": "Insulin Stacking Detection", "id": "EXP-595",
            "summary": summary, "patients": results}


# ── EXP-596: Overnight basal test (cleanest fasting window) ──

def exp_596_overnight_basal(patients, detail=False):
    """Use overnight fasting windows (00:00-06:00) as clean basal test.

    During overnight fasting with no recent boluses, BG change should be
    zero if basal is correct. Systematic drift indicates basal adjustment needed.
    Uses carb_supply (not total supply) to detect meal-free windows.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        carb_supply = r["sd"].get("carb_supply", np.zeros(len(bg)))

        # Get hours from DatetimeIndex
        if hasattr(df.index, 'hour'):
            hours = df.index.hour.values
        else:
            n = len(bg)
            hours = np.array([(t * 5 // 60) % 24 for t in range(n)])

        # Find overnight windows: 00:00-06:00 with no significant carb supply
        overnight_drifts = []

        # Walk through data looking for midnight crossings
        for t in range(len(bg) - 72):
            if hours[t] != 0:  # must start at midnight
                continue

            # Check this is a 6h overnight window
            end_t = min(t + 72, len(bg))
            bg_w = bg[t:end_t]
            cs_w = carb_supply[t:end_t]

            # No carb activity (carb_supply near zero)
            cs_valid = cs_w[np.isfinite(cs_w)]
            if len(cs_valid) > 0 and np.max(cs_valid) > 0.5:
                continue  # meal/carb detected

            # Enough valid BG
            bg_valid_mask = np.isfinite(bg_w)
            if np.sum(bg_valid_mask) < 36:
                continue

            bg_start = bg_w[bg_valid_mask][0]
            bg_end = bg_w[bg_valid_mask][-1]
            drift = bg_end - bg_start
            overnight_drifts.append(float(drift))

        if overnight_drifts:
            mean_drift = float(np.mean(overnight_drifts))
            drift_direction = "rising" if mean_drift > 5 else "falling" if mean_drift < -5 else "stable"
            recommendation = ("increase basal" if mean_drift > 10 else
                            "decrease basal" if mean_drift < -10 else
                            "basal adequate")
        else:
            mean_drift = None
            drift_direction = None
            recommendation = None

        results.append({
            "patient": p["name"],
            "n_clean_nights": len(overnight_drifts),
            "mean_overnight_drift": round(mean_drift, 1) if mean_drift is not None else None,
            "drift_std": round(float(np.std(overnight_drifts)), 1) if overnight_drifts else None,
            "drift_direction": drift_direction,
            "recommendation": recommendation,
        })

    # Summary
    drifts = [r["mean_overnight_drift"] for r in results if r["mean_overnight_drift"] is not None]
    summary = {
        "mean_overnight_drift": round(np.mean(drifts), 1) if drifts else None,
        "rising_count": sum(1 for r in results if r["drift_direction"] == "rising"),
        "falling_count": sum(1 for r in results if r["drift_direction"] == "falling"),
        "stable_count": sum(1 for r in results if r["drift_direction"] == "stable"),
        "n_patients": len(drifts),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: nights={r['n_clean_nights']}, "
                  f"drift={r['mean_overnight_drift']}mg/dL, "
                  f"→{r['recommendation']}")

    return {"name": "Overnight Basal Test", "id": "EXP-596",
            "summary": summary, "patients": results}


# ── EXP-597: Minimal data requirements ─────────────────────────

def exp_597_minimal_data(patients, detail=False):
    """How many days of data are needed for a reliable settings score?

    Bootstrap score stability: compute score on 3, 7, 14, 30, 60, 90 days
    and measure score variance at each duration.
    """
    results = []
    durations_days = [3, 7, 14, 30, 60, 90]
    steps_per_day = 288  # 5-min intervals

    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        n = len(bg)
        total_days = n // steps_per_day

        duration_scores = {}
        for dur in durations_days:
            if dur > total_days:
                duration_scores[str(dur)] = None
                continue

            steps = dur * steps_per_day
            # Bootstrap: sample 10 random windows of this duration
            scores = []
            for _ in range(min(10, max(1, total_days // dur))):
                start = np.random.randint(0, max(1, n - steps))
                end = start + steps

                # Mini score: just TIR + CV (faster than full score)
                bg_w = bg[start:end]
                bg_valid = bg_w[np.isfinite(bg_w)]
                if len(bg_valid) < steps * 0.5:
                    continue

                tir = np.mean((bg_valid >= 70) & (bg_valid <= 180)) * 100
                cv = np.std(bg_valid) / np.mean(bg_valid) * 100

                s_tir = min(100, tir / 0.70)
                s_cv = max(0, 100 - (cv - 20) * 3)
                mini_score = 0.6 * s_tir + 0.4 * s_cv
                scores.append(mini_score)

            if scores:
                duration_scores[str(dur)] = {
                    "mean": round(float(np.mean(scores)), 1),
                    "std": round(float(np.std(scores)), 1),
                    "cv": round(float(np.std(scores) / np.mean(scores) * 100), 1) if np.mean(scores) > 0 else None,
                    "n_samples": len(scores),
                }
            else:
                duration_scores[str(dur)] = None

        results.append({
            "patient": p["name"],
            "total_days": total_days,
            "score_by_duration": duration_scores,
        })

    # Find minimum reliable duration (CV < 10%)
    min_reliable = {}
    for dur in durations_days:
        cvs = []
        for r in results:
            d = r["score_by_duration"].get(str(dur))
            if d and d.get("cv") is not None:
                cvs.append(d["cv"])
        if cvs:
            min_reliable[str(dur)] = {
                "mean_cv": round(np.mean(cvs), 1),
                "reliable": np.mean(cvs) < 10,
            }

    summary = {
        "score_stability_by_duration": min_reliable,
        "minimum_reliable_days": None,
    }
    for dur in durations_days:
        if min_reliable.get(str(dur), {}).get("reliable"):
            summary["minimum_reliable_days"] = dur
            break

    if detail:
        for dur_str, info in min_reliable.items():
            print(f"  {dur_str} days: CV={info['mean_cv']}% {'✓' if info['reliable'] else '✗'}")

    return {"name": "Minimal Data Requirements", "id": "EXP-597",
            "summary": summary, "patients": results}


# ── EXP-598: AID aggressiveness index ──────────────────────────

def exp_598_aid_aggressiveness(patients, detail=False):
    """Quantify how aggressively each patient's AID system corrects.

    Measure demand intensity when BG is elevated. Higher demand = more
    aggressive correction. Demand is always positive (insulin action magnitude).
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]
        net = r["sd"].get("net", np.zeros(len(bg)))

        valid = np.isfinite(demand) & np.isfinite(bg)
        if np.sum(valid) < 100:
            continue

        dem_v = demand[valid]
        bg_v = bg[valid]
        net_v = net[valid]

        # Correction intensity: mean demand when BG > 150
        high_mask = bg_v > 150
        if np.sum(high_mask) > 10:
            correction_intensity = float(np.mean(dem_v[high_mask]))
        else:
            correction_intensity = 0

        # Response speed: how quickly does demand increase after BG crosses 180?
        crossings = []
        for t in range(1, len(bg_v)):
            if bg_v[t] > 180 and bg_v[t-1] <= 180:
                crossings.append(t)

        response_demands = []
        for c in crossings:
            if c + 6 < len(dem_v):
                resp = dem_v[c:c+6]
                response_demands.append(float(np.mean(resp)))

        mean_response = float(np.mean(response_demands)) if response_demands else 0

        # Aggressiveness index: correction intensity × response magnitude
        aggressiveness = correction_intensity * mean_response / 100  # normalize

        # Net flux when high: negative net = insulin dominates
        high_net = float(np.mean(net_v[high_mask])) if np.sum(high_mask) > 10 else 0

        # Suspend frequency: how often is demand near zero when BG is dropping?
        bg_dropping = np.gradient(bg_v) < -1
        low_demand = dem_v < np.percentile(dem_v, 20)
        suspend_rate = float(np.mean(bg_dropping & low_demand))

        results.append({
            "patient": p["name"],
            "correction_intensity": round(correction_intensity, 2),
            "mean_response_at_180": round(mean_response, 2),
            "aggressiveness_index": round(aggressiveness, 3),
            "high_bg_net_flux": round(high_net, 2),
            "suspend_rate": round(suspend_rate, 3),
            "n_crossings_180": len(crossings),
        })

    # Rank by aggressiveness
    results.sort(key=lambda x: x["aggressiveness_index"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    summary = {
        "most_aggressive": results[0]["patient"] if results else None,
        "least_aggressive": results[-1]["patient"] if results else None,
        "mean_aggressiveness": round(np.mean([r["aggressiveness_index"] for r in results]), 3),
        "mean_suspend_rate": round(np.mean([r["suspend_rate"] for r in results]), 3),
    }

    if detail:
        for r in results:
            print(f"  #{r['rank']} {r['patient']}: aggr={r['aggressiveness_index']:.3f}, "
                  f"suspend={r['suspend_rate']:.1%}")

    return {"name": "AID Aggressiveness Index", "id": "EXP-598",
            "summary": summary, "patients": results}


# ── EXP-599: Patient similarity clustering ─────────────────────

def exp_599_patient_clustering(patients, detail=False):
    """Cluster patients by metabolic profile similarity.

    Use settings score components + flux characteristics as features.
    Find which patients are most alike — enables transfer learning.
    """
    features_list = []
    patient_names = []

    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]
        supply = r["supply"]

        valid = np.isfinite(bg) & np.isfinite(demand)
        if np.sum(valid) < 100:
            continue

        bg_v = bg[valid]
        dem_v = demand[valid]
        sup_v = supply[np.isfinite(supply)]

        # Feature vector per patient
        features = [
            np.mean(bg_v),                          # mean BG
            np.std(bg_v),                            # BG variability
            np.mean((bg_v >= 70) & (bg_v <= 180)),  # TIR
            np.mean(bg_v < 70),                      # hypo fraction
            np.mean(bg_v > 250),                     # severe hyper fraction
            np.mean(np.abs(dem_v)),                   # mean demand intensity
            np.std(dem_v),                            # demand variability
            np.mean(np.abs(sup_v)) if len(sup_v) > 0 else 0,  # supply intensity
            np.mean(r["flux_resid"][np.isfinite(r["flux_resid"])]),  # residual bias
            np.std(r["flux_resid"][np.isfinite(r["flux_resid"])]),   # residual noise
        ]
        features_list.append(features)
        patient_names.append(p["name"])

    if len(features_list) < 3:
        return {"name": "Patient Clustering", "id": "EXP-599",
                "summary": {"error": "too few patients"}, "patients": []}

    X = np.array(features_list)
    # Normalize features
    X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-10)

    # Compute distance matrix
    n = len(X_norm)
    dist_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dist_matrix[i, j] = np.sqrt(np.sum((X_norm[i] - X_norm[j]) ** 2))

    # Find nearest neighbors
    patient_results = []
    for i in range(n):
        dists = dist_matrix[i].copy()
        dists[i] = np.inf
        nearest = np.argmin(dists)
        patient_results.append({
            "patient": patient_names[i],
            "nearest_neighbor": patient_names[nearest],
            "distance": round(float(dists[nearest]), 2),
        })

    # Simple clustering: k=3 using k-medoids
    # Pick 3 most distant patients as cluster centers
    centers = [0]
    for _ in range(2):
        max_min_dist = -1
        best_c = 0
        for i in range(n):
            if i in centers:
                continue
            min_d = min(dist_matrix[i, c] for c in centers)
            if min_d > max_min_dist:
                max_min_dist = min_d
                best_c = i
        centers.append(best_c)

    clusters = {}
    for i in range(n):
        cluster_id = min(range(len(centers)), key=lambda c: dist_matrix[i, centers[c]])
        cluster_name = f"cluster_{cluster_id}"
        if cluster_name not in clusters:
            clusters[cluster_name] = []
        clusters[cluster_name].append(patient_names[i])
        patient_results[i]["cluster"] = cluster_name

    summary = {
        "n_clusters": len(clusters),
        "clusters": clusters,
        "cluster_sizes": {k: len(v) for k, v in clusters.items()},
        "mean_nearest_distance": round(float(np.mean([r["distance"] for r in patient_results])), 2),
    }

    if detail:
        for r in patient_results:
            print(f"  {r['patient']}: nearest={r['nearest_neighbor']} "
                  f"(d={r['distance']}), {r['cluster']}")

    return {"name": "Patient Clustering", "id": "EXP-599",
            "summary": summary, "patients": patient_results}


# ── EXP-600: Settings adequacy vs clinical outcomes synthesis ──

def exp_600_synthesis(patients, detail=False):
    """Synthesize all clinical scores into a single patient dashboard.

    Combine: settings score, basal adequacy, correction effectiveness,
    GMI, aggressiveness — into a comprehensive patient profile.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        demand = r["demand"]
        supply = r["supply"]

        valid = np.isfinite(bg)
        bg_v = bg[valid]

        # 1. Settings score
        score = _compute_settings_score(df, pk, r)

        # 2. TIR breakdown
        tir = np.mean((bg_v >= 70) & (bg_v <= 180)) * 100
        tbr = np.mean(bg_v < 70) * 100  # time below range
        tar = np.mean(bg_v > 180) * 100  # time above range
        tbr_severe = np.mean(bg_v < 54) * 100
        tar_severe = np.mean(bg_v > 250) * 100

        # 3. GMI
        gmi = 3.31 + 0.02392 * np.mean(bg_v)

        # 4. Correction effectiveness (using high demand = correction activity)
        dem_valid = demand[np.isfinite(demand)]
        dem_p80 = np.percentile(dem_valid, 80) if len(dem_valid) > 100 else 10
        corrections = 0
        successful = 0
        for t in range(len(bg) - 24):
            if (np.isfinite(bg[t]) and bg[t] > 180 and
                np.isfinite(demand[t]) and demand[t] > dem_p80):
                corrections += 1
                if t + 24 < len(bg) and np.isfinite(bg[t + 24]) and bg[t + 24] < 150:
                    successful += 1
        correction_rate = successful / max(1, corrections)

        # 5. Overnight stability (mean BG drift 00-06)
        n = len(bg)
        hours = np.array([(t * 5 // 60) % 24 for t in range(n)])
        overnight = (hours >= 0) & (hours < 6) & np.isfinite(bg)
        overnight_std = float(np.std(bg[overnight])) if np.sum(overnight) > 100 else None

        # 6. Model fit
        dbg = r["dbg"]
        comb = r["combined_pred"]
        m = np.isfinite(dbg) & np.isfinite(comb)
        ss_res = np.sum((dbg[m] - comb[m]) ** 2)
        ss_tot = np.sum((dbg[m] - np.mean(dbg[m])) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # 7. Clinical grade
        if tir > 80 and tbr < 4 and gmi < 7.0:
            grade = "A"
        elif tir > 70 and tbr < 5 and gmi < 7.5:
            grade = "B"
        elif tir > 50 and tbr < 10:
            grade = "C"
        else:
            grade = "D"

        # 8. Top recommendation
        recs = []
        if tar > 30:
            recs.append("Reduce time above range (increase basal or reduce CR)")
        if tbr > 5:
            recs.append("Reduce hypo risk (decrease basal or increase ISF)")
        if correction_rate < 0.5:
            recs.append("Improve correction ISF (effective ISF may be too low)")
        if overnight_std and overnight_std > 30:
            recs.append("Stabilize overnight (adjust overnight basal)")
        if not recs:
            recs.append("Settings are well-tuned — maintain current approach")

        results.append({
            "patient": p["name"],
            "grade": grade,
            "settings_score": score["composite"],
            "tir": round(tir, 1),
            "tbr": round(tbr, 1),
            "tar": round(tar, 1),
            "tbr_severe": round(tbr_severe, 2),
            "tar_severe": round(tar_severe, 1),
            "gmi": round(gmi, 1),
            "correction_rate": round(correction_rate * 100, 0),
            "overnight_std": round(overnight_std, 1) if overnight_std else None,
            "model_r2": round(r2, 3),
            "top_recommendation": recs[0],
            "all_recommendations": recs,
        })

    # Summary
    grades = [r["grade"] for r in results]
    summary = {
        "grade_distribution": {g: grades.count(g) for g in "ABCD"},
        "mean_tir": round(np.mean([r["tir"] for r in results]), 1),
        "mean_gmi": round(np.mean([r["gmi"] for r in results]), 1),
        "mean_correction_rate": round(np.mean([r["correction_rate"] for r in results]), 0),
        "mean_score": round(np.mean([r["settings_score"] for r in results]), 1),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: Grade {r['grade']} | Score={r['settings_score']} | "
                  f"TIR={r['tir']}% | GMI={r['gmi']}% | Corr={r['correction_rate']}%")
            print(f"    → {r['top_recommendation']}")

    return {"name": "Clinical Synthesis Dashboard", "id": "EXP-600",
            "summary": summary, "patients": results}


# ── main ──────────────────────────────────────────────────────

ALL_EXPERIMENTS = [
    ("EXP-591", exp_591_counter_regulatory),
    ("EXP-592", exp_592_hypo_risk),
    ("EXP-593", exp_593_sensor_noise),
    ("EXP-594", exp_594_effective_isf),
    ("EXP-595", exp_595_stacking),
    ("EXP-596", exp_596_overnight_basal),
    ("EXP-597", exp_597_minimal_data),
    ("EXP-598", exp_598_aid_aggressiveness),
    ("EXP-599", exp_599_patient_clustering),
    ("EXP-600", exp_600_synthesis),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--max-patients", type=int, default=11)
    ap.add_argument("--exp", type=str, help="Run single experiment, e.g. EXP-591")
    args = ap.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    experiments = ALL_EXPERIMENTS
    if args.exp:
        experiments = [(eid, fn) for eid, fn in ALL_EXPERIMENTS if eid == args.exp]
        if not experiments:
            print(f"Unknown experiment: {args.exp}")
            return

    for exp_id, exp_fn in experiments:
        print(f"{'='*60}")
        print(f"Running {exp_id}: {exp_fn.__doc__.split(chr(10))[0] if exp_fn.__doc__ else ''}")
        print(f"{'='*60}")

        try:
            result = exp_fn(patients, detail=args.detail)
            print(f"\nSummary: {json.dumps(result['summary'], indent=2, default=str)}")

            if args.save:
                safe_name = result["name"].lower().replace(" ", "_").replace("/", "_")[:30]
                fname = SAVE_DIR / f"{exp_id.lower()}_{safe_name}.json"
                with open(fname, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"Saved → {fname}")

        except Exception as e:
            import traceback
            print(f"ERROR in {exp_id}: {e}")
            traceback.print_exc()

        print()


if __name__ == "__main__":
    main()
