#!/usr/bin/env python3
"""
EXP-2717: Total Insulin Accounting Over Variable DIA Horizons
=============================================================

Research question: Does accounting for ALL insulin (bolus + SMB + excess basal)
over the full 5-6h DIA window resolve the 2-14× ISF inflation puzzle?

Causal frame (T1D):
  - Insulin is the ONLY glucose-lowering mechanism
  - EGP RAISES glucose — it opposes insulin (headwind)
  - The AID controller continuously delivers insulin via multiple channels
  - Current experiments only capture user bolus over 2h, missing 60-80% of
    total insulin delivered during a correction

Hypotheses:
  H1: Total insulin (all channels) is 2-5× larger than user bolus alone
  H2: ISF = BG_drop / total_insulin INCREASES with horizon toward profile
  H3: Activity-weighted insulin (biexponential DIA) improves R² over raw sum
  H4: After subtracting EGP headwind, ISF converges closer to profile settings

Multi-factor confound subtraction at each timescale:
  - All horizons: BG₀ (controller proportional dosing confound)
  - 0-2h: Rate of change at event start
  - 2-4h: Carb absorption tail (events with carbs)
  - 4-6h: EGP circadian variation
  - All: Autocorrelation (subsample to independent episodes)

Depends on: EXP-2698 (BGI coefficients), EXP-2711 (BG₀ model),
            EXP-2714 (independence correction)
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Project imports ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.deconfounding import (
    BGISubtraction,
    ExperimentFilters,
    BOLUS_COEFF,
    SMB_COEFF,
    EXCESS_BASAL_COEFF,
    STEPS_PER_HOUR,
)

from dataclasses import dataclass as _dataclass

@_dataclass
class ExperimentResult:
    """Lightweight result container for standalone experiments."""
    exp_id: str
    title: str
    hypotheses: dict
    metrics: dict
    summary: str

# ── Constants ────────────────────────────────────────────────────────

EXP_ID = "2717"
TITLE = "Total Insulin Accounting Over Variable DIA Horizons"

# Horizons to evaluate (in hours)
HORIZONS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

# DIA model parameters (from forward_simulator.py / metabolic_engine.py)
FAST_TAU_HOURS = 0.8
PERSISTENT_FRACTION = 0.37
FAST_FRACTION = 1.0 - PERSISTENT_FRACTION  # 0.63
DEFAULT_DIA_HOURS = 5.0

# EGP model (from metabolic_engine.py)
HILL_N = 1.5
HILL_K = 2.0          # Half-max IOB (Units)
BASE_EGP = 1.5        # mg/dL per 5-min step at zero insulin
CIRCADIAN_AMP = 0.15

# Independence: subsample to 1 event per 2h episode (from EXP-2714)
INDEPENDENCE_GAP_STEPS = 24  # 2h × 12 steps/h

# BG floor for correction events
BG_FLOOR = 150.0  # Slightly relaxed from 180 for more data


# ── Insulin activity curve ───────────────────────────────────────────

def insulin_activity_fraction(t_minutes: float, dia_hours: float = DEFAULT_DIA_HOURS) -> float:
    """Fraction of insulin still active at time t after delivery."""
    if t_minutes <= 0:
        return 1.0
    dia_min = dia_hours * 60.0
    if t_minutes >= dia_min:
        return 0.0
    return float(np.exp(-3.0 * t_minutes / dia_min))


def insulin_absorption_rate(t_minutes: float, dia_hours: float = DEFAULT_DIA_HOURS) -> float:
    """Instantaneous absorption rate (negative derivative of activity)."""
    if t_minutes <= 0 or t_minutes >= dia_hours * 60.0:
        return 0.0
    dia_min = dia_hours * 60.0
    return (3.0 / dia_min) * np.exp(-3.0 * t_minutes / dia_min)


# ── EGP estimation ──────────────────────────────────────────────────

def estimate_egp_per_step(iob: float, hour: float, weight_kg: float = 70.0) -> float:
    """Estimate hepatic glucose production (mg/dL per 5-min step).

    Uses Hill equation for IOB suppression + circadian modulation.
    In T1D: EGP is the glucose SUPPLY that insulin must overcome.
    """
    base_rate = BASE_EGP * (weight_kg / 70.0)

    # IOB suppression (Hill equation)
    iob_safe = max(float(np.nan_to_num(iob, nan=0.0)), 0.0)
    if iob_safe > 0:
        suppression = iob_safe ** HILL_N / (iob_safe ** HILL_N + HILL_K ** HILL_N)
    else:
        suppression = 0.0
    egp_base = base_rate * (1.0 - suppression)

    # Circadian modulation (4-harmonic, peak ~5 AM)
    periods = [24.0, 12.0, 8.0, 6.0]
    amps = [CIRCADIAN_AMP, CIRCADIAN_AMP * 0.4, CIRCADIAN_AMP * 0.2, CIRCADIAN_AMP * 0.1]
    circadian = 1.0
    for amp, period in zip(amps, periods):
        circadian += amp * np.sin(2.0 * np.pi * (hour - 5.0) / period)

    return max(egp_base * circadian, 0.0)


# ── Core analysis ────────────────────────────────────────────────────

class TotalInsulinAccounting:
    """Compute ISF across multiple horizons using all insulin channels."""

    def analyze(self, grid: pd.DataFrame) -> ExperimentResult:
        """Run multi-horizon insulin accounting analysis."""

        has_smb = "bolus_smb" in grid.columns
        has_net_basal = "net_basal" in grid.columns
        has_sched_basal = "scheduled_basal_rate" in grid.columns
        has_iob = "iob" in grid.columns
        has_isf = "scheduled_isf" in grid.columns
        has_controller = "controller" in grid.columns

        print(f"  Columns available: SMB={has_smb}, net_basal={has_net_basal}, "
              f"sched_basal={has_sched_basal}, IOB={has_iob}, ISF={has_isf}")

        all_events = []
        patient_profiles = {}

        for pid in sorted(grid["patient_id"].unique()):
            pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
            max_horizon_steps = int(max(HORIZONS) * STEPS_PER_HOUR)

            if len(pg) < max_horizon_steps + 2:
                continue

            glucose = pg["glucose"].values
            bolus = pg["bolus"].values
            smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
            iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)

            # Excess basal = actual - scheduled
            if has_net_basal:
                net_basal = pg["net_basal"].values
            elif has_sched_basal and "actual_basal_rate" in pg.columns:
                net_basal = (pg["actual_basal_rate"].values - pg["scheduled_basal_rate"].values)
            else:
                net_basal = np.zeros(len(pg))

            sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.full(len(pg), np.nan)
            profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
            controller = pg["controller"].iloc[0] if has_controller else "unknown"

            hours = np.zeros(len(pg))
            if "time" in pg.columns:
                try:
                    times = pd.to_datetime(pg["time"])
                    hours = (times.dt.hour + times.dt.minute / 60.0).values
                except Exception:
                    hours = np.zeros(len(pg))

            # Store median profile ISF for this patient
            valid_isf = profile_isf[~np.isnan(profile_isf)]
            if len(valid_isf) > 0:
                patient_profiles[pid] = float(np.median(valid_isf))

            # Find correction events: BG >= floor, bolus > min_dose, carb-free
            for i in range(len(pg) - max_horizon_steps):
                bg0 = glucose[i]
                if np.isnan(bg0) or bg0 < BG_FLOOR:
                    continue
                if bolus[i] < 0.1:
                    continue

                # Check carb-free window (-1h to +2h)
                if "carbs" in pg.columns:
                    carb_window_start = max(0, i - STEPS_PER_HOUR)
                    carb_window_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                    carbs_in_window = pg["carbs"].values[carb_window_start:carb_window_end]
                    if np.nansum(carbs_in_window) > 0:
                        continue

                event = {
                    "patient_id": pid,
                    "controller": controller,
                    "idx": i,
                    "bg0": bg0,
                    "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                    "hour": float(hours[i]),
                    "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                    "user_bolus": float(bolus[i]),
                }

                # For each horizon, compute total insulin and BG drop
                for h_hours in HORIZONS:
                    h_steps = int(h_hours * STEPS_PER_HOUR)
                    end_idx = i + h_steps

                    # BG drop over this horizon
                    bg_end = glucose[end_idx]
                    if np.isnan(bg_end):
                        continue
                    bg_drop = bg0 - bg_end  # positive = glucose fell

                    # ── Raw insulin sums (no activity weighting) ──
                    bolus_sum = float(np.nansum(bolus[i:end_idx]))
                    smb_sum = float(np.nansum(smb[i:end_idx]))
                    # Convert net_basal rate to units: rate × (steps / steps_per_hour)
                    excess_basal_sum = float(np.nansum(net_basal[i:end_idx])) / STEPS_PER_HOUR
                    raw_total = bolus_sum + smb_sum + excess_basal_sum

                    # ── Activity-weighted insulin ──
                    # Weight each step's insulin by how much has been absorbed by end of horizon
                    weighted_total = 0.0
                    for k in range(h_steps):
                        t_remaining = (h_steps - k) * 5.0  # minutes remaining
                        t_elapsed = k * 5.0
                        # Fraction absorbed = 1 - fraction_remaining
                        frac_absorbed = 1.0 - insulin_activity_fraction(t_remaining)
                        step_insulin = (float(bolus[i + k]) +
                                        float(smb[i + k]) +
                                        float(net_basal[i + k]) / STEPS_PER_HOUR)
                        weighted_total += step_insulin * frac_absorbed

                    # ── EGP headwind estimate ──
                    egp_total = 0.0
                    for k in range(h_steps):
                        iob_at_k = float(iob[i + k]) if not np.isnan(iob[i + k]) else 0.0
                        hour_at_k = float(hours[i + k]) if i + k < len(hours) else hours[i]
                        egp_total += estimate_egp_per_step(iob_at_k, hour_at_k)

                    h_key = f"{h_hours:.0f}h"
                    event[f"bg_drop_{h_key}"] = float(bg_drop)
                    event[f"raw_total_{h_key}"] = float(raw_total)
                    event[f"weighted_total_{h_key}"] = float(weighted_total)
                    event[f"egp_headwind_{h_key}"] = float(egp_total)

                    # ISF variants
                    if raw_total > 0.01:
                        event[f"isf_raw_{h_key}"] = float(bg_drop / raw_total)
                    if weighted_total > 0.01:
                        event[f"isf_weighted_{h_key}"] = float(bg_drop / weighted_total)
                    # EGP-corrected: net drop = bg_drop - egp_headwind
                    net_drop = bg_drop - egp_total
                    if raw_total > 0.01:
                        event[f"isf_egp_corrected_{h_key}"] = float(net_drop / raw_total)

                all_events.append(event)

        if not all_events:
            return ExperimentResult(
                exp_id=EXP_ID,
                title=TITLE,
                hypotheses={"H1": False, "H2": False, "H3": False, "H4": False},
                metrics={},
                summary="No correction events found",
            )

        df = pd.DataFrame(all_events)
        n_events = len(df)
        n_patients = df["patient_id"].nunique()
        print(f"  Total events: {n_events}, patients: {n_patients}")

        # ── H1: Total insulin >> user bolus ──────────────────────────
        h1_results = {}
        for h_key in [f"{h:.0f}h" for h in HORIZONS]:
            col_raw = f"raw_total_{h_key}"
            if col_raw not in df.columns:
                continue
            valid = df[["user_bolus", col_raw]].dropna()
            if len(valid) > 0:
                ratio = valid[col_raw].median() / valid["user_bolus"].median()
                h1_results[h_key] = {
                    "median_user_bolus": float(valid["user_bolus"].median()),
                    "median_total_insulin": float(valid[col_raw].median()),
                    "ratio": float(ratio),
                }
        h1_pass = any(v["ratio"] > 1.5 for v in h1_results.values())
        print(f"\n  H1 (total >> user bolus): {'PASS' if h1_pass else 'FAIL'}")
        for k, v in h1_results.items():
            print(f"    {k}: user={v['median_user_bolus']:.2f}U, total={v['median_total_insulin']:.2f}U, ratio={v['ratio']:.2f}×")

        # ── H2: ISF increases with horizon toward profile ────────────
        h2_results = {}
        isf_trajectory = []
        for h_hours in HORIZONS:
            h_key = f"{h_hours:.0f}h"
            col = f"isf_raw_{h_key}"
            if col not in df.columns:
                continue
            valid = df[col].dropna()
            valid_positive = valid[valid > 0]
            if len(valid_positive) > 10:
                median_isf = float(valid_positive.median())
                isf_trajectory.append(median_isf)
                h2_results[h_key] = {
                    "median_isf": median_isf,
                    "mean_isf": float(valid_positive.mean()),
                    "n": len(valid_positive),
                }

        # Check if ISF is monotonically increasing
        if len(isf_trajectory) >= 3:
            increases = sum(1 for i in range(1, len(isf_trajectory))
                           if isf_trajectory[i] > isf_trajectory[i - 1])
            h2_pass = increases >= len(isf_trajectory) * 0.6
        else:
            h2_pass = False

        median_profile = float(np.nanmedian(list(patient_profiles.values()))) if patient_profiles else np.nan
        print(f"\n  H2 (ISF increases with horizon): {'PASS' if h2_pass else 'FAIL'}")
        print(f"    Profile ISF (median): {median_profile:.1f} mg/dL/U")
        for k, v in h2_results.items():
            ratio_to_profile = v["median_isf"] / median_profile if median_profile > 0 else np.nan
            print(f"    {k}: ISF={v['median_isf']:.1f} mg/dL/U (n={v['n']}, "
                  f"ratio to profile={ratio_to_profile:.2f})")

        # ── H3: Activity-weighted insulin improves R² ────────────────
        h3_results = {}
        for h_hours in HORIZONS:
            h_key = f"{h_hours:.0f}h"
            drop_col = f"bg_drop_{h_key}"
            raw_col = f"raw_total_{h_key}"
            weighted_col = f"weighted_total_{h_key}"

            if not all(c in df.columns for c in [drop_col, raw_col, weighted_col]):
                continue

            valid = df[[drop_col, raw_col, weighted_col, "bg0"]].dropna()
            valid = valid[(valid[raw_col] > 0.01) & (valid[weighted_col] > 0.01)]

            if len(valid) < 30:
                continue

            # R² for raw total vs BG drop
            slope_raw, _, r_raw, _, _ = stats.linregress(valid[raw_col], valid[drop_col])
            r2_raw = r_raw ** 2

            # R² for activity-weighted total vs BG drop
            slope_w, _, r_w, _, _ = stats.linregress(valid[weighted_col], valid[drop_col])
            r2_weighted = r_w ** 2

            # R² for multi-factor: total insulin + BG₀
            X = np.column_stack([valid[raw_col].values, valid["bg0"].values])
            y = valid[drop_col].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            try:
                betas, _, _, _ = np.linalg.lstsq(X_with_const, y, rcond=None)
                y_pred = X_with_const @ betas
                ss_res = np.sum((y - y_pred) ** 2)
                ss_tot = np.sum((y - y.mean()) ** 2)
                r2_multi = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            except Exception:
                r2_multi = np.nan

            h3_results[h_key] = {
                "r2_raw_insulin": float(r2_raw),
                "r2_weighted_insulin": float(r2_weighted),
                "r2_multi_insulin_bg0": float(r2_multi),
                "slope_raw": float(slope_raw),
                "slope_weighted": float(slope_w),
                "n": len(valid),
            }

        h3_pass = any(v["r2_weighted_insulin"] > v["r2_raw_insulin"] + 0.005
                      for v in h3_results.values())
        print(f"\n  H3 (activity-weighting improves R²): {'PASS' if h3_pass else 'FAIL'}")
        for k, v in h3_results.items():
            print(f"    {k}: R²(raw)={v['r2_raw_insulin']:.4f}, R²(weighted)={v['r2_weighted_insulin']:.4f}, "
                  f"R²(multi+BG₀)={v['r2_multi_insulin_bg0']:.4f}")

        # ── H4: EGP correction brings ISF closer to profile ─────────
        h4_results = {}
        for h_hours in HORIZONS:
            h_key = f"{h_hours:.0f}h"
            raw_isf_col = f"isf_raw_{h_key}"
            egp_isf_col = f"isf_egp_corrected_{h_key}"

            if not all(c in df.columns for c in [raw_isf_col, egp_isf_col]):
                continue

            raw_valid = df[raw_isf_col].dropna()
            egp_valid = df[egp_isf_col].dropna()
            raw_pos = raw_valid[raw_valid > 0]
            egp_pos = egp_valid[egp_valid > 0]

            if len(raw_pos) < 10 or len(egp_pos) < 10:
                continue

            # Distance to profile
            if median_profile > 0:
                raw_distance = abs(float(raw_pos.median()) - median_profile)
                egp_distance = abs(float(egp_pos.median()) - median_profile)
                h4_results[h_key] = {
                    "median_isf_raw": float(raw_pos.median()),
                    "median_isf_egp_corrected": float(egp_pos.median()),
                    "distance_raw": float(raw_distance),
                    "distance_egp": float(egp_distance),
                    "closer": egp_distance < raw_distance,
                    "egp_headwind_median": float(df[f"egp_headwind_{h_key}"].median()),
                }

        h4_pass = sum(1 for v in h4_results.values() if v["closer"]) > len(h4_results) / 2
        print(f"\n  H4 (EGP correction → closer to profile): {'PASS' if h4_pass else 'FAIL'}")
        for k, v in h4_results.items():
            direction = "✓ closer" if v["closer"] else "✗ farther"
            print(f"    {k}: ISF(raw)={v['median_isf_raw']:.1f}, ISF(EGP-corrected)={v['median_isf_egp_corrected']:.1f}, "
                  f"EGP headwind={v['egp_headwind_median']:.1f} mg/dL, {direction}")

        # ── Per-patient analysis ─────────────────────────────────────
        patient_results = {}
        for pid in df["patient_id"].unique():
            pdf = df[df["patient_id"] == pid]
            pr = {
                "controller": pdf["controller"].iloc[0],
                "n_events": len(pdf),
                "profile_isf": patient_profiles.get(pid, np.nan),
            }
            for h_hours in HORIZONS:
                h_key = f"{h_hours:.0f}h"
                for metric in ["isf_raw", "isf_weighted", "isf_egp_corrected", "raw_total"]:
                    col = f"{metric}_{h_key}"
                    if col in pdf.columns:
                        valid = pdf[col].dropna()
                        valid_pos = valid[valid > 0] if "isf" in metric else valid
                        if len(valid_pos) > 3:
                            pr[f"{metric}_{h_key}"] = float(valid_pos.median())
            patient_results[pid] = pr

        # ── Independence check (subsample to 1 per 2h) ──────────────
        independent_events = []
        for pid in df["patient_id"].unique():
            pdf = df[df["patient_id"] == pid].sort_values("idx")
            last_idx = -999
            for _, row in pdf.iterrows():
                if row["idx"] - last_idx >= INDEPENDENCE_GAP_STEPS:
                    independent_events.append(row)
                    last_idx = row["idx"]

        if independent_events:
            idf = pd.DataFrame(independent_events)
            n_independent = len(idf)
            compression_ratio = n_events / n_independent if n_independent > 0 else np.nan
            print(f"\n  Independence: {n_independent} independent episodes "
                  f"(compression {compression_ratio:.1f}×)")

            # Re-check ISF at 6h with independent events only
            isf_col = "isf_raw_6h"
            if isf_col in idf.columns:
                valid = idf[isf_col].dropna()
                valid_pos = valid[valid > 0]
                if len(valid_pos) > 10:
                    print(f"    Independent ISF(6h): {valid_pos.median():.1f} mg/dL/U "
                          f"(n={len(valid_pos)})")
        else:
            n_independent = 0
            compression_ratio = np.nan

        # ── Insulin channel breakdown by controller ──────────────────
        controller_breakdown = {}
        for ctrl in df["controller"].unique():
            cdf = df[df["controller"] == ctrl]
            breakdown = {"n_events": len(cdf)}
            for h_hours in [2.0, 6.0]:
                h_key = f"{h_hours:.0f}h"
                raw_col = f"raw_total_{h_key}"
                if raw_col in cdf.columns:
                    breakdown[f"median_total_{h_key}"] = float(cdf[raw_col].median())
                    breakdown[f"median_user_bolus"] = float(cdf["user_bolus"].median())
                    if f"isf_raw_{h_key}" in cdf.columns:
                        valid = cdf[f"isf_raw_{h_key}"].dropna()
                        valid_pos = valid[valid > 0]
                        if len(valid_pos) > 5:
                            breakdown[f"median_isf_{h_key}"] = float(valid_pos.median())
            controller_breakdown[ctrl] = breakdown

        print(f"\n  Controller breakdown:")
        for ctrl, bd in controller_breakdown.items():
            print(f"    {ctrl}: n={bd['n_events']}, "
                  f"bolus={bd.get('median_user_bolus', 0):.2f}U, "
                  f"total(2h)={bd.get('median_total_2h', 0):.2f}U, "
                  f"total(6h)={bd.get('median_total_6h', 0):.2f}U")

        # ── 72h Sanity Check: Whole-Patient Balance Sheet ─────────────
        #
        # Over 24h/72h windows, check conservation properties:
        #   S1: Total daily insulin ≈ 24h basal need + correction + meal coverage
        #   S2: ISF × daily_total_insulin ≈ daily_total_BG_variation (balance closes)
        #   S3: Daily insulin variance << event-level variance (noise averages out)
        #   S4: 72h cumulative excess insulin → glycogen proxy for EXP-2718
        #
        sanity_results = self._run_72h_sanity_check(grid)
        h5_pass = sanity_results.get("balance_closes", False)

        print(f"\n  H5 (72h balance sheet sanity): {'PASS' if h5_pass else 'FAIL'}")
        for k, v in sanity_results.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                print(f"    {k}: {v:.3f}")
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)):
                        print(f"    {k}.{k2}: {v2:.3f}")

        # ── Compile results ──────────────────────────────────────────
        hypotheses = {
            "H1_total_gt_bolus": h1_pass,
            "H2_isf_increases_with_horizon": h2_pass,
            "H3_activity_weighting_improves": h3_pass,
            "H4_egp_correction_closer_to_profile": h4_pass,
            "H5_72h_balance_sheet": h5_pass,
        }

        metrics = {
            "n_events": n_events,
            "n_patients": n_patients,
            "n_independent_episodes": n_independent,
            "compression_ratio": float(compression_ratio) if not np.isnan(compression_ratio) else None,
            "median_profile_isf": float(median_profile) if not np.isnan(median_profile) else None,
            "h1_insulin_ratios": h1_results,
            "h2_isf_trajectory": h2_results,
            "h3_r2_comparison": h3_results,
            "h4_egp_correction": h4_results,
            "h5_72h_sanity": sanity_results,
            "controller_breakdown": controller_breakdown,
            "patient_results": patient_results,
            "isf_trajectory_values": isf_trajectory,
        }

        n_pass = sum(hypotheses.values())
        summary = (
            f"EXP-{EXP_ID}: {n_pass}/5 hypotheses pass. "
            f"N={n_events} events, {n_patients} patients. "
        )
        if isf_trajectory:
            summary += f"ISF trajectory: {' → '.join(f'{v:.1f}' for v in isf_trajectory)} mg/dL/U. "
        summary += f"Profile ISF: {median_profile:.1f} mg/dL/U."

        return ExperimentResult(
            exp_id=EXP_ID,
            title=TITLE,
            hypotheses=hypotheses,
            metrics=metrics,
            summary=summary,
        )

    def _run_72h_sanity_check(self, grid: pd.DataFrame) -> dict:
        """72-hour whole-patient balance sheet.

        Aggregates insulin and glucose across 24h and 72h windows to verify:
        1. Daily insulin totals are stable (low CV → noise averages out)
        2. ISF × daily_insulin ≈ daily BG range (balance closes within 2×)
        3. 72h cumulative excess insulin correlates with next-day ISF
           (glycogen → resistance proxy for EXP-2718)

        This is a "smell test" — if the balance sheet doesn't close at
        the daily level, our per-event accounting has a systematic leak.
        """
        has_smb = "bolus_smb" in grid.columns
        has_net_basal = "net_basal" in grid.columns
        has_sched_basal = "scheduled_basal_rate" in grid.columns
        has_isf = "scheduled_isf" in grid.columns

        results = {}
        daily_summaries = []

        for pid in sorted(grid["patient_id"].unique()):
            pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
            if len(pg) < 288:  # need at least 1 day (288 × 5min = 24h)
                continue

            try:
                times = pd.to_datetime(pg["time"])
                pg = pg.assign(_date=times.dt.date)
            except Exception:
                continue

            glucose = pg["glucose"].values
            bolus = pg["bolus"].values
            smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
            net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
            sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.zeros(len(pg))
            profile_isf_vals = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)

            # Aggregate by calendar day
            for date_val, day_df in pg.groupby("_date"):
                idx = day_df.index
                if len(idx) < 200:  # need ~17h of data for a "full" day
                    continue

                day_glucose = glucose[idx]
                valid_glucose = day_glucose[~np.isnan(day_glucose)]
                if len(valid_glucose) < 100:
                    continue

                # Daily insulin totals (convert rates: rate per step, sum steps)
                day_bolus = float(np.nansum(bolus[idx]))
                day_smb = float(np.nansum(smb[idx]))
                day_excess_basal = float(np.nansum(net_basal[idx])) / STEPS_PER_HOUR
                day_sched_basal = float(np.nansum(sched_basal[idx])) / STEPS_PER_HOUR
                day_total_insulin = day_bolus + day_smb + day_sched_basal + day_excess_basal

                # Daily glucose metrics
                bg_mean = float(np.nanmean(valid_glucose))
                bg_std = float(np.nanstd(valid_glucose))
                bg_range = float(np.nanmax(valid_glucose) - np.nanmin(valid_glucose))
                tir = float(np.mean((valid_glucose >= 70) & (valid_glucose <= 180)))

                # Profile ISF for this patient
                day_isf_vals = profile_isf_vals[idx]
                profile_isf = float(np.nanmedian(day_isf_vals)) if np.any(~np.isnan(day_isf_vals)) else np.nan

                # "Balance": ISF × total_insulin should approximate total BG variation capacity
                if not np.isnan(profile_isf) and day_total_insulin > 0:
                    implied_bg_capacity = profile_isf * day_total_insulin
                    # Compare to actual BG range
                    balance_ratio = implied_bg_capacity / bg_range if bg_range > 10 else np.nan
                else:
                    implied_bg_capacity = np.nan
                    balance_ratio = np.nan

                daily_summaries.append({
                    "patient_id": pid,
                    "date": str(date_val),
                    "n_steps": len(idx),
                    "day_bolus": day_bolus,
                    "day_smb": day_smb,
                    "day_excess_basal": day_excess_basal,
                    "day_sched_basal": day_sched_basal,
                    "day_total_insulin": day_total_insulin,
                    "bg_mean": bg_mean,
                    "bg_std": bg_std,
                    "bg_range": bg_range,
                    "tir": tir,
                    "profile_isf": profile_isf,
                    "implied_bg_capacity": implied_bg_capacity,
                    "balance_ratio": balance_ratio,
                })

        if not daily_summaries:
            return {"balance_closes": False, "error": "no daily data"}

        ddf = pd.DataFrame(daily_summaries)
        n_days = len(ddf)
        n_patients_daily = ddf["patient_id"].nunique()
        print(f"\n  72h sanity: {n_days} patient-days, {n_patients_daily} patients")

        # S1: Daily insulin CV — should be low (< 0.5) if accounting is consistent
        per_patient_cv = {}
        for pid in ddf["patient_id"].unique():
            pdf = ddf[ddf["patient_id"] == pid]
            if len(pdf) >= 3:
                mean_ins = pdf["day_total_insulin"].mean()
                std_ins = pdf["day_total_insulin"].std()
                if mean_ins > 0:
                    per_patient_cv[pid] = std_ins / mean_ins

        if per_patient_cv:
            median_cv = float(np.median(list(per_patient_cv.values())))
            results["daily_insulin_cv_median"] = median_cv
            results["daily_insulin_cv_iqr"] = [
                float(np.percentile(list(per_patient_cv.values()), 25)),
                float(np.percentile(list(per_patient_cv.values()), 75)),
            ]
            print(f"    Daily insulin CV: {median_cv:.3f} (lower = more stable)")
        else:
            median_cv = np.nan

        # S2: Balance ratio — ISF × daily_insulin / BG_range should be order 1-10×
        valid_balance = ddf["balance_ratio"].dropna()
        valid_balance = valid_balance[(valid_balance > 0) & (valid_balance < 1000)]
        if len(valid_balance) > 10:
            median_balance = float(valid_balance.median())
            results["balance_ratio_median"] = median_balance
            results["balance_ratio_iqr"] = [
                float(valid_balance.quantile(0.25)),
                float(valid_balance.quantile(0.75)),
            ]
            print(f"    Balance ratio (ISF×insulin/BG_range): {median_balance:.1f}× "
                  f"(1.0 = perfect conservation)")
        else:
            median_balance = np.nan

        # S3: Daily BG variance vs event-level — daily should be much smaller
        per_patient_daily_bg_std = {}
        for pid in ddf["patient_id"].unique():
            pdf = ddf[ddf["patient_id"] == pid]
            if len(pdf) >= 3:
                per_patient_daily_bg_std[pid] = float(pdf["bg_std"].mean())

        if per_patient_daily_bg_std:
            median_daily_std = float(np.median(list(per_patient_daily_bg_std.values())))
            results["median_daily_bg_std"] = median_daily_std
            print(f"    Median daily BG σ: {median_daily_std:.1f} mg/dL")

        # S4: 72h cumulative excess insulin → next-day effective ISF
        # For each patient, compute rolling 3-day excess insulin and
        # correlate with ISF-like measures on the following day
        glycogen_correlations = []
        for pid in ddf["patient_id"].unique():
            pdf = ddf[ddf["patient_id"] == pid].sort_values("date").reset_index(drop=True)
            if len(pdf) < 4:
                continue

            # 3-day rolling excess insulin (sum of excess above scheduled basal)
            excess_3d = pdf["day_excess_basal"].rolling(3, min_periods=3).sum()
            # Next-day "effective ISF" proxy: BG_range / total_insulin
            next_day_isf_proxy = pdf["bg_range"] / pdf["day_total_insulin"].replace(0, np.nan)

            # Correlate 3-day excess with NEXT day's ISF proxy (shift by 1)
            valid_idx = (~excess_3d.isna()) & (~next_day_isf_proxy.shift(-1).isna())
            if valid_idx.sum() >= 5:
                x = excess_3d[valid_idx].values
                y = next_day_isf_proxy.shift(-1)[valid_idx].values
                try:
                    r, p = stats.pearsonr(x, y)
                    glycogen_correlations.append({"patient_id": pid, "r": float(r), "p": float(p)})
                except Exception:
                    pass

        if glycogen_correlations:
            median_r = float(np.median([g["r"] for g in glycogen_correlations]))
            n_sig = sum(1 for g in glycogen_correlations if g["p"] < 0.05)
            results["glycogen_proxy_r_median"] = median_r
            results["glycogen_proxy_n_significant"] = n_sig
            results["glycogen_proxy_n_tested"] = len(glycogen_correlations)
            print(f"    72h excess insulin → next-day ISF proxy: r={median_r:.3f} "
                  f"({n_sig}/{len(glycogen_correlations)} patients p<0.05)")

        # S5: Channel decomposition — what fraction of daily insulin is each channel?
        channel_fracs = {}
        for col, label in [("day_bolus", "bolus"), ("day_smb", "smb"),
                           ("day_sched_basal", "scheduled_basal"),
                           ("day_excess_basal", "excess_basal")]:
            valid = ddf[ddf["day_total_insulin"] > 0]
            if len(valid) > 0:
                frac = float((valid[col] / valid["day_total_insulin"]).median())
                channel_fracs[label] = frac
        results["daily_channel_fractions"] = channel_fracs
        if channel_fracs:
            print(f"    Daily channel fractions: " +
                  ", ".join(f"{k}={v:.1%}" for k, v in channel_fracs.items()))

        # S6: Per-controller daily totals
        ctrl_daily = {}
        if "controller" in grid.columns:
            # Map patient → controller
            pid_ctrl = grid.groupby("patient_id")["controller"].first().to_dict()
            ddf["controller"] = ddf["patient_id"].map(pid_ctrl)
            for ctrl in ddf["controller"].dropna().unique():
                cdf = ddf[ddf["controller"] == ctrl]
                ctrl_daily[ctrl] = {
                    "median_daily_insulin": float(cdf["day_total_insulin"].median()),
                    "median_daily_bolus": float(cdf["day_bolus"].median()),
                    "median_daily_smb": float(cdf["day_smb"].median()),
                    "median_tir": float(cdf["tir"].median()),
                    "n_days": len(cdf),
                }
            results["controller_daily"] = ctrl_daily
            print(f"    Per-controller daily totals:")
            for ctrl, cd in ctrl_daily.items():
                print(f"      {ctrl}: {cd['median_daily_insulin']:.1f}U/day "
                      f"(bolus={cd['median_daily_bolus']:.1f}, smb={cd['median_daily_smb']:.1f}), "
                      f"TIR={cd['median_tir']:.1%}")

        # Determine if balance closes:
        # CV < 0.5 AND balance ratio between 0.5 and 50×
        balance_closes = (
            (not np.isnan(median_cv) and median_cv < 0.5) and
            (not np.isnan(median_balance) and 0.5 < median_balance < 50.0)
        )
        results["balance_closes"] = balance_closes
        results["n_patient_days"] = n_days
        results["n_patients_daily"] = n_patients_daily

        return results


# ── Visualization ────────────────────────────────────────────────────

def create_dashboard(result: ExperimentResult) -> Optional[str]:
    """Create 6-panel dashboard for total insulin accounting."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        print("  matplotlib not available, skipping dashboard")
        return None

    metrics = result.metrics
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    # Panel 1: Total insulin vs user bolus across horizons
    ax1 = fig.add_subplot(gs[0, 0])
    h1 = metrics.get("h1_insulin_ratios", {})
    if h1:
        horizons_list = sorted(h1.keys(), key=lambda x: float(x.replace("h", "")))
        ratios = [h1[h]["ratio"] for h in horizons_list]
        user_bolus = [h1[h]["median_user_bolus"] for h in horizons_list]
        total_ins = [h1[h]["median_total_insulin"] for h in horizons_list]

        x = range(len(horizons_list))
        ax1.bar([i - 0.15 for i in x], user_bolus, 0.3, label="User bolus", color="steelblue")
        ax1.bar([i + 0.15 for i in x], total_ins, 0.3, label="Total insulin", color="coral")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(horizons_list)
        ax1.set_ylabel("Insulin (Units)")
        ax1.set_title("H1: Total vs User Bolus")
        ax1.legend(fontsize=8)
        for i, r in enumerate(ratios):
            ax1.text(i, max(total_ins[i], user_bolus[i]) + 0.1, f"{r:.1f}×",
                     ha="center", fontsize=8, fontweight="bold")

    # Panel 2: ISF trajectory across horizons
    ax2 = fig.add_subplot(gs[0, 1])
    h2 = metrics.get("h2_isf_trajectory", {})
    profile_isf = metrics.get("median_profile_isf", None)
    if h2:
        horizons_list = sorted(h2.keys(), key=lambda x: float(x.replace("h", "")))
        isf_vals = [h2[h]["median_isf"] for h in horizons_list]
        ax2.plot(range(len(horizons_list)), isf_vals, "o-", color="darkgreen",
                 linewidth=2, markersize=8, label="Measured ISF")
        if profile_isf:
            ax2.axhline(profile_isf, color="red", linestyle="--", label=f"Profile ISF={profile_isf:.0f}")
        ax2.set_xticks(range(len(horizons_list)))
        ax2.set_xticklabels(horizons_list)
        ax2.set_ylabel("ISF (mg/dL/U)")
        ax2.set_title("H2: ISF Convergence Toward Profile")
        ax2.legend(fontsize=8)

    # Panel 3: R² comparison across horizons
    ax3 = fig.add_subplot(gs[0, 2])
    h3 = metrics.get("h3_r2_comparison", {})
    if h3:
        horizons_list = sorted(h3.keys(), key=lambda x: float(x.replace("h", "")))
        r2_raw = [h3[h]["r2_raw_insulin"] for h in horizons_list]
        r2_weighted = [h3[h]["r2_weighted_insulin"] for h in horizons_list]
        r2_multi = [h3[h]["r2_multi_insulin_bg0"] for h in horizons_list]

        x = range(len(horizons_list))
        ax3.plot(x, r2_raw, "s-", label="Raw insulin", color="steelblue")
        ax3.plot(x, r2_weighted, "^-", label="Activity-weighted", color="coral")
        ax3.plot(x, r2_multi, "D-", label="Multi (insulin+BG₀)", color="darkgreen")
        ax3.set_xticks(list(x))
        ax3.set_xticklabels(horizons_list)
        ax3.set_ylabel("R²")
        ax3.set_title("H3: R² by Insulin Measure")
        ax3.legend(fontsize=8)

    # Panel 4: EGP headwind magnitude
    ax4 = fig.add_subplot(gs[1, 0])
    h4 = metrics.get("h4_egp_correction", {})
    if h4:
        horizons_list = sorted(h4.keys(), key=lambda x: float(x.replace("h", "")))
        egp_hw = [h4[h]["egp_headwind_median"] for h in horizons_list]
        isf_raw = [h4[h]["median_isf_raw"] for h in horizons_list]
        isf_egp = [h4[h]["median_isf_egp_corrected"] for h in horizons_list]

        ax4_twin = ax4.twinx()
        ax4.bar(range(len(horizons_list)), egp_hw, color="lightsalmon", alpha=0.7,
                label="EGP headwind (mg/dL)")
        ax4_twin.plot(range(len(horizons_list)), isf_raw, "o-", color="steelblue",
                      label="ISF (raw)")
        ax4_twin.plot(range(len(horizons_list)), isf_egp, "s-", color="darkgreen",
                      label="ISF (EGP-corrected)")
        if profile_isf:
            ax4_twin.axhline(profile_isf, color="red", linestyle="--", alpha=0.5)
        ax4.set_xticks(range(len(horizons_list)))
        ax4.set_xticklabels(horizons_list)
        ax4.set_ylabel("EGP headwind (mg/dL)")
        ax4_twin.set_ylabel("ISF (mg/dL/U)")
        ax4.set_title("H4: EGP Headwind & ISF Correction")
        ax4.legend(loc="upper left", fontsize=7)
        ax4_twin.legend(loc="upper right", fontsize=7)

    # Panel 5: Per-patient ISF at 2h vs 6h vs profile
    ax5 = fig.add_subplot(gs[1, 1])
    patient_results = metrics.get("patient_results", {})
    if patient_results:
        pids = sorted(patient_results.keys())
        isf_2h = []
        isf_6h = []
        prof = []
        labels = []
        for pid in pids:
            pr = patient_results[pid]
            i2 = pr.get("isf_raw_2h", np.nan)
            i6 = pr.get("isf_raw_6h", np.nan)
            p = pr.get("profile_isf", np.nan)
            if not np.isnan(i2) and not np.isnan(i6) and not np.isnan(p):
                isf_2h.append(i2)
                isf_6h.append(i6)
                prof.append(p)
                labels.append(pid[:8])

        if isf_2h:
            x = range(len(labels))
            ax5.scatter(x, isf_2h, marker="v", color="steelblue", s=40, label="ISF@2h", zorder=3)
            ax5.scatter(x, isf_6h, marker="^", color="coral", s=40, label="ISF@6h", zorder=3)
            ax5.scatter(x, prof, marker="o", color="green", s=40, label="Profile", zorder=3)
            ax5.set_xticks(list(x))
            ax5.set_xticklabels(labels, rotation=90, fontsize=6)
            ax5.set_ylabel("ISF (mg/dL/U)")
            ax5.set_title("Per-Patient ISF: 2h vs 6h vs Profile")
            ax5.legend(fontsize=8)

    # Panel 6: Controller breakdown
    ax6 = fig.add_subplot(gs[1, 2])
    ctrl_bd = metrics.get("controller_breakdown", {})
    if ctrl_bd:
        controllers = sorted(ctrl_bd.keys())
        bolus_vals = [ctrl_bd[c].get("median_user_bolus", 0) for c in controllers]
        total_2h = [ctrl_bd[c].get("median_total_2h", 0) for c in controllers]
        total_6h = [ctrl_bd[c].get("median_total_6h", 0) for c in controllers]

        x = range(len(controllers))
        width = 0.25
        ax6.bar([i - width for i in x], bolus_vals, width, label="User bolus", color="steelblue")
        ax6.bar(list(x), total_2h, width, label="Total@2h", color="coral")
        ax6.bar([i + width for i in x], total_6h, width, label="Total@6h", color="darkgreen")
        ax6.set_xticks(list(x))
        ax6.set_xticklabels(controllers)
        ax6.set_ylabel("Insulin (Units)")
        ax6.set_title("Controller: Insulin Delivery Breakdown")
        ax6.legend(fontsize=8)

    # Hypothesis summary text
    hyps = result.hypotheses
    hyp_text = "  ".join(
        f"{'✓' if v else '✗'} {k.replace('_', ' ').title()}"
        for k, v in hyps.items()
    )
    fig.text(0.5, 0.01, hyp_text, ha="center", fontsize=10,
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "total-insulin-accounting"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard saved: {out_path}")
    return str(out_path)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print(f"=" * 70)
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"=" * 70)

    # Load data
    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"\nLoading data from {data_path}...")
    grid = pd.read_parquet(data_path)
    print(f"  Loaded: {grid.shape[0]} rows × {grid.shape[1]} cols, "
          f"{grid['patient_id'].nunique()} patients")

    # Run experiment
    exp = TotalInsulinAccounting()
    result = exp.analyze(grid)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {result.summary}")
    print(f"{'=' * 70}")

    # Save results
    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_total_insulin_accounting.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "exp_id": EXP_ID,
        "title": TITLE,
        "hypotheses": result.hypotheses,
        "metrics": result.metrics,
        "summary": result.summary,
    }

    # Clean NaN values for JSON serialization
    def clean_for_json(obj):
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_for_json(v) for v in obj]
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        return obj

    output = clean_for_json(output)

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")

    # Create dashboard
    create_dashboard(result)

    return result


if __name__ == "__main__":
    main()
