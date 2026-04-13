#!/usr/bin/env python3
"""EXP-2608: Settings Drift Detection Over Time.

Hypothesis: Patient settings needs may evolve over time. Detecting drift
in recommended adjustments enables proactive advisory updates. While
EXP-2605 showed stability in first-vs-second-half comparisons, finer
temporal resolution (30-day blocks) may reveal gradual trends.

H1: For ≥5/14 patients, ISF recommendation magnitude shows a monotonic
    trend (increasing or decreasing) across ≥3 consecutive 30-day blocks,
    suggesting evolving insulin sensitivity.
H2: SQS trend over time is correlated with TIR trend (r ≥ 0.5) — if
    settings quality degrades, TIR should worsen.
H3: Patients with significant SQS drift (slope p < 0.1) have higher
    glycemic variability (CV) than stable patients.

Design:
- Split each patient's data into 30-day blocks (minimum 3 blocks)
- Run generate_settings_advice() on each block independently
- Track SQS, top recommendation magnitude, and TIR per block
- Test for temporal trends using Spearman correlation and linear regression
- Compare drift patients vs stable patients on glycemic metrics

If confirmed: Productionize drift detection into advisory system to flag
when settings may need updating.
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
from cgmencode.production.metabolic_engine import compute_metabolic_state

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2608_drift_detection.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_PATIENTS = [
    "odc-74077367", "odc-86025410", "odc-96254963",
    "odc-39819048", "odc-49141524",
]
ALL_PATIENTS = FULL_PATIENTS + ODC_PATIENTS
BLOCK_DAYS = 30
MIN_BLOCKS = 3


def _build_profile(pdf):
    """Build PatientProfile from patient data."""
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70,
        target_high=180,
        dia_hours=6.0,
    )


def _run_advisory(pdf, profile):
    """Run advisory pipeline on a data block."""
    # Align glucose and hours (dropna can change length)
    g_mask = pdf["glucose"].notna()
    glucose = pdf.loc[g_mask, "glucose"].values
    if len(glucose) < 100:
        return None

    hours = pdf.loc[g_mask, "time"].dt.hour.values if hasattr(pdf["time"].dt, "hour") else None

    tir = float(np.mean((glucose >= 70) & (glucose <= 180)) * 100)
    tbr = float(np.mean(glucose < 70) * 100)
    cv = float(np.std(glucose) / np.mean(glucose) * 100) if np.mean(glucose) > 0 else 0

    clinical = generate_clinical_report(
        glucose=glucose,
        metabolic=None,
        profile=profile,
        carbs=pdf.loc[g_mask, "carbs"].values if "carbs" in pdf else None,
        bolus=pdf.loc[g_mask, "bolus"].values if "bolus" in pdf else None,
        hours=hours,
    )

    carbs = pdf.loc[g_mask, "carbs"].values if "carbs" in pdf else None
    bolus = pdf.loc[g_mask, "bolus"].values if "bolus" in pdf else None
    iob = pdf.loc[g_mask, "iob"].values if "iob" in pdf else None
    cob = pdf.loc[g_mask, "cob"].values if "cob" in pdf else None

    n_days = max(1, (pdf["time"].max() - pdf["time"].min()).days)

    recs = generate_settings_advice(
        glucose=glucose,
        metabolic=None,
        hours=hours,
        clinical=clinical,
        profile=profile,
        days_of_data=n_days,
        carbs=carbs,
        bolus=bolus,
        iob=iob,
        cob=cob,
    )

    sqs = compute_settings_quality_score(recs)

    top_rec = None
    top_magnitude = 0
    top_direction = ""
    isf_magnitude = 0
    isf_direction = ""
    for r in recs:
        if top_rec is None:
            top_rec = r
            top_magnitude = r.magnitude_pct
            top_direction = r.direction
        if r.parameter.value == "isf" and isf_magnitude == 0:
            isf_magnitude = r.magnitude_pct
            isf_direction = r.direction

    return {
        "sqs": sqs,
        "tir": tir,
        "tbr": tbr,
        "cv": cv,
        "n_recs": len(recs),
        "top_param": top_rec.parameter.value if top_rec else None,
        "top_direction": top_direction,
        "top_magnitude": top_magnitude,
        "isf_direction": isf_direction,
        "isf_magnitude": isf_magnitude,
    }


def main():
    print("=" * 70)
    print("EXP-2608: Settings Drift Detection Over Time")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            print(f"  {pid}: skipped (only {len(pdf)} rows)")
            continue

        ctrl = "ODC" if pid.startswith("odc") else "NS"
        profile = _build_profile(pdf)

        # Split into 30-day blocks
        t_min = pdf["time"].min()
        t_max = pdf["time"].max()
        total_days = (t_max - t_min).days
        n_blocks = total_days // BLOCK_DAYS

        if n_blocks < MIN_BLOCKS:
            print(f"  {pid}: skipped (only {n_blocks} blocks, need {MIN_BLOCKS})")
            continue

        print(f"\n{'='*50}")
        print(f"PATIENT {pid} ({ctrl}, {total_days}d, {n_blocks} blocks)")
        print(f"{'='*50}")

        blocks = []
        for i in range(n_blocks):
            t_start = t_min + pd.Timedelta(days=i * BLOCK_DAYS)
            t_end = t_start + pd.Timedelta(days=BLOCK_DAYS)
            block_df = pdf[(pdf["time"] >= t_start) & (pdf["time"] < t_end)]
            if len(block_df) < 100:
                continue

            result = _run_advisory(block_df, profile)
            if result is None:
                continue

            result["block"] = i
            result["start_date"] = str(t_start.date())
            result["end_date"] = str(t_end.date())
            blocks.append(result)

            print(f"  Block {i} ({t_start.date()}-{t_end.date()}): "
                  f"SQS={result['sqs']:.1f}, TIR={result['tir']:.1f}%, "
                  f"ISF {result['isf_direction']} {result['isf_magnitude']:.0f}%")

        if len(blocks) < MIN_BLOCKS:
            print(f"  Only {len(blocks)} valid blocks, skipping")
            continue

        # Analyze trends
        sqs_values = [b["sqs"] for b in blocks]
        tir_values = [b["tir"] for b in blocks]
        cv_values = [b["cv"] for b in blocks]
        isf_mags = [b["isf_magnitude"] * (1 if b["isf_direction"] == "increase" else -1)
                    for b in blocks]
        block_indices = list(range(len(blocks)))

        # Spearman correlation for monotonic trend
        sqs_rho, sqs_p = stats.spearmanr(block_indices, sqs_values)
        tir_rho, tir_p = stats.spearmanr(block_indices, tir_values)
        isf_rho, isf_p = stats.spearmanr(block_indices, isf_mags) if any(m != 0 for m in isf_mags) else (0, 1)

        # SQS vs TIR correlation within patient
        sqs_tir_r, sqs_tir_p = stats.pearsonr(sqs_values, tir_values) if len(set(sqs_values)) > 1 else (0, 1)

        print(f"\n  SQS trend: rho={sqs_rho:.3f} (p={sqs_p:.3f})")
        print(f"  TIR trend: rho={tir_rho:.3f} (p={tir_p:.3f})")
        print(f"  ISF trend: rho={isf_rho:.3f} (p={isf_p:.3f})")
        print(f"  SQS-TIR within patient: r={sqs_tir_r:.3f}")

        # Direction changes
        isf_dirs = [b["isf_direction"] for b in blocks if b["isf_direction"]]
        dir_changes = sum(1 for i in range(1, len(isf_dirs)) if isf_dirs[i] != isf_dirs[i-1])

        results[pid] = {
            "ctrl": ctrl,
            "n_blocks": len(blocks),
            "total_days": total_days,
            "blocks": blocks,
            "sqs_trend_rho": round(sqs_rho, 3),
            "sqs_trend_p": round(sqs_p, 3),
            "tir_trend_rho": round(tir_rho, 3),
            "tir_trend_p": round(tir_p, 3),
            "isf_trend_rho": round(isf_rho, 3),
            "isf_trend_p": round(isf_p, 3),
            "sqs_tir_corr": round(sqs_tir_r, 3),
            "dir_changes": dir_changes,
            "sqs_range": [min(sqs_values), max(sqs_values)],
            "tir_range": [min(tir_values), max(tir_values)],
            "mean_cv": round(np.mean(cv_values), 1),
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT DRIFT ANALYSIS")
    print("=" * 70)

    # H1: Monotonic ISF magnitude trends
    h1_count = 0
    for pid, r in results.items():
        has_trend = abs(r["isf_trend_rho"]) >= 0.5 and r["isf_trend_p"] < 0.2
        if has_trend:
            h1_count += 1
            direction = "increasing" if r["isf_trend_rho"] > 0 else "decreasing"
            print(f"  {pid}: ISF magnitude {direction} (rho={r['isf_trend_rho']:.3f}, p={r['isf_trend_p']:.3f})")
    print(f"\nH1 - ISF monotonic trend: {h1_count}/{len(results)} patients")
    h1_confirmed = h1_count >= 5
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥5/{len(results)})")

    # H2: SQS trend correlates with TIR trend
    sqs_trends = [r["sqs_trend_rho"] for r in results.values()]
    tir_trends = [r["tir_trend_rho"] for r in results.values()]
    if len(sqs_trends) > 3:
        h2_r, h2_p = stats.pearsonr(sqs_trends, tir_trends)
    else:
        h2_r, h2_p = 0, 1
    h2_confirmed = h2_r >= 0.5
    print(f"\nH2 - SQS trend vs TIR trend: r={h2_r:.3f} (p={h2_p:.3f})")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.5)")

    # H3: Drift patients have higher CV
    drift_cvs = []
    stable_cvs = []
    for pid, r in results.items():
        if abs(r["sqs_trend_rho"]) >= 0.4 and r["sqs_trend_p"] < 0.15:
            drift_cvs.append(r["mean_cv"])
        else:
            stable_cvs.append(r["mean_cv"])

    if drift_cvs and stable_cvs:
        h3_diff = np.mean(drift_cvs) - np.mean(stable_cvs)
        h3_confirmed = h3_diff > 0
        print(f"\nH3 - Drift CV={np.mean(drift_cvs):.1f}% vs Stable CV={np.mean(stable_cvs):.1f}%")
        print(f"  Difference: {h3_diff:+.1f}pp")
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (drift patients have higher CV)")
    else:
        h3_confirmed = False
        print(f"\nH3 - Insufficient drift/stable split ({len(drift_cvs)} drift, {len(stable_cvs)} stable)")
        print(f"  H3 NOT CONFIRMED (insufficient data)")

    # Summary table
    print(f"\n{'='*70}")
    print("PATIENT DRIFT SUMMARY")
    print(f"{'='*70}")
    print(f"{'Pt':>18s}  {'Ctrl':>4s}  {'Blks':>4s}  {'SQS_rho':>7s}  {'TIR_rho':>7s}  {'ISF_rho':>7s}  {'DirChg':>6s}  {'CV':>5s}")
    print("-" * 70)
    for pid, r in sorted(results.items()):
        print(f"{pid:>18s}  {r['ctrl']:>4s}  {r['n_blocks']:>4d}  "
              f"{r['sqs_trend_rho']:>7.3f}  {r['tir_trend_rho']:>7.3f}  "
              f"{r['isf_trend_rho']:>7.3f}  {r['dir_changes']:>6d}  "
              f"{r['mean_cv']:>5.1f}")

    # Save results
    output = {
        "experiment": "EXP-2608",
        "title": "Settings Drift Detection Over Time",
        "block_days": BLOCK_DAYS,
        "patients": results,
        "hypotheses": {
            "H1": {
                "description": "ISF monotonic trend in ≥5 patients",
                "count": h1_count,
                "total": len(results),
                "confirmed": h1_confirmed,
            },
            "H2": {
                "description": "SQS trend correlates with TIR trend",
                "r": round(h2_r, 3),
                "p": round(h2_p, 3),
                "confirmed": h2_confirmed,
            },
            "H3": {
                "description": "Drift patients have higher CV",
                "drift_cv": round(np.mean(drift_cvs), 1) if drift_cvs else None,
                "stable_cv": round(np.mean(stable_cvs), 1) if stable_cvs else None,
                "confirmed": h3_confirmed,
            },
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
