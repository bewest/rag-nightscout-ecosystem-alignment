"""
patient_onboarding.py — Cold start protocol and population defaults.

Research basis: EXP-769 (cross-patient transfer, 99.4% universal),
               EXP-777 (warm-start + 1 week), EXP-815 (population warm-start)

Key findings:
- Population physics parameters retain 99.4% of personal R² (gap=-0.004)
- Day 1 population defaults: R²≈0.437
- Warm-start + 1 week personal: R²≈0.652 (beats full personal 0.625)
- Full personal overfits to noisy early periods

State machine:
  POPULATION_DEFAULTS (day 0-2) → EARLY_PERSONAL (day 3-6) →
  WARM_START_PERSONAL (day 7+) → FULLY_CALIBRATED (day 14+)
"""

from __future__ import annotations

from typing import Dict, Optional

from .types import OnboardingPhase, OnboardingState


# Population-universal physics parameters (from EXP-769)
# These retain 99.4% of personal R² across all 11 test patients
POPULATION_DEFAULTS: Dict = {
    'ar_weight': 0.12,        # Autoregressive weight on lag-1 residual
    'decay_rate': 0.005,      # Glucose decay toward equilibrium per 5-min step
    'decay_target': 120.0,    # mg/dL equilibrium target
    'hill_n': 1.5,            # Hill coefficient for hepatic suppression
    'hill_k': 2.0,            # Half-max IOB for Hill equation
    'base_egp': 1.0,          # Basal hepatic production (mg/dL per 5-min)
    'circadian_amp': 0.15,    # Dawn phenomenon amplitude
    'ridge_alpha': 1.0,       # Ridge regression regularization
    'spike_sigma': 2.0,       # Spike detection threshold
    'isf_multiplier': 2.91,   # Effective ISF / profile ISF ratio (EXP-747)
}

# Phase transition thresholds (days of data required)
_PHASE_THRESHOLDS = {
    OnboardingPhase.POPULATION_DEFAULTS: 0.0,
    OnboardingPhase.EARLY_PERSONAL: 3.0,
    OnboardingPhase.WARM_START_PERSONAL: 7.0,
    OnboardingPhase.FULLY_CALIBRATED: 14.0,
}


def determine_phase(days_of_data: float) -> OnboardingPhase:
    """Determine onboarding phase from data availability.

    Args:
        days_of_data: total days of CGM data available.

    Returns:
        Current OnboardingPhase.
    """
    if days_of_data >= 14.0:
        return OnboardingPhase.FULLY_CALIBRATED
    elif days_of_data >= 7.0:
        return OnboardingPhase.WARM_START_PERSONAL
    elif days_of_data >= 3.0:
        return OnboardingPhase.EARLY_PERSONAL
    else:
        return OnboardingPhase.POPULATION_DEFAULTS


def get_onboarding_state(days_of_data: float,
                         personal_params: Optional[Dict] = None) -> OnboardingState:
    """Build complete onboarding state for a patient.

    The state machine controls which model parameters to use:
    - POPULATION_DEFAULTS: use POPULATION_DEFAULTS dict directly
    - EARLY_PERSONAL: begin collecting personal calibration data
    - WARM_START_PERSONAL: blend population + personal (this is SOTA)
    - FULLY_CALIBRATED: personal model with population initialization

    Args:
        days_of_data: total days of CGM + treatment data.
        personal_params: calibrated personal parameters, if available.

    Returns:
        OnboardingState with phase, parameters, and readiness flags.
    """
    phase = determine_phase(days_of_data)

    # Expected R² by phase (from EXP-777, EXP-815)
    expected_r2 = {
        OnboardingPhase.POPULATION_DEFAULTS: 0.437,
        OnboardingPhase.EARLY_PERSONAL: 0.52,
        OnboardingPhase.WARM_START_PERSONAL: 0.652,
        OnboardingPhase.FULLY_CALIBRATED: 0.652,
    }

    using_population = phase in (
        OnboardingPhase.POPULATION_DEFAULTS,
        OnboardingPhase.EARLY_PERSONAL,
    )

    # Warm-start blends population + personal (research-proven best)
    active_params = dict(POPULATION_DEFAULTS)
    if personal_params and phase in (
        OnboardingPhase.WARM_START_PERSONAL,
        OnboardingPhase.FULLY_CALIBRATED,
    ):
        active_params.update(personal_params)

    return OnboardingState(
        phase=phase,
        days_of_data=days_of_data,
        model_r2=expected_r2.get(phase),
        using_population_defaults=using_population,
        population_params=dict(POPULATION_DEFAULTS),
        personal_params=personal_params,
        ready_for_production=(phase != OnboardingPhase.POPULATION_DEFAULTS),
    )


def get_effective_params(state: OnboardingState) -> Dict:
    """Get the active model parameters for the current onboarding phase.

    Merges population defaults with any available personal calibration.

    Returns:
        Dict of model parameters to use for inference.
    """
    params = dict(POPULATION_DEFAULTS)
    if not state.using_population_defaults and state.personal_params:
        params.update(state.personal_params)
    return params
