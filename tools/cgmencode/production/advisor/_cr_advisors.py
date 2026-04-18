"""Carb ratio advisory functions — primary CR, effective CR, adequacy, context-aware."""

from __future__ import annotations
from typing import List, Optional
import numpy as np
from ..types import (
    ClinicalReport, MetabolicState, PatientProfile,
    SettingsParameter, SettingsRecommendation, PeriodMetrics,
)
from ._simulation import simulate_tir_with_settings, MIN_DATA_DAYS, HIGH_CONFIDENCE_DAYS, PERIODS


__all__ = [
    '_CR_ADEQUACY_DEVIATION_THRESHOLD',
    '_CR_ADEQUACY_MIN_MEALS',
    '_CR_EVENING_DAMPEN',
    '_CR_IOB_COEFF',
    '_CR_MORNING_BOOST',
    '_CR_NONLINEARITY_THRESHOLD',
    '_CR_PRE_BG_COEFF',
    '_MEAL_MAX_EXTRA_CARBS',
    '_MEAL_MIN_BOLUS',
    '_MEAL_MIN_CARBS',
    '_MEAL_POST_WINDOW',
    '_MIN_MEAL_EVENTS',
    '_extract_meal_response_windows',
    'advise_context_cr',
    'advise_cr',
    'advise_cr_adequacy',
    'advise_effective_cr',
    'compute_context_cr_adjustment',
]


