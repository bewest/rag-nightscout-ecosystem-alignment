#!/usr/bin/env python3
"""EXP-2612: Post-Effective-CR Advisory Validation.

Quick validation after adding advise_effective_cr() and removing sim CR.
Ensures the advisory system still correlates with TIR outcomes.

H1: SQS vs TIR correlation ≥ 0.6 (maintained from EXP-2606's r=0.726).
H2: New effective CR recommendations appear for patients with CR mismatch.
H3: Combined NS+ODC validation still significant (maintained from EXP-2607).
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
    compute_settings_quality_score,
)
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2612_post_cr_validation.json")
ALL_PATIENTS = [
    "a", "b", "c", "d", "e", "f", "g", "i", "k",
    "odc-74077367", "odc-86025410", "odc-96254963",
    "odc-39819048", "odc-49141524",
]


def main():
    print("=" * 70)
    print("EXP-2612: Post-Effective-CR Advisory Validation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = []
    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) < 500:
            continue

        g_mask = pdf["glucose"].notna()
        glucose = pdf.loc[g_mask, "glucose"].values
        hours = pdf.loc[g_mask, "time"].dt.hour.values
        bolus = pdf.loc[g_mask, "bolus"].values if "bolus" in pdf else None
        carbs_arr = pdf.loc[g_mask, "carbs"].values if "carbs" in pdf else None
        iob = pdf.loc[g_mask, "iob"].values if "iob" in pdf else None
        cob = pdf.loc[g_mask, "cob"].values if "cob" in pdf else None

        if len(glucose) < 200:
            continue

        tir = float(np.mean((glucose >= 70) & (glucose <= 180)) * 100)

        isf = float(pdf["scheduled_isf"].dropna().median())
        cr = float(pdf["scheduled_cr"].dropna().median())
        basal = float(pdf["scheduled_basal_rate"].dropna().median())
        profile = PatientProfile(
            isf_schedule=[{"start": "00:00:00", "value": isf}],
            cr_schedule=[{"start": "00:00:00", "value": cr}],
            basal_schedule=[{"start": "00:00:00", "value": basal}],
            target_low=70, target_high=180, dia_hours=6.0,
        )

        clinical = generate_clinical_report(
            glucose=glucose, metabolic=None, profile=profile,
            carbs=carbs_arr, bolus=bolus, hours=hours,
        )

        n_days = max(1, (pdf["time"].max() - pdf["time"].min()).days)

        recs = generate_settings_advice(
            glucose=glucose, metabolic=None, hours=hours,
            clinical=clinical, profile=profile,
            days_of_data=n_days,
            carbs=carbs_arr, bolus=bolus, iob=iob, cob=cob,
        )

        sqs = compute_settings_quality_score(recs)
        ctrl = "ODC" if pid.startswith("odc") else "NS"

        # Find CR and ISF recs
        cr_rec = next((r for r in recs if r.parameter.value == "cr"), None)
        isf_rec = next((r for r in recs if r.parameter.value == "isf"), None)

        top = recs[0] if recs else None
        top_desc = f"{top.parameter.value} {top.direction} {top.magnitude_pct:.0f}%" if top else "none"

        print(f"  [{ctrl}] {pid:>18s}: SQS={sqs:.1f}, TIR={tir:.1f}%, "
              f"recs={len(recs)}, top={top_desc}"
              f"{', CR=' + cr_rec.direction + ' ' + str(round(cr_rec.magnitude_pct)) + '%' if cr_rec else ''}")

        results.append({
            "pid": pid,
            "ctrl": ctrl,
            "sqs": sqs,
            "tir": tir,
            "n_recs": len(recs),
            "top_desc": top_desc,
            "has_cr_rec": cr_rec is not None,
            "cr_direction": cr_rec.direction if cr_rec else None,
            "cr_magnitude": cr_rec.magnitude_pct if cr_rec else None,
        })

    # Analysis
    print("\n" + "=" * 70)
    ns_results = [r for r in results if r["ctrl"] == "NS"]
    odc_results = [r for r in results if r["ctrl"] == "ODC"]

    # H1: NS SQS vs TIR
    ns_sqs = [r["sqs"] for r in ns_results]
    ns_tir = [r["tir"] for r in ns_results]
    h1_r, h1_p = stats.pearsonr(ns_sqs, ns_tir)
    h1_confirmed = h1_r >= 0.6
    print(f"\nH1 - NS SQS vs TIR: r={h1_r:.3f} (p={h1_p:.4f}), n={len(ns_results)}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.6)")

    # H2: Effective CR recs appear
    cr_count = sum(1 for r in results if r["has_cr_rec"])
    h2_confirmed = cr_count >= 3
    print(f"\nH2 - Effective CR recs: {cr_count}/{len(results)} patients")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: ≥3)")

    # H3: Combined correlation
    all_sqs = [r["sqs"] for r in results]
    all_tir = [r["tir"] for r in results]
    h3_r, h3_p = stats.pearsonr(all_sqs, all_tir)
    h3_confirmed = h3_r >= 0.6 and h3_p < 0.05
    print(f"\nH3 - Combined SQS vs TIR: r={h3_r:.3f} (p={h3_p:.4f}), n={len(results)}")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.6, p < 0.05)")

    output = {
        "experiment": "EXP-2612",
        "results": results,
        "hypotheses": {
            "H1": {"r": round(h1_r, 3), "p": round(h1_p, 4), "confirmed": h1_confirmed},
            "H2": {"cr_count": cr_count, "confirmed": h2_confirmed},
            "H3": {"r": round(h3_r, 3), "p": round(h3_p, 4), "confirmed": h3_confirmed},
        },
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
