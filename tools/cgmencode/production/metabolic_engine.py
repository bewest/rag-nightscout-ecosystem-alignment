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

from .types import MetabolicState, PatientData, PatientProfile, DIADiscrepancy, ResponderType, TwoComponentDIA


# Hill equation parameters for hepatic production (from continuous_pk.py)
_HILL_N = 1.5          # Hill coefficient
_HILL_K = 2.0          # Half-max IOB (Units)
_BASE_EGP = 1.5        # mg/dL per 5-min step at zero insulin
                       # EXP-1771: 1.5 wins 9/11 patients vs 1.0 (fasting RMSE)
_CIRCADIAN_AMP = 0.15  # Dawn phenomenon amplitude (15% variation)

# Glucose decay toward equilibrium (from exp_autoresearch_681.py:50)
_DECAY_TARGET = 120.0  # mg/dL equilibrium
_DECAY_RATE = 0.005    # per 5-min step

# Two-component DIA parameters (EXP-2525)
_FAST_TAU_HOURS = 0.8          # time constant for fast insulin action
_PERSISTENT_FRACTION = 0.37    # fraction of total effect that's persistent (C/(A+C))
_PERSISTENT_WINDOW_HOURS = 12.0  # lookback window for persistent HGP suppression


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

    # 4-harmonic circadian modulation (EXP-1774: +77% R², all 11 patients improve)
    # Periods: 24h (dawn phenomenon), 12h (post-prandial), 8h (tri-daily), 6h (quad)
    # Phase-shifted so 24h component peaks ~5 AM (dawn phenomenon)
    _HARMONIC_PERIODS = [24.0, 12.0, 8.0, 6.0]
    _HARMONIC_AMPS = [_CIRCADIAN_AMP, _CIRCADIAN_AMP * 0.4,
                      _CIRCADIAN_AMP * 0.2, _CIRCADIAN_AMP * 0.1]
    circadian = np.ones_like(hours, dtype=np.float64)
    for amp, period in zip(_HARMONIC_AMPS, _HARMONIC_PERIODS):
        circadian += amp * np.sin(2.0 * np.pi * (hours - 5.0) / period)

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


# ── Two-Component DIA Decomposition (EXP-2525) ──────────────────────

def _compute_total_insulin_delivered(bolus: np.ndarray,
                                     basal_rate: np.ndarray,
                                     window_steps: int) -> np.ndarray:
    """Compute rolling total insulin delivered over a lookback window.

    Args:
        bolus: (N,) bolus insulin per 5-min interval (Units).
        basal_rate: (N,) basal rate per interval (U/hr).
        window_steps: number of 5-min steps in the lookback window.

    Returns:
        (N,) total insulin delivered in the lookback window (Units).
    """
    # Per-interval insulin delivery: bolus + basal converted to per-step
    per_step = bolus + basal_rate * (5.0 / 60.0)
    # Cumulative sum for efficient rolling window
    cumsum = np.concatenate([[0.0], np.cumsum(per_step)])
    total = np.zeros(len(bolus))
    for i in range(len(bolus)):
        start = max(0, i + 1 - window_steps)
        total[i] = cumsum[i + 1] - cumsum[start]
    return total


