#!/usr/bin/env python3
"""
EXP-2741: Controller-Compensated CR Extraction
================================================

EXP-2729 extracted CR by observing glucose rise after meals, but the
deconfounded CR was too aggressive (EXP-2738: 20/22 patients worse).

Root cause: During meals, the controller SUSPENDS basal (negative excess),
so total insulin < bolus. The simulator doesn't know about basal suspension,
so when it uses a low CR → high carb rise, it overpredicts glucose.

FIX: Bilateral meal deconfounding:
1. For each meal episode, compute TOTAL insulin delivered (bolus + SMB + net_basal)
2. Compute insulin's glucose impact (BGI) using validated ISF
3. Subtract BGI from observed glucose change → pure carb impact
4. CR_compensated = carbs / (carb_impact / ISF)

This produces a CR appropriate for the simulator context where only
the user's bolus is modeled.

HYPOTHESES:
  H1: Compensated CR differs from deconfounded CR by >20% (compensation matters)
  H2: Compensated CR is closer to profile CR than deconfounded CR
  H3: Simulator MAE with compensated CR improves over profile (>40% of patients)
  H4: Simulator MAE with compensated CR beats deconfounded CR (>60% of patients)
  H5: Safety maintained (TBR not worse with compensated CR)

REFERENCES: EXP-2729, EXP-2738, EXP-2739 (ISF validated)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)

EXP_ID = "2741"
TITLE = "Controller-Compensated CR Extraction"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2729 = Path("externals/experiments/exp-2729_carb_ratio.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/cr-compensated")

MIN_CARBS = 10.0
MEAL_HORIZON = 48    # 4h
MIN_SPACING = 48     # 4h independence
MAX_EPISODES = 40
DIA_HOURS = 5.0
STEP_MIN = 5


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    return grid[grid["patient_id"].isin(qualified)]


def load_prior_results():
    """Load ISF corrections and prior CR results."""
    isf_corrections = {}
    d = json.loads(EXP_2719B.read_text())
    for pp in d["results"]["2h"]["per_patient"]:
        isf_corrections[pp["patient_id"]] = {
            "correction_factor": pp["correction_factor"],
            "empirical_isf": pp["empirical_isf"],
            "profile_isf": pp["profile_isf"],
        }

    cr_prior = {}
    d2 = json.loads(EXP_2729.read_text())
    for pp in d2["per_patient"]:
        cr_prior[pp["patient_id"]] = {
            "profile_cr": pp["profile_cr"],
            "deconfounded_cr": pp["deconfounded_cr"],
            "observed_cr": pp.get("observed_cr_indep", pp.get("observed_cr_all")),
        }

    return isf_corrections, cr_prior


def biexponential_activity(t_min, dia_hours=5.0, peak_min=75):
    """Insulin activity curve (fraction of total action per minute)."""
    tau = dia_hours * 60  # total DIA in minutes
    if t_min < 0 or t_min > tau:
        return 0.0
    # Simplified exponential model matching LoopKit
    tp = peak_min
    td = tau
    a = 2 * tp * td / (td - tp)
    S = 1.0 / (1.0 - a / td + a / (td - tp))
    activity = S * (t_min / (tp * tp)) * np.exp(-t_min / tp)
    return max(activity, 0.0)


def compute_meal_bgi(pg_slice, isf, start_idx, horizon):
    """Compute BGI from all insulin during a meal window.
    
    Uses the bilateral approach: for each insulin delivery in the window,
    compute its glucose impact using the activity curve and ISF.
    """
    bolus = pg_slice["bolus"].values
    smb = pg_slice["bolus_smb"].values if "bolus_smb" in pg_slice else np.zeros(len(pg_slice))
    net_basal = pg_slice["net_basal"].values if "net_basal" in pg_slice else np.zeros(len(pg_slice))
    sched_basal = pg_slice["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg_slice else np.zeros(len(pg_slice))

    total_bgi = 0.0  # cumulative glucose impact over horizon

    for j in range(horizon):
        # Insulin delivered at step j
        step_bolus = bolus[j] if j < len(bolus) else 0
        step_smb = smb[j] if j < len(smb) else 0
        step_excess_basal = ((net_basal[j] - sched_basal[j]) * STEP_MIN / 60.0
                              if j < len(net_basal) else 0)
        total_step_insulin = step_bolus + step_smb + step_excess_basal

        if abs(total_step_insulin) < 0.001:
            continue

        # Compute BGI from this insulin delivery over remaining horizon
        for k in range(j, horizon):
            t_since = (k - j) * STEP_MIN
            activity = biexponential_activity(t_since, DIA_HOURS)
            bgi_step = -total_step_insulin * isf * activity * STEP_MIN
            total_bgi += bgi_step

    return total_bgi


def extract_compensated_cr(grid: pd.DataFrame, isf_corrections: dict):
    """Extract CR with controller compensation subtracted."""
    all_results = {}

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < MEAL_HORIZON + 10:
            continue

        isf_info = isf_corrections.get(pid)
        if not isf_info:
            continue

        # Use corrected ISF for BGI computation (validated in EXP-2739)
        corrected_isf = isf_info["profile_isf"] / isf_info["correction_factor"]
        corrected_isf = np.clip(corrected_isf, 5, 200)

        carbs_col = pg["carbs"].values
        glucose = pg["glucose"].values
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10.0

        episodes = []
        last_meal = -MIN_SPACING - 1

        for i in range(len(pg) - MEAL_HORIZON):
            if carbs_col[i] < MIN_CARBS or i - last_meal < MIN_SPACING:
                continue
            bg0 = glucose[i]
            bg_end = glucose[min(i + MEAL_HORIZON, len(glucose) - 1)]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue

            # Total carbs in window
            total_carbs = float(np.nansum(carbs_col[i:i + 24]))  # 2h carb window
            if total_carbs < MIN_CARBS:
                continue

            # Observed glucose change
            observed_change = bg_end - bg0

            # Compute BGI from ALL insulin during the meal window
            pg_slice = pg.iloc[i:i + MEAL_HORIZON].reset_index(drop=True)
            meal_bgi = compute_meal_bgi(pg_slice, corrected_isf, i, MEAL_HORIZON)

            # Pure carb impact = observed change - insulin impact
            # observed = carb_rise + insulin_drop
            # carb_rise = observed - insulin_drop = observed - meal_bgi
            # (meal_bgi is negative for insulin, so carb_rise = observed - meal_bgi)
            carb_impact = observed_change - meal_bgi  # mg/dL rise from carbs alone

            if carb_impact <= 0:
                continue  # Carbs didn't raise glucose (rare, skip)

            # Compensated CR: carbs per unit glucose rise, scaled by ISF
            # carb_impact = carbs * (ISF / CR) → CR = carbs * ISF / carb_impact
            compensated_cr = total_carbs * corrected_isf / carb_impact

            # Simple CR: just carbs / (rise / ISF)
            if observed_change > 0:
                simple_cr = total_carbs * corrected_isf / observed_change
            else:
                simple_cr = np.nan

            # Bolus-only dose for reference
            bolus_dose = float(np.nansum(pg_slice["bolus"].values[:12]))

            episodes.append({
                "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                "carbs": total_carbs, "bolus": bolus_dose,
                "observed_change": float(observed_change),
                "meal_bgi": float(meal_bgi),
                "carb_impact": float(carb_impact),
                "compensated_cr": float(compensated_cr),
                "simple_cr": float(simple_cr),
            })
            last_meal = i

            if len(episodes) >= MAX_EPISODES:
                break

        if len(episodes) >= 3:
            comp_crs = [e["compensated_cr"] for e in episodes
                        if 0.5 < e["compensated_cr"] < 100]
            simple_crs = [e["simple_cr"] for e in episodes
                          if not np.isnan(e["simple_cr"]) and 0.5 < e["simple_cr"] < 100]

            all_results[pid] = {
                "n_episodes": len(episodes),
                "profile_cr": profile_cr,
                "compensated_cr_median": float(np.median(comp_crs)) if comp_crs else None,
                "compensated_cr_mean": float(np.mean(comp_crs)) if comp_crs else None,
                "simple_cr_median": float(np.median(simple_crs)) if simple_crs else None,
                "corrected_isf": float(corrected_isf),
                "mean_bgi": float(np.mean([e["meal_bgi"] for e in episodes])),
                "mean_carb_impact": float(np.mean([e["carb_impact"] for e in episodes])),
                "episodes": episodes,
            }

    return all_results


def validate_in_simulator(grid, cr_results, isf_corrections, cr_prior):
    """Compare profile, deconfounded, and compensated CR in simulator."""
    validation = []

    for pid, cr_info in cr_results.items():
        isf_info = isf_corrections.get(pid)
        if not isf_info or cr_info["compensated_cr_median"] is None:
            continue

        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        corrected_isf = np.clip(isf_info["profile_isf"] / isf_info["correction_factor"], 5, 200)
        profile_cr = cr_info["profile_cr"]
        compensated_cr = np.clip(cr_info["compensated_cr_median"], 2, 50)
        deconf_cr = cr_prior.get(pid, {}).get("deconfounded_cr", profile_cr)
        deconf_cr = np.clip(deconf_cr, 2, 50) if deconf_cr else profile_cr
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # Evaluate each CR variant on meal episodes
        for cr_name, cr_val in [("profile", profile_cr), ("deconfounded", deconf_cr),
                                 ("compensated", compensated_cr)]:
            settings = TherapySettings(isf=corrected_isf, cr=cr_val,
                                        basal_rate=profile_basal, dia_hours=DIA_HOURS)
            maes = []
            tbrs = []

            for ep in cr_info["episodes"][:20]:
                actual_traj = pg["glucose"].values[ep["idx"]:ep["idx"] + MEAL_HORIZON + 1]
                if len(actual_traj) < MEAL_HORIZON:
                    continue

                bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
                carb_events = [CarbEvent(0, ep["carbs"])]

                try:
                    result = forward_simulate(
                        initial_glucose=ep["bg0"], settings=settings,
                        duration_hours=4.0, start_hour=0,
                        bolus_events=bolus_events, carb_events=carb_events,
                        initial_iob=0.0, metabolic_basal_rate=profile_basal,
                        counter_reg_k=0.3, egp_enabled=True,
                    )
                    sim = np.array(result.glucose)
                    n = min(len(sim), len(actual_traj))
                    valid = ~np.isnan(actual_traj[:n])
                    if valid.sum() >= 3:
                        mae = float(np.mean(np.abs(sim[:n][valid] - actual_traj[:n][valid])))
                        tbr = float(np.sum(sim[:n] < 70)) / n
                        maes.append(mae)
                        tbrs.append(tbr)
                except Exception:
                    pass

            if maes:
                validation.append({
                    "patient_id": pid,
                    "cr_type": cr_name,
                    "cr_value": cr_val,
                    "mae": float(np.mean(maes)),
                    "tbr": float(np.mean(tbrs)),
                    "n_episodes": len(maes),
                })

    return pd.DataFrame(validation)


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()
    isf_corrections, cr_prior = load_prior_results()
    print(f"Loaded {grid['patient_id'].nunique()} patients")

    # Extract compensated CR
    print(f"\n{'=' * 60}")
    print("  BILATERAL MEAL DECONFOUNDING")
    print(f"{'=' * 60}")

    cr_results = extract_compensated_cr(grid, isf_corrections)
    print(f"Extracted compensated CR for {len(cr_results)} patients\n")

    print(f"  {'Patient':<14} {'ProfCR':>7} {'DeconfCR':>9} {'CompCR':>7} "
          f"{'MeanBGI':>8} {'CarbImpact':>11} {'N':>3}")
    print(f"  {'-' * 65}")

    for pid, info in sorted(cr_results.items()):
        deconf = cr_prior.get(pid, {}).get("deconfounded_cr", None)
        deconf_str = f"{deconf:.1f}" if deconf else "n/a"
        comp = info["compensated_cr_median"]
        print(f"  {str(pid)[:12]:<14} {info['profile_cr']:>7.1f} {deconf_str:>9} "
              f"{comp:>7.1f} {info['mean_bgi']:>8.1f} {info['mean_carb_impact']:>11.1f} "
              f"{info['n_episodes']:>3}")

    # Validate in simulator
    print(f"\n{'=' * 60}")
    print("  SIMULATOR VALIDATION")
    print(f"{'=' * 60}")

    val_df = validate_in_simulator(grid, cr_results, isf_corrections, cr_prior)

    if len(val_df) == 0:
        print("No validation results!")
        return

    # Pivot to compare
    pivot = val_df.pivot_table(index="patient_id",
                                columns="cr_type",
                                values=["mae", "tbr"])
    pivot.columns = [f"{c[1]}_{c[0]}" for c in pivot.columns]
    pivot = pivot.reset_index()

    print(f"\n  {'Patient':<14} {'ProfMAE':>8} {'DeconfMAE':>10} {'CompMAE':>8} "
          f"{'ProfTBR':>8} {'CompTBR':>8}")
    print(f"  {'-' * 62}")

    for _, r in pivot.iterrows():
        print(f"  {str(r['patient_id'])[:12]:<14} "
              f"{r.get('profile_mae', 999):>8.1f} "
              f"{r.get('deconfounded_mae', 999):>10.1f} "
              f"{r.get('compensated_mae', 999):>8.1f} "
              f"{r.get('profile_tbr', 0):>8.3f} "
              f"{r.get('compensated_tbr', 0):>8.3f}")

    n = len(pivot)

    # Hypothesis testing
    comp_crs = {pid: info["compensated_cr_median"]
                for pid, info in cr_results.items() if info["compensated_cr_median"]}
    deconf_crs = {pid: cr_prior.get(pid, {}).get("deconfounded_cr")
                  for pid in cr_results if cr_prior.get(pid, {}).get("deconfounded_cr")}
    profile_crs = {pid: cr_results[pid]["profile_cr"] for pid in cr_results}

    # H1: Compensated differs from deconfounded by >20%
    common = set(comp_crs.keys()) & set(deconf_crs.keys())
    if common:
        diffs = [abs(comp_crs[p] - deconf_crs[p]) / max(deconf_crs[p], 0.1)
                 for p in common if deconf_crs[p] and deconf_crs[p] > 0]
        h1 = np.median(diffs) > 0.2 if diffs else False
    else:
        h1 = False

    # H2: Compensated closer to profile than deconfounded
    closer_count = 0
    for p in common:
        if deconf_crs.get(p) and comp_crs.get(p) and profile_crs.get(p):
            d_prof = abs(comp_crs[p] - profile_crs[p])
            d_deconf = abs(deconf_crs[p] - profile_crs[p])
            if d_prof < d_deconf:
                closer_count += 1
    h2 = closer_count > len(common) * 0.5 if common else False

    # H3: Compensated CR improves over profile in simulator (>40%)
    if "profile_mae" in pivot and "compensated_mae" in pivot:
        comp_better = (pivot["compensated_mae"] < pivot["profile_mae"]).sum()
        h3 = comp_better > n * 0.4
    else:
        comp_better = 0
        h3 = False

    # H4: Compensated beats deconfounded in simulator (>60%)
    if "deconfounded_mae" in pivot and "compensated_mae" in pivot:
        comp_beats_deconf = (pivot["compensated_mae"] < pivot["deconfounded_mae"]).sum()
        h4 = comp_beats_deconf > n * 0.6
    else:
        comp_beats_deconf = 0
        h4 = False

    # H5: Safety
    if "profile_tbr" in pivot and "compensated_tbr" in pivot:
        tbr_worse = (pivot["compensated_tbr"] > pivot["profile_tbr"] + 0.01).sum()
        h5 = tbr_worse < n * 0.2
    else:
        h5 = True

    hypotheses = {
        "H1_comp_differs_deconf_20pct": bool(h1),
        "H2_comp_closer_to_profile": bool(h2),
        "H3_comp_beats_profile_40pct": bool(h3),
        "H4_comp_beats_deconf_60pct": bool(h4),
        "H5_safety_maintained": bool(h5),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Compensated CR beats profile: {comp_better}/{n}. "
               f"Compensated beats deconfounded: {comp_beats_deconf}/{n}.")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    per_patient_summary = []
    for pid, info in cr_results.items():
        per_patient_summary.append({
            "patient_id": pid,
            "profile_cr": info["profile_cr"],
            "deconfounded_cr": cr_prior.get(pid, {}).get("deconfounded_cr"),
            "compensated_cr": info["compensated_cr_median"],
            "n_episodes": info["n_episodes"],
            "mean_bgi": info["mean_bgi"],
            "mean_carb_impact": info["mean_carb_impact"],
        })

    out = RESULTS_DIR / f"exp-{EXP_ID}_cr_compensated.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": EXP_ID, "title": TITLE,
            "hypotheses": hypotheses,
            "per_patient": per_patient_summary,
            "validation": val_df.to_dict(orient="records") if len(val_df) > 0 else [],
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out}")

    # Dashboard
    create_dashboard(cr_results, cr_prior, pivot, hypotheses)


def create_dashboard(cr_results, cr_prior, pivot, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: Profile vs Compensated CR
    ax1 = fig.add_subplot(gs[0, 0])
    prof_crs = [cr_results[p]["profile_cr"] for p in cr_results]
    comp_crs = [cr_results[p]["compensated_cr_median"] for p in cr_results
                if cr_results[p]["compensated_cr_median"]]
    prof_crs_valid = [cr_results[p]["profile_cr"] for p in cr_results
                       if cr_results[p]["compensated_cr_median"]]
    ax1.scatter(prof_crs_valid, comp_crs, c="steelblue", s=60, alpha=0.7)
    lim = max(max(prof_crs_valid, default=1), max(comp_crs, default=1)) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", lw=1)
    ax1.set_xlabel("Profile CR"); ax1.set_ylabel("Compensated CR")
    ax1.set_title("Profile vs Compensated CR")

    # Panel 2: Deconfounded vs Compensated CR
    ax2 = fig.add_subplot(gs[0, 1])
    deconf = [cr_prior.get(p, {}).get("deconfounded_cr", None) for p in cr_results]
    comp = [cr_results[p]["compensated_cr_median"] for p in cr_results]
    valid = [(d, c) for d, c in zip(deconf, comp) if d and c and d > 0]
    if valid:
        d_vals, c_vals = zip(*valid)
        ax2.scatter(d_vals, c_vals, c="steelblue", s=60, alpha=0.7)
        lim = max(max(d_vals), max(c_vals)) * 1.1
        ax2.plot([0, lim], [0, lim], "r--", lw=1)
    ax2.set_xlabel("Deconfounded CR (EXP-2729)"); ax2.set_ylabel("Compensated CR")
    ax2.set_title("Deconfounded vs Compensated CR")

    # Panel 3: Simulator MAE comparison
    ax3 = fig.add_subplot(gs[0, 2])
    if "profile_mae" in pivot and "compensated_mae" in pivot:
        ax3.scatter(pivot["profile_mae"], pivot["compensated_mae"], c="steelblue", s=60, alpha=0.7)
        lim = max(pivot["profile_mae"].max(), pivot["compensated_mae"].max()) * 1.1
        ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Profile MAE"); ax3.set_ylabel("Compensated MAE")
    ax3.set_title("Simulator MAE: Profile vs Compensated")

    # Panel 4: BGI decomposition
    ax4 = fig.add_subplot(gs[1, 0])
    pids = list(cr_results.keys())
    bgis = [cr_results[p]["mean_bgi"] for p in pids]
    carb_impacts = [cr_results[p]["mean_carb_impact"] for p in pids]
    x = np.arange(len(pids))
    ax4.bar(x, bgis, color="steelblue", alpha=0.7, label="Insulin BGI")
    ax4.bar(x, carb_impacts, bottom=0, color="coral", alpha=0.5, label="Carb Impact")
    ax4.set_xlabel("Patient"); ax4.set_ylabel("mg/dL")
    ax4.set_title("Meal Decomposition: Insulin vs Carbs")
    ax4.legend(fontsize=8)
    ax4.axhline(0, color="black", lw=0.5)

    # Summary
    ax5 = fig.add_subplot(gs[1, 1:])
    ax5.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", "",
             f"Patients analyzed: {len(cr_results)}",
             f"Median compensated CR: {np.median(comp_crs):.1f}" if comp_crs else "",
             f"Median profile CR: {np.median(prof_crs):.1f}",
             "", "Hypotheses:"]
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")
    ax5.text(0.05, 0.95, "\n".join(lines), transform=ax5.transAxes,
             fontsize=10, va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / f'exp-{EXP_ID}-dashboard.png'}")


if __name__ == "__main__":
    main()
