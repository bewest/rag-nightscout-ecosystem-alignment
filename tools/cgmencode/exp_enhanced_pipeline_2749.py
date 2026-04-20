#!/usr/bin/env python3
"""
EXP-2749: Enhanced Pipeline with Dose-Dependent CR
====================================================

Scientific Question
-------------------
Does integrating size-stratified CR (from EXP-2747) into the full pipeline
improve over the flat-CR integrated pipeline (EXP-2743)?

Pipeline v3:
  - ISF: Waterfall residuals (EXP-2719b)
  - CR: Size-stratified — small meals use compensated CR, large meals use
        higher CR (reflecting slower absorption for large meals)
  - EGP: Per-patient adjustment (EXP-2742)
  - Basal: Profile (unchanged — EXP-2745 showed adjustment fails)

Predecessors
------------
- EXP-2743: Integrated pipeline (28% MAE improvement, 14/22 improve)
- EXP-2747: Dose-dependent CR (4/5 PASS, 82% show >20% diff large vs small)

Hypotheses
----------
H1: Enhanced pipeline beats profile for >65% of patients (vs 64% in 2743)
H2: Enhanced pipeline beats flat-CR pipeline for >40% of patients
H3: Meal-specific MAE improves with size-CR for >50% of patients
H4: Median MAE improvement over profile exceeds 30% (vs 28% in 2743)
H5: Safety maintained (TBR not significantly worse)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2741 = Path("externals/experiments/exp-2741_cr_compensated.json")
EXP_2742 = Path("externals/experiments/exp-2742_egp_personalized_isf.json")
EXP_2747 = Path("externals/experiments/exp-2747_dose_dependent_cr.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/enhanced-pipeline")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

HORIZON = 24  # 2h in 5-min steps


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf_data = json.loads(EXP_2719B.read_text())
    isf_map = {p["patient_id"]: p.get("correction_factor", 1.0)
               for p in isf_data["results"]["2h"]["per_patient"]}

    cr_data = json.loads(EXP_2741.read_text())
    cr_map = {p["patient_id"]: p.get("compensated_cr")
              for p in cr_data["per_patient"]}

    egp_data = json.loads(EXP_2742.read_text())
    egp_map = {p["patient_id"]: p for p in egp_data["per_patient"]}

    cr_size_data = json.loads(EXP_2747.read_text())
    cr_size_map = {p["patient_id"]: p for p in cr_size_data["per_patient"]}

    return grid, isf_map, cr_map, egp_map, cr_size_map


def extract_episodes(pg: pd.DataFrame, max_episodes=100) -> list:
    """Extract correction and meal episodes."""
    episodes = []

    # Corrections: BG >= 180, bolus > 0
    corr_mask = (pg["glucose"] >= 180) & (pg["bolus"] > 0)
    for idx in pg.index[corr_mask]:
        pos = pg.index.get_loc(idx)
        if pos + HORIZON >= len(pg):
            continue
        window = pg.iloc[pos:pos + HORIZON]
        glucose = window["glucose"].values
        if np.isnan(glucose).sum() > len(glucose) * 0.3:
            continue
        hour = 12.0
        if "time" in pg.columns:
            try: hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
            except: pass
        episodes.append({
            "type": "correction",
            "bg0": float(glucose[0]),
            "bolus": float(pg.iloc[pos]["bolus"]),
            "carbs": float(pg.iloc[pos].get("carbs", 0) or 0),
            "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
            "hour": hour,
        })

    # Meals: carbs > 10
    meal_mask = pg["carbs"] > 10
    for idx in pg.index[meal_mask]:
        pos = pg.index.get_loc(idx)
        if pos + HORIZON >= len(pg):
            continue
        window = pg.iloc[pos:pos + HORIZON]
        glucose = window["glucose"].values
        if np.isnan(glucose).sum() > len(glucose) * 0.3:
            continue
        hour = 12.0
        if "time" in pg.columns:
            try: hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
            except: pass
        episodes.append({
            "type": "meal",
            "bg0": float(glucose[0]),
            "bolus": float(pg.iloc[pos].get("bolus", 0) or 0),
            "carbs": float(pg.iloc[pos]["carbs"]),
            "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
            "hour": hour,
        })

    if len(episodes) > max_episodes:
        rng = np.random.RandomState(42)
        episodes = [episodes[i] for i in rng.choice(len(episodes), max_episodes, replace=False)]
    return episodes


def simulate_mode(episodes, settings, profile_basal, size_cr=None):
    """Simulate episodes with optional size-stratified CR."""
    maes, tbrs, tirs = [], [], []
    meal_maes = []

    for ep in episodes:
        # For size-CR mode, adjust CR for large meals
        if size_cr and ep["carbs"] > 0:
            threshold = size_cr.get("size_threshold", 40)
            if ep["carbs"] > threshold:
                s = TherapySettings(
                    isf=settings.isf, cr=size_cr["size_cr_large"],
                    basal_rate=settings.basal_rate, dia_hours=settings.dia_hours,
                )
            else:
                s = TherapySettings(
                    isf=settings.isf, cr=size_cr["size_cr_small"],
                    basal_rate=settings.basal_rate, dia_hours=settings.dia_hours,
                )
        else:
            s = settings

        bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
        carb_events = [CarbEvent(0, ep["carbs"])] if ep["carbs"] > 0 else []
        duration = HORIZON * 5 / 60

        try:
            result = forward_simulate(
                initial_glucose=ep["bg0"], settings=s,
                duration_hours=duration, start_hour=ep.get("hour", 12),
                bolus_events=bolus_events, carb_events=carb_events,
                initial_iob=0.0, metabolic_basal_rate=profile_basal,
                counter_reg_k=0.3, egp_enabled=True,
            )
            sim = np.array(result.glucose)
            actual = np.array([v if v is not None else np.nan for v in ep["trajectory"]])
            n = min(len(sim), len(actual))
            valid_mask = ~np.isnan(actual[:n])
            if valid_mask.sum() >= 3:
                mae = float(np.mean(np.abs(sim[:n][valid_mask] - actual[:n][valid_mask])))
                maes.append(mae)
                tbrs.append(float(np.sum(sim[:n] < 70)) / n)
                tirs.append(float(np.sum((sim[:n] >= 70) & (sim[:n] <= 180))) / n)
                if ep["type"] == "meal":
                    meal_maes.append(mae)
        except Exception:
            pass

    if not maes:
        return {"mae": 999.0, "tbr": 0.0, "tir": 0.0, "meal_mae": 999.0}
    return {
        "mae": float(np.median(maes)),
        "tbr": float(np.median(tbrs)) * 100,
        "tir": float(np.median(tirs)) * 100,
        "meal_mae": float(np.median(meal_maes)) if meal_maes else 999.0,
    }


def main():
    print("=" * 70)
    print("EXP-2749: Enhanced Pipeline with Dose-Dependent CR")
    print("=" * 70)

    grid, isf_map, cr_map, egp_map, cr_size_map = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    results = []
    n_beats_profile = 0
    n_beats_flat = 0
    n_meal_improves = 0
    tbr_diffs = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values(
            "time" if "time" in grid.columns else grid.columns[0]
        ).reset_index(drop=True)

        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # ISF
        isf_cf = isf_map.get(pid, 1.0)
        corrected_isf = float(np.clip(profile_isf / isf_cf, 5, 200))
        egp_info = egp_map.get(pid, {})
        adj_isf = egp_info.get("adjusted_isf")
        final_isf = float(np.clip(adj_isf, 5, 200)) if adj_isf and adj_isf > 0 else corrected_isf

        # CR flat (compensated with safety clamp)
        comp_cr = cr_map.get(pid)
        safe_cr = max(comp_cr, profile_cr * 0.7) if comp_cr and comp_cr > 0 else profile_cr

        # CR size-stratified
        cr_size_info = cr_size_map.get(pid, {})
        size_cr = {
            "size_cr_small": cr_size_info.get("size_cr_small", safe_cr),
            "size_cr_large": cr_size_info.get("size_cr_large", safe_cr),
            "size_threshold": cr_size_info.get("size_threshold", 40),
        }
        # Safety clamp size CRs
        size_cr["size_cr_small"] = max(size_cr["size_cr_small"], profile_cr * 0.5)
        size_cr["size_cr_large"] = max(size_cr["size_cr_large"], profile_cr * 0.5)

        episodes = extract_episodes(pg)

        # Mode 1: Profile
        settings_profile = TherapySettings(isf=profile_isf, cr=profile_cr, basal_rate=profile_basal, dia_hours=6.0)
        r_profile = simulate_mode(episodes, settings_profile, profile_basal)

        # Mode 2: Integrated flat CR (EXP-2743 style)
        settings_flat = TherapySettings(isf=final_isf, cr=safe_cr, basal_rate=profile_basal, dia_hours=6.0)
        r_flat = simulate_mode(episodes, settings_flat, profile_basal)

        # Mode 3: Enhanced — integrated + size-stratified CR
        settings_enhanced = TherapySettings(isf=final_isf, cr=safe_cr, basal_rate=profile_basal, dia_hours=6.0)
        r_enhanced = simulate_mode(episodes, settings_enhanced, profile_basal, size_cr=size_cr)

        beats_profile = r_enhanced["mae"] < r_profile["mae"]
        beats_flat = r_enhanced["mae"] < r_flat["mae"]
        meal_improves = r_enhanced["meal_mae"] < r_flat["meal_mae"]
        if beats_profile: n_beats_profile += 1
        if beats_flat: n_beats_flat += 1
        if meal_improves: n_meal_improves += 1
        tbr_diffs.append(r_enhanced["tbr"] - r_profile["tbr"])

        entry = {
            "patient_id": pid,
            "n_episodes": len(episodes),
            "profile_mae": r_profile["mae"],
            "flat_mae": r_flat["mae"],
            "enhanced_mae": r_enhanced["mae"],
            "profile_meal_mae": r_profile.get("meal_mae", 999),
            "flat_meal_mae": r_flat.get("meal_mae", 999),
            "enhanced_meal_mae": r_enhanced.get("meal_mae", 999),
            "beats_profile": beats_profile,
            "beats_flat": beats_flat,
            "meal_improves": meal_improves,
            "profile_tbr": r_profile["tbr"],
            "enhanced_tbr": r_enhanced["tbr"],
            "size_cr_small": size_cr["size_cr_small"],
            "size_cr_large": size_cr["size_cr_large"],
        }
        results.append(entry)

        prof_imp = (r_profile["mae"] - r_enhanced["mae"]) / r_profile["mae"] * 100 if r_profile["mae"] < 900 else 0
        flat_imp = (r_flat["mae"] - r_enhanced["mae"]) / r_flat["mae"] * 100 if r_flat["mae"] < 900 else 0
        print(f"  {pid[:14]:<16} eps={len(episodes):>3}  "
              f"prof={r_profile['mae']:>5.1f} flat={r_flat['mae']:>5.1f} enh={r_enhanced['mae']:>5.1f} "
              f"Δprof={prof_imp:>+5.1f}% Δflat={flat_imp:>+5.1f}%")

    # Summary
    rdf = pd.DataFrame(results)
    valid = rdf[rdf["profile_mae"] < 900]

    prof_maes = valid["profile_mae"].values
    enh_maes = valid["enhanced_mae"].values
    median_improvement = float(np.median((prof_maes - enh_maes) / prof_maes * 100))

    print(f"\n{'=' * 70}")

    h1 = n_beats_profile / len(patients) > 0.65
    h2 = n_beats_flat / len(patients) > 0.4
    h3 = n_meal_improves / len(patients) > 0.5
    h4 = median_improvement > 30
    try:
        tbr_p = stats.ttest_1samp(np.array(tbr_diffs), 0)[1]
        if np.isnan(tbr_p): tbr_p = 1.0
    except: tbr_p = 1.0
    h5 = tbr_p > 0.05

    passed = sum([h1, h2, h3, h4, h5])
    print(f"HYPOTHESES: {passed}/5 pass")

    hypotheses = {
        "H1_beats_profile_65pct": {"passed": h1, "n": n_beats_profile, "fraction": n_beats_profile / len(patients)},
        "H2_beats_flat_40pct": {"passed": h2, "n": n_beats_flat, "fraction": n_beats_flat / len(patients)},
        "H3_meal_improves_50pct": {"passed": h3, "n": n_meal_improves, "fraction": n_meal_improves / len(patients)},
        "H4_median_improvement_30pct": {"passed": h4, "median_improvement": median_improvement},
        "H5_safety": {"passed": h5, "tbr_p": float(tbr_p)},
    }
    for k, v in hypotheses.items():
        print(f"  {'✓' if v['passed'] else '✗'} {k}")

    print(f"\n  Enhanced beats profile: {n_beats_profile}/{len(patients)}")
    print(f"  Enhanced beats flat CR: {n_beats_flat}/{len(patients)}")
    print(f"  Meal MAE improves: {n_meal_improves}/{len(patients)}")
    print(f"  Median improvement over profile: {median_improvement:.1f}%")
    print(f"  Median profile MAE: {np.median(prof_maes):.1f}")
    print(f"  Median enhanced MAE: {np.median(enh_maes):.1f}")
    print(f"  TBR p-value: {tbr_p:.3f}")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2749_enhanced_pipeline.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2749",
            "title": "Enhanced Pipeline with Dose-Dependent CR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": results,
            "summary": {
                "median_profile_mae": float(np.median(prof_maes)),
                "median_enhanced_mae": float(np.median(enh_maes)),
                "median_improvement_pct": median_improvement,
                "n_beats_profile": n_beats_profile,
                "n_beats_flat": n_beats_flat,
            },
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(results, hypotheses)


def create_dashboard(results, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    rdf = pd.DataFrame(results)
    valid = rdf[rdf["profile_mae"] < 900]
    fig = plt.figure(figsize=(18, 10))
    fig.suptitle("EXP-2749: Enhanced Pipeline — ISF + Size-CR + EGP", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: Profile vs Enhanced scatter
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(valid["profile_mae"], valid["enhanced_mae"], c="steelblue", s=60, alpha=0.7)
    lim = max(valid["profile_mae"].max(), valid["enhanced_mae"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", lw=1)
    ax1.set_xlabel("Profile MAE (mg/dL)")
    ax1.set_ylabel("Enhanced MAE (mg/dL)")
    ax1.set_title("Profile vs Enhanced Pipeline")

    # Panel 2: Flat vs Enhanced scatter
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(valid["flat_mae"], valid["enhanced_mae"], c="steelblue", s=60, alpha=0.7)
    lim = max(valid["flat_mae"].max(), valid["enhanced_mae"].max()) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", lw=1)
    ax2.set_xlabel("Flat CR Pipeline MAE")
    ax2.set_ylabel("Enhanced (Size-CR) MAE")
    ax2.set_title("Flat CR vs Size-Stratified CR")

    # Panel 3: Meal-only MAE comparison
    ax3 = fig.add_subplot(gs[0, 2])
    meal_valid = valid[(valid["flat_meal_mae"] < 900) & (valid["enhanced_meal_mae"] < 900)]
    if len(meal_valid) > 0:
        ax3.scatter(meal_valid["flat_meal_mae"], meal_valid["enhanced_meal_mae"],
                   c="steelblue", s=60, alpha=0.7)
        lim = max(meal_valid["flat_meal_mae"].max(), meal_valid["enhanced_meal_mae"].max()) * 1.1
        ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Flat CR Meal MAE")
    ax3.set_ylabel("Size-CR Meal MAE")
    ax3.set_title("Meal-Specific: Flat vs Size-CR")

    # Panel 4: Per-patient improvement
    ax4 = fig.add_subplot(gs[1, 0:2])
    imp = ((valid["profile_mae"] - valid["enhanced_mae"]) / valid["profile_mae"] * 100)
    colors = ["green" if v > 0 else "red" for v in imp]
    x = np.arange(len(valid))
    ax4.bar(x, imp, color=colors, alpha=0.7)
    ax4.axhline(0, color="black", lw=0.5)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:6] for p in valid["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE Improvement (%)")
    ax4.set_title("Per-Patient Improvement over Profile")

    # Panel 5: Hypotheses
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        h_text += f"\n{tag} {k.replace('_', ' ')}"
    ax5.text(0.1, 0.9, h_text, transform=ax5.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2749-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2749-dashboard.png'}")


if __name__ == "__main__":
    main()
