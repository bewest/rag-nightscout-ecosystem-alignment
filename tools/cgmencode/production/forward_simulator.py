"""
forward_simulator.py — Physics-based forward glucose simulation (digital twin).

Research basis: Combines all validated physics components:
  - Two-component DIA (EXP-2525/2534): fast τ=0.8h + persistent 37%
  - Power-law ISF for corrections (EXP-2511): β=0.9
  - Carb absorption: linear model over absorption window
  - Mean reversion toward ~120 mg/dL equilibrium

Model architecture (basal neutrality):
  The patient's basal rate defines metabolic equilibrium. At the correct
  basal, fasting glucose stays flat. All effects are RELATIVE to this:

    dBG = -excess_insulin_effect × ISF
          + carb_rise × (ISF / CR)
          + decay_toward_120
          + noise

  Where excess_insulin = total absorption - scheduled_basal_absorption.
  This avoids double-counting supply/demand and naturally produces:
    - Flat glucose at correct basal (zero excess)
    - Glucose drop from correction bolus proportional to ISF
    - Glucose rise from missed basal proportional to ISF
    - Post-meal rise proportional to ISF/CR

  Two-component split: excess insulin effect is 63% fast (τ=0.8h)
  and 37% persistent (τ=12h, validated EXP-2525/2534).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .metabolic_engine import (
    _FAST_TAU_HOURS,
    _PERSISTENT_FRACTION,
    _PERSISTENT_WINDOW_HOURS,
    _DECAY_TARGET,
    _DECAY_RATE,
)


# ── Constants ─────────────────────────────────────────────────────────

_STEP_MINUTES = 5.0
_STEPS_PER_HOUR = 60.0 / _STEP_MINUTES  # 12
_FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION  # 0.63
_POWER_LAW_BETA = 0.9  # from EXP-2511 (causal validation, 17/17 patients)

# Insulin activity curve parameters
_DEFAULT_DIA_HOURS = 5.0

# Carb absorption
_DEFAULT_CARB_ABSORPTION_HOURS = 3.0
_MIN_BG = 39.0
_MAX_BG = 401.0


# ── Data Contracts ────────────────────────────────────────────────────

@dataclass
class InsulinEvent:
    """A single insulin delivery event."""
    time_minutes: float  # minutes from simulation start
    units: float         # insulin units
    is_bolus: bool = True  # True=bolus, False=basal segment


@dataclass
class CarbEvent:
    """A single carb intake event."""
    time_minutes: float  # minutes from simulation start
    grams: float         # grams of carbohydrate
    absorption_hours: float = _DEFAULT_CARB_ABSORPTION_HOURS


@dataclass
class TherapySettings:
    """Therapy settings for simulation.

    All schedules are lists of (hour, value) tuples sorted by hour.
    Single values are treated as flat schedules.
    """
    isf: float = 50.0   # mg/dL per Unit (can be overridden by schedule)
    cr: float = 10.0    # grams per Unit
    basal_rate: float = 0.8  # U/hr (default flat rate)
    dia_hours: float = _DEFAULT_DIA_HOURS

    # Circadian schedules: list of (hour, value). If empty, use flat value.
    isf_schedule: List[Tuple[float, float]] = field(default_factory=list)
    cr_schedule: List[Tuple[float, float]] = field(default_factory=list)
    basal_schedule: List[Tuple[float, float]] = field(default_factory=list)

    def isf_at_hour(self, hour: float) -> float:
        return _schedule_value_at(self.isf_schedule, hour, self.isf)

    def cr_at_hour(self, hour: float) -> float:
        return _schedule_value_at(self.cr_schedule, hour, self.cr)

    def basal_at_hour(self, hour: float) -> float:
        return _schedule_value_at(self.basal_schedule, hour, self.basal_rate)


@dataclass
class SimulationResult:
    """Output from forward simulation."""
    glucose: np.ndarray        # (N,) simulated glucose trace, mg/dL
    iob: np.ndarray            # (N,) insulin on board
    cob: np.ndarray            # (N,) carbs on board
    supply: np.ndarray         # (N,) supply flux per step
    demand: np.ndarray         # (N,) demand flux per step
    timestamps_min: np.ndarray  # (N,) minutes from start
    hours_of_day: np.ndarray   # (N,) fractional hour (0-24)

    @property
    def n_steps(self) -> int:
        return len(self.glucose)

    @property
    def duration_hours(self) -> float:
        return self.n_steps * _STEP_MINUTES / 60.0

    @property
    def tir(self) -> float:
        """Time in range (70-180 mg/dL) as fraction 0-1."""
        valid = self.glucose[np.isfinite(self.glucose)]
        if len(valid) == 0:
            return 0.0
        return float(np.mean((valid >= 70) & (valid <= 180)))

    @property
    def tbr(self) -> float:
        """Time below range (<70 mg/dL) as fraction 0-1."""
        valid = self.glucose[np.isfinite(self.glucose)]
        if len(valid) == 0:
            return 0.0
        return float(np.mean(valid < 70))

    @property
    def tar(self) -> float:
        """Time above range (>180 mg/dL) as fraction 0-1."""
        valid = self.glucose[np.isfinite(self.glucose)]
        if len(valid) == 0:
            return 0.0
        return float(np.mean(valid > 180))

    @property
    def mean_glucose(self) -> float:
        valid = self.glucose[np.isfinite(self.glucose)]
        return float(np.mean(valid)) if len(valid) > 0 else 120.0

    @property
    def cv(self) -> float:
        """Coefficient of variation."""
        valid = self.glucose[np.isfinite(self.glucose)]
        if len(valid) == 0 or np.mean(valid) < 1:
            return 0.0
        return float(np.std(valid) / np.mean(valid))

    def summary(self) -> Dict:
        return {
            'duration_hours': round(self.duration_hours, 1),
            'tir': round(self.tir * 100, 1),
            'tbr': round(self.tbr * 100, 1),
            'tar': round(self.tar * 100, 1),
            'mean_glucose': round(self.mean_glucose, 1),
            'cv': round(self.cv * 100, 1),
        }


@dataclass
class ScenarioComparison:
    """Side-by-side comparison of two simulation scenarios."""
    baseline: SimulationResult
    modified: SimulationResult
    baseline_label: str = "Baseline"
    modified_label: str = "Modified"

    @property
    def tir_delta(self) -> float:
        """TIR improvement (positive = better)."""
        return self.modified.tir - self.baseline.tir

    @property
    def tbr_delta(self) -> float:
        """TBR change (negative = improvement)."""
        return self.modified.tbr - self.baseline.tbr

    def summary(self) -> Dict:
        return {
            'baseline': self.baseline.summary(),
            'modified': self.modified.summary(),
            'tir_delta_pp': round(self.tir_delta * 100, 1),
            'tbr_delta_pp': round(self.tbr_delta * 100, 1),
            'baseline_label': self.baseline_label,
            'modified_label': self.modified_label,
        }


# ── Utility Functions ─────────────────────────────────────────────────

def _schedule_value_at(schedule: List[Tuple[float, float]],
                       hour: float, default: float) -> float:
    """Look up value from a sorted (hour, value) schedule."""
    if not schedule:
        return default
    # Find the last entry whose hour <= target hour
    result = default
    for h, v in schedule:
        if h <= hour:
            result = v
        else:
            break
    # Handle wrap-around: if hour < first entry, use last entry
    if hour < schedule[0][0]:
        result = schedule[-1][1]
    return result


def _insulin_activity_curve(t_minutes: float, dia_hours: float) -> float:
    """Fraction of insulin still active at time t after delivery.

    Uses the exponential decay model calibrated to the pump's DIA setting.
    At t=0: 1.0. At t=DIA: ~0.05 (5% remaining).
    """
    if t_minutes <= 0:
        return 1.0
    dia_min = dia_hours * 60.0
    if t_minutes >= dia_min:
        return 0.0
    # Exponential decay: IOB(t) = exp(-3 * t / DIA)
    # Factor 3 chosen so that e^-3 ≈ 0.05 at t=DIA
    return float(np.exp(-3.0 * t_minutes / dia_min))


def _carb_absorption_rate(t_minutes: float,
                          total_grams: float,
                          absorption_hours: float) -> float:
    """Grams of carbs absorbed in current 5-min step.

    Linear absorption model: constant rate over absorption window.
    Returns grams absorbed in this single step.
    """
    abs_minutes = absorption_hours * 60.0
    if t_minutes < 0 or t_minutes >= abs_minutes or total_grams <= 0:
        return 0.0
    # Constant absorption rate
    rate_per_min = total_grams / abs_minutes
    return rate_per_min * _STEP_MINUTES


# ── Forward Simulation Engine ─────────────────────────────────────────

def forward_simulate(
    initial_glucose: float,
    settings: TherapySettings,
    duration_hours: float = 24.0,
    start_hour: float = 0.0,
    bolus_events: Optional[List[InsulinEvent]] = None,
    carb_events: Optional[List[CarbEvent]] = None,
    initial_iob: float = 0.0,
    noise_std: float = 0.0,
    seed: Optional[int] = None,
    metabolic_basal_rate: Optional[float] = None,
) -> SimulationResult:
    """Run forward glucose simulation from initial conditions.

    This is the core digital twin engine. Given therapy settings and
    insulin/carb schedules, it generates a complete glucose trajectory
    using the validated physics model.

    The model uses **basal neutrality**: the metabolic_basal_rate defines
    the insulin rate that keeps fasting glucose flat. Any insulin above
    or below that rate produces glucose changes proportional to ISF.

    Args:
        initial_glucose: Starting glucose (mg/dL).
        settings: TherapySettings with ISF, CR, basal, DIA.
        duration_hours: Simulation length in hours (default 24h).
        start_hour: Hour of day at simulation start (0-24, for circadian).
        bolus_events: List of bolus insulin events.
        carb_events: List of carb intake events.
        initial_iob: Starting IOB (Units), e.g., from prior basal.
        noise_std: Gaussian noise σ per step (mg/dL), 0=deterministic.
        seed: Random seed for reproducibility.
        metabolic_basal_rate: Patient's true metabolic basal need (U/hr).
            If None, defaults to settings.basal_rate (assuming current
            settings are correct). Set this to compare different basal
            rates against the same patient physiology.

    Returns:
        SimulationResult with glucose, IOB, COB, supply, demand traces.
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random.RandomState()

    n_steps = int(duration_hours * _STEPS_PER_HOUR)
    bolus_events = bolus_events or []
    carb_events = carb_events or []

    # Pre-allocate arrays
    glucose = np.zeros(n_steps)
    iob_trace = np.zeros(n_steps)
    cob_trace = np.zeros(n_steps)
    supply_trace = np.zeros(n_steps)  # carb-driven glucose rise
    demand_trace = np.zeros(n_steps)  # insulin-driven glucose drop
    timestamps_min = np.arange(n_steps) * _STEP_MINUTES
    hours_of_day = (start_hour + timestamps_min / 60.0) % 24.0

    # Build per-step insulin delivery array (basal + bolus)
    insulin_per_step = np.zeros(n_steps)
    # Reference basal: the metabolic need (neutral point)
    met_basal = metabolic_basal_rate if metabolic_basal_rate is not None else settings.basal_rate
    basal_need_per_step = np.zeros(n_steps)  # metabolic need (for neutrality)

    for i in range(n_steps):
        hour = hours_of_day[i]
        basal_delivery = settings.basal_at_hour(hour) * _STEP_MINUTES / 60.0
        insulin_per_step[i] = basal_delivery
        basal_need_per_step[i] = met_basal * _STEP_MINUTES / 60.0

    for event in bolus_events:
        step_idx = int(event.time_minutes / _STEP_MINUTES)
        if 0 <= step_idx < n_steps:
            insulin_per_step[step_idx] += event.units

    # Pre-compute the insulin activity curve values for efficiency
    max_lookback = min(n_steps, int(settings.dia_hours * _STEPS_PER_HOUR) + 1)
    activity_values = np.array([
        _insulin_activity_curve(k * _STEP_MINUTES, settings.dia_hours)
        for k in range(max_lookback + 1)
    ])
    # Absorption fraction per step: activity[k] - activity[k+1]
    absorption_fractions = np.diff(activity_values)  # negative (activity decreases)
    absorption_fractions = -absorption_fractions  # make positive

    # Initialize
    glucose[0] = initial_glucose
    iob_trace[0] = initial_iob

    # ── Main integration loop ─────────────────────────────────────
    # Model: dBG = -excess_insulin_effect + carb_rise + decay
    # Where excess = total absorption - scheduled_basal_absorption
    # At correct basal with no meals/boluses: dBG ≈ decay only

    for t in range(1, n_steps):
        t_min = t * _STEP_MINUTES
        hour = hours_of_day[t]
        isf_at_t = settings.isf_at_hour(hour)
        cr_at_t = settings.cr_at_hour(hour)

        # ── Insulin absorption: total and basal-only ──────────────
        total_absorption = 0.0
        basal_absorption = 0.0
        iob = 0.0

        lookback = min(t, max_lookback - 1)
        for k in range(lookback + 1):
            j = t - k  # delivery step
            if j >= 0:
                frac = absorption_fractions[k] if k < len(absorption_fractions) else 0.0
                total_absorption += insulin_per_step[j] * frac
                basal_absorption += basal_need_per_step[j] * frac
                iob += insulin_per_step[j] * activity_values[k]

        # Add initial IOB contribution
        if initial_iob > 0 and t < max_lookback:
            iob += initial_iob * activity_values[t]
            if t > 0 and t < len(absorption_fractions):
                total_absorption += initial_iob * absorption_fractions[t]

        iob_trace[t] = max(iob, 0.0)

        # Excess insulin = total - basal (positive → glucose lowering)
        excess_absorption = total_absorption - basal_absorption

        # ── Fast demand: excess absorption × ISF × fast fraction ──
        demand_fast = excess_absorption * isf_at_t * _FAST_FRACTION

        # ── Persistent demand: cumulative excess in 12h window ────
        # The persistent component represents the "extra" glucose
        # lowering from insulin that persists beyond the IOB curve.
        # At basal, this is zero (no excess). After boluses, it adds
        # a sustained glucose-lowering tail.
        persistent_window = int(_PERSISTENT_WINDOW_HOURS * _STEPS_PER_HOUR)
        start_step = max(0, t - persistent_window)
        total_excess_12h = float(
            np.sum(insulin_per_step[start_step:t + 1])
            - np.sum(basal_need_per_step[start_step:t + 1])
        )
        if total_excess_12h > 0.01:
            persistent_demand = (total_excess_12h * isf_at_t
                                 / persistent_window * _PERSISTENT_FRACTION)
        else:
            persistent_demand = 0.0

        total_demand = demand_fast + persistent_demand
        demand_trace[t] = total_demand

        # ── Carb absorption → glucose rise ────────────────────────
        carb_absorbed = 0.0
        cob = 0.0
        for event in carb_events:
            elapsed = t_min - event.time_minutes
            if elapsed < 0:
                continue
            abs_min = event.absorption_hours * 60.0
            remaining_frac = max(0.0, 1.0 - elapsed / abs_min)
            cob += event.grams * remaining_frac
            carb_absorbed += _carb_absorption_rate(
                elapsed, event.grams, event.absorption_hours
            )
        cob_trace[t] = cob

        # Carb rise: grams absorbed / CR → units equivalent → × ISF
        carb_rise = (carb_absorbed / max(cr_at_t, 1.0)) * isf_at_t
        supply_trace[t] = carb_rise

        # ── Decay toward equilibrium ──────────────────────────────
        decay = (_DECAY_TARGET - glucose[t - 1]) * _DECAY_RATE

        # ── Integrate ─────────────────────────────────────────────
        dBG = -total_demand + carb_rise + decay
        if noise_std > 0:
            dBG += rng.normal(0, noise_std)

        glucose[t] = np.clip(glucose[t - 1] + dBG, _MIN_BG, _MAX_BG)

    return SimulationResult(
        glucose=glucose,
        iob=iob_trace,
        cob=cob_trace,
        supply=supply_trace,
        demand=demand_trace,
        timestamps_min=timestamps_min,
        hours_of_day=hours_of_day,
    )


