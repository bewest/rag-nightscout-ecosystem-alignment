#!/usr/bin/env python3
"""
Per-Patient Settings Assessment Report Generator
=================================================

Combines validated results from the waterfall pipeline to produce
actionable settings recommendations for each patient.

Currently validated settings:
  - ISF: EXP-2719b corrections validated by EXP-2739 (68% improve, safe)
  
Not yet validated (included as informational):
  - CR: EXP-2729 deconfounded CR (needs controller compensation)
  - Basal: Profile only (EGP-aware correction pending)

Usage:
  python tools/cgmencode/generate_settings_report.py

Output:
  - Per-patient JSON report in externals/experiments/settings-assessment.json
  - Summary visualization in tools/visualizations/settings-assessment/
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2729 = Path("externals/experiments/exp-2729_carb_ratio.json")
EXP_2739 = Path("externals/experiments/exp-2739_isf_only_validation.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/settings-assessment")


def load_all_data():
    """Load and merge per-patient data from all experiments."""
    # ISF corrections (2719b)
    isf_data = {}
    d = json.loads(EXP_2719B.read_text())
    for pp in d["results"]["2h"]["per_patient"]:
        isf_data[pp["patient_id"]] = {
            "profile_isf": pp["profile_isf"],
            "correction_factor": pp["correction_factor"],
            "empirical_isf": pp["empirical_isf"],
            "direction": pp["direction"],
            "recommendation": pp["recommendation"],
            "significant": pp["significant"],
            "p_value": pp["p_value"],
        }

    # CR (2729)
    cr_data = {}
    d2 = json.loads(EXP_2729.read_text())
    for pp in d2["per_patient"]:
        cr_data[pp["patient_id"]] = {
            "profile_cr": pp["profile_cr"],
            "deconfounded_cr": pp["deconfounded_cr"],
            "observed_cr": pp.get("observed_cr_indep", pp.get("observed_cr_all")),
        }

    # Validation results (2739)
    val_data = {}
    d3 = json.loads(EXP_2739.read_text())
    for pp in d3["per_patient"]:
        val_data[pp["patient_id"]] = {
            "profile_mae": pp["profile_mae"],
            "corrected_mae": pp["corrected_mae"],
            "profile_tbr": pp["profile_tbr"],
            "corrected_tbr": pp["corrected_tbr"],
            "mae_improved": pp["corrected_mae"] < pp["profile_mae"],
        }

    return isf_data, cr_data, val_data


def categorize_patient(isf_info, val_info) -> dict:
    """Categorize patient recommendation."""
    cf = isf_info["correction_factor"]
    sig = isf_info["significant"]
    improved = val_info.get("mae_improved", False) if val_info else False
    tbr_ok = (val_info.get("corrected_tbr", 0) <= val_info.get("profile_tbr", 0) * 2 + 0.01
              if val_info else True)

    if not sig:
        return {"category": "OK", "confidence": "high",
                "action": "No ISF change needed — settings within expected range."}

    if cf > 1.1 and improved and tbr_ok:
        pct = int((1 - 1/cf) * 100)
        return {"category": "REDUCE_ISF", "confidence": "high",
                "action": f"Consider reducing ISF by ~{pct}% (ISF is likely too high → under-correcting)."}

    if cf < 0.9 and improved and tbr_ok:
        pct = int((1/cf - 1) * 100)
        return {"category": "INCREASE_ISF", "confidence": "high",
                "action": f"Consider increasing ISF by ~{pct}% (ISF is likely too low → over-correcting)."}

    if cf > 1.1 and not improved:
        return {"category": "REDUCE_ISF", "confidence": "low",
                "action": "ISF appears too high but simulation validation was inconclusive. "
                          "Consider small adjustments with monitoring."}

    if cf < 0.9 and not improved:
        return {"category": "INCREASE_ISF", "confidence": "low",
                "action": "ISF appears too low but simulation validation was inconclusive. "
                          "Consider small adjustments with monitoring."}

    return {"category": "BORDERLINE", "confidence": "medium",
            "action": "ISF correction factor is small (<10%). Monitor but no urgent change needed."}


def generate_report():
    isf_data, cr_data, val_data = load_all_data()

    all_patients = sorted(set(isf_data.keys()) | set(cr_data.keys()))
    reports = []

    print(f"{'=' * 80}")
    print(f"  PER-PATIENT SETTINGS ASSESSMENT REPORT")
    print(f"{'=' * 80}")
    print(f"\n  Pipeline: EXP-2719b (ISF extraction) → EXP-2739 (validation)")
    print(f"  Patients: {len(all_patients)}")
    print()

    for pid in all_patients:
        isf = isf_data.get(pid, {})
        cr = cr_data.get(pid, {})
        val = val_data.get(pid, {})

        if not isf:
            continue

        cat = categorize_patient(isf, val)

        corrected_isf = isf["profile_isf"] / isf["correction_factor"]
        corrected_isf = np.clip(corrected_isf, 5, 200)

        report = {
            "patient_id": pid,
            # ISF assessment (VALIDATED)
            "isf_status": "validated",
            "profile_isf": round(isf["profile_isf"], 1),
            "recommended_isf": round(float(corrected_isf), 1),
            "correction_factor": round(isf["correction_factor"], 3),
            "isf_direction": isf["direction"],
            "isf_significant": isf["significant"],
            "isf_p_value": round(isf["p_value"], 4),
            # CR assessment (INFORMATIONAL — not yet validated)
            "cr_status": "informational_only",
            "profile_cr": round(cr.get("profile_cr", 0), 1),
            "deconfounded_cr": round(cr.get("deconfounded_cr", 0), 1) if cr.get("deconfounded_cr") else None,
            "cr_note": "CR extraction not yet validated in simulation. Do NOT adjust based on this value alone.",
            # Validation metrics
            "profile_mae": round(val.get("profile_mae", 0), 1) if val else None,
            "corrected_mae": round(val.get("corrected_mae", 0), 1) if val else None,
            "mae_improved": val.get("mae_improved") if val else None,
            "profile_tbr": round(val.get("profile_tbr", 0), 4) if val else None,
            "corrected_tbr": round(val.get("corrected_tbr", 0), 4) if val else None,
            # Recommendation
            **cat,
        }
        reports.append(report)

        # Print summary line
        mae_str = ""
        if val:
            impr = (val["profile_mae"] - val["corrected_mae"]) / max(val["profile_mae"], 1) * 100
            mae_str = f"MAE {val['profile_mae']:.0f}→{val['corrected_mae']:.0f} ({impr:+.0f}%)"

        symbol = {"REDUCE_ISF": "↓", "INCREASE_ISF": "↑", "OK": "✓", "BORDERLINE": "~"}.get(cat["category"], "?")
        conf = {"high": "★★★", "medium": "★★☆", "low": "★☆☆"}.get(cat["confidence"], "")

        print(f"  {symbol} {str(pid)[:14]:<16} ISF {isf['profile_isf']:>5.0f} → {corrected_isf:>5.0f} "
              f"({isf['direction']:<14}) {conf}  {mae_str}")

    # Summary stats
    n_reduce = sum(1 for r in reports if r["category"] == "REDUCE_ISF")
    n_increase = sum(1 for r in reports if r["category"] == "INCREASE_ISF")
    n_ok = sum(1 for r in reports if r["category"] == "OK")
    n_borderline = sum(1 for r in reports if r["category"] == "BORDERLINE")
    n_high = sum(1 for r in reports if r["confidence"] == "high")

    print(f"\n{'=' * 80}")
    print(f"  SUMMARY")
    print(f"{'=' * 80}")
    print(f"  ↓ Reduce ISF:   {n_reduce}/{len(reports)}")
    print(f"  ↑ Increase ISF:  {n_increase}/{len(reports)}")
    print(f"  ✓ OK:            {n_ok}/{len(reports)}")
    print(f"  ~ Borderline:    {n_borderline}/{len(reports)}")
    print(f"  High confidence: {n_high}/{len(reports)}")

    # Save
    out_path = RESULTS_DIR / "settings-assessment.json"
    with open(out_path, "w") as f:
        json.dump({
            "title": "Per-Patient Settings Assessment",
            "pipeline": ["EXP-2719b (ISF extraction)", "EXP-2729 (CR extraction, informational)",
                         "EXP-2739 (ISF validation)"],
            "n_patients": len(reports),
            "summary": {
                "reduce_isf": n_reduce, "increase_isf": n_increase,
                "ok": n_ok, "borderline": n_borderline,
                "high_confidence": n_high,
            },
            "patients": reports,
        }, f, indent=2)
    print(f"\n  Saved: {out_path}")

    # Dashboard
    create_dashboard(reports)
    return reports


def create_dashboard(reports):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    df = pd.DataFrame(reports)

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle("Per-Patient Settings Assessment Report", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    # Panel 1: ISF profile vs recommended
    ax1 = fig.add_subplot(gs[0, 0])
    colors = {"REDUCE_ISF": "#e74c3c", "INCREASE_ISF": "#2ecc71",
              "OK": "#3498db", "BORDERLINE": "#95a5a6"}
    for _, r in df.iterrows():
        c = colors.get(r["category"], "gray")
        ax1.scatter(r["profile_isf"], r["recommended_isf"], color=c, s=80, alpha=0.7,
                    edgecolors="white", linewidth=0.5)
    lim = max(df["profile_isf"].max(), df["recommended_isf"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "k--", lw=1, alpha=0.5)
    ax1.set_xlabel("Current Profile ISF")
    ax1.set_ylabel("Recommended ISF")
    ax1.set_title("ISF: Current vs Recommended")
    # Legend
    for cat, col in colors.items():
        n = (df["category"] == cat).sum()
        ax1.scatter([], [], color=col, s=40, label=f"{cat} ({n})")
    ax1.legend(fontsize=7, loc="upper left")

    # Panel 2: Correction factor distribution
    ax2 = fig.add_subplot(gs[0, 1])
    cfs = df["correction_factor"].values
    colors_cf = ["#e74c3c" if cf > 1.1 else "#2ecc71" if cf < 0.9 else "#3498db" for cf in cfs]
    ax2.barh(range(len(df)), cfs - 1.0, color=colors_cf, alpha=0.7)
    ax2.axvline(0, color="black", lw=1)
    ax2.set_xlabel("Correction Factor − 1 (>0 = ISF too high)")
    ax2.set_ylabel("Patient")
    ax2.set_title("ISF Correction Factor")

    # Panel 3: Category pie
    ax3 = fig.add_subplot(gs[1, 0])
    cats = df["category"].value_counts()
    cat_colors = [colors.get(c, "gray") for c in cats.index]
    ax3.pie(cats.values, labels=[f"{c}\n({v})" for c, v in cats.items()],
            colors=cat_colors, autopct="%1.0f%%", startangle=90)
    ax3.set_title("Recommendation Categories")

    # Panel 4: Summary text
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis("off")
    validated = df[df["mae_improved"] == True]
    lines = [
        "Settings Assessment Pipeline", "",
        f"Total patients: {len(df)}",
        f"ISF validated (EXP-2739): ✓",
        f"  - Improved: {len(validated)}/{len(df[df['mae_improved'].notna()])}",
        f"  - Reduce ISF: {(df['category']=='REDUCE_ISF').sum()}",
        f"  - Increase ISF: {(df['category']=='INCREASE_ISF').sum()}",
        f"  - No change: {(df['category']=='OK').sum()}",
        f"  - High confidence: {(df['confidence']=='high').sum()}", "",
        "CR status: ⚠ Informational only",
        "  (EXP-2738 showed CR corrections too aggressive)",
        "Basal status: ⚠ Pending validation",
    ]
    ax4.text(0.05, 0.95, "\n".join(lines), transform=ax4.transAxes,
             fontsize=10, va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    out = VIZ_DIR / "settings-assessment-dashboard.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out}")


if __name__ == "__main__":
    generate_report()
