"""
settings_optimizer.py — Quantitative settings optimization from natural experiments.

Research basis: EXP-1701 (optimal basal from fasting drift),
               EXP-1703 (optimal ISF from correction response curves),
               EXP-1705 (optimal CR from meal excursion analysis),
               EXP-1707 (evidence-based confidence grading),
               EXP-1711–1717 (retrospective validation).

Key findings (11 patients, 1,838 patient-days):
  - ISF universally underestimated 2.3× (100% of patients)
  - CR too aggressive by 27% (effective CR = 73% of profile)
  - Basal mostly well-calibrated (73% within 5%)
  - Combined optimization predicts +2.8% TIR improvement
  - ISF correction contributes 85% of predicted TIR gain

This module bridges production natural_experiment_detector (Stage 5c)
to settings_advisor (Stage 6) by extracting precise optimal values
from detected natural experiment windows, with bootstrap confidence
intervals and per-period time-of-day schedules.

Integration: Pipeline Stage 6a, between NE detection and settings advice.
"""

from __future__ import annotations

import math
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np

from .natural_experiment_detector import (
    NaturalExperiment,
    NaturalExperimentCensus,
    NaturalExperimentType,
)
from .types import (
    ConfidenceGrade,
    OptimalSettings,
    PatientProfile,
    SettingScheduleEntry,
    SettingsOptimizationResult,
)

# ── Period Definitions ────────────────────────────────────────────────

PERIODS: List[Tuple[str, int, int]] = [
    ("overnight",  0,  6),
    ("morning",    6, 10),
    ("midday",    10, 14),
    ("afternoon", 14, 18),
    ("evening",   18, 24),
]

# ── Thresholds ────────────────────────────────────────────────────────

MIN_EVIDENCE_HIGH = 10       # windows for "high" confidence
MIN_EVIDENCE_MEDIUM = 3      # windows for "medium" confidence
MIN_CORRECTION_DELTA = 5.0   # mg/dL minimum drop for valid ISF
MIN_CORRECTION_DOSE = 0.1    # U minimum bolus for valid ISF
ISF_RANGE = (5.0, 500.0)     # valid ISF range (mg/dL per U)
CR_RANGE = (1.0, 100.0)      # valid CR range (g per U)
BASAL_CLAMP_FACTOR = 0.5     # max ±50% basal change
BOOTSTRAP_N = 1000
BOOTSTRAP_CI = 0.95
BOOTSTRAP_SEED = 42

# TIR improvement coefficients (from EXP-1717 regression)
TIR_COEFF_BASAL = 0.15       # pp TIR per % basal drift reduction
TIR_COEFF_ISF = 0.85         # relative ISF contribution (85% of total)
TIR_COEFF_CR = 0.10          # pp TIR per 10% CR improvement


# ── Helpers ───────────────────────────────────────────────────────────