def advise_cr(glucose: np.ndarray,
              metabolic: MetabolicState,
              hours: np.ndarray,
              clinical: ClinicalReport,
              profile: PatientProfile,
              days_of_data: float) -> Optional[SettingsRecommendation]:
    """Generate CR recommendation with predicted TIR impact.

    Uses CR effectiveness score and post-meal excursion analysis.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    if clinical.cr_score >= 40:  # Acceptable CR
        return None

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    # Low CR score = post-meal spikes too high → decrease CR (more insulin per carb)
    direction = "decrease"

    best_delta = 0.0
    best_mult = 1.0
    for pct in [0.10, 0.15, 0.20]:
        mult = 1.0 - pct  # Lower CR = more aggressive dosing
        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            cr_multiplier=mult, hour_range=(5.0, 21.0))  # Meal hours
        delta = tir_sim - tir_now
        if delta > best_delta:
            best_delta = delta
            best_mult = mult

    magnitude = (1.0 - best_mult) * 100
    if magnitude < 1.0:  # No meaningful change found
        return None
    suggested = current_cr * best_mult
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * 0.7

    return SettingsRecommendation(
        parameter=SettingsParameter.CR,
        direction=direction,
        magnitude_pct=magnitude,
        current_value=current_cr,
        suggested_value=round(suggested, 1),
        predicted_tir_delta=round(best_delta * 100, 1),
        affected_hours=(5.0, 21.0),
        confidence=confidence,
        evidence=(f"CR effectiveness score is {clinical.cr_score:.0f}/100 (poor). "
                  f"Post-meal excursions indicate under-dosing."),
        rationale=(f"Decrease carb ratio by {magnitude:.0f}% "
                   f"(from {current_cr:.1f} to {suggested:.1f} g/U). "
                   f"Should reduce post-meal excursions. "
                   f"Predicted TIR improvement: {best_delta*100:+.1f}pp. "
                   f"Confirmable within 2 weeks."),
    )


# ── Effective CR from Meal Response (EXP-2609/2610) ──────────────────

_MEAL_MIN_CARBS = 10.0      # grams — minimum meal size
_MEAL_MIN_BOLUS = 0.5       # units — minimum bolus with meal
_MEAL_POST_WINDOW = 36      # 3 hours at 5-min intervals
_MEAL_MAX_EXTRA_CARBS = 5.0 # max additional carbs in window
_MIN_MEAL_EVENTS = 10       # minimum meals for reliable CR


def _extract_meal_response_windows(
    glucose: np.ndarray,
    hours: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    profile: PatientProfile,
    max_windows: int = 100,
) -> list:
    """Extract clean meal events with 3h glucose follow-up.

    Returns list of dicts with: carbs, bolus, hour, pre_glucose,
    peak_rise, post_tir, profile_isf, profile_cr, effective_cr.
    """
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    median_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    median_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    N = len(glucose)
    windows = []
    for i in range(N - _MEAL_POST_WINDOW):
        if carbs[i] < _MEAL_MIN_CARBS or bolus[i] < _MEAL_MIN_BOLUS:
            continue
        if np.isnan(glucose[i]):
            continue

        post = glucose[i:i + _MEAL_POST_WINDOW]
        valid = ~np.isnan(post)
        if np.sum(valid) < _MEAL_POST_WINDOW * 0.5:
            continue

        # Skip contaminated windows
        extra = np.nansum(carbs[i + 1:i + _MEAL_POST_WINDOW])
        if extra > _MEAL_MAX_EXTRA_CARBS:
            continue

        pre_g = float(glucose[i])
        peak_rise = float(np.nanmax(post) - pre_g)
        post_valid = post[valid]
        post_tir = float(np.mean((post_valid >= 70) & (post_valid <= 180)))

        # Effective CR: carbs / (glucose_from_carbs / ISF)
        # glucose_from_carbs = peak_rise + bolus_effect (what rise would be without insulin)
        glucose_from_carbs = peak_rise + float(bolus[i]) * median_isf
        if glucose_from_carbs > 0 and median_isf > 0:
            effective_insulin = glucose_from_carbs / median_isf
            effective_cr = float(carbs[i]) / effective_insulin if effective_insulin > 0 else None
        else:
            effective_cr = None

        if effective_cr is not None and 0.5 < effective_cr < 100:
            windows.append({
                "carbs": float(carbs[i]),
                "bolus": float(bolus[i]),
                "hour": float(hours[i]) if hours is not None else 12.0,
                "pre_glucose": pre_g,
                "peak_rise": peak_rise,
                "post_tir": post_tir,
                "profile_cr": median_cr,
                "effective_cr": effective_cr,
                "cr_ratio": effective_cr / median_cr,
            })

        if len(windows) >= max_windows:
            break

    return windows


def advise_effective_cr(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Generate CR recommendations from actual meal-bolus glucose response.

    Research basis:
      - EXP-2609: Effective CR differs from profile for 5/9 patients
      - EXP-2609 H2: Dawn CR is tighter (lower) for 6/9 patients
      - EXP-2609 H3: Correct-bolused meals have +7.8pp TIR vs under-bolused
      - EXP-2610: Sim CR (always 0.5×) is calibration artifact, not clinical

    Computes effective CR from meal response analysis: how many grams of
    carbs does each unit of insulin actually cover, based on post-meal
    glucose trajectory.

    Args:
        glucose: (N,) cleaned glucose at 5-min intervals.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        bolus: (N,) bolus insulin per step.
        carbs: (N,) carb intake per step.
        days_of_data: data coverage in days.

    Returns:
        List of SettingsRecommendation (0-1 items for CR adjustment).
    """
    if bolus is None or carbs is None:
        return []
    if days_of_data < MIN_DATA_DAYS:
        return []

    windows = _extract_meal_response_windows(
        glucose, hours, bolus, carbs, profile
    )
    if len(windows) < _MIN_MEAL_EVENTS:
        return []

    # Compute median effective CR
    effective_crs = [w["effective_cr"] for w in windows]
    cr_ratios = [w["cr_ratio"] for w in windows]
    median_eff_cr = float(np.median(effective_crs))
    median_ratio = float(np.median(cr_ratios))

    # Need at least 20% difference to recommend (conservative threshold)
    # Note: the effective CR calculation depends on profile ISF, which may
    # be miscalibrated. Using 20% avoids false recommendations.
    if abs(median_ratio - 1.0) < 0.20:
        return []

    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    direction = "increase" if median_ratio > 1.0 else "decrease"
    magnitude = abs(median_ratio - 1.0) * 100
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, len(windows) / 30)
    tir_delta = magnitude * 0.05

    return [SettingsRecommendation(
        parameter=SettingsParameter.CR,
        direction=direction,
        magnitude_pct=round(magnitude, 0),
        current_value=current_cr,
        suggested_value=round(median_eff_cr, 1),
        predicted_tir_delta=round(tir_delta, 1),
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(
            f"Effective CR from meal response (EXP-2609): median effective "
            f"CR={median_eff_cr:.1f} g/U from {len(windows)} meal events "
            f"(profile CR={current_cr:.1f}). Ratio={median_ratio:.2f}×."
        ),
        rationale=(
            f"{direction.capitalize()} CR by {magnitude:.0f}% "
            f"(from {current_cr:.0f} to {median_eff_cr:.0f} g/U). "
            f"Analysis of {len(windows)} meal-bolus events shows actual "
            f"carb coverage is {median_ratio:.0%} of the current profile CR. "
            f"Meals are systematically "
            f"{'over' if median_ratio > 1.0 else 'under'}-bolused."
        ),
    )]


