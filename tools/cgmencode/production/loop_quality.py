"""
loop_quality.py — AID controller quality assessment.

Research basis: EXP-2538 (loop decision quality), EXP-2540 (loop aggression).

Evaluates how well the AID loop manages glucose by analyzing:
1. Hypos the loop caused (increased insulin before hypo)
2. Excursions the loop failed to address (no SMB/bolus action)
3. Overall aggression level relative to glucose level

Key findings from research:
- 35% of hypos are loop-caused (insulin increase before hypo)
- Loop median reaction time is only 5 minutes before hypo
- 55% of >250 excursions get zero SMBs
- Aggression ratio is only 2.2× (vs expected 18× proportional)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .types import LoopQualityResult

# ── Thresholds ────────────────────────────────────────────────────────
HYPO_THRESHOLD = 70.0          # mg/dL
HIGH_THRESHOLD = 250.0         # mg/dL excursion threshold
MIN_EPISODE_LEN = 3            # consecutive readings to form an episode
LOOKBACK_STEPS = 6             # 30 min at 5-min intervals
BASAL_INCREASE_FACTOR = 1.1    # >110% of scheduled → loop increased
BASAL_REDUCE_FACTOR = 0.5      # <50% of scheduled → loop reducing
BOLUS_MIN_DOSE = 0.1           # U — minimum to count as addressed
MIN_DAYS = 3.0                 # minimum data for reliable assessment
STEP_MINUTES = 5.0             # assumed interval between readings


def _find_episodes(glucose: np.ndarray, threshold: float,
                   above: bool) -> list[int]:
    """Find episode start indices where glucose crosses threshold.

    An episode is ≥MIN_EPISODE_LEN consecutive readings beyond threshold.

    Args:
        glucose: glucose array (may contain NaN).
        threshold: mg/dL boundary.
        above: if True, find episodes above threshold; else below.

    Returns:
        List of start indices for each episode.
    """
    n = len(glucose)
    if n < MIN_EPISODE_LEN:
        return []

    if above:
        mask = glucose > threshold
    else:
        mask = glucose < threshold

    # Treat NaN as not meeting the condition
    mask = mask & ~np.isnan(glucose)

    episodes: list[int] = []
    run = 0
    start = 0
    for i in range(n):
        if mask[i]:
            if run == 0:
                start = i
            run += 1
            if run == MIN_EPISODE_LEN:
                episodes.append(start)
        else:
            run = 0

    return episodes


def _analyze_hypos(
    glucose: np.ndarray,
    basal_rate: Optional[np.ndarray],
    bolus: Optional[np.ndarray],
    scheduled_basal: float,
) -> tuple[int, int, list[float]]:
    """Classify hypo episodes as loop-caused or not.

    Returns:
        (total_hypos, loop_caused_count, reaction_times_in_minutes)
    """
    hypo_starts = _find_episodes(glucose, HYPO_THRESHOLD, above=False)
    total = len(hypo_starts)
    if total == 0:
        return 0, 0, []

    loop_caused = 0
    reaction_times: list[float] = []

    for start in hypo_starts:
        win_begin = max(0, start - LOOKBACK_STEPS)
        win_end = start

        caused = False

        # Check if loop increased basal before hypo
        if basal_rate is not None and win_end > win_begin:
            window_basal = basal_rate[win_begin:win_end]
            valid_basal = window_basal[~np.isnan(window_basal)]
            if len(valid_basal) > 0:
                if float(np.max(valid_basal)) > scheduled_basal * BASAL_INCREASE_FACTOR:
                    caused = True

        # Check if loop delivered a bolus before hypo
        if not caused and bolus is not None and win_end > win_begin:
            window_bolus = bolus[win_begin:win_end]
            valid_bolus = window_bolus[~np.isnan(window_bolus)]
            if len(valid_bolus) > 0 and float(np.sum(valid_bolus)) > BOLUS_MIN_DOSE:
                caused = True

        if caused:
            loop_caused += 1

        # Compute reaction time: how many steps before hypo did loop
        # start reducing basal below scheduled?
        if basal_rate is not None and win_end > win_begin:
            window_basal = basal_rate[win_begin:win_end]
            reaction_step = None
            # Walk backwards from hypo start
            for offset in range(len(window_basal)):
                idx = len(window_basal) - 1 - offset
                val = window_basal[idx]
                if np.isnan(val):
                    continue
                if val < scheduled_basal * BASAL_REDUCE_FACTOR:
                    reaction_step = offset
                else:
                    break
            if reaction_step is not None:
                reaction_times.append(reaction_step * STEP_MINUTES)

    return total, loop_caused, reaction_times


def _analyze_excursions(
    glucose: np.ndarray,
    bolus: Optional[np.ndarray],
) -> tuple[int, int]:
    """Count high excursions and how many lacked bolus/SMB response.

    Returns:
        (total_excursions, unaddressed_count)
    """
    exc_starts = _find_episodes(glucose, HIGH_THRESHOLD, above=True)
    total = len(exc_starts)
    if total == 0:
        return 0, 0

    if bolus is None:
        # Cannot assess without bolus data — assume all unaddressed
        return total, total

    unaddressed = 0
    n = len(glucose)
    for start in exc_starts:
        win_begin = max(0, start - LOOKBACK_STEPS)
        win_end = min(n, start + LOOKBACK_STEPS + 1)
        window_bolus = bolus[win_begin:win_end]
        valid_bolus = window_bolus[~np.isnan(window_bolus)]
        if len(valid_bolus) == 0 or float(np.sum(valid_bolus)) < BOLUS_MIN_DOSE:
            unaddressed += 1

    return total, unaddressed


def _compute_aggression(
    glucose: np.ndarray,
    basal_rate: Optional[np.ndarray],
    iob: Optional[np.ndarray],
) -> float:
    """Compute aggression ratio: mean insulin at >200 vs 70-120 mg/dL.

    Falls back to IOB-based proxy if basal_rate is not available.

    Returns:
        Aggression ratio (1.0 means no difference).
    """
    if basal_rate is not None:
        signal = basal_rate
    elif iob is not None:
        signal = iob
    else:
        return 1.0

    valid = ~np.isnan(glucose) & ~np.isnan(signal)
    high_mask = valid & (glucose > 200.0)
    low_mask = valid & (glucose >= 70.0) & (glucose <= 120.0)

    high_count = int(np.sum(high_mask))
    low_count = int(np.sum(low_mask))

    if high_count < 3 or low_count < 3:
        return 1.0

    high_mean = float(np.mean(signal[high_mask]))
    low_mean = float(np.mean(signal[low_mask]))

    return high_mean / max(low_mean, 0.01)


def _grade(loop_caused_frac: float, unaddressed_frac: float) -> str:
    """Assign overall quality grade."""
    if loop_caused_frac < 0.20 and unaddressed_frac < 0.30:
        return "good"
    if loop_caused_frac < 0.40 and unaddressed_frac < 0.60:
        return "fair"
    return "poor"


def _build_evidence(
    hypo_episodes: int,
    loop_caused: int,
    loop_caused_frac: float,
    median_rt: float,
    high_exc: int,
    unaddressed: int,
    unaddressed_frac: float,
    aggression: float,
    grade: str,
) -> str:
    """Generate human-readable summary."""
    parts: list[str] = []

    if hypo_episodes > 0:
        parts.append(
            f"{loop_caused}/{hypo_episodes} hypos ({loop_caused_frac:.0%}) "
            f"preceded by loop insulin increase"
        )
        if median_rt > 0:
            parts.append(f"median reaction time {median_rt:.0f} min before hypo")
    else:
        parts.append("No hypo episodes detected")

    if high_exc > 0:
        parts.append(
            f"{unaddressed}/{high_exc} excursions >250 ({unaddressed_frac:.0%}) "
            f"had no bolus/SMB within ±30 min"
        )
    else:
        parts.append("No prolonged excursions >250 mg/dL")

    parts.append(f"Aggression ratio {aggression:.1f}× (high-glucose vs in-range basal)")
    parts.append(f"Overall grade: {grade}")

    return ". ".join(parts) + "."


def assess_loop_quality(
    glucose: np.ndarray,
    hours: np.ndarray,
    basal_rate: Optional[np.ndarray] = None,
    bolus: Optional[np.ndarray] = None,
    iob: Optional[np.ndarray] = None,
    scheduled_basal: float = 0.0,
    days_of_data: float = 0.0,
) -> Optional[LoopQualityResult]:
    """Assess AID controller quality from glucose and insulin data.

    Args:
        glucose: cleaned glucose array (mg/dL), 5-min intervals.
        hours: fractional hours corresponding to glucose readings.
        basal_rate: actual basal rate delivered (U/hr), same length as glucose.
        bolus: bolus insulin delivered (U), same length as glucose.
        iob: insulin-on-board (U), same length as glucose. Used as
             fallback for aggression if basal_rate unavailable.
        scheduled_basal: median scheduled basal rate from profile (U/hr).
        days_of_data: total days of glucose data.

    Returns:
        LoopQualityResult or None if insufficient data.
    """
    if days_of_data < MIN_DAYS:
        return None

    n = len(glucose)
    if n < MIN_EPISODE_LEN:
        return None

    # Ensure arrays match glucose length
    if basal_rate is not None and len(basal_rate) != n:
        basal_rate = None
    if bolus is not None and len(bolus) != n:
        bolus = None
    if iob is not None and len(iob) != n:
        iob = None

    # Use a small positive default if scheduled_basal is zero/missing
    if scheduled_basal <= 0:
        if basal_rate is not None:
            valid_br = basal_rate[~np.isnan(basal_rate)]
            scheduled_basal = float(np.median(valid_br)) if len(valid_br) > 0 else 0.8
        else:
            scheduled_basal = 0.8

    # ── Hypo analysis ─────────────────────────────────────────────
    hypo_episodes, loop_caused, reaction_times = _analyze_hypos(
        glucose, basal_rate, bolus, scheduled_basal)

    if hypo_episodes > 0:
        loop_caused_frac = loop_caused / hypo_episodes
    else:
        loop_caused_frac = 0.0

    if reaction_times:
        median_rt = float(np.median(reaction_times))
    else:
        median_rt = 0.0

    # ── Excursion analysis ────────────────────────────────────────
    high_exc, unaddressed = _analyze_excursions(glucose, bolus)

    if high_exc > 0:
        unaddressed_frac = unaddressed / high_exc
    else:
        unaddressed_frac = 0.0

    # ── Aggression analysis ───────────────────────────────────────
    aggression = _compute_aggression(glucose, basal_rate, iob)

    # ── Grade and evidence ────────────────────────────────────────
    grade = _grade(loop_caused_frac, unaddressed_frac)
    evidence = _build_evidence(
        hypo_episodes, loop_caused, loop_caused_frac,
        median_rt, high_exc, unaddressed, unaddressed_frac,
        aggression, grade,
    )

    return LoopQualityResult(
        hypo_episodes=hypo_episodes,
        loop_caused_hypos=loop_caused,
        loop_caused_fraction=loop_caused_frac,
        median_reaction_time_min=median_rt,
        high_excursions=high_exc,
        unaddressed_excursions=unaddressed,
        unaddressed_fraction=unaddressed_frac,
        aggression_ratio=aggression,
        overall_grade=grade,
        evidence=evidence,
    )
