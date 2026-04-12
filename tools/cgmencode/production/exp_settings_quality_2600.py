#!/usr/bin/env python3
"""EXP-2600: Composite Settings Quality Score.

Given the 14 advisories (now consolidated by EXP-2597), derive a single
numeric "settings quality score" (0-100) that summarizes how well a
patient's therapy settings match their metabolic needs.

Hypotheses:
  H1: Settings quality score (SQS) inversely correlates with TIR deficit
      (lower SQS → lower TIR) — r > 0.7.
  H2: SQS correlates with loop workload (lower SQS → more loop work) — r > 0.5.
  H3: SQS predicts TBR risk (patients with worst SQS have highest TBR).
  H4: The top-ranked advisory correctly predicts the primary adjustment
      needed (validated against known basal/ISF/CR issues from prior exps).

Design:
  SQS = 100 - Σ(|delta_i| × confidence_i) for all recommendations.
  Higher score = better settings. 100 = no recommendations needed.
  0 = maximum total predicted improvement available.

  Run on all FULL patients with consolidated advisories.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.settings_advisor import generate_settings_advice
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2600_settings_quality.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _build_patient_profile(pdf):
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _extract_correction_events(pdf, max_events=50):
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        pre_window = glucose[max(0, i-12):i]
        post_window = glucose[i:post_idx]
        pre_tir = float(np.nanmean((pre_window >= 70) & (pre_window <= 180))) if len(pre_window) > 0 else 0.5
        post_tir = float(np.nanmean((post_window >= 70) & (post_window <= 180))) if len(post_window) > 0 else 0.5
        events.append({
            "start_bg": float(glucose[i]),
            "tir_change": post_tir - pre_tir,
            "rebound": bool(np.any(post_window < 70)),
            "rebound_magnitude": float(glucose[i] - np.nanmin(post_window)) if not np.all(np.isnan(post_window)) else 0.0,
            "went_below_70": bool(np.any(post_window < 70)),
            "bolus": float(bolus[i]),
            "hour": float(hours[i]),
        })
        if len(events) >= max_events:
            break
    return events


def _extract_meal_events(pdf, max_events=30):
    events = []
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values
    N = len(pdf)
    for i in range(N - 48):
        if carbs[i] < 10 or np.isnan(glucose[i]):
            continue
        post_idx = i + 48
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        events.append({
            "carbs": float(carbs[i]),
            "bolus": float(bolus[i]),
            "pre_meal_bg": float(glucose[i]),
            "post_meal_bg_4h": float(glucose[post_idx]),
            "hour": float(hours[i]),
        })
        if len(events) >= max_events:
            break
    return events


def _compute_loop_workload(pdf):
    """Compute loop workload as fraction of time loop deviates >20% from scheduled."""
    if "actual_basal_rate" not in pdf.columns:
        return None
    sched = pdf["scheduled_basal_rate"].values
    actual = pdf["actual_basal_rate"].values
    mask = (~np.isnan(sched)) & (~np.isnan(actual)) & (sched > 0.01)
    if np.sum(mask) < 100:
        return None
    ratio = actual[mask] / sched[mask]
    workload = float(np.mean(np.abs(ratio - 1.0) > 0.2))
    return workload


def main():
    print("=" * 70)
    print("EXP-2600: Composite Settings Quality Score")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 40}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 40}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

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

        try:
            metabolic = compute_metabolic_state(glucose, hours)
        except Exception:
            metabolic = None

        try:
            clinical = generate_clinical_report(
                glucose=glucose, metabolic=metabolic, profile=profile,
                carbs=carbs, bolus=bolus, hours=hours,
            )
        except Exception as e:
            print(f"  Clinical report failed: {e}")
            continue

        correction_events = _extract_correction_events(pdf)
        meal_events = _extract_meal_events(pdf)

        try:
            recs = generate_settings_advice(
                glucose=glucose, metabolic=metabolic, hours=hours,
                clinical=clinical, profile=profile, days_of_data=float(days),
                carbs=carbs, bolus=bolus, iob=iob, cob=cob,
                actual_basal=actual_basal,
                correction_events=correction_events,
                meal_events=meal_events,
            )
        except Exception as e:
            print(f"  Advisory failed: {e}")
            import traceback
            traceback.print_exc()
            continue

        # Compute SQS
        total_weighted_delta = sum(
            abs(r.predicted_tir_delta) * r.confidence for r in recs
        )
        sqs = max(0, 100 - total_weighted_delta)

        # TIR metrics
        valid_g = glucose[~np.isnan(glucose)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))
        tbr = float(np.mean(valid_g < 70))
        tar = float(np.mean(valid_g > 180))
        cv = float(np.nanstd(valid_g) / np.nanmean(valid_g)) if np.nanmean(valid_g) > 0 else 0

        # Loop workload
        workload = _compute_loop_workload(pdf)

        # Top advisory
        top_param = recs[0].parameter.value if recs else "none"
        top_dir = recs[0].direction if recs else "none"
        top_delta = recs[0].predicted_tir_delta if recs else 0.0

        print(f"  SQS: {sqs:.1f}/100")
        print(f"  TIR: {tir:.1%}, TBR: {tbr:.1%}, TAR: {tar:.1%}, CV: {cv:.1%}")
        print(f"  Loop workload: {workload:.1%}" if workload else "  Loop workload: N/A")
        print(f"  #Recs: {len(recs)}, top: {top_param} {top_dir} ({top_delta:+.1f}pp)")

        results[pid] = {
            "patient_id": pid,
            "sqs": sqs,
            "tir": tir,
            "tbr": tbr,
            "tar": tar,
            "cv": cv,
            "workload": workload,
            "n_recs": len(recs),
            "top_param": top_param,
            "top_direction": top_dir,
            "top_delta": top_delta,
            "total_weighted_delta": total_weighted_delta,
            "recs_summary": [
                {"param": r.parameter.value, "dir": r.direction,
                 "delta": r.predicted_tir_delta, "conf": r.confidence}
                for r in recs[:5]  # top 5
            ],
        }

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT RESULTS")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "pid": r["patient_id"],
        "sqs": r["sqs"],
        "tir": r["tir"],
        "tbr": r["tbr"],
        "tar": r["tar"],
        "cv": r["cv"],
        "workload": r["workload"],
        "deficit": 1.0 - r["tir"],
    } for r in results.values()])

    print(f"\n{'Pt':<4} {'SQS':>5} {'TIR':>6} {'TBR':>6} {'TAR':>6} {'CV':>6} {'WL':>6}")
    print("-" * 45)
    for _, r in sdf.iterrows():
        wl = f"{r['workload']:.1%}" if r['workload'] is not None else "N/A"
        print(f"{r['pid']:<4} {r['sqs']:>5.1f} {r['tir']:>6.1%} {r['tbr']:>6.1%} "
              f"{r['tar']:>6.1%} {r['cv']:>6.1%} {wl:>6}")

    # H1: SQS vs TIR
    r_sqs_tir, p_sqs_tir = stats.spearmanr(sdf["sqs"], sdf["tir"])
    print(f"\nH1 - SQS vs TIR: r={r_sqs_tir:.3f} (p={p_sqs_tir:.3f})")
    h1_confirmed = r_sqs_tir > 0.7
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.7)")

    # H2: SQS vs loop workload
    wl_mask = sdf["workload"].notna()
    if wl_mask.sum() >= 3:
        r_sqs_wl, p_sqs_wl = stats.spearmanr(sdf.loc[wl_mask, "sqs"], sdf.loc[wl_mask, "workload"])
        print(f"\nH2 - SQS vs loop workload: r={r_sqs_wl:.3f} (p={p_sqs_wl:.3f})")
        h2_confirmed = r_sqs_wl < -0.5  # negative: higher SQS = lower workload
        print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (threshold: r < -0.5)")
    else:
        print("\nH2 - Not enough workload data")
        h2_confirmed = False

    # H3: SQS vs TBR
    r_sqs_tbr, p_sqs_tbr = stats.spearmanr(sdf["sqs"], sdf["tbr"])
    print(f"\nH3 - SQS vs TBR: r={r_sqs_tbr:.3f} (p={p_sqs_tbr:.3f})")
    h3_confirmed = r_sqs_tbr < -0.3  # negative: lower SQS = higher TBR
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (threshold: r < -0.3)")

    # H4: Top advisory matches known issue (qualitative)
    print(f"\nH4 - Top advisory per patient:")
    # Known issues from prior experiments:
    known_issues = {
        "a": "basal_rate (too low)",
        "b": "isf (too high for profile)",
        "c": "basal_rate (too high)",
        "d": "isf (reasonable)",
        "e": "isf (complex)",
        "f": "basal_rate (too low)",
        "g": "isf (moderately too high)",
        "i": "isf (complex, high TBR)",
        "k": "isf (well-controlled)",
    }
    matches = 0
    for pid, r in results.items():
        known = known_issues.get(pid, "?")
        top = r["top_param"]
        match = "✓" if top in known else "✗"
        if top in known:
            matches += 1
        print(f"  {pid}: top={top} {r['top_direction']} | known={known} {match}")

    h4_confirmed = matches >= 7
    print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'} ({matches}/9 match, threshold ≥7)")

    output = {
        "experiment": "EXP-2600",
        "title": "Composite Settings Quality Score",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "h4_confirmed": h4_confirmed,
        "patient_results": list(results.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
