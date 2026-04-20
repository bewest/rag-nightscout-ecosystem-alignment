#!/usr/bin/env python3
"""
EXP-2740: Basal-EGP Equilibrium Analysis
=========================================

Scientific Question
-------------------
During fasting periods, what is the per-patient EGP-basal equilibrium?
After subtracting all non-basal insulin effects and meal effects, does
the residual glucose drift reveal:
  1. How well-matched basal and EGP are per patient
  2. Circadian patterns in the mismatch
  3. Whether the "basal is 92% EGP" finding (EXP-2735) holds with
     proper multi-factor subtraction

Predecessors
------------
- EXP-2735: EGP-Aware Basal Optimization (92% EGP fraction finding)
- EXP-2739: Per-Patient EGP Profiling & Precision

Hypotheses
----------
H1: Fasting glucose drift (after full subtraction) is <0.5 mg/dL/5min
    for >50% of patients — basal-EGP is reasonably matched.
H2: EGP estimate from fasting periods matches EXP-2739 per-patient
    estimates within 30% — method consistency.
H3: Circadian basal-EGP mismatch amplitude >1 mg/dL/5min in >50% of
    patients — circadian adjustment needed.
H4: Subtracting SMB/temp-basal effects reduces drift variance by >20%
    — multi-factor subtraction helps.
H5: Residual-based basal recommendation has <30% TDD change for >80%
    of patients — much more conservative than naive (EXP-2730).
"""

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Constants ─────────────────────────────────────────────────────────

EXP_ID = "2740"
TITLE = "Basal-EGP Equilibrium Analysis"

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_basal_egp_equilibrium.json"
VIZ_DIR = Path("visualizations/basal-egp-equilibrium")
EXP2739_JSON = RESULTS_DIR / "exp-2739_egp_personalization.json"

# Fasting window parameters
FASTING_CARB_LOOKBACK = 48    # 4 h no carbs before (48 × 5 min = 240 min)
FASTING_CARB_LOOKAHEAD = 24   # 2 h no carbs after  (24 × 5 min = 120 min)
FASTING_BOLUS_LOOKBACK = 24   # 2 h no manual bolus before
COB_THRESHOLD = 0.5            # g  — COB must be below this
MIN_FASTING_OBS = 50           # minimum fasting 5-min intervals per patient

# EGP bounds  (same convention as EXP-2739: mg/dL per 5 min)
EGP_FLOOR = -5.0
EGP_CEIL = 15.0

# Drift bounds
DRIFT_FLOOR = -5.0
DRIFT_CEIL = 5.0

# Circadian
DAWN_HOURS = [4, 5, 6, 7]
NADIR_HOURS = [22, 23, 0, 1]
MIN_HOURLY_OBS = 5

# Statistical
N_BOOTSTRAP = 500
BOOTSTRAP_SEED = 2740

# Reference from EXP-2735
POP_EGP_FRACTION = 0.92

# Regression coefficients from prior experiments
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5


# ── Helper Functions ──────────────────────────────────────────────────

def safe_float(v) -> Optional[float]:
    """Convert value to float, returning None if not finite."""
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def safe_median(arr) -> float:
    """Median that handles empty arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(np.median(arr)) if len(arr) > 0 else np.nan


def safe_iqr(arr) -> float:
    """IQR that handles small arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 4:
        return np.nan
    return float(np.percentile(arr, 75) - np.percentile(arr, 25))


def safe_cv(arr) -> Optional[float]:
    """Coefficient of variation, guarded against zero mean."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return None
    m = np.mean(arr)
    if abs(m) < 1e-9:
        return None
    return float(np.std(arr) / abs(m))


def safe_std(arr) -> float:
    """Standard deviation handling empty arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(np.std(arr)) if len(arr) > 1 else np.nan


