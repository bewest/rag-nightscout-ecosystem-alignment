"""ISF advisory functions — 13 variants covering demand-phase, circadian, dose-response."""

from __future__ import annotations
from typing import List, Optional, Tuple
import numpy as np
from ..types import (
    ClinicalReport, MetabolicState, PatientProfile,
    SettingsParameter, SettingsRecommendation, PatternProfile,
    PeriodMetrics,
)
from ..forward_simulator import (
    forward_simulate as _fwd_simulate,
    TherapySettings as _TherapySettings,
    InsulinEvent as _InsulinEvent,
    CarbEvent as _CarbEvent,
)
from ._simulation import simulate_tir_with_settings, MIN_DATA_DAYS, HIGH_CONFIDENCE_DAYS, PER_ADVISOR_TIR_DELTA_CAP_PP


__all__ = [
    'DAY_ZONE',
    'NIGHT_ZONE_END',
    'NIGHT_ZONE_START',
    '_CIRCADIAN_BLOCKS',
    '_CIRCADIAN_ISF_DEVIATION_THRESHOLD',
    '_CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK',
    '_CORR_ISF_GRID',
    '_CORR_SIM_HOURS',
    '_CORR_SIM_STEPS',
    '_CR_K_GRID',
    '_DAY_START_HOUR',
    '_ISF_BIAS_DAMPENING',
    '_ISF_NONLINEARITY_DOSE_THRESHOLD',
    '_JOINT_CR_GRID',
    '_JOINT_ISF_GRID',
    '_MAX_CORR_CARBS',
    '_MEAL_BOLUS_THRESHOLD',
    '_MEAL_CARB_THRESHOLD',
    '_MIN_CORRECTIONS',
    '_MIN_CORR_BOLUS',
    '_MIN_CORR_GLUCOSE',
    '_MIN_MEAL_WINDOWS',
    '_NIGHT_START_HOUR',
    '_OVERRIDE_ISF_MIN_CORRECTIONS',
    '_OVERRIDE_ISF_MIN_DIFF',
    '_POPULATION_CSF',
    '_POPULATION_ISF_BETA',
    '_POPULATION_K',
    '_POPULATION_K_DAY',
    '_POPULATION_K_NIGHT',
    '_SIM_DURATION_HOURS',
    '_SIM_WINDOW_STEPS',
    '_calibrate_circadian_k',
    '_calibrate_correction_isf',
    '_calibrate_counter_reg_k',
    '_estimate_csf_from_tir',
    '_estimate_typical_correction_dose',
    '_evaluate_joint_settings',
    '_extract_correction_windows',
    '_extract_meal_windows_from_arrays',
    'advise_circadian_isf',
    'advise_circadian_isf_profiled',
    'advise_correction_denominator_isf',  # Wave-12: multi-factor deconfounding
    'advise_correction_isf',
    'advise_dose_response_isf',
    'advise_forward_sim_optimization',
    'advise_isf',
    'advise_isf_dual_phase',
    'advise_isf_nonlinearity',
    'advise_isf_segmented',
    'advise_override_isf',
    'advise_patience_mode',
    'advise_response_curve_isf',
    'advise_sc_ceiling',
]


def advise_isf(clinical: ClinicalReport,
               profile: PatientProfile,
               days_of_data: float,
               dual_phase: Optional['DualPhaseISF'] = None,
               ) -> Optional[SettingsRecommendation]:
    """Generate ISF recommendation targeting demand-phase ISF.

    CORRECTED 2026-04-18 (egp-evidence-synthesis-report):
    Apparent ISF (2-10× inflated, EXP-2651) is DEPRECATED as a
    recommendation target. Demand-phase ISF (0-2h drop/dose) measures
    the true insulin effect and IS the validated target.

    When demand-phase ISF is available (from compute_demand_isf()):
      - Target demand ISF with conservative 25% step
      - Confidence scales with data and demand-phase CI quality

    When demand-phase ISF is NOT available:
      - Flag the apparent ISF discrepancy as informational
      - Recommend computing demand-phase analysis

    Multi-factor ISF methods validated (EXP-2640: r=-0.56, EXP-1301:
    R²=0.805, EXP-2652: 10-20% RMSE improvement).
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    # PRIORITY 1: Demand-phase ISF — the validated target
    if dual_phase is not None and dual_phase.n_corrections >= 5:
        demand = dual_phase.demand_isf
        gap = demand - current_isf
        gap_pct = abs(gap / current_isf) * 100 if current_isf > 0 else 0

        if gap_pct > 15 and dual_phase.confidence in ('medium', 'high'):
            step_frac = 0.25  # conservative 25% step
            suggested = current_isf + gap * step_frac
            magnitude = round(gap_pct * step_frac, 1)
            predicted_delta = min(3.0, gap_pct * 0.08)
            confidence = min(0.8, days_of_data / HIGH_CONFIDENCE_DAYS)

            return SettingsRecommendation(
                parameter=SettingsParameter.ISF,
                direction="increase" if gap > 0 else "decrease",
                magnitude_pct=magnitude,
                current_value=current_isf,
                suggested_value=round(suggested, 0),
                predicted_tir_delta=round(predicted_delta, 1),
                affected_hours=(0.0, 24.0),
                confidence=confidence,
                evidence=(
                    f"Demand-phase ISF (0–2h) = {demand:.0f} mg/dL/U "
                    f"(CI: [{dual_phase.demand_ci_low:.0f}–"
                    f"{dual_phase.demand_ci_high:.0f}], "
                    f"N={dual_phase.n_corrections}, "
                    f"confidence={dual_phase.confidence}). "
                    f"Profile ISF = {current_isf:.0f}. "
                    f"Apparent ISF = {dual_phase.apparent_isf:.0f} "
                    f"({dual_phase.inflation_ratio:.1f}× inflated, "
                    f"DEPRECATED as target, EXP-2651)."),
                rationale=(
                    f"Demand-phase ISF measures true insulin effect (0–2h, "
                    f"before EGP suppression). Conservative 25% step: "
                    f"{current_isf:.0f} → {suggested:.0f} mg/dL/U. "
                    f"Validated: dose-dependent r=-0.56 (EXP-2640), "
                    f"response-curve R²=0.805 (EXP-1301), "
                    f"circadian 10-20% RMSE (EXP-2652). "
                    f"Confirmable within 2 weeks of stable use."),
            )
        # Demand-phase ISF available but gap is small or confidence low
        return None

    # PRIORITY 2: Apparent ISF discrepancy — informational only
    # (demand-phase ISF not available; apparent ISF is deprecated as target)
    if clinical.isf_discrepancy is None or clinical.isf_discrepancy < 1.5:
        return None

    effective = clinical.effective_isf or current_isf
    confidence = min(0.5, days_of_data / HIGH_CONFIDENCE_DAYS)

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="informational",
        magnitude_pct=0.0,
        current_value=current_isf,
        suggested_value=current_isf,
        predicted_tir_delta=0.0,
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(f"Apparent ISF is {clinical.isf_discrepancy:.1f}× profile ISF "
                  f"({effective:.0f} vs {current_isf:.0f} mg/dL/U). "
                  f"Apparent ISF is DEPRECATED as recommendation target — "
                  f"it is 2–10× inflated by AID compensation (EXP-2651)."),
        rationale=(f"Demand-phase ISF (0–2h) is needed for actionable "
                   f"recommendations. Apparent ISF ({effective:.0f}) includes "
                   f"AID controller compensation and EGP suppression. "
                   f"Run dual-phase analysis (compute_demand_isf) for the "
                   f"validated ISF target. Multi-factor methods confirmed: "
                   f"EXP-2640, EXP-1301, EXP-2652."),
    )


# ── ISF Non-Linearity Advisory (EXP-2511–2518) ──────────────────────

# Population power-law exponent: ISF(dose) = ISF_base × dose^(-β)
# β = 0.899 means a 2U correction is 46% less effective per unit than 1U.
# 17/17 patients show improved prediction with power-law ISF (+53% MAE).
_POPULATION_ISF_BETA = 0.9
_ISF_NONLINEARITY_DOSE_THRESHOLD = 1.5  # warn when typical correction > this


def advise_isf_nonlinearity(
    clinical: ClinicalReport,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """Generate advisory when correction doses show diminishing returns.

    Research: EXP-2511–2518. ISF follows power-law ISF(dose) = ISF_base × dose^(-β)
    with population β = 0.9. This means larger corrections are progressively less
    effective per unit of insulin. A 2U correction achieves only ~1.07× the glucose
    drop of a 1U correction (2^0.1 ≈ 1.07), not 2×.

    NOTE: Dose-dependent ISF (r=-0.56, EXP-2640) is a validated multi-factor
    finding, consistent with SC suppression ceiling (EXP-2656) and demand vs
    apparent ISF split (EXP-2651). Split-dosing guidance is safe because it
    doesn't change controller feedback dynamics.

    The advisory fires when:
    - There is enough data (>= MIN_DATA_DAYS)
    - The patient's typical correction dose exceeds 1.5U

    If no bolus data is available, falls back to estimating typical correction
    from ISF and glucose excursion patterns.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    # Estimate typical correction dose
    typical_dose = _estimate_typical_correction_dose(
        clinical, profile, bolus)

    if typical_dose is None or typical_dose <= _ISF_NONLINEARITY_DOSE_THRESHOLD:
        return None

    beta = _POPULATION_ISF_BETA

    # Compute the effectiveness penalty
    # At dose=1, ISF = ISF_base. At dose=d, ISF = ISF_base * d^(-β)
    # Per-unit effectiveness at dose d relative to 1U: d^(-β)
    effectiveness_at_typical = typical_dose ** (-beta)
    penalty_pct = (1.0 - effectiveness_at_typical) * 100.0

    # What split-dose would achieve: 2 × half-dose corrections
    half_dose = typical_dose / 2.0
    # Total drop single: ISF_base * typical^(1-β)
    # Total drop split:  2 * ISF_base * half^(1-β)
    # Ratio: 2 * (half/typical)^(1-β) = 2 * 0.5^(1-β)
    split_ratio = 2.0 * (0.5 ** (1.0 - beta))
    split_improvement_pct = (split_ratio - 1.0) * 100.0

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = (float(np.median([float(v) for v in isf_vals]))
                   if isf_vals else 50.0)

    # ISF at the typical dose vs at 1U
    isf_at_1u = current_isf  # profile ISF is calibrated at ~1U scale
    isf_at_typical = isf_at_1u * effectiveness_at_typical

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="decrease",
        magnitude_pct=round(penalty_pct, 0),
        current_value=current_isf,
        suggested_value=round(isf_at_typical, 0),
        # Cap predicted TIR delta to a sane range. The split-dose
        # improvement is an upper bound on what dose-shaping could
        # achieve; in practice TIR impact is dominated by other
        # factors (meal timing, basal posture). Mirroring the cap
        # other ISF advisors use (e.g. demand-phase ISF capped at 3.0pp).
        predicted_tir_delta=round(min(3.0, split_improvement_pct * 0.03), 1),
        affected_hours=(0.0, 24.0),
        confidence=min(0.6, days_of_data / HIGH_CONFIDENCE_DAYS),
        evidence=(
            f"ISF non-linearity (EXP-2511): typical correction dose "
            f"{typical_dose:.1f}U is {penalty_pct:.0f}% less effective "
            f"per unit than 1U (power-law β={beta}). "
            f"Splitting into 2×{half_dose:.1f}U would be "
            f"~{split_improvement_pct:.0f}% more effective total."
        ),
        rationale=(
            f"Correction doses above {_ISF_NONLINEARITY_DOSE_THRESHOLD}U "
            f"show diminishing returns. At {typical_dose:.1f}U, each unit "
            f"achieves only {isf_at_typical:.0f} mg/dL drop vs "
            f"{isf_at_1u:.0f} mg/dL at 1U. Consider: (1) splitting large "
            f"corrections into smaller doses spaced 30+ min apart, "
            f"(2) using ISF={isf_at_typical:.0f} for doses ≥{typical_dose:.0f}U. "
            f"This is a pharmacokinetic property (β={beta}), not circadian."
        ),
    )


