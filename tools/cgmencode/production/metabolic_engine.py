"""
metabolic_engine.py — Supply/demand flux decomposition (physics layer).

Research basis: EXP-441 (metabolic throughput), EXP-601+ (flux residuals),
               EXP-1771 (hepatic base rate validation: 1.5 wins 9/11 patients),
               EXP-1772 (demand calibration: 48% fasting RMSE reduction)
Key finding: 107ms per patient, captures insulin-glucose tug-of-war

This module computes the instantaneous supply (hepatic + carbs) and
demand (insulin action) that drive glucose changes. The residual
between predicted and actual change reveals spike artifacts, sensor
noise, and unannounced meals.

Physics model:
    dBG/dt ≈ supply - demand + decay_toward_120
    supply = hepatic_production + carb_absorption
    demand = insulin_action (calibrated to patient's basal rate)
    residual = actual_dBG - predicted_dBG
"""

from __future__ import annotations

import numpy as np

from .types import MetabolicState, PatientData, PatientProfile


# Hill equation parameters for hepatic production (from continuous_pk.py)
_HILL_N = 1.5          # Hill coefficient
_HILL_K = 2.0          # Half-max IOB (Units)
_BASE_EGP = 1.5        # mg/dL per 5-min step at zero insulin
                       # EXP-1771: 1.5 wins 9/11 patients vs 1.0 (fasting RMSE)
_CIRCADIAN_AMP = 0.15  # Dawn phenomenon amplitude (15% variation)

# Glucose decay toward equilibrium (from exp_autoresearch_681.py:50)
_DECAY_TARGET = 120.0  # mg/dL equilibrium
_DECAY_RATE = 0.005    # per 5-min step


def _compute_hepatic_production(iob: np.ndarray,
                                hours: np.ndarray,
                                weight_kg: float = 70.0) -> np.ndarray:
    """Estimate hepatic glucose production (EGP).

    Hill equation for insulin suppression × circadian modulation.
    Based on cgmsim-lib liver.ts and UVA/Padova model.

    Args:
        iob: (N,) insulin on board in Units.
        hours: (N,) fractional hour of day (0-24).
        weight_kg: patient weight for base rate scaling.

    Returns:
        (N,) hepatic production in mg/dL per 5-min step.
    """
    base_rate = _BASE_EGP * (weight_kg / 70.0)

    # Hill equation suppression: high IOB → low EGP
    iob_safe = np.maximum(np.nan_to_num(iob, nan=0.0), 0.0)
    suppression = iob_safe ** _HILL_N / (iob_safe ** _HILL_N + _HILL_K ** _HILL_N)
    egp_insulin = base_rate * (1.0 - suppression)

    # Circadian modulation: peaks ~5 AM (dawn phenomenon)
    circadian = 1.0 + _CIRCADIAN_AMP * np.sin(2.0 * np.pi * (hours - 5.0) / 24.0)

    return np.maximum(egp_insulin * circadian, 0.0)


def _extract_hours(timestamps: np.ndarray) -> np.ndarray:
    """Extract fractional hours from Unix timestamps (ms)."""
    try:
        import pandas as pd
        dt = pd.to_datetime(timestamps, unit='ms')
        return np.asarray(dt.hour + dt.minute / 60.0, dtype=np.float64)
    except Exception:
        # Fallback: assume timestamps are already in seconds or ms
        ts = np.asarray(timestamps, dtype=np.float64)
        seconds = ts / 1000.0 if ts.max() > 1e12 else ts
        return (seconds % 86400) / 3600.0


