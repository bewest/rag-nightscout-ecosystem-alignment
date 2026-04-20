#!/usr/bin/env python3
"""
EXP-2743: Integrated Settings Pipeline Validation
==================================================

End-to-end validation combining all pipeline components:
- ISF corrections from EXP-2719b (waterfall residuals, validated in 2739)
- Controller-compensated CR from EXP-2741 (bilateral meal deconfounding)
- EGP personalization from EXP-2742 (per-patient EGP adjustment)
- Safety clamp: limit CR corrections to avoid TBR elevation

This is the final pipeline test: can we recommend ISF + CR + EGP
adjustments that improve glucose predictions and remain safe?

HYPOTHESES:
  H1: Integrated pipeline improves MAE over profile in >60% of patients
  H2: Integrated pipeline improves over ISF-only (EXP-2739) in >40%
  H3: Safety: TBR not significantly worse (paired t p>0.05)
  H4: Time-in-range (70-180) improves for >50% of patients
  H5: Median MAE improvement >15% vs profile settings

REFERENCES: EXP-2719b, EXP-2739, EXP-2741, EXP-2742
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)

EXP_ID = "2743"
TITLE = "Integrated Settings Pipeline Validation"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2741 = Path("externals/experiments/exp-2741_cr_compensated.json")
EXP_2742 = Path("externals/experiments/exp-2742_egp_personalized_isf.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/integrated-pipeline")

CORRECTION_HORIZON = 24  # 2h
MEAL_HORIZON = 48  # 4h
MIN_SPACING = 24
DIA_HOURS = 5.0
MIN_BG_CORRECTION = 150
MIN_CARBS = 10
MAX_EPISODES = 30
TBR_SAFETY_CLAMP = 0.05  # max 5% TBR before clamping CR


def load_all():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf_data = json.loads(EXP_2719B.read_text())
    cr_data = json.loads(EXP_2741.read_text())
    egp_data = json.loads(EXP_2742.read_text())

    isf_map = {}
    for pp in isf_data["results"]["2h"]["per_patient"]:
        isf_map[pp["patient_id"]] = pp

    cr_map = {}
    for pp in cr_data["per_patient"]:
        cr_map[pp["patient_id"]] = pp

    egp_map = {}
    for pp in egp_data["per_patient"]:
        egp_map[pp["patient_id"]] = pp

    return grid, isf_map, cr_map, egp_map


def build_settings(pid, isf_map, cr_map, egp_map, pg, mode="profile"):
    """Build TherapySettings for a given mode."""
    profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50.0
    profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10.0
    profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

    if mode == "profile":
        return TherapySettings(isf=profile_isf, cr=profile_cr,
                                basal_rate=profile_basal, dia_hours=DIA_HOURS)

    # ISF correction
    isf_info = isf_map.get(pid, {})
    cf = isf_info.get("correction_factor", 1.0)
    corrected_isf = np.clip(profile_isf / cf, 5, 200)

    if mode == "isf_only":
        return TherapySettings(isf=corrected_isf, cr=profile_cr,
                                basal_rate=profile_basal, dia_hours=DIA_HOURS)

    # CR correction — use compensated CR with safety clamp
    cr_info = cr_map.get(pid, {})
    compensated_cr = cr_info.get("compensated_cr", profile_cr)
    if compensated_cr is None or compensated_cr <= 0:
        compensated_cr = profile_cr
    # Safety: don't reduce CR below 70% of profile (avoid hypos)
    compensated_cr = max(compensated_cr, profile_cr * 0.7)
    compensated_cr = np.clip(compensated_cr, 2, 50)

    # EGP ISF adjustment
    egp_info = egp_map.get(pid, {})
    egp_adjusted_isf = egp_info.get("adjusted_isf", corrected_isf)
    if egp_adjusted_isf and egp_adjusted_isf > 0:
        final_isf = np.clip(egp_adjusted_isf, 5, 200)
    else:
        final_isf = corrected_isf

    return TherapySettings(isf=final_isf, cr=compensated_cr,
                            basal_rate=profile_basal, dia_hours=DIA_HOURS)


def extract_episodes(pg, ep_type="correction"):
    """Extract episodes from patient data."""
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    carbs = pg["carbs"].values
    episodes = []
    last = -MIN_SPACING - 1

    for i in range(len(pg) - max(CORRECTION_HORIZON, MEAL_HORIZON)):
        if i - last < MIN_SPACING:
            continue

        if ep_type == "correction":
            if glucose[i] < MIN_BG_CORRECTION or bolus[i] <= 0:
                continue
            horizon = CORRECTION_HORIZON
        else:  # meal
            if carbs[i] < MIN_CARBS:
                continue
            horizon = MEAL_HORIZON

        traj = glucose[i:i + horizon + 1]
        if np.isnan(traj).sum() > horizon * 0.3:
            continue

        episodes.append({
            "idx": i,
            "bg0": float(glucose[i]),
            "bolus": float(bolus[i]),
            "carbs": float(np.nansum(carbs[i:i + 24])) if ep_type == "meal" else 0,
            "type": ep_type,
            "horizon": horizon,
            "trajectory": [float(v) if not np.isnan(v) else None for v in traj],
        })
        last = i
        if len(episodes) >= MAX_EPISODES:
            break
    return episodes


def evaluate_patient(pid, grid, isf_map, cr_map, egp_map):
    """Evaluate all settings modes for one patient."""
    pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
    if len(pg) < MEAL_HORIZON + 10:
        return None

    correction_eps = extract_episodes(pg, "correction")
    meal_eps = extract_episodes(pg, "meal")
    all_eps = correction_eps + meal_eps

    if len(all_eps) < 3:
        return None

    profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

    results = {}
    for mode in ["profile", "isf_only", "integrated"]:
        settings = build_settings(pid, isf_map, cr_map, egp_map, pg, mode)
        maes, tbrs, tirs = [], [], []

        for ep in all_eps:
            bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
            carb_events = [CarbEvent(0, ep["carbs"])] if ep["carbs"] > 0 else []
            duration = ep["horizon"] * 5 / 60  # hours

            try:
                result = forward_simulate(
                    initial_glucose=ep["bg0"], settings=settings,
                    duration_hours=duration, start_hour=12,
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
                    tirs.append(float(np.sum((sim[:n] >= 70) & (sim[:n] <= 180))) / n)
            except Exception:
                pass

        if maes:
            results[mode] = {
                "mae": float(np.mean(maes)),
                "tbr": float(np.mean(tbrs)),
                "tir": float(np.mean(tirs)),
                "n": len(maes),
            }

    if len(results) < 2:
        return None

    return {
        "patient_id": pid,
        "n_correction": len(correction_eps),
        "n_meal": len(meal_eps),
        **{f"{mode}_{metric}": results.get(mode, {}).get(metric, 999)
           for mode in ["profile", "isf_only", "integrated"]
           for metric in ["mae", "tbr", "tir"]},
    }


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid, isf_map, cr_map, egp_map = load_all()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    results = []
    for pid in patients:
        r = evaluate_patient(pid, grid, isf_map, cr_map, egp_map)
        if r:
            results.append(r)
            print(f"  {str(pid)[:12]:<14} "
                  f"prof={r['profile_mae']:>5.1f} "
                  f"isf={r['isf_only_mae']:>5.1f} "
                  f"intg={r['integrated_mae']:>5.1f} "
                  f"tbr={r['integrated_tbr']:.3f} "
                  f"tir={r['integrated_tir']:.2f}")

    rdf = pd.DataFrame(results)
    n = len(rdf)

    print(f"\n{'=' * 60}")
    print(f"  RESULTS SUMMARY (N={n})")
    print(f"{'=' * 60}")

    for metric in ["mae", "tbr", "tir"]:
        print(f"\n  {metric.upper()}:")
        for mode in ["profile", "isf_only", "integrated"]:
            col = f"{mode}_{metric}"
            print(f"    {mode:<12} median={rdf[col].median():.1f} "
                  f"mean={rdf[col].mean():.1f}")

    # Hypotheses
    # H1: Integrated beats profile >60%
    h1_count = (rdf["integrated_mae"] < rdf["profile_mae"]).sum()
    h1 = h1_count > n * 0.6

    # H2: Integrated beats ISF-only >40%
    h2_count = (rdf["integrated_mae"] < rdf["isf_only_mae"]).sum()
    h2 = h2_count > n * 0.4

    # H3: TBR safety
    t, p = stats.ttest_rel(rdf["integrated_tbr"], rdf["profile_tbr"])
    h3 = p > 0.05 or t < 0  # not significantly worse

    # H4: TIR improves >50%
    h4_count = (rdf["integrated_tir"] > rdf["profile_tir"]).sum()
    h4 = h4_count > n * 0.5

    # H5: MAE improvement >15%
    pct_improvement = ((rdf["profile_mae"] - rdf["integrated_mae"]) / rdf["profile_mae"] * 100)
    h5 = pct_improvement.median() > 15

    hypotheses = {
        "H1_beats_profile_60pct": bool(h1),
        "H2_beats_isf_only_40pct": bool(h2),
        "H3_tbr_safety": bool(h3),
        "H4_tir_improves_50pct": bool(h4),
        "H5_mae_improvement_gt15pct": bool(h5),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    print(f"\n  Integrated beats profile: {h1_count}/{n}")
    print(f"  Integrated beats ISF-only: {h2_count}/{n}")
    print(f"  TBR safety p-value: {p:.3f}")
    print(f"  TIR improves: {h4_count}/{n}")
    print(f"  Median MAE improvement: {pct_improvement.median():.1f}%")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Beats profile: {h1_count}/{n} ({pct_improvement.median():.1f}% improvement). "
               f"Beats ISF-only: {h2_count}/{n}. TBR p={p:.3f}")
    print(f"\nSUMMARY: {summary}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / f"exp-{EXP_ID}_integrated_pipeline.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": EXP_ID, "title": TITLE,
            "hypotheses": hypotheses,
            "per_patient": rdf.to_dict(orient="records"),
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out}")

    create_dashboard(rdf, hypotheses, pct_improvement)


def create_dashboard(rdf, hypotheses, pct_improvement):
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

    # Panel 1: MAE comparison
    ax1 = fig.add_subplot(gs[0, 0])
    x = np.arange(len(rdf))
    w = 0.25
    ax1.bar(x - w, rdf["profile_mae"], w, label="Profile", color="gray", alpha=0.7)
    ax1.bar(x, rdf["isf_only_mae"], w, label="ISF-only", color="steelblue", alpha=0.7)
    ax1.bar(x + w, rdf["integrated_mae"], w, label="Integrated", color="coral", alpha=0.7)
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(p)[:6] for p in rdf["patient_id"]], rotation=45, fontsize=6)
    ax1.set_ylabel("MAE (mg/dL)")
    ax1.set_title("MAE by Pipeline Stage")
    ax1.legend(fontsize=7)

    # Panel 2: Improvement %
    ax2 = fig.add_subplot(gs[0, 1])
    colors = ["green" if v > 0 else "red" for v in pct_improvement]
    ax2.bar(x, pct_improvement, color=colors, alpha=0.7)
    ax2.axhline(0, color="black", lw=0.5)
    ax2.axhline(15, color="blue", ls="--", lw=1, label="15% target")
    ax2.set_ylabel("MAE Improvement (%)")
    ax2.set_title("MAE Improvement vs Profile")
    ax2.legend(fontsize=8)

    # Panel 3: TBR safety
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(rdf["profile_tbr"] * 100, rdf["integrated_tbr"] * 100,
                c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_tbr"].max(), rdf["integrated_tbr"].max()) * 110
    ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Profile TBR (%)")
    ax3.set_ylabel("Integrated TBR (%)")
    ax3.set_title("TBR Safety Check")

    # Panel 4: TIR comparison
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.scatter(rdf["profile_tir"] * 100, rdf["integrated_tir"] * 100,
                c="steelblue", s=60, alpha=0.7)
    ax4.plot([0, 100], [0, 100], "r--", lw=1)
    ax4.set_xlabel("Profile TIR (%)")
    ax4.set_ylabel("Integrated TIR (%)")
    ax4.set_title("Time-in-Range: Profile vs Integrated")

    # Panel 5: Pipeline stage comparison
    ax5 = fig.add_subplot(gs[1, 1])
    stages = ["Profile", "ISF-only", "Integrated"]
    medians = [rdf["profile_mae"].median(), rdf["isf_only_mae"].median(),
               rdf["integrated_mae"].median()]
    ax5.bar(stages, medians, color=["gray", "steelblue", "coral"], alpha=0.7)
    ax5.set_ylabel("Median MAE (mg/dL)")
    ax5.set_title("Pipeline Progression")

    # Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", "",
             f"Patients: {len(rdf)}",
             f"Median MAE: profile={medians[0]:.1f} → integrated={medians[2]:.1f}",
             f"Improvement: {pct_improvement.median():.1f}%",
             "", "Hypotheses:"]
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")
    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=10, va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / f'exp-{EXP_ID}-dashboard.png'}")


if __name__ == "__main__":
    main()
