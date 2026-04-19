#!/usr/bin/env python3
"""EXP-2663: Demand-Phase ISF Dose-Dependence

EXP-2640 established that APPARENT ISF is logarithmically dose-dependent
(r=-0.56, p<1e-19). But apparent ISF is inflated 2-10× by EGP suppression
and AID compensation (EXP-2651). The critical question: is DEMAND-PHASE ISF
(0-2h drop/dose) also dose-dependent?

WHY THIS MATTERS:
  - If demand ISF is dose-INDEPENDENT → dosing can use a constant per-patient
    ISF (simpler, safer, easier to tune)
  - If demand ISF is dose-DEPENDENT → dosing needs per-dose curves
    (dose = solve(ΔBG = dose × ISF(dose)))

HYPOTHESIS (physiological reasoning):
  EGP suppression is likely the dose-dependent component: larger doses cause
  more/longer hepatic glucose suppression, inflating apparent ISF more at
  higher doses. If so, demand-phase ISF (which measures only pre-EGP
  insulin effect) should be LESS dose-dependent than apparent ISF.

HYPOTHESES:
  H1: Demand ISF has weaker dose-dependence than apparent ISF (|r_demand| < |r_apparent|)
  H2: If demand ISF IS dose-dependent, the slope is shallower (per-patient)
  H3: Cross-patient demand ISF has lower CV at matched doses (more consistent)
  H4: The dose-dependence difference is robust (LOO + bootstrap)
  H5: Demand ISF dose-dependence is <0.3 for majority of patients (weak/absent)

METHODOLOGY:
  1. Extract correction events from parquet (EXP-2651 gold standard method)
  2. Compute per-event: demand ISF (drop@2h / dose) and apparent ISF (drop@nadir / dose)
  3. Correlate each with dose (Pearson r, linear/log/sqrt fits)
  4. Per-patient: compare r_demand vs r_apparent
  5. Cross-patient: dose-matched comparison of demand vs apparent CV
  6. Validation: bootstrap CIs + leave-one-patient-out

DATA: 19 patients, parquet grid, 5-min intervals
DEPENDS ON: EXP-2651 extraction method, EXP-2640 analysis framework
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2663_demand_dose_dependence.json"

STEPS_PER_HOUR = 12

# Correction extraction parameters (from EXP-2651 gold standard)
MIN_DOSE = 0.5          # Units
MIN_PRE_BG = 120        # mg/dL
CARB_WINDOW_H = 1.0     # ± hours, no carbs
PRIOR_BOLUS_H = 6.0     # Nyquist-correct: ≥DIA=6h
LAX_PRIOR_BOLUS_H = 2.0 # Fallback for SMB-heavy patients
POST_WINDOW_H = 6.0     # Track trajectory
MIN_DROP = 10            # mg/dL minimum total drop to count
MIN_EVENTS_FIT = 8      # Min events per patient for regression
DEMAND_WINDOW_H = 2.0   # Demand phase: 0-2h
NADIR_SEARCH_START_H = 1.0  # Search for nadir from 1h onward
NADIR_SEARCH_END_H = 5.0

N_BOOTSTRAP = 2000


def extract_correction_events(pdf, prior_bolus_h=None):
    """Extract clean correction bolus events with per-event ISF metrics.

    Returns list of dicts with: dose, pre_bg, demand_isf, apparent_isf,
    drop_2h, total_drop, nadir_time_h.
    Uses tiered fallback: strict 6h → lax 2h if <MIN_EVENTS_FIT at strict.
    """
    if prior_bolus_h is None:
        prior_bolus_h = PRIOR_BOLUS_H
    pdf = pdf.sort_values("time").reset_index(drop=True)
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = int(CARB_WINDOW_H * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    post_window = int(POST_WINDOW_H * STEPS_PER_HOUR)
    demand_steps = int(DEMAND_WINDOW_H * STEPS_PER_HOUR)
    nadir_start = int(NADIR_SEARCH_START_H * STEPS_PER_HOUR)
    nadir_end = int(NADIR_SEARCH_END_H * STEPS_PER_HOUR)

    events = []
    for i in range(prior_window, len(pdf) - post_window):
        if bolus[i] < MIN_DOSE:
            continue
        if np.isnan(glucose[i]) or glucose[i] < MIN_PRE_BG:
            continue

        # No carbs within ± window
        cs = max(0, i - carb_window)
        ce = min(len(pdf), i + carb_window)
        if np.nansum(carbs[cs:ce]) > 2:
            continue

        # No prior bolus
        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        traj = glucose[i:i + post_window + 1]

        # Need valid glucose at 2h for demand ISF
        idx_2h = demand_steps
        if idx_2h >= len(traj) or np.isnan(traj[0]) or np.isnan(traj[idx_2h]):
            continue

        pre_bg = float(traj[0])
        dose = float(bolus[i])
        drop_2h = float(pre_bg - traj[idx_2h])

        # Find nadir in 1h-5h window
        search_slice = traj[nadir_start:min(nadir_end, len(traj))]
        valid_mask = ~np.isnan(search_slice)
        if valid_mask.sum() < 6:
            continue

        nadir_rel = np.nanargmin(search_slice)
        nadir_bg = float(search_slice[nadir_rel])
        nadir_time_h = float(nadir_start + nadir_rel) / STEPS_PER_HOUR
        total_drop = pre_bg - nadir_bg

        if total_drop < MIN_DROP:
            continue

        # Per-event ISFs
        demand_isf = drop_2h / dose if dose > 0 else np.nan
        apparent_isf = total_drop / dose if dose > 0 else np.nan

        # Also get 1h and 3h drops for phase curve
        idx_1h = STEPS_PER_HOUR
        idx_3h = 3 * STEPS_PER_HOUR
        drop_1h = float(pre_bg - traj[idx_1h]) if idx_1h < len(traj) and not np.isnan(traj[idx_1h]) else np.nan
        drop_3h = float(pre_bg - traj[idx_3h]) if idx_3h < len(traj) and not np.isnan(traj[idx_3h]) else np.nan

        events.append({
            "dose": dose,
            "pre_bg": pre_bg,
            "drop_1h": drop_1h,
            "drop_2h": drop_2h,
            "drop_3h": drop_3h,
            "total_drop": total_drop,
            "nadir_bg": nadir_bg,
            "nadir_time_h": nadir_time_h,
            "demand_isf": demand_isf,
            "apparent_isf": apparent_isf,
        })

    return events


def fit_dose_models(doses, isfs):
    """Fit linear, log, sqrt models of ISF vs dose. Returns dict of fits."""
    result = {}
    if len(doses) < MIN_EVENTS_FIT or np.std(doses) < 0.05:
        return None

    # Linear: ISF = a + b*dose
    slope, intercept, r, p, se = stats.linregress(doses, isfs)
    result["linear"] = {
        "slope": round(float(slope), 3),
        "intercept": round(float(intercept), 2),
        "r": round(float(r), 4),
        "p": float(p),
        "r_squared": round(float(r**2), 4),
    }

    # Log: ISF = a + b*ln(dose)
    log_d = np.log(doses + 0.01)
    sl, ic, rl, pl, sel = stats.linregress(log_d, isfs)
    result["log"] = {
        "slope": round(float(sl), 3),
        "intercept": round(float(ic), 2),
        "r": round(float(rl), 4),
        "p": float(pl),
        "r_squared": round(float(rl**2), 4),
    }

    # Sqrt: ISF = a + b*sqrt(dose)
    sqrt_d = np.sqrt(doses)
    ss, ics, rs, ps, ses = stats.linregress(sqrt_d, isfs)
    result["sqrt"] = {
        "slope": round(float(ss), 3),
        "intercept": round(float(ics), 2),
        "r": round(float(rs), 4),
        "p": float(ps),
        "r_squared": round(float(rs**2), 4),
    }

    models = {"linear": abs(result["linear"]["r"]),
              "log": abs(result["log"]["r"]),
              "sqrt": abs(result["sqrt"]["r"])}
    result["best_model"] = max(models, key=models.get)
    result["best_r"] = round(float(models[result["best_model"]]), 4)

    return result


def bootstrap_r(doses, isfs, n_boot=N_BOOTSTRAP):
    """Bootstrap 95% CI for Pearson r of dose vs ISF."""
    n = len(doses)
    if n < MIN_EVENTS_FIT:
        return None
    rs = []
    rng = np.random.default_rng(42)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        if np.std(doses[idx]) < 0.05 or np.std(isfs[idx]) < 0.01:
            continue
        r, _ = stats.pearsonr(doses[idx], isfs[idx])
        if not np.isnan(r):
            rs.append(r)
    if len(rs) < n_boot * 0.5:
        return None
    rs = np.array(rs)
    return {
        "r_median": round(float(np.median(rs)), 4),
        "ci_low": round(float(np.percentile(rs, 2.5)), 4),
        "ci_high": round(float(np.percentile(rs, 97.5)), 4),
        "n_valid_boots": len(rs),
    }


def analyze_patient(pid, events):
    """Full dose-dependence analysis for one patient."""
    n = len(events)
    doses = np.array([e["dose"] for e in events])
    demand_isfs = np.array([e["demand_isf"] for e in events])
    apparent_isfs = np.array([e["apparent_isf"] for e in events])

    result = {
        "n_events": n,
        "dose_range": [round(float(doses.min()), 2), round(float(doses.max()), 2)],
        "dose_mean": round(float(np.mean(doses)), 2),
        "dose_std": round(float(np.std(doses)), 2),
        "demand_isf_median": round(float(np.median(demand_isfs)), 1),
        "demand_isf_iqr": [round(float(np.percentile(demand_isfs, 25)), 1),
                           round(float(np.percentile(demand_isfs, 75)), 1)],
        "apparent_isf_median": round(float(np.median(apparent_isfs)), 1),
        "apparent_isf_iqr": [round(float(np.percentile(apparent_isfs, 25)), 1),
                             round(float(np.percentile(apparent_isfs, 75)), 1)],
        "inflation_ratio": round(float(np.median(apparent_isfs) / np.median(demand_isfs)), 2)
            if np.median(demand_isfs) > 0 else None,
    }

    # Fit dose-dependence models for both ISF types
    demand_fits = fit_dose_models(doses, demand_isfs)
    apparent_fits = fit_dose_models(doses, apparent_isfs)
    result["demand_dose_fits"] = demand_fits
    result["apparent_dose_fits"] = apparent_fits

    if demand_fits and apparent_fits:
        # Compare correlation strengths
        r_demand = abs(demand_fits["linear"]["r"])
        r_apparent = abs(apparent_fits["linear"]["r"])
        result["r_demand_linear"] = demand_fits["linear"]["r"]
        result["r_apparent_linear"] = apparent_fits["linear"]["r"]
        result["demand_weaker"] = r_demand < r_apparent
        result["r_difference"] = round(float(r_apparent - r_demand), 4)

        # Best model comparison
        result["demand_best_model"] = demand_fits["best_model"]
        result["apparent_best_model"] = apparent_fits["best_model"]
        result["demand_best_r"] = demand_fits["best_r"]
        result["apparent_best_r"] = apparent_fits["best_r"]

    # Bootstrap CIs
    demand_boot = bootstrap_r(doses, demand_isfs)
    apparent_boot = bootstrap_r(doses, apparent_isfs)
    result["demand_bootstrap"] = demand_boot
    result["apparent_bootstrap"] = apparent_boot

    # Raw data for visualization
    result["data"] = {
        "dose": [round(float(d), 2) for d in doses],
        "demand_isf": [round(float(i), 1) for i in demand_isfs],
        "apparent_isf": [round(float(i), 1) for i in apparent_isfs],
    }

    return result


def _safe_pearsonr(x, y):
    """Pearson r with NaN/Inf filtering."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3 or np.std(x[mask]) < 1e-12 or np.std(y[mask]) < 1e-12:
        return np.nan, np.nan
    return stats.pearsonr(x[mask], y[mask])


