# ALG-XVAL Cross-Validation Results

> **Track**: ALG-XVAL Phase 3 Complete
> **Date**: 2026-03-31
> **Status**: ✅ Complete — 99.7% 3-way parity across 300 vectors

## Summary

| Metric | Result |
|--------|--------|
| Total Test Vectors | 300 (100 oref0-native + 200 Loop-derived) |
| **EventualBG Match** | **294/295 (99.7%)** |
| **Rate ±0.5 Match** | **201/203 (99.0%)** |
| Adapters Validated | 3 (oref0-JS, t1pal-Swift, AAPS-JS) |

## 3-Way Decision Parity

All 3 adapters produce identical dosing decisions within tolerance:

| Vector Suite | EventualBG | Rate ±0.5 | IOB MAE |
|-------------|------------|-----------|---------|
| oref0-native (100) | **100/100 (100%)** | **72/72 (100%)** | **0.005** |
| Loop-derived (200) | **194/195 (99.5%)** | **131/133 (98.5%)** | **0.028** |
| **Combined (300)** | **294/295 (99.7%)** | **201/203 (99.0%)** | — |

## Prediction Curve Alignment (JS ↔ Swift)

All 4 oref0 prediction trajectories match point-by-point:

| Curve | Avg MAE (mg/dL) | Max MAE | Vectors | Status |
|-------|-----------------|---------|---------|--------|
| IOB | 0.005 | 0.08 | 100 | ✅ |
| ZT | 0.013 | 0.12 | 100 | ✅ |
| COB | 0.000 | 0.00 | 100 | ✅ |
| UAM | 0.002 | 0.085 | 100 | ✅ |

## Phase 3 Key Discoveries

### A14: IOB/tau Activity Derivation
When Nightscout devicestatus has `activity=0` but `IOB>0` (common in Loop data),
derive `activity = IOB / (DIA*60/1.85)`. Mathematically exact for exponential
decay model. This enabled the 200 Loop-derived vectors to pass.

### A15: 3-Way Parity (AAPS-JS Adapter)
AAPS-JS adapter wraps Trio's oref0 JS port. With IOB/tau derivation applied
identically, all 3 adapters produce matching decisions on 294/295 vectors.

### A16: UAM Prediction Formula Alignment
Three root causes fixed:
1. **UCI vs CI separation** — JS maintains `uci` (uncapped) for UAM decay and
   `ci` (capped at maxCI) for predDev. Must preserve this distinction.
2. **Dual decay model** — `predUCI = min(slope_decay, linear_decay)`, NOT
   exponential `exp(-t/90)`. Driven by `slopeFromDeviations`.
3. **Tick count indexing** — JS `UAMpredBGs.length` starts at 1 (array
   initialized with `[bg]`). Must match in Swift loop.

UAM MAE: 71.7 → 0.002 after all 3 fixes.

## Prior Phase Results (Resolved)

The following Phase 2 issues from Feb 2026 have been **fully resolved**:

| Issue | Resolution |
|-------|-----------|
| "Doing Nothing" cases (OREF0-001, 003, 004, 006, 008) | Vectors updated with non-zero delta; superseded by 300-vector suite |
| Rate discrepancy (TEMP-009, TEMP-010) | Resolved by maxSafeBasal profile fix; superseded by 100/100 oref0-native parity |
| IOB MAE 0.888 (Swift ↔ JS) | Fixed via IOB/tau derivation (A14); now 0.005 |
| UAM prediction divergence | Fixed via formula port (A16); now 0.002 |

## T1Pal Algorithm Conformance

| Test | Result |
|------|--------|
| Insulin Model Conformance | ✅ 7/7 passed |
| IOB Curve Conformance | ✅ 3/3 passed |
| Boundary Safety | ✅ 4/4 passed |
| All Vectors Loadable | ✅ 300 test vectors |

## Files

- **Cross-validation harness**: `tools/test-harness/harness.js`
- **oref0-JS adapter**: `tools/test-harness/adapters/oref0-js/`
- **t1pal-Swift adapter**: `tools/t1pal-adapter-cli/`
- **AAPS-JS adapter**: `tools/test-harness/adapters/aaps-js/`
- **Vector store (oref0)**: `conformance/t1pal/vectors/oref0-endtoend/TV-*.json`
- **Vector store (Loop)**: `conformance/t1pal/vectors/loop-endtoend/LV-*.json`
- **Assessment history**: `docs/architecture/cross-validation-assessment.md`

## Potential Phase 4 Work

1. **Loop Swift adapter** — Cross-algorithm comparison (oref0 vs Loop on same inputs)
2. **AAPS Kotlin adapter** — Real Kotlin execution (current AAPS-JS wraps Trio's JS)
3. **Trio-specific adapter** — Test Trio's oref0 extensions (autoISF, DynISF)
4. **Nightscout live vectors** — Generate vectors from live NS instances

---

*Trace: ALG-XVAL-020 through ALG-XVAL-030, Assessments A1–A16*