def _estimate_typical_correction_dose(
    clinical: ClinicalReport,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
) -> Optional[float]:
    """Estimate the typical correction bolus dose for this patient.

    Uses bolus data if available, otherwise estimates from ISF and
    typical glucose excursions above target.
    """
    if bolus is not None:
        # Filter to correction-sized boluses (> 0.3U, < 10U).
        # Require >= 10 events: a sample size of 5 was too low to
        # support a published settings-change recommendation
        # (GAP-ADVR-001).
        corrections = bolus[(bolus > 0.3) & (bolus < 10.0)]
        if len(corrections) >= 10:
            return float(np.median(corrections))

    # Fallback: estimate from ISF and typical high-glucose excursion
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    if not isf_vals:
        return None

    current_isf = float(np.median([float(v) for v in isf_vals]))
    if current_isf <= 0:
        return None

    # Typical correction: (mean glucose - target) / ISF
    target = profile.target_range[1] if hasattr(profile, 'target_range') else 120.0
    mean_glucose = getattr(clinical, 'mean_glucose', None)
    if mean_glucose is None:
        return None

    excursion = max(0.0, mean_glucose - target)
    if excursion < 10.0:
        return None

    return excursion / current_isf


def advise_isf_segmented(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState],
                         hours: np.ndarray,
                         clinical: ClinicalReport,
                         profile: PatientProfile,
                         patterns: Optional[PatternProfile],
                         days_of_data: float,
                         ) -> List[SettingsRecommendation]:
    """Recommend time-segmented ISF when circadian variation is significant.

    Research: ISF varies 29.7% mean across time of day (EXP-765).
    When variation >50%, recommend 2-4 ISF segments for better control.

    NOTE: Circadian ISF ratios are observed APPARENT values that include
    time-varying AID compensation. Circadian segmentation adjusts relative
    ratios, which is more robust than absolute ISF changes. Circadian ISF
    validated: 10-20% RMSE improvement with 2-block split (EXP-2652).
    Underlying ISF values carry inflation from controller feedback (EXP-2651).

    Args:
        glucose, metabolic, hours: standard pipeline data.
        clinical: ClinicalReport with effective ISF.
        profile: current therapy profile.
        patterns: PatternProfile with isf_by_hour.
        days_of_data: data coverage.

    Returns:
        List of ISF SettingsRecommendations for time segments.
    """
    if patterns is None or patterns.isf_by_hour is None:
        return []
    if days_of_data < 7.0:
        return []
    if patterns.isf_variation_pct < 50.0:
        return []

    isf_by_hour = patterns.isf_by_hour
    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    recs = []
    # Group hours into segments where ISF is consistently above/below mean
    for name, h_start, h_end in PERIODS:
        h_range = range(int(h_start), int(h_end) if h_end <= 24 else 24)
        if not h_range:
            continue
        period_isf_mult = float(np.mean([isf_by_hour[h % 24] for h in h_range]))

        # Only recommend if this period's ISF differs >20% from average
        if abs(period_isf_mult - 1.0) < 0.20:
            continue

        suggested_isf = current_isf * period_isf_mult
        direction = "increase" if period_isf_mult > 1.0 else "decrease"
        magnitude = abs(period_isf_mult - 1.0) * 100

        # Simulate TIR impact
        if metabolic is not None:
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                isf_multiplier=period_isf_mult,
                hour_range=(h_start, h_end))
            predicted_delta = round((tir_sim - tir_now) * 100, 1)
        else:
            predicted_delta = round(magnitude * 0.1, 1)  # conservative estimate

        confidence = min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_isf,
            suggested_value=round(suggested_isf, 0),
            predicted_tir_delta=predicted_delta,
            affected_hours=(h_start, h_end),
            confidence=confidence,
            evidence=f"ISF variation is {patterns.isf_variation_pct:.0f}% across day (EXP-765). "
                     f"Period {name}: ISF multiplier {period_isf_mult:.2f}×.",
            rationale=f"{direction.capitalize()} ISF by {magnitude:.0f}% during {name} "
                      f"({h_start:.0f}:00-{h_end:.0f}:00) from {current_isf:.0f} to "
                      f"{suggested_isf:.0f} mg/dL/U. Based on observed circadian ISF variation.",
        ))

    return recs


# ── Forward Sim Joint ISF×CR Optimization (EXP-2562/2567/2568) ────────