def cross_patient_analysis(all_events):
    """Pool all patients and compare dose-dependence strength."""
    doses = np.array([e["dose"] for e in all_events])
    demand_isfs = np.array([e["demand_isf"] for e in all_events])
    apparent_isfs = np.array([e["apparent_isf"] for e in all_events])
    patient_ids = [e["patient_id"] for e in all_events]

    result = {
        "n_events": len(all_events),
        "n_patients": len(set(patient_ids)),
    }

    # Overall correlations
    r_demand, p_demand = _safe_pearsonr(doses, demand_isfs)
    r_apparent, p_apparent = _safe_pearsonr(doses, apparent_isfs)
    result["overall_demand_r"] = round(float(r_demand), 4) if not np.isnan(r_demand) else None
    result["overall_demand_p"] = float(p_demand) if not np.isnan(p_demand) else None
    result["overall_apparent_r"] = round(float(r_apparent), 4) if not np.isnan(r_apparent) else None
    result["overall_apparent_p"] = float(p_apparent) if not np.isnan(p_apparent) else None
    result["demand_weaker"] = abs(r_demand) < abs(r_apparent)

    # Model fits
    result["demand_fits"] = fit_dose_models(doses, demand_isfs)
    result["apparent_fits"] = fit_dose_models(doses, apparent_isfs)

    # Bootstrap CIs
    result["demand_bootstrap"] = bootstrap_r(doses, demand_isfs)
    result["apparent_bootstrap"] = bootstrap_r(doses, apparent_isfs)

    # Dose-matched comparison: at standard doses, which ISF has lower CV?
    # Use per-event data, binned by dose
    dose_bins = [(0.3, 0.75), (0.75, 1.25), (1.25, 2.0), (2.0, 3.0), (3.0, 6.0)]
    bin_analysis = {}
    for lo, hi in dose_bins:
        mask = (doses >= lo) & (doses < hi)
        if mask.sum() < 5:
            continue
        d_isfs = demand_isfs[mask]
        a_isfs = apparent_isfs[mask]
        label = f"{lo}-{hi}U"
        bin_analysis[label] = {
            "n": int(mask.sum()),
            "dose_mean": round(float(doses[mask].mean()), 2),
            "demand_median": round(float(np.median(d_isfs)), 1),
            "demand_cv": round(float(np.std(d_isfs) / np.mean(d_isfs) * 100), 1) if np.mean(d_isfs) > 0 else None,
            "apparent_median": round(float(np.median(a_isfs)), 1),
            "apparent_cv": round(float(np.std(a_isfs) / np.mean(a_isfs) * 100), 1) if np.mean(a_isfs) > 0 else None,
        }
        if bin_analysis[label]["demand_cv"] and bin_analysis[label]["apparent_cv"]:
            bin_analysis[label]["demand_cv_lower"] = (
                bin_analysis[label]["demand_cv"] < bin_analysis[label]["apparent_cv"]
            )
    result["dose_bins"] = bin_analysis

    return result


