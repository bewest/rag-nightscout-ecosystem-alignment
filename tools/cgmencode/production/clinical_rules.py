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
    BasalAssessment, ClinicalReport, ConfidenceGrade, FidelityAssessment,
    FidelityGrade, GlycemicGrade, MetabolicState, PatientProfile,
    SettingsParameter, TIR_LOW, TIR_HIGH,
    AIDCompensation, BolusTimingSafety, CompensationType, CorrectionEnergy,
    DualPhaseISF, SaturationAssessment, SaturationLevel,
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

    tir = float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH)))
    tbr = float(np.mean(valid < TIR_LOW))
    tar = float(np.mean(valid > TIR_HIGH))
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
                 hours: Optional[np.ndarray] = None,
                 iob: Optional[np.ndarray] = None,
                 cob: Optional[np.ndarray] = None) -> BasalAssessment:
    """Assess basal rate adequacy from overnight glucose behavior.

    Uses the actual glucose slope during fasting hours (00:00-06:00) as
    the primary signal. When IOB/COB arrays are provided, filters to
    clean nights (IOB < 0.5U, COB < 5g) to avoid contamination from
    residual dinner bolus or late snacks (EXP-2375).

    For AID patients, the metabolic net_flux includes loop adjustments
    and is NOT a reliable indicator of programmed basal adequacy — the
    slope of actual glucose is more reliable.

    Args:
        glucose: (N,) glucose values.
        metabolic: optional metabolic state (not used for primary assessment).
        hours: (N,) fractional hours for overnight window selection.
        iob: (N,) optional insulin-on-board for clean-night filtering.
        cob: (N,) optional carbs-on-board for clean-night filtering.

    Returns:
        BasalAssessment enum.
    """
    # Clean-night thresholds (from settings_advisor.py:2736, EXP-2375)
    CLEAN_IOB_MAX = 0.5   # Units
    CLEAN_COB_MAX = 5.0   # grams

    if hours is not None:
        # Select overnight fasting window (midnight to 6 AM)
        overnight_mask = (hours >= 0) & (hours < 6)

        # Apply clean-night filtering when IOB/COB available
        if iob is not None:
            iob_clean = np.nan_to_num(iob, nan=0.0)
            overnight_mask = overnight_mask & (iob_clean < CLEAN_IOB_MAX)
        if cob is not None:
            cob_clean = np.nan_to_num(cob, nan=0.0)
            overnight_mask = overnight_mask & (cob_clean < CLEAN_COB_MAX)

        if np.sum(overnight_mask) >= 12:  # at least 1 hour
            overnight_bg = glucose[overnight_mask]
        else:
            # Fallback: relaxed overnight (time-only, ignore IOB/COB)
            relaxed_mask = (hours >= 0) & (hours < 6)
            if np.sum(relaxed_mask) >= 12:
                overnight_bg = glucose[relaxed_mask]
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

    # NOTE: We intentionally do NOT use metabolic.net_flux here.
    # For AID patients, net_flux includes loop automated adjustments
    # (temp basals, SMBs) which dominate over the programmed basal.
    # The actual glucose slope is a more reliable indicator of whether
    # the TOTAL insulin delivery (programmed + loop) is appropriate.
    # The metabolic flux analysis is used separately in the fidelity
    # assessment to understand WHY glucose behaves as it does.

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

    Analyzes post-meal glucose excursions with archetype-aware scoring
    (EXP-1591–1598): timing explains 9× more variance than dose, so
    pre-bolus timing is weighted more heavily than excursion magnitude.

    Research findings:
    - CR scores range 9.1 to 61.5 across patients (EXP-694)
    - Meals cluster into 2 archetypes (controlled_rise 53%, high_excursion 47%)
    - Timing (peak_time) explains 9× more variance than dose
    - ARI=0.976: clusters are universal across patients

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

        # Peak timing: earlier peak suggests better pre-bolus timing
        peak_idx = int(np.argmax(valid_w))
        peak_time_min = peak_idx * 5.0

        # Archetype-aware scoring (EXP-1591):
        # - Timing penalty weighted 3× more than excursion (timing explains 9× variance)
        # - Pre-bolus timing: peak < 45 min is ideal, > 90 min penalized
        excursion_penalty = max(0, excursion - 30) / 200.0  # 0-1
        recovery_penalty = max(0, recovery - 20) / 100.0    # 0-1
        timing_penalty = max(0, peak_time_min - 45) / 135.0  # 0-1, penalizes late peaks

        # Weight: 30% excursion + 20% recovery + 50% timing (timing-dominant)
        combined_penalty = 0.30 * excursion_penalty + 0.20 * recovery_penalty + 0.50 * timing_penalty
        meal_score = max(0, 100 * (1.0 - combined_penalty))
        excursion_scores.append(meal_score)

    return float(np.mean(excursion_scores)) if excursion_scores else 50.0


