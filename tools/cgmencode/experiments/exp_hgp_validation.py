#!/usr/bin/env python3
"""
EXP-2534: Empirical Validation of Persistent HGP Suppression

Research question: Is the persistent -50 mg/dL/U HGP suppression component
(discovered in EXP-2525) a real physiological effect, or an artifact of:
  - Loop adjustments reducing basal after corrections
  - Meal effects coinciding with corrections
  - Regression to mean from high BG

Approach: Use overnight fasting (00:00-06:00, cob=0) as a clean window.
Compare nights preceded by evening correction boluses (18:00-23:59) to
matched nights without evening corrections.

Sub-experiments:
  EXP-2534a: Overnight matched-pair comparison
  EXP-2534b: Dose-response among correction nights
  EXP-2534c: Hour-by-hour temporal decay/persistence
  EXP-2534d: Loop deconfounding (basal rate comparison)

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_hgp_validation.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_hgp_validation.py --tiny
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "externals" / "experiments"

STEPS_PER_HOUR = 12  # 5-min grid


# ── Data Loading ──────────────────────────────────────────────────────

def load_data(tiny: bool = False) -> pd.DataFrame:
    """Load parquet grid data."""
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"

    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    df["date"] = df["time"].dt.date
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


# ── Night Classification ─────────────────────────────────────────────

def classify_nights(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each overnight segment (00:00-06:00) by evening context.

    Returns a DataFrame with one row per (patient_id, night_date):
      - group: 'CORRECTION' or 'NO_CORRECTION'
      - evening_dose: total correction bolus dose in evening (U)
      - midnight_bg: glucose at ~00:00
      - morning_bg: glucose at ~06:00
      - mean_bg: mean glucose 00:00-06:00
      - nadir_bg: minimum glucose 00:00-06:00
      - hourly_bg: list of mean glucose per hour
      - midnight_iob: IOB at ~00:00
      - mean_iob: mean IOB overnight
      - mean_actual_basal: mean actual basal rate overnight
      - mean_scheduled_basal: mean scheduled basal rate
      - mean_net_basal: mean net basal (actual - scheduled)
      - total_smb: total SMB insulin overnight
      - overnight_valid: whether segment has good data
    """
    results = []

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid].sort_values("time")

        # Get all unique dates
        dates = sorted(pdf["date"].unique())

        for night_date in dates:
            # Overnight window: 00:00-06:00 on this date
            overnight = pdf[
                (pdf["date"] == night_date)
                & (pdf["hour"] >= 0)
                & (pdf["hour"] < 6)
            ]

            if len(overnight) < STEPS_PER_HOUR * 4:  # need >= 4h
                continue

            gluc = overnight["glucose"].values
            valid = ~np.isnan(gluc)
            if valid.sum() < STEPS_PER_HOUR * 3:
                continue

            # Check continuity
            times = overnight["time"].values
            if len(times) > 1:
                gaps_min = np.diff(times.astype("int64")) / 1e9 / 60
                if np.max(gaps_min) > 30:
                    continue

            # Fasting check: cob must be <=1 throughout
            cob_vals = overnight["cob"].values
            if np.nanmax(cob_vals) > 1.0:
                continue

            # Evening context: 18:00-23:59 on PREVIOUS date
            prev_date = night_date - pd.Timedelta(days=1).to_pytimedelta()
            evening = pdf[
                (pdf["date"] == prev_date)
                & (pdf["hour"] >= 18)
                & (pdf["hour"] < 24)
            ]
            # Also check same-date evening (some evening data may straddle midnight)
            evening_same = pdf[
                (pdf["date"] == night_date)
                & (pdf["hour"] >= 18)
                & (pdf["hour"] < 24)
            ]

            if len(evening) < STEPS_PER_HOUR:  # need evening data
                continue

            # Detect correction boluses: bolus > 0.3U with no carbs nearby
            ev_bolus = evening["bolus"].values
            ev_carbs = evening["carbs"].values
            ev_cob = evening["cob"].values

            correction_dose = 0.0
            for i in range(len(evening)):
                if ev_bolus[i] < 0.3:
                    continue
                # Check no carbs within ±30 min (6 steps)
                start = max(0, i - 6)
                end = min(len(evening), i + 7)
                nearby_carbs = np.nansum(ev_carbs[start:end])
                cob_at_bolus = ev_cob[i] if not np.isnan(ev_cob[i]) else 0
                if nearby_carbs <= 1.0 and cob_at_bolus < 5.0:
                    correction_dose += float(ev_bolus[i])

            group = "CORRECTION" if correction_dose > 0.3 else "NO_CORRECTION"

            # Extract overnight metrics
            hours = overnight["hour"].values
            midnight_mask = hours < 0.5
            morning_mask = (hours >= 5.5) & (hours < 6.0)

            midnight_bg = float(np.nanmean(gluc[midnight_mask])) if midnight_mask.sum() > 0 else np.nan
            morning_bg = float(np.nanmean(gluc[morning_mask])) if morning_mask.sum() > 0 else np.nan

            # Hourly means
            hourly_bg = []
            for h in range(6):
                mask = (hours >= h) & (hours < h + 1)
                if mask.sum() > 0:
                    hourly_bg.append(float(np.nanmean(gluc[mask])))
                else:
                    hourly_bg.append(np.nan)

            iob_vals = overnight["iob"].values
            midnight_iob = float(np.nanmean(iob_vals[midnight_mask])) if midnight_mask.sum() > 0 else np.nan

            actual_basal = overnight["actual_basal_rate"].values
            scheduled_basal = overnight["scheduled_basal_rate"].values
            net_basal = overnight["net_basal"].values
            smb_vals = overnight["bolus_smb"].values

            results.append({
                "patient_id": pid,
                "night_date": str(night_date),
                "group": group,
                "evening_dose": correction_dose,
                "midnight_bg": midnight_bg,
                "morning_bg": morning_bg,
                "mean_bg": float(np.nanmean(gluc)),
                "nadir_bg": float(np.nanmin(gluc)),
                "hourly_bg": hourly_bg,
                "midnight_iob": midnight_iob,
                "mean_iob": float(np.nanmean(iob_vals)),
                "mean_actual_basal": float(np.nanmean(actual_basal)),
                "mean_scheduled_basal": float(np.nanmean(scheduled_basal)),
                "mean_net_basal": float(np.nanmean(net_basal)),
                "total_smb": float(np.nansum(smb_vals)),
            })

    nights_df = pd.DataFrame(results)
    print(f"Classified {len(nights_df)} overnight segments:")
    if len(nights_df) > 0:
        print(f"  CORRECTION:    {(nights_df['group'] == 'CORRECTION').sum()}")
        print(f"  NO_CORRECTION: {(nights_df['group'] == 'NO_CORRECTION').sum()}")
    return nights_df


