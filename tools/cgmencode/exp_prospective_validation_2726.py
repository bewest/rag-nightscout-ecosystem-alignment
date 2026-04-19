#!/usr/bin/env python3
"""
EXP-2726: Prospective Validation — Do Correction Factors Improve Simulated Outcomes?
======================================================================================

The critical test: EXP-2719b produced per-patient correction factors (median 1.23 at 2h).
But do these corrections ACTUALLY improve glucose control when applied prospectively?

Method:
1. For each patient, replay their actual correction events through the forward simulator
   with (a) their profile ISF and (b) corrected ISF (profile × correction_factor)
2. Compare simulated BG trajectories to actual BG trajectories
3. Measure: MAE, TIR (70-180), time below 70, time above 180

If corrections improve MAE but worsen TIR (or increase hypos), they're not safe.
If they improve both, we have actionable settings.

We also test the other researcher's independent-event ISF (EXP-2720, median 13.1)
as a third arm, creating a head-to-head comparison.

Causal frame: ISF is the controller's assumption about insulin sensitivity.
If ISF is too high, the controller gives too much insulin → larger drops, more hypos.
If ISF is too low, the controller gives too little → inadequate corrections.
Correcting ISF should move simulated outcomes closer to observed.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.forward_simulator import (
    TherapySettings,
    InsulinEvent,
    SimulationResult,
    forward_simulate,
)
from production.deconfounding import STEPS_PER_HOUR

EXP_ID = "2726"
TITLE = "Prospective Validation — Do Correction Factors Improve Outcomes?"

BG_FLOOR = 150.0
HORIZON_STEPS = 6 * STEPS_PER_HOUR  # 6h full DIA
TIR_LOW, TIR_HIGH = 70, 180


def extract_correction_episodes(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction episodes with full 6h glucose trajectory."""
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_iob = "iob" in grid.columns
    has_basal = "scheduled_basal_rate" in grid.columns

    h = int(HORIZON_STEPS)
    episodes = []

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        basal_rate = pg["scheduled_basal_rate"].values if has_basal else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        for i in range(len(pg) - h):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            # Collect actual BG trajectory
            actual_bg = glucose[i:i + h + 1].copy()
            if np.sum(np.isnan(actual_bg)) > h * 0.3:
                continue

            # Collect insulin events over the horizon
            insulin_events = []
            total_bolus = 0.0
            total_smb = 0.0
            for k in range(h):
                if bolus[i + k] > 0:
                    insulin_events.append({
                        "time_minutes": k * 5.0,
                        "units": float(bolus[i + k]),
                        "is_bolus": True,
                    })
                    total_bolus += float(bolus[i + k])
                if smb[i + k] > 0:
                    insulin_events.append({
                        "time_minutes": k * 5.0,
                        "units": float(smb[i + k]),
                        "is_bolus": True,
                    })
                    total_smb += float(smb[i + k])

            isf_val = float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan
            basal_val = float(basal_rate[i]) if not np.isnan(basal_rate[i]) else 0.8
            iob_val = float(iob[i]) if not np.isnan(iob[i]) else 0.0

            if np.isnan(isf_val) or isf_val <= 0:
                continue

            episodes.append({
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "profile_isf": isf_val,
                "basal_rate": basal_val,
                "iob_start": iob_val,
                "total_bolus": total_bolus,
                "total_smb": total_smb,
                "insulin_events": insulin_events,
                "actual_bg": actual_bg.tolist(),
                "actual_drop_6h": float(bg0 - actual_bg[-1]) if not np.isnan(actual_bg[-1]) else np.nan,
            })

    return pd.DataFrame(episodes)


