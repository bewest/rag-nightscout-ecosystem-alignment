#!/usr/bin/env python3
"""
Production Settings Report v3
===============================

Final pipeline report incorporating all validated components:

- ISF corrections: EXP-2719b (waterfall residuals)
- CR corrections: EXP-2741 (bilateral meal deconfounding)
- CR size-stratified: EXP-2747 (dose-dependent, optional)
- EGP personalization: EXP-2742 (per-patient EGP)
- Basal: NOT recommended (EXP-2745)
- Absorption: Linear is optimal (EXP-2752 — 14/22 best)
- Residuals: 40min memory from controller dynamics (EXP-2751 — not fixable)

Pipeline performance (EXP-2749):
- 17/22 patients improve over profile (77%)
- Median MAE: 43.3 → 36.9 mg/dL (7.7% improvement)
- Safety maintained (TBR p=1.0)

New in v3:
- Meal-size-dependent CR recommendations for variable-meal patients
- Absorption dynamics insights (peak/gram decreases with meal size)
- Pipeline completeness assessment (EXP-2751/2752 confirm near-complete)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2741 = Path("externals/experiments/exp-2741_cr_compensated.json")
EXP_2742 = Path("externals/experiments/exp-2742_egp_personalized_isf.json")
EXP_2747 = Path("externals/experiments/exp-2747_dose_dependent_cr.json")
EXP_2749 = Path("externals/experiments/exp-2749_enhanced_pipeline.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/production-report-v3")


def load_all():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf = json.loads(EXP_2719B.read_text())
    cr = json.loads(EXP_2741.read_text())
    egp = json.loads(EXP_2742.read_text())
    szcr = json.loads(EXP_2747.read_text()) if EXP_2747.exists() else {"per_patient": []}
    pipe = json.loads(EXP_2749.read_text()) if EXP_2749.exists() else {"per_patient": []}

    isf_map = {pp["patient_id"]: pp for pp in isf["results"]["2h"]["per_patient"]}
    cr_map = {pp["patient_id"]: pp for pp in cr["per_patient"]}
    egp_map = {pp["patient_id"]: pp for pp in egp["per_patient"]}
    szcr_map = {pp["patient_id"]: pp for pp in szcr["per_patient"]}
    pipe_map = {pp["patient_id"]: pp for pp in pipe["per_patient"]}

    return grid, isf_map, cr_map, egp_map, szcr_map, pipe_map


def categorize_patient(isf_cf, cr_ratio, mae_improvement_pct, has_size_cr_benefit):
    actions = []
    confidence = "HIGH"

    if isf_cf > 1.2:
        actions.append("REDUCE_ISF")
    elif isf_cf < 0.8:
        actions.append("INCREASE_ISF")

    if cr_ratio > 1.3:
        actions.append("INCREASE_CR")
    elif cr_ratio < 0.7:
        actions.append("REDUCE_CR")

    if has_size_cr_benefit:
        actions.append("SIZE_CR")

    if not actions:
        return "OK", "HIGH"

    if mae_improvement_pct < 5:
        confidence = "LOW"
    elif mae_improvement_pct < 15:
        confidence = "MEDIUM"

    return "+".join(actions), confidence


def main():
    print("=" * 70)
    print("  PRODUCTION SETTINGS REPORT v3")
    print("  Full Pipeline: ISF + CR + Size-CR + EGP")
    print("  Pipeline Completeness: Confirmed (EXP-2751/2752)")
    print("=" * 70)

    grid, isf_map, cr_map, egp_map, szcr_map, pipe_map = load_all()
    patients = sorted(grid["patient_id"].unique())

    report = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid]
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # ISF correction
        isf_info = isf_map.get(pid, {})
        isf_cf = isf_info.get("correction_factor", 1.0)
        corrected_isf = np.clip(profile_isf / isf_cf, 5, 200)

        # Flat CR
        cr_info = cr_map.get(pid, {})
        compensated_cr = cr_info.get("compensated_cr")
        if compensated_cr and compensated_cr > 0:
            cr_ratio = compensated_cr / profile_cr if profile_cr > 0 else 1
        else:
            compensated_cr = profile_cr
            cr_ratio = 1.0

        # Size-stratified CR
        szcr_info = szcr_map.get(pid, {})
        size_cr_small = szcr_info.get("size_cr_small")
        size_cr_large = szcr_info.get("size_cr_large")
        size_threshold = szcr_info.get("size_threshold")
        has_size_cr = bool(size_cr_small and size_cr_large and size_threshold)

        # Determine if size-CR would help
        pipe_info = pipe_map.get(pid, {})
        enh_mae = pipe_info.get("enhanced_mae") or pipe_info.get("enh_mae")
        flat_mae = pipe_info.get("flat_mae")
        has_size_cr_benefit = False
        if enh_mae and flat_mae and enh_mae < flat_mae * 0.95:
            has_size_cr_benefit = True

        # EGP
        egp_info = egp_map.get(pid, {})
        has_egp = egp_info.get("has_egp", False)
        patient_egp = egp_info.get("patient_egp")
        adjusted_isf = egp_info.get("adjusted_isf", corrected_isf)
        if adjusted_isf and adjusted_isf > 0:
            final_isf = np.clip(adjusted_isf, 5, 200)
        else:
            final_isf = corrected_isf

        # Pipeline MAE
        prof_mae = pipe_info.get("prof_mae") or pipe_info.get("profile_mae") or 999
        intg_mae = enh_mae or flat_mae or 999
        mae_improvement = ((prof_mae - intg_mae) / prof_mae * 100
                            if prof_mae < 900 and intg_mae < 900 else 0)

        category, confidence = categorize_patient(isf_cf, cr_ratio, mae_improvement, has_size_cr_benefit)

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
            "has_size_cr": has_size_cr,
            "size_cr_small": float(size_cr_small) if size_cr_small else None,
            "size_cr_large": float(size_cr_large) if size_cr_large else None,
            "size_threshold_g": float(size_threshold) if size_threshold else None,
            "has_size_cr_benefit": has_size_cr_benefit,
            "profile_basal": float(profile_basal),
            "basal_recommendation": "NO CHANGE",
            "has_egp": bool(has_egp),
            "patient_egp": float(patient_egp) if patient_egp else None,
            "profile_mae": float(prof_mae) if prof_mae < 900 else None,
            "integrated_mae": float(intg_mae) if intg_mae < 900 else None,
            "mae_improvement_pct": float(mae_improvement),
            "absorption_model": "linear",
            "pipeline_completeness": "HIGH",
        }
        report.append(entry)

    # Print
    rdf = pd.DataFrame(report)
    print(f"\n{'Patient':<14} {'Category':<28} {'Conf':>6} "
          f"{'ISF':>5}→{'':>5} {'CR':>5}→{'':>5} {'MAE%':>5} {'SzCR':>4}")
    print("-" * 100)

    for _, r in rdf.iterrows():
        print(f"{r['patient_id'][:14]:<14} {r['category']:<28} {r['confidence']:>6} "
              f"{r['profile_isf']:>5.0f}→{r['final_isf']:>5.0f} "
              f"{r['profile_cr']:>5.1f}→{r['compensated_cr']:>5.1f} "
              f"{r['mae_improvement_pct']:>+5.1f} "
              f"{'YES' if r['has_size_cr_benefit'] else '  -':>4}")

    # Summary stats
    improving = rdf[rdf["mae_improvement_pct"] > 0]
    high_conf = rdf[rdf["confidence"] == "HIGH"]
    with_szcr = rdf[rdf["has_size_cr_benefit"]]

    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"  Patients improving: {len(improving)}/{len(rdf)} ({len(improving)/len(rdf)*100:.0f}%)")
    print(f"  High confidence: {len(high_conf)}/{len(rdf)}")
    print(f"  Size-CR beneficial: {len(with_szcr)}/{len(rdf)}")
    print(f"  Median MAE improvement: {rdf['mae_improvement_pct'].median():.1f}%")

    cats = rdf["category"].value_counts()
    print(f"\n  Recommendation distribution:")
    for cat, n in cats.items():
        print(f"    {cat}: {n}")

    print(f"\n  Pipeline completeness (EXP-2751/2752):")
    print(f"    Residual autocorrelation: 40min (controller dynamics, not fixable)")
    print(f"    Absorption model: linear is optimal (no model beats it)")
    print(f"    Signal extraction: near-complete")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "settings-assessment-v3.json"
    with open(out, "w") as f:
        json.dump(clean({
            "version": "v3",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "ISF+CR+SizeCR+EGP",
            "pipeline_completeness": "HIGH (EXP-2751/2752 confirm near-complete)",
            "experiments": {
                "isf": "EXP-2719b",
                "cr": "EXP-2741",
                "size_cr": "EXP-2747",
                "egp": "EXP-2742",
                "validation": "EXP-2749",
                "absorption": "EXP-2752 (linear optimal)",
                "autocorrelation": "EXP-2751 (40min, controller)",
            },
            "summary": {
                "n_patients": len(report),
                "n_improving": int(len(improving)),
                "n_high_confidence": int(len(high_conf)),
                "n_size_cr_beneficial": int(len(with_szcr)),
                "median_mae_improvement_pct": float(rdf["mae_improvement_pct"].median()),
            },
            "per_patient": report,
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(report, rdf)


def create_dashboard(report, rdf):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(20, 14))
    fig.suptitle("Production Settings Report v3 — Full Pipeline", fontsize=16, fontweight="bold")
    gs = GridSpec(3, 4, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: ISF profile vs corrected
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(rdf["profile_isf"], rdf["final_isf"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_isf"].max(), rdf["final_isf"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", lw=1)
    ax1.set_xlabel("Profile ISF")
    ax1.set_ylabel("Optimized ISF")
    ax1.set_title("ISF: Profile vs Optimized")

    # Panel 2: CR profile vs corrected
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(rdf["profile_cr"], rdf["compensated_cr"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_cr"].max(), rdf["compensated_cr"].max()) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", lw=1)
    ax2.set_xlabel("Profile CR")
    ax2.set_ylabel("Optimized CR")
    ax2.set_title("CR: Profile vs Optimized")

    # Panel 3: MAE improvement distribution
    ax3 = fig.add_subplot(gs[0, 2])
    colors = ["#59a14f" if v > 0 else "#e15759" for v in rdf["mae_improvement_pct"]]
    ax3.barh(range(len(rdf)), rdf["mae_improvement_pct"], color=colors)
    ax3.set_yticks(range(len(rdf)))
    ax3.set_yticklabels([p[:10] for p in rdf["patient_id"]], fontsize=7)
    ax3.axvline(0, color="black", lw=0.5)
    ax3.set_xlabel("MAE Improvement (%)")
    ax3.set_title("Per-Patient Improvement")

    # Panel 4: Category distribution
    ax4 = fig.add_subplot(gs[0, 3])
    cats = rdf["category"].value_counts()
    ax4.pie(cats.values, labels=cats.index, autopct="%1.0f%%", startangle=90,
            textprops={"fontsize": 8})
    ax4.set_title("Recommendation Categories")

    # Panel 5: Confidence distribution
    ax5 = fig.add_subplot(gs[1, 0])
    confs = rdf["confidence"].value_counts()
    colors = {"HIGH": "#59a14f", "MEDIUM": "#f28e2b", "LOW": "#e15759"}
    ax5.bar(confs.index, confs.values, color=[colors.get(c, "gray") for c in confs.index])
    ax5.set_ylabel("Patients")
    ax5.set_title("Confidence Distribution")

    # Panel 6: Pipeline status summary
    ax6 = fig.add_subplot(gs[1, 1:3])
    ax6.axis("off")
    txt = """PIPELINE STATUS (v3)

