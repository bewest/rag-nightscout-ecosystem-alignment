#!/usr/bin/env python3
"""EXP-2597: Settings Report Card — Ensemble Advisory Validation.

We have 14 settings advisories but haven't validated them as an ensemble.
This experiment runs all advisories on every FULL telemetry patient and
evaluates:
  1. How many recommendations does each patient get?
  2. Are recommendations internally consistent (not contradictory)?
  3. Do patients with more/stronger recommendations have worse TIR?
  4. Which advisories fire most frequently? (feature importance for settings)

Hypotheses:
  H1: Patients with more recommendations (count) have lower TIR (r < -0.5).
  H2: Total predicted TIR improvement correlates with actual TIR deficit
      (how far TIR is from 100%) — r > 0.5.
  H3: No contradictory recommendations exist (e.g., increase AND decrease
      basal at the same time) for any patient.
  H4: The top advisory (highest predicted delta) correctly identifies the
      main settings issue for ≥7/9 patients (validated against known data).

Design:
  For each patient, construct inputs and call generate_settings_advice().
  Analyze the output ensemble.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.settings_advisor import (
    generate_settings_advice,
)
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.types import PatientProfile, SettingsParameter

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2597_settings_report.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _build_patient_profile(pdf):
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
        dia_hours=5.0,
    )


def _extract_correction_events(pdf):
    """Extract correction events for advisories that need them."""
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    N = len(pdf)
    for i in range(N - 24):  # need 2h post
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue

        # Find 2h-post glucose
        post_idx = i + 24  # 2h at 5-min intervals
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue

        # TIR change: was the 2h window after correction in-range vs before?
        pre_window = glucose[max(0, i-12):i]
        post_window = glucose[i:post_idx]
        pre_tir = float(np.nanmean((pre_window >= 70) & (pre_window <= 180))) if len(pre_window) > 0 else 0.5
        post_tir = float(np.nanmean((post_window >= 70) & (post_window <= 180))) if len(post_window) > 0 else 0.5
        tir_change = post_tir - pre_tir

        # Rebound: did glucose go below 70?
        went_below_70 = bool(np.any(post_window < 70))
        rebound_magnitude = float(glucose[i] - np.nanmin(post_window)) if not np.all(np.isnan(post_window)) else 0.0

        events.append({
            "start_bg": float(glucose[i]),
            "tir_change": tir_change,
            "rebound": went_below_70,
            "rebound_magnitude": rebound_magnitude,
            "went_below_70": went_below_70,
            "bolus": float(bolus[i]),
            "hour": float(hours[i]),
            "post_glucose_2h": float(glucose[post_idx]),
            "drop": float(glucose[i] - glucose[post_idx]),
        })

    return events[:50]  # cap


def _extract_meal_events(pdf):
    """Extract meal events for CR adequacy analysis."""
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    N = len(pdf)
    for i in range(N - 48):  # need 4h post
        if carbs[i] < 10:
            continue
        if np.isnan(glucose[i]):
            continue

        post_idx = i + 48  # 4h post
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue

        events.append({
            "carbs": float(carbs[i]),
            "bolus": float(bolus[i]),
            "pre_meal_bg": float(glucose[i]),
            "post_meal_bg_4h": float(glucose[post_idx]),
            "hour": float(hours[i]),
        })

    return events[:30]


def main():
    print("=" * 70)
    print("EXP-2597: Settings Report Card — Ensemble Advisory Validation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_reports = {}

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 50}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        # Build inputs
        glucose = pdf["glucose"].values
        hours = (pd.to_datetime(pdf["time"]).dt.hour +
                 pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
        bolus = pdf["bolus"].fillna(0).values
        carbs = pdf["carbs"].fillna(0).values
        iob = pdf["iob"].fillna(0).values
        cob = pdf["cob"].fillna(0).values if "cob" in pdf.columns else None
        actual_basal = pdf["actual_basal_rate"].fillna(0).values if "actual_basal_rate" in pdf.columns else None

        profile = _build_patient_profile(pdf)
        days = (pd.to_datetime(pdf["time"]).max() - pd.to_datetime(pdf["time"]).min()).days

        # Compute metabolic state
        try:
            metabolic = compute_metabolic_state(glucose, hours)
        except Exception:
            metabolic = None

        # Compute clinical report
        try:
            clinical = generate_clinical_report(
                glucose=glucose,
                metabolic=metabolic,
                profile=profile,
                carbs=carbs,
                bolus=bolus,
                hours=hours,
            )
        except Exception as e:
            print(f"  Clinical report failed: {e}")
            continue

        # Extract events
        correction_events = _extract_correction_events(pdf)
        meal_events = _extract_meal_events(pdf)

        # TIR
        valid_g = glucose[~np.isnan(glucose)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))
        tbr = float(np.mean(valid_g < 70))
        tar = float(np.mean(valid_g > 180))

        print(f"  TIR={tir:.1%}, TBR={tbr:.1%}, TAR={tar:.1%}")
        print(f"  Days of data: {days}")
        print(f"  Corrections: {len(correction_events)}, Meals: {len(meal_events)}")

        # Run all advisories
        try:
            recs = generate_settings_advice(
                glucose=glucose,
                metabolic=metabolic,
                hours=hours,
                clinical=clinical,
                profile=profile,
                days_of_data=float(days),
                carbs=carbs,
                bolus=bolus,
                iob=iob,
                cob=cob,
                actual_basal=actual_basal,
                correction_events=correction_events,
                meal_events=meal_events,
            )
        except Exception as e:
            print(f"  Advisory generation failed: {e}")
            import traceback
            traceback.print_exc()
            continue

        print(f"\n  RECOMMENDATIONS ({len(recs)}):")
        report = {
            "patient_id": pid,
            "tir": tir,
            "tbr": tbr,
            "tar": tar,
            "n_recs": len(recs),
            "recs": [],
            "total_predicted_delta": 0.0,
        }

        for i, r in enumerate(recs):
            delta = abs(r.predicted_tir_delta)
            report["total_predicted_delta"] += delta
            rec_info = {
                "rank": i + 1,
                "parameter": r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter),
                "direction": r.direction,
                "magnitude_pct": r.magnitude_pct,
                "current": r.current_value,
                "suggested": r.suggested_value,
                "predicted_delta": r.predicted_tir_delta,
                "confidence": r.confidence,
                "evidence_preview": r.evidence[:80] + "..." if len(r.evidence) > 80 else r.evidence,
            }
            report["recs"].append(rec_info)

            print(f"  #{i+1}: {rec_info['parameter']} {r.direction} {r.magnitude_pct:.0f}% "
                  f"({r.current_value:.2f}→{r.suggested_value:.2f}) "
                  f"Δ={r.predicted_tir_delta:+.1f}pp conf={r.confidence:.2f}")

        # Check for contradictions
        param_directions = {}
        contradictions = []
        for r in recs:
            p = r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter)
            d = r.direction
            hrs = r.affected_hours if hasattr(r, 'affected_hours') else None
            key = f"{p}_{hrs}"
            if key in param_directions:
                if param_directions[key] != d:
                    contradictions.append(f"{p}: {param_directions[key]} vs {d}")
            else:
                param_directions[key] = d

        report["contradictions"] = contradictions
        if contradictions:
            print(f"\n  ⚠ CONTRADICTIONS: {contradictions}")
        else:
            print(f"\n  ✓ No contradictions")

        all_reports[pid] = report

    if not all_reports:
        print("No results")
        return

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "patient_id": r["patient_id"],
        "tir": r["tir"],
        "n_recs": r["n_recs"],
        "total_delta": r["total_predicted_delta"],
        "tir_deficit": 1.0 - r["tir"],
        "n_contradictions": len(r["contradictions"]),
    } for r in all_reports.values()])

    print(f"\n{'Patient':<6} {'TIR':>6} {'#Recs':>5} {'TotΔ':>6} {'Deficit':>7} {'Contradictions':>14}")
    print("-" * 50)
    for _, r in sdf.iterrows():
        print(f"{r['patient_id']:<6} {r['tir']:>6.1%} {r['n_recs']:>5} "
              f"{r['total_delta']:>6.1f} {r['tir_deficit']:>7.1%} {r['n_contradictions']:>14}")

    from scipy import stats

    # H1: More recs → lower TIR
    r_count_tir, p_count_tir = stats.spearmanr(sdf["n_recs"], sdf["tir"])
    print(f"\nH1 - #Recs vs TIR: r={r_count_tir:.3f}, p={p_count_tir:.3f}")
    h1_confirmed = r_count_tir < -0.5
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r < -0.5)")

    # H2: Total delta correlates with deficit
    r_delta_deficit, p_delta_deficit = stats.spearmanr(sdf["total_delta"], sdf["tir_deficit"])
    print(f"\nH2 - Total predicted Δ vs TIR deficit: r={r_delta_deficit:.3f}, p={p_delta_deficit:.3f}")
    h2_confirmed = r_delta_deficit > 0.5
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.5)")

    # H3: No contradictions
    total_contradictions = sdf["n_contradictions"].sum()
    print(f"\nH3 - Zero contradictions: {total_contradictions} found")
    h3_confirmed = total_contradictions == 0
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # Advisory frequency analysis
    print(f"\n{'=' * 70}")
    print("ADVISORY FREQUENCY")
    print(f"{'=' * 70}")

    param_counts = {}
    for report in all_reports.values():
        for rec in report["recs"]:
            p = rec["parameter"]
            param_counts[p] = param_counts.get(p, 0) + 1

    for p, count in sorted(param_counts.items(), key=lambda x: -x[1]):
        print(f"  {p:<20}: {count}/{len(all_reports)} patients")

    # Save
    output = {
        "experiment": "EXP-2597",
        "title": "Settings Report Card — Ensemble Advisory Validation",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "reports": list(all_reports.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
