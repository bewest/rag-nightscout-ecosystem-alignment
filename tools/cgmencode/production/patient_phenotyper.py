"""Patient phenotype classifier (EXP-2541).

Classifies patients into two glycemic phenotypes based on outcomes:
  - WELL_CONTROLLED: TIR≈77%, low hypo rate, TBR≈2.2%
  - HYPO_PRONE: TIR≈67%, higher hypo rate, TBR≈5.8%, more variable

Key finding: controller type (NS vs ODC) does NOT predict phenotype
(p=0.18). Classification is based solely on glycemic outcomes.

Decision tree derived from two-cluster analysis of 19 patients.
Minimum 3 days of data required for classification.
"""

from __future__ import annotations

import numpy as np

from .types import PatientPhenotype, PatientPhenotypeResult


# ── Confidence calibration ────────────────────────────────────────────
# More data → higher confidence.  Thresholds from EXP-2541 sensitivity
# analysis: 3-day windows yield ~60% cluster agreement with 14-day
# reference; 7-day yields ~85%; 14-day is the reference standard.

def _compute_confidence(days_of_data: float) -> float:
    """Return classification confidence based on available data duration."""
    if days_of_data < 3.0:
        return 0.0
    if days_of_data < 7.0:
        return 0.4 + 0.1 * days_of_data
    if days_of_data < 14.0:
        return 0.7
    return 0.85


# ── Hypo event counting ──────────────────────────────────────────────

def _count_hypo_events(glucose: np.ndarray, threshold: float = 70.0,
                       min_consecutive: int = 3) -> int:
    """Count distinct hypoglycemic episodes.

    An episode is ≥ *min_consecutive* consecutive readings below
    *threshold* (i.e. ≥15 min at 5-min cadence).  NaN readings break
    a run.
    """
    events = 0
    run = 0
    for g in glucose:
        if np.isnan(g):
            if run >= min_consecutive:
                events += 1
            run = 0
        elif g < threshold:
            run += 1
        else:
            if run >= min_consecutive:
                events += 1
            run = 0
    # trailing run
    if run >= min_consecutive:
        events += 1
    return events


# ── Main classifier ──────────────────────────────────────────────────

def classify_patient_phenotype(
    glucose: np.ndarray,
    hours: np.ndarray,
    days_of_data: float,
) -> PatientPhenotypeResult:
    """Classify patient into a glycemic phenotype.

    Parameters
    ----------
    glucose : np.ndarray
        Glucose values in mg/dL (may contain NaN).
    hours : np.ndarray
        Fractional hour-of-day for each reading (unused by the current
        decision tree but available for future circadian extensions).
    days_of_data : float
        Total span of data in days.

    Returns
    -------
    PatientPhenotypeResult
        Classification with metrics and human-readable evidence.
    """
    valid = glucose[~np.isnan(glucose)]

    # Insufficient data guard
    if days_of_data < 3.0 or len(valid) < 36:  # 36 readings ≈ 3 hours
        return PatientPhenotypeResult(
            phenotype=PatientPhenotype.UNKNOWN,
            confidence=0.0,
            tir=0.0,
            tbr=0.0,
            tar=0.0,
            hypo_events_per_day=0.0,
            cv=0.0,
            evidence="Insufficient data for phenotype classification "
                     f"({days_of_data:.1f} days, {len(valid)} valid readings).",
        )

    n = len(valid)
    tir = float(np.sum((valid >= 70) & (valid <= 180)) / n)
    tbr = float(np.sum(valid < 70) / n)
    tar = float(np.sum(valid > 180) / n)

    mean_g = float(np.mean(valid))
    std_g = float(np.std(valid))
    cv = std_g / mean_g if mean_g > 0 else 0.0

    hypo_events = _count_hypo_events(glucose)
    hypo_per_day = hypo_events / days_of_data if days_of_data > 0 else 0.0

    confidence = _compute_confidence(days_of_data)

    # ── Decision tree (EXP-2541 cluster analysis) ─────────────────
    if tir >= 0.70 and tbr < 0.04:
        phenotype = PatientPhenotype.WELL_CONTROLLED
        evidence = (
            f"Well-controlled: TIR={tir:.1%}, TBR={tbr:.1%} "
            f"(CV={cv:.2f}, hypo {hypo_per_day:.1f}/day)."
        )
    elif tbr >= 0.04 or (tir < 0.65 and hypo_per_day >= 1.0):
        phenotype = PatientPhenotype.HYPO_PRONE
        reasons = []
        if tbr >= 0.04:
            reasons.append(f"TBR={tbr:.1%}≥4%")
        if tir < 0.65:
            reasons.append(f"TIR={tir:.1%}<65%")
        if hypo_per_day >= 1.0:
            reasons.append(f"hypo={hypo_per_day:.1f}/day≥1")
        evidence = f"Hypo-prone: {', '.join(reasons)} (CV={cv:.2f})."
    elif tir >= 0.65 and tbr < 0.04:
        phenotype = PatientPhenotype.WELL_CONTROLLED
        evidence = (
            f"Borderline well-controlled: TIR={tir:.1%}, TBR={tbr:.1%} "
            f"(CV={cv:.2f}, hypo {hypo_per_day:.1f}/day)."
        )
    elif cv > 0.36:
        phenotype = PatientPhenotype.HYPO_PRONE
        evidence = (
            f"Hypo-prone (high variability): CV={cv:.2f}>0.36, "
            f"TIR={tir:.1%}, TBR={tbr:.1%}."
        )
    else:
        phenotype = PatientPhenotype.WELL_CONTROLLED
        evidence = (
            f"Well-controlled (default): TIR={tir:.1%}, TBR={tbr:.1%}, "
            f"CV={cv:.2f}."
        )

    return PatientPhenotypeResult(
        phenotype=phenotype,
        confidence=confidence,
        tir=tir,
        tbr=tbr,
        tar=tar,
        hypo_events_per_day=hypo_per_day,
        cv=cv,
        evidence=evidence,
    )
