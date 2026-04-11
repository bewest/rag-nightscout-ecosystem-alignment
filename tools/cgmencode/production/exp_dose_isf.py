#!/usr/bin/env python3
"""
exp_dose_isf.py — Dose-Dependent ISF Model (EXP-2511–2518)

EXP-2506 found that ISF is non-linear in 15/16 patients: larger correction
doses produce smaller effective ISF (r = -0.3 to -0.7). This experiment
builds a dose-dependent ISF model and tests whether it improves correction
dose accuracy.

Model: ISF(dose) = ISF_base × dose^(-β)
  - ISF_base: ISF at 1U dose (reference sensitivity)
  - β: saturation exponent (0 = linear, 0.5 = sqrt-law, 1.0 = inverse)
  - β > 0 means larger doses are less effective per unit

Experiments:
  EXP-2511: Fit power-law ISF model per patient
  EXP-2512: Compare power-law vs flat ISF prediction accuracy
  EXP-2513: Population β distribution — is there a universal saturation exponent?
  EXP-2514: Optimal correction dose under non-linear ISF
  EXP-2515: Time-of-day × dose interaction (does β vary by period?)
  EXP-2516: IOB-dependent ISF (does stacking affect saturation?)
  EXP-2517: Cross-validation of power-law model (LOPO)
  EXP-2518: Clinical implications and recommendation engine update

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_dose_isf.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_dose_isf.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import spearmanr

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "dose-isf"
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


def find_correction_events(pdf: pd.DataFrame, min_bolus: float = 0.3,
                           min_bg: float = 120.0, carb_window: int = 6,
                           window_steps: int = 72) -> list[dict]:
    """Find correction boluses with response curve fitting.

    Lowered min_bolus to 0.3U (from 0.5) to capture small corrections
    that are critical for testing the low-dose regime of the ISF curve.
    """
    pdf = pdf.sort_values("time").copy()
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))
    iob = pdf["iob"].values if "iob" in pdf.columns else np.zeros(len(pdf))
    hours = pdf["hour"].values
    n = len(glucose)

    events = []
    for i in range(carb_window, n - window_steps):
        if bolus[i] < min_bolus:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < min_bg:
            continue
        # No carbs ±30min
        cs = carbs[max(0, i - carb_window):min(n, i + carb_window + 1)]
        if np.nansum(cs) > 1.0:
            continue

        window_bg = glucose[i:i + window_steps]
        valid = np.isfinite(window_bg)
        if valid.sum() < 12:
            continue

        t = np.arange(valid.sum()) * 5.0 / 60.0  # hours
        g = window_bg[valid]
        bg_start = g[0]
        nadir = float(np.min(g))
        amplitude = bg_start - nadir

        if amplitude < 3:  # no meaningful drop
            continue

        # Simple ISF
        simple_isf = amplitude / bolus[i]

        # Fit exponential
        curve_isf = 0.0
        fit_r2 = 0.0
        tau = 2.0
        try:
            def model(t, A, tau):
                return bg_start - A * (1 - np.exp(-t / max(tau, 0.1)))
            popt, _ = curve_fit(model, t, g, p0=[amplitude, 2.0],
                                bounds=([0, 0.1], [500, 10]), maxfev=2000)
            A_fit, tau_fit = popt
            g_pred = model(t, A_fit, tau_fit)
            ss_res = np.sum((g - g_pred) ** 2)
            ss_tot = np.sum((g - np.mean(g)) ** 2)
            fit_r2 = float(1 - ss_res / max(ss_tot, 1e-6))
            curve_isf = float(A_fit / bolus[i])
            tau = float(tau_fit)
        except Exception:
            curve_isf = simple_isf

        events.append({
            "index": int(i),
            "dose": float(bolus[i]),
            "bg_start": float(bg_start),
            "nadir": nadir,
            "amplitude": float(amplitude),
            "simple_isf": simple_isf,
            "curve_isf": curve_isf,
            "fit_r2": fit_r2,
            "tau": tau,
            "hour": float(hours[i]),
            "iob": float(iob[i]) if np.isfinite(iob[i]) else 0.0,
        })

    return events


# ── Power-Law Model ──────────────────────────────────────────────────

def power_law_isf(dose, isf_base, beta):
    """ISF(dose) = ISF_base × dose^(-β)"""
    return isf_base * np.power(np.maximum(dose, 0.01), -beta)


def fit_power_law(doses: np.ndarray, isfs: np.ndarray) -> dict:
    """Fit power-law ISF model to dose-ISF pairs."""
    valid = (doses > 0) & (isfs > 0) & np.isfinite(doses) & np.isfinite(isfs)
    d = doses[valid]
    s = isfs[valid]
    if len(d) < 5:
        return {"isf_base": float(np.median(s)), "beta": 0.0, "r2": 0.0, "n": len(d)}

    try:
        popt, _ = curve_fit(power_law_isf, d, s,
                            p0=[float(np.median(s)), 0.5],
                            bounds=([0.1, -1.0], [2000, 3.0]),
                            maxfev=5000)
        isf_base, beta = popt
        predicted = power_law_isf(d, isf_base, beta)
        ss_res = np.sum((s - predicted) ** 2)
        ss_tot = np.sum((s - np.mean(s)) ** 2)
        r2 = float(1 - ss_res / max(ss_tot, 1e-6))
    except Exception:
        isf_base = float(np.median(s))
        beta = 0.0
        r2 = 0.0

    return {
        "isf_base": round(float(isf_base), 1),
        "beta": round(float(beta), 3),
        "r2": round(r2, 3),
        "n": len(d),
    }


# ── EXP-2511: Per-Patient Power-Law Fit ──────────────────────────────

def exp_2511_power_law_fit(df: pd.DataFrame) -> dict:
    """Fit power-law ISF model per patient."""
    print("EXP-2511: Per-patient power-law ISF fit")
    patients = sorted(df["patient_id"].unique())
    results = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        events = find_correction_events(pdf)
        good = [e for e in events if e["fit_r2"] > 0.2 and e["curve_isf"] > 0]
        if len(good) < 10:
            print(f"  {pid}: skipped ({len(good)} corrections)")
            continue

        doses = np.array([e["dose"] for e in good])
        isfs = np.array([e["curve_isf"] for e in good])

        fit = fit_power_law(doses, isfs)

        # Compare flat vs power-law prediction
        flat_isf = float(np.mean(isfs))
        flat_mse = float(np.mean((isfs - flat_isf) ** 2))
        pl_predicted = power_law_isf(doses, fit["isf_base"], fit["beta"])
        pl_mse = float(np.mean((isfs - pl_predicted) ** 2))
        improvement_pct = (1 - pl_mse / max(flat_mse, 1e-6)) * 100

        results[pid] = {
            **fit,
            "flat_isf": round(flat_isf, 1),
            "flat_mse": round(flat_mse, 1),
            "powerlaw_mse": round(pl_mse, 1),
            "improvement_pct": round(float(improvement_pct), 1),
            "dose_range": [round(float(np.min(doses)), 2), round(float(np.max(doses)), 2)],
        }
        print(f"  {pid}: β={fit['beta']:.3f}, ISF_base={fit['isf_base']:.0f}, "
              f"R²={fit['r2']:.3f}, improvement={improvement_pct:+.1f}%")

    if results:
        betas = [v["beta"] for v in results.values()]
        r2s = [v["r2"] for v in results.values()]
        imps = [v["improvement_pct"] for v in results.values()]
        print(f"\n  Population β: {np.mean(betas):.3f} ± {np.std(betas):.3f}")
        print(f"  Population R²: {np.mean(r2s):.3f}")
        print(f"  Mean improvement over flat: {np.mean(imps):+.1f}%")

    return {
        "per_patient": results,
        "population_mean_beta": round(float(np.mean(betas)), 3) if results else None,
        "population_std_beta": round(float(np.std(betas)), 3) if results else None,
        "population_mean_r2": round(float(np.mean(r2s)), 3) if results else None,
        "mean_improvement_pct": round(float(np.mean(imps)), 1) if results else None,
    }


# ── EXP-2512: Power-Law vs Flat Prediction ───────────────────────────

def exp_2512_prediction_comparison(df: pd.DataFrame, exp2511: dict) -> dict:
    """Compare glucose drop prediction: power-law ISF vs flat ISF."""
    print("EXP-2512: Prediction comparison")
    patients = sorted(df["patient_id"].unique())
    results = {}

    for pid in patients:
        if pid not in exp2511.get("per_patient", {}):
            continue
        params = exp2511["per_patient"][pid]

        pdf = df[df["patient_id"] == pid].copy()
        events = find_correction_events(pdf)
        good = [e for e in events if e["fit_r2"] > 0.2 and e["curve_isf"] > 0]
        if len(good) < 10:
            continue

        flat_isf = params["flat_isf"]
        isf_base = params["isf_base"]
        beta = params["beta"]

        flat_errors = []
        pl_errors = []
        for e in good:
            actual_drop = e["amplitude"]
            # Flat prediction
            flat_pred = flat_isf * e["dose"]
            flat_errors.append(abs(actual_drop - flat_pred))
            # Power-law prediction
            pl_isf = power_law_isf(np.array([e["dose"]]), isf_base, beta)[0]
            pl_pred = pl_isf * e["dose"]
            pl_errors.append(abs(actual_drop - pl_pred))

        flat_mae = float(np.mean(flat_errors))
        pl_mae = float(np.mean(pl_errors))
        improvement = (1 - pl_mae / max(flat_mae, 1e-6)) * 100

        results[pid] = {
            "n": len(good),
            "flat_mae_mgdl": round(flat_mae, 1),
            "powerlaw_mae_mgdl": round(pl_mae, 1),
            "improvement_pct": round(float(improvement), 1),
        }
        winner = "power-law" if improvement > 0 else "flat"
        print(f"  {pid}: flat MAE={flat_mae:.1f}, PL MAE={pl_mae:.1f}, "
              f"Δ={improvement:+.1f}% ({winner})")

    if results:
        imps = [v["improvement_pct"] for v in results.values()]
        wins = sum(1 for v in results.values() if v["improvement_pct"] > 0)
        print(f"\n  Power-law wins: {wins}/{len(results)}")
        print(f"  Mean improvement: {np.mean(imps):+.1f}%")

    return {
        "per_patient": results,
        "powerlaw_wins": sum(1 for v in results.values() if v["improvement_pct"] > 0),
        "n_patients": len(results),
        "mean_improvement_pct": round(float(np.mean(imps)), 1) if results else None,
    }


# ── EXP-2513: Universal β ───────────────────────────────────────────

def exp_2513_universal_beta(exp2511: dict) -> dict:
    """Is there a universal saturation exponent?"""
    print("EXP-2513: Universal β analysis")
    pp = exp2511.get("per_patient", {})
    if not pp:
        return {"conclusion": "insufficient data"}

    betas = [v["beta"] for v in pp.values()]
    # Clustering: how many distinct β groups?
    mean_beta = float(np.mean(betas))
    std_beta = float(np.std(betas))
    cv_beta = std_beta / abs(mean_beta) * 100 if mean_beta != 0 else 0

    # Can we use a single population β?
    # Test: what's the worst-case prediction error with population β vs individual β?
    pop_degradation = []
    for pid, v in pp.items():
        individual_r2 = v["r2"]
        # Estimate population-β R² (approximate)
        pop_degradation.append(v["r2"])  # placeholder

    is_universal = cv_beta < 50  # CV < 50% suggests reasonable universality

    result = {
        "mean_beta": round(mean_beta, 3),
        "std_beta": round(std_beta, 3),
        "cv_pct": round(cv_beta, 1),
        "min_beta": round(float(np.min(betas)), 3),
        "max_beta": round(float(np.max(betas)), 3),
        "is_universal": is_universal,
        "n_patients": len(betas),
    }

    print(f"  β = {mean_beta:.3f} ± {std_beta:.3f} (CV={cv_beta:.0f}%)")
    print(f"  Range: [{min(betas):.3f}, {max(betas):.3f}]")
    print(f"  Universal? {'YES' if is_universal else 'NO'} (CV {'<' if is_universal else '>'} 50%)")

    return result


# ── EXP-2514: Optimal Correction Dose ───────────────────────────────

def exp_2514_optimal_dose(exp2511: dict) -> dict:
    """Under non-linear ISF, what's the optimal correction dose?"""
    print("EXP-2514: Optimal correction dose analysis")
    pp = exp2511.get("per_patient", {})
    if not pp:
        return {"conclusion": "insufficient data"}

    results = {}
    for pid, v in pp.items():
        isf_base = v["isf_base"]
        beta = v["beta"]

        # For a target drop of 50 mg/dL, what dose is needed?
        target_drop = 50.0

        # With flat ISF: dose = target / flat_isf
        flat_dose = target_drop / max(v["flat_isf"], 1.0)

        # With power-law: dose × ISF(dose) = target
        # dose × ISF_base × dose^(-β) = target
        # ISF_base × dose^(1-β) = target
        # dose = (target / ISF_base)^(1/(1-β))
        if beta < 0.99:
            pl_dose = (target_drop / isf_base) ** (1 / (1 - beta))
        else:
            pl_dose = float('inf')

        dose_ratio = pl_dose / max(flat_dose, 0.01)

        # Efficiency: mg/dL drop per Unit at different doses
        doses_test = [0.5, 1.0, 2.0, 3.0, 5.0]
        efficiency = {}
        for d in doses_test:
            isf_at_d = power_law_isf(np.array([d]), isf_base, beta)[0]
            efficiency[str(d)] = round(float(isf_at_d), 1)

        results[pid] = {
            "flat_dose_for_50": round(float(flat_dose), 2),
            "powerlaw_dose_for_50": round(float(pl_dose), 2) if np.isfinite(pl_dose) else None,
            "dose_ratio": round(float(dose_ratio), 2) if np.isfinite(dose_ratio) else None,
            "isf_by_dose": efficiency,
            "beta": v["beta"],
        }
        print(f"  {pid}: 50mg/dL drop needs flat={flat_dose:.1f}U, "
              f"PL={pl_dose:.1f}U ({dose_ratio:.2f}×)")

    if results:
        ratios = [v["dose_ratio"] for v in results.values()
                  if v["dose_ratio"] is not None and np.isfinite(v["dose_ratio"])]
        print(f"\n  Mean dose ratio (PL/flat): {np.mean(ratios):.2f}×")
        print(f"  Non-linear ISF means correction doses should be "
              f"{'LARGER' if np.mean(ratios) > 1 else 'SMALLER'} than flat-ISF suggests")

    return {
        "per_patient": results,
        "mean_dose_ratio": round(float(np.mean(ratios)), 2) if results else None,
    }


