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
    AIDCompensation, BolusTimingSafety, CompensationType, CorrectionEnergy,
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


def compute_correction_energy(metabolic: MetabolicState,
                              hours: np.ndarray,
                              glucose: np.ndarray,
                              days_of_data: float) -> CorrectionEnergy:
    """Compute daily correction energy — metabolic effort metric (EXP-559).

    Correction energy = daily integral of |net_flux|.
    Interpretation: higher energy → AID working harder → worse settings alignment.
    Research: r=-0.353 correlation with TIR (8/11 patients p<0.05).

    Args:
        metabolic: MetabolicState with net_flux.
        hours: (N,) fractional hours.
        glucose: (N,) glucose for TIR correlation.
        days_of_data: data coverage.

    Returns:
        CorrectionEnergy with daily scores and interpretation.
    """
    flux = np.abs(np.nan_to_num(metabolic.net_flux, nan=0.0))
    N = len(flux)
    steps_per_day = 288

    n_full_days = int(N / steps_per_day)
    if n_full_days < 1:
        total_energy = float(np.sum(flux))
        return CorrectionEnergy(
            daily_scores=[total_energy],
            mean_daily_score=total_energy,
            interpretation="Insufficient data for daily breakdown.",
        )

    daily_scores = []
    daily_tir = []
    for d in range(n_full_days):
        start = d * steps_per_day
        end = start + steps_per_day
        day_flux = flux[start:end]
        daily_scores.append(float(np.sum(day_flux)))

        day_bg = glucose[start:end]
        valid = day_bg[np.isfinite(day_bg)]
        if len(valid) > 0:
            daily_tir.append(float(np.mean((valid >= 70) & (valid <= 180))))

    mean_score = float(np.mean(daily_scores))

    # 7-day smoothed
    smoothed = None
    if len(daily_scores) >= 7:
        kernel = np.ones(7) / 7.0
        smoothed = list(np.convolve(daily_scores, kernel, mode='valid').astype(float))

    # Correlation with TIR
    corr = None
    if len(daily_scores) >= 5 and len(daily_tir) >= 5:
        scores_arr = np.array(daily_scores[:len(daily_tir)])
        tir_arr = np.array(daily_tir)
        if np.std(scores_arr) > 0 and np.std(tir_arr) > 0:
            corr = float(np.corrcoef(scores_arr, tir_arr)[0, 1])

    # Interpretation
    if mean_score < 50:
        interp = "Low correction energy — AID making minimal adjustments. Settings appear well-aligned."
    elif mean_score < 150:
        interp = "Moderate correction energy — AID compensating for some settings mismatch."
    else:
        interp = "High correction energy — AID working hard to compensate. Consider settings review."

    if corr is not None:
        interp += f" Energy-TIR correlation: r={corr:.2f}."

    return CorrectionEnergy(
        daily_scores=daily_scores,
        mean_daily_score=mean_score,
        smoothed_7d=smoothed,
        correlation_with_tir=corr,
        interpretation=interp,
    )


