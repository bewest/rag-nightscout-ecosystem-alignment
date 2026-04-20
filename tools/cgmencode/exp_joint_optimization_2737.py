#!/usr/bin/env python3
"""
EXP-2737: Joint Multi-Setting Optimization (ISF + CR + Basal)
==============================================================

Prior experiments extracted ISF, CR, and basal independently:
  - ISF: EXP-2720/2723 (empirical ~13), EXP-2733 (simulator ~20)
  - CR: EXP-2729 (deconfounded CR, 95.5% improve)
  - Basal: EXP-2730/2735 (EGP-aware drift)

But these settings interact: changing ISF affects optimal CR and basal.
The controller compensates differently depending on all three.

This experiment jointly optimizes the triplet (ISF, CR, basal) per patient
using the forward simulator to find settings that minimize combined
prediction error across BOTH correction and meal episodes.

METHOD:
1. For each patient, extract correction episodes (ISF-sensitive) and
   meal episodes (CR-sensitive) and fasting periods (basal-sensitive)
2. Define combined objective: weighted MAE across all episode types
3. Grid search over (ISF, CR, basal) space
4. Compare: joint-optimal vs independently-extracted settings

HYPOTHESES:
  H1: Joint optimization improves total MAE vs profile (>60% of patients)
  H2: Joint ISF differs from independent ISF by <30% (interactions are moderate)
  H3: Joint CR differs from independent CR by <30%
  H4: Joint optimization improves on independent settings (>40% of patients)
  H5: Safety maintained — joint settings don't increase TBR vs profile

REFERENCES: EXP-2720, EXP-2729, EXP-2733, EXP-2734 (temporal cross-val)
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import optimize, stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)
from production.deconfounding import STEPS_PER_HOUR
from production.types import TIR_LOW, TIR_HIGH

EXP_ID = "2737"
TITLE = "Joint Multi-Setting Optimization (ISF + CR + Basal)"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/joint-optimization")

BG_FLOOR_CORRECTION = 150.0
MIN_DOSE = 0.3
MIN_CARBS = 5.0
CORRECTION_HORIZON = 24   # 2h in steps
MEAL_HORIZON = 48          # 4h in steps
FASTING_HORIZON = 12       # 1h in steps
MIN_SPACING = 24           # 2h independence

# Optimization grid — coarse for speed, then refine with Nelder-Mead
ISF_RANGE = np.arange(5, 120, 10)     # 12 points
CR_RANGE = np.arange(3, 30, 4)        # 7 points
BASAL_MULTS = np.arange(0.7, 1.4, 0.15)  # 5 points
MAX_EPISODES = 30  # cap per type for speed


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)]
    print(f"Loaded {len(grid)} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_episodes(grid: pd.DataFrame) -> Dict[str, List[dict]]:
    """Extract correction, meal, and fasting episodes per patient."""
    has_smb = "bolus_smb" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_cr = "scheduled_cr" in grid.columns
    has_basal = "scheduled_basal_rate" in grid.columns

    all_episodes = {}

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < MEAL_HORIZON + 10:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        carbs = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = float(pg["scheduled_isf"].median()) if has_isf else 50.0
        profile_cr = float(pg["scheduled_cr"].median()) if has_cr else 10.0
        profile_basal = float(pg["scheduled_basal_rate"].median()) if has_basal else 0.8
        controller = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            hours = np.zeros(len(pg))

        corrections = []
        meals = []
        fasting = []

        last_corr = -MIN_SPACING - 1
        last_meal = -MIN_SPACING - 1
        last_fast = -MIN_SPACING - 1

        for i in range(len(pg) - MEAL_HORIZON):
            bg0 = glucose[i]
            if np.isnan(bg0):
                continue

            carb_window_pre = float(np.nansum(carbs[max(0, i - 12):i]))
            carb_window_post = float(np.nansum(carbs[i:min(len(pg), i + 24)]))
            has_meal = carb_window_post > MIN_CARBS

            # CORRECTION episode: high BG, bolus, no carbs
            if (bg0 >= BG_FLOOR_CORRECTION and bolus[i] >= MIN_DOSE
                    and carb_window_pre < 1 and carb_window_post < 1
                    and i - last_corr >= MIN_SPACING):
                bg_end = glucose[i + CORRECTION_HORIZON]
                if not np.isnan(bg_end):
                    dose = float(bolus[i]) + float(smb[i]) if has_smb else float(bolus[i])
                    corrections.append({
                        "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                        "dose": dose, "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "actual_traj": glucose[i:i + CORRECTION_HORIZON + 1].tolist(),
                    })
                    last_corr = i

            # MEAL episode: carbs present
            elif has_meal and i - last_meal >= MIN_SPACING * 2:
                bg_end = glucose[min(i + MEAL_HORIZON, len(glucose) - 1)]
                if not np.isnan(bg_end):
                    total_carbs = float(carb_window_post)
                    meal_bolus = float(np.nansum(bolus[i:i + 6]))  # bolus within 30min
                    meals.append({
                        "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                        "carbs": total_carbs, "bolus": meal_bolus, "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "actual_traj": glucose[i:i + MEAL_HORIZON + 1].tolist(),
                    })
                    last_meal = i

            # FASTING episode: no bolus, no carbs, no SMB
            elif (bolus[i] < 0.01 and carb_window_pre < 1 and carb_window_post < 1
                  and (not has_smb or smb[i] < 0.01)
                  and i - last_fast >= MIN_SPACING):
                bg_end = glucose[i + FASTING_HORIZON]
                if not np.isnan(bg_end) and not np.isnan(bg0):
                    fasting.append({
                        "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                        "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "drift": float(bg_end - bg0),
                    })
                    last_fast = i

        if corrections or meals:
            all_episodes[pid] = {
                "corrections": corrections[:MAX_EPISODES],
                "meals": meals[:MAX_EPISODES],
                "fasting": fasting[:MAX_EPISODES],
                "profile_isf": profile_isf,
                "profile_cr": profile_cr,
                "profile_basal": profile_basal,
                "controller": controller,
            }

    return all_episodes


def evaluate_settings(isf: float, cr: float, basal_mult: float,
                       episodes: dict, episode_type: str = "all") -> dict:
    """Evaluate a settings triplet against a patient's episodes."""
    corr_maes = []
    meal_maes = []
    fast_maes = []
    tbr_steps = 0
    total_steps = 0

    profile_basal = episodes["profile_basal"]
    basal_rate = profile_basal * basal_mult

    # Correction episodes
    if episode_type in ("all", "correction"):
        for ep in episodes["corrections"]:
            actual = np.array(ep["actual_traj"])
            bolus_events = [InsulinEvent(0, ep["dose"], True)]
            settings = TherapySettings(isf=isf, cr=cr, basal_rate=basal_rate, dia_hours=5.0)
            try:
                result = forward_simulate(
                    initial_glucose=ep["bg0"], settings=settings,
                    duration_hours=2.0, start_hour=ep["hour"],
                    bolus_events=bolus_events, initial_iob=ep["iob"],
                    metabolic_basal_rate=profile_basal,
                    counter_reg_k=0.3, egp_enabled=True,
                )
                sim = np.array(result.glucose)
                n = min(len(sim), len(actual))
                valid = ~np.isnan(actual[:n])
                if valid.sum() < 5:
                    continue
                mae = float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid])))
                corr_maes.append(mae)
                tbr_steps += int(np.sum(sim[:n] < TIR_LOW))
                total_steps += n
            except Exception:
                pass

    # Meal episodes
    if episode_type in ("all", "meal"):
        for ep in episodes["meals"]:
            actual = np.array(ep["actual_traj"])
            bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
            carb_events = [CarbEvent(0, ep["carbs"])]
            settings = TherapySettings(isf=isf, cr=cr, basal_rate=basal_rate, dia_hours=5.0)
            try:
                result = forward_simulate(
                    initial_glucose=ep["bg0"], settings=settings,
                    duration_hours=4.0, start_hour=ep["hour"],
                    bolus_events=bolus_events, carb_events=carb_events,
                    initial_iob=ep["iob"],
                    metabolic_basal_rate=profile_basal,
                    counter_reg_k=0.3, egp_enabled=True,
                )
                sim = np.array(result.glucose)
                n = min(len(sim), len(actual))
                valid = ~np.isnan(actual[:n])
                if valid.sum() < 5:
                    continue
                mae = float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid])))
                meal_maes.append(mae)
                tbr_steps += int(np.sum(sim[:n] < TIR_LOW))
                total_steps += n
            except Exception:
                pass

    corr_mae = float(np.mean(corr_maes)) if corr_maes else 999.0
    meal_mae = float(np.mean(meal_maes)) if meal_maes else 999.0

    # Combined MAE: weight corrections and meals equally
    n_corr = len(corr_maes)
    n_meal = len(meal_maes)
    if n_corr + n_meal > 0:
        combined_mae = (corr_mae * n_corr + meal_mae * n_meal) / (n_corr + n_meal)
    else:
        combined_mae = 999.0

    tbr = tbr_steps / max(total_steps, 1)

    return {
        "combined_mae": combined_mae,
        "correction_mae": corr_mae,
        "meal_mae": meal_mae,
        "n_corrections": n_corr,
        "n_meals": n_meal,
        "tbr": tbr,
    }