# Grid parameters for joint optimization
_JOINT_ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
_JOINT_CR_GRID = [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
_MIN_MEAL_WINDOWS = 10
_MEAL_CARB_THRESHOLD = 10.0   # grams
_MEAL_BOLUS_THRESHOLD = 0.1   # units
_SIM_DURATION_HOURS = 4.0
_SIM_WINDOW_STEPS = 48        # 4h × 12 steps/h
# EXP-2572: sim overshoots correction drops by ~22% (actual/sim = 0.78).
# Dampen ISF recommendations toward 1.0 by this factor.
_ISF_BIAS_DAMPENING = 0.78


def _extract_meal_windows_from_arrays(
    glucose: np.ndarray,
    hours: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    iob: np.ndarray,
    profile: PatientProfile,
    max_windows: int = 50,
) -> list:
    """Extract meal windows from time-aligned arrays for forward sim.

    Finds points where carbs > threshold and bolus > threshold, then
    extracts 4-hour windows of glucose data for simulation comparison.
    """
    N = len(glucose)
    meal_mask = (carbs > _MEAL_CARB_THRESHOLD) & (bolus > _MEAL_BOLUS_THRESHOLD)
    meal_indices = np.where(meal_mask)[0]

    # Extract profile values (median across schedule entries)
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    median_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    median_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0
    median_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    windows = []
    for idx in meal_indices:
        if idx + _SIM_WINDOW_STEPS >= N:
            continue
        window_glucose = glucose[idx:idx + _SIM_WINDOW_STEPS]
        if np.sum(np.isnan(window_glucose)) > 5:
            continue
        if np.isnan(glucose[idx]):
            continue

        windows.append({
            'g': float(glucose[idx]),
            'b': float(bolus[idx]),
            'c': float(carbs[idx]),
            'iob': float(iob[idx]) if not np.isnan(iob[idx]) else 0.0,
            'h': float(hours[idx]),
            'isf': median_isf,
            'cr': median_cr,
            'basal': median_basal,
        })
        if len(windows) >= max_windows:
            break

    return windows


def _evaluate_joint_settings(windows: list, isf_mult: float, cr_mult: float) -> Optional[float]:
    """Evaluate a single ISF×CR multiplier pair across meal windows.

    Returns mean TIR (70-180 mg/dL) as a fraction, or None if evaluation fails.
    """
    tirs = []
    for w in windows:
        try:
            # Use decoupled CSF when carbs are present (EXP-2596)
            csf = _POPULATION_CSF if w['c'] > 1.0 else None
            s = _TherapySettings(
                isf=w['isf'] * isf_mult,
                cr=w['cr'] * cr_mult,
                basal_rate=w['basal'],
                dia_hours=5.0,
                carb_sensitivity=csf,
            )
            r = _fwd_simulate(
                initial_glucose=w['g'], settings=s,
                duration_hours=_SIM_DURATION_HOURS,
                start_hour=w['h'],
                bolus_events=[_InsulinEvent(0, w['b'])],
                carb_events=[_CarbEvent(0, w['c'])],
                initial_iob=w['iob'],
                noise_std=0, seed=42,
            )
            gluc = np.array(r.glucose)
            tirs.append(float(np.mean((gluc >= 70) & (gluc <= 180))))
        except Exception:
            pass
    return float(np.mean(tirs)) if tirs else None


def advise_forward_sim_optimization(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    iob: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Generate ISF/CR recommendations using forward sim joint optimization.

    Research basis:
      - EXP-2562: Forward sim counterfactuals validated (ISF+20%→+2.1pp TIR)
      - EXP-2567: CR optimal ~2× profile (mean 2.10, median 2.00)
      - EXP-2568: Joint ISF×CR adds +8.9pp synergy vs single-axis
      - EXP-2569: Validated for DIRECTION only, NOT magnitude predictions

    Extracts meal windows from patient data, runs 7×7 joint ISF×CR grid
    search using the forward simulator, and generates directional
    recommendations for settings adjustments.

    NOTE: predicted_tir_delta values are DIRECTIONAL INDICATORS, not
    calibrated magnitude predictions. The forward sim cannot predict
    absolute TIR improvement (EXP-2569: MAE=0.409).

    Args:
        glucose: (N,) cleaned glucose at 5-min intervals.
        hours: (N,) fractional hours.
        profile: current therapy profile with ISF, CR, basal.
        bolus: (N,) bolus insulin per step.
        carbs: (N,) carb intake per step.
        iob: (N,) insulin on board per step.
        days_of_data: data coverage in days.

    Returns:
        List of SettingsRecommendation (0-2 items: ISF and/or CR).
    """
    if bolus is None or carbs is None or iob is None:
        return []
    if days_of_data < MIN_DATA_DAYS:
        return []

    windows = _extract_meal_windows_from_arrays(
        glucose, hours, bolus, carbs, iob, profile
    )
    if len(windows) < _MIN_MEAL_WINDOWS:
        return []

    # Run joint grid search
    best_tir = -1.0
    best_isf, best_cr = 1.0, 1.0
    baseline_tir = _evaluate_joint_settings(windows, 1.0, 1.0)
    if baseline_tir is None:
        return []

    for isf_m in _JOINT_ISF_GRID:
        for cr_m in _JOINT_CR_GRID:
            tir = _evaluate_joint_settings(windows, isf_m, cr_m)
            if tir is not None and tir > best_tir:
                best_tir = tir
                best_isf = isf_m
                best_cr = cr_m

    recs = []
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, len(windows) / 30)

    # NOTE (EXP-2601/2602): ISF recommendation REMOVED from sim optimization.
    # The ISF multiplier from the grid search is a SIM CALIBRATION parameter
    # (ISF×0.5 needed for ranking accuracy), NOT a clinical recommendation.
    # Clinical ISF should come from advise_correction_isf() which uses actual
    # correction bolus outcomes, not from the sim calibration multiplier.

    # NOTE (EXP-2610): CR recommendation ALSO REMOVED from sim optimization.
    # The sim CR always converges to extreme values (0.5× in independent search,
    # or 3.0× in joint search with ISF×0.5) because the simplified absorption
    # model requires both ISF and CR to be halved/doubled for calibration.
    # The sim CR is a CALIBRATION ARTIFACT, not a clinical recommendation.
    # Clinical CR should come from advise_effective_cr() which uses actual
    # meal-bolus glucose response outcomes (EXP-2609: effective CR validated,
    # H2 and H3 confirmed, dawn CR tighter for 6/9 patients).

    return []


# ── Correction-Based ISF Calibration (EXP-2579/2582/2585) ─────────────

# Counter-regulation model parameters
_CR_K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
_CORR_ISF_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]
_CORR_SIM_HOURS = 2.0
_CORR_SIM_STEPS = int(_CORR_SIM_HOURS * 12)
_MIN_CORR_BOLUS = 0.5       # minimum bolus (U) to qualify as correction
_MIN_CORR_GLUCOSE = 150.0   # minimum glucose (mg/dL) for correction
_MAX_CORR_CARBS = 1.0       # maximum carbs (g) — no meals
_MIN_CORRECTIONS = 20       # minimum corrections for reliable calibration
_POPULATION_K = 1.5         # fallback when < MIN_CORRECTIONS
# EXP-2588: Night counter-reg is +1.5 higher than day (dawn phenomenon)
_DAY_START_HOUR = 6.0
_NIGHT_START_HOUR = 22.0
_POPULATION_K_DAY = 2.2     # median day k from EXP-2588
_POPULATION_K_NIGHT = 3.8   # median night k from EXP-2588
# EXP-2596: Decoupled carb sensitivity. When ISF is calibrated (×0.5),
# coupled CSF = ISF/CR drops to 25% of profile — carbs barely register.
# Optimal decoupled CSF = 2.0 (sweet spot: r=0.933 ranking + 53% peaks).
_POPULATION_CSF = 2.0       # mg/dL per gram carb (decoupled from ISF/CR)


def _estimate_csf_from_tir(tir: float) -> float:
    """Estimate per-patient CSF from TIR (EXP-2598).

    EXP-2598 found CSF correlates with TIR (r=-0.655): lower TIR patients
    need higher CSF. Linear fit from 9 patients:
      CSF ≈ 7.5 - 5.5 × TIR  (clamped to [1.0, 6.5])
    """
    csf = 7.5 - 5.5 * tir
    return float(np.clip(csf, 1.0, 6.5))


def _extract_correction_windows(
    glucose: np.ndarray,
    hours: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    iob: np.ndarray,
    profile: PatientProfile,
    max_windows: int = 200,
) -> list:
    """Extract correction bolus events with 2h glucose follow-up.

    Corrections are boluses ≥0.5U at glucose ≥150 with <1g carbs.
    """
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    median_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    median_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0
    median_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    N = len(glucose)
    windows = []
    for i in range(N - _CORR_SIM_STEPS):
        if bolus[i] < _MIN_CORR_BOLUS or glucose[i] < _MIN_CORR_GLUCOSE:
            continue
        if carbs[i] > _MAX_CORR_CARBS:
            continue
        if np.isnan(glucose[i]):
            continue
        wg = glucose[i : i + _CORR_SIM_STEPS]
        valid_count = np.sum(~np.isnan(wg))
        if valid_count < _CORR_SIM_STEPS * 0.6:
            continue
        actual_end = float(np.nanmean(wg[-3:]))
        if np.isnan(actual_end):
            continue
        actual_drop = actual_end - float(glucose[i])

        windows.append({
            'g': float(glucose[i]),
            'b': float(bolus[i]),
            'iob': float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            'h': float(hours[i]),
            'isf': median_isf,
            'cr': median_cr,
            'basal': median_basal,
            'actual_drop': actual_drop,
        })
        if len(windows) >= max_windows:
            break

    return windows


def _calibrate_counter_reg_k(windows: list) -> float:
    """Find optimal counter-regulation k from correction windows.

    Sweeps k values and finds the one where actual/sim drop ratio ≈ 1.0.

    Research basis: EXP-2582 (per-patient k calibration).
    """
    if len(windows) < _MIN_CORRECTIONS:
        return _POPULATION_K

    best_k = _POPULATION_K
    best_dist = float('inf')

    for k in _CR_K_GRID:
        ratios = []
        for w in windows:
            try:
                s = _TherapySettings(
                    isf=w['isf'], cr=w['cr'],
                    basal_rate=w['basal'], dia_hours=5.0,
                )
                r = _fwd_simulate(
                    initial_glucose=w['g'], settings=s,
                    duration_hours=_CORR_SIM_HOURS, start_hour=w['h'],
                    bolus_events=[_InsulinEvent(0, w['b'])],
                    carb_events=[], initial_iob=w['iob'],
                    noise_std=0, seed=42, counter_reg_k=k,
                )
                sim_drop = r.glucose[-1] - w['g']
                if abs(sim_drop) > 1.0:
                    ratios.append(w['actual_drop'] / sim_drop)
            except Exception:
                pass

        if len(ratios) >= 10:
            mean_ratio = float(np.mean(ratios))
            dist = abs(mean_ratio - 1.0)
            if dist < best_dist:
                best_dist = dist
                best_k = k

    return best_k


def _calibrate_circadian_k(windows: list) -> tuple:
    """Calibrate separate day and night counter-reg k values.

    Research basis: EXP-2588 (night k +1.5 higher than day k).

    Returns:
        (day_k, night_k) tuple. Falls back to population values if
        insufficient corrections in either period.
    """
    day_windows = [w for w in windows if _DAY_START_HOUR <= w['h'] < _NIGHT_START_HOUR]
    night_windows = [w for w in windows if w['h'] < _DAY_START_HOUR or w['h'] >= _NIGHT_START_HOUR]

    day_k = _calibrate_counter_reg_k(day_windows) if len(day_windows) >= _MIN_CORRECTIONS else _POPULATION_K_DAY
    night_k = _calibrate_counter_reg_k(night_windows) if len(night_windows) >= _MIN_CORRECTIONS else _POPULATION_K_NIGHT

    return day_k, night_k


def _calibrate_correction_isf(windows: list, k: float) -> Optional[float]:
    """Find optimal ISF multiplier from corrections with calibrated k.

    Returns ISF multiplier that minimizes MAE between sim and actual drops.

    Research basis: EXP-2585 (correction-based ISF calibration).
    """
    if len(windows) < _MIN_CORRECTIONS:
        return None

    best_mult = 1.0
    best_mae = float('inf')

    for isf_m in _CORR_ISF_GRID:
        errors = []
        for w in windows:
            try:
                s = _TherapySettings(
                    isf=w['isf'] * isf_m, cr=w['cr'],
                    basal_rate=w['basal'], dia_hours=5.0,
                )
                r = _fwd_simulate(
                    initial_glucose=w['g'], settings=s,
                    duration_hours=_CORR_SIM_HOURS, start_hour=w['h'],
                    bolus_events=[_InsulinEvent(0, w['b'])],
                    carb_events=[], initial_iob=w['iob'],
                    noise_std=0, seed=42, counter_reg_k=k,
                )
                sim_drop = r.glucose[-1] - w['g']
                errors.append(abs(w['actual_drop'] - sim_drop))
            except Exception:
                pass

        if errors:
            mae = float(np.mean(errors))
            if mae < best_mae:
                best_mae = mae
                best_mult = isf_m

    return best_mult


def advise_correction_isf(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    iob: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Generate ISF recommendation from correction bolus analysis.

    NOTE: This function measures APPARENT ISF from correction outcomes,
    which includes AID controller compensation (2–10× inflation, EXP-2651).
    The counter-regulation model partially corrects for this. For more
    accurate estimates, prefer demand-phase ISF (compute_demand_isf).
    Multi-factor ISF methods validated: EXP-2640 r=-0.56, EXP-1301 R²=0.805.

    Research basis:
      - EXP-2579: Counter-regulation model reduces 2.5× overestimation
      - EXP-2582: Per-patient k calibration (10/11 in-range)
      - EXP-2585: Correction ISF differs from meal ISF (+0.34 higher)
      - EXP-2585: Per-patient correction-optimal beats 0.78 dampened (11/12)
      - EXP-2588: Night k is +1.5 higher than day k (dawn phenomenon)

    Uses a two-step calibration with circadian k:
      1. Calibrate day/night counter-regulation k from correction events
      2. With calibrated k, find optimal ISF multiplier (overall)

    This provides a correction-specific ISF recommendation that complements
    the meal-based ISF from advise_forward_sim_optimization().

    Args:
        glucose: (N,) cleaned glucose at 5-min intervals.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        bolus: (N,) bolus insulin per step.
        carbs: (N,) carb intake per step.
        iob: (N,) insulin on board per step.
        days_of_data: data coverage in days.

    Returns:
        List of SettingsRecommendation (0-2 items: overall and/or circadian).
    """
    if bolus is None or carbs is None or iob is None:
        return []
    if days_of_data < MIN_DATA_DAYS:
        return []

    windows = _extract_correction_windows(
        glucose, hours, bolus, carbs, iob, profile
    )
    if len(windows) < _MIN_CORRECTIONS:
        return []

    # Step 1: Calibrate circadian counter-reg k (EXP-2588)
    day_k, night_k = _calibrate_circadian_k(windows)

    # Step 2: Find optimal ISF multiplier using blended k
    # Use overall k for ISF calibration (circadian k for evidence)
    overall_k = _calibrate_counter_reg_k(windows)
    isf_mult = _calibrate_correction_isf(windows, overall_k)
    if isf_mult is None or abs(isf_mult - 1.0) < 0.05:
        return []

    # Build recommendation
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    suggested_isf = current_isf * isf_mult
    direction = "decrease" if isf_mult < 1.0 else "increase"
    magnitude = abs(isf_mult - 1.0) * 100
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, len(windows) / 50)
    tir_delta = min(PER_ADVISOR_TIR_DELTA_CAP_PP, magnitude * 0.05)

    circadian_note = ""
    if abs(night_k - day_k) >= 0.5:
        circadian_note = (
            f" Circadian pattern detected (EXP-2588): day k={day_k:.1f}, "
            f"night k={night_k:.1f} — corrections are less effective overnight."
        )

    return [SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction=direction,
        magnitude_pct=round(magnitude, 0),
        current_value=current_isf,
        suggested_value=round(suggested_isf, 1),
        predicted_tir_delta=round(tir_delta, 1),
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(
            f"Correction-based ISF calibration (EXP-2585): optimal ISF "
            f"multiplier {isf_mult:.1f}× from {len(windows)} correction events. "
            f"Counter-regulation k={overall_k:.1f} (auto-calibrated)."
            f"{circadian_note}"
        ),
        rationale=(
            f"{direction.capitalize()} ISF by {magnitude:.0f}% "
            f"(from {current_isf:.0f} to {suggested_isf:.0f} mg/dL/U). "
            f"Analysis of {len(windows)} correction boluses shows the current ISF "
            f"{'over' if isf_mult < 1.0 else 'under'}estimates correction effect. "
            f"This recommendation accounts for counter-regulatory physiology "
            f"(glucagon/HGP)."
        ),
    )]