def _calibrate_demand(demand: np.ndarray,
                      basal_rate: float,
                      isf: float,
                      hours: np.ndarray) -> np.ndarray:
    """Apply patient-specific demand calibration (EXP-1772).

    At the patient's scheduled basal rate, insulin demand should equal
    hepatic glucose production — the definition of metabolic steady state.

    Without calibration, demand = |ΔIOB| × ISF can be far from hepatic
    output (e.g., patient i: 10× overshoot). This normalizes demand so
    that fasting periods show near-zero predicted drift.

    EXP-1772 validation: fasting RMSE 19.6 → 10.2 (48% reduction),
    fasting bias -5.2 → -0.1, 10/11 patients improve.
    """
    demand_at_basal = basal_rate * isf / 12.0  # mg/dL per step at scheduled basal
    if demand_at_basal < 0.01:
        return demand

    # Mean hepatic production at typical IOB (basal accumulation ≈ rate × DIA/2)
    typical_iob = basal_rate * 2.5  # ~half of 5h DIA accumulation
    reference_hours = np.linspace(0, 24, 288)
    mean_hepatic = float(np.mean(_compute_hepatic_production(
        np.full(288, typical_iob), reference_hours)))

    cal_factor = mean_hepatic / demand_at_basal
    return demand * cal_factor


def compute_metabolic_state(patient: PatientData) -> MetabolicState:
    """Compute full supply-demand flux decomposition.

    This is the primary API. Wraps the physics model with production
    error handling and graceful degradation.

    Args:
        patient: PatientData with glucose, timestamps, and optionally
                 iob/cob/bolus/carbs/basal_rate.

    Returns:
        MetabolicState with supply, demand, hepatic, carb_supply,
        net_flux, and residual arrays.
    """
    N = patient.n_samples
    glucose = np.nan_to_num(patient.glucose.astype(np.float64), nan=120.0)
    hours = _extract_hours(patient.timestamps)
    profile = patient.profile

    # Extract scalar ISF (always mg/dL) and CR from profile schedules
    isf = _median_schedule_value(profile.isf_mgdl(), default=50.0)
    cr = _median_schedule_value(profile.cr_schedule, default=10.0)

    # ── Hepatic production ────────────────────────────────────────
    if patient.has_insulin_data:
        iob = np.nan_to_num(patient.iob.astype(np.float64), nan=0.0)
    else:
        iob = np.zeros(N)
    hepatic = _compute_hepatic_production(iob, hours)

    # ── Carb absorption (from COB deltas) ─────────────────────────
    if patient.cob is not None:
        cob = np.nan_to_num(patient.cob.astype(np.float64), nan=0.0)
        delta_cob = np.zeros(N)
        delta_cob[1:] = cob[:-1] - cob[1:]  # positive = being absorbed
        carb_supply = np.abs(delta_cob * (isf / max(cr, 1.0)))
    else:
        carb_supply = np.zeros(N)

    supply = hepatic + carb_supply

    # ── Insulin demand (from IOB deltas) ──────────────────────────
    if patient.has_insulin_data:
        delta_iob = np.zeros(N)
        delta_iob[1:] = iob[:-1] - iob[1:]  # positive = being absorbed
        demand = np.abs(delta_iob * isf)

        # Demand calibration (EXP-1772: reduces fasting RMSE 48%, 10/11 patients)
        # At scheduled basal rate, demand should equal hepatic production
        # (steady-state definition). Without calibration, |ΔIOB|×ISF may
        # not balance the Hill-equation hepatic output.
        basal_rate = _median_schedule_value(profile.basal_schedule, default=0.8)
        demand = _calibrate_demand(demand, basal_rate, isf, hours)
    else:
        demand = np.zeros(N)

    # Ensure non-negative
    supply = np.maximum(supply, 0.0)
    demand = np.maximum(demand, 0.0)
    net_flux = np.asarray(supply - demand, dtype=np.float64)

    # ── Residual: actual ΔBG vs physics prediction ────────────────
    bg_decay = (_DECAY_TARGET - glucose) * _DECAY_RATE
    predicted_change = net_flux[:-1] + bg_decay[:-1]
    actual_change = np.diff(glucose)
    residual = np.zeros(N)
    residual[1:] = actual_change - predicted_change

    return MetabolicState(
        supply=supply,
        demand=demand,
        hepatic=hepatic,
        carb_supply=carb_supply,
        net_flux=net_flux,
        residual=residual,
    )


def _median_schedule_value(schedule: list, default: float = 50.0) -> float:
    """Extract median value from a Nightscout schedule list."""
    if not schedule:
        return default
    values = []
    for entry in schedule:
        v = entry.get('value') or entry.get('carbratio') or entry.get('sensitivity')
        if v is not None:
            values.append(float(v))
    return float(np.median(values)) if values else default
