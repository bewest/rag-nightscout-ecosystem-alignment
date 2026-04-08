#!/usr/bin/env python3
"""EXP-1391–1400: Pipeline Refinement & Production Readiness.

Building on 110 validated experiments (EXP-1281-1390), this batch addresses:
- Inverted gain detection (patient a's K=-1.081)
- Multi-parameter coordinated adjustments
- Onboarding templates from cross-patient transfer
- Auto re-evaluation scheduling
- Confidence-gated recommendation output
- Meal-time-specific CR triage
- Recommendation magnitude calibration
- Data quality degradation curves
- Pipeline sensitivity to threshold perturbation
- Validated clinical summary generation

Run: PYTHONPATH=tools python -m cgmencode.exp_clinical_1391 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from collections import defaultdict

import numpy as np

from cgmencode.exp_metabolic_flux import load_patients as _load_patients

# ---------------------------------------------------------------------------
# Patient data loader (shared across therapy experiments)
# ---------------------------------------------------------------------------
PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / "externals" / "ns-data" / "patients")


def load_patients(max_patients: int = 11):
    """Load patient data with CGM + insulin + PK channels."""
    raw = _load_patients(PATIENTS_DIR, max_patients=max_patients)
    patients = {}
    for p in raw:
        pid = p["name"]
        df = p["df"]
        cgm = df["glucose"].values.astype(float)
        bolus = df["bolus"].values.astype(float) if "bolus" in df.columns else np.zeros(len(df))
        carbs = df["carbs"].values.astype(float) if "carbs" in df.columns else np.zeros(len(df))
        pk = p["pk"] if p["pk"] is not None else None
        insulin = pk[:, 0] if pk is not None and pk.shape[1] > 0 else None
        profile_path = Path(PATIENTS_DIR) / pid / "training" / "profile.json"
        profile = {}
        if profile_path.exists():
            with open(profile_path) as f:
                profile = json.load(f)
        patients[pid] = {
            "cgm": cgm,
            "bolus": bolus,
            "carbs": carbs,
            "insulin": insulin,
            "pk": pk,
            "df": df,
            "profile": profile,
            "n_steps": len(cgm),
        }
    print(f"Loaded {len(patients)} patients")
    return patients


# ---------------------------------------------------------------------------
# Shared utility functions (from EXP-1381 lineage)
# ---------------------------------------------------------------------------

def compute_window_metrics(cgm, insulin=None, pk=None, profile=None):
    """Compute therapy metrics for a window of data."""
    valid = cgm[~np.isnan(cgm)]
    if len(valid) < 10:
        return None
    
    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
    mean_bg = np.mean(valid)
    cv = np.std(valid) / mean_bg * 100 if mean_bg > 0 else 999
    
    # Overnight drift (indices 0:96 = midnight to 8am at 5min resolution)
    steps_per_hour = 12
    overnight = cgm[:8*steps_per_hour]
    overnight_valid = overnight[~np.isnan(overnight)]
    drift = 0.0
    if len(overnight_valid) > steps_per_hour:
        drift = (overnight_valid[-1] - overnight_valid[0]) / (len(overnight_valid) / steps_per_hour)
    
    # Meal excursions by time block
    excursions = {}
    blocks = {
        "breakfast": (6*steps_per_hour, 10*steps_per_hour),
        "lunch": (11*steps_per_hour, 15*steps_per_hour),
        "dinner": (17*steps_per_hour, 21*steps_per_hour),
    }
    for meal, (start, end) in blocks.items():
        if end <= len(cgm):
            block = cgm[start:end]
            block_valid = block[~np.isnan(block)]
            if len(block_valid) > 6:
                excursions[meal] = np.max(block_valid) - np.min(block_valid)
    
    return {
        "tir": tir,
        "mean_bg": mean_bg,
        "cv": cv,
        "drift": abs(drift),
        "excursions": excursions,
    }


def compute_therapy_score(metrics, weights=None):
    """Compute therapy health score 0-100 with TIR-heavy weights."""
    if metrics is None:
        return 0.0
    if weights is None:
        weights = [60, 15, 15, 5, 5]  # TIR-heavy from EXP-1385
    
    tir_score = min(metrics["tir"], 100) / 100 * weights[0]
    basal_ok = 1.0 if metrics["drift"] < 5.0 else 0.0
    cr_ok = 1.0
    for meal, exc in metrics.get("excursions", {}).items():
        if exc > 70:
            cr_ok = 0.0
            break
    isf_ok = 1.0  # Placeholder — requires correction event analysis
    cv_ok = 1.0 if metrics["cv"] < 36 else 0.0
    
    return (tir_score + basal_ok * weights[1] + cr_ok * weights[2] +
            isf_ok * weights[3] + cv_ok * weights[4])


def get_grade(score):
    """Convert score to letter grade."""
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


def generate_recommendations(metrics, thresholds=None):
    """Generate therapy recommendations from metrics."""
    if metrics is None:
        return []
    if thresholds is None:
        thresholds = {"drift": 5.0, "excursion": 70.0, "isf_ratio": 2.0}
    
    recs = []
    if metrics["drift"] > thresholds["drift"]:
        direction = "increase" if metrics.get("mean_bg", 150) > 150 else "decrease"
        recs.append({
            "param": "basal",
            "direction": direction,
            "magnitude": min(abs(metrics["drift"]) / 10, 0.3),
            "confidence": min(abs(metrics["drift"]) / 15, 1.0),
            "aid_scale": 1.43,
        })
    
    for meal, exc in metrics.get("excursions", {}).items():
        if meal == "breakfast":
            continue  # Skip breakfast — only 20% agreement (EXP-1353)
        if exc > thresholds["excursion"]:
            recs.append({
                "param": f"{meal}_cr",
                "direction": "tighten",
                "magnitude": 0.20,
                "confidence": min(exc / 140, 1.0),
            })
    
    return recs


def assess_preconditions(cgm, insulin=None, pk=None):
    """Check 6-point preconditions."""
    results = {}
    valid_cgm = ~np.isnan(cgm)
    results["cgm_coverage"] = np.mean(valid_cgm) * 100
    results["cgm_pass"] = results["cgm_coverage"] >= 70
    
    if insulin is not None:
        valid_ins = ~np.isnan(insulin) if insulin.ndim == 1 else ~np.isnan(insulin[:, 0])
        results["insulin_coverage"] = np.mean(valid_ins) * 100
    else:
        results["insulin_coverage"] = 0.0
    results["insulin_pass"] = results["insulin_coverage"] >= 50
    
    results["n_days"] = len(cgm) / (12 * 24)
    results["days_pass"] = results["n_days"] >= 30
    
    met = sum([results["cgm_pass"], results["insulin_pass"], results["days_pass"]])
    results["total_met"] = met
    results["pass"] = met >= 2
    
    return results


def compute_fasting_drift(cgm, steps_per_hour=12):
    """Compute overnight fasting drift rate."""
    n_days = len(cgm) // (24 * steps_per_hour)
    drifts = []
    for d in range(n_days):
        start = d * 24 * steps_per_hour
        overnight = cgm[start:start + 8*steps_per_hour]
        valid = overnight[~np.isnan(overnight)]
        if len(valid) > steps_per_hour * 2:
            rate = (valid[-1] - valid[0]) / (len(valid) / steps_per_hour)
            drifts.append(rate)
    return np.array(drifts) if drifts else np.array([0.0])


# ---------------------------------------------------------------------------
# Denormalize PK channels (from prior experiments)
# ---------------------------------------------------------------------------
def denorm_pk(pk):
    """Denormalize PK channels to physical units."""
    if pk is None or pk.shape[1] < 8:
        return None
    return {
        "iob": pk[:, 0],
        "activity": pk[:, 1],
        "basal_ratio": pk[:, 2] * 2.0,
        "carb_rate": pk[:, 3] * 0.5,
        "hepatic": pk[:, 4] * 3.0,
        "demand": pk[:, 5],
        "net_balance": pk[:, 6] * 20.0,
        "isf_curve": pk[:, 7] * 200.0,
    }


# ---------------------------------------------------------------------------
# EXPERIMENTS
# ---------------------------------------------------------------------------

EXPERIMENTS = {}

def register(exp_id):
    def decorator(func):
        EXPERIMENTS[exp_id] = func
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-1391: Inverted AID Gain Detection
# ---------------------------------------------------------------------------
@register(1391)
def exp_inverted_gain(patients, detail=False):
    """Detect when AID loop has inverted gain (fighting wrong direction).
    
    Patient a has K=-1.081 from EXP-1359. Can we detect this from data alone?
    Method: correlate correction bolus direction with subsequent BG movement.
    If corrections consistently move BG the wrong way, gain is inverted.
    """
    results = {"name": "EXP-1391: Inverted AID gain detection"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        pk = pdata.get("pk")
        if pk is None:
            per_patient.append({"patient": pid, "inverted": False, "n_events": 0})
            continue
        
        dpk = denorm_pk(pk)
        if dpk is None:
            per_patient.append({"patient": pid, "inverted": False, "n_events": 0})
            continue
        
        steps_per_hour = 12
        activity = dpk["activity"]
        
        # Find correction events: high activity (bolus) followed by BG change
        # Look for spikes in insulin activity > 2 std above mean
        mean_act = np.nanmean(activity)
        std_act = np.nanstd(activity)
        if std_act < 1e-6:
            per_patient.append({"patient": pid, "inverted": False, "n_events": 0})
            continue
        
        threshold = mean_act + 2 * std_act
        correction_events = []
        
        i = 0
        while i < len(activity) - 3 * steps_per_hour:
            if activity[i] > threshold and not np.isnan(cgm[i]):
                # BG at correction time
                bg_at_corr = cgm[i]
                # BG 2-3 hours later
                future_window = cgm[i + 2*steps_per_hour:i + 3*steps_per_hour]
                future_valid = future_window[~np.isnan(future_window)]
                
                if len(future_valid) > 0 and bg_at_corr > 100:
                    bg_after = np.mean(future_valid)
                    # If BG was high (>150) and we corrected, it should go DOWN
                    expected_direction = -1 if bg_at_corr > 150 else 1
                    actual_direction = 1 if bg_after > bg_at_corr else -1
                    
                    correction_events.append({
                        "bg_before": float(bg_at_corr),
                        "bg_after": float(bg_after),
                        "expected": expected_direction,
                        "actual": actual_direction,
                        "correct": expected_direction == actual_direction,
                    })
                    i += 3 * steps_per_hour  # Skip ahead
                    continue
            i += 1
        
        n_events = len(correction_events)
        if n_events > 0:
            correct_frac = sum(1 for e in correction_events if e["correct"]) / n_events
            inverted = correct_frac < 0.4  # Less than 40% correct = likely inverted
            
            # Compute effective gain K
            deltas = [e["bg_after"] - e["bg_before"] for e in correction_events]
            mean_delta = np.mean(deltas)
            gain_sign = "positive" if mean_delta < 0 else "negative/inverted"
        else:
            correct_frac = 1.0
            inverted = False
            gain_sign = "unknown"
            mean_delta = 0.0
        
        per_patient.append({
            "patient": pid,
            "n_events": n_events,
            "correct_fraction": round(correct_frac, 3),
            "inverted": inverted,
            "gain_sign": gain_sign,
            "mean_bg_delta": round(float(mean_delta), 1),
        })
    
    results["per_patient"] = per_patient
    n_inverted = sum(1 for p in per_patient if p["inverted"])
    results["n_inverted"] = n_inverted
    results["n_patients"] = len(per_patient)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1392: Multi-Parameter Coordinated Adjustment
# ---------------------------------------------------------------------------
@register(1392)
def exp_multi_param(patients, detail=False):
    """Test coordinated multi-parameter adjustments vs sequential.
    
    Current pipeline adjusts one param at a time. Compare:
    (A) Sequential: fix basal first, then CR
    (B) Coordinated: adjust basal+CR simultaneously, accounting for interaction
    """
    results = {"name": "EXP-1392: Multi-parameter coordinated adjustment"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        steps_per_hour = 12
        n_days = len(cgm) // (24 * steps_per_hour)
        
        # Compute full metrics
        metrics = compute_window_metrics(cgm)
        if metrics is None:
            per_patient.append({"patient": pid, "method": "skip"})
            continue
        
        # Sequential approach: fix basal, then measure residual CR need
        basal_recs = []
        cr_recs = []
        drifts = compute_fasting_drift(cgm)
        mean_drift = np.mean(np.abs(drifts))
        
        if mean_drift > 5.0:
            basal_recs.append("basal")
        
        for meal, exc in metrics.get("excursions", {}).items():
            if meal != "breakfast" and exc > 70:
                cr_recs.append(f"{meal}_cr")
        
        sequential_recs = basal_recs + cr_recs
        
        # Coordinated approach: check if drift and excursion are correlated
        # If high drift causes high excursions, fixing basal alone may fix CR too
        day_drifts = []
        day_excursions = []
        for d in range(min(n_days, 180)):
            start = d * 24 * steps_per_hour
            day_cgm = cgm[start:start + 24*steps_per_hour]
            
            # Overnight drift
            overnight = day_cgm[:8*steps_per_hour]
            ov = overnight[~np.isnan(overnight)]
            if len(ov) > steps_per_hour:
                day_drift = abs((ov[-1] - ov[0]) / (len(ov) / steps_per_hour))
            else:
                day_drift = np.nan
            
            # Dinner excursion
            dinner = day_cgm[17*steps_per_hour:21*steps_per_hour] if len(day_cgm) > 21*steps_per_hour else np.array([])
            dv = dinner[~np.isnan(dinner)] if len(dinner) > 0 else np.array([])
            if len(dv) > 6:
                day_exc = np.max(dv) - np.min(dv)
            else:
                day_exc = np.nan
            
            if not np.isnan(day_drift) and not np.isnan(day_exc):
                day_drifts.append(day_drift)
                day_excursions.append(day_exc)
        
        if len(day_drifts) > 10:
            corr = np.corrcoef(day_drifts, day_excursions)[0, 1]
        else:
            corr = 0.0
        
        # If drift-excursion correlation > 0.3, fixing basal may fix CR
        coordinated_recs = list(sequential_recs)
        basal_fixes_cr = abs(corr) > 0.3 and len(basal_recs) > 0
        if basal_fixes_cr:
            coordinated_recs = basal_recs  # Only fix basal, CR may self-resolve
        
        per_patient.append({
            "patient": pid,
            "sequential_recs": sequential_recs,
            "coordinated_recs": coordinated_recs,
            "n_sequential": len(sequential_recs),
            "n_coordinated": len(coordinated_recs),
            "drift_excursion_corr": round(float(corr), 3) if not np.isnan(corr) else 0.0,
            "basal_fixes_cr": basal_fixes_cr,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    n_reduced = sum(1 for p in per_patient if p.get("n_coordinated", 0) < p.get("n_sequential", 0))
    results["n_reduced_by_coordination"] = n_reduced
    mean_corr = np.mean([p["drift_excursion_corr"] for p in per_patient if "drift_excursion_corr" in p])
    results["mean_drift_excursion_corr"] = round(float(mean_corr), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1393: Onboarding Templates
# ---------------------------------------------------------------------------
@register(1393)
def exp_onboarding(patients, detail=False):
    """Bootstrap new patient recommendations from archetype templates.
    
    From EXP-1388: needs-tuning Jaccard=0.53. Can we use this for onboarding?
    Method: leave-one-out — predict each patient's recs from others in archetype.
    """
    results = {"name": "EXP-1393: Onboarding templates from cross-patient transfer"}
    
    # Define archetypes (from EXP-1310)
    archetypes = {
        "well-calibrated": ["d", "h", "j", "k"],
        "needs-tuning": ["b", "c", "e", "f", "g", "i"],
        "miscalibrated": ["a"],
    }
    
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        metrics = compute_window_metrics(cgm)
        if metrics is None:
            continue
        
        # Get actual recommendations
        actual_recs = generate_recommendations(metrics)
        actual_params = set(r["param"] for r in actual_recs)
        
        # Find archetype
        arch = "unknown"
        for a, members in archetypes.items():
            if pid in members:
                arch = a
                break
        
        # Get other members' recommendations
        other_params = defaultdict(int)
        n_others = 0
        for other_pid, other_pdata in patients.items():
            if other_pid == pid:
                continue
            # Check same archetype
            other_arch = "unknown"
            for a, members in archetypes.items():
                if other_pid in members:
                    other_arch = a
                    break
            if other_arch != arch:
                continue
            
            other_metrics = compute_window_metrics(other_pdata["cgm"])
            if other_metrics is None:
                continue
            other_recs = generate_recommendations(other_metrics)
            for r in other_recs:
                other_params[r["param"]] += 1
            n_others += 1
        
        # Template: params recommended by >50% of archetype peers
        template_params = set()
        if n_others > 0:
            for param, count in other_params.items():
                if count / n_others >= 0.5:
                    template_params.add(param)
        
        # Compute overlap
        if actual_params or template_params:
            intersection = actual_params & template_params
            union = actual_params | template_params
            jaccard = len(intersection) / len(union) if union else 0.0
        else:
            jaccard = 1.0  # Both empty = perfect agreement
        
        per_patient.append({
            "patient": pid,
            "archetype": arch,
            "actual_params": sorted(actual_params),
            "template_params": sorted(template_params),
            "jaccard": round(jaccard, 3),
            "n_peers": n_others,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["mean_jaccard"] = round(np.mean([p["jaccard"] for p in per_patient]), 3)
    
    # Per archetype
    for arch in archetypes:
        arch_jaccards = [p["jaccard"] for p in per_patient if p["archetype"] == arch]
        if arch_jaccards:
            results[f"{arch}_mean_jaccard"] = round(np.mean(arch_jaccards), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1394: Auto Re-evaluation Scheduling
# ---------------------------------------------------------------------------
@register(1394)
def exp_auto_schedule(patients, detail=False):
    """Detect when therapy should be re-evaluated based on score trajectory.
    
    From EXP-1387: mean 4.3 regime changes per 6 months.
    Method: monitor therapy score in rolling windows, trigger re-eval when
    score drops >10 points or changes grade.
    """
    results = {"name": "EXP-1394: Auto re-evaluation scheduling"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        steps_per_hour = 12
        steps_per_day = 24 * steps_per_hour
        window_days = 14
        window_steps = window_days * steps_per_day
        stride_days = 7
        stride_steps = stride_days * steps_per_day
        
        scores = []
        grades = []
        
        start = 0
        while start + window_steps <= len(cgm):
            window_cgm = cgm[start:start + window_steps]
            metrics = compute_window_metrics(window_cgm)
            score = compute_therapy_score(metrics)
            grade = get_grade(score)
            scores.append(score)
            grades.append(grade)
            start += stride_steps
        
        if len(scores) < 2:
            per_patient.append({"patient": pid, "n_triggers": 0, "n_windows": 0})
            continue
        
        # Detect trigger events
        triggers = []
        for i in range(1, len(scores)):
            score_drop = scores[i-1] - scores[i]
            grade_change = grades[i] != grades[i-1]
            
            if score_drop > 10 or grade_change:
                triggers.append({
                    "window": i,
                    "score_before": round(scores[i-1], 1),
                    "score_after": round(scores[i], 1),
                    "grade_before": grades[i-1],
                    "grade_after": grades[i],
                    "reason": "score_drop" if score_drop > 10 else "grade_change",
                })
        
        # Compute optimal re-eval interval
        if triggers:
            intervals = [triggers[0]["window"] * stride_days]
            for i in range(1, len(triggers)):
                intervals.append((triggers[i]["window"] - triggers[i-1]["window"]) * stride_days)
            mean_interval = np.mean(intervals)
        else:
            mean_interval = len(scores) * stride_days  # Never triggered = very stable
        
        per_patient.append({
            "patient": pid,
            "n_windows": len(scores),
            "n_triggers": len(triggers),
            "mean_interval_days": round(float(mean_interval), 0),
            "triggers": triggers[:5] if detail else [],
            "score_range": [round(min(scores), 1), round(max(scores), 1)],
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    all_intervals = [p["mean_interval_days"] for p in per_patient if p["n_triggers"] > 0]
    results["mean_reeval_interval"] = round(float(np.mean(all_intervals)), 0) if all_intervals else 999
    results["n_never_triggered"] = sum(1 for p in per_patient if p["n_triggers"] == 0)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1395: Confidence-Gated Output
# ---------------------------------------------------------------------------
@register(1395)
def exp_confidence_gate(patients, detail=False):
    """Only output recommendations exceeding confidence threshold.
    
    From EXP-1379: high-conf CR agreement 80% vs 0% low-conf.
    Method: generate all recs, filter by confidence, measure precision/recall.
    """
    results = {"name": "EXP-1395: Confidence-gated recommendation output"}
    per_patient = []
    
    thresholds = [0.3, 0.5, 0.7, 0.9]
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        metrics = compute_window_metrics(cgm)
        if metrics is None:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        all_recs = generate_recommendations(metrics)
        
        # Split data and get "ground truth" from second half
        half = len(cgm) // 2
        metrics_h2 = compute_window_metrics(cgm[half:])
        gt_recs = generate_recommendations(metrics_h2) if metrics_h2 else []
        gt_params = set(r["param"] for r in gt_recs)
        
        per_threshold = {}
        for thresh in thresholds:
            filtered = [r for r in all_recs if r.get("confidence", 0) >= thresh]
            filtered_params = set(r["param"] for r in filtered)
            
            # Precision: of what we recommend, how many are in ground truth
            if filtered_params:
                precision = len(filtered_params & gt_params) / len(filtered_params)
            else:
                precision = 1.0  # Nothing recommended = no false positives
            
            # Recall: of ground truth, how many did we catch
            if gt_params:
                recall = len(filtered_params & gt_params) / len(gt_params)
            else:
                recall = 1.0
            
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            per_threshold[f"t{thresh}"] = {
                "n_recs": len(filtered),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            }
        
        per_patient.append({
            "patient": pid,
            "n_all_recs": len(all_recs),
            "n_gt_recs": len(gt_recs),
            "thresholds": per_threshold,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Aggregate per threshold
    for thresh in thresholds:
        key = f"t{thresh}"
        precisions = [p["thresholds"][key]["precision"] for p in per_patient if "thresholds" in p]
        recalls = [p["thresholds"][key]["recall"] for p in per_patient if "thresholds" in p]
        f1s = [p["thresholds"][key]["f1"] for p in per_patient if "thresholds" in p]
        results[f"mean_precision_{key}"] = round(np.mean(precisions), 3) if precisions else 0
        results[f"mean_recall_{key}"] = round(np.mean(recalls), 3) if recalls else 0
        results[f"mean_f1_{key}"] = round(np.mean(f1s), 3) if f1s else 0
    
    return results


# ---------------------------------------------------------------------------
# EXP-1396: Meal-Time-Specific CR Triage
# ---------------------------------------------------------------------------
@register(1396)
def exp_meal_specific_cr(patients, detail=False):
    """Analyze CR adjustment needs separately for each meal time.
    
    Prior findings: dinner worst (77 mg/dL), breakfast unreliable (20% agreement).
    Method: compute per-meal excursion distributions and adjustment magnitudes.
    """
    results = {"name": "EXP-1396: Meal-time-specific CR triage"}
    per_patient = []
    
    steps_per_hour = 12
    meal_blocks = {
        "breakfast": (6*steps_per_hour, 10*steps_per_hour),
        "lunch": (11*steps_per_hour, 15*steps_per_hour),
        "dinner": (17*steps_per_hour, 21*steps_per_hour),
    }
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // (24 * steps_per_hour)
        
        meal_stats = {}
        for meal, (start_h, end_h) in meal_blocks.items():
            excursions = []
            flagged_days = 0
            
            for d in range(min(n_days, 180)):
                day_start = d * 24 * steps_per_hour
                block = cgm[day_start + start_h:day_start + end_h]
                valid = block[~np.isnan(block)]
                if len(valid) > 6:
                    exc = np.max(valid) - np.min(valid)
                    excursions.append(exc)
                    if exc > 70:
                        flagged_days += 1
            
            if excursions:
                meal_stats[meal] = {
                    "mean_excursion": round(float(np.mean(excursions)), 1),
                    "median_excursion": round(float(np.median(excursions)), 1),
                    "p90_excursion": round(float(np.percentile(excursions, 90)), 1),
                    "flag_rate": round(flagged_days / len(excursions), 3),
                    "n_days": len(excursions),
                    "suggested_cr_change": round(-0.20 if np.mean(excursions) > 70 else 0.0, 2),
                }
        
        # Rank meals by urgency
        ranked = sorted(meal_stats.items(), 
                       key=lambda x: x[1]["mean_excursion"], reverse=True)
        
        per_patient.append({
            "patient": pid,
            "meals": meal_stats,
            "priority_meal": ranked[0][0] if ranked else "none",
            "priority_excursion": ranked[0][1]["mean_excursion"] if ranked else 0,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Aggregate meal rankings
    priority_counts = defaultdict(int)
    for p in per_patient:
        priority_counts[p["priority_meal"]] += 1
    results["priority_distribution"] = dict(priority_counts)
    
    # Mean excursions per meal across all patients
    for meal in meal_blocks:
        excursions = [p["meals"][meal]["mean_excursion"] for p in per_patient 
                     if meal in p["meals"]]
        results[f"{meal}_mean_excursion"] = round(np.mean(excursions), 1) if excursions else 0
    
    return results


# ---------------------------------------------------------------------------
# EXP-1397: Recommendation Magnitude Calibration
# ---------------------------------------------------------------------------
@register(1397)
def exp_magnitude_cal(patients, detail=False):
    """Calibrate how much to adjust each parameter, not just direction.
    
    Current: fixed 20% CR tightening, drift-proportional basal.
    Method: compute dose-response from within-patient variation.
    """
    results = {"name": "EXP-1397: Recommendation magnitude calibration"}
    per_patient = []
    
    steps_per_hour = 12
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // (24 * steps_per_hour)
        
        # Basal magnitude: relationship between drift rate and TIR impact
        overnight_drifts = []
        next_day_tirs = []
        
        for d in range(min(n_days - 1, 179)):
            day_start = d * 24 * steps_per_hour
            overnight = cgm[day_start:day_start + 8*steps_per_hour]
            ov = overnight[~np.isnan(overnight)]
            
            if len(ov) > steps_per_hour:
                drift = abs((ov[-1] - ov[0]) / (len(ov) / steps_per_hour))
                
                # Next day TIR
                next_day = cgm[day_start + 24*steps_per_hour:day_start + 48*steps_per_hour]
                nv = next_day[~np.isnan(next_day)]
                if len(nv) > steps_per_hour * 6:
                    tir = np.mean((nv >= 70) & (nv <= 180)) * 100
                    overnight_drifts.append(drift)
                    next_day_tirs.append(tir)
        
        # Fit drift -> TIR relationship
        if len(overnight_drifts) > 20:
            try:
                if np.std(overnight_drifts) > 1e-6:
                    coeffs = np.polyfit(overnight_drifts, next_day_tirs, 1)
                    slope = coeffs[0]  # TIR change per unit drift
                else:
                    slope = 0.0
            except (np.linalg.LinAlgError, ValueError):
                slope = 0.0
        else:
            slope = 0.0
        
        # CR magnitude: relationship between excursion size and optimal tightening
        # Use quartile analysis
        dinner_excursions = []
        for d in range(min(n_days, 180)):
            day_start = d * 24 * steps_per_hour
            dinner = cgm[day_start + 17*steps_per_hour:day_start + 21*steps_per_hour]
            dv = dinner[~np.isnan(dinner)]
            if len(dv) > 6:
                dinner_excursions.append(np.max(dv) - np.min(dv))
        
        if dinner_excursions:
            q25 = np.percentile(dinner_excursions, 25)
            q75 = np.percentile(dinner_excursions, 75)
            mean_exc = np.mean(dinner_excursions)
            
            # Suggested CR tightening scaled by severity
            if mean_exc > 100:
                cr_adjust = -0.30  # 30% tightening for severe
            elif mean_exc > 70:
                cr_adjust = -0.20  # 20% for moderate
            elif mean_exc > 50:
                cr_adjust = -0.10  # 10% for mild
            else:
                cr_adjust = 0.0
        else:
            q25 = q75 = mean_exc = 0.0
            cr_adjust = 0.0
        
        per_patient.append({
            "patient": pid,
            "drift_tir_slope": round(float(slope), 3),
            "n_drift_days": len(overnight_drifts),
            "mean_dinner_excursion": round(float(mean_exc), 1),
            "excursion_q25": round(float(q25), 1),
            "excursion_q75": round(float(q75), 1),
            "suggested_cr_adjust": cr_adjust,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Distribution of CR adjustments
    adj_counts = defaultdict(int)
    for p in per_patient:
        adj_counts[str(p["suggested_cr_adjust"])] += 1
    results["cr_adjust_distribution"] = dict(adj_counts)
    
    mean_slope = np.mean([p["drift_tir_slope"] for p in per_patient])
    results["mean_drift_tir_slope"] = round(float(mean_slope), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1398: Data Quality Degradation Curves
# ---------------------------------------------------------------------------
@register(1398)
def exp_data_quality(patients, detail=False):
    """How does pipeline accuracy degrade with data quality?
    
    Method: artificially degrade data (add gaps, noise) and measure
    score stability and recommendation consistency.
    """
    results = {"name": "EXP-1398: Data quality degradation curves"}
    per_patient = []
    
    degradation_levels = {
        "clean": {"gap_rate": 0.0, "noise_std": 0.0},
        "mild_gaps": {"gap_rate": 0.1, "noise_std": 0.0},
        "moderate_gaps": {"gap_rate": 0.2, "noise_std": 0.0},
        "severe_gaps": {"gap_rate": 0.4, "noise_std": 0.0},
        "mild_noise": {"gap_rate": 0.0, "noise_std": 5.0},
        "moderate_noise": {"gap_rate": 0.0, "noise_std": 15.0},
        "combined": {"gap_rate": 0.15, "noise_std": 10.0},
    }
    
    rng = np.random.RandomState(42)
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"].copy()
        
        # Baseline
        base_metrics = compute_window_metrics(cgm)
        base_score = compute_therapy_score(base_metrics)
        base_recs = generate_recommendations(base_metrics) if base_metrics else []
        base_params = set(r["param"] for r in base_recs)
        
        degraded_results = {}
        for level_name, params in degradation_levels.items():
            degraded = cgm.copy()
            
            # Add gaps
            if params["gap_rate"] > 0:
                n_gaps = int(len(degraded) * params["gap_rate"])
                gap_indices = rng.choice(len(degraded), n_gaps, replace=False)
                degraded[gap_indices] = np.nan
            
            # Add noise
            if params["noise_std"] > 0:
                valid_mask = ~np.isnan(degraded)
                noise = rng.normal(0, params["noise_std"], np.sum(valid_mask))
                degraded[valid_mask] += noise
            
            deg_metrics = compute_window_metrics(degraded)
            deg_score = compute_therapy_score(deg_metrics)
            deg_recs = generate_recommendations(deg_metrics) if deg_metrics else []
            deg_params = set(r["param"] for r in deg_recs)
            
            # Consistency with baseline
            if base_params or deg_params:
                jaccard = len(base_params & deg_params) / len(base_params | deg_params) if (base_params | deg_params) else 1.0
            else:
                jaccard = 1.0
            
            degraded_results[level_name] = {
                "score": round(deg_score, 1),
                "score_delta": round(deg_score - base_score, 1),
                "rec_jaccard": round(jaccard, 3),
                "n_recs": len(deg_recs),
            }
        
        per_patient.append({
            "patient": pid,
            "base_score": round(base_score, 1),
            "degraded": degraded_results,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Aggregate by degradation level
    for level_name in degradation_levels:
        scores = [p["degraded"][level_name]["score_delta"] for p in per_patient]
        jaccards = [p["degraded"][level_name]["rec_jaccard"] for p in per_patient]
        results[f"{level_name}_mean_score_delta"] = round(float(np.mean(scores)), 1)
        results[f"{level_name}_mean_jaccard"] = round(float(np.mean(jaccards)), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1399: Pipeline Sensitivity Analysis
# ---------------------------------------------------------------------------
@register(1399)
def exp_sensitivity(patients, detail=False):
    """How robust is the pipeline to threshold perturbation?
    
    Method: perturb each threshold (drift, excursion, ISF_ratio) by ±20%
    and measure grade stability and recommendation consistency.
    """
    results = {"name": "EXP-1399: Pipeline sensitivity to threshold perturbation"}
    
    base_thresholds = {"drift": 5.0, "excursion": 70.0, "isf_ratio": 2.0}
    perturbations = {
        "base": {"drift": 5.0, "excursion": 70.0, "isf_ratio": 2.0},
        "drift_low": {"drift": 4.0, "excursion": 70.0, "isf_ratio": 2.0},
        "drift_high": {"drift": 6.0, "excursion": 70.0, "isf_ratio": 2.0},
        "excursion_low": {"drift": 5.0, "excursion": 56.0, "isf_ratio": 2.0},
        "excursion_high": {"drift": 5.0, "excursion": 84.0, "isf_ratio": 2.0},
        "all_tight": {"drift": 4.0, "excursion": 56.0, "isf_ratio": 1.6},
        "all_loose": {"drift": 6.0, "excursion": 84.0, "isf_ratio": 2.4},
    }
    
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        metrics = compute_window_metrics(cgm)
        if metrics is None:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        perturb_results = {}
        for pname, thresholds in perturbations.items():
            recs = generate_recommendations(metrics, thresholds)
            score = compute_therapy_score(metrics)
            grade = get_grade(score)
            rec_params = set(r["param"] for r in recs)
            
            perturb_results[pname] = {
                "grade": grade,
                "n_recs": len(recs),
                "params": sorted(rec_params),
            }
        
        # Compute stability: how many perturbations change the grade?
        base_grade = perturb_results["base"]["grade"]
        base_params = set(perturb_results["base"]["params"])
        
        grade_changes = sum(1 for p in perturb_results.values() if p["grade"] != base_grade)
        param_changes = sum(
            1 for pname, p in perturb_results.items() 
            if pname != "base" and set(p["params"]) != base_params
        )
        
        per_patient.append({
            "patient": pid,
            "base_grade": base_grade,
            "n_grade_changes": grade_changes,
            "n_param_changes": param_changes,
            "perturbations": perturb_results,
            "grade_stability": round(1 - grade_changes / len(perturbations), 3),
            "param_stability": round(1 - param_changes / (len(perturbations) - 1), 3),
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    stabilities = [p.get("grade_stability", 1) for p in per_patient if "grade_stability" in p]
    results["mean_grade_stability"] = round(float(np.mean(stabilities)), 3) if stabilities else 0
    param_stabs = [p.get("param_stability", 1) for p in per_patient if "param_stability" in p]
    results["mean_param_stability"] = round(float(np.mean(param_stabs)), 3) if param_stabs else 0
    
    return results


# ---------------------------------------------------------------------------
# EXP-1400: Clinical Summary Generation
# ---------------------------------------------------------------------------
@register(1400)
def exp_clinical_summary(patients, detail=False):
    """Generate validated clinical summary for each patient.
    
    Combines all pipeline components into a single actionable output:
    preconditions → score → grade → ranked recommendations → timeline.
    This is the "production output" experiment.
    """
    results = {"name": "EXP-1400: Clinical summary generation (production output)"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        insulin = pdata.get("insulin")
        pk = pdata.get("pk")
        
        # Step 1: Preconditions
        precond = assess_preconditions(cgm, insulin, pk)
        
        # Step 2: Metrics & Score
        metrics = compute_window_metrics(cgm)
        score = compute_therapy_score(metrics)
        grade = get_grade(score)
        
        # Step 3: Recommendations
        recs = generate_recommendations(metrics) if metrics else []
        
        # Step 4: Impact ranking (from EXP-1386)
        # Estimate TIR gain per parameter
        for rec in recs:
            if rec["param"] == "basal":
                rec["estimated_tir_gain"] = min(abs(metrics.get("drift", 0)) * 0.8, 8.0)
            else:
                meal = rec["param"].replace("_cr", "")
                exc = metrics.get("excursions", {}).get(meal, 0)
                rec["estimated_tir_gain"] = min(exc * 0.03, 3.0)
        
        recs.sort(key=lambda r: r.get("estimated_tir_gain", 0), reverse=True)
        
        # Step 5: Temporal context
        steps_per_day = 24 * 12
        n_days = len(cgm) // steps_per_day
        half = len(cgm) // 2
        
        metrics_h1 = compute_window_metrics(cgm[:half])
        metrics_h2 = compute_window_metrics(cgm[half:])
        score_h1 = compute_therapy_score(metrics_h1)
        score_h2 = compute_therapy_score(metrics_h2)
        
        if score_h2 > score_h1 + 5:
            trajectory = "improving"
        elif score_h2 < score_h1 - 5:
            trajectory = "declining"
        else:
            trajectory = "stable"
        
        # Step 6: Data sufficiency
        data_quality = "confident" if n_days >= 60 else ("preliminary" if n_days >= 30 else "insufficient")
        
        # Step 7: Clinical narrative
        if grade == "A":
            narrative = "Therapy well-calibrated. No adjustments needed. Continue current settings."
        elif grade == "B":
            top_rec = recs[0]["param"] if recs else "none"
            narrative = f"Therapy adequate with minor opportunity. Consider adjusting {top_rec}."
        elif grade == "C":
            rec_list = ", ".join(r["param"] for r in recs[:2])
            narrative = f"Active triage recommended. Priority adjustments: {rec_list}."
        else:  # D
            rec_list = ", ".join(r["param"] for r in recs[:3])
            narrative = f"Multiple adjustments needed urgently. Address: {rec_list}."
        
        if not precond["pass"]:
            narrative = f"Insufficient data quality (met {precond['total_met']}/3 preconditions). " + narrative
        
        summary = {
            "patient": pid,
            "data_days": n_days,
            "data_quality": data_quality,
            "preconditions": {
                "cgm_coverage": round(precond["cgm_coverage"], 1),
                "insulin_coverage": round(precond["insulin_coverage"], 1),
                "pass": precond["pass"],
            },
            "score": round(score, 1),
            "grade": grade,
            "trajectory": trajectory,
            "score_trend": {
                "first_half": round(score_h1, 1),
                "second_half": round(score_h2, 1),
            },
            "recommendations": [
                {
                    "param": r["param"],
                    "direction": r.get("direction", "unknown"),
                    "magnitude": r.get("magnitude", 0),
                    "confidence": round(r.get("confidence", 0), 2),
                    "estimated_tir_gain": round(r.get("estimated_tir_gain", 0), 1),
                }
                for r in recs
            ],
            "narrative": narrative,
        }
        
        per_patient.append(summary)
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Grade distribution
    grades = defaultdict(int)
    for p in per_patient:
        grades[p["grade"]] += 1
    results["grade_distribution"] = dict(grades)
    
    # Trajectory distribution
    trajs = defaultdict(int)
    for p in per_patient:
        trajs[p["trajectory"]] += 1
    results["trajectory_distribution"] = dict(trajs)
    
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EXP-1391-1400: Pipeline refinement")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--max-patients", type=int, default=11)
    parser.add_argument("--only", type=int, nargs="+", help="Run specific experiment(s)")
    args = parser.parse_args()

    patients = load_patients(args.max_patients)
    if not patients:
        print("ERROR: No patient data found")
        sys.exit(1)

    # Precondition report
    print("\n" + "=" * 60)
    print("PRECONDITION ASSESSMENT")
    print("=" * 60)
    for pid, pdata in sorted(patients.items()):
        precond = assess_preconditions(pdata["cgm"], pdata.get("insulin"), pdata.get("pk"))
        print(f"  {pid}: {precond['total_met']}/3 met | CGM={precond['cgm_coverage']:.1f}% ins={precond['insulin_coverage']:.1f}%")

    exp_ids = args.only if args.only else sorted(EXPERIMENTS.keys())
    all_results = {}

    for exp_id in exp_ids:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered, skipping")
            continue

        print(f"\n{'=' * 60}")
        print(f"EXP-{exp_id}: {EXPERIMENTS[exp_id].__doc__.strip().split(chr(10))[0]}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = EXPERIMENTS[exp_id](patients, detail=args.detail)
            elapsed = time.time() - t0
            result["elapsed_sec"] = round(elapsed, 1)
            all_results[exp_id] = result
            print(f"  Completed in {elapsed:.1f}s")

            # Print key metrics
            for k, v in result.items():
                if k in ("name", "per_patient", "elapsed_sec", "experiment", "timestamp"):
                    continue
                print(f"  {k}: {v}")

            if args.save:
                out_dir = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"exp-{exp_id}_therapy.json"
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved → {out_path}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()
            all_results[exp_id] = {"error": str(e), "elapsed_sec": round(elapsed, 1)}

    # Summary
    print(f"\n{'=' * 60}")
    print("PIPELINE REFINEMENT & PRODUCTION READINESS SUMMARY")
    print(f"{'=' * 60}")
    for exp_id, result in sorted(all_results.items()):
        name = result.get("name", f"EXP-{exp_id}")
        if "error" in result:
            print(f"  {name}: FAILED - {result['error']}")
        else:
            # Print most relevant metric
            key_metrics = {k: v for k, v in result.items() 
                         if k not in ("name", "per_patient", "elapsed_sec", "experiment", "timestamp")
                         and not isinstance(v, (dict, list))}
            summary = ", ".join(f"{k}={v}" for k, v in list(key_metrics.items())[:3])
            print(f"  {name}: {summary}")


if __name__ == "__main__":
    main()