# ── EXP-2534a: Matched Pair Comparison ───────────────────────────────

def exp_2534a_matched_pairs(nights: pd.DataFrame) -> dict:
    """
    Match CORRECTION and NO_CORRECTION nights by starting BG (±20 mg/dL)
    within the same patient. Compare overnight trajectories.
    """
    print("\n" + "=" * 70)
    print("EXP-2534a: Overnight Matched Pairs — CORRECTION vs NO_CORRECTION")
    print("=" * 70)

    if len(nights) == 0:
        print("  No nights available")
        return {"error": "no data"}

    BG_MATCH_WINDOW = 20  # mg/dL

    matched_pairs = []
    per_patient = {}

    for pid in sorted(nights["patient_id"].unique()):
        pn = nights[nights["patient_id"] == pid]
        corr = pn[pn["group"] == "CORRECTION"]
        no_corr = pn[pn["group"] == "NO_CORRECTION"]

        if len(corr) == 0 or len(no_corr) == 0:
            continue

        patient_pairs = []
        used_no_corr = set()

        for _, c_row in corr.iterrows():
            c_bg = c_row["midnight_bg"]
            if np.isnan(c_bg):
                continue

            # Find closest match
            candidates = no_corr[
                ~no_corr.index.isin(used_no_corr)
                & (no_corr["midnight_bg"].notna())
                & ((no_corr["midnight_bg"] - c_bg).abs() <= BG_MATCH_WINDOW)
            ]
            if len(candidates) == 0:
                continue

            best_idx = (candidates["midnight_bg"] - c_bg).abs().idxmin()
            used_no_corr.add(best_idx)
            nc_row = candidates.loc[best_idx]

            patient_pairs.append({
                "patient_id": pid,
                "corr_date": c_row["night_date"],
                "nocorr_date": nc_row["night_date"],
                "midnight_bg_corr": c_row["midnight_bg"],
                "midnight_bg_nocorr": nc_row["midnight_bg"],
                "mean_bg_corr": c_row["mean_bg"],
                "mean_bg_nocorr": nc_row["mean_bg"],
                "nadir_corr": c_row["nadir_bg"],
                "nadir_nocorr": nc_row["nadir_bg"],
                "morning_bg_corr": c_row["morning_bg"],
                "morning_bg_nocorr": nc_row["morning_bg"],
                "hourly_corr": c_row["hourly_bg"],
                "hourly_nocorr": nc_row["hourly_bg"],
                "dose": c_row["evening_dose"],
                "midnight_iob_corr": c_row["midnight_iob"],
                "midnight_iob_nocorr": nc_row["midnight_iob"],
                "mean_iob_corr": c_row["mean_iob"],
                "mean_iob_nocorr": nc_row["mean_iob"],
            })

        matched_pairs.extend(patient_pairs)
        if patient_pairs:
            per_patient[pid] = len(patient_pairs)

    n_pairs = len(matched_pairs)
    print(f"\n  Matched pairs: {n_pairs}")

    if n_pairs < 5:
        print("  Insufficient matched pairs for analysis")
        return {
            "n_pairs": n_pairs,
            "per_patient": per_patient,
            "conclusion": "insufficient_data",
        }

    # Print per-patient breakdown
    print(f"  Per-patient: {per_patient}")

    mdf = pd.DataFrame(matched_pairs)

    # Aggregate comparisons
    bg_diff_mean = float(mdf["mean_bg_corr"].mean() - mdf["mean_bg_nocorr"].mean())
    bg_diff_nadir = float(mdf["nadir_corr"].mean() - mdf["nadir_nocorr"].mean())
    bg_diff_morning = float(mdf["morning_bg_corr"].mean() - mdf["morning_bg_nocorr"].mean())
    bg_diff_midnight = float(mdf["midnight_bg_corr"].mean() - mdf["midnight_bg_nocorr"].mean())

    iob_diff_midnight = float(mdf["midnight_iob_corr"].mean() - mdf["midnight_iob_nocorr"].mean())
    iob_diff_mean = float(mdf["mean_iob_corr"].mean() - mdf["mean_iob_nocorr"].mean())

    mean_dose = float(mdf["dose"].mean())

    # Compute per-unit effect
    per_unit_mean = bg_diff_mean / mean_dose if mean_dose > 0 else 0
    per_unit_morning = bg_diff_morning / mean_dose if mean_dose > 0 else 0

    # Paired t-test for significance
    from scipy import stats
    t_mean, p_mean = stats.ttest_rel(mdf["mean_bg_corr"], mdf["mean_bg_nocorr"])
    t_morning, p_morning = stats.ttest_rel(
        mdf["morning_bg_corr"].dropna(), mdf["morning_bg_nocorr"].dropna()
    ) if mdf["morning_bg_corr"].notna().sum() > 5 else (np.nan, np.nan)

    print(f"\n  ┌────────────────────────────────────────────────────────────┐")
    print(f"  │ Metric              │ CORRECTION  │ NO_CORR     │ Δ (mg/dL)│")
    print(f"  ├─────────────────────┼─────────────┼─────────────┼──────────┤")
    print(f"  │ Midnight BG (match) │ {mdf['midnight_bg_corr'].mean():>8.1f}    │ {mdf['midnight_bg_nocorr'].mean():>8.1f}    │ {bg_diff_midnight:>+7.1f}  │")
    print(f"  │ Mean overnight BG   │ {mdf['mean_bg_corr'].mean():>8.1f}    │ {mdf['mean_bg_nocorr'].mean():>8.1f}    │ {bg_diff_mean:>+7.1f}  │")
    print(f"  │ Nadir BG            │ {mdf['nadir_corr'].mean():>8.1f}    │ {mdf['nadir_nocorr'].mean():>8.1f}    │ {bg_diff_nadir:>+7.1f}  │")
    print(f"  │ Morning BG (06:00)  │ {mdf['morning_bg_corr'].mean():>8.1f}    │ {mdf['morning_bg_nocorr'].mean():>8.1f}    │ {bg_diff_morning:>+7.1f}  │")
    print(f"  └─────────────────────┴─────────────┴─────────────┴──────────┘")
    print(f"\n  Paired t-test (mean overnight BG): t={t_mean:.2f}, p={p_mean:.4f}")
    if not np.isnan(p_morning):
        print(f"  Paired t-test (morning BG):        t={t_morning:.2f}, p={p_morning:.4f}")
    print(f"\n  Mean correction dose: {mean_dose:.2f} U")
    print(f"  Per-unit overnight BG effect: {per_unit_mean:+.1f} mg/dL/U")
    print(f"  Per-unit morning BG effect:   {per_unit_morning:+.1f} mg/dL/U")
    print(f"\n  IOB at midnight — CORRECTION: {mdf['midnight_iob_corr'].mean():.2f}, "
          f"NO_CORR: {mdf['midnight_iob_nocorr'].mean():.2f} "
          f"(Δ={iob_diff_midnight:+.2f})")
    print(f"  Mean IOB overnight — CORRECTION: {mdf['mean_iob_corr'].mean():.2f}, "
          f"NO_CORR: {mdf['mean_iob_nocorr'].mean():.2f} "
          f"(Δ={iob_diff_mean:+.2f})")

    # Interpretation
    if bg_diff_mean < -5 and p_mean < 0.05:
        interpretation = "CORRECTION nights significantly lower → supports HGP suppression"
    elif bg_diff_mean < -3:
        interpretation = "CORRECTION nights modestly lower → weak HGP signal"
    elif abs(bg_diff_mean) <= 3:
        interpretation = "No meaningful difference → HGP suppression NOT confirmed"
    else:
        interpretation = "CORRECTION nights HIGHER → possible rebound or confound"

    print(f"\n  Interpretation: {interpretation}")

    return {
        "n_pairs": n_pairs,
        "per_patient": per_patient,
        "mean_dose": mean_dose,
        "bg_diff_mean": bg_diff_mean,
        "bg_diff_nadir": bg_diff_nadir,
        "bg_diff_morning": bg_diff_morning,
        "bg_diff_midnight": bg_diff_midnight,
        "per_unit_mean_effect": per_unit_mean,
        "per_unit_morning_effect": per_unit_morning,
        "iob_diff_midnight": iob_diff_midnight,
        "iob_diff_mean": iob_diff_mean,
        "paired_ttest_mean": {"t": float(t_mean), "p": float(p_mean)},
        "paired_ttest_morning": {
            "t": float(t_morning) if not np.isnan(t_morning) else None,
            "p": float(p_morning) if not np.isnan(p_morning) else None,
        },
        "interpretation": interpretation,
        "matched_pairs_summary": {
            "corr_mean_bg": float(mdf["mean_bg_corr"].mean()),
            "nocorr_mean_bg": float(mdf["mean_bg_nocorr"].mean()),
            "corr_morning_bg": float(mdf["morning_bg_corr"].mean()),
            "nocorr_morning_bg": float(mdf["morning_bg_nocorr"].mean()),
        },
    }