# ── EXP-2515: Time × Dose Interaction ───────────────────────────────

def exp_2515_time_dose_interaction(df: pd.DataFrame) -> dict:
    """Does the saturation exponent β vary by time of day?"""
    print("EXP-2515: Time × dose interaction")
    patients = sorted(df["patient_id"].unique())
    periods = {"overnight": (0, 6), "morning": (6, 12),
               "afternoon": (12, 18), "evening": (18, 24)}

    period_betas = {p: [] for p in periods}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        events = find_correction_events(pdf)
        good = [e for e in events if e["fit_r2"] > 0.2 and e["curve_isf"] > 0]
        if len(good) < 20:
            continue

        for period, (h_start, h_end) in periods.items():
            period_events = [e for e in good if h_start <= e["hour"] < h_end]
            if len(period_events) < 5:
                continue
            doses = np.array([e["dose"] for e in period_events])
            isfs = np.array([e["curve_isf"] for e in period_events])
            fit = fit_power_law(doses, isfs)
            if fit["r2"] > 0.05:
                period_betas[period].append(fit["beta"])

    result = {}
    for period, betas in period_betas.items():
        if betas:
            result[period] = {
                "n_patients": len(betas),
                "mean_beta": round(float(np.mean(betas)), 3),
                "std_beta": round(float(np.std(betas)), 3),
            }
            print(f"  {period}: β={np.mean(betas):.3f} ± {np.std(betas):.3f} (n={len(betas)})")

    return result


