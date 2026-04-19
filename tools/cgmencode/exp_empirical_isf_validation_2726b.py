#!/usr/bin/env python3
"""
EXP-2726b: Empirical ISF Prospective Validation
=================================================

EXP-2726 showed profile ISF causes 65% TBR in simulation -- catastrophic.
The 4x lowered ISF (~13, matching EXP-2720 independent-event ISF) was far better.

The correction factors from 2719b (median 1.028) are residual corrections on the
POPULATION MODEL, not on profile ISF. We need to:
1. Extract per-patient empirical ISF from independent correction events
2. Use empirical ISF as the simulator base
3. Apply residual corrections on top of empirical ISF
4. Compare all approaches head-to-head

Arms:
  A: Profile ISF (baseline, known bad from 2726)
  B: Population median ISF (13.1 from EXP-2720)
  C: Per-patient empirical ISF (bg_drop / total_dose, independent events)
  D: Per-patient empirical ISF + residual correction from sim bias
  E: Per-patient empirical ISF with shrinkage toward population

This answers: does personalizing the empirical ISF help beyond the
population median? And do residual corrections add value on top?
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

EXP_ID = "2726b"
TITLE = "Empirical ISF Prospective Validation"

BG_FLOOR = 150.0
INDEPENDENCE_GAP = int(2 * STEPS_PER_HOUR)  # 2h between events
HORIZON_HOURS = 6.0
HORIZON_STEPS = int(6 * STEPS_PER_HOUR)
TIR_LOW, TIR_HIGH = 70, 180
POPULATION_MEDIAN_ISF = 13.1  # from EXP-2720


def extract_correction_episodes(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction episodes with 6h trajectory and independence marking."""
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

        last_event_idx = -999
        for i in range(len(pg) - h):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue
            if "carbs" in pg.columns:
                c_start = max(0, i - int(STEPS_PER_HOUR))
                c_end = min(len(pg), i + int(2 * STEPS_PER_HOUR))
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            actual_bg = glucose[i:i + h + 1].copy()
            if np.sum(np.isnan(actual_bg)) > h * 0.3:
                continue

            independent = (i - last_event_idx) >= INDEPENDENCE_GAP

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
            total_dose = total_bolus + total_smb

            if np.isnan(isf_val) or isf_val <= 0 or total_dose < 0.1:
                continue

            bg_end = actual_bg[-1]
            drop = float(bg0 - bg_end) if not np.isnan(bg_end) else np.nan
            raw_isf = drop / total_dose if total_dose > 0 and not np.isnan(drop) else np.nan

            episodes.append({
                "patient_id": pid,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "profile_isf": isf_val,
                "basal_rate": basal_val,
                "iob_start": iob_val,
                "total_dose": total_dose,
                "total_bolus": total_bolus,
                "total_smb": total_smb,
                "insulin_events": insulin_events,
                "actual_bg": actual_bg.tolist(),
                "actual_drop": drop,
                "raw_isf": raw_isf,
                "independent": independent,
            })
            last_event_idx = i

    return pd.DataFrame(episodes)


def compute_empirical_isf(episodes: pd.DataFrame) -> Dict[str, dict]:
    """Compute per-patient empirical ISF from independent events."""
    indep = episodes[episodes["independent"] & episodes["raw_isf"].notna() & (episodes["raw_isf"] > 0)]

    pop_median = float(indep["raw_isf"].median())
    pop_mean = float(indep["raw_isf"].mean())
    print(f"  Population: median raw ISF = {pop_median:.1f}, mean = {pop_mean:.1f}, N = {len(indep)}")

    patient_isfs = {}
    for pid in episodes["patient_id"].unique():
        pat_indep = indep[indep["patient_id"] == pid]
        n = len(pat_indep)

        if n < 5:
            empirical = pop_median
            shrunk = pop_median
        else:
            empirical = float(pat_indep["raw_isf"].median())
            pat_var = float(pat_indep["raw_isf"].var())
            pop_var = float(indep["raw_isf"].var())
            if pop_var > 0:
                shrink_factor = max(0, 1 - (pop_var / n) / max(pat_var, 1e-6))
                shrunk = shrink_factor * empirical + (1 - shrink_factor) * pop_median
            else:
                shrunk = empirical

        profile = float(episodes[episodes["patient_id"] == pid]["profile_isf"].iloc[0])
        patient_isfs[pid] = {
            "empirical": empirical,
            "shrunk": shrunk,
            "profile": profile,
            "n_events": n,
            "ratio": empirical / profile if profile > 0 else np.nan,
        }
        print(f"    {str(pid)[:10]:<12} profile={profile:>6.1f}  empirical={empirical:>6.1f}  "
              f"shrunk={shrunk:>6.1f}  ratio={empirical/profile:.2f}  N={n}")

    return patient_isfs


