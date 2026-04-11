"""
EXP-2542: End-to-End Settings Advisor Validation

Validates that all 6 production advisories produce CONSISTENT and REASONABLE
recommendations when run on real patient data from grid.parquet.

Sub-experiments:
  EXP-2542a — Run generate_settings_advice() on all 19 patients
  EXP-2542b — Internal consistency across advisories
  EXP-2542c — Predicted TIR impact if all recommendations adopted
  EXP-2542d — Dashboard summary (firing rates, magnitudes, confidence)
  EXP-2542e — Contradiction detection

Research basis: ISF (EXP-747), ISF nonlinearity (EXP-2511), correction
threshold (EXP-2528), circadian ISF (EXP-2271), CR adequacy (EXP-2535),
basal overnight (EXP-2371).
"""

from __future__ import annotations

import json
import sys
import os
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cgmencode.production.settings_advisor import generate_settings_advice
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.types import (
    MetabolicState,
    PatientData,
    PatientProfile,
    SettingsParameter,
    SettingsRecommendation,
)

# ── Constants ─────────────────────────────────────────────────────────

GRID_PATH = Path(__file__).resolve().parents[3] / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUTPUT_PATH = Path(__file__).resolve().parents[3] / "externals" / "experiments" / "exp-2542_settings_validation.json"

TIR_LOW = 70.0
TIR_HIGH = 180.0
HYPO_THRESHOLD = 70.0


# ── Helpers ───────────────────────────────────────────────────────────

def _load_grid():
    """Load grid.parquet into a pandas DataFrame."""
    import pandas as pd
    return pd.read_parquet(GRID_PATH)


def _extract_patient_data(df_patient) -> dict:
    """Extract arrays and profile from a single patient's DataFrame slice."""
    glucose = df_patient["glucose"].values.astype(np.float32)
    iob = df_patient["iob"].values.astype(np.float32) if "iob" in df_patient else None
    cob = df_patient["cob"].values.astype(np.float32) if "cob" in df_patient else None
    bolus = df_patient["bolus"].values.astype(np.float32) if "bolus" in df_patient else None
    carbs_col = df_patient["carbs"].values.astype(np.float32) if "carbs" in df_patient else None
    actual_basal = df_patient["actual_basal_rate"].values.astype(np.float32) if "actual_basal_rate" in df_patient else None

    # Extract hours from timestamps
    times = df_patient["time"].values
    hours = _timestamps_to_hours(times)

    # Profile from per-row schedule columns (median across the patient)
    isf_median = float(np.nanmedian(df_patient["scheduled_isf"].values))
    cr_median = float(np.nanmedian(df_patient["scheduled_cr"].values))
    basal_median = float(np.nanmedian(df_patient["scheduled_basal_rate"].values))

    # Guard against NaN in profile values
    if np.isnan(isf_median) or isf_median <= 0:
        isf_median = 50.0
    if np.isnan(cr_median) or cr_median <= 0:
        cr_median = 10.0
    if np.isnan(basal_median) or basal_median <= 0:
        basal_median = 0.8

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": isf_median}],
        cr_schedule=[{"time": "00:00", "value": cr_median}],
        basal_schedule=[{"time": "00:00", "value": basal_median}],
        dia_hours=5.0,
        target_low=70.0,
        target_high=120.0,
    )

    # Build correction events from bolus data
    correction_events = _build_correction_events(glucose, bolus, hours, isf_median)

    # Build meal events from carbs + bolus data
    meal_events = _build_meal_events(glucose, carbs_col, bolus, hours)

    # Compute days of data
    n_samples = len(glucose)
    days_of_data = n_samples * 5.0 / 60.0 / 24.0

    return {
        "glucose": glucose,
        "iob": iob,
        "cob": cob,
        "bolus": bolus,
        "carbs": carbs_col,
        "actual_basal": actual_basal,
        "hours": hours,
        "profile": profile,
        "correction_events": correction_events,
        "meal_events": meal_events,
        "days_of_data": days_of_data,
        "isf_median": isf_median,
        "cr_median": cr_median,
        "basal_median": basal_median,
    }


def _timestamps_to_hours(times) -> np.ndarray:
    """Convert datetime64 timestamps to fractional hours of day."""
    import pandas as pd
    ts = pd.DatetimeIndex(times)
    return (ts.hour + ts.minute / 60.0 + ts.second / 3600.0).values.astype(np.float32)