def leave_one_patient_out(all_events):
    """LOO sensitivity: does removing one patient change the conclusion?"""
    patient_ids = sorted(set(e["patient_id"] for e in all_events))
    results = {}
    for exclude in patient_ids:
        subset = [e for e in all_events if e["patient_id"] != exclude]
        doses = np.array([e["dose"] for e in subset])
        demand_isfs = np.array([e["demand_isf"] for e in subset])
        apparent_isfs = np.array([e["apparent_isf"] for e in subset])

        r_d, p_d = _safe_pearsonr(doses, demand_isfs)
        r_a, p_a = _safe_pearsonr(doses, apparent_isfs)
        results[exclude] = {
            "n_remaining": len(subset),
            "demand_r": round(float(r_d), 4),
            "apparent_r": round(float(r_a), 4),
            "demand_weaker": abs(r_d) < abs(r_a),
        }
    return results


def egp_fraction_analysis(all_events):
    """Analyze what fraction of dose-dependence comes from EGP suppression.

    The EGP contribution to apparent ISF = (apparent_isf - demand_isf).
    If this EGP fraction is dose-dependent but demand ISF is not,
    that confirms EGP suppression drives the dose-dependence.
    """
    doses = np.array([e["dose"] for e in all_events])
    demand_isfs = np.array([e["demand_isf"] for e in all_events])
    apparent_isfs = np.array([e["apparent_isf"] for e in all_events])

    egp_isfs = apparent_isfs - demand_isfs  # EGP-attributed ISF portion

    result = {
        "egp_isf_median": round(float(np.median(egp_isfs)), 1),
        "egp_fraction_of_apparent": round(float(np.median(egp_isfs) / np.median(apparent_isfs)), 3)
            if np.median(apparent_isfs) > 0 else None,
    }

    # Correlate EGP-ISF with dose
    if len(doses) >= MIN_EVENTS_FIT and np.std(doses) > 0.05:
        r_egp, p_egp = _safe_pearsonr(doses, egp_isfs)
        result["egp_dose_r"] = round(float(r_egp), 4)
        result["egp_dose_p"] = float(p_egp)
        result["egp_fits"] = fit_dose_models(doses, egp_isfs)
        result["egp_bootstrap"] = bootstrap_r(doses, egp_isfs)

    return result