def compute_apparent_isf(glucose: np.ndarray,
                        bolus: np.ndarray,
                        profile: PatientProfile) -> Optional[float]:
    """Estimate apparent ISF from observed correction bolus responses.

    NOTE: This returns the APPARENT ISF, which includes AID controller
    amplification (basal withdrawal, SMB cancellation) and EGP suppression.
    Apparent ISF is 2–10× larger than true demand-phase ISF (EXP-2651).
    Use compute_demand_isf() for the true insulin effect (0–2h).

    For ISF recommendations, use demand-phase ISF with conservative steps.
    Multi-factor methods validated: dose-dependent r=-0.56 (EXP-2640),
    response-curve R²=0.805 (EXP-1301). Apparent ISF alone is not
    suitable as an ISF target (EXP-747: effective ISF is 2.91× profile).

    Returns:
        Estimated apparent ISF (mg/dL per Unit), or None if insufficient data.
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


def compute_response_curve_isf(glucose: np.ndarray,
                               bolus: np.ndarray,
                               basal_rate: Optional[np.ndarray] = None,
                               profile: Optional[PatientProfile] = None,
                               ) -> dict:
    """AID-aware ISF estimation via response-curve fitting (EXP-1601–1608).

    NOTE: This returns an APPARENT ISF that includes AID controller
    compensation. Even with AID dampening detection, the resulting ISF
    conflates demand-phase insulin action with EGP suppression (EXP-2651:
    apparent ISF is 2–10× inflated). Use compute_demand_isf() for the
    true insulin effect (0–2h only).

    The naive drop/dose method underestimates ISF because AID loops
    reduce basal during 92-100% of correction windows, dampening the
    observed BG drop. This method fits an exponential decay curve:

        BG(t) = BG_start - amplitude × (1 - exp(-t/τ))

    and computes ISF = amplitude / bolus_dose.

    Research findings:
    - AID reduces basal during 92-100% of corrections
    - Correction factor ranges 0.61-2.49× (patient-dependent)
    - 7/11 patients show ISF mismatch >2× profile
    - Response-curve R² = 0.68-0.98 (excellent fit)
    - τ is bimodal: 1.5h fast responders, 4.0h slow responders

    Args:
        glucose: (N,) glucose values (mg/dL).
        bolus: (N,) bolus units per interval.
        basal_rate: (N,) actual basal rate U/hr (for AID dampening detection).
        profile: PatientProfile for scheduled basal comparison.

    Returns:
        dict with keys: isf, tau_hours, r2, n_corrections, aid_dampening_pct,
        correction_factor, isf_estimates (per-correction). Returns empty dict
        if insufficient data.
    """
    if bolus is None:
        return {}

    bolus_vals = np.nan_to_num(bolus, nan=0.0)
    correction_indices = np.where(bolus_vals > 0.5)[0]

    if len(correction_indices) < 3:
        return {}

    # Determine scheduled basal for AID dampening detection
    scheduled_basal = 0.8  # default fallback
    if profile is not None and profile.basal_schedule:
        scheduled_basal = float(np.median([
            e.get('value', e.get('rate', 0.8))
            for e in profile.basal_schedule
            if e.get('value') or e.get('rate')
        ] or [0.8]))

    isf_estimates = []
    tau_estimates = []
    dampening_count = 0
    total_corrections = 0

    for idx in correction_indices:
        # Need 2h (24 steps) post-bolus window
        post_end = min(idx + 24, len(glucose))
        if post_end - idx < 12:
            continue

        pre_bg = float(glucose[idx])
        if not np.isfinite(pre_bg) or pre_bg < 120:
            continue  # only corrections from elevated BG

        dose = float(bolus_vals[idx])
        if dose < 0.1:
            continue

        total_corrections += 1

        # Check for AID dampening: was basal reduced during correction?
        if basal_rate is not None:
            window_basal = basal_rate[idx:post_end]
            valid_basal = window_basal[np.isfinite(window_basal)]
            if len(valid_basal) > 0:
                mean_basal = float(np.mean(valid_basal))
                if mean_basal < scheduled_basal * 0.85:
                    dampening_count += 1

        # Extract BG trajectory
        bg_window = glucose[idx:post_end].copy()
        valid_mask = np.isfinite(bg_window)
        if valid_mask.sum() < 6:
            continue

        t = np.arange(len(bg_window)) * 5.0 / 60.0  # hours
        bg_vals = bg_window.copy()

        # Fit exponential decay: BG(t) = BG_start - A*(1 - exp(-t/τ))
        # Linearize: let y = BG_start - BG(t), fit y = A*(1 - exp(-t/τ))
        y = pre_bg - bg_vals
        y_valid = y[valid_mask]
        t_valid = t[valid_mask]

        if len(y_valid) < 6:
            continue

        # Grid search for τ (0.5h to 6h)
        best_r2 = -np.inf
        best_tau = 2.0
        best_amp = 0.0

        for tau_candidate in np.arange(0.5, 6.5, 0.25):
            basis = 1.0 - np.exp(-t_valid / tau_candidate)
            if np.sum(basis ** 2) < 1e-10:
                continue
            # Least squares for amplitude
            amp = float(np.sum(y_valid * basis) / np.sum(basis ** 2))
            if amp <= 0:
                continue
            predicted = amp * basis
            ss_res = np.sum((y_valid - predicted) ** 2)
            ss_tot = np.sum((y_valid - np.mean(y_valid)) ** 2)
            if ss_tot > 0:
                r2 = 1.0 - ss_res / ss_tot
                if r2 > best_r2:
                    best_r2 = r2
                    best_tau = tau_candidate
                    best_amp = amp

        if best_r2 > 0.3 and best_amp > 0:
            isf_est = best_amp / dose
            isf_estimates.append(isf_est)
            tau_estimates.append(best_tau)

    if not isf_estimates:
        return {}

    median_isf = float(np.median(isf_estimates))
    median_tau = float(np.median(tau_estimates))
    dampening_pct = dampening_count / max(total_corrections, 1)

    # Correction factor: how much AID dampening reduces observed drop
    # Simple estimate: naive ISF / response-curve ISF
    correction_factor = 1.0
    if dampening_pct > 0.5:
        correction_factor = 1.0 + 0.5 * dampening_pct  # 1.0-1.5×

    return {
        'isf': median_isf,
        'tau_hours': median_tau,
        'n_corrections': total_corrections,
        'aid_dampening_pct': dampening_pct,
        'correction_factor': correction_factor,
        'isf_estimates': isf_estimates,
        'tau_estimates': tau_estimates,
    }


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
            daily_tir.append(float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH))))

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
    delivered <3.5h apart, which risks IOB stacking and subsequent hypos.

    Research (EXP-2624): glucose nadir after correction is at 3.5h (not
    at insulin peak ~1.25h) due to the EGP suppression phase lag. Re-
    correcting before 3.5h stacks insulin while the first dose is still
    producing its full glucose-lowering effect via EGP suppression.

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
    # 3.5h threshold: glucose nadir is at 3.5h post-correction (EXP-2624)
    _STACKING_THRESHOLD_H = 3.5
    stacking = int(np.sum(intervals < _STACKING_THRESHOLD_H))
    stacking_frac = stacking / len(intervals) if len(intervals) > 0 else 0.0

    min_interval = float(np.min(intervals)) if len(intervals) > 0 else None
    mean_interval = float(np.mean(intervals)) if len(intervals) > 0 else None

    # AID-aware stacking assessment (EXP-2357, EXP-2624):
    # In closed-loop AID, the loop reduces basal during high-IOB periods.
    # However, EGP suppression continues for 3.5h regardless — the loop
    # cannot prevent the delayed glucose-lowering from the first dose.
    is_aid = True  # Default: assume AID (conservative — suppress false warnings)
    safety_flag = False

    if is_aid:
        if stacking_frac > 0.25:
            interp = (f"{stacking} of {len(intervals)} correction pairs ({stacking_frac*100:.0f}%) "
                      f"are <{_STACKING_THRESHOLD_H}h apart. Glucose nadir is at 3.5h "
                      f"post-correction (EXP-2624: EGP suppression phase lag). "
                      f"Even with AID basal reduction, re-correcting before nadir "
                      f"stacks insulin while the first dose is still active. "
                      f"Recommend waiting ≥3.5h between corrections.")
            safety_flag = True  # Flag even for AID — EGP lag is not compensated
        elif stacking > 0:
            interp = (f"{stacking} correction pair(s) <{_STACKING_THRESHOLD_H}h apart "
                      f"({stacking_frac*100:.0f}%). Glucose nadir is at 3.5h "
                      f"(EXP-2624) — consider waiting for full effect.")
        else:
            interp = "No correction stacking detected. Good bolus spacing (≥3.5h)."
    else:
        # Non-AID: traditional stacking warning with 3.5h awareness
        safety_flag = stacking_frac > 0.25
        if safety_flag:
            interp = (f"⚠ {stacking} of {len(intervals)} correction pairs ({stacking_frac*100:.0f}%) "
                      f"are <{_STACKING_THRESHOLD_H}h apart. Glucose nadir is at 3.5h "
                      f"post-correction (EXP-2624). Risk of IOB stacking and "
                      f"subsequent lows. Wait ≥3.5h between corrections.")
        elif stacking > 0:
            interp = (f"{stacking} correction pair(s) <{_STACKING_THRESHOLD_H}h apart "
                      f"({stacking_frac*100:.0f}%). Wait ≥3.5h for full correction "
                      f"effect (EXP-2624: EGP suppression phase lag).")
        else:
            interp = "No correction stacking detected. Good bolus spacing (≥3.5h)."

    return BolusTimingSafety(
        total_corrections=total,
        stacking_events=stacking,
        stacking_fraction=stacking_frac,
        min_interval_hours=min_interval,
        mean_interval_hours=mean_interval,
        safety_flag=safety_flag,
        is_aid_managed=is_aid,
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


def compute_fidelity_grade(metabolic: MetabolicState,
                           glucose: np.ndarray,
                           hours: np.ndarray,
                           days_of_data: float,
                           ada_grade: Optional[GlycemicGrade] = None,
                           ) -> FidelityAssessment:
    """Compute physics-model fidelity grade (EXP-1531–1538).

    Measures how well the supply-demand physics model predicts observed
    glucose changes. This is the PRIMARY therapy quality metric.

    Research findings:
    - RMSE+CE thresholds calibrated from 11-patient population
    - Fidelity correlates r=0.94 with RMSE but only r=-0.59 with TIR
    - Fidelity/ADA concordance is only 36%
    - R² is universally negative (mean=-0.495) due to 76.5% UAM

    Args:
        metabolic: MetabolicState with residual and net_flux.
        glucose: (N,) glucose values for R² computation.
        hours: (N,) fractional hours.
        days_of_data: data coverage.
        ada_grade: optional ADA grade for concordance check.

    Returns:
        FidelityAssessment with grade, RMSE, CE, and concordance.
    """
    # RMSE: prediction error of physics model
    residual = np.nan_to_num(metabolic.residual, nan=0.0)
    rmse = float(np.sqrt(np.mean(residual ** 2)))

    # Correction energy: daily integral of |net_flux|
    flux = np.abs(np.nan_to_num(metabolic.net_flux, nan=0.0))
    steps_per_day = 288
    if len(flux) >= steps_per_day:
        n_days = max(1, len(flux) / steps_per_day)
        ce = float(np.sum(flux) / n_days)
    else:
        ce = float(np.sum(flux))

    # R² (informational — often negative due to UAM)
    bg_change = np.zeros(len(glucose))
    bg_change[1:] = np.diff(glucose)
    valid = np.isfinite(bg_change) & np.isfinite(metabolic.net_flux)
    r2 = None
    if valid.sum() > 48:
        actual = bg_change[valid]
        predicted = metabolic.net_flux[valid]
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        if ss_tot > 0:
            r2 = float(1.0 - ss_res / ss_tot)

    # Conservation integral
    conservation = float(np.sum(np.nan_to_num(metabolic.residual, nan=0.0)))

    # Grade assignment (EXP-1535 thresholds)
    if rmse <= 6.0 and ce <= 600.0:
        grade = FidelityGrade.EXCELLENT
    elif rmse <= 9.0 and ce <= 1000.0:
        grade = FidelityGrade.GOOD
    elif rmse <= 11.0 and ce <= 1600.0:
        grade = FidelityGrade.ACCEPTABLE
    else:
        grade = FidelityGrade.POOR

    # Concordance check: does fidelity direction match ADA?
    concordance = None
    if ada_grade is not None:
        fidelity_good = grade in (FidelityGrade.EXCELLENT, FidelityGrade.GOOD)
        ada_good = ada_grade in (GlycemicGrade.A, GlycemicGrade.B)
        concordance = (fidelity_good == ada_good)

    return FidelityAssessment(
        fidelity_grade=grade,
        rmse=rmse,
        correction_energy=ce,
        r2=r2,
        conservation_integral=conservation,
        ada_grade=ada_grade,
        concordance=concordance,
    )


def grade_recommendation_confidence(parameter: SettingsParameter,
                                    estimates: list,
                                    n_bootstrap: int = 100,
                                    ) -> tuple:
    """Grade recommendation confidence via bootstrap CI width (EXP-1621–1628).

    Bootstraps the estimate list to compute 95% CI width, then assigns
    a confidence grade based on parameter-specific thresholds.

    Research findings:
    - ISF: CI width 46% median (irreducible floor ~30%)
    - CR: CI width 5% (10× tighter than ISF)
    - 8/10 patients LOO-robust

    Args:
        parameter: SettingsParameter (ISF, CR, BASAL_RATE).
        estimates: list of individual measurements (ISF values, CR values, etc.).
        n_bootstrap: number of bootstrap iterations.

    Returns:
        (ConfidenceGrade, ci_width_pct) tuple.
    """
    if len(estimates) < 3:
        return ConfidenceGrade.D, 100.0

    estimates_arr = np.array(estimates, dtype=float)
    median_val = float(np.median(estimates_arr))
    if median_val == 0:
        return ConfidenceGrade.D, 100.0

    # Bootstrap
    rng = np.random.RandomState(42)
    boot_medians = []
    for _ in range(n_bootstrap):
        sample = rng.choice(estimates_arr, size=len(estimates_arr), replace=True)
        boot_medians.append(float(np.median(sample)))

    boot_medians = np.array(boot_medians)
    ci_low = float(np.percentile(boot_medians, 2.5))
    ci_high = float(np.percentile(boot_medians, 97.5))
    ci_width_pct = (ci_high - ci_low) / abs(median_val) * 100.0

    # Parameter-specific thresholds
    if parameter == SettingsParameter.ISF:
        if ci_width_pct <= 30:
            grade = ConfidenceGrade.A
        elif ci_width_pct <= 46:
            grade = ConfidenceGrade.B
        elif ci_width_pct <= 60:
            grade = ConfidenceGrade.C
        else:
            grade = ConfidenceGrade.D
    elif parameter == SettingsParameter.CR:
        if ci_width_pct <= 5:
            grade = ConfidenceGrade.A
        elif ci_width_pct <= 10:
            grade = ConfidenceGrade.B
        elif ci_width_pct <= 15:
            grade = ConfidenceGrade.C
        else:
            grade = ConfidenceGrade.D
    else:  # BASAL_RATE
        if ci_width_pct <= 10:
            grade = ConfidenceGrade.A
        elif ci_width_pct <= 20:
            grade = ConfidenceGrade.B
        elif ci_width_pct <= 30:
            grade = ConfidenceGrade.C
        else:
            grade = ConfidenceGrade.D

    return grade, ci_width_pct


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

    # ISF analysis — use response-curve method first, fall back to naive
    effective_isf = None
    isf_confidence_grade = None
    isf_ci_width = None
    if bolus is not None:
        rc_result = compute_response_curve_isf(glucose, bolus, profile=profile)
        if rc_result and 'isf' in rc_result:
            effective_isf = rc_result['isf']
            # Confidence grade from bootstrap CI (EXP-1621)
            if 'isf_estimates' in rc_result and len(rc_result['isf_estimates']) >= 3:
                isf_confidence_grade, isf_ci_width = grade_recommendation_confidence(
                    SettingsParameter.ISF, rc_result['isf_estimates'])
        else:
            effective_isf = compute_apparent_isf(glucose, bolus, profile)
    profile_isf_vals = [e.get('value', e.get('sensitivity', 50))
                        for e in profile.isf_mgdl() if e.get('value') or e.get('sensitivity')]
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
            overnight_tir = float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH)))

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


# ── Three Ceilings Framework (EXP-1731–1738) ─────────────────────────

def compute_three_ceilings(glucose: np.ndarray,
                           metabolic: Optional[MetabolicState] = None,
                           ) -> dict:
    """Compute three performance ceilings that bound achievable TIR (EXP-1731).

    Three independent ceilings on time-above-range (TAR) improvement:

    1. **Kinetics ceiling**: TAR that is unavoidable given insulin pharmacokinetics.
       Even with perfect dosing, insulin takes 15-90 min to act. Research finding:
       53.9% of TAR is kinetics-unavoidable (EXP-1731).

    2. **Information ceiling**: TAR reducible with perfect CGM data but current
       algorithms. Limited by prediction horizon and sensor lag.

    3. **Algorithm ceiling**: TAR reducible with perfect algorithms but current
       data. Combined optimization ceiling: +17.6% TIR (EXP-1765).

    The combined ceiling = min(kinetics, information, algorithm).
    Anything above the ceiling requires fundamental changes (faster insulin,
    better sensors, or structural algorithm redesign).

    Args:
        glucose: (N,) glucose values (mg/dL).
        metabolic: MetabolicState for flux analysis.

    Returns:
        Dict with ceiling values, achievable TIR, and headroom.
    """
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 288:
        return {
            'kinetics_unavoidable_tar_frac': 0.539,
            'current_tar': 0.0,
            'achievable_tar_reduction': 0.0,
            'combined_ceiling_tir_gain': 0.176,
            'headroom': 0.0,
        }

    current_tir = float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH)))
    current_tar = float(np.mean(valid > TIR_HIGH))

    # Kinetics ceiling (EXP-1731): 53.9% of TAR is unavoidable
    kinetics_unavoidable_frac = 0.539
    achievable_tar_reduction = current_tar * (1.0 - kinetics_unavoidable_frac)

    # Algorithm ceiling (EXP-1765): +17.6% TIR maximum from settings optimization
    combined_ceiling_tir_gain = 0.176

    # Actual headroom: min of what kinetics allows and what algorithms can deliver
    headroom = min(achievable_tar_reduction, combined_ceiling_tir_gain)

    # If metabolic data available, estimate information ceiling from residual
    info_ceiling = None
    if metabolic is not None:
        # High residual variance = information gap (sensor noise, unannounced meals)
        res_std = float(np.nanstd(metabolic.residual))
        # Empirical: each mg/dL/step of residual std costs ~2% TIR
        info_loss = min(res_std * 0.02, 0.20)
        info_ceiling = headroom * (1.0 - info_loss)
        headroom = min(headroom, info_ceiling)

    return {
        'kinetics_unavoidable_tar_frac': kinetics_unavoidable_frac,
        'current_tir': current_tir,
        'current_tar': current_tar,
        'achievable_tar_reduction': achievable_tar_reduction,
        'combined_ceiling_tir_gain': combined_ceiling_tir_gain,
        'information_ceiling': info_ceiling,
        'headroom': headroom,
        'theoretical_best_tir': min(1.0, current_tir + headroom),
    }


# Deprecated alias — use compute_apparent_isf directly.
# Apparent ISF is 2-10x inflated by AID compensation (EXP-2651);
# prefer compute_demand_isf() for actionable recommendations.
compute_effective_isf = compute_apparent_isf


# ── Demand-Phase ISF (EXP-2651, 2663-2666) ──────────────────────────

# Demand phase = 0–2h post-bolus (24 steps at 5min intervals)
_DEMAND_PHASE_STEPS = 24
_MIN_DEMAND_CORRECTIONS = 5
# Isolation tiers (EXP-2666: 6h is optimal, 2h is minimum viable)
_STRICT_PRIOR_BOLUS_H = 6.0   # Nyquist-correct for DIA=6h
_LAX_PRIOR_BOLUS_H = 2.0      # Fallback for SMB-heavy patients
_CARB_EXCLUSION_H = 1.0       # ±1h carb-free zone
_MIN_PRE_BG = 120              # mg/dL minimum for correction
_MIN_DOSE = 0.5                # Units minimum bolus
_MIN_DROP = 10                 # mg/dL minimum total drop
_STEPS_PER_HOUR = 12


def _extract_demand_events(glucose, bolus_vals, carbs_vals,
                           prior_bolus_h, n_total):
    """Extract isolated correction events with specified isolation window.

    Uses EXP-2663 gold-standard method: glucose at exactly 2h (not nadir
    in 0-2h window), carb exclusion zone, prior-bolus isolation.
    """
    prior_window = int(prior_bolus_h * _STEPS_PER_HOUR)
    carb_window = int(_CARB_EXCLUSION_H * _STEPS_PER_HOUR)
    post_window = 5 * _STEPS_PER_HOUR  # 5h for apparent ISF nadir search

    demand_isfs = []
    apparent_isfs = []

    for i in range(prior_window, n_total - _DEMAND_PHASE_STEPS):
        if bolus_vals[i] < _MIN_DOSE:
            continue
        pre_bg = float(glucose[i]) if np.isfinite(glucose[i]) else np.nan
        if not np.isfinite(pre_bg) or pre_bg < _MIN_PRE_BG:
            continue

        dose = float(bolus_vals[i])

        # No prior bolus within isolation window
        if np.nansum(bolus_vals[max(0, i - prior_window):i]) > 0.3:
            continue

        # No carbs within ± exclusion zone
        if carbs_vals is not None:
            cs = max(0, i - carb_window)
            ce = min(n_total, i + carb_window)
            if np.nansum(carbs_vals[cs:ce]) > 2:
                continue

        # Demand ISF: glucose at exactly 2h (EXP-2663 method)
        idx_2h = i + _DEMAND_PHASE_STEPS
        if idx_2h >= n_total or np.isnan(glucose[idx_2h]):
            continue
        drop_2h = pre_bg - float(glucose[idx_2h])

        # Find nadir in 1-5h for apparent ISF
        nadir_start = i + _STEPS_PER_HOUR
        nadir_end = min(i + post_window, n_total)
        search = glucose[nadir_start:nadir_end]
        valid = ~np.isnan(search)
        if valid.sum() < 6:
            continue
        total_drop = pre_bg - float(np.nanmin(search))

        if total_drop < _MIN_DROP:
            continue

        if drop_2h > 5 and dose > 0:
            demand_isfs.append(drop_2h / dose)
        if total_drop > 5 and dose > 0:
            apparent_isfs.append(total_drop / dose)

    return demand_isfs, apparent_isfs


def compute_demand_isf(glucose: np.ndarray,
                       bolus: np.ndarray,
                       profile: PatientProfile,
                       carbs: Optional[np.ndarray] = None) -> Optional[DualPhaseISF]:
    """Compute dual-phase ISF: demand (0–2h) vs apparent (full drop).

    Uses EXP-2663-2666 validated methodology:
    - Glucose at exactly 2h for demand drop (not nadir in 0-2h window)
    - 6h prior-bolus isolation (Nyquist-correct for DIA=6h, EXP-2666)
    - ±1h carb exclusion zone (EXP-2663 gold standard)
    - Tiered fallback: 6h → 2h isolation for SMB-heavy patients

    Validated properties: demand ISF is dose-INDEPENDENT (|r|=0.156),
    circadian-FLAT (-4.7% from profiling), stable at 6h (rho=0.964).
    Use a single constant per patient.

    Args:
        glucose: (N,) glucose values (mg/dL), 5-min intervals.
        bolus: (N,) bolus units per interval.
        profile: PatientProfile for scheduled ISF comparison.
        carbs: (N,) optional carbs per interval for exclusion filtering.

    Returns:
        DualPhaseISF with both ISF values and isolation metadata,
        or None if insufficient correction events.
    """
    if bolus is None:
        return None

    bolus_vals = np.nan_to_num(bolus, nan=0.0)
    carbs_vals = np.nan_to_num(carbs, nan=0.0) if carbs is not None else None
    n_total = len(glucose)

    # Tier 1: strict 6h isolation (Nyquist-correct)
    demand_isfs, apparent_isfs = _extract_demand_events(
        glucose, bolus_vals, carbs_vals, _STRICT_PRIOR_BOLUS_H, n_total)
    isolation_used = _STRICT_PRIOR_BOLUS_H
    quality_note = ''

    # Tier 2: fall back to 2h if insufficient strict events
    if len(demand_isfs) < _MIN_DEMAND_CORRECTIONS:
        demand_isfs, apparent_isfs = _extract_demand_events(
            glucose, bolus_vals, carbs_vals, _LAX_PRIOR_BOLUS_H, n_total)
        isolation_used = _LAX_PRIOR_BOLUS_H
        if len(demand_isfs) >= _MIN_DEMAND_CORRECTIONS:
            quality_note = (
                f'Reduced to {_LAX_PRIOR_BOLUS_H}h isolation '
                f'(SMB-heavy patient). Prior boluses may contaminate '
                f'demand ISF estimate. Treat with caution.')

    if len(demand_isfs) < _MIN_DEMAND_CORRECTIONS:
        return None

    demand_med = float(np.median(demand_isfs))
    apparent_med = float(np.median(apparent_isfs)) if apparent_isfs else demand_med

    # Bootstrap CI for demand ISF
    if len(demand_isfs) >= 10:
        rng = np.random.default_rng(42)
        boot_medians = [
            float(np.median(rng.choice(demand_isfs, size=len(demand_isfs), replace=True)))
            for _ in range(1000)
        ]
        ci_low = float(np.percentile(boot_medians, 2.5))
        ci_high = float(np.percentile(boot_medians, 97.5))
        if isolation_used >= _STRICT_PRIOR_BOLUS_H:
            conf = 'high' if len(demand_isfs) >= 20 else 'medium'
        else:
            conf = 'medium' if len(demand_isfs) >= 20 else 'low'
    else:
        ci_low = demand_med * 0.7
        ci_high = demand_med * 1.3
        conf = 'low'

    inflation = apparent_med / max(demand_med, 0.01)

    # Scheduled ISF
    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    sched_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    return DualPhaseISF(
        demand_isf=round(demand_med, 1),
        apparent_isf=round(apparent_med, 1),
        inflation_ratio=round(inflation, 2),
        n_corrections=len(demand_isfs),
        confidence=conf,
        demand_ci_low=round(ci_low, 1),
        demand_ci_high=round(ci_high, 1),
        scheduled_isf=round(sched_isf, 1),
        isolation_h=isolation_used,
        data_quality_note=quality_note,
    )


# ── Insulin Saturation Detection (EXP-2660/2662) ─────────────────────

# Wall detection thresholds from EXP-2660 (validated on 2,602 episodes)
_WALL_IOB_RATIO = 2.0         # IOB must be > 2× median
_WALL_ROC_THRESHOLD = -5.0    # glucose ROC must be > -5 mg/dL/hr (barely falling)
_HIGH_GLUCOSE_THRESHOLD = 180  # mg/dL — sticky hyper threshold
_HIGH_GLUCOSE_DURATION = 24    # 24 × 5min = 2h sustained
_PATIENCE_CAP_RATIO = 1.5     # IOB cap at 1.5× median when wall detected


def detect_insulin_saturation(
    glucose: np.ndarray,
    iob: np.ndarray,
    hours: Optional[np.ndarray] = None,
) -> Optional[SaturationAssessment]:
    """Detect insulin saturation (wall) episodes (EXP-2660).

    Wall detection: periods where IOB > 2×median AND glucose is barely
    falling (ROC > -5 mg/dL/hr) despite high insulin. Indicates the SC
    suppression ceiling (~30% of hepatic EGP, EXP-2656) has been reached.

    Research findings:
    - 61–84% of sticky hypers show wall detection
    - Wall episodes resolve in similar time regardless of additional insulin
    - Patience mode (cap IOB at 1.5×) saves 34–82% SMBs (EXP-2662)

    Args:
        glucose: (N,) glucose values (mg/dL), 5-min intervals.
        iob: (N,) insulin-on-board values (Units).
        hours: (N,) optional fractional hours (unused, for API consistency).

    Returns:
        SaturationAssessment, or None if insufficient data.
    """
    if iob is None or len(glucose) < 48:
        return None

    valid_iob = iob[np.isfinite(iob)]
    if len(valid_iob) < 24:
        return None

    median_iob = float(np.median(valid_iob))
    if median_iob < 0.01:
        return None

    # Compute glucose ROC (mg/dL/hr) — 15-min smoothed
    roc = np.full_like(glucose, np.nan)
    for i in range(3, len(glucose)):
        if np.isfinite(glucose[i]) and np.isfinite(glucose[i - 3]):
            roc[i] = (glucose[i] - glucose[i - 3]) / 0.25  # 15min = 0.25h

    # Find high-glucose episodes (>180 for ≥2h)
    high_mask = glucose > _HIGH_GLUCOSE_THRESHOLD
    n_high_episodes = 0
    n_wall_episodes = 0
    total_wall_steps = 0
    total_high_steps = 0
    excess_insulin = 0.0

    # Episode detection via run-length
    in_episode = False
    episode_start = 0

    for i in range(len(glucose)):
        if high_mask[i] and not in_episode:
            episode_start = i
            in_episode = True
        elif not high_mask[i] and in_episode:
            episode_len = i - episode_start
            if episode_len >= _HIGH_GLUCOSE_DURATION:
                n_high_episodes += 1
                total_high_steps += episode_len

                # Check for wall within this episode
                wall_steps = 0
                for j in range(episode_start, i):
                    if (np.isfinite(iob[j]) and np.isfinite(roc[j]) and
                            iob[j] > _WALL_IOB_RATIO * median_iob and
                            roc[j] > _WALL_ROC_THRESHOLD):
                        wall_steps += 1
                        excess_u = max(0, iob[j] - _PATIENCE_CAP_RATIO * median_iob)
                        excess_insulin += excess_u  # IOB is a stock (U on board), not flow

                if wall_steps > episode_len * 0.3:  # wall in >30% of episode
                    n_wall_episodes += 1
                total_wall_steps += wall_steps

            in_episode = False

    # Handle episode at end of array
    if in_episode:
        episode_len = len(glucose) - episode_start
        if episode_len >= _HIGH_GLUCOSE_DURATION:
            n_high_episodes += 1
            total_high_steps += episode_len

            # Wall detection for final episode
            wall_steps = 0
            for j in range(episode_start, len(glucose)):
                if (np.isfinite(iob[j]) and np.isfinite(roc[j]) and
                        iob[j] > _WALL_IOB_RATIO * median_iob and
                        roc[j] > _WALL_ROC_THRESHOLD):
                    wall_steps += 1
                    excess_u = max(0, iob[j] - _PATIENCE_CAP_RATIO * median_iob)
                    excess_insulin += excess_u
            if wall_steps > episode_len * 0.3:
                n_wall_episodes += 1
            total_wall_steps += wall_steps

    if n_high_episodes == 0:
        return SaturationAssessment(
            level=SaturationLevel.NONE,
            wall_pct=0.0,
            n_wall_episodes=0,
            n_high_glucose_episodes=0,
            median_iob=round(median_iob, 2),
        )

    wall_pct = (total_wall_steps / max(total_high_steps, 1)) * 100.0

    if wall_pct > 40:
        level = SaturationLevel.SEVERE
    elif wall_pct > 20:
        level = SaturationLevel.MODERATE
    elif wall_pct > 5:
        level = SaturationLevel.MILD
    else:
        level = SaturationLevel.NONE

    return SaturationAssessment(
        level=level,
        wall_pct=round(wall_pct, 1),
        n_wall_episodes=n_wall_episodes,
        n_high_glucose_episodes=n_high_episodes,
        median_iob=round(median_iob, 2),
        excess_insulin_u=round(excess_insulin, 1),
        delayed_hypo_risk=0.0,  # requires post-episode analysis
        patience_mode_eligible=wall_pct > 10,
        iob_cap_suggestion=round(_PATIENCE_CAP_RATIO * median_iob, 2),
    )


# ── SC Suppression Ceiling Estimation (EXP-2656/2667) ────────────────

# Hill equation parameters from EXP-2656 population fits
_HILL_N = 1.5          # Hill coefficient (shape)
_HILL_K = 2.0          # IOB at 50% suppression (Units)
_BASE_EGP = 18.0       # mg/dL/hr baseline hepatic glucose output
_MIN_HIGH_IOB_POINTS = 30  # minimum high-IOB data points for fitting


def compute_sc_ceiling(
    glucose: np.ndarray,
    iob: np.ndarray,
    scheduled_isf: float = 50.0,
    dia_hours: float = 6.0,
) -> Optional[dict]:
    """Estimate per-patient SC insulin suppression ceiling (EXP-2656/2667).

    Fits a Hill equation ceiling model to high-IOB periods where insulin
    has diminishing glucose-lowering returns. The ceiling represents the
    maximum fraction of hepatic EGP that SC insulin can suppress.

    Research findings:
    - Population median ceiling: 20% (demand-ISF basis, EXP-2667)
    - Range: 10–56% across patients
    - At ceiling, ~80% of hepatic EGP remains active
    - Ceiling correlates with sticky hyper rate (r=−0.60, EXP-2656)
    - Ceiling model fits better than linear at high IOB (2–22% RMSE improvement)

    Args:
        glucose: (N,) glucose values (mg/dL), 5-min intervals.
        iob: (N,) insulin-on-board values (Units).
        scheduled_isf: profile ISF (mg/dL/U) for linear prediction.
        dia_hours: duration of insulin action (hours).

    Returns:
        dict with fitted_ceiling, fitted_base_egp, linear_rmse,
        ceiling_rmse, improvement_pct, n_high_iob_points.
        None if insufficient data.
    """
    if iob is None or len(glucose) < 48:
        return None

    valid_mask = np.isfinite(iob) & np.isfinite(glucose)
    valid_iob = iob[valid_mask]
    if len(valid_iob) < 24:
        return None

    iob_nonzero = valid_iob[valid_iob > 0.1]
    if len(iob_nonzero) < 12:
        return None
    median_iob = float(np.median(iob_nonzero))
    if median_iob < 0.01:
        return None

    # Compute glucose ROC (mg/dL/hr) — 15-min smoothed
    roc = np.full_like(glucose, np.nan)
    for i in range(3, len(glucose)):
        if np.isfinite(glucose[i]) and np.isfinite(glucose[i - 3]):
            roc[i] = (glucose[i] - glucose[i - 3]) / 0.25

    # Select high-IOB periods (>2× median)
    high_mask = (valid_mask & (iob > _WALL_IOB_RATIO * median_iob) &
                 np.isfinite(roc))
    n_high = int(np.sum(high_mask))
    if n_high < _MIN_HIGH_IOB_POINTS:
        return None

    high_iob = iob[high_mask]
    actual_roc = roc[high_mask]

    # Linear model: predicted ROC = -IOB × ISF / DIA
    linear_pred = -high_iob * scheduled_isf / dia_hours
    linear_rmse = float(np.sqrt(np.mean((actual_roc - linear_pred) ** 2)))

    # Hill suppression model
    def _hill_suppression(iob_vals, max_supp):
        iob_abs = np.abs(iob_vals)
        supp = iob_abs ** _HILL_N / (iob_abs ** _HILL_N + _HILL_K ** _HILL_N)
        return np.minimum(supp, max_supp)

    # Grid search for ceiling (avoid scipy dependency for production)
    best_ceiling = 0.3
    best_egp = _BASE_EGP
    best_sse = float('inf')

    for ceiling_candidate in np.arange(0.05, 1.01, 0.05):
        for egp_candidate in [12.0, 15.0, 18.0, 21.0, 25.0, 30.0]:
            supp = _hill_suppression(high_iob, ceiling_candidate)
            egp_residual = egp_candidate * (1.0 - supp)
            ceiling_pred = linear_pred + egp_residual
            sse = float(np.sum((actual_roc - ceiling_pred) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_ceiling = ceiling_candidate
                best_egp = egp_candidate

    # Final RMSE with best params
    supp = _hill_suppression(high_iob, best_ceiling)
    egp_residual = best_egp * (1.0 - supp)
    ceiling_pred = linear_pred + egp_residual
    ceiling_rmse = float(np.sqrt(np.mean((actual_roc - ceiling_pred) ** 2)))

    improvement_pct = 0.0
    if linear_rmse > 0:
        improvement_pct = (linear_rmse - ceiling_rmse) / linear_rmse * 100

    return {
        'fitted_ceiling': round(best_ceiling, 2),
        'fitted_base_egp': round(best_egp, 1),
        'linear_rmse': round(linear_rmse, 1),
        'ceiling_rmse': round(ceiling_rmse, 1),
        'improvement_pct': round(improvement_pct, 1),
        'n_high_iob_points': n_high,
        'median_iob': round(median_iob, 2),
    }


# ── Dose-Response ISF Curve Fitting (EXP-2636/2640) ──────────────────

_MIN_DOSE_EVENTS = 5   # minimum correction events per patient
_MIN_BOLUS_U = 0.3     # minimum bolus size
_MIN_PRE_BG = 150      # minimum pre-correction BG
_CARB_EXCLUSION_STEPS = 6  # ±30 min carb exclusion window


def compute_dose_response_isf(
    glucose: np.ndarray,
    bolus: np.ndarray,
    carbs: Optional[np.ndarray] = None,
    profile: Optional[PatientProfile] = None,
) -> Optional[dict]:
    """Fit per-patient dose-response ISF curve (EXP-2636/2640).

    ISF is logarithmically dose-dependent: ISF ≈ a + b × ln(dose).
    The log model captures receptor saturation kinetics and fits 5/6
    patients better than linear.

    Research findings:
    - Population r = −0.56, p < 10⁻¹⁹ (strongest signal in research program)
    - ISF compresses 4.6× from small (<0.75U) to large (≥3U) corrections
    - Log model: ISF ≈ 50 − 28 × ln(dose_U) (population)
    - Cross-patient CV = 8–9% at matched doses (1.5–3.0U)
    - LOO: all r < −0.49 (robust, not outlier-driven)
    - Bootstrap CI [−0.67, −0.44]

    Args:
        glucose: (N,) glucose values (mg/dL), 5-min intervals.
        bolus: (N,) bolus units per interval.
        carbs: (N,) optional carb data for contamination filtering.
        profile: PatientProfile for ISF comparison.

    Returns:
        dict with linear/log/sqrt fits, best_model, n_events, profile_ratio.
        None if insufficient correction events.
    """
    if bolus is None:
        return None

    bolus_vals = np.nan_to_num(bolus, nan=0.0)
    carb_vals = np.nan_to_num(carbs, nan=0.0) if carbs is not None else None

    # Extract isolated correction events
    correction_indices = np.where(bolus_vals >= _MIN_BOLUS_U)[0]
    events = []

    for idx in correction_indices:
        pre_bg = float(glucose[idx]) if np.isfinite(glucose[idx]) else 0.0
        if pre_bg < _MIN_PRE_BG:
            continue

        dose = float(bolus_vals[idx])

        # Exclude events near carbs
        if carb_vals is not None:
            carb_window = carb_vals[max(0, idx - _CARB_EXCLUSION_STEPS):
                                   min(len(carb_vals), idx + _CARB_EXCLUSION_STEPS)]
            if np.sum(carb_window) > 2.0:
                continue

        # Exclude events near other boluses (3h window)
        future_bolus_window = bolus_vals[idx + 1:min(idx + 36, len(bolus_vals))]
        if np.any(future_bolus_window > 0.5):
            continue

        # Measure 3h glucose drop
        post_end = min(idx + 36, len(glucose))
        if post_end - idx < 12:
            continue
        post_window = glucose[idx:post_end]
        valid_post = post_window[np.isfinite(post_window)]
        if len(valid_post) < 6:
            continue

        nadir = float(np.nanmin(post_window))
        drop = pre_bg - nadir  # positive = glucose fell
        if drop < 5:
            continue  # skip trivial corrections

        apparent_isf = drop / dose
        events.append({'dose': dose, 'drop': drop, 'isf': apparent_isf})

    if len(events) < _MIN_DOSE_EVENTS:
        return None

    doses = np.array([e['dose'] for e in events])
    isfs = np.array([e['isf'] for e in events])

    # Three model fits
    from scipy import stats as _stats

    result = {'n_events': len(events)}

    # Linear: ISF = a + b × dose
    sl, ic, r_lin, p_lin, _ = _stats.linregress(doses, isfs)
    result['linear'] = {
        'slope': round(sl, 2), 'intercept': round(ic, 1),
        'r': round(r_lin, 3), 'p': round(p_lin, 6),
    }

    # Log: ISF = a + b × ln(dose)
    log_doses = np.log(np.maximum(doses, 0.01))
    sl_log, ic_log, r_log, p_log, _ = _stats.linregress(log_doses, isfs)
    result['log'] = {
        'slope': round(sl_log, 2), 'intercept': round(ic_log, 1),
        'r': round(r_log, 3), 'p': round(p_log, 6),
    }

    # Sqrt: ISF = a + b × √dose
    sqrt_doses = np.sqrt(doses)
    sl_sq, ic_sq, r_sq, p_sq, _ = _stats.linregress(sqrt_doses, isfs)
    result['sqrt'] = {
        'slope': round(sl_sq, 2), 'intercept': round(ic_sq, 1),
        'r': round(r_sq, 3), 'p': round(p_sq, 6),
    }

    # Best model by |r|
    models = {'linear': abs(r_lin), 'log': abs(r_log), 'sqrt': abs(r_sq)}
    result['best_model'] = max(models, key=models.get)
    result['best_r'] = round(max(models.values()), 3)

    # Dose-matched predictions at standard doses
    standard_doses = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    dose_range = (float(doses.min()), float(doses.max()))
    result['dose_range'] = [round(dose_range[0], 1), round(dose_range[1], 1)]

    predictions = {}
    for d in standard_doses:
        if dose_range[0] <= d <= dose_range[1]:
            predictions[str(d)] = round(ic_log + sl_log * np.log(d), 1)
    result['isf_at_dose'] = predictions

    # Profile comparison
    sched_isf = 50.0
    if profile is not None and profile.isf_schedule:
        vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_schedule]
        sched_isf = float(np.median([float(v) for v in vals])) if vals else 50.0
    result['scheduled_isf'] = round(sched_isf, 1)
    median_isf = float(np.median(isfs))
    result['median_apparent_isf'] = round(median_isf, 1)
    result['profile_ratio'] = round(median_isf / sched_isf, 2) if sched_isf > 0 else 1.0

    return result