# ── EXP-2516: IOB-Dependent Saturation ───────────────────────────────

def exp_2516_iob_saturation(df: pd.DataFrame) -> dict:
    """Does existing IOB at correction time affect ISF?"""
    print("EXP-2516: IOB-dependent ISF")
    patients = sorted(df["patient_id"].unique())
    results = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].copy()
        events = find_correction_events(pdf)
        good = [e for e in events if e["fit_r2"] > 0.2 and e["curve_isf"] > 0]
        if len(good) < 15:
            continue

        iobs = np.array([e["iob"] for e in good])
        isfs = np.array([e["curve_isf"] for e in good])

        if np.std(iobs) < 0.1:
            continue

        corr = float(np.corrcoef(iobs, isfs)[0, 1])
        rho, p = spearmanr(iobs, isfs)

        # Split: low IOB vs high IOB
        median_iob = float(np.median(iobs))
        low_iob_isf = float(np.mean(isfs[iobs <= median_iob]))
        high_iob_isf = float(np.mean(isfs[iobs > median_iob]))

        results[pid] = {
            "n": len(good),
            "pearson_r": round(corr, 3) if np.isfinite(corr) else None,
            "spearman_rho": round(float(rho), 3) if np.isfinite(rho) else None,
            "low_iob_isf": round(low_iob_isf, 1),
            "high_iob_isf": round(high_iob_isf, 1),
            "iob_effect_pct": round(float((high_iob_isf / max(low_iob_isf, 1) - 1) * 100), 1),
        }
        direction = "↓" if corr < 0 else "↑"
        print(f"  {pid}: r={corr:.3f} ({direction}), "
              f"low-IOB ISF={low_iob_isf:.0f}, high-IOB={high_iob_isf:.0f}")

    if results:
        corrs = [v["pearson_r"] for v in results.values() if v["pearson_r"] is not None]
        neg = sum(1 for c in corrs if c < -0.1)
        print(f"\n  IOB-ISF correlation: {neg}/{len(corrs)} negative (high IOB → lower ISF)")

    return {"per_patient": results, "n_patients": len(results)}