# ── Circadian ISF: 2-Zone Recommendation (EXP-2271) ─────────────────

# EXP-2271: 2-zone (day/night) captures 61-90% of circadian ISF benefit.
# ISF varies 4.6-9× within a day. Simple day/night split is optimal for
# most patients and avoids the complexity of 4+ segment schedules.
DAY_ZONE = (7.0, 22.0)
NIGHT_ZONE_START = 22.0
NIGHT_ZONE_END = 7.0


def advise_correction_denominator_isf(
    clinical: ClinicalReport,
    profile: PatientProfile,
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """ISF extraction using correction events only (Wave-12, EXP-2741).
    
    Research basis (Wave-12, Multi-Factor Isolation):
      - EXP-2740: 70% of patients well-matched at equilibrium (EGP handled by basal)
      - EXP-2741: Correction-only denominator yields 67% ISF gap closure (4.3→43.7→63)
      - EXP-2742: Precision +64% but accuracy gap widens
      
    Key insight: Controller compensation is the dominant confound (not EGP).
    By filtering to corrections only, we remove basal/EGP/meal artifacts and
    get the cleanest ISF signal. This approach is safe, interpretable, and
    produces high confidence for 90.9% of patients.
    
    Four confound layers documented:
      1. EGP compensation (✓ already handled by basal)
      2. Steady-state basal (✓ 67% gap closure via this method)
      3. Controller dynamics (🔄 22% residual = safety margin; documented)
      4. Confounding-by-indication (⛔ fundamental observational limit)
    
    Confidence tiers:
      - HIGH: ≥50 correction events, CV<0.5, consistent effect direction
      - MEDIUM: 20-49 events, CV 0.5-1.0
      - LOW: <20 events or CV>1.0 (unreliable, don't recommend)
    
    Args:
        clinical: ClinicalReport with correction event history
        profile: current therapy profile (used for baseline comparison)
        days_of_data: data coverage in days
    
    Returns:
        SettingsRecommendation if sufficient data, else None
        
    Reference: docs/60-research/wave12-multifactor-isolation-report-2026-04-20.md
    """
    if days_of_data < MIN_DATA_DAYS:
        return None
    
    # Extract correction events (filtered for minimal confounding)
    if not hasattr(clinical, 'correction_events') or not clinical.correction_events:
        return None
    
    correction_events = clinical.correction_events
    if len(correction_events) < _MIN_CORRECTIONS:
        return None
    
    # Compute ISF from BG drops post-correction
    # Denominator = correction insulin only (no basal, no meal)
    isf_values = []
    for event in correction_events:
        # Extract relevant fields (depends on event structure)
        correction_insulin = event.get('insulin_units', 0)
        bg_before = event.get('bg_before', None)
        bg_nadir = event.get('bg_nadir', None)
        
        if correction_insulin > _MIN_CORR_BOLUS and bg_before and bg_nadir:
            if bg_before > bg_nadir:  # Must drop
                bg_drop = bg_before - bg_nadir
                isf = bg_drop / correction_insulin if correction_insulin > 0 else None
                if isf and 20 < isf < 500:  # physiological bounds
                    isf_values.append(isf)
    
    if len(isf_values) < _MIN_CORRECTIONS:
        return None
    
    # Compute statistics
    isf_array = np.array(isf_values)
    isf_median = float(np.median(isf_array))
    isf_std = float(np.std(isf_array))
    isf_cv = isf_std / isf_median if isf_median > 0 else float('inf')
    
    # Determine confidence tier
    n_events = len(isf_values)
    if n_events >= 50 and isf_cv < 0.5:
        confidence = 'high'
        reason = f"Correction-denominator ISF from {n_events} events (CV={isf_cv:.2f})"
    elif n_events >= 20 and isf_cv < 1.0:
        confidence = 'medium'
        reason = f"Moderate events {n_events} (CV={isf_cv:.2f})"
    else:
        confidence = 'low'
        reason = f"Limited data: {n_events} events (CV={isf_cv:.2f})"
    
    # Only recommend if improvement is substantial
    profile_isf = profile.isf if hasattr(profile, 'isf') else 50.0
    improvement_pct = abs(isf_median - profile_isf) / profile_isf * 100
    
    if improvement_pct < 5:
        # Not enough improvement
        return None
    
    return SettingsRecommendation(
        param=SettingsParameter.ISF,
        value=isf_median,
        unit='mg/dL per Unit',
        confidence=confidence,
        reason=reason,
        supporting_evidence=[
            f"Median ISF from {n_events} correction events",
            f"Standard deviation: {isf_std:.1f} mg/dL/U (CV={isf_cv:.2f})",
            f"Improvement vs profile: {improvement_pct:.1f}%",
            "Multi-factor deconfounding (Wave-12, EXP-2741): 67% gap closure",
            f"Note: 22% residual gap is controller safety margin (EXP-2738)",
        ]
    )


def advise_circadian_isf(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState],
                         hours: np.ndarray,
                         profile: PatientProfile,
                         days_of_data: float,
                         ) -> List[SettingsRecommendation]:
    """Recommend 2-zone (day/night) ISF split based on circadian variation.

    Research: EXP-2271 shows ISF varies 4.6-9× across the day. A simple
    2-zone split captures 61-90% of the benefit of fully time-varying ISF.
    Insulin is typically MORE effective at night (lower cortisol/GH).

    NOTE: Day/night ISF ratios reflect combined physiology + AID controller
    behavior. Relative splits (ratio-preserving) are safer than absolute
    ISF changes. The underlying ISF values carry inflation from controller
    feedback (EXP-2651). Circadian ISF validated: EXP-2271, EXP-2652.

    The approach:
    1. Compute effective ISF for day vs night periods
    2. If ratio >1.3×, recommend splitting the ISF schedule
    3. Simulate TIR impact of the split

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState for simulation.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        days_of_data: minimum 7 days required.

    Returns:
        List of SettingsRecommendation (0-2 recs: day ISF + night ISF).
    """
    if days_of_data < 7.0 or metabolic is None:
        return []

    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)

    # Compute effective ISF for day vs night via correction response
    day_mask = (hours >= DAY_ZONE[0]) & (hours < DAY_ZONE[1])
    night_mask = ~day_mask

    # Use residual-based ISF estimation: large negative residuals during
    # corrections indicate higher effective ISF
    residual = metabolic.residual
    demand = metabolic.demand

    # During high-demand periods (corrections), measure glucose response
    high_demand = demand > np.percentile(demand[demand > 0], 75) if np.any(demand > 0) else np.zeros(len(demand), dtype=bool)

    day_response = residual[day_mask & high_demand]
    night_response = residual[night_mask & high_demand]

    if len(day_response) < 20 or len(night_response) < 20:
        return []

    day_effect = float(np.abs(np.mean(day_response)))
    night_effect = float(np.abs(np.mean(night_response)))

    # GAP-ADV-EGP fix (EXP-3022b): mean-residual denominators can collapse
    # near zero in well-controlled AID patients where the controller has
    # already nulled net residuals. A small denominator inflates the
    # day/night ratio without bound and produces clinically-unsafe 4-6×
    # ISF recommendations in a single advisory cycle.
    #
    # Two defenses:
    #   (a) require both effects ≥ EFFECT_FLOOR (mg/dL/5min) so neither
    #       side is dominated by floating-point noise;
    #   (b) clamp the per-step ISF multiplier to MAX_STEP_RATIO so any
    #       single advisory cycle moves ISF by at most ±50% (matches the
    #       "Conservative 25% step" pattern at line 141 / 1538 elsewhere
    #       in this module). When the raw ratio implies a larger jump,
    #       cap the suggestion and set safety_flag with an explanation;
    #       subsequent advisory cycles can re-evaluate after the patient
    #       has been observed under the new setting.
    EFFECT_FLOOR = 1.0          # mg/dL/5min mean residual magnitude
    MAX_STEP_RATIO = 1.5        # +50% / −33% cap per single recommendation
    if day_effect < EFFECT_FLOOR or night_effect < EFFECT_FLOOR:
        return []

    raw_ratio = night_effect / day_effect

    # Only recommend split if day/night differ by >30%
    if abs(raw_ratio - 1.0) < 0.30:
        return []

    # Apply per-step clamp on either direction.
    if raw_ratio >= 1.0:
        ratio = min(raw_ratio, MAX_STEP_RATIO)
    else:
        ratio = max(raw_ratio, 1.0 / MAX_STEP_RATIO)
    clamped = abs(ratio - raw_ratio) > 1e-6

    recs = []

    # Night ISF recommendation
    if ratio > 1.0:
        # Night insulin is more effective → increase night ISF
        night_isf = current_isf * ratio
        night_magnitude = (ratio - 1.0) * 100

        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            isf_multiplier=ratio,
            hour_range=(NIGHT_ZONE_START, NIGHT_ZONE_END))
        night_delta = round((tir_sim - tir_now) * 100, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase",
            magnitude_pct=round(night_magnitude, 0),
            current_value=current_isf,
            suggested_value=round(night_isf, 0),
            predicted_tir_delta=night_delta,
            affected_hours=(NIGHT_ZONE_START, NIGHT_ZONE_END),
            confidence=min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS) * (0.6 if clamped else 1.0),
            evidence=(f"Circadian ISF analysis (EXP-2271): night insulin is "
                      f"{ratio:.1f}× more effective than day"
                      + (f" (raw {raw_ratio:.1f}× clamped at {MAX_STEP_RATIO:.1f}×; "
                         f"GAP-ADV-EGP safety cap)" if clamped else "")
                      + ". 2-zone split captures 61-90% of benefit."),
            rationale=(f"Increase ISF from {current_isf:.0f} to {night_isf:.0f} "
                       f"mg/dL/U during nighttime (22:00-07:00). "
                       f"Insulin works more effectively at night due to lower "
                       f"cortisol and growth hormone levels."
                       + (f" NOTE: per-step change capped at +50%; re-evaluate "
                          f"after observing under new setting." if clamped else "")),
        ))
    else:
        # Day insulin is more effective → increase day ISF
        day_ratio = 1.0 / ratio
        day_isf = current_isf * day_ratio
        day_magnitude = (day_ratio - 1.0) * 100

        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            isf_multiplier=day_ratio,
            hour_range=DAY_ZONE)
        day_delta = round((tir_sim - tir_now) * 100, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase",
            magnitude_pct=round(day_magnitude, 0),
            current_value=current_isf,
            suggested_value=round(day_isf, 0),
            predicted_tir_delta=day_delta,
            affected_hours=DAY_ZONE,
            confidence=min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS) * (0.6 if clamped else 1.0),
            evidence=(f"Circadian ISF analysis (EXP-2271): day insulin is "
                      f"{day_ratio:.1f}× more effective than night"
                      + (f" (raw {1.0/raw_ratio:.1f}× clamped at "
                         f"{MAX_STEP_RATIO:.1f}×; GAP-ADV-EGP safety cap)"
                         if clamped else "") + "."),
            rationale=(f"Increase ISF from {current_isf:.0f} to {day_isf:.0f} "
                       f"mg/dL/U during daytime (07:00-22:00)."
                       + (f" NOTE: per-step change capped at +50%; re-evaluate "
                          f"after observing under new setting." if clamped else "")),
        ))

    return recs