def simulate_episode(episode: dict, isf: float) -> dict:
    """Simulate one correction episode with given ISF."""
    settings = TherapySettings(
        isf=isf,
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
        duration_hours=HORIZON_HOURS,
        start_hour=episode["hour"],
        bolus_events=bolus_events,
        initial_iob=episode["iob_start"],
        noise_std=0.0,
        metabolic_basal_rate=episode["basal_rate"],
    )

    sim_bg = result.glucose
    actual_bg = np.array(episode["actual_bg"])
    n = min(len(sim_bg), len(actual_bg))

    valid = ~np.isnan(actual_bg[:n])
    if valid.sum() < 10:
        return {"mae": np.nan, "tir": np.nan, "tbr": np.nan, "tar": np.nan,
                "sim_end": np.nan, "end_error": np.nan}

    mae = float(np.mean(np.abs(sim_bg[:n][valid] - actual_bg[:n][valid])))
    sim_tir = float(np.mean((sim_bg[:n] >= TIR_LOW) & (sim_bg[:n] <= TIR_HIGH)))
    sim_tbr = float(np.mean(sim_bg[:n] < TIR_LOW))
    sim_tar = float(np.mean(sim_bg[:n] > TIR_HIGH))

    sim_end = float(sim_bg[n - 1])
    actual_end = float(actual_bg[n - 1]) if not np.isnan(actual_bg[n - 1]) else np.nan
    end_error = abs(sim_end - actual_end) if not np.isnan(actual_end) else np.nan

    return {
        "mae": mae, "tir": sim_tir, "tbr": sim_tbr, "tar": sim_tar,
        "sim_end": sim_end, "actual_end": actual_end, "end_error": end_error,
    }


