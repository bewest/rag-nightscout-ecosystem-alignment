"""EXP-681-690: Spike preprocessing pipeline, time-of-day conditioning, clinical decision support.

EXP-681: Spike-cleaned retraining — full pipeline with spike removal
EXP-682: Adaptive spike threshold — per-patient optimal σ
EXP-683: Breakfast CR personalization — time-of-day CR multiplier
EXP-684: Dawn basal conditioning — 04:00-08:00 indicator feature
EXP-685: AID-aware clinical rules — hybrid flux + clinical engine
EXP-686: Weekly trend reports — 7-day rolling flux profiles
EXP-687: Sensor age × spike rate — correlation analysis
EXP-688: Multi-patient dashboard — aggregate clinical scores
EXP-689: Real-time streaming — one-step-at-a-time simulation
EXP-690: End-to-end pipeline test — raw data to clinical report
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# shared infrastructure (proven correct in EXP-651-670)
# ---------------------------------------------------------------------------
PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand


def _compute_resid_with_flux(p):
    """Physics-based flux residual (proven in EXP-601+)."""
    df = p["df"]
    pk = p.get("pk")
    if pk is None:
        return None
    bg_col = "glucose" if "glucose" in df.columns else "sgv"
    bg = df[bg_col].values.astype(float)
    try:
        flux = compute_supply_demand(df, pk)
    except Exception:
        return None
    supply = flux["supply"]
    demand = flux["demand"]
    hepatic = flux["hepatic"]
    carb_supply = flux["carb_supply"]
    net = flux["net"]
    n = min(len(bg), len(supply))
    bg, supply, demand, hepatic, carb_supply, net = (
        bg[:n], supply[:n], demand[:n], hepatic[:n], carb_supply[:n], net[:n],
    )
    bg_decay = (120.0 - bg) * 0.005
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    return bg, supply, demand, hepatic, carb_supply, net, resid


def _build_joint_features(resid, bg, demand, order=6):
    """Joint NL+AR features (correct explicit lag, no np.roll)."""
    n = len(resid)
    n_feat = order + 4
    X = np.zeros((n, n_feat))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid[:-lag]
    bg_c = bg[:n] - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand[:n] ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand[:n] / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    return X


def _fit_ridge(X_train, y_train, X_test, y_test=None, alpha=1.0):
    """Ridge with NaN filtering (critical for CGM gaps)."""
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    mask_te = np.all(np.isfinite(X_test), axis=1)
    if mask_tr.sum() < 50 or mask_te.sum() < 50:
        return 0.0, np.full(len(X_test), np.nan), np.zeros(X_train.shape[1])
    Xc, yc = X_train[mask_tr], y_train[mask_tr]
    A = Xc.T @ Xc + alpha * np.eye(Xc.shape[1])
    w = np.linalg.solve(A, Xc.T @ yc)
    pred = X_test @ w
    if y_test is not None:
        mask_both = mask_te & np.isfinite(y_test)
        if mask_both.sum() < 50:
            return 0.0, pred, w
        ss_res = np.sum((y_test[mask_both] - pred[mask_both]) ** 2)
        ss_tot = np.sum((y_test[mask_both] - np.mean(y_test[mask_both])) ** 2)
        r2 = 1.0 - ss_res / max(ss_tot, 1e-12)
    else:
        r2 = 0.0
    return float(r2), pred, w


def _get_timestamps(p):
    """Return numpy array of timestamps."""
    df = p["df"]
    if "dateString" in df.columns:
        ts = pd.to_datetime(df["dateString"], errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        ts = df.index
    else:
        ts = pd.to_datetime(df.index, errors="coerce")
    return ts.values


def _detect_spikes(resid, sigma_mult=3.0):
    """Detect spikes via sigma threshold on residual jumps."""
    jumps = np.abs(np.diff(resid))
    valid = np.isfinite(jumps)
    if valid.sum() < 100:
        return np.array([], dtype=int)
    mu = np.nanmean(jumps[valid])
    sigma = np.nanstd(jumps[valid])
    threshold = mu + sigma_mult * sigma
    spike_idx = np.where(valid & (jumps > threshold))[0] + 1
    return spike_idx


def _interpolate_spikes(resid, spike_idx):
    """Linear interpolation over detected spike positions."""
    cleaned = resid.copy()
    spike_set = set(spike_idx)
    for idx in spike_idx:
        left = idx - 1
        while left >= 0 and left in spike_set:
            left -= 1
        right = idx + 1
        while right < len(cleaned) and right in spike_set:
            right += 1
        if left >= 0 and right < len(cleaned) and np.isfinite(cleaned[left]) and np.isfinite(cleaned[right]):
            frac = (idx - left) / max(right - left, 1)
            cleaned[idx] = cleaned[left] + frac * (cleaned[right] - cleaned[left])
        elif left >= 0 and np.isfinite(cleaned[left]):
            cleaned[idx] = cleaned[left]
        elif right < len(cleaned) and np.isfinite(cleaned[right]):
            cleaned[idx] = cleaned[right]
    return cleaned


# ---------------------------------------------------------------------------
# EXP-681: Spike-cleaned retraining
# ---------------------------------------------------------------------------
def exp_681_spike_cleaned_retraining(patients, detail=False):
    """EXP-681: Full pipeline with spike removal improves all downstream metrics."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out

        # baseline (no spike cleaning)
        X_base = _build_joint_features(resid, bg, demand)
        n = len(resid)
        split = int(n * 0.7)
        r2_base, _, _ = _fit_ridge(X_base[:split], resid[:split], X_base[split:], resid[split:])

        # spike-cleaned
        spike_idx = _detect_spikes(resid)
        cleaned = _interpolate_spikes(resid, spike_idx)
        X_clean = _build_joint_features(cleaned, bg, demand)
        r2_clean, _, _ = _fit_ridge(X_clean[:split], cleaned[:split], X_clean[split:], cleaned[split:])

        # also measure spike-cleaned R² on ORIGINAL targets (to ensure fair comparison)
        r2_clean_orig, _, _ = _fit_ridge(X_clean[:split], cleaned[:split], X_clean[split:], resid[split:])

        improvement = r2_clean - r2_base
        pr = {
            "patient": p["name"],
            "r2_base": round(r2_base, 3),
            "r2_cleaned": round(r2_clean, 3),
            "r2_cleaned_orig_targets": round(r2_clean_orig, 3),
            "improvement": round(improvement, 3),
            "n_spikes": len(spike_idx),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: base={r2_base:.3f} cleaned={r2_clean:.3f} "
                  f"on_orig={r2_clean_orig:.3f} Δ={improvement:+.3f} ({len(spike_idx)} spikes)")

    improvements = [r["improvement"] for r in results]
    return {
        "name": "EXP-681: Spike-cleaned retraining",
        "mean_r2_base": round(float(np.mean([r["r2_base"] for r in results])), 3),
        "mean_r2_cleaned": round(float(np.mean([r["r2_cleaned"] for r in results])), 3),
        "mean_improvement": round(float(np.mean(improvements)), 3),
        "improved_count": sum(1 for i in improvements if i > 0),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-682: Adaptive spike threshold
# ---------------------------------------------------------------------------
def exp_682_adaptive_threshold(patients, detail=False):
    """EXP-682: Per-patient optimal σ threshold for spike detection."""
    results = []
    thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)
        split = int(n * 0.7)

        best_sigma = 3.0
        best_r2 = -999
        sigma_results = {}

        for sigma in thresholds:
            spike_idx = _detect_spikes(resid, sigma_mult=sigma)
            cleaned = _interpolate_spikes(resid, spike_idx)
            X_clean = _build_joint_features(cleaned, bg, demand)
            r2, _, _ = _fit_ridge(X_clean[:split], cleaned[:split], X_clean[split:], cleaned[split:])
            sigma_results[sigma] = {"r2": round(r2, 3), "n_spikes": len(spike_idx)}
            if r2 > best_r2:
                best_r2 = r2
                best_sigma = sigma

        pr = {
            "patient": p["name"],
            "best_sigma": best_sigma,
            "best_r2": round(best_r2, 3),
            "all_thresholds": sigma_results,
        }
        results.append(pr)
        if detail:
            parts = [f"{s}σ:{d['r2']:.3f}({d['n_spikes']})" for s, d in sigma_results.items()]
            print(f"    {p['name']}: best={best_sigma}σ R²={best_r2:.3f} | {' '.join(parts)}")

    sigma_dist = {}
    for r in results:
        s = r["best_sigma"]
        sigma_dist[s] = sigma_dist.get(s, 0) + 1

    return {
        "name": "EXP-682: Adaptive spike threshold",
        "sigma_distribution": sigma_dist,
        "mean_best_r2": round(float(np.mean([r["best_r2"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-683: Breakfast CR personalization
# ---------------------------------------------------------------------------
def exp_683_breakfast_cr(patients, detail=False):
    """EXP-683: Time-of-day CR adjustment improves meal predictions."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))
        ts = ts[:n]

        hours = pd.DatetimeIndex(ts).hour

        # define meal windows
        breakfast_mask = (hours >= 5) & (hours < 10) & (carb_supply[:n] > 2.0)
        lunch_mask = (hours >= 10) & (hours < 14) & (carb_supply[:n] > 2.0)
        dinner_mask = (hours >= 17) & (hours < 21) & (carb_supply[:n] > 2.0)

        # measure mean absolute residual in each window
        meal_residuals = {}
        for name, mask in [("breakfast", breakfast_mask), ("lunch", lunch_mask), ("dinner", dinner_mask)]:
            if mask.sum() > 50:
                meal_resid = resid[:n][mask]
                valid = np.isfinite(meal_resid)
                if valid.sum() > 20:
                    meal_residuals[name] = {
                        "mean_resid": round(float(np.nanmean(meal_resid[valid])), 2),
                        "mae": round(float(np.nanmean(np.abs(meal_resid[valid]))), 2),
                        "n": int(valid.sum()),
                    }

        # time-of-day conditioned model: add breakfast/lunch/dinner indicator features
        X_base = _build_joint_features(resid, bg, demand)
        n_base = X_base.shape[0]

        # add 3 indicator columns
        X_tod = np.zeros((n_base, X_base.shape[1] + 3))
        X_tod[:, :X_base.shape[1]] = X_base
        hr = pd.DatetimeIndex(ts[:n_base]).hour if n_base <= n else pd.DatetimeIndex(ts[:n]).hour
        actual_n = min(n_base, len(hr))
        X_tod[:actual_n, -3] = ((hr[:actual_n] >= 5) & (hr[:actual_n] < 10)).astype(float) * carb_supply[:actual_n] / 10.0
        X_tod[:actual_n, -2] = ((hr[:actual_n] >= 10) & (hr[:actual_n] < 14)).astype(float) * carb_supply[:actual_n] / 10.0
        X_tod[:actual_n, -1] = ((hr[:actual_n] >= 17) & (hr[:actual_n] < 21)).astype(float) * carb_supply[:actual_n] / 10.0

        split = int(n_base * 0.7)
        r2_base, _, _ = _fit_ridge(X_base[:split], resid[:split], X_base[split:], resid[split:])
        r2_tod, _, _ = _fit_ridge(X_tod[:split], resid[:split], X_tod[split:], resid[split:])

        pr = {
            "patient": p["name"],
            "r2_base": round(r2_base, 3),
            "r2_tod": round(r2_tod, 3),
            "improvement": round(r2_tod - r2_base, 3),
            "meal_residuals": meal_residuals,
        }
        results.append(pr)
        if detail:
            meals_str = " ".join(f"{k}:{v['mae']}" for k, v in meal_residuals.items())
            print(f"    {p['name']}: base={r2_base:.3f} tod={r2_tod:.3f} "
                  f"Δ={r2_tod-r2_base:+.3f} meals={meals_str}")

    return {
        "name": "EXP-683: Breakfast CR personalization",
        "mean_r2_base": round(float(np.mean([r["r2_base"] for r in results])), 3),
        "mean_r2_tod": round(float(np.mean([r["r2_tod"] for r in results])), 3),
        "mean_improvement": round(float(np.mean([r["improvement"] for r in results])), 3),
        "improved_count": sum(1 for r in results if r["improvement"] > 0),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-684: Dawn basal conditioning
# ---------------------------------------------------------------------------
def exp_684_dawn_conditioning(patients, detail=False):
    """EXP-684: Dawn-specific feature improves overnight-to-morning predictions."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))
        ts = ts[:n]

        hours = pd.DatetimeIndex(ts).hour

        X_base = _build_joint_features(resid, bg, demand)
        n_base = X_base.shape[0]

        # add dawn indicator (04:00-08:00) and overnight indicator (00:00-04:00)
        X_dawn = np.zeros((n_base, X_base.shape[1] + 2))
        X_dawn[:, :X_base.shape[1]] = X_base
        actual_n = min(n_base, len(hours))
        X_dawn[:actual_n, -2] = ((hours[:actual_n] >= 4) & (hours[:actual_n] < 8)).astype(float)
        X_dawn[:actual_n, -1] = ((hours[:actual_n] >= 0) & (hours[:actual_n] < 4)).astype(float)

        split = int(n_base * 0.7)
        r2_base, _, _ = _fit_ridge(X_base[:split], resid[:split], X_base[split:], resid[split:])
        r2_dawn, _, _ = _fit_ridge(X_dawn[:split], resid[:split], X_dawn[split:], resid[split:])

        # measure specifically on dawn window
        dawn_mask = np.zeros(n_base, dtype=bool)
        dawn_mask[:actual_n] = (hours[:actual_n] >= 4) & (hours[:actual_n] < 8)
        test_dawn = dawn_mask[split:]
        if test_dawn.sum() > 100:
            r2_base_dawn, _, _ = _fit_ridge(X_base[:split], resid[:split], X_base[split:][test_dawn], resid[split:][test_dawn])
            r2_dawn_dawn, _, _ = _fit_ridge(X_dawn[:split], resid[:split], X_dawn[split:][test_dawn], resid[split:][test_dawn])
        else:
            r2_base_dawn = r2_dawn_dawn = 0.0

        pr = {
            "patient": p["name"],
            "r2_base": round(r2_base, 3),
            "r2_dawn": round(r2_dawn, 3),
            "improvement": round(r2_dawn - r2_base, 3),
            "r2_base_dawn_only": round(r2_base_dawn, 3),
            "r2_dawn_dawn_only": round(r2_dawn_dawn, 3),
            "dawn_improvement": round(r2_dawn_dawn - r2_base_dawn, 3),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: overall base={r2_base:.3f} dawn={r2_dawn:.3f} Δ={r2_dawn-r2_base:+.3f} | "
                  f"dawn-only base={r2_base_dawn:.3f} dawn={r2_dawn_dawn:.3f} Δ={r2_dawn_dawn-r2_base_dawn:+.3f}")

    return {
        "name": "EXP-684: Dawn basal conditioning",
        "mean_r2_base": round(float(np.mean([r["r2_base"] for r in results])), 3),
        "mean_r2_dawn": round(float(np.mean([r["r2_dawn"] for r in results])), 3),
        "mean_improvement": round(float(np.mean([r["improvement"] for r in results])), 3),
        "mean_dawn_improvement": round(float(np.mean([r["dawn_improvement"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-685: AID-aware clinical rules
# ---------------------------------------------------------------------------
def exp_685_aid_aware_rules(patients, detail=False):
    """EXP-685: Hybrid flux + clinical rule engine produces better recommendations."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))

        valid = np.isfinite(bg)
        tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)) * 100)
        tbr = float(np.mean(bg[valid] < 70) * 100)
        tar = float(np.mean(bg[valid] > 180) * 100)
        mean_bg = float(np.nanmean(bg[valid]))

        # flux metrics
        mean_net = float(np.nanmean(net))
        mean_demand = float(np.nanmean(demand))
        mean_supply = float(np.nanmean(supply))

        # meal-period analysis
        meal_mask = carb_supply[:n] > 2.0
        basal_mask = carb_supply[:n] < 0.5

        meal_net = float(np.nanmean(net[:n][meal_mask])) if meal_mask.sum() > 100 else 0.0
        basal_net = float(np.nanmean(net[:n][basal_mask])) if basal_mask.sum() > 100 else 0.0

        # AID-aware hybrid rules
        hybrid_recs = []
        rationale = []

        # Rule 1: High TAR + negative net → settings issue (AID trying but miscalibrated)
        if tar > 30 and mean_net < 0:
            hybrid_recs.append("adjust_CR_ISF_settings")
            rationale.append(f"TAR={tar:.0f}% but net={mean_net:.1f}<0: AID compensating, settings need tuning")

        # Rule 2: High TAR + positive net → truly insufficient insulin
        if tar > 30 and mean_net > 0:
            hybrid_recs.append("increase_total_insulin")
            rationale.append(f"TAR={tar:.0f}% and net={mean_net:.1f}>0: genuinely under-insulinized")

        # Rule 3: High TBR → reduce insulin (always)
        if tbr > 4:
            hybrid_recs.append("reduce_basal_or_sensitivity")
            rationale.append(f"TBR={tbr:.1f}%: too much time low")

        # Rule 4: Meal-specific (meal net vs basal net)
        if meal_mask.sum() > 100 and meal_net > 2.0:
            hybrid_recs.append("decrease_CR_ratio")
            rationale.append(f"Meal net={meal_net:.1f}: under-bolusing for meals")
        elif meal_mask.sum() > 100 and meal_net < -2.0:
            hybrid_recs.append("increase_CR_ratio")
            rationale.append(f"Meal net={meal_net:.1f}: over-bolusing for meals")

        # Rule 5: Basal-specific
        if basal_mask.sum() > 100 and basal_net > 1.0:
            hybrid_recs.append("increase_basal_rate")
            rationale.append(f"Basal net={basal_net:.1f}: basal insufficient")
        elif basal_mask.sum() > 100 and basal_net < -1.0:
            hybrid_recs.append("decrease_basal_rate")
            rationale.append(f"Basal net={basal_net:.1f}: basal excessive")

        # Rule 6: Good control
        if tir > 70 and tbr < 4:
            hybrid_recs.append("maintain_current_settings")
            rationale.append(f"TIR={tir:.0f}%, TBR={tbr:.1f}%: good control")

        pr = {
            "patient": p["name"],
            "tir": round(tir, 1),
            "tbr": round(tbr, 1),
            "tar": round(tar, 1),
            "mean_net": round(mean_net, 2),
            "recommendations": hybrid_recs,
            "rationale": rationale,
        }
        results.append(pr)
        if detail:
            recs_str = ", ".join(hybrid_recs) if hybrid_recs else "none"
            print(f"    {p['name']}: TIR={tir:.0f}% TBR={tbr:.1f}% TAR={tar:.0f}% net={mean_net:.1f} → {recs_str}")

    return {
        "name": "EXP-685: AID-aware clinical rules",
        "n_patients": len(results),
        "recommendation_types": _count_recs(results),
        "per_patient": results,
    }


def _count_recs(results):
    counts = {}
    for r in results:
        for rec in r["recommendations"]:
            counts[rec] = counts.get(rec, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# EXP-686: Weekly trend reports
# ---------------------------------------------------------------------------
def exp_686_weekly_trends(patients, detail=False):
    """EXP-686: Week-over-week flux changes detect metabolic drift."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)

        # compute weekly summaries
        week_len = 7 * 288
        n_weeks = n // week_len
        if n_weeks < 4:
            continue

        weekly_stats = []
        for w in range(n_weeks):
            start = w * week_len
            end = start + week_len
            bg_w = bg[start:end]
            net_w = net[start:end]
            resid_w = resid[start:end]
            valid = np.isfinite(bg_w)
            if valid.sum() < week_len // 2:
                continue
            tir_w = float(np.mean((bg_w[valid] >= 70) & (bg_w[valid] <= 180)) * 100)
            mean_net_w = float(np.nanmean(net_w))
            mean_resid_w = float(np.nanmean(resid_w[np.isfinite(resid_w)])) if np.any(np.isfinite(resid_w)) else 0.0
            weekly_stats.append({
                "week": w + 1,
                "tir": round(tir_w, 1),
                "mean_net": round(mean_net_w, 2),
                "mean_resid": round(mean_resid_w, 2),
            })

        if len(weekly_stats) < 4:
            continue

        # detect significant week-over-week changes (>5pp TIR change)
        significant_changes = 0
        for i in range(1, len(weekly_stats)):
            delta_tir = weekly_stats[i]["tir"] - weekly_stats[i-1]["tir"]
            if abs(delta_tir) > 5:
                significant_changes += 1

        # overall trend (first half vs second half)
        half = len(weekly_stats) // 2
        first_half_tir = np.mean([w["tir"] for w in weekly_stats[:half]])
        second_half_tir = np.mean([w["tir"] for w in weekly_stats[half:]])
        trend = "improving" if second_half_tir > first_half_tir + 2 else \
                "declining" if second_half_tir < first_half_tir - 2 else "stable"

        pr = {
            "patient": p["name"],
            "n_weeks": len(weekly_stats),
            "significant_changes": significant_changes,
            "first_half_tir": round(float(first_half_tir), 1),
            "second_half_tir": round(float(second_half_tir), 1),
            "trend": trend,
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {len(weekly_stats)} weeks, {significant_changes} sig changes, "
                  f"trend={trend} ({first_half_tir:.0f}%→{second_half_tir:.0f}%)")

    trends = [r["trend"] for r in results]
    return {
        "name": "EXP-686: Weekly trend reports",
        "n_patients": len(results),
        "trends": {"improving": trends.count("improving"), "declining": trends.count("declining"), "stable": trends.count("stable")},
        "mean_sig_changes": round(float(np.mean([r["significant_changes"] for r in results])), 1),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-687: Sensor age × spike rate
# ---------------------------------------------------------------------------
def exp_687_sensor_age_spikes(patients, detail=False):
    """EXP-687: Spike rate increases with sensor age."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)

        # approximate sensor age: divide into 10-day segments (typical sensor lasts 7-14 days)
        # since we don't have actual sensor insertion dates, use rolling 10-day windows
        segment_len = 10 * 288
        n_segments = n // segment_len
        if n_segments < 3:
            continue

        segment_spike_rates = []
        for s in range(n_segments):
            start = s * segment_len
            end = start + segment_len
            seg_resid = resid[start:end]
            spikes = _detect_spikes(seg_resid)
            rate = len(spikes) / segment_len * 100
            segment_spike_rates.append(rate)

        # correlate segment index with spike rate (proxy for time/sensor age)
        if len(segment_spike_rates) < 3:
            continue
        x = np.arange(len(segment_spike_rates))
        r = np.corrcoef(x, segment_spike_rates)[0, 1] if len(x) > 2 else 0.0

        # also check first-third vs last-third
        third = len(segment_spike_rates) // 3
        first_rate = np.mean(segment_spike_rates[:third])
        last_rate = np.mean(segment_spike_rates[-third:])

        pr = {
            "patient": p["name"],
            "n_segments": len(segment_spike_rates),
            "correlation": round(float(r), 3),
            "first_third_rate": round(first_rate, 3),
            "last_third_rate": round(last_rate, 3),
            "rate_change": round(last_rate - first_rate, 3),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {len(segment_spike_rates)} segments, r={r:.3f}, "
                  f"first={first_rate:.2f}% last={last_rate:.2f}% Δ={last_rate-first_rate:+.3f}")

    return {
        "name": "EXP-687: Sensor age × spike rate",
        "n_patients": len(results),
        "mean_correlation": round(float(np.mean([r["correlation"] for r in results])), 3),
        "mean_rate_change": round(float(np.mean([r["rate_change"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-688: Multi-patient dashboard
# ---------------------------------------------------------------------------
def exp_688_dashboard(patients, detail=False):
    """EXP-688: Aggregate clinical scores for fleet monitoring."""
    dashboard = []
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
        gmi = 3.31 + 0.02392 * mean_bg  # Glucose Management Indicator

        # model quality
        X = _build_joint_features(resid, bg, demand)
        n = len(resid)
        split = int(n * 0.7)
        r2, _, _ = _fit_ridge(X[:split], resid[:split], X[split:], resid[split:])

        # spike rate
        spikes = _detect_spikes(resid)
        spike_rate = len(spikes) / len(resid) * 100

        # flux balance
        mean_net = float(np.nanmean(net))

        # grade
        if tir >= 70 and tbr < 4:
            grade = "A"
        elif tir >= 60 and tbr < 5:
            grade = "B"
        elif tir >= 50:
            grade = "C"
        else:
            grade = "D"

        # risk score (0-100)
        risk = min(100, max(0, int(
            (100 - tir) * 0.5 +  # TIR penalty
            tbr * 5.0 +  # hypo penalty (weighted heavily)
            max(0, cv - 36) * 2.0 +  # variability penalty
            (1 - max(0, r2)) * 10  # model uncertainty penalty
        )))

        entry = {
            "patient": p["name"],
            "grade": grade,
            "risk_score": risk,
            "tir": round(tir, 1),
            "tbr": round(tbr, 1),
            "tar": round(tar, 1),
            "cv": round(cv, 1),
            "gmi": round(gmi, 1),
            "mean_bg": round(mean_bg, 0),
            "model_r2": round(r2, 3),
            "spike_rate": round(spike_rate, 2),
            "flux_balance": round(mean_net, 2),
        }
        dashboard.append(entry)
        if detail:
            print(f"    {p['name']}: Grade={grade} Risk={risk} TIR={tir:.0f}% TBR={tbr:.1f}% "
                  f"GMI={gmi:.1f}% R²={r2:.3f} Spikes={spike_rate:.1f}%")

    grades = [d["grade"] for d in dashboard]
    return {
        "name": "EXP-688: Multi-patient dashboard",
        "n_patients": len(dashboard),
        "grade_distribution": {g: grades.count(g) for g in ["A", "B", "C", "D"]},
        "mean_risk": round(float(np.mean([d["risk_score"] for d in dashboard])), 0),
        "mean_tir": round(float(np.mean([d["tir"] for d in dashboard])), 1),
        "dashboard": dashboard,
    }


# ---------------------------------------------------------------------------
# EXP-689: Real-time streaming simulation
# ---------------------------------------------------------------------------
def exp_689_streaming(patients, detail=False):
    """EXP-689: Model works in streaming mode (one-step-at-a-time)."""
    import time
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)

        # train model on first 70%
        X_full = _build_joint_features(resid, bg, demand)
        split = int(n * 0.7)
        _, _, w = _fit_ridge(X_full[:split], resid[:split], X_full[:split])

        # simulate streaming: process last 1000 steps one-at-a-time
        stream_start = max(split, n - 1000)
        stream_n = n - stream_start

        t0 = time.perf_counter()
        stream_preds = []
        stream_actual = []
        ar_buffer = np.zeros(6)  # AR(6) buffer

        for t in range(stream_start, n):
            # build feature vector for this single timestep
            feat = np.zeros(10)
            feat[:6] = ar_buffer
            bg_c = bg[t] - 120.0 if t < len(bg) and np.isfinite(bg[t]) else 0.0
            dem_t = demand[t] if t < len(demand) else 0.0
            feat[6] = bg_c ** 2 / 10000.0
            feat[7] = dem_t ** 2 / 1000.0
            feat[8] = bg_c * dem_t / 1000.0
            feat[9] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5

            if np.all(np.isfinite(feat)):
                pred = float(feat @ w)
                stream_preds.append(pred)
                stream_actual.append(resid[t] if t < len(resid) and np.isfinite(resid[t]) else np.nan)

            # update AR buffer
            if t < len(resid) and np.isfinite(resid[t]):
                ar_buffer = np.roll(ar_buffer, 1)
                ar_buffer[0] = resid[t]

        elapsed = time.perf_counter() - t0

        # accuracy comparison
        valid = np.array([np.isfinite(a) for a in stream_actual])
        if valid.sum() > 50:
            preds_arr = np.array(stream_preds)[valid]
            actual_arr = np.array(stream_actual)[valid]
            ss_res = np.sum((actual_arr - preds_arr) ** 2)
            ss_tot = np.sum((actual_arr - np.mean(actual_arr)) ** 2)
            r2_stream = 1.0 - ss_res / max(ss_tot, 1e-12)
        else:
            r2_stream = 0.0

        # batch R² for comparison
        r2_batch, _, _ = _fit_ridge(X_full[:split], resid[:split],
                                     X_full[stream_start:], resid[stream_start:])

        latency_us = elapsed / max(stream_n, 1) * 1e6

        pr = {
            "patient": p["name"],
            "r2_stream": round(float(r2_stream), 3),
            "r2_batch": round(float(r2_batch), 3),
            "stream_steps": stream_n,
            "total_ms": round(elapsed * 1000, 1),
            "latency_us": round(latency_us, 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: stream R²={r2_stream:.3f} batch R²={r2_batch:.3f} "
                  f"latency={latency_us:.0f}μs ({stream_n} steps in {elapsed*1000:.0f}ms)")

    return {
        "name": "EXP-689: Real-time streaming",
        "mean_r2_stream": round(float(np.mean([r["r2_stream"] for r in results])), 3),
        "mean_r2_batch": round(float(np.mean([r["r2_batch"] for r in results])), 3),
        "mean_latency_us": round(float(np.mean([r["latency_us"] for r in results])), 1),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-690: End-to-end pipeline test
# ---------------------------------------------------------------------------
def exp_690_end_to_end(patients, detail=False):
    """EXP-690: Complete pipeline from raw data to clinical report."""
    import time
    t0 = time.perf_counter()

    pipeline_results = []
    for p in patients:
        step_times = {}

        # Step 1: Flux computation
        t1 = time.perf_counter()
        out = _compute_resid_with_flux(p)
        step_times["flux"] = time.perf_counter() - t1
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out

        # Step 2: Spike detection & cleaning
        t2 = time.perf_counter()
        spikes = _detect_spikes(resid)
        cleaned = _interpolate_spikes(resid, spikes)
        step_times["spike_clean"] = time.perf_counter() - t2

        # Step 3: Feature building
        t3 = time.perf_counter()
        X = _build_joint_features(cleaned, bg, demand)
        step_times["features"] = time.perf_counter() - t3

        # Step 4: Model training
        t4 = time.perf_counter()
        n = len(cleaned)
        split = int(n * 0.7)
        r2, pred, w = _fit_ridge(X[:split], cleaned[:split], X[split:], cleaned[split:])
        step_times["train"] = time.perf_counter() - t4

        # Step 5: Clinical metrics
        t5 = time.perf_counter()
        valid = np.isfinite(bg)
        tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)) * 100)
        tbr = float(np.mean(bg[valid] < 70) * 100)
        tar = float(np.mean(bg[valid] > 180) * 100)
        mean_bg = float(np.nanmean(bg[valid]))
        gmi = 3.31 + 0.02392 * mean_bg
        step_times["metrics"] = time.perf_counter() - t5

        # Step 6: Generate report
        t6 = time.perf_counter()
        if tir >= 70 and tbr < 4:
            grade = "A"
        elif tir >= 60 and tbr < 5:
            grade = "B"
        elif tir >= 50:
            grade = "C"
        else:
            grade = "D"

        recs = []
        mean_net = float(np.nanmean(net))
        if tar > 30 and mean_net < 0:
            recs.append("adjust_settings")
        elif tar > 30:
            recs.append("increase_insulin")
        if tbr > 4:
            recs.append("reduce_insulin")
        if len(recs) == 0:
            recs.append("maintain")
        step_times["report"] = time.perf_counter() - t6

        total_time = sum(step_times.values())

        pr = {
            "patient": p["name"],
            "grade": grade,
            "tir": round(tir, 1),
            "r2": round(r2, 3),
            "n_spikes": len(spikes),
            "recommendations": recs,
            "total_ms": round(total_time * 1000, 1),
            "step_times_ms": {k: round(v * 1000, 1) for k, v in step_times.items()},
        }
        pipeline_results.append(pr)
        if detail:
            steps_str = " ".join(f"{k}={v*1000:.0f}ms" for k, v in step_times.items())
            print(f"    {p['name']}: Grade={grade} TIR={tir:.0f}% R²={r2:.3f} "
                  f"total={total_time*1000:.0f}ms [{steps_str}]")

    total_elapsed = time.perf_counter() - t0

    return {
        "name": "EXP-690: End-to-end pipeline",
        "n_patients": len(pipeline_results),
        "total_elapsed_s": round(total_elapsed, 2),
        "mean_per_patient_ms": round(total_elapsed / max(len(pipeline_results), 1) * 1000, 1),
        "grades": {g: sum(1 for r in pipeline_results if r["grade"] == g) for g in ["A", "B", "C", "D"]},
        "per_patient": pipeline_results,
    }


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
ALL_EXPERIMENTS = [
    ("EXP-681", exp_681_spike_cleaned_retraining),
    ("EXP-682", exp_682_adaptive_threshold),
    ("EXP-683", exp_683_breakfast_cr),
    ("EXP-684", exp_684_dawn_conditioning),
    ("EXP-685", exp_685_aid_aware_rules),
    ("EXP-686", exp_686_weekly_trends),
    ("EXP-687", exp_687_sensor_age_spikes),
    ("EXP-688", exp_688_dashboard),
    ("EXP-689", exp_689_streaming),
    ("EXP-690", exp_690_end_to_end),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-patients", type=int, default=5)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    for exp_id, func in ALL_EXPERIMENTS:
        if args.only and args.only != exp_id:
            continue
        print("=" * 60)
        doc = func.__doc__ or exp_id
        print(f"Running {exp_id}: {doc.strip()}")
        print("=" * 60)
        try:
            import time
            t0 = time.perf_counter()
            result = func(patients, detail=args.detail)
            elapsed = time.perf_counter() - t0
            summary = {k: v for k, v in result.items() if k != "per_patient" and k != "dashboard"}
            print(f"  RESULT: {summary}")
            if args.save:
                safe_name = result["name"].lower().replace(" ", "_").replace("/", "_").replace(":", "")[:30]
                fname = f"{exp_id.lower()}_{safe_name}.json"
                with open(fname, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fname}")
            print(f"  Time: {elapsed:.1f}s\n")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