# ── Circadian ISF Profiled: 4-Block Correction-Response (EXP-2271) ────

# EXP-2271: ISF varies 4.6-9× by time of day. This advisory uses actual
# correction events grouped into 4 time-of-day blocks to compute empirical
# per-block ISF via the response-curve method (BG drop per unit insulin).
# Complements advise_circadian_isf (2-zone residual-based) by using direct
# correction outcomes rather than metabolic residuals.

_CIRCADIAN_BLOCKS = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}
_CIRCADIAN_ISF_DEVIATION_THRESHOLD = 0.30   # 30% deviation triggers advisory
_CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK = 5    # minimum events per block


def advise_circadian_isf_profiled(
    correction_events: Optional[List[dict]] = None,
    profile: Optional[PatientProfile] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Recommend time-of-day ISF adjustments from correction event outcomes.

    Research: EXP-2271 shows ISF varies 4.6-9× across the day. This function
    uses empirical correction-response data (BG drop per unit insulin) grouped
    into 4 time-of-day blocks to detect blocks where the profile ISF is
    significantly wrong.

    NOTE: The 'drop_4h' measurement is an APPARENT ISF that includes AID
    controller compensation and EGP suppression (EXP-2651: apparent ISF is
    2–10× inflated). Relative block-to-block ratios are more reliable than
    absolute ISF values. Circadian ISF validated: EXP-2652.

    Complements advise_circadian_isf() (2-zone residual method) by using
    direct correction outcomes. The two approaches may produce overlapping
    recommendations; downstream consumers should deduplicate.

    Each correction event dict must contain:
        'hour': fractional hour (0-24) when correction was given
        'drop_4h': BG drop over 4 hours (mg/dL, positive = drop)
        'dose': insulin dose (Units, > 0)

    Args:
        correction_events: list of correction event dicts.
        profile: PatientProfile for current ISF.
        days_of_data: data coverage (minimum 3 days).

    Returns:
        List of SettingsRecommendation for blocks with >30% ISF deviation.
    """
    if days_of_data < MIN_DATA_DAYS:
        return []
    if not correction_events or profile is None:
        return []

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = (float(np.median([float(v) for v in isf_vals]))
                   if isf_vals else 50.0)

    recs: List[SettingsRecommendation] = []

    for block_name, (h_start, h_end) in _CIRCADIAN_BLOCKS.items():
        # Filter events to this block
        block_events = [
            e for e in correction_events
            if 'hour' in e and 'drop_4h' in e and 'dose' in e
            and h_start <= e['hour'] < h_end
            and e['dose'] > 0
        ]

        if len(block_events) < _CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK:
            continue

        # Compute effective ISF per event: BG drop / dose
        effective_isfs = [e['drop_4h'] / e['dose'] for e in block_events]
        block_isf = float(np.median(effective_isfs))

        if block_isf <= 0 or current_isf <= 0:
            continue

        # Deviation from profile ISF
        deviation = (block_isf - current_isf) / current_isf

        if abs(deviation) < _CIRCADIAN_ISF_DEVIATION_THRESHOLD:
            continue

        direction = "increase" if deviation > 0 else "decrease"
        magnitude = abs(deviation) * 100.0
        raw_suggested = round(block_isf, 0)

        # GAP-ADV-EGP fix (EXP-3022b): per-step ISF cap. Apparent ISF
        # measured via drop_4h/dose is inflated 2-10× by AID compensation
        # and EGP suppression (EXP-2651, noted at line 1217 above), so the
        # raw suggestion can imply an unsafe single-cycle move. Cap each
        # block's adjustment at +50% / -33% versus the current profile and
        # mark the recommendation as clamped so downstream consumers see
        # reduced confidence and a clear note.
        MAX_STEP_RATIO = 1.5
        max_up = current_isf * MAX_STEP_RATIO
        max_dn = current_isf / MAX_STEP_RATIO
        suggested = float(min(max(raw_suggested, max_dn), max_up))
        block_clamped = abs(suggested - raw_suggested) > 0.5
        if block_clamped:
            magnitude = abs((suggested - current_isf) / current_isf) * 100.0

        # Confidence: scales with event count, capped by data days.
        # Halve confidence when the safety cap was applied (clamped block).
        n = len(block_events)
        event_factor = min(1.0, n / 20.0)
        day_factor = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS)
        confidence = round(event_factor * day_factor * 0.75
                           * (0.5 if block_clamped else 1.0), 2)

        # Predicted TIR delta: conservative 0.1pp per 10% ISF correction
        predicted_delta = round(magnitude * 0.01, 1)

        clamp_note_ev = (f" Raw drop_4h/dose implied {raw_suggested:.0f}; "
                         f"capped at ±50% step (GAP-ADV-EGP)."
                         if block_clamped else "")
        clamp_note_rt = (" NOTE: per-step change capped at ±50%; "
                         "re-evaluate after observing under new setting."
                         if block_clamped else "")

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_isf,
            suggested_value=suggested,
            predicted_tir_delta=predicted_delta,
            affected_hours=(float(h_start), float(h_end)),
            confidence=confidence,
            evidence=(
                f"Circadian ISF profiling (EXP-2271): {block_name} block "
                f"({h_start:02d}:00-{h_end:02d}:00) effective ISF is "
                f"{block_isf:.0f} mg/dL/U vs profile {current_isf:.0f} "
                f"({deviation:+.0%} deviation) from {n} correction events."
                + clamp_note_ev
            ),
            rationale=(
                f"{direction.capitalize()} ISF from {current_isf:.0f} to "
                f"{suggested:.0f} mg/dL/U during {block_name} "
                f"({h_start:02d}:00-{h_end:02d}:00). ISF varies 4.6-9× "
                f"by time of day (EXP-2271). Observed {n} corrections in "
                f"this block with median effective ISF {block_isf:.0f} "
                f"mg/dL/U. Predicted TIR improvement: "
                f"+{predicted_delta}pp."
                + clamp_note_rt
            ),
        ))

    return recs


# ── Override ISF Advisory (EXP-2621) ─────────────────────────────────

# EXP-2621: 8/12 patients show ISF differs ≥0.15 during override periods.
# Override ISF tends HIGHER than non-override (less insulin effect).
# Productionized as informational advisory: helps users understand how
# their override settings interact with ISF calibration.
_OVERRIDE_ISF_MIN_CORRECTIONS = 5
_OVERRIDE_ISF_MIN_DIFF = 0.15


def advise_override_isf(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    *,
    bolus: np.ndarray,
    carbs: np.ndarray,
    override_active: np.ndarray,
    days_of_data: float,
) -> List[SettingsRecommendation]:
    """Detect ISF split between override and non-override periods.

    EXP-2621 confirmed that 8/12 patients show ISF differs by ≥0.15
    during override-active periods. This advisory informs users that
    their effective ISF may vary with override usage.

    NOTE: Override vs non-override ISF differences reflect combined
    physiology (exercise, stress) and AID controller response. Override-
    specific ISF tuning should be done carefully and conservatively.

    Args:
        glucose: (N,) glucose values.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        bolus: (N,) bolus values.
        carbs: (N,) carb values.
        override_active: (N,) binary override active flag.
        days_of_data: data coverage.

    Returns:
        List of SettingsRecommendation (0 or 1).
    """
    if days_of_data < 7:
        return []

    isf_schedule = profile.isf_mgdl()
    if not isf_schedule:
        return []
    profile_isf = float(np.median([float(e.get('value', e.get('sensitivity', 50)))
                                    for e in isf_schedule]))
    if profile_isf <= 0:
        return []

    n = min(len(glucose), len(bolus), len(carbs), len(override_active))
    glucose = glucose[:n]
    bolus = bolus[:n]
    carbs = carbs[:n]
    override_active = override_active[:n]

    # Find correction boluses (bolus > 0.5, carbs ≤ 1, glucose > 150)
    corr_mask = (
        (bolus > 0.5) &
        (carbs <= 1) &
        (glucose > 150) &
        np.isfinite(glucose)
    )

    def _isf_ratios_for_mask(mask):
        ratios = []
        indices = np.where(mask)[0]
        for idx in indices:
            if idx + 23 >= n:
                continue
            window = glucose[idx:idx + 24]
            if np.sum(np.isnan(window)) > 5:
                continue
            actual_drop = window[0] - window[-1]
            expected_drop = bolus[idx] * profile_isf
            if expected_drop > 0:
                ratio = actual_drop / expected_drop
                if 0.1 < ratio < 5.0:
                    ratios.append(ratio)
        return ratios

    on_mask = corr_mask & (override_active > 0)
    off_mask = corr_mask & (override_active == 0)

    ratios_on = _isf_ratios_for_mask(on_mask)
    ratios_off = _isf_ratios_for_mask(off_mask)

    if (len(ratios_on) < _OVERRIDE_ISF_MIN_CORRECTIONS or
            len(ratios_off) < _OVERRIDE_ISF_MIN_CORRECTIONS):
        return []

    median_on = float(np.median(ratios_on))
    median_off = float(np.median(ratios_off))
    diff = abs(median_on - median_off)

    if diff < _OVERRIDE_ISF_MIN_DIFF:
        return []

    pct_override = float(np.mean(override_active > 0)) * 100
    direction = "increase" if median_on > median_off else "decrease"
    magnitude = round(diff / median_off * 100, 0)

    confidence = min(0.9, 0.4 + 0.05 * min(len(ratios_on), 20))

    return [SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction=direction,
        magnitude_pct=magnitude,
        current_value=profile_isf,
        suggested_value=round(profile_isf * median_on, 1),
        predicted_tir_delta=round(min(PER_ADVISOR_TIR_DELTA_CAP_PP, magnitude * 0.03), 1),
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(f"Override ISF analysis (EXP-2621): ISF ratio during overrides "
                  f"= {median_on:.2f} vs {median_off:.2f} without overrides "
                  f"(n={len(ratios_on)}/{len(ratios_off)}, Δ={diff:.2f}). "
                  f"Overrides active {pct_override:.0f}% of time."),
        rationale=(f"Your insulin sensitivity differs by {diff:.2f} ({magnitude:.0f}%) "
                   f"during override periods. Consider whether your override settings "
                   f"need adjustment to match this observed ISF difference."),
    )]


# ── Patience Mode Advisory (EXP-2660/2662) ────────────────────────────


def advise_patience_mode(
    saturation: 'SaturationAssessment',
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """Recommend patience mode when insulin saturation is detected (EXP-2662).

    When the SC suppression ceiling is reached (~30% of hepatic EGP,
    EXP-2656), additional SMBs have negligible glucose-lowering effect
    but increase delayed hypo risk. Patience mode caps IOB at 1.5×median
    during wall episodes.

    Research findings (EXP-2662):
    - Saves 34–82% of SMBs during wall episodes
    - Max hyper increase: +2.1 pp (acceptable trade-off)
    - Delayed hypo reduction: 0.1–2.0 pp
    - 61–84% of sticky hypers show wall detection (EXP-2660)

    Args:
        saturation: SaturationAssessment from detect_insulin_saturation().
        days_of_data: data coverage for confidence scaling.

    Returns:
        SettingsRecommendation for patience mode, or None if not eligible.
    """
    if saturation is None or not saturation.patience_mode_eligible:
        return None

    if days_of_data < 3.0:
        return None

    confidence = min(0.7, days_of_data / 14.0)

    # Scale predicted benefit by severity
    if saturation.level.value == 'severe':
        predicted_smb_savings = '60–82%'
        predicted_delta = 1.5
    elif saturation.level.value == 'moderate':
        predicted_smb_savings = '40–60%'
        predicted_delta = 1.0
    else:
        predicted_smb_savings = '34–40%'
        predicted_delta = 0.5

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,  # closest parameter (affects dosing)
        direction="informational",
        magnitude_pct=0.0,
        current_value=saturation.median_iob,
        suggested_value=saturation.iob_cap_suggestion,
        predicted_tir_delta=round(predicted_delta, 1),
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(f"Insulin saturation detected: {saturation.wall_pct:.0f}% of "
                  f"high-glucose time at wall ({saturation.n_wall_episodes} "
                  f"episodes of {saturation.n_high_glucose_episodes} total). "
                  f"Excess insulin: ~{saturation.excess_insulin_u:.1f}U wasted. "
                  f"SC suppression ceiling reached (EXP-2656/2660)."),
        rationale=(f"PATIENCE MODE (EXP-2662): Cap IOB at "
                   f"{saturation.iob_cap_suggestion:.1f}U "
                   f"(1.5× median IOB of {saturation.median_iob:.1f}U) during "
                   f"wall episodes. Saves {predicted_smb_savings} of SMBs with "
                   f"≤+2.1pp hyper increase. Additional insulin at the SC "
                   f"suppression ceiling has negligible glucose-lowering effect "
                   f"but increases delayed hypo risk."),
    )


# ── Dual-Phase ISF Advisory (EXP-2651) ───────────────────────────────


def advise_isf_dual_phase(
    dual_phase: 'DualPhaseISF',
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """Generate INFORMATIONAL dual-phase ISF report (EXP-2651).

    Reports both demand-phase ISF (0–2h, true insulin effect) and apparent
    ISF (full correction drop, includes AID + EGP). Always informational —
    advise_isf() is the sole actionable ISF recommendation path.

    This separation avoids duplicate/conflicting ISF recommendations:
    advise_isf() emits the actionable step, this function provides the
    detailed analysis context (inflation ratio, severity, CI bounds).

    Args:
        dual_phase: DualPhaseISF from compute_demand_isf().
        days_of_data: data coverage for confidence scaling.

    Returns:
        SettingsRecommendation, or None.
    """
    if dual_phase is None or dual_phase.n_corrections < 5:
        return None

    confidence = min(0.7, days_of_data / 14.0)

    inflation_severity = (
        "extreme" if dual_phase.inflation_ratio > 5.0
        else "high" if dual_phase.inflation_ratio > 3.0
        else "moderate" if dual_phase.inflation_ratio > 2.0
        else "normal"
    )

    # Dual-phase report is INFORMATIONAL only — advise_isf() is the sole
    # actionable ISF recommendation path (avoids duplicate/conflicting recs).
    sched = dual_phase.scheduled_isf or 50.0
    demand = dual_phase.demand_isf
    gap = demand - sched
    gap_pct = abs(gap / sched) * 100 if sched > 0 else 0

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="informational",
        magnitude_pct=0.0,
        current_value=sched,
        suggested_value=sched,
        predicted_tir_delta=0.0,
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(f"Dual-phase ISF analysis (N={dual_phase.n_corrections}): "
                  f"Demand ISF (0–2h) = {dual_phase.demand_isf:.0f} mg/dL/U, "
                  f"Apparent ISF (full) = {dual_phase.apparent_isf:.0f} mg/dL/U, "
                  f"Inflation ratio = {dual_phase.inflation_ratio:.1f}× "
                  f"({inflation_severity}). "
                  f"Scheduled ISF = {sched:.0f} mg/dL/U."),
        rationale=(f"Demand-phase ISF ({dual_phase.demand_isf:.0f}) measures "
                   f"true insulin effect (0–2h, before EGP suppression). "
                   f"Apparent ISF ({dual_phase.apparent_isf:.0f}) is inflated "
                   f"{dual_phase.inflation_ratio:.1f}× by AID compensation and "
                   f"EGP suppression (EXP-2651). "
                   f"CI [{dual_phase.demand_ci_low:.0f}–{dual_phase.demand_ci_high:.0f}]. "
                   f"Multi-factor ISF estimation validated: dose-dependent "
                   f"r=-0.56 (EXP-2640), response-curve R²=0.805 (EXP-1301)."),
    )


# ── Response-Curve ISF Advisory (EXP-1301) ───────────────────────────

def advise_response_curve_isf(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    basal_rate: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
    inferred_meal_indices: Optional[np.ndarray] = None,
) -> Optional[SettingsRecommendation]:
    """Report ISF from exponential response-curve fitting (EXP-1301).

    Fits BG(t) = BG_start - amplitude * (1 - exp(-t/tau)) to each correction
    event and computes ISF = amplitude / dose. R2 = 0.805 population average.

    Also classifies responder type via tau:
    - Fast responders: tau ~ 1.5h (rapid insulin action)
    - Slow responders: tau ~ 4.0h (delayed insulin action)

    NOTE: Returns APPARENT ISF (includes AID compensation + EGP suppression).
    Use demand-phase ISF (advise_isf_dual_phase) for true insulin sensitivity.
    This advisory is informational -- complements demand ISF with tau classification.
    """
    if bolus is None or days_of_data < 7.0:
        return None

    try:
        from ..clinical_rules import compute_response_curve_isf
        result = compute_response_curve_isf(
            glucose, bolus, basal_rate, profile,
            inferred_meal_indices=inferred_meal_indices,
        )
    except Exception:
        return None

    if not result or result.get('n_corrections', 0) < 3:
        return None

    isf = result.get('isf', 0)
    tau = result.get('tau_hours', 2.0)
    r2 = result.get('r2', 0)
    n_corr = result.get('n_corrections', 0)
    dampening = result.get('aid_dampening_pct', 0)

    if isf <= 0:
        return None

    responder_type = "fast" if tau < 2.5 else "slow"

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_schedule]
    sched_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    ratio = isf / sched_isf if sched_isf > 0 else 1.0

    confidence = min(0.6, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, r2 / 0.5)

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="informational",
        magnitude_pct=0.0,
        current_value=sched_isf,
        suggested_value=sched_isf,
        predicted_tir_delta=0.0,
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(f"Response-curve ISF (EXP-1301): {n_corr} corrections, "
                  f"ISF={isf:.0f} mg/dL/U, tau={tau:.1f}h ({responder_type} "
                  f"responder), R2={r2:.2f}. AID dampening: {dampening:.0f}%. "
                  f"Profile ISF={sched_isf:.0f}, ratio={ratio:.2f}x."),
        rationale=(f"Response-curve fitting yields apparent ISF of "
                   f"{isf:.0f} mg/dL/U (tau={tau:.1f}h, {responder_type} "
                   f"responder). This is {ratio:.1f}x the profile ISF "
                   f"({sched_isf:.0f}). NOTE: Apparent ISF includes AID "
                   f"compensation (EXP-2651: 2-10x inflation). Use "
                   f"demand-phase ISF for dosing targets."),
    )


# ── SC Suppression Ceiling Advisory (EXP-2656/2667) ──────────────────

def advise_sc_ceiling(
    glucose: np.ndarray,
    iob: np.ndarray,
    profile: PatientProfile,
    days_of_data: float,
    saturation: Optional['SaturationAssessment'] = None,
) -> Optional[SettingsRecommendation]:
    """Report per-patient SC insulin suppression ceiling (EXP-2656/2667).

    SC insulin can suppress at most ~20% (median) of hepatic EGP. At this
    ceiling, additional insulin has diminishing glucose-lowering returns,
    explaining sticky hypers and delayed hypos from IOB stacking.

    Research findings:
    - Population median ceiling: 20% (demand-ISF basis, EXP-2667)
    - Range: 10-56% across patients
    - Ceiling correlates with sticky hyper rate (r=-0.60)
    - Ceiling model improves RMSE 2-22% over linear at high IOB
    """
    if iob is None or days_of_data < 7.0:
        return None

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_schedule]
    sched_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    try:
        from ..clinical_rules import compute_sc_ceiling
        ceiling = compute_sc_ceiling(glucose, iob,
                                     scheduled_isf=sched_isf,
                                     dia_hours=profile.dia_hours or 6.0)
    except Exception:
        return None

    if ceiling is None:
        return None

    fitted = ceiling['fitted_ceiling']
    improvement = ceiling['improvement_pct']
    n_pts = ceiling['n_high_iob_points']

    if improvement < 1.0:
        return None

    confidence = min(0.5, days_of_data / HIGH_CONFIDENCE_DAYS)

    wall_note = ""
    if saturation is not None and saturation.patience_mode_eligible:
        wall_note = (f" Wall episodes: {saturation.wall_pct:.0f}% of high-BG "
                     f"time. Patience mode eligible (IOB cap: "
                     f"{saturation.iob_cap_suggestion:.1f}U).")

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="informational",
        magnitude_pct=0.0,
        current_value=sched_isf,
        suggested_value=sched_isf,
        predicted_tir_delta=0.0,
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(f"SC ceiling analysis (EXP-2656/2667): fitted ceiling "
                  f"= {fitted:.0%} EGP suppression, "
                  f"RMSE improvement = {improvement:.1f}% over linear, "
                  f"N = {n_pts} high-IOB points.{wall_note}"),
        rationale=(f"SC insulin can suppress at most {fitted:.0%} of "
                   f"hepatic glucose production for this patient. At high "
                   f"IOB (>{ceiling['median_iob']:.1f}U), additional insulin "
                   f"has diminishing returns -- {1 - fitted:.0%} of EGP "
                   f"remains active regardless. This explains sticky "
                   f"hypers and delayed hypo risk from IOB stacking."),
    )


# ── Dose-Response ISF Advisory (EXP-2636/2640) ──────────────────────

def advise_dose_response_isf(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
    inferred_meal_indices: Optional[np.ndarray] = None,
) -> Optional[SettingsRecommendation]:
    """Report dose-dependent ISF curve and split-dose recommendation (EXP-2640).

    ISF compresses logarithmically with dose: ISF ~ a + b * ln(dose).
    Large corrections (>=3U) yield 4.6x lower apparent ISF than small (<0.75U)
    due to AID basal withdrawal, glucose drop ceiling, and EGP saturation.

    Clinical implication: Large corrections are less efficient per-unit.
    Splitting a 4U correction into 2x2U may be more effective.

    Research findings:
    - Population r = -0.56, p < 10^-19
    - Log model wins 5/6 patients
    - Bootstrap CI [-0.67, -0.44]
    - Cross-patient CV = 8-9% at matched doses
    """
    if bolus is None or days_of_data < 7.0:
        return None

    try:
        from ..clinical_rules import compute_dose_response_isf
        result = compute_dose_response_isf(
            glucose, bolus, carbs, profile,
            inferred_meal_indices=inferred_meal_indices,
        )
    except Exception:
        return None

    if result is None:
        return None

    best_model = result['best_model']
    best_r = result['best_r']
    n_events = result['n_events']
    log_fit = result.get('log', {})
    dose_range = result.get('dose_range', [0, 0])
    isf_at_dose = result.get('isf_at_dose', {})

    if best_r < 0.25:
        return None

    sched_isf = result.get('scheduled_isf', 50.0)
    confidence = min(0.5, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, best_r / 0.5)

    dose_summary = ", ".join(
        f"{d}U->{isf:.0f}" for d, isf in isf_at_dose.items()
    )

    split_note = ""
    if '1.0' in isf_at_dose and '3.0' in isf_at_dose:
        ratio = isf_at_dose['1.0'] / isf_at_dose['3.0'] if isf_at_dose['3.0'] > 0 else 1
        if ratio > 1.5:
            split_note = (f" Split-dose recommendation: corrections >=3U are "
                          f"{ratio:.1f}x less efficient per-unit than 1U. "
                          f"Consider splitting large corrections.")

    direction = "informational"
    magnitude = 0.0
    suggested = sched_isf
    tir_delta = 0.0

    median_isf = result.get('median_apparent_isf', sched_isf)
    profile_ratio = result.get('profile_ratio', 1.0)
    if abs(profile_ratio - 1.0) > 0.3 and best_r > 0.35:
        if profile_ratio > 1.3:
            direction = "increase"
        elif profile_ratio < 0.7:
            direction = "decrease"
        magnitude = abs(profile_ratio - 1.0) * 100
        suggested = round(median_isf, 0)
        tir_delta = round(magnitude * 0.03, 1)

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction=direction,
        magnitude_pct=round(magnitude, 0),
        current_value=sched_isf,
        suggested_value=suggested,
        predicted_tir_delta=tir_delta,
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(f"Dose-response ISF (EXP-2640): {n_events} corrections, "
                  f"best model={best_model} (|r|={best_r:.2f}), "
                  f"dose range [{dose_range[0]:.1f}-{dose_range[1]:.1f}U]. "
                  f"ISF at dose: {dose_summary}.{split_note}"),
        rationale=(f"ISF varies with correction dose ({best_model} model, "
                   f"|r|={best_r:.2f}). Larger corrections yield lower "
                   f"apparent ISF due to AID basal withdrawal, glucose drop "
                   f"ceiling, and EGP saturation (EXP-2636). "
                   f"Log model: ISF ~ {log_fit.get('intercept', 50):.0f} "
                   f"+ ({log_fit.get('slope', -28):.0f}) * ln(dose)."),
    )
