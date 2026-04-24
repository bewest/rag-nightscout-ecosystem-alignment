#!/usr/bin/env python3
"""EXP-2739: Per-Patient EGP Profiling & Precision.

Does endogenous glucose production (EGP) vary significantly across patients
and time-of-day?  Can per-patient EGP estimation improve the precision of
ISF / CR / basal extraction?

Predecessors
------------
- EXP-2735  EGP accounts for 92 % of fasting glucose drift (population EGP)
- EXP-2731  EGP-aware BGI reduces deviation variance
- EXP-2735b EGP-aware basal gives more conservative recs (19.5/100 calibration)
- EXP-2724  Glucose drift has circadian structure (KW p<1e-38)

Scientific Question
-------------------
EXP-2735 used a POPULATION-LEVEL EGP estimate (1.5-2.5 mg/dL/5min).
If EGP varies by patient (higher in insulin-resistant, lower in tight-control)
and by time-of-day (dawn phenomenon), then per-patient EGP could improve:
  1. Basal rate extraction (currently 19.5/100 calibration score)
  2. ISF extraction (EGP is 1.93× of the 10× ISF gap)
  3. CR extraction (EGP during meals confounds carb absorption)

HYPOTHESES
----------
  H1: EGP varies >2× across patients (max/min patient median EGP ratio > 2.0)
  H2: EGP has significant circadian pattern (dawn>nadir ratio > 1.5 in ≥50 %)
  H3: Per-patient EGP improves ISF extraction precision (>15 % narrower 95 % CI)
  H4: Per-patient EGP improves basal calibration score (>25/100 vs 19.5)
  H5: High-EGP-variability patients have worse settings (r > 0.3)
"""

from __future__ import annotations

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
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Constants ────────────────────────────────────────────────────────────────

EXP_ID = "2739"
TITLE = "Per-Patient EGP Profiling & Precision"

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_egp_personalization.json"
VIZ_DIR = Path("visualizations/egp-personalization")

# Fasting window parameters (5-min steps)
FASTING_CARB_WINDOW = 48     # 4 h no carbs
FASTING_BOLUS_WINDOW = 24    # 2 h no manual bolus
MIN_FASTING_OBS = 50         # minimum fasting observations per patient

# EGP outlier bounds (mg/dL per 5-min)
EGP_FLOOR = -5.0
EGP_CEIL = 10.0

# Population EGP baseline (mg/dL per 5-min step)
POP_EGP = 1.5

# Time blocks for circadian analysis
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

# Dawn window: 04-08, nadir window: 22-02 (mapped to hours)
DAWN_HOURS = list(range(4, 8))
NADIR_HOURS = [22, 23, 0, 1]

# ISF extraction parameters
ISF_MIN_BG = 150             # starting BG for correction events
ISF_POST_WINDOW = 24         # 2 h observation window (steps)
ISF_MIN_DOSE = 0.3           # minimum insulin (U)
ISF_MAX_CARBS = 3.0          # max carbs in observation window
ISF_INDEPENDENCE_GAP = 24    # 2 h gap between events

# Basal optimization parameters
DRIFT_HORIZON = 12           # 1 h (steps) for fasting drift
BASAL_CLIP_LO = 0.05
BASAL_CLIP_HI = 5.0

# Bootstrap parameters
N_BOOTSTRAP = 500
BOOTSTRAP_SEED = 2739

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


# ── Helpers ──────────────────────────────────────────────────────────────────

def safe_median(arr):
    """Median that returns NaN for empty arrays."""
    if len(arr) == 0:
        return np.nan
    return float(np.nanmedian(arr))


def safe_iqr(arr):
    """IQR that returns NaN for empty arrays."""
    if len(arr) < 4:
        return np.nan
    return float(np.nanpercentile(arr, 75) - np.nanpercentile(arr, 25))