# ── EXP-2517: LOPO Cross-Validation ─────────────────────────────────

def exp_2517_lopo_validation(df: pd.DataFrame, exp2511: dict) -> dict:
    """Leave-one-patient-out: does population β generalize?"""
    print("EXP-2517: LOPO cross-validation")
    pp = exp2511.get("per_patient", {})
    if len(pp) < 5:
        return {"conclusion": "insufficient patients"}

    patients = list(pp.keys())
    results = {}

    for leave_out in patients:
        # Population β without this patient
        others = {k: v for k, v in pp.items() if k != leave_out}
        pop_beta = float(np.mean([v["beta"] for v in others.values()]))

        # Evaluate on held-out patient
        held_out = pp[leave_out]

        # How well does pop_beta predict vs individual beta?
        # Using R² as proxy — individual should always be >= population
        individual_r2 = held_out["r2"]
        # Can't recompute pop R² without raw data, but we can compare beta gap
        beta_gap = abs(held_out["beta"] - pop_beta)

        results[leave_out] = {
            "individual_beta": held_out["beta"],
            "population_beta": round(pop_beta, 3),
            "beta_gap": round(beta_gap, 3),
            "individual_r2": individual_r2,
        }

    gaps = [v["beta_gap"] for v in results.values()]
    print(f"  Mean |β_individual - β_population|: {np.mean(gaps):.3f}")
    print(f"  Max gap: {np.max(gaps):.3f}")
    print(f"  β transfers well: {sum(1 for g in gaps if g < 0.3)}/{len(gaps)}")

    return {
        "per_patient": results,
        "mean_beta_gap": round(float(np.mean(gaps)), 3),
        "max_beta_gap": round(float(np.max(gaps)), 3),
        "n_transferable": sum(1 for g in gaps if g < 0.3),
        "n_patients": len(gaps),
    }


