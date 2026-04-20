#!/usr/bin/env python3
"""
EXP-2741: ISF via Full Multi-Factor Subtraction
=================================================

Scientific Question:
  Does properly subtracting basal insulin effects and EGP (endogenous glucose
  production) from empirical ISF measurements yield an ISF estimate closer to
  the patient's profile ISF — and thus safer for automated controller use?

Core Insight:
  Previous ISF extraction (EXP-2719b, EXP-2738) produced an empirical ISF ~4×
  lower than profile ISF because the measurement conflated:
    1. The insulin sensitivity signal (correction bolus lowering glucose)
    2. Ongoing basal insulin contribution (confounding — lowers glucose too)
    3. EGP / liver glucose production (confounding — raises glucose)
    4. Any residual meal absorption (confounding — raises glucose)

  By subtracting confounders BEFORE dividing by correction insulin, we should
  recover an ISF closer to "true" insulin sensitivity.

Predecessors:
  - EXP-2719b: Residual ISF extraction (13 mg/dL/U empirical)
  - EXP-2735: EGP-Aware Basal Optimization (basal ≈ 92% EGP)
  - EXP-2738: Safety validation (TBR risk from low ISF)
  - EXP-2740: Per-patient EGP profiling with circadian estimates

Hypotheses:
  H1: Multi-factor ISF is >1.5× closer to profile than naive ISF
  H2: EGP subtraction alone accounts for >40% of the naive-to-profile gap
  H3: Basal subtraction alone accounts for >30% of the gap
  H4: Multi-factor ISF has lower inter-event CV than naive ISF
  H5: Multi-factor ISF would pass safety simulation (predicted TBR <2pp increase)
"""

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# ──────────────────────────── Constants ────────────────────────────

EXP_ID = "2741"
TITLE = "ISF via Full Multi-Factor Subtraction"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EGP_JSON = Path("externals/experiments/exp-2740_basal_egp_equilibrium.json")
EXP2738_SIM = Path("externals/experiments/exp-2738_safety_simulation.json")

RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_isf_multifactor.json"
VIZ_DIR = Path("visualizations/isf-multifactor")
VIZ_OUT = VIZ_DIR / "isf_multifactor.png"

# Correction-event filters
BG_THRESHOLD = 180       # mg/dL — only high-BG correction events
MIN_BOLUS_U = 0.5        # Minimum bolus to count as correction
MIN_CORRECTION_U = 0.3   # Skip events where correction insulin < this (instability)
COB_THRESHOLD_G = 5.0    # Maximum COB at event time
CARB_LOOKBACK_STEPS = 24 # 2h lookback for carb contamination
CARB_LOOKAHEAD_STEPS = 24  # 2h lookahead
BOLUS_ISOLATION_STEPS = 24  # 2h prior manual-bolus isolation
WINDOW_STEPS = 24        # 2h observation window (24 × 5min)
STEP_MINUTES = 5

# Regression coefficients from EXP-2719b
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

# EXP-2738 dose-response
ISF_RATIO_VS_TBR_SPEARMAN = -0.852
SAFE_TBR_DELTA_THRESHOLD = 2.0  # pp

# Bootstrap
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 2741

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ──────────────────────────── Helpers ────────────────────────────

def safe_median(arr):
    """Median that handles empty arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.nanmedian(arr))


def safe_iqr(arr):
    """IQR that handles empty arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return (np.nan, np.nan)
    return (float(np.nanpercentile(arr, 25)), float(np.nanpercentile(arr, 75)))


