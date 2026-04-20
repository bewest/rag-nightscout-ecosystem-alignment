#!/usr/bin/env python3
"""
EXP-2728: EGP-Aware Prospective Validation
============================================

EXP-2727 showed EGP accounts for 42% of the profile→empirical ISF gap.
Now we integrate EGP into the forward simulator and re-run the head-to-head:

Arms:
  A: Profile ISF, no EGP (baseline — catastrophic, from 2726)
  B: Profile ISF + EGP (supply-side aware)
  C: Profile ISF + EGP + counter-reg (full physics)
  D: Empirical ISF, no EGP (best from 2726b)
  E: Empirical ISF + EGP (does EGP help empirical too?)
  F: Profile ISF + EGP + counter-reg, shrunk toward empirical

If Profile+EGP+CR matches or beats Empirical alone, it means the simulator
with proper physics can use profile ISF values directly.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.forward_simulator import (
    TherapySettings, InsulinEvent, forward_simulate,
)
from production.deconfounding import STEPS_PER_HOUR

EXP_ID = "2728"
TITLE = "EGP-Aware Prospective Validation"

BG_FLOOR = 150.0
INDEPENDENCE_GAP = int(2 * STEPS_PER_HOUR)
HORIZON_STEPS = int(6 * STEPS_PER_HOUR)
TIR_LOW, TIR_HIGH = 70, 180


def extract_independent_episodes(grid: pd.DataFrame, max_total: int = 6000) -> pd.DataFrame:
    """Extract independent correction episodes."""
    has_smb = "bolus_smb" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_iob = "iob" in grid.columns
    has_basal = "scheduled_basal_rate" in grid.columns

    h = HORIZON_STEPS
    episodes = []

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        basal_rate = pg["scheduled_basal_rate"].values if has_basal else np.full(len(pg), np.nan)

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        last_idx = -999
        for i in range(len(pg) - h):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue
            if "carbs" in pg.columns:
                c_start = max(0, i - int(STEPS_PER_HOUR))
                c_end = min(len(pg), i + int(2 * STEPS_PER_HOUR))
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            if (i - last_idx) < INDEPENDENCE_GAP:
                continue
            last_idx = i

            actual_bg = glucose[i:i + h + 1].copy()
            if np.sum(np.isnan(actual_bg)) > h * 0.3:
                continue

            total_bolus = float(bolus[i])
            total_smb_sum = 0.0
            insulin_events = []
            if total_bolus > 0:
                insulin_events.append({"time_minutes": 0, "units": total_bolus, "is_bolus": True})
            for k in range(1, min(h, int(2 * STEPS_PER_HOUR))):
                if smb[i + k] > 0:
                    insulin_events.append({"time_minutes": k * 5.0, "units": float(smb[i + k]), "is_bolus": True})
                    total_smb_sum += float(smb[i + k])

            isf_val = float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan
            basal_val = float(basal_rate[i]) if not np.isnan(basal_rate[i]) else 0.8
            iob_val = float(iob[i]) if not np.isnan(iob[i]) else 0.0

            if np.isnan(isf_val) or isf_val <= 0:
                continue

            total_dose = total_bolus + total_smb_sum
            bg_end = actual_bg[-1]
            drop = float(bg0 - bg_end) if not np.isnan(bg_end) else np.nan
            raw_isf = drop / total_dose if total_dose > 0 and not np.isnan(drop) else np.nan

            episodes.append({
                "patient_id": pid,
                "bg0": bg0,
                "hour": float(hours[i]),
                "profile_isf": isf_val,
                "basal_rate": basal_val,
                "iob_start": iob_val,
                "total_dose": total_dose,
                "insulin_events": insulin_events,
                "actual_bg": actual_bg.tolist(),
                "actual_drop": drop,
                "raw_isf": raw_isf,
            })

    df = pd.DataFrame(episodes)
    if len(df) > max_total:
        sampled = []
        for pid in df["patient_id"].unique():
            pat = df[df["patient_id"] == pid]
            if len(pat) > 200:
                pat = pat.sample(200, random_state=42)
            sampled.append(pat)
        df = pd.concat(sampled, ignore_index=True)
    return df


def simulate_episode(ep: dict, isf: float, egp: bool = False, creg: float = 0.0) -> dict:
    settings = TherapySettings(
        isf=isf, cr=10.0,
        basal_rate=ep["basal_rate"],
        dia_hours=5.0,
    )
    bolus_events = [
        InsulinEvent(ev["time_minutes"], ev["units"], ev["is_bolus"])
        for ev in ep["insulin_events"]
    ]
    result = forward_simulate(
        initial_glucose=ep["bg0"],
        settings=settings,
        duration_hours=6.0,
        start_hour=ep["hour"],
        bolus_events=bolus_events,
        initial_iob=ep["iob_start"],
        metabolic_basal_rate=ep["basal_rate"],
        counter_reg_k=creg,
        egp_enabled=egp,
    )
    sim_bg = result.glucose
    actual_bg = np.array(ep["actual_bg"])
    n = min(len(sim_bg), len(actual_bg))
    valid = ~np.isnan(actual_bg[:n])
    if valid.sum() < 10:
        return {"mae": np.nan, "tir": np.nan, "tbr": np.nan, "tar": np.nan, "end_error": np.nan}

    mae = float(np.mean(np.abs(sim_bg[:n][valid] - actual_bg[:n][valid])))
    tir = float(np.mean((sim_bg[:n] >= TIR_LOW) & (sim_bg[:n] <= TIR_HIGH)))
    tbr = float(np.mean(sim_bg[:n] < TIR_LOW))
    tar = float(np.mean(sim_bg[:n] > TIR_HIGH))
    actual_end = float(actual_bg[n-1]) if not np.isnan(actual_bg[n-1]) else np.nan
    end_err = abs(float(sim_bg[n-1]) - actual_end) if not np.isnan(actual_end) else np.nan
    return {"mae": mae, "tir": tir, "tbr": tbr, "tar": tar, "end_error": end_err}


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = (Path(__file__).resolve().parent.parent.parent
                 / "externals" / "ns-parquet" / "training" / "grid.parquet")
    grid = pd.read_parquet(data_path)
    print(f"Loaded {grid.shape[0]} rows, {grid['patient_id'].nunique()} patients")

    episodes = extract_independent_episodes(grid)
    print(f"Extracted {len(episodes)} independent episodes, {episodes['patient_id'].nunique()} patients")

    # Compute per-patient empirical ISF
    pos_isf = episodes[episodes["raw_isf"].notna() & (episodes["raw_isf"] > 0)]
    pop_emp_isf = float(pos_isf["raw_isf"].median())
    pat_emp = pos_isf.groupby("patient_id")["raw_isf"].median().to_dict()
    print(f"Population empirical ISF: {pop_emp_isf:.1f}")

    # Arms configuration
    arms = {
        "A_profile":          {"isf": "profile", "egp": False, "creg": 0.0},
        "B_profile+egp":      {"isf": "profile", "egp": True,  "creg": 0.0},
        "C_profile+egp+creg": {"isf": "profile", "egp": True,  "creg": 1.1},
        "D_empirical":        {"isf": "empirical", "egp": False, "creg": 0.0},
        "E_empirical+egp":    {"isf": "empirical", "egp": True,  "creg": 0.0},
    }

    results_by_arm = {}
    for arm_name, cfg in arms.items():
        arm_results = []
        for _, ep in episodes.iterrows():
            if cfg["isf"] == "profile":
                isf = ep["profile_isf"]
            else:
                isf = pat_emp.get(ep["patient_id"], pop_emp_isf)
            if isf <= 0 or np.isnan(isf):
                continue
            r = simulate_episode(ep.to_dict(), isf, egp=cfg["egp"], creg=cfg["creg"])
            r["patient_id"] = ep["patient_id"]
            arm_results.append(r)
        df = pd.DataFrame(arm_results)
        results_by_arm[arm_name] = df
        valid = df["mae"].notna().sum()
        print(f"  {arm_name}: {valid} valid")

    # Results
    print(f"\n{'=' * 70}")
    print(f"  RESULTS")
    print(f"{'=' * 70}")

    arm_summary = {}
    print(f"\n  {'Arm':<25} {'MAE':>8} {'TIR%':>8} {'TBR%':>8} {'TAR%':>8} {'EndErr':>8}")
    print(f"  {'-' * 65}")

    for arm_name in arms:
        df = results_by_arm[arm_name].dropna(subset=["mae"])
        if len(df) == 0:
            continue
        s = {
            "mae": float(df["mae"].mean()),
            "tir": float(df["tir"].mean()) * 100,
            "tbr": float(df["tbr"].mean()) * 100,
            "tar": float(df["tar"].mean()) * 100,
            "end_error": float(df["end_error"].dropna().mean()),
            "n": int(len(df)),
        }
        arm_summary[arm_name] = s
        print(f"  {arm_name:<25} {s['mae']:>8.1f} {s['tir']:>8.1f} "
              f"{s['tbr']:>8.1f} {s['tar']:>8.1f} {s['end_error']:>8.1f}")

    # Physics contribution analysis
    a_mae = arm_summary.get("A_profile", {}).get("mae", 999)
    b_mae = arm_summary.get("B_profile+egp", {}).get("mae", 999)
    c_mae = arm_summary.get("C_profile+egp+creg", {}).get("mae", 999)
    d_mae = arm_summary.get("D_empirical", {}).get("mae", 999)
    e_mae = arm_summary.get("E_empirical+egp", {}).get("mae", 999)

    print(f"\n  Physics Contributions:")
    print(f"    EGP alone:       {a_mae:.1f} -> {b_mae:.1f} ({(a_mae-b_mae)/a_mae*100:+.1f}% MAE reduction)")
    print(f"    EGP + counter-reg: {a_mae:.1f} -> {c_mae:.1f} ({(a_mae-c_mae)/a_mae*100:+.1f}%)")
    print(f"    Empirical ISF:   {a_mae:.1f} -> {d_mae:.1f} ({(a_mae-d_mae)/a_mae*100:+.1f}%)")
    print(f"    Empirical + EGP: {a_mae:.1f} -> {e_mae:.1f} ({(a_mae-e_mae)/a_mae*100:+.1f}%)")

    gap = a_mae - d_mae
    if gap > 0:
        egp_share = (a_mae - b_mae) / gap * 100
        creg_share = (b_mae - c_mae) / gap * 100
        controller_share = (c_mae - d_mae) / gap * 100
        print(f"\n    Gap decomposition (profile→empirical = {gap:.1f} mg/dL):")
        print(f"      EGP:            {egp_share:+.0f}%")
        print(f"      Counter-reg:    {creg_share:+.0f}%")
        print(f"      Controller:     {controller_share:+.0f}%")

    # Hypotheses
    a_tbr = arm_summary.get("A_profile", {}).get("tbr", 0)
    c_tbr = arm_summary.get("C_profile+egp+creg", {}).get("tbr", 0)
    d_tbr = arm_summary.get("D_empirical", {}).get("tbr", 0)

    hypotheses = {
        "H1_egp_improves_profile": bool(b_mae < a_mae),
        "H2_full_physics_beats_naive_empirical": bool(c_mae < d_mae),
        "H3_egp_reduces_tbr_significantly": bool(c_tbr < a_tbr - 10),
        "H4_empirical_plus_egp_best": bool(e_mae <= min(c_mae, d_mae)),
        "H5_profile_egp_creg_safe": bool(c_tbr < 10),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n  Hypotheses: {n_pass}/5")
    for k, v in hypotheses.items():
        print(f"    {'PASS' if v else 'FAIL'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Profile+EGP+CR MAE={c_mae:.1f} vs Empirical MAE={d_mae:.1f}. "
               f"EGP reduces profile MAE by {(a_mae-b_mae)/a_mae*100:.0f}%.")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # Save
    out_path = (Path(__file__).resolve().parent.parent.parent
                / "externals" / "experiments" / f"exp-{EXP_ID}_egp_aware_validation.json")

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
            "population_empirical_isf": pop_emp_isf,
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out_path}")

    create_dashboard(arm_summary, hypotheses, gap if gap > 0 else 1)


def create_dashboard(arm_summary, hypotheses, gap):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    arms = list(arm_summary.keys())
    maes = [arm_summary[a]["mae"] for a in arms]
    tirs = [arm_summary[a]["tir"] for a in arms]
    tbrs = [arm_summary[a]["tbr"] for a in arms]
    tars = [arm_summary[a]["tar"] for a in arms]
    colors = ["indianred", "orange", "gold", "darkgreen", "steelblue"]

    # Panel 1: MAE
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.barh(range(len(arms)), maes, color=colors[:len(arms)])
    ax1.set_yticks(range(len(arms)))
    ax1.set_yticklabels([a.split("_", 1)[1] for a in arms], fontsize=8)
    ax1.set_xlabel("MAE (mg/dL)")
    ax1.set_title("Trajectory MAE")

    # Panel 2: TBR (safety)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.barh(range(len(arms)), tbrs, color=colors[:len(arms)])
    ax2.set_yticks(range(len(arms)))
    ax2.set_yticklabels([a.split("_", 1)[1] for a in arms], fontsize=8)
    ax2.set_xlabel("TBR (%)")
    ax2.set_title("Time Below Range (Safety)")
    ax2.axvline(5, color="red", linestyle="--", alpha=0.5, label="5% target")
    ax2.legend(fontsize=8)

    # Panel 3: TIR
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.barh(range(len(arms)), tirs, color=colors[:len(arms)])
    ax3.set_yticks(range(len(arms)))
    ax3.set_yticklabels([a.split("_", 1)[1] for a in arms], fontsize=8)
    ax3.set_xlabel("TIR (%)")
    ax3.set_title("Time In Range")

    # Panel 4: Stacked TIR/TBR/TAR
    ax4 = fig.add_subplot(gs[1, 0])
    x = np.arange(len(arms))
    ax4.bar(x, tbrs, label="TBR", color="red", alpha=0.8)
    ax4.bar(x, tirs, bottom=tbrs, label="TIR", color="green", alpha=0.8)
    ax4.bar(x, tars, bottom=[t+i for t, i in zip(tbrs, tirs)], label="TAR", color="orange", alpha=0.8)
    ax4.set_xticks(x)
    ax4.set_xticklabels([a.split("_", 1)[1] for a in arms], rotation=20, fontsize=7)
    ax4.set_ylabel("%")
    ax4.set_title("Glucose Distribution")
    ax4.legend(fontsize=8)

    # Panel 5: Gap decomposition waterfall
    ax5 = fig.add_subplot(gs[1, 1])
    a_mae = arm_summary.get("A_profile", {}).get("mae", 0)
    b_mae = arm_summary.get("B_profile+egp", {}).get("mae", 0)
    c_mae = arm_summary.get("C_profile+egp+creg", {}).get("mae", 0)
    d_mae = arm_summary.get("D_empirical", {}).get("mae", 0)
    steps = ["Profile", "+EGP", "+CounterReg", "Empirical"]
    vals = [a_mae, b_mae, c_mae, d_mae]
    ax5.plot(range(len(steps)), vals, "o-", color="steelblue", linewidth=2, markersize=8)
    ax5.fill_between(range(len(steps)), vals, d_mae, alpha=0.2, color="steelblue")
    ax5.set_xticks(range(len(steps)))
    ax5.set_xticklabels(steps, fontsize=8)
    ax5.set_ylabel("MAE (mg/dL)")
    ax5.set_title("Gap Decomposition Waterfall")

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", ""]
    for a in arms:
        s = arm_summary[a]
        lines.append(f"{a.split('_',1)[1]}: MAE={s['mae']:.1f} TIR={s['tir']:.0f}% TBR={s['tbr']:.1f}%")
    lines.append("")
    lines.append("Hypotheses:")
    for k, v in hypotheses.items():
        lines.append(f"  {'PASS' if v else 'FAIL'} {k}")
    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=8, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "egp-aware-validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
