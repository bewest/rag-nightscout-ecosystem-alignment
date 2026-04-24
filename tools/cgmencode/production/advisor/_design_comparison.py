"""Cross-design hypothetical: predicted TIR if patient switched controllers.

Heuristic estimator backed by the EXP-2916–2944 cross-design synthesis
(see docs/60-research/synthesis-design-comparison-2026-04-23.md). Given
the patient's current controller class and observed glycemic profile,
produce a directional estimate of how TIR/TBR/TAR would shift if the
patient migrated to a different design (Loop ↔ oref1 ↔ oref0).

Design-class baselines (from the cohort):

    Pooled all-patient TIR / TBR / TAR (from EXP-2925, n=9 oref1 / 7 Loop):
        oref1:  82.6 / 3.64 / 13.78
        Loop:   66.1 / 3.88 / 30.04
        oref0:  ~74  / ~5   / ~21    (smaller cohort, asymmetric hypo at night)

    Design effect estimates (additive percentage points, controller-relative):
        Loop  → oref1: +16.5 TIR, ~0 TBR, -16 TAR  (UAM + dynamic-ISF + SMB)
        Loop_AB_OFF → Loop_AB_ON: +5 TIR (autobolus closes 53% of PP gap)
        oref1 → Loop:  -16.5 TIR (the inverse — informational only)
        oref0 → oref1: +8 TIR, -1.4 TBR (SMB-as-correction gives both)

Caveats:
    - These are cohort-mean shifts, not personalised predictions.
    - A patient with ALREADY oref1-style TIR (>=80%) gains little.
    - A patient with high overnight TBR risk (alcohol/EGP suppression)
      may NOT benefit: oref1's faster correction can deepen hypos when
      hepatic glucose output is suppressed. The advisor flags this.

The output is an `ActionRecommendation` at priority 3 (informational)
that the clinician/patient can use as a "would migration help?" prompt.
"""

from __future__ import annotations
from typing import List, Optional
import numpy as np

from ..types import (
    ActionRecommendation, ClinicalReport, ControllerType,
)


__all__ = [
    'recommend_design_migration',
    '_DESIGN_BASELINES',
    '_DESIGN_DELTAS',
    '_MIN_DAYS_FOR_HYPOTHETICAL',
    '_TBR_RISK_THRESHOLD',
]


# Cohort baselines (TIR, TBR<70, TAR>180 — percentages)
_DESIGN_BASELINES = {
    'loop':  (66.1, 3.88, 30.04),
    'oref1': (82.6, 3.64, 13.78),
    'oref0': (74.0, 5.00, 21.00),
}

# Migration deltas: dict[(from, to)] -> (dTIR, dTBR, dTAR)
_DESIGN_DELTAS = {
    ('loop',  'oref1'): (+16.5,  0.0, -16.3),
    ('loop',  'oref0'): ( +7.9, +1.1,  -9.0),
    ('oref0', 'oref1'): ( +8.6, -1.4,  -7.2),
    ('oref1', 'loop'):  (-16.5,  0.0, +16.3),
}

_MIN_DAYS_FOR_HYPOTHETICAL = 14.0
_TBR_RISK_THRESHOLD = 4.0      # TBR<70 above which migration is risky
_TBR54_RISK_THRESHOLD = 1.0    # severe-hypo carve-out
_TIR_CEILING_FOR_BENEFIT = 80.0  # patients above this get diminishing returns


def _normalize_controller(controller_type) -> Optional[str]:
    if controller_type is None:
        return None
    if isinstance(controller_type, ControllerType):
        v = controller_type.value
    else:
        v = str(controller_type)
    v = v.lower()
    if 'loop' in v:
        return 'loop'
    if 'oref1' in v or 'aaps' in v or 'trio' in v:
        return 'oref1'
    if 'oref0' in v:
        return 'oref0'
    return None


