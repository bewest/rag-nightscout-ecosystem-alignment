#!/usr/bin/env python3
"""
EXP-2717b: Excess Insulin Accounting Over Variable DIA Horizons
================================================================

Follow-up to EXP-2717, which showed that ISF = BG_drop / total_insulin DECREASES
with horizon because scheduled basal is maintenance insulin (counterbalances EGP).

Key insight: Only EXCESS insulin (above scheduled basal) causes BG to DROP.
Scheduled basal keeps glucose steady by matching EGP. The controller adjusts
this balance — suspending when too much bolus insulin is active.

Hypotheses:
  H1: Excess insulin (above scheduled basal) is smaller than total, but positive
  H2: ISF = BG_drop / excess_insulin INCREASES with horizon toward profile
  H3: The ratio excess/total DECREASES with horizon (basal dominates at longer windows)
  H4: Per-patient ISF at optimal horizon correlates with profile ISF (r > 0.5)
  H5: After BG₀ confound subtraction, residual ISF approaches profile

Multi-timescale confound accounting:
  At each horizon h, we subtract:
  - Maintenance insulin: scheduled_basal × h (steady-state EGP counterbalance)
  - BG₀ confound: controller proportional dosing (higher BG → more insulin)
  - EGP variation: circadian and IOB-dependent hepatic output changes

This directly addresses the ISF inflation puzzle: if excess insulin at the
correct DIA horizon gives ISF ≈ profile, the puzzle is solved.
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.deconfounding import STEPS_PER_HOUR

# ── Constants ────────────────────────────────────────────────────────

EXP_ID = "2717b"
TITLE = "Excess Insulin Accounting Over Variable DIA Horizons"

HORIZONS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
BG_FLOOR = 150.0
DEFAULT_DIA_HOURS = 5.0
INDEPENDENCE_GAP_STEPS = 24  # 2h


@dataclass
class Result:
    exp_id: str
    title: str
    hypotheses: dict
    metrics: dict
    summary: str


def insulin_activity_fraction(t_minutes: float, dia_hours: float = DEFAULT_DIA_HOURS) -> float:
    if t_minutes <= 0:
        return 1.0
    dia_min = dia_hours * 60.0
    if t_minutes >= dia_min:
        return 0.0
    return float(np.exp(-3.0 * t_minutes / dia_min))


def analyze(grid: pd.DataFrame) -> Result:
    """Run excess-insulin accounting across horizons."""

    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_sched_basal = "scheduled_basal_rate" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_controller = "controller" in grid.columns

    print(f"  Columns: SMB={has_smb}, net_basal={has_net_basal}, "
          f"sched_basal={has_sched_basal}")

    all_events = []
    patient_profiles = {}

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        max_h_steps = int(max(HORIZONS) * STEPS_PER_HOUR)
        if len(pg) < max_h_steps + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if has_controller else "unknown"

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        valid_isf = profile_isf[~np.isnan(profile_isf)]
        if len(valid_isf) > 0:
            patient_profiles[pid] = float(np.median(valid_isf))

        for i in range(len(pg) - max_h_steps):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR:
                continue
            if bolus[i] < 0.1:
                continue

            # Carb-free check
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            event = {
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                "user_bolus": float(bolus[i]),
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            }

            for h_hours in HORIZONS:
                h_steps = int(h_hours * STEPS_PER_HOUR)
                end_idx = i + h_steps
                bg_end = glucose[end_idx]
                if np.isnan(bg_end):
                    continue

                bg_drop = bg0 - bg_end
                h_key = f"{h_hours:.0f}h"

                # Total insulin delivered in window
                total_bolus = float(np.nansum(bolus[i:end_idx]))
                total_smb = float(np.nansum(smb[i:end_idx]))
                total_net_basal = float(np.nansum(net_basal[i:end_idx])) / STEPS_PER_HOUR
                total_sched_basal = float(np.nansum(sched_basal[i:end_idx])) / STEPS_PER_HOUR
                total_insulin = total_bolus + total_smb + total_sched_basal + total_net_basal

                # EXCESS insulin = total - scheduled basal (maintenance)
                # This is what actually LOWERS glucose beyond steady state
                excess_insulin = total_bolus + total_smb + total_net_basal
                # Note: net_basal already = actual - scheduled, so excess = bolus + smb + net_basal

                # Activity-weighted excess (weight by absorption fraction)
                weighted_excess = 0.0
                for k in range(h_steps):
                    t_remaining_min = (h_steps - k) * 5.0
                    frac_absorbed = 1.0 - insulin_activity_fraction(t_remaining_min)
                    step_excess = (float(bolus[i + k]) +
                                   float(smb[i + k]) +
                                   float(net_basal[i + k]) / STEPS_PER_HOUR)
                    weighted_excess += step_excess * frac_absorbed

                event[f"bg_drop_{h_key}"] = float(bg_drop)
                event[f"total_insulin_{h_key}"] = float(total_insulin)
                event[f"excess_insulin_{h_key}"] = float(excess_insulin)
                event[f"weighted_excess_{h_key}"] = float(weighted_excess)
                event[f"sched_basal_{h_key}"] = float(total_sched_basal)
                event[f"excess_frac_{h_key}"] = (
                    float(excess_insulin / total_insulin) if total_insulin > 0.01 else np.nan
                )

                # ISF variants
                if excess_insulin > 0.01:
                    event[f"isf_excess_{h_key}"] = float(bg_drop / excess_insulin)
                if weighted_excess > 0.01:
                    event[f"isf_weighted_excess_{h_key}"] = float(bg_drop / weighted_excess)
                if total_insulin > 0.01:
                    event[f"isf_total_{h_key}"] = float(bg_drop / total_insulin)

            all_events.append(event)

    if not all_events:
        return Result(EXP_ID, TITLE, {}, {}, "No events")

    df = pd.DataFrame(all_events)
    n_events = len(df)
    n_patients = df["patient_id"].nunique()
    print(f"  Events: {n_events}, patients: {n_patients}")

    median_profile = float(np.nanmedian(list(patient_profiles.values()))) if patient_profiles else np.nan

    # ── H1: Excess insulin is positive but < total ───────────────
    h1_results = {}
    for h_hours in HORIZONS:
        h_key = f"{h_hours:.0f}h"
        exc_col = f"excess_insulin_{h_key}"
        tot_col = f"total_insulin_{h_key}"
        if exc_col in df.columns and tot_col in df.columns:
            valid = df[[exc_col, tot_col]].dropna()
            valid = valid[valid[tot_col] > 0.01]
            if len(valid) > 0:
                h1_results[h_key] = {
                    "median_excess": float(valid[exc_col].median()),
                    "median_total": float(valid[tot_col].median()),
                    "excess_fraction": float(valid[exc_col].median() / valid[tot_col].median()),
                    "pct_positive": float((valid[exc_col] > 0).mean()),
                }

    h1_pass = all(v["pct_positive"] > 0.5 and v["excess_fraction"] < 1.0
                  for v in h1_results.values())
    print(f"\n  H1 (excess positive, < total): {'PASS' if h1_pass else 'FAIL'}")
    for k, v in h1_results.items():
        print(f"    {k}: excess={v['median_excess']:.2f}U, total={v['median_total']:.2f}U, "
              f"frac={v['excess_fraction']:.1%}, positive={v['pct_positive']:.1%}")

    # ── H2: ISF_excess INCREASES with horizon ────────────────────
    h2_results = {}
    isf_excess_trajectory = []
    isf_total_trajectory = []
    for h_hours in HORIZONS:
        h_key = f"{h_hours:.0f}h"
        for prefix, trajectory in [("isf_excess", isf_excess_trajectory),
                                    ("isf_total", isf_total_trajectory)]:
            col = f"{prefix}_{h_key}"
            if col in df.columns:
                valid = df[col].dropna()
                valid_pos = valid[valid > 0]
                if len(valid_pos) > 10:
                    med = float(valid_pos.median())
                    if prefix == "isf_excess":
                        h2_results[h_key] = {
                            "median_isf_excess": med,
                            "n": len(valid_pos),
                        }
                    trajectory.append(med)

    if len(isf_excess_trajectory) >= 3:
        increases = sum(1 for i in range(1, len(isf_excess_trajectory))
                        if isf_excess_trajectory[i] > isf_excess_trajectory[i - 1])
        h2_pass = increases >= len(isf_excess_trajectory) * 0.6
    else:
        h2_pass = False

    print(f"\n  H2 (ISF_excess increases with horizon): {'PASS' if h2_pass else 'FAIL'}")
    print(f"    Profile ISF: {median_profile:.1f} mg/dL/U")
    print(f"    ISF(excess):  {' → '.join(f'{v:.1f}' for v in isf_excess_trajectory)}")
    print(f"    ISF(total):   {' → '.join(f'{v:.1f}' for v in isf_total_trajectory)}")
    for k, v in h2_results.items():
        ratio = v["median_isf_excess"] / median_profile if median_profile > 0 else np.nan
        print(f"    {k}: ISF(excess)={v['median_isf_excess']:.1f} (ratio to profile={ratio:.2f})")

    # ── H3: Excess/total fraction DECREASES with horizon ─────────
    frac_trajectory = []
    for h_hours in HORIZONS:
        h_key = f"{h_hours:.0f}h"
        if h_key in h1_results:
            frac_trajectory.append(h1_results[h_key]["excess_fraction"])

    if len(frac_trajectory) >= 3:
        decreases = sum(1 for i in range(1, len(frac_trajectory))
                        if frac_trajectory[i] < frac_trajectory[i - 1])
        h3_pass = decreases >= len(frac_trajectory) * 0.6
    else:
        h3_pass = False

    print(f"\n  H3 (excess fraction decreases with horizon): {'PASS' if h3_pass else 'FAIL'}")
    print(f"    Excess fraction: {' → '.join(f'{v:.1%}' for v in frac_trajectory)}")

    # ── H4: Per-patient ISF at best horizon correlates with profile ─
    # Find horizon where median ISF_excess is closest to profile
    if isf_excess_trajectory and median_profile > 0:
        best_idx = min(range(len(isf_excess_trajectory)),
                       key=lambda i: abs(isf_excess_trajectory[i] - median_profile))
        best_horizon = HORIZONS[best_idx]
        best_h_key = f"{best_horizon:.0f}h"
    else:
        best_h_key = "2h"

    patient_isf_data = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid]
        prof = patient_profiles.get(pid, np.nan)
        if np.isnan(prof):
            continue

        # Get ISF at each horizon for this patient
        patient_row = {"patient_id": pid, "profile_isf": prof}
        for h_hours in HORIZONS:
            h_key = f"{h_hours:.0f}h"
            col = f"isf_excess_{h_key}"
            if col in pdf.columns:
                valid = pdf[col].dropna()
                valid_pos = valid[valid > 0]
                if len(valid_pos) >= 5:
                    patient_row[f"isf_{h_key}"] = float(valid_pos.median())
        patient_isf_data.append(patient_row)

    h4_results = {}
    h4_pass = False
    if patient_isf_data:
        pidf = pd.DataFrame(patient_isf_data)
        for h_hours in HORIZONS:
            h_key = f"{h_hours:.0f}h"
            col = f"isf_{h_key}"
            if col in pidf.columns:
                valid = pidf[["profile_isf", col]].dropna()
                if len(valid) >= 5:
                    r, p = stats.pearsonr(valid["profile_isf"], valid[col])
                    h4_results[h_key] = {
                        "r": float(r),
                        "p": float(p),
                        "n_patients": len(valid),
                        "median_extracted": float(valid[col].median()),
                        "median_profile": float(valid["profile_isf"].median()),
                    }
                    if r > 0.5 and p < 0.05:
                        h4_pass = True

    print(f"\n  H4 (per-patient ISF_excess correlates with profile): {'PASS' if h4_pass else 'FAIL'}")
    for k, v in h4_results.items():
        sig = "*" if v["p"] < 0.05 else ""
        print(f"    {k}: r={v['r']:.3f}{sig}, extracted={v['median_extracted']:.1f} vs "
              f"profile={v['median_profile']:.1f} (n={v['n_patients']})")

    # ── H5: BG₀ residualized ISF approaches profile ─────────────
    h5_results = {}
    h5_pass = False
    for h_hours in HORIZONS:
        h_key = f"{h_hours:.0f}h"
        drop_col = f"bg_drop_{h_key}"
        exc_col = f"excess_insulin_{h_key}"

        if not all(c in df.columns for c in [drop_col, exc_col]):
            continue

        valid = df[[drop_col, exc_col, "bg0"]].dropna()
        valid = valid[valid[exc_col] > 0.01]
        if len(valid) < 50:
            continue

        # Step 1: Regress BG_drop on BG₀ to get controller-dose confound
        slope_bg0, intercept_bg0, r_bg0, _, _ = stats.linregress(valid["bg0"], valid[drop_col])
        bg0_predicted = intercept_bg0 + slope_bg0 * valid["bg0"]
        residual_drop = valid[drop_col] - bg0_predicted

        # Step 2: ISF from residual (excess insulin explains residual after BG₀ subtracted)
        valid_res = pd.DataFrame({
            "residual_drop": residual_drop.values,
            "excess_insulin": valid[exc_col].values,
        })
        valid_res = valid_res[valid_res["excess_insulin"] > 0.01]

        if len(valid_res) > 30:
            slope_res, intercept_res, r_res, p_res, _ = stats.linregress(
                valid_res["excess_insulin"], valid_res["residual_drop"])
            r2_residual = r_res ** 2

            # The slope IS the residualized ISF
            residualized_isf = float(slope_res)

            h5_results[h_key] = {
                "r2_bg0": float(r_bg0 ** 2),
                "r2_residual_excess": float(r2_residual),
                "residualized_isf": residualized_isf,
                "ratio_to_profile": float(residualized_isf / median_profile) if median_profile > 0 else np.nan,
                "n": len(valid_res),
            }

            if 0.3 < (residualized_isf / median_profile) < 3.0:
                h5_pass = True

    print(f"\n  H5 (BG₀-residualized ISF approaches profile): {'PASS' if h5_pass else 'FAIL'}")
    for k, v in h5_results.items():
        print(f"    {k}: R²(BG₀)={v['r2_bg0']:.4f}, R²(resid~excess)={v['r2_residual_excess']:.4f}, "
              f"ISF={v['residualized_isf']:.1f} (ratio={v['ratio_to_profile']:.2f})")

    # ── Per-controller summary ───────────────────────────────────
    ctrl_summary = {}
    for ctrl in df["controller"].unique():
        cdf = df[df["controller"] == ctrl]
        cs = {"n_events": len(cdf)}
        for h_hours in [2.0, 4.0, 6.0]:
            h_key = f"{h_hours:.0f}h"
            for metric in ["excess_insulin", "isf_excess"]:
                col = f"{metric}_{h_key}"
                if col in cdf.columns:
                    valid = cdf[col].dropna()
                    if "isf" in metric:
                        valid = valid[valid > 0]
                    if len(valid) > 5:
                        cs[f"{metric}_{h_key}"] = float(valid.median())
        ctrl_summary[ctrl] = cs

    print(f"\n  Controller summary:")
    for ctrl, cs in ctrl_summary.items():
        print(f"    {ctrl}: n={cs['n_events']}, "
              f"excess(2h)={cs.get('excess_insulin_2h', 0):.2f}U, "
              f"excess(6h)={cs.get('excess_insulin_6h', 0):.2f}U, "
              f"ISF(2h)={cs.get('isf_excess_2h', 0):.1f}, "
              f"ISF(6h)={cs.get('isf_excess_6h', 0):.1f}")

    # ── Compile ──────────────────────────────────────────────────
    hypotheses = {
        "H1_excess_positive_lt_total": h1_pass,
        "H2_isf_excess_increases": h2_pass,
        "H3_excess_frac_decreases": h3_pass,
        "H4_patient_isf_correlates_profile": h4_pass,
        "H5_residualized_isf_near_profile": h5_pass,
    }

    metrics = {
        "n_events": n_events,
        "n_patients": n_patients,
        "median_profile_isf": float(median_profile) if not np.isnan(median_profile) else None,
        "h1_excess_vs_total": h1_results,
        "h2_isf_trajectory": h2_results,
        "h3_excess_fraction_trajectory": frac_trajectory,
        "h4_patient_correlation": h4_results,
        "h5_residualized_isf": h5_results,
        "isf_excess_trajectory": isf_excess_trajectory,
        "isf_total_trajectory": isf_total_trajectory,
        "controller_summary": ctrl_summary,
        "patient_profiles": patient_profiles,
    }

    n_pass = sum(hypotheses.values())
    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. N={n_events}, {n_patients} patients. "
               f"ISF(excess): {' → '.join(f'{v:.1f}' for v in isf_excess_trajectory)}. "
               f"ISF(total): {' → '.join(f'{v:.1f}' for v in isf_total_trajectory)}. "
               f"Profile={median_profile:.1f}.")

    return Result(EXP_ID, TITLE, hypotheses, metrics, summary)


# ── Visualization ────────────────────────────────────────────────────

def create_dashboard(result: Result) -> Optional[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return None

    m = result.metrics
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    profile_isf = m.get("median_profile_isf", 55)

    # Panel 1: ISF trajectory — excess vs total vs profile
    ax1 = fig.add_subplot(gs[0, 0])
    exc_traj = m.get("isf_excess_trajectory", [])
    tot_traj = m.get("isf_total_trajectory", [])
    if exc_traj:
        x = range(len(exc_traj))
        ax1.plot(x, exc_traj, "o-", color="darkgreen", linewidth=2, markersize=8, label="ISF (excess)")
        if tot_traj:
            ax1.plot(range(len(tot_traj)), tot_traj, "s--", color="steelblue", label="ISF (total)")
        if profile_isf:
            ax1.axhline(profile_isf, color="red", linestyle="--", linewidth=2,
                        label=f"Profile={profile_isf:.0f}")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels([f"{h:.0f}h" for h in HORIZONS[:len(exc_traj)]])
        ax1.set_ylabel("ISF (mg/dL/U)")
        ax1.set_title("ISF: Excess vs Total vs Profile")
        ax1.legend(fontsize=8)

    # Panel 2: Excess fraction decreasing
    ax2 = fig.add_subplot(gs[0, 1])
    frac_traj = m.get("h3_excess_fraction_trajectory", [])
    if frac_traj:
        ax2.bar(range(len(frac_traj)), [f * 100 for f in frac_traj], color="coral")
        ax2.set_xticks(range(len(frac_traj)))
        ax2.set_xticklabels([f"{h:.0f}h" for h in HORIZONS[:len(frac_traj)]])
        ax2.set_ylabel("Excess / Total (%)")
        ax2.set_title("Excess Fraction Decreases with Horizon")
        ax2.axhline(50, color="gray", linestyle=":", alpha=0.5)

    # Panel 3: R² from residualized ISF
    ax3 = fig.add_subplot(gs[0, 2])
    h5 = m.get("h5_residualized_isf", {})
    if h5:
        horizons_list = sorted(h5.keys(), key=lambda x: float(x.replace("h", "")))
        r2_bg0 = [h5[h]["r2_bg0"] for h in horizons_list]
        r2_res = [h5[h]["r2_residual_excess"] for h in horizons_list]
        res_isf = [h5[h]["residualized_isf"] for h in horizons_list]

        ax3_twin = ax3.twinx()
        ax3.plot(range(len(horizons_list)), r2_bg0, "o-", color="steelblue", label="R²(BG₀)")
        ax3.plot(range(len(horizons_list)), r2_res, "s-", color="coral", label="R²(resid~excess)")
        ax3_twin.plot(range(len(horizons_list)), res_isf, "D-", color="darkgreen",
                      label="Residualized ISF")
        if profile_isf:
            ax3_twin.axhline(profile_isf, color="red", linestyle="--", alpha=0.5)
        ax3.set_xticks(range(len(horizons_list)))
        ax3.set_xticklabels(horizons_list)
        ax3.set_ylabel("R²")
        ax3_twin.set_ylabel("ISF (mg/dL/U)")
        ax3.set_title("Residualized ISF After BG₀ Subtraction")
        ax3.legend(loc="upper left", fontsize=7)
        ax3_twin.legend(loc="upper right", fontsize=7)

    # Panel 4: Per-patient ISF vs profile at best horizon
    ax4 = fig.add_subplot(gs[1, 0])
    h4 = m.get("h4_patient_correlation", {})
    patient_profs = m.get("patient_profiles", {})
    # Find best horizon
    best_h = max(h4.keys(), key=lambda k: h4[k].get("r", 0)) if h4 else None
    if best_h and patient_profs:
        ax4.set_title(f"Per-Patient ISF@{best_h}: Extracted vs Profile (r={h4[best_h]['r']:.3f})")
        ax4.set_xlabel("Profile ISF (mg/dL/U)")
        ax4.set_ylabel(f"Extracted ISF@{best_h} (mg/dL/U)")
        # Add 1:1 line
        ax4.plot([0, 300], [0, 300], "k--", alpha=0.3, label="1:1")
        ax4.legend(fontsize=8)

    # Panel 5: Excess insulin by horizon
    ax5 = fig.add_subplot(gs[1, 1])
    h1 = m.get("h1_excess_vs_total", {})
    if h1:
        horizons_list = sorted(h1.keys(), key=lambda x: float(x.replace("h", "")))
        excess = [h1[h]["median_excess"] for h in horizons_list]
        total = [h1[h]["median_total"] for h in horizons_list]
        maintenance = [t - e for t, e in zip(total, excess)]

        x = range(len(horizons_list))
        ax5.bar(x, excess, label="Excess (correction)", color="coral")
        ax5.bar(x, maintenance, bottom=excess, label="Maintenance (basal)", color="lightblue")
        ax5.set_xticks(list(x))
        ax5.set_xticklabels(horizons_list)
        ax5.set_ylabel("Insulin (Units)")
        ax5.set_title("Insulin Decomposition: Correction vs Maintenance")
        ax5.legend(fontsize=8)

    # Panel 6: Summary text
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    summary_lines = [
        f"N = {m.get('n_events', 0)} events, {m.get('n_patients', 0)} patients",
        f"Profile ISF = {profile_isf:.1f} mg/dL/U",
        "",
        "ISF Trajectory (excess insulin):",
    ]
    for i, v in enumerate(exc_traj):
        ratio = v / profile_isf if profile_isf else 0
        summary_lines.append(f"  {HORIZONS[i]:.0f}h: {v:.1f} mg/dL/U ({ratio:.0%} of profile)")
    summary_lines.append("")
    summary_lines.append("Hypothesis Results:")
    for k, v in result.hypotheses.items():
        summary_lines.append(f"  {'✓' if v else '✗'} {k}")

    ax6.text(0.05, 0.95, "\n".join(summary_lines), transform=ax6.transAxes,
             fontsize=10, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "total-insulin-accounting"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")
    return str(out_path)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"\nLoading {data_path}...")
    grid = pd.read_parquet(data_path)
    print(f"  {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    result = analyze(grid)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {result.summary}")
    print(f"{'=' * 70}")

    # Save
    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_excess_insulin_accounting.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({"exp_id": EXP_ID, "title": TITLE,
                         "hypotheses": result.hypotheses,
                         "metrics": result.metrics, "summary": result.summary}), f, indent=2)
    print(f"\nSaved: {out_path}")

    create_dashboard(result)
    return result


if __name__ == "__main__":
    main()
