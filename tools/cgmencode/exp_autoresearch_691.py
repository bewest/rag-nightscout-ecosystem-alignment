"""EXP-691-700: Spike-cleaned advanced models, physiological insights, clinical intelligence.

EXP-691: Cleaned joint model v2 — 2σ spike + dawn conditioning combined
EXP-692: Cleaned hypo prediction — spike cleaning improves hypo F1
EXP-693: Basal rate assessment — overnight flux balance
EXP-694: CR effectiveness score — post-meal recovery speed
EXP-695: Personalized alert thresholds — patient-specific alarm levels
EXP-696: Settings change detection — changepoints in flux profiles
EXP-697: Cross-patient transfer — cleaned models transfer better
EXP-698: Longitudinal stability — cleaned model staleness comparison
EXP-699: Minimal data pipeline — cleaned pipeline with 3 days
EXP-700: Grand summary metrics — comprehensive before/after comparison
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand


def _compute_resid_with_flux(p):
    """Physics-based flux residual."""
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
    """Joint NL+AR features (correct explicit lag)."""
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


def _build_joint_features_dawn(resid, bg, demand, hours, order=6):
    """Joint NL+AR features + dawn/overnight indicators."""
    X_base = _build_joint_features(resid, bg, demand, order)
    n = X_base.shape[0]
    X = np.zeros((n, X_base.shape[1] + 2))
    X[:, :X_base.shape[1]] = X_base
    actual_n = min(n, len(hours))
    X[:actual_n, -2] = ((hours[:actual_n] >= 4) & (hours[:actual_n] < 8)).astype(float)
    X[:actual_n, -1] = ((hours[:actual_n] >= 0) & (hours[:actual_n] < 4)).astype(float)
    return X


def _fit_ridge(X_train, y_train, X_test, y_test=None, alpha=1.0):
    """Ridge with NaN filtering."""
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


def _detect_spikes(resid, sigma_mult=2.0):
    """Detect spikes via 2σ threshold (proven optimal in EXP-682)."""
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
    """Linear interpolation over spike positions."""
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


def _clean_resid(resid):
    """Apply standard 2σ spike cleaning pipeline."""
    spikes = _detect_spikes(resid, sigma_mult=2.0)
    return _interpolate_spikes(resid, spikes), len(spikes)


# ---------------------------------------------------------------------------
# EXP-691: Cleaned joint model v2 — combined improvements
# ---------------------------------------------------------------------------
def exp_691_cleaned_model_v2(patients, detail=False):
    """EXP-691: 2σ spike cleaning + dawn conditioning combined."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))
        hours = pd.DatetimeIndex(ts[:n]).hour

        split = int(n * 0.7)

        # v0: baseline
        X0 = _build_joint_features(resid[:n], bg, demand)[:n]
        r2_v0, _, _ = _fit_ridge(X0[:split], resid[:split], X0[split:n], resid[split:n])

        # v1: spike cleaning only
        cleaned, n_spikes = _clean_resid(resid)
        X1 = _build_joint_features(cleaned[:n], bg, demand)[:n]
        r2_v1, _, _ = _fit_ridge(X1[:split], cleaned[:split], X1[split:n], cleaned[split:n])

        # v2: spike cleaning + dawn
        X2 = _build_joint_features_dawn(cleaned[:n], bg, demand, hours)[:n]
        r2_v2, _, _ = _fit_ridge(X2[:split], cleaned[:split], X2[split:n], cleaned[split:n])

        pr = {
            "patient": p["name"],
            "r2_v0_baseline": round(r2_v0, 3),
            "r2_v1_cleaned": round(r2_v1, 3),
            "r2_v2_cleaned_dawn": round(r2_v2, 3),
            "total_improvement": round(r2_v2 - r2_v0, 3),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: v0={r2_v0:.3f} v1={r2_v1:.3f} v2={r2_v2:.3f} "
                  f"total_Δ={r2_v2 - r2_v0:+.3f}")

    return {
        "name": "EXP-691: Cleaned model v2",
        "mean_v0": round(float(np.mean([r["r2_v0_baseline"] for r in results])), 3),
        "mean_v1": round(float(np.mean([r["r2_v1_cleaned"] for r in results])), 3),
        "mean_v2": round(float(np.mean([r["r2_v2_cleaned_dawn"] for r in results])), 3),
        "mean_total_improvement": round(float(np.mean([r["total_improvement"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-692: Cleaned hypo prediction
# ---------------------------------------------------------------------------
def exp_692_cleaned_hypo(patients, detail=False):
    """EXP-692: Spike cleaning improves hypo detection."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)
        split = int(n * 0.7)

        # hypo labels: BG < 70 within next 6 steps (30 min)
        hypo_labels = np.zeros(n, dtype=int)
        for i in range(n - 6):
            if np.any(bg[i+1:i+7] < 70):
                hypo_labels[i] = 1

        f1_v0 = 0.0
        f1_v1 = 0.0

        for version, resid_data, label in [("v0", resid, "baseline"), ("v1", None, "cleaned")]:
            if version == "v1":
                resid_data, _ = _clean_resid(resid)
            X = _build_joint_features(resid_data, bg, demand)
            _, pred, _ = _fit_ridge(X[:split], resid_data[:split], X[split:])

            test_labels = hypo_labels[split:]
            valid = np.isfinite(pred) & np.isfinite(test_labels.astype(float))
            if valid.sum() < 100 or test_labels[valid].sum() < 10:
                continue

            best_f1 = 0
            for thresh in np.linspace(-15, -1, 30):
                pred_hypo = (pred[valid] < thresh).astype(int)
                tp = np.sum((pred_hypo == 1) & (test_labels[valid] == 1))
                fp = np.sum((pred_hypo == 1) & (test_labels[valid] == 0))
                fn = np.sum((pred_hypo == 0) & (test_labels[valid] == 1))
                prec = tp / max(tp + fp, 1)
                rec = tp / max(tp + fn, 1)
                f1 = 2 * prec * rec / max(prec + rec, 1e-12)
                if f1 > best_f1:
                    best_f1 = f1

            if version == "v0":
                f1_v0 = best_f1
            else:
                f1_v1 = best_f1

        pr = {
            "patient": p["name"],
            "hypo_rate": round(float(hypo_labels[split:].mean()) * 100, 1),
            "f1_baseline": round(float(f1_v0), 3),
            "f1_cleaned": round(float(f1_v1), 3),
            "f1_improvement": round(float(f1_v1 - f1_v0), 3),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: hypo={pr['hypo_rate']:.1f}% F1_base={pr['f1_baseline']:.3f} "
                  f"F1_clean={pr['f1_cleaned']:.3f} Δ={pr['f1_improvement']:+.3f}")

    return {
        "name": "EXP-692: Cleaned hypo prediction",
        "mean_f1_baseline": round(float(np.mean([r["f1_baseline"] for r in results])), 3),
        "mean_f1_cleaned": round(float(np.mean([r["f1_cleaned"] for r in results])), 3),
        "mean_improvement": round(float(np.mean([r["f1_improvement"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-693: Basal rate assessment
# ---------------------------------------------------------------------------
def exp_693_basal_assessment(patients, detail=False):
    """EXP-693: Overnight flux balance predicts optimal basal rate."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))
        hours = pd.DatetimeIndex(ts[:n]).hour

        overnight_mask = (hours >= 0) & (hours < 6) & (carb_supply[:n] < 0.5)
        if overnight_mask.sum() < 500:
            continue

        overnight_bg = bg[:n][overnight_mask]
        overnight_net = net[:n][overnight_mask]
        overnight_demand = demand[:n][overnight_mask]
        overnight_supply = supply[:n][overnight_mask]

        valid = np.isfinite(overnight_bg)
        if valid.sum() < 200:
            continue

        mean_overnight_bg = float(np.nanmean(overnight_bg[valid]))
        overnight_tir = float(np.mean((overnight_bg[valid] >= 70) & (overnight_bg[valid] <= 180)) * 100)
        overnight_tbr = float(np.mean(overnight_bg[valid] < 70) * 100)
        overnight_net_valid = overnight_net[np.isfinite(overnight_net)]
        mean_overnight_net = float(np.nanmean(overnight_net_valid)) if len(overnight_net_valid) > 0 else 0.0

        valid_sd = np.isfinite(overnight_demand) & (overnight_demand > 0.1)
        sd_ratio = float(np.nanmean(overnight_supply[valid_sd] / overnight_demand[valid_sd])) if valid_sd.sum() > 100 else 1.0

        if overnight_tbr > 5:
            assessment = "basal_too_high"
        elif mean_overnight_bg > 180:
            assessment = "basal_too_low"
        elif overnight_tir > 70:
            assessment = "basal_appropriate"
        elif mean_overnight_net < -2:
            assessment = "basal_slightly_high"
        elif mean_overnight_net > 2:
            assessment = "basal_slightly_low"
        else:
            assessment = "basal_marginal"

        pr = {
            "patient": p["name"],
            "overnight_bg": round(mean_overnight_bg, 0),
            "overnight_tir": round(overnight_tir, 1),
            "overnight_tbr": round(overnight_tbr, 1),
            "overnight_net": round(mean_overnight_net, 2),
            "sd_ratio": round(sd_ratio, 3),
            "assessment": assessment,
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: BG={mean_overnight_bg:.0f} TIR={overnight_tir:.0f}% "
                  f"TBR={overnight_tbr:.1f}% net={mean_overnight_net:.1f} ratio={sd_ratio:.2f} → {assessment}")

    assessments = [r["assessment"] for r in results]
    return {
        "name": "EXP-693: Basal rate assessment",
        "n_patients": len(results),
        "assessment_distribution": {a: assessments.count(a) for a in set(assessments)},
        "mean_overnight_tir": round(float(np.mean([r["overnight_tir"] for r in results])), 1),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-694: CR effectiveness score
# ---------------------------------------------------------------------------
def exp_694_cr_effectiveness(patients, detail=False):
    """EXP-694: Post-meal flux recovery speed indicates CR accuracy."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)

        meal_starts = []
        i = 0
        while i < n - 36:
            if carb_supply[i] > 5.0:
                meal_starts.append(i)
                i += 36
            else:
                i += 1

        if len(meal_starts) < 5:
            pr = {"patient": p["name"], "n_meals": len(meal_starts), "mean_recovery_min": None, "cr_score": None}
            results.append(pr)
            if detail:
                print(f"    {p['name']}: insufficient meals ({len(meal_starts)})")
            continue

        recovery_times = []
        peak_bgs = []
        for ms in meal_starts:
            post_window = net[ms:min(ms + 36, n)]
            if len(post_window) < 12:
                continue
            recovered = False
            for t in range(6, len(post_window) - 2):
                if all(abs(post_window[t+j]) < 1.5 for j in range(3) if t+j < len(post_window)):
                    recovery_times.append(t * 5)
                    recovered = True
                    break
            if not recovered:
                recovery_times.append(180)
            bg_window = bg[ms:min(ms + 36, n)]
            valid_bg = bg_window[np.isfinite(bg_window)]
            if len(valid_bg) > 0:
                peak_bgs.append(float(np.max(valid_bg)))

        mean_recovery = float(np.mean(recovery_times)) if recovery_times else 180
        mean_peak = float(np.mean(peak_bgs)) if peak_bgs else 0
        time_score = max(0, min(100, (180 - mean_recovery) / 150 * 100))
        peak_score = max(0, min(100, (300 - mean_peak) / 160 * 100))
        cr_score = (time_score + peak_score) / 2

        pr = {
            "patient": p["name"],
            "n_meals": len(meal_starts),
            "mean_recovery_min": round(mean_recovery, 0),
            "mean_peak_bg": round(mean_peak, 0),
            "cr_score": round(cr_score, 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: {len(meal_starts)} meals, recovery={mean_recovery:.0f}min "
                  f"peak={mean_peak:.0f} CR_score={cr_score:.0f}")

    valid_scores = [r["cr_score"] for r in results if r["cr_score"] is not None]
    return {
        "name": "EXP-694: CR effectiveness score",
        "n_patients": len(results),
        "mean_cr_score": round(float(np.mean(valid_scores)), 1) if valid_scores else 0,
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-695: Personalized alert thresholds
# ---------------------------------------------------------------------------
def exp_695_alert_thresholds(patients, detail=False):
    """EXP-695: Per-patient residual distributions enable custom alerts."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        cleaned, _ = _clean_resid(resid)
        n = len(cleaned)
        split = int(n * 0.7)

        X = _build_joint_features(cleaned, bg, demand)
        _, pred, w = _fit_ridge(X[:split], cleaned[:split], X[split:])

        test_resid = cleaned[split:]
        valid = np.isfinite(test_resid) & np.isfinite(pred)
        if valid.sum() < 100:
            continue

        errors = test_resid[valid] - pred[valid]
        p5 = float(np.percentile(errors, 5))
        p95 = float(np.percentile(errors, 95))

        alert_low = p5 * 1.5
        alert_high = p95 * 1.5

        n_low = int(np.sum(errors < alert_low))
        n_high = int(np.sum(errors > alert_high))
        alert_rate = (n_low + n_high) / len(errors) * 100

        fixed_threshold = 15.0
        fixed_rate = int(np.sum(np.abs(errors) > fixed_threshold)) / len(errors) * 100

        pr = {
            "patient": p["name"],
            "error_p5": round(p5, 1),
            "error_p95": round(p95, 1),
            "alert_low": round(alert_low, 1),
            "alert_high": round(alert_high, 1),
            "personal_alert_rate": round(alert_rate, 1),
            "fixed_alert_rate": round(fixed_rate, 1),
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: errors [{p5:.0f}, {p95:.0f}] personal_alerts={alert_rate:.1f}% "
                  f"fixed_alerts={fixed_rate:.1f}%")

    return {
        "name": "EXP-695: Personalized alert thresholds",
        "mean_personal_rate": round(float(np.mean([r["personal_alert_rate"] for r in results])), 1),
        "mean_fixed_rate": round(float(np.mean([r["fixed_alert_rate"] for r in results])), 1),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-696: Settings change detection
# ---------------------------------------------------------------------------
def exp_696_settings_change(patients, detail=False):
    """EXP-696: Flux profile shifts detect when metabolic patterns change."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        n = len(resid)

        week_len = 7 * 288
        n_weeks = n // week_len
        if n_weeks < 4:
            continue

        weekly_profiles = []
        for w in range(n_weeks):
            start = w * week_len
            end = start + week_len
            hourly = np.zeros(24)
            for h in range(24):
                mask = np.zeros(week_len, dtype=bool)
                for d in range(7):
                    day_start = d * 288
                    h_start = day_start + h * 12
                    h_end = h_start + 12
                    if h_end <= week_len:
                        mask[h_start:h_end] = True
                week_net = net[start:end]
                vals = week_net[mask[:len(week_net)]]
                valid_v = np.isfinite(vals)
                hourly[h] = float(np.nanmean(vals[valid_v])) if valid_v.sum() > 0 else 0.0
            weekly_profiles.append(hourly)

        changepoints = []
        for w in range(1, len(weekly_profiles)):
            diff = np.sum((np.array(weekly_profiles[w]) - np.array(weekly_profiles[w-1])) ** 2)
            rmsd = np.sqrt(diff / 24)
            if rmsd > 3.0:
                changepoints.append({"week": w + 1, "rmsd": round(float(rmsd), 2)})

        pr = {
            "patient": p["name"],
            "n_weeks": len(weekly_profiles),
            "n_changepoints": len(changepoints),
            "changepoints": changepoints[:5],
        }
        results.append(pr)
        if detail:
            cp_str = ", ".join(f"w{c['week']}({c['rmsd']})" for c in changepoints[:5])
            print(f"    {p['name']}: {len(weekly_profiles)} weeks, {len(changepoints)} changepoints: {cp_str}")

    return {
        "name": "EXP-696: Settings change detection",
        "n_patients": len(results),
        "mean_changepoints": round(float(np.mean([r["n_changepoints"] for r in results])), 1),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-697: Cross-patient transfer
# ---------------------------------------------------------------------------
def exp_697_cross_transfer(patients, detail=False):
    """EXP-697: Spike-cleaned models transfer better between patients."""
    results = []
    patient_data = []

    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        cleaned, _ = _clean_resid(resid)
        X_raw = _build_joint_features(resid, bg, demand)
        X_clean = _build_joint_features(cleaned, bg, demand)
        patient_data.append({
            "name": p["name"],
            "resid": resid, "cleaned": cleaned,
            "X_raw": X_raw, "X_clean": X_clean,
        })

    if len(patient_data) < 3:
        return {"name": "EXP-697: Cross-patient transfer", "error": "insufficient patients"}

    for i, test_p in enumerate(patient_data):
        train_Xr = np.concatenate([d["X_raw"] for j, d in enumerate(patient_data) if j != i])
        train_yr = np.concatenate([d["resid"] for j, d in enumerate(patient_data) if j != i])
        train_Xc = np.concatenate([d["X_clean"] for j, d in enumerate(patient_data) if j != i])
        train_yc = np.concatenate([d["cleaned"] for j, d in enumerate(patient_data) if j != i])

        r2_raw, _, _ = _fit_ridge(train_Xr, train_yr, test_p["X_raw"], test_p["resid"])
        r2_clean, _, _ = _fit_ridge(train_Xc, train_yc, test_p["X_clean"], test_p["cleaned"])

        n = len(test_p["cleaned"])
        split = int(n * 0.7)
        r2_personal, _, _ = _fit_ridge(test_p["X_clean"][:split], test_p["cleaned"][:split],
                                        test_p["X_clean"][split:], test_p["cleaned"][split:])

        pr = {
            "patient": test_p["name"],
            "r2_raw_transfer": round(r2_raw, 3),
            "r2_clean_transfer": round(r2_clean, 3),
            "r2_personal": round(r2_personal, 3),
            "transfer_improvement": round(r2_clean - r2_raw, 3),
        }
        results.append(pr)
        if detail:
            print(f"    {test_p['name']}: raw_xfer={r2_raw:.3f} clean_xfer={r2_clean:.3f} "
                  f"personal={r2_personal:.3f} Δ={r2_clean - r2_raw:+.3f}")

    return {
        "name": "EXP-697: Cross-patient transfer",
        "mean_raw_transfer": round(float(np.mean([r["r2_raw_transfer"] for r in results])), 3),
        "mean_clean_transfer": round(float(np.mean([r["r2_clean_transfer"] for r in results])), 3),
        "mean_personal": round(float(np.mean([r["r2_personal"] for r in results])), 3),
        "mean_transfer_improvement": round(float(np.mean([r["transfer_improvement"] for r in results])), 3),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-698: Longitudinal stability
# ---------------------------------------------------------------------------
def exp_698_longitudinal_stability(patients, detail=False):
    """EXP-698: Cleaned model stability exceeds uncleaned over 6 months."""
    results = []
    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        cleaned, _ = _clean_resid(resid)
        n = len(resid)

        train_end = min(30 * 288, int(n * 0.3))
        if train_end < 1000:
            continue

        X_raw = _build_joint_features(resid, bg, demand)
        X_clean = _build_joint_features(cleaned, bg, demand)

        _, _, w_raw = _fit_ridge(X_raw[:train_end], resid[:train_end], X_raw[:train_end])
        _, _, w_clean = _fit_ridge(X_clean[:train_end], cleaned[:train_end], X_clean[:train_end])

        horizons = [30, 60, 90, 120, 150]
        decay_raw = {}
        decay_clean = {}

        for days in horizons:
            test_start = days * 288
            test_end = min((days + 30) * 288, n)
            if test_start >= n or test_end - test_start < 288:
                continue

            X_te_r = X_raw[test_start:test_end]
            y_te_r = resid[test_start:test_end]
            mask_r = np.all(np.isfinite(X_te_r), axis=1) & np.isfinite(y_te_r)
            if mask_r.sum() > 50:
                pred_r = X_te_r[mask_r] @ w_raw
                ss_res = np.sum((y_te_r[mask_r] - pred_r) ** 2)
                ss_tot = np.sum((y_te_r[mask_r] - np.mean(y_te_r[mask_r])) ** 2)
                decay_raw[days] = round(1.0 - ss_res / max(ss_tot, 1e-12), 3)

            X_te_c = X_clean[test_start:test_end]
            y_te_c = cleaned[test_start:test_end]
            mask_c = np.all(np.isfinite(X_te_c), axis=1) & np.isfinite(y_te_c)
            if mask_c.sum() > 50:
                pred_c = X_te_c[mask_c] @ w_clean
                ss_res = np.sum((y_te_c[mask_c] - pred_c) ** 2)
                ss_tot = np.sum((y_te_c[mask_c] - np.mean(y_te_c[mask_c])) ** 2)
                decay_clean[days] = round(1.0 - ss_res / max(ss_tot, 1e-12), 3)

        pr = {"patient": p["name"], "raw_decay": decay_raw, "clean_decay": decay_clean}
        results.append(pr)
        if detail:
            parts = []
            for d in sorted(set(list(decay_raw.keys()) + list(decay_clean.keys()))):
                r = decay_raw.get(d, "?")
                c = decay_clean.get(d, "?")
                parts.append(f"{d}d: raw={r}/clean={c}")
            print(f"    {p['name']}: {', '.join(parts)}")

    return {
        "name": "EXP-698: Longitudinal stability",
        "n_patients": len(results),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-699: Minimal data pipeline
# ---------------------------------------------------------------------------
def exp_699_minimal_data(patients, detail=False):
    """EXP-699: Cleaned pipeline works with just 3 days of data."""
    results = []
    day_sizes = [1, 3, 7, 14, 30]

    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        cleaned, _ = _clean_resid(resid)
        n = len(cleaned)

        test_start = max(0, n - 30 * 288)
        test_end = n
        if test_end - test_start < 288:
            continue

        X_clean = _build_joint_features(cleaned, bg, demand)

        day_r2s = {}
        for days in day_sizes:
            train_n = days * 288
            if train_n > test_start:
                continue
            train_start = max(0, test_start - train_n)

            r2, _, _ = _fit_ridge(
                X_clean[train_start:train_start + train_n],
                cleaned[train_start:train_start + train_n],
                X_clean[test_start:test_end],
                cleaned[test_start:test_end],
            )
            day_r2s[days] = round(r2, 3)

        pr = {"patient": p["name"], "r2_by_days": day_r2s}
        results.append(pr)
        if detail:
            parts = [f"{d}d={r}" for d, r in sorted(day_r2s.items())]
            print(f"    {p['name']}: {' '.join(parts)}")

    agg = {}
    for days in day_sizes:
        vals = [r["r2_by_days"][days] for r in results if days in r["r2_by_days"]]
        if vals:
            agg[days] = round(float(np.mean(vals)), 3)

    return {
        "name": "EXP-699: Minimal data pipeline",
        "mean_r2_by_days": agg,
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# EXP-700: Grand summary metrics
# ---------------------------------------------------------------------------
def exp_700_grand_summary(patients, detail=False):
    """EXP-700: Comprehensive before/after comparison across all improvements."""
    import time
    results = []
    t0 = time.perf_counter()

    for p in patients:
        out = _compute_resid_with_flux(p)
        if out is None:
            continue
        bg, supply, demand, hepatic, carb_supply, net, resid = out
        ts = _get_timestamps(p)
        n = min(len(ts) - 1, len(resid))
        hours = pd.DatetimeIndex(ts[:n]).hour
        split = int(n * 0.7)

        valid = np.isfinite(bg)
        tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)) * 100)
        mean_bg = float(np.nanmean(bg[valid]))

        # v0: Original baseline
        X0 = _build_joint_features(resid[:n], bg, demand)[:n]
        r2_v0, _, _ = _fit_ridge(X0[:split], resid[:split], X0[split:n], resid[split:n])

        # v1: Spike-cleaned
        cleaned, n_spikes = _clean_resid(resid)
        X1 = _build_joint_features(cleaned[:n], bg, demand)[:n]
        r2_v1, _, _ = _fit_ridge(X1[:split], cleaned[:split], X1[split:n], cleaned[split:n])

        # v2: Spike-cleaned + dawn
        X2 = _build_joint_features_dawn(cleaned[:n], bg, demand, hours)[:n]
        r2_v2, pred_v2, w_v2 = _fit_ridge(X2[:split], cleaned[:split], X2[split:n], cleaned[split:n])

        # prediction intervals
        mask_tr = np.all(np.isfinite(X2[:split]), axis=1) & np.isfinite(cleaned[:split])
        if mask_tr.sum() > 100:
            train_err = cleaned[:split][mask_tr] - X2[:split][mask_tr] @ w_v2
            resid_std = float(np.std(train_err))
        else:
            resid_std = float(np.nanstd(cleaned[:split]))

        test_valid = np.isfinite(pred_v2) & np.isfinite(cleaned[split:n])
        if test_valid.sum() > 100:
            lower = pred_v2[test_valid] - 1.96 * resid_std
            upper = pred_v2[test_valid] + 1.96 * resid_std
            coverage = float(np.mean((cleaned[split:n][test_valid] >= lower) &
                                      (cleaned[split:n][test_valid] <= upper)) * 100)
        else:
            coverage = 0.0

        pr = {
            "patient": p["name"],
            "tir": round(tir, 1),
            "mean_bg": round(mean_bg, 0),
            "r2_v0_baseline": round(r2_v0, 3),
            "r2_v1_spike_cleaned": round(r2_v1, 3),
            "r2_v2_cleaned_dawn": round(r2_v2, 3),
            "total_improvement": round(r2_v2 - r2_v0, 3),
            "relative_improvement_pct": round((r2_v2 - r2_v0) / max(abs(r2_v0), 0.001) * 100, 0),
            "pi_coverage": round(coverage, 1),
            "pi_width": round(resid_std * 3.92, 1),
            "n_spikes_removed": n_spikes,
        }
        results.append(pr)
        if detail:
            print(f"    {p['name']}: v0={r2_v0:.3f} → v1={r2_v1:.3f} → v2={r2_v2:.3f} "
                  f"total_Δ={r2_v2-r2_v0:+.3f} ({pr['relative_improvement_pct']:.0f}%) "
                  f"PI={coverage:.0f}%±{resid_std*3.92:.0f}")

    elapsed = time.perf_counter() - t0

    return {
        "name": "EXP-700: Grand summary",
        "n_patients": len(results),
        "mean_r2_v0": round(float(np.mean([r["r2_v0_baseline"] for r in results])), 3),
        "mean_r2_v1": round(float(np.mean([r["r2_v1_spike_cleaned"] for r in results])), 3),
        "mean_r2_v2": round(float(np.mean([r["r2_v2_cleaned_dawn"] for r in results])), 3),
        "mean_total_improvement": round(float(np.mean([r["total_improvement"] for r in results])), 3),
        "mean_coverage": round(float(np.mean([r["pi_coverage"] for r in results])), 1),
        "elapsed_s": round(elapsed, 2),
        "per_patient": results,
    }


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
ALL_EXPERIMENTS = [
    ("EXP-691", exp_691_cleaned_model_v2),
    ("EXP-692", exp_692_cleaned_hypo),
    ("EXP-693", exp_693_basal_assessment),
    ("EXP-694", exp_694_cr_effectiveness),
    ("EXP-695", exp_695_alert_thresholds),
    ("EXP-696", exp_696_settings_change),
    ("EXP-697", exp_697_cross_transfer),
    ("EXP-698", exp_698_longitudinal_stability),
    ("EXP-699", exp_699_minimal_data),
    ("EXP-700", exp_700_grand_summary),
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
