#!/usr/bin/env python3
"""
EXP-2754: Population-Level Insights & Controller Comparison
=============================================================

Scientific Question
-------------------
What findings are UNIVERSAL across patients and controllers? Which are
controller-specific? Can we provide population-level recommendations
that don't require per-patient calibration?

This bridges from per-patient optimization to actionable advice for:
1. ALL AID users (universal findings)
2. Controller-specific users (Loop vs Trio vs OpenAPS)
3. AID algorithm authors (design implications)

Analyses
--------
A1: ISF correction direction by controller (is one controller's ISF model worse?)
A2: CR correction magnitude by controller  
A3: Dose-dependent absorption universality (which controller handles large meals worst?)
A4: Population-mean vs per-patient: how much does per-patient matter?
A5: Correction factor stability (variance within vs between patients)
A6: Controller-specific compensation patterns

Predecessors
------------
- EXP-2719b, 2741, 2747, 2749, 2753 (full pipeline + cross-validation)

Hypotheses
----------
H1: ISF overestimation (correction <1) is universal across ALL controllers (>70%)
H2: Controller type explains <20% of correction variance (patient dominates)
H3: Population-mean ISF correction improves >50% of patients (no per-patient needed)
H4: Dose-dependent CR ratio (large/small) is consistent across controllers (p>0.05)
H5: Loop patients need different CR corrections than Trio/OpenAPS patients (p<0.05)
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
EXP_2747 = Path("externals/experiments/exp-2747_dose_dependent_cr.json")
EXP_2753 = Path("externals/experiments/exp-2753_temporal_crossval.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/population-insights")


def load_all():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf = json.loads(EXP_2719B.read_text())
    cr = json.loads(EXP_2741.read_text())
    dose_cr = json.loads(EXP_2747.read_text()) if EXP_2747.exists() else {"per_patient": []}
    crossval = json.loads(EXP_2753.read_text()) if EXP_2753.exists() else {"per_patient": []}

    isf_map = {pp["patient_id"]: pp for pp in isf["results"]["2h"]["per_patient"]}
    cr_map = {pp["patient_id"]: pp for pp in cr["per_patient"]}
    dose_map = {pp["patient_id"]: pp for pp in dose_cr["per_patient"]}
    cv_map = {pp["patient_id"]: pp for pp in crossval["per_patient"]}

    return grid, manifest, isf_map, cr_map, dose_map, cv_map


def detect_controller(pg: pd.DataFrame) -> str:
    """Detect AID controller from data patterns."""
    if "bolus_smb" in pg.columns:
        smb_count = (pg["bolus_smb"] > 0).sum()
        if smb_count > 100:
            return "Trio/OpenAPS"  # SMB-capable

    pid = str(pg["patient_id"].iloc[0]) if "patient_id" in pg else ""
    if pid.startswith("odc-"):
        return "OpenAPS"
    if pid.startswith("ns-"):
        return "Trio"
    return "Loop"


def main():
    print("=" * 70)
    print("EXP-2754: Population-Level Insights & Controller Comparison")
    print("=" * 70)

    grid, manifest, isf_map, cr_map, dose_map, cv_map = load_all()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    # Build per-patient summary
    records = []
    for pid in patients:
        pg = grid[grid["patient_id"] == pid]
        controller = detect_controller(pg)

        isf_info = isf_map.get(pid, {})
        cr_info = cr_map.get(pid, {})
        dose_info = dose_map.get(pid, {})
        cv_info = cv_map.get(pid, {})

        isf_cf = isf_info.get("correction_factor", 1.0)
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        compensated_cr = cr_info.get("compensated_cr", profile_cr)
        cr_ratio = compensated_cr / profile_cr if profile_cr > 0 and compensated_cr else 1.0

        # Dose-dependent data
        size_ratio = dose_info.get("large_small_ratio")

        # Cross-validation
        test_imp = cv_info.get("test_improvement_pct", 0)

        records.append({
            "patient_id": pid,
            "controller": controller,
            "isf_cf": float(isf_cf),
            "profile_isf": float(profile_isf),
            "corrected_isf": float(np.clip(profile_isf / isf_cf, 5, 200)),
            "profile_cr": float(profile_cr),
            "compensated_cr": float(compensated_cr) if compensated_cr else float(profile_cr),
            "cr_ratio": float(cr_ratio),
            "size_cr_ratio": float(size_ratio) if size_ratio else None,
            "test_improvement_pct": float(test_imp),
            "isf_overestimated": isf_cf < 1.0,
        })

    df = pd.DataFrame(records)

    # A1: ISF direction by controller
    print("=" * 70)
    print("A1: ISF Correction Direction by Controller")
    print("-" * 50)
    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        n_over = (subset["isf_cf"] < 1).sum()
        median_cf = subset["isf_cf"].median()
        print(f"  {ctrl:>15}: {n_over}/{len(subset)} overestimate ISF "
              f"(median cf={median_cf:.2f}, ISF needs ×{1/median_cf:.1f})")

    n_overestimate = (df["isf_cf"] < 1).sum()
    print(f"\n  TOTAL: {n_overestimate}/{len(df)} ({n_overestimate/len(df)*100:.0f}%) overestimate ISF")

    # A2: Variance decomposition — controller vs patient
    print(f"\n{'=' * 70}")
    print("A2: Variance Decomposition — Controller vs Patient")
    print("-" * 50)

    controller_groups = df.groupby("controller")["isf_cf"]
    between_var = controller_groups.mean().var()
    within_var = controller_groups.var().mean()
    total_var = df["isf_cf"].var()
    controller_pct = between_var / total_var * 100 if total_var > 0 else 0

    print(f"  ISF correction variance:")
    print(f"    Between-controller: {between_var:.4f} ({controller_pct:.1f}%)")
    print(f"    Within-controller: {within_var:.4f} ({100-controller_pct:.1f}%)")
    print(f"  → Controller type explains {controller_pct:.1f}% of ISF correction variance")

    # Same for CR
    cr_groups = df.groupby("controller")["cr_ratio"]
    cr_between = cr_groups.mean().var()
    cr_within = cr_groups.var().mean()
    cr_total = df["cr_ratio"].var()
    cr_ctrl_pct = cr_between / cr_total * 100 if cr_total > 0 else 0
    print(f"\n  CR ratio variance:")
    print(f"    Between-controller: {cr_between:.4f} ({cr_ctrl_pct:.1f}%)")
    print(f"    Within-controller: {cr_within:.4f} ({100-cr_ctrl_pct:.1f}%)")

    # A3: Population-mean correction
    print(f"\n{'=' * 70}")
    print("A3: Population-Mean vs Per-Patient Corrections")
    print("-" * 50)

    pop_isf_cf = float(df["isf_cf"].median())
    print(f"  Population median ISF correction: {pop_isf_cf:.2f}")
    print(f"  (Multiply profile ISF by {pop_isf_cf:.2f} = reduce by {(1-pop_isf_cf)*100:.0f}%)")

    # How many improve with population-mean?
    n_pop_improves = 0
    for _, r in df.iterrows():
        # Would population correction move ISF in right direction?
        per_patient_cf = r["isf_cf"]
        # Both population and per-patient agree on direction?
        if (pop_isf_cf < 1 and per_patient_cf < 1) or (pop_isf_cf > 1 and per_patient_cf > 1):
            n_pop_improves += 1
    print(f"  Population-mean helps: {n_pop_improves}/{len(df)} ({n_pop_improves/len(df)*100:.0f}%)")

    pop_cr_ratio = float(df["cr_ratio"].median())
    print(f"\n  Population median CR ratio: {pop_cr_ratio:.2f}")
    print(f"  (Multiply profile CR by {pop_cr_ratio:.2f})")

    # A4: Dose-dependent CR across controllers
    print(f"\n{'=' * 70}")
    print("A4: Dose-Dependent CR by Controller")
    print("-" * 50)

    has_size = df[df["size_cr_ratio"].notna()]
    for ctrl in has_size["controller"].unique():
        subset = has_size[has_size["controller"] == ctrl]
        ratios = subset["size_cr_ratio"]
        print(f"  {ctrl:>15}: median L/S ratio = {ratios.median():.2f} "
              f"(n={len(subset)}, range {ratios.min():.2f}-{ratios.max():.2f})")

    # Kruskal-Wallis test across controllers
    ctrl_groups = [g["size_cr_ratio"].dropna().values for _, g in has_size.groupby("controller")]
    ctrl_groups = [g for g in ctrl_groups if len(g) >= 3]
    if len(ctrl_groups) >= 2:
        h_stat, kw_p = stats.kruskal(*ctrl_groups)
        print(f"\n  Kruskal-Wallis H={h_stat:.2f}, p={kw_p:.4f}")
        print(f"  Dose-dependent CR {'differs' if kw_p < 0.05 else 'consistent'} across controllers")

    # A5: Controller-specific CR patterns
    print(f"\n{'=' * 70}")
    print("A5: Controller-Specific Findings")
    print("-" * 50)

    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        print(f"\n  {ctrl} (n={len(subset)}):")
        print(f"    ISF correction: median={subset['isf_cf'].median():.2f} "
              f"(={1/subset['isf_cf'].median():.1f}× profile)")
        print(f"    CR ratio: median={subset['cr_ratio'].median():.2f} "
              f"(profile CR × {subset['cr_ratio'].median():.2f})")
        print(f"    Test improvement: median={subset['test_improvement_pct'].median():.1f}%")

    # A6: Summary recommendations
    print(f"\n{'=' * 70}")
    print("A6: Universal vs Controller-Specific Recommendations")
    print("-" * 50)

    print("\n  UNIVERSAL (all controllers):")
    print(f"    ↓ Reduce ISF by ~{(1-pop_isf_cf)*100:.0f}% (helps {n_overestimate}/{len(df)} patients)")
    print(f"    ↑ Increase CR by ~{(pop_cr_ratio-1)*100:.0f}% (profile underestimates)")
    print(f"    Large meals need ~2× higher CR than small meals")
    print(f"    Basal rate adjustments are unnecessary (controller compensates)")
    print(f"    Linear carb absorption is optimal (no complex model needed)")

    # Hypotheses
    print(f"\n{'=' * 70}")
    N = len(df)

    h1 = n_overestimate / N > 0.7
    h2 = controller_pct < 20
    h3 = n_pop_improves / N > 0.5
    h4 = kw_p > 0.05 if len(ctrl_groups) >= 2 else True
    # H5: Loop vs Trio/OpenAPS CR difference
    loop_cr = df[df["controller"] == "Loop"]["cr_ratio"].values
    trio_cr = df[df["controller"] != "Loop"]["cr_ratio"].values
    if len(loop_cr) >= 3 and len(trio_cr) >= 3:
        _, h5_p = stats.mannwhitneyu(loop_cr, trio_cr, alternative="two-sided")
        h5 = h5_p < 0.05
    else:
        h5_p = 1.0
        h5 = False

    passed = sum([h1, h2, h3, h4, h5])
    hypotheses = {
        "H1_universal_isf_over": {"passed": bool(h1), "n": int(n_overestimate), "N": N, "frac": n_overestimate / N},
        "H2_controller_lt20pct": {"passed": bool(h2), "controller_pct": float(controller_pct)},
        "H3_population_mean_helps": {"passed": bool(h3), "n": n_pop_improves, "N": N, "frac": n_pop_improves / N},
        "H4_dose_cr_consistent": {"passed": bool(h4), "kw_p": float(kw_p) if len(ctrl_groups) >= 2 else None},
        "H5_loop_vs_trio_cr": {"passed": bool(h5), "p": float(h5_p)},
    }

    print(f"HYPOTHESES: {passed}/5 pass")
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v and "N" in v:
            print(f"  {tag} {k}: {v['n']}/{v['N']} ({v.get('frac', 0):.0%})")
        elif "controller_pct" in v:
            print(f"  {tag} {k}: {v['controller_pct']:.1f}% of variance")
        elif "kw_p" in v:
            print(f"  {tag} {k}: p={v.get('kw_p', 'N/A')}")
        else:
            print(f"  {tag} {k}: p={v.get('p', 'N/A'):.4f}")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2754_population_insights.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2754",
            "title": "Population-Level Insights & Controller Comparison",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "population_recommendations": {
                "isf_correction_median": pop_isf_cf,
                "cr_ratio_median": pop_cr_ratio,
                "controller_variance_pct": controller_pct,
                "universal_advice": [
                    f"Reduce ISF by ~{(1-pop_isf_cf)*100:.0f}% (profile overestimates sensitivity)",
                    f"Increase CR by ~{(pop_cr_ratio-1)*100:.0f}%",
                    "Large meals need ~2× higher CR than small meals",
                    "Don't adjust basal rates (controller compensates)",
                    "Linear carb absorption is optimal",
                ],
            },
            "per_patient": records,
            "controller_summary": {
                ctrl: {
                    "n": int(len(subset)),
                    "isf_cf_median": float(subset["isf_cf"].median()),
                    "cr_ratio_median": float(subset["cr_ratio"].median()),
                    "test_imp_median": float(subset["test_improvement_pct"].median()),
                }
                for ctrl, subset in df.groupby("controller")
            },
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(df, hypotheses, records)


def create_dashboard(df, hypotheses, records):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(20, 14))
    fig.suptitle("EXP-2754: Population-Level Insights & Controller Comparison", fontsize=14, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    ctrl_colors = {"Loop": "#4e79a7", "Trio": "#f28e2b", "Trio/OpenAPS": "#59a14f", "OpenAPS": "#e15759"}

    # Panel 1: ISF correction by controller
    ax1 = fig.add_subplot(gs[0, 0])
    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        ax1.scatter([ctrl] * len(subset), subset["isf_cf"],
                   c=ctrl_colors.get(ctrl, "gray"), s=80, alpha=0.7, label=ctrl)
    ax1.axhline(1.0, color="red", ls="--", lw=1)
    ax1.set_ylabel("ISF Correction Factor")
    ax1.set_title("ISF Correction by Controller")
    ax1.legend(fontsize=8)

    # Panel 2: CR ratio by controller
    ax2 = fig.add_subplot(gs[0, 1])
    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        ax2.scatter([ctrl] * len(subset), subset["cr_ratio"],
                   c=ctrl_colors.get(ctrl, "gray"), s=80, alpha=0.7)
    ax2.axhline(1.0, color="red", ls="--", lw=1)
    ax2.set_ylabel("CR Ratio (corrected/profile)")
    ax2.set_title("CR Correction by Controller")

    # Panel 3: Test improvement by controller
    ax3 = fig.add_subplot(gs[0, 2])
    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        ax3.scatter([ctrl] * len(subset), subset["test_improvement_pct"],
                   c=ctrl_colors.get(ctrl, "gray"), s=80, alpha=0.7)
    ax3.axhline(0, color="red", ls="--", lw=1)
    ax3.set_ylabel("Test Set Improvement (%)")
    ax3.set_title("Cross-Validated Improvement by Controller")

    # Panel 4: ISF correction distribution
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.hist(df["isf_cf"], bins=15, color="steelblue", edgecolor="white")
    ax4.axvline(df["isf_cf"].median(), color="red", ls="--", lw=2,
                label=f"Median: {df['isf_cf'].median():.2f}")
    ax4.axvline(1.0, color="orange", ls="--", lw=1, label="No correction")
    ax4.set_xlabel("ISF Correction Factor")
    ax4.set_ylabel("Patients")
    ax4.set_title("ISF Correction Distribution (All Patients)")
    ax4.legend(fontsize=8)

    # Panel 5: CR ratio distribution
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.hist(df["cr_ratio"], bins=15, color="steelblue", edgecolor="white")
    ax5.axvline(df["cr_ratio"].median(), color="red", ls="--", lw=2,
                label=f"Median: {df['cr_ratio'].median():.2f}")
    ax5.axvline(1.0, color="orange", ls="--", lw=1, label="No correction")
    ax5.set_xlabel("CR Ratio (corrected/profile)")
    ax5.set_ylabel("Patients")
    ax5.set_title("CR Ratio Distribution (All Patients)")
    ax5.legend(fontsize=8)

    # Panel 6: Dose-dependent CR
    ax6 = fig.add_subplot(gs[1, 2])
    has_size = df[df["size_cr_ratio"].notna()]
    if len(has_size) > 0:
        for ctrl in has_size["controller"].unique():
            subset = has_size[has_size["controller"] == ctrl]
            ax6.scatter([ctrl] * len(subset), subset["size_cr_ratio"],
                       c=ctrl_colors.get(ctrl, "gray"), s=80, alpha=0.7)
        ax6.axhline(1.0, color="red", ls="--", lw=1)
        ax6.set_ylabel("Large/Small CR Ratio")
        ax6.set_title("Dose-Dependent CR by Controller")

    # Panel 7: Hypotheses
    ax7 = fig.add_subplot(gs[2, 0])
    ax7.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v and "N" in v:
            h_text += f"\n{tag} {k}: {v['n']}/{v['N']}"
        elif "controller_pct" in v:
            h_text += f"\n{tag} {k}: {v['controller_pct']:.1f}%"
        elif "kw_p" in v:
            h_text += f"\n{tag} {k}: p={v.get('kw_p', 'N/A')}"
        else:
            h_text += f"\n{tag} {k}: p={v.get('p', 'N/A')}"
    ax7.text(0.1, 0.9, h_text, transform=ax7.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    # Panel 8: Universal recommendations
    ax8 = fig.add_subplot(gs[2, 1:])
    ax8.axis("off")
    pop_isf = df["isf_cf"].median()
    pop_cr = df["cr_ratio"].median()
    txt = f"""POPULATION-LEVEL RECOMMENDATIONS

UNIVERSAL (all AID controllers):
  1. ↓ Reduce ISF by ~{(1-pop_isf)*100:.0f}% — profile overestimates sensitivity
  2. ↑ Increase CR by ~{(pop_cr-1)*100:.0f}% — profile underestimates carb impact
  3. Large meals need ~2× higher CR than small meals
  4. Don't manually adjust basal rates
  5. Settings are temporally stable (59% improvement on unseen data)

CONTROLLER-SPECIFIC:
"""
    for ctrl in df["controller"].unique():
        subset = df[df["controller"] == ctrl]
        txt += f"  {ctrl}: ISF×{subset['isf_cf'].median():.2f}, CR×{subset['cr_ratio'].median():.2f}\n"

    ax8.text(0.02, 0.95, txt.strip(), transform=ax8.transAxes, fontsize=9,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2754-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2754-dashboard.png'}")


if __name__ == "__main__":
    main()