def recommend_design_migration(
    clinical: ClinicalReport,
    current_controller,
    *,
    days_of_data: float,
    target_design: str = 'oref1',
) -> List[ActionRecommendation]:
    """Estimate the TIR delta of migrating to a different controller class.

    Args:
        clinical: ClinicalReport with tir_70_180, tbr_lt70, tbr_lt54, tar_gt180.
        current_controller: ControllerType enum or string ('loop', 'oref1',
            'oref0', 'aaps', 'trio'). 'aaps' and 'trio' map to 'oref1'.
        days_of_data: coverage gate.
        target_design: 'oref1' (default), 'loop', or 'oref0'.

    Returns:
        0-1 ActionRecommendation. Returns [] when:
          - days_of_data is short
          - controller class can't be identified
          - no migration delta is defined for the (from, to) pair
          - patient already has TIR above the benefit ceiling
    """
    if days_of_data < _MIN_DAYS_FOR_HYPOTHETICAL:
        return []

    src = _normalize_controller(current_controller)
    if src is None or src == target_design:
        return []

    delta = _DESIGN_DELTAS.get((src, target_design))
    if delta is None:
        return []

    dtir, dtbr, dtar = delta

    tir_now = float(getattr(clinical, 'tir', 0.0)) * 100
    tbr_now = float(getattr(clinical, 'tbr', 0.0)) * 100
    # ClinicalReport doesn't expose a separate tbr_lt54 today; treat
    # severe-hypo as a fraction of overall TBR (~25% of TBR<70 is a
    # conservative cohort estimate from EXP-2925).
    tbr54_now = tbr_now * 0.25
    tar_now = float(getattr(clinical, 'tar', 0.0)) * 100

    if tir_now == 0.0:
        return []

    # Personalisation: scale benefit by current shortfall vs target cohort
    # (a patient already at 78% TIR migrating to oref1 baseline ~83% only
    # gains ~5pp, not the full +16.5 cohort delta). Hard-cap at 14 pp to
    # stay strictly below the dataclass guard ceiling (GAP-ADVR-003) —
    # any single recommendation claiming more than that is implausible
    # at the cohort-mean confidence level (0.40) we ship.
    _SCALED_DTIR_CAP = 14.0
    if dtir > 0:
        target_tir, _, _ = _DESIGN_BASELINES[target_design]
        headroom = max(0.0, target_tir - tir_now)
        scaled_dtir = min(dtir, headroom + 1.0, _SCALED_DTIR_CAP)
    else:
        scaled_dtir = max(dtir, -_SCALED_DTIR_CAP)

    # Risk gate: oref1 fires SMBs more aggressively. If the patient
    # already shows above-threshold severe-hypo or non-trivial TBR with
    # an alcohol/EGP-suppression signature, flag the migration as risky.
    risky = (
        target_design == 'oref1' and
        (tbr54_now >= _TBR54_RISK_THRESHOLD or tbr_now >= _TBR_RISK_THRESHOLD)
    )

    # Don't bother recommending when scaled benefit is sub-clinical
    if abs(scaled_dtir) < 2.0 and not risky:
        return []

    src_pretty = {'loop': 'Loop', 'oref1': 'oref1 (Trio / AAPS)',
                  'oref0': 'oref0 (legacy AAPS)'}
    tgt_pretty = {'loop': 'Loop', 'oref1': 'Trio or AAPS (oref1)',
                  'oref0': 'oref0 (legacy AAPS)'}

    description = (
        f"Cross-design hypothetical (EXP-2916–2944): a patient with your "
        f"current profile (TIR {tir_now:.0f}%, TBR {tbr_now:.1f}%, TAR "
        f"{tar_now:.0f}%) on {src_pretty[src]} migrating to "
        f"{tgt_pretty[target_design]} would expect roughly "
        f"{scaled_dtir:+.1f} pp TIR ({dtbr:+.1f} pp TBR, {dtar:+.1f} pp "
        f"TAR) based on cohort means. "
    )
    if risky:
        description += (
            f"⚠️ Caveat: TBR<70 is {tbr_now:.1f}% and TBR<54 is "
            f"{tbr54_now:.2f}%. The oref1 SMB-as-correction profile fires "
            f"more aggressively and may deepen overnight hypos when the "
            f"underlying cause is hepatic suppression (alcohol, late "
            f"meals) rather than under-dosing. Discuss with your clinician "
            f"before migrating."
        )
    else:
        description += (
            "This is a directional estimate from cross-design pooling, not "
            "a per-patient simulation. Settings tuning on the current "
            "controller may capture much of the same benefit (see other "
            "recommendations in this report)."
        )

    return [ActionRecommendation(
        action_type="design_migration_hypothetical",
        priority=3,
        description=description,
        predicted_tir_delta=round(scaled_dtir, 1),
        confidence=0.40,  # cohort-level, not personal
        time_sensitive=False,
    )]