def optimize_patient(episodes: dict) -> dict:
    """Find optimal (ISF, CR, basal_mult) for a patient via grid search."""
    profile_isf = episodes["profile_isf"]
    profile_cr = episodes["profile_cr"]

    # Phase 1: Coarse grid search
    best = {"mae": 999.0, "isf": profile_isf, "cr": profile_cr, "basal_mult": 1.0}

    for isf in ISF_RANGE:
        for cr in CR_RANGE:
            result = evaluate_settings(isf, cr, 1.0, episodes)
            if result["combined_mae"] < best["mae"]:
                best = {"mae": result["combined_mae"], "isf": isf, "cr": cr,
                        "basal_mult": 1.0, **result}

    # Phase 2: Refine with Nelder-Mead from best grid point
    def objective(params):
        isf, cr, bm = params
        if isf < 2 or cr < 1 or bm < 0.3 or bm > 2.0:
            return 999.0
        r = evaluate_settings(isf, cr, bm, episodes)
        return r["combined_mae"]

    try:
        nm_result = optimize.minimize(
            objective, [best["isf"], best["cr"], best["basal_mult"]],
            method="Nelder-Mead",
            options={"maxiter": 40, "xatol": 1.0, "fatol": 1.0},
        )
        if nm_result.fun < best["mae"]:
            isf_nm, cr_nm, bm_nm = nm_result.x
            result = evaluate_settings(isf_nm, cr_nm, bm_nm, episodes)
            best.update({"mae": result["combined_mae"],
                         "isf": round(isf_nm, 1), "cr": round(cr_nm, 1),
                         "basal_mult": round(bm_nm, 2), **result})
    except Exception:
        pass

    # Also evaluate profile settings for comparison
    profile_result = evaluate_settings(profile_isf, profile_cr, 1.0, episodes)

    # Evaluate independent ISF (from EXP-2720-style: correction-only)
    indep_best = {"mae": 999.0, "isf": profile_isf}
    for isf in ISF_RANGE:
        result = evaluate_settings(isf, profile_cr, 1.0, episodes, episode_type="correction")
        if result["correction_mae"] < indep_best["mae"]:
            indep_best = {"mae": result["correction_mae"], "isf": isf}

    return {
        "joint_isf": best["isf"],
        "joint_cr": best["cr"],
        "joint_basal_mult": best["basal_mult"],
        "joint_mae": best["mae"],
        "joint_corr_mae": best.get("correction_mae", 999),
        "joint_meal_mae": best.get("meal_mae", 999),
        "joint_tbr": best.get("tbr", 0),
        "profile_mae": profile_result["combined_mae"],
        "profile_corr_mae": profile_result["correction_mae"],
        "profile_meal_mae": profile_result["meal_mae"],
        "profile_tbr": profile_result["tbr"],
        "indep_isf": indep_best["isf"],
        "profile_isf": profile_isf,
        "profile_cr": profile_cr,
        "n_corrections": best.get("n_corrections", 0),
        "n_meals": best.get("n_meals", 0),
    }


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()
    episodes = extract_episodes(grid)
    print(f"Extracted episodes for {len(episodes)} patients")

    for pid, ep in episodes.items():
        print(f"  {str(pid)[:12]:<14} corr={len(ep['corrections']):>3}  "
              f"meal={len(ep['meals']):>3}  fast={len(ep['fasting']):>3}")

    # ── Optimize per patient ─────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  JOINT OPTIMIZATION")
    print(f"{'=' * 60}")

    results = []
    for pid, ep in episodes.items():
        if len(ep["corrections"]) < 5 and len(ep["meals"]) < 3:
            print(f"  {str(pid)[:12]}: skipped (too few episodes)")
            continue

        print(f"  Optimizing {str(pid)[:12]}...", end=" ", flush=True)
        opt = optimize_patient(ep)
        opt["patient_id"] = pid
        opt["controller"] = ep["controller"]
        results.append(opt)

        improvement = (opt["profile_mae"] - opt["joint_mae"]) / max(opt["profile_mae"], 1) * 100
        print(f"ISF {opt['profile_isf']:.0f}→{opt['joint_isf']:.0f}, "
              f"CR {opt['profile_cr']:.0f}→{opt['joint_cr']:.0f}, "
              f"basal ×{opt['joint_basal_mult']:.1f}, "
              f"MAE {opt['profile_mae']:.0f}→{opt['joint_mae']:.0f} "
              f"({improvement:+.0f}%)")

    df = pd.DataFrame(results)
    if len(df) == 0:
        print("No patients optimized!")
        return {}, {}

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 60}")

    print(f"\n  {'Patient':<12} {'ProfISF':>7} {'JntISF':>7} {'IndISF':>7} "
          f"{'ProfCR':>6} {'JntCR':>6} {'BslMlt':>6} "
          f"{'ProfMAE':>8} {'JntMAE':>7} {'Impr':>6}")
    print(f"  {'-'*80}")

    for _, r in df.sort_values("joint_mae").iterrows():
        impr = (r["profile_mae"] - r["joint_mae"]) / max(r["profile_mae"], 1) * 100
        print(f"  {str(r['patient_id'])[:10]:<12} "
              f"{r['profile_isf']:>7.0f} {r['joint_isf']:>7.0f} {r['indep_isf']:>7.0f} "
              f"{r['profile_cr']:>6.0f} {r['joint_cr']:>6.0f} {r['joint_basal_mult']:>6.1f} "
              f"{r['profile_mae']:>8.1f} {r['joint_mae']:>7.1f} {impr:>+5.0f}%")

    # Aggregates
    n_improved = (df["joint_mae"] < df["profile_mae"]).sum()
    n_total = len(df)
    med_profile_mae = df["profile_mae"].median()
    med_joint_mae = df["joint_mae"].median()

    print(f"\n  Patients improved: {n_improved}/{n_total} ({n_improved/n_total*100:.0f}%)")
    print(f"  Median MAE: profile={med_profile_mae:.1f} → joint={med_joint_mae:.1f} "
          f"({(med_profile_mae - med_joint_mae)/max(med_profile_mae,1)*100:+.0f}%)")

    # ISF comparison: joint vs independent
    isf_diff = np.abs(df["joint_isf"] - df["indep_isf"]) / np.maximum(df["indep_isf"], 1)
    cr_diff = np.abs(df["joint_cr"] - df["profile_cr"]) / np.maximum(df["profile_cr"], 1)
    print(f"\n  ISF: joint vs independent — median |diff| = {isf_diff.median()*100:.0f}%")
    print(f"  CR: joint vs profile — median |diff| = {cr_diff.median()*100:.0f}%")

    # Safety: TBR comparison
    tbr_worse = (df["joint_tbr"] > df["profile_tbr"] + 0.01).sum()
    print(f"\n  TBR worsened: {tbr_worse}/{n_total} patients")
    print(f"  Median TBR: profile={df['profile_tbr'].median():.3f} → joint={df['joint_tbr'].median():.3f}")

    # ── Hypotheses ───────────────────────────────────────────────
    h1_pass = n_improved > n_total * 0.6
    h2_pass = isf_diff.median() < 0.3
    h3_pass = cr_diff.median() < 0.3
    h4_indep_mae = []
    for _, r in df.iterrows():
        pid = r["patient_id"]
        ep = episodes[pid]
        indep_result = evaluate_settings(r["indep_isf"], r["profile_cr"], 1.0, ep)
        h4_indep_mae.append(indep_result["combined_mae"])
    df["indep_combined_mae"] = h4_indep_mae
    h4_pass = (df["joint_mae"] < df["indep_combined_mae"]).sum() > n_total * 0.4
    h5_pass = tbr_worse < n_total * 0.2

    hypotheses = {
        "H1_joint_beats_profile_60pct": bool(h1_pass),
        "H2_isf_diff_lt_30pct": bool(h2_pass),
        "H3_cr_diff_lt_30pct": bool(h3_pass),
        "H4_joint_beats_independent_40pct": bool(h4_pass),
        "H5_safety_maintained": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"{n_improved}/{n_total} improved ({n_improved/max(n_total,1)*100:.0f}%). "
               f"MAE: profile {med_profile_mae:.0f} → joint {med_joint_mae:.0f}")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # ── Save ─────────────────────────────────────────────────────
    out_path = RESULTS_DIR / f"exp-{EXP_ID}_joint_optimization.json"

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
            "per_patient": df.to_dict(orient="records"),
            "summary": summary,
            "aggregates": {
                "n_improved": int(n_improved),
                "n_total": int(n_total),
                "median_profile_mae": float(med_profile_mae),
                "median_joint_mae": float(med_joint_mae),
                "median_isf_diff_pct": float(isf_diff.median() * 100),
                "median_cr_diff_pct": float(cr_diff.median() * 100),
            },
        }), f, indent=2)
    print(f"Saved: {out_path}")

    # Dashboard
    create_dashboard(df, hypotheses, episodes)

    return hypotheses, df