def test_hypotheses(per_patient, cross_patient, loo):
    """Evaluate all 5 hypotheses."""
    hypotheses = {}

    # H1: Demand ISF has weaker dose-dependence than apparent (per-patient majority)
    patients_with_fits = {pid: r for pid, r in per_patient.items()
                          if r.get("demand_dose_fits") and r.get("apparent_dose_fits")}
    n_weaker = sum(1 for r in patients_with_fits.values() if r.get("demand_weaker", False))
    n_total = len(patients_with_fits)
    hypotheses["H1_demand_weaker"] = {
        "description": "Demand ISF has weaker dose-dependence than apparent (majority of patients)",
        "n_demand_weaker": n_weaker,
        "n_total": n_total,
        "fraction": round(n_weaker / n_total, 2) if n_total > 0 else None,
        "pass": n_weaker > n_total / 2 if n_total > 0 else False,
    }

    # H2: Demand dose-slope is shallower per patient
    n_shallower = 0
    for pid, r in patients_with_fits.items():
        d_slope = abs(r["demand_dose_fits"]["linear"]["slope"])
        a_slope = abs(r["apparent_dose_fits"]["linear"]["slope"])
        if d_slope < a_slope:
            n_shallower += 1
    hypotheses["H2_shallower_slope"] = {
        "description": "Demand ISF dose-slope is shallower than apparent (per-patient)",
        "n_shallower": n_shallower,
        "n_total": n_total,
        "fraction": round(n_shallower / n_total, 2) if n_total > 0 else None,
        "pass": n_shallower > n_total / 2 if n_total > 0 else False,
    }

    # H3: Cross-patient demand ISF has lower CV at matched doses
    bins = cross_patient.get("dose_bins", {})
    n_lower_cv = sum(1 for b in bins.values() if b.get("demand_cv_lower", False))
    n_bins = len(bins)
    hypotheses["H3_lower_cv"] = {
        "description": "Demand ISF has lower CV than apparent at matched dose bins",
        "n_lower_cv": n_lower_cv,
        "n_bins": n_bins,
        "pass": n_lower_cv > n_bins / 2 if n_bins > 0 else False,
    }

    # H4: LOO robust — conclusion unchanged for all patients
    n_robust = sum(1 for v in loo.values() if v["demand_weaker"])
    n_loo = len(loo)
    hypotheses["H4_loo_robust"] = {
        "description": "Demand weaker conclusion holds for all LOO iterations",
        "n_hold": n_robust,
        "n_total": n_loo,
        "fraction": round(n_robust / n_loo, 2) if n_loo > 0 else None,
        "pass": n_robust == n_loo,
    }

    # H5: Demand ISF dose-dependence |r| < 0.3 for majority of patients
    n_weak = 0
    for pid, r in patients_with_fits.items():
        if abs(r["demand_dose_fits"]["linear"]["r"]) < 0.3:
            n_weak += 1
    hypotheses["H5_demand_weak_dependence"] = {
        "description": "Demand ISF dose-dependence |r| < 0.3 for majority of patients",
        "n_weak": n_weak,
        "n_total": n_total,
        "fraction": round(n_weak / n_total, 2) if n_total > 0 else None,
        "pass": n_weak > n_total / 2 if n_total > 0 else False,
    }

    return hypotheses