Component     │ Method           │ Status      │ Performance
──────────────┼──────────────────┼─────────────┼────────────
ISF           │ Waterfall resid. │ PRODUCTION  │ 68% improve
CR (flat)     │ Bilateral deconf │ PRODUCTION  │ 73% improve
CR (size)     │ Dose-dependent   │ OPTIONAL    │ 41% improve
EGP           │ Per-patient      │ PRODUCTION  │ 55% improve
Basal         │ Fasting drift    │ NOT USED    │ 1/22
Absorption    │ Linear (best)    │ CONFIRMED   │ 14/22 best
Residuals     │ Controller ACF   │ IRREDUCIBLE │ 40min memory

Pipeline completeness: HIGH
Remaining autocorrelation is from controller dynamics (correct behavior).
No additional physics-based factors can reduce residuals further.
"""
    ax6.text(0.02, 0.95, txt.strip(), transform=ax6.transAxes, fontsize=8,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    # Panel 7: ISF correction direction
    ax7 = fig.add_subplot(gs[1, 3])
    reduce = sum(1 for _, r in rdf.iterrows() if "REDUCE_ISF" in r["category"])
    increase = sum(1 for _, r in rdf.iterrows() if "INCREASE_ISF" in r["category"])
    ok = len(rdf) - reduce - increase
    ax7.bar(["↓ Reduce", "OK", "↑ Increase"], [reduce, ok, increase],
            color=["#e15759", "#59a14f", "#4e79a7"])
    ax7.set_ylabel("Patients")
    ax7.set_title("ISF Direction")

    # Panel 8: Key findings
    ax8 = fig.add_subplot(gs[2, :])
    ax8.axis("off")
    findings = """KEY FINDINGS & RECOMMENDATIONS FOR AID AUTHORS

1. ISF Settings: Most patients (68%) have ISF set too high — profile overestimates insulin sensitivity.
   → AID systems should suggest ISF reduction when TIR is suboptimal.

2. CR Settings: Bilateral deconfounding reveals true CR after subtracting controller basal suspension.
   → 73% of patients improve with corrected CR.

3. Large Meal Absorption: Peak per gram = 1.81 mg/dL/g for large meals vs 2.99 for small (EXP-2750).
   → Carb absorption models should be meal-size-dependent. Current linear models overpredict large-meal peaks.

4. Basal Rates: Controller temp basals dominate fasting behavior. Adjusting scheduled basal makes no difference.
   → Basal optimization is the controller's job, not the patient's.

5. Pipeline Completeness: Residual autocorrelation (40min) comes from controller response dynamics, not model gaps.
   → No additional deconfounding factors will improve predictions. Pipeline is near-complete.

6. AID Controller Compensation: The controller masks most setting errors. Only bilateral deconfounding
   (subtracting both supply AND demand sides) reveals true underlying settings.
"""
    ax8.text(0.01, 0.95, findings.strip(), transform=ax8.transAxes, fontsize=8.5,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "production-report-v3-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'production-report-v3-dashboard.png'}")


if __name__ == "__main__":
    main()
