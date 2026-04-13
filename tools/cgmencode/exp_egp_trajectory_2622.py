#!/usr/bin/env python3
"""EXP-2622: Multi-Day EGP Trajectory & Glycogen State Estimation.

MOTIVATION: EGP operates on 10-72h timescales (glycogen depletion/repletion,
gluconeogenesis adaptation). The current metabolic engine models EGP with a
12h persistent window and instantaneous Hill suppression. Overnight glucose
drift should correlate with prior-day carb intake via glycogen filling.

The overnight fasting period (00-06h) is the cleanest EGP observation window:
no carb absorption, minimal bolus, only basal insulin and EGP interact.
Drift = EGP - basal_insulin_action. Night-to-night variation in drift
should reflect the multi-day glycogen/metabolic cycle.

APPROACH:
1. Extract clean overnight windows (00-06, no carbs, no bolus, glucose avail)
2. Compute overnight glucose drift rate (mg/dL/hr) per window
3. For each night, compute prior-24h and prior-48h cumulative carbs & insulin
4. Build glycogen proxy: exponential accumulator with τ=24h decay
5. Test correlations between prior-day metabolism and tonight's EGP rate

HYPOTHESES:
H1: Prior-24h cumulative carbs explain ≥10% of overnight drift variance
    (R² ≥ 0.10) across pooled windows. Higher prior carbs → higher drift
    (glycogen-loaded liver produces more glucose → EGP rises → drift up).
H2: Night-to-night drift autocorrelation ≥ 0.3 (persistent metabolic state,
    consistent with multi-day glycogen timescale, not random noise).
H3: Glycogen proxy (τ=24h exponential of cumulative carbs) predicts drift
    better than raw prior-24h carbs (R² improvement ≥ 0.03).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2622_egp_trajectory.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

OVERNIGHT_START = 0   # hour
OVERNIGHT_END = 6     # hour
MIN_WINDOW_STEPS = 36  # ≥3h of valid data (36 × 5min)
STEPS_PER_HOUR = 12

GLYCOGEN_TAU_HOURS = 24.0  # exponential decay time constant
GLYCOGEN_TAU_STEPS = GLYCOGEN_TAU_HOURS * STEPS_PER_HOUR


def _extract_overnight_drift_with_context(pdf: pd.DataFrame) -> list:
    """Extract overnight drift windows with prior-day metabolic context.

    For each night 00:00-06:00:
    - Compute glucose drift rate (mg/dL/hr)
    - Compute prior-24h and prior-48h cumulative carbs and insulin
    - Compute glycogen proxy (exponential accumulator)
    """
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])
    pdf["hour"] = t.dt.hour
    pdf["date"] = t.dt.date

    # Build glycogen proxy over entire record
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    decay = 1.0 - 1.0 / max(GLYCOGEN_TAU_STEPS, 1)
    glycogen = np.zeros(len(pdf))
    for i in range(1, len(pdf)):
        glycogen[i] = glycogen[i - 1] * decay + carbs[i]

    dates = sorted(pdf["date"].unique())
    windows = []

    for date in dates:
        # Overnight window: this date 00:00-06:00
        night_mask = (pdf["date"] == date) & (pdf["hour"] >= OVERNIGHT_START) & (pdf["hour"] < OVERNIGHT_END)
        night = pdf[night_mask]
        if len(night) < MIN_WINDOW_STEPS:
            continue

        gluc = night["glucose"].values
        valid = ~np.isnan(gluc)
        if valid.sum() < MIN_WINDOW_STEPS:
            continue

        # Glucose drift rate via linear regression
        t_hrs = np.arange(len(gluc)) * (5.0 / 60.0)
        t_v = t_hrs[valid]
        g_v = gluc[valid]
        if len(t_v) < 6:
            continue
        slope, intercept = np.polyfit(t_v, g_v, 1)

        # Prior-day context: look back 24h and 48h from midnight
        night_start_idx = night.index[0]
        pos = pdf.index.get_loc(night_start_idx)

        steps_24h = 24 * STEPS_PER_HOUR
        steps_48h = 48 * STEPS_PER_HOUR

        start_24h = max(0, pos - steps_24h)
        start_48h = max(0, pos - steps_48h)

        prior_24h = pdf.iloc[start_24h:pos]
        prior_48h = pdf.iloc[start_48h:pos]

        carbs_24h = float(prior_24h["carbs"].fillna(0).sum())
        carbs_48h = float(prior_48h["carbs"].fillna(0).sum())
        insulin_24h = float(prior_24h["bolus"].fillna(0).sum())
        if "actual_basal_rate" in prior_24h.columns:
            insulin_24h += float(prior_24h["actual_basal_rate"].fillna(0).sum() * 5.0 / 60.0)
        insulin_48h = float(prior_48h["bolus"].fillna(0).sum())
        if "actual_basal_rate" in prior_48h.columns:
            insulin_48h += float(prior_48h["actual_basal_rate"].fillna(0).sum() * 5.0 / 60.0)

        # Glycogen proxy at start of night
        glyc_value = float(glycogen[pos]) if pos < len(glycogen) else 0.0

        # Mean IOB during overnight (for context)
        mean_iob = float(night["iob"].fillna(0).mean())

        # Check for bolus/carb contamination
        night_carbs = float(night["carbs"].fillna(0).sum())
        night_bolus = float(night["bolus"].fillna(0).sum())

        if night_carbs > 2.0 or night_bolus > 0.5:
            continue  # contaminated window

        windows.append({
            "date": str(date),
            "drift_rate": float(slope),        # mg/dL per hour
            "start_glucose": float(g_v[0]),
            "end_glucose": float(g_v[-1]),
            "n_valid_points": int(valid.sum()),
            "carbs_24h": carbs_24h,
            "carbs_48h": carbs_48h,
            "insulin_24h": insulin_24h,
            "insulin_48h": insulin_48h,
            "glycogen_proxy": glyc_value,
            "mean_iob_overnight": mean_iob,
            "carb_insulin_ratio_24h": carbs_24h / max(insulin_24h, 0.1),
        })

    return windows


def main():
    print("=" * 70)
    print("EXP-2622: Multi-Day EGP Trajectory & Glycogen State Estimation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}
    pooled_drift = []
    pooled_carbs24 = []
    pooled_carbs48 = []
    pooled_glycogen = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288 * 7:  # need at least 7 days
            print(f"  SKIP: insufficient data ({len(pdf)} rows)")
            continue

        windows = _extract_overnight_drift_with_context(pdf)
        print(f"  Clean overnight windows: {len(windows)}")

        if len(windows) < 10:
            print(f"  SKIP: too few windows")
            continue

        drifts = np.array([w["drift_rate"] for w in windows])
        c24 = np.array([w["carbs_24h"] for w in windows])
        c48 = np.array([w["carbs_48h"] for w in windows])
        glyc = np.array([w["glycogen_proxy"] for w in windows])

        pooled_drift.extend(drifts)
        pooled_carbs24.extend(c24)
        pooled_carbs48.extend(c48)
        pooled_glycogen.extend(glyc)

        # Per-patient correlations
        r_c24, p_c24 = stats.pearsonr(c24, drifts) if len(c24) >= 5 else (np.nan, np.nan)
        r_c48, p_c48 = stats.pearsonr(c48, drifts) if len(c48) >= 5 else (np.nan, np.nan)
        r_glyc, p_glyc = stats.pearsonr(glyc, drifts) if len(glyc) >= 5 else (np.nan, np.nan)

        # Night-to-night autocorrelation (lag-1)
        if len(drifts) >= 5:
            autocorr = float(np.corrcoef(drifts[:-1], drifts[1:])[0, 1])
        else:
            autocorr = np.nan

        r2_c24 = r_c24 ** 2 if not np.isnan(r_c24) else np.nan
        r2_glyc = r_glyc ** 2 if not np.isnan(r_glyc) else np.nan

        print(f"  Mean drift: {np.mean(drifts):.2f} mg/dL/hr (σ={np.std(drifts):.2f})")
        print(f"  Prior-24h carbs→drift:  r={r_c24:.3f} (R²={r2_c24:.3f}, p={p_c24:.4f})")
        print(f"  Prior-48h carbs→drift:  r={r_c48:.3f} (p={p_c48:.4f})")
        print(f"  Glycogen proxy→drift:   r={r_glyc:.3f} (R²={r2_glyc:.3f}, p={p_glyc:.4f})")
        print(f"  Night-to-night autocorr: {autocorr:.3f}")

        all_results[pid] = {
            "n_windows": len(windows),
            "drift_mean": float(np.mean(drifts)),
            "drift_std": float(np.std(drifts)),
            "drift_median": float(np.median(drifts)),
            "carbs_24h_mean": float(np.mean(c24)),
            "r_carbs24_drift": float(r_c24) if not np.isnan(r_c24) else None,
            "r2_carbs24_drift": float(r2_c24) if not np.isnan(r2_c24) else None,
            "p_carbs24_drift": float(p_c24) if not np.isnan(p_c24) else None,
            "r_carbs48_drift": float(r_c48) if not np.isnan(r_c48) else None,
            "p_carbs48_drift": float(p_c48) if not np.isnan(p_c48) else None,
            "r_glycogen_drift": float(r_glyc) if not np.isnan(r_glyc) else None,
            "r2_glycogen_drift": float(r2_glyc) if not np.isnan(r2_glyc) else None,
            "p_glycogen_drift": float(p_glyc) if not np.isnan(p_glyc) else None,
            "autocorr_lag1": float(autocorr) if not np.isnan(autocorr) else None,
            "windows": windows,
        }

    # ── Pooled analysis ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("POOLED ANALYSIS")
    print("=" * 70)

    pooled_drift = np.array(pooled_drift)
    pooled_carbs24 = np.array(pooled_carbs24)
    pooled_carbs48 = np.array(pooled_carbs48)
    pooled_glycogen = np.array(pooled_glycogen)

    r_pool24, p_pool24 = stats.pearsonr(pooled_carbs24, pooled_drift) if len(pooled_drift) >= 10 else (np.nan, np.nan)
    r_pool48, p_pool48 = stats.pearsonr(pooled_carbs48, pooled_drift) if len(pooled_drift) >= 10 else (np.nan, np.nan)
    r_pool_glyc, p_pool_glyc = stats.pearsonr(pooled_glycogen, pooled_drift) if len(pooled_drift) >= 10 else (np.nan, np.nan)

    r2_pool24 = r_pool24 ** 2 if not np.isnan(r_pool24) else np.nan
    r2_pool_glyc = r_pool_glyc ** 2 if not np.isnan(r_pool_glyc) else np.nan

    print(f"  Total pooled windows: {len(pooled_drift)}")
    print(f"  Pooled carbs_24h→drift:  r={r_pool24:.3f} (R²={r2_pool24:.3f}, p={p_pool24:.4f})")
    print(f"  Pooled carbs_48h→drift:  r={r_pool48:.3f} (p={p_pool48:.4f})")
    print(f"  Pooled glycogen→drift:   r={r_pool_glyc:.3f} (R²={r2_pool_glyc:.3f}, p={p_pool_glyc:.4f})")

    # ── Hypothesis testing ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_data = [p for p in FULL_PATIENTS if p in all_results]

    # H1: Prior-24h carbs R² ≥ 0.10 pooled
    h1_pass = r2_pool24 >= 0.10 if not np.isnan(r2_pool24) else False
    print(f"  H1: Pooled R²(carbs_24h, drift) = {r2_pool24:.4f} "
          f"(threshold: ≥0.10) → {'PASS' if h1_pass else 'FAIL'}")
    # Also per-patient
    h1_per_patient = {p: all_results[p].get("r2_carbs24_drift") for p in patients_with_data}
    h1_count = sum(1 for v in h1_per_patient.values() if v is not None and v >= 0.10)
    print(f"  H1 per-patient: {h1_count}/9 with R² ≥ 0.10")

    # H2: Night-to-night autocorrelation ≥ 0.3
    autocorrs = [all_results[p]["autocorr_lag1"] for p in patients_with_data
                 if all_results[p]["autocorr_lag1"] is not None]
    median_autocorr = float(np.median(autocorrs)) if autocorrs else 0
    h2_pass = median_autocorr >= 0.3
    print(f"  H2: Median night-to-night autocorrelation = {median_autocorr:.3f} "
          f"(threshold: ≥0.3) → {'PASS' if h2_pass else 'FAIL'}")
    for pid in patients_with_data:
        ac = all_results[pid].get("autocorr_lag1")
        print(f"      {pid}: {ac:.3f}" if ac is not None else f"      {pid}: N/A")

    # H3: Glycogen proxy R² > carbs_24h R² by ≥0.03
    r2_improvement = (r2_pool_glyc - r2_pool24) if not (np.isnan(r2_pool_glyc) or np.isnan(r2_pool24)) else 0
    h3_pass = r2_improvement >= 0.03
    print(f"  H3: R² improvement (glycogen vs carbs_24h) = {r2_improvement:.4f} "
          f"(threshold: ≥0.03) → {'PASS' if h3_pass else 'FAIL'}")
    print(f"      R²_glycogen={r2_pool_glyc:.4f}  R²_carbs24={r2_pool24:.4f}")

    # Build pooled windows list for visualization
    pooled_windows = []
    for pid in patients_with_data:
        for w in all_results[pid].get("windows", []):
            pooled_windows.append({**w, "patient_id": pid})

    # ── Save results ────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2622",
        "title": "Multi-Day EGP Trajectory & Glycogen State Estimation",
        "patients": patients_with_data,
        "per_patient": {p: {k: v for k, v in all_results[p].items() if k != "windows"}
                        for p in patients_with_data},
        "pooled": {
            "n_windows": len(pooled_drift),
            "drift_mean": float(np.mean(pooled_drift)),
            "drift_std": float(np.std(pooled_drift)),
            "r_carbs24": float(r_pool24) if not np.isnan(r_pool24) else None,
            "r2_carbs24": float(r2_pool24) if not np.isnan(r2_pool24) else None,
            "p_carbs24": float(p_pool24) if not np.isnan(p_pool24) else None,
            "r_carbs48": float(r_pool48) if not np.isnan(r_pool48) else None,
            "p_carbs48": float(p_pool48) if not np.isnan(p_pool48) else None,
            "r_glycogen": float(r_pool_glyc) if not np.isnan(r_pool_glyc) else None,
            "r2_glycogen": float(r2_pool_glyc) if not np.isnan(r2_pool_glyc) else None,
            "p_glycogen": float(p_pool_glyc) if not np.isnan(p_pool_glyc) else None,
        },
        "pooled_windows": pooled_windows,
        "hypotheses": {
            "H1": {
                "statement": "Prior-24h carbs R² ≥ 0.10 for overnight drift (pooled)",
                "metric": "r2_carbs24_pooled",
                "value": float(r2_pool24) if not np.isnan(r2_pool24) else None,
                "threshold": 0.10,
                "result": "PASS" if h1_pass else "FAIL",
                "per_patient_r2": h1_per_patient,
                "n_patients_passing": h1_count,
            },
            "H2": {
                "statement": "Night-to-night drift autocorrelation ≥ 0.3 (median)",
                "metric": "median_autocorrelation",
                "value": median_autocorr,
                "threshold": 0.3,
                "result": "PASS" if h2_pass else "FAIL",
                "per_patient": {p: all_results[p].get("autocorr_lag1")
                                for p in patients_with_data},
            },
            "H3": {
                "statement": "Glycogen proxy R² improves over raw carbs_24h by ≥0.03",
                "metric": "r2_improvement",
                "value": float(r2_improvement),
                "threshold": 0.03,
                "result": "PASS" if h3_pass else "FAIL",
                "r2_glycogen": float(r2_pool_glyc) if not np.isnan(r2_pool_glyc) else None,
                "r2_carbs24": float(r2_pool24) if not np.isnan(r2_pool24) else None,
            },
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