def safe_cv(arr):
    """Coefficient of variation, guarded against zero mean."""
    arr = np.array(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return np.nan
    m = np.nanmean(arr)
    if abs(m) < 1e-6:
        return np.nan
    return float(np.nanstd(arr) / abs(m))


def bootstrap_ci(arr, n_boot=N_BOOTSTRAP, ci=0.95, seed=BOOTSTRAP_SEED):
    """Bootstrap 95 % CI for the median."""
    arr = np.array(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 5:
        return (np.nan, np.nan, np.nan)
    rng = np.random.RandomState(seed)
    medians = np.array([
        np.median(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    alpha = (1 - ci) / 2
    lo, hi = np.percentile(medians, [100 * alpha, 100 * (1 - alpha)])
    return (float(lo), float(np.median(medians)), float(hi))


def hour_of_day(time_series: pd.Series) -> np.ndarray:
    """Extract hour-of-day from datetime series, handling timezone-aware."""
    ts = pd.to_datetime(time_series)
    return ts.dt.hour.values.astype(float)


# ── Part 0: Load Data ───────────────────────────────────────────────────────

def load_data() -> Tuple[pd.DataFrame, List[str]]:
    """Load grid parquet and qualified patient list."""
    print(f"[EXP-{EXP_ID}] Loading data...")
    grid = pd.read_parquet(GRID)
    manifest = json.load(open(MANIFEST))
    qualified = manifest["qualified_patients"]
    grid = grid[grid["patient_id"].isin(qualified)].copy()
    print(f"  {len(grid):,} rows, {len(qualified)} patients")
    return grid, qualified


# ── Part 1: Per-Patient EGP Profiling ────────────────────────────────────────

def identify_fasting_mask(
    pdf: pd.DataFrame,
    patient_id: Optional[str] = None,
    *,
    use_inferred_meals: bool = True,
) -> np.ndarray:
    """Return boolean mask of fasting 5-min intervals for one patient.

    Fasting = rolling sum of carbs over 4 h == 0
              AND rolling sum of manual bolus over 2 h == 0.

    When `use_inferred_meals` is True and `patient_id` is provided, the
    mask additionally excludes the [-2h, +4h] window around each inferred
    meal (production residual+insulin detector) — protects EGP estimates
    from under-loggers whose logged carbs are unreliable.
    """
    n = len(pdf)
    carbs = pdf["carbs"].fillna(0).values.astype(float)
    bolus = pdf["bolus"].fillna(0).values.astype(float)

    # Rolling sums (backwards-looking)
    carb_roll = np.zeros(n, dtype=float)
    bolus_roll = np.zeros(n, dtype=float)
    for i in range(n):
        c_start = max(0, i - FASTING_CARB_WINDOW + 1)
        b_start = max(0, i - FASTING_BOLUS_WINDOW + 1)
        carb_roll[i] = np.nansum(carbs[c_start:i + 1])
        bolus_roll[i] = np.nansum(bolus[b_start:i + 1])

    mask = (carb_roll < 0.5) & (bolus_roll < 0.1)
    # Also require valid glucose_roc and insulin_activity
    roc_valid = np.isfinite(pdf["glucose_roc"].values)
    ia_valid = np.isfinite(pdf["insulin_activity"].values)
    isf_valid = np.isfinite(pdf["scheduled_isf"].values)
    gluc_valid = np.isfinite(pdf["glucose"].values)

    mask = mask & roc_valid & ia_valid & isf_valid & gluc_valid

    if use_inferred_meals and patient_id is not None:
        try:
            from cgmencode.production.fasting_helpers import (
                apply_inferred_meal_exclusion,
            )
            mask = apply_inferred_meal_exclusion(mask, pdf, patient_id)
        except Exception:
            pass  # fall back to logged-only mask

    return mask


def compute_egp_observations(pdf: pd.DataFrame, fasting_mask: np.ndarray) -> pd.DataFrame:
    """Compute observed EGP at each fasting 5-min step.

    EGP_obs = glucose_roc + insulin_activity * scheduled_isf
    (glucose_roc = EGP - |BGI| + noise;
     BGI = -insulin_activity * ISF;
     so EGP = glucose_roc + insulin_activity * ISF)

    Note: insulin_activity is positive when insulin is active, and
    BGI = -insulin_activity * ISF is the glucose-lowering effect.
    So observed glucose_roc ≈ EGP + BGI = EGP - insulin_activity * ISF
    Therefore: EGP ≈ glucose_roc + insulin_activity * ISF
    """
    roc = pdf["glucose_roc"].values
    ia = pdf["insulin_activity"].values
    isf = pdf["scheduled_isf"].values
    hours = hour_of_day(pdf["time"])

    # Compute EGP at fasting points
    # ia is insulin activity; BGI (glucose lowering) = -ia * isf per time unit
    # The sign convention: ia > 0 means insulin is active, lowering glucose
    # glucose_roc = EGP - ia * isf (approximately)
    # So: EGP = glucose_roc + ia * isf
    egp_obs = roc + ia * isf

    result = pd.DataFrame({
        "egp_obs": egp_obs,
        "glucose_roc": roc,
        "insulin_activity": ia,
        "scheduled_isf": isf,
        "glucose": pdf["glucose"].values,
        "iob": pdf["iob"].values if "iob" in pdf.columns else np.nan,
        "hour": hours,
        "fasting": fasting_mask,
    })
    # Filter to fasting only
    result = result[fasting_mask].copy()
    # Remove outliers
    result = result[
        (result["egp_obs"] >= EGP_FLOOR) & (result["egp_obs"] <= EGP_CEIL)
    ].copy()
    return result


def profile_patient_egp(pdf: pd.DataFrame, patient_id: str) -> Optional[Dict[str, Any]]:
    """Compute EGP profile for a single patient."""
    fasting_mask = identify_fasting_mask(pdf, patient_id)
    n_fasting = int(np.sum(fasting_mask))

    if n_fasting < MIN_FASTING_OBS:
        print(f"    {patient_id}: only {n_fasting} fasting obs, skipping")
        return None

    egp_df = compute_egp_observations(pdf, fasting_mask)
    if len(egp_df) < MIN_FASTING_OBS:
        print(f"    {patient_id}: only {len(egp_df)} valid EGP obs after filtering")
        return None

    egp_vals = egp_df["egp_obs"].values

    # Overall statistics
    med = float(np.nanmedian(egp_vals))
    mean = float(np.nanmean(egp_vals))
    std = float(np.nanstd(egp_vals))
    iqr = safe_iqr(egp_vals)
    cv = safe_cv(egp_vals)
    ci_lo, ci_med, ci_hi = bootstrap_ci(egp_vals)
    ci_width = ci_hi - ci_lo if np.isfinite(ci_hi) and np.isfinite(ci_lo) else np.nan

    # Circadian pattern: bin by hour
    hourly_egp = {}
    for h in range(24):
        mask_h = (egp_df["hour"] >= h) & (egp_df["hour"] < h + 1)
        vals_h = egp_df.loc[mask_h, "egp_obs"].values
        hourly_egp[h] = {
            "median": safe_median(vals_h),
            "mean": float(np.nanmean(vals_h)) if len(vals_h) > 0 else np.nan,
            "n": int(len(vals_h)),
        }

    # Dawn phenomenon: peak in 4-8 AM vs nadir in 22-02
    dawn_vals = egp_df.loc[egp_df["hour"].isin(DAWN_HOURS), "egp_obs"].values
    nadir_vals = egp_df.loc[egp_df["hour"].isin(NADIR_HOURS), "egp_obs"].values
    dawn_med = safe_median(dawn_vals)
    nadir_med = safe_median(nadir_vals)
    dawn_ratio = dawn_med / nadir_med if (np.isfinite(nadir_med) and abs(nadir_med) > 0.01) else np.nan

    # EGP by 4-hour blocks
    block_egp = {}
    for (blo, bhi), label in zip(TIME_BLOCKS, BLOCK_LABELS):
        mask_b = (egp_df["hour"] >= blo) & (egp_df["hour"] < bhi)
        vals_b = egp_df.loc[mask_b, "egp_obs"].values
        block_egp[label] = {
            "median": safe_median(vals_b),
            "mean": float(np.nanmean(vals_b)) if len(vals_b) > 0 else np.nan,
            "std": float(np.nanstd(vals_b)) if len(vals_b) > 2 else np.nan,
            "n": int(len(vals_b)),
        }

    # Kruskal-Wallis test for circadian significance
    block_samples = []
    for (blo, bhi) in TIME_BLOCKS:
        mask_b = (egp_df["hour"] >= blo) & (egp_df["hour"] < bhi)
        vals_b = egp_df.loc[mask_b, "egp_obs"].values
        if len(vals_b) >= 5:
            block_samples.append(vals_b)
    if len(block_samples) >= 3:
        kw_stat, kw_p = stats.kruskal(*block_samples)
    else:
        kw_stat, kw_p = np.nan, np.nan

    return {
        "patient_id": patient_id,
        "n_fasting_obs": int(len(egp_df)),
        "egp_median": med,
        "egp_mean": mean,
        "egp_std": std,
        "egp_iqr": iqr,
        "egp_cv": cv,
        "egp_ci_lo": ci_lo,
        "egp_ci_hi": ci_hi,
        "egp_ci_width": ci_width,
        "dawn_egp_median": float(dawn_med) if np.isfinite(dawn_med) else None,
        "nadir_egp_median": float(nadir_med) if np.isfinite(nadir_med) else None,
        "dawn_nadir_ratio": float(dawn_ratio) if np.isfinite(dawn_ratio) else None,
        "circadian_kw_stat": float(kw_stat) if np.isfinite(kw_stat) else None,
        "circadian_kw_p": float(kw_p) if np.isfinite(kw_p) else None,
        "block_egp": block_egp,
        "hourly_egp": {str(h): v for h, v in hourly_egp.items()},
    }


def run_part1(grid: pd.DataFrame, qualified: List[str]) -> List[Dict]:
    """Part 1: Per-patient EGP profiling (H1, H2)."""
    print(f"\n{'='*70}")
    print("PART 1: Per-Patient EGP Profiling")
    print(f"{'='*70}")

    profiles = []
    for pid in sorted(qualified):
        pdf = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 500:
            print(f"  {pid}: too few rows ({len(pdf)}), skipping")
            continue
        prof = profile_patient_egp(pdf, pid)
        if prof is not None:
            profiles.append(prof)
            print(f"  {pid}: median EGP={prof['egp_median']:.3f}, "
                  f"CV={prof['egp_cv']:.3f}, dawn_ratio={prof.get('dawn_nadir_ratio', 'N/A')}")

    print(f"\n  Profiled {len(profiles)} patients with ≥{MIN_FASTING_OBS} fasting obs")
    return profiles


# ── Part 2: EGP-Personalized ISF Extraction ─────────────────────────────────

def extract_correction_events(
    pdf: pd.DataFrame,
    patient_egp: float,
    patient_id: Optional[str] = None,
    *,
    use_inferred_meals: bool = True,
) -> Tuple[List[Dict], List[Dict]]:
    """Extract correction events and compute ISF under population vs personal EGP.

    Returns (pop_events, personal_events) where each event has:
      isf, bg_start, bg_end, dose, n_steps, egp_contribution

    When `patient_id` is provided and `use_inferred_meals=True`, events
    are additionally rejected if any production-detected inferred meal
    starts within the [event_idx − 1h, event_idx + ISF_POST_WINDOW] band.
    This prevents under-logged meals from contaminating ISF estimates
    (post-meal hyperglycemia masquerading as a fasting correction).
    """
    n = len(pdf)
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    bolus_smb = pdf["bolus_smb"].fillna(0).values if "bolus_smb" in pdf.columns else np.zeros(n)
    carbs = pdf["carbs"].fillna(0).values
    net_basal = pdf["net_basal"].fillna(0).values if "net_basal" in pdf.columns else np.zeros(n)
    sched_basal = pdf["scheduled_basal_rate"].fillna(0).values if "scheduled_basal_rate" in pdf.columns else np.zeros(n)

    # Pre-compute inferred-meal exclusion mask: True = grid index is
    # contaminated by an inferred meal (use as "reject" indicator).
    inferred_blocked = np.zeros(n, dtype=bool)
    if use_inferred_meals and patient_id is not None:
        try:
            from cgmencode.production.fasting_helpers import (
                apply_inferred_meal_exclusion,
            )
            allow = np.ones(n, dtype=bool)
            # Pre-window 1h, post-window covers ISF_POST_WINDOW (2h)
            allow = apply_inferred_meal_exclusion(
                allow, pdf, patient_id,
                pre_steps=STEPS_PER_HOUR,
                post_steps=ISF_POST_WINDOW,
            )
            inferred_blocked = ~allow
        except Exception:
            pass

    pop_events = []
    pers_events = []
    last_event_idx = -ISF_INDEPENDENCE_GAP - 1

    for i in range(STEPS_PER_HOUR, n - ISF_POST_WINDOW):
        # Need manual bolus ≥ 0.5 U
        if bolus[i] < 0.5:
            continue
        # BG must be elevated
        if np.isnan(glucose[i]) or glucose[i] < ISF_MIN_BG:
            continue
        # Independence gap
        if (i - last_event_idx) < ISF_INDEPENDENCE_GAP:
            continue

        # Check for end-of-window glucose
        end_idx = i + ISF_POST_WINDOW
        if end_idx >= n or np.isnan(glucose[end_idx]):
            continue

        # No significant carbs in window
        carbs_in_window = np.nansum(carbs[i:end_idx])
        if carbs_in_window > ISF_MAX_CARBS:
            continue

        # Reject if inferred meal contaminates this window
        if inferred_blocked[i] or np.any(inferred_blocked[i:end_idx]):
            continue

        bg_start = glucose[i]
        bg_end = glucose[end_idx]
        bg_drop = bg_start - bg_end
        if bg_drop <= 0:
            continue

        # Total insulin: manual bolus + SMBs + excess basal
        total_bolus = bolus[i]
        total_smb = np.nansum(bolus_smb[i:end_idx])
        excess_basal = np.nansum(
            np.clip(net_basal[i:end_idx] - sched_basal[i:end_idx], 0, None)
        ) / STEPS_PER_HOUR
        total_insulin = total_bolus + total_smb + excess_basal
        if total_insulin < ISF_MIN_DOSE:
            continue

        n_steps = ISF_POST_WINDOW

        # Population EGP correction
        pop_egp_total = POP_EGP * n_steps
        pop_corrected_drop = bg_drop + pop_egp_total  # EGP adds to glucose
        pop_isf = pop_corrected_drop / total_insulin

        # Personal EGP correction
        pers_egp_total = patient_egp * n_steps
        pers_corrected_drop = bg_drop + pers_egp_total
        pers_isf = pers_corrected_drop / total_insulin

        # Sanity: ISF should be positive and < 500
        if pop_isf < 1 or pop_isf > 500 or pers_isf < 1 or pers_isf > 500:
            continue

        last_event_idx = i

        pop_events.append({
            "isf": pop_isf,
            "bg_start": bg_start,
            "bg_end": bg_end,
            "dose": total_insulin,
            "n_steps": n_steps,
            "egp_total": pop_egp_total,
        })
        pers_events.append({
            "isf": pers_isf,
            "bg_start": bg_start,
            "bg_end": bg_end,
            "dose": total_insulin,
            "n_steps": n_steps,
            "egp_total": pers_egp_total,
        })

    return pop_events, pers_events


def run_part2(
    grid: pd.DataFrame, qualified: List[str], profiles: List[Dict],
) -> List[Dict]:
    """Part 2: EGP-personalized ISF extraction (H3)."""
    print(f"\n{'='*70}")
    print("PART 2: EGP-Personalized ISF Extraction")
    print(f"{'='*70}")

    egp_lookup = {p["patient_id"]: p["egp_median"] for p in profiles}
    results = []

    for pid in sorted(qualified):
        if pid not in egp_lookup:
            continue
        patient_egp = egp_lookup[pid]
        pdf = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        pop_events, pers_events = extract_correction_events(pdf, patient_egp, pid)

        if len(pop_events) < 5:
            print(f"  {pid}: only {len(pop_events)} correction events, skipping")
            continue

        pop_isfs = np.array([e["isf"] for e in pop_events])
        pers_isfs = np.array([e["isf"] for e in pers_events])

        pop_ci = bootstrap_ci(pop_isfs)
        pers_ci = bootstrap_ci(pers_isfs)
        pop_ci_width = pop_ci[2] - pop_ci[0] if np.isfinite(pop_ci[0]) else np.nan
        pers_ci_width = pers_ci[2] - pers_ci[0] if np.isfinite(pers_ci[0]) else np.nan

        improvement = (pop_ci_width - pers_ci_width) / pop_ci_width * 100 if pop_ci_width > 0 else np.nan

        profile_isf = pdf["scheduled_isf"].median()

        results.append({
            "patient_id": pid,
            "n_events": len(pop_events),
            "patient_egp": patient_egp,
            "pop_isf_median": float(np.median(pop_isfs)),
            "pop_isf_ci_lo": pop_ci[0],
            "pop_isf_ci_hi": pop_ci[2],
            "pop_isf_ci_width": pop_ci_width,
            "pop_isf_cv": safe_cv(pop_isfs),
            "pers_isf_median": float(np.median(pers_isfs)),
            "pers_isf_ci_lo": pers_ci[0],
            "pers_isf_ci_hi": pers_ci[2],
            "pers_isf_ci_width": pers_ci_width,
            "pers_isf_cv": safe_cv(pers_isfs),
            "ci_width_improvement_pct": float(improvement) if np.isfinite(improvement) else None,
            "profile_isf": float(profile_isf) if np.isfinite(profile_isf) else None,
        })

        print(f"  {pid}: pop CI width={pop_ci_width:.1f}, pers CI width={pers_ci_width:.1f}, "
              f"improvement={improvement:.1f}%" if np.isfinite(improvement) else
              f"  {pid}: insufficient data for CI comparison")

    return results


# ── Part 3: EGP-Personalized Basal Optimization ─────────────────────────────

def compute_fasting_drift_per_block(
    pdf: pd.DataFrame,
    fasting_mask: np.ndarray,
    patient_egp_by_block: Dict[str, float],
) -> Dict[str, Dict]:
    """Compute fasting drift per 4-hour block, with pop vs personal EGP subtracted."""
    glucose = pdf["glucose"].values
    hours = hour_of_day(pdf["time"])
    n = len(pdf)
    results = {}

    for (blo, bhi), label in zip(TIME_BLOCKS, BLOCK_LABELS):
        raw_drifts = []
        pop_corrected = []
        pers_corrected = []

        for i in range(n - DRIFT_HORIZON):
            if not fasting_mask[i]:
                continue
            # Check the block
            h = hours[i]
            if not (blo <= h < bhi):
                continue
            # Valid glucose at both endpoints
            if np.isnan(glucose[i]) or np.isnan(glucose[i + DRIFT_HORIZON]):
                continue
            # All steps in the horizon should be fasting
            if not np.all(fasting_mask[i:i + DRIFT_HORIZON]):
                continue

            raw_drift = glucose[i + DRIFT_HORIZON] - glucose[i]
            pop_egp_contribution = POP_EGP * DRIFT_HORIZON
            pers_egp = patient_egp_by_block.get(label, POP_EGP)
            pers_egp_contribution = pers_egp * DRIFT_HORIZON

            raw_drifts.append(raw_drift)
            pop_corrected.append(raw_drift - pop_egp_contribution)
            pers_corrected.append(raw_drift - pers_egp_contribution)

        results[label] = {
            "n_windows": len(raw_drifts),
            "raw_drift_median": safe_median(raw_drifts),
            "pop_corrected_median": safe_median(pop_corrected),
            "pers_corrected_median": safe_median(pers_corrected),
            "raw_drift_std": float(np.std(raw_drifts)) if len(raw_drifts) > 2 else np.nan,
            "pop_corrected_std": float(np.std(pop_corrected)) if len(pop_corrected) > 2 else np.nan,
            "pers_corrected_std": float(np.std(pers_corrected)) if len(pers_corrected) > 2 else np.nan,
        }

    return results


def score_basal_calibration(
    drift_blocks: Dict[str, Dict],
    patient_isf: float,
    current_basal_blocks: Dict[str, float],
    mode: str = "pop",
) -> Tuple[float, Dict]:
    """Score basal calibration (0-100) from residual drift after EGP subtraction.

    A perfect score means the residual drift after EGP correction is zero
    (basal exactly compensates insulin need minus EGP).
    """
    key = f"{mode}_corrected_median"
    block_scores = {}
    total_score = 0
    n_valid = 0

    for label in BLOCK_LABELS:
        bdata = drift_blocks.get(label)
        if bdata is None or bdata["n_windows"] < 5:
            block_scores[label] = None
            continue

        residual = bdata[key]
        if np.isnan(residual) or np.isnan(patient_isf) or patient_isf < 1:
            block_scores[label] = None
            continue

        # Convert residual drift to basal adjustment needed (U/hr)
        # drift in mg/dL over 1h; ISF = mg/dL per U
        basal_adj = residual / patient_isf
        current = current_basal_blocks.get(label, 1.0)

        # Score: 100 if no adjustment needed, decaying with |adjustment|
        # relative error = |adj| / current
        if current > 0.01:
            rel_error = abs(basal_adj) / current
        else:
            rel_error = abs(basal_adj)
        # Score: exp(-2 * rel_error) * 100
        block_score = 100 * np.exp(-2 * rel_error)
        block_scores[label] = float(block_score)
        total_score += block_score
        n_valid += 1

    overall = total_score / n_valid if n_valid > 0 else 0
    return overall, block_scores


def run_part3(
    grid: pd.DataFrame, qualified: List[str], profiles: List[Dict],
) -> List[Dict]:
    """Part 3: EGP-personalized basal optimization (H4)."""
    print(f"\n{'='*70}")
    print("PART 3: EGP-Personalized Basal Optimization")
    print(f"{'='*70}")

    egp_lookup = {p["patient_id"]: p for p in profiles}
    results = []

    for pid in sorted(qualified):
        if pid not in egp_lookup:
            continue
        prof = egp_lookup[pid]
        pdf = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        fasting_mask = identify_fasting_mask(pdf, pid)

        if np.sum(fasting_mask) < MIN_FASTING_OBS:
            continue

        # Patient-specific EGP by block
        pers_egp_by_block = {}
        for label in BLOCK_LABELS:
            block_data = prof["block_egp"].get(label, {})
            med = block_data.get("median")
            if med is not None and np.isfinite(med):
                pers_egp_by_block[label] = med
            else:
                pers_egp_by_block[label] = prof["egp_median"]

        drift_blocks = compute_fasting_drift_per_block(pdf, fasting_mask, pers_egp_by_block)

        # Patient ISF from profile
        patient_isf = float(pdf["scheduled_isf"].median())
        if np.isnan(patient_isf) or patient_isf < 1:
            continue

        # Current basal by block
        current_basal_blocks = {}
        hours = hour_of_day(pdf["time"])
        for (blo, bhi), label in zip(TIME_BLOCKS, BLOCK_LABELS):
            mask_b = (hours >= blo) & (hours < bhi)
            vals = pdf.loc[mask_b, "scheduled_basal_rate"].values
            vals = vals[np.isfinite(vals)]
            current_basal_blocks[label] = float(np.median(vals)) if len(vals) > 0 else 1.0

        pop_score, pop_block_scores = score_basal_calibration(
            drift_blocks, patient_isf, current_basal_blocks, mode="pop"
        )
        pers_score, pers_block_scores = score_basal_calibration(
            drift_blocks, patient_isf, current_basal_blocks, mode="pers"
        )

        results.append({
            "patient_id": pid,
            "patient_isf": patient_isf,
            "patient_egp_median": prof["egp_median"],
            "pop_basal_score": pop_score,
            "pers_basal_score": pers_score,
            "score_improvement": pers_score - pop_score,
            "pop_block_scores": pop_block_scores,
            "pers_block_scores": pers_block_scores,
            "drift_blocks": {
                label: {
                    "n_windows": b["n_windows"],
                    "raw_drift_median": b["raw_drift_median"],
                    "pop_corrected_median": b["pop_corrected_median"],
                    "pers_corrected_median": b["pers_corrected_median"],
                }
                for label, b in drift_blocks.items()
            },
        })

        print(f"  {pid}: pop_score={pop_score:.1f}, pers_score={pers_score:.1f}, "
              f"Δ={pers_score - pop_score:+.1f}")

    return results


# ── Part 4: EGP Variability vs Settings Quality ─────────────────────────────

def run_part4(
    grid: pd.DataFrame, profiles: List[Dict], isf_results: List[Dict],
) -> Dict:
    """Part 4: Correlate EGP variability with settings extraction error (H5)."""
    print(f"\n{'='*70}")
    print("PART 4: EGP Variability vs Settings Quality")
    print(f"{'='*70}")

    # Build per-patient metrics
    egp_cvs = []
    settings_errors = []
    patient_ids = []

    egp_lookup = {p["patient_id"]: p for p in profiles}
    isf_lookup = {r["patient_id"]: r for r in isf_results}

    for pid, prof in egp_lookup.items():
        if pid not in isf_lookup:
            continue
        isf_res = isf_lookup[pid]
        egp_cv = prof["egp_cv"]
        profile_isf = isf_res.get("profile_isf")
        empirical_isf = isf_res.get("pers_isf_median")

        if (egp_cv is None or profile_isf is None or empirical_isf is None
                or not np.isfinite(egp_cv) or not np.isfinite(profile_isf)
                or not np.isfinite(empirical_isf) or profile_isf < 1):
            continue

        settings_error = abs(profile_isf - empirical_isf) / profile_isf
        egp_cvs.append(egp_cv)
        settings_errors.append(settings_error)
        patient_ids.append(pid)

    print(f"  {len(egp_cvs)} patients with both EGP CV and settings error")

    if len(egp_cvs) < 5:
        print("  Insufficient data for correlation")
        return {
            "n_patients": len(egp_cvs),
            "correlation_r": None,
            "correlation_p": None,
            "regression_slope": None,
            "regression_intercept": None,
            "patient_data": [],
        }

    egp_arr = np.array(egp_cvs)
    err_arr = np.array(settings_errors)

    # Guard against constant arrays
    if np.std(egp_arr) < 1e-6 or np.std(err_arr) < 1e-6:
        print("  Constant values — cannot compute correlation")
        r, p_val, slope, intercept = np.nan, np.nan, np.nan, np.nan
    else:
        slope, intercept, r, p_val, se = stats.linregress(egp_arr, err_arr)

    print(f"  Correlation: r={r:.3f}, p={p_val:.4f}")
    print(f"  Regression: settings_error = {slope:.3f} * EGP_CV + {intercept:.3f}")

    return {
        "n_patients": len(egp_cvs),
        "correlation_r": float(r) if np.isfinite(r) else None,
        "correlation_p": float(p_val) if np.isfinite(p_val) else None,
        "regression_slope": float(slope) if np.isfinite(slope) else None,
        "regression_intercept": float(intercept) if np.isfinite(intercept) else None,
        "patient_data": [
            {"patient_id": pid, "egp_cv": cv, "settings_error": se}
            for pid, cv, se in zip(patient_ids, egp_cvs, settings_errors)
        ],
    }


# ── Hypothesis Evaluation ────────────────────────────────────────────────────

def evaluate_hypotheses(
    profiles: List[Dict],
    isf_results: List[Dict],
    basal_results: List[Dict],
    variability: Dict,
) -> Dict[str, Dict]:
    """Evaluate all 5 hypotheses."""
    print(f"\n{'='*70}")
    print("HYPOTHESIS EVALUATION")
    print(f"{'='*70}")

    hypotheses = {}

    # H1: EGP varies >2× across patients
    medians = [p["egp_median"] for p in profiles if np.isfinite(p["egp_median"])]
    if len(medians) >= 2:
        med_arr = np.array(medians)
        # Use positive medians only for ratio
        positive = med_arr[med_arr > 0.01]
        if len(positive) >= 2:
            ratio = float(np.max(positive) / np.min(positive))
        else:
            ratio = np.nan
        h1_pass = bool(ratio > 2.0) if np.isfinite(ratio) else False
        detail = (f"max/min ratio = {ratio:.2f} across {len(medians)} patients, "
                  f"range [{np.min(med_arr):.3f}, {np.max(med_arr):.3f}]")
    else:
        h1_pass = False
        ratio = np.nan
        detail = "Insufficient patients"

    hypotheses["H1_inter_patient_variation_gt_2x"] = {
        "passed": h1_pass,
        "detail": detail,
        "max_min_ratio": float(ratio) if np.isfinite(ratio) else None,
    }
    print(f"\n  H1 (EGP varies >2× across patients): {'PASS' if h1_pass else 'FAIL'}")
    print(f"      {detail}")

    # H2: Dawn > nadir ratio > 1.5 in ≥50% of patients
    dawn_ratios = [
        p["dawn_nadir_ratio"] for p in profiles
        if p.get("dawn_nadir_ratio") is not None and np.isfinite(p["dawn_nadir_ratio"])
    ]
    n_with_dawn = sum(1 for r in dawn_ratios if r > 1.5)
    pct_dawn = n_with_dawn / len(dawn_ratios) * 100 if dawn_ratios else 0
    h2_pass = bool(pct_dawn >= 50.0) if dawn_ratios else False
    detail = (f"{n_with_dawn}/{len(dawn_ratios)} patients ({pct_dawn:.0f}%) "
              f"have dawn/nadir ratio > 1.5")
    hypotheses["H2_circadian_dawn_gt_1_5_in_50pct"] = {
        "passed": h2_pass,
        "detail": detail,
        "pct_patients_with_dawn": pct_dawn,
        "dawn_ratios": [float(r) for r in dawn_ratios],
    }
    print(f"\n  H2 (Dawn/nadir ratio > 1.5 in ≥50%): {'PASS' if h2_pass else 'FAIL'}")
    print(f"      {detail}")

    # H3: Per-patient EGP improves ISF precision by >15%
    improvements = [
        r["ci_width_improvement_pct"] for r in isf_results
        if r.get("ci_width_improvement_pct") is not None
        and np.isfinite(r["ci_width_improvement_pct"])
    ]
    if improvements:
        med_improvement = float(np.median(improvements))
        h3_pass = bool(med_improvement > 15.0)
        detail = (f"Median CI width improvement = {med_improvement:.1f}% "
                  f"({len(improvements)} patients)")
    else:
        h3_pass = False
        med_improvement = np.nan
        detail = "No valid ISF comparisons"
    hypotheses["H3_isf_precision_gt_15pct_improvement"] = {
        "passed": h3_pass,
        "detail": detail,
        "median_improvement_pct": float(med_improvement) if np.isfinite(med_improvement) else None,
        "per_patient_improvements": [float(i) for i in improvements],
    }
    print(f"\n  H3 (ISF precision improves >15%): {'PASS' if h3_pass else 'FAIL'}")
    print(f"      {detail}")

    # H4: Per-patient EGP improves basal score (>25/100 vs 19.5)
    pers_scores = [r["pers_basal_score"] for r in basal_results]
    pop_scores = [r["pop_basal_score"] for r in basal_results]
    if pers_scores:
        med_pers = float(np.median(pers_scores))
        med_pop = float(np.median(pop_scores))
        h4_pass = bool(med_pers > 25.0)
        detail = (f"Personalized median score = {med_pers:.1f}/100 "
                  f"(vs pop = {med_pop:.1f}/100, baseline 19.5)")
    else:
        h4_pass = False
        med_pers = np.nan
        med_pop = np.nan
        detail = "No valid basal results"
    hypotheses["H4_basal_score_gt_25"] = {
        "passed": h4_pass,
        "detail": detail,
        "pers_median_score": float(med_pers) if np.isfinite(med_pers) else None,
        "pop_median_score": float(med_pop) if np.isfinite(med_pop) else None,
    }
    print(f"\n  H4 (Basal score > 25/100): {'PASS' if h4_pass else 'FAIL'}")
    print(f"      {detail}")

    # H5: EGP variability correlates with settings error (r > 0.3)
    r_val = variability.get("correlation_r")
    if r_val is not None and np.isfinite(r_val):
        h5_pass = bool(abs(r_val) > 0.3)
        detail = (f"r = {r_val:.3f}, p = {variability.get('correlation_p', np.nan):.4f} "
                  f"({variability['n_patients']} patients)")
    else:
        h5_pass = False
        detail = "Could not compute correlation"
    hypotheses["H5_egp_cv_correlates_with_error_gt_0_3"] = {
        "passed": h5_pass,
        "detail": detail,
        "r": float(r_val) if r_val is not None and np.isfinite(r_val) else None,
    }
    print(f"\n  H5 (EGP CV vs error r > 0.3): {'PASS' if h5_pass else 'FAIL'}")
    print(f"      {detail}")

    n_pass = sum(1 for h in hypotheses.values() if bool(h["passed"]))
    print(f"\n  OVERALL: {n_pass}/5 hypotheses passed")

    return hypotheses


# ── Visualization ────────────────────────────────────────────────────────────

def create_visualizations(
    profiles: List[Dict],
    isf_results: List[Dict],
    basal_results: List[Dict],
    variability: Dict,
):
    """Create 2×3 panel visualization."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Color scheme
    C_POP = "#2196F3"       # blue for population
    C_PERS = "#4CAF50"      # green for personalized
    C_EGP = "#FF9800"       # orange for EGP
    C_DAWN = "#F44336"      # red for dawn
    C_SCATTER = "#9C27B0"   # purple for scatter
    C_GRID = "#E0E0E0"

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(f"EXP-{EXP_ID}: Per-Patient EGP Profiling & Precision",
                 fontsize=14, fontweight="bold", y=0.98)

    # ── Panel 1: Per-patient EGP distribution (box plot) ────────────────
    ax = axes[0, 0]
    sorted_profs = sorted(profiles, key=lambda p: p["egp_median"])
    pids_short = [p["patient_id"][:8] for p in sorted_profs]
    medians = [p["egp_median"] for p in sorted_profs]
    iqrs = [p["egp_iqr"] for p in sorted_profs]
    ci_los = [p["egp_ci_lo"] for p in sorted_profs]
    ci_his = [p["egp_ci_hi"] for p in sorted_profs]

    x_pos = np.arange(len(sorted_profs))
    ax.bar(x_pos, medians, color=C_EGP, alpha=0.7, width=0.6, label="Median EGP")
    for i, (lo, hi) in enumerate(zip(ci_los, ci_his)):
        if np.isfinite(lo) and np.isfinite(hi):
            ax.plot([i, i], [lo, hi], color="black", linewidth=1.5)
    ax.axhline(POP_EGP, color=C_POP, linestyle="--", linewidth=1.5, label=f"Pop EGP ({POP_EGP})")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(pids_short, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("EGP (mg/dL per 5 min)")
    ax.set_title("A. Per-Patient EGP Distribution")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # ── Panel 2: Circadian EGP pattern ──────────────────────────────────
    ax = axes[0, 1]
    all_hourly = {h: [] for h in range(24)}
    for prof in profiles:
        for h_str, v in prof["hourly_egp"].items():
            h = int(h_str)
            med = v.get("median")
            if med is not None and np.isfinite(med):
                all_hourly[h].append(med)

    hours_arr = np.arange(24)
    means_h = [np.mean(all_hourly[h]) if all_hourly[h] else np.nan for h in range(24)]
    stds_h = [np.std(all_hourly[h]) if len(all_hourly[h]) > 1 else 0 for h in range(24)]
    means_arr = np.array(means_h)
    stds_arr = np.array(stds_h)

    valid_h = np.isfinite(means_arr)
    ax.plot(hours_arr[valid_h], means_arr[valid_h], color=C_EGP, linewidth=2,
            marker="o", markersize=4, label="Mean ± SD")
    ax.fill_between(
        hours_arr[valid_h],
        (means_arr - stds_arr)[valid_h],
        (means_arr + stds_arr)[valid_h],
        color=C_EGP, alpha=0.2
    )
    # Dawn window highlight
    ax.axvspan(4, 8, color=C_DAWN, alpha=0.1, label="Dawn window (4-8h)")
    ax.axhline(POP_EGP, color=C_POP, linestyle="--", linewidth=1, alpha=0.7)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("EGP (mg/dL per 5 min)")
    ax.set_title("B. Circadian EGP Pattern")
    ax.set_xlim(0, 23)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # ── Panel 3: ISF precision improvement ──────────────────────────────
    ax = axes[0, 2]
    if isf_results:
        isf_sorted = sorted(isf_results, key=lambda r: r.get("ci_width_improvement_pct") or 0)
        isf_pids = [r["patient_id"][:8] for r in isf_sorted]
        pop_widths = [r["pop_isf_ci_width"] for r in isf_sorted]
        pers_widths = [r["pers_isf_ci_width"] for r in isf_sorted]

        x_pos2 = np.arange(len(isf_sorted))
        w = 0.35
        ax.bar(x_pos2 - w / 2, pop_widths, w, color=C_POP, alpha=0.7, label="Population EGP")
        ax.bar(x_pos2 + w / 2, pers_widths, w, color=C_PERS, alpha=0.7, label="Personal EGP")
        ax.set_xticks(x_pos2)
        ax.set_xticklabels(isf_pids, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("ISF 95% CI Width (mg/dL/U)")
        ax.legend(fontsize=8)
    ax.set_title("C. ISF Precision: Pop vs Personal EGP")
    ax.grid(True, alpha=0.3)

    # ── Panel 4: Basal calibration score ────────────────────────────────
    ax = axes[1, 0]
    if basal_results:
        basal_sorted = sorted(basal_results, key=lambda r: r["pers_basal_score"])
        b_pids = [r["patient_id"][:8] for r in basal_sorted]
        b_pop = [r["pop_basal_score"] for r in basal_sorted]
        b_pers = [r["pers_basal_score"] for r in basal_sorted]

        x_pos3 = np.arange(len(basal_sorted))
        w = 0.35
        ax.bar(x_pos3 - w / 2, b_pop, w, color=C_POP, alpha=0.7, label="Population EGP")
        ax.bar(x_pos3 + w / 2, b_pers, w, color=C_PERS, alpha=0.7, label="Personal EGP")
        ax.axhline(19.5, color="red", linestyle=":", linewidth=1, label="Baseline (19.5)")
        ax.axhline(25.0, color="green", linestyle=":", linewidth=1, label="Target (25)")
        ax.set_xticks(x_pos3)
        ax.set_xticklabels(b_pids, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Basal Calibration Score (0-100)")
        ax.legend(fontsize=7, loc="upper left")
    ax.set_title("D. Basal Calibration: Pop vs Personal EGP")
    ax.grid(True, alpha=0.3)

    # ── Panel 5: EGP variability vs settings error scatter ──────────────
    ax = axes[1, 1]
    pd_data = variability.get("patient_data", [])
    if len(pd_data) >= 3:
        cvs = [d["egp_cv"] for d in pd_data]
        errs = [d["settings_error"] for d in pd_data]
        ax.scatter(cvs, errs, color=C_SCATTER, alpha=0.7, s=60, edgecolors="white",
                   linewidth=0.5)
        # Regression line
        r_val = variability.get("correlation_r")
        if r_val is not None and np.isfinite(r_val):
            slope = variability["regression_slope"]
            intercept = variability["regression_intercept"]
            if slope is not None and np.isfinite(slope):
                x_line = np.linspace(min(cvs), max(cvs), 50)
                ax.plot(x_line, slope * x_line + intercept, color=C_SCATTER,
                        linestyle="--", linewidth=1.5, label=f"r={r_val:.2f}")
                ax.legend(fontsize=9)
        for d in pd_data:
            ax.annotate(d["patient_id"][:6], (d["egp_cv"], d["settings_error"]),
                        fontsize=6, alpha=0.6)
    ax.set_xlabel("EGP Coefficient of Variation")
    ax.set_ylabel("Settings Error (|profile-empirical|/profile)")
    ax.set_title("E. EGP Variability vs Settings Error")
    ax.grid(True, alpha=0.3)

    # ── Panel 6: Dawn phenomenon magnitude ──────────────────────────────
    ax = axes[1, 2]
    dawn_data = [
        (p["patient_id"][:8], p["dawn_nadir_ratio"])
        for p in profiles
        if p.get("dawn_nadir_ratio") is not None
        and np.isfinite(p["dawn_nadir_ratio"])
    ]
    if dawn_data:
        dawn_data.sort(key=lambda x: x[1])
        d_pids = [d[0] for d in dawn_data]
        d_ratios = [d[1] for d in dawn_data]

        colors = [C_DAWN if r > 1.5 else C_EGP for r in d_ratios]
        x_pos4 = np.arange(len(dawn_data))
        ax.bar(x_pos4, d_ratios, color=colors, alpha=0.7)
        ax.axhline(1.5, color="red", linestyle="--", linewidth=1, label="Threshold (1.5)")
        ax.axhline(1.0, color="gray", linestyle=":", linewidth=0.8)
        ax.set_xticks(x_pos4)
        ax.set_xticklabels(d_pids, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Dawn/Nadir EGP Ratio")
        ax.legend(fontsize=8)
    ax.set_title("F. Dawn Phenomenon Magnitude")
    ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = VIZ_DIR / "egp_personalization.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Visualization saved to {out_path}")
    return str(out_path)


# ── Assemble JSON Output ─────────────────────────────────────────────────────

def assemble_output(
    profiles: List[Dict],
    isf_results: List[Dict],
    basal_results: List[Dict],
    variability: Dict,
    hypotheses: Dict,
    viz_path: str,
) -> Dict:
    """Assemble complete experiment output."""
    # Summary statistics across patients
    medians = [p["egp_median"] for p in profiles if np.isfinite(p["egp_median"])]
    cvs = [p["egp_cv"] for p in profiles if np.isfinite(p["egp_cv"])]
    dawn_ratios = [
        p["dawn_nadir_ratio"] for p in profiles
        if p.get("dawn_nadir_ratio") is not None and np.isfinite(p["dawn_nadir_ratio"])
    ]

    # ISF improvement summary
    isf_improvements = [
        r["ci_width_improvement_pct"] for r in isf_results
        if r.get("ci_width_improvement_pct") is not None
        and np.isfinite(r["ci_width_improvement_pct"])
    ]

    # Basal score summary
    pop_basal_scores = [r["pop_basal_score"] for r in basal_results]
    pers_basal_scores = [r["pers_basal_score"] for r in basal_results]

    n_pass = sum(1 for h in hypotheses.values() if bool(h["passed"]))

    output = {
        "exp_id": EXP_ID,
        "title": TITLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": (
            f"{n_pass}/5 hypotheses passed. "
            f"Per-patient EGP profiling across {len(profiles)} patients. "
            f"EGP range [{min(medians):.3f}, {max(medians):.3f}] mg/dL/5min. "
            f"Median ISF CI improvement: {np.median(isf_improvements):.1f}%. "
            f"Median basal score: pop={np.median(pop_basal_scores):.1f}, "
            f"pers={np.median(pers_basal_scores):.1f}."
        ) if medians and isf_improvements and pop_basal_scores else
        f"{n_pass}/5 hypotheses passed. Per-patient EGP profiling across {len(profiles)} patients.",

        "parameters": {
            "fasting_carb_window_steps": FASTING_CARB_WINDOW,
            "fasting_bolus_window_steps": FASTING_BOLUS_WINDOW,
            "min_fasting_obs": MIN_FASTING_OBS,
            "egp_floor": EGP_FLOOR,
            "egp_ceil": EGP_CEIL,
            "population_egp": POP_EGP,
            "isf_min_bg": ISF_MIN_BG,
            "isf_post_window_steps": ISF_POST_WINDOW,
            "isf_min_dose": ISF_MIN_DOSE,
            "drift_horizon_steps": DRIFT_HORIZON,
            "n_bootstrap": N_BOOTSTRAP,
        },

        "egp_summary": {
            "n_patients": len(profiles),
            "egp_median_across_patients": float(np.median(medians)) if medians else None,
            "egp_mean_across_patients": float(np.mean(medians)) if medians else None,
            "egp_std_across_patients": float(np.std(medians)) if medians else None,
            "egp_range": [float(min(medians)), float(max(medians))] if medians else None,
            "inter_patient_cv": safe_cv(medians),
            "median_intra_patient_cv": float(np.median(cvs)) if cvs else None,
            "median_dawn_nadir_ratio": float(np.median(dawn_ratios)) if dawn_ratios else None,
        },

        "isf_precision_summary": {
            "n_patients": len(isf_results),
            "median_ci_improvement_pct": float(np.median(isf_improvements)) if isf_improvements else None,
            "mean_ci_improvement_pct": float(np.mean(isf_improvements)) if isf_improvements else None,
            "n_improved": sum(1 for i in isf_improvements if i > 0),
            "n_worsened": sum(1 for i in isf_improvements if i < 0),
        },

        "basal_score_summary": {
            "n_patients": len(basal_results),
            "pop_median_score": float(np.median(pop_basal_scores)) if pop_basal_scores else None,
            "pers_median_score": float(np.median(pers_basal_scores)) if pers_basal_scores else None,
            "score_improvement_median": float(np.median([
                r["score_improvement"] for r in basal_results
            ])) if basal_results else None,
        },

        "variability_vs_quality": {
            "correlation_r": variability.get("correlation_r"),
            "correlation_p": variability.get("correlation_p"),
            "n_patients": variability.get("n_patients"),
        },

        "hypotheses": hypotheses,

        "per_patient_egp_profiles": profiles,
        "per_patient_isf_results": isf_results,
        "per_patient_basal_results": basal_results,
        "variability_detail": variability,

        "visualization": viz_path,
    }

    return output


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"{'#'*70}")
    print(f"# EXP-{EXP_ID}: {TITLE}")
    print(f"{'#'*70}")

    grid, qualified = load_data()

    # Part 1: EGP profiling
    profiles = run_part1(grid, qualified)
    if not profiles:
        print("\nERROR: No patients profiled. Aborting.")
        sys.exit(1)

    # Part 2: ISF extraction
    isf_results = run_part2(grid, qualified, profiles)

    # Part 3: Basal optimization
    basal_results = run_part3(grid, qualified, profiles)

    # Part 4: Variability vs quality
    variability = run_part4(grid, profiles, isf_results)

    # Evaluate hypotheses
    hypotheses = evaluate_hypotheses(profiles, isf_results, basal_results, variability)

    # Visualization
    print(f"\n{'='*70}")
    print("CREATING VISUALIZATIONS")
    print(f"{'='*70}")
    viz_path = create_visualizations(profiles, isf_results, basal_results, variability)

    # Assemble and save JSON
    output = assemble_output(
        profiles, isf_results, basal_results, variability, hypotheses, viz_path,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {OUT_JSON}")

    # ── Final Summary ────────────────────────────────────────────────────
    print(f"\n{'#'*70}")
    print(f"# EXP-{EXP_ID} FINAL SUMMARY")
    print(f"{'#'*70}")
    print(f"\nPatients profiled: {len(profiles)}")
    medians = [p['egp_median'] for p in profiles if np.isfinite(p['egp_median'])]
    if medians:
        print(f"EGP range: [{min(medians):.3f}, {max(medians):.3f}] mg/dL/5min")
        print(f"Population EGP: {POP_EGP} mg/dL/5min")
        pos_med = [m for m in medians if m > 0.01]
        if len(pos_med) >= 2:
            print(f"Max/min ratio: {max(pos_med)/min(pos_med):.2f}")

    n_pass = sum(1 for h in hypotheses.values() if bool(h["passed"]))
    print(f"\nHYPOTHESIS VERDICTS ({n_pass}/5 passed):")
    for key, val in hypotheses.items():
        status = "✓ PASS" if bool(val["passed"]) else "✗ FAIL"
        print(f"  {status}  {key}")
        print(f"         {val['detail']}")

    print(f"\nOutputs:")
    print(f"  JSON: {OUT_JSON}")
    print(f"  Viz:  {viz_path}")
    print(f"  Script: {Path(__file__).relative_to(Path.cwd())}")

    return output


if __name__ == "__main__":
    main()
