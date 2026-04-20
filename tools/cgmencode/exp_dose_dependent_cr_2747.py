#!/usr/bin/env python3
"""
EXP-2747: Dose-Dependent CR Analysis
=====================================

Scientific Question
-------------------
Does CR (carb ratio) vary with meal size? Analogous to the finding that ISF
is dose-dependent (EXP-2680: r=-0.66 to -0.86), larger meals may have
different absorption dynamics leading to non-linear carb impact.

In closed-loop AID, the controller adjusts insulin differently for large vs
small meals. EXP-2741 showed controllers SUSPEND basal during meals. Do they
suspend MORE for larger meals? Does absorption kinetics change?

Predecessors
------------
- EXP-2680: Dose-dependent ISF (r=-0.66 to -0.86)
- EXP-2741: Bilateral meal deconfounding (compensated CR)
- EXP-2743: Integrated pipeline (28% MAE improvement)

Hypotheses
----------
H1: CR varies significantly with meal size (large meals > small meals)
    — ANOVA across meal size tertiles p<0.05 for >50% of patients
H2: Effective CR for large meals (>60g) is >20% different from small (<30g)
H3: Controller suspension is proportional to meal size (r > 0.3)
H4: Size-stratified CR improves MAE over flat CR for >40% of patients
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
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/dose-dependent-cr")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

MEAL_HORIZON = 48  # steps (4h)
MEAL_MIN_CARBS = 5


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf_data = json.loads(EXP_2719B.read_text())
    isf_map = {p["patient_id"]: p.get("correction_factor", 1.0)
               for p in isf_data["results"]["2h"]["per_patient"]}

    egp_data = json.loads(EXP_2742.read_text())
    egp_map = {p["patient_id"]: p for p in egp_data["per_patient"]}

    return grid, isf_map, egp_map


def extract_meal_events(pg: pd.DataFrame) -> list:
    """Extract meal events with controller response data."""
    events = []
    meal_mask = pg["carbs"] >= MEAL_MIN_CARBS
    meal_idx = pg.index[meal_mask]

    for idx in meal_idx:
        pos = pg.index.get_loc(idx)
        if pos + MEAL_HORIZON >= len(pg):
            continue

        window = pg.iloc[pos:pos + MEAL_HORIZON]
        glucose = window["glucose"].values
        if np.isnan(glucose).sum() > len(glucose) * 0.3:
            continue

        carbs = float(pg.iloc[pos]["carbs"])
        bolus = float(pg.iloc[pos].get("bolus", 0) or 0)

        # Compute controller response over meal window
        sched_basal = float(pg.iloc[pos].get("scheduled_basal_rate", 0.8) or 0.8)
        net_basals = window.get("net_basal", pd.Series(sched_basal, index=window.index)).fillna(sched_basal).values
        excess_basal = np.sum((net_basals - sched_basal) * (5 / 60))  # total U excess

        smbs = window.get("bolus_smb", pd.Series(0, index=window.index)).fillna(0).values
        total_smb = float(np.sum(smbs))

        # Total insulin in window
        total_insulin = bolus + total_smb + excess_basal

        # BG trajectory
        bg0 = float(glucose[0])
        bg_end = float(glucose[-1]) if not np.isnan(glucose[-1]) else bg0

        # ISF for BGI calculation
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)

        # BGI from total insulin
        bgi = total_insulin * isf  # expected BG drop from insulin

        # Carb impact: observed rise + BGI
        # BG_change = carb_rise - insulin_drop
        # carb_rise = BG_change + insulin_drop = (bg_end - bg0) + bgi
        bg_change = bg_end - bg0
        carb_impact = bg_change + bgi  # mg/dL rise from carbs

        # Effective CR: carbs / (carb_impact / ISF) = carbs * ISF / carb_impact
        if carb_impact > 10:  # positive carb impact needed
            effective_cr = carbs * isf / carb_impact if carb_impact > 0 else None
        else:
            effective_cr = None

        hour = 12.0
        if "time" in pg.columns:
            try:
                hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
            except Exception:
                pass

        events.append({
            "carbs": carbs,
            "bolus": bolus,
            "excess_basal": float(excess_basal),
            "total_smb": total_smb,
            "total_insulin": float(total_insulin),
            "bg0": bg0,
            "bg_end": bg_end,
            "bg_change": float(bg_change),
            "carb_impact": float(carb_impact),
            "effective_cr": float(effective_cr) if effective_cr else None,
            "isf": isf,
            "sched_basal": sched_basal,
            "hour": hour,
            "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
        })

    return events


def analyze_dose_dependence(events: list) -> dict:
    """Analyze whether CR varies with meal size."""
    valid = [e for e in events if e["effective_cr"] is not None and 0 < e["effective_cr"] < 100]
    if len(valid) < 10:
        return {"n_valid": len(valid), "significant": False}

    carbs = np.array([e["carbs"] for e in valid])
    crs = np.array([e["effective_cr"] for e in valid])

    # Overall correlation
    r, p = stats.pearsonr(carbs, crs)

    # Tertile analysis
    t1 = np.percentile(carbs, 33)
    t2 = np.percentile(carbs, 67)
    small = [e["effective_cr"] for e in valid if e["carbs"] <= t1]
    medium = [e["effective_cr"] for e in valid if t1 < e["carbs"] <= t2]
    large = [e["effective_cr"] for e in valid if e["carbs"] > t2]

    # ANOVA
    groups = [g for g in [small, medium, large] if len(g) >= 3]
    if len(groups) >= 2:
        f_stat, anova_p = stats.f_oneway(*groups)
    else:
        f_stat, anova_p = 0, 1.0

    # Controller response vs meal size
    basal_suspensions = np.array([e["excess_basal"] for e in valid])
    r_ctrl, p_ctrl = stats.pearsonr(carbs, basal_suspensions) if len(valid) >= 5 else (0, 1)

    return {
        "n_valid": len(valid),
        "r_carbs_cr": float(r),
        "p_carbs_cr": float(p),
        "anova_p": float(anova_p),
        "anova_f": float(f_stat),
        "significant": anova_p < 0.05,
        "median_cr_small": float(np.median(small)) if small else None,
        "median_cr_medium": float(np.median(medium)) if medium else None,
        "median_cr_large": float(np.median(large)) if large else None,
        "n_small": len(small),
        "n_large": len(large),
        "cr_ratio_large_small": (float(np.median(large) / np.median(small))
                                  if small and large and np.median(small) > 0 else None),
        "r_controller_mealsize": float(r_ctrl),
        "p_controller_mealsize": float(p_ctrl),
    }


def build_size_stratified_cr(events: list, profile_cr: float) -> dict:
    """Build small/medium/large CR for simulation."""
    valid = [e for e in events if e["effective_cr"] is not None and 0 < e["effective_cr"] < 100]
    if len(valid) < 10:
        return {"small": profile_cr, "large": profile_cr, "threshold": 40}

    carbs = np.array([e["carbs"] for e in valid])
    threshold = float(np.median(carbs))

    small_crs = [e["effective_cr"] for e in valid if e["carbs"] <= threshold]
    large_crs = [e["effective_cr"] for e in valid if e["carbs"] > threshold]

    small_cr = float(np.median(small_crs)) if small_crs else profile_cr
    large_cr = float(np.median(large_crs)) if large_crs else profile_cr

    # Safety clamp
    small_cr = max(small_cr, profile_cr * 0.5)
    large_cr = max(large_cr, profile_cr * 0.5)

    return {"small": small_cr, "large": large_cr, "threshold": threshold}


def simulate_episodes(episodes, settings, profile_basal, size_cr=None):
    """Simulate episodes, optionally using size-stratified CR."""
    maes, tbrs = [], []

    for ep in episodes:
        # Use size-stratified CR if provided
        if size_cr and ep["carbs"] > 0:
            if ep["carbs"] > size_cr["threshold"]:
                s = TherapySettings(
                    isf=settings.isf, cr=size_cr["large"],
                    basal_rate=settings.basal_rate, dia_hours=settings.dia_hours,
                    basal_schedule=settings.basal_schedule,
                )
            else:
                s = TherapySettings(
                    isf=settings.isf, cr=size_cr["small"],
                    basal_rate=settings.basal_rate, dia_hours=settings.dia_hours,
                    basal_schedule=settings.basal_schedule,
                )
        else:
            s = settings

        bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
        carb_events = [CarbEvent(0, ep["carbs"])] if ep["carbs"] > 0 else []
        duration = MEAL_HORIZON * 5 / 60

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
            valid = ~np.isnan(actual[:n])
            if valid.sum() >= 3:
                maes.append(float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid]))))
                tbrs.append(float(np.sum(sim[:n] < 70)) / n)
        except Exception:
            pass

    if not maes:
        return {"mae": 999.0, "tbr": 0.0}
    return {"mae": float(np.median(maes)), "tbr": float(np.median(tbrs)) * 100}


def main():
    print("=" * 70)
    print("EXP-2747: Dose-Dependent CR Analysis")
    print("=" * 70)

    grid, isf_map, egp_map = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    results = []
    n_significant = 0
    n_large_diff = 0
    n_ctrl_corr = 0
    n_size_improves = 0
    tbr_diffs = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values("time" if "time" in grid.columns else grid.columns[0]).reset_index(drop=True)
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # ISF correction
        isf_cf = isf_map.get(pid, 1.0)
        corrected_isf = float(np.clip(profile_isf / isf_cf, 5, 200))
        egp_info = egp_map.get(pid, {})
        adj_isf = egp_info.get("adjusted_isf")
        final_isf = float(np.clip(adj_isf, 5, 200)) if adj_isf and adj_isf > 0 else corrected_isf

        events = extract_meal_events(pg)
        analysis = analyze_dose_dependence(events)

        if analysis.get("significant"):
            n_significant += 1

        cr_ratio = analysis.get("cr_ratio_large_small")
        if cr_ratio and abs(cr_ratio - 1.0) > 0.2:
            n_large_diff += 1

        r_ctrl = analysis.get("r_controller_mealsize", 0)
        if abs(r_ctrl) > 0.3:
            n_ctrl_corr += 1

        # Build size-stratified CR
        size_cr = build_size_stratified_cr(events, profile_cr)

        # Simulate: flat CR vs size-stratified CR
        # Only meal episodes
        meal_eps = [e for e in events if e["carbs"] >= MEAL_MIN_CARBS]

        settings_flat = TherapySettings(isf=final_isf, cr=profile_cr, basal_rate=profile_basal, dia_hours=6.0)
        settings_integrated = TherapySettings(isf=final_isf, cr=profile_cr, basal_rate=profile_basal, dia_hours=6.0)

        r_flat = simulate_episodes(meal_eps, settings_flat, profile_basal)
        r_size = simulate_episodes(meal_eps, settings_integrated, profile_basal, size_cr=size_cr)

        size_improves = r_size["mae"] < r_flat["mae"]
        if size_improves:
            n_size_improves += 1

        tbr_diffs.append(r_size["tbr"] - r_flat["tbr"])

        entry = {
            "patient_id": pid,
            "n_meals": len(events),
            "n_valid_cr": analysis.get("n_valid", 0),
            "profile_cr": profile_cr,
            **analysis,
            "size_cr_small": size_cr["small"],
            "size_cr_large": size_cr["large"],
            "size_threshold": size_cr["threshold"],
            "flat_mae": r_flat["mae"],
            "size_mae": r_size["mae"],
            "size_improves": size_improves,
            "flat_tbr": r_flat["tbr"],
            "size_tbr": r_size["tbr"],
        }
        results.append(entry)

        sig = "***" if analysis.get("significant") else "   "
        diff = f"L/S={cr_ratio:.2f}" if cr_ratio else "L/S=N/A "
        print(f"  {pid[:14]:<16} {sig} meals={len(events):>4} valid={analysis.get('n_valid',0):>4} "
              f"{diff:<10} ctrl_r={r_ctrl:>+5.2f} "
              f"MAE: flat={r_flat['mae']:>5.1f} size={r_size['mae']:>5.1f}{'+'if size_improves else '-'}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: ", end="")

    h1 = n_significant / len(patients) > 0.5
    h2 = n_large_diff / len(patients) > 0.5  # >20% difference for majority
    h3 = n_ctrl_corr / len(patients) > 0.5
    h4 = n_size_improves / len(patients) > 0.4
    try:
        tbr_arr = np.array(tbr_diffs)
        tbr_t, tbr_p = stats.ttest_1samp(tbr_arr, 0)
        if np.isnan(tbr_p):
            tbr_p = 1.0
    except Exception:
        tbr_p = 1.0
    h5 = tbr_p > 0.05

    passed = sum([h1, h2, h3, h4, h5])
    print(f"{passed}/5 pass")

    hypotheses = {
        "H1_dose_dependent_cr": {"passed": h1, "n": n_significant, "fraction": n_significant / len(patients)},
        "H2_large_diff_20pct": {"passed": h2, "n": n_large_diff, "fraction": n_large_diff / len(patients)},
        "H3_controller_proportional": {"passed": h3, "n": n_ctrl_corr, "fraction": n_ctrl_corr / len(patients)},
        "H4_size_improves_40pct": {"passed": h4, "n": n_size_improves, "fraction": n_size_improves / len(patients)},
        "H5_safety_maintained": {"passed": h5, "tbr_p": float(tbr_p)},
    }

    for k, v in hypotheses.items():
        print(f"  {'✓' if v['passed'] else '✗'} {k}")

    print(f"\n  Dose-dependent CR (significant): {n_significant}/{len(patients)}")
    print(f"  Large/small CR diff >20%: {n_large_diff}/{len(patients)}")
    print(f"  Controller proportional: {n_ctrl_corr}/{len(patients)}")
    print(f"  Size-stratified improves: {n_size_improves}/{len(patients)}")
    print(f"  TBR p-value: {tbr_p:.3f}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2747_dose_dependent_cr.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2747",
            "title": "Dose-Dependent CR Analysis",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": results,
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
    fig = plt.figure(figsize=(18, 10))
    fig.suptitle("EXP-2747: Dose-Dependent CR Analysis", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: Large/Small CR ratio
    ax1 = fig.add_subplot(gs[0, 0])
    ratios = rdf["cr_ratio_large_small"].dropna()
    ax1.hist(ratios, bins=15, color="steelblue", alpha=0.7, edgecolor="black")
    ax1.axvline(1.0, color="red", ls="--", lw=1, label="Equal")
    ax1.set_xlabel("CR Large / CR Small")
    ax1.set_ylabel("Count")
    ax1.set_title("Dose-Dependent CR Ratio")
    ax1.legend()

    # Panel 2: Controller suspension vs meal size
    ax2 = fig.add_subplot(gs[0, 1])
    r_ctrls = rdf["r_controller_mealsize"].dropna()
    ax2.bar(range(len(r_ctrls)), r_ctrls.values, color="steelblue", alpha=0.7)
    ax2.axhline(0.3, color="red", ls="--", lw=1)
    ax2.axhline(-0.3, color="red", ls="--", lw=1)
    ax2.set_xlabel("Patient")
    ax2.set_ylabel("r(meal_size, basal_suspension)")
    ax2.set_title("Controller Response vs Meal Size")

    # Panel 3: Flat vs Size MAE
    ax3 = fig.add_subplot(gs[0, 2])
    valid = rdf[(rdf["flat_mae"] < 900) & (rdf["size_mae"] < 900)]
    ax3.scatter(valid["flat_mae"], valid["size_mae"], c="steelblue", s=60, alpha=0.7)
    lim = max(valid["flat_mae"].max(), valid["size_mae"].max()) * 1.1
    ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Flat CR MAE")
    ax3.set_ylabel("Size-Stratified CR MAE")
    ax3.set_title("Flat vs Size-Stratified CR")

    # Panel 4: Per-patient MAE comparison
    ax4 = fig.add_subplot(gs[1, 0:2])
    x = np.arange(len(valid))
    w = 0.35
    ax4.bar(x - w/2, valid["flat_mae"], w, label="Flat CR", color="lightgray")
    ax4.bar(x + w/2, valid["size_mae"], w, label="Size-Stratified", color="steelblue", alpha=0.7)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:6] for p in valid["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE (mg/dL)")
    ax4.set_title("Per-Patient: Flat vs Size-Stratified CR")
    ax4.legend()

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
    fig.savefig(VIZ_DIR / "exp-2747-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2747-dashboard.png'}")


if __name__ == "__main__":
    main()