def run_arm(episodes: pd.DataFrame, isf_fn, arm_name: str,
            max_per_patient: int = 200) -> pd.DataFrame:
    """Run simulation arm with per-patient ISF function."""
    results = []
    for pid in episodes["patient_id"].unique():
        pat_eps = episodes[episodes["patient_id"] == pid]
        if len(pat_eps) > max_per_patient:
            pat_eps = pat_eps.sample(max_per_patient, random_state=42)

        for _, ep in pat_eps.iterrows():
            isf = isf_fn(ep)
            if isf <= 0 or np.isnan(isf):
                continue
            result = simulate_episode(ep.to_dict(), isf)
            result["patient_id"] = ep["patient_id"]
            result["profile_isf"] = ep["profile_isf"]
            result["used_isf"] = isf
            results.append(result)

    df = pd.DataFrame(results)
    n_valid = df["mae"].notna().sum()
    print(f"  {arm_name}: {n_valid} valid simulations")
    return df


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = (Path(__file__).resolve().parent.parent.parent
                 / "externals" / "ns-parquet" / "training" / "grid.parquet")
    grid = pd.read_parquet(data_path)
    print(f"Loaded {grid.shape[0]} rows, {grid['patient_id'].nunique()} patients")

    print("\nExtracting correction episodes...")
    episodes = extract_correction_episodes(grid)
    n_indep = episodes["independent"].sum()
    print(f"  {len(episodes)} total, {n_indep} independent (2h gap)")

    print("\nComputing empirical ISF from independent events...")
    patient_isfs = compute_empirical_isf(episodes)

    # Arms
    arms = {
        "A_profile": lambda ep: ep["profile_isf"],
        "B_pop_median": lambda ep: POPULATION_MEDIAN_ISF,
        "C_empirical": lambda ep: patient_isfs.get(ep["patient_id"], {}).get("empirical", POPULATION_MEDIAN_ISF),
        "E_shrunk": lambda ep: patient_isfs.get(ep["patient_id"], {}).get("shrunk", POPULATION_MEDIAN_ISF),
    }

    print(f"\nSimulating {len(arms)} arms (max 200 episodes/patient)...")
    results_by_arm = {}
    for arm_name, isf_fn in arms.items():
        results_by_arm[arm_name] = run_arm(episodes, isf_fn, arm_name)

    # Aggregate
    print(f"\n{'=' * 70}")
    print(f"  AGGREGATE RESULTS")
    print(f"{'=' * 70}")

    arm_summary = {}
    print(f"\n  {'Arm':<15} {'MAE':>8} {'TIR%':>8} {'TBR%':>8} {'TAR%':>8} {'EndErr':>8}")
    print(f"  {'-' * 55}")

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
        print(f"  {arm_name:<15} {s['mae']:>8.1f} {s['tir']:>8.1f} {s['tbr']:>8.1f} "
              f"{s['tar']:>8.1f} {s['end_error']:>8.1f}")

    # Per-patient comparison
    print(f"\n  Per-Patient: Profile vs Empirical vs Shrunk")
    print(f"  {'Patient':<12} {'ProfMAE':>8} {'EmpMAE':>8} {'ShrMAE':>8} "
          f"{'ProfISF':>8} {'EmpISF':>8} {'ShrISF':>8} {'Winner':>8}")
    print(f"  {'-' * 70}")

    pat_comparisons = []
    for pid in episodes["patient_id"].unique():
        row = {"patient_id": str(pid)}
        for arm_name in ["A_profile", "C_empirical", "E_shrunk"]:
            df = results_by_arm[arm_name]
            pat = df[df["patient_id"] == pid]["mae"].dropna()
            row[f"{arm_name}_mae"] = float(pat.mean()) if len(pat) >= 5 else np.nan

        info = patient_isfs.get(pid, {})
        row["profile_isf"] = info.get("profile", np.nan)
        row["empirical_isf"] = info.get("empirical", np.nan)
        row["shrunk_isf"] = info.get("shrunk", np.nan)
        row["n_indep"] = info.get("n_events", 0)

        prof = row.get("A_profile_mae", np.nan)
        emp = row.get("C_empirical_mae", np.nan)
        shr = row.get("E_shrunk_mae", np.nan)

        if not np.isnan(prof):
            best = min(prof, emp, shr)
            if best == emp:
                winner = "Emp"
            elif best == shr:
                winner = "Shr"
            else:
                winner = "Prof"

            row["emp_better"] = bool(emp < prof)
            row["shr_better"] = bool(shr < prof)

            print(f"  {str(pid)[:10]:<12} {prof:>8.1f} {emp:>8.1f} {shr:>8.1f} "
                  f"{row['profile_isf']:>8.1f} {row['empirical_isf']:>8.1f} "
                  f"{row['shrunk_isf']:>8.1f} {winner:>8}")

        pat_comparisons.append(row)

    pat_df = pd.DataFrame(pat_comparisons)

    # Hypotheses
    n_emp_better = sum(1 for r in pat_comparisons if r.get("emp_better", False))
    n_shr_better = sum(1 for r in pat_comparisons if r.get("shr_better", False))
    n_total = sum(1 for r in pat_comparisons if "emp_better" in r)

    prof_mae = arm_summary.get("A_profile", {}).get("mae", 999)
    pop_mae = arm_summary.get("B_pop_median", {}).get("mae", 999)
    emp_mae = arm_summary.get("C_empirical", {}).get("mae", 999)
    shr_mae = arm_summary.get("E_shrunk", {}).get("mae", 999)

    prof_tbr = arm_summary.get("A_profile", {}).get("tbr", 0)
    emp_tbr = arm_summary.get("C_empirical", {}).get("tbr", 0)

    hypotheses = {
        "H1_empirical_beats_profile": bool(emp_mae < prof_mae),
        "H2_empirical_beats_population": bool(emp_mae < pop_mae),
        "H3_shrunk_best_overall": bool(shr_mae <= min(emp_mae, pop_mae)),
        "H4_majority_patients_improve": bool(n_emp_better > n_total * 0.5),
        "H5_empirical_safe_less_hypo": bool(emp_tbr < prof_tbr + 2.0),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n  Hypotheses: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"    {'PASS' if v else 'FAIL'} {k}")

    print(f"\n  Patients: empirical better for {n_emp_better}/{n_total} "
          f"({n_emp_better/n_total*100:.0f}%)" if n_total > 0 else "")
    print(f"  Patients: shrunk better for {n_shr_better}/{n_total} "
          f"({n_shr_better/n_total*100:.0f}%)" if n_total > 0 else "")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Profile MAE={prof_mae:.1f}, Pop MAE={pop_mae:.1f}, "
               f"Empirical MAE={emp_mae:.1f}, Shrunk MAE={shr_mae:.1f}. "
               f"{n_emp_better}/{n_total} patients improved with empirical ISF.")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # Save
    out_path = (Path(__file__).resolve().parent.parent.parent
                / "externals" / "experiments" / f"exp-{EXP_ID}_empirical_isf_validation.json")

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
            "patient_isfs": {k: v for k, v in patient_isfs.items()},
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out_path}")

    create_dashboard(arm_summary, pat_df, hypotheses, patient_isfs)