def _safe_val(v) -> Optional[float]:
    """Return v as float if finite, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _bootstrap_ci(values: List[float],
                  n_boot: int = BOOTSTRAP_N,
                  ci: float = BOOTSTRAP_CI) -> Tuple[float, float, float]:
    """Bootstrap confidence interval for median.

    Returns (median, ci_low, ci_high).
    """
    arr = np.array(values, dtype=float)
    med = float(np.median(arr))
    if len(arr) < 3:
        return med, med, med
    rng = np.random.RandomState(BOOTSTRAP_SEED)
    medians = []
    for _ in range(n_boot):
        sample = arr[rng.randint(0, len(arr), size=len(arr))]
        medians.append(float(np.median(sample)))
    medians.sort()
    alpha = (1 - ci) / 2
    lo = medians[int(alpha * n_boot)]
    hi = medians[int((1 - alpha) * n_boot)]
    return med, lo, hi


def _period_for_hour(hour: float) -> str:
    """Map hour-of-day to period name."""
    for name, start, end in PERIODS:
        if start <= hour < end:
            return name
    return "overnight"  # 24 wraps to overnight


def _profile_value_at_hour(schedule: List[Dict], hour: float,
                           key: str = 'value') -> float:
    """Extract profile value active at a given hour.

    Schedule entries are [{time: "HH:MM", value: X}, ...] sorted by time.
    Returns the last entry whose time is <= hour.
    """
    if not schedule:
        return 0.0
    best = schedule[0].get(key) or schedule[0].get('sensitivity') or 0.0
    for entry in schedule:
        t = entry.get('time', '00:00')
        parts = t.split(':')
        entry_hour = int(parts[0]) + int(parts[1]) / 60 if len(parts) >= 2 else 0
        if entry_hour <= hour:
            best = entry.get(key) or entry.get('sensitivity') or entry.get('rate') or best
    return float(best) if best else 0.0


def _profile_mean(schedule: List[Dict], key: str = 'value') -> float:
    """Compute mean profile value across all entries."""
    vals = []
    for entry in schedule:
        v = entry.get(key) or entry.get('sensitivity') or entry.get('rate')
        if v is not None:
            vals.append(float(v))
    return float(np.mean(vals)) if vals else 0.0


def _evidence_confidence(n: int) -> str:
    """Grade confidence from evidence window count."""
    if n >= MIN_EVIDENCE_HIGH:
        return "high"
    elif n >= MIN_EVIDENCE_MEDIUM:
        return "medium"
    else:
        return "low"


# ── Core Extraction ───────────────────────────────────────────────────

def _extract_basal_schedule(
    fasting: List[NaturalExperiment],
    overnight: List[NaturalExperiment],
    profile: PatientProfile,
) -> List[SettingScheduleEntry]:
    """Extract optimal basal schedule from fasting/overnight drift.

    Research basis: EXP-1701 — per-period basal from drift analysis.
    Method: drift_mg_dl_per_hour / ISF gives basal adjustment in U/hr.
    Positive drift → increase basal; negative drift → decrease.
    """
    overnight_fasting = [w for w in overnight
                         if w.measurements.get('is_fasting', False)]
    all_fasting = list(fasting) + overnight_fasting

    profile_isf_mean = _profile_mean(profile.isf_mgdl(), 'value')
    if profile_isf_mean < 1:
        profile_isf_mean = _profile_mean(profile.isf_mgdl(), 'sensitivity')
    if profile_isf_mean < 1:
        profile_isf_mean = 50.0  # safe fallback

    schedule = []
    for period_name, start_h, end_h in PERIODS:
        profile_basal = _profile_value_at_hour(
            profile.basal_schedule, (start_h + end_h) / 2, 'value')
        if profile_basal <= 0:
            profile_basal = _profile_value_at_hour(
                profile.basal_schedule, (start_h + end_h) / 2, 'rate')
        if profile_basal <= 0:
            profile_basal = _profile_mean(profile.basal_schedule, 'value') or 0.8

        drifts = []
        for w in all_fasting:
            if _period_for_hour(w.hour_of_day) != period_name:
                continue
            d = _safe_val(w.measurements.get('drift_mg_dl_per_hour'))
            if d is not None:
                drifts.append(d)

        conf = _evidence_confidence(len(drifts))
        if len(drifts) >= MIN_EVIDENCE_MEDIUM:
            med_drift = float(np.median(drifts))
            adjustment = med_drift / max(profile_isf_mean, 10)
            new_basal = max(0.05, profile_basal + adjustment)
            new_basal = max(profile_basal * BASAL_CLAMP_FACTOR,
                            min(profile_basal * (1 + BASAL_CLAMP_FACTOR), new_basal))
            new_basal = round(new_basal, 3)

            if len(drifts) >= 3:
                _, lo, hi = _bootstrap_ci(drifts)
                adj_lo = lo / max(profile_isf_mean, 10)
                adj_hi = hi / max(profile_isf_mean, 10)
                ci_lo = round(max(0.05, profile_basal + adj_lo), 3)
                ci_hi = round(max(0.05, profile_basal + adj_hi), 3)
            else:
                ci_lo, ci_hi = None, None
        else:
            new_basal = round(profile_basal, 3)
            ci_lo, ci_hi = None, None

        change_pct = ((new_basal - profile_basal) / max(profile_basal, 0.01)) * 100

        schedule.append(SettingScheduleEntry(
            period=period_name,
            start_hour=start_h,
            current_value=round(profile_basal, 3),
            recommended_value=new_basal,
            change_pct=round(change_pct, 1),
            confidence=conf,
            n_evidence=len(drifts),
            ci_low=ci_lo,
            ci_high=ci_hi,
        ))

    return schedule


def _extract_isf_schedule(
    corrections: List[NaturalExperiment],
    profile: PatientProfile,
) -> List[SettingScheduleEntry]:
    """Extract optimal ISF schedule from correction response curves.

    Research basis: EXP-1703 — ISF from BG delta / bolus dose.
    Uses curve_isf (exponential fit) when available, falls back to simple_isf.
    Key finding: ISF universally underestimated 2.3× across all patients.
    """
    schedule = []
    all_isf_vals = []  # fallback pool

    # Pre-compute all valid ISF values for fallback
    for w in corrections:
        m = w.measurements
        isf = _safe_val(m.get('curve_isf')) or _safe_val(m.get('simple_isf'))
        if isf is not None and ISF_RANGE[0] < isf < ISF_RANGE[1]:
            all_isf_vals.append(isf)

    for period_name, start_h, end_h in PERIODS:
        mid_h = (start_h + end_h) / 2
        profile_isf = _profile_value_at_hour(profile.isf_mgdl(), mid_h, 'value')
        if profile_isf < 1:
            profile_isf = _profile_value_at_hour(profile.isf_mgdl(), mid_h, 'sensitivity')
        if profile_isf < 1:
            profile_isf = _profile_mean(profile.isf_mgdl()) or 50.0

        isf_vals = []
        for w in corrections:
            if _period_for_hour(w.hour_of_day) != period_name:
                continue
            m = w.measurements
            isf = _safe_val(m.get('curve_isf')) or _safe_val(m.get('simple_isf'))
            if isf is not None and ISF_RANGE[0] < isf < ISF_RANGE[1]:
                isf_vals.append(isf)

        conf = _evidence_confidence(len(isf_vals))
        if len(isf_vals) >= MIN_EVIDENCE_MEDIUM:
            med, lo, hi = _bootstrap_ci(isf_vals)
        elif all_isf_vals:
            # Fallback: use all corrections regardless of period
            med = float(np.median(all_isf_vals))
            lo, hi = med * 0.8, med * 1.2
            conf = "low"
        else:
            med = profile_isf
            lo, hi = med * 0.8, med * 1.2
            conf = "low"

        change_pct = ((med - profile_isf) / max(profile_isf, 0.01)) * 100

        schedule.append(SettingScheduleEntry(
            period=period_name,
            start_hour=start_h,
            current_value=round(profile_isf, 1),
            recommended_value=round(med, 1),
            change_pct=round(change_pct, 1),
            confidence=conf,
            n_evidence=len(isf_vals),
            ci_low=round(lo, 1),
            ci_high=round(hi, 1),
        ))

    return schedule


def _extract_cr_schedule(
    meals: List[NaturalExperiment],
    profile: PatientProfile,
) -> List[SettingScheduleEntry]:
    """Extract optimal CR schedule from meal excursion analysis.

    Research basis: EXP-1705 — effective CR = carbs / (bolus + excursion/ISF).
    Key finding: effective CR is 73% of profile (patients overbolusing).
    """
    profile_isf_mean = _profile_mean(profile.isf_mgdl(), 'value')
    if profile_isf_mean < 1:
        profile_isf_mean = _profile_mean(profile.isf_mgdl(), 'sensitivity')
    if profile_isf_mean < 1:
        profile_isf_mean = 50.0

    schedule = []
    all_cr_vals = []  # fallback pool

    # Pre-compute all valid CR values for fallback
    for w in meals:
        m = w.measurements
        cg = _safe_val(m.get('carbs_g'))
        mb = _safe_val(m.get('bolus_u'))
        exc = _safe_val(m.get('excursion_mg_dl'))
        if (cg is not None and cg >= 5 and
                mb is not None and mb >= 0.1 and
                exc is not None):
            add_ins = exc / max(profile_isf_mean, 10)
            total = mb + add_ins
            if total > 0:
                eff_cr = cg / total
                if CR_RANGE[0] < eff_cr < CR_RANGE[1]:
                    all_cr_vals.append(eff_cr)

    for period_name, start_h, end_h in PERIODS:
        mid_h = (start_h + end_h) / 2
        profile_cr = _profile_value_at_hour(profile.cr_schedule, mid_h, 'value')
        if profile_cr < 1:
            profile_cr = _profile_mean(profile.cr_schedule) or 10.0

        cr_vals = []
        for w in meals:
            if _period_for_hour(w.hour_of_day) != period_name:
                continue
            m = w.measurements
            cg = _safe_val(m.get('carbs_g'))
            mb = _safe_val(m.get('bolus_u'))
            exc = _safe_val(m.get('excursion_mg_dl'))
            if (cg is not None and cg >= 5 and
                    mb is not None and mb >= 0.1 and
                    exc is not None):
                add_ins = exc / max(profile_isf_mean, 10)
                total = mb + add_ins
                if total > 0:
                    eff_cr = cg / total
                    if CR_RANGE[0] < eff_cr < CR_RANGE[1]:
                        cr_vals.append(eff_cr)

        # Higher threshold for CR (meals have more variability)
        cr_min_high = 15
        conf_raw = _evidence_confidence(len(cr_vals))
        if conf_raw == "high" and len(cr_vals) < cr_min_high:
            conf_raw = "medium"

        if len(cr_vals) >= MIN_EVIDENCE_MEDIUM:
            med, lo, hi = _bootstrap_ci(cr_vals)
            conf = conf_raw
        elif all_cr_vals:
            med = float(np.median(all_cr_vals))
            lo, hi = med * 0.8, med * 1.2
            conf = "low"
        else:
            med = profile_cr
            lo, hi = med * 0.8, med * 1.2
            conf = "low"

        change_pct = ((med - profile_cr) / max(profile_cr, 0.01)) * 100

        schedule.append(SettingScheduleEntry(
            period=period_name,
            start_hour=start_h,
            current_value=round(profile_cr, 1),
            recommended_value=round(med, 1),
            change_pct=round(change_pct, 1),
            confidence=conf,
            n_evidence=len(cr_vals),
            ci_low=round(lo, 1),
            ci_high=round(hi, 1),
        ))

    return schedule


def _grade_overall_confidence(
    basal: List[SettingScheduleEntry],
    isf: List[SettingScheduleEntry],
    cr: List[SettingScheduleEntry],
) -> Tuple[ConfidenceGrade, int]:
    """Grade overall settings confidence from evidence counts.

    Research basis: EXP-1707 — all patients grade B+ with mean 1,101 windows.
    A: ≥100 total evidence, ≥12 period-settings at medium+
    B: ≥50 total, ≥8 at medium+
    C: ≥20 total, ≥4 at medium+
    D: below C thresholds
    """
    all_entries = list(basal) + list(isf) + list(cr)
    total = sum(e.n_evidence for e in all_entries)
    sufficient = sum(1 for e in all_entries
                     if e.confidence in ("high", "medium"))

    if total >= 100 and sufficient >= 12:
        grade = ConfidenceGrade.A
    elif total >= 50 and sufficient >= 8:
        grade = ConfidenceGrade.B
    elif total >= 20 and sufficient >= 4:
        grade = ConfidenceGrade.C
    else:
        grade = ConfidenceGrade.D

    return grade, total


def _predict_tir_improvement(
    basal: List[SettingScheduleEntry],
    isf: List[SettingScheduleEntry],
    cr: List[SettingScheduleEntry],
) -> Tuple[float, Dict[str, float]]:
    """Predict TIR improvement from settings corrections.

    Research basis: EXP-1717 — combined +2.8% TIR predicted,
    ISF contributes 85% of gain.

    Uses simplified linear model calibrated on EXP-1711–1715 results.
    """
    # Basal contribution: drift reduction → TIR
    basal_drifts = [abs(e.change_pct) for e in basal
                    if e.confidence != "low" and abs(e.change_pct) > 2]
    basal_tir = sum(d * TIR_COEFF_BASAL / 100 for d in basal_drifts)

    # ISF contribution: mismatch reduction → TIR (dominant lever)
    isf_mismatches = [abs(e.change_pct) for e in isf
                      if e.confidence != "low" and abs(e.change_pct) > 5]
    isf_tir = sum(m * TIR_COEFF_ISF / 100 for m in isf_mismatches)

    # CR contribution: bolus accuracy → TIR
    cr_changes = [abs(e.change_pct) for e in cr
                  if e.confidence != "low" and abs(e.change_pct) > 5]
    cr_tir = sum(c * TIR_COEFF_CR / 100 for c in cr_changes)

    total = round(basal_tir + isf_tir + cr_tir, 2)
    contributions = {
        "basal": round(basal_tir, 2),
        "isf": round(isf_tir, 2),
        "cr": round(cr_tir, 2),
    }

    return total, contributions


def _validate_retrospective(
    basal: List[SettingScheduleEntry],
    isf: List[SettingScheduleEntry],
    cr: List[SettingScheduleEntry],
    fasting: List[NaturalExperiment],
    corrections: List[NaturalExperiment],
    meals: List[NaturalExperiment],
) -> Tuple[float, float, float, int]:
    """Compute retrospective validation metrics.

    Research basis: EXP-1711 (basal drift reduction 22%),
    EXP-1713 (ISF residual improvement 7/11), EXP-1715 (CR 82%).

    Returns: (basal_improvement%, isf_improvement%, cr_improvement%, n_recs)
    """
    # Basal: what fraction of fasting drift would be eliminated?
    basal_map = {e.period: e for e in basal}
    drift_before, drift_after = 0.0, 0.0
    for w in fasting:
        d = _safe_val(w.measurements.get('drift_mg_dl_per_hour'))
        if d is None:
            continue
        period = _period_for_hour(w.hour_of_day)
        drift_before += abs(d)
        entry = basal_map.get(period)
        if entry and entry.confidence != "low":
            residual = abs(d) * (1.0 - min(abs(entry.change_pct) / 100.0, 0.5))
            drift_after += residual
        else:
            drift_after += abs(d)
    basal_pct = ((drift_before - drift_after) / max(drift_before, 0.001)) * 100

    # ISF: correction residual improvement
    isf_map = {e.period: e for e in isf}
    isf_improved, isf_total = 0, 0
    for w in corrections:
        m = w.measurements
        isf_est = _safe_val(m.get('curve_isf')) or _safe_val(m.get('simple_isf'))
        if isf_est is None:
            continue
        period = _period_for_hour(w.hour_of_day)
        entry = isf_map.get(period)
        if entry and entry.confidence != "low":
            isf_total += 1
            # Would the recommended ISF be closer?
            profile_err = abs(isf_est - entry.current_value)
            rec_err = abs(isf_est - entry.recommended_value)
            if rec_err < profile_err:
                isf_improved += 1
    isf_pct = (isf_improved / max(isf_total, 1)) * 100

    # CR: meal excursion improvement
    cr_map = {e.period: e for e in cr}
    cr_improved, cr_total = 0, 0
    for w in meals:
        m = w.measurements
        cg = _safe_val(m.get('carbs_g'))
        mb = _safe_val(m.get('bolus_u'))
        if cg is None or cg < 5 or mb is None or mb < 0.1:
            continue
        period = _period_for_hour(w.hour_of_day)
        entry = cr_map.get(period)
        if entry and entry.confidence != "low":
            cr_total += 1
            # Would recommended CR produce better bolus?
            profile_bolus = cg / max(entry.current_value, 1)
            rec_bolus = cg / max(entry.recommended_value, 1)
            if abs(rec_bolus - mb) < abs(profile_bolus - mb):
                cr_improved += 1
    cr_pct = (cr_improved / max(cr_total, 1)) * 100

    # Count actionable recommendations (medium/high confidence, >5% change)
    n_recs = sum(1 for sched in [basal, isf, cr]
                 for e in sched
                 if e.confidence in ("high", "medium") and abs(e.change_pct) > 5)

    return round(basal_pct, 1), round(isf_pct, 1), round(cr_pct, 1), n_recs


def _compute_temporal_stability(
    isf_schedule: List[SettingScheduleEntry],
) -> float:
    """Compute temporal stability metric for ISF recommendations.

    Research basis: EXP-1903/1907 — ISF CV across rolling windows = 4.8%
    for stable patients, 9.5% across 5-fold CV. CV > 15% indicates instability.

    Returns CV as a fraction (0.0 = perfectly stable, higher = less stable).
    For production, we approximate by measuring the spread of ISF evidence
    counts and confidence across periods.
    """
    isf_vals = [e.recommended_value for e in isf_schedule
                if e.confidence in ('high', 'medium') and e.recommended_value > 0]
    if len(isf_vals) < 2:
        return 0.0
    mean_isf = float(np.mean(isf_vals))
    if mean_isf < 1:
        return 0.0
    cv = float(np.std(isf_vals) / mean_isf)
    return round(cv, 3)


def _make_validation_note(
    grade: 'ConfidenceGrade',
    isf_schedule: List[SettingScheduleEntry],
    stability_cv: float,
) -> str:
    """Generate human-readable validation context.

    Research basis: EXP-1901 series — within-patient mismatch→TIR r=-0.371
    (p=0.0007), train/verify concordance 0.849, 5-fold CV stability 9.5%.
    """
    # ISF mismatch ratio
    ratios = [e.recommended_value / max(e.current_value, 1)
              for e in isf_schedule
              if e.confidence in ('high', 'medium') and e.current_value > 0]
    mean_ratio = float(np.mean(ratios)) if ratios else 1.0

    parts = []
    if mean_ratio > 1.5:
        parts.append(f"ISF appears {mean_ratio:.1f}× underestimated")
    elif mean_ratio < 0.7:
        parts.append(f"ISF appears {1/mean_ratio:.1f}× overestimated")

    if stability_cv > 0.15:
        parts.append("ISF varies >15% across time periods — recommendation less certain")
    elif stability_cv < 0.05:
        parts.append("ISF is highly stable across time periods")

    # Validated expectation setting
    if mean_ratio > 1.2:
        parts.append(
            "Within-patient validation (EXP-1901, p<0.001) confirms "
            "windows closer to optimal ISF have better TIR. "
            "AID compensates well, so expect incremental improvement")

    return ". ".join(parts) + "." if parts else ""


# ── Public API ────────────────────────────────────────────────────────

def optimize_settings(
    census: NaturalExperimentCensus,
    profile: PatientProfile,
) -> SettingsOptimizationResult:
    """Compute optimal pump settings from natural experiment windows.

    This is the production bridge from EXP-1701–1721 research.
    Takes detected natural experiments (Stage 5c output) and the patient's
    current profile, then extracts quantitative optimal settings for
    basal rate, ISF, and CR — per time-of-day period with bootstrap CI.

    Args:
        census: Natural experiment census from detect_natural_experiments()
        profile: Patient's current therapy profile

    Returns:
        SettingsOptimizationResult with optimal schedules, confidence,
        predicted TIR improvement, and retrospective validation metrics.

    Research validation:
        - 11 patients, 1,838 patient-days, 1,101 mean evidence windows
        - All patients grade B+ confidence
        - +2.8% predicted TIR improvement (population mean)
        - ISF correction contributes 85% of gain
    """
    # Partition experiments by type
    fasting = census.filter_by_type(NaturalExperimentType.FASTING)
    overnight = census.filter_by_type(NaturalExperimentType.OVERNIGHT)
    corrections = census.filter_by_type(NaturalExperimentType.CORRECTION)
    meals = census.filter_by_type(NaturalExperimentType.MEAL)

    w = []

    # Extract optimal schedules
    basal_schedule = _extract_basal_schedule(fasting, overnight, profile)
    isf_schedule = _extract_isf_schedule(corrections, profile)
    cr_schedule = _extract_cr_schedule(meals, profile)

    # Grade overall confidence
    grade, total_evidence = _grade_overall_confidence(
        basal_schedule, isf_schedule, cr_schedule)

    # Predict TIR improvement
    tir_delta, tir_contributions = _predict_tir_improvement(
        basal_schedule, isf_schedule, cr_schedule)

    # Build OptimalSettings
    optimal = OptimalSettings(
        basal_schedule=basal_schedule,
        isf_schedule=isf_schedule,
        cr_schedule=cr_schedule,
        confidence_grade=grade,
        total_evidence=total_evidence,
        predicted_tir_delta=tir_delta,
        tir_contributions=tir_contributions,
    )

    # Retrospective validation
    all_fasting = list(fasting) + [
        w for w in overnight
        if w.measurements.get('is_fasting', False)]
    basal_imp, isf_imp, cr_imp, n_recs = _validate_retrospective(
        basal_schedule, isf_schedule, cr_schedule,
        all_fasting, corrections, meals)

    # Temporal stability (EXP-1901/1903/1907)
    stability_cv = _compute_temporal_stability(isf_schedule)
    validation_note = _make_validation_note(grade, isf_schedule, stability_cv)

    if stability_cv > 0.15:
        w.append(f"ISF varies {stability_cv*100:.0f}% across periods — "
                 "consider whether time-of-day variation is clinical or noise")

    return SettingsOptimizationResult(
        optimal=optimal,
        basal_drift_reduction_pct=basal_imp,
        isf_residual_improvement_pct=isf_imp,
        cr_excursion_improvement_pct=cr_imp,
        n_recommendations=n_recs,
        temporal_stability_cv=stability_cv,
        validation_note=validation_note,
        warnings=w,
    )