def _build_correction_events(
    glucose: np.ndarray,
    bolus: Optional[np.ndarray],
    hours: np.ndarray,
    isf: float,
) -> List[dict]:
    """Build correction event dicts from bolus + glucose arrays.

    A correction event is a bolus > 0.3U when glucose > 150 mg/dL.
    We compute the 4h BG drop, rebound, and hypo occurrence.
    """
    if bolus is None:
        return []

    events = []
    n = len(glucose)
    indices_4h = 48  # 4 hours at 5-min intervals

    for i in range(n):
        if bolus[i] <= 0.3 or not np.isfinite(glucose[i]):
            continue
        if glucose[i] < 150:
            continue
        if i + indices_4h >= n:
            continue

        start_bg = float(glucose[i])
        end_bg = float(glucose[min(i + indices_4h, n - 1)])
        window = glucose[i:i + indices_4h + 1]
        valid_window = window[np.isfinite(window)]

        if len(valid_window) < 12:
            continue

        drop_4h = start_bg - end_bg
        nadir = float(np.nanmin(valid_window))
        went_below_70 = nadir < HYPO_THRESHOLD

        # Rebound: does BG rise > 30 mg/dL from nadir within window?
        nadir_idx = int(np.nanargmin(window[:len(valid_window)]))
        remaining = window[nadir_idx:]
        remaining_valid = remaining[np.isfinite(remaining)]
        rebound = False
        rebound_magnitude = 0.0
        if len(remaining_valid) > 0:
            peak_after = float(np.nanmax(remaining_valid))
            rebound_magnitude = peak_after - nadir
            rebound = rebound_magnitude > 30

        # TIR change: fraction in range after vs before
        pre_tir = float(np.mean(
            (valid_window[:12] >= TIR_LOW) & (valid_window[:12] <= TIR_HIGH)
        )) if len(valid_window) >= 12 else 0.5
        post_tir = float(np.mean(
            (valid_window[-12:] >= TIR_LOW) & (valid_window[-12:] <= TIR_HIGH)
        )) if len(valid_window) >= 12 else 0.5
        tir_change = post_tir - pre_tir

        events.append({
            "start_bg": start_bg,
            "drop_4h": drop_4h,
            "dose": float(bolus[i]),
            "hour": float(hours[i]),
            "tir_change": tir_change,
            "rebound": rebound,
            "rebound_magnitude": rebound_magnitude,
            "went_below_70": went_below_70,
        })

    return events


def _build_meal_events(
    glucose: np.ndarray,
    carbs: Optional[np.ndarray],
    bolus: Optional[np.ndarray],
    hours: np.ndarray,
) -> List[dict]:
    """Build meal event dicts from carbs + bolus + glucose arrays.

    A meal event is a carb entry > 5g with a bolus > 0.1U in the
    surrounding 30-min window. Computes 4h post-meal BG.
    """
    if carbs is None or bolus is None:
        return []

    events = []
    n = len(glucose)
    indices_4h = 48

    for i in range(n):
        if carbs[i] <= 5 or not np.isfinite(glucose[i]):
            continue
        if i + indices_4h >= n:
            continue

        # Find bolus in ±6 interval window (30 min)
        window_start = max(0, i - 6)
        window_end = min(n, i + 7)
        bolus_window = bolus[window_start:window_end]
        total_bolus = float(np.nansum(bolus_window[bolus_window > 0.1]))

        if total_bolus < 0.1:
            continue

        pre_meal_bg = float(glucose[i])
        post_meal_bg_4h = float(glucose[min(i + indices_4h, n - 1)])

        if not np.isfinite(post_meal_bg_4h):
            # Find nearest valid reading
            for offset in range(-3, 4):
                idx = min(max(i + indices_4h + offset, 0), n - 1)
                if np.isfinite(glucose[idx]):
                    post_meal_bg_4h = float(glucose[idx])
                    break
            else:
                continue

        events.append({
            "carbs": float(carbs[i]),
            "bolus": total_bolus,
            "pre_meal_bg": pre_meal_bg,
            "post_meal_bg_4h": post_meal_bg_4h,
            "hour": float(hours[i]),
        })

    return events