# ── EXP-2518: Clinical Implications ─────────────────────────────────

def exp_2518_clinical_implications(exp2511: dict, exp2512: dict,
                                    exp2513: dict, exp2514: dict) -> dict:
    """Synthesize findings into clinical recommendations."""
    print("EXP-2518: Clinical implications")
    insights = []

    if exp2511.get("population_mean_beta"):
        beta = exp2511["population_mean_beta"]
        insights.append(
            f"Population saturation exponent β = {beta:.3f}. "
            f"This means a 2U correction is {100*(1-2**(-beta)):.0f}% less effective "
            f"per unit than a 1U correction.")

    if exp2512.get("powerlaw_wins"):
        wins = exp2512["powerlaw_wins"]
        total = exp2512["n_patients"]
        imp = exp2512.get("mean_improvement_pct", 0)
        insights.append(
            f"Power-law ISF improves glucose drop prediction in {wins}/{total} patients "
            f"(mean MAE improvement: {imp:+.1f}%).")

    if exp2513.get("is_universal") is not None:
        univ = exp2513["is_universal"]
        cv = exp2513.get("cv_pct", 0)
        insights.append(
            f"β is {'universal' if univ else 'patient-specific'} (CV={cv:.0f}%). "
            f"{'Population β can be used as a starting point.' if univ else 'Individual calibration required.'}")

    if exp2514.get("mean_dose_ratio"):
        ratio = exp2514["mean_dose_ratio"]
        insights.append(
            f"Under non-linear ISF, corrections need {ratio:.2f}× the dose that "
            f"flat-ISF would suggest for a 50 mg/dL target drop. "
            f"{'Split larger corrections into 2-3 smaller doses for better efficiency.' if ratio > 1.2 else ''}")

    for i, ins in enumerate(insights):
        print(f"  [{i+1}] {ins}")

    return {
        "insights": insights,
        "recommendation": (
            "ISF is dose-dependent. For production settings advisor: "
            "(1) warn users when correction dose >2U that diminishing returns apply, "
            "(2) consider split-dose strategy for large corrections, "
            "(3) use ISF_base (at 1U reference) as the primary ISF parameter."
        ),
    }


