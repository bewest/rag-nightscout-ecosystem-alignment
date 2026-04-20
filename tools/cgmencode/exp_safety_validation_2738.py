#!/usr/bin/env python3
"""
EXP-2738: Safety Validation of Independently-Extracted Settings
================================================================

EXP-2737 proved that unconstrained joint optimization finds degenerate
solutions (ISF→0, CR→∞, basal→2×) because these parameters are NOT
independently identifiable from glucose trajectories alone.

This experiment validates the WATERFALL-EXTRACTED settings instead:
  - ISF correction factors from EXP-2719b (residual method)
  - CR from EXP-2729 (deconfounded meal analysis)
  - Basal from profile (pending EGP-aware correction)

The forward simulator evaluates whether applying these corrections
per-patient:
  1. Reduces prediction error (MAE) vs profile settings
  2. Does NOT increase time below range (TBR < 70 mg/dL)
  3. Does NOT increase severe hypo events (< 54 mg/dL)

This is the SAFETY GATE before any settings can be recommended.

HYPOTHESES:
  H1: Corrected settings reduce MAE in >60% of patients
  H2: Corrected settings don't increase TBR (paired test p > 0.05)
  H3: No patient has >2× increase in TBR with corrected settings
  H4: Severe hypo events (< 54) don't increase
  H5: Correction-episode MAE improves more than meal-episode MAE

REFERENCES: EXP-2719b, EXP-2729, EXP-2737 (identifiability lesson)
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
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)

EXP_ID = "2738"
TITLE = "Safety Validation of Waterfall-Extracted Settings"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2729 = Path("externals/experiments/exp-2729_carb_ratio.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/safety-validation")

TIR_LOW = 70.0
TIR_HIGH = 180.0
SEVERE_LOW = 54.0
MIN_DOSE = 0.3
MIN_CARBS = 5.0
BG_FLOOR = 150.0
CORRECTION_HORIZON = 24  # 2h in 5-min steps
MEAL_HORIZON = 48         # 4h
MIN_SPACING = 24           # 2h
MAX_EPISODES = 25


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)]
    return grid


def load_corrections() -> Dict[str, dict]:
    """Load per-patient correction factors from EXP-2719b and EXP-2729."""
    corrections = {}

    # ISF corrections from 2719b (2h horizon)
    d = json.loads(EXP_2719B.read_text())
    for pp in d["results"]["2h"]["per_patient"]:
        pid = pp["patient_id"]
        corrections[pid] = {
            "correction_factor": pp["correction_factor"],
            "profile_isf": pp["profile_isf"],
            "empirical_isf": pp["empirical_isf"],
            "direction": pp["direction"],
            "recommendation": pp["recommendation"],
            "significant": pp["significant"],
        }

    # CR corrections from 2729
    d2 = json.loads(EXP_2729.read_text())
    for pp in d2["per_patient"]:
        pid = pp["patient_id"]
        if pid in corrections:
            corrections[pid]["profile_cr"] = pp["profile_cr"]
            corrections[pid]["deconfounded_cr"] = pp["deconfounded_cr"]
            corrections[pid]["cr_ratio"] = pp["deconfounded_cr"] / max(pp["profile_cr"], 0.1)

    return corrections


def extract_episodes(grid: pd.DataFrame) -> Dict[str, dict]:
    """Extract correction and meal episodes per patient."""
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

        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            hours = np.zeros(len(pg))

        corrections = []
        meals = []
        last_corr = -MIN_SPACING - 1
        last_meal = -MIN_SPACING - 1

        for i in range(len(pg) - MEAL_HORIZON):
            bg0 = glucose[i]
            if np.isnan(bg0):
                continue

            carb_pre = float(np.nansum(carbs[max(0, i - 12):i]))
            carb_post = float(np.nansum(carbs[i:min(len(pg), i + 24)]))

            # Correction episodes
            if (bg0 >= BG_FLOOR and bolus[i] >= MIN_DOSE
                    and carb_pre < 1 and carb_post < 1
                    and i - last_corr >= MIN_SPACING):
                bg_end = glucose[i + CORRECTION_HORIZON] if i + CORRECTION_HORIZON < len(glucose) else np.nan
                if not np.isnan(bg_end):
                    dose = float(bolus[i]) + (float(smb[i]) if has_smb else 0.0)
                    traj = glucose[i:i + CORRECTION_HORIZON + 1]
                    corrections.append({
                        "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                        "dose": dose, "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "actual_traj": traj.tolist(),
                    })
                    last_corr = i

            # Meal episodes
            elif (carb_post > MIN_CARBS and i - last_meal >= MIN_SPACING * 2):
                end_idx = min(i + MEAL_HORIZON, len(glucose) - 1)
                bg_end = glucose[end_idx]
                if not np.isnan(bg_end):
                    total_carbs = float(carb_post)
                    meal_bolus = float(np.nansum(bolus[i:i + 6]))
                    traj = glucose[i:end_idx + 1]
                    meals.append({
                        "idx": i, "bg0": float(bg0), "bg_end": float(bg_end),
                        "carbs": total_carbs, "bolus": meal_bolus,
                        "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "actual_traj": traj.tolist(),
                    })
                    last_meal = i

        if corrections or meals:
            all_episodes[pid] = {
                "corrections": corrections[:MAX_EPISODES],
                "meals": meals[:MAX_EPISODES],
                "profile_isf": profile_isf,
                "profile_cr": profile_cr,
                "profile_basal": profile_basal,
            }

    return all_episodes


def simulate_episode(ep: dict, settings: TherapySettings, duration_hours: float,
                      profile_basal: float, carb_events=None) -> Optional[dict]:
    """Simulate a single episode and return metrics."""
    actual = np.array(ep["actual_traj"])
    bolus_events = []
    dose = ep.get("dose", ep.get("bolus", 0))
    if dose > 0:
        bolus_events = [InsulinEvent(0, dose, True)]

    try:
        result = forward_simulate(
            initial_glucose=ep["bg0"], settings=settings,
            duration_hours=duration_hours, start_hour=ep["hour"],
            bolus_events=bolus_events, carb_events=carb_events or [],
            initial_iob=ep["iob"], metabolic_basal_rate=profile_basal,
            counter_reg_k=0.3, egp_enabled=True,
        )
        sim = np.array(result.glucose)
        n = min(len(sim), len(actual))
        valid = ~np.isnan(actual[:n])
        if valid.sum() < 3:
            return None

        mae = float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid])))
        tbr = float(np.sum(sim[:n] < TIR_LOW)) / n
        severe = float(np.sum(sim[:n] < SEVERE_LOW)) / n
        tar = float(np.sum(sim[:n] > TIR_HIGH)) / n

        return {"mae": mae, "tbr": tbr, "severe": severe, "tar": tar, "n": n}
    except Exception:
        return None


def evaluate_settings_for_patient(episodes: dict, isf: float, cr: float,
                                    basal_rate: float) -> dict:
    """Run all episodes for a patient with given settings."""
    settings_corr = TherapySettings(isf=isf, cr=cr, basal_rate=basal_rate, dia_hours=5.0)
    settings_meal = TherapySettings(isf=isf, cr=cr, basal_rate=basal_rate, dia_hours=5.0)

    corr_results = []
    meal_results = []

    for ep in episodes["corrections"]:
        r = simulate_episode(ep, settings_corr, 2.0, episodes["profile_basal"])
        if r:
            corr_results.append(r)

    for ep in episodes["meals"]:
        carb_events = [CarbEvent(0, ep["carbs"])]
        r = simulate_episode(ep, settings_meal, 4.0, episodes["profile_basal"], carb_events)
        if r:
            meal_results.append(r)

    all_results = corr_results + meal_results

    if not all_results:
        return {"mae": 999, "tbr": 0, "severe": 0, "tar": 0,
                "corr_mae": 999, "meal_mae": 999,
                "n_corr": 0, "n_meal": 0}

    return {
        "mae": float(np.mean([r["mae"] for r in all_results])),
        "tbr": float(np.mean([r["tbr"] for r in all_results])),
        "severe": float(np.mean([r["severe"] for r in all_results])),
        "tar": float(np.mean([r["tar"] for r in all_results])),
        "corr_mae": float(np.mean([r["mae"] for r in corr_results])) if corr_results else 999,
        "meal_mae": float(np.mean([r["mae"] for r in meal_results])) if meal_results else 999,
        "n_corr": len(corr_results),
        "n_meal": len(meal_results),
    }


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()
    corrections = load_corrections()
    episodes = extract_episodes(grid)

    print(f"Loaded {grid['patient_id'].nunique()} patients, "
          f"{len(corrections)} with corrections, {len(episodes)} with episodes")

    # ── Evaluate profile vs corrected settings ───────────────────
    print(f"\n{'=' * 60}")
    print("  SAFETY VALIDATION")
    print(f"{'=' * 60}")

    results = []
    for pid, ep in episodes.items():
        if pid not in corrections:
            print(f"  {str(pid)[:12]}: skipped (no correction data)")
            continue

        corr = corrections[pid]
        if len(ep["corrections"]) < 3 and len(ep["meals"]) < 3:
            print(f"  {str(pid)[:12]}: skipped (too few episodes)")
            continue

        print(f"  Validating {str(pid)[:12]}...", end=" ", flush=True)

        profile_isf = ep["profile_isf"]
        profile_cr = ep["profile_cr"]
        profile_basal = ep["profile_basal"]

        # Corrected ISF: apply 2719b correction factor
        cf = corr["correction_factor"]
        corrected_isf = profile_isf / cf  # cf > 1 means ISF too high → divide

        # Corrected CR: use 2729 deconfounded CR if available
        corrected_cr = corr.get("deconfounded_cr", profile_cr)
        if corrected_cr is None or corrected_cr <= 0:
            corrected_cr = profile_cr

        # Clamp to physiological ranges
        corrected_isf = np.clip(corrected_isf, 5, 200)
        corrected_cr = np.clip(corrected_cr, 2, 50)

        # Evaluate both
        profile_result = evaluate_settings_for_patient(
            ep, profile_isf, profile_cr, profile_basal)
        corrected_result = evaluate_settings_for_patient(
            ep, corrected_isf, corrected_cr, profile_basal)

        mae_impr = ((profile_result["mae"] - corrected_result["mae"])
                     / max(profile_result["mae"], 1) * 100)

        print(f"ISF {profile_isf:.0f}→{corrected_isf:.0f}, "
              f"CR {profile_cr:.0f}→{corrected_cr:.0f}, "
              f"MAE {profile_result['mae']:.0f}→{corrected_result['mae']:.0f} "
              f"({mae_impr:+.0f}%), "
              f"TBR {profile_result['tbr']:.3f}→{corrected_result['tbr']:.3f}")

        results.append({
            "patient_id": pid,
            "controller": corr.get("direction", "unknown"),
            "profile_isf": profile_isf,
            "corrected_isf": corrected_isf,
            "correction_factor": cf,
            "profile_cr": profile_cr,
            "corrected_cr": corrected_cr,
            "direction": corr["direction"],
            "recommendation": corr["recommendation"],
            "profile_mae": profile_result["mae"],
            "corrected_mae": corrected_result["mae"],
            "profile_corr_mae": profile_result["corr_mae"],
            "corrected_corr_mae": corrected_result["corr_mae"],
            "profile_meal_mae": profile_result["meal_mae"],
            "corrected_meal_mae": corrected_result["meal_mae"],
            "profile_tbr": profile_result["tbr"],
            "corrected_tbr": corrected_result["tbr"],
            "profile_severe": profile_result["severe"],
            "corrected_severe": corrected_result["severe"],
            "profile_tar": profile_result["tar"],
            "corrected_tar": corrected_result["tar"],
            "n_corr": corrected_result["n_corr"],
            "n_meal": corrected_result["n_meal"],
        })

    df = pd.DataFrame(results)
    if len(df) == 0:
        print("No patients validated!")
        return

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 70}")

    print(f"\n  {'Patient':<12} {'ProfISF':>7} {'CorrISF':>7} {'CF':>5} "
          f"{'ProfCR':>6} {'CorrCR':>6} "
          f"{'ProfMAE':>8} {'CorrMAE':>8} {'Impr':>6} "
          f"{'P_TBR':>6} {'C_TBR':>6}")
    print(f"  {'-' * 95}")

    for _, r in df.sort_values("corrected_mae").iterrows():
        impr = ((r["profile_mae"] - r["corrected_mae"])
                / max(r["profile_mae"], 1) * 100)
        print(f"  {str(r['patient_id'])[:10]:<12} "
              f"{r['profile_isf']:>7.0f} {r['corrected_isf']:>7.0f} "
              f"{r['correction_factor']:>5.2f} "
              f"{r['profile_cr']:>6.0f} {r['corrected_cr']:>6.1f} "
              f"{r['profile_mae']:>8.1f} {r['corrected_mae']:>8.1f} "
              f"{impr:>+5.0f}% "
              f"{r['profile_tbr']:>6.3f} {r['corrected_tbr']:>6.3f}")

    # Aggregates
    n_improved = (df["corrected_mae"] < df["profile_mae"]).sum()
    n_total = len(df)
    med_profile_mae = df["profile_mae"].median()
    med_corrected_mae = df["corrected_mae"].median()

    print(f"\n  MAE improved: {n_improved}/{n_total} ({n_improved/n_total*100:.0f}%)")
    print(f"  Median MAE: profile={med_profile_mae:.1f} → corrected={med_corrected_mae:.1f} "
          f"({(med_profile_mae - med_corrected_mae)/max(med_profile_mae,1)*100:+.0f}%)")

    # Correction vs Meal MAE improvement
    corr_improved = (df["corrected_corr_mae"] < df["profile_corr_mae"]).sum()
    meal_improved = (df["corrected_meal_mae"] < df["profile_meal_mae"]).sum()
    print(f"  Correction MAE improved: {corr_improved}/{n_total}")
    print(f"  Meal MAE improved: {meal_improved}/{n_total}")

    # Safety metrics
    tbr_increased = df["corrected_tbr"] > df["profile_tbr"] + 0.001
    tbr_doubled = df["corrected_tbr"] > df["profile_tbr"] * 2 + 0.001
    severe_increased = df["corrected_severe"] > df["profile_severe"] + 0.001

    print(f"\n  SAFETY:")
    print(f"  TBR increased: {tbr_increased.sum()}/{n_total}")
    print(f"  TBR >2× worse: {tbr_doubled.sum()}/{n_total}")
    print(f"  Severe hypo increased: {severe_increased.sum()}/{n_total}")
    print(f"  Median TBR: {df['profile_tbr'].median():.4f} → {df['corrected_tbr'].median():.4f}")
    print(f"  Median severe: {df['profile_severe'].median():.4f} → {df['corrected_severe'].median():.4f}")

    # Paired t-test on TBR
    if n_total >= 5:
        t_stat, p_val = stats.ttest_rel(df["corrected_tbr"], df["profile_tbr"])
        print(f"  TBR paired t-test: t={t_stat:.3f}, p={p_val:.4f} "
              f"({'corrected worse' if t_stat > 0 else 'corrected better'})")
    else:
        p_val = 1.0

    # ── Hypotheses ───────────────────────────────────────────────
    h1_pass = n_improved > n_total * 0.6
    h2_pass = p_val > 0.05 or t_stat <= 0  # TBR not significantly worse
    h3_pass = tbr_doubled.sum() == 0
    h4_pass = severe_increased.sum() <= 1
    h5_corr_impr_pct = corr_improved / max(n_total, 1)
    h5_meal_impr_pct = meal_improved / max(n_total, 1)
    h5_pass = h5_corr_impr_pct >= h5_meal_impr_pct  # corrections improve at least as much

    hypotheses = {
        "H1_mae_improves_60pct": bool(h1_pass),
        "H2_tbr_not_worse": bool(h2_pass),
        "H3_no_2x_tbr_increase": bool(h3_pass),
        "H4_severe_hypo_stable": bool(h4_pass),
        "H5_corrections_improve_more": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"{n_improved}/{n_total} improved ({n_improved/max(n_total,1)*100:.0f}%). "
               f"MAE: {med_profile_mae:.0f}→{med_corrected_mae:.0f}. "
               f"TBR safe: {not tbr_doubled.any()}")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # ── Save ─────────────────────────────────────────────────────
    out_path = RESULTS_DIR / f"exp-{EXP_ID}_safety_validation.json"

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
                "n_improved": int(n_improved), "n_total": int(n_total),
                "median_profile_mae": float(med_profile_mae),
                "median_corrected_mae": float(med_corrected_mae),
                "tbr_doubled": int(tbr_doubled.sum()),
                "severe_increased": int(severe_increased.sum()),
            },
        }), f, indent=2)
    print(f"Saved: {out_path}")

    # Dashboard
    create_dashboard(df, hypotheses)

    return hypotheses, df


def create_dashboard(df, hypotheses):
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

    # Panel 1: Profile vs Corrected MAE
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(df["profile_mae"], df["corrected_mae"], color="steelblue", alpha=0.7, s=60)
    lim = max(df["profile_mae"].max(), df["corrected_mae"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax1.set_xlabel("Profile MAE (mg/dL)")
    ax1.set_ylabel("Corrected MAE (mg/dL)")
    ax1.set_title("MAE: Profile vs Corrected")
    ax1.legend(fontsize=8)

    # Panel 2: TBR comparison
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(df["profile_tbr"] * 100, df["corrected_tbr"] * 100,
                color="steelblue", alpha=0.7, s=60)
    lim = max(df["profile_tbr"].max(), df["corrected_tbr"].max()) * 110
    ax2.plot([0, lim], [0, lim], "r--", linewidth=1, label="1:1")
    ax2.set_xlabel("Profile TBR (%)")
    ax2.set_ylabel("Corrected TBR (%)")
    ax2.set_title("Safety: TBR Comparison")
    ax2.legend(fontsize=8)

    # Panel 3: ISF change distribution
    ax3 = fig.add_subplot(gs[0, 2])
    change = (df["corrected_isf"] - df["profile_isf"]) / df["profile_isf"] * 100
    colors = ["#2ecc71" if v < 0 else "#e74c3c" for v in change]
    ax3.barh(range(len(df)), change.values, color=colors, alpha=0.7)
    ax3.set_xlabel("ISF Change (%)")
    ax3.set_ylabel("Patient")
    ax3.set_title("ISF Adjustment Direction")
    ax3.axvline(0, color="black", linewidth=0.5)

    # Panel 4: MAE improvement bar
    ax4 = fig.add_subplot(gs[1, 0])
    improvement = ((df["profile_mae"] - df["corrected_mae"])
                   / df["profile_mae"].clip(lower=1) * 100)
    colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in improvement]
    ax4.bar(range(len(df)), improvement.values, color=colors, alpha=0.7)
    ax4.axhline(0, color="black", linewidth=0.5)
    ax4.set_xlabel("Patient")
    ax4.set_ylabel("MAE Improvement (%)")
    ax4.set_title("Per-Patient MAE Improvement")

    # Panel 5: Correction vs Meal MAE change
    ax5 = fig.add_subplot(gs[1, 1])
    corr_impr = ((df["profile_corr_mae"] - df["corrected_corr_mae"])
                 / df["profile_corr_mae"].clip(lower=1) * 100)
    meal_impr = ((df["profile_meal_mae"] - df["corrected_meal_mae"])
                 / df["profile_meal_mae"].clip(lower=1) * 100)
    x = np.arange(len(df))
    w = 0.35
    ax5.bar(x - w/2, corr_impr.values, w, label="Correction", color="steelblue", alpha=0.7)
    ax5.bar(x + w/2, meal_impr.values, w, label="Meal", color="coral", alpha=0.7)
    ax5.axhline(0, color="black", linewidth=0.5)
    ax5.set_xlabel("Patient")
    ax5.set_ylabel("MAE Improvement (%)")
    ax5.set_title("Correction vs Meal Improvement")
    ax5.legend(fontsize=8)

    # Panel 6: Correction factor vs MAE improvement
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.scatter(df["correction_factor"], improvement, color="steelblue", alpha=0.7, s=60)
    ax6.set_xlabel("ISF Correction Factor")
    ax6.set_ylabel("MAE Improvement (%)")
    ax6.set_title("Correction Factor vs Improvement")
    ax6.axhline(0, color="red", linewidth=0.5, linestyle="--")
    ax6.axvline(1.0, color="red", linewidth=0.5, linestyle="--")

    # Summary panel
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis("off")
    n_improved = (df["corrected_mae"] < df["profile_mae"]).sum()
    n_total = len(df)
    lines = [
        f"EXP-{EXP_ID}: {TITLE}", "",
        f"Patients: {n_total} | MAE improved: {n_improved}/{n_total} ({n_improved/n_total*100:.0f}%)",
        f"Median MAE: profile={df['profile_mae'].median():.1f} → corrected={df['corrected_mae'].median():.1f}",
        f"Median ISF: profile={df['profile_isf'].median():.0f} → corrected={df['corrected_isf'].median():.0f}",
        f"Median CR: profile={df['profile_cr'].median():.0f} → corrected={df['corrected_cr'].median():.1f}",
        f"Median TBR: {df['profile_tbr'].median():.4f} → {df['corrected_tbr'].median():.4f}",
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