# ── EXP-2534b: Dose-Response ─────────────────────────────────────────

def exp_2534b_dose_response(nights: pd.DataFrame) -> dict:
    """
    Among CORRECTION nights, stratify by evening dose and test whether
    larger doses produce diminishing additional overnight BG reduction
    (consistent with power-law HGP model).
    """
    print("\n" + "=" * 70)
    print("EXP-2534b: Dose-Response Among Correction Nights")
    print("=" * 70)

    corr = nights[nights["group"] == "CORRECTION"].copy()
    if len(corr) < 10:
        print("  Insufficient correction nights")
        return {"error": "insufficient_data", "n_correction_nights": len(corr)}

    # Dose strata
    bins = {"small (<1U)": (0.3, 1.0), "medium (1-2U)": (1.0, 2.0), "large (>2U)": (2.0, 100.0)}
    strata = {}

    # Raw analysis (uncorrected for starting BG)
    print(f"\n  Raw overnight BG by dose stratum:")
    print(f"  {'Dose Stratum':<16} │ {'N':>4} │ {'Mean Dose':>9} │ {'Mean BG':>8} │ {'Nadir':>6} │ {'Morning':>8} │ {'Mid BG':>7}")
    print(f"  {'─' * 16}─┼──{'─' * 4}─┼──{'─' * 7}──┼──{'─' * 6}──┼──{'─' * 4}──┼──{'─' * 6}──┼──{'─' * 5}──")

    for label, (lo, hi) in bins.items():
        mask = (corr["evening_dose"] >= lo) & (corr["evening_dose"] < hi)
        stratum = corr[mask]
        if len(stratum) < 3:
            strata[label] = {"n": len(stratum), "note": "too few"}
            continue

        strata[label] = {
            "n": len(stratum),
            "mean_dose": float(stratum["evening_dose"].mean()),
            "mean_bg": float(stratum["mean_bg"].mean()),
            "std_bg": float(stratum["mean_bg"].std()),
            "nadir_bg": float(stratum["nadir_bg"].mean()),
            "morning_bg": float(stratum["morning_bg"].mean()),
            "midnight_bg": float(stratum["midnight_bg"].mean()),
            "mean_iob": float(stratum["mean_iob"].mean()),
        }
        s = strata[label]
        print(f"  {label:<16} │ {s['n']:>4} │ {s['mean_dose']:>8.2f}U │ {s['mean_bg']:>7.1f}  │ {s['nadir_bg']:>5.1f}  │ {s['morning_bg']:>7.1f}  │ {s['midnight_bg']:>6.1f}")

    # BG-adjusted analysis: compute overnight drift (mean_bg - midnight_bg)
    # This controls for starting BG, which is confounded with dose
    corr_valid = corr[corr["midnight_bg"].notna()].copy()
    corr_valid["overnight_drift"] = corr_valid["mean_bg"] - corr_valid["midnight_bg"]
    corr_valid["morning_drift"] = corr_valid["morning_bg"] - corr_valid["midnight_bg"]

    print(f"\n  BG-drift-adjusted analysis (controlling for midnight BG):")
    print(f"  {'Dose Stratum':<16} │ {'N':>4} │ {'Mean Dose':>9} │ {'BG Drift':>9} │ {'Morn Drift':>10} │ {'IOB':>5}")
    print(f"  {'─' * 16}─┼──{'─' * 4}─┼──{'─' * 7}──┼──{'─' * 7}──┼──{'─' * 8}──┼──{'─' * 3}──")

    adjusted_strata = {}
    for label, (lo, hi) in bins.items():
        mask = (corr_valid["evening_dose"] >= lo) & (corr_valid["evening_dose"] < hi)
        stratum = corr_valid[mask]
        if len(stratum) < 3:
            continue
        drift = float(stratum["overnight_drift"].mean())
        morn_drift = float(stratum["morning_drift"].mean())
        iob = float(stratum["mean_iob"].mean())
        dose = float(stratum["evening_dose"].mean())
        adjusted_strata[label] = {
            "n": len(stratum),
            "mean_dose": dose,
            "overnight_drift": drift,
            "morning_drift": morn_drift,
            "mean_iob": iob,
        }
        print(f"  {label:<16} │ {len(stratum):>4} │ {dose:>8.2f}U │ {drift:>+8.1f}  │ {morn_drift:>+9.1f}  │ {iob:>4.2f}")

    # Test for dose-response trend using adjusted drift
    valid_strata = [v for v in adjusted_strata.values() if "mean_dose" in v]
    if len(valid_strata) >= 2:
        doses = [s["mean_dose"] for s in valid_strata]
        drifts = [s["overnight_drift"] for s in valid_strata]

        from scipy import stats
        if len(doses) >= 3:
            r, p = stats.pearsonr(doses, drifts)
        else:
            r = np.corrcoef(doses, drifts)[0, 1] if len(doses) == 2 else np.nan
            p = np.nan

        print(f"\n  Dose-drift correlation: r={r:.3f}" + (f", p={p:.4f}" if not np.isnan(p) else ""))

        # Check for diminishing returns (power-law signature)
        if len(valid_strata) >= 3:
            deltas = [drifts[i + 1] - drifts[i] for i in range(len(drifts) - 1)]
            dose_steps = [doses[i + 1] - doses[i] for i in range(len(doses) - 1)]
            marginal = [d / s if s > 0 else 0 for d, s in zip(deltas, dose_steps)]
            print(f"  Marginal drift change per unit dose: {[f'{m:+.1f}' for m in marginal]}")
            if all(m < 0 for m in marginal):
                if len(marginal) >= 2 and abs(marginal[-1]) < abs(marginal[0]) * 0.8:
                    print("  → Diminishing returns detected (power-law consistent)")
                else:
                    print("  → Larger doses produce MORE negative drift (dose-response)")
            elif all(m > 0 for m in marginal):
                print("  → Larger doses show LESS negative drift — NOT supporting HGP")
        else:
            marginal = []

        return {
            "n_correction_nights": len(corr),
            "strata": strata,
            "adjusted_strata": adjusted_strata,
            "dose_drift_correlation": {"r": float(r) if not np.isnan(r) else None,
                                        "p": float(p) if not np.isnan(p) else None},
        }

    return {
        "n_correction_nights": len(corr),
        "strata": strata,
        "adjusted_strata": adjusted_strata if adjusted_strata else {},
        "note": "insufficient_strata_for_trend",
    }


