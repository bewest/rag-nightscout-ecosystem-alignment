#!/usr/bin/env python3
"""
EXP-2739: ISF-Only Safety Validation (No CR Changes)
=====================================================

EXP-2738 showed that ISF corrections improve correction-episode MAE
(9/22 patients) but CR corrections worsen meals (20/22 patients).

This experiment validates ISF corrections ALONE, keeping profile CR.
This isolates the ISF improvement signal from the CR degradation.

HYPOTHESES:
  H1: ISF-only corrections improve overall MAE in >40% of patients
  H2: Correction-episode MAE improves in >50% of patients
  H3: Meal-episode MAE doesn't worsen more than 10% median
  H4: TBR doesn't increase (paired test p > 0.05)
  H5: No patient has >2× TBR increase

REFERENCES: EXP-2719b, EXP-2738 (full corrections too aggressive)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)

EXP_ID = "2739"
TITLE = "ISF-Only Safety Validation"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/isf-only-validation")

TIR_LOW = 70.0
SEVERE_LOW = 54.0
BG_FLOOR = 150.0
CORRECTION_HORIZON = 24
MEAL_HORIZON = 48
MIN_SPACING = 24
MAX_EPISODES = 25
MIN_DOSE = 0.3
MIN_CARBS = 5.0


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    return grid[grid["patient_id"].isin(qualified)]


def load_isf_corrections() -> Dict[str, dict]:
    d = json.loads(EXP_2719B.read_text())
    corrections = {}
    for pp in d["results"]["2h"]["per_patient"]:
        corrections[pp["patient_id"]] = {
            "correction_factor": pp["correction_factor"],
            "profile_isf": pp["profile_isf"],
            "empirical_isf": pp["empirical_isf"],
            "direction": pp["direction"],
            "significant": pp["significant"],
        }
    return corrections


def extract_episodes(grid):
    has_smb = "bolus_smb" in grid.columns
    has_iob = "iob" in grid.columns
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
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50.0
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10.0
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        try:
            hours = (pd.to_datetime(pg["time"]).dt.hour + pd.to_datetime(pg["time"]).dt.minute / 60.0).values
        except Exception:
            hours = np.zeros(len(pg))

        corrections, meals = [], []
        last_corr, last_meal = -MIN_SPACING - 1, -MIN_SPACING - 1

        for i in range(len(pg) - MEAL_HORIZON):
            bg0 = glucose[i]
            if np.isnan(bg0):
                continue
            carb_pre = float(np.nansum(carbs[max(0, i-12):i]))
            carb_post = float(np.nansum(carbs[i:min(len(pg), i+24)]))

            if (bg0 >= BG_FLOOR and bolus[i] >= MIN_DOSE
                    and carb_pre < 1 and carb_post < 1
                    and i - last_corr >= MIN_SPACING):
                if i + CORRECTION_HORIZON < len(glucose):
                    bg_end = glucose[i + CORRECTION_HORIZON]
                    if not np.isnan(bg_end):
                        dose = float(bolus[i]) + (float(smb[i]) if has_smb else 0)
                        corrections.append({
                            "bg0": float(bg0), "bg_end": float(bg_end),
                            "dose": dose, "hour": float(hours[i]),
                            "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                            "actual_traj": glucose[i:i+CORRECTION_HORIZON+1].tolist(),
                        })
                        last_corr = i

            elif carb_post > MIN_CARBS and i - last_meal >= MIN_SPACING * 2:
                end_idx = min(i + MEAL_HORIZON, len(glucose) - 1)
                bg_end = glucose[end_idx]
                if not np.isnan(bg_end):
                    meals.append({
                        "bg0": float(bg0), "bg_end": float(bg_end),
                        "carbs": float(carb_post),
                        "bolus": float(np.nansum(bolus[i:i+6])),
                        "hour": float(hours[i]),
                        "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                        "actual_traj": glucose[i:end_idx+1].tolist(),
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


def sim_episode(ep, settings, dur, basal, carb_events=None):
    actual = np.array(ep["actual_traj"])
    dose = ep.get("dose", ep.get("bolus", 0))
    bolus_events = [InsulinEvent(0, dose, True)] if dose > 0 else []
    try:
        r = forward_simulate(
            initial_glucose=ep["bg0"], settings=settings,
            duration_hours=dur, start_hour=ep["hour"],
            bolus_events=bolus_events, carb_events=carb_events or [],
            initial_iob=ep["iob"], metabolic_basal_rate=basal,
            counter_reg_k=0.3, egp_enabled=True,
        )
        sim = np.array(r.glucose)
        n = min(len(sim), len(actual))
        valid = ~np.isnan(actual[:n])
        if valid.sum() < 3:
            return None
        return {
            "mae": float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid]))),
            "tbr": float(np.sum(sim[:n] < TIR_LOW)) / n,
            "severe": float(np.sum(sim[:n] < SEVERE_LOW)) / n,
        }
    except Exception:
        return None


def eval_patient(episodes, isf, cr):
    basal = episodes["profile_basal"]
    settings = TherapySettings(isf=isf, cr=cr, basal_rate=basal, dia_hours=5.0)

    corr_r, meal_r = [], []
    for ep in episodes["corrections"]:
        r = sim_episode(ep, settings, 2.0, basal)
        if r: corr_r.append(r)
    for ep in episodes["meals"]:
        carbs = [CarbEvent(0, ep["carbs"])]
        r = sim_episode(ep, settings, 4.0, basal, carbs)
        if r: meal_r.append(r)

    all_r = corr_r + meal_r
    if not all_r:
        return {"mae": 999, "tbr": 0, "severe": 0, "corr_mae": 999, "meal_mae": 999,
                "n_corr": 0, "n_meal": 0}
    return {
        "mae": np.mean([r["mae"] for r in all_r]),
        "tbr": np.mean([r["tbr"] for r in all_r]),
        "severe": np.mean([r["severe"] for r in all_r]),
        "corr_mae": np.mean([r["mae"] for r in corr_r]) if corr_r else 999,
        "meal_mae": np.mean([r["mae"] for r in meal_r]) if meal_r else 999,
        "n_corr": len(corr_r), "n_meal": len(meal_r),
    }


def main():
    print(f"{'='*70}\nEXP-{EXP_ID}: {TITLE}\n{'='*70}")

    grid = load_data()
    corrections = load_isf_corrections()
    episodes = extract_episodes(grid)
    print(f"Patients: {len(episodes)} with episodes, {len(corrections)} with ISF corrections")

    results = []
    for pid, ep in episodes.items():
        if pid not in corrections:
            continue
        if len(ep["corrections"]) < 3 and len(ep["meals"]) < 3:
            continue

        corr = corrections[pid]
        profile_isf = ep["profile_isf"]
        profile_cr = ep["profile_cr"]  # KEEP PROFILE CR

        cf = corr["correction_factor"]
        corrected_isf = np.clip(profile_isf / cf, 5, 200)

        print(f"  {str(pid)[:12]:<14}", end="", flush=True)

        prof = eval_patient(ep, profile_isf, profile_cr)
        corr_r = eval_patient(ep, corrected_isf, profile_cr)  # ISF only change

        impr = (prof["mae"] - corr_r["mae"]) / max(prof["mae"], 1) * 100
        print(f"ISF {profile_isf:.0f}→{corrected_isf:.0f} (CF={cf:.2f}), "
              f"MAE {prof['mae']:.0f}→{corr_r['mae']:.0f} ({impr:+.0f}%), "
              f"TBR {prof['tbr']:.3f}→{corr_r['tbr']:.3f}")

        results.append({
            "patient_id": pid,
            "profile_isf": profile_isf, "corrected_isf": corrected_isf,
            "correction_factor": cf, "direction": corr["direction"],
            "profile_cr": profile_cr,
            "profile_mae": prof["mae"], "corrected_mae": corr_r["mae"],
            "profile_corr_mae": prof["corr_mae"], "corrected_corr_mae": corr_r["corr_mae"],
            "profile_meal_mae": prof["meal_mae"], "corrected_meal_mae": corr_r["meal_mae"],
            "profile_tbr": prof["tbr"], "corrected_tbr": corr_r["tbr"],
            "profile_severe": prof["severe"], "corrected_severe": corr_r["severe"],
            "n_corr": corr_r["n_corr"], "n_meal": corr_r["n_meal"],
        })

    df = pd.DataFrame(results)
    n = len(df)

    # Aggregates
    n_improved = (df["corrected_mae"] < df["profile_mae"]).sum()
    corr_improved = (df["corrected_corr_mae"] < df["profile_corr_mae"]).sum()
    meal_improved = (df["corrected_meal_mae"] < df["profile_meal_mae"]).sum()

    med_p = df["profile_mae"].median()
    med_c = df["corrected_mae"].median()
    med_p_meal = df["profile_meal_mae"].median()
    med_c_meal = df["corrected_meal_mae"].median()
    meal_change = (med_c_meal - med_p_meal) / max(med_p_meal, 1) * 100

    tbr_doubled = (df["corrected_tbr"] > df["profile_tbr"] * 2 + 0.001).sum()
    if n >= 5:
        t, p = stats.ttest_rel(df["corrected_tbr"], df["profile_tbr"])
    else:
        t, p = 0, 1

    print(f"\n{'='*70}\nRESULTS\n{'='*70}")
    print(f"  MAE improved: {n_improved}/{n} ({n_improved/n*100:.0f}%)")
    print(f"  Correction MAE improved: {corr_improved}/{n}")
    print(f"  Meal MAE improved: {meal_improved}/{n}")
    print(f"  Median MAE: {med_p:.1f} → {med_c:.1f} ({(med_p-med_c)/max(med_p,1)*100:+.0f}%)")
    print(f"  Median meal MAE change: {meal_change:+.1f}%")
    print(f"  TBR >2× worse: {tbr_doubled}/{n}")
    print(f"  TBR t-test: t={t:.3f}, p={p:.4f}")

    h1 = n_improved > n * 0.4
    h2 = corr_improved > n * 0.5
    h3 = abs(meal_change) < 10
    h4 = p > 0.05 or t <= 0
    h5 = tbr_doubled == 0

    hypotheses = {
        "H1_overall_mae_40pct": bool(h1),
        "H2_correction_mae_50pct": bool(h2),
        "H3_meal_mae_within_10pct": bool(h3),
        "H4_tbr_not_worse": bool(h4),
        "H5_no_2x_tbr": bool(h5),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'='*70}\nHYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"{n_improved}/{n} improved ({n_improved/n*100:.0f}%). "
               f"MAE: {med_p:.0f}→{med_c:.0f}. "
               f"Corr MAE improved: {corr_improved}/{n}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / f"exp-{EXP_ID}_isf_only_validation.json"
    with open(out, "w") as f:
        json.dump(clean({"exp_id": EXP_ID, "title": TITLE,
                         "hypotheses": hypotheses,
                         "per_patient": df.to_dict(orient="records"),
                         "summary": summary}), f, indent=2)
    print(f"\nSaved: {out}")

    # Dashboard
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        fig = plt.figure(figsize=(16, 10))
        fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
        gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

        # Profile vs Corrected MAE
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.scatter(df["profile_mae"], df["corrected_mae"], c="steelblue", s=60, alpha=0.7)
        lim = max(df["profile_mae"].max(), df["corrected_mae"].max()) * 1.1
        ax1.plot([0, lim], [0, lim], "r--", lw=1)
        ax1.set_xlabel("Profile MAE"); ax1.set_ylabel("ISF-Corrected MAE")
        ax1.set_title("Overall MAE")

        # Correction MAE
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.scatter(df["profile_corr_mae"], df["corrected_corr_mae"], c="steelblue", s=60, alpha=0.7)
        lim = max(df["profile_corr_mae"].max(), df["corrected_corr_mae"].max()) * 1.1
        ax2.plot([0, lim], [0, lim], "r--", lw=1)
        ax2.set_xlabel("Profile Corr MAE"); ax2.set_ylabel("ISF-Corrected Corr MAE")
        ax2.set_title("Correction-Episode MAE")

        # TBR
        ax3 = fig.add_subplot(gs[0, 2])
        ax3.scatter(df["profile_tbr"]*100, df["corrected_tbr"]*100, c="steelblue", s=60, alpha=0.7)
        lim = max(df["profile_tbr"].max(), df["corrected_tbr"].max()) * 110
        ax3.plot([0, lim], [0, lim], "r--", lw=1)
        ax3.set_xlabel("Profile TBR (%)"); ax3.set_ylabel("ISF-Corrected TBR (%)")
        ax3.set_title("Safety: TBR")

        # Per-patient improvement
        ax4 = fig.add_subplot(gs[1, 0])
        impr = (df["profile_mae"] - df["corrected_mae"]) / df["profile_mae"].clip(1) * 100
        colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in impr]
        ax4.bar(range(n), impr.values, color=colors, alpha=0.7)
        ax4.axhline(0, color="black", lw=0.5)
        ax4.set_xlabel("Patient"); ax4.set_ylabel("MAE Improvement (%)")
        ax4.set_title("Per-Patient Improvement")

        # Summary
        ax5 = fig.add_subplot(gs[1, 1:])
        ax5.axis("off")
        lines = [f"EXP-{EXP_ID}: {TITLE}", "",
                 f"MAE improved: {n_improved}/{n} ({n_improved/n*100:.0f}%)",
                 f"Correction MAE improved: {corr_improved}/{n}",
                 f"Meal MAE change: {meal_change:+.1f}%",
                 f"TBR >2× worse: {tbr_doubled}/{n}", "",
                 "Hypotheses:"]
        for k, v in hypotheses.items():
            lines.append(f"  {'✓' if v else '✗'} {k}")
        ax5.text(0.05, 0.95, "\n".join(lines), transform=ax5.transAxes,
                 fontsize=10, va="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        VIZ_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(VIZ_DIR / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Dashboard: {VIZ_DIR / f'exp-{EXP_ID}-dashboard.png'}")
    except ImportError:
        pass

    print(f"\n{'='*70}\nSUMMARY: {summary}\n{'='*70}")


if __name__ == "__main__":
    main()