def _rec_to_dict(rec: SettingsRecommendation) -> dict:
    """Convert a SettingsRecommendation to a JSON-serializable dict."""
    d = {
        "parameter": rec.parameter.value,
        "direction": rec.direction,
        "magnitude_pct": rec.magnitude_pct,
        "current_value": rec.current_value,
        "suggested_value": rec.suggested_value,
        "predicted_tir_delta": rec.predicted_tir_delta,
        "affected_hours": list(rec.affected_hours),
        "confidence": rec.confidence,
        "evidence": rec.evidence,
        "rationale": rec.rationale,
    }
    if rec.confidence_grade is not None:
        d["confidence_grade"] = rec.confidence_grade.value
    if rec.ci_width_pct is not None:
        d["ci_width_pct"] = rec.ci_width_pct
    return d


def _safe_float(v) -> Optional[float]:
    """Convert to float, returning None for NaN/inf."""
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── EXP-2542a: Run Settings Advisor on All Patients ───────────────────

def run_2542a(df) -> dict:
    """Run generate_settings_advice() on each patient. Returns per-patient results."""
    import pandas as pd

    patient_ids = sorted(df["patient_id"].unique())
    results = {}

    for pid in patient_ids:
        print(f"  [2542a] Processing patient {pid}...")
        df_p = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        data = _extract_patient_data(df_p)

        glucose = data["glucose"]
        hours = data["hours"]
        profile = data["profile"]
        days = data["days_of_data"]

        # Build PatientData for metabolic engine
        timestamps_ms = (pd.DatetimeIndex(df_p["time"]).astype(np.int64) // 10**6).values.astype(np.float64)
        patient_data = PatientData(
            glucose=glucose,
            timestamps=timestamps_ms,
            profile=profile,
            iob=data["iob"],
            cob=data["cob"],
            bolus=data["bolus"],
            carbs=data["carbs"],
            basal_rate=data["actual_basal"],
            patient_id=pid,
        )

        # Compute metabolic state
        try:
            metabolic = compute_metabolic_state(patient_data)
        except Exception as e:
            print(f"    WARNING: metabolic engine failed for {pid}: {e}")
            metabolic = None

        # Generate clinical report
        try:
            clinical = generate_clinical_report(
                glucose, metabolic, profile,
                carbs=data["carbs"], bolus=data["bolus"], hours=hours,
            )
        except Exception as e:
            print(f"    WARNING: clinical report failed for {pid}: {e}")
            continue

        # Run full settings advisor
        try:
            recs = generate_settings_advice(
                glucose=glucose,
                metabolic=metabolic,
                hours=hours,
                clinical=clinical,
                profile=profile,
                days_of_data=days,
                carbs=data["carbs"],
                bolus=data["bolus"],
                iob=data["iob"],
                cob=data["cob"],
                actual_basal=data["actual_basal"],
                correction_events=data["correction_events"],
                meal_events=data["meal_events"],
            )
        except Exception as e:
            print(f"    WARNING: settings advisor failed for {pid}: {e}")
            recs = []

        # Compute basic glycemic stats
        valid_g = glucose[np.isfinite(glucose)]
        tir = float(np.mean((valid_g >= TIR_LOW) & (valid_g <= TIR_HIGH))) if len(valid_g) > 0 else 0.0
        tbr = float(np.mean(valid_g < TIR_LOW)) if len(valid_g) > 0 else 0.0
        tar = float(np.mean(valid_g > TIR_HIGH)) if len(valid_g) > 0 else 0.0

        results[pid] = {
            "patient_id": pid,
            "days_of_data": round(days, 1),
            "n_samples": len(glucose),
            "glycemic_stats": {
                "tir": round(tir * 100, 1),
                "tbr": round(tbr * 100, 1),
                "tar": round(tar * 100, 1),
                "mean_glucose": round(float(np.nanmean(valid_g)), 1) if len(valid_g) > 0 else None,
            },
            "profile": {
                "isf": data["isf_median"],
                "cr": data["cr_median"],
                "basal": data["basal_median"],
            },
            "n_correction_events": len(data["correction_events"]),
            "n_meal_events": len(data["meal_events"]),
            "n_recommendations": len(recs),
            "recommendations": [_rec_to_dict(r) for r in recs],
        }
        print(f"    → {len(recs)} recommendations, TIR={tir*100:.1f}%")

    return results


# ── EXP-2542b: Recommendation Consistency ─────────────────────────────

def run_2542b(patient_results: dict) -> dict:
    """Check internal consistency across advisories for each patient."""
    inconsistencies = []
    consistent_count = 0
    total_checked = 0

    for pid, pr in patient_results.items():
        recs = pr["recommendations"]
        if not recs:
            continue

        patient_issues = []

        # Index recommendations by parameter type
        isf_recs = [r for r in recs if r["parameter"] == "isf"]
        cr_recs = [r for r in recs if r["parameter"] == "cr"]
        basal_recs = [r for r in recs if r["parameter"] == "basal_rate"]
        threshold_recs = [r for r in recs if r["parameter"] == "correction_threshold"]

        # Check 1: ISF recommendation direction vs nonlinearity
        isf_main = [r for r in isf_recs if "discrepancy" in r.get("evidence", "").lower() or "EXP-747" in r.get("evidence", "")]
        isf_nonlinear = [r for r in isf_recs if "non-linearity" in r.get("evidence", "").lower() or "EXP-2511" in r.get("evidence", "")]

        if isf_main and isf_nonlinear:
            total_checked += 1
            main_dir = isf_main[0]["direction"]
            nl_dir = isf_nonlinear[0]["direction"]
            # Nonlinearity always suggests "decrease" (effective ISF at high doses is lower)
            # Main ISF can go either way. Conflict: main says increase but NL says decrease
            if main_dir == "increase" and nl_dir == "decrease":
                patient_issues.append({
                    "check": "isf_vs_nonlinearity",
                    "severity": "warning",
                    "detail": (
                        f"ISF main says {main_dir} (effective > profile) but "
                        f"nonlinearity says {nl_dir} (dose-dependent diminishing). "
                        f"Not contradictory: main ISF is about calibration, "
                        f"nonlinearity is about dose-response shape."
                    ),
                })
            else:
                consistent_count += 1

        # Check 2: Correction threshold vs ISF direction
        if threshold_recs and isf_main:
            total_checked += 1
            thresh_dir = threshold_recs[0]["direction"]
            isf_dir = isf_main[0]["direction"]
            # If threshold says increase (don't correct at low BG) and ISF says increase
            # (corrections are more effective), these are coherent.
            # Contradiction: threshold says corrections are harmful but ISF says they're
            # more effective — this means corrections WORK but shouldn't be done at low BG.
            # Actually not a contradiction, just nuanced. Flag if both say decrease.
            if thresh_dir == "decrease" and isf_dir == "decrease":
                patient_issues.append({
                    "check": "threshold_vs_isf",
                    "severity": "info",
                    "detail": (
                        f"Both correction threshold and ISF recommend decrease. "
                        f"Threshold wants to correct at lower BG while ISF says "
                        f"corrections are less effective. Potentially conflicting signals."
                    ),
                })
            else:
                consistent_count += 1

        # Check 3: Circadian ISF blocks internal consistency
        circadian_isf = [r for r in isf_recs
                         if "circadian" in r.get("evidence", "").lower()
                         or "EXP-2271" in r.get("evidence", "")]
        if len(circadian_isf) >= 2:
            total_checked += 1
            directions = set(r["direction"] for r in circadian_isf)
            # Having both increase and decrease across blocks is EXPECTED
            # (ISF varies by time of day). Flag only if all blocks go same direction
            # — that suggests the base ISF is wrong, not the circadian pattern.
            if len(directions) == 1 and len(circadian_isf) >= 3:
                patient_issues.append({
                    "check": "circadian_isf_uniformity",
                    "severity": "warning",
                    "detail": (
                        f"All {len(circadian_isf)} circadian ISF blocks recommend "
                        f"'{directions.pop()}'. This suggests the baseline ISF is "
                        f"wrong rather than a circadian pattern issue."
                    ),
                })
            else:
                consistent_count += 1

        # Check 4: CR adequacy vs post-meal TIR
        cr_adequacy = [r for r in cr_recs if "adequacy" in r.get("evidence", "").lower() or "EXP-2535" in r.get("evidence", "")]
        if cr_adequacy:
            total_checked += 1
            cr_dir = cr_adequacy[0]["direction"]
            tar = pr["glycemic_stats"]["tar"]
            # If CR says over-dosing but TAR is high, contradictory
            if cr_dir == "increase" and tar > 30:
                patient_issues.append({
                    "check": "cr_vs_tar",
                    "severity": "contradiction",
                    "detail": (
                        f"CR adequacy says over-dosing (increase CR) but "
                        f"TAR is {tar:.1f}% (high). Over-dosing should lower "
                        f"TAR, not raise it. Possible data or detection issue."
                    ),
                })
            # If CR says under-dosing but TAR is low, mild inconsistency
            elif cr_dir == "decrease" and tar < 10:
                patient_issues.append({
                    "check": "cr_vs_tar",
                    "severity": "info",
                    "detail": (
                        f"CR adequacy says under-dosing (decrease CR) but "
                        f"TAR is only {tar:.1f}%. AID may be compensating. "
                        f"Recommendation still valid to reduce AID workload."
                    ),
                })
            else:
                consistent_count += 1

        # Check 5: Opposing CR recommendations
        cr_directions = [r["direction"] for r in cr_recs]
        if "increase" in cr_directions and "decrease" in cr_directions:
            total_checked += 1
            patient_issues.append({
                "check": "cr_opposing_directions",
                "severity": "contradiction",
                "detail": (
                    f"Multiple CR recommendations in opposing directions. "
                    f"Directions: {cr_directions}. May reflect time-of-day "
                    f"differences or conflicting advisory logic."
                ),
            })
        elif len(cr_directions) >= 2:
            total_checked += 1
            consistent_count += 1

        if patient_issues:
            inconsistencies.append({
                "patient_id": pid,
                "n_issues": len(patient_issues),
                "issues": patient_issues,
            })

    return {
        "total_checks": total_checked,
        "consistent_checks": consistent_count,
        "consistency_rate": round(consistent_count / max(total_checked, 1) * 100, 1),
        "patients_with_issues": len(inconsistencies),
        "inconsistencies": inconsistencies,
    }


# ── EXP-2542c: Predicted TIR Impact ──────────────────────────────────

def run_2542c(patient_results: dict) -> dict:
    """Estimate total TIR impact if all recommendations are adopted per patient."""
    impact_summary = {}

    for pid, pr in patient_results.items():
        recs = pr["recommendations"]
        if not recs:
            impact_summary[pid] = {
                "current_tir": pr["glycemic_stats"]["tir"],
                "total_predicted_delta": 0.0,
                "n_recommendations": 0,
                "by_parameter": {},
            }
            continue

        current_tir = pr["glycemic_stats"]["tir"]

        # Sum predicted deltas by parameter type (skip NaN)
        by_param: Dict[str, float] = defaultdict(float)
        for r in recs:
            d = r["predicted_tir_delta"]
            if d is not None and np.isfinite(d):
                by_param[r["parameter"]] += d

        total_delta = sum(by_param.values())
        projected_tir = min(100.0, current_tir + total_delta)

        impact_summary[pid] = {
            "current_tir": current_tir,
            "total_predicted_delta": round(total_delta, 1),
            "projected_tir": round(projected_tir, 1),
            "n_recommendations": len(recs),
            "by_parameter": {k: round(v, 1) for k, v in by_param.items()},
            "is_plausible": total_delta < 30.0,  # >30pp would be implausible
        }

    # Population-level stats
    deltas = [v["total_predicted_delta"] for v in impact_summary.values()]
    current_tirs = [v["current_tir"] for v in impact_summary.values()]

    return {
        "per_patient": impact_summary,
        "population": {
            "mean_predicted_delta": round(float(np.mean(deltas)), 1) if deltas else 0.0,
            "median_predicted_delta": round(float(np.median(deltas)), 1) if deltas else 0.0,
            "max_predicted_delta": round(float(np.max(deltas)), 1) if deltas else 0.0,
            "n_implausible": sum(1 for v in impact_summary.values() if not v["is_plausible"]),
            "mean_current_tir": round(float(np.mean(current_tirs)), 1) if current_tirs else 0.0,
            "mean_projected_tir": round(
                float(np.mean([v["projected_tir"] for v in impact_summary.values()])), 1
            ) if impact_summary else 0.0,
        },
    }


# ── EXP-2542d: Recommendation Dashboard ──────────────────────────────

def run_2542d(patient_results: dict) -> dict:
    """Dashboard summary of recommendation patterns across all patients."""
    all_recs = []
    for pr in patient_results.values():
        for r in pr["recommendations"]:
            r["_patient_id"] = pr["patient_id"]
            all_recs.append(r)

    n_patients = len(patient_results)

    # Firing rate per advisory type
    param_counts = Counter(r["parameter"] for r in all_recs)
    patients_with_param = defaultdict(set)
    for r in all_recs:
        patients_with_param[r["parameter"]].add(r["_patient_id"])

    firing_rates = {}
    for param in ["isf", "cr", "basal_rate", "correction_threshold"]:
        n_fires = len(patients_with_param.get(param, set()))
        firing_rates[param] = {
            "n_patients": n_fires,
            "pct_patients": round(n_fires / max(n_patients, 1) * 100, 1),
            "total_recommendations": param_counts.get(param, 0),
        }

    # Categorize by evidence source
    source_counts = Counter()
    for r in all_recs:
        evidence = r.get("evidence", "")
        if "EXP-747" in evidence or "discrepancy" in evidence.lower():
            source_counts["isf_discrepancy"] += 1
        elif "EXP-2511" in evidence or "non-linearity" in evidence.lower():
            source_counts["isf_nonlinearity"] += 1
        elif "EXP-2528" in evidence or "threshold" in evidence.lower():
            source_counts["correction_threshold"] += 1
        elif "EXP-2271" in evidence or "circadian" in evidence.lower():
            source_counts["circadian_isf"] += 1
        elif "EXP-2535" in evidence or "adequacy" in evidence.lower():
            source_counts["cr_adequacy"] += 1
        elif "EXP-2371" in evidence or "overnight" in evidence.lower():
            source_counts["overnight_basal"] += 1
        elif "EXP-2341" in evidence or "context" in evidence.lower():
            source_counts["context_cr"] += 1
        elif "CR effectiveness" in evidence:
            source_counts["cr_simulation"] += 1
        elif "Basal assessed" in evidence or "Overnight TIR" in evidence:
            source_counts["basal_simulation"] += 1
        else:
            source_counts["other"] += 1

    # Magnitude distributions
    magnitudes_by_param = defaultdict(list)
    confidences_by_param = defaultdict(list)
    deltas_by_param = defaultdict(list)

    for r in all_recs:
        p = r["parameter"]
        magnitudes_by_param[p].append(r["magnitude_pct"])
        confidences_by_param[p].append(r["confidence"])
        deltas_by_param[p].append(r["predicted_tir_delta"])

    magnitude_stats = {}
    for p, vals in magnitudes_by_param.items():
        magnitude_stats[p] = {
            "mean": round(float(np.mean(vals)), 1),
            "median": round(float(np.median(vals)), 1),
            "min": round(float(np.min(vals)), 1),
            "max": round(float(np.max(vals)), 1),
        }

    confidence_stats = {}
    for p, vals in confidences_by_param.items():
        confidence_stats[p] = {
            "mean": round(float(np.mean(vals)), 2),
            "median": round(float(np.median(vals)), 2),
            "min": round(float(np.min(vals)), 2),
            "max": round(float(np.max(vals)), 2),
        }

    # Recommendations per patient distribution
    recs_per_patient = [pr["n_recommendations"] for pr in patient_results.values()]

    return {
        "total_recommendations": len(all_recs),
        "n_patients": n_patients,
        "recs_per_patient": {
            "mean": round(float(np.mean(recs_per_patient)), 1),
            "median": round(float(np.median(recs_per_patient)), 1),
            "min": int(np.min(recs_per_patient)),
            "max": int(np.max(recs_per_patient)),
        },
        "firing_rates": firing_rates,
        "advisory_source_counts": dict(source_counts.most_common()),
        "magnitude_stats": magnitude_stats,
        "confidence_stats": confidence_stats,
        "most_common_advisory": source_counts.most_common(1)[0] if source_counts else ("none", 0),
    }


# ── EXP-2542e: Contradiction Detection ───────────────────────────────

def run_2542e(patient_results: dict) -> dict:
    """Detect logical contradictions that would make following all advice impossible."""
    contradictions = []
    warnings = []

    for pid, pr in patient_results.items():
        recs = pr["recommendations"]
        if len(recs) < 2:
            continue

        # Group by parameter
        by_param = defaultdict(list)
        for r in recs:
            by_param[r["parameter"]].append(r)

        # Contradiction 1: Same parameter, overlapping hours, opposing directions
        # BUT: exclude circadian ISF cross-method overlaps (2-zone vs 4-block
        # are complementary methods that naturally recommend different directions
        # for overlapping time windows).
        for param, param_recs in by_param.items():
            if len(param_recs) < 2:
                continue
            for i in range(len(param_recs)):
                for j in range(i + 1, len(param_recs)):
                    r1, r2 = param_recs[i], param_recs[j]
                    if r1["direction"] != r2["direction"]:
                        h1 = r1["affected_hours"]
                        h2 = r2["affected_hours"]

                        # Skip cross-method circadian ISF comparisons:
                        # 2-zone (EXP-2271 residual) uses 7-22 / 22-7 windows
                        # 4-block (EXP-2271 profiled) uses 0-6/6-12/12-18/18-24
                        # These are complementary, not contradictory.
                        e1 = r1.get("evidence", "")
                        e2 = r2.get("evidence", "")
                        is_cross_circadian = (
                            ("Circadian ISF" in e1 or "circadian" in e1.lower())
                            and ("Circadian ISF" in e2 or "circadian" in e2.lower())
                            and (
                                ("profiling" in e1 and "profiling" not in e2)
                                or ("profiling" in e2 and "profiling" not in e1)
                                or h1 != h2  # different time blocks
                            )
                        )
                        if is_cross_circadian:
                            continue

                        # Skip all-day (0-24) vs block-specific recs: the
                        # all-day rec is a baseline suggestion while block
                        # recs are refinements.
                        if (h1 == [0.0, 24.0] or h2 == [0.0, 24.0]):
                            warnings.append({
                                "patient_id": pid,
                                "type": "allday_vs_block",
                                "detail": (
                                    f"{param}: all-day '{r1['direction']}' vs "
                                    f"block '{r2['direction']}' ({h2[0]:.0f}-{h2[1]:.0f}h). "
                                    f"Block-specific rec should take priority."
                                ),
                            })
                            continue

                        if _hours_overlap(h1, h2):
                            contradictions.append({
                                "patient_id": pid,
                                "type": "opposing_overlapping",
                                "parameter": param,
                                "rec1_direction": r1["direction"],
                                "rec1_hours": h1,
                                "rec1_magnitude": r1["magnitude_pct"],
                                "rec2_direction": r2["direction"],
                                "rec2_hours": h2,
                                "rec2_magnitude": r2["magnitude_pct"],
                                "detail": (
                                    f"{param}: '{r1['direction']}' ({h1[0]:.0f}-{h1[1]:.0f}h) "
                                    f"vs '{r2['direction']}' ({h2[0]:.0f}-{h2[1]:.0f}h)"
                                ),
                            })

        # Contradiction 2: ISF says corrections too effective but TAR is high
        isf_recs = by_param.get("isf", [])
        tar = pr["glycemic_stats"]["tar"]
        for r in isf_recs:
            if r["direction"] == "decrease" and tar > 25:
                if "discrepancy" in r.get("evidence", "").lower():
                    warnings.append({
                        "patient_id": pid,
                        "type": "isf_decrease_with_high_tar",
                        "detail": (
                            f"ISF decrease recommended (corrections too effective) "
                            f"but TAR={tar:.1f}% is high. If corrections work well, "
                            f"TAR should be lower. May indicate other factors."
                        ),
                    })

        # Contradiction 3: Total predicted delta is implausibly large
        total_delta = sum(r["predicted_tir_delta"] for r in recs)
        current_tir = pr["glycemic_stats"]["tir"]
        if total_delta > 30:
            warnings.append({
                "patient_id": pid,
                "type": "implausible_total_delta",
                "detail": (
                    f"Total predicted TIR delta is +{total_delta:.1f}pp from "
                    f"{len(recs)} recommendations. This exceeds plausible limits "
                    f"(>30pp). Individual deltas likely not independent."
                ),
            })

        # Contradiction 4: Recommendations would push TIR > 100%
        if current_tir + total_delta > 105:
            warnings.append({
                "patient_id": pid,
                "type": "tir_overflow",
                "detail": (
                    f"Current TIR {current_tir:.1f}% + predicted delta "
                    f"+{total_delta:.1f}pp = {current_tir + total_delta:.1f}%, "
                    f"exceeding 100%. Deltas are not additive."
                ),
            })

    return {
        "n_contradictions": len(contradictions),
        "n_warnings": len(warnings),
        "contradictions": contradictions,
        "warnings": warnings,
        "verdict": (
            "PASS" if len(contradictions) == 0
            else f"FAIL: {len(contradictions)} contradictions found"
        ),
    }


def _hours_overlap(h1: list, h2: list) -> bool:
    """Check if two hour ranges overlap (accounting for midnight wrap)."""
    a_start, a_end = h1
    b_start, b_end = h2

    # For ranges that wrap midnight (e.g. 22-6), expand logic
    if a_start <= a_end and b_start <= b_end:
        return a_start < b_end and b_start < a_end
    # Simplify: if either wraps midnight, or both are 0-24, they overlap
    if a_start == 0 and a_end == 24:
        return True
    if b_start == 0 and b_end == 24:
        return True
    # Approximate: treat wrap-around as overlapping
    return True


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("EXP-2542: End-to-End Settings Advisor Validation")
    print("=" * 70)

    print("\nLoading grid data...")
    df = _load_grid()
    print(f"  Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    # EXP-2542a
    print("\n── EXP-2542a: Running Settings Advisor on All Patients ──")
    patient_results = run_2542a(df)

    # EXP-2542b
    print("\n── EXP-2542b: Recommendation Consistency ──")
    consistency = run_2542b(patient_results)
    print(f"  Consistency rate: {consistency['consistency_rate']}% "
          f"({consistency['consistent_checks']}/{consistency['total_checks']} checks)")
    print(f"  Patients with issues: {consistency['patients_with_issues']}")
    for inc in consistency["inconsistencies"]:
        for issue in inc["issues"]:
            print(f"    [{issue['severity']}] {inc['patient_id']}: {issue['check']}")

    # EXP-2542c
    print("\n── EXP-2542c: Predicted TIR Impact ──")
    impact = run_2542c(patient_results)
    pop = impact["population"]
    print(f"  Mean current TIR: {pop['mean_current_tir']}%")
    print(f"  Mean predicted TIR delta: +{pop['mean_predicted_delta']}pp")
    print(f"  Mean projected TIR: {pop['mean_projected_tir']}%")
    print(f"  Implausible predictions: {pop['n_implausible']}")

    # EXP-2542d
    print("\n── EXP-2542d: Recommendation Dashboard ──")
    dashboard = run_2542d(patient_results)
    print(f"  Total recommendations: {dashboard['total_recommendations']}")
    print(f"  Mean per patient: {dashboard['recs_per_patient']['mean']}")
    print(f"  Most common advisory: {dashboard['most_common_advisory']}")
    print(f"  Firing rates:")
    for param, info in dashboard["firing_rates"].items():
        print(f"    {param}: {info['pct_patients']}% of patients "
              f"({info['total_recommendations']} recs)")
    print(f"  Advisory source breakdown:")
    for source, count in dashboard["advisory_source_counts"].items():
        print(f"    {source}: {count}")

    # EXP-2542e
    print("\n── EXP-2542e: Contradiction Detection ──")
    contradictions = run_2542e(patient_results)
    print(f"  Verdict: {contradictions['verdict']}")
    print(f"  Contradictions: {contradictions['n_contradictions']}")
    print(f"  Warnings: {contradictions['n_warnings']}")
    for c in contradictions["contradictions"][:5]:
        print(f"    [CONTRADICTION] {c['patient_id']}: {c['detail']}")
    for w in contradictions["warnings"][:5]:
        print(f"    [WARNING] {w['patient_id']}: {w['detail']}")

    # Save results
    output = {
        "experiment": "EXP-2542",
        "title": "End-to-End Settings Advisor Validation",
        "n_patients": len(patient_results),
        "results": {
            "exp_2542a_per_patient": patient_results,
            "exp_2542b_consistency": consistency,
            "exp_2542c_impact": impact,
            "exp_2542d_dashboard": dashboard,
            "exp_2542e_contradictions": contradictions,
        },
        "summary": {
            "total_recommendations": dashboard["total_recommendations"],
            "mean_recs_per_patient": dashboard["recs_per_patient"]["mean"],
            "consistency_rate": consistency["consistency_rate"],
            "mean_predicted_tir_delta": pop["mean_predicted_delta"],
            "n_contradictions": contradictions["n_contradictions"],
            "n_warnings": contradictions["n_warnings"],
            "verdict": contradictions["verdict"],
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Results saved to {OUTPUT_PATH}")

    # Final summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"  Patients analyzed:        {len(patient_results)}")
    print(f"  Total recommendations:    {dashboard['total_recommendations']}")
    print(f"  Mean per patient:         {dashboard['recs_per_patient']['mean']}")
    print(f"  Consistency rate:         {consistency['consistency_rate']}%")
    print(f"  Mean predicted TIR Δ:     +{pop['mean_predicted_delta']}pp")
    print(f"  Contradictions:           {contradictions['n_contradictions']}")
    print(f"  Warnings:                 {contradictions['n_warnings']}")
    print(f"  Overall verdict:          {contradictions['verdict']}")

    return output


if __name__ == "__main__":
    main()