def assess_correction_timing(bolus: Optional[np.ndarray],
                             glucose: np.ndarray,
                             timestamps: np.ndarray,
                             ) -> BolusTimingSafety:
    """Analyze correction bolus spacing for IOB stacking risk.

    Flags when correction boluses (high BG + bolus, no meal) are
    delivered <4h apart, which risks IOB stacking and subsequent hypos.

    Args:
        bolus: (N,) bolus Units per interval.
        glucose: (N,) glucose for context.
        timestamps: (N,) Unix timestamps (ms).

    Returns:
        BolusTimingSafety assessment.
    """
    if bolus is None:
        return BolusTimingSafety(
            total_corrections=0, stacking_events=0, stacking_fraction=0.0,
            interpretation="No bolus data available.")

    bolus_vals = np.nan_to_num(bolus, nan=0.0)
    bg_vals = np.nan_to_num(glucose, nan=120.0)

    # Identify correction boluses: bolus > 0.3U when BG > 150 mg/dL
    correction_mask = (bolus_vals > 0.3) & (bg_vals > 150)
    correction_indices = np.where(correction_mask)[0]

    total = len(correction_indices)
    if total < 2:
        return BolusTimingSafety(
            total_corrections=total, stacking_events=0, stacking_fraction=0.0,
            interpretation="Too few corrections to assess timing patterns.")

    # Compute inter-correction intervals (hours)
    intervals = []
    for i in range(1, len(correction_indices)):
        dt_ms = timestamps[correction_indices[i]] - timestamps[correction_indices[i - 1]]
        intervals.append(float(dt_ms) / 3_600_000.0)  # ms → hours

    intervals = np.array(intervals)
    stacking = int(np.sum(intervals < 4.0))
    stacking_frac = stacking / len(intervals) if len(intervals) > 0 else 0.0

    min_interval = float(np.min(intervals)) if len(intervals) > 0 else None
    mean_interval = float(np.mean(intervals)) if len(intervals) > 0 else None

    safety_flag = stacking_frac > 0.25  # >25% stacking is concerning

    if safety_flag:
        interp = (f"⚠ {stacking} of {len(intervals)} correction pairs ({stacking_frac*100:.0f}%) "
                  f"are <4h apart. Risk of IOB stacking and subsequent lows.")
    elif stacking > 0:
        interp = (f"{stacking} correction pair(s) <4h apart ({stacking_frac*100:.0f}%). "
                  f"Occasional stacking — monitor for post-correction lows.")
    else:
        interp = "No correction stacking detected. Good bolus spacing."

    return BolusTimingSafety(
        total_corrections=total,
        stacking_events=stacking,
        stacking_fraction=stacking_frac,
        min_interval_hours=min_interval,
        mean_interval_hours=mean_interval,
        safety_flag=safety_flag,
        interpretation=interp,
    )


def assess_aid_compensation(clinical: ClinicalReport,
                            metabolic: Optional[MetabolicState],
                            ) -> AIDCompensation:
    """Detect AID compensation vs genuine under-insulinization (EXP-747).

    Uses flux polarity + glycemic metrics to classify:
    - High TAR + negative net flux → AID compensating for bad settings
    - High TAR + positive net flux → genuinely under-insulinized
    - High TBR + negative flux → over-insulinized
    - Good TIR → well controlled

    Args:
        clinical: ClinicalReport with TIR/TAR/TBR and ISF discrepancy.
        metabolic: MetabolicState for flux analysis.

    Returns:
        AIDCompensation assessment.
    """
    tar = clinical.tar
    tbr = clinical.tbr
    tir = clinical.tir
    isf_ratio = clinical.isf_discrepancy

    mean_flux = 0.0
    polarity = "balanced"
    if metabolic is not None:
        mean_flux = metabolic.mean_net_flux
        if mean_flux < -0.5:
            polarity = "negative"
        elif mean_flux > 0.5:
            polarity = "positive"

    # Classification logic
    if tir >= 0.65:
        comp_type = CompensationType.WELL_CONTROLLED
        interp = "Good glycemic control. AID and settings appear well-matched."
    elif tbr > 0.06 and polarity == "negative":
        comp_type = CompensationType.OVER_INSULINIZED
        interp = ("Excessive time below range with net negative flux. "
                   "Total insulin delivery may be too high. Consider reducing basal or ISF.")
    elif tar > 0.30 and polarity == "negative":
        comp_type = CompensationType.AID_COMPENSATING
        interp = ("High time above range despite AID delivering extra insulin (negative flux). "
                   "AID is compensating for settings mismatch — underlying settings likely too conservative. "
                   "Consider adjusting CR/ISF closer to observed effective values.")
    elif tar > 0.30 and polarity in ("positive", "balanced"):
        comp_type = CompensationType.UNDER_INSULINIZED
        interp = ("High time above range with insufficient insulin delivery. "
                   "Patient may be genuinely under-insulinized. "
                   "Consider increasing basal rate or adjusting CR for more aggressive dosing.")
    else:
        comp_type = CompensationType.WELL_CONTROLLED
        interp = "Glycemic control is acceptable. No major AID compensation pattern detected."

    if isf_ratio and isf_ratio > 2.0:
        interp += f" ISF discrepancy: effective ISF is {isf_ratio:.1f}× profile setting."

    return AIDCompensation(
        compensation_type=comp_type,
        isf_ratio=isf_ratio,
        mean_net_flux=mean_flux,
        flux_polarity=polarity,
        tar=tar,
        tbr=tbr,
        interpretation=interp,
    )


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