# ── EXP-2534c: Temporal Decay ────────────────────────────────────────

def exp_2534c_temporal_decay(nights: pd.DataFrame) -> dict:
    """
    Track the correction-group BG advantage hour by hour (00-06).
    If HGP suppression is truly persistent, the advantage should be constant.
    If it decays, fit an exponential to estimate the real time constant.
    """
    print("\n" + "=" * 70)
    print("EXP-2534c: Hour-by-Hour Temporal Decay of Correction Advantage")
    print("=" * 70)

    corr = nights[nights["group"] == "CORRECTION"]
    no_corr = nights[nights["group"] == "NO_CORRECTION"]

    if len(corr) < 5 or len(no_corr) < 5:
        print("  Insufficient data for temporal analysis")
        return {"error": "insufficient_data"}

    # Expand hourly BG arrays
    corr_hourly = np.array(corr["hourly_bg"].tolist())  # shape: (n_corr, 6)
    nocorr_hourly = np.array(no_corr["hourly_bg"].tolist())

    # Handle NaN: use column means
    hours = list(range(6))
    hourly_results = []

    print(f"\n  {'Hour':<8} │ {'CORRECTION':>11} │ {'NO_CORR':>11} │ {'Δ BG':>8} │ {'95% CI':>14}")
    print(f"  {'─' * 8}─┼──{'─' * 9}──┼──{'─' * 9}──┼──{'─' * 6}──┼──{'─' * 12}──")

    advantages = []
    ci_lowers = []
    ci_uppers = []

    for h in hours:
        c_vals = corr_hourly[:, h]
        n_vals = nocorr_hourly[:, h]
        c_vals = c_vals[~np.isnan(c_vals)]
        n_vals = n_vals[~np.isnan(n_vals)]

        if len(c_vals) < 3 or len(n_vals) < 3:
            hourly_results.append({"hour": h, "note": "insufficient"})
            advantages.append(np.nan)
            continue

        c_mean = float(np.mean(c_vals))
        n_mean = float(np.mean(n_vals))
        delta = c_mean - n_mean
        advantages.append(delta)

        # 95% CI via bootstrap-approximated SEM
        from scipy import stats
        se = np.sqrt(np.var(c_vals) / len(c_vals) + np.var(n_vals) / len(n_vals))
        ci_lo = delta - 1.96 * se
        ci_hi = delta + 1.96 * se
        ci_lowers.append(ci_lo)
        ci_uppers.append(ci_hi)

        hourly_results.append({
            "hour": h,
            "corr_mean": c_mean,
            "nocorr_mean": n_mean,
            "delta": delta,
            "ci_95": [float(ci_lo), float(ci_hi)],
            "n_corr": len(c_vals),
            "n_nocorr": len(n_vals),
        })

        print(f"  {h:02d}:00    │ {c_mean:>10.1f}  │ {n_mean:>10.1f}  │ {delta:>+7.1f}  │ [{ci_lo:>+6.1f}, {ci_hi:>+6.1f}]")

    # Fit decay model to advantages
    adv = np.array(advantages)
    valid = ~np.isnan(adv)
    valid_hours = np.array(hours)[valid]
    valid_adv = adv[valid]

    decay_fit = None
    if len(valid_adv) >= 4:
        # Model 1: Constant (no decay)
        const_mean = float(np.mean(valid_adv))
        const_ss = float(np.sum((valid_adv - const_mean) ** 2))

        # Model 2: Linear decay
        from scipy import stats
        slope, intercept, r_lin, p_lin, se_lin = stats.linregress(valid_hours, valid_adv)
        linear_ss = float(np.sum((valid_adv - (slope * valid_hours + intercept)) ** 2))

        # Model 3: Exponential decay: a * exp(-t/tau) + c
        try:
            def exp_decay(t, a, tau, c):
                return a * np.exp(-t / tau) + c

            # Initial guesses
            p0 = [valid_adv[0] - valid_adv[-1], 3.0, valid_adv[-1]]
            popt, pcov = curve_fit(exp_decay, valid_hours.astype(float), valid_adv,
                                   p0=p0, maxfev=5000,
                                   bounds=([-100, 0.5, -100], [100, 20, 100]))
            exp_pred = exp_decay(valid_hours.astype(float), *popt)
            exp_ss = float(np.sum((valid_adv - exp_pred) ** 2))
            decay_fit = {
                "amplitude": float(popt[0]),
                "tau_hours": float(popt[1]),
                "plateau": float(popt[2]),
                "ss_residual": exp_ss,
            }
        except (RuntimeError, ValueError):
            exp_ss = np.inf
            decay_fit = None

        # Compare models
        best_model = "constant"
        if linear_ss < const_ss * 0.7 and p_lin < 0.1:
            best_model = "linear_decay"
        if decay_fit and exp_ss < min(const_ss, linear_ss) * 0.7:
            best_model = "exponential_decay"

        print(f"\n  Model comparison:")
        print(f"    Constant:    SS={const_ss:.1f}, mean advantage={const_mean:+.1f} mg/dL")
        print(f"    Linear:      SS={linear_ss:.1f}, slope={slope:+.2f} mg/dL/hr, p={p_lin:.4f}")
        if decay_fit:
            print(f"    Exponential: SS={exp_ss:.1f}, τ={decay_fit['tau_hours']:.1f}h, "
                  f"plateau={decay_fit['plateau']:+.1f} mg/dL")
        print(f"    Best model: {best_model}")

        if best_model == "constant":
            print(f"\n  → Advantage is PERSISTENT (no decay in 6h) = {const_mean:+.1f} mg/dL")
            print(f"    This SUPPORTS persistent HGP suppression")
        elif best_model == "exponential_decay" and decay_fit:
            if decay_fit["tau_hours"] > 4:
                print(f"\n  → Very slow decay (τ={decay_fit['tau_hours']:.1f}h) ≈ persistent")
                print(f"    Plateau = {decay_fit['plateau']:+.1f} mg/dL — SUPPORTS HGP suppression")
            else:
                print(f"\n  → Decaying advantage (τ={decay_fit['tau_hours']:.1f}h)")
                print(f"    Residual plateau = {decay_fit['plateau']:+.1f} mg/dL")
                print(f"    Partial HGP signal but with significant transient component")
        else:
            print(f"\n  → Linear decay: {slope:+.2f} mg/dL/hr")
            print(f"    Advantage disappears in ~{abs(intercept / slope):.1f}h" if slope != 0 else "")

        return {
            "hourly": hourly_results,
            "model_comparison": {
                "constant": {"ss": const_ss, "mean": const_mean},
                "linear": {"ss": linear_ss, "slope": float(slope),
                           "intercept": float(intercept), "p": float(p_lin)},
                "exponential": decay_fit,
                "best_model": best_model,
            },
        }

    return {"hourly": hourly_results, "note": "insufficient_hours_for_model_fit"}


