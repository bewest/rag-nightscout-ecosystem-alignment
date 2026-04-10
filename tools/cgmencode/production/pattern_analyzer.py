"""
pattern_analyzer.py — Circadian, changepoint, ISF variation, phenotype analysis.

Research basis: EXP-781 (circadian correction, +0.474 R²),
               EXP-696 (settings change detection),
               EXP-765 (ISF time-of-day variation, 29.7% mean)

Key findings:
  - Circadian fit: a·sin(2πh/24) + b·cos(2πh/24) + c explains +0.474 R² at 60min
  - Changepoint distribution is bimodal: 0 or 10+ per patient
  - ISF varies 29.7% by time of day (patient c: 82.2%)
  - Phenotypes: morning-high vs night-hypo vs stable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .types import (CircadianFit, ExcursionType, HarmonicFit, MetabolicState,
                    PatternProfile, Phenotype)


def fit_circadian(residuals: np.ndarray,
                  hours: np.ndarray) -> CircadianFit:
    """Fit 3-parameter circadian model to glucose residuals.

    Model: residual ≈ a·sin(2πh/24) + b·cos(2πh/24) + c

    This captures the dawn phenomenon and other time-of-day effects.
    Research finding: this 3-parameter model adds +0.474 R² at 60-min
    prediction horizon (EXP-781).

    Args:
        residuals: (N,) prediction residuals (actual - predicted BG change).
        hours: (N,) fractional hour of day (0-24).

    Returns:
        CircadianFit with coefficients, amplitude, and phase.
    """
    valid = np.asarray(np.isfinite(residuals) & np.isfinite(hours))
    if np.sum(valid) < 48:  # need at least 4 hours of data
        return CircadianFit(a=0.0, b=0.0, c=0.0, amplitude=0.0, phase_hours=0.0)

    r = residuals[valid]
    h = hours[valid]

    # Build design matrix: [sin, cos, 1]
    angle = 2.0 * np.pi * h / 24.0
    A = np.column_stack([np.sin(angle), np.cos(angle), np.ones(len(h))])

    # Least squares fit
    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, r, rcond=None)
    except np.linalg.LinAlgError:
        return CircadianFit(a=0.0, b=0.0, c=0.0, amplitude=0.0, phase_hours=0.0)

    a, b, c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])
    amplitude = float(np.sqrt(a**2 + b**2))
    phase = float(np.arctan2(a, b) * 24.0 / (2.0 * np.pi)) % 24.0

    # R² improvement from circadian fit
    predicted = A @ coeffs
    ss_res = np.sum((r - predicted) ** 2)
    ss_tot = np.sum((r - np.mean(r)) ** 2)
    r2_improvement = float(1.0 - ss_res / max(ss_tot, 1e-12)) if ss_tot > 0 else 0.0

    return CircadianFit(
        a=a, b=b, c=c,
        amplitude=amplitude,
        phase_hours=phase,
        r2_improvement=r2_improvement,
    )


def fit_harmonic_circadian(glucose: np.ndarray,
                           hours: np.ndarray,
                           periods: list = None) -> HarmonicFit:
    """Fit multi-frequency harmonic circadian model (EXP-1631–1638).

    Model: glucose(h) = offset + Σ_k [a_k·sin(2πh/P_k) + b_k·cos(2πh/P_k)]

    Research finding: 4-harmonic (24+12+8+6h) captures 96% of circadian
    glucose variance (R²=0.959 mean) vs 51% for single sinusoidal.
    Improvement is universal: all 11 patients benefit (+6% to +73%).

    Args:
        glucose: (N,) glucose values (mg/dL).
        hours: (N,) fractional hour of day (0-24).
        periods: list of harmonic periods in hours (default [24, 12, 8, 6]).

    Returns:
        HarmonicFit with amplitudes, phases, and R² per harmonic.
    """
    if periods is None:
        periods = [24.0, 12.0, 8.0, 6.0]

    valid = np.isfinite(glucose) & np.isfinite(hours)
    if np.sum(valid) < 48:
        return HarmonicFit(
            amplitudes=[0.0] * len(periods),
            phases=[0.0] * len(periods),
            offset=float(np.nanmean(glucose)) if len(glucose) > 0 else 120.0,
            periods=periods,
            r2=0.0,
            r2_by_harmonic={f'{int(p)}h': 0.0 for p in periods},
            dominant_amplitude=0.0,
            dominant_period=periods[0],
        )

    # Bin glucose by fractional hour (288 bins = 5-min resolution over 24h)
    g = glucose[valid]
    h = hours[valid]

    # Build design matrix: [sin(2πh/P1), cos(2πh/P1), sin(2πh/P2), ...]
    columns = []
    for p in periods:
        angle = 2.0 * np.pi * h / p
        columns.append(np.sin(angle))
        columns.append(np.cos(angle))
    columns.append(np.ones(len(h)))  # offset

    A = np.column_stack(columns)

    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, g, rcond=None)
    except np.linalg.LinAlgError:
        return HarmonicFit(
            amplitudes=[0.0] * len(periods),
            phases=[0.0] * len(periods),
            offset=float(np.mean(g)),
            periods=periods,
            r2=0.0,
            r2_by_harmonic={f'{int(p)}h': 0.0 for p in periods},
            dominant_amplitude=0.0,
            dominant_period=periods[0],
        )

    offset = float(coeffs[-1])
    amplitudes = []
    phases = []
    for i, p in enumerate(periods):
        a_coeff = float(coeffs[2 * i])
        b_coeff = float(coeffs[2 * i + 1])
        amp = float(np.sqrt(a_coeff**2 + b_coeff**2))
        phase_h = float(np.arctan2(a_coeff, b_coeff) * p / (2.0 * np.pi)) % p
        amplitudes.append(amp)
        phases.append(phase_h)

    # Compute R² for full model
    predicted = A @ coeffs
    ss_res = np.sum((g - predicted) ** 2)
    ss_tot = np.sum((g - np.mean(g)) ** 2)
    r2_full = float(1.0 - ss_res / max(ss_tot, 1e-12))

    # Compute cumulative R² adding one harmonic at a time
    r2_by_harmonic = {}
    for k in range(len(periods)):
        n_cols = 2 * (k + 1) + 1  # sin/cos pairs + offset
        A_sub = np.column_stack(columns[:2 * (k + 1)] + [columns[-1]])
        try:
            c_sub, _, _, _ = np.linalg.lstsq(A_sub, g, rcond=None)
            pred_sub = A_sub @ c_sub
            ss_r = np.sum((g - pred_sub) ** 2)
            r2_by_harmonic[f'{int(periods[k])}h'] = float(1.0 - ss_r / max(ss_tot, 1e-12))
        except np.linalg.LinAlgError:
            r2_by_harmonic[f'{int(periods[k])}h'] = 0.0

    # Dominant harmonic
    max_idx = int(np.argmax(amplitudes))

    return HarmonicFit(
        amplitudes=amplitudes,
        phases=phases,
        offset=offset,
        periods=periods,
        r2=r2_full,
        r2_by_harmonic=r2_by_harmonic,
        dominant_amplitude=amplitudes[max_idx],
        dominant_period=periods[max_idx],
    )


# ── Excursion Detection & Cascade Analysis (EXP-1691) ────────────────

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# Transitions that form metabolic cascades (EXP-1691: 62% participation)
CASCADE_TRANSITIONS = {
    ('hypo_entry', 'hypo_recovery'),
    ('hypo_recovery', 'rebound_rise'),
    ('hypo_recovery', 'uam_rise'),
    ('hypo_recovery', 'hypo_entry'),
    ('hypo_recovery', 'meal_rise'),
    ('rebound_rise', 'insulin_fall'),
    ('rebound_rise', 'post_rise_fall'),
    ('rebound_rise', 'natural_fall'),
    ('rebound_rise', 'correction_drop'),
    ('insulin_fall', 'hypo_entry'),
    ('post_rise_fall', 'hypo_entry'),
    ('natural_fall', 'hypo_entry'),
    ('correction_drop', 'hypo_entry'),
    ('meal_rise', 'correction_drop'),
    ('meal_rise', 'insulin_fall'),
    ('uam_rise', 'insulin_fall'),
    ('uam_rise', 'post_rise_fall'),
    ('uam_rise', 'correction_drop'),
}


@dataclass
class Excursion:
    """A single classified glucose excursion."""
    start_idx: int
    end_idx: int
    start_bg: float
    end_bg: float
    direction: str            # 'rise' or 'fall'
    magnitude: float          # mg/dL
    duration_steps: int
    rate: float               # mg/dL per 5-min step
    excursion_type: str       # matches ExcursionType values
    has_carbs: bool
    carb_amount: float
    iob_at_start: float
    iob_delta: float
    supply_mean: float
    demand_mean: float
    net_mean: float
    tod_hour: float


@dataclass
class CascadeChain:
    """A sequence of linked excursions forming a metabolic cascade."""
    excursions: List[Excursion]
    length: int
    total_magnitude: float
    duration_steps: int
    root_type: str            # type of first excursion in chain


@dataclass
class CascadeAnalysis:
    """Summary of excursion and cascade detection over a glucose trace."""
    excursions: List[Excursion] = field(default_factory=list)
    chains: List[CascadeChain] = field(default_factory=list)
    total_excursions: int = 0
    in_chain_count: int = 0
    isolated_count: int = 0
    cascade_participation: float = 0.0   # fraction of excursions in chains
    type_counts: Dict[str, int] = field(default_factory=dict)


def detect_excursions(glucose: np.ndarray,
                      carbs: np.ndarray,
                      iob: np.ndarray,
                      metabolic: Optional[MetabolicState] = None,
                      min_excursion: float = 15.0) -> List[Excursion]:
    """Detect and classify all glucose excursions (EXP-1691).

    An excursion is a contiguous rise or fall ≥ min_excursion mg/dL.
    Classification uses priority-ordered rules based on glucose level,
    carb timing, IOB changes, and preceding excursion context.

    Args:
        glucose: (N,) glucose values (mg/dL), may contain NaN.
        carbs: (N,) carb grams per step.
        iob: (N,) insulin on board (Units).
        metabolic: MetabolicState for supply/demand context.
        min_excursion: minimum magnitude to qualify (mg/dL).

    Returns:
        List of Excursion in chronological order.
    """
    N = len(glucose)
    excursions: List[Excursion] = []

    g = glucose.copy().astype(np.float64)
    for i in range(1, N):
        if np.isnan(g[i]) and not np.isnan(g[i - 1]):
            g[i] = g[i - 1]

    _carbs = np.nan_to_num(carbs, nan=0.0) if carbs is not None else np.zeros(N)
    _iob = np.nan_to_num(iob, nan=0.0) if iob is not None else np.zeros(N)

    # Supply/demand context
    if metabolic is not None:
        supply = metabolic.supply
        demand = metabolic.demand
        net = metabolic.net_flux
    else:
        supply = np.zeros(N)
        demand = np.zeros(N)
        net = np.zeros(N)

    i = 0
    while i < N - 2:
        if np.isnan(g[i]):
            i += 1
            continue

        start_idx = i
        start_bg = g[i]
        peak_bg = start_bg
        trough_bg = start_bg
        peak_idx = i
        trough_idx = i

        j = i + 1
        direction = None
        while j < N:
            if np.isnan(g[j]):
                j += 1
                continue
            if g[j] > peak_bg:
                peak_bg = g[j]
                peak_idx = j
            if g[j] < trough_bg:
                trough_bg = g[j]
                trough_idx = j

            if direction is None:
                if g[j] - start_bg >= min_excursion:
                    direction = 'rise'
                elif start_bg - g[j] >= min_excursion:
                    direction = 'fall'

            if direction == 'rise' and peak_bg - g[j] >= min_excursion:
                break
            elif direction == 'fall' and g[j] - trough_bg >= min_excursion:
                break
            j += 1

        if direction is None:
            i = j
            continue

        if direction == 'rise':
            end_idx, end_bg = peak_idx, peak_bg
            magnitude = peak_bg - start_bg
        else:
            end_idx, end_bg = trough_idx, trough_bg
            magnitude = start_bg - trough_bg

        duration_steps = end_idx - start_idx
        if duration_steps < 1:
            i = j
            continue

        rate = magnitude / duration_steps

        # Context for classification
        s_mean = float(np.nanmean(supply[start_idx:end_idx + 1]))
        d_mean = float(np.nanmean(demand[start_idx:end_idx + 1]))
        n_mean = float(np.nanmean(net[start_idx:end_idx + 1]))

        carb_window = _carbs[max(0, start_idx - 6):min(N, end_idx + 6)]
        has_carbs = float(np.nansum(carb_window)) > 1.0
        carb_amount = float(np.nansum(carb_window))

        iob_start = float(_iob[start_idx])
        iob_end = float(_iob[min(end_idx, N - 1)])
        iob_delta = iob_end - iob_start
        tod_hour = (start_idx % STEPS_PER_DAY) / STEPS_PER_HOUR

        # Priority-ordered classification
        if direction == 'fall' and end_bg < 70:
            exc_type = ExcursionType.HYPO_ENTRY.value
        elif direction == 'rise' and start_bg < 70:
            exc_type = ExcursionType.HYPO_RECOVERY.value
        elif direction == 'rise' and has_carbs:
            exc_type = ExcursionType.MEAL_RISE.value
        elif direction == 'fall' and iob_delta > 0.5:
            exc_type = ExcursionType.CORRECTION_DROP.value
        elif direction == 'rise' and not has_carbs:
            pre_bg = glucose[max(0, start_idx - 12):start_idx + 1]
            valid_pre = ~np.isnan(pre_bg)
            if valid_pre.sum() >= 2:
                pre_change = float(pre_bg[valid_pre][-1] - pre_bg[valid_pre][0])
                if pre_change < -20:
                    exc_type = ExcursionType.REBOUND_RISE.value
                else:
                    exc_type = ExcursionType.UAM_RISE.value
            else:
                exc_type = ExcursionType.UAM_RISE.value
        elif direction == 'fall':
            pre_bg = glucose[max(0, start_idx - 18):start_idx + 1]
            valid_pre = ~np.isnan(pre_bg)
            if d_mean > s_mean * 0.8 and d_mean > 2.0:
                exc_type = ExcursionType.INSULIN_FALL.value
            elif valid_pre.sum() >= 2 and float(pre_bg[valid_pre][-1] - pre_bg[valid_pre][0]) > 15:
                exc_type = ExcursionType.POST_RISE_FALL.value
            else:
                exc_type = ExcursionType.NATURAL_FALL.value
        else:
            exc_type = f'unclassified_{direction}'

        excursions.append(Excursion(
            start_idx=start_idx, end_idx=end_idx,
            start_bg=float(start_bg), end_bg=float(end_bg),
            direction=direction, magnitude=float(magnitude),
            duration_steps=duration_steps, rate=float(rate),
            excursion_type=exc_type, has_carbs=has_carbs,
            carb_amount=carb_amount, iob_at_start=iob_start,
            iob_delta=iob_delta, supply_mean=s_mean,
            demand_mean=d_mean, net_mean=n_mean, tod_hour=tod_hour,
        ))
        i = end_idx + 1

    return excursions


def detect_cascade_chains(excursions: List[Excursion]) -> CascadeAnalysis:
    """Detect metabolic cascade chains from classified excursions (EXP-1691).

    Cascades are sequences of excursions linked by CASCADE_TRANSITIONS.
    Research finding: 62% of excursions participate in cascades;
    breaking cascade roots reduces downstream excursions.

    Args:
        excursions: chronologically ordered list from detect_excursions().

    Returns:
        CascadeAnalysis with chains, participation rate, and type counts.
    """
    if not excursions:
        return CascadeAnalysis()

    chains: List[CascadeChain] = []
    current_chain = [excursions[0]]

    for i in range(1, len(excursions)):
        prev_type = excursions[i - 1].excursion_type
        curr_type = excursions[i].excursion_type
        if (prev_type, curr_type) in CASCADE_TRANSITIONS:
            current_chain.append(excursions[i])
        else:
            if len(current_chain) >= 2:
                chains.append(_build_chain(current_chain))
            current_chain = [excursions[i]]

    if len(current_chain) >= 2:
        chains.append(_build_chain(current_chain))

    in_chain = sum(c.length for c in chains)
    total = len(excursions)
    isolated = total - in_chain

    type_counts: Dict[str, int] = {}
    for exc in excursions:
        type_counts[exc.excursion_type] = type_counts.get(exc.excursion_type, 0) + 1

    return CascadeAnalysis(
        excursions=excursions,
        chains=chains,
        total_excursions=total,
        in_chain_count=in_chain,
        isolated_count=isolated,
        cascade_participation=in_chain / max(total, 1),
        type_counts=type_counts,
    )


def _build_chain(excursions: List[Excursion]) -> CascadeChain:
    """Build a CascadeChain from a sequence of linked excursions."""
    total_mag = sum(e.magnitude for e in excursions)
    duration = excursions[-1].end_idx - excursions[0].start_idx
    return CascadeChain(
        excursions=excursions,
        length=len(excursions),
        total_magnitude=total_mag,
        duration_steps=duration,
        root_type=excursions[0].excursion_type,
    )


def compute_harmonic_features(hours: np.ndarray,
                              periods: Optional[List[float]] = None,
                              ) -> np.ndarray:
    """Compute 4-harmonic temporal features for use across modules (EXP-1774).

    Replaces single sin/cos pair with 8 features (sin+cos for each period).
    Research: +77% relative R² improvement, all 11 patients benefit.

    Args:
        hours: (N,) fractional hour of day (0-24).
        periods: harmonic periods (default [24, 12, 8, 6] hours).

    Returns:
        (N, 8) array: [sin_24, cos_24, sin_12, cos_12, sin_8, cos_8, sin_6, cos_6].
    """
    if periods is None:
        periods = [24.0, 12.0, 8.0, 6.0]
    h = np.asarray(hours, dtype=np.float64)
    features = np.zeros((len(h), 2 * len(periods)))
    for k, p in enumerate(periods):
        angle = 2.0 * np.pi * h / p
        features[:, 2 * k] = np.sin(angle)
        features[:, 2 * k + 1] = np.cos(angle)
    return features


def detect_changepoints(glucose: np.ndarray,
                        window_size: int = 288,
                        threshold_mult: float = 2.0) -> List[int]:
    """Detect settings changepoints via rolling RMSD analysis.

    Changepoints indicate when a patient's glucose behavior shifts
    significantly — often corresponding to therapy changes (basal,
    ISF, CR adjustments) or lifestyle changes.

    Research finding: changepoint count is bimodal — patients have
    either 0 or 10+ (stable vs volatile phenotypes, EXP-696).

    Args:
        glucose: (N,) glucose values.
        window_size: rolling window size in samples (default 288 = 1 day).
        threshold_mult: RMSD must exceed median × this to flag change.

    Returns:
        List of indices where changepoints are detected.
    """
    valid = np.nan_to_num(glucose, nan=120.0)
    N = len(valid)
    if N < window_size * 2:
        return []

    # Rolling RMSD
    half = window_size // 2
    rmsd_values = np.zeros(N)

    for i in range(half, N - half):
        left = valid[i - half:i]
        right = valid[i:i + half]
        if len(left) > 10 and len(right) > 10:
            rmsd_values[i] = abs(np.std(right) - np.std(left))

    # Find peaks above threshold
    active = rmsd_values[half:N - half]
    if len(active) == 0 or np.median(active) == 0:
        return []

    threshold = np.median(active) + threshold_mult * np.std(active)
    candidates = np.where(rmsd_values > threshold)[0]

    # Merge nearby changepoints (within 1 day)
    if len(candidates) == 0:
        return []

    merged = [int(candidates[0])]
    for idx in candidates[1:]:
        if idx - merged[-1] > 288:  # at least 1 day apart
            merged.append(int(idx))

    return merged


def estimate_isf_by_hour(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState],
                         hours: np.ndarray) -> np.ndarray:
    """Estimate ISF variation across 24 hours.

    Research finding: ISF varies 29.7% mean by time of day.
    Patient c shows 82.2% variation (EXP-765).

    Uses the ratio of glucose change to insulin effect per hour
    to estimate effective ISF at each time of day.

    Args:
        glucose: (N,) glucose values.
        metabolic: MetabolicState for insulin demand.
        hours: (N,) fractional hours.

    Returns:
        (24,) array of relative ISF multipliers by hour (1.0 = average).
    """
    isf_by_hour = np.ones(24)

    if metabolic is None:
        return isf_by_hour

    bg_change = np.zeros(len(glucose))
    bg_change[1:] = np.diff(glucose)

    for hour in range(24):
        mask = (hours.astype(int) % 24 == hour) & np.isfinite(glucose)
        if np.sum(mask) < 6:
            continue

        # ISF proxy: how much does glucose change per unit insulin demand?
        demand_h = metabolic.demand[mask]
        bg_change_h = bg_change[mask]

        # Only use periods with measurable insulin effect
        active = demand_h > 0.1
        if active.sum() < 3:
            continue

        sensitivity = float(np.median(np.abs(bg_change_h[active]) / demand_h[active]))
        isf_by_hour[hour] = sensitivity

    # Normalize to mean = 1.0
    mean_isf = np.mean(isf_by_hour[isf_by_hour > 0])
    if mean_isf > 0:
        isf_by_hour = isf_by_hour / mean_isf

    return isf_by_hour


def classify_phenotype(glucose: np.ndarray,
                       hours: np.ndarray) -> Phenotype:
    """Classify patient into glucose phenotype.

    Phenotypes:
    - MORNING_HIGH: elevated fasting glucose (dawn phenomenon dominant)
    - NIGHT_HYPO: frequent overnight lows
    - STABLE: neither pattern dominant
    """
    valid = np.isfinite(glucose)
    if valid.sum() < 288:  # need at least 1 day
        return Phenotype.STABLE

    # Morning window (5-9 AM)
    morning_mask = valid & (hours >= 5) & (hours < 9)
    morning_bg = glucose[morning_mask] if morning_mask.any() else np.array([120.0])

    # Night window (midnight - 5 AM)
    night_mask = valid & (hours >= 0) & (hours < 5)
    night_bg = glucose[night_mask] if night_mask.any() else np.array([120.0])

    # Daytime for comparison
    day_mask = valid & (hours >= 9) & (hours < 22)
    day_bg = glucose[day_mask] if day_mask.any() else np.array([120.0])

    morning_mean = float(np.mean(morning_bg))
    night_hypo_rate = float(np.mean(night_bg < 70))
    day_mean = float(np.mean(day_bg))

    if morning_mean > day_mean + 20:
        return Phenotype.MORNING_HIGH
    elif night_hypo_rate > 0.05:
        return Phenotype.NIGHT_HYPO
    else:
        return Phenotype.STABLE


def analyze_patterns(glucose: np.ndarray,
                     metabolic: Optional[MetabolicState],
                     hours: np.ndarray) -> PatternProfile:
    """Full pattern analysis pipeline.

    This is the primary API. Requires ≥2 weeks of data for reliable
    changepoint detection; shorter periods still get circadian + phenotype.

    Args:
        glucose: (N,) cleaned glucose values.
        metabolic: MetabolicState from metabolic_engine.
        hours: (N,) fractional hour of day.

    Returns:
        PatternProfile with circadian fit, changepoints, ISF variation,
        weekly trend, and phenotype.
    """
    # Circadian fit (legacy sinusoidal)
    residuals = metabolic.residual if metabolic is not None else np.zeros(len(glucose))
    circadian = fit_circadian(residuals, hours)

    # Multi-harmonic circadian fit (EXP-1631–1638: R²=0.959 vs 0.515)
    harmonic = fit_harmonic_circadian(glucose, hours)

    # Changepoints
    changepoints = detect_changepoints(glucose)

    # ISF variation
    isf_by_hour = estimate_isf_by_hour(glucose, metabolic, hours)
    isf_range = float(np.max(isf_by_hour) - np.min(isf_by_hour))
    isf_mean = float(np.mean(isf_by_hour))
    isf_variation_pct = (isf_range / isf_mean * 100.0) if isf_mean > 0 else 0.0

    # Weekly trend: compare first half vs second half TIR
    mid = len(glucose) // 2
    valid_first = glucose[:mid][np.isfinite(glucose[:mid])]
    valid_second = glucose[mid:][np.isfinite(glucose[mid:])]

    tir_first = float(np.mean((valid_first >= 70) & (valid_first <= 180))) if len(valid_first) > 0 else 0.5
    tir_second = float(np.mean((valid_second >= 70) & (valid_second <= 180))) if len(valid_second) > 0 else 0.5

    delta_tir = tir_second - tir_first
    if delta_tir > 0.05:
        weekly_trend = "improving"
    elif delta_tir < -0.05:
        weekly_trend = "declining"
    else:
        weekly_trend = "stable"

    # Phenotype classification
    phenotype = classify_phenotype(glucose, hours)

    return PatternProfile(
        circadian=circadian,
        changepoints=changepoints,
        n_changepoints=len(changepoints),
        isf_variation_pct=isf_variation_pct,
        isf_by_hour=isf_by_hour,
        weekly_trend=weekly_trend,
        phenotype=phenotype,
        tir_first_half=tir_first,
        tir_second_half=tir_second,
        harmonic=harmonic,
    )