# ── Scenario Comparison ──────────────────────────────────────────────

def compare_scenarios(
    initial_glucose: float,
    baseline_settings: TherapySettings,
    modified_settings: TherapySettings,
    duration_hours: float = 24.0,
    start_hour: float = 0.0,
    bolus_events: Optional[List[InsulinEvent]] = None,
    carb_events: Optional[List[CarbEvent]] = None,
    initial_iob: float = 0.0,
    seed: int = 42,
    baseline_label: str = "Baseline",
    modified_label: str = "Modified",
    metabolic_basal_rate: Optional[float] = None,
) -> ScenarioComparison:
    """Simulate two scenarios side-by-side for comparison.

    Same meals/boluses, different settings. This is the core
    "what if I changed my ISF?" question.

    The metabolic_basal_rate defines the patient's true basal need —
    both scenarios are compared against this same reference. If not
    provided, defaults to baseline_settings.basal_rate.

    Args:
        initial_glucose: Starting BG for both scenarios.
        baseline_settings: Current therapy settings.
        modified_settings: Proposed therapy settings.
        duration_hours: Length of simulation.
        start_hour: Hour of day at start.
        bolus_events: Shared insulin events (boluses only; basal from settings).
        carb_events: Shared carb events.
        initial_iob: Starting IOB.
        seed: Random seed (same noise for both).
        baseline_label: Label for baseline scenario.
        modified_label: Label for modified scenario.
        metabolic_basal_rate: Patient's true basal need. Both scenarios
            use this same reference for neutrality.

    Returns:
        ScenarioComparison with both results and deltas.
    """
    met_basal = metabolic_basal_rate or baseline_settings.basal_rate

    baseline = forward_simulate(
        initial_glucose=initial_glucose,
        settings=baseline_settings,
        duration_hours=duration_hours,
        start_hour=start_hour,
        bolus_events=bolus_events,
        carb_events=carb_events,
        initial_iob=initial_iob,
        seed=seed,
        metabolic_basal_rate=met_basal,
    )

    modified = forward_simulate(
        initial_glucose=initial_glucose,
        settings=modified_settings,
        duration_hours=duration_hours,
        start_hour=start_hour,
        bolus_events=bolus_events,
        carb_events=carb_events,
        initial_iob=initial_iob,
        seed=seed,
        metabolic_basal_rate=met_basal,
    )

    return ScenarioComparison(
        baseline=baseline,
        modified=modified,
        baseline_label=baseline_label,
        modified_label=modified_label,
    )


