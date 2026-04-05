"""
continuous_pk.py — Continuous pharmacokinetic state channels for CGM/AID modeling.

Converts sparse treatment events (bolus, carbs, basal) into dense continuous
physiological state signals at 5-min resolution, guided by the UVA/Padova
compartment model and oref0 insulin activity curves.

Design philosophy: The AID pump delivers insulin continuously via three
mechanisms — scheduled basal (maintaining metabolic equilibrium), temp basal
adjustments (AID corrections), and boluses (meal/correction). ALL three are
real insulin creating real absorption and activity. The open source community
(oref0, Loop, AAPS) models this as:

  total_activity = scheduled_basal_activity + temp_deviation_activity + bolus_activity

When the pump suspends (0 U/hr), that's not "zero insulin" — it's a DEFICIT
relative to what the body needs. Activity from prior scheduled doses continues
to decay over DIA hours, so a 1-hour suspension only reduces activity to ~65%
of baseline.

Normalization: Insulin can be expressed as:
  - Absolute: U/min (what we compute)
  - TDD-relative: activity / (TDD / 1440) = fraction of daily average
  - Basal-relative: actual_rate / scheduled_rate (1.0=nominal, 0=suspended)

EXP-348: Validate that continuous PK channels correlate with glucose dynamics.

Usage:
    from tools.cgmencode.continuous_pk import build_continuous_pk_features

    pk_channels = build_continuous_pk_features(df)
    # pk_channels is (N, 8) normalized array

References:
    - UVA/Padova T1DMS: externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts
    - oref0 IOB/net basal: externals/oref0/lib/iob/total.js (netbasalinsulin)
    - Loop BasalRelativeDose: externals/LoopAlgorithm/.../Insulin/RelativeDelivery.swift
    - oref0 exponential model: externals/oref0/lib/iob/calculate.js
    - cgmsim-lib insulin activity: externals/cgmsim-lib/src/utils.ts
    - cgmsim-lib liver model: externals/cgmsim-lib/src/liver.ts
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional


# ── Insulin Activity Curve (oref0/cgmsim-lib exponential model) ────────

def _insulin_activity_at_t(t_min: float, dose: float, dia_min: float,
                            peak_min: float) -> float:
    """Single-dose insulin activity at time t_min after injection.

    Implements the oref0/cgmsim-lib exponential insulin activity curve:
      a(t) = dose * (norm / tau²) * t * (1 - t/DIA) * exp(-t/tau)

    where tau = peak * (1 - peak/DIA) / (1 - 2*peak/DIA)
    and norm ensures integral over [0, DIA] = dose.

    This models the two-compartment subcutaneous absorption (Isc1 → Isc2 → plasma)
    from UVA/Padova as a single analytic curve.

    Args:
        t_min: Minutes since injection
        dose: Insulin dose in units
        dia_min: Duration of insulin action in minutes
        peak_min: Time to peak activity in minutes

    Returns:
        Insulin activity in U/min at time t_min
    """
    if t_min <= 0 or t_min >= dia_min or dose <= 0:
        return 0.0

    tau = peak_min * (1 - peak_min / dia_min) / (1 - 2 * peak_min / dia_min)
    if tau <= 0:
        return 0.0

    scale_factor = (2 * tau) / dia_min
    norm = 1.0 / (1 - scale_factor + (1 + scale_factor) * np.exp(-dia_min / tau))

    activity = dose * (norm / (tau * tau)) * t_min * (1 - t_min / dia_min) * np.exp(-t_min / tau)

    # Ramp up in first 15 minutes (injection site delay)
    if t_min < 15:
        activity *= t_min / 15.0

    return max(activity, 0.0)


def _build_activity_kernel(dia_hours: float = 5.0, peak_min: float = 55.0,
                           interval_min: int = 5) -> np.ndarray:
    """Pre-compute the insulin activity kernel for convolution.

    The kernel represents the activity curve for a 1-unit dose, sampled at
    interval_min resolution. This is computed once and reused for all doses
    via convolution, avoiding the O(N × DIA_steps) nested loop.

    Returns:
        (K,) array where K = DIA / interval_min, representing activity per
        unit dose at each time offset.
    """
    dia_min = dia_hours * 60
    K = int(dia_min / interval_min)
    kernel = np.zeros(K)
    for k in range(K):
        t_min = (k + 1) * interval_min  # +1 because activity at t=0 is 0
        kernel[k] = _insulin_activity_at_t(t_min, 1.0, dia_min, peak_min)
    return kernel


def _convolve_doses_with_kernel(dose_series: np.ndarray,
                                 kernel: np.ndarray) -> np.ndarray:
    """Convolve a sparse dose time series with the activity kernel.

    Each nonzero entry in dose_series creates a scaled copy of the kernel
    extending forward in time. This is equivalent to the nested loop but
    uses numpy for efficiency.

    Args:
        dose_series: (N,) array of doses at each timestep (most are 0)
        kernel: (K,) activity-per-unit kernel from _build_activity_kernel

    Returns:
        (N,) array of total activity at each timestep
    """
    N = len(dose_series)
    K = len(kernel)
    activity = np.zeros(N)

    # Sparse iteration: only process nonzero doses
    nonzero_idx = np.nonzero(dose_series)[0]
    for i in nonzero_idx:
        dose = dose_series[i]
        end = min(i + K, N)
        length = end - i
        activity[i:end] += dose * kernel[:length]

    return activity


def compute_insulin_activity(bolus_series: pd.Series,
                              actual_basal_series: pd.Series,
                              scheduled_basal_array: np.ndarray,
                              dia_hours: float = 5.0, peak_min: float = 55.0,
                              interval_min: int = 5) -> dict:
    """Compute continuous insulin activity from ALL insulin delivery sources.

    Models insulin exactly as Loop does: every micro-dose of actual delivery
    (scheduled basal + temp adjustment + bolus) creates its own absorption
    curve. The scheduled basal maintains a steady-state activity floor;
    temp basals and boluses perturb above/below.

    Returns a dict with decomposed signals:
      - 'total':     Activity from all insulin (scheduled + temp + bolus)
      - 'net':       Activity from deviations only (temp deviation + bolus)
                     This is what drives dBG/dt (scheduled = equilibrium)
      - 'basal_steady_state': The equilibrium activity from scheduled basal
      - 'bolus_only': Activity from boluses alone
      - 'basal_ratio': actual_rate / scheduled_rate at each timestep
                       (1.0 = nominal, 0 = suspended, >1 = high temp)

    The open source AID community insight: receiving 100% of scheduled basal
    means the body gets its needed insulin to maintain glucose homeostasis.
    Suspension (0%) creates a "net negative" — not zero activity, but a
    growing deficit as scheduled activity decays without replenishment.

    Args:
        bolus_series: Series of bolus doses (U) with DatetimeIndex
        actual_basal_series: Series of ACTUAL basal rates (U/hr) — includes
            temp basals, suspensions, overrides. Use temp_rate after ffill.
        scheduled_basal_array: (N,) array of SCHEDULED basal rates (U/hr)
            from the patient's basal profile, expanded per timestep.
        dia_hours: Duration of insulin action in hours
        peak_min: Time to peak activity in minutes
        interval_min: Grid interval in minutes

    Returns:
        Dict with 'total', 'net', 'basal_steady_state', 'bolus_only',
        'basal_ratio' arrays, each (N,).
    """
    N = len(bolus_series)
    kernel = _build_activity_kernel(dia_hours, peak_min, interval_min)

    bolus_vals = bolus_series.fillna(0).values
    actual_basal_vals = actual_basal_series.ffill().fillna(0).values
    sched_basal_vals = scheduled_basal_array

    # Convert basal rates (U/hr) to micro-doses (U per interval)
    actual_basal_doses = actual_basal_vals * interval_min / 60.0
    sched_basal_doses = sched_basal_vals * interval_min / 60.0
    net_basal_doses = actual_basal_doses - sched_basal_doses

    # Convolve each source with the activity kernel
    bolus_activity = _convolve_doses_with_kernel(bolus_vals, kernel)
    actual_basal_activity = _convolve_doses_with_kernel(actual_basal_doses, kernel)
    sched_basal_activity = _convolve_doses_with_kernel(sched_basal_doses, kernel)
    net_basal_activity = _convolve_doses_with_kernel(net_basal_doses, kernel)

    # Total = everything actually delivered
    total_activity = bolus_activity + actual_basal_activity
    # Net = only deviations from equilibrium (what drives glucose changes)
    net_activity = bolus_activity + net_basal_activity

    # Basal coverage ratio: actual / scheduled (handles schedule = 0 edge case)
    safe_sched = np.where(sched_basal_vals > 0.01, sched_basal_vals, 0.01)
    basal_ratio = actual_basal_vals / safe_sched
    # Clip to reasonable range (0 to 5x scheduled)
    basal_ratio = np.clip(basal_ratio, 0.0, 5.0)

    return {
        'total': total_activity,
        'net': net_activity,
        'basal_steady_state': sched_basal_activity,
        'bolus_only': bolus_activity,
        'basal_ratio': basal_ratio,
    }


def compute_insulin_activity_legacy(bolus_series: pd.Series, basal_series: pd.Series,
                              scheduled_basal: float,
                              dia_hours: float = 5.0, peak_min: float = 55.0,
                              interval_min: int = 5) -> np.ndarray:
    """Legacy: net-only activity for backward compatibility. Use compute_insulin_activity."""
    N = len(bolus_series)
    dia_min = dia_hours * 60
    dia_steps = int(dia_min / interval_min)
    activity = np.zeros(N)

    bolus_vals = bolus_series.fillna(0).values
    basal_vals = basal_series.ffill().fillna(0).values

    for i in range(N):
        if bolus_vals[i] > 0:
            dose = bolus_vals[i]
            for j in range(i, min(i + dia_steps, N)):
                t_min = (j - i) * interval_min
                activity[j] += _insulin_activity_at_t(t_min, dose, dia_min, peak_min)

    for i in range(N):
        net_rate = basal_vals[i] - scheduled_basal
        if abs(net_rate) > 0.01:
            micro_dose = net_rate * interval_min / 60.0
            for j in range(i, min(i + dia_steps, N)):
                t_min = (j - i) * interval_min
                activity[j] += _insulin_activity_at_t(t_min, micro_dose, dia_min, peak_min)

    return activity


# ── Carb Absorption Rate (multi-phase GI model) ───────────────────────

def _carb_absorption_rate_at_t(t_min: float, carbs: float,
                                abs_time_min: float) -> float:
    """Carb absorption rate at time t_min after ingestion.

    Uses a piecewise-linear model inspired by Loop's CarbMath and UVA/Padova's
    Qsto1→Qsto2→Qgut pathway:
    - Rising phase (0 → 15%): gastric emptying accelerates (quadratic onset)
    - Plateau phase (15% → 50%): peak absorption rate sustained
    - Falling phase (50% → 100%): absorption decelerates (linear decline)

    This captures the key asymmetry observed physiologically: fast onset (carbs
    hit bloodstream quickly) with a long tail (slow carbs, fiber, fat delay).

    The area under the curve integrates to total carbs (mass conservation).

    Based on Loop's PiecewiseLinearAbsorption (CarbMath.swift:147-202).

    Args:
        t_min: Minutes since carb ingestion
        carbs: Total carbs in grams
        abs_time_min: Total absorption time in minutes

    Returns:
        Carb absorption rate in g/min
    """
    if t_min <= 0 or t_min >= abs_time_min or carbs <= 0:
        return 0.0

    # Loop-style: 3-phase with early peak
    pct_time = t_min / abs_time_min
    rise_end = 0.15      # Peak reached at 15% of absorption time
    plateau_end = 0.50   # Plateau until 50%

    # Scale factor ensures area = 1.0 for unit carbs
    # Area = rise_triangle + plateau_rect + fall_triangle
    # = 0.5*rise_end*scale + (plateau_end - rise_end)*scale + 0.5*(1-plateau_end)*scale
    # = scale * (0.5*rise_end + plateau_end - rise_end + 0.5 - 0.5*plateau_end)
    # = scale * (0.5 + 0.5*plateau_end - 0.5*rise_end)
    scale = 2.0 / (1.0 + plateau_end - rise_end)

    # Peak rate (g per unit-time-fraction)
    peak_rate = scale * carbs / abs_time_min  # g/min at plateau

    if pct_time < rise_end:
        # Rising: linear ramp to peak
        rate = peak_rate * (pct_time / rise_end)
    elif pct_time < plateau_end:
        # Plateau: sustained peak rate
        rate = peak_rate
    else:
        # Falling: linear decline to zero
        rate = peak_rate * (1.0 - pct_time) / (1.0 - plateau_end)

    return max(rate, 0.0)


def _build_carb_kernel(abs_hours: float = 3.0, interval_min: int = 5) -> np.ndarray:
    """Pre-compute carb absorption kernel for convolution."""
    abs_min = abs_hours * 60
    K = int(abs_min / interval_min)
    kernel = np.zeros(K)
    for k in range(K):
        t_min = (k + 1) * interval_min
        kernel[k] = _carb_absorption_rate_at_t(t_min, 1.0, abs_min)
    return kernel


def compute_carb_absorption_rate(carbs_series: pd.Series,
                                  abs_hours: float = 3.0,
                                  interval_min: int = 5) -> np.ndarray:
    """Compute continuous carb absorption rate from carb entry history.

    Returns the instantaneous rate of glucose appearance (g/min) at each timestep,
    combining contributions from all prior carb entries still being absorbed.

    Unlike COB (remaining carbs), this is the RATE — how fast carbs are entering
    the bloodstream NOW. This directly drives glucose rise.

    Args:
        carbs_series: Series of carb entries (g) with DatetimeIndex
        abs_hours: Carb absorption time in hours
        interval_min: Grid interval in minutes

    Returns:
        (N,) array of carb absorption rate in g/min at each grid point
    """
    kernel = _build_carb_kernel(abs_hours, interval_min)
    carbs_vals = carbs_series.fillna(0).values
    return _convolve_doses_with_kernel(carbs_vals, kernel)


# ── Hepatic Glucose Production (liver model) ──────────────────────────

def compute_hepatic_production(iob_series: np.ndarray,
                                hours_array: np.ndarray,
                                weight_kg: float = 70.0) -> np.ndarray:
    """Estimate hepatic glucose production (EGP) at each timestep.

    Based on cgmsim-lib liver.ts and UVA/Padova EGP equation:
      EGP ≈ base_rate × (1 - insulin_suppression) × circadian_modulator

    Insulin suppression uses a Hill equation (from liver.ts):
      suppression = IOB^n / (IOB^n + K^n)

    Circadian modulation uses sin wave (from sinus.ts):
      circadian = 1 + amplitude × sin(2π × hour / 24)

    This captures that the liver produces more glucose when:
    - Insulin levels are low (fasting, between meals)
    - It's early morning (dawn phenomenon, cortisol)

    Args:
        iob_series: (N,) array of insulin on board (U)
        hours_array: (N,) array of hour of day (0-24, fractional)
        weight_kg: Patient body weight in kg

    Returns:
        (N,) array of estimated hepatic glucose production in mg/dL per 5min
    """
    # Physiological parameters (from cgmsim-lib liver.ts)
    # Normal pancreas: ~0.7 U/hr for 70kg → 0.01 U/kg/hr
    physiological_basal_rate = 0.01 * weight_kg / 60  # U/min

    # Hill equation parameters for subcutaneous insulin suppression
    max_suppression = 0.65  # SC insulin can suppress max 65% of EGP
    half_max_ratio = 2.0     # Activity ratio for 50% of max suppression
    hill_coeff = 1.5

    # Base glucose production: ~1.5 mg/dL per 5-min step at zero insulin
    # (from physics_model.py LIVER_BASE_RATE)
    base_rate = 1.5  # mg/dL per 5-min

    # Circadian amplitude (from sinus.ts: ±20%)
    circadian_amplitude = 0.20

    N = len(iob_series)
    egp = np.zeros(N)

    for i in range(N):
        # Insulin suppression via Hill equation
        # Convert IOB to approximate insulin activity ratio
        iob = max(iob_series[i], 0)
        activity_ratio = iob / max(physiological_basal_rate * 60, 0.01)  # ratio to hourly baseline

        if activity_ratio > 0:
            suppression_raw = (activity_ratio ** hill_coeff) / \
                              (half_max_ratio ** hill_coeff + activity_ratio ** hill_coeff)
            suppression = suppression_raw * max_suppression
        else:
            suppression = 0.0

        production_factor = max(1.0 - suppression, 0.35)

        # Circadian modulation: peak at ~6 AM (dawn phenomenon)
        # sin(2π × hour/24) peaks at 6h
        hour = hours_array[i]
        circadian = 1.0 + circadian_amplitude * np.sin(2 * np.pi * hour / 24.0)

        egp[i] = base_rate * production_factor * circadian

    return egp


# ── Net Metabolic Balance ─────────────────────────────────────────────

def compute_net_metabolic_balance(insulin_activity: np.ndarray,
                                   carb_absorption_rate: np.ndarray,
                                   hepatic_production: np.ndarray,
                                   isf: np.ndarray,
                                   cr: np.ndarray) -> np.ndarray:
    """Compute instantaneous net glucose flux from all sources.

    net_flux > 0: glucose is RISING (carbs + liver winning over insulin)
    net_flux < 0: glucose is FALLING (insulin winning)
    net_flux ≈ 0: metabolic balance (stable glucose)

    This is the key continuous signal — it captures the instantaneous
    "tug of war" between glucose sources and sinks.

    The formula is derived from the UVA/Padova glucose equation:
      dGp/dt = EGP + Ra - Uid - Uii - E + k2·Gt - k1·Gp

    Simplified to observable quantities:
      net_flux ≈ (carb_rate/CR) × ISF + EGP - insulin_activity × ISF

    Units: approximate mg/dL per 5-min step

    ISF and CR are time-varying arrays expanded from the patient's therapy
    schedule, reflecting the circadian variation in insulin sensitivity
    (e.g., higher ISF at night, lower in morning due to dawn phenomenon).

    Args:
        insulin_activity: (N,) U/min
        carb_absorption_rate: (N,) g/min
        hepatic_production: (N,) mg/dL per 5min
        isf: (N,) array — Insulin Sensitivity Factor (mg/dL per U) at each timestep
        cr: (N,) array — Carb Ratio (g per U) at each timestep

    Returns:
        (N,) array of net glucose flux in mg/dL per 5-min
    """
    # Insulin effect: activity (U/min) × 5 min × ISF (mg/dL per U) = mg/dL glucose drop
    insulin_effect = insulin_activity * 5.0 * isf

    # Carb effect: rate (g/min) × 5 min / CR (g/U) × ISF (mg/dL/U) = mg/dL glucose rise
    # Guard against CR=0
    safe_cr = np.where(cr > 0, cr, 10.0)
    carb_effect = carb_absorption_rate * 5.0 * (isf / safe_cr)

    # Net = carb rise + liver production - insulin drop
    net = carb_effect + hepatic_production - insulin_effect

    return net


# ── Schedule Expansion (time-of-day → continuous curve) ───────────────

def expand_schedule(timestamps: pd.DatetimeIndex, schedule: list,
                    default: float = 0.0,
                    local_index: pd.DatetimeIndex = None) -> np.ndarray:
    """Expand a Nightscout time-of-day schedule into a continuous array.

    Nightscout therapy schedules (ISF, CR, basal, targets) are step functions
    defined by (timeAsSeconds, value) entries where timeAsSeconds is seconds
    since local midnight. This function evaluates the schedule at each grid
    timestamp, producing a dense array that captures the circadian variation
    in therapy settings.

    For example, a patient might have ISF=40 during the day and ISF=60 at night,
    reflecting the dawn phenomenon. Collapsing to a median would lose this
    clinically important variation.

    Args:
        timestamps: DatetimeIndex of the data grid (UTC or tz-aware)
        schedule: List of dicts with 'timeAsSeconds' and 'value' keys,
                  sorted by timeAsSeconds. E.g.:
                  [{'timeAsSeconds': 0, 'value': 60},
                   {'timeAsSeconds': 21600, 'value': 40}]
        default: Fallback value if schedule is empty
        local_index: If provided, use this for local time lookup instead of
                     timestamps (handles UTC→local conversion upstream)

    Returns:
        (N,) array of schedule values at each timestep
    """
    idx = local_index if local_index is not None else timestamps
    N = len(idx)
    values = np.full(N, default, dtype=np.float64)

    if not schedule:
        return values

    # Pre-sort schedule by timeAsSeconds for correct lookup
    sorted_sched = sorted(schedule, key=lambda e: e.get('timeAsSeconds', 0))

    for i, ts in enumerate(idx):
        sec_of_day = ts.hour * 3600 + ts.minute * 60 + ts.second
        val = sorted_sched[0].get('value', default)
        for entry in sorted_sched:
            if entry.get('timeAsSeconds', 0) <= sec_of_day:
                val = entry.get('value', default)
        values[i] = float(val)

    return values


# ── Numerical Derivatives (acceleration of absorption) ────────────────

def compute_acceleration(signal: np.ndarray, interval_min: int = 5) -> np.ndarray:
    """Compute numerical first derivative (acceleration/deceleration).

    Positive = absorption/activity is ramping UP
    Negative = absorption/activity is ramping DOWN
    Zero crossing = peak of absorption

    Args:
        signal: (N,) array of activity/rate values
        interval_min: Time between samples in minutes

    Returns:
        (N,) array of rate of change per minute
    """
    accel = np.zeros_like(signal)
    accel[1:-1] = (signal[2:] - signal[:-2]) / (2 * interval_min)  # central difference
    accel[0] = (signal[1] - signal[0]) / interval_min if len(signal) > 1 else 0
    accel[-1] = (signal[-1] - signal[-2]) / interval_min if len(signal) > 1 else 0
    return accel


# ── High-Level Feature Builder ────────────────────────────────────────

# Normalization scales for continuous PK channels
PK_NORMALIZATION = {
    'insulin_total':     0.05,    # U/min; steady-state ~0.015 + bolus peaks ~0.04
    'insulin_net':       0.05,    # U/min; net deviation activity (can be negative)
    'basal_ratio':       2.0,     # ratio; 1.0 = nominal, normalized to [0, 2.5]
    'carb_rate':         0.5,     # g/min; typical peak ~0.2-0.4 for 50g meal
    'carb_accel':        0.05,    # d(g/min)/min
    'hepatic_production': 3.0,    # mg/dL per 5min; range ~0.5-2.5
    'net_balance':       20.0,    # mg/dL per 5min; range ~±15
    'isf_curve':         200.0,   # mg/dL per U; time-varying ISF from schedule
}

PK_CHANNEL_NAMES = [
    'insulin_total', 'insulin_net',
    'basal_ratio',
    'carb_rate', 'carb_accel',
    'hepatic_production', 'net_balance',
    'isf_curve',
]

NUM_PK_CHANNELS = len(PK_CHANNEL_NAMES)


def build_continuous_pk_features(df: pd.DataFrame,
                                  dia_hours: float = 5.0,
                                  peak_min: float = 55.0,
                                  isf_schedule: list = None,
                                  cr_schedule: list = None,
                                  basal_schedule: list = None,
                                  carb_abs_hours: float = 3.0,
                                  weight_kg: float = 70.0,
                                  interval_min: int = 5,
                                  verbose: bool = False) -> np.ndarray:
    """Build all continuous PK feature channels from a Nightscout grid DataFrame.

    Produces 8 dense physiological state channels from sparse treatment events:

    1. insulin_total:  Total insulin activity from ALL sources (scheduled basal
                       + temp deviation + bolus). Represents the full insulin
                       state. Steady-state floor from scheduled basal; bolus
                       peaks on top; suspension → gradual decay over DIA.
    2. insulin_net:    Activity from DEVIATIONS only (temp deviation + bolus).
                       This drives glucose changes — scheduled basal maintains
                       equilibrium and contributes zero net glucose effect.
    3. basal_ratio:    actual_rate / scheduled_rate at each timestep.
                       1.0 = pump delivering 100% of scheduled (equilibrium).
                       0.0 = suspended (net negative insulin delivery).
                       >1.0 = high temp (more aggressive correction).
    4. carb_rate:      Carb absorption rate (g/min) from piecewise-linear GI
                       model (Loop-style: fast rise 15%, plateau, slow tail).
    5. carb_accel:     d/dt of carb absorption rate. Positive = ramping up,
                       negative = winding down, zero = at peak.
    6. hepatic_prod:   Estimated hepatic glucose production (mg/dL per 5min).
                       Hill-equation insulin suppression + circadian modulation.
    7. net_balance:    Instantaneous net glucose flux (mg/dL per 5min).
                       Positive = glucose rising, negative = falling.
                       Uses time-varying ISF and CR from therapy schedules.
    8. isf_curve:      Time-varying ISF from schedule expansion (mg/dL per U).
                       Captures circadian insulin sensitivity variation.

    ISF and CR are expanded from therapy schedules (not collapsed to scalars).
    Basal schedule is expanded per-timestep, matching how build_nightscout_grid
    expands it for net_basal computation.

    Args:
        df: DataFrame from build_nightscout_grid(). Must have DatetimeIndex and
            columns: glucose, bolus, carbs, iob, temp_rate, net_basal.
            Expects df.attrs: isf_schedule, cr_schedule, patient_tz, profile_units.
        dia_hours: Duration of insulin action
        peak_min: Time to peak insulin activity (minutes)
        isf_schedule: ISF schedule list. If None, reads from df.attrs.
        cr_schedule: CR schedule list. If None, reads from df.attrs.
        basal_schedule: Basal rate schedule list. If None, reads from df.attrs.
        carb_abs_hours: Carb absorption time (hours)
        weight_kg: Patient body weight
        interval_min: Grid interval in minutes
        verbose: Print progress

    Returns:
        (N, 8) normalized array of continuous PK channels.
    """
    from .real_data_adapter import _normalize_timezone, _to_local_index

    N = len(df)

    # Extract series
    bolus = df['bolus'] if 'bolus' in df.columns else pd.Series(np.zeros(N), index=df.index)
    carbs_col = df['carbs'] if 'carbs' in df.columns else pd.Series(np.zeros(N), index=df.index)

    # Actual basal: temp_rate represents what the pump actually delivered
    if 'temp_rate' in df.columns:
        actual_basal = df['temp_rate'].ffill().fillna(0)
    else:
        actual_basal = pd.Series(np.zeros(N), index=df.index)

    # IOB for liver suppression (use pre-computed from devicestatus if available)
    if 'iob' in df.columns:
        iob = df['iob'].fillna(0).values
    else:
        from .real_data_adapter import approximate_iob
        iob = approximate_iob(bolus, dia_hours, interval_min).values

    # Resolve local time index for schedule lookups
    patient_tz = df.attrs.get('patient_tz', '')
    local_index = _to_local_index(df.index, patient_tz)

    # Hours of day for circadian (using local time)
    if hasattr(local_index, 'hour'):
        hours = local_index.hour + local_index.minute / 60.0
    else:
        hours = np.zeros(N)

    # ── Expand therapy schedules into continuous curves ──

    # ISF schedule → continuous time-varying array
    if isf_schedule is None:
        isf_schedule = df.attrs.get('isf_schedule', [])
    isf_array = expand_schedule(df.index, isf_schedule, default=40.0,
                                local_index=local_index)

    # Detect mmol/L units and convert ISF to mg/dL/U
    profile_units = df.attrs.get('profile_units', 'mg/dL')
    if 'mmol' in profile_units.lower() or (isf_array.max() < 15 and isf_array.max() > 0):
        isf_array = isf_array * 18.0182
        if verbose:
            print(f"    Converted ISF from mmol/L → mg/dL (×18)")

    # CR schedule → continuous time-varying array
    if cr_schedule is None:
        cr_schedule = df.attrs.get('cr_schedule', [])
    cr_array = expand_schedule(df.index, cr_schedule, default=10.0,
                               local_index=local_index)

    # Basal schedule → continuous per-timestep scheduled rate
    if basal_schedule is None:
        basal_schedule = df.attrs.get('basal_schedule', [])
    if basal_schedule:
        sched_basal_array = expand_schedule(df.index, basal_schedule, default=0.0,
                                             local_index=local_index)
    else:
        # Fall back: estimate scheduled basal from median of actual delivery
        actual_vals = actual_basal.values
        positive = actual_vals[actual_vals > 0]
        median_rate = float(np.median(positive)) if len(positive) > 0 else 0.0
        sched_basal_array = np.full(N, median_rate)

    if verbose:
        print(f"  Computing continuous PK channels ({N} timesteps)...")
        n_bolus = int((bolus.fillna(0) > 0).sum())
        n_carbs = int((carbs_col.fillna(0) > 0).sum())
        print(f"    Bolus events: {n_bolus}, Carb events: {n_carbs}")
        print(f"    DIA={dia_hours}h, peak={peak_min}min")
        print(f"    ISF: {len(isf_schedule)} segments, "
              f"range [{isf_array.min():.1f}, {isf_array.max():.1f}] mg/dL/U")
        print(f"    CR: {len(cr_schedule)} segments, "
              f"range [{cr_array.min():.1f}, {cr_array.max():.1f}] g/U")
        print(f"    Basal sched: {len(basal_schedule)} segments, "
              f"range [{sched_basal_array.min():.2f}, {sched_basal_array.max():.2f}] U/hr")

    # 1-2. Insulin activity — full decomposition
    insulin = compute_insulin_activity(
        bolus, actual_basal, sched_basal_array,
        dia_hours, peak_min, interval_min)

    insulin_total = insulin['total']
    insulin_net = insulin['net']
    basal_ratio = insulin['basal_ratio']

    # 3. Carb absorption rate
    carb_rate = compute_carb_absorption_rate(carbs_col, carb_abs_hours, interval_min)

    # 4. Carb acceleration (d/dt of absorption)
    carb_accel = compute_acceleration(carb_rate, interval_min)

    # 5. Hepatic glucose production
    hepatic = compute_hepatic_production(iob, hours, weight_kg)

    # 6. Net metabolic balance (uses net insulin activity + time-varying ISF/CR)
    net_balance = compute_net_metabolic_balance(
        insulin_net, carb_rate, hepatic, isf_array, cr_array)

    if verbose:
        print(f"    Insulin total range: [{insulin_total.min():.4f}, {insulin_total.max():.4f}] U/min")
        print(f"    Insulin net range: [{insulin_net.min():.4f}, {insulin_net.max():.4f}] U/min")
        ss_mean = insulin['basal_steady_state'].mean()
        print(f"    Basal steady-state mean: {ss_mean:.5f} U/min")
        print(f"    Basal ratio range: [{basal_ratio.min():.2f}, {basal_ratio.max():.2f}]")
        print(f"    Carb rate range: [{carb_rate.min():.4f}, {carb_rate.max():.4f}] g/min")
        print(f"    Hepatic range: [{hepatic.min():.2f}, {hepatic.max():.2f}] mg/dL per 5min")
        print(f"    Net balance range: [{net_balance.min():.2f}, {net_balance.max():.2f}] mg/dL per 5min")

    # Stack and normalize
    features = np.column_stack([
        insulin_total / PK_NORMALIZATION['insulin_total'],
        insulin_net / PK_NORMALIZATION['insulin_net'],
        basal_ratio / PK_NORMALIZATION['basal_ratio'],
        carb_rate / PK_NORMALIZATION['carb_rate'],
        carb_accel / PK_NORMALIZATION['carb_accel'],
        hepatic / PK_NORMALIZATION['hepatic_production'],
        net_balance / PK_NORMALIZATION['net_balance'],
        isf_array / PK_NORMALIZATION['isf_curve'],
    ])

    return features.astype(np.float32)


# ── Validation: Correlation with glucose dynamics ─────────────────────

def validate_pk_correlation(df: pd.DataFrame, pk_features: np.ndarray,
                             interval_min: int = 5) -> Dict[str, float]:
    """Validate continuous PK channels by correlating with glucose rate of change.

    The net_metabolic_balance should correlate positively with dBG/dt:
    when net balance is positive (carbs winning), glucose should be rising;
    when negative (insulin winning), glucose should be falling.

    Args:
        df: DataFrame with 'glucose' column
        pk_features: (N, 8) array from build_continuous_pk_features
        interval_min: Grid interval

    Returns:
        Dict with Pearson correlation, Spearman correlation, and per-channel stats
    """
    glucose = df['glucose'].interpolate(limit=6).values

    # Compute glucose rate of change (mg/dL per 5-min, central difference)
    dBG = np.zeros_like(glucose)
    dBG[1:-1] = (glucose[2:] - glucose[:-2]) / 2.0
    dBG[0] = glucose[1] - glucose[0] if len(glucose) > 1 else 0
    dBG[-1] = glucose[-1] - glucose[-2] if len(glucose) > 1 else 0

    # Mask out NaN glucose
    valid = ~np.isnan(glucose) & ~np.isnan(dBG)
    # Also mask extreme glucose changes (likely sensor artifacts)
    valid &= np.abs(dBG) < 30  # < 30 mg/dL per 5-min is physiologically plausible

    if valid.sum() < 100:
        return {'error': 'insufficient valid data', 'n_valid': int(valid.sum())}

    dBG_valid = dBG[valid]

    results = {
        'n_valid': int(valid.sum()),
        'n_total': len(glucose),
        'dBG_mean': float(np.mean(dBG_valid)),
        'dBG_std': float(np.std(dBG_valid)),
    }

    # Correlate each PK channel with glucose rate of change
    from scipy import stats as sp_stats

    for ch_idx, ch_name in enumerate(PK_CHANNEL_NAMES):
        ch_data = pk_features[valid, ch_idx]
        # De-normalize for interpretability
        ch_raw = ch_data * PK_NORMALIZATION[ch_name]

        if np.std(ch_raw) < 1e-10:
            results[f'{ch_name}_pearson_r'] = 0.0
            results[f'{ch_name}_spearman_r'] = 0.0
            results[f'{ch_name}_mean'] = float(np.mean(ch_raw))
            results[f'{ch_name}_std'] = 0.0
            continue

        pearson_r, pearson_p = sp_stats.pearsonr(ch_raw, dBG_valid)
        spearman_r, spearman_p = sp_stats.spearmanr(ch_raw, dBG_valid)

        results[f'{ch_name}_pearson_r'] = float(pearson_r)
        results[f'{ch_name}_pearson_p'] = float(pearson_p)
        results[f'{ch_name}_spearman_r'] = float(spearman_r)
        results[f'{ch_name}_spearman_p'] = float(spearman_p)
        results[f'{ch_name}_mean'] = float(np.mean(ch_raw))
        results[f'{ch_name}_std'] = float(np.std(ch_raw))

    # Primary success metric: net_balance correlation with dBG/dt
    net_raw = pk_features[valid, PK_CHANNEL_NAMES.index('net_balance')] * PK_NORMALIZATION['net_balance']
    r_primary, p_primary = sp_stats.pearsonr(net_raw, dBG_valid)
    results['primary_pearson_r'] = float(r_primary)
    results['primary_pearson_p'] = float(p_primary)
    results['primary_success'] = bool(abs(r_primary) > 0.3)

    return results


# ── Standalone runner for EXP-348 ─────────────────────────────────────

def run_exp348(patients_dir: str, output_path: str = None,
               verbose: bool = True) -> dict:
    """Run EXP-348: Validate continuous PK channels across all patients.

    For each patient:
      1. Load Nightscout grid (5-min resolution)
      2. Compute continuous PK channels
      3. Correlate net_metabolic_balance with dBG/dt
      4. Compare insulin_activity correlation vs raw IOB correlation

    Success criterion: Mean |Pearson r| > 0.3 for net_balance vs dBG/dt.

    Args:
        patients_dir: Path to patient data (each subdir has training/)
        output_path: Where to save JSON results
        verbose: Print progress

    Returns:
        Experiment results dict
    """
    import os
    import json
    import time as time_mod

    if output_path is None:
        output_path = os.path.join('externals', 'experiments', 'exp348_continuous_pk.json')

    from .real_data_adapter import build_nightscout_grid

    patient_dirs = sorted([
        os.path.join(patients_dir, p, 'training')
        for p in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, p, 'training'))
    ])

    if verbose:
        print(f"EXP-348: Continuous Pharmacokinetic State Channels")
        print(f"  Patients: {len(patient_dirs)}")
        print(f"  Testing correlation of continuous PK channels with glucose dynamics")
        print()

    t0 = time_mod.time()
    per_patient = {}

    for i, pdir in enumerate(patient_dirs):
        patient_id = os.path.basename(os.path.dirname(pdir))
        if verbose:
            print(f"  Patient {patient_id} ({i+1}/{len(patient_dirs)}):")

        try:
            df, features_8ch = build_nightscout_grid(pdir, verbose=False)
            if df is None:
                if verbose:
                    print(f"    SKIP: no valid data")
                continue

            # Extract patient-specific parameters from profile
            dia = df.attrs.get('patient_dia', 5.0)

            # Build continuous PK features (all schedules expanded from df.attrs)
            pk = build_continuous_pk_features(
                df, dia_hours=dia, peak_min=55.0,
                carb_abs_hours=3.0, verbose=verbose)

            # Validate correlation with glucose dynamics
            corr = validate_pk_correlation(df, pk)

            # Also compute baseline IOB correlation for comparison
            from scipy import stats as sp_stats
            glucose = df['glucose'].interpolate(limit=6).values
            dBG = np.zeros_like(glucose)
            dBG[1:-1] = (glucose[2:] - glucose[:-2]) / 2.0
            iob_vals = df['iob'].fillna(0).values
            valid = ~np.isnan(glucose) & ~np.isnan(dBG) & (np.abs(dBG) < 30)
            if valid.sum() > 100:
                # IOB should anti-correlate (more IOB → glucose dropping)
                if np.std(iob_vals[valid]) > 1e-10:
                    iob_r, iob_p = sp_stats.pearsonr(iob_vals[valid], dBG[valid])
                    corr['baseline_iob_pearson_r'] = float(iob_r)
                    corr['baseline_iob_pearson_p'] = float(iob_p)
                else:
                    corr['baseline_iob_pearson_r'] = 0.0
                    corr['baseline_iob_pearson_p'] = 1.0

                # Raw bolus correlation (expected: near zero, sparse)
                bolus_vals = df['bolus'].fillna(0).values
                bolus_r, bolus_p = sp_stats.pearsonr(bolus_vals[valid], dBG[valid])
                corr['baseline_bolus_pearson_r'] = float(bolus_r)

                # Raw carbs correlation
                carbs_vals = df['carbs'].fillna(0).values
                carbs_r, carbs_p = sp_stats.pearsonr(carbs_vals[valid], dBG[valid])
                corr['baseline_carbs_pearson_r'] = float(carbs_r)

            per_patient[patient_id] = corr

            if verbose:
                net_r = corr.get('primary_pearson_r', 0)
                iob_r = corr.get('baseline_iob_pearson_r', 0)
                bolus_r = corr.get('baseline_bolus_pearson_r', 0)
                print(f"    net_balance↔dBG r={net_r:+.3f} | "
                      f"IOB↔dBG r={iob_r:+.3f} | "
                      f"bolus↔dBG r={bolus_r:+.3f}")

        except Exception as e:
            if verbose:
                print(f"    ERROR: {e}")
            per_patient[patient_id] = {'error': str(e)}

    elapsed = time_mod.time() - t0

    # Aggregate results
    valid_patients = {k: v for k, v in per_patient.items() if 'primary_pearson_r' in v}
    if valid_patients:
        net_rs = [v['primary_pearson_r'] for v in valid_patients.values()]
        iob_rs = [v.get('baseline_iob_pearson_r', 0) for v in valid_patients.values()]

        # Per-channel aggregation
        channel_summary = {}
        for ch in PK_CHANNEL_NAMES:
            ch_rs = [v.get(f'{ch}_pearson_r', 0) for v in valid_patients.values()]
            channel_summary[ch] = {
                'mean_r': float(np.mean(ch_rs)),
                'std_r': float(np.std(ch_rs)),
                'min_r': float(np.min(ch_rs)),
                'max_r': float(np.max(ch_rs)),
            }

        summary = {
            'n_patients': len(valid_patients),
            'net_balance_mean_r': float(np.mean(net_rs)),
            'net_balance_std_r': float(np.std(net_rs)),
            'net_balance_min_r': float(np.min(net_rs)),
            'net_balance_max_r': float(np.max(net_rs)),
            'iob_baseline_mean_r': float(np.mean(iob_rs)),
            'improvement_over_iob': float(np.mean(np.abs(net_rs)) - np.mean(np.abs(iob_rs))),
            'success_criterion': '|mean Pearson r| > 0.3 for net_balance vs dBG/dt',
            'success': bool(abs(np.mean(net_rs)) > 0.3),
            'channel_summary': channel_summary,
        }
    else:
        summary = {'n_patients': 0, 'success': False, 'error': 'no valid patients'}

    result = {
        'experiment': 'EXP-348',
        'name': 'Continuous Pharmacokinetic State Channels',
        'hypothesis': 'Continuous PK channels (insulin activity, carb absorption rate, '
                       'hepatic production, net metabolic balance) correlate with '
                       'glucose rate of change better than sparse event channels.',
        'summary': summary,
        'per_patient': per_patient,
        'elapsed_seconds': elapsed,
        'config': {
            'peak_min': 55.0,
            'carb_abs_hours': 3.0,
            'pk_channels': PK_CHANNEL_NAMES,
            'normalization': PK_NORMALIZATION,
        },
    }

    if verbose:
        print(f"\n  Summary ({summary.get('n_patients', 0)} patients, {elapsed:.1f}s):")
        print(f"    net_balance ↔ dBG/dt: mean r = {summary.get('net_balance_mean_r', 0):+.3f}")
        print(f"    IOB baseline ↔ dBG/dt: mean r = {summary.get('iob_baseline_mean_r', 0):+.3f}")
        print(f"    Improvement: {summary.get('improvement_over_iob', 0):+.3f}")
        print(f"    Success: {summary.get('success', False)}")

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    if verbose:
        print(f"\n  Saved: {output_path}")

    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='EXP-348: Continuous PK State Channels')
    parser.add_argument('patients_dir', help='Path to patient data directory')
    parser.add_argument('--output', default=None, help='Output JSON path')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    args = parser.parse_args()

    run_exp348(args.patients_dir, args.output, verbose=not args.quiet)