def decompose_two_component_dia(patient: PatientData,
                                metabolic: MetabolicState,
                                ) -> TwoComponentDIA:
    """Decompose insulin demand into fast-action and persistent HGP suppression.

    EXP-2525 discovered that insulin's glucose effect has two components:
    1. Fast action (τ=0.8h): exponentially-decaying insulin-mediated uptake.
       This is what the pump's IOB curve models.
    2. Persistent HGP suppression (>12h): once insulin triggers HGP
       suppression, it persists as a step function far beyond IOB decay.

    The fast component is proportional to demand (IOB-change × ISF),
    weighted by the fast fraction (1 - 0.37 = 0.63).

    The persistent component is proportional to total insulin delivered
    in the last 12h, weighted by the persistent fraction (0.37).
    The persistent effect is normalized to be in the same units as the
    fast effect (mg/dL per 5-min step) using ISF scaling.

    Args:
        patient: PatientData with IOB, bolus, and basal_rate data.
        metabolic: MetabolicState from compute_metabolic_state.

    Returns:
        TwoComponentDIA with decomposed effects.
    """
    N = patient.n_samples
    fast_frac = 1.0 - _PERSISTENT_FRACTION
    profile = patient.profile
    isf = _median_schedule_value(profile.isf_mgdl(), default=50.0)

    # Fast component: existing demand × fast fraction, shaped by τ
    iob_fast_effect = metabolic.demand * fast_frac

    # Persistent component: proportional to total insulin in 12h window
    window_steps = int(_PERSISTENT_WINDOW_HOURS * 12)  # 12h × 12 steps/h = 144

    if (patient.bolus is not None and patient.basal_rate is not None
            and patient.has_insulin_data):
        bolus = np.nan_to_num(patient.bolus.astype(np.float64), nan=0.0)
        basal = np.nan_to_num(patient.basal_rate.astype(np.float64), nan=0.0)
        total_insulin_12h = _compute_total_insulin_delivered(
            bolus, basal, window_steps)
    elif patient.has_insulin_data:
        # Fallback: estimate from IOB curve (less accurate)
        iob = np.nan_to_num(patient.iob.astype(np.float64), nan=0.0)
        total_insulin_12h = iob * (_PERSISTENT_WINDOW_HOURS / 5.0)
    else:
        total_insulin_12h = np.zeros(N)

    # Scale persistent effect: insulin × ISF / window_steps gives
    # mg/dL per step equivalent. This normalizes persistent effect
    # to the same units as fast effect.
    mean_demand = float(np.mean(metabolic.demand))
    if mean_demand > 1e-12:
        # Calibrate persistent to be _PERSISTENT_FRACTION of total effect
        mean_total_ins = float(np.mean(total_insulin_12h))
        if mean_total_ins > 1e-12:
            scale = (mean_demand * _PERSISTENT_FRACTION
                     / (mean_total_ins * fast_frac))
        else:
            scale = 0.0
    else:
        scale = 0.0

    iob_persistent_effect = total_insulin_12h * scale

    return TwoComponentDIA(
        iob_fast_effect=iob_fast_effect,
        iob_persistent_effect=iob_persistent_effect,
        total_insulin_12h=total_insulin_12h,
        fast_fraction=fast_frac,
        persistent_fraction=_PERSISTENT_FRACTION,
        fast_tau_hours=_FAST_TAU_HOURS,
        persistent_window_hours=_PERSISTENT_WINDOW_HOURS,
    )


# ── DIA Discrepancy Estimation (EXP-2351–2358) ──────────────────────

# IOB DIA: pump's modeled insulin activity (2.8-3.8h across patients)
# Glucose DIA: actual glucose response duration (5-20h across patients)
# Discrepancy ratio: glucose_dia / iob_dia (typically 1.5-5×)

# Population defaults from EXP-2351 (11-patient study)
_DEFAULT_IOB_DIA_HOURS = 3.3      # median IOB decay DIA
_SLOW_ONSET_THRESHOLD_MIN = 40.0  # onset >40 min → slow responder