# ── EXP-2534d: Loop Deconfounding ────────────────────────────────────

def exp_2534d_loop_deconfounding(nights: pd.DataFrame) -> dict:
    """
    Compare loop behavior on CORRECTION vs NO_CORRECTION nights.
    If the loop reduces basal after corrections, the 'persistent suppression'
    may be loop-mediated rather than physiological HGP.
    """
    print("\n" + "=" * 70)
    print("EXP-2534d: Loop Deconfounding — Basal Rate Comparison")
    print("=" * 70)

    corr = nights[nights["group"] == "CORRECTION"]
    no_corr = nights[nights["group"] == "NO_CORRECTION"]

    if len(corr) < 5 or len(no_corr) < 5:
        print("  Insufficient data")
        return {"error": "insufficient_data"}

    metrics = [
        ("mean_actual_basal", "Actual basal rate (U/hr)"),
        ("mean_scheduled_basal", "Scheduled basal (U/hr)"),
        ("mean_net_basal", "Net basal (act-sched, U/hr)"),
        ("total_smb", "Total SMB insulin (U)"),
        ("mean_iob", "Mean IOB (U)"),
    ]

    from scipy import stats

    print(f"\n  {'Metric':<28} │ {'CORRECTION':>11} │ {'NO_CORR':>11} │ {'Δ':>8} │ {'p-value':>8}")
    print(f"  {'─' * 28}─┼──{'─' * 9}──┼──{'─' * 9}──┼──{'─' * 6}──┼──{'─' * 6}──")

    loop_results = {}
    for col, label in metrics:
        c_vals = corr[col].dropna()
        n_vals = no_corr[col].dropna()
        if len(c_vals) < 5 or len(n_vals) < 5:
            continue

        c_mean = float(c_vals.mean())
        n_mean = float(n_vals.mean())
        delta = c_mean - n_mean

        t_stat, p_val = stats.ttest_ind(c_vals, n_vals, equal_var=False)

        loop_results[col] = {
            "corr_mean": c_mean,
            "nocorr_mean": n_mean,
            "delta": delta,
            "t_stat": float(t_stat),
            "p_value": float(p_val),
        }

        sig = "*" if p_val < 0.05 else " "
        print(f"  {label:<28} │ {c_mean:>10.3f}  │ {n_mean:>10.3f}  │ {delta:>+7.3f}  │ {p_val:>7.4f} {sig}")

    # Interpretation
    basal_key = "mean_actual_basal"
    iob_key = "mean_iob"

    basal_confound = False
    iob_confound = False

    if basal_key in loop_results:
        br = loop_results[basal_key]
        if br["delta"] < -0.05 and br["p_value"] < 0.05:
            basal_confound = True
            print(f"\n  ⚠ Loop REDUCES basal on correction nights by {br['delta']:+.3f} U/hr (p={br['p_value']:.4f})")
            print(f"    Some overnight BG reduction may be loop-mediated, NOT pure HGP suppression")

    if iob_key in loop_results:
        ir = loop_results[iob_key]
        if ir["delta"] > 0.1 and ir["p_value"] < 0.05:
            iob_confound = True
            print(f"\n  ⚠ IOB is HIGHER on correction nights by {ir['delta']:+.3f} U (p={ir['p_value']:.4f})")
            print(f"    Residual insulin from correction may explain some of the overnight BG difference")

    smb_key = "total_smb"
    smb_confound = False
    if smb_key in loop_results:
        sr = loop_results[smb_key]
        if sr["delta"] < -0.05 and sr["p_value"] < 0.05:
            smb_confound = True
            print(f"\n  ⚠ Loop delivers FEWER SMBs on correction nights (Δ={sr['delta']:+.3f} U)")

    if not basal_confound and not iob_confound:
        print(f"\n  ✓ No significant loop confounding detected")
        print(f"    Loop treats CORRECTION and NO_CORRECTION nights similarly")
        print(f"    → Overnight BG difference is likely PHYSIOLOGICAL (HGP suppression)")

    confound_flags = {
        "basal_confound": basal_confound,
        "iob_confound": iob_confound,
        "smb_confound": smb_confound,
    }

    # Attribution estimate
    if iob_key in loop_results and basal_key in loop_results:
        iob_delta = loop_results[iob_key]["delta"]
        # Rough estimate: 1U IOB ≈ -50 mg/dL effect (from prior ISF analysis)
        isf_estimate = 50
        iob_explained_bg = iob_delta * isf_estimate
        print(f"\n  IOB-explained BG difference: {iob_delta:+.2f} U × {isf_estimate} mg/dL/U ≈ {iob_explained_bg:+.1f} mg/dL")

        confound_flags["iob_explained_bg"] = float(iob_explained_bg)

    return {
        "loop_metrics": loop_results,
        "confound_flags": confound_flags,
    }