# ── Convenience: Replay Patient Day ──────────────────────────────────

def simulate_typical_day(
    settings: TherapySettings,
    meals: Optional[List[Tuple[float, float]]] = None,
    start_glucose: float = 120.0,
    seed: int = 42,
) -> SimulationResult:
    """Simulate a typical day with standard meals.

    If no meals provided, uses a standard 3-meal pattern:
    - Breakfast: 7:00, 45g carbs
    - Lunch: 12:00, 60g carbs
    - Dinner: 18:30, 55g carbs

    Boluses are auto-calculated from CR at meal time.

    Args:
        settings: Therapy settings.
        meals: List of (hour, grams) meal definitions.
        start_glucose: Starting BG (default 120).
        seed: Random seed.

    Returns:
        SimulationResult for 24h simulation.
    """
    if meals is None:
        meals = [
            (7.0, 45.0),    # Breakfast
            (12.0, 60.0),   # Lunch
            (18.5, 55.0),   # Dinner
        ]

    carb_events = []
    bolus_events = []
    for hour, grams in meals:
        t_min = hour * 60.0
        carb_events.append(CarbEvent(time_minutes=t_min, grams=grams))
        # Auto-bolus based on CR at meal time
        cr = settings.cr_at_hour(hour)
        bolus_units = grams / max(cr, 1.0)
        bolus_events.append(InsulinEvent(time_minutes=t_min, units=bolus_units))

    return forward_simulate(
        initial_glucose=start_glucose,
        settings=settings,
        duration_hours=24.0,
        start_hour=0.0,
        bolus_events=bolus_events,
        carb_events=carb_events,
        seed=seed,
    )
