#!/usr/bin/env python3
"""EXP-2753: Controller Response Decomposition.

During a correction event (user bolus for high BG), the AID controller also
responds by delivering SMBs, adjusting temp basal rates, and later suspending
basal. These controller actions confound ISF extraction because the BG drop
reflects BOTH the user's correction AND the controller's assistance.

This experiment decomposes the insulin delivered during correction events into:
  1. User correction bolus
  2. Controller SMBs
  3. Excess basal (temp basal above/below scheduled)
  4. Scheduled basal

Then attributes the BG drop to each component and computes a controller-
deconfounded ISF estimate.

Builds on:
  - Wave 12 (EXP-2741): Correction-only denominator closes 67% of profile gap
  - EXP-2664: Circadian demand-phase ISF profiling
  - EXP-2740: EGP-basal equilibrium residual (~0.05 mg/dL per 5min)

Hypotheses:
  H1: Controller insulin >30% of total during corrections
  H2: Controller-subtracted ISF >50% closer to profile than naive
  H3: Biphasic controller pattern: extra 0-2h, suspension 2-4h
  H4: Controller fraction varies by controller type
  H5: Unexplained residual <20% of total BG drop

Usage:
    python tools/cgmencode/exp_controller_decomposition_2753.py
"""

import json
import os
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats

# ─── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent
GRID_PATH = ROOT_DIR / "externals" / "ns-parquet" / "training" / "grid.parquet"
MANIFEST_PATH = ROOT_DIR / "externals" / "experiments" / "autoprepare-qualified.json"
RESULTS_PATH = ROOT_DIR / "externals" / "experiments" / "exp-2753_controller_decomposition.json"
VIZ_DIR = ROOT_DIR / "visualizations" / "controller-decomposition"
VIZ_PATH = VIZ_DIR / "controller_decomposition.png"

# ─── Constants ───────────────────────────────────────────────────────────────
STEPS_PER_HOUR = 12          # 5-minute intervals
STEP_MINUTES = 5
POST_WINDOW_HOURS = 4
POST_WINDOW_STEPS = POST_WINDOW_HOURS * STEPS_PER_HOUR  # 48 steps
PRIOR_CARB_WINDOW_HOURS = 2
PRIOR_CARB_STEPS = PRIOR_CARB_WINDOW_HOURS * STEPS_PER_HOUR  # 24 steps

# Correction event filters
MIN_BG_THRESHOLD = 180.0     # mg/dL — must be elevated
MIN_BOLUS_SIZE = 0.3         # U — minimum user bolus
MAX_COB_THRESHOLD = 5.0      # g — no significant carbs on board
MAX_CARB_SUM = 2.0           # g — no carbs in ±2h window
MIN_EVENTS_PER_PATIENT = 5   # minimum for inclusion

# Established coefficients (from prior experiments)
BOLUS_COEFF = -129.2         # mg/dL per U of bolus insulin
SMB_COEFF = -123.6           # mg/dL per U of SMB insulin
EXCESS_BASAL_COEFF = -130.5  # mg/dL per U of excess basal insulin

# EGP-basal residual from EXP-2740
EGP_RESIDUAL_PER_5MIN = 0.05  # mg/dL per 5-min step (net after scheduled basal)

# ISF sanity bounds
MIN_ISF = 5.0
MAX_ISF = 500.0