# ── CR Adequacy Analysis (EXP-2535/2536) ──────────────────────────────

# EXP-2535: Effective CR = 1.47× profile CR (systematic under-dosing).
# CR nonlinearity: BG rise/gram decreases with meal size (5.50→0.59).
# Post-meal TIR drops ~11pp. 4h mean delta = +1.8 mg/dL.
# EXP-2536: CR and ISF vary independently (r=0.17). Patients under-bolused
# at all time blocks. Breakfast CR is tightest (already compensated).

_CR_ADEQUACY_MIN_MEALS = 10       # minimum meals for analysis
_CR_ADEQUACY_DEVIATION_THRESHOLD = 0.20  # 20% deviation triggers recommendation
_CR_NONLINEARITY_THRESHOLD = 2.0  # BG rise ratio between small and large meals


def advise_cr_adequacy(
    meal_events: List[dict],
    profile: PatientProfile,
) -> List[SettingsRecommendation]:
    """Analyse CR adequacy from meal-level bolus and outcome data (EXP-2535/2536).

    Complements advise_cr() (simulation-based) by using actual meal events to
    detect systematic under/over-dosing and meal-size nonlinearity.

    EXP-2535 found effective CR = 1.47× profile CR across the population,
    indicating widespread under-dosing. EXP-2536 confirmed CR and ISF vary
    independently (r=0.17) and that patients under-bolus at all time blocks.

    Each meal_event dict must contain:
        'carbs': grams of carbs (> 0)
        'bolus': insulin dose (Units, > 0)
        'pre_meal_bg': glucose before meal (mg/dL)
        'post_meal_bg_4h': glucose 4h after meal (mg/dL)
        'hour': fractional hour of day (0-24)

    Args:
        meal_events: list of meal event dicts.
        profile: PatientProfile with current CR schedule.

    Returns:
        List of SettingsRecommendation (0-2: adequacy rec + nonlinearity warning).
    """
    if not meal_events or len(meal_events) < _CR_ADEQUACY_MIN_MEALS:
        return []

    # Filter to valid events
    valid = [
        e for e in meal_events
        if all(k in e for k in ('carbs', 'bolus', 'pre_meal_bg',
                                'post_meal_bg_4h', 'hour'))
        and e['carbs'] > 0 and e['bolus'] > 0
    ]

    if len(valid) < _CR_ADEQUACY_MIN_MEALS:
        return []

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    profile_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    # Compute effective CR per event: carbs / bolus
    effective_crs = np.array([e['carbs'] / e['bolus'] for e in valid])
    mean_effective_cr = float(np.mean(effective_crs))

    recs: List[SettingsRecommendation] = []

    # ── Systematic deviation check ────────────────────────────────
    if profile_cr > 0:
        deviation = (mean_effective_cr - profile_cr) / profile_cr
    else:
        deviation = 0.0

    if abs(deviation) >= _CR_ADEQUACY_DEVIATION_THRESHOLD:
        # Determine direction of dosing error
        if deviation > 0:
            # Effective CR > profile CR → patients use more carbs per unit
            # → they are under-dosing (giving less insulin than profile says)
            direction = "decrease"
            dosing_pattern = "under-dosing"
        else:
            direction = "increase"
            dosing_pattern = "over-dosing"

        magnitude_pct = abs(deviation) * 100.0

        # Confidence scales with meal count
        n = len(valid)
        confidence = min(0.85, 0.3 + 0.55 * min(1.0, n / 50.0))

        # Predicted TIR delta: ~11pp post-meal TIR drop is recoverable
        # proportionally to how much of the deviation we correct
        predicted_delta = round(min(5.0, magnitude_pct * 0.1), 1)

        # Compute 4h BG deltas for evidence
        deltas = [e['post_meal_bg_4h'] - e['pre_meal_bg'] for e in valid]
        mean_delta = float(np.mean(deltas))

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.CR,
            direction=direction,
            magnitude_pct=round(magnitude_pct, 0),
            current_value=profile_cr,
            suggested_value=round(mean_effective_cr, 1),
            predicted_tir_delta=predicted_delta,
            affected_hours=(5.0, 21.0),
            confidence=confidence,
            evidence=(
                f"CR adequacy analysis (EXP-2535): effective CR is "
                f"{mean_effective_cr:.1f} g/U vs profile {profile_cr:.1f} g/U "
                f"({deviation:+.0%} deviation) from {n} meals. "
                f"Mean 4h BG delta: {mean_delta:+.1f} mg/dL. "
                f"Systematic {dosing_pattern} detected."
            ),
            rationale=(
                f"{direction.capitalize()} CR from {profile_cr:.1f} to "
                f"{mean_effective_cr:.1f} g/U to match observed dosing. "
                f"EXP-2535 found effective CR = 1.47× profile CR population-"
                f"wide. This patient shows {deviation:+.0%} deviation "
                f"({dosing_pattern}). Predicted TIR improvement: "
                f"+{predicted_delta}pp."
            ),
        ))

    # ── Meal-size nonlinearity check ──────────────────────────────
    # Split meals into small (<30g) and large (>60g) categories
    small_meals = [e for e in valid if e['carbs'] <= 30]
    large_meals = [e for e in valid if e['carbs'] >= 60]

    if len(small_meals) >= 5 and len(large_meals) >= 5:
        small_rise = float(np.mean([
            (e['post_meal_bg_4h'] - e['pre_meal_bg']) / e['carbs']
            for e in small_meals
        ]))
        large_rise = float(np.mean([
            (e['post_meal_bg_4h'] - e['pre_meal_bg']) / e['carbs']
            for e in large_meals
        ]))

        # Only check ratio when small meals actually show a positive rise
        if small_rise > 0 and large_rise >= 0:
            nonlinearity_ratio = small_rise / max(large_rise, 0.01)

            if nonlinearity_ratio >= _CR_NONLINEARITY_THRESHOLD:
                n_small = len(small_meals)
                n_large = len(large_meals)
                confidence = min(0.70, 0.2 + 0.5 * min(
                    1.0, (n_small + n_large) / 40.0))

                recs.append(SettingsRecommendation(
                    parameter=SettingsParameter.CR,
                    direction="decrease",
                    magnitude_pct=0.0,
                    current_value=profile_cr,
                    suggested_value=profile_cr,
                    predicted_tir_delta=round(min(3.0, nonlinearity_ratio * 0.5), 1),
                    affected_hours=(5.0, 21.0),
                    confidence=confidence,
                    evidence=(
                        f"CR nonlinearity (EXP-2535): BG rise/gram is "
                        f"{small_rise:.2f} mg/dL/g for small meals (≤30g, "
                        f"n={n_small}) vs {large_rise:.2f} mg/dL/g for large "
                        f"meals (≥60g, n={n_large}). Ratio: "
                        f"{nonlinearity_ratio:.1f}×."
                    ),
                    rationale=(
                        f"Meal-size nonlinearity detected: small meals produce "
                        f"{nonlinearity_ratio:.1f}× more BG rise per gram than "
                        f"large meals. A fixed CR under-doses small meals and "
                        f"may over-dose large meals. Consider meal-size-aware "
                        f"dosing or pre-bolus timing adjustments for small meals."
                    ),
                ))

    return recs


