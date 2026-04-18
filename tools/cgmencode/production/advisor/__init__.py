"""
advisor/ — Settings advisory subpackage.

Decomposed from settings_advisor.py for maintainability.
All public symbols are re-exported here for backward compatibility.
"""

from ._simulation import simulate_tir_with_settings, PERIODS, SIMULATION_STEPS, DECAY_TARGET, DECAY_RATE
from ._isf_advisors import (
    advise_isf, advise_isf_nonlinearity, advise_isf_segmented,
    advise_forward_sim_optimization, advise_correction_isf,
    advise_circadian_isf, advise_circadian_isf_profiled,
    advise_override_isf, advise_patience_mode,
    advise_isf_dual_phase, advise_response_curve_isf,
    advise_sc_ceiling, advise_dose_response_isf,
)
from ._cr_advisors import (
    advise_cr, advise_effective_cr, advise_cr_adequacy,
    advise_context_cr, compute_context_cr_adjustment,
)
from ._basal_advisors import (
    advise_basal, advise_overnight_basal_quadrant,
    advise_loop_workload, assess_overnight_drift,
    compute_loop_workload, advise_carb_context_overnight,
)
from ._pipeline import (
    generate_settings_advice, analyze_periods,
    advise_correction_threshold,
    _consolidate_recommendations, _deduplicate_same_direction,
    determine_optimization_phase, prioritize_recommendations,
    compute_settings_quality_score,
    compute_advisory_confidence_tier, apply_confidence_tier_to_recommendations,
    apply_safety_clamp,
)
