#!/usr/bin/env python3
"""EXP-1401–1410: Extended Horizons, Dawn Phenomenon & Fidelity Gating.

Building on 120 validated experiments, this batch addresses:
- Dawn phenomenon detection and basal pattern analysis
- Time-of-day basal segmentation
- Conservation law fidelity as data quality gate
- Multi-week and monthly trend analysis
- DIA-horizon therapy metrics
- Seasonal pattern detection
- Multi-segment basal optimization
- Fidelity-filtered recommendations
- Weekly aggregation vs daily
- Comprehensive therapy timeline

Run: PYTHONPATH=tools python -m cgmencode.exp_clinical_1401 --detail --save --max-patients 11
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

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / "externals" / "ns-data" / "patients")

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR


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


def denorm_pk(pk):
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


def compute_therapy_score(tir, drift, max_excursion, cv, weights=None):
    """Compute therapy health score 0-100 with TIR-heavy weights."""
    if weights is None:
        weights = [60, 15, 15, 5, 5]
    tir_score = min(tir, 100) / 100 * weights[0]
    basal_ok = 1.0 if drift < 5.0 else 0.0
    cr_ok = 1.0 if max_excursion < 70 else 0.0
    isf_ok = 1.0
    cv_ok = 1.0 if cv < 36 else 0.0
    return tir_score + basal_ok * weights[1] + cr_ok * weights[2] + isf_ok * weights[3] + cv_ok * weights[4]


def get_grade(score):
    if score >= 80: return "A"
    elif score >= 65: return "B"
    elif score >= 50: return "C"
    else: return "D"


EXPERIMENTS = {}

def register(exp_id):
    def decorator(func):
        EXPERIMENTS[exp_id] = func
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-1401: Dawn Phenomenon Detection
# ---------------------------------------------------------------------------
@register(1401)
def exp_dawn_phenomenon(patients, detail=False):
    """Detect dawn phenomenon — pre-breakfast BG rise without carbs/bolus.
    
    Dawn phenomenon causes 4-6am BG rise from cortisol/growth hormone.
    This is a basal pattern issue, not addressable by CR adjustment.
    """
    results = {"name": "EXP-1401: Dawn phenomenon detection"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        bolus = pdata["bolus"]
        carbs = pdata["carbs"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        dawn_rises = []
        non_dawn_rises = []
        dawn_days = 0
        
        for d in range(min(n_days, 180)):
            start = d * STEPS_PER_DAY
            
            # Dawn window: 4am-7am (indices 48-84)
            dawn_start = start + 4 * STEPS_PER_HOUR
            dawn_end = start + 7 * STEPS_PER_HOUR
            dawn_cgm = cgm[dawn_start:dawn_end]
            dawn_valid = dawn_cgm[~np.isnan(dawn_cgm)]
            
            if len(dawn_valid) < STEPS_PER_HOUR:
                continue
            
            # Check for carbs/bolus during dawn window
            dawn_carbs = carbs[dawn_start:dawn_end]
            dawn_bolus = bolus[dawn_start:dawn_end]
            has_meal = np.nansum(dawn_carbs) > 5 or np.nansum(dawn_bolus) > 0.3
            
            # Pre-dawn BG (3-4am = stable overnight baseline)
            pre_dawn = cgm[start + 3*STEPS_PER_HOUR:dawn_start]
            pre_valid = pre_dawn[~np.isnan(pre_dawn)]
            
            if len(pre_valid) < 6:
                continue
            
            rise = dawn_valid[-1] - np.mean(pre_valid)
            
            if not has_meal:
                dawn_rises.append(rise)
                if rise > 15:  # >15 mg/dL rise = clinically significant
                    dawn_days += 1
            else:
                non_dawn_rises.append(rise)
        
        total_days = len(dawn_rises) + len(non_dawn_rises)
        
        if dawn_rises:
            mean_rise = float(np.mean(dawn_rises))
            median_rise = float(np.median(dawn_rises))
            p90_rise = float(np.percentile(dawn_rises, 90))
            dawn_prevalence = dawn_days / len(dawn_rises)
        else:
            mean_rise = median_rise = p90_rise = 0.0
            dawn_prevalence = 0.0
        
        per_patient.append({
            "patient": pid,
            "n_dawn_days": len(dawn_rises),
            "n_meal_days": len(non_dawn_rises),
            "mean_dawn_rise": round(mean_rise, 1),
            "median_dawn_rise": round(median_rise, 1),
            "p90_dawn_rise": round(p90_rise, 1),
            "dawn_prevalence": round(dawn_prevalence, 3),
            "clinically_significant": dawn_prevalence > 0.3 and mean_rise > 10,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    n_significant = sum(1 for p in per_patient if p["clinically_significant"])
    results["n_dawn_significant"] = n_significant
    results["mean_dawn_rise"] = round(float(np.mean([p["mean_dawn_rise"] for p in per_patient])), 1)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1402: Time-of-Day Basal Segmentation
# ---------------------------------------------------------------------------
@register(1402)
def exp_basal_segments(patients, detail=False):
    """Analyze basal needs across 4 time segments.
    
    Segments: overnight (0-6), morning (6-12), afternoon (12-18), evening (18-24).
    Compare drift rates per segment to detect time-varying basal needs.
    """
    results = {"name": "EXP-1402: Time-of-day basal segmentation"}
    per_patient = []
    
    segments = {
        "overnight": (0, 6),
        "morning": (6, 12),
        "afternoon": (12, 18),
        "evening": (18, 24),
    }
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        bolus = pdata["bolus"]
        carbs = pdata["carbs"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        segment_drifts = {seg: [] for seg in segments}
        
        for d in range(min(n_days, 180)):
            start = d * STEPS_PER_DAY
            
            for seg_name, (h_start, h_end) in segments.items():
                seg_start = start + h_start * STEPS_PER_HOUR
                seg_end = start + h_end * STEPS_PER_HOUR
                seg_cgm = cgm[seg_start:seg_end]
                seg_valid = seg_cgm[~np.isnan(seg_cgm)]
                
                if len(seg_valid) < 2 * STEPS_PER_HOUR:
                    continue
                
                # For overnight/fasting segments, compute drift
                # For meal segments, only use fasting periods (no carbs in prior 2h)
                if seg_name in ("overnight",):
                    drift = (seg_valid[-1] - seg_valid[0]) / (len(seg_valid) / STEPS_PER_HOUR)
                    segment_drifts[seg_name].append(drift)
                else:
                    # Check for carbs in this segment
                    seg_carbs = carbs[seg_start:seg_end]
                    if np.nansum(seg_carbs) < 3:  # Near-fasting
                        drift = (seg_valid[-1] - seg_valid[0]) / (len(seg_valid) / STEPS_PER_HOUR)
                        segment_drifts[seg_name].append(drift)
        
        seg_stats = {}
        for seg_name, drifts in segment_drifts.items():
            if drifts:
                seg_stats[seg_name] = {
                    "mean_drift": round(float(np.mean(drifts)), 2),
                    "std_drift": round(float(np.std(drifts)), 2),
                    "n_periods": len(drifts),
                    "flagged": abs(np.mean(drifts)) > 5.0,
                }
            else:
                seg_stats[seg_name] = {
                    "mean_drift": 0.0, "std_drift": 0.0,
                    "n_periods": 0, "flagged": False,
                }
        
        # Detect which segments need different basal
        n_flagged = sum(1 for s in seg_stats.values() if s["flagged"])
        needs_pattern = n_flagged >= 2  # 2+ segments flagged = needs basal pattern
        
        per_patient.append({
            "patient": pid,
            "segments": seg_stats,
            "n_flagged_segments": n_flagged,
            "needs_basal_pattern": needs_pattern,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["n_needs_pattern"] = sum(1 for p in per_patient if p["needs_basal_pattern"])
    
    return results


# ---------------------------------------------------------------------------
# EXP-1403: Conservation Law Fidelity Scoring
# ---------------------------------------------------------------------------
@register(1403)
def exp_fidelity_scoring(patients, detail=False):
    """Score how closely each patient's data obeys glucose conservation law.
    
    Conservation: ΔBG = supply - demand + noise
    Where supply = carbs + hepatic, demand = insulin activity
    High fidelity = physics model works well = recommendations more reliable.
    """
    results = {"name": "EXP-1403: Conservation law fidelity scoring"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        pk = pdata.get("pk")
        
        if pk is None:
            per_patient.append({
                "patient": pid, "fidelity_score": 0.0,
                "r2": -999, "mean_residual": 0, "skip": True,
            })
            continue
        
        dpk = denorm_pk(pk)
        if dpk is None:
            per_patient.append({
                "patient": pid, "fidelity_score": 0.0,
                "r2": -999, "mean_residual": 0, "skip": True,
            })
            continue
        
        # ΔBG (actual glucose change)
        dg = np.diff(cgm)
        
        # Supply - demand from PK
        supply = dpk["carb_rate"][:-1] + dpk["hepatic"][:-1]
        demand = dpk["activity"][:-1]
        predicted_change = supply - demand
        
        # Mask valid points
        valid = ~np.isnan(dg) & ~np.isnan(predicted_change) & (np.abs(dg) < 50)
        
        if np.sum(valid) < 1000:
            per_patient.append({
                "patient": pid, "fidelity_score": 0.0,
                "r2": -999, "mean_residual": 0, "n_valid": int(np.sum(valid)),
            })
            continue
        
        dg_v = dg[valid]
        pred_v = predicted_change[valid]
        
        # R² as primary fidelity measure
        ss_res = np.sum((dg_v - pred_v) ** 2)
        ss_tot = np.sum((dg_v - np.mean(dg_v)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        
        # Mean absolute residual
        mean_residual = float(np.mean(np.abs(dg_v - pred_v)))
        
        # Fidelity score 0-100
        # R² > 0 = physics explains variance, R² < 0 = worse than mean
        if r2 > 0:
            fidelity = min(r2 * 100, 100)
        else:
            fidelity = max(0, 50 + r2 * 50)  # Map [-1, 0] to [0, 50]
        
        # Compute per-day fidelity for temporal analysis
        n_days = len(cgm) // STEPS_PER_DAY
        daily_fidelities = []
        for d in range(min(n_days, 180)):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            day_dg = dg[start:min(end-1, len(dg))]
            day_pred = predicted_change[start:min(end-1, len(predicted_change))]
            day_valid = ~np.isnan(day_dg) & ~np.isnan(day_pred) & (np.abs(day_dg) < 50)
            
            if np.sum(day_valid) > 50:
                ss_r = np.sum((day_dg[day_valid] - day_pred[day_valid]) ** 2)
                ss_t = np.sum((day_dg[day_valid] - np.mean(day_dg[day_valid])) ** 2)
                day_r2 = 1 - ss_r / ss_t if ss_t > 0 else 0
                daily_fidelities.append(day_r2)
        
        per_patient.append({
            "patient": pid,
            "fidelity_score": round(float(fidelity), 1),
            "r2": round(float(r2), 4),
            "mean_residual": round(mean_residual, 2),
            "n_valid": int(np.sum(valid)),
            "daily_r2_mean": round(float(np.mean(daily_fidelities)), 4) if daily_fidelities else 0,
            "daily_r2_std": round(float(np.std(daily_fidelities)), 4) if daily_fidelities else 0,
            "n_high_fidelity_days": sum(1 for r in daily_fidelities if r > 0),
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["mean_fidelity"] = round(float(np.mean([p["fidelity_score"] for p in per_patient if not p.get("skip")])), 1)
    results["mean_r2"] = round(float(np.mean([p["r2"] for p in per_patient if p["r2"] > -999])), 4)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1404: Multi-Week Trend Analysis
# ---------------------------------------------------------------------------
@register(1404)
def exp_multiweek_trends(patients, detail=False):
    """Analyze therapy trends at weekly, biweekly, and monthly granularity.
    
    Compare trend detection at different aggregation scales.
    """
    results = {"name": "EXP-1404: Multi-week trend analysis"}
    per_patient = []
    
    scales = {
        "weekly": 7,
        "biweekly": 14,
        "monthly": 30,
        "bimonthly": 60,
    }
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        scale_results = {}
        for scale_name, window_days in scales.items():
            window_steps = window_days * STEPS_PER_DAY
            
            scores = []
            tirs = []
            
            start = 0
            while start + window_steps <= len(cgm):
                window = cgm[start:start + window_steps]
                valid = window[~np.isnan(window)]
                
                if len(valid) > STEPS_PER_DAY:
                    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
                    mean_bg = np.mean(valid)
                    cv = np.std(valid) / mean_bg * 100 if mean_bg > 0 else 99
                    
                    # Simple drift for this window
                    overnight_drifts = []
                    for d in range(window_days):
                        d_start = d * STEPS_PER_DAY
                        overnight = window[d_start:d_start + 8*STEPS_PER_HOUR]
                        ov = overnight[~np.isnan(overnight)]
                        if len(ov) > STEPS_PER_HOUR:
                            drift = abs((ov[-1] - ov[0]) / (len(ov) / STEPS_PER_HOUR))
                            overnight_drifts.append(drift)
                    
                    mean_drift = np.mean(overnight_drifts) if overnight_drifts else 0
                    score = compute_therapy_score(tir, mean_drift, 70, cv)
                    scores.append(score)
                    tirs.append(tir)
                
                start += window_steps
            
            if len(scores) >= 2:
                # Linear trend
                try:
                    if np.std(scores) > 1e-6:
                        x = np.arange(len(scores))
                        slope = np.polyfit(x, scores, 1)[0]
                    else:
                        slope = 0.0
                except (np.linalg.LinAlgError, ValueError):
                    slope = 0.0
                
                trend = "improving" if slope > 1.0 else ("declining" if slope < -1.0 else "stable")
            else:
                slope = 0.0
                trend = "insufficient"
            
            scale_results[scale_name] = {
                "n_windows": len(scores),
                "mean_score": round(float(np.mean(scores)), 1) if scores else 0,
                "score_trend_slope": round(float(slope), 3),
                "trend": trend,
                "tir_range": [round(float(min(tirs)), 1), round(float(max(tirs)), 1)] if tirs else [0, 0],
            }
        
        per_patient.append({
            "patient": pid,
            "n_days": n_days,
            "scales": scale_results,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Aggregate trend detection by scale
    for scale_name in scales:
        trends = [p["scales"][scale_name]["trend"] for p in per_patient]
        results[f"{scale_name}_improving"] = sum(1 for t in trends if t == "improving")
        results[f"{scale_name}_declining"] = sum(1 for t in trends if t == "declining")
        results[f"{scale_name}_stable"] = sum(1 for t in trends if t == "stable")
    
    return results


# ---------------------------------------------------------------------------
# EXP-1405: DIA-Horizon Therapy Metrics
# ---------------------------------------------------------------------------
@register(1405)
def exp_dia_horizon(patients, detail=False):
    """Measure therapy quality at DIA-scale (5-6h) windows.
    
    Most AID systems use DIA=5-6h. Analyze how therapy metrics look when
    measured at this natural timescale vs daily vs multi-day.
    """
    results = {"name": "EXP-1405: DIA-horizon therapy metrics"}
    per_patient = []
    
    dia_hours = 6  # Population DIA from prior experiments
    dia_steps = dia_hours * STEPS_PER_HOUR  # 72 steps
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        pk = pdata.get("pk")
        
        # Compute metrics at DIA-scale windows
        dia_tirs = []
        dia_ranges = []
        dia_cvs = []
        
        start = 0
        while start + dia_steps <= len(cgm):
            window = cgm[start:start + dia_steps]
            valid = window[~np.isnan(window)]
            
            if len(valid) > STEPS_PER_HOUR * 2:
                tir = np.mean((valid >= 70) & (valid <= 180)) * 100
                rng = np.max(valid) - np.min(valid)
                mean_bg = np.mean(valid)
                cv = np.std(valid) / mean_bg * 100 if mean_bg > 0 else 99
                
                dia_tirs.append(tir)
                dia_ranges.append(rng)
                dia_cvs.append(cv)
            
            start += dia_steps
        
        if not dia_tirs:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        # Compare DIA-scale vs daily-scale
        daily_tirs = []
        n_days = len(cgm) // STEPS_PER_DAY
        for d in range(min(n_days, 180)):
            day = cgm[d*STEPS_PER_DAY:(d+1)*STEPS_PER_DAY]
            valid = day[~np.isnan(day)]
            if len(valid) > STEPS_PER_HOUR * 6:
                daily_tirs.append(np.mean((valid >= 70) & (valid <= 180)) * 100)
        
        # DIA-scale variability (how much does TIR vary within a day?)
        dia_tir_std = np.std(dia_tirs)
        daily_tir_std = np.std(daily_tirs) if daily_tirs else 0
        
        # What fraction of DIA windows are "problem" windows?
        n_problem_dia = sum(1 for t in dia_tirs if t < 50)  # <50% TIR in 6h = problem
        problem_rate = n_problem_dia / len(dia_tirs)
        
        per_patient.append({
            "patient": pid,
            "n_dia_windows": len(dia_tirs),
            "mean_dia_tir": round(float(np.mean(dia_tirs)), 1),
            "dia_tir_std": round(float(dia_tir_std), 1),
            "mean_dia_range": round(float(np.mean(dia_ranges)), 1),
            "mean_dia_cv": round(float(np.mean(dia_cvs)), 1),
            "problem_dia_rate": round(float(problem_rate), 3),
            "n_problem_windows": n_problem_dia,
            "daily_tir_mean": round(float(np.mean(daily_tirs)), 1) if daily_tirs else 0,
            "daily_tir_std": round(float(daily_tir_std), 1),
            "granularity_ratio": round(float(dia_tir_std / daily_tir_std), 2) if daily_tir_std > 0 else 0,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["mean_problem_rate"] = round(float(np.mean([p["problem_dia_rate"] for p in per_patient if not p.get("skip")])), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1406: Seasonal/Monthly Pattern Detection
# ---------------------------------------------------------------------------
@register(1406)
def exp_seasonal_patterns(patients, detail=False):
    """Detect monthly patterns in therapy quality.
    
    Some patients show seasonal variation (e.g., less active in winter).
    Method: compute monthly TIR and test for significant month-to-month changes.
    """
    results = {"name": "EXP-1406: Seasonal/monthly pattern detection"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        # Compute 30-day block metrics
        block_days = 30
        block_steps = block_days * STEPS_PER_DAY
        
        blocks = []
        start = 0
        block_idx = 0
        while start + block_steps <= len(cgm):
            block = cgm[start:start + block_steps]
            valid = block[~np.isnan(block)]
            
            if len(valid) > STEPS_PER_DAY * 10:
                tir = np.mean((valid >= 70) & (valid <= 180)) * 100
                mean_bg = np.mean(valid)
                cv = np.std(valid) / mean_bg * 100 if mean_bg > 0 else 99
                
                blocks.append({
                    "block": block_idx,
                    "tir": round(float(tir), 1),
                    "mean_bg": round(float(mean_bg), 1),
                    "cv": round(float(cv), 1),
                })
            
            start += block_steps
            block_idx += 1
        
        if len(blocks) < 2:
            per_patient.append({"patient": pid, "n_blocks": 0, "seasonal": False})
            continue
        
        tirs = [b["tir"] for b in blocks]
        tir_range = max(tirs) - min(tirs)
        
        # Test for significant variation: range > 15% TIR
        seasonal = tir_range > 15
        
        # Compute trend
        if len(tirs) >= 2:
            try:
                slope = np.polyfit(range(len(tirs)), tirs, 1)[0]
            except (np.linalg.LinAlgError, ValueError):
                slope = 0.0
        else:
            slope = 0.0
        
        per_patient.append({
            "patient": pid,
            "n_blocks": len(blocks),
            "blocks": blocks if detail else [],
            "tir_range": round(float(tir_range), 1),
            "tir_trend_per_month": round(float(slope), 2),
            "seasonal": seasonal,
            "best_month_tir": round(float(max(tirs)), 1),
            "worst_month_tir": round(float(min(tirs)), 1),
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["n_seasonal"] = sum(1 for p in per_patient if p.get("seasonal", False))
    results["mean_tir_range"] = round(float(np.mean([p["tir_range"] for p in per_patient if p.get("n_blocks", 0) > 0])), 1)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1407: Multi-Segment Basal Optimization
# ---------------------------------------------------------------------------
@register(1407)
def exp_basal_optimization(patients, detail=False):
    """Optimize basal rates for 4 time segments independently.
    
    Compare single-rate vs 4-segment basal optimization based on drift analysis.
    """
    results = {"name": "EXP-1407: Multi-segment basal optimization"}
    per_patient = []
    
    segments = {
        "midnight_6am": (0, 6),
        "6am_noon": (6, 12),
        "noon_6pm": (12, 18),
        "6pm_midnight": (18, 24),
    }
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        bolus = pdata["bolus"]
        carbs = pdata["carbs"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        seg_analysis = {}
        for seg_name, (h_start, h_end) in segments.items():
            drifts = []
            fasting_periods = 0
            
            for d in range(min(n_days, 180)):
                start = d * STEPS_PER_DAY + h_start * STEPS_PER_HOUR
                end = d * STEPS_PER_DAY + h_end * STEPS_PER_HOUR
                
                if end > len(cgm):
                    continue
                
                seg_cgm = cgm[start:end]
                seg_carbs = carbs[start:end]
                seg_bolus = bolus[start:end]
                
                # Only use near-fasting periods
                if np.nansum(seg_carbs) > 5 or np.nansum(seg_bolus) > 0.5:
                    continue
                
                valid = seg_cgm[~np.isnan(seg_cgm)]
                if len(valid) < STEPS_PER_HOUR * 2:
                    continue
                
                fasting_periods += 1
                drift = (valid[-1] - valid[0]) / (len(valid) / STEPS_PER_HOUR)
                drifts.append(drift)
            
            if drifts:
                mean_drift = np.mean(drifts)
                # Basal adjustment direction
                if mean_drift > 3:
                    adjustment = "increase"
                    magnitude = min(abs(mean_drift) / 20, 0.3)
                elif mean_drift < -3:
                    adjustment = "decrease"
                    magnitude = min(abs(mean_drift) / 20, 0.3)
                else:
                    adjustment = "maintain"
                    magnitude = 0.0
                
                seg_analysis[seg_name] = {
                    "mean_drift": round(float(mean_drift), 2),
                    "std_drift": round(float(np.std(drifts)), 2),
                    "n_fasting": fasting_periods,
                    "adjustment": adjustment,
                    "magnitude": round(float(magnitude), 3),
                }
            else:
                seg_analysis[seg_name] = {
                    "mean_drift": 0.0, "std_drift": 0.0,
                    "n_fasting": 0, "adjustment": "insufficient_data",
                    "magnitude": 0.0,
                }
        
        # Does patient need multi-segment vs single-rate?
        adjustments = [s["adjustment"] for s in seg_analysis.values() if s["adjustment"] not in ("maintain", "insufficient_data")]
        unique_adjustments = set(adjustments)
        needs_multi = len(unique_adjustments) > 1 or (len(unique_adjustments) == 1 and any(
            s["magnitude"] > 0.1 for s in seg_analysis.values()
        ))
        
        per_patient.append({
            "patient": pid,
            "segments": seg_analysis,
            "needs_multi_segment": needs_multi,
            "n_segments_adjusting": len(adjustments),
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    results["n_needs_multi"] = sum(1 for p in per_patient if p["needs_multi_segment"])
    
    return results


# ---------------------------------------------------------------------------
# EXP-1408: Fidelity-Filtered Recommendations
# ---------------------------------------------------------------------------
@register(1408)
def exp_fidelity_filtered(patients, detail=False):
    """Generate recommendations only from high-fidelity data periods.
    
    From EXP-1403: fidelity scoring identifies when physics model works.
    Method: split data into high/low fidelity days, compare recommendations.
    """
    results = {"name": "EXP-1408: Fidelity-filtered recommendations"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        pk = pdata.get("pk")
        
        if pk is None:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        dpk = denorm_pk(pk)
        if dpk is None:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        n_days = len(cgm) // STEPS_PER_DAY
        
        # Compute per-day fidelity
        day_fidelities = []
        day_tirs = []
        day_drifts = []
        
        for d in range(min(n_days, 180)):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            
            day_cgm = cgm[start:end]
            valid = day_cgm[~np.isnan(day_cgm)]
            
            if len(valid) < STEPS_PER_HOUR * 12:
                day_fidelities.append(np.nan)
                day_tirs.append(np.nan)
                day_drifts.append(np.nan)
                continue
            
            # Day TIR
            tir = np.mean((valid >= 70) & (valid <= 180)) * 100
            
            # Day fidelity (conservation law R²)
            dg = np.diff(day_cgm[:end-start])
            supply = dpk["carb_rate"][start:end-1] + dpk["hepatic"][start:end-1]
            demand = dpk["activity"][start:end-1]
            pred = supply - demand
            
            mask = ~np.isnan(dg) & ~np.isnan(pred) & (np.abs(dg) < 50)
            if np.sum(mask) > 50:
                ss_r = np.sum((dg[mask] - pred[mask]) ** 2)
                ss_t = np.sum((dg[mask] - np.mean(dg[mask])) ** 2)
                r2 = 1 - ss_r / ss_t if ss_t > 0 else 0
            else:
                r2 = np.nan
            
            # Overnight drift
            overnight = day_cgm[:8*STEPS_PER_HOUR]
            ov = overnight[~np.isnan(overnight)]
            if len(ov) > STEPS_PER_HOUR:
                drift = abs((ov[-1] - ov[0]) / (len(ov) / STEPS_PER_HOUR))
            else:
                drift = np.nan
            
            day_fidelities.append(r2)
            day_tirs.append(tir)
            day_drifts.append(drift)
        
        fidelities = np.array(day_fidelities)
        tirs = np.array(day_tirs)
        drifts = np.array(day_drifts)
        
        # Split into high/low fidelity
        valid_fid = ~np.isnan(fidelities)
        if np.sum(valid_fid) < 10:
            per_patient.append({"patient": pid, "skip": True})
            continue
        
        median_fid = np.median(fidelities[valid_fid])
        high_mask = valid_fid & (fidelities >= median_fid)
        low_mask = valid_fid & (fidelities < median_fid)
        
        high_tir = np.nanmean(tirs[high_mask]) if np.any(high_mask) else 0
        low_tir = np.nanmean(tirs[low_mask]) if np.any(low_mask) else 0
        high_drift = np.nanmean(drifts[high_mask]) if np.any(high_mask) else 0
        low_drift = np.nanmean(drifts[low_mask]) if np.any(low_mask) else 0
        
        # Recommendations from high-fidelity days
        high_flag_basal = high_drift > 5.0
        low_flag_basal = low_drift > 5.0
        
        per_patient.append({
            "patient": pid,
            "n_days": min(n_days, 180),
            "n_high_fidelity": int(np.sum(high_mask)),
            "n_low_fidelity": int(np.sum(low_mask)),
            "median_fidelity_r2": round(float(median_fid), 4),
            "high_fid_tir": round(float(high_tir), 1),
            "low_fid_tir": round(float(low_tir), 1),
            "tir_gap": round(float(high_tir - low_tir), 1),
            "high_fid_drift": round(float(high_drift), 2),
            "low_fid_drift": round(float(low_drift), 2),
            "high_flags_basal": high_flag_basal,
            "low_flags_basal": low_flag_basal,
            "agreement": high_flag_basal == low_flag_basal,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    agreement_rate = np.mean([p["agreement"] for p in per_patient if "agreement" in p])
    results["fidelity_agreement_rate"] = round(float(agreement_rate), 3)
    tir_gaps = [p["tir_gap"] for p in per_patient if "tir_gap" in p]
    results["mean_tir_gap"] = round(float(np.mean(tir_gaps)), 1) if tir_gaps else 0
    
    return results


# ---------------------------------------------------------------------------
# EXP-1409: Weekly vs Daily Aggregation
# ---------------------------------------------------------------------------
@register(1409)
def exp_weekly_vs_daily(patients, detail=False):
    """Compare recommendation quality at weekly vs daily aggregation.
    
    Daily is noisy, weekly averages out day-to-day variation.
    Method: generate recs at daily and weekly scales, compare consistency.
    """
    results = {"name": "EXP-1409: Weekly vs daily aggregation comparison"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        # Daily metrics
        daily_flags = {"basal": 0, "dinner_cr": 0, "lunch_cr": 0}
        daily_count = 0
        
        for d in range(min(n_days, 180)):
            start = d * STEPS_PER_DAY
            day = cgm[start:start + STEPS_PER_DAY]
            valid = day[~np.isnan(day)]
            
            if len(valid) < STEPS_PER_HOUR * 12:
                continue
            
            daily_count += 1
            
            # Overnight drift
            overnight = day[:8*STEPS_PER_HOUR]
            ov = overnight[~np.isnan(overnight)]
            if len(ov) > STEPS_PER_HOUR and abs((ov[-1] - ov[0]) / (len(ov) / STEPS_PER_HOUR)) > 5:
                daily_flags["basal"] += 1
            
            # Dinner excursion
            dinner = day[17*STEPS_PER_HOUR:21*STEPS_PER_HOUR]
            dv = dinner[~np.isnan(dinner)]
            if len(dv) > 6 and (np.max(dv) - np.min(dv)) > 70:
                daily_flags["dinner_cr"] += 1
            
            # Lunch excursion
            lunch = day[11*STEPS_PER_HOUR:15*STEPS_PER_HOUR]
            lv = lunch[~np.isnan(lunch)]
            if len(lv) > 6 and (np.max(lv) - np.min(lv)) > 70:
                daily_flags["lunch_cr"] += 1
        
        daily_rates = {k: v / daily_count if daily_count > 0 else 0 for k, v in daily_flags.items()}
        
        # Weekly metrics
        weekly_flags = {"basal": 0, "dinner_cr": 0, "lunch_cr": 0}
        weekly_count = 0
        week_steps = 7 * STEPS_PER_DAY
        
        start = 0
        while start + week_steps <= len(cgm):
            week = cgm[start:start + week_steps]
            valid = week[~np.isnan(week)]
            
            if len(valid) < STEPS_PER_DAY * 3:
                start += week_steps
                continue
            
            weekly_count += 1
            
            # Weekly overnight drift (aggregate)
            week_drifts = []
            for d in range(7):
                overnight = week[d*STEPS_PER_DAY:d*STEPS_PER_DAY + 8*STEPS_PER_HOUR]
                ov = overnight[~np.isnan(overnight)]
                if len(ov) > STEPS_PER_HOUR:
                    drift = (ov[-1] - ov[0]) / (len(ov) / STEPS_PER_HOUR)
                    week_drifts.append(drift)
            
            if week_drifts and abs(np.mean(week_drifts)) > 5:
                weekly_flags["basal"] += 1
            
            # Weekly dinner excursion (aggregate)
            week_dinner_excs = []
            for d in range(7):
                dinner = week[d*STEPS_PER_DAY + 17*STEPS_PER_HOUR:d*STEPS_PER_DAY + 21*STEPS_PER_HOUR]
                dv = dinner[~np.isnan(dinner)]
                if len(dv) > 6:
                    week_dinner_excs.append(np.max(dv) - np.min(dv))
            
            if week_dinner_excs and np.mean(week_dinner_excs) > 70:
                weekly_flags["dinner_cr"] += 1
            
            # Weekly lunch excursion
            week_lunch_excs = []
            for d in range(7):
                lunch = week[d*STEPS_PER_DAY + 11*STEPS_PER_HOUR:d*STEPS_PER_DAY + 15*STEPS_PER_HOUR]
                lv = lunch[~np.isnan(lunch)]
                if len(lv) > 6:
                    week_lunch_excs.append(np.max(lv) - np.min(lv))
            
            if week_lunch_excs and np.mean(week_lunch_excs) > 70:
                weekly_flags["lunch_cr"] += 1
            
            start += week_steps
        
        weekly_rates = {k: v / weekly_count if weekly_count > 0 else 0 for k, v in weekly_flags.items()}
        
        # Compare daily vs weekly flag rates
        per_patient.append({
            "patient": pid,
            "n_daily": daily_count,
            "n_weekly": weekly_count,
            "daily_rates": {k: round(v, 3) for k, v in daily_rates.items()},
            "weekly_rates": {k: round(v, 3) for k, v in weekly_rates.items()},
            "basal_daily_vs_weekly": round(daily_rates.get("basal", 0) - weekly_rates.get("basal", 0), 3),
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    # Aggregate
    for param in ["basal", "dinner_cr", "lunch_cr"]:
        daily_mean = np.mean([p["daily_rates"][param] for p in per_patient])
        weekly_mean = np.mean([p["weekly_rates"][param] for p in per_patient])
        results[f"{param}_daily_flag_rate"] = round(float(daily_mean), 3)
        results[f"{param}_weekly_flag_rate"] = round(float(weekly_mean), 3)
    
    return results


# ---------------------------------------------------------------------------
# EXP-1410: Comprehensive Therapy Timeline
# ---------------------------------------------------------------------------
@register(1410)
def exp_therapy_timeline(patients, detail=False):
    """Generate complete therapy timeline showing evolution over months.
    
    Combines all signals (basal, CR, ISF, score, grade) into a temporal
    narrative showing how therapy quality evolves.
    """
    results = {"name": "EXP-1410: Comprehensive therapy timeline"}
    per_patient = []
    
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        n_days = len(cgm) // STEPS_PER_DAY
        
        # 14-day windows with 7-day stride
        window_days = 14
        stride_days = 7
        window_steps = window_days * STEPS_PER_DAY
        stride_steps = stride_days * STEPS_PER_DAY
        
        timeline = []
        start = 0
        epoch = 0
        
        while start + window_steps <= len(cgm):
            window = cgm[start:start + window_steps]
            valid = window[~np.isnan(window)]
            
            if len(valid) < STEPS_PER_DAY * 5:
                start += stride_steps
                epoch += 1
                continue
            
            # TIR
            tir = np.mean((valid >= 70) & (valid <= 180)) * 100
            mean_bg = np.mean(valid)
            cv = np.std(valid) / mean_bg * 100 if mean_bg > 0 else 99
            
            # Drift
            drifts = []
            for d in range(window_days):
                overnight = window[d*STEPS_PER_DAY:d*STEPS_PER_DAY + 8*STEPS_PER_HOUR]
                ov = overnight[~np.isnan(overnight)]
                if len(ov) > STEPS_PER_HOUR:
                    drifts.append(abs((ov[-1] - ov[0]) / (len(ov) / STEPS_PER_HOUR)))
            mean_drift = np.mean(drifts) if drifts else 0
            
            # Dinner excursion
            dinner_excs = []
            for d in range(window_days):
                dinner = window[d*STEPS_PER_DAY + 17*STEPS_PER_HOUR:d*STEPS_PER_DAY + 21*STEPS_PER_HOUR]
                dv = dinner[~np.isnan(dinner)]
                if len(dv) > 6:
                    dinner_excs.append(np.max(dv) - np.min(dv))
            mean_dinner = np.mean(dinner_excs) if dinner_excs else 0
            
            # Score and grade
            score = compute_therapy_score(tir, mean_drift, mean_dinner, cv)
            grade = get_grade(score)
            
            timeline.append({
                "epoch": epoch,
                "day_start": epoch * stride_days,
                "tir": round(float(tir), 1),
                "mean_bg": round(float(mean_bg), 1),
                "drift": round(float(mean_drift), 2),
                "dinner_exc": round(float(mean_dinner), 1),
                "score": round(float(score), 1),
                "grade": grade,
            })
            
            start += stride_steps
            epoch += 1
        
        if len(timeline) < 2:
            per_patient.append({"patient": pid, "n_epochs": 0})
            continue
        
        # Summarize trajectory
        scores = [t["score"] for t in timeline]
        grades = [t["grade"] for t in timeline]
        
        # Grade transitions
        transitions = []
        for i in range(1, len(grades)):
            if grades[i] != grades[i-1]:
                transitions.append({
                    "epoch": timeline[i]["epoch"],
                    "from": grades[i-1],
                    "to": grades[i],
                })
        
        # Overall trend
        try:
            slope = np.polyfit(range(len(scores)), scores, 1)[0]
        except (np.linalg.LinAlgError, ValueError):
            slope = 0.0
        
        if slope > 0.5:
            overall = "improving"
        elif slope < -0.5:
            overall = "declining"
        else:
            overall = "stable"
        
        per_patient.append({
            "patient": pid,
            "n_epochs": len(timeline),
            "overall_trend": overall,
            "score_slope": round(float(slope), 3),
            "n_grade_transitions": len(transitions),
            "transitions": transitions[:10] if detail else [],
            "grade_distribution": dict(defaultdict(int, {g: grades.count(g) for g in set(grades)})),
            "score_range": [round(min(scores), 1), round(max(scores), 1)],
            "timeline": timeline if detail else timeline[:3] + timeline[-3:] if len(timeline) > 6 else timeline,
        })
    
    results["per_patient"] = per_patient
    results["n_patients"] = len(per_patient)
    
    trends = [p["overall_trend"] for p in per_patient if p.get("n_epochs", 0) > 0]
    results["improving"] = sum(1 for t in trends if t == "improving")
    results["declining"] = sum(1 for t in trends if t == "declining")
    results["stable"] = sum(1 for t in trends if t == "stable")
    
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EXP-1401-1410")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--max-patients", type=int, default=11)
    parser.add_argument("--only", type=int, nargs="+")
    args = parser.parse_args()

    patients = load_patients(args.max_patients)
    if not patients:
        print("ERROR: No patient data found")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("PRECONDITION ASSESSMENT")
    print(f"{'='*60}")
    for pid, pdata in sorted(patients.items()):
        cgm = pdata["cgm"]
        valid_pct = np.mean(~np.isnan(cgm)) * 100
        n_days = len(cgm) // STEPS_PER_DAY
        print(f"  {pid}: CGM={valid_pct:.1f}% days={n_days}")

    exp_ids = args.only if args.only else sorted(EXPERIMENTS.keys())

    for exp_id in exp_ids:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered")
            continue

        print(f"\n{'='*60}")
        print(f"EXP-{exp_id}: {EXPERIMENTS[exp_id].__doc__.strip().split(chr(10))[0]}")
        print(f"{'='*60}")

        t0 = time.time()
        try:
            result = EXPERIMENTS[exp_id](patients, detail=args.detail)
            elapsed = time.time() - t0
            result["elapsed_sec"] = round(elapsed, 1)
            print(f"  Completed in {elapsed:.1f}s")

            for k, v in result.items():
                if k in ("name", "per_patient", "elapsed_sec"):
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

    print(f"\n{'='*60}")
    print("EXTENDED HORIZONS & FIDELITY SUMMARY")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