# ── Context-Aware CR (EXP-2341) ──────────────────────────────────────

# EXP-2341: Carbs explain <16% of glucose rise. Pre-meal BG is NEGATIVELY
# correlated with rise (r=-0.33 to -0.69). Multi-factor model R²=0.14-0.54
# (avg +0.277 over carbs-only).
#
# Factors: pre-meal BG, time of day, IOB at meal time
# Pre-meal BG effect: higher starting BG → smaller rise (regression to mean
# + stronger insulin response at higher BG levels)

# Coefficients from EXP-2341 population model
_CR_PRE_BG_COEFF = -0.15     # mg/dL rise per mg/dL pre-BG above 120
_CR_IOB_COEFF = -5.0          # mg/dL rise per Unit IOB at meal time
_CR_MORNING_BOOST = 1.20      # 20% more insulin needed at breakfast
_CR_EVENING_DAMPEN = 0.90     # 10% less insulin needed at dinner


def compute_context_cr_adjustment(pre_meal_bg: float,
                                  iob_at_meal: float,
                                  hour: float,
                                  base_cr: float,
                                  ) -> dict:
    """Compute context-aware CR adjustment for a specific meal context.

    Research (EXP-2341): Pre-meal BG is negatively correlated with
    post-meal rise. Higher starting BG means the same carbs produce
    a SMALLER glucose excursion. IOB at meal time also reduces rise.

    This function adjusts the base CR for the current context:
    - High pre-meal BG → less insulin needed (larger CR)
    - High IOB → less insulin needed (larger CR)
    - Morning → more insulin needed (smaller CR)

    Args:
        pre_meal_bg: current glucose before meal (mg/dL).
        iob_at_meal: current IOB (Units).
        hour: fractional hour of day.
        base_cr: base carb ratio from profile (g/U).

    Returns:
        Dict with 'adjusted_cr', 'adjustment_pct', 'factors' explaining
        each component of the adjustment.
    """
    factors = {}
    total_multiplier = 1.0

    # Pre-meal BG adjustment: higher BG → less insulin
    bg_delta = pre_meal_bg - 120.0
    if abs(bg_delta) > 10:
        bg_effect = _CR_PRE_BG_COEFF * bg_delta / 50.0  # normalized
        bg_mult = 1.0 - bg_effect
        bg_mult = max(0.7, min(1.3, bg_mult))
        total_multiplier *= bg_mult
        factors['pre_meal_bg'] = {
            'value': pre_meal_bg,
            'effect': f"{'less' if bg_mult > 1 else 'more'} insulin needed",
            'multiplier': round(bg_mult, 2),
        }

    # IOB adjustment: high IOB → less insulin needed
    if iob_at_meal > 0.5:
        iob_mult = max(0.7, 1.0 + iob_at_meal * 0.05)
        total_multiplier *= iob_mult
        factors['iob'] = {
            'value': iob_at_meal,
            'effect': f"{'less' if iob_mult > 1 else 'more'} insulin needed",
            'multiplier': round(iob_mult, 2),
        }

    # Time-of-day adjustment: morning more aggressive, evening less
    if 5.0 <= hour < 10.0:
        tod_mult = 1.0 / _CR_MORNING_BOOST  # smaller CR = more insulin
        total_multiplier *= tod_mult
        factors['time_of_day'] = {
            'period': 'morning',
            'effect': 'dawn phenomenon — more insulin needed',
            'multiplier': round(tod_mult, 2),
        }
    elif 17.0 <= hour < 21.0:
        tod_mult = 1.0 / _CR_EVENING_DAMPEN  # larger CR = less insulin
        total_multiplier *= tod_mult
        factors['time_of_day'] = {
            'period': 'evening',
            'effect': 'better insulin sensitivity — less insulin needed',
            'multiplier': round(tod_mult, 2),
        }

    adjusted_cr = base_cr * total_multiplier
    adjustment_pct = (total_multiplier - 1.0) * 100

    return {
        'adjusted_cr': round(adjusted_cr, 1),
        'base_cr': base_cr,
        'adjustment_pct': round(adjustment_pct, 1),
        'total_multiplier': round(total_multiplier, 2),
        'factors': factors,
        'interpretation': (
            f"Context-adjusted CR: {adjusted_cr:.1f} g/U "
            f"(base {base_cr:.1f}, {adjustment_pct:+.0f}%). "
            f"Pre-BG {pre_meal_bg:.0f}, IOB {iob_at_meal:.1f}U, "
            f"hour {hour:.0f}."
        ),
    }