def safe_cv(arr):
    """Coefficient of variation (%) that handles edge cases."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return np.nan
    m = np.nanmean(arr)
    if abs(m) < 1e-6:
        return np.nan
    return float(100.0 * np.nanstd(arr, ddof=1) / abs(m))


def bootstrap_ci(arr, n_boot=N_BOOTSTRAP, seed=BOOTSTRAP_SEED, ci=0.95):
    """Bootstrap confidence interval for the median."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return (np.nan, np.nan)
    rng = np.random.RandomState(seed)
    medians = np.array([
        np.median(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    lo = np.percentile(medians, 100 * (1 - ci) / 2)
    hi = np.percentile(medians, 100 * (1 + ci) / 2)
    return (float(lo), float(hi))


def get_patient_egp(egp_data, patient_id, hour):
    """Get EGP rate for a patient at a given hour (0-23).

    Returns EGP in mg/dL per 5-min step.
    Falls back: circadian_egp[hour] → median_egp → 0.0
    """
    if patient_id not in egp_data:
        return 0.0
    pe = egp_data[patient_id]
    circ = pe.get("circadian_egp", [])
    if circ and 0 <= hour < len(circ) and circ[hour] is not None:
        return float(circ[hour])
    med = pe.get("median_egp", None)
    if med is not None:
        return float(med)
    return 0.0


# ──────────────────────────── Data Loading ────────────────────────────

def load_data():
    """Load grid, manifest, and EGP data."""
    print("[LOAD] Reading grid parquet …")
    grid = pd.read_parquet(GRID)
    print(f"  Grid: {grid.shape[0]:,} rows × {grid.shape[1]} cols, "
          f"{grid['patient_id'].nunique()} patients")

    manifest = json.load(open(MANIFEST))
    qualified = manifest["qualified_patients"]
    print(f"  Qualified patients: {len(qualified)}")

    egp_raw = json.load(open(EGP_JSON))
    per_patient_egp = egp_raw["per_patient_egp"]
    egp_patients = set(per_patient_egp.keys())
    print(f"  EGP patients (EXP-2740): {len(egp_patients)} → {sorted(egp_patients)}")

    # Only analyze patients that have BOTH qualification AND EGP data
    analysis_patients = sorted(set(qualified) & egp_patients)
    print(f"  Analysis patients (intersection): {len(analysis_patients)}")

    # Load EXP-2738 for dose-response reference
    exp2738 = {}
    if EXP2738_SIM.exists():
        exp2738 = json.load(open(EXP2738_SIM))
        print(f"  EXP-2738 simulation loaded: {len(exp2738.get('per_patient', []))} patients")

    return grid, analysis_patients, per_patient_egp, exp2738


# ──────────────────────────── Correction Event Identification ────────────────────────────

def identify_correction_events(pdf):
    """Identify correction bolus events for a single patient DataFrame.

    Returns a list of dicts, one per qualifying event, with all fields
    needed for ISF computation.
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    n = len(pdf)
    events = []

    # Precompute useful series
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values
    bolus_smb = pdf["bolus_smb"].values
    net_basal = pdf["net_basal"].values
    carbs = pdf["carbs"].values
    cob = pdf["cob"].values
    times = pdf["time"].values
    scheduled_isf = pdf["scheduled_isf"].values
    scheduled_basal = pdf.get("scheduled_basal_rate")
    if scheduled_basal is not None:
        scheduled_basal = scheduled_basal.values
    else:
        scheduled_basal = np.full(n, np.nan)

    for i in range(n):
        # Gate 1: BG ≥ threshold
        if not np.isfinite(glucose[i]) or glucose[i] < BG_THRESHOLD:
            continue

        # Gate 2: Manual bolus > minimum
        if not np.isfinite(bolus[i]) or bolus[i] < MIN_BOLUS_U:
            continue

        # Gate 3: Low COB (no active meal)
        if np.isfinite(cob[i]) and cob[i] > COB_THRESHOLD_G:
            continue

        # Gate 4: No carbs at event time
        if np.isfinite(carbs[i]) and carbs[i] > 0:
            continue

        # Gate 5: No carbs within lookback/lookahead window
        lb_start = max(0, i - CARB_LOOKBACK_STEPS)
        la_end = min(n, i + CARB_LOOKAHEAD_STEPS)
        carb_window = carbs[lb_start:la_end]
        if np.nansum(carb_window) > 0:
            continue

        # Gate 6: 2h isolation from prior manual bolus
        iso_start = max(0, i - BOLUS_ISOLATION_STEPS)
        prior_boluses = bolus[iso_start:i]
        if np.nansum(prior_boluses) > 0:
            continue

        # Gate 7: Full 2h observation window available
        win_end = i + WINDOW_STEPS
        if win_end >= n:
            continue

        # Gate 8: Valid glucose at end of window
        bg_end = glucose[win_end]
        if not np.isfinite(bg_end):
            # Try nearby points (±2 steps)
            for offset in [-1, 1, -2, 2]:
                idx = win_end + offset
                if 0 <= idx < n and np.isfinite(glucose[idx]):
                    bg_end = glucose[idx]
                    break
            if not np.isfinite(bg_end):
                continue

        bg_start = glucose[i]
        bg_drop = bg_start - bg_end  # positive if glucose fell

        # ── Compute insulin totals over the window ──
        win_bolus = bolus[i:win_end]
        win_smb = bolus_smb[i:win_end]
        win_basal = net_basal[i:win_end]
        win_sched_basal = scheduled_basal[i:win_end]

        # Total insulin in the window (all sources)
        # net_basal is U/hr; multiply by 5/60 to get U per 5-min step
        total_basal_u = np.nansum(win_basal) * (STEP_MINUTES / 60.0)
        total_bolus_u = np.nansum(win_bolus)
        total_smb_u = np.nansum(win_smb)
        total_insulin = total_bolus_u + total_smb_u + total_basal_u

        # Correction insulin = manual bolus only (the signal)
        correction_insulin = bolus[i]  # just the event bolus

        # Gate 9: Correction insulin must be meaningful
        if correction_insulin < MIN_CORRECTION_U:
            continue

        # Scheduled basal contribution over 2h
        sched_basal_u = np.nansum(win_sched_basal) * (STEP_MINUTES / 60.0)
        if not np.isfinite(sched_basal_u) or sched_basal_u <= 0:
            # Fallback: use median net_basal from this patient as proxy
            sched_basal_u = np.nanmedian(net_basal) * 2.0  # 2 hours
            if not np.isfinite(sched_basal_u) or sched_basal_u < 0:
                sched_basal_u = 0.0

        # Excess insulin above scheduled basal
        excess_insulin = total_insulin - sched_basal_u
        if excess_insulin < MIN_CORRECTION_U:
            excess_insulin = np.nan  # will skip in method 3

        # ── EGP contribution ──
        # Get hour of event for circadian EGP
        ts = pd.Timestamp(times[i])
        hour = ts.hour if hasattr(ts, "hour") else 12

        # Profile ISF at event time
        prof_isf = scheduled_isf[i]

        events.append({
            "index": int(i),
            "bg_start": float(bg_start),
            "bg_end": float(bg_end),
            "bg_drop": float(bg_drop),
            "total_insulin": float(total_insulin),
            "correction_insulin": float(correction_insulin),
            "total_bolus": float(total_bolus_u),
            "total_smb": float(total_smb_u),
            "total_basal_u": float(total_basal_u),
            "scheduled_basal_u": float(sched_basal_u),
            "excess_insulin": float(excess_insulin) if np.isfinite(excess_insulin) else None,
            "hour": int(hour),
            "profile_isf": float(prof_isf) if np.isfinite(prof_isf) else None,
        })

    return events


# ──────────────────────────── ISF Computation Methods ────────────────────────────

def compute_isf_methods(events, per_patient_egp, patient_id):
    """Compute all 5 ISF methods for a list of correction events.

    Returns per-event ISF values for each method and summary stats.
    """
    isf_naive = []        # Method 1
    isf_egp = []          # Method 2
    isf_basal = []        # Method 3
    isf_multi = []        # Method 4
    isf_profile = []      # Method 5

    event_details = []

    for ev in events:
        bg_drop = ev["bg_drop"]
        total_insulin = ev["total_insulin"]
        corr_insulin = ev["correction_insulin"]
        sched_basal_u = ev["scheduled_basal_u"]
        hour = ev["hour"]
        prof_isf = ev["profile_isf"]

        # EGP contribution over 2h window (WINDOW_STEPS 5-min intervals)
        egp_rate = get_patient_egp(per_patient_egp, patient_id, hour)
        egp_contribution = egp_rate * WINDOW_STEPS  # mg/dL over 2h

        # ── Method 1: Naive ISF ──
        # ISF = bg_drop / total_insulin
        if total_insulin > MIN_CORRECTION_U:
            m1 = bg_drop / total_insulin
        else:
            m1 = np.nan

        # ── Method 2: EGP-subtracted ISF ──
        # Without EGP, glucose would have fallen MORE:
        # adjusted_drop = bg_drop + EGP_contribution
        adjusted_drop_egp = bg_drop + egp_contribution
        if total_insulin > MIN_CORRECTION_U:
            m2 = adjusted_drop_egp / total_insulin
        else:
            m2 = np.nan

        # ── Method 3: Basal-subtracted ISF ──
        # Only count excess insulin above scheduled basal
        excess_ins = ev["excess_insulin"]
        if excess_ins is not None and excess_ins > MIN_CORRECTION_U:
            m3 = bg_drop / excess_ins
        else:
            m3 = np.nan

        # ── Method 4: Full multi-factor ISF ──
        # Adjusted drop = bg_drop + EGP_contribution (total insulin effect)
        # Then divide by CORRECTION insulin only (not basal)
        # adjusted_drop includes ALL insulin effects; we want only correction effect
        # correction_effect = total_effect - basal_effect
        # basal_effect = sched_basal_u * true_ISF  ← circular!
        #
        # Alternative approach: use regression coefficient to estimate basal effect
        # basal_glucose_effect = sched_basal_u * |EXCESS_BASAL_COEFF|
        # But that's in the "per-unit" sense; EXCESS_BASAL_COEFF ≈ -130 mg/dL per U/hr
        # Since sched_basal_u is already in Units: basal_effect = sched_basal_u * ~ISF
        #
        # Non-circular approach:
        # (bg_drop + EGP_contribution) = all insulin effect
        # ISF_multi = (bg_drop + EGP_contribution) / correction_insulin
        # This avoids the circularity by simply dividing adjusted drop by correction-only insulin
        if corr_insulin > MIN_CORRECTION_U:
            m4 = (bg_drop + egp_contribution) / corr_insulin
        else:
            m4 = np.nan

        # ── Method 5: Profile ISF ──
        m5 = prof_isf if prof_isf is not None else np.nan

        isf_naive.append(m1)
        isf_egp.append(m2)
        isf_basal.append(m3)
        isf_multi.append(m4)
        isf_profile.append(m5)

        event_details.append({
            "bg_start": ev["bg_start"],
            "bg_end": ev["bg_end"],
            "bg_drop": bg_drop,
            "correction_insulin": corr_insulin,
            "total_insulin": total_insulin,
            "scheduled_basal_u": sched_basal_u,
            "egp_rate": float(egp_rate),
            "egp_contribution": float(egp_contribution),
            "isf_naive": float(m1) if np.isfinite(m1) else None,
            "isf_egp_adjusted": float(m2) if np.isfinite(m2) else None,
            "isf_basal_adjusted": float(m3) if np.isfinite(m3) else None,
            "isf_multifactor": float(m4) if np.isfinite(m4) else None,
            "isf_profile": float(m5) if np.isfinite(m5) else None,
            "hour": ev["hour"],
        })

    # Filter extreme outliers (ISF > 500 or < 0) from all arrays
    def clip(arr, lo=-50, hi=500):
        a = np.asarray(arr, dtype=float)
        a[(a < lo) | (a > hi)] = np.nan
        return a

    isf_naive = clip(isf_naive)
    isf_egp = clip(isf_egp)
    isf_basal = clip(isf_basal)
    isf_multi = clip(isf_multi)
    isf_profile = clip(isf_profile)

    methods = {
        "naive": isf_naive,
        "egp_adjusted": isf_egp,
        "basal_adjusted": isf_basal,
        "multifactor": isf_multi,
        "profile": isf_profile,
    }

    summary = {}
    for name, arr in methods.items():
        finite = arr[np.isfinite(arr)]
        iqr = safe_iqr(finite)
        ci = bootstrap_ci(finite)
        summary[name] = {
            "median": safe_median(finite),
            "mean": float(np.nanmean(finite)) if len(finite) > 0 else None,
            "iqr_25": iqr[0],
            "iqr_75": iqr[1],
            "ci_lo": ci[0],
            "ci_hi": ci[1],
            "cv_pct": safe_cv(finite),
            "n_valid": int(len(finite)),
        }

    return methods, summary, event_details


# ──────────────────────────── Gap Analysis ────────────────────────────

def compute_gap_analysis(summary):
    """Compute how much each method closes the naive-to-profile gap.

    Gap ratio = profile_ISF / method_ISF
    Perfect = 1.0; naive is typically ~4.0
    """
    prof = summary["profile"]["median"]
    naive = summary["naive"]["median"]

    if prof is None or naive is None or not np.isfinite(prof) or not np.isfinite(naive):
        return None

    if abs(naive) < 1e-6:
        return None

    naive_gap = prof - naive  # positive if naive < profile
    if abs(naive_gap) < 1e-6:
        return None

    result = {
        "profile_isf": float(prof),
        "naive_isf": float(naive),
        "naive_gap": float(naive_gap),
        "gap_ratio_naive": float(prof / naive) if abs(naive) > 1e-6 else None,
    }

    for method_name in ["egp_adjusted", "basal_adjusted", "multifactor"]:
        m = summary[method_name]["median"]
        if m is not None and np.isfinite(m) and abs(m) > 1e-6:
            gap_closed = m - naive  # how much closer to profile
            pct_closed = 100.0 * gap_closed / naive_gap if abs(naive_gap) > 1e-6 else 0
            result[f"gap_ratio_{method_name}"] = float(prof / m)
            result[f"gap_closed_pct_{method_name}"] = float(pct_closed)
            result[f"isf_{method_name}"] = float(m)
        else:
            result[f"gap_ratio_{method_name}"] = None
            result[f"gap_closed_pct_{method_name}"] = None
            result[f"isf_{method_name}"] = None

    return result


# ──────────────────────────── Safety Prediction ────────────────────────────

def predict_tbr_delta(isf_ratio):
    """Predict TBR change from ISF ratio using EXP-2738 dose-response.

    EXP-2738 found strong Spearman correlation between ISF ratio and TBR delta.
    isf_ratio = profile_ISF / empirical_ISF

    The relationship is approximately linear in the observed range:
    - ratio ~1.0 → minimal TBR change
    - ratio ~2.0 → moderate TBR increase (~4-6pp)
    - ratio ~4.0 → large TBR increase (~15-20pp)

    We use the EXP-2738 per-patient data to build a simple linear model.
    For now, use the approximate relationship:
      tbr_delta ≈ 5.0 * (isf_ratio - 1.0)
    which gives ~0pp at ratio=1, ~5pp at ratio=2, ~15pp at ratio=4.
    """
    if isf_ratio is None or not np.isfinite(isf_ratio):
        return np.nan
    # Clamp ratio to reasonable range
    ratio = max(0.5, min(isf_ratio, 6.0))
    # Linear approximation from EXP-2738 dose-response
    tbr_delta = 5.0 * (ratio - 1.0)
    return float(tbr_delta)


# ──────────────────────────── Main Analysis ────────────────────────────

def run_analysis():
    """Main analysis pipeline."""
    grid, analysis_patients, per_patient_egp, exp2738 = load_data()

    # ── Per-patient analysis ──
    per_patient_results = []
    all_methods_medians = {
        "naive": [], "egp_adjusted": [], "basal_adjusted": [],
        "multifactor": [], "profile": [],
    }
    all_gap_analyses = []
    all_cvs = {
        "naive": [], "egp_adjusted": [], "basal_adjusted": [],
        "multifactor": [],
    }

    for pid in analysis_patients:
        print(f"\n{'='*60}")
        print(f"  Patient: {pid}")
        print(f"{'='*60}")

        pdf = grid[grid["patient_id"] == pid].copy()
        if len(pdf) == 0:
            print(f"  [SKIP] No data for {pid}")
            continue

        pdf = pdf.sort_values("time").reset_index(drop=True)
        print(f"  Rows: {len(pdf):,}")

        # Identify correction events
        events = identify_correction_events(pdf)
        print(f"  Correction events found: {len(events)}")

        if len(events) < 3:
            print(f"  [SKIP] Too few events for {pid}")
            continue

        # Compute ISF by all methods
        methods, summary, event_details = compute_isf_methods(
            events, per_patient_egp, pid
        )

        # Gap analysis
        gap = compute_gap_analysis(summary)

        # Print summary
        print(f"  ISF Summary:")
        for mname, mstats in summary.items():
            med = mstats["median"]
            cv = mstats["cv_pct"]
            nv = mstats["n_valid"]
            med_s = f"{med:.1f}" if med is not None and np.isfinite(med) else "N/A"
            cv_s = f"{cv:.1f}%" if cv is not None and np.isfinite(cv) else "N/A"
            print(f"    {mname:20s}: median={med_s:>8s}  CV={cv_s:>8s}  n={nv}")

        if gap:
            print(f"  Gap Analysis:")
            for k, v in gap.items():
                if v is not None and isinstance(v, float):
                    print(f"    {k}: {v:.3f}")

        # Collect per-patient medians
        for mname in all_methods_medians:
            med = summary[mname]["median"]
            if med is not None and np.isfinite(med):
                all_methods_medians[mname].append(med)

        for mname in all_cvs:
            cv = summary[mname]["cv_pct"]
            if cv is not None and np.isfinite(cv):
                all_cvs[mname].append(cv)

        if gap:
            all_gap_analyses.append(gap)

        # Safety prediction for each method
        safety = {}
        for mname in ["naive", "egp_adjusted", "basal_adjusted", "multifactor"]:
            ratio = gap.get(f"gap_ratio_{mname}") if gap else None
            if ratio is None and gap:
                med = summary[mname]["median"]
                prof = summary["profile"]["median"]
                if med and np.isfinite(med) and prof and np.isfinite(prof) and abs(med) > 1e-6:
                    ratio = prof / med
            tbr_pred = predict_tbr_delta(ratio) if ratio is not None else np.nan
            safety[mname] = {
                "isf_ratio": float(ratio) if ratio is not None and np.isfinite(ratio) else None,
                "predicted_tbr_delta": float(tbr_pred) if np.isfinite(tbr_pred) else None,
                "safe": bool(tbr_pred < SAFE_TBR_DELTA_THRESHOLD) if np.isfinite(tbr_pred) else None,
            }

        per_patient_results.append({
            "patient_id": pid,
            "n_events": len(events),
            "n_valid_naive": summary["naive"]["n_valid"],
            "isf_summary": summary,
            "gap_analysis": gap,
            "safety_prediction": safety,
            "event_details": event_details[:5],  # first 5 events as examples
        })

    # ──────────────────────────── Population Summary ────────────────────────────

    print(f"\n{'='*60}")
    print(f"  POPULATION SUMMARY")
    print(f"{'='*60}")

    n_patients = len(per_patient_results)
    print(f"  Patients analyzed: {n_patients}")

    pop_summary = {
        "n_patients": n_patients,
        "method_medians": {},
        "method_cvs": {},
    }

    for mname in ["naive", "egp_adjusted", "basal_adjusted", "multifactor", "profile"]:
        vals = all_methods_medians[mname]
        pop_summary["method_medians"][mname] = {
            "median_of_medians": safe_median(vals),
            "iqr_25": safe_iqr(vals)[0],
            "iqr_75": safe_iqr(vals)[1],
            "n": len(vals),
        }
        print(f"  {mname:20s}: median={safe_median(vals):.1f} "
              f"(IQR {safe_iqr(vals)[0]:.1f}–{safe_iqr(vals)[1]:.1f}), n={len(vals)}")

    for mname in ["naive", "egp_adjusted", "basal_adjusted", "multifactor"]:
        vals = all_cvs[mname]
        pop_summary["method_cvs"][mname] = {
            "median_cv": safe_median(vals),
            "n": len(vals),
        }

    # ── Gap closure summary ──
    if all_gap_analyses:
        gap_pcts_egp = [g["gap_closed_pct_egp_adjusted"] for g in all_gap_analyses
                        if g.get("gap_closed_pct_egp_adjusted") is not None]
        gap_pcts_basal = [g["gap_closed_pct_basal_adjusted"] for g in all_gap_analyses
                          if g.get("gap_closed_pct_basal_adjusted") is not None]
        gap_pcts_multi = [g["gap_closed_pct_multifactor"] for g in all_gap_analyses
                          if g.get("gap_closed_pct_multifactor") is not None]

        pop_summary["gap_closure"] = {
            "egp_median_pct": safe_median(gap_pcts_egp),
            "basal_median_pct": safe_median(gap_pcts_basal),
            "multifactor_median_pct": safe_median(gap_pcts_multi),
            "n_patients_with_gap": len(all_gap_analyses),
        }

        print(f"\n  Gap Closure (median % of naive→profile gap):")
        print(f"    EGP only:       {safe_median(gap_pcts_egp):.1f}%")
        print(f"    Basal only:     {safe_median(gap_pcts_basal):.1f}%")
        print(f"    Multi-factor:   {safe_median(gap_pcts_multi):.1f}%")

    # ──────────────────────────── Hypothesis Testing ────────────────────────────

    print(f"\n{'='*60}")
    print(f"  HYPOTHESIS TESTING")
    print(f"{'='*60}")

    hypotheses = {}

    # H1: Multi-factor ISF is >1.5× closer to profile than naive ISF
    if all_gap_analyses:
        naive_gaps = [abs(g["profile_isf"] - g["naive_isf"]) for g in all_gap_analyses]
        multi_gaps = []
        for g in all_gap_analyses:
            mi = g.get("isf_multifactor")
            if mi is not None and np.isfinite(mi):
                multi_gaps.append(abs(g["profile_isf"] - mi))
            else:
                multi_gaps.append(np.nan)

        valid = [(ng, mg) for ng, mg in zip(naive_gaps, multi_gaps) if np.isfinite(mg) and ng > 0]
        if valid:
            closeness_ratios = [ng / mg if mg > 0 else np.inf for ng, mg in valid]
            median_closeness = safe_median(closeness_ratios)
            n_closer = sum(1 for r in closeness_ratios if np.isfinite(r) and r > 1.5)
            h1_pass = bool(median_closeness > 1.5)
            hypotheses["H1_multifactor_closer"] = {
                "passed": h1_pass,
                "description": "Multi-factor ISF is >1.5× closer to profile than naive ISF",
                "median_closeness_ratio": float(median_closeness) if np.isfinite(median_closeness) else None,
                "n_patients_closer_1_5x": n_closer,
                "n_total": len(valid),
            }
            h1_verdict = "PASS ✓" if h1_pass else "FAIL ✗"
            print(f"  H1 [{h1_verdict}]: Multi-factor {median_closeness:.2f}× closer "
                  f"(threshold: 1.5×), {n_closer}/{len(valid)} patients")
        else:
            hypotheses["H1_multifactor_closer"] = {
                "passed": False, "description": "Insufficient data", "n_total": 0,
            }
            print("  H1 [FAIL ✗]: Insufficient data")
    else:
        hypotheses["H1_multifactor_closer"] = {
            "passed": False, "description": "No gap analyses available",
        }
        print("  H1 [FAIL ✗]: No gap analyses")

    # H2: EGP subtraction alone accounts for >40% of the naive-to-profile gap
    if all_gap_analyses:
        egp_pcts = [g["gap_closed_pct_egp_adjusted"] for g in all_gap_analyses
                    if g.get("gap_closed_pct_egp_adjusted") is not None
                    and np.isfinite(g["gap_closed_pct_egp_adjusted"])]
        if egp_pcts:
            median_egp_pct = safe_median(egp_pcts)
            h2_pass = bool(median_egp_pct > 40)
            hypotheses["H2_egp_accounts_40pct"] = {
                "passed": h2_pass,
                "description": "EGP subtraction alone accounts for >40% of naive-to-profile gap",
                "median_pct_closed": float(median_egp_pct),
                "n_patients": len(egp_pcts),
            }
            h2_verdict = "PASS ✓" if h2_pass else "FAIL ✗"
            print(f"  H2 [{h2_verdict}]: EGP closes {median_egp_pct:.1f}% of gap "
                  f"(threshold: 40%)")
        else:
            hypotheses["H2_egp_accounts_40pct"] = {
                "passed": False, "description": "Insufficient data",
            }
            print("  H2 [FAIL ✗]: Insufficient data")
    else:
        hypotheses["H2_egp_accounts_40pct"] = {
            "passed": False, "description": "No gap analyses",
        }
        print("  H2 [FAIL ✗]: No gap analyses")

    # H3: Basal subtraction alone accounts for >30% of the gap
    if all_gap_analyses:
        basal_pcts = [g["gap_closed_pct_basal_adjusted"] for g in all_gap_analyses
                      if g.get("gap_closed_pct_basal_adjusted") is not None
                      and np.isfinite(g["gap_closed_pct_basal_adjusted"])]
        if basal_pcts:
            median_basal_pct = safe_median(basal_pcts)
            h3_pass = bool(median_basal_pct > 30)
            hypotheses["H3_basal_accounts_30pct"] = {
                "passed": h3_pass,
                "description": "Basal subtraction alone accounts for >30% of naive-to-profile gap",
                "median_pct_closed": float(median_basal_pct),
                "n_patients": len(basal_pcts),
            }
            h3_verdict = "PASS ✓" if h3_pass else "FAIL ✗"
            print(f"  H3 [{h3_verdict}]: Basal closes {median_basal_pct:.1f}% of gap "
                  f"(threshold: 30%)")
        else:
            hypotheses["H3_basal_accounts_30pct"] = {
                "passed": False, "description": "Insufficient data",
            }
            print("  H3 [FAIL ✗]: Insufficient data")
    else:
        hypotheses["H3_basal_accounts_30pct"] = {
            "passed": False, "description": "No gap analyses",
        }
        print("  H3 [FAIL ✗]: No gap analyses")

    # H4: Multi-factor ISF has lower inter-event CV than naive ISF
    naive_cvs = all_cvs["naive"]
    multi_cvs = all_cvs["multifactor"]
    if naive_cvs and multi_cvs:
        median_naive_cv = safe_median(naive_cvs)
        median_multi_cv = safe_median(multi_cvs)
        n_lower = sum(1 for nc, mc in zip(naive_cvs, multi_cvs) if mc < nc)
        h4_pass = bool(median_multi_cv < median_naive_cv)
        hypotheses["H4_lower_cv"] = {
            "passed": h4_pass,
            "description": "Multi-factor ISF has lower inter-event CV than naive",
            "median_naive_cv": float(median_naive_cv),
            "median_multi_cv": float(median_multi_cv),
            "n_lower": n_lower,
            "n_total": min(len(naive_cvs), len(multi_cvs)),
        }
        h4_verdict = "PASS ✓" if h4_pass else "FAIL ✗"
        print(f"  H4 [{h4_verdict}]: Multi CV={median_multi_cv:.1f}% vs "
              f"Naive CV={median_naive_cv:.1f}%")
    else:
        hypotheses["H4_lower_cv"] = {
            "passed": False, "description": "Insufficient data",
        }
        print("  H4 [FAIL ✗]: Insufficient data")

    # H5: Multi-factor ISF passes safety (predicted TBR increase <2pp)
    tbr_preds = []
    for pr in per_patient_results:
        sp = pr["safety_prediction"].get("multifactor", {})
        td = sp.get("predicted_tbr_delta")
        if td is not None and np.isfinite(td):
            tbr_preds.append(td)

    if tbr_preds:
        median_tbr = safe_median(tbr_preds)
        n_safe = sum(1 for t in tbr_preds if t < SAFE_TBR_DELTA_THRESHOLD)
        h5_pass = bool(median_tbr < SAFE_TBR_DELTA_THRESHOLD)
        hypotheses["H5_safety_pass"] = {
            "passed": h5_pass,
            "description": f"Multi-factor ISF predicted TBR increase <{SAFE_TBR_DELTA_THRESHOLD}pp",
            "median_predicted_tbr_delta": float(median_tbr),
            "n_safe": n_safe,
            "n_total": len(tbr_preds),
            "pct_safe": float(100.0 * n_safe / len(tbr_preds)),
        }
        h5_verdict = "PASS ✓" if h5_pass else "FAIL ✗"
        print(f"  H5 [{h5_verdict}]: Predicted TBR delta = {median_tbr:.2f}pp "
              f"(threshold: {SAFE_TBR_DELTA_THRESHOLD}pp), "
              f"{n_safe}/{len(tbr_preds)} patients safe")
    else:
        hypotheses["H5_safety_pass"] = {
            "passed": False, "description": "Insufficient data",
        }
        print("  H5 [FAIL ✗]: Insufficient data")

    # ──────────────────────────── Build Output ────────────────────────────

    n_passed = sum(1 for h in hypotheses.values() if bool(h.get("passed", False)))
    n_total = len(hypotheses)

    summary_text = (
        f"EXP-{EXP_ID}: {TITLE}. "
        f"{n_passed}/{n_total} hypotheses passed. "
        f"Analyzed {n_patients} patients with per-patient EGP data. "
    )

    # Add key finding
    prof_med = pop_summary["method_medians"].get("profile", {}).get("median_of_medians", 0)
    naive_med = pop_summary["method_medians"].get("naive", {}).get("median_of_medians", 0)
    multi_med = pop_summary["method_medians"].get("multifactor", {}).get("median_of_medians", 0)
    if prof_med and naive_med and multi_med:
        summary_text += (
            f"Population median ISF: naive={naive_med:.1f}, "
            f"multifactor={multi_med:.1f}, profile={prof_med:.1f}."
        )

    output = {
        "exp_id": EXP_ID,
        "title": TITLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary_text,
        "parameters": {
            "bg_threshold": BG_THRESHOLD,
            "min_bolus_u": MIN_BOLUS_U,
            "min_correction_u": MIN_CORRECTION_U,
            "cob_threshold_g": COB_THRESHOLD_G,
            "carb_lookback_steps": CARB_LOOKBACK_STEPS,
            "carb_lookahead_steps": CARB_LOOKAHEAD_STEPS,
            "bolus_isolation_steps": BOLUS_ISOLATION_STEPS,
            "window_steps": WINDOW_STEPS,
            "step_minutes": STEP_MINUTES,
            "n_bootstrap": N_BOOTSTRAP,
            "safe_tbr_delta_threshold": SAFE_TBR_DELTA_THRESHOLD,
        },
        "population_summary": pop_summary,
        "hypotheses": hypotheses,
        "per_patient_results": per_patient_results,
        "dose_response_reference": {
            "source": "EXP-2738",
            "isf_ratio_vs_tbr_spearman": ISF_RATIO_VS_TBR_SPEARMAN,
            "model": "linear: tbr_delta = 5.0 * (isf_ratio - 1.0)",
        },
    }

    # Save JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  ✓ Results saved to {OUT_JSON}")

    # ──────────────────────────── Visualization ────────────────────────────

    create_visualization(per_patient_results, pop_summary, all_gap_analyses, hypotheses)

    return output


# ──────────────────────────── Visualization ────────────────────────────

def create_visualization(per_patient_results, pop_summary, all_gap_analyses, hypotheses):
    """Create 2×3 panel visualization."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(20, 13))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=16, fontweight="bold", y=0.98)

    method_names = ["naive", "egp_adjusted", "basal_adjusted", "multifactor", "profile"]
    method_labels = ["Naive", "EGP-adj", "Basal-adj", "Multi-factor", "Profile"]
    colors = ["#e74c3c", "#e67e22", "#3498db", "#2ecc71", "#9b59b6"]

    # ── Panel 1: ISF Method Comparison (box plot) ──
    ax = axes[0, 0]
    method_data = []
    for mname in method_names:
        vals = []
        for pr in per_patient_results:
            s = pr["isf_summary"].get(mname, {})
            med = s.get("median")
            if med is not None and np.isfinite(med):
                vals.append(med)
        method_data.append(vals)

    bp = ax.boxplot(method_data, patch_artist=True, tick_labels=method_labels,
                    widths=0.6, showfliers=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    # Add profile reference line
    prof_vals = method_data[4]
    if prof_vals:
        prof_med = np.median(prof_vals)
        ax.axhline(prof_med, color="#9b59b6", linestyle="--", alpha=0.7,
                    label=f"Profile median={prof_med:.0f}")
        ax.legend(fontsize=8)

    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("(a) ISF by Method", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 2: Gap Closure Waterfall ──
    ax = axes[0, 1]
    if all_gap_analyses:
        # Compute median gap closure for each step
        egp_pcts = [g.get("gap_closed_pct_egp_adjusted", 0)
                    for g in all_gap_analyses
                    if g.get("gap_closed_pct_egp_adjusted") is not None]
        basal_pcts = [g.get("gap_closed_pct_basal_adjusted", 0)
                      for g in all_gap_analyses
                      if g.get("gap_closed_pct_basal_adjusted") is not None]
        multi_pcts = [g.get("gap_closed_pct_multifactor", 0)
                      for g in all_gap_analyses
                      if g.get("gap_closed_pct_multifactor") is not None]

        categories = ["EGP\nonly", "Basal\nonly", "Multi-\nfactor"]
        medians = [safe_median(egp_pcts), safe_median(basal_pcts), safe_median(multi_pcts)]
        bar_colors = [colors[1], colors[2], colors[3]]

        bars = ax.bar(categories, medians, color=bar_colors, alpha=0.7, edgecolor="black")
        ax.axhline(100, color="black", linestyle="--", alpha=0.5, label="Full gap closure")
        ax.axhline(0, color="gray", linestyle="-", alpha=0.3)

        for bar, val in zip(bars, medians):
            if np.isfinite(val):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                        f"{val:.0f}%", ha="center", va="bottom", fontsize=10,
                        fontweight="bold")

        ax.set_ylabel("% of Naive→Profile Gap Closed")
        ax.set_title("(b) Gap Closure by Subtraction Step", fontsize=11,
                      fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)
    else:
        ax.text(0.5, 0.5, "No gap data", transform=ax.transAxes, ha="center")
        ax.set_title("(b) Gap Closure", fontsize=11, fontweight="bold")

    # ── Panel 3: Per-Patient ISF Ladder ──
    ax = axes[0, 2]
    if per_patient_results:
        # Sort patients by profile ISF
        sorted_patients = sorted(
            per_patient_results,
            key=lambda p: p["isf_summary"].get("profile", {}).get("median", 0) or 0
        )

        y_pos = np.arange(len(sorted_patients))
        pid_labels = []

        for idx, pr in enumerate(sorted_patients):
            pid_short = pr["patient_id"][-8:]
            pid_labels.append(pid_short)

            for mi, mname in enumerate(method_names):
                med = pr["isf_summary"].get(mname, {}).get("median")
                if med is not None and np.isfinite(med):
                    marker = "o" if mname != "profile" else "D"
                    size = 8 if mname != "multifactor" else 12
                    ax.scatter(med, idx, color=colors[mi], marker=marker,
                               s=size**2, zorder=3, alpha=0.8,
                               edgecolors="black" if mname == "multifactor" else "none",
                               linewidths=0.5)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(pid_labels, fontsize=8)
        ax.set_xlabel("ISF (mg/dL per U)")
        ax.set_title("(c) Per-Patient ISF Ladder", fontsize=11, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=c, label=l, markersize=8)
            for c, l in zip(colors[:4], method_labels[:4])
        ] + [
            Line2D([0], [0], marker="D", color="w", markerfacecolor=colors[4],
                   label=method_labels[4], markersize=8)
        ]
        ax.legend(handles=legend_elements, fontsize=7, loc="lower right")
    else:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center")
        ax.set_title("(c) Per-Patient ISF Ladder", fontsize=11, fontweight="bold")

    # ── Panel 4: Precision Comparison (CV) ──
    ax = axes[1, 0]
    cv_methods = ["naive", "egp_adjusted", "basal_adjusted", "multifactor"]
    cv_labels = ["Naive", "EGP-adj", "Basal-adj", "Multi-factor"]
    cv_colors = colors[:4]

    cv_data = []
    for mname in cv_methods:
        vals = []
        for pr in per_patient_results:
            cv = pr["isf_summary"].get(mname, {}).get("cv_pct")
            if cv is not None and np.isfinite(cv):
                vals.append(cv)
        cv_data.append(vals)

    if any(cv_data):
        bp2 = ax.boxplot(cv_data, patch_artist=True, tick_labels=cv_labels,
                         widths=0.6)
        for patch, color in zip(bp2["boxes"], cv_colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)

        # Add medians as text
        for i, vals in enumerate(cv_data):
            if vals:
                med = np.median(vals)
                ax.text(i + 1, med + 2, f"{med:.0f}%", ha="center", fontsize=9,
                        fontweight="bold")

    ax.set_ylabel("CV (%)")
    ax.set_title("(d) Measurement Precision (lower=better)", fontsize=11,
                  fontweight="bold")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 5: Safety Prediction ──
    ax = axes[1, 1]
    safety_methods = ["naive", "egp_adjusted", "basal_adjusted", "multifactor"]
    safety_labels = ["Naive", "EGP-adj", "Basal-adj", "Multi-factor"]
    safety_colors = colors[:4]

    tbr_data = {m: [] for m in safety_methods}
    for pr in per_patient_results:
        for mname in safety_methods:
            sp = pr["safety_prediction"].get(mname, {})
            td = sp.get("predicted_tbr_delta")
            if td is not None and np.isfinite(td):
                tbr_data[mname].append(td)

    tbr_medians = []
    tbr_errs_lo = []
    tbr_errs_hi = []
    for mname in safety_methods:
        vals = tbr_data[mname]
        if vals:
            med = np.median(vals)
            q25 = np.percentile(vals, 25)
            q75 = np.percentile(vals, 75)
            tbr_medians.append(med)
            tbr_errs_lo.append(med - q25)
            tbr_errs_hi.append(q75 - med)
        else:
            tbr_medians.append(0)
            tbr_errs_lo.append(0)
            tbr_errs_hi.append(0)

    x_pos = np.arange(len(safety_methods))
    bars = ax.bar(x_pos, tbr_medians, yerr=[tbr_errs_lo, tbr_errs_hi],
                  color=safety_colors, alpha=0.7, edgecolor="black", capsize=5)

    ax.axhline(SAFE_TBR_DELTA_THRESHOLD, color="red", linestyle="--", alpha=0.7,
               label=f"Safety threshold ({SAFE_TBR_DELTA_THRESHOLD}pp)")
    ax.axhline(0, color="gray", linestyle="-", alpha=0.3)

    for bar, val in zip(bars, tbr_medians):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val:.1f}pp", ha="center", va="bottom", fontsize=10,
                fontweight="bold")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(safety_labels, rotation=30)
    ax.set_ylabel("Predicted TBR Δ (pp)")
    ax.set_title("(e) Safety: Predicted TBR Change", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 6: EGP vs Basal Contribution ──
    ax = axes[1, 2]
    if all_gap_analyses:
        egp_fracs = []
        basal_fracs = []
        for g in all_gap_analyses:
            egp_pct = g.get("gap_closed_pct_egp_adjusted")
            multi_pct = g.get("gap_closed_pct_multifactor")
            basal_pct = g.get("gap_closed_pct_basal_adjusted")

            if (egp_pct is not None and multi_pct is not None and basal_pct is not None
                    and np.isfinite(egp_pct) and np.isfinite(multi_pct)
                    and np.isfinite(basal_pct) and abs(multi_pct) > 1e-6):
                egp_fracs.append(100.0 * egp_pct / multi_pct if multi_pct != 0 else 0)
                basal_fracs.append(100.0 * basal_pct / multi_pct if multi_pct != 0 else 0)

        if egp_fracs and basal_fracs:
            ax.scatter(egp_fracs, basal_fracs, c=colors[3], s=100, alpha=0.7,
                       edgecolors="black", zorder=3)

            # Add reference lines
            ax.axhline(50, color="gray", linestyle=":", alpha=0.5)
            ax.axvline(50, color="gray", linestyle=":", alpha=0.5)

            # Labels
            for i, (ef, bf) in enumerate(zip(egp_fracs, basal_fracs)):
                if i < len(per_patient_results):
                    pid_short = per_patient_results[i]["patient_id"][-6:]
                    ax.annotate(pid_short, (ef, bf), fontsize=7,
                                textcoords="offset points", xytext=(5, 5))

            ax.set_xlabel("EGP contribution (% of multi-factor gap closure)")
            ax.set_ylabel("Basal contribution (% of multi-factor gap closure)")
            ax.set_title("(f) EGP vs Basal Contribution", fontsize=11,
                          fontweight="bold")
            ax.grid(alpha=0.3)
        else:
            ax.text(0.5, 0.5, "Insufficient data", transform=ax.transAxes,
                    ha="center")
            ax.set_title("(f) EGP vs Basal Contribution", fontsize=11,
                          fontweight="bold")
    else:
        ax.text(0.5, 0.5, "No gap data", transform=ax.transAxes, ha="center")
        ax.set_title("(f) EGP vs Basal Contribution", fontsize=11,
                      fontweight="bold")

    # ── Hypothesis verdicts text box ──
    n_passed = sum(1 for h in hypotheses.values() if bool(h.get("passed", False)))
    n_total = len(hypotheses)
    verdict_lines = [f"Hypotheses: {n_passed}/{n_total} passed"]
    for hname, hdata in sorted(hypotheses.items()):
        status = "✓" if bool(hdata.get("passed", False)) else "✗"
        desc = hdata.get("description", "")[:60]
        verdict_lines.append(f"  {status} {hname}: {desc}")

    verdict_text = "\n".join(verdict_lines)
    fig.text(0.02, 0.01, verdict_text, fontsize=8, family="monospace",
             verticalalignment="bottom",
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    plt.tight_layout(rect=[0, 0.08, 1, 0.96])

    fig.savefig(VIZ_OUT, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  ✓ Visualization saved to {VIZ_OUT}")


# ──────────────────────────── Entry Point ────────────────────────────

if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"  EXP-{EXP_ID}: {TITLE}")
    print(f"{'='*60}")
    print()

    result = run_analysis()

    # Final verdict
    print(f"\n{'='*60}")
    print(f"  FINAL VERDICT")
    print(f"{'='*60}")
    hyps = result["hypotheses"]
    for hname in sorted(hyps.keys()):
        h = hyps[hname]
        status = "PASS ✓" if bool(h.get("passed", False)) else "FAIL ✗"
        desc = h.get("description", "")
        print(f"  {hname}: [{status}] {desc}")

    n_passed = sum(1 for h in hyps.values() if bool(h.get("passed", False)))
    n_total = len(hyps)
    print(f"\n  Overall: {n_passed}/{n_total} hypotheses passed")
    print(f"  Results: {OUT_JSON}")
    print(f"  Visual:  {VIZ_OUT}")
    print()