def create_dashboard(df, hypotheses, episodes):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 14))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: Profile vs Joint MAE per patient
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(df["profile_mae"], df["joint_mae"], color="steelblue", alpha=0.7, s=60)
    lim = max(df["profile_mae"].max(), df["joint_mae"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax1.set_xlabel("Profile MAE (mg/dL)")
    ax1.set_ylabel("Joint-Optimized MAE (mg/dL)")
    ax1.set_title("Profile vs Joint MAE")
    ax1.legend(fontsize=8)

    # Panel 2: Profile ISF vs Joint ISF
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(df["profile_isf"], df["joint_isf"], color="steelblue", alpha=0.7, s=60)
    lim = max(df["profile_isf"].max(), df["joint_isf"].max()) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax2.set_xlabel("Profile ISF")
    ax2.set_ylabel("Joint-Optimized ISF")
    ax2.set_title("Profile vs Joint ISF")
    ax2.legend(fontsize=8)

    # Panel 3: Profile CR vs Joint CR
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(df["profile_cr"], df["joint_cr"], color="steelblue", alpha=0.7, s=60)
    lim = max(df["profile_cr"].max(), df["joint_cr"].max()) * 1.1
    ax3.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax3.set_xlabel("Profile CR")
    ax3.set_ylabel("Joint-Optimized CR")
    ax3.set_title("Profile vs Joint CR")
    ax3.legend(fontsize=8)

    # Panel 4: MAE improvement per patient (bar)
    ax4 = fig.add_subplot(gs[1, 0])
    improvement = ((df["profile_mae"] - df["joint_mae"]) / df["profile_mae"].clip(lower=1) * 100)
    colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in improvement]
    ax4.bar(range(len(df)), improvement.values, color=colors, alpha=0.7)
    ax4.axhline(0, color="black", linewidth=0.5)
    ax4.set_xlabel("Patient")
    ax4.set_ylabel("MAE Improvement (%)")
    ax4.set_title("Per-Patient MAE Improvement")

    # Panel 5: Joint vs Independent ISF
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.scatter(df["indep_isf"], df["joint_isf"], color="steelblue", alpha=0.7, s=60)
    lim = max(df["indep_isf"].max(), df["joint_isf"].max()) * 1.1
    ax5.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax5.set_xlabel("Independent ISF (correction-only)")
    ax5.set_ylabel("Joint-Optimized ISF")
    ax5.set_title("Independent vs Joint ISF")
    ax5.legend(fontsize=8)

    # Panel 6: Basal multiplier distribution
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.hist(df["joint_basal_mult"], bins=len(BASAL_MULTS), color="steelblue",
             edgecolor="white", alpha=0.8)
    ax6.axvline(1.0, color="red", linewidth=2, linestyle="--", label="No change")
    ax6.set_xlabel("Basal Multiplier")
    ax6.set_ylabel("Patients")
    ax6.set_title("Optimal Basal Adjustment")
    ax6.legend(fontsize=8)

    # Row 3: Summary
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis("off")
    n_improved = (df["joint_mae"] < df["profile_mae"]).sum()
    lines = [
        f"EXP-{EXP_ID}: {TITLE}", "",
        f"Patients: {len(df)} | Improved: {n_improved}/{len(df)} ({n_improved/len(df)*100:.0f}%)",
        f"Median MAE: profile={df['profile_mae'].median():.1f} → joint={df['joint_mae'].median():.1f}",
        f"Median ISF: profile={df['profile_isf'].median():.0f} → joint={df['joint_isf'].median():.0f} "
        f"(indep={df['indep_isf'].median():.0f})",
        f"Median CR: profile={df['profile_cr'].median():.0f} → joint={df['joint_cr'].median():.0f}",
        f"Median Basal mult: {df['joint_basal_mult'].median():.1f}",
        "",
        "Hypotheses:",
    ]
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")

    ax7.text(0.05, 0.95, "\n".join(lines), transform=ax7.transAxes,
             fontsize=10, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VIZ_DIR / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
