#!/usr/bin/env python3
"""
Production Settings Report v2
===============================

Combines all validated pipeline components into a final per-patient
settings assessment:

- ISF corrections: EXP-2719b (waterfall residuals) — validated EXP-2739
- CR corrections: EXP-2741 (bilateral meal deconfounding) — validated EXP-2743
- EGP personalization: EXP-2742 (per-patient EGP) — validated EXP-2743
- Basal: NOT recommended (EXP-2745: fasting drift reflects controller, not patient)

Pipeline performance (EXP-2743):
- 14/22 patients improve over profile (64%)
- Median MAE: 81.6 → 58.8 mg/dL (28% improvement)
- 18/22 patients improve TIR (82%)
- Safety maintained (TBR not significantly worse)

Output: JSON report + dashboard visualization
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2741 = Path("externals/experiments/exp-2741_cr_compensated.json")
EXP_2742 = Path("externals/experiments/exp-2742_egp_personalized_isf.json")
EXP_2743 = Path("externals/experiments/exp-2743_integrated_pipeline.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/production-report-v2")


def load_all():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf = json.loads(EXP_2719B.read_text())
    cr = json.loads(EXP_2741.read_text())
    egp = json.loads(EXP_2742.read_text())
    pipeline = json.loads(EXP_2743.read_text())

    isf_map = {pp["patient_id"]: pp for pp in isf["results"]["2h"]["per_patient"]}
    cr_map = {pp["patient_id"]: pp for pp in cr["per_patient"]}
    egp_map = {pp["patient_id"]: pp for pp in egp["per_patient"]}
    pipe_map = {pp["patient_id"]: pp for pp in pipeline["per_patient"]}

    return grid, isf_map, cr_map, egp_map, pipe_map


def categorize_patient(isf_cf, cr_ratio, mae_improvement_pct):
    """Categorize patient recommendation."""
    actions = []
    confidence = "HIGH"

    # ISF
    if isf_cf > 1.2:
        actions.append("REDUCE_ISF")
    elif isf_cf < 0.8:
        actions.append("INCREASE_ISF")

    # CR
    if cr_ratio > 1.3:
        actions.append("INCREASE_CR")
    elif cr_ratio < 0.7:
        actions.append("REDUCE_CR")

    if not actions:
        return "OK", "HIGH"

    if mae_improvement_pct < 5:
        confidence = "LOW"
    elif mae_improvement_pct < 15:
        confidence = "MEDIUM"

    return "+".join(actions), confidence


def main():
    print("=" * 70)
    print("  PRODUCTION SETTINGS REPORT v2")
    print("  Integrated Pipeline: ISF + CR + EGP")
    print("=" * 70)

    grid, isf_map, cr_map, egp_map, pipe_map = load_all()
    patients = sorted(grid["patient_id"].unique())

    report = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid]
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # ISF
        isf_info = isf_map.get(pid, {})
        isf_cf = isf_info.get("correction_factor", 1.0)
        corrected_isf = np.clip(profile_isf / isf_cf, 5, 200)

        # CR
        cr_info = cr_map.get(pid, {})
        compensated_cr = cr_info.get("compensated_cr")
        if compensated_cr and compensated_cr > 0:
            cr_ratio = compensated_cr / profile_cr if profile_cr > 0 else 1
        else:
            compensated_cr = profile_cr
            cr_ratio = 1.0

        # EGP
        egp_info = egp_map.get(pid, {})
        has_egp = egp_info.get("has_egp", False)
        patient_egp = egp_info.get("patient_egp")
        adjusted_isf = egp_info.get("adjusted_isf", corrected_isf)
        if adjusted_isf and adjusted_isf > 0:
            final_isf = np.clip(adjusted_isf, 5, 200)
        else:
            final_isf = corrected_isf

        # Pipeline validation
        pipe_info = pipe_map.get(pid, {})
        prof_mae = pipe_info.get("profile_mae") or 999
        intg_mae = pipe_info.get("integrated_mae") or 999
        mae_improvement = ((prof_mae - intg_mae) / prof_mae * 100
                            if prof_mae < 900 and intg_mae < 900 else 0)

        category, confidence = categorize_patient(isf_cf, cr_ratio, mae_improvement)

        entry = {
            "patient_id": pid,
            "category": category,
            "confidence": confidence,
            "profile_isf": float(profile_isf),
            "corrected_isf": float(corrected_isf),
            "final_isf": float(final_isf),
            "isf_correction_factor": float(isf_cf),
            "profile_cr": float(profile_cr),
            "compensated_cr": float(compensated_cr),
            "cr_ratio": float(cr_ratio),
            "profile_basal": float(profile_basal),
            "basal_recommendation": "NO CHANGE (controller compensates)",
            "has_egp": bool(has_egp),
            "patient_egp": float(patient_egp) if patient_egp else None,
            "profile_mae": float(prof_mae) if prof_mae < 900 else None,
            "integrated_mae": float(intg_mae) if intg_mae < 900 else None,
            "mae_improvement_pct": float(mae_improvement),
        }
        report.append(entry)

    # Print summary
    rdf = pd.DataFrame(report)
    print(f"\n{'Patient':<14} {'Category':<20} {'Conf':>6} "
          f"{'ISF':>4}→{'Final':>5} {'CR':>4}→{'Comp':>5} "
          f"{'MAE%':>5}")
    print("-" * 75)

    for _, r in rdf.iterrows():
        print(f"{str(r['patient_id'])[:12]:<14} {r['category']:<20} {r['confidence']:>6} "
              f"{r['profile_isf']:>4.0f}→{r['final_isf']:>5.0f} "
              f"{r['profile_cr']:>4.0f}→{r['compensated_cr']:>5.0f} "
              f"{r['mae_improvement_pct']:>+5.1f}")

    # Summary stats
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    cats = rdf["category"].value_counts()
    for cat, count in cats.items():
        print(f"  {cat}: {count} patients")

    confs = rdf["confidence"].value_counts()
    print()
    for conf, count in confs.items():
        print(f"  {conf} confidence: {count} patients")

    print(f"\n  High-confidence recommendations: {(rdf['confidence'] == 'HIGH').sum()}/{len(rdf)}")
    print(f"  Patients improving: {(rdf['mae_improvement_pct'] > 0).sum()}/{len(rdf)}")
    print(f"  Median MAE improvement: {rdf['mae_improvement_pct'].median():.1f}%")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "settings-assessment-v2.json"
    with open(out, "w") as f:
        json.dump(clean({
            "version": 2,
            "pipeline": {
                "isf": "EXP-2719b waterfall residuals (validated EXP-2739, 68% improve)",
                "cr": "EXP-2741 bilateral meal deconfounding (validated EXP-2743, 73% improve)",
                "egp": "EXP-2742 per-patient EGP (validated EXP-2743, available for 11/22)",
                "basal": "NOT RECOMMENDED (EXP-2745: fasting drift = controller compensation)",
                "integrated": "EXP-2743: 64% improve, 28% median MAE reduction, 82% TIR improvement",
            },
            "patients": report,
            "summary": {
                "n_patients": len(report),
                "categories": cats.to_dict(),
                "high_confidence": int((rdf["confidence"] == "HIGH").sum()),
                "patients_improving": int((rdf["mae_improvement_pct"] > 0).sum()),
                "median_improvement_pct": float(rdf["mae_improvement_pct"].median()),
            },
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(rdf)


def create_dashboard(rdf):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle("Production Settings Report v2: Integrated Pipeline", fontsize=14, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: Category distribution
    ax1 = fig.add_subplot(gs[0, 0])
    cats = rdf["category"].value_counts()
    ax1.barh(range(len(cats)), cats.values, color="steelblue", alpha=0.7)
    ax1.set_yticks(range(len(cats)))
    ax1.set_yticklabels(cats.index, fontsize=9)
    ax1.set_xlabel("Count")
    ax1.set_title("Recommendation Categories")

    # Panel 2: ISF correction factors
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(rdf["profile_isf"], rdf["final_isf"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_isf"].max(), rdf["final_isf"].max()) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", lw=1)
    ax2.set_xlabel("Profile ISF")
    ax2.set_ylabel("Final ISF (corrected + EGP)")
    ax2.set_title("ISF: Profile vs Recommended")

    # Panel 3: CR comparison
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(rdf["profile_cr"], rdf["compensated_cr"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_cr"].max(), rdf["compensated_cr"].max()) * 1.1
    ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Profile CR")
    ax3.set_ylabel("Compensated CR")
    ax3.set_title("CR: Profile vs Recommended")

    # Panel 4: MAE improvement
    ax4 = fig.add_subplot(gs[1, 0:2])
    colors = ["green" if v > 0 else "red" for v in rdf["mae_improvement_pct"]]
    x = np.arange(len(rdf))
    ax4.bar(x, rdf["mae_improvement_pct"], color=colors, alpha=0.7)
    ax4.axhline(0, color="black", lw=0.5)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:6] for p in rdf["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE Improvement (%)")
    ax4.set_title("Per-Patient MAE Improvement")

    # Panel 5: Confidence distribution
    ax5 = fig.add_subplot(gs[1, 2])
    confs = rdf["confidence"].value_counts()
    ax5.pie(confs.values, labels=confs.index, autopct="%1.0f%%",
            colors=["green", "orange", "red"][:len(confs)], startangle=90)
    ax5.set_title("Confidence Distribution")

    # Panel 6: Pipeline status summary
    ax6 = fig.add_subplot(gs[2, :])
    ax6.axis("off")
    summary_text = """