def simulate_episode(episode: dict, isf_override: float) -> dict:
    """Simulate a correction episode with a given ISF."""
    settings = TherapySettings(
        isf=isf_override,
        cr=10.0,
        basal_rate=episode["basal_rate"],
        dia_hours=5.0,
    )

    bolus_events = [
        InsulinEvent(
            time_minutes=ev["time_minutes"],
            units=ev["units"],
            is_bolus=ev["is_bolus"],
        )
        for ev in episode["insulin_events"]
    ]

    result = forward_simulate(
        initial_glucose=episode["bg0"],
        settings=settings,
        duration_hours=6.0,
        start_hour=episode["hour"],
        bolus_events=bolus_events,
        initial_iob=episode["iob_start"],
        noise_std=0.0,
        metabolic_basal_rate=episode["basal_rate"],
    )

    sim_bg = result.glucose
    actual_bg = np.array(episode["actual_bg"])
    n = min(len(sim_bg), len(actual_bg))

    # Metrics
    valid = ~np.isnan(actual_bg[:n])
    if valid.sum() < 10:
        return {"mae": np.nan, "tir": np.nan, "tbr": np.nan, "tar": np.nan}

    mae = float(np.mean(np.abs(sim_bg[:n][valid] - actual_bg[:n][valid])))

    # TIR on simulated trajectory
    sim_tir = float(np.mean((sim_bg[:n] >= TIR_LOW) & (sim_bg[:n] <= TIR_HIGH)))
    sim_tbr = float(np.mean(sim_bg[:n] < TIR_LOW))
    sim_tar = float(np.mean(sim_bg[:n] > TIR_HIGH))

    # End-point accuracy
    sim_end = float(sim_bg[n - 1])
    actual_end = float(actual_bg[n - 1]) if not np.isnan(actual_bg[n - 1]) else np.nan
    end_error = abs(sim_end - actual_end) if not np.isnan(actual_end) else np.nan

    return {
        "mae": mae,
        "tir": sim_tir,
        "tbr": sim_tbr,
        "tar": sim_tar,
        "sim_end": sim_end,
        "actual_end": actual_end if not np.isnan(actual_end) else None,
        "end_error": end_error if not np.isnan(end_error) else None,
    }