def main():
    parser = argparse.ArgumentParser(description="EXP-2663: Demand-Phase ISF Dose-Dependence")
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2663: Demand-Phase ISF Dose-Dependence")
    print("=" * 70)

    parquet_path = Path(args.parquet)
    if not parquet_path.exists():
        print(f"ERROR: {parquet_path} not found. Run 'make bootstrap' first.")
        sys.exit(1)

    df = pd.read_parquet(parquet_path)
    patients = sorted(df["patient_id"].unique())
    print(f"Loaded {len(df):,} rows, {len(patients)} patients from {parquet_path}")

    # ── Per-patient analysis ─────────────────────────────────────
    per_patient = {}
    all_events = []

    print("\n--- Per-Patient Analysis ---")
    for pid in patients:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            print(f"  {pid}: insufficient data ({len(pdf)} rows)")
            continue

        # Tiered extraction: strict 6h → lax 2h fallback
        events = extract_correction_events(pdf, PRIOR_BOLUS_H)
        iso_used = PRIOR_BOLUS_H
        if len(events) < MIN_EVENTS_FIT:
            events = extract_correction_events(pdf, LAX_PRIOR_BOLUS_H)
            iso_used = LAX_PRIOR_BOLUS_H
        if len(events) < MIN_EVENTS_FIT:
            print(f"  {pid}: insufficient corrections ({len(events)})")
            continue

        # Tag events with patient ID for cross-patient
        for e in events:
            e["patient_id"] = pid
        all_events.extend(events)

        result = analyze_patient(pid, events)
        per_patient[pid] = result

        # Print summary
        if result.get("demand_dose_fits") and result.get("apparent_dose_fits"):
            rd = result["r_demand_linear"]
            ra = result["r_apparent_linear"]
            weaker = "✓" if result.get("demand_weaker") else "✗"
            print(f"  {pid}: n={result['n_events']:>3}, "
                  f"demand r={rd:>7.3f}, apparent r={ra:>7.3f}, "
                  f"demand_weaker={weaker}, "
                  f"inflation={result.get('inflation_ratio', '?')}×, "
                  f"demand_ISF={result['demand_isf_median']:.0f}, "
                  f"apparent_ISF={result['apparent_isf_median']:.0f}")
        else:
            print(f"  {pid}: n={result['n_events']}, insufficient variance for fit")

    print(f"\nTotal: {len(all_events)} events across {len(per_patient)} patients")

    # ── Cross-patient analysis ───────────────────────────────────
    print("\n--- Cross-Patient Analysis ---")
    cross = cross_patient_analysis(all_events)
    print(f"  Overall demand r  = {cross['overall_demand_r']:.4f} (p={cross['overall_demand_p']:.2e})")
    print(f"  Overall apparent r = {cross['overall_apparent_r']:.4f} (p={cross['overall_apparent_p']:.2e})")
    print(f"  Demand weaker: {cross['demand_weaker']}")

    if cross.get("demand_fits"):
        print(f"  Demand best model: {cross['demand_fits']['best_model']} "
              f"(|r|={cross['demand_fits']['best_r']:.3f})")
    if cross.get("apparent_fits"):
        print(f"  Apparent best model: {cross['apparent_fits']['best_model']} "
              f"(|r|={cross['apparent_fits']['best_r']:.3f})")

    print("\n  Dose bins:")
    for label, b in sorted(cross.get("dose_bins", {}).items()):
        dcv = f"{b['demand_cv']:.0f}%" if b.get("demand_cv") else "?"
        acv = f"{b['apparent_cv']:.0f}%" if b.get("apparent_cv") else "?"
        winner = "demand" if b.get("demand_cv_lower") else "apparent"
        print(f"    {label:>8}: n={b['n']:>3}, "
              f"demand={b['demand_median']:>5.0f} (CV={dcv:>4}), "
              f"apparent={b['apparent_median']:>5.0f} (CV={acv:>4}) → {winner}")

    # ── EGP fraction analysis ────────────────────────────────────
    print("\n--- EGP Fraction Analysis ---")
    egp = egp_fraction_analysis(all_events)
    print(f"  EGP-attributed ISF (apparent - demand) median: {egp['egp_isf_median']:.1f} mg/dL/U")
    if egp.get("egp_fraction_of_apparent"):
        print(f"  EGP fraction of apparent ISF: {egp['egp_fraction_of_apparent']*100:.0f}%")
    if egp.get("egp_dose_r"):
        print(f"  EGP-ISF vs dose: r={egp['egp_dose_r']:.4f} (p={egp['egp_dose_p']:.2e})")
        if egp.get("egp_fits"):
            print(f"  EGP best model: {egp['egp_fits']['best_model']} "
                  f"(|r|={egp['egp_fits']['best_r']:.3f})")

    # ── Leave-one-patient-out ────────────────────────────────────
    print("\n--- Leave-One-Patient-Out ---")
    loo = leave_one_patient_out(all_events)
    for pid, v in sorted(loo.items()):
        print(f"  exclude {pid}: demand r={v['demand_r']:.3f}, "
              f"apparent r={v['apparent_r']:.3f}, "
              f"demand_weaker={v['demand_weaker']}")

    # ── Hypothesis testing ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS RESULTS")
    print("=" * 70)
    hyp = test_hypotheses(per_patient, cross, loo)
    for hid, h in sorted(hyp.items()):
        status = "PASS ✓" if h["pass"] else "FAIL ✗"
        detail = ""
        if "fraction" in h and h["fraction"] is not None:
            detail = f" ({h['fraction']*100:.0f}%)"
        elif "n_hold" in h:
            detail = f" ({h['n_hold']}/{h['n_total']})"
        print(f"  {hid}: {status}{detail}")
        print(f"    {h['description']}")

    # ── Clinical interpretation ──────────────────────────────────
    print("\n" + "=" * 70)
    print("CLINICAL INTERPRETATION")
    print("=" * 70)

    demand_r = abs(cross["overall_demand_r"])
    apparent_r = abs(cross["overall_apparent_r"])

    if demand_r < 0.2:
        dosing_rec = ("Demand ISF is approximately dose-INDEPENDENT.\n"
                      "    → Production can use constant per-patient demand ISF for dosing.\n"
                      "    → Simplifies recommendations: no dose-response curves needed.")
    elif demand_r < 0.4:
        dosing_rec = ("Demand ISF has WEAK dose-dependence.\n"
                      "    → Constant ISF is a reasonable approximation for typical doses.\n"
                      "    → Consider dose-adjustment only for extreme doses (>3× median).")
    else:
        dosing_rec = ("Demand ISF has STRONG dose-dependence.\n"
                      "    → Production must use dose-response curves (like apparent ISF).\n"
                      "    → ISF = f(dose) rather than a constant per patient.")

    print(f"  Demand ISF dose-dependence: |r|={demand_r:.3f}")
    print(f"  Apparent ISF dose-dependence: |r|={apparent_r:.3f}")
    print(f"  Conclusion: {dosing_rec}")

    if demand_r < apparent_r:
        print("\n  The dose-dependence is WEAKER for demand ISF than apparent ISF.")
        print("  This supports the hypothesis that EGP suppression drives dose-dependence.")
    else:
        print("\n  Unexpectedly, demand ISF is NOT less dose-dependent.")
        print("  Dose-dependence may reflect genuine insulin pharmacodynamics,")
        print("  not just EGP confounding.")

    # ── Save results ─────────────────────────────────────────────
    def convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"{type(obj)} not serializable")

    results = {
        "experiment": "EXP-2663",
        "title": "Demand-Phase ISF Dose-Dependence",
        "n_total_events": len(all_events),
        "n_patients": len(per_patient),
        "per_patient": per_patient,
        "cross_patient": cross,
        "egp_fraction": egp,
        "leave_one_out": loo,
        "hypotheses": hyp,
        "summary": {
            "overall_demand_r": cross["overall_demand_r"],
            "overall_apparent_r": cross["overall_apparent_r"],
            "demand_weaker_than_apparent": cross["demand_weaker"],
            "demand_dose_independent": demand_r < 0.2,
            "recommendation": "constant_isf" if demand_r < 0.3 else "dose_curve",
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