def bootstrap_ci(arr, n_boot=N_BOOTSTRAP, ci=0.95, seed=BOOTSTRAP_SEED):
    """Bootstrap confidence interval for the median."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 5:
        return np.nan, np.nan
    rng = np.random.RandomState(seed)
    medians = np.array([
        np.median(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    lo = np.percentile(medians, (1 - ci) / 2 * 100)
    hi = np.percentile(medians, (1 + ci) / 2 * 100)
    return float(lo), float(hi)


def hour_of_day(time_series: pd.Series) -> np.ndarray:
    """Extract hour-of-day from a datetime series."""
    ts = pd.to_datetime(time_series)
    return ts.dt.hour.values


def infer_controller(pdf: pd.DataFrame) -> str:
    """Infer controller type from available columns.

    Trio/OpenAPS patients have non-null sensitivity_ratio;
    Loop patients have non-null loop_predicted_30.
    """
    if "sensitivity_ratio" in pdf.columns:
        sr_valid = pdf["sensitivity_ratio"].notna().sum()
        if sr_valid > len(pdf) * 0.3:
            return "trio"
    if "loop_predicted_30" in pdf.columns:
        lp_valid = pdf["loop_predicted_30"].notna().sum()
        if lp_valid > len(pdf) * 0.3:
            return "loop"
    return "unknown"


def sanitize_for_json(obj: Any) -> Any:
    """Recursively replace NaN / Inf with None for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if not np.isfinite(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# ── Data Loading ──────────────────────────────────────────────────────

def load_data() -> Tuple[pd.DataFrame, List[str]]:
    """Load grid data and qualified patient list."""
    print("\n  Loading grid data ...")
    grid = pd.read_parquet(GRID)
    manifest = json.load(open(MANIFEST))
    qualified = manifest["qualified_patients"]
    grid = grid[grid["patient_id"].isin(qualified)].copy()
    print(
        f"  Grid: {len(grid):,} rows × {len(grid.columns)} cols, "
        f"{len(qualified)} qualified patients"
    )
    return grid, qualified


def load_exp2739() -> Optional[Dict]:
    """Load EXP-2739 results for cross-validation of EGP estimates."""
    if not EXP2739_JSON.exists():
        print(f"  WARNING: EXP-2739 results not found at {EXP2739_JSON}")
        return None
    with open(EXP2739_JSON) as f:
        data = json.load(f)
    lookup: Dict[str, Dict] = {}
    for prof in data.get("per_patient_egp_profiles", []):
        pid = prof.get("patient_id")
        if pid and prof.get("egp_median") is not None:
            lookup[pid] = {
                "egp_median": prof["egp_median"],
                "hourly_egp": prof.get("hourly_egp", []),
            }
    print(f"  Loaded EXP-2739: {len(lookup)} patient EGP profiles")
    return lookup


# ── Step 1: Enhanced Fasting-Window Identification ────────────────────

def identify_fasting_mask(pdf: pd.DataFrame) -> np.ndarray:
    """Return boolean mask of clean fasting 5-min intervals.

    Requirements
    ------------
    - No carbs for ≥ 4 h prior  AND  ≥ 2 h after  (no meal contamination)
    - No manual bolus for ≥ 2 h prior  (no correction contamination)
    - COB ≈ 0  (carbs on board depleted)
    - Valid glucose, glucose_roc, insulin_activity, scheduled_isf
    """
    n = len(pdf)
    carbs = pdf["carbs"].fillna(0).values.astype(float)
    bolus = pdf["bolus"].fillna(0).values.astype(float)
    cob = (
        pdf["cob"].fillna(0).values.astype(float)
        if "cob" in pdf.columns
        else np.zeros(n)
    )

    # Backward-looking rolling sums
    carb_back = np.zeros(n, dtype=float)
    bolus_back = np.zeros(n, dtype=float)
    for i in range(n):
        c_start = max(0, i - FASTING_CARB_LOOKBACK + 1)
        b_start = max(0, i - FASTING_BOLUS_LOOKBACK + 1)
        carb_back[i] = np.nansum(carbs[c_start : i + 1])
        bolus_back[i] = np.nansum(bolus[b_start : i + 1])

    # Forward-looking carb check
    carb_fwd = np.zeros(n, dtype=float)
    for i in range(n):
        c_end = min(n, i + FASTING_CARB_LOOKAHEAD)
        carb_fwd[i] = np.nansum(carbs[i:c_end])

    mask = (
        (carb_back < 0.5)
        & (carb_fwd < 0.5)
        & (bolus_back < 0.1)
        & (cob < COB_THRESHOLD)
    )

    # Valid sensor / algorithm data
    for col in ["glucose_roc", "insulin_activity", "scheduled_isf", "glucose"]:
        if col in pdf.columns:
            mask &= np.isfinite(pdf[col].values)

    # Need scheduled_basal_rate for the decomposition
    if "scheduled_basal_rate" in pdf.columns:
        mask &= np.isfinite(pdf["scheduled_basal_rate"].values)

    return mask


# ── Step 2: Multi-Factor Decomposition ───────────────────────────────

def compute_fasting_decomposition(
    pdf: pd.DataFrame, fasting_mask: np.ndarray
) -> pd.DataFrame:
    """Decompose fasting glucose dynamics into components.

    Components
    ----------
    raw_drift          : observed glucose_roc during fasting (the composite signal)
    total_bgi          : BGI from ALL insulin  (−insulin_activity × ISF)
    egp_estimate       : back-calculated EGP = glucose_roc − total_bgi
    excess_basal       : net_basal − scheduled_basal_rate  (controller temp adjustment)
    adjusted_drift     : OLS residual after regressing out controller covariates

    The adjusted drift uses per-patient OLS regression to remove the
    empirical effect of controller actions (temp-basal adjustments and
    SMBs) from the raw drift.  This avoids the unit mismatch that arises
    from directly comparing delivery rates to PK-processed insulin
    activity.  Regression automatically finds the correct conversion.

    Units follow the EXP-2739 convention for cross-experiment consistency:
        egp = glucose_roc + insulin_activity × scheduled_isf
    """
    roc = pdf["glucose_roc"].values.copy()
    ia = pdf["insulin_activity"].values.copy()
    isf = pdf["scheduled_isf"].values.copy()
    gluc = pdf["glucose"].values.copy()
    hours = hour_of_day(pdf["time"])

    net_basal = (
        pdf["net_basal"].fillna(0).values.copy()
        if "net_basal" in pdf.columns
        else np.zeros(len(pdf))
    )
    sched_basal = (
        pdf["scheduled_basal_rate"].fillna(0).values.copy()
        if "scheduled_basal_rate" in pdf.columns
        else np.zeros(len(pdf))
    )
    bolus_smb = (
        pdf["bolus_smb"].fillna(0).values.copy()
        if "bolus_smb" in pdf.columns
        else np.zeros(len(pdf))
    )
    iob = (
        pdf["iob"].fillna(0).values.copy()
        if "iob" in pdf.columns
        else np.zeros(len(pdf))
    )

    # Total BGI from all insulin (negative → insulin lowers glucose)
    total_bgi = -ia * isf

    # EGP estimate: liver glucose production
    egp_estimate = roc - total_bgi   # = roc + ia × isf

    # Controller action variables (delivery-rate space)
    excess_basal = net_basal - sched_basal   # U/hr above scheduled

    # Raw drift: what we observe
    raw_drift = roc.copy()

    # Placeholder adjusted drift (will be computed per-patient after filtering)
    adjusted_drift = raw_drift.copy()

    result = pd.DataFrame(
        {
            "raw_drift": raw_drift,
            "total_bgi": total_bgi,
            "egp_estimate": egp_estimate,
            "excess_basal": excess_basal,
            "adjusted_drift": adjusted_drift,
            "glucose": gluc,
            "insulin_activity": ia,
            "scheduled_isf": isf,
            "net_basal": net_basal,
            "scheduled_basal_rate": sched_basal,
            "bolus_smb": bolus_smb,
            "iob": iob,
            "hour": hours,
            "fasting": fasting_mask,
        }
    )

    # Filter to fasting only
    result = result[fasting_mask].copy()

    # Remove EGP outliers
    result = result[
        (result["egp_estimate"] >= EGP_FLOOR)
        & (result["egp_estimate"] <= EGP_CEIL)
    ].copy()

    # Remove drift outliers
    result = result[
        (result["raw_drift"] >= DRIFT_FLOOR)
        & (result["raw_drift"] <= DRIFT_CEIL)
    ].copy()

    return result


# ── Step 3: Per-Patient Analysis ──────────────────────────────────────

def analyze_patient(pdf: pd.DataFrame, pid: str) -> Optional[Dict]:
    """Full basal-EGP equilibrium analysis for one patient."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    if len(pdf) < 500:
        return None

    controller = infer_controller(pdf)

    # -- fasting identification --
    fasting_mask = identify_fasting_mask(pdf)
    n_fasting = int(fasting_mask.sum())
    if n_fasting < MIN_FASTING_OBS:
        return None

    fdf = compute_fasting_decomposition(pdf, fasting_mask)
    if len(fdf) < MIN_FASTING_OBS:
        return None

    # ── Raw drift statistics ────────────────────────────
    raw = fdf["raw_drift"].values
    raw_mean = float(np.mean(raw))
    raw_median = float(np.median(raw))
    raw_std = float(np.std(raw))
    raw_abs_mean = float(np.mean(np.abs(raw)))
    raw_var = float(np.var(raw))

    # ── Regression-based controller subtraction ──────────
    # Model: glucose_roc = β₀ + β₁·excess_basal + β₂·bolus_smb + ε
    # β₀ = equilibrium drift when controller is idle
    # adjusted_drift = β₀ + ε  (residual without controller effects)
    excess_b = fdf["excess_basal"].values
    smb_v = fdf["bolus_smb"].values

    # Build design matrix [1, excess_basal, bolus_smb]
    n_obs = len(raw)
    X_ctrl = np.column_stack([np.ones(n_obs), excess_b, smb_v])
    beta, _res, _rank, _sv = np.linalg.lstsq(X_ctrl, raw, rcond=None)

    # Adjusted = raw minus controller-explained component (keep intercept)
    controller_predicted = X_ctrl[:, 1:] @ beta[1:]
    adj = raw - controller_predicted   # = β₀ + ε

    # Store regression coefficients for diagnostics
    reg_intercept = float(beta[0])
    reg_excess_basal_coeff = float(beta[1])
    reg_smb_coeff = float(beta[2])
    controller_r2 = (
        1.0 - np.var(adj) / raw_var if raw_var > 1e-9 else 0.0
    )

    adj_mean = float(np.mean(adj))
    adj_median = float(np.median(adj))
    adj_std = float(np.std(adj))
    adj_abs_mean = float(np.mean(np.abs(adj)))
    adj_var = float(np.var(adj))

    # ── Variance reduction from multi-factor subtraction ─
    if raw_var > 1e-9:
        var_reduction_pct = (1.0 - adj_var / raw_var) * 100
    else:
        var_reduction_pct = np.nan

    # ── EGP statistics ──────────────────────────────────
    egp = fdf["egp_estimate"].values
    egp_median = float(np.median(egp))
    egp_mean = float(np.mean(egp))
    egp_std = float(np.std(egp))
    egp_ci_lo, egp_ci_hi = bootstrap_ci(egp)

    # ── Circadian analysis ──────────────────────────────
    hours = fdf["hour"].values
    hourly_drift: Dict[int, Dict] = {}
    hourly_egp: Dict[int, Dict] = {}
    hourly_adj_drift: Dict[int, Dict] = {}

    for h in range(24):
        h_mask = hours == h
        h_raw = raw[h_mask]
        h_egp = egp[h_mask]
        h_adj = adj[h_mask]

        if len(h_raw) >= MIN_HOURLY_OBS:
            hourly_drift[h] = {
                "median": float(np.median(h_raw)),
                "mean": float(np.mean(h_raw)),
                "std": float(np.std(h_raw)),
                "n": int(len(h_raw)),
            }
            hourly_egp[h] = {
                "median": float(np.median(h_egp)),
                "mean": float(np.mean(h_egp)),
                "n": int(len(h_egp)),
            }
            hourly_adj_drift[h] = {
                "median": float(np.median(h_adj)),
                "mean": float(np.mean(h_adj)),
                "std": float(np.std(h_adj)),
                "n": int(len(h_adj)),
            }

    # Circadian EGP: 24-element list (None for missing hours)
    circadian_egp: List[Optional[float]] = []
    for h in range(24):
        if h in hourly_egp:
            circadian_egp.append(safe_float(hourly_egp[h]["median"]))
        else:
            circadian_egp.append(None)

    # Dawn vs nadir
    dawn_vals = [hourly_drift[h]["median"] for h in DAWN_HOURS if h in hourly_drift]
    nadir_vals = [hourly_drift[h]["median"] for h in NADIR_HOURS if h in hourly_drift]
    dawn_drift = safe_median(dawn_vals) if dawn_vals else np.nan
    nadir_drift = safe_median(nadir_vals) if nadir_vals else np.nan

    if np.isfinite(dawn_drift) and np.isfinite(nadir_drift):
        circadian_amplitude = abs(dawn_drift - nadir_drift)
    else:
        circadian_amplitude = np.nan

    # Full circadian range (max − min across all hours with data)
    hourly_medians = [
        hourly_drift[h]["median"] for h in range(24) if h in hourly_drift
    ]
    if len(hourly_medians) >= 6:
        circadian_range = float(max(hourly_medians) - min(hourly_medians))
    else:
        circadian_range = np.nan

    # Kruskal-Wallis test for circadian significance
    hour_groups = []
    for h in range(24):
        h_mask = hours == h
        h_vals = raw[h_mask]
        if len(h_vals) >= MIN_HOURLY_OBS:
            hour_groups.append(h_vals)

    if len(hour_groups) >= 3:
        try:
            kw_stat, kw_p = stats.kruskal(*hour_groups)
            kw_stat, kw_p = float(kw_stat), float(kw_p)
        except ValueError:
            kw_stat, kw_p = np.nan, np.nan
    else:
        kw_stat, kw_p = np.nan, np.nan

    # ── Basal-rate recommendation ───────────────────────
    median_isf = float(np.median(fdf["scheduled_isf"].values))
    median_sched_basal = float(np.median(fdf["scheduled_basal_rate"].values))

    # If adjusted_drift > 0 → glucose rising → basal insufficient → increase
    # delta_basal = adj_mean / ISF  (in the same rate units as basal)
    if median_isf > 1e-6 and np.isfinite(adj_mean):
        basal_adjustment = adj_mean / median_isf
    else:
        basal_adjustment = np.nan

    if np.isfinite(basal_adjustment) and median_sched_basal > 0.01:
        basal_pct_change = (basal_adjustment / median_sched_basal) * 100
        recommended_basal = median_sched_basal + basal_adjustment
    else:
        basal_pct_change = np.nan
        recommended_basal = np.nan

    # TDD estimation  (basal ≈ 50 % TDD)
    approx_tdd = median_sched_basal * 24 * 2 if median_sched_basal > 0 else np.nan
    if (
        np.isfinite(approx_tdd)
        and approx_tdd > 0
        and np.isfinite(basal_adjustment)
    ):
        tdd_change_pct = abs(basal_adjustment * 24 / approx_tdd * 100)
    else:
        tdd_change_pct = np.nan

    return {
        "patient_id": pid,
        "controller": controller,
        "n_total_obs": int(len(pdf)),
        "n_fasting_obs": int(len(fdf)),
        "fasting_pct": round(float(len(fdf) / len(pdf) * 100), 2),
        # raw drift
        "raw_drift_mean": safe_float(raw_mean),
        "raw_drift_median": safe_float(raw_median),
        "raw_drift_std": safe_float(raw_std),
        "raw_drift_abs_mean": safe_float(raw_abs_mean),
        "raw_drift_var": safe_float(raw_var),
        # adjusted drift
        "adj_drift_mean": safe_float(adj_mean),
        "adj_drift_median": safe_float(adj_median),
        "adj_drift_std": safe_float(adj_std),
        "adj_drift_abs_mean": safe_float(adj_abs_mean),
        "adj_drift_var": safe_float(adj_var),
        # variance reduction
        "var_reduction_pct": safe_float(var_reduction_pct),
        # regression diagnostics
        "reg_intercept": safe_float(reg_intercept),
        "reg_excess_basal_coeff": safe_float(reg_excess_basal_coeff),
        "reg_smb_coeff": safe_float(reg_smb_coeff),
        "controller_r2": safe_float(controller_r2),
        # EGP
        "egp_median": safe_float(egp_median),
        "egp_mean": safe_float(egp_mean),
        "egp_std": safe_float(egp_std),
        "egp_ci_lo": safe_float(egp_ci_lo),
        "egp_ci_hi": safe_float(egp_ci_hi),
        # circadian
        "circadian_egp": circadian_egp,
        "circadian_amplitude": safe_float(circadian_amplitude),
        "circadian_range": safe_float(circadian_range),
        "dawn_drift": safe_float(dawn_drift),
        "nadir_drift": safe_float(nadir_drift),
        "kw_stat": safe_float(kw_stat),
        "kw_p": safe_float(kw_p),
        "hourly_drift": {str(k): v for k, v in hourly_drift.items()},
        "hourly_egp": {str(k): v for k, v in hourly_egp.items()},
        "hourly_adj_drift": {str(k): v for k, v in hourly_adj_drift.items()},
        # basal recommendation
        "median_isf": safe_float(median_isf),
        "median_sched_basal": safe_float(median_sched_basal),
        "basal_adjustment": safe_float(basal_adjustment),
        "recommended_basal": safe_float(recommended_basal),
        "basal_pct_change": safe_float(basal_pct_change),
        "tdd_change_pct": safe_float(tdd_change_pct),
    }


# ── Step 4: Run All Patients ─────────────────────────────────────────

def run_analysis(grid: pd.DataFrame, qualified: List[str]) -> List[Dict]:
    """Run per-patient basal-EGP equilibrium analysis."""
    print(f"\n{'=' * 70}")
    print("STEP 1-3: Per-Patient Basal-EGP Equilibrium Analysis")
    print(f"{'=' * 70}")

    results: List[Dict] = []
    for i, pid in enumerate(sorted(qualified)):
        pdf = grid[grid["patient_id"] == pid]
        if len(pdf) == 0:
            continue

        result = analyze_patient(pdf, pid)
        if result is not None:
            results.append(result)
            vr = result["var_reduction_pct"]
            vr_str = f"{vr:+.1f}%" if vr is not None else "  N/A"
            print(
                f"  [{i + 1:2d}/{len(qualified)}] {pid[:8]:>8s}: "
                f"n_fast={result['n_fasting_obs']:5d}, "
                f"raw={result['raw_drift_mean']:+.3f}, "
                f"adj={result['adj_drift_mean']:+.3f}, "
                f"EGP={result['egp_median']:.3f}, "
                f"var_red={vr_str}"
            )
        else:
            print(
                f"  [{i + 1:2d}/{len(qualified)}] {pid[:8]:>8s}: "
                f"SKIPPED (insufficient fasting data)"
            )

    print(f"\n  Analysed {len(results)}/{len(qualified)} patients")
    return results


# ── Step 5: Population Summaries & EXP-2739 Comparison ────────────────

def compute_population_summaries(
    results: List[Dict], exp2739: Optional[Dict]
) -> Dict:
    """Compute population-level statistics and cross-validate with EXP-2739."""
    print(f"\n{'=' * 70}")
    print("STEP 4: Population Summaries & EXP-2739 Comparison")
    print(f"{'=' * 70}")

    raw_means = [r["raw_drift_mean"] for r in results if r["raw_drift_mean"] is not None]
    adj_means = [r["adj_drift_mean"] for r in results if r["adj_drift_mean"] is not None]
    raw_abs = [r["raw_drift_abs_mean"] for r in results if r["raw_drift_abs_mean"] is not None]
    adj_abs = [r["adj_drift_abs_mean"] for r in results if r["adj_drift_abs_mean"] is not None]
    egp_medians = [r["egp_median"] for r in results if r["egp_median"] is not None]
    var_reds = [r["var_reduction_pct"] for r in results if r["var_reduction_pct"] is not None]
    circ_amps = [
        r["circadian_amplitude"]
        for r in results
        if r["circadian_amplitude"] is not None
    ]
    circ_ranges = [
        r["circadian_range"]
        for r in results
        if r["circadian_range"] is not None
    ]
    tdd_changes = [
        r["tdd_change_pct"]
        for r in results
        if r["tdd_change_pct"] is not None
    ]
    basal_pcts = [
        r["basal_pct_change"]
        for r in results
        if r["basal_pct_change"] is not None
    ]

    print(f"\n  Drift: raw_median={safe_median(raw_means):.4f}, "
          f"adj_median={safe_median(adj_means):.4f}")
    print(f"  EGP median across patients: {safe_median(egp_medians):.3f}")
    print(f"  Variance reduction: median={safe_median(var_reds):.1f}%")
    print(f"  Circadian range: median={safe_median(circ_ranges):.3f}")

    # EXP-2739 comparison
    egp_comparison: List[Dict] = []
    if exp2739:
        for r in results:
            pid = r["patient_id"]
            if pid in exp2739 and r["egp_median"] is not None:
                ref = exp2739[pid]["egp_median"]
                this = r["egp_median"]
                if ref is not None and abs(ref) > 1e-6:
                    pct_diff = abs(this - ref) / abs(ref) * 100
                    egp_comparison.append(
                        {
                            "patient_id": pid,
                            "exp2739_egp": ref,
                            "exp2740_egp": this,
                            "pct_diff": round(pct_diff, 2),
                        }
                    )
        if egp_comparison:
            pct_diffs = [c["pct_diff"] for c in egp_comparison]
            print(f"\n  EXP-2739 comparison: {len(egp_comparison)} patients matched")
            print(f"  Median EGP difference: {safe_median(pct_diffs):.1f}%")
            print(
                f"  Within 30%: "
                f"{sum(1 for d in pct_diffs if d < 30)}/{len(pct_diffs)}"
            )

    return {
        "n_patients": len(results),
        "raw_drift_median": safe_float(safe_median(raw_means)),
        "adj_drift_median": safe_float(safe_median(adj_means)),
        "raw_abs_drift_median": safe_float(safe_median(raw_abs)),
        "adj_abs_drift_median": safe_float(safe_median(adj_abs)),
        "egp_median_across": safe_float(safe_median(egp_medians)),
        "egp_std_across": safe_float(safe_std(egp_medians)),
        "egp_range": (
            [safe_float(min(egp_medians)), safe_float(max(egp_medians))]
            if egp_medians
            else None
        ),
        "var_reduction_median": safe_float(safe_median(var_reds)),
        "circadian_amplitude_median": safe_float(safe_median(circ_amps)),
        "circadian_range_median": safe_float(safe_median(circ_ranges)),
        "tdd_change_median": safe_float(safe_median(tdd_changes)),
        "basal_pct_change_median": safe_float(safe_median(basal_pcts)),
        "egp_comparison": egp_comparison,
    }


# ── Step 6: Hypothesis Evaluation ────────────────────────────────────

def evaluate_hypotheses(
    results: List[Dict], summary: Dict, exp2739: Optional[Dict]
) -> Dict:
    """Evaluate all five hypotheses."""
    print(f"\n{'=' * 70}")
    print("STEP 5: Hypothesis Evaluation")
    print(f"{'=' * 70}")

    hypotheses: Dict[str, Dict] = {}

    # ── H1: |adjusted drift| < 0.5 for > 50 % of patients ──
    abs_drifts = [
        abs(r["adj_drift_mean"])
        for r in results
        if r["adj_drift_mean"] is not None
    ]
    n_well = sum(1 for d in abs_drifts if d < 0.5)
    h1_frac = n_well / len(abs_drifts) if abs_drifts else 0
    h1_pass = bool(h1_frac > 0.50)
    hypotheses["H1_drift_magnitude"] = {
        "passed": h1_pass,
        "description": (
            "Fasting drift <0.5 mg/dL/5min for >50% of patients"
        ),
        "n_well_matched": n_well,
        "n_total": len(abs_drifts),
        "fraction": safe_float(h1_frac),
        "threshold": 0.50,
        "detail": (
            f"{n_well}/{len(abs_drifts)} ({h1_frac * 100:.1f}%) patients "
            f"have |drift| < 0.5 mg/dL/5min (threshold: >50%)"
        ),
    }
    print(f"\n  H1: {h1_frac * 100:.1f}% well-matched → "
          f"{'PASS' if h1_pass else 'FAIL'}")

    # ── H2: EGP matches EXP-2739 within 30 % ──
    comparison = summary.get("egp_comparison", [])
    if comparison:
        pct_diffs = [c["pct_diff"] for c in comparison]
        n_within = sum(1 for d in pct_diffs if d < 30)
        h2_frac = n_within / len(pct_diffs) if pct_diffs else 0
        h2_pass = bool(h2_frac > 0.50)
        med_diff = safe_median(pct_diffs)
        hypotheses["H2_egp_consistency"] = {
            "passed": h2_pass,
            "description": "EGP estimates match EXP-2739 within 30%",
            "n_within_30pct": n_within,
            "n_compared": len(pct_diffs),
            "fraction_within": safe_float(h2_frac),
            "median_pct_diff": safe_float(med_diff),
            "detail": (
                f"{n_within}/{len(pct_diffs)} patients within 30% of EXP-2739 "
                f"(median diff: {med_diff:.1f}%)"
            ),
        }
        print(f"  H2: {n_within}/{len(pct_diffs)} within 30% → "
              f"{'PASS' if h2_pass else 'FAIL'}")
    else:
        hypotheses["H2_egp_consistency"] = {
            "passed": False,
            "description": "EGP estimates match EXP-2739 within 30%",
            "detail": "EXP-2739 results not available for comparison",
        }
        print("  H2: EXP-2739 not available → FAIL (no data)")

    # ── H3: Circadian range > 1 mg/dL/5min in > 50 % of patients ──
    circ_ranges = [
        r["circadian_range"]
        for r in results
        if r["circadian_range"] is not None
    ]
    n_sig = sum(1 for c in circ_ranges if c > 1.0)
    h3_frac = n_sig / len(circ_ranges) if circ_ranges else 0
    h3_pass = bool(h3_frac > 0.50)
    hypotheses["H3_circadian_mismatch"] = {
        "passed": h3_pass,
        "description": (
            "Circadian mismatch >1 mg/dL/5min in >50% of patients"
        ),
        "n_significant": n_sig,
        "n_total": len(circ_ranges),
        "fraction": safe_float(h3_frac),
        "median_range": safe_float(safe_median(circ_ranges)),
        "detail": (
            f"{n_sig}/{len(circ_ranges)} ({h3_frac * 100:.1f}%) patients "
            f"have circadian range >1.0 (threshold: >50%)"
        ),
    }
    print(f"  H3: {h3_frac * 100:.1f}% with circadian >1.0 → "
          f"{'PASS' if h3_pass else 'FAIL'}")

    # ── H4: multi-factor subtraction reduces variance by > 20 % ──
    var_reds = [
        r["var_reduction_pct"]
        for r in results
        if r["var_reduction_pct"] is not None
    ]
    med_red = safe_median(var_reds)
    n_above = sum(1 for v in var_reds if v > 20)
    h4_pass = bool(np.isfinite(med_red) and med_red > 20)
    hypotheses["H4_variance_reduction"] = {
        "passed": h4_pass,
        "description": (
            "Multi-factor subtraction reduces variance by >20%"
        ),
        "median_reduction_pct": safe_float(med_red),
        "n_above_20pct": n_above,
        "n_total": len(var_reds),
        "detail": (
            f"Median variance reduction: {med_red:.1f}% "
            f"({n_above}/{len(var_reds)} above 20%, threshold: median >20%)"
        ),
    }
    print(f"  H4: Median var reduction {med_red:.1f}% → "
          f"{'PASS' if h4_pass else 'FAIL'}")

    # ── H5: < 30 % TDD change for > 80 % of patients ──
    tdd_changes = [
        r["tdd_change_pct"]
        for r in results
        if r["tdd_change_pct"] is not None
    ]
    n_cons = sum(1 for t in tdd_changes if t < 30)
    h5_frac = n_cons / len(tdd_changes) if tdd_changes else 0
    h5_pass = bool(h5_frac > 0.80)
    hypotheses["H5_conservative_recommendation"] = {
        "passed": h5_pass,
        "description": (
            "Basal recommendation <30% TDD change for >80% of patients"
        ),
        "n_conservative": n_cons,
        "n_total": len(tdd_changes),
        "fraction": safe_float(h5_frac),
        "median_tdd_change": safe_float(safe_median(tdd_changes)),
        "detail": (
            f"{n_cons}/{len(tdd_changes)} ({h5_frac * 100:.1f}%) patients "
            f"need <30% TDD change (threshold: >80%)"
        ),
    }
    print(f"  H5: {h5_frac * 100:.1f}% conservative → "
          f"{'PASS' if h5_pass else 'FAIL'}")

    return hypotheses


# ── Step 7: Visualization (2 × 3 panel) ──────────────────────────────

def create_visualizations(results: List[Dict], summary: Dict) -> str:
    """Create 2×3 panel figure for the basal-EGP equilibrium analysis."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Colour palette
    C_RAW = "#E53935"
    C_ADJ = "#43A047"
    C_EGP = "#FF9800"
    C_LOOP = "#2196F3"
    C_TRIO = "#9C27B0"
    C_UNK = "#757575"
    C_REF = "#607D8B"

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(
        f"EXP-{EXP_ID}: {TITLE}",
        fontsize=14, fontweight="bold", y=0.98,
    )

    sorted_r = sorted(results, key=lambda r: r["raw_drift_mean"] or 0)
    pids_short = [r["patient_id"][:6] for r in sorted_r]

    # ── A: Per-patient fasting drift (raw vs adjusted) ───────────
    ax = axes[0, 0]
    raw_box_data = []
    adj_box_data = []
    for r in sorted_r:
        raw_box_data.append(r["raw_drift_mean"] or 0)
        adj_box_data.append(r["adj_drift_mean"] or 0)

    x = np.arange(len(sorted_r))
    w = 0.35
    ax.bar(x - w / 2, raw_box_data, w, color=C_RAW, alpha=0.7, label="Raw drift")
    ax.bar(x + w / 2, adj_box_data, w, color=C_ADJ, alpha=0.7, label="After subtraction")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.axhline(0.5, color=C_REF, lw=1, ls="--", alpha=0.5, label="±0.5 threshold")
    ax.axhline(-0.5, color=C_REF, lw=1, ls="--", alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(pids_short, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Mean drift (mg/dL per 5 min)")
    ax.set_title("A: Raw vs Adjusted Fasting Drift")
    ax.legend(fontsize=7, loc="upper left")

    # ── B: EGP consistency with EXP-2739 ─────────────────────────
    ax = axes[0, 1]
    comparison = summary.get("egp_comparison", [])
    if comparison:
        ref_vals = [c["exp2739_egp"] for c in comparison]
        this_vals = [c["exp2740_egp"] for c in comparison]
        ax.scatter(
            ref_vals, this_vals,
            c=C_EGP, s=50, alpha=0.7, edgecolors="black", linewidth=0.5,
        )
        all_v = ref_vals + this_vals
        vmin, vmax = min(all_v), max(all_v)
        margin = (vmax - vmin) * 0.15 if vmax > vmin else 1.0
        lims = [vmin - margin, vmax + margin]
        ax.plot(lims, lims, "k--", lw=1, alpha=0.5, label="y = x")
        xs = np.linspace(lims[0], lims[1], 100)
        ax.fill_between(xs, xs * 0.7, xs * 1.3, alpha=0.1, color=C_EGP, label="±30%")
        if (
            len(ref_vals) >= 3
            and np.std(ref_vals) > 1e-6
            and np.std(this_vals) > 1e-6
        ):
            slope, intercept, r_val, p_val, _ = stats.linregress(ref_vals, this_vals)
            ax.plot(xs, slope * xs + intercept, color=C_EGP, lw=1.5, alpha=0.7)
            ax.text(
                0.05, 0.95,
                f"r = {r_val:.3f}, p = {p_val:.3g}",
                transform=ax.transAxes, fontsize=8, va="top",
            )
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.legend(fontsize=7)
    else:
        ax.text(
            0.5, 0.5, "EXP-2739 data\nnot available",
            transform=ax.transAxes, ha="center", va="center", fontsize=12,
        )
    ax.set_xlabel("EXP-2739 EGP (mg/dL per 5 min)")
    ax.set_ylabel("EXP-2740 EGP (mg/dL per 5 min)")
    ax.set_title("B: EGP Consistency (vs EXP-2739)")

    # ── C: Circadian drift pattern (mean ± SD across patients) ───
    ax = axes[0, 2]
    all_hourly: Dict[int, List[float]] = {h: [] for h in range(24)}
    for r in results:
        for h_str, vals in r.get("hourly_drift", {}).items():
            all_hourly[int(h_str)].append(vals["median"])

    hrs_plot = list(range(24))
    means_c = [
        np.mean(all_hourly[h]) if all_hourly[h] else np.nan for h in hrs_plot
    ]
    stds_c = [
        np.std(all_hourly[h]) if len(all_hourly[h]) > 1 else 0
        for h in hrs_plot
    ]
    valid = [
        (h, m, s) for h, m, s in zip(hrs_plot, means_c, stds_c) if np.isfinite(m)
    ]
    if valid:
        vh, vm, vs_ = zip(*valid)
        vm_a, vs_a = np.array(vm), np.array(vs_)
        ax.plot(vh, vm_a, "o-", color=C_RAW, lw=2, ms=4, label="Mean drift")
        ax.fill_between(vh, vm_a - vs_a, vm_a + vs_a, alpha=0.2, color=C_RAW)
        for h in DAWN_HOURS:
            ax.axvspan(h - 0.5, h + 0.5, alpha=0.1, color="red")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Drift (mg/dL per 5 min)")
    ax.set_title("C: Circadian Drift Pattern")
    ax.set_xticks([0, 4, 8, 12, 16, 20])
    ax.legend(fontsize=7)

    # ── D: Variance reduction bar chart ──────────────────────────
    ax = axes[1, 0]
    vr_data = [(r["patient_id"][:6], r["var_reduction_pct"] or 0) for r in sorted_r]
    labs4, vals4 = zip(*vr_data) if vr_data else ([], [])
    colors4 = [C_ADJ if v > 20 else C_RAW for v in vals4]
    ax.bar(range(len(vals4)), vals4, color=colors4, alpha=0.7)
    ax.axhline(20, color=C_REF, lw=1.5, ls="--", label="20% threshold")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(range(len(labs4)))
    ax.set_xticklabels(labs4, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Variance reduction (%)")
    ax.set_title("D: Multi-Factor Subtraction Effect")
    ax.legend(fontsize=7)

    # ── E: Basal recommendation magnitude (histogram) ────────────
    ax = axes[1, 1]
    tdd_vals = [
        r["tdd_change_pct"]
        for r in results
        if r["tdd_change_pct"] is not None
    ]
    if tdd_vals:
        upper = max(tdd_vals) + 5
        bins = np.arange(0, upper, 5)
        if len(bins) < 2:
            bins = np.array([0, 5, 10])
        ax.hist(tdd_vals, bins=bins, color=C_ADJ, alpha=0.7, edgecolor="black")
        ax.axvline(30, color=C_RAW, lw=2, ls="--", label="30% TDD threshold")
        n_below = sum(1 for t in tdd_vals if t < 30)
        ax.text(
            0.95, 0.95,
            f"{n_below}/{len(tdd_vals)} < 30%",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
        )
    ax.set_xlabel("% TDD change needed")
    ax.set_ylabel("Number of patients")
    ax.set_title("E: Basal Recommendation Magnitude")
    ax.legend(fontsize=7)

    # ── F: Patient equilibrium summary (sorted, coloured by ctrl) ─
    ax = axes[1, 2]
    sorted_by_adj = sorted(results, key=lambda r: r["adj_drift_mean"] or 0)
    pids6 = [r["patient_id"][:6] for r in sorted_by_adj]
    drifts6 = [r["adj_drift_mean"] or 0 for r in sorted_by_adj]
    colors6 = []
    for r in sorted_by_adj:
        ctrl = r.get("controller", "unknown")
        if ctrl == "loop":
            colors6.append(C_LOOP)
        elif ctrl == "trio":
            colors6.append(C_TRIO)
        else:
            colors6.append(C_UNK)

    ax.barh(
        range(len(drifts6)), drifts6,
        color=colors6, alpha=0.7, edgecolor="black", linewidth=0.3,
    )
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(0.5, color=C_REF, lw=1, ls="--", alpha=0.5)
    ax.axvline(-0.5, color=C_REF, lw=1, ls="--", alpha=0.5)
    ax.set_yticks(range(len(pids6)))
    ax.set_yticklabels(pids6, fontsize=7)
    ax.set_xlabel("Adjusted drift (mg/dL per 5 min)")
    ax.set_title("F: Equilibrium Summary by Controller")
    legend_el = [
        Patch(facecolor=C_LOOP, alpha=0.7, label="Loop"),
        Patch(facecolor=C_TRIO, alpha=0.7, label="Trio"),
        Patch(facecolor=C_UNK, alpha=0.7, label="Unknown"),
    ]
    ax.legend(handles=legend_el, fontsize=7, loc="lower right")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = VIZ_DIR / "basal_egp_equilibrium.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Visualization saved to {out_path}")
    return str(out_path)


# ── Step 8: Output Assembly ──────────────────────────────────────────

def assemble_output(
    results: List[Dict],
    summary: Dict,
    hypotheses: Dict,
    viz_path: str,
) -> Dict:
    """Assemble complete experiment output JSON.

    CRITICAL: exports per_patient_egp dict keyed by patient_id for
    downstream use by EXP-2741 and EXP-2742.
    """
    # Build per_patient_egp (required by EXP-2741/2742)
    per_patient_egp: Dict[str, Dict] = {}
    for r in results:
        pid = r["patient_id"]
        per_patient_egp[pid] = {
            "median_egp": r["egp_median"],
            "circadian_egp": r["circadian_egp"],
            "mean_residual": r["adj_drift_mean"],
            "residual_std": r["adj_drift_std"],
        }

    n_pass = sum(
        1 for h in hypotheses.values() if bool(h.get("passed", False))
    )

    # Guard against None in summary values for the f-string
    s_raw = summary.get("raw_drift_median")
    s_adj = summary.get("adj_drift_median")
    s_egp = summary.get("egp_median_across")
    s_vr = summary.get("var_reduction_median")
    s_tdd = summary.get("tdd_change_median")

    output = {
        "exp_id": EXP_ID,
        "title": TITLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": (
            f"EXP-{EXP_ID}: {TITLE}. "
            f"{n_pass}/5 hypotheses passed. "
            f"Analysed {len(results)} patients. "
            + (f"Median raw fasting drift: {s_raw:.4f} mg/dL/5min. "
               if s_raw is not None else "")
            + (f"Median adjusted drift: {s_adj:.4f} mg/dL/5min. "
               if s_adj is not None else "")
            + (f"Median EGP: {s_egp:.3f}. "
               if s_egp is not None else "")
            + (f"Median variance reduction: {s_vr:.1f}%. "
               if s_vr is not None else "")
            + (f"Median TDD change: {s_tdd:.1f}%."
               if s_tdd is not None else "")
        ),
        "parameters": {
            "fasting_carb_lookback_steps": FASTING_CARB_LOOKBACK,
            "fasting_carb_lookahead_steps": FASTING_CARB_LOOKAHEAD,
            "fasting_bolus_lookback_steps": FASTING_BOLUS_LOOKBACK,
            "cob_threshold_g": COB_THRESHOLD,
            "min_fasting_obs": MIN_FASTING_OBS,
            "egp_floor": EGP_FLOOR,
            "egp_ceil": EGP_CEIL,
            "drift_floor": DRIFT_FLOOR,
            "drift_ceil": DRIFT_CEIL,
            "dawn_hours": DAWN_HOURS,
            "nadir_hours": NADIR_HOURS,
            "n_bootstrap": N_BOOTSTRAP,
            "min_hourly_obs": MIN_HOURLY_OBS,
            "pop_egp_fraction": POP_EGP_FRACTION,
        },
        "population_summary": summary,
        "hypotheses": hypotheses,
        "per_patient_results": results,
        "per_patient_egp": per_patient_egp,
        "visualization": viz_path,
    }

    return sanitize_for_json(output)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 70}")
    print(f"# EXP-{EXP_ID}: {TITLE}")
    print(f"{'#' * 70}")

    # Load data
    grid, qualified = load_data()
    exp2739 = load_exp2739()

    # Per-patient analysis
    results = run_analysis(grid, qualified)
    if not results:
        print("\nERROR: No patients analysed successfully. Aborting.")
        sys.exit(1)

    # Population summaries
    summary = compute_population_summaries(results, exp2739)

    # Hypotheses
    hypotheses = evaluate_hypotheses(results, summary, exp2739)

    # Visualization
    print(f"\n{'=' * 70}")
    print("CREATING VISUALIZATIONS")
    print(f"{'=' * 70}")
    viz_path = create_visualizations(results, summary)

    # Assemble & save
    output = assemble_output(results, summary, hypotheses, viz_path)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {OUT_JSON}")

    # ── Final Summary ────────────────────────────────────────────
    print(f"\n{'#' * 70}")
    print(f"# EXP-{EXP_ID} FINAL SUMMARY")
    print(f"{'#' * 70}")
    print(f"\nPatients analysed: {len(results)}")

    s = summary
    for label, key in [
        ("Median raw drift", "raw_drift_median"),
        ("Median adjusted drift", "adj_drift_median"),
        ("Median EGP", "egp_median_across"),
        ("Median variance reduction", "var_reduction_median"),
        ("Median circadian range", "circadian_range_median"),
        ("Median TDD change", "tdd_change_median"),
    ]:
        val = s.get(key)
        if val is not None:
            print(f"  {label}: {val:.4f}")

    n_pass = sum(
        1 for h in hypotheses.values() if bool(h.get("passed", False))
    )
    print(f"\nHYPOTHESIS VERDICTS ({n_pass}/5 passed):")
    for key, val in hypotheses.items():
        status = "✓ PASS" if bool(val.get("passed", False)) else "✗ FAIL"
        print(f"  {status}  {key}")
        print(f"         {val.get('detail', '')}")

    print(f"\nPer-patient EGP export: {len(output['per_patient_egp'])} patients")
    print("  (Available for EXP-2741 and EXP-2742)")

    print(f"\nOutputs:")
    print(f"  JSON:   {OUT_JSON}")
    print(f"  Viz:    {viz_path}")
    print(f"  Script: tools/cgmencode/exp_basal_egp_equilibrium_2740.py")

    return output


if __name__ == "__main__":
    main()