def get_correction_factors(grid: pd.DataFrame, episodes: pd.DataFrame) -> Dict[str, float]:
    """Compute per-patient correction factors using EXP-2719b method."""
    # Quick population model: observed_drop = α × bg0_centered + β × excess_insulin + γ × iob + intercept

    events = []
    for _, ep in episodes.iterrows():
        excess = ep["total_bolus"] + ep["total_smb"]
        drop = ep.get("actual_drop_6h", np.nan)
        if np.isnan(drop):
            continue
        events.append({
            "patient_id": ep["patient_id"],
            "bg0_centered": ep["bg0"] - 120.0,
            "excess_insulin": excess,
            "iob_start": ep["iob_start"],
            "observed_drop": drop,
        })

    df = pd.DataFrame(events)
    if len(df) < 100:
        return {}

    X = df[["bg0_centered", "excess_insulin", "iob_start"]].values
    y = df["observed_drop"].values
    X_aug = np.column_stack([X, np.ones(len(X))])
    b, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    y_pred = X_aug @ b
    df["residual"] = y - y_pred

    factors = {}
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        pv = df[mask]
        if len(pv) < 10:
            factors[pid] = 1.0
            continue
        mean_obs = pv["observed_drop"].mean()
        mean_predicted = y_pred[mask.values].mean()
        if mean_predicted > 0:
            factors[pid] = float(mean_obs / mean_predicted)
        else:
            factors[pid] = 1.0

    return factors


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    grid = pd.read_parquet(data_path)
    print(f"Loaded {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    episodes = extract_correction_episodes(grid)
    print(f"Extracted {len(episodes)} correction episodes, {episodes['patient_id'].nunique()} patients")

    # Get correction factors
    print("\nComputing correction factors (EXP-2719b method)...")
    correction_factors = get_correction_factors(grid, episodes)
    cfs = [v for v in correction_factors.values() if v != 1.0]
    print(f"  {len(correction_factors)} patients, median CF = {np.median(cfs):.3f}")

    # Three ISF arms:
    # Arm A: Profile ISF (baseline)
    # Arm B: Profile ISF × correction factor (EXP-2719b)
    # Arm C: Profile ISF × 0.25 (approximate independent-event ISF ratio: 13.1/55)
    arms = {
        "profile": lambda ep: ep["profile_isf"],
        "corrected": lambda ep: ep["profile_isf"] * correction_factors.get(ep["patient_id"], 1.0),
        "lowered_4x": lambda ep: ep["profile_isf"] * 0.25,
    }

    # Simulate
    print(f"\nSimulating {len(episodes)} episodes × {len(arms)} arms...")
    results_by_arm = {arm: [] for arm in arms}

    for arm_name, isf_fn in arms.items():
        arm_results = []
        for idx, ep in episodes.iterrows():
            isf = isf_fn(ep)
            if isf <= 0 or np.isnan(isf):
                continue
            result = simulate_episode(ep.to_dict(), isf)
            result["patient_id"] = ep["patient_id"]
            result["profile_isf"] = ep["profile_isf"]
            result["used_isf"] = isf
            arm_results.append(result)
        results_by_arm[arm_name] = pd.DataFrame(arm_results)
        n_valid = results_by_arm[arm_name]["mae"].notna().sum()
        print(f"  {arm_name}: {n_valid} valid simulations")

    # Aggregate results
    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")

    arm_summary = {}
    print(f"\n  {'Arm':<15} {'MAE':>8} {'TIR%':>8} {'TBR%':>8} {'TAR%':>8} {'EndErr':>8}")
    print(f"  {'-' * 55}")

    for arm_name in arms:
        df = results_by_arm[arm_name]
        valid = df.dropna(subset=["mae"])
        if len(valid) == 0:
            continue

        mae = float(valid["mae"].mean())
        tir = float(valid["tir"].mean()) * 100
        tbr = float(valid["tbr"].mean()) * 100
        tar = float(valid["tar"].mean()) * 100
        end_err = float(valid["end_error"].dropna().mean()) if valid["end_error"].notna().sum() > 0 else np.nan

        arm_summary[arm_name] = {
            "mae": mae, "tir": tir, "tbr": tbr, "tar": tar,
            "end_error": end_err, "n": len(valid),
        }
        print(f"  {arm_name:<15} {mae:>8.1f} {tir:>8.1f} {tbr:>8.1f} {tar:>8.1f} {end_err:>8.1f}")

    # Per-patient comparison
    print(f"\n  Per-Patient: Profile vs Corrected")
    print(f"  {'Patient':<12} {'ProfMAE':>8} {'CorrMAE':>8} {'Δ':>8} {'ProfISF':>8} {'CorrISF':>8} {'CF':>6}")
    print(f"  {'-' * 58}")

    pat_comparisons = []
    for pid in episodes["patient_id"].unique():
        prof_df = results_by_arm["profile"]
        corr_df = results_by_arm["corrected"]

        prof_pat = prof_df[prof_df["patient_id"] == pid]["mae"].dropna()
        corr_pat = corr_df[corr_df["patient_id"] == pid]["mae"].dropna()

        if len(prof_pat) < 5 or len(corr_pat) < 5:
            continue

        prof_mae = float(prof_pat.mean())
        corr_mae = float(corr_pat.mean())
        delta = corr_mae - prof_mae
        cf = correction_factors.get(pid, 1.0)
        prof_isf = float(results_by_arm["profile"][results_by_arm["profile"]["patient_id"] == pid]["profile_isf"].iloc[0])
        corr_isf = prof_isf * cf

        improved = "✓" if delta < 0 else "✗"
        print(f"  {pid[:10]:<12} {prof_mae:>8.1f} {corr_mae:>8.1f} {delta:>+8.1f}{improved} {prof_isf:>8.1f} {corr_isf:>8.1f} {cf:>6.2f}")

        pat_comparisons.append({
            "patient_id": pid,
            "profile_mae": prof_mae,
            "corrected_mae": corr_mae,
            "delta_mae": delta,
            "improved": delta < 0,
            "correction_factor": cf,
            "profile_isf": prof_isf,
            "corrected_isf": corr_isf,
        })

    pat_df = pd.DataFrame(pat_comparisons)

    # Hypotheses
    n_improved = pat_df["improved"].sum() if len(pat_df) > 0 else 0
    n_total = len(pat_df)

    # H1: Corrected ISF improves MAE for majority of patients
    h1_pass = n_improved > n_total * 0.5 if n_total > 0 else False

    # H2: Corrected ISF doesn't increase hypoglycemia (TBR)
    prof_tbr = arm_summary.get("profile", {}).get("tbr", 0)
    corr_tbr = arm_summary.get("corrected", {}).get("tbr", 0)
    h2_pass = corr_tbr <= prof_tbr + 2.0  # Allow 2% margin

    # H3: Corrected ISF improves aggregate MAE
    prof_mae = arm_summary.get("profile", {}).get("mae", 999)
    corr_mae = arm_summary.get("corrected", {}).get("mae", 999)
    h3_pass = corr_mae < prof_mae

    # H4: 4× lowered ISF is worse than correction factors (overcorrects)
    low_mae = arm_summary.get("lowered_4x", {}).get("mae", 999)
    h4_pass = corr_mae < low_mae

    # H5: Correction factors are safe (TBR < 5% for corrected arm)
    h5_pass = corr_tbr < 5.0

    hypotheses = {
        "H1_majority_improved": bool(h1_pass),
        "H2_no_hypo_increase": bool(h2_pass),
        "H3_aggregate_mae_improved": bool(h3_pass),
        "H4_better_than_naive_4x": bool(h4_pass),
        "H5_safe_tbr_under_5pct": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n  Hypotheses: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"    {'✓' if v else '✗'} {k}")

    print(f"\n  Patients improved: {n_improved}/{n_total} ({n_improved/n_total*100:.0f}%)" if n_total > 0 else "")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Corrected MAE={corr_mae:.1f} vs Profile={prof_mae:.1f}. "
               f"{n_improved}/{n_total} patients improved.")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # Save
    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_prospective_validation.json"

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({
            "exp_id": EXP_ID, "title": TITLE,
            "hypotheses": hypotheses,
            "arm_summary": arm_summary,
            "per_patient": pat_comparisons,
            "correction_factors": correction_factors,
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out_path}")

    # Dashboard
    create_dashboard(arm_summary, pat_df, hypotheses, correction_factors)


def create_dashboard(arm_summary, pat_df, hypotheses, correction_factors):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    # Panel 1: MAE by arm
    ax1 = fig.add_subplot(gs[0, 0])
    arms = list(arm_summary.keys())
    maes = [arm_summary[a]["mae"] for a in arms]
    colors = ["steelblue", "darkgreen", "coral"]
    ax1.bar(range(len(arms)), maes, color=colors[:len(arms)])
    ax1.set_xticks(range(len(arms)))
    ax1.set_xticklabels(arms, rotation=15)
    ax1.set_ylabel("MAE (mg/dL)")
    ax1.set_title("Aggregate MAE by Arm")

    # Panel 2: TIR/TBR/TAR by arm
    ax2 = fig.add_subplot(gs[0, 1])
    x = np.arange(len(arms))
    tirs = [arm_summary[a]["tir"] for a in arms]
    tbrs = [arm_summary[a]["tbr"] for a in arms]
    tars = [arm_summary[a]["tar"] for a in arms]
    w = 0.25
    ax2.bar(x - w, tirs, w, label="TIR", color="green", alpha=0.8)
    ax2.bar(x, tbrs, w, label="TBR", color="red", alpha=0.8)
    ax2.bar(x + w, tars, w, label="TAR", color="orange", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(arms, rotation=15)
    ax2.set_ylabel("%")
    ax2.set_title("Time in Range by Arm")
    ax2.legend(fontsize=8)

    # Panel 3: Per-patient MAE comparison
    ax3 = fig.add_subplot(gs[0, 2])
    if len(pat_df) > 0:
        ax3.scatter(pat_df["profile_mae"], pat_df["corrected_mae"],
                    c=["green" if d else "red" for d in pat_df["improved"]], alpha=0.7)
        lim = max(pat_df["profile_mae"].max(), pat_df["corrected_mae"].max()) * 1.1
        ax3.plot([0, lim], [0, lim], "k--", alpha=0.5, label="Equal")
        ax3.set_xlabel("Profile ISF MAE")
        ax3.set_ylabel("Corrected ISF MAE")
        ax3.set_title(f"Per-Patient MAE ({pat_df['improved'].sum()}/{len(pat_df)} improved)")
        ax3.legend()

    # Panel 4: Correction factor vs MAE improvement
    ax4 = fig.add_subplot(gs[1, 0])
    if len(pat_df) > 0:
        ax4.scatter(pat_df["correction_factor"], pat_df["delta_mae"], color="steelblue", alpha=0.7)
        ax4.axhline(0, color="red", linewidth=1, linestyle="--")
        ax4.axvline(1, color="gray", linewidth=1, linestyle="--")
        ax4.set_xlabel("Correction Factor")
        ax4.set_ylabel("ΔMAE (negative = improvement)")
        ax4.set_title("Correction Factor vs MAE Change")

    # Panel 5: Profile ISF vs Corrected ISF
    ax5 = fig.add_subplot(gs[1, 1])
    if len(pat_df) > 0:
        ax5.scatter(pat_df["profile_isf"], pat_df["corrected_isf"], color="steelblue", alpha=0.7)
        lim = max(pat_df["profile_isf"].max(), pat_df["corrected_isf"].max()) * 1.1
        ax5.plot([0, lim], [0, lim], "k--", alpha=0.5)
        ax5.set_xlabel("Profile ISF")
        ax5.set_ylabel("Corrected ISF")
        ax5.set_title("ISF: Profile vs Corrected")

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [f"EXP-{EXP_ID}: Prospective Validation", ""]
    for arm in arm_summary:
        s = arm_summary[arm]
        lines.append(f"{arm}: MAE={s['mae']:.1f}, TIR={s['tir']:.1f}%, TBR={s['tbr']:.1f}%")
    lines.append("")
    lines.append("Hypothesis Results:")
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")
    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "prospective-validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
