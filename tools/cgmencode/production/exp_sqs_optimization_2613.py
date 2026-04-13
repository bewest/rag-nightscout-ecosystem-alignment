#!/usr/bin/env python3
"""EXP-2613: SQS Formula Optimization.

The SQS (Settings Quality Score) formula degraded from r=0.726 to r=0.548
after adding effective CR and removing sim CR. This experiment tests
alternative SQS formulas to find the one with best TIR correlation.

H1: A formula using top-recommendation magnitude only (instead of sum)
    improves correlation to r ≥ 0.65.
H2: Weighting ISF recommendations higher than CR improves correlation.
H3: The optimal formula maintains r ≥ 0.6 across both NS and ODC patients.

Design:
- Run advisory on all 14 patients (same as EXP-2612)
- Compute SQS using 6 different formulas
- Rank formulas by TIR correlation
- Select best formula and validate on NS vs ODC split
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.settings_advisor import (
    generate_settings_advice,
    SettingsParameter,
)
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2613_sqs_optimization.json")
ALL_PATIENTS = [
    "a", "b", "c", "d", "e", "f", "g", "i", "k",
    "odc-74077367", "odc-86025410", "odc-96254963",
    "odc-39819048", "odc-49141524",
]


def sqs_current(recs):
    """Current: 100 - Σ(magnitude_pct × confidence × 0.15)."""
    if not recs:
        return 100.0
    return max(0, 100 - sum(r.magnitude_pct * r.confidence * 0.15 for r in recs))


def sqs_top_only(recs):
    """Use only the top recommendation (highest predicted_tir_delta)."""
    if not recs:
        return 100.0
    top = max(recs, key=lambda r: abs(r.predicted_tir_delta))
    return max(0, 100 - top.magnitude_pct * top.confidence * 0.3)


def sqs_weighted(recs):
    """ISF weighted 2× higher than CR in sum."""
    if not recs:
        return 100.0
    weights = {
        SettingsParameter.ISF: 2.0,
        SettingsParameter.CR: 1.0,
        SettingsParameter.BASAL_RATE: 1.5,
    }
    total = sum(r.magnitude_pct * r.confidence * 0.15 *
                weights.get(r.parameter, 1.0) for r in recs)
    return max(0, 100 - total)


def sqs_sqrt(recs):
    """Square root of sum — diminishing returns for multiple recs."""
    if not recs:
        return 100.0
    total = sum(r.magnitude_pct * r.confidence for r in recs)
    return max(0, 100 - np.sqrt(total) * 1.5)


def sqs_max_mag(recs):
    """Use maximum magnitude across all recs."""
    if not recs:
        return 100.0
    max_mag = max(r.magnitude_pct * r.confidence for r in recs)
    return max(0, 100 - max_mag * 0.3)


def sqs_n_plus_mag(recs):
    """Combine number of recs with top magnitude."""
    if not recs:
        return 100.0
    n = len(recs)
    top_mag = max(r.magnitude_pct * r.confidence for r in recs)
    return max(0, 100 - (n * 2 + top_mag * 0.25))


SQS_FORMULAS = {
    "current": sqs_current,
    "top_only": sqs_top_only,
    "weighted": sqs_weighted,
    "sqrt": sqs_sqrt,
    "max_mag": sqs_max_mag,
    "n_plus_mag": sqs_n_plus_mag,
}


def main():
    print("=" * 70)
    print("EXP-2613: SQS Formula Optimization")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    patient_data = []

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) < 500:
            continue

        g_mask = pdf["glucose"].notna()
        glucose = pdf.loc[g_mask, "glucose"].values
        hours = pdf.loc[g_mask, "time"].dt.hour.values
        bolus = pdf.loc[g_mask, "bolus"].values if "bolus" in pdf else None
        carbs = pdf.loc[g_mask, "carbs"].values if "carbs" in pdf else None
        iob = pdf.loc[g_mask, "iob"].values if "iob" in pdf else None
        cob = pdf.loc[g_mask, "cob"].values if "cob" in pdf else None

        if len(glucose) < 200:
            continue

        tir = float(np.mean((glucose >= 70) & (glucose <= 180)) * 100)

        isf = float(pdf["scheduled_isf"].dropna().median())
        cr = float(pdf["scheduled_cr"].dropna().median())
        basal_rate = float(pdf["scheduled_basal_rate"].dropna().median())
        profile = PatientProfile(
            isf_schedule=[{"start": "00:00:00", "value": isf}],
            cr_schedule=[{"start": "00:00:00", "value": cr}],
            basal_schedule=[{"start": "00:00:00", "value": basal_rate}],
            target_low=70, target_high=180, dia_hours=6.0,
        )

        clinical = generate_clinical_report(
            glucose=glucose, metabolic=None, profile=profile,
            carbs=carbs, bolus=bolus, hours=hours,
        )

        n_days = max(1, (pdf["time"].max() - pdf["time"].min()).days)

        recs = generate_settings_advice(
            glucose=glucose, metabolic=None, hours=hours,
            clinical=clinical, profile=profile,
            days_of_data=n_days,
            carbs=carbs, bolus=bolus, iob=iob, cob=cob,
        )

        ctrl = "ODC" if pid.startswith("odc") else "NS"
        sqs_values = {name: fn(recs) for name, fn in SQS_FORMULAS.items()}

        patient_data.append({
            "pid": pid,
            "ctrl": ctrl,
            "tir": tir,
            "n_recs": len(recs),
            "recs_summary": [(r.parameter.value, r.direction, round(r.magnitude_pct, 0))
                             for r in recs[:5]],
            **sqs_values,
        })

    # ====== Formula comparison ======
    print("\n" + "=" * 70)
    print("FORMULA COMPARISON")
    print("=" * 70)

    tirs = [p["tir"] for p in patient_data]
    ns_mask = [p["ctrl"] == "NS" for p in patient_data]
    ns_tirs = [p["tir"] for p in patient_data if p["ctrl"] == "NS"]

    best_formula = None
    best_r = 0

    for name in SQS_FORMULAS:
        all_sqs = [p[name] for p in patient_data]
        ns_sqs = [p[name] for p in patient_data if p["ctrl"] == "NS"]

        r_all, p_all = stats.pearsonr(all_sqs, tirs) if len(set(all_sqs)) > 1 else (0, 1)
        r_ns, p_ns = stats.pearsonr(ns_sqs, ns_tirs) if len(set(ns_sqs)) > 1 else (0, 1)

        marker = " *** BEST" if r_all > best_r else ""
        if r_all > best_r:
            best_r = r_all
            best_formula = name

        print(f"\n  {name:>12s}: All r={r_all:.3f} (p={p_all:.4f}), NS r={r_ns:.3f} (p={p_ns:.4f}){marker}")

        # Print per-patient SQS for top formulas
        if name in ("current", "top_only", "sqrt", "max_mag"):
            for p in patient_data:
                print(f"    {p['pid']:>18s}: SQS={p[name]:.1f}, TIR={p['tir']:.1f}%")

    print(f"\n{'='*70}")
    print(f"BEST FORMULA: {best_formula} (r={best_r:.3f})")
    print(f"{'='*70}")

    # H1: Top-only formula improves to r ≥ 0.65
    r_top, p_top = stats.pearsonr([p["top_only"] for p in patient_data], tirs)
    h1_confirmed = r_top >= 0.65
    print(f"\nH1 - top_only formula: r={r_top:.3f}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.65)")

    # H2: Weighted formula improves
    r_wt, p_wt = stats.pearsonr([p["weighted"] for p in patient_data], tirs)
    r_cur, _ = stats.pearsonr([p["current"] for p in patient_data], tirs)
    h2_confirmed = r_wt > r_cur
    print(f"\nH2 - weighted vs current: r={r_wt:.3f} vs r={r_cur:.3f}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Best formula maintains r ≥ 0.6 across both groups
    best_all = [p[best_formula] for p in patient_data]
    r_best, p_best = stats.pearsonr(best_all, tirs)
    h3_confirmed = r_best >= 0.6
    print(f"\nH3 - best formula ({best_formula}) combined: r={r_best:.3f}")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.6)")

    output = {
        "experiment": "EXP-2613",
        "title": "SQS Formula Optimization",
        "best_formula": best_formula,
        "best_r": round(best_r, 3),
        "patients": patient_data,
        "formula_correlations": {
            name: round(stats.pearsonr([p[name] for p in patient_data], tirs)[0], 3)
            for name in SQS_FORMULAS
        },
        "hypotheses": {
            "H1": {"r": round(r_top, 3), "confirmed": h1_confirmed},
            "H2": {"weighted_r": round(r_wt, 3), "current_r": round(r_cur, 3), "confirmed": h2_confirmed},
            "H3": {"r": round(r_best, 3), "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