def advise_context_cr(glucose: np.ndarray,
                      metabolic: Optional[MetabolicState],
                      hours: np.ndarray,
                      profile: PatientProfile,
                      carbs: Optional[np.ndarray] = None,
                      days_of_data: float = 0.0,
                      ) -> List[SettingsRecommendation]:
    """Recommend time-of-day CR adjustments based on context analysis.

    Research (EXP-2341): Multi-factor CR model improves R² by +0.28
    vs carbs-only. Key finding: 47-80% of meals are under-bolused
    for 8/11 patients. Morning meals need ~20% more insulin.

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState for meal response analysis.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        carbs: (N,) optional carb data for meal detection.
        days_of_data: minimum 7 days required.

    Returns:
        List of CR SettingsRecommendations by time period.
    """
    if days_of_data < 7.0 or carbs is None:
        return []

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    c = np.nan_to_num(carbs.astype(np.float64), nan=0.0)

    recs = []

    # Analyze meal response by time of day
    for name, h_start, h_end in PERIODS:
        if name == "fasting":
            continue  # No meals during fasting

        mask = (hours >= h_start) & (hours < h_end)
        # Find meals in this period: carbs > 5g
        meal_indices = np.where(mask & (c > 5))[0]
        if len(meal_indices) < 5:
            continue

        # Compute post-meal excursions (2h window)
        excursions = []
        for idx in meal_indices:
            if idx + 24 >= len(bg):
                continue
            pre_bg = float(bg[idx])
            post_window = bg[idx:idx+24]
            peak = float(np.max(post_window))
            excursion = peak - pre_bg
            excursions.append(excursion)

        if not excursions:
            continue

        mean_excursion = float(np.mean(excursions))
        # Excessive excursion: >60 mg/dL mean suggests under-bolusing
        if mean_excursion < 40:
            continue

        # Recommend CR decrease (more aggressive) for this period
        # Scale by excursion severity
        cr_reduction = min(0.25, (mean_excursion - 40) / 200)
        suggested_cr = current_cr * (1.0 - cr_reduction)
        magnitude = cr_reduction * 100

        # Simulate impact
        if metabolic is not None:
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                cr_multiplier=(1.0 - cr_reduction),
                hour_range=(h_start, h_end))
            predicted_delta = round((tir_sim - tir_now) * 100, 1)
        else:
            predicted_delta = round(magnitude * 0.1, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.CR,
            direction="decrease",
            magnitude_pct=round(magnitude, 0),
            current_value=current_cr,
            suggested_value=round(suggested_cr, 1),
            predicted_tir_delta=predicted_delta,
            affected_hours=(h_start, h_end),
            confidence=min(0.65, days_of_data / HIGH_CONFIDENCE_DAYS),
            evidence=(f"Context-aware CR analysis (EXP-2341): {name} meals "
                      f"show mean excursion {mean_excursion:.0f} mg/dL from "
                      f"{len(meal_indices)} meals. Pre-meal BG negatively "
                      f"correlated with rise (carbs explain <16% of variance)."),
            rationale=(f"Decrease {name} CR from {current_cr:.1f} to "
                       f"{suggested_cr:.1f} g/U ({magnitude:.0f}% more insulin). "
                       f"Mean post-meal excursion is {mean_excursion:.0f} mg/dL."),
        ))

    return recs