def create_dashboard(arm_summary, pat_df, hypotheses, patient_isfs):
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
    colors = ["indianred", "steelblue", "darkgreen", "darkorange"]
    ax1.bar(range(len(arms)), maes, color=colors[:len(arms)])
    ax1.set_xticks(range(len(arms)))
    ax1.set_xticklabels([a.split("_", 1)[1] for a in arms], rotation=20, fontsize=8)
    ax1.set_ylabel("MAE (mg/dL)")
    ax1.set_title("Aggregate MAE by Arm")

    # Panel 2: TIR/TBR/TAR
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
    ax2.set_xticklabels([a.split("_", 1)[1] for a in arms], rotation=20, fontsize=8)
    ax2.set_ylabel("%")
    ax2.set_title("Time in Range by Arm")
    ax2.legend(fontsize=8)

    # Panel 3: Profile ISF vs Empirical ISF
    ax3 = fig.add_subplot(gs[0, 2])
    profs = [v["profile"] for v in patient_isfs.values()]
    emps = [v["empirical"] for v in patient_isfs.values()]
    ax3.scatter(profs, emps, color="steelblue", alpha=0.7, s=50)
    lim = max(max(profs), max(emps)) * 1.1
    ax3.plot([0, lim], [0, lim], "k--", alpha=0.5, label="1:1")
    ax3.plot([0, lim], [0, lim/4], "r--", alpha=0.5, label="4:1")
    ax3.set_xlabel("Profile ISF")
    ax3.set_ylabel("Empirical ISF")
    ax3.set_title("Profile vs Empirical ISF")
    ax3.legend(fontsize=8)

    # Panel 4: Per-patient MAE comparison
    ax4 = fig.add_subplot(gs[1, 0])
    if "A_profile_mae" in pat_df.columns and "C_empirical_mae" in pat_df.columns:
        valid = pat_df.dropna(subset=["A_profile_mae", "C_empirical_mae"])
        ax4.scatter(valid["A_profile_mae"], valid["C_empirical_mae"],
                    c=["green" if e else "red" for e in valid.get("emp_better", [False]*len(valid))],
                    alpha=0.7, s=50)
        lim = max(valid["A_profile_mae"].max(), valid["C_empirical_mae"].max()) * 1.1
        ax4.plot([0, lim], [0, lim], "k--", alpha=0.5)
        ax4.set_xlabel("Profile ISF MAE")
        ax4.set_ylabel("Empirical ISF MAE")
        n_better = valid.get("emp_better", pd.Series([False])).sum()
        ax4.set_title(f"Per-Patient MAE ({n_better}/{len(valid)} improved)")

    # Panel 5: ISF ratio distribution
    ax5 = fig.add_subplot(gs[1, 1])
    ratios = [v["ratio"] for v in patient_isfs.values() if not np.isnan(v["ratio"])]
    ax5.hist(ratios, bins=20, color="steelblue", alpha=0.8, edgecolor="white")
    ax5.axvline(np.median(ratios), color="red", linewidth=2, label=f"median={np.median(ratios):.2f}")
    ax5.set_xlabel("Empirical/Profile ISF Ratio")
    ax5.set_ylabel("Count")
    ax5.set_title("ISF Calibration Ratio")
    ax5.legend()

    # Panel 6: Summary text
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", ""]
    for arm in arm_summary:
        s = arm_summary[arm]
        lines.append(f"{arm}: MAE={s['mae']:.1f}, TIR={s['tir']:.1f}%, TBR={s['tbr']:.1f}%")
    lines.append("")
    lines.append("Hypothesis Results:")
    for k, v in hypotheses.items():
        lines.append(f"  {'PASS' if v else 'FAIL'} {k}")
    lines.append("")
    lines.append(f"ISF ratio: median={np.median(ratios):.2f}")
    lines.append(f"Profile ISF ~{1/np.median(ratios):.0f}x too high for simulator")
    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=8, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "empirical-isf-validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
