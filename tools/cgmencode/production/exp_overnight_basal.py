#!/usr/bin/env python3
"""
exp_overnight_basal.py — Overnight Basal Rate Assessment (EXP-2371–2378)

Leverages the DIA mechanism finding (EXP-2368) that AID loop confounding is the
dominant DIA extension mechanism. Overnight (00:00–06:00) is the cleanest window
for basal assessment because:
  - No meal absorption expected
  - Correction boluses from dinner have largely cleared (>6h post)
  - Counter-regulatory response is minimal during sleep
  - Loop activity can be measured and deconfounded

Experiments:
  EXP-2371: Overnight glucose drift characterization
  EXP-2372: Basal adequacy classification (rising/stable/falling)
  EXP-2373: Loop activity during overnight (suspension/increase patterns)
  EXP-2374: Dawn phenomenon detection and quantification
  EXP-2375: Overnight IOB contribution (residual dinner bolus effect)
  EXP-2376: Circadian basal need estimation (4-harmonic time model)
  EXP-2377: Optimal basal rate estimation from overnight glucose drift
  EXP-2378: Cross-patient basal phenotyping and recommendations

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_overnight_basal.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_overnight_basal.py --tiny
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "overnight-basal"
RESULTS_DIR = ROOT / "externals" / "experiments"


def load_data(tiny: bool = False) -> pd.DataFrame:
    """Load parquet data, return with datetime index."""
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


def get_overnight_segments(pdf: pd.DataFrame) -> list[dict]:
    """
    Extract individual overnight segments (continuous 00:00–06:00 windows).

    Each segment is a dict with:
      - glucose: array of glucose values
      - time: array of timestamps
      - iob: array of IOB values
      - actual_basal: array of actual basal rates
      - scheduled_basal: array of scheduled basal rates
      - date: date of the overnight segment
      - duration_hours: length of the segment
    """
    pdf = pdf.sort_values("time").copy()
    overnight = pdf[(pdf["hour"] >= 0) & (pdf["hour"] < 6)].copy()
    if len(overnight) < 12:
        return []

    overnight["date"] = overnight["time"].dt.date
    segments = []
    for date, grp in overnight.groupby("date"):
        gluc = grp["glucose"].values
        valid = ~np.isnan(gluc)
        if valid.sum() < 12:  # need at least 1 hour of data
            continue

        # Check continuity: gaps > 15 min indicate missing data
        times = grp["time"].values
        if len(times) > 1:
            gaps = np.diff(times.astype("int64")) / 1e9 / 60  # minutes
            if np.max(gaps) > 30:
                continue

        seg = {
            "date": str(date),
            "glucose": gluc,
            "time": grp["time"].values,
            "iob": grp["iob"].values if "iob" in grp.columns else np.zeros(len(grp)),
            "actual_basal": grp["actual_basal_rate"].values if "actual_basal_rate" in grp.columns else np.zeros(len(grp)),
            "scheduled_basal": grp["scheduled_basal_rate"].values if "scheduled_basal_rate" in grp.columns else np.zeros(len(grp)),
            "cob": grp["cob"].values if "cob" in grp.columns else np.zeros(len(grp)),
            "hour": grp["hour"].values,
            "duration_hours": (times[-1] - times[0]).astype("int64") / 1e9 / 3600,
        }
        segments.append(seg)

    return segments


def exp_2371_overnight_drift(df: pd.DataFrame) -> dict:
    """
    EXP-2371: Overnight glucose drift characterization.

    For each overnight segment, compute:
    - Linear drift (mg/dL/hour) via least-squares fit
    - Mean, std, min glucose
    - Whether segment crosses hypo threshold (< 70 mg/dL)
    """
    print("=" * 60)
    print("EXP-2371: Overnight Glucose Drift Characterization")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        if not segments:
            print(f"  {pid}: no valid overnight segments")
            continue

        drifts = []
        means = []
        stds = []
        hypo_nights = 0
        for seg in segments:
            gluc = seg["glucose"]
            valid = ~np.isnan(gluc)
            if valid.sum() < 6:
                continue
            hours = seg["hour"][valid]
            g = gluc[valid]
            if len(hours) < 2:
                continue
            # Linear fit: glucose = a * hour + b
            coeffs = np.polyfit(hours, g, 1)
            drift = coeffs[0]  # mg/dL per hour
            drifts.append(drift)
            means.append(np.mean(g))
            stds.append(np.std(g))
            if np.any(g < 70):
                hypo_nights += 1

        if not drifts:
            continue

        drift_arr = np.array(drifts)
        r = {
            "n_nights": len(drifts),
            "drift_mg_per_hour": {
                "mean": float(np.mean(drift_arr)),
                "median": float(np.median(drift_arr)),
                "std": float(np.std(drift_arr)),
                "q25": float(np.percentile(drift_arr, 25)),
                "q75": float(np.percentile(drift_arr, 75)),
            },
            "mean_glucose": float(np.mean(means)),
            "mean_variability": float(np.mean(stds)),
            "hypo_night_pct": float(100 * hypo_nights / len(drifts)),
            "rising_night_pct": float(100 * np.mean(drift_arr > 2)),
            "falling_night_pct": float(100 * np.mean(drift_arr < -2)),
            "stable_night_pct": float(100 * np.mean(np.abs(drift_arr) <= 2)),
        }
        results[pid] = r

        drift_med = r["drift_mg_per_hour"]["median"]
        direction = "RISING" if drift_med > 2 else "FALLING" if drift_med < -2 else "STABLE"
        print(f"  {pid}: {r['n_nights']} nights, drift {drift_med:+.1f} mg/dL/h ({direction}), "
              f"glucose {r['mean_glucose']:.0f}±{r['mean_variability']:.0f}, "
              f"hypo {r['hypo_night_pct']:.0f}%")

    return results


def exp_2372_basal_adequacy(df: pd.DataFrame) -> dict:
    """
    EXP-2372: Basal adequacy classification.

    Classifies each patient's overnight basal as:
    - INADEQUATE_LOW: glucose consistently rises (drift > +3 mg/dL/h)
    - INADEQUATE_HIGH: glucose consistently falls (drift < -3 mg/dL/h)
    - MARGINAL_LOW: glucose tends to rise (drift +1 to +3)
    - MARGINAL_HIGH: glucose tends to fall (drift -3 to -1)
    - ADEQUATE: glucose stable (|drift| ≤ 1)

    Also estimates the basal rate adjustment needed to achieve stable glucose.
    """
    print("\n" + "=" * 60)
    print("EXP-2372: Basal Adequacy Classification")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        if not segments:
            continue

        drifts = []
        basal_ratios = []  # actual/scheduled
        for seg in segments:
            gluc = seg["glucose"]
            valid = ~np.isnan(gluc)
            if valid.sum() < 6:
                continue
            hours = seg["hour"][valid]
            g = gluc[valid]
            if len(hours) < 2:
                continue
            coeffs = np.polyfit(hours, g, 1)
            drifts.append(coeffs[0])

            # Compute actual/scheduled basal ratio
            ab = seg["actual_basal"]
            sb = seg["scheduled_basal"]
            ab_valid = ab[~np.isnan(ab)]
            sb_valid = sb[~np.isnan(sb)]
            if len(ab_valid) > 0 and len(sb_valid) > 0:
                ab_mean = np.mean(ab_valid)
                sb_mean = np.mean(sb_valid)
                if sb_mean > 0.01 and ab_mean < 50:  # filter implausible values
                    basal_ratios.append(ab_mean / sb_mean)

        if not drifts:
            continue

        drift_med = float(np.median(drifts))
        drift_mean = float(np.mean(drifts))

        if drift_med > 3:
            classification = "INADEQUATE_LOW"
            adjustment = "increase"
        elif drift_med > 1:
            classification = "MARGINAL_LOW"
            adjustment = "slight_increase"
        elif drift_med < -3:
            classification = "INADEQUATE_HIGH"
            adjustment = "decrease"
        elif drift_med < -1:
            classification = "MARGINAL_HIGH"
            adjustment = "slight_decrease"
        else:
            classification = "ADEQUATE"
            adjustment = "none"

        # Estimate ISF-based basal change needed
        # If drift is +X mg/dL/h, we need ~X/ISF more units/hour
        # Use population ISF estimate ~50 mg/dL/U
        isf_estimate = 50.0
        if "scheduled_isf" in pdf.columns:
            isf_vals = pdf["scheduled_isf"].dropna()
            if len(isf_vals) > 0 and isf_vals.median() > 0:
                isf_estimate = float(isf_vals.median())

        basal_change_needed = drift_med / isf_estimate  # U/h

        r = {
            "n_nights": len(drifts),
            "drift_median": drift_med,
            "drift_mean": drift_mean,
            "classification": classification,
            "adjustment": adjustment,
            "basal_change_needed_u_per_h": float(basal_change_needed),
            "isf_used": float(isf_estimate),
            "basal_ratio_median": float(np.median(basal_ratios)) if basal_ratios else None,
            "basal_ratio_mean": float(np.mean(basal_ratios)) if basal_ratios else None,
        }
        results[pid] = r
        print(f"  {pid}: {classification} (drift {drift_med:+.1f} mg/dL/h), "
              f"need {basal_change_needed:+.03f} U/h, "
              f"basal ratio {r['basal_ratio_median']:.2f}" if r["basal_ratio_median"] else
              f"  {pid}: {classification} (drift {drift_med:+.1f} mg/dL/h), "
              f"need {basal_change_needed:+.03f} U/h")

    return results


def exp_2373_loop_overnight(df: pd.DataFrame) -> dict:
    """
    EXP-2373: Loop activity during overnight hours.

    Measures:
    - How much the loop modulates basal overnight
    - Suspension frequency and duration
    - Whether loop over-corrects (glucose swings)
    """
    print("\n" + "=" * 60)
    print("EXP-2373: Loop Activity During Overnight")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        if not segments:
            continue

        suspension_pcts = []
        increase_pcts = []
        modulation_depths = []

        for seg in segments:
            ab = seg["actual_basal"]
            sb = seg["scheduled_basal"]
            valid = ~np.isnan(ab) & ~np.isnan(sb) & (sb > 0.01) & (ab < 50)
            if valid.sum() < 6:
                continue

            ratio = ab[valid] / sb[valid]
            suspension_pcts.append(100 * np.mean(ratio < 0.1))
            increase_pcts.append(100 * np.mean(ratio > 1.5))
            modulation_depths.append(float(np.std(ratio)))

        if not suspension_pcts:
            continue

        r = {
            "n_nights": len(suspension_pcts),
            "suspension_pct": float(np.mean(suspension_pcts)),
            "increase_pct": float(np.mean(increase_pcts)),
            "modulation_depth": float(np.mean(modulation_depths)),
            "loop_active": float(np.mean(suspension_pcts)) > 5 or float(np.mean(increase_pcts)) > 5,
        }
        results[pid] = r
        status = "ACTIVE" if r["loop_active"] else "MINIMAL"
        print(f"  {pid}: loop {status}, suspend {r['suspension_pct']:.0f}%, "
              f"increase {r['increase_pct']:.0f}%, modulation {r['modulation_depth']:.2f}")

    return results


def exp_2374_dawn_phenomenon(df: pd.DataFrame) -> dict:
    """
    EXP-2374: Dawn phenomenon detection and quantification.

    Dawn phenomenon: glucose rise starting ~3-5 AM due to cortisol/GH surge.
    Detection method:
    - Compare glucose trend 00:00-03:00 vs 03:00-06:00
    - Dawn phenomenon present if 03:00-06:00 drift significantly > 00:00-03:00 drift
    """
    print("\n" + "=" * 60)
    print("EXP-2374: Dawn Phenomenon Detection")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        if not segments:
            continue

        early_drifts = []  # 00:00-03:00
        dawn_drifts = []   # 03:00-06:00
        dawn_magnitudes = []

        for seg in segments:
            gluc = seg["glucose"]
            hours = seg["hour"]
            valid = ~np.isnan(gluc)

            early_mask = valid & (hours < 3)
            dawn_mask = valid & (hours >= 3)

            if early_mask.sum() < 4 or dawn_mask.sum() < 4:
                continue

            # Fit linear trend to each phase
            try:
                early_coeff = np.polyfit(hours[early_mask], gluc[early_mask], 1)
                dawn_coeff = np.polyfit(hours[dawn_mask], gluc[dawn_mask], 1)
            except (np.linalg.LinAlgError, ValueError):
                continue

            early_drifts.append(early_coeff[0])
            dawn_drifts.append(dawn_coeff[0])
            dawn_magnitudes.append(dawn_coeff[0] - early_coeff[0])

        if not dawn_magnitudes:
            continue

        dawn_arr = np.array(dawn_magnitudes)
        dawn_present = float(np.median(dawn_arr)) > 2.0  # >2 mg/dL/h acceleration

        r = {
            "n_nights": len(dawn_magnitudes),
            "early_drift_median": float(np.median(early_drifts)),
            "dawn_drift_median": float(np.median(dawn_drifts)),
            "dawn_acceleration_median": float(np.median(dawn_arr)),
            "dawn_acceleration_mean": float(np.mean(dawn_arr)),
            "dawn_present": dawn_present,
            "dawn_magnitude_mg_per_h": float(np.median(dawn_arr)) if dawn_present else 0.0,
            "nights_with_dawn_pct": float(100 * np.mean(dawn_arr > 2)),
        }
        results[pid] = r
        status = "YES" if dawn_present else "NO"
        print(f"  {pid}: dawn={status}, early {r['early_drift_median']:+.1f} vs "
              f"dawn {r['dawn_drift_median']:+.1f} mg/dL/h, "
              f"acceleration {r['dawn_acceleration_median']:+.1f} mg/dL/h")

    return results


def exp_2375_overnight_iob(df: pd.DataFrame) -> dict:
    """
    EXP-2375: Overnight IOB contribution.

    Measures residual IOB at midnight from dinner boluses and whether it
    confounds overnight glucose assessment.
    """
    print("\n" + "=" * 60)
    print("EXP-2375: Overnight IOB Contribution")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        if not segments:
            continue

        midnight_iobs = []
        morning_iobs = []  # at 06:00
        iob_clears_by = []  # hour when IOB < 0.1

        for seg in segments:
            iob = seg["iob"]
            hours = seg["hour"]
            valid = ~np.isnan(iob)
            if valid.sum() < 6:
                continue

            # IOB at start (midnight)
            early = iob[valid & (hours < 1)]
            if len(early) > 0:
                midnight_iobs.append(float(np.mean(early)))

            # IOB at end (~6am)
            late = iob[valid & (hours > 5)]
            if len(late) > 0:
                morning_iobs.append(float(np.mean(late)))

            # When does IOB clear?
            for h in np.arange(0, 6, 0.5):
                mask = valid & (hours >= h) & (hours < h + 0.5)
                if mask.sum() > 0 and np.mean(iob[mask]) < 0.1:
                    iob_clears_by.append(h)
                    break

        if not midnight_iobs:
            continue

        r = {
            "n_nights": len(midnight_iobs),
            "midnight_iob_mean": float(np.mean(midnight_iobs)),
            "midnight_iob_median": float(np.median(midnight_iobs)),
            "morning_iob_mean": float(np.mean(morning_iobs)) if morning_iobs else 0,
            "iob_clear_hour_median": float(np.median(iob_clears_by)) if iob_clears_by else 6.0,
            "significant_midnight_iob": float(np.mean(midnight_iobs)) > 0.5,
        }
        results[pid] = r
        iob_status = "HIGH" if r["significant_midnight_iob"] else "LOW"
        print(f"  {pid}: midnight IOB={r['midnight_iob_median']:.2f}U ({iob_status}), "
              f"clears by {r['iob_clear_hour_median']:.1f}h")

    return results


def exp_2376_circadian_basal(df: pd.DataFrame) -> dict:
    """
    EXP-2376: Circadian basal need estimation using 4-harmonic time model.

    Fits: drift(h) = a0 + Σ[a_k * sin(2πk*h/24) + b_k * cos(2πk*h/24)]
    for k=1..4 harmonics, using overnight hour-by-hour drift rates.

    This captures dawn phenomenon, dusk rise, and other circadian patterns.
    """
    print("\n" + "=" * 60)
    print("EXP-2376: Circadian Basal Need (4-Harmonic Model)")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()

        # Compute hourly glucose drift across ALL hours (not just overnight)
        pdf["glucose_diff"] = pdf["glucose"].diff()
        pdf["time_diff_h"] = pdf["time"].diff().dt.total_seconds() / 3600
        valid = (pdf["time_diff_h"] > 0) & (pdf["time_diff_h"] < 0.15) & pdf["glucose_diff"].notna()
        pdf_valid = pdf[valid].copy()
        pdf_valid["drift_rate"] = pdf_valid["glucose_diff"] / pdf_valid["time_diff_h"]

        # Filter extreme values (sensor noise)
        drift_clip = pdf_valid["drift_rate"].clip(-100, 100)
        pdf_valid["drift_rate"] = drift_clip

        if len(pdf_valid) < 100:
            continue

        hours = pdf_valid["hour"].values
        drifts = pdf_valid["drift_rate"].values

        # Fit 4-harmonic model
        n_harmonics = 4
        X = np.column_stack([np.ones(len(hours))] +
                            [np.sin(2 * np.pi * k * hours / 24) for k in range(1, n_harmonics + 1)] +
                            [np.cos(2 * np.pi * k * hours / 24) for k in range(1, n_harmonics + 1)])

        try:
            coeffs, residuals, rank, sv = np.linalg.lstsq(X, drifts, rcond=None)
        except np.linalg.LinAlgError:
            continue

        # Evaluate fitted curve at each hour
        eval_hours = np.arange(0, 24, 0.5)
        X_eval = np.column_stack([np.ones(len(eval_hours))] +
                                 [np.sin(2 * np.pi * k * eval_hours / 24) for k in range(1, n_harmonics + 1)] +
                                 [np.cos(2 * np.pi * k * eval_hours / 24) for k in range(1, n_harmonics + 1)])
        fitted = X_eval @ coeffs

        # R² of the harmonic fit
        ss_res = np.sum((drifts - (X @ coeffs)) ** 2)
        ss_tot = np.sum((drifts - np.mean(drifts)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Find peak demand (maximum drift rate = where glucose rises fastest)
        peak_hour = eval_hours[np.argmax(fitted)]
        trough_hour = eval_hours[np.argmin(fitted)]
        amplitude = float(np.max(fitted) - np.min(fitted))

        # Convert drift to basal need: positive drift → need more basal
        # drift_rate (mg/dL/h) / ISF (mg/dL/U) = basal_deficit (U/h)
        isf = 50.0
        if "scheduled_isf" in pdf.columns:
            isf_vals = pdf["scheduled_isf"].dropna()
            if len(isf_vals) > 0 and isf_vals.median() > 0:
                isf = float(isf_vals.median())

        basal_need_curve = fitted / isf  # U/h adjustment needed

        r = {
            "n_samples": len(pdf_valid),
            "r_squared": float(r_squared),
            "coefficients": [float(c) for c in coeffs],
            "peak_demand_hour": float(peak_hour),
            "trough_demand_hour": float(trough_hour),
            "amplitude_mg_per_h": amplitude,
            "basal_amplitude_u_per_h": float(amplitude / isf),
            "isf_used": float(isf),
            "hourly_drift_fitted": {str(h): float(v) for h, v in zip(eval_hours, fitted)},
            "hourly_basal_adjustment": {str(h): float(v) for h, v in zip(eval_hours, basal_need_curve)},
        }
        results[pid] = r
        print(f"  {pid}: R²={r_squared:.3f}, peak demand {peak_hour:.0f}h, "
              f"trough {trough_hour:.0f}h, amplitude {amplitude:.1f} mg/dL/h "
              f"({amplitude/isf:.3f} U/h)")

    return results


def exp_2377_optimal_basal(df: pd.DataFrame, drift_results: dict) -> dict:
    """
    EXP-2377: Optimal basal rate estimation from overnight glucose drift.

    Uses the overnight drift to estimate what the basal rate SHOULD be:
    - drift > 0 → increase basal by drift/ISF
    - drift < 0 → decrease basal by |drift|/ISF
    - Compares to scheduled and actual basal

    Filters to low-IOB, no-COB segments for cleanest signal.
    """
    print("\n" + "=" * 60)
    print("EXP-2377: Optimal Basal Rate Estimation")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        segments = get_overnight_segments(pdf)
        dr = drift_results.get(pid, {})
        if not segments or not dr:
            continue

        # Filter to clean segments: low IOB, low COB
        clean_drifts = []
        clean_basals_sched = []
        clean_basals_actual = []

        for seg in segments:
            gluc = seg["glucose"]
            iob = seg["iob"]
            cob = seg["cob"]
            hours = seg["hour"]
            valid = ~np.isnan(gluc)

            if valid.sum() < 6:
                continue

            # Only use segments where IOB is low (< 0.5U) and COB is low
            iob_valid = iob[~np.isnan(iob)]
            cob_valid = cob[~np.isnan(cob)]
            if len(iob_valid) > 0 and np.mean(iob_valid) > 0.5:
                continue
            if len(cob_valid) > 0 and np.mean(cob_valid) > 5:
                continue

            # Compute drift
            try:
                coeffs = np.polyfit(hours[valid], gluc[valid], 1)
            except (np.linalg.LinAlgError, ValueError):
                continue
            clean_drifts.append(coeffs[0])

            # Get basal rates
            ab = seg["actual_basal"]
            sb = seg["scheduled_basal"]
            ab_v = ab[~np.isnan(ab) & (ab < 50)]
            sb_v = sb[~np.isnan(sb)]
            if len(ab_v) > 0:
                clean_basals_actual.append(float(np.mean(ab_v)))
            if len(sb_v) > 0:
                clean_basals_sched.append(float(np.mean(sb_v)))

        if not clean_drifts:
            continue

        drift = float(np.median(clean_drifts))

        # ISF for this patient
        isf = 50.0
        if "scheduled_isf" in pdf.columns:
            isf_vals = pdf["scheduled_isf"].dropna()
            if len(isf_vals) > 0 and isf_vals.median() > 0:
                isf = float(isf_vals.median())

        sched_basal = float(np.median(clean_basals_sched)) if clean_basals_sched else 0
        actual_basal = float(np.median(clean_basals_actual)) if clean_basals_actual else 0

        # Optimal = scheduled + drift/ISF
        adjustment = drift / isf
        optimal_basal = max(0.0, sched_basal + adjustment)

        r = {
            "n_clean_nights": len(clean_drifts),
            "clean_drift_median": drift,
            "scheduled_basal": sched_basal,
            "actual_basal": actual_basal,
            "optimal_basal": float(optimal_basal),
            "adjustment_u_per_h": float(adjustment),
            "isf_used": float(isf),
            "pct_change": float(100 * adjustment / sched_basal) if sched_basal > 0.01 else None,
        }
        results[pid] = r
        pct = f" ({r['pct_change']:+.0f}%)" if r["pct_change"] is not None else ""
        print(f"  {pid}: {r['n_clean_nights']} clean nights, drift {drift:+.1f} mg/dL/h, "
              f"sched {sched_basal:.2f} → optimal {optimal_basal:.2f} U/h{pct}")

    return results


def exp_2378_phenotyping(drift_results: dict, adequacy_results: dict,
                         dawn_results: dict, loop_results: dict,
                         optimal_results: dict) -> dict:
    """
    EXP-2378: Cross-patient basal phenotyping and recommendations.

    Groups patients into phenotypes based on overnight behavior:
    - "Stable Sleeper": adequate basal, no dawn phenomenon
    - "Dawn Riser": adequate baseline but significant dawn phenomenon
    - "Chronic Under-Basaled": consistently rising glucose overnight
    - "Over-Basaled": consistently falling glucose overnight
    - "Loop-Dependent": stable glucose but only because loop modulates aggressively
    """
    print("\n" + "=" * 60)
    print("EXP-2378: Cross-Patient Basal Phenotyping")
    print("=" * 60)

    results = {}
    phenotype_counts = {}

    for pid in drift_results:
        drift = drift_results[pid]
        adequacy = adequacy_results.get(pid, {})
        dawn = dawn_results.get(pid, {})
        loop = loop_results.get(pid, {})
        optimal = optimal_results.get(pid, {})

        classification = adequacy.get("classification", "UNKNOWN")
        dawn_present = dawn.get("dawn_present", False)
        loop_active = loop.get("loop_active", False)
        modulation = loop.get("modulation_depth", 0)

        # Phenotype assignment
        if classification == "ADEQUATE" and not dawn_present and not loop_active:
            phenotype = "stable_sleeper"
        elif classification == "ADEQUATE" and loop_active and modulation > 0.5:
            phenotype = "loop_dependent"
        elif dawn_present and classification in ("ADEQUATE", "MARGINAL_LOW"):
            phenotype = "dawn_riser"
        elif classification in ("INADEQUATE_LOW", "MARGINAL_LOW"):
            phenotype = "under_basaled"
        elif classification in ("INADEQUATE_HIGH", "MARGINAL_HIGH"):
            phenotype = "over_basaled"
        else:
            phenotype = "mixed"

        phenotype_counts[phenotype] = phenotype_counts.get(phenotype, 0) + 1

        # Recommendations
        recommendations = []
        if phenotype == "under_basaled":
            adj = optimal.get("adjustment_u_per_h", 0)
            recommendations.append(f"Increase overnight basal by {adj:+.03f} U/h")
        elif phenotype == "over_basaled":
            adj = optimal.get("adjustment_u_per_h", 0)
            recommendations.append(f"Decrease overnight basal by {abs(adj):.03f} U/h")
        elif phenotype == "dawn_riser":
            dawn_mag = dawn.get("dawn_magnitude_mg_per_h", 0)
            recommendations.append(f"Consider higher basal 03:00-06:00 (+{dawn_mag:.1f} mg/dL/h to compensate)")
        elif phenotype == "loop_dependent":
            recommendations.append("Basal appears adequate only because loop compensates. "
                                   "Consider reviewing scheduled rate.")
        elif phenotype == "stable_sleeper":
            recommendations.append("Overnight basal appears well-calibrated. No changes needed.")

        r = {
            "phenotype": phenotype,
            "classification": classification,
            "dawn_present": dawn_present,
            "loop_active": loop_active,
            "drift_median": drift.get("drift_mg_per_hour", {}).get("median", 0),
            "recommendations": recommendations,
        }
        results[pid] = r
        print(f"  {pid}: {phenotype.upper()}, {', '.join(recommendations)}")

    print(f"\n  Phenotype distribution: {phenotype_counts}")
    results["_phenotype_distribution"] = phenotype_counts
    return results


def generate_visualizations(drift_results: dict, adequacy_results: dict,
                            dawn_results: dict, circadian_results: dict,
                            optimal_results: dict, phenotype_results: dict):
    """Generate figures for the overnight basal analysis."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping visualizations")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # --- Figure 1: Overnight drift distribution ---
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    patients = sorted([p for p in drift_results if not p.startswith("_")])
    drifts = [drift_results[p]["drift_mg_per_hour"]["median"] for p in patients]
    labels = [p[:12] for p in patients]

    colors = []
    for d in drifts:
        if d > 3:
            colors.append("red")
        elif d > 1:
            colors.append("orange")
        elif d < -3:
            colors.append("blue")
        elif d < -1:
            colors.append("lightblue")
        else:
            colors.append("green")

    axes[0].barh(range(len(patients)), drifts, color=colors)
    axes[0].set_yticks(range(len(patients)))
    axes[0].set_yticklabels(labels, fontsize=8)
    axes[0].axvline(0, color="black", linewidth=0.5)
    axes[0].axvline(3, color="red", linewidth=0.5, linestyle="--", label="+3 threshold")
    axes[0].axvline(-3, color="blue", linewidth=0.5, linestyle="--", label="-3 threshold")
    axes[0].set_xlabel("Overnight Drift (mg/dL/h)")
    axes[0].set_title("Overnight Glucose Drift")
    axes[0].legend(fontsize=7)

    # --- Figure 1b: Dawn phenomenon ---
    dawn_accel = [dawn_results.get(p, {}).get("dawn_acceleration_median", 0) for p in patients]
    dawn_colors = ["red" if a > 2 else "gray" for a in dawn_accel]
    axes[1].barh(range(len(patients)), dawn_accel, color=dawn_colors)
    axes[1].set_yticks(range(len(patients)))
    axes[1].set_yticklabels(labels, fontsize=8)
    axes[1].axvline(2, color="red", linewidth=0.5, linestyle="--", label="Dawn threshold")
    axes[1].set_xlabel("Dawn Acceleration (mg/dL/h)")
    axes[1].set_title("Dawn Phenomenon")
    axes[1].legend(fontsize=7)

    # --- Figure 1c: Phenotype distribution ---
    pheno_dist = phenotype_results.get("_phenotype_distribution", {})
    if pheno_dist:
        pheno_colors = {
            "stable_sleeper": "green", "dawn_riser": "orange",
            "under_basaled": "red", "over_basaled": "blue",
            "loop_dependent": "purple", "mixed": "gray"
        }
        labels_p = list(pheno_dist.keys())
        values_p = list(pheno_dist.values())
        colors_p = [pheno_colors.get(l, "gray") for l in labels_p]
        axes[2].pie(values_p, labels=[l.replace("_", "\n") for l in labels_p],
                    colors=colors_p, autopct="%1.0f%%", startangle=90)
        axes[2].set_title("Overnight Phenotypes")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_overnight_drift_and_phenotypes.png", dpi=150)
    plt.close()
    print(f"  Saved fig1_overnight_drift_and_phenotypes.png")

    # --- Figure 2: Circadian drift curve (selected patients) ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Pick 4 representative patients (diverse phenotypes)
    representative = []
    for phenotype in ["stable_sleeper", "under_basaled", "dawn_riser", "loop_dependent"]:
        for p in patients:
            if phenotype_results.get(p, {}).get("phenotype") == phenotype and p in circadian_results:
                representative.append((p, phenotype))
                break
    # Fill remaining slots
    while len(representative) < 4 and patients:
        for p in patients:
            if p in circadian_results and p not in [r[0] for r in representative]:
                ph = phenotype_results.get(p, {}).get("phenotype", "unknown")
                representative.append((p, ph))
                break
        if len(representative) < 4:
            break

    for idx, (ax, (pid, pheno)) in enumerate(zip(axes.flat, representative)):
        cr = circadian_results[pid]
        hours = sorted([float(h) for h in cr["hourly_drift_fitted"].keys()])
        fitted = [cr["hourly_drift_fitted"][str(h)] for h in hours]

        ax.plot(hours, fitted, "b-", linewidth=2, label="4-harmonic fit")
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.axvspan(0, 6, alpha=0.1, color="blue", label="Overnight")
        ax.axvspan(3, 6, alpha=0.1, color="orange", label="Dawn window")
        ax.set_xlabel("Hour of Day")
        ax.set_ylabel("Glucose Drift (mg/dL/h)")
        ax.set_title(f"{pid[:12]} ({pheno}), R²={cr['r_squared']:.3f}")
        ax.set_xlim(0, 24)
        ax.legend(fontsize=7)

    plt.suptitle("Circadian Glucose Drift Patterns (4-Harmonic Model)", fontsize=14)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_circadian_drift_curves.png", dpi=150)
    plt.close()
    print(f"  Saved fig2_circadian_drift_curves.png")

    # --- Figure 3: Scheduled vs Optimal basal ---
    fig, ax = plt.subplots(figsize=(10, 6))

    opt_patients = [p for p in patients if p in optimal_results and
                    optimal_results[p].get("scheduled_basal", 0) > 0.01]
    if opt_patients:
        sched = [optimal_results[p]["scheduled_basal"] for p in opt_patients]
        optimal = [optimal_results[p]["optimal_basal"] for p in opt_patients]
        x = range(len(opt_patients))

        ax.bar([i - 0.2 for i in x], sched, 0.4, label="Scheduled", color="steelblue")
        ax.bar([i + 0.2 for i in x], optimal, 0.4, label="Optimal (drift-adjusted)", color="coral")
        ax.set_xticks(list(x))
        ax.set_xticklabels([p[:12] for p in opt_patients], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Basal Rate (U/h)")
        ax.set_title("Scheduled vs Drift-Adjusted Optimal Overnight Basal")
        ax.legend()
        ax.axhline(0, color="gray", linewidth=0.5)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_scheduled_vs_optimal_basal.png", dpi=150)
    plt.close()
    print(f"  Saved fig3_scheduled_vs_optimal_basal.png")


def main():
    parser = argparse.ArgumentParser(description="Overnight Basal Assessment")
    parser.add_argument("--tiny", action="store_true", help="Use tiny dataset for dev")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    # Run experiments
    drift_results = exp_2371_overnight_drift(df)
    adequacy_results = exp_2372_basal_adequacy(df)
    loop_results = exp_2373_loop_overnight(df)
    dawn_results = exp_2374_dawn_phenomenon(df)
    iob_results = exp_2375_overnight_iob(df)
    circadian_results = exp_2376_circadian_basal(df)
    optimal_results = exp_2377_optimal_basal(df, drift_results)
    phenotype_results = exp_2378_phenotyping(
        drift_results, adequacy_results, dawn_results,
        loop_results, optimal_results)

    # Generate visualizations
    print("\nGenerating visualizations...")
    generate_visualizations(drift_results, adequacy_results, dawn_results,
                            circadian_results, optimal_results, phenotype_results)

    # Save results
    all_results = {
        "exp_2371": drift_results,
        "exp_2372": adequacy_results,
        "exp_2373": loop_results,
        "exp_2374": dawn_results,
        "exp_2375": iob_results,
        "exp_2376": circadian_results,
        "exp_2377": optimal_results,
        "exp_2378": phenotype_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2371-2378_overnight_basal.json"
    with open(out_path, "w") as f:
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            raise TypeError(f"Cannot serialize {type(obj)}")
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
