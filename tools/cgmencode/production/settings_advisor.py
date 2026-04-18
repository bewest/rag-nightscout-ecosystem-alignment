"""
settings_advisor.py — Counterfactual TIR prediction for therapy changes.

Research basis: EXP-693 (basal assessment), EXP-694 (CR effectiveness),
               EXP-747 (ISF discrepancy 2.91×), EXP-574/575 (counterfactual ISF/CR),
               EXP-2271 (circadian ISF 4.6-9×, 2-zone captures 61-90%),
               EXP-2341 (context-aware CR: pre-BG + time + IOB, R²+0.28),
               EXP-2551 (two-component DIA + power-law ISF: MAE 0.30pp, r=0.933)

This module is a backward-compatible re-export shim. The actual
implementation lives in the advisor/ subpackage:

    advisor/_simulation.py     — Physics simulation (EXP-2551)
    advisor/_isf_advisors.py   — 13 ISF advisory variants
    advisor/_cr_advisors.py    — CR advisory functions
    advisor/_basal_advisors.py — Basal, overnight drift, workload
    advisor/_pipeline.py       — Wiring, consolidation, safety clamp

All public symbols are re-exported here so existing imports continue to work:
    from .settings_advisor import generate_settings_advice  # still works
"""

# Re-export everything from submodules for backward compatibility
from .advisor._simulation import *        # noqa: F401,F403
from .advisor._isf_advisors import *      # noqa: F401,F403
from .advisor._cr_advisors import *       # noqa: F401,F403
from .advisor._basal_advisors import *    # noqa: F401,F403
from .advisor._pipeline import *          # noqa: F401,F403
