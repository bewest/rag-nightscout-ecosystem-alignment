"""
continuous_pk.py — Continuous pharmacokinetic state channels for CGM/AID modeling.

Converts sparse treatment events (bolus, carbs, basal) into dense continuous
physiological state signals at 5-min resolution, guided by the UVA/Padova
compartment model and oref0 insulin activity curves.

EXP-348: Validate that continuous PK channels (insulin_activity, carb_absorption_rate,
hepatic_production, net_metabolic_balance) correlate with observed glucose dynamics
better than raw sparse event channels.

Key insight: Instead of feeding models sparse bolus/carb spikes alongside crude
IOB/COB exponential/linear decays, we compute the continuous physiological states
those events create — absorption rates, activity curves, metabolic balance — giving
the model dense, physiologically grounded input channels.

Usage:
    from tools.cgmencode.continuous_pk import (
        compute_insulin_activity,
        compute_carb_absorption_rate,
        compute_hepatic_production,
        compute_net_metabolic_balance,
        build_continuous_pk_features,
    )

    # From a build_nightscout_grid DataFrame:
    pk_channels = build_continuous_pk_features(df, dia=5.0, peak_min=55, isf=40, cr=10)
    # pk_channels is (N, 6) array: [insulin_activity, insulin_accel, carb_rate,
    #                                carb_accel, hepatic_production, net_balance]

References:
    - UVA/Padova T1DMS: externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts
    - oref0 exponential IOB: externals/oref0/lib/iob/calculate.js
    - cgmsim-lib insulin activity: externals/cgmsim-lib/src/utils.ts (getExpTreatmentActivity)
    - cgmsim-lib liver model: externals/cgmsim-lib/src/liver.ts
    - cgmsim-lib circadian: externals/cgmsim-lib/src/sinus.ts
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


def compute_insulin_activity(bolus_series: pd.Series, basal_series: pd.Series,
                              scheduled_basal: float,
                              dia_hours: float = 5.0, peak_min: float = 55.0,
                              interval_min: int = 5) -> np.ndarray:
    """Compute continuous insulin activity curve from bolus + basal history.

    Returns the instantaneous rate of insulin action (U/min) at each timestep,
    combining contributions from all prior boluses and net basal deviation.

    Unlike IOB (which is remaining insulin), this is the ACTIVITY — the rate
    at which insulin is currently lowering glucose. This is the derivative of
    the IOB curve and more directly relates to glucose dynamics.

    Args:
        bolus_series: Series of bolus doses (U) with DatetimeIndex
        basal_series: Series of actual basal rates (U/hr) with DatetimeIndex
        scheduled_basal: Scheduled basal rate (U/hr) for net basal computation
        dia_hours: Duration of insulin action in hours
        peak_min: Time to peak activity in minutes
        interval_min: Grid interval in minutes

    Returns:
        (N,) array of insulin activity in U/min at each grid point
    """
    N = len(bolus_series)
    dia_min = dia_hours * 60
    dia_steps = int(dia_min / interval_min)
    activity = np.zeros(N)

    bolus_vals = bolus_series.fillna(0).values
    basal_vals = basal_series.ffill().fillna(0).values

    # Bolus contributions: each bolus creates an activity curve
    for i in range(N):
        if bolus_vals[i] > 0:
            dose = bolus_vals[i]
            for j in range(i, min(i + dia_steps, N)):
                t_min = (j - i) * interval_min
                activity[j] += _insulin_activity_at_t(t_min, dose, dia_min, peak_min)

    # Basal deviation contributions: net basal above/below scheduled
    # Each 5-min basal "micro-dose" = (rate U/hr) * (5/60) hrs = rate/12 U
    for i in range(N):
        net_rate = basal_vals[i] - scheduled_basal
        if abs(net_rate) > 0.01:  # skip negligible deviations
            micro_dose = net_rate * interval_min / 60.0
            for j in range(i, min(i + dia_steps, N)):
                t_min = (j - i) * interval_min
                activity[j] += _insulin_activity_at_t(t_min, micro_dose, dia_min, peak_min)

    return activity


# ── Carb Absorption Rate (multi-phase GI model) ───────────────────────

def _carb_absorption_rate_at_t(t_min: float, carbs: float,
                                abs_time_min: float) -> float:
    """Carb absorption rate at time t_min after ingestion.

    Uses a trapezoidal model inspired by UVA/Padova's Qsto1→Qsto2→Qgut pathway:
    - Rising phase (0 → peak): gastric emptying accelerates
    - Peak phase: maximum absorption rate
    - Falling phase (peak → end): absorption decelerates

    The area under the curve integrates to total carbs (mass conservation).

    This is a simplification of UVA/Padova's nonlinear kempt model but captures
    the key asymmetry: faster onset than resolution.

    Args:
        t_min: Minutes since carb ingestion
        carbs: Total carbs in grams
        abs_time_min: Total absorption time in minutes

    Returns:
        Carb absorption rate in g/min
    """
    if t_min <= 0 or t_min >= abs_time_min or carbs <= 0:
        return 0.0

    # Peak at 30% of absorption time (UVA/Padova bmeal ≈ 0.69, so peak is early)
    peak_fraction = 0.30
    peak_time = abs_time_min * peak_fraction

    # Trapezoidal: rise linearly to peak, then fall linearly
    # Area = carbs, so peak_rate = 2 * carbs / abs_time_min
    peak_rate = 2.0 * carbs / abs_time_min

    if t_min < peak_time:
        # Rising phase
        rate = peak_rate * (t_min / peak_time)
    else:
        # Falling phase
        rate = peak_rate * (1.0 - (t_min - peak_time) / (abs_time_min - peak_time))

    return max(rate, 0.0)


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
    N = len(carbs_series)
    abs_min = abs_hours * 60
    abs_steps = int(abs_min / interval_min)
    rate = np.zeros(N)

    carbs_vals = carbs_series.fillna(0).values

    for i in range(N):
        if carbs_vals[i] > 0:
            carb_amount = carbs_vals[i]
            for j in range(i, min(i + abs_steps, N)):
                t_min = (j - i) * interval_min
                rate[j] += _carb_absorption_rate_at_t(t_min, carb_amount, abs_min)

    return rate


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
    'insulin_activity':  0.05,    # U/min; typical peak ~0.02-0.04 for 5U bolus
    'insulin_accel':     0.005,   # d(U/min)/min; rate of change of activity
    'carb_rate':         0.5,     # g/min; typical peak ~0.2-0.4 for 50g meal
    'carb_accel':        0.05,    # d(g/min)/min
    'hepatic_production': 3.0,    # mg/dL per 5min; range ~0.5-2.5
    'net_balance':       20.0,    # mg/dL per 5min; range ~±15
}

PK_CHANNEL_NAMES = [
    'insulin_activity', 'insulin_accel',
    'carb_rate', 'carb_accel',
    'hepatic_production', 'net_balance',
]

NUM_PK_CHANNELS = len(PK_CHANNEL_NAMES)


def build_continuous_pk_features(df: pd.DataFrame,
                                  dia_hours: float = 5.0,
                                  peak_min: float = 55.0,
                                  isf_schedule: list = None,
                                  cr_schedule: list = None,
                                  carb_abs_hours: float = 3.0,
                                  weight_kg: float = 70.0,
                                  scheduled_basal: float = None,
                                  interval_min: int = 5,
                                  verbose: bool = False) -> np.ndarray:
    """Build all continuous PK feature channels from a Nightscout grid DataFrame.

    Takes the DataFrame produced by build_nightscout_grid() and computes 6
    continuous physiological state channels. ISF and CR are expanded from
    their therapy schedules into time-varying arrays, preserving the circadian
    variation that a scalar median would destroy.

    Args:
        df: DataFrame with columns: glucose, bolus, carbs, iob, plus basal info.
            Must have DatetimeIndex at regular intervals. Expects df.attrs to
            contain 'isf_schedule', 'cr_schedule', 'patient_tz' from the grid builder.
        dia_hours: Duration of insulin action
        peak_min: Time to peak insulin activity (minutes)
        isf_schedule: ISF schedule list. If None, reads from df.attrs['isf_schedule'].
        cr_schedule: CR schedule list. If None, reads from df.attrs['cr_schedule'].
        carb_abs_hours: Carb absorption time (hours)
        weight_kg: Patient body weight
        scheduled_basal: Scheduled basal rate. If None, uses median of actual.
        interval_min: Grid interval in minutes
        verbose: Print progress

    Returns:
        (N, 6) normalized array: [insulin_activity, insulin_accel,
                                   carb_rate, carb_accel,
                                   hepatic_production, net_balance]
    """
    from .real_data_adapter import _normalize_timezone, _to_local_index

    N = len(df)

    # Extract series
    bolus = df['bolus'] if 'bolus' in df.columns else pd.Series(np.zeros(N), index=df.index)
    carbs = df['carbs'] if 'carbs' in df.columns else pd.Series(np.zeros(N), index=df.index)

    # Basal rate: use temp_rate if available, else fall back
    if 'temp_rate' in df.columns:
        basal = df['temp_rate'].ffill().fillna(0)
    elif 'basal' in df.columns:
        basal = df['basal'].ffill().fillna(0)
    else:
        basal = pd.Series(np.zeros(N), index=df.index)

    if scheduled_basal is None:
        basal_vals = basal.values
        positive = basal_vals[basal_vals > 0]
        scheduled_basal = float(np.median(positive)) if len(positive) > 0 else 0.0

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

    # Expand ISF schedule → continuous time-varying array
    if isf_schedule is None:
        isf_schedule = df.attrs.get('isf_schedule', [])
    isf_array = expand_schedule(df.index, isf_schedule, default=40.0,
                                local_index=local_index)

    # Detect mmol/L units and convert ISF to mg/dL/U
    # ISF in mmol/L means "mmol/L drop per unit insulin" → ×18.0182 for mg/dL
    # Heuristic: if max ISF < 15, it's almost certainly mmol/L
    # (mg/dL ISF ranges 15-200+; mmol/L ISF ranges 0.5-12)
    profile_units = df.attrs.get('profile_units', 'mg/dL')
    if 'mmol' in profile_units.lower() or (isf_array.max() < 15 and isf_array.max() > 0):
        isf_array = isf_array * 18.0182
        if verbose:
            print(f"    Converted ISF from mmol/L → mg/dL (×18)")

    # Expand CR schedule → continuous time-varying array
    # CR is g carbs per unit insulin — unit-independent, no conversion needed
    if cr_schedule is None:
        cr_schedule = df.attrs.get('cr_schedule', [])
    cr_array = expand_schedule(df.index, cr_schedule, default=10.0,
                               local_index=local_index)

    if verbose:
        print(f"  Computing continuous PK channels ({N} timesteps)...")
        n_bolus = int((bolus.fillna(0) > 0).sum())
        n_carbs = int((carbs.fillna(0) > 0).sum())
        print(f"    Bolus events: {n_bolus}, Carb events: {n_carbs}")
        print(f"    DIA={dia_hours}h, peak={peak_min}min")
        print(f"    ISF schedule: {len(isf_schedule)} segments, "
              f"range [{isf_array.min():.1f}, {isf_array.max():.1f}] mg/dL/U")
        print(f"    CR schedule: {len(cr_schedule)} segments, "
              f"range [{cr_array.min():.1f}, {cr_array.max():.1f}] g/U")

    # 1. Insulin activity curve
    insulin_act = compute_insulin_activity(
        bolus, basal, scheduled_basal, dia_hours, peak_min, interval_min)

    # 2. Insulin acceleration (d/dt of activity)
    insulin_accel = compute_acceleration(insulin_act, interval_min)

    # 3. Carb absorption rate
    carb_rate = compute_carb_absorption_rate(carbs, carb_abs_hours, interval_min)

    # 4. Carb acceleration (d/dt of absorption)
    carb_accel = compute_acceleration(carb_rate, interval_min)

    # 5. Hepatic glucose production
    hepatic = compute_hepatic_production(iob, hours, weight_kg)

    # 6. Net metabolic balance (uses time-varying ISF and CR)
    net_balance = compute_net_metabolic_balance(
        insulin_act, carb_rate, hepatic, isf_array, cr_array)

    if verbose:
        print(f"    Insulin activity range: [{insulin_act.min():.4f}, {insulin_act.max():.4f}] U/min")
        print(f"    Carb rate range: [{carb_rate.min():.4f}, {carb_rate.max():.4f}] g/min")
        print(f"    Hepatic range: [{hepatic.min():.2f}, {hepatic.max():.2f}] mg/dL per 5min")
        print(f"    Net balance range: [{net_balance.min():.2f}, {net_balance.max():.2f}] mg/dL per 5min")

    # Stack and normalize
    features = np.column_stack([
        insulin_act / PK_NORMALIZATION['insulin_activity'],
        insulin_accel / PK_NORMALIZATION['insulin_accel'],
        carb_rate / PK_NORMALIZATION['carb_rate'],
        carb_accel / PK_NORMALIZATION['carb_accel'],
        hepatic / PK_NORMALIZATION['hepatic_production'],
        net_balance / PK_NORMALIZATION['net_balance'],
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
        pk_features: (N, 6) array from build_continuous_pk_features
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
            isf_schedule = df.attrs.get('isf_schedule', [])
            cr_schedule = df.attrs.get('cr_schedule', [])

            # Build continuous PK features (ISF/CR expanded from schedules)
            pk = build_continuous_pk_features(
                df, dia_hours=dia, peak_min=55.0,
                isf_schedule=isf_schedule, cr_schedule=cr_schedule,
                carb_abs_hours=3.0, scheduled_basal=None, verbose=verbose)

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