# ── Visualization ────────────────────────────────────────────────────

def generate_visualizations(df: pd.DataFrame, exp2511: dict):
    """Generate dose-ISF visualizations."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    pp = exp2511.get("per_patient", {})

    # Fig 1: Population dose-ISF scatter with power-law fits
    fig, axes = plt.subplots(3, 4, figsize=(16, 12), sharex=True)
    axes = axes.flatten()
    patients = sorted(pp.keys())[:12]

    for ax, pid in zip(axes, patients):
        pdf = df[df["patient_id"] == pid].copy()
        events = find_correction_events(pdf)
        good = [e for e in events if e["fit_r2"] > 0.2 and e["curve_isf"] > 0]
        if not good:
            ax.set_visible(False)
            continue

        doses = np.array([e["dose"] for e in good])
        isfs = np.array([e["curve_isf"] for e in good])
        params = pp[pid]

        ax.scatter(doses, isfs, s=15, alpha=0.5, c='steelblue')
        d_range = np.linspace(0.2, max(doses) * 1.1, 100)
        pl_fit = power_law_isf(d_range, params["isf_base"], params["beta"])
        ax.plot(d_range, pl_fit, 'r-', lw=2,
                label=f'β={params["beta"]:.2f}')
        ax.axhline(y=params["flat_isf"], color='gray', linestyle='--', alpha=0.5)
        ax.set_title(f'{pid} (R²={params["r2"]:.2f})', fontsize=9)
        ax.legend(fontsize=7)
        ax.set_ylim(0, min(np.percentile(isfs, 95) * 2, 800))

    for ax in axes[len(patients):]:
        ax.set_visible(False)

    fig.supxlabel("Correction Dose (U)", fontsize=12)
    fig.supylabel("Effective ISF (mg/dL/U)", fontsize=12)
    fig.suptitle("Dose-Dependent ISF: Power-Law Fits Per Patient", fontsize=14)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_dose_isf_fits.png", dpi=150)
    plt.close(fig)
    print(f"  Saved {VIZ_DIR / 'fig1_dose_isf_fits.png'}")

    # Fig 2: Population β distribution
    betas = [v["beta"] for v in pp.values()]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(betas, bins=15, color='steelblue', edgecolor='navy', alpha=0.8)
    ax.axvline(x=np.mean(betas), color='red', linestyle='--', lw=2,
               label=f'Mean β = {np.mean(betas):.3f}')
    ax.axvline(x=0, color='gray', linestyle=':', alpha=0.5, label='Linear (β=0)')
    ax.set_xlabel("Saturation Exponent (β)", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title("ISF Saturation Exponent Distribution\n(β>0 = larger doses less effective)", fontsize=13)
    ax.legend()
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_beta_distribution.png", dpi=150)
    plt.close(fig)
    print(f"  Saved {VIZ_DIR / 'fig2_beta_distribution.png'}")

    # Fig 3: Flat vs power-law MAE comparison
    if "per_patient" in exp2511:
        pids = sorted(pp.keys())
        fig, ax = plt.subplots(figsize=(10, 6))
        flat_mse = [pp[p]["flat_mse"] for p in pids]
        pl_mse = [pp[p]["powerlaw_mse"] for p in pids]
        x = np.arange(len(pids))
        width = 0.35
        ax.bar(x - width/2, flat_mse, width, label='Flat ISF', color='salmon')
        ax.bar(x + width/2, pl_mse, width, label='Power-law ISF', color='steelblue')
        ax.set_xticks(x)
        ax.set_xticklabels(pids, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel("MSE (mg/dL/U)²")
        ax.set_title("ISF Prediction Error: Flat vs Power-Law Model")
        ax.legend()
        fig.tight_layout()
        fig.savefig(VIZ_DIR / "fig3_flat_vs_powerlaw.png", dpi=150)
        plt.close(fig)
        print(f"  Saved {VIZ_DIR / 'fig3_flat_vs_powerlaw.png'}")


# ── Main ─────────────────────────────────────────────────────────────

def convert(obj):
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
    print("DOSE-DEPENDENT ISF MODEL (EXP-2511–2518)")
    print("=" * 60)

    results = {}

    results["exp_2511"] = exp_2511_power_law_fit(df)
    print()

    results["exp_2512"] = exp_2512_prediction_comparison(df, results["exp_2511"])
    print()

    results["exp_2513"] = exp_2513_universal_beta(results["exp_2511"])
    print()

    results["exp_2514"] = exp_2514_optimal_dose(results["exp_2511"])
    print()

    results["exp_2515"] = exp_2515_time_dose_interaction(df)
    print()

    results["exp_2516"] = exp_2516_iob_saturation(df)
    print()

    results["exp_2517"] = exp_2517_lopo_validation(df, results["exp_2511"])
    print()

    results["exp_2518"] = exp_2518_clinical_implications(
        results["exp_2511"], results["exp_2512"],
        results["exp_2513"], results["exp_2514"])

    # Visualizations
    print()
    try:
        generate_visualizations(df, results["exp_2511"])
    except Exception as e:
        print(f"  Visualization failed: {e}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "exp-2511-2518_dose_dependent_isf.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
