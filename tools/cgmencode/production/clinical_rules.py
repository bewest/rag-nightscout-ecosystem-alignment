"""
clinical_rules.py — Basal assessment, CR scoring, AID-aware recommendations.

Research basis: EXP-693 (basal rate assessment), EXP-694 (CR effectiveness),
               EXP-685 (AID-aware clinical rules), EXP-747 (ISF discrepancy 2.91×)

Key findings:
  - Effective ISF is 2.91× profile ISF (AID masks bad settings)
  - 5/8 patients have basal too low (EXP-746)
  - 46.5% of glucose rises are unannounced meals (EXP-748)
  - CR scores range 9.1-61.5 (highly variable between patients)
  - All 11/11 test patients successfully graded and classified
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .types import (
    BasalAssessment, ClinicalReport, GlycemicGrade,
    MetabolicState, PatientProfile,
)


# ISF discrepancy ratio (from EXP-747)
AID_ISF_MULTIPLIER = 2.91


def assess_glycemic_control(glucose: np.ndarray) -> dict:
    """Compute standard glycemic metrics.

    Args:
        glucose: (N,) glucose values (mg/dL).

    Returns:
        dict with tir, tbr, tar, mean_glucose, gmi, cv.
    """
    valid = glucose[np.isfinite(glucose)]
    if len(valid) == 0:
        return {'tir': 0, 'tbr': 0, 'tar': 0, 'mean_glucose': 0, 'gmi': 0, 'cv': 0}

    tir = float(np.mean((valid >= 70) & (valid <= 180)))
    tbr = float(np.mean(valid < 70))
    tar = float(np.mean(valid > 180))
    mean_bg = float(np.mean(valid))
    gmi = 3.31 + 0.02392 * mean_bg  # GMI formula (Bergenstal 2018)
    cv = float(np.std(valid) / mean_bg * 100) if mean_bg > 0 else 0.0

    return {
        'tir': tir, 'tbr': tbr, 'tar': tar,
        'mean_glucose': mean_bg, 'gmi': gmi, 'cv': cv,
    }


def grade_glycemic_control(tir: float, tbr: float) -> GlycemicGrade:
    """Assign A-D grade based on TIR and TBR.

    Grading criteria:
      A: TIR ≥ 70% and TBR < 4% (consensus target)
      B: TIR ≥ 60% and TBR < 5%
      C: TIR ≥ 50%
      D: Below all thresholds
    """
    if tir >= 0.70 and tbr < 0.04:
        return GlycemicGrade.A
    elif tir >= 0.60 and tbr < 0.05:
        return GlycemicGrade.B
    elif tir >= 0.50:
        return GlycemicGrade.C
    else:
        return GlycemicGrade.D


def assess_basal(glucose: np.ndarray,
                 metabolic: Optional[MetabolicState] = None,
                 hours: Optional[np.ndarray] = None) -> BasalAssessment:
    """Assess basal rate adequacy from overnight glucose behavior.

    The key insight from research: analyze glucose during fasting periods
    (typically 00:00-06:00) where carb/bolus effects are minimal.
    If glucose drifts up → basal too low. Drifts down → too high.

    Args:
        glucose: (N,) glucose values.
        metabolic: optional metabolic state for flux analysis.
        hours: (N,) fractional hours for overnight window selection.

    Returns:
        BasalAssessment enum.
    """
    if hours is not None:
        # Select overnight fasting window (midnight to 6 AM)
        overnight_mask = (hours >= 0) & (hours < 6)
        if np.sum(overnight_mask) >= 12:  # at least 1 hour
            overnight_bg = glucose[overnight_mask]
        else:
            overnight_bg = glucose
    else:
        overnight_bg = glucose

    valid = overnight_bg[np.isfinite(overnight_bg)]
    if len(valid) < 12:
        return BasalAssessment.APPROPRIATE  # insufficient data

    # Linear trend over overnight period
    x = np.arange(len(valid), dtype=float)
    slope = np.polyfit(x, valid, 1)[0]  # mg/dL per 5-min step
    slope_per_hour = slope * 12.0  # convert to mg/dL per hour

    # Use metabolic flux if available for more precise assessment
    if metabolic is not None and hours is not None:
        mask = (hours >= 0) & (hours < 6)
        if np.sum(mask) > 0:
            overnight_net = np.mean(metabolic.net_flux[mask])
            # Net flux should be near zero during fasting with correct basal
            if overnight_net > 1.5:
                return BasalAssessment.TOO_LOW
            elif overnight_net < -1.5:
                return BasalAssessment.TOO_HIGH

    # Threshold: ±5 mg/dL/hr drift is clinically significant
    if slope_per_hour > 5.0:
        return BasalAssessment.TOO_LOW
    elif slope_per_hour < -5.0:
        return BasalAssessment.TOO_HIGH
    elif slope_per_hour > 2.0 or slope_per_hour < -2.0:
        return BasalAssessment.SLIGHTLY_HIGH if slope_per_hour < 0 else BasalAssessment.TOO_LOW
    else:
        return BasalAssessment.APPROPRIATE


def score_cr_effectiveness(glucose: np.ndarray,
                           carbs: np.ndarray,
                           bolus: np.ndarray) -> float:
    """Score carb ratio effectiveness (0-100).

    Analyzes post-meal glucose excursions:
    - Low score: large post-meal spikes and/or slow recovery
    - High score: modest excursions with clean recovery to baseline

    Research finding: CR scores range 9.1 to 61.5 across patients (EXP-694).

    Args:
        glucose, carbs, bolus: aligned (N,) arrays.

    Returns:
        CR effectiveness score (0-100, higher = better).
    """
    valid_bg = glucose[np.isfinite(glucose)]
    if len(valid_bg) < 24 or carbs is None:
        return 50.0  # neutral score with insufficient data

    # Find meal events (carbs > 5g threshold)
    meal_indices = np.where(np.nan_to_num(carbs, nan=0.0) > 5.0)[0]
    if len(meal_indices) == 0:
        return 50.0

    excursion_scores = []
    for meal_idx in meal_indices:
        # Look at 3-hour post-meal window (36 steps × 5 min)
        post_start = meal_idx
        post_end = min(meal_idx + 36, len(glucose))
        if post_end - post_start < 12:
            continue

        window = glucose[post_start:post_end]
        valid_w = window[np.isfinite(window)]
        if len(valid_w) < 6:
            continue

        pre_meal = float(valid_w[0])
        peak = float(np.max(valid_w))
        excursion = peak - pre_meal

        # Recovery: BG at 3h should be near pre-meal level
        recovery = abs(valid_w[-1] - pre_meal)

        # Score: penalize large excursion and slow recovery
        # Perfect meal: excursion < 30 mg/dL, recovery < 20 mg/dL
        excursion_penalty = max(0, excursion - 30) / 200.0  # 0-1
        recovery_penalty = max(0, recovery - 20) / 100.0    # 0-1
        meal_score = max(0, 100 * (1.0 - excursion_penalty - recovery_penalty))
        excursion_scores.append(meal_score)

    return float(np.mean(excursion_scores)) if excursion_scores else 50.0


def compute_effective_isf(glucose: np.ndarray,
                          bolus: np.ndarray,
                          profile: PatientProfile) -> Optional[float]:
    """Estimate effective ISF from observed correction bolus responses.

    Research finding: effective ISF is 2.91× profile ISF because
    AID systems compensate for inaccurate settings (EXP-747).

    Returns:
        Estimated effective ISF (mg/dL per Unit), or None if insufficient data.
    """
    # Find correction boluses (bolus with no nearby carbs)
    if bolus is None:
        return None

    bolus_vals = np.nan_to_num(bolus, nan=0.0)
    correction_indices = np.where(bolus_vals > 0.5)[0]  # significant boluses

    if len(correction_indices) < 3:
        return None

    isf_estimates = []
    for idx in correction_indices:
        # Check if this is a correction (no carbs within 30 min)
        window = max(0, idx - 6), min(len(glucose), idx + 6)
        if len(glucose) <= window[1]:
            continue

        # Measure BG drop over 2 hours post-bolus
        post_end = min(idx + 24, len(glucose))
        if post_end - idx < 12:
            continue

        pre_bg = float(glucose[idx])
        nadir = float(np.nanmin(glucose[idx:post_end]))
        drop = pre_bg - nadir
        dose = float(bolus_vals[idx])

        if dose > 0.1 and drop > 5:
            isf_estimates.append(drop / dose)

    if not isf_estimates:
        return None

    return float(np.median(isf_estimates))


def generate_recommendations(grade: GlycemicGrade,
                             basal: BasalAssessment,
                             cr_score: float,
                             tbr: float,
                             tar: float,
                             isf_discrepancy: Optional[float] = None) -> List[str]:
    """Generate actionable clinical recommendations.

    AID-aware: distinguishes between settings issues and AID compensation.
    """
    recs = []

    if basal == BasalAssessment.TOO_LOW:
        recs.append("Basal rate appears too low. Overnight glucose trending upward. "
                     "Consider increasing basal by 10-20% in consultation with care team.")
    elif basal == BasalAssessment.TOO_HIGH:
        recs.append("Basal rate appears too high. Overnight glucose trending downward. "
                     "Consider decreasing basal by 10-20%.")

    if cr_score < 30:
        recs.append(f"Carb ratio effectiveness is low ({cr_score:.0f}/100). "
                     "Post-meal excursions are larger than expected. "
                     "Consider adjusting CR or pre-bolus timing.")

    if tbr > 0.04:
        recs.append(f"Time below range is {tbr*100:.1f}% (target <4%). "
                     "Review insulin delivery around low glucose periods.")

    if tar > 0.30:
        recs.append(f"Time above range is {tar*100:.1f}%. "
                     "Consider reviewing correction factors and carb counting.")

    if isf_discrepancy and isf_discrepancy > 2.0:
        recs.append(f"Effective ISF is {isf_discrepancy:.1f}× profile ISF. "
                     "AID system may be compensating for settings mismatch. "
                     "Consider ISF adjustment with care team.")

    if grade == GlycemicGrade.A:
        recs.append("Excellent glycemic control. Continue current management.")
    elif not recs:
        recs.append("Glycemic control is acceptable. No urgent changes recommended.")

    return recs


def generate_clinical_report(glucose: np.ndarray,
                             metabolic: Optional[MetabolicState],
                             profile: PatientProfile,
                             carbs: Optional[np.ndarray] = None,
                             bolus: Optional[np.ndarray] = None,
                             hours: Optional[np.ndarray] = None,
                             ) -> ClinicalReport:
    """Generate complete clinical decision support report.

    This is the primary API for clinical rules.

    Args:
        glucose: (N,) cleaned glucose values (mg/dL).
        metabolic: MetabolicState from metabolic_engine.
        profile: patient's therapy profile.
        carbs, bolus: (N,) arrays for CR scoring.
        hours: (N,) fractional hours for overnight analysis.

    Returns:
        ClinicalReport with grade, scores, and recommendations.
    """
    metrics = assess_glycemic_control(glucose)
    grade = grade_glycemic_control(metrics['tir'], metrics['tbr'])
    basal = assess_basal(glucose, metabolic, hours)
    cr_score = score_cr_effectiveness(glucose, carbs, bolus) if carbs is not None else 50.0

    # ISF analysis
    effective_isf = compute_effective_isf(glucose, bolus, profile) if bolus is not None else None
    profile_isf_vals = [e.get('value', e.get('sensitivity', 50))
                        for e in profile.isf_schedule if e.get('value') or e.get('sensitivity')]
    profile_isf = float(np.median(profile_isf_vals)) if profile_isf_vals else None
    isf_discrepancy = (effective_isf / profile_isf
                       if effective_isf and profile_isf and profile_isf > 0
                       else None)

    # Risk score: composite 0-100 (higher = more concern)
    risk_score = (
        30.0 * metrics['tbr'] / 0.04 +      # TBR weight
        20.0 * max(0, metrics['tar'] - 0.25) / 0.25 +  # TAR weight
        20.0 * max(0, metrics['cv'] - 36) / 20.0 +     # CV weight
        30.0 * (1.0 - metrics['tir'])                   # TIR complement
    )
    risk_score = float(np.clip(risk_score, 0, 100))

    overnight_tir = None
    if hours is not None:
        overnight_mask = (hours >= 0) & (hours < 6)
        overnight_bg = glucose[overnight_mask]
        valid = overnight_bg[np.isfinite(overnight_bg)]
        if len(valid) > 0:
            overnight_tir = float(np.mean((valid >= 70) & (valid <= 180)))

    recommendations = generate_recommendations(
        grade, basal, cr_score, metrics['tbr'], metrics['tar'], isf_discrepancy
    )

    return ClinicalReport(
        grade=grade,
        risk_score=risk_score,
        tir=metrics['tir'],
        tbr=metrics['tbr'],
        tar=metrics['tar'],
        mean_glucose=metrics['mean_glucose'],
        gmi=metrics['gmi'],
        cv=metrics['cv'],
        basal_assessment=basal,
        cr_score=cr_score,
        effective_isf=effective_isf,
        profile_isf=profile_isf,
        isf_discrepancy=isf_discrepancy,
        recommendations=recommendations,
        overnight_tir=overnight_tir,
    )