# ── Synthesis ─────────────────────────────────────────────────────────

def synthesize(results: dict) -> dict:
    """Combine all sub-experiment results into final verdict."""
    print("\n" + "=" * 70)
    print("SYNTHESIS: Is Persistent HGP Suppression Real?")
    print("=" * 70)

    verdict = {
        "hgp_confirmed": None,
        "confidence": None,
        "evidence": [],
        "confounds": [],
    }

    # Evidence from 2534a
    a = results.get("exp_2534a", {})
    if "bg_diff_mean" in a:
        delta = a["bg_diff_mean"]
        p = a.get("paired_ttest_mean", {}).get("p", 1.0)
        if delta < -5 and p is not None and p < 0.05:
            verdict["evidence"].append(f"Matched pairs: {delta:+.1f} mg/dL (p={p:.4f}) — SUPPORTS HGP")
        elif delta < -3:
            verdict["evidence"].append(f"Matched pairs: {delta:+.1f} mg/dL — weak signal")
        else:
            verdict["evidence"].append(f"Matched pairs: {delta:+.1f} mg/dL — NOT supportive")

    # Evidence from 2534c
    c = results.get("exp_2534c", {})
    mc = c.get("model_comparison", {})
    if mc.get("best_model") == "constant":
        verdict["evidence"].append("Temporal: constant advantage (no decay) — SUPPORTS persistent HGP")
    elif mc.get("best_model") == "exponential_decay":
        exp = mc.get("exponential", {})
        tau = exp.get("tau_hours", 0)
        plat = exp.get("plateau", 0)
        if tau > 4:
            verdict["evidence"].append(f"Temporal: very slow decay τ={tau:.1f}h — SUPPORTS HGP")
        elif abs(plat) > 3:
            verdict["evidence"].append(f"Temporal: decay τ={tau:.1f}h but plateau={plat:+.1f} — partial HGP")
        else:
            verdict["evidence"].append(f"Temporal: decaying advantage τ={tau:.1f}h — WEAKENS HGP")

    # Confounds from 2534d
    d = results.get("exp_2534d", {})
    flags = d.get("confound_flags", {})
    if flags.get("iob_confound"):
        iob_bg = flags.get("iob_explained_bg", 0)
        verdict["confounds"].append(f"IOB confound: residual insulin explains ~{iob_bg:+.1f} mg/dL")
    if flags.get("basal_confound"):
        verdict["confounds"].append("Loop reduces basal on correction nights")
    if not flags.get("iob_confound") and not flags.get("basal_confound"):
        verdict["evidence"].append("Loop behavior: no confounding detected — SUPPORTS physiological HGP")

    # Overall verdict
    supports = sum(1 for e in verdict["evidence"] if "SUPPORTS" in e)
    weakens = sum(1 for e in verdict["evidence"] if "WEAKENS" in e or "NOT" in e)
    n_confounds = len(verdict["confounds"])

    if supports >= 2 and n_confounds == 0:
        verdict["hgp_confirmed"] = True
        verdict["confidence"] = "HIGH"
    elif supports >= 2 and n_confounds > 0:
        verdict["hgp_confirmed"] = True
        verdict["confidence"] = "MODERATE — confounds present but effect persists"
    elif supports >= 1:
        verdict["hgp_confirmed"] = "partial"
        verdict["confidence"] = "LOW — mixed evidence"
    else:
        verdict["hgp_confirmed"] = False
        verdict["confidence"] = "HGP suppression NOT confirmed as physiological"

    print(f"\n  Evidence FOR persistent HGP:  {supports}")
    print(f"  Evidence AGAINST:             {weakens}")
    print(f"  Confounds identified:         {n_confounds}")
    for e in verdict["evidence"]:
        print(f"    • {e}")
    for c in verdict["confounds"]:
        print(f"    ⚠ {c}")
    print(f"\n  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║ VERDICT: HGP confirmed = {str(verdict['hgp_confirmed']):<8}                       ║")
    print(f"  ║ Confidence: {verdict['confidence']:<48} ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝")

    return verdict


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-2534: HGP Suppression Validation")
    parser.add_argument("--tiny", action="store_true", help="Use tiny dataset")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2534: Empirical Validation of Persistent HGP Suppression")
    print("=" * 70)
    print("Hypothesis: Evening correction boluses produce persistently lower")
    print("overnight glucose via hepatic glucose production suppression.\n")

    df = load_data(tiny=args.tiny)

    # Classify all overnight segments
    nights = classify_nights(df)

    if len(nights) == 0:
        print("ERROR: No valid overnight segments found")
        sys.exit(1)

    results = {}

    # EXP-2534a: Matched pairs
    results["exp_2534a"] = exp_2534a_matched_pairs(nights)

    # EXP-2534b: Dose-response
    results["exp_2534b"] = exp_2534b_dose_response(nights)

    # EXP-2534c: Temporal decay
    results["exp_2534c"] = exp_2534c_temporal_decay(nights)

    # EXP-2534d: Loop deconfounding
    results["exp_2534d"] = exp_2534d_loop_deconfounding(nights)

    # Synthesis
    results["synthesis"] = synthesize(results)

    # Summary statistics
    results["metadata"] = {
        "experiment": "EXP-2534",
        "title": "Empirical Validation of Persistent HGP Suppression",
        "total_nights": len(nights),
        "correction_nights": int((nights["group"] == "CORRECTION").sum()),
        "no_correction_nights": int((nights["group"] == "NO_CORRECTION").sum()),
        "patients": sorted(nights["patient_id"].unique().tolist()),
        "n_patients": int(nights["patient_id"].nunique()),
    }

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2534_hgp_validation.json"

    # Convert any non-serializable types
    def sanitize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(v) for v in obj]
        return obj

    with open(out_path, "w") as f:
        json.dump(sanitize(results), f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