INTEGRATED SETTINGS PIPELINE — PRODUCTION STATUS

ISF Extraction:     EXP-2719b (waterfall residuals)     → VALIDATED (EXP-2739: 68% improve, safe)
CR Extraction:      EXP-2741 (bilateral deconfounding)  → VALIDATED (EXP-2743: 73% improve)
EGP Personalization: EXP-2742 (per-patient EGP)          → VALIDATED (EXP-2743: 55% improve)
Basal Extraction:   EXP-2745 (fasting drift)            → NOT RECOMMENDED (controller compensates)

End-to-End:         EXP-2743 (integrated pipeline)      → 64% improve, 28% MAE reduction, TBR safe

Key Findings:
• ISF, CR, and basal are NOT jointly identifiable from glucose trajectories (EXP-2737)
• Waterfall approach (extract each from signal-dominant episodes) IS correct
• Controller-compensated CR fixes the 2738 disaster (deconfounded CR too aggressive)
• Per-patient EGP varies >2× and affects ISF by >10% for 73% of patients
• Fasting drift reflects controller compensation, not patient physiology (EXP-2745)
"""
    ax6.text(0.02, 0.95, summary_text.strip(), transform=ax6.transAxes,
             fontsize=9, va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "production-report-v2-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'production-report-v2-dashboard.png'}")


if __name__ == "__main__":
    main()