# ─── JSON Serializer ────────────────────────────────────────────────────────
def convert(obj):
    """Numpy-to-JSON serializer."""
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [convert(x) for x in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    raise TypeError(f"{type(obj)} not serializable")


# ─── Controller Detection ───────────────────────────────────────────────────
def detect_controller(pdf):
    """Detect controller type from available columns.

    Loop patients: have loop_enacted_rate but no sensitivity_ratio.
    Trio/OpenAPS patients: have sensitivity_ratio AND eventual_bg.
    """
    sr_frac = pdf["sensitivity_ratio"].notna().mean()
    loop_frac = pdf["loop_enacted_rate"].notna().mean()
    eb_frac = pdf["eventual_bg"].notna().mean()

    if sr_frac > 0.1 and eb_frac > 0.1:
        return "trio_openaps"
    elif loop_frac > 0.1:
        return "loop"
    else:
        return "unknown"


# ─── Scheduled Basal Estimation ──────────────────────────────────────────────
def estimate_scheduled_basal(pdf):
    """Estimate per-patient scheduled basal rate.

    Uses the scheduled_basal_rate column directly (median across all rows).
    Also computes a 'calm period' basal from net_basal during flat glucose
    periods with no bolus/SMB as a validation check.

    Returns:
        scheduled_rate: float — U/hr scheduled basal rate
        calm_net_basal_median: float — median net_basal during calm periods
    """
    # Primary: use scheduled_basal_rate column
    sbr = pdf["scheduled_basal_rate"].dropna()
    scheduled_rate = float(sbr.median()) if len(sbr) > 0 else 0.0

    # Validation: calm period net_basal should be near zero
    calm_mask = (
        (pdf["bolus"].fillna(0) == 0) &
        (pdf["bolus_smb"].fillna(0) == 0) &
        (pdf["glucose_roc"].fillna(0).abs() < 0.2)
    )
    calm_net = pdf.loc[calm_mask, "net_basal"]
    calm_net_median = float(calm_net.median()) if len(calm_net) > 100 else np.nan

    return scheduled_rate, calm_net_median


# ─── Correction Event Extraction ────────────────────────────────────────────
def extract_correction_events(pdf, scheduled_rate):
    """Extract correction events with insulin decomposition.

    Criteria:
      - BG >= 180 mg/dL
      - Manual bolus > 0.3 U
      - No carbs (carbs == 0 or cob < 5) at event and for 2h prior
      - Full 4h post-event window available

    For each event, decompose insulin in the 4h window into:
      - correction_insulin: user bolus at event time
      - smb_insulin: controller SMBs during 4h window
      - excess_basal_insulin: net_basal * 5/60 summed (+ or -)
      - scheduled_basal_insulin: scheduled_rate * 4h

    Returns list of event dicts.
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    n = len(pdf)

    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    bolus_smb = pdf["bolus_smb"].fillna(0).values.astype(np.float64)
    net_basal = pdf["net_basal"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    cob = pdf["cob"].fillna(0).values.astype(np.float64)
    glucose_roc = pdf["glucose_roc"].fillna(0).values.astype(np.float64)
    scheduled_isf_arr = pdf["scheduled_isf"].values.astype(np.float64)
    time_arr = pd.to_datetime(pdf["time"])

    events = []
    used_indices = set()

    for i in range(PRIOR_CARB_STEPS, n - POST_WINDOW_STEPS):
        # Filter 1: Minimum bolus size (user correction)
        if bolus[i] < MIN_BOLUS_SIZE:
            continue

        # Filter 2: BG must be elevated
        if np.isnan(glucose[i]) or glucose[i] < MIN_BG_THRESHOLD:
            continue

        # Filter 3: No significant COB
        if cob[i] > MAX_COB_THRESHOLD:
            continue

        # Filter 4: No carbs in prior 2h window or at event
        carb_start = max(0, i - PRIOR_CARB_STEPS)
        carb_sum = np.nansum(carbs[carb_start:i + 1])
        if carb_sum > MAX_CARB_SUM:
            continue

        # Filter 5: No carbs in post-event 2h (first half of window)
        post_carb_end = min(n, i + PRIOR_CARB_STEPS)
        post_carb_sum = np.nansum(carbs[i + 1:post_carb_end])
        if post_carb_sum > MAX_CARB_SUM:
            continue

        # Filter 6: Valid 4h glucose endpoint
        end_idx = i + POST_WINDOW_STEPS
        if end_idx >= n or np.isnan(glucose[end_idx]):
            # Try nearby indices
            found = False
            for offset in [-1, 1, -2, 2]:
                alt = end_idx + offset
                if 0 <= alt < n and not np.isnan(glucose[alt]):
                    end_idx = alt
                    found = True
                    break
            if not found:
                continue

        # Filter 7: No overlap with previous event (minimum 2h gap)
        if any(abs(i - ui) < PRIOR_CARB_STEPS for ui in used_indices):
            continue

        used_indices.add(i)

        # ─── Compute insulin components ─────────────────────────────
        window = slice(i, i + POST_WINDOW_STEPS)

        # User correction insulin (only the manual bolus at event time)
        correction_insulin = float(bolus[i])

        # Controller SMBs in 4h window (include those at event time too)
        smb_insulin = float(np.nansum(bolus_smb[i:i + POST_WINDOW_STEPS]))

        # Excess basal: net_basal is in U/hr, convert each 5-min step
        # net_basal = actual_rate - scheduled_rate (already a delta)
        excess_basal_per_step = net_basal[i:i + POST_WINDOW_STEPS] * (STEP_MINUTES / 60.0)
        excess_basal_insulin = float(np.nansum(excess_basal_per_step))

        # Scheduled basal over 4h
        scheduled_basal_insulin = scheduled_rate * POST_WINDOW_HOURS

        # Total
        actual_basal_insulin = scheduled_basal_insulin + excess_basal_insulin
        controller_insulin = smb_insulin + max(excess_basal_insulin, 0)
        total_insulin = correction_insulin + smb_insulin + actual_basal_insulin

        # ─── Compute BG drop ────────────────────────────────────────
        pre_bg = float(glucose[i])
        post_bg = float(glucose[end_idx])
        bg_drop = pre_bg - post_bg  # positive = BG fell

        # ─── Profile ISF for attribution ─────────────────────────────
        isf_profile = float(scheduled_isf_arr[i]) if not np.isnan(scheduled_isf_arr[i]) else np.nan
        # Use profile ISF (physiological sensitivity) for attributing BG
        # change to each insulin component. This avoids the overestimation
        # from regression coefficients (which capture marginal per-step effects).
        attr_isf = isf_profile if (not np.isnan(isf_profile) and isf_profile > 0) else 50.0

        # ─── BG attribution using profile ISF ────────────────────────
        # Only EXCESS insulin above the EGP-balanced baseline drives BG changes.
        # Scheduled basal ≈ EGP at steady state (they cancel).
        #
        # Three sources of excess insulin:
        #   1. Correction bolus (always positive, lowers BG)
        #   2. Controller SMBs (positive, lowers BG)
        #   3. Excess basal (signed: + = extra lowers BG; - = suspension raises BG)
        correction_bg_drop = correction_insulin * attr_isf   # positive = lowers BG
        smb_bg_drop = smb_insulin * attr_isf                 # positive = lowers BG
        excess_basal_bg_drop = excess_basal_insulin * attr_isf  # signed

        # EGP residual contribution over 4h (small, raises BG)
        egp_contribution = EGP_RESIDUAL_PER_5MIN * POST_WINDOW_STEPS  # positive mg/dL

        # Predicted BG drop = sum of excess insulin effects - EGP residual
        predicted_bg_drop = correction_bg_drop + smb_bg_drop + excess_basal_bg_drop - egp_contribution

        # ─── Insulin volume fractions (of total excess insulin) ──────
        # Total excess insulin = correction + SMBs + net_basal delta
        total_excess_insulin = correction_insulin + smb_insulin + excess_basal_insulin

        if total_excess_insulin > 0.01:
            correction_insulin_frac = correction_insulin / total_excess_insulin
            smb_insulin_frac = smb_insulin / total_excess_insulin
            excess_basal_insulin_frac = excess_basal_insulin / total_excess_insulin
        else:
            correction_insulin_frac = smb_insulin_frac = excess_basal_insulin_frac = 0.0

        # BG-lowering component fractions (only positive contributors)
        total_lowering = correction_bg_drop + smb_bg_drop + max(excess_basal_bg_drop, 0)
        if total_lowering > 0.01:
            correction_frac = correction_bg_drop / total_lowering
            smb_frac = smb_bg_drop / total_lowering
            excess_frac = max(excess_basal_bg_drop, 0) / total_lowering
        else:
            correction_frac = smb_frac = excess_frac = 0.0

        # Suspension offset fraction: how much does suspension reduce the drop?
        if bg_drop > 0.01:
            suspension_offset_mg = max(-excess_basal_bg_drop, 0)  # only when suspending
            suspension_offset_frac = suspension_offset_mg / bg_drop
        else:
            suspension_offset_frac = 0.0

        # ─── ISF Estimates ───────────────────────────────────────────
        # Method 1: Naive ISF = total BG drop / total excess insulin
        if total_excess_insulin > 0.01 and bg_drop > 0:
            isf_naive = bg_drop / total_excess_insulin
        else:
            isf_naive = np.nan

        # Method 2: Correction-denominator ISF (EXP-2741 approach)
        # Uses only correction bolus in denominator
        if correction_insulin > 0 and bg_drop > 0:
            isf_correction_denom = bg_drop / correction_insulin
        else:
            isf_correction_denom = np.nan

        # Method 3: Controller-subtracted ISF
        # Subtract the controller's BG impact (SMBs + excess basal)
        # using profile ISF as the conversion factor
        controller_bg_effect = smb_bg_drop + excess_basal_bg_drop  # signed
        bg_drop_correction_only = bg_drop - controller_bg_effect + egp_contribution
        if correction_insulin > 0 and bg_drop_correction_only > 0:
            isf_controller_subtracted = bg_drop_correction_only / correction_insulin
        else:
            isf_controller_subtracted = np.nan

        # ─── Timeline data: per-step breakdown ─────────────────────
        timeline_smb = bolus_smb[i:i + POST_WINDOW_STEPS].tolist()
        timeline_net_basal = net_basal[i:i + POST_WINDOW_STEPS].tolist()
        timeline_glucose = glucose[i:i + POST_WINDOW_STEPS].tolist()

        events.append({
            "index": int(i),
            "time": str(time_arr.iloc[i]),
            "pre_bg": pre_bg,
            "post_bg": post_bg,
            "bg_drop": bg_drop,
            # Insulin components (volumes in U)
            "correction_insulin": correction_insulin,
            "smb_insulin": smb_insulin,
            "excess_basal_insulin": excess_basal_insulin,
            "scheduled_basal_insulin": scheduled_basal_insulin,
            "actual_basal_insulin": actual_basal_insulin,
            "controller_insulin": controller_insulin,
            "total_insulin": total_insulin,
            "total_excess_insulin": float(total_excess_insulin),
            # BG attribution (profile-ISF based, excess-only model)
            "attr_isf_used": float(attr_isf),
            "correction_bg_drop": float(correction_bg_drop),
            "smb_bg_drop": float(smb_bg_drop),
            "excess_basal_bg_drop": float(excess_basal_bg_drop),
            "egp_contribution": float(egp_contribution),
            "predicted_bg_drop": float(predicted_bg_drop),
            "controller_bg_effect": float(controller_bg_effect),
            "bg_drop_correction_only": float(bg_drop_correction_only),
            # Fractions
            "correction_fraction": float(correction_frac),
            "smb_fraction": float(smb_frac),
            "excess_basal_fraction": float(excess_frac),
            "correction_insulin_frac": float(correction_insulin_frac),
            "smb_insulin_frac": float(smb_insulin_frac),
            "excess_basal_insulin_frac": float(excess_basal_insulin_frac),
            "suspension_offset_fraction": float(suspension_offset_frac),
            # ISF estimates
            "isf_naive": float(isf_naive) if not np.isnan(isf_naive) else None,
            "isf_correction_denom": float(isf_correction_denom) if not np.isnan(isf_correction_denom) else None,
            "isf_controller_subtracted": float(isf_controller_subtracted) if not np.isnan(isf_controller_subtracted) else None,
            "isf_profile": float(isf_profile) if not np.isnan(isf_profile) else None,
            # Timeline (for aggregation)
            "timeline_smb": timeline_smb,
            "timeline_net_basal": timeline_net_basal,
            "timeline_glucose": timeline_glucose,
        })

    return events


# ─── Per-Patient Analysis ────────────────────────────────────────────────────
def analyze_patient(pdf, patient_id):
    """Run full correction event decomposition for one patient."""
    print(f"  Processing {patient_id} ({len(pdf)} rows)...", end=" ")

    controller = detect_controller(pdf)
    scheduled_rate, calm_net_median = estimate_scheduled_basal(pdf)

    events = extract_correction_events(pdf, scheduled_rate)
    n_events = len(events)
    print(f"{n_events} correction events, controller={controller}")

    if n_events < MIN_EVENTS_PER_PATIENT:
        return None

    # ─── Aggregate event statistics ──────────────────────────────
    correction_insulins = [e["correction_insulin"] for e in events]
    smb_insulins = [e["smb_insulin"] for e in events]
    excess_basals = [e["excess_basal_insulin"] for e in events]
    sched_basals = [e["scheduled_basal_insulin"] for e in events]
    total_insulins = [e["total_insulin"] for e in events]
    bg_drops = [e["bg_drop"] for e in events]

    # Fractions
    corr_fracs = [e["correction_fraction"] for e in events]
    smb_fracs = [e["smb_fraction"] for e in events]
    excess_fracs = [e["excess_basal_fraction"] for e in events]
    suspension_fracs = [e["suspension_offset_fraction"] for e in events]

    # ISF values (filter valid)
    isf_naive_vals = [e["isf_naive"] for e in events if e["isf_naive"] is not None
                      and MIN_ISF < e["isf_naive"] < MAX_ISF]
    isf_corr_vals = [e["isf_correction_denom"] for e in events if e["isf_correction_denom"] is not None
                     and MIN_ISF < e["isf_correction_denom"] < MAX_ISF]
    isf_sub_vals = [e["isf_controller_subtracted"] for e in events
                    if e["isf_controller_subtracted"] is not None
                    and MIN_ISF < e["isf_controller_subtracted"] < MAX_ISF]
    isf_profile_vals = [e["isf_profile"] for e in events if e["isf_profile"] is not None
                        and MIN_ISF < e["isf_profile"] < MAX_ISF]

    # Controller fraction of EXCESS insulin (above baseline)
    ctrl_fractions = []
    for e in events:
        total_excess = e.get("total_excess_insulin", 0)
        if total_excess > 0.01:
            ctrl_excess = e["smb_insulin"] + e["excess_basal_insulin"]
            ctrl_fractions.append(ctrl_excess / total_excess)

    # ─── Timeline aggregation ────────────────────────────────────
    # Average SMB and net_basal per time step across events
    timeline_smb_matrix = np.array([e["timeline_smb"] for e in events])
    timeline_nb_matrix = np.array([e["timeline_net_basal"] for e in events])

    avg_smb_timeline = np.nanmean(timeline_smb_matrix, axis=0).tolist()
    avg_nb_timeline = np.nanmean(timeline_nb_matrix, axis=0).tolist()

    # ─── BG decomposition accounting ────────────────────────────
    observed_drops = [e["bg_drop"] for e in events]
    predicted_drops = [e["predicted_bg_drop"] for e in events]
    residuals = [o - p for o, p in zip(observed_drops, predicted_drops)]
    residual_fracs = []
    for o, r in zip(observed_drops, residuals):
        if abs(o) > 1:
            residual_fracs.append(abs(r) / abs(o))

    # ─── ISF gap closure analysis ────────────────────────────────
    if isf_profile_vals and isf_naive_vals and isf_sub_vals:
        median_profile = np.median(isf_profile_vals)
        median_naive = np.median(isf_naive_vals)
        median_corr = np.median(isf_corr_vals) if isf_corr_vals else np.nan
        median_sub = np.median(isf_sub_vals)

        profile_naive_gap = abs(median_profile - median_naive)
        if profile_naive_gap > 0.01:
            corr_denom_closure = 1.0 - abs(median_profile - median_corr) / profile_naive_gap if not np.isnan(median_corr) else np.nan
            ctrl_sub_closure = 1.0 - abs(median_profile - median_sub) / profile_naive_gap
        else:
            corr_denom_closure = np.nan
            ctrl_sub_closure = np.nan
    else:
        median_profile = median_naive = median_corr = median_sub = np.nan
        profile_naive_gap = corr_denom_closure = ctrl_sub_closure = np.nan

    return {
        "patient_id": patient_id,
        "controller": controller,
        "n_events": n_events,
        "scheduled_basal_rate": scheduled_rate,
        "calm_net_basal_median": float(calm_net_median) if not np.isnan(calm_net_median) else None,
        # Insulin summary
        "mean_correction_insulin": float(np.mean(correction_insulins)),
        "mean_smb_insulin": float(np.mean(smb_insulins)),
        "mean_excess_basal_insulin": float(np.mean(excess_basals)),
        "mean_scheduled_basal_insulin": float(np.mean(sched_basals)),
        "mean_total_insulin": float(np.mean(total_insulins)),
        "mean_bg_drop": float(np.mean(bg_drops)),
        # Fractions (of BG-lowering only, excludes EGP-balanced scheduled basal)
        "mean_correction_fraction": float(np.mean(corr_fracs)),
        "mean_smb_fraction": float(np.mean(smb_fracs)),
        "mean_excess_basal_fraction": float(np.mean(excess_fracs)),
        "mean_suspension_offset_fraction": float(np.mean(suspension_fracs)),
        # Controller fraction of excess insulin
        "mean_controller_fraction_of_excess": float(np.mean(ctrl_fractions)) if ctrl_fractions else None,
        "median_controller_fraction_of_excess": float(np.median(ctrl_fractions)) if ctrl_fractions else None,
        # ISF summary
        "isf_naive_median": float(np.median(isf_naive_vals)) if isf_naive_vals else None,
        "isf_naive_p25": float(np.percentile(isf_naive_vals, 25)) if isf_naive_vals else None,
        "isf_naive_p75": float(np.percentile(isf_naive_vals, 75)) if isf_naive_vals else None,
        "isf_correction_denom_median": float(np.median(isf_corr_vals)) if isf_corr_vals else None,
        "isf_controller_subtracted_median": float(np.median(isf_sub_vals)) if isf_sub_vals else None,
        "isf_profile_median": float(np.median(isf_profile_vals)) if isf_profile_vals else None,
        "n_isf_naive": len(isf_naive_vals),
        "n_isf_corr_denom": len(isf_corr_vals),
        "n_isf_ctrl_sub": len(isf_sub_vals),
        # Gap closure
        "profile_naive_gap": float(profile_naive_gap) if not np.isnan(profile_naive_gap) else None,
        "corr_denom_gap_closure": float(corr_denom_closure) if not np.isnan(corr_denom_closure) else None,
        "ctrl_sub_gap_closure": float(ctrl_sub_closure) if not np.isnan(ctrl_sub_closure) else None,
        # BG accounting
        "mean_observed_drop": float(np.mean(observed_drops)),
        "mean_predicted_drop": float(np.mean(predicted_drops)),
        "mean_residual": float(np.mean(residuals)),
        "mean_residual_fraction": float(np.mean(residual_fracs)) if residual_fracs else None,
        # Timeline
        "avg_smb_timeline": avg_smb_timeline,
        "avg_net_basal_timeline": avg_nb_timeline,
        # Raw events (for JSON export)
        "events": events,
    }


# ─── Cross-Patient Aggregation ───────────────────────────────────────────────
def aggregate_results(patient_results):
    """Compute cross-patient statistics."""
    n_patients = len(patient_results)
    if n_patients == 0:
        return {}

    # Collect per-patient medians
    all_ctrl_fracs = [r["mean_controller_fraction_of_excess"] for r in patient_results
                      if r["mean_controller_fraction_of_excess"] is not None]
    all_corr_fracs = [r["mean_correction_fraction"] for r in patient_results]
    all_smb_fracs = [r["mean_smb_fraction"] for r in patient_results]
    all_excess_fracs = [r["mean_excess_basal_fraction"] for r in patient_results]
    all_suspension_fracs = [r["mean_suspension_offset_fraction"] for r in patient_results]

    # ISF gap closure
    corr_closures = [r["corr_denom_gap_closure"] for r in patient_results
                     if r["corr_denom_gap_closure"] is not None]
    ctrl_closures = [r["ctrl_sub_gap_closure"] for r in patient_results
                     if r["ctrl_sub_gap_closure"] is not None]

    # Residual fractions
    residual_fracs = [r["mean_residual_fraction"] for r in patient_results
                      if r["mean_residual_fraction"] is not None]

    # Controller type breakdown
    by_controller = defaultdict(list)
    for r in patient_results:
        by_controller[r["controller"]].append(r)

    controller_summary = {}
    for ctype, rs in by_controller.items():
        cfracs = [r["mean_controller_fraction_of_excess"] for r in rs
                  if r["mean_controller_fraction_of_excess"] is not None]
        controller_summary[ctype] = {
            "n_patients": len(rs),
            "total_events": sum(r["n_events"] for r in rs),
            "mean_controller_fraction": float(np.mean(cfracs)) if cfracs else None,
            "median_controller_fraction": float(np.median(cfracs)) if cfracs else None,
            "mean_correction_fraction": float(np.mean([r["mean_correction_fraction"] for r in rs])),
            "mean_smb_fraction": float(np.mean([r["mean_smb_fraction"] for r in rs])),
            "mean_excess_basal_fraction": float(np.mean([r["mean_excess_basal_fraction"] for r in rs])),
            "mean_suspension_offset_fraction": float(np.mean([r["mean_suspension_offset_fraction"] for r in rs])),
        }

    # Timeline aggregation across patients
    all_smb_timelines = []
    all_nb_timelines = []
    for r in patient_results:
        if r["avg_smb_timeline"]:
            all_smb_timelines.append(r["avg_smb_timeline"])
        if r["avg_net_basal_timeline"]:
            all_nb_timelines.append(r["avg_net_basal_timeline"])

    pop_smb_timeline = np.nanmean(np.array(all_smb_timelines), axis=0).tolist() if all_smb_timelines else []
    pop_nb_timeline = np.nanmean(np.array(all_nb_timelines), axis=0).tolist() if all_nb_timelines else []

    # ─── Hypothesis Testing ──────────────────────────────────────
    # H1: Controller insulin >30% of total excess insulin
    h1_values = all_ctrl_fracs
    h1_median = float(np.median(h1_values)) if h1_values else 0
    h1_result = h1_median > 0.30
    h1_ci = _bootstrap_ci(h1_values) if len(h1_values) >= 3 else (np.nan, np.nan)

    # H2: Controller-subtracted ISF >50% closer to profile
    h2_values = ctrl_closures
    h2_corr_values = corr_closures
    h2_median = float(np.median(h2_values)) if h2_values else 0
    h2_corr_median = float(np.median(h2_corr_values)) if h2_corr_values else 0
    h2_result = h2_median > 0.50 if h2_values else False
    h2_improvement = h2_median - h2_corr_median if h2_values and h2_corr_values else np.nan

    # H3: Biphasic pattern — less suspension (or extra) early, more suspension late
    # During corrections, controllers typically suspend basal (net_basal < 0).
    # Biphasic = less suspension early (allowing correction), more suspension late (preventing low).
    if pop_nb_timeline and len(pop_nb_timeline) == POST_WINDOW_STEPS:
        first_half = np.mean(pop_nb_timeline[:24])  # 0-2h
        second_half = np.mean(pop_nb_timeline[24:])  # 2-4h
        # Biphasic: first half is less negative (or positive) than second half
        h3_result = bool(first_half > second_half)
        h3_first_half = float(first_half)
        h3_second_half = float(second_half)
    else:
        h3_result = False
        h3_first_half = h3_second_half = np.nan

    # H4: Controller fraction varies by controller type
    if len(by_controller) >= 2:
        groups = []
        for ctype in sorted(by_controller.keys()):
            g = [r["mean_controller_fraction_of_excess"] for r in by_controller[ctype]
                 if r["mean_controller_fraction_of_excess"] is not None]
            if g:
                groups.append(g)
        if len(groups) >= 2 and all(len(g) >= 2 for g in groups):
            if len(groups) == 2:
                # Use Mann-Whitney U since small samples
                try:
                    stat, pval = stats.mannwhitneyu(groups[0], groups[1], alternative="two-sided")
                    h4_result = bool(pval < 0.10)
                    h4_pvalue = float(pval)
                except Exception:
                    h4_result = False
                    h4_pvalue = np.nan
            else:
                try:
                    stat, pval = stats.kruskal(*groups)
                    h4_result = bool(pval < 0.10)
                    h4_pvalue = float(pval)
                except Exception:
                    h4_result = False
                    h4_pvalue = np.nan
        else:
            h4_result = False
            h4_pvalue = np.nan
    else:
        h4_result = False
        h4_pvalue = np.nan

    # H5: Unexplained residual < 20%
    h5_median = float(np.median(residual_fracs)) if residual_fracs else 1.0
    h5_result = h5_median < 0.20

    return {
        "n_patients": n_patients,
        "total_events": sum(r["n_events"] for r in patient_results),
        # Population insulin fractions
        "population_correction_fraction": float(np.mean(all_corr_fracs)),
        "population_smb_fraction": float(np.mean(all_smb_fracs)),
        "population_excess_basal_fraction": float(np.mean(all_excess_fracs)),
        "population_suspension_offset_fraction": float(np.mean(all_suspension_fracs)),
        "population_controller_fraction_of_excess": float(np.median(all_ctrl_fracs)) if all_ctrl_fracs else None,
        # ISF gap closure
        "median_corr_denom_gap_closure": float(np.median(corr_closures)) if corr_closures else None,
        "median_ctrl_sub_gap_closure": float(np.median(ctrl_closures)) if ctrl_closures else None,
        # Residual
        "median_residual_fraction": float(np.median(residual_fracs)) if residual_fracs else None,
        # Controller breakdown
        "by_controller": controller_summary,
        # Timeline (population average)
        "pop_smb_timeline": pop_smb_timeline,
        "pop_net_basal_timeline": pop_nb_timeline,
        # Hypotheses
        "hypotheses": {
            "H1_controller_gt_30pct": {
                "description": "Controller-initiated insulin >30% of total during corrections",
                "result": h1_result,
                "median_controller_fraction": h1_median,
                "ci_95": [float(h1_ci[0]), float(h1_ci[1])] if not np.isnan(h1_ci[0]) else None,
                "verdict": "SUPPORTED" if h1_result else "NOT SUPPORTED",
            },
            "H2_ctrl_sub_gt_50pct_closure": {
                "description": "Controller-subtracted ISF >50% closer to profile than naive",
                "result": h2_result,
                "median_ctrl_sub_closure": h2_median,
                "median_corr_denom_closure": h2_corr_median,
                "improvement_over_corr_denom": float(h2_improvement) if not np.isnan(h2_improvement) else None,
                "verdict": "SUPPORTED" if h2_result else "NOT SUPPORTED",
            },
            "H3_biphasic_pattern": {
                "description": "Controller shows biphasic: extra insulin 0-2h, suspension 2-4h",
                "result": h3_result,
                "first_half_mean_net_basal": float(h3_first_half) if not np.isnan(h3_first_half) else None,
                "second_half_mean_net_basal": float(h3_second_half) if not np.isnan(h3_second_half) else None,
                "verdict": "SUPPORTED" if h3_result else "NOT SUPPORTED",
            },
            "H4_controller_type_varies": {
                "description": "Controller fraction differs by controller type (Loop vs Trio/OpenAPS)",
                "result": h4_result,
                "p_value": float(h4_pvalue) if not np.isnan(h4_pvalue) else None,
                "verdict": "SUPPORTED" if h4_result else "NOT SUPPORTED",
            },
            "H5_residual_lt_20pct": {
                "description": "Unexplained residual <20% of total BG drop",
                "result": h5_result,
                "median_residual_fraction": h5_median,
                "verdict": "SUPPORTED" if h5_result else "NOT SUPPORTED",
            },
        },
    }


def _bootstrap_ci(values, n_boot=2000, alpha=0.05):
    """Bootstrap confidence interval for the median."""
    if len(values) < 3:
        return (np.nan, np.nan)
    values = np.array(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(42)
    boots = []
    for _ in range(n_boot):
        sample = rng.choice(values, size=len(values), replace=True)
        boots.append(np.median(sample))
    lo = np.percentile(boots, 100 * alpha / 2)
    hi = np.percentile(boots, 100 * (1 - alpha / 2))
    return (float(lo), float(hi))


# ─── Visualization ───────────────────────────────────────────────────────────
def create_visualization(patient_results, cross_patient, output_path):
    """Create 2×3 panel visualization."""
    fig = plt.figure(figsize=(20, 13))
    gs = gridspec.GridSpec(2, 3, hspace=0.35, wspace=0.35)

    colors = {
        "correction": "#2196F3",
        "smb": "#FF9800",
        "excess_basal": "#E91E63",
        "scheduled_basal": "#9E9E9E",
        "egp": "#4CAF50",
        "residual": "#795548",
    }

    # ─── Panel 1: BG-lowering attribution pie chart ────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    corr_frac = cross_patient["population_correction_fraction"]
    smb_frac = cross_patient["population_smb_fraction"]
    excess_frac = cross_patient["population_excess_basal_fraction"]
    susp_frac = cross_patient["population_suspension_offset_fraction"]

    fracs = [corr_frac, smb_frac, excess_frac]
    labels_pie = ["Correction\nBolus", "Controller\nSMBs", "Excess Basal\n(temp increase)"]
    pie_colors = [colors["correction"], colors["smb"], colors["excess_basal"]]

    # Filter out zero/negative fractions
    valid = [(f, l, c) for f, l, c in zip(fracs, labels_pie, pie_colors) if f > 0.001]
    if valid:
        vf, vl, vc = zip(*valid)
        wedges, texts, autotexts = ax1.pie(
            vf, labels=vl, colors=vc, autopct="%1.1f%%",
            startangle=90, pctdistance=0.75,
            textprops={"fontsize": 9}
        )
        for at in autotexts:
            at.set_fontweight("bold")
    # Add annotation about suspension
    ax1.text(0, -1.3, f"Basal suspension offsets {susp_frac:.0%} of drop",
             ha="center", fontsize=8, style="italic", color="gray")
    ax1.set_title("BG-Lowering Attribution\n(Excess Insulin Only, EGP-Balanced)", fontsize=11, fontweight="bold")

    # ─── Panel 2: Controller timeline ────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    timeline = cross_patient.get("pop_net_basal_timeline", [])
    smb_timeline = cross_patient.get("pop_smb_timeline", [])
    if timeline and len(timeline) == POST_WINDOW_STEPS:
        hours = np.arange(POST_WINDOW_STEPS) * STEP_MINUTES / 60.0
        ax2.fill_between(hours, 0, timeline, where=np.array(timeline) > 0,
                         alpha=0.4, color=colors["excess_basal"], label="Excess basal (+)")
        ax2.fill_between(hours, 0, timeline, where=np.array(timeline) <= 0,
                         alpha=0.4, color="#64B5F6", label="Basal suspension (-)")
        ax2.plot(hours, timeline, color=colors["excess_basal"], linewidth=1.5)
        if smb_timeline and len(smb_timeline) == POST_WINDOW_STEPS:
            ax2_twin = ax2.twinx()
            ax2_twin.bar(hours, smb_timeline, width=0.07, alpha=0.6,
                         color=colors["smb"], label="SMBs")
            ax2_twin.set_ylabel("SMB dose (U)", fontsize=9, color=colors["smb"])
            ax2_twin.tick_params(axis="y", labelcolor=colors["smb"])
        ax2.axhline(0, color="black", linewidth=0.5, linestyle="--")
        ax2.axvline(2.0, color="gray", linewidth=0.8, linestyle=":", label="2h mark")
        ax2.set_xlabel("Hours since correction bolus", fontsize=9)
        ax2.set_ylabel("Net basal excess (U/hr)", fontsize=9)
        ax2.legend(loc="upper right", fontsize=7)
    ax2.set_title("Controller Response Timeline\n(Avg Across Events)", fontsize=11, fontweight="bold")

    # ─── Panel 3: ISF method comparison (box plots) ──────────────
    ax3 = fig.add_subplot(gs[0, 2])
    isf_data = {"Naive": [], "Corr-Denom": [], "Ctrl-Sub": [], "Profile": []}
    for r in patient_results:
        for e in r["events"]:
            if e["isf_naive"] is not None and MIN_ISF < e["isf_naive"] < MAX_ISF:
                isf_data["Naive"].append(e["isf_naive"])
            if e["isf_correction_denom"] is not None and MIN_ISF < e["isf_correction_denom"] < MAX_ISF:
                isf_data["Corr-Denom"].append(e["isf_correction_denom"])
            if e["isf_controller_subtracted"] is not None and MIN_ISF < e["isf_controller_subtracted"] < MAX_ISF:
                isf_data["Ctrl-Sub"].append(e["isf_controller_subtracted"])
            if e["isf_profile"] is not None and MIN_ISF < e["isf_profile"] < MAX_ISF:
                isf_data["Profile"].append(e["isf_profile"])

    box_data = []
    box_labels = []
    box_colors = []
    method_colors = ["#EF5350", "#FFA726", "#66BB6A", "#42A5F5"]
    for (label, vals), clr in zip(isf_data.items(), method_colors):
        if vals:
            box_data.append(vals)
            box_labels.append(f"{label}\n(n={len(vals)})")
            box_colors.append(clr)

    if box_data:
        bp = ax3.boxplot(box_data, tick_labels=box_labels, patch_artist=True,
                         showfliers=False, widths=0.6)
        for patch, clr in zip(bp["boxes"], box_colors):
            patch.set_facecolor(clr)
            patch.set_alpha(0.6)
        # Add median line for profile
        if isf_data["Profile"]:
            ax3.axhline(np.median(isf_data["Profile"]), color="#42A5F5",
                        linewidth=1.5, linestyle="--", alpha=0.7, label="Profile median")
            ax3.legend(fontsize=8)
    ax3.set_ylabel("ISF (mg/dL per U)", fontsize=9)
    ax3.set_title("ISF Method Comparison", fontsize=11, fontweight="bold")

    # ─── Panel 4: Controller fraction by type ────────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    by_ctrl = cross_patient.get("by_controller", {})
    if by_ctrl:
        ctrl_types = sorted(by_ctrl.keys())
        x_pos = np.arange(len(ctrl_types))
        width = 0.2

        corr_vals = [by_ctrl[ct]["mean_correction_fraction"] for ct in ctrl_types]
        smb_vals = [by_ctrl[ct]["mean_smb_fraction"] for ct in ctrl_types]
        excess_vals = [by_ctrl[ct]["mean_excess_basal_fraction"] for ct in ctrl_types]

        ax4.bar(x_pos - width, corr_vals, width, label="Correction",
                color=colors["correction"], alpha=0.8)
        ax4.bar(x_pos, smb_vals, width, label="SMBs",
                color=colors["smb"], alpha=0.8)
        ax4.bar(x_pos + width, excess_vals, width, label="Excess Basal",
                color=colors["excess_basal"], alpha=0.8)

        ax4.set_xticks(x_pos)
        labels_ctrl = []
        for ct in ctrl_types:
            n = by_ctrl[ct]["n_patients"]
            nevt = by_ctrl[ct]["total_events"]
            labels_ctrl.append(f"{ct}\n(n={n}, {nevt} events)")
        ax4.set_xticklabels(labels_ctrl, fontsize=9)
        ax4.set_ylabel("Fraction of BG Drop", fontsize=9)
        ax4.legend(fontsize=8)
    ax4.set_title("Controller Fraction by Type", fontsize=11, fontweight="bold")

    # ─── Panel 5: BG drop waterfall ──────────────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    # Compute population-average BG drop waterfall (EGP-equilibrium model)
    avg_bg_drop = np.mean([r["mean_observed_drop"] for r in patient_results])
    avg_corr_drop = np.mean([np.mean([e["correction_bg_drop"] for e in r["events"]])
                             for r in patient_results])
    avg_smb_drop = np.mean([np.mean([e["smb_bg_drop"] for e in r["events"]])
                            for r in patient_results])
    # excess_basal_bg_drop is signed (negative = suspension raises BG)
    avg_excess_drop = np.mean([np.mean([e["excess_basal_bg_drop"] for e in r["events"]])
                               for r in patient_results])
    avg_egp = EGP_RESIDUAL_PER_5MIN * POST_WINDOW_STEPS
    predicted_sum = avg_corr_drop + avg_smb_drop + avg_excess_drop - avg_egp
    residual = avg_bg_drop - predicted_sum

    waterfall_labels = ["Correction\nBolus", "Controller\nSMBs", "Excess Basal\n(net, incl susp)",
                        "EGP\nresidual", "Residual\n(unexplained)", "Observed\nDrop"]
    waterfall_vals = [avg_corr_drop, avg_smb_drop, avg_excess_drop,
                      -avg_egp, residual, avg_bg_drop]
    waterfall_colors = [colors["correction"], colors["smb"], colors["excess_basal"],
                        colors["egp"], colors["residual"], "black"]

    # Cumulative waterfall
    cumulative = 0
    bottoms = []
    heights = []
    for j, v in enumerate(waterfall_vals[:-1]):
        bottoms.append(cumulative)
        heights.append(v)
        cumulative += v

    # Waterfall bars
    bar_colors = []
    for j, h in enumerate(heights):
        if h < 0:
            bar_colors.append("#81C784" if j != len(heights) - 1 else colors["residual"])
        else:
            bar_colors.append(waterfall_colors[j])

    for j, (b, h) in enumerate(zip(bottoms, heights)):
        ax5.bar(j, h, bottom=b, color=waterfall_colors[j], alpha=0.8,
                edgecolor="white", linewidth=0.5)
        label_y = b + h / 2
        ax5.text(j, label_y, f"{h:+.0f}", ha="center", va="center",
                 fontsize=8, fontweight="bold")

    # Observed drop bar
    ax5.bar(len(waterfall_labels) - 1, avg_bg_drop, color="black", alpha=0.3,
            edgecolor="black", linewidth=1.5)
    ax5.text(len(waterfall_labels) - 1, avg_bg_drop / 2, f"{avg_bg_drop:.0f}",
             ha="center", va="center", fontsize=8, fontweight="bold", color="white")

    ax5.set_xticks(range(len(waterfall_labels)))
    ax5.set_xticklabels(waterfall_labels, fontsize=8, rotation=15)
    ax5.set_ylabel("BG Impact (mg/dL)", fontsize=9)
    ax5.axhline(0, color="black", linewidth=0.5)
    ax5.set_title("BG Drop Waterfall\n(EGP-Equilibrium Model)", fontsize=11, fontweight="bold")

    # ─── Panel 6: Per-patient gap closure ────────────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    patient_ids = []
    corr_denom_closures = []
    ctrl_sub_closures = []
    for r in patient_results:
        if r["corr_denom_gap_closure"] is not None and r["ctrl_sub_gap_closure"] is not None:
            short_id = r["patient_id"][:8]
            patient_ids.append(short_id)
            corr_denom_closures.append(r["corr_denom_gap_closure"] * 100)
            ctrl_sub_closures.append(r["ctrl_sub_gap_closure"] * 100)

    if patient_ids:
        x = np.arange(len(patient_ids))
        width = 0.35
        ax6.bar(x - width / 2, corr_denom_closures, width, label="Corr-Denom",
                color="#FFA726", alpha=0.8)
        ax6.bar(x + width / 2, ctrl_sub_closures, width, label="Ctrl-Subtracted",
                color="#66BB6A", alpha=0.8)
        ax6.set_xticks(x)
        ax6.set_xticklabels(patient_ids, fontsize=7, rotation=45, ha="right")
        ax6.axhline(50, color="red", linewidth=0.8, linestyle="--", alpha=0.5, label="50% target")
        ax6.axhline(100, color="green", linewidth=0.8, linestyle="--", alpha=0.3)
        ax6.set_ylabel("Gap Closure (%)", fontsize=9)
        ax6.legend(fontsize=7, loc="best")
    ax6.set_title("Per-Patient ISF Gap Closure", fontsize=11, fontweight="bold")

    # ─── Main title ──────────────────────────────────────────────
    fig.suptitle("EXP-2753: Controller Response Decomposition During Corrections",
                 fontsize=14, fontweight="bold", y=0.98)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\n  Visualization saved to {output_path}")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("EXP-2753: Controller Response Decomposition")
    print("=" * 72)
    timestamp = datetime.now(tz=None).astimezone().isoformat()

    # ─── Load data ───────────────────────────────────────────────
    print("\n[1/6] Loading data...")
    grid = pd.read_parquet(GRID_PATH)
    manifest = json.load(open(MANIFEST_PATH))
    qualified = manifest["qualified_patients"]
    print(f"  Grid: {grid.shape[0]} rows, {grid.shape[1]} columns")
    print(f"  Qualified patients: {len(qualified)}")

    # ─── Process each patient ────────────────────────────────────
    print("\n[2/6] Extracting correction events and decomposing insulin...")
    patient_results = []
    skipped = []
    for pid in sorted(qualified):
        pdf = grid[grid["patient_id"] == pid].copy()
        if len(pdf) < 1000:
            print(f"  Skipping {pid}: too few rows ({len(pdf)})")
            skipped.append({"patient_id": pid, "reason": "too_few_rows", "n_rows": len(pdf)})
            continue

        try:
            result = analyze_patient(pdf, pid)
            if result is None:
                skipped.append({"patient_id": pid, "reason": f"<{MIN_EVENTS_PER_PATIENT} events"})
            else:
                patient_results.append(result)
        except Exception as exc:
            print(f"  ERROR on {pid}: {exc}")
            traceback.print_exc()
            skipped.append({"patient_id": pid, "reason": str(exc)})

    print(f"\n  Qualifying patients: {len(patient_results)}")
    print(f"  Skipped: {len(skipped)}")
    for s in skipped:
        print(f"    {s['patient_id']}: {s['reason']}")

    if len(patient_results) == 0:
        print("\nERROR: No qualifying patients. Exiting.")
        sys.exit(1)

    # ─── Cross-patient aggregation ───────────────────────────────
    print("\n[3/6] Computing cross-patient statistics...")
    cross_patient = aggregate_results(patient_results)

    # ─── Print results ───────────────────────────────────────────
    print("\n[4/6] Results Summary")
    print("-" * 60)
    total_events = cross_patient["total_events"]
    print(f"  Total correction events: {total_events}")
    print(f"  Patients analyzed: {cross_patient['n_patients']}")

    print(f"\n  Population BG-Lowering Attribution (excess insulin only, EGP-balanced):")
    print(f"    Correction bolus:   {cross_patient['population_correction_fraction']:.1%}")
    print(f"    Controller SMBs:    {cross_patient['population_smb_fraction']:.1%}")
    print(f"    Excess basal (+):   {cross_patient['population_excess_basal_fraction']:.1%}")
    print(f"    Basal suspension offsets: {cross_patient['population_suspension_offset_fraction']:.1%} of BG drop")

    ctrl_frac = cross_patient.get("population_controller_fraction_of_excess")
    if ctrl_frac is not None:
        print(f"\n  Controller fraction of excess insulin: {ctrl_frac:.1%}")

    print(f"\n  ISF Gap Closure:")
    cc = cross_patient.get("median_corr_denom_gap_closure")
    cs = cross_patient.get("median_ctrl_sub_gap_closure")
    if cc is not None:
        print(f"    Correction-denominator: {cc:.1%}")
    if cs is not None:
        print(f"    Controller-subtracted:  {cs:.1%}")

    print(f"\n  Residual (unexplained):")
    rf = cross_patient.get("median_residual_fraction")
    if rf is not None:
        print(f"    Median residual fraction: {rf:.1%}")

    print(f"\n  Controller breakdown:")
    for ctype, info in cross_patient.get("by_controller", {}).items():
        print(f"    {ctype}: {info['n_patients']} patients, {info['total_events']} events, "
              f"ctrl_frac={info.get('median_controller_fraction', 'N/A')}")

    # ─── Hypothesis verdicts ─────────────────────────────────────
    print("\n[5/6] Hypothesis Verdicts")
    print("-" * 60)
    hyps = cross_patient.get("hypotheses", {})
    for hid, hdata in sorted(hyps.items()):
        verdict = hdata.get("verdict", "UNKNOWN")
        desc = hdata.get("description", "")
        print(f"  {hid}: {verdict}")
        print(f"    {desc}")
        # Print key metric
        for k, v in hdata.items():
            if k not in ("description", "result", "verdict"):
                if isinstance(v, float):
                    print(f"    {k}: {v:.4f}")
                elif v is not None:
                    print(f"    {k}: {v}")
        print()

    # ─── Create visualization ────────────────────────────────────
    print("[6/6] Creating visualization...")
    try:
        create_visualization(patient_results, cross_patient, str(VIZ_PATH))
    except Exception as exc:
        print(f"  WARNING: Visualization failed: {exc}")
        traceback.print_exc()

    # ─── Save JSON results ───────────────────────────────────────
    # Strip raw events from per-patient for export (keep timeline for synthesis)
    per_patient_export = {}
    for r in patient_results:
        pid = r["patient_id"]
        # Keep a summary, drop raw events to save space
        export = {k: v for k, v in r.items() if k != "events"}
        export["n_events"] = r["n_events"]
        # Keep summary event stats for synthesis
        export["event_summary"] = {
            "mean_pre_bg": float(np.mean([e["pre_bg"] for e in r["events"]])),
            "mean_post_bg": float(np.mean([e["post_bg"] for e in r["events"]])),
            "mean_bg_drop": float(np.mean([e["bg_drop"] for e in r["events"]])),
            "mean_correction_insulin": float(np.mean([e["correction_insulin"] for e in r["events"]])),
            "mean_smb_insulin": float(np.mean([e["smb_insulin"] for e in r["events"]])),
            "mean_excess_basal_insulin": float(np.mean([e["excess_basal_insulin"] for e in r["events"]])),
            "mean_total_insulin": float(np.mean([e["total_insulin"] for e in r["events"]])),
        }
        per_patient_export[pid] = export

    output = {
        "experiment": "EXP-2753",
        "title": "Controller Response Decomposition",
        "timestamp": timestamp,
        "description": (
            "Decomposes insulin during correction events into user bolus, "
            "controller SMBs, excess basal, and scheduled basal. Attributes "
            "BG drop to each component and computes controller-deconfounded ISF."
        ),
        "parameters": {
            "min_bg_threshold": MIN_BG_THRESHOLD,
            "min_bolus_size": MIN_BOLUS_SIZE,
            "max_cob_threshold": MAX_COB_THRESHOLD,
            "post_window_hours": POST_WINDOW_HOURS,
            "bolus_coeff": BOLUS_COEFF,
            "smb_coeff": SMB_COEFF,
            "excess_basal_coeff": EXCESS_BASAL_COEFF,
            "egp_residual_per_5min": EGP_RESIDUAL_PER_5MIN,
            "min_events_per_patient": MIN_EVENTS_PER_PATIENT,
        },
        "n_patients_qualified": len(patient_results),
        "n_patients_skipped": len(skipped),
        "skipped": skipped,
        "per_patient": per_patient_export,
        "cross_patient": cross_patient,
        "coefficients_used": {
            "BOLUS_COEFF": BOLUS_COEFF,
            "SMB_COEFF": SMB_COEFF,
            "EXCESS_BASAL_COEFF": EXCESS_BASAL_COEFF,
        },
        "controller_response_timeline": {
            "description": "Population-average controller response per 5-min step after correction bolus",
            "steps": POST_WINDOW_STEPS,
            "step_minutes": STEP_MINUTES,
            "smb_timeline": cross_patient.get("pop_smb_timeline", []),
            "net_basal_timeline": cross_patient.get("pop_net_basal_timeline", []),
        },
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"\n  Results saved to {RESULTS_PATH}")

    print("\n" + "=" * 72)
    print("EXP-2753 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