def estimate_dia_discrepancy(patient: PatientData,
                             metabolic: MetabolicState,
                             ) -> DIADiscrepancy:
    """Estimate DIA discrepancy between IOB decay and glucose response.

    The pump's insulin model decays faster than insulin's actual glucose
    effect. This function estimates both DIAs and reports the discrepancy.

    IOB DIA: estimated from IOB curve half-life (pump model).
    Glucose DIA: estimated from correction bolus response duration.

    Research finding (EXP-2351): IOB DIA = 2.8-3.8h, glucose DIA = 5-20h.
    8/11 patients are slow responders (onset >40 min).

    Args:
        patient: PatientData with IOB and glucose.
        metabolic: MetabolicState from compute_metabolic_state.

    Returns:
        DIADiscrepancy with both DIA estimates and responder type.
    """
    profile = patient.profile

    # Extract profile DIA (if available) or use population default
    profile_dia = getattr(profile, 'dia_hours', None)
    if profile_dia is None or profile_dia <= 0:
        profile_dia = 5.0  # Nightscout default

    # ── IOB decay DIA estimation ──────────────────────────────────
    iob_dia = _DEFAULT_IOB_DIA_HOURS
    if patient.has_insulin_data and len(patient.iob) > 288:
        iob = np.nan_to_num(patient.iob.astype(np.float64), nan=0.0)
        # Estimate half-life from IOB autocorrelation
        iob_nz = iob[iob > 0.1]
        if len(iob_nz) > 100:
            # Use the IOB decay curve: find where IOB drops to 10% of peak
            # after a bolus. Approximate from IOB distribution percentiles.
            p90 = float(np.percentile(iob_nz, 90))
            # Steps where IOB goes from high to 10% of p90
            high_mask = iob > p90 * 0.9
            if np.sum(high_mask) > 10:
                # Simple half-life estimate from high IOB decay
                segments = np.diff(np.where(high_mask)[0])
                if len(segments) > 5:
                    median_duration = float(np.median(segments[segments > 1]))
                    iob_dia = min(max(median_duration * 5 / 60 * 2.5, 2.0), 6.0)

    # ── Glucose response DIA estimation ───────────────────────────
    # From correction bolus analysis: find boluses during high BG,
    # measure how long until glucose effect diminishes
    glucose_dia = None
    onset_min = None
    nadir_min = None
    isf_ratio = None

    glucose = np.nan_to_num(patient.glucose.astype(np.float64), nan=120.0)
    isf = _median_schedule_value(profile.isf_mgdl(), default=50.0)

    if patient.has_insulin_data and patient.bolus is not None:
        bolus = np.nan_to_num(patient.bolus.astype(np.float64), nan=0.0)
        N = len(glucose)

        correction_drops = []
        onset_times = []
        nadir_times = []

        for i in range(N - 72):  # need 6h post-bolus window
            if bolus[i] < 0.3 or glucose[i] < 150:
                continue
            # Skip if there are carbs nearby (want pure corrections)
            if patient.carbs is not None:
                carbs_nearby = np.nan_to_num(patient.carbs[max(0,i-6):i+6], nan=0.0)
                if float(np.sum(carbs_nearby)) > 1.0:
                    continue

            pre_bg = float(glucose[i])
            # Find onset: first step where BG drops >1 mg/dL from pre
            onset = None
            for j in range(1, min(36, N - i)):
                if glucose[i + j] < pre_bg - 1.0:
                    onset = j * 5  # minutes
                    break

            # Find nadir in 6h window
            window = glucose[i:i+72]
            nadir_idx = int(np.argmin(window))
            nadir_bg = float(window[nadir_idx])
            drop = pre_bg - nadir_bg

            if drop > 10 and nadir_idx > 0:
                correction_drops.append(drop / bolus[i])  # mg/dL per unit
                nadir_times.append(nadir_idx * 5)
                if onset is not None:
                    onset_times.append(onset)

                # Find when glucose returns to 90% of pre-BG
                for j in range(nadir_idx + 1, min(len(window), 72)):
                    if window[j] > pre_bg - drop * 0.1:
                        # This is the glucose response duration
                        glucose_dia_candidate = j * 5 / 60  # hours
                        break

        if correction_drops:
            effective_isf = float(np.median(correction_drops))
            isf_ratio = effective_isf / isf if isf > 0 else None

        if nadir_times:
            nadir_min = float(np.median(nadir_times))
            # Glucose DIA ≈ 2.5× time to nadir (exponential decay heuristic)
            glucose_dia = nadir_min * 2.5 / 60  # hours

        if onset_times:
            onset_min = float(np.median(onset_times))

    # ── Responder type classification ─────────────────────────────
    responder = ResponderType.SLOW  # default (8/11 in EXP-2355)
    if onset_min is not None:
        if onset_min < 25:
            responder = ResponderType.FAST
        elif onset_min <= _SLOW_ONSET_THRESHOLD_MIN:
            responder = ResponderType.MEDIUM

    # ── Discrepancy ratio and interpretation ──────────────────────
    discrepancy = None
    interp_parts = [f"IOB decay DIA: {iob_dia:.1f}h"]

    if glucose_dia is not None:
        discrepancy = glucose_dia / iob_dia if iob_dia > 0 else None
        interp_parts.append(f"Glucose response DIA: {glucose_dia:.1f}h")
        if discrepancy is not None and discrepancy > 1.5:
            interp_parts.append(
                f"Discrepancy: {discrepancy:.1f}× — insulin affects glucose "
                f"much longer than the pump model assumes."
            )
    else:
        interp_parts.append("Glucose response DIA: insufficient correction data.")

    interp_parts.append(f"Responder type: {responder.value}")
    if isf_ratio is not None:
        interp_parts.append(f"Effective ISF ratio: {isf_ratio:.2f}×")

    return DIADiscrepancy(
        iob_dia_hours=iob_dia,
        glucose_dia_hours=glucose_dia,
        discrepancy_ratio=discrepancy,
        responder_type=responder,
        onset_minutes=onset_min,
        nadir_minutes=nadir_min,
        isf_ratio=isf_ratio,
        interpretation=" | ".join(interp_parts),
    )
