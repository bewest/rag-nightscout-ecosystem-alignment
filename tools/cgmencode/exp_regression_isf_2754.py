"""
EXP-2754: Regression-Based Multi-Factor ISF
=============================================

Scientific Question
-------------------
Can we extract accurate ISF from AID data using multi-factor REGRESSION
instead of per-event DIVISION?  Division (ISF = bg_drop / insulin) amplifies
noise when the denominator is small.  Regression fits bg_drop = beta * X
across ALL events simultaneously, giving the partial effect of correction
insulin while controlling for confounders.

Predecessors
------------
EXP-2738  Dose-response safety (ISF ratio vs TBR: rho=-0.85)
EXP-2741  Division-based ISF extraction (3 patients, ISF up to 276)
EXP-2672  Autoprepare qualification gate (22 patients)

Hypotheses
----------
H1  Multi-factor regression ISF is within 2x of profile ISF for >60%
    of patients (vs naive division which overshot 4-10x).
H2  Regression R^2 > 0.15 for the multi-factor model.
H3  beta_correction > beta_smb > beta_excess_basal (per-unit ordering).
H4  Regression ISF has narrower 95% CI than division ISF.
H5  Multi-factor regression ISF is predicted safe (TBR increase < 2pp)
    for >50% of patients.
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GRID_PATH = Path("externals/ns-parquet/training/grid.parquet")
DS_PATH = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST_PATH = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_PATH = Path("externals/experiments/exp-2754_regression_isf.json")
VIZ_DIR = Path("visualizations/regression-isf")

STEPS_PER_HOUR = 12          # 5-min grid
HORIZON_2H = 24              # steps
HORIZON_4H = 48              # steps
BG_THRESHOLD = 150           # mg/dL  (relaxed from 180)
MIN_BOLUS = 0.3              # U
CARB_EXCLUSION_PRIOR = 12    # steps = 1h prior
CARB_EXCLUSION_POST = 12     # steps = 1h post (for feature, not filter)
MIN_EVENTS_PER_PATIENT = 10  # regression minimum
CALM_ROC_THRESHOLD = 0.3     # mg/dL/min for scheduled-basal estimation
SAFETY_RHO = -0.85           # from EXP-2738 dose-response
SAFETY_TBR_THRESHOLD = 2.0   # pp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def json_safe(obj):
    """Serialise numpy / pandas types for JSON."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (pd.Timedelta, np.timedelta64)):
        return str(obj)
    if pd.isna(obj):
        return None
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def safe_median(arr):
    """Median ignoring NaN; return NaN if empty."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.nanmedian(arr))


def safe_mean(arr):
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.nanmean(arr))


def safe_std(arr):
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return np.nan
    return float(np.nanstd(arr, ddof=1))


def ols_regression(X, y):
    """OLS via numpy.linalg.lstsq.  Returns beta, se, R2, residuals."""
    n, k = X.shape
    beta, residuals_arr, rank, sv = np.linalg.lstsq(X, y, rcond=None)

    y_hat = X @ beta
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0

    # Standard errors via (X'X)^{-1} * sigma^2
    dof = max(n - k, 1)
    sigma2 = ss_res / dof
    try:
        cov = np.linalg.inv(X.T @ X) * sigma2
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)

    return {
        "beta": beta,
        "se": se,
        "r2": r2,
        "n": n,
        "k": k,
        "sigma2": sigma2,
        "residuals": y - y_hat,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data():
    """Load grid, devicestatus, and manifest; filter to qualified patients."""
    print("[1/7] Loading data ...")
    manifest = json.loads(MANIFEST_PATH.read_text())
    qualified = manifest["qualified_patients"]
    print(f"  Qualified patients: {len(qualified)}")

    grid = pd.read_parquet(GRID_PATH)
    grid = grid[grid["patient_id"].isin(qualified)].copy()
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  Grid rows: {len(grid):,}")

    # Controller info from devicestatus
    ds = pd.read_parquet(DS_PATH, columns=["patient_id", "controller"])
    ctrl_map = (
        ds.groupby("patient_id")["controller"]
        .agg(lambda s: s.mode().iloc[0] if len(s) > 0 else "unknown")
        .to_dict()
    )

    return grid, qualified, ctrl_map


# ---------------------------------------------------------------------------
# Scheduled-basal estimation
# ---------------------------------------------------------------------------
def estimate_scheduled_basal(pg: pd.DataFrame) -> float:
    """Per-patient median of net_basal during calm periods.

    Calm = no bolus for 2h, no SMB for 1h, |glucose_roc| < threshold.
    Falls back to overall median of net_basal if not enough calm rows.
    """
    nb = pg["net_basal"].fillna(0).values
    bolus = pg["bolus"].fillna(0).values
    smb = pg["bolus_smb"].fillna(0).values
    roc = pg["glucose_roc"].fillna(0).values

    n = len(pg)
    calm_mask = np.ones(n, dtype=bool)

    # No manual bolus within ±2h (24 steps)
    bolus_idx = np.where(bolus > 0.05)[0]
    for bi in bolus_idx:
        lo = max(0, bi - 24)
        hi = min(n, bi + 24)
        calm_mask[lo:hi] = False

    # No SMB within ±1h (12 steps)
    smb_idx = np.where(smb > 0.01)[0]
    for si in smb_idx:
        lo = max(0, si - 12)
        hi = min(n, si + 12)
        calm_mask[lo:hi] = False

    # |glucose_roc| < threshold
    calm_mask &= np.abs(roc) < CALM_ROC_THRESHOLD

    calm_nb = nb[calm_mask]
    if len(calm_nb) >= 20:
        return float(np.nanmedian(calm_nb))
    # Fallback: overall median (less precise but usable)
    return float(np.nanmedian(nb)) if len(nb) > 0 else 0.0


# ---------------------------------------------------------------------------
# Correction-event extraction
# ---------------------------------------------------------------------------
def extract_correction_events(pg: pd.DataFrame, sched_basal: float) -> list[dict]:
    """Find correction-like events for one patient.

    Criteria (relaxed for regression):
      - glucose >= 150 mg/dL
      - manual bolus > 0.3 U
      - no carbs within 1h prior
      - enough future glucose data to compute bg_drop
    """
    glucose = pg["glucose"].values
    bolus = pg["bolus"].fillna(0).values
    smb = pg["bolus_smb"].fillna(0).values
    carbs = pg["carbs"].fillna(0).values
    net_basal = pg["net_basal"].fillna(0).values
    iob = pg["iob"].fillna(0).values
    roc = pg["glucose_roc"].fillna(0).values
    times = pg["time"].values
    isf_sched = pg["scheduled_isf"].fillna(0).values

    n = len(pg)
    events = []

    for i in range(n):
        # Basic filters
        if np.isnan(glucose[i]) or glucose[i] < BG_THRESHOLD:
            continue
        if bolus[i] < MIN_BOLUS:
            continue

        # Carb exclusion: no carbs in 1h prior
        carb_start = max(0, i - CARB_EXCLUSION_PRIOR)
        if np.nansum(carbs[carb_start:i]) > 0.5:
            continue

        # Ensure enough future data
        if i + HORIZON_4H >= n:
            continue

        # 2h and 4h glucose
        g_2h = glucose[i + HORIZON_2H] if not np.isnan(glucose[i + HORIZON_2H]) else np.nan
        g_4h = glucose[i + HORIZON_4H] if not np.isnan(glucose[i + HORIZON_4H]) else np.nan

        if np.isnan(g_2h) and np.isnan(g_4h):
            continue

        bg_drop_2h = glucose[i] - g_2h if not np.isnan(g_2h) else np.nan
        bg_drop_4h = glucose[i] - g_4h if not np.isnan(g_4h) else np.nan

        # Accumulate SMB and excess basal over horizons
        smb_2h = float(np.nansum(smb[i:i + HORIZON_2H]))
        smb_4h = float(np.nansum(smb[i:i + HORIZON_4H]))
        excess_basal_2h = float(np.nansum(net_basal[i:i + HORIZON_2H] - sched_basal)) * (5.0 / 60.0)
        excess_basal_4h = float(np.nansum(net_basal[i:i + HORIZON_4H] - sched_basal)) * (5.0 / 60.0)
        sched_basal_2h = sched_basal * 2.0
        sched_basal_4h = sched_basal * 4.0

        # Carbs nearby (±1h)
        carb_lo = max(0, i - CARB_EXCLUSION_PRIOR)
        carb_hi = min(n, i + CARB_EXCLUSION_POST)
        carbs_nearby = float(np.nansum(carbs[carb_lo:carb_hi]))

        # Total insulin (for naive methods)
        total_insulin_2h = bolus[i] + smb_2h + max(excess_basal_2h, 0)
        total_insulin_4h = bolus[i] + smb_4h + max(excess_basal_4h, 0)

        # Time of day
        ts = pd.Timestamp(times[i])
        hour = ts.hour if hasattr(ts, "hour") else 12

        evt = {
            "index": int(i),
            "bg_start": float(glucose[i]),
            "bg_drop_2h": float(bg_drop_2h) if not np.isnan(bg_drop_2h) else None,
            "bg_drop_4h": float(bg_drop_4h) if not np.isnan(bg_drop_4h) else None,
            "correction_insulin": float(bolus[i]),
            "smb_insulin_2h": smb_2h,
            "smb_insulin_4h": smb_4h,
            "excess_basal_2h": excess_basal_2h,
            "excess_basal_4h": excess_basal_4h,
            "scheduled_basal_2h": sched_basal_2h,
            "scheduled_basal_4h": sched_basal_4h,
            "total_insulin_2h": total_insulin_2h,
            "total_insulin_4h": total_insulin_4h,
            "carbs_nearby": carbs_nearby,
            "iob_start": float(iob[i]),
            "glucose_roc_start": float(roc[i]),
            "hour_of_day": hour,
            "isf_scheduled": float(isf_sched[i]) if isf_sched[i] > 0 else np.nan,
        }
        events.append(evt)

    return events


# ---------------------------------------------------------------------------
# Division-based ISF (baselines)
# ---------------------------------------------------------------------------
def compute_division_isf(events: list[dict], horizon: str = "4h") -> dict:
    """Per-event division: ISF = bg_drop / insulin.

    Returns median, IQR, and per-event ISF values.
    """
    bg_key = f"bg_drop_{horizon}"
    ins_total = f"total_insulin_{horizon}"
    ins_corr = "correction_insulin"

    isf_naive_list = []
    isf_corr_list = []

    for ev in events:
        bd = ev.get(bg_key)
        if bd is None or np.isnan(bd):
            continue
        # Naive: bg_drop / total_insulin
        ti = ev[ins_total]
        if ti > 0.1:
            isf_naive_list.append(bd / ti)
        # Correction-only: bg_drop / correction_insulin
        ci = ev[ins_corr]
        if ci > 0.1:
            isf_corr_list.append(bd / ci)

    return {
        "isf_naive_division": safe_median(isf_naive_list),
        "isf_naive_division_iqr": (
            float(np.nanpercentile(isf_naive_list, 25)) if len(isf_naive_list) >= 4 else np.nan,
            float(np.nanpercentile(isf_naive_list, 75)) if len(isf_naive_list) >= 4 else np.nan,
        ),
        "isf_correction_division": safe_median(isf_corr_list),
        "isf_correction_division_iqr": (
            float(np.nanpercentile(isf_corr_list, 25)) if len(isf_corr_list) >= 4 else np.nan,
            float(np.nanpercentile(isf_corr_list, 75)) if len(isf_corr_list) >= 4 else np.nan,
        ),
        "n_naive": len(isf_naive_list),
        "n_corr": len(isf_corr_list),
        "isf_naive_values": isf_naive_list,
        "isf_correction_values": isf_corr_list,
    }


# ---------------------------------------------------------------------------
# Regression models (per-patient)
# ---------------------------------------------------------------------------
def run_patient_regressions(events: list[dict], horizon: str = "4h") -> dict:
    """Run all three regression models for one patient.

    Model 1  Simple:  bg_drop = b1 * total_insulin + b0
    Model 2  Multi-factor:  bg_drop = b1 * correction + b2 * smb + b3 * excess_basal + b4 * bg_start + b0
    Model 3  Full controls:  bg_drop = b1 * correction + b2 * smb + b3 * excess_basal + b4 * bg_start + b5 * carbs + b6 * iob + b0
    """
    bg_key = f"bg_drop_{horizon}"
    smb_key = f"smb_insulin_{horizon}"
    eb_key = f"excess_basal_{horizon}"
    ti_key = f"total_insulin_{horizon}"

    # Collect valid events
    rows = []
    for ev in events:
        bd = ev.get(bg_key)
        if bd is None or np.isnan(bd):
            continue
        rows.append(ev)

    if len(rows) < MIN_EVENTS_PER_PATIENT:
        return {"status": "insufficient_events", "n_events": len(rows)}

    n = len(rows)
    bg_drop = np.array([r[bg_key] for r in rows], dtype=float)
    correction = np.array([r["correction_insulin"] for r in rows], dtype=float)
    smb = np.array([r[smb_key] for r in rows], dtype=float)
    excess_basal = np.array([r[eb_key] for r in rows], dtype=float)
    total_ins = np.array([r[ti_key] for r in rows], dtype=float)
    bg_start = np.array([r["bg_start"] for r in rows], dtype=float)
    carbs = np.array([r["carbs_nearby"] for r in rows], dtype=float)
    iob_start = np.array([r["iob_start"] for r in rows], dtype=float)

    ones = np.ones(n)

    results = {}

    # --- Model 1: Simple ---
    X1 = np.column_stack([total_ins, ones])
    if np.std(total_ins) > 1e-6:
        m1 = ols_regression(X1, bg_drop)
        results["model1_simple"] = {
            "isf_naive_regression": float(m1["beta"][0]),
            "intercept": float(m1["beta"][1]),
            "se_isf": float(m1["se"][0]),
            "r2": float(m1["r2"]),
            "n": int(m1["n"]),
            "ci95_isf": (
                float(m1["beta"][0] - 1.96 * m1["se"][0]),
                float(m1["beta"][0] + 1.96 * m1["se"][0]),
            ),
        }
        # Prediction MAE
        pred = X1 @ m1["beta"]
        results["model1_simple"]["mae"] = float(np.mean(np.abs(bg_drop - pred)))
    else:
        results["model1_simple"] = {"status": "constant_predictor"}

    # --- Model 2: Multi-factor ---
    # Center features for numerical stability
    corr_c = correction - np.mean(correction)
    smb_c = smb - np.mean(smb)
    eb_c = excess_basal - np.mean(excess_basal)
    bg_c = bg_start - np.mean(bg_start)

    X2 = np.column_stack([correction, smb, excess_basal, bg_start, ones])
    X2_c = np.column_stack([corr_c, smb_c, eb_c, bg_c, ones])

    has_variance = all(
        np.std(v) > 1e-6 for v in [correction, smb, excess_basal, bg_start]
    )
    # Even with some constant features, try fitting
    if np.std(correction) > 1e-6:
        # Use centred X for numerical stability; beta for non-intercept terms
        # is the same as uncentred
        m2 = ols_regression(X2, bg_drop)
        m2_c = ols_regression(X2_c, bg_drop)
        # Use centred SEs (more stable)
        se_to_use = m2_c["se"] if not np.any(np.isnan(m2_c["se"][:4])) else m2["se"]

        results["model2_multifactor"] = {
            "isf_correction": float(m2["beta"][0]),
            "beta_smb": float(m2["beta"][1]),
            "beta_excess_basal": float(m2["beta"][2]),
            "beta_bg_start": float(m2["beta"][3]),
            "intercept": float(m2["beta"][4]),
            "se_correction": float(se_to_use[0]),
            "se_smb": float(se_to_use[1]),
            "se_excess_basal": float(se_to_use[2]),
            "se_bg_start": float(se_to_use[3]),
            "r2": float(m2["r2"]),
            "n": int(m2["n"]),
            "ci95_isf": (
                float(m2["beta"][0] - 1.96 * se_to_use[0]),
                float(m2["beta"][0] + 1.96 * se_to_use[0]),
            ),
        }
        pred2 = X2 @ m2["beta"]
        results["model2_multifactor"]["mae"] = float(np.mean(np.abs(bg_drop - pred2)))
    else:
        results["model2_multifactor"] = {"status": "constant_correction"}

    # --- Model 3: Full controls ---
    X3 = np.column_stack([correction, smb, excess_basal, bg_start, carbs, iob_start, ones])
    if np.std(correction) > 1e-6:
        m3 = ols_regression(X3, bg_drop)
        results["model3_full"] = {
            "isf_controlled": float(m3["beta"][0]),
            "beta_smb": float(m3["beta"][1]),
            "beta_excess_basal": float(m3["beta"][2]),
            "beta_bg_start": float(m3["beta"][3]),
            "beta_carbs": float(m3["beta"][4]),
            "beta_iob": float(m3["beta"][5]),
            "intercept": float(m3["beta"][6]),
            "se_correction": float(m3["se"][0]),
            "r2": float(m3["r2"]),
            "n": int(m3["n"]),
            "ci95_isf": (
                float(m3["beta"][0] - 1.96 * m3["se"][0]),
                float(m3["beta"][0] + 1.96 * m3["se"][0]),
            ),
        }
        pred3 = X3 @ m3["beta"]
        results["model3_full"]["mae"] = float(np.mean(np.abs(bg_drop - pred3)))
    else:
        results["model3_full"] = {"status": "constant_correction"}

    results["n_events"] = n
    results["status"] = "ok"
    return results


# ---------------------------------------------------------------------------
# Population (pooled) regression with patient fixed effects
# ---------------------------------------------------------------------------
def run_population_regression(all_events: dict, horizon: str = "4h") -> dict:
    """Pool all patients; include patient dummies as fixed effects."""
    bg_key = f"bg_drop_{horizon}"
    smb_key = f"smb_insulin_{horizon}"
    eb_key = f"excess_basal_{horizon}"

    # Collect rows
    rows = []
    pids = []
    for pid, evts in all_events.items():
        for ev in evts:
            bd = ev.get(bg_key)
            if bd is None or np.isnan(bd):
                continue
            rows.append(ev)
            pids.append(pid)

    if len(rows) < 20:
        return {"status": "insufficient_pooled_events", "n": len(rows)}

    n = len(rows)
    bg_drop = np.array([r[bg_key] for r in rows], dtype=float)
    correction = np.array([r["correction_insulin"] for r in rows], dtype=float)
    smb = np.array([r[smb_key] for r in rows], dtype=float)
    excess_basal = np.array([r[eb_key] for r in rows], dtype=float)
    bg_start = np.array([r["bg_start"] for r in rows], dtype=float)

    # Patient fixed effects (dummies, drop first for identification)
    unique_pids = sorted(set(pids))
    pid_to_idx = {p: i for i, p in enumerate(unique_pids)}
    n_patients = len(unique_pids)

    if n_patients > 1:
        dummies = np.zeros((n, n_patients - 1))
        for j, pid in enumerate(pids):
            idx = pid_to_idx[pid]
            if idx > 0:
                dummies[j, idx - 1] = 1.0
        X = np.column_stack([correction, smb, excess_basal, bg_start, dummies, np.ones(n)])
    else:
        X = np.column_stack([correction, smb, excess_basal, bg_start, np.ones(n)])

    if np.std(correction) < 1e-6:
        return {"status": "constant_correction"}

    m = ols_regression(X, bg_drop)

    result = {
        "status": "ok",
        "isf_population": float(m["beta"][0]),
        "beta_smb": float(m["beta"][1]),
        "beta_excess_basal": float(m["beta"][2]),
        "beta_bg_start": float(m["beta"][3]),
        "se_correction": float(m["se"][0]),
        "se_smb": float(m["se"][1]),
        "se_excess_basal": float(m["se"][2]),
        "r2": float(m["r2"]),
        "n_events": n,
        "n_patients": n_patients,
        "ci95_isf": (
            float(m["beta"][0] - 1.96 * m["se"][0]),
            float(m["beta"][0] + 1.96 * m["se"][0]),
        ),
    }
    # Prediction MAE
    pred = X @ m["beta"]
    result["mae"] = float(np.mean(np.abs(bg_drop - pred)))
    return result


# ---------------------------------------------------------------------------
# Safety assessment (from EXP-2738 dose-response)
# ---------------------------------------------------------------------------
def safety_assessment(isf_estimate: float, isf_profile: float) -> dict:
    """Predict TBR change if profile ISF were replaced with isf_estimate.

    From EXP-2738: rho(ISF_ratio, TBR) = -0.85
    ISF_ratio = profile / estimate.  If ratio < 1 → more aggressive → more hypo.
    Approximate: delta_TBR ≈ slope * (ratio - 1)
    We use a linear approximation calibrated to the observed relationship.
    """
    if np.isnan(isf_estimate) or np.isnan(isf_profile) or isf_estimate <= 0 or isf_profile <= 0:
        return {"predicted_tbr_change_pp": np.nan, "safe": None}

    isf_ratio = isf_profile / isf_estimate
    # Linear model: delta_TBR ≈ -3.0 * (ratio - 1)
    # If ratio < 1 (estimate > profile → less aggressive), TBR decreases (good)
    # If ratio > 1 (estimate < profile → more aggressive), TBR increases (bad)
    predicted_tbr_change = -3.0 * (isf_ratio - 1.0)
    safe = bool(predicted_tbr_change < SAFETY_TBR_THRESHOLD)

    return {
        "isf_ratio": float(isf_ratio),
        "predicted_tbr_change_pp": float(predicted_tbr_change),
        "safe": safe,
    }


# ---------------------------------------------------------------------------
# Per-patient analysis orchestrator
# ---------------------------------------------------------------------------
def analyse_patient(pid: str, pg: pd.DataFrame, ctrl: str) -> dict:
    """Run full analysis pipeline for one patient."""
    sched_basal = estimate_scheduled_basal(pg)
    events = extract_correction_events(pg, sched_basal)

    result = {
        "patient_id": pid,
        "controller": ctrl,
        "n_rows": len(pg),
        "n_events": len(events),
        "scheduled_basal_estimated": sched_basal,
    }

    if len(events) == 0:
        result["status"] = "no_events"
        return result

    # Division-based ISF (baselines)
    div_4h = compute_division_isf(events, "4h")
    div_2h = compute_division_isf(events, "2h")
    result["division_4h"] = div_4h
    result["division_2h"] = div_2h

    # Profile ISF
    isf_sched_vals = [e["isf_scheduled"] for e in events if not np.isnan(e["isf_scheduled"])]
    result["isf_profile"] = safe_median(isf_sched_vals)

    # Regression models (4h horizon)
    reg_4h = run_patient_regressions(events, "4h")
    result["regression_4h"] = reg_4h

    # Regression models (2h horizon)
    reg_2h = run_patient_regressions(events, "2h")
    result["regression_2h"] = reg_2h

    # Safety assessment for each ISF method
    isf_profile = result["isf_profile"]
    safety = {}

    # Division naive
    isf_nd = div_4h["isf_naive_division"]
    safety["naive_division"] = safety_assessment(isf_nd, isf_profile)

    # Division correction
    isf_cd = div_4h["isf_correction_division"]
    safety["correction_division"] = safety_assessment(isf_cd, isf_profile)

    # Regression naive
    if reg_4h.get("status") == "ok" and "isf_naive_regression" in reg_4h.get("model1_simple", {}):
        isf_rn = reg_4h["model1_simple"]["isf_naive_regression"]
        safety["naive_regression"] = safety_assessment(isf_rn, isf_profile)
    else:
        safety["naive_regression"] = {"predicted_tbr_change_pp": np.nan, "safe": None}

    # Regression multi-factor
    if reg_4h.get("status") == "ok" and "isf_correction" in reg_4h.get("model2_multifactor", {}):
        isf_mf = reg_4h["model2_multifactor"]["isf_correction"]
        safety["multifactor_regression"] = safety_assessment(isf_mf, isf_profile)
    else:
        safety["multifactor_regression"] = {"predicted_tbr_change_pp": np.nan, "safe": None}

    # Regression full controls
    if reg_4h.get("status") == "ok" and "isf_controlled" in reg_4h.get("model3_full", {}):
        isf_fc = reg_4h["model3_full"]["isf_controlled"]
        safety["full_controlled_regression"] = safety_assessment(isf_fc, isf_profile)
    else:
        safety["full_controlled_regression"] = {"predicted_tbr_change_pp": np.nan, "safe": None}

    result["safety"] = safety
    result["status"] = "ok" if reg_4h.get("status") == "ok" else "insufficient_events"

    return result


# ---------------------------------------------------------------------------
# Hypothesis evaluation
# ---------------------------------------------------------------------------
def evaluate_hypotheses(patient_results: list[dict], pop_reg: dict) -> dict:
    """Evaluate all 5 hypotheses from the spec."""
    verdicts = {}

    # Collect patients with regression results
    reg_patients = [p for p in patient_results if p.get("regression_4h", {}).get("status") == "ok"]

    # --- H1: Multi-factor ISF within 2x of profile for >60% of patients ---
    within_2x_count = 0
    h1_total = 0
    for p in reg_patients:
        isf_mf = p["regression_4h"]["model2_multifactor"].get("isf_correction")
        isf_prof = p.get("isf_profile")
        if isf_mf is not None and isf_prof is not None and isf_prof > 0 and isf_mf > 0:
            ratio = isf_mf / isf_prof
            if 0.5 <= ratio <= 2.0:
                within_2x_count += 1
            h1_total += 1

    h1_pct = within_2x_count / h1_total * 100 if h1_total > 0 else 0
    verdicts["H1"] = {
        "description": "Multi-factor regression ISF within 2x of profile for >60% of patients",
        "within_2x_count": within_2x_count,
        "total": h1_total,
        "pct_within_2x": h1_pct,
        "threshold": 60.0,
        "verdict": "PASS" if h1_pct > 60 else "FAIL",
    }

    # --- H2: Regression R² > 0.15 for multi-factor model ---
    r2_vals = []
    for p in reg_patients:
        r2 = p["regression_4h"]["model2_multifactor"].get("r2")
        if r2 is not None:
            r2_vals.append(r2)

    r2_med = safe_median(r2_vals)
    r2_pass_count = sum(1 for r in r2_vals if r > 0.15)
    verdicts["H2"] = {
        "description": "Regression R² > 0.15 for multi-factor model",
        "median_r2": r2_med,
        "patients_above_015": r2_pass_count,
        "total": len(r2_vals),
        "pct_above": r2_pass_count / len(r2_vals) * 100 if r2_vals else 0,
        "verdict": "PASS" if r2_med > 0.15 else "FAIL",
    }

    # --- H3: β_correction > β_smb > β_excess_basal ---
    h3_pass = 0
    h3_total = 0
    for p in reg_patients:
        m2 = p["regression_4h"]["model2_multifactor"]
        bc = m2.get("isf_correction")
        bs = m2.get("beta_smb")
        be = m2.get("beta_excess_basal")
        if bc is not None and bs is not None and be is not None:
            h3_total += 1
            if bc > bs > be:
                h3_pass += 1

    # Also check population-level
    pop_ordering = False
    if pop_reg.get("status") == "ok":
        pop_bc = pop_reg.get("isf_population", 0)
        pop_bs = pop_reg.get("beta_smb", 0)
        pop_be = pop_reg.get("beta_excess_basal", 0)
        pop_ordering = pop_bc > pop_bs > pop_be

    verdicts["H3"] = {
        "description": "β_correction > β_smb > β_excess_basal",
        "patient_level_pass": h3_pass,
        "patient_level_total": h3_total,
        "patient_level_pct": h3_pass / h3_total * 100 if h3_total > 0 else 0,
        "population_ordering": pop_ordering,
        "verdict": "PASS" if pop_ordering or (h3_pass / max(h3_total, 1) > 0.5) else "FAIL",
    }

    # --- H4: Regression ISF has narrower 95% CI than division ISF ---
    reg_ci_widths = []
    div_ci_widths = []
    for p in reg_patients:
        # Regression CI
        m2 = p["regression_4h"]["model2_multifactor"]
        ci = m2.get("ci95_isf")
        if ci and len(ci) == 2 and not np.isnan(ci[0]) and not np.isnan(ci[1]):
            reg_ci_widths.append(abs(ci[1] - ci[0]))

        # Division CI (IQR as proxy)
        div = p.get("division_4h", {})
        iqr = div.get("isf_correction_division_iqr")
        if iqr and len(iqr) == 2 and not np.isnan(iqr[0]) and not np.isnan(iqr[1]):
            div_ci_widths.append(abs(iqr[1] - iqr[0]))

    reg_med_ci = safe_median(reg_ci_widths)
    div_med_ci = safe_median(div_ci_widths)
    verdicts["H4"] = {
        "description": "Regression ISF has narrower 95% CI than division ISF IQR",
        "median_regression_ci_width": reg_med_ci,
        "median_division_iqr_width": div_med_ci,
        "narrower": bool(reg_med_ci < div_med_ci) if not (np.isnan(reg_med_ci) or np.isnan(div_med_ci)) else None,
        "verdict": "PASS" if (not np.isnan(reg_med_ci) and not np.isnan(div_med_ci) and reg_med_ci < div_med_ci) else "FAIL",
    }

    # --- H5: Multi-factor regression ISF predicted safe for >50% ---
    safe_count = 0
    h5_total = 0
    for p in reg_patients:
        s = p.get("safety", {}).get("multifactor_regression", {})
        if s.get("safe") is not None:
            h5_total += 1
            if bool(s["safe"]):
                safe_count += 1

    h5_pct = safe_count / h5_total * 100 if h5_total > 0 else 0
    verdicts["H5"] = {
        "description": "Multi-factor regression ISF predicted safe (TBR < 2pp) for >50% of patients",
        "safe_count": safe_count,
        "total": h5_total,
        "pct_safe": h5_pct,
        "threshold": 50.0,
        "verdict": "PASS" if h5_pct > 50 else "FAIL",
    }

    return verdicts


# ---------------------------------------------------------------------------
# Visualization (2×3 panel)
# ---------------------------------------------------------------------------
def create_visualizations(patient_results: list[dict], pop_reg: dict, verdicts: dict):
    """Create 2×3 panel dashboard."""
    print("[6/7] Creating visualizations ...")
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    reg_patients = [p for p in patient_results if p.get("regression_4h", {}).get("status") == "ok"]
    all_patients = [p for p in patient_results if p.get("n_events", 0) > 0]

    fig = plt.figure(figsize=(20, 14))
    gs = gridspec.GridSpec(2, 3, hspace=0.35, wspace=0.35)

    # Colour scheme
    C_DIV_NAIVE = "#d62728"
    C_DIV_CORR = "#ff7f0e"
    C_REG_NAIVE = "#2ca02c"
    C_REG_MF = "#1f77b4"
    C_PROFILE = "#9467bd"

    # -----------------------------------------------------------------------
    # Panel 1: ISF method comparison (box plots)
    # -----------------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0])

    isf_data = {
        "Div-Naive": [],
        "Div-Corr": [],
        "Reg-Naive": [],
        "Reg-MF": [],
        "Profile": [],
    }
    for p in all_patients:
        # Division
        d4 = p.get("division_4h", {})
        isf_data["Div-Naive"].append(d4.get("isf_naive_division", np.nan))
        isf_data["Div-Corr"].append(d4.get("isf_correction_division", np.nan))
        # Profile
        isf_data["Profile"].append(p.get("isf_profile", np.nan))

        # Regression
        r4 = p.get("regression_4h", {})
        if r4.get("status") == "ok":
            m1 = r4.get("model1_simple", {})
            isf_data["Reg-Naive"].append(m1.get("isf_naive_regression", np.nan))
            m2 = r4.get("model2_multifactor", {})
            isf_data["Reg-MF"].append(m2.get("isf_correction", np.nan))
        else:
            isf_data["Reg-Naive"].append(np.nan)
            isf_data["Reg-MF"].append(np.nan)

    # Prepare for boxplot (filter NaN per group)
    bp_data = []
    bp_labels = []
    bp_colors = [C_DIV_NAIVE, C_DIV_CORR, C_REG_NAIVE, C_REG_MF, C_PROFILE]
    for label, color in zip(isf_data.keys(), bp_colors):
        vals = [v for v in isf_data[label] if np.isfinite(v)]
        bp_data.append(vals if vals else [0])
        bp_labels.append(label)

    bplot = ax1.boxplot(bp_data, patch_artist=True, tick_labels=bp_labels, widths=0.6)
    for patch, color in zip(bplot["boxes"], bp_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax1.set_ylabel("ISF (mg/dL per U)")
    ax1.set_title("Panel 1: ISF Method Comparison")
    ax1.tick_params(axis="x", rotation=30)
    # Clip y-axis to avoid extreme outliers dominating
    yvals = [v for vals in bp_data for v in vals if np.isfinite(v)]
    if yvals:
        y_lo = max(min(yvals), -200)
        y_hi = min(max(yvals), 600)
        margin = (y_hi - y_lo) * 0.1
        ax1.set_ylim(y_lo - margin, y_hi + margin)
    ax1.axhline(0, color="gray", ls="--", lw=0.5)

    # -----------------------------------------------------------------------
    # Panel 2: Regression coefficients per patient with CIs
    # -----------------------------------------------------------------------
    ax2 = fig.add_subplot(gs[0, 1])

    pid_labels = []
    beta_corr = []
    beta_smb = []
    beta_eb = []
    se_corr = []
    se_smb_v = []
    se_eb_v = []

    for p in reg_patients:
        m2 = p["regression_4h"]["model2_multifactor"]
        pid_labels.append(p["patient_id"][:8])
        beta_corr.append(m2.get("isf_correction", 0))
        beta_smb.append(m2.get("beta_smb", 0))
        beta_eb.append(m2.get("beta_excess_basal", 0))
        se_corr.append(m2.get("se_correction", 0) * 1.96)
        se_smb_v.append(m2.get("se_smb", 0) * 1.96)
        se_eb_v.append(m2.get("se_excess_basal", 0) * 1.96)

    if pid_labels:
        x = np.arange(len(pid_labels))
        w = 0.25
        ax2.bar(x - w, beta_corr, w, yerr=se_corr, label="β correction", color=C_REG_MF, alpha=0.7, capsize=2)
        ax2.bar(x, beta_smb, w, yerr=se_smb_v, label="β SMB", color=C_REG_NAIVE, alpha=0.7, capsize=2)
        ax2.bar(x + w, beta_eb, w, yerr=se_eb_v, label="β excess basal", color=C_DIV_CORR, alpha=0.7, capsize=2)
        ax2.set_xticks(x)
        ax2.set_xticklabels(pid_labels, rotation=45, ha="right", fontsize=7)
        ax2.legend(fontsize=7, loc="upper right")
    ax2.set_ylabel("Coefficient (mg/dL per U)")
    ax2.set_title("Panel 2: Regression Coefficients (Model 2)")
    ax2.axhline(0, color="gray", ls="--", lw=0.5)

    # -----------------------------------------------------------------------
    # Panel 3: R² comparison: simple vs multi-factor
    # -----------------------------------------------------------------------
    ax3 = fig.add_subplot(gs[0, 2])

    r2_simple = []
    r2_multi = []
    r2_labels = []
    for p in reg_patients:
        r2_labels.append(p["patient_id"][:8])
        m1 = p["regression_4h"].get("model1_simple", {})
        m2 = p["regression_4h"].get("model2_multifactor", {})
        r2_simple.append(m1.get("r2", 0))
        r2_multi.append(m2.get("r2", 0))

    if r2_labels:
        x = np.arange(len(r2_labels))
        w = 0.35
        ax3.bar(x - w / 2, r2_simple, w, label="Simple (Model 1)", color=C_REG_NAIVE, alpha=0.7)
        ax3.bar(x + w / 2, r2_multi, w, label="Multi-factor (Model 2)", color=C_REG_MF, alpha=0.7)
        ax3.set_xticks(x)
        ax3.set_xticklabels(r2_labels, rotation=45, ha="right", fontsize=7)
        ax3.legend(fontsize=7)
    ax3.axhline(0.15, color="red", ls="--", lw=1, label="H2 threshold")
    ax3.set_ylabel("R²")
    ax3.set_title("Panel 3: R² Simple vs Multi-Factor")

    # -----------------------------------------------------------------------
    # Panel 4: ISF precision (CI width comparison)
    # -----------------------------------------------------------------------
    ax4 = fig.add_subplot(gs[1, 0])

    ci_reg_w = []
    ci_div_w = []
    ci_labels = []
    for p in reg_patients:
        m2 = p["regression_4h"]["model2_multifactor"]
        ci = m2.get("ci95_isf")
        div_iqr = p.get("division_4h", {}).get("isf_correction_division_iqr")
        if ci and len(ci) == 2 and not np.isnan(ci[0]) and not np.isnan(ci[1]):
            rw = abs(ci[1] - ci[0])
        else:
            rw = np.nan
        if div_iqr and len(div_iqr) == 2 and not np.isnan(div_iqr[0]) and not np.isnan(div_iqr[1]):
            dw = abs(div_iqr[1] - div_iqr[0])
        else:
            dw = np.nan
        if np.isfinite(rw) or np.isfinite(dw):
            ci_reg_w.append(rw if np.isfinite(rw) else 0)
            ci_div_w.append(dw if np.isfinite(dw) else 0)
            ci_labels.append(p["patient_id"][:8])

    if ci_labels:
        x = np.arange(len(ci_labels))
        w = 0.35
        ax4.bar(x - w / 2, ci_div_w, w, label="Division IQR", color=C_DIV_CORR, alpha=0.7)
        ax4.bar(x + w / 2, ci_reg_w, w, label="Regression 95% CI", color=C_REG_MF, alpha=0.7)
        ax4.set_xticks(x)
        ax4.set_xticklabels(ci_labels, rotation=45, ha="right", fontsize=7)
        ax4.legend(fontsize=7)
    ax4.set_ylabel("Width (mg/dL per U)")
    ax4.set_title("Panel 4: ISF Precision")

    # -----------------------------------------------------------------------
    # Panel 5: Safety prediction (dot plot with threshold)
    # -----------------------------------------------------------------------
    ax5 = fig.add_subplot(gs[1, 1])

    methods = ["naive_division", "correction_division", "naive_regression", "multifactor_regression"]
    method_labels = ["Div-Naive", "Div-Corr", "Reg-Naive", "Reg-MF"]
    method_colors = [C_DIV_NAIVE, C_DIV_CORR, C_REG_NAIVE, C_REG_MF]

    for mi, (method, mlabel, mcol) in enumerate(zip(methods, method_labels, method_colors)):
        tbr_vals = []
        for p in reg_patients:
            s = p.get("safety", {}).get(method, {})
            tv = s.get("predicted_tbr_change_pp")
            if tv is not None and np.isfinite(tv):
                tbr_vals.append(tv)
        if tbr_vals:
            jitter = np.random.default_rng(42 + mi).uniform(-0.15, 0.15, len(tbr_vals))
            ax5.scatter(
                np.full(len(tbr_vals), mi) + jitter,
                tbr_vals,
                c=mcol, alpha=0.6, s=30, edgecolors="k", linewidths=0.3,
            )

    ax5.axhline(SAFETY_TBR_THRESHOLD, color="red", ls="--", lw=1.5, label=f"Safety threshold ({SAFETY_TBR_THRESHOLD}pp)")
    ax5.axhline(0, color="gray", ls="--", lw=0.5)
    ax5.set_xticks(range(len(method_labels)))
    ax5.set_xticklabels(method_labels, rotation=30)
    ax5.set_ylabel("Predicted ΔT BR (pp)")
    ax5.set_title("Panel 5: Safety Prediction")
    ax5.legend(fontsize=7)

    # -----------------------------------------------------------------------
    # Panel 6: Gap-closure waterfall
    # -----------------------------------------------------------------------
    ax6 = fig.add_subplot(gs[1, 2])

    # Compute median absolute ratio-to-profile for each method
    stages = ["Div-Naive", "Div-Corr", "Reg-MF", "Profile"]
    stage_keys = [
        ("division_4h", "isf_naive_division"),
        ("division_4h", "isf_correction_division"),
        ("regression_4h.model2_multifactor", "isf_correction"),
        (None, "isf_profile"),
    ]
    stage_errors = []

    for stage_label, (container, key) in zip(stages, stage_keys):
        ratios = []
        for p in all_patients:
            isf_prof = p.get("isf_profile")
            if isf_prof is None or np.isnan(isf_prof) or isf_prof <= 0:
                continue
            if container is None:
                isf_val = p.get(key)
            elif "." in container:
                parts = container.split(".")
                obj = p
                for part in parts:
                    obj = obj.get(part, {}) if isinstance(obj, dict) else {}
                isf_val = obj.get(key) if isinstance(obj, dict) else None
            else:
                isf_val = p.get(container, {}).get(key)
            if isf_val is not None and np.isfinite(isf_val) and isf_val > 0:
                ratios.append(abs(isf_val / isf_prof - 1.0))  # distance from 1.0
        stage_errors.append(safe_median(ratios) * 100 if ratios else np.nan)

    # Waterfall: show decrease in median error
    colors_wf = [C_DIV_NAIVE, C_DIV_CORR, C_REG_MF, C_PROFILE]
    valid_stages = [(s, e, c) for s, e, c in zip(stages, stage_errors, colors_wf) if np.isfinite(e)]
    if valid_stages:
        xs = np.arange(len(valid_stages))
        bars = [e for _, e, _ in valid_stages]
        cols = [c for _, _, c in valid_stages]
        lbls = [s for s, _, _ in valid_stages]
        ax6.bar(xs, bars, color=cols, alpha=0.7, edgecolor="k", linewidth=0.5)
        ax6.set_xticks(xs)
        ax6.set_xticklabels(lbls, rotation=30)
        for xi, b in zip(xs, bars):
            ax6.text(xi, b + 1, f"{b:.0f}%", ha="center", va="bottom", fontsize=8)
    ax6.set_ylabel("Median |ISF/Profile − 1| (%)")
    ax6.set_title("Panel 6: Gap Closure Waterfall")

    # -----------------------------------------------------------------------
    # Title and save
    # -----------------------------------------------------------------------
    n_reg = len(reg_patients)
    n_all = len(all_patients)
    h_str = "  |  ".join(f"{k}: {v['verdict']}" for k, v in verdicts.items())
    fig.suptitle(
        f"EXP-2754: Regression-Based Multi-Factor ISF  |  "
        f"{n_reg} regression patients / {n_all} total  |  {h_str}",
        fontsize=11, fontweight="bold", y=0.98,
    )

    fig.savefig(VIZ_DIR / "regression_isf.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {VIZ_DIR / 'regression_isf.png'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 72)
    print("EXP-2754: Regression-Based Multi-Factor ISF")
    print("=" * 72)

    grid, qualified, ctrl_map = load_data()

    # ------------------------------------------------------------------
    # Step 1–2: Per-patient event extraction + regression
    # ------------------------------------------------------------------
    print("[2/7] Extracting correction events and running regressions ...")
    patient_results = []
    all_events = {}  # pid → events (for population regression)

    for pid in sorted(qualified):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < 100:
            print(f"  {pid}: too few rows ({len(pg)}), skipping")
            continue

        ctrl = ctrl_map.get(pid, "unknown")
        result = analyse_patient(pid, pg, ctrl)
        patient_results.append(result)

        # Store events for population regression
        sched_basal = result["scheduled_basal_estimated"]
        events = extract_correction_events(pg, sched_basal)
        if events:
            all_events[pid] = events

        status = result.get("status", "")
        n_ev = result.get("n_events", 0)
        reg_st = result.get("regression_4h", {}).get("status", "N/A")
        print(f"  {pid:25s}  events={n_ev:4d}  reg_status={reg_st}")

    print(f"\n  Total patients analysed:  {len(patient_results)}")
    print(f"  Patients with regression: {sum(1 for p in patient_results if p.get('regression_4h', {}).get('status') == 'ok')}")
    print(f"  Total events pooled:      {sum(len(v) for v in all_events.values())}")

    # ------------------------------------------------------------------
    # Step 3: Population regression
    # ------------------------------------------------------------------
    print("\n[3/7] Running population (pooled) regression with fixed effects ...")
    pop_reg_4h = run_population_regression(all_events, "4h")
    pop_reg_2h = run_population_regression(all_events, "2h")

    if pop_reg_4h.get("status") == "ok":
        print(f"  Population ISF (4h): {pop_reg_4h['isf_population']:.1f} mg/dL per U")
        print(f"  β_smb: {pop_reg_4h['beta_smb']:.1f},  β_excess_basal: {pop_reg_4h['beta_excess_basal']:.1f}")
        print(f"  R²: {pop_reg_4h['r2']:.3f},  N={pop_reg_4h['n_events']},  patients={pop_reg_4h['n_patients']}")
    else:
        print(f"  Population regression status: {pop_reg_4h.get('status')}")

    # ------------------------------------------------------------------
    # Step 4: Compare ISF methods (summary table)
    # ------------------------------------------------------------------
    print("\n[4/7] ISF method comparison ...")
    reg_patients = [p for p in patient_results if p.get("regression_4h", {}).get("status") == "ok"]

    header = f"{'Patient':>15s} | {'Div-Naive':>10s} | {'Div-Corr':>10s} | {'Reg-Naive':>10s} | {'Reg-MF':>10s} | {'Profile':>10s} | {'Ratio':>6s}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for p in reg_patients:
        d4 = p.get("division_4h", {})
        r4 = p["regression_4h"]
        dn = d4.get("isf_naive_division", np.nan)
        dc = d4.get("isf_correction_division", np.nan)
        rn = r4.get("model1_simple", {}).get("isf_naive_regression", np.nan)
        rm = r4.get("model2_multifactor", {}).get("isf_correction", np.nan)
        pr = p.get("isf_profile", np.nan)
        ratio = rm / pr if (pr and pr > 0 and np.isfinite(rm)) else np.nan
        print(f"  {p['patient_id'][:15]:>15s} | {dn:10.1f} | {dc:10.1f} | {rn:10.1f} | {rm:10.1f} | {pr:10.1f} | {ratio:6.2f}")

    # ------------------------------------------------------------------
    # Step 5: Hypothesis evaluation
    # ------------------------------------------------------------------
    print("\n[5/7] Evaluating hypotheses ...")
    verdicts = evaluate_hypotheses(patient_results, pop_reg_4h)

    for hid, v in verdicts.items():
        print(f"\n  {hid}: {v['verdict']}  —  {v['description']}")
        for k2, v2 in v.items():
            if k2 not in ("verdict", "description"):
                print(f"    {k2}: {v2}")

    # ------------------------------------------------------------------
    # Step 6: Visualisation
    # ------------------------------------------------------------------
    create_visualizations(patient_results, pop_reg_4h, verdicts)

    # ------------------------------------------------------------------
    # Step 7: Save results JSON
    # ------------------------------------------------------------------
    print("\n[7/7] Saving results ...")

    # Strip large per-event arrays from division results for JSON
    for p in patient_results:
        for key in ("division_4h", "division_2h"):
            d = p.get(key, {})
            d.pop("isf_naive_values", None)
            d.pop("isf_correction_values", None)

    output = {
        "experiment": "EXP-2754",
        "title": "Regression-Based Multi-Factor ISF",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "parameters": {
            "bg_threshold": BG_THRESHOLD,
            "min_bolus": MIN_BOLUS,
            "carb_exclusion_prior_steps": CARB_EXCLUSION_PRIOR,
            "min_events_per_patient": MIN_EVENTS_PER_PATIENT,
            "horizons": ["2h", "4h"],
            "calm_roc_threshold": CALM_ROC_THRESHOLD,
            "safety_rho": SAFETY_RHO,
            "safety_tbr_threshold": SAFETY_TBR_THRESHOLD,
        },
        "summary": {
            "n_patients_total": len(patient_results),
            "n_patients_regression": sum(
                1 for p in patient_results
                if p.get("regression_4h", {}).get("status") == "ok"
            ),
            "n_events_total": sum(p.get("n_events", 0) for p in patient_results),
            "n_events_pooled": sum(len(v) for v in all_events.values()),
        },
        "population_regression_4h": pop_reg_4h,
        "population_regression_2h": pop_reg_2h,
        "hypotheses": verdicts,
        "per_patient": patient_results,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2, default=json_safe))
    print(f"  Saved → {RESULTS_PATH}")

    # ------------------------------------------------------------------
    # Final verdicts
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("HYPOTHESIS VERDICTS")
    print("=" * 72)
    all_pass = True
    for hid, v in verdicts.items():
        symbol = "✓" if v["verdict"] == "PASS" else "✗"
        print(f"  {symbol} {hid}: {v['verdict']}  —  {v['description']}")
        if v["verdict"] != "PASS":
            all_pass = False
    overall = "ALL PASS" if all_pass else "MIXED"
    print(f"\n  Overall: {overall}")
    print("=" * 72)


if __name__ == "__main__":
    main()
