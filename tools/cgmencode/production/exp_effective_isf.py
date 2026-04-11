#!/usr/bin/env python3
"""
exp_effective_isf.py — Cross-Validation of Effective ISF Estimation Methods
(EXP-2501–2508)

Two independent methods estimate that effective ISF differs from profile ISF:
  1. EXP-2387: Loop suspension model → ISF_eff = ISF / (1 - 0.3 × suspension%)
     Mean ratio: 1.22× (range 1.02-1.41)
  2. EXP-1301: Response-curve fitting → BG(t) = BG_start - amp × (1-exp(-t/τ))
     Mean ratio: 3.65× (range 1.52-7.60)

The 3× discrepancy between methods is itself a key finding:
  - Method 1 only accounts for BASAL suspension during corrections
  - Method 2 captures ALL confounds (basal suspension + temp basal increases
    elsewhere + ISF profile inaccuracy + variable insulin sensitivity)

This experiment cross-validates and reconciles these two methods to determine:
  - Which method is more appropriate for clinical recommendations?
  - What explains the discrepancy?
  - Can we decompose the ratio into basal-suspension vs other components?

Experiments:
  EXP-2501: Side-by-side comparison of both methods on 11 overlapping patients
  EXP-2502: Decompose response-curve ratio into suspension vs residual components
  EXP-2503: Correlation between methods — does the ranking agree?
  EXP-2504: Loop activity during correction windows (direct measurement)
  EXP-2505: ISF ratio vs time of day (circadian validation)
  EXP-2506: ISF ratio vs correction dose (dose-response linearity)
  EXP-2507: ISF ratio stability over time (rolling windows)
  EXP-2508: Reconciled ISF recommendation strategy

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_effective_isf.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_effective_isf.py --tiny
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
VIZ_DIR = ROOT / "visualizations" / "effective-isf"
RESULTS_DIR = ROOT / "externals" / "experiments"


def load_data(tiny: bool = False) -> pd.DataFrame:
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


def load_prior_results() -> tuple[dict, dict]:
    """Load results from EXP-1301 and EXP-2381-2388."""
    with open(RESULTS_DIR / "exp-1301_therapy.json") as f:
        exp1301 = json.load(f)
    with open(RESULTS_DIR / "exp-2381-2388_settings_simulation.json") as f:
        exp2387 = json.load(f)
    return exp1301, exp2387


def find_correction_boluses(pdf: pd.DataFrame, min_bolus: float = 0.5,
                            min_bg: float = 130.0, carb_window: int = 6,
                            window_steps: int = 72) -> list[dict]:
    """Find correction boluses: bolus ≥ min_bolus, no carbs ±30min, BG ≥ min_bg."""
    pdf = pdf.sort_values("time").copy()
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))
    iob = pdf["iob"].values if "iob" in pdf.columns else np.zeros(len(pdf))
    hours = pdf["hour"].values
    ab = pdf["actual_basal_rate"].values if "actual_basal_rate" in pdf.columns else np.zeros(len(pdf))
    sb = pdf["scheduled_basal_rate"].values if "scheduled_basal_rate" in pdf.columns else np.zeros(len(pdf))

    corrections = []
    n = len(glucose)

    for i in range(carb_window, n - window_steps):
        if bolus[i] < min_bolus:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < min_bg:
            continue
        # No carbs within ±30 min (6 steps)
        carb_window_slice = carbs[max(0, i - carb_window):min(n, i + carb_window + 1)]
        if np.nansum(carb_window_slice) > 1.0:
            continue

        # Extract post-correction window
        window_glucose = glucose[i:i + window_steps]
        window_hours = hours[i:i + window_steps]
        window_ab = ab[i:i + window_steps]
        window_sb = sb[i:i + window_steps]
        window_iob = iob[i:i + window_steps]

        valid = np.isfinite(window_glucose)
        if valid.sum() < 12:
            continue

        # Loop suspension metrics during correction
        valid_basal = np.isfinite(window_ab) & np.isfinite(window_sb) & (window_sb > 0.01) & (window_ab < 50)
        if valid_basal.sum() > 6:
            ratio = window_ab[valid_basal] / window_sb[valid_basal]
            suspension_pct = float(np.mean(ratio < 0.1) * 100)
            mean_ratio = float(np.mean(ratio))
        else:
            suspension_pct = 0.0
            mean_ratio = 1.0

        # Response curve: fit exponential decay
        t = np.arange(valid.sum()) * 5.0 / 60.0  # hours
        g = window_glucose[valid]
        bg_start = g[0]
        nadir = float(np.min(g))
        amplitude = bg_start - nadir

        # Simple ISF: amplitude / bolus dose
        simple_isf = amplitude / bolus[i] if bolus[i] > 0 else 0

        # Fit exponential: BG(t) = BG_start - A × (1 - exp(-t/τ))
        curve_isf = 0.0
        fit_r2 = 0.0
        tau = 2.0
        if amplitude > 5 and len(t) > 6:
            try:
                from scipy.optimize import curve_fit
                def model(t, A, tau):
                    return bg_start - A * (1 - np.exp(-t / max(tau, 0.1)))
                popt, _ = curve_fit(model, t, g, p0=[amplitude, 2.0],
                                    bounds=([0, 0.1], [500, 10]),
                                    maxfev=2000)
                A_fit, tau_fit = popt
                g_pred = model(t, A_fit, tau_fit)
                ss_res = np.sum((g - g_pred) ** 2)
                ss_tot = np.sum((g - np.mean(g)) ** 2)
                fit_r2 = float(1 - ss_res / max(ss_tot, 1e-6))
                curve_isf = float(A_fit / bolus[i])
                tau = float(tau_fit)
            except Exception:
                pass

        corrections.append({
            "index": int(i),
            "bolus_dose": float(bolus[i]),
            "bg_start": float(bg_start),
            "nadir": nadir,
            "amplitude": float(amplitude),
            "simple_isf": simple_isf,
            "curve_isf": curve_isf,
            "fit_r2": fit_r2,
            "tau_hours": tau,
            "hour_of_day": float(hours[i]),
            "suspension_pct": suspension_pct,
            "mean_basal_ratio": mean_ratio,
            "iob_at_correction": float(iob[i]) if np.isfinite(iob[i]) else 0.0,
        })

    return corrections


# ── EXP-2501: Side-by-Side Comparison ────────────────────────────────

def exp_2501_method_comparison(df: pd.DataFrame) -> dict:
    """Compare loop-suspension ISF vs response-curve ISF across all patients."""
    print("EXP-2501: Method comparison")
    exp1301, exp2387 = load_prior_results()

    # Build lookup from EXP-1301
    curve_ratios = {}
    for item in exp1301["per_patient"]:
        curve_ratios[item["patient"]] = {
            "curve_isf": item["mean_isf_curve"],
            "profile_isf": item["mean_isf_profile"],
            "ratio": item["curve_vs_profile_ratio"],
            "tau": item["mean_tau_hours"],
            "r2": item["mean_fit_r2"],
            "n_corrections": item["n_corrections"],
        }

    # Build lookup from EXP-2387
    sim_ratios = {}
    e2387 = exp2387["exp_2387"]
    for pid, v in e2387.items():
        if isinstance(v, dict) and "isf_ratio" in v:
            sim_ratios[pid] = v["isf_ratio"]

    # Compare on overlapping patients
    overlap = set(curve_ratios.keys()) & set(sim_ratios.keys())
    comparison = []
    for pid in sorted(overlap):
        cr = curve_ratios[pid]
        sr = sim_ratios[pid]
        comparison.append({
            "patient": pid,
            "response_curve_ratio": cr["ratio"],
            "loop_suspension_ratio": sr,
            "discrepancy": cr["ratio"] / sr,
            "response_curve_isf": cr["curve_isf"],
            "profile_isf": cr["profile_isf"],
            "fit_r2": cr["r2"],
            "tau": cr["tau"],
            "n_corrections": cr["n_corrections"],
        })

    if comparison:
        curve_vals = [c["response_curve_ratio"] for c in comparison]
        sim_vals = [c["loop_suspension_ratio"] for c in comparison]
        disc = [c["discrepancy"] for c in comparison]

        # Correlation between methods
        if len(curve_vals) > 2:
            corr = float(np.corrcoef(curve_vals, sim_vals)[0, 1])
        else:
            corr = float('nan')

        # Rank correlation (Spearman)
        from scipy.stats import spearmanr
        if len(curve_vals) > 2:
            rho, p_val = spearmanr(curve_vals, sim_vals)
        else:
            rho, p_val = float('nan'), float('nan')

        print(f"  Overlapping patients: {len(overlap)}")
        print(f"  Response-curve ratio: {np.mean(curve_vals):.2f}× (range {min(curve_vals):.2f}-{max(curve_vals):.2f})")
        print(f"  Loop-suspension ratio: {np.mean(sim_vals):.2f}× (range {min(sim_vals):.2f}-{max(sim_vals):.2f})")
        print(f"  Discrepancy (curve/sim): {np.mean(disc):.2f}× (range {min(disc):.2f}-{max(disc):.2f})")
        print(f"  Pearson r: {corr:.3f}")
        print(f"  Spearman ρ: {rho:.3f} (p={p_val:.4f})")
    else:
        corr, rho, p_val = float('nan'), float('nan'), float('nan')

    return {
        "n_overlap": len(overlap),
        "comparison": comparison,
        "pearson_r": float(corr) if np.isfinite(corr) else None,
        "spearman_rho": float(rho) if np.isfinite(rho) else None,
        "spearman_p": float(p_val) if np.isfinite(p_val) else None,
        "mean_discrepancy": float(np.mean(disc)) if comparison else None,
    }


# ── EXP-2502: Decompose Response-Curve Ratio ────────────────────────

def exp_2502_decompose_ratio(df: pd.DataFrame) -> dict:
    """Decompose response-curve ISF ratio into suspension vs residual components."""
    print("EXP-2502: Decompose ISF ratio")
    results = {}
    patients = sorted(df["patient_id"].unique())

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        if len(corrections) < 5:
            continue

        # Get profile ISF
        if "isf" in pdf.columns:
            profile_isf = float(pdf["isf"].dropna().median())
        else:
            profile_isf = 50.0

        # Filter for good fits
        good = [c for c in corrections if c["fit_r2"] > 0.3 and c["curve_isf"] > 0]
        if len(good) < 3:
            continue

        mean_curve_isf = float(np.mean([c["curve_isf"] for c in good]))
        mean_suspension = float(np.mean([c["suspension_pct"] for c in good]))
        mean_basal_ratio = float(np.mean([c["mean_basal_ratio"] for c in good]))

        # Suspension component: ISF_suspension = profile_ISF / (1 - 0.3 × susp%)
        suspension_factor = 1.0 / (1.0 - 0.3 * mean_suspension / 100.0) if mean_suspension < 95 else 3.0
        suspension_isf = profile_isf * suspension_factor

        # Total curve ratio
        total_ratio = mean_curve_isf / profile_isf if profile_isf > 0 else 1.0

        # Residual = total / suspension component
        residual_ratio = total_ratio / suspension_factor if suspension_factor > 0 else total_ratio

        results[pid] = {
            "n_corrections": len(good),
            "profile_isf": profile_isf,
            "curve_isf": round(mean_curve_isf, 1),
            "total_ratio": round(total_ratio, 2),
            "suspension_pct": round(mean_suspension, 1),
            "suspension_factor": round(suspension_factor, 2),
            "residual_ratio": round(residual_ratio, 2),
            "mean_basal_ratio": round(mean_basal_ratio, 2),
        }

        print(f"  {pid}: total={total_ratio:.2f}× = suspension({suspension_factor:.2f}×) × residual({residual_ratio:.2f}×)")

    if results:
        total_ratios = [v["total_ratio"] for v in results.values()]
        susp_factors = [v["suspension_factor"] for v in results.values()]
        resid_ratios = [v["residual_ratio"] for v in results.values()]
        print(f"\n  Population total ratio: {np.mean(total_ratios):.2f}×")
        print(f"  Population suspension factor: {np.mean(susp_factors):.2f}×")
        print(f"  Population residual ratio: {np.mean(resid_ratios):.2f}×")

    return {
        "per_patient": results,
        "population_mean_total": round(float(np.mean(total_ratios)), 2) if results else None,
        "population_mean_suspension": round(float(np.mean(susp_factors)), 2) if results else None,
        "population_mean_residual": round(float(np.mean(resid_ratios)), 2) if results else None,
    }


# ── EXP-2503: Rank Correlation ──────────────────────────────────────

def exp_2503_rank_correlation(df: pd.DataFrame) -> dict:
    """Do the methods rank patients the same way?"""
    print("EXP-2503: Rank correlation")
    # Recompute from raw data to include all 19 patients
    patients = sorted(df["patient_id"].unique())
    patient_data = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        good = [c for c in corrections if c["fit_r2"] > 0.3 and c["curve_isf"] > 0]
        if len(good) < 3:
            continue

        if "isf" in pdf.columns:
            profile_isf = float(pdf["isf"].dropna().median())
        else:
            profile_isf = 50.0

        # Response-curve ratio
        mean_curve_isf = float(np.mean([c["curve_isf"] for c in good]))
        curve_ratio = mean_curve_isf / profile_isf if profile_isf > 0 else 1.0

        # Suspension-based ratio
        mean_susp = float(np.mean([c["suspension_pct"] for c in good]))
        susp_ratio = 1.0 / (1.0 - 0.3 * mean_susp / 100.0) if mean_susp < 95 else 3.0

        patient_data[pid] = {
            "curve_ratio": round(curve_ratio, 2),
            "suspension_ratio": round(susp_ratio, 2),
            "n_corrections": len(good),
        }

    if len(patient_data) > 3:
        from scipy.stats import spearmanr, kendalltau
        curve = [v["curve_ratio"] for v in patient_data.values()]
        susp = [v["suspension_ratio"] for v in patient_data.values()]

        rho, rho_p = spearmanr(curve, susp)
        tau, tau_p = kendalltau(curve, susp)

        print(f"  {len(patient_data)} patients")
        print(f"  Spearman ρ: {rho:.3f} (p={rho_p:.4f})")
        print(f"  Kendall τ: {tau:.3f} (p={tau_p:.4f})")
    else:
        rho, rho_p, tau, tau_p = [float('nan')] * 4

    return {
        "per_patient": patient_data,
        "n_patients": len(patient_data),
        "spearman_rho": round(float(rho), 3) if np.isfinite(rho) else None,
        "spearman_p": round(float(rho_p), 4) if np.isfinite(rho_p) else None,
        "kendall_tau": round(float(tau), 3) if np.isfinite(tau) else None,
        "kendall_p": round(float(tau_p), 4) if np.isfinite(tau_p) else None,
    }


# ── EXP-2504: Loop Activity During Corrections ──────────────────────

def exp_2504_loop_during_corrections(df: pd.DataFrame) -> dict:
    """Directly measure loop activity during correction windows."""
    print("EXP-2504: Loop activity during corrections")
    patients = sorted(df["patient_id"].unique())
    patient_results = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        if len(corrections) < 5:
            continue

        suspensions = [c["suspension_pct"] for c in corrections]
        ratios = [c["mean_basal_ratio"] for c in corrections]
        doses = [c["bolus_dose"] for c in corrections]

        # Does loop respond more to larger corrections?
        if len(doses) > 5:
            corr_dose_susp = float(np.corrcoef(doses, suspensions)[0, 1])
        else:
            corr_dose_susp = float('nan')

        patient_results[pid] = {
            "n_corrections": len(corrections),
            "mean_suspension_pct": round(float(np.mean(suspensions)), 1),
            "median_suspension_pct": round(float(np.median(suspensions)), 1),
            "mean_basal_ratio": round(float(np.mean(ratios)), 2),
            "pct_with_suspension": round(float(100 * np.mean(np.array(suspensions) > 5)), 1),
            "dose_suspension_corr": round(corr_dose_susp, 3) if np.isfinite(corr_dose_susp) else None,
        }
        print(f"  {pid}: suspension={np.mean(suspensions):.1f}%, "
              f"ratio={np.mean(ratios):.2f}, "
              f"dose-susp r={corr_dose_susp:.3f}" if np.isfinite(corr_dose_susp) else
              f"  {pid}: suspension={np.mean(suspensions):.1f}%, "
              f"ratio={np.mean(ratios):.2f}")

    if patient_results:
        all_susp = [v["mean_suspension_pct"] for v in patient_results.values()]
        all_ratio = [v["mean_basal_ratio"] for v in patient_results.values()]
        print(f"\n  Population: suspension={np.mean(all_susp):.1f}%, ratio={np.mean(all_ratio):.2f}")

    return {
        "per_patient": patient_results,
        "population_mean_suspension": round(float(np.mean(all_susp)), 1) if patient_results else None,
        "population_mean_ratio": round(float(np.mean(all_ratio)), 2) if patient_results else None,
    }


# ── EXP-2505: Circadian ISF Variation ────────────────────────────────

def exp_2505_circadian_isf(df: pd.DataFrame) -> dict:
    """ISF ratio by time of day — does it vary with circadian rhythm?"""
    print("EXP-2505: Circadian ISF variation")
    patients = sorted(df["patient_id"].unique())

    period_isf = {"overnight": [], "morning": [], "afternoon": [], "evening": []}
    periods = {"overnight": (0, 6), "morning": (6, 12), "afternoon": (12, 18), "evening": (18, 24)}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        good = [c for c in corrections if c["fit_r2"] > 0.3 and c["curve_isf"] > 0]

        if len(good) < 10:
            continue

        for period, (h_start, h_end) in periods.items():
            period_corrs = [c for c in good if h_start <= c["hour_of_day"] < h_end]
            if len(period_corrs) >= 3:
                mean_isf = float(np.mean([c["curve_isf"] for c in period_corrs]))
                period_isf[period].append(mean_isf)

    result = {}
    for period, values in period_isf.items():
        if values:
            result[period] = {
                "n_patients": len(values),
                "mean_isf": round(float(np.mean(values)), 1),
                "std_isf": round(float(np.std(values)), 1),
            }
            print(f"  {period}: n={len(values)}, mean ISF={np.mean(values):.1f} ± {np.std(values):.1f}")

    return result


# ── EXP-2506: Dose-Response Linearity ────────────────────────────────

def exp_2506_dose_response(df: pd.DataFrame) -> dict:
    """Is ISF constant across different bolus doses?"""
    print("EXP-2506: Dose-response linearity")
    patients = sorted(df["patient_id"].unique())
    patient_results = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        good = [c for c in corrections if c["fit_r2"] > 0.3 and c["curve_isf"] > 0]

        if len(good) < 10:
            continue

        doses = np.array([c["bolus_dose"] for c in good])
        isfs = np.array([c["curve_isf"] for c in good])

        # Correlation between dose and ISF
        corr = float(np.corrcoef(doses, isfs)[0, 1]) if len(doses) > 3 else float('nan')

        # Split into small vs large dose
        median_dose = float(np.median(doses))
        small = isfs[doses <= median_dose]
        large = isfs[doses > median_dose]

        patient_results[pid] = {
            "n_corrections": len(good),
            "dose_isf_corr": round(corr, 3) if np.isfinite(corr) else None,
            "small_dose_isf": round(float(np.mean(small)), 1) if len(small) > 0 else None,
            "large_dose_isf": round(float(np.mean(large)), 1) if len(large) > 0 else None,
            "is_linear": abs(corr) < 0.3 if np.isfinite(corr) else None,
        }
        lin = "linear" if patient_results[pid]["is_linear"] else "non-linear"
        print(f"  {pid}: r={corr:.3f} ({lin})")

    if patient_results:
        linear_count = sum(1 for v in patient_results.values() if v.get("is_linear"))
        total = len(patient_results)
        print(f"\n  Linear dose-response: {linear_count}/{total} patients")

    return {
        "per_patient": patient_results,
        "n_linear": sum(1 for v in patient_results.values() if v.get("is_linear")),
        "n_total": len(patient_results),
    }


# ── EXP-2507: ISF Stability Over Time ───────────────────────────────

def exp_2507_isf_stability(df: pd.DataFrame) -> dict:
    """Is ISF stable over the data collection period?"""
    print("EXP-2507: ISF stability over time")
    patients = sorted(df["patient_id"].unique())
    patient_results = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        corrections = find_correction_boluses(pdf)
        good = [c for c in corrections if c["fit_r2"] > 0.3 and c["curve_isf"] > 0]

        if len(good) < 20:
            continue

        isfs = [c["curve_isf"] for c in good]
        indices = [c["index"] for c in good]

        # Split into first half / second half
        mid = len(isfs) // 2
        first_half = isfs[:mid]
        second_half = isfs[mid:]

        mean_first = float(np.mean(first_half))
        mean_second = float(np.mean(second_half))
        drift_pct = ((mean_second - mean_first) / mean_first * 100) if mean_first > 0 else 0

        # Rolling CV
        cv = float(np.std(isfs) / np.mean(isfs) * 100) if np.mean(isfs) > 0 else 0

        patient_results[pid] = {
            "n_corrections": len(good),
            "first_half_isf": round(mean_first, 1),
            "second_half_isf": round(mean_second, 1),
            "drift_pct": round(drift_pct, 1),
            "cv_pct": round(cv, 1),
            "is_stable": abs(drift_pct) < 20 and cv < 60,
        }
        stable = "stable" if patient_results[pid]["is_stable"] else "DRIFTING"
        print(f"  {pid}: drift={drift_pct:+.1f}%, CV={cv:.0f}% ({stable})")

    if patient_results:
        stable_count = sum(1 for v in patient_results.values() if v.get("is_stable"))
        print(f"\n  Stable ISF: {stable_count}/{len(patient_results)} patients")

    return {
        "per_patient": patient_results,
        "n_stable": sum(1 for v in patient_results.values() if v.get("is_stable")),
        "n_total": len(patient_results),
    }


# ── EXP-2508: Reconciled ISF Strategy ───────────────────────────────

def exp_2508_reconciled_strategy(exp2501: dict, exp2502: dict,
                                  exp2504: dict, exp2506: dict) -> dict:
    """Synthesize findings into a reconciled ISF recommendation strategy."""
    print("EXP-2508: Reconciled ISF strategy")

    insights = []

    # 1. Discrepancy analysis
    if exp2501.get("mean_discrepancy"):
        disc = exp2501["mean_discrepancy"]
        insights.append(f"Response-curve ISF is {disc:.1f}× higher than loop-suspension ISF.")
        insights.append("Loop suspension accounts for only a fraction of the total ISF discrepancy.")

    # 2. Decomposition
    if exp2502.get("population_mean_suspension") and exp2502.get("population_mean_residual"):
        susp = exp2502["population_mean_suspension"]
        resid = exp2502["population_mean_residual"]
        total = exp2502["population_mean_total"]
        insights.append(
            f"ISF ratio decomposes: {total:.2f}× total = "
            f"{susp:.2f}× (suspension) × {resid:.2f}× (residual).")
        if resid > 1.5:
            insights.append(
                "Large residual ratio suggests profile ISF is fundamentally wrong, "
                "not just confounded by loop behavior.")
        else:
            insights.append(
                "Small residual ratio suggests loop suspension is the primary confounder.")

    # 3. Dose-response
    if exp2506.get("n_total") and exp2506.get("n_linear"):
        lin = exp2506["n_linear"]
        total = exp2506["n_total"]
        insights.append(
            f"Dose-response linearity: {lin}/{total} patients show linear ISF "
            f"(ISF doesn't change with dose size).")

    # 4. Recommendation
    recommendation = (
        "For clinical ISF recommendations, use the loop-suspension model (1.22×) as "
        "the conservative adjustment, since it only corrects for the measurable "
        "confound. The response-curve method captures real ISF variation but includes "
        "unmeasured confounds (time-varying sensitivity, counter-regulatory responses) "
        "that make the ratio unreliable for direct use in pump settings. "
        "Recommend ISF increase of 10-20% (not the full response-curve amount) "
        "to reduce loop workload while maintaining safety margins."
    )
    insights.append(recommendation)

    for i, insight in enumerate(insights):
        print(f"  [{i+1}] {insight}")

    return {
        "insights": insights,
        "recommended_approach": "loop_suspension_conservative",
        "recommended_isf_adjustment_range_pct": [10, 20],
    }


# ── Visualization ────────────────────────────────────────────────────

def generate_visualizations(exp2501: dict, exp2502: dict, exp2504: dict):
    """Generate comparison visualizations."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping visualizations")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Method comparison scatter
    if exp2501.get("comparison"):
        comp = exp2501["comparison"]
        fig, ax = plt.subplots(figsize=(8, 6))
        curve = [c["response_curve_ratio"] for c in comp]
        sim = [c["loop_suspension_ratio"] for c in comp]
        pids = [c["patient"] for c in comp]

        ax.scatter(sim, curve, s=80, c='steelblue', edgecolors='navy', alpha=0.8, zorder=3)
        for i, pid in enumerate(pids):
            ax.annotate(pid, (sim[i], curve[i]), fontsize=8,
                        xytext=(5, 5), textcoords='offset points')

        # Unity line and identity
        lims = [0.8, max(max(curve), max(sim)) * 1.1]
        ax.plot(lims, lims, '--', color='gray', alpha=0.5, label='1:1 line')
        ax.set_xlabel("Loop Suspension ISF Ratio (EXP-2387)", fontsize=12)
        ax.set_ylabel("Response-Curve ISF Ratio (EXP-1301)", fontsize=12)
        ax.set_title("ISF Estimation: Two Methods Diverge", fontsize=14)

        r = exp2501.get("pearson_r", "N/A")
        ax.text(0.05, 0.95, f"Pearson r = {r:.3f}" if isinstance(r, float) else f"r = {r}",
                transform=ax.transAxes, fontsize=11, va='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax.legend()
        fig.tight_layout()
        fig.savefig(VIZ_DIR / "fig1_method_comparison.png", dpi=150)
        plt.close(fig)
        print(f"  Saved {VIZ_DIR / 'fig1_method_comparison.png'}")

    # Fig 2: Decomposition bar chart
    if exp2502.get("per_patient"):
        pp = exp2502["per_patient"]
        fig, ax = plt.subplots(figsize=(10, 6))
        pids = sorted(pp.keys())
        x = np.arange(len(pids))
        total = [pp[p]["total_ratio"] for p in pids]
        susp = [pp[p]["suspension_factor"] for p in pids]
        resid = [pp[p]["residual_ratio"] for p in pids]

        width = 0.25
        ax.bar(x - width, total, width, label='Total (curve)', color='steelblue')
        ax.bar(x, susp, width, label='Suspension component', color='salmon')
        ax.bar(x + width, resid, width, label='Residual component', color='seagreen')

        ax.set_xlabel("Patient")
        ax.set_ylabel("ISF Ratio (vs profile)")
        ax.set_title("ISF Ratio Decomposition: Suspension vs Residual")
        ax.set_xticks(x)
        ax.set_xticklabels(pids, rotation=45, ha='right', fontsize=8)
        ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
        ax.legend()
        fig.tight_layout()
        fig.savefig(VIZ_DIR / "fig2_isf_decomposition.png", dpi=150)
        plt.close(fig)
        print(f"  Saved {VIZ_DIR / 'fig2_isf_decomposition.png'}")

    # Fig 3: Loop activity during corrections
    if exp2504.get("per_patient"):
        pp = exp2504["per_patient"]
        fig, ax = plt.subplots(figsize=(8, 6))
        pids = sorted(pp.keys())
        susp = [pp[p]["mean_suspension_pct"] for p in pids]
        ratio = [pp[p]["mean_basal_ratio"] for p in pids]

        colors = ['crimson' if s > 30 else 'steelblue' for s in susp]
        ax.barh(pids, susp, color=colors, edgecolor='navy', alpha=0.8)
        ax.set_xlabel("Mean Suspension % During Corrections")
        ax.set_title("Loop Suspension During Correction Windows")
        ax.axvline(x=30, color='red', linestyle='--', alpha=0.5, label='High suspension threshold')
        ax.legend()
        fig.tight_layout()
        fig.savefig(VIZ_DIR / "fig3_correction_suspension.png", dpi=150)
        plt.close(fig)
        print(f"  Saved {VIZ_DIR / 'fig3_correction_suspension.png'}")


# ── Main ─────────────────────────────────────────────────────────────

def convert(obj):
    """JSON serializer for numpy types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    print("=" * 60)
    print("EFFECTIVE ISF CROSS-VALIDATION (EXP-2501–2508)")
    print("=" * 60)

    results = {}

    # EXP-2501: Method comparison
    try:
        results["exp_2501"] = exp_2501_method_comparison(df)
    except Exception as e:
        print(f"  EXP-2501 failed: {e}")
        results["exp_2501"] = {"error": str(e)}

    print()

    # EXP-2502: Decomposition
    results["exp_2502"] = exp_2502_decompose_ratio(df)
    print()

    # EXP-2503: Rank correlation
    results["exp_2503"] = exp_2503_rank_correlation(df)
    print()

    # EXP-2504: Loop during corrections
    results["exp_2504"] = exp_2504_loop_during_corrections(df)
    print()

    # EXP-2505: Circadian ISF
    results["exp_2505"] = exp_2505_circadian_isf(df)
    print()

    # EXP-2506: Dose-response
    results["exp_2506"] = exp_2506_dose_response(df)
    print()

    # EXP-2507: Stability
    results["exp_2507"] = exp_2507_isf_stability(df)
    print()

    # EXP-2508: Reconciled strategy
    results["exp_2508"] = exp_2508_reconciled_strategy(
        results.get("exp_2501", {}),
        results.get("exp_2502", {}),
        results.get("exp_2504", {}),
        results.get("exp_2506", {}))

    # Visualizations
    print()
    try:
        generate_visualizations(
            results.get("exp_2501", {}),
            results.get("exp_2502", {}),
            results.get("exp_2504", {}))
    except Exception as e:
        print(f"  Visualization failed: {e}")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "exp-2501-2508_effective_isf_crossval.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
